# Chi phí bảo trì, tương thích và phạm vi tin cậy của phần mở rộng Maven

> **Build Tool Maven · Mở rộng Maven**  
> Tài liệu dành cho người thiết kế build, duy trì plugin/extension và vận hành CI trên **Maven 3.9.x, JDK 17**, đồng thời chuẩn bị kiểm thử khả năng tương thích Maven 4. Mục tiêu là đánh giá một phần mở rộng trước khi đưa vào POM hoặc `.mvn/extensions.xml`: **nó có thật sự cần thiết, chi phí duy trì đến đâu, chạy dưới cơ chế classloading/API nào, được cấp quyền gì, và có thể ảnh hưởng bao nhiêu dự án khi gặp lỗi hoặc bị xâm nhập?** Bài có bảng ra quyết định, POM Java 17 chạy được với plugin thay cho extension khi phù hợp, công cụ Java 17 đọc cấu hình extension không khởi động Maven, quy trình QA/rollback và các tình huống lỗi thực tế.

## 1. Vấn đề: “chỉ thêm một extension” có thể đổi toàn bộ hành vi build

Maven được thiết kế để mở rộng bằng **plugins** và **extensions**. Nhưng không phải mọi cơ chế mở rộng có cùng thời điểm nạp, classloader, tầm ảnh hưởng hoặc chi phí vận hành.

Một nhóm có thể thêm dependency vào `.mvn/extensions.xml` để cải thiện quan sát CI; một nhóm khác dùng build extension để hỗ trợ packaging mới; một nhóm nữa chỉ cần chạy một goal ở phase `validate`. Nhìn vào POM, cả ba đều có thể được gọi chung là “mở rộng Maven”, nhưng **tính chất bảo trì và ranh giới tin cậy rất khác**.

Khi extension lỗi:

- Build có thể **không khởi tạo được Maven session** để báo đúng lỗi project.
- Một lỗi tương thích Maven Core/API có thể ảnh hưởng **mọi module** hoặc mọi project dùng cùng cấu hình.
- Nếu extension thay dependency resolution/repository transport, artifact inputs cũng có thể thay đổi.
- Mã Java của plugin/extension chạy trong **Maven JVM với quyền của tài khoản chạy Maven**; việc tạo classloader riêng **không phải một sandbox về quyền filesystem/network/secrets**.
- Local developer, IDE embedded Maven, CI runner và môi trường release có thể dùng Maven/JDK/extension inventory khác nhau.
- Một lần nâng Maven Core/JDK hoặc đổi phiên bản extension có thể gây `NoSuchMethodError`, `ClassNotFoundException`, `LinkageError` hoặc component lookup error.

Do đó câu hỏi kỹ thuật đúng là: **“Mình cần mở rộng _điểm nào_ của Maven, và có cơ chế nào ít đặc quyền hơn để đạt cùng kết quả?”**

### 1.1. Phân biệt hai loại rủi ro

| Nhóm | Câu hỏi | Hậu quả khi bỏ qua |
| --- | --- | --- |
| **Bảo trì và tương thích** | Ai nâng phiên bản, kiểm thử API, sửa code, hỗ trợ Maven/JDK mới? | Build hỏng sau nâng cấp; CI/IDE lệch nhau |
| **Phạm vi tin cậy** | Mã được nạp khi nào, có thể nhìn thấy/đổi gì, chạy bằng quyền nào? | Lộ secrets, sửa artifact, thay input, ảnh hưởng quá nhiều dự án |

Không nên đánh đổi một rủi ro bảo mật lớn để giảm vài dòng cấu hình. Ngược lại, không nên viết một core extension phức tạp khi goal Maven plugin đã đáp ứng được yêu cầu.

## 2. Ba lựa chọn cần phân biệt: plugin, build extension, core extension

Theo tài liệu Apache Maven *Using Extensions*, **core extensions nạp sớm**, còn **build extensions nạp muộn hơn**. Plugins thông thường cung cấp goals được Maven thực thi theo CLI hoặc lifecycle.

| Tiêu chí | Plugin thông thường | Build extension | Core extension |
| --- | --- | --- | --- |
| Dùng để | Chạy một tác vụ như compile, format, package, scan | Bổ sung thành phần/cơ chế liên quan project, packaging, lifecycle hoặc plugin | Bổ sung/điều chỉnh thành phần Maven ở mức khởi động/core |
| Cách khai báo phổ biến | `<build><plugins><plugin>...` | `<build><extensions>...` hoặc plugin `<extensions>true</extensions>` | `.mvn/extensions.xml`, `-Dmaven.ext.class.path`, cấu hình JVM/Maven installation phù hợp |
| Thời điểm | Theo goal/phase | Khi xử lý build model/project | Sớm trong Maven startup/session |
| Classloader | Plugin realm với Maven API và dependencies phù hợp | Build extension realms/project realm | Core extension realm/API exposure liên quan Maven Core |
| Khả năng tác động | Goal + code do plugin thực thi | Có thể đổi project behavior, plugin integrations | Có thể tham gia/hook vào core-level behavior |
| Nguy cơ vận hành | Vẫn có quyền process, nhưng phạm vi kích hoạt rõ hơn | Cao hơn khi tác động nhiều goals/modules | Cao nhất khi làm lỗi bootstrap hoặc thay core behavior |
| Cách rollback phổ biến | Bỏ execution/đổi plugin version rồi build lại | Bỏ `<extensions>` hoặc `extensions=true` trên bản sao project | Loại `.mvn/extensions.xml`/global loading trên môi trường kiểm thử, khởi chạy lại Maven |
| Khi phù hợp | Có goal đáp ứng nhu cầu trong một phase | Thực sự cần cung cấp build extension contract | Cần thành phần rất sớm mà plugin/build extension không đáp ứng |

**Không đọc bảng như một “thang quyền hệ điều hành” mà Maven tự áp**. Plugin và extension đều là **mã được thực thi trong Maven process**, có thể truy cập files/network/credentials nếu môi trường chạy cho phép. Classloader isolation chủ yếu giải quyết **khả năng nhìn thấy classes và APIs**, không phải sandbox security.

### 2.1. Trường hợp plugin là đủ

- Sinh file cấu hình từ properties.
- Đóng gói, nén, checksum hoặc xuất báo cáo.
- Đăng ký source/resource roots qua goal của plugin phù hợp.
- Chạy code generation theo lifecycle.
- Phân tích dependencies, kiểm tra license, vulnerability hoặc formatting.
- Tạo một build marker trong `target/`.

Các hành động này thường có thể thực hiện bằng plugin goal được bind vào phase phù hợp, **không cần can thiệp Maven bootstrap**.

### 2.2. Khi build extension có cơ sở

- Một plugin phải cung cấp **cơ chế packaging/lifecycle mapping** đặc thù, không chỉ chạy goal sau khi model đã dựng.
- Dự án cần integration sâu với Maven project class realm hoặc extension points đã được Maven hỗ trợ.
- Một phần của build phải được nhận diện bởi Maven **trước khi goals thông thường đủ để thực hiện nhiệm vụ**.

Hãy kiểm tra documentation của artifact vì một plugin có thể triển khai chức năng extension nhưng người dùng chỉ cần một số goals, không cần đặt `<extensions>true</extensions>`.

### 2.3. Khi core extension có cơ sở

- Cần can thiệp **sớm** vào Maven execution, ví dụ thành phần core, lifecycle participant hoặc cơ chế transport/resolver integration đặc biệt.
- Có yêu cầu tích hợp cấp tổ chức trên nhiều projects và có chủ sở hữu rõ.
- API/extension point mà plugin thường không thể đáp ứng đúng thời điểm.

**Một thay đổi “toàn bộ build” không tự động cần core extension.** Đôi khi parent POM, settings/mirror, CI step hoặc Maven plugin đủ. Tính năng càng nạp sớm, chi phí review/rollback càng cần lớn.

## 3. Ba cách nạp extension không tương đương

### 3.1. Core extension tại `.mvn/extensions.xml`

Một project có thể khai báo core extension bằng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<extensions xmlns="http://maven.apache.org/EXTENSIONS/1.0.0">
    <extension>
        <groupId>org.example.internal</groupId>
        <artifactId>approved-core-extension</artifactId>
        <version>1.2.3</version>
    </extension>
</extensions>
```

**Đây chỉ là ví dụ cú pháp; tọa độ `org.example.internal:approved-core-extension:1.2.3` không được khẳng định tồn tại** và không được copy vào lab đang hoạt động. Nếu thêm file này vào `.mvn/extensions.xml` rồi chạy Maven, Maven có thể cố resolve nó **trước khi thực hiện goals** và fail ngay khi extension không có.

Nội dung `.mvn/extensions.xml` là **một build input có thể thực thi**: PR sửa file ấy cần security review tương tự PR sửa CI scripts hoặc parent POM quan trọng.

### 3.2. Core extension qua `maven.ext.class.path`

Một Maven invocation có thể nhận một JAR qua:

```bash
mvn -Dmaven.ext.class.path=/path/to/approved-extension.jar validate
```

Lệnh này **chỉ minh họa interface**; không có JAR thật ở đường dẫn trên. File được cấp từ `maven.ext.class.path` phải được kiểm soát provenance, bytes và compatibility; đây không phải tùy chọn “đổi log level” đơn thuần.

Vì có thể đặt qua command-line/environment, chỉ đọc POM của project **không đủ** để biết mọi extension đã nạp.

### 3.3. Core extension tại Maven installation hoặc user scope

Tài liệu Maven cũng mô tả:

```text
${maven.home}/lib/ext
```

và với Maven 3.10.0 trở đi có thể có các file extension descriptor cấp người dùng/installation:

```text
${user.home}/.m2/extensions.xml
${maven.home}/conf/extensions.xml
```

Các paths và tính năng phụ thuộc **phiên bản Maven đang chạy**. Đối với Maven 3.9.x, **không dựa vào user-level descriptor mới của 3.10** như cơ chế đã có sẵn. Nếu chạy Maven 4, phải xem docs/version tương ứng.

**Rủi ro:** extension được nạp ngoài project repo có thể khiến máy developer khác CI dù cùng commit/POM. Khi điều tra “chỉ máy A bị lỗi”, phải xem môi trường Maven installation/user/CLI chứ không chỉ `.mvn/extensions.xml`.

### 3.4. Build extension tại `<build><extensions>`

Đoạn POM minh họa:

```xml
<build>
    <extensions>
        <extension>
            <groupId>org.example.internal</groupId>
            <artifactId>approved-build-extension</artifactId>
            <version>2.0.0</version>
        </extension>
    </extensions>
</build>
```

Đây là **fragment**, không phải POM runnable; artifact giả định. Nó thể hiện một extension theo **project build model**, nạp muộn hơn core extension trong cơ chế Maven.

### 3.5. Build extension qua plugin `<extensions>true</extensions>`

Đoạn minh họa khác:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.example.internal</groupId>
            <artifactId>custom-packaging-plugin</artifactId>
            <version>2.0.0</version>
            <extensions>true</extensions>
        </plugin>
    </plugins>
</build>
```

`extensions=true` **không chỉ có nghĩa “bật plugin”**; nó cho Maven biết plugin đóng vai trò cung cấp build extension. Không thêm flag này để giải quyết lỗi goal không tìm thấy nếu plugin không thực sự là extension.

### 3.6. `pluginManagement` không tự kích hoạt extension

Khi khai báo version/config trong:

```xml
<pluginManagement>...</pluginManagement>
```

ta đang **quản lý defaults cho plugins**. Điều đó không đồng nghĩa tất cả plugin trong `pluginManagement` sẽ được thực thi như một execution hay biến thành core extension.

Tương tự, việc có một JAR dependency trong `<dependencies>` **không** biến nó thành Maven extension. Project dependency, plugin dependency, build extension và core extension là **những đường nạp khác nhau**.

## 4. Thời điểm nạp quyết định tầm ảnh hưởng

Mô hình đơn giản hóa:

```text
mvn starts
    |
    +-- Maven distribution / bootstrap
    |
    +-- Core extensions (.mvn/extensions.xml, CLI, env/installation)
    |     Có thể thêm hoặc thay components/behaviors sớm
    |
    +-- Đọc model/settings, parent POM, active profiles, project reactor
    |
    +-- Build extensions và plugin extension integrations
    |
    +-- Resolve plugins/goals, lifecycle executions
    |
    +-- Plugin goals: validate -> compile -> test -> package -> verify ...
    |
    +-- Final artifacts, tests, CI evidence
```

Sơ đồ **cố ý giản lược** thứ tự nội bộ của Resolver/model builder và không thay source code Maven. Nó dùng để phân biệt **tính chất early-boot**: nếu core extension gây lỗi, các goals ở `validate`, test hay Maven Enforcer có thể **chưa kịp chạy**.

### 4.1. Tại sao Enforcer không là bộ lọc đủ cho core extension?

Giả sử POM có Enforcer rule cấm một plugin. Rule ấy chạy **khi Maven đã khởi tạo đủ để execute goal**. Nhưng core extension từ `.mvn/extensions.xml` có thể được nạp **trước** phase đó.

Vì vậy **không được** tuyên bố “đã có `maven-enforcer-plugin` thì mọi core extensions đều được kiểm trước khi thực thi”. Cần **pre-build policy scanning** do CI runner thực hiện **trước khi gọi Maven**, cộng với approved extension inventory/repository policy.

### 4.2. Classloader không phải security sandbox

Maven Classloading Guide mô tả các realms như Maven Core, Core Extensions, Project/Build Extensions và Plugin. Chúng giúp quản lý:

- Class visibility.
- Maven API imports và exported packages.
- Version conflicts giữa plugin/extension dependencies.
- Component/service injection trong Maven runtime.

Nhưng một extension Java đã được JVM thực thi có thể dùng `java.nio.file.Files`, sockets, process APIs và environment variables theo **quyền OS/process/container** của job.

**Không có quyền filesystem/network khác nhau chỉ vì Maven chọn một realm khác.** Muốn giới hạn rủi ro thực sự, cần runner isolation, egress policy, secret separation, repository access controls và review artifacts đã execute.

### 4.3. Plugin cũng là mã tin cậy

Không vì plugin có scope hẹp hơn extension mà nó tự an toàn. Một plugin goal có thể:

- Thực thi external tools hoặc shell commands.
- Đọc credentials trong job.
- Tạo/sửa files và artifacts.
- Tải thêm files qua HTTP.
- Thay source/generated resources.
- Ghi thông tin nhạy cảm ra logs/network.

Vì vậy **plugin-first** là lựa chọn giảm mức can thiệp vào Maven core và giảm chi phí coupling, **không phải một đảm bảo mật mã rằng plugin không thể gây hại**.

## 5. Mô hình chi phí bảo trì: không chỉ đếm số dòng Java

Một phần mở rộng cần được đánh giá theo tổng chi phí vòng đời:

```text
TCO ~ thiết kế + kiểm thử ban đầu + nâng phiên bản Maven/JDK
    + bảo trì dependency graph + CI/platform compatibility
    + hỗ trợ developer/IDE + incident investigation
    + phát hành/rollback + quản trị khóa, repo và supply-chain
```

Đây là **mô hình lập kế hoạch**, không phải công thức tính tiền chính thức của Apache Maven.

### 5.1. Ma trận chi phí tương đối

| Chi phí | Plugin đã được duy trì | Custom plugin | Build extension | Core extension |
| --- | --- | --- | --- | --- |
| Viết code/lifecycle integration | Thấp nếu có sẵn | Trung bình | Trung bình–cao | Cao |
| Phụ thuộc Maven internals | Thường thấp hơn nếu dùng APIs ổn định | Tùy API | Cao hơn | Thường cao nhất |
| Kiểm thử Maven/JDK matrix | Cần | Cần | Nhiều hơn | Nhiều nhất |
| Onboarding IDE/CLI | Dễ hơn | Cần setup goal/phase | Cần quản lý extension model | Cần giải quyết early startup/global injection |
| Điều tra lỗi classloader | Có | Có | Nhiều hơn | Phức tạp nhất |
| Quyền review/security | Bắt buộc | Bắt buộc | Chặt | Chặt nhất |
| Blast radius | Tùy goal/module | Tùy goal/module | Project/reactor | Core/session, có thể nhiều projects |
| Rollback | Bỏ execution/version | Bỏ execution/version | Sửa POM build extension | Sửa `.mvn`/installation trước khi gọi Maven |

Mức “cao/thấp” là **thứ tự ưu tiên thiết kế**, không phải số đo chắc chắn. Một core extension nhỏ được duy trì tốt có thể ổn định hơn một custom plugin kém chất lượng. Cần bằng chứng kiểm thử và ownership thực tế.

### 5.2. Những chi phí bị ẩn

- Một extension được commit vào project nhưng **không ai giữ compatibility matrix**.
- Docs cũ chỉ thử Maven 3.6 và JDK 8, trong khi CI đã chuyển Maven 3.9/JDK 17.
- Extension tự phụ thuộc một version Maven Core/Resolver cụ thể, rồi Maven upgrade phá class linkage.
- Các dự án khác nhau có phiên bản extension khác nhau, tạo “snowflake builds”.
- Developer phải sửa Maven installation bằng tay; onboarding khó, IDE embedded Maven không khớp.
- Build mất hàng phút trong bootstrap trước cả khi log phase đầu tiên.
- Secrets của release runner xuất hiện sớm hơn chính policy gate.
- Extension làm build không tái lập do tải network, đóng gói timestamp hoặc đổi cache state.
- Không có tài liệu gỡ extension khi hỏng, dẫn tới phải sửa trực tiếp runner image đang sản xuất.

Đây là lý do **phần mở rộng được tổ chức dùng rộng phải có chủ sở hữu và vòng đời release như một sản phẩm nội bộ**.

### 5.3. Quy tắc ưu tiên giảm chi phí

1. Dùng tính năng Maven/CI có sẵn.
2. Dùng **Maven plugin hiện có** được duy trì và ghim version.
3. Nếu cần logic riêng, cân nhắc custom goal/Mojo với **public plugin APIs**.
4. Chỉ dùng build extension khi thật sự cần project extension hook.
5. Chỉ dùng core extension khi giải thích được **vì sao plugin/build extension không thể giải quyết đúng thời điểm**.
6. Đánh giá việc bỏ extension định kỳ; tính năng từng cần ở Maven cũ có thể đã trở thành built-in feature.

## 6. Tương thích Maven/JDK không đồng nghĩa tương thích Java source

Một extension/plugin Java có ba tầng version liên quan:

| Tầng | Ví dụ | Rủi ro |
| --- | --- | --- |
| Java bytecode/runtime | Class compiled `--release 17` | Nếu Maven JVM chạy Java thấp hơn, `UnsupportedClassVersionError` |
| Maven Core/Plugin APIs | MavenProject, Resolver, Plexus/Sisu, Plugin API | Thay API/DI/classloading có thể gây `NoSuchMethodError`/component lookup |
| Plugin/extension dependencies | Guice, SLF4J, Wagon, Resolver, ASM... | Class realm/version conflicts; bridge API thay đổi |

Một Java class biên dịch thành công **không chứng minh extension dùng được với mọi Maven versions**. Ngược lại, Maven project application compile `--release 17` không bảo đảm chính Maven extension được viết cũng target Java 17; đó là **artifact/JVM khác**.

### 6.1. Maven 3.9.x và Maven 4

Apache Maven hướng dẫn migration từ Maven 3 sang Maven 4 theo ba bước:

1. Chuẩn hóa Maven 3/JDK/toolchain và nâng plugins phù hợp.
2. Chạy compatibility tests với Maven 4 theo tài liệu thời điểm áp dụng.
3. Chỉ đưa các Maven 4-only features vào sau khi quyết định bỏ hỗ trợ Maven 3.

Maven 4 yêu cầu **JDK 17 để chạy Maven** và có những thay đổi core/plugin APIs, dependency injection, lifecycle defaults. Những extensions dựa vào internal APIs hoặc Maven 2-era integration có thể bị lỗi.

**Không khẳng định mọi Maven 3 plugin/extension tương thích 100% với Maven 4.** Kiểm tra plugin/extension maintainer documentation, phát hiện warnings và chạy trên Maven distribution thực tế sẽ dùng.

### 6.2. Tại sao “Maven API không đổi package name” vẫn có thể hỏng?

Cùng một FQCN có thể đổi:

- Constructor/method signature.
- Method return type hoặc default behavior.
- Component injection bindings.
- Lifecycle timing.
- Classloader isolation rules hoặc module visibility.
- Resolver transport/cache API contracts.

Do đó compile với version A rồi chạy với version B có thể gây binary linkage error **ngay cả khi source vẫn compile** trên classpath khác.

### 6.3. Plugin validation warnings

Với Maven versions hỗ trợ, có thể dùng:

```bash
mvn -Dmaven.plugin.validation=verbose -B verify
```

để xem thêm diagnostics về plugins sử dụng API cũ hoặc vấn đề validation theo Maven version. Đó **không phải scanner xác thực cryptographic**, và warnings không tự bao trùm toàn bộ core extension compatibility.

Nếu POM có extension phá bootstrap, có thể không tới được giai đoạn in cảnh báo plugins; cần kiểm tra extension riêng.

### 6.4. `requireMavenVersion` hữu ích nhưng không giải quyết early bootstrap

Một rule:

```xml
<requireMavenVersion>
    <version>[3.9,4.0)</version>
</requireMavenVersion>
```

có thể từ chối Maven ngoài 3.9.x trong lifecycle test project. Nó **không kiểm extension trước khi extension được nạp**, nên người làm security review vẫn cần preflight ngoài Maven.

### 6.5. Matrix tối thiểu trước khi phát hành extension

| Hàng thử | Maven | JDK | Kiểm tra |
| --- | --- | --- | --- |
| Development chính | 3.9.x được tổ chức chuẩn hóa | 17 | Bootstrap, compile/tests, plugin output |
| Build không extension | Cùng version | 17 | Baseline/rollback so sánh |
| Supported JDK mới hơn | 3.9.x theo support policy | 21 nếu tổ chức dùng | API/classfile/runtime compatibility |
| Candidate Maven major | Maven 4 version tổ chức đang đánh giá | 17+ | Startup, APIs, DI, dependencies, lifecycle |
| Minimal network/cache | Maven3.9/JDK17 | 17 | Resolve extension từ approved repository |
| Offline đã prefetch | Maven3.9/JDK17 | 17 | Không phụ thuộc tải ngoài dự kiến |
| Multi-module reactor | Maven3.9/JDK17 | 17 | Shared state, threading/goal order |
| IDE delegate/embedded | Maven distribution được IDE dùng | Theo cấu hình IDE | Build model import + early extension behavior |

**Không bắt tất cả projects hỗ trợ JDK 21/Maven4 ngay.** Matrix phải bám theo **chính sách supported environments**. Nhưng nếu định nâng, có bằng chứng trước khi bật extension trên release runners.

## 7. Phạm vi tin cậy: extension nhìn thấy gì và có thể gây tác động nào?

Một bảng đe dọa định tính:

| Tài sản / quyền | Plugin goal | Build extension | Core extension |
| --- | --- | --- | --- |
| Project source/output | Có thể truy cập bằng quyền Maven process | Có thể | Có thể |
| Network egress | Có thể nếu runner cho phép | Có thể | Có thể |
| Maven settings/credentials | Có thể đọc nếu không được cách ly | Có thể | Có thể |
| Repository resolution | Có thể ảnh hưởng qua goal/config | Có thể tích hợp project resolution | Có thể ảnh hưởng core/resolver rất sớm |
| Plugin/component classloading | Qua plugin realm/APIs | Qua build extension realm | Qua core extension realm/APIs |
| Tác động trước `validate` | Thường không cần để chạy goal thông thường | Có thể trong model/build setup | **Có, vì early loading** |
| Phạm vi nhiều projects | Nếu cùng plugin được áp hoặc global CI logic | Nếu được áp diện rộng | Có thể rất rộng nếu user/global extension |
| Bị Maven tự sandbox quyền OS? | **Không** | **Không** | **Không** |

**Không hiểu “có thể” là Maven công khai bảo đảm mọi API private.** Khả năng can thiệp cụ thể còn phụ thuộc extension point, Maven version và cách Maven realms cung cấp components. Nhưng ở mức security design, **đã nạp Java code vào Maven process phải được coi là execution-capable**.

### 7.1. Vì sao secret injection timing quan trọng?

Nếu protected release job cấp publisher token và signing key **ngay đầu job**, một core extension đã được nạp trước khi Enforcer/QA chạy có thể **có khả năng truy cập secrets trong environment**. Đây là nguy cơ thiết kế, không cần giả định extension cụ thể có hành vi độc hại.

**Mẫu cải thiện:**

```text
Untrusted PR/build:
  - Maven clean verify
  - approved read-only dependencies
  - không có signing key hoặc publish token
        |
        v
Protected QA + artifact digest
        |
        v
Isolated signer:
  - chỉ nhận final bytes đã approved
  - không khởi chạy project Maven chứa extension tùy ý
        |
        v
Publisher:
  - scoped write token + approved repository
  - không chạy untrusted extension
```

Mọi việc thực thi mã từ source/POM cần được coi là rủi ro khi có secrets. **Tách jobs/runner/credentials** quan trọng hơn việc chỉ phân loại artifact là “plugin” hay “extension”.

### 7.2. `.mvn/extensions.xml` là input của build, không phải metadata vô hại

Trong code review, thay đổi file này có thể thay:

- Artifact được Maven resolve và thực thi.
- Maven Core components/behavior.
- Repository transport hoặc model participant.
- Build startup failures và logs.
- Kết quả output nếu extension thay inputs/lifecycle.

Vì vậy file `.mvn/extensions.xml` cần **CODEOWNERS/reviewer được ủy quyền** hoặc policy kiểm tương đương, approval tương tự thay release workflow.

### 7.3. Repository supply chain

Đối với extension tọa độ Maven:

```text
groupId:artifactId:version
```

**Ghim version là cần nhưng chưa đủ**. Nếu upstream cho overwrite cùng tọa độ, bytes vẫn có thể đổi. Hãy:

- Tải chỉ từ approved repositories/mirror.
- Ghi SHA-256 thực và kiểm trusted expected digest khi cần.
- Cấm mutable release overwrite.
- Cấm dynamic versions/SNAPSHOT theo release policy.
- Giới hạn quyền upload extension namespace.
- Duy trì SBOM/dependency inventory và vulnerability/license review.
- Khi dùng third-party extension, theo dõi maintenance/release cadence và security advisories.

Một SHA-256 lấy từ chính cùng repository do attacker kiểm soát **không tự bảo đảm trust**; expected digest/provenance cần được bảo vệ độc lập theo mức rủi ro.

### 7.4. Environment-level extension injection

Ngoài project `.mvn/extensions.xml`, kiểm:

```text
MAVEN_OPTS
JAVA_TOOL_OPTIONS
.mvn/jvm.config
.mvn/maven.config
-Dmaven.ext.class.path
${maven.home}/lib/ext
```

và descriptor người dùng/installation khi Maven version hỗ trợ. Những mục này **không đồng nhất**: một số là JVM args/agents, số khác cấu hình Maven core extension. Nhưng chúng đều là input môi trường có thể làm build khác nhau.

**Đừng chỉ kiểm một POM rồi khẳng định biết toàn bộ build execution code.**

## 8. Bài lab: giải quyết một custom build step bằng plugin, không dùng extension

Một tình huống thực tế: nhóm muốn in hoặc tạo một marker để CI biết đã chạy bước kiểm tra chuẩn hóa. Vì tác vụ này chạy ở `validate`, nó **không cần thay Maven core**.

Lab dưới đây dùng **Maven AntRun Plugin 3.2.0**, một plugin hiện có được Apache Maven tài liệu hóa. Nó tạo `target/plugin-step.txt` với marker `plugin-step=ok`. Mục tiêu là minh họa **lựa chọn plugin-first** và tách biệt từ core extension, không khuyến nghị AntRun là giải pháp duy nhất cho mọi custom build step. AntRun có thể chạy Ant tasks, do đó **vẫn phải review code**.

### 8.1. Cây thư mục

```text
extension-boundary-lab/
├── pom.xml
├── audit/
│   └── ExtensionAudit.java
└── src/
    ├── main/java/org/example/extcost/PolicyApp.java
    └── test/java/org/example/extcost/PolicyAppTest.java
```

**Không có `.mvn/extensions.xml` ở baseline**, không có `<build><extensions>`, và không có plugin `<extensions>true</extensions>`. Tool Java trong `audit/` đọc cấu hình nhưng không bị đóng vào JAR.

### 8.2. `pom.xml` runnable đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>extension-boundary-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Extension Boundary Lab</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <version>3.5.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>org.example.extcost.PolicyApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.2.0</version>
                <executions>
                    <execution>
                        <id>write-build-policy-marker</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}"/>
                                <echo file="${project.build.directory}/plugin-step.txt"
                                      message="plugin-step=ok"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>validate-local-toolchain</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
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

**Giải thích:**

- `maven-antrun-plugin` là **plugin goal thông thường** với execution id và phase `validate`; không có `<extensions>true</extensions>`.
- `<mkdir>` bảo đảm `target` tồn tại, `<echo>` tạo file marker. Đây là hành động minh họa, không chạy shell command bên ngoài.
- Maven Enforcer Plugin đặt ngưỡng Maven 3.9.x và JDK 17+ cho **lab**. Khi thử Maven 4, rule này sẽ cố ý chặn phiên bản ngoài `[3.9,4.0)`; migration test phải dùng **fixture/phương án policy riêng có phê duyệt**, không chỉnh release policy tùy tiện.
- `project.build.outputTimestamp` cố định archive timestamps khi plugins hỗ trợ, không bảo đảm mọi build inputs đáng tin.
- Mục tiêu release/runtime là JAR có đúng main class; AntRun marker ở `target/plugin-step.txt` **không tự đi vào application JAR**.
- Plugin goal có thể thất bại nếu Maven không tải được plugin từ approved repositories, giống các plugins khác; điều đó **không** khiến nó biến thành core extension.

### 8.3. `src/main/java/org/example/extcost/PolicyApp.java`

```java
package org.example.extcost;

import java.util.Locale;

public final class PolicyApp {
    private PolicyApp() {
    }

    public static String normalize(String value) {
        return value == null ? ""
                : value.strip().toUpperCase(Locale.ROOT);
    }

    public static String message(String value) {
        return "EXTENSION POLICY: " + normalize(value);
    }

    public static void main(String[] args) {
        System.out.println(message(" plugin first "));
    }
}
```

Program hoàn toàn sử dụng JDK 17, nên JAR main **không cần third-party runtime dependency**. `String.strip()` có từ Java 11; `Locale.ROOT` tránh phụ thuộc locale người dùng cho uppercase.

### 8.4. `src/test/java/org/example/extcost/PolicyAppTest.java`

```java
package org.example.extcost;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class PolicyAppTest {
    @Test
    void normalizesWhitespace() {
        assertEquals("PLUGIN FIRST",
                PolicyApp.normalize(" plugin first "));
    }

    @Test
    void normalizesNull() {
        assertEquals("", PolicyApp.normalize(null));
    }

    @Test
    void buildsMessage() {
        assertEquals("EXTENSION POLICY: PLUGIN FIRST",
                PolicyApp.message("plugin first"));
    }
}
```

JUnit Jupiter chỉ ở test scope. Surefire 3.6.1 tìm class `PolicyAppTest` theo convention và chạy ba test methods nếu dependencies/plugins được resolve thành công.

### 8.5. Chạy build

Trong `extension-boundary-lab/`:

```bash
java -version
mvn -version
mvn -B -ntp clean verify
```

Kết quả kỳ vọng có:

```text
target/plugin-step.txt
target/classes/org/example/extcost/PolicyApp.class
target/test-classes/org/example/extcost/PolicyAppTest.class
target/surefire-reports/TEST-org.example.extcost.PolicyAppTest.xml
target/extension-boundary-lab-1.0.0.jar
```

Dòng test summary dự kiến:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **kỳ vọng từ code**, không phải log đã được thực thi. Maven stdout đầy đủ phụ thuộc environment/versions.

### 8.6. Kiểm tra plugin đã chạy

Linux/macOS:

```bash
cat target/plugin-step.txt
```

Windows PowerShell:

```powershell
Get-Content .\target\plugin-step.txt
```

Nội dung có dòng:

```text
plugin-step=ok
```

Ant Echo có thể ghi line ending theo runtime/plugin, nên kiểm **nội dung marker** chứ không đoán checksum riêng của text file.

### 8.7. Chạy JAR thực tế

```bash
java -jar target/extension-boundary-lab-1.0.0.jar
```

**Stdout chính xác do Java main in:**

```text
EXTENSION POLICY: PLUGIN FIRST
```

Cấu hình Maven JAR Plugin có `Main-Class` đúng, còn app chỉ cần Java runtime. Việc JAR chạy **không chứng minh extension được sandbox**; bài lab **không nạp extension** và chỉ nhằm so sánh cách mở rộng bằng plugin.

### 8.8. Vì sao ví dụ này thuyết phục?

Giả sử yêu cầu thật là “mỗi build phải tạo một marker trước compile”. Plugin goal ở `validate` đủ làm việc đó. Nếu thay bằng core extension:

- Người duy trì phải xử lý Maven bootstrap/classloader/extension lifecycle.
- Một lỗi startup có thể làm cả Maven session không chạy.
- Security review phải kiểm extension chạy sớm với quyền của CI process.
- Tăng matrix compatibility Maven/JDK/IDE/repository transport.
- Rollback phức tạp hơn một plugin execution.

**Không có giá trị tương xứng** khi goal thông thường đã giải quyết yêu cầu.

## 9. Tool Java 17 đọc cấu hình extension mà không khởi động Maven

Khi cần kiểm tra `.mvn/extensions.xml` **trước** khi Maven có cơ hội nạp extensions, có thể dùng tool đọc XML độc lập bằng JDK 17.

Dưới đây là `audit/ExtensionAudit.java` đầy đủ. Nó:

1. Đọc `pom.xml` trực tiếp bằng JDK XML parser.
2. Đếm `<build><extensions><extension>`.
3. Đếm các plugins có `<extensions>true</extensions>` trực tiếp trong `<build><plugins>`.
4. Nếu có `.mvn/extensions.xml`, đếm core extension entries.
5. Báo **không có extension trực tiếp** hoặc **cần security review**.
6. Thoát mã lỗi `3` nếu có declaration cần review; dùng được làm preflight gate trong một lab nhỏ.

### 9.1. `audit/ExtensionAudit.java`

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;

public final class ExtensionAudit {
    private ExtensionAudit() {
    }

    private static Document load(Path path) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        factory.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
        factory.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        try (InputStream input = Files.newInputStream(path)) {
            return factory.newDocumentBuilder().parse(input);
        }
    }

    private static String local(Node node) {
        String name = node.getLocalName();
        return name == null ? node.getNodeName() : name;
    }

    private static List<Element> children(
            Element parent, String wanted) {
        List<Element> found = new ArrayList<>();
        if (parent == null) {
            return found;
        }

        for (Node node = parent.getFirstChild();
                node != null; node = node.getNextSibling()) {
            if (node instanceof Element element
                    && wanted.equals(local(element))) {
                found.add(element);
            }
        }
        return found;
    }

    private static Element child(Element parent, String wanted) {
        List<Element> matches = children(parent, wanted);
        return matches.isEmpty() ? null : matches.get(0);
    }

    private static String content(Element parent, String wanted) {
        Element match = child(parent, wanted);
        return match == null ? ""
                : match.getTextContent().trim();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java audit/ExtensionAudit.java PROJECT_DIR");
        }

        Path root = Path.of(args[0]);
        Document pom = load(root.resolve("pom.xml"));
        Element build = child(pom.getDocumentElement(), "build");

        int buildExtensions = children(
                child(build, "extensions"), "extension").size();

        int pluginExtensionFlags = 0;
        for (Element plugin :
                children(child(build, "plugins"), "plugin")) {
            if ("true".equalsIgnoreCase(
                    content(plugin, "extensions"))) {
                pluginExtensionFlags++;
            }
        }

        Path coreFile = root.resolve(".mvn/extensions.xml");
        int coreExtensions = Files.exists(coreFile)
                ? children(load(coreFile).getDocumentElement(),
                        "extension").size()
                : 0;

        System.out.println(
                "core-extension-entries=" + coreExtensions);
        System.out.println(
                "build-extension-entries=" + buildExtensions);
        System.out.println(
                "plugin-extension-flags=" + pluginExtensionFlags);

        boolean review = coreExtensions + buildExtensions
                + pluginExtensionFlags > 0;

        System.out.println(review
                ? "policy=REVIEW_REQUIRED"
                : "policy=NO_EXTENSION_DECLARATIONS");

        if (review) {
            System.exit(3);
        }
    }
}
```

**Giới hạn có chủ đích:**

- Tool chỉ đếm declarations **trực tiếp** trong POM root và `.mvn/extensions.xml` ở path được chỉ định.
- Nó **không** resolve parent POM, BOM, active profiles, imported plugins, Maven user/global extensions, `maven.ext.class.path` hoặc Java agents.
- Nó không xác minh version, signatures, provenance, repository origins hay mã Java bên trong artifact.
- `NO_EXTENSION_DECLARATIONS` nghĩa là **không thấy ba dạng khai báo được tool quét**, **không** có nghĩa “Maven build an toàn” hoặc “không có bất cứ extension nào”.
- `REVIEW_REQUIRED` không mặc định có nghĩa malicious; nó chỉ tạo gate để người được ủy quyền đánh giá.
- XML parser cấm DOCTYPE/external entities nhằm tránh mở rộng XML inputs tùy ý; đây là defensive parsing, không thay filesystem/CI trust isolation.

### 9.2. Chạy tool trên baseline project

Khi chưa tạo `.mvn/extensions.xml`:

```bash
java audit/ExtensionAudit.java .
```

**Stdout chính xác:**

```text
core-extension-entries=0
build-extension-entries=0
plugin-extension-flags=0
policy=NO_EXTENSION_DECLARATIONS
```

Process exit code `0`. Bản POM baseline có `maven-antrun-plugin` và `maven-enforcer-plugin`, **nhưng chúng là plugins thông thường**, nên `plugin-extension-flags=0`.

### 9.3. Nếu có extension trong bản sao project

Nếu trong **một bản copy chỉ dùng để review** bạn thêm `.mvn/extensions.xml` theo ví dụ mục 3.1, khi chạy standalone tool:

```bash
java audit/ExtensionAudit.java .
```

Nó sẽ thấy một core entry và in:

```text
core-extension-entries=1
build-extension-entries=0
plugin-extension-flags=0
policy=REVIEW_REQUIRED
```

Process exit code **3**. **Không chạy `mvn` trên bản copy có tọa độ extension giả định** và không xem một POM scan “PASS” là bằng chứng runtime đã nạp extension đó thành công.

### 9.4. Chạy preflight scanner trước Maven, không ngược lại

Một workflow CI đơn giản:

```bash
set -euo pipefail
java audit/ExtensionAudit.java .
mvn -B -ntp clean verify
java -jar target/extension-boundary-lab-1.0.0.jar
```

Nếu project có extension declaration, tool exit nonzero khiến shell dừng **trước khi gọi Maven**. Đây là một **gate mô phỏng**; với dự án có extensions được phê duyệt, cần chuyển từ “deny all” sang **allowlist đã ký duyệt với exact version/digest/source** chứ không xóa gate.

Nếu CI chạy chính `mvn` để thực hiện scanner, core extension có thể đã được nạp; **mục đích là dùng JDK tool độc lập trước Maven startup**.

### 9.5. Tránh chạy scanner với quyền và secrets không cần thiết

Tool chỉ đọc files; nó không cần access tokens hoặc signing keys. Chạy trong job **không có secrets release** và repo checkout có trust level được kiểm soát. Nếu scanner code nằm trong cùng PR không tin cậy, attacker có thể tự sửa scanner hoặc workflow để bỏ qua gate; trong production, policy scanner nên được **cấp từ một nguồn tin cậy độc lập** với chính nội dung đang được kiểm.

## 10. Compatibility contract cho extension nên được ghi rõ

Một extension nội bộ nên công bố:

```text
Extension identity:
  groupId / artifactId / exact version
  Source repository / release commit / source digest
  Artifact SHA-256 / signing identity
Supported Maven:
  tested 3.9.x distributions; candidate Maven4 separately
Supported JDK:
  runtime Java 17; optional JDK21 tests if supported
Extension loading:
  core via .mvn/extensions.xml OR build via POM
Required permissions:
  read-only repositories, no signer/publisher token
  network egress policy
Owner:
  team / backup maintainer / escalation path
Rollback:
  remove exact declaration in a controlled copy
  revert Maven runner image/config
Tests:
  unit, integration, multi-module, parallel, cold-cache, offline
```

Đây là **mẫu thông tin cần điền theo artifact thật**, không phải thông tin về một extension có sẵn.

### 10.1. Ghim Maven distribution là một input khác

Maven Wrapper có thể chuẩn hóa Maven version dự án dùng. Nhưng nếu extension được nạp **trước khi Maven model chạy**, nó vẫn phụ thuộc Maven distribution và Java runtime của Wrapper/CI. Khi lên Maven 4, Maven 3-compatible plugins không bảo đảm mọi core extension internals vẫn phù hợp.

Giữ đủ evidence:

```text
mvn -version
java -version
Git commit của project
extension GAV + digest
active .mvn descriptors
runner image / Maven distribution
repository origin / CI run
```

Đừng lưu mỗi dòng “Maven 3” vì minor/patch version có thể ảnh hưởng APIs và Maven Resolver behavior.

### 10.2. Dependency drift của extension

Một extension có transitive dependencies riêng, ví dụ logger, JSON library hoặc transport client. Khi:

- Extension version không được ghim.
- Repository manager cho overwrite artifacts.
- Plugin/extension dependency graph thay đổi.
- Maven upgrade đổi Maven API/SLF4J/Resolver versions.

thì classloading hoặc behavior có thể thay đổi.

**Đừng chọn cách thêm cùng thư viện vào project `<dependencies>` để “vá” classloader của extension**. Project dependencies và core/plugin/extension realms khác nhau; phải sửa chính extension artifact/dependency declaration hoặc version compatibility theo docs.

### 10.3. Hỗ trợ IDE là một hợp đồng riêng

Một IDE có thể dùng embedded Maven, external Maven, import Maven model bằng tooling riêng hoặc delegate build sang Maven CLI. Một extension hoạt động ở CLI nhưng làm IDE import fail cần điều tra:

- IDE dùng Maven distribution/JDK nào.
- IDE có đọc đúng `.mvn/extensions.xml`/settings không.
- Có extension global ở user HOME không.
- Classloading/Resolver APIs trong embedded Maven có khác không.
- Có thể dùng external Maven compatible thay vì đổi extension nội bộ không.

Không sửa mã ứng dụng để chữa lỗi do Maven IDE importer chưa support extension.

## 11. Kiểm thử extension: unit tests chưa đủ

Một extension can thiệp Maven classloading/lifecycle, nên một unit test của Java class **không chứng minh nó chạy đúng trong Maven invocation thật**.

### 11.1. Bốn tầng test

| Tầng | Kiểm tra | Ví dụ |
| --- | --- | --- |
| Java unit | Logic độc lập, validation, parser/helper | JUnit assertions |
| Mojo/component unit | Component behavior với injected dependencies/mocks | Maven Plugin Testing Harness |
| Maven integration | Start Maven thật với fixture projects/goals | Maven Invoker Plugin |
| Environment/CI E2E | Correct JDK/Maven, mirror, secrets boundary, multi-module, deploy | Isolated runner + artifact digest |

Apache Maven Plugin Testing Harness dùng được để unit-test Mojos; **Maven Invoker Plugin** khởi chạy Maven projects thật để kiểm chứng integration. Với **core extension**, phải có test bao gồm **bootstrap chính extension**: mock logic không tái hiện đầy đủ startup failure.

### 11.2. Positive tests

- Project baseline có extension hoạt động đúng với Maven version được hỗ trợ.
- Goals chạy đúng thứ tự, output và test count đúng.
- `mvn help:effective-pom` hoạt động nếu extension yêu cầu model access.
- Multi-module build cho output đúng ở mỗi module.
- Offline build với cache đã prefetch và approved inputs.
- CI plugin/ext log không lộ secrets.
- Artifact SHA-256/reproducibility controls không bị extension làm thay đổi ngoài spec.

### 11.3. Negative tests

- Extension không tồn tại hoặc version bị đổi sai.
- JDK quá thấp so với classfile target.
- Maven major version nằm ngoài support.
- Incompatible transitive library/classloader realm.
- Repository trả artifact/checksum sai.
- Extension ném lỗi trong startup hoặc lifecycle hook.
- Chạy với `-T` khi extension giữ state không thread-safe.
- Extension được khai báo không đúng ở POM vs `.mvn`.
- CI thiếu network nhưng extension cố gọi remote ngoài approved endpoints.

Test âm tính phải chạy trong **fixture/runner tách biệt**, không sửa production repository hoặc user global Maven installation.

### 11.4. Không tự cho rằng extension thread-safe

Maven reactor có thể chạy song song:

```bash
mvn -T 2 -B verify
```

Một extension có mutable static/singleton state hoặc component scope không thích hợp có thể có race condition, nhất là khi nhiều modules dùng cùng extension.

**Không khẳng định Maven tự cô lập state của extension cho từng module**. Cần test concurrency, khóa shared state đúng cách hoặc giới hạn build song song theo policy khi extension chưa hỗ trợ.

### 11.5. Không dùng snapshot/test-only artifact cho release

Nếu extension version là `1.2.3-SNAPSHOT`, cùng tọa độ có thể trỏ binary khác theo metadata. Release pipeline quan trọng nên dùng exact approved release coordinates và xác minh bytes/origin. Ngoại lệ SNAPSHOT trong development phải có retention/attestation rõ.

## 12. Thiết kế quyết định: khi nào đủ lý do để viết extension?

Hãy hoàn thành bảng này trong design review:

| Câu hỏi | Câu trả lời cần có |
| --- | --- |
| Chức năng mong muốn là gì? | Một hành vi đo được, có tests |
| Plugin goal có làm được không? | Đã thử API/goals nào và tại sao thiếu |
| Vì sao cần đúng thời điểm nạp? | Phải trước model? trước goal? hay chỉ ở phase? |
| Extension point công khai có được Maven hỗ trợ không? | Docs/Maven version rõ |
| Ai là người sở hữu? | Maintainer + backup + lịch on-call |
| Phạm vi sử dụng? | Một module, reactor, toàn công ty hay installation |
| Tài sản có thể bị ảnh hưởng? | Source, POM, artifact, repo, CI secret |
| Cách kiểm thử? | Unit + Maven integration + matrix + negative |
| Cách rollback khi Maven không start? | Script/runner copy/descriptor revert |
| Cách chứng minh dependency trust? | Approved repo, exact version, checksum/signature |
| Chi phí vận hành? | Nâng cấp API, releases, CI latency, training |
| Success criteria? | Không regression, build time và output được đo |

Nếu không có câu trả lời cho **“vì sao plugin không đủ”**, đề xuất core extension **chưa được biện minh**.

### 12.1. Một quyết định nhanh theo nhu cầu

```text
Cần một tác vụ tại build phase?
  -> Plugin goal, không dùng extension nếu đủ.

Cần đóng gói mới hoặc lifecycle mapping được Maven support?
  -> Xem build extension/plugin extensions=true.

Cần thay core component trước model/goals?
  -> Chỉ cân nhắc core extension sau architecture/security review.

Cần áp chung mọi project nhưng chỉ là convention?
  -> Xem parent POM, settings, Maven Wrapper, CI policy trước.

Cần thêm thông tin vào report?
  -> Xem plugin/reporting/CI step trước.

Cần kiểm soát secrets/repository ACL?
  -> Dùng CI/IAM/repository manager; extension không thay authorization.
```

Không dùng extension để xây một cơ chế phân quyền giả ở layer Maven mà quyền ghi/thực thi thật vẫn nằm ở runner/registry.

## 13. Một scorecard đánh giá độ rủi ro

Dùng thang **định tính** để chuẩn bị họp review, không biến thành “chứng nhận an toàn” tự động:

| Yếu tố | Thấp | Trung bình | Cao |
| --- | --- | --- | --- |
| Load timing | Goal đơn lẻ | Build extension | Core startup |
| Blast radius | Một module | Reactor/project | Nhiều repos/global runner |
| API coupling | Public stable Plugin API | Một số component internals | Internal Maven Core/Resolver |
| Secrets exposure | No secrets | Read-only token | Publish/sign/admin tokens |
| Network scope | Offline/allowlist | Approved repositories | Egress mở mọi host |
| Provenance | Signed/verified immutable artifact | Pin version, chưa digest | Dynamic/mutable/unknown upstream |
| Test coverage | Matrix + negative E2E | Unit + happy path | Không có integration |
| Rollback | One-file revert đã tập | Manual runner rebuild | Không có rollback tested |
| Ownership | Rõ maintainer, SLA | Một người | Không có người chịu trách nhiệm |

**Một yếu tố “Cao” ở secrets hoặc global injection đủ để cần security review sâu**, không cộng điểm rồi tự cho phép nếu trung bình thấp. Ví dụ core extension với publisher token nên được phân tách secret boundaries trước, bất kể extension nhỏ tới đâu.

### 13.1. Ví dụ phân tích chi phí

Nhóm muốn thêm `CI build marker` cho mỗi build:

- **Plugin:** POM bind goal `validate`, output là file/console rõ, rollback một execution.
- **Build extension:** phải chứng minh vì sao cần class realm và extension lifecycle; nếu không thì thừa.
- **Core extension:** nạp sớm, rủi ro khởi động và security cao nhưng không tạo lợi ích tương ứng.

**Lựa chọn:** plugin-first, như lab mục 8.

Ngược lại, nếu thật sự cần cung cấp transport integration được Maven core dùng **trước cả plugin resolution**, plugin goal có thể **không đủ thời điểm**. Lúc này core extension có lý do, nhưng vẫn cần code/repository approvals, compatibility matrix và rollback trước rollout.

## 14. Thực hành thay đổi phiên bản và rolling upgrade

Một quy trình an toàn cho tổ chức dùng extension:

1. **Inventory:** liệt kê core/build/plugin extensions theo repo và Maven installation scope.
2. **Chốt owner:** ai có quyền approve version/digest.
3. **Baseline:** lưu Maven/JDK versions, artifact hashes, build duration, dependency graph và tests.
4. **Tách fixture:** chạy extension mới trong sample project, không dùng release token.
5. **Chạy integration matrix:** Maven/JDK/IDE/multi-module/cold-cache/parallel.
6. **So artifact behavior:** output/digests, logs và repository requests.
7. **Canary:** áp vào một repo/runner với khả năng revert.
8. **Progressive rollout:** tăng scope theo nhóm dự án, không bật đồng loạt.
9. **Observe:** startup failures, build time, changed outputs và unexpected egress.
10. **Rollback rehearsal:** loại extension khỏi cấu hình runner/project, xác minh Maven start lại.
11. **Release:** chỉ sau khi policies/QA PASS và có record.
12. **Retrospective:** cập nhật support matrix, docs và owner khi có issue.

### 14.1. Vì sao rollback của core extension cần tập trước?

Nếu Maven không start, lệnh:

```bash
mvn help:effective-pom
```

cũng có thể thất bại trước khi in POM. Bạn cần một cách sửa file `.mvn/extensions.xml` hoặc external runner config **không phụ thuộc Maven**.

Trong repository được phép sửa, tạo rollback commit/PR loại declaration lỗi. Trong CI, có thể dùng runner image trước đó; không chỉnh Maven installation trên production runner một cách thủ công và không kiểm soát.

### 14.2. “Disable bằng profile” có luôn hoạt động không?

**Không** đối với core extension `.mvn/extensions.xml`: nó được nạp sớm theo cơ chế startup, không phải một `<profile>` trong POM có thể tắt sau khi Maven đã start.

Build extension có thể chịu ảnh hưởng effective POM/profile theo cách cấu hình; cần test phiên bản Maven thực tế. Đừng dùng conditional profile như biện pháp duy nhất phòng core extension broken.

### 14.3. Dùng branch test, không thay global installation

Khi thử nâng extension, dùng:

```text
isolated CI runner
dedicated Maven distribution
temporary user home/settings
sample project checkout
approved artifact repository
```

thay vì thả JAR thử nghiệm vào `${maven.home}/lib/ext` dùng chung của developers hoặc release agents. Điều này giới hạn blast radius và tạo kết quả dễ tái hiện hơn.

## 15. Maven repository, cache và supply-chain risk

### 15.1. Core extension phải được resolve trước goals

Nếu `.mvn/extensions.xml` trỏ tới artifact không resolve được, Maven có thể fail trong bootstrap. Khi dùng:

```bash
mvn -o validate
```

Maven offline chỉ thành công nếu required extension artifacts và dependencies đã có trong local repository/điều kiện resolution phù hợp. **Offline không phải giải pháp tự tạo missing JAR**.

### 15.2. `-U` không tự sửa compatibility

```bash
mvn -U validate
```

có thể khiến Maven kiểm tra metadata/SNAPSHOT theo rules, nhưng **không biến extension compile cho Maven API A thành extension binary compatible với Maven API B**. Có thể cần version mới hoặc rebuild extension theo supported APIs.

### 15.3. Repository manager vẫn cần policy

Một approved Maven repository manager có thể quản lý upstreams, retention, immutability, credentials, audit. Tuy nhiên một mirror không tự chứng minh extension bytes đáng tin nếu policy cho overwrite hoặc artifact source không được review.

**Đặc biệt với core extension:** tách approved namespace/repository và thực thi review/digest verification **trước Maven startup** khi security policy yêu cầu.

### 15.4. Lưu fingerprint/digest ở đâu?

Một release approval record ngoài cache tùy ý:

```text
extension = org.example.internal:approved-core-extension:1.2.3
sha256 = <trusted digest of exact JAR bytes>
sourceCommit = <approved source commit>
maven = 3.9.x tested distribution
jdk = 17 tested runtime
signer = <verified identity if required>
ciRun = <trusted CI run ID>
approval = <record reference>
```

Các giá trị trong dấu góc là **schema minh họa**, phải được lấy từ artifact thật; không chép làm bằng chứng.

### 15.5. Classloader conflicts không xử lý bằng xóa cả `.m2`

Một `NoSuchMethodError` có thể do extension phụ thuộc thư viện/API khác Maven Core. Xóa cache local có thể dẫn tới tải lại **cùng version lỗi**, hoặc tạm che lỗi nếu metadata khác. Điều tra:

- Maven version/classloader realms.
- Exact extension GAV + dependencies và JAR digest.
- Stack trace/class origin.
- Reproducible minimal fixture.
- Các versions của Maven Core/Resolver/SLF4J/Sisu có liên quan.

Dùng separate local repository cho thử nghiệm thay vì xóa cache chung của người khác.

## 16. Debug lỗi extension không làm lan thêm rủi ro

### 16.1. `ClassNotFoundException` trong bootstrap

Có thể do:

- Extension artifact không chứa class mà descriptor yêu cầu.
- Transitive dependency không resolve.
- Maven version khác class visibility/API.
- Maven class realm isolation hoặc package export sai.
- JDK/classfile mismatch.

Phải xác định **class nào vắng mặt, code nào đang yêu cầu, nạp qua realm nào**. Không giải quyết bằng cách chép ngẫu nhiên nhiều JARs vào `${maven.home}/lib/ext`.

### 16.2. `NoSuchMethodError`, `ClassCastException`, `LinkageError`

Những lỗi linkage có thể do Maven APIs hoặc dependencies binary-incompatible. Ví dụ compile với một version API có method mà runtime Maven cũ không có; dù class name đúng, bytecode vẫn gọi method sai signature.

Checklist:

```text
stack trace first failing frame
extension GAV/version/digest
Maven distribution version
JDK runtime version
dependency/tree/release notes của extension
realm/classloading diagnostics khi có
compatibility matrix của maintainer
```

Không dùng `-DskipTests` để sửa một lỗi core extension bootstrap; tests chưa đến lượt chạy.

### 16.3. Component lookup/injection failures

Core/build extensions có thể thêm các components vào container/injection model. Nếu component names hoặc annotations/DI integration thay đổi giữa Maven versions, một extension có thể fail tạo component.

Hãy đối chiếu Maven extension authoring APIs và migration notes, đặc biệt các changes liên quan Plexus/Sisu/JSR-330 khi chuẩn bị Maven 4.

### 16.4. Maven chạy CLI nhưng IDE import fail

Kiểm tra:

```bash
mvn -version
```

và IDE toolchain/settings. Nếu IDE dùng embedded Maven/JDK khác, classloading có thể khác. Đừng thay project business code để chữa lỗi version/extension startup. Thử external Maven distribution mà plugin/extension support.

### 16.5. Maven `-X` có ích nhưng log nhạy cảm

```bash
mvn -B -X validate
```

có thể in bootstrap/classloader/repository diagnostics. Nhưng debug output có thể chứa internal paths, repository URLs và metadata môi trường. Phải **redact** trước khi chia sẻ. Không bật `-X` ở CI release rồi upload logs công khai khi có secrets.

### 16.6. Multi-module chỉ lỗi khi `-T`

Một extension chia sẻ mutable state qua singleton hoặc static fields có thể xuất hiện race khi reactor chạy song song:

```bash
mvn -B -T 2 verify
```

Dùng baseline single-thread và parallel-test để xác định. Không dùng tăng thread count làm “tối ưu miễn phí” khi extension chưa có concurrency contract.

## 17. Ghi nhận trade-offs về hiệu năng

Maven core extension có thể được nạp và chuẩn bị components ngay lúc startup; plugin execution thường chỉ có chi phí ở goals được gọi. Nhưng tốc độ phụ thuộc implementation, network, cache, số modules, plugin executions và toolchain.

**Cần đo thực nghiệm:**

- Maven startup time.
- Time to first lifecycle goal.
- Total `clean verify` wall-clock.
- Extension/plugin artifact resolution time.
- Number of remote repository calls.
- CPU/memory allocation và GC.
- Parallel reactor behavior.
- Frequency of cold-cache failures.
- Artifact digests/size nếu extension ảnh hưởng generated outputs.

### 17.1. Thử baseline vs candidate

Trong cùng runner sạch:

```text
A: Maven 3.9.x/JDK17 không extension
B: Maven 3.9.x/JDK17 có extension candidate
```

Giữ:

```text
same Git commit
same settings/repositories
same Maven/JDK
same goals/profiles
same warm/cold cache policy
same build/test targets
```

Thực hiện nhiều runs, so median/distribution, không dùng một số đo duy nhất. Nếu candidate làm build nhanh hơn nhưng thay hash artifacts trái spec, đó **không phải cải thiện được chấp nhận**.

### 17.2. Avoid extension latency hidden in startup

Một extension gọi network API trên startup có thể làm mọi `mvn validate` chậm/treo khi network fail. Nếu không thật cần ở early startup, chuyển tác vụ sang một plugin goal/CI step để có retries/timeouts/exit policy rõ.

Khi extension bắt buộc phải kết nối remote sớm, thiết kế:

- Bounded timeout.
- Fail policy tường minh, không nuốt lỗi.
- Approved endpoints/egress.
- Không log secrets.
- Cache/invalidation đúng và reproducible inputs.
- Observability + rollback path.

## 18. Hai cách “global” dễ bị nhầm

### 18.1. Parent POM áp plugin cho nhiều project

Một parent POM có thể quản lý:

```xml
<build>
    <pluginManagement>
        <plugins>
            <!-- versions/config dùng chung -->
        </plugins>
    </pluginManagement>
</build>
```

Điều này tạo **quy ước version/config**, không nhất thiết biến code thành core extension. Nó cũng cần security review vì parent POM được nhiều projects kế thừa, nhưng không nhất thiết can thiệp Maven bootstrap.

### 18.2. Global core extension áp trên nhiều builds

Một extension cài ở Maven installation/user scope (khi supported) có thể tác động **nhiều projects không hề khai báo nó** trong source repo. Đây là khác biệt lớn về reproducibility:

```text
Project source A + Maven env X -> build result A
Project source A + Maven env Y -> build result B
```

Cùng commit/POM nhưng Maven environment khác có thể làm build đổi. Bảo đảm baseline **build image, Maven distribution, user-home configuration và extension inventory** nhất quán giữa CI/developers nếu yêu cầu reproducibility.

## 19. Vòng đời vận hành một extension nội bộ

### 19.1. Trước khi viết

- Xác định use case không thể giải quyết bằng plugin/CI/settings.
- Kiểm tra Maven API docs, extension point và maintainer release notes.
- Xác định Maven/JDK support matrix.
- Security review quyền code sẽ có ở runner.
- Định nghĩa output/provenance và expected test behavior.

### 19.2. Trong quá trình phát triển

- Chỉ dựa vào public/stable APIs khi có thể.
- Ghim dependencies và kiểm tra license/vulnerability.
- Viết unit tests + Maven integration fixtures.
- Tránh global mutable state, đặc biệt multi-module và `-T`.
- Không đọc release secrets trong extension nếu không thực sự cần.
- Tránh unbounded network I/O ở Maven startup.
- Không thay Maven installation hay user HOME mặc định khi thử nghiệm.

### 19.3. Trước release

- Build extension artifact ở trusted CI.
- Ghi exact GAV/source commit/SHA-256.
- Chạy Maven/JDK/IDE matrix đã cam kết.
- Test failure/rollback cases.
- Review runtime permissions và repository write scope.
- Có release notes nêu binary compatibility và config migration.
- Canary trên một tập dự án nhỏ.

### 19.4. Sau release

- Theo dõi Maven release/major migration.
- Sửa vulnerabilities của transitive dependencies.
- Duy trì tài liệu bootstrap/triage.
- Có owner/backup và lịch hỗ trợ incidents.
- Loại extension không còn cần thiết hoặc không được duy trì.
- Định kỳ so installed/global extension inventory trên runners.

## 20. Runbook khi Maven đột nhiên không start

1. **Xác nhận phạm vi:** tất cả projects hay chỉ một repo? Developer, CI, IDE?
2. **Ghi Maven/JDK versions** và thời điểm bắt đầu lỗi.
3. **Dừng cấp secrets** cho job fail khi chưa rõ extension behavior.
4. **Kiểm `.mvn/extensions.xml`** từ Git diff trên một runner/checkout tin cậy, không chạy Maven để “đọc” nó.
5. **Kiểm Maven installation/user/global extension scope** theo phiên bản Maven thực.
6. **Xác định extension GAV/digest** và repository source.
7. **Sao chép minimal fixture** trong môi trường cô lập, tránh release token.
8. **Thử rollback có kiểm soát**: remove/revert declaration hoặc runner image trong bản sao, chạy Maven baseline.
9. **So stack traces/classloader/API versions** để tìm incompatibility.
10. **Khôi phục** bằng version đã duyệt hoặc loại bỏ extension.
11. **Rerun clean verify, kiểm output/test/sha256** trên artifact mới.
12. **Cập nhật regression integration test** và release support matrix.

Không sửa project code, xóa toàn bộ `.m2` hay nới quyền CI registry để “chữa” core extension chưa rõ lỗi.

## 21. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Maven fail trước phase `validate` | Core extension bootstrap/resolve lỗi | Xem `.mvn/extensions.xml`, startup stack |
| “Unresolveable extension” | GAV/version/repository/offline cache | Kiểm approved mirror, exact GAV |
| `ClassNotFoundException` ở extension | Class/dependency/realm export thiếu | Jar contents, classloader docs |
| `NoSuchMethodError` sau nâng Maven | API/runtime version mismatch | Matrix + Maven release notes |
| `ClassCastException` giữa Maven components | Class realm/API incompatibility | Stack first failing frame |
| Plexus/Sisu component không tạo | DI integration thay | Extension authoring API/migration |
| CLI PASS nhưng IDE import FAIL | Maven/JDK/embedded version khác | Align IDE external Maven |
| Chỉ CI fail | Runner image/settings/global extension khác | Compare extension inventories |
| Build dùng khác artifact dù cùng POM | Global core ext/repo override | Ghi env, resolved graph, SHA |
| `-o` fail trước compile | Extension chưa trong cache | Prefetch approved extension artifacts |
| `-U` không sửa lỗi | Binary incompatibility | Upgrade/rebuild extension đúng API |
| Maven 4 fail nhưng Maven 3 PASS | Changed APIs/DI/lifecycle | Migration matrix |
| Enforcer không phát hiện ext độc hại | Ext chạy trước Enforcer | Pre-Maven scanner/approval |
| Extension bắt đầu gọi host lạ | Network code/compromise | Block egress, audit, revoke creds |
| Token lộ trong logs | Extension/plugin log sai | Revoke/rotate, review runner boundaries |
| `-T 2` fail nhưng `-T 1` PASS | Shared state/race | Thread-safety tests |
| Startup chậm đột ngột | Ext tải remote/chờ service | Measure bootstrap/timeout |
| Artifact hash đổi sau thêm ext | Codegen/resolution/packaging changed | Compare JAR/dependency inputs |
| Plugin không chạy | Goal không bind/phase sai | Effective POM/lifecycle |
| Plugin bị nhầm build extension | `<extensions>true` không cần | Bỏ flag sau khi review |
| Build extension không hoạt động | Đặt core vs build descriptor sai | Check docs về loading path |
| Mất parent POM khi nạp ext | Repository/pom resolution khác | Check repo origin/settings |
| Extension “được pin” nhưng bytes khác | Remote overwrite/cache | Trusted digest + immutable repo |
| Không rollback được vì Maven không start | Dùng Maven goal để tự gỡ ext | Revert descriptor ngoài Maven |
| CI scan `pom.xml` nói không có extension | Global injection/profile/parent không scan | Full inventory + independent checks |

## 22. Q&A tự kiểm tra

**1.** Plugin và core extension khác nhau chủ yếu ở đâu?  
**Đáp án:** Plugin thực thi goals theo lifecycle/CLI; core extension nạp sớm và có thể tích hợp core behavior.

**2.** `<extensions>true</extensions>` trong plugin có chỉ là bật execution không?  
**Đáp án:** Không; nó khai báo plugin như một build extension.

**3.** `.mvn/extensions.xml` dùng cho loại nào?  
**Đáp án:** Core extensions trong cơ chế Maven tương ứng.

**4.** `<build><extensions>` khác `.mvn/extensions.xml` không?  
**Đáp án:** Có; build extensions từ project model khác core extension nạp sớm.

**5.** Classloader isolation của Maven có chặn đọc file/network bằng quyền OS không?  
**Đáp án:** Không.

**6.** Maven Enforcer ở `validate` có thể chặn core extension trước khi nó load không?  
**Đáp án:** Không bảo đảm; cần pre-Maven policy scanning.

**7.** Vì sao core extension cần security review chặt?  
**Đáp án:** Nó chạy sớm, có thể ảnh hưởng core/session và dùng quyền Maven process.

**8.** Một plugin goal bình thường có an toàn tuyệt đối không?  
**Đáp án:** Không; plugin cũng có quyền process và phải kiểm nguồn/permissions.

**9.** Khi nào chọn plugin thay extension?  
**Đáp án:** Khi tác vụ có thể chạy ở lifecycle phase/goal mà không cần can thiệp bootstrap.

**10.** Khi nào build extension có lý do?  
**Đáp án:** Khi cần project extension hook/packaging/lifecycle integration mà goal thường không đáp ứng.

**11.** Khi nào core extension có lý do?  
**Đáp án:** Khi cần core integration rất sớm và có design/security/compatibility evidence.

**12.** Maven 4 yêu cầu JDK runtime tối thiểu nào?  
**Đáp án:** JDK 17 theo migration guide hiện hành.

**13.** Plugin compile Java 17 có tự bảo đảm tương thích mọi Maven version không?  
**Đáp án:** Không; Maven APIs/dependencies và runtime behavior cũng quan trọng.

**14.** `NoSuchMethodError` sau Maven upgrade thường gợi ý gì?  
**Đáp án:** Binary/API incompatibility giữa compile/runtime versions.

**15.** Vì sao IDE có thể lỗi dù Maven CLI PASS?  
**Đáp án:** IDE dùng Maven/JDK/classloading/settings khác.

**16.** Maven 3.9.x có thể dùng user `.m2/extensions.xml` theo tính năng Maven 3.10 không?  
**Đáp án:** Không nên giả định; phải xét Maven version được cài.

**17.** Một core extension có thể thay hành vi của nhiều projects không?  
**Đáp án:** Có nếu được cài ở phạm vi user/installation hoặc nhiều projects cùng bật.

**18.** `pluginManagement` có tự chạy plugin goals không?  
**Đáp án:** Không; nó quản lý versions/config defaults.

**19.** Artifact tọa độ GAV cố định có đủ bảo đảm bytes đáng tin không?  
**Đáp án:** Không nếu repository có overwrite; cần provenance/digest/immutability.

**20.** `-o` có đảm bảo extension hoạt động không?  
**Đáp án:** Không, cần extension và dependencies sẵn trong local repo.

**21.** `-U` có tự sửa `ClassCastException` do API đổi không?  
**Đáp án:** Không; phải chỉnh version/compatibility.

**22.** Vì sao cần test `-T`?  
**Đáp án:** Để phát hiện shared-state/thread-safety issues.

**23.** Maven Invoker Plugin hữu ích thế nào?  
**Đáp án:** Chạy Maven projects thật làm integration fixtures.

**24.** Plugin Testing Harness unit test đủ cho core extension không?  
**Đáp án:** Không; cần bootstrap/integration/E2E tests.

**25.** Tại sao phải có cách rollback không chạy Maven?  
**Đáp án:** Vì core extension có thể làm Maven không start.

**26.** Một scanner Java đọc `.mvn/extensions.xml` có chứng minh mã extension an toàn không?  
**Đáp án:** Không; chỉ phát hiện một phần declarations, vẫn cần trust review.

**27.** Tại sao không để PR build có publisher/signing secrets?  
**Đáp án:** Plugins/extensions/code từ PR chạy cùng process/job có thể truy cập secrets.

**28.** Biện pháp thay extension thường xuyên nhất?  
**Đáp án:** Built-in Maven/CI, existing plugins, hoặc custom Mojo dùng public APIs.

**29.** Khi không có owner hỗ trợ extension thì nên làm gì?  
**Đáp án:** Không nâng phạm vi sử dụng; tìm replacement/ownership trước rollout.

**30.** Kết luận đánh giá extension là gì?  
**Đáp án:** Có cần nạp sớm hay không, ai chịu trách nhiệm, hỗ trợ Maven/JDK nào, quyền chạy tới đâu, test/rollback/digest đã được chứng minh chưa.

## 23. Checklist quyết định và vận hành

- [ ] Mô tả hành vi cần đạt và chứng cứ plugin/CI không đủ.
- [ ] Chọn đúng plugin, build extension hay core extension.
- [ ] Không thêm `<extensions>true</extensions>` chỉ để “bật” plugin.
- [ ] `.mvn/extensions.xml` nằm trong code review có owner phù hợp.
- [ ] Extension GAV và dependencies được pin/approved.
- [ ] Maven version/JDK runtime support matrix được công bố.
- [ ] Compatibility Maven 4 được test riêng khi dự định migration.
- [ ] Không dựa internal Maven APIs nếu có public extension point.
- [ ] Có integration fixtures chạy Maven process thật.
- [ ] Kiểm cả multi-module và parallel build nếu được hỗ trợ.
- [ ] Unit tests cho logic độc lập và expected failure cases.
- [ ] Chính sách repository nguồn tải, immutability và SHA-256 rõ.
- [ ] Không có signer/publisher token trong untrusted build.
- [ ] Runner network egress và artifact read rights giới hạn.
- [ ] Scanner pre-Maven xử lý extension changes trên trusted CI.
- [ ] Có inventory project/user/installation-level extensions.
- [ ] IDE và CI dùng Maven distribution phù hợp.
- [ ] `MAVEN_OPTS`, `jvm.config`, `maven.ext.class.path` được xem xét.
- [ ] Có logs redaction và audit extension-origin changes.
- [ ] Không quảng bá “classloader = sandbox”.
- [ ] Có timeout và failure policy khi extension gọi remote service.
- [ ] Đo performance baseline vs candidate cùng điều kiện.
- [ ] Có canary/progressive rollout thay vì bật toàn công ty.
- [ ] Có rollback rehearsal hoạt động **không cần Maven**.
- [ ] Có CI evidence commit/Maven/JDK/extension digest.
- [ ] Sau thay extension, QA output và test counts thực.
- [ ] Không thay Maven installation/global HOME thủ công trên shared runner.
- [ ] Extension không còn cần thiết được loại bỏ theo quy trình.
- [ ] Owner/backup/incident response SLA đủ rõ.

## 24. Nguồn tham khảo

1. [Apache Maven — Using Extensions](https://maven.apache.org/guides/mini/guide-using-extensions.html) — core/build extension và cách khai báo.
2. [Apache Maven — Configuring Maven](https://maven.apache.org/configure.html) — `.mvn/extensions.xml`, `maven.ext.class.path` và user/installation scope theo Maven version.
3. [Apache Maven — Maven Classloading](https://maven.apache.org/reference/maven-classloading.html) — Core, Core Extensions, Build Extensions và Plugin class realms.
4. [Apache Maven — Guide to Maven Classloading](https://maven.apache.org/guides/mini/guide-maven-classloading.html) — giới hạn export/visibility.
5. [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4) — Java 17, upgrade path và tương thích.
6. [Apache Maven — What's New in Maven 4](https://maven.apache.org/whatsnewinmaven4.html) — Maven API/plugin validation và các thay đổi đáng xét.
7. [Apache Maven — Plugins Compatibility Plan](https://maven.apache.org/developers/compatibility-plan.html) — minimum Maven/JDK requirements của plugin versions.
8. [Apache Maven AntRun Plugin 3.2.0 — Usage](https://maven.apache.org/plugins/maven-antrun-plugin/usage.html) — goal `antrun:run` và `<target>` Ant tasks.
9. [Apache Maven Enforcer Plugin 3.6.3 — `enforcer:enforce`](https://maven.apache.org/enforcer/maven-enforcer-plugin/enforce-mojo.html) — lifecycle `validate`.
10. [Apache Maven Enforcer — Require Maven Version](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html) — version range toolchain policies.
11. [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html) — goals, plugin version pinning, execution.
12. [Apache Maven Invoker Plugin](https://maven.apache.org/plugins/maven-invoker-plugin/) — Maven integration test projects.
13. [Apache Maven Plugin Testing Mechanism](https://maven.apache.org/plugin-testing/maven-plugin-testing-harness/faq.html) — Mojo unit tests vs Maven Invoker integration.
14. [Apache Maven Plugin Tools — Java Annotations](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/using-annotations.html) — custom Mojo authoring APIs.
15. [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html) — output reproducibility/binary evidence.
16. [Apache Maven — Settings Reference](https://maven.apache.org/settings.html) — repositories/mirrors/credentials.
17. [Java SE 17 — Java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — Java 17 source-file execution.
18. [Java SE 17 — XMLConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/XMLConstants.html) — external XML resource access restrictions.

**Kết luận:** Maven extensions có thể mở rộng sức mạnh của build nhưng cũng tăng **coupling, chi phí bảo trì, ma trận tương thích và phạm vi tin cậy**. **Ưu tiên plugin goal khi chức năng chỉ cần chạy ở phase cụ thể**; chỉ chọn build/core extension khi có lý do kỹ thuật về extension point hoặc thời điểm nạp. Classloader không phải security sandbox. Trước khi rollout, phải **pin và xác minh artifact, test trên Maven/JDK matrix, giữ secrets ngoài untrusted builds, có scanner trước Maven và có rollback không phụ thuộc Maven startup**.

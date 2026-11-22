# Quan sát đồ thị dependency bằng \`dependencies\` và \`dependencyInsight\` trong Gradle

## 1. Mục tiêu của bài học

Khi viết `dependencies { implementation 'group:module:version' }`, bạn mới mô tả **yêu cầu** của build. Để tạo classpath thực sự, Gradle còn phải tìm metadata ở repository, đi theo các **transitive dependencies** (dependency bắc cầu), áp dụng constraints/rules, chọn component và variant phù hợp, rồi xác định artifact sử dụng.

Vì vậy, file `build.gradle` **không tự nói hết** những gì sẽ xuất hiện trên `compileClasspath` hoặc `runtimeClasspath`. Một thư viện có thể:

- Có mặt dù bạn không khai báo trực tiếp, vì nó là dependency bắc cầu.
- Có **version được chọn khác version được yêu cầu**, do conflict resolution, constraint, platform (BOM), rule hoặc lựa chọn khác.
- Xuất hiện ở runtime nhưng không ở compile, hoặc ở test nhưng không ở app runtime.
- Xuất hiện ở nhiều nhánh của đồ thị nhưng Gradle chỉ mở rộng nhánh đó một lần trong báo cáo.
- Không resolve được vì thiếu artifact, repository, metadata hoặc do attributes/variants không tương thích.

Hai công cụ CLI tích hợp của Gradle giúp quan sát kết quả:

1. **`dependencies`**: nhìn **toàn bộ cây dependency của một configuration** (hoặc nhiều configuration trong project). Dùng để trả lời: *“Ở classpath này có những module nào, đi vào qua nhánh nào, và version nào đã được chọn?”*
2. **`dependencyInsight`**: nhìn **một module hoặc nhóm module khớp tên trong một configuration**, theo hướng giải thích *ai cần nó* và *vì sao Gradle chọn version/variant đó*. Dùng để trả lời: *“Tại sao thư viện này là 1.17.1 thay vì 1.11? Nó đến từ đâu?”*

Bài học thuộc mục **Phân giải dependency** của Gradle, minh họa bằng **Groovy DSL** và một ứng dụng **Java 17**. Dùng Gradle Wrapper của dự án (`./gradlew` hoặc `.\gradlew.bat`), không dựa vào version Gradle cài toàn cục.

## 2. Trước tiên: configuration là “góc nhìn” lên đồ thị

Trong Java ecosystem, plugin `java`, `java-library` hoặc `application` bổ sung các configuration khác nhau. Không có một đồ thị duy nhất cho “mọi dependency của project”:

| Configuration | Công dụng điển hình | Có phù hợp để xem đồ thị resolve? |
| --- | --- | --- |
| `implementation` | Nơi **khai báo** thư viện cho mã chính | Thường là dependency bucket, không dùng để resolve trực tiếp |
| `api` | Nơi khai báo dependency lộ qua API library | Do `java-library` tạo; thường không phải classpath để resolve trực tiếp |
| `compileOnly` | Dependency chỉ cần lúc compile | Bucket khai báo, không dùng thay `compileClasspath` |
| `runtimeOnly` | Dependency chỉ cần lúc run | Bucket khai báo, không dùng thay `runtimeClasspath` |
| `compileClasspath` | Các file/variants cần cho `compileJava` | **Có**, resolvable trong Java plugin |
| `runtimeClasspath` | Các file/variants cần để chạy ứng dụng | **Có**, resolvable trong Java plugin |
| `testCompileClasspath` | Các file cần compile test | **Có**, khi plugin tạo test source set |
| `testRuntimeClasspath` | Các file cần chạy test | **Có**, khi plugin tạo test source set |
| `annotationProcessor` | Công cụ xử lý annotation | Thường resolvable cho Java compilation |
| `buildscript classpath` | Thư viện cho chính build script | **Khác project dependencies**; xem bằng `buildEnvironment` |

Với các Gradle version hiện đại, configuration có các vai trò tách bạch: **declarable** (khai báo), **resolvable** (tính graph/variants/artifacts) và **consumable** (cung cấp variants cho consumer). Cùng một library có thể xuất hiện trong hai report nhưng với **variant khác nhau** do attributes mà consumer yêu cầu.

Một ví dụ đơn giản:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'commons-codec:commons-codec:1.17.1'
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.16'
}
~~~

`commons-codec` được khai báo `implementation`, có thể xuất hiện trong cả compile/runtime classpath. `slf4j-simple` được khai báo `runtimeOnly`, không có lý do mặc định để xuất hiện trên main `compileClasspath`. Do đó:

~~~bash
./gradlew -q dependencies --configuration compileClasspath
./gradlew -q dependencies --configuration runtimeClasspath
~~~

có thể tạo ra hai cây khác nhau, hoàn toàn đúng thiết kế.

**Lưu ý:** đừng kết luận “không có dependency” chỉ vì kiểm tra nhầm configuration. Trước hết xác định project, task và classpath đang gặp sự cố.

## 3. Lệnh `dependencies`: quan sát bức tranh rộng

Cú pháp nền tảng:

~~~bash
./gradlew dependencies
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencies --configuration testRuntimeClasspath
~~~

- `./gradlew dependencies`: liệt kê report cho **các configuration thuộc project đang chọn**, không tự quét tất cả module trong multi-project build.
- `--configuration runtimeClasspath`: chỉ tập trung vào **một** configuration. Đây là cách dễ phân tích và đưa vào bug report hơn việc dán tất cả configuration.
- `-q`: chế độ quiet, giúp report ít log Gradle khác hơn; nội dung graph vẫn tùy dependencies và phiên bản Gradle.

Nếu project có tên `:app`:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

Đây là lệnh report cho **module `:app`**, không phải root project. Khi có nhiều module cùng khai báo một thư viện, phải ghi rõ project path để không lẫn graph của module khác.

Nếu chưa biết configuration nào tồn tại, với Gradle hiện đại:

~~~bash
./gradlew -q resolvableConfigurations
./gradlew :app:resolvableConfigurations
~~~

`resolvableConfigurations` giúp thấy những configuration có thể resolve cùng attributes/liên hệ của chúng. Không cần (và thường không nên) cố resolve bucket `implementation` trực tiếp; chọn `compileClasspath` hoặc `runtimeClasspath` phù hợp.

### 3.1. Cách đọc một cây dependency

Ví dụ sau **chỉ để minh họa ký hiệu**, tên và version ở report thực tế tùy project:

~~~text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- com.acme:feature-a:1.0
|    \--- com.acme:common:1.2 -> 1.4
+--- com.acme:feature-b:2.0
|    \--- com.acme:common:1.4 (*)
\--- com.acme:common:1.4
~~~

Giải thích:

- Dòng ngay dưới `runtimeClasspath` là những **dependency trực tiếp theo góc nhìn configuration** hoặc những nhánh được configuration kế thừa.
- Dòng thụt vào là dependency bắc cầu của một thành phần ở mức trên.
- `com.acme:common:1.2 -> 1.4`: một nhánh yêu cầu `1.2`, nhưng **component được chọn là 1.4**.
- Dấu `(*)`: nhánh transitive tương tự đã được Gradle mở rộng ở nơi khác trong cùng report; đây **không phải** dấu báo lỗi hoặc thư viện không được tải.
- Một module có thể xuất hiện trên nhiều nhánh. Cây in ra các **đường dẫn yêu cầu**, còn quá trình resolution thường chọn một phiên bản component phù hợp cho từng module trong configuration.

Đừng suy rằng mỗi dòng trong report tương đương **một bản JAR khác nhau được load vào JVM**. Có thể có constraint, platform, project component, variant không phải JAR, và nhiều đường dẫn trùng nhau được rút gọn.

### 3.2. Các annotation quan trọng trong report

| Ký hiệu | Ý nghĩa | Cách xử lý khi thấy |
| --- | --- | --- |
| `+---`, `\---` | Cấp nhánh trong cây dependency | Theo độ thụt lề để tìm “ai kéo vào” |
| `|` | Nhánh vẫn tiếp diễn ở cấp trên | Giúp đọc cấu trúc cây |
| `1.11 -> 1.17.1` | Requested version khác selected version | Dùng `dependencyInsight` để biết **vì sao** được chọn |
| `(*)` | Transitive subtree đã được mở rộng ở chỗ khác | Không phải missing dependency; tìm lần mở rộng đầu |
| `(c)` | **Dependency constraint**, không phải một dependency thông thường | Tìm component tương ứng trong cây, xem `dependencyInsight` |
| `(n)` | Một dependency/configuration **không thể resolve** theo ngữ cảnh hiển thị | Xác định configuration/metadata; không coi là JAR đã có |
| `FAILED` | Một node resolution bị lỗi (khi report hiển thị lỗi) | Xem thông báo Gradle và repository/coordinates/attributes |
| `No dependencies` | Configuration đó không khai báo/không có graph hiển thị | Kiểm tra đã chọn đúng project và configuration chưa |

`(c)` thường xuất hiện do platform/BOM hoặc explicit dependency constraints. Nó không có nghĩa Gradle đã tải một JAR constraint. `(*)` cũng không nói Gradle bỏ qua dependency: nó chỉ rút gọn bản in để tránh lặp cây.

Nếu thấy `(n)` ở một bucket cấu hình không resolvable, không nên suy ngay có lỗi repository; đó có thể là trạng thái thiết kế của configuration.

### 3.3. Cây cho biết “cái gì” nhưng chưa phải toàn bộ “vì sao”

Ví dụ:

~~~text
+--- commons-codec:commons-codec:1.17.1
\--- org.apache.httpcomponents:httpclient:4.5.14
     +--- commons-codec:commons-codec:1.11 -> 1.17.1
     +--- commons-logging:commons-logging:1.2
     \--- org.apache.httpcomponents:httpcore:4.4.16
~~~

Đây là **trích đoạn minh họa của runtimeClasspath** cho demo mục 6, không phải cam kết mọi phiên bản Gradle sẽ in giống hệt thứ tự/nhánh. Bạn đã biết `httpclient` yêu cầu Commons Codec `1.11` và Gradle chọn `1.17.1` trong graph, nhưng chưa biết có **constraint, force, selected-by-rule hay lý do conflict mặc định**. Đó là lúc chuyển từ `dependencies` sang `dependencyInsight`.

## 4. Lệnh `dependencyInsight`: tập trung vào một module

Cú pháp khuyến nghị:

~~~bash
./gradlew dependencyInsight \
  --dependency commons-codec:commons-codec \
  --configuration runtimeClasspath
~~~

Có thể viết trên một dòng để dùng được ở mọi shell:

~~~bash
./gradlew dependencyInsight --dependency commons-codec:commons-codec --configuration runtimeClasspath
~~~

`--dependency` chọn module cần xem theo `group:name` hoặc **một phần tên**. Nếu dùng phần tên quá rộng như `commons` và nhiều module cùng khớp, report có thể chứa nhiều kết quả; muốn điều tra một artifact cụ thể, ưu tiên `group:name`.

`--configuration` chỉ configuration mà bạn muốn giải thích. **Thông thường nó là tham số bắt buộc**, nhưng với một số project dùng Java plugin, Gradle có default `compileClasspath` cho `dependencyInsight`. Để tránh nhầm compile/runtime và để câu lệnh tái lập tốt trong CI, vẫn nên **luôn ghi tường minh `--configuration`**.

Ví dụ cho project `:app`:

~~~bash
./gradlew :app:dependencyInsight --dependency commons-codec:commons-codec --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency commons-codec --configuration testRuntimeClasspath
~~~

Report giúp trả lời hai câu hỏi liên kết:

1. **Version/variant được chọn là gì?** Thông tin component/variant/attributes và `Selection reasons`.
2. **Đường đi đến module đó là gì?** Các dependency path từ configuration consumer qua những module yêu cầu nó, thường hiển thị theo hướng ngược với cây `dependencies`.

### 4.1. Hướng nhìn khác nhau của hai công cụ

`dependencies` hiển thị đại ý **từ configuration đi tới dependency**:

~~~text
runtimeClasspath
  \--- httpclient:4.5.14
        \--- commons-codec:1.11 -> 1.17.1
~~~

`dependencyInsight` tập trung vào **Commons Codec** và cho biết các requester:

~~~text
commons-codec:commons-codec:1.17.1
  Selection reasons:
    - By conflict resolution: between versions 1.17.1 and 1.11

commons-codec:commons-codec:1.11 -> 1.17.1
\--- org.apache.httpcomponents:httpclient:4.5.14
     \--- runtimeClasspath

commons-codec:commons-codec:1.17.1
\--- runtimeClasspath
~~~

Đoạn trên là **sơ đồ output rút gọn minh họa**, không phải stdout toàn bộ từng phiên bản Gradle. Report thật có thể bao gồm bảng variant attributes, nhiều con đường và ký hiệu rút gọn. Điều quan trọng là từ `dependencyInsight` bạn thấy **1.17.1 được chọn do conflict giữa yêu cầu trực tiếp và transitive**.

### 4.2. Hai tùy chọn nâng cao

~~~bash
# Khi report quá nhiều nhánh:
./gradlew dependencyInsight --dependency commons-codec --configuration runtimeClasspath --single-path

# Khi cần chẩn đoán thuộc tính/variant được chọn:
./gradlew dependencyInsight --dependency commons-codec --configuration runtimeClasspath --all-variants
~~~

- `--single-path`: chỉ hiển thị **một đường dẫn** tới dependency. Hữu ích để đọc nhanh, **nhưng có thể ẩn các requester khác**. Khi tìm tất cả nơi kéo thư viện vào, không dùng cờ này hoặc chạy lại không có nó.
- `--all-variants`: yêu cầu hiển thị **mọi variant có thể được báo cáo**, không chỉ variant được chọn, phù hợp khi tìm lý do khác biệt giữa `java-api` và `java-runtime` hoặc attributes. Với một artifact chỉ có metadata Maven POM đơn giản, report variant có thể không phong phú bằng module có Gradle Module Metadata.
- Hai cờ trên **không tự thay đổi version dependency được resolve**; chúng điều chỉnh cách quan sát report.

Khi không tìm thấy module khớp trong configuration, `dependencyInsight` có thể thông báo không có dependency phù hợp. Điều đó **không chứng minh module vắng mặt ở mọi configuration**: hãy thử `compileClasspath`/`testRuntimeClasspath`/module project đúng hoặc xem graph trước.

## 5. “Selection reasons” trong dependencyInsight đọc ra sao?

Điểm mạnh của `dependencyInsight` không chỉ là in version mà còn cung cấp **lý do chọn**. Tên cụ thể của các dòng có thể thay đổi giữa các phiên bản Gradle, nhưng những nhóm lý do quan trọng gồm:

| Lý do | Diễn giải | Cần điều tra gì tiếp |
| --- | --- | --- |
| `By conflict resolution` | Có nhiều yêu cầu version cho cùng module; Gradle giải quyết xung đột | Những requester nào đòi version khác? Có constraint không? |
| `By constraint` | Một dependency constraint tham gia vào kết quả | Xem `constraints { }`, platform/BOM và nơi constraint đến từ |
| `Forced` | Có quy tắc force hoặc enforced platform tác động chọn version | Tìm `resolutionStrategy.force`/`enforcedPlatform` trong build logic |
| `Selected by rule` | Resolution rule đã điều chỉnh quyết định mặc định | Tìm rules, plugin quản lý dependency, component metadata logic |
| `Was requested` | Module được yêu cầu; có thể kèm lý do do `because` khai báo | Đọc lời giải thích trong dependency declaration |
| `By ancestor` | Một version constraint nghiêm ngặt (`strictly`) từ ancestor tác động selection | Kiểm tra rich version và đường dẫn ancestor |
| `Rejection ...` | Có version bị loại theo rule/attributes/rich version | Kiểm tra `reject`, attributes, variant compatibility |
| Không có reason bổ sung | Module chỉ được yêu cầu trực tiếp/bắc cầu, không có lý do đặc biệt được báo | Đừng tự tạo suy đoán về conflict hoặc force |

**Không mặc định “Gradle luôn chọn bản mới nhất”**. Với hai yêu cầu version đơn giản, mặc định Gradle thường chọn version cao hơn theo conflict resolution. Nhưng `strictly`, platform, forced module, rich versions, substitution, rule, capabilities, attributes hoặc phiên bản không tương thích có thể khiến kết quả khác. Đọc `Selection reasons` và dependency paths để biết trường hợp cụ thể.

### 5.1. Dependency constraint là gì?

Ví dụ một Java project có thể khai báo:

~~~groovy
dependencies {
    implementation 'commons-codec:commons-codec:1.17.1'

    constraints {
        implementation('commons-codec:commons-codec:1.17.1') {
            because 'Phiên bản được kiểm thử cho ứng dụng'
        }
    }
}
~~~

Đây là trích đoạn minh họa việc ghi **lý do của constraint**; không cần tạo cả direct dependency và constraint trùng nhau trong mọi build. Nếu constraint xuất hiện trong cây với `(c)`, hãy đọc nó như **ràng buộc chọn version**, chứ không phải một file JAR thứ hai.

Một constraint **không tạo ra dependency mới từ hư không** nếu chưa có dependency yêu cầu component tương ứng; nó tham gia lựa chọn khi graph có module đó. Với BOM/platform, constraints có thể xuất hiện qua nhiều thành phần.

### 5.2. `because` làm report dễ hiểu

~~~groovy
dependencies {
    implementation('commons-codec:commons-codec:1.17.1') {
        because 'Đồng bộ API cần dùng với bộ kiểm thử của nhóm'
    }
}
~~~

Gradle có thể hiển thị reason theo nhóm `Was requested` kèm nội dung `because`. Việc ghi lý do rất hữu ích khi người bảo trì thấy hai version trong graph và muốn biết tại sao một dependency được khai báo tường minh.

### 5.3. `strictly` và force cần thận trọng

Ví dụ minh họa rich version constraint:

~~~groovy
dependencies {
    implementation('commons-codec:commons-codec') {
        version {
            strictly '1.17.1'
        }
    }
}
~~~

`strictly` thể hiện ý định khóa yêu cầu version mạnh hơn `prefer`; nếu các constraint không thể thỏa mãn, resolution có thể thất bại thay vì “chọn bừa một bản”. Không nên áp dụng `strictly` hoặc `force` làm mẹo chữa mọi warning: đôi khi vấn đề thật là plugin/library chưa tương thích phiên bản được ép.

Một **report** giúp tìm nguyên nhân, nó không phải nơi sửa kết quả; thay đổi cần thực hiện trong `dependencies`, platform/constraint hoặc resolution rules có kiểm soát, sau đó chạy report lần nữa.

## 6. Demo Java 17: một dependency trực tiếp và một dependency bắc cầu

Demo sử dụng một dependency transitive có đường dẫn xác định:

- `org.apache.httpcomponents:httpclient:4.5.14` yêu cầu **`commons-codec:commons-codec:1.11`** qua Maven metadata.
- Build đồng thời yêu cầu trực tiếp **`commons-codec:commons-codec:1.17.1`**.
- Với cấu hình mặc định đơn giản, Gradle sẽ chọn **1.17.1** cho module Commons Codec trong `runtimeClasspath` của demo; `dependencyInsight` cho thấy đường đi/lý do chọn.

`httpclient` 4.5.14 là dòng thư viện lâu năm, dùng ở đây **để minh họa metadata transitive version**, không phải lời khuyên chọn HTTP client mới cho ứng dụng sản xuất. Với hệ thống thật, chọn thư viện và phiên bản theo hỗ trợ, tương thích và kiểm tra bảo mật của tổ chức.

### 6.1. Cấu trúc dự án

~~~text
dependency-graph-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    └── main/
        └── java/
            └── demo/
                └── App.java
~~~

Đây là cấu trúc **dự án đã có Gradle Wrapper**. Bốn file Wrapper không phải file mẫu rỗng: chúng phải được tạo bởi Gradle Wrapper đúng quy trình, với Gradle version tương thích JDK.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'dependency-graph-demo'
~~~

### 6.3. `build.gradle`

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    // Dependency trực tiếp, dùng cho Java source và runtime.
    implementation 'commons-codec:commons-codec:1.17.1'

    // Module này kéo Commons Codec 1.11 vào qua metadata bắc cầu.
    implementation 'org.apache.httpcomponents:httpclient:4.5.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}
~~~

**Điều kiện thực thi:** project có Java 17 toolchain (được Gradle phát hiện hoặc cấu hình resolver để cung cấp), Gradle Wrapper tương thích và Maven Central có thể truy cập. `application` là core plugin của Gradle, không cần version riêng. Cả hai dependency là Maven coordinates cho **application project**, không phải plugin hoặc build script dependency.

### 6.4. `src/main/java/demo/App.java`

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import org.apache.commons.codec.binary.Hex;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String source = args.length == 0 ? "Gradle" : args[0];
        byte[] data = source.getBytes(StandardCharsets.UTF_8);
        System.out.println("hex=" + Hex.encodeHexString(data));
    }
}
~~~

Đây là **Java 17 program hoàn chỉnh**. Public class `App` nằm trong `App.java` và thư mục package `demo`. `Hex` đến từ `commons-codec`. Nếu gọi `javac` từ terminal mà không cung cấp Commons Codec JAR trên classpath, compiler sẽ báo thiếu `org.apache.commons.codec.binary.Hex`; Gradle cung cấp JAR từ `implementation`.

Nếu đã tải Commons Codec JAR về máy và muốn tự chạy ngoài Gradle, lệnh tương đương về ý tưởng:

~~~bash
# Ví dụ: CODEC_JAR trỏ tới file commons-codec-1.17.1.jar đã tải.
javac -cp "$CODEC_JAR" -d out src/main/java/demo/App.java
java -cp "out:$CODEC_JAR" demo.App
~~~

Lệnh Unix trên cần biến môi trường `CODEC_JAR` hợp lệ. Windows dùng dấu phân tách classpath `;` thay vì `:`. Vì Gradle tự quản lý dependency, cách chạy qua Wrapper dưới đây đơn giản hơn và tránh thao tác classpath thủ công.

### 6.5. Chạy ứng dụng

~~~bash
./gradlew -q run
./gradlew -q run --args='Hi'
~~~

Output do `demo.App` in lần lượt:

~~~text
hex=477261646c65
~~~

và:

~~~text
hex=4869
~~~

`Gradle` có byte UTF-8 lần lượt là `47 72 61 64 6c 65` (hex), còn `Hi` là `48 69`. Đây là output cố định của chương trình cho hai input ASCII nói trên, **không phải toàn bộ log của Gradle**. Task `run` do `application` plugin tạo, `--args` là application arguments cho `main(String[] args)`.

PowerShell Windows:

~~~powershell
.\gradlew.bat -q run
.\gradlew.bat -q run --args="Hi"
~~~

Nếu project không có JDK 17 toolchain hoặc mạng bị chặn khi cache chưa chứa dependencies, Gradle có thể fail trước khi chạy Java; đó là vấn đề môi trường/dependency resolution, không phải sự khác biệt giữa hai dòng stdout.

### 6.6. In cây runtime và đối chiếu

~~~bash
./gradlew -q dependencies --configuration runtimeClasspath
~~~

Trong report thực tế bạn sẽ tìm thấy (thứ tự dòng/nhánh có thể khác):

~~~text
commons-codec:commons-codec:1.17.1
org.apache.httpcomponents:httpclient:4.5.14
  \--- commons-codec:commons-codec:1.11 -> 1.17.1
~~~

Đây là **các dòng tiêu biểu**, không phải bản chép nguyên toàn bộ cây. Những dependency khác của HttpClient như `httpcore`, `commons-logging` cũng có thể có mặt. Mục tiêu là nhìn thấy:

1. Yêu cầu Commons Codec **1.17.1** trực tiếp.
2. Yêu cầu Commons Codec **1.11** bắc cầu qua HttpClient.
3. **Selected version 1.17.1** trong configuration đang xét.

Không mặc định `compileClasspath` sẽ in cây **giống hệt** `runtimeClasspath`: Gradle chọn variants/attributes theo mục tiêu compile hoặc runtime. Với những artifact chỉ có Maven POM và không dùng variants phức tạp, graph cơ bản có thể giống; vẫn nên kiểm tra configuration đúng với lỗi đang gặp.

### 6.7. Dùng `dependencyInsight` tìm lý do

~~~bash
./gradlew -q dependencyInsight --dependency commons-codec:commons-codec --configuration runtimeClasspath
~~~

Điểm cần tìm trong report:

- Component được chọn: `commons-codec:commons-codec:1.17.1`.
- `Selection reasons` có lý do liên quan **conflict resolution** giữa các yêu cầu version, nếu không có rule/constraint bổ sung.
- Hai đường dẫn yêu cầu: một từ `runtimeClasspath` do khai báo trực tiếp, một qua `org.apache.httpcomponents:httpclient:4.5.14` với version `1.11 -> 1.17.1`.
- Bảng variant attributes (nếu Gradle hiển thị) giúp hiểu variant được chọn phù hợp `java-runtime`/consumer attributes.

Kết luận quan trọng: **`dependencies` giúp tìm vị trí xuất hiện của module, `dependencyInsight` cho biết nguyên nhân version được chọn.** Khi đổi một dependency, nên chạy lại cả hai trước và sau để xác minh tác động.

### 6.8. Thử thay đổi để tự quan sát

Chỉ trong **bản sao demo**:

1. Bỏ dòng `implementation 'commons-codec:commons-codec:1.17.1'`.
2. Chạy `./gradlew dependencyInsight --dependency commons-codec --configuration runtimeClasspath` và `./gradlew dependencies --configuration runtimeClasspath`.
3. Khi không còn yêu cầu nào khác cao hơn, Commons Codec **1.11** từ HttpClient thường được chọn (theo metadata hiện tại của demo). Quan sát lý do conflict có còn xuất hiện không.
4. Thêm lại khai báo trực tiếp `1.17.1` và so sánh.

**Không chuyển kết quả thử nghiệm thành khuyến nghị downgrade**. Một thư viện transitive có version cũ trong POM không có nghĩa version đó đủ an toàn hoặc phù hợp cho hệ thống production. Dùng report để hiểu, còn chính sách version phụ thuộc compatibility và security review.

## 7. Tìm đúng dependency trong multi-project build

Giả sử có:

~~~text
multi-build/
├── settings.gradle
├── build.gradle
├── app/build.gradle
└── library/build.gradle
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'multi-build'
include 'app', 'library'
~~~

`app/build.gradle` có thể chứa:

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':library')
}
~~~

Với multi-project build, `:app` và `:library` có **các configurations và dependency graphs riêng**. Các lệnh cần nhắm đúng module:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency commons-codec --configuration runtimeClasspath
./gradlew :library:dependencies --configuration runtimeClasspath
~~~

Đây là **ví dụ đường dẫn task**, chưa phải một demo build đầy đủ; cần hai module được khai báo, plugin và repository phù hợp. Một dependency từ `:library` có thể tác động `:app:runtimeClasspath` qua variants/project dependencies. Nhưng không nên suy luận tất cả library internal dependencies đều xuất hiện trên `:app:compileClasspath`: `api` so với `implementation` và variant metadata ảnh hưởng consumer visibility.

### 7.1. Root report không quét mọi module

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Chạy từ root chỉ yêu cầu report của project ở ngữ cảnh gọi (thường root). Nếu root chỉ chứa convention/configuration, nó có thể không có `runtimeClasspath` như Java module. **Lỗi “configuration not found” ở root không chứng minh module `:app` thiếu configuration đó.** Dùng `:app:dependencies` hoặc chọn đúng project.

### 7.2. Task path khác với project dependency path

- `:app:dependencies`: Gradle task report trong module `:app`.
- `implementation project(':library')`: dependency tham chiếu output/variants của một module khác.
- `pluginManagement.includeBuild('build-logic')`: cơ chế tìm plugin từ included build, **không phải project dependency `:library`**.

Khi graph xuất hiện `project :library`, hãy hiểu đó là **project component**. Thông tin nó cung cấp phụ thuộc variant được chọn, không phải một Maven coordinate `group:name:version` theo đúng cùng kiểu với dependency ngoài.

## 8. Khi nào dùng `compileClasspath`, `runtimeClasspath` và `testRuntimeClasspath`?

Các triệu chứng gợi ý configuration:

| Triệu chứng | Configuration cần nhìn trước | Vì sao? |
| --- | --- | --- |
| `javac` báo thiếu package/type | `compileClasspath` | Compiler cần API/class khi biên dịch |
| `java.lang.NoClassDefFoundError` khi chạy app | `runtimeClasspath` | JVM chạy cần implementation runtime phù hợp |
| Test compile báo thiếu JUnit/assertion API | `testCompileClasspath` | Test source phải được biên dịch |
| Test chạy không có engine/service | `testRuntimeClasspath` | Runtime test cần engine/implementation |
| Annotation processor không chạy | `annotationProcessor` | Processor path riêng |
| App có nhiều logging providers | `runtimeClasspath` | Trùng logging binding/implementation thường lộ ở runtime |
| Dependency lỗi trên một variant Android | Configuration theo build type/flavor, ví dụ `debugRuntimeClasspath` | Android Gradle Plugin tạo graph theo variant |
| Dependency lỗi trên Kotlin Multiplatform target | Configuration theo target/source set được plugin tạo | Không luôn tồn tại một `runtimeClasspath` JVM chung |

Không ép một lời giải Java plugin sang Android/KMP bằng cách giả định tên configuration luôn giống nhau. Hãy xem `resolvableConfigurations`, các task plugin tạo hoặc tài liệu plugin tương ứng.

### 8.1. Một dependency có thể bị “ẩn” trong scope bạn không kiểm

Nếu `implementation` chứa Commons Codec, nó có thể không xuất hiện trong `annotationProcessor`. Nếu `testImplementation` chứa một test library, `runtimeClasspath` của source chính thường không chứa nó. Điều này là ranh giới dependency đúng, không phải Gradle quên resolve.

### 8.2. Vì sao `api` và `implementation` ảnh hưởng consumer?

Với `java-library`, `api` biểu thị dependency cần lộ trong **compile API** của library. `implementation` biểu thị chi tiết triển khai. Nếu module `:app` phụ thuộc `:library`, các dependency được công bố qua variants khác nhau có thể ảnh hưởng đồ thị compile/runtime của app khác nhau. Dùng `:app:dependencies --configuration compileClasspath` và runtime counterpart để nhìn từ **consumer thực sự**.

## 9. Đọc variant/attributes trong `dependencyInsight`

Gradle hiện đại dùng **variant-aware resolution**. Một component có thể công bố nhiều variants, chẳng hạn dành cho Java API hay Java runtime. Gradle so các **attributes** mà consumer yêu cầu với attributes do producer cung cấp.

Trong report `dependencyInsight`, bạn có thể thấy bảng tương tự:

~~~text
Variant runtime:
  | Attribute Name           | Provided    | Requested   |
  |--------------------------|-------------|-------------|
  | org.gradle.usage         | java-runtime| java-runtime|
  | org.gradle.category      | library     | library     |
~~~

Đây là **mô phỏng bảng tối giản**, không phải cam kết mọi dependency sẽ công bố đúng hai attributes này. Với module POM Maven đơn giản, Gradle có thể suy ra variants; Gradle Module Metadata có thể chứa variants phong phú hơn.

Khi báo “No matching variant” hoặc “Ambiguous variants”, việc **chỉ đổi version** đôi khi không giải quyết được. Cần:

1. Xác định configuration của consumer và attributes được yêu cầu.
2. Xác định các variants producer cung cấp.
3. Chạy `dependencyInsight --all-variants` nếu component có thể resolve đủ để hiển thị.
4. Xem plugin/model đang đặt attributes, target JVM version, usage, category và capabilities.
5. Chỉnh model của producer/consumer hoặc chọn dependency tương thích; không tùy tiện tắt toàn bộ attribute matching.

**`--all-variants` là chế độ report**, không phải một phép ép Gradle sử dụng mọi variant. Bản báo cáo có thể thay đổi theo Gradle version và metadata thực tế.

## 10. BOM, platform và constraints trong đồ thị

Không phải mọi node hiện ra đều đại diện JAR. `platform(...)` hoặc `constraints` có thể đưa **version constraints** vào resolution.

Ví dụ trích đoạn:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'commons-codec:commons-codec:1.17.1'

    constraints {
        implementation('commons-codec:commons-codec:1.17.1') {
            because 'Giữ version được nhóm xác nhận tương thích'
        }
    }
}
~~~

Đoạn này không phải một tình huống thực tế cần cả direct dependency và constraint cùng một version; nó giúp nhận ra `(c)` trong report. Nếu dùng BOM:

~~~groovy
// Trích đoạn đặt trong dependencies {} của project:
implementation platform('org.springframework.boot:spring-boot-dependencies:3.4.0')
~~~

Đây là **ví dụ cú pháp platform**, không có nghĩa chỉ khai báo BOM sẽ tải tất cả thư viện Spring Boot hoặc tự thêm starter. Gradle dùng các constraints/platform metadata khi có dependency tương ứng được yêu cầu; chúng có thể hiện ra ở cây với annotation `(c)`.

Khi thấy version arrow thay đổi sau khi thêm platform, dùng `dependencyInsight` để nhận diện `By constraint`, `Forced` hoặc nguyên nhân khác. Nếu chọn `enforcedPlatform` thay vì `platform`, yêu cầu phiên bản có thể mạnh hơn và ảnh hưởng consumers của library; cần hiểu chính sách version trước khi áp dụng.

## 11. Quan sát buildscript dependencies và plugin dependencies

`./gradlew dependencies` trong project Java là report của **project configurations**. Nó **không đồng nghĩa** report classpath mà Gradle dùng để chạy mọi plugin.

Đối với buildscript classpath:

~~~bash
./gradlew buildEnvironment
./gradlew :app:buildEnvironment
~~~

`buildEnvironment` cho biết dependencies của build script của project tương ứng, đặc biệt các dependency được đưa vào `buildscript { dependencies { classpath ... } }`. Không gọi `dependencyInsight --configuration runtimeClasspath` để hỏi “vì sao một plugin binary đã được nạp?” nếu module đó chỉ hiện diện trên plugin/buildscript classpath.

External plugins khai báo ở:

~~~groovy
plugins {
    id 'com.gradleup.shadow' version '9.6.1'
}
~~~

được Gradle resolve qua **plugin ID, marker/implementation và `pluginManagement`**, không phải qua `implementation` của app. Có thể cần kiểm tra plugin repository, plugin resolution rule hoặc included build tương ứng; `buildEnvironment` có thể không biểu diễn mọi plugin resolution giống một `classpath` do build script trực tiếp khai báo.

Khi điều tra security/compatibility, phân biệt **runtime app dependency** và **dependency dùng để thực thi Gradle build** vì phạm vi và vòng đời khác nhau.

## 12. Những vấn đề phổ biến và quy trình xử lý

| Hiện tượng | Dấu hiệu report | Hướng chẩn đoán |
| --- | --- | --- |
| Không thấy một module trong `dependencies` | Đã chọn nhầm `compileClasspath`, root project hoặc cấu hình không có library | Xác định source set, project path và configuration đúng |
| Thấy version cũ bị đổi | Dòng `1.11 -> 1.17.1` | `dependencyInsight` để xem conflict/constraint/force |
| Thấy `(*)` | Nhánh đã mở rộng ở nơi khác | Không đánh dấu lỗi; tìm lần xuất hiện đầu |
| Thấy `(c)` | Constraint/platform trong graph | Không coi là JAR; xem reason/constraint origin |
| Thấy `(n)` | Dependency hoặc configuration không resolvable | Kiểm tra vai trò configuration và tình trạng metadata |
| Thấy `FAILED` | Artifact/module/metadata resolve thất bại | Xem repository, coordinate, kết nối, auth, variant và thông báo lỗi |
| `dependencyInsight` không có kết quả | Không khớp tên hoặc không nằm trong configuration | Dùng `group:name` đúng và đổi configuration/project phù hợp |
| `--single-path` chỉ thấy một requester | Report bị giới hạn theo cờ | Chạy lại không có `--single-path` |
| Version được chọn thấp hơn mong đợi | Constraint `strictly`, forced rule, alignment, metadata/variants | Xem `Selection reasons` và version constraints |
| App compile được nhưng runtime lỗi class | Compile/runtime graph khác nhau | So sánh `compileClasspath` vs `runtimeClasspath` |
| Report root trống nhưng `:app` có lib | Root không phải Java module | Dùng `:app:dependencies` |
| Buildscript tìm được JAR nhưng app không import được | Hai classpath khác nhau | Khai báo dependency cho đúng project configuration |
| Mạng lỗi khi report lần đầu | Gradle phải resolve metadata/artifact | Kiểm proxy, repository, credential và cache policy |
| `--offline` fail dù build khác chạy | Cache chưa có mọi module/metadata cần thiết | Tránh offline hoặc chuẩn bị cache đầy đủ |
| `--refresh-dependencies` không sửa được lỗi | Dependency không khai báo, plugin ID sai, variant không khớp | Sửa khai báo/root cause thay vì chỉ refresh |
| Output khác nhau giữa máy dev/CI | Dynamic version, dependency lock, plugin/repo/cache khác | So sánh Wrapper/JDK/Gradle config và locking |
| “Unsafe configuration resolution” warning | Build logic resolve project khác sai scope/thời điểm | Dùng project dependency/cross-project modeling theo API hỗ trợ |

Một cách đọc nhanh khi có lỗi:

~~~text
1. Lỗi ở app, test, annotation processor, plugin hay buildscript?
         |
         v
2. Project path nào? (:app, :library, root...)
         |
         v
3. Configuration resolvable nào?
         |
         v
4. dependencies --configuration <tên>
         |
         v
5. Tìm module/arrow/(c)/(n)/FAILED
         |
         v
6. dependencyInsight --dependency group:name --configuration <tên>
         |
         v
7. Xác định requester + selected version + selection reason
         |
         v
8. Sửa build model và kiểm tra lại trước/sau
~~~

Không thay đổi dependency version chỉ vì nhìn thấy mũi tên `->`. Mũi tên cho thấy kết quả chọn khác yêu cầu; có thể là hành vi đúng, hoặc có thể là xung đột cần giải quyết theo yêu cầu compatibility thực sự.

## 13. Báo cáo dependency graph cho PR/CI

Khi một PR cập nhật library quan trọng, một report ngắn nên trả lời được:

- **Project/variant/configuration** đang xét, ví dụ `:app:runtimeClasspath`.
- **Module** trọng tâm: `group:name`.
- **Requested versions** và **selected version**.
- **Requesters**: dependency trực tiếp hay qua module nào.
- **Selection reason**: conflict, constraint, forced, rule, reject hoặc variant.
- **Tác động compile/runtime/test** nếu cấu hình thay đổi.
- **Phiên bản Gradle Wrapper** và repository/lockfile nếu kết quả phụ thuộc môi trường.
- **Cách xác minh**: lệnh `dependencies` và `dependencyInsight` đủ để tái hiện.

Trên Unix, khi cần lưu report vào file, có thể dùng redirect của shell:

~~~bash
./gradlew -q :app:dependencies --configuration runtimeClasspath > runtime-dependencies.txt
./gradlew -q :app:dependencyInsight --dependency commons-codec --configuration runtimeClasspath > codec-insight.txt
~~~

Đây là ví dụ cho **multi-project có module `:app`**; với demo single-project, bỏ `:app:`. Không coi output file chứa riêng report là manifest khóa version. Nếu muốn tái lập build, cân nhắc **dependency locking**, dependency verification và constraints/platform được review, không dựa vào file text từ một lần chạy.

### 13.1. Build Scan cho graph lớn

Gradle có thể tạo một **Build Scan** bằng `--scan` để xem dependency graph dễ tìm kiếm hơn trong trình duyệt:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath --scan
~~~

Build Scan có thể upload metadata build lên dịch vụ bên ngoài; **chỉ dùng khi chính sách bảo mật của dự án cho phép**. Nếu chưa có quyền/không muốn chia sẻ, report CLI cục bộ vẫn đủ cho phần lớn phân tích. Nội dung và địa chỉ scan phụ thuộc môi trường/plugin; không tự bịa link Scan trong bug report.

## 14. Những giới hạn cần biết của hai report

**`dependencies` và `dependencyInsight` là công cụ quan sát**, không phải lời hứa rằng dependency đã được Java classloader nạp thành công khi chạy ứng dụng. Những trường hợp cần xử lý thêm:

1. **Artifact vs component:** report nói về dependency resolution, nhưng một component có thể có nhiều artifacts hoặc variants; file thực sự trên classpath phụ thuộc task và attributes.
2. **Dynamic versions:** `1.+` hoặc version range có thể cho kết quả khác theo thời gian và cache; report là ảnh chụp kết quả tại lần resolve đó.
3. **Resolution rules:** component substitution, dependency constraints, forced versions, capabilities hoặc metadata rules có thể làm kết quả khác “chọn cao nhất”.
4. **Build logic vs app:** plugin/buildscript dependencies khác app classpath.
5. **Custom configuration:** các plugin Android/KMP/Scala/Kotlin/Gradle distribution có những configuration riêng, không chỉ `compileClasspath`/`runtimeClasspath`.
6. **Report side effects:** task report có thể kích hoạt dependency resolution và truy cập repository; không đặt thao tác này eager ở top level `build.gradle` hoặc tự resolve configuration của project khác từ task action.
7. **Conflicting capability/variants:** đôi khi vấn đề không phải version mà là nhiều components cung cấp cùng capability hoặc không có variant phù hợp.

Nếu cần biết **file JAR cụ thể** được task tiêu thụ, có thể xem task classpath bằng API/IDE hoặc dùng report chuyên biệt của plugin. Không biến tất cả biến thể của resolution thành việc “mở thư mục `~/.gradle/caches`” vì cache vật lý không trả lời được lý do chọn trong configuration.

## 15. Bài tập thực hành có đáp án gợi ý

### Bài A — đọc mũi tên

Cho dòng:

~~~text
commons-codec:commons-codec:1.11 -> 1.17.1
~~~

Hỏi: version nào được yêu cầu, version nào được chọn? **Đáp án:** yêu cầu 1.11, được chọn 1.17.1 **trong graph đang quan sát**. Chưa thể kết luận chính xác vì sao nếu chưa đọc `dependencyInsight`.

### Bài B — vì sao có `(*)`?

~~~text
+--- com.example:first:1.0
|    \--- com.example:shared:2.0
\--- com.example:second:1.0
     \--- com.example:shared:2.0 (*)
~~~

`(*)` nghĩa là Gradle không mở rộng lại subtree trùng, **không phải module thứ hai bị thiếu shared dependency**. Khi cần phân tích origin, dùng `dependencyInsight` cho `com.example:shared`.

### Bài C — chọn đúng configuration

Task `test` không tìm JUnit Jupiter engine khi chạy, trong khi `compileJava` không lỗi. Bạn nên kiểm tra `testRuntimeClasspath` trước, không chỉ `compileClasspath`. Nếu là lỗi Java source chính thiếu class, ưu tiên `compileClasspath`.

### Bài D — giữ một path hay mọi path?

`--single-path` phù hợp khi report có hàng trăm requester và bạn cần một ví dụ ngắn. Để tìm tất cả nơi kéo dependency vào, **bỏ cờ này**. Với các module trùng tên, dùng `--dependency group:name`.

### Bài E — thử xung đột ở demo

Chạy:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-codec --configuration runtimeClasspath
~~~

Ghi lại direct `1.17.1` và transitive `1.11`. Sau đó trong project demo bỏ direct `1.17.1`, chạy lại, so sánh selected version và selection reasons. Không làm thử nghiệm downgrade lên production nếu chưa xác nhận compatibility và security.

### Bài F — `(c)` có tải JAR?

Nhìn thấy `commons-codec:commons-codec:{strictly 1.17.1} -> 1.17.1 (c)`. Bạn đã biết điều gì? **Đó là constraint** tham gia lựa chọn, không khẳng định có một JAR thứ hai chỉ dành cho constraint. Cần tìm dependency thật và xem `dependencyInsight`.

### Bài G — `buildEnvironment` so với `runtimeClasspath`

Nếu `build.gradle` dùng SnakeYAML qua `buildscript.classpath` nhưng Java app không có dependency vào SnakeYAML, nó có tự xuất hiện ở `runtimeClasspath` không? **Không.** Hãy chạy `buildEnvironment` để xem buildscript graph, và `dependencies --configuration runtimeClasspath` để xem app runtime graph.

### Bài H — multi-project

Root chứa `:app` và `:library`. Lệnh `./gradlew dependencies --configuration runtimeClasspath` ở root không tìm thấy configuration. Có nên xóa cache không? **Không.** Hãy chạy `./gradlew :app:dependencies --configuration runtimeClasspath` vì root có thể không áp dụng Java plugin.

## 16. Checklist khi tự điều tra dependency

1. Dùng **Gradle Wrapper** của repository và ghi lại Gradle version khi so sánh môi trường.
2. Xác định module/project đang lỗi, rồi chọn **resolvable configuration** đúng (compile/runtime/test).
3. Chạy `dependencies --configuration ...` để tìm module trực tiếp, bắc cầu, mũi tên version và annotation.
4. Nhớ `(*)` là cây bị rút gọn; `(c)` là constraint; `(n)` là không resolvable.
5. Chạy `dependencyInsight --dependency group:name --configuration ...` để xem requesters và selection reasons.
6. Dùng `--single-path` để thu gọn hoặc `--all-variants` để xem variants khi thích hợp.
7. Không giả định “Gradle luôn chọn mới nhất” khi có constraints, platform, rule, forced versions hoặc variants.
8. Với multi-project, chọn task `:app:dependencies` thay vì dùng root report theo thói quen.
9. Với script/plugin classpath, xem `buildEnvironment`/plugin resolution thay vì chỉ app `runtimeClasspath`.
10. Khi cập nhật dependency, **so sánh trước và sau**, chạy compile/test, review security và tính tái lập.
11. Không xóa cache/force version tùy tiện chỉ dựa vào một mũi tên trong report.
12. Lưu command và configuration trong bug report; tránh upload Build Scan nếu chính sách dữ liệu không cho phép.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, các marker `(*)`/`(c)`/`(n)`, `dependencyInsight`, `--single-path` và `--all-variants`.
- [Gradle User Manual — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html): module/project/file dependency, transitive dependencies và `because`.
- [Gradle User Manual — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): vai trò declarable/resolvable/consumable và configuration của Java plugin.
- [Gradle User Manual — Dependency Constraints and Conflict Resolution](https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html): constraints, version conflict và lựa chọn component.
- [Gradle User Manual — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): task reports, `--configuration` và cách dùng CLI.
- [Gradle User Manual — Variant Selection](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): attributes, capabilities và selection.
- [Apache HttpClient 4.5.14 — Dependencies](https://hc.apache.org/httpcomponents-client-4.5.x/current/httpclient/dependencies.html): metadata transitive `commons-codec:1.11` dùng cho demo.

# Dependency ngoài, dependency project và dependency tệp

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Mô hình dependency

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **external module dependency** (dependency ngoài), **project dependency** (dependency tới project khác trong cùng build) và **file dependency** (dependency trực tiếp tới một hoặc nhiều file).
2. Hiểu tại sao **loại dependency** và **dependency configuration** là hai khái niệm khác nhau; áp dụng đúng implementation, api, runtimeOnly, compileOnly và testImplementation.
3. Khai báo cả ba loại bằng Gradle Groovy DSL và biết khi nào cần repository, tọa độ module, Gradle project path hoặc file path.
4. Giải thích **transitive dependencies**, metadata, version resolution, variant-aware resolution và khác biệt compileClasspath/runtimeClasspath.
5. Thực hành một dự án **Java 17** gồm hai Gradle subprojects và một JAR được tạo bằng javac/jar: ứng dụng dùng cả external, project và file dependencies.
6. Biết cách dùng dependencies, dependencyInsight và projects để chẩn đoán lỗi; chọn cách quản lý binary hợp lý cho CI, nhóm phát triển và library publication.

**Cốt lõi:** Cùng xuất hiện trong dependencies { ... }, nhưng dependency ngoài trỏ tới **module có tọa độ ở repository**; dependency project trỏ tới **một project Gradle trong build**; dependency tệp trỏ tới **file đã tồn tại**, không mang module metadata để Gradle tự tìm những dependency khác của file ấy.

## 1. Ba loại dependency trong cùng một bản đồ

Một ứng dụng Java có thể dùng đồng thời:

- **Thư viện đã phát hành:** Apache Commons Lang từ Maven Central.
- **Thư viện nội bộ:** module :core được nhóm xây dựng cùng dự án.
- **JAR cũ từ nhà cung cấp:** file app/libs/local-label.jar.

Các dạng khai báo Groovy DSL:

~~~groovy
dependencies {
    // External module dependency:
    implementation 'org.apache.commons:commons-lang3:3.14.0'

    // Project dependency:
    implementation project(':core')

    // File dependency:
    implementation files('libs/local-label.jar')
}
~~~

Đây là minh họa **ba loại nguồn** trên một configuration. Trong dự án lab chạy được ở phần 6, Commons Lang chỉ được :core sử dụng nên dòng external được đặt trong core/build.gradle; :app dùng project(':core') và file dependency.

### 1.1. So sánh nhanh

| Tiêu chí | Dependency ngoài | Dependency project | Dependency tệp |
|---|---|---|---|
| Cú pháp mẫu | implementation 'group:name:version' | implementation project(':core') | implementation files('libs/local.jar') |
| Định danh | Group, module name và version | Gradle project path | Đường dẫn file hoặc FileCollection |
| Nơi lấy | Maven/Ivy repository hoặc module repository được cấu hình | Một project trong build hiện tại | Filesystem |
| Repository cho chính dependency đó? | Cần nguồn repository thích hợp | Không; nhưng project đích có thể dùng external modules | Không |
| Có thông tin metadata module? | Có thể có POM/Gradle Module Metadata/Ivy | Có mô hình project, outgoing variants | Không có module metadata gắn với file notation |
| Dependency kéo theo | Theo metadata và quy tắc resolution | Theo các dependency/variants của project đích | File không tự khai báo dependency của nó |
| Task producer | Không có task compile module ngoài trong current build | Gradle hiểu task nào cung cấp classes/artifact | Đường dẫn file đơn thuần không chỉ task tạo file |
| Version conflict resolution | Có identity/version cho module | Variant/attribute resolution của project | Không có module version identity để hòa giải như external module |
| Publish | Có thể ghi module dependency vào published metadata | Thường biểu diễn thành module dependency sau publish | Không được ghi thành module dependency có tọa độ trong descriptor đã publish |
| Dùng phù hợp | Thư viện version hóa được phát hành | Module cùng sản phẩm/build | Binary legacy, PoC hoặc tình huống có kiểm soát |

**Sắc thái:** File dependency có thể đi theo classpath khi được lan truyền qua quan hệ giữa các project trong cùng build; nhưng consumer **ở ngoài** build không thể tự resolve file local từ một published POM như với module dependency. Vì thế không nên kết luận file dependency hoàn toàn không thể truyền qua project dependency, cũng không nên hứa nó được publish như một module.

## 2. Phân biệt loại dependency với phạm vi sử dụng

Gradle tách hai câu hỏi:

1. **Cần thư viện nào và lấy từ đâu?** External, project hay file.
2. **Nó tham gia classpath nào?** Thông qua configuration do plugin cung cấp.

Ví dụ cả ba loại đều có thể được đặt trong runtimeOnly:

~~~groovy
dependencies {
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.13'
    runtimeOnly project(':runtimeSupport')
    runtimeOnly files('libs/driver.jar')
}
~~~

Đoạn trên chỉ minh họa cú pháp: :runtimeSupport và file driver.jar phải tồn tại trong dự án thực tế. Các dependency ấy được khai báo cho runtime, không tự động được dùng để compile mã nguồn chính.

### 2.1. Những configuration thường gặp với Java plugin

| Configuration | Vai trò chính |
|---|---|
| implementation | Dependency dùng khi compile và runtime trong module; với java-library, không mặc định phơi bày dependency implementation trong compile classpath của consumer |
| api | Dependency thuộc API của một module java-library, có thể được consumer dùng khi compile |
| compileOnly | Chỉ cần để compile; không có trên runtime classpath chuẩn |
| runtimeOnly | Chỉ cần lúc chạy; không cấp cho compileClasspath |
| testImplementation | Phụ thuộc để compile/chạy tests |
| testRuntimeOnly | Phụ thuộc chỉ cần ở runtime của tests |
| annotationProcessor | Processor cho Java annotation processing, khác implementation dependency |

Các configuration này tùy thuộc **plugin**. Chẳng hạn api là đặc trưng của java-library, không thể giả định mọi plugin đều cung cấp nó. Với app cần dùng một class từ JAR local trong mã Java, dùng implementation files(...), không phải runtimeOnly files(...).

**Phân biệt bucket với classpath:** implementation là nơi **khai báo**; compileClasspath và runtimeClasspath là những configuration được Gradle **resolve** để tìm các file thực sự dùng cho compile/run.

### 2.2. Khi nào chọn api thay implementation?

Trong library module:

- Nếu dependency chỉ được dùng **bên trong method body** hoặc implementation, ưu tiên implementation.
- Nếu type của dependency xuất hiện trong public method signature, public field, superclass/interface hay public annotation mà consumer cần nhìn thấy khi compile, cân nhắc api.
- api có thể tăng compile classpath của các project tiêu thụ; không nên lạm dụng chỉ để “cho chắc”.

Hai chiều hoàn toàn độc lập: dependency external có thể được khai báo api hoặc implementation; dependency project cũng vậy. File dependency cũng được đặt trong configuration thích hợp, dù nó có hạn chế về metadata.

## 3. Dependency ngoài: External Module Dependency

### 3.1. Group, name, version và repository

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Ba thành phần tọa độ:

~~~text
group             : name          : version
org.apache.commons: commons-lang3 : 3.14.0
~~~

- **group** cho biết nhóm xuất bản.
- **name** là module/artifact.
- **version** mô tả phiên bản được yêu cầu; phiên bản được chọn cuối cùng còn có thể do conflict resolution hoặc constraint quyết định.
- **repository** cho biết nơi Gradle tìm metadata và artifact. Gradle không tự mặc định Maven Central cho mọi project; bạn phải khai báo repository theo mô hình build.

External dependency không cần được copy bằng tay vào libs. Gradle tải và cache metadata/artifact khi cần và điều kiện mạng/quyền truy cập cho phép.

### 3.2. Metadata làm được điều file dependency không làm được

Một module published có thể mang:

- Tọa độ, phiên bản, danh sách artifact.
- Dependency của chính nó, bao gồm những dependency transitive.
- Thông tin compile/runtime scope, variant, capability và attribute (tùy format metadata).
- Thông tin cần cho resolution, kiểm tra phiên bản và khả năng tái lập build.

Giả sử module A khai báo phụ thuộc module B trong metadata, khi dự án yêu cầu A, Gradle có thể đưa B vào graph phù hợp. Đó là **transitive dependency**.

Không phải module nào cũng có dependency transitive. Ví dụ Commons Lang không cần được giả định kéo theo những JAR cụ thể chỉ để minh họa.

### 3.3. Phiên bản được yêu cầu khác phiên bản đã resolve

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Đây là yêu cầu 3.14.0. Trong graph phức tạp, một nhánh khác có thể yêu cầu version khác của cùng module và Gradle chọn phiên bản theo resolution rules. Đừng khẳng định classpath chắc chắn chứa đúng phiên bản được ghi nếu chưa kiểm tra graph.

Công cụ thích hợp:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

Chạy những lệnh ấy tại project có dependency, hoặc chỉ rõ project path trong multi-project build.

### 3.4. Nên ưu tiên notation chuỗi

Đối với Gradle mới, dùng một chuỗi group:name:version:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.14.0'
~~~

Dạng map notation cũ như implementation group: ..., name: ..., version: ... đã bị deprecated trong Gradle 9.x và không nên dùng trong build mới. Nếu có classifier hoặc extension đặc thù, tra notation chuẩn trong tài liệu Gradle; đừng tự biến mỗi file ZIP/JAR thành một chuỗi tùy tiện.

## 4. Dependency project: module cùng multi-project build

### 4.1. Project path đến từ settings.gradle

~~~text
my-product/
├── settings.gradle
├── app/build.gradle
└── core/build.gradle
~~~

**settings.gradle:**

~~~groovy
rootProject.name = 'my-product'
include('app', 'core')
~~~

**app/build.gradle:**

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':core')
}
~~~

:core là đường dẫn project Gradle trong build, **không phải** Maven coordinate và cũng không phải đường dẫn filesystem tới một JAR cụ thể.

Project :core cần được include. Nếu chỉ có thư mục core nhưng không được settings.gradle đăng ký, Gradle không mặc nhiên coi đó là một subproject. Với project lồng nhau, path có thể là :libs:core tùy cấu trúc include.

### 4.2. Task dependency được mô hình hóa tự động

Khi :app tiêu thụ :core, Gradle có thể xác định output classes/artifact của :core mà :app cần. Ví dụ:

~~~bash
./gradlew :app:compileJava
~~~

Gradle bố trí các producer tasks cần thiết của :core trước consumer :app. Bạn **không** cần thêm dependsOn(':core:jar') một cách thủ công chỉ để dùng project dependency Java bình thường.

Không khẳng định :core:jar luôn phải chạy trước compileJava của :app. Gradle có thể chọn output classes hoặc JAR tùy variant và tối ưu classpath. Nguyên lý đúng là consumer nhận được output cần thiết với quan hệ task phù hợp.

### 4.3. Variant-aware resolution

Java Library Plugin cung cấp những variant tiêu biểu:

- **apiElements** cho compile consumer.
- **runtimeElements** cho runtime consumer.

Gradle dựa vào attributes và yêu cầu consumer để chọn variant tương thích. Với core:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Nếu code của core chỉ dùng Commons Lang nội bộ, :app compile có thể thấy API của core nhưng **không** nhận Commons Lang trong compileClasspath qua implementation của core; :app runtime lại cần Commons Lang vì core dùng thư viện đó khi chạy. Đây là hành vi mong muốn: bảo vệ API boundary và hạn chế recompilation không cần thiết.

Nếu một public API của core có type từ Commons Lang mà consumer phải compile chống lại, đổi khai báo phù hợp thành:

~~~groovy
dependencies {
    api 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Như vậy compile consumer có thể nhận dependency API. Không đổi tất cả implementation thành api theo thói quen.

### 4.4. Project khác build không tự thành project dependency

Một repo Git khác hoặc một build Gradle độc lập không thể được gọi project(':core') chỉ vì nó có tên core. Các lựa chọn phù hợp là:

- Publish thư viện đó vào Maven/Ivy repository rồi dùng external module dependency.
- Dùng composite build/includeBuild và dependency substitution khi thực sự muốn phát triển nhiều build cùng nhau.
- Tổ chức lại thành một multi-project build nếu các module nên chia sẻ một lifecycle.

Đây là lý do project dependency phù hợp nhất cho các module cùng build và cùng nguồn phát triển.

## 5. Dependency tệp: File Dependency

### 5.1. Dùng files và fileTree

Trong app/build.gradle:

~~~groovy
dependencies {
    implementation files('libs/local-label.jar')
}
~~~

Gradle resolve đường dẫn tương đối với **project app**, tức app/libs/local-label.jar. Nó không tự tra Maven Central hay tạo JAR ấy.

Nếu có nhiều file định danh rõ ràng:

~~~groovy
dependencies {
    implementation files('libs/a.jar', 'libs/b.jar')
}
~~~

Nếu thực sự cần quét tất cả JAR trong một directory:

~~~groovy
dependencies {
    implementation fileTree(dir: 'libs', include: ['*.jar'])
}
~~~

**Thận trọng:** FileTree có thể đưa cả JAR cũ, JAR trùng class hoặc version không đúng vào classpath. Nó không tự chọn một phiên bản “tốt nhất” bằng module conflict resolution. Với số file nhỏ và biết trước, khai báo files(...) tường minh dễ kiểm toán hơn.

### 5.2. File dependency không có module metadata

Dòng:

~~~groovy
implementation files('libs/local-label.jar')
~~~

chỉ chứa file path, không nói group/name/version hoặc dependency của JAR. Nếu local-label.jar cần thêm thư viện X để chạy thì **Gradle không tự tải X** chỉ vì JAR có bytecode tham chiếu tới class của X. Cần khai báo X riêng hoặc chuyển JAR sang module có metadata.

Một JAR có thể chứa manifest, class hoặc module-info; điều đó **không tương đương** với việc file dependency của Gradle có POM/Gradle Module Metadata khai báo mọi transitive dependencies.

### 5.3. Xung đột JAR cục bộ

Nếu files('libs/foo-1.0.jar') cùng tồn tại với module external foo phiên bản mới và cả hai chứa cùng class, Gradle không có module version identity cho file dependency để hòa giải giống hai module cùng group/name.

Rủi ro thường gặp:

- NoClassDefFoundError khi runtime thiếu class.
- NoSuchMethodError khi code biên dịch với version khác runtime.
- Trùng class làm hành vi phụ thuộc classpath order.
- License/security/provenance khó kiểm tra.

Dùng module có tọa độ khi có thể và tránh copy nhiều phiên bản binary vào libs.

### 5.4. File dependency và publication

Theo tài liệu Gradle:

- File dependencies có thể đi theo transitive classpath **trong cùng build** qua các project/configuration phù hợp.
- File dependencies **không** được biểu diễn thành dependency có tọa độ trong POM/Ivy descriptor được publish.
- Consumer bên ngoài không thể tự tải một JAR nội bộ chỉ dựa vào published metadata của bạn.

Vì vậy, nếu publish một library cần vendor JAR, nên đưa vendor JAR vào một Maven/Ivy repository với group:name:version và khai báo dependency module. Đừng chỉ dùng files('libs/vendor.jar') rồi trông đợi người dùng khác tự nhận đủ classpath.

### 5.5. File do task tạo cần quan hệ producer

Ví dụ chưa đủ:

~~~groovy
dependencies {
    implementation files('build/generated/vendor.jar')
}
~~~

Nếu vendor.jar chỉ xuất hiện sau khi task khác chạy, path tĩnh không tự cấp thông tin task producer. Cần một cách wiring task output/artifact/provider đúng chuẩn hoặc bảo đảm JAR đã được chuẩn bị trước build.

Với JAR được nhóm xây dựng từ source, **project dependency** thường đơn giản và đáng tin cậy hơn, bởi Gradle hiểu mối quan hệ producer–consumer. Với JAR bên ngoài nhưng có vòng đời release, **module dependency** tốt hơn vì có tọa độ/metadata.

### 5.6. Repository trên ổ đĩa vẫn là repository

Ví dụ một Maven repository nội bộ đặt tại folder:

~~~groovy
repositories {
    maven {
        url = uri('../local-maven-repo')
    }
}

dependencies {
    implementation 'com.example:vendor-lib:1.2.3'
}
~~~

Đây là **external module dependency** dù repository ở ổ đĩa, nếu artifact có layout/metadata đúng. Địa chỉ local hay remote **không** phân loại dependency; cách Gradle định danh và resolve component mới quyết định.

## 6. Bài lab Java 17: kết hợp cả ba dependency

Ta xây một ứng dụng có thể chạy bằng Gradle:

- :core dùng Commons Lang được resolve từ Maven Central.
- :app dùng class công khai từ :core thông qua project dependency.
- :app dùng một class được đóng gói thành JAR local-label.jar thông qua file dependency.

**Kết quả mong đợi khi chạy ứng dụng:** một dòng Hello Java [local].

### 6.1. Cấu trúc

~~~text
dependency-kinds-lab/
├── settings.gradle
├── gradlew                       # sinh khi tạo Wrapper
├── gradlew.bat
├── gradle/wrapper/...
├── core/
│   ├── build.gradle
│   └── src/main/java/demo/core/GreetingFormatter.java
├── app/
│   ├── build.gradle
│   ├── libs/
│   │   └── local-label.jar       # do bước javac/jar tạo ra
│   └── src/main/java/demo/app/App.java
└── vendor-src/
    └── demo/vendor/LocalLabel.java
~~~

Ban đầu bạn chỉ cần tạo settings.gradle, hai build.gradle và ba file .java. Những file Wrapper hoặc JAR xuất hiện sau các bước tạo tương ứng.

### 6.2. Root settings.gradle

~~~groovy
rootProject.name = 'dependency-kinds-lab'

include('core', 'app')

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

- include đăng ký cả :core và :app trong build.
- Maven Central làm nguồn chung cho external modules.
- Không cần repositories trong từng build.gradle của ví dụ, vì dependencyResolutionManagement được cấu hình ở settings.
- Phải có kết nối mạng và quyền truy cập repository cho lần resolve Commons Lang đầu tiên; file vendor thì không được tải từ Maven Central.

### 6.3. Module core và dependency ngoài

**core/build.gradle:**

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

**core/src/main/java/demo/core/GreetingFormatter.java:**

~~~java
package demo.core;

import org.apache.commons.lang3.StringUtils;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String greet(String name) {
        return "Hello " + StringUtils.capitalize(name);
    }
}
~~~

- :core cần Commons Lang để compile vì gọi StringUtils.capitalize.
- Phương thức public greet trả String của JDK và nhận String; nó **không phơi bày kiểu Commons Lang** cho consumer. Dùng implementation phù hợp.
- capitalize("java") cho kết quả "Java".

### 6.4. Module app và project/file dependency

**app/build.gradle:**

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.app.App'
}

dependencies {
    implementation project(':core')
    implementation files('libs/local-label.jar')
}
~~~

**app/src/main/java/demo/app/App.java:**

~~~java
package demo.app;

import demo.core.GreetingFormatter;
import demo.vendor.LocalLabel;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String line = GreetingFormatter.greet("java")
                + " " + LocalLabel.suffix();
        System.out.println(line);
    }
}
~~~

App cần **hai class**:

1. GreetingFormatter từ :core, được Gradle build và chọn variant phù hợp.
2. LocalLabel từ JAR ở app/libs, phải được chuẩn bị trước lúc app compile.

Commons Lang không phải dependency trực tiếp trong app/build.gradle vì app không sử dụng StringUtils. Khi chạy, thư viện ngoài vẫn cần xuất hiện trên runtime classpath để code trong core hoạt động.

### 6.5. File Java sẽ được đóng gói thành JAR local

**vendor-src/demo/vendor/LocalLabel.java:**

~~~java
package demo.vendor;

public final class LocalLabel {
    private LocalLabel() {
    }

    public static String suffix() {
        return "[local]";
    }
}
~~~

Đây là source code **để tạo binary làm file dependency**, không phải thư mục Java source set của app. Vì thế Gradle app không tự compile file này. Bước tiếp theo dùng javac/jar của JDK 17.

### 6.6. Chuẩn bị local-label.jar

Thực hiện **từ root dependency-kinds-lab**.

Linux/macOS:

~~~bash
mkdir -p app/libs build/vendor-classes
javac -encoding UTF-8 -d build/vendor-classes vendor-src/demo/vendor/LocalLabel.java
jar --create --file app/libs/local-label.jar -C build/vendor-classes .
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force app\libs, build\vendor-classes | Out-Null
javac -encoding UTF-8 -d build\vendor-classes vendor-src\demo\vendor\LocalLabel.java
jar --create --file app\libs\local-label.jar -C build\vendor-classes .
~~~

Giải thích:

- javac biên dịch package demo.vendor thành build/vendor-classes/demo/vendor/LocalLabel.class.
- jar đóng gói các .class thành app/libs/local-label.jar.
- Tùy chọn -C build/vendor-classes . nghĩa là lấy nội dung của thư mục classes để đặt đúng package path trong JAR.

Kiểm tra file:

~~~bash
jar --list --file app/libs/local-label.jar
~~~

Trong danh sách có thể có manifest và các entry khác; entry lớp quan trọng là:

~~~text
demo/vendor/LocalLabel.class
~~~

**Đây là bài học về file dependency, không phải quy trình CI khuyến nghị.** Bạn đã tự tạo JAR trước khi chạy Gradle, nên Gradle không tự biết các lệnh javac/jar ngoài build. Với dự án lâu dài hãy chuyển vendor-src thành Gradle project riêng hoặc publish JAR vào repository, thay vì phụ thuộc một file thủ công chỉ có trên máy một người.

### 6.7. Chạy ứng dụng

Nếu dự án có Gradle Wrapper:

~~~bash
./gradlew :app:run --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run --quiet
~~~

Nếu chưa có Wrapper, dùng một Gradle đã cài phù hợp chạy gradle wrapper một lần từ root rồi dùng các script đã tạo. Nên commit Wrapper cần thiết trong dự án thực tế.

Với đúng code và JAR ở trên, JDK 17/toolchain phù hợp, Gradle resolve Commons Lang thành công, **dòng stdout do App.main in** là:

~~~text
Hello Java [local]
~~~

Giải thích từng phần:

- GreetingFormatter.greet("java") trả "Hello Java" nhờ StringUtils.capitalize từ dependency ngoài.
- LocalLabel.suffix() trả "[local]" từ local-label.jar.
- App ghép thêm một dấu cách và in kết quả.

Các log Gradle, thông báo tải dependency và kết quả task graph có thể thay đổi theo phiên bản/môi trường. Khối stdout trên chỉ ghi dòng chắc chắn do ứng dụng tạo ra.

### 6.8. Tại sao không cần xây core thành JAR thủ công?

Dòng implementation project(':core') mô tả producer/consumer ở cấp project. Khi cần compile/run app, Gradle xác định output thích hợp từ core và các task tạo nó. Bạn không cần sao chép file core/build/libs/*.jar vào app/libs.

Đừng khẳng định Gradle luôn chạy core:jar trước app:compileJava; một số Java compilation paths có thể dùng classes output. Kết luận chính xác là **Gradle tự quản lý task dependency và variant/artifact cho project dependency**.

Trái lại, files('libs/local-label.jar') chỉ là một file path. Nếu xóa JAR trước khi chạy app, class LocalLabel có thể không được tìm thấy khi compile. Task run không tự biết cách chạy lại javac/jar ngoài Gradle.

## 7. Quan sát dependency graph và classpath

Các lệnh sau chạy từ root của bài lab.

### 7.1. Xem compileClasspath và runtimeClasspath

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Bạn nên thấy một nhánh liên quan tới project :core. Commons Lang nằm trong implementation của core, nên có thể xuất hiện trong runtimeClasspath của app nhưng không bị phơi bày vào compileClasspath của app qua API của core.

File dependency có thể hiện trong báo cáo dưới dạng file collection tùy phiên bản Gradle; đừng đoán chính xác mọi dòng định dạng báo cáo. Hãy kiểm tra thông tin classpath mà build thực sự resolve.

### 7.2. Xác định external module đang dùng

~~~bash
./gradlew :core:dependencies --configuration compileClasspath
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

- :core cần Commons Lang để compile.
- :app runtime cần thư viện này để thực thi code của core.
- dependencyInsight giải thích cách Gradle chọn version khi một module xuất hiện trong resolved graph.

Không kỳ vọng file dependency cung cấp cùng loại group:name:version để chạy version conflict analysis. Với file JAR, hãy xem path, hash, manifest và binary thực tế.

### 7.3. Kiểm tra project paths

~~~bash
./gradlew projects
~~~

Phải nhìn thấy :app và :core. Nếu không, hãy sửa settings.gradle/include trước khi sửa dependency project.

### 7.4. Cache và offline

Sau một lần online build đã resolve thư viện ngoài:

~~~bash
./gradlew :app:run --offline --quiet
~~~

Lệnh có thể thành công khi bản Gradle Wrapper, JDK và các external dependencies cần thiết đã có sẵn; **offline không tự tạo local-label.jar**. Dependency cache của Gradle khác với file dependency ở app/libs.

## 8. Hiểu rõ api/implementation qua ví dụ

Trong :core:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Với public signature:

~~~java
public static String greet(String name)
~~~

consumer không cần Commons Lang để compile lời gọi greet.

Nếu một method public của core lại trả kiểu thuộc Commons Lang, ví dụ minh họa:

~~~java
// Chỉ minh họa phần API, không thay code trong lab.
public static org.apache.commons.lang3.tuple.Pair<String, String> pair() {
    return org.apache.commons.lang3.tuple.Pair.of("left", "right");
}
~~~

consumer phải hiểu kiểu Pair khi compile; khi đó core nên cân nhắc:

~~~groovy
dependencies {
    api 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

**Hai trục khác nhau:** External/project/file trả lời nguồn cung cấp dependency; api/implementation mô tả quan hệ classpath với consumer. Một dependency project cũng có thể là api khi nó là một phần public API của library.

## 9. Khi nào không nên dùng file dependency?

Các dấu hiệu nên chuyển từ file dependency sang module hoặc project:

1. Nhiều developer cùng dùng nhưng mỗi người lưu JAR ở vị trí khác.
2. CI sạch không có binary, nên build chỉ thành công trên máy đã “chuẩn bị tay”.
3. JAR cần những dependency khác nhưng không có metadata để tự resolve.
4. Hai bản foo-1.0.jar/foo-2.0.jar cùng tồn tại và gây trùng class.
5. Bạn publish thư viện cho consumer ngoài build và muốn họ tự resolve dependencies.
6. Bạn cần inventory, nâng phiên bản, đối chiếu license, provenance hoặc lỗ hổng bảo mật.
7. JAR thực ra được build từ source trong cùng repository mà bạn sở hữu.

Cách thay thế:

- **Dùng project dependency** nếu có source và module cùng build.
- **Publish binary lên Maven/Ivy repository** với group:name:version và metadata phù hợp nếu đây là artifact được quản lý độc lập.
- **Giữ file dependency có kiểm soát** nếu chỉ là legacy binary tạm thời; ghi chính sách checksum/version, đảm bảo mọi CI/dev đều có đúng file trước build.

**Đừng nhầm Maven repo trên đĩa với file dependency.** Đoạn sau vẫn là external module dependency nếu repository có layout/metadata chuẩn:

~~~groovy
repositories {
    maven {
        url = uri('../local-maven-repo')
    }
}

dependencies {
    implementation 'com.example:vendor-lib:1.2.3'
}
~~~

Vị trí local hay remote không phải tiêu chí phân loại; **module identity và cách resolve** mới quan trọng.

## 10. Lỗi thường gặp và cách chẩn đoán

### 10.1. Could not find group:name:version

**Nguyên nhân thường gặp:** Sai tọa độ, chưa publish, thiếu repository, authentication/proxy/TLS sai, hoặc đang dùng --offline khi cache chưa đủ.

**Hướng sửa:** Xác minh group/name/version và cấu hình repository thực tế. --refresh-dependencies hữu ích khi metadata có thể cũ, không thể sửa tọa độ sai hoặc quyền truy cập thiếu.

### 10.2. Project with path ':core' could not be found

**Nguyên nhân:** settings.gradle không include core hoặc bạn đang chạy một build khác.

**Hướng sửa:** Kiểm tra root và include('core'), chạy ./gradlew projects rồi sửa project path; không cần tải JAR từ Maven Central để giải quyết.

### 10.3. Package demo.vendor does not exist

**Nguyên nhân:** app/libs/local-label.jar chưa được tạo, sai path, JAR không chứa class đúng package hoặc khai báo runtimeOnly thay vì implementation khi Java source cần compile.

**Hướng sửa:** Kiểm tra tồn tại app/libs/local-label.jar, chạy jar --list, sửa file path và configuration nếu cần.

### 10.4. NoClassDefFoundError / NoSuchMethodError khi chạy

**Nguyên nhân có thể:** JAR local thiếu transitive thư viện, lớp trùng tên ở hai JAR, version compile/runtime khác nhau hoặc ứng dụng chỉ đóng gói classes mà không kèm runtime dependencies.

**Hướng sửa:** So sánh runtimeClasspath với compileClasspath, dùng dependencyInsight cho external module, dùng jar --list/checksum cho file dependency. Không mặc định task jar của Java plugin tạo fat JAR.

### 10.5. Sửa source core nhưng app dùng lớp cũ

**Nguyên nhân:** App còn phụ thuộc file core-old.jar hoặc trùng class thay vì chỉ dùng project(':core').

**Hướng sửa:** Xóa JAR copy cũ khỏi cấu hình, dùng project dependency để Gradle tự theo dõi output producer phù hợp.

### 10.6. App không import được Commons Lang dù core có dependency

**Nguyên nhân:** Trong java-library, implementation của core không tự phơi bày trong app compileClasspath.

**Hướng sửa:** Nếu app trực tiếp dùng Commons Lang, khai báo trực tiếp trong app; nếu API công khai của core chứa type của Commons Lang, cân nhắc api ở core.

### 10.7. Library publish xong nhưng người dùng thiếu JAR local

**Nguyên nhân:** File dependency không thành module dependency có tọa độ trong published descriptor.

**Hướng sửa:** Publish JAR vào repository module và khai báo version phù hợp, hoặc tổ chức distribution riêng tùy use case.

### 10.8. implementation không chạy như task

implementation là configuration khai báo dependency, không phải task. Dùng :app:dependencies để xem graph, :app:run để chạy Java; không dùng ./gradlew implementation như một hành động build.

### 10.9. File do task sinh ra nhưng compile chạy trước

Chỉ ghi files('build/generated/lib.jar') không bảo đảm có task dependency. Nối đúng output Provider/artifact producer, hoặc dùng project module; đừng dựa vào việc file được tạo tình cờ ở lần build trước.

## 11. Checklist review một dependency mới

1. Nguồn là module publish, project cùng build hay file local?
2. Configuration có phù hợp compile/runtime/test không?
3. Với external: group/name/version và repository đã chính xác chưa?
4. Với project: project path được include và variant phù hợp chưa?
5. Với file: path tương đối với đúng project, binary có trong CI sạch và có version/checksum rõ không?
6. Có transitive dependencies/metadata cần thiết không?
7. Có public API buộc dùng api thay vì implementation không?
8. Có hai JAR chứa cùng class hoặc các version không tương thích không?
9. Sự thay đổi trong source producer có cập nhật consumer đúng không?
10. Khi publish, người dùng ngoài build có tự resolve dependencies không?
11. Có nguy cơ license/security/supply-chain cần theo dõi không?
12. Đã kiểm tra resolved dependency graph thay vì chỉ nhìn số dòng dependencies { ... } chưa?

## 12. Bài tập tự kiểm tra

**Bài 1.** Viết ba dòng Gradle Groovy DSL: dùng Commons Lang 3.14.0 từ Maven Central, module :shared cùng build, và file libs/legacy.jar, tất cả dùng cho compile/runtime.

**Bài 2.** Vì sao project(':shared') không hoạt động nếu settings.gradle chưa include shared, dù thư mục shared có tồn tại?

**Bài 3.** Legacy.jar cần Jackson tại runtime nhưng là file dependency không có POM. Gradle có tự tải Jackson không?

**Bài 4.** Core dùng Commons Lang chỉ trong method body. Với java-library, chọn api hay implementation? App nhận những dependency nào ở compile so với runtime?

**Bài 5.** Nếu core public method trả type org.apache.commons.lang3.tuple.Pair, nên chọn api hay implementation trong core?

**Bài 6.** App import StringUtils trực tiếp; hiện Commons Lang chỉ là implementation của core. Bạn nên xử lý dependency tại app thế nào?

**Bài 7.** Có fileTree('libs') chứa foo-1.0.jar và foo-2.0.jar, Gradle có tự chọn một file như cách module version conflict resolution không?

**Bài 8.** Bạn publish module có files('libs/private.jar'); consumer bên ngoài có thể dựa vào POM để tự tải private.jar không?

**Bài 9.** File JAR được custom task tạo trong build; chỉ khai báo files('build/generated/a.jar') có đủ để Gradle tự chạy task tạo JAR trước khi compile không?

**Bài 10.** Vì sao :app:dependencies --configuration runtimeClasspath có thể hiển thị nhiều dependency hơn những dòng khai báo trực tiếp trong app/build.gradle?

**Bài 11.** Dùng implementation project(':core') có cần tự tạo dependsOn(':core:jar') cho mọi consumer không? Vì sao?

**Bài 12.** Task jar mặc định có biến mọi dependency implementation thành một JAR duy nhất chứa tất cả class không?

### Đáp án gợi ý

1. implementation 'org.apache.commons:commons-lang3:3.14.0'; implementation project(':shared'); implementation files('libs/legacy.jar'). Cần có source và repository phù hợp.
2. Path tới project phải được settings.gradle đăng ký; Gradle không tự suy ra từ thư mục bất kỳ.
3. Không. File dependency không mang metadata transitive; phải khai báo Jackson riêng hoặc dùng module có metadata.
4. implementation là lựa chọn phù hợp khi core dùng nội bộ; app compile thấy API core nhưng không mặc định thấy Commons Lang qua implementation, còn app runtime có thể chứa Commons Lang do core cần nó.
5. api, nếu Pair thực sự thuộc public API cần để consumer compile.
6. App nên khai báo Commons Lang trực tiếp khi dùng trực tiếp; không tự đổi mọi dependency core thành api.
7. Không. FileTree có thể đưa cả hai JAR vào classpath.
8. Không. Published descriptor không tự cung cấp module dependency cho JAR local đó.
9. Không chắc. Cần kết nối artifact với TaskProvider/producer hoặc tạo file trước build qua quy trình được kiểm soát.
10. Vì transitive dependencies, project dependency và variant-aware resolution.
11. Không. Gradle mô hình hóa producer/consumer tasks theo project dependency và variant.
12. Không. Task jar mặc định đóng gói outputs của project; dùng distribution hoặc packaging phù hợp nếu cần gom runtime dependencies.

## Tài liệu tham khảo chính thức

- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html): loại module/project/file, cú pháp và đặc điểm file dependency.
- [Gradle — Dependency Management Basics](https://docs.gradle.org/current/userguide/dependency_management_basics.html): repositories, resolution và nguồn dependency.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): include project và project dependency.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api/implementation, variants và compile/runtime classpaths.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html): configuration bucket và resolvable classpath.
- [Gradle — Dependency Versions](https://docs.gradle.org/current/userguide/dependency_versions.html): version constraints, dynamic/changing dependency và cách nhận diện version của file dependency.
- [Gradle — Dependency Insight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): xem tree và quyết định phiên bản.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): xác minh artifact/metadata khi cần kiểm soát supply chain.

**Ghi nhớ:** Dependency ngoài dùng **repository và group:name:version**; dependency project dùng **project path và task/variant model của Gradle**; dependency tệp dùng **file path không có module metadata**. Chọn đúng nguồn, đúng configuration và kiểm tra resolved classpath. Với hệ thống phát triển dài hạn, ưu tiên cơ chế version hóa, metadata và quy trình build/publish tái lập.
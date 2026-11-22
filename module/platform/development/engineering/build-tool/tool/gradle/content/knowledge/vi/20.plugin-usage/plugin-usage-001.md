# Plugin cung cấp task, extension, configuration và quy ước trong Gradle

## 1. Mục tiêu học tập và tình huống thực tế

Khi đọc một file **build.gradle** có các dòng như **plugins { id 'java-library' }**, **tasks.named('test')**, **java { toolchain { ... } }** hoặc **dependencies { implementation(...) }**, người mới dễ nghĩ mọi tên và block đó đều là cú pháp có sẵn của ngôn ngữ Groovy. Thực tế, phần lớn chúng tồn tại vì **một plugin Gradle đã được áp dụng vào project**.

Plugin là cách đóng gói và tái sử dụng build logic. Một plugin có thể:

- **Đăng ký task** mới và cấu hình những task đã có.
- **Cung cấp extension**: đối tượng cấu hình có kiểu, thường tạo ra một block DSL mới trong build script.
- **Tạo dependency configurations**: các phạm vi dùng để khai báo, phân giải hoặc công bố dependencies.
- **Đặt conventions (giá trị mặc định/quy ước)** cho property, task, toolchain, đầu ra hoặc cách cấu hình các plugin khác.
- Áp dụng plugin khác, đăng ký callbacks, thêm components/artifacts và tích hợp vào lifecycle task hiện có.

Bài học thuộc chủ đề **Sử dụng plugin**, tập trung trực tiếp vào câu hỏi: **Plugin cung cấp task, extension, configuration và quy ước như thế nào, và người viết build.gradle dùng chúng ra sao?**

Sau khi học, bạn có thể:

1. Giải thích sự khác nhau giữa **Plugin**, **Project**, **Task**, **Extension**, **Configuration**, **Property/Provider** và **Convention**.
2. Nhận ra tác dụng của **java**, **java-library**, **application** cùng tác dụng của một plugin tự viết.
3. Áp dụng plugin đúng scope, hiểu giai đoạn **apply** so với giai đoạn task action thực thi.
4. Sử dụng **tasks.register**, **tasks.named**, **configureEach**, **extensions.create** và **Property.convention**.
5. Phân biệt **declarable**, **resolvable**, **consumable configuration**, không resolve nhầm **implementation**.
6. Viết một plugin bằng Java 17 cung cấp đủ **task**, **extension**, **configuration** và **default conventions**.
7. Chạy ví dụ multi-project bằng Gradle Wrapper; tự kiểm chứng Java source bằng **javac --release 17** và **java**.
8. Chẩn đoán lỗi **task not found**, **unknown property**, **configuration not found**, plugin ID không resolve và output/cache sai.

## 2. Mô hình tư duy: plugin bổ sung năng lực vào một Project

Một **Project** trong Gradle là mô hình của một thành phần build, chẳng hạn module **:core** hoặc **:app**. Project có sẵn những collection/API như **plugins**, **tasks**, **extensions**, **configurations** và **dependencies**. Plugin dùng những API này để thêm hoặc điều chỉnh phần tử.

~~~text
                         build.gradle của :app
                                |
                   plugins { id 'application' }
                                |
                                v
                        Gradle áp dụng Plugin
                                |
              +-----------------+------------------+
              |                 |                  |
              v                 v                  v
         TASKS             EXTENSIONS         CONFIGURATIONS
       compileJava          java              implementation
       run                  application       runtimeClasspath
       test                 ...               testImplementation
              |                 |                  |
              +-----------------+------------------+
                                |
                                v
                  Plugin thiết lập conventions:
                 toolchain, output, task wiring...
                                |
                                v
                  Gradle lập graph và thực thi
                   những task được yêu cầu
~~~

Ví dụ khi áp dụng **application** plugin:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.Main'
}

tasks.named('run', JavaExec) {
    args 'hello'
}
~~~

- **application** là plugin tích hợp Gradle, mang lại task **run**, extension **application** và áp dụng các khả năng của Java plugin.
- **application { ... }** cấu hình extension chứ **không phải** lệnh Groovy tùy ý được công nhận ở mọi project.
- **tasks.named('run', JavaExec)** cấu hình task **run** đã được plugin đăng ký; nếu chưa áp dụng application plugin thì task này thường không tồn tại.
- Khi chạy **./gradlew run**, Gradle mới thực thi task **run** cùng các task dependency cần thiết. Đoạn **plugins { ... }** là cấu hình build, không phải một câu lệnh trực tiếp chạy ứng dụng.

### 2.1. Bảng phân biệt nhanh

| Khái niệm | Trả lời câu hỏi nào? | Ví dụ |
| --- | --- | --- |
| **Plugin** | Ai thêm khả năng vào build? | **java-library**, **application**, **demo.greeting** |
| **Task** | Build cần làm công việc gì? | **compileJava**, **test**, **generateGreeting** |
| **Extension** | Người dùng cấu hình tính năng bằng cách nào? | **java { ... }**, **application { ... }**, **greeting { ... }** |
| **Configuration** | Dependencies được khai báo, giải quyết hoặc công bố ở scope nào? | **implementation**, **runtimeClasspath**, **greetingTools** |
| **Property/Provider** | Dữ liệu được cấu hình và cung cấp khi nào? | **Property<String>**, **RegularFileProperty** |
| **Convention** | Giá trị mặc định hợp lý là gì nếu người dùng không ghi đè? | target Java 17, recipient mặc định **Gradle**, output dưới **build/** |

**Một plugin có thể cung cấp cả bốn loại; không phải mọi plugin bắt buộc phải cung cấp đủ bốn.** Ví dụ một plugin checkstyle tập trung vào task, configuration và extension chất lượng mã; một convention plugin có thể chỉ cấu hình plugin Java đã có.

### 2.2. Plugin được áp dụng vào phạm vi nào?

Gradle hỗ trợ các plugin target khác nhau:

- **Plugin<Project>**: áp dụng cho từng project, thường là plugin bạn viết ở **build.gradle**.
- **Plugin<Settings>**: xử lý settings, plugin resolution, project inclusion hoặc chính sách ở initialization.
- **Plugin<Gradle>**: tác động ở cấp đối tượng Gradle/invocation, thường dùng trong init plugin hoặc hạ tầng tổ chức.

Ví dụ trong bài dùng **Plugin<Project>**. Áp dụng vào **:core** không tự làm extension của plugin xuất hiện ở **:app**, trừ khi bạn cũng áp dụng plugin vào :app. Mỗi project có **task container**, **extension container** và **configuration container** riêng.

## 3. Áp dụng plugin: core, external và custom

### 3.1. Core plugins

Các plugin phổ biến đi kèm bản phân phối Gradle:

~~~groovy
plugins {
    id 'java'
}
~~~

hoặc:

~~~groovy
plugins {
    id 'java-library'
}
~~~

hoặc:

~~~groovy
plugins {
    id 'application'
}
~~~

Dùng plugin phù hợp với vai trò của module:

- **java**: mô hình nguồn Java, biên dịch, kiểm thử, đóng JAR.
- **java-library**: ngoài Java còn thêm tách biệt **api** và **implementation** cho thư viện.
- **application**: cung cấp application extension và task **run**, distribution/install tasks.

Đây là các ví dụ tách biệt; không phải chỉ có thể áp dụng một plugin. **application** áp dụng Java plugin dưới lớp, vì vậy không nhất thiết khai báo thêm **id 'java'**.

### 3.2. External plugins

Plugin bên ngoài có ID, phiên bản và nguồn plugin resolution:

~~~groovy
plugins {
    id 'com.diffplug.spotless' version '7.0.2'
}
~~~

Đoạn này **minh họa cú pháp plugin version**, không phải phần bắt buộc của demo chạy bên dưới. Khi dùng thật, kiểm tra phiên bản tương thích với Gradle/JDK và plugin được phát hành trên kho được tổ chức cho phép. Một plugin có thể thêm task formatter, extension và các cấu hình riêng.

**External plugin repositories** thường được cấu hình ở **settings.gradle**:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

Trong khi external **library dependencies** của project được cấu hình riêng:

~~~groovy
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

Không tự suy rằng **mavenCentral()** trong dependencyResolutionManagement đủ để resolve mọi plugin ID; đây là hai cơ chế resolution khác nhau.

### 3.3. Custom plugin trong build logic

Khi nhóm muốn chuẩn hóa task hoặc DSL, có thể tạo plugin trong **buildSrc** hoặc included build **build-logic**:

~~~groovy
plugins {
    id 'demo.greeting'
}
~~~

**demo.greeting** trong bài là plugin **tự viết** và chỉ tồn tại sau khi bạn tạo đầy đủ file build logic ở mục 9. Nó **không** phải core plugin hoặc plugin có thể lấy từ Gradle Plugin Portal theo ID đó.

**buildSrc** phù hợp cho bài thực hành và project nhỏ. Với repo lớn, convention plugin trong included build **build-logic** thường có lợi thế về modularity và phạm vi rebuild rõ hơn.

### 3.4. plugins block và apply plugin

Dạng hiện đại thường được ưu tiên:

~~~groovy
plugins {
    id 'java-library'
}
~~~

Dạng legacy/dynamic:

~~~groovy
apply plugin: 'java-library'
~~~

Cả hai có thể áp dụng plugin, nhưng **plugins { ... }** thường rõ ràng hơn về plugin request, version và khả năng giải quyết plugin trước khi phần còn lại của script được đánh giá. Không thay **apply plugin** cho **plugins block** tùy tiện khi bạn chưa hiểu plugin resolution hoặc plugin đã ở classpath nào.

### 3.5. apply false ở root

Trong multi-project build:

~~~groovy
plugins {
    id 'com.diffplug.spotless' version '7.0.2' apply false
}
~~~

**apply false** không áp dụng plugin vào root, vì thế root không tự có các task/extension của plugin đó. Subproject có thể áp dụng plugin theo cơ chế phù hợp. Đây là snippet giải thích scope, không phải file root dùng trong lab bên dưới.

## 4. Khi nào các phần tử được tạo: apply, configuration và execution

Plugin thường có method **apply(Project project)**. Gradle gọi method này khi plugin được áp dụng vào project. Trong **apply**, plugin có thể:

1. Tạo extension.
2. Đặt conventions cho các property.
3. Đăng ký configurations.
4. Đăng ký tasks.
5. Tạo quan hệ giữa task inputs/outputs và dependency configurations.
6. Đăng ký callback cấu hình khi plugin khác được áp dụng.

**apply() không phải task action.** Nếu một plugin mở kết nối mạng, đọc toàn bộ filesystem hoặc tính toán nặng ngay trong apply, công việc đó sẽ xảy ra ở lúc cấu hình, dù người dùng chỉ chạy **help**. Thiết kế tốt mô tả tasks và providers trước, chỉ làm công việc nghiệp vụ trong **@TaskAction** hoặc task action.

~~~text
INITIALIZATION
  - settings.gradle xác định projects, plugin repositories
           |
           v
CONFIGURATION
  - Gradle áp dụng plugins vào từng Project cần cấu hình
  - plugin.apply(project)
  - thêm extensions / configurations / task registrations
  - đọc build.gradle và giá trị cấu hình của người dùng
  - lập task graph
           |
           v
EXECUTION
  - Gradle xử lý task graph cần thiết
  - đọc inputs, chạy @TaskAction của tasks được chọn
  - tạo outputs, kiểm tra UP-TO-DATE/cache nếu đủ điều kiện
~~~

Gradle có configuration cache và các tối ưu khác, nên không giả định mỗi lần gọi Gradle đều thực hiện lại toàn bộ configuration. Sơ đồ diễn giải thứ tự logic của một build khi configuration không được tái sử dụng.

### 4.1. Plugin có thể đăng ký task mà không thực thi task

~~~groovy
tasks.register('hello') {
    group = 'demo'
    doLast {
        println 'Hello'
    }
}
~~~

Chỉ sau khi task được chọn (trực tiếp hoặc qua dependency) thì **doLast** mới có khả năng chạy. Lệnh **./gradlew help** không có lý do thực thi hello chỉ vì nó đã được đăng ký.

Phân biệt:

- **tasks.register(...)**: đăng ký task theo hướng tránh hiện thực/cấu hình sớm.
- **tasks.named(...)**: tham chiếu/cấu hình task theo tên đã đăng ký.
- **tasks.withType(SomeType).configureEach { ... }**: áp dụng cấu hình cho từng task phù hợp khi được cấu hình.
- **tasks.create(...)**, **tasks.getByName(...)**, **tasks.all { ... }**: có thể gây eager task realization, nên hạn chế trong plugin cần mở rộng tốt.

### 4.2. Callback khi plugin khác được áp dụng

Một plugin có thể chỉ cấu hình task của Java plugin khi Java plugin thật sự xuất hiện:

~~~groovy
pluginManager.withPlugin('java') {
    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
~~~

Đây là **snippet Groovy DSL minh họa**, thích hợp khi build có Java Test tasks và JUnit Platform dependencies. **withPlugin('java')** tránh phụ thuộc cứng vào thứ tự plugin: callback được dùng khi plugin Java đã có hoặc vừa được áp dụng. Không dùng **afterEvaluate** như công cụ mặc định chỉ để chờ một task hay extension xuất hiện.

## 5. Plugin cung cấp task: từ đăng ký tới việc thực thi

### 5.1. Tạo task một cách lazy

Một plugin nên ưu tiên:

~~~java
project.getTasks().register(
    "generateGreeting",
    GenerateGreetingTask.class,
    task -> {
        task.setGroup("demo");
        task.setDescription("Tạo tệp lời chào");
    }
);
~~~

**GenerateGreetingTask** là lớp tùy chỉnh sẽ được định nghĩa ở mục 9, không phải class Gradle có sẵn. API **register** trả **TaskProvider<GenerateGreetingTask>**, cho phép cấu hình hoặc khai báo dependency mà không phải lấy đối tượng Task ngay.

Ngược lại:

~~~java
project.getTasks().create("generateGreeting", GenerateGreetingTask.class);
~~~

sẽ hiện thực task sớm hơn. Với project lớn, khác biệt này có thể ảnh hưởng thời gian cấu hình, đặc biệt nếu plugin tạo nhiều task tùy chọn.

### 5.2. Task cần input/output rõ ràng

Một custom task đáng tin nên mô tả những gì ảnh hưởng kết quả:

~~~java
@Input
public abstract Property<String> getRecipient();

@OutputFile
public abstract RegularFileProperty getOutputFile();
~~~

- **@Input** nói Gradle biết chuỗi recipient là input nghiệp vụ.
- **@OutputFile** khai báo file task tạo ra.
- **Property** và **RegularFileProperty** hỗ trợ giá trị lazy, convention và nối từ extension.
- **@TaskAction** đánh dấu method làm việc khi task được thực thi.

Nhờ các khai báo đó, Gradle có thể xác định input/output của task để hỗ trợ up-to-date checks; build cache còn phụ thuộc task/cache policy và các điều kiện tương ứng, không tự đảm bảo mọi custom task đều được cache.

### 5.3. Group, description và plugin task discoverability

Khi plugin thêm task, nên đặt **group** và **description**:

~~~groovy
tasks.register('generateGreeting') {
    group = 'documentation'
    description = 'Tạo lời chào cho nhóm'
}
~~~

Người dùng có thể khám phá qua:

~~~bash
./gradlew tasks
./gradlew tasks --all
./gradlew help --task generateGreeting
~~~

Không xem nhóm task là dependency hoặc phase: **group** chỉ giúp hiển thị trong task report.

### 5.4. Plugin được áp dụng nhưng task chưa chắc có thể dùng ngay

Nếu task được tạo **có điều kiện** sau khi plugin khác xuất hiện, hoặc chỉ có trong một project được áp dụng plugin, việc gọi task từ root có thể gây nhầm.

Với multi-project:

~~~bash
./gradlew :app:generateGreeting
./gradlew :core:generateGreeting
~~~

đường dẫn đầy đủ **:app:** và **:core:** loại bỏ ambiguity. Plugin chỉ tạo task ở những project đã áp dụng nó.

## 6. Plugin cung cấp extension: DSL có kiểu cho người dùng

### 6.1. Extension tạo ra một block mới

Plugin có thể gọi:

~~~java
GreetingExtension extension = project.getExtensions()
        .create("greeting", GreetingExtension.class);
~~~

Khi đó build script có thể cấu hình:

~~~groovy
greeting {
    recipient.set('Java 17')
    outputFile.set(layout.buildDirectory.file('generated/app-hello.txt'))
}
~~~

Block **greeting { ... }** không phải một keyword của Java, Groovy hoặc Gradle core; đó là tên extension do plugin tự thêm vào project.

Extension nên dùng **managed properties**:

~~~java
public abstract class GreetingExtension {
    public abstract Property<String> getRecipient();
    public abstract RegularFileProperty getOutputFile();
}
~~~

Gradle tạo implementation cho những getter trừu tượng theo JavaBeans convention. Không cần tự viết field, constructor setter và getter thông thường nếu không có lý do đặc biệt.

### 6.2. Extension không tự thực thi công việc

Việc gọi:

~~~groovy
greeting {
    recipient.set('Student')
}
~~~

chỉ cấu hình property. Nó không tạo file, không chạy task và không in lời chào. Muốn thực thi, vẫn cần chạy task mà plugin cung cấp:

~~~bash
./gradlew :app:generateGreeting
~~~

Plugin chịu trách nhiệm **nối extension property vào task property**, thường qua Provider:

~~~java
task.getRecipient().set(extension.getRecipient());
task.getOutputFile().set(extension.getOutputFile());
~~~

Không cần gọi **extension.getRecipient().get()** trong **apply**: đọc sớm có thể lấy giá trị default trước khi build script ghi đè hoặc gây lỗi khi giá trị chưa có. **set(provider)** giữ quan hệ lazy giữa extension và task.

### 6.3. Type-safe hơn map động

Một extension có **Property<String>**, **RegularFileProperty**, **DirectoryProperty**, **ListProperty<T>** hoặc **MapProperty<K,V>** cho phép:

- IDE gợi ý cấu hình phù hợp.
- Validation kiểu dữ liệu sớm hơn.
- Nguồn giá trị Provider có thể nối tới task mà không cần đọc ngay.
- Gradle theo dõi input/output khi task type khai báo đúng annotations.
- Tài liệu hóa DSL rõ ràng.

Tránh lạm dụng **ext.someValue = '...'** làm API của plugin khi một extension có kiểu sẽ dễ bảo trì hơn. Extra properties vẫn tồn tại trong Gradle nhưng không tự mang đầy đủ đặc tính của typed managed properties.

### 6.4. Một project có thể có nhiều extensions

Java plugin cung cấp **java** extension, Application plugin cung cấp **application** extension, custom plugin cung cấp **greeting**. Chúng có tên và type riêng. Không dùng hai plugins cố tạo extension cùng tên không tương thích; Gradle có thể báo name conflict hoặc hành vi DSL không rõ ràng.

## 7. Plugin cung cấp configuration: ba vai trò khác nhau

**Configuration** trong Gradle là mô hình dependency management, không phải một plugin setting object. Java plugin cung cấp nhiều configurations để người dùng khai báo và giải quyết dependencies.

| Vai trò | Dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| **Declarable / dependency scope** | Khai báo dependencies, không tự resolve hoặc publish | **implementation**, **api**, **testImplementation** |
| **Resolvable** | Tính dependency graph và lấy artifact files | **compileClasspath**, **runtimeClasspath** |
| **Consumable** | Công bố variants/artifacts cho project khác sử dụng | **apiElements**, **runtimeElements** |

Một plugin có thể tạo cả ba loại. Không phải cứ tên **configuration** thì nó dùng để tải JAR ngay; API và vai trò quyết định điều đó.

### 7.1. Configuration do Java plugin cung cấp

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-contract:1.0'
    implementation 'org.example:internal-codec:1.0'
    testImplementation 'org.example:test-helper:1.0'
}
~~~

Các tọa độ **org.example** chỉ minh họa, không phải artifact thực. **api/implementation/testImplementation** là scopes khai báo dependency. Khi compile hoặc run, Gradle resolve **compileClasspath/runtimeClasspath** tương ứng; producer có **apiElements/runtimeElements** cho consumer khác.

Plugin tạo configurations **không có nghĩa** mọi dependency sẽ được tải ngay khi plugin apply. Gradle thường trì hoãn resolution cho đến khi cần configuration.

### 7.2. Custom configurations cho công cụ phụ trợ

Giả sử plugin Greeting cần **một tập JAR của công cụ tùy chọn** nhưng không muốn đưa chúng vào classpath của Java application. Plugin có thể tạo:

- **greetingTools**: dependency scope để người dùng khai báo thư viện phục vụ tác vụ hỗ trợ.
- **greetingToolClasspath**: resolvable configuration kế thừa dependency scope, dùng làm input của task **showGreetingTools**.

Người dùng viết:

~~~groovy
dependencies {
    greetingTools 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Lệnh này **không** giống:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Đầu tiên khai báo thư viện cho configuration chuyên biệt của plugin; thứ hai đưa thư viện vào dependency scope của Java application. Chỉ cần tool path không đồng nghĩa cần thư viện trên production runtimeClasspath.

### 7.3. API tạo configurations theo vai trò

Gradle hiện đại cung cấp các factory methods hỗ trợ đặt đúng roles:

~~~java
var toolScope = project.getConfigurations()
        .dependencyScope("greetingTools");

var toolClasspath = project.getConfigurations()
        .resolvable("greetingToolClasspath");

toolClasspath.configure(configuration ->
        configuration.extendsFrom(toolScope.get()));
~~~

Đây là **đoạn trong class Plugin<Project>**, đầy đủ trong lab ở mục 9. Những methods **dependencyScope/resolvable/consumable** hiện còn được Gradle mô tả là **incubating** trên một số bản Gradle; bài thực hành dùng **Gradle 9.x** hỗ trợ APIs này. Nếu dự án dùng Gradle cũ không có factory, cần dùng **configurations.register** và đặt đúng các cờ **canBeDeclared**, **canBeResolved**, **canBeConsumed** theo API của bản đó.

Một configuration chỉ nên có **một vai trò chính**. Không tạo một custom configuration rồi để nó vừa declarable, vừa resolvable, vừa consumable chỉ vì API legacy mặc định bật nhiều cờ.

### 7.4. Configuration inheritance không làm tất cả scopes giống nhau

**greetingToolClasspath** kế thừa dependencies từ **greetingTools**, nhưng đó là quan hệ có chủ đích do plugin thiết kế. Nó không đồng nghĩa **greetingTools** tự trở thành implementation hoặc runtime dependency của ứng dụng.

Nếu gọi:

~~~groovy
configurations.implementation.resolve()
~~~

Gradle hiện đại có thể báo lỗi vì **implementation** là dependency scope, không phải resolvable configuration. Để xem JAR trên classpath ứng dụng, dùng:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Còn để xem công cụ của plugin, dùng:

~~~bash
./gradlew :app:dependencies --configuration greetingToolClasspath
~~~

### 7.5. Consumable configurations và variants

Plugin tạo library hoặc code generator có thể công bố **consumable configuration** cùng artifact/attributes để project khác chọn variant phù hợp. Java Library Plugin đã có **apiElements** và **runtimeElements**; một plugin đơn giản không nhất thiết phải tạo thêm consumable variant.

Bài thực hành Greeting chỉ cần declarable và resolvable custom configurations. Không tự thêm một consumable configuration không có artifact hoặc usage rõ ràng chỉ để đủ ba vai trò.

## 8. Plugin cung cấp quy ước: hai nghĩa của chữ convention

### 8.1. Convention của một Property

Trong custom plugin:

~~~java
extension.getRecipient().convention("Gradle");

extension.getOutputFile().convention(
        project.getLayout().getBuildDirectory()
                .file("generated/greeting.txt"));
~~~

**convention(...)** cung cấp giá trị mặc định, chỉ được sử dụng khi chưa có giá trị khác ghi đè theo mô hình Property. Người dùng có thể viết:

~~~groovy
greeting {
    recipient.set('Java 17')
}
~~~

Với module không ghi đè, recipient vẫn là **Gradle**. Với module ghi đè, recipient là **Java 17**. Đây là **convention mặc định**, không phải một ràng buộc cứng.

**set(...)** thiết lập giá trị nguồn; **convention(...)** đặt default có thể bị thay. Nếu viết trong plugin:

~~~java
extension.getRecipient().set("Gradle");
~~~

thì property được thiết lập như một giá trị thực ban đầu thay vì chỉ một convention. Nó vẫn có thể được người dùng thay đổi trong nhiều tình huống, nhưng ý nghĩa khác; không dùng **set** thay **convention** khi muốn truyền đạt chính sách mặc định rõ ràng.

### 8.2. Convention plugin như một loại build logic

**Convention plugin** là plugin chuyên áp dụng hoặc cấu hình các plugins khác theo chuẩn của nhóm: Java toolchain, JUnit, code style, compiler flags, publishing policy, task groups. Nó là một **plugin**, không phải cùng thứ với method **Property.convention**.

Ví dụ code trong một convention plugin Java:

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
~~~

Đây là **đoạn Groovy DSL minh họa nội dung convention**, không phải một precompiled plugin được đăng ký đầy đủ. Nếu được đóng gói đúng, nó có thể chuẩn hóa cách biên dịch Java của nhiều module.

### 8.3. Quy ước tốt phải ghi đè được khi cần

- Đặt **toolchain Java 17** theo chuẩn nhóm nếu các module cùng target.
- Đặt **buildDirectory** cho generated outputs thay vì ghi vào source tree.
- Đặt mặc định **recipient** thay vì bắt tất cả module cung cấp một chuỗi mới.
- Dùng **Provider** để cho phép giá trị đến từ Gradle properties, môi trường hoặc task outputs khi phù hợp.
- Chỉ cưỡng chế thật sự khi đó là policy kỹ thuật rõ ràng (ví dụ bảo mật); phân biệt **default** với **rule không cho ghi đè**.

Nếu plugin cố khóa tất cả property bằng finalize/disallowChanges quá sớm, người dùng khó cấu hình extension trong project build script; đừng làm vậy nếu không có yêu cầu rõ.

## 9. Ví dụ chạy được: plugin Java 17 cung cấp đủ bốn thành phần

Ta tạo một plugin **demo.greeting** trong **buildSrc**, dùng Java 17. Plugin sẽ:

1. Tạo **greeting** extension với **recipient** và **outputFile**.
2. Đặt convention **recipient = Gradle**, output **build/generated/greeting.txt**.
3. Tạo custom configurations **greetingTools** và **greetingToolClasspath**.
4. Đăng ký task **generateGreeting** có input/output được Gradle theo dõi.
5. Đăng ký task **showGreetingTools** để xem các JAR trong classpath công cụ.
6. Được áp dụng vào cả **:core** và **:app**, với :app ghi đè extension, còn :core giữ default.
7. Cho phép chạy ứng dụng Java thuần ở :app để phân biệt **Gradle build logic** với **Java application logic**.

### 9.1. Cấu trúc thư mục

~~~text
plugin-contract-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── buildSrc/
│   ├── build.gradle
│   └── src/main/java/demo/build/
│       ├── GreetingExtension.java
│       ├── GenerateGreetingTask.java
│       ├── ShowGreetingToolsTask.java
│       └── GreetingPlugin.java
├── core/
│   ├── build.gradle
│   └── src/main/java/demo/core/Message.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
~~~

**Gradle Wrapper:** Nếu bắt đầu project mới, tạo wrapper một lần bằng bản Gradle CLI phù hợp (**gradle wrapper**) rồi dùng **./gradlew** hoặc **.\gradlew.bat**. Demo sử dụng API factory configurations được hỗ trợ trong **Gradle 9.x**, **Java toolchain 17** và **Java source 17**. Cần JDK phù hợp để chạy Gradle và JDK 17 toolchain có sẵn hoặc được cung cấp bằng cấu hình provisioning.

**buildSrc** là build logic đặc biệt, được Gradle biên dịch để class/plugin descriptor của nó xuất hiện trên classpath của main build. Không phải include **':buildSrc'** như một subproject của ứng dụng.

### 9.2. settings.gradle

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}

rootProject.name = 'plugin-contract-lab'
include ':core', ':app'
~~~

Maven Central phục vụ dependency **org.apache.commons:commons-lang3:3.17.0** mà task tùy chọn của demo dùng. Plugin **demo.greeting** lấy trực tiếp từ **buildSrc**, không cần thêm plugin repository để resolve ID demo.greeting.

**FAIL_ON_PROJECT_REPOS** làm việc đặt repository trong subproject trái chính sách bị báo lỗi. Vì vậy các build.gradle bên dưới không khai báo repositories.

### 9.3. build.gradle ở root

~~~groovy
plugins {
    id 'base'
}

tasks.register('greetAll') {
    group = 'demo'
    description = 'Tạo lời chào ở hai subproject'
    dependsOn ':core:generateGreeting', ':app:generateGreeting'
}
~~~

Task tổng hợp chỉ khai báo dependency. Plugin **demo.greeting** không được áp dụng ở root, do đó root không tự có extension **greeting** hoặc task **generateGreeting**. **greetAll** lại có thể chạy task của các subproject bằng task paths.

### 9.4. buildSrc/build.gradle

~~~groovy
plugins {
    id 'java-gradle-plugin'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

gradlePlugin {
    plugins {
        greetingPlugin {
            id = 'demo.greeting'
            implementationClass = 'demo.build.GreetingPlugin'
        }
    }
}
~~~

**java-gradle-plugin** giúp biên dịch plugin Java, thêm Gradle API theo cấu hình phù hợp, sinh plugin descriptor và thực hiện một số validations. Block **gradlePlugin.plugins** ánh xạ ID **demo.greeting** tới **GreetingPlugin**. Không cần tự ghi file **META-INF/gradle-plugins/demo.greeting.properties** trong mô hình này.

### 9.5. buildSrc/src/main/java/demo/build/GreetingExtension.java

~~~java
package demo.build;

import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;

public abstract class GreetingExtension {
    public abstract Property<String> getRecipient();
    public abstract RegularFileProperty getOutputFile();
}
~~~

Class là **abstract** với hai managed properties. Gradle tạo implementation phù hợp khi **extensions.create(...)** được gọi. Tên getter phải theo JavaBeans convention **getRecipient**, **getOutputFile** để Gradle biết cách quản lý chúng.

### 9.6. buildSrc/src/main/java/demo/build/GenerateGreetingTask.java

~~~java
package demo.build;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

public abstract class GenerateGreetingTask extends DefaultTask {

    @Input
    public abstract Property<String> getRecipient();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();

    @TaskAction
    public void generateGreeting() throws IOException {
        String recipient = getRecipient().get();
        Path destination = getOutputFile().get().getAsFile().toPath();

        Path parent = destination.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        String content = "Xin chào, " + recipient + "!\n";
        Files.writeString(
                destination,
                content,
                StandardCharsets.UTF_8);

        System.out.println("GENERATED=" + destination.getFileName());
    }
}
~~~

Mục tiêu code:

- **@Input** theo dõi thay đổi recipient.
- **@OutputFile** theo dõi file kết quả.
- **@TaskAction** chạy khi task thật sự được thực thi.
- **Files.createDirectories** đảm bảo output directory tồn tại.
- **Files.writeString** với UTF-8 tạo file Unicode tiếng Việt có newline cuối.
- Task action không gọi **getProject()**, không sửa Project model và không resolve configuration khác; thuận lợi hơn cho configuration cache.
- Nếu input/output không đổi và Gradle xác định task up-to-date, task action có thể không chạy lần thứ hai. Đó là đúng, không phải plugin bị hỏng.

### 9.7. buildSrc/src/main/java/demo/build/ShowGreetingToolsTask.java

~~~java
package demo.build;

import java.io.File;
import java.util.List;
import org.gradle.api.DefaultTask;
import org.gradle.api.file.ConfigurableFileCollection;
import org.gradle.api.tasks.Classpath;
import org.gradle.api.tasks.TaskAction;

public abstract class ShowGreetingToolsTask extends DefaultTask {

    @Classpath
    public abstract ConfigurableFileCollection getToolFiles();

    @TaskAction
    public void showTools() {
        List<String> names = getToolFiles()
                .getFiles()
                .stream()
                .map(File::getName)
                .sorted()
                .toList();

        String description = names.isEmpty()
                ? "(none)"
                : String.join(",", names);

        System.out.println("TOOLS=" + description);
    }
}
~~~

**@Classpath** thể hiện input là tập file thuộc classpath, để Gradle có thể theo dõi thay đổi phù hợp. Task này không đóng gói JAR, không tải dependency để chạy Java source ứng dụng; nó chỉ xem tên các file được resolve trong **greetingToolClasspath**.

**Stream.toList()** được Java 17 hỗ trợ. Nếu configuration không có dependency, task in **TOOLS=(none)**. Nếu chứa Apache Commons Lang 3.17.0, output thường chứa tên JAR **commons-lang3-3.17.0.jar**; số lượng tên sẽ thay đổi khi bạn bổ sung các dependencies transitive khác.

### 9.8. buildSrc/src/main/java/demo/build/GreetingPlugin.java

~~~java
package demo.build;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class GreetingPlugin implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        GreetingExtension extension = project.getExtensions()
                .create("greeting", GreetingExtension.class);

        extension.getRecipient().convention("Gradle");
        extension.getOutputFile().convention(
                project.getLayout()
                        .getBuildDirectory()
                        .file("generated/greeting.txt"));

        var toolScope = project.getConfigurations()
                .dependencyScope("greetingTools");

        var toolClasspath = project.getConfigurations()
                .resolvable("greetingToolClasspath");

        toolClasspath.configure(configuration ->
                configuration.extendsFrom(toolScope.get()));

        project.getTasks().register(
                "generateGreeting",
                GenerateGreetingTask.class,
                task -> {
                    task.setGroup("demo");
                    task.setDescription("Tạo file lời chào UTF-8");
                    task.getRecipient().set(extension.getRecipient());
                    task.getOutputFile().set(extension.getOutputFile());
                });

        project.getTasks().register(
                "showGreetingTools",
                ShowGreetingToolsTask.class,
                task -> {
                    task.setGroup("demo");
                    task.setDescription("Liệt kê JARs của greetingToolClasspath");
                    task.getToolFiles().from(toolClasspath.get());
                });
    }
}
~~~

Bốn trách nhiệm của plugin hiện rõ:

1. **Extension:** **extensions.create("greeting", GreetingExtension.class)**.
2. **Conventions:** **recipient.convention("Gradle")** và outputFile mặc định dưới build directory.
3. **Configurations:** **dependencyScope("greetingTools")**, **resolvable("greetingToolClasspath")**, nối bằng **extendsFrom(...)**.
4. **Tasks:** đăng ký **generateGreeting** và **showGreetingTools** bằng **tasks.register**.

**Tại sao dùng toolClasspath.get() trong action cấu hình task thay vì ngay trong apply?** Closure của **tasks.register** chỉ chạy khi task được cấu hình, tránh cưỡng bức lấy configuration cho mọi lời gọi Gradle. **get()** trong vùng cấu hình task lấy đối tượng Configuration, không resolve artifact ngay; việc đọc **getFiles()** trong TaskAction **showTools** mới yêu cầu các file thực.

**Tại sao không gọi extension.getRecipient().get() trong apply?** Người dùng có thể ghi đè extension ở build.gradle sau lúc plugin apply. Bằng cách **task.getRecipient().set(extension.getRecipient())**, task giữ một Provider kết nối với giá trị extension được cấu hình.

**Không giữ Project trong TaskAction**: class task chỉ dùng managed properties đã được Gradle truyền vào nó, giúp tránh những lỗi phổ biến của configuration cache.

### 9.9. core/build.gradle

~~~groovy
plugins {
    id 'java-library'
    id 'demo.greeting'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Module **:core** áp dụng plugin nhưng **không** ghi đè block **greeting**. Vì vậy:

- **:core:generateGreeting** dùng recipient default là **Gradle**.
- Output mặc định là **core/build/generated/greeting.txt**.
- **:core:showGreetingTools** không có dependency khai báo, nếu chạy sẽ in **TOOLS=(none)**.

Java Library Plugin còn tạo **compileJava**, **jar**, **test**, extension **java** và các configurations **implementation**, **api**, **runtimeClasspath**... Đây là những đóng góp **của java-library**, không phải của demo.greeting.

### 9.10. core/src/main/java/demo/core/Message.java

~~~java
package demo.core;

public final class Message {
    private Message() {
    }

    public static String format(String name) {
        return "Java 17: Xin chào, " + name + "!";
    }
}
~~~

Đây là logic ứng dụng Java độc lập. Plugin Greeting không sửa class Message và không cần load class này trong apply().

### 9.11. app/build.gradle

~~~groovy
plugins {
    id 'application'
    id 'demo.greeting'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':core')

    greetingTools 'org.apache.commons:commons-lang3:3.17.0'
}

application {
    mainClass = 'demo.app.Main'
}

greeting {
    recipient.set('Java 17')
    outputFile.set(
            layout.buildDirectory.file('generated/app-hello.txt'))
}
~~~

Ở đây:

- **application** cung cấp extension application, task run và các khả năng Java.
- **demo.greeting** cung cấp **greeting** extension và hai task.
- **implementation project(':core')** là dependency cho Java application, cho phép Main dùng Message.
- **greetingTools 'org.apache.commons:commons-lang3:3.17.0'** là dependency nằm trong custom configuration của plugin; nó **không** tự trở thành Java application implementation.
- **greeting { ... }** ghi đè hai conventions của plugin riêng cho :app.
- **app/build/generated/app-hello.txt** thuộc output của :app, không đụng output của :core.
- Plugin không tự thêm **generateGreeting** vào task **run**; task làm việc độc lập trừ khi ta khai báo dependency rõ.

### 9.12. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.core.Message;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Message.format("Gradle"));
    }
}
~~~

Java source chỉ phụ thuộc **Message** qua **project(':core')**, không phụ thuộc custom Gradle plugin API lúc runtime.

## 10. Chạy ví dụ và kiểm tra đầu ra

### 10.1. Lệnh Gradle trên Linux/macOS

~~~bash
./gradlew --version
./gradlew projects
./gradlew :core:tasks --all
./gradlew :app:tasks --all
./gradlew --rerun-tasks -q greetAll
./gradlew -q :core:showGreetingTools
./gradlew -q :app:showGreetingTools
./gradlew -q :app:run
./gradlew :app:dependencies --configuration greetingToolClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Lệnh **greetAll** yêu cầu hai task **:core:generateGreeting** và **:app:generateGreeting**. Với **--rerun-tasks**, task actions được yêu cầu chạy lại thay vì được coi là UP-TO-DATE. Các dòng do task actions của ví dụ in, thứ tự giữa hai project có thể khác:

~~~text
GENERATED=greeting.txt
GENERATED=app-hello.txt
~~~

Đọc nội dung hai file:

~~~bash
cat core/build/generated/greeting.txt
cat app/build/generated/app-hello.txt
~~~

Stdout từ hai lệnh đọc file lần lượt là:

~~~text
Xin chào, Gradle!
Xin chào, Java 17!
~~~

**:core:showGreetingTools** với configuration chưa khai báo dependency sẽ in:

~~~text
TOOLS=(none)
~~~

**:app:showGreetingTools** sẽ in danh sách JAR chứa tên **commons-lang3-3.17.0.jar** khi Maven Central hoặc cache/mirror đã cung cấp artifact. Với dependency này và metadata thông thường, dòng dự kiến là:

~~~text
TOOLS=commons-lang3-3.17.0.jar
~~~

Nếu kho/metadata hoặc dependency graph thay đổi, danh sách có thể khác; đừng gắn logic sản phẩm với chuỗi tên JAR in ra chỉ để demo.

**:app:run** chạy chương trình Java 17 và stdout chính xác của main method là:

~~~text
Java 17: Xin chào, Gradle!
~~~

Gradle có thể in thêm thông tin daemon, tasks, logs hoặc **BUILD SUCCESSFUL**. Các block stdout trên chỉ mô tả những dòng do code ví dụ chủ động in, không phải toàn bộ console output.

### 10.2. Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :core:tasks --all
.\gradlew.bat :app:tasks --all
.\gradlew.bat --rerun-tasks -q greetAll
.\gradlew.bat -q :core:showGreetingTools
.\gradlew.bat -q :app:showGreetingTools
.\gradlew.bat -q :app:run
.\gradlew.bat :app:dependencies --configuration greetingToolClasspath
.\gradlew.bat :app:dependencies --configuration runtimeClasspath

Get-Content core\build\generated\greeting.txt
Get-Content app\build\generated\app-hello.txt
~~~

Nếu PowerShell hiển thị tiếng Việt sai, kiểm tra encoding console/font; file do **Files.writeString(..., UTF_8)** tạo ra có UTF-8. Không tự thay đổi source string/encoding chỉ để phù hợp một console cấu hình sai.

### 10.3. Kiểm chứng Java 17 độc lập với Gradle

Lớp **Message** và **Main** không dùng Gradle API; có thể biên dịch trực tiếp:

~~~bash
mkdir -p out

javac --release 17 -d out \
    core/src/main/java/demo/core/Message.java \
    app/src/main/java/demo/app/Main.java

java -cp out demo.app.Main
~~~

Stdout:

~~~text
Java 17: Xin chào, Gradle!
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out core\src\main\java\demo\core\Message.java app\src\main\java\demo\app\Main.java
java -cp out demo.app.Main
~~~

Lệnh **javac/java** chỉ xác minh source code ứng dụng; **không chứng minh plugin cung cấp đúng tasks/extensions/configurations/conventions**. Để kiểm chứng bốn phần đó, dùng **Gradle Wrapper** và các lệnh ở mục 10.1–10.2.

### 10.4. Phân biệt lời chào do task tạo với stdout của app

Lời chào do plugin tạo:

~~~text
core/build/generated/greeting.txt = Xin chào, Gradle!
app/build/generated/app-hello.txt = Xin chào, Java 17!
~~~

Lời chào do chương trình Java khi chạy ứng dụng:

~~~text
Java 17: Xin chào, Gradle!
~~~

Hai phần này có chủ đích tách biệt. Plugin Greeting **không** tự làm ứng dụng Java đọc output task. Muốn app cần file đó, phải mô hình hóa file input và dependency task producer–consumer một cách rõ ràng.

## 11. Plugin application, task discovery và dependency graph

### 11.1. Tìm tác vụ đến từ plugin nào

Các lệnh:

~~~bash
./gradlew :core:tasks --all
./gradlew :app:tasks --all
./gradlew help --task :app:generateGreeting
~~~

giúp xem tasks được đăng ký. **generateGreeting** và **showGreetingTools** do demo.greeting cung cấp; **compileJava**, **jar**, **test** do Java plugin/application plugin cung cấp; **run** do Application plugin cung cấp.

Không suy rằng tất cả tasks hiển thị trong **tasks --all** đều được thực thi. Task registration và task execution là hai việc khác nhau.

### 11.2. Plugin không mặc định tự móc task vào build

Plugin có thể tạo **generateGreeting** mà không nối nó vào **build**, **assemble** hay **run**. Đó là lựa chọn kiến trúc có chủ đích: task có thể tùy chọn.

Nếu nghiệp vụ muốn một task phụ thuộc vào generateGreeting, hãy đặt quan hệ:

~~~groovy
tasks.named('run') {
    dependsOn tasks.named('generateGreeting')
}
~~~

Đây là **đoạn minh họa bổ sung**, áp dụng trong module đã có cả task **run** và **generateGreeting**. Nhưng chỉ nên thêm nếu chạy app thực sự cần file generated. Nếu ứng dụng không đọc file ấy, thêm dependsOn chỉ làm tăng công việc không cần.

### 11.3. Plugin tự áp dụng plugin khác

Một custom plugin có thể chọn:

~~~java
project.getPluginManager().apply("java");
~~~

để bảo đảm Java plugin có mặt, hoặc chỉ hỗ trợ những project đã có Java plugin. Đây là một **đoạn minh họa trong method apply**; không cần cho plugin Greeting vì nó không đòi Java plugin để tạo file lời chào. Trong demo, chính các subproject tự áp dụng java-library/application.

Không tự áp dụng plugin nặng vào tất cả modules nếu task của plugin không cần nó.

### 11.4. Đúng thứ tự nhưng không phụ thuộc thứ tự ngầm

Nếu một plugin cần chỉnh sửa Java extension hoặc Java tasks, dùng **pluginManager.withPlugin('java') { ... }** để đợi plugin Java, thay vì gọi thẳng **tasks.getByName('compileJava')** trong apply() và hy vọng người dùng luôn liệt kê plugin Java trước.

Với Groovy DSL:

~~~groovy
pluginManager.withPlugin('java') {
    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }
}
~~~

Đoạn này minh họa cấu hình có điều kiện; JavaCompile tasks chỉ tồn tại khi plugin Java ecosystem phù hợp.

## 12. Configuration roles và lý do tách công cụ khỏi app runtime

Trong lab, **:app** có hai dependency paths độc lập:

~~~text
                                :app
                                 |
                    +------------+-------------+
                    |                          |
                    v                          v
              implementation               greetingTools
                    |                          |
                    v                          v
             runtimeClasspath          greetingToolClasspath
                    |                          |
                    v                          v
             task :app:run             task showGreetingTools
                    |                          |
                    v                          v
             :core code/library          Commons Lang JAR
~~~

**Điều không nên làm:** đặt mọi JAR phục vụ plugin build-time vào **implementation**. Khi đó ứng dụng production có thể mang theo công cụ không cần thiết, tăng runtime classpath và khiến API của module có thể phụ thuộc nhầm vào công cụ build.

**Điều nên làm:** khai báo custom dependency scope cho công cụ, resolvable classpath cho task cần nó, và gắn file collection đó làm input của task qua **@Classpath**. Đây là mẫu thiết kế phổ biến ở plugin code generator, static analysis, doc generator, compiler helper hoặc artifact transform.

### 12.1. Không resolve configuration trong apply

Một antipattern:

~~~java
public void apply(Project project) {
    var files = project.getConfigurations()
            .getByName("runtimeClasspath")
            .getFiles();
}
~~~

Đây là **đoạn cố ý sai về thời điểm**. Trong apply(), build script chưa chắc đã khai báo toàn bộ dependencies; resolve quá sớm có thể khóa metadata, chậm initialization/configuration và gây lỗi nếu plugin khác còn cấu hình classpath.

Thay vào đó, task nhận **Provider/Configuration/FileCollection** như input, và Gradle resolve khi task cần. Lab đặt file collection trong task property **getToolFiles()**, tránh resolve tất cả công cụ chỉ vì plugin được áp dụng.

### 12.2. Không gọi project.repositories nếu policy cấm

Một plugin tự thêm repository:

~~~java
project.getRepositories().mavenCentral();
~~~

có thể gây lỗi với **RepositoriesMode.FAIL_ON_PROJECT_REPOS**. Đây là snippet minh họa hành vi cần cân nhắc, **không** xuất hiện trong plugin Greeting. Plugin tác giả thường nên để người dùng/tổ chức kiểm soát dependency repositories trong settings thay vì âm thầm thêm nguồn tải.

## 13. Conventions, override và giá trị cuối

### 13.1. Hai project dùng cùng plugin nhưng cấu hình khác

**:core**:

~~~groovy
plugins {
    id 'demo.greeting'
}
~~~

không ghi đè extension, nên dùng:

~~~text
recipient = Gradle
outputFile = core/build/generated/greeting.txt
~~~

**:app**:

~~~groovy
plugins {
    id 'demo.greeting'
}

greeting {
    recipient.set('Java 17')
    outputFile.set(layout.buildDirectory.file('generated/app-hello.txt'))
}
~~~

nên dùng:

~~~text
recipient = Java 17
outputFile = app/build/generated/app-hello.txt
~~~

Đây là giá trị theo project-specific extensions. Plugin không dùng một static variable dùng chung giữa :core và :app.

### 13.2. get() quá sớm có thể gây lỗi

Đoạn không nên dùng trong apply():

~~~java
String recipient = extension.getRecipient().get();
~~~

Ngay cả khi plugin đã đặt default, việc lấy recipient sớm làm mất tính lazy của wiring và có thể khiến task không theo đúng giá trị người dùng set sau này nếu bạn chụp giá trị vào biến cứng.

Mẫu trong lab:

~~~java
task.getRecipient().set(extension.getRecipient());
~~~

giữ Provider, để Gradle lấy giá trị khi task thực sự cần.

### 13.3. Override task property và extension property

Nếu người dùng muốn một task cụ thể khác default:

~~~groovy
tasks.named('generateGreeting', GenerateGreetingTask) {
    recipient.set('Chỉ riêng task')
}
~~~

đây là snippet minh họa, cần type **GenerateGreetingTask** có trên buildscript classpath. Nó thay cấu hình input của task đó mà không nhất thiết thay extension **greeting.recipient**. Trong tài liệu API plugin, cần làm rõ đâu là nguồn cấu hình chính và đâu là task-level override để tránh bất đồng giữa các task.

### 13.4. Khi nào cần validation?

Nếu recipient rỗng thì thông báo tạo ra có thể không có nghĩa. Plugin có thể:

- Validate trong task action và ném **GradleException** với lỗi rõ ràng.
- Dùng type có ràng buộc thích hợp, thay vì String tự do nếu domain cần.
- Không im lặng biến input sai thành một output trông hợp lệ.

**Không tự đọc environment variables, secrets hoặc filesystem tùy tiện trong apply()** chỉ để validate; ưu tiên Provider API và input properties có kiểm soát.

## 14. Cấu hình plugin qua Kotlin DSL

Định nghĩa plugin trong Java không bắt buộc consumer phải dùng Groovy DSL. Nếu người dùng viết **app/build.gradle.kts**, các phần ứng dụng tương đương về ý nghĩa:

~~~kotlin
plugins {
    application
    id("demo.greeting")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":core"))
    add("greetingTools", "org.apache.commons:commons-lang3:3.17.0")
}

application {
    mainClass.set("demo.app.Main")
}

configure<demo.build.GreetingExtension> {
    recipient.set("Java 17")
    outputFile.set(layout.buildDirectory.file("generated/app-hello.txt"))
}
~~~

Đây là snippet Kotlin DSL **minh họa cấu hình tương đương**, không thể ghép đồng thời với **app/build.gradle** cùng project vì hai files là hai lựa chọn. Với plugin ở buildSrc, Gradle có class **demo.build.GreetingExtension** trên classpath project scripts.

Trong Kotlin DSL, nếu extension có name **greeting**, người dùng cũng có thể cấu hình qua typed extension function khi accessor được tạo; việc dùng **configure<...>** trực tiếp cho thấy extension type mà không dựa vào giả định IDE đã sinh đúng accessor. Với custom configuration, **add("greetingTools", "...")** là cú pháp an toàn nếu chưa có Kotlin accessor convenience.

Không lấy cú pháp Groovy **greeting { recipient = '...' }** rồi dán nguyên vào file .gradle.kts.

## 15. Plugin binary, convention plugin, script plugin và nguồn phân phối

| Kiểu | Cách dùng | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| **Core plugin** | **id 'java'**, **id 'application'** | Có sẵn trong Gradle, API/tooling ổn định theo bản Gradle | Vẫn cần chọn plugin đúng loại module |
| **External binary plugin** | **id 'vendor.plugin' version 'x.y'** | Được xuất bản, chia sẻ giữa repositories | Cần plugin repository, version và trust policy |
| **Custom binary plugin** | **id 'demo.greeting'** từ buildSrc/build-logic/plugin artifact | API có kiểu, test/validation, cấu trúc tốt | Cần build logic và Gradle API tương thích |
| **Precompiled script/convention plugin** | **id 'my.java-conventions'** | Dễ gom chuẩn Gradle DSL dùng chung | Cần đặt file/build logic đúng cách |
| **Legacy script plugin** | **apply from: 'common.gradle'** | Nhanh cho code cũ | Ít được khuyến nghị cho logic lớn, dễ phụ thuộc thứ tự và thiếu API ổn định |

Gradle tài liệu hiện đại khuyến nghị plugin build logic có cấu trúc, convention plugins và lazy APIs thay vì nhân bản **allprojects { ... }** hoặc sử dụng legacy script plugin cho hệ thống lớn.

### 15.1. Không nhầm plugin API và project API

Một plugin không tự sở hữu một Project global. **apply(Project project)** được gọi với project cụ thể. Nếu plugin có mutable static state và dùng giữa nhiều projects, có thể gây concurrency/caching bugs. Dùng Task properties hoặc Build Service khi cần tài nguyên chia sẻ hợp lệ.

### 15.2. Khi nào đưa buildSrc sang build-logic?

**buildSrc** đơn giản và tự có trên build classpath, phù hợp demo. Ở monorepo, build logic trong included build **build-logic** thường giúp xây dựng ranh giới và caching rõ hơn, hỗ trợ convention plugins chuyên biệt, tránh buildSrc phình to.

Việc di chuyển cần tạo **settings.gradle** riêng cho build-logic, đăng ký plugin đúng ID, thêm **pluginManagement { includeBuild('build-logic') }** khi phù hợp và giữ repositories/classpaths nhất quán. Không chỉ di chuyển thư mục rồi mong Gradle tự tìm ra plugin ID.

## 16. Plugin, configuration cache và tính đúng đắn

### 16.1. Hạn chế side effects trong apply()

Không thực hiện những việc này ở configuration chỉ vì plugin được áp dụng:

- Gọi HTTP request để kiểm tra thông tin build.
- Mở server, database hoặc socket dùng cho nhiều tasks.
- Resolve toàn bộ runtimeClasspath khi dependencies chưa được khai báo xong.
- Sinh file output business ngay khi người dùng chỉ chạy **help**.
- Duyệt mọi task và gọi **get()** để ép hiện thực.
- Đọc biến môi trường bí mật rồi in vào log.

Những hành vi đó chậm, khó tái lập và có thể xung đột với configuration cache.

Mô hình của lab đặt công việc viết file vào **GenerateGreetingTask.@TaskAction** và đặt các giá trị qua **Property**. Task **showGreetingTools** chỉ lấy classpath khi thực thi; plugin **apply** chủ yếu tạo model.

### 16.2. UP-TO-DATE khác plugin không áp dụng

Khi chạy:

~~~bash
./gradlew :app:generateGreeting
./gradlew :app:generateGreeting
~~~

lần thứ hai task có thể **UP-TO-DATE** và không in **GENERATED=...**, vì input/output không thay đổi. Điều đó không có nghĩa extension mất đi hoặc plugin chưa apply.

Có thể quan sát trong log thường:

~~~text
> Task :app:generateGreeting UP-TO-DATE
~~~

Nếu xóa file output hoặc đổi **recipient**, task sẽ phải được xét chạy lại. Dùng **--rerun-tasks** để thử action nhưng không dùng liên tục trong CI bình thường.

### 16.3. Configuration cache khác build cache

- **Configuration cache** lưu/tái sử dụng kết quả configuration khi đủ điều kiện.
- **Up-to-date checks** bỏ qua action khi input/output phù hợp trạng thái trước.
- **Build cache** có thể tái sử dụng outputs của task cacheable đủ điều kiện.
- **Task configuration avoidance** giảm việc hiện thực/cấu hình tasks không cần.

Những cơ chế khác nhau. Việc dùng **tasks.register** không tự đảm bảo configuration cache compatibility; việc khai báo **@OutputFile** không tự làm mọi task cacheable.

Thử:

~~~bash
./gradlew --configuration-cache :app:generateGreeting
./gradlew --configuration-cache :app:generateGreeting
~~~

Đọc warning/báo cáo lỗi nếu plugin custom truy cập state không được hỗ trợ. Trong lab, task action được thiết kế chỉ dùng managed inputs/outputs, thuận lợi cho configuration cache.

### 16.4. Xác thực plugin bằng validatePlugins

Gradle Plugin Development Plugin cung cấp task validation cho các type của plugin:

~~~bash
./gradlew -p buildSrc validatePlugins
~~~

Đối với một số cấu trúc buildSrc, task này giúp phát hiện getter task chưa có annotation, vấn đề task properties hoặc API build logic. Không tuyên bố **validatePlugins** đảm bảo mọi hành vi business, caching và concurrency đều đúng. Cần cả functional tests/Gradle TestKit khi plugin trở thành phần quan trọng trong CI.

## 17. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **Plugin with id 'demo.greeting' not found** | Chưa có descriptor/class trong buildSrc, sai id hoặc build logic compile lỗi | Kiểm tra buildSrc/build.gradle, gradlePlugin registration, class name và lỗi buildSrc |
| **Could not find method greeting()** | Plugin chưa áp dụng trong project hoặc extension tên khác | Kiểm tra **plugins { id 'demo.greeting' }** và **extensions.create("greeting", ...)** |
| **Could not get unknown property recipient** | Tên managed getter sai hoặc dùng cú pháp sai DSL | Kiểm tra **getRecipient()** và Groovy/Kotlin syntax |
| **Task 'generateGreeting' not found** | Plugin áp dụng ở project khác, task được đăng ký có điều kiện hoặc sai task path | Dùng **:app:tasks --all** và đúng project |
| **Configuration with name 'greetingTools' not found** | Plugin chưa apply, tên scope sai hoặc registration lỗi | Kiểm tra **dependencyScope("greetingTools")** và nơi viết dependencies |
| **Cannot resolve configuration implementation** | **implementation** là dependency scope, không phải resolvable | Dùng **runtimeClasspath/compileClasspath** hoặc custom resolvable config |
| Không resolve **greetingToolClasspath** | Repository, DNS, TLS, version hoặc credentials có vấn đề | Kiểm tra Maven Central/mirror, báo lỗi resolution chính xác |
| Lỗi **No value available** | Task property thiếu convention hoặc chưa set | Thêm **convention** hoặc cấu hình extension input bắt buộc |
| File được tạo ở đường dẫn lạ | buildDirectory thay đổi hoặc extension outputFile bị override | In/kiểm tra property, không hardcode **projectDir/build** |
| Task luôn chạy dù input không đổi | Không khai báo đúng input/output hoặc tác động side effect | Dùng @Input/@OutputFile, tránh ghi file ngoài mô hình |
| Task không in log ở lần chạy hai | UP-TO-DATE hoặc cache, không phải plugin mất | Dùng task report, kiểm tra file output; --rerun-tasks nếu muốn quan sát action |
| Plugin làm **help** chậm | Resolve dependency/IO/get task trong apply | Chuyển sang Provider, register, task actions |
| **A task's properties are not valid** | Getter custom task thiếu annotation hoặc annotation sai | Chạy **validatePlugins**, sửa managed properties |
| **Configuration cache problems found** | Task action truy cập Project hoặc state không hỗ trợ | Chuyển dữ liệu qua Property, tách config khỏi execution |
| Plugin tự thêm Maven repo gây FAIL mode | Vi phạm centralized repositories | Đưa repository hợp lệ vào settings, không che policy |
| **No matching variant** khi lấy JAR | Sai attributes/capability của producer/consumer | Kiểm tra outgoing/resolvable configurations và metadata |
| **Java 17 toolchain not found** | JDK 17 chưa có/provisioning chưa cấu hình | Cài/cấu hình Java toolchain đúng, không giả version |
| Dependency task chạy nhưng không có output | Task chưa tạo file, bị SKIPPED hoặc consumer thiếu dependency | Mô tả @OutputFile/@InputFile và wiring task |
| Hai modules dùng chung một recipient ngoài ý muốn | Plugin dùng mutable static/global thay vì per-Project extension | Dùng Project-scoped extension và Properties |

### 17.1. Quy trình kiểm tra từ ngoài vào trong

~~~text
Task, extension hoặc configuration không tồn tại?
             |
             v
1. Đúng Project path và đúng Gradle Wrapper?
             |
             v
2. Plugin ID có được resolve và apply vào project đó?
             |
             v
3. Nếu plugin tự viết: buildSrc/build-logic đã build được?
             |
             v
4. Plugin.apply tạo extension, configuration, task name nào?
             |
             v
5. Project build.gradle có cấu hình extension hợp lệ?
             |
             v
6. Dependency scope có tồn tại, đang resolve đúng configuration?
             |
             v
7. Task được chọn trong graph, inputs/outputs đầy đủ?
             |
             v
8. Xem stdout, log, task outcome và configuration cache warnings
~~~

Lệnh chẩn đoán:

~~~bash
./gradlew --version
./gradlew projects
./gradlew :app:tasks --all
./gradlew help --task :app:generateGreeting
./gradlew :app:dependencies --configuration greetingToolClasspath
./gradlew :app:generateGreeting --info
./gradlew :app:generateGreeting --stacktrace
./gradlew -p buildSrc validatePlugins
~~~

Khi có lỗi thực, đọc **exception đầu tiên cùng nguyên nhân gốc**, không xóa **~/.gradle** hoặc thêm repository tùy tiện trước khi xác định vì sao plugin/module không resolve được.

## 18. Thực hành mở rộng

### Bài 1 — Nhận diện đóng góp của plugin

Trong lab, ghi lại:

- Task nào đến từ **java-library** và **application**?
- Task nào đến từ **demo.greeting**?
- Extension **java**, **application** và **greeting** do ai tạo?
- Configuration **implementation** do ai tạo? **greetingTools** do ai tạo?

Đáp án phải có scope theo project, không được gộp :core và :app thành một task container.

### Bài 2 — Đổi convention, giữ override

Đổi default recipient trong **GreetingPlugin** từ **Gradle** thành **Team**. Chạy lại **:core:generateGreeting** và **:app:generateGreeting**. Vì sao :core đổi nội dung còn :app vẫn in **Java 17**? Xác minh bằng file output, không chỉ log của task.

### Bài 3 — Đổi output file bằng extension

Trong app:

~~~groovy
greeting {
    outputFile.set(layout.buildDirectory.file('generated/new-message.txt'))
}
~~~

Chạy **:app:generateGreeting**, xác minh file mới. Không sửa Java task class vì extension đã cung cấp API cấu hình output.

### Bài 4 — Thêm dependency công cụ

Thêm một artifact hợp lệ khác vào **greetingTools** rồi chạy **:app:showGreetingTools**. Kiểm tra số/tên JAR thay đổi nhưng **:app:run** vẫn chỉ cần dependencies Java application. Nếu công cụ có transitive dependencies, số lượng JAR có thể lớn hơn số dependency declarations.

### Bài 5 — Bỏ plugin và xem lỗi

Tạm xóa **id 'demo.greeting'** khỏi app nhưng giữ:

~~~groovy
greeting {
    recipient.set('Java 17')
}
~~~

hoặc giữ:

~~~groovy
dependencies {
    greetingTools 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Chạy Gradle; phân loại lỗi extension/configuration chưa tồn tại. Hoàn tác để khôi phục.

### Bài 6 — Chuyển đổi task eager sang lazy

Một plugin cũ viết:

~~~groovy
tasks.create('oldReport') {
    doLast { println 'old' }
}
~~~

Thử đổi sang **tasks.register('oldReport')**, nối dependency qua TaskProvider và dùng **tasks.named** để cấu hình từ module. Kiểm tra **help** không cần làm công việc task.

### Bài 7 — Xây convention plugin Java

Viết plugin riêng dùng **java-library**, đặt Java 17 toolchain và encoding UTF-8, rồi áp dụng cho hai module. Phân biệt **convention plugin** (chuẩn hóa build) với **Property.convention** (default cho một property).

### Bài 8 — Bài toán output producer–consumer

Tạo task consumer đọc file **greeting.outputFile** bằng **@InputFile RegularFileProperty**, nối provider của **GenerateGreetingTask.outputFile** vào task consumer. Khi đó Gradle có thông tin output producer và input consumer để lập dependency phù hợp. Không lấy file trong configuration rồi tự đọc ngay.

## 19. Câu hỏi tự kiểm tra

1. Vì sao **application { ... }** không phải block có sẵn ở mọi Project?
2. Task **run** thường do plugin nào cung cấp?
3. **Plugin.apply(Project)** khác **@TaskAction** ra sao?
4. Vì sao plugin nên dùng **tasks.register** hơn **tasks.create** cho task tùy chọn?
5. **Extension** là gì và vì sao Property có kiểu giúp DSL dễ bảo trì?
6. **Property.convention(value)** khác **Property.set(value)** ở ý nghĩa mặc định thế nào?
7. Configuration **implementation** là declarable, resolvable hay consumable?
8. Vì sao **greetingToolClasspath** được tách khỏi **greetingTools**?
9. Một plugin được áp dụng vào :core có tự thêm task vào :app không?
10. **apply false** có đồng nghĩa task của plugin đã xuất hiện ở root không?
11. Nếu task action dùng Project để resolve configuration, có thể gặp vấn đề gì với configuration cache?
12. Thêm **greetingTools** dependency có tự làm Java app nhìn thấy JAR đó khi compile không?
13. Java toolchain là extension, task hay configuration?
14. Khi task báo **UP-TO-DATE**, có nghĩa plugin apply không thành công không?
15. Vì sao custom plugin không nên tự thêm repositories trái policy?
16. **Convention plugin** khác **Property.convention** thế nào?
17. Nếu muốn chạy file output của task khác, nên dùng **Provider/Property** hay biến static?
18. Plugin **demo.greeting** được resolve từ đâu trong lab?

**Gợi ý đáp án:** (1) plugin application tạo extension; (2) Application plugin; (3) apply cấu hình model, TaskAction làm việc khi task chạy; (4) tránh task realization sớm; (5) đối tượng DSL có kiểu; (6) convention là default có thể ghi đè; (7) declarable; (8) scope khai báo so với resolvable path; (9) không; (10) không; (11) không an toàn cho configuration cache và có thể resolve quá sớm; (12) không; (13) extension **java** chứa toolchain settings; (14) không, task có thể không cần chạy lại; (15) centralized repository policy và bảo mật; (16) một cái là plugin thiết lập chuẩn, cái kia là default của property; (17) Provider/Property và input/output wiring; (18) buildSrc của main build.

## 20. Checklist áp dụng và tài liệu tham khảo

Trước khi dùng hoặc viết Gradle plugin trong repository thật:

- [ ] Plugin ID tồn tại và được áp dụng ở **đúng project**.
- [ ] Plugin/Gradle/JDK versions tương thích; external plugin repository được cấu hình an toàn.
- [ ] Task names, group, description và task paths rõ ràng.
- [ ] Đăng ký task bằng **register**, cấu hình bằng **named/configureEach** khi có thể.
- [ ] Task inputs/outputs được khai báo bằng **Property** và annotations chính xác.
- [ ] Extension có managed getters và tên không xung đột với plugin khác.
- [ ] Giá trị mặc định dùng **convention** nếu người dùng cần quyền ghi đè.
- [ ] Custom configuration chỉ mang một role phù hợp; không resolve nhầm dependency scope.
- [ ] Phân biệt **dependencyResolutionManagement** và **pluginManagement**.
- [ ] Không resolve dependency hoặc làm IO nặng trong **apply()**.
- [ ] Không truy cập Project state không an toàn từ task action.
- [ ] Task graph, dependencies và producer/consumer wiring được kiểm chứng.
- [ ] Chạy thử trên Gradle Wrapper với các lệnh **tasks**, **dependencies**, **build**, **validatePlugins**.
- [ ] Test cả default conventions lẫn user overrides ở ít nhất hai projects.
- [ ] Xem xét configuration cache, UP-TO-DATE, security và build performance khi đưa plugin vào CI.

### Tài liệu Gradle chính thức

- [Introduction to Plugins](https://docs.gradle.org/current/userguide/plugins.html)
- [Implementing Gradle Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html)
- [Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html)
- [Pre-compiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html)
- [Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html)
- [Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)
- [Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html)
- [Custom Gradle Types / Managed Properties](https://docs.gradle.org/current/userguide/custom_gradle_types.html)
- [Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html)
- [Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html)

**Kết luận:** **Plugin là đơn vị mở rộng mô hình Gradle Project.** Khi được áp dụng, nó có thể cung cấp **task để làm việc**, **extension để người dùng cấu hình**, **configuration để quản lý dependencies** và **convention để có giá trị mặc định hợp lý**. Người viết build.gradle cần hiểu phần tử nào do plugin nào tạo, ở scope nào và được dùng vào giai đoạn nào. Plugin tốt đăng ký task lười, nối dữ liệu bằng managed properties, giữ vai trò configuration rõ ràng và không làm side effect trong apply. Nhờ đó build Java 17 đa module có thể chia sẻ logic mà vẫn dễ kiểm chứng, tối ưu và bảo trì.

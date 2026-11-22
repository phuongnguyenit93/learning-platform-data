# Cấu hình extension và đối tượng có tên bằng Groovy DSL

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Groovy DSL

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **extension**, **extra property**, **task**, **named domain object** và **container quản lý đối tượng có tên** trong Gradle.
2. Hiểu vì sao các khối Groovy DSL như application { ... }, java { ... }, sourceSets { ... } hoặc publishing { ... } xuất hiện sau khi áp dụng plugin phù hợp.
3. Cấu hình một extension có sẵn, truy xuất extension theo tên/kiểu và cấu hình phần tử có tên bằng named(...).
4. Chọn đúng create(...), register(...), named(...), configureEach(...) để tránh tạo hoặc cấu hình đối tượng quá sớm.
5. Đọc và vận dụng một dự án Gradle Groovy DSL chạy được trên Java 17+, rồi hiểu cách plugin tự khai báo extension và container riêng.
6. Chẩn đoán các lỗi như "Could not find method ...", "Task with name ... not found", sai tên đối tượng, closure bị hiểu nhầm receiver và lạm dụng thao tác eager.

Đề bài này tập trung vào **cấu hình mô hình build bằng Groovy DSL**, không phải cách viết ứng dụng bằng ngôn ngữ Groovy. Các đoạn trong build.gradle là mã Groovy chạy trong ngữ cảnh Gradle; mã ứng dụng ở ví dụ thực hành là Java 17.

## 1. Vì sao Gradle có extension và đối tượng có tên?

Gradle tổ chức cấu hình bằng một mô hình đối tượng. Một plugin có thể đóng góp khả năng vào dự án dưới dạng:

- **Extension**: đối tượng chứa các tùy chọn của plugin hoặc một nhóm cấu hình có ý nghĩa. Ví dụ plugin application tạo extension application để đặt mainClass; plugin java cung cấp extension java cho toolchain và những tùy chỉnh của Java.
- **Task**: công việc sẽ được thực thi, như run, compileJava hoặc jar. Mỗi task có **tên duy nhất trong project của nó** và thuộc tập hợp tasks.
- **Named domain object**: một thực thể cấu hình được nhận diện qua tên trong một container, như source set main/test, configuration implementation/runtimeClasspath, publication mavenJava hay task run.
- **NamedDomainObjectContainer**: đối tượng quản lý các phần tử cùng loại, bảo đảm tên là duy nhất trong container, hỗ trợ tạo mới, tham chiếu, chọn và cấu hình theo tên.
- **Provider/Property**: API biểu diễn và nối các giá trị cấu hình, giúp hoãn việc đọc giá trị đến khi cần và biểu thị dữ liệu đầu vào cho task.

Ví dụ trực quan:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'example.Main'
}

tasks.named('run') {
    args 'Lan'
}
~~~

Có hai thao tác rất khác nhau:

- application { ... } cấu hình **một extension** do plugin application tạo ra.
- tasks.named('run') { ... } tìm và cấu hình **task đã tồn tại theo tên** trong container tasks. Nó không tạo mới task run.

Nếu bỏ plugin application, extension application và task run thường không tồn tại. Khối DSL không tự tạo ra một tính năng chỉ vì ta viết tên nó vào build.gradle.

### 1.1. Sơ đồ mô hình

~~~text
Project (dự án Gradle)
├── extensions (ExtensionContainer)
│   ├── java             -> JavaPluginExtension
│   ├── application      -> JavaApplication
│   └── lesson           -> extension riêng nếu plugin/script đăng ký
│       └── channels     -> NamedDomainObjectContainer<ChannelSpec>
│           ├── dev      -> ChannelSpec(name="dev")
│           └── prod     -> ChannelSpec(name="prod")
├── tasks (TaskContainer)
│   ├── run              -> JavaExec
│   ├── compileJava      -> JavaCompile
│   └── jar              -> Jar
└── configurations (ConfigurationContainer)
    ├── implementation
    └── runtimeClasspath
~~~

Sơ đồ biểu diễn **các ví dụ thuộc những plugin và cấu hình phù hợp**, không ngụ ý mọi project Gradle đều có đủ mọi extension/task/configuration trên. Dù đều có tên, task và dependency configuration có API, vòng đời và ý nghĩa khác nhau.

## 2. Groovy DSL biến đối tượng thành khối cấu hình như thế nào?

Một khối như:

~~~groovy
application {
    mainClass = 'example.Main'
}
~~~

là cách diễn đạt ngắn gọn việc gọi API cấu hình extension application. Plugin đã đăng ký đối tượng extension dưới tên application, và Gradle tích hợp đối tượng ấy vào DSL của build script.

Trong Groovy, cặp dấu ngoặc nhọn { ... } tạo **closure**. Gradle cấu hình closure để những thuộc tính/phương thức bên trong có thể hướng tới đối tượng đang cấu hình (closure delegate). Nhờ đó mainClass trong khối application được hiểu là thuộc tính của extension application, không phải một biến Java toàn cục.

Tư duy đúng:

~~~text
Tên block được plugin đăng ký/Gradle hỗ trợ
    ↓
Closure đang cấu hình đối tượng nào?
    ↓
Tên property và method có tồn tại trên đối tượng đó?
    ↓
Plugin/task nào thực sự sử dụng giá trị vừa đặt?
~~~

Khi closure được lồng nhiều tầng, receiver cũng thay đổi. Ví dụ java.toolchain.languageVersion là thuộc tính của Java Toolchain Specification, còn application.mainClass thuộc extension ứng dụng. Không nên mặc định tên field nhìn giống nhau thì thuộc cùng một đối tượng.

**Cú pháp Groovy DSL thường gặp:**

~~~groovy
application {
    mainClass = 'example.Main'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.register('announce') {
    group = 'help'
    description = 'In một thông báo'
    doLast {
        println 'Thông báo từ task'
    }
}
~~~

Dấu ngoặc có thể được lược bớt ở các lệnh gọi Groovy đơn giản; tuy nhiên để dễ đọc và tránh nhầm khi lồng các closure, bài này ưu tiên cú pháp có ngoặc ở các API như named(...), register(...).

### 2.1. Extension không đồng nghĩa với extra property (ext)

Gradle có **ExtraPropertiesExtension** (thường truy cập qua ext) để gắn các key-value tùy ý:

~~~groovy
ext.releaseLabel = 'demo'
~~~

Giá trị releaseLabel ở đây chỉ là thuộc tính mở rộng động, **không phải một plugin extension có kiểu rõ ràng** như application, java hoặc một extension do plugin tạo qua extensions.create(...).

So sánh:

| Cơ chế | Ví dụ | Thích hợp khi |
|---|---|---|
| Extension có kiểu | application { mainClass = 'example.Main' } | Plugin cung cấp một mô hình cấu hình ổn định |
| Gradle Property/Provider | providers.gradleProperty('releaseLabel') | Nhận cấu hình từ các nguồn project property tiêu chuẩn |
| Extra property (ext) | ext.releaseLabel = 'demo' | Truyền một giá trị bổ sung trong build logic đơn giản |
| Named object | tasks.named('run') { ... } | Cấu hình một phần tử đã tồn tại trong collection có tên |

Không nên dùng ext để mô phỏng cả một mô hình extension phức tạp: tên key ít được kiểm tra và thiếu cấu trúc kiểu/Provider rõ ràng. Việc thêm ext.releaseLabel cũng không làm Gradle tự tạo task hoặc plugin tương ứng.

## 3. Cấu hình extension do plugin cung cấp

### 3.1. Plugin application

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'example.Main'
    applicationDefaultJvmArgs = ['-Dapp.mode=lab']
}
~~~

- Plugin application cung cấp extension application và task run cùng các task phân phối.
- mainClass chỉ tên lớp chứa phương thức public static void main(String[] args).
- applicationDefaultJvmArgs áp dụng các tham số JVM mặc định cho những điểm chạy do plugin hỗ trợ, chứ không tự thay đổi JVM đang chạy Gradle.
- Nếu lớp Main không nằm đúng package/classpath hoặc không có main hợp lệ, việc đặt mainClass không thể tự sửa mã.

### 3.2. Extension java

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Đây là cấu hình Java plugin extension, chỉ định toolchain Java 17 cho các tác vụ phù hợp. Nó **khác** phiên bản JDK dùng để chạy tiến trình Gradle; môi trường phải cung cấp JDK tương thích hoặc đã thiết lập cách provision toolchain.

### 3.3. Truy xuất bằng API thay vì DSL block

Một extension cũng có thể được truy xuất tường minh:

~~~groovy
def javaExtension = extensions.getByName('java')
println javaExtension.class.name
~~~

Đoạn trên **chỉ là ví dụ truy xuất** khi plugin java đã áp dụng; dòng println sẽ chạy trong pha cấu hình nếu đặt trực tiếp ở cấp root build.gradle. Trong code có kiểm tra kiểu, ưu tiên getByType(JavaPluginExtension) hoặc configure(type, Action) khi đã biết kiểu extension, tránh phụ thuộc tên string rải rác.

Ví dụ khi cần truy xuất extension của application:

~~~groovy
def appModel = extensions.getByName('application')
println appModel.mainClass.get()
~~~

Dòng thứ hai có thể in example.Main nếu giá trị đã được thiết lập trước đó. Đây là giá trị cấu hình **của extension**; không nên nhầm với đầu ra của ứng dụng khi chạy task run.

**Lưu ý thứ tự:** Plugin phải được áp dụng trước khi truy xuất extension do nó tạo. Chỉ tên block thôi không xác định được extension thuộc plugin nào nếu dự án đã viết build logic riêng hoặc nhiều plugin đăng ký thêm DSL.

## 4. Đối tượng có tên và các API thao tác phổ biến

Mô hình NamedDomainObjectContainer cho phép thao tác đối tượng theo **tên định danh**, ví dụ main, test, run, jar, implementation. Tên thường phân biệt chữ hoa/chữ thường.

| API | Làm gì? | Mối quan hệ với lazy configuration |
|---|---|---|
| create('dev') | Tạo ngay đối tượng dev trong container | **Eager**: thực thể được khởi tạo lúc gọi |
| register('dev') | Đăng ký đối tượng dev sẽ được tạo khi thực sự cần | **Lazy**: trả về NamedDomainObjectProvider |
| named('dev') | Lấy provider tham chiếu đến đối tượng **đã có/đã đăng ký** theo tên | Thường **lazy**; không tự tạo tên mới |
| named('dev') { ... } | Gắn hành động cấu hình cho đối tượng cùng tên | Ưu tiên khi cần cấu hình một phần tử cụ thể |
| getByName('dev') | Lấy đối tượng ngay theo tên | Thường làm đối tượng được hiện thực hóa (realized) |
| configureEach { ... } | Áp dụng cấu hình cho các đối tượng trong collection khi chúng được cấu hình | Phù hợp khi cần áp dụng một quy tắc cho nhiều đối tượng mà không ép tạo tất cả |
| withType(T).configureEach { ... } | Cấu hình các đối tượng thuộc kiểu T | Dùng phổ biến cho task, ví dụ JavaCompile |

Với named(...), Gradle có thể báo lỗi nếu tên không có trong container. **Không dùng named(...) như một cách tạo mới.** Với create/register, container phải có khả năng tạo phần tử mới; việc có API nhận tên không có nghĩa mọi loại container đều nên dùng register() theo cùng một cách nghiệp vụ.

### 4.1. Task: đăng ký mới, rồi cấu hình theo tên

~~~groovy
tasks.register('welcome') {
    group = 'help'
    doLast {
        println 'Welcome from Gradle'
    }
}

tasks.named('welcome') {
    description = 'In lời chào'
}
~~~

- register('welcome') cung cấp TaskProvider cho task mới, chưa cần hiện thực hóa ngay.
- named('welcome') nhận lại provider và thêm cấu hình; không tạo task thứ hai.
- Gọi ./gradlew -q welcome sẽ in một dòng từ action:

~~~text
Welcome from Gradle
~~~

Nếu thay named('welcome') bằng named('unknownTask'), Gradle có thể thất bại khi tìm tên; cần kiểm tra task được tạo trong cùng project và plugin đã áp dụng hay chưa.

### 4.2. Cấu hình task có sẵn theo tên/kiểu

~~~groovy
plugins {
    id 'java'
}

tasks.named('jar', Jar) {
    archiveBaseName = 'sample'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

- Plugin java đăng ký task jar và compileJava; task jar là kiểu Jar.
- named('jar', Jar) vừa chọn tên vừa kiểm tra kiểu phù hợp.
- withType(JavaCompile).configureEach áp dụng mã hóa UTF-8 cho những task kiểu JavaCompile mà Gradle cấu hình trong build.
- archiveBaseName chỉ đổi phần tên artifact; nó không thay thế toàn bộ cấu hình đóng gói.

Khi chỉ một task cần thay đổi, dùng named('tên'). Khi một quy tắc áp dụng cho **nhiều task cùng kiểu**, dùng withType(...).configureEach. Tránh dùng tasks.all { ... } hoặc cách truy cập trực tiếp làm hiện thực hóa không cần thiết mọi task.

### 4.3. Source set: các đối tượng main và test

~~~groovy
plugins {
    id 'java'
}

sourceSets {
    named('main') {
        java.srcDir('src/shared/java')
    }

    named('test') {
        java.srcDir('src/integrationTestSupport/java')
    }
}
~~~

- Java plugin cung cấp sourceSets, một collection các SourceSet có tên.
- main và test là source set mặc định do plugin java cung cấp.
- named('main') và named('test') cấu hình **đối tượng có sẵn**.
- java.srcDir(...) thêm đường dẫn nguồn; trái lại, gán toàn bộ srcDirs có thể ghi đè danh sách thư mục đang có.
- Thêm thư mục nguồn không đồng nghĩa Gradle tự có file Java trong đó. Nếu thư mục rỗng thì các task có thể không có source tương ứng.

### 4.4. Dependency configuration: object có tên nhưng khác task

~~~groovy
plugins {
    id 'java'
}

configurations.named('implementation') {
    description = 'Dependencies cho mã chính'
}
~~~

implementation là tên của một **dependency configuration** do Java plugin tạo. Nó không phải task. Không thể chạy ./gradlew implementation để "thực thi" configuration như task, trừ khi một task khác trùng tên được đăng ký rõ ràng.

Cũng cần phân biệt việc **cấu hình đối tượng**:

~~~groovy
configurations.named('implementation') {
    description = 'Compile dependency scope'
}
~~~

với **khai báo một thư viện** thuộc configuration đó:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Dòng thứ hai thêm dependency qua DependencyHandler, chứ không cấu hình thuộc tính description của Configuration. Khi thêm dependency ngoài ví dụ chính, Gradle cần repository phù hợp như mavenCentral() để resolve.

## 5. Thực hành chạy được: Java 17, extension và các named object mặc định

Bài thực hành này không cần thư viện ngoài. Nó dùng **application plugin**, Java toolchain 17, một source set main, task run và jar có tên. Bạn sẽ thấy phần config của build.gradle ảnh hưởng đến chương trình Java thế nào.

### 5.1. Cấu trúc thư mục

~~~text
groovy-extension-lab/
├── settings.gradle
├── build.gradle
├── gradlew                   # được tạo ở bước Wrapper
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/demo/Main.java
    └── shared/java/demo/Formatter.java
~~~

Nếu chưa tạo Wrapper, ban đầu chỉ cần hai tệp Gradle và hai tệp Java. Có thể dùng một Gradle đã cài để chạy gradle wrapper một lần; sau đó dùng Wrapper và commit các file cần thiết.

**settings.gradle**

~~~groovy
rootProject.name = 'groovy-extension-lab'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.Main'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

// sourceSets là extension/container do plugin java cung cấp.
sourceSets {
    named('main') {
        java.srcDir('src/shared/java')
    }
}

// Cấu hình task run được application plugin đăng ký.
tasks.named('run', JavaExec) {
    args 'Lan'
}

// Cấu hình task jar được Java plugin đăng ký.
tasks.named('jar', Jar) {
    archiveBaseName = 'groovy-extension-lab'
}

// Quy tắc áp dụng cho những task biên dịch Java cùng kiểu.
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

// Task do dự án đăng ký mới và sử dụng project property.
def lessonTitle = providers.gradleProperty('lessonTitle')
    .orElse('Groovy DSL')

tasks.register('showTitle') {
    inputs.property('lessonTitle', lessonTitle)

    doLast {
        println 'Lesson=' + lessonTitle.get()
    }
}
~~~

**src/main/java/demo/Main.java**

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Guest" : args[0];
        System.out.println(Formatter.greet(name));
    }
}
~~~

**src/shared/java/demo/Formatter.java**

~~~java
package demo;

public final class Formatter {
    private Formatter() {
    }

    public static String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

**Vì sao Java compile được?** Class Formatter nằm trong thư mục src/shared/java, vốn không phải source root mặc định của Java plugin. Khối sourceSets.named('main') đã **bổ sung** thư mục ấy vào Java source set main. Vì cả hai lớp cùng package demo và được biên dịch cho main, Main có thể gọi Formatter.greet(...).

### 5.2. Chạy bằng Wrapper

Trên Linux/macOS:

~~~bash
./gradlew -q run
./gradlew -q showTitle
./gradlew -q showTitle -PlessonTitle="Thực hành Gradle"
./gradlew jar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat -q run
.\gradlew.bat -q showTitle
.\gradlew.bat -q showTitle -PlessonTitle="Thực hành Gradle"
.\gradlew.bat jar
~~~

**Đầu ra do ứng dụng Java tạo ra khi chạy run** (bỏ qua log JVM/Gradle nếu có):

~~~text
Xin chào, Lan!
~~~

**Đầu ra action của showTitle mặc định:**

~~~text
Lesson=Groovy DSL
~~~

**Đầu ra action của showTitle khi có -PlessonTitle:**

~~~text
Lesson=Thực hành Gradle
~~~

Các chuỗi trên là đầu ra của chương trình/task, không phải toàn bộ log Gradle. Tên file JAR tạo ra ở build/libs/ còn phụ thuộc phiên bản project và quy tắc archive tương ứng; đừng đoán chắc toàn bộ tên tệp khi chưa xem artifact thực tế.

### 5.3. Đọc lại cấu hình vừa viết

| Đoạn build.gradle | Đối tượng được cấu hình | Ý nghĩa |
|---|---|---|
| application { mainClass = ... } | Extension application | Chỉ lớp main khi chạy ứng dụng |
| java { toolchain { ... } } | Java plugin extension | Cung cấp toolchain Java 17 |
| sourceSets.named('main') { ... } | SourceSet có tên main | Thêm một thư mục mã nguồn |
| tasks.named('run', JavaExec) { ... } | Task có tên run | Truyền argument Lan cho main |
| tasks.named('jar', Jar) { ... } | Task có tên jar | Chỉnh base name của archive |
| tasks.withType(JavaCompile).configureEach | Collection các task JavaCompile | Thiết lập charset chung |
| tasks.register('showTitle') | Task mới do dự án đăng ký | Thực thi action in nhãn bài học |

Lưu ý hai lần "cấu hình" trong quá trình build:

- Các closure cấu hình extension và task thường được đăng ký/áp dụng trong **configuration phase**.
- Lệnh println nằm trong doLast của showTitle chạy khi **execution phase** thực thi task đó.

Không đặt việc tải dữ liệu mạng, gọi API hoặc tính toán nặng ngay ở cấp root build.gradle chỉ để cấu hình extension, vì cấu hình build có thể chạy cả khi task đó không được yêu cầu.

## 6. Tự định nghĩa extension: extension được đăng ký ra sao?

Khi **sử dụng** một plugin, thông thường chỉ cần khối application { ... } hoặc java { ... }. Khi **viết plugin hoặc xây DSL riêng**, bạn có thể tạo extension và expose ra build script.

Ví dụ dưới minh họa cơ chế với một kiểu managed đơn giản. Đây là **một ví dụ build.gradle khác**, không ghép thẳng vào build.gradle của mục 5.

**settings.gradle**

~~~groovy
rootProject.name = 'custom-extension-lab'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'base'
}

// Gradle tạo implementation cho managed interface.
interface GreetingOptions {
    org.gradle.api.provider.Property<String> getMessage()
    org.gradle.api.provider.Property<String> getTarget()
}

// Đăng ký extension với tên greeting.
def greetingModel = extensions.create('greeting', GreetingOptions)

greeting {
    message = 'Xin chào'
    target = 'Gradle'
}

tasks.register('showGreeting') {
    doLast {
        println greetingModel.message.get() + ', ' + greetingModel.target.get() + '!'
    }
}
~~~

Chạy:

~~~bash
./gradlew -q showGreeting
~~~

Action in:

~~~text
Xin chào, Gradle!
~~~

**Đây là cơ chế cơ bản của extension:**

1. Kiểu GreetingOptions khai báo hai property theo mô hình managed type của Gradle; không tự viết field và constructor cho từng property.
2. extensions.create('greeting', GreetingOptions) đăng ký một extension của project dưới tên greeting.
3. Khối greeting { ... } cấu hình extension theo tên vừa đăng ký, và cú pháp assignment của Groovy DSL đặt giá trị vào các Property.
4. Task tiêu thụ hai giá trị qua get(). Đoạn thực hành minh họa cách đọc giá trị rõ ràng; plugin production nên nối Property vào input của task có kiểu để Gradle quản lý input/output và hỗ trợ configuration cache.

**Lưu ý về cách thiết kế plugin thực tế:** Không nên lặp lại định nghĩa extension trong mỗi build.gradle của hàng trăm module. Hãy đóng gói kiểu extension, đăng ký extension và task tương ứng trong plugin chung (plugin class hoặc convention plugin) rồi để module tiêu thụ DSL. Ví dụ trên chỉ cố ý viết tất cả vào một file để quan sát cơ chế.

## 7. Tự định nghĩa container chứa nhiều đối tượng có tên

Khi cấu hình có **nhiều thực thể cùng loại** như môi trường dev/staging/prod hoặc nhiều nhóm báo cáo, một extension đơn lẻ với hàng chục field như devMessage, prodMessage, stagingMessage sẽ khó mở rộng. Thay vào đó, extension có thể chứa **NamedDomainObjectContainer<T>**, mỗi phần tử có name và các property riêng.

### 7.1. Ví dụ managed object và named container

Ví dụ tiếp theo độc lập với ví dụ mục 5 và 6. Nó minh họa cách khai báo kiểu, đăng ký container, tạo hai channel có tên rồi cấu hình một channel đã đăng ký.

**settings.gradle**

~~~groovy
rootProject.name = 'named-container-lab'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'base'
}

// Phần tử có tên và property do Gradle quản lý.
interface ChannelSpec extends org.gradle.api.Named {
    org.gradle.api.provider.Property<String> getMessage()
}

// Extension chứa một container các ChannelSpec có tên.
abstract class LessonExtension {
    abstract org.gradle.api.provider.Property<String> getTitle()
    abstract org.gradle.api.NamedDomainObjectContainer<ChannelSpec> getChannels()

    void channels(
        org.gradle.api.Action<? super
            org.gradle.api.NamedDomainObjectContainer<ChannelSpec>> action
    ) {
        action.execute(getChannels())
    }
}

// Cài extension theo tên lesson.
def lessonModel = extensions.create('lesson', LessonExtension)

lesson {
    title = 'Groovy DSL'

    channels {
        register('dev') {
            message = 'Chế độ phát triển'
        }
        register('prod') {
            message = 'Chế độ phát hành'
        }
    }
}

// named() lấy đúng đối tượng đã đăng ký, không tạo đối tượng mới.
lessonModel.channels.named('dev') {
    message = 'Hello từ dev'
}

tasks.register('showDev') {
    doLast {
        def channel = lessonModel.channels.named('dev').get()
        println 'lesson=' + lessonModel.title.get()
        println 'channel=' + channel.name
        println 'message=' + channel.message.get()
    }
}
~~~

Chạy:

~~~bash
./gradlew -q showDev
~~~

Đầu ra action:

~~~text
lesson=Groovy DSL
channel=dev
message=Hello từ dev
~~~

**Cách hiểu ví dụ:**

- ChannelSpec là kiểu named managed object; thuộc tính name có sẵn theo giao diện Named, trong khi message là Property<String> của riêng từng phần tử.
- LessonExtension có thuộc tính title và một container channels. Gradle có thể hiện thực hóa managed property của kiểu container.
- Phương thức channels(Action) cho phép DSL lồng channels { ... } cấu hình container.
- register('dev') và register('prod') **đăng ký hai tên**, mỗi tên có cấu hình message riêng.
- lessonModel.channels.named('dev') { ... } **cấu hình bổ sung** cho dev; nó không tạo channel dev mới, và cấu hình sau thay message thành "Hello từ dev".
- .get() ở phần đọc cuối cùng yêu cầu đối tượng dev thực sự được hiện thực hóa. Với một container lớn, tránh get() quá sớm khi vẫn có thể nối provider vào nơi sử dụng.
- Task showDev truy cập extension trong action để ví dụ ngắn và dễ học. Khi triển khai plugin cho dự án lớn, nên sử dụng task type với @Input và Property/Provider, không tùy ý chụp đối tượng Project/extension động trong task action nếu muốn tối ưu configuration cache và incremental build.

Vì tên nằm trong container, register('dev') lần thứ hai thường gây lỗi trùng tên. Nếu định sửa dev đã có, phải dùng named('dev') thay vì lặp create/register.

### 7.2. Một cú pháp viết ngắn thường gặp trong DSL

Nhiều container của Gradle cho phép cú pháp tên đối tượng dưới dạng khối:

~~~groovy
sourceSets {
    main {
        java.srcDir 'src/shared/java'
    }
}
~~~

Cách viết này thuận tiện nhờ Groovy/Gradle DSL, nhưng với code cần bảo trì lâu dài, đặc biệt khi yêu cầu lazy configuration hoặc muốn **phân biệt rõ tạo mới và chỉnh sửa**, cú pháp tường minh thường dễ hiểu hơn:

~~~groovy
sourceSets.named('main') {
    java.srcDir('src/shared/java')
}
~~~

Đối với container tự định nghĩa, cú pháp shorthand như dev { ... } phụ thuộc quy tắc cấu hình mà container cung cấp; khi muốn chắc chắn, dùng register('dev') { ... } để tạo hoặc named('dev') { ... } để cấu hình đối tượng đã có.

## 8. Những nguyên tắc quan trọng khi dùng Provider và lazy configuration

### 8.1. Đừng nhầm Provider với giá trị đã lấy

Ví dụ:

~~~groovy
def label = providers.gradleProperty('lessonLabel')
    .orElse('Mặc định')

tasks.register('showLabel') {
    doLast {
        println label.get()
    }
}
~~~

label là **Provider**; lời gọi get() đọc giá trị hiện tại theo mô hình Provider. TaskProvider trả về bởi tasks.register(...) là provider của **task**, còn NamedDomainObjectProvider trả về bởi container.register(...) hoặc named(...) tham chiếu **đối tượng có tên**. Chúng đều phục vụ trì hoãn nhưng không phải cùng một loại giá trị.

Với property khai báo là Gradle Property<String>, thường dùng:

~~~groovy
message.convention('Mặc định')
message.set('Giá trị mới')
~~~

- convention(...) đặt giá trị mặc định, có thể được thay bằng giá trị cấu hình tường minh.
- set(...) khai báo giá trị do người dùng/chính build logic chọn.
- get() lấy giá trị, có thể gây lỗi nếu property không có giá trị.
- Với môi trường có nhiều nguồn cấu hình, dùng Provider kết hợp map/orElse thay vì buộc đọc giá trị sớm.

### 8.2. Lazy đến đâu?

| Cách viết | Thời điểm tác động điển hình | Khuyến nghị |
|---|---|---|
| tasks.create('report') | Tạo task ngay khi cấu hình | Hạn chế cho mã mới |
| tasks.register('report') | Đăng ký task; chỉ hiện thực hóa khi cần | Ưu tiên |
| tasks.getByName('report') | Truy xuất task ngay | Chỉ dùng khi thực sự cần instance |
| tasks.named('report') | Lấy TaskProvider của task đã tồn tại | Ưu tiên khi cấu hình theo tên |
| tasks.withType(Test) { ... } | Có thể eagerly configure nhiều task | Thay bằng withType(Test).configureEach |
| tasks.withType(Test).configureEach { ... } | Cấu hình theo kiểu khi đối tượng được cấu hình | Ưu tiên cho quy tắc chung |
| provider.get() trong configuration | Lấy giá trị ngay | Chỉ khi phải có giá trị để cấu hình |
| Provider nối vào Property của task | Gradle quản lý chuỗi giá trị tốt hơn | Ưu tiên cho plugin/build logic có vòng đời dài |

Lazy configuration không có nghĩa một đối tượng sẽ **không bao giờ được tạo**: nếu cần nó để chạy hoặc để lấy dữ liệu, Gradle vẫn hiện thực hóa. Giá trị ở đây là tránh khởi tạo và cấu hình **những đối tượng không liên quan** đến task đang yêu cầu.

### 8.3. Pha cấu hình và pha thực thi

~~~groovy
println 'Configuring build'

tasks.register('demoPhase') {
    println 'Configuring demoPhase'

    doLast {
        println 'Executing demoPhase'
    }
}
~~~

Hai dòng đầu thuộc mã **configuration** (dòng trong register phụ thuộc thời điểm task được hiện thực hóa); dòng trong doLast chạy **khi task thực thi**. Số lần và thứ tự dòng log cấu hình có thể khác khi Gradle sử dụng configuration cache; không dùng ví dụ này để khẳng định thứ tự log tuyệt đối trong mọi Gradle version.

Không nên giữ tham chiếu Project hoặc đọc environment/network tùy tiện trong action của task. Với task type thực tế, khai báo input/output qua Property, RegularFileProperty, DirectoryProperty, @Input, @InputFile và các API thích hợp để Gradle biết khi nào cần chạy lại và hỗ trợ cache.

## 9. Tránh nhầm phạm vi và thứ tự plugin

### 9.1. Cấu hình extension trước khi plugin tồn tại

Sai về ý tưởng:

~~~groovy
application {
    mainClass = 'demo.Main'
}

// Không có plugin application cung cấp extension trong project.
~~~

Nếu không có một plugin khác tự khai báo extension tên application, Gradle có thể báo không tìm thấy method/property. Sửa bằng cách áp dụng plugin phù hợp trước:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.Main'
}
~~~

### 9.2. Đối tượng có tên nằm trong một project cụ thể

Trong multi-project build, :app:run và :service:run là hai task thuộc **hai project**, có thể trùng tên ngắn run nhưng path khác. Tương tự, extension của project app không tự xuất hiện trong service chỉ vì root project đã cấu hình extension đó.

Nếu cần cấu hình nhiều project, áp dụng plugin đúng project và dùng convention plugin/shared build logic khi phù hợp. Không nên cố gọi extensions.getByName('application') trên root trong khi plugin chỉ được áp dụng ở :app.

### 9.3. Khác biệt giữa extension và container

Một extension có thể chứa **nhiều property** hoặc một **container** của những đối tượng khác nhau. Nhưng không phải cứ có một khối { ... } thì đó là extension hoặc NamedDomainObjectContainer:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Khối repositories là DSL của RepositoryHandler, tạo/định nghĩa nơi lấy dependency. Đừng gán mọi block trong build.gradle vào cùng một loại. Khi không rõ, tìm đúng loại API trong Gradle DSL reference hoặc tài liệu plugin.

## 10. Lỗi thường gặp và cách chẩn đoán

### Lỗi 1: Could not find method application() for arguments ...

**Dấu hiệu:** Gradle không nhận ra khối application { ... }.

**Kiểm tra:** Plugin application đã áp dụng cho **đúng project** chưa? Tên block có đúng với extension do plugin đăng ký không? Build script đã có lỗi cấu hình xảy ra trước đó chưa?

**Cách sửa:** Áp dụng plugin hoặc dùng tên extension đúng theo tài liệu. Không thay một cách mù quáng bằng ext.application vì đó là cơ chế khác.

### Lỗi 2: Task with name 'run' not found

**Dấu hiệu:** tasks.named('run') không tìm được.

**Kiểm tra:** Plugin application đã tạo run? Đang cấu hình root hay subproject? Có phải task thực sự tên run với chữ thường?

**Cách sửa:** Sửa đúng project và áp dụng plugin. Nếu cần một task **mới**, dùng tasks.register('tênTask'), không dùng named để tạo mới.

### Lỗi 3: Cannot create ... as it already exists

**Dấu hiệu:** Gọi create('dev') hoặc register('dev') lặp với tên đã có.

**Cách sửa:** Nếu muốn thay đổi object hiện có, dùng named('dev') { ... }. Nếu thật sự cần đối tượng thứ hai, đặt một tên khác có ý nghĩa.

### Lỗi 4: No such property / Could not set unknown property

**Dấu hiệu:** Đặt một property không tồn tại trong extension hoặc nhầm receiver của closure.

**Kiểm tra:** Đối tượng đang được cấu hình thuộc type nào? Property tên mainClass hay mainClassName? Tài liệu plugin/version hiện dùng ghi cú pháp nào? Đối tượng Property<T> cần thao tác bằng set(...) hay có thể dùng assignment Groovy DSL?

**Cách sửa:** Đọc API của type, hạn chế lồng closure quá sâu, dùng tên/đối tượng tường minh khi cần. Không đoán API từ ví dụ plugin khác.

### Lỗi 5: named(...) không tạo đối tượng mới

**Dấu hiệu:** Dùng sourceSets.named('integrationTest') khi source set này chưa có.

**Cách sửa:** Nếu thực sự cần source set mới, cân nhắc:

~~~groovy
sourceSets {
    create('integrationTest') {
        java.srcDir('src/integrationTest/java')
    }
}
~~~

Đây chỉ mới tạo source set và source directory. Để **chạy test integration** thành quy trình chuẩn, còn cần cấu hình classpath, task Test, framework và quan hệ vòng đời phù hợp; một source set mới không tự có toàn bộ pipeline kiểm thử tương ứng.

### Lỗi 6: Cấu hình task chậm và tác động quá rộng

**Dấu hiệu:** Task không liên quan cũng bị tạo/cấu hình, build configuration lâu.

**Kiểm tra:** Có đang dùng tasks.all, getByName, withType(Test) { ... } hoặc duyệt toàn bộ task không? Có gọi Provider.get() quá sớm?

**Cách sửa:** Ưu tiên register, named và configureEach theo phạm vi thực sự cần. Tránh công việc nặng trong configuration phase.

### Lỗi 7: Extension có giá trị, task lại không thay đổi

**Dấu hiệu:** Bạn cấu hình greeting { message = 'Hello' } nhưng task luôn in giá trị hard-code.

**Căn nguyên:** Extension chỉ **lưu cấu hình**; task/plugin phải **đọc và áp dụng** property đó. Không có liên kết tự động từ mọi extension tới mọi task.

**Cách sửa:** Dùng Provider/Property để nối extension vào task input, hoặc cấu hình task rõ ràng. Với plugin production, có thể tạo custom task type và đặt input/output có annotation để Gradle theo dõi thay đổi.

## 11. Checklist thiết kế Groovy DSL dễ bảo trì

1. **Biết ai sở hữu DSL block.** Kiểm tra plugin, project và kiểu object trước khi viết config.
2. **Nhóm cấu hình có ý nghĩa thành extension.** Khi viết plugin, dùng Property<T>/Provider để cấu hình có kiểu và dễ kết nối.
3. **Dùng container cho nhiều đối tượng cùng loại.** Mỗi đối tượng có name ổn định, chỉ tạo mới khi cần.
4. **Đặt đúng API theo hành động:** create/register để thêm mới; named để cấu hình đã có; configureEach để áp dụng quy tắc rộng.
5. **Tránh eager configuration.** Đừng lạm dụng getByName, all, gọi get() hoặc iterate mọi task ở pha cấu hình.
6. **Giữ quan hệ extension → task rõ ràng.** Giá trị chỉ có tác dụng khi task/plugin tiêu thụ nó.
7. **Phân biệt cấu hình và hành động.** Khai báo input/output và hoãn công việc thực tế sang task execution.
8. **Bảo đảm phạm vi project.** Trong multi-project build, áp dụng plugin và cấu hình đúng module.
9. **Ưu tiên API chính thức.** Nhiều plugin có tên extension, object và property riêng; tra cứu tài liệu/version tương ứng.
10. **Kiểm tra bằng một task nhỏ.** Dùng Wrapper, kiểm tra task có được đăng ký, giá trị nhận đúng và output khi chạy có như dự kiến.

## 12. Bài tập tự kiểm tra

**Câu 1.** Sau khi áp dụng application plugin, hai đoạn application { mainClass = 'demo.Main' } và tasks.named('run') { args 'A' } đang cấu hình cùng đối tượng hay khác đối tượng?

**Câu 2.** Nếu muốn tạo task report mới và sau đó chỉnh description của report, nên chọn register(...) hay named(...) cho từng thao tác?

**Câu 3.** Trong Java plugin, sourceSets.named('main') dùng để tạo source set hay lấy source set đã có? Khi muốn thêm đường dẫn mà không mất source roots mặc định, nên gọi gì?

**Câu 4.** Vì sao register('prod') thường tốt hơn create('prod') nếu container cho phép lazy registration và chưa cần dùng prod ngay?

**Câu 5.** Một plugin tạo extension tên lesson nhưng không đăng ký task nào đọc lesson.title. Ghi lesson { title = 'Hello' } có tự làm JAR đổi tên không?

**Câu 6.** Một plugin đã đăng ký channel dev. Nếu cần thay message của dev, dùng register('dev') lần nữa có đúng không? Nên dùng gì?

**Câu 7.** tasks.withType(Test) { ... } và tasks.withType(Test).configureEach { ... } khác nhau ra sao đối với cấu hình task?

**Gợi ý đáp án:**

1. Khác: application là extension cấu hình; run là task có tên.
2. register('report') để tạo task; named('report') { description = ... } để cấu hình task có tên đó.
3. Lấy main đã có; java.srcDir('...') giúp bổ sung source root.
4. register trả provider, trì hoãn khởi tạo/cấu hình cho tới khi cần, giảm công việc không liên quan.
5. Không; extension phải được plugin/task tiêu thụ để ảnh hưởng đến hành vi hoặc artifact.
6. Không; gọi named('dev') { message = ... } trên đối tượng đã tồn tại.
7. Dạng configureEach là API ưu tiên cho lazy configuration; dạng closure trực tiếp có thể cấu hình eagerly nhiều task.

## Tài liệu chính thức để học sâu hơn

- [Gradle User Manual — Writing Build Scripts](https://docs.gradle.org/current/userguide/writing_build_scripts_intermediate.html): extension, plugin và các khối cấu hình của Gradle.
- [Gradle User Manual — Developing Binary Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_binary.html): đăng ký extension và định nghĩa DSL riêng.
- [Gradle User Manual — Collections](https://docs.gradle.org/current/userguide/collections.html): named domain objects, cấu trúc collection, custom container.
- [Gradle User Manual — Gradle Managed Types](https://docs.gradle.org/current/userguide/custom_gradle_types.html): managed property, typed model và object có tên.
- [Gradle User Manual — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): register, named, configureEach và tránh eager configuration.
- [Gradle DSL — NamedDomainObjectContainer](https://docs.gradle.org/current/dsl/org.gradle.api.NamedDomainObjectContainer.html): các phương thức create/register/named/getByName.
- [Gradle API — ObjectFactory](https://docs.gradle.org/current/javadoc/org/gradle/api/model/ObjectFactory.html): cách Gradle tạo typed extension và named container.

**Ghi nhớ:** Extension trả lời câu hỏi **“plugin/dự án này được cấu hình thế nào?”**; named domain object trả lời **“đang cấu hình phần tử tên gì trong collection nào?”**. Groovy DSL dùng closure để biểu đạt ngắn gọn hai việc đó; hiểu rõ chủ sở hữu, tên, kiểu và vòng đời đối tượng mới giúp cấu hình Gradle chính xác, hiệu quả và dễ bảo trì.
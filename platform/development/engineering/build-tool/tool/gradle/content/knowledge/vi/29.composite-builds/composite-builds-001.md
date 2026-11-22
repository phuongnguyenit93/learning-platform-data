# Phân biệt multi-project build với composite build trong Gradle

## 1. Bối cảnh và mục tiêu

Khi một ứng dụng Java bắt đầu có nhiều thành phần, bạn thường muốn tách mã thành các module như **app**, **domain**, **api**, **storage** và **test-support**. Gradle hỗ trợ nhiều cách tổ chức, nhưng hai cách dễ nhầm nhất là:

- **Multi-project build**: một **Gradle build** gồm một root project và nhiều **subprojects**, khai báo bằng **include(...)** trong một settings file.
- **Composite build**: một **build tree** gồm nhiều **Gradle builds độc lập**, kết nối bằng **includeBuild(...)** hoặc tùy chọn **--include-build**; các builds này có thể phối hợp biên dịch, thực thi task và thay thế dependencies bằng local projects.

Tên gọi không chỉ là lựa chọn từ ngữ. Chúng quyết định **đơn vị cấu hình**, **phạm vi của project(':...')**, **cách resolve dependencies**, **cách chạy task**, **cách chia sẻ convention plugins**, **cách build độc lập**, và khả năng làm việc cùng một thư viện mà chưa publish.

Bài học thuộc nhóm **Composite build** trong Build Tool Gradle, tập trung chính xác vào **“Phân biệt multi-project build với composite build”**.

Sau bài học, bạn có thể:

1. Đọc cấu trúc build và xác định nó là single-project, multi-project, composite hay kết hợp cả hai.
2. Phân biệt **project**, **subproject**, **root build**, **included build** và **build tree**.
3. Hiểu khác nhau giữa **include('lib')** với **includeBuild('../lib')**.
4. Biết khi nào dùng **implementation project(':lib')** và khi nào dùng **implementation 'org.example:greeting-lib:1.0.0'**.
5. Giải thích cơ chế **automatic dependency substitution** theo **group + project.name** của included build.
6. Viết **hai ví dụ Java 17 chạy được** — một multi-project, một composite — cho cùng kết quả stdout.
7. Chạy task bằng **:app:run** trong multi-project và bằng **run** hoặc build-tree task path trong composite.
8. Tạo explicit dependency substitution khi publication coordinate không trùng project identity.
9. Phân biệt included build chứa library với included build chứa Gradle convention/plugin logic.
10. Không nhầm task dependency **gradle.includedBuild('...').task(':...')** với dependency Java.
11. Hiểu các giới hạn về configuration isolation, repositories, properties, variants, publication, build paths và concurrency.
12. Lựa chọn kiến trúc phù hợp cho monorepo, nhiều repository, independent releases, CI và local co-development.

## 2. Định nghĩa ngắn gọn

**Multi-project build:** Một Gradle invocation có một settings file gốc khai báo root project và các subprojects. Ví dụ:

~~~groovy
rootProject.name = 'my-system'
include 'app', 'lib', 'shared'
~~~

Đây là **một build** với các project paths **:**, **:app**, **:lib**, **:shared**. Project **:app** tham chiếu project **:lib** bằng:

~~~groovy
dependencies {
    implementation project(':lib')
}
~~~

**Composite build:** Một build chứa hay liên kết tới **những builds khác**, mỗi build có thể có settings và project hierarchy riêng. Ví dụ:

~~~groovy
rootProject.name = 'my-app'
includeBuild('../my-library')
~~~

Nếu **my-library** cung cấp module **org.example:my-library**, app có thể khai báo một dependency thông thường:

~~~groovy
dependencies {
    implementation 'org.example:my-library:1.0.0'
}
~~~

Gradle có thể tự thay dependency tới module đã phát hành bằng một **local project thuộc included build**, không cần publish library trước.

**Điểm mấu chốt:** Multi-project dùng **project dependency trong cùng build**; composite dùng **build inclusion và module dependency substitution giữa các builds**. Đừng coi **includeBuild** là một cách viết khác của **include**.

## 3. Bảng so sánh nhanh

| Khía cạnh | Multi-project build | Composite build |
| --- | --- | --- |
| Thành phần | Root project + subprojects | Một build + các **included builds** độc lập |
| Khai báo trong settings | **include('app', 'lib')** | **includeBuild('../lib')** |
| Số settings files | Thông thường một settings file của build | Mỗi included build có settings file và project hierarchy riêng |
| Dependency Java nội bộ | **project(':lib')** | Module coordinate như **org.example:lib:1.0.0**, được substitution |
| Phạm vi project(':...') | Các projects trong cùng build | Không băng qua build boundary |
| Cấu hình plugins/repos | Có thể cấu hình chung từ root build, nhưng nên ưu tiên conventions có chủ đích | Mỗi build cấu hình độc lập; không tự kế thừa repos/plugins/catalogs |
| Version catalog | Thường có thể dùng chung từ settings của cùng build | Không tự chia sẻ giữa builds |
| Chạy task | **:app:run**, **:lib:test** | **:included-build-name:task** hoặc IncludedBuild task reference |
| Build library độc lập | Có thể chạy task của module; nhưng module nằm trong chung build | Included library có thể mở/chạy với settings riêng |
| Co-development chưa publish | **project dependency** | **Automatic/explicit substitution** |
| Chia sẻ build logic | Convention plugins/subprojects, buildSrc/build-logic | **includeBuild** / **pluginManagement.includeBuild** |
| Release/versioning | Dễ phối hợp một release train, nhưng có thể publish modules riêng | Hợp với các builds có vòng đời/versions độc lập |
| Ranh giới cấu hình | Nhiều projects thuộc cùng Gradle build | Các builds được cấu hình riêng |
| Cấu hình/thao tác từ root | Root có thể cấu hình các subprojects (không nên lạm dụng) | Root không dùng **subprojects{}** để chỉnh included builds |
| Nâng Gradle | Thường một Wrapper cho build | Mỗi build có thể có Wrapper riêng khi chạy standalone |
| Khi nên chọn | Modules trong một sản phẩm, phát triển/phát hành cùng nhau | Tích hợp builds tự chủ, thử library chưa publish, build-logic |

Bảng là **mô hình mặc định**, không phải quy tắc ép buộc. Một **multi-project build cũng có thể nằm trong composite**, và **một included build có thể tự là multi-project build**.

## 4. Hiểu root project, subproject, included build và build tree

### 4.1. Multi-project

~~~text
multi-demo/
├── settings.gradle          <-- một Gradle build
├── build.gradle             <-- optional root configuration
├── app/
│   ├── build.gradle         <-- :app
│   └── src/...
└── lib/
    ├── build.gradle         <-- :lib
    └── src/...
~~~

**settings.gradle** khai báo:

~~~groovy
rootProject.name = 'multi-demo'
include 'app', 'lib'
~~~

Các project paths là:

~~~text
:
:app
:lib
~~~

Task paths ví dụ:

~~~text
:app:compileJava
:app:run
:lib:jar
:lib:test
~~~

Nếu chạy từ thư mục root, **./gradlew :app:run** chọn đúng task **run** ở project **:app**.

### 4.2. Composite với hai builds riêng

~~~text
workspace/
├── greeting-app/
│   ├── settings.gradle      <-- build A: app
│   ├── build.gradle
│   └── src/...
└── greeting-lib/
    ├── settings.gradle      <-- build B: library
    ├── build.gradle
    └── src/...
~~~

**greeting-app/settings.gradle**:

~~~groovy
rootProject.name = 'greeting-app'
includeBuild('../greeting-lib')
~~~

**greeting-lib/settings.gradle**:

~~~groovy
rootProject.name = 'greeting-lib'
~~~

Build A và build B **không trở thành hai subprojects trong một build**. Mỗi build có root project riêng; nếu library có thêm các modules, chính settings của library quyết định subprojects của nó.

### 4.3. Build tree

Khi Gradle tạo một composite, **build tree** gồm:

~~~text
build tree
  |
  +-- root build (greeting-app)
  |     +-- project :
  |
  +-- included build (greeting-lib)
        +-- project :
~~~

Đường dẫn task hiển thị trên toàn build tree có thể mang prefix của included build:

~~~text
:greeting-lib:compileJava
:greeting-lib:jar
:greeting-app:run   # cách hiển thị tùy build tree/CLI context
~~~

Khi gọi task từ **greeting-app root**, task của app là **:run**. Khi cần gọi task của included library từ app, dùng build-tree task path như **:greeting-lib:jar**, hoặc một task dependency được cung cấp qua IncludedBuild API.

**Không đánh đồng task path với project dependency notation**: một build-tree task path có thể truy cập task của included build, nhưng **project(':greeting-lib')** vẫn không phải một Java project dependency từ app sang library.

### 4.4. Composite và multi-project có thể kết hợp

Một included build có thể chứa:

~~~groovy
rootProject.name = 'sdk'
include 'api', 'implementation'
~~~

Khi root build khác dùng **includeBuild('../sdk')**, build **sdk** vẫn có hai subprojects **:api** và **:implementation** riêng của nó. Các task paths có thể là:

~~~text
:sdk:api:compileJava
:sdk:implementation:test
~~~

Các Java consumers ở build khác không dùng **project(':sdk:api')**. Chúng dùng published module coordinates của những project thuộc **sdk**, hoặc khai báo substitution rõ ràng.

## 5. Ý nghĩa chính xác của include và includeBuild

### 5.1. include tạo ProjectDescriptors trong cùng settings hierarchy

~~~groovy
include 'app', 'lib'
~~~

Gradle sẽ tạo các project descriptors với đường dẫn quy ước **app/** và **lib/** (hoặc đường dẫn được tùy biến bằng **project(...).projectDir**).

Ví dụ:

~~~groovy
include 'services:api'
~~~

tương ứng project path **:services:api** và thư mục mặc định **services/api**. Tên có dấu hai chấm trong project path là hierarchy của **một build**.

Từ Gradle 9, project directories được include cần tồn tại và có quyền ghi phù hợp; không dựa vào hành vi các bản cũ từng cho phép missing directories mà không báo lỗi sớm.

### 5.2. includeBuild trỏ vào root directory của một build khác

~~~groovy
includeBuild('../greeting-lib')
~~~

Đường dẫn tương đối được resolve từ directory chứa settings file gọi nó. Nó trỏ tới **build root**, nơi có **settings.gradle** hoặc **settings.gradle.kts** của library, chứ không trỏ trực tiếp tới một subproject tùy ý bên trong library.

Ví dụ sai:

~~~groovy
includeBuild('../greeting-lib/src/main/java')
~~~

Đó không phải thư mục root Gradle build.

### 5.3. CLI --include-build

Bạn có thể tạm đưa một build khác vào invocation:

~~~bash
./gradlew run --include-build ../greeting-lib
~~~

Cách này phù hợp co-development tạm thời khi không muốn sửa settings file. Nhưng khi ứng dụng cần resolve unpublished **plugins { id '...' }**, Gradle khuyến nghị khai báo included plugin build trong **settings.gradle** bằng **pluginManagement.includeBuild** để plugin resolution hoạt động ổn định.

Không dùng **--include-build** như một cơ chế chia sẻ configuration giữa hai builds. Nó tạo composite cho invocation, không biến Gradle projects thành cùng hierarchy.

### 5.4. Đừng khai báo trùng một thư mục thành subproject và included build

Mẫu gây hiểu lầm:

~~~groovy
include 'greeting-lib'
includeBuild('greeting-lib')
~~~

Nếu cùng một Gradle build được đưa vào cả hai vai trò, bạn có thể gặp collision về names/build paths, output contention hoặc cấu hình khó đoán. Phải quyết định library là **subproject của root** hay **included build độc lập**, trừ khi có thiết kế đặc biệt được kiểm soát kỹ.

## 6. Ví dụ hoàn chỉnh A: multi-project Java 17

Ta tạo **một Gradle build** gồm subprojects **:greeting-lib** và **:app**. App gọi class thư viện qua **project(':greeting-lib')**.

### 6.1. Cây thư mục

~~~text
multi-project-lab/
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── greeting-lib/
│   ├── build.gradle
│   └── src/main/java/org/example/greeting/Greeting.java
└── app/
    ├── build.gradle
    └── src/main/java/org/example/app/Main.java
~~~

**Không bắt buộc có root build.gradle** trong lab này. Các subprojects khai báo plugins/Java riêng, root settings đủ để xác định build.

Nếu workspace chưa có Wrapper, dùng Gradle CLI đã cài một lần để tạo bằng **gradle wrapper**, sau đó commit **gradlew**, **gradlew.bat**, **gradle/wrapper/**. Dùng bản Gradle phù hợp với Java 17 và những APIs đang sử dụng.

### 6.2. multi-project-lab/settings.gradle

~~~groovy
rootProject.name = 'multi-project-lab'
include 'greeting-lib', 'app'
~~~

Khai báo **include**, không **includeBuild**. Hai module nằm trong một build với project paths **:greeting-lib** và **:app**.

### 6.3. multi-project-lab/greeting-lib/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

group = 'org.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Java library plugin tạo main/test source sets, tasks compile/packaging và outgoing Java variants. **group/version** được khai báo để library có identity rõ khi xuất bản, nhưng app **không cần một Maven module coordinate** vì nó dùng direct **project dependency**.

### 6.4. multi-project-lab/app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'org.example.app.Main'
}

dependencies {
    implementation project(':greeting-lib')
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Dòng **implementation project(':greeting-lib')** là tâm điểm của multi-project build:

- **project(...)** tìm một Project trong **cùng settings hierarchy**.
- Gradle dùng metadata/variants của outgoing project để đưa các classes/artifacts/dependencies cần thiết lên compile/runtime classpath.
- Khi **:app:compileJava** cần output của library, Gradle sẽ lên lịch những producer tasks phù hợp.
- Không cần publish **greeting-lib** vào Maven Local hay Maven Central trước.

### 6.5. greeting-lib/src/main/java/org/example/greeting/Greeting.java

~~~java
package org.example.greeting;

public final class Greeting {
    private Greeting() {
    }

    public static String hello(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Mã dùng Java standard library, không có external dependencies.

### 6.6. app/src/main/java/org/example/app/Main.java

~~~java
package org.example.app;

import org.example.greeting.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
                "OUTPUT=" + Greeting.hello("Gradle"));
    }
}
~~~

**Stdout chính xác:**

~~~text
OUTPUT=Xin chào, Gradle!
~~~

### 6.7. Lệnh chạy A — Linux/macOS

Chạy từ **multi-project-lab/**:

~~~bash
./gradlew --version
./gradlew projects
./gradlew :greeting-lib:compileJava
./gradlew :app:compileJava
./gradlew :app:run
./gradlew :app:build
./gradlew :greeting-lib:jar
~~~

Task **:app:run** sử dụng runtimeClasspath đã được Gradle resolve, bao gồm compiled library output; console có dòng:

~~~text
OUTPUT=Xin chào, Gradle!
~~~

Gradle có thể in những dòng task status, daemon log, warnings. Khối trên chỉ là **stdout của Java Main**.

### 6.8. Lệnh chạy A — Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :app:compileJava
.\gradlew.bat :app:run
.\gradlew.bat :app:build
~~~

Không cần cài Maven để chạy ứng dụng này; cả hai Java projects đã nằm trong cùng Gradle build.

### 6.9. Kiểm tra task graph và dependencies

~~~bash
./gradlew :app:compileJava --dry-run
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency greeting-lib
~~~

Trong task graph, bạn nên thấy các bước cần thiết để biên dịch library trước khi app tiêu thụ output. **--dry-run chỉ xem task được chọn**, không compile Java và không bảo đảm file output tồn tại.

Trong dependency report, **:greeting-lib** là một **project dependency**, không phải một external JAR đã tải từ repository.

### 6.10. Một root, nhiều project paths

Chạy:

~~~bash
./gradlew projects
~~~

Báo cáo Gradle sẽ liệt kê root project và các subprojects **:app**, **:greeting-lib**. Điều này phù hợp vì hai modules được định nghĩa bởi **một settings.gradle**.

## 7. Ví dụ hoàn chỉnh B: composite build Java 17

Ta xây **hai Gradle builds độc lập** ở cùng cấp trong workspace, dùng một thư viện local **greeting-lib** mà **không publish** trước. Code Java giữ nguyên như ví dụ A để phân biệt **build topology**, không bị nhiễu bởi logic ứng dụng.

### 7.1. Cây thư mục

~~~text
composite-workspace/
├── greeting-app/
│   ├── settings.gradle
│   ├── build.gradle
│   ├── gradlew
│   ├── gradlew.bat
│   ├── gradle/wrapper/...
│   └── src/main/java/org/example/app/Main.java
└── greeting-lib/
    ├── settings.gradle
    ├── build.gradle
    ├── gradlew                 # tùy chọn khi build standalone
    ├── gradlew.bat             # tùy chọn
    ├── gradle/wrapper/...      # tùy chọn
    └── src/main/java/org/example/greeting/Greeting.java
~~~

Mỗi build có **settings.gradle** riêng. Wrapper trong **greeting-app/** được dùng khi chạy composite từ app. Library có thể có Wrapper riêng cho standalone CI; không cần chạy hai wrappers đồng thời trong cùng một invocation.

### 7.2. greeting-lib/settings.gradle

~~~groovy
rootProject.name = 'greeting-lib'
~~~

Tên root project của library là **greeting-lib**. Đây cũng là **project.name** dùng cho default dependency substitution của included build một project.

### 7.3. greeting-lib/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

group = 'org.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Hai giá trị đặc biệt:

- **group = 'org.example'**
- **project.name = 'greeting-lib'** (từ settings)

Cơ chế auto-substitution có thể coi included build này cung cấp module coordinate **org.example:greeting-lib**. **Version** vẫn có ý nghĩa cho publishing, nhưng default auto-substitution chủ yếu match theo **group + name**, không yêu cầu published JAR đã có.

### 7.4. greeting-app/settings.gradle

~~~groovy
rootProject.name = 'greeting-app'
includeBuild('../greeting-lib')
~~~

**includeBuild** được đặt tại app settings, đường dẫn **../greeting-lib** trỏ đến build root của library. Không có **include 'greeting-lib'** ở đây; library không trở thành **:greeting-lib** subproject của app.

### 7.5. greeting-app/build.gradle

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'org.example.app.Main'
}

dependencies {
    implementation 'org.example:greeting-lib:1.0.0'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

**Đây là khác biệt trọng tâm của ví dụ B.**

Ứng dụng khai báo dependency có dạng **group:name:version**, giống như khi tiêu thụ một library từ Maven repository. Nhưng Gradle biết rằng included build **greeting-lib** có local project với **group + name** phù hợp, nên nó tự thay external module dependency bằng local project dependency trong quá trình resolution.

Vì vậy application có thể compile/run mà chưa từng publish **org.example:greeting-lib:1.0.0** lên Maven Central hoặc Maven Local.

**repositories { mavenCentral() }** được khai báo ở app để các external dependencies khác có nơi resolve; nó **không phải nơi library local được publish**. Khi substitution làm việc, Gradle chọn local project mà không cần có published version của chính greeting-lib trên Maven Central.

### 7.6. Java files

**composite-workspace/greeting-lib/src/main/java/org/example/greeting/Greeting.java**:

~~~java
package org.example.greeting;

public final class Greeting {
    private Greeting() {
    }

    public static String hello(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

**composite-workspace/greeting-app/src/main/java/org/example/app/Main.java**:

~~~java
package org.example.app;

import org.example.greeting.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
                "OUTPUT=" + Greeting.hello("Gradle"));
    }
}
~~~

Đây là toàn bộ Java source cần để biên dịch bằng Gradle demo. Không cần một lớp bootstrap khác.

### 7.7. Lệnh chạy B — Linux/macOS

Từ **composite-workspace/greeting-app/**:

~~~bash
./gradlew --version
./gradlew projects
./gradlew :compileJava --dry-run
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency greeting-lib
./gradlew run
./gradlew build
~~~

**Stdout chính xác từ Java Main:**

~~~text
OUTPUT=Xin chào, Gradle!
~~~

Gradle có thể in task names của included build trước khi chạy app; đó là task graph được lập do dependency substitution.

### 7.8. Lệnh chạy B — Windows PowerShell

Từ **composite-workspace\greeting-app**:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :compileJava --dry-run
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat run
.\gradlew.bat build
~~~

**Không** cần chuyển **greeting-lib** thành một subproject. Gradle composite sẽ build local library khi app yêu cầu classes/artifacts thông qua resolved dependency.

### 7.9. Chạy library độc lập

Từ **composite-workspace/greeting-lib/**:

~~~bash
./gradlew build
./gradlew jar
~~~

Nếu library chưa có Wrapper riêng, có thể dùng Gradle CLI đã cài để chạy **gradle build** hoặc tạo Wrapper một lần rồi commit. Library không yêu cầu **greeting-app/settings.gradle** để build các classes của chính nó.

**Đây là năng lực kiến trúc của composite:** mỗi build giữ settings/plugins/repos riêng và có thể mở/test/publish một cách độc lập; composite chỉ kết nối chúng khi cần phát triển/kiểm tra cùng nhau.

### 7.10. Tại sao project(':greeting-lib') sai trong ví dụ B?

Nếu bạn đổi:

~~~groovy
dependencies {
    implementation project(':greeting-lib')
}
~~~

trong **greeting-app/build.gradle**, Gradle sẽ tìm một subproject path **:greeting-lib** trong **settings của greeting-app**. Nhưng settings chỉ có:

~~~groovy
rootProject.name = 'greeting-app'
includeBuild('../greeting-lib')
~~~

Nên không có subproject đó; bạn có thể gặp **UnknownProjectException** hoặc thông báo không tìm thấy Project.

Dùng:

~~~groovy
dependencies {
    implementation 'org.example:greeting-lib:1.0.0'
}
~~~

để Gradle tự substitute local included project bằng cơ chế composite.

## 8. So sánh Java 17 ở mức compiler độc lập

Để thấy rằng khác biệt nằm ở **Gradle topology**, không phải logic Java, bạn có thể biên dịch cùng hai classes bằng JDK 17, không cần Gradle dependency resolution.

### 8.1. Dùng nguồn từ multi-project

Từ **multi-project-lab/** trên Linux/macOS:

~~~bash
mkdir -p out

javac --release 17 -encoding UTF-8 -d out \
  greeting-lib/src/main/java/org/example/greeting/Greeting.java \
  app/src/main/java/org/example/app/Main.java

java -cp out org.example.app.Main
~~~

Stdout:

~~~text
OUTPUT=Xin chào, Gradle!
~~~

### 8.2. Dùng nguồn từ composite

Từ **composite-workspace/**:

~~~bash
mkdir -p out

javac --release 17 -encoding UTF-8 -d out \
  greeting-lib/src/main/java/org/example/greeting/Greeting.java \
  greeting-app/src/main/java/org/example/app/Main.java

java -cp out org.example.app.Main
~~~

Stdout giống hệt:

~~~text
OUTPUT=Xin chào, Gradle!
~~~

### 8.3. Windows PowerShell

Multi-project:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out greeting-lib\src\main\java\org\example\greeting\Greeting.java app\src\main\java\org\example\app\Main.java
java -cp out org.example.app.Main
~~~

Composite, từ **composite-workspace**:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out greeting-lib\src\main\java\org\example\greeting\Greeting.java greeting-app\src\main\java\org\example\app\Main.java
java -cp out org.example.app.Main
~~~

**Ranh giới kiểm chứng:** javac/java thủ công chỉ chứng minh hai Java classes có cú pháp/logic đúng. **Gradle commands** ở mục 6 và 7 mới kiểm chứng task wiring của multi-project, project dependency, included build và dependency substitution.

## 9. Bảng đối chiếu hai ví dụ

| Hạng mục | Multi-project A | Composite B |
| --- | --- | --- |
| Root settings | multi-project-lab/settings.gradle | greeting-app/settings.gradle |
| Thư viện có settings riêng? | Không | Có, greeting-lib/settings.gradle |
| Khai báo trong settings | **include 'greeting-lib', 'app'** | **includeBuild('../greeting-lib')** |
| App project path | **:app** | **:** của greeting-app |
| Library identity trong app build | **project(':greeting-lib')** | **org.example:greeting-lib:1.0.0** |
| Cách Gradle tìm library | Project descriptor trong cùng build | Included build substitution theo group/name |
| Lệnh chạy app | **./gradlew :app:run** | **./gradlew run** |
| Library cần publish trước? | Không | Không |
| Library chạy độc lập ngoài app? | Phụ thuộc cùng settings khi dùng project paths | Có build root/settings riêng |
| Dependency report | Project dependency :greeting-lib | Module dependency được substitute bằng included project |
| Java stdout | OUTPUT=Xin chào, Gradle! | OUTPUT=Xin chào, Gradle! |
| Khi nào đổi sang Maven artifact? | Thường thay project dependency bằng module coordinate | Bỏ includeBuild, giữ module coordinate và có repository chứa artifact |

**Một composite có thể dùng một multi-project build làm included build**. Vì vậy câu hỏi không nên là “composite hay multi-project cái nào mạnh hơn”, mà là “ranh giới tự chủ của các build cần nằm ở đâu?”.

## 10. Automatic dependency substitution hoạt động như thế nào?

Khi thêm:

~~~groovy
includeBuild('../greeting-lib')
~~~

Gradle phân tích projects trong included build để nhận biết những module coordinates mà chúng có thể cung cấp.

Theo cơ chế mặc định:

~~~text
module identity = project.group : project.name
~~~

Ví dụ:

~~~text
included build:
  project.group = org.example
  project.name  = greeting-lib

consumer request:
  org.example:greeting-lib:1.0.0

Gradle resolves to:
  included project greeting-lib
~~~

Điểm quan trọng:

- Default substitution dùng **group + project.name** của included project để match module.
- **Version** trong dependency notation vẫn là phần của requested module coordinate, nhưng default substitution không cần đã publish đúng JAR version ấy.
- Khi đã substitute, Gradle resolve theo local project/variants thay vì tải bản remote của module đó.
- Producer tasks của local project được đưa vào graph khi consumer cần outputs.
- Điều này hỗ trợ vòng lặp **sửa library → chạy app** mà không phải publishToMavenLocal liên tục.

### 10.1. Xác minh substitution từ dependency report

Trong app composite:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency greeting-lib
~~~

Trong dependency graph, một entry có thể biểu thị module request **org.example:greeting-lib:1.0.0** được chuyển thành local project do composite. Cách Gradle hiển thị arrow, project path hoặc selection reason có thể thay theo phiên bản/graph; đừng so sánh console text như một API bất biến.

### 10.2. Tại sao name quan trọng?

Nếu build library có:

~~~groovy
rootProject.name = 'greeting-implementation'
~~~

nhưng app yêu cầu:

~~~groovy
implementation 'org.example:greeting-lib:1.0.0'
~~~

thì **project.name** là **greeting-implementation**, không khớp **greeting-lib**. Default substitution có thể không xảy ra; Gradle sẽ cố resolve external module qua repositories. Nếu artifact chưa publish, build fail.

**Sửa:** đổi tên project cho khớp public coordinate, hoặc khai báo explicit substitution đúng.

### 10.3. Khi publication artifactId khác project.name

Một thư viện có thể publish Maven artifact ID được custom thành **greeting-api**, trong khi tên Gradle project là **greeting-lib**. Default auto-substitution nhìn **project.group/project.name**, không nhất thiết hiểu custom artifactId của MavenPublication.

Cần explicit mapping hoặc đồng bộ identity giữa project và published artifact. Đừng suy **maven-publish** tự cung cấp mọi mapping cần thiết cho composite.

### 10.4. Version conflict và sai lệch với published module

Trong composite, Gradle có thể chọn local included project thay cho published coordinate, và không kiểm tra published JAR remote theo cùng cách. Điều này có nghĩa:

- Consumer có thể build thành công với local source **mới hơn** artifact đã phát hành.
- Khi bỏ includeBuild và quay về published artifact, tests có thể thất bại.
- Một custom publication có POM/variants/capabilities khác local project có thể dẫn đến hai dependency graphs khác nhau.
- Thay một module phụ thuộc transitive có thể làm resolution khác so với production.

Vì vậy trước release, nên có một CI job kiểm thử **published artifacts thực sự** hoặc staging repository, không chỉ build composite từ source.

## 11. Explicit dependency substitution

### 11.1. Khi nào cần?

- **project.name** khác Maven **artifactId**.
- Included build không đặt **group** như published module.
- Một build có nhiều publications từ cùng project.
- Publication dùng variants/configurations khác default project model.
- Có nhu cầu map module cũ sang project mới khi refactor.
- Muốn chỉ định rõ ràng module nào được dùng trong composite.

### 11.2. Ví dụ một library tên khác tọa độ module

Giả sử library build root vẫn tên **greeting-lib**, nhưng consumer đang dùng module public **org.example:greeting-api:1.0.0**.

Thay nội dung **greeting-app/settings.gradle** bằng:

~~~groovy
rootProject.name = 'greeting-app'

includeBuild('../greeting-lib') {
    dependencySubstitution {
        substitute module('org.example:greeting-api') using project(':')
    }
}
~~~

Và trong **greeting-app/build.gradle**:

~~~groovy
dependencies {
    implementation 'org.example:greeting-api:1.0.0'
}
~~~

**Đây là một biến thể thay thế**, không áp dụng đồng thời với dependency **org.example:greeting-lib** của lab B nếu bạn muốn quan sát đúng một mapping. **project(':')** ở trong cấu hình **dependencySubstitution của includeBuild** đề cập tới **root project của included build greeting-lib**, không phải root app. Đây là ngữ cảnh DSL đặc biệt; đừng sao chép nó sang **dependencies { implementation project(':') }**.

### 11.3. Mapping subproject trong included multi-project build

Nếu included build **sdk** có subproject **:api**:

~~~groovy
includeBuild('../sdk') {
    dependencySubstitution {
        substitute module('org.example:sdk-api') using project(':api')
    }
}
~~~

Điều kiện: **../sdk/settings.gradle** thực sự include **api** và project ấy có Java/library component phù hợp. Mapping này thuộc app settings của consumer và chỉ được áp dụng trong composite tương ứng.

### 11.4. Substitution có thể không “truyền ngược” sang standalone build

Quy tắc explicit substitution khai báo ở **greeting-app** không tự xuất hiện khi chạy một invocation riêng bên trong **greeting-lib**. Library vẫn dùng settings/configuration của nó, không biết mọi consumer mappings.

Nếu muốn nhất quán hai hướng, nên thiết kế group/project.name trùng published coordinate để auto-substitution hoạt động tự nhiên. Khi không thể, cần khai báo mappings ở đúng build contexts hoặc dùng công cụ release/testing phù hợp.

## 12. project dependency và module dependency: đừng nhầm hai hình thức

### 12.1. Multi-project direct dependency

~~~groovy
dependencies {
    implementation project(':greeting-lib')
}
~~~

Gradle không cần biết Maven group/artifactId của :greeting-lib để tìm project: **:greeting-lib** là project path trong **settings hierarchy hiện tại**.

### 12.2. Composite dependency

~~~groovy
dependencies {
    implementation 'org.example:greeting-lib:1.0.0'
}
~~~

Gradle nhìn thấy module coordinate rồi áp dụng substitution rules trong build tree khi có included build cung cấp module tương ứng.

### 12.3. Không viết project(':included-build-name:subproject') để đi xuyên biên giới

Sai:

~~~groovy
dependencies {
    implementation project(':greeting-lib')
}
~~~

nếu **greeting-lib** chỉ được thêm bằng **includeBuild**, không bằng **include**. Cú pháp project(...) dùng project path **trong cùng build**; không phải một API truy cập bất kỳ build-tree node nào.

### 12.4. Không dùng dependsOn thay Java dependency

Một lựa chọn sai khác:

~~~groovy
tasks.named('compileJava') {
    dependsOn gradle.includedBuild('greeting-lib').task(':jar')
}
~~~

Dòng này có thể bảo đảm một task được chạy trước, nhưng **không tự đưa library JAR/classes vào Java compiler classpath**. Java cần được khai báo bằng **implementation 'org.example:greeting-lib:1.0.0'** hoặc một dependency model có variants/artifacts phù hợp.

**Task dependency** chỉ mô tả thứ tự/producer task. **Java module dependency** mô tả những classes/artifacts/dependency graph cần cho compile/runtime.

## 13. Gọi task của included build

### 13.1. CLI task path

Từ **greeting-app/**, có thể dùng:

~~~bash
./gradlew :greeting-lib:jar
./gradlew :greeting-lib:compileJava
./gradlew run
~~~

**:greeting-lib** ở đây là tên/build-tree path của included build. Library bản thân có root project **:** khi đứng riêng. Với included multi-project build, đường dẫn có thể có thêm tên subproject, ví dụ **:sdk:api:test**.

### 13.2. IncludedBuild API

Trong **greeting-app/build.gradle**, bạn có thể bổ sung task:

~~~groovy
tasks.register('verifyIncludedLibrary') {
    group = 'verification'
    description = 'Chạy check trong included library build'

    dependsOn gradle.includedBuild('greeting-lib').task(':check')
}
~~~

Sau đó:

~~~bash
./gradlew verifyIncludedLibrary
~~~

Gradle sẽ chạy task **:check** của included build **greeting-lib** theo dependency khai báo. Không dùng **tasks.named(':greeting-lib:check')** để giả nó là task thuộc chính project app; **IncludedBuild.task(...)** là API đúng để tham chiếu task của build khác.

### 13.3. Task cross-build không có nghĩa có project cross-build

Một composite cho phép root orchestration task dependsOn included tasks, ví dụ chạy tests/verification của library và app trong một CI invocation. Nhưng **included build không xuất hiện trong subprojects{} của app** và root không thể dùng **project(':greeting-lib')** theo ý muốn.

### 13.4. Chạy tasks ở một root orchestration build

Một dạng monorepo khác:

~~~text
workspace/
├── orchestration/
│   ├── settings.gradle
│   └── build.gradle
├── application-build/
│   ├── settings.gradle
│   └── build.gradle
└── library-build/
    ├── settings.gradle
    └── build.gradle
~~~

**orchestration/settings.gradle**:

~~~groovy
rootProject.name = 'orchestration'
includeBuild('../application-build')
includeBuild('../library-build')
~~~

**orchestration/build.gradle**:

~~~groovy
tasks.register('verifyAll') {
    dependsOn gradle.includedBuild('application-build').task(':check')
    dependsOn gradle.includedBuild('library-build').task(':check')
}
~~~

Đây là **kiến trúc thay thế** với root orchestrator riêng, yêu cầu hai included builds có tasks **:check** ở root; không sao chép nguyên vào lab A hoặc B vì tên/directory khác. Khi chạy **./gradlew verifyAll** từ orchestration root, Gradle gọi checks của hai builds.

### 13.5. Trùng tên build-tree paths

Tên một included build thường được lấy từ tên thư mục. Nếu hai builds có cùng build path hoặc build path trùng với một root project path, Gradle yêu cầu giải quyết collision.

Ví dụ:

~~~groovy
includeBuild('../library-build') {
    name = 'external-library-build'
}
~~~

Đây là cấu hình minh họa để đổi **build path name** trong composite, **không tự đổi** group/name của published Java module. Build-tree path uniqueness là vấn đề task/project identification; Maven module identity là vấn đề dependency substitution.

## 14. Ranh giới configuration: cùng build và khác build

### 14.1. Multi-project: root có thể quản lý subprojects

Một root build script có thể dùng:

~~~groovy
subprojects {
    repositories {
        mavenCentral()
    }
}
~~~

Cú pháp hợp lệ với một multi-project build, nhưng nhiều dự án hiện đại ưu tiên **dependencyResolutionManagement**, convention plugins và cấu hình từng module để tránh coupling/eager cross-project configuration.

Trong multi-project, root settings có thể khai báo:

~~~groovy
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

và các subprojects trong build dùng policy repositories tương ứng. Đừng dùng **allprojects/subprojects** rộng một cách mặc định khi việc quản lý convention plugin/lazy configuration phù hợp hơn.

### 14.2. Composite: included builds có settings riêng

Nếu **greeting-app** khai báo:

~~~groovy
repositories {
    mavenCentral()
}
~~~

điều đó **không tự áp dụng** vào **greeting-lib**. Tương tự:

- Root **pluginManagement.repositories** không tự chia sẻ với included build.
- Root **dependencyResolutionManagement.repositories** không tự áp vào included build.
- Root **version catalog** không tự trở thành catalog của included build.
- Root **buildSrc** không tự được included build dùng.
- Root **gradle.properties** user-defined values không tự kế thừa sang included builds theo file configuration; các property được truyền qua CLI/system properties có quy tắc riêng.
- Root **subprojects {}** chỉ thao tác trong root build project hierarchy.

Để library có external dependencies, nó cần khai báo repositories hoặc dùng một convention/plugin/thiết lập organization phù hợp **trong chính build của library**.

### 14.3. Cần chia sẻ conventions thì dùng plugin đúng

Nếu hai builds phải thống nhất Java 17, compiler flags, repositories/security rules hoặc dependency version constraints, đừng copy trực tiếp block **subprojects{}** từ app rồi mong Gradle áp cho included library.

Các lựa chọn:

1. Tạo convention plugin độc lập trong **build-logic** và include đúng ở mỗi build.
2. Publish internal Gradle plugin trên plugin repository đáng tin cậy.
3. Dùng organization init scripts hoặc enterprise policies với phạm vi rõ ràng.
4. Dùng version catalogs trong mỗi settings hoặc phát hành catalog phù hợp, không giả chúng tự chia sẻ.
5. Thiết lập CI/toolchain/repository credentials qua cơ chế chung được quản lý, vẫn tôn trọng build isolation.

### 14.4. Properties và CI variables

Với composite, **gradle.properties** của main build không tự trở thành file properties của mọi included build. Trong khi đó **-P** trên Gradle CLI hoặc **-D** JVM system properties có hành vi truyền qua invocation/build tree theo tài liệu Gradle.

Để cấu hình credentials an toàn:

- Cấp secrets qua CI environment/secret manager đúng phạm vi.
- Hạn chế in resolved property values trong build logs.
- Không commit private repository tokens vào từng build.
- Đừng phụ thuộc đường dẫn tuyệt đối tới **~/.gradle/** của một developer.
- Kiểm chứng bằng Gradle Wrapper trong CI trên workspace sạch.

## 15. Composite cho convention plugin và build logic

Một use case rất quan trọng không phải Java library mà là **build logic**.

### 15.1. buildSrc và build-logic

**buildSrc** là một cơ chế Gradle tự phát hiện dành cho build logic. Trong codebase lớn, nhiều team tách custom plugins vào một build độc lập **build-logic** để có ranh giới rõ và quản lý code/test độc lập.

Ví dụ:

~~~text
product/
├── settings.gradle
├── build.gradle
├── app/build.gradle
└── build-logic/
    ├── settings.gradle
    ├── build.gradle
    └── src/main/java/... plugin implementation ...
~~~

Trong settings:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}
~~~

Sau đó một project build script có thể áp dụng plugin ID do build-logic công bố.

### 15.2. pluginManagement.includeBuild cho plugins

Ví dụ trong **settings.gradle**:

~~~groovy
pluginManagement {
    includeBuild('build-logic')

    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

Nếu included plugin build đăng ký plugin ID **org.example.java-conventions**, project build script có thể:

~~~groovy
plugins {
    id 'org.example.java-conventions'
}
~~~

**Lưu ý:** Đây là snippet minh họa; plugin ID **org.example.java-conventions** phải được build-logic thực sự công bố bằng **java-gradle-plugin** hoặc cơ chế phù hợp. Không tự có plugin chỉ vì directory tên build-logic tồn tại.

### 15.3. Settings plugins và thời điểm plugin resolution

Nếu muốn áp dụng một **settings plugin** từ included build trong chính settings script, Gradle hướng dẫn đưa **includeBuild** vào block **pluginManagement** trước block **plugins** sử dụng plugin đó. Chỉ dùng **includeBuild(...)** tùy tiện sau khi settings plugin cần được resolve có thể quá muộn hoặc không hợp lệ với plugin DSL.

### 15.4. includeBuild thường so với pluginManagement.includeBuild

- **includeBuild('library')** tại settings level: thường dùng để đưa library/producer build vào composite, hỗ trợ module dependency substitution.
- **pluginManagement { includeBuild('build-logic') }**: đăng ký plugin-producing build cho plugin resolution trong **plugins {}**.
- Hai trường hợp đều liên quan included builds nhưng mục tiêu khác nhau. Khi plugin được dùng cho build scripts, ưu tiên cách tài liệu khuyến nghị theo plugin resolution lifecycle.

Đừng khai báo plugin ID giả rồi dùng **implementation project(':build-logic')** trong Java application; build logic là Gradle plugin classpath, không phải production Java library.

## 16. Khi nào chọn multi-project?

Multi-project thích hợp khi:

- Các modules là những thành phần của **một sản phẩm**.
- Muốn một settings hierarchy cho toàn hệ thống.
- Dependencies giữa modules phần lớn là **project(...)**.
- Nhóm chấp nhận một release/dependency governance khá đồng bộ.
- Cần task orchestration/IDE import đơn giản cho các modules cùng repository.
- Muốn quản lý chung toolchain, repositories và conventions một cách minh bạch.
- Ranh giới giữa modules chủ yếu là **code architecture**, chưa cần ranh giới **independent build configuration**.

Ví dụ:

~~~text
ecommerce/
  settings.gradle
  domain/
  persistence/
  api/
  web/
  tests/
~~~

Các modules **domain → persistence → web** thường được chỉnh sửa và kiểm tra cùng nhau; có thể dùng project dependencies trực tiếp.

### 16.1. Ưu điểm

- Một hierarchy, dễ đọc project paths.
- Không cần module coordinate chính xác để phụ thuộc module nội bộ.
- Tận dụng variant-aware project dependencies.
- Chung settings giúp giữ quy tắc repository/plugin/version catalogs.
- Task graph được Gradle xây với cross-project dependency relationships trong cùng build.
- Dễ chạy **./gradlew build** trên toàn build theo policies.
- Dễ dạy người mới về Gradle projects/subprojects.

### 16.2. Chi phí/giới hạn

- Root build có thể trở nên lớn nếu quá nhiều subprojects và build logic coupling.
- Root **subprojects{}** cấu hình rộng có thể ảnh hưởng configuration time/isolated projects.
- Một dependency graph dùng nhiều projects khác đội/ngành có thể gây phụ thuộc chéo khó kiểm soát.
- Module version/release independence cần governance riêng dù nằm cùng build.
- Tách module thành library standalone có thể cần refactor settings, publication và CI.

Không suy rằng multi-project luôn chậm; với configuration cache, build cache, lazy configuration và task avoidance tốt, một multi-project build lớn vẫn có thể hoạt động hiệu quả.

## 17. Khi nào chọn composite?

Composite thích hợp khi:

- App dùng một **thư viện độc lập** đang được phát triển song song nhưng chưa publish.
- Các repository/builds có CI, release, group/version hoặc ownership độc lập.
- Monorepo có nhiều self-contained Gradle builds và cần một root điều phối.
- Muốn tách **build-logic/convention plugins** khỏi application projects.
- Cần thử bản local của một module thay bản Maven published trong ngắn hạn.
- Muốn kiểm thử integration giữa builds mà không ép chúng chia sẻ mọi settings.
- Muốn library developers có thể mở/test build riêng trong IDE.

### 17.1. Ưu điểm

- Thay external dependency bằng local source mà không phải publish snapshot liên tục.
- Included builds có settings, scripts, repository policies riêng.
- Ranh giới độc lập giúp codebase lớn chia trách nhiệm.
- Có thể phối hợp một thư viện và nhiều consumers trong cùng build tree.
- Giúp thử thay đổi library/API trực tiếp với ứng dụng sử dụng.
- Tách build logic thành included plugin build rõ ràng.

### 17.2. Chi phí/giới hạn

- Phải hiểu dependency substitution, group/name/project identity.
- Included builds không tự chia sẻ repository/plugin/version catalogs.
- Custom publications/variants có thể khác project substitution.
- CI cần test cả local-substitution mode và published-artifact mode khi quan trọng.
- Build tree paths cần duy nhất.
- Nhiều Gradle invocations cùng include một build có thể gặp concurrent file/project locking conflicts.
- Auto-discovery substitutions có chi phí cấu hình khi included builds quá lớn.
- Không phải plugin ecosystem nào cũng xử lý composite/cross-build tasks giống nhau.

### 17.3. Quyết định bằng câu hỏi

Hỏi theo thứ tự:

1. Hai phần mã có thật sự cần **settings/build lifecycle độc lập** không?
2. Chúng thường được sửa/release cùng nhau hay có versioning riêng?
3. App có tiêu thụ library như **published module coordinate** không?
4. Có cần chạy library standalone mà không biết app không?
5. Có cần thay local source thay artifact từ repository khi phát triển không?
6. Có công việc build-logic/convention plugin cần ranh giới riêng không?
7. CI có thể kiểm thử published artifact contract không?
8. Team có kiểm soát được group/name, substitution, repository policies và build path không?

Nếu phần lớn câu trả lời là “một sản phẩm, cùng cấu hình, liên kết trực tiếp”, hãy bắt đầu với multi-project. Nếu cần “builds tự chủ, local substitution và integration ở ranh giới phát hành”, composite phù hợp hơn.

## 18. Publication và dependency substitution không hoàn toàn giống nhau

### 18.1. project output có thể khác published artifact

Một project **java-library** có API/runtime variants theo Gradle model. Khi được publish bằng **maven-publish**, POM/Gradle Module Metadata có thể được tùy biến:

- Artifact ID đổi tên.
- Dependency declarations bị chỉnh thủ công.
- Một publication xuất nhiều artifacts.
- Capabilities/variants chỉ được công bố tại publication layer.
- Additional classifiers/sources/Javadoc/shadowed artifacts được gắn riêng.
- Một custom configuration được xuất bản thay vì default Java component.

Composite **default project substitution** không nhất thiết tái hiện mọi hành vi của **published module** trong repository. Gradle docs cảnh báo nhiều build có custom publications không tương thích hoàn toàn với default substitution.

### 18.2. “Dùng local” không phải “đang chạy đúng bản đã phát hành”

Ví dụ app yêu cầu:

~~~groovy
implementation 'org.example:greeting-lib:1.0.0'
~~~

và includeBuild tới working tree đang có thay đổi chưa commit. App có thể chạy với source mới chứ không phải JAR **1.0.0** được publish tuần trước. Đây là tính năng rất hữu ích để thử API, nhưng cũng có thể che regression khi deploy.

Vì vậy release verification nên bao gồm:

1. Build/test library.
2. Publish library vào staging repository (hoặc local test Maven repository).
3. Trong một consumer verification job, resolve published/staging artifact đúng coordinate.
4. Chạy unit/integration tests với **published metadata**, không chỉ local project substitution.
5. So sánh dependency graph/runtime behavior khi khác nhau.
6. Phát hành/promote theo checksum/version đã xác minh.

### 18.3. Tắt global substitutions khi thật sự muốn dùng published module

Gradle cho phép tắt rules trên một configuration cụ thể:

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.useGlobalDependencySubstitutionRules = false
}
~~~

**Đây là snippet chẩn đoán/chính sách thay thế, không nên dán vào lab B** vì nó sẽ khiến runtimeClasspath tìm published **org.example:greeting-lib:1.0.0** trong repositories; lab chưa publish nó nên resolution có thể fail.

Khi muốn kiểm thử published build thực tế, phải cấu hình repository có artifact thật và xem xét **mọi configurations cần resolve** (compile/runtime/test/runtime variants), không chỉ một runtimeClasspath. Đừng cho phép một classpath lấy local source còn classpath khác lấy published binary mà không có mục đích rõ.

### 18.4. Không xuất bản local composite như một artifact

**includeBuild** không tự tạo một “composite JAR”. Mỗi project trong mỗi build vẫn có **jar/publish** tasks và publications riêng. Root composite có thể điều phối tasks, nhưng không tự xuất bản nhiều builds thành một Maven coordinate.

Khi cần phát hành nhiều modules, xác định rõ artifact coordinates, versions, repositories và release order của từng build. **Task dependency** không thay thế **publication/dependency metadata**.

## 19. Configuration-on-demand, build performance và isolation

### 19.1. Composite auto-discovery có chi phí

Để tự tìm module identities, Gradle cần kiểm tra projects thuộc included builds. Với included build rất lớn, việc auto-discovery có thể khiến nhiều projects được cấu hình để xác định group/name, dù invocation chỉ cần một library nhỏ.

Theo tài liệu Gradle, khi bật **configuration-on-demand**, **explicit dependency substitutions** có thể giúp tránh phải cấu hình cả included build không cần thiết; ngược lại, rely hoàn toàn vào default discovery có thể làm startup cost lớn.

Không tự kết luận “composite luôn nhanh hơn multi-project”. Hiệu quả thực tế phụ thuộc:

- Số projects/configuration scripts.
- Cách plugin được áp dụng.
- Lazy task registration và configuration avoidance.
- Configuration cache.
- Dependency metadata/variant resolution.
- Reuse outputs/build cache.
- Số included builds được cấu hình.
- CI parallelism và workspace layout.

### 19.2. Configuration cache không biến hai builds thành một

**Configuration cache** lưu/reuse kết quả configuration khi tương thích. Nó không làm included builds chia sẻ root settings, repositories hoặc source sets. Một build plugin sử dụng mutable global state, eager file reads hoặc task graph APIs không đúng có thể làm cache lỗi dù cấu trúc composite hợp lệ.

Đo lường:

~~~bash
./gradlew help --configuration-cache
./gradlew run --configuration-cache
./gradlew run --configuration-cache
~~~

Lệnh thứ ba có thể sử dụng lại cache entry nếu inputs/configuration phù hợp. Đừng tự suy output cache luôn được reuse trong mọi Gradle version/plugin; kiểm tra logs và configuration-cache report thực tế.

### 19.3. Build cache và project outputs

Một **build cache** có thể giúp tái sử dụng task outputs giữa invocations, kể cả khi các builds là standalone/composite, nếu tasks cacheable và inputs/toolchain tương ứng. Nhưng cache không làm thay nhiệm vụ dependency substitution, cũng không thay publication versioning.

### 19.4. Chạy nhiều composite invocations đồng thời

Một included build có thể bị dùng đồng thời bởi hai Gradle invocations ở hai workspace roots khác nhau. Gradle docs cảnh báo multiple composite builds có thể conflict khi chúng include **cùng một physical build** đồng thời, vì project locks không được chia sẻ theo cách đủ bảo đảm giữa invocations.

Trong CI, nên:

- Cấp workspace riêng cho parallel jobs, không cùng ghi output directories.
- Tránh để nhiều invocation khác nhau chạy build outputs cùng vị trí.
- Cân nhắc serialized access hoặc isolated checkouts khi dùng chung physical included library.
- Không xóa build/ của included project trong lúc invocation khác đang dùng nó.
- Kiểm tra Gradle daemon/cache concurrency theo thực tế.

## 20. Build naming và namespace collisions

### 20.1. Task identity trên toàn build tree

Gradle phải xác định duy nhất task/project trong build tree. Nếu root có subproject **:greeting-lib** và một included build cũng tên/path **greeting-lib**, naming collision có thể xảy ra.

Ví dụ:

~~~groovy
includeBuild('../greeting-lib') {
    name = 'local-greeting-source'
}
~~~

Sau khi đổi tên build path, task có thể được chọn qua:

~~~bash
./gradlew :local-greeting-source:jar
~~~

**Nhưng Java dependency coordinate có thể vẫn là org.example:greeting-lib**, vì đổi build path name không tự đổi **project.group/project.name**.

### 20.2. Nested composites được flatten

Một included build có thể tự include build khác. Gradle hiện hành mô tả build tree được flatten cho composite lồng nhau để các included builds có build paths duy nhất. Vì vậy tên build lồng nhau vẫn phải tránh collision trên toàn tree.

Không dùng relative task path hoặc project(...) mơ hồ để đi xuyên các boundary; nên xem **./gradlew projects** và tài liệu Build Tree/IncludedBuild API khi có nghi ngờ.

### 20.3. Đừng đổi directory name một cách tùy tiện

Tên included build path mặc định có thể xuất phát từ directory name. Đổi tên thư mục trong monorepo có thể ảnh hưởng task path, settings inclusion và các CI scripts tham chiếu nó, dù Java module coordinate không đổi.

Giải pháp: dùng **includeBuild('path') { name = 'stable-build-name' }** khi cần một task/build-tree identifier ổn định; đồng thời kiểm soát module identity riêng.

## 21. CI và local development: chiến lược kiểm tra

### 21.1. Multi-project CI

Một pipeline đơn giản:

~~~bash
./gradlew --no-daemon clean build
./gradlew :app:run
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Từ root multi-project, lệnh **build** có thể chạy lifecycle tasks của các subprojects khi được chọn theo conventions. Nếu muốn policy rõ, chỉ định tasks cụ thể (**:app:check**, **:greeting-lib:check**, **:app:assemble**) và thu JUnit reports từng module.

### 21.2. Composite co-development CI

Từ **greeting-app**:

~~~bash
./gradlew --no-daemon run
./gradlew :greeting-lib:check
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency greeting-lib
~~~

Điều này xác nhận local library được dùng khi compile/run app. Nếu cần test API contract như published artifact, thêm job riêng không sử dụng substitution.

### 21.3. CI hai chế độ

Một chiến lược đáng tin cho library phát hành độc lập:

| Chế độ | Cách resolve library | Điều kiểm tra |
| --- | --- | --- |
| **Co-development** | includeBuild → local source | Sửa library/app cùng lúc và phát hiện breakages sớm |
| **Published contract** | module dependency từ staging/release repo | POM/metadata/variants, transitive dependencies và artifact thực |

Chế độ đầu **không thay thế** chế độ sau. Đặc biệt với custom publications, relocated/shadowed variants hoặc platform metadata, sai khác có thể chỉ xuất hiện khi tiêu thụ artifact đã publish.

### 21.4. Không nên tự publishToMavenLocal chỉ để composite chạy

Một antipattern thường gặp:

~~~bash
cd greeting-lib
./gradlew publishToMavenLocal

cd ../greeting-app
./gradlew run
~~~

Với composite đúng và auto-substitution, bạn thường không cần vòng lặp publish/copy JAR này. Việc publishToMavenLocal trước mỗi lần chỉnh source làm mất tính immediate feedback và có thể để lại artifact stale.

Tuy nhiên **publishToMavenLocal/staging** vẫn có mục đích khi bạn chủ động muốn kiểm thử **published artifact contract**. Đừng xóa hoàn toàn những tests ấy vì composite đã chạy.

## 22. Di chuyển từ multi-project sang composite

### 22.1. Bước 1 — Xác định boundary thực

Trước khi tách :greeting-lib ra ngoài:

- Library có người dùng/versioning riêng không?
- Có cần build/test/publish độc lập không?
- Có thư viện chung nào mà library đang ngầm lấy từ root build script không?
- Có plugin/repository/version catalog chỉ được root settings cung cấp không?
- Có task cross-project wiring nào dùng **project(':...')**, **tasks.getByPath**, **subprojects{}** không?

Đây là những ràng buộc phải tách hoặc biểu diễn lại khi đổi build boundary.

### 22.2. Bước 2 — Làm library tự chủ

Thêm vào thư mục library:

~~~text
greeting-lib/settings.gradle
greeting-lib/build.gradle
~~~

Và đảm bảo:

- Plugins/toolchain/repos/dependency constraints được định nghĩa trong build của library.
- **group** và **project.name** khớp module coordinate dự định publish.
- Có Wrapper/test tasks/CI phù hợp cho standalone.
- Không dùng **project(':some-root-module')** sang build cũ.
- Có publication metadata đủ nếu library sẽ được phát hành.

### 22.3. Bước 3 — Thay include bằng includeBuild

Từ:

~~~groovy
rootProject.name = 'multi-project-lab'
include 'app', 'greeting-lib'
~~~

sang một app root settings:

~~~groovy
rootProject.name = 'greeting-app'
includeBuild('../greeting-lib')
~~~

Đây là **hai kiến trúc khác nhau**, không nhất thiết chỉnh đúng hai dòng trong cùng thư mục nếu layout vẫn chưa tách.

### 22.4. Bước 4 — Thay project dependency bằng module coordinate

Từ:

~~~groovy
implementation project(':greeting-lib')
~~~

thành:

~~~groovy
implementation 'org.example:greeting-lib:1.0.0'
~~~

Và kiểm tra group/name của included build. Nếu publication artifactId khác, khai báo explicit substitution.

### 22.5. Bước 5 — Xem lại task references

Những references như:

~~~groovy
tasks.named(':greeting-lib:test')
~~~

trong root project không phải cách an toàn để truy cập một task của included build. Dùng:

~~~groovy
gradle.includedBuild('greeting-lib').task(':test')
~~~

để khai báo cross-build task dependencies khi thật sự cần. Java compile/runtime dependencies vẫn phải đi qua module coordinate.

### 22.6. Bước 6 — Kiểm tra hai modes

- Library chạy standalone.
- App chạy composite khi không có artifact được publish.
- App chạy published/staging module khi không có includeBuild.
- Dependency graph/classpath không thiếu libs.
- CI reports/versions/artifact coordinates ổn định.
- Gradle Wrapper/toolchain và IDE import phù hợp.

Nếu thiếu một bước, chuyển đổi “trông như đã tách directory” nhưng build thực vẫn phụ thuộc cấu hình root cũ.

## 23. Di chuyển từ composite về multi-project

Nếu các builds vốn tách rời giờ thành một sản phẩm có release train chung và luôn phải được thay đổi cùng nhau, có thể gộp vào multi-project.

Hướng làm:

1. Chọn một root settings.
2. Di chuyển các modules vào project directories phù hợp.
3. **include(...)** những module cần vào một build.
4. Chuyển dependencies module coordinate sang **project(...)** khi thích hợp.
5. Di chuyển conventions/plugins/repositories vào một chính sách chung có chủ đích.
6. Xử lý tên project paths và Gradle build scripts còn phụ thuộc standalone settings.
7. Kiểm tra publication coordinates/versioning (việc đổi project.name có thể đổi artifactId).
8. Chạy full compile/test/assemble và kiểm tra dependency report.

**Không bắt buộc** phải xóa khả năng publish library riêng chỉ vì nó trở thành subproject. Multi-project và independent Maven publications không loại trừ nhau.

## 24. Những lỗi thường gặp và cách sửa

| Lỗi hoặc biểu hiện | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| **UnknownProjectException** khi project(':greeting-lib') | Library chỉ là included build | Dùng module coordinate và auto/explicit substitution |
| Gradle cố tải module từ Maven Central | group/name không match included project | Kiểm tra group, rootProject.name, explicit substitution |
| Included build thiếu repositories | Root repositories không tự áp dụng | Khai báo repositories trong included build |
| Included build thiếu plugin version | pluginManagement/version catalogs độc lập | Khai báo riêng hoặc dùng shared convention plugin |
| **:greeting-lib:run** không tồn tại | Library không có application/run task | Chọn :greeting-lib:jar/check hoặc đăng ký task phù hợp |
| Task path collision | Included build name trùng root project path | Đổi build path bằng includeBuild { name = '...' } |
| App compileJava chạy trước library? | Java module dependency chưa khai báo đúng | Dùng implementation GAV/project thay cho dependsOn đơn thuần |
| App tìm thấy library cũ sau khi sửa | Đang dùng remote module, auto-substitution không match | Xem dependencyInsight và settings.includeBuild |
| Build pass composite nhưng fail khi deploy | Local project model khác published artifact | Test staging/published dependency graph |
| buildSrc plugin không có ở included build | buildSrc thuộc build riêng | Chuyển logic vào shared plugin/included build |
| **project(':sdk:api')** fail | Xuyên qua build boundary bằng project notation | Dùng published module coordinate hoặc substitution |
| Included library settings.gradle không được thấy | includeBuild trỏ sai root directory | Chỉnh relative path từ settings file của consumer |
| Composite luôn cấu hình quá nhiều modules | Auto-discovery substitutions trên included multi-project lớn | Xem explicit mappings, lazy config, đo configuration time |
| SNAPSHOT không đổi khi app chạy | Dependency thực vẫn là published snapshot/cache | Xác minh substitution và build-tree tasks |
| Multiple CI jobs gây lock/output conflict | Cùng physical included build bị hai invocations dùng | Dùng isolated checkouts/workspaces |
| Root subprojects{} không ảnh hưởng library | Included build không thuộc root subprojects | Chuyển policy sang convention plugin/own build config |
| gradle.properties root không có trong library | User-defined properties không được chia sẻ bằng file | Định nghĩa tại đúng build hoặc truyền CLI/env theo policy |
| Có Gradle wrapper ở app nhưng library wrapper khác | Standalone builds có toolchain/version riêng | Chuẩn hóa compatibility trong CI, kiểm tra composite |
| **:app:run** fail ở composite sample | App root project là **:**, không có :app subproject | Dùng **./gradlew run** từ greeting-app |
| **./gradlew run** fail ở multi root | run task ở :app, không root | Dùng **./gradlew :app:run** |
| Composite không tự publish library | includeBuild chỉ tích hợp local builds | Dùng maven-publish/release workflow riêng |
| CLI --include-build không cung cấp plugin | Plugin DSL resolution cần settings/pluginManagement | Dùng pluginManagement.includeBuild |
| Published variant không giống local project | Custom publication/metadata không map với default configuration | Explicit mappings + published-contract tests; xem Gradle limitations |
| Project directory missing (Gradle 9+) | include(...) trỏ tới thư mục không tồn tại | Tạo/mapping projectDir chính xác trước build |
| Module name đúng nhưng group sai | Auto-substitution match group + name | Sửa group hoặc explicit mapping |
| Conventions đổi nhưng included build không cập nhật | Build logic nằm trong settings/root của app | Áp dụng plugin ở chính included build hoặc shared build logic |

### 24.1. Quy trình debug ngắn

~~~text
Composite không resolve đúng local library?
             |
             v
1. Consumer settings có includeBuild đúng đường dẫn?
             |
             v
2. Included build có settings.gradle riêng?
             |
             v
3. project.group và project.name đúng module GAV?
             |
             v
4. Dependency declaration là module coordinate?
             |
             v
5. dependencyInsight có ghi nhận project substitution?
             |
             v
6. Có publication artifactId/variant khác project default?
             |
             v
7. Có cần explicit substitution trong settings?
             |
             v
8. Library chạy standalone và app chạy composite?
             |
             v
9. Published-contract tests có chạy với artifact thật?
~~~

### 24.2. Lệnh chẩn đoán

Multi-project:

~~~bash
./gradlew projects
./gradlew :app:compileJava --dry-run
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:run
~~~

Composite từ greeting-app:

~~~bash
./gradlew projects
./gradlew :compileJava --dry-run
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency greeting-lib
./gradlew :greeting-lib:jar
./gradlew run
~~~

**--dry-run** chỉ lập task graph, không chứng minh classes đã được compile hoặc runtime substitution hoạt động đến cùng. Chạy **run** thật và đọc dependency report để kết luận.

## 25. Những ngộ nhận cần tránh

| Ngộ nhận | Sự thật |
| --- | --- |
| “includeBuild tương tự include nhưng thêm dấu Build.” | includeBuild thêm một **build độc lập**, không phải subproject. |
| “Mọi project trong build tree đều dùng project(':...').” | project() chỉ tìm project trong **cùng build hierarchy**. |
| “Composite bắt buộc publish library trước.” | Dependency substitution cho phép dùng local source trực tiếp. |
| “Composite tự chia sẻ plugins/repositories/version catalogs.” | Mỗi included build cấu hình riêng. |
| “Tên build path là Maven artifactId.” | Hai loại identity khác nhau. |
| “Build tree task path là Java dependency coordinate.” | Task selection và dependency resolution là hai cơ chế riêng. |
| “Đã dependsOn included jar thì compile classpath tự có JAR.” | Cần module/project dependency đúng. |
| “Composite local source chắc chắn giống published binary.” | Custom publications/metadata có thể khác. |
| “Multi-project luôn nhanh hơn composite.” | Performance phụ thuộc build logic và các caches. |
| “Composite luôn nhanh hơn multi-project.” | Auto-discovery có thể cấu hình nhiều included projects. |
| “includeBuild giúp root chỉnh mọi subprojects của library.” | Included build không thuộc root subprojects{}. |
| “Không có artifacts remote thì composite không thể chạy.” | Auto-substitution có thể dùng local project không cần publish. |
| “Mỗi included build chỉ có một project.” | Included build có thể là multi-project. |
| “Một root composite tự publish tất cả included builds.” | Publications là trách nhiệm riêng, cần orchestration có chủ đích. |
| “Kotlin/Android/Gradle plugin builds đều dùng chính xác cách Java lab.” | Plugin ecosystems có DSL/variant/lifecycle khác; xem tài liệu tương ứng. |

## 26. Bài tập thực hành

### Bài 1 — Đọc cấu trúc

Cho:

~~~groovy
rootProject.name = 'platform'
include 'api', 'service'
includeBuild('build-logic')
~~~

Hãy chỉ ra **api**, **service**, **build-logic** thuộc loại nào. Vì sao không gọi **project(':build-logic')** như project dependency từ :api nếu build-logic là included build?

### Bài 2 — Chạy multi-project

Tạo lab A, chạy **./gradlew :app:run**, kiểm tra **OUTPUT=Xin chào, Gradle!**. Đổi tên **:greeting-lib** trong settings nhưng không cập nhật dependency của :app: điều gì xảy ra?

### Bài 3 — Chạy composite không publish

Tạo lab B, bảo đảm library chưa có published artifact trong Maven Local. Chạy **./gradlew run** ở greeting-app và kiểm tra stdout. Giải thích tại sao Gradle vẫn biên dịch library.

### Bài 4 — Tạo lỗi project() xuyên build

Đổi dependency B sang:

~~~groovy
implementation project(':greeting-lib')
~~~

Chạy app, đọc lỗi. Khôi phục module coordinate **org.example:greeting-lib:1.0.0**.

### Bài 5 — Đổi group

Đổi library group thành **org.other** nhưng giữ app dependency **org.example:greeting-lib:1.0.0**. Quan sát dependencyInsight và lỗi resolution nếu artifact không có trên repository. Sửa bằng cách đồng bộ group hoặc explicit substitution.

### Bài 6 — Explicit substitution

Cho library tên **greeting-lib** nhưng app yêu cầu **org.example:greeting-api**. Thêm dependencySubstitution trong includeBuild, xác minh **./gradlew run** vẫn in đúng stdout.

### Bài 7 — Task dependency qua IncludedBuild

Đăng ký **verifyIncludedLibrary** như mục 13. Chạy:

~~~bash
./gradlew verifyIncludedLibrary
~~~

Quan sát Gradle gọi **:check** trong included build. Vì sao việc này không thay **implementation module coordinate** trên app compile/runtime classpath?

### Bài 8 — Test published contract

Publish library sang Maven Local hoặc staging theo Maven Publish Plugin, bỏ includeBuild và thêm repository chứa artifact thật. Chạy app từ published JAR. So sánh dependency report và runtime output với composite mode.

### Bài 9 — Monorepo orchestration

Tạo ba builds: orchestration, app và lib. Chạy **verifyAll** để gọi checks của hai included builds. Giải thích vì sao root orchestrator có thể không có Java classes nhưng vẫn giúp CI điều phối.

### Bài 10 — Plugin build logic

Tạo plugin-producing build-logic, include bằng **pluginManagement.includeBuild**, áp dụng custom plugin ID cho một project. Phân biệt plugins resolution với application module dependency substitution.

### Bài 11 — Configuration isolation

Đưa một custom repository vào settings của greeting-app và thử dùng nó trong greeting-lib mà không khai báo lại. Vì sao không hoạt động? Hãy chỉnh từng build một cách có kiểm soát.

### Bài 12 — Build path collisions

Tạo một root subproject có tên trùng với included build path, quan sát Gradle error và sửa bằng **includeBuild { name = '...' }**. Vì sao đổi build path không nhất thiết đổi Maven coordinate?

### Bài 13 — Java 17 độc lập

Biên dịch source từ lab A và B bằng **javac --release 17 -encoding UTF-8**, chạy **java -cp out ...**. Nếu cả hai in cùng stdout, điều đó có chứng minh Gradle composite substitution đúng không? Vì sao cần Gradle run/dependencyInsight?

### Bài 14 — CI hai chế độ

Viết hai CI jobs: một chạy local composite, một chạy consumer trên published library. Chỉ ra failure chỉ xuất hiện ở một chế độ và nguyên nhân tiềm năng: custom publication, version mismatch, transitive dependency hoặc variant metadata.

## 27. Câu hỏi tự kiểm tra

1. Multi-project build được khai báo chủ yếu bằng method nào?
2. Composite build được khai báo chủ yếu bằng method nào?
3. Included build có phải là subproject không?
4. Mỗi included build có settings riêng không?
5. project(':lib') có đi xuyên build boundaries không?
6. Dependency Java của composite consumer thường viết theo dạng nào?
7. Auto-substitution match những yếu tố identity nào?
8. Version trong module coordinate có nhất thiết làm Gradle tải published JAR khi includeBuild đúng không?
9. Có thể dùng CLI option nào để thêm build tạm?
10. Task của included build có thể được gọi theo đường dẫn nào?
11. API nào cho phép dependsOn task của included build?
12. dependsOn included jar có thay Java implementation dependency không?
13. Multi-project và composite có thể kết hợp không?
14. Root repositories có tự áp vào included builds không?
15. Root version catalog có tự áp vào included builds không?
16. buildSrc của main build có tự trở thành build logic của included build không?
17. Khi nào cần explicit dependencySubstitution?
18. project.name khác Maven artifactId có thể gây lỗi gì?
19. Khi nào nên dùng pluginManagement.includeBuild?
20. Composite có tự publish artifact của local library không?
21. Vì sao local composite build có thể khác published release?
22. Khi nào cần test consumer bằng published artifact?
23. Những rủi ro khi hai Gradle invocations cùng include một physical build?
24. Đổi included build name có tự đổi Java module coordinate không?
25. Những yếu tố nào ảnh hưởng tốc độ multi/composite?
26. Vì sao source Java 17 cùng code có thể chạy ở cả hai layouts?
27. Vì sao không nên copy subprojects{} từ root sang composite?
28. Included build có thể là multi-project build không?
29. Khi chuyển từ multi-project sang composite, phải thay đổi dependency notation gì?
30. Điều kiện quan trọng nhất để chọn multi-project hay composite là gì?

**Đáp án gợi ý:** (1) include(...); (2) includeBuild(...); (3) không; (4) có; (5) không; (6) group:name:version; (7) project.group + project.name; (8) không; (9) --include-build; (10) :build-name:task hoặc :build-name:subproject:task; (11) gradle.includedBuild(...).task(...); (12) không; (13) có; (14) không; (15) không; (16) không; (17) coordinate lệch/custom publication; (18) substitution không match; (19) khi include plugin-producing build để resolve plugins DSL; (20) không; (21) project model khác published metadata/working tree; (22) release/staging verification; (23) workspace/output locking conflicts; (24) không; (25) số modules/config/scripts/caches/plugins; (26) build topology khác nhưng Java source giống; (27) build isolation; (28) có; (29) project(':lib') thành module coordinate và includeBuild; (30) mức tự chủ của builds và workflow dependency/version/release.

## 28. Checklist khi thiết kế kiến trúc Gradle

- [ ] Mỗi module cần một project path trong cùng build hay một build độc lập?
- [ ] Thực sự cần **include** hay **includeBuild**?
- [ ] Build root/settings files và project directories được xác định chính xác.
- [ ] Project paths không bị nhầm với build-tree task paths.
- [ ] Multi-project dependencies dùng **project(':...')** đúng project hierarchy.
- [ ] Composite dependencies dùng **module coordinates** và substitution đúng.
- [ ] Included project **group/project.name** phù hợp consumer coordinate.
- [ ] Custom Maven artifactId/variant/publication được kiểm tra để biết có cần explicit mapping.
- [ ] Không cấu hình root **subprojects{}** để hy vọng tác động lên included builds.
- [ ] Mỗi build có repositories/plugins/version catalogs/credentials phù hợp.
- [ ] Không lộ secrets khi chia sẻ configuration qua CLI/env/CI.
- [ ] Convention plugins được đặt trong build-logic đúng API pluginManagement.
- [ ] Cross-build task dependencies dùng IncludedBuild.task thay vì project(...) giả.
- [ ] Build-tree names là duy nhất, không va root project paths.
- [ ] Java toolchain/Gradle Wrapper versions tương thích trên mọi included builds.
- [ ] Standalone included build chạy được mà không dựa vào consumer root.
- [ ] Composite mode chạy được khi library chưa publish.
- [ ] Published-contract mode kiểm thử metadata/artifact thật trước release.
- [ ] CI có reports/evidence cho từng build/test suite cần thiết.
- [ ] Không cho nhiều invocations ghi cùng output directory trong parallel CI.
- [ ] Đo configuration cache/build cache/performance thực tế thay vì giả định.
- [ ] Khi di chuyển build boundary, xem lại publishing, root config và dependency graph.
- [ ] Không gộp hai builds chỉ vì dùng chung thư mục Git; ranh giới Gradle phải phục vụ kiến trúc.

## 29. Tài liệu chính thức

- [Gradle — Composite Builds (Included Builds)](https://docs.gradle.org/current/userguide/composite_builds.html)
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle — Structuring and Organizing Gradle Projects](https://docs.gradle.org/current/userguide/organizing_gradle_projects.html)
- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html)
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Dependency Substitution](https://docs.gradle.org/current/userguide/resolution_rules.html)
- [Gradle — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html)
- [Gradle — Sharing Build Logic with Convention Plugins](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html)
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)

**Kết luận:** **Multi-project build** tổ chức nhiều subprojects bên trong **một Gradle build** và dùng **project(':...')** để mô hình hóa dependencies nội bộ. **Composite build** tổ chức **nhiều Gradle builds độc lập** và dùng **includeBuild(...)** cùng **dependency substitution** để thay module bên ngoài bằng local source mà không cần publish trước. Hai mô hình có thể kết hợp, nhưng không chia sẻ cùng ranh giới project/configuration. Chọn dựa trên quyền tự chủ, cách version/release, nhu cầu local co-development và khả năng kiểm chứng published artifact — không chỉ dựa trên số thư mục trong repository.

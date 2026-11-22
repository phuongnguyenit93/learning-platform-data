# Cách Gradle xác định các project tham gia một build

## 1. Mục tiêu học tập

Trong một repository Java có nhiều thư mục, việc tồn tại thư mục chứa mã nguồn hoặc file **build.gradle** không có nghĩa thư mục đó tự động trở thành một project của Gradle. Gradle cần biết **build nào đang được khởi động**, **project gốc là đâu** và **những project con nào được khai báo tham gia**. Quyết định này xảy ra chủ yếu ở **giai đoạn initialization**, trước khi các task được chọn và chạy.

Sau bài học, bạn có thể:

- Mô tả thứ tự Gradle tìm settings, tạo đối tượng **Settings**, khai báo các **ProjectDescriptor**, rồi tạo **Project** tương ứng.
- Phân biệt **root project**, **subproject**, **project path**, **project directory**, **build script** và **included build**.
- Dùng **settings.gradle** hoặc **settings.gradle.kts** để khai báo đúng project và định vị thư mục khi cấu trúc vật lý không trùng tên logic.
- Giải thích vì sao **include()** khác **includeBuild()**, và vì sao “được đưa vào build” chưa có nghĩa “mọi task của project đó đều chạy”.
- Chẩn đoán project không xuất hiện trong **projects**, thư mục bị thiếu, sai project path hoặc chạy Gradle từ sai điểm bắt đầu.

## 2. Bức tranh tổng thể: Gradle quyết định điều gì và vào lúc nào?

Một lần gọi **./gradlew** không đơn giản là đi tìm mọi file **build.gradle** dưới thư mục hiện tại. Gradle tổ chức công việc theo ba giai đoạn cơ bản:

~~~text
Lệnh ./gradlew ...
       |
       v
INITIALIZATION
  - Xác định build đang làm việc và settings.gradle(.kts)
  - Tạo và chạy đối tượng Settings
  - Xác định root project, subprojects, included builds
  - Tạo mô tả/đối tượng project tham gia
       |
       v
CONFIGURATION
  - Áp dụng build script, plugin và cấu hình task
  - Phân tích yêu cầu task, quan hệ phụ thuộc
  - Xây dựng kế hoạch thực thi task
       |
       v
EXECUTION
  - Thực thi những task cần thiết theo kế hoạch
  - Biên dịch, kiểm thử, đóng gói... nếu được yêu cầu
~~~

**Trọng tâm bài học là initialization.** Câu hỏi của bước này là **“Những project nào tồn tại trong cấu trúc của build đang chạy?”**. Câu hỏi ở configuration/execution mới là **“Task nào cần cấu hình và thực thi?”**.

Ví dụ một build có ba project **:**, **:core** và **:cli**; khi chạy **:cli:run**, Gradle không tự chạy mọi task của cả ba project. Nó chạy task **run** và những task/phụ thuộc thực sự cần, có thể bao gồm biên dịch **:core** khi **:cli** phụ thuộc **:core**.

Gradle có các tối ưu như **configuration cache**; khi cache hợp lệ, cách cấu hình được xử lý lại có thể khác. Điều không đổi là **cấu trúc project của build được khai báo theo settings**, chứ không do một vòng quét ngẫu nhiên tất cả thư mục mã nguồn quyết định.

## 3. Bắt đầu từ đâu: Gradle tìm build và settings

### 3.1. File settings là điểm xác định cấu trúc build

Một root build Java thường có:

~~~text
my-workspace/
├── settings.gradle              # Groovy DSL
├── build.gradle                 # Cấu hình root (có thể không cần)
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── library/
│   └── build.gradle
└── application/
    └── build.gradle
~~~

Dự án dùng **Kotlin DSL** thường có **settings.gradle.kts** và **build.gradle.kts** thay cho hai file cùng tên đuôi **.gradle**. Chọn đúng DSL đang được repo sử dụng; không tạo hai settings file để mô tả hai sơ đồ build cạnh tranh trong cùng root.

Trong mô hình bình thường, Gradle nhận diện settings file của build và đánh giá nội dung của nó. **Settings** khai báo những project sẽ được tạo trong build. File **build.gradle** ở root hoặc subproject tập trung vào **cấu hình plugin, dependencies, tasks**, không phải cơ chế chuẩn để thêm project vào danh sách tham gia.

### 3.2. Root project luôn hiện diện

Khi xây dựng cấu trúc một build, Gradle luôn có **root project**, với project path đặc biệt **:**. Nếu settings ghi:

~~~groovy
rootProject.name = 'my-workspace'
~~~

thì tên root project là **my-workspace**. **Tên** này khác với **project path**: root vẫn có path **:**, không trở thành **:my-workspace**.

Nếu không đặt tên bằng **rootProject.name**, Gradle thường suy ra tên từ thư mục root. Đặt tên minh bạch giúp build ổn định khi thư mục checkout trên CI thay đổi. Project một module đơn giản có thể chạy không cần settings file rõ ràng, nhưng multi-project build nên có **settings.gradle(.kts)** để diễn đạt cấu trúc chính xác.

### 3.3. Thư mục thực thi lệnh không luôn là root project

Bạn có thể chạy lệnh trong root hoặc một subproject. Gradle giải quyết build/settings phù hợp với điểm bắt đầu và các tùy chọn dòng lệnh; vì vậy khi điều tra lỗi, luôn kiểm tra **working directory**, đường dẫn settings và task path. Dùng **-p** (hay **--project-dir**) để chọn thư mục project bắt đầu khi cần:

~~~bash
./gradlew -p ./application tasks
~~~

Lệnh ví dụ chỉ có ý nghĩa khi đường dẫn **./application** thực sự tồn tại và phù hợp cấu trúc build. Trong script CI, cách ít gây nhầm lẫn là chuyển vào thư mục chứa Wrapper/settings của build rồi gọi task bằng đường dẫn tuyệt đối theo hệ phân cấp project, ví dụ **:application:build**.

Nếu một thư mục con có **settings.gradle(.kts)** riêng, đó có thể là một build độc lập; cần phân biệt với subproject thuộc root build đang xét.

## 4. Settings.include(): danh sách project logic tham gia build

### 4.1. Khai báo đơn giản

Ví dụ cấu trúc vật lý:

~~~text
shop/
├── settings.gradle
├── build.gradle
├── catalog/
│   └── build.gradle
└── checkout/
    └── build.gradle
~~~

**settings.gradle** (Groovy DSL):

~~~groovy
rootProject.name = 'shop'
include 'catalog', 'checkout'
~~~

Tương đương với Kotlin DSL trong **settings.gradle.kts**:

~~~kotlin
rootProject.name = "shop"
include("catalog", "checkout")
~~~

Cấu trúc logic của build:

~~~text
:             root project "shop"
├── :catalog  subproject "catalog"
└── :checkout subproject "checkout"
~~~

Để kiểm tra thay vì tự suy đoán:

~~~bash
./gradlew projects
~~~

Task **projects** trình bày danh sách project được khai báo trong build đang chạy. Đây là dấu hiệu rõ ràng hơn việc chỉ thấy các folder trong trình quản lý file.

### 4.2. include() nhận project path, không nhận đường dẫn filesystem

Đây là điểm dễ nhầm nhất. Tham số của **include()** là **project path** trong cấu trúc Gradle, dùng dấu hai chấm **:** phân cấp:

~~~groovy
include ':services:inventory'
~~~

Gradle hiểu project **:services:inventory** có project cha **:services**. Nếu project cha chưa được khai báo riêng, Gradle cũng tạo descriptor tương ứng cho cha. Theo quy ước mặc định:

~~~text
:services            -> <root>/services
:services:inventory  -> <root>/services/inventory
~~~

**Không** viết đường dẫn kiểu **include 'services/inventory'** rồi coi dấu gạch chéo như ngăn cấp project. Cách thể hiện đúng quan hệ Gradle là **:services:inventory**.

Trong Gradle 9.0 trở lên, thư mục của project được include phải **tồn tại và có thể ghi** khi được kiểm tra; đây là ràng buộc chặt hơn các phiên bản cũ. Nếu cấu hình include **:services:inventory**, hãy bảo đảm cả thư mục trung gian được tạo dưới root khi các descriptor dùng vị trí mặc định. Đừng tạo project rỗng vô ý do đánh sai project path.

### 4.3. Thư mục có build.gradle không tự trở thành project

Giả sử repository có:

~~~text
repo/
├── settings.gradle
├── core/build.gradle
├── demo/build.gradle
└── tools/build.gradle
~~~

Với:

~~~groovy
rootProject.name = 'repo'
include ':core', ':demo'
~~~

Danh sách root/subproject của build chính gồm **:**, **:core**, **:demo**; thư mục **tools/** không tự được thêm vì có **tools/build.gradle**. Muốn nó tham gia, cần khai báo rõ **include ':tools'** (nếu thực sự cùng build). Nếu **tools** có settings độc lập và được liên kết bằng **includeBuild**, cách Gradle quản lý nó khác hoàn toàn: đó là included build, xem mục 8.

Kết luận thực tế: khi muốn biết project nào tham gia, **đọc settings file trước**, rồi kiểm tra với **projects**. Không dùng kết quả **find build.gradle** làm danh sách sự thật của Gradle.

## 5. ProjectDescriptor: nối tên logic với thư mục và build script

Khi xử lý **include()**, Gradle tạo mô tả cho từng project. Qua **ProjectDescriptor**, settings có thể xác định **name**, **projectDir** và **buildFileName**. Cần phân biệt ba khái niệm:

| Thuộc tính/khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Project path** | Địa chỉ logic có dấu **:** trong build, dùng để chọn project/task và khai báo dependency. | **:cli**, **:services:api** |
| **Project name** | Tên ngắn của project trong phân cấp. | **cli**, **api** |
| **projectDir** | Thư mục filesystem chứa project và là cơ sở tìm build script. | **apps/console/** |
| **buildFileName** | Tên build script của project, mặc định tùy DSL là **build.gradle** hoặc **build.gradle.kts**. | **build.gradle** |
| **Root project path** | Luôn là ký hiệu **:** của build tương ứng. | **:** |

### 5.1. Đổi projectDir khi thư mục không trùng tên logic

Giả sử muốn project path **:cli** nhưng mã nguồn nằm ở **apps/console/**:

~~~text
repo/
├── settings.gradle
├── build.gradle
└── apps/
    └── console/
        └── build.gradle
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'repo'
include ':cli'
project(':cli').projectDir = file('apps/console')
~~~

Giờ **:cli** là project logic; file build của nó nằm tại **apps/console/build.gradle**. Không cần tạo **repo/cli/** chỉ vì tên project là **:cli**, bởi descriptor đã đổi **projectDir**.

Điều này đặc biệt hữu ích khi layout repo chịu ràng buộc bởi nhóm chức năng, tên thư mục lịch sử hoặc quy ước monorepo, còn tên project Gradle cần ổn định.

### 5.2. Đổi buildFileName khi cần

Ví dụ một project có build script riêng tên **library.gradle**:

~~~groovy
include ':library'
project(':library').projectDir = file('components/library')
project(':library').buildFileName = 'library.gradle'
~~~

Khi đó Gradle tìm **components/library/library.gradle** cho project **:library**. Đây chỉ là ví dụ tùy biến; thông thường nên dùng tên file mặc định để IDE, công cụ và thành viên trong nhóm dễ nhận ra.

### 5.3. Tên, path và thư mục không thể thay thế cho nhau

Trong cùng một build, **:cli** là đường dẫn logic dùng trong:

~~~groovy
dependencies {
    implementation project(':cli')
}
~~~

Tuy nhiên **project(':cli')** chỉ hợp lệ nếu **:cli** đã thực sự được include. Đường dẫn **apps/console/** là một vị trí trên filesystem, không thể thay trực tiếp vào **project(':...')** bằng dấu **/**. Nếu project đổi tên hoặc đổi đường dẫn logic, phải rà soát các chỗ tham chiếu task và dependency theo path.

## 6. Ví dụ Java 17 chạy được: một root và hai subproject

Ví dụ sau tạo build mang tên **discovery-lab**, có thư viện **:engine** và ứng dụng **:cli**. File của ứng dụng ở **apps/console/** nhưng project path được khai báo **:cli**.

### 6.1. Cấu trúc dự án

~~~text
discovery-lab/
├── settings.gradle
├── build.gradle
├── gradlew                         # Sinh bằng Gradle Wrapper
├── gradlew.bat                     # Sinh bằng Gradle Wrapper
├── gradle/wrapper/...              # Sinh bằng Gradle Wrapper
├── engine/
│   ├── build.gradle
│   └── src/main/java/demo/engine/Greeting.java
└── apps/
    └── console/
        ├── build.gradle
        └── src/main/java/demo/cli/Main.java
~~~

Các file Wrapper có thể được sinh bằng lệnh **gradle wrapper** khi máy đã cài Gradle CLI, sau đó được commit vào repository. Khi đã có Wrapper, dùng **./gradlew** trên Unix hoặc **.\gradlew.bat** trên Windows thay vì lệ thuộc vào Gradle toàn cục.

### 6.2. File settings.gradle quyết định project nào tồn tại

~~~groovy
rootProject.name = 'discovery-lab'

include ':engine', ':cli'
project(':cli').projectDir = file('apps/console')
~~~

Sau initialization, Gradle có **ba project** trong build chính:

- **:** là root project, thư mục **discovery-lab/**.
- **:engine** có thư mục **engine/**.
- **:cli** có thư mục **apps/console/**.

Nếu bỏ dòng **include ':engine', ':cli'**, hai folder source vẫn có thể tồn tại, nhưng chúng sẽ không tự trở thành subproject của build chính.

### 6.3. File build.gradle ở root

~~~groovy
plugins {
    id 'base'
}
~~~

Plugin **base** cung cấp một số lifecycle task chung ở root; demo không áp dụng Java plugin cho root vì root chỉ điều phối hai module. Mỗi module tự khai báo plugin phù hợp.

### 6.4. Module thư viện :engine

**engine/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**engine/src/main/java/demo/engine/Greeting.java**:

~~~java
package demo.engine;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Xin chào, " + name + " từ engine!";
    }
}
~~~

Thư viện công khai phương thức **Greeting.message**. Module này không cần **main**; nó được đóng gói thành JAR để project khác dùng.

### 6.5. Module ứng dụng :cli trong thư mục apps/console

**apps/console/build.gradle**:

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':engine')
}

application {
    mainClass = 'demo.cli.Main'
}
~~~

**apps/console/src/main/java/demo/cli/Main.java**:

~~~java
package demo.cli;

import demo.engine.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message("Gradle"));
    }
}
~~~

**implementation project(':engine')** là **project dependency**. Nó dựa vào path logic **:engine**, cho phép Gradle đưa output phù hợp của thư viện lên classpath ứng dụng và sắp xếp các bước biên dịch liên quan. Nó **không** thêm một project mới vào build; việc thêm project đã được thực hiện trong settings.

### 6.6. Chạy và quan sát bằng Gradle

Trong thư mục **discovery-lab/**, sau khi có Wrapper và JDK phù hợp:

**Linux/macOS:**

~~~bash
./gradlew projects
./gradlew :engine:tasks --all
./gradlew :cli:dependencies --configuration runtimeClasspath
./gradlew :cli:run
./gradlew :cli:build
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat projects
.\gradlew.bat :engine:tasks --all
.\gradlew.bat :cli:dependencies --configuration runtimeClasspath
.\gradlew.bat :cli:run
.\gradlew.bat :cli:build
~~~

Quan sát:

1. **projects** liệt kê root **discovery-lab**, **:engine** và **:cli**. Dù file của **:cli** ở **apps/console/**, task path vẫn là **:cli:run**.
2. **:engine:tasks --all** liệt kê task của thư viện; không tự thêm project khác.
3. **:cli:dependencies** cho biết **:cli** phụ thuộc project **:engine** trong runtime classpath.
4. **:cli:run** chạy Java main; stdout do chương trình tự in là:

~~~text
Xin chào, Gradle từ engine!
~~~

Log Gradle có thể có thêm dòng về task, phiên bản, thời gian chạy hoặc cache; chúng không phải là stdout cố định của chương trình.

5. **:cli:build** chạy các task cần thiết để build module ứng dụng và các dependency liên quan. Nếu không có lỗi, Gradle báo **BUILD SUCCESSFUL**. Điều đó không đồng nghĩa mọi task của mọi project đã được chạy.

### 6.7. Đối chứng Java độc lập với Gradle

Mã Java trên dùng duy nhất Java standard library. Có thể biên dịch và chạy bằng **javac/java** trực tiếp để đối chiếu rằng output không phải hành vi riêng của Gradle:

~~~bash
mkdir -p out
javac --release 17 -d out engine/src/main/java/demo/engine/Greeting.java apps/console/src/main/java/demo/cli/Main.java
java -cp out demo.cli.Main
~~~

Dòng in chính xác vẫn là:

~~~text
Xin chào, Gradle từ engine!
~~~

Trên Windows PowerShell, có thể tạo thư mục bằng **New-Item -ItemType Directory -Force out** và chạy hai câu lệnh **javac/java** cùng tham số với dấu **/** hoặc **\** trong đường dẫn. Phần biên dịch tay xác nhận code Java đúng; riêng để kiểm chứng **Gradle phát hiện đúng project**, phải dùng **projects** và các task path được khai báo.

## 7. Project có mặt trong build khác với task được chọn

Hai quyết định dễ bị gộp thành một:

- **Project discovery:** project được đưa vào hệ phân cấp build bằng settings, ví dụ **:engine** và **:cli**.
- **Task selection:** sau khi cấu hình, Gradle quyết định task nào thực hiện dựa vào task người dùng gọi, plugin và quan hệ dependency.

Ví dụ:

~~~bash
./gradlew projects
./gradlew :engine:compileJava
./gradlew :cli:run
./gradlew :cli:build --dry-run
~~~

**projects** giúp quan sát cấu trúc; **:engine:compileJava** chỉ nhắm task của engine và những phụ thuộc bắt buộc của nó; **:cli:run** cần đầu ra của engine; **--dry-run** hiển thị các task dự kiến chạy mà không thực thi hành động task.

Trong multi-project build, tên ngắn như **build**, **test**, **tasks** có quy tắc chọn task theo project hiện tại và cây con. Vì vậy trong CI hoặc tài liệu dùng lâu dài, đường dẫn rõ ràng kiểu **:cli:build** hoặc **:engine:test** thường tránh nhầm lẫn hơn gọi tên trần.

Một project có trong build không nhất thiết có task **test**: nó chỉ có những task mà plugin và build script cung cấp/đăng ký. Root build với plugin **base** trong ví dụ không tự trở thành module Java.

**Task dependency** không nên được dùng để lén thay thế khai báo project. Gradle phải biết project có tồn tại từ settings trước khi **project(':engine')** trong dependency của ứng dụng có thể tham chiếu thành công.

## 8. include() và includeBuild(): hai cấu trúc khác nhau

### 8.1. Multi-project build: include()

~~~groovy
rootProject.name = 'customer-service'
include ':api', ':domain', ':storage'
~~~

Ba subproject nằm trong **cùng một build** dưới root **customer-service**. Chúng chia sẻ một settings model, có thể tham chiếu nhau qua **project(':domain')**, và có project paths thuộc cùng một hệ phân cấp.

### 8.2. Composite build: includeBuild()

~~~groovy
rootProject.name = 'customer-service'
include ':api', ':domain'

includeBuild '../shared-build'
~~~

Đây là **đoạn minh họa**, chỉ dùng nếu **../shared-build** thực sự chứa một Gradle build độc lập có settings/root phù hợp. Lệnh **includeBuild** nhận **đường dẫn thư mục root của một build khác**, không phải project path kiểu **:domain**.

Một **included build** có settings, root project và subproject riêng. Nó tham gia **composite build** nhằm chia sẻ build logic hoặc cho phép dependency substitution giữa các build. Nó **không tự biến thành subproject của root customer-service**, vì vậy không thể mặc định dùng **project(':shared-build')** trong main build chỉ do đã gọi **includeBuild**.

So sánh:

| Góc nhìn | **include(':module')** | **includeBuild('directory')** |
| --- | --- | --- |
| Đối tượng được thêm | Subproject thuộc cùng root build | Một Gradle build độc lập |
| Tham số | Project path dùng dấu **:** | Đường dẫn filesystem tới root included build |
| Nguồn settings | Cùng settings file của main build | Included build có settings/model riêng |
| Địa chỉ dependency | Thường dùng **project(':module')** | Có cơ chế composite dependency substitution hoặc tích hợp build logic |
| Cách quan sát | **./gradlew projects** của main build | Cấu hình composite, các included build và task paths phù hợp |
| Trường hợp thường gặp | Nhiều module cùng một sản phẩm/repo | Thử bản thư viện đang phát triển, dùng build logic riêng |

**includeBuild('build-logic')** thường xuất hiện trong project dùng convention plugins; còn **pluginManagement { includeBuild('build-logic') }** là mẫu sử dụng included build để cung cấp plugin trong giai đoạn plugin resolution. Những trường hợp này phục vụ tổ chức build logic và cần được phân biệt với **include(':build-logic')**, vốn sẽ biến nó thành subproject bình thường.

Thư mục **buildSrc/** cũng có xử lý đặc biệt dành cho build logic trong Gradle. Đừng suy diễn rằng mọi thư mục **buildSrc/** hoặc **build-logic/** đều là subproject ứng dụng; cần kiểm tra settings và cơ chế Gradle tương ứng.

### 8.3. Thế còn pluginManagement và dependencyResolutionManagement?

File settings thường có thêm:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'example'
include ':api', ':domain'
~~~

**pluginManagement** điều khiển cách resolve plugin, còn **dependencyResolutionManagement** điều khiển cách cung cấp repository/dependency policy. Hai block này **không tự khai báo thêm project**. Chính lời gọi **include** và **includeBuild** (hoặc logic tương đương trong settings) quyết định thành phần cấu trúc build.

Đừng nhầm **includeBuild** trong plugin management với chuyện tự thêm project Java để chạy test hoặc xuất bản artifact.

## 9. Cấu trúc có thể phụ thuộc logic settings, nhưng phải có thể dự đoán

Settings file là script Groovy/Kotlin, nên có thể sử dụng điều kiện hoặc logic để quyết định inclusion. Ví dụ Groovy DSL sau chỉ include module **optional-tools** khi thư mục tồn tại:

~~~groovy
rootProject.name = 'conditional-lab'

if (file('optional-tools').isDirectory()) {
    include ':optional-tools'
}
~~~

Ví dụ này **không tự động quét tất cả module**; logic settings đang chỉ rõ điều kiện thêm một module. Tuy nhiên, cấu trúc build thay đổi theo filesystem có thể làm local/CI có danh sách project khác nhau. Chỉ dùng dạng động nếu sản phẩm thật sự yêu cầu; khi build dùng CI và nhiều developer, một **danh sách include có chủ đích, có thể kiểm chứng** thường dễ bảo trì hơn.

Nếu quyết định include phụ thuộc environment variable, tham số Gradle hoặc file generated, phải bảo đảm nguồn đó được kiểm soát và tài liệu hóa. Việc có hoặc không có source file Java bên dưới một thư mục không phải tín hiệu Gradle tự dùng để định danh project.

## 10. Những lỗi thường gặp và cách đọc đúng

| Hiện tượng | Nguyên nhân gần nhất cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Có folder **payment/build.gradle** nhưng **projects** không thấy **:payment** | Chưa **include ':payment'** hoặc đang chạy một build khác | Xem **settings.gradle(.kts)** của build thực tế và dùng **./gradlew projects** |
| **Project with path ':engine' could not be found** | Sai project path, thiếu include hoặc đổi tên project | Kiểm tra tên/path từ **projects**, sửa **include** hay tham chiếu **project(':engine')** |
| **The project directory ... does not exist or is not writable** | Descriptor trỏ tới thư mục thiếu/không ghi được, đặc biệt Gradle 9+ | Kiểm tra **projectDir**, tạo đúng thư mục hoặc sửa mapping, giải quyết quyền |
| **:cli:run** không có task **run** | Project đã include nhưng chưa áp dụng **application** plugin hoặc task khác tên | Đọc **apps/console/build.gradle**, chạy **:cli:tasks --all** |
| Task chạy trên module “khác” kỳ vọng | Dùng tên task trần hoặc đứng ở project khác | Dùng task path đầy đủ như **:cli:build** |
| **:services:api** xuất hiện thêm **:services** | Include project path phân cấp tạo descriptor project cha | Kiểm tra cả thư mục cha và cách tổ chức layout |
| File nằm **apps/console/** nhưng project path **:cli** | **projectDir** được map khác mặc định | Đây có thể là cấu hình đúng; dùng **:cli** khi gọi task/dependency |
| **includeBuild('../tools')** nhưng **project(':tools')** không tồn tại | Included build khác với subproject | Đổi cách kết nối theo composite build hoặc dùng **include** nếu muốn cùng project hierarchy |
| Plugin tải không được nhưng project vẫn đúng | Lỗi plugin repository/credentials/mạng trong quá trình config | Kiểm tra **pluginManagement**, proxy, plugin version; không tự sửa include |
| Mỗi máy thấy project khác nhau | Settings có điều kiện theo file, env hoặc tham số | Ghi lại input settings, thống nhất cấu trúc và kiểm thử trên CI |
| Chạy trong thư mục con thấy root lạ | Đã chọn build khác, có settings riêng hoặc **-p** sai | Kiểm tra điểm bắt đầu, Wrapper và settings của đúng root |

### 10.1. Chuỗi kiểm tra thực tế

~~~text
Không thấy project hoặc gọi task sai?
             |
             v
1. Xác nhận thư mục đang chạy Wrapper và build root
             |
             v
2. Mở settings.gradle(.kts) của build đó
             |
             v
3. Tìm rootProject.name, include, includeBuild
             |
             v
4. Đối chiếu project path với projectDir/buildFileName
             |
             v
5. Kiểm tra thư mục thật có tồn tại/ghi được không
             |
             v
6. Chạy ./gradlew projects
             |
             v
7. Chạy ./gradlew :duong-dan-project:tasks --all
             |
             v
8. Kiểm tra task, plugin và dependency của project
~~~

Ví dụ **:duong-dan-project:tasks** ở bước 7 là ký hiệu chỗ đặt tên; khi dùng thật hãy thay bằng path từ **projects** như **:cli:tasks**. Không dựa vào việc có một file **build.gradle** để kết luận một project đã được đăng ký.

### 10.2. Không chữa lỗi bằng cách thêm include vô tội vạ

Có repo nhiều build độc lập, có module chỉ để sinh code, thư mục chứa test fixture hoặc convention plugins. Việc thêm tất cả chúng bằng **include** có thể tạo ra project sai chức năng, task xung đột hoặc vòng phụ thuộc. Khi không thấy một folder trong **projects**, cần xác định trước folder đó **phải là subproject của build hiện tại hay là included build / công cụ bên ngoài**.

Việc sửa settings ảnh hưởng đến hệ phân cấp project chung: khi đổi path, không quên cập nhật các tham chiếu **project(':...')**, đường dẫn task trong CI và cấu hình IDE/build publication có dựa vào project name.

## 11. Bài tập quan sát và câu hỏi kiểm tra

### Bài tập A: Một folder bị bỏ qua

Tạo root có **settings.gradle**, thư mục **alpha/** và **beta/**, cả hai đều chứa **build.gradle**. Ban đầu settings chỉ viết:

~~~groovy
rootProject.name = 'lab'
include ':alpha'
~~~

Chạy **./gradlew projects**. Sau đó thêm **include ':beta'** và chạy lại. Hãy ghi lại sự khác nhau trong danh sách project. Bạn sẽ thấy **sự tồn tại của build script không tự đủ để trở thành subproject**.

### Bài tập B: Project path tách khỏi thư mục

Trong bài thực hành **discovery-lab**, thay projectDir của **:cli** bằng đường dẫn tới một folder thực sự khác, chuyển đúng source và build script sang đó rồi chạy lại **:cli:run**. Nếu giữ cùng project path và cấu hình chính xác, lời gọi task vẫn là **:cli:run**. Tự giải thích tại sao đường dẫn nguồn thay đổi nhưng project path không đổi.

### Bài tập C: Đọc task graph

Dùng:

~~~bash
./gradlew :cli:build --dry-run
~~~

Xác định những task từ **:engine** xuất hiện khi build **:cli**. So sánh với **./gradlew projects** để chỉ ra: danh sách **project tham gia** và danh sách **task cần chạy** là hai lớp thông tin khác nhau.

### Câu hỏi tự kiểm tra

1. Gradle xác định root/subprojects chủ yếu ở phase nào?
2. Nếu **settings.gradle** có **include ':service:api'**, project path và thư mục mặc định của API là gì?
3. **project(':cli').projectDir = file('apps/console')** thay đổi điều gì, và điều gì giữ nguyên?
4. Khác biệt căn bản giữa **include(':lib')** và **includeBuild('lib-build')**?
5. Vì sao folder tồn tại và có **build.gradle** vẫn có thể không xuất hiện trong **projects**?
6. Nếu **:cli:run** chạy thành công mà **:engine:test** không chạy, có nghĩa **:engine** không tham gia build không?
7. Khi đổi project path, nên kiểm tra những chỗ tham chiếu nào?

**Đáp án gợi ý:** (1) **initialization**; (2) path **:service:api**, thư mục mặc định **service/api** dưới root, project cha **:service** cũng được mô tả; (3) đổi thư mục vật lý, path **:cli** vẫn giữ; (4) thêm subproject cùng build so với thêm một build độc lập trong composite; (5) chưa include hoặc đang chạy build khác; (6) không, project có thể tham gia mà task test của nó không cần chạy; (7) project dependency, task path, CI scripts, cấu hình plugin và IDE có liên quan.

## 12. Những điều cần nhớ

**Settings quyết định cấu trúc**, **build script cấu hình project**, còn **task graph quyết định công việc chạy**. Root project luôn có path **:**; các subproject cần được khai báo rõ qua **include()** (hoặc logic settings tương đương). **Project path** dùng dấu **:** để định danh theo cây logic; **projectDir** cho biết vị trí vật lý và có thể được gán khác mặc định. **includeBuild()** lại nối một build độc lập vào composite, không gắn nó thành subproject của root.

Khi một module “biến mất” trong Gradle, ba thao tác có giá trị nhất là **đọc settings đúng build**, **chạy ./gradlew projects** và **đối chiếu ProjectDescriptor/path với thư mục thật**. Sau khi xác nhận project tồn tại, mới điều tra plugin, dependency và task cụ thể.

### Tài liệu tham khảo chính thức

- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html)
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle — Intro to Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html)
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html)
- [Gradle — Settings API](https://docs.gradle.org/current/javadoc/org/gradle/api/initialization/Settings.html)
- [Gradle — Settings File](https://docs.gradle.org/current/userguide/part4_settings_file.html)

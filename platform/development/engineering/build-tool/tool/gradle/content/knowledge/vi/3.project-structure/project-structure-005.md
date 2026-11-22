# Root project, subproject, đường dẫn thư mục và Gradle project path

## 1. Mục tiêu và bức tranh tổng thể

Trong Gradle, một *build* có thể quản lý một dự án hoặc nhiều dự án con (*multi-project build*). Để hiểu và cấu hình đúng, cần phân biệt bốn khái niệm:

1. **Root project:** dự án gốc của một build, làm điểm đầu của cây project.
2. **Subproject:** một project được khai báo là phần tử con trong cùng build, có cấu hình và task riêng.
3. **Đường dẫn thư mục (filesystem path):** vị trí vật lý trên ổ đĩa, ví dụ `/work/shop/app` hoặc `C:\work\shop\app`.
4. **Gradle project path:** định danh logic của một project trong cây Gradle, ví dụ `:`, `:app` hoặc `:services:billing`; dấu `:` là dấu phân cách cấp, không phải dấu phân cách thư mục.

**Quy tắc cốt lõi:** `settings.gradle` (Groovy DSL) hoặc `settings.gradle.kts` (Kotlin DSL) quyết định project nào tham gia build và mối quan hệ cha–con. Vị trí thư mục thường tương ứng với project path theo quy ước, nhưng có thể cấu hình khác đi.

Hiểu được sự khác biệt này giúp bạn đọc cấu trúc project trong IDE, viết `implementation project(':...')`, chạy đúng task và xử lý lỗi `Project with path '...' could not be found`.

## 2. Một build, nhiều project: ai là gốc, ai là con?

Xét cấu trúc dự án ví dụ:

~~~text
shop/
├── settings.gradle
├── build.gradle
├── app/
│   └── build.gradle
└── catalog/
    └── build.gradle
~~~

Nội dung `shop/settings.gradle`:

~~~groovy
rootProject.name = 'shop'
include(':app', ':catalog')
~~~

Gradle xây dựng cây project logic:

~~~text
:                    root project, name = shop
├── :app             subproject app
└── :catalog         subproject catalog
~~~

- **Build** là toàn bộ cấu hình và vòng đời thực hiện từ settings, một hoặc nhiều project, plugin và task.
- **Root project** vẫn là một `Project` bình thường, có thể có plugin, dependencies, tasks và `build.gradle` riêng. Nó không mặc nhiên chứa toàn bộ mã nguồn của các subproject.
- **Subproject** cũng là một `Project`, không chỉ là “thư mục con”. Chỉ thêm thư mục `reports/` mà không khai báo trong `settings.gradle` sẽ không tạo ra `:reports`.
- Với ví dụ trên, `:app` và `:catalog` là hai project cùng cấp (*siblings*) vì đều là con trực tiếp của `:`. Chúng không tự động phụ thuộc mã nguồn hoặc task của nhau.
- `rootProject.name = 'shop'` đặt **tên** của root project; **project path** của gốc vẫn luôn là `:`, không phải `:shop`.

Root `build.gradle` có thể không tồn tại nếu root chỉ có vai trò điều phối; `settings.gradle` mới là nơi xác định thành viên của multi-project build. Mỗi subproject có thể có `build.gradle` của mình; plugin áp dụng trong một subproject không tự động áp dụng cho các project còn lại.

## 3. Phân biệt project name, project path, projectDir và đường dẫn task

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `rootProject.name` | `shop` | Tên hiển thị và danh tính build gốc |
| `project.name` của `:app` | `app` | Tên project tại nút hiện tại |
| `project.path` | `:app` hoặc `:services:billing` | Địa chỉ logic trong cây project Gradle |
| `project.projectDir` | `/work/shop/app` | Thư mục vật lý của project |
| `rootProject.projectDir` / `rootDir` | `/work/shop` | Thư mục vật lý của root project |
| `layout.projectDirectory` | Directory của project | API Gradle cung cấp vị trí project để xây dựng đường dẫn file |
| `build.gradle` | `app/build.gradle` | Script cấu hình project (Groovy DSL) |
| `settings.gradle` | `shop/settings.gradle` | Script khai báo cấu trúc build và các project tham gia |
| Task name | `compileJava` | Tên một task trong một project |
| Task path | `:app:compileJava` | Định danh task: project path + tên task |

`:` là project path của root project; `:app` là project path của ứng dụng; `:app:run` là **task path**, trỏ tới task `run` thuộc project `:app`. Không được nhầm project `:app:run` với một project con có tên `run` khi đang nói về lệnh chạy task.

**Thư mục và project path có thể giống nhau nhưng không đồng nhất:**

~~~text
Đường dẫn vật lý: /work/shop/services/billing
Gradle project path: :services:billing
Đường dẫn task:   :services:billing:build
~~~

Trên Windows, đường dẫn vật lý dùng ký tự `\`; Gradle project path vẫn dùng dấu `:` trên mọi hệ điều hành.

## 4. Gradle tạo cây project vào thời điểm nào?

Ở mức khái quát, Gradle có ba giai đoạn:

1. **Initialization:** tìm/đọc `settings.gradle(.kts)`, thiết lập root project và các subproject đã `include(...)`; tạo mô tả và đối tượng Project tương ứng.
2. **Configuration:** đánh giá các `build.gradle(.kts)` liên quan, áp dụng plugin, đăng ký/cấu hình task và chuẩn bị task graph.
3. **Execution:** thực hiện các task được yêu cầu cùng các task phụ thuộc cần thiết.

Sự phân chia này giải thích tại sao **đặt một `build.gradle` vào thư mục chưa đủ để thư mục đó thành subproject**: Gradle phải biết đến project đó qua settings trước khi cấu hình build script của nó.

Ví dụ trong `settings.gradle`:

~~~groovy
rootProject.name = 'shop'
include(':app')
~~~

Tệp `catalog/build.gradle` có tồn tại cũng chưa khiến `:catalog` tham gia build nếu chưa được `include(':catalog')`. Ngược lại, khi đã include mà thư mục `catalog/` chưa tồn tại, Gradle 9.0 trở lên kiểm tra nghiêm ngặt hơn: thư mục project phải tồn tại và có thể ghi; không nên tạo project rỗng vô tình.

### Vai trò khác nhau của hai tệp cấu hình

- `settings.gradle` xác định *project nào*, tên root, cách nối project path với thư mục, cùng những thiết lập build như plugin management hoặc dependency resolution management.
- `build.gradle` của mỗi project mô tả *project đó làm gì*: plugin, dependencies, tasks, compiler/toolchain, artifact, test và các tùy chọn build.
- `settings.gradle.kts`/`build.gradle.kts` là các biến thể Kotlin DSL. Ví dụ thực hành bên dưới nhất quán dùng Groovy DSL; chuyển sang Kotlin DSL cần đổi cú pháp cho phù hợp.

## 5. Ví dụ thực hành Java 17: root có app và thư viện

Ví dụ này độc lập và có thể chạy với **JDK 17**, một bản Gradle tương thích hoặc Gradle Wrapper phù hợp. Tạo chính xác cấu trúc sau:

~~~text
structure-demo/
├── settings.gradle
├── build.gradle
├── app/
│   ├── build.gradle
│   └── src/
│       └── main/
│           └── java/
│               └── example/
│                   └── app/
│                       └── Main.java
└── library/
    ├── build.gradle
    └── src/
        └── main/
            └── java/
                └── example/
                    └── library/
                        └── Greeter.java
~~~

### 5.1. Khai báo thành viên của build ở root

`structure-demo/settings.gradle`:

~~~groovy
rootProject.name = 'structure-demo'
include(':app', ':library')
~~~

Hai lời khai báo có ý nghĩa khác nhau: `rootProject.name` đặt tên gốc; `include` khai báo hai subproject. Các thư mục `app/` và `library/` phải được tạo thật trước khi chạy build.

`structure-demo/build.gradle`:

~~~groovy
plugins {
    id 'base'
}
~~~

Ở đây root chỉ áp dụng plugin `base` cho một số task vòng đời nền tảng; root **không chứa** mã Java để biên dịch và không tự động trở thành project Java chỉ vì project con có mã Java. Tệp root này cũng có thể được bỏ đi đối với ví dụ đơn giản, nhưng giữ lại để thấy cấu hình ở root và ở subproject là hai phạm vi riêng.

### 5.2. Khai báo project thư viện

`structure-demo/library/build.gradle`:

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

`structure-demo/library/src/main/java/example/library/Greeter.java`:

~~~java
package example.library;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Hello from library";
    }
}
~~~

Plugin `java-library` cung cấp các task và configurations dành cho thư viện Java. Class `Greeter` là `public` nên project ứng dụng có thể sử dụng khi được đưa vào compile classpath.

### 5.3. Khai báo project ứng dụng

`structure-demo/app/build.gradle`:

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
    mainClass = 'example.app.Main'
}

dependencies {
    implementation project(':library')
}
~~~

`structure-demo/app/src/main/java/example/app/Main.java`:

~~~java
package example.app;

import example.library.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

Dòng `implementation project(':library')` khai báo **project dependency**: `:app` tiêu thụ mã/artifact của `:library`. Nó không tìm thư mục có tên `library` bằng một lệnh mở file thủ công; Gradle phân giải project path trong graph của build.

Gradle sẽ tổ chức các task cần thiết để biên dịch `:library` trước khi phần mã của `:app` cần thư viện đó. Đường dẫn package Java `example.library` **không phải** project path: package dùng dấu chấm và là không gian tên trong mã Java; project path dùng dấu hai chấm và là địa chỉ trong Gradle.

### 5.4. Chạy và xác minh

Ở thư mục `structure-demo/`, nếu đã cài Gradle tương thích, dùng:

~~~bash
gradle projects
gradle :app:run --quiet
gradle :library:jar
gradle :app:dependencies --configuration runtimeClasspath
~~~

Stdout của riêng lệnh `gradle :app:run --quiet` trong ví dụ này:

~~~text
Hello from library
~~~

Các lệnh còn lại chủ yếu in thông tin Gradle, danh sách project, tác vụ hoặc đồ thị dependency, nên nội dung log thay đổi tùy phiên bản và môi trường.

Để dùng **Gradle Wrapper**, trước hết tạo Wrapper khi có Gradle đã cài:

~~~bash
gradle wrapper
~~~

Khi các file wrapper đã được tạo và lưu cùng dự án, sử dụng lệnh tương ứng với hệ điều hành:

~~~bash
# macOS/Linux
./gradlew :app:run --quiet
./gradlew projects

# Windows (PowerShell hoặc cmd)
gradlew.bat :app:run --quiet
gradlew.bat projects
~~~

Wrapper giúp nhóm/CI dùng phiên bản Gradle được dự án chỉ định. Nó **không thay thế JDK phù hợp** để chạy Gradle và biên dịch mã nguồn; cấu hình Java toolchain ở trên yêu cầu có sẵn hoặc có cơ chế cung cấp JDK 17 phù hợp.

### 5.5. Vì sao có thể chạy task của thư viện từ root?

`gradle :library:jar` dùng một task path tuyệt đối: tìm project `:library` rồi chạy task `jar` của project đó. `gradle :app:run` tìm project `:app` rồi chạy task `run` do plugin `application` cung cấp. Bạn không cần `cd library` hoặc `cd app` để chạy từng task.

Nếu chạy `gradle build` từ root, Gradle xử lý task selector `build` trên phạm vi project liên quan trong cây, thường bao gồm các subproject có task mang tên đó. Khi muốn chỉ rõ mục tiêu, viết **fully qualified task path** `:app:build` hoặc `:library:build`. Lưu ý task được chọn vẫn có thể kéo theo task ở project khác qua dependency graph.

## 6. Project path lồng nhiều cấp: đọc như một cây

Giả sử một hệ thống có thư mục:

~~~text
commerce/
├── settings.gradle
├── apps/
│   └── storefront/
│       └── build.gradle
└── services/
    ├── billing/
    │   └── build.gradle
    └── shipping/
        └── build.gradle
~~~

Trong `commerce/settings.gradle`:

~~~groovy
rootProject.name = 'commerce'
include(':apps:storefront')
include(':services:billing', ':services:shipping')
~~~

Bây giờ cây project logic là:

~~~text
:
├── :apps
│   └── :apps:storefront
└── :services
    ├── :services:billing
    └── :services:shipping
~~~

Các nút trung gian `:apps` và `:services` là project trong cây dù không có `build.gradle` riêng. Với Gradle 9+, thư mục của mọi project được khai báo, kể cả cấp trung gian, phải tồn tại và có thể ghi. Các project trung gian không mặc nhiên có task Java vì chưa áp dụng Java plugin.

Cách đọc `:services:billing` là: từ root `:`, đi vào project `services`, rồi đi vào project con `billing`. Dấu `:` đầu tiên giúp nhận diện đường dẫn project tuyệt đối. Một số API/khai báo `include` chấp nhận đường dẫn không có dấu `:` đầu; trong lệnh chạy task và khai báo dependency, viết đầy đủ `:services:billing` để rõ ràng.

Ví dụ đường dẫn task:

~~~bash
gradle :services:billing:tasks
gradle :services:billing:build
~~~

Lệnh thứ hai chỉ có thể thành công khi project `:services:billing` có task `build` (chẳng hạn được tạo bởi plugin `java`, `java-library`, `application` hoặc `base`). Việc có tên project trong settings chưa tự tạo mọi task.

**Quan hệ cha–con không phải quan hệ code dependency.** `:services` là project cha về cấu trúc Gradle; `:services:billing` chưa tự động phụ thuộc output của `:services`, và `:services:shipping` cũng không tự động phụ thuộc `:services:billing`. Muốn dùng thư viện của project khác, hãy khai báo dependency cụ thể.

## 7. Project path không bắt buộc khớp đường dẫn thư mục

Mặc định, Gradle ánh xạ mỗi đoạn của project path thành một đoạn đường dẫn thư mục tương ứng (theo settings directory/root directory). Nhưng đôi khi project được tổ chức vật lý khác với tên logic.

Ví dụ muốn giữ project path `:library` nhưng mã nguồn nằm tại `components/shared-library`:

~~~text
structure-demo/
├── settings.gradle
├── app/
│   └── build.gradle
└── components/
    └── shared-library/
        └── build.gradle
~~~

Thay `settings.gradle` của ví dụ ở mục 5 bằng:

~~~groovy
rootProject.name = 'structure-demo'
include(':app', ':library')

project(':library').projectDir = file('components/shared-library')
~~~

Ở đây:

| Thứ cần tra cứu | Kết quả |
| --- | --- |
| Project path của thư viện | `:library` |
| Project name | `library` |
| Physical project directory | `components/shared-library` |
| Build script mặc định | `components/shared-library/build.gradle` |
| Dependency từ ứng dụng | `implementation project(':library')` |
| Task path của thư viện | `:library:jar` |

Điểm quan trọng là **chỉ đổi nơi Gradle tìm nội dung project**; không cần sửa `implementation project(':library')` trong `app/build.gradle` nếu project path không đổi.

Với ví dụ này, bạn cần thật sự **di chuyển toàn bộ thư mục nội dung thư viện** từ `library/` sang `components/shared-library/`, bao gồm tệp build và mã nguồn. Nếu chỉ sửa `projectDir` nhưng chưa có thư mục đích, Gradle sẽ thất bại do không tìm được thư mục project hợp lệ.

Có thể khai báo project descriptor này trong settings vì tại thời điểm đó Gradle đang xác định thành viên và vị trí của build. Không nên tìm cách “đổi projectDir” trong phần code tùy tiện của các task đã chạy: project directory là thông tin cấu trúc đã được xác lập ở giai đoạn initialization.

### Đổi tên thư mục so với đổi tên project

- Chuyển `library/` thành `components/shared-library/` và sửa `projectDir`: project path có thể giữ nguyên `:library`.
- Thay `include(':library')` bằng `include(':shared')`: project path logic trở thành `:shared`; chỗ tham chiếu `project(':library')` phải được cập nhật phù hợp.
- Thay `rootProject.name`: tên root thay đổi, nhưng root path vẫn `:`; project path `:app` không tự nhiên thành `:new-root-name:app`.

Tên thư mục, tên project và tên artifact (ví dụ JAR) có thể được cấu hình độc lập. Đừng suy ra project path chỉ bằng việc nhìn tên thư mục trong File Explorer.

## 8. Đường dẫn trong build script: tương đối với cái gì?

Sự nhầm lẫn thường xuất hiện khi build script dùng file tương đối.

| Tình huống | Ví dụ | Vị trí cần nghĩ đến |
| --- | --- | --- |
| File thuộc project hiện tại | `file('src/main/resources')` trong `app/build.gradle` | Thư mục project `:app` |
| File thuộc root project | `rootProject.file('config/checkstyle.xml')` | Thư mục root project |
| File trong API layout của project | `layout.projectDirectory.file('src/main/resources/app.yml')` | Directory của project hiện tại |
| Đường dẫn trong settings khi cấu hình descriptor | `project(':app').projectDir = file('modules/app')` | Đường dẫn được giải quyết từ nơi chứa settings |
| Project dependency | `project(':library')` | Project trong graph Gradle, **không phải** file trên đĩa |
| Task gọi từ command line | `:app:compileJava` | Task thuộc project `:app`, **không phải** đường dẫn thư mục |

Đường dẫn tương đối trong `app/build.gradle` thường được giải quyết theo **project directory** của `:app`, không phải thư mục shell nơi bạn đang đứng. Với settings, đường dẫn dùng để ánh xạ descriptor nên được hiểu theo settings directory.

Ví dụ khi thư viện được remap sang `components/shared-library`, trong `components/shared-library/build.gradle`, `file('src/main/java')` vẫn trỏ tới thư mục `components/shared-library/src/main/java`. Nếu viết code phụ thuộc vào thư mục shell hiện tại như `new File('src/main/java')`, có thể tạo hành vi khó dự đoán; nên dùng `layout.projectDirectory` hoặc API `project.file(...)`.

Để kiểm tra vị trí, có thể chạy:

~~~bash
gradle projects
gradle :app:properties
gradle :library:properties
~~~

Trong output của task `properties`, tìm các thuộc tính như `name`, `path` và `projectDir`. Với nhiều dự án lớn, lệnh này có thể in nhiều cấu hình, nên lọc trên terminal nếu cần.

## 9. Task path khác project path và ảnh hưởng của cwd

Tại root của ví dụ `structure-demo`:

~~~bash
gradle :app:compileJava
gradle :app:build
gradle :library:jar
gradle :app:run --quiet
~~~

Đây là các **task path đầy đủ**, vì thế việc chọn task không phụ thuộc vào cách viết tắt tên task. Ví dụ `:app:compileJava` gồm project `:app` và task `compileJava`; còn `:app` chỉ là project path.

Ngược lại:

~~~bash
gradle build
~~~

Là một **task selector không chỉ rõ project**. Khi chạy từ root, Gradle có thể chạy task `build` trên nhiều project trong cây. Phạm vi còn liên quan tới vị trí bạn khởi chạy Gradle. Các task đặc biệt dạng trợ giúp như `help` hoặc `dependencies` có quy tắc chọn/hiển thị hẹp hơn, nên không nên suy từ một lệnh ra mọi lệnh.

Mẹo an toàn khi automation và CI: dùng đường dẫn task đầy đủ, ví dụ `:app:build`, khi bạn muốn mục tiêu rõ ràng. Tuy nhiên chạy `:app:build` có thể kích hoạt các task của `:library` vì `:app` khai báo dependency tới `:library`; đó là quan hệ phụ thuộc thực thi hợp lệ.

**Một trường hợp dễ nhầm:** package Java `example.app`, project path `:app`, class `example.app.Main` và task path `:app:run` là bốn cách đặt tên ở bốn lớp khác nhau. Chúng có thể trùng từ “app” nhưng không được Gradle tự quy đổi qua lại.

## 10. Project relationship, dependency và thư mục độc lập

Trong `settings.gradle`:

~~~groovy
rootProject.name = 'structure-demo'
include(':app', ':library')
~~~

Lời gọi `include` **chỉ thiết lập thành viên/đường dẫn**. Nó không nói `:app` dùng code `:library`. Dòng:

~~~groovy
dependencies {
    implementation project(':library')
}
~~~

Trong `app/build.gradle` mới tạo dependency thực sự giữa hai project. Gradle dựa vào quan hệ đó để giải quyết các thành phần được công bố bởi thư viện (ví dụ Java classes) và sắp xếp các task build cần thiết.

Đừng dùng thao tác chép file JAR thủ công như cách mặc định để hai subproject trao đổi mã khi có thể dùng project dependency. Project dependency giữ được thông tin variant, classpath và quan hệ build rõ ràng hơn.

Nếu có rất nhiều subproject, đừng tạo một khối `allprojects { ... }` lớn ở root chỉ để tiện điều khiển mọi project. Cân nhắc chia sẻ convention thông qua plugin phù hợp hoặc build logic riêng, giữ mỗi project có trách nhiệm rõ và tránh cấu hình chéo không cần thiết. Nguyên tắc này giúp cấu trúc build dễ bảo trì, nhất là khi muốn sử dụng cấu hình song song, build cache hoặc configuration cache.

## 11. Multi-project build và composite build không giống nhau

- **Multi-project build:** một settings file khai báo root và subprojects bằng `include(':app', ':library')`. Các project ở chung một cây Gradle cho build đó.
- **Composite build:** một build có thể tham gia cùng build độc lập khác bằng `includeBuild('build-logic')` hoặc cơ chế tương tự. Build được include có settings, root project và cây project riêng; nó **không đơn giản trở thành subproject** `:build-logic` của root hiện tại.
- **`buildSrc`:** thư mục đặc biệt Gradle có thể tự build để cung cấp build logic cho build chính; không nên nhầm với subproject ứng dụng mà bạn khai báo qua `include(...)`.

Ví dụ ý tưởng trong settings:

~~~groovy
rootProject.name = 'structure-demo'
include(':app', ':library')
includeBuild('build-logic')
~~~

Đoạn này chỉ minh họa cấu trúc: `build-logic/` phải là **một Gradle build hợp lệ, đã được tạo và cấu hình riêng**. Nó không phải project thứ ba cùng cấp theo nghĩa `include(':build-logic')`. Một composite build có cách đặt tên, giải quyết dependency và thực thi task xuyên build riêng; tránh suy ra địa chỉ của included build từ công thức project path của multi-project build.

## 12. Những lỗi thường gặp và cách kiểm tra

### 12.1. `Project with path ':library' could not be found`

**Nguyên nhân thường gặp:** `:library` chưa được khai báo bằng `include` trong settings của build hiện tại, hoặc project đã đổi tên/path nhưng dependency vẫn giữ tên cũ.

**Cách kiểm tra:**
1. Mở đúng `settings.gradle(.kts)` của build.
2. Chạy `gradle projects` để thấy project path có thực.
3. Đối chiếu với `project(':library')` trong dependencies.
4. Khi dùng composite build, xác định lại build nào sở hữu project/coordinate liên quan.

Không giải quyết lỗi này bằng cách chỉ tạo thêm thư mục `library/` trong khi settings vẫn thiếu khai báo.

### 12.2. Project được include nhưng Gradle không tìm thấy thư mục

**Nguyên nhân:** Ánh xạ mặc định từ `:services:billing` tới `services/billing` không đúng layout thật, hoặc thư mục chưa tồn tại/có quyền truy cập không phù hợp. Từ Gradle 9.0, directory của project phải tồn tại và ghi được.

**Cách sửa:** tạo thư mục cần thiết (kể cả thư mục project trung gian), hoặc thiết lập `project(':services:billing').projectDir = file('đường/dẫn/thật')` trong settings. Không đoán đường dẫn từ task path hay package Java.

### 12.3. Có thư mục và `build.gradle` nhưng `gradle projects` không liệt kê

**Nguyên nhân:** chưa `include` project trong settings, hoặc đang gọi Gradle từ build khác.

**Cách sửa:** xác định root/settings thực sự, khai báo project trong settings rồi chạy lại `gradle projects`. Việc file build script tồn tại không đồng nghĩa Gradle đã đưa nó vào cây project.

### 12.4. `Task 'build' not found in project ':x'`

**Nguyên nhân:** project `:x` có tồn tại nhưng chưa áp dụng plugin tạo task `build`, hoặc dùng sai task name.

**Cách sửa:** chạy `gradle :x:tasks --all` để xem task có thật; kiểm tra plugin trong `x/build.gradle`. Đừng đồng nhất sự tồn tại của project với sự tồn tại của task.

### 12.5. Chạy `gradle build` khiến nhiều subproject cùng build

**Nguyên nhân:** lệnh ngắn không có project path được hiểu như task selector trong cây project liên quan.

**Cách sửa:** dùng `gradle :app:build` khi cần chọn đúng project. Nếu dependency bắt buộc phải xây phần của project khác, Gradle vẫn thực hiện các task phụ thuộc hợp lệ.

### 12.6. Dependency giữa hai project không tìm thấy class

**Nguyên nhân có thể:** thiếu `implementation project(':library')`, dùng sai project path, class Java chưa `public`, cấu trúc source set sai, package/import sai hoặc lỗi compilation.

**Cách sửa:** xác minh `gradle projects`, `gradle :app:dependencies --configuration compileClasspath` và `gradle :app:compileJava`; kiểm tra file Java và đúng package. Việc xếp hai thư mục cạnh nhau không tự tạo Java classpath.

### 12.7. Di chuyển thư mục khiến CI hoặc IDE lỗi

**Nguyên nhân:** đã đổi vị trí vật lý nhưng settings, projectDir, đường dẫn đọc file hoặc task script còn phụ thuộc vị trí cũ.

**Cách sửa:** cập nhật ánh xạ trong settings, dùng `project.file(...)`/`layout.projectDirectory` cho file thuộc project, chạy `gradle projects` và build bằng wrapper ở môi trường sạch. Chỉ cập nhật các tham chiếu project path khi bản thân định danh logic thực sự thay đổi.

## 13. Bài tập áp dụng có đáp án

**Bài tập 1 — Phân biệt các loại đường dẫn**

Có root tên `warehouse`, project `:services:stock`, thư mục vật lý mặc định là `/repo/warehouse/services/stock`. Hãy chỉ ra project path của root, project path của stock và task path để build stock.

**Đáp án:** root là `:`, stock là `:services:stock`, task path là `:services:stock:build` (nếu task `build` tồn tại). Tên `warehouse` không xuất hiện trong project path.

**Bài tập 2 — Một thư mục mới có tự thành project không?**

Bạn tạo thư mục `reporting/` và file `reporting/build.gradle` nhưng không sửa settings. Chạy `gradle projects` có chắc thấy `:reporting` không?

**Đáp án:** Không. Cần thêm `include(':reporting')` vào settings của build. Kiểm tra thư mục thật có tồn tại và ghi được.

**Bài tập 3 — Di chuyển thư viện, giữ API dependency**

Ban đầu project `:library` nằm ở `library/`. Bạn muốn chuyển sang `modules/common-lib/` nhưng vẫn giữ `implementation project(':library')`. Sửa phần nào?

**Đáp án:** di chuyển nội dung thư mục và thêm vào `settings.gradle` sau `include(':library')`:

~~~groovy
project(':library').projectDir = file('modules/common-lib')
~~~

Project path logic không thay đổi, vì vậy dòng dependency dùng `:library` vẫn hợp lệ.

**Bài tập 4 — Parent project có đồng nghĩa với Java dependency không?**

Có `:services` và `:services:billing`. Billing có tự được đưa class Java của services vào classpath không?

**Đáp án:** Không. Quan hệ parent–child trong project tree và project dependency là hai quan hệ khác nhau. Phải khai báo dependency phù hợp nếu thật sự cần sử dụng artifact của một project khác.

**Bài tập 5 — Chọn đúng task**

Muốn chỉ yêu cầu Gradle chạy test của `:app` thay vì dùng task selector trên nhiều project, nên gọi thế nào?

**Đáp án:** `gradle :app:test`. Nó chọn task `test` của `:app`; mọi task phụ thuộc thực sự vẫn được chạy theo graph.

## 14. Tóm tắt các quy tắc phải nhớ

1. **Root project có path `:`, dù tên root là gì.**
2. **Subproject là nút được khai báo qua settings**; một thư mục bình thường chưa đủ.
3. **Project path dùng dấu `:`, filesystem path dùng dấu phân cách của hệ điều hành.**
4. **Project path thường ánh xạ tới thư mục tương ứng nhưng có thể đổi bằng `projectDir`** mà không đổi định danh logic.
5. **Task path = project path + task name**; `:app:build` là task, `:app` là project.
6. **Quan hệ cha–con không tự tạo dependency giữa các artifact**; dùng `implementation project(':...')` hoặc configuration phù hợp.
7. **Dùng `gradle projects` để xem graph và task path đầy đủ khi gọi build cụ thể.**
8. **Với Gradle 9+, kiểm tra directory project tồn tại và writable**, nhất là khi dùng đường dẫn nested hoặc remap.

Tài liệu chính thức để tìm hiểu tiếp:
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html)
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html)

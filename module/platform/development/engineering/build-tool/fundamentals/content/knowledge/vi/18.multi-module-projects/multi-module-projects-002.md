# Dự án gốc, mô-đun con và đồ thị phụ thuộc nội bộ

Gradle cho phép tổ chức một hệ thống thành nhiều project nằm trong cùng một build. Cách tổ chức này gọi là **multi-project build**. Mỗi project có thể quản lý một phần mã nguồn, dependency, task và artifact riêng; các project kết nối với nhau bằng **project dependency**.

Trong cấu trúc đó, **root project** là project gốc của build, còn **subprojects** là các project được khai báo trong tệp settings. Root project thường quản lý cấu hình chung và các tác vụ tổng hợp. Subproject thường chứa một thư viện hoặc một phần ứng dụng có thể biên dịch, kiểm thử và đóng gói độc lập.

Để hiểu một build nhiều mô-đun, cần nắm ba lớp cấu trúc: settings xác định những project nào thuộc build; mỗi project có build script và cấu hình riêng; các project dependency mô tả project nào cần đầu ra của project nào. Từ các quan hệ đó, Gradle phân giải dependency và tự thiết lập những task cần chạy theo đúng thứ tự.

## 1. Multi-project build là gì?

Một Gradle build có thể chứa một project hoặc nhiều project. Với ứng dụng nhỏ, một project duy nhất có thể đủ. Khi hệ thống lớn hơn, nhóm có thể tách mã thành các phần như:

- **domain**: mô hình nghiệp vụ và quy tắc cốt lõi.
- **data**: truy cập database hoặc hệ thống lưu trữ.
- **service**: phối hợp các chức năng nghiệp vụ.
- **app**: điểm khởi chạy và kết nối các thành phần.
- **web**: giao diện HTTP hoặc REST API.

Mỗi phần có thể trở thành một Gradle subproject. Các project này cùng thuộc một build, dùng chung Gradle Wrapper và được khai báo trong một settings file.

Ví dụ cấu trúc:

~~~text
shop-platform/
├── gradlew
├── gradlew.bat
├── settings.gradle.kts
├── build.gradle.kts
├── domain/
│   ├── build.gradle.kts
│   └── src/
├── data/
│   ├── build.gradle.kts
│   └── src/
├── service/
│   ├── build.gradle.kts
│   └── src/
└── app/
    ├── build.gradle.kts
    └── src/
~~~

Trong ví dụ này:

- Thư mục **shop-platform/** là thư mục gốc của build.
- Project gốc được gọi là **root project**.
- Các project **domain**, **data**, **service** và **app** là subproject.
- Mỗi subproject có thể có build script riêng.
- Các project có thể khai báo dependency đến project khác trong cùng build.

Multi-project build giúp nhóm phân chia trách nhiệm, giới hạn phạm vi thay đổi, quản lý dependency nội bộ và chỉ chạy các task cần thiết.

## 2. Vai trò của root project

Root project là project có đường dẫn project là **:**. Nó thường tương ứng với thư mục chứa settings file của build.

Các trách nhiệm thường đặt ở root:

- Đặt tên build và khai báo cấu trúc project trong settings.
- Khai báo phiên bản plugin hoặc cấu hình dùng chung.
- Quản lý repository theo chính sách của build.
- Cấu hình quy ước chung cho các subproject.
- Cung cấp task tổng hợp hoặc tài liệu build.
- Tổ chức convention plugin và version catalog.

Root project không bắt buộc phải chứa mã nguồn ứng dụng. Trong nhiều dự án, root chủ yếu là nơi điều phối các subproject.

Ví dụ settings file:

~~~kotlin
rootProject.name = "shop-platform"

include(":domain")
include(":data")
include(":service")
include(":app")
~~~

Sau khi Gradle đọc settings, nó biết build có project gốc tên **shop-platform** và bốn project con với các project path tương ứng.

Build script ở root có thể khai báo plugin nền tảng hoặc cấu hình chung:

~~~kotlin
plugins {
    base
}
~~~

Plugin **base** cung cấp một số lifecycle task như assemble, check và build cho project hiện tại. Việc một task root có tổng hợp task ở subproject hay không còn phụ thuộc cách cấu hình dependency task của build. Không nên giả định chỉ vì một project là root thì mọi task con đều tự động được gọi trong mọi lệnh.

## 3. settings.gradle.kts xác định cấu trúc build

Tệp **settings.gradle.kts** hoặc **settings.gradle** là nơi Gradle xác định các project thuộc build.

Với Kotlin DSL:

~~~kotlin
rootProject.name = "shop-platform"

include(":domain", ":data", ":service", ":app")
~~~

Với Groovy DSL:

~~~groovy
rootProject.name = 'shop-platform'

include 'domain', 'data', 'service', 'app'
~~~

Mỗi lệnh include khai báo một project path. Gradle dùng project path để xác định vị trí mặc định của project trong cây thư mục.

Ví dụ:

| Project path | Thư mục mặc định |
|---|---|
| **:** | Thư mục root |
| **:domain** | **domain/** |
| **:app** | **app/** |
| **:services:api** | **services/api/** |
| **:services:worker** | **services/worker/** |

Project path luôn bắt đầu bằng dấu hai chấm. Dấu hai chấm tiếp theo phân tách các cấp trong cây project.

### Project lồng nhau

Một build có thể tổ chức các subproject theo nhóm:

~~~kotlin
rootProject.name = "shop-platform"

include(":services:api")
include(":services:worker")
include(":libraries:domain")
include(":libraries:security")
~~~

Cấu trúc thư mục mặc định:

~~~text
shop-platform/
├── settings.gradle.kts
├── services/
│   ├── api/
│   └── worker/
└── libraries/
    ├── domain/
    └── security/
~~~

Project path của API là **:services:api**, còn project path của domain là **:libraries:domain**. Tên thư mục và project path mặc định tương ứng với nhau, nhưng có thể tùy chỉnh nếu cấu trúc repository cần khác.

## 4. Tùy chỉnh thư mục của subproject

Đôi khi thư mục mã nguồn hiện có không trùng với cấu trúc mặc định theo project path. Có thể ánh xạ project path đến một thư mục khác trong settings file.

Ví dụ:

~~~kotlin
rootProject.name = "shop-platform"

include(":domain")
project(":domain").projectDir = file("modules/business-domain")

include(":app")
project(":app").projectDir = file("applications/storefront")
~~~

Khi đó:

- Project **:domain** dùng thư mục **modules/business-domain/**.
- Project **:app** dùng thư mục **applications/storefront/**.

Build script mặc định của project vẫn thường có tên **build.gradle.kts** hoặc **build.gradle** trong thư mục project. Có thể đổi tên build file bằng thuộc tính **buildFileName** nếu có lý do rõ ràng, nhưng nên giữ quy ước mặc định để người đọc dễ tìm cấu hình.

Không nên tùy chỉnh project directory chỉ để tạo một cây thư mục phức tạp hơn. Hãy dùng ánh xạ khi repository đã có cấu trúc thực tế cần giữ hoặc khi nhóm muốn tách rõ mã ứng dụng và thư viện.

## 5. Mỗi subproject có build script và cấu hình riêng

Sau khi khai báo trong settings, mỗi subproject có thể có build script riêng.

Ví dụ project domain:

~~~kotlin
plugins {
    id("java-library")
}

group = "com.example.shop"
version = "1.0.0"
~~~

Project data:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation(project(":domain"))
}
~~~

Project service:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation(project(":domain"))
    implementation(project(":data"))
}
~~~

Project app:

~~~kotlin
plugins {
    application
}

dependencies {
    implementation(project(":service"))
}

application {
    mainClass.set("com.example.shop.app.Main")
}
~~~

Mỗi project có thể có plugin, source set, dependency và task riêng. Chẳng hạn, project domain có thể là thư viện Java; project app có thể dùng Application plugin để tạo distribution chạy được.

Project dependency nội bộ được khai báo bằng **project(path)**. Trong Kotlin DSL, ví dụ phổ biến là:

~~~kotlin
implementation(project(":domain"))
~~~

Điều này nói rằng project hiện tại cần output của project domain trên classpath tương ứng với configuration implementation.

## 6. Đồ thị phụ thuộc nội bộ là gì?

Khi một subproject khai báo dependency đến project khác, Gradle hình thành **project dependency graph**. Mỗi nút là một project; mỗi cạnh thể hiện project cần output của project khác.

Giả sử:

~~~text
app
└── service
    ├── domain
    └── data
        └── domain
~~~

Có thể diễn giải:

- App cần service.
- Service cần domain và data.
- Data cũng cần domain.
- Domain là project nền tảng, không phụ thuộc ngược lên service hoặc app.

Một đồ thị có hướng tương ứng:

~~~text
app  -> service
service -> domain
service -> data
data -> domain
~~~

Mũi tên ở đây có nghĩa project bên trái khai báo dependency đến project bên phải. Khi build project app, Gradle cần đầu ra của service; để tạo service, Gradle tiếp tục cần domain và data; để tạo data, Gradle cũng cần domain.

Đồ thị phụ thuộc nội bộ giúp trả lời:

- Project nào cần project nào?
- Thay đổi trong project nền tảng có thể ảnh hưởng những project nào?
- Vì sao một lệnh build ở app kéo task từ domain hoặc data?
- Có dependency vòng khiến các project không thể được xây dựng theo thứ tự hợp lệ không?

## 7. Khai báo project dependency bằng project path

Một project dependency dùng project path để chỉ rõ project đích.

Ví dụ:

~~~kotlin
dependencies {
    implementation(project(":domain"))
}
~~~

Nếu project đích nằm lồng nhau:

~~~kotlin
dependencies {
    implementation(project(":libraries:security"))
}
~~~

Project path phải khớp với project đã khai báo trong settings. Nếu gõ sai tên hoặc project chưa được include, Gradle có thể báo không tìm thấy project.

Project dependency khác external module dependency:

~~~kotlin
dependencies {
    // Project dependency trong cùng build.
    implementation(project(":domain"))

    // External dependency lấy từ repository.
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

Project dependency trỏ đến một project trong cùng multi-project build. External dependency được xác định bằng group, module và version rồi phân giải từ repository.

## 8. Gradle kết nối dependency với task như thế nào?

Khi một project phụ thuộc vào output của project khác, Gradle không chỉ thêm đường dẫn JAR vào classpath. Nó còn thiết lập các task dependency cần thiết để output đó tồn tại trước khi consumer sử dụng.

Ví dụ:

~~~text
:app:compileJava
        |
        | cần output của project :service
        v
:service:jar hoặc output variant phù hợp
        |
        | cần output của project :domain
        v
:domain:jar hoặc output variant phù hợp
~~~

Task cụ thể được chọn phụ thuộc vào plugin, variant và configuration đang phân giải. Với Java plugin, Gradle thường dùng các variant compile hoặc runtime của project producer, rồi nối task tạo output tương ứng vào task graph.

Điều quan trọng là project dependency giúp Gradle biết đầu ra nào cần được tạo và thiết lập quan hệ task tự động. Thông thường không cần tự viết task dependsOn thủ công cho từng bước biên dịch project dependency.

Ví dụ project app:

~~~kotlin
dependencies {
    implementation(project(":service"))
}
~~~

Khi chạy task biên dịch hoặc đóng gói phù hợp của app, Gradle có thể đưa các task cần thiết của service và dependency của service vào task graph.

## 9. Phân biệt project dependency graph và task graph

Hai đồ thị có liên quan nhưng mô tả hai cấp khác nhau.

**Project dependency graph** mô tả quan hệ giữa các project hoặc component. Ví dụ app cần service, service cần domain.

**Task graph** mô tả các task cụ thể được chọn trong một lần chạy Gradle. Ví dụ compileJava, processResources, jar và test.

| Đồ thị | Nút | Câu hỏi được trả lời |
|---|---|---|
| Project dependency graph | Project hoặc component | Project nào sử dụng project nào? |
| Task graph | Task Gradle | Task nào phải chạy và theo thứ tự nào? |

Ví dụ, project app phụ thuộc vào service. Quan hệ này có thể dẫn đến các task compile của service phải hoàn thành trước task compile của app. Nhưng project dependency graph không phải danh sách task; một project có nhiều task, và chỉ một tập con được chọn cho lệnh cụ thể.

Một task cũng có thể phụ thuộc vào task khác trong cùng project mà không tạo project dependency mới. Ví dụ task test phụ thuộc vào task compileTestJava thuộc cùng project.

Khi chẩn đoán build, hãy xác định đang hỏi ở cấp nào:

- Nếu muốn biết vì sao app cần domain, hãy xem project dependency.
- Nếu muốn biết vì sao compileJava chạy trước test, hãy xem task dependency.
- Nếu muốn biết task nào được chọn khi gọi build, hãy xem task graph của lệnh đó.

## 10. Project dependency và variant

Gradle không chỉ nhìn project đích như một thư mục có JAR. Khi dùng các plugin có hỗ trợ variant, Gradle chọn output phù hợp với configuration của consumer.

Ví dụ Java project có các nhu cầu khác nhau:

- Compile classpath cần API và class cần thiết khi biên dịch.
- Runtime classpath cần các dependency và output để thực thi.
- Test classpath cần thêm output và dependency của test source set.

Gradle Java plugin cung cấp các variant phù hợp cho những mục tiêu này. Khi app khai báo:

~~~kotlin
dependencies {
    implementation(project(":domain"))
}
~~~

Gradle phân giải project dependency theo attributes và variant phù hợp với configuration đang dùng. Nhờ đó, compile task có thể nhận compile variant, còn runtime task nhận runtime variant.

Nếu project producer dùng Java Library plugin, có thể khai báo API và implementation dependency để kiểm soát những dependency nào được xuất ra cho consumer.

## 11. api và implementation giữa các project

Với plugin **java-library**, hai configuration quan trọng là **api** và **implementation**.

- **api** dùng cho dependency là một phần của API công khai của thư viện và cần xuất hiện trên compile classpath của consumer.
- **implementation** dùng cho dependency nội bộ của thư viện; consumer vẫn nhận dependency cần thiết ở runtime nhưng không cần dependency đó trên compile classpath chỉ vì thư viện dùng nó bên trong.

Ví dụ project domain cung cấp một kiểu public dựa trên module khác:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api(project(":shared-model"))
}
~~~

Nếu public API của domain có kiểu thuộc shared-model, consumer cần đọc kiểu đó khi biên dịch. Khi đó api có thể phù hợp.

Nếu domain chỉ sử dụng một thư viện nội bộ trong implementation:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

Consumer của domain không cần đưa commons-lang3 vào compile classpath chỉ vì domain sử dụng nó bên trong.

Với app, thông thường khai báo dependency trực tiếp theo cách app sử dụng:

~~~kotlin
dependencies {
    implementation(project(":service"))
}
~~~

Không nên dùng api ở mọi nơi. Đưa dependency vào API surface quá rộng làm tăng coupling và có thể khiến thay đổi nội bộ của một project lan ra nhiều consumer.

## 12. Dependency graph nên có hướng rõ ràng và tránh chu trình

Một đồ thị dependency tốt thường có hướng từ lớp ứng dụng đến các lớp nền tảng:

~~~text
app
 |
 v
service
 |       \
 v        v
domain   data
           |
           v
         domain
~~~

Project nền tảng không nên phụ thuộc ngược vào project ứng dụng. Ví dụ, nếu domain cần service trong khi service lại cần domain, đồ thị sẽ có chu trình:

~~~text
domain -> service
   ^         |
   |         v
   +---------+
~~~

Chu trình project dependency thường dẫn đến task dependency cycle hoặc mô hình module khó phân giải. Gradle cần xác định đầu ra nào phải có trước, nhưng các project lại chờ lẫn nhau.

Cách xử lý thường là:

- Chuyển abstraction hoặc interface chung sang một project nhỏ hơn.
- Tách API khỏi implementation.
- Đảo chiều dependency bằng interface hoặc dependency injection.
- Gom hai phần có vòng phụ thuộc chặt thành một project nếu ranh giới tách không hợp lý.
- Đặt project nền tảng ở tầng dưới và project điều phối ở tầng trên.

Ví dụ sau khi tách interface:

~~~text
app -> service -> domain-api
data -> domain-api
~~~

Service phụ thuộc abstraction; data triển khai abstraction. Domain API không phụ thuộc ngược vào service hoặc data.

## 13. Root project, allprojects và subprojects

Gradle cung cấp các khối cấu hình để áp dụng thiết lập cho nhiều project.

### allprojects

Khối **allprojects** áp dụng cho root project và các subproject thuộc build:

~~~kotlin
allprojects {
    group = "com.example.shop"
    version = "1.0.0"
}
~~~

Ví dụ này đặt group và version cho tất cả project trong build.

### subprojects

Khối **subprojects** chỉ áp dụng cho các project con:

~~~kotlin
subprojects {
    tasks.withType<Test>().configureEach {
        useJUnitPlatform()
    }
}
~~~

Ví dụ này cấu hình JUnit Platform cho các Test task thuộc subproject. Root project không bị áp dụng cấu hình đó bởi khối subprojects.

### Dùng cấu hình chung có chủ đích

Có thể cấu hình repository ở root hoặc qua settings theo chính sách repository tập trung. Tuy nhiên, không nên đưa mọi cấu hình của mọi project vào một khối lớn. Khi dự án phát triển, các subproject có thể cần plugin, test framework hoặc dependency khác nhau.

Cấu hình dùng chung nên có phạm vi rõ ràng:

- Group, version hoặc convention chung có thể được quản lý tập trung.
- Repository có thể được kiểm soát từ settings.
- Plugin và quy ước build nên được đóng gói thành convention plugin.
- Dependency cụ thể vẫn nên khai báo ở project thực sự sử dụng chúng.

## 14. Convention plugin cho cấu hình lặp lại

Nếu nhiều subproject dùng cùng Java version, compiler option, test framework và quy tắc đóng gói, có thể tạo convention plugin để tránh lặp lại.

Ví dụ, một convention plugin nội bộ có thể áp dụng Java Library plugin và cấu hình toolchain:

~~~kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Các subproject thư viện có thể áp dụng plugin theo tên convention đã được đăng ký trong build logic:

~~~kotlin
plugins {
    id("shop.java-library-conventions")
}
~~~

Convention plugin thường được đặt trong build logic như buildSrc hoặc một included build chuyên chứa plugin. Với dự án lớn, included build cho build logic giúp tách việc phát triển plugin khỏi cấu hình của từng project.

Lợi ích:

- Quy tắc chung được định nghĩa một lần.
- Các project áp dụng theo nhu cầu.
- Build script của subproject ngắn và tập trung vào dependency của chính nó.
- Thay đổi compiler/test convention có thể được review tại một nơi.

Không nên biến convention plugin thành nơi chứa mọi quyết định riêng của từng project. Plugin nên thể hiện quy ước ổn định, còn các khác biệt thực sự nên được cấu hình rõ ở project sử dụng.

## 15. Version catalog và dependency dùng chung

Một multi-project build có thể dùng version catalog để quản lý tọa độ và version dependency tập trung.

Tệp **gradle/libs.versions.toml**:

~~~toml
[versions]
junit = "5.10.2"
commonsLang = "3.14.0"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang" }
~~~

Trong subproject:

~~~kotlin
dependencies {
    implementation(libs.commons.lang3)
    testImplementation(libs.junit.jupiter)
}
~~~

Version catalog giúp các project dùng cùng alias và version request. Nó không tự động thêm dependency vào mọi subproject. Project nào cần thư viện thì khai báo alias tương ứng trong dependencies của project đó.

Cũng cần phân biệt version catalog với dependency locking. Catalog tập trung khai báo version; locking ghi lại phiên bản thực tế đã được phân giải cho configuration.

## 16. Chạy task trong multi-project build

Có thể chạy task ở một project cụ thể bằng project path đầy đủ.

Ví dụ:

~~~bash
./gradlew :app:build
~~~

Chạy test của project domain:

~~~bash
./gradlew :domain:test
~~~

Chạy task ở project lồng nhau:

~~~bash
./gradlew :services:api:test
~~~

Nếu gọi task bằng tên không có project path, Gradle task name selector có thể chọn các task trùng tên trong nhiều project của build. Ví dụ:

~~~bash
./gradlew test
~~~

Lệnh này thường chạy task test ở các project có task cùng tên. Khi cần kiểm soát phạm vi chính xác, hãy dùng project path như **:app:test**.

Một số lệnh hữu ích:

| Lệnh | Mục đích |
|---|---|
| **./gradlew projects** | Liệt kê project trong build |
| **./gradlew tasks** | Liệt kê task của project hiện tại |
| **./gradlew :app:tasks --all** | Liệt kê task của project app |
| **./gradlew :app:build** | Build project app và dependency cần thiết |
| **./gradlew :domain:test** | Chạy test của project domain |
| **./gradlew :app:dependencies --configuration runtimeClasspath** | Xem dependency graph runtime của app |
| **./gradlew :app:dependencyInsight --dependency domain --configuration compileClasspath** | Truy nguyên dependency domain trên compile classpath |

Khi task được gọi ở một project, Gradle có thể đưa task của project dependency vào graph để tạo output cần thiết. Vì vậy, log của một lệnh có thể hiển thị task thuộc nhiều project path khác nhau.

## 17. Đọc project dependency graph

Để xem các project mà một project cần, có thể dùng task dependencies với configuration phù hợp:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Kết quả hiển thị các external module và project dependency được phân giải trên runtime classpath.

Ví dụ minh họa:

~~~text
runtimeClasspath
+--- project :service
|    +--- project :domain
|    \--- project :data
|         \--- project :domain
\--- org.apache.commons:commons-lang3:3.14.0
~~~

Đọc kết quả:

- App sử dụng project service.
- Service cần domain và data.
- Data cũng cần domain.
- App còn sử dụng commons-lang3 từ repository.

Nếu muốn tập trung vào một dependency:

~~~bash
./gradlew :app:dependencyInsight --dependency domain --configuration runtimeClasspath
~~~

Lệnh này giúp tìm nguồn đưa dependency vào graph và phiên bản được chọn nếu đó là external module. Với project dependency, kết quả cho biết project path và đường dependency liên quan.

Cần phân biệt output dependency report với task execution plan. Báo cáo dependencies cho biết các component trên configuration; dry run cho biết các task được chọn khi thực thi lệnh.

## 18. Multi-project build khác composite build như thế nào?

Hai mô hình đều cho phép phối hợp nhiều phần mã nguồn, nhưng cấu trúc khác nhau.

**Multi-project build** có một settings file quản lý root project và các subproject:

~~~kotlin
include(":app", ":domain")
~~~

Các project nằm trong cùng một build và có thể tham chiếu nhau bằng project dependency:

~~~kotlin
dependencies {
    implementation(project(":domain"))
}
~~~

**Composite build** kết hợp nhiều build độc lập bằng included build:

~~~kotlin
includeBuild("../shared-library")
~~~

Included build có settings và cấu hình riêng. Nó không trở thành subproject thông thường của root build. Composite build thường hữu ích khi phát triển nhiều repository hoặc build độc lập cùng lúc, ví dụ thay một external module dependency bằng source build cục bộ.

| Tiêu chí | Multi-project build | Composite build |
|---|---|---|
| Settings file | Một settings file chính cho các project trong build | Mỗi included build có cấu hình riêng |
| Quan hệ project | Root project và subproject | Nhiều build độc lập được kết hợp |
| Dependency | Project dependency giữa các subproject | Có thể thay external module bằng project từ included build |
| Cấu hình | Chia sẻ build context và cấu hình chung | Mỗi build giữ cấu hình và lifecycle riêng |
| Trường hợp dùng | Chia một sản phẩm thành nhiều module trong cùng repository/build | Phối hợp nhiều build hoặc repository độc lập |

Không nên dùng includeBuild chỉ để tạo một subproject mới trong cùng build. Nếu module thuộc cùng sản phẩm và cần quản lý như một phần của build, include thường phù hợp hơn.

## 19. Quy trình thiết kế một multi-project build

Khi tách một project lớn thành nhiều subproject, có thể thực hiện theo các bước:

1. Xác định các phần có trách nhiệm độc lập, ví dụ domain, data, service và app.
2. Xác định hướng dependency mong muốn: project ứng dụng phụ thuộc project dịch vụ; project nền tảng không phụ thuộc ngược lên ứng dụng.
3. Tạo thư mục và build script riêng cho từng project.
4. Khai báo các project trong settings file bằng include.
5. Đặt tên project path rõ ràng và ổn định.
6. Khai báo project dependency trong build script của consumer bằng project path.
7. Dùng api hoặc implementation phù hợp với public API của thư viện.
8. Chuyển cấu hình lặp lại thành convention plugin khi có đủ nhu cầu.
9. Kiểm tra graph bằng projects và dependencies.
10. Chạy task theo project path để xác nhận build, test và dependency output.
11. Kiểm tra chu trình dependency và tách abstraction nếu các project phụ thuộc vòng.
12. Duy trì version catalog, locking và repository policy nhất quán cho toàn build.

Việc tách project nên phản ánh ranh giới trách nhiệm và hướng thay đổi của mã nguồn. Không nên tạo một subproject riêng cho mỗi package nếu các phần đó luôn thay đổi cùng nhau và không có ranh giới dependency rõ ràng.

## 20. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Project không được tìm thấy | Chưa include trong settings hoặc project path sai | Kiểm tra settings và tên path |
| Build script của subproject không được đọc | Project directory hoặc build file mapping sai | Kiểm tra projectDir và vị trí build.gradle(.kts) |
| Không tìm thấy class của project khác | Chưa khai báo project dependency hoặc chọn sai configuration | Thêm project dependency phù hợp |
| Build chạy task từ nhiều project ngoài dự kiến | Gọi task bằng tên chung hoặc dependency kéo thêm project | Dùng task path đầy đủ và xem task graph |
| Project dependency cycle | Hai hoặc nhiều project phụ thuộc lẫn nhau | Tách API/abstraction và định hướng lại dependency |
| Consumer phải khai báo thêm dependency của thư viện | Producer dùng implementation trong khi kiểu đó xuất hiện trong public API | Xem xét api với java-library plugin |
| Root task không chạy mọi subproject task như mong đợi | Chưa cấu hình aggregate task hoặc nhầm task selector với dependency | Xác định task path và khai báo quan hệ tổng hợp rõ ràng |
| Version khác giữa các project | Các project dùng version request khác nhau hoặc thiếu quy tắc alignment | Dùng version catalog, platform, constraints và locking |
| Cấu hình chung khó kiểm soát | Quá nhiều logic trong allprojects/subprojects | Chuyển quy ước ổn định thành convention plugin |

## 21. Những nguyên tắc cần nhớ

- Root project là project gốc của build; subprojects là các project được khai báo trong settings.
- Settings file quyết định project nào thuộc build và project path của chúng.
- Project path bắt đầu bằng dấu hai chấm; project lồng nhau dùng nhiều cấp như **:services:api**.
- Mỗi subproject có thể có build script, plugin, source set, dependency và task riêng.
- Project dependency dùng **project(":path")** để tham chiếu project trong cùng build.
- Project dependency graph mô tả quan hệ giữa project; task graph mô tả task được chọn trong một lần chạy.
- Gradle tự thiết lập task dependency cần thiết để tạo output của project được tham chiếu.
- Dùng **api** khi dependency là một phần API công khai; dùng **implementation** cho dependency nội bộ.
- Thiết kế đồ thị dependency có hướng rõ ràng và tránh chu trình.
- Dùng **allprojects** và **subprojects** có chủ đích; convention plugin phù hợp hơn khi quy tắc chung phát triển.
- Version catalog quản lý alias và version request; dependency locking ghi kết quả phân giải.
- Dùng project path đầy đủ khi cần chạy task trong một project cụ thể.
- Multi-project build khác composite build: subproject thuộc cùng build, còn included build giữ settings và lifecycle độc lập.

Một multi-project build được tổ chức tốt cho phép mỗi phần của ứng dụng có trách nhiệm và dependency rõ ràng. Root project điều phối cấu trúc build, subproject quản lý mã và task của mình, còn project dependency graph thể hiện hướng sử dụng giữa các phần. Khi đồ thị được thiết kế không có chu trình và task path được dùng rõ ràng, Gradle có thể xây dựng đúng các project cần thiết mà vẫn giữ build script dễ hiểu và bảo trì.

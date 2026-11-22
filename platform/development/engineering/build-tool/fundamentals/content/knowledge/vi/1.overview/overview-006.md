# Tác vụ, vòng đời, plugin, phụ thuộc và artifact: bản đồ thuật ngữ

Build tool tự động hóa những việc cần làm để biến mã nguồn và tài nguyên của dự án thành đầu ra có thể kiểm thử, đóng gói hoặc phân phối. Với Gradle, các khái niệm thường gặp có quan hệ với nhau: plugin bổ sung khả năng cho project; plugin tạo hoặc cấu hình task và configuration; configuration nhận khai báo dependency; task đọc input, thực hiện công việc và tạo output; một số output được đóng gói thành artifact.

Có thể hình dung luồng tổng quát như sau:

~~~text
Lệnh Gradle
    |
    v
Build lifecycle
(initialization -> configuration -> execution)
    |
    v
Task graph
(các task và quan hệ phụ thuộc/thứ tự)
    |
    v
Task actions
(đọc input -> xử lý -> ghi output)
    |
    v
Artifact
(JAR, WAR, ZIP, ...)
~~~

Đây là bản đồ thuật ngữ cho các khái niệm nền tảng. Ví dụ dùng Gradle và Java để minh họa; tên task, configuration và loại artifact thực tế phụ thuộc vào plugin cùng cấu trúc của từng project.

## 1. Các đơn vị cấu thành một Gradle build

| Thuật ngữ | Ý nghĩa | Cách nhận biết |
|---|---|---|
| Build | Một lần chạy Gradle cùng toàn bộ project và cấu hình liên quan | Lệnh như `./gradlew build` |
| Project | Một đơn vị cấu hình và công việc trong build; thường tương ứng với một thư mục | Root project hoặc subproject |
| Root project | Project gốc của build | Thường có `settings.gradle` và `build.gradle` ở thư mục gốc |
| Subproject | Project con được khai báo trong settings | Ví dụ `:app`, `:library` |
| Included build | Một build Gradle độc lập được kết nối vào build hiện tại, thường dùng trong composite build | Được khai báo bằng `includeBuild(...)` |
| Settings script | Tập tin xác định cấu trúc build và cách tìm plugin | `settings.gradle` hoặc `settings.gradle.kts` |
| Build script | Tập tin cấu hình một project | `build.gradle` hoặc `build.gradle.kts` |
| Gradle Wrapper | Bộ script và cấu hình để chạy đúng phiên bản Gradle đã chọn cho repository | `gradlew`, `gradlew.bat`, thư mục `gradle/wrapper` |
| Plugin | Phần mở rộng bổ sung quy ước, cấu hình và hành vi cho build | Plugin `java`, Spring Boot plugin hoặc convention plugin |
| Task | Một đơn vị công việc có thể được Gradle đưa vào task graph và thực thi | `compileJava`, `test`, `jar` |
| Configuration | Một nhóm khai báo dependency hoặc một góc nhìn để phân giải/cung cấp dependency | `implementation`, `runtimeClasspath` |
| Dependency | Một thành phần mà project cần để biên dịch, chạy, kiểm thử hoặc thực hiện một công việc khác | Thư viện Maven hoặc project khác |
| Artifact | Tập tin đầu ra được tạo hoặc cung cấp bởi build | JAR, WAR, ZIP |

Một build có thể chứa nhiều project. Mỗi project có thể áp dụng nhiều plugin, khai báo nhiều task và configuration. Task graph được hình thành từ những task được yêu cầu cùng các quan hệ giữa chúng; nó không phải danh sách cố định áp dụng giống nhau cho mọi project.

### Settings script và build script làm hai việc khác nhau

Settings script được dùng để xác định build gồm những project nào, project nằm ở đâu và các build khác có được kết nối hay không. Ví dụ:

~~~groovy
rootProject.name = 'sample-build'
include 'app', 'library'
~~~

Đoạn cấu hình này đặt tên build và khai báo hai subproject. Đường dẫn project của chúng lần lượt là `:app` và `:library`.

Build script cấu hình một project cụ thể, chẳng hạn áp dụng plugin và khai báo dependency:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Gradle Wrapper giúp mọi người trong nhóm chạy cùng phiên bản Gradle mà repository đã chọn. Khi làm việc trong repository có Wrapper, thông thường nên dùng `./gradlew` trên macOS/Linux hoặc `gradlew.bat` trên Windows thay vì phụ thuộc vào một bản Gradle cài toàn máy.

## 2. Task và những quan hệ trong task graph

**Task** là đơn vị công việc Gradle quản lý. Một task có thể biên dịch mã, chạy kiểm thử, sao chép tập tin, tạo JAR hoặc thực hiện một thao tác tùy chỉnh.

Cần phân biệt ba khái niệm:

- **Task type** mô tả loại hành vi và các thuộc tính mà task có. Ví dụ `JavaCompile` là loại task biên dịch Java.
- **Task instance** là task cụ thể được đăng ký trong một project. Ví dụ `compileJava` là một task instance thường có kiểu `JavaCompile`.
- **Task path** xác định task trong toàn build. `:compileJava` là task ở root project; `:app:compileJava` là task trong subproject `app`.

Task có thể có các action. Với task tùy chỉnh viết bằng Groovy, `doFirst` và `doLast` thêm action chạy trước hoặc sau các action khác:

~~~groovy
tasks.register('showBuildMessage') {
    doLast {
        println 'Build task executed'
    }
}
~~~

Đăng ký task bằng `tasks.register(...)` cho phép Gradle trì hoãn việc tạo task cho đến khi cần. Đây là một phần của cơ chế configuration avoidance. Khi chỉ cần tham chiếu đến task đã đăng ký, `tasks.named(...)` thường phù hợp hơn việc buộc Gradle tạo task ngay lập tức.

### Các kiểu quan hệ giữa task

| Quan hệ | Ý nghĩa | Có tự đưa task được nhắc tới vào graph không? |
|---|---|---|
| `dependsOn` | Task hiện tại cần task khác hoàn tất trước khi chạy | Có |
| `mustRunAfter` | Nếu cả hai task đã được chọn, task hiện tại phải chạy sau task kia | Không |
| `shouldRunAfter` | Đề nghị thứ tự khi cả hai task được chọn; Gradle có thể bỏ qua ràng buộc mềm để giải quyết graph | Không |
| `finalizedBy` | Đăng ký task chạy sau task được chỉ định, thường dùng để dọn dẹp hoặc tổng kết | Có, khi task được finalize thực thi |

Ví dụ, task `packageApp` phụ thuộc vào task `compileJava`:

~~~groovy
tasks.register('packageApp') {
    dependsOn tasks.named('compileJava')
}
~~~

Khi yêu cầu chạy `packageApp`, Gradle đưa `compileJava` vào graph và bảo đảm nó hoàn tất trước `packageApp`.

Ngược lại, `mustRunAfter` chỉ điều chỉnh thứ tự nếu cả hai task vốn đã được chọn. Nếu chỉ yêu cầu task A, khai báo A chạy sau B không có nghĩa B sẽ tự chạy. Đây là điểm khác biệt quan trọng giữa **quan hệ phụ thuộc thực thi** và **ràng buộc thứ tự**.

Task graph thường là đồ thị có hướng không chu trình (DAG). Các cạnh thể hiện quan hệ cần thiết để sắp xếp việc thực thi. Gradle có thể chạy các task độc lập song song khi cấu hình build và tài nguyên cho phép; vì vậy không nên suy luận rằng mọi task luôn chạy lần lượt theo một danh sách duy nhất.

### Input, output và trạng thái task

Gradle cần biết task đọc dữ liệu nào và tạo ra dữ liệu nào. Các thuộc tính input/output được khai báo đúng giúp Gradle quyết định có cần thực hiện lại task hay có thể tái sử dụng kết quả.

- **Input** là dữ liệu ảnh hưởng đến kết quả, chẳng hạn tập tin nguồn, cấu hình hoặc giá trị tùy chọn.
- **Output** là dữ liệu task tạo ra, chẳng hạn tập tin class, báo cáo kiểm thử hoặc JAR.
- **Up-to-date check** so sánh trạng thái input và output với lần chạy trước. Nếu đầu vào không đổi và output vẫn hợp lệ, task có thể được đánh dấu `UP-TO-DATE`.
- **Build cache** có thể khôi phục output đã được tạo trước đó khi các điều kiện cache phù hợp, thay vì chạy lại action. Task cần khai báo input/output chính xác và đáp ứng yêu cầu cache để dùng cơ chế này an toàn.
- **Incremental task** có thể xử lý phần input thay đổi thay vì xử lý lại toàn bộ dữ liệu.
- **Configuration cache** lưu mô hình cấu hình để giảm thời gian cấu hình ở lần chạy sau. Nó khác build cache, vốn tập trung vào output của task.
- **Dependency cache** lưu metadata và các thành phần dependency đã tải/phân giải. Nó cũng khác hai loại cache ở trên.

Một số trạng thái thường thấy trong log là `SUCCESS`, `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED` và `FAILED`. Chúng mô tả kết quả thực thi của task; `UP-TO-DATE` hay `FROM-CACHE` không có nghĩa là task bị lỗi hoặc bị bỏ quên.

## 3. Build lifecycle của Gradle

Gradle xử lý một lần build qua ba phase chính. Đây là **vòng đời của build**, khác với vòng đời nghiệp vụ của ứng dụng và cũng khác với danh sách task của một plugin.

| Phase | Gradle làm gì? | Ví dụ việc diễn ra |
|---|---|---|
| Initialization | Xác định build và các project tham gia | Đọc settings script, tìm root project và subproject, kết nối included build |
| Configuration | Đánh giá cấu hình của các project liên quan và chuẩn bị task graph | Áp dụng plugin, cấu hình task, đọc khai báo dependency và xác định task cần chạy |
| Execution | Thực thi các task trong graph theo quan hệ phụ thuộc và thứ tự | Biên dịch Java, chạy test, tạo JAR |

Điểm cần nhớ là build script được đánh giá trong phase **configuration**, còn action của task chạy trong phase **execution**. Việc đăng ký một task không đồng nghĩa task đó sẽ chạy. Task chỉ được thực thi khi được yêu cầu trực tiếp hoặc được đưa vào graph thông qua các quan hệ phù hợp.

Ví dụ:

~~~shell
./gradlew :app:test
~~~

Gradle khởi tạo build, cấu hình project cần thiết, xác định task `test` trong project `app` cùng các task phụ thuộc, rồi thực thi graph đó. Các task biên dịch và chuẩn bị test thường xuất hiện trong graph vì `test` cần chúng.

Có thể xem graph dự kiến mà không thực thi action bằng:

~~~shell
./gradlew :app:test --dry-run
~~~

Tùy chọn `--dry-run` hữu ích khi muốn hiểu task nào sẽ được lên lịch. Nó không thay thế việc chạy build thật để kiểm tra kết quả.

### Build lifecycle tasks

Các plugin thường cung cấp những task tổng hợp (aggregate task) để gom nhiều công việc liên quan. Với Java plugin, những tên quen thuộc gồm:

- `clean`: xóa thư mục output build của project.
- `classes`: gom các công việc tạo class chính và xử lý resource.
- `test`: biên dịch và chạy test theo cấu hình của project.
- `jar`: đóng gói class và resource thành JAR.
- `assemble`: gom các công việc tạo artifact.
- `check`: gom các công việc kiểm tra, thường gồm test.
- `build`: task tổng hợp thường kết hợp `assemble` và `check`.

Đây là quy ước phổ biến do plugin cung cấp, không phải mọi project đều có chính xác cùng task. Plugin khác có thể bổ sung hoặc thay đổi graph. Ví dụ, ứng dụng Spring Boot thường có task `bootJar` để tạo executable JAR theo cách đóng gói của Spring Boot plugin.

Lệnh:

~~~shell
./gradlew clean build
~~~

yêu cầu Gradle chạy `clean` và `build` theo thứ tự yêu cầu trên dòng lệnh. `clean` xóa output cũ; `build` sau đó thực hiện các công việc cần thiết để tạo artifact và chạy các kiểm tra được nối vào graph. Bản thân `build` không phải một lệnh biên dịch đơn lẻ.

## 4. Plugin, extension và convention

**Plugin** bổ sung một tập hợp khả năng cho build hoặc project. Khi áp dụng plugin, Gradle có thể tạo task, tạo configuration, cung cấp extension, thiết lập quy ước và nối các phần việc với nhau.

Ví dụ, Java plugin cung cấp các task và configuration quen thuộc để biên dịch, kiểm thử và đóng gói Java. Spring Boot plugin bổ sung quy trình đóng gói ứng dụng Spring Boot, trong đó có task `bootJar` khi phù hợp.

Cú pháp plugins DSL thường dùng:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
}
~~~

Plugin có thể được tìm thấy qua các repository plugin được cấu hình trong settings script, thường ở khối `pluginManagement`. Cách khai báo phiên bản và repository cho plugin thuộc cơ chế phân giải plugin; nó có liên quan nhưng không đồng nhất với repository dùng để phân giải thư viện của project.

Một số nhóm plugin:

- **Core plugin** được Gradle cung cấp, ví dụ `java`, `java-library`.
- **Community hoặc third-party plugin** do bên ngoài cung cấp, ví dụ plugin của Spring Boot.
- **Script plugin** là script được áp dụng để chia sẻ cấu hình; nó thường không có mức đóng gói và quản lý phiên bản như binary plugin.
- **Binary plugin** là plugin được đóng gói thành thành phần có thể tái sử dụng.
- **Convention plugin** đóng gói quy ước dùng chung cho nhiều project, chẳng hạn phiên bản Java, quy tắc kiểm thử hoặc cấu hình chất lượng mã.

Ba thuật ngữ thường bị nhầm:

| Thuật ngữ | Vai trò |
|---|---|
| Plugin | Bổ sung khả năng và quy ước cho build/project |
| Extension | Đối tượng cấu hình mà plugin cung cấp để người dùng điều chỉnh hành vi |
| Task | Công việc cụ thể có thể được đưa vào graph và thực thi |

Ví dụ, plugin có thể cung cấp extension để cấu hình phiên bản Java, đồng thời đăng ký task biên dịch. Extension chứa cấu hình; task dùng cấu hình đó khi thực hiện công việc.

## 5. Dependency, configuration và repository

**Dependency** là thành phần mà project cần. Với Java, dependency thường là thư viện bên ngoài hoặc một project khác trong cùng build. Cần phân biệt dependency của project với task dependency:

- Project/module dependency trả lời câu hỏi: mã nguồn hoặc runtime cần thư viện/project nào?
- Task dependency trả lời câu hỏi: task nào phải hoàn thành trước task nào?

Một thư viện được khai báo trong dependency configuration không tự động có nghĩa là một task cụ thể sẽ chạy. Ngược lại, `dependsOn` giữa hai task không phải là cách khai báo thư viện Java.

### Dependency configuration

Trong Gradle, dependency thường được khai báo vào một **configuration**. Configuration mô tả nhóm dependency và cách chúng được dùng hoặc cung cấp. Với Java plugin, các tên phổ biến gồm:

| Configuration | Mục đích khái quát |
|---|---|
| `implementation` | Dependency cần cho việc biên dịch và chạy nội bộ project |
| `api` | Dependency được công khai trên compile API của consumer; thường dùng với Java Library plugin |
| `compileOnly` | Có trên compile classpath nhưng không được đưa vào runtime classpath theo cách thông thường |
| `runtimeOnly` | Cần khi chạy nhưng không cần trên compile classpath |
| `testImplementation` | Dependency dùng để biên dịch test |
| `testRuntimeOnly` | Dependency chỉ cần khi chạy test |
| `compileClasspath` | Classpath được phân giải để biên dịch; thường là configuration có thể resolve |
| `runtimeClasspath` | Classpath được phân giải để chạy; thường là configuration có thể resolve |

Các configuration khai báo như `implementation` và `testImplementation` thường là nơi thêm dependency. Những configuration như `compileClasspath` và `runtimeClasspath` biểu diễn tập hợp đã được phân giải cho một mục đích cụ thể. Không nên tùy tiện thêm dependency vào configuration chỉ nhằm resolve hoặc dùng làm đầu ra cho consumer.

Khác biệt giữa `implementation` và `api` có ý nghĩa rõ nhất khi xây dựng thư viện. `implementation` giữ dependency ở bên trong implementation của thư viện; `api` làm dependency đó xuất hiện trên compile API mà project tiêu thụ thư viện có thể nhìn thấy. Với một ứng dụng Java thông thường, `implementation` là lựa chọn mặc định hợp lý cho phần lớn thư viện mà mã nguồn ứng dụng sử dụng.

Ví dụ khai báo:

~~~groovy
dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.16'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
    runtimeOnly 'com.h2database:h2:2.3.232'
}
~~~

### Tọa độ dependency và các loại dependency

Một dependency Maven thường được xác định bằng tọa độ:

~~~text
group:name:version
~~~

Ví dụ `org.slf4j:slf4j-api:2.0.16` có group là `org.slf4j`, tên module là `slf4j-api` và phiên bản là `2.0.16`.

Các loại khai báo thường gặp:

- **External module dependency**: thư viện được phân phối qua repository, thường dùng tọa độ group/name/version.
- **Project dependency**: phụ thuộc vào project khác trong cùng build, ví dụ `implementation project(':library')`.
- **File dependency**: tham chiếu trực tiếp đến tập tin JAR. Cách này ít metadata hơn dependency quản lý qua repository và không tự cung cấp đầy đủ thông tin dependency bắc cầu.

Dependency bắc cầu (transitive dependency) là dependency mà một thư viện phụ thuộc vào. Gradle xây dựng dependency graph từ các khai báo trực tiếp và metadata của những module liên quan. Nếu nhiều nhánh yêu cầu các phiên bản khác nhau, Gradle áp dụng quy tắc phân giải phiên bản và metadata để chọn thành phần phù hợp. Khi cần tính lặp lại giữa các lần build, có thể quản lý phiên bản tập trung và dùng dependency locking.

### Repository dùng để tìm dependency

Repository là nơi Gradle tìm metadata và tập tin dependency. Ví dụ:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Khai báo dependency cho Gradle biết project cần thành phần nào; khai báo repository cho Gradle biết có thể tìm thành phần đó ở đâu. Chỉ khai báo dependency mà không có repository thích hợp có thể dẫn đến lỗi không tìm thấy module.

Một vài điểm phân biệt:

- `mavenCentral()` là repository công khai thường dùng để lấy thư viện Maven.
- `mavenLocal()` tìm trong Maven local repository trên máy đang chạy; kết quả có thể khác nhau giữa các máy.
- Repository plugin trong `pluginManagement` phục vụ phân giải plugin.
- Repository trong khối `repositories` của project phục vụ phân giải dependency của project.

**Dependency resolution** là quá trình Gradle tìm module, đọc metadata, chọn phiên bản/variant và tải thành phần cần thiết. Nó xảy ra khi một configuration cần được resolve, thường trong lúc task cần classpath tương ứng.

### Variant và capability

Một module có thể cung cấp nhiều biến thể (variant), chẳng hạn biến thể dành cho compile, runtime, một nền tảng hoặc một loại thư viện. Gradle dùng thuộc tính (attributes) và metadata để chọn variant phù hợp với nhu cầu của consumer. Capability giúp mô tả khả năng mà một component cung cấp và hỗ trợ phát hiện xung đột khi nhiều component cùng cung cấp một capability.

Ở mức cơ bản, chỉ cần nhớ rằng dependency không phải lúc nào cũng là một JAR duy nhất được chọn chỉ bằng tên và phiên bản; metadata của module còn có thể quyết định biến thể nào phù hợp với configuration đang resolve.

## 6. Artifact và quá trình đóng gói

**Artifact** là tập tin được tạo ra hoặc được cung cấp như một đầu ra của build. Trong dự án Java, artifact thường là JAR; ứng dụng web có thể tạo WAR; quy trình phân phối cũng có thể tạo ZIP chứa tài liệu hoặc nhiều tập tin.

Một số thuật ngữ liên quan:

- **Output** là đầu ra mà task tạo ra. Output có thể là một tập tin, nhiều tập tin hoặc một thư mục.
- **Archive** là tập tin đóng gói nhiều nội dung, ví dụ JAR, WAR hoặc ZIP.
- **Archive task** là task tạo archive; ví dụ `jar` tạo JAR theo cấu hình của Java plugin.
- **Classifier** phân biệt biến thể artifact cùng tên và phiên bản, ví dụ `sources` hoặc `javadoc`.
- **Publication** mô tả thành phần sẽ được xuất bản, gồm artifact và metadata cần thiết.
- **Artifact repository** là nơi lưu trữ artifact đã xuất bản để consumer tải về.

Thông thường, output archive của project nằm dưới thư mục `build/`, ví dụ `build/libs/`. Đây là vị trí theo quy ước, không phải cam kết cho mọi task. Cần xem output của task hoặc cấu hình archive khi cần xác định đường dẫn chính xác.

Ví dụ, Java plugin có task `jar`. Spring Boot plugin có thể cung cấp `bootJar` để đóng gói ứng dụng Spring Boot theo định dạng executable JAR. Hai artifact có mục đích và nội dung đóng gói khác nhau; việc task nào tồn tại và task nào được dùng phụ thuộc plugin cùng cấu hình project.

Cần phân biệt ba bước:

1. **Tạo artifact**: task như `jar` hoặc `bootJar` tạo tập tin.
2. **Đưa artifact vào publication**: cấu hình publication xác định artifact và metadata cần xuất bản.
3. **Publish artifact**: task publish chuyển publication đến repository đích.

Một JAR nằm trong `build/libs/` chưa có nghĩa nó đã được xuất bản lên Maven repository. Tương tự, dependency tải từ Maven repository là artifact được cung cấp bởi một module khác, không phải output do build hiện tại vừa tạo.

## 7. Ghép các khái niệm thành một luồng thực tế

Giả sử project Java có mã nguồn trong `src/main/java`, test trong `src/test/java` và áp dụng Java plugin. Khi chạy:

~~~shell
./gradlew clean build
~~~

Có thể đọc quá trình ở các lớp sau:

1. **Wrapper và build**: Wrapper chọn phiên bản Gradle của repository rồi khởi chạy build.
2. **Initialization**: Gradle đọc settings script để nhận diện root project và các subproject.
3. **Configuration**: Java plugin được áp dụng; plugin cung cấp các task như `compileJava`, `test`, `jar`, `assemble`, `check` và các configuration dependency. Gradle đọc khai báo dependency và chuẩn bị task graph cần cho `build`.
4. **Dependency resolution**: Khi task cần compile classpath hoặc runtime classpath, Gradle resolve configuration tương ứng từ các repository đã khai báo.
5. **Execution**: Các task biên dịch mã nguồn, xử lý resource, biên dịch/chạy test và đóng gói được thực thi theo graph. Task độc lập có thể chạy song song nếu điều kiện cho phép.
6. **Output và artifact**: Các file class, báo cáo test và JAR được tạo trong thư mục build theo cấu hình. JAR là artifact có thể được dùng ở bước tiếp theo hoặc đưa vào publication.

Một graph đơn giản có thể được hình dung như sau; graph thật do plugin và cấu hình của project quyết định:

~~~text
                         build
                        /     \
                   assemble   check
                      |         |
                     jar       test
                      |         |
                    classes  testClasses
                      |         |
                compileJava  compileTestJava
~~~

Sơ đồ chỉ nhấn mạnh các quan hệ tổng quát. Graph thực tế còn có thể chứa các task xử lý resource, kiểm tra bổ sung, tạo mã nguồn, kiểm tra định dạng hoặc các task do plugin khác thêm vào.

## 8. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| `build` là một lệnh biên dịch | `build` thường là task tổng hợp nối các công việc đóng gói và kiểm tra |
| Mọi task đều chạy mỗi lần gọi Gradle | Task chỉ chạy khi được chọn vào graph; một số task có thể `UP-TO-DATE`, lấy từ cache hoặc bị skip |
| `mustRunAfter` giống `dependsOn` | `mustRunAfter` chỉ sắp xếp hai task đã được chọn; `dependsOn` tạo quan hệ phụ thuộc và đưa task cần thiết vào graph |
| Plugin là một task | Plugin bổ sung khả năng; plugin có thể tạo nhiều task và configuration |
| Extension là nơi thực thi công việc | Extension là mô hình cấu hình; task thực hiện công việc |
| `implementation` là task | Đây là configuration dùng để khai báo dependency |
| Dependency của thư viện giống dependency giữa task | Một loại nối các component; loại còn lại nối các công việc trong task graph |
| Repository và artifact là một | Repository là nơi lưu trữ/phân phối; artifact là tập tin được lưu trữ hoặc tiêu thụ |
| JAR trong `build/libs` đã được publish | Tạo file và publish file là hai bước riêng |
| Build lifecycle là thứ tự cố định của các task | Build lifecycle gồm initialization, configuration, execution; task graph thay đổi theo yêu cầu và plugin |

Khi gặp một thuật ngữ trong log hoặc build script, hãy đặt nó vào đúng lớp: nó mô tả cấu trúc build, giai đoạn xử lý, công việc, quan hệ giữa công việc, thư viện đầu vào hay tập tin đầu ra? Xác định đúng lớp thường giúp tìm đúng nơi cần đọc hoặc cấu hình.

## 9. Bản đồ tra cứu nhanh

| Nếu câu hỏi là... | Hãy tìm... |
|---|---|
| Build gồm những project nào? | `settings.gradle`, `include`, `includeBuild` |
| Project áp dụng khả năng nào? | Khối `plugins` và plugin đã được áp dụng |
| Task nào sẽ chạy? | Task được yêu cầu, `dependsOn`, task graph, `--dry-run` |
| Vì sao task chạy trước/sau task khác? | `dependsOn`, `mustRunAfter`, `shouldRunAfter`, `finalizedBy` |
| Vì sao task không chạy lại? | Input/output, up-to-date check, build cache |
| Project cần thư viện nào? | Khối `dependencies` |
| Gradle tìm thư viện ở đâu? | Khối `repositories` và `pluginManagement` |
| Phiên bản/variant nào được chọn? | Dependency graph, metadata, constraints và attributes |
| Tập tin nào được tạo? | Output của task và thư mục `build/` |
| Artifact được phân phối thế nào? | Publication và artifact repository |

Khi đọc một build script, có thể lần theo chuỗi: plugin cung cấp quy ước và khả năng; configuration nhận dependency; task sử dụng mã nguồn, resource và dependency để tạo output; task graph cùng build lifecycle quyết định khi nào công việc được cấu hình và thực thi; artifact là một trong những đầu ra có thể được lưu trữ hoặc phân phối.

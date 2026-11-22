# Kiểm soát thư mục chạy, Gradle User Home và cấu hình tiến trình trong Gradle

## 1. Tại sao ba nhóm cấu hình này dễ bị nhầm?

Một lệnh Gradle chịu ảnh hưởng đồng thời bởi **nơi gọi lệnh**, **nơi Gradle lưu cấu hình/cache theo người dùng** và **môi trường chạy tiến trình Java thực thi build**. Ba nhóm này có thể độc lập với nhau:

- **Thư mục chạy/điểm bắt đầu của build**: Gradle đọc dự án nào, dự án nào là ngữ cảnh để chọn task; chủ yếu liên quan tới thư mục hiện tại và tùy chọn `-p`/`--project-dir`.
- **Gradle User Home**: nơi chứa các bản phân phối Wrapper, cache dependency, daemon log, cấu hình người dùng và init script; có thể chọn bằng `GRADLE_USER_HOME` hoặc `-g`/`--gradle-user-home`.
- **Cấu hình tiến trình**: Gradle Client JVM và Gradle Daemon JVM dùng Java nào, bao nhiêu heap, có tái sử dụng daemon không, chạy song song tối đa bao nhiêu worker; liên quan tới `JAVA_HOME`, `org.gradle.jvmargs`, `org.gradle.java.home`, `--daemon`, `--no-daemon`, `--max-workers` và các thuộc tính khác.

Thay đổi một nhóm **không tự động đổi nhóm còn lại**. Ví dụ, `-g /tmp/gradle-cache` không khiến Gradle đọc dự án tại `/tmp/gradle-cache`; `-p ./service` không làm Gradle di chuyển cache người dùng vào `./service`; `--no-daemon` không có nghĩa là chạy Gradle không cần JVM.

Hướng dẫn dùng Gradle Wrapper của chính dự án: `./gradlew` trên Linux/macOS, `.\gradlew.bat` trên Windows. Nếu dự án chưa có Wrapper, phải tạo nó trước bằng quy trình Gradle phù hợp; không thay mặc định bằng bản `gradle` cài toàn cục khi dự án đã pin phiên bản.

## 2. Phân biệt các thư mục quan trọng

Giả sử kho mã nguồn có cấu trúc sau:

~~~text
/work/store/
├── gradlew
├── gradlew.bat
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── app/
│   └── build.gradle.kts
└── .gradle/                  # thư mục cache riêng của build, thường được bỏ qua trong Git
~~~

Trong `settings.gradle.kts`, ví dụ có `include("app")`. Những đường dẫn sau khác nhau về nhiệm vụ:

| Khái niệm | Ví dụ | Dùng để làm gì? |
| --- | --- | --- |
| Shell working directory | `/work/store` sau `cd /work/store` | Hệ điều hành quyết định nơi thực thi lệnh và cách diễn giải đường dẫn tương đối truyền qua shell |
| Gradle start directory | Mặc định theo shell working directory; có thể đặt qua `-p` | Gradle xác định ngữ cảnh dự án ban đầu để thực thi lệnh |
| Root project directory | `/work/store` | Dự án gốc của một multi-project build; chứa settings và thường có `gradle.properties` của build |
| Subproject directory | `/work/store/app` | Thư mục và build script riêng của dự án con `:app` |
| Project-local cache | `/work/store/.gradle/` | Trạng thái và cache gắn với một build; có thể điều chỉnh bằng `--project-cache-dir` |
| Gradle User Home | Ví dụ `/home/linh/.gradle` | Cache phân phối Gradle, dependency, cấu hình người dùng, init scripts và daemon |
| Gradle installation home | Thư mục cài đặt/phân phối Gradle | Chứa bản Gradle đang chạy; **khác** với Gradle User Home |
| `build/` | `/work/store/app/build/` | Đầu ra build của dự án; không phải cache người dùng |

Không đồng nhất `GRADLE_HOME` (thư mục cài Gradle, nếu dùng) với `GRADLE_USER_HOME` (thư mục dữ liệu người dùng). Cũng đừng nhầm thư mục `.gradle` **bên trong repository** với `~/.gradle` **trong home người dùng**.

## 3. Kiểm soát thư mục bắt đầu bằng `cd` và `-p`

Mặc định, Gradle chọn thư mục hiện tại làm **start directory**. Đường dẫn tới script Wrapper chỉ cho biết chạy *script nào*, không có nghĩa Gradle tự lấy thư mục chứa script làm start directory.

### Chạy từ thư mục gốc

~~~bash
cd /work/store
./gradlew help
./gradlew :app:tasks
~~~

Trong ví dụ trên, `help` được gọi với ngữ cảnh root. Task path tuyệt đối `:app:tasks` xác định rõ dự án con `app`; với build nhiều module, tên task có dấu `:` giúp tránh phụ thuộc vào vị trí gọi lệnh.

### Chạy từ thư mục con

~~~bash
cd /work/store/app
../gradlew help
../gradlew :app:tasks
~~~

Dùng `../gradlew` vì Wrapper thực tế nằm ở thư mục cha. Gradle có thể phát hiện root build qua settings, nhưng start directory lúc này là `app`. Một task name không định danh đầy đủ có thể được chọn theo ngữ cảnh dự án hiện tại. Khi viết hướng dẫn CI hoặc script dùng chung, nên dùng task path rõ ràng như `:app:test` hoặc chạy từ root để tránh diễn giải khác nhau.

### Chạy từ thư mục khác bằng `-p`

~~~bash
cd /work
./store/gradlew --project-dir=./store help
./store/gradlew -p ./store :app:tasks
~~~

`-p` là dạng ngắn của `--project-dir`; nó đặt **thư mục bắt đầu cho Gradle**, mặc định là thư mục hiện tại. Đường dẫn `./store` trong ví dụ được viết tương đối với nơi shell đang đứng. Đối với script automation/CI, dùng đường dẫn tuyệt đối hoặc bảo đảm bước `cd` rõ ràng để tránh phụ thuộc ngữ cảnh.

Với multi-project build:

~~~bash
cd /work/store
./gradlew -p ./app help
./gradlew :app:help
~~~

Hai lệnh được dùng để minh họa cách chỉ định start directory và task path. Chúng có thể không tương đương với mọi loại task/logic dự án; task selector không định danh bằng `:` còn có thể chọn các task con tùy theo project context. Muốn nhắm đúng một task, ưu tiên project path đầy đủ.

**Không nhầm `-p` với `-P`:** `-p ./app` chọn thư mục bắt đầu; `-Penv=dev` truyền project property `env` có giá trị `dev`. Chữ hoa/chữ thường rất quan trọng.

### Quy tắc xử lý đường dẫn trong build script

Các Gradle API như `layout.projectDirectory.file("config/app.yaml")` dùng **project directory** làm gốc, phù hợp khi đọc tài nguyên của module. Tránh giả định `System.getProperty("user.dir")` luôn là thư mục module, đặc biệt khi daemon được tái sử dụng. Tránh tự dựa vào shell working directory để tìm file đầu vào bên trong task; nên khai báo đường dẫn thông qua các đối tượng `layout`, `projectDir` và input/output của Gradle.

## 4. Gradle User Home: nội dung và mục đích

Theo mặc định, Gradle User Home nằm ở `~/.gradle` trên Linux/macOS hoặc `%USERPROFILE%\.gradle` trên Windows (nếu không được cấu hình khác). Đây là không gian dùng chung cho các build của cùng một môi trường người dùng.

~~~text
GRADLE_USER_HOME/
├── gradle.properties               # thiết lập Gradle của người dùng
├── init.d/                         # init scripts áp dụng cho các build sử dụng home này
├── caches/                         # cache phân giải dependency, script và dữ liệu Gradle
├── wrapper/
│   └── dists/                      # các bản Gradle do Wrapper tải/giải nén
├── daemon/
│   └── <gradle-version>/           # registry và log của daemon theo phiên bản
└── jdks/                           # JDK được Gradle quản lý khi chức năng liên quan được dùng
~~~

Cấu trúc thực tế thay đổi theo phiên bản Gradle và các tính năng đang sử dụng. Sự xuất hiện của một thư mục không có nghĩa dự án đã dùng toàn bộ tính năng đó.

Một `GRADLE_USER_HOME` **mới** thường làm lần chạy đầu lâu hơn vì phải tải lại phân phối Gradle, plugin/dependency và biên dịch lại những phần chưa có trong cache. Việc tách user home giúp cô lập cache hoặc cấu hình cho thử nghiệm/CI, nhưng cũng có thể làm build thay đổi nếu home cũ chứa repository credentials, init scripts hoặc thuộc tính người dùng cần thiết.

## 5. Chọn Gradle User Home bằng `-g` hoặc biến môi trường

Hai cách phổ biến:

1. `-g DIR` hay `--gradle-user-home=DIR`: chọn Gradle User Home **cho lần gọi lệnh**.
2. Biến môi trường `GRADLE_USER_HOME`: chọn home cho các lần gọi từ tiến trình/shell nhận biến đó, nếu lệnh không ghi đè bằng tùy chọn trực tiếp.

### Linux/macOS — thiết lập cho một lệnh

~~~bash
cd /work/store

# Chỉ tác động lần gọi này; dùng đường dẫn tuyệt đối khi triển khai CI
GRADLE_USER_HOME=/tmp/gradle-lab ./gradlew help

# Cách tương đương về ý định đối với một lệnh
./gradlew --gradle-user-home=/tmp/gradle-lab help

# Chọn nơi khác và đồng thời cố định start directory
./gradlew -p /work/store -g /tmp/gradle-lab :app:tasks
~~~

Ở lệnh thứ ba, `-p` điều khiển start directory, `-g` điều khiển user home. Không lệnh nào tự đổi thư mục hiện tại của shell cha.

### Linux/macOS — thiết lập cho phiên shell

~~~bash
export GRADLE_USER_HOME="$HOME/.gradle-experiments"
./gradlew help
./gradlew --status

# Khi không muốn biến tiếp tục ảnh hưởng các lệnh sau:
unset GRADLE_USER_HOME
~~~

### Windows PowerShell — thiết lập và khôi phục

~~~powershell
Set-Location C:\work\store

# Một lệnh với thư mục chỉ định trực tiếp
.\gradlew.bat -g C:\gradle-lab help

# Thiết lập biến môi trường cho PowerShell hiện tại
$previousGradleHome = $env:GRADLE_USER_HOME
$env:GRADLE_USER_HOME = 'C:\gradle-lab'
.\gradlew.bat help

# Khôi phục giá trị cũ (nếu trước đó chưa có thì xóa biến)
if ($null -eq $previousGradleHome) {
    Remove-Item Env:GRADLE_USER_HOME -ErrorAction SilentlyContinue
} else {
    $env:GRADLE_USER_HOME = $previousGradleHome
}
~~~

Nếu đường dẫn chứa khoảng trắng, cần bao bởi dấu nháy đúng theo shell. Trong CI nên dùng biến môi trường theo job/container, dùng cache với khóa phù hợp Gradle/JDK/hệ điều hành và không đưa thư mục home chứa thông tin nhạy cảm vào Git. Đừng tùy tiện đặt Gradle User Home vào workspace được commit.

**Tùy chọn bổ sung:** `--project-cache-dir DIR` điều chỉnh cache **riêng của build**, mặc định là `.gradle` dưới root project. Nó không thay cho `-g`, không thay `GRADLE_USER_HOME`, không quy định chỗ các bản Wrapper được lưu.

## 6. `gradle.properties`: cùng tên tệp, khác phạm vi

Gradle có thể tìm thấy tệp `gradle.properties` trong nhiều vị trí:

| Vị trí | Phạm vi và cách dùng |
| --- | --- |
| `<GRADLE_USER_HOME>/gradle.properties` | Thiết lập riêng cho người dùng/CI; tránh commit credential hoặc đường dẫn máy cá nhân |
| `<ROOT_PROJECT>/gradle.properties` | Thiết lập nên chia sẻ của dự án; có thể commit các thuộc tính không bí mật |
| `<GRADLE_HOME>/gradle.properties` | Thiết lập theo nơi cài Gradle, ít dùng với dự án dựa vào Wrapper |

Nếu cùng một **Gradle property** tồn tại ở cả ba tệp, Gradle xét ưu tiên cấu hình người dùng cao hơn cấu hình root project, rồi đến cấu hình nơi cài đặt Gradle. Tùy chọn dòng lệnh trực tiếp và system property phù hợp có thể có ưu tiên cao hơn; không được suy từ thứ tự của ba tệp rằng mọi loại cờ, biến môi trường, project property và JVM argument đều tuân một quy tắc duy nhất.

Ví dụ tệp `gradle.properties` tại **root project**:

~~~properties
# Giá trị minh họa; cân chỉnh theo khả năng máy/runner
org.gradle.jvmargs=-Xmx2g -XX:MaxMetaspaceSize=512m -Dfile.encoding=UTF-8
org.gradle.daemon=true
org.gradle.parallel=false
org.gradle.workers.max=2
org.gradle.caching=true
~~~

Giải thích:

- `org.gradle.jvmargs`: JVM arguments của **tiến trình build Gradle/Daemon**, không phải cấu hình heap mặc định của mọi Java application hoặc JVM chạy test.
- `org.gradle.daemon`: lựa chọn dùng daemon theo mặc định của build; `--daemon`/`--no-daemon` áp dụng cho lần chạy.
- `org.gradle.parallel`: cho phép thực thi các dự án phù hợp song song trong multi-project build; hiệu quả phụ thuộc cấu trúc task, tài nguyên và Gradle version.
- `org.gradle.workers.max`: giới hạn số worker Gradle dùng để thực hiện công việc song song; không đồng nghĩa số core vật lý, cũng không phải cài đặt heap.
- `org.gradle.caching`: bật build cache cho task đủ điều kiện; **khác** với việc Gradle luôn có cache dependency trong user home.

Tệp `gradle/wrapper/gradle-wrapper.properties` thì khác: nó chọn **bản phân phối Gradle** cho Wrapper. Đặt `org.gradle.jvmargs` trong `gradle.properties`, không nhầm với URL Wrapper.

## 7. Gradle Client và Gradle Daemon là các tiến trình khác nhau

Lệnh `./gradlew help` thường có luồng như sau:

~~~text
Terminal / Shell
    │
    ├─ chạy gradlew hoặc gradlew.bat
    │       │
    │       └─ Java khởi động Gradle Client / Wrapper
    │                 │
    │                 ├─ đọc phiên bản, lựa chọn Java và cấu hình build
    │                 └─ kết nối đến daemon tương thích
    │                        hoặc khởi động daemon mới
    │                                  │
    │                                  ▼
    │                         Gradle Daemon JVM
    │                         cấu hình dự án, chạy task
    │                                  │
    │                       có thể tạo thêm tiến trình:
    │                         test JVM, compiler, worker
    └─ nhận log / trạng thái hoàn thành
~~~

**Gradle Client JVM** phục vụ khởi tạo, kết nối và trao đổi với daemon; nó thường được khởi chạy bằng Java do `JAVA_HOME` hoặc `PATH`/IDE chỉ định. `JAVA_OPTS` và `GRADLE_OPTS` thường tác động đến JVM chạy Gradle Client; không nên chỉ tăng `JAVA_OPTS=-Xmx...` và kỳ vọng heap Daemon đổi tương ứng.

**Gradle Daemon JVM** thực hiện cấu hình và build; mặc định Gradle ưu tiên tái sử dụng daemon tương thích về phiên bản Gradle, Java và JVM arguments. Nếu thay `org.gradle.jvmargs` hoặc Java được chọn, Gradle có thể phải khởi động một daemon khác. Điều này giải thích tại sao một máy có thể có nhiều Gradle daemon.

Các Java process do task tạo thêm (ví dụ `Test` JVM hoặc fork compiler) có cài đặt bộ nhớ riêng. Tăng `org.gradle.jvmargs` **không tự nâng heap cho mọi test process**. Nếu task `test` hết bộ nhớ, cần kiểm tra cấu hình task `Test`, ví dụ `maxHeapSize`, thay vì chỉ chỉnh heap của Gradle daemon.

## 8. Các cờ tiến trình cần biết

| Lệnh/cấu hình | Tác dụng | Khi nên dùng |
| --- | --- | --- |
| `./gradlew --status` | Xem daemon của phiên bản Gradle đang được gọi | Chẩn đoán nhiều daemon, trạng thái IDLE/BUSY |
| `./gradlew --stop` | Yêu cầu dừng daemon của **cùng phiên bản Gradle** | Sau thay đổi cấu hình/JDK hoặc khi daemon có biểu hiện lỗi |
| `./gradlew help --daemon` | Cho phép sử dụng daemon cho lần chạy | Dùng daemon như mặc định Gradle hiện đại |
| `./gradlew help --no-daemon` | Không duy trì daemon dài hạn cho lần chạy | Chạy thử để khoanh vùng vấn đề daemon hoặc trong môi trường có yêu cầu riêng |
| `./gradlew help --max-workers=2` | Hạn chế worker tối đa | CI nhỏ, máy đang thiếu CPU/RAM, đo đạc hiệu năng |
| `./gradlew help --parallel` | Bật thực thi project song song | Multi-project build phù hợp và đủ tài nguyên |
| `./gradlew help --no-parallel` | Tắt thực thi project song song | Tái hiện lỗi cạnh tranh tài nguyên |
| `./gradlew help --console=plain` | Ghi log dạng dễ đọc trong CI | Log file, terminal không hỗ trợ rich console |
| `./gradlew help --info` | Tăng thông tin chẩn đoán | Khi khó xác định JVM/daemon, phân giải hoặc task |

Các lệnh `help` trong bảng là ví dụ ít phụ thuộc plugin; task `help` có sẵn trong Gradle. **`--no-daemon` không bảo đảm chỉ có một JVM:** nếu yêu cầu JVM của build khác JVM Client, Gradle có thể tạo **single-use daemon** rồi dừng nó khi build kết thúc để bảo toàn cấu hình JVM.

`--stop` và `--status` không phải công cụ quản lý mọi daemon của tất cả phiên bản; nếu hai build dùng Gradle khác version, mỗi bản có phạm vi daemon riêng. Log daemon thường nằm ở `<GRADLE_USER_HOME>/daemon/<gradle-version>/daemon-<pid>.out.log`. Có thể đọc log để phân biệt lỗi kết nối, khởi động, thiếu bộ nhớ, tắt bất thường và các cảnh báo JVM.

Ngoài ra `--foreground` khởi chạy Gradle Daemon ở foreground, hữu ích trong tình huống cần theo dõi tiến trình trực tiếp; không phải cờ thường dùng cho mỗi build. Điều chỉnh mức log và số worker chỉ nên dựa trên triệu chứng/đo đạc, tránh tăng song song bằng mọi giá khi RAM hạn chế.

## 9. Chọn JVM: `JAVA_HOME`, `org.gradle.java.home` và Daemon JVM criteria

Có **ba câu hỏi khác nhau**:

1. **Java nào khởi động Wrapper/Gradle Client?** Thường lấy từ `JAVA_HOME` hoặc `java` trên `PATH` (hoặc thiết lập JDK của IDE).
2. **Java nào chạy Gradle Daemon?** Nếu dự án không chỉ định riêng, thường xuất phát từ môi trường Client. Có thể đặt `org.gradle.java.home=/duong/dan/toi/jdk` trong `gradle.properties` hoặc truyền `-Dorg.gradle.java.home=/duong/dan/toi/jdk` khi cần kiểm tra. JDK đó phải tương thích với bản Gradle đang dùng.
3. **Java nào dùng để biên dịch/chạy ứng dụng và test?** Có thể do Java Toolchains và cấu hình `JavaCompile`/`Test` của dự án quyết định; không mặc định là Java của daemon.

Ví dụ kiểm tra JVM của môi trường terminal:

~~~bash
java -version
./gradlew --version
./gradlew --status
~~~

`java -version` phản ánh lệnh Java shell gọi được. `./gradlew --version` cho biết thông tin của bản Gradle và JVM hiển thị theo Gradle; tham khảo cấu hình Daemon và log nếu cần xác định chính xác tiến trình build đang sử dụng JVM nào. Trong môi trường IDE, JDK IDE chọn có thể khác `JAVA_HOME` của terminal.

**Lưu ý với Gradle hiện đại:** nếu build có `gradle/gradle-daemon-jvm.properties` (cấu hình Daemon JVM criteria do task `updateDaemonJvm` quản lý), tiêu chí JVM này có ưu tiên hơn `JAVA_HOME` và `org.gradle.java.home` khi chọn Java cho Daemon. Vì thế, khi đổi Java mà Daemon vẫn chạy bản khác, cần kiểm tra tệp này trước khi kết luận biến môi trường bị bỏ qua.

Ví dụ thay JVM argument tạm thời cho một lần chạy:

~~~bash
./gradlew help -Dorg.gradle.jvmargs="-Xmx2g -XX:MaxMetaspaceSize=512m"
~~~

Dấu nháy giữ chuỗi JVM args có dấu cách thành một tham số shell. Đây là **cấu hình heap của Gradle**, không thay thế lựa chọn JDK; nên dùng thuộc tính trong `gradle.properties` của dự án nếu cần thống nhất lâu dài giữa thành viên và CI.

## 10. Thực hành: tự nhìn thấy hai thư mục Gradle sử dụng

Tại một dự án demo **đã có Wrapper**, bổ sung vào `build.gradle.kts` ở root:

~~~kotlin
// build.gradle.kts (root project)
val demoProjectDirectory = layout.projectDirectory.asFile.absolutePath
val demoRootDirectory = rootProject.layout.projectDirectory.asFile.absolutePath
val demoUserHome = gradle.gradleUserHomeDir.absolutePath

tasks.register("whereGradleRuns") {
    doLast {
        println("projectDir = " + demoProjectDirectory)
        println("rootDir = " + demoRootDirectory)
        println("gradleUserHome = " + demoUserHome)
    }
}
~~~

Các biến được lấy ở pha cấu hình, còn task chỉ in ba chuỗi đường dẫn; đoạn code Kotlin DSL này độc lập với plugin Java. `rootDir` và `projectDir` trùng nhau khi định nghĩa task ở root project; nếu đặt task tương tự ở subproject, `projectDir` sẽ là thư mục của subproject. Output phụ thuộc máy, vì vậy không nên công bố một đường dẫn cụ thể là stdout cố định.

Chạy tại root project trên Linux/macOS:

~~~bash
./gradlew whereGradleRuns
./gradlew -g /tmp/gradle-demo-home whereGradleRuns
~~~

Kết quả cần kiểm tra:

~~~text
projectDir = <đường dẫn root project>
rootDir = <đường dẫn root project>
gradleUserHome = <thư mục Gradle User Home của lần gọi đó>
~~~

Các dòng có dấu `<...>` **là mô tả định dạng, không phải stdout nguyên văn**. Lệnh thứ hai phải in `gradleUserHome` là `/tmp/gradle-demo-home` (có thể hiện dưới dạng đường dẫn đã chuẩn hóa); hai đường dẫn project/root giữ nguyên. Nếu đổi `-p` tới một subproject và chạy task được khai báo tương ứng ở subproject, đường dẫn `projectDir` thay đổi theo project được chọn trong khi Gradle User Home không vì thế đổi theo.

Muốn kiểm chứng tác động lên cache, kiểm tra thư mục `wrapper/dists`, `caches` và `daemon` trong user home **sau khi** chạy; không cần sửa hay xóa cache để thực hiện thử nghiệm. Hãy xóa task demo nếu chỉ dùng nó để học, không đưa thông tin môi trường cục bộ hoặc credential vào stdout của pipeline công khai.

## 11. Mẫu dùng trong CI và script tự động hóa

Ý tưởng cho một runner Linux có repository tại `/work/store`:

~~~bash
# Các đường dẫn trong ví dụ chỉ là minh họa cho máy/runner có thật
cd /work/store

# Cô lập Gradle User Home cho job hoặc lấy từ cache CI tin cậy
export GRADLE_USER_HOME=/work/gradle-user-home

# Chọn rõ start directory, hạn chế worker và log dễ phân tích
./gradlew -p /work/store --no-daemon --max-workers=2 --console=plain :app:build
~~~

**Tiền điều kiện:** dự án có module `app` và task `:app:build` (ví dụ nhờ plugin Java); runner đã được chuẩn bị Java tương thích; Wrapper có quyền thực thi và truy cập bản phân phối/dependency cần thiết. Đây là ví dụ cấu hình CLI, không bảo đảm chạy trên mọi repository chưa có module hoặc task này.

Những quyết định cần thiết để build ổn định:

- **Cố định thư mục chạy** bằng bước `cd` và/hoặc `-p`; không dựa vào mặc định của runner khác nhau.
- **Dùng Wrapper** để lấy phiên bản Gradle do repository kiểm soát.
- **Đặt `GRADLE_USER_HOME` rõ ràng** khi cần cache/cô lập mỗi job; lưu ý cache home có thể chứa thông tin nhạy cảm và init script ảnh hưởng hành vi build.
- **Kiểm soát Java**: khai báo JDK của runner, tiêu chí Daemon JVM và Java toolchain của dự án cho đúng mục tiêu. Không dùng duy nhất `java -version` để suy ra JDK của mọi task.
- **Cân chỉnh giới hạn tiến trình**: heap của Gradle Daemon, số worker, parallel execution và heap của test JVM là các giá trị riêng. Chọn theo RAM/CPU, không tự tăng vô hạn.
- **Giữ log chẩn đoán**: khi lỗi, ghi nhận phiên bản Gradle/JDK, dòng lệnh, nơi start, Gradle User Home đã chọn và các daemon log phù hợp. Tránh đưa secret hoặc đường dẫn riêng nhạy cảm vào log công khai.

`--offline` chỉ hoạt động hiệu quả khi bản phân phối và dependency cần thiết đã sẵn; chuyển sang Gradle User Home trống có thể khiến Wrapper không tải được bản Gradle hoặc Gradle không phân giải được dependency. Không dùng `--offline` như một cách tự động sửa lỗi mạng.

## 12. Những nhầm lẫn và lỗi phổ biến

| Hiện tượng | Cần kiểm tra | Hướng giải quyết |
| --- | --- | --- |
| `./gradlew: No such file or directory` | Shell đang ở đâu, script Wrapper nằm ở đâu? | `cd` vào root hoặc gọi đúng đường dẫn script, ví dụ `../gradlew`; `-p` không thay thế việc tìm script |
| Task chạy sai module | Start directory, root project và task path | Chỉ định `:app:taskName` hoặc `-p` rõ ràng; tránh tên task mơ hồ |
| Gradle tải lại phân phối/dependency mỗi lần | Có thay đổi `GRADLE_USER_HOME`, `-g`, quyền ghi hoặc cache CI không? | Dùng home/caching ổn định nếu phù hợp; kiểm tra `wrapper/dists` và `caches` |
| Thấy hai thư mục `.gradle` khác nhau | Một cái trong root project, một cái là `~/.gradle` | Xác định project-local cache và Gradle User Home theo chức năng, không xóa nhầm |
| Thay `JAVA_HOME` nhưng daemon vẫn dùng JVM khác | `org.gradle.java.home`, Daemon JVM criteria, Gradle JDK của IDE | Kiểm tra thứ tự chọn JVM và cấu hình build; chạy `--status`/xem log nếu cần |
| Sửa `org.gradle.jvmargs` nhưng nhiều daemon cùng tồn tại | Daemon cũ không tương thích với JVM args mới | Xác nhận daemon/version/JDK; khi phù hợp dùng `./gradlew --stop` với đúng Gradle version |
| `--no-daemon` vẫn thấy Java process cho build | Gradle có thể dùng single-use daemon để tôn trọng JVM args | Đây có thể là hành vi hợp lệ; kiểm tra log và cấu hình JVM |
| CI bị thiếu RAM hoặc quá nhiều fork | `--max-workers`, `org.gradle.parallel`, heap Daemon, test `maxHeapSize` | Hạn chế worker và kiểm tra heap của từng loại process |
| Build có hành vi khác dù cùng code | `gradle.properties` ở user home, init scripts, repository credentials | So sánh cấu hình môi trường/home; đưa quy tắc chung vào dự án, bảo vệ secret |
| Bật `-g` nhưng task không tìm được file trong dự án | Task đang dùng đường dẫn tương đối hoặc shell working directory | Kiểm tra `layout.projectDirectory`, `rootProject.layout.projectDirectory`, khai báo file inputs đúng |
| Đặt `--project-cache-dir` nhưng cache dependency không chuyển | Chỉ thay cache của build, không phải user home | Dùng `-g`/`GRADLE_USER_HOME` cho shared caches |
| `-P` không đổi thư mục | `-P` là project property, không phải `-p` | Sửa đúng chữ thường của cờ `-p` |

Khi khắc phục sự cố, nên kiểm tra theo thứ tự **script được gọi → start directory và task path → Gradle User Home/cache → cấu hình properties → Client/Daemon JVM → worker/test process**. Cách phân tách này giúp tránh “sửa” sai tầng, chẳng hạn xóa cache khi thật ra task đang chạy ở sai module.

## 13. Checklist ghi nhớ

1. Xác định vị trí repository và **thư mục hiện tại**; dùng đúng `./gradlew` hoặc `.\gradlew.bat`.
2. Nếu cần chạy từ nơi khác, đặt `-p` để chọn start directory và dùng task path tuyệt đối dạng `:module:task` nếu cần.
3. Xem `GRADLE_USER_HOME`/`-g` để biết Gradle đang dùng cache, init scripts và properties của người dùng nào.
4. Không nhầm `-p`, `-P`, `-g`, `--project-cache-dir`, `GRADLE_HOME` và `GRADLE_USER_HOME`.
5. Phân biệt Java chạy **Client**, Java chạy **Daemon** và Java dành cho **toolchain/test**.
6. Dùng `org.gradle.jvmargs` cho JVM thực thi Gradle, `--max-workers` cho giới hạn worker, cấu hình task phù hợp cho heap của test JVM.
7. Khi đổi JVM/properties, kiểm tra daemon phù hợp và log; nhớ `--no-daemon` đôi khi vẫn dùng tiến trình daemon ngắn hạn.
8. Trong CI, cố định thư mục, JDK và đường dẫn home/caches; không commit credential hoặc dữ liệu Gradle User Home.

## Tài liệu tham khảo

- [Gradle User Manual — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): các cờ `-p`, `-g`, `--project-cache-dir`, daemon và worker.
- [Gradle User Manual — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): nguồn properties, thứ tự ưu tiên, `JAVA_HOME`, `GRADLE_USER_HOME`, JVM arguments.
- [Gradle User Manual — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): Client/Daemon JVM, single-use daemon, `--status`, `--stop` và Daemon JVM criteria.
- [Gradle User Manual — Gradle-managed Directories and Caches](https://docs.gradle.org/current/userguide/directory_layout.html): cấu trúc Gradle User Home và project-local cache.
- [Gradle API — Gradle.getGradleUserHomeDir](https://docs.gradle.org/current/javadoc/org/gradle/api/invocation/Gradle.html): API truy xuất Gradle User Home trong task minh họa.

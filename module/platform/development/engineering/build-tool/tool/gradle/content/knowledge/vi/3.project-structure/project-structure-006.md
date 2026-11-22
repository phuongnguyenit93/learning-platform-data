# Vai trò của thư mục .gradle, Gradle User Home và cache

## 1. Vì sao Gradle có nhiều thư mục mang tên “.gradle”?

Khi chạy một lệnh như `./gradlew test`, Gradle cần lưu nhiều loại dữ liệu ngoài mã nguồn: trạng thái của lần build trước, metadata về thư viện đã tải, kết quả biên dịch có thể dùng lại, bản phân phối Gradle, nhật ký tiến trình nền và các thiết lập dành riêng cho máy của người dùng. Các dữ liệu này không nên bị trộn với mã nguồn được quản lý bằng Git.

**Điểm phân biệt quan trọng nhất:** có một thư mục `.gradle/` **bên trong gốc dự án** và một **Gradle User Home** thường cũng có tên `.gradle` nhưng nằm ở thư mục home của người dùng. Chúng có phạm vi, tuổi thọ và vai trò khác nhau.

| Vị trí | Mục đích chính | Phạm vi | Thường đưa vào Git? |
| --- | --- | --- | --- |
| `<PROJECT_ROOT>/.gradle/` | Trạng thái/cache nội bộ của build đó: incremental build, cấu hình được lưu lại | Một build/dự án Gradle | Không |
| `<GRADLE_USER_HOME>/` (mặc định `~/.gradle/`) | Cache thư viện, bộ phân phối Wrapper, nhật ký daemon, cấu hình người dùng | Các build dùng chung Gradle User Home | Không |
| `<PROJECT_ROOT>/build/` và `<subproject>/build/` | Đầu ra của task: class, báo cáo, JAR, test results... | Một project/subproject | Không |
| `<PROJECT_ROOT>/gradle/wrapper/` | File cấu hình và JAR của **Gradle Wrapper** | Dự án và các thành viên nhóm | Có, bao gồm `gradle-wrapper.jar` và `gradle-wrapper.properties` |
| `<PROJECT_ROOT>/gradle.properties` | Các thuộc tính Gradle ở cấp dự án (nếu có) | Project/build | Tùy nội dung; tuyệt đối không commit bí mật |
| `<GRADLE_USER_HOME>/gradle.properties` | Thuộc tính Gradle cục bộ cấp người dùng | Các build dùng chung User Home | Không |

Ký hiệu `<PROJECT_ROOT>` nghĩa là thư mục chứa root build; `<GRADLE_USER_HOME>` nghĩa là đường dẫn Gradle User Home thực tế. Trong Gradle nhiều module, các module con vẫn có thể có `build/` của riêng mình; root build có thư mục `.gradle/` để giữ state tương ứng.

## 2. Cây thư mục: nhìn một lần để không nhầm

Một dự án Gradle dùng Wrapper và Kotlin DSL có thể trông như sau (Groovy DSL chỉ khác các file `*.gradle` thay cho `*.gradle.kts`):

~~~text
my-app/                             # Project root: thường clone từ Git
├── .gradle/                        # Gradle sinh ra: state/cache theo build
│   ├── <gradle-version>/          # Trạng thái của phiên bản Gradle
│   └── configuration-cache/       # Khi dùng Configuration Cache
├── build/                          # Đầu ra build của root project
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar      # Mã launcher Wrapper: đưa vào Git
│       └── gradle-wrapper.properties
├── gradlew                         # Wrapper trên Linux/macOS
├── gradlew.bat                     # Wrapper trên Windows
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties               # Cấu hình chung của project, nếu có
├── src/
│   └── ...
└── service/
    ├── build.gradle.kts
    └── build/                      # Đầu ra build của subproject
~~~

Trên Linux/macOS, Gradle User Home mặc định là `$HOME/.gradle`; trên Windows thường là `C:\Users\<USERNAME>\.gradle`. Thư mục này ở **ngoài** dự án:

~~~text
<GRADLE_USER_HOME>/
├── caches/
│   ├── <gradle-version>/          # Cache riêng cho phiên bản Gradle
│   ├── modules-2/                 # Dependency artifacts + metadata
│   ├── build-cache-1/             # Local Build Cache, nếu được sử dụng
│   └── ...                        # Các cache khác, tên có thể thay đổi
├── daemon/                         # Registry và log của Gradle Daemon
├── wrapper/
│   └── dists/                     # Bộ phân phối Gradle Wrapper đã tải
├── jdks/                           # JDK có thể được tải bởi toolchain support
├── init.d/                         # Init scripts của người dùng
└── gradle.properties               # Cấu hình riêng của người dùng
~~~

Các tên như `modules-2`, `build-cache-1` và `<gradle-version>` mô tả bố cục phổ biến, **không phải API ổn định để ứng dụng phụ thuộc vào**. Các phiên bản Gradle hoặc cách cấu hình cache có thể thay đổi chi tiết lưu trữ. Không chỉnh file nhị phân/metadata trong những thư mục này bằng tay.

Hai đường dẫn rất dễ nhầm:

- `my-app/gradle/wrapper/gradle-wrapper.properties`: là **cấu hình Wrapper** trong repository; thuộc tính `distributionUrl` chỉ tới bản phân phối Gradle cần tải.
- `~/.gradle/wrapper/dists/`: là **nơi lưu bản Gradle đã tải/giải nén** để Wrapper sử dụng ở máy cục bộ; không phải thư mục cần commit.

Vì vậy, khi clone dự án sang máy khác, nhóm mang theo script Wrapper và cấu hình phiên bản, nhưng không mang theo cache cục bộ.

## 3. Thư mục .gradle ở gốc dự án dùng để làm gì?

`<PROJECT_ROOT>/.gradle/` là nơi Gradle giữ thông tin gắn với build hiện tại, chẳng hạn:

1. **Trạng thái incremental build:** fingerprint/snapshot của đầu vào, đầu ra, lịch sử chạy task để Gradle biết phần việc nào còn cập nhật. Một task có thể báo `UP-TO-DATE` khi điều kiện phù hợp.
2. **Configuration Cache:** dữ liệu cấu hình đã được Gradle tính toán và lưu lại trong `.gradle/configuration-cache/` khi tính năng này được bật; giúp những lần chạy sau với đầu vào cấu hình không đổi bỏ qua phần cấu hình tốn thời gian.
3. **State/metadata riêng của phiên bản Gradle:** nhiều thư mục con có tên phiên bản và được Gradle tự quản lý.

Nó **không phải** nơi duy nhất chứa cache, không phải output chính của mọi task, và không phải thư mục source cần đưa vào Git. Kết quả biên dịch Java thường nằm ở `build/classes/java/main/` hoặc `<module>/build/classes/java/main/`; JAR thường nằm ở `build/libs/` nếu task tương ứng có chạy.

**Phân biệt với `build/`:** `build/` là nơi bạn tìm sản phẩm build và báo cáo; `.gradle/` là state/cache Gradle cần để quyết định cách build. Chạy `clean` (nếu plugin đã tạo task này) thường xóa nội dung output trong `build/` của project được áp dụng; nó **không đồng nghĩa** với xóa `.gradle/` hay dependency cache ở User Home.

Trong multi-project build, khi cần biết “gốc” là đâu, hãy tìm `settings.gradle` hoặc `settings.gradle.kts` của build đang chạy, không suy từ thư mục mã nguồn bạn tình cờ mở trong IDE. Một included build/composite build có thể có state độc lập.

## 4. Gradle User Home lưu trữ gì, đặt ở đâu?

**Gradle User Home** là vùng dữ liệu của người sử dụng Gradle: một máy có nhiều dự án khác nhau có thể chia sẻ những dữ liệu này. Đường dẫn mặc định:

- Linux/macOS: `~/.gradle`, tức `$HOME/.gradle`.
- Windows: thường là `%USERPROFILE%\.gradle` (ví dụ `C:\Users\Lan\.gradle`).

Bạn có thể thay bằng biến môi trường `GRADLE_USER_HOME` hoặc tùy chọn CLI `--gradle-user-home` / `-g`. Tên `GRADLE_USER_HOME` **khác** với `GRADLE_HOME`: `GRADLE_HOME` nếu được dùng là nơi cài đặt một bản Gradle, không phải kho lưu toàn bộ cache và cấu hình người dùng.

Những nhóm dữ liệu chính trong User Home:

- `caches/`: metadata, artifact của dependency, các cache script, artifact transform, local Build Cache nếu dùng.
- `wrapper/dists/`: các bản phân phối Gradle do Wrapper tải về theo URL cấu hình.
- `daemon/`: registry và file log của Gradle Daemon; một tiến trình daemon đang chạy là **process**, không phải chỉ một thư mục trong ổ đĩa.
- `gradle.properties`: các thiết lập dành riêng cho người dùng, ví dụ một số tham số Gradle/JVM hoặc thông tin truy cập repository được đặt hợp lý và bảo vệ bằng quyền file.
- `init.d/`: init scripts có thể ảnh hưởng nhiều build của cùng User Home.
- `jdks/`: Java toolchains có thể tải JDK tương ứng vào đây khi cơ chế tự tải được cấu hình.

**Tác dụng chia sẻ:** nếu hai dự án cùng resolve một artifact từ cùng repository và metadata phù hợp, Gradle có thể tái sử dụng file đã tải từ User Home thay vì tải lặp lại. Ngược lại, khi bạn chuyển máy hoặc dùng User Home mới, các dữ liệu chưa có phải được tạo hoặc tải lại.

**Không đồng bộ nguyên thư mục User Home lên Git, gửi cho đồng nghiệp hay phát hành kèm dự án.** Nó có thể chứa file cấu hình riêng, metadata và dữ liệu nhạy cảm từ môi trường build. Nếu cần chia sẻ cấu hình, hãy khai báo thông số không bí mật trong repository; với bí mật, sử dụng cơ chế secrets/credentials phù hợp.

## 5. “Cache” không phải một loại duy nhất

Từ “cache” trong Gradle có nhiều ý nghĩa; mỗi loại xử lý một công đoạn khác nhau của build.

| Loại | Lưu gì? | Vị trí thường gặp | Khi nào hữu ích? |
| --- | --- | --- | --- |
| **Dependency Cache** | Các JAR/POM và metadata đã resolve, thông tin phiên bản động/changing modules | `<GRADLE_USER_HOME>/caches/modules-2/` | Khi nhiều build cần cùng thư viện; hỗ trợ build offline nếu mọi dependency cần thiết đã có |
| **Local Build Cache** | Đầu ra của **task cacheable**, được định danh từ các input/task implementation | Thường `<GRADLE_USER_HOME>/caches/build-cache-1/`, có thể cấu hình nơi khác | Khi muốn tái sử dụng output task từ lần chạy hoặc workspace khác |
| **Configuration Cache** | Kết quả cấu hình build và task graph đã serialize | `<PROJECT_ROOT>/.gradle/configuration-cache/` | Khi chạy lại nhóm task với đầu vào cấu hình phù hợp, tránh cấu hình lại |
| **Incremental build state / task history** | Snapshot input/output, lịch sử execution để quyết định task có còn up-to-date | `<PROJECT_ROOT>/.gradle/` | Khi build lại trong cùng workspace, bỏ qua việc không đổi |
| **Cache script/Gradle version** | Các build script đã xử lý/biên dịch, dữ liệu riêng cho từng phiên bản Gradle | `<GRADLE_USER_HOME>/caches/<gradle-version>/` | Giảm chi phí khởi tạo, cấu hình |
| **Wrapper distributions** | Bản Gradle Wrapper đã tải và giải nén | `<GRADLE_USER_HOME>/wrapper/dists/` | Tránh tải lại bản Gradle khi dùng lại cùng distribution |

### Dependency Cache khác Build Cache ra sao?

Ví dụ `implementation("org.apache.commons:commons-lang3:3.17.0")` trong một build script Kotlin DSL:

- **Dependency Cache** có thể chứa JAR và metadata của `commons-lang3` sau khi Gradle resolve dependency. Nó trả lời câu hỏi: *“Thư viện đầu vào đã được tải chưa?”*
- **Build Cache** có thể chứa kết quả `compileJava` của một lượt build nếu task phù hợp để cache và caching được bật. Nó trả lời câu hỏi: *“Có thể tái sử dụng kết quả thực thi task với bộ input tương đương không?”*

Có cache thư viện **không** đồng nghĩa có sẵn class biên dịch của ứng dụng. Và có Build Cache **không** làm một dependency chưa có xuất hiện ở chế độ offline.

### UP-TO-DATE, FROM-CACHE và Configuration Cache

Khi nhìn output Gradle, ba hiện tượng sau có ý nghĩa riêng:

- `UP-TO-DATE`: Gradle xác định task không cần chạy do đầu vào/đầu ra còn phù hợp với thông tin theo dõi của build.
- `FROM-CACHE`: Gradle khôi phục đầu ra task từ Build Cache; cần cache khả dụng và task đủ điều kiện.
- `Reusing configuration cache.` (thông báo có thể khác theo phiên bản): Gradle dùng lại kết quả **giai đoạn cấu hình**, không khẳng định mọi task execution đều đã được bỏ qua.

Một build có thể dùng nhiều cơ chế cùng lúc: ví dụ cache cấu hình giúp bỏ qua configuration, cache dependency cung cấp thư viện, và `compileJava` được đánh dấu `UP-TO-DATE` hoặc `FROM-CACHE`. Các thông báo là **dấu hiệu chẩn đoán**, không phải stdout cố định của mọi dự án.

### Build Cache không giống Configuration Cache

Trong chu trình Gradle: initialization → configuration → execution, **Configuration Cache** tối ưu phần configuration; **Build Cache** tối ưu execution của những task có thể cache đầu ra. Hai tính năng độc lập và có yêu cầu tính hợp lệ riêng. Với một số plugin/custom task, Configuration Cache cần plugin/build logic được sửa để tương thích. Không nên xóa cache khi Gradle tự invalidates một entry vì đầu vào đã đổi: cache miss là hành vi bình thường.

## 6. Một lần chạy Gradle đi qua những nơi nào?

Giả sử bạn đứng tại root dự án có Gradle Wrapper và plugin Java, chạy:

~~~bash
./gradlew test --build-cache
~~~

Trên Windows PowerShell, lệnh tương ứng là:

~~~powershell
.\gradlew.bat test --build-cache
~~~

Luồng tổng quát:

1. **Wrapper xác định phiên bản Gradle.** Script `gradlew`/`gradlew.bat` khởi động Wrapper JAR và dùng `distributionUrl` trong `gradle/wrapper/gradle-wrapper.properties`. Nếu cần tải bản phân phối, Wrapper lưu vào vùng `wrapper/dists/` của Gradle User Home được dùng.
2. **Gradle khởi động và nạp cấu hình.** Nó đọc các build/settings script, properties và plugin liên quan; có thể dùng dữ liệu trong User Home hoặc cache configuration trong `<PROJECT_ROOT>/.gradle/` khi đáp ứng điều kiện.
3. **Resolve dependency.** Gradle tra dependency metadata/artifact trong `caches/` của User Home, kết hợp kiểm tra repository theo quy tắc cache và trạng thái offline/online.
4. **Quyết định chạy task.** Gradle kiểm tra điều kiện task, incremental state, Build Cache nếu đã bật; task có thể chạy thật, `UP-TO-DATE`, `FROM-CACHE` hoặc `NO-SOURCE`.
5. **Ghi đầu ra và trạng thái.** Các artifact/test report xuất hiện trong `build/` của project tương ứng; Gradle cập nhật cache/state cần thiết.

Quy trình trên giải thích vì sao cùng một project có thể nhanh hơn ở lần chạy sau, vì sao project clone mới thường phải tải nhiều thứ, và vì sao xóa `build/` chưa chắc làm Gradle tải lại dependency.

## 7. Lệnh và thao tác kiểm tra có kiểm soát

Chạy các lệnh tại **thư mục gốc dự án**, nơi có `gradlew`/`gradlew.bat`. Các lệnh dưới đây phụ thuộc vào trạng thái dự án và môi trường; phần mô tả là kết quả cần quan sát, **không phải output cố định**.

### 7.1. Xem phiên bản và xác định cache đang dùng

~~~bash
# Linux/macOS
./gradlew --version
./gradlew help
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat --version
.\gradlew.bat help
~~~

`--version` cho biết phiên bản Gradle mà Wrapper chạy (cùng thông tin JVM/môi trường). `help` là một tác vụ đơn giản để quan sát việc Gradle cấu hình và chạy build. Kiểm tra thư mục `.gradle/` bên cạnh `settings.gradle(.kts)` và đường dẫn User Home tương ứng. Việc có hay không có từng thư mục con phụ thuộc cấu hình, tính năng đã sử dụng và phiên bản Gradle.

Trên Linux/macOS, có thể xem **đường dẫn mặc định**, và giá trị override của phiên shell nếu có:

~~~bash
printf 'Default: %s\n' "$HOME/.gradle"
printf 'Override: %s\n' "$GRADLE_USER_HOME"
~~~

Trên Windows PowerShell:

~~~powershell
Write-Output (Join-Path $HOME ".gradle")
Write-Output $env:GRADLE_USER_HOME
~~~

Nếu biến môi trường rỗng thì thường dùng giá trị mặc định; nếu có tùy chọn `-g` hoặc `--gradle-user-home` khi gọi Gradle, cần xét thêm tùy chọn đó. Các câu lệnh in trên giúp định hướng, không tự xác minh được mọi tùy chọn đã truyền qua IDE hay script khác.

### 7.2. Tách riêng Gradle User Home để thử nghiệm

Một Gradle User Home tách biệt hữu ích khi bạn muốn kiểm tra vấn đề liên quan cache/cấu hình của user, hoặc giảm ảnh hưởng đến môi trường chung. Ví dụ cho **một lần chạy**:

~~~bash
# Linux/macOS; có thể tải lại bản Gradle và các dependencies
GRADLE_USER_HOME="$HOME/.gradle-demo" ./gradlew help
~~~

~~~powershell
# Windows PowerShell; chỉ áp dụng trong phiên shell hiện tại
$env:GRADLE_USER_HOME = Join-Path $env:TEMP "gradle-demo"
.\gradlew.bat help
~~~

Lúc này User Home mới ban đầu thường chưa có caches và distribution; lần chạy đầu có thể lâu hoặc cần mạng. Trên PowerShell, việc đặt biến như trên còn ảnh hưởng các lệnh Gradle tiếp theo trong shell đó; khi kết thúc thử nghiệm, có thể mở shell mới hoặc khôi phục giá trị biến cũ. Việc đổi User Home **không tự di chuyển** thư mục `.gradle/` nằm trong project root.

CLI cũng hỗ trợ `-g` / `--gradle-user-home` để chỉ định Gradle User Home cho lời gọi Gradle. Khi dùng Wrapper, đặt `GRADLE_USER_HOME` trước lúc gọi như ví dụ trên là cách rõ ràng để Wrapper lẫn Gradle nhận cùng đường dẫn.

### 7.3. Kiểm tra từng loại cache

~~~bash
# Sau khi có test task của plugin Java:
./gradlew test --build-cache
./gradlew test --build-cache

# Quan sát trường hợp không cho phép dùng Build Cache:
./gradlew test --no-build-cache

# Thử cơ chế Configuration Cache khi build/plugin tương thích:
./gradlew help --configuration-cache
./gradlew help --configuration-cache

# Resolve dependency từ cache, không truy cập mạng:
./gradlew test --offline

# Buộc kiểm tra lại trạng thái dependency theo quy tắc Gradle:
./gradlew test --refresh-dependencies
~~~

Trên Windows, đổi `./gradlew` thành `.\gradlew.bat`. Các lệnh `test` giả định project có plugin tạo task đó, ví dụ Java plugin. `--build-cache` bật cơ chế dùng Build Cache cho lượt chạy đó; không đảm bảo mọi task sẽ có cache hit. `--no-build-cache` không tắt Dependency Cache. `--configuration-cache` bật Configuration Cache cho lượt chạy, nếu môi trường/plugin cho phép.

**`--offline`** cho Gradle dùng dữ liệu dependency đã cache; nếu cần artifact/metadata chưa có, resolution có thể thất bại. **`--refresh-dependencies`** yêu cầu Gradle kiểm tra lại tình trạng dependencies và metadata theo cơ chế của nó; nó **không phải** lệnh xóa toàn bộ cache và không nhất thiết tải lại byte giống hệt nếu Gradle xác nhận artifact không đổi.

## 8. Khi gặp lỗi: chọn phạm vi xử lý nhỏ nhất

| Triệu chứng | Cần kiểm tra trước | Hành động hợp lý |
| --- | --- | --- |
| Clone mới, build lần đầu lâu | Wrapper có tải Gradle không? Plugin/dependency có phải tải mới không? | Để Gradle hoàn thành lượt tải đầu; dùng đúng Wrapper và repository |
| `--offline` thất bại vì thiếu dependency | User Home hiện tại có artifact/metadata cần thiết chưa? | Chạy online khi có mạng để resolve; đảm bảo User Home đúng |
| Dependency dường như không cập nhật | Repository, dynamic/changing version, cache metadata, dependency locks | Thử `--refresh-dependencies`; kiểm tra dependency graph thay vì xóa cả User Home |
| Đã thay code nhưng task báo `UP-TO-DATE` không đúng kỳ vọng | Task inputs/outputs có được khai báo chính xác không? Plugin/custom task có lỗi không? | Xem `--info`; sửa mô hình input/output của task |
| Build Cache khôi phục kết quả không mong muốn | Task có khai báo đầy đủ input và output? Plugin có hỗ trợ cache đúng cách? | Chẩn đoán với `--no-build-cache`; sửa task/plugin nếu cần |
| Configuration Cache báo lỗi tương thích | Build script/plugin/task có bắt state không được phép? | Đọc báo cáo và xử lý build logic; thử `--no-configuration-cache` để cô lập vấn đề |
| Daemon lỗi/không khởi động | JDK, JVM args, memory và log trong `<GRADLE_USER_HOME>/daemon/` | Đọc log, kiểm tra JDK; cân nhắc `./gradlew --stop` trước khi chạy lại |
| Ổ đĩa đầy | Cache nào chiếm chỗ: `caches`, `wrapper/dists`, `build`? | Để cơ chế tự dọn của Gradle xử lý; chỉ cân nhắc dọn thủ công đúng phần sau khi hiểu hệ quả |

Lệnh cơ bản thường bị hiểu nhầm:

- `./gradlew clean`: chạy task `clean` nếu được plugin cung cấp, xóa **đầu ra build** ở những project có task đó được thực thi; nó không xóa Gradle User Home.
- `./gradlew --stop`: yêu cầu dừng Gradle Daemon mà lệnh có thể quản lý; nó **không xóa cache**.
- `./gradlew --refresh-dependencies`: kiểm tra lại cache resolution của dependency; không tương đương “xóa `~/.gradle`”.
- `./gradlew --offline`: dùng cache dependency, tránh truy cập network; không có nghĩa tất cả tác vụ build đều không cần chạy.
- `--no-build-cache` và `--no-configuration-cache`: vô hiệu hóa hai cơ chế khác nhau, không tự xóa dữ liệu trên đĩa.

**Không xóa `~/.gradle/` như phản xạ đầu tiên.** Việc đó có thể xóa distributions, cache dependency, init scripts, thiết lập cá nhân và thông tin truy cập repository; lần build kế tiếp có thể phải tải lại nhiều GB hoặc thất bại khi offline. Nếu thật sự cần làm mới cache bị hỏng, trước hết xác định loại cache, tạm dừng các build đang dùng chung User Home, lưu lại cấu hình cần thiết rồi chỉ xử lý thư mục liên quan theo hướng dẫn phù hợp với phiên bản Gradle.

**Đối với `.gradle/configuration-cache`:** Gradle tự invalidates entry khi các đầu vào cấu hình thay đổi. Nếu cần chẩn đoán một trạng thái lỗi cụ thể, có thể tắt tính năng cho một lần chạy bằng `--no-configuration-cache` trước; xóa thư mục configuration cache chỉ là biện pháp có chủ đích sau khi xác định cần thiết, không phải bước bắt buộc sau mọi lần đổi build script.

## 9. Git, chia sẻ dự án và môi trường CI

Khi chia sẻ project:

- **Commit:** `settings.gradle(.kts)`, `build.gradle(.kts)`, `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, `gradle/wrapper/gradle-wrapper.properties` và các cấu hình project cần thiết không chứa bí mật.
- **Ignore:** `.gradle/`, `build/` và các thư mục sinh ra bởi build khác tùy project. Ví dụ thông dụng trong `.gitignore`:

~~~gitignore
.gradle/
**/build/
~~~

Quy tắc cụ thể phải xét cấu trúc repository: nếu có thư mục nguồn tên `build` được cố ý quản lý bằng Git thì cần ngoại lệ phù hợp. Giữ nguyên file Wrapper đã được kiểm tra nguồn gốc và phiên bản; file Wrapper không phải cache, nên đừng xóa nó khi “dọn Gradle”.

Trong CI, cache có thể giảm thời gian tải dependency và thực thi task, nhưng cache là **tối ưu hiệu năng** chứ không phải nguồn sự thật của bản build. CI vẫn phải biết phiên bản Gradle/JDK, plugin, dependency và các repository tương ứng. Cache keys và phạm vi chia sẻ cần được chọn phù hợp để tránh dùng nhầm state. Không nên đưa toàn bộ User Home cá nhân hoặc secrets của developer vào artifact/cache được công khai; cân nhắc công cụ cache hỗ trợ Gradle và quyền truy cập của hệ thống CI. Configuration Cache có thể chứa state nhạy cảm và cơ chế mã hóa theo môi trường, nên đừng tùy tiện sao chép giữa máy.

## 10. Tình huống thực hành và tự kiểm tra

**Tình huống A — Dự án A đã tải JUnit, dự án B mới thêm JUnit cùng phiên bản.** Nếu cả hai dùng cùng Gradle User Home và metadata/repository phù hợp, Gradle có thể tái sử dụng artifact ở **Dependency Cache**. Điều này chưa bảo đảm compilation/test output của B lấy được từ **Build Cache**, vì output task còn phụ thuộc input và cấu hình của B.

**Tình huống B — Chạy `clean` rồi `test --build-cache`.** Output trong `build/` có thể bị xóa, trong khi cache thư viện và local Build Cache vẫn còn. Nếu task cacheable và cache hit, Gradle có thể phục hồi output với `FROM-CACHE`; nếu không, task chạy lại. Đây là lý do `clean` không đồng nghĩa “build lại hoàn toàn từ số không”.

**Tình huống C — Copy source code sang máy khác nhưng không copy `~/.gradle`.** Dự án vẫn có thể build nhờ Wrapper và cấu hình đã commit, miễn là máy có JDK/mạng/repository phù hợp. Lượt đầu có thể tải lại Gradle distribution và dependencies; không cần mang nguyên cache cũ.

**Tình huống D — Project tự dưng có `.gradle/configuration-cache`.** Đó thường là state do Configuration Cache tạo khi đã bật; nó không phải thư mục mã nguồn, cũng không phải dependency cache. Thử bật/tắt tính năng một cách có kiểm soát để quan sát khác biệt cấu hình, thay vì đoán theo tên thư mục.

Tự trả lời:

1. Hai thư mục đều tên `.gradle` nhưng một nằm trong repo, một nằm trong `$HOME`. Cái nào có thể chia sẻ cache dependency giữa nhiều dự án? **Gradle User Home**.
2. `build/libs/app.jar` là Dependency Cache hay output build? **Output của task build/packaging**.
3. `--refresh-dependencies` có xóa mọi bản Gradle Wrapper trong `wrapper/dists` không? **Không**.
4. Có `FROM-CACHE` thì configuration phase chắc chắn đã được cache không? **Không**; đó là dấu hiệu đầu ra task được lấy từ Build Cache.
5. Tài liệu nào nên commit để người khác tự lấy đúng Gradle version? **Wrapper scripts, JAR và `gradle-wrapper.properties`**.
6. Muốn tái hiện vấn đề trong User Home mà không tác động kho cache cũ nên làm gì? **Dùng một `GRADLE_USER_HOME` thử nghiệm riêng** và lưu ý phải tải các thành phần cần thiết.

## Tài liệu chính thức

- [Gradle-managed Directories and Caches](https://docs.gradle.org/current/userguide/directory_layout.html) — vị trí và cấu trúc Project Root, Gradle User Home, cơ chế cleanup cache.
- [Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html) — artifact, metadata, offline mode và refresh dependencies.
- [Build Cache](https://docs.gradle.org/current/userguide/build_cache.html) — cache output task, cache local/remote.
- [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html) — lưu và tái sử dụng trạng thái cấu hình.
- [The Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) — Wrapper script, properties và cách phân phối phiên bản Gradle.
- [Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html) — biến môi trường như `GRADLE_USER_HOME` và thuộc tính Gradle.

**Ghi nhớ:** `project/.gradle` giữ **state của build**, `Gradle User Home` giữ **dữ liệu và cache dùng chung ở cấp người dùng**, `build` chứa **đầu ra task**, còn `gradle/wrapper` chứa **cấu hình Wrapper phải được quản lý cùng mã nguồn**. Hiểu ranh giới này giúp chẩn đoán lỗi, tránh xóa nhầm dữ liệu và lựa chọn cách cache hiệu quả.

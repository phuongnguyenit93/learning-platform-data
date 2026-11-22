# Xóa đầu ra cũ: mục đích và giới hạn của thao tác clean

Trong vòng đời build Java, đầu ra được tạo ra ở nhiều giai đoạn: source được biên dịch thành class files, resource được xử lý, test tạo báo cáo, rồi các class và resource được đóng gói thành JAR hoặc một artifact khác. Những file này thường được lưu dưới thư mục build của từng Gradle project. Khi build lại, Gradle có thể sử dụng các đầu ra đã tồn tại nếu xác định chúng vẫn hợp lệ.

Thao tác `clean` giải quyết một nhu cầu cụ thể: xóa các đầu ra build để lần chạy tiếp theo tạo lại chúng. Việc này hữu ích khi cần kiểm tra một build từ trạng thái output sạch, loại bỏ file cũ gây nhiễu trong quá trình điều tra, hoặc chuẩn bị một workspace trước khi tạo artifact mới.

Tuy nhiên, `clean` không phải nút “đặt lại toàn bộ máy”. Nó không xóa mọi cache, dependency đã tải, trạng thái bên ngoài dự án hay mọi file mà một script từng tạo ra. Hiểu đúng phạm vi của thao tác này giúp tránh mất dữ liệu, tránh tốn thời gian build không cần thiết và quan trọng hơn là không dùng `clean` để che giấu lỗi trong cách khai báo task.

## 1. `clean` làm gì trong Gradle?

Với Gradle, task `clean` thường được cung cấp bởi Base Plugin và xóa thư mục build của project. Java plugin áp dụng các thành phần nền tảng cần thiết để có lifecycle task này. Thư mục build mặc định thường là `build/` nằm trong project directory, nhưng dự án có thể cấu hình vị trí khác thông qua build directory.

Ví dụ, một project Java có thể có cấu trúc:

~~~text
orders-service/
├── src/
│   ├── main/
│   └── test/
├── build.gradle
├── gradle.properties
└── build/
    ├── classes/
    ├── generated/
    ├── resources/
    ├── reports/
    ├── test-results/
    ├── libs/
    └── tmp/
~~~

Sau khi chạy:

~~~bash
./gradlew :orders-service:clean
~~~

Gradle xóa build directory của project `orders-service` theo cấu hình hiện hành. Các file được tạo trong những lần build trước như class files, processed resources, test reports và JAR trong thư mục đó sẽ bị xóa. Lần chạy tiếp theo sẽ phải tạo lại những output cần thiết.

Với Windows PowerShell, có thể gọi Gradle Wrapper như sau:

~~~powershell
.\gradlew.bat :orders-service:clean
~~~

Đường dẫn và task path trong ví dụ chỉ minh họa. Hãy dùng đúng project path và wrapper của repository đang làm việc.

### 1.1. `clean` xóa output, không xóa source

Mục đích của build directory là chứa các file có thể được tạo lại từ source, cấu hình và dependency. Vì vậy, source code và dữ liệu đầu vào do nhóm quản lý nên nằm ở các vị trí riêng, chẳng hạn:

- `src/main/java`: mã nguồn Java chính.
- `src/test/java`: mã nguồn kiểm thử.
- `src/main/resources`: resource do dự án quản lý.
- `build.gradle` hoặc `build.gradle.kts`: build logic của project.
- Các file schema, template hoặc cấu hình nguồn được quản lý trong repository.

Những file này không thuộc output mặc định cần xóa của task `clean`. Nếu dự án đặt file nguồn hoặc dữ liệu do con người quản lý bên trong build directory, cấu hình đó tạo ra rủi ro mất dữ liệu khi clean. Hãy giữ source input và output được sinh ra ở những vùng riêng biệt.

### 1.2. Vì sao cần xóa output cũ?

Gradle có thể bỏ qua task khi output được xem là up-to-date. Đây là hành vi mong muốn trong build thông thường vì không cần làm lại công việc nếu input không đổi và task mô tả đúng input/output.

Nhưng trong một số tình huống, output còn sót có thể làm khó việc xác định nguyên nhân:

- Một task tùy biến đã tạo file nhưng không khai báo đầy đủ input.
- Một script bên ngoài đã chép file vào build directory.
- Một task từng dùng đường dẫn output cũ, sau đó build logic được thay đổi.
- Một bước sinh mã bị dừng giữa chừng và để lại một phần file.
- Một artifact cũ vẫn còn trong thư mục output, khiến người dùng tưởng đó là artifact mới.
- Một lỗi chỉ xuất hiện khi build từ trạng thái sạch, nhưng không xuất hiện khi dùng output của lần chạy trước.

Xóa output rồi build lại giúp kiểm tra liệu kết quả có phụ thuộc vào trạng thái build directory trước đó hay không.

## 2. Phạm vi của task `clean`

Không nên suy luận phạm vi xóa chỉ từ tên task. Gradle là hệ thống multi-project; mỗi project có thể có build directory và task riêng. Cần biết task nào thực sự được chọn trong lệnh.

Ví dụ:

~~~bash
# Chọn task clean của project orders-service
./gradlew :orders-service:clean

# Xem các task clean được chọn khi gọi từ root
./gradlew clean --dry-run
~~~

Task path đầy đủ giúp giới hạn rõ project cần thao tác. Khi chạy task selector không có project path, Gradle có thể chọn các task cùng tên trong phạm vi project phù hợp của build. Hãy đọc output của `--dry-run` hoặc task list để xác nhận chính xác những project nào sẽ bị clean.

Trong một multi-project build, có thể có các thư mục:

~~~text
repository/
├── build/
├── module-a/
│   └── build/
├── module-b/
│   └── build/
└── module-c/
    └── build/
~~~

Mỗi project có thể có build directory riêng. Việc xóa output của một module không mặc nhiên có nghĩa là mọi output trong toàn repository đã bị xóa. Ngược lại, một task selector có thể chọn nhiều task clean nếu build được cấu hình theo cách đó. Khi dữ liệu quan trọng nằm ở nhiều project, xác định phạm vi task trước khi thực hiện.

### 2.1. Build directory có thể được cấu hình lại

Mặc định, Gradle thường dùng thư mục `build` trong project. Tuy nhiên, build logic có thể thay đổi vị trí này, ví dụ để đưa output vào một thư mục dùng chung hoặc một vùng riêng cho CI.

Vì task clean hoạt động theo build directory được cấu hình, không nên mặc định rằng nó luôn xóa chính xác một đường dẫn cố định. Nếu project thay đổi `layout.buildDirectory`, hãy xác định giá trị thực tế và kiểm tra task graph.

Một task tùy biến cũng có thể ghi output ra ngoài build directory, chẳng hạn:

- Thư mục generated source được cấu hình ở một vị trí khác.
- Một file được ghi vào thư mục gốc repository.
- Artifact được copy sang thư mục distribution.
- File được tạo ở thư mục tạm của hệ điều hành.
- Output được ghi vào một volume hoặc storage bên ngoài.

Những file này có thể không bị task clean mặc định xóa. Nếu chúng là output thuộc quy trình build, cần khai báo và quản lý vòng đời của chúng một cách rõ ràng. Không nên mở rộng task clean thành thao tác xóa rộng tùy tiện chỉ để “dọn cho sạch”.

## 3. Những thứ `clean` thường không xóa

Một nhầm lẫn phổ biến là cho rằng chạy `clean` sẽ xóa mọi thứ Gradle từng sử dụng. Trên thực tế, task clean chủ yếu xử lý build directory của project. Nhiều loại cache và trạng thái khác nằm ngoài phạm vi đó.

| Thành phần | Vị trí thường gặp | Task `clean` mặc định có xóa không? |
|---|---|---|
| Compiled classes và processed resources | Project `build/` | Có, nếu nằm trong build directory được clean |
| JAR/WAR trong output directory | Project `build/libs/` hoặc output đã cấu hình trong build directory | Có, nếu thuộc build directory đó |
| Test reports và test results | Project `build/reports/`, `build/test-results/` | Có, nếu nằm trong build directory đó |
| Gradle project cache | Project `.gradle/` | Không |
| Gradle User Home caches | Thường là `~/.gradle/caches/` hoặc vị trí GRADLE_USER_HOME | Không |
| Gradle Wrapper distributions | Thường nằm trong Gradle User Home | Không |
| Source code và file cấu hình | `src/`, build scripts và các file nguồn khác | Không |
| Docker images, containers và volumes | Docker daemon/storage | Không |
| Database hoặc service bên ngoài | Hệ thống riêng | Không |
| Output tùy biến nằm ngoài build directory | Đường dẫn do build logic hoặc script chọn | Không, trừ khi task clean được cấu hình xử lý rõ ràng |

### 3.1. Gradle User Home và dependency cache

Khi Gradle tải plugin hoặc thư viện Maven, các artifact và metadata thường được lưu trong Gradle User Home. Trên nhiều máy, thư mục này là `~/.gradle`; nó có thể được thay đổi bằng biến môi trường `GRADLE_USER_HOME`.

Chạy `clean` không xóa các dependency đã tải về. Đây là chủ ý: xóa output của project không cần thiết phải tải lại toàn bộ thư viện. Nhờ vậy, một clean build vẫn có thể sử dụng dependency cache để tiết kiệm thời gian và băng thông.

Nếu muốn điều tra vấn đề dependency resolution, cần phân biệt task clean với các thao tác liên quan đến dependency cache. Ví dụ, `--refresh-dependencies` yêu cầu Gradle kiểm tra lại trạng thái dependency theo cơ chế resolution của nó. Đây là lựa chọn khác với việc xóa build directory và không nên thêm vào mọi lần clean một cách máy móc.

### 3.2. Gradle project cache và daemon

Gradle có thể lưu trạng thái dự án trong thư mục `.gradle/` ở project và sử dụng Gradle Daemon để tăng tốc các lần chạy. Task `clean` không có nghĩa là dừng daemon hoặc xóa toàn bộ trạng thái Gradle.

Nếu đang điều tra một vấn đề cụ thể liên quan tới daemon hoặc project cache, hãy dùng biện pháp chẩn đoán phù hợp với triệu chứng và tài liệu Gradle. Xóa toàn bộ cache hoặc dừng daemon không phải bước mặc định để xử lý mọi lỗi build.

### 3.3. Công cụ bên ngoài và môi trường runtime

Một dự án có thể sử dụng Docker Compose, database, message broker, file được tải từ hệ thống khác hoặc một service đang chạy trên máy. Các tài nguyên đó không nằm trong build directory của Gradle.

Chạy `clean` không xóa container, volume, database record hoặc file dữ liệu bên ngoài. Điều này rất quan trọng khi một quy trình build hoặc test có side effect ra môi trường ngoài. Hãy quản lý vòng đời những tài nguyên đó bằng công cụ và lệnh có phạm vi rõ ràng của chúng.

## 4. `clean build` có ý nghĩa gì?

Cụm từ “clean build” thường được dùng để chỉ việc xóa output cũ rồi chạy lại build. Ví dụ:

~~~bash
./gradlew clean build
~~~

Trong một Gradle invocation, các task được chọn và quan hệ phụ thuộc sẽ được đưa vào task graph. Task clean được thực hiện trước những task phụ thuộc vào nó theo thứ tự graph. Tuy nhiên, với multi-project build, cần xác định task clean nào đã được chọn và những project nào nằm trong phạm vi.

Clean build hữu ích trong các trường hợp:

- Kiểm tra dự án có thể tạo lại output từ source và cấu hình hay không.
- Điều tra lỗi có thể do output cũ hoặc trạng thái build directory.
- Xác minh thay đổi trong task sinh mã hoặc resource processing.
- Tạo lại artifact trước một lần kiểm chứng hoặc đóng gói quan trọng.
- Kiểm tra workspace CI có phụ thuộc vào output không được quản lý hay không.

Một clean build là phép thử hữu ích, nhưng không phải bằng chứng đầy đủ rằng build có thể tái lập ở mọi môi trường. Nó vẫn có thể sử dụng dependency cache, build cache, toolchain đã cài, biến môi trường hoặc service bên ngoài.

### 4.1. Clean build không đồng nghĩa với cold build

Có ít nhất ba khái niệm cần phân biệt:

- **Clean build:** xóa build output theo task clean rồi chạy build.
- **Build không dùng build cache:** tắt việc tái sử dụng output từ Gradle build cache trong invocation đó.
- **Cold environment build:** chạy trong môi trường mới hoặc được cô lập, với trạng thái local tối thiểu và các đầu vào được xác định.

Sau `clean build`, Gradle vẫn có thể phục hồi output từ build cache nếu task hỗ trợ cache và cache được bật. Dependency cache cũng vẫn có thể được sử dụng. Do đó, “đã chạy clean” không đồng nghĩa với “mọi task đã thực thi lại từ đầu” hoặc “đã tải lại mọi dependency”.

Khi cần kiểm tra việc tái sử dụng build cache, có thể so sánh với invocation có `--no-build-cache`:

~~~bash
./gradlew clean build --no-build-cache
~~~

Nếu cần yêu cầu task chạy lại và bỏ qua kiểm tra up-to-date, có thể cân nhắc `--rerun-tasks`. Cờ này thay đổi hành vi thực thi task và có thể làm build lâu hơn; chỉ dùng khi mục tiêu điều tra yêu cầu. Hãy xem task outcome trong log để xác nhận điều gì thực sự đã chạy.

Không nên ghép mọi cờ này vào một lệnh chuẩn cho mọi tình huống. Mỗi cờ kiểm tra một khía cạnh khác nhau; dùng quá nhiều có thể làm thay đổi điều kiện build mà ta đang muốn quan sát.

## 5. `clean` khác gì với các thao tác khác?

Một số lệnh có thể tạo cảm giác tương tự nhưng tác động vào những lớp trạng thái khác nhau.

| Thao tác | Mục đích chính | Phạm vi điển hình |
|---|---|---|
| `clean` | Xóa output build của project | Build directory |
| `build` | Chạy lifecycle build | Các task verification và assembly theo cấu hình |
| `assemble` | Tạo artifact | Các task đóng gói |
| `check` | Chạy các bước kiểm chứng | Test và các verification task đã được gắn |
| `--no-build-cache` | Không dùng Gradle build cache trong invocation | Cách tái sử dụng output task |
| `--rerun-tasks` | Yêu cầu chạy lại task, bỏ qua up-to-date checks | Quyết định thực thi task |
| `--refresh-dependencies` | Kiểm tra lại dependency resolution | Dependency metadata/artifact resolution |
| `gradle --stop` | Dừng Gradle Daemon | Các daemon Gradle liên quan |
| Xóa `.gradle/` hoặc Gradle User Home | Xóa trạng thái/cache Gradle rộng hơn | Project cache hoặc cache dùng chung |
| Rebuild trong IDE | Phụ thuộc cách IDE tích hợp build | Có thể gọi Gradle task hoặc dùng cơ chế riêng |

Không nên dùng các thao tác này thay thế lẫn nhau. Nếu vấn đề là một file class cũ trong build directory, clean có thể phù hợp. Nếu vấn đề là phiên bản dependency được resolve, cần điều tra dependency. Nếu vấn đề là daemon, xem xét daemon. Nếu vấn đề nằm trong database test, phải quản lý database test riêng.

## 6. Giới hạn của clean khi chẩn đoán lỗi build

Một clean build có thể làm lỗi biến mất, nhưng điều đó không có nghĩa nguyên nhân đã được sửa.

Ví dụ, một task tùy biến đọc file cấu hình nhưng không khai báo file đó là input. Khi file thay đổi, Gradle có thể cho rằng task vẫn up-to-date và giữ output cũ. Chạy clean xóa output; task buộc phải tạo lại và kết quả có vẻ đúng.

Nếu chỉ thêm clean vào mọi lệnh build, nhóm có thể che đi lỗi khai báo input/output. Build sẽ luôn làm lại nhiều việc, mất lợi ích incremental build và vẫn còn lỗi nền tảng trong task.

Một ví dụ khác là script copy file vào build directory mà không gắn file đó với task nào. Clean xóa file, nhưng lần chạy tiếp theo script lại tạo ra nó. Nếu không biết script là nguồn tạo file, người điều tra có thể mất nhiều thời gian tìm nguyên nhân.

Khi clean làm lỗi biến mất, hãy tiếp tục điều tra:

1. Xác định task nào đã tạo file liên quan.
2. Tìm tất cả input thực tế mà task đọc.
3. So sánh input đó với những input Gradle đã được khai báo.
4. Kiểm tra output path và task dependency.
5. Xác định có script hoặc công cụ ngoài Gradle ghi vào cùng thư mục hay không.
6. Chạy lại theo cùng điều kiện để xác nhận nguyên nhân đã được sửa.

Clean là công cụ chẩn đoán trạng thái output. Nó không thay thế việc sửa task contract hoặc xử lý nguồn gốc của file sai.

## 7. Chi phí và rủi ro khi clean quá thường xuyên

Xóa output trước mọi lần build có một số chi phí:

- Compiler phải biên dịch lại source thay vì dùng output up-to-date.
- Resource processing và các bước sinh file phải chạy lại.
- Test classes và những output phụ thuộc phải được tạo lại.
- Packaging phải tạo lại artifact.
- Build có thể kéo dài hơn đáng kể với dự án nhiều module.
- Một số báo cáo cũ bị xóa, làm mất bằng chứng cần thiết nếu chưa lưu.
- Những file được đặt nhầm trong build directory có thể bị xóa dù chúng không phải output có thể tái tạo.

Build cache có thể giảm một phần chi phí nếu output task có thể được phục hồi. Tuy nhiên, clean liên tục vẫn làm mất output trong workspace và có thể gây thêm thao tác I/O hoặc cache restore.

Trong phát triển hằng ngày, incremental build thường là lựa chọn hiệu quả. Clean nên được dùng khi có mục đích cụ thể: xác minh từ trạng thái sạch, điều tra output cũ, hoặc chuẩn bị môi trường theo yêu cầu của pipeline.

### 7.1. Cẩn thận với dữ liệu cần giữ lại

Một thư mục build có thể chứa test report, log hoặc file trung gian hữu ích cho việc điều tra. Trước khi chạy clean sau một build thất bại, hãy lưu các báo cáo và log cần thiết.

Nếu một task tùy biến ghi file do người dùng chỉnh sửa vào build directory, đó là dấu hiệu thiết kế output chưa phù hợp. Clean có thể xóa file đó. Hãy chuyển dữ liệu được quản lý bởi con người ra khỏi build directory hoặc điều chỉnh vị trí output theo một hợp đồng rõ ràng.

## 8. Dùng clean trong dự án nhiều module

Trong multi-project build, mỗi subproject có thể có output riêng. Ví dụ:

~~~text
repository/
├── build/
├── service-a/
│   └── build/
├── service-b/
│   └── build/
└── shared-library/
    └── build/
~~~

Nếu chỉ muốn xóa output của `service-a`, dùng task path cụ thể:

~~~bash
./gradlew :service-a:clean
~~~

Nếu muốn kiểm tra task clean nào sẽ được chọn khi chạy từ root:

~~~bash
./gradlew clean --dry-run
~~~

Sau đó xem output task graph để biết các project bị ảnh hưởng. Không nên giả định lệnh root chỉ xóa một build directory hoặc chắc chắn xóa mọi build directory mà không kiểm tra cấu hình build.

Một số repository có thể định nghĩa task aggregate riêng ở root hoặc có custom build logic thay đổi quan hệ giữa các task. Task path, project structure và plugin đang áp dụng quyết định phạm vi thực tế.

## 9. Dùng clean trong CI

CI thường tạo workspace mới cho mỗi job, nhưng không phải hệ thống nào cũng dùng workspace hoàn toàn mới. Một số runner tái sử dụng thư mục làm việc hoặc mount cache giữa các lần chạy.

Nếu workspace đã sạch và không chứa build output cũ, chạy clean có thể không mang lại nhiều giá trị. Nếu runner tái sử dụng workspace, clean có thể giúp loại bỏ output project còn sót trước khi build. Dù vậy, cần phân biệt build output với cache mà CI cố ý giữ lại.

Một cấu hình CI tốt nên xác định rõ:

- Workspace được tạo mới hay tái sử dụng.
- Build directory nào được giữ giữa các job.
- Gradle build cache được bật ở đâu.
- Dependency cache được chia sẻ như thế nào.
- Artifact và report nào cần upload sau khi job kết thúc.
- Cách lưu báo cáo khi build fail.

Không nên xóa cache CI một cách định kỳ chỉ vì muốn build “sạch”. Cache dependency và build cache là các cơ chế tối ưu riêng; nếu cần kiểm tra tính đúng đắn của cache, hãy thiết kế một lần chạy so sánh có mục tiêu và ghi nhận điều kiện.

## 10. Một quy trình clean có kiểm soát

Khi cần kiểm tra từ trạng thái output sạch, có thể làm theo quy trình sau.

### Bước 1: Xác định project và output cần làm sạch

Kiểm tra project path, build directory và task clean tương ứng. Nếu là multi-project build, xác định rõ chỉ cần clean một module hay nhiều module.

### Bước 2: Giữ lại bằng chứng cần thiết

Nếu lần build trước thất bại, lưu log, test report hoặc file cần điều tra trước khi xóa build directory. Đừng xóa output rồi mới nhận ra báo cáo lỗi đã mất.

### Bước 3: Kiểm tra task graph

Dùng dry run để xem task nào được chọn:

~~~bash
./gradlew :orders-service:clean --dry-run
~~~

Dry run chỉ giúp quan sát task selection; nó không thực hiện thao tác xóa.

### Bước 4: Chạy clean và build

~~~bash
./gradlew :orders-service:clean :orders-service:build
~~~

Dùng đúng task path và lifecycle phù hợp với module. Với library, artifact có thể được tạo bởi jar; với Spring Boot application, cần xác nhận bootJar được thực hiện theo cấu hình.

### Bước 5: Kiểm tra kết quả

Xác nhận task outcome, test report và artifact. Kiểm tra artifact được tạo trong lần chạy này, có cấu trúc đúng và gắn với đúng project. Nếu cần so sánh với build trước, lưu checksum và metadata của cả hai lần chạy.

### Bước 6: Điều tra nếu clean làm thay đổi kết quả

Nếu build chỉ thành công sau khi clean, tìm task có output cũ hoặc input chưa được khai báo. Sửa nguyên nhân, rồi chạy lại incremental build để kiểm tra rằng task vẫn cập nhật đúng khi input thay đổi.

## 11. Ví dụ: task sinh mã bị thiếu input

Giả sử một task tạo file Java từ schema:

~~~text
src/main/schema/order.json
        |
        v
generateOrderModel
        |
        v
build/generated/sources/order/Order.java
        |
        v
compileJava
~~~

Nếu task sinh mã không khai báo schema là input, Gradle có thể không nhận ra schema đã thay đổi. Khi đó:

1. Lần build đầu tạo Order.java.
2. Người phát triển sửa order.json.
3. Gradle không thấy input đã khai báo thay đổi và có thể giữ output cũ.
4. Build tiếp tục với source sinh từ schema cũ.
5. Chạy clean xóa build directory, nên task sinh mã chạy lại và tạo source mới.

Kết quả sau clean có thể đúng, nhưng lỗi gốc là task chưa khai báo input đầy đủ. Cách sửa là mô tả schema như input của task và file source được sinh như output. Khi đó Gradle có thể đánh giá trạng thái task chính xác mà không cần clean mỗi lần.

Ví dụ này cho thấy clean có giá trị trong việc phát hiện trạng thái output cũ, đồng thời cũng cho thấy vì sao không nên biến clean thành cách khắc phục thường trực.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Clean xóa toàn bộ cache Gradle | Clean chủ yếu xóa build directory của project |
| Clean xóa dependency đã tải | Dependency cache thường nằm trong Gradle User Home và vẫn được giữ |
| Clean đảm bảo mọi task chạy lại từ đầu | Build cache hoặc cơ chế task khác vẫn có thể tái sử dụng output |
| Clean sửa được lỗi build | Clean chỉ xóa output; lỗi trong source, cấu hình hoặc task logic vẫn còn |
| Clean luôn cần trước build | Incremental build là hành vi bình thường; clean chỉ cần khi có mục tiêu cụ thể |
| Clean root chắc chắn chỉ xóa root build | Task selector và task graph có thể chọn nhiều project; cần kiểm tra |
| File nằm trong build directory nào cũng an toàn để xóa | Dự án có thể đã đặt nhầm dữ liệu do con người quản lý vào đó |
| Clean sẽ xóa container hoặc database test | Tài nguyên bên ngoài cần được quản lý riêng |
| Build thành công sau clean chứng minh build reproducible | Cần kiểm soát input, môi trường và so sánh kết quả theo mức yêu cầu |

## 13. Checklist trước và sau khi chạy clean

Trước khi chạy:

- [ ] Xác định rõ lý do cần clean.
- [ ] Xác định project path và phạm vi task.
- [ ] Biết build directory thực tế của project.
- [ ] Kiểm tra có dữ liệu hoặc báo cáo cần giữ lại không.
- [ ] Xác nhận source input không nằm trong build directory.
- [ ] Xác định output tùy biến nằm ngoài build directory có cần xử lý riêng không.

Sau khi chạy:

- [ ] Task clean đã thực hiện trên đúng project.
- [ ] Build tiếp theo tạo lại output cần thiết.
- [ ] Test và verification task được chạy hoặc có trạng thái skip giải thích được.
- [ ] Artifact mới được xác định đúng, không lấy nhầm file cũ ở nơi khác.
- [ ] Nếu kết quả thay đổi sau clean, đã tìm nguyên nhân output/input thay vì chỉ giữ clean như một workaround.
- [ ] Báo cáo và artifact cần lưu đã được giữ theo chính sách dự án.

## Kết luận

Task `clean` của Gradle xóa build output trong phạm vi build directory được cấu hình cho project. Nó hữu ích khi cần tạo lại output, kiểm tra trạng thái sạch hoặc điều tra lỗi có thể liên quan tới file cũ. Nó không xóa source, dependency cache, Gradle User Home, daemon hay tài nguyên bên ngoài theo mặc định.

Clean cũng không chứng minh mọi task đã chạy lại, không đảm bảo build reproducible và không sửa được lỗi trong cách khai báo input/output. Khi dùng có mục tiêu, xác định đúng phạm vi và kiểm tra task outcome sau đó, clean là công cụ hữu ích trong vòng đời build. Khi dùng thay cho việc sửa nguyên nhân, nó chỉ làm quy trình chậm hơn và có thể che giấu vấn đề cần giải quyết.

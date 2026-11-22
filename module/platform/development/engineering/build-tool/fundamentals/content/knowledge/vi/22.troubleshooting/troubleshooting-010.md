# Làm mới cache hoặc clean có kiểm soát sau khi xác định giả thuyết

Khi một build Gradle có kết quả bất thường, phản xạ thường gặp là xóa thư mục cache hoặc chạy clean. Cách đó đôi khi giúp, nhưng cũng có thể làm mất bằng chứng, khiến lần build sau tải lại nhiều dependency hoặc che khuất lỗi thật. Trước khi làm mới dữ liệu, hãy xác định **giả thuyết cụ thể**: output cũ trong project không đúng, metadata dependency bị lỗi thời, output task lấy từ build cache không phù hợp, configuration cache không tương thích, hay daemon đang giữ trạng thái không mong muốn.

Gradle có nhiều lớp lưu trữ khác nhau. Lệnh **clean** chỉ xử lý output build của project theo task clean; **--refresh-dependencies** yêu cầu Gradle kiểm tra lại trạng thái dependency; **--no-build-cache** tắt sử dụng build cache cho lần chạy; **--no-configuration-cache** tắt tái sử dụng configuration cache; **--rerun-tasks** yêu cầu chạy lại task. Các lệnh này không thay thế nhau.

Nguyên tắc của bài này là: ghi lại lỗi, chọn lớp dữ liệu có liên quan, dùng thao tác nhỏ nhất để kiểm chứng giả thuyết, rồi so sánh kết quả. Chỉ xóa thủ công một vùng cache cụ thể khi đã có bằng chứng cho thấy vùng đó là nguyên nhân và Gradle không có tùy chọn phù hợp để làm mới.

## 1. Vì sao cần xác định giả thuyết trước khi clean hoặc xóa cache?

Một thông báo build lỗi có thể xuất phát từ nhiều nguyên nhân:

- Source hoặc resource đã thay đổi nhưng output trong thư mục build không được cập nhật đúng.
- Dependency version hoặc metadata trong repository đã thay đổi.
- Task custom khai báo thiếu input hoặc output nên Gradle đánh giá trạng thái up-to-date sai.
- Build cache trả về output của task không phù hợp do task khai báo input sai.
- Configuration cache không thể tái sử dụng sau thay đổi build logic hoặc plugin.
- Gradle daemon đang ở trạng thái lỗi hoặc giữ tài nguyên.
- Gradle Wrapper distribution hoặc artifact transform bị hỏng.
- Repository, credential, proxy, certificate hoặc mạng đang có vấn đề.

Xóa mọi cache cùng lúc làm cho kết quả khó diễn giải. Nếu build thành công sau khi xóa toàn bộ, ta vẫn chưa biết lớp dữ liệu nào thực sự gây lỗi. Nếu build tiếp tục thất bại, ta có thể đã mất thông tin cần thiết để chẩn đoán.

Một giả thuyết tốt có thể kiểm chứng được, ví dụ:

- “Dependency metadata trong cache có thể cũ; thử refresh dependency rồi xem version và repository được phân giải.”
- “Output của project app có thể còn sót; clean riêng app rồi build lại.”
- “Task compileJava có thể đang lấy output từ build cache; chạy lại task với cache bị tắt để so sánh.”
- “Configuration cache có thể liên quan đến lỗi cấu hình; chạy một lần với configuration cache bị tắt.”
- “Daemon có thể giữ trạng thái JVM bất thường; dừng daemon rồi chạy lại cùng lệnh.”

## 2. Phân biệt các lớp cache và output của Gradle

Không có một thư mục cache duy nhất cho tất cả hoạt động của Gradle. Những lớp chính cần phân biệt:

| Lớp dữ liệu | Nội dung | Vị trí thường gặp | Khi nào nghi ngờ |
|---|---|---|---|
| Project build output | Class đã biên dịch, resource đã xử lý, report, JAR và output task | Thư mục build/ trong từng project | Output cũ, file sinh ra còn sót, cần xác minh clean build |
| Project-local Gradle state | Trạng thái nội bộ của build trong workspace | Thư mục .gradle/ ở root project | Cần điều tra trạng thái cục bộ của build hoặc configuration cache |
| Dependency cache | Metadata module, thông tin repository và artifact đã tải | Gradle User Home, thường dưới caches/modules-2/ | Dependency metadata lỗi thời, artifact cache có vấn đề |
| Build cache | Output của task cacheable | Local Gradle User Home hoặc remote cache | Nghi output task được khôi phục không đúng |
| Configuration cache | Kết quả cấu hình build để tái sử dụng | Thường trong .gradle/configuration-cache/ của build | Lỗi liên quan configuration cache hoặc build logic |
| Wrapper distribution cache | Bản Gradle distribution được Wrapper tải về | Gradle User Home, thường dưới wrapper/dists/ | Distribution tải thiếu hoặc giải nén lỗi |
| Artifact transform cache | Kết quả biến đổi artifact, ví dụ instrument hoặc transform dependency | Gradle User Home cache | Lỗi lặp lại khi transform một artifact |
| Daemon process và log | Tiến trình JVM chạy nền và log của nó | Tiến trình đang chạy; log trong Gradle User Home/daemon/ | Daemon crash, lỗi giao tiếp hoặc trạng thái tiến trình |

**Gradle User Home** mặc định thường là thư mục .gradle trong home directory của người dùng. Có thể thay đổi bằng biến môi trường GRADLE_USER_HOME hoặc tùy chọn tương ứng. Vì vậy, không nên đoán vị trí cache chỉ từ một đường dẫn mặc định; kiểm tra cấu hình môi trường của máy đang chạy build.

## 3. Quy trình trước khi thực hiện thao tác làm mới

Trước khi chạy clean hoặc xóa cache, hãy lưu lại thông tin có thể giúp tái hiện lỗi:

1. Lệnh Gradle đầy đủ và thư mục làm việc.
2. Mã thoát của tiến trình.
3. Gradle Wrapper version và JDK đang dùng.
4. Task path hoặc giai đoạn build bị lỗi.
5. Phần What went wrong và exception chain liên quan.
6. Dependency, configuration hoặc task input có liên quan.
7. Build có chạy offline, dùng remote cache, proxy hoặc repository riêng hay không.
8. Lỗi có tái hiện được trên một workspace sạch hoặc máy khác không.

Bắt đầu bằng log có mức chi tiết vừa đủ:

~~~bash
./gradlew build --stacktrace --info --console=plain
~~~

Nếu lỗi chỉ xuất hiện ở một task, chạy đúng task đó để giảm log:

~~~bash
./gradlew :app:compileJava --stacktrace --info --console=plain
~~~

Nếu cần xem task nào được chọn mà không thực thi action:

~~~bash
./gradlew :app:build --dry-run --console=plain
~~~

Không chạy clean trước khi lưu log nếu cần so sánh trạng thái trước và sau. Khi task tạo file sinh ra hoặc report phục vụ điều tra, clean có thể xóa chính dữ liệu đó.

## 4. Chọn thao tác theo loại giả thuyết

Bảng sau giúp chọn công cụ đúng phạm vi:

| Giả thuyết | Thao tác đầu tiên nên thử | Dữ liệu bị tác động |
|---|---|---|
| Output trong project cũ hoặc không nhất quán | clean project hoặc task clean phù hợp | Project build output |
| Dependency metadata hoặc trạng thái phân giải cần kiểm tra lại | --refresh-dependencies | Dependency resolution state |
| Task output từ build cache có thể sai | --no-build-cache cùng task cụ thể | Tắt đọc/ghi build cache cho lần chạy |
| Task đang bị bỏ qua do up-to-date nhưng cần chạy lại để so sánh | --rerun-tasks cho phạm vi phù hợp | Buộc task được yêu cầu thực thi |
| Configuration cache có thể gây lỗi | --no-configuration-cache | Tắt tái sử dụng configuration cache cho lần chạy |
| Daemon có dấu hiệu bất thường | --stop rồi chạy lại | Dừng daemon process |
| Wrapper distribution có bằng chứng bị hỏng | Dừng Gradle, xử lý đúng distribution cache của version đó | Bản Gradle distribution đã tải |
| Task custom cho output sai sau thay đổi input | Kiểm tra khai báo input/output và logic task | Sửa nguyên nhân trong build logic |

Không có thao tác nào trong bảng là cách sửa chung cho mọi lỗi. Chọn đúng dòng theo bằng chứng đang có.

## 5. Clean: xóa output build của project

Task **clean** của Java plugin và các plugin liên quan thường xóa thư mục build của project. Đây là thao tác phù hợp khi nghi output cũ hoặc file sinh ra trong workspace không còn phản ánh source hiện tại.

Chạy clean cho toàn build rồi build lại:

~~~bash
./gradlew clean build
~~~

Chỉ clean một project cụ thể:

~~~bash
./gradlew :app:clean :app:build
~~~

Với multi-project build, có thể gọi task clean theo project path. Nếu cần clean tất cả subproject, dùng task selector phù hợp với cấu trúc build hoặc chỉ rõ project path cần làm sạch.

Clean thường xóa:

- Class đã biên dịch.
- Resource đã xử lý.
- JAR hoặc archive do project tạo.
- Test report và test result nằm trong build directory.
- Output của custom task được đặt trong build directory.

Clean không tự xóa:

- Dependency cache trong Gradle User Home.
- Local hoặc remote build cache.
- Gradle Wrapper distribution.
- Toàn bộ daemon log.
- Configuration cache nằm ngoài build directory.
- Source code hoặc file cấu hình project.

Điều này rất quan trọng: **clean build không đồng nghĩa xóa mọi cache của Gradle**. Nếu task output được lưu trong build cache, Gradle vẫn có thể khôi phục output sau clean.

### Khi clean có ích

Clean hợp lý khi:

- Một file generated cũ còn tồn tại dù source đã đổi.
- Output của task không được dọn đúng sau khi đổi cấu hình.
- Cần xác nhận build tạo lại artifact từ source hiện tại.
- Có dấu hiệu output trong build directory bị sửa thủ công hoặc bị công cụ ngoài Gradle can thiệp.

### Khi clean không giải quyết được nguyên nhân

Clean không sửa được:

- Dependency version được chọn sai.
- Repository không truy cập được.
- Credential hết hạn.
- Task custom khai báo thiếu input.
- Build cache remote chứa output sai do task không cache-safe.
- Plugin không tương thích với Gradle.
- Configuration cache hoặc daemon có vấn đề riêng.

Nếu clean tạm thời làm lỗi biến mất nhưng lỗi quay lại ở build kế tiếp, cần kiểm tra logic task và khai báo input/output thay vì lặp lại clean vô hạn.

## 6. --refresh-dependencies: làm mới trạng thái phân giải dependency

Khi nghi Gradle đang dùng metadata dependency cũ hoặc cần kiểm tra lại artifact trong repository, có thể chạy:

~~~bash
./gradlew build --refresh-dependencies
~~~

Tùy chọn này yêu cầu Gradle làm mới dependency resolution state. Gradle kiểm tra lại metadata và trạng thái artifact theo quy tắc cache, checksum và repository.

Không nên hiểu rằng tùy chọn này luôn tải lại toàn bộ JAR. Nếu artifact hiện tại vẫn hợp lệ theo metadata và checksum, Gradle có thể tiếp tục dùng artifact đã có. Mục tiêu là xác minh lại trạng thái dependency, không phải xóa sạch mọi dữ liệu đã tải.

### Khi nên dùng

- Một dynamic version như 1.+ hoặc latest.release có thể đã có phiên bản mới.
- Metadata của module trong repository đã được cập nhật.
- Repository vừa publish lại metadata hoặc sửa artifact.
- Build báo dependency không tìm thấy dù repository đã được cập nhật.
- Cần kiểm tra lại trạng thái dependency sau khi đổi repository hoặc version constraint.

### Khi không nên dùng

Không dùng refresh dependency để xử lý lỗi compile do thiếu import, lỗi test assertion hoặc output generated cũ. Những lỗi đó không được giải quyết bằng việc làm mới metadata dependency.

Nếu repository trả 401, 403, timeout hoặc certificate error, refresh sẽ vẫn gặp lỗi cho đến khi credential, quyền truy cập, proxy, certificate hoặc mạng được sửa.

### Kết hợp với dependencyInsight

Trước và sau khi refresh, có thể xem module nào được chọn:

~~~bash
./gradlew :app:dependencyInsight --dependency gson --configuration runtimeClasspath
~~~

Xem toàn bộ runtime dependency:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

So sánh kết quả giúp xác định version, đường dependency và lý do chọn version. Đừng chỉ nhìn việc build thành công để kết luận dependency đã được làm mới đúng.

## 7. --no-build-cache: kiểm chứng output lấy từ cache

Nếu nghi task đang nhận output không đúng từ build cache, hãy chạy task liên quan với build cache bị tắt:

~~~bash
./gradlew :app:compileJava --no-build-cache --rerun-tasks
~~~

Tùy chọn **--no-build-cache** tắt sử dụng build cache cho lần chạy đó. Kết hợp **--rerun-tasks** giúp yêu cầu task được thực thi lại thay vì dùng trạng thái up-to-date cục bộ.

Sau đó so sánh output và hành vi với lần chạy bình thường.

Nếu lần chạy không dùng cache tạo ra kết quả đúng, còn lần dùng cache tạo ra kết quả sai, hãy điều tra:

- Task có khai báo đủ input không?
- Có property nào ảnh hưởng output nhưng bị bỏ sót?
- Task có phụ thuộc thời gian, biến môi trường hoặc file ngoài project không?
- Task có ghi output không xác định hoặc có side effect không?
- Task implementation hoặc plugin có thay đổi mà cache key chưa phản ánh đúng không?

Không nên xóa toàn bộ build cache ngay. Tắt cache trong một lần chạy là phép thử ít tác động hơn. Nếu giả thuyết được xác nhận, sửa task hoặc cấu hình cacheability trước khi quyết định xóa entry hoặc làm mới cache.

## 8. --rerun-tasks: yêu cầu thực thi lại task

Tùy chọn:

~~~bash
./gradlew build --rerun-tasks
~~~

yêu cầu Gradle chạy lại task được chọn thay vì bỏ qua chúng vì trạng thái up-to-date. Đây là cách hữu ích để kiểm tra xem output hiện tại có được tạo lại đúng không.

Phân biệt:

- **clean** xóa output trong project theo task clean.
- **--rerun-tasks** yêu cầu task thực thi lại.
- **--no-build-cache** tắt sử dụng build cache trong lần chạy.
- **--refresh-dependencies** làm mới dependency resolution.

Nếu chỉ muốn kiểm tra một task:

~~~bash
./gradlew :app:processResources --rerun-tasks
~~~

Nếu muốn kiểm tra task và tránh lấy output từ build cache:

~~~bash
./gradlew :app:processResources --rerun-tasks --no-build-cache
~~~

Không nên dùng --rerun-tasks cho mọi build thường ngày. Nó làm mất lợi ích up-to-date checking và có thể khiến build lâu hơn đáng kể.

## 9. --no-configuration-cache: kiểm tra riêng configuration cache

Configuration cache lưu kết quả cấu hình build để Gradle có thể tái sử dụng ở lần chạy sau. Nếu nghi lỗi liên quan đến configuration cache, thử:

~~~bash
./gradlew build --no-configuration-cache
~~~

Nếu build thành công khi tắt configuration cache, hãy điều tra:

- Plugin hoặc build logic nào chưa tương thích.
- Task có truy cập Project hoặc Gradle model không đúng thời điểm không?
- Có callback hoặc closure giữ trạng thái không thể serialize không?
- Build script có đọc dữ liệu thay đổi ngoài các input được theo dõi không?
- Configuration cache report chỉ ra vấn đề ở plugin hoặc task nào?

Tắt cache là phép thử để khoanh vùng, không phải kết luận rằng cần xóa toàn bộ thư mục .gradle. Khi lỗi đã được xác định, ưu tiên sửa build logic hoặc nâng plugin tương thích.

Có thể bật lại và xem thông tin liên quan:

~~~bash
./gradlew build --configuration-cache --configuration-cache-problems=warn
~~~

Tùy phiên bản Gradle, mức hỗ trợ và cách hiển thị warning có thể khác. Khi cấu hình cache không được tái sử dụng, đọc thông báo Gradle và report thay vì chỉ xóa cache rồi thử lại.

## 10. --stop: xử lý daemon mà không xóa cache

Nếu có dấu hiệu daemon bị treo, lỗi giao tiếp, JVM state bất thường hoặc tiến trình nền chiếm tài nguyên, dừng daemon:

~~~bash
./gradlew --stop
~~~

Sau đó chạy lại đúng lệnh đã ghi nhận:

~~~bash
./gradlew build --stacktrace --info --console=plain
~~~

Dừng daemon không xóa dependency cache, build cache hoặc source. Lần chạy tiếp theo có thể tạo daemon mới theo cấu hình JVM của build.

Nếu cần so sánh một lần chạy không tái sử dụng daemon:

~~~bash
./gradlew build --no-daemon
~~~

Tùy cấu hình JVM, Gradle có thể vẫn tạo một single-use daemon để đáp ứng yêu cầu JVM của build. Vì vậy, --no-daemon không phải lệnh xóa trạng thái hoặc cache.

Không nên dừng daemon như phản xạ cho mọi lỗi dependency hoặc compile. Chỉ thử khi có bằng chứng lỗi liên quan đến tiến trình daemon hoặc cần loại trừ giả thuyết đó.

## 11. Xử lý Wrapper distribution cache có kiểm soát

Gradle Wrapper tải distribution được chỉ định trong gradle-wrapper.properties và lưu trong Gradle User Home, thường dưới wrapper/dists/.

Nếu log cho thấy lỗi giải nén distribution, file distribution bị thiếu hoặc bản tải không hoàn chỉnh, có thể cần tải lại đúng distribution version.

Trước khi xóa thủ công:

1. Xác nhận lỗi thực sự nằm ở Wrapper distribution, không phải build script.
2. Đọc distributionUrl và distributionSha256Sum nếu dự án có cấu hình checksum.
3. Dừng các build và daemon đang sử dụng distribution.
4. Xác định chính xác thư mục distribution tương ứng với URL/version bị lỗi.
5. Chỉ xử lý thư mục đó theo quy trình của nhóm.
6. Chạy lại Wrapper để nó tải và cài đặt distribution.
7. Xác nhận checksum nếu dự án đã khai báo.

Không xóa toàn bộ wrapper/dists nếu chỉ một version bị lỗi. Việc đó buộc các build khác tải lại distribution và có thể làm gián đoạn môi trường offline.

Nếu lỗi chỉ là không tải được distribution do proxy hoặc mạng, xóa thư mục cache sẽ không sửa được kết nối. Hãy sửa proxy, certificate hoặc network trước.

## 12. Xử lý dependency cache thủ công: chỉ khi có bằng chứng

Dependency cache nằm trong Gradle User Home và có thể chứa nhiều metadata/artifact được dùng chung bởi nhiều build. Xóa toàn bộ caches/modules-2 có thể khiến nhiều dự án phải phân giải và tải dependency lại.

Trước khi xóa thủ công, hãy ưu tiên:

~~~bash
./gradlew build --refresh-dependencies
~~~

Nếu vẫn có bằng chứng một artifact cụ thể bị hỏng, xác định module, version, repository và file liên quan từ log hoặc dependency report. Chỉ xử lý phạm vi nhỏ nhất theo quy trình vận hành của tổ chức.

Cần lưu ý:

- Không xóa cache khi một build đang sử dụng nó.
- Không đoán đường dẫn dựa trên một Gradle User Home mặc định nếu máy đã tùy chỉnh.
- Không xóa cache chung trên CI runner đang chạy job khác.
- Không xóa metadata hoặc artifact của các module không liên quan.
- Ghi lại file hoặc thư mục đã xử lý để có thể giải thích thay đổi.
- Nếu lỗi tái diễn, kiểm tra nguồn artifact và repository thay vì tiếp tục xóa.

Với artifact lấy từ repository nội bộ, cần xác minh checksum, nội dung publish và quyền truy cập. Một JAR được publish sai sẽ tiếp tục sai sau khi tải lại.

## 13. Artifact transform cache và lỗi transform

Gradle có thể biến đổi artifact trước khi đưa vào classpath hoặc task, ví dụ instrument, unpack hoặc chuyển đổi định dạng. Kết quả transform có thể được cache trong Gradle User Home.

Nếu lỗi xuất hiện trong transform, đọc log để xác định:

- Artifact đầu vào và tọa độ module.
- Transform action hoặc plugin thực hiện biến đổi.
- JDK và Gradle version.
- Đường dẫn output transform.
- Lỗi có lặp lại với cùng artifact trên máy khác không.

Thử làm mới dependency hoặc chạy lại task có thể giúp phân biệt lỗi artifact đầu vào với lỗi transform. Không nên xóa toàn bộ Gradle User Home vì một transform lỗi của một module.

Nếu transform do plugin thực hiện, kiểm tra phiên bản plugin và compatibility với Gradle/JDK. Nếu artifact đầu vào hỏng, kiểm tra checksum hoặc tải artifact từ repository đáng tin cậy.

## 14. Offline mode không phải là refresh

Tùy chọn:

~~~bash
./gradlew build --offline
~~~

yêu cầu Gradle không truy cập mạng để phân giải dependency. Gradle chỉ có thể dùng metadata và artifact đã có sẵn trong cache phù hợp.

Offline mode hữu ích khi:

- Mạng tạm thời không có nhưng dependency đã được tải.
- Cần xác nhận build có thể chạy với tập dependency cache hiện có.
- Muốn phát hiện dependency nào chưa có trong cache.

Nếu dependency mới chưa được tải hoặc metadata cần làm mới, offline build có thể thất bại. Không kết hợp offline với mục tiêu làm mới dependency qua repository vì hai mục tiêu trái nhau.

Một phép thử hữu ích:

1. Chạy build online với --refresh-dependencies nếu nghi metadata.
2. Xác nhận dependency được phân giải.
3. Chạy offline để xem build có phụ thuộc vào truy cập mạng trong quá trình đó không.

Offline mode không xóa cache và cũng không chứng minh artifact cache là mới nhất.

## 15. Kết hợp thao tác nhưng giữ được khả năng xác định nguyên nhân

Có thể kết hợp một số tùy chọn khi giả thuyết cần kiểm tra nhiều lớp, nhưng nên thay đổi ít biến nhất có thể.

Ví dụ kiểm tra output task và build cache:

~~~bash
./gradlew :app:jar --rerun-tasks --no-build-cache
~~~

Kiểm tra dependency resolution và build lại project:

~~~bash
./gradlew :app:clean :app:build --refresh-dependencies
~~~

Tuy nhiên, lệnh thứ hai đồng thời clean output và refresh dependency. Nếu mục tiêu là biết lớp nào gây lỗi, nên chạy hai phép thử riêng:

~~~bash
./gradlew :app:clean :app:build
~~~

Sau khi lưu kết quả, thử:

~~~bash
./gradlew :app:build --refresh-dependencies
~~~

Khi mỗi lần chỉ thay đổi một điều kiện, kết quả dễ diễn giải hơn. Chỉ kết hợp nhiều tùy chọn khi đã có lý do rõ ràng và muốn xác minh một kịch bản cụ thể.

## 16. Cẩn trọng khi xóa thư mục .gradle

Trong workspace, thư mục .gradle thường chứa trạng thái nội bộ của Gradle cho build đó. Gradle User Home cũng có thư mục .gradle mặc định, nhưng hai vị trí có phạm vi khác nhau.

- **Project-local .gradle/** thuộc workspace của một build.
- **Gradle User Home/.gradle/** là vùng dữ liệu của người dùng, có thể được nhiều project dùng chung.

Không nên nhầm hai nơi hoặc xóa một thư mục chỉ vì tên giống nhau.

Nếu nghi project-local configuration cache có vấn đề, thử --no-configuration-cache trước. Nếu cần xóa thủ công, xác định đúng project root và đúng thư mục con cache sau khi dừng build liên quan.

Không xóa project-local .gradle một cách tùy tiện nếu nhóm dùng nó để giữ trạng thái cần thiết cho điều tra hoặc nếu build đang chạy. Cũng không xóa Gradle User Home/.gradle để sửa một lỗi chỉ xuất hiện ở một task của một project.

## 17. Ví dụ chẩn đoán theo giả thuyết

### Tình huống A: File generated cũ vẫn xuất hiện trong JAR

Giả thuyết: output cũ trong project chưa được dọn hoặc task generate không cập nhật file đã xóa.

Bước thử:

~~~bash
./gradlew :app:clean :app:jar
~~~

Nếu artifact sau clean đúng nhưng build tăng dần tiếp theo lại chứa file cũ, vấn đề có thể nằm ở task custom: task không xử lý input bị xóa hoặc output không được khai báo đúng. Cần sửa task thay vì phụ thuộc vào clean mỗi lần.

### Tình huống B: Dependency version không đúng như mong đợi

Giả thuyết: dynamic version hoặc metadata trong repository đã thay đổi.

Xem đường dependency:

~~~bash
./gradlew :app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Sau đó yêu cầu làm mới:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath --refresh-dependencies
~~~

So sánh version được chọn và lý do. Nếu repository trả lỗi xác thực hoặc không có artifact, sửa repository/credential thay vì xóa cache.

### Tình huống C: Task được khôi phục output không đúng

Giả thuyết: build cache chứa output không phù hợp hoặc task không khai báo input đầy đủ.

Thử:

~~~bash
./gradlew :app:compileJava --rerun-tasks --no-build-cache
~~~

Nếu output đúng khi không dùng cache, kiểm tra annotation input/output, task implementation và dữ liệu môi trường ảnh hưởng kết quả. Sửa nguyên nhân trước khi bật cache lại.

### Tình huống D: Build lỗi khi tái sử dụng configuration cache

Giả thuyết: plugin hoặc build logic chưa tương thích với configuration cache.

Thử:

~~~bash
./gradlew build --no-configuration-cache --stacktrace
~~~

Nếu chạy được, xem configuration cache report và thông báo Gradle để xác định plugin/task liên quan. Tắt cache chỉ là bước khoanh vùng.

### Tình huống E: Gradle daemon không phản hồi

Giả thuyết: daemon process bị treo hoặc lỗi giao tiếp.

Thử:

~~~bash
./gradlew --stop
./gradlew build --stacktrace --info
~~~

Nếu lỗi vẫn xảy ra, kiểm tra daemon log, JDK, memory và worker process. Dừng daemon không đồng nghĩa xóa dependency cache.

## 18. Ma trận chọn thao tác theo dấu hiệu lỗi

| Dấu hiệu quan sát | Nên kiểm tra trước | Phép thử có kiểm soát |
|---|---|---|
| Class hoặc resource cũ còn trong output | Task output và project build directory | clean project/task liên quan rồi build lại |
| Version dependency không đúng | Dependency graph, constraints, repository metadata | dependencyInsight rồi --refresh-dependencies |
| Artifact download lỗi checksum hoặc metadata bất thường | Repository, artifact và dependency cache | Refresh; xác minh artifact/checksum; chỉ xử lý cache module cụ thể nếu cần |
| Task có vẻ dùng output cache sai | Input/output và cacheability của task | --rerun-tasks --no-build-cache |
| Build lỗi chỉ khi dùng configuration cache | Plugin và configuration cache report | --no-configuration-cache |
| Daemon crash hoặc không phản hồi | Daemon log, JDK, JVM arguments | --stop rồi chạy lại |
| Wrapper không khởi động hoặc distribution hỏng | gradle-wrapper.properties và distribution cache đúng version | Dừng build, xử lý distribution cụ thể và tải lại |
| Dependency chưa có khi offline | Dependency cache và repository | Chạy online để tải/phân giải rồi thử offline |
| Task custom không cập nhật output khi file bị xóa | InputChanges và output mapping | Sửa logic REMOVED; clean chỉ dùng để xác nhận tạm thời |

## 19. Những thao tác nên tránh

- Xóa toàn bộ Gradle User Home để xử lý một lỗi nhỏ của một project.
- Xóa caches/modules-2 khi chưa xác định dependency hoặc chưa thử refresh.
- Chạy clean lặp đi lặp lại thay vì sửa task khai báo thiếu input/output.
- Dùng --refresh-dependencies để chữa lỗi compiler hoặc assertion.
- Dùng --rerun-tasks cho mọi build phát triển thường ngày.
- Xóa build cache remote khi chưa xác định phạm vi ảnh hưởng đến các team hoặc CI khác.
- Xóa configuration cache trong lúc build đang sử dụng nó.
- Xóa Wrapper distributions khi lỗi thực chất là proxy hoặc certificate.
- Chạy nhiều thao tác làm mới cùng lúc rồi kết luận không biết thay đổi nào đã sửa lỗi.
- Xóa log hoặc report trước khi lưu lại bằng chứng cần thiết.

Xóa cache rộng có thể khiến build sau chậm hơn, làm các job CI tải lại dependency, và gây khó khăn cho những build đang dùng chung Gradle User Home. Nếu dùng remote cache, thay đổi cache còn có thể ảnh hưởng nhiều máy khác.

## 20. Quy trình làm mới cache hoặc clean có kiểm soát

Một quy trình thực tế:

**Bước 1: Tái hiện lỗi**

Chạy lại lệnh gốc với cùng JDK, Gradle Wrapper, working directory và môi trường. Lưu mã thoát cùng log.

**Bước 2: Phân loại giai đoạn lỗi**

Xác định lỗi xảy ra ở wrapper startup, settings/plugin resolution, dependency resolution, task execution, test hay runtime.

**Bước 3: Viết giả thuyết**

Ghi rõ lớp dữ liệu nghi ngờ và bằng chứng. Ví dụ: “Task processResources giữ output cũ vì file nguồn đã bị xóa.”

**Bước 4: Chọn phép thử nhỏ nhất**

Chọn clean, refresh dependencies, rerun tasks, tắt build cache, tắt configuration cache hoặc dừng daemon theo giả thuyết.

**Bước 5: Thay đổi một yếu tố**

Tránh kết hợp clean, refresh, xóa cache và thay dependency cùng lúc nếu chưa cần. Giữ log trước và sau.

**Bước 6: So sánh kết quả**

Kiểm tra mã thoát, task outcome, version dependency, nội dung output và exception mới. Xác định giả thuyết được hỗ trợ hay bị bác bỏ.

**Bước 7: Sửa nguyên nhân gốc**

Ví dụ: khai báo input còn thiếu, sửa repository credential, cập nhật plugin, sửa task incremental hoặc điều chỉnh dependency constraint.

**Bước 8: Chạy lại build bình thường**

Sau khi sửa, chạy lệnh build thông thường để xác nhận cơ chế tăng dần hoạt động. Sau đó chạy clean build khi cần xác nhận khả năng tạo artifact từ trạng thái sạch.

**Bước 9: Xác minh trên CI**

Dùng môi trường và lệnh tương đương pipeline. Nếu có remote cache, kiểm tra cả trường hợp cache bật và phép thử không dùng cache khi phù hợp.

**Bước 10: Ghi lại thao tác đã thực hiện**

Ghi lệnh, thư mục hoặc cache cụ thể đã xử lý, kết quả trước/sau và lý do. Điều này giúp lần sau không phải lặp lại thao tác rộng không cần thiết.

## 21. Những nguyên tắc cần nhớ

- Xác định giả thuyết và lưu log trước khi clean hoặc làm mới cache.
- **clean** xóa output build của project; nó không xóa toàn bộ Gradle User Home.
- **--refresh-dependencies** làm mới dependency resolution state; không bảo đảm tải lại mọi artifact.
- **--no-build-cache** tắt sử dụng build cache cho lần chạy; dùng để kiểm tra output task có liên quan cache hay không.
- **--rerun-tasks** yêu cầu thực thi lại task; không thay thế việc khai báo input/output đúng.
- **--no-configuration-cache** giúp kiểm tra lỗi liên quan configuration cache.
- **--stop** dừng daemon, không xóa dependency hoặc build cache.
- Dependency cache, build cache, configuration cache, Wrapper distribution cache và project build output là các lớp khác nhau.
- Nếu task custom tạo output sai, sửa logic task và input/output thay vì lặp lại clean.
- Nếu dependency lỗi, xác định repository, credential, version và metadata trước khi xóa cache.
- Chỉ xóa thủ công vùng cache nhỏ nhất đã được xác định; dừng build liên quan và tránh ảnh hưởng Gradle User Home dùng chung.
- Kiểm tra lại build tăng dần, clean build và CI sau khi xử lý.

Làm mới cache và clean là công cụ chẩn đoán có phạm vi khác nhau. Khi xác định đúng lớp dữ liệu và dùng một phép thử có kiểm soát, ta có thể xác nhận giả thuyết mà không làm mất dữ liệu cần điều tra hoặc gây tải lại không cần thiết. Sau cùng, mục tiêu là sửa nguyên nhân gốc để build ổn định trong cả lần chạy tăng dần lẫn lần build từ trạng thái sạch.

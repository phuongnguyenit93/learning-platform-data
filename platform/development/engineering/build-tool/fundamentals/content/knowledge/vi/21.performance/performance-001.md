# Đo thời gian build và xác định nút thắt trước khi tối ưu

Build chậm làm giảm tốc độ phản hồi của lập trình viên, kéo dài thời gian CI và khiến nhóm khó phát hành thường xuyên. Tuy nhiên, cảm giác “build chậm” chưa đủ để xác định cần sửa điều gì. Một build có thể tốn thời gian ở giai đoạn khởi tạo, cấu hình project, tải dependency, biên dịch, sinh mã, chạy test, đóng gói hoặc chờ tài nguyên hệ thống. Mỗi nguyên nhân cần cách đo và cách xử lý khác nhau.

Muốn cải thiện hiệu năng build, trước hết cần có **baseline (mốc đo ban đầu)**, dùng cùng điều kiện để đo lại, và xác định công việc nào đang chi phối tổng thời gian. Sau đó mới thử một thay đổi có giả thuyết rõ ràng và so sánh kết quả. Quy trình này tránh việc tối ưu một task không ảnh hưởng đáng kể đến thời gian người dùng phải chờ.

## 1. Hiểu đúng thời gian build cần đo

Một lệnh build thường bao gồm nhiều giai đoạn. Có thể mô hình hóa đơn giản:

```text
Khởi động tiến trình build
          |
          v
Đọc Settings / POM và cấu hình project
          |
          v
Phân giải plugin và dependency
          |
          v
Tạo task graph / lập kế hoạch lifecycle
          |
          v
Thực thi task hoặc plugin goal
          |
          v
Kiểm tra, đóng gói và ghi kết quả
```

Đây là mô hình khái quát. Một số công việc có thể diễn ra xen kẽ hoặc song song; dependency resolution có thể xảy ra trong lúc cấu hình hoặc khi task cần dependency; Gradle và Maven cũng tổ chức lifecycle khác nhau.

Trước khi đo, hãy xác định câu hỏi cần trả lời:

- **Thời gian từ lúc chạy lệnh đến lúc có kết quả:** người dùng hoặc CI phải chờ bao lâu?
- **Thời gian cấu hình:** build tool mất bao lâu để đọc build script/POM và chuẩn bị task?
- **Thời gian thực thi task:** task nào tiêu tốn thời gian nhiều nhất?
- **Thời gian trên critical path:** những công việc nào quyết định thời điểm build có thể kết thúc?
- **Thời gian chờ bên ngoài:** tải dependency, truy cập repository, database, container hoặc dịch vụ từ xa?
- **Tài nguyên sử dụng:** CPU, bộ nhớ, đĩa, mạng hoặc garbage collection có đang giới hạn build không?

Một build có thể có tổng thời gian CPU của các task lớn hơn thời gian thực tế vì một số task chạy song song. Vì vậy, cộng thời gian từng task không phải lúc nào cũng bằng thời gian người dùng chờ.

## 2. Xây dựng baseline có thể so sánh

Baseline là kết quả đo ban đầu được ghi lại cùng điều kiện. Nếu không có baseline, sau một thay đổi ta không biết build nhanh hơn thật hay chỉ khác môi trường.

### 2.1. Cố định đầu vào

Khi so sánh hai lần build, hãy cố gắng giữ ổn định:

- Git commit và trạng thái working tree.
- Gradle Wrapper hoặc Maven Wrapper version.
- JDK chạy build và Java toolchain/compiler.
- Version plugin và dependency đã phân giải.
- Build command, task, profile và project properties.
- Hệ điều hành, CPU, RAM, ổ đĩa và giới hạn container/CI.
- Trạng thái cache, daemon và dependency đã tải.
- Mức tải nền của máy và các build khác đang chạy.

Nếu một trong các yếu tố này thay đổi, hãy ghi lại. Ví dụ, so sánh build từ hai commit khác nhau có thể hợp lý khi đánh giá một thay đổi code, nhưng không còn là phép đo cô lập cho một tối ưu cấu hình.

### 2.2. Đo nhiều lần

Không nên kết luận từ một lần chạy. Kết quả có thể bị ảnh hưởng bởi tải CPU, hoạt động antivirus, cập nhật hệ thống, mạng hoặc quá trình JIT warm-up.

Một cách thực hành đơn giản:

1. Chọn đúng lệnh build cần đo.
2. Chạy một lần để khởi tạo daemon, tải dependency hoặc làm nóng cache nếu kịch bản là warm build.
3. Chạy thêm vài lần với cùng điều kiện.
4. Ghi thời gian từng lần và dùng median (trung vị) làm con số đại diện.
5. Ghi cả mức dao động, không chỉ một con số trung bình.

Ví dụ:

| Lần chạy | Thời gian |
|---|---:|
| 1 | 42.1 giây |
| 2 | 31.4 giây |
| 3 | 30.8 giây |
| 4 | 31.2 giây |
| 5 | 30.9 giây |

Lần đầu lâu hơn có thể do tải dependency, khởi động daemon hoặc cache chưa nóng. Nếu mục tiêu là đánh giá trải nghiệm phát triển hằng ngày, các lần warm run thường quan trọng. Nếu mục tiêu là đánh giá một CI runner mới, cold build cũng có ý nghĩa riêng. Không trộn hai loại kết quả trong cùng một phép so sánh.

### 2.3. Phân biệt cold build và warm build

**Cold build** thường chỉ một lần build khi một hoặc nhiều cache chưa được làm nóng, daemon chưa sẵn sàng hoặc dependency chưa có trên máy. **Warm build** là build sau khi môi trường đã có trạng thái cache/daemon phù hợp.

Các khái niệm cần phân biệt:

- Gradle daemon: tiến trình nền giữ JVM và trạng thái để các lần build tiếp theo giảm chi phí khởi động.
- Configuration cache: lưu kết quả cấu hình build để có thể tái sử dụng ở lần chạy phù hợp.
- Build cache: lưu output của task có thể cache để khôi phục thay vì thực thi lại.
- Up-to-date checking: bỏ qua task khi input không thay đổi và output còn hợp lệ.
- Dependency cache: lưu artifact và metadata đã tải từ repository.

Một lần chạy warm có thể hưởng lợi từ nhiều cơ chế khác nhau. Khi đo, hãy ghi rõ cơ chế nào được bật và cache đang ở trạng thái nào.

Không nên xóa toàn bộ cache người dùng một cách tùy tiện chỉ để tạo cold build. Nếu cần đo cold build, hãy dùng môi trường hoặc thư mục cache riêng được kiểm soát và ghi rõ điều kiện. Xóa cache có thể làm tăng tải mạng, ảnh hưởng các project khác và tạo ra một kịch bản không giống CI thực tế.

## 3. Đo thời gian tổng thể từ command line

### 3.1. Linux và macOS

Shell có lệnh `time` để đo thời gian thực thi của một command:

```bash
time ./gradlew build
time ./mvnw verify
```

Thông thường output phân biệt thời gian thực (wall-clock/real), thời gian CPU ở user mode và thời gian CPU ở system mode. Wall-clock là chỉ số gần với thời gian người dùng phải chờ.

### 3.2. Windows PowerShell

PowerShell có `Measure-Command`:

```powershell
Measure-Command { .\gradlew.bat build }
Measure-Command { .\mvnw.cmd verify }
```

Kết quả có thuộc tính `TotalSeconds`, `TotalMilliseconds` và các thành phần thời gian khác. Dùng cùng shell, cùng command và cùng điều kiện khi so sánh.

### 3.3. Ghi nhận thời gian CI

CI có thể hiển thị thời gian job, step hoặc stage. Cần phân biệt:

- Thời gian chờ runner được cấp (queue time).
- Thời gian checkout source và tải cache.
- Thời gian chạy build tool.
- Thời gian upload artifact và báo cáo.
- Thời gian chờ dịch vụ hoặc bước thủ công.

Nếu job mất 12 phút nhưng Gradle chỉ chạy 5 phút, tối ưu task Gradle không thể giải quyết toàn bộ 7 phút còn lại. Cần đo theo từng step để tìm đúng phạm vi.

## 4. Đo và phân tích build Gradle

Gradle cung cấp nhiều mức quan sát khác nhau. Nên bắt đầu bằng công cụ có mức chi tiết phù hợp, rồi đi sâu khi đã có giả thuyết.

### 4.1. Xem phiên bản và môi trường build

```bash
./gradlew --version
```

Lệnh này hiển thị phiên bản Gradle, JVM đang chạy Gradle và thông tin môi trường liên quan. Đây là dữ liệu cơ bản cần lưu khi so sánh hai máy.

`./gradlew --version` không nhất thiết cho biết mọi Java toolchain mà các task sẽ sử dụng. Nếu build dùng `java.toolchain`, hãy ghi lại cấu hình toolchain và thông tin compiler thực tế.

### 4.2. Dùng Gradle build profile

Có thể chạy:

```bash
./gradlew build --profile
```

Gradle tạo báo cáo profile HTML trong thư mục `build/reports/profile/` của build. Báo cáo cung cấp thông tin về thời gian cấu hình, task và một số hoạt động build để giúp xác định vùng tốn thời gian.

Profile hữu ích cho bước chẩn đoán ban đầu vì nó cho thấy build đang tiêu tốn thời gian ở khu vực nào. Nó không thay thế profiler CPU hoặc phân tích sâu một task tùy chỉnh. Khi so sánh, giữ cùng command và điều kiện; việc bật công cụ đo có thể tạo thêm một ít overhead.

### 4.3. Dùng Build Scan/Develocity khi tổ chức đã cấu hình

Nếu dự án đã tích hợp Gradle Build Scan hoặc Develocity, có thể dùng:

```bash
./gradlew build --scan
```

Build Scan có thể cung cấp timeline của build, task execution, dependency resolution, cache hit/miss, cấu hình và môi trường. Timeline giúp nhìn được task nào chạy tuần tự, task nào chạy song song và phần nào nằm trên critical path.

Việc tạo scan phụ thuộc plugin/cấu hình và chính sách của tổ chức. Build Scan có thể thu thập thông tin build và môi trường, vì vậy hãy tuân theo quy định dữ liệu nội bộ trước khi chia sẻ scan ra ngoài tổ chức.

### 4.4. Dùng log `--info`

```bash
./gradlew build --info
```

`--info` cung cấp thêm thông tin về task, cache, dependency và các quyết định thực thi. Nó hữu ích khi profile cho thấy một task đáng chú ý nhưng chưa rõ vì sao task chạy hoặc bị bỏ qua.

`--debug` tạo lượng log lớn hơn nhiều:

```bash
./gradlew build --debug
```

Chỉ dùng khi cần điều tra sâu. Debug log có thể chứa thông tin về đường dẫn, repository, môi trường hoặc cấu hình nhạy cảm; hãy kiểm tra log trước khi chia sẻ.

### 4.5. Xem task graph bằng dry-run

```bash
./gradlew build --dry-run
```

`--dry-run` cho biết các task nào sẽ được đưa vào task graph và thứ tự dự kiến, nhưng không thực thi task như một build thực tế. Đây là công cụ để hiểu phạm vi công việc, không phải công cụ đo thời gian.

Nếu build graph có hàng trăm task nhưng chỉ một số task được chạy thực tế do up-to-date hoặc cache, hãy đọc trạng thái task trong lần build thật để hiểu phần nào đã được thực hiện.

## 5. Đọc kết quả Gradle đúng cách

### 5.1. Phân biệt configuration time và task execution time

Một build có thể chậm trước khi task đầu tiên bắt đầu. Ví dụ:

- Nhiều build script và plugin cần được cấu hình.
- Plugin thực hiện truy cập filesystem hoặc đọc metadata trong configuration phase.
- Logic trong `allprojects`, `subprojects` hoặc `afterEvaluate` tạo nhiều công việc cấu hình.
- Configuration cache không được dùng hoặc không có cache hit.

Nếu task execution ngắn nhưng tổng thời gian dài, tối ưu compiler hoặc test có thể không giúp nhiều. Hãy xem phần configuration trong profile/scan và đánh giá khả năng sử dụng configuration cache, cấu hình lazy hoặc giảm logic chạy trong configuration phase.

### 5.2. Task duration không đồng nghĩa với critical path

Giả sử task A mất 40 giây, task B mất 35 giây và chúng chạy song song. Tổng thời gian người dùng chờ có thể gần 40 giây cộng phần overhead, chứ không phải 75 giây. Ngược lại, một chuỗi task phụ thuộc nhau, mỗi task mất 10 giây, có thể tạo critical path dài 50 giây.

Vì vậy, hãy xem timeline và quan hệ phụ thuộc, không chỉ sắp xếp task theo duration. Ưu tiên công việc đang giữ build không thể kết thúc hoặc làm các worker khác phải chờ.

### 5.3. Hiểu trạng thái task

Một số trạng thái thường thấy trong output Gradle:

- `SUCCESS`: task đã thực thi.
- `UP-TO-DATE`: input không thay đổi và output còn hợp lệ, nên task được bỏ qua.
- `FROM-CACHE`: output được khôi phục từ build cache.
- `NO-SOURCE`: không có source phù hợp để xử lý.
- `SKIPPED`: task bị bỏ qua theo điều kiện hoặc cấu hình.
- `FAILED`: task thất bại.

Nếu một task `UP-TO-DATE`, thời gian thực thi trước đó không phải thời gian nó tiêu tốn trong lần chạy hiện tại. Nếu task `FROM-CACHE`, build vẫn tốn thời gian để kiểm tra cache và khôi phục output, nhưng thường ít hơn việc chạy lại task.

### 5.4. Tổng thời gian task có thể lớn hơn wall-clock

Khi Gradle chạy task song song, thời gian của các task có thể chồng lấn. Báo cáo cộng duration của task có thể lớn hơn tổng thời gian build. Để hiểu người dùng phải chờ bao lâu, hãy dùng wall-clock và timeline critical path.

## 6. Đo build Maven

Maven có mô hình lifecycle/phase và plugin goal. Mặc định, output của Maven thường hiển thị thời gian tổng cho từng project trong reactor và tổng thời gian build ở cuối.

### 6.1. Ghi lại phiên bản và command

```bash
./mvnw --version
```

Lệnh này cho biết Maven version và Java runtime Maven đang dùng. Khi so sánh, ghi lại Maven Wrapper, JDK, profile, properties và các tham số CLI.

### 6.2. Đọc tổng thời gian và reactor summary

Chạy:

```bash
./mvnw verify
```

Maven thường in `Reactor Summary` và `Total time`. Với build nhiều mô-đun, summary giúp xác định project nào có kết quả khác hoặc có thể liên quan đến thời gian đáng chú ý. Tổng thời gian ở cuối gần với thời gian Maven ghi nhận cho phiên build; nên dùng `time` hoặc `Measure-Command` nếu cần đo wall-clock từ bên ngoài.

### 6.3. Bật log chi tiết

```bash
./mvnw -X verify
```

`-X` bật debug output, cho biết nhiều chi tiết về plugin, goal, dependency và quá trình thực thi. Output rất dài, nên chỉ dùng khi cần xác định điều gì xảy ra bên trong một phase hoặc plugin.

Có thể thêm timestamp vào log của Maven SLF4J simple logger trong các môi trường dùng logger hỗ trợ những thuộc tính này:

```bash
./mvnw -Dorg.slf4j.simpleLogger.showDateTime=true \
       -Dorg.slf4j.simpleLogger.dateTimeFormat=HH:mm:ss.SSS \
       verify
```

Khả năng hiển thị timestamp phụ thuộc phiên bản Maven và logger provider đang được sử dụng. Nếu không có timestamp như mong muốn, hãy kiểm tra logger configuration của phiên bản Maven đó thay vì giả định mọi Maven installation có cùng output.

Timestamp giúp ước lượng khoảng thời gian giữa các thông báo, nhưng không thay thế profiler chuyên dụng. Plugin có thể ghi log không đều hoặc thực hiện công việc nền giữa hai dòng log.

### 6.4. Xác định project hoặc plugin goal đáng chú ý

Maven in các dòng dạng:

```text
--- maven-compiler-plugin:...:compile (...) @ order-domain ---
--- maven-surefire-plugin:...:test (...) @ order-domain ---
```

Các dòng này giúp xác định plugin goal đang chạy và project tương ứng. Kết hợp timestamp, debug log và báo cáo test để khoanh vùng. Nếu cần thời gian chính xác cho từng plugin goal, có thể dùng profiler/extension được tổ chức phê duyệt và tương thích với Maven version đang dùng; không cài một extension tùy tiện chỉ để đo vì nó có thể làm thay đổi chính môi trường cần đo.

### 6.5. Đo theo module trong reactor

Với build nhiều module, có thể chạy một project cùng các dependency cần thiết:

```bash
./mvnw -pl application -am verify
```

`-pl` chọn project; `-am` (also make) yêu cầu Maven build thêm các project trong reactor mà project được chọn phụ thuộc vào. Cách này giúp khoanh vùng một phần build, nhưng kết quả không thể thay thế phép đo toàn reactor nếu mục tiêu là thời gian của pipeline đầy đủ.

### 6.6. Chạy song song trong Maven

Maven hỗ trợ build song song cho reactor bằng `-T`:

```bash
./mvnw -T 1C verify
```

`1C` yêu cầu số thread dựa trên số lõi CPU theo cách Maven hỗ trợ. Tăng concurrency có thể giảm wall-clock khi các module độc lập và tài nguyên còn dư. Tuy nhiên, cần xem cảnh báo plugin không thread-safe, dependency giữa module, giới hạn CPU/RAM và tải của dịch vụ ngoài. Không nên bật song song như một tối ưu mặc định trước khi có baseline và xác nhận build an toàn.

## 7. Tách các loại build để đo đúng trải nghiệm

Một project có nhiều kiểu build khác nhau. Không nên chỉ đo một lệnh rồi suy ra mọi hoạt động đều nhanh hoặc chậm.

| Kịch bản | Câu hỏi cần trả lời | Ví dụ lệnh |
|---|---|---|
| Compile nhanh | Thay đổi một file Java mất bao lâu để biên dịch? | `./gradlew compileJava` |
| Test nhanh | Unit test cần chạy bao lâu? | `./gradlew test` |
| Incremental build | Sau một thay đổi nhỏ, task nào phải chạy lại? | `./gradlew build` sau thay đổi có kiểm soát |
| Full local build | Build sạch của project mất bao lâu? | `./gradlew clean build` |
| CI verification | Pipeline kiểm tra đầy đủ mất bao lâu? | `./gradlew build` hoặc `./mvnw verify` |
| Package/release | Tạo artifact và các bước phát hành mất bao lâu? | `./gradlew assemble`/task release hoặc Maven `package`/`verify` theo quy trình |
| Build một module | Module nào gây chậm và dependency của nó là gì? | `./gradlew :module:build`, `./mvnw -pl module -am verify` |

`clean build` đo một kịch bản khác với incremental build. Clean xóa output build của project, làm các task cần chạy lại; nó không nhất thiết xóa dependency cache hoặc mọi cache của build tool. Hãy ghi rõ đang đo clean build hay incremental build.

## 8. Tìm nút thắt theo nhóm nguyên nhân

Khi đã có profile hoặc log, hãy phân loại nguyên nhân trước khi thay đổi cấu hình.

### 8.1. Khởi động và cấu hình build

Dấu hiệu:

- Thời gian từ lúc chạy lệnh đến task đầu tiên dài.
- Nhiều project hoặc plugin được cấu hình dù chỉ chạy một task nhỏ.
- Root build script chứa nhiều logic động.
- Configuration cache không hit hoặc thường xuyên bị invalidated.

Hướng điều tra:

- Xem configuration time trong profile/scan.
- Kiểm tra plugin nào được áp dụng và logic cấu hình chạy ở đâu.
- Tìm các thao tác filesystem, process hoặc truy cập mạng trong configuration phase.
- Xem `allprojects`, `subprojects`, `afterEvaluate` và các callback cấu hình chéo project.
- Kiểm tra configuration cache compatibility và lý do cache không được dùng.

Hướng cải thiện có thể gồm cấu hình lazy, dùng `tasks.register`/`configureEach`, tránh làm việc nặng trong configuration phase, giảm plugin không cần thiết và sửa nguyên nhân khiến configuration cache bị vô hiệu hóa.

### 8.2. Dependency resolution và mạng

Dấu hiệu:

- Build lần đầu chậm hơn nhiều lần sau.
- Log cho thấy tải nhiều artifact hoặc metadata.
- CI thường xuyên truy cập repository từ xa.
- Một số dependency dùng version động hoặc metadata thay đổi liên tục.

Hướng điều tra:

- Kiểm tra dependency graph và số lượng artifact cần resolve.
- Xem repository nào được truy cập và thời gian tải.
- Xác nhận dependency cache được dùng đúng cách.
- Kiểm tra mirror/repository nội bộ và độ ổn định mạng.
- Dùng version cụ thể và dependency locking khi phù hợp.

Không nên chuyển mọi build sang offline chỉ để có thời gian đẹp hơn. Offline build có thể thất bại khi thiếu dependency trong cache và không đại diện cho môi trường CI cần tải dependency mới.

### 8.3. Biên dịch Java và annotation processing

Dấu hiệu:

- `compileJava` hoặc `compileTestJava` chiếm phần lớn thời gian.
- Thay đổi nhỏ khiến nhiều source set biên dịch lại.
- Annotation processor sinh nhiều file hoặc chạy lâu.

Hướng điều tra:

- Xác định source set và task compile nào chậm.
- Kiểm tra số lượng source file và compiler options.
- Kiểm tra annotation processor, code generator và task sinh mã.
- Xem incremental compilation có hoạt động không.
- Kiểm tra thay đổi dependency hoặc compiler option có làm mất khả năng incremental không.

Đừng vội tăng số worker nếu compiler đang bị giới hạn RAM hoặc đĩa. Song song hóa quá mức có thể làm garbage collection và I/O tăng, khiến build chậm hơn.

### 8.4. Unit test và integration test

Dấu hiệu:

- Task `test` chiếm phần lớn thời gian.
- Một vài test có thời gian dài hoặc chạy không ổn định.
- Test phụ thuộc database, container, HTTP service hoặc thời gian chờ.

Hướng điều tra:

- Xem test report và duration từng test/class.
- Tách unit test với integration test nếu chúng có yêu cầu runtime khác nhau.
- Tìm test có sleep, retry, timeout dài hoặc gọi mạng không cần thiết.
- Kiểm tra setup/teardown và chi phí khởi động fixture.
- Xác định test nào có thể chạy song song an toàn.

Không được bỏ test hoặc giảm assertion chỉ để làm build nhanh hơn mà không đánh giá rủi ro. Mục tiêu là giảm chi phí không cần thiết và giữ mức kiểm chứng phù hợp.

### 8.5. Task đóng gói, copy và xử lý resource

Dấu hiệu:

- `jar`, `war`, `processResources`, `copy`, archive hoặc task sinh tài liệu chiếm nhiều thời gian.
- Nhiều file lớn được copy hoặc nén lặp lại.
- Task tùy chỉnh chạy lại dù input không thay đổi.

Hướng điều tra:

- Xem task input/output và trạng thái up-to-date.
- Kiểm tra có xử lý lại toàn bộ thư mục khi chỉ một file thay đổi không.
- Kiểm tra filtering/transform có áp dụng cho file nhị phân không.
- Xác nhận task khai báo output và input đầy đủ để Gradle có thể bỏ qua hoặc cache.

### 8.6. CPU, bộ nhớ và đĩa

Dấu hiệu:

- CPU gần 100% trong phần lớn build.
- RAM chạm giới hạn, JVM thường xuyên garbage collection hoặc container bị OOM.
- Đĩa có latency cao hoặc nhiều file nhỏ được tạo/đọc.
- Tăng số worker làm thời gian tệ hơn.

Hướng điều tra:

- Quan sát CPU/RAM/đĩa trong lúc build.
- Kiểm tra heap size của Gradle/Maven và test worker.
- Xem log GC hoặc dùng Java Flight Recorder/profiler khi cần phân tích CPU/memory sâu.
- Kiểm tra giới hạn container và số CPU mà JVM nhận diện.
- Đo lại sau khi thay đổi concurrency hoặc heap một cách riêng biệt.

### 8.7. Dịch vụ ngoài và tác vụ mạng

Integration test, code generation hoặc task release có thể chờ dịch vụ ngoài. Nếu task chủ yếu chờ mạng, tăng CPU hoặc heap sẽ không giúp. Hãy đo thời gian gọi dịch vụ, retry, timeout và độ trễ repository/API.

## 9. Tìm đúng task có ảnh hưởng đến thời gian hoàn tất

Một task có duration lớn chưa chắc là nút thắt tổng thể. Cần xem nó có nằm trên critical path hoặc có giữ các task khác phải chờ không.

Ví dụ:

```text
compileDomain (12s) ----+
                       +--> package (8s) --> verify (4s)
compileApi (18s) -------+
```

Nếu `compileDomain` và `compileApi` chạy song song, đường dài nhất trước package là 18 giây. Giảm `compileDomain` từ 12 xuống 6 giây có thể không giảm đáng kể tổng thời gian nếu `compileApi` vẫn mất 18 giây. Giảm `compileApi` mới tác động trực tiếp hơn đến critical path.

Trong thực tế, task graph phức tạp hơn và có thể có nhiều nhánh, worker process và resource contention. Dùng timeline/profile để nhận diện công việc đang chặn kết thúc build.

Hãy ưu tiên theo ba yếu tố:

1. Task nằm trên critical path hoặc thường xuyên khiến các task khác chờ.
2. Task xuất hiện trong kịch bản mà nhóm chạy nhiều nhất (ví dụ incremental build mỗi lần sửa code).
3. Task có nguyên nhân có thể thay đổi mà không làm giảm độ tin cậy của build.

Một task chạy 2 phút nhưng chỉ thuộc release build hàng tuần có thể ít quan trọng hơn task 20 giây được chạy hàng chục lần mỗi ngày.

## 10. Gradle Profiler và benchmark có kiểm soát

Gradle Profiler là công cụ riêng dành cho việc benchmark build Gradle. Nó hỗ trợ chạy nhiều iteration và các scenario để đo các loại thay đổi khác nhau, chẳng hạn incremental build sau khi sửa một file, build với configuration cache hoặc build cache.

Nó phù hợp khi cần so sánh một thay đổi hiệu năng có độ chênh nhỏ và muốn giảm ảnh hưởng của việc đo thủ công. Hãy dùng phiên bản công cụ tương thích với Gradle, định nghĩa scenario rõ ràng và chạy trên cùng máy/runner hoặc các máy có cấu hình tương đương.

Một benchmark tốt cần xác định:

- Lệnh hoặc task được chạy.
- Trạng thái cache trước mỗi iteration.
- File nào được thay đổi giữa các lần chạy.
- Có dùng daemon hay không.
- Có dùng configuration cache/build cache hay không.
- Số lần warm-up và số iteration được đo.
- Chỉ số báo cáo, ví dụ median và phân phối thời gian.

Không nên lấy một lần chạy `clean build` để kết luận hiệu quả của configuration cache hoặc incremental compilation. Mỗi tính năng cần scenario phản ánh đúng cách nó được dùng.

## 11. Thiết kế phép đo cho các cơ chế cache Gradle

Các cache giải quyết những phần khác nhau. Muốn đánh giá chúng, hãy tạo phép đo tách biệt.

| Cơ chế | Phần được tối ưu | Kịch bản nên đo |
|---|---|---|
| Gradle daemon | Chi phí khởi động JVM/Gradle giữa các lần chạy | So sánh lần chạy đầu và các lần chạy tiếp theo trong cùng môi trường |
| Configuration cache | Tái sử dụng kết quả cấu hình build | Chạy cùng task nhiều lần, quan sát cache reuse và lý do invalidation |
| Build cache | Tái sử dụng output task từ local/remote cache | Chạy lại build hoặc build trên runner khác có cùng input/cache key |
| Up-to-date checking | Bỏ qua task khi input/output không đổi | Chạy lại build mà không sửa source |
| Incremental compilation | Chỉ xử lý phần source bị ảnh hưởng | Sửa một file Java và đo compile task |
| Dependency cache | Giảm tải artifact/metadata đã có | So sánh cold dependency resolution với warm resolution có kiểm soát |

Một build có thể vừa dùng up-to-date checking vừa dùng build cache. Khi task up-to-date, Gradle không cần lấy output từ cache. Khi task cần chạy nhưng cache có entry phù hợp, output có thể được khôi phục từ cache.

### 11.1. Kiểm tra configuration cache

Có thể chạy:

```bash
./gradlew build --configuration-cache
```

Lần đầu Gradle có thể phải cấu hình và lưu cache. Lần sau, nếu input và điều kiện phù hợp, Gradle có thể tái sử dụng configuration cache. Hãy xem thông báo cache được lưu/reused và nguyên nhân cache bị bỏ qua hoặc invalidated.

Nếu build script hoặc plugin chưa tương thích, cần sửa nguyên nhân thay vì cố ép dùng cache. Không nên đánh giá lợi ích chỉ từ lần đầu vì đó thường là lần tạo cache chứ chưa phải lần reuse.

### 11.2. Kiểm tra build cache

Build cache có thể được bật bằng cấu hình build hoặc command:

```bash
./gradlew build --build-cache
```

Để đo hiệu quả, cần so sánh task thực sự cacheable và có input/output ổn định. Nếu task không cacheable hoặc cache key khác nhau do input thay đổi, cache sẽ không giúp.

Không nên biến một task không xác định input/output thành cacheable chỉ để tăng cache hit. Task phải khai báo đầy đủ input, output và tránh phụ thuộc vào trạng thái ngoài không được mô hình hóa; nếu không, build có thể trả về output cũ sai.

### 11.3. Phân biệt `clean` và incremental

```bash
# Clean build
./gradlew clean build

# Incremental/warm build sau một thay đổi nhỏ hoặc không đổi source
./gradlew build
```

`clean` xóa output của project theo task clean. Nó không nhất thiết xóa daemon, dependency cache hoặc build cache. Vì vậy, `clean build` vẫn có thể hưởng lợi từ dependency cache hoặc build cache. Hãy ghi rõ cache nào được giữ khi gọi một phép đo là “cold”.

## 12. Một số cách đo Maven theo kịch bản

Maven không có cùng mô hình configuration cache và build cache như Gradle core. Tuy nhiên, vẫn có thể đo từng phase, plugin goal và module để xác định vùng tốn thời gian.

### 12.1. So sánh compile và test

```bash
# Chỉ đi đến biên dịch mã test
./mvnw test-compile

# Tiếp tục đến phase test
./mvnw test

# Đi qua toàn bộ lifecycle đến verify
./mvnw verify
```

Nếu `test-compile` nhanh nhưng `test` lâu, phần tốn thời gian nhiều khả năng nằm ở test execution hoặc runtime setup. Nếu `compile` đã chậm, hãy xem compiler, annotation processor và source/module cần biên dịch.

### 12.2. Tạm tách test execution khi chẩn đoán

Maven có các thuộc tính thường dùng:

```bash
# Bỏ qua thực thi test, nhưng vẫn biên dịch test source
./mvnw package -DskipTests

# Bỏ qua cả biên dịch và thực thi test
./mvnw package -Dmaven.test.skip=true
```

Hai lệnh này phục vụ chẩn đoán hoặc tình huống build được cho phép bỏ test. Chúng không tương đương về mặt kiểm chứng: `-DskipTests` vẫn có thể compile test; `maven.test.skip` bỏ cả bước compile test và thực thi. Không dùng kết quả build bỏ test làm bằng chứng rằng kiểm thử đã pass.

### 12.3. Kiểm tra plugin và dependency

Khi nghi ngờ plugin goal hoặc dependency resolution, dùng `-X` để xem chi tiết. Có thể dùng `dependency:tree` để xem graph:

```bash
./mvnw dependency:tree
```

Nếu một plugin hoặc dependency tải chậm, xem repository, mirror, metadata và network timing. Tránh thay version hoặc repository đồng thời với thay đổi compiler/test vì sẽ khó biết nguyên nhân cải thiện.

## 13. Dùng profiler khi log chưa đủ

Profile build cho biết vùng nào chậm, nhưng có lúc cần biết code nào bên trong task tiêu tốn CPU hoặc bộ nhớ. Khi đó có thể dùng Java Flight Recorder (JFR), Java Mission Control hoặc profiler được tổ chức phê duyệt.

JFR có thể thu thập:

- CPU execution samples.
- Garbage collection và allocation.
- Thread states và contention.
- I/O và một số sự kiện JVM.
- Hoạt động của tiến trình build hoặc test worker nếu ghi đúng tiến trình.

Ví dụ bật recording cho một tiến trình Java bằng JVM option phù hợp:

```text
-XX:StartFlightRecording=filename=build.jfr,settings=profile,dumponexit=true
```

Cần truyền option cho đúng JVM. Gradle daemon, worker process và test JVM có thể là các tiến trình khác nhau; gắn option vào JVM không chạy task cần đo sẽ không thu được dữ liệu mong muốn. Maven cũng chạy trong JVM riêng và có thể khởi chạy forked test process.

Không bắt đầu bằng profiler sâu nếu chưa biết task hoặc phase nào đáng chú ý. Profiling có overhead và tạo dữ liệu lớn; hãy dùng nó sau khi profile/log đã thu hẹp phạm vi.

## 14. Từ số đo đến giả thuyết nguyên nhân

Sau khi có số liệu, hãy viết giả thuyết có thể kiểm chứng. Ví dụ:

| Quan sát | Giả thuyết | Phép kiểm tra tiếp theo |
|---|---|---|
| Configuration chiếm phần lớn thời gian | Plugin hoặc logic root project cấu hình quá nhiều | Xem build scan/profile và kiểm tra configuration cache |
| `compileJava` chậm sau mỗi thay đổi | Incremental compilation không hoạt động hoặc annotation processor chạy lại | Xem compiler log, task input và processor |
| `test` chiếm nhiều thời gian | Một số test chậm hoặc setup dịch vụ ngoài tốn thời gian | Xem test report, phân loại unit/integration và đo test riêng |
| Build CI lần đầu chậm, lần sau nhanh | Dependency cache hoặc daemon chưa nóng | So sánh cold/warm và cache hit/miss |
| Nhiều task cùng chờ trước một task cuối | Task cuối hoặc dependency trên critical path đang chặn | Xem timeline và quan hệ task dependency |
| Tăng worker làm build chậm hơn | CPU/RAM/đĩa bị tranh chấp hoặc task không song song an toàn | Đo CPU, memory, GC và chạy thử với concurrency khác |
| Maven chỉ chậm ở một module | Plugin goal hoặc dependency riêng của module đó | Xem reactor summary, timestamp và dependency tree |

Giả thuyết tốt phải chỉ ra điều gì sẽ thay đổi nếu giả thuyết đúng. Ví dụ: “Nếu test database là nút thắt, chạy unit test riêng sẽ giảm đáng kể thời gian; báo cáo test sẽ cho thấy các test tích hợp có duration dài.” Điều này cụ thể hơn câu “có lẽ Gradle chậm”.

## 15. Thử tối ưu theo từng thay đổi

Khi đã xác định nút thắt, thực hiện một thay đổi nhỏ và đo lại.

1. Lưu baseline, command và điều kiện.
2. Nêu giả thuyết nguyên nhân.
3. Thay đổi một yếu tố chính, ví dụ bật configuration cache hoặc sửa một task không incremental.
4. Chạy đúng scenario trước đó với cùng điều kiện.
5. So sánh median, độ dao động, critical path và correctness.
6. Giữ thay đổi nếu lợi ích có ý nghĩa và không làm giảm độ tin cậy; nếu không, hoàn nguyên hoặc thử giả thuyết khác.

Ví dụ, nếu task `processResources` chạy lại mọi lần do input/output không được khai báo đúng, hãy sửa task để mô hình hóa input/output. Sau đó kiểm tra trạng thái `UP-TO-DATE` ở lần chạy tiếp theo và đo lại incremental build. Không chỉ đo `clean build`, vì lỗi nằm ở khả năng bỏ qua công việc khi input không đổi.

Nếu test là nút thắt, hãy xem test nào chậm và lý do. Tách integration test có thể giúp lập trình viên chạy unit test nhanh hơn, nhưng CI vẫn cần chạy integration test theo chính sách. Tách test không có nghĩa bỏ kiểm chứng.

## 16. Các chỉ số cần lưu trong báo cáo hiệu năng

Một báo cáo đơn giản nhưng hữu ích nên có:

| Trường | Nội dung |
|---|---|
| Mục tiêu đo | Incremental build, clean build, test, verify hoặc release |
| Source revision | Git commit và trạng thái working tree |
| Build command | Toàn bộ command, task/phase và property |
| Build tool | Gradle/Maven Wrapper version và plugin liên quan |
| JVM/toolchain | Vendor, version, heap, toolchain và compiler release |
| Cache state | Daemon, configuration cache, build cache, dependency cache |
| Môi trường | OS, CPU, RAM, container limit, disk và mạng |
| Wall-clock | Thời gian từ bắt đầu đến kết thúc |
| Task/phase nổi bật | Duration, trạng thái, vị trí trên critical path |
| Tài nguyên | CPU, memory, GC, disk/network khi cần |
| Kết quả | Test pass/fail, artifact được tạo, lỗi hoặc cảnh báo |
| Ghi chú | Khác biệt môi trường, cache warm-up, hoạt động nền |

Lưu profile, Build Scan link hoặc log đã được kiểm tra thông tin nhạy cảm. Báo cáo giúp nhóm so sánh theo thời gian và nhận biết khi một thay đổi build làm hiệu năng suy giảm.

## 17. Những sai lầm thường gặp khi đo build

- **Chỉ chạy một lần rồi kết luận.** Một lần chạy có thể bị ảnh hưởng bởi mạng, CPU hoặc cache.
- **So sánh cold build với warm build.** Hai kịch bản có điều kiện và mục tiêu khác nhau.
- **Không ghi lại JDK, Wrapper hoặc plugin version.** Môi trường khác có thể làm kết quả thay đổi.
- **Chỉ nhìn tổng thời gian.** Không biết configuration, dependency, compile hay test là nguyên nhân.
- **Chỉ nhìn task lâu nhất.** Task đó có thể chạy song song và không nằm trên critical path.
- **Cộng duration task để suy ra wall-clock.** Các task có thể chồng lấn.
- **Dùng `--dry-run` để đo.** Lệnh này không thực thi task nên không phản ánh thời gian build thật.
- **Dùng debug log cho mọi lần benchmark.** Log chi tiết có overhead và làm kết quả nhiễu.
- **Xóa cache toàn cục không có kế hoạch.** Việc này ảnh hưởng project khác và tạo kịch bản cold không đại diện.
- **Bật song song trước khi đo.** Concurrency có thể gây tranh chấp tài nguyên hoặc plugin không thread-safe.
- **Tắt test để báo build nhanh hơn.** Build nhanh hơn nhưng không còn cùng mức kiểm chứng.
- **Thay nhiều yếu tố cùng lúc.** Không thể xác định thay đổi nào tạo ra kết quả.
- **Tối ưu trước khi có giả thuyết.** Có thể tốn công vào một vùng không ảnh hưởng thời gian chờ thực tế.

## 18. Ví dụ thực hành: điều tra một Gradle build mất nhiều thời gian

Giả sử `./gradlew build` mất khoảng 4 phút trên máy phát triển. Nhóm thực hiện:

**Bước 1: tạo baseline.** Chạy cùng commit, cùng Wrapper/JDK và cùng lệnh nhiều lần. Ghi median khoảng 235 giây cho warm build.

**Bước 2: tạo profile.** Chạy `./gradlew build --profile`, mở HTML report và nhận thấy `test` chiếm nhiều thời gian, trong khi configuration chỉ chiếm phần nhỏ.

**Bước 3: xem test report.** Một nhóm integration test khởi động database container cho từng lớp test. Phần lớn thời gian nằm ở setup và teardown, không phải assertion.

**Bước 4: đưa ra giả thuyết.** Nếu dùng chung fixture/container cho nhóm test có thể giảm thời gian khởi động mà vẫn cô lập dữ liệu, test runtime sẽ giảm.

**Bước 5: thay đổi và đo lại.** Nhóm điều chỉnh test fixture, chạy lại cùng scenario và kiểm tra kết quả test. Median giảm còn 170 giây, tất cả test vẫn được thực thi và pass.

**Bước 6: xác nhận CI.** Chạy pipeline trên runner tương đương, xem lại test report và đo nhiều lần. Chỉ sau khi xác nhận kết quả ổn định mới giữ thay đổi.

Đây là ví dụ minh họa cách suy luận, không phải cam kết rằng tối ưu test fixture luôn đem lại mức cải thiện cụ thể. Kết quả phụ thuộc dự án và môi trường.

## 19. Ví dụ thực hành: Maven reactor chậm

Giả sử một Maven reactor có `domain`, `persistence`, `api` và `application`. `./mvnw verify` mất 6 phút.

Quy trình:

1. Ghi lại Maven Wrapper, JDK, commit và command.
2. Dùng `time ./mvnw verify` hoặc `Measure-Command` để lấy wall-clock.
3. Xem reactor summary và tổng thời gian ở cuối log.
4. Chạy `./mvnw -pl application -am verify` để khoanh vùng project application cùng dependency trong reactor.
5. Bật timestamp/debug khi cần xác định plugin goal chậm.
6. Xem test report Surefire/Failsafe để tìm test kéo dài.
7. Nếu build có nhiều module độc lập, thử `-T 1C` sau khi xác nhận plugin có thể chạy thread-safe và tài nguyên đủ.
8. So sánh nhiều lần cùng điều kiện và kiểm tra kết quả test.

Nếu `application` phụ thuộc tất cả module, việc build riêng nó vẫn có thể kéo theo nhiều project. Không nên so trực tiếp thời gian `-pl application -am` với toàn reactor mà không ghi rõ phạm vi công việc.

## 20. Quy trình đo và tối ưu hiệu năng build

Có thể dùng trình tự sau cho một dự án mới hoặc một build đang chậm:

1. **Xác định trải nghiệm cần cải thiện.** Ví dụ incremental build của lập trình viên, CI verify hay release package.
2. **Chốt baseline.** Cùng source, build tool, JDK, command và cache state; chạy nhiều lần.
3. **Tách thời gian tổng thể.** Dùng wall-clock và profile/scan hoặc log phù hợp.
4. **Xác định nút thắt.** Phân loại configuration, dependency resolution, compile, test, packaging, I/O hoặc dịch vụ ngoài.
5. **Xem critical path.** Xác định công việc nào thực sự giữ build chưa thể kết thúc.
6. **Viết giả thuyết kiểm chứng được.** Nêu nguyên nhân và kết quả mong đợi nếu giả thuyết đúng.
7. **Thử một thay đổi.** Giữ nguyên các yếu tố khác.
8. **Đo lại cùng scenario.** So median, độ dao động, tài nguyên và task graph.
9. **Xác nhận correctness.** Test, artifact và dependency graph vẫn phải đúng.
10. **Lưu kết quả.** Ghi thay đổi, số đo trước/sau và điều kiện benchmark để lần sau có thể so sánh.

## 21. Bài tập vận dụng

Một build Gradle có thời gian như sau trong một lần warm build:

| Giai đoạn/task | Thời gian quan sát |
|---|---:|
| Configuration | 35 giây |
| `compileJava` | 22 giây |
| `compileTestJava` | 8 giây |
| `test` | 95 giây |
| `jar` | 6 giây |
| Các task khác | 14 giây |
| Wall-clock toàn build | 128 giây |

Hãy phân tích:

1. Vì sao tổng thời gian các mục có thể lớn hơn wall-clock?
2. Task nào đáng được điều tra đầu tiên nếu mục tiêu là giảm thời gian build hằng ngày?
3. Cần mở báo cáo nào để tìm test chậm trong task `test`?
4. Nếu configuration chiếm 35 giây, nên dùng công cụ nào để xem nguyên nhân cấu hình?
5. Nếu task `compileJava` chỉ chậm sau clean build, phép đo nào cần thực hiện để đánh giá incremental compilation?
6. Vì sao cần ghi rõ daemon, configuration cache, build cache và dependency cache?
7. `--dry-run` có thể trả lời câu hỏi gì và không thể trả lời câu hỏi gì?
8. Nếu muốn so sánh hai thay đổi cấu hình, cần giữ ổn định những đầu vào nào?
9. Nếu tăng số worker làm build chậm hơn, cần quan sát tài nguyên hệ thống nào?
10. Làm thế nào xác nhận một tối ưu không làm giảm mức kiểm chứng của build?

Có thể thực hành trên một project Java nhỏ: chạy `./gradlew build --profile`, xem báo cáo, chạy lại với cùng source, sau đó sửa một file và đo incremental build. Với Maven, so sánh `./mvnw test-compile`, `./mvnw test` và `./mvnw verify`, đồng thời ghi wall-clock và xem reactor summary.

## 22. Nguyên tắc duy trì hiệu năng build

- Đo đúng kịch bản người dùng hoặc CI thực sự chạy.
- Lưu baseline và điều kiện benchmark để kết quả có thể so sánh.
- Tách cold build, warm build, clean build và incremental build.
- Dùng profile/scan/log để xác định vùng chậm trước khi thay đổi.
- Xem task timeline và critical path, không chỉ task có duration lớn nhất.
- Phân biệt configuration, dependency resolution, compile, test và packaging.
- Dùng cache đúng mục đích và bảo đảm input/output của task được khai báo đầy đủ.
- Chỉ tăng parallelism sau khi kiểm tra plugin, dependency và giới hạn tài nguyên.
- Dùng profiler sâu khi log và profile đã thu hẹp được phạm vi.
- Thử một thay đổi mỗi lần và đo lại bằng cùng scenario.
- Giữ test và các kiểm tra correctness trong quy trình.
- Ghi lại số đo, nguyên nhân và kết quả để phát hiện regression về sau.

Tối ưu build bắt đầu bằng việc hiểu thời gian đang được tiêu tốn ở đâu. Khi có baseline đáng tin cậy, timeline và task graph rõ ràng, nhóm có thể tập trung vào đúng nút thắt, thử thay đổi có kiểm soát và xác nhận hiệu quả bằng số liệu thay vì phỏng đoán.

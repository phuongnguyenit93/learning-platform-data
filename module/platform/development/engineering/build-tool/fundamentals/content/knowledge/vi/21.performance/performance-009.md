# Đánh giá cải tiến hiệu năng cùng độ ổn định và tính đúng

Một thay đổi trong build script có thể làm build nhanh hơn nhưng vẫn là một thay đổi xấu nếu nó khiến output sai, bỏ qua kiểm tra cần thiết hoặc làm kết quả lúc đúng lúc sai. Ví dụ, bật chạy song song có thể rút ngắn thời gian build nhưng tạo race condition giữa các task; dùng build cache có thể giảm thời gian biên dịch nhưng trả lại output cũ nếu task khai báo thiếu input; bỏ integration test có thể làm pipeline nhanh hơn nhưng giảm khả năng phát hiện lỗi.

Vì vậy, đánh giá một cải tiến hiệu năng cần xem xét đồng thời ba khía cạnh:

- **Hiệu năng:** build hoặc ứng dụng hoàn thành nhanh hơn, dùng ít CPU/RAM/I/O hơn, hoặc xử lý được nhiều công việc hơn.
- **Độ ổn định:** kết quả và thời gian thực hiện không dao động bất thường; build không phát sinh lỗi ngẫu nhiên, race condition hoặc phụ thuộc trạng thái máy.
- **Tính đúng:** output, hành vi và các kiểm tra bắt buộc vẫn đáp ứng yêu cầu sau khi tối ưu.

Không nên chấp nhận một cải tiến chỉ vì một lần chạy nhanh hơn. Cần có baseline, phép đo lặp lại, so sánh trong điều kiện tương đương và bằng chứng rằng tính đúng cùng độ ổn định vẫn được giữ.

## 1. Phân biệt hiệu năng build và hiệu năng ứng dụng

Trong một dự án Java, từ “hiệu năng” có thể nói đến hai đối tượng khác nhau.

**Hiệu năng build** là thời gian và tài nguyên mà Gradle/Maven sử dụng để biên dịch, kiểm thử, đóng gói và tạo artifact. Ví dụ: thời gian `compileJava`, thời gian cấu hình Gradle, số task được khôi phục từ cache, hoặc tổng thời gian CI.

**Hiệu năng ứng dụng** là tốc độ và mức tiêu thụ tài nguyên khi chương trình đã chạy. Ví dụ: latency của API, throughput, thời gian khởi động JVM, CPU/RAM của service hoặc thời gian truy vấn database.

Hai loại có thể liên quan nhưng không thay thế nhau. Build nhanh hơn không chứng minh ứng dụng chạy nhanh hơn; tối ưu code runtime không nhất thiết làm build nhanh hơn.

| Đối tượng | Câu hỏi đo lường | Chỉ số thường dùng |
|---|---|---|
| Build | Mất bao lâu để tạo artifact và chạy verification? | Wall-clock time, task duration, configuration time |
| Incremental build | Thay đổi nhỏ cần chạy lại bao nhiêu công việc? | Thời gian sau thay đổi, số task `UP-TO-DATE`/`FROM-CACHE` |
| CI pipeline | Một commit cần bao lâu để có kết quả? | Job duration, queue time, cache hit, retry/failure rate |
| Ứng dụng | Một request mất bao lâu và hệ thống xử lý được bao nhiêu request? | Latency p50/p95/p99, throughput, error rate |
| Tài nguyên | Build hoặc ứng dụng dùng bao nhiêu tài nguyên? | CPU, peak memory, GC, disk/network I/O |

Trước khi thử tối ưu, hãy xác định đúng đối tượng. Nếu mục tiêu là rút ngắn vòng phản hồi của lập trình viên, cần đo incremental build và test feedback. Nếu mục tiêu là giảm thời gian phát hành, cần đo toàn bộ CI pipeline và các bước verification/release.

## 2. Ba điều kiện để một cải tiến được xem là thành công

Một cải tiến chỉ nên được chấp nhận khi đồng thời đạt các điều kiện cần thiết.

| Điều kiện | Bằng chứng cần có | Ví dụ không đạt |
|---|---|---|
| Nhanh hơn hoặc tiết kiệm tài nguyên hơn | Phép đo so sánh với baseline trong điều kiện tương đương | Một lần chạy nhanh hơn do cache nóng tình cờ |
| Ổn định | Nhiều lần chạy có độ dao động chấp nhận được, không có lỗi ngẫu nhiên | Task song song lúc pass lúc fail |
| Đúng | Test, output, artifact và hợp đồng build vẫn hợp lệ | Bỏ integration test khiến build nhanh nhưng lỗi không còn bị phát hiện |

Ví dụ, một task code generation giảm thời gian từ 40 giây xuống 8 giây. Nếu task mới không khai báo schema là input, khi schema đổi Gradle có thể dùng output cũ. Con số thời gian tốt hơn nhưng kết quả không đúng; cải tiến đó không thể chấp nhận.

## 3. Thiết lập baseline trước khi thay đổi

Baseline là kết quả đo của hệ thống trước khi áp dụng tối ưu. Không có baseline, rất khó xác định thay đổi có thực sự cải thiện hay chỉ trùng với một lần máy chạy nhanh.

Trước khi đo, ghi lại:

- Commit hoặc revision đang được build.
- Phiên bản Gradle/Maven Wrapper, JDK và toolchain.
- Hệ điều hành, CPU, RAM và loại runner/agent.
- Dependency lock và repository được sử dụng.
- Các tham số build, biến môi trường và profile.
- Cache đang bật hay tắt; daemon có nóng hay không.
- Lệnh chính xác, ví dụ `./gradlew clean build` hay `./gradlew test`.
- Test suite nào được chạy và có task nào bị skip hay không.

Không so sánh một build cold trên máy A với một build warm trên máy B rồi kết luận thay đổi code đã tăng tốc. Môi trường và trạng thái cache là một phần của điều kiện đo.

### 3.1. Chọn kịch bản đại diện

Một dự án thường có nhiều loại build:

| Kịch bản | Mô phỏng điều gì? | Ví dụ lệnh Gradle |
|---|---|---|
| Clean build | Build từ output project sạch | `./gradlew clean build` |
| Warm build | Chạy lại khi output và daemon đã được chuẩn bị | `./gradlew build` |
| Incremental build | Thay đổi một phần source/resource rồi build lại | Sửa một class rồi chạy `./gradlew classes` |
| Test feedback | Thời gian từ thay đổi đến kết quả test | `./gradlew test` |
| CI verification | Luồng kiểm tra gần với pipeline | `./gradlew clean check` |
| Cache restore | Khôi phục output từ build cache | `./gradlew build --build-cache` trong workspace phù hợp |

Không phải mọi kịch bản đều cần đo trong mọi dự án. Hãy chọn những luồng ảnh hưởng trực tiếp đến người dùng build hoặc chi phí CI.

### 3.2. Đo cold và warm riêng biệt

Cold build có thể bao gồm thời gian khởi động daemon, tải dependency, cấu hình project và tạo output lần đầu. Warm build thường tận dụng daemon, dependency cache, configuration cache hoặc build cache.

Hai kết quả trả lời hai câu hỏi khác nhau. Đừng gộp chúng thành một con số trung bình duy nhất.

Ví dụ bảng ghi nhận:

| Lần đo | Clean build | Incremental build | Cache state |
|---|---:|---:|---|
| Baseline 1 | 92 s | 18 s | Cold / warm theo kịch bản |
| Baseline 2 | 89 s | 17 s | Cùng điều kiện |
| Baseline 3 | 95 s | 19 s | Cùng điều kiện |

Các số trên chỉ minh họa cách ghi kết quả, không phải ngưỡng chuẩn cho mọi dự án.

## 4. Chọn chỉ số hiệu năng phù hợp

Thời gian tổng thể là chỉ số dễ hiểu nhất, nhưng không phải lúc nào cũng đủ để giải thích nguyên nhân.

### 4.1. Wall-clock time

Wall-clock time là thời gian thực tế từ lúc bắt đầu đến khi lệnh hoàn tất. Đây thường là chỉ số quan trọng nhất đối với lập trình viên và CI vì nó phản ánh thời gian chờ.

Có thể đo bằng `time` trên Linux/macOS:

```bash
time ./gradlew clean build
```

PowerShell có thể đo bằng `Measure-Command`:

```powershell
Measure-Command { .\gradlew.bat clean build }
```

Khi đo, hãy dùng cùng shell, cùng lệnh và cùng điều kiện cache. Đảm bảo output không bị ảnh hưởng bởi một job nặng khác chạy trên cùng máy.

### 4.2. Task duration và configuration time

Tổng thời gian build có thể bị chi phối bởi một task cụ thể hoặc bởi configuration phase. Nếu chỉ nhìn wall-clock, bạn biết build chậm nhưng chưa biết cần tối ưu ở đâu.

Với Gradle, có thể tạo profile:

```bash
./gradlew build --profile
```

Gradle tạo báo cáo profile trong thư mục reports của project, thường dưới `build/reports/profile/`. Báo cáo có thể cho biết thời gian cấu hình, task execution và một số thông tin liên quan đến build.

Có thể dùng Build Scan nếu tổ chức cho phép:

```bash
./gradlew build --scan
```

Build Scan cung cấp thông tin chi tiết về task, dependency, cache và môi trường. Việc upload dữ liệu scan cần tuân theo chính sách dữ liệu của tổ chức; không bật tùy tiện nếu build chứa thông tin nội bộ nhạy cảm.

### 4.3. CPU, memory, disk và network

Một thay đổi có thể giảm thời gian nhưng tăng mạnh peak memory hoặc I/O. Điều đó có thể làm CI thiếu ổn định khi nhiều job chạy đồng thời.

Các chỉ số nên cân nhắc:

- CPU utilization và thời gian CPU.
- Peak heap/non-heap memory hoặc tổng RSS của tiến trình.
- Garbage collection count/time khi JVM chịu tải.
- Disk read/write và số lượng file được tạo.
- Network bytes và thời gian tải dependency/cache.
- Số lượng worker/process đồng thời.

Ví dụ, tăng `max-workers` có thể rút ngắn build trên máy nhiều CPU nhưng làm RAM tăng vượt giới hạn runner. Khi đó pipeline có thể bị OOM hoặc chậm hơn do tranh chấp tài nguyên.

### 4.4. Cache effectiveness

Khi đánh giá build cache hoặc configuration cache, cần theo dõi:

- Số task `FROM-CACHE`.
- Số task `UP-TO-DATE`.
- Task nào không cacheable và lý do.
- Cache miss do input thay đổi hay do task implementation không ổn định.
- Thời gian tải output từ remote cache so với thực thi task.

Cache hit rate cao không tự động đồng nghĩa build nhanh hơn. Với output rất nhỏ, tải remote cache có thể tốn thời gian hơn chạy task. Cần đo cả latency khôi phục output và thời gian thực thi thực tế.

## 5. Đo lặp lại và xử lý dao động

Một lần đo không đủ để đánh giá cải tiến. Thời gian build có thể thay đổi do CPU scheduling, antivirus, filesystem cache, network, background process, daemon state và tải CI.

Hãy chạy nhiều lần theo cùng quy trình. Với tập số đo:

```text
Baseline:  92, 89, 95, 91, 90 giây
Candidate: 74, 76, 73, 75, 77 giây
```

Có thể so sánh median, min/max và độ phân tán. Median thường ít bị một lần chạy bất thường chi phối hơn mean. Tuy nhiên, vẫn cần xem toàn bộ phân bố để phát hiện outlier và độ dao động.

| Thống kê | Ý nghĩa |
|---|---|
| Minimum | Lần nhanh nhất; dễ bị ảnh hưởng bởi điều kiện thuận lợi bất thường |
| Mean | Trung bình; nhạy với outlier |
| Median (p50) | Giá trị giữa; hữu ích để mô tả lần chạy điển hình |
| p90/p95 | Thể hiện các lần chạy chậm ở đuôi phân bố |
| Standard deviation | Mức phân tán quanh mean |
| Failure rate | Tỷ lệ lần chạy thất bại |

Với CI, p95 hoặc tỷ lệ job vượt deadline có thể quan trọng hơn min. Một cải tiến làm median giảm nhưng p95 tăng mạnh có thể khiến trải nghiệm của một số developer hoặc pipeline xấu đi.

### 5.1. Dùng cùng số lần chạy cho baseline và candidate

Một phương pháp thực tế:

1. Chọn một commit baseline và một commit candidate.
2. Dùng cùng runner class, JDK, Gradle/Maven version và cache policy.
3. Chạy mỗi cấu hình nhiều lần.
4. Xen kẽ thứ tự chạy baseline/candidate nếu có thể để giảm ảnh hưởng nhiệt độ CPU hoặc tải máy theo thời gian.
5. Ghi lại mọi lần chạy, kể cả lỗi và timeout.
6. So sánh median, p95 và độ phân tán.

Không xóa các lần chạy chậm chỉ vì chúng làm kết quả kém đẹp. Nếu có lý do loại một lần đo, hãy ghi rõ lý do như runner bị gián đoạn hoặc job khác chiếm CPU.

## 6. Thiết kế thí nghiệm A/B cho thay đổi build

Khi thay một cơ chế như parallel execution, configuration cache, build cache hoặc incremental task, hãy thay đổi từng yếu tố chính một lần nếu mục tiêu là xác định nguyên nhân.

Ví dụ đánh giá configuration cache:

| Biến thể | Cấu hình | Điều cần đo |
|---|---|---|
| A | Configuration cache tắt | Configuration time, total time |
| B | Configuration cache bật | Configuration time, total time, cache reuse/failure |

Đảm bảo cả A và B chạy cùng task, cùng source revision và cùng dependency state. Nếu đồng thời bật configuration cache, remote build cache, parallelism và thay JDK, bạn khó biết yếu tố nào tạo ra cải tiến hoặc lỗi.

### 6.1. Kiểm soát biến gây nhiễu

Các biến có thể làm kết quả sai lệch:

- Gradle daemon đang nóng hay chưa.
- Dependency cache có sẵn hay không.
- Remote cache có dữ liệu hay không.
- Build chạy trong container hay host.
- Runner có cùng CPU/RAM quota hay không.
- Antivirus hoặc indexing service đang hoạt động.
- Mạng hoặc repository manager có tải khác nhau.
- Có test retry hoặc task bị skip hay không.

Ghi lại trạng thái các biến này trong kết quả đo. Nếu không thể giữ giống nhau, hãy phân nhóm số liệu theo kịch bản thay vì so sánh trực tiếp.

## 7. Đánh giá incremental build và task avoidance

Incremental build là một trong những luồng quan trọng nhất của trải nghiệm developer. Sau một thay đổi nhỏ, build tool nên chỉ thực hiện những công việc cần thiết.

Ví dụ, khi sửa một file Java không liên quan đến module khác, Gradle có thể chỉ biên dịch phần bị ảnh hưởng và chạy các test liên quan theo cấu hình. Nếu một task custom không khai báo input/output đúng, nó có thể luôn chạy lại hoặc tệ hơn là không chạy khi input đã thay đổi.

Khi đánh giá cải tiến incremental build, hãy đo:

- Thời gian sau thay đổi một class.
- Thời gian sau thay đổi resource.
- Thời gian sau thay đổi dependency/build script.
- Số task chạy lại.
- Số task `UP-TO-DATE`/`FROM-CACHE`.
- Output có phản ánh thay đổi mới không.

Không chỉ đo thời gian. Cần xác nhận thay đổi source thật sự xuất hiện trong class file hoặc artifact mới.

### 7.1. Kiểm tra task graph

Có thể dùng:

```bash
./gradlew build --dry-run
```

`--dry-run` giúp quan sát task nào được lên lịch mà không thực thi task action. Nó hữu ích để hiểu graph nhưng không phải phép đo thời gian build thực tế.

Để xem task outcome và cache behavior, chạy lệnh thật với log:

```bash
./gradlew build --info
```

### 7.2. Không tối ưu bằng cách bỏ dependency sai

Nếu một task mất nhiều thời gian, bỏ dependency của nó khỏi lifecycle có thể làm build nhanh hơn nhưng khiến output thiếu hoặc kiểm tra không còn chạy. Trước khi bỏ task, cần xác định task đó có phải một phần của hợp đồng build không và có thể thay thế bằng kiểm tra nhẹ hơn mà vẫn bảo đảm yêu cầu hay không.

## 8. Đánh giá parallel execution

Chạy song song có thể giảm wall-clock time khi các task độc lập và máy có đủ tài nguyên. Nhưng nó cũng làm lộ race condition nếu task chia sẻ file hoặc trạng thái không được quản lý.

Gradle có thể chạy task song song giữa project khi bật parallel execution:

```properties
org.gradle.parallel=true
```

Hoặc dùng tùy chọn phù hợp của Gradle khi chạy. Cần đo trước/sau và quan sát peak memory, CPU, I/O cùng failure rate.

Một task an toàn khi chạy song song nên:

- Có output directory riêng hoặc ghi file không xung đột.
- Không phụ thuộc thứ tự task khác nếu không khai báo dependency.
- Không sửa chung một file từ nhiều task.
- Không dùng mutable global state không được đồng bộ.
- Khai báo input/output và quan hệ task chính xác.
- Không thực hiện tác dụng phụ ngoài phạm vi task mà không kiểm soát.

Nếu parallelism làm build nhanh hơn 15% nhưng thỉnh thoảng tạo output hỏng, cải tiến đó chưa đạt. Cần sửa race hoặc giới hạn song song cho task cụ thể rồi đo lại.

## 9. Đánh giá build cache mà không đánh đổi tính đúng

Build cache có thể giảm đáng kể thời gian build, nhưng chỉ an toàn khi task output được xác định từ các input đã khai báo.

Một task cacheable cần:

- Khai báo mọi file/property/classpath ảnh hưởng output.
- Khai báo output rõ ràng.
- Không đọc hostname, thời gian hiện tại hoặc biến môi trường tùy tiện.
- Chuẩn hóa đường dẫn nếu task relocatable.
- Tạo output xác định cho cùng input.
- Không có side effect không thể khôi phục chỉ từ output.

Khi thử bật cache, hãy kiểm tra cả trường hợp cache miss và cache hit:

```bash
./gradlew clean build --build-cache --info
```

Sau đó chạy lại hoặc build ở workspace khác để xem task nào được khôi phục. Kiểm tra output sau cache restore bằng test hoặc so sánh checksum/nội dung phù hợp.

### 9.1. Kiểm tra tính đúng sau cache restore

Một quy trình kiểm tra có thể là:

1. Build từ input A và tạo output O.
2. Lưu checksum hoặc nội dung kỳ vọng của O.
3. Build lại với cùng input và xác nhận cache restore.
4. So sánh output được khôi phục với O.
5. Thay đổi một input quan trọng thành B.
6. Xác nhận cache key thay đổi hoặc task chạy lại.
7. Kiểm tra output mới phản ánh B.

Nếu task dùng biến môi trường làm input nhưng không khai báo, bước 5 có thể phát hiện cache trả output cũ. Đây là lỗi tính đúng, dù hiệu năng có vẻ rất tốt.

## 10. Đánh giá configuration cache

Configuration cache giảm chi phí configuration phase bằng cách lưu trạng thái cấu hình có thể tái sử dụng. Nó không phải build cache và không thay thế task output cache.

Có thể thử:

```bash
./gradlew build --configuration-cache
```

Chạy lần đầu để tạo configuration cache, sau đó chạy lại cùng build để đo thời gian configuration reuse. Cần kiểm tra Gradle có báo reuse cache hay phải cấu hình lại.

Một thay đổi có thể làm build nhanh hơn nhưng phá configuration cache nếu plugin/task truy cập trạng thái không tương thích. Không nên chỉ bỏ qua warning hoặc tắt tính năng để che vấn đề nếu configuration cache là mục tiêu của dự án.

Khi đánh giá:

- Đo lần đầu và lần reuse riêng biệt.
- Chạy cùng task graph và cùng tham số.
- Kiểm tra task/plugin compatibility.
- Xác nhận output vẫn đúng sau reuse.
- Theo dõi invalidation khi build script hoặc input cấu hình thay đổi.

## 11. Kiểm tra độ ổn định của test sau tối ưu

Một cải tiến build có thể thay đổi thứ tự task, số worker hoặc cách test được chạy. Điều này có thể làm lộ flaky test hoặc tạo lỗi mới.

Độ ổn định cần được đo bằng:

- Tỷ lệ test pass/fail qua nhiều lần chạy.
- Số lần retry.
- Test có timeout hoặc treo không.
- Thời gian test p50/p95.
- Sự khác biệt khi chạy song song và tuần tự.
- Sự khác biệt giữa local và CI.

Nếu test chỉ pass khi chạy tuần tự, cần tìm shared state, port, file hoặc database dùng chung. Không nên mặc định tăng timeout hoặc retry là sửa được nguyên nhân.

### 11.1. Phân biệt flaky test với regression thật

Khi test fail sau tối ưu:

1. Giữ lại log và test report của lần fail.
2. Chạy lại đúng commit và đúng môi trường để xác định có tái hiện không.
3. Kiểm tra thay đổi có ảnh hưởng thứ tự task, thread, process hoặc cache không.
4. Xác minh test data và tài nguyên ngoài có trạng thái sạch không.
5. Kiểm tra output build có thay đổi ngoài dự kiến không.

Nếu failure tái hiện ổn định, xử lý như regression. Nếu chỉ xuất hiện ngẫu nhiên, điều tra flaky/race; không loại bỏ kết quả fail khỏi số liệu hiệu năng.

## 12. Tính đúng của artifact sau tối ưu

Sau khi thay đổi build pipeline, hãy xác nhận artifact vẫn đáp ứng hợp đồng:

- Class và resource bắt buộc có mặt.
- Manifest/Main-Class hoặc module metadata đúng.
- Dependency/runtime classpath được phân giải chính xác.
- Version, classifier và extension đúng.
- Không thiếu generated source/resource.
- Test và static analysis bắt buộc vẫn chạy.
- Artifact có thể khởi động hoặc được consumer sử dụng.

Với thư viện, có thể tạo consumer sample project để compile và chạy API công khai từ artifact đã publish vào repository thử nghiệm. Với ứng dụng, có thể chạy smoke test trên JAR/WAR/distribution đã đóng gói.

Đây là cách phát hiện tình huống build nhanh hơn do vô tình bỏ qua một task package, resource generation hoặc verification.

## 13. Đo hiệu năng ứng dụng sau thay đổi code

Nếu cải tiến nằm trong Java application runtime chứ không phải build pipeline, cần đo các chỉ số runtime phù hợp.

### 13.1. Latency và throughput

- **Latency:** thời gian xử lý một request hoặc operation.
- **Throughput:** số request/operation hoàn thành trong một đơn vị thời gian.
- **Error rate:** tỷ lệ request thất bại hoặc trả kết quả sai.
- **Resource usage:** CPU, memory, GC, thread, connection pool và I/O.

Không nên chỉ nhìn average latency. Một thay đổi có thể cải thiện average nhưng làm p99 xấu đi do một số request bị block hoặc GC pause dài.

### 13.2. Microbenchmark và JMH

Với một đoạn code JVM nhỏ, không nên đo bằng cách gọi `System.nanoTime()` quanh một vòng lặp tùy ý rồi kết luận. JVM có JIT compilation, dead-code elimination, warmup, GC và các yếu tố khác làm kết quả sai lệch.

JMH (Java Microbenchmark Harness) được thiết kế cho microbenchmark JVM. Nó hỗ trợ warmup, measurement iterations, forks và tiêu thụ kết quả để giảm một số sai lệch phổ biến.

Ví dụ benchmark rút gọn:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Scope;

@State(Scope.Thread)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class ParserBenchmark {
    private final String input = "order-2026-001";

    @Benchmark
    public int parseLength() {
        return input.length();
    }
}
```

Đây là ví dụ minh họa cấu trúc benchmark; một benchmark thực tế cần cấu hình JMH plugin/dependency, warmup, measurement, forks và dữ liệu đại diện. Không dùng kết quả microbenchmark để dự đoán trực tiếp latency của toàn bộ service.

### 13.3. Load test và kiểm tra dưới tải

Với API/service, cần kiểm tra ở mức tải gần thực tế:

- Tải thấp để xác định latency cơ bản.
- Tải mục tiêu để đo throughput và p95/p99.
- Tải cao để quan sát saturation và error rate.
- Soak test để phát hiện memory leak hoặc suy giảm theo thời gian.

Điều kiện so sánh phải tương đương: cùng dữ liệu, cùng cấu hình, cùng hardware quota và cùng mức tải. Đồng thời xác nhận response đúng, không chỉ đo tốc độ trả lời.

## 14. Đánh giá trade-off hiệu năng và tài nguyên

Không phải cải tiến nào giảm wall-clock cũng tốt hơn trên mọi khía cạnh.

| Thay đổi | Lợi ích có thể có | Rủi ro cần đo |
|---|---|---|
| Tăng parallel workers | Giảm thời gian chờ | Tăng RAM/CPU contention, race condition |
| Bật build cache | Giảm task execution | Cache miss, remote download chậm, output sai nếu input thiếu |
| Bật configuration cache | Giảm configuration time | Plugin incompatibility, invalidation thường xuyên |
| Tăng heap | Giảm GC hoặc OOM trong một số trường hợp | Chiếm RAM runner, ảnh hưởng job khác |
| Tăng test parallelism | Giảm thời gian test | Shared state, port/data conflict, flaky test |
| Giảm test suite | Build nhanh hơn | Mất coverage hành vi và quality gate |
| Dùng dependency động ít kiểm soát | Có thể nhận bản mới tự động | Build không tái lập, cache thay đổi theo thời gian |
| Tắt một bước kiểm tra | Giảm thời gian pipeline | Giảm khả năng phát hiện lỗi |

Khi lựa chọn, hãy xem tổng chi phí: thời gian, tài nguyên, độ tin cậy và rủi ro phát hành. Một build nhanh hơn vài giây nhưng tăng failure rate hoặc gây rework thường không phải cải tiến thực tế.

## 15. Đặt ngưỡng và quality gate cho hiệu năng

Không nên đặt một ngưỡng chung cho mọi dự án. Ngưỡng cần dựa trên baseline, SLA nội bộ và chi phí của việc chậm.

Ví dụ chính sách:

- Incremental compile không được tăng quá một tỷ lệ nhất định so với baseline.
- CI verification p95 phải nằm dưới thời gian cho phép.
- Test failure rate phải bằng 0 đối với test bắt buộc.
- Không được tăng số flaky test hoặc số lần retry.
- Peak memory phải nằm trong giới hạn runner.
- Artifact checksum/reproducibility hoặc smoke test phải đạt theo hợp đồng.

Khi đo performance regression, nên dùng ngưỡng có biên độ để tránh báo động do nhiễu nhỏ. Với hệ thống có dữ liệu ổn định và đo lặp nhiều lần, có thể dùng kiểm định thống kê hoặc confidence interval. Với pipeline ít lần chạy, hãy báo rõ độ không chắc chắn thay vì khẳng định một thay đổi nhỏ là cải thiện có ý nghĩa.

## 16. Báo cáo kết quả thí nghiệm

Một báo cáo cải tiến nên giúp reviewer trả lời:

1. Vấn đề ban đầu là gì?
2. Đo ở kịch bản nào và trên môi trường nào?
3. Baseline và candidate khác nhau ở điểm nào?
4. Có bao nhiêu lần chạy và thống kê nào được dùng?
5. Thời gian, CPU, RAM, cache hit và failure rate thay đổi ra sao?
6. Test, output và artifact có được xác nhận đúng không?
7. Có trade-off hoặc giới hạn nào?
8. Cách tái hiện phép đo là gì?

Ví dụ bảng báo cáo:

| Chỉ số | Baseline | Candidate | Thay đổi |
|---|---:|---:|---:|
| Clean build median | 120 s | 98 s | -18.3% |
| Incremental build median | 24 s | 15 s | -37.5% |
| Build p95 | 132 s | 106 s | -19.7% |
| Peak memory | 2.1 GB | 2.4 GB | +14.3% |
| Test pass rate | 100% | 100% | Không đổi |
| Flaky/retry count | 0 | 0 | Không đổi |
| Artifact smoke test | Pass | Pass | Không đổi |

Các con số trên chỉ minh họa định dạng báo cáo. Khi báo cáo thật, phải ghi số lần đo, máy/runner, cache state và command chính xác. Nếu peak memory tăng, cần đánh giá xem mức tăng có phù hợp giới hạn tài nguyên không.

## 17. Những lỗi thường gặp khi đánh giá tối ưu

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Một lần build nhanh hơn nhiều | Cache nóng, máy ít tải hoặc dependency đã có sẵn | Chạy nhiều lần với baseline/candidate trong điều kiện tương đương |
| Median giảm nhưng CI vẫn hay chậm | p95/p99 hoặc queue time tăng | Theo dõi phân bố và queue time, không chỉ median |
| Build nhanh hơn nhưng artifact sai | Task bị bỏ qua hoặc cache key thiếu input | Kiểm tra task graph, input/output và artifact contents |
| Bật parallel làm test lúc pass lúc fail | Shared state hoặc race condition | Cô lập tài nguyên, khai báo dependency và kiểm thử lặp |
| Cache hit cao nhưng build không nhanh | Tải remote cache chậm hơn thực thi task | Đo restore time, task duration và kích thước output |
| Tối ưu local nhưng CI không cải thiện | Runner, cache policy hoặc môi trường khác | Đo trên CI đại diện và kiểm soát khác biệt môi trường |
| Tắt test làm pipeline xanh nhanh | Quality gate bị loại khỏi graph | Khôi phục test bắt buộc và tìm cách tối ưu thực thi test |
| Benchmark JVM cho kết quả bất thường | Không warmup, dead-code elimination hoặc GC | Dùng JMH và workload đại diện |
| Retry làm tỷ lệ pass tăng | Flaky test bị che chứ chưa được sửa | Theo dõi retry riêng và xử lý nguyên nhân gốc |
| Chỉ kiểm tra exit code build | Không xác nhận nội dung/hành vi artifact | Thêm test, checksum, consumer test hoặc smoke test phù hợp |

## 18. Quy trình đánh giá một cải tiến hiệu năng

Có thể áp dụng trình tự sau cho một thay đổi build hoặc runtime:

1. **Xác định mục tiêu:** rút ngắn clean build, incremental build, test feedback, CI hay latency ứng dụng.
2. **Chọn chỉ số:** wall-clock, p50/p95, CPU, memory, cache hit, throughput hoặc error rate.
3. **Ghi baseline:** commit, toolchain, máy, cache state, command và test suite.
4. **Tạo candidate có phạm vi rõ:** thay đổi một yếu tố chính để dễ quy kết nguyên nhân.
5. **Chạy lặp lại:** ghi tất cả lần đo, lỗi, timeout và retry.
6. **So sánh thống kê:** median, p95, độ phân tán và tài nguyên.
7. **Kiểm tra độ ổn định:** chạy lại test, kiểm tra race/flaky và khác biệt local/CI.
8. **Kiểm tra tính đúng:** xác nhận test bắt buộc, task graph, output và artifact.
9. **Đánh giá trade-off:** xem RAM, I/O, network, chi phí cache và độ phức tạp vận hành.
10. **Tài liệu hóa:** command, môi trường, dữ liệu và kết quả đủ để người khác tái hiện.
11. **Đưa vào CI có kiểm soát:** theo dõi regression sau khi áp dụng rộng rãi.

## 19. Ví dụ đánh giá bật Gradle build cache

Giả sử một project có nhiều task compile và code generation. Mục tiêu là giảm thời gian CI trên các commit chỉ thay đổi một phần source.

### Bước 1: Ghi baseline

```bash
./gradlew clean build --no-build-cache
```

Chạy nhiều lần trong môi trường chuẩn, lưu tổng thời gian, task duration và test report. Đảm bảo đây là baseline tương ứng với cách build hiện tại.

### Bước 2: Bật cache

```bash
./gradlew clean build --build-cache --info
```

Ghi lại task nào được lưu hoặc khôi phục. Nếu task không cacheable, tìm nguyên nhân và xem có thể mô hình hóa input/output đầy đủ hay không.

### Bước 3: Kiểm tra incremental và cache restore

Build lần đầu để tạo entry, sau đó chạy lại hoặc checkout cùng revision ở workspace khác. Xác nhận task `FROM-CACHE` và so sánh output.

### Bước 4: Kiểm tra thay đổi input

Sửa một file source, resource hoặc schema quan trọng. Xác nhận task liên quan chạy lại và output mới phản ánh thay đổi. Đây là bước cần thiết để phát hiện input bị khai báo thiếu.

### Bước 5: Xác nhận test và artifact

Chạy `check`, kiểm tra report, kiểm tra JAR và chạy smoke test. Không chỉ ghi nhận thời gian build.

### Bước 6: Kết luận

Chỉ chấp nhận cải tiến khi thời gian/chi phí giảm, cache restore đúng, test ổn định và artifact vẫn đúng. Nếu một task không an toàn để cache, giữ task đó ngoài cache và tối ưu các task khác.

## 20. Ví dụ đánh giá test parallelism

Giả sử unit test mất 8 phút. Candidate tăng số fork từ 1 lên 4.

Đo trước/sau:

| Chỉ số | 1 fork | 4 forks |
|---|---:|---:|
| Test duration median | 480 s | 190 s |
| Peak memory | 1.0 GB | 2.8 GB |
| Test failure | 0/10 | 1/10 |
| Retry needed | 0 | 1 |

Các số liệu trên chỉ minh họa. Dù thời gian giảm mạnh, candidate có một lần test failure và memory tăng gần ba lần. Không nên kết luận cải tiến thành công cho đến khi xác định nguyên nhân failure, kiểm tra tài nguyên runner và chạy lặp lại ổn định.

Nếu nguyên nhân là test dùng chung port, có thể cấp port ngẫu nhiên hoặc cô lập fixture. Nếu database test bị chia sẻ, dùng schema/database riêng theo worker. Sau khi sửa, đo lại với cùng số fork và cùng điều kiện.

## 21. Phân biệt tối ưu thật với việc giảm mức bảo đảm

Một số thay đổi làm thời gian giảm nhưng thực chất bỏ đi công việc:

- Bỏ integration test khỏi `check`.
- Dùng `-x test` trong CI.
- Đánh dấu task luôn `UP-TO-DATE` dù input thay đổi.
- Tắt kiểm tra checksum/dependency verification.
- Không chạy smoke test sau đóng gói.
- Dùng cache mà task khai báo thiếu input.
- Giảm timeout hoặc bỏ assertion để test pass.

Những thay đổi này không cải thiện hiệu năng của cùng một hợp đồng build; chúng thay đổi hợp đồng. Nếu dự án cần phân chia kiểm tra nhanh và đầy đủ, hãy định nghĩa các entry point rõ ràng, ví dụ `fastCheck` cho feedback nhanh và `check` cho verification đầy đủ. CI/release vẫn phải chạy bộ kiểm tra được cam kết.

## 22. Nguyên tắc cần ghi nhớ

- Đo đúng đối tượng: build performance khác application runtime performance.
- Ghi baseline trước khi thay đổi và giữ điều kiện đo tương đương.
- Đo nhiều lần; theo dõi median, p95, độ phân tán và failure rate thay vì chỉ nhìn một lần nhanh nhất.
- Theo dõi CPU, RAM, disk/network và cache behavior cùng wall-clock time.
- Phân biệt clean, warm, incremental, cache restore và CI build.
- Dùng Gradle profile/Build Scan hoặc log phù hợp để tìm bottleneck; không dùng `--dry-run` làm benchmark thực thi.
- Kiểm tra task graph và input/output để bảo đảm incremental build/cache không bỏ sót thay đổi.
- Chạy lại test và kiểm tra artifact sau khi bật parallelism, cache hoặc configuration cache.
- Không chấp nhận retry/flaky test tăng lên như một cái giá mặc định cho build nhanh hơn.
- Đánh giá trade-off giữa thời gian, tài nguyên, độ ổn định và tính đúng.
- Lưu command, môi trường và kết quả để người khác có thể tái hiện phép đo.

Một cải tiến hiệu năng có giá trị khi nó giảm thời gian hoặc tài nguyên trong điều kiện đo có thể lặp lại, đồng thời giữ cho build ổn định và sản phẩm đúng. Baseline, phép đo lặp, kiểm tra output và test report tạo thành bằng chứng để quyết định có nên áp dụng thay đổi hay không.

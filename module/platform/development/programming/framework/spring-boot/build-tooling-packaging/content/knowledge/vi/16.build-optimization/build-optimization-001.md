# Đo thời gian bản dựng trước khi chọn hướng tối ưu

## 1. Vấn đề: “Build chậm” chưa đủ để biết phải sửa gì

Một nhóm làm ứng dụng Spring Boot có thể nói “Maven mất hơn hai phút”, “Gradle vừa bật cache thì nhanh hơn”, hoặc “CI chạy quá lâu”. Những nhận xét ấy chưa chỉ ra **phần nào thực sự tốn thời gian**, liệu các lần chạy có **cùng điều kiện** và một thay đổi có **tạo cải thiện đo được** hay không.

Ví dụ, lần đầu chạy **./gradlew build** có thể phải tải Gradle distribution và dependencies, khởi động daemon, cấu hình project, compile, chạy tests và đóng gói JAR. Lần thứ hai có thể trả **UP-TO-DATE** cho hầu hết tasks. So thời gian của hai lần ấy rồi kết luận chỉ một thay đổi trong build.gradle làm build nhanh gấp mười lần là sai nếu điều kiện cache khác nhau.

**Nguyên tắc trung tâm:** trước khi bật parallel build, configuration cache, build cache, tăng heap, tách module hoặc bỏ tests, hãy đo **cùng một công việc** trên **cùng điều kiện**, tìm ra nút thắt và kiểm chứng giả thuyết bằng nhiều lần đo.

Một phép đo tốt phải trả lời được:
- **Đo cái gì?** Build sạch, incremental build, no-change build, CI verification hay chỉ packaging?
- **Đo ở đâu?** Laptop, CI runner, cùng JDK, CPU, RAM, ổ đĩa, mạng hay khác?
- **Đo bao lâu?** Wall-clock elapsed time, thời gian task/goal, startup, configuration, dependency resolution, test hay packaging?
- **Mỗi lần có chạy đúng công việc không?** Tests có thực sự chạy? Tasks có cache hit? Có download dependency?
- **Kết luận có ổn định không?** Có nhiều mẫu, trung vị và độ biến thiên không?
- **Cái gì sẽ thay đổi?** Chỉ một cấu hình tại một thời điểm hay cùng lúc đổi JDK, phiên bản Spring Boot, cache, số workers và tập tests?

Bài học này thuộc nhóm **Tối ưu bản dựng**: mục tiêu là **đo trước, phân tích sau, rồi mới tối ưu**.

## 2. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt thời gian **end-to-end** với thời gian Maven plugin goal và Gradle task.
2. Thiết kế bốn kịch bản benchmark: **fresh environment**, **clean build**, **no-change build**, và **incremental change**.
3. Đo Maven với báo cáo **Total time**, stopwatch của shell/PowerShell và log có thể đối chiếu.
4. Đo Gradle bằng **--profile**, **Build Scan** (khi được phép), task outcomes và time của toàn lệnh.
5. Không nhầm **UP-TO-DATE**, **FROM-CACHE**, **NO-SOURCE**, **SKIPPED** với công việc thực sự được thực hiện.
6. Tính trung vị, độ dao động và phần trăm cải thiện từ những mẫu cụ thể.
7. Từ số liệu chọn một giả thuyết: dependency/network, startup/configuration, Java compile, annotation processing, tests, packaging, cache hoặc tài nguyên máy.
8. Thiết lập phép đo đối chứng trước/sau, tránh tối ưu giả do skip tests hoặc dùng hai phạm vi build khác nhau.
9. Lưu một bảng baseline đủ thông tin để so sánh trên CI và theo thời gian.

## 3. Thế nào là một chỉ số thời gian có ý nghĩa?

### 3.1. Wall-clock elapsed time: chỉ số đầu tiên

Đo khoảng thời gian từ khi **bắt đầu gọi command** tới khi process kết thúc thành công hoặc thất bại:

~~~text
T_wall = t_finish - t_start
~~~

Ví dụ một lần gọi build mất 105 giây theo stopwatch. Con số này gần với thời gian người phát triển phải chờ khi dùng đúng command đó, kể cả một phần overhead từ JVM startup, script Wrapper, disk/network và xử lý console logs.

**Không dùng thời gian CPU thay thế wall-clock**: build có thể chờ mạng, I/O hoặc locks nên CPU time không phản ánh thời gian chờ của người dùng. Ngược lại, một build đa tiến trình có thể có **tổng CPU time lớn hơn wall-clock time** do nhiều lõi chạy song song.

Lưu ý: thời gian ghi trong Maven **Total time** và Gradle **BUILD SUCCESSFUL in ...** là thông tin build tool báo cáo, có thể không trùng chính xác stopwatch bao quanh toàn bộ invocation. Stopwatch ngoài process có thể bao gồm Wrapper bootstrap, khởi tạo shell/JVM và download distribution. Hãy dùng một **kiểu đồng hồ nhất quán** cho baseline và candidate.

### 3.2. Breakdown theo giai đoạn giúp tìm nút thắt

Một pipeline Java/Spring Boot thường gồm:

~~~text
Wrapper / Java startup
       |
Build initialization và configuration
       |
Dependency/plugin resolution
       |
Source generation + resource processing
       |
Java/Kotlin compilation
       |
Unit tests / integration tests / quality checks
       |
Spring Boot JAR/WAR packaging
       |
Artifacts, reports, cleanup và CI post-steps
~~~

Trên Gradle, profile/Build Scan giúp phân tích các phần **startup**, **configuration**, **dependency resolution**, **task execution** và chi tiết từng task. Với Maven, CLI thường in mỗi plugin goal trong lifecycle cùng **Total time** cuối build; muốn có breakdown thời lượng goals chính xác cần sử dụng profiling/instrumentation bổ sung phù hợp, hoặc đo riêng các phase có kiểm soát.

**Một cảnh báo quan trọng:** trong build có parallelism, tổng thời lượng các tasks **không nhất thiết bằng** thời gian end-to-end. Hai tasks chạy đồng thời 30 giây có thể tiêu tốn tổng 60 giây task time nhưng chỉ góp khoảng 30 giây vào wall time. Đừng cộng mọi task duration rồi gọi đó là thời gian build; hãy xem **critical path** và mức độ song song.

### 3.3. Thời gian nào mới là chỉ số mục tiêu?

| Người dùng quan tâm | Command/đo lường điển hình | Vì sao |
| --- | --- | --- |
| Developer sửa một dòng Java rồi test nhanh | Maven test hoặc Gradle test, sau thay đổi nhỏ | Tần suất lặp lại cao |
| Developer chạy lại không đổi code | Maven verify, Gradle build (no-change) | Đo caching/up-to-date behavior |
| CI kiểm tra pull request | Maven clean verify hoặc Gradle clean build | Phải giữ nguyên phạm vi kiểm thử |
| CI tạo executable artifact | Maven package/repackage hoặc Gradle bootJar/build | Đo đường phân phối thực tế |
| CI runner mới không có caches | Fresh checkout + deps/distribution download + build | Đo cold start và network |
| Build nhiều module | Maven reactor được chọn, Gradle task paths | Phân biệt toàn repo và chỉ module cần thiết |

Nếu mục tiêu là **rút thời gian CI verify**, đo mỗi lần **bootJar** chưa đủ vì nó có thể **không chạy tests**. Nếu mục tiêu là **developer feedback khi sửa code**, đo clean build toàn repo có thể không đại diện. Chọn kịch bản theo trải nghiệm muốn cải thiện, không theo command nào cho số nhỏ nhất.

## 4. Bốn kịch bản cần đo riêng

### 4.1. Fresh environment: môi trường chưa có cache

**Fresh build** là lần build trên một runner/workspace mới theo định nghĩa bạn chọn, có thể chưa tải Gradle distribution, Maven/Gradle plugins, dependencies và chưa có build outputs.

Đặc điểm:
- Network, repository mirror/proxy, DNS, TLS và tốc độ download có thể chiếm phần lớn thời gian.
- Gradle daemon chưa được warm up, JVM chưa có lợi ích của các lần chạy trước.
- Maven local repository hoặc Gradle User Home có thể trống nếu runner thật sự mới.
- Nó phù hợp với **ephemeral CI agents** hoặc trải nghiệm setup ban đầu.

**Cách đo đáng tin:** dùng CI runner/container image hoặc một môi trường thử nghiệm riêng được chuẩn bị giống nhau cho các lần A/B. Không tự xóa **~/.m2** hoặc **~/.gradle** của người dùng để giả lập cold: việc đó có thể làm chậm các dự án khác, gây mất cache và thay đổi điều kiện ngoài mong muốn.

### 4.2. Clean build: xóa output, không nhất thiết xóa dependency cache

~~~bash
./mvnw -B -ntp clean verify
./gradlew --console=plain clean build
~~~

**clean** xóa các build output tương ứng; nó **không đồng nghĩa** xóa Maven repository trong **~/.m2/repository** hoặc Gradle dependency cache trong **~/.gradle/caches**. Gradle build cache cũng có thể khôi phục task outputs sau clean nếu đã bật.

Do đó, hãy ghi nhãn thật chính xác: **clean output, warmed dependency caches** hoặc **clean output, build-cache enabled**, thay vì gọi mọi lần clean là cold build.

Dùng kịch bản này nếu muốn đo công việc compile/test/package từ outputs sạch, nhưng vẫn phải ghi cache settings và môi trường.

### 4.3. No-change warm build: chạy lại y hệt, không đổi input

~~~bash
./mvnw -B -ntp verify
./mvnw -B -ntp verify

./gradlew --console=plain build
./gradlew --console=plain build
~~~

Các cặp lệnh là **hai lần chạy liên tiếp** của một công cụ (chọn Maven hoặc Gradle). Không sửa source, build scripts, system properties hoặc environment giữa hai lần.

Với Gradle Java plugin, lần sau nhiều tasks có thể **UP-TO-DATE** hoặc **FROM-CACHE**. Maven tiêu chuẩn không có chính xác cùng cơ chế task-output cache mặc định như Gradle; một số plugin có incremental checks riêng, nhưng Maven vẫn có thể thực thi goals/test/packaging. Nếu project dùng **Maven Build Cache Extension**, đó là một thành phần tùy chọn, phải ghi riêng trong baseline.

**Không dùng no-change time để dự đoán thời gian compile thực khi sửa source.** Nó là một kịch bản khác cần đo riêng.

### 4.4. Incremental build sau một thay đổi nhỏ

Ví dụ sửa một phương thức trong **src/main/java**, giữ nguyên dependency graph, rồi gọi command thường dùng:

~~~bash
./mvnw -B -ntp test
./gradlew --console=plain test
~~~

Lý tưởng là thử một thay đổi **không đổi public ABI** và một thay đổi **có đổi ABI** để xem module/tác vụ nào phải biên dịch lại. Với dự án có generated sources/annotation processors, một thay đổi nhỏ có thể làm tăng phạm vi invalidation.

**Quy trình:** chuẩn bị cùng commit, thực hiện một patch xác định, đo lượt build, hoàn tác patch và khôi phục cùng điều kiện cho lần tiếp theo. Không đo lần đầu của A ở workspace warm rồi đo B trên một workspace đã bị sửa khác mà không reset. Đặc biệt khi Gradle có incremental compilation/build cache, thứ tự và trạng thái outputs ảnh hưởng kết quả.

## 5. Đặt một baseline có thể lặp lại

### 5.1. Bản ghi tối thiểu

Trước khi đo, ghi:

| Nhóm | Cần lưu |
| --- | --- |
| Mã nguồn | Commit hash/branch, uncommitted diff, module scope |
| Build tool | Maven hoặc Gradle, phiên bản Wrapper, plugin versions |
| JDK | java -version và JVM mà Maven/Gradle thực sự dùng |
| Lệnh | Full command gồm tasks/phases, flags, profiles, test filters |
| Máy | OS, CPU cores, RAM, loại ổ đĩa, CI runner type, container limits |
| Network | Online/offline, repository mirror, cache đã warm hay chưa |
| Cache | Gradle build cache/configuration cache, daemon, Maven local repo/extension |
| Kịch bản | Fresh/clean/no-change/incremental; lần warm-up số mấy |
| Kết quả | Exit status, wall time, report paths, task outcomes, tests summary |
| Môi trường chạy | CI job identifier, thời điểm, tải máy, antivirus/background jobs |

Một kết quả chỉ gồm “98 giây” mà không có command/commit/cache state không đủ đáng tin để ra quyết định. Nếu A/B chạy trên runner khác cấu hình hoặc đổi số test cases, chênh lệch có thể không phải do phương án tối ưu.

### 5.2. Cần bao nhiêu mẫu?

Một lần đo chỉ cho giá trị quan sát tại một thời điểm. Tối thiểu nên lấy **5 mẫu hợp lệ** cho mỗi phương án trong điều kiện ổn định để biết mức dao động; nếu hiệu quả dự kiến chỉ vài phần trăm hoặc môi trường nhiều nhiễu, cần nhiều mẫu hơn.

**Warm-up** 1–2 lần đối với benchmark warm/daemon để JVM, Gradle daemon và caches về trạng thái mục tiêu; **không** lấy lượt warm-up ấy làm số liệu nếu mục tiêu là steady-state performance. Ngược lại, với fresh CI cold-start, **lượt cold đầu tiên chính là đối tượng đo** và phải dùng nhiều môi trường fresh độc lập nếu muốn ước lượng phân phối cold times.

Lưu **tất cả** mẫu, không chỉ mẫu nhanh nhất. Có thể dùng **median** làm đại diện vì bền với một lần chậm bất thường; dùng min/max hoặc p25–p75 để thể hiện độ biến thiên. Với chỉ 5 mẫu, đừng trình bày p95/p99 như dự báo chính xác cho SLA.

## 6. Đo Maven trên Linux/macOS

### 6.1. Đọc thời gian Maven báo cáo

Chạy một build thực, ví dụ:

~~~bash
./mvnw -B -ntp clean verify
~~~

Các cờ:
- **-B**: Maven batch mode, phù hợp automation và log không tương tác.
- **-ntp**: tắt dòng download/upload transfer progress, giúp log ít nhiễu hơn.
- **clean verify**: xóa output rồi thực hiện lifecycle đến verify, bao gồm test và packaging theo POM.

Cuối một build thành công, Maven thường in các dòng tương tự:

~~~text
[INFO] BUILD SUCCESS
[INFO] Total time:  42.817 s
[INFO] Finished at: 2026-11-09T02:00:00Z
~~~

**Đây chỉ là log minh họa**, không phải kết quả đo thực tế của project. **Total time** của Maven tiện cho quan sát nhanh; muốn so sánh toàn bộ thời gian người dùng chờ, dùng thêm stopwatch bao quanh CLI. Với project nhiều module, Maven còn có thể in reactor summary, nhưng summary tiêu chuẩn **không cung cấp profiling chi tiết mọi goal theo thời gian thực thi**.

### 6.2. Dùng shell time làm đồng hồ ngoài

Trên Linux/macOS:

~~~bash
time -p ./mvnw -B -ntp clean verify
~~~

Output bên ngoài thường có dạng:

~~~text
real 43.21
user 66.78
sys 2.91
~~~

Đây cũng là **số giả định minh họa**. **real** là elapsed wall-clock, **user** là CPU time ở user mode, **sys** là CPU time ở kernel mode. Trên hệ nhiều process/threads, **user** có thể cao hơn **real**. Cú pháp **time -p** được nhiều shell/Unix tools hỗ trợ; chi tiết output tùy shell và hệ điều hành.

Nếu đang đo warm build, thay **clean verify** bằng **verify** nhưng phải ghi kịch bản, không so thẳng kết quả warm với baseline clean.

### 6.3. Script Linux lấy 5 mẫu clean build, giữ log theo từng lượt

Đối với **Linux có GNU /usr/bin/time**, tạo **benchmark-maven.sh** ngoài hoặc trong project root:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

RESULT_DIR="$(cd .. && pwd)/benchmark-results-maven"
mkdir -p "$RESULT_DIR"

for run in 1 2 3 4 5; do
    echo "Maven clean verification: run $run"
    /usr/bin/time -p -o "$RESULT_DIR/run-$run.time"         ./mvnw -B -ntp clean verify         > "$RESULT_DIR/run-$run.log" 2>&1
done

echo "Completed 5 successful Maven runs."
echo "Timing and build logs: $RESULT_DIR"
~~~

Cách chạy:

~~~bash
chmod +x benchmark-maven.sh
./benchmark-maven.sh
~~~

Trong script này, **set -e** làm vòng lặp dừng khi một lần build thất bại; như vậy không vô tình ghi một lần FAIL thành một mẫu “nhanh”. Output logs và time files nằm **ngoài project root**, tránh ảnh hưởng đến tasks có quy tắc quét input trong repo. **/usr/bin/time -p -o** ở đây là cú pháp của **GNU time**, không phải tùy chọn portable cho mọi macOS. Trên macOS có thể dùng shell **time -p** và chuyển hướng stderr phù hợp.

Lưu ý script chạy **5 clean builds**, trong đó dependencies và tool distributions có thể ngày càng được warm. Nếu muốn benchmark **steady-state clean with warm deps**, hãy chuẩn bị/warm caches trước khi chạy và lưu điều kiện ấy. Nếu muốn benchmark **fresh cold**, không dùng vòng lặp trên cùng một workspace làm năm mẫu cold độc lập.

**Thao tác clean xóa build outputs** và có thể mất thời gian/tốn I/O. Chỉ chạy trong workspace mà bạn có quyền thực hiện clean, không chạy trên job production đang dùng chung output của process khác.

### 6.4. Không dùng skipTests để “chứng minh” tối ưu

Lệnh:

~~~bash
./mvnw -B -ntp clean verify -DskipTests
~~~

thường nhanh hơn vì **Surefire không thực thi unit tests** (test source vẫn được compiler biên dịch), nhưng đó là **thay đổi phạm vi xác minh**, không phải tăng hiệu năng của cùng một build.

**-Dmaven.test.skip=true** còn bỏ test compilation và execution theo plugins hỗ trợ, nên lại càng khác baseline có test. Khi đánh giá một phương án tối ưu build, **không được so lệnh có test với lệnh bỏ test** rồi tuyên bố thuật toán compile, compiler hoặc cache đã cải thiện. Nếu có use case đóng gói nhanh với skip, lập một dòng baseline **riêng** và ghi rõ ý nghĩa giới hạn.

## 7. Đo Maven trên Windows/PowerShell

Maven Wrapper Windows thường là **mvnw.cmd**. Để đo toàn command và xác minh exit code, dùng PowerShell:

~~~powershell
$clock = [System.Diagnostics.Stopwatch]::StartNew()
& .\mvnw.cmd -B -ntp clean verify
$code = $LASTEXITCODE
$clock.Stop()

Write-Host ("elapsed={0:F3}s; exit={1}" -f $clock.Elapsed.TotalSeconds, $code)
if ($code -ne 0) { exit $code }
~~~

**Stopwatch** dùng timer của .NET cho elapsed time; ở đây không cần một module PowerShell ngoài. **$LASTEXITCODE** ghi exit code của lệnh .cmd. Khi code khác 0, ví dụ dừng script với code đó; không coi build lỗi là mẫu benchmark thành công.

Đo Gradle tương tự, thay dòng gọi command bằng:

~~~powershell
& .\gradlew.bat --console=plain clean build
~~~

Hai đoạn là **lựa chọn thay thế**, không chạy Maven rồi Gradle trong cùng một lượt đo nếu mục tiêu là so cùng command. Với Windows, đường filesystem/cache, antivirus scanning và process startup có thể khác Linux, nên kết quả không so trực tiếp khi mục đích là quyết định tối ưu trên một nền tảng cụ thể.

Có thể dùng **Measure-Command**, nhưng nếu muốn kiểm tra exit code, lưu stdout/stderr và metadata của command, phiên bản Stopwatch tường minh giúp người học thấy rõ phạm vi thời gian được bao quanh.

## 8. Đo Gradle bằng CLI và local profile

### 8.1. Bắt đầu từ command thật

Ví dụ Spring Boot Gradle project:

~~~bash
./gradlew --version
./gradlew --console=plain clean build
./gradlew --console=plain build
~~~

Lệnh thứ hai là **clean build**, lệnh thứ ba là **no-change/warm build** nếu không sửa bất kỳ input nào. Gradle thường in thông báo:

~~~text
BUILD SUCCESSFUL in 18s
9 actionable tasks: 6 executed, 3 up-to-date
~~~

Dòng trên chỉ là **minh họa**; số tasks/thời gian/task outcomes thực tế phụ thuộc project và Gradle version. Nên xem **tasks thực thi thật hay UP-TO-DATE/FROM-CACHE** thay vì nhìn một con số duy nhất.

**--console=plain** làm log ít chứa progress UI/ANSI sequences, thuận tiện lưu trong CI và đọc lại. Nó không phải cờ làm build nhanh hơn theo một mức cụ thể.

### 8.2. Tạo báo cáo --profile tại máy, không cần upload scan

~~~bash
./gradlew --console=plain build --profile
~~~

Gradle tạo một HTML report thông thường dưới:

~~~text
build/reports/profile/
    profile-<timestamp>.html
~~~

Ở đây **<timestamp>** là phần tên file do Gradle tạo, không phải ký tự bạn phải dùng nguyên trong tên file. Với multi-project builds, report thường nằm dưới **build/reports/profile** của **root project**. Report hiển thị startup/configuration/task execution theo categories, nhưng không chi tiết bằng Build Scan.

Để đo một lượt clean có phân tích:

~~~bash
./gradlew --console=plain clean build --profile
~~~

**--profile** có thể thêm một ít overhead do thu thập và ghi report. Khi so A/B, nên dùng cùng option; khi cần đánh giá trực tiếp user wait time, đo bình thường (không profiler) và dùng một lượt có profiler để **chẩn đoán**. Không trộn một mẫu A có --profile với B không có --profile mà không ghi khác biệt.

Tài liệu: https://docs.gradle.org/current/userguide/inspect.html

### 8.3. Đọc đúng breakdown của Gradle

Trong profile, chú ý:
- **Startup:** JVM/Gradle startup, daemon, init scripts, wrapper distribution nếu cần.
- **Settings / Configuration:** đánh giá settings.gradle, build.gradle, apply plugins, cấu hình projects/tasks.
- **Dependency resolution:** tải/giải module versions và metadata tùy build.
- **Task execution:** compileJava, processResources, test, bootJar và các tasks khác.
- **Task outcomes:** khi task đã UP-TO-DATE hoặc FROM-CACHE, thời gian thực thi actions có thể khác hẳn lượt rebuild.

Nếu configuration chiếm nhiều thời gian trên **no-change build**, xem plugins/configuration scripts và cân nhắc **configuration cache** sau khi xác nhận compatibility. Nếu test chiếm 70% thời gian, việc bật thêm compiler worker count có thể không giải quyết vấn đề chính.

### 8.4. Build Scan: nhiều thông tin hơn, nhưng có chia sẻ metadata

Nếu chính sách bảo mật và người sở hữu repo cho phép:

~~~bash
./gradlew --console=plain build --scan
~~~

Build Scan tạo một bản ghi có thông tin performance, task timeline, environment, dependencies và build events. Lệnh có thể yêu cầu đồng ý điều khoản; scan có thể được **publish tới dịch vụ bên ngoài hoặc Develocity server** tùy cấu hình.

**Không bật --scan cho project nội bộ nhạy cảm khi chưa được cho phép**. Build Scan có thể chứa metadata của build/repo/máy, đường dẫn, task names và phần thông tin khác do plugin thu thập. Nếu cần chỉ giữ local evidence, dùng **--profile**; nếu công ty có Develocity nội bộ được duyệt, dùng server và chính sách dữ liệu của tổ chức.

Một Build Scan có thể giúp tìm:
- Thời gian startup vs configuration vs execution.
- Task timeline và critical path.
- Task cache hits, up-to-date behavior.
- Remote/local cache, dependency resolution bottlenecks.
- Plugin hoặc build script mất thời gian trong configuration.

Nguồn: https://docs.gradle.org/current/userguide/build_scans.html

### 8.5. --dry-run không dùng để đo build execution

~~~bash
./gradlew build --dry-run
~~~

Lệnh này là **xem kế hoạch task**, không thực thi task actions thông thường. Nếu thời gian --dry-run rất nhỏ, nó **không** chứng minh compiler, tests hay Spring Boot packaging đã nhanh tương đương. Dù vậy, configuration phase vẫn có thể được thực hiện và có side effects từ build scripts.

Dùng --dry-run khi cần biết task graph hoặc task nào còn được chọn; dùng **build thật** khi đo trải nghiệm build.

## 9. Bốn yếu tố Gradle dễ tạo benchmark sai

### 9.1. UP-TO-DATE không phải compiler chạy nhanh hơn

Nếu task **:compileJava UP-TO-DATE**, Gradle xác định inputs/outputs phù hợp nên thường **không gọi Java compiler** trong lượt đó. Đó là lợi ích incremental/up-to-date checking, không chứng minh bản thân **javac** nhanh hơn.

Nếu muốn ép thực thi tất cả tasks có thể chạy trong graph:

~~~bash
./gradlew --console=plain test --rerun-tasks
~~~

Theo Gradle documentation, **--rerun-tasks** bỏ qua up-to-date checks và build cache để ép task actions chạy lại; nó tương tự **clean test** ở mục đích tái thực thi, nhưng **không xóa build outputs** như clean. Do đó **--rerun-tasks** và **clean** không hoàn toàn đồng nhất, nhất là với custom tasks.

### 9.2. Build cache và dependency cache là hai cơ chế khác nhau

- **Dependency cache** lưu downloaded artifacts/metadata từ repositories.
- **Build cache** lưu **outputs của tasks** đủ điều kiện và có input fingerprints phù hợp.
- **UP-TO-DATE** là kết quả kiểm tra input/output trong workspace đang có.
- **Configuration cache** lưu kết quả **configuration phase** cho các lần build tương thích.

Các lệnh kiểm soát Gradle build cache:

~~~bash
./gradlew build --build-cache
./gradlew build --no-build-cache
~~~

Nếu bật build cache, clean vẫn xóa **build/** nhưng task có thể phục hồi outputs với **FROM-CACHE**. Vì vậy benchmark **clean build with cache** có thể khác clean build với **--no-build-cache**.

**Không nên xóa ~/.gradle/caches** để làm benchmark nếu không có workspace/CI riêng. Một lần chạy **--no-build-cache** không có nghĩa dependency cache cũng bị vô hiệu.

### 9.3. Configuration cache và Gradle daemon

~~~bash
./gradlew build --configuration-cache
./gradlew build --no-configuration-cache
~~~

Configuration cache giảm công việc cấu hình nếu plugin/scripts/tasks tương thích. Nó **không tự biến test methods thành nhanh hơn** và không thay thế build cache. Lần đầu tạo cache và lần sau reuse cần được đo **cùng một kịch bản**; nếu cấu hình bị invalidated thì các lần sau có thể phải cấu hình lại.

Gradle daemon giúp tránh chi phí khởi động JVM và làm warm environment nhanh hơn. **--no-daemon** đổi mô hình startup/daemon, không phải một lựa chọn để “đo công bằng hơn” trong mọi trường hợp. Nếu CI production dùng daemon, benchmark cũng nên phản ánh chính sách đó; nếu cần đo first-run overhead, ghi rõ daemon có sẵn hay không.

### 9.4. Tác vụ chạy song song và critical path

Trong multi-project builds, Gradle có thể chạy một số tasks song song (khi cấu hình và task graph cho phép). Khi bật parallelism, tổng task CPU time có thể tăng dù wall-clock giảm. Vì vậy trước khi bật **--parallel**, kiểm tra critical path và khả năng contention RAM/CPU/disk.

Chỉ so phương án với **cùng test suite, cùng nguồn và cùng phần cứng**. Nếu song song làm test suite flaky vì dùng chung database/port, việc giảm vài giây không đáng giá so với mất độ tin cậy.

## 10. Maven có cache giống Gradle không?

Maven tiêu chuẩn dùng **local repository** để lưu tải dependencies/plugins, giúp những lần build sau không download lại. Điều này **khác** khả năng cache task outputs của Gradle.

Maven có **Apache Maven Build Cache Extension** nhưng đó là một **extension tùy chọn**, cần cài/cấu hình/đánh giá, không phải cache task-output mặc định có sẵn trong mọi Maven 3 build. Tài liệu extension cho biết phiên bản hiện hành yêu cầu **Maven 3.9.0+** và cần khai báo extension, có thể bật remote cache khi phù hợp.

Không dùng một baseline Maven 3.6 không có extension so với Maven 3.9 có extension và kết luận “Maven core nhanh hơn X%”; bạn đã thay cơ chế caching. Nếu cân nhắc extension, đo riêng:
- Không có extension.
- Extension enabled nhưng cold cache.
- Extension enabled và cache hit.
- CI agent mới với shared remote cache.

**Nhớ kiểm chứng đúng đầu ra và tests**: cache sai input fingerprint có thể tái sử dụng artifact không phù hợp. Maven Build Cache Extension là opt-in và chủ project chịu trách nhiệm xác minh chính xác.

Nguồn: https://maven.apache.org/extensions/maven-build-cache-extension/

## 11. Ví dụ Spring Boot dùng làm đối tượng benchmark

Một project nhỏ giúp thực hành command và đọc outcomes mà không cần thêm database, Docker hoặc external services. **Nó không đại diện kích thước một dự án doanh nghiệp**; không dùng thời gian từ ví dụ tí hon để dự báo lợi ích của thay đổi trong repo vài triệu dòng code.

Dùng **Java 17**, Spring Boot **3.5.16**, và Maven hoặc Gradle. Spring Boot 3.5.16 thực sự được phát hành ngày **25/06/2026** và là bản OSS cuối cùng của nhánh 3.5; bài chọn để có ví dụ ổn định, không phải khuyến nghị nhánh đang nhận OSS fixes. Dự án mới phải chọn phiên bản được hỗ trợ theo yêu cầu bảo mật và tính tương thích.

### 11.1. Sơ đồ file

~~~text
build-timing-lab/
├── pom.xml hoặc build.gradle (+ settings.gradle)
├── mvnw / mvnw.cmd / .mvn/wrapper/... (nếu Maven)
├── gradlew / gradlew.bat / gradle/wrapper/... (nếu Gradle)
└── src/
    ├── main/java/com/example/timing/
    │   ├── TimingApplication.java
    │   └── MathOperations.java
    └── test/java/com/example/timing/
        └── MathOperationsTest.java
~~~

Wrapper phải được tạo bằng công cụ tương ứng như Spring Initializr hoặc Wrapper plugin; ghi file POM/build script không tự tạo Wrapper.

### 11.2. Java source độc lập và có kết quả xác định

Tệp **src/main/java/com/example/timing/MathOperations.java**:

~~~java
package com.example.timing;

public final class MathOperations {
    private MathOperations() {
    }

    public static int sumFirst(int n) {
        if (n < 0 || n > 1000) {
            throw new IllegalArgumentException("n must be in 0..1000");
        }

        int result = 0;
        for (int value = 1; value <= n; value++) {
            result += value;
        }
        return result;
    }
}
~~~

Tệp **src/main/java/com/example/timing/TimingApplication.java**:

~~~java
package com.example.timing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TimingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimingApplication.class, args);
        System.out.println("sum=" + MathOperations.sumFirst(10));
    }
}
~~~

Tệp **src/test/java/com/example/timing/MathOperationsTest.java**:

~~~java
package com.example.timing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MathOperationsTest {
    @Test
    void sumOfFirstTenNumbers() {
        assertEquals(55, MathOperations.sumFirst(10));
    }
}
~~~

Nếu chạy ứng dụng Spring Boot non-web với dependency **spring-boot-starter** thì console có thể chứa các dòng Spring logging, nhưng một dòng do source code này in ra sau khi context khởi động là:

~~~text
sum=55
~~~

Test **sumOfFirstTenNumbers** kiểm tra phép cộng 1 + 2 + ... + 10 = 55; nếu test được chạy đúng qua JUnit Jupiter, nó có thể PASS. Vì demo không có embedded web server, không mong đợi endpoint HTTP hoặc một process phục vụ port 8080.

### 11.3. Maven pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>build-timing-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot starter parent quản lý dependency versions và Maven plugins. **spring-boot-maven-plugin** được khai báo để áp dụng repackage theo parent, tạo executable JAR khi package. Không thêm **-DskipTests** trong phép đo baseline nếu mục tiêu là verify đầy đủ.

Các lệnh:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
./mvnw -B -ntp verify
java -jar target/build-timing-lab-1.0.0.jar
~~~

Đọc **Total time** ở cuối hai lần build, sau đó đo ngoài bằng **time -p**. Kết quả lần thứ hai có thể khác vì Maven local repository đã warm, nhưng không được khẳng định Maven skip tất cả compilation/tests như Gradle up-to-date.

### 11.4. Gradle Groovy DSL đầy đủ

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'build-timing-lab'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dùng plugin Java và Spring Boot 3.5.16, Gradle Wrapper 8.14 là một lựa chọn hợp lệ cho ví dụ. Dependency-management plugin giúp import Spring Boot BOM. Nếu project không dùng plugin đó, phải khai báo BOM bằng Gradle native platform phù hợp thay vì bỏ mọi version.

Các lệnh:

~~~bash
./gradlew --version
./gradlew --console=plain clean build
./gradlew --console=plain build
./gradlew --console=plain build --profile
java -jar build/libs/build-timing-lab-1.0.0.jar
~~~

Lượt **build** đầu tiên và lượt **build** lặp lại có thể cho task outcomes khác nhau. Report **--profile** được tạo dưới **build/reports/profile** khi Gradle hỗ trợ option đó; kiểm tra HTML report để xem phần overhead thuộc startup, configuration hay tasks.

### 11.5. Điều gì làm ví dụ này hữu ích nhưng không đại diện?

**MathOperations** gần như không tốn công compile/test, nên phần lớn thời gian có thể đến từ startup/configuration/repository resolution và framework/plugin overhead. Nếu thêm 5.000 test cases hoặc annotation processors, bottleneck có thể khác hoàn toàn. Khi đưa phép đo vào dự án thật, vẫn phải ghi test count, active profiles, số submodules và dependency cache state.

## 12. Cách tính trung vị và tỷ lệ cải thiện

### 12.1. Một bộ số liệu minh họa

Giả sử đã đo **cùng một clean verification workload**, cùng runner/JDK/cache condition, năm lượt hợp lệ mỗi cấu hình:

| Run | Baseline (giây) | Candidate (giây) |
| --- | ---: | ---: |
| 1 | 120 | 94 |
| 2 | 123 | 96 |
| 3 | 118 | 97 |
| 4 | 121 | 95 |
| 5 | 120 | 98 |
| **Median** | **120** | **96** |

Bộ số trên là **dữ liệu giả định để học cách xử lý**, không phải benchmark thật của Maven hay Gradle.

Sau sắp xếp:

~~~text
Baseline: 118, 120, 120, 121, 123 -> median = 120 s
Candidate: 94, 95, 96, 97, 98   -> median = 96 s
~~~

Phần trăm giảm thời gian:

~~~text
Improvement = (T_baseline - T_candidate) / T_baseline * 100%
            = (120 - 96) / 120 * 100%
            = 20%
~~~

Tức candidate giảm **24 giây** trên một lượt build tiêu biểu và **20%** so với trung vị baseline. **Không** được trình bày rằng build nhanh hơn 24% chỉ bằng cách lấy 24/96; mẫu số cho chỉ số “giảm thời gian so với baseline” là **120**.

Nếu candidate có trung vị **130 giây** trong khi baseline **120 giây**, thay vào công thức cho giá trị âm (regression). Một cải thiện nhỏ hơn độ biến thiên nền cần lấy nhiều mẫu và kiểm tra nguồn nhiễu trước khi chốt.

### 12.2. Java 17: chương trình tính median từ số đo

Tạo file độc lập **BuildTimingStats.java** ngoài ứng dụng Spring Boot hoặc trong một thư mục công cụ riêng:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class BuildTimingStats {
    private BuildTimingStats() {
    }

    public static void main(String[] args) {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "Provide one or more durations in seconds");
        }

        double[] durations = Arrays.stream(args)
                .mapToDouble(Double::parseDouble)
                .sorted()
                .toArray();

        for (double duration : durations) {
            if (!Double.isFinite(duration) || duration < 0) {
                throw new IllegalArgumentException(
                        "Durations must be finite and non-negative");
            }
        }

        int n = durations.length;
        double median = n % 2 == 1
                ? durations[n / 2]
                : (durations[n / 2 - 1] + durations[n / 2]) / 2.0;

        System.out.printf(
                Locale.US,
                "n=%d min=%.1f s median=%.1f s max=%.1f s%n",
                n, durations[0], median, durations[n - 1]);
    }
}
~~~

Biên dịch/chạy với Java 17:

~~~bash
javac --release 17 BuildTimingStats.java
java BuildTimingStats 120 123 118 121 120
java BuildTimingStats 94 96 97 95 98
~~~

Stdout chính xác của hai lệnh **java** (không tính stdout của lệnh javac khi compile thành công):

~~~text
n=5 min=118.0 s median=120.0 s max=123.0 s
n=5 min=94.0 s median=96.0 s max=98.0 s
~~~

Code dùng **Double.parseDouble** nên đầu vào phải là số thập phân dạng dấu chấm (ví dụ **42.5**). Nó sắp xếp mẫu và lấy median; **không tự thu thập thời gian build**, không bỏ outliers tùy tiện, không tính confidence intervals, và không được xem năm mẫu là một phép đo p95 chính xác.

### 12.3. Vì sao median thường hữu ích?

Nếu bốn lần build mất 40–42 giây nhưng một lần mất 180 giây vì antivirus hoặc download mạng, **mean** có thể bị kéo lệch đáng kể. **Median** cho cái nhìn tốt hơn về trải nghiệm điển hình. Tuy nhiên, lần 180 giây có thể là tình huống rất thật của CI; không nên xóa nó khỏi dữ liệu, mà cần điều tra và mô tả **tail latency** riêng.

Không vì median đẹp mà bỏ qua:
- Build failures/flaky tests.
- Spike do repository outage.
- Performance regressions trên runner cấu hình yếu hơn.
- Chi phí tăng CPU/RAM của phương án nhanh hơn.

## 13. Một quy trình A/B cho thay đổi tối ưu

### Bước 1. Định nghĩa workload bất biến

Ví dụ muốn tăng tốc CI pull-request verification:

~~~text
Tool: Gradle Wrapper 8.14, JDK 17
Command: ./gradlew --console=plain clean build
Scope: toàn bộ project, cùng test suite
Runner: cùng machine type, CPU/RAM/container limits
Caches: build cache OFF, configuration cache OFF
Result: chỉ nhận BUILD SUCCESSFUL và test report hợp lệ
~~~

Lệnh/flags và điều kiện thực tế phải được ghi trong baseline. Đây là **thông số ví dụ**, không phải đề xuất tắt cache trên mọi CI. Nếu CI hiện tại có caches, hãy **đo baseline theo đúng trạng thái CI thực tế** và dùng một test riêng có cache OFF khi cần cô lập nguyên nhân.

### Bước 2. Thu thập baseline

Chạy warm-up khi kịch bản yêu cầu rồi đo ít nhất năm lượt; lưu log và các task outcomes. Lấy median, min/max, số failures và report/profile.

### Bước 3. Phân tích bottleneck

Ví dụ trong Gradle --profile, thấy configuration mất 35 giây còn test task chỉ 10 giây. Giả thuyết có thể là build scripts/plugins config quá nặng; không nên tối ưu JUnit trước khi làm rõ nguyên nhân.

Với Maven, nếu log cuối build cho thấy tổng 120 giây nhưng không có breakdown chi tiết, thử **đo các phase** và phân tích test reports:
- Chạy **mvn test** để đo đến phase test.
- Chạy **mvn package** để đo đầy đủ cả packaging.
- Xem goals, annotation processors, các integration tests được bind thêm trong verify.
  
**Cẩn thận:** không lấy phép trừ thời gian **mvn package − mvn test** thành thời gian packaging chính xác khi hai command khác trạng thái cache, test execution khác nhau hoặc profile khác. Muốn profiling chuẩn, dùng công cụ bổ sung hoặc đo trong những điều kiện xác định.

### Bước 4. Thay đổi đúng một biến

Ví dụ chỉ bật **configuration cache**, hoặc chỉ sửa một Gradle plugin config tốn thời gian, hoặc chỉ tách integration-test suite khỏi dev-loop (nếu mục tiêu thay đổi chính sách test được phê duyệt). Không cùng lúc tăng RAM, đổi JDK, nâng Boot và bật cache rồi cố gắng gán hiệu quả cho một yếu tố.

### Bước 5. Thu mẫu candidate

Đảm bảo same commit/source workload về mặt ngữ nghĩa, cùng phần cứng và biến điều kiện chỉ khác đúng lựa chọn tối ưu. Với benchmark cache, cần quy định rõ lần cold fill cache và lần warm hit; báo cáo hai con số khác nhau.

### Bước 6. So sánh median và kiểm tra correctness

Một candidate chỉ hợp lệ khi:
- Command still verifies cùng tập tests/quality checks.
- Test summary, archive và runtime behavior không thua baseline.
- Không phát sinh flaky tests, race conditions hoặc invalidated caches khó dự đoán.
- Có chênh lệch đủ lớn và ổn định để vượt noise.

Nếu ứng dụng tạo JAR nhanh hơn nhưng bỏ **test** và làm CI release mất bước verify, đó là **phạm vi công việc nhỏ đi**, không phải cải thiện hiệu năng cho cùng yêu cầu.

### Bước 7. Quyết định rollout hay rollback

Ghi mô tả thay đổi, các mẫu thời gian, median, rủi ro và cách rollback. Nếu không quan sát được cải thiện ổn định, có thể **không** đưa thay đổi vào mainline ngay cả khi nghe hợp lý về mặt lý thuyết.

## 14. Bản đồ chẩn đoán theo phần tốn thời gian

| Dữ liệu quan sát | Giả thuyết ưu tiên kiểm tra | Hướng điều tra trước tối ưu |
| --- | --- | --- |
| Fresh build lâu, warm build nhanh | Download dependencies, wrapper distribution, network | Mirror/repositories, proxy, cache policy của CI |
| Mọi build đều lâu trước khi task chạy | JVM/daemon startup, init/configuration | Gradle --profile, startup/configuration breakdown, plugins |
| Không đổi source mà Gradle vẫn execute nhiều tasks | Inputs/outputs không ổn định, custom task thiếu declarations | UP-TO-DATE details, task inputs/outputs |
| Gradle FROM-CACHE hiếm dù cùng inputs | Cache key khác, env path, plugin cacheability | Build Scan/caching report, task metadata |
| compileJava chiếm nhiều thời gian | Nhiều source, annotation processors, invalidation | Task profiling, annotation processor config, ABI changes |
| processResources chậm bất thường | Copy/filter quá nhiều files, input glob sai | Resource includes/excludes, filtering, file count |
| Unit tests chiếm phần lớn wall time | Context initialization, test fixtures, DB/network, sequential work | Surefire/Gradle reports, test isolation/parallel options |
| Packaging JAR/WAR chậm | Nhiều/khổng lồ dependencies, compression, layers/index | Artifact size, bootJar/repackage, file I/O |
| Build CPU thấp nhưng wall time cao | I/O, network, locks hoặc chờ external service | OS monitoring, network metrics, CI logs |
| Build CPU/RAM quá cao, máy swap | Quá nhiều workers/forks/daemons, heap không cân đối | Memory, GC, worker counts, container limits |
| Multi-module build chỉ sửa 1 module mà rebuild tất cả | Task dependencies, inter-module ABI, thiếu incremental path | Maven reactor selection, Gradle project graph |
| Developer build nhanh nhưng CI chậm | Fresh runners, remote cache miss, security scans, constrained CPU | So cùng runner, tách build tool time và CI overhead |

**Đây là danh sách giả thuyết**, không phải kết luận được phép đưa ra chỉ từ một dòng log. Dữ liệu phải xác nhận giai đoạn nào gây tốn thời gian và tại sao.

### 14.1. Nếu bottleneck nằm ở dependency download

Cân nhắc repository manager/mirror gần CI, version pinning, policy cache và việc giảm dynamic SNAPSHOT resolution. Không xóa caches mỗi build vì sợ lỗi dependency mà chưa có bằng chứng. Tránh dùng **--offline** chỉ để tạo số đẹp nếu production CI cần cập nhật dependencies/certificate metadata theo chính sách.

### 14.2. Nếu bottleneck nằm ở Gradle configuration

Xem plugins áp dụng cho root/subprojects, eager task configuration, reading files/network ở configuration phase và khả năng tương thích configuration cache. **--configuration-cache** có thể cải thiện no-change dev loop nhưng cần báo cáo riêng **first store** và **cache reuse**. Không bật cấu hình cache rồi bỏ qua warnings/incompatibilities trong production.

### 14.3. Nếu bottleneck nằm ở compile/code generation

Quan sát số files cần compile và annotation processor behavior. Code generator tạo nhiều source hoặc đọc rộng hơn đầu vào cần thiết có thể làm incremental build mất hiệu quả. Với Gradle, cấu hình task inputs/outputs và cacheability đúng có thể giảm repeated work. Với Maven, phân tích plugins, modules và compiler options; không chọn **skip compilation** như một tối ưu chức năng.

### 14.4. Nếu bottleneck nằm ở tests

Đếm số tests, execution time từng suite, số lần khởi tạo Spring ApplicationContext, dùng database containers/external services và test isolation. Trong Spring Boot, khởi tạo nhiều Spring contexts khác nhau có thể tốn chi phí đáng kể; cân nhắc giảm số biến thể cấu hình test khi hợp lý.

Nếu muốn chạy tests song song, đánh giá dữ liệu chung, cổng mạng, transaction, external resources và khả năng flaky. **Bỏ test hoàn toàn** là giảm phạm vi kiểm chứng, không thể gọi là tối ưu cùng workload.

### 14.5. Nếu bottleneck nằm ở archive packaging

Kiểm tra loại artifact thực tế: Maven **spring-boot:repackage**, Gradle **bootJar**, JAR vs WAR, compression, snapshot dependencies và artifact upload trong CI. Các bước scan ký số hoặc upload image có thể nằm **ngoài build tool command**; phải xác định bạn đang đo **build tool** hay **entire CI job** trước khi tối ưu.

## 15. Đo theo module và command đúng trong multi-project build

Một repo Spring Boot nhiều module có thể có **application**, **common**, **data** và **integration-tests**. Hai yêu cầu khác nhau:

- **Full reactor/build**: tất cả modules trong phạm vi CI.
- **Targeted developer build**: chỉ application module và các dependencies cần thiết.

### 15.1. Maven reactor

Ví dụ module **app** tồn tại:

~~~bash
./mvnw -B -ntp clean verify
./mvnw -B -ntp -pl app -am verify
~~~

**-pl app** chọn module, **-am** build các reactor projects mà app cần. Đây không phải phép đo A/B của cùng workload nếu tập modules thay đổi. Nhưng nó giúp tạo hai **mục tiêu benchmark riêng**: thời gian CI toàn repo và thời gian phản hồi khi dev ở app.

Nếu muốn so chính sách parallel reactor, có thể nghiên cứu Maven **-T** (ví dụ **-T 1C**) sau khi xác định bottleneck và kiểm tra plugin thread safety. **-T** không luôn nhanh hơn: CPU/RAM/IO contention và plugins không thread-safe có thể gây lỗi hoặc chậm. Benchmark theo đúng reactor, same tests và same runner.

### 15.2. Gradle multi-project

~~~bash
./gradlew --console=plain build
./gradlew --console=plain :app:build
./gradlew --console=plain :app:bootJar
~~~

Giả định **:app** tồn tại. Lệnh **:app:build** có thể kéo theo tasks ở các project dependencies; **:app:bootJar** tập trung packaging và không mặc nhiên chạy task **:app:test**. Chúng đo **phạm vi khác nhau**; chỉ so thời gian bên trong cùng mục tiêu.

Một build multi-module có thể hưởng lợi từ **--parallel** khi task graph có đủ công việc độc lập và máy có tài nguyên; hãy đo CPU/RAM pressure và correctness khi bật. Với CPU bị giới hạn 2 cores trong container, đặt worker count cao có thể làm chậm.

## 16. Khi số liệu khác nhau phải điều tra điều gì?

### 16.1. Một lần build bất thường chậm

Các lý do: tải file mới, DNS chậm, Maven repository đang lag, antivirus scan, Gradle daemon mới, JIT warm-up, GC pause, ổ đĩa bận, CI agent bị tranh chấp, test chờ database, timeout. Đừng xóa mẫu vì nó “xấu”; ghi nhận nguyên nhân nếu có, và tách “độ ổn định” khỏi “median speed”.

### 16.2. Chuyển nhánh làm cache invalidated

Thay đổi build.gradle, settings.gradle, pom.xml, JDK, compiler flags, annotation processor versions hoặc resource input có thể làm nhiều tasks rebuild. No-change build sau một lần chạy trên commit A **không so** trực tiếp với first build trên commit B nếu cache state khác nhau.

### 16.3. Tổng thời gian Maven khác Gradle

Có thể khác vì:
- Maven chạy đến **verify**, Gradle chỉ gọi **bootJar**.
- Surefire và Gradle JUnit Platform có test filters/suites khác nhau.
- Kết quả cache/up-to-date khác.
- Version of plugins hoặc dependency graph khác.
- Java toolchain, daemon và JVM memory khác.
  
Để so build tools, trước hết kiểm chứng **cùng behavior và artifacts**, xác định điều kiện cân bằng và lặp lại nhiều lần. Không so một command Maven với một task Gradle khác phạm vi rồi kết luận tool nào “nhanh hơn”.

### 16.4. Tổng thời gian của CI không bằng tổng build tool time

Một CI job có thể gồm checkout, restore cache, setup JDK, unit tests, Docker build, security scan, publish/upload, artifact signing và notifications. Dùng hệ thống metrics của CI để đo **job wall time** và từng step. Nếu Maven Total time là 35 giây nhưng CI job mất 7 phút, phải phân tích những bước **ngoài Maven** trước khi sửa Maven compiler.

## 17. Một mẫu báo cáo đo lường có thể tái sử dụng

~~~text
Build Performance Baseline
Project/commit: build-timing-lab / <commit-hash>
Goal: CI verification latency (tests must run)
Tool: Gradle Wrapper 8.14 + Spring Boot Gradle Plugin 3.5.16
JDK: 17
Runner: Linux 4 vCPU, 8 GiB RAM, same runner class
Command: ./gradlew --console=plain clean build
Cache state: dependency cache warm, build cache disabled,
             configuration cache disabled, daemon state controlled
Sample method: 1 warm-up + 5 measured runs
Success criteria: BUILD SUCCESSFUL + required tests passed
Baseline durations (s): 120, 123, 118, 121, 120
Candidate durations (s): 94, 96, 97, 95, 98
Median baseline: 120.0 s
Median candidate: 96.0 s
Difference: -24.0 s / -20.0%
Observed bottleneck: [fill using actual profile]
Single candidate change: [identify one config change]
Correctness validation: [test reports, artifacts, smoke check]
Recommendation: [ship / rerun with more samples / rollback]
~~~

**Các con số/tên máy/nhận định trong khối trên là một báo cáo mẫu giả định**, không phải kết quả đo thật. Khi áp dụng, thay placeholders bằng dữ liệu xác minh được; không in kết luận “cải thiện 20%” nếu chưa có các lần build hợp lệ.

**Không lưu credentials, access tokens, private repository URLs có tham số nhạy cảm hoặc full environment dumps không được phép trong log/scan công khai.**

### Quyết định dựa vào chi phí/lợi ích

Nếu CI chạy 15 lượt/ngày và mỗi lượt tiết kiệm 24 giây, thời gian build wall-clock tiết kiệm tổng cộng **360 giây (6 phút)** mỗi ngày cho những lượt đó. Với nhiều CI jobs chạy song song, điều này không tự tương đương 6 phút wall-clock ngắn hơn cho toàn đội; cần xét số runner slots, queueing và critical path.

Một tối ưu tốn nhiều ngày bảo trì mà chỉ giảm 1–2 giây không ổn định có thể kém ưu tiên hơn sửa một bước download dependency bất thường mất 90 giây. Ngoài tốc độ, cần tính chi phí tài nguyên và rủi ro correctness.

## 18. Sai lầm phổ biến khi đo thời gian build

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| So lần đầu tải dependencies với lần thứ hai đã warm | Khác điều kiện | Ghi cold/warm và so tương ứng |
| Gọi mọi **clean** là cold | Clean không xóa Maven/Gradle dependency cache | Ghi rõ output/cache state |
| So **verify** có tests với **package -DskipTests** | Khác test workload | Giữ nguyên test commands/flags |
| So **gradle build** với **gradle bootJar** | Khác task graph | So cùng task set hoặc báo hai mục tiêu |
| Dùng **--dry-run** làm số đo compile time | Không chạy task actions | Chạy build thật |
| Chỉ đo một lần rồi chốt | Dễ nhiễu | Nhiều samples, median và spread |
| Bỏ những mẫu chậm mà không điều tra | Che tail latency | Giữ lại và ghi nguyên nhân nếu rõ |
| Bật cache rồi tuyên bố compiler nhanh hơn | Có thể không compile | Phân tích UP-TO-DATE/FROM-CACHE |
| Tổng các Gradle task durations thành wall time | Tasks có thể chạy song song | Đo stopwatch và xem critical path |
| So hai developer laptops khác nhau | CPU/JDK/disk/network khác | Dùng cùng CI runner hoặc môi trường chuẩn |
| Tăng heap/số workers không kiểm RAM | Có thể swap/contend | Đo memory/GC và kiểm correctness |
| Đổi nhiều knobs cùng lúc | Không xác định nguyên nhân | Một thay đổi một vòng A/B |
| Đo build tool nhưng kết luận toàn CI nhanh hơn | Có nhiều CI steps ngoài build tool | Đo cả CI job/critical path |
| Chỉ xem BUILD SUCCESSFUL | Có thể tests skip hoặc report cũ | Xem task outcomes/test reports hiện tại |
| Dùng Maven CLI Total time cho mọi phân đoạn | Chỉ là tổng build | Profiler/instrumentation/phase analysis phù hợp |

## 19. Checklist kiểm tra trước khi chọn hướng tối ưu

- [ ] Đã định nghĩa kịch bản cụ thể: fresh, clean, warm no-change hoặc incremental change.
- [ ] Dùng đúng Maven Wrapper/Gradle Wrapper và JDK version cho cả baseline và candidate.
- [ ] Giữ cùng commit/build inputs hoặc ghi rõ thay đổi duy nhất được đánh giá.
- [ ] Giữ cùng test suite, profiles, quality gates và package tasks.
- [ ] Ghi lại CPU, RAM, OS, disk, mạng, runner type và resource limits.
- [ ] Ghi rõ Maven local repo/Gradle dependency cache, daemon, build cache, configuration cache.
- [ ] Dùng external stopwatch để có wall time; với Maven đọc **Total time**, với Gradle xem **--profile** và task outcomes.
- [ ] Nếu dùng Build Scan, đã được phê duyệt chính sách chia sẻ metadata.
- [ ] Đã có ít nhất vài mẫu hợp lệ; phân biệt lượt warm-up với samples.
- [ ] Tính median và mức dao động, không chọn duy nhất mẫu nhanh nhất.
- [ ] Không lẫn clean build với cold dependencies hoặc rerun tasks với fresh runner.
- [ ] Đã xác định bottleneck trước khi thay build.gradle, pom.xml hay CI.
- [ ] Thay một biến có giả thuyết rõ; đo A/B và kiểm tra test reports/artifacts.
- [ ] Ghi nhận regressions, flaky tests, RAM/CPU pressure và khả năng rollback.
- [ ] Có báo cáo về wall-time change, mức chắc chắn và tác động thực tế lên developer/CI.
- [ ] Không bật/tắt skipTests, -x test hoặc tắt security checks chỉ để làm số đo đẹp.

## 20. Câu hỏi tự đánh giá

**Câu 1.** Chạy Maven clean verify hai lần, lần thứ hai nhanh hơn. Có đủ bằng chứng Maven compiler đã tối ưu không?

**Trả lời:** Chưa. Maven local repository/plugins có thể đã được tải đầy đủ. Phải xem goal execution, compile logs, test counts và dependency/cache state. Clean không xóa dependency cache.

**Câu 2.** Gradle báo **:compileJava UP-TO-DATE**. Có thể kết luận Java compiler rất nhanh không?

**Trả lời:** Không. Gradle có thể đã bỏ chạy compile action nhờ input/output checks. Muốn đo compiler thật, cần scenario có công việc compile, hoặc sử dụng --rerun-tasks theo thiết kế benchmark.

**Câu 3.** Dùng **./gradlew build --dry-run** để đo thời gian test có hợp lệ không?

**Trả lời:** Không. Nó lập task plan nhưng không thực thi test actions. Cần build/test thật và xem test report/task outcome.

**Câu 4.** Maven **-DskipTests** có tính là tăng hiệu năng build với cùng chất lượng không?

**Trả lời:** Không. Nó giảm phạm vi xác minh vì Surefire không chạy unit tests. Hãy đo riêng use case package nhanh và giữ CI verification đầy đủ.

**Câu 5.** Tại sao tổng task time của một Gradle build có thể lớn hơn stopwatch wall time?

**Trả lời:** Tasks có thể chạy song song. Tổng durations là tổng công của nhiều tasks; wall time phụ thuộc critical path và thời gian thực tế từ start tới finish.

**Câu 6.** Bật --scan có gì cần lưu ý?

**Trả lời:** Build Scan thường publish metadata build tới dịch vụ được cấu hình; có thể có thông tin project/máy/paths. Cần chính sách cho phép. Nếu chỉ cần profile trên máy, dùng --profile.

**Câu 7.** Với baseline median 120 giây và candidate 96 giây, giảm bao nhiêu phần trăm?

**Trả lời:** (120 − 96) / 120 × 100% = **20%**, tiết kiệm **24 giây** trên median build.

**Câu 8.** Vì sao không so CI **build** với developer **bootJar**?

**Trả lời:** bootJar có thể không chạy tests/quality checks mà CI build chạy. Phải so cùng workload hoặc báo hai mục tiêu hiệu năng độc lập.

**Câu 9.** Configuration cache và build cache giống nhau không?

**Trả lời:** Không. Configuration cache tái sử dụng kết quả configuration phase; build cache tái sử dụng output các tasks có cache key phù hợp. Dependency cache lại lưu dependencies/plugins đã tải.

**Câu 10.** Khi nào nên chọn thay đổi kỹ thuật?

**Trả lời:** Khi một bottleneck được quan sát bằng profile/log, có giả thuyết giải thích vì sao thay đổi giúp, kết quả A/B ổn định qua nhiều mẫu, correctness giữ nguyên và lợi ích xứng đáng với rủi ro/chi phí.

## 21. Tổng kết

Một bản dựng Spring Boot nên được tối ưu theo vòng lặp:

~~~text
Định nghĩa workload / success criteria
                 |
                 v
Ghi môi trường + cache state
                 |
                 v
Thu nhiều mẫu wall time
                 |
                 v
Maven log / Gradle --profile / approved scan
                 |
                 v
Xác định bottleneck và critical path
                 |
                 v
Đưa ra một giả thuyết tối ưu
                 |
                 v
Thay một biến + đo A/B
                 |
                 v
So median, spread, test correctness
                 |
                 v
Rollout hoặc rollback có bằng chứng
~~~

**Không tối ưu theo cảm giác.** Một lần no-change build nhanh không chứng minh clean/CI build nhanh; việc skip tests không làm compiler nhanh hơn; một Build Scan đẹp không thay thế được kiểm chứng ứng dụng. Đo **thời gian đúng loại công việc**, biết **vì sao chậm** và so sánh **trước/sau với điều kiện tương đương** mới giúp đầu tư đúng vào cache, dependencies, compilation, tests, packaging hoặc CI infrastructure.

## 22. Tài liệu tham khảo chính thức

- Gradle — Build Scan và local profile (--profile): https://docs.gradle.org/current/userguide/inspect.html
- Gradle — Build Scan Basics, dữ liệu và điều kiện publish: https://docs.gradle.org/current/userguide/build_scans.html
- Gradle — Performance guide: https://docs.gradle.org/current/userguide/performance.html
- Gradle — Command-line options: https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle — Java Testing: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Gradle Profiler (scenarios, warm-up, profiling): https://github.com/gradle/gradle-profiler
- Apache Maven — Maven Getting Started (Total time, first dependency downloads): https://maven.apache.org/guides/getting-started/
- Apache Maven — CLI Options (-B, -ntp, -pl, -am, -T): https://maven.apache.org/ref/3-LATEST/maven-embedder/cli.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Build Cache Extension (opt-in): https://maven.apache.org/extensions/maven-build-cache-extension/
- Spring Boot — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Spring Boot — Gradle Plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/
- Spring Boot 3.5.16 release announcement: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

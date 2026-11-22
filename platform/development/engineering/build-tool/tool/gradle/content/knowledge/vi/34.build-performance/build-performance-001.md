# Đo baseline và tách thời gian khởi động, cấu hình, thực thi trong Gradle

## Mục tiêu bài học

Khi một Gradle build “chậm”, câu hỏi đầu tiên không phải “bật thêm cache nào?” mà là **chậm ở đâu, so với đường chuẩn nào, trong điều kiện nào?** Một lệnh **./gradlew build** có thể mất thời gian để khởi động JVM/Gradle Daemon, đọc settings và build logic, cấu hình projects, phân giải dependencies, rồi thực thi tasks. Độ trễ mà developer thấy còn có thể bao gồm tải Gradle Wrapper, download dependencies, kết nối daemon hoặc chờ hệ điều hành cấp CPU/I/O. Nếu không đo trước, rất dễ tối ưu nhầm giai đoạn.

Chủ đề **Hiệu năng build** này tập trung vào cách **thiết lập baseline có thể tái lập**, phân biệt **startup, initialization/settings, configuration, task execution** và đọc số đo đúng. Các ví dụ minh họa với **Gradle Java 17** nhưng phương pháp có thể áp dụng cho Kotlin/Android/Groovy và multi-project builds với workload tương ứng.

Sau bài học, bạn có thể:

1. Định nghĩa baseline có đầy đủ **task, commit, Gradle Wrapper, JDK, máy, OS, flags, cache/daemon state, nguồn dữ liệu và thống kê**.
2. Phân biệt **wall-clock time** của toàn lệnh và thời gian từng phase/task; tránh cộng chồng các task durations chạy song song.
3. Dùng **--profile** để tạo báo cáo HTML cục bộ và **--scan** khi muốn timeline, configuration breakdown, dependency resolution và cache insights chi tiết.
4. Phân biệt **cold daemon/warm daemon**, **cold outputs/warm outputs**, **build cache**, **configuration cache**, **dependency cache** và “clean build”.
5. Thiết kế ba workload chính: **no-op build**, **incremental build sau sửa nhỏ** và **clean/full rebuild**.
6. Dùng **help** làm tín hiệu tham khảo cho configuration overhead nhưng không biến nó thành phương pháp trừ số cơ học.
7. Chạy một lab Java 17 có **:core** và **:app** và xác minh ứng dụng in đúng kết quả.
8. Tạo benchmark runner độc lập bằng **Java 17 ProcessBuilder + System.nanoTime** để thu nhiều wall-time samples.
9. Tính **min, median, p90, mean**, thay đổi tương đối và speedup; biết cách nhận diện noise, outliers, thiếu warm-up.
10. Phân biệt benchmark không instrumentation và một lượt profiling có instrumentation overhead.
11. Dùng **Gradle Profiler** cho kịch bản/warm-up/iterations chuyên nghiệp và so sánh trước–sau.
12. Áp dụng các biện pháp tối ưu đúng phase: daemon, configuration avoidance, dependency resolution, cache, incremental tasks và parallelism.
13. Thiết kế báo cáo baseline cho CI/team, có giới hạn về tính riêng tư của Build Scan.
14. Tránh các kết luận sai như “Gradle build tasks cộng lại mất 40 giây nên tổng build phải 40 giây” hoặc “UP-TO-DATE chứng minh build cache đã hit”.

**Nguyên tắc xuyên suốt:** **Đo cùng workload, giữ các điều kiện khác như nhau, lấy nhiều mẫu, xem phases rồi mới thay một biến.**

Ví dụ dùng **Groovy DSL**, có Kotlin DSL và lệnh Unix/PowerShell. Để chạy mã Java, cần **JDK 17** và **Gradle Wrapper hỗ trợ Java 17**. Lab dùng các plugin tích hợp Gradle, không cần dependency Java từ Maven Central. Wrapper cần distribution đã có sẵn hoặc được tải lần đầu.

---

## 1. Baseline hiệu năng là gì?

Một **performance baseline** là bộ quan sát được ghi lại **trước khi** áp dụng thay đổi tối ưu, để làm mốc so sánh. Nó không chỉ là một số “build 12 giây”, mà là toàn bộ ngữ cảnh khiến số đó có ý nghĩa.

Ví dụ một baseline đúng dạng:

~~~text
Scenario: local-no-op-assemble
Git commit: a1b2c3d (minh họa)
Task: :app:assemble
Gradle: Wrapper version được pin trong gradle-wrapper.properties
JDK: 17, Java home được ghi nhận
Machine: 8 logical CPU, RAM 16 GiB, SSD
Environment: Linux x86_64, developer laptop cắm điện
Daemon: warm compatible daemon
Configuration cache: OFF
Build cache: OFF
Task outputs: already built, expected UP-TO-DATE
Dependency artifacts: warmed
Warm-ups: 3 (not counted)
Samples: 10
Metric: external wall-clock elapsed milliseconds
Statistic: median and p90
~~~

Các giá trị commit, số CPU/RAM và sample count ở trên chỉ là **ví dụ định dạng**, không phải số đo từ máy người học.

### 1.1. Vì sao cần ghi workload?

**./gradlew help** và **./gradlew :app:assemble** làm hai công việc khác nhau. **./gradlew clean build** và **./gradlew build** cũng khác; một lệnh có cache hits còn lệnh kia không chưa chắc tương đương.

Hãy xác định câu hỏi trước:

| Câu hỏi thực tế | Workload nên đo |
| --- | --- |
| Mở terminal và gọi Gradle có chậm? | **help** hoặc một task nhỏ, cold/warm daemon riêng |
| Mọi lệnh đều mất vài giây dù không có thay đổi? | **no-op :app:assemble**, xem startup/configuration |
| Sửa một class rồi compile có chậm? | Sửa file có kiểm soát + **:app:compileJava** |
| CI phải biên dịch lại từ checkout sạch mất bao lâu? | Clean build trên CI với cùng daemon/cache policy |
| Tests lâu? | **:app:test** hoặc suite thực tế, có test count cố định |
| Dependency resolution chậm? | Build Scan dependency resolution và network/caches state |
| Release artifact chậm? | Task thật dùng trong pipeline (assemble/shadowJar/publish) với side effects kiểm soát |

Một benchmark của **help** không thể đại diện toàn bộ thời gian test/compile, nhưng giúp định vị chi phí trước task execution.

### 1.2. Những thứ phải cố định

Khi so sánh before/after, cố định:
- **Git commit/source tree** nếu bạn đang đo đổi Gradle flag hoặc plugin.
- **Gradle Wrapper** và phân phối Gradle.
- **JDK chạy daemon**, toolchain Java/Kotlin, JVM args và heap.
- **Số workers/parallel mode**.
- **Build cache/configuration cache flags** và cache state.
- **Task selector** đúng tên, arguments và system/project properties.
- **OS/CPU/RAM/disk**, tải hệ thống và network state.
- **Chế độ daemon warm/cold**, thứ tự chạy A/B.
- **Repositories** và trạng thái dependencies offline/online.

Nếu điều kiện thay đổi, ghi nhận sự khác biệt. Không tự đặt kết luận rằng hiệu năng tốt hơn nhờ plugin chỉ vì đo sau khi dependency download đã xong.

### 1.3. Mục tiêu của baseline

Một baseline tốt trả lời được:
- **Total wall time** là bao nhiêu?
- **Startup** chiếm bao nhiêu?
- **Settings/buildSrc/project configuration** chiếm bao nhiêu?
- **Task execution timeline** có những tasks chậm nào?
- **Dependency resolution** xảy ra ở configuration hay execution?
- **UP-TO-DATE/FROM-CACHE/NO-SOURCE/EXECUTED** có tỷ lệ thế nào?
- **Median/p90** có ổn định trong nhiều lần chạy không?
- Có cải thiện đáng kể khi thay đổi một yếu tố không?

---

## 2. Những mốc thời gian trong một Gradle build

Gradle có mô hình ba pha cơ bản **initialization → configuration → execution**, nhưng trong báo cáo hiệu năng chi tiết còn tách nhỏ **startup, settings/buildSrc, loading projects, configuring projects, dependency resolution, tasks**.

~~~text
Người dùng chạy ./gradlew :app:assemble
       |
       v
Wrapper script / client JVM
       |
       +--> (lần đầu) kiểm tra/tải Gradle distribution
       |
       v
Gradle startup / kết nối hoặc khởi động Daemon
       |
       v
Initialization: settings, build tree, init scripts, buildSrc
       |
       v
Configuration: plugins, build scripts, tasks, dependency graph
       |
       v
Task execution: compileJava -> classes -> jar -> assemble
       |
       v
Gradle trả exit code, process kết thúc
~~~

Sơ đồ **khái niệm**, không phải đảm bảo mọi hoạt động I/O hoặc dependency resolution được xếp vào một “hộp” duy nhất: một số dependency có thể resolve khi cấu hình, một số khi task thực thi; configuration cache có thể bỏ qua phần lớn cấu hình; Gradle có thể thực thi tasks song song.

### 2.1. Startup

Trong Build Scan/profile, startup có thể bao gồm:
- JVM initialization/class loading.
- Gradle Daemon startup nếu chưa có daemon tương thích.
- Wrapper distribution download trong lần đầu (nếu xảy ra).
- Init scripts hoặc các bước startup tương ứng.

**Lần chạy đầu tiên sau cài Gradle/JDK mới có thể chậm bất thường**. Không lấy số đó làm baseline warm daemon cho mọi ngày.

### 2.2. Initialization và settings/buildSrc

Gradle xác định **settings.gradle(.kts)**, projects được include, included builds và build logic. Tài liệu profiling có category **Settings and buildSrc** riêng; buildSrc build hoặc included plugin build ban đầu có thể tốn nhiều thời gian, các lần sau thường có up-to-date/caching behavior.

**Một settings plugin chạy I/O nặng** có thể làm hầu hết các commands chậm, kể cả **help**. Lúc này tối ưu compileJava chưa giải quyết gốc rễ.

### 2.3. Loading/configuring projects

Configuration xử lý build scripts, áp plugins, tạo/đăng ký tasks và lập task graph. Ví dụ vấn đề:
- Eager configuration tất cả tasks.
- Cross-project cấu hình nhiều modules không cần.
- Network call trong plugin apply.
- Resolve dependencies ngay khi đọc build.gradle.
- Đọc hàng nghìn files trong configuration.

Một **no-op build** có thể bị thống trị bởi configuration, dù không phải chạy compiler.

### 2.4. Dependency resolution

Dependency resolution có thể xảy ra:
- Trong configuration, đặc biệt nếu build script gọi configurations.compileClasspath.files sớm.
- Ở execution hoặc thời điểm Gradle cần artifact inputs.
- Khi configuration cache được lưu/khôi phục, semantics thay đổi theo Gradle version.

**Không coi dependency resolution như một pha thứ tư được cộng cứng vào wall time**: nó có thể lồng vào các giai đoạn khác. Build Scan giúp nhận diện nó nằm ở đâu.

### 2.5. Task execution

Task execution bao gồm:
- Compile code.
- Process resources.
- Run unit/integration tests.
- Generate source/report/artifacts.
- Restore outputs từ build cache, hoặc skip tasks UP-TO-DATE.
- Các task actions/custom tools.

**Không đồng nhất task graph “có 50 tasks” với “50 tasks thực sự chạy”**. Lifecycle tasks như assemble có thể chỉ phụ thuộc các tasks khác và không có action đáng kể.

### 2.6. Tại sao wall time không luôn bằng tổng các durations?

Với parallel task execution, hai tasks có thể chạy **đồng thời**:

~~~text
Time: 0s      2s      4s      6s
Task A: [===========4s===========]
Task B:       [=======3s=======]
Total elapsed from A start to B end: 5s
Sum durations A + B: 7s
~~~

Nếu một dashboard báo tổng durations là 7 giây, nó **không chứng minh** tổng build mất 7 giây; ở ví dụ elapsed chỉ 5 giây. Trong đời thực còn startup, configuration, daemon idle, artifact transforms và nhiều tiến trình khác.

**Quy tắc:** chỉ dùng **external wall clock** hoặc “total build elapsed” theo định nghĩa profiler cho thời gian thực người dùng chờ. **Sum task durations** giúp tìm khối lượng công việc, không thay wall-clock.

### 2.7. Critical path quan trọng hơn tasks cộng dồn

Giảm 3 giây của một task chạy song song với task khác kéo dài hơn 10 giây có thể **không giảm total wall time**. Tối ưu những tasks nằm trên **critical path** thường có tác động tới perceived duration hơn. Timeline trong Build Scan hữu ích hơn bảng xếp hạng tổng durations nếu build có parallel execution.

---

## 3. Đo wall-clock, profile và Build Scan: ba lớp đo khác nhau

| Công cụ/cách đo | Đo gì | Khi nào dùng | Giới hạn |
| --- | --- | --- | --- |
| **External wall-clock timer** | Từ lúc start process đến exit | So sánh tác động tổng thể | Không tự biết phase nào chậm |
| **Gradle --profile** | HTML category breakdown | Điều tra cục bộ, không muốn publish dữ liệu | Ít chi tiết hơn Build Scan; có measurement overhead |
| **Gradle --scan / Build Scan** | Performance timeline/config/dependency resolution/task details | Phân tích sâu và chia sẻ giữa team khi được phép | Có thể publish dữ liệu build ra dịch vụ ngoài; phải kiểm tra policy |
| **Gradle Profiler** | Nhiều lần benchmark, scenario/warmup, profiling | Đo nghiêm túc trước–sau trên workload được kiểm soát | Là một công cụ riêng cần cài đặt và setup |
| **JFR/async-profiler** | JVM methods/CPU/allocation level | Xác định bottleneck code/plugin cụ thể | Chi phí instrumentation; không thay baseline wall-time |

### 3.1. External wall-clock gồm gì?

Nếu bạn dùng một Java ProcessBuilder để chạy **./gradlew**, thời gian tính từ trước **ProcessBuilder.start()** đến sau **waitFor()** thường bao gồm:
- Launch shell/Wrapper client.
- Mở/kết nối Daemon hoặc tạo single-use Daemon.
- Cấu hình và task execution.
- Phần overhead trước khi process thoát.

Nó có thể khác “BUILD SUCCESSFUL in 2s” mà Gradle tự báo vì **điểm bắt đầu/kết thúc đo không giống nhau**, và vì thời gian tải Wrapper distribution hoặc process creation có thể nằm ngoài bộ đo nội bộ của Gradle.

### 3.2. Đừng đo bằng System.currentTimeMillis trong task rồi gọi tổng build

Nếu bạn đặt timeStart tại **doFirst** của compileJava và timeEnd tại doLast, bạn chỉ đo một phần task; startup/configuration xảy ra trước đó, còn task khác có thể chạy song song.

Muốn đo toàn lời gọi CLI thì timer nằm **bên ngoài Gradle process**. Muốn phân tích phases thì dùng **--profile/Build Scan**, không đo bằng một task marker rồi lấy hiệu giữa hai timestamps.

---

## 4. Dùng --profile để tách các giai đoạn

Gradle CLI hỗ trợ:

~~~bash
./gradlew :app:assemble --profile
~~~

Sau khi build hoàn tất, Gradle tạo **HTML profile report** trong **build/reports/profile/** ở root project (trừ khi project đã tùy chỉnh reporting location). Tên file thường chứa timestamp để tránh ghi đè.

### 4.1. Các nhóm thường thấy

Theo Gradle Profiling docs, nhóm gồm:
- **Startup**.
- **Settings and buildSrc**.
- **Loading projects**.
- **Configuring projects**.
- **Task execution**.

Tùy Gradle version, report có các nhóm con và cách bố trí khác nhau. Đây là **breakdown cấp cao**; số liệu Build Scan thường chi tiết hơn.

### 4.2. Chạy riêng một build nhẹ

~~~bash
./gradlew help --profile --console=plain
~~~

**help** là một task nhẹ, hữu ích để lộ startup/configuration overhead. Nếu help đã mất phần lớn thời gian, hãy xem settings, buildSrc, plugins, dependency resolution lúc configuration thay vì vội tối ưu Java compiler.

**Không lấy time(help) trừ time(assemble) rồi kết luận đó chính xác là execution time**: hai invocations có thể khác daemon/caches, task graph, lazy configuration, artifact resolution và profiling overhead.

### 4.3. Chạy workload có thực thi

~~~bash
./gradlew :app:assemble --profile --console=plain
~~~

Trong report, xem:
1. Startup.
2. Settings/buildSrc.
3. Loading/configuring projects.
4. Task execution: tasks nào thực thi, UP-TO-DATE hay bỏ qua.
5. Thời gian total build và điều kiện daemon/caches.

### 4.4. Chỉ đo clean khi định nghĩa rõ clean

Trong multi-project lab, muốn xóa outputs của cả :core và :app rồi compile lại:

~~~bash
./gradlew :core:clean :app:clean :app:assemble \
    --no-build-cache --no-configuration-cache \
    --profile --console=plain
~~~

**:core:clean** và **:app:clean** là các task trong cùng invocation; đây là một **clean-build scenario có thêm công việc clean**. Thời gian của scenario này bao gồm clean tasks; nó không hoàn toàn bằng “time để compile từ empty directory mà không đếm xóa files”.

Khi cần benchmark *compile cost từ fresh state*, có thể dùng Gradle Profiler **cleanup-tasks** trước từng measured invocation để tách công việc dọn khỏi measurement. Phải công bố định nghĩa scenario thay vì gọi mọi thứ “clean build”.

### 4.5. Report không đo lại kết quả trong quá khứ

Nếu build đã chạy từ một giờ trước mà không có **--profile**, bạn không thể dùng một profile report tạo sau đó rồi giả định nó mô tả run cũ. Trạng thái cache và task outputs có thể thay đổi; cần chạy scenario được định nghĩa để tạo evidence hiện tại.

### 4.6. Đường dẫn report và quyền truy cập

Report HTML được sinh cục bộ; giữ nó làm artifact CI nếu team cần so sánh hoặc review. Không nên commit toàn thư mục **build/** vào Git. Tránh dùng generated HTML như nguồn dữ liệu tự động ổn định để parse production metrics nếu layout report có thể đổi theo Gradle version; dùng Gradle Profiler CSV/JSON hoặc Build Scan data APIs được hỗ trợ khi cần automation.

---

## 5. Dùng --scan / Build Scan để phân tích chi tiết hơn

Gradle hiện đại hỗ trợ:

~~~bash
./gradlew :app:assemble --scan
~~~

Build Scan cung cấp trang Performance và các views liên quan:
- Total build duration.
- Startup và daemon/environment.
- Configuration breakdown theo scripts/plugins.
- Dependency resolution timing và nơi phát sinh.
- Task execution timeline, caching outcomes và parallelism.
- Chi tiết environment, Gradle/JDK/plugins liên quan.

**Build Scan có thể được publish lên một dịch vụ ngoài tổ chức**. Nó chứa thông tin về build environment, console logs, paths, dependencies và các metadata khác. Chỉ bật/publish khi chính sách cho phép, xem tùy chọn Develocity nội bộ nếu tổ chức có. Một đường dẫn scan “khó đoán” không thay cơ chế kiểm soát truy cập thực sự.

### 5.1. Khi scan cho thấy configuration chậm

Mở Performance → Configuration. Sắp các scripts/plugins theo thời gian apply/cấu hình. Nếu một plugin khiến configuration mất nhiều giây, xem:
- Plugin apply() có đọc files/network không?
- Có **afterEvaluate**, eager **tasks.all** hoặc configure mọi task vô điều kiện?
- Có dependency resolution trong configuration không?
- Có buildSrc / included build build logic cần rebuild?
- Có tất cả projects được cấu hình cho một task nhỏ không?

**Đo trước khi chỉnh**. Tránh sửa nhiều plugins/flags cùng lúc vì không xác định được yếu tố gây cải thiện.

### 5.2. Khi scan cho thấy execution chậm

Xem:
- Critical path và tasks kéo dài.
- Test runtime, test worker startup/fork count.
- Java/Kotlin compilation và annotation processing.
- Artifact transforms và dependency download.
- Tasks không incremental/cacheable.
- UP-TO-DATE/FROM-CACHE/NO-SOURCE ratios.
- Parallel capacity, CPU contention và I/O bottlenecks.

Một task tiêu tốn nhiều cumulative CPU time nhưng luôn ở nhánh song song không phải lúc nào cũng nên tối ưu trước critical-path task.

### 5.3. Khi scan cho thấy dependency resolution chậm

Đặc biệt xem **resolution during configuration**. Trong build.gradle, ví dụ phản tác dụng:

~~~groovy
// Phản ví dụ: force resolution khi cấu hình.
def allJarsNow = configurations.compileClasspath.files
~~~

Dòng này buộc Gradle phân giải configuration khi đọc script (nếu configuration đã tồn tại), ngay cả khi task cần nó không được chạy. Với dependency graph/network lớn, **help** cũng có thể chậm.

Ưu tiên khai báo task inputs bằng **Provider/Configuration** để Gradle resolve khi cần. Mẫu đúng cho task type cụ thể phải được kiểm tra theo task API; không tùy ý chuyển sang **doLast** nếu config cache hoặc task input modeling đòi cách khác.

### 5.4. Profiling không thay benchmarking

**--scan/--profile** hữu ích để tìm nguyên nhân, nhưng instrumentation và publishing có thể thêm overhead. Dùng chúng để tìm điểm nóng, sau đó kiểm chứng hiệu quả bằng nhiều **wall-clock samples** của cùng scenario với instrumentation settings ổn định.

---

## 6. Thiết kế các scenario: cold, warm, no-op, clean và incremental

Một baseline không nên trộn các loại build.

### 6.1. Cold daemon vs warm daemon

**Cold daemon**: chưa có Gradle Daemon phù hợp, Gradle phải tạo/khởi động mới. Chi phí JVM startup/class loading/JIT thường cao hơn.

**Warm daemon**: đã có daemon tương thích Gradle version/JDK/JVM args; reuse JIT warmed state và file watching metadata theo điều kiện.

Dùng:

~~~bash
./gradlew --status
~~~

để xem daemon của Gradle version tương ứng. Dùng:

~~~bash
./gradlew --stop
~~~

chỉ trong môi trường đo **cô lập**, vì nó có thể dừng daemon đang được người khác dùng của Gradle version đó trên cùng Gradle User Home/máy. Đừng đưa --stop vào benchmark lặp trong workspace shared mà không có kiểm soát.

### 6.2. --no-daemon không đồng nghĩa không có JVM startup

~~~bash
./gradlew :app:assemble --no-daemon
~~~

yêu cầu không tái sử dụng daemon lâu dài. Theo Gradle docs, nếu client JVM arguments không tương thích với JVM yêu cầu cho build, Gradle vẫn có thể tạo **single-use daemon** rồi dừng sau build. Vì vậy **--no-daemon** khác “chạy mọi thứ trong cùng JVM client không có overhead”.

Không dùng **--no-daemon** để mô phỏng một developer đang dùng warm daemon liên tục; đó là workload khác.

### 6.3. Cold outputs / clean build

Clean outputs nghĩa là generated files/class/JAR từ lần trước bị xóa, task phải tạo lại khi cần. **Nó không mặc nhiên xóa dependency caches, Gradle Daemon, Gradle distribution hoặc remote build cache**.

Ví dụ:

~~~bash
./gradlew :core:clean :app:clean :app:assemble
~~~

Nếu build cache đang bật và cache entries còn, compiler/archive tasks có thể **FROM-CACHE** thay vì thực thi từ đầu. Muốn benchmark thực thi đầy đủ, tắt build cache hoặc thiết kế một scenario kiểm soát cache store.

### 6.4. Warm outputs / no-op build

Sau khi assemble thành công, chạy lại:

~~~bash
./gradlew :app:assemble
~~~

nếu không đổi inputs/outputs, các tasks work-producing có thể **UP-TO-DATE**. Lần chạy này đo overhead giữ project/model/task graph và skip decisions; không phản ánh compile time của code mới.

Một no-op build vẫn có thể mất đáng kể thời gian vì settings, plugins, dependency resolution, configuration hoặc daemon startup.

### 6.5. Incremental build

Một workflow gần thực tế:
1. Build thành công từ source.
2. Sửa một method body, giữ public ABI.
3. Gọi **:app:compileJava** hoặc **:app:assemble**.
4. Ghi những tasks bị re-execute và elapsed time.
5. Hoàn nguyên source trước scenario khác.

Không dùng **--rerun-tasks** cho incremental scenario: flag ấy cố tình buộc tasks chạy lại và phá semantics đang đo.

### 6.6. Build cache vs configuration cache

| Cơ chế | Lưu gì | Dấu hiệu |
| --- | --- | --- |
| **Dependency cache** | Artifacts/metadata tải từ Maven/Ivy repositories | Download giảm, dependency resolved locally |
| **Build cache** | Task outputs dựa trên input fingerprints | **FROM-CACHE** |
| **Configuration cache** | Configured task graph và state của configuration | **Reusing configuration cache** |
| **Up-to-date checks** | Task output/input history ở workspace hiện tại | **UP-TO-DATE** |
| **Gradle Daemon** | JVM runtime reuse và một số state | Không khởi động daemon mới |

**FROM-CACHE không phải UP-TO-DATE; configuration-cache hit không phải build-cache hit.** Một invocation có thể vừa reuse configuration cache vừa restore task outputs từ build cache.

### 6.7. Không chạy --offline trước khi chuẩn bị dependencies

~~~bash
./gradlew :app:assemble --offline
~~~

tắt network dependency resolution nhưng **chỉ hợp lệ khi cache đã có mọi artifact cần thiết**. Nếu artifact chưa được cache, build có thể fail; không dùng offline failure làm bằng chứng repository latency. Với lab không có external modules, --offline có thể chạy, nhưng Wrapper distribution vẫn cần đã có trước invocation.

---

## 7. Quy trình đo baseline từng bước

### Bước 1 — Chọn duy nhất một workflow

Ví dụ: **:app:assemble** ở trạng thái warm daemon, output đã build, không thay source. Không dùng :app:run và :app:assemble xen kẽ rồi gộp durations.

### Bước 2 — Ghi lại môi trường

~~~bash
./gradlew --version
java -version
./gradlew --status
~~~

Ghi Gradle Wrapper distribution, JVM Gradle daemon, Java toolchain, OS/CPU/RAM, commit ID. **--version** không đo compilation; đây là bước ghi metadata.

### Bước 3 — Kiểm tra build correctness

~~~bash
./gradlew :app:assemble
~~~

Nếu build fail hoặc source output sai, sửa correctness trước khi benchmark. Tối ưu một build có lỗi chưa phải mục tiêu phù hợp.

### Bước 4 — Làm ấm có chủ đích

Chạy workload vài lượt để tránh JIT/class loading/caches cold outliers:

~~~bash
./gradlew :app:assemble
./gradlew :app:assemble
./gradlew :app:assemble
~~~

Ba lần là **ví dụ**; số warmups phù hợp phụ thuộc scenario và tool. Ghi rõ warmups không được tính vào samples.

### Bước 5 — Lấy ít nhất vài mẫu, không dùng một run

Thu 7–10 wall times hoặc nhiều hơn nếu variance cao. Không thay flags, file contents hoặc external dependencies giữa các samples. Nếu task state vô tình thay đổi, bỏ lượt đó hoặc chuyển sang scenario mới.

### Bước 6 — Tính median và p90

Median đại diện trung tâm bền vững hơn mean khi có một vài outliers. **p90** (phân vị 90) cho thấy phần đuôi chậm; với chỉ 5 samples, p90 rất nhạy với một sample nên cần ghi n.

### Bước 7 — Chạy profiling riêng

~~~bash
./gradlew :app:assemble --profile
~~~

hoặc một Build Scan được policy cho phép. Đọc Startup, Settings/buildSrc, Loading/Configuring Projects, Task Execution.

### Bước 8 — Thay một biến

Ví dụ bật **--configuration-cache** nhưng giữ mọi thứ khác như baseline. Đo **cache miss lần đầu** tách khỏi **cache hit các lần sau**. Không vừa bật configuration cache vừa nâng Gradle Wrapper vừa đổi JDK rồi tuyên bố một yếu tố duy nhất tạo speedup.

### Bước 9 — Lặp lại nhiều samples

Chạy cùng workflow sau thay đổi, warmup tương tự. So median/p90, hiệu ứng so với noise và correctness. Có thể hoán đổi thứ tự A/B nếu hệ thống nóng dần theo thời gian để giảm bias.

### Bước 10 — Lưu kết quả

Lưu CSV/JSON, commit và flags, profile/scan URLs nếu được phép, môi trường và nhận xét. Người khác phải có thể chạy lại setup và ra xu hướng tương tự.

---

## 8. Lab Java 17: multi-project build để đo thật

Lab tạo **:core** và **:app**. App dùng code của core, không phụ thuộc Maven Central, nên network dependency resolution không làm sai lệch thử nghiệm cơ bản. Có các tasks **:app:assemble**, **:app:compileJava**, **:app:run** và **help** để so sánh workload.

### 8.1. Cây thư mục

~~~text
gradle-performance-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── core/
│   ├── build.gradle
│   └── src/main/java/lab/core/Normalizer.java
├── app/
│   ├── build.gradle
│   └── src/main/java/lab/app/Main.java
└── tools/
    ├── BaselineRunner.java
    └── TimeStats.java
~~~

**Wrapper** phải được Gradle tạo từ distribution đáng tin hoặc lấy từ project tin cậy. Không tự tạo gradle-wrapper.jar bằng một text file. Chọn Gradle Wrapper version tương thích JVM17 theo Gradle compatibility matrix.

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'gradle-performance-lab'

include 'core', 'app'
~~~

### 8.3. build.gradle ở root

~~~groovy
plugins {
    id 'base'
}
~~~

Root có **base** plugin để cung cấp lifecycle cơ bản; hai modules cấu hình Java riêng. Không dùng subprojects { ... } để tạo một benchmark chứa cross-project configuration phức tạp ngoài chủ đề.

### 8.4. core/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

### 8.5. core/src/main/java/lab/core/Normalizer.java

~~~java
package lab.core;

import java.util.Locale;

public final class Normalizer {
    private Normalizer() {
    }

    public static String normalize(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input");
        }
        return input.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

**Locale.ROOT** giữ kết quả ổn định khi chạy trên các locale khác nhau. Code Java 17 này không yêu cầu thư viện ngoài.

### 8.6. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

dependencies {
    implementation project(':core')
}

application {
    mainClass = 'lab.app.Main'
}
~~~

**project(':core')** tạo dependency graph giữa app và core, để Gradle lập lịch producer compilations/artifacts phù hợp. Khi chạy :app:compileJava, Gradle có thể chọn class directories thay vì luôn tạo :core:jar; đó là hợp lệ.

### 8.7. app/src/main/java/lab/app/Main.java

~~~java
package lab.app;

import lab.core.Normalizer;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
                "BASELINE_OK: " +
                Normalizer.normalize("  gradle  ")
        );
    }
}
~~~

### 8.8. Chạy ứng dụng

Linux/macOS:

~~~bash
./gradlew :app:run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run
~~~

**Dòng stdout Java chính xác:**

~~~text
BASELINE_OK: GRADLE
~~~

Gradle còn in task logs/BUILD SUCCESSFUL, nên đây không phải transcript toàn bộ console.

### 8.9. Chạy build task

~~~bash
./gradlew :app:assemble
~~~

Kỳ vọng Gradle compile Java sources, xử lý resources và sinh JAR/distribution artifacts cần cho application plugin. Task graph exact phụ thuộc Gradle version. Không gán sẵn thời lượng; sample thật phải đo tại môi trường của người học.

### 8.10. Kiểm tra clean build đầy đủ của hai modules

~~~bash
./gradlew :core:clean :app:clean :app:assemble \
    --no-build-cache --no-configuration-cache \
    --console=plain
~~~

Task :core:clean và :app:clean đảm bảo outputs của cả hai modules bị dọn ở scenario này. Khi không dùng build cache, Gradle sẽ cần tạo lại outputs cần thiết. **Task clean và nhiều overhead cũng được tính vào elapsed**; công bố đúng định nghĩa này.

### 8.11. Kiểm tra no-op

Sau assemble thành công:

~~~bash
./gradlew :app:assemble \
    --no-build-cache --no-configuration-cache \
    --console=plain
~~~

Nếu không thay input/output, các task có outputs có thể **UP-TO-DATE**. Nhiệm vụ hiện tại không phải đo compiler throughput mà là no-op overhead.

### 8.12. Kiểm tra configuration bằng help

~~~bash
./gradlew help \
    --no-build-cache --no-configuration-cache \
    --profile --console=plain
~~~

Mở report và xem Startup/Settings/buildSrc/Configuring Projects. Với lab nhỏ, thời gian có thể chỉ vài giây hoặc ít hơn sau warm-up; không khẳng định số nào là “đúng chuẩn” cho mọi máy.

### 8.13. So profile của help và assemble

~~~bash
./gradlew help --profile
./gradlew :app:assemble --profile
~~~

Cả hai tạo profile reports riêng. So giai đoạn configuration trong từng run; không lấy hiệu hai total times làm “chỉ task execution” vì tasks selected có thể làm task graph/resolution và caching khác.

---

## 9. Benchmark Runner Java 17: tự đo nhiều wall-time samples

Mục đích: có một tiện ích **Java thuần** chạy Gradle Wrapper nhiều lần và đo **wall-clock** bằng **System.nanoTime()**. Nó không cần Gradle API để compile.

Đây là **công cụ thực sự thực thi lệnh Gradle được truyền vào**. Chỉ dùng với lệnh đáng tin trong repository của bạn; không chấp nhận command input từ người lạ mà không kiểm soát.

### 9.1. File tools/BaselineRunner.java

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public final class BaselineRunner {
    private BaselineRunner() {
    }

    public static void main(String[] args)
            throws IOException, InterruptedException {

        if (args.length < 3) {
            throw new IllegalArgumentException(
                    "Usage: BaselineRunner <warmups> <runs> <gradle-args...>"
            );
        }

        int warmups = Integer.parseInt(args[0]);
        int runs = Integer.parseInt(args[1]);

        if (warmups < 0 || runs < 1) {
            throw new IllegalArgumentException(
                    "warmups must be >= 0 and runs >= 1"
            );
        }

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT)
                .contains("win");

        List<String> command = new ArrayList<>();
        if (windows) {
            command.add("cmd.exe");
            command.add("/c");
            command.add("gradlew.bat");
        } else {
            command.add("./gradlew");
        }
        command.addAll(Arrays.asList(args).subList(2, args.length));

        List<Long> samples = new ArrayList<>();

        for (int i = 0; i < warmups + runs; i++) {
            ProcessBuilder builder = new ProcessBuilder(command);
            builder.redirectErrorStream(true);
            builder.redirectOutput(
                    ProcessBuilder.Redirect.DISCARD
            );

            long start = System.nanoTime();
            Process process = builder.start();
            int exitCode = process.waitFor();
            long elapsedNanos = System.nanoTime() - start;
            long elapsedMillis = TimeUnit.NANOSECONDS
                    .toMillis(elapsedNanos);

            if (exitCode != 0) {
                throw new IllegalStateException(
                        "Gradle exit=" + exitCode
                        + " on iteration=" + (i + 1)
                        + ". Run the command manually to inspect logs."
                );
            }

            if (i < warmups) {
                System.out.println(
                        "warmup " + (i + 1)
                        + " completed (excluded)"
                );
            } else {
                samples.add(elapsedMillis);
                System.out.println(
                        "sample " + (i - warmups + 1)
                        + " = " + elapsedMillis + " ms"
                );
            }
        }

        Collections.sort(samples);
        int n = samples.size();
        double median = n % 2 == 1
                ? samples.get(n / 2)
                : (samples.get(n / 2 - 1)
                        + samples.get(n / 2)) / 2.0;
        int p90Index = (int) Math.ceil(n * 0.90) - 1;
        long p90 = samples.get(p90Index);
        double mean = samples.stream()
                .mapToLong(Long::longValue)
                .average()
                .orElseThrow();

        System.out.printf(
                Locale.ROOT,
                "n=%d median=%.1f ms p90=%d ms mean=%.1f ms%n",
                n, median, p90, mean
        );
    }
}
~~~

### 9.2. Cách hoạt động

- **warmups** là số invocations trước khi lấy samples.
- **runs** là số measured invocations.
- Mọi arguments sau hai số được chuyển cho **Gradle Wrapper** như đã viết.
- Trên Unix chạy **./gradlew**, trên Windows chạy **cmd.exe /c gradlew.bat**.
- Đo từ lúc gọi **ProcessBuilder.start** đến **waitFor** (xấp xỉ external wall elapsed).
- Dừng và báo lỗi nếu một Gradle invocation trả exit code khác 0.
- **Không ghi đè source code**; runner chỉ chạy những tasks người dùng yêu cầu.
- Không thay output/repository/cache giữa samples.

**Lưu ý:** runner bỏ qua console output để kết quả bớt nhiễu do I/O. Nếu build fail, hãy chạy lệnh Gradle thủ công để xem lỗi; không sử dụng runner để giấu failure. Đầu ra timing **không có số cố định** vì mỗi máy khác nhau; chỉ ví dụ output của app ở mục 8 có thể được dự đoán chính xác.

### 9.3. Compile runner trên Linux/macOS

~~~bash
mkdir -p .benchmark-classes

javac --release 17 -encoding UTF-8 \
    -d .benchmark-classes tools/BaselineRunner.java
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force .benchmark-classes | Out-Null

javac --release 17 -encoding UTF-8 -d .benchmark-classes tools\BaselineRunner.java
~~~

Output classes nằm trong **.benchmark-classes/** ở root, **không nằm trong build/** để Gradle clean tasks của modules không xóa benchmark runner.

### 9.4. Đo no-op assemble có warm-up

Trước hết chạy:

~~~bash
./gradlew :app:assemble \
    --no-build-cache --no-configuration-cache
~~~

Rồi đo:

~~~bash
java -cp .benchmark-classes BaselineRunner \
    3 7 :app:assemble \
    --no-build-cache --no-configuration-cache \
    --console=plain
~~~

**3 warmups, 7 samples**, mỗi sample có thể khác nhau. Các compiled artifacts hiện có, nên đây là **no-op assemble** scenario; không phải 7 lần compile sạch.

Trên PowerShell, viết một dòng để tránh vấn đề line continuation:

~~~powershell
java -cp .benchmark-classes BaselineRunner 3 7 :app:assemble --no-build-cache --no-configuration-cache --console=plain
~~~

Output dạng minh họa:

~~~text
warmup 1 completed (excluded)
warmup 2 completed (excluded)
warmup 3 completed (excluded)
sample 1 = <measured ms>
...
sample 7 = <measured ms>
n=7 median=<measured ms> p90=<measured ms> mean=<measured ms>
~~~

**Đây chỉ là mẫu format**, không phải stdout byte-for-byte từ một máy thật. Không đưa những số tự đoán vào báo cáo baseline.

### 9.5. Vì sao ProcessBuilder hữu ích?

Các shell khác nhau có cách đo time khác nhau (Bash time, PowerShell Measure-Command, GNU /usr/bin/time). Một Java runner dùng **System.nanoTime** giữ công thức thống nhất và đo process duration. Tuy vậy:
- Windows cmd.exe có overhead khác Unix shell.
- Timer resolution và scheduler khác nhau.
- JDK/OS khác có thể ảnh hưởng.
- JVM process dùng để chạy runner có overhead riêng **nằm ngoài sample timer**.

Vì thế chỉ so trên **cùng máy/cùng environment** hoặc ghi đầy đủ machine context.

### 9.6. Khi nào không dùng runner này?

Nó đo một command lặp **trên trạng thái outputs do các lượt trước tạo ra**. Không phù hợp nếu bạn muốn 7 lần **fresh clean build** mà không reset outputs ở mỗi iteration.

Với clean scenario chuyên nghiệp, dùng **Gradle Profiler** có cleanup-tasks hoặc một harness tạo workspace/reset state có kiểm soát, không tự gọi cùng lệnh 7 lần rồi ghi tên “clean build”.

---

## 10. Java 17 TimeStats: minh họa cách tính median và p90

Để có kết quả tính toán **hoàn toàn xác định** không phụ thuộc Gradle runtime, tạo file **tools/TimeStats.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public final class TimeStats {
    private TimeStats() {
    }

    public static void main(String[] args) {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "Provide positive millisecond samples"
            );
        }

        List<Long> samples = new ArrayList<>();
        for (String value : args) {
            long ms = Long.parseLong(value);
            if (ms <= 0) {
                throw new IllegalArgumentException(
                        "Milliseconds must be positive"
                );
            }
            samples.add(ms);
        }

        Collections.sort(samples);
        int n = samples.size();

        long min = samples.get(0);
        double median = n % 2 == 1
                ? samples.get(n / 2)
                : (samples.get(n / 2 - 1)
                        + samples.get(n / 2)) / 2.0;

        int p90Index = (int) Math.ceil(0.90 * n) - 1;
        long p90 = samples.get(p90Index);

        double mean = samples.stream()
                .mapToLong(Long::longValue)
                .average()
                .orElseThrow();

        System.out.printf(Locale.ROOT, "n=%d%n", n);
        System.out.printf(Locale.ROOT, "min=%d ms%n", min);
        System.out.printf(
                Locale.ROOT, "median=%.1f ms%n", median
        );
        System.out.printf(Locale.ROOT, "p90=%d ms%n", p90);
        System.out.printf(
                Locale.ROOT, "mean=%.1f ms%n", mean
        );
    }
}
~~~

Biên dịch/chạy từ root:

~~~bash
javac --release 17 -encoding UTF-8 \
    -d .benchmark-classes tools/TimeStats.java

java -cp .benchmark-classes TimeStats 790 810 820 800 880
~~~

Nếu chưa có **.benchmark-classes**, tạo folder theo mục 9.3 trước.

**Stdout chính xác:**

~~~text
n=5
min=790 ms
median=810.0 ms
p90=880 ms
mean=820.0 ms
~~~

Các giá trị đã sort là **790, 800, 810, 820, 880**. Median là phần tử giữa **810**. p90 theo phương pháp **nearest rank** với n=5 là phần tử thứ **ceil(0.9 × 5)=5**, tức **880**. Mean = (790+810+820+800+880)/5 = **820.0**.

**Chú ý:** có nhiều cách tính percentile; bài này chọn nearest-rank tường minh. Khi so dashboard Gradle Profiler/Develocity, kiểm tra cùng định nghĩa percentile trước khi so chênh lệch.

---

## 11. Phân tích baseline before/after đúng toán

### 11.1. Time reduction

Giả sử **median baseline = 1200 ms** và **median variant = 960 ms** (số giả định):

~~~text
absolute reduction = 1200 - 960 = 240 ms

relative time reduction
    = (1200 - 960) / 1200 * 100%
    = 20%
~~~

**Giảm 20% thời gian** không đồng nghĩa **nhanh hơn 20% theo hệ số throughput**. Nếu nói speedup ratio:

~~~text
speedup = old_time / new_time = 1200 / 960 = 1.25x
~~~

Đây là 25% cao hơn về hệ số tốc độ nếu workload là như nhau. Trong báo cáo nên dùng cụm **“time reduction 20%”** hoặc **“speedup 1.25×”**, tránh trộn.

### 11.2. Ý nghĩa của p90

Nếu median tốt hơn nhưng p90 xấu đi nhiều, có thể:
- Daemon restart ngẫu nhiên.
- GC hoặc CPU contention.
- Network latency variability.
- Build cache miss thỉnh thoảng.
- Test worker startup khác nhau.
- CI host không ổn định.

Một optimization cho developer workflows nên cân nhắc cả **thời gian thường thấy** và **tail latency**.

### 11.3. Một mẫu không chứng minh cải thiện

Giả sử run A mất 8.1s và run B mất 7.9s. Chênh lệch 0.2s có thể nhỏ hơn noise do filesystem, JIT/GC hoặc scheduler. Cần nhiều samples và so scatter/spread, tránh tuyên bố speedup dựa trên một cặp timing.

### 11.4. A/B test để giảm hiệu ứng nóng dần

Nếu có thể, đo theo các lượt:
- A warm-ups + samples.
- B warm-ups + samples.
- A lặp lại để xem baseline có drift.
- B lặp lại nếu cần.

Khi benchmark automated, dùng **Gradle Profiler** và isolate scenarios, giữ caches/warmups nhất quán. Không so một bản A cold-daemon với B warm-daemon rồi suy ra cải thiện code.

---

## 12. Gradle Profiler cho benchmark chuyên nghiệp

Công cụ nguồn mở **Gradle Profiler** được Gradle đề xuất khi cần benchmarking/profiling nhiều iterations và scenarios.

### 12.1. Lệnh cơ bản

Sau khi cài binary **gradle-profiler** từ nguồn tin cậy, tại root lab:

~~~bash
gradle-profiler --benchmark \
    --project-dir . \
    :app:assemble
~~~

Gradle Profiler chạy nhiều lần và tạo reports như **profile-out/benchmark.html**, **benchmark.csv** và **benchmark.json**. Nó hỗ trợ warmups, iterations và thống kê samples.

**gradle-profiler** không phải task tích hợp trong ./gradlew. Nếu shell báo command not found, cài CLI theo hướng dẫn dự án Gradle Profiler; không thay bằng **./gradlew gradle-profiler**.

### 12.2. Thiết kế performance.scenarios

File **performance.scenarios** minh họa:

~~~text
no_op_assemble {
    tasks = [":app:assemble"]
}

clean_assemble {
    cleanup-tasks = [":core:clean", ":app:clean"]
    tasks = [":app:assemble"]
}
~~~

**Ý nghĩa:**
- no_op_assemble phù hợp khi outputs đã được tạo và không có thay đổi.
- clean_assemble dùng cleanup-tasks trước mỗi measured run, nên dễ tách chi phí cleanup khỏi công việc chính hơn lệnh clean và assemble trong cùng invocation.

Cấu hình Gradle Profiler CLI/DSL có thể tiến hóa theo version; kiểm tra **gradle-profiler --help** và documentation đúng bản cài.

### 12.3. Chạy scenarios

~~~bash
gradle-profiler --benchmark \
    --scenario-file performance.scenarios \
    --warmups 3 \
    --iterations 10 \
    no_op_assemble clean_assemble
~~~

Trong Gradle Profiler, cache state/daemon mode của scenario cũng phải được kiểm soát, không chỉ số warmups. Nếu dùng scenario clean_assemble mà build cache bật, tasks có thể restore outputs từ cache; đó không phải benchmark CPU compile nguyên bản.

### 12.4. Output CSV/JSON

Gradle Profiler hỗ trợ machine-readable results để:
- Lưu raw samples.
- So median/p25/p75/max/standard deviation.
- So phiên bản Gradle/DSL/plugin trước–sau.
- Theo dõi performance regression.
- Kết hợp thống kê thay vì một số lẻ.

Không tự gán tên field CSV/JSON cố định nếu tool version thay đổi; kiểm tra schema thực tế trong report.

### 12.5. Method-level profiling

Nếu Build Scan chỉ ra **một plugin** mất nhiều thời gian, Gradle Profiler có thể hỗ trợ JFR/async-profiler để tìm code hotspot CPU/allocation. Phân tích JVM-level chỉ sau khi biết được giai đoạn chậm, vì profiler làm tăng overhead và có nhiều chi phí setup.

---

## 13. Đọc phase breakdown đúng: năm bẫy dễ mắc

### 13.1. “Startup chiếm 60%” trên lần đầu không có nghĩa ngày nào cũng 60%

Nếu vừa tải Gradle distribution/khởi động daemon, startup có thể phình lớn. Lần hai reuse daemon và warmed caches khác hẳn. Hãy đo cold startup riêng và warm startup riêng.

### 13.2. “Configuring projects 2s” không có nghĩa mọi thao tác settings/buildSrc chỉ 2s

Profile có **Settings and buildSrc** và **Loading Projects** riêng. Chỉ nhìn Configuring Projects mà bỏ qua settings/init scripts/build logic có thể làm nhầm phase gây vấn đề.

### 13.3. “Task execution 1s” không có nghĩa compiler thật mất 1s

Task execution phase có thể chỉ kiểm tra UP-TO-DATE, restore FROM-CACHE hoặc skip NO-SOURCE; không có compile thật. Phải xem **task outcomes** và input state, không chỉ total execution duration.

### 13.4. “Cộng task timings bằng tổng thời gian build”

Sai khi tasks song song, overlapping, nhiều workers hoặc artifact transforms. Dùng timeline/critical path và external wall.

### 13.5. “Lượt có --scan/--profile luôn phản ánh production workload”

Profiling có thêm instrumentation và có thể xuất/publish data. Nếu muốn đo speedup chính xác, dùng một loạt measurements với cùng profiling state hoặc dùng non-instrumented benchmark riêng. Tránh so before có profile nhưng after không profile mà không nêu chênh lệch.

---

## 14. Giải pháp tối ưu theo phase sau khi đo

| Phase/triệu chứng | Nhóm nguyên nhân | Hướng tối ưu phải kiểm chứng |
| --- | --- | --- |
| Cold startup cao | Daemon khởi động, JDK/JIT, Gradle distribution download | Warm daemon/Wrapper pre-provision, thống nhất JVM args |
| Warm startup vẫn cao | Init scripts, daemon không reusable, JVM mismatch | So JVM args/version, inspect init scripts |
| Settings/buildSrc chậm | Plugin/build logic biên dịch lại, settings code I/O | Tách minimal build logic, tránh I/O ở initialization |
| Loading/configuring projects chậm | Eager configuration, cross-project logic | Lazy tasks.register/configureEach, chỉ cấu hình work cần |
| Dependency resolution ở configuration | configurations.*.files bị đọc quá sớm | Deferred resolution, Provider/Configuration wiring |
| Dependency resolution mạng cao | Chậm repositories, dynamic/changing versions | Cache metadata hợp lý, repository order, lock fixed versions |
| Task compileJava chậm | Annotation processors, classpath lớn, ABI changes | Incremental compile, compile avoidance, classpath hygiene |
| Task tests chậm | Test discovery/fork setup, integration environment | Tối ưu test setup, phân loại suites, worker configuration |
| Nhiều tasks chạy lại dù input không đổi | Outputs/inputs không khai báo hoặc unstable | Incremental build modeling, @Input/@Output contract |
| Task execution có cache miss | Build cache off, non-cacheable task, changing inputs | @CacheableTask đúng, normalized inputs/outputs |
| Workload có parallel stalls | Task critical path, resource contention | Chỉnh task graph, parallel workers theo CPU/RAM |
| No-op build chậm | Config dominates, invalid configuration cache | Configuration cache sau khi kiểm tra compatibility |

### 14.1. Daemon: đúng cho developer workflows

Gradle Daemon bật mặc định ở Gradle hiện đại. Không tắt nó chỉ vì CI config trước đây dùng --no-daemon. Trên developer laptop và CI agents lâu sống, reuse daemon giúp tiết kiệm startup. Với ephemeral containers chạy đúng một build, lợi ích warm daemon có thể nhỏ; baseline phải phản ánh kiến trúc CI thực tế.

### 14.2. Configuration cache: đo cả miss và hit

~~~bash
./gradlew :app:assemble --configuration-cache
./gradlew :app:assemble --configuration-cache
~~~

Lần đầu có thể tạo entry, lần sau có thể **Reusing configuration cache** nếu inputs unchanged. Không gộp hai lần vào một số duy nhất. Cần build logic compatible; nếu có lỗi configuration cache phải sửa thay vì dùng flags warnings để che vấn đề.

### 14.3. Build cache: tách khỏi configuration cache

~~~bash
./gradlew :core:clean :app:clean \
    :app:assemble --build-cache
~~~

Nếu cache entry tương ứng tồn tại, compile/package outputs có thể **FROM-CACHE**. Nó không chứng minh configuration cache cũng hit. Muốn benchmark execution workload thực sự, chọn điều kiện cache on/off tường minh.

### 14.4. Avoid eager task realization

Trong custom Gradle plugin, dùng:

~~~groovy
tasks.register('generateDocs') {
    // Cấu hình lazy.
}
~~~

thay vì eager tạo và cấu hình hàng nghìn tasks khi không được yêu cầu. Một task được tạo ở configuration không nhất thiết thực thi, nhưng chi phí configure/eager resolution vẫn làm mọi invocation chậm.

### 14.5. Không làm network I/O trong plugin apply

Một plugin gọi endpoint khi apply vào 100 projects có thể khiến **help** chậm. Đưa network interaction vào task phù hợp với declared inputs/outputs và cơ chế caching an toàn, hoặc giảm/thay bằng versioned artifact/repository resolution.

### 14.6. Thay tối ưu chỉ sau khi đọc critical path

Nếu báo cáo cho thấy compileJava của :core mất 4 giây nhưng chạy song song với test suite 15 giây, tối ưu compileJava 1 giây chưa chắc giảm total wall. Đo lại timeline và critical path để xác nhận lợi ích.

---

## 15. Baseline cho CI: thứ gì cần lưu?

Một bảng kết quả minh họa (**số giả định**, không phải kết quả lab):

| Scenario | Daemon | Build cache | Configuration cache | Median wall | p90 wall | Ghi chú |
| --- | --- | --- | --- | ---: | ---: | --- |
| no-op-assemble | warm | off | off | 1.4s | 1.8s | Tasks UP-TO-DATE |
| no-op-assemble | warm | off | hit | 0.7s | 0.9s | Configuration reused |
| clean-assemble | warm | off | off | 7.8s | 8.5s | Recompile |
| clean-assemble | warm | on | off | 3.0s | 4.1s | FROM-CACHE nếu entry có |
| cold-help | cold | off | off | 3.2s | 4.0s | Startup dominated |

Không đọc bảng này như ngưỡng mong đợi cho mọi dự án: CPU/JVM/plugins/dependencies và cache topology khiến số thật rất khác.

### 15.1. Metadata CI cần ghi kèm

~~~text
Scenario ID
Repository and commit SHA
Branch/PR
Gradle Wrapper version and distribution checksum
Gradle daemon JDK and Java toolchains
OS image / CPU / RAM / disk type
Task selector and all flags
Parallel workers and org.gradle.jvmargs
Daemon state (cold/warm)
Build cache mode (off/local/remote/hit rates)
Configuration cache mode (off/miss/hit)
Dependency cache/network state
Warmup count and measured iteration count
Wall-clock samples, median, p90
Profile/Build Scan link (if allowed)
Failure count and task outcomes
Measurement date and owner
~~~

### 15.2. Không biến một build hỏng thành sample

Nếu một invocation fail do javac, tests, network, OOM, timeout, wrapper download error hoặc machine restart, baseline phải đánh dấu failed/outlier theo policy. **Không đưa 0ms hoặc một duration cụt vào histogram của builds thành công.**

### 15.3. Chú ý đồng bộ clocks

**System.nanoTime** phù hợp đo duration trong cùng JVM process, không phải timestamp có thể so tuyệt đối giữa machines. Không lấy UTC timestamp của máy A trừ máy B để tính một build duration nếu clocks không đồng bộ.

### 15.4. Resource contention

CI workers chạy nhiều Gradle processes trên cùng máy có thể tranh CPU/RAM/disk. Nếu cần comparative benchmark chính xác, dùng dedicated runner hoặc hạn chế concurrency; ghi máy và workload nền. Chạy benchmark giữa lúc hệ thống deploy/download dependencies làm variance tăng.

### 15.5. Confidentiality của Build Scan

Nếu build chứa internal package names, paths, env identifiers, logs hoặc repository metadata nhạy cảm, cần kiểm tra retention/access-control của Build Scan. Không publish công khai chỉ để nhận một timeline đẹp; local **--profile** là phương án ít trao đổi dữ liệu hơn.

---

## 16. Ví dụ lỗi thường gặp và cách phân tích

| Dấu hiệu | Khả năng nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| Lần đầu 40s, lần hai 5s | Wrapper download, daemon/JIT cold, dependency cache | So startup và network logs |
| --no-daemon chậm hơn | Mất daemon reuse/single-use daemon overhead | Đo riêng warm daemon vs no-daemon |
| help mất 12s | Settings/plugins/configuration chậm | --profile help, scan Configuration |
| assemble nhanh nhưng test lâu | Test execution bottleneck | Scan task timeline/test workers |
| Total build 8s, sum tasks 15s | Tasks chạy song song | Critical path/wall clock |
| Profile không có trong build/reports/profile | Sai build root, task chưa xong hoặc layout tùy chỉnh | Kiểm console report location, filesystem |
| FROM-CACHE xuất hiện không compile | Output restore từ build cache | Cache key, task outcome, artifact correctness |
| UP-TO-DATE bị gọi là build cache hit | Nhầm local history và output cache | Xem outcome, clean then --build-cache |
| No-op vẫn chậm | Cấu hình/daemon/init scripts | help vs assemble profile, config cache |
| Configuration cache không hit | Inputs config đổi, plugin unsupported, task selector khác | Gradle diagnostics về invalidation |
| --profile before chậm hơn after không profile | Instrumentation khác | Đo hai phía cùng flags |
| BuildScan báo resolution ở configuration | Eager resolutions | Xem scripts/plugins/configurations.files |
| --offline fail | Dependency chưa cache | Warm dependencies trước khi đo offline |
| Clean build vẫn FROM-CACHE | Build cache còn entry | Tắt cache hoặc định nghĩa clean+cache-on riêng |
| --rerun-tasks bị coi incremental | Flag ép rerun | Không dùng --rerun-tasks cho incremental |
| Cùng command nhưng thời gian khác đáng kể | Daemon/JIT/GC/CPU/load | Warmup, samples, p90, môi trường |
| JVM flag thay đổi tạo daemon khác | Daemon compatibility mismatch | --status, --version, jvmargs |
| Gradle Wrapper version khác | Benchmark môi trường khác | Pin wrapper, so properties |
| Java toolchain download làm chậm | JDK toolchain chưa có | Pre-install toolchain hoặc đo provisioning scenario |
| Task :app:assemble không tạo Main stdout | assemble chỉ build, không run | Dùng :app:run để xác minh app |
| gradle-profiler command not found | CLI tool chưa cài | Cài riêng theo docs |
| Gradle Profiler no-op scenario lại execute | Inputs/outputs thay hoặc cleanup | Xác minh task outcomes/scenario configuration |
| Source đổi giữa samples | Workload không còn giống | Reset source, phân loại incremental scenario |
| p90 từ 5 mẫu rất dao động | Sample count quá ít | Thu thêm samples, ghi method |
| Một script benchmark loại bỏ lỗi bằng pipe | Exit code Gradle bị che | Kiểm exit code từng invocation |
| CI share cache không an toàn | Untrusted writes/poisoning | Restrict remote cache writers/readers |

### 16.1. Debug checklist gọn

1. Có baseline scenario name và task selector đúng không?
2. Gradle Wrapper/JDK/OS có giống nhau không?
3. Daemon warm hay cold? JVM args có tạo daemon mới?
4. Build cache/configuration cache on/off/hit/miss?
5. Dependency artifacts đã tải trước khi đo chưa?
6. Tasks thực sự EXECUTED hay UP-TO-DATE/FROM-CACHE?
7. Có artifacts bị xóa hay source files thay đổi giữa samples?
8. Có profiler overhead/scan publishing trong chỉ một phía không?
9. Median/p90/sample count đã được ghi?
10. Số thời gian lấy từ external wall clock hay profile categories?
11. Task durations có overlap không?
12. Optimization có giảm critical path/total wall thật không?

---

## 17. Bài tập có đáp án

### Bài 1 — Baseline chỉ ghi “build 10s”

**Đáp án:** chưa đủ. Cần task, commit, flags, Gradle/JDK, daemon/caches, hardware và số samples.

### Bài 2 — Help mất 8s nhưng compileJava chỉ 1s

**Đáp án:** kiểm tra Startup, Settings/buildSrc, Loading/Configuring Projects và dependency resolution trong configuration. Không vội tối ưu compiler.

### Bài 3 — Chạy clean build khi build cache vẫn bật

**Đáp án:** outputs cục bộ bị xóa, nhưng task outputs vẫn có thể FROM-CACHE. Muốn đo full execution, tắt build cache hoặc thiết kế scenario kiểm soát cache state.

### Bài 4 — UP-TO-DATE có phải cache hit?

**Đáp án:** không. UP-TO-DATE là output/history của workspace hiện tại; FROM-CACHE là restore từ build cache.

### Bài 5 — Tại sao cần warmup?

**Đáp án:** tránh trộn JVM startup/JIT/class loading/dependency setup bất thường với steady-state measurements. Warmup count phải được công bố.

### Bài 6 — Có thể trừ total help khỏi total assemble để lấy execution time?

**Đáp án:** không chính xác. Hai invocations có thể khác graph, cache state, lazy config, dependency resolution và profiler overhead. Xem phase breakdown trong cùng build.

### Bài 7 — Sum task durations = 25s, wall = 14s

**Đáp án:** có thể hợp lệ vì tasks overlap/parallel. Dùng timeline và critical path, không cộng cứng task durations.

### Bài 8 — --no-daemon có bảo đảm không có daemon process?

**Đáp án:** không luôn. Nếu client JVM không tương thích yêu cầu build, Gradle có thể tạo single-use daemon; không có daemon reusable sau invocation.

### Bài 9 — Profiling mặc định Gradle?

**Đáp án:** Gradle có --profile tạo HTML cục bộ; --scan tạo Build Scan nhiều chi tiết hơn nhưng có thể publish metadata; Gradle Profiler là CLI riêng cho benchmark/scenarios.

### Bài 10 — Nhìn configuration cache message “Reusing configuration cache”

**Đáp án:** Gradle reuse task graph/configuration. Nó không tự chứng minh task outputs FROM-CACHE; xem outcomes riêng.

### Bài 11 — So plugin A và B nhưng đổi Gradle version cùng lúc

**Đáp án:** không xác định được nguyên nhân. Giữ Gradle Wrapper/JDK/flags cố định hoặc phân chia thử nghiệm từng biến.

### Bài 12 — TimeStats cho 790,810,820,800,880

**Đáp án:** n=5, min=790ms, median=810ms, p90 nearest rank=880ms, mean=820ms.

### Bài 13 — Before median 1200ms, after 960ms

**Đáp án:** tiết kiệm 240ms; time reduction=20%; speedup factor=1.25x.

### Bài 14 — Cold build chậm vì tải dependency lần đầu

**Đáp án:** ghi đây là cold dependency scenario; nếu muốn benchmark compile performance, tải/warm dependencies trước. Không trộn vào warm measurements.

### Bài 15 — JVM args thay đổi làm Gradle daemon không reuse

**Đáp án:** daemon compatibility phụ thuộc Gradle version/JDK/JVM args; xem --status và report. Hai runs không cùng warm-daemon condition.

### Bài 16 — Build có 30 tasks, có chắc 30 tasks chạy action?

**Đáp án:** không. Lifecycle tasks, UP-TO-DATE, FROM-CACHE và NO-SOURCE không nhất thiết chạy action. Xem task outcomes.

### Bài 17 — Test execution sum giảm 5s nhưng wall không đổi

**Đáp án:** tasks có thể không nằm trên critical path; xem timeline/parallelism và CPU contention.

### Bài 18 — Benchmark runner có stdout Gradle không?

**Đáp án:** trong lab BaselineRunner bỏ Gradle stdout/stderr và kiểm exit code; nó in warmup/samples/tóm tắt. Muốn debug lỗi, chạy lệnh Gradle thủ công.

### Bài 19 — p90 có thể khác với công cụ khác dù cùng samples?

**Đáp án:** có nếu công cụ dùng percentile interpolation khác. Bài dùng nearest-rank; phải so cùng định nghĩa.

### Bài 20 — Khi nào dùng --profile thay --scan?

**Đáp án:** khi cần breakdown cơ bản cục bộ, không muốn publish dữ liệu lên dịch vụ. Build Scan cung cấp chi tiết hơn nếu policy cho phép.

### Bài 21 — Một command chỉ chạy help có đại diện full CI check không?

**Đáp án:** không. Help chủ yếu giúp quan sát initialization/configuration; CI check gồm compile/tests/artifact tasks khác.

### Bài 22 — Tại sao dùng System.nanoTime thay currentTimeMillis?

**Đáp án:** nanoTime dùng để đo elapsed duration trong cùng JVM, phù hợp monotonic clock semantics, không phụ thuộc đồng bộ wall-clock timestamp.

### Bài 23 — Khi nào dùng Gradle Profiler?

**Đáp án:** khi cần benchmark nhiều iterations, warmups, scenarios như no-op/clean/incremental và machine-readable outputs, đặc biệt khi so nâng Gradle/plugin/Java version.

### Bài 24 — p90 ổn định nhưng median cải thiện?

**Đáp án:** median tốt hơn có ý nghĩa cho typical run, nhưng p90 không cải thiện có thể nghĩa tail bottlenecks vẫn tồn tại; phân tích sample distribution và nguyên nhân.

### Bài 25 — Build Scan được phép upload mọi nơi?

**Đáp án:** không. Nó có thể chứa logs/metadata nội bộ; kiểm tra privacy/access/repository policy. Không publish khi chưa có quyền.

### Bài 26 — Tối ưu configureEach có tác dụng lên phase nào?

**Đáp án:** chủ yếu giảm eager task configuration/realization, có thể giảm configuration overhead; cần profile before/after để biết lợi ích trên workload thực.

### Bài 27 — Sửa một method body nhưng chạy --rerun-tasks

**Đáp án:** không còn là incremental scenario chuẩn; --rerun-tasks buộc nhiều work items chạy lại. Bỏ flag và kiểm tra Gradle incremental compilation.

### Bài 28 — Java app lab in gì?

**Đáp án:** khi chạy :app:run, dòng do Java main in đúng là **BASELINE_OK: GRADLE**.

---

## 18. Checklist áp dụng trong dự án thật

- [ ] Mọi số đo có scenario ID và workload/task selector rõ?
- [ ] Có phân biệt thời gian bên ngoài (wall) với breakdown nội bộ Gradle?
- [ ] Có ghi Gradle Wrapper, Java daemon/toolchain, OS, CPU, RAM và disk?
- [ ] Có ghi commit/source tree và những flags đã sử dụng?
- [ ] Daemon được phân loại warm/cold?
- [ ] Không dùng --no-daemon làm proxy mơ hồ cho cold workspace?
- [ ] Wrapper download và dependency download được phân biệt với compile time?
- [ ] Build cache ON/OFF và hit/miss được ghi?
- [ ] Configuration cache ON/OFF và hit/miss được ghi?
- [ ] Dependency cache/network state giống nhau giữa trước và sau?
- [ ] No-op/clean/incremental được đo thành scenarios khác nhau?
- [ ] Clean scenario có nêu rõ tasks dọn output và có tính thời gian clean hay không?
- [ ] Không dùng --rerun-tasks để giả làm incremental build?
- [ ] Có ít nhất vài warmup runs trước measured samples?
- [ ] Có đủ samples để đọc median/p90 và noise?
- [ ] Không chỉ lấy một BUILD SUCCESSFUL in ... làm kết luận?
- [ ] Có phân biệt SUM task durations và elapsed/critical path?
- [ ] --profile/--scan được sử dụng để xác định phase chậm?
- [ ] Scan/publication phù hợp privacy/security policy?
- [ ] Có xem Settings and buildSrc, Loading/Configuring Projects riêng?
- [ ] Dependency resolution lúc configuration được theo dõi?
- [ ] Có xem UP-TO-DATE/FROM-CACHE/NO-SOURCE/EXECUTED outcomes?
- [ ] Trước–sau dùng cùng profiling instrumentation settings?
- [ ] Một lần chỉ thay một biến khi quy trách nhiệm optimization?
- [ ] Khi thay đổi Gradle/JDK, có đo baseline mới và lưu compatibility?
- [ ] CI runner/resource contention được kiểm soát hoặc ghi nhận?
- [ ] Build failures được loại khỏi success-duration samples có ghi chú?
- [ ] Report lưu median/p90, số mẫu và cách tính percentile?
- [ ] Có chạy functional correctness checks sau tối ưu?
- [ ] Có xem tác động lên critical path thay vì tối ưu tasks không ảnh hưởng wall?
- [ ] Có cơ chế rollback nếu hiệu năng xấu đi hoặc correctness thay đổi?

## Tài liệu chính thức và công cụ tham khảo

- [Gradle — Improve the Performance of Gradle Builds](https://docs.gradle.org/current/userguide/performance.html): baseline đầu tiên, daemon/build cache/configuration cache, configuration bottlenecks và dependency resolution.
- [Gradle — Build Scan / Profiling](https://docs.gradle.org/current/userguide/inspect.html): --scan, --profile, Startup, Settings and buildSrc, Loading Projects, Configuration và Tasks.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): --profile, --scan, --parallel, --max-workers, --build-cache, --configuration-cache, --no-daemon.
- [Gradle — The Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): daemon compatibility, warm/cold, single-use daemon và JVM args.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): org.gradle.caching, org.gradle.configuration-cache, org.gradle.jvmargs và build properties.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): skip configuration phase trên hit, inputs invalidation, task graph/parallelism.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): FROM-CACHE, task outputs, cache keys/relocatability.
- [Gradle — The Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization, configuration, execution.
- [Gradle — Gradle Profiler](https://github.com/gradle/gradle-profiler): benchmark scenarios, warmups, iterations, JSON/CSV và profiling tools.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): Gradle Wrapper/JDK compatibility.

**Kết luận:** Tối ưu Gradle build bắt đầu bằng **định nghĩa baseline có thể tái lập**, sau đó **tách startup, settings/buildSrc, configuration, dependency resolution và task execution** bằng --profile hoặc Build Scan, đo **external wall time** qua nhiều samples, đọc median/p90 và chỉ thay từng yếu tố một. **No-op, incremental, clean, cold/warm daemon và cache modes** phải là những kịch bản riêng. Không dùng sum task durations làm total elapsed khi tasks overlap, không coi UP-TO-DATE là FROM-CACHE, và không tuyên bố cải thiện chỉ bằng một lần chạy. Một performance optimization chỉ có giá trị khi **wall time trên workload thực sự giảm mà build vẫn đúng**.
# Maven Daemon và đánh giá hiệu quả trong môi trường cụ thể

## 1. Mục tiêu bài học

**Maven Daemon** (lệnh `mvnd`) là công cụ Apache giúp giảm chi phí khởi động lại Maven qua nhiều lần build. Thay vì mỗi lần gọi `mvn` đều tạo một JVM Maven mới rồi thoát khi hoàn tất, `mvnd` sử dụng **daemon JVM sống lâu hơn**, nhận nhiều yêu cầu từ client và tái sử dụng một số trạng thái của JVM/plugin giữa các lần chạy. Nó cũng hỗ trợ **build reactor nhiều module song song theo mặc định** và có console UI tối ưu cho parallel builds.

**Không được kết luận “mvnd luôn nhanh hơn Maven X%”** nếu chưa đo trên source tree, JDK, Maven/plugin versions, CPU/RAM, cache, network và loại job cụ thể. Một developer chạy `verify` nhiều lần trong cùng phiên có thể được lợi rõ rệt, trong khi một CI container chỉ chạy một build rồi bị xóa có thể không hưởng được JVM warm-up. Nếu `mvnd` dùng nhiều threads còn `mvn` chạy tuần tự, chênh lệch có thể đến từ **parallelism**, không chỉ daemon caching.

Nội dung tập trung vào:

1. Cơ chế daemon JVM, Maven Core/plugin classloaders, JIT, client/daemon và song song.
2. Cài đặt/cấu hình `mvnd`, trạng thái, dừng daemon, bộ nhớ và tính tương thích.
3. Phân biệt `mvnd` với `mvn`, Maven Wrapper `mvnw`, `-T`, `-B`, `-ntp`, build cache và Maven 4.
4. Đo **cold start, warm incremental, repeated clean build, parallel reactor, CPU/RAM** mà không thiên vị.
5. Lab Java 17 có Maven multi-module reactor, source/tests hoàn chỉnh, expected output và benchmark harness đo nhiều lần bằng `System.nanoTime`.
6. Phân tích số đo, quyết định sử dụng trên laptop/IDE/CI và những rủi ro về memory, plugin thread safety, shared daemons, secret isolation.
7. Troubleshooting, bài tập và checklist ra quyết định.

Tài liệu chính thức: [Apache Maven Daemon](https://maven.apache.org/tools/mvnd.html), [Apache Maven Daemon GitHub](https://github.com/apache/maven-mvnd) và [Apache Maven Downloads](https://maven.apache.org/download.cgi).

## 2. Maven truyền thống và mvnd chạy khác nhau thế nào?

### 2.1. Với Maven CLI thông thường

Một lệnh:

```bash
mvn -B -ntp clean verify
```

thường làm các việc:

```text
Shell/CI
  |
  +-- Java launcher tạo JVM Maven mới
  |
  +-- Khởi tạo Maven Core, classloaders, extension/plugin environment
  |
  +-- Đọc POM/settings, resolve model và dependencies/plugins
  |
  +-- Chạy lifecycle goals
  |
  +-- Maven process kết thúc
```

Mỗi lần gọi lại `mvn`, nhiều phần khởi động JVM/Maven và JIT warm-up phải thực hiện lại. **Artifacts đã tải trong `~/.m2/repository` vẫn có thể được cache** giữa các lần Maven thường; không nên so sánh mvnd với một Maven chạy không có local cache rồi nói toàn bộ chênh lệch do daemon.

### 2.2. Với Maven Daemon

Lệnh tương ứng:

```bash
mvnd -B -ntp clean verify
```

có kiến trúc:

```text
Native client mvnd / Java client fallback
  |
  +-- tìm daemon tương thích và đang rảnh
  |       |
  |       +-- nếu có: gửi build request
  |       |
  |       +-- nếu không có: tạo daemon JVM mới
  |
  +-- daemon JVM thực hiện Maven build
  |       |
  |       +-- giữ Maven Core / plugin classloaders
  |       +-- giữ JIT-optimized code
  |       +-- có thể phục vụ các build tiếp theo
  |       +-- có thể dùng reactor multi-module parallel
  |
  +-- client nhận logs/results/exit status
  |
  +-- daemon có thể tiếp tục sống khi build đã xong
```

Các lợi ích kỹ thuật được tài liệu dự án mô tả:
- **JVM reuse:** tránh khởi động JVM chạy build từ đầu cho mỗi request.
- **Plugin classloader reuse:** giảm chi phí đọc/parse plugin classes/JARs; dự án ghi chú SNAPSHOT plugin versions không được cache theo cơ chế này.
- **JIT reuse:** mã Maven Core, plugin và JDK đã được JIT tối ưu có thể dùng tiếp ở build sau.
- **Native client:** ở các nền tảng được hỗ trợ có launcher client do GraalVM native-image tạo, khởi động nhẹ hơn một JVM client thông thường.
- **Parallel reactor mặc định:** có thể sử dụng nhiều CPU cores để build nhiều modules độc lập.
- **Console output cho parallel builds:** hiển thị trạng thái modules, tổng hợp logs; thứ tự log có thể khác Maven thông thường.

Đây là cơ chế **tối ưu overhead**, không làm Java source “biên dịch nhanh hơn về bản chất” trong mọi project. Một build chủ yếu tốn 8 phút integration tests hoặc download network thường ít được lợi tỷ lệ phần trăm hơn một build nhỏ chủ yếu tốn Maven startup.

### 2.3. Reuse không giống bỏ qua kiểm thử

Chạy `mvnd verify` **không có nghĩa skip compiler, tests, plugins hoặc Maven lifecycle**. Nếu Maven goal chạy đúng và không có cấu hình skip, tests vẫn phải chạy; daemon giữ runtime/JIT, không biến `verify` thành một cached pass bí mật.

Cũng cần phân biệt:
- **Maven local repository cache:** file JAR/POM tải xuống disk.
- **mvnd daemon state/cache:** Maven JVM, plugin classloaders, JIT và metadata runtime.
- **Incremental compilation:** compiler/plugin có thể không biên dịch lại những source không đổi.
- **Build cache extension:** cơ chế khác có thể reuse outputs của goals theo inputs/checksums.
- **OS filesystem cache:** hệ điều hành cache disk blocks.

Khi benchmark, mỗi lớp đều có thể ảnh hưởng; không ghi kết luận sai về nguồn lợi ích.

## 3. mvnd so với Maven Wrapper, Maven 4 và -T

| Khía cạnh | `mvn` | `./mvnw` | `mvnd` |
| --- | --- | --- | --- |
| Maven distribution | Installed Maven trong PATH | Version Maven theo Wrapper properties | Maven Core được đóng gói trong mvnd distribution |
| JVM chạy Maven | Thường tạo mới mỗi invocation | Như Maven thường sau bootstrap | Daemon JVM giữ qua nhiều invocations |
| Reactor parallelism mặc định | Thường tuần tự | Như Maven thường | **Có thể parallel theo CPU cores** |
| CLI | Maven options | Maven options | Maven options + mvnd-specific |
| JDK | Machine/CI cung cấp | Machine/CI cung cấp | **Java 17+ cho daemon theo tài liệu mvnd** |
| Local repository | Có | Có | Có, không mất Maven cache semantics |
| Dùng trên ephemeral CI | Phù hợp baseline | Phù hợp reproducible tool bootstrap | Chỉ nên dùng sau benchmark/kiểm trust boundary |
| Commit gì vào Git | POM và source | Thêm mvnw/mvnw.cmd/properties | Không tự có checked-in launcher; phải provision mvnd riêng |

**Wrapper không tự khởi chạy mvnd.** Một repository có `mvnw` đã pin Maven version chưa có nghĩa `mvnd` sẽ sử dụng cùng Maven Core version. `mvnd` phát hành riêng, **nhúng Maven** và có release line riêng. Ghi lại output thực tế của `mvn --version`, `./mvnw --version`, `mvnd --version` để không so các core/toolchain khác nhau rồi đổ mọi chênh lệch cho daemon.

Theo trang download Apache trong giai đoạn tài liệu này, có **mvnd 1.0.6 (release)** và **mvnd 2.0.0-rc-3 (preview)**. Preview không nên tự động dùng làm production baseline. Đối chiếu trang download chính thức tại thời điểm triển khai; không xem version này là “latest mãi mãi”. Apache mvnd 1.x thuộc tuyến Maven 3.x; 2.x hướng Maven 4.x. **Không tự suy ra Maven Core patch version từ số hiệu mvnd**, kiểm tra runtime đã cài.

### 3.1. `mvn -T` không giống daemon

Maven thường cũng có tùy chọn parallel reactor:

```bash
mvn -B -ntp -T 4 clean verify
```

Nó cho phép nhiều modules không phụ thuộc nhau được xây song song, nhưng **mỗi invocation Maven thường vẫn là một JVM mới**. Ngược lại, `mvnd` có thể dùng nhiều modules song song **và** reuse daemon. Vì vậy đo:
- `mvn -T1` đối chiếu `mvnd -T1` để tách ảnh hưởng JVM reuse.
- `mvn` có parallelism được cấu hình đối chiếu `mvnd` default cho **throughput thực tế**, nhưng cần ghi rõ số threads.
- Không gọi `mvn` tuần tự và `mvnd` đa luồng là “apples-to-apples daemon benchmark”.

### 3.2. Default thread count của mvnd

Theo Apache Maven Daemon README, default parallelism của mvnd có dạng:

```java
Math.max(Runtime.getRuntime().availableProcessors() - 1, 1)
```

Số CPUs trong container có thể khác số cores vật lý; `availableProcessors()` phụ thuộc JVM/OS/cgroup configuration. Với project không hỗ trợ parallel builds, dùng:

```bash
mvnd -T1 -B -ntp clean verify
```

để chạy tuần tự. Với CI cần đo được nguyên nhân tăng tốc, **bắt đầu cả hai ở `-T1`** rồi mở thêm lượt đo parallel để đánh giá giới hạn CPU/resource. Tài liệu mvnd cũng có tùy chọn `-1`/`--serial` cho chế độ sát Maven thường (one thread, không buffering), nhưng `-T1` là cách quen thuộc để cố định số build threads khi benchmark.

### 3.3. Khi modules phụ thuộc nhau, không phải tất cả được chạy song song

Một reactor:

```text
root (pom)
  +-- math-core (jar) -----+
  |                       |
  +-- text-tools (jar) ---+-- task-app (jar)
```

`math-core` và `text-tools` độc lập, có thể được build cùng thời điểm. `task-app` phải đợi cả hai. Nếu các modules tạo thành chuỗi phụ thuộc dài, dù CPU nhiều, **parallel speedup có trần do critical path**. Đừng dùng số lượng modules làm đại diện trực tiếp cho khả năng song song.

## 4. Cài đặt mvnd và kiểm tra môi trường

### 4.1. Điều kiện

- Java/JDK **17 trở lên** cho mvnd daemon theo tài liệu dự án; JDK chạy application có thể có target khác nhờ toolchains/compiler.
- Binary distribution của mvnd phù hợp OS/architecture.
- Quyền chạy client executable, tạo daemon process, dùng local storage/registry và tải dependencies/plugins qua repository được duyệt.
- Dung lượng RAM đủ cho daemon JVM, Maven/plugins và forked test JVMs.
- Chính sách OS/cgroup/CI cho phép long-lived process nếu muốn tái sử dụng.

**Không được đảm bảo mọi platform có native client.** Apache mvnd cung cấp native client cho một số nền tảng; fallback launcher `mvnd.sh` trên Unix hoặc `mvnd.cmd` trên Windows có thể chạy Java client khi native image không có. Kiểm tra bảng supported platforms trong README của đúng release. Không download một binary dành cho kiến trúc khác rồi khắc phục bằng cách tắt bảo vệ hệ điều hành.

### 4.2. Download thủ công từ Apache

Dùng [Apache Maven Downloads](https://maven.apache.org/download.cgi), chọn **Maven Daemon release đã được duyệt** cho OS/architecture. Sau đó:
1. Download ZIP/tar.gz từ Apache distribution link chính thức.
2. Xác minh SHA-512/signature với nguồn KEYS tin cậy theo hướng dẫn Apache.
3. Giải nén vào thư mục tools được phép, không đè Maven cài sẵn.
4. Thêm `bin` của mvnd vào PATH cho phiên benchmark/terminal.
5. Provision JDK17+, xác minh `JAVA_HOME` nếu cần.
6. Chạy `mvnd --version` và `mvnd --help`.
7. Kiểm tra repository settings/mirror và local cache trước khi đo.

**Đây là hướng dẫn**, không đưa lệnh download giả hoặc checksum không có nguồn xác minh. Người dùng Windows có thể cần Microsoft Visual C++ runtime phù hợp với native client. Dự án cũng hỗ trợ SDKMAN!, Homebrew và một số installers; dùng package manager tin cậy nếu organization đã duyệt.

Ví dụ SDKMAN! trên môi trường có hỗ trợ:

```bash
sdk install mvnd
mvnd --version
```

Lệnh SDKMAN! lấy bản do package manager chọn; nếu cần benchmark reproducible, pin mvnd release và lưu version trong run metadata. Không so một máy vừa auto-upgrade mvnd với máy còn dùng bản cũ mà không ghi khác biệt.

### 4.3. Kiểm tra phiên bản và daemon state

```bash
java -version
mvn --version
mvnd --version
mvnd --status
mvnd --help
```

- `--version`: xác nhận mvnd distribution/Maven Core/JDK thực tế.
- `--status`: xem các daemon hiện có, trạng thái, IDs theo mvnd registry.
- `--help`: kiểm flags hỗ trợ ở đúng version.
- `--stop`: dừng **tất cả daemon instances trong registry tương ứng**, không chỉ daemon của project đang đứng.

**Không chạy `mvnd --stop` trên shared machine khi người khác đang build.** Nếu làm cold-start experiment, dùng máy/runner riêng hoặc phối hợp team và xác nhận không có session khác bị ảnh hưởng.

### 4.4. Không nhầm shutdown với clean

`mvnd --stop` dừng daemons, làm mất lợi thế warm JVM ở lần build sau; nó **không xóa** local Maven repository, Maven distribution, project `target` hoặc test artifacts. `mvn clean` xóa project build output trong `target` theo Clean Plugin, nhưng **không làm JVM daemon lạnh đi**.

Khi nói “cold build”, phải phân biệt:
- **Cold daemon:** không có usable daemon trước lệnh.
- **Cold project:** `target` chưa có hoặc vừa clean.
- **Cold dependency cache:** local repository chưa có plugins/dependencies.
- **Cold OS cache:** filesystem buffers chưa ấm.

Không gộp bốn trạng thái thành một khái niệm.

## 5. Cấu hình mvnd, bộ nhớ và khả năng cô lập

### 5.1. Các file properties

Theo mvnd README, configuration được đọc từ các địa điểm như:
- Path chỉ định bằng biến `MVND_PROPERTIES_PATH` hoặc system property `mvnd.propertiesPath`.
- `[PROJECT_HOME]/.mvn/mvnd.properties`.
- `[USER_HOME]/.m2/mvnd.properties`.
- `[MVND_HOME]/conf/mvnd.properties`.

**Đừng suy đoán precedence của các file bằng thứ tự liệt kê** khi có nhiều nơi ghi cùng key; kiểm documentation và actual effective behavior ở mvnd release đang dùng. Hãy tránh cấu hình trùng lặp nếu không cần.

Một config minh họa cho **máy dùng để benchmark có RAM đủ**, không phải mặc định áp cho mọi laptop:

```properties
# ~/.m2/mvnd.properties hoặc .mvn/mvnd.properties
mvnd.maxHeapSize = 2G
mvnd.idleTimeout = 30 minutes
mvnd.minThreads = 1
```

Đơn vị duration và cú pháp trong ví dụ là kiểu mvnd properties, cần đối chiếu parser/config của **version đã cài**; nếu gặp lỗi invalid property value, không im lặng bỏ qua. Việc tăng `maxHeapSize` không đảm bảo build nhanh hơn: có thể tăng memory footprint và GC pressure, đặc biệt trên CI runner có giới hạn RAM.

### 5.2. Thread counts và resource limits

Với parallel reactor, ngoài CPU dành cho build threads còn có:
- Maven daemon JVM.
- Forked JVMs của Surefire/Failsafe.
- Java compiler, annotation processors.
- Network download threads.
- Native processes: Node, Docker, database service, code generators.
- OS filesystem cache, container memory overhead.

Ví dụ runner 2 vCPU/4 GiB RAM không nên mặc định dùng 8 parallel build threads và 4 GiB daemon heap, vì tổng bộ nhớ sẽ vượt giới hạn. Xác minh:
1. `availableProcessors()` theo JVM.
2. `-T1` hoặc `-T2` để xây baseline.
3. Số Surefire forks và test process memory.
4. RAM peak/RSS của daemon **và tất cả child processes**.
5. Container OOM-kill events, GC pauses và CPU throttling.
6. Throughput khi CI runner có jobs khác chạy song song.

### 5.3. Khi cấu hình JVM đổi

Một daemon có thể được coi là không tương thích và mvnd tạo daemon khác khi một số **discriminating environment/config properties** thay đổi. Vì thế:
- Đừng mặc định sửa `JAVA_HOME` hoặc heap là đủ để daemon cũ nhận ngay mọi setting mới.
- Sau đổi JDK, config secrets, plugins/build extensions hoặc mvnd distribution, kiểm `mvnd --status` và phiên bản daemon.
- Trên máy test riêng, có thể stop daemon và chạy lại để xác minh effect; không dừng chung trên shared runner.
- Không giả định tất cả environment variables đều kích hoạt daemon mới.

### 5.4. Daemon lâu sống hơn build: rủi ro về trust boundary

Long-lived daemon có thể tái sử dụng JVM giữa các builds. Maven plugins là **code thực thi trong build process**, có thể đọc environment, filesystem, system properties và network. Trong shared CI có jobs từ nhiều users/PRs, reuse daemon giữa các mức độ tin cậy khác nhau cần được xem xét kỹ.

Best practices:
- **Không chia sẻ daemon giữa untrusted PRs và release jobs có secrets.**
- Cô lập theo OS user/container/runner/workspace/trust boundary.
- Không đặt signing keys/tokens trong POM, mvnd.properties được commit hoặc debug logs.
- Dừng daemon ở cuối ephemeral isolated job nếu hạ tầng yêu cầu teardown, nhưng điều này làm giảm hiệu quả reuse.
- Pin plugins/build extensions và nguồn dependencies.
- Theo dõi memory leak/stateful plugin behavior; nếu build không deterministic, so lại với Maven CLI và daemon mới.
- Không xem `mvnd` là sandbox: nó không hạn chế quyền của plugin code như một security boundary.

## 6. Benchmark mvnd đúng cách: điều cần đo

**Câu hỏi cần trả lời là:** “Với project và máy cụ thể, công việc nào nhanh hơn bao nhiêu, lặp lại có ổn định không, đổi lại mất gì về CPU/RAM và chất lượng build?”

Không phải “mvnd nhanh hơn Maven bao nhiêu trên Internet”. Cần benchmark **đúng workflow của team**.

### 6.1. Ma trận kịch bản

| Kịch bản | Maven CLI | mvnd | Mục đích |
| --- | --- | --- | --- |
| One-shot, daemon lạnh | `mvn -T1 clean verify` | `mvnd -T1 clean verify` sau môi trường daemon sạch | Chi phí khởi tạo |
| Warm incremental | `mvn -T1 verify` | `mvnd -T1 verify` với daemon đã warm | JVM/plugin reuse |
| Repeated clean builds | `mvn -T1 clean verify` | `mvnd -T1 clean verify` với daemon warm | Có lợi cả khi phải biên dịch lại? |
| Parallel throughput | `mvn -T N clean verify` | `mvnd -T N clean verify` | Tách effect parallel threads |
| Realistic defaults | Team's `mvn`/`mvnw` invocation | Team's `mvnd` invocation | Trải nghiệm thực tế, ghi rõ thread configs |
| CI ephemeral | Job dùng Maven cho một build | Job cài mvnd và dùng một build | Có bù chi phí provision/daemon? |
| CI persistent | Nhiều jobs/builds trong một trust boundary | Reused compatible daemon giữa builds | Có amortize startup nhưng an toàn không? |

**Đừng chạy CI deploy/sign/release thật để benchmark**. Chọn `verify` hoặc `clean verify` không có external side effects ngoài workspace/tests. Nếu test suite tạo DB/file/network effect, dùng môi trường test riêng.

### 6.2. Các biến phải giữ cố định

- Cùng Git commit/tag, source tree, POM, active profiles.
- JDK version/vendor/architecture cho Maven/mvnd processes.
- Maven Core/plugin versions **càng tương đồng càng tốt**; mvnd nhúng Maven nên phải ghi lại chênh lệch thật.
- Cùng local Maven repository và approved remote repositories; prefetch dependencies trước các warm runs.
- Cùng memory/CPU limits và không có heavy background jobs.
- Cùng `-B`, `-ntp`, `-T1` khi đo riêng daemon effect.
- Cùng tests, compiler flags, fork counts và environment variables.
- Cùng tình trạng `target` (verify incremental vs clean).
- Thứ tự chạy **đảo qua lại** thay vì 10 lần Maven trước rồi 10 lần mvnd sau.
- Không chỉ so một run, không ghi benchmark qua network download không kiểm soát.
- Ghi timestamps của experiment, versions và machine specs.
- Kiểm tra exit code và test reports, không tính failed run là “nhanh”.

**Phần quan trọng nhất:** `mvnd` thường chạy modules song song theo default, còn `mvn` thường tuần tự. Muốn đo daemon overhead, ép cả hai `-T1`. Muốn đo productivity thực, cho phép cả hai parallel cùng giới hạn rồi đo lại.

### 6.3. Cold-start measurement phải trung thực

Trên **máy test riêng**, trong trạng thái đã prefetch dependencies, một lượt minh họa:

```bash
mvnd --status
mvnd --stop
mvnd --status
mvnd -B -ntp -T1 clean verify
```

Lần đầu có thể mất thời gian khởi tạo daemon. Nhưng `--stop` chỉ dừng daemon, **không làm local repository hay OS cache lạnh**. Muốn đo Maven CLI cold startup, gọi Maven từ JVM mới; muốn đánh giá downloader/bootstrap, ghi riêng setup time.

**Không nhúng `mvnd --stop` trong script benchmark chạy trên máy chung**, vì nó có thể dừng build khác. Trong CI dùng disposable runner, setup/teardown controlled là lựa chọn phù hợp.

### 6.4. Warm-up và số lần chạy

Đề nghị cho kịch bản warm:
1. Chạy baseline trên source tree đúng, xác minh tests pass.
2. Gọi Maven và mvnd **2 lượt warm-up mỗi công cụ** (có thể hơn nếu JIT/OS cache dao động).
3. Đo tối thiểu **7 lượt** cho mỗi công cụ; dự án biến động lớn có thể cần 15–30.
4. Đảo thứ tự trên từng cặp để tránh lợi thế công cụ luôn chạy sau.
5. Ghi elapsed wall time, exit code, CPU/RSS/GC nếu có.
6. Tính **median** và độ phân tán (min/max hoặc p90).
7. So khả năng sử dụng RAM khi daemon **nhàn rỗi giữa các build**.
8. Lặp ở máy khác hoặc thời điểm khác trước khi áp quy định toàn team.

Nếu chỉ lấy build log `Total time`, bạn có thể bỏ qua phần client setup, file/log copying và setup ngoài Maven. Với câu hỏi “developer chờ bao lâu?”, **wall-clock từ lúc gọi process đến khi process exit** là metric hữu ích. Nếu hỏi riêng Maven lifecycle, cần thêm số liệu goal/plugin execution.

### 6.5. Cách tính

Giả sử:
- Median `mvn` là `T_mvn` giây.
- Median `mvnd` là `T_mvnd` giây.

Phần trăm giảm thời gian:

```text
time_reduction_% = 100 * (T_mvn - T_mvnd) / T_mvn
speedup_x        = T_mvn / T_mvnd
```

Ví dụ **số giả định chỉ để học công thức**:

```text
mvn median   = 12.0 s
mvnd median  =  9.0 s
time reduced = 25.0 %
speedup      = 1.33 x
```

Đây **không phải benchmark đã thực thi** và không chứng minh mvnd thắng 25% trên project bất kỳ. Nếu `mvnd` chậm hơn, `time_reduction_%` âm — ghi nhận trung thực thay vì bỏ sample.

### 6.6. Vì sao median tốt hơn một lần chạy?

Các build có outliers do JIT, GC, OS scheduling, antivirus, filesystem cache, CI network, test process startup. Median ít nhạy cảm với vài mẫu quá chậm, nhưng phải báo **số mẫu, warm-up, min/max và test failure count**. Với latency SLA, p90/p95 cũng có ích; với loop của developer, median và số lần build mỗi ngày thể hiện time saved.

## 7. Lab Maven Java 17 đa module, runnable từ đầu

Lab có **ba modules**:
- `math-core`: đếm số nguyên tố trong khoảng nhỏ.
- `text-tools`: chuẩn hóa tag bằng `Locale.ROOT`.
- `task-app`: dùng cả hai modules để in một dòng kết quả.

`math-core` và `text-tools` không phụ thuộc nhau, nên là hai nhánh **có thể chạy song song**; `task-app` phụ thuộc cả hai. Mã đủ nhỏ để benchmark minh họa startup overhead, không giả tạo một sleep dài khiến speedup vô nghĩa.

**Không có network/API credentials trong Java app.** Khi lần đầu Maven build, Maven cần tải JUnit và plugins theo `settings.xml`/mirrors; dùng approved repository. Có thể chạy `javac` trực tiếp để xác minh logic nếu không muốn tải plugin ngay.

### 7.1. Cây thư mục

```text
mvnd-performance-lab/
├── pom.xml
├── math-core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/training/perf/math/PrimeCounter.java
│       └── test/java/dev/training/perf/math/PrimeCounterTest.java
├── text-tools/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/training/perf/text/TextTag.java
│       └── test/java/dev/training/perf/text/TextTagTest.java
├── task-app/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/training/perf/app/App.java
│       └── test/java/dev/training/perf/app/AppTest.java
└── bench/
    └── BuildBench.java
```

Yêu cầu:
- JDK 17+ để compile/run Java examples.
- Apache Maven 3.x cho lệnh `mvn` baseline (chọn version và ghi rõ).
- mvnd release phù hợp đã tải riêng và chạy cùng JDK17+.
- Network hoặc trusted cache để tải Maven plugins và JUnit khi thiếu.
- Workspace riêng; không chạy deploy, Docker hoặc benchmark trên repository phát hành.
- Khi so Maven và mvnd, kiểm Maven Core version embedded trong mvnd để nhận biết khác biệt.

### 7.2. Tạo folders trên Unix

```bash
mkdir -p mvnd-performance-lab/math-core/src/main/java/dev/training/perf/math
mkdir -p mvnd-performance-lab/math-core/src/test/java/dev/training/perf/math
mkdir -p mvnd-performance-lab/text-tools/src/main/java/dev/training/perf/text
mkdir -p mvnd-performance-lab/text-tools/src/test/java/dev/training/perf/text
mkdir -p mvnd-performance-lab/task-app/src/main/java/dev/training/perf/app
mkdir -p mvnd-performance-lab/task-app/src/test/java/dev/training/perf/app
mkdir -p mvnd-performance-lab/bench
cd mvnd-performance-lab
```

Windows PowerShell:

```powershell
$root = "mvnd-performance-lab"
$dirs = @(
    "math-core/src/main/java/dev/training/perf/math",
    "math-core/src/test/java/dev/training/perf/math",
    "text-tools/src/main/java/dev/training/perf/text",
    "text-tools/src/test/java/dev/training/perf/text",
    "task-app/src/main/java/dev/training/perf/app",
    "task-app/src/test/java/dev/training/perf/app",
    "bench"
)
foreach ($d in $dirs) {
    New-Item -ItemType Directory -Force -Path "$root/$d" | Out-Null
}
Set-Location $root
```

Tạo các file tiếp theo **đúng tên và vị trí**. Những command không tự generate source; source bên dưới là nội dung cần lưu.

### 7.3. Root aggregator POM: `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.training.perf</groupId>
    <artifactId>mvnd-performance-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>math-core</module>
        <module>text-tools</module>
        <module>task-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
        <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.6.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Giải thích:
- Root có `packaging=pom` và là reactor aggregator.
- `math-core`/`text-tools` độc lập; `task-app` phụ thuộc chúng, Maven graph bảo đảm thứ tự đúng.
- `pluginManagement` ghim versions khi lifecycle bind compiler/test/JAR plugins, kể cả khi child POMs không liệt kê chúng.
- Java target 17; JUnit dùng cho tests.
- `outputTimestamp` giúp các plugins phù hợp tạo reproducible archive timestamps; không có nghĩa mọi JAR trên mọi máy luôn cùng hash.
- Không dùng `-DskipTests` hoặc `-fn` trong benchmark.
- Không cấu hình deployment; lab chỉ `verify`.

### 7.4. `math-core/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.training.perf</groupId>
        <artifactId>mvnd-performance-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>math-core</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 7.5. `text-tools/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.training.perf</groupId>
        <artifactId>mvnd-performance-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>text-tools</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 7.6. `task-app/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.training.perf</groupId>
        <artifactId>mvnd-performance-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>task-app</artifactId>

    <dependencies>
        <dependency>
            <groupId>dev.training.perf</groupId>
            <artifactId>math-core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>dev.training.perf</groupId>
            <artifactId>text-tools</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Khi gọi root `mvn verify` hoặc `mvnd verify`, reactor cung cấp artifacts các module cùng GAV version, không cần `mvn install` từng module trước. **Không chạy `task-app` standalone từ một clean local repository khi chưa có internal dependencies**; dùng root reactor hoặc `-pl :task-app -am`.

### 7.7. Java source: `PrimeCounter.java`

Tệp `math-core/src/main/java/dev/training/perf/math/PrimeCounter.java`:

```java
package dev.training.perf.math;

public final class PrimeCounter {

    private PrimeCounter() {
    }

    public static int countUpTo(int maximum) {
        if (maximum < 2) {
            return 0;
        }
        if (maximum > 100_000) {
            throw new IllegalArgumentException("demo maximum is 100000");
        }

        int count = 0;
        for (int candidate = 2; candidate <= maximum; candidate++) {
            boolean prime = true;
            for (int divisor = 2;
                    divisor <= candidate / divisor;
                    divisor++) {
                if (candidate % divisor == 0) {
                    prime = false;
                    break;
                }
            }
            if (prime) {
                count++;
            }
        }
        return count;
    }
}
```

Giới hạn `100_000` chỉ giữ demo nhỏ, không phải thuật toán tối ưu production. `candidate / divisor` giúp tránh overflow phép `divisor * divisor`; với những giá trị nhỏ của lab, kết quả đếm là deterministic. **Không thêm `Thread.sleep` cố tình làm nặng test để “chứng minh” mvnd nhanh** — như vậy sẽ đo sự chờ không có ích.

### 7.8. Java tests: `PrimeCounterTest.java`

Tệp `math-core/src/test/java/dev/training/perf/math/PrimeCounterTest.java`:

```java
package dev.training.perf.math;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PrimeCounterTest {

    @Test
    void countsPrimesUpToThirty() {
        assertEquals(10, PrimeCounter.countUpTo(30));
    }

    @Test
    void numbersBelowTwoHaveNoPrimes() {
        assertEquals(0, PrimeCounter.countUpTo(-5));
        assertEquals(0, PrimeCounter.countUpTo(1));
    }

    @Test
    void countsPrimesUpToOneHundred() {
        assertEquals(25, PrimeCounter.countUpTo(100));
    }
}
```

Có **3 tests** trong module `math-core`.

### 7.9. Java source: `TextTag.java`

Tệp `text-tools/src/main/java/dev/training/perf/text/TextTag.java`:

```java
package dev.training.perf.text;

import java.util.Locale;

public final class TextTag {

    private TextTag() {
    }

    public static String normalize(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("tag is required");
        }
        return input.strip().toLowerCase(Locale.ROOT);
    }
}
```

`Locale.ROOT` giữ normalization không phụ thuộc default language/region của máy. Nếu dùng `toLowerCase()` theo locale người dùng, identifiers/test results có thể khác trên một số môi trường.

### 7.10. Java tests: `TextTagTest.java`

Tệp `text-tools/src/test/java/dev/training/perf/text/TextTagTest.java`:

```java
package dev.training.perf.text;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TextTagTest {

    @Test
    void normalizesTrimAndCase() {
        assertEquals("maven", TextTag.normalize("  MAVEN  "));
    }

    @Test
    void rejectsBlank() {
        assertThrows(IllegalArgumentException.class,
            () -> TextTag.normalize(" \t "));
    }
}
```

Có **2 tests** trong module `text-tools`.

### 7.11. Java application: `App.java`

Tệp `task-app/src/main/java/dev/training/perf/app/App.java`:

```java
package dev.training.perf.app;

import dev.training.perf.math.PrimeCounter;
import dev.training.perf.text.TextTag;

public final class App {

    private App() {
    }

    public static String summary() {
        return "primes=" + PrimeCounter.countUpTo(30)
            + ";tag=" + TextTag.normalize("  MAVEN  ");
    }

    public static void main(String[] args) {
        System.out.println(summary());
    }
}
```

Sau khi build thành công, **stdout riêng của Java application** chính xác:

```text
primes=10;tag=maven
```

Nó không phải toàn bộ Maven console output; Maven thường in build phases/test logs/Total time tùy version và settings.

### 7.12. Java tests: `AppTest.java`

Tệp `task-app/src/test/java/dev/training/perf/app/AppTest.java`:

```java
package dev.training.perf.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {

    @Test
    void summaryCombinesBothModules() {
        assertEquals("primes=10;tag=maven", App.summary());
    }
}
```

Có **1 test** trong module `task-app`. Tổng toàn reactor: **3 + 2 + 1 = 6 JUnit Jupiter tests**. Parent packaging `pom` không có tests.

### 7.13. Build baseline bằng Maven

Từ root lab:

```bash
java -version
mvn --version
mvn -B -ntp -T1 clean verify
```

Khi network/cache và JDK hợp lệ, Maven nên chạy các tests và tạo:
- `math-core/target/math-core-1.0.0.jar`.
- `text-tools/target/text-tools-1.0.0.jar`.
- `task-app/target/task-app-1.0.0.jar`.

Surefire test totals theo các class đã viết:
- `math-core`: 3 tests.
- `text-tools`: 2 tests.
- `task-app`: 1 test.
- Tổng: **6 tests, 0 failures, 0 errors, 0 skipped** khi lab chạy chuẩn.

**Không giả định Maven in một summary duy nhất “Tests run: 6”**, vì Surefire reports thường theo từng module. Có thể kiểm XML reports dưới `*/target/surefire-reports` để xác minh tổng. Đừng chỉ nhìn `BUILD SUCCESS` nếu đã có flag skip-tests trong environment.

### 7.14. Build tương đương bằng mvnd

```bash
mvnd --version
mvnd -B -ntp -T1 clean verify
```

Khi cả hai commands pass, output artifacts và các tests phải có cùng behavior theo contract. **Không khẳng định build bytes/hash bằng nhau chỉ vì hai commands pass**; Maven Core/plugin/runtime và ZIP metadata có thể khác. Đo runtime chỉ khi chất lượng tests, scopes và lifecycle goal giống nhau.

Bỏ `-T1` để quan sát mvnd mặc định có parallel reactor:

```bash
mvnd -B -ntp clean verify
```

Sau đó đối chiếu với Maven cũng cho phép parallel:

```bash
mvn -B -ntp -T2 clean verify
mvnd -B -ntp -T2 clean verify
```

Lựa chọn `-T2` chỉ là ví dụ để **cố định hai build threads**, không phải gợi ý mọi runner đều phải dùng 2. Kiểm xem unit tests/third-party plugins có an toàn khi parallel. Nếu chưa chắc, dùng `-T1`.

### 7.15. Chạy ứng dụng sau khi build

Linux/macOS:

```bash
java -cp "task-app/target/classes:math-core/target/classes:text-tools/target/classes" dev.training.perf.app.App
```

Windows PowerShell:

```powershell
java -cp "task-app\target\classes;math-core\target\classes;text-tools\target\classes" dev.training.perf.app.App
```

**Stdout mong đợi:**

```text
primes=10;tag=maven
```

Chạy với `-cp` vì lab không cấu hình `Main-Class` manifest hoặc fat JAR. Không dùng `java -jar task-app/target/task-app-1.0.0.jar` rồi kết luận lab hỏng nếu JVM báo thiếu Main-Class/MathCore: đó là khác biệt packaging/classpath.

## 8. Java 17 benchmark harness: nhiều mẫu, median, logs và so công bằng

Phần này tạo một file độc lập `bench/BuildBench.java`. Nó dùng **JDK standard library** để:
- Khởi chạy `mvn` và `mvnd` như child processes.
- Cố định `-B -ntp -T1` cho cả hai.
- Chạy **2 warm-up mỗi tool**.
- Đo **ít nhất 7 samples** mỗi tool, **đảo thứ tự** qua các cặp.
- Chỉ ghi elapsed wall-clock từ lúc start process đến lúc exit.
- Ghi Maven logs của từng run vào `benchmark-logs/` (không làm tràn console).
- Kiểm child exit code; nếu fail, **dừng benchmark và báo path log**, không đưa lỗi vào median.
- In CSV sample seconds, median và % giảm thời gian.

**Lưu ý:** script không đo “cold daemon” vì không gọi `mvnd --stop` (đó là thao tác không nên tự động làm trên máy dùng chung). Harness đo **warm/repeated** workload. Với `clean` mode, `clean verify` vẫn biên dịch lại project nhưng daemon JVM đã warm; không gọi nhầm “cold daemon”.

### 8.1. Java source: `bench/BuildBench.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public final class BuildBench {

    private BuildBench() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.err.println(
                "Usage: BuildBench <verify|clean> <repetitions> "
                + "<mvn-launcher> <mvnd-launcher>");
            System.exit(2);
            return;
        }

        String mode = args[0];
        if (!mode.equals("verify") && !mode.equals("clean")) {
            throw new IllegalArgumentException(
                "mode must be verify or clean");
        }

        int repetitions = Integer.parseInt(args[1]);
        if (repetitions < 3 || repetitions > 30) {
            throw new IllegalArgumentException(
                "repetitions must be from 3 to 30");
        }

        String mvn = args[2];
        String mvnd = args[3];
        List<Double> mvnTimes = new ArrayList<>();
        List<Double> mvndTimes = new ArrayList<>();

        System.err.println("Warm-up: 2 runs per tool");
        for (int i = 1; i <= 2; i++) {
            run("mvn", mvn, mode, i, true);
            run("mvnd", mvnd, mode, i, true);
        }

        System.out.println("tool,scenario,run,seconds");
        for (int i = 1; i <= repetitions; i++) {
            if (i % 2 == 1) {
                mvnTimes.add(run("mvn", mvn, mode, i, false));
                mvndTimes.add(run("mvnd", mvnd, mode, i, false));
            } else {
                mvndTimes.add(run("mvnd", mvnd, mode, i, false));
                mvnTimes.add(run("mvn", mvn, mode, i, false));
            }
        }

        double m = median(mvnTimes);
        double d = median(mvndTimes);
        double savedPercent = 100.0 * (m - d) / m;

        System.out.printf(Locale.ROOT,
            "median_mvn=%.3fs,median_mvnd=%.3fs,saved=%.1f%%%n",
            m, d, savedPercent);
        System.out.println(
            "All measured builds exited successfully.");
    }

    private static double run(
            String label,
            String launcher,
            String mode,
            int sample,
            boolean warmup)
            throws IOException, InterruptedException {

        List<String> command = new ArrayList<>();
        String lower = launcher.toLowerCase(Locale.ROOT);
        boolean windows = System.getProperty("os.name")
            .toLowerCase(Locale.ROOT).contains("win");

        // Windows .cmd/.bat requires the command interpreter.
        if (windows &&
                (lower.endsWith(".cmd") || lower.endsWith(".bat"))) {
            command.add("cmd.exe");
            command.add("/d");
            command.add("/c");
        }

        command.add(launcher);
        command.add("-B");
        command.add("-ntp");
        command.add("-T1");
        if (mode.equals("clean")) {
            command.add("clean");
        }
        command.add("verify");

        Path dir = Path.of("benchmark-logs");
        Files.createDirectories(dir);
        String suffix = warmup ? "-warmup" : "";
        Path log = dir.resolve(
            label + "-" + mode + "-" + sample + suffix + ".log");

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.redirectErrorStream(true);
        builder.redirectOutput(log.toFile());

        long start = System.nanoTime();
        Process process = builder.start();
        boolean finished = process.waitFor(20, TimeUnit.MINUTES);
        if (!finished) {
            process.destroyForcibly();
            throw new IllegalStateException(
                "Build timed out; see " + log);
        }
        int code = process.exitValue();
        double seconds = (System.nanoTime() - start) / 1e9;

        if (code != 0) {
            throw new IllegalStateException(
                "Build failed: " + label + ", exit=" + code
                + ", see " + log);
        }

        if (!warmup) {
            System.out.printf(Locale.ROOT,
                "%s,%s,%d,%.3f%n",
                label, mode, sample, seconds);
        }
        return seconds;
    }

    private static double median(List<Double> values) {
        List<Double> sorted = new ArrayList<>(values);
        Collections.sort(sorted);
        int size = sorted.size();
        int half = size / 2;
        if (size % 2 == 1) {
            return sorted.get(half);
        }
        return (sorted.get(half - 1) + sorted.get(half)) / 2;
    }
}
```

**Phân tích tính đúng của harness:**
- Java 17 hỗ trợ `ProcessBuilder`, `Path.of`, `System.nanoTime` và `waitFor(timeout, TimeUnit)`.
- `-T1` giữ reactor tuần tự cho cả hai, tránh lẫn lợi ích parallelism.
- `ProcessBuilder` capture combined stdout/stderr vào file; không deadlock vì redirect trực tiếp sang disk.
- `System.nanoTime` thích hợp đo elapsed time, không dùng wall clock timezone.
- `mvn` và `mvnd` được truyền **dưới dạng launcher argument**, tránh hard-code path trong Java.
- Trên Windows, launcher có suffix `.cmd` hoặc `.bat` đi qua `cmd.exe /d /c`. Nếu có native `mvnd.exe`, truyền đường dẫn executable đó trực tiếp và không dùng `cmd.exe`.
- Hai lượt warm-up cho mỗi tool **không được đưa vào median**. Mỗi cặp đo đảo thứ tự khi sample index chẵn.
- Nếu bất kỳ run nào exit non-zero hoặc timeout, harness **không in kết luận median giả**; xem log và sửa nguyên nhân.
- `benchmark-logs/` là output local, không chứa secrets trong ví dụ; trong dự án thật có thể cần sanitize Maven logs/headers/URLs trước khi chia sẻ.
- Timeout 20 phút là **giới hạn thử nghiệm**, có thể chỉnh theo workload; tránh benchmark treo vô hạn.

**Hạn chế:** harness không tự đo CPU/RSS, không loại bỏ mọi noise, không bảo đảm exact same Maven Core giữa hai distributions, và không test cold daemon. Nó là một công cụ lặp lại có thể review và mở rộng, không phải microbenchmark khoa học cho mọi project.

### 8.2. Compile harness không cần Maven

Linux/macOS từ root `mvnd-performance-lab`:

```bash
mkdir -p bench/out
javac -d bench/out bench/BuildBench.java
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "bench/out" | Out-Null
javac -d "bench/out" "bench/BuildBench.java"
```

Nên chạy baseline `mvn -B -ntp -T1 clean verify` và `mvnd -B -ntp -T1 clean verify` **một lần bên ngoài harness** để đảm bảo plugin/dependency caches đã có và mọi tests pass.

### 8.3. Đo repeated incremental verify

Linux/macOS:

```bash
java -cp bench/out BuildBench verify 7 mvn mvnd
```

Windows PowerShell nếu `mvn.cmd` và `mvnd.cmd` nằm trong PATH:

```powershell
java -cp "bench/out" BuildBench verify 7 mvn.cmd mvnd.cmd
```

Nếu Windows dùng mvnd native client `mvnd.exe` thay vì script, truyền `mvnd.exe` ở argument cuối. Có thể truyền **đường dẫn executable tuyệt đối** dưới dạng một CLI argument nếu không có trên PATH, nhưng phải đúng file đã được duyệt. Không ghép quotes/path bằng chuỗi tùy ý trong Java.

Output sample **có dạng** (các số dưới đây chỉ minh họa format, KHÔNG phải kết quả thực tế):

```text
tool,scenario,run,seconds
mvn,verify,1,3.421
mvnd,verify,1,1.850
...
median_mvn=3.400s,median_mvnd=1.900s,saved=44.1%
All measured builds exited successfully.
```

Dấu `...` ở ví dụ trên **chỉ ký hiệu các sample rows còn lại được lược trong văn bản**, không phải dòng mà chương trình in. Mỗi công cụ phải có **7 measurement rows**, tức 14 rows CSV chưa kể header/summary; warm-up logs vẫn được lưu riêng. Đừng copy numbers minh họa vào báo cáo performance.

### 8.4. Đo repeated clean builds

Linux/macOS:

```bash
java -cp bench/out BuildBench clean 7 mvn mvnd
```

Windows PowerShell:

```powershell
java -cp "bench/out" BuildBench clean 7 mvn.cmd mvnd.cmd
```

Mỗi run dùng `clean verify`, nên project outputs được rebuild; tuy nhiên **daemon đã được warm-up**. Đây là workload khác incremental `verify`. Một project có annotation processing/code generation lớn có thể thấy chênh lệch nhỏ hơn vì compile/test cost chiếm phần lớn thời gian.

### 8.5. Chạy parallel test tách biệt

Với reactor có modules độc lập:

```bash
mvn -B -ntp -T2 clean verify
mvnd -B -ntp -T2 clean verify
```

Chỉ chạy ở môi trường thích hợp. So với `-T1`:
- Nếu cả hai đều nhanh hơn tương tự, khả năng phần tăng đến từ parallel module schedule.
- Nếu mvnd đặc biệt nhanh trong các repeated builds, JVM/classloader reuse có thể đóng góp.
- Nếu `-T2` chậm hơn `-T1`, project có thể bị CPU/IO contention hoặc tests không thread-safe.
- Nếu có lỗi concurrency, cần xử lý shared build outputs, temp files, ports, global static caches, code generators hoặc plugin thread safety.

Đừng lấy “parallel mặc định mvnd” làm bằng chứng nền tảng cho mọi reactor. Với 3 modules chỉ một số được chạy đồng thời, speedup bị ràng buộc bởi dependency graph.

### 8.6. So khớp correctness trước performance

Một benchmark có ý nghĩa phải kiểm:
- `mvn` và `mvnd` đều exit **0**.
- Test reports không có failures/errors/skip ngoài policy.
- Không có `-DskipTests`, `-fn` hoặc profile khác giữa hai calls.
- Cùng version code và dependencies/plugin repos.
- Không có build output bị một công cụ làm khác behavior.
- App chạy ra `primes=10;tag=maven`.
- Artifact hashes/provenance có thể được so riêng nếu yêu cầu reproducibility.

**Nếu mvnd build “nhanh” vì bỏ test hoặc plugin fail mà exit bị che, đó là thất bại của benchmark.**

## 9. CPU, memory, GC và energy trade-offs

### 9.1. Không chỉ đo elapsed time

Một daemon thường **vẫn giữ JVM heap/RSS sau build**, kể cả khi user đã nhìn thấy terminal prompt. Điều này có thể xứng đáng trên máy developer build nhiều lần, nhưng trên laptop RAM hạn chế hoặc CI host chia nhiều tenants, bộ nhớ nhàn rỗi đó có chi phí.

Thu thập tối thiểu:
- **Wall-clock median** của `verify` và `clean verify`.
- **RSS/working set** của daemon JVM khi build và khi idle.
- **Peak memory** gồm Surefire JVMs và child processes.
- CPU utilization và throttling.
- GC pause/time khi có dấu hiệu memory pressure.
- Số daemon instances, tuổi/idle timeout.
- Điện năng/nhiệt/tiếng quạt (nếu trên laptop).
- Tần suất và độ dài vòng feedback thực tế của developer.

### 9.2. Ghi RSS và CPU theo OS

Linux có thể dùng `ps`/`top`, Windows dùng Task Manager/Resource Monitor hoặc PowerShell `Get-Process`. Ví dụ **lệnh quan sát** không tự tác động state:

```bash
mvnd --status
ps -eo pid,rss,%cpu,command
```

Kết quả cần lọc process của daemon và child JVMs theo người dùng/machine, tránh nhầm JVM IDE với mvnd. `ps` chỉ là snapshot, **không đại diện cho peak RSS**; muốn peak cần monitor theo thời gian hoặc metric từ cgroup/JFR/OS tooling.

Windows PowerShell ví dụ:

```powershell
mvnd --status
Get-Process java,javaw -ErrorAction SilentlyContinue |
    Select-Object Id,ProcessName,CPU,WorkingSet64
```

Các process mang tên `java` còn có IDE/server/ứng dụng khác; cần correlate PID từ mvnd status/process command line. Memory số liệu dưới `WorkingSet64` là bytes và `CPU` là accumulated process CPU time, **không phải CPU percentage tại thời điểm hiện tại**.

### 9.3. Tính ngưỡng lợi ích thực

Giả sử dữ liệu benchmark thật cho project:
- Developer chạy 20 lượt `verify` mỗi ngày.
- Median Maven thường là `12s`, mvnd `9s`.
- Chênh lệch mỗi lượt là `3s`.

Lợi ích lý thuyết:

```text
20 builds/day * 3 seconds/build = 60 seconds/day
```

Đây là **ví dụ tính toán**, không phải đo trên dự án cụ thể. Cần trừ:
- Cold-start và chi phí setup mvnd.
- Idle memory impact.
- Các trường hợp daemon hết hạn hoặc bị stop.
- Time mất do lỗi plugin/concurrency.
- Khác biệt về debugging/output.
- Chi phí CI caching/provisioning/teardown nếu triển khai.

Nếu project chỉ build một lần/ngày, vài giây warm benefit có thể không đáng trả chi phí vận hành thêm. Nếu một reactor lớn có hàng trăm incremental builds mỗi ngày, kết quả có thể khác.

## 10. Khi nào nên dùng mvnd?

### 10.1. Developer workstation

**Thường là ứng viên tốt** nếu:
- Developer chạy Maven nhiều lần trong phiên làm việc.
- JDK/Maven ổn định và đủ RAM.
- Plugins dùng ổn định, không có state leak.
- Project multi-module có nhánh độc lập và thread-safe.
- Daemon được giữ trong cùng trust boundary cá nhân.

Quy trình thử:
1. Đảm bảo `mvn clean verify` là baseline đáng tin.
2. Cài mvnd đã kiểm checksum/signature.
3. Chạy `mvnd -T1 verify` nhiều lần.
4. So with `mvn -T1 verify`, benchmark median.
5. Mở parallel modes khi tests/plugins an toàn.
6. Theo dõi idle RSS và trải nghiệm máy.
7. Nếu không lợi, quay lại Maven/Wrapper; không cố ép cả team dùng daemon.

### 10.2. IDE

IDE có Maven integration có thể sử dụng embedded/external Maven runtime; **không tự động sử dụng mvnd** khi user nhấn Build. Nếu muốn IDE sử dụng mvnd cần xem IDE/extension hỗ trợ thực tế.

Đánh giá:
- IDE Maven importer có thực sự gọi mvnd hay chỉ embedded Maven?
- Run configurations có dùng đúng Maven/Java versions không?
- IntelliJ/Eclipse internal incremental compilation có thể nhanh hơn gọi Maven cho mỗi file save; đừng kết luận mvnd thay compiler của IDE.
- Thử same code path/goal trên CLI trước khi so UI build timings.
- Không thay Maven version/JDK chỉ để một plugin IDE hoạt động mà chưa kiểm compatibility.

### 10.3. CI ephemeral runner

CI job sống vài phút, tạo container mới, chạy một `verify` rồi xóa:
- Daemon **không có nhiều lần build để amortize startup**.
- Download/installation mvnd và startup daemon là cost.
- Nếu CI task phần lớn integration tests/network, warm JIT ít ảnh hưởng.
- Teardown container dừng daemon sau một invocation.
- Parallelism có thể giúp, nhưng Maven thường cũng có `-T`.

**Mặc định giữ Maven Wrapper/Maven CLI trong CI ephemeral** trừ khi benchmark trên runner thật chứng minh mvnd có lợi đáng kể và team có kế hoạch versioning/cache/security. Không chọn mvnd chỉ vì developer laptop thấy ấn tượng.

### 10.4. CI persistent runners

Persistent runner xử lý nhiều builds của **cùng dự án/trust boundary** có thể tái sử dụng daemon và giảm latency. Tuy nhiên:
- Cần process isolation theo user/project.
- Không reuse daemon giữa untrusted PR và secrets-bearing release.
- Quy định idle timeout, max daemons, RAM limits.
- Cập nhật/stop daemon khi đổi JDK, mvnd version, security policy hoặc compromised workspace.
- Theo dõi memory leaks và long-lived classloader effects.
- So throughput tổng hệ thống, không chỉ latency một job.
- Không dùng random global `mvnd --stop` khi workers khác đang build.

### 10.5. Plugin compatibility và side effects

Một số Maven plugins giữ mutable static state, dùng tmp path/port cố định, không thread-safe hoặc giả định mỗi invocation JVM mới. Daemon reuse và parallel reactor có thể làm lộ bugs. Khi gặp lỗi chỉ xuất hiện ở mvnd:
1. Thử `mvnd -T1 clean verify` để loại concurrent module builds.
2. Kiểm plugin versions và logs của module hỏng.
3. So với `mvn -T1 clean verify` trên cùng JDK/settings.
4. Trên **máy test riêng**, restart daemon rồi thử lại để kiểm trạng thái tích lũy.
5. Đánh giá test isolation, static caches, forked JVM settings, local ports/files.
6. Báo issue có reproducer tối giản, không ép `-fn`/skipTests.
7. Nếu problem không thể xử lý, dùng Maven thường cho workflow đó.

## 11. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng cao | Việc cần kiểm |
| --- | --- | --- |
| `mvnd: command not found` | Chưa cài/không ở PATH | mvnd distribution bin, executable permissions |
| Java version unsupported | mvnd daemon yêu cầu Java 17+ | `java -version`, `mvnd --version`, `JAVA_HOME` |
| Native client không chạy | OS/arch/runtime mismatch | Chọn artifact đúng, Java client fallback khi hỗ trợ |
| Windows native client thiếu runtime DLL | Visual C++ runtime chưa cài | Xem official README, cài runtime được duyệt |
| Build lần đầu chậm | Startup/JIT/plugin caches lạnh | Đo warm-up và cold riêng |
| mvnd không nhanh hơn mvn | Project test/IO bound, 1 build, overhead | Chia scenarios, đo median, kiểm thread parity |
| mvnd nhanh hơn bất thường | mvnd default parallel, Maven serial | Cả hai `-T1` rồi so lại |
| mvnd dùng nhiều RAM | Daemon JVM giữ heap hoặc nhiều instances | `mvnd --status`, RSS, heap, idle timeout |
| CI OOM-killed | CPU/RAM limits, forked tests, parallelism | Giảm `-T`/heap, inspect cgroup |
| Log task-app đến sau khi core hoàn tất | Reactor dependencies và buffered logs | Hiểu module order; `--raw-streams` nếu cần |
| Tests flake khi parallel | Plugin/test shared files/ports/static state | `-T1`, isolate fixtures, sửa race |
| Build chỉ fail sau vài lần mvnd | Cached plugin state/long-lived JVM | So daemon fresh vs warm, tìm state leak |
| mvnd báo nhiều daemon instances | Incompatible env/config hoặc concurrent builds | Inspect status và properties |
| mvnd --stop ảnh hưởng team | Shared daemon registry | Chỉ stop trên isolated machine sau phối hợp |
| Cùng project nhưng kết quả khác | Maven Core/settings/JDK/profiles/threads khác | So `--version`, effective settings/POM, options |
| Plugin chạy interactive bị treo | Prompt/credentials/TTY | `-B`, pre-provision secrets, CI timeout |
| mvnd không tương thích extension | Plugin/core extension assumptions | Reproduce minimal, dùng Maven CLI fallback |
| Wrapper và mvnd dùng versions khác | Separate distributions | Ghi rõ Maven Core versions, align khi có thể |
| CI build xanh dù tests bị skip | Flags/CI job rules | Test reports, exit codes, quality gates |
| Daemon log chứa secrets | Debug/third-party plugins | Sanitize logs, restrict access/rotate secrets |
| Một benchmark quá đẹp | Đo lần đầu vs cached run, thiếu control | Counterbalance warm-up, repeat median |

### 11.1. Diagnostic commands an toàn

```bash
java -version
mvn --version
mvnd --version
mvnd --status
mvnd -B -ntp -T1 -e validate
```

`-e` giúp in stack trace trong một số lỗi. Không bật `-X` debug mặc định trên CI có secrets. Đừng chia sẻ `~/.m2/settings.xml` hoặc mvnd logs chứa internal URLs/credentials lên diễn đàn công khai.

### 11.2. Raw streams và plugin output

mvnd có thể thu/buffer `System.out` từ plugins theo project. Nếu một automation cần **stdout không đổi** (ví dụ lấy value từ `help:evaluate`), Apache README gợi ý thêm `--raw-streams`:

```bash
mvnd help:evaluate -Dexpression=project.version -q -DforceStdout --raw-streams
```

Tùy plugin/version, cần xác minh stdout/stderr cụ thể, không parse human-readable parallel UI bằng regex thiếu kiểm soát. Đối với chương trình Java `App` trong lab, dùng `java -cp ...` riêng để lấy stdout ổn định, **không lấy output đó từ log mvnd**.

## 12. Quy trình ra quyết định có thể audit

Một team có thể ghi benchmark manifest:

```yaml
experiment:
  topic: mvnd-vs-maven
  projectCommit: "<commit-hash-recorded-at-run-time>"
  mvndRelease: "<mvnd-version>"
  mvnCore: "<mvn-version>"
  mvndEmbeddedMaven: "<embedded-version>"
  javaRuntime: "<jdk-vendor-and-version>"
  osAndArch: "<os-architecture>"
  cpuQuota: "<vCPU-limit>"
  ramLimit: "<RAM>"
  repositorySource: "<approved-repository-id>"
  scenario: "verify"
  threads: 1
  warmupsPerTool: 2
  measuredRunsPerTool: 7
  metrics:
    medianWallSeconds: "<from-harness>"
    p90WallSeconds: "<calculate-from-raw-samples>"
    peakRssMiB: "<from-OS-monitor>"
  gate:
    allBuildsSucceeded: true
    testsWereRun: true
    sourceAndProfilesMatched: true
```

Các giá trị trong dấu góc ở đây là **schema minh họa cần điền từ kết quả thật**, không phải benchmark đã có. Nếu chưa có dữ liệu, ghi rõ “not measured”, không đặt số 0 khiến hiểu sai. Có thể lưu raw CSV và test reports ở CI artifact store có quyền phù hợp.

### 12.1. Quy tắc thử nghiệm

1. **Chỉ thay một biến ở một lượt:** daemon on/off, rồi thread count, rồi heap — tránh đồng thời đổi Maven Core và JDK.
2. **Không mặc định tốc độ là tiêu chí duy nhất:** memory, security, plugin stability, developer experience cũng quan trọng.
3. **Tách interactive vs CI:** môi trường khác nhau nên quyết định có thể khác nhau.
4. **Không dùng số benchmark từ máy khác như SLA:** vCPU throttling, SSD/NFS, module graph, test duration khác.
5. **Không tắt tests/quality gates để làm đẹp kết quả.**
6. **Không xóa toàn bộ ~/.m2/repository** để “tạo cold run” trên máy người khác.
7. **Không stop daemon toàn hệ thống** khi còn build của đồng đội.
8. **Ghi trạng thái cache và daemon** cùng source/version/toolchain.
9. **Quyết định có thể đảo ngược:** duy trì `mvn`/`./mvnw` fallback và chuẩn chất lượng chung.
10. **Review lại khi nâng version Maven/mvnd/JDK/plugins** vì performance và compatibility có thể đổi.

### 12.2. Kết luận theo tình huống

| Môi trường | Khi nên thử mvnd | Khi Maven thông thường có thể tốt hơn |
| --- | --- | --- |
| Developer laptop đủ RAM | Nhiều builds trong một phiên, lặp `verify` | Ít builds, RAM ít, daemon idle chiếm tài nguyên |
| Desktop reactor lớn | Nhiều modules độc lập và plugins thread-safe | Dependencies gần như chuỗi dài, shared-state bugs |
| CI ephemeral container | Có nhiều invocations trong cùng một job và gains đã đo | Mỗi job chỉ chạy một `verify` rồi xóa runner |
| CI persistent dedicated | Nhiều builds cùng trust boundary, daemon reuse và security policy rõ | Multi-tenant/untrusted PRs hoặc teardown bắt buộc |
| IDE-driven development | IDE cho chạy mvnd được xác thực, build Maven nhiều lần | IDE incremental compiler đã đáp ứng workflow |
| Release/security jobs | Chỉ nếu được phê duyệt, kết quả đúng và isolated | Muốn baseline dễ audit, plugin tương thích rộng |

**Không có lựa chọn thắng tuyệt đối.** Quyết định sau benchmark nên ghi rõ: công cụ, version, scenario, threads, p50/p90, memory, exit/test correctness và môi trường sử dụng.

## 13. Bài tập thực hành

**Bài 1 — Nguồn tăng tốc.** Nêu ba cơ chế mvnd có thể giảm overhead khi chạy Maven nhiều lần.

**Đáp án:** Reuse JVM, plugin classloaders và JIT-optimized code; default parallel reactor cũng có thể đóng góp nhưng phải đo riêng.

**Bài 2 — Vì sao một mvnd invocation có thể chậm?** Trên container mới chỉ chạy một build, lợi ích nào chưa phát huy?

**Đáp án:** Warm daemon/JIT/classloader reuse giữa nhiều builds. Setup/startup/download có thể chiếm phần đáng kể.

**Bài 3 — So công bằng.** Vì sao không so `mvn clean verify` với `mvnd clean verify` rồi kết luận toàn bộ chênh lệch là daemon?

**Đáp án:** mvnd có thể parallel modules mặc định, Maven thường thì không. Dùng cả hai `-T1` để tách effect.

**Bài 4 — Clean vs cold daemon.** Chạy `mvnd clean verify` có xóa daemon warm state không?

**Đáp án:** Không. Maven clean chủ yếu dọn project `target`, daemon vẫn có thể sống.

**Bài 5 — Daemon status.** `mvnd --status` và `mvnd --stop` khác gì?

**Đáp án:** Status đọc trạng thái; stop dừng các daemon trong registry tương ứng và có thể ảnh hưởng người khác.

**Bài 6 — Java.** Lab có mấy modules và module nào độc lập?

**Đáp án:** Ba modules; `math-core` và `text-tools` độc lập; `task-app` phụ thuộc cả hai.

**Bài 7 — Runnable output.** Java application trong lab in gì?

**Đáp án:** `primes=10;tag=maven`.

**Bài 8 — Tests.** Tổng JUnit tests của lab?

**Đáp án:** Sáu: `math-core` ba, `text-tools` hai, `task-app` một.

**Bài 9 — Benchmark median.** Vì sao đo 7 samples mỗi tool và warm-up trước?

**Đáp án:** Hạn chế ảnh hưởng random outliers/JIT/GC/cache, không lấy một run làm chân lý.

**Bài 10 — Phân biệt cache.** Local Maven repository cache có phải mvnd JVM cache không?

**Đáp án:** Không. Disk artifacts cache khác JVM/plugin classloader/JIT reuse.

**Bài 11 — Plugin thread safety.** Nếu `mvnd -T1` pass nhưng default parallel fail, nên nghĩ đến gì?

**Đáp án:** Race/shared output/port, plugin không thread-safe hoặc test fixture conflicts. Kiểm dependencies graph/logs trước.

**Bài 12 — Java runtime.** mvnd daemon theo README yêu cầu Java version nào?

**Đáp án:** Java 17 trở lên.

**Bài 13 — Maven Core alignment.** mvnd và Maven CLI có chắc cùng core version vì cùng tên Maven không?

**Đáp án:** Không. mvnd nhúng Maven distribution riêng; phải xem `--version`.

**Bài 14 — CI security.** Có nên reuse mvnd daemon giữa untrusted PR và release job có secrets không?

**Đáp án:** Không. Cô lập theo trust boundary/runner hoặc dùng baseline Maven ephemeral.

**Bài 15 — Memory.** Vì sao mvnd có thể tốt về latency nhưng tệ về máy RAM ít?

**Đáp án:** Daemon JVM giữ heap/RSS khi idle; thêm forked test JVMs làm peak memory tăng.

**Bài 16 — Formula.** Nếu Maven median 12s và mvnd median 9s, time reduction là bao nhiêu?

**Đáp án:** 25%, speedup khoảng 1.33x; đó là ví dụ số giả định.

**Bài 17 — p90.** Nếu hai phương án có cùng median nhưng một phương án có outliers 60s, nên xem metric nào?

**Đáp án:** p90/p95, max, failure/GC/resource samples; đừng chỉ nhìn median.

**Bài 18 — Log parsing.** Vì sao `--raw-streams` có thể cần cho `help:evaluate`?

**Đáp án:** mvnd có buffered/reordered plugin output; raw streams giúp automation lấy stdout dạng cần.

**Bài 19 — Phân quyền.** Wrapper đã pin Maven liệu có làm `mvnd` tự pin theo không?

**Đáp án:** Không. mvnd là tool/distribution riêng, CI phải provision/pin mvnd nếu dùng.

**Bài 20 — Quyết định.** Có nên đổi mọi CI jobs sang mvnd sau khi đo nhanh hơn một lần trên laptop?

**Đáp án:** Không. Benchmark trên runner/workload thực, đo many runs, correctness, RAM và trust isolation trước.

## 14. Checklist trước khi áp dụng mvnd cho dự án

- [ ] Đã xác nhận mục tiêu: developer latency hay CI throughput?
- [ ] Đã xác nhận project/Java/Maven Core/plugin versions, approved artifact repository.
- [ ] mvnd distribution được tải từ nguồn tin cậy và verify checksum/signature.
- [ ] JDK cho mvnd daemon đáp ứng Java 17+ theo README hiện hành.
- [ ] mvnd native client/platform compatibility được xác nhận; fallback khi cần.
- [ ] Không nhầm mvnd với Maven Wrapper hoặc Maven 4.
- [ ] Source commit, profiles, tests và environment giống giữa hai công cụ.
- [ ] Warm-up và measured runs được tách rõ.
- [ ] Mọi measured run đều thành công và chạy đúng quality gates.
- [ ] Baseline `mvn -T1` vs `mvnd -T1` đã được đo.
- [ ] Parallel mode được đánh giá riêng với thread counts rõ.
- [ ] Phân biệt daemon cold, project clean và dependency cache cold.
- [ ] Có median, min/max/p90 và sample count.
- [ ] Có CPU/RSS/heap/GC/child-process memory khi cần.
- [ ] Có ghi vCPU/RAM/container limits và nền tảng OS.
- [ ] Có raw run logs và source/provenance metadata.
- [ ] Không stop shared daemons khi người khác đang build.
- [ ] Không reuse daemon giữa untrusted jobs và secrets-bearing jobs.
- [ ] Plugin thread safety, port/tmp/test isolation đã được xác nhận.
- [ ] Maven CLI hoặc Maven Wrapper fallback vẫn hoạt động.
- [ ] CI không dùng `-fn`/skip tests hoặc cắt quality gates để nhanh.
- [ ] Không biến experiment thành deployment production ngoài ý muốn.
- [ ] Quy trình upgrade/teardown/idle timeout được documented.
- [ ] Benchmark được lặp trên máy/CI thực tế, không dùng số mẫu minh họa.
- [ ] Quyết định có ghi lợi ích, chi phí và thời điểm đánh giá lại.

## 15. Nguồn tham khảo chính thức

- [Apache Maven — Maven Daemon](https://maven.apache.org/tools/mvnd.html): chức năng, khái niệm và cách chạy.
- [Apache Maven Daemon repository/README](https://github.com/apache/maven-mvnd): JVM/classloader/JIT reuse, parallel module builds, install, `--status`/`--stop` và configuration.
- [Apache Maven Daemon README source](https://github.com/apache/maven-mvnd/blob/master/README.adoc): version-specific commands, native/Java client, supported platforms và plugin output.
- [Apache Maven downloads](https://maven.apache.org/download.cgi): stable/preview releases, OS binaries, signatures/checksums.
- [Apache Maven Daemon default properties](https://github.com/apache/maven-mvnd/blob/master/dist/src/main/distro/conf/mvnd.properties): thread/memory/idle timeout and daemon settings.
- [Apache Maven — Parallel builds](https://cwiki.apache.org/confluence/display/MAVEN/Parallel+builds+in+Maven+3): reactor threading, plugin thread safety.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): clean/verify and lifecycle semantics.
- [Apache Maven — Guide to Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor DAG, build ordering.
- [Apache Maven — Configuring Maven](https://maven.apache.org/configure.html): JVM/CLI/runtime configurations.
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): repositories, mirrors, credentials, profiles.
- [Apache Maven — Guide to Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): outputTimestamp/compare.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): test execution, forked JVMs, parallel tests.

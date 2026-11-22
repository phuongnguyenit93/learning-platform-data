# Shenandoah: chọn `-XX:+UseShenandoahGC` trên môi trường thực sự hỗ trợ

> **Bối cảnh Java 15 và JDK hiện hành:** Shenandoah là garbage collector (GC) hướng tới **GC pause ngắn**, thực hiện nhiều công việc thu gom và di chuyển đối tượng đồng thời với application threads. **JEP 379 đưa Shenandoah thành tính năng production trong OpenJDK 15**. Cờ khởi động chính vẫn là **`-XX:+UseShenandoahGC`**, nhưng **không phải mọi bản phân phối, bản build, hệ điều hành và kiến trúc CPU đều đóng gói/hỗ trợ Shenandoah**. Cách vận hành đúng là **kiểm tra chính runtime sẽ deploy**, bật collector bằng cờ đó, xác nhận qua GC startup logs, rồi benchmark. Với OpenJDK JDK 25–27 có Shenandoah, **SATB (single-generation) vẫn là default mode** còn **Generational Shenandoah là lựa chọn riêng** qua `-XX:ShenandoahGCMode=generational`; không nhầm với mặc định của ZGC.

## 1. Kết luận thực hành trước tiên

Nếu image/runtime được xác nhận có hỗ trợ Shenandoah, một cấu hình khởi đầu:

~~~bash
java -XX:+UseShenandoahGC -Xms256m -Xmx2g -Xlog:gc=info -jar app.jar
~~~

- `-XX:+UseShenandoahGC`: yêu cầu HotSpot chọn **Shenandoah**.
- `-Xms256m`: heap tối thiểu/ban đầu được cấu hình.
- `-Xmx2g`: trần của **Java heap**, không phải trần toàn bộ RAM tiến trình.
- `-Xlog:gc=info`: bật logging để quan sát collector và các sự kiện GC.
- `app.jar` là tên minh họa; thay bằng JAR thực của ứng dụng.

**Điều kiện bắt buộc:** lệnh chỉ hợp lệ khi binary JVM đã **được build kèm và có thể vận hành Shenandoah** trên host. Nếu JVM báo không hỗ trợ, đó là kết quả cần xử lý về **JDK distribution/platform**, không phải lỗi cú pháp Java. Không nên âm thầm bỏ cờ và tuyên bố vẫn đang dùng Shenandoah.

Trên build OpenJDK **JDK 25–27** có hỗ trợ, nếu muốn **Generational Shenandoah** thay cho SATB default:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xms256m -Xmx2g -Xlog:gc=info -jar app.jar
~~~

Từ **JDK 25, Generational Shenandoah trở thành product feature** qua JEP 521; không cần `-XX:+UnlockExperimentalVMOptions` chỉ để chọn mode này trên build phù hợp. **Không đem mode flag đó áp dụng máy móc cho Java 15 hoặc JDK 17**, vốn chưa có Generational Shenandoah trong mainline ở những phiên bản tương ứng.

**Không suy ra:** `-XX:+UseShenandoahGC` tự kích hoạt chế độ generational trên JDK 25/26/27; theo man page OpenJDK/Oracle JDK 27, `ShenandoahGCMode` vẫn mặc định `satb` trong các build có collector.

## 2. Shenandoah là gì và khác mục đích của G1 thế nào?

Trong ứng dụng Java, các đối tượng không còn reachable từ GC roots sẽ có thể được thu hồi. Shenandoah là **concurrent compacting collector**: nó cố gắng thực hiện phần lớn việc đánh dấu, di chuyển đối tượng và cập nhật tham chiếu **trong lúc các threads Java tiếp tục chạy**. Đây là lý do nó hướng tới **độ trễ tạm dừng ngắn ngay cả với heap lớn**.

Sơ đồ khái niệm:

~~~text
          Java application threads
                  |
                  | create / access objects
                  v
          Java heap (regions)
                  |
           Shenandoah cycle
       +----------+-----------+
       |                      |
  Concurrent work        Brief pauses
  - marking              - coordination
  - evacuation           - certain GC phases
  - reference updates
       |                      |
       +----------+-----------+
                  |
             reclaim regions
~~~

Đây là **sơ đồ tư duy**, không phải thứ tự pha chính xác của mọi mode/version. Cơ chế chi tiết, barriers và phase names thay đổi theo collector implementation.

**Các ý đúng:**

- Shenandoah ưu tiên **low pause latency**.
- Phần lớn GC có thể chạy đồng thời với application threads.
- Một số giai đoạn vẫn cần **safepoint/stop-the-world**.
- Với heap pressure hoặc GC không theo kịp allocation, có thể có **degenerated/full GC fallback**, tăng thời gian dừng.
- Concurrent work và barriers tiêu tốn **CPU/memory overhead**.
- Không có đảm bảo chung rằng dùng Shenandoah luôn tăng throughput hoặc mọi pause đều dưới 1 ms.

**So với G1:** G1 là collector generational, region-based và có các pha dừng theo mục tiêu pause; thường là lựa chọn mặc định ở nhiều cấu hình HotSpot. Shenandoah thực hiện nhiều khâu đồng thời hơn để tối ưu pause latency. Việc nào tốt hơn phụ thuộc vào latency SLA, allocation rate, live set, CPU quota và footprint.

## 3. Từ Java 15 đến hiện tại: biết đúng mốc version

| Phiên bản | Vai trò Shenandoah | Cách hiểu hiện nay |
| --- | --- | --- |
| Java 12–14 | Giai đoạn ban đầu/experimental trong mainline | Chỉ là bối cảnh lịch sử, không lấy cờ experimental cũ làm mặc định production |
| **Java 15** | **JEP 379: Shenandoah thành product feature** | `-XX:+UseShenandoahGC` là tên cờ chính; runtime vẫn phải có collector |
| JDK 17 LTS | Shenandoah được dùng trong các OpenJDK builds có hỗ trợ | Thực hiện kiểm tra vendor/platform; chưa có generational mode mainline như JDK 25 |
| JDK 21 LTS | Nhiều vendor hỗ trợ Shenandoah, có thể có backport khác nhau | Không suy luận tập mode/flag từ số phiên bản nếu vendor có backport |
| JDK 24 | **JEP 404: Generational Shenandoah ở trạng thái experimental** | Đó là mốc phát triển, không dùng experimental configuration như hướng dẫn chung |
| **JDK 25 LTS** | **JEP 521: Generational Shenandoah thành product feature** | Có thể chọn `-XX:ShenandoahGCMode=generational` nếu collector được đóng gói |
| JDK 26/27 | Trong builds hỗ trợ, `ShenandoahGCMode=satb` vẫn là mặc định theo java command docs | Mode generational là opt-in; kiểm tra logs/flags của chính build |
| Phiên bản về sau | Cơ chế/default có thể đổi tiếp | Xem release notes/man page của runtime thực, không suy đoán |

Một collector có **tính năng production** không đồng nghĩa **mọi nhà cung cấp JDK bắt buộc shipping nó**. Shenandoah là tính năng HotSpot/OpenJDK có thể được **loại trừ lúc build** hoặc chưa hỗ trợ CPU architecture tương ứng.

### Không nhầm với ZGC

ZGC cũng hướng đến low latency nhưng có lộ trình mode khác: ZGC loại non-generational mode từ JDK 24, còn **Shenandoah JDK 25–27 vẫn công bố cả SATB lẫn generational trong builds hỗ trợ**. Vì thế:

~~~text
UseShenandoahGC == true  -> collector Shenandoah được chọn
ShenandoahGCMode=satb    -> single-generation SATB
ShenandoahGCMode=generational -> generational (JDK25+ mainline)
~~~

Đừng áp dụng quy tắc “Generational ZGC mặc định” sang Shenandoah. Đọc tên collector, giá trị mode và version riêng.

## 4. Vì sao phải kiểm tra bản phân phối JDK?

“Java 25” hay “Java 27” chỉ nói tới **Java platform feature version**, không bảo đảm mọi hotspot feature build-time đều giống nhau.

Ví dụ trong thực tế, các bản phân phối OpenJDK như **Red Hat build of OpenJDK** mô tả Shenandoah là collector được cung cấp; những image khác, trong đó có một số Oracle JDK builds, có thể **không bao gồm Shenandoah**.

Các khác biệt cần xét:

1. **JVM implementation:** HotSpot hay runtime khác; `-XX:...` không phải Java Language Specification.
2. **JDK vendor/distribution:** Oracle JDK, Temurin, Red Hat OpenJDK, Corretto, Liberica, Zulu… và chính build/tag được triển khai.
3. **Build options:** collector có được biên dịch vào JVM không?
4. **OS và architecture:** HotSpot có đủ hỗ trợ nền tảng/barriers cho Shenandoah không?
5. **Phiên bản/patch update:** những mode/flags có thể thay đổi; vendor có thể backport khác nhau.
6. **Container base image:** một tag `eclipse-temurin:25` không đồng nghĩa toàn bộ các tags khác hoặc image tối giản cũng có lựa chọn như nhau.

Không nên trả lời bằng bảng “vendor X luôn có/Y luôn không có” qua mọi năm và mọi platform. **Phép thử khởi động thực tế** ở image/host chuẩn xác hơn.

### Bộ lệnh probe ban đầu

~~~bash
java -version
java -XX:+UseShenandoahGC -version
~~~

Lệnh thứ nhất xác định runtime đang gọi. Lệnh thứ hai yêu cầu khởi động với Shenandoah. Nếu thoát **exit code 0** và báo version đúng, JVM đã chấp nhận flag ở cấu hình đó; nhưng bạn vẫn nên bật logging ở lần probe tiếp theo để biết collector thực sự hoạt động và mode nào được chọn:

~~~bash
java -XX:+UseShenandoahGC -Xlog:gc+init=info -version
~~~

Nếu JVM không hỗ trợ, thông báo lỗi có thể là kiểu “Option -XX:+UseShenandoahGC not supported”, “Unrecognized VM option…” hoặc từ chối khởi tạo theo đặc thù vendor/build. **Đừng viết code dựa vào câu lỗi cố định**: chỉ cần exit status khác 0 và nội dung log chẩn đoán phù hợp.

### Probe đúng nơi deployment

Không đủ nếu chạy probe trên laptop còn production chạy JDK khác. Kiểm tra:

- Trong Docker image **đúng digest/tag** định deploy.
- Trên node/Kubernetes runtime thực khi CPU architecture có thể khác.
- Ở đúng container/service account và cgroup restrictions.
- Với startup arguments cuối cùng được inject qua Helm/systemd/`JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`.
- Trong CI trên mỗi nhóm kiến trúc cần hỗ trợ.

## 5. Một quy trình fail-fast trước khi chạy ứng dụng

Khi yêu cầu sản phẩm là **bắt buộc Shenandoah**, không nên bắt lỗi rồi âm thầm bỏ `-XX:+UseShenandoahGC` để chạy collector mặc định mà vẫn báo “Shenandoah enabled”.

Quy trình:

~~~text
1. Chọn JDK image/vendor/version được hỗ trợ.
2. Probe java -XX:+UseShenandoahGC -version.
3. Nếu probe fail:
       FAIL DEPLOYMENT hoặc chọn image hỗ trợ theo policy.
4. Nếu probe pass:
       Probe -Xlog:gc+init=info; xác nhận collector/mode.
5. Thử cấu hình Xms/Xmx và memory/CPU limits thật.
6. Chạy smoke tests và workload tests.
7. Deploy với monitoring và rollback.
~~~

Trên Linux shell hỗ trợ POSIX có thể dùng:

~~~bash
if java -XX:+UseShenandoahGC -version >/dev/null 2>&1; then
  echo "Shenandoah option accepted by this JVM"
else
  echo "Shenandoah unsupported by this JVM" >&2
  exit 1
fi
~~~

Đây là **script probe**, không phải code Java. Nó giúp pipeline dừng sớm khi không hỗ trợ, nhưng **không xác nhận collector được dùng trong dịch vụ đã chạy**; bước đó cần startup logs/flags của chính tiến trình.

Trên PowerShell, có thể dùng:

~~~powershell
java -XX:+UseShenandoahGC -version
if ($LASTEXITCODE -ne 0) {
    throw "This JVM cannot start with Shenandoah GC"
}
~~~

Không giả định shell nào cũng hiểu cú pháp `if ...; then` hoặc `$LASTEXITCODE`. Có thể dùng script tương ứng với CI image được chọn.

## 6. Cờ `-XX:+UseShenandoahGC` và mức độ hỗ trợ

### 6.1. Cờ chính

~~~bash
java -XX:+UseShenandoahGC -Xmx1g -jar app.jar
~~~

`-XX:+UseShenandoahGC` là **HotSpot VM option**, không nằm trong Java source code. Compiler `javac` không có flag này để “bật collector khi biên dịch”. Lựa chọn GC diễn ra **khi khởi động JVM**.

Nếu runtime không hỗ trợ Shenandoah, JVM có thể từ chối startup. Nếu bạn cung cấp nhiều GC selection flags xung đột, JVM có thể báo lỗi không chọn được collector. Đừng vừa bật `-XX:+UseG1GC`, vừa bật `-XX:+UseShenandoahGC` rồi mong JVM tự chọn cái “nhanh hơn”.

### 6.2. Không cần flag experimental cũ để dùng chế độ production

JEP 379 đưa Shenandoah thành product feature ở JDK15. Do đó khi muốn **chế độ Shenandoah thông thường trên một build hỗ trợ**, không cần thêm `-XX:+UnlockExperimentalVMOptions` chỉ để mở khóa collector.

Với **Generational Shenandoah**, JDK24 từng là experimental; **từ JDK25 được đưa thành product feature theo JEP521**, nên hướng dẫn hiện hành JDK25+ không cần experimental unlock cho mode đó trên builds có hỗ trợ.

**Không biến** một cờ experimental tồn tại trong release cũ thành hướng dẫn mới cho JDK27.

### 6.3. Cờ cấu hình mode cho Shenandoah trong JDK25–27

~~~bash
# Shenandoah SATB default (khi build hỗ trợ):
java -XX:+UseShenandoahGC -Xmx2g -jar app.jar

# Chọn generational một cách rõ ràng:
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xmx2g -jar app.jar
~~~

Cấu hình default có thể đổi trong các JDK tương lai; khi mục tiêu SLA phụ thuộc mode, nên **kiểm tra mode trong startup log** và cân nhắc cấu hình tường minh.

Khi bật generational, `ShenandoahGCHeuristics` chỉ hỗ trợ **`adaptive`** trong các JDK25/27 docs hiện hành. Không sao chép `static`/`compact` hoặc heuristic tuning khác từ SATB vào generational mà không đối chiếu tài liệu đúng version.

## 7. SATB và Generational Shenandoah trong JDK hiện hành

### 7.1. SATB single-generation (default trong docs JDK25–27)

`satb` là viết tắt của **Snapshot-At-The-Beginning**, một phương pháp concurrent marking. Ở mode này, Shenandoah thu gom theo mô hình **một generation**, phù hợp với thiết kế Shenandoah trước khi Generational mode được đưa vào mainline.

~~~text
ShenandoahGCMode=satb:
    Heap chứa nhiều regions
            |
    concurrent marking/evacuation
            |
    reclaim garbage
~~~

Không đồng nhất “single generation” với “không có regions”, “không concurrent” hoặc “không low latency”. Shenandoah SATB vẫn là low-pause concurrent collector.

### 7.2. Generational Shenandoah (product feature JDK25+)

Mode generational tổ chức việc thu gom theo **young** và **old** generation, tận dụng hiện tượng nhiều objects mới được cấp phát có tuổi thọ ngắn:

~~~text
Allocated objects
       |
       v
Young generation
       |
       +-- objects chết sớm -> thu hồi
       |
       +-- sống qua nhiều lần -> promote
                                     |
                                     v
                              Old generation
~~~

Lợi ích tiềm năng:

- Nhiều objects ngắn hạn được xử lý hiệu quả hơn.
- Tăng throughput trong các workloads có allocation lớn.
- Cải thiện đáp ứng khi có allocation spikes/young collections.
- Duy trì định hướng low-pause của Shenandoah.

Không bảo đảm generational thắng SATB trên mọi workload. Cần đo cả **tail latency, throughput, CPU, memory, allocation stalls**. Các pha young/old, heuristics và overhead vẫn phụ thuộc implementation và application.

### 7.3. Mode không phải collector

Bảng phân biệt:

| Lựa chọn | Flag | Đối tượng thay đổi |
| --- | --- | --- |
| Chọn Shenandoah thay GC mặc định | `-XX:+UseShenandoahGC` | **Garbage collector** |
| Chọn mode generational khi collector hỗ trợ | `-XX:ShenandoahGCMode=generational` | **Mode của Shenandoah** |
| Chọn SATB nếu build hỗ trợ | `-XX:ShenandoahGCMode=satb` | **Mode của Shenandoah** |
| Chọn G1 thay Shenandoah | `-XX:+UseG1GC` | **Collector khác** |

Trước khi so sánh SATB vs Generational, đảm bảo cả hai lệnh được chạy trên **cùng HotSpot build** có các modes tương ứng.

## 8. Cấu hình heap: `-Xms` và `-Xmx` trước khi tune quá nhiều

Với Shenandoah, GC cố thu hồi đồng thời, nghĩa là application vẫn tạo thêm đối tượng trong khi collector chạy. Nếu không còn **heap headroom**, allocator có thể chờ GC hoặc phải đi tới các fallback paths.

Một cấu hình khởi đầu:

~~~bash
java -XX:+UseShenandoahGC -Xms256m -Xmx2g -jar app.jar
~~~

- `-Xmx` giới hạn maximum **Java heap**, không bảo đảm đủ RAM cho mọi workloads.
- `-Xms` ảnh hưởng mức heap ban đầu/tối thiểu theo VM semantics.
- Live set (objects còn reachable) cần nhỏ hơn trần heap **có đủ khoảng trống cho allocation**.
- Application allocation rate cao có thể khiến concurrent collector khó theo kịp, nhất là CPU bị throttled.
- Không nâng `Xmx` vô hạn nếu có memory leak; nên profile retained objects và giới hạn caches.

### Heap ≠ tổng memory của process

~~~text
Total process memory consumption (mô hình):
   Java heap
 + metaspace + code cache
 + thread stacks
 + NIO direct/native buffers
 + JNI/native allocations
 + GC/JVM overhead
 + other runtime allocations
~~~

Các vùng có thể có reservations/commit/RSS khác nhau; sơ đồ chỉ nhằm nhắc rằng `-Xmx` **không** là memory limit của container.

Trong Kubernetes/container, không đặt `-Xmx` bằng đúng toàn bộ container memory limit. Cần chừa **native headroom** và đo RSS/working set thực.

### Ví dụ với budget có điều kiện

Container giới hạn RAM 2 GiB; một cấu hình thử nghiệm có thể là:

~~~bash
java -XX:+UseShenandoahGC -Xms128m -Xmx1280m -jar app.jar
~~~

Không suy ra “1280m luôn tối ưu cho container 2GiB”. Nó chỉ minh họa **max heap thấp hơn container limit**, dành chỗ cho các vùng khác. Ứng dụng dùng nhiều threads, direct memory hoặc JNI có thể cần thêm headroom.

## 9. Heuristics, uncommit và các cờ tuning

**Bắt đầu từ default** là lựa chọn dễ duy trì; chỉ thay đổi flags sau khi benchmark. Những cờ hay được đề cập trong tài liệu Shenandoah:

| Cờ | Ý nghĩa | Khi nào cân nhắc |
| --- | --- | --- |
| `-XX:+UseShenandoahGC` | Chọn collector | Khi build đã hỗ trợ và benchmark có lợi |
| `-Xmx<size>` | Heap maximum | Điều chỉnh theo live set và headroom |
| `-Xms<size>` | Heap initial/min | Theo footprint/latency/commit behavior |
| `-Xlog:gc=info` | Log GC ở mức info | Chẩn đoán/quan sát cơ bản |
| `-Xlog:gc*=info` | Log nhiều tags liên quan GC | Phân tích kỹ hơn, chú ý log volume |
| `-XX:ShenandoahGCMode=generational` | Chọn Generational Shenandoah | Build JDK25+ có feature và mode, khi benchmark |
| `-XX:ShenandoahGCMode=satb` | Chọn SATB | Khi cần pin rõ mode và build hỗ trợ |
| `-XX:ShenandoahGCHeuristics=adaptive` | Heuristics thích ứng | Default trong JDK25–27 man pages, thường không cần ghi |
| `-XX:ShenandoahUncommitDelay=<ms>` | Thời gian idle trước uncommit, tùy build | Chỉ khi có mục tiêu footprint và xác nhận option support |
| `-XX:-ShenandoahUncommit` | Tắt uncommit khi option có sẵn | Hạn chế khi có lý do đo đạc rõ ràng |
| `-XX:ConcGCThreads=<n>` | Số concurrent GC threads | Advanced tuning theo CPU quota và log |

Thời gian của `ShenandoahUncommitDelay` trong nhiều HotSpot builds được tính theo **milliseconds**; **không** đoán đơn vị từ tên. Khi muốn điều chỉnh, đọc tài liệu và `PrintFlagsFinal`/help của bản JVM thật.

### Heuristics trong generational

Trong OpenJDK/Oracle `java` command docs của JDK25–27, `generational` mode chỉ hỗ trợ heuristic **`adaptive`**. Vì thế:

~~~bash
# Trên JDK25+ có Shenandoah generational:
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xmx2g -jar app.jar
~~~

Không cần thêm `-XX:ShenandoahGCHeuristics=adaptive` vì đó là default trong tài liệu nêu trên. Đừng ghép thêm những heuristics ngoài danh sách mode hỗ trợ.

### Uncommit không đồng nghĩa xóa objects

**Uncommit** là việc trả các vùng memory chưa dùng về OS khi đáp ứng chính sách. Nó không phải thao tác xóa objects đang còn reachable và không giải quyết memory leak.

Khi `-Xms` gần `-Xmx` hoặc bằng nhau, khả năng co heap và trả memory không còn như cấu hình cho phép heap biến động; còn trạng thái RSS thực tế cũng phụ thuộc OS, page mappings và JVM. Đo trước khi chọn.

## 10. Cách xác minh collector và mode ở startup

Một quy trình đủ để tránh “tưởng đã bật nhưng thực tế không phải Shenandoah”:

~~~bash
java -version
java -XX:+UseShenandoahGC -Xlog:gc=info -version
java -XX:+UseShenandoahGC -Xlog:gc+init=info -version
~~~

Trong một build hỗ trợ, log có thể cho thấy **Using Shenandoah** và thông tin về mode, heap sizing, workers. **Không viết assertion dựa trên toàn bộ câu chữ/địa chỉ memory**, vì JVM vendor và release có thể thay đổi cách hiển thị.

Một phương pháp xem options khi cần:

~~~bash
java -XX:+UseShenandoahGC -XX:+PrintFlagsFinal -version
~~~

Lệnh này in nhiều flags. Trên Linux/macOS có thể lọc:

~~~bash
java -XX:+UseShenandoahGC -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'UseShenandoahGC|ShenandoahGCMode|ShenandoahGCHeuristics'
~~~

**Đừng mặc định mọi terminal có `grep`**. PowerShell có thể dùng `Select-String`:

~~~powershell
java -XX:+UseShenandoahGC -XX:+PrintFlagsFinal -version 2>&1 | Select-String "UseShenandoahGC|ShenandoahGCMode|ShenandoahGCHeuristics"
~~~

Output thay đổi theo platform; hãy kiểm tra boolean `UseShenandoahGC` và giá trị `ShenandoahGCMode`, không so định dạng cột cố định.

### Nếu muốn xác nhận chế độ generational

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xlog:gc+init=info -version
~~~

Lệnh này chỉ nên chạy trên **JDK25+ build hỗ trợ**. Nếu JVM startup fail, kiểm tra version, cờ chính, build options, OS/CPU và lỗi thật trước khi sửa.

## 11. Quan sát tiến trình đang hoạt động

Trên JDK có công cụ `jcmd` và quyền attach vào tiến trình:

~~~bash
jcmd
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
~~~

PID `12345` chỉ là ví dụ; lấy từ process list hoặc `jcmd` thực của hệ thống.

- `VM.command_line`: biết arguments đã dùng, giúp phát hiện cờ nào được inject.
- `VM.flags`: kiểm tra VM options được áp dụng; format có thể khác giữa releases.
- `GC.heap_info`: snapshot các thông tin heap, **không phải bằng chứng đủ** về performance latency.
- Nếu attach bị chặn trong container/user permissions, đây là hạn chế vận hành; vẫn có thể xác minh qua startup logs và metrics.

Có thể bật file log:

~~~bash
java -XX:+UseShenandoahGC -Xms256m -Xmx2g -Xlog:gc*:file=gc-shenandoah.log:time,uptime,level,tags -jar app.jar
~~~

Cấu hình này sử dụng Unified JVM Logging. Dùng mức log chi tiết vừa đủ, thiết lập rotation/storage phù hợp. Không log thông tin nhạy cảm từ ứng dụng vào các kênh không kiểm soát.

### Những gì cần quan sát trong GC logs/telemetry

- Collector/mode thực sự được chọn;
- GC cycles, pauses và các phase durations;
- Dấu hiệu **degenerated/full GC** khi concurrency không theo kịp;
- Heap occupancy, allocation rates, free headroom;
- CPU usage/throttling và số GC threads;
- Backpressure, p99 response time của ứng dụng;
- Object churn, allocation stalls, native/container RSS.

Tên phase/tag có thể đổi theo SATB/generational hoặc patch-level. Hệ thống giám sát nên gắn version/distribution và có tests khi nâng JDK.

## 12. Chương trình Java 17+ chạy được để đo workload cùng runtime

Collector không được chọn từ Java source; chọn bằng **JVM startup option**. Một chương trình Java thông thường có thể được chạy dưới Shenandoah, G1 hoặc ZGC để so sánh trong cùng môi trường.

Lưu thành file **`ShenandoahWorkloadDemo.java`**:

~~~java
public final class ShenandoahWorkloadDemo {
    private static final int ROUNDS = 8_192;
    private static final int BLOCK_BYTES = 16 * 1024;
    private static final int RETAINED_SLOTS = 32;
    private static volatile long observedChecksum;

    public static void main(String[] args) {
        // Mỗi vòng cấp phát một mảng rồi giữ lại một cửa sổ nhỏ.
        // Các mảng bị thay thế có thể trở thành ứng viên GC.
        byte[][] retained = new byte[RETAINED_SLOTS][];
        long checksum = 0L;

        for (int i = 0; i < ROUNDS; i++) {
            byte[] block = new byte[BLOCK_BYTES];
            block[0] = (byte) (i % 251);
            block[BLOCK_BYTES - 1] = (byte) ((i / 251) % 251);

            retained[i % RETAINED_SLOTS] = block;
            checksum += block[0] & 0xff;
        }

        int liveSlots = 0;
        for (byte[] block : retained) {
            if (block != null) {
                liveSlots++;
            }
        }

        observedChecksum = checksum;

        System.out.println("rounds: " + ROUNDS);
        System.out.println("array bytes: " + BLOCK_BYTES);
        System.out.println("retained slots: " + liveSlots);
        System.out.println(
                "checksum positive: " + (observedChecksum > 0));
    }
}
~~~

### Biên dịch

~~~bash
javac ShenandoahWorkloadDemo.java
~~~

Nếu compiler còn hỗ trợ target Java 15:

~~~bash
javac --release 15 ShenandoahWorkloadDemo.java
~~~

Chương trình không dùng preview features hay APIs GC nội bộ, nên có thể biên dịch cho Java 15. **Nhưng biên dịch `--release 15` không quyết định collector**; collector được chọn ở runtime.

### Chạy trên JDK có Shenandoah

~~~bash
java -XX:+UseShenandoahGC -Xms64m -Xmx256m ShenandoahWorkloadDemo
~~~

**Stdout chính xác do chương trình tạo ra:**

~~~text
rounds: 8192
array bytes: 16384
retained slots: 32
checksum positive: true
~~~

Kết quả:

- `ROUNDS` là **8192**.
- `BLOCK_BYTES` là **16384** (16 KiB).
- `RETAINED_SLOTS` là **32**, toàn bộ đều được gán sau 8192 vòng.
- `observedChecksum` dương vì nhiều vòng có `i % 251` khác 0.
- Dữ liệu danh nghĩa được cấp phát bằng các mảng là `8192 × 16384 = 134217728 bytes`, tức **128 MiB**, chưa kể headers/structures khác.
- Tại cuối vòng lặp, còn tham chiếu tới 32 mảng, tương ứng khoảng **512 KiB array payload**; những mảng cũ không được giữ qua biến `retained` trở thành ứng viên thu gom.
- Dù có nhiều allocations, **số GC cycles và thời điểm GC không được đảm bảo**; JIT/runtime/heap/mode khác nhau có thể dẫn đến GC logs khác nhau.

**Nếu startup báo collector không được hỗ trợ, không có các dòng stdout trên**. Khi đó cần đổi sang build/JVM có Shenandoah hoặc dùng collector khác theo chính sách.

### Bật GC log cho cùng chương trình

~~~bash
java -XX:+UseShenandoahGC -Xms64m -Xmx256m -Xlog:gc=info ShenandoahWorkloadDemo
~~~

Các dòng GC là output **biến động**; không thể viết một stdout tổng thể cố định. Nếu muốn so với G1 trên **cùng runtime/hardware**, thử:

~~~bash
java -XX:+UseG1GC -Xms64m -Xmx256m -Xlog:gc=info ShenandoahWorkloadDemo
~~~

**Đây không phải benchmark production**: một vòng cấp phát ngắn không mô phỏng tail latency, workload mix, object lifetimes, pinned data, I/O hay CPU contention thực tế. Mục tiêu demo là minh họa **GC được chọn qua startup**, không phải chứng minh collector nào nhanh hơn.

### Chạy Generational Shenandoah trên JDK25+

Chỉ khi build JDK25+ hỗ trợ:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xms64m -Xmx256m -Xlog:gc=info ShenandoahWorkloadDemo
~~~

Stdout chương trình Java vẫn giống phần trên; **log collector/mode** khác, số GC cycles không cố định.

## 13. Kiểm tra tương thích JDK build theo hai tầng

### Tầng A — VM có collector không?

~~~bash
java -XX:+UseShenandoahGC -version
~~~

Nếu lỗi “not supported”/“unrecognized” thì không thể cho service production sử dụng Shenandoah trên binary ấy. **Đừng dùng cờ ép khác để cố mở tính năng không có trong build**. Một image hỗ trợ G1 hoặc ZGC có thể chạy ứng dụng nhưng **không có Shenandoah**.

### Tầng B — VM có mode cần dùng không?

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -version
~~~

Trên JDK25+ hỗ trợ, JVM có thể chấp nhận mode; trên JDK15/17 mainline, mode đó chưa tồn tại. Nếu không biết vendor/backport, luôn probe. Khi pipeline cần xác nhận cấu hình, dùng log `gc+init` và kiểm tra mode chính xác.

**Khả năng sử dụng collector và khả năng sử dụng một mode là hai điều kiện khác nhau.**

### Khi cần fallback

Một hệ thống có thể cho phép fallback sang G1/ZGC khi Shenandoah không có, nhưng chỉ thực hiện nếu được **đặc tả và chấp thuận**:

- Thay đổi collector có thể làm thay đổi pause latency, CPU usage và footprint.
- Alerting/thresholds cần đặt lại.
- Benchmark/test đã chạy với Shenandoah không chứng minh fallback đáp ứng SLA.
- Không nên fallback im lặng rồi tiếp tục hiển thị “Shenandoah enabled”.

Đối với nhiệm vụ cần Shenandoah cụ thể, tốt hơn **fail deployment có thông báo rõ** và sửa base image.

## 14. Vì sao Shenandoah có thể tạo GC pauses hoặc Full GC?

Shenandoah low-pause không phải “zero pause”. Khi concurrent GC chạy không đủ nhanh so với tốc độ allocation, có thể xuất hiện:

- **Allocation pressure:** thiếu các regions có thể cấp phát.
- **Pacing:** ứng dụng bị làm chậm để GC có cơ hội bắt kịp (tùy chính sách).
- **Degenerated GC:** một phần công việc được chuyển sang stop-the-world fallback.
- **Full GC:** trường hợp fallback tốn kém, có thể làm latency tăng mạnh.
- **OutOfMemoryError:** khi không thể thỏa mãn cấp phát theo tình trạng bộ nhớ.

Các vấn đề thường gặp:

1. `-Xmx` quá sát **live set** hoặc traffic bursts.
2. Memory leak/cache không giới hạn làm live set tăng.
3. CPU throttling nặng khiến GC threads không đủ thời gian.
4. Concurrent threads bị cạnh tranh tài nguyên với application.
5. Object churn/high allocation rate vượt khả năng reclaim.
6. Native/container limit gây OOM kill dù Java heap chưa tới Xmx.

Do đó, khi p99 tăng đột ngột, kiểm tra **GC logs có degenerated/full cycles**, allocation stalls, CPU throttling và memory. Không chỉ tăng RAM mà bỏ qua nguyên nhân.

## 15. Container, Kubernetes và runtime thực

### 15.1. Trong Docker

Một ví dụ minh họa **chỉ có ý nghĩa nếu image đã kiểm chứng có Shenandoah**:

~~~bash
docker run --rm --memory=2g my-shenandoah-jdk25-image java -XX:+UseShenandoahGC -Xms256m -Xmx1g -jar app.jar
~~~

Lệnh này giả định image không có ENTRYPOINT làm thay đổi cú pháp và có `app.jar` tại nơi phù hợp. Không phải tên image có thật; cần dùng image đã duyệt của đội bạn.

**Quan trọng:**

- `--memory=2g` giới hạn RAM của container, không phải `Xmx`.
- `-Xmx1g` chừa một phần để native memory; chỉ là ví dụ budgeting.
- Phải kiểm tra CPU architecture của image và build support.
- Không dựa vào `docker run java -version` trên một image khác với production.

### 15.2. Trong Kubernetes

Mảnh cấu hình minh họa:

~~~yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: "-XX:+UseShenandoahGC -Xms256m -Xmx1g -Xlog:gc=info"
resources:
  requests:
    memory: "1536Mi"
  limits:
    memory: "2Gi"
~~~

Đây **không phải Deployment YAML hoàn chỉnh** và không phải recommended sizing. Chỉ minh họa việc đưa JVM options vào container env và **heap max nhỏ hơn memory limit**. Kiểm tra nguồn cấu hình khác như `JDK_JAVA_OPTIONS`/command line để không xung đột collector flags.

Nếu chạy nhiều node với kiến trúc khác nhau, cần kiểm tra từng architecture; một build có Shenandoah trên amd64 không tự bảo đảm tương đương trên mọi CPU.

### 15.3. CPU quota và GC concurrency

Shenandoah cần CPU để đánh dấu/di chuyển objects trong khi ứng dụng chạy. Nếu Kubernetes CPU limit quá thấp hoặc node quá tải, concurrent GC có thể không theo kịp. Theo dõi:

- CPU throttling time/rate;
- CPU per process và concurrent GC threads;
- Request rate và allocations per second;
- GC cycle durations, fallback events;
- RSS/container memory working set;
- p95/p99 latencies của endpoint.

Không chỉ đo số RAM tiết kiệm; trade-off CPU là phần quan trọng của quyết định chọn Shenandoah.

## 16. Khi nào nên thử Shenandoah, khi nào không?

**Nên thử khi:**

- Service có latency SLO nghiêm ngặt, đặc biệt tail latency nhạy với GC.
- Heap/live set tương đối lớn và việc tạm dừng dài là chi phí đáng kể.
- Có thể cấp đủ CPU và memory headroom cho concurrent collector.
- Bạn có quyền chọn **JDK distribution hỗ trợ** và kiểm soát build.
- Có môi trường benchmark/monitoring đủ tin cậy.

**Không nên ép khi:**

- Runtime/vendor bắt buộc không có Shenandoah.
- G1 hoặc ZGC đang đáp ứng SLO với chi phí tốt hơn.
- CPU quota quá hạn chế hoặc workload quá nhỏ khiến overhead không đáng.
- Nhóm không có cách quan sát collector và xử lý lỗi startup/fallback.
- Việc bật thêm collector sẽ tạo complexity mà chưa có lợi ích đo được.

### Bảng so sánh ở mức quyết định

| Tiêu chí | G1 | Shenandoah | ZGC |
| --- | --- | --- | --- |
| Mục tiêu | Cân bằng throughput/pause và footprint | Concurrent low-pause GC | Concurrent low-pause GC |
| Bật trên HotSpot hỗ trợ | `-XX:+UseG1GC` | `-XX:+UseShenandoahGC` | `-XX:+UseZGC` |
| Availability | Phổ biến, thường là mặc định | **Phụ thuộc vendor/build/platform** | Phụ thuộc runtime/platform nhưng phân phối khác Shenandoah |
| Tính chất pause | Có các STW evacuation pauses | Chủ yếu concurrent, vẫn có brief pauses/fallback | Chủ yếu concurrent, vẫn có pauses/fallback |
| Tuning đầu tiên | Heap, pause goal, logging | Heap/headroom, logs, mode nếu cần | Heap/headroom, logs |
| Tốt nhất cho mọi workload? | Không | Không | Không |

Không suy luận Shenandoah “nhanh hơn ZGC” chỉ từ kiến trúc; phải **benchmark trên cùng runtime, CPU quota, heap policy, traffic và latency metrics**.

### Các metrics nên thu thập

- p50/p95/p99/p99.9 response latency;
- Throughput (requests/s, jobs/s);
- Java heap used/committed/peak;
- Process RSS và container OOM events;
- CPU utilization/throttling, GC worker CPU;
- GC pauses, degenerated/full cycles;
- Allocation rate, live set, object churn;
- Startup time, warm-up, steady-state, soak;
- Application errors/timeouts, lock/contention.

## 17. Cách xử lý lỗi startup và lỗi runtime

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| “`UseShenandoahGC` not supported” | Build không kèm collector hoặc platform không hỗ trợ | Chọn JDK build có Shenandoah, probe đúng host |
| “Unrecognized VM option `UseShenandoahGC`” | JVM khác HotSpot hoặc build thiếu feature | Kiểm tra vendor/implementation và docs |
| Generational mode bị từ chối | JDK trước productization, vendor/backport hoặc flag không hỗ trợ | Xác nhận JDK25+ build, probe mode cụ thể |
| Khởi động được nhưng không thấy Shenandoah log | Chưa bật log đúng tags, log chuyển chỗ hoặc GC không được chọn | `-Xlog:gc+init=info`, `VM.flags`, verify command line |
| JVM chạy G1 dù script dự định Shenandoah | Flag bị bỏ qua trong wrapper hoặc không được truyền | Kiểm tra command/ENTRYPOINT/env vars thật |
| Nhiều GC selection flags cùng xuất hiện | Config từ nhiều tầng chồng nhau | Bỏ cờ xung đột, chỉ chọn một collector |
| GC pause vẫn cao | Degenerated/full GC, heap pressure, safepoints | Kiểm tra GC logs, headroom, CPU |
| CPU tăng sau đổi collector | Concurrent GC/barrier overhead hoặc contention | Benchmark và điều chỉnh allocation/CPU, cân nhắc collector khác |
| Memory usage tăng | Heap min/max, uncommit policy, live set, native memory | Phân biệt heap used/committed/RSS, profile retained objects |
| Container bị kill dù heap chưa đầy | Native memory + JVM overhead vượt limit | Chừa container headroom, kiểm tra RSS/OOM events |
| `Xms=Xmx` nhưng RSS không giảm | Heap min cao và uncommit kém hiệu quả | Dùng heap policy phù hợp, đo footprint |
| Không có GC events trong chương trình nhỏ | Không đủ allocation hoặc JIT/heap đủ rộng | Tăng workload có kiểm soát, kiểm tra startup GC riêng |
| GC mode không giống tài liệu online | Version/vendor/backport khác | Dùng docs của **chính bản JDK** và `PrintFlagsFinal` |
| P99 tệ hơn G1 sau đổi collector | Trade-offs hoặc workload không hợp | Dừng rollout/rollback và phân tích benchmark |
| CPU throttling mạnh trên Kubernetes | Quota thấp, concurrent GC chưa đủ CPU | Điều chỉnh resource budget, đo cycles/stalls |
| Java code biên dịch nhưng flag không nhận | GC là startup option của JVM, không phải Java API | Dùng JVM có Shenandoah và kiểm tra flags |
| GC được bật nhưng mục tiêu throughput không đạt | Tối ưu low pause có overhead, workload khác dự đoán | So G1/ZGC và application tuning |

### Không retry vô hạn khi thiếu collector

Nếu image không hỗ trợ Shenandoah, việc chạy lại cùng lệnh 100 lần không tạo ra collector. Hãy giải quyết đúng nguyên nhân: chọn build tương thích, thay đổi deployment policy hoặc lựa chọn GC khác theo quyết định đã kiểm thử.

### Không tắt observability để “sửa” startup lỗi

Tháo `-Xlog` vì log làm người dùng thấy cảnh báo không giải quyết flag unsupported. Phải đọc lỗi thật và xác nhận mode/collector.

## 18. Kịch bản rollout và rollback có kiểm soát

Một kế hoạch khả thi:

1. Ghi nhận baseline ứng dụng đang chạy, gồm p99, throughput, RSS, CPU, GC pauses.
2. Xác định JDK binary/vender/version hiện tại và JDK hỗ trợ Shenandoah được duyệt.
3. Probe collector + mode trên mọi architecture/OS cần deploy.
4. Ghi rõ exact JVM flags cho canary và staging.
5. Chạy load tests: warm-up, steady load, burst, soak, cancellation và graceful shutdown.
6. So sánh SATB và generational **nếu hai mode đều được hỗ trợ**.
7. Kiểm tra latency spikes và degenerated/full collections.
8. Kiểm tra heap/native RSS headroom theo cgroup memory limit.
9. Triển khai canary theo tỷ lệ nhỏ, quan sát metrics và error rate.
10. Nếu không đạt SLO, rollback **cả JDK image và JVM flags** theo kế hoạch, không chỉ xóa một cờ.
11. Ghi lại build digest, patch-level, command-line/values của tất cả GC flags.
12. Tái benchmark khi nâng JDK feature version hoặc thay vendor vì mode heuristics có thể đổi.

**Lưu ý:** migrate sang một JVM có Shenandoah cũng có thể thay đổi JIT/library/runtime ngoài GC. Đừng quy mọi chênh lệch hiệu năng cho collector nếu baseline và trial khác nhiều biến.

## 19. Bài tập thực hành kèm đáp án

**Câu 1.** Trên OpenJDK JDK25 có hỗ trợ Shenandoah, cờ nào yêu cầu collector này?

**Đáp án:** `-XX:+UseShenandoahGC`.

**Câu 2.** Có nên mặc định rằng Oracle JDK và mọi image Java 25 đều chứa Shenandoah?

**Đáp án:** Không. Collector có thể bị loại trừ lúc build hoặc không hỗ trợ platform. Luôn probe chính binary/container bằng `java -XX:+UseShenandoahGC -version`.

**Câu 3.** `java -version` in 27; có đủ chứng minh Shenandoah available không?

**Đáp án:** Không. Version không nói tính năng build-time có/không. Cần probe startup và xem GC log.

**Câu 4.** Vì sao không dùng `-XX:+UnlockExperimentalVMOptions` theo thói quen khi chọn Shenandoah thông thường trên JDK25?

**Đáp án:** Shenandoah được productized từ JDK15; generational mode cũng thành product từ JDK25. Không cần experimental unlock chỉ cho các tính năng production nêu trên.

**Câu 5.** Trên OpenJDK JDK25, bật `-XX:+UseShenandoahGC` có mặc định chạy generational mode không?

**Đáp án:** Không; docs JDK25–27 cho thấy default `ShenandoahGCMode=satb`. Cần chọn `-XX:ShenandoahGCMode=generational` nếu muốn mode đó và build hỗ trợ.

**Câu 6.** Generational Shenandoah có phải chính thức từ JDK15 không?

**Đáp án:** Không. Shenandoah collector production từ 15; Generational Shenandoah được productized theo JEP521 ở JDK25.

**Câu 7.** Vì sao không nên chép `-XX:ShenandoahGCHeuristics=compact` từ một cấu hình SATB vào generational mode?

**Đáp án:** Trong tài liệu OpenJDK25–27, generational chỉ hỗ trợ `adaptive` heuristics. Flag không phù hợp có thể gây lỗi startup hoặc hành vi không mong muốn.

**Câu 8.** `-Xmx2g` có bảo đảm container limit 2GiB an toàn không?

**Đáp án:** Không. Java heap không bao gồm toàn bộ native memory/threads/metaspace và GC overhead; phải chừa headroom.

**Câu 9.** Java code dùng `System.gc()` có thể lựa chọn Shenandoah không?

**Đáp án:** Không. Collector được chọn ở VM startup bằng `-XX:+UseShenandoahGC`; `System.gc()` không phải API chọn GC.

**Câu 10.** `javac --release 15` có ép chương trình chạy Shenandoah bản Java15 không?

**Đáp án:** Không. Compiler target bytecode/API, còn GC do runtime JVM quyết định.

**Câu 11.** Lệnh probe thành công có chứng minh SLA low latency đã đạt không?

**Đáp án:** Không. Nó chỉ kiểm tra collector có thể khởi động. SLA cần load tests và monitoring p99, pauses, CPU và memory.

**Câu 12.** Vì sao một service có thể gặp Full GC dù dùng Shenandoah?

**Đáp án:** Khi concurrent GC không theo kịp allocation hoặc thiếu headroom, có thể phát sinh degenerated/full GC fallback và latency lớn.

**Câu 13.** Shenandoah được chọn trên một image Linux amd64 có chắc khả dụng trên image ARM64 tương ứng không?

**Đáp án:** Không chắc. Phải probe đúng image/platform/architecture.

**Câu 14.** G1 đáp ứng SLO với CPU thấp, còn Shenandoah dùng CPU cao mà p99 không cải thiện. Có bắt buộc đổi không?

**Đáp án:** Không. Chọn collector theo kết quả benchmark và tổng chi phí vận hành, không vì nhãn collector mới.

**Câu 15.** Vì sao khi fail Shenandoah nên chặn deployment nếu policy bắt buộc nó?

**Đáp án:** Im lặng fallback khiến kết quả vận hành không đúng cấu hình đã được phê duyệt; phải đổi runtime hoặc có fallback được đánh giá chính thức.

**Câu 16.** `ShenandoahGCMode=generational` có thể dùng nguyên trên mọi JDK21 không?

**Đáp án:** Không. Mainline product generational ở JDK25; vendor có thể backport, nhưng phải kiểm tra đúng JDK distribution/build.

**Câu 17.** Dùng `-XX:+UseShenandoahGC -Xlog:gc=info` có thể tạo số log lines cố định trên mọi máy không?

**Đáp án:** Không. Số GC events và format khác nhau theo runtime/workload/JIT/OS. Test chương trình nên tách stdout của app khỏi GC logs biến động.

**Câu 18.** Vì sao cần kiểm tra CPU throttling khi đánh giá Shenandoah?

**Đáp án:** Concurrent GC cần CPU để reclaim. Nếu throttled, GC có thể chậm và dẫn tới stalls hoặc fallback, làm p99 tăng.

## 20. Checklist cho môi trường hiện hành

- [ ] Đã xác định đúng JDK distribution/vendor/build, version và OS/CPU architecture.
- [ ] Đã probe `java -XX:+UseShenandoahGC -version` trên **chính runtime deploy**.
- [ ] Đã xác nhận `Using Shenandoah`/collector thông qua startup log hoặc VM flags.
- [ ] Không coi Shenandoah là collector mặc định chỉ vì JDK version mới.
- [ ] Với JDK25–27, hiểu default `satb` và generational là **opt-in** khi build hỗ trợ.
- [ ] Không thêm experimental unlock cũ chỉ để chọn production features.
- [ ] Không dùng heuristic/mode flags không được JDK target hỗ trợ.
- [ ] Cấu hình `-Xms`/`-Xmx` theo live set, peak allocation và headroom.
- [ ] Đã chừa memory cho native RSS, stacks, metaspace và direct buffers.
- [ ] Đã xem CPU quota/throttling và đo GC concurrency.
- [ ] Đã bật GC logs ở mức phù hợp, quan sát degenerated/full GC và p99.
- [ ] Đã benchmark với G1/ZGC theo cùng workload và resource budgets.
- [ ] Đã kiểm tra failure/no-support và có policy fail-fast hoặc fallback minh bạch.
- [ ] Đã kiểm tra Docker/Kubernetes/service startup args cuối cùng, không chỉ laptop.
- [ ] Có canary rollout, rollback plan và metrics để quyết định.
- [ ] Đã ghi lại quyết định theo **JDK version và collector mode cụ thể**, không chỉ `"Java 25"`.

## 21. Tài liệu chính thức và tham khảo còn áp dụng

- **JEP 379 — Shenandoah: A Low-Pause-Time Garbage Collector (Production), JDK15:** https://openjdk.org/jeps/379
- **JEP 404 — Generational Shenandoah (Experimental), JDK24:** https://openjdk.org/jeps/404
- **JEP 521 — Generational Shenandoah, product feature JDK25:** https://openjdk.org/jeps/521
- **OpenJDK JDK25 — `java` command / Shenandoah options:** https://github.com/openjdk/jdk/blob/jdk-25-ga/src/java.base/share/man/java.md
- **OpenJDK JDK27 — `java` man page:** https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- **Red Hat build of OpenJDK 25 — Generational Shenandoah release notes:** https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/release_notes_for_red_hat_build_of_openjdk_25.0.1/openjdk25-features
- **Red Hat Developer — Shenandoah GC tuning overview:** https://developers.redhat.com/articles/2024/05/28/beginners-guide-shenandoah-garbage-collector
- **OpenJDK Shenandoah project documentation:** https://wiki.openjdk.org/display/shenandoah/Main
- **OpenJDK JDK17 — `ManagementFactory` và GC MXBeans:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html

**Kết luận:** `-XX:+UseShenandoahGC` là **tên cờ đúng để chọn Shenandoah** trên HotSpot/OpenJDK **có đóng gói và hỗ trợ collector này**. Trước tiên phải **probe chính JVM build/platform sẽ chạy**, sau đó xác nhận qua GC startup logs và kiểm tra hiệu năng. Với các OpenJDK builds JDK25–27 có tính năng này, `satb` còn là mode mặc định, trong khi **Generational Shenandoah là product feature chọn riêng** bằng `-XX:ShenandoahGCMode=generational`. Không sao chép cờ experimental hoặc heuristics không phù hợp; ưu tiên đúng heap budget, CPU headroom, monitoring và benchmark để lựa chọn có căn cứ.

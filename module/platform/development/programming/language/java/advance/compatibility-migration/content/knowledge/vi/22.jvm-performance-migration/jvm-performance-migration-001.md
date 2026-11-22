# Cờ JVM đã deprecated, bị bỏ qua hoặc bị loại bỏ

Khi nâng cấp JDK, ứng dụng Java có thể không khởi động vì một JVM option được chấp nhận ở phiên bản cũ đã bị loại bỏ. Nguy hiểm hơn, ứng dụng có thể **khởi động thành công nhưng một cờ từng điều khiển GC, locking hoặc logging đã trở thành vô hiệu**. Người vận hành tưởng vẫn đang dùng cấu hình tuning cũ, trong khi JVM thực tế chạy với giá trị mặc định hoặc cơ chế mới. Hệ thống không ném exception trong trường hợp này, nhưng độ trễ, CPU, memory footprint, GC pause và khả năng chẩn đoán có thể thay đổi.

Một ví dụ kinh điển là `-XX:MaxPermSize`: Permanent Generation đã bị loại khỏi HotSpot ở JDK 8; trong những JDK còn nhận option cũ, JVM có thể cảnh báo rằng nó **bỏ qua** option đó. Một ví dụ khác là `-XX:+UseConcMarkSweepGC`: CMS bị loại khỏi JDK 14. Một script khởi động mang theo các cờ CMS từ Java 8 không còn là bằng chứng JVM mới vẫn dùng CMS.

Bài này giải thích vòng đời JVM flags trong HotSpot, cách phân biệt **deprecated**, **obsolete/ignored**, **expired/removed**, các trường hợp tương thích dễ nhầm, phương pháp thu thập options hiệu lực và quy trình thay thế cờ cũ khi thực hiện Java Advance Compatibility Migration.

## 1. Cờ JVM là gì và được truyền ở đâu?

JVM flags là các tham số dùng để cấu hình cách máy ảo Java khởi động và vận hành. Chúng không giống tham số nghiệp vụ truyền cho method `main(String[] args)`.

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -XX:+UseG1GC -jar orders-service.jar --profile=prod
~~~

Trong ví dụ:

- `-Xms512m` và `-Xmx2g` điều khiển kích thước heap theo chính sách JVM.
- `-XX:+UseG1GC` yêu cầu bộ thu gom rác G1 ở HotSpot có hỗ trợ.
- `-jar orders-service.jar` chọn ứng dụng.
- `--profile=prod` sau tên JAR là tham số **ứng dụng**, không phải một `-XX` flag của JVM.

Một hệ thống còn có thể truyền thêm options bằng script, container image, service manager, IDE hoặc biến môi trường, nên dòng lệnh mà lập trình viên nhìn thấy không nhất thiết là toàn bộ cấu hình.

### 1.1. Các nhóm tùy chọn phổ biến

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| Standard options | `-version`, `-cp`, `--module-path` | Tham số được tài liệu Java launcher định nghĩa |
| Extra options `-X` | `-Xms`, `-Xmx`, `-Xlog` | Tùy chọn thêm, thường đặc thù HotSpot |
| Advanced options `-XX` | `-XX:+UseG1GC`, `-XX:MaxRAMPercentage=75` | Điều khiển GC, JIT, memory, serviceability... |
| System properties `-D` | `-Dfile.encoding=UTF-8` | Tạo Java system property, không phải mọi property đều là JVM tuning flag |
| Module/runtime options | `--add-opens`, `--add-exports` | Điều khiển truy cập module theo các quy tắc JDK |
| Agent options | `-javaagent`, `-agentpath` | Nạp Java/native agent khi startup |
| Application arguments | `--spring.profiles.active=prod` sau `-jar app.jar` | Do ứng dụng/framework tự xử lý |

Một `-D...` có thể làm hành vi nền tảng thay đổi, nhưng không nên gộp tất cả system properties vào nhóm `-XX` vì vòng đời và thông báo lỗi có thể khác nhau.

### 1.2. Cú pháp boolean và giá trị

Một flag boolean của HotSpot thường có dạng:

~~~bash
-XX:+SomeFeature   # Yêu cầu bật
-XX:-SomeFeature   # Yêu cầu tắt
~~~

Một flag nhận giá trị:

~~~bash
-XX:MaxMetaspaceSize=256m
-XX:MaxRAMPercentage=70.0
~~~

Dấu `+`/`-` và dạng `=value` không thể dùng tùy tiện cho mọi flag. Option sai cú pháp, ngoài khoảng cho phép hoặc phụ thuộc vào một điều kiện khác vẫn có thể khiến JVM từ chối khởi động dù tên flag được nhận diện.

## 2. Vòng đời một HotSpot flag: dùng được không đồng nghĩa còn tác dụng

HotSpot có quy trình thay đổi vòng đời của nhiều cờ được dùng để tuning. Các thuật ngữ quan trọng:

| Trạng thái | JVM thường làm gì? | Tác động thực tế |
|---|---|---|
| **Supported / active** | Nhận và thực thi option theo chức năng được tài liệu hóa | Cờ có thể ảnh hưởng runtime |
| **Deprecated** | Vẫn nhận và **vẫn áp dụng**, nhưng phát cảnh báo | Cần lên kế hoạch thay thế, chưa được phép giả định cờ vô dụng |
| **Obsolete** | Có thể tiếp tục nhận, cảnh báo và **bỏ qua giá trị** | Cờ có thể không còn tác dụng dù JVM chạy được |
| **Expired / removed** | Không còn nhận option hoặc báo unrecognized VM option | JVM có thể thoát trước khi ứng dụng chạy |
| **Ignored do ngữ cảnh** | Option có thể hợp lệ nhưng không ảnh hưởng trong cấu hình hiện tại | Không nhất thiết có cảnh báo; cần xác minh tính hiệu lực |
| **Locked / experimental / diagnostic** | Cờ tồn tại nhưng yêu cầu mở khóa hoặc điều kiện phù hợp | Không phải đã deprecated hay bị loại bỏ |

Theo mô tả vòng đời của HotSpot, đường đi thường là:

~~~text
ACTIVE
   |
   v
DEPRECATED
  Vẫn dùng và cảnh báo
   |
   v
OBSOLETE
  Nhận nhưng bỏ qua, cảnh báo
   |
   v
EXPIRED / REMOVED
  Không nhận, có thể làm JVM fail startup
~~~

Đây là **mô hình khái niệm**. Không phải mọi flag đều trải qua đủ các giai đoạn; các cờ thử nghiệm hoặc phụ thuộc JVM implementation có thể có chính sách khác. Không thể xác định trạng thái chỉ từ tên cờ: phải đối chiếu với **JDK feature release, update release, JVM vendor và build**.

### 2.1. Deprecated: còn hiệu lực, nhưng phải chuẩn bị migration

Nếu một cờ ở trạng thái deprecated, JVM có thể in cảnh báo như:

~~~text
Java HotSpot(TM) 64-Bit Server VM warning:
  Option SomeFlag was deprecated in version X
  and will likely be removed in a future release.
~~~

Mẫu trên là minh họa, không phải thông điệp cố định cho mọi version. **Không xóa một cờ tuning quan trọng chỉ vì có chữ deprecated** rồi cho rằng hành vi sẽ giữ nguyên. Hãy ghi lại baseline, hiểu tác dụng hiện tại, chọn phương án mới và test trên runtime mục tiêu.

### 2.2. Obsolete: còn nhận nhưng không còn điều khiển JVM

Một cờ obsolete có thể tạo thông báo kiểu:

~~~text
OpenJDK 64-Bit Server VM warning:
  Ignoring option SomeFlag; support was removed in ...
~~~

JVM có thể tiếp tục khởi động. Đây là trường hợp dễ gây hiểu nhầm: hệ thống chạy được **không chứng minh cờ đang hoạt động**. Nếu trước đây cờ điều khiển GC hoặc locking, hiệu năng có thể khác hoàn toàn.

### 2.3. Removed/expired: lỗi khởi động rõ ràng

Ví dụ minh họa:

~~~text
Unrecognized VM option 'SomeOldFlag'
Error: Could not create the Java Virtual Machine.
Error: A fatal exception has occurred.
~~~

Đây là lỗi JVM parsing/configuration, thường xảy ra **trước `main()`**. Nếu log ứng dụng không xuất hiện, không có nghĩa code chưa được deploy; có thể tiến trình Java không qua được giai đoạn parse options.

Một số lỗi tương tự còn đến từ flag viết sai chính tả hoặc option được hỗ trợ trên JVM vendor khác. Cần phân biệt “bị loại bỏ theo JDK” với “không hề tồn tại trên runtime hiện tại”.

### 2.4. Ignored vì hoàn cảnh không giống obsolete

Ví dụ một flag chỉ ảnh hưởng một GC cụ thể nhưng ứng dụng đang chạy GC khác. Một số HotSpot versions có thể chấp nhận option mà nó không có tác dụng trong cấu hình hiện tại. Ngoài ra, JVM có thể tự điều chỉnh một số giá trị trong runtime hoặc dùng cơ chế ergonomics.

Vì vậy, **được parser chấp nhận**, **được lưu làm flag**, **có tác động thực tế** là ba mức kiểm chứng khác nhau.

## 3. Các ví dụ lịch sử quan trọng khi nâng JDK

### 3.1. Permanent Generation bị loại khỏi HotSpot từ JDK 8

Trước JDK 8, HotSpot có Permanent Generation (PermGen) và một số cờ như:

~~~bash
-XX:PermSize=128m
-XX:MaxPermSize=256m
~~~

JDK 8 thay PermGen bằng **Metaspace** (JEP 122). Các flag PermGen trong những runtime còn tương thích cú pháp có thể bị bỏ qua và phát cảnh báo.

Một cấu hình legacy:

~~~bash
java -XX:MaxPermSize=256m -jar app.jar
~~~

không phải là cách giới hạn Metaspace trên các JDK mới. Những tùy chọn Metaspace cần xét gồm:

~~~bash
-XX:MetaspaceSize=128m
-XX:MaxMetaspaceSize=512m
~~~

**Không thay `MaxPermSize=256m` bằng `MaxMetaspaceSize=256m` một cách máy móc.** PermGen và Metaspace có cơ chế quản lý, memory accounting và tác động khác nhau; giới hạn metaspace quá thấp có thể dẫn tới `OutOfMemoryError: Metaspace`. Phải đo class loading, metaspace commit/usage và native memory trước khi chọn giới hạn.

### 3.2. CMS GC bị loại khỏi JDK 14

Collector **Concurrent Mark Sweep (CMS)** bị deprecated từ JDK 9 và bị loại khỏi JDK 14 theo **JEP 363**. Các option lịch sử như:

~~~bash
-XX:+UseConcMarkSweepGC
-XX:+CMSClassUnloadingEnabled
-XX:CMSInitiatingOccupancyFraction=70
~~~

không còn là một chiến lược tuning CMS hợp lệ trên JDK đích sau khi CMS bị loại. Ở một số bản, JVM có thể cảnh báo/bỏ qua cờ cũ; ở bản khác, cờ đã hết vòng đời và có thể bị từ chối.

**Hướng migration:** chọn collector còn được hỗ trợ, chẳng hạn G1 cho workload phù hợp:

~~~bash
java -XX:+UseG1GC -Xmx4g -jar app.jar
~~~

Nhưng thay `UseConcMarkSweepGC` bằng `UseG1GC` không bảo đảm cùng latency, throughput và footprint. CMS và G1 có policy, tuning knobs, cách xử lý vùng nhớ và pause model khác nhau. Hãy đo GC logs, p95/p99 latency, CPU, allocation rate và heap occupancy trước/sau thay đổi.

### 3.3. Biased locking: deprecated ở JDK 15, obsolete từ JDK 18

**JEP 374** vô hiệu hóa biased locking mặc định và deprecated các option liên quan ở **JDK 15**. Theo JDK 18 release notes, `UseBiasedLocking` và một số tùy chọn như `BiasedLockingStartupDelay` đã trở thành **obsolete**, được cảnh báo và bỏ qua ở JDK 18.

Ví dụ option legacy:

~~~bash
-XX:+UseBiasedLocking
-XX:BiasedLockingStartupDelay=0
~~~

Nếu chỉ copy hai cờ từ một hướng dẫn tối ưu cũ sang Java 21, không thể kết luận JVM còn bật biased locking. Các phiên bản sau có thể có trạng thái hỗ trợ khác, vì vậy cần kiểm tra ở đúng JDK mục tiêu.

Nếu ứng dụng dùng nhiều synchronized operations không tranh chấp, hãy đo tác động thực tế của JVM mới. Không nên cố giữ một cơ chế locking đã bị thay đổi bằng cờ không còn tác dụng.

### 3.4. GC logging chuyển sang Unified Logging từ JDK 9

Trước JDK 9, script thường sử dụng các flag như:

~~~bash
-verbose:gc
-Xloggc:/var/log/app/gc.log
-XX:+PrintGCDetails
-XX:+PrintGCDateStamps
-XX:+UseGCLogFileRotation
~~~

JDK 9 giới thiệu hệ thống **Unified JVM Logging** (JEP 158); nhiều flag GC/tracing cũ bị deprecated, aliased, obsolete hoặc bị loại bỏ qua các bản JDK sau đó. Không nên giả định mọi flag ở danh sách trên có cùng trạng thái tại tất cả JDK.

Một cách viết kiểu mới cho HotSpot:

~~~bash
java \
  -Xlog:gc*,safepoint=info:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=10M \
  -jar app.jar
~~~

Lệnh minh họa dùng cú pháp shell kiểu Unix. `gc*` chọn các tag GC liên quan, `safepoint=info` bổ sung nhóm safepoint, phần `filecount`/`filesize` cấu hình rotation theo Unified Logging.

Cấu hình mới không phải phép chuyển từng cờ 1-1 một cách tuyệt đối. Cần xác định nhóm event, log level, decorators và rotation để đáp ứng nhu cầu phân tích GC của hệ thống. Ví dụ `-Xloggc` vẫn có thể ở trạng thái deprecated trong một JDK mới, nhưng dùng `-Xlog:gc:file=...` giúp loại bỏ phụ thuộc cú pháp legacy.

### 3.5. Tracing flags của class loading

Một số ứng dụng cũ dùng:

~~~bash
-XX:+TraceClassLoading
-XX:+TraceClassUnloading
-XX:+TraceExceptions
~~~

Những tracing flags này được thay bằng Unified Logging và trở nên obsolete ở các mốc sau khi JDK 9 giới thiệu cơ chế mới. Các tương đương thường gặp:

~~~bash
-Xlog:class+load=info
-Xlog:class+unload=info
-Xlog:exceptions=info
~~~

Ví dụ:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

Đừng chỉ thay tên cờ mà không kiểm tra log volume và nơi ghi. Class loading log ở production có thể rất lớn, nên cần giới hạn thời gian, mức log và dung lượng.

### 3.6. `--illegal-access`: obsolete không có nghĩa đóng gói được nới lỏng

Trong quá trình JPMS migration, `--illegal-access=permit` từng được dùng để tạm nới khả năng reflection vào một số package nội bộ của JDK. JDK 17 (JEP 403) làm option này trở thành **obsolete**; nó không còn thực hiện cơ chế relaxed strong encapsulation như ở các JDK cũ.

Ví dụ:

~~~bash
java --illegal-access=permit -jar legacy-app.jar
~~~

Trong một bản JDK mà option vẫn được chấp nhận nhưng bỏ qua, sự có mặt của nó trên command line **không bảo đảm reflection được phép**. Hướng xử lý là nâng framework sử dụng JDK internals hoặc cấu hình có mục đích như:

~~~bash
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

Chỉ dùng `--add-opens` khi đã xác định rõ package, caller và nhu cầu deep reflection; không nên biến đây thành danh sách quyền mở không kiểm soát.

### 3.7. Security Manager là ví dụ liên quan đến system property

`java.security.manager` chủ yếu là **system property**, không phải cờ `-XX`, nhưng vẫn cần được kiểm kê trong migration vì nhiều script ghi chung với JVM flags.

Ở **JDK 24**, theo JEP 486, việc kích hoạt Java Security Manager đã bị vô hiệu hóa vĩnh viễn. Một command line cố bật `-Djava.security.manager=allow` hoặc một chế độ kích hoạt tương tự có thể làm JVM báo lỗi và thoát. Điều này khác với flag obsolete được chấp nhận nhưng bỏ qua.

Nếu ứng dụng dùng Security Manager như sandbox, việc xóa property để JVM khởi động là chưa đủ: phải đánh giá lại mô hình an toàn, vì cơ chế bảo vệ trước đây không còn hiện diện. Phân tách process/container, quyền hệ điều hành và network policies là những biện pháp cần xem xét.

### 3.8. Một số RTM locking options bị loại ở JDK 25

Oracle JDK 25 `java` command documentation ghi nhận các option RTM locking liên quan như:

~~~bash
-XX:+UseRTMDeopt
-XX:RTMAbortRatio=50
-XX:RTMRetryCount=5
~~~

trong nhóm đã bị loại bỏ ở JDK 25. Một script tuning khóa cũ mang theo chúng có thể gặp `Unrecognized VM option` trên bản đó.

Đây là ví dụ cho thấy không chỉ GC flags mới thay đổi. Các tùy chọn JIT, locking, CPU-specific intrinsics và tracing cũng có vòng đời. Khi nâng qua nhiều major release, cần rà soát toàn bộ options, không chỉ `-Xmx` và `-XX:+UseG1GC`.

## 4. Bảng phân loại những trường hợp hay gặp

Bảng dưới đây mô tả **mốc thay đổi đã được tài liệu hóa**, không khẳng định cờ giữ nguyên trạng thái ở mọi JDK mới hơn.

| Option / nhóm | Mốc đáng chú ý | Điều phải làm |
|---|---|---|
| `-XX:PermSize`, `-XX:MaxPermSize` | PermGen bị loại ở JDK 8; flag legacy có thể bị bỏ qua | Xóa flag cũ, đánh giá Metaspace thay vì map 1-1 |
| `-XX:+UseConcMarkSweepGC` và CMS options | CMS deprecated JDK 9, removed JDK 14 | Chọn GC hiện có, đo lại pause/throughput |
| `-XX:+UseBiasedLocking` | Disabled/deprecated JDK 15, obsolete JDK 18 | Xóa cờ legacy, đo concurrency/locking |
| `-XX:+TraceClassLoading` | Dịch chuyển sang Unified Logging sau JDK 9 | Dùng `-Xlog:class+load=info` |
| `-XX:+TraceClassUnloading` | Dịch chuyển sang Unified Logging | Dùng `-Xlog:class+unload=info` |
| `-XX:+TraceExceptions` | Dịch chuyển sang Unified Logging | Dùng `-Xlog:exceptions=info` |
| `-Xloggc:...` | Được khuyến nghị thay bằng Unified Logging | Dùng `-Xlog:gc:...` theo cú pháp mới |
| `--illegal-access=permit` | Obsolete từ JDK 17 | Không kỳ vọng flag mở lại internal APIs |
| `-Djava.security.manager=allow` | Kích hoạt Security Manager bị chặn ở JDK 24 | Thiết kế lại bảo vệ, không tìm cờ bypass |
| Một số `-XX:RTM...` | Removed trong JDK 25 | Loại khỏi script và đo lock performance |
| `-XX:+IgnoreUnrecognizedVMOptions` | Vẫn có thể được một số HotSpot hỗ trợ như cơ chế bỏ qua cờ không nhận diện | Không dùng để che lỗi migration |

Các option `-XX` mang tính **JVM implementation-specific**, nên một cờ của HotSpot không nhất thiết được OpenJ9 hoặc GraalVM chấp nhận theo cùng ý nghĩa. Cũng có thể có khác biệt giữa vendor/build updates.

## 5. Cờ có mặt trong `PrintFlagsFinal` chưa chắc được dùng

HotSpot hỗ trợ một số chế độ in flags:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Kết quả có thể chứa tên flag, kiểu, giá trị và nguồn thiết lập. Một ví dụ minh họa cấu trúc:

~~~text
size_t MaxHeapSize = ... {product} {ergonomic}
bool UseG1GC = true {product} {command line}
~~~

Không nên copy những dòng mẫu làm kết quả cố định: giá trị và marker phụ thuộc JDK, host, container và lệnh thực tế.

### 5.1. Ý nghĩa của “giá trị hiệu lực”

Một JVM flag có thể là:

- Được đặt bởi người dùng trên command line.
- Được JVM chọn qua ergonomics.
- Được tính từ CPU/RAM/container limits.
- Phụ thuộc flag khác hoặc collector cụ thể.
- Có thể điều chỉnh ở runtime nếu flag thuộc nhóm manageable.
- Không còn tồn tại trong danh sách vì đã obsolete/removed.

Bởi vậy, `PrintFlagsFinal` là bằng chứng quan trọng nhưng **không đủ** để xác nhận một tuning knob thực sự đang cải thiện hiệu năng. Cần so sánh log và metric liên quan đến chức năng mà nó được cho là điều khiển.

### 5.2. `PrintCommandLineFlags` và `VM.flags`

Một số HotSpot versions hỗ trợ:

~~~bash
java -XX:+PrintCommandLineFlags -version
~~~

Lệnh này giúp xem các flag đáng chú ý trên command line/ergonomics, nhưng không phải luôn in mọi option trong một deployment phức tạp.

Với tiến trình đang chạy:

~~~bash
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
~~~

`12345` là PID minh họa. `VM.command_line` giúp xem startup command, còn `VM.flags` và `VM.flags -all` dùng để khảo sát flags mà JVM báo cáo. Những lệnh chẩn đoán phụ thuộc vào hỗ trợ của JVM và quyền attach/process; kiểm tra `jcmd 12345 help` nếu không rõ.

### 5.3. `-Xlog:arguments` không phải nguồn tổng quát cho mọi JDK

Trong các tình huống cần log command line hoặc startup, hãy chọn tag/log option **đã được tài liệu của JDK đích hỗ trợ**, không tự phát minh một tag. `java -Xlog:help` giúp xem unified logging tags và cấu hình khả dụng.

~~~bash
java -Xlog:help
~~~

Các tag không tồn tại hoặc cú pháp sai cũng có thể khiến JVM khởi động thất bại.

## 6. Điều tra nguồn cờ JVM: không chỉ `JAVA_HOME`

Trong hệ thống hiện đại, startup flags có thể đến từ nhiều lớp:

~~~text
Dockerfile / base image
       |
       +--> Entrypoint shell script
       |       |
       |       +--> JAVA_OPTS (quy ước riêng của script/framework)
       |       +--> JAVA_TOOL_OPTIONS
       |       +--> JDK_JAVA_OPTIONS
       |       +--> _JAVA_OPTIONS (implementation-specific)
       |       +--> java @args-file
       |
       +--> Kubernetes Deployment / Helm values
       |
       +--> Service manager (systemd, Windows Service)
       |
       +--> CI/CD deployment variables
       |
       v
    JVM command line thực tế
~~~

### 6.1. `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS`

Các biến này có thể chèn tùy chọn vào quá trình khởi động Java theo phạm vi hỗ trợ của launcher/JVM. Chúng rất hữu ích trong container hoặc build/test, nhưng cũng khiến một tùy chọn không còn hợp lệ được truyền đến nhiều Java processes ngoài ý muốn.

Ví dụ:

~~~bash
export JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65.0"
java -jar app.jar
~~~

Hoặc:

~~~bash
export JDK_JAVA_OPTIONS="-Xlog:gc"
java -jar app.jar
~~~

Hai biến có phạm vi xử lý và giới hạn riêng. Không nên giả định chúng giống nhau về mọi tham số và thứ tự. Trong môi trường đa JDK, một biến dành cho JDK mới có thể phá process còn chạy JDK cũ.

### 6.2. `JAVA_OPTS` không phải tham số chuẩn của Java launcher

Nhiều Docker entrypoint, application server hoặc startup script dùng biến `JAVA_OPTS` nhưng chính Java launcher không bắt buộc tự đọc nó. Điều này có nghĩa việc thay đổi `JAVA_OPTS` chỉ có tác dụng nếu script đã dùng biến đó trong command line.

Cần đọc entrypoint hoặc process arguments thực tế, không chỉ đọc giá trị môi trường rồi kết luận.

### 6.3. Argument files

Java launcher có thể đọc tham số từ file:

~~~text
# jvm.args
-Xms512m
-Xmx2g
-XX:+UseG1GC
-Xlog:gc*:file=gc.log:time,uptime,level,tags
~~~

Khởi động bằng:

~~~bash
java @jvm.args -jar app.jar
~~~

Khi audit, nhớ kiểm tra cả `@...` files. Một file chứa flag obsolete có thể nằm trong image hoặc volume, hoàn toàn ngoài repository ứng dụng.

### 6.4. Kiểm soát thông tin nhạy cảm

Log command line hoặc dump environment có thể chứa token, mật khẩu, endpoint nội bộ. Chỉ thu thập cờ liên quan và xóa secret trước khi chia sẻ, đặc biệt nếu dùng `-Dsome.password=...`. Không đưa toàn bộ process command line vào ticket công khai.

## 7. Quy trình audit JVM flags trước khi nâng JDK

### Bước 1: Xác định runtime nguồn và đích

Ghi rõ:

~~~bash
java -version
java -XshowSettings:vm -version
~~~

Nếu có nhiều JDK trong máy, hãy chạy lệnh bằng executable thực tế trong image hoặc host triển khai. Chỉ dựa vào JDK của laptop không đủ để xác nhận hành vi production.

Cần ghi:

- JDK feature/update/build.
- Vendor và JVM implementation.
- OS/architecture.
- Container image, CPU/RAM limits.
- Command line/JVM options hiệu lực.

### Bước 2: Thu thập tất cả startup options

Xem application manifest/script, Dockerfile, service manager, Kubernetes values, CI deployment và biến môi trường. Ghi cả options được inject tự động bởi APM, platform hoặc sidecar.

Tạo một inventory:

| Flag | Nguồn | Mục đích lịch sử | Trạng thái trên JDK đích | Hành động |
|---|---|---|---|---|
| `-XX:MaxPermSize=256m` | Startup script | Giới hạn PermGen | Legacy/ignored | Xóa, đo Metaspace |
| `-XX:+UseConcMarkSweepGC` | Helm values | GC CMS | CMS đã bị loại | Chọn GC mới, benchmark |
| `-Xloggc:gc.log` | Wrapper script | GC log file | Cú pháp cũ/deprecated ở JDK mới | Chuyển Unified Logging |
| `-XX:+UseBiasedLocking` | Shared JAVA_OPTS | Lock tuning | Obsolete tại mốc JDK 18 | Xóa, đo lock contention |
| `-Xmx2g` | Dockerfile | Heap cap | Tùy chọn còn dùng | Xác minh với container limit |
| `--add-opens=...` | Runtime config | Reflection integration | Phụ thuộc package/module | Kiểm tra necessity và scope |

Không cần chỉnh sửa ngay mọi dòng. Đầu tiên phải biết **cờ có thực sự được sử dụng và có ảnh hưởng gì**.

### Bước 3: Phân loại theo vòng đời

Với từng flag:

1. Nó thuộc HotSpot hay JVM vendor khác?
2. Bản JDK đích nhận option không?
3. Có warning deprecated/obsolete không?
4. Nếu được nhận, nó còn tác động không?
5. Có tùy chọn thay thế chính thức không?
6. Bỏ nó có thay đổi default/ergonomics không?
7. Có test/metric nào xác nhận mục tiêu tuning ban đầu không?

Lưu tài liệu release notes hoặc JEP cụ thể cho các thay đổi đáng kể, thay vì đoán từ một danh sách flag cũ.

### Bước 4: Smoke-test khả năng parse flags

Trên runtime mục tiêu, thử khởi động một JVM với những flag thực tế nhưng không chạy ứng dụng trước:

~~~bash
java -Xms512m -Xmx2g -XX:+UseG1GC -version
~~~

Nếu một option không được nhận, có thể phát hiện lỗi sớm. Nhưng **`-version` thành công chỉ chứng minh một phần của startup path**. Một số option chỉ có tác động hoặc lỗi khi class loading, native agent, GC, module hoặc workload ứng dụng được kích hoạt.

Dùng một môi trường thử nghiệm và kiểm tra cả **exit code lẫn stderr**. Warning không phải lúc nào khiến exit code khác 0.

### Bước 5: So sánh flags trước/sau

Ghi output của `PrintFlagsFinal`, `VM.flags` và JVM command line ở cả JDK nguồn/đích. Đừng so sánh toàn bộ output theo kiểu “giá trị càng giống càng tốt”: JDK mới có thể đổi default hoặc bỏ biến không còn tương ứng.

Điểm cần tìm là sự thay đổi ở **các giả định về hiệu năng và vận hành**: collector, heap sizing, logging, tiered compilation, code cache, container awareness và flags do user chỉ định.

### Bước 6: Kiểm thử workload có giám sát

Chạy cùng artifact/workload/cấu hình dữ liệu trong điều kiện đủ đại diện. Quan sát:

- Startup time.
- Heap usage, GC allocation rate, pause times.
- p50/p95/p99 latency.
- Throughput, CPU utilization.
- Container memory limit/OOM kills.
- Native memory/Metaspace.
- JIT warmup, compilation activity nếu liên quan.
- Log volume và khả năng chẩn đoán sau sự cố.

Không khẳng định “đã tương đương” chỉ vì JVM không phát warning và healthcheck xanh.

## 8. Chuyển GC logging cũ sang `-Xlog`

GC logging là nhóm cờ dễ chuyển đổi nhất nhưng có nhiều bẫy.

### 8.1. Cú pháp Unified Logging tổng quát

Một dạng thường thấy:

~~~text
-Xlog:<what>:<output>:<decorators>:<output-options>
~~~

Trong đó:

- `what` xác định tags và level, ví dụ `gc*` hoặc `gc+heap=debug`.
- `output` có thể là `stdout`, `stderr` hoặc file.
- `decorators` bổ sung thời gian, uptime, level, tags, v.v.
- `output-options` hỗ trợ rotation cho file trong những cấu hình phù hợp.

Ví dụ:

~~~bash
-Xlog:gc*:file=logs/gc.log:time,uptime,level,tags:filecount=10,filesize=20M
~~~

Khi output file ở thư mục chưa tồn tại hoặc không có quyền ghi, JVM có thể báo lỗi khởi động hoặc không tạo được log. Chuẩn bị filesystem, disk quota và quy tắc rotation trong container trước khi triển khai.

### 8.2. Không chuyển 1-1 bằng tên

Một script cũ có `PrintGCDetails` và `PrintGCDateStamps` chưa chắc cần một loạt `-Xlog` tags giống hệt. Nên đặt câu hỏi:

- Mục tiêu là đo pause time hay phân tích heap occupancy?
- Cần thông tin safepoint không?
- Có cần rotation và dung lượng bao nhiêu?
- Log được collector nào tạo?
- Có cần tương thích với parser/dashboard hiện tại không?

Khi chuyển, hãy kiểm tra công cụ phân tích GC log có hiểu định dạng mới. Việc JVM ghi log thành công không đồng nghĩa dashboard vẫn đọc được dữ liệu như cũ.

### 8.3. Log level ảnh hưởng overhead

`info` thường phù hợp hơn khi theo dõi vận hành; `debug` hoặc `trace` có thể tăng log volume và overhead đáng kể. Không bật tất cả tags ở `trace` trong production chỉ vì muốn “giữ nguyên độ chi tiết” của một cờ lịch sử.

## 9. Chọn GC mới: không có ánh xạ 1-1 cho các flags CMS

Nếu hệ thống nâng từ JDK 8 dùng CMS lên JDK mới, một số tuning knobs cũ không còn tương đương trực tiếp.

### 9.1. Ví dụ cấu hình CMS cũ

~~~bash
java \
  -Xms4g -Xmx4g \
  -XX:+UseConcMarkSweepGC \
  -XX:CMSInitiatingOccupancyFraction=70 \
  -XX:+UseCMSInitiatingOccupancyOnly \
  -jar service.jar
~~~

Không nên sửa thành:

~~~text
Thay tên CMS bằng G1
Giữ nguyên mọi ngưỡng %
Giả định pause time tương đương
~~~

G1 có cơ chế chọn vùng, pause prediction và concurrent marking riêng. Những tham số CMS không phải knobs được dịch trực tiếp cho G1.

### 9.2. Cách bắt đầu lại

Một cấu hình đơn giản hơn:

~~~bash
java \
  -Xms4g -Xmx4g \
  -XX:+UseG1GC \
  -Xlog:gc*:file=logs/gc.log:time,uptime,level,tags \
  -jar service.jar
~~~

Sau đó đo thực tế, xác định mục tiêu SLO và cân nhắc tuning phù hợp G1, ví dụ `-XX:MaxGCPauseMillis` khi có lý do. Giá trị mong muốn không phải cam kết pause tuyệt đối, và không nên sao chép từ hướng dẫn tuning CMS.

JDK mới còn có các collector khác như ZGC hoặc Shenandoah ở những runtime có hỗ trợ. Việc lựa chọn collector cần dựa trên workload và support matrix, không theo tên flag cũ.

## 10. Flags memory và container: hợp lệ vẫn có thể không phù hợp

Không phải mọi vấn đề sau nâng JDK đều do cờ bị deprecated. Một số flag vẫn hợp lệ nhưng tương tác với **ergonomics mới** hoặc cấu hình container khác nhau.

### 10.1. `-Xmx` và tỉ lệ RAM

Ví dụ:

~~~bash
-Xmx2g
-XX:MaxRAMPercentage=70.0
~~~

Khi cấu hình giới hạn heap tường minh bằng `-Xmx`, đừng suy rằng `MaxRAMPercentage` sẽ được dùng theo cách bạn mong đợi. Cần kiểm tra `MaxHeapSize` thực tế qua JVM flags hoặc `-XshowSettings:vm`.

Với container có memory limit, cần đo tổng RSS chứ không chỉ heap: JVM còn dùng Metaspace, code cache, direct buffers, thread stacks và native allocations.

### 10.2. `UseContainerSupport` và CPU detection

Các JDK HotSpot hiện đại trên Linux có khả năng nhận diện tài nguyên container. Nhưng thuật toán xử lý cgroups, CPU quota và memory limits có thể thay đổi theo phiên bản JDK và môi trường.

Khi nâng JDK đồng thời đổi image/kernel/cgroup version, một khác biệt GC threads hoặc `Runtime.availableProcessors()` không nhất thiết đến từ cờ cũ bị bỏ qua. Có thể kiểm tra:

~~~bash
java -Xlog:os+container=info -version
java -XX:+PrintFlagsFinal -version
~~~

Định dạng và mức log phụ thuộc JDK. Trên một số runtime có thể cần `debug` để thấy thông tin cụ thể hơn.

### 10.3. Không giữ mãi “tuning magic” của môi trường cũ

Một `JAVA_OPTS` có hàng chục `-XX` flags nhưng không có căn cứ đo lường làm migration khó hơn. Một số flag từng khắc phục bug ở JDK 8 đã trở nên không cần thiết hoặc gây xấu hiệu năng trên JDK mới.

Chiến lược hợp lý là bắt đầu từ một cấu hình có ít tùy chỉnh, đo baseline mới, rồi bổ sung flag khi có **giả thuyết và kết quả đo hỗ trợ**. Không xóa mù quáng các giới hạn quan trọng như heap, OOM diagnostics hoặc proxy/network settings.

## 11. `IgnoreUnrecognizedVMOptions`: vì sao không nên dùng làm phương án migration

HotSpot hỗ trợ tùy chọn:

~~~bash
-XX:+IgnoreUnrecognizedVMOptions
~~~

Tùy chọn này có thể làm JVM **bỏ qua một số VM options không được nhận diện** thay vì lỗi ngay. Nó đôi khi được sử dụng ở script chung cho nhiều JDK để tránh startup fail khi một JDK không hiểu một flag.

Nhưng trong migration nó có rủi ro nghiêm trọng:

- Một typo trong tên flag có thể bị bỏ qua thay vì phát hiện.
- Một cờ tuning quan trọng có thể không còn hiệu lực nhưng hệ thống vẫn chạy.
- Khác biệt giữa JVM vendor có thể bị che.
- Một số lỗi tham số hoặc chính sách khác vẫn không nhất thiết được option này xử lý.
- Vận hành mất bằng chứng rõ về việc một cấu hình không còn được hỗ trợ.

Ví dụ:

~~~bash
java -XX:+IgnoreUnrecognizedVMOptions \
     -XX:+SomeNonexistentTuningFlag \
     -version
~~~

Lệnh chỉ minh họa vấn đề; **không khuyến nghị** dùng nó trong production để bỏ qua các cờ lạ. Một JVM vẫn khởi động không chứng minh mọi thiết lập đã có hiệu lực.

Nếu cần script dùng chung cho nhiều JDK, phương án tốt hơn là **phân nhánh cấu hình theo JDK được hỗ trợ**, có test startup riêng cho từng JDK và xác minh flags hiệu lực. Tránh dùng một cờ “ignore” toàn cục như lớp che lỗi.

### 11.1. Startup gate nên nghiêm ngặt

Trong CI hoặc canary, một warning “obsolete flag ignored” nên được xem là khoản nợ migration cần xử lý, dù exit code bằng 0. Với lỗi `Unrecognized VM option`, build/deploy cần dừng và báo nguyên nhân rõ.

Có thể thu thập stderr của lần khởi động thử trong môi trường không nhạy cảm, nhưng không nên đưa nguyên văn mọi log có secret ra pipeline artifact công khai.

## 12. Deprecated khác với experimental và diagnostic

HotSpot có các nhóm cờ phục vụ diagnostics hoặc tính năng thử nghiệm, đôi khi cần mở khóa:

~~~bash
-XX:+UnlockDiagnosticVMOptions
-XX:+UnlockExperimentalVMOptions
~~~

Đây **không phải** cách khôi phục mọi flag đã bị xóa. Một flag experimental được bảo vệ bởi bước mở khóa không đồng nghĩa flag đó deprecated; một flag đã expired sẽ không tự trở lại chỉ vì `UnlockExperimentalVMOptions` được bật.

### 12.1. Lỗi locked flag

JVM có thể báo một flag chỉ được dùng sau khi bật unlock tương ứng. Khi đó cần xem liệu team có thực sự cần cờ đó và rủi ro khi sử dụng trong production.

### 12.2. Experimental flags không có cùng cam kết ổn định

Các tùy chọn phục vụ thử nghiệm có thể thay đổi nhanh hơn hoặc có ít bảo đảm về tương thích. Không nên coi một experimental flag được dùng ở môi trường benchmark là một phần của giao diện tuning ổn định qua nhiều JDK.

### 12.3. Diagnostic flags không thay thế observability lâu dài

Một flag chẩn đoán có thể tạo lượng log rất lớn hoặc làm thay đổi profile performance. Sử dụng trong runbook phải ghi rõ mục đích, thời gian bật, giới hạn dung lượng và kế hoạch tắt.

## 13. Kiểm tra cờ trên từng JVM vendor và architecture

Java SE định nghĩa nhiều API và hành vi nền tảng, nhưng `-XX` flags thường gắn với implementation. HotSpot, OpenJ9 và các bản phân phối tùy biến có thể sử dụng cú pháp/tuning option khác nhau.

Ví dụ:

- HotSpot sử dụng `-XX:+UseG1GC` trong các JDK hỗ trợ G1.
- OpenJ9 có các tùy chọn quản lý memory/GC theo cơ chế riêng.
- Một số intrinsic hoặc RTM options phụ thuộc CPU/platform.
- Container flags có thể có hành vi khác theo OS.
- Diagnostic serviceability commands có thể khác nhau.

Vì thế một script được thiết kế cho “Java 21” chưa chắc chạy giống nhau trên mọi JVM Java 21. Cần đặt tên rõ **vendor/implementation**, hoặc giới hạn cấu hình theo support matrix.

### 13.1. Không dùng version số nguyên làm toàn bộ quy tắc

Ví dụ:

~~~text
if java.version >= 17:
    use new option
~~~

có thể quá đơn giản nếu cờ khác nhau theo JDK vendor, update build hoặc platform. Khi cần cấu hình động, nên dùng một ma trận đã được kiểm thử cho những tổ hợp thực sự được hỗ trợ.

### 13.2. Kiểm chứng trên artifact và container thật

`java -version` trên máy host không đồng nghĩa `java` bên trong container là bản đó. Khi điều tra, chạy ngay trong môi trường tương đương production và kiểm tra image digest, JDK home, startup script và process command line.

## 14. Tách lỗi JVM option khỏi lỗi ứng dụng

Một startup failure sau nâng JDK không nhất thiết do code Java. Có thể dùng cây quyết định:

~~~text
JVM process không khởi động
       |
       v
Có thông báo "Unrecognized VM option"?
       |
  +----+----+
  |         |
 Có        Không
  |         |
  v         v
Kiểm tra  Có lỗi mở file log, heap, agent,
cờ,      module, class file, JNI hoặc GC init?
JDK/vdr       |
  |           v
  |        Đọc stderr và hs_err logs
  v
Đối chiếu flag với docs JDK đích
  |
  +--> Deprecated: còn tác dụng, cần test khi bỏ
  |
  +--> Obsolete: bị bỏ qua, xóa/thay đúng cơ chế
  |
  +--> Removed: phải loại bỏ/đổi option
  |
  +--> Typo/locked/invalid: sửa cú pháp hoặc cấu hình
  |
  v
Khởi động lại smoke test rồi chạy workload
~~~

Nếu JVM khởi động nhưng performance regression, hãy xem GC log, heap, JIT, container limits và effective flags. Không dùng một lỗi API ứng dụng như `NoSuchMethodError` để kết luận flag tuning nào đó vô dụng nếu chưa có bằng chứng.

### 14.1. Lỗi ngay trước `main()`

Một flag bị xóa hoặc sai cú pháp thường được xử lý trước khi Java main chạy. Trong container orchestrator, hậu quả có thể là CrashLoopBackOff, startup probe fail hoặc service không có log ứng dụng.

Những dấu hiệu nên tìm ở stderr/container logs:

~~~text
Unrecognized VM option ...
Improperly specified VM option ...
Could not create the Java Virtual Machine
Ignoring option ...
Option ... was deprecated ...
~~~

Một warning `Ignoring option` có thể là **nguyên nhân của khác biệt hành vi** mà không phải nguyên nhân crash. Phân biệt severity và tác động thực tế.

### 14.2. Lỗi chỉ khi agent được bật

Nếu một startup script có `-javaagent`, `-agentpath` và các `-XX` tuning flags, một crash có thể do agent không hỗ trợ JDK mới. Không nên xóa bừa mọi flag; cần phân lập theo thành phần trong môi trường test: không agent, chỉ một agent, các agent kết hợp, rồi so sánh logs và JNI/native crash reports.

## 15. Migration plan theo nhiều giai đoạn

### Giai đoạn A – Discovery

1. Thu thập JVM version/vendor/build và danh sách flags từ mọi process.
2. Tìm startup scripts, environment injection, Dockerfile, Helm/Kubernetes config, argument files.
3. Xác định owner của từng flag và mục tiêu tuning ban đầu.
4. Đánh dấu cờ liên quan GC, memory, locking, logging, JIT, diagnostics, modules và agent.

Kết quả mong muốn là một bảng inventory có nguồn, phiên bản đích và hành động dự kiến.

### Giai đoạn B – Phân loại

1. Đọc JDK release notes, migration guide và `java` command docs ở version mục tiêu.
2. Gắn nhãn active/deprecated/obsolete/removed/unknown.
3. Phân biệt flag JVM với system property hoặc tham số ứng dụng.
4. Xác định cờ có cần tồn tại không.
5. Xác định cách đo ảnh hưởng nếu bỏ/đổi cờ.

Đừng coi một tài liệu của JDK 17 là nguồn chính xác cho toàn bộ cờ của JDK 27.

### Giai đoạn C – Cleanup và thay thế

Ví dụ:

~~~text
-XX:MaxPermSize -> bỏ; đánh giá Metaspace nếu có yêu cầu
CMS options -> bỏ; thiết kế GC policy phù hợp JDK mới
TraceClassLoading -> Unified Logging class+load
PrintGC* legacy options -> Unified Logging gc*
--illegal-access -> bỏ; sửa truy cập module hoặc mở chính xác nếu cần
Option bị removed -> xóa/đổi trước khi deploy
~~~

Đối với một flag deprecated còn tác dụng, nên benchmark việc bỏ hoặc thay; đừng thay đổi quá nhiều cờ cùng lúc nếu cần tìm nguyên nhân regression.

### Giai đoạn D – Smoke test trên JDK đích

- Xác minh parse flags bằng `java -version` trong môi trường tương ứng.
- Khởi động ứng dụng với full startup command.
- Kiểm tra warnings, stderr và exit code.
- Dùng `jcmd VM.command_line`/`VM.flags` khi có quyền.
- Kiểm tra logging path, heap cap và GC thực sự được chọn.

### Giai đoạn E – So sánh performance

Dùng cùng workload và ngân sách tài nguyên. Lưu baseline trên JDK cũ, rồi so sánh JDK mới với cấu hình đã được dọn. Với thay đổi GC, cần theo dõi pause/throughput/heap cùng lúc; với thay đổi JIT/locking, cần xem CPU, p99 latency và warmup.

### Giai đoạn F – Canary và rollback

Triển khai nhóm nhỏ có đủ observability. Trước khi rollback, đảm bảo binary cũ vẫn chạy trên hạ tầng và dữ liệu do bản mới tạo ra còn được đọc/ghi an toàn. **Rollback JDK không tự đảo dữ liệu hoặc protocol đã được phiên bản mới ghi.**

Nếu một option đã bị loại bỏ ở JDK mới, đừng tự động khôi phục cờ đó bằng `IgnoreUnrecognizedVMOptions` rồi gọi việc đó là remediation. Cần loại bỏ giả định tuning đã lỗi thời và kiểm chứng kết quả.

## 16. Ví dụ thực tế: một script Java 8 chạy trên JDK mới

Giả sử startup script cũ:

~~~bash
java \
  -Xms2g \
  -Xmx2g \
  -XX:MaxPermSize=256m \
  -XX:+UseConcMarkSweepGC \
  -XX:CMSInitiatingOccupancyFraction=70 \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -Xloggc:/var/log/orders/gc.log \
  -jar orders.jar
~~~

### 16.1. Điều gì có thể xảy ra?

- `MaxPermSize` không còn điều khiển PermGen vì PermGen đã biến mất.
- CMS đã bị loại, các options CMS không còn thiết kế collector hiện hành.
- Cờ GC logging cũ có thể deprecated/obsolete hoặc không được nhận tùy JDK.
- Nếu một flag hết vòng đời, JVM có thể không khởi động.
- Nếu JVM bỏ qua một số cờ mà vẫn chạy, GC thực tế và log output có thể khác mục tiêu cũ.

### 16.2. Bản chuyển đổi ban đầu

Với workload thích hợp cho G1 và chỉ nhằm minh họa migration:

~~~bash
java \
  -Xms2g \
  -Xmx2g \
  -XX:+UseG1GC \
  -Xlog:gc*,safepoint=info:file=/var/log/orders/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar orders.jar
~~~

Đây không phải cấu hình tối ưu cuối cùng. Cần đo mức nhớ, GC pause, CPU và log volume; nếu cgroup limit thấp, giữ heap 2g có thể gây OOM vì native overhead.

### 16.3. Những gì phải xác minh

| Kiểm tra | Mục đích |
|---|---|
| `java -version` và image digest | Đúng runtime triển khai |
| `-XX:+PrintFlagsFinal` | Heap/GC flags báo cáo đúng |
| `jcmd VM.flags` khi process chạy | Kiểm tra flags trong runtime |
| GC log mới | Có event và rotation đúng |
| Throughput/latency | Không tạo regression không chấp nhận |
| Heap/Metaspace/RSS | Không vượt budget container |
| Startup warnings | Không còn obsolete/unknown flags |
| Canary rollback plan | Có thể phục hồi an toàn nếu lỗi |

Thay cờ chỉ là bước cấu hình; xác minh vận hành mới là kết quả migration.

## 17. Những hiểu nhầm thường gặp

**“Flag vẫn được Java nhận nên chắc chắn vẫn có tác dụng.”** Sai. Obsolete flags có thể được nhận nhưng bỏ qua với warning.

**“Deprecated nghĩa là JVM đã bỏ qua.”** Sai. Trong vòng đời HotSpot, deprecated thường vẫn được áp dụng nhưng cảnh báo.

**“Một flag obsolete sẽ luôn được nhận ở mọi JDK tương lai.”** Sai. Nó có thể trở thành expired/removed và khiến JVM từ chối khởi động.

**“`-XX:+IgnoreUnrecognizedVMOptions` giúp migration an toàn.”** Không. Nó có thể che lỗi tên cờ và làm mất bằng chứng về cấu hình không còn tác dụng.

**“`MaxPermSize` và `MaxMetaspaceSize` chỉ là hai tên của cùng một cấu hình.”** Không. PermGen và Metaspace có cơ chế quản lý khác nhau.

**“CMS flags có thể giữ nguyên khi chuyển sang G1.”** Không. G1 có thiết kế/tuning knobs riêng; cần đo lại workload.

**“GC logging mới chỉ cần đổi `-Xloggc` thành `-Xlog`.”** Chưa đủ. Cần xét tags, levels, decorators, file rotation và công cụ phân tích log.

**“`--illegal-access=permit` vẫn mở JDK internals trên Java 17 trở lên.”** Ở JDK 17 nó đã obsolete, không còn tạo khả năng relaxed strong encapsulation như trước.

**“`mvn test` chạy được là mọi process Java cùng dùng một JDK.”** Không. Maven launcher, test JVM, app/container JVM và script có thể khác nhau và nhận flags khác nhau.

**“PrintFlagsFinal chứng minh performance đã tối ưu.”** Không. Nó hiển thị cấu hình được báo cáo, không phải kết quả benchmark.

**“Không có warning nghĩa là cấu hình hoàn toàn đúng.”** Không. Có thể một flag hợp lệ nhưng không có hiệu lực trong collector/mode đang chọn, hoặc ứng dụng vẫn bị regression vì default JDK đổi.

**“JDK mới luôn tốt hơn với bộ tuning cũ.”** Không. Cờ tuning tối ưu cho một workload/JDK/GC trước đó có thể không thích hợp sau nâng cấp.

**“Chỉ cần xem Dockerfile là đủ.”** Không. Helm values, `JAVA_TOOL_OPTIONS`, service manager, `@args-file` và các công cụ inject agent có thể thêm flags runtime.

## 18. Checklist cho JVM flags migration

- [ ] Đã xác định feature/update/build, vendor và JVM implementation ở nguồn/đích.
- [ ] Đã thu thập startup flags từ command line, environment, scripts, container và argument files.
- [ ] Đã phân biệt `-X`, `-XX`, `-D`, module options, agents và tham số ứng dụng.
- [ ] Đã phân loại flag active/deprecated/obsolete/removed/unknown theo đúng JDK đích.
- [ ] Đã xác định cờ nào bị bỏ qua dù JVM vẫn khởi động.
- [ ] Đã loại bỏ PermGen options không còn tác dụng.
- [ ] Đã thay thế hoặc loại bỏ các CMS/biased locking flags không được hỗ trợ.
- [ ] Đã chuyển GC/class tracing cần thiết sang Unified Logging.
- [ ] Đã kiểm tra JPMS `--illegal-access` và chính sách Security Manager nếu có.
- [ ] Đã xem xét `IgnoreUnrecognizedVMOptions` và loại bỏ việc che lỗi không cần thiết.
- [ ] Đã xác minh `java -version` và `jcmd VM.command_line` trên process thực tế.
- [ ] Đã kiểm tra `PrintFlagsFinal`/`VM.flags` và hiểu giới hạn của chúng.
- [ ] Đã kiểm tra heap sizing, Metaspace và container memory/CPU limits.
- [ ] Đã bảo đảm GC log có đủ dữ liệu và log parser/dashboard đọc được.
- [ ] Đã chạy smoke test và ghi cả stderr, warning, exit code.
- [ ] Đã đo throughput, CPU, allocation, GC, native memory và p95/p99 trên workload đại diện.
- [ ] Đã thử canary với startup command và image giống production.
- [ ] Đã xác định chủ sở hữu, lý do và kế hoạch loại bỏ các cờ tuning tùy chỉnh.
- [ ] Đã lập kế hoạch rollback không dựa vào khả năng đọc/ghi dữ liệu cũ chưa được kiểm chứng.

## 19. Nguồn tài liệu nên tham khảo

Những tài liệu sau giải thích vòng đời options và những thay đổi được sử dụng làm ví dụ:

- [Oracle JDK 27 – The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): các nhóm standard/extra/advanced options, các mục Deprecated/Obsolete/Removed và Unified Logging.
- [Oracle JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): nâng từ JDK 8 và các thay đổi PermGen/CMS/GC flags.
- [Oracle JDK 25 – The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): ví dụ nhóm RTM options bị loại và các option hiện hành ở JDK 25.
- [JEP 122 – Remove the Permanent Generation](https://openjdk.org/jeps/122): thay PermGen bằng Metaspace.
- [JEP 158 – Unified JVM Logging](https://openjdk.org/jeps/158): mô hình `-Xlog`.
- [JEP 363 – Remove the Concurrent Mark Sweep Garbage Collector](https://openjdk.org/jeps/363): loại bỏ CMS từ JDK 14.
- [JEP 374 – Disable and Deprecate Biased Locking](https://openjdk.org/jeps/374): thay đổi biased locking từ JDK 15.
- [JDK 18 Release Notes](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html): trạng thái obsolete của các biased-locking flags.
- [JEP 403 – Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): hành vi của `--illegal-access` trên JDK 17.
- [JEP 486 – Permanently Disable the Security Manager](https://openjdk.org/jeps/486): chính sách Security Manager ở JDK 24.
- [Oracle `jcmd` command reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): chẩn đoán process, VM flags và command line.

Đối với từng flag trong cấu hình của một dự án, tra cứu tài liệu **đúng bản JDK đang triển khai**, vendor-specific release notes và thử trên runtime thật. Danh sách ví dụ trong bài không phải catalog bất biến cho mọi phiên bản Java.

## 20. Kết luận

Các cờ JVM không có hợp đồng ổn định giống nhau. Một cờ **deprecated** có thể vẫn áp dụng nhưng cảnh báo; cờ **obsolete** có thể được chấp nhận song **bị bỏ qua**; cờ **expired/removed** có thể làm JVM không khởi động. Ngoài ra, cờ hợp lệ vẫn có thể không tạo tác động trong mode/collector hiện tại hoặc bị thay đổi về giá trị mặc định.

Để nâng JDK an toàn, hãy kiểm kê mọi nguồn JVM arguments, xác định vòng đời của từng cờ theo runtime đích, loại bỏ những điều chỉnh đã lỗi thời và chuyển các cơ chế tương ứng như CMS/PermGen/GC logging sang phương án đang được hỗ trợ. Quan trọng hơn, cần **xác minh JVM đang chạy thực sự dùng cấu hình nào** và **đo ảnh hưởng đến ứng dụng** qua GC logs, CPU, memory, throughput và latency trên workload đại diện. Một startup sạch warning là tín hiệu tốt; bằng chứng tương thích hiệu năng và khả năng vận hành mới là mục tiêu cuối cùng.

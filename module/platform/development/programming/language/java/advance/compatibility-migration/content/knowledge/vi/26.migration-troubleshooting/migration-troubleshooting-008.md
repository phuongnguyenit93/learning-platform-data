# Unrecognized VM option và tùy chọn GC đã bị xóa

Khi nâng JDK trong **Java Advance Compatibility Migration**, lỗi đầu tiên đôi khi xuất hiện **trước cả khi ứng dụng chạy**. Một script từng khởi động ổn với JDK 8 có thể bị JDK mới từ chối vì một tham số JVM cũ, chẳng hạn cờ GC đã bị loại bỏ, cờ logging thuộc hệ thống trước Java 9 hoặc một option vendor-specific không tồn tại ở runtime mới.

Thông báo thường gặp:

~~~text
Unrecognized VM option 'SomeOldFlag'
Error: Could not create the Java Virtual Machine.
Error: A fatal exception has occurred. Program will exit.
~~~

Lỗi này thuộc **giai đoạn khởi tạo JVM**. Nó khác lỗi biên dịch Java, lỗi dependency, `OutOfMemoryError` hay exception xuất hiện khi chương trình đang xử lý request. Muốn chẩn đoán đúng, cần tìm **tham số thực sự được truyền tới đúng JVM**, xác định tình trạng của tham số trên **JDK/distribution đích**, rồi loại bỏ hoặc thay thế nó theo chức năng, thay vì đoán một cờ có tên tương tự.

Đặc biệt, **“GC đã bị xóa” và “tên option báo unrecognized” không phải lúc nào xuất hiện cùng nhau**. Ví dụ bộ thu gom CMS bị loại khỏi HotSpot ở JDK 14 theo JEP 363, nhưng một số bản JDK vẫn **nhận cờ cũ và cảnh báo rằng nó bị bỏ qua**. Ngược lại, một số tùy chọn incremental CMS đã bị loại ở JDK 9 khiến JVM không thể khởi động. Vì thế, phải phân biệt đúng các trạng thái `deprecated`, `obsolete`, `removed` và `unrecognized`.

Bài học này cung cấp phương pháp điều tra startup flags, bảng phân loại cờ GC cũ, cách chuyển sang `-Xlog`, ví dụ cấu hình Gradle/Maven/container, kiểm tra collector thực tế và quy trình kiểm thử sau khi sửa.

## 1. Lỗi xảy ra ở giai đoạn nào?

Quá trình khởi động một ứng dụng Java có thể nhìn giản lược như sau:

~~~text
Shell / container / service manager
        |
        v
Java launcher + environment options
        |
        v
Parse and validate JVM options
        |
        +--> INVALID OPTION
        |      "Unrecognized VM option ..."
        |      JVM startup fails
        |
        v
Initialize JVM, heap and collector
        |
        v
Create class loaders / load main class
        |
        v
Run application initialization
        |
        v
Business requests / background jobs
~~~

Khi JVM từ chối option trước lúc tạo máy ảo, sửa classpath hoặc thay một method trong source thường **không giải quyết nguyên nhân**. Cần nhìn vào **startup command**, không phải stack trace của mã nghiệp vụ.

### 1.1. So sánh các triệu chứng khởi động

| Triệu chứng | Nhóm lỗi | Hướng điều tra đầu tiên |
|---|---|---|
| `Unrecognized VM option 'X'` | Cờ không được JVM đích nhận | Tên option, syntax, JDK/version/vendor và nơi inject |
| `Unrecognized option: --something` | Launcher option không hỗ trợ hoặc sai tên | `java --help`, `java --help-extra`, release |
| `Could not create the Java Virtual Machine` | Lỗi khởi tạo chung, có thể do option | Đọc **dòng lỗi trước đó** |
| `Ignoring option ...; support was removed ...` | Cờ được chấp nhận nhưng không còn tác dụng | Bỏ cờ, xác nhận default mới |
| `... is deprecated; will use ... instead` | Cờ cũ còn được ánh xạ tạm thời | Chuyển sang cú pháp chính thức |
| `Multiple garbage collectors selected` hoặc xung đột tương đương | Chọn nhiều GC không hợp lệ | Kiểm toàn bộ flags từ mọi nguồn |
| `Error: A JNI error has occurred` | Có thể là lỗi class loading/main startup | Xem thông báo chi tiết; không mặc định là GC |
| `UnsupportedClassVersionError` | Bytecode yêu cầu runtime mới hơn | JDK runtime và class-file version |
| `OutOfMemoryError: Java heap space` | Bộ nhớ heap lúc runtime | Heap sizing, leak, allocation và GC logs |
| `InaccessibleObjectException` | Deep reflection bị JPMS chặn | `opens`, framework, JDK internals |

**Một lỗi bắt đầu bằng “Could not create the Java Virtual Machine” không nhất thiết do heap không đủ.** Đọc thông báo unrecognized/invalid phía trên trước khi điều chỉnh `-Xmx`.

## 2. Phân loại vòng đời JVM options

Tên cờ có thể trải qua các trạng thái khác nhau giữa các bản HotSpot:

| Trạng thái | Ý nghĩa điển hình | Có thể khởi động? | Việc nên làm |
|---|---|---|---|
| Supported | JVM hiểu và áp dụng theo tài liệu | Thường có, nếu giá trị và các điều kiện hợp lệ | Giữ nếu có lý do và bằng chứng |
| Experimental | Tùy chọn chưa cam kết ổn định, có thể cần unlock | Tùy JVM/flags | Kiểm compatibility, tránh dùng mặc định vô căn cứ |
| Diagnostic | Phục vụ phân tích, đôi khi cần mở khóa | Tùy cấu hình | Chỉ dùng khi có mục tiêu điều tra |
| Deprecated | Còn nhận hoặc hoạt động nhưng có thể cảnh báo | Thường có | Lập kế hoạch thay |
| Obsolete | Cờ còn được nhận nhưng **bị bỏ qua**, thường cảnh báo | Có thể có | Xóa; không kỳ vọng tác dụng |
| Removed | Cờ không còn được nhận trong bản JVM tương ứng | Thường không | Xóa hoặc đổi cách đạt mục tiêu |
| Unrecognized | JVM hiện tại không hiểu tên/cú pháp | Không, nếu không có policy bỏ qua | Kiểm typo, phiên bản, vendor và option source |

Tình trạng không hoàn toàn đồng nhất giữa mọi vendor/distribution/update. Một cờ được liệt kê trong hướng dẫn JDK 14 có thể không được chấp nhận trong bản JDK mới hơn. Vì vậy **phải hỏi runtime cụ thể**, không đoán từ năm phát hành hoặc từ cờ có sẵn trên máy khác.

### 2.1. Obsolete không có nghĩa tính năng còn hoạt động

Một cảnh báo như:

~~~text
OpenJDK 64-Bit Server VM warning:
Ignoring option UseConcMarkSweepGC; support was removed in 14.0
~~~

được đưa ra để minh họa tình huống cờ **không còn hiệu lực**. Ứng dụng có thể tiếp tục chạy với collector khác. Nếu đội ngũ chỉ nhìn `exit code = 0` rồi viết “đang dùng CMS”, kết luận sẽ sai.

Ngược lại, khi một JVM trả `Unrecognized VM option`, nó đã dừng sớm. Không có lý do chờ ứng dụng tự xử lý lỗi này.

## 3. Những nguyên nhân không liên quan đến GC

Dù bài tập trung vào cờ GC, cùng một thông báo có thể đến từ:

- Sai chính tả `-XX:MaxGCPauseMillis=...` hoặc dùng dấu `+` sai chỗ.
- Truyền tùy chọn dành cho JDK mới vào JDK cũ.
- Truyền option của một JVM khác, ví dụ cấu hình HotSpot vào JVM không tương thích.
- Dùng cờ chỉ có trên một OS/architecture hoặc build đặc thù.
- Cờ experimental/diagnostic chưa mở khóa đúng cách.
- Cú pháp `-Xlog` sai tag/level/decorator hoặc chưa được JDK hỗ trợ.
- Tham số cũ tồn tại trong `JAVA_TOOL_OPTIONS` hoặc `_JAVA_OPTIONS` mà người phát triển không thấy.
- IDE, Gradle daemon, Maven, CI hoặc container bổ sung cờ không giống terminal.
- Đưa system property nhầm cú pháp, ví dụ dùng `-XX:` thay cho `-D`.
- Sử dụng một tài liệu JVM cũ cho một bản JDK khác.

Do đó, câu hỏi đầu tiên khi gặp `Unrecognized VM option` luôn là:

> **JVM nào nhận đúng chuỗi option nào, từ nguồn cấu hình nào?**

Chỉ sau đó mới xét cờ đã bị remove, thay đổi định dạng hay lỗi triển khai.

## 4. Xác định phiên bản Java thực sự đang chạy

Trong terminal Unix-like:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
command -v java
~~~

Trên Windows PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
Get-Command java
~~~

Nếu có nhiều JDK, `java` trên `PATH` có thể không phải JDK được thiết lập trong IDE hoặc container. Nên dùng **đường dẫn tuyệt đối đến Java executable** khi tạo reproduction để tránh sự thay đổi không nhìn thấy:

~~~bash
/opt/jdk-21/bin/java -version
/opt/jdk-25/bin/java -version
~~~

Các đường dẫn trên là ví dụ. Chúng không chứng minh một JDK đã tồn tại trên máy hiện tại.

### 4.1. Java runtime khác compiler, daemon và test worker

Một ứng dụng Gradle có thể sử dụng:

- JDK chạy Gradle daemon.
- JDK do Java toolchain chọn để biên dịch.
- JDK được task `Test` chọn.
- JDK chạy ứng dụng trong production.

Maven cũng có JVM chạy Maven core và những JVM fork riêng cho test/plugin. Vì thế, chạy `java -version` ngoài terminal là **tín hiệu hữu ích nhưng không đủ**. Lỗi option phải được gắn với đúng process.

## 5. Kiểm cú pháp, ý nghĩa và support của từng option

Các nhóm tham số thường gặp:

| Dạng | Ví dụ | Ghi chú |
|---|---|---|
| Standard launcher | `--class-path`, `--module-path` | Theo tài liệu Java launcher |
| Nonstandard `-X` | `-Xms512m`, `-Xmx2g`, `-Xlog:gc` | Không phải mọi version đều hỗ trợ cùng tập |
| HotSpot `-XX` | `-XX:+UseG1GC`, `-XX:MaxGCPauseMillis=200` | Có flag boolean và flag có giá trị |
| System property | `-Dfile.encoding=UTF-8` | Không phải cờ GC |
| Java agent | `-javaagent:agent.jar` | Thuộc cơ chế agent |
| Module access | `--add-opens=...` | Giải quyết vấn đề opens/reflection |
| Native access | `--enable-native-access=...` | Tính khả dụng/phạm vi phụ thuộc JDK |

Một cờ boolean thường dùng `-XX:+FlagName` hoặc `-XX:-FlagName`. Một cờ số dùng `-XX:FlagName=value`. Nhưng không được suy ra mọi tên flag có cả hai dạng hoặc mọi giá trị đều hợp lệ.

### 5.1. Công cụ tự mô tả của JVM

Trên các HotSpot JDK tương ứng:

~~~bash
java --help
java --help-extra
java -Xlog:help
java -XX:+PrintFlagsFinal -version
~~~

- `--help` và `--help-extra` giới thiệu launcher options.
- `-Xlog:help` mô tả tag/level/decorator trên Java 9+.
- `-XX:+PrintFlagsFinal -version` in các JVM flags hiệu lực/có sẵn theo runtime cụ thể.

Output của `PrintFlagsFinal` rất dài; cần lọc theo mục tiêu chẩn đoán. Trên JDK trước Java 9, `-Xlog:help` không phải công cụ áp dụng được.

### 5.2. Thử một option tối thiểu

Để xác minh JVM **chấp nhận cú pháp** mà không cần chạy application:

~~~bash
java -XX:+UseG1GC -version
~~~

Nếu lệnh này chạy, mới chứng minh JVM chấp nhận cờ khi khởi tạo, chưa chứng minh collector phù hợp workload. Để đánh giá hành vi, chạy ứng dụng/test với GC logging và quan sát dưới tải.

Một thử nghiệm riêng cho cấu hình logging trên JDK 9+:

~~~bash
java -Xlog:gc -version
~~~

Không nên ghép ngay toàn bộ 30 cờ để xác minh một option: tìm từng nguồn lỗi sẽ khó hơn.

## 6. Mốc JDK quan trọng với GC flags

| Mốc | Thay đổi | Cách hiểu đúng |
|---|---|---|
| JDK 8 | PermGen đã bị thay bằng Metaspace (JEP 122) | `PermSize` và `MaxPermSize` không còn giới hạn PermGen |
| JDK 9 | G1 trở thành GC mặc định HotSpot trong cấu hình phổ biến (JEP 248) | Nếu không chỉ định GC, collector có thể khác JDK 8 |
| JDK 9 | Unified JVM Logging và unified GC logging (JEP 158/271) | Chuyển cờ GC logging cũ sang `-Xlog` |
| JDK 9 | Một số kết hợp GC và Incremental CMS không còn được hỗ trợ (JEP 214) | Một số launch configurations cũ bị từ chối |
| JDK 14 | CMS collector bị loại bỏ (JEP 363) | Cờ CMS cũ có thể thành obsolete và bị bỏ qua trước khi được loại khỏi flag parser |
| JDK 15 | ZGC trở thành production feature (JEP 377) | Có thêm lựa chọn GC, không tự là default |
| JDK 21 | Generational ZGC được giới thiệu (JEP 439) | Chế độ và flags cần kiểm theo release |
| JDK 23 | Generational ZGC trở thành chế độ mặc định khi chọn ZGC (JEP 474) | Cấu hình ZGC cũ có thể thay ý nghĩa |
| JDK 24 | Non-generational ZGC bị loại bỏ (JEP 490) | `ZGenerational` không còn là lựa chọn mode cần giữ |

Đây là các mốc HotSpot/OpenJDK, không khẳng định mọi nhà phân phối hoặc platform có đầy đủ cùng bộ collectors. Chỉ kết luận sau khi xác định **runtime JDK thực tế** và startup arguments.

## 7. CMS đã bị loại bỏ: lỗi thường gặp nhất

CMS (Concurrent Mark Sweep) là collector từng được dùng cho workload nhạy pause ở nhiều triển khai Java 8. Một lệnh cũ:

~~~bash
java \
  -XX:+UseConcMarkSweepGC \
  -XX:+CMSParallelRemarkEnabled \
  -XX:+UseParNewGC \
  -jar service.jar
~~~

Cấu hình này không nên được mang nguyên sang JDK hiện đại.

### 7.1. CMS removal ở JDK 14

JEP 363 loại bỏ implementation CMS trong JDK 14. Một số cờ liên quan CMS được đưa vào trạng thái **obsolete**, có thể bị bỏ qua kèm cảnh báo; các cờ khác đã bị loại ở những mốc sớm hơn hoặc bị xóa sau đó.

Điều đó dẫn đến hai tình huống khác nhau:

~~~text
Case A:
  JVM accepts an obsolete flag, prints warning,
  ignores the flag and may start with another collector.

Case B:
  JVM no longer recognizes a removed flag,
  prints "Unrecognized VM option" and exits.
~~~

**Không được suy rằng JDK 14 luôn báo đúng một chuỗi unrecognized cho `UseConcMarkSweepGC`.** Cách phản ứng tùy cờ và release.

### 7.2. Thay CMS bằng gì?

Không có một cờ “CMS mới” giữ nguyên semantics và tuning knobs.

Các hướng có thể xem xét:

- Thử **G1** theo default/`-XX:+UseG1GC` nếu phù hợp workload.
- Nếu yêu cầu tail latency nghiêm ngặt, đánh giá ZGC hoặc collector khác **có trong runtime được hỗ trợ**.
- Với batch throughput-oriented workload, đánh giá Parallel GC.
- Xóa CMS-specific flags không còn tác dụng.
- Đặt lại mục tiêu heap/GC pause bằng benchmark trên ứng dụng thực tế.

Ví dụ thử G1 trên JDK phù hợp:

~~~bash
java \
  -XX:+UseG1GC \
  -Xms512m -Xmx2g \
  "-Xlog:gc*:file=gc.log:time,uptime,level,tags" \
  -jar service.jar
~~~

Đây là cú pháp minh họa, không phải khuyến nghị hiệu năng phổ quát. Việc chọn collector nên dựa trên p95/p99 latency, throughput, CPU/GC overhead và peak RSS.

### 7.3. Không chuyển CMS knob sang G1 bằng cách đổi tên

CMS và G1 có kiến trúc và chính sách quản lý heap khác nhau. Những cờ về CMS remark, initiating occupancy hoặc fragmentation không có tương ứng một-một với G1.

Giữ `CMSInitiatingOccupancyFraction` chỉ vì “trước đây chạy tốt” có thể vô nghĩa khi CMS đã biến mất. Nếu cần tuning G1, bắt đầu từ defaults và các option **được JDK đích hỗ trợ**, rồi đo thực tế. Đừng tạo một danh sách tuning tương tự về tên mà chưa biết tác dụng.

## 8. Các kết hợp GC đã bị loại từ JDK 9

JEP 214 loại bỏ những tổ hợp GC cũ đã được đánh dấu deprecated trước đó. Các tài liệu migration nêu những trường hợp như:

- `DefNew + CMS`.
- `ParNew + SerialOld`.
- Incremental CMS.
- Một số CMS foreground/compaction options.

Ví dụ cờ Incremental CMS cũ:

~~~bash
java -Xincgc -jar service.jar
~~~

Hoặc:

~~~bash
java -XX:+CMSIncrementalMode -jar service.jar
~~~

Những cấu hình này không nên được dùng trên Java 9+. Tùy runtime, chúng có thể bị từ chối ngay khi khởi động. Hướng sửa là **loại cờ cấu hình collector đã không còn**, sau đó chọn một collector được hỗ trợ và kiểm lại hiệu năng.

Một vài cờ điển hình bị loại trong quá trình xử lý các GC combination cũ gồm:

~~~text
-Xincgc
-XX:+CMSIncrementalMode
-XX:+UseCMSCompactAtFullCollection
-XX:CMSFullGCsBeforeCompaction=...
-XX:+UseCMSCollectionPassing
~~~

Danh sách không đầy đủ và mỗi cờ có thể có trạng thái parser khác nhau theo JDK. Không tìm một cờ tương tự trên G1 chỉ bằng suy đoán tên.

## 9. PermGen flags sau Java 8

Hai option lịch sử:

~~~text
-XX:PermSize=...
-XX:MaxPermSize=...
~~~

liên quan **Permanent Generation** trong các HotSpot JDK cũ. PermGen đã bị loại ở Java 8 (JEP 122), thay bằng cơ chế Metaspace.

Một thông báo quen thuộc trên runtime tương ứng:

~~~text
Java HotSpot(TM) 64-Bit Server VM warning:
Ignoring option MaxPermSize; support was removed in 8.0
~~~

Đây **không nhất thiết là lỗi startup**. Nhưng cờ đã bị bỏ qua, nên không nên giữ nó như một phần “tuning hợp lệ”.

### 9.1. Không thay thế cơ học PermGen bằng Metaspace

Có các cờ như:

~~~text
-XX:MetaspaceSize=...
-XX:MaxMetaspaceSize=...
~~~

Nhưng ý nghĩa không tương đương hoàn toàn với PermGen. Metaspace chủ yếu lưu class metadata ngoài Java heap; `MetaspaceSize` ảnh hưởng ngưỡng/chính sách GC theo metadata, còn `MaxMetaspaceSize` giới hạn metaspace.

Không lấy `MaxPermSize=256m` cũ rồi đặt `MaxMetaspaceSize=256m` chỉ để giữ nguyên con số. Trước tiên đo class loading và metadata under workload; giới hạn quá thấp có thể gây `OutOfMemoryError: Metaspace`.

## 10. Chuyển GC logging cũ sang Unified Logging

Từ Java 9, HotSpot sử dụng Unified JVM Logging. Những flag Java 8 như:

~~~bash
java \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -XX:+PrintGCTimeStamps \
  -Xloggc:/var/log/app/gc.log \
  -jar service.jar
~~~

phải được **rà soát và chuyển đổi**. Một số cờ còn được ánh xạ với cảnh báo ở JDK mới, một số đã bị xóa, vì vậy không nên dựa vào compatibility alias.

### 10.1. Bảng mapping tham khảo

| Cờ logging cũ | Ý định | Cách làm trên JDK 9+ |
|---|---|---|
| `-XX:+PrintGC` | GC events cơ bản | `-Xlog:gc` |
| `-XX:+PrintGCDetails` | GC details | `-Xlog:gc*` |
| `-XX:+PrintGCDateStamps` | Timestamp theo đồng hồ | Decorator `time` |
| `-XX:+PrintGCTimeStamps` | Uptime timestamp | Decorator `uptime` |
| `-Xloggc:file` | Ghi GC log ra file | `-Xlog:gc:file=...` hoặc `gc*` |
| `-XX:+PrintHeapAtGC` | Heap thông tin mỗi GC | `-Xlog:gc+heap=trace` |
| `-XX:+PrintTenuringDistribution` | Phân bố tuổi object | `-Xlog:gc+age*=debug` hoặc trace phù hợp |
| `-XX:+PrintReferenceGC` | Reference processing | `-Xlog:gc+ref*=debug` |
| `-XX:+PrintGCApplicationStoppedTime` | Thời gian ứng dụng dừng | `-Xlog:safepoint` |
| `-XX:NumberOfGCLogFiles=...` | Số file log xoay vòng | File output option `filecount=...` |
| `-XX:GCLogFileSize=...` | Dung lượng mỗi file | File output option `filesize=...` |
| `-XX:+UseGCLogFileRotation` | Bật rotation | Đặt rotation trong `-Xlog` output options |

Bảng nhằm chuyển **mục tiêu logging**, không khẳng định nội dung log hai JDK có thể so byte-to-byte. Unified Logging thay đổi format, tag, timestamp và mức chi tiết.

### 10.2. Một cấu hình hiện đại thực dụng

~~~bash
java \
  "-Xlog:gc*,safepoint:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=20m" \
  -jar service.jar
~~~

Cấu hình trên:

- Chọn các log với tag GC và safepoint tương ứng ở level mặc định.
- Ghi vào file.
- Thêm các decorators thời gian/uptime/level/tags.
- Giới hạn số file và dung lượng log theo framework hỗ trợ.

Cần xác minh quyền ghi thư mục và storage capacity. Logging quá chi tiết có thể tạo lượng dữ liệu lớn; không mặc định dùng trace trên production dài hạn.

### 10.3. Xem cú pháp chính xác trên JDK đích

~~~bash
java -Xlog:help
~~~

Nếu truyền tag không tồn tại, JVM có thể báo lỗi về logging configuration. Đó không đồng nghĩa GC bị loại. Thay tag/level/decorator cho đúng tài liệu version.

### 10.4. Đừng giữ hai hệ logging cùng lúc

Kết hợp cả `-XX:+PrintGCDetails` và `-Xlog:gc*` có thể gây warning hoặc cấu hình lặp/ghi đè tùy runtime. Nên chọn một cấu hình thống nhất theo JDK đích, lưu vào nguồn build/deployment có thẩm quyền, kiểm file log được ghi và parser dashboard hiểu format mới.

## 11. ZGC: tùy chọn mode đổi qua JDK 21–24

ZGC là ví dụ cho thấy một collector còn tồn tại nhưng **cờ chọn mode** có thể thay đổi.

Các mốc:

1. **JDK 21:** Generational ZGC được giới thiệu (JEP 439).
2. **JDK 23:** Generational ZGC trở thành mode mặc định **khi ZGC được chọn** (JEP 474).
3. **JDK 24:** Non-generational ZGC bị loại bỏ (JEP 490); không còn nhu cầu duy trì cờ chọn mode `ZGenerational`.

Một command cũ có thể chứa:

~~~bash
java -XX:+UseZGC -XX:-ZGenerational -jar service.jar
~~~

Khi nâng lên JDK 24+, **không giữ option yêu cầu non-generational mode**. Nếu chọn ZGC, có thể bắt đầu từ:

~~~bash
java -XX:+UseZGC -jar service.jar
~~~

Nhưng đây không phải lời khuyên chọn ZGC cho mọi ứng dụng. Heap headroom, CPU và workload có thể khiến G1/Parallel GC phù hợp hơn. Nếu chương trình gặp lỗi `ZGenerational`, cần xem release docs để phân biệt flag đã bị loại, obsolete hay không được hỗ trợ trong build hiện tại.

### 11.1. Default của ZGC khác default của toàn JVM

“Generational ZGC là mặc định” nghĩa là **khi chạy ZGC**, chế độ generational được sử dụng ở những JDK đã chuyển default. Nó **không đồng nghĩa ZGC trở thành collector mặc định cho mọi ứng dụng Java**. Trên nhiều HotSpot server configurations, G1 vẫn là default collector khi không chọn GC khác.

## 12. Không chọn collector bằng một bộ cờ mâu thuẫn

Một tình huống hay gặp khi nhiều tầng cấu hình ghép JVM arguments:

~~~text
JAVA_TOOL_OPTIONS:
  -XX:+UseG1GC

Container entrypoint:
  -XX:+UseParallelGC

Gradle/Maven or app script:
  -XX:+UseZGC
~~~

Nếu JVM từ chối các lựa chọn không thể dùng đồng thời, đó là vấn đề **GC selection conflict**, không phải nhất thiết collector đã bị xóa.

Quy trình:

1. Thu thập toàn bộ launcher arguments từ script, environment và process manager.
2. Xác định chính xác một collector muốn sử dụng hoặc để JVM chọn mặc định.
3. Loại những cờ GC selector trùng/mâu thuẫn.
4. Xóa CMS-only options còn sót.
5. Khởi động và kiểm GC thật sự.
6. Chạy benchmark trước khi phát hành.

**Không dùng quy tắc “cờ cuối thắng” cho mọi JVM flags.** Một số cờ có thể override, nhưng những cờ xung đột có thể làm JVM từ chối khởi động; cơ chế phụ thuộc flag/runtime.

## 13. Tìm cờ cũ được truyền từ đâu

Đây thường là công đoạn mất nhiều thời gian nhất. Một startup option có thể xuất hiện ở:

- Shell script `start.sh`, `startup.bat`.
- Unit file của systemd và drop-in overrides.
- Dockerfile `ENTRYPOINT`, `CMD`.
- Kubernetes Deployment/Helm values, ConfigMap và environment.
- `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `_JAVA_OPTIONS` khi JVM tương ứng hỗ trợ.
- Gradle `org.gradle.jvmargs`, `Test.jvmArgs`, `JavaExec.jvmArgs`.
- Maven `MAVEN_OPTS`, `.mvn/jvm.config`, Surefire/Failsafe `argLine`.
- IDE run/debug configurations.
- Application server startup scripts hoặc container entrypoint.
- Cron/job scheduler, init scripts, agent/profiler bootstrap.
- JDK argument file `@options.txt`.
- Platform-injected defaults và launcher wrapper của tổ chức.

### 13.1. Kiểm nguồn environment

Unix-like shell:

~~~bash
printf '%s\n' "$JAVA_TOOL_OPTIONS"
printf '%s\n' "$JDK_JAVA_OPTIONS"
printf '%s\n' "$_JAVA_OPTIONS"
~~~

PowerShell:

~~~powershell
$env:JAVA_TOOL_OPTIONS
$env:JDK_JAVA_OPTIONS
$env:_JAVA_OPTIONS
~~~

**Lưu ý bảo mật:** environment và startup args có thể chứa endpoint, token hoặc secret. Không paste toàn bộ vào ticket hoặc public logs; chỉ trích các flag liên quan và che giá trị nhạy cảm.

Không phải mọi JDK/runtime/launcher xử lý ba biến theo cách giống nhau. Đặc biệt `JDK_JAVA_OPTIONS` là cơ chế Java launcher được đưa vào ở thế hệ JDK mới; đừng kỳ vọng nó hoạt động trên mọi JDK 8.

### 13.2. Tìm trong repository

Ví dụ với ripgrep:

~~~bash
rg -n 'UseConcMarkSweepGC|CMS|PrintGC|Xloggc|PermSize|ZGenerational' .
~~~

Với một repository thực tế có nhiều loại cấu hình, nên tìm cả `-XX:`, `-Xlog`, `JAVA_TOOL_OPTIONS` và `org.gradle.jvmargs`. Một số cờ chỉ nằm trong CI secrets/config bên ngoài repo, nên search source chưa đủ.

### 13.3. Khi process đã khởi động

HotSpot cung cấp một số lệnh:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.version
~~~

Đổi `<pid>` thành PID thật. Những lệnh này chỉ dùng được khi JVM đã chạy và tool có quyền attach. **Nếu process chưa khởi động được vì unrecognized flag thì không có process để jcmd**; khi đó cần xem launcher, service manager, script và stderr trước.

## 14. Gradle: daemon có lỗi khác test worker

Một lỗi có thể xuất hiện khi Gradle daemon không khởi động hoặc khi task `Test` fork JVM. Hai trường hợp cần cấu hình khác nhau.

### 14.1. Gradle daemon

Ví dụ `gradle.properties` cũ:

~~~properties
org.gradle.jvmargs=-Xmx2g -XX:+UseConcMarkSweepGC
~~~

Khi Gradle daemon chạy trên JDK không hỗ trợ CMS, cờ này có thể bị bỏ qua kèm warning hoặc gây lỗi theo release. Cần kiểm JVM của daemon và gỡ option lỗi từ nguồn khai báo.

Nếu không cần lựa chọn GC cụ thể, có thể giữ mức tối thiểu:

~~~properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
~~~

`-Xmx2g` chỉ là ví dụ; chọn theo memory budget cho daemon/build workload, không coi đây là giá trị tối ưu mặc định.

### 14.2. Gradle Test JVM

Test forks có thể dùng JVM và cờ khác daemon. Ví dụ trong `build.gradle.kts`:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs(
        "-XX:+UseG1GC",
        "-Xlog:gc"
    )
}
~~~

Đây là lựa chọn cho **JDK 9+** nếu test launcher hỗ trợ. Nếu project còn chạy tests trên Java 8, không dùng `-Xlog:gc` cho Java 8; cần cấu hình theo test runtime hoặc tách job.

Không áp dụng flags GC tùy tiện cho mọi task nếu một số task chạy trên JDK khác. Và cấu hình `Test.jvmArgs` không thay JVM flags của Gradle daemon.

### 14.3. Gradle JavaExec/application plugin

Một task chạy app:

~~~kotlin
tasks.named<JavaExec>("run") {
    jvmArgs("-XX:+UseG1GC", "-Xlog:gc")
}
~~~

Code này giả định project thực sự có task `run` (ví dụ từ Application plugin). Trong dự án thật, tên task và plugin phải được xác nhận. Các startup scripts mà Application plugin tạo có thể có cấu hình JVM riêng; cần kiểm artifact triển khai chứ không chỉ `gradlew run`.

### 14.4. Đừng chữa lỗi daemon bằng test arguments

Nếu message nằm ở log “Unable to start the daemon process” hoặc JVM command line của Gradle daemon, sửa `tasks.test.jvmArgs` sẽ không giúp daemon khởi động. Ngược lại, thay `org.gradle.jvmargs` chưa chắc ảnh hưởng child JVM của test.

Phải phân loại theo **JVM process thực sự bị lỗi** trước khi sửa.

## 15. Maven: MAVEN_OPTS khác Surefire/Failsafe argLine

Maven cũng có nhiều tầng JVM:

- Maven runtime nhận một số arguments từ `MAVEN_OPTS` hoặc `.mvn/jvm.config` theo cấu hình.
- Compiler plugin sử dụng compiler trong runtime hoặc toolchain đã chọn.
- Surefire/Failsafe có thể tạo JVM fork để thực thi test.
- Application plugin/custom launchers có thể tạo process độc lập.

Ví dụ cờ cũ trong `.mvn/jvm.config`:

~~~text
-Xmx2g
-XX:+UseConcMarkSweepGC
~~~

Nếu JDK chạy Maven không còn hỗ trợ CMS, cần sửa file này theo compatibility policy. Không chỉ sửa POM dependency.

### 15.1. Surefire argLine

Ví dụ POM dành cho test trên JDK hỗ trợ `-Xlog`:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>-XX:+UseG1GC -Xlog:gc</argLine>
  </configuration>
</plugin>
~~~

Plugin version cần được quản lý bằng cấu hình POM thực tế. Nếu có JaCoCo hoặc plugin khác thêm JVM args qua `argLine`, cần tích hợp đúng cơ chế biến/property của chúng để tránh ghi đè agent options hoặc nhân đôi flags.

Một `argLine` của Surefire không tự cấu hình Maven core hoặc Failsafe/ứng dụng production. Để điều tra lỗi, xác định command line của **test fork** và plugin đang chạy.

## 16. IDE và CI: cấu hình hợp lệ trên máy này có thể sai trên máy khác

Một IDE run configuration có thể dùng Java 17 và cờ `-XX:+UseConcMarkSweepGC` được bỏ qua kèm warning; CI chạy JDK khác và fail cứng. Hoặc IDE không truyền cờ cũ nhưng script CI vẫn truyền.

Để tránh drift:

1. Ghi chính xác JDK của IDE, Gradle/Maven, test worker và CI.
2. Chọn wrapper build tool và Java toolchain/baseline rõ ràng.
3. Tập trung GC flags quan trọng ở cấu hình được version-control.
4. Chỉ tạo exceptions theo môi trường khi có lý do và owner.
5. Thử production launcher **ngoài IDE** với runtime image thực.
6. Không coi `java -version` của terminal là bằng chứng CI đang dùng cùng JDK.

Nếu test được chạy bằng IDE runner riêng, kết quả có thể khác khi dùng Gradle/Maven tasks vì classpath, VM args và test engine khác. Với migration, lệnh build chuẩn trong CI nên là nguồn xác nhận cuối.

## 17. Docker/Kubernetes: lỗi trước khi health check

Một Dockerfile cũ:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar /app/app.jar

ENTRYPOINT [
  "java",
  "-XX:+UseConcMarkSweepGC",
  "-XX:+PrintGCDateStamps",
  "-jar",
  "/app/app.jar"
]
~~~

Đây là ví dụ có các cờ legacy sai/không còn phù hợp. Một cấu hình minh họa sau migration:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar /app/app.jar

ENTRYPOINT [
  "java",
  "-XX:+UseG1GC",
  "-Xlog:gc*:stdout:time,uptime,level,tags",
  "-jar",
  "/app/app.jar"
]
~~~

Dùng base image cụ thể phải theo policy và **pin digest** ở production khi cần reproducibility. Trong thực tế có thể chọn mặc định GC và không đặt `-XX:+UseG1GC` nếu đã xác minh collector mặc định phù hợp.

Một số lưu ý:

- Kubernetes Deployment hoặc Helm chart có thể thêm `JAVA_TOOL_OPTIONS` ngoài Dockerfile.
- Startup script có thể đọc cả `JAVA_OPTS` và `JAVA_TOOL_OPTIONS`; `JAVA_OPTS` bản thân không phải biến được Java launcher chuẩn tự động áp dụng, nó có hiệu lực khi script sử dụng.
- Một container có thể có nhiều JVM child processes với flags khác nhau.
- Ghi GC log vào file yêu cầu writable mount và rotation/retention; stdout có thể phù hợp với logging stack của Kubernetes.
- JVM không khởi động thì readiness probe không thể pass; event container restart không chứng minh ứng dụng đã tạo request.
- Nếu đổi `-Xmx` cùng lúc với collector, phải kiểm cgroup memory headroom cho metaspace, thread stacks và native memory.

## 18. Cảnh báo: IgnoreUnrecognizedVMOptions không phải cách sửa migration

HotSpot có thể hỗ trợ cờ:

~~~text
-XX:+IgnoreUnrecognizedVMOptions
~~~

Nó có thể khiến một số option không nhận diện được bị bỏ qua, tùy JVM và cơ chế flag parsing. Nhưng đây **không phải giải pháp bền vững** cho migration.

### 18.1. Vì sao không nên bật đại trà?

- Một flag quan trọng bị viết sai tên có thể âm thầm không có tác dụng.
- Collector được mong đợi không được chọn, gây thay đổi latency/throughput.
- Một security/diagnostic flag bị bỏ qua khiến đội vận hành tưởng rằng policy đã bật.
- Môi trường cũ/mới chạy với configuration thực khác nhau dù command giống nhau.
- Cờ removed bị bỏ qua không có nghĩa tính năng đã được thay thế.
- Một số lỗi về giá trị, xung đột hoặc tính khả dụng không nhất thiết được che bởi tùy chọn này.

Nếu từng dùng nó như workaround, ghi owner và thời hạn gỡ; **liệt kê đầy đủ flags được bỏ qua và chuyển sang cấu hình được hỗ trợ**.

### 18.2. Phải fail fast khi configuration sai

Với production, một option cần thiết nhưng không được JVM hiểu thường nên khiến deployment fail rõ ràng, thay vì silently chạy với cấu hình khác kỳ vọng. Nên có startup validation trên JDK đích và kiểm flags/collector thật sau khi launch.

## 19. Khi cờ chỉ bị cảnh báo mà JVM vẫn chạy

Đây là trường hợp dễ bị bỏ qua hơn lỗi cứng. Ví dụ:

~~~text
warning: Ignoring option MaxPermSize; support was removed ...
~~~

hoặc một cảnh báo rằng tùy chọn logging cũ đã được ánh xạ sang `-Xlog`.

Nếu JVM vẫn start:

1. Ghi warning và JDK version.
2. Xác định flag thuộc trạng thái deprecated/obsolete.
3. Kiểm hành vi runtime có còn đúng kỳ vọng không.
4. Xóa hoặc thay flag theo tài liệu JDK.
5. Chạy lại startup với cấu hình mới.
6. So collector, heap sizing, GC logs và performance.
7. Không bỏ qua warning chỉ vì exit code bằng 0.

Đặc biệt, **CMS đã bị remove nhưng flag CMS có thể bị ignore**. Khi đó ứng dụng đang chạy collector khác. Nếu chưa đo, chưa thể nói migration giữ được pause/throughput.

## 20. Kiểm collector và heap đã được chọn thực tế

Sau khi bỏ flags cũ, không nên dừng ở bước “JVM khởi động được”.

### 20.1. GC startup logging

Trên Java 9+:

~~~bash
java -Xlog:gc -jar service.jar
~~~

Startup logs thường có dòng thông báo collector được sử dụng, ví dụ G1. Cấu trúc log thay đổi theo version.

### 20.2. In flags khi startup

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Có thể dùng command line có chủ đích để lọc các flag như `UseG1GC`, `UseParallelGC`, `UseZGC`, `MaxHeapSize`, `MaxGCPauseMillis`. Công cụ `PrintFlagsFinal` chỉ cho biết JVM hiểu/tính toán flags theo bản runtime; nó không thay benchmark.

### 20.3. Trên JVM đang chạy

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

Thay `<pid>` bằng PID thật. Những command availability khác nhau theo JDK/collector; dùng `jcmd <pid> help` khi cần. Đối với Java process bị chết trước startup thì không có PID còn sống để tra.

### 20.4. Chú ý quyền/đường dẫn logging

Nếu thay `-Xloggc:/var/log/app/gc.log` bằng `-Xlog:...file=...` nhưng ứng dụng chạy non-root, lỗi ghi GC log có thể khiến JVM không khởi tạo như kỳ vọng. Chẩn đoán bao gồm cả filesystem permission và container log storage; không kết luận flag GC parser sai nếu vấn đề là file output.

## 21. Một pipeline phát hiện JVM flags lỗi trước khi deploy

Có thể thiết kế một bước smoke test trong CI **trên đúng JDK runtime image**:

~~~text
1. Build artifact
2. Assemble production VM options
3. Validate startup with target java executable
4. Capture stderr/stdout and version
5. Start application or minimal smoke workload
6. Inspect collector and GC logging
7. Run regression/integration tests
8. Compare SLO and memory
9. Publish only if gates pass
~~~

Không nhất thiết phải tạo một chương trình mới để parse flags. Nhưng **chỉ chạy `java -version` trên runner không đủ** nếu production option được lắp từ Helm values/entrypoint hoặc CI dùng JDK khác image.

### 21.1. Ví dụ startup argument file

Trên Java launcher hỗ trợ argument files:

~~~text
# vm-options.txt
-Xms512m
-Xmx2g
-XX:+UseG1GC
-Xlog:gc*:stdout:time,uptime,level,tags
~~~

Chạy:

~~~bash
java @vm-options.txt -jar service.jar
~~~

Việc gom cờ vào một file giúp review diff và tránh copy-paste. Tuy nhiên phải kiểm cú pháp argument file đúng phiên bản launcher, encoding và cách tham số được ghép với arguments do môi trường bổ sung.

Có thể dùng config-generation step để chọn bộ cờ theo JDK đích, nhưng logic ấy phải version-controlled và có test. Không hardcode nhiều cờ cũ rồi chỉ bật chế độ ignore.

## 22. Khởi động được chưa có nghĩa hiệu năng tương thích

Sau khi loại bỏ CMS flags, ứng dụng có thể chạy trên G1 hoặc collector khác với hành vi rất khác:

| Chỉ số | Vì sao cần đo |
|---|---|
| p50/p95/p99 latency | GC pause có thể ảnh hưởng tail latency |
| Throughput | Collector và CPU overhead có thể đổi |
| GC pause count/duration | So theo mục tiêu, không chỉ số sự kiện |
| Heap used/committed/max | Thay collector có thể đổi heap ergonomics |
| RSS/container memory | Bộ nhớ native/GC bookkeeping cũng có thể đổi |
| CPU throttling | Concurrent GC và thread count chịu ảnh hưởng quota |
| Startup/warm-up | JIT và class loading có thể khác |
| OOME/OOMKilled | Collector mới không miễn trừ thiếu headroom |

Không có mapping một-một từ `CMSInitiatingOccupancyFraction` sang một giá trị G1/ZGC bảo đảm latency cũ. Cần benchmark trên request mix và memory/CPU limits đại diện.

### 22.1. So sánh GC logs theo mục tiêu chung

GC event names, phases và cấu trúc vùng nhớ có thể khác nhau giữa CMS/G1/ZGC. Đừng so số lượng “young GC” hoặc tổng số log lines như một metric tương đương tuyệt đối.

Nên so:

- Tổng throughput công việc.
- Thời gian pause (phân phối và max) theo đơn vị thống nhất.
- GC CPU/overhead.
- Allocation/live-set/headroom khi có thể.
- p99 application latency.
- Peak RSS và tổng memory budget.
- Độ ổn định trong một bài test tải đủ dài.

## 23. Ví dụ điều tra: từ JDK 8/CMS sang JDK 21

Giả sử script cũ chứa:

~~~bash
java \
  -Xms1g -Xmx4g \
  -XX:+UseConcMarkSweepGC \
  -XX:+CMSIncrementalMode \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -Xloggc:/logs/gc.log \
  -jar billing.jar
~~~

### Bước 1: Xác định lỗi đầu tiên

Nếu JVM báo `Unrecognized VM option 'CMSIncrementalMode'` hoặc `PrintGCDateStamps`, đừng sửa class application. Những cờ đó thuộc cơ chế GC/logging cũ.

### Bước 2: Xóa cả họ cờ không còn phù hợp

Không chỉ xóa đúng một cờ mà thông báo đầu tiên nhắc tới rồi dừng. Có thể còn nhiều cờ cũ khác; mỗi lần JVM parse đến cờ kế tiếp lại fail.

### Bước 3: Thay bộ chọn collector

Để JVM dùng default hoặc chọn G1 có chủ đích sau khi xem support và benchmark. Không xem việc G1 khởi động được là thay thế hiệu năng 1:1 cho CMS.

### Bước 4: Chuyển logging

Ví dụ:

~~~bash
java \
  -Xms1g -Xmx4g \
  -XX:+UseG1GC \
  "-Xlog:gc*:file=/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20m" \
  -jar billing.jar
~~~

### Bước 5: Kiểm hiệu lực

Xác nhận GC được chọn là G1, file log được tạo, tài khoản chạy app có quyền ghi và heap sizing như kỳ vọng.

### Bước 6: Chạy hồi quy

Chạy cùng chức năng nghiệp vụ và workload trên môi trường cũ/mới, lưu memory, pause, error rate và p99 latency. Không ngẫu nhiên nâng driver, ORM hoặc đổi schema trong cùng phép thử nếu mục tiêu là cô lập ảnh hưởng GC.

Mọi command ở ví dụ chỉ là tài liệu học, **không phải lệnh đã chạy trên hệ thống của người đọc**.

## 24. Ví dụ điều tra: ZGC cũ trên JDK 24

Giả sử production đang dùng ZGC với:

~~~text
-XX:+UseZGC
-XX:-ZGenerational
~~~

Sau khi lên JDK 24, non-generational ZGC đã bị loại bỏ. Không nên giữ option yêu cầu mode không còn.

Hướng xử lý:

1. Kiểm JDK runtime và release notes.
2. Xóa `-XX:-ZGenerational` khi nâng lên release không còn mode này.
3. Giữ `-XX:+UseZGC` **chỉ nếu có lý do chọn ZGC**.
4. Chạy startup validation và GC logs.
5. Benchmark heap headroom, GC CPU và latency; workload từng tối ưu cho non-generational có thể có trade-off khác.
6. Lưu kết quả và cập nhật config docs.

Đừng nói “Java đã xóa ZGC” — bị xóa là **non-generational mode**, không phải toàn bộ ZGC collector.

## 25. Ví dụ điều tra: Gradle daemon không khởi động, application không có lỗi

Log có thể chứa:

~~~text
Unable to start the daemon process.
Unrecognized VM option 'SomeRemovedFlag'
~~~

Nếu cờ nằm trong `org.gradle.jvmargs`, JVM bị lỗi là **Gradle daemon**. Bước hợp lý:

1. Kiểm Gradle JVM/JDK trong terminal/IDE/CI.
2. Kiểm `gradle.properties` ở project/user scope và launcher settings.
3. Tìm cờ cũ trong `org.gradle.jvmargs`.
4. Xóa/thay flag không hỗ trợ cho daemon.
5. Khởi động lại build bằng wrapper đúng phiên bản.
6. Sau đó mới kiểm các `Test` và `JavaExec` child JVM.

Không cần sửa `-Xmx` của application container nếu chỉ Gradle daemon fail. Và không nên xóa hàng loạt Gradle caches để giải quyết một option parser error.

## 26. Ví dụ điều tra: app production fail nhưng unit test pass

Trong CI, unit tests có thể chạy với G1 mặc định, còn Kubernetes manifest truyền:

~~~yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: "-XX:+UseConcMarkSweepGC -XX:+PrintGCDateStamps"
~~~

Đây là ví dụ của một nguồn option **ngoài repository build tasks**. Lý do unit test pass là JVM test không nhận cùng cờ; lỗi chỉ xuất hiện khi pod start.

Sửa trong deployment configuration, chạy chính image/entrypoint ở staging và thêm bước kiểm startup flags vào pipeline. Không đánh dấu migration hoàn tất chỉ vì unit tests xanh.

## 27. Tình huống cờ không bị xóa nhưng giá trị không hợp lệ

Không phải mọi lỗi parsing là removed option. Ví dụ:

~~~text
-XX:MaxGCPauseMillis=abc
~~~

Cờ có thể tồn tại, nhưng `abc` không phải giá trị hợp lệ. Hoặc:

~~~text
-Xmx-1g
~~~

là sizing syntax không hợp lệ. Một số flags yêu cầu range hoặc dependency conditions đặc biệt.

Cách chẩn đoán:

- Xác minh tên option có tồn tại trong JVM đích.
- Kiểm đúng dạng boolean/số/size.
- Kiểm range/đơn vị.
- Kiểm unlock requirement nếu là experimental/diagnostic.
- Kiểm các cờ phụ thuộc hoặc xung đột.
- Chạy reproduction chỉ với một cờ, rồi ghép dần.
- Không dùng `IgnoreUnrecognizedVMOptions` để che sai giá trị.

Nếu báo lỗi “improperly specified VM option”, “outside the allowed range” hoặc tương tự, cần giữ nguyên thông báo gốc trong báo cáo; đừng gộp mọi lỗi thành unrecognized.

## 28. JVM vendor và runtime image cũng ảnh hưởng

Các bản phân phối Java không nhất thiết giống hệt nhau về:

- Những GC có sẵn trên OS/architecture.
- Experimental/diagnostic flags.
- Những bản vá/backport theo update train.
- Runtime image tối giản hoặc custom `jlink`.
- GC logging support và build-time features.
- Cách packaged launcher truyền options.

Ví dụ, một collector có thể không được build cho một platform, dù JDK feature number giống nhau. Cần xác minh bằng tài liệu của vendor và các lệnh runtime introspection; không tự gán cho JDK một collector chỉ vì đọc JEP chung.

Khi triển khai nhiều kiến trúc (Linux x64/ARM64/Windows), cần kiểm startup và GC flags ở **mỗi tổ hợp được tuyên bố hỗ trợ**.

## 29. Phân biệt lỗi JVM option với lỗi Java application option

Một command:

~~~bash
java -Xmx1g -jar app.jar --mode=batch
~~~

thường hiểu:

- `-Xmx1g` là JVM option trước `-jar`.
- `--mode=batch` là argument của ứng dụng sau tên JAR.

Nhưng:

~~~bash
java -jar app.jar -XX:+UseG1GC
~~~

thường truyền `-XX:+UseG1GC` cho **ứng dụng** như một argument, không cấu hình GC của Java launcher vì đứng sau JAR. Framework CLI có thể báo “unknown option”, dễ nhầm với `Unrecognized VM option` của JVM.

Vì vậy, kiểm **vị trí đối số** trước và sau `-jar`, `--module` hoặc main class. Với shell wrapper, đảm bảo các JVM flags đặt đúng phía launcher.

## 30. Kế hoạch kiểm thử và go/no-go

Một thay đổi khắc phục option error cần qua ít nhất những gate phù hợp:

| Gate | Câu hỏi | Bằng chứng |
|---|---|---|
| Static audit | Có cờ bị remove/obsolete trong mọi nguồn cấu hình không? | Danh mục VM options, diff |
| Parse/startup | JVM đích có chấp nhận toàn bộ flags không? | Exit code, stderr, logs |
| Collector selection | Đúng GC hoặc default đã được duyệt? | GC init log, VM.flags |
| Logging | GC/safepoint logs có ghi đúng không? | File/stdout, retention config |
| Memory | Heap/metaspace/native trong ngân sách? | JVM metrics, RSS/container usage |
| Performance | p99 latency, throughput và GC pauses đạt SLO? | Load test, GC logs |
| Regression | Business behavior và negative tests vẫn đúng? | Unit/integration/security tests |
| Reproducibility | IDE/CLI/CI/production dùng config có kiểm soát? | Artifact and environment fingerprint |
| Rollback | Có thể quay lại artifact/config ổn định không? | Rollout và recovery plan |

Không tự động chấp nhận việc một option bị bỏ qua như dấu hiệu an toàn. Một application chạy collector khác với dự định có thể phát sinh regression dưới tải dù smoke test thành công.

## 31. Quy trình chẩn đoán 12 bước

### Bước 1 — Lưu nguyên văn lỗi và thời điểm

Giữ stderr/stdout và message đầu tiên, tránh chỉ lưu dòng cuối `Could not create the Java Virtual Machine`. Ghi JDK path/version, OS, container image và service/job name.

### Bước 2 — Xác định process nào lỗi

Gradle daemon, Maven, test worker, application server, batch job hay Java agent? Đường sửa khác nhau.

### Bước 3 — Thu đầy đủ JVM arguments

Kiểm script, environment, IDE, Gradle/Maven, CI, Docker/Kubernetes, argument file và service manager. Che secrets trong logs.

### Bước 4 — Phân loại từng flag

Gắn nhãn supported/deprecated/obsolete/removed/unknown/vender-specific/invalid value. Không chỉ xóa cờ đầu tiên trong error.

### Bước 5 — Kiểm tài liệu đúng JDK

Dùng `java --help-extra`, `-Xlog:help`, `-XX:+PrintFlagsFinal`, vendor docs và release notes. Với collector thay đổi, xem JEP có liên quan.

### Bước 6 — Tạo reproduction tối thiểu

Thử `java [flag] -version` trên chính Java executable đích. Phân biệt lỗi option với application logic.

### Bước 7 — Xóa cờ đã hết tác dụng

Không giữ `MaxPermSize`, CMS-only options hoặc mode đã bị loại chỉ vì có thể còn được ignore.

### Bước 8 — Thay mục tiêu logging bằng cú pháp mới

Chuyển GC logs sang `-Xlog`, kiểm tags/decorators/rotation/output permission và log ingestion.

### Bước 9 — Chọn GC có chủ đích

Dùng default hoặc collector được hỗ trợ, dựa trên latency/throughput/memory requirements. Không copy CMS tuning sang G1/ZGC.

### Bước 10 — Chạy đúng launcher thực tế

Dùng artifact và container/VM entrypoint như production, không chỉ chạy `java -version` trên laptop.

### Bước 11 — Chạy regression và performance tests

So ứng dụng trên old/new JDK với test suite, workload và memory/CPU budget tương đương trong phạm vi hỗ trợ.

### Bước 12 — Ghi bằng chứng và chốt ownership

Lưu diff JVM arguments, actual GC, JDK build, test reports, metrics, những nơi chưa kiểm và kế hoạch rà soát khi nâng JDK tiếp.

## 32. Mẫu bảng audit JVM options

| Option đang có | Nguồn | JDK đích | Phân loại | Quyết định |
|---|---|---|---|---|
| `-XX:+UseConcMarkSweepGC` | Deployment script | 21 | CMS không còn | Xóa, kiểm default/G1 |
| `-XX:+CMSIncrementalMode` | Startup args | 21 | Incremental CMS không hỗ trợ | Xóa |
| `-XX:+PrintGCDateStamps` | Launcher | 21 | Legacy GC logging | Chuyển `-Xlog` decorator |
| `-Xloggc:gc.log` | Launcher | 21 | Legacy/deprecated logging form | Chuyển `-Xlog` |
| `-XX:MaxPermSize=256m` | Old build config | 21 | Obsolete/ignored | Xóa, không thay cap cơ học |
| `-XX:-ZGenerational` | ZGC config | 24 | Non-generational mode removed | Xóa, chạy generational ZGC nếu chọn ZGC |
| `-Xmx2g` | Deployment | 21 | Supported sizing | Giữ nếu memory budget xác nhận |
| `-XX:+UseG1GC` | Application script | 21 | Supported collector | Giữ hoặc dùng default sau test |

Đây là **mẫu phân tích**, không phải kết quả từ một service thật. “JDK đích” chỉ là ví dụ để minh họa cách xác định; trước khi sửa, vẫn phải xem cụ thể cờ nào được runtime/vendor nhận hay ignore.

## 33. Mẫu báo cáo sự cố cho Prime hoặc reviewer

~~~yaml
incident:
  category: "JVM_STARTUP_FLAG"
  symptom: "Unrecognized VM option"
  failingProcess: "application container"
  targetJdk:
    version: "record java -version"
    vendorBuild: "record exact build"
  option:
    name: "CMSIncrementalMode"
    source: "deployment JVM arguments"
    original: "-XX:+CMSIncrementalMode"
  change:
    action: "remove legacy CMS option"
    replacementCollector: "G1"
    logging: "-Xlog:gc*"
  validation:
    startup: "NOT_YET_RUN"
    actualCollector: "NOT_YET_VERIFIED"
    regressionTests: "NOT_YET_RUN"
    performanceTest: "NOT_YET_RUN"
  risks:
    - "GC pause profile can differ from CMS"
  owner: "runtime-team"
~~~

Không được thay `NOT_YET_RUN` bằng PASS trước khi có log/artifact. Nên gắn commit, JDK build, binary/container digest, test report, workload và số liệu SLO thực tế.

## 34. Những hiểu lầm cần tránh

**“Unrecognized VM option nghĩa là code Java sai.”** Không. Đây thường là lỗi launcher/JVM arguments trước khi application chạy.

**“CMS bị xóa ở JDK 14 thì mọi cờ CMS đều báo unrecognized từ JDK 14.”** Không. Một số có thể là obsolete, được nhận và bị bỏ qua; một số khác đã bị loại sớm hoặc muộn hơn.

**“JVM khởi động thành công nghĩa là mọi flag đã được áp dụng.”** Không. Obsolete flags có thể bị ignore kèm warning.

**“Cứ bật `IgnoreUnrecognizedVMOptions` là đủ.”** Không. Nó có thể che cả flag quan trọng bị sai.

**“GC tuning của CMS có mapping tương đương sang G1.”** Không. Thuật toán và mục tiêu khác nhau.

**“JDK 9 trở lên vẫn cần `PrintGCDateStamps`.”** Không. Unified Logging dùng decorators như `time` và `uptime`.

**“`PrintGCDetails` và `-Xlog:gc*` luôn cho file giống nhau.”** Không. Format/tag/level thay đổi.

**“Generational ZGC là default thì mọi ứng dụng dùng ZGC.”** Không. Nó chỉ nói mode của ZGC khi ZGC được chọn.

**“ZGC đã bị loại khỏi JDK 24.”** Không. Non-generational mode bị loại, không phải toàn bộ collector.

**“Chạy `java -version` tại terminal là đủ xác minh production.”** Không nếu app/container/test JVM khác.

**“Tất cả startup JVM options phải nằm trong source.”** Không. Có thể đến từ CI, Docker, environment, service manager, IDE và tool wrappers.

**“Chỉ cần sửa cờ đầu tiên làm fail.”** Có thể còn một chuỗi cờ không tương thích khác.

**“JDK mới vẫn có cờ này nên mọi vendor/architecture đều hỗ trợ.”** Không nhất thiết.

**“Đổi GC mà functional tests pass là xong.”** Cần đánh giá latency, throughput, GC overhead, memory và OOM risk.

**“Bỏ `-Xmx`/đặt heap sát memory limit sẽ tránh lỗi startup.”** Không liên quan unrecognized flag và có thể gây OOMKilled.

## 35. Checklist kiểm tra sau migration

- [ ] Đã xác định chính xác JDK feature/update/vendor/build của process lỗi.
- [ ] Đã ghi đầy đủ thông báo startup và option name đầu tiên.
- [ ] Đã phân biệt Gradle daemon, Maven core, test JVM và application JVM.
- [ ] Đã kiểm các nguồn `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `_JAVA_OPTIONS` và launcher scripts khi áp dụng.
- [ ] Đã rà soát source/build/CI/container/Helm/systemd/IDE cho cờ GC cũ.
- [ ] Đã phân loại flags supported, deprecated, obsolete, removed hoặc invalid.
- [ ] Đã loại CMS-only/incremental-CMS flags khi chuyển JDK không hỗ trợ.
- [ ] Đã loại PermGen flags và không ép metaspace cap theo giá trị cũ vô căn cứ.
- [ ] Đã cập nhật ZGC mode flags theo JDK mục tiêu nếu dùng ZGC.
- [ ] Đã chuyển legacy GC logging sang `-Xlog` trên Java 9+.
- [ ] Đã kiểm logging tags/decorators/rotation và quyền ghi output.
- [ ] Đã bỏ flags trùng/mâu thuẫn khi ghép từ nhiều nguồn.
- [ ] Không dùng `IgnoreUnrecognizedVMOptions` làm giải pháp lâu dài.
- [ ] Đã chạy startup test bằng **đúng production JDK và launcher options**.
- [ ] Đã xác nhận collector/heap flags hiệu lực từ logs/JVM diagnostics.
- [ ] Đã chạy regression tests với application artifact thật.
- [ ] Đã so latency, throughput, GC pauses, RSS và memory budget.
- [ ] Đã ghi lại test nào chưa chạy và môi trường chưa kiểm.
- [ ] Đã lưu diff cấu hình, JDK build, logs và quyết định go/no-go.
- [ ] Đã có chủ sở hữu và phương án rollback/roll-forward nếu có regression.

## 36. Tài liệu tham khảo chính thức

Nên ưu tiên tài liệu **đúng JDK mục tiêu** thay vì sao chép cờ từ hướng dẫn nhiều năm trước:

- **JEP 122 — Remove the Permanent Generation:** https://openjdk.org/jeps/122
- **JEP 158 — Unified JVM Logging:** https://openjdk.org/jeps/158
- **JEP 214 — Remove GC Combinations Deprecated in JDK 8:** https://openjdk.org/jeps/214
- **JEP 248 — Make G1 the Default Garbage Collector:** https://openjdk.org/jeps/248
- **JEP 271 — Unified GC Logging:** https://openjdk.org/jeps/271
- **JEP 363 — Remove the CMS Garbage Collector:** https://openjdk.org/jeps/363
- **JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector:** https://openjdk.org/jeps/377
- **JEP 439 — Generational ZGC:** https://openjdk.org/jeps/439
- **JEP 474 — ZGC: Generational Mode by Default:** https://openjdk.org/jeps/474
- **JEP 490 — ZGC: Remove the Non-Generational Mode:** https://openjdk.org/jeps/490
- **Java 21 launcher options và mapping GC logging:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- **Oracle JDK 26 migration guide:** https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html
- **JDK 24 migration changes:** https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html

Các liên kết này giúp xác định mốc và syntax chính thức. Với JDK mới hơn hoặc một runtime vendor khác, cần đối chiếu release notes, flags và collector availability tại thời điểm triển khai.

## Kết luận

**`Unrecognized VM option` là vấn đề về cấu hình khởi tạo JVM, không phải lỗi cần chữa bằng sửa mã Java.** Khi nâng JDK, những cờ GC cũ có thể bị xóa, trở thành obsolete và bị bỏ qua, hoặc còn được nhận nhưng chỉ tồn tại như alias tạm thời. CMS đã bị loại khỏi JDK 14, một số tổ hợp Incremental CMS bị loại từ JDK 9, còn hệ thống GC logging mới từ Java 9 sử dụng `-Xlog`. Với ZGC, thay đổi mode qua JDK 21–24 cũng có thể khiến cờ cũ mất ý nghĩa hoặc không còn được hỗ trợ.

Cách giải quyết bền vững là **xác định đúng JVM đang lỗi, thu đầy đủ startup options, phân loại trạng thái từng cờ theo JDK đích, xóa hoặc thay đúng chức năng rồi kiểm chứng collector và logs thực tế**. Sau khi ứng dụng khởi động, vẫn cần chạy regression/performance tests dưới tải đại diện để xác nhận hiệu năng và memory budget. “Hết thông báo lỗi” chỉ là bước đầu; kết quả migration tốt là một cấu hình có thể truy vết, được JVM đích hỗ trợ và có bằng chứng vận hành an toàn.

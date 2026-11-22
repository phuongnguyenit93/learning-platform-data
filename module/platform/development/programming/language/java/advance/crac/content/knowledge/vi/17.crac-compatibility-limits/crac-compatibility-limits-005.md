# Giới hạn thay đổi heap, GC và các cờ JVM theo bản dựng

Checkpoint CRaC lưu trạng thái của một tiến trình Java đang chạy. Trạng thái đó không chỉ gồm object trong heap mà còn có cấu trúc quản lý bộ nhớ, trạng thái garbage collector (GC), vùng mã JIT, thread, native memory và nhiều thành phần nội bộ của JVM. Vì vậy, checkpoint có quan hệ chặt chẽ với bản dựng JDK và cấu hình JVM đã dùng khi tạo ảnh.

Một checkpoint được tạo với heap và GC configuration cụ thể không nên được xem như dữ liệu có thể tùy ý restore bằng một JDK khác, collector khác hoặc một bộ cờ JVM khác. Thay đổi các tham số như `-Xms`, `-Xmx`, `-XX:+UseG1GC`, compressed object pointers, object alignment hoặc các tùy chọn ảnh hưởng cấu trúc runtime có thể làm môi trường restore không còn khớp với trạng thái đã lưu.

Nguyên tắc vận hành an toàn là **cố định JDK vendor/build và bộ JVM flags đã tạo checkpoint; nếu cần thay đổi heap, GC hoặc cờ ảnh hưởng runtime, hãy tạo checkpoint mới từ cấu hình mới**. Chỉ thay đổi khi tài liệu của đúng bản phân phối JDK xác nhận tùy chọn đó được phép thay đổi trong quá trình restore và đã có kiểm thử với chính tổ hợp triển khai.

## 1. Vì sao heap và GC configuration liên quan tới checkpoint?

JVM quản lý bộ nhớ bằng nhiều cấu trúc ngoài object graph của ứng dụng. Khi tiến trình được checkpoint, các vùng nhớ và cấu trúc runtime này là một phần của trạng thái cần được phục hồi.

Các thành phần liên quan gồm:

- **Java heap:** vùng chứa object, array và dữ liệu ứng dụng.
- **Heap reservation và commit:** vùng địa chỉ JVM dành trước và vùng bộ nhớ đã commit cho heap.
- **Object layout:** cách JVM biểu diễn object header, reference và alignment.
- **GC metadata:** region, card table, remembered set, marking state, free list hoặc cấu trúc tương đương của collector.
- **Native memory:** vùng nhớ ngoài heap do JVM, GC, thư viện native và ứng dụng sử dụng.
- **Code cache:** vùng lưu mã máy được JIT compiler tạo ra.
- **Thread stack:** vùng stack của các thread đang tồn tại.
- **Runtime metadata:** class metadata, classloader, cấu trúc đồng bộ và trạng thái nội bộ khác.

Các cấu trúc này được tạo và quản lý theo cấu hình JVM cụ thể. Nếu restore bằng cấu hình khác, không thể giả định JVM sẽ tự chuyển đổi toàn bộ trạng thái đã lưu sang layout hoặc chính sách mới.

## 2. Heap sizing: `-Xms` và `-Xmx`

Hai tùy chọn heap sizing thường gặp:

- `-Xms`: kích thước heap ban đầu mà JVM yêu cầu.
- `-Xmx`: giới hạn heap tối đa.

Ví dụ:

```bash
java -Xms512m -Xmx2g -jar app.jar
```

Các giá trị này ảnh hưởng cách JVM reserve, commit và quản lý heap. Một tiến trình tạo checkpoint với `-Xms512m -Xmx2g` đã hình thành trạng thái bộ nhớ theo cấu hình đó. Khi restore, thay bằng `-Xms1g -Xmx4g` không đơn thuần là thay một con số cấu hình: heap và các cấu trúc runtime đã tồn tại trong ảnh cần được tiếp tục theo các giả định tương ứng.

Vì vậy, hãy giữ nguyên heap sizing khi restore, trừ khi nhà cung cấp JDK có tài liệu rõ ràng về khả năng thay đổi và xác nhận cấu hình mới tương thích.

### 2.1. Tác động của việc thay `-Xmx`

Thay đổi `-Xmx` có thể làm thay đổi:

- giới hạn heap mà JVM được phép sử dụng;
- quyết định sizing và ergonomics của GC;
- số region hoặc kích thước vùng quản lý heap ở collector có phân vùng;
- ngưỡng kích hoạt GC và hành vi allocation;
- lượng bộ nhớ mà container cần cung cấp.

Nếu checkpoint được tạo với heap tối đa lớn nhưng container restore có memory limit thấp hơn, tiến trình có thể không restore được, bị hệ điều hành/container runtime giới hạn hoặc bị OOM sau khi nhận tải. Ngược lại, tăng `-Xmx` khi restore không đảm bảo JVM có thể mở rộng trạng thái heap đã lưu theo cách an toàn.

### 2.2. Tác động của việc thay `-Xms`

`-Xms` ảnh hưởng lượng heap ban đầu JVM cam kết hoặc quản lý theo chính sách của runtime. Thay đổi giá trị này có thể làm thay đổi memory footprint và hành vi mở rộng heap. Khi restore, trạng thái heap đã có trong checkpoint; không nên coi `-Xms` là một tham số độc lập có thể đổi tùy ý.

### 2.3. Chọn heap trước khi tạo checkpoint

Heap nên được chọn từ workload và giới hạn môi trường tạo checkpoint:

1. Đo heap usage trong workload đại diện.
2. Xác định allocation rate và GC behavior.
3. Đo native memory, thread stack, code cache và phần memory ngoài heap.
4. Chừa headroom cho restore, callback và tải sau khi instance sẵn sàng.
5. Đối chiếu với container memory limit và node capacity.
6. Chạy restore thử trên đúng giới hạn tài nguyên dự kiến.

Không nên đặt `-Xmx` bằng toàn bộ memory limit của container. JVM còn cần native memory, thread stack, direct buffer, metaspace, code cache và các vùng nhớ khác. Container cũng cần khoảng trống cho agent, thư viện native và tiến trình phụ trợ nếu có.

## 3. Object layout và các cờ ảnh hưởng cách biểu diễn bộ nhớ

Một số cờ JVM ảnh hưởng cách JVM biểu diễn object và reference. Chúng có thể tác động tới kích thước object, cách truy cập heap và các giả định nội bộ của runtime.

Ví dụ các tùy chọn thường gặp ở HotSpot:

- `-XX:+UseCompressedOops`: sử dụng compressed ordinary object pointers trong các điều kiện JVM hỗ trợ.
- `-XX:+UseCompressedClassPointers`: nén class pointer trong object metadata.
- `-XX:ObjectAlignmentInBytes=<n>`: điều chỉnh alignment của object trong các bản JVM hỗ trợ.
- Các tùy chọn liên quan tới heap base, pointer compression hoặc layout nội bộ khác.

Các tùy chọn này phụ thuộc kiến trúc, kích thước heap và bản dựng JVM. Một số có thể được JVM tự quyết định theo ergonomics thay vì do người vận hành chỉ định.

Khi checkpoint được tạo, object graph đã tồn tại với layout do JVM chọn. Không nên đổi các cờ ảnh hưởng layout khi restore nếu chưa có tài liệu xác nhận rõ ràng. Hãy ghi lại cả giá trị hiệu lực, không chỉ các cờ đã gõ trong command line.

### 3.1. Giá trị mặc định cũng là một phần cấu hình

Nếu không chỉ định `UseCompressedOops`, JVM có thể tự bật hoặc tắt tùy theo kiến trúc và heap sizing. Hai môi trường dùng cùng command line nhưng khác memory limit hoặc JDK build có thể có giá trị hiệu lực khác nhau.

Do đó, chỉ lưu file launch script là chưa đủ. Cần ghi nhận effective flags và thông tin runtime từ chính tiến trình tạo checkpoint.

## 4. GC collector và trạng thái nội bộ

Garbage collector quản lý heap bằng các cấu trúc và thuật toán riêng. Một checkpoint lưu trạng thái tiến trình trong đó có các cấu trúc runtime của collector. Vì vậy, collector được chọn khi tạo checkpoint là một phần quan trọng của bộ cấu hình cần giữ ổn định.

Các collector phổ biến của HotSpot có thiết kế khác nhau, ví dụ:

| Collector | Đặc điểm khái quát | Những gì cần cố định khi tạo checkpoint |
| --- | --- | --- |
| Serial GC | Thu gom theo cách đơn giản, thường dùng cho heap nhỏ hoặc môi trường đặc thù | Cấu hình collector và các tham số heap liên quan |
| Parallel GC | Ưu tiên throughput, có các worker song song khi GC | Collector, số worker và các tham số sizing quan trọng |
| G1 GC | Chia heap thành region và cân bằng pause/throughput | Collector, region/heap ergonomics và các cờ G1 |
| ZGC | Collector độ trễ thấp với cấu trúc quản lý heap riêng | Collector, chế độ hoạt động và các cờ ZGC theo JDK |
| Shenandoah | Collector concurrent với cơ chế quản lý heap riêng | Collector và các tùy chọn được hỗ trợ trong đúng build |

Không thể lấy checkpoint được tạo với một collector rồi tùy ý restore bằng collector khác. Ví dụ, `-XX:+UseG1GC` và `-XX:+UseZGC` không phải hai lựa chọn thay thế có thể đổi ở bước restore như thay một biến cấu hình ứng dụng.

### 4.1. G1 GC

G1 chia heap thành nhiều region và duy trì metadata phục vụ marking, remembered set, evacuation và lựa chọn collection set. Kích thước heap, region size, số worker và các tùy chọn G1 ảnh hưởng tới cách collector tổ chức và vận hành.

Nếu thay `-XX:+UseG1GC`, heap sizing hoặc cờ G1 giữa tạo checkpoint và restore, trạng thái runtime đã lưu có thể không còn tương thích với cấu hình mới. Hãy giữ nguyên collector và các cờ quan trọng; muốn đổi chính sách G1, hãy khởi chạy lại ứng dụng với cấu hình mới, warm-up và tạo checkpoint mới.

### 4.2. ZGC và các collector khác

ZGC và các collector concurrent có cấu trúc quản lý bộ nhớ riêng. Tùy chọn của collector có thể thay đổi cách heap được ánh xạ, cách xử lý reference và cách sử dụng native memory. Các chế độ và tên cờ cũng có thể thay đổi giữa các JDK release.

Không giả định rằng cùng tên collector đồng nghĩa với cùng implementation qua mọi JDK. Cần ghi lại JDK build cụ thể và kiểm tra tài liệu của bản đó. Nếu nâng JDK hoặc thay collector, nên tạo checkpoint mới thay vì tái sử dụng ảnh cũ.

### 4.3. GC state không phải chỉ là heap contents

Một heap có cùng object contents vẫn có thể được quản lý bởi các cấu trúc GC khác nhau. GC còn theo dõi vùng nhớ, metadata, phase, reference processing và trạng thái nội bộ. Do đó, không thể đánh giá khả năng tương thích chỉ bằng cách so sánh số object hoặc heap used.

Việc restore cần giữ sự nhất quán giữa heap, metadata của collector và runtime đã tạo ra chúng.

## 5. Các nhóm JVM flags cần phân biệt

Không phải mọi JVM flag đều có cùng mức độ ảnh hưởng. Khi đóng gói checkpoint, nên phân loại flags để biết phần nào phải pin chặt và phần nào có thể được thay đổi theo tài liệu của JDK.

| Nhóm | Ví dụ | Cách quản lý |
| --- | --- | --- |
| Heap sizing | `-Xms`, `-Xmx`, `-Xmn` nếu được dùng | Giữ nguyên giữa checkpoint và restore |
| GC selection | `-XX:+UseG1GC`, `-XX:+UseZGC`, `-XX:+UseParallelGC` | Không đổi collector cho ảnh đã tạo |
| GC tuning | G1 pause target, GC worker count, region-related flags | Giữ nguyên và version cùng runtime |
| Object layout | CompressedOops, compressed class pointers, object alignment | Cố định theo giá trị hiệu lực |
| Runtime memory | Metaspace, code cache, direct memory limits | Ghi nhận và giữ tương thích |
| Thread/runtime | Stack size, compiler threads, runtime thread options | Không thay tùy tiện; kiểm thử theo build |
| Module/access | `--add-opens`, `--add-exports`, module path | Giữ cùng cấu hình để tránh khác biệt class access |
| Agent/native | `-javaagent`, `-agentlib`, `-agentpath` | Cố định binary, version và cấu hình agent |
| Diagnostics | JFR, logging, GC log | Quản lý riêng; đánh giá ảnh hưởng và cách bật khi restore |
| System properties | `-Dkey=value`, locale, timezone, encoding | Giữ nhất quán với cấu hình đã được object khởi tạo sử dụng |
| CRaC options | Checkpoint/restore path và các tùy chọn riêng của JDK | Theo tài liệu của đúng JDK distribution |

Một số flags có thể được thay đổi động qua diagnostic command hoặc MXBean trong một số bản JVM; điều đó không có nghĩa mọi thay đổi đều phù hợp khi restore. Với checkpoint, cách quản lý dễ kiểm soát nhất là dùng cùng bộ flags và chỉ thay đổi sau khi tạo checkpoint mới.

## 6. Flags có thể thay đổi động và flags khởi động

JVM có các loại tùy chọn khác nhau:

- **Startup-only flags:** chỉ được đọc khi JVM khởi chạy; không thể thay đổi bằng cách sửa command line sau khi process đã chạy.
- **Manageable flags:** một số giá trị có thể thay đổi qua JMX hoặc diagnostic command nếu JVM hỗ trợ.
- **Ergonomic values:** JVM tự chọn dựa trên JDK, phần cứng, container limit và các flags khác.
- **Restore-specific options:** tùy chọn điều khiển cơ chế restore do bản phân phối JDK quy định.

Không suy luận khả năng thay đổi chỉ từ tên flag. Hãy xem metadata của flag và tài liệu của JDK cụ thể. Ngay cả khi một flag là manageable, cần kiểm tra liệu việc thay đổi trước checkpoint có tạo ra trạng thái được hỗ trợ khi restore hay không.

### 6.1. Xem giá trị flags hiệu lực

Có thể ghi lại flags khi chạy JVM bằng:

```bash
java -XX:+PrintFlagsFinal -version
```

Lệnh in ra danh sách flags và giá trị cuối cùng sau khi áp dụng defaults và command line. Output có thể rất dài; pipeline nên lưu toàn bộ output làm artifact của release.

Với một tiến trình đang chạy, dùng `jcmd` của JDK tương ứng:

```bash
jcmd <pid> VM.flags -all
jcmd <pid> VM.command_line
jcmd <pid> VM.version
```

Các lệnh này giúp xem flags, command line và phiên bản JVM thực tế. Một số lệnh hoặc trường output phụ thuộc bản JDK; kiểm tra `jcmd <pid> help` nếu lệnh không được hỗ trợ.

### 6.2. So sánh cấu hình trước khi restore

Release manifest nên chứa digest của file flags và danh sách effective flags quan trọng. Trước restore, deployment system có thể xác minh:

- JDK vendor/version/build khớp.
- Heap sizing khớp.
- GC collector và các tùy chọn quan trọng khớp.
- Object layout flags khớp.
- Native agent và module options khớp.
- Container memory limit và kiến trúc nằm trong phạm vi đã kiểm thử.

Không cần coi mọi diagnostic flag là blocker nếu chúng được tài liệu xác nhận có thể thay đổi. Nhưng mọi ngoại lệ cần được định nghĩa rõ trong compatibility policy, không xử lý bằng phỏng đoán khi deploy.

## 7. Cấu hình container và memory limit

JVM có thể dùng container-aware ergonomics để xác định heap và số CPU nhìn thấy. Memory limit hoặc CPU quota của container vì thế có thể ảnh hưởng tới giá trị flags hiệu lực.

Ví dụ, cùng một lệnh:

```bash
java -XX:+UseContainerSupport -jar app.jar
```

có thể dẫn tới heap sizing khác nhau nếu container có memory limit khác nhau. Nếu checkpoint được tạo trong container 4 GiB nhưng restore trong container 1 GiB, JVM có thể không còn đủ tài nguyên để phục hồi và vận hành trạng thái đã lưu.

Các yếu tố cần ghi nhận:

- Container memory limit và CPU limit.
- Cgroup version và cách JVM nhận diện container.
- Heap max và heap initial hiệu lực.
- Số processor JVM nhìn thấy.
- Native memory và direct memory limit.
- Thread count và stack size.
- Node capacity và áp lực memory tại thời điểm restore.

Không chỉ kiểm tra `-Xmx`. Một ứng dụng có heap 1 GiB vẫn có thể vượt memory limit nếu native memory, thread stack, direct buffer, code cache và các tiến trình khác chiếm phần còn lại.

### 7.1. Đặt memory headroom

Ví dụ một container có giới hạn 3 GiB không nên mặc định đặt `-Xmx3g`. Một phần memory cần dành cho:

- Metaspace và class metadata.
- Code cache.
- Thread stacks.
- Direct byte buffers.
- Native libraries và GC structures.
- JVM internal allocations.
- Agent, profiler hoặc telemetry.
- Phần dự phòng cho biến động workload.

Hãy đo memory footprint thực tế sau restore và dưới tải đại diện. Mục tiêu là instance có thể restore, đạt readiness và chịu được tải mà không bị OOM kill.

## 8. Code cache và JIT-related flags

CRaC có thể giữ trạng thái mã đã được JIT biên dịch trong tiến trình. Vì vậy, code cache và các tùy chọn compiler cũng là một phần của runtime state cần được quản lý.

Một số flags liên quan:

- `-XX:ReservedCodeCacheSize`.
- `-XX:InitialCodeCacheSize`.
- `-XX:+TieredCompilation`.
- Các tùy chọn compiler thread hoặc compilation threshold theo JDK.

Nếu thay code cache size hoặc compiler configuration khi restore, không nên giả định mã đã biên dịch và trạng thái compiler sẽ tự được chuyển đổi phù hợp. Hãy giữ cấu hình đã tạo checkpoint hoặc tạo ảnh mới sau khi thay đổi.

Warm-up cũng ảnh hưởng lượng code cache được sử dụng. Nếu workload làm nóng quá nhiều đường code hiếm, checkpoint có thể chứa nhiều mã JIT hơn mức cần thiết. Cần đo lợi ích latency với kích thước ảnh và memory footprint, không chỉ cố làm nóng càng nhiều method càng tốt.

## 9. Metaspace, direct memory và thread stack

Heap không phải vùng memory duy nhất bị ảnh hưởng bởi flags.

### 9.1. Metaspace

Metaspace lưu class metadata. Những flags như `-XX:MetaspaceSize` và `-XX:MaxMetaspaceSize` có thể ảnh hưởng hành vi quản lý metadata. Ứng dụng dùng nhiều classloader, proxy hoặc dynamic class generation cần theo dõi metaspace và class unloading.

Checkpoint giữ trạng thái class metadata của tiến trình. Không nên thay cấu hình metaspace hoặc bộ classpath tùy tiện khi restore.

### 9.2. Direct memory

NIO direct buffer và một số thư viện native sử dụng memory ngoài heap. `-XX:MaxDirectMemorySize` có thể giới hạn lượng direct buffer mà ứng dụng sử dụng. Nếu container restore có memory limit thấp hơn, direct memory và native allocation có thể làm instance vượt giới hạn dù heap vẫn còn trống.

### 9.3. Thread stack

`-Xss` ảnh hưởng stack size của thread Java mới. Thread đã tồn tại khi checkpoint có stack state riêng trong tiến trình. Thay đổi stack size khi restore không biến đổi stack đã được lưu của các thread hiện hữu; nó có thể chỉ ảnh hưởng cách tạo thread mới theo runtime và cần được kiểm tra với JDK cụ thể.

Hãy giữ thread configuration ổn định, drain những task không cần tồn tại qua checkpoint và xác minh số thread sau restore.

## 10. Java agent, native agent và instrumentation

Các agent có thể thay đổi bytecode, instrument class, tạo thread hoặc cấp phát native memory. Chúng có thể ảnh hưởng class loading và runtime state trước checkpoint.

Ví dụ:

- APM agent.
- Profiler.
- Coverage agent.
- Bytecode instrumentation agent.
- Native agent dùng `-agentlib` hoặc `-agentpath`.

Nếu tạo checkpoint với một agent nhưng restore bằng binary hoặc cấu hình agent khác, trạng thái instrumentation và runtime có thể không khớp. Hãy cố định agent version, checksum và flags. Nếu agent không hỗ trợ CRaC hoặc không có hướng dẫn restore, cần kiểm tra khả năng tương thích trước khi đưa vào image.

Một số agent có thể cần callback hoặc hook riêng để đóng socket, flush telemetry và khởi động lại exporter. Không nên giả định JVM tự xử lý mọi tài nguyên của agent chỉ vì tiến trình được checkpoint.

## 11. System properties và môi trường khởi chạy

Các system properties như timezone, locale, encoding, profile hoặc cấu hình framework có thể đã được đọc và sao chép vào object trong heap. Nếu restore với giá trị khác, ứng dụng có thể có trạng thái lai: object đã khởi tạo giữ giá trị cũ trong khi component lazy đọc giá trị mới.

Ví dụ:

```bash
java \
  -Duser.timezone=UTC \
  -Dfile.encoding=UTF-8 \
  -Dspring.profiles.active=production \
  -Xms512m \
  -Xmx2g \
  -XX:+UseG1GC \
  -jar app.jar
```

Các giá trị trên chỉ minh họa. Nếu thay timezone hoặc Spring profile sau restore, những bean đã được tạo trước checkpoint có thể không tự thay đổi. Nếu cần cấu hình động, hãy thiết kế một lifecycle refresh rõ ràng thay vì dựa vào việc thay environment variable.

Không phải system property nào cũng ảnh hưởng layout JVM, nhưng chúng có thể ảnh hưởng hành vi ứng dụng. Vì vậy, nên ghi lại launch configuration và giữ nhất quán theo release.

## 12. Tạo compatibility manifest cho heap, GC và JVM flags

Mỗi checkpoint release nên lưu thông tin cấu hình đủ để nhận diện chính xác runtime đã tạo ảnh.

Ví dụ:

```yaml
runtime:
  vendor: "<jdk-vendor>"
  version: "<java-runtime-version>"
  build: "<jdk-build-number>"
  vmName: "<jvm-name>"
  architecture: amd64

heap:
  initial: 512m
  maximum: 2g
  compressedOops: true
  compressedClassPointers: true
  objectAlignment: "<effective-value>"

gc:
  collector: G1
  flagsFile: jvm-flags.txt
  flagsSha256: "<flags-file-sha256>"

memory:
  maxMetaspace: "<effective-value>"
  maxDirectMemory: "<effective-value>"
  reservedCodeCache: "<effective-value>"
  threadStackSize: "<effective-value>"

container:
  memoryLimit: 3Gi
  cpuLimit: "2"
  imageDigest: "sha256:<image-digest>"

checkpoint:
  createdWithRuntime: "<same-runtime-identifier>"
  path: /var/lib/app/checkpoint
```

Các giá trị trong dấu ngoặc nhọn là placeholder. Pipeline cần lấy giá trị thực tế từ JVM và môi trường đã tạo checkpoint. Không suy đoán giá trị effective từ file cấu hình.

### 12.1. Ghi lại effective flags

Có thể lưu output của:

```bash
java -XX:+PrintFlagsFinal -version > effective-flags.txt 2>&1
```

Và với tiến trình đã chạy:

```bash
jcmd <pid> VM.flags -all > process-flags.txt
jcmd <pid> VM.command_line > process-command-line.txt
jcmd <pid> VM.version > process-version.txt
```

Hãy tạo checksum cho các file này và lưu cùng manifest. Một số flags có thể có giá trị khác giữa startup và lúc checkpoint nếu chúng được thay đổi động; nếu có, ghi rõ thời điểm và giá trị cuối cùng.

## 13. Quy trình thay đổi heap hoặc GC an toàn

Nếu cần tăng heap, đổi collector hoặc điều chỉnh flags, hãy coi đó là một cấu hình runtime mới.

Quy trình đề xuất:

1. Tạo release configuration mới với JDK build và JVM flags đã chọn.
2. Khởi chạy ứng dụng mới từ đầu bằng cấu hình đó.
3. Kiểm tra effective flags, heap, GC và container memory.
4. Chạy workload warm-up đại diện.
5. Đo latency, throughput, allocation, GC pause và memory footprint.
6. Xác nhận ứng dụng đạt tiêu chí warm-up và resource có thể drain.
7. Tạo checkpoint mới.
8. Restore thử bằng đúng JDK, flags và container image mới.
9. Đo restore-to-ready và kiểm tra dưới tải.
10. Chỉ promote release mới sau khi kiểm thử thành công.

Không nên sửa `-Xmx` trong deployment manifest rồi tiếp tục sử dụng checkpoint cũ mà không kiểm tra. Việc thay cờ khởi động không thay đổi trạng thái heap đã lưu trong ảnh.

### 13.1. Ví dụ thay đổi cấu hình

Giả sử release cũ dùng:

```bash
-Xms512m -Xmx2g -XX:+UseG1GC
```

Sau khi đo tải, nhóm vận hành muốn dùng:

```bash
-Xms1g -Xmx3g -XX:+UseZGC
```

Đây là thay đổi cả heap sizing lẫn collector. Cách triển khai nên là khởi chạy ứng dụng mới với cấu hình mới, warm-up lại, tạo checkpoint mới và phát hành một bundle mới. Không ghép ảnh cũ với lệnh restore mới chỉ vì JAR không thay đổi.

## 14. Thay đổi flags nào có thể chấp nhận?

Không có một quy tắc chung áp dụng cho mọi JDK distribution. Một số tùy chọn được dùng để điều khiển restore, một số chỉ ảnh hưởng logging/diagnostics, một số là startup-only và một số thay đổi trạng thái runtime quan trọng.

| Loại thay đổi | Cách xử lý |
| --- | --- |
| Thay `-Xms` hoặc `-Xmx` | Giữ nguyên; nếu cần đổi, tạo checkpoint mới trừ khi tài liệu JDK xác nhận rõ trường hợp được hỗ trợ |
| Đổi GC collector | Không dùng ảnh cũ; tạo checkpoint mới với collector mới |
| Đổi object layout/compressed pointers | Giữ nguyên giá trị hiệu lực; tạo ảnh mới khi thay đổi |
| Đổi code cache/compiler flags | Giữ nguyên trừ khi có hướng dẫn cụ thể và kiểm thử |
| Đổi module access hoặc classpath | Xem là thay đổi runtime/application bundle; tạo checkpoint mới |
| Đổi agent/native library | Pin cùng binary và cấu hình; nếu thay đổi, tạo và kiểm thử ảnh mới |
| Bật/tắt logging hoặc JFR | Kiểm tra flags nào được hỗ trợ tại restore và ảnh hưởng của agent/runtime; không tự suy luận |
| Thay system property của ứng dụng | Đánh giá object đã khởi tạo; refresh có kiểm soát hoặc tạo ảnh mới |
| Thay checkpoint/restore path | Theo cú pháp và giới hạn của JDK CRaC cụ thể |

Nếu nhà cung cấp JDK công bố một tùy chọn được phép khác giữa checkpoint và restore, hãy ghi nhận ngoại lệ đó trong manifest và test bằng đúng bản build. Không lấy tài liệu của một JDK khác làm bằng chứng cho runtime đang triển khai.

## 15. Kiểm tra lỗi liên quan tới heap, GC và flags

Khi restore thất bại, cần phân loại lỗi theo lớp thay vì thay nhiều flags cùng lúc.

| Dấu hiệu | Nguyên nhân có thể | Việc cần kiểm tra |
| --- | --- | --- |
| JVM báo unrecognized hoặc unsupported option | JDK restore không hỗ trợ flag hoặc flag đã đổi tên | Vendor, version, build và tài liệu của runtime |
| Restore thất bại khi dùng heap sizing khác | Heap configuration không tương thích với trạng thái ảnh hoặc môi trường thiếu memory | So sánh `-Xms`, `-Xmx`, container limit và effective flags |
| Lỗi liên quan GC hoặc memory mapping | Collector/build hoặc trạng thái memory không tương thích | Collector, GC flags, JDK build và kernel |
| Process restore được nhưng OOM sau đó | Memory limit thấp, native memory hoặc workload vượt dự kiến | Heap, metaspace, direct memory, thread stack, code cache và cgroup |
| GC pause tăng mạnh sau restore | Heap/GC sizing không phù hợp với workload hoặc môi trường mới | GC logs/JFR, allocation rate và collector configuration |
| Code cache hoặc compilation bất thường | Compiler flags, JDK build hoặc warm-up khác | Effective compiler flags, code cache usage và JFR |
| Native agent lỗi sau restore | Agent không hỗ trợ checkpoint/restore hoặc binary khác | Agent version, checksum, native dependencies và lifecycle hook |
| Hành vi ứng dụng khác dù process restore thành công | System properties hoặc cấu hình object đã khởi tạo không khớp | Launch config, Spring profile, timezone và config refresh |

Giữ log của JVM, CRIU và ứng dụng. Không bỏ qua lỗi resource hoặc tiếp tục phục vụ chỉ vì process đã xuất hiện sau restore.

## 16. Kiểm thử tương thích theo ma trận cấu hình

Khi hỗ trợ nhiều profile triển khai, nên tạo ma trận cho các cấu hình được phép. Mỗi profile phải được tạo checkpoint và restore bằng đúng runtime tuple.

| Thành phần | Giá trị cần cố định | Kiểm tra |
| --- | --- | --- |
| JDK | Vendor, version, build | Restore bằng đúng build |
| Heap | `-Xms`, `-Xmx`, các giới hạn heap | So sánh effective flags và memory footprint |
| GC | Collector và GC tuning flags | Checkpoint/restore rồi chạy workload đại diện |
| Object layout | Compressed pointers, alignment | So sánh effective flags |
| Native memory | Metaspace, direct memory, code cache | Đo memory sau restore và dưới tải |
| Thread | Stack size, worker count, compiler threads | Kiểm tra thread state và resource usage |
| Agents | Binary version và arguments | Restore và kiểm tra agent lifecycle |
| Container | Image digest, memory/CPU limit | Restore trong đúng container constraints |
| OS | Kernel, architecture, CRIU | `criu check` và smoke test thực tế |

### 16.1. Smoke test tối thiểu

Với mỗi profile:

1. Khởi chạy bằng JDK và flags đã pin.
2. Lưu effective flags và runtime version.
3. Chạy warm-up workload.
4. Tạo checkpoint.
5. Restore bằng đúng JDK build và container configuration.
6. Xác nhận callback resource và health/readiness.
7. Chạy workload đại diện sau restore.
8. Đo heap, GC, CPU, native memory và latency.

### 16.2. Kiểm tra âm tính

Thử nghiệm có kiểm soát với một JDK hoặc flags không khớp có thể giúp xác nhận release validation từ chối tổ hợp sai trước khi gọi restore. Không cần cố tình chạy một tổ hợp không được hỗ trợ trong môi trường production.

## 17. Quy tắc quản lý release

Mỗi checkpoint release nên bất biến. Không ghi đè ảnh cũ khi thay đổi heap hoặc GC configuration. Gắn checkpoint với:

- JDK vendor/version/build.
- Application version và checksum.
- Dependency/classpath digest.
- Effective JVM flags.
- Heap và GC configuration.
- Container image digest.
- OS/kernel/architecture và CRIU version.
- Resource configuration cần thiết để restore.

Khi phát hành cấu hình mới, giữ lại bundle trước đó để rollback. Rollback phải khôi phục đúng cặp runtime và checkpoint, không chỉ đổi JVM flags hoặc container tag.

## 18. Kết luận

Heap, GC và nhiều cờ JVM ảnh hưởng trực tiếp tới trạng thái runtime được lưu trong checkpoint. `-Xms`, `-Xmx`, collector, object layout, code cache, metaspace, direct memory, thread stack và agent configuration cần được quản lý cùng JDK build đã tạo ảnh.

Hãy ghi lại effective flags, pin JDK vendor/version/build và giữ nguyên cấu hình khi restore. Nếu cần thay đổi heap, collector hoặc cờ ảnh hưởng cấu trúc runtime, hãy khởi chạy ứng dụng mới, warm-up lại và tạo checkpoint mới. Chỉ áp dụng ngoại lệ khi tài liệu của đúng bản phân phối JDK xác nhận rõ khả năng tương thích và tổ hợp đã được kiểm thử. Cách quản lý theo release bundle giúp tránh ghép sai trạng thái JVM với cấu hình mới và làm cho quá trình restore có thể tái hiện.

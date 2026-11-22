# Tính sẵn có của bộ thu gom phụ thuộc bản phân phối, phiên bản và nền tảng

**Không có một danh sách bộ thu gom rác (garbage collectors, GC) dùng được trên mọi chương trình Java và mọi môi trường.** Java SE quy định cách chương trình phải hoạt động, nhưng không bắt buộc tất cả Java Virtual Machine (JVM) triển khai **Serial, Parallel, G1, ZGC, Shenandoah, CMS** hoặc dùng chung một bộ cờ điều khiển. Một collector có thể tồn tại trong mã nguồn OpenJDK nhưng **không được build** vào một bản phân phối, có trong binary nhưng **không khả dụng** trên hệ điều hành/CPU cụ thể, hoặc khả dụng nhưng **không được chọn mặc định**.

Đề bài thuộc nhóm **các bộ thu gom JVM**: mục đích ở đây không phải xếp hạng thuật toán GC nào tốt nhất, mà là giải thích **làm sao xác định một collector có sẵn, có dùng được và đang thực sự hoạt động trên chính runtime sẽ triển khai**.

Quy tắc thực hành quan trọng nhất:

> **Dùng binary Java thật để xác minh.** Ghi nhận vendor/VM implementation, JDK version, OS/architecture, build options, runtime flags và logs. Đừng sao chép cấu hình GC từ một máy hoặc một bài viết sang môi trường khác mà không kiểm tra.

## 1. Sáu chiều quyết định collector có dùng được không

Một tính năng GC có thể bị giới hạn ở một hoặc nhiều tầng:

| Chiều | Câu hỏi cần xác minh | Ví dụ |
| --- | --- | --- |
| **JVM implementation** | JVM là HotSpot, OpenJ9, Native Image runtime hay thứ khác? | `-XX:+UseG1GC` là cờ HotSpot; OpenJ9 dùng GC policies riêng |
| **Distribution / vendor** | Binary nào được phát hành, đóng gói và hỗ trợ? | Hai vendors cùng OpenJDK major version có thể có GC build options khác |
| **JDK release** | GC đã được giới thiệu, production-ready, deprecated hay removed? | ZGC generational thay đổi qua JDK 21/23/24 |
| **OS và CPU architecture** | Port này có backend và yêu cầu hệ thống cần thiết không? | OS, x86-64/AArch64, giới hạn address space |
| **Build/feature flags** | Collector có được compile vào VM này và được phép bật không? | Shenandoah có thể thiếu trong một số builds |
| **Runtime resource/configuration** | Collector có khởi động với heap, CPU, page/VM constraints hiện tại không? | Một GC low-latency có thể yêu cầu dung lượng heap/nền tảng phù hợp |

Thêm một chiều thứ bảy là **vòng đời hỗ trợ (support policy)**: vendor có thể phát hành binary nhận một flag nhưng không cung cấp cùng mức hỗ trợ thương mại, security fixes hoặc backports như distribution khác.

### Bốn cấp độ “có sẵn” phải phân biệt

1. **Có trong tài liệu/thiết kế:** thuật toán đã được mô tả, có JEP hoặc reference implementation.
2. **Có trong binary:** collector thực sự được build và có cơ chế cấu hình tương ứng.
3. **Khởi động thành công trong deployment này:** option và ràng buộc OS/CPU/heap cho phép VM đi vào trạng thái chạy hợp lệ.
4. **Đang được chọn/sử dụng:** JVM này đã chọn collector đó ở process hiện tại, qua flags/default ergonomics.

Một collector có thể ở cấp 1 nhưng không đạt cấp 2. Có flag được nhận diện chưa đủ chứng minh startup đạt cấp 3; danh sách flags được hỗ trợ chưa nói collector nào đang chạy ở cấp 4.

## 2. Java SE không chuẩn hóa danh mục collector hay `-XX` flags

`java.lang.System.gc()` là API Java SE, nhưng các GC algorithms cụ thể nằm ở tầng implementation. Java ứng dụng không có phương thức Java SE chuẩn dạng:

```text
GarbageCollector.select("Shenandoah");
```

Dòng trên **là ký hiệu minh họa, không phải Java API**. Việc chọn collector trong HotSpot thường diễn ra **khi JVM khởi động** bằng flags, hoặc do **ergonomics** chọn mặc định. Không chuyển collector tùy ý lúc process đang chạy như thay một biến Java.

Cú pháp:

```bash
java -XX:+UseG1GC MyApp
```

có ý nghĩa khi binary JVM **hỗ trợ cờ HotSpot** đó. Cùng chương trình bytecode, nếu chạy trên **OpenJ9**, cách chọn GC và chính sách khác. Nếu biên dịch thành **GraalVM Native Image**, tiến trình sau đó **không chạy trên HotSpot JVM thông thường**, nên phải xem chính sách GC của Native Image.

**Khác biệt tên:** `Java 17` mô tả phiên bản Java platform; `HotSpot 17` nói tới implementation tương ứng; `Temurin 17` hoặc `Oracle JDK 17` mô tả distribution. Không được biến tất cả thành các nhãn đồng nghĩa.

## 3. HotSpot: các lựa chọn quen thuộc và điều kiện hỗ trợ

Trên những build HotSpot JDK 17 phổ biến, những collectors thường được nhắc tới:

| Collector | Cờ chọn trong HotSpot | Tình trạng cần kiểm tra |
| --- | --- | --- |
| **Serial GC** | `-XX:+UseSerialGC` | Một GC worker, generational/traditional STW; thường sẵn trong build HotSpot thông dụng |
| **Parallel GC** | `-XX:+UseParallelGC` | Throughput collector với nhiều GC workers; thường sẵn |
| **G1 GC** | `-XX:+UseG1GC` | Collector theo regions, được chọn mặc định trong nhiều cấu hình HotSpot hiện đại |
| **ZGC** | `-XX:+UseZGC` | Low-latency collector; hỗ trợ phụ thuộc JDK release, OS/architecture, build và heap constraints |
| **Shenandoah** | `-XX:+UseShenandoahGC` | Concurrent collector; **không có trong mọi HotSpot binary** dù có trong OpenJDK sources |
| **Epsilon GC** | `-XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC` | No-op collector phục vụ thử nghiệm, có thể không được build/bật; **không thu gom object** |
| **CMS (đã loại bỏ)** | `-XX:+UseConcMarkSweepGC` ở JDK cũ | Đã **removed khỏi upstream HotSpot từ JDK 14**, không phải option collector hợp lệ ở JDK 17 chuẩn |

Bảng phân biệt **hướng dẫn kiểm tra**, không phải cam kết availability trên mọi vendor build, JDK minor release, processor architecture hoặc VM port. Các collector có thể giới hạn heap size, hỗ trợ nén pointers, cách xử lý large pages, page mapping hoặc các yêu cầu khác.

### Mặc định không đồng nghĩa luôn dùng G1

G1 là default trong **nhiều** cấu hình HotSpot từ JDK 9, nhưng JVM ergonomics có thể chọn khác tùy CPU count, memory, kiểu VM hoặc cấu hình môi trường. Vì vậy:

- **Không truyền flag** nghĩa là **để VM chọn**, không phải một lời tuyên bố collector mặc định giống nhau ở mọi nơi.
- **Truyền `-XX:+UseG1GC`** thể hiện yêu cầu cụ thể và có thể bị từ chối nếu binary không hỗ trợ.
- **Log startup hoặc flags thực tế** mới xác nhận collector đã chọn.

Không suy từ việc máy có nhiều cores rằng G1 chắc chắn chạy, hay từ container nhỏ rằng Serial chắc chắn chạy.

## 4. Phiên bản JDK làm thay đổi tập collectors

Tính sẵn có của bộ thu gom là một **tính chất theo thời gian**. Một ví dụ điển hình: **ZGC**.

| Mốc upstream OpenJDK/HotSpot | Thay đổi GC đáng chú ý | Ý nghĩa |
| --- | --- | --- |
| **JDK 9** | G1 trở thành default trong các cấu hình HotSpot thông dụng; CMS deprecated | Bài viết JDK 8 về defaults không còn áp dụng nguyên xi |
| **JDK 11** | ZGC và Epsilon được đưa vào theo hướng experimental ở những builds/platforms phù hợp | Cần chú ý experimental/support flags |
| **JDK 12** | Shenandoah được tích hợp theo trạng thái experimental tại những builds có hỗ trợ | Không thể đồng nhất “trong OpenJDK” với “mọi distribution có binary” |
| **JDK 14** | CMS bị loại khỏi upstream HotSpot | `UseConcMarkSweepGC` không còn chọn CMS trên HotSpot 17 |
| **JDK 15** | ZGC và Shenandoah được đưa thành production features ở phạm vi ports/builds hỗ trợ | Không có nghĩa mọi OS/CPU đều có cả hai |
| **JDK 21** | Generational ZGC được giới thiệu theo mode lựa chọn | Cần phân biệt non-generational ZGC và generational ZGC |
| **JDK 23** | Generational ZGC là mode mặc định khi chọn ZGC; mode cũ bị deprecated | Flags/mode thay đổi |
| **JDK 24** | Non-generational ZGC bị loại khỏi upstream JDK | Cấu hình legacy `ZGenerational` không nên sao chép lên bản mới |

**Đọc đúng bảng:** đây là những mốc **upstream** đã được ghi nhận, không cam kết vendors không backport hoặc phát hành patchset riêng. Chẳng hạn một distribution mang số major cũ có thể chứa một GC backport, nhưng bạn phải xác minh bằng release notes/build và chạy thử; **không nên mặc định có backport**.

### 4.1. Trường hợp ZGC chi tiết

Trên một HotSpot JDK 17 phù hợp, dùng `-XX:+UseZGC` lựa chọn **ZGC non-generational** thời kỳ đó. Về các phiên bản sau:

- **JDK 21:** Generational ZGC xuất hiện (JEP 439), có thể chọn bằng `-XX:+UseZGC -XX:+ZGenerational`.
- **JDK 23:** Generational ZGC thành mode mặc định (JEP 474); chuyển trạng thái hỗ trợ mode cũ.
- **JDK 24:** non-generational mode bị loại bỏ (JEP 490). Không tiếp tục dùng `-XX:-ZGenerational` với ý định trở về thuật toán cũ.
- **JDK 25+:** hãy đọc tài liệu phiên bản đang dùng; đừng cố giữ nguyên một flag chỉ vì từng được dùng trên JDK 21.

**Quan trọng:** Collector “ZGC” tồn tại ở cả hai releases không có nghĩa **thuật toán, generation policy, cờ điều khiển và memory behavior** giống hệt. Nếu migration guide nói `ZGenerational` obsolete/removed, hãy thay đổi cấu hình tương ứng thay vì bỏ qua cảnh báo.

### 4.2. Trường hợp Shenandoah

Shenandoah là low-pause/concurrent GC được tích hợp trong upstream OpenJDK, nhưng có sự khác biệt **những distribution thực sự build/include nó**. Khi gặp thông báo “Shenandoah GC is not supported” hay “option not available” trong một JDK, không được suy rằng **mọi OpenJDK JDK 17** đều thiếu Shenandoah.

Cách xác minh: xem vendor release notes, dùng startup option trên binary đích, kiểm tra exit code và log. Một số JDK đời cũ còn cần mở experimental options trước `UseShenandoahGC`. Không thêm `-XX:+UnlockExperimentalVMOptions` bừa nếu JDK đã coi feature là production; dùng đúng documentation của bản build.

### 4.3. CMS là trường hợp đã bị removed

**Concurrent Mark-Sweep (CMS)** xuất hiện trong các HotSpot JDK cũ, deprecated từ JDK 9 và **removed từ JDK 14** theo JEP 363. Nếu tài liệu production cũ chứa:

```text
-XX:+UseConcMarkSweepGC
-XX:+CMSParallelRemarkEnabled
-XX:CMSInitiatingOccupancyFraction=...
```

đây là **flags lịch sử để nhận diện cấu hình**, không phải bộ lệnh đề nghị dùng ở JDK 17+. Khi migrate, cần chọn collector đang được hỗ trợ và **đánh giá workload lại**, không thay chuỗi `CMS` thành `G1` trong mọi flag rồi coi như giữ nguyên semantics.

## 5. “Distribution” và “implementation” là hai khái niệm

Java có nhiều vendors/distributions. Một số distributions dựa trên **HotSpot/OpenJDK**, một số dựa trên **OpenJ9**, hoặc cung cấp runtime khác. Vendor có thể thay đổi packaging, patches, build configurations và support matrix theo release.

Ví dụ các tên bạn có thể thấy trong thực tế:

- **Oracle JDK, Eclipse Temurin, Microsoft Build of OpenJDK, Red Hat build of OpenJDK, Amazon Corretto**: phần lớn các dòng phát hành liên quan sử dụng HotSpot/OpenJDK, nhưng **phải kiểm tra binary thật**, đừng dựa vào logo/vendor name cho mọi product.
- **IBM Semeru Runtime với OpenJ9** và các OpenJ9-based runtimes: có **chính sách GC và flags khác HotSpot**.
- **GraalVM chạy Java trên JVM**: trong trường hợp JVM mode có thể sử dụng HotSpot-based runtime; cần xem mode và bản phân phối.
- **GraalVM Native Image**: chạy executable native với runtime riêng, **không phải JDK HotSpot đang chạy các `-XX:+Use...GC` tùy ý**.
- **Android ART**: có runtime/garbage collector riêng; không mặc định hỗ trợ HotSpot flags dù ứng dụng được viết bằng Java/Kotlin.

Các tên ở đây để minh họa **các họ môi trường**, không phải tuyên bố tính năng GC cố định cho mọi bản sản phẩm cùng thương hiệu.

### Vendor support không bằng availability

Một binary có thể khởi động với collector experimental nhưng vendor không cung cấp cùng mức SLA/hỗ trợ vận hành như collector production. Nếu dùng production, kiểm tra:

1. Release notes và danh sách feature của distribution.
2. Platform support matrix (OS/CPU và container).
3. Có cần experimental/diagnostic unlock flags hay không.
4. Collector có được vendor support lâu dài không.
5. Những giới hạn heap, compressed references, virtual memory và GC logging.
6. Thay đổi giữa update releases trong cùng major version.

Không dùng “bật flag chạy được trên laptop” để tự suy rằng vendor cam kết hỗ trợ trong production container.

## 6. OpenJ9 không dùng danh sách flags GC của HotSpot

**Eclipse OpenJ9** là một JVM implementation khác. Các GC policies của nó được lựa chọn điển hình bằng:

```bash
java -Xgcpolicy:gencon MyApp
```

Một số policies trong tài liệu OpenJ9 gồm:

| OpenJ9 policy | Đặc điểm tổng quát | Hạn chế/ghi chú |
| --- | --- | --- |
| `gencon` | Generational concurrent; nursery/tenure | Thường là default trong OpenJ9 docs |
| `balanced` | Regions, nhiều phần heap; hướng tới cân bằng pause/throughput | Một số bản chỉ hỗ trợ 64-bit |
| `optthruput` | Hướng tới throughput, STW collection truyền thống | Không tự suy nó chính là HotSpot Parallel GC |
| `optavgpause` | Hướng tới average pause time qua những cơ chế riêng | Không thể dùng tên này trên HotSpot theo mặc định |
| `metronome` | Real-time/incremental trong các cấu hình phù hợp | Có hạn chế architecture/platform; xem docs theo bản |
| `nogc` | Không thực hiện GC cycles | Chỉ cho các workload/thử nghiệm rất đặc thù |

Các policies này **không** là tên thay thế 1-1 của Serial/Parallel/G1/ZGC/Shenandoah. Ví dụ `gencon` không có nghĩa bạn đang chạy G1; hai collectors có thể đều generational nhưng thuật toán và cấu trúc heap khác nhau.

### Phát hiện JVM implementation trước khi chọn GC

Dùng:

```bash
java -version
java --version
```

Trên những bản Java hiện đại, output có thể chứa `OpenJDK 64-Bit Server VM`, `Eclipse OpenJ9 VM` hoặc các nhãn khác. Không hard-code toàn bộ chuỗi version là một format tiêu chuẩn bắt buộc.

Nếu đã xác định JVM là OpenJ9, đọc **OpenJ9 GC policy docs và `java -Xgcpolicy:help`/`-Xhelp` nếu binary hỗ trợ**. Không đưa `-XX:+UseZGC` vào ứng dụng OpenJ9 rồi xem lỗi “unrecognized option” là một bug của Java.

### Ví dụ câu lệnh không portable

```text
HotSpot: java -XX:+UseG1GC MyApp
OpenJ9:  java -Xgcpolicy:gencon MyApp
```

Chúng **không có nghĩa giống nhau**, chỉ đều là những ví dụ cấu hình collector hợp lệ khi đúng implementation hỗ trợ. Cùng bytecode `MyApp.class` có thể chạy trên cả hai JVM nhưng flags tối ưu ở startup **không thể copy y nguyên**.

## 7. GraalVM: phải tách JVM mode và Native Image

Tên “GraalVM” dễ làm người học trộn **một JVM runtime** với **native executable tạo bởi Native Image**.

### 7.1. Chạy Java bytecode trên JVM

Nếu dùng một Java launcher tương thích HotSpot trong GraalVM distribution để chạy `java MyApp`, GC options phải đối chiếu theo JVM implementation/build/version thực tế. Không phải cứ có Graal JIT compiler thì garbage collector cũng chuyển thành một thuật toán có tên “Graal GC”.

### 7.2. Build và chạy Native Image

**Native Image** biên dịch ứng dụng Java thành một **native executable** dùng runtime memory management riêng. Ví dụ tài liệu Native Image mô tả:

- **Serial GC** là default trong nhiều bản Native Image.
- **G1** và **Epsilon** có thể có availability phụ thuộc edition/version/OS/architecture.
- Cấu hình builder có dạng `native-image --gc=serial ...` hoặc `--gc=G1` khi mode đó được hỗ trợ.

```bash
native-image --gc=serial HelloApp
```

Đây là **ví dụ lựa chọn GC ở build time**, chỉ chạy khi đã cài Native Image tool và có class/application `HelloApp` hợp lệ. Không được suy rằng native binary có thể được đổi collector bằng:

```text
./helloapp -XX:+UseZGC
```

Dòng trên **chỉ để nêu sai lầm**, không phải lệnh khuyến nghị. Tham số `-XX:+UseZGC` của HotSpot không có nghĩa tự động trên runtime Native Image. Hãy tra chính xác **Native Image memory management và build options** của edition/release đang dùng.

**Điểm dễ nhầm:** tên “Serial GC” xuất hiện cả trong HotSpot và Native Image không chứng minh hai runtime có cùng heap layout, collection phases hay flags.

## 8. Hệ điều hành và kiến trúc CPU có thể loại trừ một GC

Dù JVM có cùng version nguồn, không phải collector nào cũng có port/implementation bằng nhau trên:

- Windows, Linux, macOS và các Unix variants.
- x86-64/AMD64, AArch64/ARM64, PPC64, s390x và những kiến trúc khác.
- 32-bit so với 64-bit.
- Các mức hỗ trợ virtual-memory reservation, OS page mapping và CPU instructions.
- Containers với memory cgroups, CPU quotas, page sizes và security restrictions.

**Ví dụ tư duy:** một GC concurrent/low-latency có thể cần các khả năng quản lý virtual memory hoặc address space mà một OS/CPU port chưa hỗ trợ. Khi đó cờ `Use...GC` có thể tồn tại trong tài liệu cấp dự án nhưng binary trên nền tảng đích từ chối startup.

Không đưa một bảng “ZGC luôn hỗ trợ Windows/AArch64” hoặc “Shenandoah không bao giờ hỗ trợ macOS” mà không gắn **release/build/version** cụ thể, vì ports tiếp tục được mở rộng. Đúng hơn là **chạy test trên image/container/VM thực tế** và đọc support matrix của vendor.

### Container không đổi JVM implementation, nhưng đổi môi trường

Một image Docker có thể:

- Dùng **JRE/JDK khác** laptop dù đều in “Java 17”.
- Sử dụng OS libc/architecture khác.
- Chạy với ít CPU quotas và heap limit.
- Dùng binary JVM biên dịch với những features khác.
- Bị giới hạn PID, page mapping hoặc tài nguyên native memory.

Do đó collector hoạt động trên laptop **không được coi là đã kiểm chứng trên container**. Chạy cùng các lệnh kiểm tra **bên trong image/container production**, không chỉ trên máy host.

## 9. Tài liệu nói collector có sẵn, vì sao JVM vẫn từ chối?

Các lỗi nên phân loại trước khi sửa:

| Triệu chứng startup | Ý nghĩa khả dĩ | Điều cần làm |
| --- | --- | --- |
| `Unrecognized VM option 'UseShenandoahGC'` | Flag không được nhận diện trong binary hiện tại | Kiểm tra VM implementation/version/build |
| `Unrecognized VM option 'UseConcMarkSweepGC'` | Flag đã bị removed trên release này | Migrate off CMS flags |
| `Unrecognized option: -Xgcpolicy:gencon` | Dùng flag OpenJ9 với HotSpot | Chọn syntax đúng JVM |
| `Option ... is experimental and must be enabled via UnlockExperimentalVMOptions` | Feature hiện dưới trạng thái experimental trên bản đó | Tra docs rồi bật unlock **khi có hỗ trợ** |
| `... is not supported on this platform` | Có flag/collector nhưng port hiện không phù hợp | Kiểm tra vendor platform matrix |
| `Error occurred during initialization of VM` | JVM thất bại lúc khởi tạo, nguyên nhân có thể do heap/GC/flag conflicts | Đọc **dòng nguyên nhân kế tiếp**, không chỉ tiêu đề |
| JVM chạy nhưng không thấy GC mong đợi | Default ergonomics hoặc option chưa được truyền vào đúng process | Xem startup logs và VM.flags |
| Warning “Ignoring option...” | Flag obsolete/removed/không còn hiệu lực | Sửa cấu hình; **không coi warning là chọn collector thành công** |

Nội dung thông báo trong bảng là **mẫu phân loại**, không cam kết wording đầy đủ ở mọi HotSpot/OpenJ9 build. Có trường hợp VM chấp nhận syntax rồi từ chối khởi tạo vì ràng buộc bộ nhớ hoặc option xung đột.

### Không sử dụng `IgnoreUnrecognizedVMOptions` để che sai cấu hình GC

Một số HotSpot cho phép:

```text
-XX:+IgnoreUnrecognizedVMOptions
```

Điều này có thể khiến cấu hình sai **không làm startup fail** và collector bạn tưởng đã bật **không được chọn**. Trong vận hành cần GC policy xác định, việc bỏ qua unknown flags là nguy hiểm: app vẫn chạy, nhưng latency và footprint khác kỳ vọng.

Ưu tiên **fail fast**, ghi flag selection và kiểm tra collector đang hoạt động. Chỉ dùng cơ chế bỏ qua unknown flags khi có lý do quản lý tương thích rõ ràng và đã xác nhận hành vi dự phòng.

## 10. Quy trình kiểm tra trên runtime thật

Không cần viết ứng dụng phức tạp để bước đầu phân biệt availability. Với JDK/launcher thực tế:

### Bước 1 — Nhận diện binary

```bash
java -version
java --version
```

Ghi lại **full build string**, vendor và VM name. Nếu có nhiều `java` trong hệ thống, đảm bảo command được gọi từ **đúng `PATH`** hoặc đường dẫn absolute. Đừng lấy version của `javac` ở máy host để suy version `java` trong container.

### Bước 2 — Kiểm tra collector mặc định

Trên **HotSpot** hỗ trợ unified logging:

```bash
java -Xlog:gc=info -version
```

Tìm dòng mô tả collector được chọn, ví dụ `Using G1` hoặc `Using Serial`; đây chỉ là mẫu wording/log, không phải stdout cam kết. Nếu VM không hỗ trợ `-Xlog`, dùng hướng dẫn tương ứng vendor.

### Bước 3 — Thử khởi động với một collector cụ thể

Trên HotSpot, thử **một flag tại mỗi lần chạy**, không gom bốn `Use...GC` flags xung đột:

```bash
java -XX:+UseSerialGC -Xlog:gc=info -version
java -XX:+UseParallelGC -Xlog:gc=info -version
java -XX:+UseG1GC -Xlog:gc=info -version
java -XX:+UseZGC -Xlog:gc=info -version
java -XX:+UseShenandoahGC -Xlog:gc=info -version
```

Đây là **các thử nghiệm riêng**, không phải danh sách câu lệnh được đảm bảo thành công. Nếu một lệnh báo lỗi trên JVM đích, **ghi lỗi**, không giả định flag/collector có mặt. Với Epsilon experimental (chỉ khi JDK hỗ trợ):

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -version
```

**Epsilon không làm GC:** không dùng làm collector production cho workload cần reclaimed memory liên tục.

### Bước 4 — Xác minh chứ không chỉ nhìn exit code

Trên HotSpot hỗ trợ:

```bash
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version
```

Tìm `UseG1GC` có effective value phù hợp và không có warning startup. Đọc cả **GC logging** nếu có. `PrintFlagsFinal` có output dài và flag names khác nhau theo release. Nếu JVM dùng default collector, một số flags có thể được ergonomic selection; đọc giá trị thực tế thay vì suy từ cấu hình ứng dụng.

### Bước 5 — Đo trên workload thực tế

Chạy app với cùng heap/CPU/container quota và GC logging, so sánh **pause/throughput/after-GC live heap/native memory**. Một JVM khởi động được với `UseZGC` chưa chứng minh collector đó phù hợp với heap vài chục MB hoặc CPU quota rất thấp.

### Bước 6 — Ghi lại kết quả có thể lặp lại

Một record tốt gồm:

```text
JVM vendor:
JVM implementation:
JDK version + build:
OS / architecture:
Container image digest:
CPU quota:
Memory limit:
Collector requested:
Effective collector:
Startup exit status:
GC log evidence:
Heap flags:
Observed pause/throughput:
Vendor support reference:
```

Đây là **mẫu biểu mẫu chẩn đoán**, không phải dữ liệu đã đo. Giữ record này trong cấu hình vận hành/CI để lần nâng cấp JVM sau biết collector support có đổi không.

## 11. Java 17+: chương trình nhận diện JVM và GC qua MXBeans

Dùng public Java Management API có thể đọc **tên GC beans** mà runtime expose. Điều này hữu ích khi cần xác định JVM thực sự hoạt động, **nhưng bean names không chuẩn hóa thành một bảng GC algorithm portable giữa các JVM**.

Tạo file **`GcRuntimeProbe.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class GcRuntimeProbe {
    public static void main(String[] args) {
        System.out.println("java.version: "
                + System.getProperty("java.version"));
        System.out.println("java.vendor: "
                + System.getProperty("java.vendor"));
        System.out.println("java.vm.name: "
                + System.getProperty("java.vm.name"));
        System.out.println("java.vm.version: "
                + System.getProperty("java.vm.version"));
        System.out.println("os.name: "
                + System.getProperty("os.name"));
        System.out.println("os.arch: "
                + System.getProperty("os.arch"));
        System.out.println("available processors: "
                + Runtime.getRuntime().availableProcessors());

        List<String> collectors = new ArrayList<>();
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            collectors.add(bean.getName());
        }
        Collections.sort(collectors);

        System.out.println("collector beans: " + collectors);
        System.out.println("bean count: " + collectors.size());
    }
}
```

Biên dịch:

```bash
javac -encoding UTF-8 GcRuntimeProbe.java
```

Chạy trên HotSpot với những collector được hỗ trợ:

```bash
java GcRuntimeProbe
java -XX:+UseSerialGC GcRuntimeProbe
java -XX:+UseG1GC GcRuntimeProbe
```

**Các dòng output có định dạng cố định, nhưng giá trị phụ thuộc runtime:**

```text
java.version: <phiên bản JVM>
java.vendor: <vendor>
java.vm.name: <VM name>
java.vm.version: <VM build>
os.name: <OS>
os.arch: <CPU architecture>
available processors: <số CPU theo runtime>
collector beans: [<các bean names VM công bố>]
bean count: <số bean>
```

Những mục giữa dấu `<...>` là **ký hiệu mô tả dữ liệu phụ thuộc môi trường**, không phải output mà code in y nguyên. Trên HotSpot Serial GC, bean names thường có `Copy` và `MarkSweepCompact`; trên HotSpot G1 thường có `G1 Young Generation` và `G1 Old Generation`; một số collectors mới hoặc một bản OpenJ9 sẽ đặt tên khác.

**Không viết test `collector beans` phải có đúng 2 phần tử trên mọi collector.** MXBeans mô tả management view của VM; một collector có thể expose số bean khác với số GC algorithms thực tế.

### Vì sao `java.vm.name` quan trọng?

`java.version` chỉ cho biết Java version dạng công khai. `java.vm.name` giúp phân biệt HotSpot-based VM với OpenJ9 hoặc runtime khác; `java.vendor` cho biết nhà phát hành. Kết hợp ba giá trị này với OS/arch cho bức tranh rõ hơn so với một tên sản phẩm duy nhất.

**Nếu chạy Native Image:** `java.vm.name` và công cụ Java Management API có thể không áp dụng giống JVM mode; không dùng cùng mẫu này làm phép thử cho mọi native executable nếu chưa xác minh API hỗ trợ.

## 12. Java 17+: workload để thử collector đã được chọn

Muốn kiểm tra startup availability, `-version` thường đủ để bước đầu xác định option. Muốn quan sát collector thực thi trong một workload, tạo **`GcAllocationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GcAllocationDemo {
    private static volatile Object last;

    public static void main(String[] args) {
        List<byte[]> keep = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 400; i++) {
            byte[] block = new byte[128 * 1024];
            block[0] = (byte) (i % 100);
            checksum += Byte.toUnsignedInt(block[0]);

            if (i % 80 == 0) {
                keep.add(block);
            }
            last = block;
        }

        System.out.println("checksum: " + checksum);
        System.out.println("retained arrays: " + keep.size());
        System.out.println("bytes per array: " + keep.get(0).length);
        System.out.println("done");
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 GcAllocationDemo.java
java -XX:+UseSerialGC -Xms32m -Xmx64m GcAllocationDemo
```

**Standard output chương trình khi không bật GC logs:**

```text
checksum: 19800
retained arrays: 5
bytes per array: 131072
done
```

Giải thích:

- 400 lần lặp; `i % 100` chạy qua 0..99 **bốn chu kỳ**, mỗi chu kỳ tổng `4950`, nên checksum **19800**.
- `keep` lưu arrays ở `i=0,80,160,240,320`, tổng **5**; mỗi array dài `128 × 1024 = 131072` bytes.
- `last` là volatile static field giúp đường cấp phát có hiệu ứng observable và tham chiếu một array gần nhất; số GC cycles/tenuring vẫn tùy collector.
- Tổng bytes từng được yêu cầu cấp phát trong vòng lặp lớn hơn 50 MiB, nhưng không đồng nghĩa 50 MiB cùng reachable một lúc.
- **Không khẳng định** JVM phải xảy ra đúng một young/full GC: heap ergonomics, optimization và collection policy khác nhau.

So sánh **những lần chạy riêng** trên HotSpot đích:

```bash
java -XX:+UseParallelGC -Xms32m -Xmx64m -Xlog:gc=info GcAllocationDemo
java -XX:+UseG1GC -Xms32m -Xmx64m -Xlog:gc=info GcAllocationDemo
java -XX:+UseZGC -Xms128m -Xmx256m -Xlog:gc=info GcAllocationDemo
```

**Lưu ý điều kiện:** lần cuối chỉ là ví dụ để thử ZGC khi JDK/OS/architecture/budget hỗ trợ. Tăng heap cho ZGC nghĩa là không còn một so sánh apples-to-apples về throughput với hai lần đầu; nó dùng để **kiểm tra chạy được và đọc log**, không xếp hạng hiệu năng. Nếu VM báo option/heap/platform không hỗ trợ, hãy ghi nhận và dừng thử collector đó.

### Log output không có expected value duy nhất

Một JVM HotSpot có thể in dạng:

```text
[info][gc] Using G1
[info][gc] GC(...) Pause Young (...) ...ms
```

Đây là **mẫu log minh họa**, không phải stdout của code hay lời hứa có đúng hai lines. Logs phụ thuộc flags, collector, JDK version và mức tải. Ngay cả một GC hỗ trợ startup tốt cũng có thể không phát sinh chu kỳ trong demo quá ngắn.

## 13. CI/CD: xác minh trước và sau khi nâng cấp JDK

Khi một ứng dụng có yêu cầu về GC, **nâng cấp JVM** không chỉ là đổi số version:

- Một flag có thể deprecated/obsolete/removed.
- Collector được chuyển từ experimental sang production.
- Một mode generational có thể trở thành default hoặc là lựa chọn duy nhất.
- Vendor đổi base image, OS layer, architecture hoặc build option.
- CPU/container memory limits thay đổi cách JVM chọn default.
- Performance/regression có thể khác dù collector vẫn cùng tên.

### Ví dụ kiểm tra sớm khi build container

Đối với HotSpot có nhu cầu cố định G1:

```bash
java -XX:+UseG1GC -Xlog:gc=info -version
```

Đặt bước tương đương trong image/runtime kiểm thử. Kiểm tra:

1. Lệnh **exit code bằng 0**.
2. Không có warning cho GC flags đã bị bỏ/không nhận diện.
3. GC startup log/flags xác nhận collector mong muốn.
4. Runtime vendor/architecture đúng với target.
5. Khả năng chạy ứng dụng với heap/CPU limits thực tế.
6. GC metrics trên workload smoke test và tải đại diện.

### Không dùng tự động fallback im lặng

Ví dụ code deploy:

```text
Nếu ZGC không khởi động được:
    tự xóa UseZGC và chạy default collector
```

Đây là **pseudocode policy**. Trừ khi kiến trúc đã phê duyệt fallback và có kiểm tra SLO, việc tự đổi collector có thể đưa production vào một trạng thái **chạy được nhưng latency xấu**. Fail fast + rollback/alert thường an toàn hơn với services yêu cầu GC behavior cụ thể.

Có thể chủ động thiết kế danh sách collectors hợp lệ cho từng environment, nhưng phải ghi rõ **điều kiện hỗ trợ và benchmark** của mỗi lựa chọn.

## 14. Troubleshooting tình huống thực tế

### Case A — “Mình dùng JDK 17 nhưng Shenandoah flag báo không nhận diện”

**Không vội kết luận** JVM bị lỗi: xác định `java -version`, vendor, build, OS/arch. Kiểm tra distribution có build Shenandoah hay không và release notes của nó. Nếu production cần Shenandoah, cần **chọn đúng runtime build được hỗ trợ**, không sao chép một flag từ một JDK khác.

### Case B — “CMS trên JDK 8 chạy được, nâng lên 17 lỗi startup”

CMS đã bị removed từ JDK 14 upstream HotSpot. Cấu hình CMS cũ không còn phù hợp. Cần **migrate** sang collector hỗ trợ (thường thử default/G1 hoặc lựa chọn khác), xóa flags liên quan và benchmark lại pause/throughput.

### Case C — “JDK 21 chạy `ZGenerational`, JDK 24 warning/không nhận”

ZGC thay đổi: generational mode thành default ở JDK 23; non-generational removed JDK 24. Sử dụng **JDK24+ GC docs** và giảm các flags obsolete thay vì tin output cũ.

### Case D — “Cùng Java 17, một image dùng G1 còn image khác dùng Serial”

Kiểm tra **binary VM, CPU quota, memory limits, startup flags và default ergonomics**. Không đủ dữ liệu nếu chỉ có major version. Nếu collector quan trọng với SLO, truyền flag được kiểm chứng và log nó.

### Case E — “Copy `-Xgcpolicy:balanced` từ OpenJ9 sang HotSpot”

Sai implementation namespace: flag OpenJ9 không phải flag HotSpot. Dùng đúng runtime GC policy, không cố ánh xạ tên balanced thành G1 theo từ ngữ.

### Case F — “Ứng dụng GraalVM Native Image báo không hỗ trợ `UseG1GC`”

Xác định đang chạy **JVM mode** hay **Native Image executable**. Native Image GC selection được thực hiện theo builder/runtime options của Native Image (ví dụ `--gc=...` lúc build). Xác minh edition/OS/arch và documentation tương ứng.

### Case G — “Cờ nhận được nhưng process vẫn dùng collector khác”

Có thể đang chạy một **binary khác qua PATH**, option được cấu hình cho bước build chứ không phải runtime, flag bị bỏ qua/obsolete, hoặc default selection khác kỳ vọng. Lấy full startup command, flags/logs của **đúng PID/process**.

### Case H — “Có GC phù hợp nhưng heap quá nhỏ nên không startup”

Collector tồn tại trong binary nhưng **không thỏa runtime constraints**; tăng hợp lý test heap trong giới hạn container hoặc chọn collector khác được hỗ trợ. Không dùng một yêu cầu heap khởi động thất bại để kết luận rằng collector không có trong JDK.

## 15. Lỗi suy luận phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Java 17 ở đâu cũng có cùng danh sách GC.” | Vendor, JVM implementation, build và platform có thể khác |
| “JEP được chấp nhận nghĩa là mọi binary đều build collector đó.” | Còn build-time options và vendor packaging |
| “Flag được in trong danh sách nghĩa là collector đang chạy.” | Chỉ startup/VM flags/logs xác minh lựa chọn |
| “GC startup thành công nghĩa là performance phù hợp.” | Cần benchmark và quan sát pause/throughput/footprint |
| “G1 luôn là default ở mọi JVM.” | Default là quyết định implementation/ergonomics |
| “Một JVM nhận `UseSerialGC` thì nó dùng HotSpot implementation mọi trường hợp.” | Tên tương tự có thể tồn tại trong runtime khác, không cùng semantics |
| “Shenandoah có trong OpenJDK source nên Oracle/Temurin/... đều phải có.” | Feature/build support khác theo distribution/release |
| “ZGC mode không đổi giữa JDK 17 và 24.” | Generational transitions đã thay đổi |
| “CMS vẫn có trên HotSpot 17 nếu thêm experimental unlock.” | CMS đã removed từ upstream JDK14 |
| “OpenJ9 `gencon` chỉ là tên khác của G1.” | Thuật toán/GC policy khác |
| “Native Image dùng mọi HotSpot `-XX` flags như JVM mode.” | Runtime selection khác, có build-time options riêng |
| “Có cùng OS là có cùng GC support.” | CPU arch, JDK build, vendor, release cũng quan trọng |
| “Container không ảnh hưởng lựa chọn collector.” | CPU/memory limits và image binary có thể ảnh hưởng |
| “`-Xmx` là toàn bộ process memory.” | Native memory/stacks/metaspace/code cache nằm ngoài heap |
| “Một lần thử `-version` đủ chứng minh GC meets p99 goals.” | Chỉ bước availability startup; cần workload |
| “Bỏ qua unrecognized flags là cách fix.” | Có thể âm thầm đổi collector và gây regression |
| “Hai GC có tên gần giống là cùng implementation.” | Tên và chính sách có thể khác theo JVM |
| “JDK update minor chắc chắn không đổi GC behavior.” | Vendor fixes/ergonomics có thể thay đổi |

## 16. Bài tập tự kiểm tra

**Bài 1.** Hai máy đều dùng Java 17 nhưng một máy có Shenandoah, máy kia không. Có mâu thuẫn với Java SE không?  
**Đáp án:** Không. GC implementation/build/vendor khác nhau không vi phạm ngữ nghĩa Java nếu VM đáp ứng hợp đồng Java SE.

**Bài 2.** `java -version` hiển thị OpenJ9. Có thể dùng `-XX:+UseZGC` như trên HotSpot không?  
**Đáp án:** Không mặc nhiên. Cần tra GC policies/flags OpenJ9, ví dụ `-Xgcpolicy:gencon`.

**Bài 3.** Một HotSpot JDK 17 có `-XX:+UseZGC` nhưng từ chối khởi động trong container. Có chứng minh ZGC vắng mặt khỏi binary?  
**Đáp án:** Chưa đủ. Kiểm tra thông báo platform/heap/memory constraints, CPU, build và conflict flags.

**Bài 4.** Vì sao không dùng `-XX:+UseConcMarkSweepGC` trên HotSpot 17?  
**Đáp án:** CMS bị removed từ JDK 14 upstream; cần migrate và đo lại.

**Bài 5.** Khi chọn ZGC trên JDK 21, muốn bật generational mode thì làm thế nào?  
**Đáp án:** Trên build hỗ trợ, dùng `-XX:+UseZGC -XX:+ZGenerational` theo JEP 439 và kiểm tra startup.

**Bài 6.** Trên JDK 24, có thể tắt generational để trở về non-generational ZGC không?  
**Đáp án:** Không; non-generational mode đã bị loại bỏ upstream.

**Bài 7.** Có thể dùng `-Xgcpolicy:balanced` trên HotSpot vì “balanced” giống G1 không?  
**Đáp án:** Không. Đây là policy của OpenJ9, không phải cú pháp HotSpot G1.

**Bài 8.** Tại sao cần kiểm tra cả JVM vendor và VM name?  
**Đáp án:** Vendor/distribution và implementation là hai trục khác nhau; tên vendor không tự bảo đảm loại VM hay GC build.

**Bài 9.** `GarbageCollectorMXBean` cho biết “G1 Young Generation”. Điều này chứng minh gì?  
**Đáp án:** VM expose management bean tên ấy; trên HotSpot nó là bằng chứng hữu ích về GC hiện hành, nhưng phải kết hợp flags/logs khi yêu cầu xác minh nghiêm ngặt.

**Bài 10.** Một Native Image binary có G1 không?  
**Đáp án:** Phụ thuộc phiên bản/edition/platform/build-time option; không suy từ việc `java` của GraalVM JVM mode có G1.

**Bài 11.** Một GC được đánh dấu experimental có được production support mặc định không?  
**Đáp án:** Không mặc định. Phải xem vendor release notes/support policy.

**Bài 12.** Tại sao startup success chưa đủ cho chọn GC?  
**Đáp án:** Chưa biết pauses, throughput, live set, memory footprint và phù hợp SLO dưới tải thực.

**Bài 13.** Cùng image Java trên laptop và container khác kiến trúc có thể khác GC support không?  
**Đáp án:** Có, nếu binaries/OS/architecture/features khác; phải thử trên container target.

**Bài 14.** `UseG1GC` được liệt kê trong `PrintFlagsFinal` nhưng `UseSerialGC` mới được chọn. Kết luận gì?  
**Đáp án:** Flag G1 xuất hiện không có nghĩa được bật; đọc giá trị effective của các flags và startup log.

**Bài 15.** Một deployment đặt `IgnoreUnrecognizedVMOptions` để giữ service chạy khi GC option lỗi. Có rủi ro gì?  
**Đáp án:** Service có thể khởi động với collector khác mà team không biết, gây latency/performance regression.

**Bài 16.** JDK update từ 21 sang 24 có cần kiểm tra lại ZGC flags?  
**Đáp án:** Có. Generational ZGC là lựa chọn trên JDK21, mặc định từ JDK23, non-generational mode bị loại JDK24.

**Bài 17.** Hai HotSpot distributions cùng hỗ trợ G1 thì hiệu năng nhất thiết giống nhau?  
**Đáp án:** Không. Build flags, JDK patch level, OS, CPU quotas, heap ergonomics và workload vẫn ảnh hưởng.

**Bài 18.** Muốn xác minh collector của process đang chạy, nên dùng gì?  
**Đáp án:** JVM version/vendor/VM name, startup GC logs, effective VM flags, `jcmd VM.flags` khi hỗ trợ, và GC MXBeans/JFR tùy JVM.

## 17. Checklist trước khi quyết định hoặc nâng cấp collector

- [ ] Đã xác định **JVM implementation** thay vì chỉ biết “Java 17/21/25”?
- [ ] Đã ghi đầy đủ vendor, build number, JDK major/update?
- [ ] Đã xác minh OS, CPU arch, container image digest, libc/page/memory constraints cần thiết?
- [ ] Đã đọc **release notes + support matrix** đúng version/vendor?
- [ ] Đã phân biệt experimental/production/deprecated/removed?
- [ ] Đã thử khởi động với **một** collector option mỗi lần?
- [ ] Đã kiểm tra **exit status**, warning và startup GC log?
- [ ] Đã xác minh collector **thực tế** thay vì chỉ đoán từ option name?
- [ ] Không dùng `IgnoreUnrecognizedVMOptions` che option GC sai?
- [ ] Đã kiểm tra heap sizing, CPU quota và native memory budget?
- [ ] Đã đo pauses, throughput và memory footprint trên tải đại diện?
- [ ] Có test sau JDK major/minor update để phát hiện flags obsolete?
- [ ] Có rollback/fail-fast policy nếu collector yêu cầu không dùng được?
- [ ] Không copy flags giữa HotSpot, OpenJ9 và Native Image mà không điều chỉnh?
- [ ] Đã lưu lại kết quả để đội vận hành có thể tái hiện?

## 18. Kết luận

**Tính sẵn có của GC là thuộc tính của _runtime cụ thể_, không phải của ngôn ngữ Java nói chung.** Một collector có thể được mô tả trong JEP, có tên trong flag help, được build vào HotSpot, khởi động trên Linux x86-64, nhưng không có trong một distribution/architecture khác. Một mode từng hợp lệ cũng có thể bị removed qua những release mới; CMS và non-generational ZGC là ví dụ điển hình.

Hãy luôn xác minh theo thứ tự:

```text
JDK vendor / VM implementation
        ↓
Full JDK build và release notes
        ↓
OS + CPU + container constraints
        ↓
GC option có được hỗ trợ không?
        ↓
Khởi động thành công không?
        ↓
Collector thực sự được chọn là gì?
        ↓
Có đáp ứng SLO và memory budget khi chịu tải không?
```

**Nếu chỉ nhớ một quy tắc:** đừng hỏi “Java có ZGC/Shenandoah không?” một cách trừu tượng; hãy hỏi **“binary JVM này, trên môi trường triển khai này, với bộ flags và heap này, có hỗ trợ và đang sử dụng collector đó không?”**

### Tài liệu tham khảo gốc

- Oracle JDK 17 — **HotSpot Available Collectors**: https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html
- Oracle JDK 17 — **The java Command / HotSpot GC flags**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17 — **Garbage Collection Tuning Guide**: https://docs.oracle.com/en/java/javase/17/gctuning/
- OpenJDK — **JEP 333: ZGC**, **JEP 377: ZGC production**, **JEP 439: Generational ZGC**, **JEP 474: Generational by default**, **JEP 490: Remove Non-Generational Mode**: https://openjdk.org/jeps/333 ; https://openjdk.org/jeps/377 ; https://openjdk.org/jeps/439 ; https://openjdk.org/jeps/474 ; https://openjdk.org/jeps/490
- OpenJDK — **JEP 189: Shenandoah**, **JEP 379: Shenandoah production**, **JEP 363: Remove CMS**: https://openjdk.org/jeps/189 ; https://openjdk.org/jeps/379 ; https://openjdk.org/jeps/363
- Eclipse OpenJ9 — **GC Policies**: https://eclipse.dev/openj9/docs/gc/ và https://eclipse.dev/openj9/docs/xgcpolicy/
- GraalVM — **Native Image Memory Management**: https://www.graalvm.org/dev/reference-manual/native-image/optimizations-and-performance/MemoryManagement/
- Java SE 17 — **GarbageCollectorMXBean**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html

**Tài liệu có thể thay đổi theo phiên bản:** khi nghiên cứu bộ thu gom trên JDK mới hơn JDK 17, luôn chọn đúng mục documentation của release đang chạy; không sao chép một matrix cũ như chân lý cố định cho mọi JDK tương lai.
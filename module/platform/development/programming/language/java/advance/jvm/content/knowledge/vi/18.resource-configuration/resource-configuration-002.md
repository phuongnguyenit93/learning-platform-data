# Tùy chọn chuẩn, -X, -XX và cách xác nhận cờ được hỗ trợ trong JVM

## Mục tiêu

Trong một ứng dụng Java thực tế, JVM nhận được nhiều loại tham số: tùy chọn launcher, tham số dành cho JVM, system properties và **application arguments**. Chúng không cùng ngữ nghĩa, không cùng mức ổn định và không phải tất cả được hỗ trợ trên mọi vendor/JDK build.

Ví dụ:

~~~bash
java -Xms256m -Xmx1g -XX:+UseG1GC -Dapp.profile=prod -jar service.jar --port=8080
~~~

Lệnh minh họa trên có:
- `-Xms256m` và `-Xmx1g`: nhóm **-X** định cấu hình initial/minimum heap và maximum Java heap.
- `-XX:+UseG1GC`: nhóm **-XX** chọn G1 garbage collector theo HotSpot.
- `-Dapp.profile=prod`: một **standard launcher option** truyền system property cho Java code.
- `-jar service.jar`: launcher chạy JAR có Main-Class hợp lệ.
- `--port=8080`: **argument của ứng dụng**, không phải JVM option khi nằm sau `-jar service.jar`.

Một cờ được ghi trong cấu hình không đồng nghĩa nó có tác dụng: cờ có thể bị từ chối, cần unlock, chỉ hỗ trợ trên một platform, bị đánh dấu **deprecated**, **obsolete** (nhận nhưng bỏ qua), **expired/removed** (bị từ chối), hoặc được JVM thay đổi giá trị cuối vì ergonomics hay flag precedence.

Sau bài, bạn có thể:
1. Phân loại **standard options**, **extra/non-standard -X** và **advanced HotSpot -XX**.
2. Viết đúng cú pháp Boolean `-XX:+Flag`/`-XX:-Flag` và giá trị `-XX:Flag=value`; hiểu `-Xmx2g` không giống `-XX:+Xmx`.
3. Kiểm tra phạm vi hỗ trợ qua `java --help`, `java -X`, `-Xlog:help`, tài liệu bản JDK, `-XX:+PrintFlagsFinal` và `jcmd`.
4. Phân biệt **cờ được parser chấp nhận**, **đang bật**, **giá trị cuối**, **có tác dụng với subsystem** và **được hỗ trợ ổn định**.
5. Phát hiện nhầm JDK binary, cờ đặt sai phía `-jar`, môi trường `JDK_JAVA_OPTIONS`/`JAVA_TOOL_OPTIONS`, cờ cần unlock và options hết vòng đời.
6. Cấu hình Java heap, CPU, native resources và GC theo yêu cầu thật, không suy từ một command-line flag thành toàn bộ process memory.
7. Sử dụng ví dụ Java 17+ có stdout xác định, cùng quy trình smoke-test an toàn cho CI/CD và production.

## 1. Ba nhóm option: tên gọi và mức độ ổn định

Tài liệu chính thức về lệnh `java` phân biệt:

| Nhóm | Ví dụ | Đặc điểm |
| --- | --- | --- |
| **Standard Java launcher options** | `--class-path`, `-cp`, `-jar`, `-Dkey=value`, `--module-path`, `--enable-assertions`, `--version` | Được tài liệu Java command mô tả và có kỳ vọng tính tương thích rộng hơn giữa các JVM implementations |
| **Extra/non-standard options (-X)** | `-Xms`, `-Xmx`, `-Xss`, `-Xint`, `-XshowSettings`, `-Xlog` | HotSpot-specific hoặc không được bảo đảm mọi JVM hỗ trợ; có thể thay đổi |
| **Advanced HotSpot options (-XX)** | `-XX:+UseG1GC`, `-XX:MaxRAMPercentage=75`, `-XX:+PrintFlagsFinal` | Cấu hình sâu runtime, GC, JIT, serviceability; độ ổn định tùy flag và release |

**Không thể đánh giá tính ổn định chỉ bằng độ dài tên cờ.** `-Xmx` thuộc -X nhưng được sử dụng rất phổ biến; còn một flag `-XX` có thể là product flag quen thuộc, diagnostic flag cần unlock hoặc experimental flag chỉ phù hợp thử nghiệm. Dù vậy cả -X và -XX **không là hợp đồng Java SE áp dụng vô điều kiện cho mọi JVM**. <https://dev.java/learn/jvm/tools/core/java/>

### Standard không có nghĩa chương trình không cần kiểm tra version

Một option được ghi nhận trong một JDK hiện tại có thể **chưa tồn tại trong JDK đời trước**. Chẳng hạn các module options xuất hiện theo lịch sử Java Platform Module System, và `--enable-preview` yêu cầu sự phù hợp giữa compiler/runtime và bản phát hành. Với toolchains thực tế, luôn tra tài liệu của đúng JDK được triển khai.

### Một ứng dụng có nhiều “đường” nhận tham số

~~~text
Operating system / shell
         |
         +-- environment variables
         |      JDK_JAVA_OPTIONS / JAVA_TOOL_OPTIONS
         |
         +-- java launcher args
                  |
           JVM / module/class loader
                  |
            main(String[] args)
                  |
          application framework parser
~~~

Lỗi thường gặp là trộn `-Dserver.port=8080` (system property), `--server.port=8080` (có thể là application argument của framework), và `-XX:...` (VM flag). Chúng **không tự hoán đổi** cho nhau.

## 2. Cú pháp launcher: đặt JVM options trước main target

Ba kiểu chạy thông dụng:

~~~bash
java [options] com.example.Main [app-args]
java [options] -jar application.jar [app-args]
java [options] --module module.name[/MainClass] [app-args]
~~~

Trong code fence, các phần trong dấu ngoặc vuông là **ký hiệu minh họa** của command grammar, không được gõ nguyên nếu không có ý nghĩa cụ thể. `options` thường được parser của launcher đọc **trước main class hoặc -jar artifact**. Những token sau main target thông thường được chuyển vào `main(String[] args)` của ứng dụng.

So sánh:

~~~bash
java -Dapp.mode=study -Xmx128m -jar demo.jar input.txt
~~~

Đây là **mẫu lệnh**, cần JAR đúng. JVM thấy system property `app.mode=study` và heap maximum ~128 MiB; ứng dụng nhận `input.txt`.

Ngược lại:

~~~bash
java -jar demo.jar -Xmx128m
~~~

Ở đây `-Xmx128m` thường là **chuỗi argument của ứng dụng** sau JAR, **không đặt maximum heap**. Một framework có thể có parser riêng và thậm chí báo “unknown app argument”. Hãy xem actual JVM command line, không chỉ một string xuất hiện đâu đó trong launch script.

### `-jar` không giống classpath mode

~~~bash
java -cp lib/app.jar:lib/dependency.jar com.example.Main
~~~

Lệnh trên minh họa **Linux/macOS** với classpath separator `:`; Windows dùng `;`. Khi chạy `-jar`, launcher dùng entry point/JAR rules tương ứng; việc thêm `-cp` có thể không ảnh hưởng theo cách bạn dự đoán. Đừng cố “sửa thiếu dependency” bằng cách đổi vị trí flags mà không đọc tài liệu `-jar` và manifest/classpath.

### System properties

~~~bash
java -Ddemo.mode=study com.example.Main
~~~

Trong Java, đọc bằng `System.getProperty("demo.mode")`. Đây không phải environment variable. `System.getenv("DEMO_MODE")` đọc một nguồn khác. Một application framework có thể thêm cách ánh xạ giữa properties/environment nhưng đó không phải behavior của JVM option parser.

## 3. -X: các extra options thường gặp

| Flag | Tác dụng chính | Cảnh báo |
| --- | --- | --- |
| `-Xms256m` | Thiết lập kích thước heap khởi đầu/minimum theo semantics HotSpot | Không phải tổng process RSS |
| `-Xmx2g` | Hard maximum Java heap | Native memory còn có metaspace, thread stacks, code cache, direct memory... |
| `-Xss1m` | Thiết lập stack size cho platform threads theo HotSpot/OS | Không phải “tổng stack của mọi thread” |
| `-Xint` | Chế độ interpreted-only cho Java code | Thay đổi performance mạnh, không dùng để mô phỏng production tự nhiên |
| `-Xcomp` | Thiên về compile sớm | Có thể tốn compilation CPU và khác profile |
| `-Xbatch` | Chạy JIT compilation foreground thay vì background theo policy | Có thể làm warmup/latency rất khác |
| `-XshowSettings:vm` | In VM settings hữu ích | Output thay đổi theo bản JDK |
| `-Xlog:gc*=info` | Unified logging GC ở HotSpot bản hỗ trợ | Log I/O có overhead; không có output bất biến |
| `-Xshare:off` / `-Xshare:on` | Điều khiển CDS sharing | ON bắt buộc dùng archive, dễ fail khi mismatch |

**Không sử dụng tất cả cờ cùng lúc chỉ vì chúng xuất hiện trong bảng.** Nếu đang đo GC, bật `-Xint` hoặc `-Xcomp` sẽ đổi JIT execution model, làm so sánh mất ý nghĩa.

### Kích thước tài nguyên: đơn vị đúng

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -Xss1m -jar application.jar
~~~

Tùy chọn -X thường có suffix `k`/`m`/`g` với cách diễn giải kích thước kiểu binary units trong HotSpot. Đọc actual `MaxHeapSize`/`InitialHeapSize` bằng VM diagnostics để xác nhận. Đừng kết luận “container RAM=2 GiB đủ vì -Xmx2g”: process cần bộ nhớ **ngoài Java heap**.

### -Xlog: cú pháp và cấu hình logging

Ví dụ:

~~~bash
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar application.jar
~~~

Đây là **mẫu chạy**, cần file JAR thực. Unified logging chia selectors (tags/levels), output và decorators; các tags có thể khác release. Hãy xem `java -Xlog:help` trên chính JDK để tìm syntax và tags khả dụng.

Cảnh báo: verbose logging tạo CPU/disk I/O và có thể ghi chi tiết hoạt động ứng dụng. Ở production, cân nhắc dung lượng log, rotation, quyền đọc và phạm vi thông tin.

## 4. -XX: hai dạng cú pháp phổ biến

### Boolean flag: dấu + và -

~~~bash
java -XX:+UseG1GC -version
java -XX:-UseCompressedOops -version
~~~

- `-XX:+FlagName` nghĩa yêu cầu bật Boolean flag đó.
- `-XX:-FlagName` nghĩa yêu cầu tắt.
- **Không** dùng `-XX:UseG1GC=true` như một thay thế bừa bãi vì syntax được tài liệu mô tả cho boolean flags là `+/-`.
- Việc flag bị disable hoặc unsupported **không đồng nghĩa** JVM không thể chạy: tùy constraint hoặc dependency giữa flags, parser có thể fail hoặc runtime có behavior theo policy.

`UseCompressedOops` là flag HotSpot có thể chịu constraints về heap/platform/JDK release; đừng tắt tùy tiện vì ảnh hưởng memory/performance và có thay đổi theo phiên bản. Ví dụ trên **chỉ minh họa grammar**, không phải lời khuyên tuning.

### Flag nhận giá trị: dấu bằng

~~~bash
java -XX:MaxRAMPercentage=65 -version
java -XX:ActiveProcessorCount=2 -version
java -XX:MaxMetaspaceSize=256m -version
java -XX:ReservedCodeCacheSize=128m -version
~~~

Cần phân biệt:
- `MaxRAMPercentage` là một **percent value** (ví dụ 65 nghĩa 65%, không phải 0.65).
- `ActiveProcessorCount` điều chỉnh số processors JVM **báo/nhận diện cho ergonomics** như GC/ForkJoin; không tạo CPU cores hoặc giới hạn cứng scheduler của OS.
- `MaxMetaspaceSize` đặt giới hạn metaspace thích hợp; quá thấp có thể làm class loading fail.
- `ReservedCodeCacheSize` điều chỉnh vùng chứa JIT-compiled code; không phải Java heap.
- Với mỗi flag, đọc constraints và default trong **Java command docs của đúng release**.

Một số flag có syntax option-specific khác. Đừng tự giả định mọi option với argument đều dùng dấu bằng, hay thay suffix `m` vào một percent flag.

## 5. Bốn mức ý nghĩa khi nói “cờ được hỗ trợ”

Cần tách bốn câu hỏi:

| Câu hỏi | Kiểm tra chính | Vì sao khác nhau |
| --- | --- | --- |
| **Parser có nhận option?** | Thử khởi động `java [flag] -version`, kiểm tra exit code/stderr | Một obsolete flag đôi khi được nhận nhưng bị bỏ qua |
| **Flag có tồn tại ở runtime?** | `PrintFlagsFinal`, `jcmd VM.flags -all`, tài liệu đúng JDK | Một option có thể bị ẩn sau unlock hoặc chỉ tồn tại bản HotSpot khác |
| **Effective value cuối là gì?** | `PrintFlagsFinal` hoặc `jcmd PID VM.flags -all` | Ergonomics, default, command line và constraints có thể ảnh hưởng |
| **Feature thực sự hoạt động?** | Subsystem logs/behavior, metrics, smoke test workload | “flag true” không chứng minh GC/JIT/memory performance đạt kỳ vọng |

Ví dụ `-XX:+UseZGC` có thể được parser nhận, nhưng câu “mọi ZGC mode như JDK 21 còn tồn tại trong JDK 25” không đúng: underlying algorithms/legacy flags đã thay đổi. Tương tự, JVM chấp nhận một old flag và in warning có thể **không hề áp dụng effect**.

**Lưu ý:** `java -version` có thể trả 0 ngay cả khi một flag hợp lệ chỉ định tính năng hiếm dùng và runtime workload không kích hoạt nó. Smoke test kiểm tra khả năng khởi động, không đủ để chứng minh hiệu năng.

## 6. Bước 1: biết chính xác bản JDK đang thực thi

Bắt đầu:

~~~bash
java -version
java --version
javac -version
~~~

Output từ `java -version` gồm version/build/vendor/VM details tùy JDK; không có stdout chung cố định. `javac` có thể thuộc một JDK khác với `java` trong PATH.

Đặc biệt khi dùng:
- IDE run configurations;
- Maven/Gradle toolchains;
- application servers có private bundled JRE;
- Docker/Podman images hoặc Kubernetes Pods;
- systemd/windows services và shell aliases;
- nhiều cài đặt JDK17/21/25 cạnh nhau.

**Hãy chạy các lệnh kiểm tra trong chính runtime/container/launch environment sẽ khởi động service**, không suy từ shell máy cá nhân. Với ứng dụng đang chạy, lấy process command line và VM version bằng công cụ gắn đúng PID.

### Java home không tự bảo đảm binary được gọi

`JAVA_HOME` là biến môi trường thường được scripts/toolchains dùng; khi gõ `java`, shell còn áp dụng PATH/resolution rules. Trên Windows có `Get-Command java` trong PowerShell; trên Linux/macOS có `command -v java`. Không khẳng định `JAVA_HOME` và `java -version` luôn trùng nhau nếu không kiểm tra.

## 7. Bước 2: Java launcher tự công bố những options nào?

Các lệnh phổ biến:

~~~bash
java --help
java -X
java -Xlog:help
~~~

Ý nghĩa:
- `java --help` mô tả cú pháp launcher và **standard options** phù hợp.
- `java -X` hiển thị nhiều extra/non-standard options của HotSpot trên bản đó.
- `java -Xlog:help` cung cấp logging tags, levels, decorators và syntax được hỗ trợ.

**Không có lệnh `java -X` nào nhất thiết liệt kê mọi option -XX**, đặc biệt diagnostic/experimental/internal flags. Tương tự, một flag xuất hiện ở help không bảo đảm nó có cùng range/default trên một JDK khác.

Có thể dùng `java --help-extra` ở những JDK hỗ trợ để xem thêm option descriptions. Kết quả output phụ thuộc binary và version.

### Cách kiểm tra trên PowerShell

~~~powershell
java --help
java -X
java -Xlog:help
~~~

Đầu ra của một vài launcher options có thể đến stderr; khi lọc kết quả cần quan tâm cả stdout và stderr. Không dùng “không thấy trong một `Select-String`” làm bằng chứng tuyệt đối rằng flag không tồn tại.

## 8. Bước 3: xem giá trị các -XX flags của HotSpot

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Trên HotSpot bản hỗ trợ, lệnh này liệt kê nhiều VM flags cùng:
- loại (ví dụ bool, intx, uintx, size_t, double...);
- tên (ví dụ `MaxHeapSize`);
- giá trị cuối đã được tính;
- phân loại và/hoặc nguồn gốc (product, diagnostic, experimental, command line, ergonomic, default...) tùy bản build và định dạng output.

Ví dụ cấu trúc dòng **minh họa**, không phải log cố định:

~~~text
   size_t MaxHeapSize = 536870912 {product} {ergonomic}
     bool UseG1GC = true         {product} {ergonomic}
~~~

Các con số, dấu `=` hoặc `:=`, name/value, category/origin thay đổi theo JDK/flags/container. **Đừng copy kết quả minh họa để xác nhận production instance**.

### So default với explicitly set

~~~bash
java -XX:+PrintFlagsFinal -version
java -Xmx512m -XX:+PrintFlagsFinal -version
~~~

So `MaxHeapSize` giữa hai lần. Khi có `-Xmx512m`, expected maximum Java heap ở cấu hình HotSpot phù hợp là 512 MiB (536.870.912 bytes). Nhưng command line có thể bị ảnh hưởng bởi hidden environment flags; để kiểm soát thí nghiệm, kiểm tra cả môi trường và actual input args.

Với `-XX:MaxRAMPercentage=65` và **không** đặt `-Xmx`, maximum heap thường được tính theo tài nguyên container/host mà VM nhận diện và những constraints liên quan. Con số thật không thể suy chỉ từ “65% của 8 GiB host RAM” nếu container memory limit chỉ 2 GiB hoặc có minimum/maximum limits khác.

### Xem range nếu cần kiểm tra giá trị đầu vào

Trên các JDK HotSpot có hỗ trợ:

~~~bash
java -XX:+PrintFlagsRanges -version
~~~

Dữ liệu ranges chỉ xuất hiện đầy đủ cho các flags có range được khai báo; output không thay thế các **inter-flag constraints** hoặc runtime limitations. Một giá trị nằm trong range nhưng xung đột với memory budget/GC mode vẫn có thể làm startup fail.

### PrintFlagsInitial và PrintFlagsFinal

Một số HotSpot builds cho phép:

~~~bash
java -XX:+PrintFlagsInitial -version
java -XX:+PrintFlagsFinal -version
~~~

`PrintFlagsInitial` cho biết nhiều initial/default flag values khi thích hợp; `PrintFlagsFinal` phản ánh final chosen values của startup. Chúng không phải mô tả **mọi thay đổi động phát sinh suốt lifetime** và không có nghĩa tất cả cờ có thể chỉnh live.

## 9. Bước 4: kiểm tra process đang chạy, không chỉ thử một JVM mới

Một JVM được khởi động bằng Helm chart/script/IDE có thể dùng arguments khác nhiều so với lệnh thử `java -version` của bạn. Với target process HotSpot có quyền attach, sử dụng:

~~~bash
jcmd
jcmd PID VM.command_line
jcmd PID VM.flags
jcmd PID VM.flags -all
jcmd PID VM.version
~~~

**`PID` ở đây là ký hiệu cần thay bằng process ID thật**, không phải chuỗi hợp lệ để copy y nguyên. Dùng `jcmd PID help` để xem những diagnostics khả dụng trên chính process; availability và output có thể thay đổi theo JDK.

Diễn giải:
- `VM.command_line` cho biết actual VM/Java command line theo diagnostic implementation.
- `VM.flags` tóm tắt một số VM flags.
- `VM.flags -all` yêu cầu thêm danh sách các flags, thường với giá trị/nguồn gốc, nếu supported.
- `VM.version` xác nhận actual runtime VM build.

Một vài flags là **manageable** và có thể điều chỉnh live qua công cụ như `jinfo`/management, nhưng **phần lớn startup flags không có quyền đổi động**, và việc chỉnh live trên production là thao tác vận hành cần kiểm soát.

### Không phải mọi JVM đều cho attach

Hạn chế container namespaces, filesystem permissions, quyền OS, flag disable attach mechanism, JDK installation và bảo mật có thể khiến `jcmd` thất bại. Đừng coi attach failure là bằng chứng flag không được hỗ trợ; đầu tiên kiểm tra permission/PID/VM build.

### Java API tự đọc một số args

`ManagementFactory.getRuntimeMXBean().getInputArguments()` trả về các input arguments mà VM nhận theo contract API, hữu ích khi logging cấu hình khởi động. Nó **không nhất thiết đầy đủ mọi launcher/application argument**, và một số options chỉ thuộc launcher, không thuộc VM. Khi muốn biết flags cuối cùng, ưu tiên `PrintFlagsFinal`/`jcmd` hơn là parse một chuỗi Java args.

## 10. Các trạng thái vòng đời: active, deprecated, obsolete, expired

Các `-XX` options không có tuổi thọ vô hạn. OpenJDK HotSpot có cơ chế quản lý flags, mô tả trong nguồn `arguments.cpp`.

| Trạng thái | Thường có hiệu lực không? | Dấu hiệu |
| --- | --- | --- |
| **Active/supportable** | Có theo semantics và constraints | Launcher nhận flag và VM áp dụng |
| **Deprecated** | Thường còn effect | Warning, được cảnh báo có thể bị xóa trong bản sau |
| **Obsolete** | **Không còn effect** | VM có thể vẫn nhận cú pháp để tương thích, in warning và bỏ qua |
| **Expired/removed** | Không còn được nhận như option hợp lệ | VM từ chối startup, thường báo unrecognized flag |
| **Experimental** | Có thể có effect nhưng chưa ổn định | Cần `UnlockExperimentalVMOptions` nếu flag bị khóa |
| **Diagnostic** | Có thể có effect, dùng cho điều tra | Cần `UnlockDiagnosticVMOptions` đối với flags bị khóa |

**Phân biệt:** Một option bị obsolete vẫn có thể cho exit code 0. Do đó **startup success không đủ** để kết luận flag đang hoạt động. Nếu có warning “Ignoring option...” hoặc tương đương, phải xử lý cấu hình.

### Ví dụ về cờ bị loại bỏ theo release

Trên HotSpot JDK 17:
- `-XX:MaxPermSize=...` và `-XX:PermSize=...` là options lịch sử của PermGen đã bị loại bỏ; JVM hiện đại dùng metaspace.
- `-XX:+TraceClassLoading` bị loại bỏ, có replacement `-Xlog:class+load=info` trong Unified Logging.
- `--illegal-access=...` đã obsolete trong JDK 17: có thể được nhận nhưng không còn nới encapsulation như những release trước.

Trên JDK 24, một số `MaxRAMFraction`-style flags cũ đã bị loại bỏ, hướng tới các flags `MaxRAMPercentage` tương ứng. Trong JDK mới hơn, một flag khác có thể đi qua deprecated → obsolete → expired, không phải mọi flag theo chính xác một release schedule. Đọc danh sách **Deprecated / Obsolete / Removed Options** của **đúng JDK**.

### Khi migrate từ JDK 17 lên 21/25/26

Không suy từ “flag từng chạy trên Java 8” thành “flag vẫn hợp lệ trên Java 25”. Khi nâng version:
1. Liệt kê toàn bộ command line và environment-injected options.
2. Tra đúng Java launcher docs và release notes.
3. Tạo runtime image test đúng vendor/architecture.
4. Khởi động bằng exact production flags, capture exit code, warnings.
5. Đọc `PrintFlagsFinal`/`VM.flags` và subsystem logs.
6. Loại deprecated/obsolete flags và tìm replacement có tài liệu.
7. Chạy integration/performance tests trước rollout.

Nếu cờ đổi semantics giữa các JDK, có thể cần **version-conditional config** chứ không chỉ xóa warning.

## 11. Diagnostic và experimental flags: unlock đúng cách

Một số HotSpot options nằm trong các nhóm **diagnostic** hoặc **experimental** và không sẵn cho production command line nếu không unlock.

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -version
java -XX:+UnlockExperimentalVMOptions -XX:+SomeExperimentalFlag -version
~~~

Dòng thứ hai là **minh họa cú pháp**, `SomeExperimentalFlag` không phải tên cờ thật và không được chạy nguyên vẹn. Với diagnostic flag như `LogCompilation`, cần áp dụng đúng yêu cầu của bản HotSpot. Đặt flag unlock **trước flags cần unlock** giúp tránh lỗi parse ở những versions tương ứng.

**Không có nghĩa:** “chỉ cần bật UnlockDiagnosticVMOptions là mọi flag bí mật được hỗ trợ và an toàn”. Diagnostic/experimental flags có thể không nằm trong API ổn định và có thể đổi/xóa. Chỉ bật khi có nhu cầu đo/điều tra rõ ràng, kèm rollout và rollback plan.

### Đừng dùng `-XX:+IgnoreUnrecognizedVMOptions` để che lỗi cấu hình

Một số HotSpot builds có flag cho phép bỏ qua options không nhận ra. Việc sử dụng nó để “đẩy một file JVM_FLAGS chung cho mọi JDK” có thể che sự cố:
- JVM vô tình không bật GC mode mà team kỳ vọng;
- heap/native memory bound bị bỏ qua;
- container chạy với default ngoài dự kiến;
- warning mất khỏi tuyến CI và chỉ lộ ra khi service quá tải.

Đối với flag ảnh hưởng correctness/resource budget, **fail-fast và xác minh** tốt hơn là silently ignore. Nếu một library/agent sử dụng điều kiện version khác nhau, hãy cấu hình nhánh theo runtime cụ thể.

## 12. Các cờ tài nguyên thiết yếu: heap không bằng RSS

Một ứng dụng JVM sử dụng nhiều vùng memory:

~~~text
JVM PROCESS
 |
 +-- Java heap        -Xms, -Xmx, MaxRAMPercentage
 +-- Class metadata   Metaspace, Compressed Class Space
 +-- JIT code cache   ReservedCodeCacheSize
 +-- Thread stacks    -Xss for eligible platform threads
 +-- Direct/native    ByteBuffers, JNI, JVM internals
 +-- GC bookkeeping   card tables, remembered sets, etc.
 +-- OS mapped data   CDS archives, mapped files, libraries
 |
 +-- CPU threads/scheduler limits
      ActiveProcessorCount, GC thread ergonomics, container quota
~~~

`-Xmx1g` chỉ hạn chế một phần **Java heap**, không phải tổng process resident set size. Một container có limit 1 GiB và `-Xmx1g` dễ gặp OOM kill do native components, ngay cả khi Java heap chưa đầy.

| Mục tiêu | Các flags thường xem | Rủi ro khi cấu hình |
| --- | --- | --- |
| Maximum Java heap | `-Xmx`, `-XX:MaxRAMPercentage` | Xmx thấp: GC pressure/OOME; cao: RSS/native headroom thiếu |
| Initial heap | `-Xms` | Khởi tạo lớn/committed memory; quá nhỏ có expansion churn |
| Thread stack | `-Xss` | Stack quá nhỏ: StackOverflowError; quá lớn: native memory pressure |
| Class metadata | `-XX:MaxMetaspaceSize` | Class loading fail nếu quá chặt |
| Direct memory | `-XX:MaxDirectMemorySize` | Native/direct buffer limits, tùy JDK semantics |
| JIT code cache | `-XX:ReservedCodeCacheSize` | Compilation có thể bị giới hạn khi quá thấp |
| CPU ergonomics | `-XX:ActiveProcessorCount` | Không cấp thêm CPU, chỉ thay logic sizing/policy |
| Collector | `-XX:+UseG1GC`, `-XX:+UseZGC` | Thuật toán/flags có version-specific behavior |
| GC logs | `-Xlog:gc*` | Giúp quan sát, tạo overhead/disk logs |

**Không nên** đặt đồng thời nhiều flags điều khiển cùng mục tiêu mà không hiểu thứ tự ưu tiên. Khi có explicit `-Xmx`, cờ `MaxRAMPercentage` có thể không còn quyết định heap maximum như lúc không đặt Xmx.

## 13. Cấu hình trong containers: một ví dụ vận hành

Giả sử container có memory limit 2 GiB, ứng dụng có heap live set vài trăm MiB và sử dụng direct buffers/native libraries. Một thử nghiệm có thể bắt đầu:

~~~bash
java -Xms256m -Xmx1g -XX:+UseG1GC -Xlog:gc*=info -jar service.jar
~~~

Đây là **mẫu thăm dò**, không phải khuyến nghị số tối ưu. Chỉ đặt 1 GiB heap nếu đã đo:
- peak live heap và allocation spikes;
- thread count/stacks;
- metaspace/class loading;
- direct/native memory;
- JIT code cache, GC native overhead;
- container RSS/working set và CPU throttling.

Nếu container limit 2 GiB, **đừng dùng một bảng cờ Java thay cho thực tế memory metrics**. Với process đang chạy, có thể dùng:
- `jcmd PID GC.heap_info` để xem heap picture;
- `jcmd PID VM.flags` để xem VM config;
- JFR, GC logs và monitoring systems;
- `jcmd PID VM.native_memory summary` nếu process đã bật Native Memory Tracking phù hợp từ startup, ví dụ `-XX:NativeMemoryTracking=summary`.

**NMT không thể bật đầy đủ tùy ý sau khi JVM đã chạy** trên nhiều HotSpot configurations và có overhead. Không tự ý bật `NativeMemoryTracking=detail` trên production trước khi đánh giá chi phí.

### Vì sao ActiveProcessorCount cần thận trọng?

`-XX:ActiveProcessorCount=2` ảnh hưởng JVM's view of processors trong các ergonomics như sizing worker pools, nhưng không phải Linux `cgroups` CPU quota, không khóa ứng dụng chỉ sử dụng đúng hai OS CPUs và không ngăn native libraries tạo threads. Hãy đo process CPU thực tế và xem container metrics.

## 14. Ví dụ Java 17+: chứng minh launcher vs system property vs app args

Tạo file **`JvmOptionProbe.java`**:

~~~java
import java.util.Arrays;

public class JvmOptionProbe {
    public static void main(String[] args) {
        boolean assertionsEnabled = false;
        assert assertionsEnabled = true;

        String mode = System.getProperty("demo.mode", "missing");
        int sum = 19 + 23;

        System.out.println("mode=" + mode);
        System.out.println("assertions=" + assertionsEnabled);
        System.out.println("args=" + Arrays.toString(args));
        System.out.println("sum=" + sum);
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 JvmOptionProbe.java
~~~

Chạy trên JDK 17+:

~~~bash
java -ea -Ddemo.mode=study -Xms32m -Xmx128m JvmOptionProbe alpha beta
~~~

**Stdout nghiệp vụ chính xác:**

~~~text
mode=study
assertions=true
args=[alpha, beta]
sum=42
~~~

Giải thích:
- `-ea`/`--enable-assertions` bật đánh giá `assert` cho class trong ngữ cảnh này; assignment trong assert chỉ là **demo**, không phải pattern viết production logic.
- `-Ddemo.mode=study` tạo system property, không đi vào `args`.
- `-Xms32m` và `-Xmx128m` gửi option cho HotSpot, không đi vào `args`.
- `alpha beta` nằm sau main class, đi vào `String[] args`.
- Phép cộng 19+23 có thể được `javac` gấp thành constant, nhưng business output vẫn 42.

Thử đặt `-Xmx128m` sau class:

~~~bash
java -ea -Ddemo.mode=study JvmOptionProbe alpha -Xmx128m
~~~

Ứng dụng sẽ nhận `args=[alpha, -Xmx128m]`; token này **không phải JVM heap option** ở vị trí ấy. Đừng gán nghĩa cho substring `-Xmx` mà bỏ qua thứ tự argument.

## 15. Ví dụ Java 17+: quan sát effective heap trong ứng dụng

Trong HotSpot, có thể dùng management API để truy vấn một số VM flags. Tạo file **`HotSpotFlagProbe.java`**:

~~~java
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.VMOption;
import java.lang.management.ManagementFactory;

public class HotSpotFlagProbe {
    public static void main(String[] args) {
        HotSpotDiagnosticMXBean bean =
                ManagementFactory.getPlatformMXBean(
                        HotSpotDiagnosticMXBean.class);

        if (bean == null) {
            System.out.println("hotspotBeanAvailable=false");
            return;
        }

        VMOption option = bean.getVMOption("MaxHeapSize");
        long bytes = Long.parseLong(option.getValue());

        System.out.println("hotspotBeanAvailable=true");
        System.out.println("maxHeapMiB=" + (bytes / 1024 / 1024));
        System.out.println("origin=" + option.getOrigin());
    }
}
~~~

Biên dịch và chạy trên **HotSpot JDK 17+**:

~~~bash
javac --release 17 HotSpotFlagProbe.java
java -Xmx128m HotSpotFlagProbe
~~~

Khi HotSpotDiagnosticMXBean được hỗ trợ và `-Xmx128m` được áp dụng, ví dụ thường in:

~~~text
hotspotBeanAvailable=true
maxHeapMiB=128
origin=VM_CREATION
~~~

Đây là **expected output trên HotSpot JDK 17+ chuẩn với cấu hình nêu trên**, không phải contract của mọi JVM vendor hoặc tương lai. Bean có thể không có ở một VM khác, và `VMOption.Origin` phản ánh cơ chế config mà runtime báo cáo. Đừng dùng dấu bằng giữa `Runtime.getRuntime().maxMemory()` và `MaxHeapSize` như một phép kiểm tuyệt đối trên mọi collector/build, vì ergonomics và alignment.

### Phân biệt management-origin với effective behavior

`origin=VM_CREATION` thường biểu thị một option được set ở JVM startup, nhưng không chứng minh business performance. Một option có thể đã được nhận và có origin phù hợp nhưng chỉ được dùng khi subsystem cụ thể hoạt động. Với GC, xác minh tiếp bằng `-Xlog:gc*`; với heap, xem actual memory metrics; với JIT, đọc compilation diagnostics.

## 16. Phương pháp xác nhận cờ bằng smoke test độc lập

Nếu muốn biết một flag Boolean có được HotSpot build hiện tại chấp nhận:

~~~bash
java -XX:+UseG1GC -version
~~~

Kiểm tra **exit status** và output. Khi thành công, lệnh chứng minh:
- option được launcher/VM chấp nhận;
- VM có thể khởi động tới bước in version;
- không có immediate syntax/constraint error trong configuration đó.

Nhưng chưa chứng minh:
- application thực chạy đúng;
- GC event cụ thể đã xảy ra;
- heap limit theo container không gây OOM khi tải;
- throughput hoặc latency có cải thiện.

Nên thêm:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=info -version
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version
~~~

Với flags Boolean khác, kiểm tra tên đúng, nhóm flag product/diagnostic/experimental và version-specific restrictions. Nếu parser trả lỗi, ghi exact error/exit code thay vì thêm `-XX:+IgnoreUnrecognizedVMOptions` để che.

### Cờ GC có thể đổi ý nghĩa theo release

Ví dụ ZGC:
- JDK 21 giới thiệu Generational ZGC dưới dạng mode có thể chọn;
- JDK 23 chọn generational mode mặc định khi đã chọn ZGC;
- JDK 24 loại bỏ non-generational ZGC;
- một số legacy flags như `ZGenerational` tiến tới obsolete/expired ở JDK mới.

**Không nên copy bộ cờ chuyên biệt của một JDK rồi áp dụng nguyên sang JDK khác.** Nếu cần một app image chạy nhiều release, tạo version-specific JVM_ARGS và smoke-test mỗi image.

## 17. System properties, environment variables và injected JVM options

Ba cơ chế khác nhau:

| Nguồn | Ví dụ | Ai xử lý |
| --- | --- | --- |
| CLI system property | `-Ddemo.mode=study` | Launcher/VM cung cấp `System.getProperty` |
| Environment variable ứng dụng | `DEMO_MODE=study` | OS/environment; app đọc `System.getenv` |
| `JDK_JAVA_OPTIONS` | `-Ddemo.mode=study -Xmx128m` | Java launcher prepend trước parsed CLI args |
| `JAVA_TOOL_OPTIONS` | `-Ddemo.mode=study` | JVM startup instrumentation/config path theo implementation/contract |
| `_JAVA_OPTIONS` | Cú pháp nội bộ thường thấy ở một số vendor | Không dùng làm cơ chế portable được cam kết công khai |

**Lưu ý JDK_JAVA_OPTIONS:** theo tài liệu Java command, nó được **prepend** vào options của launcher, in thông báo nhắc trên stderr và **không cho** các options chọn main class hoặc thoát launcher sớm như `-jar`, `-h`. Một `@argument-file` được cho phép theo launcher semantics.

**Lưu ý JAVA_TOOL_OPTIONS:** thường dùng để đưa VM options cho processes có startup được điều khiển bởi một wrapper, nhưng không có cùng quyền xử lý các launcher-only options như JDK_JAVA_OPTIONS; một số runtime environments còn giới hạn injection vì lý do bảo mật.

### Lỗi “đã xóa flag khỏi startup script nhưng vẫn thấy”

Có thể flag đang được inject qua:
- `JDK_JAVA_OPTIONS` hoặc `JAVA_TOOL_OPTIONS`;
- IDE configuration/Gradle JVM args;
- service wrapper/application server;
- Docker `ENTRYPOINT`/`CMD`;
- Helm chart config map/env;
- Kubernetes mutating admissions;
- shell alias hoặc script kế thừa;
- vendor-specific launcher.

Khi điều tra, xem **actual process VM.command_line** và environment injection thay vì chỉ đọc một file startup. Không công khai secrets có thể nằm trong `-Dpassword=...` khi chia sẻ logs; command lines/JVM input args có thể lộ thông tin nhạy cảm.

## 18. Argument files và quoting: tránh lỗi khó nhìn

Java launcher hỗ trợ **@argument file** để lưu nhiều options. Ví dụ file văn bản `vm.args`:

~~~text
-Xms64m
-Xmx256m
-Ddemo.mode=study
-ea
JvmOptionProbe
alpha
beta
~~~

Đây là **nội dung file tham số của launcher**, không phải application data. Nếu `vm.args` tồn tại:

~~~bash
java @vm.args
~~~

Thực hiện tương đương chương trình ở mục 14 nếu môi trường và quoting phù hợp. Cần lưu ý:
- Đây là feature **Java launcher**, không phải mọi wrapper/VM embedding API đều hiểu `@vm.args`.
- Encoding, escaping/quoting và wildcard expansion có quy tắc riêng; xem phần *java Command-Line Argument Files* của đúng JDK.
- Các options trước main class vẫn là launcher/VM options; các tokens sau class là app args.
- Nếu cấu hình chứa whitespace trong property value, dùng quoting đúng shell/argument-file rules.
- Không viết password/token vào argument file có quyền đọc rộng hoặc commit secrets vào source control.

Một số tools như Maven/Gradle cũng sử dụng `@argfile` nhưng **đừng tự động giả định quoting rules/option parser của Java launcher giống toàn bộ tools khác**.

## 19. Cách kiểm tra trên Windows PowerShell

Xác định binary đang dùng:

~~~powershell
Get-Command java
java -version
java -X
~~~

Xem flags có liên quan (lọc output; có thể cần cả stderr tùy tool):

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String "MaxHeapSize|InitialHeapSize|UseG1GC|ActiveProcessorCount"
~~~

Khi cần kiểm tra PID:

~~~powershell
jcmd
jcmd 12345 VM.command_line
jcmd 12345 VM.flags -all
~~~

**12345 là PID minh họa**, phải thay PID thật. Không đọc kết quả từ một Java process khác rồi gán cho service cần điều tra. `jcmd` có thể cần quyền tương ứng (cùng user, attach permissions).

PowerShell có xử lý quoting/escaping khác Bash. Đặc biệt với properties chứa whitespace, hãy kiểm tra argument thực mà JVM nhận bằng Java test app thay vì chỉ dựa vào cú pháp trông hợp lý.

## 20. Cách kiểm tra trên Linux/macOS

~~~bash
command -v java
java -version
java -X
java -XX:+PrintFlagsFinal -version
~~~

Ví dụ lọc:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 |
    grep -E 'MaxHeapSize|UseG1GC|ActiveProcessorCount'
~~~

Dùng `jcmd PID VM.command_line` nếu JVM đang chạy và attach được. Trên container, PID trong host namespace có thể khác PID bên trong container; chạy diagnostics trong đúng namespace/context.

**Không dùng output `ps` làm nguồn duy nhất:** một số wrappers/launchers có thể thay đổi argv hiển thị, và environment-injected flags không nhất thiết xuất hiện đầy đủ ở những công cụ OS thông thường.

## 21. Phân biệt defaults, command line và ergonomics

HotSpot thường tự tính nhiều values theo:
- số logical processors mà JVM nhận diện;
- heap budget/memory limit;
- GC được chọn;
- OS/architecture;
- JDK build, flavor và VM tuning;
- tỷ lệ CPU/quota/container support;
- quan hệ ràng buộc giữa các flags.

Ví dụ, nếu không đặt `-Xmx`, `MaxHeapSize` được HotSpot chọn theo ergonomics. Khi đặt `-Xmx512m`, giá trị cuối khác. Nhưng không phải mọi default value được in là “đã dùng ở runtime”: một flag thuộc collector không được chọn có thể vẫn tồn tại và có giá trị mặc định.

### Tại sao cần nhìn origin?

Cột provenance giúp phân biệt:
- `{default}`: giữ default trong build/context;
- `{ergonomic}`: được VM điều chỉnh theo heuristic;
- `{command line}`: được set qua startup arguments;
- các origins khác có thể liên quan environment, management hoặc attach.

Định dạng/tên origins phụ thuộc build. Không suy rằng source luôn được biểu diễn cùng string qua JDK versions. Nếu nhiều layers thiết lập cùng flag, giá trị cuối và actual command line cần được xem cùng nhau.

### Một cờ không thay thế metric

`-XX:MaxRAMPercentage=65` không chứng minh JVM dùng đúng 65% host RAM; nó là một **input to heap-sizing policy**. `-XX:+UseG1GC` không chứng minh latency <200ms; `-XX:ActiveProcessorCount=2` không giới hạn process chỉ chạy trên hai CPU cores.

Tách *configuration intent*, *effective VM option*, *subsystem behavior* và *business outcome*. Đây là nền tảng của mọi bài kiểm tra cấu hình tài nguyên nghiêm túc.

## 22. Case study: JVM không khởi động sau khi nâng JDK

Một service từng dùng:

~~~text
JAVA_OPTS="-Xms512m -Xmx2g -XX:MaxRAMFraction=4 -XX:+TraceClassLoading"
~~~

Đây là **cấu hình ví dụ lịch sử**, không phải tập flags nên tiếp tục dùng. Trên JDK mới, `TraceClassLoading` hoặc `MaxRAMFraction` có thể bị loại bỏ và làm VM fail.

Quy trình xử lý:
1. Lấy exact stderr, exit code, JDK vendor/build/runtime image.
2. Xác định JVM options đến từ `JAVA_OPTS` của wrapper hay môi trường trực tiếp; `JAVA_OPTS` **không phải biến mà java launcher tự nhận theo chuẩn**, chỉ có effect nếu script sử dụng nó.
3. Chạy mỗi nhóm flags trên **exact JDK**; không sửa production ngay.
4. Tra phần *Removed Options* của release đang dùng.
5. Thay `-XX:+TraceClassLoading` bằng Unified Logging `-Xlog:class+load=info` nếu mục tiêu là quan sát class loading.
6. Cân nhắc thay `MaxRAMFraction` bằng `MaxRAMPercentage` **khi không còn explicit -Xmx**, thay vì giữ một flag thừa.
7. Chạy smoke test `java ... -version`, rồi start ứng dụng với test traffic.
8. Đối chiếu `PrintFlagsFinal`, `VM.command_line`, GC/heap/CPU metrics.
9. Ghi version-conditional config và rollback plan.

**Không chỉ thêm** `IgnoreUnrecognizedVMOptions` để service start, bởi bạn có thể mất các ràng buộc memory mà deployment đang dựa vào.

## 23. Tình huống cờ được nhận nhưng kết quả ngược kỳ vọng

### A. Đặt heap đúng nhưng container vẫn OOMKilled

Nguyên nhân có thể là native memory, metaspace, stacks, direct buffers, JIT code cache, file mappings và GC overhead. Giải pháp không phải chỉ tiếp tục giảm `-Xmx` một cách mù quáng; cần đo NMT/RSS/heap và xét budget toàn process.

### B. Đặt ActiveProcessorCount=2 mà nhìn process vẫn có nhiều threads

Flag ảnh hưởng JVM ergonomics, không phải strict OS thread cap. GC threads, JIT threads, application workers và native libraries vẫn tồn tại theo chính sách riêng.

### C. Bật PrintFlagsFinal nhưng không thấy user-defined property

`-Ddemo.mode=study` là Java system property, không phải `-XX` flag. Kiểm tra bằng Java API hoặc `-XshowSettings:properties` theo JDK thay vì tìm "demo.mode" trong HotSpot flag table.

### D. Đặt -Xmx trước JAR nhưng app báo nó là input

Nếu thật sự JVM thấy flag trước `-jar` và app báo `-Xmx` là argument, có thể launcher wrapper đã reorder tokens. Đọc actual command line từ `VM.command_line` và kiểm tra script/container ENTRYPOINT.

### E. Flag PrintFlagsFinal có value nhưng tính năng không hoạt động

Cờ có thể chỉ là heuristic, ở trạng thái obsolete (không còn effect), hoặc subsystem không được chọn. Đọc warnings, docs và log subsystem; không suy từ một value printed.

### F. Cùng flags nhưng hai JDK cho heap khác nhau

Defaults/ergonomics/container support/architecture/collector có thể khác. Nếu muốn đối chứng hiệu năng, cố định JDK hoặc ghi rõ version là một biến độc lập.

## 24. Quy trình kiểm định JVM args trong CI/CD

Một pipeline đáng tin nên dùng đúng runtime image production.

**Tầng A — Syntax / startup smoke:**
- Capture `java -version`.
- Chạy `java [JVM_FLAGS] -version` trên exact binary.
- Assert exit code = 0, không có warning không được chấp nhận.
- Không dùng `IgnoreUnrecognizedVMOptions` trừ khi đã chứng minh lý do.

**Tầng B — Effective configuration:**
- Chạy `java [JVM_FLAGS] -XX:+PrintFlagsFinal -version`.
- Lấy các flags quan trọng: `MaxHeapSize`, `InitialHeapSize`, selected GC, `ActiveProcessorCount`, metaspace/code cache nếu cần.
- So với budget và constraints của deployment, không compare nguyên văn output giữa releases.

**Tầng C — Application smoke:**
- Khởi động JAR/class thật, kiểm tra entrypoint, module/classpath và app arguments.
- Health check sẵn sàng, basic request, timeout, error logs, resource availability.
- Kiểm tra đúng runtime process bằng `jcmd PID VM.command_line` khi có quyền.

**Tầng D — Load/performance verification:**
- GC logs, heap/RSS/CPU throttling, NMT (nếu bật), p95/p99 end-to-end latency.
- Đặt budgets và limits, đừng dùng flags như KPI.
- Canary + rollback khi thay JDK/GC/heap.

**Tầng E — Configuration governance:**
- Lưu exact JDK vendor/build, JVM args, environment-provided args và generated manifests.
- Có owner cho mỗi non-default flag: vì sao bật, baseline đo, cách verify, kế hoạch xóa.
- Thêm test cho cả khi thiếu flag và khi bị deprecated/obsolete.
- Xem xét secrets trong system properties và logs.

## 25. Không dùng flags theo kiểu “bộ sưu tập tối ưu hiệu năng”

Cấu hình:

~~~text
-Xms4g
-Xmx4g
-XX:+AlwaysPreTouch
-XX:+UseG1GC
-XX:ActiveProcessorCount=2
-XX:MaxMetaspaceSize=128m
-XX:ReservedCodeCacheSize=64m
~~~

có thể phù hợp một số experiments nhưng **không phải cấu hình tốt cho mọi Java server**. Ví dụ:
- `-Xms=-Xmx` có thể làm tăng committed memory; đổi lại heap size ổn định hơn trong tình huống nhất định.
- `AlwaysPreTouch` có thể làm startup dài hơn và memory commitment khác.
- Metaspace 128 MiB có thể quá nhỏ cho ứng dụng dùng nhiều frameworks/proxies.
- Code cache 64 MiB có thể chặn JIT compilation trên workload lớn.
- ActiveProcessorCount=2 có thể làm GC/JIT/pool heuristics dưới mức hardware thực nếu được đặt sai.

Một configuration nên có **tài nguyên mục tiêu, profile workload, chứng cứ đo và rollback**. Đừng giữ flags chỉ vì copy từ một bài viết về Java 8.

## 26. Bài tập thực hành

### Bài 1 — Phân loại options

Phân loại trong lệnh:

~~~bash
java -Ddemo.env=test -Xmx512m -XX:+UseG1GC -jar app.jar hello
~~~

**Đáp án:** `-D` standard launcher property; `-Xmx` extra; `-XX:+UseG1GC` advanced; `-jar` standard launch mode; `hello` application argument.

### Bài 2 — Sai vị trí

Lệnh:

~~~bash
java -jar app.jar -Xmx512m
~~~

**Đáp án:** `-Xmx512m` đi vào app args theo launcher target grammar, không cấu hình maximum heap.

### Bài 3 — Boolean flag

Muốn bật G1 trong HotSpot dùng `-XX:+UseG1GC`, không dùng `-XX:UseG1GC` tùy tiện. Để tắt một Boolean flag, cú pháp cơ bản `-XX:-FlagName` — nhưng **đừng tắt G1** nếu không xác định GC thay thế và constraints.

### Bài 4 — Value flag

Muốn gợi ý JVM tự sizing heap từ memory budget với `MaxRAMPercentage`, dùng mẫu `-XX:MaxRAMPercentage=65`, không phải `-XX:+MaxRAMPercentage`.

### Bài 5 — Cờ có hỗ trợ hay không?

Đề xuất ba kiểm tra:
1. Tra Java command docs của **đúng release**.
2. Chạy một smoke test bằng exact binary và đọc exit status/warnings.
3. Kiểm tra `PrintFlagsFinal`/`jcmd` và feature logs trong application workload.

### Bài 6 — Vì sao `-Xmx=1g` chưa đủ khống chế container 1 GiB?

**Đáp án:** Heap không phải toàn bộ process memory. Native memory, metaspace, stacks, direct buffers, JIT và mappings còn chiếm thêm.

### Bài 7 — Vì sao `-XX:+IgnoreUnrecognizedVMOptions` rủi ro?

**Đáp án:** Nó có thể che cờ bị xóa/đánh sai, khiến JVM chạy với defaults thay vì resource limits dự kiến.

### Bài 8 — Phân biệt PrintFlagsFinal và VM.command_line

**Đáp án:** PrintFlagsFinal giúp xem effective VM flag values tại startup; VM.command_line phản ánh command-line JVM process đã nhận. Kết hợp cả hai để biết ý định và kết quả.

### Bài 9 — Vì sao `java -X` không liệt kê mọi -XX?

**Đáp án:** Nó là help cho extra options được launcher công bố; các -XX flags có nhóm/level riêng, nhiều flags còn bị gated/implementation-specific.

### Bài 10 — Một cờ obsolete được parser chấp nhận, có nghĩa nó còn hoạt động không?

**Đáp án:** Không. Obsolete thường được chấp nhận rồi bỏ qua với warning. Phải xem lifecycle và behavior.

### Bài 11 — -D không thấy trong PrintFlagsFinal?

**Đáp án:** Vì system property khác VM flag. Kiểm tra bằng `System.getProperty` hoặc VM/launcher property diagnostics thích hợp.

### Bài 12 — Một process chạy trong Docker nhận MaxHeapSize nhỏ hơn mong đợi dù host có 64 GiB?

**Đáp án:** Container memory limit/HotSpot ergonomics/flags có thể khiến JVM chỉ xem budget nhỏ hơn host. Xác minh exact process flags/container limits.

### Bài 13 — Java source-level preview option có phải -XX advanced flag?

**Đáp án:** Không. `--enable-preview` thuộc launcher/compiler workflow liên quan preview language/API features; nó không đồng nghĩa experimental VM GC flag.

### Bài 14 — Cần unlock flags chẩn đoán bằng cách nào?

**Đáp án:** Dùng `-XX:+UnlockDiagnosticVMOptions` trước những flags được đánh dấu diagnostic, trên HotSpot build có hỗ trợ. Không tự đặt cờ không tồn tại.

### Bài 15 — Một flag từng chạy trên JDK 8 nhưng JDK 25 fail: JVM bị lỗi?

**Đáp án:** Không nhất thiết. Flag có thể đã removed/expired. Tra docs đúng JDK, thay bằng option được hỗ trợ, test behavior.

## 27. Bản đồ tư duy

~~~text
                     java LAUNCHER
                           |
         +-----------------+-----------------+
         |                 |                 |
      STANDARD            -X               -XX
 -D, -cp, -jar         -Xms/-Xmx       +Flag / -Flag
 --module-path         -Xss, -Xlog     Flag=value
 --version, -ea        -Xint, -X       GC/JIT/memory
         |                 |                 |
         +-----------------+-----------------+
                           |
                 EXACT JDK VENDOR/BUILD
                           |
                   ARE FLAGS ACCEPTED?
               /                         \
             NO                           YES
             |                             |
        stop; fix                    ACTIVE vs OBSOLETE?
        version/syntax              /               \
                                   warning?         effect?
                                      |                |
                                inspect docs       PrintFlagsFinal
                                                   jcmd VM.flags
                                                      |
                                               SUBSYSTEM LOGS
                                                      |
                                                RESOURCE METRICS
                                                      |
                                               APPLICATION SLO
                           |
                  DO NOT CONFUSE WITH:
             app arguments after main/-jar
             env JAVA_TOOL_OPTIONS
             JDK_JAVA_OPTIONS
             process RSS vs Java heap
             parser acceptance vs semantic effect
~~~

**Tổng kết:** Tùy chọn **standard**, **-X** và **-XX** khác nhau về parser, phạm vi, mức ổn định và mục đích. Trước khi đưa một flag vào cấu hình tài nguyên, hãy kiểm tra **đúng Java binary/version**, đọc `java --help`/`java -X` và tài liệu release, chạy startup smoke, xem **effective VM flags** bằng `PrintFlagsFinal` hoặc `jcmd`, rồi xác nhận behavior và resources bằng logging/metrics. Một flag đã được chấp nhận vẫn có thể obsolete hoặc không phù hợp workload; một flag đã được set không phải bảo đảm hiệu năng. Hãy quản lý JVM args như **cấu hình vận hành có phiên bản, có bằng chứng và có rollback**, không phải tập hợp các mẹo không kiểm chứng.

## Tài liệu tham khảo

- [Oracle JDK 17 — The java Command, Standard/Extra/Advanced options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Oracle JDK 21 — The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle JDK 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
- [Oracle JDK 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
- [Dev.java — Java Application Launcher: Standard, -X and -XX options](https://dev.java/learn/jvm/tools/core/java/).
- [Oracle JDK 17 — jcmd utility](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html).
- [Oracle JDK 17 — jinfo utility](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jinfo.html).
- [Oracle JDK 17 — Java ManagementFactory and RuntimeMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html).
- [Oracle JDK 17 — HotSpotDiagnosticMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html).
- [Oracle JDK 17 — VMOption and Origin](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/VMOption.html).
- [OpenJDK HotSpot runtime — arguments.cpp, deprecated/obsolete/expired flags](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/arguments.cpp).
- [OpenJDK — JEP 158, Unified JVM Logging](https://openjdk.org/jeps/158).
- [OpenJDK — JEP 271, Unified GC Logging](https://openjdk.org/jeps/271).

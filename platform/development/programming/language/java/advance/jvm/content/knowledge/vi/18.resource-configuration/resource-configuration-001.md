# Nhận diện đúng JDK, nhà cung cấp, phiên bản VM và kiến trúc đang chạy

## 1. Bài toán: “máy này cài Java 17” chưa trả lời được điều gì?

Khi cấu hình tài nguyên, chọn bộ thu gom rác, chạy chương trình cần JNI, điều tra một lỗi triển khai hoặc tối ưu HotSpot, câu hỏi cần trả lời không chỉ là “máy có Java hay không”. Cần biết chính xác **tiến trình Java đang chạy thật sự dùng runtime nào**, **nhà cung cấp nào**, **VM implementation/build nào** và **kiến trúc nào**.

Có ít nhất bốn lớp dễ bị lẫn:

1. **JDK dùng để build**: `javac`, `jar` và các công cụ mà CI/IDE đã gọi.
2. **Java launcher dùng để khởi chạy**: file thực thi `java` được giải quyết qua đường dẫn tuyệt đối, `PATH`, wrapper hoặc container entrypoint.
3. **JVM đang thực thi application process**: thông tin thật do `Runtime.version()`, `System` properties và `jcmd` của **đúng PID** báo.
4. **Host/OS/container/native ABI**: nơi tiến trình đang chạy, giới hạn CPU/memory, kiến trúc thực tế của binary và thư viện native.

Bốn lớp có thể **không trùng nhau**. Ví dụ:

```text
Developer laptop:
  JAVA_HOME = /opt/jdk17
  PATH      = /usr/local/bin:/opt/jdk21/bin:...

Build pipeline:
  ./gradlew chạy bằng JDK 21 nhưng --release 17 khi compile

Production container:
  /opt/runtime/bin/java là custom JDK 17 image
  host kernel báo x86_64, container giới hạn 2 CPUs

Ứng dụng:
  System.getProperty("java.vendor") và
  System.getProperty("java.vm.name") đến từ process runtime
```

Không lấy giá trị `JAVA_HOME` của shell hiện tại để khẳng định process khác đang dùng đúng runtime ấy; không nhìn `javac -version` rồi suy version JVM của service; không nhìn `uname -m` trên host rồi khẳng định architecture của mọi JVM trong container.

**Mục tiêu của bài**: nhận diện chính xác runtime identity, phân biệt **Java feature release / update / build**, **vendor / VM name / VM version**, **OS/CPU architecture / process bitness / native ABI**, đọc cấu hình của **đúng process**, và xây một checklist điều tra có thể tái lập trên **Java 17+**.

---

## 2. Bộ câu hỏi tối thiểu phải trả lời trước khi tuning

Trước khi áp dụng `-Xmx`, `-Xss`, `-XX:+UseG1GC` hay mở JNI library, ghi rõ:

| Câu hỏi | Nguồn thường dùng | Vì sao quan trọng? |
| --- | --- | --- |
| JVM đang dùng Java feature bao nhiêu? | `Runtime.version().feature()`, `java.version` | Kiểm tra APIs/class-file compatibility |
| Chính xác release/update/build nào? | `Runtime.version()`, `java -version` | Vá lỗi, compiler/GC behavior và sự cố vendor-specific |
| Ai phân phối runtime? | `java.vendor`, `java.vendor.url` | Hỗ trợ, security updates, distribution |
| JVM implementation nào? | `java.vm.name`, `java.vm.vendor` | HotSpot/OpenJ9 hay implementation khác có option khác |
| Phiên bản VM implementation? | `java.vm.version`, `jcmd PID VM.version` | Diagnostics và flags phụ thuộc build |
| Runtime được cài ở đâu? | `java.home`, executable command/path | Dò launcher hay thư viện đi kèm đúng runtime |
| Runtime process là kiến trúc gì? | `os.arch` cộng OS binary inspection | Chọn đúng JNI native lib, CPU-specific features |
| Runtime có phải 64-bit? | VM output, binary/ABI tools, HotSpot-specific `sun.arch.data.model` | Native pointer width, address space, memory limits |
| Host OS và container ra sao? | `os.name`, container/OS tools, `-XshowSettings:system` (khi hỗ trợ) | CPU quota, memory limits và Linux cgroup |
| Effective VM flags là gì? | `jcmd PID VM.flags`, `-XX:+PrintFlagsFinal` | Các ergonomic defaults có thể khác options khai báo |
| Java executable và javac có cùng JDK? | Absolute paths, `java -version`/`javac -version` | Tránh build đúng nhưng deploy sai |
| Đúng PID ứng dụng đang quan tâm chưa? | PID + `VM.command_line` + `VM.version` | Một máy có thể chạy nhiều Java services |

Chụp thông tin theo **process và thời điểm thực tế**, nhất là sau rolling deployment hoặc khi pods được thay thế.

## 3. Java release, patch, build: đừng chỉ đọc “17”

**Java feature version** là đời ngôn ngữ/API lớn như 8, 11, 17, 21. Các bản cập nhật của cùng feature release có thể khác đáng kể về bug fixes, security patches, hỗ trợ CPU/OS và HotSpot behavior.

Từ Java 10, version string được giải thích theo các thành phần:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
       -<PRE_RELEASE>+<BUILD>-<OPTIONAL>
```

Những thành phần zero ở cuối thường được lược bỏ; nhãn prerelease/build/optional metadata phụ thuộc release và vendor.

Ví dụ **minh họa định dạng**, không phải khẳng định đó là bản mới nhất:

```text
17.0.12+7
  feature = 17
  interim = 0
  update  = 12
  patch   = 0 (vắng mặt trong string)
  build   = 7
```

Với Java 17:

```java
Runtime.Version v = Runtime.version();
int feature = v.feature();
int interim = v.interim();
int update = v.update();
int patch = v.patch();
java.util.Optional<Integer> build = v.build();
```

Đây là **đoạn API minh họa**; file chạy độc lập ở mục 10. `Runtime.Version` cũng cung cấp thông tin về pre-release/optional metadata. Không tự phân tích version string bằng `split("\\.")` rồi giả định mọi build chỉ có ba số thuần: có thể còn dấu `+`, prerelease tag hoặc vendor-specific metadata.

### 3.1. Vì sao version feature không đủ để đánh giá compatibility?

- **Class files:** Java 17 có major class-file version **61**. Runtime Java 11 không thực thi được class major 61 theo spec thông thường.
- **API:** `javac --release 17` kiểm soát source/target/public API compatibility cho Java 17, nhưng không biến native library của kiến trúc này chạy trên kiến trúc khác.
- **JVM options:** hai HotSpot 17 patch builds có thể khác behavior/diagnostics hỗ trợ hoặc default heuristics.
- **Binary archive:** một CDS archive tạo từ JDK build A không được coi là portable sang JDK build B chỉ vì đều in “17”.
- **Security:** một runtime cũ và một runtime mới cùng Java 17 có thể khác security fixes.

### 3.2. `java.version`, `java.runtime.version` và `java.vm.version` khác nhau

| Property | Ý nghĩa chính | Không nên suy ra |
| --- | --- | --- |
| `java.version` | Version của Java Runtime Environment | Không phải toàn bộ identity của JVM binary |
| `java.runtime.version` | Version string của Java runtime nếu implementation cung cấp | Không nhất thiết là same string với JVM version |
| `java.vm.version` | Version của VM implementation | Không tự xác định Java launcher path |
| `java.specification.version` | Java SE runtime specification feature version | Không gồm vendor/patch/build |
| `java.vm.specification.version` | JVM specification version | Không bằng JIT compiler implementation version |
| `java.class.version` | Highest class-file format version runtime báo hỗ trợ | Không có nghĩa từng class đang tải đều đã compile với version ấy |

**Lưu ý:** JDK 17 `System` API mô tả các chuẩn system properties, nhưng một số property mang tính implementation-specific, optional hoặc có thể bị code/lệnh chạy thay đổi. Kết luận quan trọng nên **đối chiếu ít nhất hai nguồn**, ví dụ `java -version`, `System` runtime properties và `jcmd PID VM.version`.

### 3.3. Không nhầm JVM specification vendor với runtime vendor

Ví dụ `java.vm.specification.vendor` mô tả **bên ban hành JVM specification**; nó không nhất thiết là nhà cung cấp binary HotSpot mà bạn đang chạy. Để xác định distribution/vendor, ưu tiên đọc `java.vendor`, và đối chiếu `java.vm.vendor`, `java.vm.name` và startup banner.

## 4. Vendor, distribution, implementation và “VM name”

**Vendor/distribution** trả lời “ai xây dựng/phân phối/support runtime mà bạn cài?”. **Implementation** trả lời “bộ máy JVM nào thực thi bytecode/JIT/GC?”. Một vendor có thể phân phối nhiều dạng runtime; ngược lại nhiều vendors cùng xây dựa trên OpenJDK/HotSpot.

| Thành phần | Ví dụ minh họa | Điều cần nhớ |
| --- | --- | --- |
| JDK distribution/vendor | Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK | Vendor không tự xác định GC/VM implementation |
| VM implementation | HotSpot, Eclipse OpenJ9, GraalVM Java runtime dựa trên HotSpot trong các cấu hình | Diagnostics/flags có thể khác |
| `java.vm.name` | Có thể báo `OpenJDK 64-Bit Server VM` hoặc dạng vendor-specific | Chuỗi không phải tiêu chuẩn định danh duy nhất |
| `java.vm.vendor` | VM implementation vendor/distributor metadata | Có thể khác `java.vendor` hoặc cùng giá trị |
| `java.vm.version` | VM build/version | Không suy “VM build number = JDK patch number” |
| `java.home` | Directory của Java runtime hiện tại | Không phải `JAVA_HOME` của build shell |
| `java.vendor.version` | Vendor version, nếu cung cấp | Có thể vắng mặt (`null`) |

**Tên “OpenJDK” không có nghĩa vendor duy nhất**. OpenJDK là dự án mã nguồn và nhiều distributions được xây từ nó. “OpenJDK 64-Bit Server VM” mô tả một loại VM; vendor ở field khác.

### 4.1. Vendor string có ổn định như một enum không?

Không. Vendor tên có thể thay đổi theo distribution/build hoặc cách đóng gói; là **chuỗi nhận diện**, không phải enum chuẩn có cố định toàn bộ các hãng.

Không viết logic production:

```java
if (System.getProperty("java.vendor").equals("Oracle Corporation")) {
    // Sai khi coi mọi implementation khác chắc chắn không hỗ trợ API Java 17.
}
```

Đoạn trên là **phản ví dụ**. Nếu cần Java API version, dùng `Runtime.version().feature()` và feature-detection hợp lý. Nếu cần một **HotSpot-only flag**, kiểm tra **VM implementation + actual flag availability**; đừng giả định chỉ một vendor mới có HotSpot.

### 4.2. “JDK 17” không đảm bảo VM là HotSpot

Một số Java 17 distributions có thể sử dụng VM implementation khác HotSpot. Những tools/options như `-XX:+PrintFlagsFinal`, Native Memory Tracking, `jcmd` subcommands và HotSpot code cache/G1 internals không phải Java SE portable API.

Nếu `java.vm.name` là OpenJ9 hoặc một VM khác, dùng **manual đúng implementation** thay vì áp một bộ HotSpot diagnostics và kết luận “JVM bị lỗi vì không nhận flag”.

## 5. JDK vs JRE/runtime image vs Java launcher vs `javac`

Trước đây người học hay phân biệt JDK/JRE, nhưng với JDK 17 bạn còn có **custom runtime image** được xây bằng `jlink`. Ứng dụng có thể chạy bằng một runtime image **không có `javac`**, dù Java 17 runtime đầy đủ cho modules ứng dụng cần.

```text
JDK đầy đủ:
  bin/java
  bin/javac
  bin/jar
  bin/jcmd
  ... modules/tools

Custom runtime (jlink):
  bin/java
  modules được chọn
  có thể không chứa javac/jcmd
```

**`java.home`** trong process chỉ ra runtime installation directory thực tế mà JVM báo. Việc nó không có compiler `javac` không chứng minh “không phải Java 17” hoặc “runtime hỏng”.

### 5.1. Các lệnh cần chạy trên đúng máy

**Linux/macOS (POSIX shell):**

```bash
command -v java
command -v javac
type -a java
type -a javac
java -version
javac -version
printf '%s\n' "$JAVA_HOME"
"$JAVA_HOME/bin/java" -version
```

Các lệnh dùng `"$JAVA_HOME/bin/java"` giả định `JAVA_HOME` **đã được thiết lập đúng và trỏ tới JDK hợp lệ**; nếu biến rỗng/không tồn tại, lệnh sẽ thất bại. `type -a` là tiện ích thường có trong Bash, không phải tính năng portable của mọi POSIX shells. Trên macOS, `readlink -f` không phải luôn sẵn có; đừng chép hướng dẫn Linux symlink resolution sang macOS mà không kiểm tra.

**Windows PowerShell:**

```powershell
Get-Command java -All
Get-Command javac -All
java -version
javac -version
$env:JAVA_HOME
& "$env:JAVA_HOME\bin\java.exe" -version
```

Cần phân biệt **PowerShell PATH resolution**, function/alias/wrapper và đường dẫn binary cuối cùng. Một shell có thể gọi script shim, package manager launcher hoặc symlink chứ không nhất thiết `java.exe` trực tiếp.

### 5.2. Vì sao `java -version` và `javac -version` có thể khác?

- `PATH` ưu tiên binary `java` của JDK A, còn `javac` của JDK B.
- Build tools dùng Java Toolchains và chọn riêng compiler của JDK khác.
- IDE dùng project SDK hoặc boot JDK riêng shell.
- Maven/Gradle daemon đã khởi động từ trước với một JDK khác.
- CI worker đã cấu hình `JAVA_HOME` sau khi daemon/service khởi động.
- Runtime image chỉ có Java launcher, compiler đến từ JDK khác.
- Container runtime image khác builder stage.

Nếu `javac` thuộc JDK 21 còn `java` thuộc JDK 17, lệnh compile mặc định tạo class version mới hơn có thể gây `UnsupportedClassVersionError` lúc chạy. Dùng `javac --release 17` để target Java 17 và **test trên chính runtime target**, không chỉ nhìn toolchain tên “Java”.

### 5.3. `java -version` không phải `java --version` của mọi JVM cổ

Trên Java 17 launcher, cả `-version` và `--version` đều được hỗ trợ. Một số hướng dẫn cũ dành cho Java 8 có syntax khác; xác định JDK trước khi áp flags hiện đại.

**Lưu ý output stream:** `java -version` truyền thống thường ghi banner ra **standard error**, còn `java --version` được thiết kế để in version ra standard output trong launcher phổ biến. Không xây pipeline phụ thuộc stdout của một variant nếu chưa kiểm tra shell redirection.

## 6. Architecture: host, process, JVM bitness, CPU và native ABI

**`os.arch` là tên kiến trúc được Java runtime báo**, ví dụ thường gặp `amd64`, `x86_64`, `aarch64` hay `arm64` tùy implementation/platform. Nó là **một tín hiệu về runtime environment**, không phải mô tả đầy đủ của CPU host, tập lệnh CPU thực tế hay layout của mọi thư viện native.

```text
                     Physical machine
                      architecture
                            │
                   OS kernel / hypervisor
                            │
             container / VM / process namespace
                            │
                   executable architecture
                            │
                 JVM process data model
                            │
                 os.arch / java.vm.name
                            │
               JNI native libraries (ABI)
```

Các giá trị có thể trùng nhau trong hệ thông thường, nhưng không được mặc định điều đó trong mọi trường hợp cross-arch emulation, Rosetta, WoW64, multi-arch containers hoặc remote development.

### 6.1. `os.arch` không phải `uname -m` trong mọi môi trường

- `System.getProperty("os.arch")` là giá trị JVM cung cấp cho **process runtime**.
- `uname -m` thường là công cụ shell hỏi về kernel/machine architecture; trong virtualized/emulated environments có thể khác điều JVM báo.
- OS/container image có thể là một architecture cụ thể trong khi developer host là architecture khác.
- CPU có thể hỗ trợ extension như AVX nhưng `os.arch` thường không cho biết toàn bộ extension flags.
- Chuỗi `amd64` và `x86_64` thường biểu thị cùng họ kiến trúc trong nhiều hệ sinh thái, nhưng không thể dùng simple string comparison làm chứng nhận native library compatibility.

**Nếu triển khai JNI/JNA**, cần chọn native binary đúng **OS + instruction set + process bitness + ABI + C runtime/linker requirements**, không chỉ trùng tên `os.arch`.

### 6.2. 32-bit vs 64-bit: ba phép đo khác nhau

1. **Java primitive `long` luôn 64-bit**, bất kể JVM là 32-bit hay 64-bit. `int` luôn 32-bit theo Java language specification.
2. **Native pointer size** thuộc process ABI; trên một JVM 64-bit thông thường có pointers 64-bit, nhưng **Compressed Oops** có thể dùng compressed references nội bộ.
3. **`sun.arch.data.model`** thường trả `32` hoặc `64` trong **HotSpot-related implementations**, nhưng là **implementation-specific property**, không được coi là Java SE standard portable API.

```java
System.out.println(Integer.SIZE);  // 32
System.out.println(Long.SIZE);     // 64
```

Đây là **snippet**; nó chứng minh width của Java primitive types, **không chứng minh** bitness của JVM process.

### 6.3. Những nguồn kiểm tra native architecture đáng tin hơn khi cần

**Linux:**

```bash
uname -m
file /path/to/java
readelf -h /path/to/java
```

`readelf` cần gói binutils và ELF executable; `file` có thể theo symlink nếu thêm option phù hợp. Trên macOS:

```bash
uname -m
file /path/to/java
lipo -info /path/to/java
```

`lipo` chỉ phù hợp với Mach-O/universal binaries. Trên Windows dùng PowerShell/system tools để kiểm tra **OS architecture, process architecture và PE executable architecture**; các API/công cụ cụ thể phụ thuộc Windows version và môi trường.

Không suy process bitness chỉ từ RAM size, heap `-Xmx` hay Java primitive sizes.

### 6.4. CPU architecture ảnh hưởng những quyết định JVM nào?

- Lựa chọn native JNI libraries `.so`/`.dll`/`.dylib`.
- CPU-specific JIT intrinsics/vector instructions và khả năng hỗ trợ hardware.
- Default thread stack size và memory layout theo platform.
- HotSpot ports và tập JVM flags có hỗ trợ hay không.
- Container multi-arch image selection, cross-build.
- Performance baseline: cùng code Java có thể có tốc độ khác trên x64/ARM64.
- CDS/custom VM archive compatibility và native-image artifacts.

Architecture không quyết định duy nhất GC latency; CPU quota, memory speed, JDK implementation, workload và compiler policy còn ảnh hưởng lớn.

## 7. Java System properties: đọc đúng nhưng không tuyệt đối hóa

Java SE 17 có bộ thuộc tính tiêu chuẩn/được runtime định nghĩa qua `System.getProperty(...)`. Chúng rất tiện cho **thông tin tiến trình đang chạy**, song có giới hạn:

- System properties là các giá trị **có thể đọc và một số trường hợp có thể ghi lại** bằng `System.setProperty` hoặc `-Dkey=value`; đừng lấy một string làm chứng thực chống giả mạo.
- Không phải mọi property mà tutorial trên mạng nêu đều là chuẩn Java SE.
- Vendor-specific properties có thể thiếu hoặc đổi tên.
- `java.home` chỉ ra runtime home, nhưng quá trình launch từ wrapper có thể che nguồn executable ngoài JVM.
- `os.arch` mô tả JVM environment, không chứng nhận mọi CPU feature/native ABI.
- Thu thập property list cần tránh đưa secrets/cấu hình nhạy cảm vào logs.

### 7.1. Nhóm nhận diện cốt lõi

| Property | Dùng để biết | Cẩn trọng |
| --- | --- | --- |
| `java.version` | Java runtime version | Phân biệt feature và full build |
| `java.runtime.version` | Runtime build string nếu có | Có thể khác `java.vm.version` |
| `java.vendor` | Java runtime vendor | Không suy VM implementation |
| `java.vendor.version` | Vendor-specific optional version | Có thể null |
| `java.home` | Runtime installation location | Không bằng shell JAVA_HOME bắt buộc |
| `java.vm.name` | VM implementation name | Không phải một enum portable |
| `java.vm.vendor` | Vendor VM | Có thể khác java.vendor |
| `java.vm.version` | VM implementation version | So cùng PID |
| `java.vm.info` | Một số HotSpot VMs báo build/mode info | Không phải portable Java SE property |
| `java.specification.version` | Spec feature version | Không chứa patch/security build |
| `java.vm.specification.version` | VM specification version | Khác implementation version |
| `java.class.version` | Max class-file version runtime nhận | Java 17 thường `61.0` |
| `os.name` | OS name | Không tự mô tả distro/kernel |
| `os.arch` | JVM-reported architecture | Không thay native ABI test |
| `os.version` | OS version property | Trong containers, host kernel và userspace khác |
| `sun.arch.data.model` | HotSpot-family-specific 32/64 model | Optional/nonportable; có thể thiếu |
| `java.class.path` | Java classpath system property | Có thể không mô tả đầy đủ module layer/custom loader |
| `java.library.path` | Native library search path | Không đảm bảo library ABI tương thích |
| `jdk.module.main` | Tên main module trên một số modular launches | Có thể null; không luôn có |
| `user.dir` | Current working directory | Không chứng minh JDK installation |

### 7.2. Không in mọi `System.getProperties()` trong production log

`System.getProperties()` có thể bao gồm classpath, user directories và những system properties do ứng dụng gắn chứa passwords/tokens/endpoint nội bộ. Một diagnostic tool in mọi property ra log sẽ tăng rủi ro lộ bí mật.

Ưu tiên **allowlist các trường nhận diện**. Khi dùng `-XshowSettings:properties` hoặc `jcmd PID VM.system_properties` trên môi trường production, hạn chế quyền truy cập và nơi lưu output.

## 8. `java -version`, `-XshowSettings` và `-XX:+PrintFlagsFinal`

### 8.1. Lệnh launcher

```bash
java -version
java --version
```

Thường cung cấp Java release, runtime distribution và VM banner. Ví dụ định dạng **minh họa**, không phải output chính xác ở mọi build:

```text
openjdk version "17.0.x" ...
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ... (mixed mode, sharing)
```

“mixed mode” thường liên quan interpreter và JIT compiled execution; “sharing” có thể chỉ CDS support/use theo HotSpot banner. **Không lấy banner là bằng chứng duy nhất** về flags/GC mode đang dùng, đặc biệt trên VM implementation khác.

### 8.2. In các system properties của JVM đang khởi chạy

```bash
java -XshowSettings:properties -version
```

Có thể tìm:

```text
java.home = ...
java.runtime.version = ...
java.vendor = ...
java.version = ...
java.vm.name = ...
java.vm.vendor = ...
java.vm.version = ...
os.arch = ...
os.name = ...
sun.arch.data.model = ...  (nếu build có)
```

Đây là **hình thức hiển thị minh họa**, giá trị thực phụ thuộc môi trường; các dòng có thể xuất hiện ở standard error và theo format của launcher. Dùng `-XshowSettings:vm` để xem một số VM settings; đừng suy nó tương đương dump toàn bộ flags.

### 8.3. Cấu hình effective flags

```bash
java -XX:+PrintFlagsFinal -version
```

Trên HotSpot, lệnh có thể in rất nhiều flags, bao gồm ergonomic defaults do VM tự chọn. Một cờ có thể được:

- Đặt bằng command line.
- Đặt qua environment/wrapper.
- Chọn bởi ergonomics dựa trên CPU/heap/container settings.
- Có default khác giữa JDK versions.
- Không tồn tại trên VM implementation khác.

Vì vậy chỉ nhìn Dockerfile có dòng `-Xmx2g` không đủ để biết **mọi effective JVM flags** của process. Cần xem process thực đang chạy và runtime tooling.

**Cẩn trọng output:** `PrintFlagsFinal` rất dài, phần lớn không liên quan bài toán; lọc đúng flags và version thay vì dump vào issue tracker chứa bí mật.

### 8.4. Đọc thông tin container trên Linux

Với HotSpot Java 17 được hỗ trợ, launcher có:

```bash
java -XshowSettings:system -version
```

Trên **Linux**, category `system` cung cấp thông tin host hoặc container configuration theo implementation; trên OS khác có thể không hỗ trợ hoặc hiển thị khác.

Dùng để kiểm tra container-related CPU/memory limits **khi hoạt động**. Không dùng nó để thay toàn bộ cgroup tools khi cần forensic diagnosis; VM chỉ báo những gì nó thấy và hỗ trợ theo JDK update/build.

## 9. Nhận diện đúng process với `jcmd` trên HotSpot

Nếu cần điều tra một service đang chạy, **đừng mở terminal rồi chỉ gọi `java -version`**: lệnh đó có thể chạy binary khác với JVM process của service. Hãy hỏi chính **PID** ấy bằng công cụ phù hợp.

Trên HotSpot JDK 17:

```bash
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.system_properties
jcmd <pid> VM.flags
jcmd <pid> VM.info
```

`<pid>` là placeholder phải thay bằng PID hợp lệ. Không chép nguyên dấu `<`/`>` vào shell; đó không phải cú pháp PID.

- **`VM.version`:** thông tin phiên bản JVM đích.
- **`VM.command_line`:** cách JVM đích được khởi chạy, hỗ trợ đối chiếu options.
- **`VM.system_properties`:** system properties **trong JVM đích** (có thể có dữ liệu nhạy cảm).
- **`VM.flags`:** các JVM flags đang có hiệu lực theo khả năng của VM.
- **`VM.info`:** thông tin VM/environment/status mở rộng.
- **`jcmd -l`:** liệt kê JVM processes mà công cụ có thể nhìn thấy/attach phù hợp.

Diagnostic commands phụ thuộc runtime implementation/build và quyền thực thi. Cần cùng host/namespace thích hợp, OS permissions và khả năng attach; process có thể ngăn attach hoặc đã chết.

### 9.1. PID và container namespaces

Khi app chạy trong container:

```text
Host PID:            12345 (ví dụ)
Container PID:           1 (ví dụ)
JVM process namespace:   phụ thuộc container runtime
```

`jcmd` chạy trên host và `jcmd` chạy trong container **có thể thấy PID khác**. Đừng gửi `jcmd 1` trên host rồi nghĩ chắc chắn đang nói với PID 1 của container. Dùng `docker exec`/`kubectl exec` với đúng target container nếu quyền/hệ thống cho phép, hoặc map PID đúng qua các công cụ container/OS.

### 9.2. Lệnh `jcmd` không nhất thiết có trong runtime image

Custom image từ `jlink` hoặc container minimal có thể chỉ chứa `bin/java`, không có `jcmd`. Cần tool image cùng runtime family/version và quyền attach phù hợp, hoặc ghi allowlisted runtime identity ở startup. **Không cài lại JDK vào production container chỉ để có một lần `jcmd` nếu việc đó làm đổi runtime và phá tính reproducible**.

### 9.3. Công cụ đang chạy khác công cụ attach

`jcmd` từ JDK A có thể không hoàn toàn tương thích/quyền với JVM B. Kết quả đáng tin nhất là dùng tools từ cùng distribution/build hoặc bộ công cụ được nhà cung cấp hỗ trợ để quan sát process đích.

### 9.4. VM flags không phải Java language specification

`-XX:+UseG1GC` là HotSpot option, không phải Java source-level feature. `-Xmx` là launcher option phổ biến, nhưng interpretation và collector choices có implementation-specific dimensions. Nếu `java.vm.name` báo implementation khác, tra tài liệu đúng VM trước khi dùng các `-XX` flags.

## 10. Java 17 runnable demo: in “runtime fingerprint” của chính process

Lưu file **`RuntimeFingerprint.java`** sau đây. Đây là chương trình độc lập, có thể biên dịch bằng JDK 17. Nó in những fields cố định của Java 17 cùng những fields **phải thu thập từ máy thật**, thay vì bịa vendor/CPU/path.

```java
import java.lang.Runtime;
import java.lang.System;
import java.util.LinkedHashMap;
import java.util.Map;

public final class RuntimeFingerprint {
    public static void main(String[] args) {
        Runtime.Version version = Runtime.version();

        System.out.println("javaFeature=" + version.feature());
        System.out.println("java17=" + (version.feature() == 17));
        System.out.println("classFormat=" +
                System.getProperty("java.class.version"));

        Map<String, String> fields = new LinkedHashMap<>();
        fields.put("java.version", System.getProperty("java.version"));
        fields.put("java.runtime.version",
                System.getProperty("java.runtime.version"));
        fields.put("java.vendor", System.getProperty("java.vendor"));
        fields.put("java.home", System.getProperty("java.home"));
        fields.put("java.vm.name", System.getProperty("java.vm.name"));
        fields.put("java.vm.vendor", System.getProperty("java.vm.vendor"));
        fields.put("java.vm.version", System.getProperty("java.vm.version"));
        fields.put("os.name", System.getProperty("os.name"));
        fields.put("os.arch", System.getProperty("os.arch"));
        fields.put("os.version", System.getProperty("os.version"));
        fields.put("sun.arch.data.model",
                System.getProperty("sun.arch.data.model", "<absent>"));

        for (Map.Entry<String, String> item : fields.entrySet()) {
            System.out.println(item.getKey() + "=" + item.getValue());
        }

        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("logicalProcessors=" +
                Runtime.getRuntime().availableProcessors());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 RuntimeFingerprint.java
java RuntimeFingerprint
```

**Phần đầu stdout xác định khi chạy trên Java 17 chuẩn:**

```text
javaFeature=17
java17=true
classFormat=61.0
```

**Các dòng sau thay đổi theo môi trường**; ví dụ dưới đây là **hình thức diễn giải**, không phải output được đo thật:

```text
java.version=<runtime-release>
java.runtime.version=<runtime-build>
java.vendor=<runtime-vendor>
java.home=<runtime-home>
java.vm.name=<vm-implementation-name>
java.vm.vendor=<vm-vendor>
java.vm.version=<vm-build>
os.name=<os-name>
os.arch=<jvm-reported-architecture>
os.version=<os-version>
sun.arch.data.model=<value-or-absent>
pid=<process-id>
logicalProcessors=<count-visible-to-runtime>
```

Những chuỗi trong ngoặc nhọn là placeholder giải thích các dòng **biến thiên**; không nên dán lại làm evidence. Khi tự chạy, **đọc giá trị thật**.

**Giải thích quan trọng:**

1. `Runtime.version()` mô tả Java runtime hiện tại, không phải `javac` của một process build khác.
2. `java.vm.name`/`java.vm.vendor` cho biết VM implementation metadata, không chỉ Java specification.
3. `java.home` là path runtime của JVM hiện tại. Nó có thể là một custom `jlink` image và khác shell `JAVA_HOME`.
4. `os.arch` là giá trị runtime báo về architecture, cần đối chiếu native binary khi lựa chọn JNI/ABI.
5. `sun.arch.data.model` là **nonportable property**. Default `<absent>` cho biết không có property; code không giả sử JVM nào cũng có.
6. `pid` là PID theo process namespace được Java/OS cung cấp, không phải một số ổn định giữa lần chạy.
7. `availableProcessors()` báo số logical processors JVM nhìn thấy theo implementation và giới hạn môi trường; không chắc bằng số core vật lý trên host.
8. `classFormat=61.0` là class-file format version mà JVM Java 17 báo hỗ trợ; không phải thông tin compile version của tất cả các libraries đã load.

### 10.1. Vì sao không in `System.getenv()` toàn bộ?

Environment có thể chứa tokens, passwords, URLs nội bộ hoặc thông tin không nên đưa vào console/log. Trong demo, chỉ dùng các system properties liên quan runtime identity. Nếu cần `JAVA_HOME`, hãy ghi **đường dẫn cho phép chia sẻ** sau khi đã xác minh đó không phải secret/nhạy cảm.

### 10.2. Kiểm tra version patch/build một cách có cấu trúc

Bổ sung snippet sau vào `main` nếu muốn xem thông tin chi tiết:

```java
Runtime.Version version = Runtime.version();
System.out.println("feature=" + version.feature());
System.out.println("interim=" + version.interim());
System.out.println("update=" + version.update());
System.out.println("patch=" + version.patch());
System.out.println("build=" + version.build().orElse(-1));
```

Đoạn này là **snippet**, không phải file độc lập; `-1` là giá trị tự chọn để biểu diễn build metadata vắng mặt, **không phải build number thật**. Dùng API thay regex bóc tách chuỗi `java.version`.

## 11. Java 17 runnable demo thứ hai: feature gate có kết quả xác định

Một chương trình không nên yêu cầu đúng vendor nếu chỉ cần Java language/runtime feature. Tạo file **`FeatureGate.java`**:

```java
public final class FeatureGate {
    public static void main(String[] args) {
        int required = 17;
        int current = Runtime.version().feature();
        boolean supported = current >= required;

        System.out.println("requiredFeature=" + required);
        System.out.println("runtimeFeature=" + current);
        System.out.println("supported=" + supported);
    }
}
```

Biên dịch/chạy trên JDK 17:

```bash
javac --release 17 FeatureGate.java
java FeatureGate
```

**Stdout chính xác khi runtime đang là Java 17:**

```text
requiredFeature=17
runtimeFeature=17
supported=true
```

Trên Java 21, `supported=true` nhưng `runtimeFeature=21`. Đây không phải lỗi: kiểm tra yêu cầu **Java ít nhất 17**, không phải “chỉ Java 17 mới đúng”. Nếu app thực sự chỉ được certify trên Java 17, hãy thay policy thành `current == 17` và document/test như một **compatibility matrix** riêng — không nhầm policy release với API support.

### 11.1. Feature gate không kiểm tra JNI architecture

`supported=true` **không chứng minh** native libraries tương thích. Một Java 17 trên ARM64 và Java 17 trên x64 đều có feature=17 nhưng JNI `.so` không thể xem là interchangeable. Native binaries phải được kiểm tra OS/arch/ABI độc lập.

## 12. Java 17 runnable demo thứ ba: nhắc distinction giữa primitives và VM bitness

Tạo file **`PrimitiveVsArchitecture.java`**:

```java
public final class PrimitiveVsArchitecture {
    public static void main(String[] args) {
        System.out.println("intBits=" + Integer.SIZE);
        System.out.println("longBits=" + Long.SIZE);
        System.out.println("charBits=" + Character.SIZE);
        System.out.println("doubleBits=" + Double.SIZE);

        String arch = System.getProperty("os.arch", "unknown");
        System.out.println("architectureReported=" + arch);
    }
}
```

Biên dịch:

```bash
javac --release 17 PrimitiveVsArchitecture.java
java PrimitiveVsArchitecture
```

**Bốn dòng stdout đầu là bất biến theo Java primitive types:**

```text
intBits=32
longBits=64
charBits=16
doubleBits=64
```

Dòng `architectureReported=...` là **giá trị thực của JVM** và thay đổi theo platform. Nó không phải bằng chứng đầy đủ về bitness hoặc native library ABI.

**Giải thích:** Java `long` luôn là 64-bit, kể cả khi một JVM implementation ở process data model 32-bit; Java `char` là 16-bit UTF-16 code unit, không có nghĩa mọi Unicode character chiếm đúng 16 bits; `double` IEEE 754 64-bit. Không suy runtime pointer width từ các hằng `SIZE`.

## 13. Kiểm chứng JDK hiện tại từ Java code và OS command

Một quy trình so chéo đáng tin:

```text
A. Từ bên ngoài process:
   command -v java / Get-Command java
   java -version
   javac -version
   JAVA_HOME

B. Từ BÊN TRONG process:
   Runtime.version()
   java.vendor / java.vm.* / java.home
   os.arch / os.name
   availableProcessors()

C. Từ diagnostic attach vào đúng PID:
   jcmd PID VM.version
   jcmd PID VM.command_line
   jcmd PID VM.flags
   jcmd PID VM.system_properties

D. Từ OS/container:
   executable path / actual ELF/PE/Mach-O architecture
   cgroup CPU & memory limits
   container image digest / architecture
   process namespace mapping

Kết luận khi những nguồn có liên quan đã được đối chiếu.
```

### 13.1. Khi kết quả A và B không trùng nhau

Nếu terminal in `java -version` Java 21 nhưng `RuntimeFingerprint` trong service cho Java 17:

- Chưa thể coi service dùng Java 21; terminal có thể đang ưu tiên một executable khác.
- Xem `java.home` từ service, process command-line path và binary trong container.
- Kiểm tra Windows service/systemd unit, startup shell và environment lúc service khởi động.
- Tìm launcher wrapper/shim hoặc service manager option.
- Nếu process nằm trong container, chạy kiểm tra **trong chính container** thay vì host shell.

**Không tự restart production để “sửa” kết quả phiên bản** trước khi hiểu dependency/compatibility và deployment ownership.

### 13.2. Khi `java -version` và `javac -version` khác nhau

Ví dụ compiler báo 21, launcher báo 17:

1. Ghi đường dẫn tuyệt đối của cả hai.
2. Kiểm tra IDE/Maven/Gradle Java Toolchains.
3. Dùng `javac --release 17` khi build cho runtime 17.
4. Test artifact bằng đúng Java 17 runtime.
5. Nếu cần compiler APIs/toolchain khác, pin JDK build trong CI.
6. Dọn PATH/JAVA_HOME/configuration theo một nguồn rõ ràng, tránh sửa mù.

Không chỉ đổi tên `JAVA_HOME` rồi nghĩ mọi Gradle daemon/service đang chạy sẽ tự đổi JDK.

## 14. JDK đã cài trên máy không đồng nghĩa JDK đang chạy trong IDE/build tool

IDE và build systems có nhiều tầng:

- **IDE runtime JDK:** Java dùng để chạy IDE.
- **Project SDK:** Java APIs/project language level mà editor gán.
- **Gradle/Maven daemon JVM:** Java dùng chạy build process/plugin code.
- **Java compiler toolchain:** JDK thực hiện compilation.
- **Test JVM:** Process chạy unit/integration tests.
- **Production runtime JVM:** JVM cuối cùng chạy service.

Ví dụ compile class Java 17 bằng JDK 21 nhờ `--release 17` rồi test chỉ trên JDK 21 **chưa chứng minh** ứng dụng chạy tốt trên JDK 17: runtime còn có configuration/module/illegal access/native dependencies khác. Test ở target Java 17.

### 14.1. Class file format và `UnsupportedClassVersionError`

Nếu class được biên dịch ở major version cao hơn runtime hỗ trợ, JVM có thể ném:

```text
java.lang.UnsupportedClassVersionError: ...
```

Thông điệp đầy đủ phụ thuộc class/JVM. Về cơ bản:

| Java feature | Class major version thường gặp |
| --- | ---: |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

Đây là mapping class format; không phải bảng version VM vendor. Dùng:

```bash
javap -verbose MyClass
```

rồi xem `major version`. `javap` phải chỉ đúng class file/artifact đã deploy, không phải class file cũ của project trong IDE. Nếu có multi-release JAR, actual class selected còn phụ thuộc runtime version và JAR layout.

### 14.2. Dùng `--release` thay vì chỉ `-source/-target`

`javac --release 17` kiểm soát cú pháp, class target và public platform API set tương ứng Java 17. Trong nhiều trường hợp nó an toàn hơn `-source 17 -target 17` khi compiler bản mới có APIs mới hơn và bạn không muốn vô tình compile call tới method chỉ tồn tại trên JDK của build machine.

**Ngoại lệ:** `--release` không tự đảm bảo tương thích **JNI library**, dynamic linkage dependencies, native crypto providers hoặc vendor-specific APIs. Chúng cần test trong target runtime.

## 15. Container và tài nguyên: “máy 64 cores” không có nghĩa JVM dùng 64

Bài nằm trong nhóm **Cấu hình tài nguyên**, nên runtime identity phải liên hệ tới **effective resources**. HotSpot Java 17 thường nhận diện Linux containers qua cgroups và áp dụng container awareness theo khả năng của bản JDK/platform.

Dù vậy:

- Host có thể có 64 CPUs nhưng container được quota tương đương 2 CPUs.
- `Runtime.getRuntime().availableProcessors()` thường phản ánh số logical processors JVM thấy, **không phải** số physical cores của host.
- `-XX:ActiveProcessorCount` có thể override số processors mà HotSpot dùng cho ergonomics và báo qua Java APIs tùy implementation.
- `-Xmx` có thể được đặt trực tiếp, được suy từ percentages/ergonomics hoặc từ wrapper configuration; không chỉ phụ thuộc host RAM.
- Container memory limit khác “host total memory” và khác “heap maximum”.
- JNI/native memory, thread stacks, direct buffers và code cache vẫn cần RAM ngoài Java heap.
- Architecture ảnh hưởng native dependencies, không phải cách duy nhất điều chỉnh `-Xmx`.

### 15.1. Xem effective CPUs ngay trong Java process

`RuntimeFingerprint` ở mục 10 có:

```java
Runtime.getRuntime().availableProcessors()
```

Dòng `logicalProcessors=<n>` phản ánh giá trị runtime báo **ở lần chạy ấy**. Nếu JVM có HotSpot option `-XX:ActiveProcessorCount=2`, nó có thể làm thay đổi CPU count dùng cho ergonomics. Nhưng đây vẫn không phải lời chứng nhận “container có đúng hai physical cores”.

### 15.2. Xem heap JVM như thế nào?

Snippet dùng trong Java 17:

```java
Runtime rt = Runtime.getRuntime();
long maxHeap = rt.maxMemory();
long committedHeap = rt.totalMemory();
long freeInCommitted = rt.freeMemory();
```

Đây là **snippet**, không phải file độc lập. `maxMemory()` là mức JVM sẽ cố dành cho heap tối đa, không phải memory limit của container; `totalMemory()`/`freeMemory()` phản ánh heap memory theo API chứ không phải tổng RSS/process memory.

Đừng tính “RAM còn trống trong container = maxMemory - totalMemory” hoặc “RSS bằng -Xmx”; cần tính cả native allocations, metaspace, JIT code cache và thread stacks.

### 15.3. `-XshowSettings:system` không thay cgroup forensics

Trên HotSpot/Linux Java 17, `-XshowSettings:system` hữu ích để biết JVM đang nhận host/container constraints. Nhưng khi CPU throttling/swap/oom-killer là vấn đề, cần dữ liệu OS/cgroup, container runtime metrics và Kubernetes events. Một JVM có thể báo logical processor count phù hợp mà vẫn bị CPU throttled nhiều do tải cạnh tranh.

## 16. Kiểm tra Java process thật trong Docker/Kubernetes

Quy trình gợi ý:

1. Xác định đúng deployment/pod/container, image **digest** và architecture target.
2. Kiểm tra entrypoint và command line thực, không chỉ Dockerfile template.
3. Vào đúng container nếu được phép: `java -version`, `command -v java`, `$JAVA_HOME`.
4. Ghi allowlisted runtime identity từ chính application (ví dụ `RuntimeFingerprint` hoặc telemetry startup).
5. Nếu có tooling và permissions, `jcmd <pid> VM.version`/`VM.command_line`.
6. Đối chiếu `os.arch` và native binary architecture, nhất là multi-arch manifests.
7. Kiểm tra effective CPU/memory limits thay vì host totals.
8. Bảo đảm JDK/runtime builder stage và production stage không bị nhầm.
9. Tái kiểm tra sau deploy/rollout, không dùng log của pod cũ.
10. Nếu dùng Java agents/CDS/AppCDS/JNI, xác định compatibility theo **runtime process**, không suy từ build machine.

### 16.1. Multi-stage container build

```text
Stage 1:
  JDK 21 builder
  javac --release 17
  build app.jar

Stage 2:
  Minimal Java 17 runtime image
  java -jar app.jar
```

Đây là workflow **hợp lệ về ý tưởng** nếu app không vô tình dùng APIs/native libraries không tồn tại ở target và được test. Hai stages có thể khác CPU architecture nếu multi-platform builder/emulation được dùng; kiểm tra artifact JAR (portable bytecode) riêng với **native libraries** (architecture-specific).

### 16.2. Docker `--platform` và host architecture

Một image có thể được build cho `linux/arm64` hoặc `linux/amd64`. Khi chạy trên host khác architecture qua emulation, performance/ABI behavior và JVM port compatibility có thể thay đổi. `os.arch` từ Java process là tín hiệu hữu ích, nhưng phải ghép với image platform và executable format.

Đừng lấy `docker info` host architecture làm câu trả lời thay cho application runtime nếu có emulation/multiarch.

## 17. VM options, flags và phiên bản khi chẩn đoán lỗi

### 17.1. `Unrecognized VM option`

Nếu một runtime không nhận `-XX:...`, có thể là:

- Flag chỉ có trên HotSpot nhưng bạn chạy OpenJ9.
- Flag đã đổi tên/xóa giữa phiên bản.
- Flag diagnostic phải unlock hoặc chỉ có trong debug build.
- Sai chính tả/định dạng/đơn vị.
- Build vendor đã tắt hoặc sửa option.
- Công cụ launch đang gọi nhầm binary.

Đừng chỉ kết luận “JDK 17 này bị hỏng”. Ghi `java.vm.name`, `java.vm.version` và absolute launcher path trước, rồi tra tài liệu VM đúng build.

### 17.2. `-XX:+UnlockDiagnosticVMOptions` không phải một giấy phép chung

Một số flags chỉ hoạt động khi unlock diagnostic options, một số chỉ có ở non-product builds; và có flags không hỗ trợ trong JVM nhất định. Không chép startup options từ tutorial C2/GC cho mọi VM với cùng Java feature.

### 17.3. `-XX:+PrintFlagsFinal` có “giá trị hiệu lực” nhưng phải hiểu nguồn

Ví dụ `MaxHeapSize` có thể do explicit `-Xmx`, ergonomics hoặc container sizing; `ActiveProcessorCount` có thể override CPU detected. Khi đọc flag output hãy xem implementation/build/command line, đặc biệt trong dịch vụ được script/wrapper quản lý.

Một flag báo giá trị cụ thể không chứng minh OS thật đang cấp đủ CPU/RAM liên tục; container cgroups và scheduler là lớp khác.

## 18. JNI/native libraries: kiểm tra đủ OS, arch và ABI

`System.loadLibrary("foo")` thường tìm native library theo conventions và `java.library.path`. Mỗi platform có suffix/cách load khác nhau:

- Linux: `libfoo.so`.
- macOS: `libfoo.dylib`.
- Windows: `foo.dll`.

Tên file **không chứng minh nội dung đã build đúng architecture**. Một `libfoo.so` có thể được build cho x86_64, trong khi JVM chạy trên aarch64. Những khác biệt còn gồm:

- 32-bit vs 64-bit process ABI.
- Calling conventions, C/C++ standard library, libc variant.
- Symbols exported/JNI mangling, native transitive dependencies.
- CPU instruction extensions và runtime linker path.
- Dynamic loader search policy và permissions.

Nếu gặp `UnsatisfiedLinkError`, phải phân biệt **không tìm thấy file** với **đã tìm thấy nhưng load không được do ABI/dependency/symbol**. Một phương pháp:

1. Xác minh `os.name`/`os.arch` trong chính Java process.
2. Xác minh VM 32/64-bit bằng startup banner/native binary inspection.
3. Xem `java.library.path` nếu liên quan.
4. Kiểm tra architecture của `.so/.dll/.dylib` và dependent libraries.
5. Đọc native loader error message và OS tool output.
6. Thử bằng đúng container/runtime image, không chỉ developer laptop.

**Không đặt `-Dsun.arch.data.model=64` để “biến JVM 32-bit thành 64-bit”**. Đó chỉ sửa string property nếu JVM cho phép, không đổi binary architecture/ABI.

## 19. Reproducible environment manifest: lưu gì để debug?

Để so sánh “local chạy, production lỗi”, nên ghi có kiểm soát:

```text
Application artifact ID/digest:
  app-version, checksum, dependencies digest

Build toolchain:
  compiler path, javac -version, --release target
  CI image digest, build OS/architecture

Production runtime:
  java.version, Runtime.version(), java.vendor
  java.vm.name, java.vm.vendor, java.vm.version
  java.home, os.name, os.arch, os.version

Execution identity:
  process PID/namespace, executable path
  VM.command_line (redacted), selected VM flags
  container image digest/platform

Resource constraints:
  availableProcessors, container CPU quota/cpuset
  -Xmx/-Xms, observed heap max, cgroup memory
  GC type, native-memory considerations

Native dependencies:
  artifact OS/architecture/ABI, library digests

Observations:
  exceptions, logs, timestamps, diagnostics build
```

**Redaction là bắt buộc trong production runbooks**: không copy toàn bộ `VM.system_properties`, launcher arguments hoặc environment chứa mật khẩu/tokens vào hệ thống public. Nếu thực sự cần lưu, áp dụng access controls và retention phù hợp.

### 19.1. “Environment fingerprint” nên làm bằng typed fields

Dùng structured metadata có field names rõ ràng, ví dụ:

```text
javaFeature=17
javaRuntimeVersion=<from actual VM>
javaVendor=<from actual VM>
vmName=<from actual VM>
vmVendor=<from actual VM>
vmVersion=<from actual VM>
osArchitecture=<reported value>
runtimeExecutable=<verified executable path>
imageDigest=<release digest>
```

Các placeholders chỉ để diễn giải schema, không phải các giá trị thực. Nếu dùng nó làm cache key cho JIT-specific artifacts, phải theo compatibility contract **của artifact provider**, không coi tất cả các trường trong bảng trên là điều kiện đủ hoặc cần của mọi loại cache.

## 20. Tình huống thực tế và cách điều tra

### 20.1. Case A — Local Java 21, production Java 17

Triệu chứng: local chạy, production có `UnsupportedClassVersionError`.

**Giả thuyết:** build ra class major 65 của Java 21, production runtime chỉ hỗ trợ major 61.

**Kiểm tra:** so `javac -version`/compiler toolchain, `javap -verbose` trên **artifact deploy**, `java -version` của đúng production container và `Runtime.version()` nếu process khởi động được.

**Xử lý:** compile với target `--release 17`, test artifact trên JDK 17, kiểm tra dependent JARs và plugin-generated classes.

### 20.2. Case B — Đặt `JAVA_HOME` JDK 17 nhưng server vẫn dùng JDK 11

Triệu chứng: shell mới báo JAVA_HOME đúng nhưng service vẫn cũ.

**Giả thuyết:** service daemon chạy từ trước, có executable absolute path hoặc systemd/Windows service config khác shell hiện tại.

**Kiểm tra:** PID service, actual executable path, `java.home`/`java.vm.version` từ **process**, startup script và service manager.

**Xử lý:** sửa cấu hình launcher bằng absolute runtime path và redeploy/restart có kiểm soát. Đừng lấy giá trị shell để sửa dữ liệu hoặc restart production ngoài change procedure.

### 20.3. Case C — ARM64 pod bị lỗi JNI

Triệu chứng: `UnsatisfiedLinkError` khi chạy trên ARM64.

**Giả thuyết:** image được chọn là arm64 nhưng native dependency là x86_64.

**Kiểm tra:** pod image architecture, runtime `os.arch`, native library binary headers và loader error.

**Xử lý:** cung cấp native library đúng ABI/arch hoặc chọn platform image đúng; compile Java source lại một mình không sửa được file native khác kiến trúc.

### 20.4. Case D — Host 32 CPUs nhưng JVM chỉ báo 2

Triệu chứng: GC/worker pools hoạt động theo số CPU thấp hơn mong đợi.

**Giả thuyết:** cgroup quota/cpuset hoặc `-XX:ActiveProcessorCount=2`.

**Kiểm tra:** Java `availableProcessors()` trong process, `-XshowSettings:system` trên HotSpot/Linux, `jcmd PID VM.flags` và cgroup config.

**Xử lý:** điều chỉnh CPU quota/active processor policy dựa trên workload và resource budgets; không giả định máy host cung cấp toàn bộ CPU cho mọi container.

### 20.5. Case E — GraalVM/HotSpot vs Native Image

**GraalVM JDK** có thể có `java` launcher chạy Java bytecode trên một JVM dựa trên HotSpot trong một số builds, còn một **native-image executable** là chương trình native đã được build AOT và không tương đương một JVM `java -jar` process. Đừng gộp hai artifact chỉ vì đều đến từ cùng vendor/toolchain.

Với native-image executable, `System` properties/VM diagnostics/GC/runtime capabilities có thể khác theo công cụ/bản build. Phải đọc documentation **của artifact và version cụ thể**.

### 20.6. Case F — Chạy JDK mới hơn nhưng flags cũ

Triệu chứng: VM in “Unrecognized VM option” hoặc warning về option bị deprecated.

**Kiểm tra:** vendor, VM implementation, version và output `-XX:+PrintFlagsFinal`/VM-specific docs; không dùng bảng flags của một JDK khác theo thói quen.

**Xử lý:** cập nhật flags theo target JDK/VM và benchmark collector/resource behavior. Không biến cảnh báo thành “JVM 17 chắc phải dùng G1” mà chưa xác định implementation.

## 21. Những lỗi diễn giải thường gặp

1. **“`java -version` trên host chính là runtime của mọi container.”** Sai; container có image riêng.
2. **“`JAVA_HOME` xác định chắc file `java` mà PATH gọi.”** Sai; launcher resolution/wrapper khác.
3. **“`javac -version` bằng Java version của service.”** Sai; compiler/process riêng.
4. **“Project language level trong IDE quyết định production VM.”** Sai.
5. **“`--release 17` chứng minh JNI native lib chạy trên mọi architecture.”** Sai.
6. **“Cùng Java 17 thì mọi vendor/VM đều có cùng HotSpot flags.”** Sai.
7. **“`java.vm.name` cho biết toàn bộ vendor/patch/build.”** Sai; cần thêm properties.
8. **“`java.vm.specification.vendor` luôn là JDK distributor.”** Sai.
9. **“`java.specification.version` là đầy đủ bản vá security.”** Sai.
10. **“`java.class.version` là compile version của từng class trong app.”** Sai.
11. **“`Runtime.version().feature()==17` chứng minh VM thuộc đúng patch release.”** Sai.
12. **“`Integer.SIZE` hoặc `Long.SIZE` đo JVM pointer width.”** Sai.
13. **“`os.arch` là danh sách CPU extensions/ISA features.”** Sai.
14. **“`uname -m` luôn bằng `os.arch` trong mọi container/emulation.”** Sai.
15. **“Cứ có `amd64` trong property là mọi native `.so` trên Linux chạy được.”** Sai.
16. **“JDK 17 chắc chắn có `javac` trong runtime image production.”** Sai nếu jlink/minimal image.
17. **“Không thấy `jcmd` nghĩa service không chạy JVM.”** Sai; runtime image có thể thiếu tool.
18. **“`-XX:+PrintFlagsFinal` là Java SE portable API.”** Sai; phụ thuộc VM implementation.
19. **“`-XshowSettings:system` luôn có output giống nhau trên Windows/macOS/Linux.”** Sai.
20. **“`os.name`/`os.version` giải thích đầy đủ container base distro.”** Sai; JVM nhìn kernel/userspace trong ngữ cảnh phù hợp.
21. **“`availableProcessors()` bằng số physical cores chắc chắn được cấp riêng.”** Sai.
22. **“Heap max là toàn bộ RAM limit container.”** Sai; off-heap/native memory còn dùng RAM.
23. **“Đổi `System.setProperty("os.arch", ...)` đổi native binary architecture.”** Sai.
24. **“Máy có JDK 21 nên class-file major 65 luôn chạy được trên Java 17 container.”** Sai.
25. **“Chạy success trên builder image chứng minh success trên runtime image.”** Sai.
26. **“`java.home` = môi trường `JAVA_HOME` của mọi process.”** Sai.
27. **“`java.vendor` luôn chỉ một enum chính thức của JVM vendors.”** Sai, là string.
28. **“`java.vm.version` bắt buộc giống `java.version`.”** Sai.
29. **“Java runtime version >= 17 bảo đảm không còn lỗi classpath/module reflection.”** Sai.
30. **“JDK feature/version fingerprint đủ để chứng minh CDS archive binary compatible.”** Sai; build/classpath/VM flags cũng quan trọng.
31. **“`java -version` cần khởi động mọi application main class.”** Sai; chỉ launcher.
32. **“`jcmd PID VM.version` trên PID bất kỳ trong host luôn thành công.”** Sai; attach permissions/namespaces.
33. **“`-XX:ActiveProcessorCount` bắt buộc bằng số core vật lý.”** Sai.
34. **“Có thể dump toàn bộ VM.system_properties lên public logs mà an toàn.”** Sai; có thể chứa sensitive data.
35. **“CPU architecture là lý do duy nhất khác hiệu năng giữa hai JDKs.”** Sai; VM build/GC/flags/workload/containers.
36. **“HotSpot 64-Bit Server VM” banner có nghĩa heap luôn 64 GiB hoặc lớn hơn.”** Sai; heap riêng và phụ thuộc flags/limits.
37. **“`java.vendor` cùng giá trị nghĩa hai JDK binaries có cùng checksum.”** Sai.
38. **“`ProcessHandle.current().pid()` luôn bằng host PID khi chạy container.”** Không bảo đảm, PID namespace.
39. **“Một JDK hỗ trợ Linux x64 mặc định hỗ trợ Linux ARM64.”** Sai; phải chọn correct port/build.
40. **“Java primitive widths thay đổi theo CPU architecture.”** Sai; Java language semantics xác định width.

## 22. Bài tập thực hành

### Bài 1 — Khám phá môi trường thực

Chạy `RuntimeFingerprint`. Ghi lại:

- Java feature/update/build theo `Runtime.Version`.
- Java vendor, VM name/vendor/version.
- `java.home` và absolute launcher path.
- `os.arch`, `os.name` và (nếu có) `sun.arch.data.model`.
- `availableProcessors` và container CPU quota (nếu liên quan).

**Câu hỏi:** Có cặp giá trị nào khác trực giác (ví dụ Java 17 từ runtime image nhưng `javac` của IDE là 21)? Giải thích bằng toolchain/runtime separation.

### Bài 2 — So builder và runtime images

Biên dịch `FeatureGate` với JDK 21 dùng `--release 17`, chạy trên JDK 17. Sau đó thử build không dùng `--release` rồi xác minh class-file major với `javap -verbose` trước khi đưa lên runtime.

**Yêu cầu:** Không tùy tiện gọi `java` trên host; dùng absolute paths hoặc container images đã pin.

### Bài 3 — Kiểm tra resource awareness

Trong một HotSpot Java 17 Linux container test, đo `availableProcessors()` với cgroup CPU quota khác nhau, và một lần cấu hình `-XX:ActiveProcessorCount` nếu runtime hỗ trợ.

**Yêu cầu:** Không suy số physical cores từ API này; ghi kernel/cgroup/runtime version.

### Bài 4 — Chọn đúng JNI artifact

Giả sử có `libcodec.so` build cho Linux x86_64 và production image chạy Linux aarch64. Trình bày các bước xác minh `os.arch`, binary headers, dependencies và cách xây thư viện đúng architecture.

**Đáp án định hướng:** Java bytecode có thể portable, native JNI binary thường không; cần build/dùng một phiên bản phù hợp OS/ABI.

### Bài 5 — Tạo incident report có dữ liệu tối thiểu

Viết báo cáo gồm Java runtime feature/build, VM vendor/name/version, executable path, container image digest/arch, selected VM flags, symptoms và exception. Không gửi full `System.getProperties()` hoặc tokens.

**Tiêu chí đạt:** Một kỹ sư khác có thể xác định **đúng runtime process và architecture** để lặp lại issue.

## 23. Câu hỏi tự kiểm tra (có đáp án)

**Câu 1.** Lệnh nào cho biết phiên bản JVM đang chạy trong đúng process PID trên HotSpot?

**Đáp án:** `jcmd <pid> VM.version` khi attach được; đối chiếu với `VM.command_line` và Java-side properties.

**Câu 2.** Nếu `javac -version` là 21 nhưng runtime Java feature là 17, đây có nhất thiết là lỗi?

**Đáp án:** Không. Có thể cố ý cross-compile bằng `--release 17`. Vấn đề là artifact có đúng Java 17 API/class-file/native compatibility và được test trên runtime target hay không.

**Câu 3.** `java.vendor` và `java.vm.name` có trả lời cùng câu hỏi không?

**Đáp án:** Không. Vendor nói về distribution, VM name nói về implementation.

**Câu 4.** `java.vm.specification.vendor` có nhất thiết là Oracle/Temurin/Corretto đang phân phối binary không?

**Đáp án:** Không. Specification vendor khác implementation/distribution vendor.

**Câu 5.** Vì sao `-Dsun.arch.data.model=64` không biến một JVM 32-bit thành JVM 64-bit?

**Đáp án:** Vì nó là property string, không thay đổi executable ABI/pointer width.

**Câu 6.** `Runtime.version().feature()` có thể dùng để check một API yêu cầu Java 17 không?

**Đáp án:** Có, nếu policy là tối thiểu feature 17, nhưng không thay dependency/native compatibility tests.

**Câu 7.** Java 17 class major version là bao nhiêu?

**Đáp án:** **61**; property `java.class.version` thường trả `61.0`.

**Câu 8.** Có thể coi `os.arch=amd64` là bằng chứng mọi CPU extensions mà JIT có thể dùng đều hiện diện không?

**Đáp án:** Không. Architecture family không nêu mọi ISA extensions/hardware features.

**Câu 9.** `Runtime.getRuntime().availableProcessors()` thể hiện host physical core count hay JVM-visible logical processor count?

**Đáp án:** JVM-visible logical processor count; có thể bị ảnh hưởng bởi container quotas/cpuset và VM flags.

**Câu 10.** `java.home` bằng `JAVA_HOME` không?

**Đáp án:** Không bắt buộc. `java.home` là runtime location của process, `JAVA_HOME` là environment variable có thể trỏ JDK khác.

**Câu 11.** Tại sao `jcmd` trong custom JRE image có thể không tìm thấy?

**Đáp án:** Runtime image có thể chỉ chứa modules/executables cần chạy app, không có diagnostic tools.

**Câu 12.** Làm gì trước khi thử `-XX:+PrintFlagsFinal` trên VM khác HotSpot?

**Đáp án:** Xác định `java.vm.name`/vendor/version và tham khảo VM-specific docs để biết option hỗ trợ.

**Câu 13.** Đo total RAM JVM bằng `maxMemory()` đúng không?

**Đáp án:** Không. `maxMemory` liên quan Java heap limit; native stacks, metaspace, code cache và direct buffers khác.

**Câu 14.** Vì sao host `uname -m` và Java `os.arch` có thể khác?

**Đáp án:** Container/emulation/VM process bitness/platform reporting khác; cần kiểm tra executable và native ABI của process.

**Câu 15.** Có an toàn để chia sẻ full `jcmd PID VM.system_properties` trên issue công khai không?

**Đáp án:** Không; nó có thể chứa đường dẫn/thông tin cấu hình hoặc secret, cần lọc/redact.

**Câu 16.** Một ứng dụng Java 17 chạy tốt trên local x86_64, lên ARM64 bị `UnsatisfiedLinkError`. Có đủ chứng cứ JVM thiếu Java feature không?

**Đáp án:** Không; nghi native library architecture/ABI mismatch và kiểm tra đường load/dependency.

**Câu 17.** Hai services cùng Java 17 nhưng Java.vm.name khác nhau. Có thể copy HotSpot-only tuning flags giữa chúng không?

**Đáp án:** Không mặc định. Phải dùng tài liệu/validation đúng VM implementation.

**Câu 18.** Nếu container image tag không đổi nhưng digest thay đổi, runtime identity có thể đã đổi không?

**Đáp án:** Có. Pin digest và kiểm chứng runtime mới.

**Câu 19.** `Runtime.Version.update()` và `feature()` khác nhau thế nào?

**Đáp án:** Feature là Java release family, update là thành phần update release trong scheme; không coi update là major feature.

**Câu 20.** Đâu là bộ thông tin tối thiểu có ích trước khi báo lỗi GC/container?

**Đáp án:** JDK feature/update/build, vendor, VM name/version, OS/arch, process PID/launch command, effective VM flags, CPU/memory limits, workload và logs được redact.

## 24. Checklist nhận diện runtime trước khi sửa cấu hình tài nguyên

- [ ] Xác nhận **đúng service/pod/container/PID**, không nhầm shell với process đích.
- [ ] Ghi **`Runtime.version()`** gồm feature/update/build khi có.
- [ ] Ghi `java.version`, `java.vendor`, `java.vm.name`, `java.vm.vendor`, `java.vm.version`.
- [ ] Ghi `java.home` và đường dẫn executable thực của service.
- [ ] So `java -version`/`javac -version` theo đường dẫn tuyệt đối.
- [ ] Phân biệt build JDK, test JDK, production runtime.
- [ ] Kiểm tra Java class major version (Java 17 → 61) của artifact nếu cần.
- [ ] Ghi `os.name`/`os.arch` và xác minh process/native binary ABI khi có JNI.
- [ ] Đọc `-XshowSettings:system` trên HotSpot/Linux nếu cần container awareness.
- [ ] Ghi `availableProcessors` và effective CPU quota/cpuset.
- [ ] Xác minh heap flags `-Xms/-Xmx`, GC, stack size và native memory constraints.
- [ ] Với HotSpot: thử `jcmd PID VM.version`/`VM.command_line`/`VM.flags` khi được phép.
- [ ] Xử lý chênh lệch giữa host/shell/app process rõ ràng thay vì giả định đồng nhất.
- [ ] Trong multi-arch images, pin image digest/platform và JNI artifacts tương ứng.
- [ ] Chỉ dùng JVM flags được **VM implementation/build thật** hỗ trợ.
- [ ] Redact secrets trước khi lưu diagnostic outputs.
- [ ] Kiểm thử trên runtime/deployment target sau khi đổi JDK hay flags.

## 25. Tổng kết bản đồ quyết định

```text
Bạn cần tối ưu hoặc debug một Java service?
                    │
                    ▼
          XÁC ĐỊNH ĐÚNG PROCESS
          PID + container + executable
                    │
                    ▼
           XÁC ĐỊNH JAVA VERSION
       Runtime.version(), java.version
         feature / update / patch / build
                    │
                    ▼
          XÁC ĐỊNH VM IMPLEMENTATION
       java.vm.name / vendor / version
                    │
                    ▼
          XÁC ĐỊNH ARCHITECTURE
        os.arch + process binary + ABI
                    │
                    ▼
         XÁC ĐỊNH RESOURCE ENVELOPE
       CPUs/quota, RAM/cgroup, -Xmx, GC
                    │
                    ▼
          KIỂM TRA BUILD VS RUNTIME
          javac / --release / class major
                    │
                    ▼
        THU THẬP EFFECTIVE VM FLAGS
           jcmd (nếu có và attach được)
                    │
                    ▼
       ÁP DỤNG TUNING / FIX PHÙ HỢP
       đúng JDK + đúng VM + đúng target
                    │
                    ▼
         VERIFY trên runtime production-like
```

**Ghi nhớ:** Mỗi lần nói “ứng dụng đang dùng Java 17”, hãy xác nhận **Java 17 của tiến trình nào, bản vá/build nào, vendor nào, JVM implementation nào, trên architecture nào và với giới hạn tài nguyên nào**. `java -version` trong shell, `JAVA_HOME`, `javac -version`, `os.arch` và `jcmd PID VM.version` **cung cấp những góc nhìn khác nhau**, không thay nhau được. Tốt nhất là đối chiếu **runtime properties của chính process**, **toolchain paths**, **native binary/OS/container facts** và **effective VM flags** trước khi đưa ra quyết định GC, heap, JIT hay JNI.

### Tài liệu chính thức

- [Oracle Java SE 17 — System Properties](https://docs.oracle.com/en/java/javase/17/docs/api/system-properties.html): `java.vendor`, `java.version`, `java.vm.name` và properties liên quan.
- [Java SE 17 — `java.lang.System` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): định nghĩa `getProperty`/`getProperties`, danh sách chuẩn và caveats.
- [Java SE 17 — `java.lang.Runtime.Version`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html): các thành phần feature/interim/update/patch/build.
- [Oracle JDK 17 — Version String Format](https://docs.oracle.com/en/java/javase/17/install/version-string-format.html): giải thích release numbering.
- [Oracle JDK 17 — `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-version`, `--version`, `-XshowSettings`, `-XX:+PrintFlagsFinal` và HotSpot options.
- [Oracle JDK 17 — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release 17` và compilation compatibility.
- [Oracle JDK 17 — `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): `-verbose` để đọc class-file major.
- [Oracle JDK 17 — `jcmd` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.version`, `VM.command_line`, `VM.flags`, `VM.system_properties`.
- [Java SE 17 — `ProcessHandle` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html): PID và metadata của tiến trình.
- [JVMS SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): bytecode/class major version khác runtime VM implementation build.

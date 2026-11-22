# Phân biệt AOT cache của JVM với biên dịch thành chương trình native

## 1. Vì sao có hai cách đều được gọi là “AOT”?

Trong Java, **Ahead-of-Time (AOT)** có nghĩa rộng là *chuẩn bị trước một số thông tin hoặc mã thực thi* thay vì đợi tới lúc ứng dụng cần chúng. Nhưng **AOT không phải tên của một định dạng file duy nhất**, và cụm “đã AOT” chưa đủ để biết ứng dụng **có cần JVM để chạy hay không**.

Hai cơ chế cần phân biệt trong bài này:

1. **JVM AOT cache (HotSpot / Project Leyden):** chạy ứng dụng Java trên **JVM bình thường**, nhưng dùng dữ liệu đã được ghi trước từ các lần chuẩn bị/training. Trên **JDK 25**, AOT cache có thể lưu class-loading/linking data, những đối tượng phù hợp và **method profiles** để cải thiện startup/warmup. Ứng dụng vẫn chạy qua `java`, sử dụng JVM runtime, garbage collector và có thể dùng **JIT compiler**.
2. **Native executable (ví dụ GraalVM Native Image):** dùng build tool để phân tích bytecode, xác định các thành phần cần dùng và **biên dịch chương trình thành tệp thực thi native** cho một OS/CPU target. Khi triển khai, thường chạy tệp `app-native` / `app-native.exe` **trực tiếp**, không khởi động HotSpot bằng lệnh `java -jar ...`. Executable vẫn chứa **những phần Java runtime cần thiết**, chứ không phải Java semantics biến mất.

**Một câu để nhớ:** AOT cache = **chuẩn bị cho JVM chạy ứng dụng hiệu quả hơn**; Native Image = **biên dịch và đóng gói ứng dụng thành executable native**. Cả hai hướng có thể cải thiện khởi động, nhưng khác nhau về **artifact, runtime, dynamic capabilities, build cost, portability và cơ chế tối ưu về sau**.

### Cảnh báo quan trọng về tên gọi

- File `.aot` của HotSpot JDK 25 **không phải** chương trình native chạy trực tiếp.
- File `.jsa` của CDS/AppCDS cũng **không phải** native executable.
- File `.class` và `.jar` thông thường chứa **bytecode Java**, không phải binary native.
- Tool `native-image` trong GraalVM **không phải** tùy chọn đồng nghĩa với `-XX:AOTCacheOutput` của HotSpot.
- Từ “AOT” của **Spring AOT processing** thường chỉ code generation/analysis phục vụ các đường triển khai, **không tự động** tạo native executable nếu chưa chạy Native Image build.

## 2. Ba con đường từ Java source tới chương trình chạy

### 2.1. Java/JVM thông thường

~~~text
StartupCompare.java
      |
      | javac
      v
StartupCompare.class   ->  startup-compare.jar
      |
      | java -jar startup-compare.jar
      v
HotSpot JVM
  - load/link/init classes theo Java rules
  - interpreter thực thi bytecode
  - profiling/JIT compile hot code khi phù hợp
  - GC và Java runtime hoạt động
      |
      v
Application result
~~~

Ở chế độ này, code có thể đi từ interpreter sang C1/C2 (hoặc compiler khác tùy cấu hình), rồi tới native machine code **tạo trong runtime**. JIT compilation không đổi định dạng `.jar` ban đầu.

### 2.2. JVM có AOT cache

~~~text
Build Java classes/JAR
      |
      v
JDK 25 training run (Java application thật)
      |
      | record classes, metadata, method profiles phù hợp
      v
AOT configuration/training information
      |
      | assembly
      v
startup-compare.aot   (AOT cache artifact)
      |
      | java -XX:AOTCache=startup-compare.aot -jar ...
      v
HotSpot JVM vẫn chạy:
  - đọc/map AOT cache tương thích
  - tái sử dụng dữ liệu classes/linking/profiles phù hợp
  - interpreter/JIT vẫn có vai trò trong runtime
  - GC và Java runtime vẫn có vai trò
      |
      v
Application result
~~~

**Cache không thay thế JVM**. Nó giúp VM có “bài chuẩn bị” từ trước; phần ứng dụng, JVM và JDK vẫn phải phù hợp với cache.

### 2.3. Native Image

~~~text
Build Java classes/JAR
      |
      | native-image tool
      v
Reachability analysis (closed-world model)
  - xác định reachable classes/methods/fields
  - xử lý metadata cho reflection/resources/JNI khi cần
  - các class initialization decisions
      |
      v
Ahead-of-time compilation + native linking
      |
      v
startup-compare-native[.exe]
  - application native code
  - những phần Java runtime cần thiết
  - GC/threading/safepoint support tương ứng
      |
      | chạy executable trực tiếp
      v
Application result
~~~

**Native Image không có nghĩa “không còn runtime”.** Native executable vẫn có logic/runtime hỗ trợ memory management, class metadata và threading theo cơ chế Native Image; nó chỉ **không cần khởi động HotSpot JVM truyền thống** để thực hiện chương trình theo cách `java -jar`.

## 3. Bảng so sánh trọng tâm

| Đặc điểm | HotSpot JVM + AOT cache | GraalVM Native Image |
| --- | --- | --- |
| Artifact tối ưu | `.aot` (và có thể `.aotconfig` trong workflow tách bước) | Native executable như `app-native`, `app-native.exe` |
| Cách chạy | `java -XX:AOTCache=... -jar app.jar` | `./app-native` hoặc `.\app-native.exe` |
| Có chạy HotSpot JVM? | **Có** | **Không**, dùng runtime nhúng/được link cho Native Image |
| Có cần JDK/JRE tương thích lúc runtime? | **Có**, JVM và classpath/module state phù hợp | Thường không cần JVM/JDK đầy đủ ở máy triển khai; vẫn có OS/native library requirements |
| Input trước build | Java bytecode và ứng dụng chạy thử | Java bytecode, dependency graph, reachability metadata |
| Cách AOT làm việc | Training và lưu artifacts giúp JVM startup/warmup | Whole-program reachability + ahead-of-time code generation/linking |
| Java JIT khi chạy? | **Vẫn có thể dùng** JIT; JDK 25 cache profiles giúp JIT tối ưu sớm hơn | Không dùng HotSpot tiered JIT thông thường cho ứng dụng đã biên dịch |
| Dynamic class loading | JVM semantics thông thường, chịu các điều kiện dùng cache | Theo **closed-world assumption**; code cần biết ở build time |
| Reflection/proxy/resources | Hành vi JVM linh hoạt như ứng dụng thường, với các ràng buộc cache | Có thể cần reachability metadata/configuration |
| Class initialization | Phần semantics runtime được bảo toàn theo JVM rules | Có phân biệt **build-time** và **run-time initialization** |
| Compatibility | App/JDK release/OS/CPU phải tương thích cache | Native binary phụ thuộc OS/CPU và runtime native libraries cần thiết |
| Build overhead | Training + assembly; có thể dùng một flag thuận tiện JDK 25 | Static analysis và native linking thường tốn CPU/RAM/build time |
| Lợi ích chính | Giảm startup/warmup của Java VM ít thay đổi mô hình ứng dụng | Rút ngắn startup, giảm footprint runtime và bỏ yêu cầu JVM truyền thống |
| Đổi dependency sau build | Cache thường phải tái tạo, app JAR vẫn là input runtime | Phải **rebuild native executable** |
| Tooling | `java`, `jcmd`, JFR, HotSpot `-Xlog` theo phiên bản | Native Image runtime/tooling và platform profiler phù hợp |
| Khả năng điều chỉnh sau deploy | Các JVM flags/GC/JIT tiếp tục phát huy, tùy compatibility | Options/native runtime có tập hỗ trợ và hành vi khác; không áp máy móc mọi HotSpot flags |

**Không khẳng định Native Image luôn nhanh hơn mọi JVM+AOT workload.** Native có thể vượt trội ở cold start; Java HotSpot JIT vẫn có thế mạnh tối ưu runtime cho một số workloads chạy lâu, đặc biệt khi nhận nhiều runtime profiles mới. Kết luận phải dựa trên metric thực tế.

## 4. AOT cache của JDK 25 lưu cái gì?

Theo Oracle JDK 25 `java` launcher manual và các JEP thuộc Project Leyden, AOT cache được phát triển để đưa một số công việc từ **production startup** sang **training/assembly**.

### Nền tảng từ CDS

**Class Data Sharing (CDS)** từng lưu class metadata đã xử lý trước trong archive, thường có đuôi `.jsa`. Các archived classes có thể được map vào JVM processes sau đó, giảm class-loading work và đôi khi giảm footprint nhờ memory-mapped shared pages.

AOT cache từ JDK 24 mở rộng hướng này. Oracle JDK 25 nêu AOT cache là container cho artifacts có khả năng giúp khởi động/warmup: lớp đã xử lý, class loading/linking data và những objects phù hợp. **Không nên coi AOT cache là heap snapshot đầy đủ** của toàn bộ app, cũng không phải một JAR mới.

### JEP 483: Ahead-of-Time Class Loading & Linking

**JEP 483 (JDK 24)** đưa workflow **training → assembly → production** để ghi nhận/lưu một phần trạng thái class loading/linking thích hợp. Production JVM dùng những dữ liệu đã chuẩn bị nếu compatibility checks cho phép.

**Không hiểu** đây là thực thi trước toàn bộ `main`, lưu tất cả sockets/database connections hoặc khôi phục tiến trình như sau một checkpoint toàn bộ OS process.

### JEP 515: Ahead-of-Time Method Profiling

**JEP 515 (JDK 25)** đưa method profiles đã thu trong training vào AOT cache. Khi JVM start, những profiles này giúp JIT bắt đầu tối ưu với thông tin tốt hơn **thay vì phải chờ thu tất cả profile mới từ cold runtime**.

**Điểm phải phân biệt:** Lưu **JIT profiles** vào `.aot` không tương đương lưu **native executable**. JIT vẫn có thể sinh machine code **trong production runtime**. Điều này khác với Native Image vốn AOT-compile reachable application code thành binary khi build.

Một số trang tài liệu lịch sử có thể còn mô tả “compiled methods và execution profiles sẽ được lưu trong cache ở tương lai”. Cần đối chiếu JDK release và **JEP 515**: JDK 25 đã có **AOT Method Profiling**, nhưng **không vì thế mà cache là một Native Image executable**.

### JEP 514: AOT Command-Line Ergonomics

JDK 25 đơn giản hóa thao tác tạo cache qua `-XX:AOTCacheOutput=...`, giúp một lệnh thực hiện **training** rồi khởi chạy assembly phase thích hợp để sinh cache. Tài liệu vẫn mô tả workflow tách **record/create/on** cho automation chi tiết.

## 5. Các artifacts của JVM AOT cache

| Artifact | Vai trò | Tự chạy được không? |
| --- | --- | --- |
| `.java` | Source Java | Không phải native executable |
| `.class` | JVM bytecode | Dùng Java launcher/JVM phù hợp |
| `.jar` | Đóng gói classes/resources | Thông thường dùng `java -jar` |
| `.classlist` | Class list phục vụ CDS workflow truyền thống | Không |
| `.jsa` | CDS/AppCDS archive | **Không**, dùng với JVM |
| `.aotconfig` | Dữ liệu configuration/training của JDK 25 AOT workflow | **Không** |
| `.aot` | Cache AOT artifacts tiêu chuẩn trên JDK 25 | **Không**, JVM đọc bằng `-XX:AOTCache` |
| `app-native` / `app-native.exe` | Native Image executable theo target OS/CPU | **Có**, chạy trực tiếp khi native runtime dependencies được thỏa |

Không đổi phần mở rộng từ `.aot` thành `.exe` để biến nó thành program. Cũng không nói `.aot` là file chứa những instruction CPU hoàn chỉnh để bỏ HotSpot.

## 6. Chương trình Java 17+ dùng để so sánh hai hướng

Tạo file **`StartupCompare.java`**:

~~~java
public final class StartupCompare {
    private StartupCompare() {
    }

    static int sumTo(int n) {
        int sum = 0;
        for (int i = 1; i <= n; i++) {
            sum += i;
        }
        return sum;
    }

    static String message(String name) {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        System.out.println("message=" + message("AOT"));
        System.out.println("sum=" + sumTo(10));
    }
}
~~~

Chương trình **không cần library ngoài**, không có I/O file/network, không phụ thuộc thời gian, không dùng non-deterministic random hoặc thread scheduling.

Biên dịch bằng **Java 17+**:

~~~bash
javac -g StartupCompare.java
java StartupCompare
~~~

**Stdout xác định khi chạy thành công, không bật VM diagnostic logs:**

~~~text
message=Hello, AOT
sum=55
~~~

Bởi `sumTo(10)` cộng `1+2+...+10 = 55`. Giá trị này giữ nguyên khi chạy bằng HotSpot không cache, HotSpot có cache hoặc Native Image đã biên dịch thành công.

### Đóng JAR để thí nghiệm AOT cache

Tạo thư mục clean cho artifact, nếu bạn muốn không dùng class directory trong các command tiếp theo.

**Linux/macOS hoặc PowerShell (các lệnh Java/JAR này dùng được ở cả hai):**

~~~bash
javac -d classes StartupCompare.java
jar --create --file startup-compare.jar --main-class StartupCompare -C classes .
java -jar startup-compare.jar
~~~

**Trước đó cần tạo thư mục `classes`**:

- Linux/macOS: chạy `mkdir -p classes`.
- Windows PowerShell: chạy `New-Item -ItemType Directory -Force classes | Out-Null`.

Đầu ra chương trình vẫn hai dòng trên. Trong JAR có `StartupCompare.class` và manifest ghi `Main-Class`. **Giữ nguyên bytes của JAR** trong quá trình tạo/dùng cache để tránh mismatch.

**Lưu ý:** lệnh `javac -d classes` yêu cầu thư mục `classes` tồn tại; bước tạo thư mục là một phần bắt buộc của lab, không phải giả định tool tự tạo root directory.

## 7. Bài lab A — tạo AOT cache trên HotSpot JDK 25

Những lệnh ở phần này yêu cầu **HotSpot JDK 25** hoặc JVM/JDK khác tài liệu hóa đầy đủ cùng options. **Chúng không chạy trên JDK 17 chỉ vì mã nguồn Java tương thích Java 17.**

### Bước A1. Xác nhận JDK đang chạy

~~~bash
java -version
java -Xlog:help
~~~

Kiểm tra output cho thấy **JDK 25 HotSpot**. Nếu trong một hệ thống có nhiều `java`/`javac` trên PATH, phải làm rõ JDK dùng để tạo `.aot` và JVM sẽ dùng cache trong runtime.

**Không cố bật flags AOT trên Java 17 rồi kết luận tính năng lỗi** khi JVM báo `Unrecognized VM option`. JDK 17 có CDS/AppCDS nhưng chưa có workflow AOT Cache JDK 25 này.

### Bước A2. Chạy baseline không có AOT cache

~~~bash
java -XX:AOTMode=off -jar startup-compare.jar
~~~

**Stdout ứng dụng:**

~~~text
message=Hello, AOT
sum=55
~~~

`-XX:AOTMode=off` vô hiệu hóa sử dụng AOT cache theo semantics Oracle JDK 25. Để so sánh performance cần đo riêng nhiều process starts; ở bước này chỉ thiết lập baseline chức năng.

### Bước A3. Training + assembly qua một lệnh

~~~bash
java -XX:AOTCacheOutput=startup-compare.aot -jar startup-compare.jar
~~~

Ở JDK 25, chế độ mặc định `AOTMode=auto` kết hợp `AOTCacheOutput` làm một **training execution** và một **assembly JVM process** phù hợp để ghi artifacts. **Đừng diễn giải command này là “đã compile JAR thành native exe”.**

Đầu ra ứng dụng từ training run vẫn là:

~~~text
message=Hello, AOT
sum=55
~~~

Các diagnostic/build messages của JVM (nếu có) có thể xuất hiện ngoài hai dòng. Sau lệnh, kiểm tra artifact:

**Linux/macOS:**

~~~bash
ls -lh startup-compare.aot
~~~

**Windows PowerShell:**

~~~powershell
Get-Item .\startup-compare.aot
~~~

Nếu file không được tạo, xem exit code/log và tính tương thích của VM flags; không đi thẳng sang kết luận đã có cache hợp lệ.

### Bước A4. Chạy lại ứng dụng với cache

~~~bash
java -XX:AOTCache=startup-compare.aot -jar startup-compare.jar
~~~

**Stdout ứng dụng vẫn là:**

~~~text
message=Hello, AOT
sum=55
~~~

Đây là **production run của JVM**, không phải chạy file `startup-compare.aot` trực tiếp.

### Bước A5. Xác nhận JVM có sử dụng AOT cache

~~~bash
java -XX:AOTCache=startup-compare.aot -Xlog:aot=info -jar startup-compare.jar
~~~

Lúc này VM có thể in **AOT diagnostic logs** liên quan cache. Hãy kiểm tra những thông tin về **cache load / mapping / validation / rejection** mà JDK thực tế xuất ra; log format, exact text và timing thay đổi theo release/build. Để xem tag/level hợp lệ, dùng `java -Xlog:help`.

**Quan trọng:** một file `.aot` tồn tại trên disk **không chứng minh** runtime đã map/đọc thành công nó. Trong chế độ automatic, JVM có thể fallback hoặc không dùng vì cache không tương thích.

### Bước A6. Kiểm tra nghiêm ngặt trong môi trường test

~~~bash
java -XX:AOTMode=on -XX:AOTCache=startup-compare.aot -Xlog:aot=info -jar startup-compare.jar
~~~

`AOTMode=on` là chế độ yêu cầu dùng AOT cache theo options; nó hữu ích khi chẩn đoán lỗi compatibility. **Không dùng chế độ strict một cách mù quáng trong production**: nếu cache thiếu/không hợp lệ, JVM có thể exit thay vì fallback.

Nếu JVM từ chối cache, **không báo thí nghiệm thành công chỉ vì app vẫn chạy ở mode khác**. Đọc AOT logs, xác nhận đúng path/JDK/JAR/options.

## 8. Workflow ba giai đoạn tách riêng trên JDK 25

Tài liệu Oracle còn định nghĩa các modes **`record` → `create` → `on`** để kiểm soát rõ từng bước.

### Training / record

~~~bash
java -XX:AOTMode=record -XX:AOTConfiguration=startup-compare.aotconfig -jar startup-compare.jar
~~~

Process chạy chương trình để ghi thống kê/dữ liệu configuration thích hợp. File `startup-compare.aotconfig` **không phải** program và **chưa phải** final `.aot`.

### Assembly / create

~~~bash
java -XX:AOTMode=create -XX:AOTConfiguration=startup-compare.aotconfig -XX:AOTCache=startup-compare.aot -jar startup-compare.jar
~~~

Theo Oracle JDK 25, **create mode thực hiện assembly, không chạy ứng dụng `main`**. Nếu thao tác thành công, tạo `startup-compare.aot`.

### Production / on

~~~bash
java -XX:AOTMode=on -XX:AOTCache=startup-compare.aot -jar startup-compare.jar
~~~

Ứng dụng chạy trên **HotSpot JVM với cache**. Ba giai đoạn được tách phù hợp cho build pipeline, image build và deployment.

### Không trộn tùy tiện các AOT options

Oracle JDK 25 đặt constraints:

- `-XX:AOTCacheOutput=...` là lựa chọn output, không được dùng đồng thời với `-XX:AOTCache=...`.
- `-XX:AOTConfiguration=...` ghi ở `record`, đọc ở `create` theo mode.
- `-XX:AOTMode=off` bỏ qua cache; `auto` mặc định quyết định record/on/off theo options.
- `-XX:AOTMode=create` không đồng nghĩa gọi native-image; chỉ **assemble cache**.
- AOT cache cần **app/JDK/OS/CPU compatibility**.

**Nếu bước create báo lỗi, giữ nguyên dữ liệu training và đọc log**; đừng thay các flags cho tới khi “không còn lỗi” rồi khẳng định vẫn là cùng thí nghiệm.

## 9. Cache không tương thích: một giới hạn thực tế quan trọng

Theo Oracle JDK 25, AOT cache là artifact cho tổ hợp cụ thể:

1. **Ứng dụng** như biểu diễn qua `-classpath`, `-jar` hay `--module-path` và code/resources.
2. **Một JDK release/build phù hợp**.
3. **OS và CPU architecture**.

Nếu thay đổi thành phần này, phải **tạo lại AOT cache**. Một số JVM options, JVMTI agents hoặc điều kiện runtime khác có thể khiến cache không được dùng. Đừng giả định archive dùng được trên mọi node chỉ vì cùng tên file.

| Thay đổi sau training | Điều nên làm |
| --- | --- |
| Đổi JDK 25 build/release | Recreate cache |
| Rebuild JAR/dependency | Recreate cache |
| Đổi architecture x86-64 ↔ ARM64 | Recreate cache |
| Chuyển OS Windows ↔ Linux | Recreate cache |
| Thêm agent/VM options ảnh hưởng loading | Kiểm tra compatibility; có thể cần recreate |
| Đổi workload production mạnh so với training | Cache có thể thiếu profiles/classes hữu ích; retrain |
| Đổi JVM vendor | Kiểm tra hỗ trợ option, không mặc định portable |

**Không xem `.aot` như artifact độc lập tương đương source JAR.** Build/release pipeline nên quản lý **cache cùng JDK/container image và application version**, không chia sẻ rộng giữa các runtime khác nhau.

### Dữ liệu training phải đại diện

Nếu app production dùng một hot route nhưng training chỉ in `Hello` một lần, cache có thể không chứa những profiles quan trọng. Việc training không làm Java methods cố định vĩnh viễn; HotSpot production vẫn có thể profile và JIT theo workload runtime.

**Một cache hợp lệ nhưng chưa có profile tối ưu không phải cache lỗi.** Tính hữu ích phụ thuộc những code paths đã load/chạy trong training và khả năng áp dụng artifacts khi production.

## 10. Bài lab B — biên dịch cùng JAR thành native executable

Để làm phần này cần **GraalVM distribution có Native Image tool** cùng native compiler/linker toolchain phù hợp, ví dụ build tools trên Linux/macOS hoặc Visual Studio Build Tools trên Windows theo hướng dẫn của bản GraalVM bạn dùng.

**Không đòi `native-image` phải tồn tại trong một OpenJDK HotSpot JDK bình thường.** Đây là công cụ phụ thuộc distribution/installation.

### Bước B1. Kiểm tra công cụ

~~~bash
java -version
native-image --version
~~~

Nếu shell báo command not found, cài đúng GraalVM Native Image/toolchain theo tài liệu của bản đó. **Không tạo file `.exe` giả** hoặc rename `.jar` để “qua bước này”.

### Bước B2. Biên dịch native executable

Từ thư mục có `startup-compare.jar`:

~~~bash
native-image -jar startup-compare.jar startup-compare-native
~~~

Đây là **lệnh Native Image build**, không phải production execution. Build tool phân tích reachable code, compile/link native code và tạo executable cho OS/CPU build target.

- Trên Linux/macOS, output thường là `startup-compare-native` (dạng executable).
- Trên Windows, output thường là `startup-compare-native.exe`.
- Native Image build **có thể mất nhiều thời gian và cần nhiều CPU/RAM**, kể cả chương trình nhỏ so với `javac`.
- Những libraries phức tạp có reflection/proxy/JNI/resources có thể cần reachability metadata; chương trình lab đơn giản không cần cấu hình đặc biệt.

**Không cam kết mọi version của `native-image` cho cùng file size hay build log.** Kiểm tra `native-image --help` và docs đúng bản nếu command-line options thay đổi.

### Bước B3. Chạy output trực tiếp

**Linux/macOS:**

~~~bash
./startup-compare-native
~~~

**Windows PowerShell:**

~~~powershell
.\startup-compare-native.exe
~~~

**Stdout chương trình khi native build/run thành công:**

~~~text
message=Hello, AOT
sum=55
~~~

**Khác biệt nhìn thấy được:** không có `java -jar`, `-XX:AOTCache` hay JDK command để chạy program. Native binary vẫn phụ thuộc hệ điều hành/architecture và có thể phụ thuộc những system libraries; “standalone” không đồng nghĩa “chạy được mọi OS không cần gì khác”.

### Bước B4. Đừng dùng cùng tên “AOT artifact” cho hai file

~~~text
HotSpot:
  startup-compare.jar + startup-compare.aot + compatible JDK
                 |
                 v
        java -XX:AOTCache=... -jar ...

Native Image:
  startup-compare-native[.exe] + native OS/runtime prerequisites
                 |
                 v
          ./startup-compare-native
~~~

**Native executable không dùng HotSpot `.aot` như một “plugin cache” mặc định.** Hai build pipelines độc lập dù cùng bắt đầu từ Java bytecode.

## 11. Native Image và “closed-world assumption”

GraalVM Native Image dựa vào **static reachability analysis** từ entry points: compiler phải biết những classes/methods/fields cần thiết để đưa vào executable. Nếu ứng dụng dùng dynamic behavior mà static analysis không nhìn thấy đủ, phải bổ sung **reachability metadata** thích hợp.

Những trường hợp cần đặc biệt chú ý:

- `Class.forName(...)` với tên class tạo từ runtime config.
- Reflection tìm constructors/methods/fields theo chuỗi từ input.
- Dynamic proxies.
- JNI libraries và foreign/native integrations.
- Resources lấy từ classpath bằng tên runtime.
- Serialization frameworks hoặc libraries tạo adapters/reflection.
- Framework dependency injection, runtime scanning và generated classes.

**Không diễn giải closed-world là “Native Image không hỗ trợ reflection”.** Nó hỗ trợ theo những điều kiện khác Java HotSpot linh hoạt: phần class/method/field được dùng cần known/reachable/configured ở build time phù hợp. GraalVM có tooling và reachability metadata repository hỗ trợ nhiều libraries.

### Ví dụ minh họa reflection (không phải file chạy độc lập)

~~~java
String typeName = readNameFromConfig();
Class<?> type = Class.forName(typeName);
Object object = type.getDeclaredConstructor().newInstance();
~~~

Đoạn này là **pseudo-context Java**: `readNameFromConfig()` không được định nghĩa nên không thể biên dịch độc lập. Trên JVM, classpath ở runtime có thể chứa một implementation bổ sung phù hợp. Với Native Image, loại class sẽ được reflective loading phải được build tool biết hoặc có metadata đúng; việc thêm JAR mới sau khi native executable đã build không tự mở rộng closed-world code set.

**Giới hạn của ví dụ:** dynamic library loading/JNI trong Native Image có một số hỗ trợ riêng, nhưng không có quyền biến một binary đã đóng gói thành một JVM classloader cho mọi bytecode plugin tùy ý.

## 12. Class initialization: khác biệt tinh tế nhưng rất quan trọng

**JVM+AOT cache** vẫn chạy trên JVM và giữ class-loading/linking/initialization semantics theo các điều kiện tài liệu, nhằm không để training thực thi các side effects tùy ý rồi làm ứng dụng production sai.

**GraalVM Native Image** phân biệt:

- **Build-time initialization:** class static initializer có thể được thực thi khi tạo native image và state thích hợp được ghi vào **image heap** trong binary.
- **Run-time initialization:** class được initialization khi native executable chạy.

Một class chứa:

~~~java
final class Settings {
    static final String ENV = System.getenv("APP_ENV");
}
~~~

Đây là declaration minh họa; không có `main`.

Nếu một class được **build-time initialized**, việc đọc environment variable có thể bị “đóng băng” theo build environment. Điều đó **có thể làm production thấy giá trị của build-time env** nếu bạn cấu hình không đúng.

GraalVM Native Image cung cấp options như:

~~~bash
native-image --initialize-at-run-time=Settings -jar startup-compare.jar startup-compare-native
~~~

Đây là **lệnh ví dụ về option**, không phải yêu cầu chạy ngay với JAR lab vì lab **không có class `Settings`**. Nếu áp dụng trong ứng dụng thật, thay class name bằng tên đầy đủ của class có static initialization thích hợp và kiểm tra compiler/version docs.

**Bài học:** không tùy tiện cho crypto providers, random seeds, time-dependent config, system properties hoặc environment-derived state chạy ở **build time**. Với Native Image, class initialization policy là một phần rất quan trọng của correctness và reproducibility.

### Khác với AOT cache snapshot

Không coi HotSpot AOT cache là **Native Image image heap** hay ngược lại. Chúng khác dữ liệu được phép lưu, lifecycle và runtime compatibility. **Không có ngụ ý** một cache `.aot` lưu toàn bộ Java heap của training run rồi khôi phục object identities của user sessions production.

## 13. Runtime, GC, JIT và flags khác nhau thế nào?

| Vấn đề | HotSpot + AOT cache | Native Image |
| --- | --- | --- |
| Launcher | `java` | Executable native |
| JIT compiler | Có thể tiếp tục C1/C2/tiered compilation | Không có HotSpot tiered JIT thông dụng trong native runtime |
| Class data | JVM có thể map AOT cache | Nhiều class/runtime artifacts đã được linked vào binary |
| GC | HotSpot GC đã chọn (G1, v.v.) | Native Image GC implementation/configuration |
| Heap flags | JVM flags như `-Xmx` | Native Image options có thể khác, kiểm tra `--help`/docs |
| JVM diagnostic flags | `-Xlog:aot`, `-Xlog:class+load`, JFR/JVM tools | Native-image-specific runtime/diagnostics; không dùng nguyên bộ `-XX` HotSpot |
| Runtime reflection | JVM semantics đầy đủ theo classpath/module rules | Thường bị ràng buộc reachability metadata |
| Runtime code discovery | JVM classloading có thể load JARs theo APIs/cấu hình | Closed-world model, không tự nạp bytecode chưa có khi build |

**Native Image vẫn có garbage collection** trong phần runtime Java cần thiết. Câu “Native Image không chạy JVM nên không còn GC” là sai. Nó không sử dụng HotSpot GC/JIT theo cách của `java`, chứ không bỏ memory management.

### JIT trên HotSpot có thể thắng ở workload dài

JDK 25 AOT cache giúp HotSpot JIT khởi đầu thuận lợi hơn nhờ profiles training, **nhưng vẫn có thể tiếp tục quan sát runtime workload và recompilation**. Native Image thường đặt trọng tâm giảm runtime overhead/startup và đóng gói tối ưu theo build-time knowledge. Với một số throughput-heavy long-running workloads, JIT adaptive optimization có thể lợi thế; **không có một người thắng duy nhất**.

## 14. Cách so sánh startup và throughput đúng

**Hai dòng `message=...` và `sum=55` cho biết cùng semantics**, nhưng không chứng minh AOT cache/native image nhanh hơn bao nhiêu.

Các metric cần phân biệt:

| Metric | Ý nghĩa | Cách kiểm chứng |
| --- | --- | --- |
| **Build time** | Thời gian/công sức tạo JAR, cache hoặc native binary | Đo build pipeline |
| **Cold start** | Từ process launch đến ready/first useful output | Đo end-to-end nhiều process starts |
| **Warmup** | Thời gian tới steady throughput | Benchmark/chạy tải theo giai đoạn |
| **Steady-state throughput** | Số requests/operations hoàn thành mỗi đơn vị thời gian | Workload đủ lâu và lặp lại |
| **Tail latency** | P95/P99 response times | Load testing với concurrency thực |
| **RSS/native memory** | Tổng memory process theo OS | Process/container metrics |
| **Java heap/live-set** | Java objects reachable + heap sizing | JVM/native-runtime-specific diagnostics |
| **Binary/artifact size** | Tổng file deploy và dependency footprint | Filesystem/container image inspection |
| **Operational effort** | Rebuild/training metadata, toolchains, flags và portability | Theo build/release pipeline |

### Đối chứng JVM không cache và có cache

~~~bash
java -XX:AOTMode=off -jar startup-compare.jar
java -XX:AOTCache=startup-compare.aot -jar startup-compare.jar
~~~

Hai lệnh này cần **JDK 25**. Trong phép đo performance thật, xác minh trước cache được load bằng `-Xlog:aot`, rồi đo **không bật verbose logs** để tránh méo kết quả.

### Đối chứng native

~~~bash
./startup-compare-native
~~~

Lệnh trên dành cho POSIX OS với binary đã build thành công. Trên Windows dùng `.\startup-compare-native.exe`.

**Không thực hiện một lần chạy mỗi mode và tuyên bố “Native nhanh hơn 100 lần”.** OS file cache, antivirus, page faults, JVM ergonomics, CPU frequency, container startup, app dependencies và I/O có thể che hoặc khuếch đại khác biệt.

### Khuyến nghị đo

1. Dùng **cùng business logic và inputs**.
2. Tách **build time** khỏi runtime.
3. Nhiều process starts, có thống kê median/P95.
4. Workload đủ thật để xét JIT steady-state.
5. Đo CPU, memory, peak RSS và GC bên cạnh latency.
6. Ghi rõ JDK/GraalVM versions, target OS/CPU, JVM/native flags.
7. Tách I/O/database/network latency khỏi Java startup khi cần.
8. Ghi lại native compiler/toolchain/size của binary và deployment image.
9. Không ép flags JVM sang Native Image khi chúng không được hỗ trợ.
10. Tái benchmark mỗi khi thay version/runtime/CPU.

**Kết quả tùy application.** Một CLI/serverless function ưu tiên cold-start có thể được Native Image cải thiện nhiều; một server chạy hàng tuần, có dynamic plugins và JIT-beneficial workload có thể thích hợp HotSpot+AOT hơn. Đây là **giả thuyết kiến trúc**, không phải số đo cho ứng dụng cụ thể.

## 15. Triển khai trên container và máy khác

### HotSpot + cache

Ví dụ deployment cần:

~~~text
container/runtime:
  compatible JDK/JVM
  startup-compare.jar
  startup-compare.aot
  correct entry command:
    java -XX:AOTCache=startup-compare.aot -jar startup-compare.jar
~~~

Bạn **không nên** copy `.aot` tạo trên OS/CPU/JDK khác rồi mặc định compatible. Với image build, training và production workload phải đủ đại diện; nếu pipeline build trên x86-64 mà production chạy ARM64, cần tái tạo cache phù hợp thay vì rename.

### Native Image

~~~text
container/runtime:
  startup-compare-native
  native runtime libraries cần thiết cho target
  command:
    ./startup-compare-native
~~~

Binary có thể giúp giảm deployment size so với nguyên JDK, nhưng không phải lúc nào container image nhỏ nhất cũng là native: base image/system dependencies, debug symbols và static/dynamic linking choices ảnh hưởng nhiều.

Native executable tạo trên Linux **không chạy trực tiếp trên Windows** như một portable JAR. Thường phải cross-compile/có toolchain phù hợp hoặc build trên target OS/architecture. Java `.jar` là bytecode portable theo điều kiện version/dependencies; file `.aot` lại có compatibility constraints nghiêm ngặt riêng.

## 16. Quy trình chọn giải pháp

### Khi nên ưu tiên JVM + AOT cache

- Đang triển khai trên HotSpot JDK có hỗ trợ cache.
- Muốn cải thiện **startup/warmup** nhưng giữ Java runtime/JIT/classloading linh hoạt.
- Có plugin/reflection-heavy libraries và không muốn closed-world metadata phức tạp.
- Có những endpoints hot thay đổi theo tải production, nên JIT adaptive optimization có giá trị.
- Đã có stack toolchain của JDK/JFR/JMX/GC/tuning.
- Deployment luôn đi cùng JDK image và có pipeline training tái lập được.

### Khi nên thử Native Image

- Cold startup và low idle RSS cực kỳ quan trọng.
- Ứng dụng có dependency graph ổn định, khả năng kiểm soát reflection/resources.
- Sẵn sàng đầu tư build time và native toolchain.
- Có khả năng test build-time class init, locale/timezone/resources/certificates/JNI.
- Deployment theo OS/CPU target cụ thể, chấp nhận rebuild cho platform khác.
- Đã có framework/tooling hỗ trợ Native Image metadata tốt.

### Khi chưa nên kết luận

Nếu ứng dụng có classloading động rất mạnh, runtime-generated bytecode hoặc native libraries phức tạp, đừng mặc định Native Image không làm được, nhưng phải **kiểm tra compatibility metadata và build limitations** thật. Ngược lại nếu mục tiêu chỉ giảm JVM cold start, không mặc định phải đổi cả runtime sang Native Image khi HotSpot AOT cache có thể đủ.

## 17. Các câu hỏi quan trọng khi thiết kế pipeline

**17.1. Training AOT cache có cần dữ liệu production thật không?**  
Không nhất thiết. Nên dùng **representative workload** với dữ liệu giả phù hợp, đủ chạm những classes/methods quan trọng mà không rò rỉ secrets. Training sẽ chọn artifacts theo behavior, nên workload nghèo nàn làm cache ít hữu ích.

**17.2. Cache có tự cập nhật sau khi JVM chạy với tải mới không?**  
Không coi file `.aot` đã tạo là một file continuously refreshed chỉ vì JIT tiếp tục profile trong production. Nếu muốn cache cập nhật, cần quy trình **retrain/reassemble** theo công cụ/version. JVM có thể JIT code mới bình thường dù cache không ghi lại các profiles mới.

**17.3. Native binary có thể dùng file config khác lúc chạy không?**  
Có thể, nếu application/runtime thiết kế đọc config tại runtime. **Closed-world** ràng buộc **code/class reachability** chứ không nói mọi dữ liệu runtime bị đóng cứng; nhưng class initialization lúc build và resources được đóng gói có thể làm một số giá trị khác biệt.

**17.4. Dùng JVM+AOT có mất tính tương thích JPMS không?**  
Không. Ứng dụng vẫn có classpath/module path và JVM semantics; tuy nhiên cache có compatibility conditions với application/modules/options. Với Native Image, analysis/linking cũng phải xử lý module/library use theo toolchain.

**17.5. Native Image có thể dùng JFR/JMX như HotSpot không?**  
Không nên mặc định đầy đủ cùng một bộ công cụ/flags. GraalVM Native Image có những capabilities riêng (có thể bao gồm monitoring/profiling features tùy edition/version), nên kiểm tra **tài liệu đúng distribution**, không dùng HotSpot option list như hợp đồng.

**17.6. Cái nào “AOT compile machine code” rõ nghĩa hơn?**  
**Native Image** rõ ràng compile reachable application bytecode thành **native executable**. **JDK 25 AOT cache** tập trung preloading/linking/profiles, và JIT sinh optimized machine code trong runtime; đừng nói chỉ cần `AOTCacheOutput` là đã native compile toàn bộ ứng dụng.

## 18. Troubleshooting theo triệu chứng

| Triệu chứng | Loại | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- | --- |
| `Unrecognized VM option 'AOTCacheOutput'` | JVM cache | JDK 17/21 hoặc non-supporting VM | Kiểm tra `java -version`; dùng JDK 25 tương thích |
| `.aot` không xuất hiện | JVM cache | Training/assembly lỗi, permissions | Kiểm tra exit code và AOT logs |
| App chạy nhưng cache không dùng | JVM cache | Mismatch JDK/JAR/OS/CPU/options | `-Xlog:aot`; test strict `AOTMode=on` |
| Startup không nhanh hơn rõ | JVM cache | Workload quá nhỏ, profiles/training thiếu | Đo nhiều process starts và workload đại diện |
| Cùng cache có node chạy node lỗi | JVM cache | Different JDK/image/arch | Tạo cache cho đúng target |
| `native-image: command not found` | Native Image | Không có GraalVM tool trên PATH | Cài toolchain/distribution phù hợp |
| Native build thiếu native compiler | Native Image | GCC/Clang/MSVC dependencies | Cài OS-specific build tools theo docs |
| Native build thiếu reflection/proxy metadata | Native Image | Closed-world analysis không biết dynamic code | Bổ sung reachability metadata |
| Native binary có config sai | Native Image | Static initialization đã chạy ở build time | Chọn run-time init / đọc config runtime |
| Native app không chạy máy khác | Native Image | OS/CPU/libs mismatch | Build đúng target và kiểm tra system libraries |
| Native build quá lâu/RAM cao | Native Image | Whole-program analysis/codegen | Điều chỉnh build resources/pipeline |
| Native app OOME | Native Image | Native runtime heap/memory policy không phù hợp | Xem native runtime diagnostics, không dùng mù HotSpot flags |

**Chẩn đoán theo loại artifact trước.** Một lỗi `AOTCacheOutput` của JDK 17 không liên quan Native Image build; một lỗi reachability của Native Image không sửa bằng `-Xlog:aot` HotSpot.

## 19. Sai lầm và hiểu nhầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “AOT = mọi thứ luôn được compile thành machine code trước runtime.” | AOT có nhiều loại artifacts, từ class metadata tới profile/code. |
| “`.aot` là `.exe` của Java.” | `.aot` của HotSpot là **cache**, không chạy trực tiếp. |
| “CDS `.jsa` là native executable.” | CDS archive được JVM đọc, không tự execute. |
| “Có AOT cache thì Java không cần JVM.” | **Vẫn cần HotSpot/JVM**. |
| “JDK 25 `AOTCacheOutput` tạo Native Image.” | Nó tạo JVM AOT cache, không phải native executable. |
| “Native Image không có garbage collector.” | Có Java runtime support/GC trong native binary. |
| “Native Image vẫn chạy HotSpot C1/C2 JIT như `java`.” | Nó AOT compile thành binary, runtime model khác. |
| “AOT method profile là machine code lưu sẵn.” | Profiles giúp JVM JIT compile sớm hơn, không đồng nghĩa native binary. |
| “Native Image không hỗ trợ reflection.” | Hỗ trợ tùy analysis/reachability metadata và constraints. |
| “Native Image có dynamic plugin classloading tùy ý y hệt JVM.” | Closed-world model đặt giới hạn với code chỉ được biết lúc runtime. |
| “Cứ đổi đuôi `.jar` thành `.exe` là native.” | Phải thực sự chạy Native Image compiler/linker. |
| “JAR chạy được ở mọi máy không cần Java.” | Bytecode cần runtime Java hỗ trợ version/dependencies. |
| “AOT cache portable giữa mọi JDK/OS/CPU.” | Cache phụ thuộc combination application/JDK/OS/arch. |
| “Native binary tạo trên Linux chạy thẳng trên Windows.” | Binary target-specific. |
| “Native build không cần native compiler/linker.” | Thường cần toolchain native phù hợp. |
| “AOT cache chứa toàn bộ heap state của training.” | Không phải process snapshot, chỉ artifacts được hỗ trợ. |
| “Native Image build-time init luôn an toàn.” | Có thể đóng băng env/time/resources không mong muốn. |
| “JVM+AOT không còn JIT warmup.” | Có thể giảm, nhưng JIT/adaptive optimization vẫn tồn tại. |
| “Có cache là startup chắc chắn giảm 50%.” | Phải benchmark ứng dụng thực; lợi ích tùy workload. |
| “Native Image luôn có throughput cao nhất.” | JIT có thể hiệu quả hơn cho một số workloads dài. |
| “Runtime flags HotSpot đều dùng được trên native binary.” | Hai runtime có options/capabilities khác nhau. |
| “JEP 515 thay Java source thành binary.” | JEP 515 ghi nhận AOT method profiles, không thay định dạng ứng dụng. |
| “Classpath đổi sau AOT cache không sao.” | Có thể invalidate cache; cần recreate. |
| “Native executable không phụ thuộc libc/OS.” | Có thể có system library/native runtime prerequisites. |
| “Một lần chạy benchmark đủ kết luận.” | Nhiễu hệ thống và workload cần đo nhiều lần có kiểm soát. |

## 20. Câu hỏi ôn tập có đáp án

**1.** `startup-compare.aot` có chạy trực tiếp như program không?  
**Đáp án:** Không. Nó là AOT cache của JVM, được đọc khi dùng `java -XX:AOTCache=...`.

**2.** Native Image tạo đầu ra gì?  
**Đáp án:** Native executable/shared library cho OS/CPU target, chứa compiled application code và những phần Java runtime cần thiết.

**3.** JVM có AOT cache còn dùng JIT không?  
**Đáp án:** Có thể. JDK 25 hỗ trợ AOT method profiles để JIT có dữ liệu tối ưu ngay đầu runtime.

**4.** JDK version nào trong bài có workflow `AOTCacheOutput`?  
**Đáp án:** **JDK 25** theo tài liệu ví dụ. Java source vẫn có thể biên dịch với Java 17.

**5.** Vì sao `java -jar startup-compare.jar` và `./startup-compare-native` khác nhau?  
**Đáp án:** Một lệnh khởi động JVM thực thi bytecode, một lệnh khởi động binary native đã biên dịch.

**6.** JEP 483 lưu loại công việc gì?  
**Đáp án:** AOT class-loading/linking artifacts từ training/assembly.

**7.** JEP 515 bổ sung gì ở JDK 25?  
**Đáp án:** Ahead-of-Time Method Profiling — lưu method profiles đã ghi nhận cho JVM/JIT về sau.

**8.** Vì sao cache có thể không load sau khi đổi JAR?  
**Đáp án:** Cache gắn với application/JDK/OS/CPU configuration và consistency checks.

**9.** Native Image có thể cần cấu hình reflection vì sao?  
**Đáp án:** Static reachability analysis có thể không biết những classes/methods chỉ được gọi theo tên runtime.

**10.** Class initialization ở build time Native Image có rủi ro gì?  
**Đáp án:** Có thể lưu static state phụ thuộc env/config của máy build thay vì máy production nếu cấu hình sai.

**11.** Native Image có GC không?  
**Đáp án:** Có thể dùng GC tương ứng với runtime của native binary; không phải “không còn GC”.

**12.** `-XX:AOTMode=on` dùng khi nào?  
**Đáp án:** Để yêu cầu cache và chẩn đoán compatibility trong môi trường kiểm thử có kiểm soát.

**13.** Cache tồn tại chứng minh đã sử dụng không?  
**Đáp án:** Không. Cần runtime diagnostics như `-Xlog:aot` và kiểm tra validation/mapping.

**14.** Chạy một lần Native Image nhanh hơn HotSpot có đủ kết luận không?  
**Đáp án:** Không; cần đo cold start, warmup, throughput, memory nhiều lần trong điều kiện tương đương.

## 21. Checklist tự thực hành

- [ ] Đọc `java -version`, biết rõ build nào hỗ trợ JDK 25 AOT options.
- [ ] Chạy chương trình Java 17+ và xác nhận `message=Hello, AOT` / `sum=55`.
- [ ] Biên dịch và đóng `startup-compare.jar` có Main-Class đúng.
- [ ] Dùng HotSpot JDK 25 chạy baseline `AOTMode=off`.
- [ ] Tạo `startup-compare.aot` bằng `AOTCacheOutput` hoặc record/create.
- [ ] Chạy lại `java -XX:AOTCache=... -jar startup-compare.jar`.
- [ ] Đọc `-Xlog:aot` để xác nhận cache được chấp nhận; không suy từ file tồn tại.
- [ ] Không đổi JAR/JDK/OS/CPU giữa training và production test.
- [ ] Trên GraalVM có Native Image tool, build executable từ cùng JAR.
- [ ] Chạy executable trực tiếp, không dùng `java -jar`.
- [ ] So sánh outputs để chứng minh semantics của chương trình mẫu.
- [ ] Phân biệt cache data và compiled binary trong build artifacts.
- [ ] Chỉ benchmark sau khi bảo đảm cả hai paths hoạt động đúng.
- [ ] Nếu app thực dùng reflection, đánh giá Native Image reachability metadata.
- [ ] Kiểm tra config build-time/run-time initialization trước triển khai.
- [ ] Ghi lại những ràng buộc môi trường thay vì kết luận một giải pháp luôn thắng.

## 22. Nguồn chính thức

- [Oracle JDK 25 — java Command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:AOTCache`, `AOTCacheOutput`, `AOTConfiguration`, `AOTMode`; training/assembly/production và compatibility constraints.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): cơ chế record/training AOT class loading/linking data, là nền tảng JDK 24.
- [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): cải thiện commands tạo AOT cache trong JDK 25.
- [OpenJDK JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): lưu method profiles để cải thiện startup/warmup JIT.
- [Inside.java — Run Into the New Year with Java's AOT Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/): minh họa workflow AOT cache và những thay đổi JDK 25.
- [Oracle GraalVM 25 — Native Image Basics](https://docs.oracle.com/en/graalvm/jdk/25/docs/reference-manual/native-image/basics/): executable model, build-time/run-time initialization, image heap và closed-world analysis.
- [GraalVM Native Image Reference Manual](https://www.graalvm.org/reference-manual/native-image/): tạo native executable với `native-image`, prerequisites và build options.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): reflection, JNI, dynamic proxy và resource metadata.
- [GraalVM Native Image — Class Initialization](https://www.graalvm.org/latest/reference-manual/native-image/basics/#build-time-vs-run-time): phân biệt build-time và run-time class initialization.
- [JVMS Java SE 25](https://docs.oracle.com/javase/specs/jvms/se25/html/index.html): Java class-file/VM semantics; không bắt buộc compiler/AOT implementation cụ thể.
- [Oracle JDK 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): kiến thức nền về CDS/archive trên HotSpot.

**Kết luận:** **JVM AOT cache** và **native compilation** đều “làm trước một phần việc” nhưng **không phải cùng giải pháp**. Trên JDK 25, `.aot` giúp HotSpot chuẩn bị class-loading/linking data và method profiles, **vẫn dùng `java` và vẫn có JIT/GC/runtime Java**. Với GraalVM Native Image, build tool phân tích reachable bytecode và sinh **native executable target-specific**, chứa runtime cần thiết nhưng không phụ thuộc việc khởi động HotSpot theo mô hình `java -jar`. Khi chọn công nghệ, hãy xem **startup/warmup, throughput, RSS, native build time, reflection/dynamic loading, initialization policy, platform compatibility và vận hành thực tế** — không chỉ so sánh tên gọi “AOT”.
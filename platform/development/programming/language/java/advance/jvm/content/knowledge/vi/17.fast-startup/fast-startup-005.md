# AOT cache của HotSpot: học từ lần chạy thử, tạo cache và dùng lại theo phiên bản hỗ trợ

**Ahead-of-Time (AOT) cache của HotSpot** là cơ chế lưu lại một phần công việc chuẩn bị mà JVM đã học được khi chạy ứng dụng, để những lần khởi động tiếp theo có thể **tái sử dụng thông tin phù hợp** và giảm thời gian startup/warm-up. Tư tưởng chính: thay vì mỗi tiến trình Java phải hoàn toàn tự khám phá, load/link và profile tất cả cùng một đường thực thi ngay lúc phục vụ người dùng, ta cho JVM quan sát **training run**, tạo **AOT cache**, rồi chạy ứng dụng cùng phiên bản/build phù hợp với cache đó.

**Điểm phải nhớ ngay:** đây là tính năng có mốc hỗ trợ cụ thể của **HotSpot**, không phải “mọi Java 17 đều có AOT cache mới”. **JDK 24** đưa AOT class loading/linking vào AOT cache (JEP 483). **JDK 25** bổ sung **Ahead-of-Time Method Profiling** (JEP 515) và rút gọn lệnh tạo cache bằng **JEP 514**. **JDK 26** mở rộng cách cache object dùng được với nhiều GC, bao gồm ZGC theo **JEP 516**. Phải đối chiếu JVM vendor, JDK build, OS/CPU và flags của phiên bản **thực sự chạy**.

AOT cache này **không phải** một quy trình chuyển `.class` thành native executable độc lập, **không phải** thư viện `native-image` của GraalVM và **không bảo đảm** mọi method của ứng dụng đã được biên dịch thành native code sẵn trước khi production start.

## 1. Bài toán: startup và warm-up của HotSpot

Một JVM mới khởi chạy thường phải hoàn thành nhiều công việc:

- Khởi tạo các bộ phận VM và runtime.
- Đọc classpath/modules, tìm và mở các classes cần dùng.
- Parse class file, kiểm tra bytecode, load và link classes.
- Thực hiện class initialization khi chương trình thật sự cần (`<clinit>`, theo Java semantics).
- Chuẩn bị một số runtime objects và metadata.
- Chạy interpreter/C1, thu thập invocation/branch/type profiles.
- Biên dịch các hot methods bằng JIT (C1/C2) khi có đủ căn cứ.
- Hoàn thành warm-up của ứng dụng (cache kết nối, object graph, libraries).

```text
KHÔNG SỬ DỤNG AOT CACHE
Process start
     │
     ├──► Load và link classes
     ├──► Chuẩn bị một số JVM structures
     ├──► Chạy và quan sát method profiles
     ├──► JIT compile hot methods
     └──► Phục vụ workload
               │
               ▼
           steady state (nếu đạt)
```

Nếu cùng ứng dụng được khởi động lại liên tục, một phần công việc có thể được làm **lặp đi lặp lại**. AOT cache cho phép chuyển **phần thích hợp** sang giai đoạn chuẩn bị và reuse ở các lần khởi động tương thích.

### Hai chỉ số không giống nhau

| Chỉ số | Ý nghĩa | Cách đo |
| --- | --- | --- |
| **Startup latency** | Từ lúc gọi launcher tới lúc ứng dụng đạt điểm ready/first useful response | Timestamp khách quan, ready probe, trace |
| **Warm-up time** | Thời gian tới throughput/latency tương đối ổn định sau startup | Nhiều cửa sổ workload, compiler/CPU/latency telemetry |
| **Steady-state throughput** | Năng lực xử lý khi đã warm-up đủ | Load test nhiều lần, công việc tương đương |
| **CPU during warm-up** | Công sức JVM/JIT/class loading và ứng dụng sử dụng | JFR/OS CPU/profile |
| **Memory footprint** | Heap, native memory và chi phí cache mapping | Heap/RSS/NMT khi khả dụng |

AOT cache nhằm **cải thiện startup/warm-up**; **không đảm bảo** steady-state throughput luôn tăng hay mọi application đều nhanh hơn cùng một tỷ lệ.

## 2. AOT cache thực sự chứa gì?

Nội dung cache **phụ thuộc JDK release và HotSpot build**:

| Thành phần | Vai trò | Lưu ý |
| --- | --- | --- |
| **Classes đã xử lý** | Cho phép tái dùng kết quả class loading/linking được cho phép bởi JEP 483 | Không bảo đảm mọi class của cả ứng dụng đều đã vào cache |
| **Linked metadata / resolved information** | Giảm công việc link/load lặp lại phù hợp | Có consistency restrictions; phụ thuộc cấu hình |
| **Một số heap objects JVM có thể cache** | Khởi tạo trước các object structures được chọn | Không phải snapshot của toàn bộ heap production |
| **Method execution profiles (JDK 25+)** | JIT được dùng profile học từ training trước khi có đủ profile mới | Không đồng nghĩa cache lưu sẵn mọi C2 native method |
| **Những artifacts tương lai (tùy release)** | AOT framework có thể mở rộng | Luôn xác minh release notes; đừng dự đoán nội dung cache chưa được triển khai |

**Đặc biệt:** trên JDK 25, “Ahead-of-Time Method Profiling” nghĩa là **lưu profile để JIT có thể bắt đầu tối ưu sớm hơn**, không nên diễn giải rằng JEP 515 đã đóng gói toàn bộ optimized C2 machine code của chương trình vào `.aot` như một binary native độc lập.

### AOT cache không phải một heap dump

Heap dump ghi một snapshot object graph phục vụ debugging; còn AOT cache chỉ lưu artifacts được JVM coi là hợp lệ để reuse, dưới quy tắc consistency. Không lấy một `.hprof` rồi đổi tên thành `.aot`. Không kỳ vọng AOT cache giữ runtime user sessions, trạng thái kết nối TCP, credentials của một process hoặc các tài nguyên không thể portable.

### AOT cache không bỏ qua yêu cầu đúng đắn của Java

Class loading, linking, initialization, class-loader identity, JVMTI/instrumentation, reflection và dynamic loading đều có semantics phải được bảo toàn. Nếu cache không tương thích, runtime có thể từ chối dùng cache hoặc từ chối khởi động trong mode strict; **không** được sử dụng cache cũ để chạy class definitions không khớp.

## 3. Ba pha cốt lõi: record → create → production

JEP 483 (JDK 24) dùng mô hình ba pha rõ ràng:

```text
Pha A: TRAINING / RECORD
  Chạy ứng dụng với workload đại diện
         │ JVM quan sát classes/paths
         ▼
  AOT Configuration (.aotconfig)
         │
         ▼
Pha B: ASSEMBLY / CREATE
  Đọc configuration, chuẩn bị artifacts
         │ Ứng dụng main KHÔNG chạy ở pha create
         ▼
  AOT Cache (.aot)
         │
         ▼
Pha C: PRODUCTION / ON
  Chạy ứng dụng với cache tương thích
         │
         └──► Reuse artifacts, vẫn thực thi Java bình thường
```

### Vì sao tách record và create?

Recording nhận biết **ứng dụng thật làm gì** trên đường chạy đặc trưng. Cache assembly có thể xử lý thêm classes và linked objects trong một VM process riêng, không cần thực thi business workload lại như một production request.

Cách tách pha còn giúp phân chia **ngân sách tài nguyên**: training có thể gần deployment environment, còn assembly chạy trong môi trường build/CI có tài nguyên phù hợp.

**Đừng nhầm:** “AOT” không có nghĩa mọi việc xảy ra tại `javac` compile time. Training có thể **thật sự chạy Java code** cùng inputs/systems giả lập, sau đó assembly xây artifacts cho lần chạy tới.

## 4. Những cờ AOT quan trọng theo bản HotSpot

Các cờ dưới đây thuộc **HotSpot JDK có hỗ trợ AOT cache (JDK 24+)**:

| Cờ | Tác dụng |
| --- | --- |
| `-XX:AOTMode=record` | Chạy application trong giai đoạn training và ghi configuration |
| `-XX:AOTConfiguration=file.aotconfig` | Đường dẫn file cấu hình AOT được tạo/đọc |
| `-XX:AOTMode=create` | Assembly phase đọc configuration và tạo cache |
| `-XX:AOTCache=file.aot` | Dùng/định vị cache, tùy mode; trong `create` là output |
| `-XX:AOTMode=on` | Production mode yêu cầu cache phù hợp, giúp phát hiện lỗi rõ |
| `-XX:AOTMode=off` | Không dùng AOT cache trong run đang xét |
| `-XX:AOTCacheOutput=file.aot` | Từ **JDK 25**: record + assembly thuận tiện trong một invocation |
| `-XX:AOTMode=auto` | JVM tự chọn hành vi phù hợp theo options/cache khả dụng trong các versions hỗ trợ |

**Không áp các cờ này cho JDK 17:** một bản HotSpot 17 thông dụng không có JEP 483. Thử `java -XX:AOTCacheOutput=app.aot ...` trên JDK 17 có thể gây `Unrecognized VM option`; đó là lỗi **version/feature availability**, không phải code Java sai.

### Không bật nhiều chế độ đối nghịch

Khi dùng cache đầu vào `-XX:AOTCache=app.aot`, không đồng thời định nghĩa cache đầu ra `-XX:AOTCacheOutput=...` trong cùng một lần gọi nếu version docs nói hai options xung đột.

Trước khi tạo cache, xem tài liệu cho **đúng JDK release** và chạy `java -version` từ **đúng java executable**. Không dùng `-XX:+IgnoreUnrecognizedVMOptions` để “giấu” AOT flags không được hỗ trợ: ứng dụng có thể chạy mà **không thật sự dùng cache**.

## 5. Chương trình Java 17+ dùng làm demo AOT

Mã sau **biên dịch được bằng Java 17+**, còn **quy trình cache AOT phải chạy trên HotSpot JDK 24/25/26 có hỗ trợ**. Tạo file **`AotCacheDemo.java`**:

```java
public final class AotCacheDemo {
    interface Rule {
        int apply(int value);
    }

    static final class AddOne implements Rule {
        @Override
        public int apply(int value) {
            return value + 1;
        }
    }

    static final class Twice implements Rule {
        @Override
        public int apply(int value) {
            return value * 2;
        }
    }

    private static volatile long resultSink;

    static long runScenario() {
        Rule first = new AddOne();
        Rule second = new Twice();
        long total = 0;

        for (int i = 0; i < 20_000; i++) {
            total += first.apply(i % 10);
        }
        for (int i = 0; i < 8_000; i++) {
            total += second.apply(i % 4);
        }
        resultSink = total;
        return total;
    }

    public static void main(String[] args) {
        if (args.length != 0) {
            throw new IllegalArgumentException("No arguments expected");
        }
        long answer = runScenario();
        System.out.println("application: AotCacheDemo");
        System.out.println("checksum: " + answer);
        System.out.println("ready: true");
    }
}
```

### Biên dịch và đóng gói thành JAR

```bash
javac -encoding UTF-8 AotCacheDemo.java
jar --create --file app.jar --main-class AotCacheDemo AotCacheDemo.class
```

Nếu JDK `jar` không hỗ trợ syntax này, kiểm tra `jar --help` đúng version. Hai **nested classes** cũng cần có trong JAR. Lệnh `jar` phía trên chỉ thêm `AotCacheDemo.class`, **chưa thêm** các file `AotCacheDemo$Rule.class`, `AotCacheDemo$AddOne.class` và `AotCacheDemo$Twice.class` được sinh khi compile. Vì vậy để có một **JAR chạy được đầy đủ**, dùng lệnh sau thay cho dòng `jar` vừa minh họa:

```bash
jar --create --file app.jar --main-class AotCacheDemo AotCacheDemo.class AotCacheDemo$Rule.class AotCacheDemo$AddOne.class AotCacheDemo$Twice.class
```

**Lưu ý shell:** ký tự `$` trong tên class files có thể được PowerShell/bash diễn giải khác nhau. Để tránh lỗi shell, thay cả hai lệnh `jar` kể trên bằng lệnh **portable hơn trên thư mục build sạch**:

```bash
jar --create --file app.jar --main-class AotCacheDemo -C . .
```

**Chỉ sử dụng lệnh `-C . .` khi thư mục làm việc sạch chỉ chứa source/classes cần đóng gói và không có JAR sẵn**; nếu không, command có thể tự gói nhiều files ngoài ý muốn. Với bài lab, cách ổn định là đặt toàn bộ files vào thư mục riêng, dùng một class không có nested classes (xem biến thể phần dưới), hoặc thêm tên class files theo đúng quoting của shell. Trong các lệnh AOT tiếp theo, giả sử bạn đã có **`app.jar` hợp lệ, chứa các classes cần thiết**; có thể kiểm tra bằng `jar --list --file app.jar`.

### Phiên bản đóng gói được khuyến nghị cho lab

Để không phụ thuộc shell glob/quoting, dùng riêng **PowerShell**:

```powershell
jar --create --file app.jar --main-class AotCacheDemo 'AotCacheDemo.class' 'AotCacheDemo$Rule.class' 'AotCacheDemo$AddOne.class' 'AotCacheDemo$Twice.class'
```

Trên **bash/sh**, dùng:

```bash
jar --create --file app.jar --main-class AotCacheDemo 'AotCacheDemo.class' 'AotCacheDemo$Rule.class' 'AotCacheDemo$AddOne.class' 'AotCacheDemo$Twice.class'
```

Hai lệnh trên thêm đúng bốn class files; hãy dùng **một** lệnh tùy shell, không chạy tất cả các biến thể liên tiếp để ghi đè JAR rồi làm thay đổi artifacts giữa training/production.

### Chạy Java thường trước khi làm AOT

```bash
java -cp app.jar AotCacheDemo
```

**Standard output chính xác do ứng dụng in:**

```text
application: AotCacheDemo
checksum: 134000
ready: true
```

**Kiểm tra phép tính:**

- Với `i % 10` chạy 0..9, `AddOne` cho tổng mỗi 10 iterations = **55**. Có 2.000 chu kỳ trong 20.000 iterations → **110.000**.
- Với `i % 4` chạy 0..3, `Twice` cho tổng mỗi 4 iterations = **12**. Có 2.000 chu kỳ trong 8.000 iterations → **24.000**.
- Tổng = **134.000**. Kết quả số học không phụ thuộc AOT/JIT, vì cache phải bảo toàn Java semantics.

Bài lab dùng `volatile resultSink` để giữ kết quả có tác dụng quan sát theo Java Memory Model; **điều đó không buộc JIT phải compile method với một cấp cụ thể**.

## 6. JDK 24: quy trình ba pha tường minh

**Yêu cầu:** HotSpot JDK 24 build hỗ trợ JEP 483, đúng OS/architecture. Đã biên dịch và tạo `app.jar` hợp lệ ở mục 5.

### 6.1. Record

```bash
java -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -cp app.jar AotCacheDemo
```

Trong pha này **application thực sự chạy**, vì vậy có stdout:

```text
application: AotCacheDemo
checksum: 134000
ready: true
```

JVM đồng thời ghi những thông tin training vào `app.aotconfig`. Có thể có thêm logs nếu bật các options chẩn đoán; **không dự đoán trước** thời gian và kích thước file.

### 6.2. Create

```bash
java -XX:AOTMode=create -XX:AOTConfiguration=app.aotconfig -XX:AOTCache=app.aot -cp app.jar
```

Pha **create** dùng AOT configuration để sinh `app.aot`. **Không gọi `main` ứng dụng** ở pha này; không mong thấy ba dòng stdout tính toán. Khi build tạo cache lỗi, phải sửa vấn đề tương thích/đầu vào, **không** sử dụng file output chưa được xác minh.

### 6.3. Run với cache

```bash
java -XX:AOTMode=on -XX:AOTCache=app.aot -cp app.jar AotCacheDemo
```

Application vẫn phải in:

```text
application: AotCacheDemo
checksum: 134000
ready: true
```

**Điều cần phân biệt:** output đúng chứng minh logic ứng dụng **không đổi**, **không tự chứng minh** cache đã được sử dụng. `AOTMode=on` hữu ích để buộc VM kiểm tra khả năng load cache; cần thêm startup logs để xác minh artifacts được dùng.

### 6.4. Không thay JAR giữa ba pha

Sau recording, **giữ nguyên `app.jar`** cho assembly và production test. Recompile, repackage hoặc đổi classpath dù source “giống nhau” có thể đổi file timestamps/bytes và phá những điều kiện cache consistency. Nếu ứng dụng đổi build, **xóa cache cũ và tạo lại** trên artifacts cuối cùng.

## 7. JDK 25+: cách ngắn gọn từ training tới cache

**JEP 514** cho phép dùng `-XX:AOTCacheOutput=...` để record và assemble trong một lời gọi thuận tiện:

```bash
java -XX:AOTCacheOutput=app.aot -cp app.jar AotCacheDemo
```

JVM chạy training workload của ứng dụng và có thể khởi chạy **một JVM thứ hai** để tạo cache khi pha record kết thúc. Vì thế việc “một lệnh shell” **không đồng nghĩa một JVM process duy nhất** hoặc không tốn bộ nhớ bổ sung. Kết quả `app.aot` chỉ được xem là hợp lệ khi quá trình hoàn tất thành công.

Lần chạy reuse:

```bash
java -XX:AOTMode=on -XX:AOTCache=app.aot -cp app.jar AotCacheDemo
```

Đây là quy trình hai command đơn giản thích hợp cho lab/training trong build pipeline khi runtime hỗ trợ.

### Khi vẫn nên dùng ba pha?

- Muốn tách **training workload** với assembly job.
- Training container có CPU/memory thấp, nhưng assembly cần resources cao hơn.
- Muốn lưu/configure `.aotconfig` độc lập để kiểm tra/trace.
- Cần kiểm soát rõ build vs production artifacts.
- Muốn giảm rủi ro memory pressure do JVM assembly được launch cùng command.

**Đặc biệt trong container:** một số trường hợp JVM assembly dùng memory options tương đương training. Đừng chọn `-Xmx` sát giới hạn container rồi ngạc nhiên khi training + assembly bị OOM. Tách ba pha hoặc cấp memory budget hợp lý.

### JEP 515: lưu method profiles từ training

Từ JDK 25, AOT cache có thể lưu **method execution profiles** để JIT không phải chờ profile phát triển từ 0 trong các subsequent runs. Kết quả có thể là:

- Hot methods được biết sớm hơn.
- C1/C2 có thông tin type/branch/call activity từ training.
- Warm-up ổn định nhanh hơn trên workload phù hợp.
- Một số extra startup/warm-up CPU work được giảm hoặc chuyển thời điểm.

**Không đảm bảo mọi method hot đã được compile sẵn**; JIT vẫn phải chạy và thích nghi nếu production traffic differs. Dữ liệu profile không “khóa chặt” runtime type choices; HotSpot phải bảo toàn Java semantics qua guards/fallback/deoptimization nếu profile khác thực tế.

## 8. JDK 26: AOT object cache và các GC

Một hạn chế đáng chú ý ở mốc đầu của AOT cache là hỗ trợ **GC-specific AOT object caching**. Theo **JEP 516 (JDK 26)**, HotSpot mở rộng AOT object caching để có thể dùng với **các garbage collectors được hỗ trợ**, trong đó có ZGC, thay vì những giới hạn đã có ở JDK 24–25.

**Điều cần đọc cẩn thận:**

- Tính năng chính là cải thiện portability của **AOT object cache theo collector** trong phạm vi implementation; **không có nghĩa `.aot` của JDK 25 tự nhiên dùng được với JDK 26**.
- Cache vẫn gắn với **một JDK release, application và OS/CPU**; nâng JDK thì **regenerate**.
- Không vì JEP 516 mà suy mọi collector trong mọi vendor build và architecture đều được hỗ trợ.
- Nếu startup báo incompatibility, **đọc nguyên nhân**, đừng bật `IgnoreUnrecognizedVMOptions`.

### Bảng mốc cần nhớ

| JDK | Điểm AOT cache liên quan | Điều cần tránh suy diễn |
| --- | --- | --- |
| 17 | **Không có quy trình JEP 483 mới** | Không dùng `AOTMode`/`AOTCacheOutput` của JDK 24–25 |
| 24 | JEP 483, class loading/linking cache; record/create/on rõ ràng | Không có cờ `AOTCacheOutput` tiện lợi của JEP 514 |
| 25 | JEP 514 và JEP 515, CLI gọn + method profiles | Method profiles không có nghĩa cache đã chứa mọi native methods |
| 26 | JEP 516, AOT object caching with any GC trong phạm vi hỗ trợ | Cache của JDK khác **không** tự hợp lệ |
| Mới hơn | Xem docs/version và release notes chính xác | Không áp bảng cũ như một danh mục feature vĩnh viễn |

Thông tin ở đây gắn **mốc upstream OpenJDK/HotSpot**. Một distribution có thể có backports/patches; xác minh **binary thật** thay vì chỉ so version major bằng suy đoán.

## 9. Cache có phụ thuộc application và môi trường không?

**Có.** Oracle JDK `java` docs ghi AOT cache phụ thuộc các chiều trọng yếu:

- **Application identity**: classpath/JAR/module path và artifacts phù hợp.
- **JDK release/build**: thay runtime cần tái tạo cache.
- **OS/CPU architecture**: không copy cache giữa những nền tảng khác rồi mặc định chạy.
- **Những JVM options liên quan**: collectors, instrumentation/JVMTI, class loading/linking flags hoặc những options khác có thể không tương thích.
- **Training context**: classpath, class loaders, class initialization/linking behavior và environment phải hợp lệ khi production reuse.

### Checklist consistency

- [ ] Cùng JDK release và binary/runtime thích hợp.
- [ ] Cùng OS/CPU architecture/ABI theo tài liệu version.
- [ ] JAR/classpath artifacts không bị rebuild sau recording.
- [ ] File timestamps quan trọng được bảo toàn.
- [ ] Classpath dùng paths/JARs theo hướng dẫn release, tránh tùy tiện wildcard/directory/nested JARs.
- [ ] Runtime classpath có quan hệ tương thích với training classpath theo docs.
- [ ] Những Java agents/JVMTI class-file transformations không làm phá constraints.
- [ ] JDK options khi train/create/run không có incompatibility.
- [ ] Training cover những startup paths và methods sẽ được dùng thật.
- [ ] AOT cache được phát hành cùng application artifact, không tái dùng chéo builds.

**Đừng đọc checklist như cách bảo đảm 100% cache luôn hoạt động:** mỗi release có các ràng buộc chi tiết hơn; hãy thử mode strict và đọc logs.

### Classpath JAR thay đổi rất dễ làm cache stale

Đổi một transitive dependency, thêm plugin, thay manifest, đổi fat JAR layout hoặc repackaging khiến application identity khác. Một build pipeline tốt nên coi `app.aot` là **derived artifact** của **chính app.jar + JDK + target platform**, không phải một file cấu hình vĩnh viễn.

## 10. Training workload phải đại diện nhưng không gây side effect nguy hiểm

AOT cache học từ những class/method paths được exercise trong **training run**. Nếu training chỉ gọi `--version` hoặc in banner, cache có thể không cover:

- HTTP server startup.
- Serialization/deserialization code paths.
- JSON validation và route matching.
- Dependency injection wiring.
- ORM initializations.
- Hot request processing methods.
- Các branches phụ thuộc config/feature flags.

Nhưng cho training toàn bộ integration tests không chọn lọc cũng có thể làm cache lưu **classes của test frameworks**, tạo artifacts không liên quan production.

### Thiết kế training tốt

1. Xác định **mốc ready/startup** và workload hot nhất.
2. Giữ **classpath/JAR production**.
3. Mock database/external services khi cần, nhưng vẫn exercise những code paths tương tự.
4. Không phát sinh giao dịch nghiệp vụ thật hoặc gửi email/charge thẻ trong training.
5. Chạy smoke scenarios tiêu biểu; tránh cả “chỉ hello world” lẫn “stress test tất cả”.
6. Thu thông tin classes/methods đã đi qua.
7. Đóng ứng dụng và cho JVM hoàn thành cache creation thành công.
8. Dùng đúng cache trên staging rồi đo startup/warm-up dưới tải đại diện.
9. Regenerate khi application dependencies hoặc JDK thay đổi.

### Training không phải “đoán” toàn bộ production

Một ứng dụng có feature flags, dynamic class loading hoặc plugin ecosystem có thể dùng classes hoàn toàn mới tại production. AOT cache không bắt mọi class/method tương lai phải nằm trong cache; JVM vẫn có đường xử lý runtime hợp lệ cho những artifacts không cached khi điều kiện được hỗ trợ.

**Không biến class loading lúc runtime thành sai logic** chỉ vì training chưa từng cover nó. Kết quả có thể là **không hưởng lợi AOT** ở đường đó; nếu dynamic loading/JVMTI options phá consistency, startup strict mode có thể từ chối cache.

## 11. Kiểm chứng thực sự đang dùng AOT cache

**Output ứng dụng giống nhau** là điều bắt buộc về correctness, nhưng chưa đủ chứng minh cache được nạp.

Trên HotSpot với tính năng AOT logging hỗ trợ, thử:

```bash
java -XX:AOTMode=on -XX:AOTCache=app.aot -Xlog:aot,class+path=info -cp app.jar AotCacheDemo
```

Một số bản có thể báo những messages liên quan loaded/linked classes được reuse. **Đọc log của JVM thật**; không hard-code một mẫu stdout log cố định cho mọi build.

### Ba phép đối chiếu

| Run | Lệnh | Câu hỏi |
| --- | --- | --- |
| **No cache** | `java -XX:AOTMode=off -cp app.jar AotCacheDemo` | Baseline chạy không dùng AOT artifacts |
| **Cache, fail-fast** | `java -XX:AOTMode=on -XX:AOTCache=app.aot -cp app.jar AotCacheDemo` | Cache hợp lệ và load được? |
| **Cache, logging** | `java -XX:AOTMode=on -XX:AOTCache=app.aot -Xlog:aot,class+path=info -cp app.jar AotCacheDemo` | Có evidence JVM reuse artifacts? |

`-XX:AOTMode=on` hữu ích khi cần strict startup failure nếu cache thiếu/incompatible, thay vì để default automatic behavior có thể chuyển sang chạy không cache. Log/option syntax phải được kiểm tra trên đúng release.

### Debug khi log không nói rõ

- Dùng `java -version` xác nhận đúng JDK, VM name.
- Dùng `java -Xlog:help` để xem tags của chính VM.
- Xem errors/warnings khi tạo cache.
- Kiểm tra tồn tại, quyền đọc và kích thước file `.aot`.
- Kiểm tra cache format/magic bằng công cụ được vendor hỗ trợ; **không chỉnh binary thủ công**.
- Đảm bảo training/create/production dùng đúng app JAR/dependencies.
- Không để build pipeline “tự bỏ AOT flags nếu lỗi” rồi gắn nhãn run là “cache-enabled”.

## 12. So sánh startup/warm-up cho công bằng

AOT thường được kỳ vọng giảm startup overhead, nhưng phép đo dễ nhiễu. Để so sánh:

- **Cùng** JDK vendor/build, CPU/memory quota, GC, container image.
- **Cùng** JAR/app arguments, classpath, config và external dependencies.
- Chọn **no-cache baseline** bằng `AOTMode=off` thay vì dùng JDK version khác.
- Chạy **cache-enabled** với `AOTMode=on` xác nhận hợp lệ.
- Định nghĩa metric: JVM process launch → app ready, hoặc first useful request.
- Đo **nhiều cold process launches**. Tránh so một lần warm file-system cache với một lần cold disk cache.
- Giữ JIT warm-up và startup work tương đương.
- Tách **elapsed startup**, **memory footprint**, **warm-up CPU** và **steady-state throughput**.
- Báo median/percentiles và độ phân tán, không chỉ lần tốt nhất.

### Không báo kết quả đo phỏng đoán

Một vài benchmark chính thức của các nhóm OpenJDK/Oracle có thể thể hiện mức cải thiện đáng kể trên workload cụ thể. **Không thể áp con số đó trực tiếp** cho AotCacheDemo hoặc một web service bất kỳ.

Ví dụ báo cáo chuẩn:

```text
Runtime: HotSpot JDK <version + build đã đo>
Application artifact: app.jar <digest đã xác minh>
No-cache command: ...
AOT-cache command: ...
Run count: <số runs thực>
Ready-time median A/B: <số liệu đo>
p95 startup A/B: <số liệu đo>
CPU / RSS / heap A/B: <số liệu đo>
Compiler/JFR differences: <observed evidence>
Conclusion: chỉ giới hạn trong môi trường/workload đã đo
```

Đây là **mẫu phải điền bằng số đo thực**, không phải kết quả cố định. Không đưa các trường mô tả này vào stdout kỳ vọng của chương trình Java.

## 13. AOT cache khác CDS, AppCDS và Dynamic CDS như thế nào?

**Class Data Sharing (CDS)** tồn tại trước AOT cache của JEP 483 và giúp reuse class metadata đã lưu qua archive. Ví dụ HotSpot có các flags lịch sử:

```text
-Xshare:on
-XX:SharedArchiveFile=archive.jsa
-XX:ArchiveClassesAtExit=archive.jsa
```

Đây là **ví dụ lựa chọn CDS của HotSpot theo phiên bản hỗ trợ**, không phải lệnh tạo JEP 483 AOT cache. File `.jsa` và `.aot` có workflow/semantics khác theo release.

| Cơ chế | Mục tiêu chính | Phân biệt quan trọng |
| --- | --- | --- |
| CDS/AppCDS | Chia sẻ một phần class metadata/archive để giảm startup/memory | Có thể dùng trên HotSpot trước JDK 24 |
| Dynamic CDS archive | Tạo archive classes trong những cách chạy hỗ trợ | Không đồng nhất `.jsa` với `.aot` |
| JEP 483 AOT cache | Framework mới reuse load/link classes/selected objects | Có training/config/create phases |
| JEP 515 method profiling | Tái dùng execution profiles từ training | Đưa dữ liệu cho JIT; không phải native executable |
| GraalVM Native Image | Build executable native với runtime đặc thù | Không phải `java -XX:AOTCache=...` của HotSpot |

**JDK 17:** có thể học CDS và performance tuning cổ điển, nhưng không đặt tên nhầm cơ chế đó thành **“JEP 483 AOT cache”**. Muốn thực nghiệm tính năng của mục này, chuẩn bị đúng HotSpot JDK 24+.

## 14. AOT cache không đồng nghĩa ahead-of-time native compilation cũ

Trước JEP 483, HotSpot có những thí nghiệm AOT compilation khác. **JEP 295** giới thiệu experimental ahead-of-time compilation (`jaotc`), rồi **JEP 410** loại bỏ AOT compiler experimental và `jaotc` khỏi JDK 17.

Những mốc này thường bị nhập nhằng:

- **JEP 295/410:** liên quan **experimental AOT compiler/jaotc** đã bị loại khỏi upstream JDK 17.
- **JEP 483:** AOT cache class loading/linking được giới thiệu ở JDK 24.
- **JEP 515:** bổ sung method profile caching từ JDK 25.
- **GraalVM Native Image:** hệ thống native compilation khác, có builder và runtime khác.

Vì vậy câu “JDK 17 đã bỏ AOT, nên Java 25 không còn AOT cache” là **sai do nhầm hai tính năng khác nhau**. Ngược lại, “Java 25 có AOT cache nên `jaotc` đã trở lại” cũng không đúng.

## 15. Startup optimizations không làm thay đổi luật class initialization

AOT class linking không được phép tự ý thay observable Java semantics về:

- Class initialization khi active use yêu cầu.
- Thứ tự `<clinit>` phù hợp.
- Exceptions từ static initializer.
- Runtime/linkage errors.
- Thread synchronization của class initialization.
- Reflection/dynamic loading theo những điều kiện được hỗ trợ.

Ví dụ:

```java
final class InitDemo {
    static {
        System.out.println("class initialization");
    }

    static void run() {
        System.out.println("run");
    }
}
```

Đây là class snippet, **chưa có `main`**. Tối ưu AOT không có quyền in chuỗi “class initialization” ở một thời điểm tùy ý làm thay đổi quan sát bắt buộc của Java code. Việc chuẩn bị artifact trước thời gian chạy chỉ được thực hiện trong những ranh giới compatibility mà HotSpot đảm bảo.

### Phân biệt load/link với initialize

Một class có thể được **load/link** trước khi thực sự **initialize**. AOT cache giúp chuẩn bị những phần công việc phù hợp nhưng không được tự đồng nhất “đã ở cache” với “static initializers đã chạy cho production process”.

**Đừng dùng AOT cache để né bugs trong static initializer.** Nếu một class khởi tạo sai/lỗi trong application, cache không làm lỗi logic trở nên hợp lệ.

## 16. Dynamic classes, agents và instrumentation

Một số ứng dụng load classes hoặc thay class bytes theo runtime:

- Java agents/bytecode instrumentation.
- Application server class loaders.
- Dependency injection proxies.
- Dynamic proxies / hidden classes.
- Hot-reload/redefinition tools.
- Custom class loaders.
- Plugin frameworks.

Điều đó không có nghĩa tất cả ứng dụng như trên không thể hưởng AOT. Nhưng **một số JVMTI operations**, đặc biệt agent thay bootstrap/system classloader search path, có thể không tương thích với cache đã link trước.

### Cần báo gì khi có agent?

1. Agent nào chạy trong training và production?
2. Có transform class bytes không?
3. Có add vào bootstrap/system class loader search path không?
4. Agent version/options có thay đổi?
5. `AOTMode=on` có chấp nhận config này không?
6. Những classes dynamic có được exercise và reuse không?
7. Nếu cache bị từ chối, có thể tắt optimization hoặc thay training/config theo docs mà vẫn giữ correctness không?

**Không** giải quyết bằng việc bắt buộc tắt monitoring/security agents ở production nếu chưa đánh giá yêu cầu vận hành. Hiệu năng tối ưu phải phù hợp instrumentation và bảo mật thực tế.

## 17. Triệu chứng và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `Unrecognized VM option 'AOTMode'` | JDK quá cũ hoặc JVM khác HotSpot | `java -version`, release/build docs |
| `AOTCacheOutput` không nhận ở JDK 24 | JEP 514 là JDK 25 feature | Dùng record/create ở JDK 24 |
| `app.aot` không tồn tại | Training/assembly chưa hoàn tất, sai path/permission | Exit code, filenames, logs |
| Cache không load ở mode `on` | JDK/app/OS/CPU/flags không tương thích | Đọc error details, so artifacts |
| Chạy được nhưng không nhanh hơn | Training shallow, app quá nhỏ hoặc bottleneck không nằm ở load/link/profile | JFR/class logs và benchmark nhiều lần |
| Cùng tên JAR nhưng cache stale | JAR rebuilt, dependency đổi, timestamps/bytes khác | File digests và build pipeline |
| AOT assembly OOM | JVM thứ hai tiêu thụ memory, container quota thấp | Memory limit, tách pha |
| Chạy AOT trên ZGC JDK 25 gặp giới hạn | JEP 516 xuất hiện từ JDK 26 | Kiểm tra release và collector support |
| App output khác khi dùng cache | Vấn đề correctness/config hoặc ứng dụng có non-determinism | Reproduce, so flags/config, báo bug nếu cần |
| `-Xlog:aot` không tạo event mong đợi | Tag/level khác, cache không reuse, logging config | `-Xlog:help`, startup flags, strict mode |
| First request vẫn chậm | DB/network/framework init không cover, JIT còn warm-up | Request tracing/JFR, profile training |
| RAM/RSS tăng | Cache mapping/assembly overhead, config/bộ nhớ runtime | OS metrics, NMT, compare same windows |

### Lỗi không phải luôn “JVM không hỗ trợ”

Một flag **được nhận diện** nhưng VM từ chối vì **class path mismatch** khác với flag **không được build vào JVM**. Ghi đúng error, phân loại **availability vs compatibility vs effectiveness** trước khi chọn cách xử lý.

### Mode auto và sự im lặng nguy hiểm

`AOTMode=auto` có thể chạy ứng dụng mà **không dùng cache** nếu một cache không được nạp trong những trường hợp được phép. Trong CI/benchmark muốn chứng minh cache hoạt động, hãy dùng mode **on** và đọc logs. **Không kết luận “có `-XX:AOTCache=...` trên command line thì cache chắc chắn đã được dùng”.**

## 18. Lỗi vận hành khi đóng gói cache

### Không gắn `.aot` vào container image khác build

Một cache tạo với JDK build A rồi copy vào image B có JDK khác có thể không còn hợp lệ. Cách đúng: xây **application artifact + AOT cache** theo target release/platform cụ thể, lưu manifest metadata và phát hành chúng có version cùng nhau.

### Không sửa JAR sau training

Dù chỉ thay timestamp hoặc repackage, JVM có thể coi classpath artifacts không khớp. Trong release pipeline:

```text
Compile source
    ↓
Package immutable app.jar
    ↓
Train → assemble app.aot (same immutable app.jar)
    ↓
Validate strict AOT on staging
    ↓
Publish app.jar + app.aot + manifest
    ↓
Deploy both with matching JDK runtime image
```

**Mỗi lần build source/dependencies/JDK** nên regenerate cache. Nếu target có nhiều OS/CPU architectures, tạo/kiểm tra artifacts phù hợp từng target, thay vì suy `app.aot` là binary portable.

### AOT cache là artifact phải bảo vệ

File cache chứa thông tin về classes/metadata/runtime artifacts, không mặc nhiên là public. Cần file permissions, checksum/digest, provenance, artifact signing/policy khi tổ chức yêu cầu và kiểm soát người có quyền thay nó.

Không upload `.aot` hoặc training logs chứa nội dung nhạy cảm lên kho công khai chỉ để debug. Khi logging/cache config có user information, áp dụng retention/security policy tương ứng.

## 19. Training trong test vs production

### Training bằng integration/smoke tests

Ưu điểm:

- Có thể thực hiện trong CI không truy cập production database.
- Dễ lặp lại, ghi artifact và đặt quality gates.
- Có thể test một số startup/request paths đại diện.

Giới hạn:

- Test-only classes làm cache to mà không giúp production.
- Mocked paths không cover actual production hot methods.
- Synthetic traffic khác phân bố receiver types/requests.
- Một số integrations khó tái tạo đúng cách.

### Training dưới production-like workload

Ưu điểm:

- Có thể quan sát class/method paths sát thực tế.
- Phù hợp ứng dụng có dynamic initialization.

Giới hạn:

- Có nguy cơ business side effects và tài nguyên nhạy cảm.
- Khó cố định classpath/environment trong rolling deployment.
- Cache output phải được chuyển sang build/deploy flow an toàn.
- Time windows có thể bỏ sót hot paths của những thời điểm khác.

**Khuyến nghị:** ưu tiên isolated, repeatable training phản ánh production; nếu chỉ training ở production thì cần policy chặt chẽ về side effects, dữ liệu, bảo mật và artifact promotion. Không nên nghĩ training là “cứ chạy app một lần bất kỳ”.

## 20. Thí nghiệm A/B: cache là biến duy nhất

Một thí nghiệm đúng nên so:

**A — no cache:**

```bash
java -XX:AOTMode=off -cp app.jar AotCacheDemo
```

**B — strict AOT cache:**

```bash
java -XX:AOTMode=on -XX:AOTCache=app.aot -cp app.jar AotCacheDemo
```

Cả hai command dùng **cùng JDK**, app JAR, OS/CPU, GC/heap, input và môi trường. Trong ví dụ nhỏ này, **stdout phải giống** ở cả A và B nếu được hỗ trợ.

### Thu số liệu có ý nghĩa

- Process elapsed startup tới dòng `ready: true`, nếu dùng marker đó làm proxy.
- Thời gian tới first request ready trong ứng dụng server thực.
- CPU của compiler/class loading trong warm-up.
- Number of class loads, JFR events, compilation events.
- Heap committed/used, process RSS, memory maps của cache.
- Number of runs, median/p95 và variability.
- Error rates và correctness output.
- Cache artifact size vs savings.

**Không dùng một lần chạy** với `time java ...` để tuyên bố “AOT giúp giảm 40% startup”; filesystem cache, OS scheduler, JIT, entropy và process launch overhead đều thay đổi.

### Hiệu năng có thể tốt hơn ở metric này và xấu ở metric khác

Caching có thể cải thiện startup nhưng tăng storage footprint hoặc memory mapping overhead. Cache assembly cũng tiêu thụ CPU/RAM trong build stage. Nếu application chạy lâu liên tục, lợi ích startup có thể không phải KPI chính.

**Sự lựa chọn phụ thuộc use case:** batch jobs, CLI, serverless cold start và autoscaled services thường quan tâm startup; hệ thống uptime nhiều tháng có thể coi steady-state throughput/latency quan trọng hơn.

## 21. Kinh nghiệm gỡ lỗi từ output chương trình

Cần chia ít nhất ba loại output:

1. **Java application stdout:** các dòng `application`, `checksum`, `ready`; trong demo chúng có expected values cố định.
2. **JVM AOT/GC/class loading logs:** format/time/files thay đổi theo JDK và flags; **không viết expected stdout cố định** cho chúng.
3. **Timing/benchmark metrics:** thuộc môi trường đo; không phải hợp đồng ngôn ngữ Java.

Một báo cáo đúng có thể viết:

```text
Functional QA: PASS
  application=AotCacheDemo
  checksum=134000
  ready=true

AOT startup validation: PASS/FAIL theo strict mode + log thực tế
  JVM vendor/version/build: ghi từ máy thật
  AOT cache path/digest: ghi từ build thật
  Classpath/JAR digest: ghi từ build thật

Startup performance:
  Runs A/B: số đo thực
  Median, p95, variation: số đo thực
  Kết luận: giới hạn trong workload/target đo
```

**Đây là biểu mẫu ghi thực nghiệm, không phải một báo cáo kết quả thực tế đã đo**. Mỗi trạng thái cần có log/evidence cụ thể nếu đem dùng để quyết định rollout.

## 22. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “AOT cache của HotSpot đã có trên Java 17.” | JEP 483 bắt đầu từ JDK 24 upstream |
| “Có `jaotc` trên JDK 25 vì có AOT cache.” | `jaotc` experimental đã removed từ JDK 17 |
| “AOT cache nghĩa toàn bộ app thành native executable.” | `.aot` là artifacts cho HotSpot JVM, không phải executable |
| “JEP 515 đóng gói tất cả compiled C2 methods.” | Method profiles được reuse để JIT tối ưu sớm |
| “Training chỉ cần `java -version`.” | Training phải chạy code paths ứng dụng thật |
| “Ứng dụng thay build vẫn dùng cache cũ.” | Regenerate theo application/JDK/platform constraints |
| “`AOTMode=auto` luôn đảm bảo cache được nạp.” | Có trường hợp VM chạy mà không sử dụng cache |
| “`AOTCacheOutput` dùng được trên JDK 24.” | Cờ tiện lợi này từ JDK 25 |
| “Cache của JDK 25 dùng trực tiếp trên JDK 26.” | Cache release-specific, phải tạo lại |
| “Dùng cache là bỏ qua static initialization.” | Java class-init semantics vẫn được bảo toàn |
| “Cache chứa mọi runtime object và secrets của ứng dụng.” | Chỉ có artifacts JVM cho phép cache |
| “JVM đổi GC nhưng cache luôn tương thích.” | Khả năng tùy JDK/GC và options; JEP 516 mở rộng JDK 26 |
| “JAR chỉ cần cùng filename.” | Artifact contents/timestamps/classpath consistency cần đối chiếu |
| “JVM in checksum đúng là chứng minh cache load.” | Phải dùng strict mode/logs |
| “Training càng nhiều test frameworks càng tốt.” | Thêm unused classes có thể làm cache phình to |
| “AOT chắc chắn tăng throughput sau warm-up.” | Chủ yếu hướng startup/warm-up, phải đo |
| “Một `.aot` dùng cho Windows/Linux/ARM như nhau.” | Không, cache platform-specific |
| “Lỗi không có AOT file nghĩa Java code sai.” | Có thể output path/permission/assembly failed |
| “Làm một lệnh output không tốn bộ nhớ phụ.” | JDK 25 có thể khởi chạy JVM assembly khác |
| “Cứ bật flags AOT trên OpenJ9 là được.” | HotSpot-specific; xác minh implementation |
| “Có Java agent đồng nghĩa luôn dùng AOT được.” | Một số JVMTI classloader changes không tương thích |
| “CDS `.jsa` và JEP 483 `.aot` là cùng file format.” | Khác mechanism/workflow theo release |

## 23. Bài tập tự kiểm tra

**Bài 1.** JDK mốc nào có AOT cache class loading/linking theo JEP 483?  
**Đáp án:** **JDK 24**.

**Bài 2.** JDK 25 bổ sung gì cho AOT?  
**Đáp án:** JEP 514 (ergonomic `AOTCacheOutput`) và JEP 515 (method profiling).

**Bài 3.** JDK 26 có cải thiện nào liên quan GC?  
**Đáp án:** JEP 516 mở rộng AOT object caching với những GCs hỗ trợ, trong đó có ZGC.

**Bài 4.** Vì sao JDK 17 `-XX:AOTMode=record` có thể lỗi?  
**Đáp án:** JEP 483 chưa có ở JDK 17 thông dụng; flags mới không được nhận diện.

**Bài 5.** Ba pha AOT gồm gì?  
**Đáp án:** Training/record → assembly/create → production/on.

**Bài 6.** Khi mode `create` chạy, có cần chạy lại `main` ứng dụng để tính checksum không?  
**Đáp án:** Không. Assembly đọc configuration và tạo cache; application main không được chạy trong pha này.

**Bài 7.** `AOTCacheOutput` khác record/create tường minh thế nào?  
**Đáp án:** Từ JDK 25, JVM làm record và assemble thuận tiện từ một invocation, có thể dùng JVM phụ để assemble.

**Bài 8.** Cache JDK 25 còn dùng được sau khi upgrade sang JDK 26?  
**Đáp án:** Không mặc định; phải regenerate cho JDK release/build và environment mới.

**Bài 9.** Training chỉ chạm một endpoint, production có mười endpoints. Có thể có giới hạn gì?  
**Đáp án:** Classes/method profiles chưa cover những paths còn lại, làm benefits AOT kém.

**Bài 10.** Cache có thay đổi `static` initializer observable Java semantics không?  
**Đáp án:** Không được; HotSpot phải giữ class loading/linking/initialization rules hợp lệ.

**Bài 11.** AOT cache là một native executable dùng thay `java`?  
**Đáp án:** Không. Đây là cache cho JVM, khác GraalVM Native Image.

**Bài 12.** JDK 25 có profile AOT thì JIT vẫn chạy sau startup không?  
**Đáp án:** Có. Cache profiles giúp JIT ra quyết định sớm, không đảm bảo có sẵn mọi native code.

**Bài 13.** AotCacheDemo in checksum bao nhiêu?  
**Đáp án:** **134000**, tổng 110000 từ AddOne và 24000 từ Twice.

**Bài 14.** Muốn fail-fast khi cache bị thiếu, dùng gì?  
**Đáp án:** `-XX:AOTMode=on` kết hợp đường dẫn `-XX:AOTCache=...` trên JVM hỗ trợ, rồi xem startup exit/log.

**Bài 15.** Cùng JAR filename nhưng rebuild dependency, có nên giữ `.aot`?  
**Đáp án:** Không; regenerate, đừng chỉ so filename.

**Bài 16.** Cache được tạo trên x86-64 Linux dùng trực tiếp trên AArch64 Windows?  
**Đáp án:** Không mặc định; OS/CPU khác khiến cache không tương thích.

**Bài 17.** Có Java agent thay classloading paths, phải làm gì?  
**Đáp án:** Xác minh JVMTI constraints và strict startup trên build/agent config thực.

**Bài 18.** Bật cache nhưng p99 không giảm; có lỗi không?  
**Đáp án:** Chưa kết luận. AOT hướng startup/warm-up; p99 có thể bị DB/I/O/locks/GC chi phối.

**Bài 19.** Chạy `java -Xlog:aot,class+path=info` có chứng minh toàn bộ cache đúng không?  
**Đáp án:** Chỉ giúp quan sát events; cần kết hợp strict mode, matching artifacts, successful startup và đo.

**Bài 20.** Vì sao không dùng `-XX:+IgnoreUnrecognizedVMOptions` để “bảo đảm deploy luôn chạy”?  
**Đáp án:** Có thể lặng lẽ bỏ AOT flag; service chạy nhưng benchmark/operational expectation sai.

**Bài 21.** Training load cả test framework có lợi không?  
**Đáp án:** Không nhất thiết; có thể tăng unused classes/cache size, giảm hiệu quả.

**Bài 22.** Có thể copy cache từ staging lên production?  
**Đáp án:** Chỉ khi application, JDK, OS/CPU và compatibility constraints khớp, artifact được quản lý an toàn và strict verification pass.

**Bài 23.** Cache cũ gặp lỗi, có nên tự sửa bytes `.aot` bằng hex editor?  
**Đáp án:** Không. Đây là VM-derived binary artifact; phải tìm nguyên nhân và regenerate đúng build.

**Bài 24.** Benchmark startup muốn quy lợi ích AOT, nên so điều gì?  
**Đáp án:** Cùng JDK/app/workload/heap/CPU nhưng `AOTMode=off` vs `AOTMode=on`, nhiều cold-process runs và log xác minh cache.

## 24. Checklist thực hành cuối bài

- [ ] Đã dùng **HotSpot JDK 24+** phù hợp, không nhầm JDK 17?
- [ ] Đã biết chính xác release hỗ trợ **JEP 483 / 514 / 515 / 516** nào?
- [ ] Đã compile Java code và tạo JAR chứa đầy đủ classes?
- [ ] Đã kiểm tra `jar --list --file app.jar` trước training?
- [ ] Đã lưu app JAR bất biến giữa record, create và run?
- [ ] Training đã exercise representative startup/hot paths?
- [ ] Không thực thi real business side effects trong training?
- [ ] `.aotconfig`/`.aot` được ghi hoàn tất, có quyền đọc/ghi và đủ disk?
- [ ] Khi dùng `AOTCacheOutput` đã dự trù memory cho assembly JVM?
- [ ] Production test dùng `AOTMode=on` để phát hiện cache mismatch rõ?
- [ ] Đã xem `-Xlog:aot,class+path=info` và `java -Xlog:help` đúng release?
- [ ] Đã xác minh application output giữ đúng nghĩa khi có/không cache?
- [ ] Đã không copy cache qua OS/CPU/JDK release khác?
- [ ] Đã kiểm tra agent/JVMTI/classpath/GC constraints?
- [ ] Đã regenerate cache nếu source/dependencies/JDK thay đổi?
- [ ] Đã đo startup/warm-up A/B nhiều lần với cùng CPU/heap/GC?
- [ ] Đã báo giới hạn và công việc chưa cover trong training?
- [ ] Đã quản lý provenance, digest và bảo mật file cache?
- [ ] Đã tách AOT cache của JEP 483 khỏi CDS `.jsa`, `jaotc` và GraalVM Native Image?

## 25. Kết luận

**AOT cache HotSpot là cơ chế học và reuse, không phải phép màu biên dịch Java toàn bộ thành native binary.** Từ JDK 24, JVM có thể quan sát một training run, xây các artifacts về loading/linking rồi dùng lại khi startup. JDK 25 làm quy trình thuận tiện hơn và thêm method profiles để JIT warm-up sớm. JDK 26 mở rộng sự hỗ trợ của object caching theo GC.

Muốn vận hành đúng:

```text
Immutable application artifact + đúng HotSpot release
              │
              ▼
Representative training run
              │
              ▼
AOT configuration / cache assembly
              │
              ▼
Strict cache validation trên target
              │
              ▼
Production startup sử dụng cache được xác minh
              │
              ▼
A/B benchmark startup + warm-up + memory
              │
              ▼
Regenerate cache ở mỗi build/JDK/OS/CPU thay đổi
```

**Tập trung vào điều có thể chứng minh:** đúng chức năng ứng dụng, file cache được tạo thành công, HotSpot thực sự nạp nó, và kết quả startup/warm-up được đo trong môi trường đại diện. Không hứa một mức tăng tốc cố định, không bỏ qua consistency constraints, và không dùng flags của JDK mới ở runtime chưa hỗ trợ.

### Tài liệu gốc

1. **OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking (JDK 24):** https://openjdk.org/jeps/483
2. **OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics (JDK 25):** https://openjdk.org/jeps/514
3. **OpenJDK JEP 515 — Ahead-of-Time Method Profiling (JDK 25):** https://openjdk.org/jeps/515
4. **OpenJDK JEP 516 — Ahead-of-Time Object Caching with Any GC (JDK 26):** https://openjdk.org/jeps/516
5. **Oracle JDK 24 — `java` command và AOT cache options:** https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
6. **Oracle JDK 25 — `java` command, `AOTCacheOutput`, `AOTMode`:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
7. **Oracle JDK 26 — `java` command, AOT cache mode/compatibility:** https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html
8. **Inside Java (Oracle, 2026) — Run Into the New Year with Java’s AOT Cache Optimizations:** https://inside.java/2026/01/09/run-aot-cache/
9. **OpenJDK JEP 410 — Remove the Experimental AOT and JIT Compiler:** https://openjdk.org/jeps/410
10. **OpenJDK Project Leyden:** https://openjdk.org/projects/leyden/

**Ghi nhớ:** cấu hình được đánh giá đúng khi ghi rõ **JDK version + application digest + OS/CPU + training coverage + strict AOT reuse evidence + A/B metrics**, chứ không chỉ vì có một file tên `app.aot` nằm trên đĩa.
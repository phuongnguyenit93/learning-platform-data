# Class Data Sharing (CDS) chia sẻ dữ liệu lớp như thế nào?

## 1. CDS là gì và giải quyết vấn đề nào?

**Class Data Sharing (CDS)** là một cơ chế của **HotSpot JVM** cho phép JVM chuẩn bị và lưu **một phần dữ liệu metadata của các lớp Java** vào một tệp archive, thường có phần mở rộng **`.jsa`**. Khi JVM khác được khởi chạy với điều kiện tương thích, nó có thể **memory-map** archive này vào không gian địa chỉ tiến trình và sử dụng biểu diễn lớp đã lưu thay vì phải làm lại toàn bộ một số bước tải, phân tích, kiểm tra và tạo metadata từ bytecode/JAR.

Mục tiêu chính:

- **Giảm startup time**, đặc biệt phần chi phí class loading và linking đối với lớp đã được archive.
- **Giảm memory footprint tổng** khi nhiều JVM processes sử dụng cùng archive: các trang nhớ chỉ đọc có thể cùng trỏ tới những physical pages do hệ điều hành quản lý.
- **Giảm công việc khởi tạo biểu diễn class**, đặc biệt với nhiều classes thường được dùng đi dùng lại.

CDS **không phải** cơ chế chia sẻ Java heap thông thường giữa hai chương trình Java; **không phải** làm sẵn mọi static initializer; **không phải** JIT/AOT compile toàn bộ chương trình thành machine code; cũng **không phải** bộ nhớ đệm tự động cho database, HTTP hay state nghiệp vụ.

### Một sơ đồ ý nghĩa

```text
                Khi chuẩn bị archive
.class/JAR/runtime classes
          |
          v
  HotSpot xác định các lớp được archive
          |
          v
     CDS archive (.jsa)
     metadata ở dạng dùng lại
          |
          +------------------------------+
          |                              |
          v                              v
     JVM process A                   JVM process B
  map cùng archive                 map cùng archive
     |                              |
     +-- shared read-only pages -----+
     |                              |
     +-- private / COW state         +-- private / COW state
     +-- Java heap A riêng           +-- Java heap B riêng
     +-- static state A riêng         +-- static state B riêng
     +-- JIT/code cache A riêng      +-- JIT/code cache B riêng
```

**Ý chính:** *Chia sẻ dữ liệu lớp* là chia sẻ các biểu diễn metadata phù hợp **qua các mapping của hệ điều hành**; không phải cho hai ứng dụng quyền sửa cùng một object tùy ý.

### Câu hỏi bài học trả lời

1. Archive chứa những loại dữ liệu gì và vì sao có thể đọc nhanh hơn JAR?
2. Dữ liệu nào thực sự được **share**, dữ liệu nào vẫn **private**?
3. Default CDS, AppCDS, static base archive và dynamic top archive khác nhau ra sao?
4. `-Xshare:auto`, `-Xshare:off`, `-Xshare:on` vận hành thế nào?
5. Làm sao tạo và dùng archive bằng JDK 17?
6. Làm sao chứng minh lớp ứng dụng được lấy từ archive chứ không phải JAR?
7. Vì sao CDS không bỏ `<clinit>`, JIT warm-up, class loaders và Java semantics?
8. Khi nào archive không dùng được và cần thiết kế fallback/thí nghiệm thế nào?

## 2. Class loading truyền thống tốn công việc gì?

Nếu một class chưa được nạp vào runtime, đường xử lý có thể liên quan:

1. Class loader định vị nguồn bytecode thích hợp.
2. Đọc các bytes của class từ runtime image, JAR, filesystem hoặc nguồn tùy biến.
3. Parse class file/constant pool và xây dựng những metadata cần thiết.
4. Verification các constraints, preparation static fields.
5. Resolution symbolic references khi cần.
6. Initialization ở lần active use thích hợp, theo JLS §12.4.
7. Trong quá trình thực thi, profiling/JIT compilation có thể phát sinh riêng.

```text
No suitable CDS archive:
   class path / module image / JAR bytes
                  |
           locate + read
                  |
             class parsing
                  |
          verify / metadata setup
                  |
         link + runtime class state
                  |
         initialize when required
```

Không có công thức “mỗi class tốn đúng X microseconds”. Chi phí thay đổi theo class size, loader behavior, file cache, JVM build, agents, classpath scanning, resolution và những hoạt động runtime khác.

### CDS tiết kiệm điều gì?

Archive lưu **dữ liệu lớp đã được chuẩn bị theo định dạng HotSpot có thể tái sử dụng**. Khi những điều kiện hợp lệ, JVM có thể **map và khai thác metadata này**, tránh lặp lại một phần việc tìm, đọc, phân tích và tổ chức class metadata từ JAR cho các lớp có trong archive.

Đây không phải lệnh “bỏ qua mọi bước verification/security checks trên mọi lớp”; HotSpot vẫn phải đảm bảo class identity, cấu hình loader, compatibility và Java semantics đúng.

**Lợi ích đến từ việc tái dùng phần việc đã được thực hiện**, không phải thay đổi kết quả của chương trình.

## 3. Archive CDS lưu những gì?

Trong HotSpot, **class metadata** đại diện cho thông tin mà VM cần để thực thi class/interface, có thể gồm:

- Thông tin cấu trúc class, superclass/interfaces.
- Method và field descriptors, constant-pool information.
- Metadata đã parse/link/preprocess phù hợp định dạng archive.
- Những runtime data structures đủ điều kiện để archive theo HotSpot/JDK release.
- Trong một số cấu hình, **archived heap objects** chuyên biệt như một số String objects/constant data đã được VM chuẩn bị phù hợp.

Không suy rằng “CDS copy nguyên toàn bộ object graph của ứng dụng vào archive”. Các shared contents và representation thay đổi theo JDK/collector/platform. **HotSpot implementation** quyết định chính xác dữ liệu nào được archive, phiên bản metadata nào phải tái tạo hoặc relocate.

### 3.1. Metadata khác Java object instance

```java
class Customer {
    long id;
    String name;
}
```

Đây là class snippet, chưa phải chương trình chạy độc lập.

Archive có thể hỗ trợ **metadata mô tả `Customer`** nếu lớp được archive. Khi mỗi tiến trình chạy `new Customer()`, chúng **không cùng nhận một object Java dùng chung**, không dùng chung value của `id` và không chia sẻ một biến `name` mutable giữa các JVM.

```text
Shared idea:
  class shape / metadata for Customer
Per JVM:
  new Customer() object allocations
  instance fields (id, name)
  application data and state
```

### 3.2. “Archive classes” không phải archive source code

CDS không lưu lại source Java (`.java`) để biên dịch. Nó lưu runtime-friendly representations dựa trên classes đã biết. JVM vẫn phải tuân theo class loading/security/initialization rules và có thể phải fallback sang class files thông thường khi archive không dùng được.

### 3.3. Archive có thể lớn hơn class files

Theo tài liệu **Oracle JDK 17 Application Class Data Sharing**, biểu diễn lớp trong archive có thể tốn nhiều dung lượng đĩa hơn class bytes trong JAR/runtime image (tài liệu nêu khoảng 2–5 lần tùy lớp). Lý do là định dạng được tối ưu cho tái dùng nhanh, không chỉ nén file tối đa.

Do vậy **đừng archive mọi class của mọi library theo mặc định**. Chỉ nên chứa các classes thực tế hay được ứng dụng sử dụng, trừ khi profile và chính sách triển khai cho thấy cần phạm vi khác.

## 4. “Sharing” diễn ra ở tầng hệ điều hành: memory mapping

Điểm cốt lõi không nằm ở một singleton Java toàn cục, mà ở **memory-mapped files** của OS.

Tại runtime:

1. JVM mở archive tương thích.
2. Các vùng của archive được map vào **virtual address space** của process.
3. Nhiều JVM processes có thể map cùng file/physical file-cache pages.
4. Những pages **read-only** có thể được dùng chung vật lý.
5. Những vùng cần ghi có thể dùng **copy-on-write (COW)** hoặc được cung cấp dưới dạng private data thích hợp.

```text
File on disk: cds-demo.jsa
        |
        v
Operating-system page cache / mapped file pages
        |
        +--------------------------+
        |                          |
       JVM A                      JVM B
 virtual address A             virtual address B
        |                          |
        +---- shared RO pages -----+
        |                          |
    private RW/COW pages       private RW/COW pages
        |                          |
     Heap A                       Heap B
```

### 4.1. Virtual address giống nhau không phải điều kiện bắt buộc

JVM có thể map archive tại những virtual addresses phù hợp và xử lý relocation/pointer adjustments theo HotSpot/JDK requirements. Không được suy các processes phải có cùng absolute pointer addresses để dùng chung file pages.

### 4.2. Copy-on-write nghĩa gì?

Một file-backed page có thể **được share khi chưa bị thay đổi**; khi một process cần ghi vào một mapped page theo cơ chế COW, OS cung cấp một private page cho thay đổi đó. JVM còn có các vùng private state riêng không đặt trong shared archive pages.

**Không suy “mọi vùng archive vĩnh viễn read-only”**, vì các logs HotSpot có thể cho thấy archive regions có labels `ReadOnly` và `ReadWrite`. Những trang được dùng chung thực tế tùy OS mapping, memory page modifications và implementation.

### 4.3. Shared physical memory giúp lúc nào?

Nếu nhiều Java processes cùng dùng cùng JDK/CDS archive và những pages được map/chia sẻ, tổng **physical memory consumption** có thể thấp hơn so với mỗi process tự lưu những bản metadata riêng.

Tuy nhiên:

- Mỗi JVM vẫn có private Java heap, threads, native allocations, code cache.
- Không phải mọi page đều có thể dùng chung.
- RSS của từng process có thể tính cả shared mapped pages, nên **cộng RSS đơn giản giữa processes có thể đếm trùng**. Trên Linux có thể cân nhắc PSS hoặc các metrics phù hợp khi đánh giá total shared-memory footprint.
- Một JVM đơn độc vẫn có thể giảm startup ngay cả khi chưa có tiến trình thứ hai để share page với nó.

### 4.4. Không phải Java-level shared mutable memory

CDS không cung cấp API giống shared-memory queue hay distributed cache. Không có điều kiện Java Memory Model nào cho phép thread ở process A tự truy cập `static int counter` của process B nhờ cả hai cùng map archive.

## 5. Điều gì vẫn riêng cho mỗi JVM?

Ngay cả khi class `CDSDemo` được load từ shared archive, mỗi JVM process có runtime state độc lập:

| Thành phần | Dùng chung nhờ CDS? | Ghi chú |
| --- | --- | --- |
| Những metadata pages read-only đã archive | **Có thể chia sẻ qua OS** | Tùy điều kiện archive/mapping |
| Những archive pages bị ghi/COW | **Không giữ sharing của phần đã copy** | Private modified pages |
| Java heap thông thường | **Không** | Mỗi JVM có heap riêng |
| Objects tạo bởi `new` trong app | **Không** | Mỗi process tạo object riêng |
| Giá trị static mutable của class | **Không** | Runtime class state mỗi JVM |
| Java threads và stack frames | **Không** | Tạo riêng từng process |
| Monitor locks và synchronization state | **Không theo nghĩa app dùng chung giữa processes** | JMM áp dụng trong mỗi JVM process |
| JIT profiles, C1/C2 compiled methods | **Không chỉ vì bật CDS** | Code cache và JIT state riêng |
| GC state, roots và heap generations | **Không** | GC quản lý heap từng process |
| Network connections / DB pools | **Không** | App cần khởi tạo riêng |
| CDS archive file | **Có thể cùng sử dụng** | File/page cache được OS chia sẻ |

**Cách nhớ:** *shared class metadata* ≠ *shared live application state*.

## 6. CDS không bỏ qua class initialization (`<clinit>`)

Đây là điểm dễ gây nhầm nhất.

```java
final class Settings {
    static final int LIMIT;

    static {
        LIMIT = 42;
        System.out.println("Settings initialized");
    }
}
```

Đây là class snippet. Khi một process đầu tiên active-use `Settings`, JVM phải thực hiện initialization phù hợp và in marker. Process thứ hai dù dùng cùng CDS archive **vẫn có trạng thái class initialization riêng** và có thể in marker khi active-use trong process ấy.

### Vì sao archive không thể “làm sẵn” tùy ý `<clinit>`?

Static initializer có thể:

- Đọc environment variables/config.
- Tạo objects gắn với process.
- Mở files/sockets.
- Gọi JNI/native code.
- Đăng ký shutdown hooks.
- Khởi tạo static fields phụ thuộc runtime.

Nếu JVM bỏ qua tất cả side effects này chỉ vì class metadata đã archive, semantics có thể sai. CDS vì thế **không phải cache kết quả tùy ý của application static initialization**.

### 6.1. Archived heap objects là một phạm vi hẹp hơn

Một số JVM versions/GC configurations hỗ trợ archive các đối tượng heap chuyên biệt đã được VM chuẩn bị một cách an toàn. Điều này **không đồng nghĩa** có thể archive mọi object sinh ra từ user-defined `<clinit>` và tái dùng nó như một mutable singleton giữa các JVM processes.

### 6.2. Class load != class init

CDS thường tập trung giảm work lúc **loading/linking**. JLS §12.4 vẫn quy định lúc nào initialize. Một class có thể được load từ archive mà static block vẫn chạy khi first active use.

## 7. CDS không thay thế JIT warm-up

Hai tối ưu giải quyết hai loại công việc khác nhau:

```text
CDS:    bytecode/class representation -> shared archived metadata
        Giảm chi phí load/link tương ứng

JIT:    executable hot bytecode -> machine code
        Cải thiện hiệu năng thực thi hot methods/loops
```

Một application chạy nhiều lần:

- Có thể dùng CDS giúp nạp metadata nhanh hơn.
- Nhưng C1/C2 vẫn có thể cần runtime profiles để tối ưu.
- Nếu code chưa hot, vẫn có thể chạy interpreter.
- Nếu code đã hot, JVM có compiled code trong **private code cache**, không tự lấy native code C2 của process trước từ `.jsa`.

Không viết “bật CDS là chương trình đã warm-up C2 trước khi `main`” hoặc “archive là Java executable”.

### 7.1. Tránh nhầm CDS với AOT code caching

Có những cơ chế AOT/native-image/code precompilation khác qua các JDK và JVM distributions. CDS `.jsa` trong phạm vi JDK 17 không phải một JIT-compiled method-cache nói chung. Nếu một release mới bổ sung các khả năng AOT liên quan, phải đọc **tài liệu đúng phiên bản** chứ không nhập lẫn semantics.

## 8. Default CDS archive — vì sao không cần tự tạo gì đã thấy hiệu ứng?

Từ JDK 12, nhiều JDK 64-bit distributions (gồm Oracle JDK) cung cấp **default CDS archive** được tạo sẵn, thường chứa những platform/core library classes hay dùng.

Theo tài liệu Oracle JDK 17, trên cấu hình phổ biến, đường dẫn default archive là:

```text
Linux/macOS: $JAVA_HOME/lib/server/classes.jsa
Windows:     %JAVA_HOME%\bin\server\classes.jsa
```

Lưu ý: vị trí và việc có archive phụ thuộc JDK vendor/distribution/install layout, không phải JLS guarantee.

### 8.1. Ba chế độ thường gặp

| Option | Ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| **`-Xshare:auto`** | Dùng CDS khi có archive tương thích, có thể fallback | Mặc định phù hợp ở nhiều HotSpot builds |
| **`-Xshare:off`** | Tắt CDS để đối chứng | Phù hợp testing/diagnostics |
| **`-Xshare:on`** | Yêu cầu dùng CDS; không dùng được thì lỗi/exit | **Chỉ dùng testing**, không khuyến nghị production |

Lệnh thử:

```bash
java -Xshare:auto -version
java -Xshare:off -version
java -Xshare:on -version
```

Với `-Xshare:on`, JVM có thể **khởi động thất bại** khi archive tương thích không có hoặc cấu hình gây xung đột. Không nên dùng flag này trên production chỉ vì muốn “bắt buộc nhanh”.

### 8.2. Không có archive phù hợp thì sao?

Trong **auto mode**, JVM có thể không dùng archive và thực hiện class loading bình thường theo chính sách HotSpot. Khi **on mode**, việc không thể dùng CDS có thể khiến VM fail thay vì tiếp tục.

**Một process chạy thành công không đủ chứng minh CDS đã được dùng.** Hãy quan sát `-Xlog:cds=info` và nguồn class loading.

## 9. AppCDS — đưa lớp ứng dụng vào archive

**Application Class Data Sharing (AppCDS)** mở rộng ý tưởng từ core JDK classes sang application/library classes phù hợp.

Tình huống:

- 10 JVM instances đều chạy cùng application JAR.
- Những classes/framework libraries giống nhau được nạp rất nhiều lần.
- Nếu archive metadata đã chuẩn bị phù hợp, các processes có thể map lại một phần dữ liệu đó.

AppCDS **có thể** giúp startup và footprint. Nhưng nếu chương trình chủ yếu tốn thời gian kết nối DB, đọc config hoặc chạy expensive initialization, AppCDS không giải quyết toàn bộ.

### 9.1. Không có nghĩa archive “chứa tất cả classes của JAR”

Một archive thường chứa **tập classes đủ điều kiện và đã được quan sát/đưa vào class list** trong quá trình build/dump.

Những classes ở code paths chưa được chạy hoặc các classes không archive-eligible có thể vẫn được load bình thường sau này.

### 9.2. Runtime class loader và archive eligibility

HotSpot AppCDS hỗ trợ những trường hợp built-in loaders và một số custom-loader classes theo điều kiện phiên bản/nguồn class/compatibility phù hợp. **Không cam kết mọi custom bytecode generator, runtime proxy hay classloader tự viết đều được archive và reuse hoàn toàn**.

### 9.3. Vì sao archive phải gắn đúng artifact?

CDS metadata phản ánh những classes/JARs và VM configuration ở thời điểm tạo archive. Nếu code thay đổi nhưng ta cố dùng metadata cũ, kết quả có thể sai; vì vậy JVM có compatibility checks và có thể từ chối/dừng dùng archive.

**Không dùng một archive build từ artifact A để kỳ vọng nó đại diện chính xác cho artifact B**.

## 10. Base archive và dynamic top archive

HotSpot có thể sử dụng tối đa **hai tầng archive** trong cấu hình tài liệu JDK 17:

1. **Base (static) archive:** thường là default archive chứa core classes từ JDK.
2. **Dynamic (top) archive:** thêm những classes được xác định từ một lần chạy ứng dụng và không có trong base archive tương ứng.

```text
               Base archive
         $JAVA_HOME/.../classes.jsa
          (core / base classes)
                     |
                     v
          Dynamic top archive
                app.jsa
        (application/library classes)
                     |
                     v
         Java process startup:
    map base + dynamic when compatible
                     |
                     v
      load archived metadata on demand
```

Từ “static”/“dynamic” ở đây là **cách tạo/tầng archive**, **không phải** Java keyword `static`, không phải trạng thái initialized hay dữ liệu “tĩnh/động” trong heap.

### 10.1. Dynamic archive không thay thế base

Một dynamic top archive thường **phụ thuộc base archive** dùng khi tạo nó. Khi khởi chạy, JVM cần một base archive tương thích để map top archive đúng cách.

### 10.2. Đường dẫn `SharedArchiveFile`

Trong các trường hợp được tài liệu hỗ trợ:

```text
-XX:SharedArchiveFile=app.jsa
```

có thể dùng trực tiếp một dynamic archive, để JVM tìm base archive đã được ghi nhận.

Khi chỉ định tường minh cả hai:

```text
Linux/macOS: -XX:SharedArchiveFile=base.jsa:app.jsa
Windows:     -XX:SharedArchiveFile=base.jsa;app.jsa
```

Dấu phân tách **khác nhau giữa OS**. Trên command line Windows shell, dấu `;` cũng có thể có ý nghĩa riêng, nên quote toàn bộ JVM argument nếu cần.

## 11. Ví dụ Java 17+ độc lập: CDS không chia sẻ static state

Tạo tệp **`CDSDemo.java`**:

```java
public final class CDSDemo {
    private static volatile long sink;

    static final class Engine {
        static final int base;

        static {
            base = 7;
            System.out.println("engine initialized");
        }

        static int mix(int x) {
            return (x * 31 + (x >>> 3) + base) & 1023;
        }
    }

    static long compute() {
        long sum = 0;
        for (int i = 0; i < 10_000; i++) {
            sum += Engine.mix(i);
        }
        sink = sum;
        return sum;
    }

    public static void main(String[] args) {
        System.out.println("started");
        long result = compute();
        System.out.println("checksum=" + result);
        System.out.println("sinkMatches=" + (sink == result));
    }
}
```

Đặt file ở thư mục thực hành riêng, không cần module/package.

### 11.1. Biên dịch và đóng gói JAR

```bash
javac --release 17 CDSDemo.java
jar --create --file cds-demo.jar CDSDemo.class 'CDSDemo$Engine.class'
```

**Quan trọng về shell:** Lệnh `jar` trên là ví dụ cho Bash/POSIX shell với **single quotes**, dùng để tránh `$Engine` bị shell hiểu là một biến. Trên Windows PowerShell, có thể dùng:

```powershell
javac --release 17 CDSDemo.java
jar --create --file cds-demo.jar CDSDemo.class 'CDSDemo$Engine.class'
```

PowerShell cũng chấp nhận một chuỗi single-quoted literal như trên. Tùy layout, nếu đã tồn tại JAR cũ trong thư mục thì xóa/đổi tên JAR test theo cách an toàn trước khi tạo lại; không ghi đè artifacts sản xuất.

### 11.2. Chạy không dùng CDS

```bash
java -Xshare:off -cp cds-demo.jar CDSDemo
```

**Stdout chính xác khi chạy thành công:**

```text
started
engine initialized
checksum=5113344
sinkMatches=true
```

### 11.3. Chạy với CDS mặc định

```bash
java -Xshare:auto -cp cds-demo.jar CDSDemo
```

Chương trình có **cùng bốn dòng stdout** như trên. Default CDS có thể giúp một số core JDK classes, nhưng **chưa chắc** đã archive `CDSDemo` vì nó là application class chưa có trong default archive.

### 11.4. Tại sao static initializer vẫn in?

Mỗi lần khởi chạy Java process mới, class `CDSDemo$Engine` được active-use lần đầu, chạy static block theo JLS và in `engine initialized`.

Tệp `.jsa` có thể cung cấp class metadata đã chuẩn bị, **không dùng chung static variable value trong hai JVM processes** hoặc bỏ đi side effect của source initializer.

### 11.5. Kiểm thử được thực hiện

File đã được biên dịch bằng **`javac --release 17`**, sau đó chạy thành công bằng các options liên quan CDS trên **OpenJDK/HotSpot JDK 24.0.2** tại môi trường thử nghiệm.

**Phân biệt rõ:** Đây là code Java 17-compatible, **không phải lời khẳng định đã chạy trên một binary JDK 17 cụ thể**. Các lệnh sử dụng những tùy chọn được tài liệu JDK 17 mô tả. Số build/runtime phải được kiểm tra lại ở nơi bạn triển khai.

## 12. Dynamic AppCDS: top archive và ý nghĩa của lần chạy chuẩn bị

Trên **HotSpot JDK 17**, dùng application JAR đã tạo ở phần 11:

```bash
java -XX:ArchiveClassesAtExit=cds-demo.jsa -cp cds-demo.jar CDSDemo
```

Chương trình vẫn thực thi bình thường; JVM ghi **dynamic top archive** ở giai đoạn exit phù hợp. Archive chứa **metadata của các lớp đủ điều kiện đã được nạp** nhưng chưa thuộc base archive, **không phải ảnh chụp Java heap để process khác tiếp tục**. Nếu process bị kill đột ngột, base archive không phù hợp hoặc configuration lỗi, không được giả định file `.jsa` đã sẵn sàng. Cần xác minh file/exit code và log.

## 13. Dùng dynamic archive — kiểm chứng lớp được chia sẻ

Ở một **JVM process mới**, cùng JDK build và application JAR:

```bash
java -XX:SharedArchiveFile=cds-demo.jsa -Xlog:class+load=info -cp cds-demo.jar CDSDemo
```

Ứng dụng vẫn phải có cùng hành vi: `started`, `engine initialized`, `checksum=5113344`, `sinkMatches=true`. Trong diagnostic log HotSpot, lớp thực sự được tải từ dynamic top archive có thể có marker `source: shared objects file (top)`. Một class còn được đọc từ JAR có thể hiển thị `source: file:...`. **Chỉ có file `.jsa` trên đĩa hay thấy JVM chạy thành công chưa đủ để kết luận application class đã dùng CDS**.

CDS reuse metadata, không chia sẻ mutable `static` fields giữa JVM processes và không chạy trước các static initializers tùy ý. Bài về **AppCDS static/dynamic** ngay sau đây dạy đầy đủ workflow; bài về **class-loading logs** giúp xác định archive mapped, class source và fallback.

## 14. Quan sát memory mapping bằng `-Xlog:cds`

Một lệnh chẩn đoán:

```bash
java -XX:SharedArchiveFile=cds-demo.jsa \
     -Xlog:cds=info \
     -cp cds-demo.jar CDSDemo
```

Các sự kiện HotSpot có thể cho thấy:

```text
... Opened archive .../classes.jsa
... Opened archive cds-demo.jsa
... Mapped static  region #... (ReadOnly)
... Mapped dynamic region #... (ReadOnly)
... Mapped dynamic region #... (ReadWrite)
```

Đây là **log mẫu được rút gọn**, không phải thứ tự/timestamps/addresses bắt buộc. JVM có thể map archive tại những địa chỉ khác và log thêm xử lý pointer relocations/heap objects.

### 14.1. Vì sao có nhiều regions?

HotSpot có thể chia archive thành những regions được bảo vệ/định vị khác nhau theo cách triển khai. Các regions có thể chứa read-only metadata, writable/COW data, bitmap/relocation metadata v.v. **Không hứa mỗi archive chỉ một memory-mapped region**.

### 14.2. Vì sao có thể phải relocate?

Archive được tạo với một số layouts/pointer assumptions. Khi map vào process mới, address-space layout và runtime pointer encoding có thể khác; VM xử lý compatibility hoặc relocations nếu hỗ trợ.

Điều này không phá nguyên lý sharing; shared file pages vẫn có thể mang lại lợi ích nếu tương thích, nhưng đôi khi phải có private adjustments.

### 14.3. Không dùng `-Xlog:cds` như stopwatch chính xác

Logging có I/O overhead và nội dung event là diagnostic, không phải một phép tách thuần túy tất cả memory mapping/preparation CPU costs. Dùng log để **xác nhận và giải thích**, rồi đo startup benchmark **không logging**.

## 15. Static AppCDS — class list, dump và reuse

Static AppCDS tách **thu thập danh sách class** và **tạo archive** thành hai pha. Ví dụ tối giản trên HotSpot JDK 17:

```bash
java -Xshare:off -XX:DumpLoadedClassList=cds-demo.classlist -cp cds-demo.jar CDSDemo
java -Xshare:dump -XX:SharedClassListFile=cds-demo.classlist -XX:SharedArchiveFile=cds-static.jsa -cp cds-demo.jar
java -XX:SharedArchiveFile=cds-static.jsa -cp cds-demo.jar CDSDemo
```

Lệnh đầu **chạy ứng dụng**, lệnh thứ hai tạo archive **không gọi `main`**, lệnh cuối khởi chạy JVM mới. Điều kiện JDK/classpath/JAR phải tương thích; ứng dụng tiếp tục tuân theo Java class initialization semantics. Bài tập đầy đủ về classlist, dynamic top archive, flags, CI/CD và các trường hợp lỗi là trọng tâm riêng của bài **AppCDS, archive tĩnh và archive động**.

| So sánh | Static archive | Dynamic archive |
| --- | --- | --- |
| Class list riêng | Có trong workflow thông dụng | Không bắt buộc |
| Thời điểm tạo | Pha `-Xshare:dump` | Khi app exit với `ArchiveClassesAtExit` |
| Base/top | Custom static/base | Top layer phụ thuộc base |
| Java objects/state dùng chung giữa process | Không tự động | Không tự động |

Trên HotSpot JDK 17, static dump có ràng buộc classpath; vì vậy dùng JAR thay vì giả định non-empty class directory luôn hợp lệ. Xác minh archive bằng `-Xlog:cds` và **nguồn class** bằng `-Xlog:class+load`, không chỉ kiểm tra file tồn tại.

## 16. Dùng `jcmd VM.cds` khi phù hợp

Tài liệu Oracle JDK 17 `java` có nhắc công cụ `jcmd` có thể hỗ trợ tạo CDS archives từ JVM đang chạy, với những diagnostic commands như:

```text
jcmd <pid> VM.cds static_dump my_static_archive.jsa
jcmd <pid> VM.cds dynamic_dump my_dynamic_archive.jsa
```

**`<pid>` là placeholder**; dùng PID thực tế. Các commands/arguments có thể phụ thuộc build/permissions.

### 16.1. Dynamic dump cần cấu hình phù hợp

Theo tài liệu `java` của JDK 17, `VM.cds dynamic_dump` có thể cần JVM được start với:

```text
-XX:+RecordDynamicDumpInfo
```

Không giả định mọi process đã chạy sẵn đều cho phép dynamic dump. Kiểm tra:

```bash
jcmd <pid> help
```

### 16.2. Không đụng vào production process không kiểm soát

Diagnostic operations có thể làm tăng CPU/memory/I/O, tạo file và thay state profiling. Thử trên môi trường test/staging trước khi thêm dump operation vào production runbooks.

## 17. Tại sao archive đôi khi không sử dụng được?

Archive có thể không phù hợp vì:

- **JDK vendor/build/version** không trùng hoặc không tương thích với archive tạo ra.
- **Classpath/JAR changes**: file JAR chứa lớp đã archive được sửa sau khi dump.
- **Module/classpath restrictions** hoặc các option `--upgrade-module-path`, `--patch-module`, `--limit-modules` có tác động làm CDS không khả dụng trong những cấu hình JDK 17 được tài liệu ghi rõ.
- **Base archive** của dynamic top archive không phù hợp.
- **VM options/GC/pointer encoding** hoặc những runtime assumptions khác không khớp.
- **Custom classloader behavior** làm lớp không đủ điều kiện hoặc không thể được dùng từ archive.
- **Java agents/instrumentation/class transformation** thay hình dạng class khi load.
- Archive bị thiếu, không đọc được, bị hỏng hoặc permission không phù hợp.

### 17.1. Fallback vs fail-fast

- `-Xshare:auto`: cố dùng nếu tương thích, có thể fallback khi không dùng được.
- `-Xshare:on`: yêu cầu dùng, nên lỗi khi archive không khả dụng; chỉ dùng testing.
- `-Xshare:off`: không dùng archive, hữu ích tạo baseline.

**Không kết luận CDS đang hoạt động chỉ vì VM options có `-Xshare:auto`**. Cần bằng chứng từ `-Xlog:cds=info` và `-Xlog:class+load=info`.

### 17.2. Hãy rebuild khi deployment artifact thay đổi

Một CI/CD pipeline tạo application JAR mới thì phải xem archive cũ như một artifact **versioned và có dependency** lên JDK + app. Nếu classpath/JAR thay đổi, nên tạo lại archive dưới cùng cấu hình deployment tương ứng.

### 17.3. An toàn, đồng nhất và provenance

Không coi `.jsa` là một nguồn dữ liệu tùy ý có thể tải từ bên thứ ba rồi map vào production. Nó là **VM-specific binary artifact**, nên phải được tạo/kiểm soát qua trusted build pipeline và được bảo vệ bằng file permissions, image signatures và deployment policy thích hợp.

## 18. CDS và Class Data Sharing trong container

Một hình dung phổ biến:

```text
Container image:
  JDK runtime + classes.jsa
  application.jar
  cds-demo.jsa (optionally generated at image build)
          |
       deployment
          |
  +-------+--------+
  |                |
Pod/JVM A        Pod/JVM B
  |                |
Same host image layers + compatible mapping?
  -> OS có thể share file-backed physical pages
  -> mỗi JVM vẫn có private heap, threads, JIT state
```

### 18.1. Shared pages giữa containers có thể xảy ra

Khi containers trên **cùng OS kernel/host** map file-backed pages phù hợp, filesystem/page cache và memory mappings có thể đem lại sharing tương tự các processes thông thường. Nhưng không được suy **containers ở các hosts khác nhau có một RAM vật lý dùng chung**.

### 18.2. Image build có thể tạo archive trước deployment

Nếu build pipeline tạo archive bằng **đúng JDK build, app JAR và options** dự định sử dụng, runtime có thể map nó ở lần khởi động đầu. Điều này có thể hữu ích cho services restart/scale thường xuyên.

### 18.3. Application mutable state không chia sẻ

Pod A đổi `static int count` không thay `static int count` của Pod B. CDS chỉ giúp reuse những dữ liệu lớp đủ điều kiện; đồng bộ state giữa các pods vẫn cần network/database/messaging hoặc cơ chế phân tán thích hợp.

### 18.4. Đừng chỉ đo container boot event

Tách:

- Container image pull/unpack/start.
- OS/JVM process startup.
- Application readiness.
- First-request latency.
- Memory footprint/RSS/PSS.
- Resource pressure khi many JVMs cùng host.

CDS thường giúp **bên trong Java startup/class loading**, không giải quyết toàn bộ image pull/network initialization.

## 19. JAR packaging và classpath consistency

Archive tạo từ application JAR được kiểm tra với classpath/JAR metadata, do đó:

1. Giữ path/order classpath hợp lệ theo JDK rules.
2. Không sửa JAR sau khi tạo archive.
3. Không trộn classes từ phiên bản khác mà không rebuild archive.
4. Kiểm tra symlinks/mount paths trong deployment environment nếu phát sinh incompatibility.
5. Không cho rằng tương đương source code bảo đảm binary artifact giống nhau; timestamp/manifest/layout có thể ảnh hưởng checks.

### 19.1. Fat JAR, nested JAR và custom loaders

Một fat JAR hoặc framework launcher có thể dùng class loader/URL/resource semantics khác classpath JAR thông thường. Không giả định mọi framework nested-JAR structure đều được CDS xử lý giống lệnh `java -cp cds-demo.jar CDSDemo`.

Cách đúng là tạo archive bằng **chính phương thức launch production** được hỗ trợ rồi kiểm tra class origins trong logs.

### 19.2. Classpath thay đổi nhưng archive vẫn được dùng một phần?

Các JDK releases có quy tắc kiểm tra classpath khác nhau cho base/top archive. Oracle JDK 17 document mô tả constraints cụ thể như classpath lúc dump phải trùng hoặc là prefix của runtime classpath trong những workflow liên quan. **Không suy mọi loại thay đổi đều làm archive hoàn toàn vô dụng, cũng không hứa bất kỳ thay đổi nào an toàn**. Xem log và chính sách build/version.

## 20. Đánh giá startup bằng thí nghiệm có kiểm soát

Tối thiểu tạo các nhóm:

| Nhóm | JVM options | Ý nghĩa |
| --- | --- | --- |
| **A** | `-Xshare:off` | Baseline không CDS |
| **B** | `-Xshare:auto` | Default core-class CDS |
| **C** | `-XX:SharedArchiveFile=cds-demo.jsa` | Default base + AppCDS dynamic top |
| **D** | `-Xshare:on` (chỉ test phù hợp) | Confirm tính sẵn dùng, không là production tuning mặc định |

Cần giữ cùng:

- JDK vendor/version/build.
- App JAR và classpath.
- JVM heap/GC/cpu flags, container quotas.
- Workload đầu vào và correctness checksum.
- Host/OS và mức cạnh tranh CPU/I/O tương đương.
- Số repetitions, cách randomize/exchange order.
- Mốc đo (process wall time, time to ready, first request).

### 20.1. Thu đúng metrics

**External process elapsed time**: bao gồm launch/bootstrap/execution/shutdown. Sử dụng GNU `time`, PowerShell `Measure-Command` hoặc parent benchmark harness.

**Application readiness time**: dùng readiness marker/health probe, không chỉ khi `main` bắt đầu.

**First request latency**: đo riêng vì CDS có thể chuyển một phần chi phí startup, nhưng ứng dụng vẫn có lazy init/JIT/network work.

**Total memory footprint**: đo khi nhiều JVM instances chạy đồng thời, phân biệt RSS và shared pages/PSS khi OS hỗ trợ.

### 20.2. Không đo baseline khi in class-load logs

`-Xlog:class+load=info` có thể sinh hàng nghìn lines và tạo I/O overhead. **Chạy diagnostics riêng baseline** để kiểm tra archive use, sau đó đo performance không bật heavy logging.

### 20.3. Đừng lấy một sample làm tốc độ bảo đảm

Một JVM restart mới có thể dùng OS page cache đã ấm; C2 runtime state vẫn mới. CDS benefit thường lớn hơn trong workload class-heavy, trong khi application chủ yếu I/O có thể gần như không đổi end-to-end startup.

Đo **median/spread/p95** qua nhiều runs và nêu assumptions rõ ràng.

## 21. Ví dụ tập lệnh benchmark trên PowerShell

Sau khi có `cds-demo.jar` và `cds-demo.jsa`:

```powershell
foreach ($mode in @("off", "base", "app")) {
    Write-Output "MODE=$mode"
    foreach ($trial in 1..5) {
        if ($mode -eq "off") {
            Measure-Command { java -Xshare:off -cp cds-demo.jar CDSDemo }
        } elseif ($mode -eq "base") {
            Measure-Command { java -Xshare:auto -cp cds-demo.jar CDSDemo }
        } else {
            Measure-Command {
                java -XX:SharedArchiveFile=cds-demo.jsa -cp cds-demo.jar CDSDemo
            }
        }
    }
}
```

Đây là lệnh **minh họa đo lặp** chứ chưa phải báo cáo statistics tự động. Nếu cần tính median, hãy thu `TotalMilliseconds` từ `Measure-Command` vào CSV và đảm bảo Java process exit code/checksum hợp lệ.

### 21.1. Những lỗi đo dễ gặp

- Đo run thứ nhất với filesystem cache lạnh, run thứ hai với cache ấm.
- Dùng `-Xshare:off` cho baseline nhưng quên archive đã bị fallback trong mode khác.
- Dùng log verbose ở chỉ một mode.
- So một process kết thúc ngay với service tồn tại liên tục.
- Đưa `-Xcomp`, heap/GC flags khác vào một nhóm làm mất kiểm soát biến.
- Benchmark quá ngắn nên shell/process scheduling noise áp đảo CDS effects.

## 22. Các lợi ích CDS không được hứa tuyệt đối

**CDS có thể**:

- Giảm work khi load/link những classes nằm trong archive.
- Giảm startup time của class-heavy JVM applications.
- Giảm tổng memory footprint qua nhiều processes sharing archive pages.
- Giảm phần JVM startup trong service scale-out/container workloads.

**CDS không đảm bảo**:

- Mọi class được nạp từ archive.
- Mọi class initialize sớm hoặc không initialize.
- Mọi Java objects hoặc static fields được share.
- Các hot methods tự có C2 compiled code lúc startup.
- Runtime execution throughput tăng đúng một tỷ lệ.
- Tất cả Java process startup time là class loading, hoặc có thể giảm hết bằng CDS.
- Archive tương thích qua mọi JDK update, app version hoặc JVM flags.
- Tránh mọi class verification/resolution work có thể phát sinh.

**Không biến “up to X% faster startup” của một benchmark bên ngoài thành performance claim cho tất cả services.**

## 23. So sánh CDS với các khái niệm khác

| Khái niệm | Cơ chế | Khác CDS ở điểm nào? |
| --- | --- | --- |
| **JIT C1/C2** | Biên dịch hot bytecode thành machine code | Không chỉ chia sẻ class metadata |
| **Class initialization** | Chạy `<clinit>` khi có active use | CDS không bỏ init side effects |
| **Classpath scanning** | Framework tìm classes/annotations/resources | Scanning là work khác, có thể chưa định nghĩa classes |
| **JAR compression** | Nén classes/resources trên đĩa | CDS lưu runtime-ready data để tái dùng |
| **OS filesystem page cache** | Cache pages của tệp | CDS tận dụng mappings và runtime format, không chỉ caching JAR bytes |
| **Metaspace** | Vùng runtime metadata của HotSpot | Archived metadata có sharing/mapping rules riêng |
| **Shared mutable Java heap** | Cơ chế chia sẻ state đối tượng giữa processes | CDS không cung cấp loại API đó |
| **CRaC/checkpoint restore** | Lưu/khôi phục trạng thái process trong công nghệ tương ứng | Không đồng nghĩa CDS; lifecycle và side effects khác |
| **Native-image/AOT compilation** | Biên dịch một phần code trước runtime | Không phải cùng định dạng/hợp đồng với AppCDS JDK 17 |

## 24. Những hiểu lầm thường gặp

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “CDS chia sẻ mọi Java objects giữa JVM processes.” | Chủ yếu chia sẻ metadata/archive pages đủ điều kiện; mỗi process có heap/state riêng. |
| “Hai JVM có cùng static field value vì cùng archive.” | Static mutable state được khởi tạo/quản lý riêng cho mỗi runtime. |
| “Có `.jsa` thì static initializer không chạy.” | `<clinit>` vẫn theo JLS initialization rules. |
| “CDS là cache của C2 compiled code.” | Không phải JIT code cache nói chung của HotSpot JDK17. |
| “Class loaded từ shared objects file là class có sẵn Java instance.” | Shared class representation khác object instance. |
| “CDS bật nghĩa mọi class của JAR archived.” | Chỉ các classes đủ điều kiện được tạo archive và dùng. |
| “Archive disk file luôn nhỏ hơn JAR.” | Runtime-ready archive data có thể lớn hơn class bytes. |
| “-Xshare:on là lựa chọn production tốt nhất.” | Oracle ghi rõ chỉ nên dùng testing vì có thể khiến VM fail startup. |
| “-Xshare:auto luôn bắt buộc dùng được archive.” | Có thể fallback khi archive không tương thích. |
| “Chỉ cần chạy mặc định và thấy kết quả đúng là CDS hoạt động.” | Cần log `cds` và `class+load` để xác nhận. |
| “CDS chia sẻ dữ liệu qua RAM giữa hai hosts khác nhau.” | OS page sharing là trên cùng host/kernel, không phải phân tán RAM. |
| “Không có RO pages share thì mọi CDS performance benefit biến mất.” | Ngay một process có thể hưởng startup benefit từ archive. |
| “RSS của N JVM cộng lại là tổng RAM không trùng lặp.” | RSS có thể đếm shared pages nhiều lần. |
| “Dynamic top archive có thể đứng độc lập không cần base.” | Theo mô hình JDK17 dynamic archive phụ thuộc base tương thích. |
| “Chỉnh JAR sau khi dump vẫn chắc dùng archive cũ.” | Runtime validation có thể từ chối và yêu cầu rebuild. |
| “-XX:ArchiveClassesAtExit lưu heap tại exit.” | Nó ghi class data archive, không snapshot tùy ý của app heap. |
| “CDS thay việc kết nối DB hoặc warm TLS.” | Không. Đây là application/environment initialization work khác. |
| “Class sharing xóa class identity theo loader.” | Loader/class identity semantics vẫn phải đúng. |
| “Có class ở archive thì runtime không cần class initialization lock.” | Class init synchronization/lifecycle vẫn được giữ. |
| “Default archive chứa hết application classes.” | Default thường nhắm vào các core JDK classes. |
| “Bật class-load logging không ảnh hưởng benchmark.” | Verbose logging có overhead và phải tách diagnostic runs. |
| “CDS chỉ hữu ích khi có hai JVM.” | Một JVM có thể tiết kiệm startup; nhiều JVM giúp thêm memory sharing. |

## 25. Tự kiểm tra kèm đáp án

**Câu 1.** CDS là viết tắt của gì?

**Đáp án:** Class Data Sharing — cơ chế HotSpot archive/reuse những dữ liệu lớp đủ điều kiện để cải thiện startup và memory footprint.

**Câu 2.** Archive thường có đuôi gì?

**Đáp án:** `.jsa`, ví dụ `classes.jsa` hoặc `cds-demo.jsa`.

**Câu 3.** Nhiều JVM share archive bằng cơ chế cấp OS nào?

**Đáp án:** Memory mapping của file, có thể share read-only physical pages và COW/private writable state.

**Câu 4.** Có thể làm thay đổi `static int counter` của JVM B bằng cách sửa counter của JVM A không?

**Đáp án:** Không. Application static/runtime state là riêng từng process.

**Câu 5.** CDS có tự bỏ `<clinit>` không?

**Đáp án:** Không. Initialization code/side effects vẫn theo Java semantics.

**Câu 6.** CDS có giúp class loading nhanh hơn JAR không?

**Đáp án:** Có thể. Archived runtime-ready metadata giúp tránh lặp một phần read/parse/link work với classes phù hợp.

**Câu 7.** `-Xshare:off` làm gì?

**Đáp án:** Tắt CDS, thường dùng làm baseline/diagnostics.

**Câu 8.** `-Xshare:auto` khác `-Xshare:on` thế nào?

**Đáp án:** Auto dùng nếu có archive phù hợp và có thể fallback; on yêu cầu dùng, lỗi nếu không thể và chỉ nên dùng testing.

**Câu 9.** Default CDS archive thường chứa lớp nào?

**Đáp án:** Những platform/core library classes hay dùng được build JDK chuẩn bị sẵn, tùy distribution.

**Câu 10.** AppCDS là gì?

**Đáp án:** Application Class Data Sharing, mở rộng archive tới các application/library classes đủ điều kiện.

**Câu 11.** Dynamic top archive được tạo bằng option nào?

**Đáp án:** `-XX:ArchiveClassesAtExit=app.jsa` trong workflow phù hợp với JDK17.

**Câu 12.** Top archive có cần base archive không?

**Đáp án:** Có, theo mô hình dynamic AppCDS JDK17 cần base archive tương thích.

**Câu 13.** Vì sao `CDSDemo$Engine` vẫn in marker khi chạy lần sau bằng archive?

**Đáp án:** Static initializer chạy theo class initialization của process mới; metadata sharing không giữ live static state của process cũ.

**Câu 14.** Log nào chứng minh app class đến từ archive?

**Đáp án:** `-Xlog:class+load=info` với source báo `shared objects file` hoặc `shared objects file (top)` trên HotSpot phù hợp.

**Câu 15.** `-Xlog:cds=info` cho biết gì?

**Đáp án:** Các thông tin mở/map archive, region handling, compatibility/relocation theo JVM build.

**Câu 16.** Vì sao không nên tải archive `.jsa` tùy tiện trên Internet?

**Đáp án:** Đây là binary VM-specific artifact; cần nguồn đáng tin và đúng build/configuration để tránh compatibility/security issues.

**Câu 17.** Static AppCDS khác dynamic ở bước đầu nào?

**Đáp án:** Workflow static thường cần capture class list và chạy `-Xshare:dump`; dynamic có thể archive tại process exit mà không cần class list riêng.

**Câu 18.** Vì sao không cộng RSS của ba JVM rồi gọi đó là RAM dùng riêng?

**Đáp án:** Shared mapped pages có thể được tính lặp trong RSS của mỗi process; PSS/OS metrics giúp đánh giá chia sẻ.

**Câu 19.** Có thể dùng archive tạo từ JDK 24 trên binary JDK 17 mà không kiểm tra không?

**Đáp án:** Không. CDS archives rất nhạy với JDK build/format compatibility.

**Câu 20.** CDS có làm methods `compute` C2 compiled trước lần chạy đầu không?

**Đáp án:** Không. JIT profiling/compilation là phần runtime khác CDS class metadata.

**Câu 21.** Vì sao app benchmark có thể không thấy startup cải thiện lớn dù CDS dùng đúng?

**Đáp án:** Class load/link chỉ là một phần tổng thời gian; framework initialization, I/O, networking, JIT, GC và OS launch có thể chiếm phần lớn.

**Câu 22.** Nếu archive không dùng được trong `-Xshare:auto`, cách kiểm tra?

**Đáp án:** Xem `-Xlog:cds=info`, `-Xlog:class+load=info` và compatibility conditions, sau đó rebuild archive nếu phù hợp.

**Câu 23.** Hai pods ở các hosts khác nhau có physical pages chung nhờ CDS không?

**Đáp án:** Không. Mỗi host có page cache/RAM riêng; CDS files có thể được triển khai đồng nhất nhưng không tạo shared physical memory liên host.

**Câu 24.** Khi nào nên tạo archive?

**Đáp án:** Trong CI/build/staging với JDK/application/config tương ứng production, rồi đo trước/sau; tránh archive cũ không cùng release.

## 26. Checklist áp dụng thực tế

1. Xác định **JDK vendor/build/version** của hệ đích.
2. Kiểm tra default CDS bằng `-Xlog:cds=info`.
3. Đối chiếu `-Xshare:off` và `-Xshare:auto` với cùng workload.
4. Nếu muốn archive application classes, đóng gói JAR theo workflow JDK17.
5. Chạy application qua `ArchiveClassesAtExit` để tạo dynamic top archive phù hợp.
6. Dùng `SharedArchiveFile` khi chạy lại.
7. Kiểm tra class origin qua `-Xlog:class+load=info`.
8. Kiểm tra static initializer vẫn chạy đúng trên mỗi process.
9. Ghi lại archive size và class coverage; không tối ưu chỉ vì có file.
10. Kiểm tra JAR unchanged, classpath/modulepath validity và base archive compatibility.
11. Không dựa vào `-Xshare:on` trong production.
12. Nếu custom loaders/agents có mặt, thử với đúng production launch command.
13. Với containers, phân biệt restart time và image pull/start overhead.
14. Với memory, so footprint khi nhiều JVMs chạy đồng thời; không cộng RSS thiếu ngữ cảnh.
15. Chạy diagnostic logging **tách** performance baseline.
16. Đo process wall time, application readiness, first request và memory footprint qua nhiều runs.
17. Không nhầm CDS với JIT warm-up, class init hoặc database connection setup.
18. Đưa archive thành artifact được quản lý/version cùng JDK và app, tái tạo khi thay build.

### Kết luận

```text
JAR/class bytes              CDS archive (.jsa)
     |                             |
  conventional                    runtime-ready
  loading path                    class metadata
     |                             |
     +---------- HotSpot ----------+
                       |
              map compatible archive
                       |
         +-------------+-------------+
         |                           |
    JVM process A               JVM process B
         |                           |
    shared file pages when supported
         |                           |
    private JVM heap             private JVM heap
    private statics              private statics
    private JIT state            private JIT state

CDS speeds eligible class data reuse.
CDS does NOT replace class initialization or JIT.
```

**Tóm lại:** CDS giúp HotSpot **không phải tạo lại toàn bộ metadata của những classes phổ biến** mỗi khi JVM process mới chạy. Archive được **memory-map**, cho phép chia sẻ read-only pages ở cấp OS và tái dùng dữ liệu runtime-ready. Khi mở rộng thành AppCDS, nhiều application/library classes cũng có thể tham gia. Nhưng mỗi JVM vẫn có **heap, static fields, threads, GC và JIT state riêng**; `<clinit>`, ứng dụng và business workflows vẫn phải vận hành đúng Java semantics. Đánh giá lợi ích qua **archive-use logs và startup/memory benchmark thực tế**, không chỉ qua sự tồn tại của tệp `.jsa`.

### Tài liệu chính thức

- [Oracle JDK 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html): default archives, memory footprint, dynamic AppCDS, các `-Xshare` options.
- [Oracle JDK 17 — `java` Command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): static/dynamic workflows, classpath/modulepath restrictions, `SharedArchiveFile`, `ArchiveClassesAtExit` và `jcmd VM.cds`.
- [dev.java — CDS and AppCDS in HotSpot](https://dev.java/learn/jvm/other-tools/cds-appcds/): cơ chế memory mapping, mặc định `-Xshare:auto` và hướng dẫn.
- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): mở rộng tới application classes.
- [OpenJDK JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): default archive cùng JDK.
- [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): dynamic top archive và dump khi process exit.
- [JVMS §5 — Loading, Linking, Initializing (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): semantics JVM class loading/initialization.
- [JLS §12.4 — Initialization of Classes and Interfaces (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): active use và class initialization.

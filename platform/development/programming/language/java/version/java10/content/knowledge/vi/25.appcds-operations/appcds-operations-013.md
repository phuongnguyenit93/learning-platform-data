# Phân biệt nền tảng AppCDS của Java 10 với các cơ chế lưu trữ được bổ sung về sau

## 1. Mục tiêu bài học

**AppCDS (Application Class Data Sharing)** xuất hiện trong **JDK 10** theo **JEP 310**: mở rộng khả năng **CDS (Class Data Sharing)** để có thể chia sẻ dữ liệu class của ứng dụng và thư viện, không chỉ các class nền tảng của JDK.

Từ mốc đó, HotSpot tiếp tục phát triển cách **tạo, tổ chức và tái sử dụng dữ liệu đã chuẩn bị trước** nhằm cải thiện startup, bộ nhớ chia sẻ và warm-up. Tuy nhiên, tên gọi giống nhau rất dễ dẫn tới nhầm lẫn:

- **AppCDS ở Java 10**: mở rộng *đối tượng class có thể nằm trong shared archive*.
- **Default CDS archive từ JDK 12**: bản JDK thông dụng có kho các class nền tảng được đóng gói sẵn.
- **Dynamic CDS archive từ JDK 13**: thu thập các class đã load và tạo một *top-layer archive* khi ứng dụng kết thúc.
- **AOT cache từ JDK 24**: mở rộng ý tưởng chuẩn bị trước, gồm **class loading/linking** và các artifact tối ưu hóa khác, không chỉ là class metadata.
- **JDK 25–26**: giảm số bước tạo AOT cache, bổ sung **method profiling** và mở rộng khả năng cache đối tượng sang các garbage collector khác.

**Điều quan trọng nhất:** Đây là **các giai đoạn phát triển liên quan nhau**, không phải sáu định dạng tệp có thể hoán đổi hoặc một câu lệnh chạy chung trên mọi phiên bản JDK. AppCDS/CDS **vẫn còn được hỗ trợ** trong JDK hiện đại; AOT cache đem lại lựa chọn rộng hơn trên JDK mới, nhưng không biến mọi `.jsa` thành `.aot`.

Bài học chỉ dùng các khái niệm và API/cờ JVM **vẫn có giá trị**. Những lệnh lịch sử chỉ phù hợp với bản JDK rất cũ không được lấy làm cấu hình đề xuất cho production hiện tại.

Sau khi học, bạn có thể:

1. Phân biệt mốc **JDK 10/12/13/24/25/26** chính xác.
2. Nhận biết **static CDS archive**, **default archive**, **dynamic archive** và **AOT cache** lưu những gì.
3. Chọn các cờ **`-XX:SharedArchiveFile`**, **`-XX:ArchiveClassesAtExit`**, **`-XX:AOTCacheOutput`**, **`-XX:AOTCache`** theo phiên bản JDK.
4. Chạy một ứng dụng Java 17+ có cùng kết quả chức năng trong nhiều chế độ tối ưu khởi động.
5. Kiểm tra hiệu quả bằng log JVM và benchmark, tránh nhầm “tệp tồn tại” với “cache được dùng”.
6. Quản lý tương thích với JDK, JAR, classpath, OS/CPU, container và lifecycle phát hành.

## 2. Trước hết: CDS khác AppCDS như thế nào?

### 2.1. CDS — nền tảng

Khi JVM thông thường tải class, nó phải đọc định dạng class và chuẩn bị một số cấu trúc runtime cần thiết. **CDS** đưa một phần công việc này vào giai đoạn chuẩn bị trước, lưu dữ liệu class đã được xử lý trong một **archive** để lần khởi động tương thích có thể tận dụng.

Lợi ích có thể bao gồm:

- Giảm một phần thời gian khởi động do tránh lặp lại một số xử lý class.
- Chia sẻ các trang bộ nhớ chỉ đọc/ít thay đổi giữa nhiều tiến trình JVM tương thích.
- Giảm footprint **thực tế** trong một số tình huống triển khai nhiều JVM.

Điều này **không** có nghĩa toàn bộ class của ứng dụng, toàn bộ Java heap hoặc mã máy đã JIT compile đều được lưu sẵn trong một archive CDS kiểu truyền thống.

### 2.2. AppCDS — mở rộng từ Java 10

**JEP 310** đưa **application class-data sharing** vào OpenJDK/HotSpot ở JDK 10. Điểm mới cốt lõi không phải thay đổi ngôn ngữ Java, mà là mở rộng những **class đủ điều kiện được lưu chia sẻ**, đặc biệt các class đến từ ứng dụng và JAR thư viện.

Trước khi có các tiện ích được bổ sung sau này, workflow cơ bản của AppCDS là:

~~~text
Chạy ứng dụng để thu class list
        |
        v
Tạo shared archive tĩnh (static dump)
        |
        v
Chạy ứng dụng tương thích và nạp archive
~~~

Workflow **static archive** kiểu này vẫn có thể sử dụng trên các JDK hiện hành. Tuy nhiên, nếu trình bày Java 10 như thể nó đã có **dynamic archive**, **AOTCacheOutput** hay **method profiles được lưu từ lần training**, đó là sai mốc phiên bản.

### 2.3. `.jsa` không phải `.jar`

- **JAR** chứa bytecode và tài nguyên mà ứng dụng cần để chạy.
- **CDS/AppCDS archive** thường dùng phần mở rộng `.jsa`; đây là dữ liệu chia sẻ được HotSpot chuẩn bị theo format riêng.
- `java -jar app.jar` là lệnh chạy ứng dụng; `java -jar app.jsa` **không phải** cách dùng archive.
- Archive là **artifact tối ưu**. Nó không thay thế JAR nguồn, không phải backup và không bảo đảm ứng dụng tiếp tục hoạt động nếu mã gốc/JAR bị xóa.

## 3. Bảng dòng thời gian: tính năng nào xuất hiện khi nào?

| Mốc | Cơ chế / JEP | Điều được bổ sung | Chú ý hiện nay |
| --- | --- | --- | --- |
| **JDK 10** | **JEP 310 — Application Class-Data Sharing** | Cho phép đưa class của ứng dụng/thư viện vào CDS archive | Nền tảng AppCDS **vẫn có giá trị** |
| **JDK 12** | **JEP 341 — Default CDS Archives** | Đóng gói default CDS archive cho các class lõi vào JDK trên những nền tảng hỗ trợ | Nhiều JDK hiện đại dùng default archive khi điều kiện cho phép |
| **JDK 13** | **JEP 350 — Dynamic CDS Archives** | Tạo top-layer archive từ các class đã được nạp khi ứng dụng kết thúc | Giảm bước class-list thủ công |
| **Các JDK mới hơn** | **Auto-create CDS, runtime dump bằng `jcmd VM.cds`** | Cải thiện cách tạo/duy trì archive truyền thống | Dùng theo tài liệu của JDK triển khai |
| **JDK 24** | **JEP 483 — Ahead-of-Time Class Loading & Linking** | Đưa **AOT cache** vào HotSpot để lưu các artifact đã chuẩn bị trước (gồm class loading/linking và đối tượng phù hợp) | Thường qua training → assembly → production |
| **JDK 25** | **JEP 514 — AOT Command-Line Ergonomics** | Giúp tạo cache từ một lệnh `-XX:AOTCacheOutput` | Một lệnh người dùng, nhưng vẫn có bước assembly của JVM |
| **JDK 25** | **JEP 515 — AOT Method Profiling** | Lưu thông tin profile phương thức từ lần training để hỗ trợ JIT warm-up | **Profile**, không đồng nghĩa mọi mã máy đã được AOT compile |
| **JDK 26** | **JEP 516 — AOT Object Caching with Any GC** | Mở rộng cơ chế cache đối tượng để hoạt động với mọi GC được hỗ trợ, gồm ZGC | Không nên áp ràng buộc GC trước JDK 26 cho mọi phiên bản mới |

Mốc **JDK 27** tiếp tục có tài liệu về **CDS/AppCDS và AOT cache**. Chỉ áp dụng các khả năng/cờ mà **bản JDK cụ thể** ghi nhận; đừng sao chép một lệnh AOT của JDK 25 vào JDK 17 rồi cho rằng JVM sẽ tự hiểu.

## 4. So sánh theo bản chất dữ liệu được lưu

| Cơ chế | Artifact điển hình | Nội dung/đơn vị tối ưu | Mục đích chính |
| --- | --- | --- | --- |
| CDS truyền thống | Static `.jsa` | Dữ liệu class đã xử lý trước, chia sẻ được | Startup và memory sharing |
| AppCDS từ Java 10 | Static `.jsa` có cả class ứng dụng | Mở rộng tập class được lưu | Startup ứng dụng có nhiều class/JAR |
| Default CDS JDK 12+ | Default `.jsa` trong bản JDK | Các class cốt lõi mà JDK đã đóng gói sẵn | Lợi ích CDS mà không phải tạo archive ứng dụng |
| Dynamic CDS JDK 13+ | Dynamic top `.jsa` cộng base | Class tải trong lần chạy chuẩn bị, chưa nằm trong base và đủ điều kiện | Tránh tự thu class list riêng |
| AOT cache từ JDK 24 | `.aot` | Dữ liệu class và các thành phần **load/link** cùng artifact AOT khác theo JDK | Startup **và** warm-up tốt hơn |
| AOT cache JDK 25+ | `.aot` | Trên nền AOT cache còn có **method profiling** đã ghi trong training | Giúp JIT tối ưu sớm hơn |
| AOT cache JDK 26+ | `.aot` | Caching đối tượng có thể dùng với mọi GC được hỗ trợ | Mở rộng phạm vi runtime dùng tối ưu AOT |

Bảng này là **khung so sánh**, không phải tuyên bố mọi class hoặc đối tượng đều được lưu lại. Một class chưa từng được tải, class không đủ điều kiện, một nhánh tính năng không xuất hiện trong training, hoặc một cấu hình JVM không tương thích có thể không tận dụng được cache.

### Điều KHÔNG đúng

1. “AppCDS Java 10 đã lưu method-execution profiles để JVM warm-up tức thì” — **sai**; mốc đó thuộc các mở rộng AOT mới hơn.
2. “Dynamic CDS archive tồn tại từ JDK 10” — **sai**; JEP 350 được đưa vào JDK 13.
3. “Default CDS archive có nghĩa mọi class ứng dụng đã được đóng gói sẵn” — **sai**; default archive chủ yếu liên quan class JDK.
4. “AOT cache chỉ là đổi đuôi `.jsa` thành `.aot`” — **sai**; phạm vi tối ưu và quy trình khác.
5. “JDK 25 AOT method profiling tức là toàn bộ ứng dụng được compile thành native executable” — **sai**; HotSpot vẫn chạy JVM và tiếp tục JIT theo runtime.
6. “Tất cả JDK từ 10 trở đi đều hiểu `-XX:AOTCacheOutput`” — **sai**; dùng tính năng ở phiên bản được hỗ trợ.

## 5. Một ví dụ Java 17+ dùng để minh họa mọi chế độ

Lưu tệp **ArchiveLayersDemo.java**:

~~~java
import java.util.stream.IntStream;

public class ArchiveLayersDemo {
    static final class Stats {
        int sum() {
            return IntStream.rangeClosed(1, 5).sum();
        }
    }

    public static void main(String[] args) {
        int result = new Stats().sum();
        System.out.println("sum: " + result);
        System.out.println("valid: " + (result == 15));
    }
}
~~~

Biên dịch và đóng gói thành **app.jar**:

~~~bash
mkdir classes
javac -d classes ArchiveLayersDemo.java
jar --create --file app.jar -C classes .
java -cp app.jar ArchiveLayersDemo
~~~

Đầu ra của ứng dụng:

~~~text
sum: 15
valid: true
~~~

Đây là kết quả **độc lập với chế độ CDS/AOT**, miễn ứng dụng chạy thành công. Nó kiểm chứng logic chương trình, **không phải bằng chứng** archive đã được nạp. Tùy chọn logging của JVM có thể viết thêm các dòng lên stderr/stdout tùy cấu hình, vì vậy khi làm bài học nên phân biệt **hai dòng đầu ra nghiệp vụ** với **thông báo JVM**.

Lệnh đóng gói tạo JAR chứa `ArchiveLayersDemo.class` và `ArchiveLayersDemo$Stats.class`. Sử dụng JAR nhất quán giúp workflow CDS dễ kiểm soát classpath.

**Lưu ý phạm vi:** mã Java và lệnh đóng gói chạy trên JDK 17+. Những lệnh `AOTMode`/AOT cache ở phần sau **không dành cho JDK 17**, dù ứng dụng Java được dùng lại.

## 6. Vận hành AppCDS kiểu static archive trên JDK hiện đại

Nền tảng AppCDS từ JDK 10 có quy trình static class list → static dump → nạp archive. Với một bản **JDK 17+** hỗ trợ những tùy chọn dưới đây, bạn có thể thao tác theo dạng:

### 6.1. Thu danh sách class đã tải

~~~bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist -cp app.jar ArchiveLayersDemo
~~~

Lần này chương trình chạy để JVM ghi **app.classlist**. Tệp đó là **danh sách class**, không phải archive đã tối ưu.

### 6.2. Dump static CDS archive

~~~bash
java -Xshare:dump -XX:SharedClassListFile=app.classlist -XX:SharedArchiveFile=app-static.jsa -cp app.jar
~~~

Đây là **chế độ dump**: JVM tạo `app-static.jsa` từ thông tin phù hợp, **không chạy `main` của ứng dụng**. Một số class được yêu cầu có thể không đủ điều kiện để lưu; cần kiểm tra log nếu muốn biết mức bao phủ thực tế.

### 6.3. Nạp static archive

~~~bash
java -XX:SharedArchiveFile=app-static.jsa -cp app.jar ArchiveLayersDemo
~~~

`-XX:SharedArchiveFile` trong lệnh này là **đường dẫn archive khi chạy**. Nó cũng được dùng làm **đường dẫn ghi** ở bước `-Xshare:dump` — cùng cờ, khác chế độ.

Kiểm tra bằng:

~~~bash
java -Xlog:cds=info -Xlog:class+load=info -XX:SharedArchiveFile=app-static.jsa -cp app.jar ArchiveLayersDemo
~~~

**Không thể suy ra class đã được chia sẻ chỉ từ việc lệnh in `sum: 15`.** Bạn cần tìm những dòng log xác nhận archive được mở/map và class được load từ vùng chia sẻ.

### Static AppCDS vẫn còn hữu ích khi nào?

- Build pipeline muốn tự chủ bước tạo class list và archive.
- Cần artifact có thời điểm tạo rõ ràng, cố định theo JDK/app release.
- Hệ thống đã có quy trình AppCDS được chứng minh cải thiện performance.
- Muốn đối chiếu static archive với dynamic archive hoặc AOT cache một cách có kiểm soát.

Không nên xem static archive **mặc nhiên hiệu quả hơn mọi giải pháp mới**, vì hiệu năng phụ thuộc classpath, workload, JDK và cấu trúc archive.

## 7. JDK 12 — default CDS archive không phải AppCDS toàn ứng dụng

**JEP 341** khiến nhiều JDK đã đóng gói **default CDS archive** ngay lúc build, giúp các tiến trình Java tương thích tận dụng class JDK mà không phải tự chạy dump trước.

Ví dụ, chỉ với:

~~~bash
java -cp app.jar ArchiveLayersDemo
~~~

JVM có thể sử dụng default CDS archive khi JDK và điều kiện chạy cho phép. Có thể chủ động tắt để so sánh:

~~~bash
java -Xshare:off -cp app.jar ArchiveLayersDemo
~~~

Cần hiểu:

- Default archive **không tự chứa toàn bộ class** của mọi ứng dụng.
- Nó là **base phổ biến** cho một số quy trình dynamic archive.
- Sự tồn tại của default CDS archive phụ thuộc bản phân phối JDK và môi trường cụ thể; không nên tuyệt đối hóa “mọi JVM đều luôn bật”.
- Nếu JVM phải bỏ qua CDS do cấu hình không phù hợp, kết quả chức năng Java vẫn có thể bình thường.

Đây là **bổ sung về cách phân phối/khởi tạo archive**, khác với bước **mở rộng tập class ứng dụng** ở JDK 10.

## 8. JDK 13 — dynamic CDS archive: tạo kho từ một lần chạy

**JEP 350** thêm khả năng **dynamic archiving**: lấy các class được tải trong lần chạy, lưu phần phù hợp vào **dynamic top archive** khi tiến trình thoát. Cơ chế này bỏ bớt các bước thu class list thủ công.

### 8.1. Tạo dynamic archive

~~~bash
java -XX:ArchiveClassesAtExit=app-dynamic.jsa -cp app.jar ArchiveLayersDemo
~~~

Khi chương trình kết thúc và điều kiện dump phù hợp, JVM tạo `app-dynamic.jsa`. Archive này thường dựa vào **base CDS archive** của JDK.

### 8.2. Nạp dynamic archive ở lần tiếp theo

~~~bash
java -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveLayersDemo
~~~

So sánh với static:

| Tính chất | Static archive | Dynamic archive |
| --- | --- | --- |
| Cách thu class | Class list, dump được điều khiển riêng | Class được tải trong lần chạy training/dump |
| Cờ quan trọng | `DumpLoadedClassList`, `-Xshare:dump`, `SharedClassListFile` | `ArchiveClassesAtExit` |
| Tệp tạo ra | Static `.jsa` | Dynamic `.jsa` |
| Quan hệ với base | Có thể đóng vai trò static/base | Thường là top-layer dựa trên base |
| Lệnh sử dụng | `SharedArchiveFile=static.jsa` | `SharedArchiveFile=dynamic.jsa` |
| Khả năng tối ưu | Tùy JDK và tính năng | Theo tài liệu JDK mới, dynamic archive hỗ trợ **ít tối ưu hơn static** ở một số khía cạnh |

**Không nói** mọi class đã được load đều chắc chắn vào archive: JVM chỉ lưu các class thỏa điều kiện chia sẻ. Training không kích hoạt một nhánh code thì class chỉ được load ở nhánh đó cũng không được bảo đảm có trong dynamic archive.

### 8.3. Hai tầng base và top

Khi chỉ định custom base và dynamic top trên **Linux/macOS**:

~~~bash
java -XX:SharedArchiveFile=base.jsa:app-dynamic.jsa -cp app.jar ArchiveLayersDemo
~~~

Trên **Windows**, dùng dấu `;` giữa hai archive:

~~~powershell
java "-XX:SharedArchiveFile=base.jsa;app-dynamic.jsa" -cp app.jar ArchiveLayersDemo
~~~

`base.jsa` phải là **base archive hợp lệ đã được tạo**. Không thể tùy tiện lấy top archive được dump từ base A rồi chạy với một base B khác. Đường dẫn custom base, JDK và classpath phải tương thích.

Với dynamic archive tạo dựa trên default archive, người dùng thường chỉ cần chỉ định dynamic top như ví dụ ở 8.2; JVM có thể tìm default base từ metadata của archive.

## 9. Các tiện ích quản lý CDS về sau — vẫn thuộc họ `.jsa`

Bên cạnh luồng static/dynamic thủ công, các JDK mới còn có tiện ích giảm việc phải sửa script khởi động.

### 9.1. `-XX:+AutoCreateSharedArchive`

Theo tài liệu **JDK 25/27**, cách dùng:

~~~bash
java -XX:+AutoCreateSharedArchive -XX:SharedArchiveFile=app-auto.jsa -cp app.jar ArchiveLayersDemo
~~~

Hành vi chính theo hợp đồng của JDK nêu trên:

- Nếu archive hợp lệ đã tồn tại và tương thích JDK, JVM có thể **nạp archive đó**.
- Nếu archive chưa tồn tại, JVM có thể tạo **dynamic CDS archive khi kết thúc**.
- Nếu archive có từ một JDK build khác, việc thay thế tùy chính sách phiên bản archive. Tài liệu JDK 25 nêu điều kiện đặc biệt cho archive tạo bằng **JDK trước 19**: chúng không được tự thay thế như archive mới.
- Không có nghĩa một lần đầu đã “tự hưởng đầy đủ AppCDS”; archive được tạo ở cuối lần chạy sẽ có lợi từ lần chạy phù hợp tiếp theo.

Tính năng này **vẫn là CDS archive**, không phải AOT cache của JEP 483. Vì vậy file `app-auto.jsa` không tự trở thành file `app.aot`.

### 9.2. `jcmd VM.cds`

Với JDK hỗ trợ, có thể yêu cầu một JVM đang chạy tạo archive:

~~~bash
jcmd <pid> VM.cds static_dump app-static.jsa
~~~

Hoặc dynamic dump:

~~~bash
jcmd <pid> VM.cds dynamic_dump app-dynamic.jsa
~~~

Theo tài liệu JDK 25, **dynamic_dump** đòi hỏi JVM đích khởi động với `-XX:+RecordDynamicDumpInfo`. Đây là ví dụ cú pháp mô tả; thay `<pid>` bằng PID thật trước khi chạy.

Lợi ích là có thể dump từ quy trình đang chạy mà không phải lúc nào cũng sửa trực tiếp lệnh tạo ứng dụng. Tuy nhiên việc hỗ trợ `jcmd`, quyền attach process và điều kiện dump phụ thuộc JDK, nền tảng, cấu hình bảo mật/containment. Dùng nó theo tài liệu **JDK cụ thể**.

**Kết luận phần này:** auto-create và `jcmd` là **cách quản lý CDS/AppCDS dễ hơn**, không phải bằng chứng nội dung được cache giống các artifact AOT class linking/profiling.

## 10. JDK 24 — AOT cache: bước chuyển từ archive class sang artifact rộng hơn

**JEP 483 — Ahead-of-Time Class Loading & Linking** đưa **AOT cache** vào JDK 24. CDS truyền thống đã giảm một phần công việc **phân tích/chuẩn bị class**, nhưng nhiều công việc **loading, linking và chuẩn bị đối tượng runtime** vẫn có thể lặp ở mỗi lần khởi động.

AOT cache mở rộng loại thông tin có thể được chuẩn bị **trong một lần chạy training** và tái sử dụng trong lần chạy production. Các artifact phụ thuộc JDK có thể gồm:

- Class đã được chuẩn bị/tải và liên kết theo cơ chế hỗ trợ.
- Metadata/đồ thị phụ thuộc cần thiết để khởi tạo runtime nhanh hơn.
- Một số đối tượng Java phù hợp có thể được cache theo khả năng của JDK.
- Thông tin profile phương thức ở các phiên bản mới hơn (JDK 25+).

**Khác biệt căn bản:** `-XX:AOTCache=app.aot` không phải cách viết mới cho `-XX:SharedArchiveFile=app.jsa`. Hai lựa chọn thuộc những luồng công việc và tập tối ưu khác nhau. AOT cache vẫn chạy trên **HotSpot JVM**, không phải bản executable độc lập của một công cụ native-image.

### 10.1. Quy trình ba giai đoạn ở JDK 24

Tài liệu JDK 24 trình bày:

~~~text
Training (record) → AOT configuration
             ↓
Assembly (create) → AOT cache
             ↓
Production (load) → Chạy ứng dụng sử dụng cache
~~~

Lệnh cho cùng ví dụ `app.jar` (chạy trên **JDK 24**):

~~~bash
java -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -cp app.jar ArchiveLayersDemo
~~~

Khi training, ứng dụng **chạy bình thường** để JVM quan sát class và hành vi có ích cho cache. Tiếp đó tạo cache:

~~~bash
java -XX:AOTMode=create -XX:AOTConfiguration=app.aotconfig -XX:AOTCache=app.aot -cp app.jar ArchiveLayersDemo
~~~

Trong mode **create**, JVM thực hiện assembly để ghi `app.aot`, **không thực thi `ArchiveLayersDemo.main` theo cách của production**.

Sau khi cache được tạo:

~~~bash
java -XX:AOTCache=app.aot -cp app.jar ArchiveLayersDemo
~~~

Với một bản JDK phù hợp và cache hợp lệ, JVM có thể sử dụng `app.aot` để tăng hiệu quả startup. Các kết quả chức năng của `main` phải giữ nguyên.

**Các file không giống nhau:**

| File | Vai trò | Có thể đưa trực tiếp vào `SharedArchiveFile`? |
| --- | --- | --- |
| `app.aotconfig` | Dữ liệu cấu hình/thống kê từ lần training | Không |
| `app.aot` | AOT cache thành phẩm | Không; dùng `-XX:AOTCache` |
| `app-dynamic.jsa` | CDS archive | Dùng trong `-XX:SharedArchiveFile` |
| `app.jar` | Mã bytecode và tài nguyên ứng dụng | Không; dùng `-cp`/`-jar` |

### 10.2. Lưu ý về `AOTClassLinking`

JDK 24+ có tùy chọn `-XX:+AOTClassLinking` cho những tối ưu liên kết class tiên tiến hơn. Trong quy trình dùng `-XX:AOTMode`, JDK có thể bật tính năng này theo mặc định. Các tối ưu càng mạnh có thể càng cần **tính nhất quán** giữa lệnh training và production (module graph, JVM options, class loading/agent).

Không nên “cố ép tối ưu” khi có bytecode instrumentation, module options khác nhau hoặc các phụ thuộc runtime thay đổi mà chưa xác nhận tính tương thích. Hãy kiểm tra log AOT và startup behavior.

## 11. JDK 25 — giảm số lệnh tạo cache và lưu method profiles

### 11.1. JEP 514 — AOT Command-Line Ergonomics

Từ JDK 25, workflow phổ biến có thể được viết bằng **một lệnh tạo cache**:

~~~bash
java -XX:AOTCacheOutput=app.aot -cp app.jar ArchiveLayersDemo
~~~

Theo tài liệu JDK 25, khi truyền `AOTCacheOutput` trong chế độ tự động, JVM chạy ứng dụng để **training** và sau đó khởi động **một tiến trình JVM thứ hai** để thực hiện assembly. Người dùng không phải tự gõ cả hai lệnh record/create của workflow JDK 24.

Để dùng cache đã tạo:

~~~bash
java -XX:AOTCache=app.aot -cp app.jar ArchiveLayersDemo
~~~

**Điểm quan trọng:**

- `AOTCacheOutput` là **đích ghi cache** trong lần chuẩn bị.
- `AOTCache` là **đường dẫn cache đọc trong lần chạy sau** (và có vai trò tương ứng ở mode create cũ).
- Không đặt đồng thời `-XX:AOTCacheOutput` và `-XX:AOTCache` vào cùng lệnh để mong ghi rồi đọc một file.
- “Một lệnh” không có nghĩa chỉ có một giai đoạn logic: **training + assembly** vẫn diễn ra.

Chỉ dùng cú pháp này trên **JDK 25 trở lên có tài liệu hỗ trợ**; không chuyển nguyên vào Java 10/17/21.

### 11.2. JEP 515 — AOT Method Profiling

Cũng tại JDK 25, JVM có thể lưu **method-execution profiles** được thu thập trong lần training, rồi sử dụng ngay khi production bắt đầu. Điều này giúp JIT có thông tin về hành vi phương thức sớm hơn thay vì chờ ứng dụng đạt đủ tải mới thu được profile.

Phân biệt rõ:

- **Method profile**: thống kê/hình dạng lời gọi mà compiler dùng để ra quyết định tối ưu.
- **Compiled native method code**: mã máy đã được biên dịch.
- **Native executable**: chương trình có thể chạy độc lập mà không yêu cầu cùng mô hình JVM.

JEP 515 tập trung vào **method profiles**. Không được mô tả nó như việc Java 25 tự lưu **toàn bộ mã máy của mọi phương thức** hoặc tạo native executable. JVM vẫn có thể biên dịch JIT trong production và điều chỉnh khi dữ liệu thực khác lần training.

### 11.3. Vì sao “startup nhanh” khác “warm-up nhanh”?

- **Startup** thường đo từ lúc JVM bắt đầu tới khi ứng dụng sẵn sàng phục vụ.
- **Warm-up** liên quan tới thời gian/khối lượng công việc để các đường code đạt hiệu suất ổn định, gồm profiling và JIT.
- CDS/AppCDS nhắm mạnh tới công việc chuẩn bị **class**.
- AOT class loading/linking giảm thêm một số công việc trước khi ứng dụng phục vụ.
- Method profiling giúp **warm-up** ở những đường chạy được training.

Không có một con số tăng tốc áp dụng cho mọi ứng dụng. Cần benchmark trên workload thật, đồng thời tách **thời gian tới sẵn sàng** khỏi **độ trễ yêu cầu ban đầu**.

## 12. JDK 26 — object caching dùng được với nhiều GC

**JEP 516 — Ahead-of-Time Object Caching with Any GC** ở **JDK 26** cải thiện cách lưu/khôi phục đối tượng Java được cache để các tối ưu AOT liên quan tới object caching có thể hoạt động với mọi garbage collector được hỗ trợ, bao gồm **ZGC**.

Trước thay đổi này, cách biểu diễn/ánh xạ đối tượng vào heap có ràng buộc do một số GC có bố cục dữ liệu khác nhau. JEP 516 cho phép nạp trạng thái đối tượng theo cách phù hợp hơn với nhiều GC.

Điều đó **không có nghĩa**:

- Mọi object của ứng dụng đều được cache.
- Các object có trạng thái phụ thuộc runtime (socket, kết nối database, bí mật, file descriptor) tự nhiên trở thành dữ liệu cache an toàn.
- Mọi tùy chọn GC và JVM đều tương thích với bất kỳ cache cũ nào.
- Có thể đưa `app.aot` của JDK 26 lên JDK 17 và mong JVM hiểu.

**Hệ quả vận hành:** khi nâng JDK hoặc thay chiến lược GC, cần tạo và kiểm tra lại AOT cache trên runtime đích. Tính năng mở rộng hỗ trợ GC của JDK 26 không xóa bỏ các ràng buộc về app/JDK/OS/CPU.

## 13. Lựa chọn cách dùng theo phiên bản JDK

| Runtime mục tiêu | Lựa chọn cơ bản phù hợp | Không nên dùng |
| --- | --- | --- |
| **JDK 10** (bối cảnh lịch sử) | Hiểu nền tảng AppCDS static archive | Không gán dynamic archive hay AOT cache cho JDK 10 |
| **JDK 17/21** | Default CDS, static AppCDS hoặc dynamic AppCDS | Không dùng `AOTCacheOutput` |
| **JDK 24** | CDS/AppCDS còn dùng được; thêm AOT cache với record/create | Không lấy lệnh one-step của JDK 25 làm mặc định |
| **JDK 25** | Có thể ưu tiên AOT cache với `AOTCacheOutput`; method profiles hỗ trợ warm-up | Không xem method profiles là compiled native executable |
| **JDK 26+** | AOT cache tiếp tục mở rộng, bao gồm object caching với nhiều GC | Không tái dùng cache từ JDK/ứng dụng khác mà chưa kiểm tra |

Nếu đang vận hành một ứng dụng **Java 17 hoặc Java 21** và có AppCDS hoạt động tốt, không cần bỏ nó chỉ vì JDK mới có AOT cache: **tính năng của runtime đang chạy mới là giới hạn thực**. Nếu đã triển khai JDK 25/26/27, có thể thử AOT cache và so kết quả với AppCDS; lựa chọn dựa trên **đo lường ứng dụng thực**.

### Một cây quyết định ngắn

~~~text
JDK hiện tại có hỗ trợ AOT cache không?
  ├─ Không: dùng default CDS/AppCDS nếu workload hưởng lợi
  │    ├─ Muốn dump class list trước? → static AppCDS
  │    └─ Muốn tận dụng class đã load ở lần chạy? → dynamic AppCDS
  └─ Có: kiểm tra các điều kiện classpath, agent, JDK và môi trường
       ├─ Tương thích, startup/warm-up quan trọng? → thử AOT cache
       ├─ Không tương thích? → tối ưu bằng CDS/AppCDS hoặc chạy bình thường
       └─ Luôn đo baseline và xác minh cache thật sự được nạp
~~~

Không cần triển khai cả static `.jsa`, dynamic `.jsa` và `.aot` cùng lúc chỉ vì chúng đều tồn tại: thêm artifact đồng nghĩa thêm chi phí build, kiểm tra tương thích và bảo trì.

## 14. Tương thích: vì sao không thể sao chép archive tùy ý?

| Yếu tố | Rủi ro với AppCDS/`.jsa` | Rủi ro với AOT/`.aot` |
| --- | --- | --- |
| JDK build | Archive có thể không nạp khi đổi build | AOT cache gắn với JDK release/build và cách tối ưu tương ứng |
| JAR/classpath | JAR đổi làm dữ liệu class trong archive không còn hợp lệ | Cache gắn với tập class, đường dẫn và hành vi training của app |
| OS/CPU | Dữ liệu CDS phụ thuộc JVM/platform tương thích | AOT cache gắn với OS/CPU cụ thể |
| JVM/module flags | Một số option làm CDS mất hiệu lực | Một số option phá giả thiết class linking/cached objects |
| Java agents, instrumentation | Class được biến đổi có thể không đủ điều kiện chia sẻ | Cache AOT có thể không tương thích với class loading/instrumentation khác training |
| Cache/path permission | Không đọc được archive hoặc không ghi dump | Không đọc được cache hoặc không ghi training/assembly |
| Container image | Archive từ image/JDK cũ không khớp image mới | Cần build cache trên image/runtime tương thích |

**Nguyên tắc sản xuất:**

1. Coi archive/cache là **artifact của cặp JDK + ứng dụng** (và điều kiện OS/CPU, launch flags).
2. Giữ **classpath/module path và thư viện** nhất quán giữa training, tạo cache và production.
3. Tạo lại cache khi nâng JDK, đổi JAR hoặc thay đổi các tùy chọn ảnh hưởng class loading.
4. Đặt đường dẫn rõ ràng, bảo đảm quyền đọc archive trong runtime; đừng cho tiến trình không tin cậy ghi sửa cache.
5. Nếu có biến thể image/architecture, tạo cache theo từng biến thể phù hợp.
6. Không sửa `.jsa`/`.aot` bằng text editor hoặc đổi phần mở rộng để “chuyển định dạng”.

Một số hạn chế trong tài liệu Java 17/25 áp dụng cho classpath có thư mục không rỗng, module path, hoặc option như `--patch-module`. **Đọc tài liệu đúng phiên bản JVM** vì chi tiết hỗ trợ có thể thay đổi; không suy rộng nguyên trạng một hạn chế của JDK cũ ra mọi JDK tương lai.

## 15. Kiểm chứng bằng logging: CDS và AOT không dùng cùng một dấu hiệu

### 15.1. Kiểm tra CDS/AppCDS

~~~bash
java -Xlog:cds=info -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveLayersDemo
~~~

Khi cần theo dõi class:

~~~bash
java -Xlog:class+load=info -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveLayersDemo
~~~

Tìm thông tin archive được mở/map và class được nạp từ **shared objects file**. Các thông điệp log có thể thay đổi theo JDK, nên không hard-code một stdout cụ thể.

### 15.2. Kiểm tra AOT cache

Trên **JDK 25+**, sau khi có `app.aot`:

~~~bash
java -Xlog:aot -XX:AOTMode=auto -XX:AOTCache=app.aot -cp app.jar ArchiveLayersDemo
~~~

`AOTMode=auto` là lựa chọn phù hợp trong nhiều trường hợp production: khi cache không thể dùng, JVM có thể tiếp tục chạy mà không hưởng lợi từ cache theo hợp đồng của JDK.

Để **kiểm tra nghiêm ngặt trong QA**:

~~~bash
java -XX:AOTMode=on -XX:AOTCache=app.aot -cp app.jar ArchiveLayersDemo
~~~

Với JDK 25, `AOTMode=on` yêu cầu dùng được AOT cache; nếu không phù hợp JVM sẽ báo lỗi và dừng. **Không** coi nó là chế độ bắt buộc an toàn cho mọi production service có khả năng thêm JVM agent hoặc thay flags ở thời điểm deploy.

Tương tự, đối với CDS truyền thống:

~~~bash
java -Xshare:off -cp app.jar ArchiveLayersDemo
~~~

cho một baseline **không dùng CDS**, trong khi `-Xshare:on` chỉ nên dùng trong bối cảnh kiểm thử cưỡng chế. **`-Xshare` không phải alias của `AOTMode`**; hai nhóm tùy chọn thuộc các cơ chế và luồng khác nhau.

### 15.3. So sánh đúng

- **CDS**: xác minh archive được load và class được chia sẻ.
- **AOT**: xác minh cache được chấp nhận, các artifact AOT có thể dùng, không có thông báo mismatch.
- **Chức năng**: vẫn cần kiểm thử output/API nghiệp vụ độc lập tối ưu.
- **Hiệu năng**: đo nhiều lần, phân biệt cold/warm file cache, startup, warm-up, RSS/PSS và tài nguyên của các tiến trình JVM.

Đừng kết luận “AOT nhanh hơn AppCDS 50% trên mọi ứng dụng” từ một chương trình cực nhỏ. Mức tăng phụ thuộc workload, số class, profile training, dịch vụ mạng/database và version JVM.

## 16. Phương pháp benchmark công bằng

Một phép đo nên phân biệt:

| Nhóm | Cách chạy | Điều cần quan sát |
| --- | --- | --- |
| Không CDS | `java -Xshare:off -cp app.jar ArchiveLayersDemo` | Baseline về class sharing |
| CDS mặc định | `java -cp app.jar ArchiveLayersDemo` | Default JDK archive có thể được dùng |
| AppCDS cụ thể | `java -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar ArchiveLayersDemo` | Tác động archive chứa class ứng dụng |
| AOT cụ thể | `java -XX:AOTCache=app.aot -cp app.jar ArchiveLayersDemo` | Tác động AOT cache nếu JDK hỗ trợ |

Cần giữ nguyên **JDK**, **ứng dụng**, **cấu hình JVM**, **môi trường CPU/memory** trong cùng một lượt so sánh. Khi so **JDK 17 AppCDS** với **JDK 25 AOT**, nhiều thành phần khác cũng đã thay đổi (GC, compiler, class libraries); không thể quy mọi khác biệt cho cache.

Khuyến nghị đo:

1. **Startup time**: từ launch tới ứng dụng sẵn sàng thực sự phục vụ.
2. **Time to first request/first useful work**: trải nghiệm người dùng nhận kết quả đầu tiên.
3. **Warm-up curve**: độ trễ và throughput những lần request đầu tới khi ổn định.
4. **Bộ nhớ**: RSS/PSS, số instance, trang chia sẻ; không chỉ nhìn heap used.
5. **Chi phí tạo cache**: thời gian training, tài nguyên assembly và dung lượng artifact.
6. **Độ ổn định vận hành**: tốc độ và khả năng khởi động khi cache thiếu/sai.

Không bật logging quá chi tiết trong benchmark chính, vì ghi nhiều log có thể làm sai kết quả đo startup.

## 17. Các lỗi hiểu nhầm phổ biến

| Nhầm lẫn | Vì sao không đúng | Cách nhớ/sửa |
| --- | --- | --- |
| “AppCDS được thêm ở Java 13.” | JEP 310 thuộc **JDK 10**. | JDK 13 thêm **dynamic archives**, không thêm AppCDS từ đầu. |
| “Java 10 có `ArchiveClassesAtExit`.” | Dynamic dump được bổ sung sau ở JDK 13. | Dùng lệnh dynamic với JDK hỗ trợ. |
| “Mặc định có CDS nghĩa là AppCDS đã chứa mọi JAR.” | Default archive JDK chủ yếu có class nền tảng. | Archive ứng dụng cần chuẩn bị phù hợp. |
| “`.jsa` và `.aot` chỉ khác phần mở rộng.” | Nội dung/cache lifecycle và option khác. | CDS dùng `SharedArchiveFile`, AOT dùng `AOTCache`. |
| “AOT ở JDK 24 chỉ là static AppCDS.” | JEP 483 mở rộng class loading/linking và cache artifact. | Phân biệt mục tiêu và quá trình training. |
| “JDK 25 đã AOT compile toàn bộ method.” | JEP 515 lưu **method profiles** cho JIT. | Profile không đồng nghĩa native method code. |
| “`AOTCacheOutput` có trên Java 17.” | One-step ergonomics bắt đầu JDK 25. | Kiểm tra JDK trước khi đưa flag. |
| “JDK 26 vẫn chỉ cache được object với G1.” | JEP 516 mở rộng sang các GC khác, gồm ZGC. | Đọc tài liệu JDK 26+. |
| “AOT cache có thể dùng cho mọi JVM/mọi CPU.” | Cache gắn với JDK, app và OS/CPU. | Build và dùng trên runtime tương thích. |
| “Dữ liệu output đúng chứng tỏ CDS/AOT đã nạp.” | Output ứng dụng không chứa trạng thái archive. | Xem `-Xlog:cds`/`-Xlog:aot`. |
| “`-Xshare:off` là cách dùng AOT.” | Đây là tùy chọn điều khiển CDS. | Đọc đúng nhóm cờ và mode. |
| “Bắt buộc cache bằng mọi giá giúp production an toàn hơn.” | Strict mode có thể làm JVM không khởi động. | Dùng auto/fallback và log; fail-fast trong QA khi cần. |
| “Training một lần đại diện mọi tính năng.” | Class/đường code chưa được kích hoạt có thể không vào cache. | Thiết kế kịch bản training phù hợp. |
| “Đổi JAR nhưng giữ archive cũ không sao.” | Classpath/artifact mismatch có thể vô hiệu cache. | Tạo lại trong build pipeline. |
| “Cache chứa bí mật runtime có thể chia sẻ vô điều kiện.” | Đối tượng/cấu hình runtime có ràng buộc an toàn. | Chỉ dùng cơ chế được JVM hỗ trợ, bảo vệ artifact. |
| “Dùng cùng cách dump cho mọi JDK mới.” | Tính năng và tùy chọn thay đổi theo JDK. | Gắn mỗi lệnh với phiên bản hỗ trợ. |

## 18. Bài tập tự kiểm tra

### Câu 1 — Java 10 mở rộng điều gì?

**Hỏi:** Một người nói “AppCDS Java 10 tự động tạo dynamic archive khi ứng dụng thoát”. Đúng không?

**Đáp án:** Không. JEP 310 ở **JDK 10** mở rộng class-data sharing tới class ứng dụng; **dynamic archiving bằng `ArchiveClassesAtExit`** thuộc JEP 350 ở **JDK 13**.

### Câu 2 — default CDS archive

**Hỏi:** Từ JDK 12 có default CDS archive thì có cần chuẩn bị archive ứng dụng riêng không?

**Đáp án:** Không bắt buộc đối với việc chạy ứng dụng, nhưng **default archive không đồng nghĩa đã chứa tất cả class ứng dụng**. Nếu muốn tối ưu class của ứng dụng, hãy đánh giá AppCDS hoặc AOT cache tùy JDK.

### Câu 3 — chọn artifact

**Hỏi:** Có `app-dynamic.jsa` và `app.aot`. Nên dùng cùng cờ `-XX:SharedArchiveFile` để nạp cả hai không?

**Đáp án:** Không. CDS archive dùng `-XX:SharedArchiveFile`, còn AOT cache dùng `-XX:AOTCache` trên JDK hỗ trợ. Không tráo file.

### Câu 4 — JDK 24 cần bao nhiêu bước?

**Hỏi:** Ở JDK 24, AOT cache training và assembly có thể được biểu diễn bằng những mode nào?

**Đáp án:** `-XX:AOTMode=record` với `-XX:AOTConfiguration` cho training, sau đó `-XX:AOTMode=create` kết hợp configuration và cache output cho assembly; production nạp cache bằng `-XX:AOTCache`.

### Câu 5 — JDK 25 giảm số bước ra sao?

**Hỏi:** `-XX:AOTCacheOutput=app.aot` có nghĩa không cần training nữa không?

**Đáp án:** Không. JVM vẫn chạy **training** rồi thực hiện **assembly** (có thể qua một JVM thứ hai). JEP 514 chỉ làm quy trình thao tác đơn giản hơn.

### Câu 6 — method profile và native code

**Hỏi:** JEP 515 nghĩa là toàn bộ phương thức đã được biên dịch thành mã máy trong `.aot`?

**Đáp án:** Không. Nó bổ sung **method-execution profile** giúp JIT lập kế hoạch tối ưu sớm; đừng đánh đồng profile với native compiled code hoặc native executable.

### Câu 7 — nâng JDK/GC

**Hỏi:** Nâng ứng dụng từ JDK 25 sang JDK 26 với ZGC có thể giữ nguyên `app.aot` không?

**Đáp án:** Không giả định được. JEP 516 hỗ trợ object caching với nhiều GC hơn, nhưng archive/cache vẫn gắn với JDK/runtime và app. Cần tạo, kiểm thử lại cache cho deployment đích.

### Câu 8 — lỗi AOT không nạp

**Hỏi:** Dùng `-XX:AOTMode=auto` ở production mà AOT cache không tương thích thì điều gì quan trọng?

**Đáp án:** Theo tài liệu JDK 25, JVM có thể tiếp tục chạy **không sử dụng cache**; vì thế cần **log/metrics** để biết hiệu năng có đang hưởng lợi. Với `AOTMode=on` trong QA, lỗi không tương thích có thể khiến JVM dừng để fail-fast.

### Câu 9 — nhiều tầng archive

**Hỏi:** Với custom static base và dynamic top, viết cú pháp Windows ra sao?

**Đáp án:**

~~~powershell
java "-XX:SharedArchiveFile=base.jsa;top.jsa" -cp app.jar ArchiveLayersDemo
~~~

Trên Linux/macOS dùng dấu `:` giữa hai archive, không dùng `;`.

## 19. Checklist triển khai thực tế

Trước khi đưa một archive/cache vào production:

- [ ] Xác nhận **phiên bản JDK**, kiến trúc và tập JVM options thực tế.
- [ ] Chọn đúng **CDS/AppCDS** hay **AOT cache**; không tráo `.jsa`/`.aot`.
- [ ] Ghi lại đường dẫn và phiên bản **JAR, classpath, module path**.
- [ ] Dùng training đủ đại diện, nhưng không làm việc có tác động nguy hiểm lên dữ liệu production.
- [ ] Tạo archive/cache với đúng JDK và ứng dụng sẽ deploy.
- [ ] Tạo checksum/artifact version nếu cần truy vết và supply-chain security.
- [ ] Đảm bảo quyền đọc trong runtime, quyền ghi trong build/training, không để người không tin cậy thay thế archive.
- [ ] Kiểm tra **`-Xlog:cds`** hoặc **`-Xlog:aot`** tương ứng.
- [ ] Đảm bảo ứng dụng chạy đúng khi **không có cache**, nếu đây là chiến lược fallback.
- [ ] Đo startup, time-to-first-response, warm-up và bộ nhớ so với baseline.
- [ ] Thiết kế tái tạo cache khi đổi JDK, ứng dụng, classpath hoặc image.
- [ ] Ghi rõ chính sách xử lý lỗi cache trong QA và production.

## 20. Tóm tắt và tài liệu chính thức

**Nhớ theo mốc:**

- **JDK 10 — JEP 310:** AppCDS thêm **class ứng dụng** vào khả năng chia sẻ class.
- **JDK 12 — JEP 341:** JDK có **default CDS archive** đóng gói sẵn trong những bản dựng hỗ trợ.
- **JDK 13 — JEP 350:** **Dynamic CDS archive** tạo từ các class đã load, trên base archive.
- **JDK 24 — JEP 483:** **AOT cache** mở rộng quá trình chuẩn bị trước sang class loading/linking và artifact tối ưu khác.
- **JDK 25 — JEP 514/515:** **Tạo cache gọn hơn** và **lưu method profiles** cho warm-up.
- **JDK 26 — JEP 516:** **Object caching** sử dụng được với nhiều GC hơn, kể cả ZGC.

**Nhớ theo cờ:**

| Cơ chế | Cờ chủ yếu để tạo | Cờ chủ yếu để sử dụng |
| --- | --- | --- |
| Static CDS | `-Xshare:dump` + `SharedArchiveFile` | `-XX:SharedArchiveFile=...jsa` |
| Dynamic CDS | `-XX:ArchiveClassesAtExit=...jsa` | `-XX:SharedArchiveFile=...jsa` |
| Auto-create CDS (JDK hỗ trợ) | `-XX:+AutoCreateSharedArchive` + `SharedArchiveFile` | Dùng cùng cặp cờ khi nạp lại |
| AOT cache JDK 24 | `AOTMode=record` rồi `AOTMode=create` | `-XX:AOTCache=...aot` |
| AOT cache JDK 25+ | `-XX:AOTCacheOutput=...aot` | `-XX:AOTCache=...aot` |

**Tài liệu chuẩn:**

1. [JEP 310 — Application Class-Data Sharing (JDK 10)](https://openjdk.org/jeps/310).
2. [JEP 341 — Default CDS Archives (JDK 12)](https://openjdk.org/jeps/341).
3. [JEP 350 — Dynamic CDS Archives (JDK 13)](https://openjdk.org/jeps/350).
4. [JEP 483 — Ahead-of-Time Class Loading & Linking (JDK 24)](https://openjdk.org/jeps/483).
5. [JEP 514 — Ahead-of-Time Command-Line Ergonomics (JDK 25)](https://openjdk.org/jeps/514).
6. [JEP 515 — Ahead-of-Time Method Profiling (JDK 25)](https://openjdk.org/jeps/515).
7. [JEP 516 — Ahead-of-Time Object Caching with Any GC (JDK 26)](https://openjdk.org/jeps/516).
8. [Oracle JDK 17 — `java` launcher / AppCDS](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#application-class-data-sharing).
9. [Oracle JDK 25 — CDS và Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
10. [Oracle JDK 26 — các thay đổi hiệu năng/AOT](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html).
11. [Oracle JDK 27 — `java` launcher, các tùy chọn CDS/AOT hiện hành](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).
12. [dev.java — CDS and AppCDS in HotSpot](https://dev.java/learn/jvm/cps-appcds/).

**Kết luận:** AppCDS Java 10 là **bước mở rộng phạm vi chia sẻ dữ liệu class**. Các tính năng về sau lần lượt giải quyết **cách đóng gói sẵn archive**, **cách tạo archive động**, và cuối cùng là **lưu thêm các công việc tối ưu hóa trước khi chạy** thông qua AOT cache. Hãy chọn cơ chế theo **JDK thực tế, artifact được hỗ trợ và mục tiêu startup/warm-up**, không chỉ dựa vào tên gọi “archive” hay phần mở rộng tệp.

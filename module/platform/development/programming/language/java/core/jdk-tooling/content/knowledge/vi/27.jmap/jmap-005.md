# Live object trong Java heap với jmap

**Live object** là đối tượng mà garbage collector (GC) vẫn xem là có thể truy cập tại thời điểm kiểm tra heap. Một object thường còn live khi tồn tại đường tham chiếu từ GC root tới object đó. Ví dụ, object được giữ trong static field, trong collection còn được ứng dụng sử dụng, hoặc trong stack của một thread đang chạy có thể tiếp tục tồn tại trong heap.

Trong công cụ `jmap`, tùy chọn `live` giới hạn histogram hoặc heap dump vào tập object còn live. Tùy chọn này hữu ích khi điều tra memory leak, vì nó tập trung vào những object vẫn được giữ lại sau khi GC loại bỏ các object không còn reachable.

Cần phân biệt object còn live với object đang được xử lý ngay lúc này. Một object có thể không còn cần cho nghiệp vụ nhưng vẫn live vì một cache, listener, static collection hoặc thread vô tình giữ tham chiếu tới nó. Đây là một trong những nguyên nhân phổ biến khiến heap tăng liên tục.

## 1. Object được xem là live như thế nào?

GC không quyết định object có live chỉ dựa vào việc biến trong source code còn nằm trong phạm vi khai báo hay không. JVM xác định tập object có thể truy cập từ các **GC root** và các quy tắc reachability của Java.

Các nguồn tham chiếu thường gặp gồm:

- Local reference còn được JVM giữ trong stack frame của thread đang chạy.
- Static field của class đã được nạp.
- JNI global/local reference do mã native giữ.
- Thread đang hoạt động, monitor và một số cấu trúc nội bộ của JVM.
- Object khác còn reachable và đang giữ tham chiếu tới object cần xét.

Ví dụ:

~~~java
static final List<Object> CACHE = new ArrayList<>();

public static void keep(Object value) {
    CACHE.add(value);
}
~~~

Object được thêm vào `CACHE` vẫn reachable qua static field và collection, nên GC không thể thu hồi nó khi collection còn giữ tham chiếu. Nếu ứng dụng thêm liên tục mà không loại bỏ phần tử cũ, số live object có thể tăng theo thời gian.

Ngược lại:

~~~java
public static void createTemporaryObjects() {
    List<byte[]> temporary = new ArrayList<>();
    for (int i = 0; i < 1000; i++) {
        temporary.add(new byte[1024]);
    }
}
~~~

Sau khi phương thức kết thúc và không còn tham chiếu nào khác tới các array, chúng có thể trở thành unreachable và được GC thu hồi ở một chu kỳ sau. Việc object trở thành unreachable không đồng nghĩa bộ nhớ được trả lại ngay lập tức; GC quyết định thời điểm thu hồi.

Java còn có các loại reachability liên quan tới `SoftReference`, `WeakReference` và `PhantomReference`. Quy tắc xử lý reference ảnh hưởng tới thời điểm object bị coi là có thể thu hồi. Vì vậy, “live” là kết quả theo quy tắc reachability/reference processing của JVM tại lần kiểm tra, không phải nhãn nghiệp vụ do ứng dụng tự gán.

## 2. Vì sao cần lọc live object?

Một histogram toàn heap có thể bao gồm cả object chưa được GC thu hồi dù đã không còn reachable. Histogram live giúp tập trung vào những object vẫn còn được giữ lại.

| Câu hỏi | Dữ liệu phù hợp |
|---|---|
| Heap đang chứa bao nhiêu instance của từng class, kể cả object chưa thu hồi? | Histogram all objects |
| Sau khi loại object không còn reachable, class nào vẫn chiếm nhiều instance? | Histogram live objects |
| Object nào đang giữ một lượng lớn object khác? | Live heap dump và phân tích reference graph/dominator tree |
| Class nào tăng số instance qua nhiều lần chạy workload tương đương? | So sánh live histogram hoặc nhiều heap dump |

Live object đặc biệt hữu ích khi điều tra memory leak do cache tăng không giới hạn, listener/callback không được unregister, ThreadLocal giữ object, classloader cũ sau redeploy, session không hết hạn hoặc buffer bị giữ bởi một graph tham chiếu ngoài dự kiến.

Một histogram chỉ cho biết số instance và tổng shallow size theo class. Nó không chỉ ra ai đang giữ object. Để tìm nguyên nhân, cần mở heap dump bằng công cụ phân tích và lần theo đường tham chiếu tới GC root.

## 3. Xem histogram live bằng jmap

`jmap` là công cụ dòng lệnh trong JDK để xem thông tin heap của một Java process. Xác định PID trước bằng:

~~~sh
jcmd -l
~~~

Hoặc:

~~~sh
jps -l
~~~

Lệnh xem histogram chỉ gồm live object:

~~~sh
jmap -histo:live <pid>
~~~

Ví dụ:

~~~sh
jmap -histo:live 18360
~~~

Kết quả thường có các cột:

~~~text
 num     #instances         #bytes  class name (module)
-------------------------------------------------------
   1:          5000          80000  com.example.CacheEntry
   2:          1200          38400  java.lang.String
   3:           250          20000  byte[]
Total          6450         138400
~~~

Ý nghĩa:

- `num`: thứ tự class trong histogram.
- `#instances`: số instance của class.
- `#bytes`: tổng shallow size của các instance class đó.
- `class name`: tên class; có thể kèm module.

Đây là output minh họa. Số lượng, kích thước và thứ tự class phụ thuộc JVM, workload, collector và thời điểm lấy histogram.

`#bytes` là tổng kích thước trực tiếp của các object thuộc class đó, không phải retained heap. Retained heap là lượng bộ nhớ chỉ có thể được giải phóng nếu một object hoặc nhóm object giữ chúng bị loại khỏi graph; muốn đánh giá giá trị này cần công cụ phân tích heap dump.

Có thể ghi histogram ra file:

~~~sh
jmap -histo:live,file=live-histogram.txt <pid>
~~~

Tùy chọn `parallel=<number>` điều chỉnh số thread kiểm tra theo khả năng của JVM. Giá trị 1 tắt xử lý song song; giá trị 0 để VM tự chọn số thread. Không cần thay đổi tùy chọn này nếu chưa có lý do đo đạc cụ thể.

## 4. So sánh all objects và live objects

Không có `live` thì `jmap -histo` đếm toàn bộ object mà heap inspection nhìn thấy, kể cả object chưa được thu hồi dù đã unreachable. Có thể ghi rõ `all`:

~~~sh
jmap -histo <pid>
jmap -histo:all <pid>
jmap -histo:live <pid>
~~~

| Lệnh | Phạm vi |
|---|---|
| `jmap -histo <pid>` | Tất cả object trong heap theo snapshot |
| `jmap -histo:all <pid>` | Tất cả object trong heap |
| `jmap -histo:live <pid>` | Chỉ object được xem là live |

Ví dụ, một ứng dụng vừa tạo 100.000 object tạm thời rồi bỏ tham chiếu, đồng thời vẫn giữ 5.000 object trong một static array. Histogram all có thể cho thấy:

~~~text
#instances    class name
100000        HeapProbe$DeadRecord
  5000        HeapProbe$LiveRecord
~~~

Sau khi kiểm tra live-only:

~~~text
#instances    class name
  5000        HeapProbe$LiveRecord
~~~

`DeadRecord` không còn xuất hiện trong histogram live vì chúng không còn reachable và đã bị GC thu hồi trong quá trình xác định tập live. Kết quả cụ thể phụ thuộc thời điểm GC và workload; nếu GC đã thu hồi object trước khi chạy histogram all, hai lần đo có thể gần giống nhau.

Live-only inspection có thể yêu cầu GC để xác định tập object còn reachable. Việc này có thể gây pause hoặc ảnh hưởng latency. Hãy cân nhắc tải heap, collector và thời điểm thực hiện trước khi chạy trên production.

## 5. Tạo heap dump chỉ chứa live object

Histogram cho biết class nào có nhiều instance. Nếu cần biết object nào đang giữ object khác, tạo heap dump ở định dạng HPROF để phân tích reference graph.

Dump chỉ các live object:

~~~sh
jmap -dump:live,format=b,file=heap-live.hprof <pid>
~~~

Dump toàn bộ object:

~~~sh
jmap -dump:all,format=b,file=heap-all.hprof <pid>
~~~

Ví dụ với PID:

~~~sh
jmap -dump:live,format=b,file=C:/diagnostics/heap-live.hprof 18360
~~~

| Tùy chọn | Ý nghĩa |
|---|---|
| `live` | Chỉ ghi object được xem là live |
| `all` | Ghi tất cả object trong heap |
| `format=b` | Dùng định dạng HPROF binary |
| `file=<path>` | Đường dẫn file heap dump |
| `gz=<level>` | Ghi dump nén với mức 1–9 |

Nếu không chỉ định `live` hoặc `all`, `jmap -dump` mặc định dump tất cả object. Nếu cả hai được truyền, `live` được ưu tiên theo help của JDK hiện hành.

Heap dump có thể rất lớn và làm tiến trình tạm dừng trong lúc thu thập. Hãy bảo đảm đủ dung lượng ổ đĩa và chọn thư mục có quyền ghi. Không ghi đè dump cũ nếu chưa xác nhận file đó không còn cần cho điều tra.

## 6. Phân tích heap dump

Sau khi có file HPROF, mở bằng công cụ tương thích, ví dụ Eclipse Memory Analyzer (MAT) hoặc một heap analyzer phù hợp với phiên bản dump. Các bước thường dùng:

1. Mở file `heap-live.hprof`.
2. Xem histogram để tìm class có nhiều instance hoặc tổng shallow size lớn.
3. Mở dominator tree để tìm object giữ lại phần lớn heap.
4. Chọn instance đáng ngờ và xem incoming references.
5. Dùng chức năng “Path to GC Roots” để tìm đường tham chiếu từ GC root tới object.
6. Xác định collection, static field, thread, ThreadLocal, listener hoặc classloader đang giữ object.
7. Đối chiếu với source code và lifecycle của thành phần sở hữu tham chiếu.
8. Sửa nguyên nhân giữ object, sau đó lặp lại workload và so sánh heap snapshot.

Ví dụ: histogram cho thấy hàng triệu `com.example.Session` instance. Trong dominator tree, một static `ConcurrentHashMap` giữ phần lớn session. Path to GC Roots có thể chỉ ra map thuộc singleton service. Khi đó cần xem logic hết hạn/xóa session và lifecycle của map.

Đừng chỉ dựa vào số instance lớn để kết luận memory leak. Một cache có giới hạn, pool hoặc registry có thể giữ object có chủ đích. Hãy kiểm tra tốc độ tăng, retained heap, giới hạn cấu hình và hành vi sau khi workload kết thúc.

## 7. Ví dụ Java 17+: tạo object live và object tạm

Ví dụ sau giữ 5.000 `LiveRecord` trong static field, đồng thời tạo 100.000 `DeadRecord` rồi bỏ tham chiếu. Chương trình giữ JVM chạy để bạn có thời gian lấy histogram.

Tạo file `HeapProbe.java`:

~~~java
public class HeapProbe {
    static Object[] keep;

    public static void main(String[] args) throws InterruptedException {
        keep = new Object[5_000];
        for (int i = 0; i < keep.length; i++) {
            keep[i] = new LiveRecord(i);
        }

        Object[] temporary = new Object[100_000];
        for (int i = 0; i < temporary.length; i++) {
            temporary[i] = new DeadRecord(i);
        }
        temporary = null;

        System.out.println("heap-probe-ready");
        Thread.sleep(120_000);
    }

    static class LiveRecord {
        final int id;
        LiveRecord(int id) { this.id = id; }
    }

    static class DeadRecord {
        final int id;
        DeadRecord(int id) { this.id = id; }
    }
}
~~~

Biên dịch bằng Java 17 trở lên:

~~~sh
mkdir -p out
javac --release 17 -d out HeapProbe.java
~~~

Chạy chương trình:

~~~sh
java -Xms256m -Xmx256m -cp out HeapProbe
~~~

Stdout chính xác:

~~~text
heap-probe-ready
~~~

Mở terminal thứ hai, tìm PID:

~~~sh
jcmd -l
~~~

Giả sử PID là `18360`. Chạy histogram all trước:

~~~sh
jmap -histo:all 18360
~~~

Sau đó chạy live-only:

~~~sh
jmap -histo:live 18360
~~~

Trong một lần kiểm thử với JDK 24.0.2, histogram all ghi nhận 100.000 `HeapProbe$DeadRecord` và 5.000 `HeapProbe$LiveRecord`. Histogram live chỉ còn 5.000 `HeapProbe$LiveRecord`. Kích thước byte và tổng số class khác có thể thay đổi theo JDK, kiến trúc và môi trường.

Khi hoàn tất, quay lại terminal chạy `HeapProbe` và nhấn `Ctrl+C` để dừng tiến trình.

## 8. Dùng jcmd thay cho jmap

Oracle đánh dấu `jmap` là công cụ experimental và unsupported, có thể không còn trong các bản JDK tương lai. Tài liệu troubleshooting khuyến nghị dùng `jcmd` cho chẩn đoán hiện đại vì có giao diện diagnostic command mới hơn và giảm overhead trong nhiều tình huống.

Histogram live-only bằng `jcmd`:

~~~sh
jcmd <pid> GC.class_histogram
~~~

Theo JDK 24, mặc định command này không yêu cầu `-all`, nên chỉ kiểm tra object live. Để bao gồm cả object unreachable:

~~~sh
jcmd <pid> GC.class_histogram -all
~~~

Heap dump live-only:

~~~sh
jcmd <pid> GC.heap_dump heap-live.hprof
~~~

Heap dump tất cả object:

~~~sh
jcmd <pid> GC.heap_dump -all heap-all.hprof
~~~

`GC.heap_dump` mặc định yêu cầu full GC trước khi dump, trừ khi dùng `-all`. Các command `GC.class_histogram` và `GC.heap_dump` có impact cao, phụ thuộc kích thước và nội dung heap. Hãy xem mô tả command trước khi chạy:

~~~sh
jcmd <pid> help GC.class_histogram
jcmd <pid> help GC.heap_dump
~~~

Nếu command không có trên phiên bản JDK đích, kiểm tra help của chính JVM đó và tài liệu phiên bản tương ứng. Không giả định mọi JDK đều có cùng option.

## 9. Tác động và lưu ý khi lấy live heap

Việc xác định live set có thể cần GC hoặc thao tác heap inspection ở safepoint. Tác động có thể gồm:

- Pause ứng dụng trong lúc JVM kiểm tra heap hoặc thực hiện full GC.
- Tăng CPU và I/O trong thời gian tạo histogram/dump.
- Tăng dung lượng file tạm và áp lực lên ổ đĩa.
- Thay đổi trạng thái heap do object unreachable được thu hồi trong quá trình kiểm tra.
- Ảnh hưởng latency của service, đặc biệt khi heap lớn hoặc traffic cao.

Trên JDK 24, `jcmd GC.class_histogram` được đánh dấu Impact: High; `GC.heap_dump` cũng có Impact: High và mặc định yêu cầu full GC trừ khi chọn `-all`. Vì vậy, ưu tiên chạy trong cửa sổ bảo trì hoặc trên replica/staging khi có thể. Nếu phải lấy dữ liệu production, hãy phối hợp với người vận hành và theo dõi pause/latency.

Một live heap dump vẫn có thể chứa rất nhiều dữ liệu nhạy cảm: token, password, session, thông tin cá nhân, payload request và dữ liệu nghiệp vụ. “Live” không có nghĩa là dữ liệu an toàn để chia sẻ. Hạn chế quyền đọc, mã hóa khi lưu/chuyển, không tải lên nơi công khai và xóa theo chính sách lưu trữ.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích đúng |
|---|---|
| Live object là object vừa được tạo | Tuổi object không quyết định live; khả năng reachable mới quan trọng |
| Object không còn dùng trong nghiệp vụ sẽ tự động chết | Nếu vẫn còn tham chiếu từ GC root, object vẫn live |
| Biến ra khỏi scope nghĩa là object được thu hồi ngay | Object có thể chỉ trở thành eligible for GC; thời điểm thu hồi do GC quyết định |
| `-histo:live` và `-histo` luôn cho cùng kết quả | Histogram all có thể còn chứa object unreachable chưa bị GC thu hồi |
| Histogram cho biết object nào giữ memory | Histogram chỉ thống kê class/instance/bytes; cần heap dump và reference analysis |
| `#bytes` là retained heap | Đây là tổng shallow size theo class, không phải retained size |
| Live heap dump không chứa dữ liệu nhạy cảm | Object live có thể chứa secret và dữ liệu người dùng |
| `jmap` là công cụ được hỗ trợ lâu dài | Oracle đánh dấu jmap experimental/unsupported và khuyến nghị jcmd |

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jmap: command not found` | Chỉ cài JRE hoặc PATH thiếu JDK bin | Cài JDK và kiểm tra PATH/`JAVA_HOME` |
| Không kết nối được PID | PID sai, JVM đã dừng hoặc quyền attach không phù hợp | Xác định PID lại, dùng cùng user phù hợp và xem lỗi attach |
| Không thấy class mong đợi trong histogram live | Object đã unreachable và bị GC thu hồi | Kiểm tra histogram all và đường tham chiếu trong workload |
| Histogram all và live gần như giống nhau | GC đã thu hồi object tạm trước khi đo hoặc phần lớn object vẫn reachable | Lặp lại workload có kiểm soát và đo gần thời điểm tạo object |
| Heap dump không tạo được file | Không đủ quyền ghi, thư mục không tồn tại hoặc thiếu dung lượng | Chọn đường dẫn hợp lệ, kiểm tra quyền và dung lượng đĩa |
| Heap dump rất lớn | Heap lớn hoặc đang dump all objects | Dùng live dump khi phù hợp, cân nhắc nén và dung lượng lưu trữ |
| Ứng dụng bị pause khi lấy dump | GC/heap inspection có thể gây pause và I/O | Lấy dump trong cửa sổ phù hợp, theo dõi impact và cân nhắc replica |
| Không mở được HPROF | File ghi dở, thiếu dung lượng hoặc analyzer không tương thích | Xác minh file hoàn tất và dùng công cụ hỗ trợ HPROF |
| Windows báo thiếu `dbgeng.dll` | Thiếu Debugging Tools for Windows trên cấu hình cần thành phần này | Cài thành phần phù hợp và kiểm tra PATH tới `jvm.dll` |
| jmap không phản hồi | JVM bị treo hoặc attach không hoàn tất | Dùng jcmd nếu có thể; với core dump, xem `jhsdb jmap` theo tài liệu JDK |

## 12. Quy trình điều tra memory leak bằng live object

1. Xác định đúng JVM và PID bằng `jcmd -l` hoặc công cụ hệ điều hành.
2. Ghi nhận heap usage, workload và thời điểm lấy mẫu.
3. Chạy histogram live để xác định class có số instance hoặc shallow size lớn.
4. Lấy live heap dump khi cần tìm object graph.
5. Dùng dominator tree và Path to GC Roots để xác định reference giữ object.
6. Đối chiếu với cache, collection, listener, ThreadLocal, thread và classloader trong source.
7. Kiểm tra object có được giữ có chủ đích hay do lifecycle/cleanup bị thiếu.
8. Sửa nguyên nhân, chạy lại workload tương đương và so sánh histogram/dump.
9. Xác nhận số live object và retained heap ổn định sau khi tải kết thúc.
10. Bảo vệ và xóa heap dump theo chính sách dữ liệu.

### Checklist

- [ ] Đã xác định đúng PID của JVM cần phân tích.
- [ ] Đã hiểu live object là object reachable theo quy tắc GC.
- [ ] Đã phân biệt histogram all và histogram live.
- [ ] Đã hiểu `#bytes` là shallow size, không phải retained heap.
- [ ] Đã dùng live heap dump khi cần phân tích reference graph.
- [ ] Đã xem tác động GC, pause, CPU, I/O và dung lượng file.
- [ ] Đã dùng dominator tree/Path to GC Roots để tìm object giữ lại heap.
- [ ] Đã đối chiếu với lifecycle và mục đích của cache/collection.
- [ ] Đã cân nhắc dùng `jcmd` thay cho jmap.
- [ ] Đã bảo vệ heap dump vì có thể chứa dữ liệu nhạy cảm.

`jmap -histo:live` và `jmap -dump:live` giúp tập trung vào object mà GC vẫn xem là reachable. Kết hợp histogram, heap dump và phân tích đường tham chiếu tới GC root sẽ giúp tìm class hoặc collection đang giữ object quá lâu, từ đó xác định nguyên nhân memory leak và kiểm chứng hiệu quả sau khi sửa.

## Tài liệu tham khảo

- [Oracle JDK 24 — The jmap Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmap.html)
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle JDK 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 24 — Troubleshooting Memory Leaks](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-memory-leaks.html)
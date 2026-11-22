# 13.3 Bật NativeMemoryTracking từ lúc khởi động với `summary` hoặc `detail`

## 1. Native Memory Tracking (NMT) dùng để làm gì?

**Native Memory Tracking (NMT)** là khả năng chẩn đoán của **HotSpot JVM** để thống kê bộ nhớ do chính JVM quản lý: heap được đặt chỗ và commit, metadata lớp, thread stack, JIT code cache, cấu trúc GC, vùng cấp phát nội bộ và một số nguồn cấp phát native khác. NMT giúp trả lời các câu hỏi:

- JVM đã **reserve** và **commit** bao nhiêu bộ nhớ theo từng nhóm?
- Nhóm nào tăng dần theo thời gian, dù Java heap có vẻ ổn định?
- Nếu cần đào sâu, những **native allocation call site** hoặc vùng địa chỉ ảo nào đang đóng góp vào mức tăng?
- Sau khi ứng dụng warm up, bộ nhớ thay đổi bao nhiêu giữa hai thời điểm?

Bài này tập trung vào **bật NMT ngay từ khi khởi động JVM** bằng `-XX:NativeMemoryTracking=summary` hoặc `-XX:NativeMemoryTracking=detail`; sau đó xác nhận cấu hình và đọc bằng `jcmd`. Đây là công cụ phân tích **bộ nhớ native phía HotSpot**, không phải heap profiler hay trình phát hiện mọi rò rỉ bộ nhớ trong tiến trình.

**Giới hạn quan trọng:** NMT không bao phủ đầy đủ cấp phát trực tiếp của thư viện native bên thứ ba, mã JNI không đi qua bộ cấp phát được HotSpot theo dõi, hay mọi phần bộ nhớ của thư viện JDK. Vì vậy, kết quả NMT **không đồng nhất** với RSS, bộ nhớ container hay toàn bộ address space của tiến trình. Các số liệu phải được đối chiếu với hệ điều hành khi nghi ngờ native leak ngoài JVM.

## 2. Vì sao phải bật từ lúc khởi động?

HotSpot mặc định đặt NMT ở `off` để tránh chi phí theo dõi. Chọn cấp độ bằng **JVM startup option**:

```text
-XX:NativeMemoryTracking=off
-XX:NativeMemoryTracking=summary
-XX:NativeMemoryTracking=detail
```

Theo tài liệu HotSpot (JDK 17–26), `jcmd VM.native_memory` **đọc được** kết quả đã theo dõi, tạo baseline, in diff và có thể **tắt** NMT, nhưng **không thể bật lại NMT đã off hoặc nâng summary thành detail trong cùng JVM**. Khi cần NMT ở mức cao hơn, phải sửa tùy chọn khởi động và **restart JVM** theo quy trình vận hành phù hợp. Nếu xảy ra sự cố lúc NMT đang off, không có cách hồi tố để dựng lại allocation history từ các cấp phát đã qua.

| Cấp độ lúc khởi động | Thu thập được | Câu hỏi phù hợp | Giới hạn |
| --- | --- | --- | --- |
| `off` (mặc định) | Không duy trì NMT | Chạy khi không cần NMT | `jcmd` không thể lấy báo cáo NMT hữu ích. |
| `summary` | Tổng hợp theo subsystem/category, `malloc`/`mmap`/`arena`, reserved/committed | Nhóm nào đang tăng? JVM có tăng native memory hay không? | Không đủ dữ liệu để truy chi tiết call site. |
| `detail` | Toàn bộ dạng summary **và** native allocation call sites, bản đồ virtual memory/committed regions | Allocation site nào tăng? Vùng native nào tạo khác biệt? | Theo dõi và báo cáo chi tiết hơn, có thể làm tăng CPU, RAM, thời gian lấy dump và dung lượng output. |

NMT làm thay đổi profile hiệu năng và bản thân NMT cũng dùng bộ nhớ; tài liệu Oracle đưa ra mức tác động tham khảo **5–10% hiệu năng**, tùy workload/build. Không coi con số này là cam kết cho mọi cấu hình: hãy benchmark ứng dụng thực khi đưa vào môi trường có yêu cầu latency nghiêm ngặt. `detail` nên dùng có mục tiêu khi `summary` đã chỉ ra nhóm bất thường nhưng chưa đủ bằng chứng.

**Quy tắc lựa chọn:** lần đầu điều tra thường dùng `summary` vì dễ đọc; khi cần định vị native C/C++ call sites thì chủ động chạy lại với `detail` ngay từ startup. Không có thao tác `jcmd` nào biến dữ liệu summary cũ thành detail một cách chính xác.

## 3. Các cách khởi động JVM với NMT

### 3.1 Ứng dụng Java chạy trực tiếp

```bash
java -XX:NativeMemoryTracking=summary -Xms256m -Xmx1g -jar application.jar
```

Đổi sang `detail` khi điều tra sâu:

```bash
java -XX:NativeMemoryTracking=detail -Xms256m -Xmx1g -jar application.jar
```

Chỉ chọn **một** trong hai mức cho một lần chạy. `-Xms`/`-Xmx` trong ví dụ là cấu hình heap minh họa, không phải điều kiện bắt buộc để sử dụng NMT. Các tùy chọn `-XX` phải nằm **trước** `-jar` hoặc tên main class:

```bash
# Sai mục đích: đối số bên phải application.jar được chuyển vào main(String[] args)
java -jar application.jar -XX:NativeMemoryTracking=summary
```

Dòng trên có thể làm ứng dụng nhận một đối số lạ trong khi **NMT của JVM vẫn không được bật**.

### 3.2 Chạy bằng classpath

```bash
java -XX:NativeMemoryTracking=summary -cp out com.example.Main
```

Không cần code Java gọi API NMT. Tùy chọn `-XX:NativeMemoryTracking` được JVM xử lý **trước khi `main` chạy**. Cú pháp này áp dụng cho các ứng dụng dùng HotSpot/OpenJDK tương thích, gồm cả executable Spring Boot JAR khi khởi chạy bằng `java -jar`.

### 3.3 Ứng dụng container

Đặt tùy chọn trong câu lệnh khởi động Java thực sự của container. Ví dụ hình thức `exec` trong Dockerfile:

```dockerfile
ENTRYPOINT ["java", "-XX:NativeMemoryTracking=summary", "-jar", "/app/application.jar"]
```

Nếu runtime được khởi chạy bằng script hoặc cấu hình orchestration, kiểm tra **câu lệnh cuối cùng** (entrypoint, args, environment) để chắc chắn cờ đã đến Java process. Có thể đặt `JAVA_TOOL_OPTIONS=-XX:NativeMemoryTracking=summary` trong môi trường phù hợp, nhưng biến này ảnh hưởng **mọi JVM** kế thừa biến môi trường đó, bao gồm tác vụ build/tool phụ; ghi rõ phạm vi và thử trước. Tránh vô tình bật `detail` trên tất cả dịch vụ.

Trong container, cần phân biệt **PID nhìn từ container** với PID nhìn từ host. `jcmd` phải nhìn thấy JVM cùng PID namespace, có Java tool đủ tương thích và quyền attach. Không suy ra PID từ tên pod hoặc service.

### 3.4 In báo cáo khi JVM thoát bình thường

Có thể bật thêm diagnostic options để HotSpot in NMT cuối vòng đời tiến trình:

```bash
java -XX:NativeMemoryTracking=summary \
     -XX:+UnlockDiagnosticVMOptions \
     -XX:+PrintNMTStatistics \
     -jar application.jar
```

Ví dụ trên dùng cú pháp tiếp dòng của shell Unix; trên Windows PowerShell hãy gõ tất cả tùy chọn trên **một dòng** hoặc dùng cú pháp tiếp dòng riêng của PowerShell. `-XX:+UnlockDiagnosticVMOptions` và `-XX:+PrintNMTStatistics` là để in thống kê lúc thoát; **không bắt buộc** khi chỉ muốn bật `summary`/`detail` rồi đọc bằng `jcmd`. Khi bị `SIGKILL`, container OOM kill hoặc hệ điều hành kết thúc tiến trình đột ngột, đừng trông chờ báo cáo shutdown này luôn xuất hiện.

## 4. Xác minh đúng JVM đang chạy

Trước khi phân tích, kiểm tra version, PID, JVM options và trạng thái NMT **trên ứng dụng đích**:

```bash
java -version
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> help VM.native_memory
jcmd <PID> VM.native_memory summary scale=MB
```

Thay `<PID>` bằng số PID thực tế được liệt kê, không gõ nguyên dấu `<` và `>`. `java -version` ở terminal chỉ mô tả binary được shell dùng; lệnh `jcmd <PID> VM.version` mới xác nhận runtime của **process cần điều tra**. `VM.command_line` hoặc `VM.flags` giúp xác minh flag NMT có được đưa vào startup, kể cả khi cấu hình đến từ launcher/script.

Khi NMT chưa bật, JVM có thể trả thông báo tương đương “Native memory tracking is not enabled”. Đây là lỗi **cấu hình khởi động**, không phải bug của `jcmd`. Khi NMT được bật ở mức `summary`, lệnh `detail` không tự tạo ra các call sites còn thiếu. Đọc output thực tế của JDK đang dùng và dùng `jcmd <PID> help VM.native_memory` để xem cú pháp công cụ tương ứng.

**Vấn đề quyền:** công cụ `jcmd` thường cần cùng máy/namespace và user đủ quyền attach; ảnh hưởng của `-XX:+DisableAttachMechanism`, container PID namespace, bản JDK thiếu `jcmd` hoặc hạn chế bảo mật có thể khiến lệnh thất bại dù NMT đã bật. Khi gặp lỗi attach, xử lý quyền/quy trình triển khai theo chính sách thay vì kết luận ngay “NMT off”.

## 5. `summary`: đọc tổng hợp và phân biệt reserved với committed

Bắt đầu bằng:

```bash
jcmd <PID> VM.native_memory summary
jcmd <PID> VM.native_memory summary scale=MB
```

Bạn sẽ thấy dòng `Total` và các category. Cấu trúc khái quát:

```text
Native Memory Tracking:
Total: reserved=..., committed=...
- Java Heap (reserved=..., committed=...)
- Class (reserved=..., committed=...)
- Thread (reserved=..., committed=...)
- Code (reserved=..., committed=...)
- GC (reserved=..., committed=...)
- Other (reserved=..., committed=...)
...
```

Đây chỉ là **sơ đồ vị trí trường**; tên nhóm, số lượng nhóm và các chi tiết `malloc`/`mmap` khác nhau giữa JDK, GC, nền tảng và cấu hình. Để xem số thật phải chạy `jcmd` trên JVM đích.

- **Reserved**: dải địa chỉ ảo JVM đã đặt chỗ; không đồng nghĩa số byte RAM vật lý đang dùng. Ví dụ khi `-Xmx` lớn, Java Heap có thể reserve vùng lớn dù chưa commit hết.
- **Committed**: phần bộ nhớ đã được hệ điều hành cam kết cấp phát theo quan sát NMT. Đây vẫn **không chính xác bằng RSS**: committed không có nghĩa mọi trang đã cư trú trong RAM vật lý ở thời điểm đọc.
- **`malloc`**: bộ nhớ phân bổ qua các đường cấp phát native mà NMT theo dõi; output có thể kèm số lần/phần tử cấp phát.
- **`mmap`**: các vùng địa chỉ ảo dựa trên mapping/reservation, thường liên quan Java Heap, class space, code cache và vùng JVM khác.
- **`arena`**: quản lý bộ nhớ theo chunk để cấp phát ngắn hạn; đừng dùng số lượng arena làm số byte rò rỉ từng Java object.

Một số category thường gặp:

| Category | Nội dung cần xem | Ví dụ hướng điều tra tiếp |
| --- | --- | --- |
| `Java Heap` | Heap reserved/committed, chịu ảnh hưởng `-Xms`/`-Xmx` và GC | Đối chiếu `GC.heap_info`, heap usage, GC logs; NMT không profile từng Java object. |
| `Class` | Metaspace, class space, metadata lớp | Classloader, dynamic class generation, class unloading, `VM.classloader_stats`/`VM.metaspace`. |
| `Thread` | Cấu trúc thread, native stack reservation/commit | Số platform thread, stack size, thread creation; không suy số live thread chính xác chỉ từ byte. |
| `Code` | JIT-generated code/code cache | Tình trạng compilation và code cache. |
| `GC` | Native structures của garbage collector | Collector đang dùng, số CPU/heap, cấu hình GC và cấu trúc hỗ trợ. |
| `Compiler` | Tài nguyên của C1/C2/JIT compiler | Warm up, hoạt động biên dịch, chu kỳ tăng/giảm sau khởi động. |
| `Internal`, `Other` | Các phân bổ được HotSpot theo dõi nhưng khó gán vào category chuyên biệt | Xem `detail` và tài liệu của build cụ thể; tránh quy ngay “Other = leak”. |
| `Native Memory Tracking` | Bộ nhớ dành cho chính bộ đếm/tracker | Là overhead của quá trình quan sát. |
| `Symbol`, `Arena Chunk`, `Module`, `Logging`… | Cấu trúc vận hành JVM | Theo dõi chiều tăng qua các mốc; category có thể xuất hiện/thay đổi theo JDK. |

**Sai lầm hay gặp:** lấy `Total reserved` làm RAM đang dùng, hoặc tính `Total committed` trừ `Java Heap committed` rồi gọi phần dư là “toàn bộ native memory của process”. Cách trừ này chỉ cho phần non-heap **nằm trong phạm vi NMT**, không bao gồm toàn bộ cấp phát không được HotSpot theo dõi.

## 6. `detail`: nhìn native call site và bản đồ virtual memory

Muốn biết **allocation site phía JVM** liên quan đến tăng bộ nhớ, JVM phải được khởi động với `detail`:

```bash
java -XX:NativeMemoryTracking=detail -jar application.jar
```

Khi chạy:

```bash
jcmd <PID> VM.native_memory detail scale=KB
```

Ngoài các category như `summary`, báo cáo có thể bao gồm:

- **Virtual memory map**: dải địa chỉ reserved/committed với nguồn gọi HotSpot liên quan.
- **Call-site allocation statistics**: tổng phân bổ theo các điểm cấp phát native, đôi khi hiện ký hiệu C/C++/địa chỉ tùy build và symbols.
- **Phân rã theo `malloc`/`mmap` và vùng commit**: giúp phát hiện phần nào của một category tăng.

“Call site” ở đây **không phải Java stack trace của từng đối tượng**. NMT không trả về chuỗi phương thức Java đã gọi `new` như heap profiler. Nếu nghi heap leak cần heap dump/profiler; nếu nghi JNI hoặc thư viện C cấp phát ngoài HotSpot, cần OS/native tools hoặc profiler phù hợp.

Báo cáo `detail` thường dài; nên lưu artifact có **mốc thời gian, PID, build JDK và chế độ NMT**. Dùng `detail.diff` sau baseline để tập trung vào phần tăng, thay vì cuộn từng địa chỉ trong báo cáo tổng.

**Không thể chuyển cấp độ bằng câu lệnh đọc:** JVM chạy `summary` có thể cung cấp `summary`/`summary.diff`; muốn `detail`/`detail.diff` đầy đủ phải restart với `NativeMemoryTracking=detail`.

## 7. Baseline và diff: phân tích xu hướng thay vì một ảnh chụp

Một snapshot NMT đơn lẻ cho biết hiện trạng; leak giả định cần **mức tăng lặp lại theo thời gian**. Sau khi ứng dụng warm up và trước khi bắt đầu pha tải cần đo, đặt baseline:

```bash
jcmd <PID> VM.native_memory baseline
```

Sau 5, 15 hoặc 30 phút chạy workload ổn định, lấy chênh lệch:

```bash
jcmd <PID> VM.native_memory summary.diff scale=MB
```

Nếu đã khởi động bằng `detail`, có thể dùng:

```bash
jcmd <PID> VM.native_memory detail.diff scale=KB
```

`summary.diff`/`detail.diff` hiển thị **giá trị hiện tại và phần tăng/giảm** so với baseline; ký hiệu cộng/trừ chỉ delta, không có nghĩa bản thân tổng hiện tại nhỏ hoặc lớn. Gọi `baseline` lần nữa sẽ thay mốc đối chiếu, vì vậy ghi lại thời điểm mốc và đừng vô tình reset baseline giữa lần đo.

Quy trình mẫu:

1. Chạy ứng dụng có NMT và xác nhận `VM.native_memory summary` hoạt động.
2. Cho ứng dụng warm up; ghi heap committed, RSS/working set, CPU, thread count, request rate, tải DB/network và collector.
3. Đặt `baseline` **sau warm up**; đánh dấu thời gian chính xác.
4. Chạy workload có kiểm soát; chụp `summary.diff` nhiều lần và lưu từng kết quả.
5. Nếu một category tăng bền vững qua nhiều chu kỳ dừng tải/GC mà không quay lại mức nền, chuyển sang điều tra sâu (ví dụ lần chạy `detail` mới).
6. Thử workload đối chứng và đối chiếu process-level RSS; xác minh tăng do cache hợp lệ, JIT, class loading, GC sizing hoặc memory pool trước khi gọi là leak.

**Không có ngưỡng tuyệt đối “delta dương = leak”.** JVM có thể tăng bộ nhớ bình thường trong pha warm up, compilation, mở rộng class metadata, GC hoặc connection pool. Với leak nhỏ cần quan sát lâu hơn; ứng dụng phải được kiểm tra khi tải và vòng đời đối tượng/tài nguyên tương đương.

## 8. Ví dụ Java 17+: thấy NMT trước và sau một cấp phát native

Lưu chương trình độc lập sau thành **`NmtStartupDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;

public class NmtStartupDemo {
    private static volatile ByteBuffer retained;

    public static void main(String[] args) throws Exception {
        BufferedReader console =
                new BufferedReader(new InputStreamReader(System.in));

        System.out.println("READY");
        console.readLine();

        retained = ByteBuffer.allocateDirect(32 * 1024 * 1024);
        retained.put(0, (byte) 1);
        System.out.println("ALLOCATED");

        console.readLine();
        System.out.println("DONE");
    }
}
```

`ByteBuffer.allocateDirect` yêu cầu một direct buffer khoảng **32 MiB** nằm ngoài Java heap thông thường; `retained` giữ tham chiếu để buffer không đủ điều kiện bị thu hồi trong lúc đo. Ghi một byte để bảo đảm ít nhất phần đầu của buffer được chạm tới. Mã không đòi hỏi API preview; dùng **JDK 17+ và HotSpot** cho hướng dẫn NMT.

Biên dịch:

```bash
javac --release 17 NmtStartupDemo.java
```

**Terminal 1** — chạy ở chế độ `summary`:

```bash
java -XX:NativeMemoryTracking=summary -Xms128m -Xmx512m NmtStartupDemo
```

Chương trình in `READY` và **chờ Enter**. Trên **terminal 2**, tìm PID của `NmtStartupDemo` và đặt baseline:

```bash
jcmd -l
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline
```

Quay lại terminal 1, **nhấn Enter một lần** để cấp phát buffer. Khi thấy `ALLOCATED`, quay sang terminal 2:

```bash
jcmd <PID> VM.native_memory summary.diff scale=KB
```

Phân tích category có delta dương từ cấp phát; trên nhiều build HotSpot, direct buffer có thể xuất hiện dưới `Other`/`malloc`, nhưng **không cam kết output đúng một tên nhóm hoặc đúng 32.768 KB**: runtime có thêm các chi phí metadata và các cấp phát nền. Đối chiếu thay đổi trong `Total committed`, category và RSS; số phần trăm và địa chỉ không cố định.

Cuối cùng nhấn Enter lần thứ hai ở terminal 1 để thoát. Nếu người dùng nhấn Enter **hai lần**, các dòng stdout **do chương trình in**, theo thứ tự, là:

```text
READY
ALLOCATED
DONE
```

Lệnh `jcmd` trên terminal 2 tạo output riêng và không phải stdout của ứng dụng.

**Chạy lại bằng `detail`:** sau khi ứng dụng cũ đã thoát, dùng:

```bash
java -XX:NativeMemoryTracking=detail -Xms128m -Xmx512m NmtStartupDemo
```

Lặp lại thao tác baseline trước lần Enter đầu tiên, sau đó dùng:

```bash
jcmd <PID> VM.native_memory detail.diff scale=KB
```

So sánh thông tin call sites xuất hiện ở `detail` mà `summary` không cung cấp. Đây là mô phỏng giáo dục, không phải bài đo leak: buffer được giữ cố ý trong thời gian ngắn, rồi tài nguyên của process được hệ điều hành thu hồi khi thoát. Trên hệ thống thiếu console tương tác, `readLine()` có thể nhận EOF và kết thúc sớm; chạy trong terminal tương tác để lặp lại đúng các bước.

## 9. Vận hành thật: từ dấu hiệu đến hành động

### Trường hợp A — Container bị OOM kill, Java heap chưa đầy

**Quan sát:** `-Xmx` có vẻ nhỏ hơn container memory limit, nhưng RSS vẫn tăng. **Thao tác:** bật `summary` từ lần deploy kế tiếp; thu NMT theo thời gian và kết hợp cgroup/container memory, RSS, thread stacks, native libraries và memory mappings. Nếu `Total committed` trong NMT tăng tương ứng, tìm category; nếu RSS tăng mà NMT ổn định, mở rộng điều tra sang thư viện native/JNI/allocator và OS page mappings.

**Không kết luận:** NMT thấp không chứng minh tiến trình không tiêu thụ bộ nhớ; phạm vi tracker có giới hạn.

### Trường hợp B — `Thread` tăng dần sau mỗi đợt request

**Giả thuyết:** platform threads tăng, thread lifecycle hoặc pool/config không giải phóng. **Thao tác:** so sánh NMT `Thread` với thread dump, số OS threads, pool executor và stack size. `reserved` của stack có thể lớn hơn đáng kể `committed`. Không dùng NMT như nguồn duy nhất đếm virtual thread và không giả định mỗi virtual thread có một OS stack riêng.

### Trường hợp C — `Class` tăng, heap không tăng tương ứng

**Giả thuyết:** tăng metaspace/classloaders, proxy/bytecode generation, hot reload hoặc các classloader không được giải phóng. **Thao tác:** so sánh `Class`, `VM.classloader_stats`, `VM.metaspace`, số lớp tải và lịch sử deployment; khi cần nguồn native chính xác có thể chạy `detail`. Class metadata tăng một thời gian sau startup có thể bình thường.

### Trường hợp D — `Code` hoặc `GC` tăng sau warm up

**Giả thuyết:** code cache của JIT/GC structures được cấp phát theo nhu cầu. **Thao tác:** giữ cố định JDK, collector, `-Xms/-Xmx`, thời gian warm up và tải; đọc delta qua các giai đoạn. Nếu đường biểu diễn dần phẳng ra và bộ nhớ còn trong hạn mức, chưa có bằng chứng leak.

### Trường hợp E — `Other` tăng ổn định, `summary` không đủ giải thích

**Thao tác:** lưu snapshot, tạo môi trường tái hiện và **restart với `detail`**; lấy baseline sau warm up, tái hiện workload, gọi `detail.diff`. Nếu call sites HotSpot không tăng nhưng RSS vẫn tăng, nghiên cứu native allocations ngoài NMT. Không dựa vào nhãn `Other` để khẳng định lỗi nằm ở ứng dụng hoặc thư viện cụ thể.

## 10. Những lỗi vận hành và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra / xử lý |
| --- | --- | --- |
| `VM.native_memory` báo NMT chưa bật | Startup thiếu flag, flag nằm sau `-jar`, cấu hình chỉ sửa nhưng process chưa restart | Xem `VM.command_line`/`VM.flags`, chỉnh Java command và restart. |
| `detail` không có call sites | Process chỉ bật `summary` | Chạy lại với `-XX:NativeMemoryTracking=detail`; không tự “nâng cấp” bằng `jcmd`. |
| `summary.diff` lỗi hoặc không có baseline | Chưa gọi `baseline` trong JVM hiện tại | Gọi `baseline` sau warm up rồi thu diff; baseline không tồn tại qua process restart. |
| `jcmd` không attach được | Khác user/PID namespace, không có công cụ trong image, attach bị chặn, không phải JVM HotSpot hỗ trợ | Kiểm tra PID namespace, user, Java version, `jcmd -l` và chính sách runtime. |
| `Total reserved` rất lớn | Heap/class space đặt chỗ địa chỉ ảo lớn | So sánh `committed`, RSS, `-Xmx`, cgroup; reserved khác RAM thực dùng. |
| NMT không giải thích được RSS tăng | Ngoài phạm vi JVM tracking, native library, OS mappings hoặc RSS khác committed | Dùng `pmap`/`smaps` trên Linux, process memory tools, native profiler và metric hệ điều hành. |
| Kết quả thay đổi khi nâng JDK/GC | Category, allocation implementation và cấu hình GC khác nhau | So sánh cùng workload, build, GC và flags; tránh so bằng một con số không đủ ngữ cảnh. |
| Dừng NMT bằng `VM.native_memory shutdown` | Tracker bị tắt trong process hiện tại | Muốn theo dõi lại thì restart process với flag NMT. |

Đừng bỏ qua chi phí đo: `detail` có thể gây overhead và output lớn, đặc biệt khi thu liên tục. Với tiến trình quan trọng, cân nhắc mức `summary`, tần suất chụp và khoảng thời gian đo, rồi tái hiện `detail` trên staging khi cần phân tích sâu. Báo cáo NMT cũng có thể chứa địa chỉ/native symbol nhạy cảm với môi trường chạy; lưu trong nơi kiểm soát truy cập.

## 11. Phân biệt NMT với các thước đo bộ nhớ khác

| Dữ liệu | Đo/quan sát gì? | Có trả lời trực tiếp “NMT summary/detail” không? |
| --- | --- | --- |
| NMT `reserved` | Không gian địa chỉ ảo HotSpot đã đặt chỗ | Có; không phải RAM vật lý. |
| NMT `committed` | Bộ nhớ HotSpot cam kết cấp phát | Có; không hoàn toàn bằng RSS. |
| Java heap used | Byte của object còn trong heap theo GC/runtime | Không; dùng heap/GC metrics hoặc heap profiler. |
| RSS / working set | Những trang của process đang cư trú ở RAM theo OS | Không; dùng OS/container metrics. |
| cgroup container memory | Bộ nhớ bị tính vào giới hạn container | Không; kiểm tra cgroup/monitoring. |
| malloc của JNI/native third-party | Cấp phát ngoài khả năng quan sát HotSpot NMT | Thường không; dùng native allocation profiler hoặc OS tool. |
| Buffer pool (direct/mapped) | Thống kê pool từ `BufferPoolMXBean` | Độc lập; phối hợp để giải thích các buffer allocations. |

Ví dụ khi Java heap `reserved=1GiB` và `committed=256MiB`, phép cộng **1 GiB + số native committed** sẽ phóng đại RAM đã tiêu thụ vì 1 GiB là địa chỉ ảo reserved. Ngược lại, chỉ nhìn heap used có thể bỏ sót Thread Stack, GC, Code Cache hoặc native library allocation. Một quyết định vận hành tốt phải nhìn đủ **heap usage, NMT delta, RSS/container metrics và tải ứng dụng**.

## 12. Checklist trước khi xác nhận đã bật NMT đúng

- [ ] Tùy chọn `-XX:NativeMemoryTracking=summary` hoặc `detail` được đặt **trước `-jar`/main class** trong Java command thực tế.
- [ ] Đã restart JVM sau khi sửa startup options và xác minh **runtime PID/JDK** đúng ứng dụng.
- [ ] `jcmd <PID> VM.command_line`/`VM.flags` xác nhận cấu hình; `VM.native_memory summary` trả báo cáo hợp lệ.
- [ ] Chọn `summary` cho phân tích category, `detail` khi thực sự cần call sites; biết không thể nâng mức theo dõi trong cùng process.
- [ ] Hiểu `reserved` khác `committed` và cả hai khác RSS; NMT có giới hạn bao phủ.
- [ ] Đã lưu phiên bản JDK/HotSpot, GC, `-Xms/-Xmx`, PID, OS/container, tải và thời điểm mỗi lần lấy mẫu.
- [ ] Đã đặt `baseline` sau warm up, thu `summary.diff` hoặc `detail.diff` nhiều lần trên workload có kiểm soát.
- [ ] Đã đo overhead với workload quan trọng, tránh thu báo cáo chi tiết quá dày.
- [ ] Nếu nghi native leak ngoài JVM, đã bổ sung OS/native metrics trước khi quy kết nguyên nhân.
- [ ] Nếu bật `PrintNMTStatistics`, hiểu rằng process bị kill đột ngột có thể không in báo cáo khi thoát.

## 13. Tài liệu chính thức để đối chiếu

1. Oracle Java 21 VM Guide, *Native Memory Tracking* — mô tả modes, `jcmd`, baseline, giới hạn bao phủ và thông tin lúc exit: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
2. Oracle Java 26 VM Guide, *Native Memory Tracking* — kiểm tra cùng cơ chế startup trên JDK hiện đại: https://docs.oracle.com/en/java/javase/26/vm/native-memory-tracking.html
3. Oracle Java 26 `jcmd` manual — cú pháp `VM.native_memory` và từng option: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html
4. Oracle Java 21 Troubleshooting Guide, *Diagnostic Tools* — category, `summary/detail`, `baseline/diff` và cách đọc ví dụ: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
5. Oracle `java` launcher options — cú pháp `-XX:NativeMemoryTracking` trên build cụ thể: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html

**Nguyên tắc thực hành:** chọn mức NMT ngay ở startup, xác minh trên đúng process, ghi baseline sau warm up và đối chiếu **delta theo category/call site** với metric hệ điều hành. NMT rất hữu ích để khoanh vùng phần bộ nhớ do HotSpot quản lý, nhưng không đủ để kết luận độc lập về mọi native leak hoặc RSS của ứng dụng.

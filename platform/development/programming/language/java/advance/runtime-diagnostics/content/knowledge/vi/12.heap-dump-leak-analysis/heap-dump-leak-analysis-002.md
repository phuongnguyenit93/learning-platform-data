# 12.2. Thu `GC.class_histogram` và hiểu số đối tượng, tổng byte theo lớp

## Mục tiêu

Sau bài học, bạn có thể:

1. Thu **class histogram** từ một JVM đang chạy bằng `jcmd <PID> GC.class_histogram`, lưu đầu ra để xem lại và hiểu phạm vi của số liệu.
2. Đọc đúng các cột `#instances`, `#bytes`, `class name`, `Total` và cách JVM sắp xếp các lớp.
3. Phân biệt **shallow size** (dung lượng trực tiếp của đối tượng) với **retained size** (dung lượng có thể thu hồi nếu giải phóng một đối tượng hoặc nhóm đối tượng).
4. Giải thích vì sao nhiều `byte[]`, `String`, collection hoặc số lượng instance tăng chưa đủ kết luận rò rỉ bộ nhớ.
5. So sánh các snapshot trong điều kiện tương đương và biết khi nào phải chuyển sang heap dump, GC log, JFR hoặc bộ đo native memory.

> **Trọng tâm:** `GC.class_histogram` trả lời câu hỏi “Đang có bao nhiêu đối tượng của từng lớp và chúng chiếm bao nhiêu byte trực tiếp trên Java heap?”. Nó **không** tự trả lời “Ai đang giữ những đối tượng này?” hoặc “Tại sao chúng chưa được GC?”.

## 1. Class histogram là gì?

Java heap chứa các **object instance** và **array** mà ứng dụng/JDK tạo ra. Class histogram duyệt heap và gom các đối tượng theo lớp runtime, rồi in thống kê tổng hợp:

- **Class:** tên kiểu đối tượng như `com.example.Order`, `java.lang.String`, `[B` (mảng `byte[]`).
- **Instance count:** số đối tượng thuộc lớp đó tại lần thu thập.
- **Bytes:** tổng kích thước **trực tiếp** (shallow bytes) của các đối tượng thuộc lớp đó.
- **Total:** tổng instance và tổng shallow bytes của các dòng được thống kê.

Công cụ là một *snapshot*, không phải chỉ số liên tục, cũng không cho biết tốc độ cấp phát. JVM có thể cấp phát nhiều đối tượng tạm thời rồi thu gom bình thường; bản histogram sau thu gom có thể không còn chúng.

**Phân biệt các công cụ:**

| Công cụ/dữ liệu | Trả lời tốt nhất câu hỏi nào? | Không trực tiếp cung cấp |
| --- | --- | --- |
| `GC.class_histogram` | Có bao nhiêu instance và bao nhiêu shallow bytes theo lớp? | GC root, graph tham chiếu, retained size, nơi cấp phát. |
| `GC.heap_info`/GC metrics | Dung lượng heap đang dùng, vùng heap/GC nói chung ra sao? | Đối tượng cụ thể nào giữ bộ nhớ. |
| `GC.heap_dump` + công cụ phân tích (ví dụ Eclipse MAT) | Đối tượng nào còn sống, chuỗi tham chiếu, dominator, retained size? | Xu hướng liên tục nếu chỉ có một lần dump. |
| JFR/Java Mission Control | Thời điểm và vị trí cấp phát, GC, hành vi runtime theo thời gian (tùy cấu hình ghi nhận)? | Bản đồ tham chiếu đầy đủ của mọi object như heap dump. |
| Native Memory Tracking | Vùng bộ nhớ native do JVM theo dõi dùng ở đâu? | Toàn bộ object graph Java heap hoặc bộ nhớ native của thư viện bên ngoài mà JVM không theo dõi. |

**Ví dụ thực tế:** `java.lang.String` có thể xuất hiện 100.000 instance với 2,4 MB shallow bytes, còn `[B` chiếm hàng chục MB. Điều đó không mâu thuẫn: đối tượng `String` giữ tham chiếu đến một `byte[]` chứa dữ liệu ký tự (JDK 9+ dùng compact strings tùy nội dung). Phần mảng được **tính ở dòng `[B`**, không cộng vào shallow size của dòng `String`.

## 2. Điều kiện chạy và cú pháp chính xác

`jcmd` nằm trong **JDK** (không đảm bảo có trong JRE/runtime image tối giản), gửi diagnostic command tới một tiến trình Java đang chạy. Sử dụng một bản JDK phù hợp với JVM đích; ví dụ thực hành bên dưới dùng **Java 17 trở lên**, cũng áp dụng với Java 21.

Đầu tiên xác định đúng PID:

```bash
java -version
jcmd -l
jcmd 12345 help GC.class_histogram
```

Trong ba lệnh trên, **`12345` chỉ là PID minh họa**. Thay bằng PID ứng dụng thực tế; không dùng mã thread, ID container hay PID của chính `jcmd`. Lệnh `help` của **JVM đích** là nguồn xác nhận các option được hỗ trợ ở phiên bản đang chạy.

Cú pháp:

```text
jcmd <PID> GC.class_histogram [options]
```

Ví dụ (Linux/macOS, Windows PowerShell hoặc `cmd.exe` đều hỗ trợ chuyển hướng `>`):

```bash
# Thống kê mặc định, ghi ra stdout:
jcmd 12345 GC.class_histogram

# Lưu stdout vào file trong terminal đang chạy jcmd:
jcmd 12345 GC.class_histogram > histo-01.txt

# Bao gồm cả object hiện không reachable:
jcmd 12345 GC.class_histogram -all > histo-all.txt

# Yêu cầu dùng tối đa khoảng 2 worker cho bước duyệt heap:
jcmd 12345 GC.class_histogram -parallel=2 > histo-parallel.txt
```

| Tùy chọn | Ý nghĩa và lưu ý |
| --- | --- |
| Không có option | Thống kê đối tượng được xem là **live/reachable** sau xử lý GC tương ứng của HotSpot; cách mặc định có thể yêu cầu **Full GC** trước khi kiểm kê. |
| `-all` | Kiểm kê **cả đối tượng không còn reachable** tại thời điểm quan sát. Đây không phải “chỉ live”; các đối tượng chờ thu gom có thể làm số liệu cao hơn. Trên HotSpot, chế độ này thường tránh bước yêu cầu Full GC của chế độ mặc định, nhưng vẫn phải quét heap nên vẫn tốn tài nguyên. |
| `-parallel=0` | Mặc định: để JVM tự chọn số luồng phục vụ heap inspection. |
| `-parallel=1` | Dùng một luồng kiểm kê, tắt song song hóa bước kiểm kê. |
| `-parallel=N` (N lớn hơn 1) | JVM **cố gắng** dùng số luồng được yêu cầu nhưng có thể ít hơn; không phải cam kết nhanh hơn hoặc không pause. |

**Cảnh báo vận hành:** tài liệu `jcmd` xếp `GC.class_histogram` vào nhóm **Impact: High**, phụ thuộc vào kích thước và nội dung heap. Lần lấy mặc định có thể kéo theo Full GC và pause đáng kể. Trên production, cần chọn thời điểm, số lượng mẫu và phạm vi phù hợp; không chạy thành vòng lặp ngắn trong giờ cao tải chỉ để “theo dõi liên tục”.

**Cách ghi file rất dễ nhầm:** `GC.class_histogram` in dữ liệu ra **stdout**, nên `> histo-01.txt` làm **shell gọi `jcmd`** tạo file. Khác với `GC.heap_dump /tmp/app.hprof` là lệnh yêu cầu **JVM đích** ghi file HPROF vào filesystem của nó. Không áp dụng tùy tiện tham số `filename=...` cho `GC.class_histogram`; cú pháp có hiệu lực nên được kiểm tra bằng `jcmd <PID> help GC.class_histogram`.

### Trường hợp không attach được

- `jcmd` thường phải chạy **trên cùng máy** với JVM đích, dưới **cùng effective user/group** và trong môi trường cho phép attach.
- Nếu JVM chạy bên trong Docker/Kubernetes, PID và filesystem nhìn từ host có thể khác; `jcmd -l` trên host không nhất thiết thấy tiến trình trong container. Hãy xác minh PID trong đúng namespace và sử dụng bộ công cụ được cung cấp trong container hoặc cách attach hợp lệ.
- Nếu image chỉ có Java runtime tối giản, có thể thiếu `jcmd`; dùng JDK/debug image phù hợp sau khi xác nhận cách kết nối, quyền và phiên bản.
- Nếu JVM đã thoát, bị chặn attach hoặc đang không phản hồi, không thể dựa vào một lệnh `jcmd` để chắc chắn có histogram.

## 3. Đọc một kết quả histogram

Đầu ra điển hình của HotSpot (số lượng, tên lớp và module dưới đây **chỉ là ví dụ minh họa**, không phải kết quả cố định):

```text
12345:
 num     #instances         #bytes  class name (module)
-------------------------------------------------------
   1:          5100       10500000  [B (java.base@21)
   2:          4000          96000  HistogramDemo$Payload
   3:          1500          36000  java.lang.String (java.base@21)
   4:           600          28800  java.util.HashMap$Node (java.base@21)
   ...
 Total         ...            ...
```

Giải nghĩa từng phần:

| Trường | Phải hiểu như thế nào? | Lỗi diễn giải thường gặp |
| --- | --- | --- |
| `num` | Hạng của dòng, thường sắp theo `#bytes` giảm dần. | Coi số hạng là ID cố định của lớp; thứ hạng **có thể đổi giữa hai lần đo**. |
| `#instances` | Số object/array thuộc lớp tại snapshot. | Coi đó là số object đã được tạo ra trong cả vòng đời JVM. |
| `#bytes` | Tổng shallow size **bằng byte** của các instance trong chính dòng lớp đó. | Coi là retained size hoặc toàn bộ đồ thị object mà lớp đó tham chiếu. |
| `class name` | Tên lớp runtime; mảng được hiển thị bằng tên nội bộ kiểu JVM. | Nhầm `[B` với một lớp người dùng hoặc tính chung mảng vào lớp bao chứa. |
| `(module)` nếu có | Thông tin module/phiên bản cho một số lớp, tùy JDK. | Coi chữ module là một phần của tên lớp Java. |
| `Total` | Tổng số instance và shallow bytes của các dòng histogram. | Coi là toàn bộ RAM/RSS hoặc giá trị heap `-Xmx`. |

**Phép tính:** Nếu một dòng cho thấy `4.000` instance và `96.000` byte, kích thước shallow trung bình là `96.000 / 4.000 = 24 byte/object`. Đây là phép chia **trên dữ liệu của chính snapshot**; nó không cho biết các object đó giữ bao nhiêu byte qua tham chiếu. Một mảng có thể dài ngắn khác nhau nên shallow size trung bình của các instance `[B` không phải hằng số.

### Đọc ký hiệu mảng

| Tên histogram | Kiểu Java |
| --- | --- |
| `[B` | `byte[]` |
| `[C` | `char[]` |
| `[I` | `int[]` |
| `[J` | `long[]` |
| `[Z` | `boolean[]` |
| `[Ljava.lang.Object;` | `java.lang.Object[]` |
| `[[I` | `int[][]` (các mảng cấp ngoài chứa tham chiếu tới `int[]`) |

**Quan trọng:** với `byte[]` hoặc `int[]`, số byte bao gồm header mảng, phần tử thực tế và padding/alignment tùy JVM, nên không đơn giản lấy `#instances × độ dài` nếu các mảng không đồng kích thước. Với `int[][]`, JVM lưu các mảng con thành object riêng; histogram tính chúng theo các dòng mảng tương ứng.

Các lớp `java.lang.String`, `java.util.HashMap$Node`, `[B`, `[Ljava.lang.Object;` thường xuất hiện nhiều trong ứng dụng bình thường. **Thấy chúng đứng đầu bảng không đồng nghĩa có leak**. Cần đối chiếu workload, số lượng hợp lý, giới hạn cache/buffer và xu hướng qua thời gian.

## 4. Thực hành Java 17+: tạo thay đổi có kiểm soát để so sánh hai snapshot

Ta cố tình giữ tham chiếu mạnh tới một số object và mảng để chúng **không bị GC thu gom** trước lúc lấy histogram. Đây là demo phục vụ phép đo, không phải ứng dụng có rò rỉ không kiểm soát.

Tạo file **`HistogramDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;

public class HistogramDemo {
    private static final List<Payload> ITEMS = new ArrayList<>();
    private static final List<byte[]> LARGE_BUFFERS = new ArrayList<>();

    private record Payload(int id, byte[] body) {}

    private static void allocate(int from, int numberOfItems) {
        for (int i = from; i < from + numberOfItems; i++) {
            ITEMS.add(new Payload(i, new byte[512]));
        }
        for (int i = 0; i < 4; i++) {
            LARGE_BUFFERS.add(new byte[1024 * 1024]);
        }
    }

    public static void main(String[] args) throws Exception {
        BufferedReader input =
                new BufferedReader(new InputStreamReader(System.in));

        allocate(0, 2_000);
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Phase A: items=" + ITEMS.size()
                + ", largeBuffers=" + LARGE_BUFFERS.size());
        System.out.println("Press Enter to grow...");
        input.readLine();

        allocate(2_000, 2_000);
        System.out.println("Phase B: items=" + ITEMS.size()
                + ", largeBuffers=" + LARGE_BUFFERS.size());
        System.out.println("Press Enter to exit...");
        input.readLine();

        System.out.println("Done.");
    }
}
```

Ở đây:

- `Payload` là một **record** hợp lệ từ Java 16; tên lớp lồng nhau trong histogram thường là `HistogramDemo$Payload`.
- Danh sách `ITEMS` giữ tham chiếu đến từng `Payload`, và mỗi `Payload` giữ một mảng `byte[512]`; shallow bytes của `Payload` và của `[B` nằm ở **hai dòng khác nhau**.
- `LARGE_BUFFERS` giữ bốn mảng `byte[1 MiB]` trong pha A, rồi tổng cộng tám mảng trong pha B. Chúng cùng được gộp vào dòng `[B` với nhiều mảng byte khác do JVM/ứng dụng tạo.
- Hai danh sách là trường `static` nên đối tượng còn reachable ở cả hai thời điểm đo. `readLine()` giữ tiến trình sống để một terminal khác chạy `jcmd`.

### Terminal A — chạy chương trình

```bash
javac --release 17 HistogramDemo.java
java -Xms64m -Xmx256m HistogramDemo
```

Đầu ra trước khi nhấn Enter (PID tùy máy):

```text
PID=12345
Phase A: items=2000, largeBuffers=4
Press Enter to grow...
```

**Chưa nhấn Enter.** `12345` không phải PID bắt buộc; sử dụng số in ra thực tế.

### Terminal B — lấy snapshot A

```bash
jcmd -l
jcmd 12345 help GC.class_histogram
jcmd 12345 GC.class_histogram > histo-A.txt
```

Trong terminal B, file `histo-A.txt` được shell tạo tại thư mục đang làm việc của terminal; chỉ lấy khi câu lệnh `jcmd` đã hoàn tất.

### Chuyển sang pha B rồi thu lần hai

Quay lại terminal A, **nhấn Enter một lần**. Chương trình sẽ in:

```text
Phase B: items=4000, largeBuffers=8
Press Enter to exit...
```

Giữ terminal A chạy. Trong terminal B:

```bash
jcmd 12345 GC.class_histogram > histo-B.txt
```

Tìm lớp demo trên Linux/macOS:

```bash
grep -F 'HistogramDemo$Payload' histo-A.txt
grep -F 'HistogramDemo$Payload' histo-B.txt
```

Hoặc Windows PowerShell:

```powershell
Select-String -Path .\histo-A.txt -SimpleMatch 'HistogramDemo$Payload'
Select-String -Path .\histo-B.txt -SimpleMatch 'HistogramDemo$Payload'
```

Dấu nháy đơn ở tên `HistogramDemo$Payload` giúp shell **không thay `$Payload` bằng biến môi trường**. Không dùng số hạng `num` để ghép hai file; hãy tìm **tên lớp**.

### Kết quả cần kiểm chứng

| Chỉ số | Pha A | Pha B | Diễn giải |
| --- | ---: | ---: | --- |
| `HistogramDemo$Payload`: `#instances` | Khoảng **2.000** | Khoảng **4.000** | 2.000 instance mới được giữ lại bởi `ITEMS`; với ví dụ này số đếm thường đúng hai mốc trên. |
| `HistogramDemo$Payload`: `#bytes` | Phụ thuộc JVM | Tăng tương ứng số instance | Chỉ gồm shallow size của record, **không gồm** mảng `body` nó trỏ tới. |
| `[B`: `#instances` | Tùy toàn JVM | Tăng do demo tạo thêm **2.000 mảng 512 byte** và **4 mảng 1 MiB** | Ngoài mảng của demo, JVM và thư viện vẫn có các mảng byte khác. |
| `[B`: `#bytes` | Tùy toàn JVM | Thường tăng đáng kể (hơn 4 MiB chỉ từ bốn mảng lớn mới) | Tổng shallow bytes của **tất cả** mảng byte live, không riêng demo. |

Lưu ý `-Xms64m -Xmx256m` ở ví dụ là **kích thước heap khởi tạo/tối đa**, không phải số byte dự kiến ở dòng `Total`. Các số liệu JVM và thứ tự bảng thay đổi theo JDK, GC, OS và các thư viện được tải.

Cuối cùng, quay lại terminal A và **nhấn Enter lần nữa**; đầu ra cuối:

```text
Done.
```

## 5. Shallow size khác retained size như thế nào?

Xem mô hình đối tượng đơn giản:

```text
ArrayList<Payload> ITEMS
    |
    +--> Payload A (id, reference) --> byte[512]
    |
    +--> Payload B (id, reference) --> byte[512]
    |
    +--> ... 
```

- **Shallow size của `Payload A`**: phần header object, trường `id`, biến tham chiếu `body`, padding. Không chứa 512 byte dữ liệu của mảng mà `body` trỏ tới.
- **Shallow size của `byte[512]`**: header mảng + phần tử + alignment. Có thể cao hơn 512 byte do chi phí của chính đối tượng mảng.
- **Retained size của một đối tượng**: lượng bộ nhớ trên heap có thể được giải phóng nhờ object đó không còn reachable, xét các quan hệ tham chiếu và các đường đi khác tới GC roots. Nếu mảng còn được object khác tham chiếu, không thể tính toàn bộ mảng là retained size riêng của `Payload A`.

Ví dụ giả định (chỉ minh họa phép tính, **không phải output đo được**):

| Class | `#instances` | `#bytes` | Trung bình shallow |
| --- | ---: | ---: | ---: |
| `app.CacheEntry` | 4.000 | 96.000 | 24 byte/instance |
| `[B` | 4.200 | 2.300.000 | Khoảng 548 byte/mảng (gồm nhiều độ dài) |

Không được cộng `2.300.000` byte của `[B` vào mỗi `app.CacheEntry`. Một số mảng có thể thuộc đối tượng khác hoặc được chia sẻ. Histogram không có cạnh tham chiếu để xác minh chủ sở hữu của mảng.

**Nếu cần tìm object giữ bộ nhớ:** thu heap dump HPROF, mở bằng Eclipse MAT, kiểm tra **Dominator Tree**, **Retained Heap**, **Path to GC Roots** và phân biệt strong/weak/soft references. Histogram chỉ giúp chọn các lớp đáng nghi để bắt đầu phân tích sâu.

## 6. So sánh histogram để tìm dấu hiệu rò rỉ

Một lần đo có thể cho biết lớp nào đang chiếm bộ nhớ, nhưng chẩn đoán memory leak thường cần **nhiều snapshot** và bối cảnh vận hành.

Quy trình đề xuất:

1. **Xác định hiện tượng:** heap sau GC vẫn tăng, pause GC thường xuyên, service chậm hoặc OOME; ghi thời gian, lượng traffic, kích thước cache/queue, bản JDK.
2. **Chọn phương thức nhất quán:** so sánh hai lần `GC.class_histogram` mặc định với nhau; tránh so sánh một file `-all` với một file mặc định rồi gọi chênh lệch là leak.
3. **Lấy mẫu trong các trạng thái tương đương:** cùng instance JVM, sau giai đoạn warm-up, workload gần tương đương; nếu có thể, chụp sau khi cùng một loại tác vụ/batch hoàn tất.
4. **So sánh theo tên lớp và các cột count/bytes:** lớp nào tăng nhiều, tăng liên tiếp, không quay xuống sau các chu kỳ xử lý và GC? Cần xem **cả số lượng instance lẫn bytes** vì một vài mảng rất lớn có thể quan trọng hơn hàng triệu object nhỏ.
5. **Kiểm tra kỳ vọng nghiệp vụ:** cache tăng có giới hạn? Danh sách request đã xong còn giữ reference? Queue backlog, retry buffer, thread-local, listener registry có được dọn đúng không?
6. **Chuyển sang bằng chứng về giữ tham chiếu:** khi tăng bất thường kéo dài, heap dump/MAT tìm GC roots và retained size; JFR giúp phân tích nơi phát sinh cấp phát, log/metrics xác nhận vòng đời.

Ví dụ giả định về xu hướng (**không phải bằng chứng leak tự động**):

| Tên lớp | Snapshot 1 `#instances` | Snapshot 2 `#instances` | Snapshot 3 `#instances` | Cần làm gì tiếp? |
| --- | ---: | ---: | ---: | --- |
| `app.RequestContext` | 10.000 | 25.000 | 42.000 | Kiểm tra request kết thúc rồi có bị giữ trong registry/queue không. |
| `app.CacheEntry` | 8.000 | 9.500 | 10.000 | Nếu cache giới hạn ở 10.000, có thể đang đạt trạng thái ổn định. |
| `java.lang.String` | 150.000 | 180.000 | 155.000 | Có biến động và thu hồi; cần thêm dữ liệu, không suy leak. |
| `[B` | 25.000 | 30.000 | 27.000 | Kiểm tra nguồn buffer và tổng `#bytes`; count riêng không đủ. |

**Cạm bẫy:** số `#bytes` của một lớp tăng có thể do nhiều object hơn, hoặc với **array** là do array mới dài hơn. Số `#instances` tăng có thể là công việc hợp lệ đang chờ hoàn tất. Nếu một lớp đang được tải bởi nhiều classloader, tên hiển thị không đủ để phân biệt mọi trường hợp; cần xem classloader trong công cụ phân tích heap.

### Tính chênh lệch đúng cách

Với mỗi lớp, dùng:

```text
delta_instances = instances_lan_2 - instances_lan_1
delta_bytes     = bytes_lan_2 - bytes_lan_1
avg_shallow     = bytes / instances     (nếu instances > 0)
```

Ví dụ giả định `Payload`:

```text
Lần 1: 2.000 instance, 48.000 byte
Lần 2: 4.000 instance, 96.000 byte
=> delta_instances = +2.000
=> delta_bytes     = +48.000 byte
=> avg_shallow     = 24 byte/instance ở cả hai lần
```

Đây chỉ là **minh họa công thức**. Thông số thực tế của `Payload` phụ thuộc object layout, alignment, kiểu JVM và cách mã được biên dịch. Khi so sánh nhiều lớp, hãy đối chiếu theo **tên class + classloader nếu cần**, không theo cột thứ tự `num`.

## 7. Khi nào dùng `-all`, khi nào dùng mặc định?

**Mặc định:** phù hợp khi muốn hiểu **live set** của ứng dụng (những object JVM vẫn xem là còn sống sau bước thu gom liên quan). Trên HotSpot, mặc định có thể yêu cầu **Full GC**, khiến phép đo mang tác động đáng kể. Khi so sánh hai lần mặc định, điều kiện tương đương giúp kết quả hữu ích hơn.

**`-all`:** phù hợp khi muốn xem cả object chưa được dọn dù không reachable, hoặc cần tránh thay đổi số liệu do một lần Full GC được yêu cầu khi thống kê. Tuy nhiên:

- `-all` **không** có nghĩa “đã bỏ qua mọi pause”, “không tác động hiệu năng”, hay “đều là đối tượng sống”.
- Object không còn reachable vẫn có thể xuất hiện trước khi GC thu gom; vì vậy một lớp có `#bytes` lớn trong `-all` chưa chứng minh bị giữ lâu.
- Đừng trộn các snapshot có/không có `-all` để suy ra chênh lệch do tăng trưởng nghiệp vụ; hai chế độ có tập đối tượng khác nhau.

**`-parallel`:** tác động đến số luồng heap inspection mà JVM cố gắng dùng; không thay đổi ý nghĩa logic của `#instances`/`#bytes`. Đừng mặc định `-parallel=8` là an toàn hơn hoặc nhanh hơn trên máy production.

## 8. Giới hạn của histogram và những nguồn bộ nhớ khác

### Heap so với RAM của tiến trình

Histogram tập trung vào **đối tượng trên Java heap**. Nó không đo trực tiếp:

- **Metaspace** (metadata class), code cache, thread stacks.
- Dung lượng off-heap/native cấp phát ngoài Java heap, ví dụ native library.
- Toàn bộ memory resident (RSS) của OS/container.
- Buffer native thực tế sau một số wrapper `DirectByteBuffer` (wrapper nằm trên heap, phần native allocation không được cộng như shallow bytes của wrapper).

Nếu RSS tăng nhưng heap histogram ổn định, cần kiểm tra GC/heap metrics, native memory tracking (nếu được bật), direct buffers, thread count, memory mapping, JNI và dữ liệu OS/container. **Không có dòng lớp nào lớn không đồng nghĩa JVM không thể bị OOME**: còn khả năng thiếu bộ nhớ native, metaspace, cấu hình heap hoặc giới hạn container.

### Khi nào cần heap dump?

Nếu histogram cho thấy `app.Order`, `HashMap$Node`, `[B` hoặc một cache tăng bền vững, câu hỏi tiếp theo thường là “Object nào giữ chúng sống?”. Khi có thẩm quyền, đủ không gian lưu trữ và chấp nhận tác động, có thể thu:

```bash
jcmd 12345 GC.heap_dump /tmp/app-12345.hprof
```

Đây là **một công cụ khác**; file HPROF được ghi ở hệ thống file của JVM đích, có thể rất lớn, có thể gây pause đáng kể và chứa dữ liệu ứng dụng nhạy cảm. Dùng công cụ như Eclipse MAT để xem dominator tree, retained heap, đường tới GC roots. Không dùng histogram thay cho việc tìm owner/root.

### Khi nào cần JFR hoặc GC log?

- **Nghi nhiều cấp phát tạm thời:** JFR allocation events/samples hoặc profiler thích hợp cho hot allocation paths; histogram live có thể không hiện các object đã được GC.
- **Nghi GC là nguyên nhân chậm:** GC logs và metrics giúp hiểu thời lượng, tần suất pause và lượng heap sau GC.
- **Nghi native memory:** Native Memory Tracking khi được bật phù hợp cho các vùng JVM theo dõi, nhưng không bao quát mọi native allocation của thư viện bên ngoài.

## 9. Vấn đề hay gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/xử lý |
| --- | --- | --- |
| `jcmd` không tìm thấy | Máy/container chỉ có runtime image, thiếu JDK tools hoặc PATH sai. | Cài/dùng bộ JDK phù hợp; kiểm tra `java -version` và vị trí `jcmd`. |
| `jcmd -l` không thấy JVM | PID namespace khác, người dùng khác, tiến trình đã thoát hoặc attach bị hạn chế. | Xác định PID và effective user thực trong môi trường JVM; kiểm tra cấu hình attach. |
| Lệnh mất nhiều thời gian, service pause | Heap rất lớn, nhiều đối tượng; chế độ mặc định có thể cần Full GC. | Giảm tần suất đo, chọn lúc ít tải, phối hợp kế hoạch vận hành; quan sát GC logs. |
| Kết quả B có ít instance hơn A | GC, workload, cache eviction, tác vụ kết thúc hoặc hai chế độ đo khác nhau. | Kiểm tra cùng JVM, cùng option, thời điểm GC và tải; chụp thêm mẫu có kiểm soát. |
| `[B` đứng đầu nhưng không biết ai giữ | Histogram không lưu mối quan hệ owner/reference. | Phân tích HPROF bằng MAT và GC roots; phân biệt mảng của String, buffer, serialization, cache. |
| Không thấy lớp cần tìm | Chưa có instance live, tên lớp có nested `$`, package khác, GC đã thu gom. | Kiểm tra tên runtime, workload, thời điểm lấy mẫu; thử tìm chuỗi tên trong file. |
| File histogram không xuất hiện trong container | `>` ghi file ở máy/shell gọi `jcmd`, không phải filesystem JVM. | Xem thư mục và quyền ghi của terminal; không nhầm với `GC.heap_dump`. |
| Dòng class tăng liên tục | Có thể backlog/caching hợp lệ hoặc leak thật. | Đối chiếu giới hạn nghiệp vụ, đo sau khi hoàn tất workload và tìm retaining path. |

**Bảo mật dữ liệu:** histogram có thể làm lộ tên package, lớp nội bộ, module và đặc điểm vận hành. Heap dump còn nhạy cảm hơn vì có thể chứa dữ liệu trong object. Chỉ chia sẻ, lưu và xóa theo chính sách truy cập phù hợp.

## 10. Tự kiểm tra

1. Một dòng có `#instances=2.000` và `#bytes=48.000`. Shallow size trung bình? **24 byte/object**.
2. `#bytes` của `app.Customer` có bao gồm mảng và đối tượng mà mỗi `Customer` trỏ tới? **Không.** Các object được trỏ tới nằm ở dòng lớp của chính chúng; histogram không ghi owner.
3. Vì sao `[B` thường lớn? Vì nhiều thành phần (chuỗi, buffer, dữ liệu mã hóa/serialization...) dùng `byte[]`; cần đối chiếu workload và heap graph, không mặc định là leak.
4. Có nên so một histogram mặc định với histogram `-all` để kết luận growth? **Không**; `-all` có thể tính thêm object đã unreachable.
5. `GC.class_histogram` có phải công cụ quan sát định kỳ chi phí thấp không? **Không**; tài liệu phân loại Impact: High và chế độ mặc định có thể yêu cầu Full GC.
6. Khi số lượng object đáng nghi tăng qua nhiều snapshot, bước tiếp theo là gì? **Xác minh workload/cache/GC**, rồi dùng heap dump/MAT tìm retaining paths và GC roots nếu dấu hiệu vẫn tồn tại.

## Tài liệu tham khảo

- [Oracle Java 21 — `jcmd` (`GC.class_histogram`, `-all`, `-parallel`, Impact: High)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle Java 21 — Diagnostic Tools (cách dùng `jcmd`, cách đọc heap histogram)](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html).
- [Oracle — Troubleshoot Memory Leaks (histogram qua nhiều lần đo và khi nào cần phân tích sâu)](https://docs.oracle.com/en/java/javase/23/troubleshoot/troubleshooting-memory-leaks.html).
- [OpenJDK HotSpot — cách `ClassHistogramDCmd` xử lý tùy chọn `-all` và yêu cầu GC](https://code.googlesource.com/edge/openjdk/+/refs/heads/master/hotspot/src/share/vm/services/diagnosticCommand.cpp).

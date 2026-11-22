# Class histogram bằng jmap

**Class histogram** là bảng thống kê các đối tượng Java trong heap theo class. Mỗi dòng cho biết class nào đang có bao nhiêu instance và tổng dung lượng shallow heap của những instance đó. Đây là cách nhanh để tìm nhóm object đang chiếm nhiều Java heap, phát hiện collection tăng bất thường và thu thập bằng chứng ban đầu khi điều tra memory leak.

Trong JDK, `jmap -histo <pid>` tạo histogram cho heap của một Java process đang chạy. Tùy chọn `-histo:live` chỉ đếm những object còn reachable. Với quy trình chẩn đoán hiện đại, Oracle khuyến nghị dùng `jcmd <pid> GC.class_histogram`; lệnh này có impact High, phụ thuộc kích thước và nội dung heap.

Histogram là thống kê theo class, không phải sơ đồ object graph. Nó cho biết class nào có nhiều object và chiếm bao nhiêu shallow bytes, nhưng không trực tiếp cho biết object nào giữ tham chiếu khiến cả một nhóm object không được giải phóng. Khi cần tìm đường dẫn giữ object, hãy tạo heap dump và phân tích bằng công cụ như Eclipse Memory Analyzer (MAT) hoặc JDK Mission Control.

## 1. Class histogram là gì?

Java heap lưu các object được tạo trong thời gian ứng dụng chạy. Một ứng dụng có thể tạo rất nhiều object thuộc nhiều class khác nhau:

- Object nghiệp vụ như `Order`, `Customer` hoặc `Session`.
- Collection như `HashMap`, `ArrayList` và các node nội bộ.
- Object chuỗi và mảng như `String`, `byte[]`, `char[]`.
- Object của framework, thư viện, JDK và JVM.
- Object đại diện cho proxy, lambda, cache hoặc buffer.

Class histogram gom các object theo class và thống kê số lượng cùng tổng kích thước của mỗi nhóm.

Ví dụ, nếu ứng dụng tạo 500.000 object `com.example.Session` và mỗi object giữ tham chiếu đến nhiều object khác, histogram có thể cho thấy số lượng Session tăng cao. Nó giúp xác định nhóm class cần điều tra tiếp.

Histogram trả lời:

- Class nào có nhiều instance nhất?
- Class nào có tổng shallow heap lớn nhất?
- Số lượng instance của class nghiệp vụ có tăng qua các lần chụp không?
- Các mảng như `byte[]` hoặc `Object[]` đang chiếm bao nhiêu heap?
- Có class hoặc collection bất thường xuất hiện trong top đầu không?

Histogram không trực tiếp trả lời:

- Object nào là GC root hoặc ai đang giữ tham chiếu đến nó?
- Tổng dung lượng của toàn bộ object graph được giữ bởi một object là bao nhiêu?
- Một object được tạo tại dòng code nào?
- Bộ nhớ native hoặc direct memory đang được dùng bao nhiêu?

Để trả lời những câu hỏi sau, cần heap dump, allocation profiling, JFR, JMX hoặc công cụ theo dõi native memory.

## 2. Chạy jmap -histo

Cú pháp:

```sh
jmap -histo <pid>
```

`<pid>` là process ID của Java application cần kiểm tra. Ví dụ:

```sh
jmap -histo 24680
```

Lệnh kết nối đến JVM đích và in histogram của Java object heap. PID 24680 chỉ là số minh họa; hãy thay bằng PID thực tế.

Có thể dùng đường dẫn đầy đủ nếu `jmap` không nằm trong PATH:

```sh
$JAVA_HOME/bin/jmap -histo 24680
```

Trên Windows PowerShell:

```powershell
& "$env:JAVA_HOME\bin\jmap.exe" -histo 24680
```

Đầu ra có thể khá dài. Chuyển hướng vào file để đọc, tìm kiếm và so sánh:

```sh
jmap -histo 24680 > histogram.txt
```

Trên PowerShell:

```powershell
jmap -histo 24680 | Out-File -Encoding utf8 histogram.txt
```

Không nên chạy histogram liên tục với tần suất cao trên một ứng dụng nhạy cảm về latency. Heap inspection có thể tốn thời gian và ảnh hưởng đến hoạt động của JVM, tùy kích thước heap, số lượng object, collector và runtime.

## 3. Đọc các cột trong output

Output điển hình có dạng:

```text
 num     #instances         #bytes  class name (module)
-------------------------------------------------------
   1:         50000        2400000  com.example.Session (app)
   2:        100000        1600000  java.lang.String (java.base)
   3:         25000         800000  [B (java.base)
   4:          5000         240000  java.util.HashMap$Node (java.base)
-------------------------------------------------------
 Total        180000        5040000
```

Đây là ví dụ minh họa cách trình bày, không phải output cố định. Số lượng, số byte, thứ tự và phần module phụ thuộc ứng dụng, JDK và kiến trúc runtime.

| Cột | Ý nghĩa |
|---|---|
| `num` | Thứ hạng của dòng trong histogram |
| `#instances` | Số object instance thuộc class |
| `#bytes` | Tổng shallow heap size của các instance thuộc class, tính bằng byte |
| `class name` | Tên class hoặc dạng mô tả class |
| `module` | Module chứa class trong các phiên bản JDK có hiển thị thông tin này |
| `Total` | Tổng instance và tổng byte của các dòng được thống kê |

Các dòng thường được sắp xếp theo tổng dung lượng giảm dần. Class đứng đầu là nhóm chiếm nhiều shallow bytes nhất tại thời điểm chụp, không nhất thiết là class có nhiều instance nhất.

Ví dụ:

- `com.example.Session` có 50.000 instance.
- Tổng shallow size của nhóm Session là 2.400.000 byte.
- `java.lang.String` có 100.000 instance và chiếm 1.600.000 byte.
- `[B` là ký hiệu cho mảng byte.

Không dùng số thứ tự `num` làm định danh ổn định giữa các lần chụp. Thứ hạng thay đổi khi số lượng và kích thước object thay đổi.

## 4. Shallow heap size và retained heap size

Đây là khác biệt quan trọng nhất khi đọc class histogram.

**Shallow heap size** là dung lượng của chính object, gồm object header, field và phần padding/alignment theo cách JVM biểu diễn object. Nó không cộng dung lượng các object khác được object đó tham chiếu.

**Retained heap size** là lượng heap có thể được giải phóng nếu object hoặc nhóm object được xét không còn được giữ bởi các tham chiếu khác. Giá trị này phụ thuộc vào đồ thị tham chiếu và dominator relationship.

Ví dụ:

```java
class Customer {
    String name;
    byte[] avatar;
}
```

Một object `Customer` giữ tham chiếu đến một `String` và một mảng byte.

Trong histogram:

- Shallow bytes của `Customer` chỉ tính object Customer.
- Shallow bytes của `String` được tính ở dòng String.
- Shallow bytes của `byte[]` được tính ở dòng mảng byte.
- Histogram không cộng toàn bộ avatar vào dòng Customer.

Vì vậy, một class có shallow heap nhỏ vẫn có thể là điểm giữ một object graph rất lớn. Muốn tìm retained heap, dominator và đường dẫn từ GC roots, cần phân tích heap dump.

Không cộng các giá trị histogram theo cách suy luận rằng một object cha giữ toàn bộ những object con; histogram đã thống kê mỗi object theo class của chính nó.

## 5. Tính kích thước trung bình mỗi instance

Có thể ước tính shallow size trung bình của một class bằng:

\[
\text{Average shallow size}
=
\frac{\text{\#bytes}}{\text{\#instances}}
\]

Ví dụ, một class có 50.000 instance và tổng 2.400.000 byte:

\[
\frac{2.400.000}{50.000}=48 \text{ bytes/object}
\]

Đây là giá trị trung bình từ histogram. Nó hữu ích để so sánh tương đối, nhưng không cho biết retained size và không thay thế việc kiểm tra object layout thực tế.

Với các object cùng một class, kích thước shallow thường giống nhau trong một runtime, nhưng có thể thay đổi giữa JDK, kiến trúc, compressed references, object alignment và tùy chọn JVM.

Đừng giả định một object Java luôn có kích thước cố định như 16 hoặc 24 byte. Hãy dùng số liệu của runtime đang phân tích.

## 6. Ý nghĩa của các class name dạng mảng

Histogram thường hiển thị tên class của array theo descriptor JVM:

| Tên trong histogram | Kiểu Java tương ứng |
|---|---|
| `[B` | `byte[]` |
| `[C` | `char[]` |
| `[I` | `int[]` |
| `[J` | `long[]` |
| `[F` | `float[]` |
| `[D` | `double[]` |
| `[Z` | `boolean[]` |
| `[Ljava.lang.Object;` | `Object[]` |
| `[[B` | Mảng hai chiều của byte array |

Các array có thể chiếm nhiều bộ nhớ dù class nghiệp vụ giữ chúng chỉ chiếm ít shallow bytes. Ví dụ một cache lưu nhiều payload dạng byte array có thể khiến `[B` đứng đầu histogram.

Từ Java 9, biểu diễn nội bộ của String trên các JDK phổ biến sử dụng byte array cho nội dung chuỗi trong nhiều trường hợp. Vì vậy, khi điều tra memory do chuỗi, hãy xem cả dòng `java.lang.String` và dòng `[B`, thay vì chỉ nhìn String.

Một dòng `[B` lớn không tự động chứng minh có memory leak. Cần xác định mảng đến từ payload, buffer, cache, serialization hay thành phần nào khác.

## 7. Phân biệt -histo và -histo:live

`jmap` hỗ trợ hai dạng:

```sh
jmap -histo <pid>
```

```sh
jmap -histo:live <pid>
```

| Lệnh | Phạm vi object |
|---|---|
| `jmap -histo <pid>` | Thống kê object trong heap, bao gồm cả object chưa được thu gom |
| `jmap -histo:live <pid>` | Chỉ thống kê object còn sống/reachable |

Object không còn reachable có thể vẫn tồn tại trong heap cho đến khi garbage collector thu gom. Do đó histogram không có `:live` có thể bao gồm object rác chưa được thu gom tại thời điểm chụp.

`-histo:live` hữu ích khi cần quan sát live set và loại bớt nhiễu do object đã không còn được tham chiếu. Tuy nhiên, việc xác định object còn sống cần xử lý reachability/GC theo cách triển khai của JVM; thao tác có thể tạo pause hoặc chi phí đáng kể.

Đối với production, hãy cân nhắc impact trước khi chạy. Nếu cần số liệu theo thời gian với overhead thấp hơn, xem xét JFR hoặc JMX thay vì liên tục yêu cầu live histogram.

## 8. Phân biệt jmap -histo với jcmd GC.class_histogram

Oracle khuyến nghị dùng `jcmd` cho chẩn đoán hiện đại thay cho các công cụ cũ như `jmap`.

Lệnh tương ứng:

```sh
jcmd 24680 GC.class_histogram
```

Xem cú pháp của JVM mục tiêu:

```sh
jcmd 24680 help GC.class_histogram
```

Trong JDK 21, command `GC.class_histogram` có các tùy chọn:

| Tùy chọn | Ý nghĩa |
|---|---|
| Không có `-all` | Không yêu cầu thống kê cả object unreachable; mặc định `false` |
| `-all` | Kiểm tra tất cả object, bao gồm object unreachable |
| `-parallel=N` | Số thread song song dùng để kiểm tra heap; 0 để JVM tự chọn, 1 để tắt parallelism |

Ví dụ chỉ kiểm tra live objects theo mặc định:

```sh
jcmd 24680 GC.class_histogram
```

Ví dụ bao gồm object unreachable:

```sh
jcmd 24680 GC.class_histogram -all
```

Điểm cần chú ý: mặc định của hai công cụ khác nhau theo tài liệu JDK 21. `jmap -histo` không có `:live` thống kê heap objects; `jcmd GC.class_histogram` mặc định `-all=false`, còn `-all` bật việc kiểm tra cả object unreachable.

`GC.class_histogram` được Oracle mô tả có **Impact: High**, phụ thuộc kích thước và nội dung heap. Không nên coi đây là thao tác monitoring nhẹ. Xem trợ giúp trên đúng JVM trước khi chạy vì các diagnostic command và tùy chọn có thể khác giữa phiên bản hoặc implementation.

## 9. Tìm PID trước khi chạy histogram

Có thể tìm JVM đang chạy bằng:

```sh
jps -l
```

Ví dụ:

```text
24680 com.example.HistogramDemo
25120 com.example.OrderService
```

Sau khi xác định đúng process:

```sh
jmap -histo 24680
```

Hoặc dùng jcmd:

```sh
jcmd 24680 GC.class_histogram
```

Nếu không thấy process, dùng công cụ hệ điều hành:

Linux/macOS:

```sh
ps -ef
```

Windows PowerShell:

```powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
```

Trong container, PID trên host có thể khác PID trong container. Chạy công cụ trong đúng container/PID namespace hoặc xác định PID theo môi trường mà công cụ có thể attach.

Công cụ attach thường cần chạy trên cùng máy với JVM đích và dưới tài khoản hệ điều hành có quyền phù hợp. Khi thao tác trong môi trường nhiều user, hãy xác định đúng tài khoản chạy ứng dụng và chính sách attach.

## 10. Ví dụ Java 17+: tạo object để quan sát histogram

Ví dụ sau giữ 100.000 instance của một class nghiệp vụ trong static collection. Nhờ tham chiếu tĩnh, các object vẫn reachable trong lúc chương trình chờ.

Tạo file `src/com/example/HistogramDemo.java`:

```java
package com.example;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class HistogramDemo {
    private static final List<SampleRecord> RETAINED =
            new ArrayList<>();

    private static final class SampleRecord {
        private final int id;

        private SampleRecord(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 100_000; i++) {
            RETAINED.add(new SampleRecord(i));
        }

        System.out.println("READY records=" + RETAINED.size());

        new CountDownLatch(1).await();
    }
}
```

Biên dịch:

```sh
mkdir -p out
javac -d out src/com/example/HistogramDemo.java
```

Chạy:

```sh
java -cp out com.example.HistogramDemo
```

Stdout chính xác:

```text
READY records=100000
```

Chương trình chờ vô hạn để bạn có thể mở terminal thứ hai và kiểm tra heap. Dùng `jps -l` để tìm PID của `com.example.HistogramDemo`.

Chạy histogram:

```sh
jmap -histo <pid>
```

Hoặc chỉ đếm object còn sống:

```sh
jmap -histo:live <pid>
```

Tìm class `com.example.HistogramDemo$SampleRecord`. Histogram phải thể hiện khoảng 100.000 instance của class này trong khi chương trình đang giữ list. Tổng byte phụ thuộc object layout và cấu hình JVM, không nên hard-code một giá trị cụ thể.

Nếu muốn dùng jcmd:

```sh
jcmd <pid> GC.class_histogram
```

Sau khi thực hành, quay lại terminal đầu và nhấn Ctrl+C để dừng chương trình.

## 11. Tìm class chiếm nhiều heap nhất

Khi mở histogram, bắt đầu bằng cách sắp xếp câu hỏi theo hai cột chính:

- `#instances` cao: class tạo ra nhiều object.
- `#bytes` cao: class có tổng shallow heap lớn.

Hai thứ hạng này không nhất thiết giống nhau. Một class có nhiều object nhỏ có thể đứng cao ở số instance nhưng thấp hơn ở tổng byte. Một class có ít instance lớn có thể đứng cao ở tổng byte.

Ví dụ cách đọc:

| Dấu hiệu | Hướng điều tra |
|---|---|
| Nhiều `String` | Kiểm tra cache chuỗi, key, payload, logging hoặc dữ liệu được giữ lâu |
| Nhiều `[B` | Kiểm tra nội dung byte, serialization, network buffer, file payload |
| Nhiều `Object[]` | Kiểm tra backing array của collection, queue hoặc cache |
| Nhiều `HashMap$Node` | Kiểm tra map tăng liên tục, key không được xóa hoặc cache không giới hạn |
| Nhiều class domain như `Session`/`Request` | Kiểm tra lifecycle, timeout, cleanup và reference retention |
| Nhiều proxy/lambda | Kiểm tra việc tạo proxy, callback, listener hoặc class generation |
| Nhiều classloader/class | Kiểm tra redeploy, plugin lifecycle và classloader leak |

Đây là các giả thuyết để điều tra, không phải kết luận tự động. Một ứng dụng có thể hợp lệ khi giữ hàng trăm nghìn String hoặc map node nếu workload yêu cầu.

## 12. Histogram và memory leak

Memory leak trong Java thường xảy ra khi ứng dụng không còn cần một object nhưng vẫn giữ reference đến object đó. Garbage collector chỉ thu hồi object không còn reachable từ GC roots.

Histogram hỗ trợ phát hiện dấu hiệu tăng trưởng:

1. Khởi động ứng dụng và chờ hoàn tất warm-up.
2. Đưa ứng dụng vào workload ổn định hoặc cùng một kịch bản tải.
3. Chụp histogram ban đầu.
4. Để ứng dụng chạy thêm một khoảng thời gian.
5. Chụp histogram tiếp theo trong điều kiện tương tự.
6. So sánh số instance và tổng bytes theo class.
7. Tìm nhóm class tăng đều qua nhiều snapshot.
8. Dùng heap dump để xác định object graph và đường dẫn giữ tham chiếu.

Ví dụ so sánh:

| Class | Snapshot 1 | Snapshot 2 | Nhận xét |
|---|---:|---:|---|
| `com.example.Session` | 10.000 | 40.000 | Tăng mạnh, cần kiểm tra lifecycle |
| `java.lang.String` | 80.000 | 110.000 | Tăng; cần xác định nguồn tạo và owner |
| `byte[]` | 20.000 | 90.000 | Có thể liên quan payload/cache |
| `java.util.HashMap$Node` | 15.000 | 55.000 | Kiểm tra map và chính sách eviction |

Bảng trên chỉ là ví dụ phân tích. Không kết luận leak từ hai snapshot đơn lẻ. Cần kiểm tra cùng điều kiện tải, thời gian warm-up, GC và thay đổi lưu lượng.

Một class tăng instance có thể phản ánh workload tăng, cache được làm nóng hoặc queue đang tích lũy hợp lệ. Dấu hiệu đáng chú ý hơn là live set tiếp tục tăng sau khi ứng dụng đạt trạng thái ổn định và qua các chu kỳ GC.

## 13. So sánh histogram theo thời gian

Có thể lưu các lần chụp thành file riêng:

```sh
jmap -histo:live 24680 > histo-01.txt
```

Sau một khoảng thời gian:

```sh
jmap -histo:live 24680 > histo-02.txt
```

Và tiếp tục:

```sh
jmap -histo:live 24680 > histo-03.txt
```

Dùng diff hoặc công cụ bảng tính để đối chiếu:

```sh
diff -u histo-01.txt histo-02.txt
```

Trên Windows có thể dùng `Compare-Object` sau khi đọc file, hoặc nhập dữ liệu vào công cụ phân tích phù hợp. Không so sánh chỉ theo số thứ tự dòng vì thứ hạng class có thể thay đổi; hãy so sánh theo class name và module.

Nếu mục tiêu là live set, hãy giữ cách chụp nhất quán giữa các lần. Không so sánh histogram bao gồm unreachable objects với histogram chỉ chứa live objects rồi coi chênh lệch là memory leak.

Để kết luận tốt hơn, ghi lại timestamp, PID, JDK version, heap size, workload và thời điểm GC gần nhất cùng mỗi file histogram.

## 14. Vì sao histogram không đủ để tìm nguyên nhân?

Histogram chỉ tổng hợp theo class. Nó không giữ quan hệ giữa object với object khác. Ví dụ:

- Một cache có thể giữ nhiều Customer object.
- Một Customer giữ Order list.
- Mỗi Order giữ nhiều LineItem.
- Mỗi LineItem giữ String và byte array.

Histogram có thể cho thấy tất cả các class trên đều chiếm bộ nhớ, nhưng không chỉ ra object cache nào là điểm giữ cả nhóm.

Để tìm nguyên nhân:

1. Tạo heap dump tại thời điểm phù hợp.
2. Mở heap dump bằng Eclipse Memory Analyzer (MAT) hoặc công cụ tương đương.
3. Xem histogram và dominator tree.
4. Tìm object có retained heap lớn.
5. Xem path to GC roots để biết reference chain.
6. Truy ngược code tạo và giữ reference.
7. Xác định lifecycle hoặc cleanup bị thiếu.
8. Sửa code và chạy lại workload để xác nhận retained/live set ổn định.

Ví dụ tạo heap dump bằng jcmd:

```sh
jcmd 24680 GC.heap_dump /tmp/app-heap.hprof
```

Heap dump có thể rất lớn, cần dung lượng đĩa và có thể tạo pause đáng kể. Theo tài liệu JDK 21, lệnh này có impact High và mặc định yêu cầu full GC trừ khi dùng tùy chọn `-all`. Hãy kiểm tra trợ giúp trước khi chạy trong production.

## 15. Class histogram và class loader statistics

Nếu histogram cho thấy nhiều class hoặc object liên quan đến classloader, cần kiểm tra class loader riêng.

`jmap` có tùy chọn:

```sh
jmap -clstats 24680
```

Nó in thống kê class loader của Java heap.

Với `jcmd`:

```sh
jcmd 24680 VM.classloader_stats
```

Lệnh này in thống kê về các classloader. Có thể xem thêm:

```sh
jcmd 24680 VM.classloaders
```

Classloader leak có thể xảy ra khi ứng dụng redeploy nhưng classloader cũ vẫn được giữ bởi thread, ThreadLocal, static reference, JDBC driver, logging framework hoặc callback chưa được gỡ bỏ.

Histogram cho thấy object/class liên quan; classloader statistics và heap dump giúp tìm nguồn giữ classloader.

## 16. Class histogram không đo toàn bộ process memory

Class histogram thống kê object trong Java heap. Tổng `#bytes` không bằng toàn bộ RSS hoặc resident memory của process.

Các vùng bộ nhớ khác có thể gồm:

- Metaspace và compressed class space.
- Thread stack.
- JIT code cache.
- Native allocation từ JNI hoặc thư viện native.
- Direct byte buffer và các vùng off-heap.
- Bộ nhớ GC, compiler và cấu trúc nội bộ của JVM.

Nếu process RSS tăng nhưng histogram Java heap không tăng tương ứng, hãy kiểm tra native memory và các vùng ngoài heap.

Native Memory Tracking (NMT) cần được bật khi khởi chạy JVM, ví dụ:

```sh
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Sau khi JVM chạy, xem summary:

```sh
jcmd 24680 VM.native_memory summary
```

NMT giúp theo dõi các nhóm native memory do HotSpot quản lý. Nó không theo dõi mọi allocation do code native bên thứ ba thực hiện. Nếu nghi ngờ native leak ngoài phạm vi NMT, cần thêm công cụ hệ điều hành như process memory map hoặc profiler native.

## 17. Tác động và an toàn khi chạy histogram

Theo tài liệu JDK 21:

- `jmap` là công cụ experimental và unsupported, có thể thay đổi hoặc không còn ở các bản JDK tương lai.
- `jcmd GC.class_histogram` có impact High, phụ thuộc kích thước và nội dung heap.
- Heap inspection có thể làm tăng thời gian dừng hoặc ảnh hưởng latency của ứng dụng.
- Output có thể rất dài với heap lớn và nhiều class.

Thực hành an toàn:

- Xác định đúng PID và đúng môi trường.
- Chạy dưới tài khoản có quyền attach phù hợp.
- Thu thập trong khoảng thời gian có thể chấp nhận được.
- Hạn chế số lần chụp liên tiếp.
- Chuyển output vào file để không làm đầy terminal log.
- Kiểm tra dung lượng đĩa nếu tạo heap dump.
- Bảo vệ file histogram và heap dump vì chúng có thể tiết lộ tên class, package và cấu trúc nội bộ.
- Không upload heap dump lên nơi công khai; heap dump có thể chứa dữ liệu người dùng, token hoặc nội dung nghiệp vụ.

Nếu cần diagnostic thường xuyên trong production, ưu tiên JFR, JMX hoặc hệ thống observability phù hợp. Dùng histogram như một bước điều tra có chủ đích thay vì polling liên tục.

## 18. Các lựa chọn thay thế và công cụ bổ trợ

| Công cụ | Dữ liệu | Khi nên dùng |
|---|---|---|
| `jcmd PID GC.class_histogram` | Histogram class trên heap | Thay thế được khuyến nghị cho jmap histogram |
| `jmap -histo` | Histogram heap gồm các object theo class | Chẩn đoán tương tác trên runtime còn hỗ trợ |
| `jmap -histo:live` | Histogram các object còn sống | Quan sát live set |
| `jmap -dump:live,format=b,file=...` | Heap dump HPROF của live objects | Cần object graph để phân tích sâu |
| `jcmd PID GC.heap_dump file.hprof` | Heap dump HPROF | Tạo dữ liệu cho MAT hoặc heap analyzer |
| JDK Mission Control/JFR | Allocation, live set, GC event và xu hướng theo thời gian | Điều tra leak hoặc tăng bộ nhớ kéo dài |
| JConsole/JMX | Heap pool và các MBean runtime | Theo dõi memory usage và xu hướng |
| NMT | Nhóm native memory do HotSpot quản lý | Điều tra bộ nhớ ngoài Java heap |

JFR hữu ích khi cần biết object nào được tạo nhiều và live set thay đổi ra sao theo thời gian. JMC có thể phân tích live objects, allocation và đường dẫn đến GC root khi recording được cấu hình phù hợp.

Histogram và heap dump bổ sung cho nhau: histogram giúp xác định class đáng chú ý; heap dump giúp xác định object cụ thể và reference chain.

## 19. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jmap: command not found` | Chưa cài JDK hoặc `JAVA_HOME/bin` chưa nằm trong PATH | Dùng đúng JDK và kiểm tra vị trí executable |
| `Could not find process` | PID sai, process đã dừng hoặc namespace khác | Dùng `jps -l`/`ps` để xác định lại |
| Attach bị từ chối | Khác user, quyền hệ điều hành hoặc attach bị chặn | Kiểm tra user, quyền và runtime configuration |
| Không thấy class mong đợi | Class chưa được load, instance không còn tồn tại hoặc dùng nhầm PID | Kiểm tra workload, classloader và process |
| `-histo` và `-histo:live` khác nhiều | Có nhiều object unreachable chưa được thu gom | So sánh đúng mục tiêu và ghi nhận khác biệt live/all |
| Histogram thay đổi mạnh giữa hai lần | Workload khác, GC khác thời điểm hoặc ứng dụng đang warm-up | Chụp trong điều kiện tải ổn định và ghi timestamp |
| `byte[]` chiếm phần lớn heap | Payload, cache, serialization hoặc buffer lớn | Tìm owner của mảng qua heap dump và dominator tree |
| Histogram không giải thích RSS tăng | Bộ nhớ tăng nằm ngoài Java heap | Kiểm tra NMT, direct memory và native allocation |
| Histogram chạy rất lâu | Heap lớn hoặc có rất nhiều object | Chọn thời điểm phù hợp, dùng jcmd và theo dõi impact |
| `jcmd GC.class_histogram` báo command không tồn tại | JVM/version không hỗ trợ command đó | Chạy `jcmd PID help` và kiểm tra JDK mục tiêu |
| Heap dump không tạo được file | Thiếu quyền ghi hoặc dung lượng đĩa | Chọn đường dẫn có quyền ghi và kiểm tra dung lượng |
| Không tìm thấy leak từ histogram | Object graph giữ reference không thể hiện trong thống kê class | Tạo heap dump, xem dominator và path to GC roots |

Nếu công cụ attach thất bại, không kết luận rằng heap không có vấn đề. Hãy xác minh process, user, namespace và runtime trước khi đổi công cụ.

## 20. Quy trình điều tra bằng class histogram

Khi ứng dụng có dấu hiệu tăng heap hoặc OutOfMemoryError:

1. Xác định lỗi thuộc Java heap, Metaspace hay native memory từ thông báo và log.
2. Tìm đúng PID và ghi lại JDK version, heap limit, collector và thời điểm.
3. Chờ ứng dụng qua warm-up nếu tình huống cho phép.
4. Chụp histogram ban đầu bằng `jcmd PID GC.class_histogram` hoặc `jmap -histo:live PID`.
5. Lưu output và timestamp.
6. Duy trì workload ổn định trong khoảng thời gian quan sát.
7. Chụp thêm histogram và so sánh theo class name, instance count và bytes.
8. Tập trung vào class nghiệp vụ hoặc collection tăng đều.
9. Nếu chưa rõ owner, tạo heap dump và phân tích dominator/path to GC roots.
10. Nếu RSS tăng nhưng Java heap ổn định, kiểm tra native memory.
11. Xác định code giữ reference và lifecycle cần sửa.
12. Chạy lại cùng workload để xác nhận live set không tiếp tục tăng.

Trong báo cáo, phân biệt rõ histogram all objects và live objects, vì hai chế độ có ý nghĩa khác nhau. Không kết luận memory leak chỉ từ một class có nhiều instance hoặc một lần chụp.

## 21. Checklist

- [ ] Đã xác định đúng JVM PID và môi trường/container.
- [ ] Đã xác nhận quyền attach của tài khoản vận hành.
- [ ] Đã dùng `jmap -histo <pid>` hoặc `jcmd <pid> GC.class_histogram`.
- [ ] Đã hiểu khác biệt giữa `jmap -histo` và `jmap -histo:live`.
- [ ] Đã phân biệt default của jmap với tùy chọn `-all` của jcmd.
- [ ] Đã đọc đúng cột instance count, bytes và class name.
- [ ] Đã hiểu `#bytes` là shallow heap, không phải retained heap.
- [ ] Đã xem xét các mảng `[B`, `[C`, `[I` và collection nội bộ.
- [ ] Đã chụp nhiều snapshot trong workload tương đương.
- [ ] Đã tránh chạy heap inspection quá thường xuyên trên production.
- [ ] Đã tạo heap dump khi cần tìm dominator và path to GC roots.
- [ ] Đã kiểm tra native memory nếu RSS không khớp Java heap.
- [ ] Đã bảo vệ histogram và heap dump khỏi truy cập không phù hợp.
- [ ] Đã ghi lại JDK, PID, thời điểm, workload và loại histogram.

## 22. Tài liệu tham khảo

- Oracle JDK 21 Tool Reference — The `jmap` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jmap.html
- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle Java Troubleshooting Guide — Troubleshoot Memory Leaks: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html

Class histogram là điểm khởi đầu hiệu quả để hiểu object nào đang chiếm Java heap. Hãy đọc đúng số instance và shallow bytes, phân biệt object reachable với object chưa được thu gom, rồi so sánh nhiều snapshot trong workload ổn định. Khi cần tìm nguyên nhân giữ object, chuyển sang heap dump, dominator tree và path to GC roots; khi bộ nhớ process tăng ngoài heap, kiểm tra native memory bằng công cụ phù hợp.
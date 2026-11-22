# Phân tích heap dump trong Java

**Heap dump** là ảnh chụp trạng thái các object đang nằm trên Java heap tại một thời điểm. File dump lưu thông tin về class, object instance, field và quan hệ tham chiếu giữa các object. Khi ứng dụng tăng bộ nhớ bất thường hoặc gặp OutOfMemoryError, heap dump giúp xác định object nào chiếm nhiều bộ nhớ và vì sao garbage collector vẫn phải giữ chúng sống.

Với HotSpot JVM, heap dump thường được lưu ở định dạng nhị phân **HPROF**. Có thể tạo dump bằng jcmd, jmap, JConsole hoặc tự động khi xảy ra Java heap exhaustion. Oracle khuyến nghị dùng **jcmd** cho chẩn đoán mới; **jmap** vẫn có trong JDK 26 nhưng được đánh dấu experimental và unsupported.

Phân tích heap dump không chỉ là tìm class có nhiều instance nhất. Cần hiểu khác biệt giữa shallow heap và retained heap, tìm đường tham chiếu từ Garbage Collection (GC) roots, kiểm tra object dominator và đối chiếu nhiều snapshot để xác định object nào đang bị giữ lại ngoài dự kiến.

## 1. Heap dump dùng để làm gì?

Heap dump hỗ trợ điều tra những vấn đề liên quan tới object trên Java heap:

- Memory leak: object không còn cần thiết nhưng vẫn được giữ bởi một reference.
- Heap tăng liên tục: số lượng instance hoặc kích thước object tăng qua thời gian.
- OutOfMemoryError: Java heap space.
- Cache hoặc collection tăng không giới hạn.
- ClassLoader leak: class và class loader cũ vẫn còn reachable.
- Object graph quá lớn: một object gốc giữ nhiều object con.
- Nhiều instance bất thường của một class.
- Bộ nhớ bị giữ bởi static field, listener, thread local hoặc queue.

Ví dụ, một ứng dụng có thể tạo nhiều request object. Sau khi request kết thúc, các object đáng lẽ có thể được garbage collector thu hồi. Nhưng nếu một static collection vẫn giữ reference tới chúng, các object tiếp tục sống và heap tăng dần.

Heap dump cho biết trạng thái object tại thời điểm chụp. Nó không tự ghi lại toàn bộ lịch sử object được tạo ra ở đâu và khi nào. Muốn tìm allocation site theo thời gian, cần kết hợp Java Flight Recorder (JFR), profiler hoặc instrumentation phù hợp.

## 2. Java heap và những gì heap dump thể hiện

Java heap là vùng bộ nhớ runtime dùng để cấp phát object và array. Garbage collector xác định object nào còn reachable từ GC roots và thu hồi những object không còn reachable.

Một heap dump HPROF thường chứa:

- Thông tin class và class loader.
- Object instance và array.
- Giá trị primitive field.
- Reference giữa các object.
- Thông tin về GC roots.
- Một số metadata cần thiết để phân tích object graph.

Mô hình tham chiếu:

~~~text
GC Roots
   |
   v
Application static field
   |
   v
Cache object
   |
   v
Object array
   |
   +------> Customer object
   |
   +------> Order object
   |
   +------> byte[] buffer
~~~

Nếu đường tham chiếu từ GC root tới object vẫn tồn tại, garbage collector xem object đó là reachable và không thu hồi nó.

### Heap dump không đại diện cho toàn bộ RAM của process

Heap dump tập trung vào Java heap. Nó không phải bản sao đầy đủ của resident memory (RSS) hoặc toàn bộ native memory của process.

Các vùng cần phân biệt:

| Vùng bộ nhớ | Ví dụ | Heap dump phản ánh thế nào |
|---|---|---|
| Java heap | Object, array, collection | Có dữ liệu object và reference |
| Metaspace | Class metadata của HotSpot | Không phải object graph thông thường trên Java heap |
| Thread stack | Stack frame và local variable | Có thể xuất hiện qua GC root/reference context, nhưng không phải bản dump đầy đủ stack memory |
| Direct/native memory | DirectByteBuffer payload, JNI allocation | Không chứa đầy đủ native payload |
| Code cache | JIT compiled code | Không phải nội dung Java heap |
| Native library | C/C++ allocation | Không được heap dump Java mô tả đầy đủ |

Nếu RSS tăng nhưng Java heap không tăng tương ứng, cần kiểm tra native memory, direct buffer, thread stack, metaspace hoặc thư viện JNI. Có thể dùng Native Memory Tracking (NMT), OS tools và JFR để điều tra các vùng này.

## 3. Các khái niệm quan trọng khi đọc heap dump

### Shallow heap

**Shallow heap** là lượng bộ nhớ mà chính object chiếm, không cộng các object khác mà nó tham chiếu.

Ví dụ một ArrayList chứa 10.000 String:

- Shallow size của ArrayList chỉ tính object ArrayList.
- Shallow size của backing Object[] tính mảng tham chiếu.
- Shallow size của từng String và byte[] backing của nó được tính riêng.

Vì vậy, một object có shallow size nhỏ vẫn có thể giữ một lượng bộ nhớ rất lớn.

### Retained heap

**Retained heap** là lượng bộ nhớ có thể được thu hồi nếu object đang xét trở nên unreachable, dựa trên quan hệ dominator trong object graph.

Ví dụ:

~~~text
Static field
    |
    v
Cache
    |
    v
Object[]
    |
    +----> 10,000 Customer objects
    |
    +----> 10,000 byte[] buffers
~~~

Object Cache có thể có shallow size nhỏ nhưng retained heap lớn vì nó giữ backing array và các object được tham chiếu bên dưới.

Retained heap là số liệu quan trọng để tìm object đang giữ nhiều bộ nhớ. Không cộng đơn giản shallow size của mọi object có thể đi tới từ một node, vì object có thể được nhiều nhánh cùng tham chiếu. Dominator analysis xử lý quan hệ giữ sống này.

### Dominator

Object A **dominates** object B nếu mọi đường đi từ GC roots tới B đều phải đi qua A. Nếu A không còn reachable, B cũng không còn reachable qua bất kỳ đường nào khác.

Dominator tree biến object graph thành cấu trúc cây giúp xác định object nào đang giữ các nhóm object khác sống.

Trong Eclipse Memory Analyzer (MAT), Dominator Tree thường được sắp theo retained heap để dễ tìm object hoặc nhóm object chiếm nhiều bộ nhớ.

### GC roots

GC roots là các điểm bắt đầu mà garbage collector sử dụng để xác định object reachable. Một số loại root phổ biến:

- Reference từ local variable trong stack frame của thread đang hoạt động.
- Static field của class đang được giữ sống.
- JNI global reference.
- Thread object và các reference nội bộ của JVM.
- Một số object nội bộ do runtime quản lý.

Khi một object đáng lẽ đã hết vòng đời nhưng vẫn xuất hiện trong heap, hãy lần theo **Path to GC Roots** để tìm reference đang giữ nó.

### Object count và retained size không giống nhau

Một class có hàng triệu instance chưa chắc là nguyên nhân chính nếu mỗi instance nhỏ và thời gian sống ngắn. Ngược lại, một object cache duy nhất có thể giữ hàng triệu object con và chiếm phần lớn retained heap.

Hãy xem đồng thời:

- Số lượng instance.
- Tổng shallow heap.
- Retained heap.
- Loại object và class loader.
- Đường dẫn tới GC roots.
- Sự thay đổi giữa các snapshot.

## 4. Tạo heap dump bằng jcmd

Oracle khuyến nghị dùng jcmd thay cho jmap trong quy trình chẩn đoán mới. jcmd gửi diagnostic command tới JVM đang chạy và hỗ trợ tạo HPROF heap dump.

Xác định Java process:

~~~bash
jcmd -l
~~~

Ví dụ output:

~~~text
2125 com.acme.DemoServer
5485 jdk.jcmd/sun.tools.jcmd.JCmd
~~~

Dùng PID cụ thể để tạo dump:

~~~bash
jcmd 2125 GC.heap_dump /secure/diagnostics/heap-2125.hprof
~~~

PID 2125 chỉ là ví dụ; thay bằng PID của ứng dụng thực tế.

Lệnh GC.heap_dump có mức tác động **High** theo tài liệu JDK 26. Theo mặc định, JVM yêu cầu một full GC trước khi tạo dump, trừ khi dùng tùy chọn -all. Điều này có thể gây pause đáng kể tùy kích thước heap và nội dung object graph.

### Dump tất cả object, kể cả object unreachable

~~~bash
jcmd 2125 GC.heap_dump -all=true /secure/diagnostics/heap-all.hprof
~~~

Tùy chọn -all yêu cầu dump cả object unreachable. Khi không dùng -all, command yêu cầu full GC và tạo dump theo tập object còn lại sau quá trình GC.

Với phân tích memory leak thông thường, snapshot của object còn reachable sau GC thường hữu ích vì nó tập trung vào bộ nhớ đang thực sự được giữ sống.

Chỉ dùng -all khi có lý do cần kiểm tra object chưa reachable hoặc muốn quan sát nội dung trước khi GC loại bỏ chúng.

### Nén heap dump

jcmd hỗ trợ nén HPROF khi ghi:

~~~bash
jcmd 2125 GC.heap_dump -gz=1 /secure/diagnostics/heap-2125.hprof.gz
~~~

Giá trị nén thấp ưu tiên tốc độ; giá trị cao tăng mức nén và có thể tốn CPU hơn. Kiểm tra khả năng đọc file nén của công cụ phân tích đang dùng; nếu công cụ không đọc trực tiếp, giải nén thành HPROF trước khi mở.

### Kiểm tra cú pháp command

~~~bash
jcmd 2125 help GC.heap_dump
~~~

Help của JVM đích hiển thị các option khả dụng theo JDK và VM đang chạy. Các option thường gặp trong JDK 26:

| Option | Ý nghĩa |
|---|---|
| -all | Dump cả object unreachable |
| -gz | Ghi HPROF dạng gzip với mức nén chỉ định |
| -overwrite | Cho phép ghi đè file đã tồn tại |
| -parallel | Số thread dùng để tạo heap dump |

Không dùng -overwrite nếu chưa xác nhận file đích có thể bị thay thế. Mặc định command không ghi đè file đã tồn tại.

## 5. Tạo heap dump bằng jmap

jmap là công cụ legacy dùng để lấy thông tin bộ nhớ từ Java process. Trong JDK 26, manual đánh dấu jmap là **experimental and unsupported**, có thể bị thay đổi hoặc loại bỏ trong các JDK tương lai. Oracle khuyến nghị dùng jcmd vì hỗ trợ chẩn đoán mới và giảm performance overhead.

Cú pháp dump HPROF:

~~~bash
jmap -dump:format=b,file=heap.hprof 2125
~~~

Chỉ dump object còn live sau GC:

~~~bash
jmap -dump:live,format=b,file=heap-live.hprof 2125
~~~

Tùy chọn -dump gồm:

- live: chỉ dump object live.
- format=b: ghi HPROF binary format.
- file=filename: tên file output.

Các tùy chọn thường dùng khác:

~~~bash
jmap -histo 2125
jmap -histo:live 2125
jmap -clstats 2125
jmap -finalizerinfo 2125
~~~

| Tùy chọn | Công dụng |
|---|---|
| -histo | Histogram object theo class |
| -histo:live | Histogram chỉ tính object live |
| -clstats | Thống kê class loader |
| -finalizerinfo | Thông tin object đang chờ finalization |
| -dump | Tạo heap dump |

Không nên xây dựng automation mới phụ thuộc format output của jmap. Với thao tác tạo dump trên JVM đang chạy, ưu tiên:

~~~bash
jcmd 2125 GC.heap_dump /secure/diagnostics/heap.hprof
~~~

## 6. Tự động tạo heap dump khi OutOfMemoryError

Có thể cấu hình JVM tạo heap dump khi Java heap bị cạn:

~~~bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/diagnostics/java_pid%p.hprof \
  -jar app.jar
~~~

Trong đó:

- -XX:+HeapDumpOnOutOfMemoryError bật dump khi JVM phát hiện Java heap exhaustion.
- -XX:HeapDumpPath chỉ định thư mục và tên file.
- %p được thay bằng process ID của JVM.

Nếu không đặt HeapDumpPath, file mặc định được tạo trong working directory với tên dạng java_pid<pid>.hprof.

### Giới hạn của tự động dump

Tùy chọn này áp dụng cho OutOfMemoryError do Java heap exhaustion. Nó không bảo đảm tạo dump cho mọi loại OutOfMemoryError, ví dụ lỗi tạo native thread hoặc lỗi tài nguyên native khác.

Trước khi bật trong production:

- Chọn thư mục có đủ dung lượng.
- Đảm bảo process có quyền ghi.
- Dùng tên file phân biệt theo PID.
- Bảo vệ quyền đọc file.
- Có chính sách retention và xóa file cũ.
- Kiểm thử trên môi trường staging.
- Xác định cách lấy dump ra khỏi máy bị lỗi để phân tích.

Nếu heap gần bằng giới hạn bộ nhớ container hoặc disk quota, dump có thể thất bại vì không đủ dung lượng. Đừng chỉ dựa vào tùy chọn tự động mà bỏ qua việc giám sát dung lượng đĩa.

## 7. Phân tích heap dump bằng Eclipse Memory Analyzer

**Eclipse Memory Analyzer (MAT)** là công cụ phân tích heap dump, hỗ trợ đọc HPROF, thống kê object, xây dựng dominator tree và lần theo GC roots.

Tải MAT từ trang chính thức Eclipse và mở file HPROF:

1. Khởi chạy Memory Analyzer.
2. Chọn Open Heap Dump.
3. Chọn file .hprof.
4. Chờ MAT parse object graph và tạo index.
5. Bắt đầu bằng Overview và Leak Suspects Report.
6. Kiểm tra Histogram, Top Consumers và Dominator Tree.
7. Chọn object nghi ngờ và chạy Path to GC Roots.

MAT có thể cần lượng bộ nhớ lớn để phân tích dump lớn. Nếu dump chứa hàng chục triệu object, nên dùng máy phân tích 64-bit có RAM và dung lượng đĩa phù hợp. Có thể tăng heap của chính MAT qua cấu hình -Xmx trong file ini của ứng dụng MAT.

### Overview

Overview cho biết tổng quan về heap dump, bao gồm số lượng object, class, class loader và dung lượng heap được ghi nhận.

Bắt đầu từ overview để xác định dump có parse thành công và quy mô object graph trước khi chạy truy vấn nặng.

### Histogram

Histogram nhóm object theo class, thường hiển thị:

- Class name.
- Number of instances.
- Shallow heap.
- Retained heap hoặc số liệu tương ứng nếu được tính.

Ví dụ minh họa:

| Class | Instances | Shallow heap |
|---|---:|---:|
| byte[] | 2.000 | 32 MB |
| java.lang.String | 18.000 | 1,2 MB |
| java.util.HashMap$Node | 12.000 | 0,8 MB |
| com.acme.Customer | 2.000 | 0,3 MB |

Số liệu trên chỉ là ví dụ. Histogram giúp tìm class chiếm số lượng hoặc shallow heap lớn, nhưng chưa cho biết ai đang giữ object đó sống.

### Top Consumers

Top Consumers giúp nhóm object chiếm nhiều bộ nhớ theo class, package hoặc class loader. Dùng truy vấn này để khoanh vùng khu vực cần điều tra.

### Dominator Tree

Dominator Tree sắp xếp các object theo retained heap. Đây là nơi phù hợp để tìm object giữ một lượng lớn object con.

Các câu hỏi cần đặt ra:

- Object nào có retained heap lớn nhất?
- Nó thuộc class ứng dụng hay class JDK?
- Nó được giữ bởi static field, cache, listener hay thread?
- Object con có phải dữ liệu đáng lẽ đã hết vòng đời không?
- Một class loader cũ có giữ nhiều class hoặc instance không?

### Path to GC Roots

Khi đã tìm thấy object đáng ngờ, mở Path to GC Roots để xem reference chain từ GC root tới object.

Ví dụ:

~~~text
GC Root
   |
   v
LeakyCache.CACHE (static field)
   |
   v
ArrayList
   |
   v
Object[] elementData
   |
   +----> byte[16384]
   +----> byte[16384]
   +----> byte[16384]
~~~

Đường tham chiếu cho thấy static collection vẫn giữ các buffer. Nếu collection không có cơ chế giới hạn hoặc eviction, số object có thể tăng theo số request.

Không phải mọi object được giữ sống đều là leak. Cache có giới hạn, connection pool hoặc object dùng chung có thể được giữ sống có chủ đích. Cần đối chiếu với yêu cầu nghiệp vụ và vòng đời dự kiến.

### Leak Suspects Report

Leak Suspects Report chạy các heuristic để gợi ý khu vực có thể gây memory leak. Đây là điểm khởi đầu hữu ích, không phải kết luận cuối cùng.

Luôn xác nhận suspect bằng dominator tree, retained heap và path to GC roots.

## 8. Quy trình phân tích một heap dump

Một quy trình hiệu quả:

1. **Xác định triệu chứng**: heap tăng liên tục, GC không thu hồi được nhiều bộ nhớ hay OOME.
2. **Thu thập snapshot**: tạo HPROF ở thời điểm tải cao hoặc ngay sau khi tái hiện sự cố.
3. **Mở bằng MAT**: xác nhận dump được parse thành công.
4. **Xem overview**: kiểm tra tổng object, class và heap size.
5. **Xem histogram**: tìm class có instance count hoặc shallow heap bất thường.
6. **Xem Top Consumers**: xác định package/class loader chiếm nhiều bộ nhớ.
7. **Mở Dominator Tree**: tìm object có retained heap lớn.
8. **Lần theo GC roots**: xác định reference đang giữ object sống.
9. **Đối chiếu source code**: tìm static collection, listener, cache, thread local hoặc lifecycle chưa được dọn.
10. **Đề xuất sửa**: giới hạn cache, unregister listener, remove reference hoặc kết thúc lifecycle đúng cách.
11. **Tái hiện và kiểm thử**: chạy cùng workload sau khi sửa.
12. **Thu thập snapshot mới**: xác nhận retained heap không còn tăng bất thường.

Không dừng ở việc tìm thấy một class có nhiều instance. Phải tìm ra reference giữ object sống và xác định tại sao reference đó tồn tại.

## 9. So sánh nhiều heap dump để tìm xu hướng

Một snapshot cho biết trạng thái tại một thời điểm. Hai hoặc nhiều snapshot được tạo trong điều kiện tương đương có thể giúp xác định xu hướng tăng trưởng.

Ví dụ:

| Snapshot | Request đã xử lý | Cache entries | Retained heap của cache |
|---|---:|---:|---:|
| dump-1 | 1.000 | 1.000 | 20 MB |
| dump-2 | 2.000 | 2.000 | 40 MB |
| dump-3 | 3.000 | 3.000 | 60 MB |

Bảng chỉ minh họa tình huống cache tăng không giới hạn. Số liệu thực tế cần lấy từ dump và cùng truy vấn trong MAT.

### Cách so sánh đáng tin cậy

- Chụp các dump sau cùng giai đoạn warm-up.
- Dùng cùng workload hoặc cùng số request.
- Ghi lại thời điểm, heap size, GC và cấu hình runtime.
- Dùng cùng phương pháp tạo dump, đặc biệt là cách xử lý object unreachable.
- So sánh instance count, shallow heap, retained heap và dominator.
- Tìm class tăng theo số request thay vì tăng ngẫu nhiên theo tải.
- Kiểm tra object có còn reachable qua cùng root chain hay không.

Nếu dùng jcmd GC.heap_dump mặc định, command yêu cầu full GC trước khi dump. Điều này giúp snapshot tập trung vào object còn reachable sau GC. Nếu dùng -all, snapshot còn gồm object unreachable nên không nên so sánh trực tiếp với dump mặc định mà không tính đến khác biệt này.

### Đừng nhầm allocation rate với memory leak

Ứng dụng có thể allocate rất nhiều object tạm thời nhưng GC vẫn thu hồi chúng. Allocation rate cao gây GC pressure nhưng không nhất thiết là memory leak.

Một dấu hiệu đáng chú ý hơn là live set sau GC tăng dần và object cũ tiếp tục được giữ bởi reference không cần thiết.

## 10. Ví dụ Java 17+: tạo cache giữ object không giới hạn

Ví dụ này mô phỏng một cache giữ byte array trong static collection mà không có cơ chế eviction. Các object vẫn reachable nên GC không thể thu hồi chúng.

Cấu trúc:

~~~text
project/
  src/
    com/acme/LeakyCache.java
  out/
~~~

Tệp src/com/acme/LeakyCache.java:

~~~java
package com.acme;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public final class LeakyCache {

    private static final List<byte[]> CACHE = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 2000; i++) {
            CACHE.add(new byte[16 * 1024]);
        }

        System.out.println("READY objects=" + CACHE.size());
        new CountDownLatch(1).await();
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d out src/com/acme/LeakyCache.java
~~~

Chạy với heap giới hạn để thực hành:

~~~bash
java -Xms128m -Xmx128m -cp out com.acme.LeakyCache
~~~

Stdout chính xác:

~~~text
READY objects=2000
~~~

Ứng dụng giữ 2.000 byte arrays trong static list và chờ vô thời hạn để JVM không thoát. Đây là ví dụ giữ object có chủ đích nhằm mô phỏng một cache không được giới hạn.

### Tạo dump

Mở terminal thứ hai và tìm PID:

~~~bash
jcmd -l
~~~

Giả sử PID là 2125:

~~~bash
jcmd 2125 GC.heap_dump leaky-cache.hprof
~~~

### Phân tích trong MAT

1. Mở leaky-cache.hprof.
2. Chạy Histogram và tìm class byte[].
3. Mở Dominator Tree.
4. Tìm LeakyCache hoặc ArrayList có retained heap lớn.
5. Mở Path to GC Roots cho một byte[].
6. Xác nhận đường tham chiếu đi qua static field CACHE.
7. Đề xuất giới hạn cache hoặc loại bỏ reference khi dữ liệu hết hạn.

Sau khi phân tích, quay lại terminal chạy LeakyCache và nhấn Ctrl+C để dừng process thử nghiệm.

Kết quả phân tích có thể khác đôi chút theo JDK, object layout và MAT version. Đường tham chiếu cốt lõi cần tìm là static CACHE giữ backing array, từ đó giữ các byte[] sống.

## 11. Phân biệt memory leak, cache hợp lệ và allocation pressure

| Hiện tượng | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Memory leak | Live set tăng qua thời gian và object không còn cần vẫn reachable | Dominator Tree, Path to GC Roots |
| Cache hợp lệ | Object được giữ có chủ đích và có giới hạn/eviction | Kiểm tra cache policy, TTL, maximum size |
| Allocation pressure | Nhiều object tạm thời, GC thường xuyên nhưng live set sau GC ổn định | JFR allocation events, allocation profile |
| ClassLoader leak | Class loader cũ và class của nó vẫn reachable | Class Loader Statistics, Dominator Tree |
| Native memory leak | RSS tăng nhưng Java heap không tăng tương ứng | NMT, OS tools, JNI/native profiler |
| Direct buffer accumulation | DirectByteBuffer hoặc native buffer tăng | Buffer pool metrics, native memory, reference lifecycle |

Heap dump rất mạnh trong việc tìm object đang sống và reference chain. Nó không thay thế profiling allocation hoặc phân tích native memory.

## 12. Heap dump và class histogram

Histogram là bản tóm tắt số lượng object theo class. Nó thường nhỏ hơn heap dump và có thể là bước sàng lọc ban đầu.

Dùng jcmd:

~~~bash
jcmd 2125 GC.class_histogram
~~~

JDK 26 xếp GC.class_histogram mức tác động High vì chi phí phụ thuộc kích thước và nội dung heap.

Histogram cho biết class nào có nhiều instance hoặc chiếm nhiều shallow heap. Nó không cung cấp đầy đủ object graph như heap dump.

Dùng jmap legacy:

~~~bash
jmap -histo 2125
jmap -histo:live 2125
~~~

Để xác định nguyên nhân giữ object sống, cần heap dump và công cụ phân tích object reference.

## 13. Heap dump từ core dump sau sự cố

Khi JVM đã crash và có core dump, có thể dùng Serviceability Agent qua jhsdb để phân tích postmortem.

Tạo heap dump HPROF từ core:

~~~bash
jhsdb jmap \
  --exe /path/to/java \
  --core /path/to/core \
  --binaryheap \
  --dumpfile heap-from-core.hprof
~~~

Trong đó:

- --exe chỉ định Java executable tương ứng với core dump.
- --core chỉ định core file.
- --binaryheap yêu cầu dump Java heap ở định dạng HPROF.
- --dumpfile đặt tên file output.

Sau khi tạo, mở HPROF bằng MAT như heap dump thông thường.

### Cảnh báo khi dùng jhsdb

jhsdb là công cụ experimental và unsupported. Oracle cảnh báo attach jhsdb vào live process có thể khiến process bị treo và có khả năng crash khi debugger detach.

Với JVM đang chạy, ưu tiên jcmd. Dùng jhsdb ở chế độ postmortem với executable và core dump phù hợp.

Core dump và heap dump đều có thể chứa dữ liệu nhạy cảm. Bảo vệ cả hai theo cùng chính sách truy cập và retention.

## 14. Lỗi thường gặp khi tạo và phân tích heap dump

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jcmd không tìm thấy process | PID sai hoặc JVM ở container namespace khác | Dùng jcmd -l hoặc ps trong đúng namespace |
| Attach failed | Khác tài khoản hoặc attach mechanism bị tắt | Kiểm tra quyền OS và DisableAttachMechanism |
| GC.heap_dump chạy lâu | Heap lớn hoặc object graph lớn | Đánh giá thời gian pause và không gửi lệnh lặp lại |
| Dump thất bại vì thiếu disk | File cần nhiều dung lượng | Kiểm tra dung lượng và chọn volume đủ lớn |
| Không ghi được file | Process không có quyền ghi thư mục | Chọn thư mục được cấp quyền |
| MAT báo lỗi parse | File dump không hoàn chỉnh, bị hỏng hoặc định dạng không hỗ trợ | Kiểm tra file, JDK và MAT version; tạo lại dump nếu cần |
| MAT hết bộ nhớ | Dump có quá nhiều object hoặc MAT heap quá nhỏ | Dùng máy 64-bit và tăng -Xmx của MAT |
| Không tìm thấy leak trong histogram | Nhiều object nhỏ hoặc vấn đề nằm ở reference chain | Dùng Dominator Tree và Path to GC Roots |
| Retained heap nhỏ nhưng shallow heap lớn | Nhiều object độc lập hoặc shared references | Xem histogram và dominator relationship |
| Heap dump không giải thích RSS tăng | Bộ nhớ tăng nằm ngoài Java heap | Kiểm tra NMT, direct buffer, JNI và OS metrics |
| Hai snapshot không so sánh được | Workload, GC hoặc cách dump khác nhau | Chuẩn hóa điều kiện và cách thu thập |
| jmap không hoạt động trên JDK mới | jmap là experimental/unsupported | Chuyển sang jcmd GC.heap_dump |
| Core dump không phân tích được | Sai executable hoặc core không tương ứng | Dùng đúng binary và core từ cùng process/JDK |
| Không thấy object tạm trong dump mặc định | Full GC đã loại object unreachable | Dùng -all khi có mục tiêu kiểm tra object unreachable |

## 15. Bảo vệ heap dump trong production

Heap dump có thể chứa hầu hết dữ liệu ứng dụng đang giữ trong memory:

- Access token và session.
- Password hoặc secret cấu hình sai cách.
- Nội dung request và response.
- Dữ liệu khách hàng.
- Thông tin cá nhân.
- Khóa hoặc dữ liệu nhạy cảm được lưu trong object.
- SQL query, cache và dữ liệu nghiệp vụ.

Các nguyên tắc vận hành:

1. Chỉ thu thập khi có mục đích chẩn đoán rõ ràng.
2. Xác nhận đúng JVM và PID.
3. Đánh giá pause và mức tác động High trước khi chạy.
4. Kiểm tra dung lượng đĩa.
5. Ghi vào thư mục chỉ nhóm được phép mới truy cập.
6. Không lưu dump trong web root hoặc thư mục public.
7. Mã hóa khi lưu hoặc chuyển giao theo chính sách tổ chức.
8. Không gửi heap dump lên dịch vụ chia sẻ công khai.
9. Giới hạn retention và xóa an toàn sau khi kết thúc điều tra.
10. Ghi nhận người thu thập, thời điểm, PID, JDK và nơi lưu.

Heap dump là dữ liệu nhạy cảm hơn nhiều so với log thông thường. Quyền đọc file dump cần được kiểm soát chặt.

## 16. Checklist phân tích heap dump

- [ ] Xác định triệu chứng và mục tiêu phân tích.
- [ ] Xác nhận JDK, JVM và PID đích.
- [ ] Kiểm tra quyền attach và attach mechanism.
- [ ] Ước lượng dung lượng heap dump và disk.
- [ ] Chọn jcmd GC.heap_dump cho JVM đang chạy.
- [ ] Chỉ dùng jmap khi cần duy trì quy trình legacy.
- [ ] Xác định có cần dump object unreachable bằng -all hay không.
- [ ] Bảo vệ file HPROF theo chính sách dữ liệu.
- [ ] Mở dump trong MAT và xác nhận parse hoàn tất.
- [ ] Kiểm tra overview, histogram và top consumers.
- [ ] Dùng Dominator Tree để tìm retained heap lớn.
- [ ] Dùng Path to GC Roots để tìm reference giữ object sống.
- [ ] Đối chiếu với vòng đời object trong source code.
- [ ] So sánh snapshot sau workload tương đương.
- [ ] Dùng JFR nếu cần tìm allocation trend hoặc allocation site.
- [ ] Dùng NMT/OS tools nếu nghi ngờ native memory.
- [ ] Kiểm thử bản sửa và xác nhận live set ổn định.

## 17. Ghi nhớ

- Heap dump là snapshot object graph trên Java heap tại một thời điểm.
- HPROF là định dạng binary phổ biến cho HotSpot heap dump.
- jcmd GC.heap_dump là lựa chọn được Oracle khuyến nghị cho JVM đang chạy; command có mức tác động High.
- GC.heap_dump mặc định yêu cầu full GC; -all dump cả object unreachable và không yêu cầu full GC theo cách mặc định.
- jmap vẫn có trong JDK 26 nhưng là experimental/unsupported; ưu tiên jcmd cho chẩn đoán mới.
- -dump:live,format=b,file=... tạo HPROF chỉ chứa object live bằng jmap.
- -XX:+HeapDumpOnOutOfMemoryError tự tạo dump khi xảy ra Java heap exhaustion; HeapDumpPath chỉ định vị trí file.
- Shallow heap là kích thước bản thân object; retained heap là bộ nhớ có thể được thu hồi nếu object không còn reachable theo dominator relationship.
- Dominator Tree tìm object giữ nhiều object khác sống; Path to GC Roots chỉ ra reference chain.
- Histogram cho biết class và số lượng object nhưng không tự tìm được nguyên nhân leak.
- So sánh nhiều snapshot trong điều kiện tương đương giúp xác định live set tăng theo thời gian.
- Heap dump không giải thích đầy đủ native memory, direct buffer payload, thread stack hoặc RSS.
- MAT Leak Suspects là gợi ý; cần xác nhận bằng dominator, retained heap và GC roots.
- Heap dump có thể chứa secret và dữ liệu người dùng; bảo vệ file như dữ liệu production nhạy cảm.

## Tài liệu tham khảo chính thức

- [The jmap Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jmap.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Troubleshooting Memory Leaks — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html)
- [Diagnostic Tools — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The jhsdb Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jhsdb.html)
- [Eclipse Memory Analyzer — Finding Memory Leak](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html)
- [Eclipse Memory Analyzer — Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html)
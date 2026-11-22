# Heap, Metaspace và mã máy do JIT biên dịch

Trong JVM, một ứng dụng Java có thể dùng nhiều vùng nhớ với mục đích khác nhau. Ba vùng thường bị nhầm lẫn là **Java Heap**, **Metaspace** và **Code Cache**. Heap giữ dữ liệu của đối tượng; Metaspace giữ metadata mô tả các lớp đã được nạp; Code Cache giữ mã máy mà JIT compiler tạo ra để JVM thực thi nhanh hơn.

Sự phân biệt này đặc biệt hữu ích khi làm việc với **CRaC (Coordinated Restore at Checkpoint)**. CRaC tạo checkpoint của một tiến trình đang chạy rồi khôi phục tiến trình đó ở lần khởi động sau. Vì vậy, trạng thái đối tượng, trạng thái nạp lớp và trạng thái biên dịch của JVM có thể ảnh hưởng đến thời gian khởi động, dung lượng checkpoint và mức tiêu thụ bộ nhớ sau restore.

## 1. Nhìn tổng thể các vùng nhớ

Đặc tả JVM mô tả các vùng dữ liệu runtime như heap, method area, runtime constant pool, Java stack và native method stack. **Metaspace** và **Code Cache** là cách HotSpot triển khai một số phần của mô hình đó; chúng không phải tên vùng nhớ bắt buộc mà mọi JVM implementation đều phải dùng.

Trong HotSpot hiện đại, có thể hình dung các vùng liên quan như sau:

```text
Tiến trình Java
│
├── Java Heap
│   ├── Đối tượng
│   ├── Mảng
│   └── Các vùng phục vụ GC (ví dụ: Eden, Survivor, Old)
│
├── Metaspace (native memory)
│   ├── Metadata của class
│   ├── Metadata của method
│   └── Cấu trúc runtime liên quan đến class
│
├── Code Cache (native memory)
│   ├── Mã máy do JIT biên dịch
│   ├── Runtime stubs
│   └── Các đoạn mã được JVM sinh ra
│
└── Các vùng khác
    ├── Java stack của từng thread
    ├── Direct buffer / native allocation
    ├── Native library và cấu trúc nội bộ JVM
    └── Bộ nhớ phục vụ GC, compiler và thread
```

Heap, Metaspace và Code Cache có thể cùng tăng trong một ứng dụng, nhưng chúng không chứa cùng loại dữ liệu và không được điều chỉnh bằng cùng một tham số JVM. Đặt `-Xmx` lớn hơn chỉ tăng giới hạn heap; nó không tự động cấp thêm Metaspace hoặc Code Cache.

## 2. Java Heap: nơi chứa đối tượng và mảng

### 2.1. Vai trò của Heap

Java Heap là vùng nhớ runtime dùng để cấp phát đối tượng và mảng. Heap được chia sẻ giữa các thread trong cùng JVM. Khi chương trình thực hiện:

```java
Customer customer = new Customer("An");
int[] scores = new int[100];
```

các đối tượng `Customer` và `int[]` được cấp phát trên heap theo mô hình thực thi thông thường. Biến cục bộ `customer` và `scores` là các tham chiếu; nếu chúng là biến cục bộ trong một method, vị trí lưu biến tham chiếu thường gắn với stack frame của thread, còn đối tượng được tham chiếu nằm trên heap.

JIT có thể tối ưu một số phép cấp phát bằng escape analysis và scalar replacement. Vì thế, không nên suy luận rằng mỗi biểu thức `new` trong mã nguồn chắc chắn tạo ra một đối tượng vật lý tồn tại trên heap sau tối ưu hóa.

### 2.2. Heap và Garbage Collection

Heap được quản lý bởi Garbage Collector (GC). GC xác định những đối tượng còn có thể truy cập từ các GC root, sau đó thu hồi hoặc tái sử dụng vùng nhớ của những đối tượng không còn reachable.

Một số khái niệm thường gặp trong HotSpot:

- **Young Generation**: khu vực dành cho các đối tượng mới được cấp phát. Trong cấu hình generational, khu vực này thường có Eden và Survivor.
- **Old Generation**: nơi các đối tượng sống lâu hơn có thể được chuyển đến.
- **Eden**: nơi phần lớn đối tượng mới được cấp phát trong các collector generational.
- **Survivor**: vùng giữ các đối tượng sống sót qua một hoặc nhiều lần thu gom ở Young Generation.

Đây là cách tổ chức phổ biến, nhưng chi tiết bố trí phụ thuộc GC được chọn. G1 tổ chức heap thành các region; ZGC có cơ chế và cấu trúc riêng. Không nên áp dụng sơ đồ Eden/Survivor/Old một cách máy móc cho mọi collector.

### 2.3. Điều chỉnh kích thước Heap

Hai tham số cơ bản:

```bash
java -Xms512m -Xmx2g -jar application.jar
```

- `-Xms`: kích thước heap ban đầu và mức tối thiểu mà JVM hướng tới.
- `-Xmx`: kích thước heap tối đa.

Các giá trị trên chỉ là ví dụ cú pháp, không phải khuyến nghị cấp phát cho mọi ứng dụng. Khi chọn heap cần xem xét giới hạn bộ nhớ của máy hoặc container, số lượng request đồng thời, kích thước dữ liệu sống lâu, GC pause và phần native memory mà tiến trình còn cần.

Nếu heap quá nhỏ, GC có thể chạy thường xuyên và ứng dụng có thể gặp `OutOfMemoryError: Java heap space`. Nếu heap quá lớn so với giới hạn container, tiến trình vẫn có thể bị hệ điều hành kết thúc do vượt memory limit, dù Java Heap chưa chạm `-Xmx`.

### 2.4. Những gì không nằm trong Heap

Không phải mọi dữ liệu mà ứng dụng Java sử dụng đều nằm trên heap. Ví dụ:

- Class metadata của HotSpot nằm trong Metaspace.
- Mã máy do JIT sinh ra nằm trong Code Cache.
- Thread stack là vùng nhớ riêng cho từng thread.
- Direct `ByteBuffer` có thể sử dụng native memory.
- Thư viện JNI và các thư viện native có thể cấp phát bộ nhớ ngoài heap.

Đây là lý do RSS hoặc tổng bộ nhớ container có thể cao hơn đáng kể so với heap đang sử dụng.

## 3. Metaspace: metadata của các class đã nạp

### 3.1. Metaspace lưu gì?

Khi JVM nạp một class, nó cần lưu thông tin để hiểu và thực thi class đó: cấu trúc lớp, thông tin field và method, bytecode, runtime constant pool cùng các cấu trúc metadata liên quan. Trong HotSpot, phần lớn class metadata này được cấp phát trong **Metaspace**, sử dụng native memory thay vì Java Heap.

Metaspace được giới thiệu từ Java 8 để thay thế PermGen của các phiên bản HotSpot cũ. Vì vậy, tài liệu hoặc cấu hình Java cũ có thể nhắc đến `PermGen`, `-XX:PermSize` hay `-XX:MaxPermSize`; đó không phải cách điều chỉnh Metaspace trên các JVM hiện đại.

Một số điểm cần phân biệt:

- Một instance như `new Customer()` thuộc Heap.
- Metadata mô tả class `Customer` thuộc vùng metadata do JVM quản lý, trong HotSpot thường là Metaspace.
- Đối tượng `java.lang.Class` đại diện cho class là một Java object trên Heap.
- Giá trị của static field gắn với class mirror và cách JVM biểu diễn dữ liệu; không nên kết luận rằng mọi static field đều được lưu trực tiếp trong Metaspace.
- String literal/interned string được quản lý như đối tượng trên Heap, dù thông tin constant pool của class có thể tham chiếu đến chúng.

### 3.2. ClassLoader và vòng đời Metaspace

Class được gắn với ClassLoader đã định nghĩa nó. Trong HotSpot, metadata của class có thể được thu hồi khi class được unload; việc unload thường chỉ có thể xảy ra khi ClassLoader định nghĩa class đó không còn reachable và JVM thực hiện một chu kỳ GC có khả năng class unloading.

Điều này giải thích vì sao một ứng dụng có thể gặp Metaspace tăng liên tục dù số lượng object trên Heap không tăng tương ứng. Một số nguyên nhân thường gặp:

- Ứng dụng liên tục sinh class động hoặc proxy.
- Framework tạo nhiều class cho các lần cấu hình hoặc triển khai.
- Một ClassLoader cũ vẫn bị giữ bởi static reference, thread, ThreadLocal, callback hoặc cache.
- Ứng dụng hot reload nhưng ClassLoader của phiên bản cũ không được giải phóng.
- Class được nạp với số lượng lớn và vẫn còn cần thiết trong suốt vòng đời ứng dụng.

ClassLoader leak có thể giữ lại cả metadata trong Metaspace lẫn các object trên Heap. Vì vậy, khi điều tra cần xem cả class loading/unloading, reference chain và vòng đời ClassLoader, không chỉ nhìn một con số heap.

### 3.3. Các tham số Metaspace

Ví dụ:

```bash
java -XX:MetaspaceSize=128m -XX:MaxMetaspaceSize=512m -jar application.jar
```

- `-XX:MetaspaceSize` là ngưỡng ban đầu liên quan đến thời điểm JVM cân nhắc GC dựa trên mức sử dụng Metaspace; nó không phải giới hạn cứng đơn giản tương đương `-Xmx`.
- `-XX:MaxMetaspaceSize` đặt giới hạn tối đa cho Metaspace.
- `-XX:CompressedClassSpaceSize` điều chỉnh không gian dành cho compressed class pointers khi tính năng tương ứng được sử dụng.

Không nên đặt `MaxMetaspaceSize` quá thấp chỉ để giảm bộ nhớ. Khi Metaspace tiến gần giới hạn, JVM có thể cần GC và class unloading để thu hồi metadata. Nếu không thu hồi đủ, ứng dụng có thể gặp `OutOfMemoryError: Metaspace` hoặc lỗi liên quan đến compressed class space.

## 4. JIT và Code Cache: mã máy được sinh ra khi chương trình chạy

### 4.1. Từ bytecode đến mã máy

Java compiler thường biên dịch mã nguồn thành bytecode trong file `.class`. Khi chạy, JVM có thể diễn giải bytecode bằng interpreter. HotSpot còn theo dõi hành vi thực thi, chẳng hạn method nào được gọi thường xuyên và nhánh nào thường được chọn. Khi một method hoặc đoạn code đủ nóng, JIT compiler có thể biên dịch nó thành mã máy phù hợp với kiến trúc CPU đang chạy.

Luồng khái quát:

```text
.java
  │ javac
  ▼
.class (bytecode)
  │
  ▼
JVM interpreter + runtime profiling
  │
  ├── Code ít được gọi: tiếp tục diễn giải
  │
  └── Code đủ nóng
        │
        ▼
      JIT compiler
        │
        ▼
      Mã máy native
        │
        ▼
      Code Cache
        │
        ▼
      CPU thực thi mã máy
```

HotSpot thường sử dụng các mức biên dịch khác nhau. C1 có thể tạo mã nhanh với chi phí biên dịch thấp; C2 thực hiện tối ưu hóa sâu hơn với chi phí biên dịch cao hơn. Khi bật tiered compilation, JVM có thể đi qua nhiều mức trước khi method đạt mức tối ưu cao hơn. Chi tiết phụ thuộc phiên bản JVM và các tùy chọn runtime.

JIT cũng có thể thực hiện **On-Stack Replacement (OSR)** để chuyển một vòng lặp đang chạy từ interpreter sang mã đã biên dịch. Một số tối ưu hóa dựa trên giả định về kiểu dữ liệu hoặc hành vi runtime. Khi giả định không còn đúng, JVM có thể deoptimize và quay về một mức thực thi ít tối ưu hơn để tiếp tục thu thập thông tin hoặc biên dịch lại.

### 4.2. Code Cache chứa gì?

Trong HotSpot, **Code Cache** là vùng native memory dùng để lưu các đoạn mã máy được JVM sinh ra, bao gồm compiled methods (thường được gọi là nmethods) và một số stub/runtime code. CPU có thể thực thi trực tiếp các đoạn mã này.

Code Cache không phải Java Heap:

- GC quản lý object trên Heap.
- JIT compiler sinh và quản lý mã máy trong Code Cache.
- Một method đã biên dịch không phải là một Java object thông thường mà ứng dụng có thể giữ bằng reference.
- Xóa object khỏi Heap không đồng nghĩa mã máy tương ứng lập tức biến mất khỏi Code Cache; JVM quản lý vòng đời compiled code riêng.

Ở một số phiên bản HotSpot có segmented code cache, các đoạn mã được phân vùng theo nhóm như non-method, profiled và non-profiled code. Đây là chi tiết triển khai có thể thay đổi theo phiên bản và cấu hình JVM.

### 4.3. Khi Code Cache đầy

Nếu Code Cache thiếu chỗ, JVM có thể gặp khó khăn khi tiếp tục biên dịch method mới. Tùy phiên bản và tình trạng code cache, JVM có thể dọn các compiled code không còn sử dụng, nhưng nếu không giải phóng đủ dung lượng thì JIT compilation có thể bị hạn chế hoặc tạm dừng. Ứng dụng vẫn có thể chạy bằng interpreter và những đoạn mã đã biên dịch còn hợp lệ, nhưng hiệu năng có thể giảm.

Tham số thường dùng:

```bash
java -XX:InitialCodeCacheSize=32m -XX:ReservedCodeCacheSize=240m -jar application.jar
```

- `-XX:InitialCodeCacheSize` đặt dung lượng ban đầu.
- `-XX:ReservedCodeCacheSize` đặt dung lượng Code Cache tối đa được reserve.

Các con số cần được chọn theo phiên bản JDK, workload và số lượng method thực sự nóng. Tăng Code Cache không sửa được nguyên nhân sinh class/method quá nhiều và cũng không thay thế việc đo đạc.

## 5. So sánh ba vùng nhớ

| Tiêu chí | Java Heap | Metaspace | Code Cache |
|---|---|---|---|
| Dữ liệu chính | Object và array | Class metadata | Mã máy do JVM/JIT sinh ra |
| Vị trí trong HotSpot | Java heap | Native memory | Native memory |
| Đơn vị quản lý chính | Garbage Collector | Class loading/unloading và quản lý metadata | JIT compiler và quản lý compiled code |
| Tăng khi | Số lượng/kích thước object sống tăng | Nhiều class được nạp hoặc metadata tăng | Nhiều method được biên dịch hoặc code được sinh ra |
| Lỗi/triệu chứng liên quan | `OutOfMemoryError: Java heap space` | `OutOfMemoryError: Metaspace` | Code Cache đầy, JIT compilation bị hạn chế |
| Tham số thường gặp | `-Xms`, `-Xmx` | `-XX:MetaspaceSize`, `-XX:MaxMetaspaceSize` | `-XX:InitialCodeCacheSize`, `-XX:ReservedCodeCacheSize` |

Ba vùng này có quan hệ trong cùng một tiến trình nhưng cần được theo dõi riêng. Một ứng dụng có thể có heap còn nhiều chỗ nhưng vẫn hết Metaspace; cũng có thể heap và Metaspace ổn định trong khi Code Cache gần đầy.

## 6. CRaC tác động thế nào đến các vùng nhớ?

### 6.1. Checkpoint là lưu trạng thái tiến trình

CRaC phối hợp giữa JVM và cơ chế checkpoint/restore của hệ điều hành để lưu trạng thái của một tiến trình đang chạy. Khi restore, tiến trình được khôi phục từ checkpoint thay vì thực hiện toàn bộ quá trình khởi động ứng dụng từ đầu.

Điểm quan trọng là checkpoint của CRaC không giống việc serialize từng object thành một định dạng dữ liệu độc lập. Nó lưu trạng thái tiến trình theo cơ chế và giới hạn của runtime/nền tảng. Do đó, checkpoint phụ thuộc chặt vào môi trường tương thích: JVM build, kiến trúc, thư viện native, cấu hình và các điều kiện hệ điều hành được hỗ trợ.

Với ba vùng nhớ:

- **Heap**: object, array, cache và trạng thái ứng dụng đang tồn tại tại thời điểm checkpoint thuộc trạng thái bộ nhớ của tiến trình. Những object đã được tạo và còn reachable có thể sẵn sàng ngay sau restore.
- **Metaspace**: trạng thái class đã nạp và metadata JVM quản lý là một phần trạng thái runtime của tiến trình. Ứng dụng có thể tránh phải nạp và liên kết lại một số class đã được chuẩn bị trước checkpoint.
- **Code Cache**: mã máy do JIT tạo ra được lưu trong vùng nhớ native của tiến trình. Khi checkpoint/restore giữ được các trang nhớ tương ứng, compiled code có thể được phục hồi cùng tiến trình. Việc một compiled method cụ thể tiếp tục được sử dụng, bị invalidate/deoptimize hay được biên dịch lại còn phụ thuộc JVM build, nền tảng và điều kiện runtime; cần xác nhận bằng log và đo hiệu năng trên môi trường triển khai thực tế.

Vì vậy, có thể chuẩn bị ứng dụng trước checkpoint để giảm công việc khởi động sau restore, nhưng không nên mặc định rằng mọi class hoặc mọi đoạn mã JIT sẽ luôn được giữ nguyên và sử dụng trong mọi môi trường.

### 6.2. Warm-up trước checkpoint

Nếu checkpoint được tạo ngay sau khi JVM vừa khởi động, nhiều class có thể chưa được nạp, cache ứng dụng còn rỗng và các method quan trọng chưa đủ nóng để JIT biên dịch. Sau restore, ứng dụng vẫn phải thực hiện một phần công việc khởi tạo và warm-up.

Một quy trình chuẩn bị có thể gồm:

1. Khởi động ứng dụng bằng đúng JVM và cấu hình dự kiến dùng khi triển khai.
2. Thực hiện các bước khởi tạo an toàn: nạp cấu hình, chuẩn bị dependency, khởi tạo cache cần thiết.
3. Gửi workload đại diện qua các luồng xử lý quan trọng để class được nạp và method nóng có cơ hội được JIT biên dịch.
4. Quan sát heap, Metaspace, Code Cache, GC và thời gian xử lý để xác định trạng thái đã ổn định.
5. Đưa ứng dụng về trạng thái có thể checkpoint: không còn request hoặc tác vụ dở dang mà ứng dụng không thể phục hồi an toàn.
6. Thực hiện checkpoint và kiểm tra hành vi sau restore bằng cùng điều kiện triển khai dự kiến.

Workload warm-up nên đại diện cho traffic thật. Chỉ gọi một endpoint đơn giản có thể làm nóng một phần code nhưng bỏ sót các luồng xử lý quan trọng. Ngược lại, warm-up quá rộng có thể làm heap giữ nhiều cache không cần thiết, nạp quá nhiều class hoặc tăng kích thước Code Cache, khiến checkpoint lớn hơn và mức dùng bộ nhớ sau restore cao hơn.

### 6.3. Trạng thái bộ nhớ và tài nguyên bên ngoài

Không phải mọi thứ mà ứng dụng nhìn thấy đều được bảo toàn theo cùng cách với các trang nhớ. Kết nối mạng, socket, file descriptor, thread tương tác với hệ điều hành, lease, token có thời hạn và kết nối tới database có thể cần được đóng trước checkpoint hoặc tạo lại sau restore.

CRaC cung cấp cơ chế đăng ký resource callback, thường thông qua `org.crac.Resource`, để ứng dụng chuẩn bị trước checkpoint và phục hồi sau restore. Ví dụ khung:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class AppResource implements Resource {

    public AppResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Dừng nhận việc mới, đóng hoặc giải phóng tài nguyên cần xử lý.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Tạo lại kết nối và làm mới tài nguyên phụ thuộc thời gian.
    }
}
```

Đây là skeleton minh họa. Hành vi cụ thể cần phù hợp với thư viện đang sử dụng và phiên bản CRaC. Các callback giúp ứng dụng xử lý tài nguyên; chúng không thay thế việc hiểu trạng thái Heap, Metaspace và Code Cache tại thời điểm checkpoint.

## 7. Theo dõi và chẩn đoán

Khi ứng dụng chạy lâu hoặc sau restore, cần xác định vùng nhớ nào đang tăng. Không nên chỉ nhìn tổng RAM hoặc heap usage rồi kết luận ngay là memory leak.

### 7.1. Kiểm tra Heap

```bash
jcmd <pid> GC.heap_info
```

Lệnh này cung cấp thông tin heap và GC hiện tại. Có thể kết hợp GC log:

```bash
java -Xlog:gc*,safepoint=info -jar application.jar
```

GC log giúp quan sát tần suất thu gom, lượng heap trước/sau GC và thời gian pause. Nếu cần điều tra object giữ bộ nhớ, có thể thu heap dump bằng công cụ phù hợp và phân tích dominator tree, retained size cùng reference chain.

### 7.2. Kiểm tra Metaspace và native memory

Có thể bật Native Memory Tracking (NMT) khi khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar application.jar
```

Sau đó truy vấn:

```bash
jcmd <pid> VM.native_memory summary
```

NMT hỗ trợ phân loại một phần native memory do JVM quản lý. NMT phải được bật từ lúc JVM khởi động và có overhead; số liệu của nó không phải lúc nào cũng bao phủ mọi native allocation do thư viện bên thứ ba thực hiện.

Để theo dõi class loading và unloading:

```bash
java -Xlog:class+load=info,class+unload=info -jar application.jar
```

Nếu Metaspace tăng liên tục, hãy đối chiếu số class đã nạp, số class được unload, số lượng ClassLoader và các reference giữ ClassLoader. Tăng `MaxMetaspaceSize` có thể trì hoãn lỗi nhưng không xử lý được ClassLoader leak.

### 7.3. Kiểm tra Code Cache và JIT

Với HotSpot hỗ trợ diagnostic command tương ứng, có thể xem thống kê Code Cache:

```bash
jcmd <pid> Compiler.codecache
```

Để ghi log hoạt động biên dịch:

```bash
java -Xlog:jit+compilation=debug -jar application.jar
```

Hãy kiểm tra dung lượng đã dùng, dung lượng còn lại, số method được biên dịch và thông báo Code Cache đầy. Khi đánh giá CRaC, so sánh số liệu trước checkpoint và sau restore, đồng thời đo latency của các endpoint đại diện. Một con số Code Cache được khôi phục không tự nó chứng minh rằng mọi method quan trọng đã được thực thi bằng mã máy sau restore.

### 7.4. Đọc đúng các loại lỗi

| Triệu chứng | Vùng cần kiểm tra trước | Hướng điều tra |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Heap | Object giữ lâu, cache không giới hạn, heap quá nhỏ hoặc workload tăng |
| `OutOfMemoryError: Metaspace` | Metaspace | Class tăng liên tục, ClassLoader leak, giới hạn Metaspace quá thấp |
| Lỗi liên quan `Compressed class space` | Compressed class space | Số lượng class và cấu hình compressed class pointers |
| Log cho biết Code Cache đầy hoặc compiler bị disabled | Code Cache | Dung lượng Code Cache, số lượng compiled method và JIT activity |
| Container bị OOM kill dù heap chưa đầy | Tổng bộ nhớ tiến trình/container | Metaspace, Code Cache, thread stack, direct buffer, native library và phần bộ nhớ khác |

Heap dump hữu ích cho object graph, nhưng không đủ để giải thích toàn bộ native memory. Ngược lại, NMT giúp xem các nhóm native memory của JVM nhưng không thay thế heap dump khi cần tìm object giữ reference.

## 8. Những sai lầm thường gặp khi tối ưu cho CRaC

### Chỉ tăng `-Xmx` khi tổng RAM tăng

`-Xmx` chỉ đặt giới hạn Java Heap. Nếu Metaspace, Code Cache, direct buffer hoặc thread stack tăng, tăng heap có thể khiến tổng bộ nhớ tiến trình còn lớn hơn và làm container dễ chạm giới hạn hơn.

### Cho rằng Metaspace chứa toàn bộ object static

Static field gắn với class nhưng không có nghĩa mọi giá trị static đều nằm trực tiếp trong Metaspace. Đối tượng được tham chiếu bởi static field vẫn là object trên Heap. Một static cache có thể làm Heap tăng dù số class và Metaspace không đổi.

### Cho rằng Code Cache là nơi lưu bytecode

Bytecode nằm trong class representation và được JVM quản lý cùng trạng thái class. Code Cache chủ yếu chứa mã máy được sinh ra trong quá trình thực thi, cùng một số mã runtime do JVM tạo.

### Checkpoint càng muộn càng tốt

Checkpoint sau warm-up có thể giảm công việc sau restore, nhưng chờ quá lâu có thể làm cache phình to, giữ dữ liệu tạm không cần thiết, tăng số class đã nạp hoặc làm checkpoint lớn hơn. Cần chọn thời điểm dựa trên số đo và trạng thái nghiệp vụ.

### Mặc định mọi kết nối vẫn hợp lệ sau restore

Một object Java đại diện cho connection có thể vẫn xuất hiện trong Heap được khôi phục, nhưng socket hoặc phiên làm việc ở hệ điều hành/server có thể đã hết hiệu lực. Resource callback cần đóng, tạo lại hoặc xác thực lại các tài nguyên phụ thuộc môi trường.

### Tăng giới hạn mà không tìm nguyên nhân

Tăng `MaxMetaspaceSize` hoặc `ReservedCodeCacheSize` có thể giúp ứng dụng có thêm không gian, nhưng nếu class được tạo không giới hạn hoặc workload khiến JIT sinh quá nhiều mã, vấn đề gốc vẫn còn. Hãy xác định vùng tăng, tốc độ tăng và nguyên nhân trước khi điều chỉnh.

## 9. Quy trình kiểm tra thực tế

Khi tối ưu một ứng dụng Java dùng CRaC, có thể thực hiện theo quy trình sau:

1. **Ghi baseline trước checkpoint**: heap used/committed, GC activity, Metaspace, Code Cache, số class đã nạp, RSS và thời gian xử lý request.
2. **Chạy warm-up có kiểm soát**: dùng workload đại diện, tránh tạo dữ liệu thử nghiệm không cần thiết hoặc làm thay đổi trạng thái nghiệp vụ.
3. **Kiểm tra các vùng nhớ**: xác định heap tăng do object sống, Metaspace tăng do class, hay Code Cache tăng do JIT compilation.
4. **Kiểm tra điều kiện checkpoint**: xử lý request đang chạy, thread và tài nguyên ngoài bộ nhớ theo yêu cầu của CRaC và thư viện ứng dụng.
5. **Tạo checkpoint rồi restore**: xác nhận ứng dụng khởi động và nhận request thành công trong môi trường tương thích.
6. **Đo lại sau restore**: so sánh thời gian sẵn sàng phục vụ, latency của workload đại diện, GC, class loading và JIT compilation.
7. **Lặp lại với cấu hình khác**: chỉ thay đổi một nhóm tham số mỗi lần để biết thay đổi nào tạo ra tác động.

Một checkpoint tốt không chỉ có thời gian restore ngắn. Ứng dụng còn phải có trạng thái nghiệp vụ hợp lệ, tài nguyên bên ngoài hoạt động đúng, bộ nhớ nằm trong giới hạn triển khai và hiệu năng ổn định khi nhận traffic thật.

## 10. Ghi nhớ khi đọc số liệu JVM

Khi nhìn một báo cáo bộ nhớ, hãy phân biệt ba khái niệm:

- **Used**: lượng dữ liệu hiện đang sử dụng.
- **Committed**: lượng bộ nhớ JVM đã cam kết có thể sử dụng theo cơ chế quản lý của vùng nhớ.
- **Reserved**: vùng địa chỉ bộ nhớ được dành trước; reserved không đồng nghĩa toàn bộ vùng đó đã chiếm RAM vật lý.

Vì vậy, không nên cộng mọi giá trị reserved để suy ra RAM thực tế. RSS phản ánh các trang bộ nhớ đang resident của tiến trình, còn số liệu heap, Metaspace, Code Cache và NMT có cách đo và phạm vi riêng.

Khi đọc log hoặc dashboard, luôn xác định rõ số liệu đang nói về Heap, native memory, Code Cache, committed hay reserved. Đây là bước đầu tiên để phân biệt một heap leak, một ClassLoader leak, Code Cache pressure và việc tiến trình dùng nhiều native memory sau CRaC restore.


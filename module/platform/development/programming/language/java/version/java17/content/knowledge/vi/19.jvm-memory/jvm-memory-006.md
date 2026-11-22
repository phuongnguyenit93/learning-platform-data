# Đặt giới hạn heap phù hợp môi trường triển khai

## 1. Vì sao phải đặt giới hạn heap?

Java Virtual Machine (JVM) quản lý vùng nhớ heap để cấp phát object. Khi ứng dụng chạy trong container, VM trên máy ảo, máy chủ vật lý hoặc Kubernetes, lượng RAM mà tiến trình có thể sử dụng bị giới hạn bởi tài nguyên môi trường triển khai.

Nếu heap được cấu hình quá lớn, tiến trình có thể vượt giới hạn bộ nhớ của container do còn cần native memory, thread stack, metaspace, code cache, direct buffer và các vùng nhớ khác. Hệ điều hành hoặc container runtime có thể kết thúc tiến trình vì vượt memory limit, kể cả khi Java heap chưa đầy.

Nếu heap quá nhỏ, garbage collector phải thu hồi thường xuyên, độ trễ tăng, throughput giảm và ứng dụng có thể ném `OutOfMemoryError: Java heap space`.

Việc đặt giới hạn heap cần trả lời ba câu hỏi:

1. JVM nhìn thấy bao nhiêu RAM trong môi trường thực tế?
2. Bao nhiêu RAM có thể dành cho Java heap sau khi trừ các khoản native/non-heap và phần dự phòng?
3. Heap cần bao nhiêu để xử lý workload đỉnh với mức GC và latency chấp nhận được?

Trong Java 17, các lựa chọn chính là:

- `-Xms`: heap ban đầu và mức heap tối thiểu.
- `-Xmx`: giới hạn heap tối đa.
- `-XX:InitialRAMPercentage`: tỷ lệ RAM dùng để tính heap ban đầu nếu không đặt `-Xms`.
- `-XX:MaxRAMPercentage`: tỷ lệ RAM dùng để tính heap tối đa nếu không đặt `-Xmx`.
- Container awareness của HotSpot: nhận biết giới hạn tài nguyên container trên Linux để JVM tính ergonomics phù hợp.

**Heap max không phải memory limit của toàn bộ tiến trình.** Đây là nguyên tắc quan trọng nhất khi chạy Java trong container.

## 2. Phân biệt heap với tổng bộ nhớ tiến trình

### 2.1. Những vùng nhớ chính của một tiến trình Java

Một JVM sử dụng nhiều loại bộ nhớ:

| Vùng nhớ | Mục đích | Có nằm trong Java heap không? |
|---|---|---|
| Java heap | Object, array và phần lớn dữ liệu ứng dụng được cấp phát bằng `new` | Có |
| Metaspace | Metadata của class, method, runtime constant pool | Không |
| Compressed class space | Một phần metadata class khi compressed class pointers được bật | Không |
| Code cache | Mã máy được JIT compiler sinh ra | Không |
| Thread stack | Stack frame, local variable và call state của từng thread | Không |
| Direct buffer | Buffer ngoài heap, thường dùng cho I/O hiệu năng cao | Không |
| GC native structures | Cấu trúc dữ liệu và metadata nội bộ của garbage collector | Không |
| JNI/native library | Bộ nhớ do thư viện native hoặc code JNI cấp phát | Không |
| JVM internal/native | Các cấu trúc nội bộ khác của VM | Không |

Ngoài ra, tiến trình còn cần bộ nhớ cho thư viện hệ thống, vùng ánh xạ file, socket và những hoạt động của runtime. Cách hệ điều hành/container tính memory usage có thể bao gồm thêm page cache hoặc các khoản ngoài heap.

### 2.2. Mô hình ngân sách bộ nhớ

Có thể hình dung:

```text
Container memory limit
|
+-- Java heap (tối đa Xmx)
|
+-- Metaspace và class metadata
|
+-- JIT code cache
|
+-- Thread stacks
|
+-- Direct / mapped buffers
|
+-- GC và JVM native structures
|
+-- JNI, native libraries và các vùng nhớ khác
|
+-- Phần dự phòng cho dao động tải và runtime
~~~

Một công thức lập ngân sách đơn giản:

\[
M_{limit} \geq M_{heap} + M_{native} + M_{reserve}
\]

Trong đó:

- (M_{limit}): memory limit thực tế của container/tiến trình.
- (M_{heap}): heap tối đa dự kiến.
- (M_{native}): các khoản ngoài heap và native memory.
- (M_{reserve}): khoảng trống an toàn cho dao động workload, GC, thread tăng thêm và overhead hệ thống.

Đây là mô hình lập kế hoạch, không phải phép đo chính xác tuyệt đối. Hãy đo RSS/cgroup usage trong môi trường gần production để xác định các khoản thực tế.

### 2.3. Xmx không đồng nghĩa RSS

`-Xmx` đặt giới hạn trên của Java heap. JVM không nhất thiết sử dụng ngay toàn bộ lượng đó trong RAM vật lý.

Các khái niệm khác nhau:

- **Maximum heap:** giới hạn trên JVM được phép mở rộng heap tới.
- **Committed heap:** vùng heap JVM đã cam kết sử dụng.
- **Used heap:** phần heap đang chứa object còn được tính là đang sử dụng.
- **RSS (Resident Set Size):** lượng trang bộ nhớ của tiến trình đang hiện diện trong RAM.
- **Container memory usage:** số liệu bộ nhớ mà cgroup/container runtime ghi nhận theo cơ chế của nền tảng.

Vì vậy, không thể suy ra RSS bằng `Xmx`, và cũng không thể kết luận container an toàn chỉ vì heap used đang thấp.

## 3. Các tùy chọn heap quan trọng trong Java 17

### 3.1. -Xms: heap ban đầu

`-Xms` chỉ định kích thước heap ban đầu:

```shell
java -Xms256m -jar app.jar
```

Giá trị này cũng đặt mức heap tối thiểu mà JVM duy trì theo cấu hình. JVM có thể tăng heap khi cần, nhưng không mở rộng vượt giới hạn tối đa.

Ví dụ:

```shell
java -Xms512m -Xmx1024m -jar app.jar
```

Ứng dụng bắt đầu với heap 512 MB và có thể mở rộng tới 1024 MB.

Không nên đặt `-Xms` bằng toàn bộ container limit. Heap không phải vùng nhớ duy nhất của JVM; phần còn lại vẫn cần chỗ cho native memory và runtime.

### 3.2. -Xmx: heap tối đa

`-Xmx` đặt giới hạn trên của Java heap:

```shell
java -Xmx768m -jar app.jar
```

Nếu ứng dụng cần cấp phát object vượt khả năng thu hồi và heap không thể mở rộng thêm, JVM có thể ném `OutOfMemoryError: Java heap space`.

`-Xmx` không giới hạn:

- Metaspace.
- Thread stack.
- Direct buffer.
- Native allocation từ JNI hoặc thư viện.
- Toàn bộ RSS của tiến trình.

Vì thế, đặt `-Xmx` bằng memory limit của container là cấu hình nguy hiểm trong hầu hết ứng dụng.

### 3.3. InitialRAMPercentage và MaxRAMPercentage

HotSpot có các tùy chọn ergonomics theo phần trăm:

```shell
java \
  -XX:InitialRAMPercentage=20.0 \
  -XX:MaxRAMPercentage=60.0 \
  -jar app.jar
```

- `InitialRAMPercentage`: tỷ lệ RAM khả dụng mà JVM dùng để tính heap ban đầu nếu không đặt `-Xms`.
- `MaxRAMPercentage`: tỷ lệ RAM khả dụng mà JVM dùng để tính heap tối đa nếu không đặt `-Xmx`.

Trên HotSpot Java 17, các giá trị mặc định phổ biến là:

| Flag | Giá trị mặc định HotSpot thường gặp | Vai trò |
|---|---:|---|
| `InitialRAMPercentage` | 1.5625 | Tính heap ban đầu |
| `MaxRAMPercentage` | 25.0 | Tính heap tối đa |
| `MinRAMPercentage` | 50.0 | Giới hạn heap theo tỷ lệ cho hệ thống RAM nhỏ |

Đây là giá trị mặc định của HotSpot, không phải cam kết cho mọi JVM vendor hoặc mọi phiên bản/provider. Hãy xem flag thực tế của runtime đang triển khai.

**Lưu ý về tên `MinRAMPercentage`:** flag này không phải phần trăm heap tối thiểu ban đầu. Nó được dùng để tính giới hạn heap tối đa trong trường hợp hệ thống có lượng RAM nhỏ theo quy tắc ergonomics của HotSpot.

### 3.4. Xms/Xmx và các percentage flag có quan hệ ưu tiên

Khi đặt `-Xmx`, giá trị explicit này quyết định heap max; `MaxRAMPercentage` không còn là nguồn tính heap max. Tương tự, `-Xms` ghi đè cách tính initial heap từ `InitialRAMPercentage`.

Nên chọn một cách cấu hình rõ:

| Mục tiêu | Cấu hình |
|---|---|
| Môi trường có kích thước cố định, cần heap max rõ ràng | `-Xms...` và `-Xmx...` |
| Cùng artifact chạy trên nhiều container size | `InitialRAMPercentage` và `MaxRAMPercentage` |
| Muốn heap max cố định nhưng initial heap theo tỷ lệ | `-Xmx...` cùng `InitialRAMPercentage` |

Tránh cấu hình nhiều flag chồng chéo rồi không kiểm tra giá trị cuối cùng mà JVM áp dụng.

### 3.5. MaxRAM

`-XX:MaxRAM` ảnh hưởng lượng RAM tối đa mà HotSpot dùng làm cơ sở cho ergonomics:

```shell
java -XX:MaxRAM=2g -XX:MaxRAMPercentage=60.0 -jar app.jar
```

Trong triển khai container thông thường, không cần tự đặt `MaxRAM` nếu JVM đã nhận diện đúng cgroup memory limit. Chỉ điều chỉnh khi có lý do vận hành rõ ràng và đã xác nhận giá trị JVM đang nhìn thấy.

## 4. Container awareness trong Java 17

### 4.1. JVM cần biết giới hạn container

Nếu JVM chỉ nhìn thấy RAM của host, trong khi container bị giới hạn thấp hơn nhiều, JVM có thể tính heap quá lớn cho môi trường thực tế.

Ví dụ:

- Máy host có 64 GiB RAM.
- Container chỉ có memory limit 1 GiB.
- JVM không nhận diện container limit và tính heap theo RAM host.

Heap max khi đó có thể vượt xa lượng memory container cho phép. Khi container dùng hết giới hạn, runtime có thể bị hệ điều hành kết thúc.

HotSpot có **container support** để đọc giới hạn tài nguyên từ Linux control groups (cgroups) và dùng thông tin đó cho ergonomics.

### 4.2. UseContainerSupport

Trên Linux, `-XX:+UseContainerSupport` được bật mặc định trong các bản HotSpot hiện đại, bao gồm Java 17. JVM có thể sử dụng giới hạn memory/CPU của container khi tính tài nguyên khả dụng.

Kiểm tra flag:

```shell
java -XX:+PrintFlagsFinal -version
```

Tìm dòng `UseContainerSupport`. Trên Linux, cũng có thể xem thông tin hệ thống/container:

```shell
java -XshowSettings:system -version
```

Output tùy nền tảng và cgroup provider, nhưng có thể hiển thị thông tin giới hạn tài nguyên mà JVM nhận diện.

Không cần thêm `-XX:+UseContainerSupport` vào mọi lệnh Java 17 nếu runtime đã bật mặc định. Quan trọng là xác nhận JVM thực tế nhận diện đúng giới hạn, đặc biệt khi chạy image/JDK vendor khác nhau hoặc cấu hình cgroup đặc biệt.

### 4.3. cgroups v1 và v2

Linux dùng control groups để theo dõi và giới hạn tài nguyên. Tùy host, container runtime và cấu hình kernel, môi trường có thể dùng cgroups v1 hoặc v2.

Các file thường gặp:

| Cgroup | Memory limit | Memory usage hiện tại |
|---|---|---|
| v1 | `memory.limit_in_bytes` | `memory.usage_in_bytes` |
| v2 | `memory.max` | `memory.current` |

Ví dụ đường dẫn thường gặp:

```text
/sys/fs/cgroup/memory.max
/sys/fs/cgroup/memory.current
```

Ở cgroup v1, đường dẫn có thể nằm dưới:

```text
/sys/fs/cgroup/memory/memory.limit_in_bytes
/sys/fs/cgroup/memory/memory.usage_in_bytes
```

Đường dẫn thực tế có thể khác theo mount namespace và runtime. Không hardcode một đường dẫn cho mọi container.

### 4.4. Container limit khác host RAM

Với container memory limit 1 GiB, JVM nên tính ergonomics dựa trên giới hạn mà container cung cấp thay vì mặc định dùng toàn bộ RAM host. Tuy nhiên, **container limit vẫn là ngân sách tổng**, không phải ngân sách heap.

Nếu JVM nhận diện đúng 1 GiB và đặt `MaxRAMPercentage=75`, heap max có thể gần 768 MiB, nhưng khoảng còn lại phải đủ cho metaspace, stacks, direct buffers, native code và overhead. Với ứng dụng có nhiều thread hoặc NIO/direct buffer, tỷ lệ đó có thể quá cao.

## 5. Docker và Kubernetes: giới hạn nào thực sự có tác dụng?

### 5.1. Docker memory limit

Ví dụ chạy container với giới hạn 1 GiB:

```shell
docker run --memory=1g my-java-app:17
```

Container runtime thiết lập giới hạn cgroup. JVM Java 17 có thể nhận diện giới hạn đó trên Linux khi container support hoạt động.

Không nên chỉ nhìn vào RAM host hoặc kết quả `free -m` trong một môi trường khác rồi quyết định heap cho container.

### 5.2. Kubernetes requests và limits

Ví dụ cấu hình container:

```yaml
resources:
  requests:
    memory: "512Mi"
  limits:
    memory: "1Gi"
```

Hai trường có ý nghĩa khác nhau:

- **request**: lượng tài nguyên Kubernetes dùng cho scheduling và quyết định đặt Pod lên node nào.
- **limit**: giới hạn memory được áp dụng cho container qua cơ chế của node/runtime.

JVM cần được lập ngân sách theo memory limit thực tế. Không dùng request như thể đó là giới hạn bộ nhớ tối đa của container.

Nếu không đặt limit, JVM có thể nhìn thấy lượng RAM khả dụng lớn hơn mức mà nền tảng vận hành mong muốn. Khi triển khai production, cần hiểu rõ chính sách quota/limit của namespace, node và container.

### 5.3. Ví dụ cấu hình heap percentage trong Kubernetes

```yaml
containers:
  - name: application
    image: example/application:17
    env:
      - name: JAVA_TOOL_OPTIONS
        value: "-XX:InitialRAMPercentage=20.0 -XX:MaxRAMPercentage=60.0"
    resources:
      requests:
        memory: "512Mi"
      limits:
        memory: "1Gi"
~~~

Trong ví dụ, `MaxRAMPercentage=60.0` là **giá trị minh họa để bắt đầu thử nghiệm**, không phải khuyến nghị cố định cho mọi ứng dụng. Phải đo peak native/non-heap usage và heap live set dưới tải thật trước khi chốt.

`JAVA_TOOL_OPTIONS` được JVM nhận để bổ sung tùy chọn khi khởi tạo. Cần kiểm tra log khởi động để xác nhận option được nhận, tránh vô tình đặt trùng hoặc xung đột với command line của entrypoint.

## 6. Chọn Xmx theo ngân sách thay vì theo cảm tính

### 6.1. Bắt đầu từ memory limit

Giả sử container có memory limit 1 GiB:

```text
Container limit:           1024 MiB
Native/non-heap peak:       220 MiB (ước lượng ban đầu)
Safety reserve:             120 MiB
------------------------------------
Budget còn lại cho heap:    684 MiB
~~~

Với các giả định này, có thể bắt đầu thử `-Xmx640m`. Sau đó đo lại trong workload thực tế để xác nhận:

- Heap có đủ cho live set và allocation burst không?
- Native/non-heap peak có thực sự gần 220 MiB không?
- RSS/cgroup usage có giữ khoảng trống an toàn không?
- GC pause và throughput có đạt mục tiêu không?

Nếu native memory tăng theo số thread hoặc số kết nối, con số 220 MiB sẽ thay đổi. Không coi phép trừ ban đầu là kết quả đo.

### 6.2. Ví dụ dùng MaxRAMPercentage

Với container 1 GiB:

```shell
java \
  -XX:InitialRAMPercentage=20.0 \
  -XX:MaxRAMPercentage=60.0 \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/diagnostics/heap \
  -jar app.jar
```

Nếu JVM nhận diện 1 GiB là RAM khả dụng cho ergonomics, 60% tương đương xấp xỉ 614 MiB theo phép tính thô. Kích thước thực tế còn phụ thuộc ergonomics, alignment và cấu hình runtime.

Percentage flags hữu ích khi cùng một image chạy ở nhiều memory tier. Nếu container limit thay đổi, JVM có thể tính heap max theo tỷ lệ thay vì giữ một `-Xmx` cứng cho mọi môi trường.

### 6.3. Ví dụ dùng Xms và Xmx cố định

Nếu mỗi môi trường có ngân sách rõ ràng:

```shell
java -Xms384m -Xmx640m -jar app.jar
```

Ưu điểm:

- Heap max được xác định rõ.
- Dễ so sánh giữa các lần triển khai có cùng memory limit.
- Ít phụ thuộc vào phép tính phần trăm.

Đổi lại, khi cùng artifact chạy trên container có kích thước khác nhau, phải quản lý cấu hình theo môi trường.

### 6.4. Khi nào đặt Xms bằng Xmx?

Một số hệ thống đặt:

```shell
java -Xms640m -Xmx640m -jar app.jar
```

Điều này giữ kích thước heap ban đầu và tối đa bằng nhau, giúp hành vi heap ít thay đổi trong quá trình chạy. Tuy nhiên:

- Heap committed ban đầu lớn hơn cấu hình Xms thấp.
- Container cần đủ headroom cho các vùng native/non-heap.
- Không có nghĩa toàn bộ 640 MiB lập tức trở thành RSS vật lý.
- Không tự động làm GC nhanh hơn hoặc loại bỏ memory leak.

Chỉ chọn Xms bằng Xmx khi đã hiểu mức heap cần thiết từ lúc khởi động và đo được tác động đến memory footprint.

## 7. Các khoản ngoài heap cần tính đến

### 7.1. Metaspace

Metaspace lưu metadata của class và được cấp phát ngoài Java heap. Ứng dụng có nhiều class, dynamic proxy, classloader hoặc hot reload có thể dùng nhiều metaspace.

Flag:

```shell
-XX:MaxMetaspaceSize=256m
```

đặt giới hạn metaspace. Không nên đặt giới hạn quá thấp chỉ để giảm RSS; nếu metadata cần nhiều hơn, JVM có thể ném `OutOfMemoryError: Metaspace`. Hãy đo trước khi áp dụng.

### 7.2. Thread stack

Mỗi Java thread cần stack riêng. Tổng bộ nhớ stack có thể tăng theo số lượng thread:

~~~text
Total thread stack budget
≈ thread count × stack size per thread
~~~

Flag `-Xss` điều chỉnh kích thước stack mỗi thread:

```shell
java -Xss512k -jar app.jar
```

Không hạ `-Xss` chỉ để ép ứng dụng chạy trong container nhỏ. Stack quá thấp có thể gây `StackOverflowError` khi call depth lớn hoặc framework cần nhiều stack frame. Giảm số thread không cần thiết thường là hướng đầu tiên cần xem xét.

### 7.3. Direct buffers

NIO có thể sử dụng direct byte buffer ngoài heap:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
~~~

Direct buffer hữu ích cho một số đường I/O nhưng chiếm native memory. Có thể đặt giới hạn bằng:

```shell
-XX:MaxDirectMemorySize=256m
```

Flag này giới hạn tổng dung lượng direct buffer allocation theo cơ chế JVM. Không đặt quá thấp nếu thư viện network/database cần nhiều direct buffer; ứng dụng có thể gặp `OutOfMemoryError: Direct buffer memory`.

Không nhầm direct buffer với heap object wrapper: đối tượng `ByteBuffer` vẫn có phần metadata/object trên heap, còn vùng dữ liệu direct nằm ngoài heap.

### 7.4. Code cache và GC structures

JIT compiler tạo mã máy lưu trong code cache; garbage collector cũng cần native structures, remembered sets, mark bitmaps hoặc metadata tùy collector.

Các khoản này thường được JVM quản lý tự động. Không nên tùy tiện giảm code cache hoặc thay đổi hàng loạt GC flags chỉ để khớp một con số RSS mà chưa xác định vùng nhớ đang tăng.

### 7.5. JNI và native libraries

Thư viện native có thể cấp phát bộ nhớ ngoài heap qua malloc hoặc API native. Những allocation này không nhất thiết xuất hiện trong heap dump.

Nếu:

- Heap used thấp.
- Metaspace ổn định.
- RSS/cgroup usage vẫn tăng.

thì cần xem xét direct buffer, thread stacks, JNI/native library và các mapping ngoài heap. Heap dump đơn thuần không đủ để giải thích mọi trường hợp.

## 8. Đo heap và bộ nhớ thực tế

### 8.1. Runtime API

Java cung cấp thông tin cơ bản:

```java
public class HeapUsage {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();

        long max = runtime.maxMemory();
        long committed = runtime.totalMemory();
        long free = runtime.freeMemory();
        long used = committed - free;

        System.out.printf("Heap max: %.1f MiB%n", toMiB(max));
        System.out.printf("Heap committed: %.1f MiB%n", toMiB(committed));
        System.out.printf("Heap used: %.1f MiB%n", toMiB(used));
    }

    private static double toMiB(long bytes) {
        return bytes / 1024.0 / 1024.0;
    }
}
```

Ý nghĩa:

- `maxMemory()`: heap max JVM có thể sử dụng, thường tương ứng giới hạn heap sau ergonomics.
- `totalMemory()`: heap hiện đã committed.
- `freeMemory()`: phần còn trống trong heap committed.
- `totalMemory() - freeMemory()`: ước lượng heap used tại thời điểm đọc.

Các giá trị thay đổi theo thời gian và có thể thay đổi sau GC. Chúng không đo tổng RSS của tiến trình.

### 8.2. MemoryMXBean

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = memoryBean.getHeapMemoryUsage();
MemoryUsage nonHeap = memoryBean.getNonHeapMemoryUsage();

System.out.println("Heap used: " + heap.getUsed());
System.out.println("Heap committed: " + heap.getCommitted());
System.out.println("Heap max: " + heap.getMax());
System.out.println("Non-heap used: " + nonHeap.getUsed());
System.out.println("Non-heap committed: " + nonHeap.getCommitted());
```

`MemoryMXBean` cho biết heap và non-heap usage theo góc nhìn JVM. Nó không bao gồm mọi native allocation của thư viện bên thứ ba.

### 8.3. Theo dõi direct và mapped buffers

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.printf(
            "%s: count=%d, used=%d, capacity=%d%n",
            pool.getName(),
            pool.getCount(),
            pool.getMemoryUsed(),
            pool.getTotalCapacity()
    );
}
```

Các pool thường có tên như `direct` và `mapped`. Số liệu giúp quan sát vùng buffer ngoài heap mà JVM quản lý.

### 8.4. Theo dõi số lượng thread

```java
int threadCount = ManagementFactory.getThreadMXBean()
        .getThreadCount();
System.out.println("Live threads: " + threadCount);
```

Nếu thread count tăng bất thường, tổng stack memory cũng có thể tăng. Kết hợp thread metrics với `-Xss` và RSS để hiểu chi phí bộ nhớ.

## 9. Chẩn đoán bằng công cụ JDK 17

### 9.1. Xem các flag JVM thực tế

Khi JVM đang chạy:

```shell
jcmd <pid> VM.flags
```

Xem giá trị các flag sau ergonomics:

```shell
java -XX:+PrintFlagsFinal -version
```

Trên Linux/macOS có thể lọc:

```shell
java -XX:+PrintFlagsFinal -version 2>&1 | grep -E "MaxHeapSize|InitialHeapSize|MaxRAMPercentage|InitialRAMPercentage|UseContainerSupport"
```

Trên Windows PowerShell:

```powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String "MaxHeapSize|InitialHeapSize|MaxRAMPercentage|InitialRAMPercentage|UseContainerSupport"
```

Không chỉ xem command line mà hãy kiểm tra flag cuối cùng JVM thực sự dùng. `-Xmx` hoặc `-Xms` có thể ghi đè các percentage flags.

### 9.2. Xem heap hiện tại

```shell
jcmd <pid> GC.heap_info
```

Lệnh này hiển thị thông tin heap và collector theo JVM đang chạy. Kết hợp với metric heap used/committed/max để xác định heap có đang tiến gần giới hạn hay không.

### 9.3. Xem cấu hình và thông tin VM

```shell
jcmd <pid> VM.info
jcmd <pid> VM.flags
```

Các lệnh giúp kiểm tra thông tin runtime và flag đang có hiệu lực. Công cụ attach có thể cần chạy dưới cùng user hoặc trong môi trường có quyền truy cập tiến trình.

### 9.4. Native Memory Tracking

HotSpot có Native Memory Tracking (NMT) để quan sát một số nhóm native memory do JVM quản lý. Bật từ lúc khởi động:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Sau đó truy vấn:

```shell
jcmd <pid> VM.native_memory summary
```

NMT có overhead và không theo dõi mọi allocation native của thư viện bên thứ ba. Nó là công cụ chẩn đoán bổ sung, không thay thế RSS/cgroup metrics.

### 9.5. GC logging

Java 17 dùng unified logging:

```shell
java -Xlog:gc*:file=/var/log/app-gc.log:time,uptime,level,tags -jar app.jar
```

GC log giúp quan sát:

- Heap trước và sau GC.
- Tần suất và loại collection.
- Pause time.
- Heap có thường xuyên chạm giới hạn không.
- Sau GC còn lại bao nhiêu live data.

Không kết luận heap thiếu chỉ từ một lần GC dài. Hãy xem xu hướng qua workload đủ lâu, bao gồm warm-up và peak load.

## 10. Xử lý OutOfMemoryError và container bị OOM kill

### 10.1. Các dạng lỗi bộ nhớ khác nhau

| Dấu hiệu | Vùng nhớ/nguyên nhân có thể |
|---|---|
| `OutOfMemoryError: Java heap space` | Không cấp phát được object trong heap sau khi GC không thu hồi đủ |
| `OutOfMemoryError: GC overhead limit exceeded` | JVM dành phần lớn thời gian cho GC nhưng thu hồi được rất ít heap |
| `OutOfMemoryError: Metaspace` | Metaspace không thể mở rộng đủ |
| `OutOfMemoryError: Direct buffer memory` | Không cấp phát được direct buffer theo giới hạn/cơ chế hiện tại |
| `OutOfMemoryError: unable to create native thread` | Hệ điều hành/JVM không tạo thêm thread, có thể do native memory hoặc giới hạn thread/process |
| Container state `OOMKilled` | Cgroup/kernel kết thúc container khi vượt memory limit; JVM có thể không kịp ném OOME hoặc ghi heap dump |

Không phải mọi vấn đề memory đều là heap exhaustion. Cần xác định đúng loại lỗi trước khi tăng `-Xmx`.

### 10.2. Bật heap dump khi Java ném OOME

Cấu hình:

```shell
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/diagnostics/heap \
  -jar app.jar
```

Khi JVM phát sinh một số dạng `OutOfMemoryError`, nó cố gắng ghi heap dump để phân tích object đang giữ bộ nhớ. Thư mục đích phải tồn tại hoặc có thể được JVM tạo theo cách phù hợp, có quyền ghi và đủ dung lượng.

Heap dump có thể rất lớn và chứa dữ liệu nhạy cảm của ứng dụng. Bảo vệ quyền truy cập, thời gian lưu và quy trình chuyển file; không đưa dump vào log công khai hoặc image/container layer.

### 10.3. OOMKilled có thể không tạo heap dump

Khi kernel kết thúc tiến trình do cgroup memory limit, JVM có thể bị dừng đột ngột trước khi xử lý exception hoặc ghi dump. Trong Kubernetes, container có thể hiển thị trạng thái `OOMKilled` và exit code thường gặp là 137.

Vì vậy, cần quan sát trước khi chạm limit:

- Container/cgroup memory usage và peak.
- Process RSS.
- Heap used/committed/max.
- Direct buffer usage.
- Metaspace.
- Thread count.
- GC pause và allocation rate.

Heap dump chỉ là một nguồn chẩn đoán; không thay thế metric native memory và container.

### 10.4. Heap dump không tự chứng minh memory leak

Một heap dump là snapshot tại một thời điểm. Để tìm leak, cần xác định object nào còn reachable, đường tham chiếu giữ object, retained size và xu hướng tăng qua thời gian.

Một heap lớn có thể là live set hợp lệ khi tải cao. Ngược lại, heap used sau GC tăng dần qua các chu kỳ có thể gợi ý object bị giữ ngoài dự kiến.

## 11. Quy trình sizing heap cho một ứng dụng mới

### Bước 1 — Xác định memory limit thật

Ghi nhận:

- Container memory limit.
- Kubernetes request/limit.
- Host/VM và cgroup version.
- JDK vendor, version và JVM options.
- Số lượng container/replica và sidecar liên quan.

Đảm bảo JVM nhìn thấy đúng memory limit qua container support.

### Bước 2 — Đo baseline khi ứng dụng khởi động

Theo dõi:

- RSS sau startup.
- Heap used, committed và max.
- Metaspace và code cache.
- Thread count.
- Direct/mapped buffer usage.
- NMT summary nếu cần.

Baseline giúp biết ứng dụng tiêu thụ bao nhiêu memory trước khi nhận tải lớn.

### Bước 3 — Chạy workload đại diện

Test với:

- Dữ liệu có kích thước thực tế.
- Số request đồng thời gần peak.
- Số kết nối và thread dự kiến.
- Warm-up/JIT.
- Batch hoặc tác vụ nền.
- Các trường hợp tạo object lớn và allocation burst.

Đừng sizing dựa trên một lần chạy idle hoặc chỉ dựa vào average traffic.

### Bước 4 — Đo live set và GC

Quan sát heap sau các chu kỳ GC, tần suất collection, pause time và allocation rate. Heap cần đủ khoảng trống cho live set, allocation burst và hoạt động GC.

Nếu live set sau GC đã chiếm gần hết heap max, tăng heap có thể cần thiết. Nếu live set thấp nhưng RSS cao, điều tra native/non-heap trước khi tăng heap.

### Bước 5 — Dành ngân sách cho non-heap/native

Đo hoặc ước lượng:

- Metaspace.
- Thread stacks theo thread count và `-Xss`.
- Direct buffer.
- Code cache và GC structures.
- JNI/native library.
- Phần dự phòng.

Đối chiếu với cgroup memory limit, không chỉ với Xmx.

### Bước 6 — Chọn cấu hình ban đầu

Chọn `-Xmx` cố định nếu mỗi môi trường có ngân sách rõ. Chọn `MaxRAMPercentage` nếu cùng image chạy trên nhiều memory tier và JVM nhận diện container limit đúng.

Đặt `-Xms`/InitialRAMPercentage theo yêu cầu startup và memory footprint. Không mặc định phải bằng Xmx.

### Bước 7 — Stress test và kiểm tra headroom

Tăng tải tới peak dự kiến và vượt peak trong giới hạn test an toàn. Xác nhận:

- Không OOM.
- Container không bị OOMKilled.
- GC pause và throughput đạt mục tiêu.
- RSS/cgroup usage còn headroom.
- Khi scale thread/connection, native memory vẫn trong ngân sách.

### Bước 8 — Theo dõi sau triển khai

Giữ dashboard và alert cho heap, GC, RSS/cgroup usage, thread count, direct memory và OOM events. Revisit sizing khi workload, JDK, thư viện hoặc memory limit thay đổi.

## 12. Ví dụ cấu hình theo các môi trường

### 12.1. Container nhỏ 512 MiB

Với limit 512 MiB, không đặt heap 512 MiB. Một cấu hình thử nghiệm có thể là:

```shell
java -Xms128m -Xmx256m -jar app.jar
```

Phần còn lại dành cho metaspace, stacks, direct buffers, JVM native memory và reserve. Đây chỉ là điểm bắt đầu; ứng dụng có thể cần heap khác tùy live set và native usage.

### 12.2. Container 1 GiB, cùng artifact chạy nhiều tier

```shell
java \
  -XX:InitialRAMPercentage=20.0 \
  -XX:MaxRAMPercentage=60.0 \
  -jar app.jar
```

Khi container memory limit thay đổi, heap max được tính theo phần trăm RAM JVM nhận diện. Cần kiểm tra lại native headroom ở từng tier.

### 12.3. Máy ảo có memory budget cố định

```shell
java -Xms1g -Xmx2g -jar app.jar
```

Cấu hình explicit giúp giới hạn heap rõ ràng. Trước khi dùng, phải xác nhận VM có đủ RAM cho 2 GiB heap cộng non-heap/native và OS.

### 12.4. Ứng dụng có nhiều direct buffer

Nếu profiling cho thấy ứng dụng dùng nhiều direct buffer, có thể đặt cap phù hợp:

```shell
java -Xmx512m -XX:MaxDirectMemorySize=256m -jar app.jar
```

Tổng memory vẫn còn cần metaspace, stacks, code cache, GC và các khoản native khác. Đừng cộng hai con số này rồi cho rằng đã đủ ngân sách.

### 12.5. Ứng dụng có nhiều thread

Nếu ứng dụng tạo hàng nghìn thread, thread stack có thể là phần đáng kể của memory footprint. Trước khi hạ `-Xss`, hãy xem xét:

- Dùng thread pool giới hạn.
- Dùng async/non-blocking I/O nếu kiến trúc phù hợp.
- Kiểm tra thread leak.
- Đo stack usage và xác định stack size tối thiểu an toàn.

Giảm thread count thường giải quyết được nguyên nhân gốc tốt hơn chỉ hạ stack size.

## 13. Các sai lầm thường gặp khi đặt heap

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Đặt `-Xmx` bằng container memory limit | Không còn headroom cho native/non-heap; dễ OOMKilled | Trừ ngân sách native và reserve trước khi chọn heap |
| Nghĩ Xmx là tổng RAM JVM | Bỏ sót metaspace, stacks, direct buffer, JNI | Theo dõi heap và process/cgroup memory song song |
| Sizing theo RAM host thay vì cgroup limit | JVM có thể chọn heap quá lớn cho container | Xác nhận container awareness và memory limit thực tế |
| Dùng Kubernetes request như hard limit | JVM có thể tính dựa trên mức tài nguyên sai | Dùng container memory limit để lập ngân sách |
| Đặt Xms = Xmx theo thói quen | Baseline committed heap cao, giảm headroom ban đầu | Chọn Xms theo startup/live set thực tế |
| Tăng Xmx khi RSS cao nhưng heap thấp | Không giải quyết native memory pressure, còn giảm headroom | Đo metaspace, stacks, direct buffers, JNI và NMT |
| Hạ Xmx chỉ để tránh OOMKilled | Có thể tạo Java heap OOME và GC thrashing sớm hơn | Phân tích tổng memory và workload |
| Đặt MaxMetaspaceSize quá thấp | OOME Metaspace khi nạp class | Chỉ đặt cap sau khi đo metadata usage |
| Đặt MaxDirectMemorySize quá thấp | OOME Direct buffer memory | Đo direct buffer workload trước khi giới hạn |
| Hạ Xss quá thấp | StackOverflowError | Giảm thread count hoặc đo call depth trước |
| Bỏ qua thread count | Stack/native memory tăng theo concurrency | Theo dõi thread và giới hạn pool |
| Chỉ nhìn heap dump khi container OOMKilled | Không thấy đầy đủ native usage; có thể không kịp tạo dump | Kết hợp cgroup/RSS/NMT/metrics |
| Không kiểm tra flag JVM cuối cùng | Flag bị ghi đè hoặc không được áp dụng | Dùng `jcmd VM.flags` và `PrintFlagsFinal` |
| Copy tỷ lệ heap của ứng dụng khác | Workload và native overhead khác nhau | Sizing bằng benchmark/load test của chính ứng dụng |

## 14. Ví dụ Java 17: in thông tin heap và buffer

Lưu file **MemorySnapshot.java**:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;

public class MemorySnapshot {

    private static double mib(long bytes) {
        return bytes / 1024.0 / 1024.0;
    }

    public static void main(String[] args) {
        MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memoryBean.getHeapMemoryUsage();
        MemoryUsage nonHeap = memoryBean.getNonHeapMemoryUsage();

        System.out.printf("Heap used: %.1f MiB%n", mib(heap.getUsed()));
        System.out.printf(
                "Heap committed: %.1f MiB%n",
                mib(heap.getCommitted())
        );
        System.out.printf("Heap max: %.1f MiB%n", mib(heap.getMax()));
        System.out.printf(
                "Non-heap used: %.1f MiB%n",
                mib(nonHeap.getUsed())
        );

        ThreadMXBean threadBean = ManagementFactory.getThreadMXBean();
        System.out.println("Live threads: " + threadBean.getThreadCount());

        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class
                )) {
            System.out.printf(
                    "%s: used=%.1f MiB, capacity=%.1f MiB, count=%d%n",
                    pool.getName(),
                    mib(pool.getMemoryUsed()),
                    mib(pool.getTotalCapacity()),
                    pool.getCount()
            );
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 MemorySnapshot.java
java -Xms128m -Xmx512m MemorySnapshot
```

Ví dụ này đọc các metric do JVM cung cấp. Nó không đo tổng RSS/cgroup usage. Trong môi trường triển khai, hãy ghép số liệu này với metrics container hoặc process từ nền tảng quan sát.

## 15. Checklist vận hành khi thay đổi heap limit

Trước khi triển khai:

- Xác nhận memory limit của container/VM.
- Xác nhận JVM Java 17 nhận diện đúng cgroup limit.
- Kiểm tra Xms/Xmx và percentage flags cuối cùng.
- Ước lượng metaspace, thread stacks, direct buffers và native libraries.
- Xác nhận heap dump path có quyền ghi và đủ dung lượng.
- Chạy workload đại diện và peak load.
- Kiểm tra GC pause, throughput và RSS/cgroup peak.

Sau khi triển khai:

- Theo dõi heap used/committed/max.
- Theo dõi process RSS và container memory current/peak.
- Theo dõi GC pause và allocation rate.
- Theo dõi metaspace, direct buffers và thread count.
- Cảnh báo trước khi cgroup usage chạm limit.
- Ghi nhận OOMKilled và OutOfMemoryError riêng biệt.
- Đánh giá lại khi tăng concurrency, thay đổi thư viện hoặc nâng JDK.

## 16. Bài tập thực hành

### Bài 1 — Quan sát Xms và Xmx

Chạy chương trình `MemorySnapshot` với:

```shell
java -Xms128m -Xmx512m MemorySnapshot
java -Xms256m -Xmx512m MemorySnapshot
```

So sánh heap committed ban đầu và heap max. Giải thích vì sao hai cấu hình có cùng Xmx nhưng baseline committed có thể khác nhau.

### Bài 2 — So sánh percentage flags

Chạy:

```shell
java -XX:InitialRAMPercentage=20 -XX:MaxRAMPercentage=60 MemorySnapshot
```

So sánh với cấu hình explicit Xms/Xmx. Dùng `PrintFlagsFinal` hoặc `jcmd VM.flags` để xem JVM áp dụng giá trị nào.

### Bài 3 — Thử trong container

Chạy cùng một image Java 17 với hai memory limit khác nhau, ví dụ 512 MiB và 1 GiB. Quan sát:

- Container limit.
- Heap max.
- RSS/cgroup usage.
- Startup footprint.

Giải thích vai trò của `UseContainerSupport` và `MaxRAMPercentage`.

### Bài 4 — Phân biệt heap OOM và OOMKilled

Trong môi trường test riêng, tạo workload cấp phát heap tăng dần. So sánh trường hợp JVM ném `OutOfMemoryError: Java heap space` với trường hợp container runtime kết thúc tiến trình do memory limit. Ghi nhận log, exit code và heap dump nếu có.

Không thực hiện bài này trên môi trường production hoặc dữ liệu thật.

### Bài 5 — Đo direct buffer

Tạo một số `ByteBuffer.allocateDirect`, quan sát `BufferPoolMXBean`, thử giới hạn `MaxDirectMemorySize` trong một JVM test. Giải thích vì sao heap used không phản ánh đầy đủ direct buffer usage.

### Bài 6 — Thread stack budget

Tạo thread pool với số thread khác nhau, đo RSS và thread count. So sánh tác động của concurrency. Không hạ Xss trước khi kiểm tra stack depth và khả năng xảy ra `StackOverflowError`.

### Bài 7 — Lập ngân sách memory

Với container limit 2 GiB, đo peak non-heap/native và chọn reserve. Tính heap max ban đầu theo công thức ngân sách, sau đó kiểm chứng bằng load test. Giải thích vì sao không thể chỉ chọn Xmx bằng 2 GiB.

## 17. Câu hỏi tự kiểm tra

1. Heap và RSS khác nhau thế nào?
2. `-Xms` và `-Xmx` có vai trò gì?
3. `InitialRAMPercentage` và `MaxRAMPercentage` được dùng khi nào?
4. `-Xmx` có ghi đè `MaxRAMPercentage` không?
5. Vì sao `MaxRAMPercentage=100` thường nguy hiểm trong container?
6. `MinRAMPercentage` có phải mức heap tối thiểu ban đầu không?
7. Container awareness giúp JVM nhận diện tài nguyên gì?
8. `UseContainerSupport` có mặc định bật trên HotSpot Java 17 Linux không?
9. Kubernetes request và limit khác nhau thế nào?
10. Vì sao container memory limit không thể dành toàn bộ cho heap?
11. Metaspace, code cache và thread stack nằm ở đâu?
12. Direct buffer ảnh hưởng memory budget thế nào?
13. Khi nào `MaxDirectMemorySize` hữu ích?
14. Vì sao `OutOfMemoryError: Java heap space` khác `OOMKilled`?
15. Heap dump có thể bỏ sót loại memory pressure nào?
16. NMT hỗ trợ điều tra native memory ra sao và có giới hạn gì?
17. Vì sao phải test peak workload thay vì chỉ quan sát idle?
18. Làm thế nào xác nhận JVM đang dùng Xmx/percentage flag nào?

## 18. Tài liệu tham khảo

- [Java SE 17 VM Options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xms`, `-Xmx`, percentage flags, container support và các tùy chọn runtime.
- [Java SE 17 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/): điều tra memory leak, OutOfMemoryError, GC và native memory.
- [Java SE 17 API — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `maxMemory()`, `totalMemory()`, `freeMemory()`.
- [Java SE 17 API — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap memory usage.
- [Java SE 17 API — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): quan sát direct và mapped buffer pools.
- [OpenJDK JEP 8182070 — Container Awareness](https://openjdk.org/jeps/8182070): nhận biết giới hạn tài nguyên container trong JVM.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): ý nghĩa memory request và limit.
- [Docker — Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): giới hạn memory container.

Đặt heap phù hợp là bài toán **ngân sách bộ nhớ của toàn tiến trình**. Hãy xác định container limit, trừ các khoản non-heap/native và reserve, rồi chọn Xmx hoặc MaxRAMPercentage theo cách triển khai. Sau đó kiểm chứng bằng heap metrics, GC logs, RSS/cgroup usage và workload đỉnh. Cách làm này giúp JVM có đủ heap để hoạt động mà vẫn giữ khoảng trống cho các vùng nhớ ngoài heap trong Java 17.

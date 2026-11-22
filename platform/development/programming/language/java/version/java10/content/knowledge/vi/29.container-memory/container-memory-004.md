# `-XX:MaxRAMPercentage` và giới hạn heap theo bộ nhớ khả dụng (Java 10+)

## 1. Giới thiệu

Chạy ứng dụng Java trong Docker hoặc Kubernetes đặt ra một vấn đề quan trọng: **RAM của máy chủ không phải RAM mà container có thể sử dụng**. Ví dụ máy chủ có 64 GiB RAM, nhưng container chứa JVM chỉ được sử dụng tối đa 1 GiB. Nếu JVM đặt heap dựa trên 64 GiB mà không nhận diện giới hạn container, ứng dụng có thể bị hệ điều hành/container runtime kết thúc khi vượt memory limit.

Từ **JDK 10**, HotSpot tăng khả năng nhận biết giới hạn tài nguyên container và bổ sung các tùy chọn phần trăm để tính kích thước heap linh hoạt, trong đó có **`-XX:MaxRAMPercentage`**.

Câu lệnh ví dụ:

~~~bash
java -XX:MaxRAMPercentage=75.0 -jar app.jar
~~~

Ý nghĩa: JVM sử dụng tỷ lệ **75% của mức RAM khả dụng được nhận diện** để chọn **maximum Java heap** theo chính sách sizing của HotSpot. Nếu mức RAM được nhận diện là 1 GiB, kết quả **theo mô hình đơn giản** là khoảng **768 MiB**, nhưng kích thước heap thực tế còn chịu ảnh hưởng của JVM ergonomics, alignment và những tùy chọn khác.

Bài học thuộc nhóm **Bộ nhớ trong container** của chủ đề **Java 10**, với trọng tâm trực tiếp là `-XX:MaxRAMPercentage` và giới hạn heap.

Sau bài học, bạn sẽ có thể:
1. Giải thích cờ `MaxRAMPercentage` và cách JVM dùng memory limit.
2. Phân biệt bộ nhớ host, container limit, Java heap và bộ nhớ process tổng.
3. Nắm ưu tiên của `-Xmx` so với percentage-based sizing.
4. Hiểu `InitialRAMPercentage` và `MinRAMPercentage` (đặc biệt tên cờ dễ nhầm).
5. Phân biệt Kubernetes requests và limits.
6. Kiểm tra container awareness bằng những lệnh HotSpot/JDK hiện đại.
7. Dùng chương trình Java 17+ để minh họa tính toán và quan sát actual heap max.
8. Chọn mức heap có headroom cho Metaspace, stacks, direct buffers, GC/JIT và native memory.
9. Xử lý các trường hợp heap OOME, container OOM kill và runtime nhận sai cgroup limit.

**Ghi chú phiên bản:** Kiến thức vẫn áp dụng trong những JDK hiện hành như JDK 17, 21 và Java SE 25. Không khuyến nghị sử dụng lại các cờ `...RAMFraction` cũ đã bị deprecated.

## 2. Java heap không phải toàn bộ RAM của process

Một Java process sử dụng nhiều vùng bộ nhớ:

| Thành phần | Mục đích | Bị giới hạn bởi `-Xmx`? |
| --- | --- | --- |
| Java heap | Object, mảng do GC quản lý | **Có** |
| Metaspace | Metadata của lớp và class loader | Không |
| Platform thread stacks | Ngăn xếp các threads | Không |
| JIT code cache | Mã máy được JIT biên dịch | Không |
| Direct buffers | Vùng native backing của direct byte buffers | Không |
| Native/JNI allocations | Các thư viện native và JVM internals | Không |
| GC/JVM structures | Bảng, vùng làm việc và thông tin VM | Không |
| Mapped/shared pages | Một số mapped files, thư viện, CDS data | Không đồng nghĩa Java heap |

Do đó, **maximum heap** không phải giới hạn toàn bộ process Java.

~~~text
Node: 64 GiB RAM
  │
  └─ Container Java: memory limit = 1 GiB
       │
       ├─ Java heap: ví dụ max khoảng 768 MiB
       ├─ Metaspace
       ├─ Thread stacks
       ├─ Code cache
       ├─ Direct/native buffers
       └─ JVM/GC/JNI và vùng bộ nhớ khác
~~~

Khi 768 MiB heap được cấu hình, điều đó **không** có nghĩa JVM sẽ lập tức sử dụng đúng 768 MiB RAM lúc startup, cũng **không** có nghĩa 256 MiB còn lại được JVM bảo lưu riêng cho native memory.

Cần phân biệt:
- **Heap used:** object memory đang sử dụng trong heap.
- **Heap committed:** số byte heap đã commit.
- **Heap max:** giới hạn lớn nhất JVM tính toán cho heap.
- **RSS:** resident pages được hệ điều hành tính cho process.
- **Container memory usage:** các trang và loại bộ nhớ được cgroup/container runtime hạch toán; không chỉ là heap.

Nếu tổng footprint vượt memory limit, container có thể bị **OOM kill**, ngay cả khi Java heap chưa chạm giới hạn. Ngược lại, chương trình có thể bị **`OutOfMemoryError: Java heap space`** khi max heap đã hết dù container vẫn còn RAM ngoài heap.

## 3. JDK 10 đã bổ sung gì?

Oracle JDK 10 Release Notes ghi nhận các tùy chọn:
- **`-XX:InitialRAMPercentage`**
- **`-XX:MaxRAMPercentage`**
- **`-XX:MinRAMPercentage`**

Chúng hỗ trợ chọn heap size theo phần trăm bộ nhớ khả dụng, phù hợp với container có nhiều memory limits khác nhau, và thay thế hướng cấu hình Fraction cũ như `-XX:MaxRAMFraction`.

HotSpot Linux hiện đại hỗ trợ **`-XX:+UseContainerSupport`**, thường được bật mặc định. Nó giúp JVM đọc giới hạn CPU/memory của container khi có môi trường được hỗ trợ.

Tuy nhiên, hệ sinh thái Linux cgroups đã phát triển từ **cgroups v1** sang **cgroups v2**. Không được giả định bản JDK 10 đời đầu luôn đọc cgroups v2 chính xác. Khi triển khai trên Docker/Kubernetes hiện nay, ưu tiên runtime được cập nhật và **xác minh giới hạn JVM thực sự nhìn thấy**.

## 4. Tùy chọn `MaxRAMPercentage`: ý nghĩa và công thức

Cú pháp:

~~~bash
-XX:MaxRAMPercentage=<percent>
~~~

Ví dụ:

~~~bash
java -XX:MaxRAMPercentage=70.0 -jar app.jar
~~~

Mô hình tính đơn giản:

~~~text
Maximum heap theo mô hình
  ≈ Detected available RAM × MaxRAMPercentage / 100
~~~

Nếu JVM nhận diện 2 GiB available RAM:

~~~text
2 GiB = 2.048 MiB
2.048 × 70% = 1.433,6 MiB
~~~

**Đây là phép ước lượng**, không phải cam kết về số byte chính xác. Trên HotSpot còn có các điều chỉnh theo maximum heap ergonomics, alignment, small-memory heuristics và flags khác.

Theo manual Oracle Java SE 17/25, default của `MaxRAMPercentage` là **25%**. Nhưng nếu môi trường rất nhỏ hoặc cấu hình có overrides thì không thể khẳng định actual max heap luôn chính xác 25% của số RAM người vận hành nhìn thấy.

### Những phép tính minh họa

| RAM khả dụng được nhận diện | Percentage | Heap tính theo mô hình | Phần còn lại trên giấy |
| --- | ---: | ---: | ---: |
| 512 MiB | 50% | 256 MiB | 256 MiB |
| 1 GiB | 50% | 512 MiB | 512 MiB |
| 1 GiB | 70% | 716,8 MiB | 307,2 MiB |
| 1 GiB | 75% | 768 MiB | 256 MiB |
| 2 GiB | 75% | 1.536 MiB | 512 MiB |
| 4 GiB | 60% | 2.457,6 MiB | 1.638,4 MiB |

**Không được coi cột phần còn lại là RAM dự trữ an toàn đã được đảm bảo**: đó chỉ là phép trừ giữa limit và heap theo mô hình.

Với container 1 GiB mà đặt 95%, mô hình cho heap **972,8 MiB**, chỉ còn khoảng **51,2 MiB** trên giấy. Chừng đó có thể không đủ cho JVM native memory, đặc biệt khi số platform threads/direct buffers hoặc Metaspace tăng.

**Không có tỷ lệ phần trăm tối ưu chung**. Một CLI nhỏ, API server nhiều threads và ứng dụng xử lý dữ liệu off-heap có nhu cầu khác nhau.

## 5. `-Xmx` so với `MaxRAMPercentage`: cái nào có ưu tiên?

`-Xmx` đặt **maximum heap tường minh**, vì vậy nó được ưu tiên so với cách tính maximum heap theo percentage.

Ví dụ:

~~~bash
java -Xmx512m -XX:MaxRAMPercentage=80.0 -jar app.jar
~~~

Ở đây `-Xmx512m` đặt maximum heap, không cộng thêm 80% và không tự biến thành 80% container RAM.

Một lỗi vận hành là đặt `MaxRAMPercentage` trong manifest nhưng không biết image hoặc startup wrapper đã truyền `-Xmx` qua:
- Docker ENTRYPOINT;
- `JAVA_TOOL_OPTIONS`;
- `JDK_JAVA_OPTIONS`;
- Shell startup scripts;
- IDE hoặc build-tool runtime settings.

**Cách xử lý:** đọc VM flags của process thật, không chỉ đọc cấu hình trên giấy.

### `-XX:MaxRAM` là gì?

`-XX:MaxRAM` đặt một **cơ sở RAM cho phép sizing heap** theo JVM ergonomics. Nó không thay cgroup memory limit và không giới hạn trực tiếp tất cả native allocations.

### `-XX:InitialRAMPercentage` là gì?

Cờ này tham gia chọn **initial heap size** theo tỷ lệ, khi không có `-Xms` tường minh. Nó **khác** với `MaxRAMPercentage`, vốn liên quan maximum heap. `-Xms` tường minh có ưu tiên đối với initial heap.

### `-XX:MinRAMPercentage` là gì?

Tên gọi rất dễ hiểu sai. Theo tài liệu HotSpot, **MinRAMPercentage** tham gia tính **maximum heap khi lượng RAM khả dụng rất nhỏ**. Nó **không** chỉ định “heap phải có ít nhất n% RAM”, cũng không phải cờ thay thế cho `-Xms`.

Vì vậy, với container rất nhỏ, JVM có thể không tính maximum heap theo `MaxRAMPercentage` một cách đơn giản; phải xem `MaxHeapSize` và actual runtime value.

## 6. Kubernetes memory request khác memory limit

Ví dụ cấu hình của một container:

~~~yaml
resources:
  requests:
    memory: "512Mi"
  limits:
    memory: "1Gi"
~~~

- **Memory request**: liên quan lập lịch và quản lý tài nguyên.
- **Memory limit**: giới hạn bộ nhớ mà container phải tuân thủ.
- HotSpot container-aware thường dùng **limit hữu hiệu mà cgroup phản ánh**, không tự dùng request làm maximum heap basis.

Vì vậy, nếu request 512Mi, limit 1Gi, `MaxRAMPercentage=75`, mô hình heap là **768 MiB**, không phải 384 MiB.

Nếu không có memory limit hữu hiệu, JVM có thể dựa trên memory host hoặc ràng buộc khác. Không được nghĩ request là hard cap khi manifest không có limit.

**Lưu ý:** Pod có thể có nhiều container; mỗi Java process cần đánh giá giới hạn và số liệu đúng container mà nó chạy. Nếu admission controller hoặc runtime đã thay đổi resource settings, phải dựa vào môi trường **đang áp dụng**, không chỉ file YAML dự kiến.

## 7. Cách JVM nhìn thấy container memory limit

Trên HotSpot Linux có hỗ trợ, `UseContainerSupport` cho phép VM phát hiện các ràng buộc của cgroup. Tùy version/build:
- Có thể nhận diện cgroup v1 hoặc v2;
- Đọc giới hạn RAM, CPU theo khả năng VM;
- Khi không có limit phù hợp, có thể dùng thông tin RAM host;
- Khi container support bị tắt, kết quả sizing có thể khác đáng kể.

Một ví dụ nguy hiểm: host 64 GiB, container limit 1 GiB, JVM không nhận ra limit nên dùng 25% RAM host: mô hình max heap có thể lên tới **16 GiB**. Số này vượt xa container memory cap và có nguy cơ OOM kill.

**Cách xử lý ưu tiên:** xác định JVM version, cgroup type, kiểm tra container metrics. Nếu runtime cũ không nhận diện môi trường, nâng JDK được hỗ trợ hoặc tạm sử dụng `-Xmx` tường minh với budget phù hợp. **Đừng chỉ đổi 25% thành 20%** trong khi cơ sở RAM đã sai nhiều lần.

## 8. Kiểm tra JVM version, container detection và max heap

### Kiểm tra JDK đang gọi

~~~bash
java --version
~~~

Ghi feature/update/build và distribution. JDK 17/21/25 có các bản cập nhật container support khác nhau; trong production nên dùng bản được hỗ trợ.

### Xem maximum heap estimate

~~~bash
java -XX:MaxRAMPercentage=75.0 -XshowSettings:vm -version
~~~

Trên HotSpot phù hợp, `-XshowSettings:vm` hiển thị các JVM settings, thường có maximum heap estimate. Kết quả phụ thuộc runtime và container; không có output cố định.

### Xem Linux system/container settings

~~~bash
java -XshowSettings:system -version
~~~

Trên JDK/Linux hỗ trợ, cài đặt này hiển thị thông tin OS/container mà JVM nhận diện. Nếu không chạy trong container hoặc metrics provider không khả dụng, output có thể khác.

### Xem thêm chi tiết cgroup

~~~bash
java -Xlog:os+container=trace -version
~~~

`trace` có thể in nhiều dòng, chỉ nên dùng ở lượt chẩn đoán. Xem JVM phát hiện cgroup gì, có thấy memory limit không và có cảnh báo về provider không.

### Xem cờ đã tính cuối cùng

~~~bash
java -XX:MaxRAMPercentage=75.0 -XX:+PrintFlagsFinal -version
~~~

Dòng output khá nhiều; tìm **MaxRAMPercentage**, **MaxHeapSize**, **MaxRAM**, **UseContainerSupport** và các flags tùy môi trường. **MaxRAMPercentage=75** không đủ chứng minh actual heap max đúng phép nhân; `MaxHeapSize` phản ánh quyết định cuối cùng hơn.

Các lệnh này khởi động một JVM **mới**. Nếu điều tra service production, kiểm tra những flags mà chính process đó dùng.

## 9. Ví dụ Docker với limit 1 GiB

Nếu có Docker và image JDK phù hợp:

~~~bash
docker run --rm --memory=1g eclipse-temurin:17-jdk java -XX:MaxRAMPercentage=75.0 -XshowSettings:vm -version
~~~

Lệnh đặt limit container 1 GiB, chọn percentage 75 và in cài đặt JVM để quan sát maximum heap.

Kiểm tra system/container metrics:

~~~bash
docker run --rm --memory=1g eclipse-temurin:17-jdk java -XshowSettings:system -version
~~~

So sánh với cấu hình `-Xmx` cố định:

~~~bash
docker run --rm --memory=1g eclipse-temurin:17-jdk java -Xmx512m -XshowSettings:vm -version
~~~

**Điều kiện:** Cần Docker daemon, quyền chạy và image có thể được lấy từ registry. Image tag có thể được cập nhật theo thời gian. Khi benchmark, cố định image digest/JDK build và ghi lại resource limits. Không đưa ra một số max heap như thể nó là output bắt buộc trên mọi máy.

## 10. Chương trình Java 17+ độc lập

Chương trình sau có:
- Phần **mặc định**: dùng ba giới hạn RAM giả định và phần trăm cố định. Stdout xác định.
- Phần **`--runtime`**: in maximum heap của chính JVM đang chạy; giá trị phụ thuộc môi trường.

Tạo tệp **ContainerHeapSizingDemo.java**:

~~~java
import java.util.Locale;

public class ContainerHeapSizingDemo {

    static void estimate(long limitMiB, double percent) {
        double modeledHeapMiB = limitMiB * percent / 100.0;
        double remainderMiB = limitMiB - modeledHeapMiB;

        System.out.printf(Locale.ROOT,
                "limit=%d MiB; percent=%.1f%%; "
                        + "modeled heap=%.1f MiB; remainder=%.1f MiB%n",
                limitMiB, percent, modeledHeapMiB, remainderMiB);
    }

    static void showRuntime() {
        Runtime runtime = Runtime.getRuntime();
        double maxHeapMiB = runtime.maxMemory() / (1024.0 * 1024.0);

        System.out.println("=== runtime-dependent ===");
        System.out.printf(Locale.ROOT,
                "actual max heap=%.1f MiB%n", maxHeapMiB);
        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("java.vm.name="
                + System.getProperty("java.vm.name"));
        System.out.println("java.home="
                + System.getProperty("java.home"));
    }

    public static void main(String[] args) {
        estimate(1024, 75.0);
        estimate(2048, 70.0);
        estimate(4096, 60.0);

        if (args.length > 0 && "--runtime".equals(args[0])) {
            showRuntime();
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 ContainerHeapSizingDemo.java
java ContainerHeapSizingDemo
~~~

**Stdout chính xác khi không truyền tham số:**

~~~text
limit=1024 MiB; percent=75.0%; modeled heap=768.0 MiB; remainder=256.0 MiB
limit=2048 MiB; percent=70.0%; modeled heap=1433.6 MiB; remainder=614.4 MiB
limit=4096 MiB; percent=60.0%; modeled heap=2457.6 MiB; remainder=1638.4 MiB
~~~

Chạy với thông tin runtime:

~~~bash
java -XX:MaxRAMPercentage=70.0 ContainerHeapSizingDemo --runtime
~~~

Đầu ra có **ba dòng toán học như trên**, sau đó là các dòng:
- `=== runtime-dependent ===`;
- `actual max heap=...` với số MiB thực;
- `java.version=...`;
- `java.vm.name=...`;
- `java.home=...`.

Các dấu ba chấm ở đây **chỉ mô tả dữ liệu phụ thuộc môi trường**, không phải stdout cố định.

### Cách hiểu ví dụ

`modeled heap` là kết quả số học, không phải Java heap được JVM cấp thật. `Runtime.getRuntime().maxMemory()` chỉ cho biết **maximum heap** của process đang chạy, không đo tổng RAM container. Phần `remainder` cũng không đồng nghĩa native memory được đặt trước; đó là khoảng dư theo mô hình.

Chương trình không cần Docker để chạy phần toán học, nên dùng được trong một lớp học Java 17+.

## 11. Đo memory ngoài heap trước khi chốt percentage

Một phần RAM container phải dành cho các vùng ngoài Java heap. Cần quan sát:
1. **Metaspace** và class loader behavior.
2. **Số platform threads**, kích thước stack và peak concurrent threads.
3. **Direct/native buffers** và JNI allocations.
4. **JIT code cache**, GC native structures.
5. **Memory-mapped pages**, OS/cgroup accounting.
6. Tổng RSS/PSS hoặc những chỉ số container memory tương ứng.

Trên HotSpot, có thể bật **Native Memory Tracking** khi process khởi động:

~~~text
-XX:NativeMemoryTracking=summary
~~~

Với công cụ và quyền phù hợp:

~~~text
jcmd <pid> VM.native_memory summary
~~~

Thay `<pid>` bằng PID thật. Native Memory Tracking có overhead và **không thay thế hoàn toàn** công cụ theo dõi mọi cấp phát native từ bên thứ ba. Chỉ bật khi phù hợp với môi trường.

**Nguyên tắc:** Nếu ứng dụng dùng nhiều direct buffers hoặc thread stacks, tỷ lệ heap lớn có thể không an toàn dù GC performance trông tốt ở tải thấp.

## 12. Chọn tỷ lệ theo một quy trình có thể kiểm chứng

### Bước 1 — Xác nhận RAM thực JVM nhận diện

Dùng Kubernetes/Docker configuration **và** `-XshowSettings:system` hoặc container log. Không tuning dựa trên yêu cầu (request) khi JVM sizing theo giới hạn (limit).

### Bước 2 — Ghi các override

Kiểm tra `-Xmx`, `-Xms`, `MaxRAM`, startup scripts, `JAVA_TOOL_OPTIONS`. Nếu `-Xmx` đang bật, percentage có thể không còn quyết định maximum heap.

### Bước 3 — Đo native footprint

Đo ở tải gần thực tế, bao gồm peak concurrency và thời điểm nhiều direct buffers/threads nhất. Không chỉ nhìn mức RAM khi ứng dụng idle.

### Bước 4 — Chọn tỷ lệ để thử

Ví dụ một giá trị **60–70%** có thể là khởi điểm **chỉ để kiểm thử** trên một service có native footprint vừa phải. Đây **không phải tỷ lệ được bảo đảm an toàn** cho mọi ứng dụng. Có hệ thống nên thấp hơn, có hệ thống phù hợp với tỷ lệ khác.

### Bước 5 — Đọc actual heap max

Dùng `MaxHeapSize`, `-XshowSettings:vm` hoặc `Runtime.maxMemory()`. Đừng chỉ nhân percentage trên giấy.

### Bước 6 — Chạy workload và đo

Đo Java heap used/committed/max, GC pauses, p95/p99 latency, CPU, throughput, container memory và OOM events.

### Bước 7 — Thử một thay đổi và có rollback

Nếu heap quá nhỏ khiến GC lặp nhiều nhưng native memory vẫn thấp, có thể thử tăng tỷ lệ. Nếu container OOM kill mà heap chưa đầy, cân nhắc giảm tỷ lệ hoặc tối ưu native usage. Dùng staging/canary và giữ khả năng rollback.

## 13. Khi nào dùng `-Xmx` cố định?

**Percentage-based heap sizing** hữu ích khi:
- Một image chạy trên nhiều memory limits;
- Muốn max heap được tính lại theo môi trường ở **lần JVM khởi động mới**;
- Có thể đo native memory và xác minh container detection;
- Không có cờ max heap tường minh chồng chéo.

**`-Xmx` cố định** có thể hợp lý khi:
- Ứng dụng có heap budget đã benchmark chính xác;
- Cần chừa một lượng native RAM cố định lớn;
- Runtime cũ nhận diện cgroup không đáng tin;
- Muốn tách heap size khỏi các thay đổi deployment limits.

**Không có bảo đảm JVM tự thay maximum heap khi container memory limit được chỉnh trong lúc process đang chạy.** Heap maximum thường được xác định khi JVM startup. Nếu thay limit trong deployment, nên khởi động process mới và xác nhận lại.

## 14. Các lỗi thực tế và nguyên nhân

**Lỗi 1 — MaxRAMPercentage giới hạn tổng RAM JVM.**  
Sai. Nó điều chỉnh maximum Java heap, không trực tiếp giới hạn Metaspace, threads hay native memory.

**Lỗi 2 — 75% nghĩa JVM chiếm ngay 75% RAM.**  
Sai. Maximum heap khác used/committed và resident memory.

**Lỗi 3 — `MinRAMPercentage` là minimum heap.**  
Sai. Nó tham gia maximum heap sizing cho small-memory cases.

**Lỗi 4 — Percentage luôn thắng `-Xmx`.**  
Sai. `-Xmx` tường minh có ưu tiên đối với max heap.

**Lỗi 5 — Kubernetes request là container limit.**  
Sai. Request và limit có chức năng khác nhau.

**Lỗi 6 — Không đặt limit thì JVM sẽ tự lấy request.**  
Không được bảo đảm; JVM có thể thấy RAM host.

**Lỗi 7 — Java 10 đời đầu hỗ trợ mọi cgroups v2 hiện đại.**  
Không được giả định như vậy. Kiểm tra build và nâng JDK được hỗ trợ.

**Lỗi 8 — Container OOM kill luôn có Java `OutOfMemoryError` stack trace.**  
Sai. OS/container có thể kill process không có Java exception.

**Lỗi 9 — Heap max thấp nghĩa container chắc chắn an toàn.**  
Không. Direct/native memory có thể tăng đủ để vượt memory limit.

**Lỗi 10 — Chọn 95% để giảm GC luôn là tốt.**  
Sai. Có thể không còn headroom cho native memory.

**Lỗi 11 — Chỉ nhìn `Runtime.maxMemory()` sẽ biết container RAM.**  
Sai. Đây là Java heap max của process.

**Lỗi 12 — Đổi container limit làm max heap thay đổi ngay.**  
Không có cam kết; cần restart/kiểm tra mới.

**Lỗi 13 — Dùng `MaxRAMFraction` trong cấu hình mới.**  
Không nên. `MaxRAMPercentage` là lựa chọn hiện đại thay thế.

**Lỗi 14 — Đổi percentage mà không đo lại.**  
Sai phương pháp. Thay đổi heap ảnh hưởng GC, throughput và native headroom.

## 15. Checklist áp dụng

1. Xác định JDK vendor/version/build và container runtime.
2. Kiểm tra container **memory limit**, không nhầm với request.
3. Xác minh hỗ trợ cgroups v1/v2 và `UseContainerSupport`.
4. Đọc `-XshowSettings:system` trên JVM phù hợp.
5. Kiểm tra flags `-Xmx`, `-Xms`, `MaxRAM`, RAMPercentage.
6. Xác nhận **actual max heap**, không chỉ modeled heap.
7. Đo Metaspace, direct buffers, thread stacks và native use.
8. Chừa headroom cho peak workload và memory accounting.
9. Phân biệt heap OOME với container/OS OOM kill.
10. Đo GC pauses, p99 latency, throughput và container memory.
11. Không xem một tỷ lệ cố định là giải pháp chung.
12. Khi thay JDK hoặc container limit, kiểm chứng lại kết quả sizing.
13. Dùng canary và rollback khi thay memory budget.
14. Chỉ kết luận thành công khi có dữ liệu trước/sau.

## 16. Tự kiểm tra kiến thức

**1. Cờ `MaxRAMPercentage` được giới thiệu ở đâu?**  
Trong nhóm RAMPercentage options của JDK 10.

**2. Container limit 1 GiB, percentage 75% thì mô hình heap là bao nhiêu?**  
768 MiB; actual value cần xem JVM runtime.

**3. `-Xmx512m` và `MaxRAMPercentage=80` cùng đặt có ý nghĩa gì?**  
`-Xmx512m` có ưu tiên cho maximum heap.

**4. `MinRAMPercentage` có đặt heap tối thiểu không?**  
Không. Nó tham gia tính maximum heap ở small-memory cases.

**5. Kubernetes request khác limit thế nào?**  
Request phục vụ lập lịch; limit là ràng buộc memory usage.

**6. Vì sao 95% có thể gây container OOM kill?**  
Vì các thành phần ngoài heap cần RAM.

**7. Làm sao xác minh JVM nhận diện memory limit đúng?**  
Kiểm tra `-XshowSettings:system` hoặc `-Xlog:os+container` ở runtime phù hợp.

**8. Cách nào biết max heap thật?**  
`-XshowSettings:vm`, `MaxHeapSize` hoặc `Runtime.maxMemory()`.

**9. Java heap OOME có đồng nghĩa container OOM kill không?**  
Không. Chúng liên quan những giới hạn khác nhau.

**10. Cấu hình percentage có bảo đảm điều chỉnh heap khi limit đổi trong process đang chạy không?**  
Không. Heap max thường được chọn lúc JVM startup.

**11. Vì sao không dùng `MaxRAMFraction` cho cấu hình mới?**  
Các cờ Fraction cũ đã bị deprecated và được thay thế bằng dạng Percentage.

**12. Có một tỷ lệ phù hợp cho mọi ứng dụng không?**  
Không. Phải dựa trên native footprint, workload và benchmark.

## 17. Tổng kết

- **`-XX:MaxRAMPercentage` (JDK 10+)** giúp sizing **maximum Java heap** theo tỷ lệ memory mà JVM nhận diện.
- **Container memory limit** quan trọng hơn RAM host khi JVM được hỗ trợ và nhận diện cgroup chính xác.
- **Kubernetes request không phải limit**; không tự dùng request làm hard heap budget.
- **`-Xmx` ưu tiên hơn** percentage khi được đặt tường minh.
- **`MinRAMPercentage` không phải minimum heap**; liên quan sizing heap tối đa trên bộ nhớ nhỏ.
- **Heap không phải tổng RAM process**; phải chừa headroom cho Metaspace, threads, direct buffers và JVM native allocations.
- Xác minh actual max heap bằng **`-XshowSettings:vm`**, **`MaxHeapSize`** hoặc **`Runtime.maxMemory()`**.
- Đo trong container thật, xác minh cgroups và tránh tỷ lệ quá cao khi native footprint lớn.
- Chọn mức phù hợp bằng **benchmark, quan sát memory và kế hoạch rollback**, không chỉ một phép nhân phần trăm.

**Tài liệu chính thức và còn áp dụng:**
- [Oracle JDK 10 Release Notes: Container Awareness, RAMPercentage options](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html).
- [Oracle Java SE 17: java launcher, MaxRAMPercentage, MinRAMPercentage, UseContainerSupport](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Oracle Java SE 25: java launcher, heap sizing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
- [Red Hat Developer: Java 17 container awareness](https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness).

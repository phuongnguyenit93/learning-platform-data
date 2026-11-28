# CDS và cơ chế AOT được bản JDK lựa chọn hỗ trợ

Khi một ứng dụng Java khởi động, Java Virtual Machine (JVM) phải chuẩn bị môi trường chạy, tìm và nạp các lớp, liên kết các tham chiếu cần thiết, khởi tạo những thành phần của ứng dụng và, khi có đủ thông tin runtime, tối ưu mã được thực thi thường xuyên. Với ứng dụng chạy ngắn, tác vụ dòng lệnh, serverless hoặc dịch vụ cần scale nhanh, **thời gian khởi động (startup)** và **thời gian đạt hiệu năng ổn định (warm-up)** có thể quan trọng không kém throughput sau khi hệ thống đã chạy lâu.

Trong hệ sinh thái Java 27, hai nhóm cơ chế đáng tìm hiểu là:

- **Class Data Sharing (CDS) và Application Class Data Sharing (AppCDS):** lưu một số dữ liệu lớp ở dạng archive để JVM có thể sử dụng lại nhanh hơn và chia sẻ những trang bộ nhớ phù hợp giữa nhiều tiến trình.
- **Ahead-of-Time (AOT) cache của HotSpot:** ghi nhận những gì ứng dụng thực sự làm trong một đợt *training*, rồi chuẩn bị các artifact trước lần chạy sau để giảm một phần công việc startup/warm-up. AOT cache dựa trên CDS nhưng có phạm vi tối ưu rộng hơn, tùy phiên bản và implementation.

Từ khóa **“được bản JDK lựa chọn hỗ trợ”** là ràng buộc quan trọng. Những tùy chọn như `-XX:AOTCache`, `-XX:AOTMode` và `-XX:ArchiveClassesAtExit` được tài liệu hóa cho **HotSpot trong các bản JDK tương ứng**; không được mặc định mọi Java Virtual Machine, nhà cung cấp JDK hoặc GraalVM Native Image có cùng tính năng và cú pháp.

Bài thuộc chương **Chẩn đoán và hiệu năng** trong module **Java 27 và các kiến thức liên quan**. Nội dung ưu tiên các cơ chế **vẫn áp dụng ở Java SE 27**; ví dụ cũ về CDS chỉ được nêu khi còn là tính năng hiện hành và có lý do sử dụng, không coi các cờ thử nghiệm hoặc hướng dẫn từ thời Java 8 là đường đi mặc định cho JDK 27.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích khác biệt giữa **class loading**, **class data sharing**, **AOT cache**, **JIT compilation** và **native-image**.
2. Biết vì sao archive có thể cải thiện startup nhưng không thể thay thế việc tối ưu SQL, I/O hay logic ứng dụng.
3. Nhận diện **CDS archive mặc định** của một bản phân phối JDK hỗ trợ, không tạo lại archive không cần thiết.
4. Tạo và sử dụng **dynamic AppCDS archive** bằng `-XX:ArchiveClassesAtExit` và `-XX:SharedArchiveFile`.
5. Thực hiện quy trình **AOT training → assembly → production** bằng các option được tài liệu Java SE 27 mô tả.
6. Phân biệt chế độ `AOTMode=auto`, `record`, `create`, `required` và `off`; biết trường hợp nên tránh fail-fast trên production.
7. Dùng `-Xlog:cds`, `-Xlog:aot`, `-Xlog:class+load` và `jcmd` để quan sát thay vì đoán cache đã có hiệu lực.
8. Hiểu cache phụ thuộc **ứng dụng, JDK release/build, OS/CPU, classpath/module path và một số runtime options**.
9. Thiết kế training đủ đại diện, tránh cache thừa hoặc không khớp với lần chạy production.
10. Đánh giá hiệu quả bằng benchmark có **cold/warm run**, latency, throughput, RSS/PSS, disk footprint và resource constraints.
11. Biết khi nào CDS, HotSpot AOT cache, hoặc một công cụ AOT/natively compiled của vendor khác phù hợp hơn.

## 2. Phân biệt startup, warm-up và steady-state

### 2.1. Ba giai đoạn không đồng nhất

| Khái niệm | Điều đang xảy ra | Tác động mà CDS/AOT có thể mang lại |
|---|---|---|
| **Startup** | VM khởi động; classes được tìm/nạp/liên kết; cấu hình và thành phần ứng dụng khởi tạo | Giảm một phần công việc xử lý class và những artifact có thể tái sử dụng |
| **Warm-up** | JIT quan sát các phương thức chạy nhiều, thu thập profile và tối ưu | Một số AOT optimization có thể chuyển công việc sang giai đoạn chuẩn bị |
| **Steady-state** | Ứng dụng đã xử lý đủ workload, JIT và caches tương đối ổn định | Không nhất thiết tăng throughput đáng kể, có thể gần như tương đương |

Một cải thiện **startup 100 ms** có thể quan trọng cho command-line tool chỉ chạy 300 ms, nhưng ít tác động đến dịch vụ chạy nhiều tháng. Ngược lại, dịch vụ cần scale từ 0 lên hàng chục instances sau một sự kiện tải tăng đột biến có thể hưởng lợi lớn từ khả năng sẵn sàng nhanh.

### 2.2. Đừng đồng nhất thời điểm main bắt đầu với startup end-to-end

Ví dụ:

~~~java
public final class StartupTimer {
    public static void main(String[] args) {
        long start = System.nanoTime();
        System.out.println("Inside main: " +
                (System.nanoTime() - start) + " ns");
    }
}
~~~

Đồng hồ bắt đầu **sau** giai đoạn JVM startup đã xảy ra trước khi `main` được gọi. Nó không đo tổng thời gian thực tế từ lúc OS tạo process cho tới lúc ứng dụng nhận request đầu tiên.

Để đo startup, phải chọn một mốc rõ: process start → `main`, process start → log sẵn sàng, process start → HTTP health-check thực sự sẵn sàng, hay startup → đáp ứng request đầu tiên theo SLA.

### 2.3. AOT không tự loại bỏ JIT

“Chuẩn bị trước khi chạy” trong HotSpot AOT cache **không đồng nghĩa** mọi class, mọi phương thức Java được chuyển thành một native executable cố định. HotSpot vẫn có runtime, GC, dynamic class loading và cơ chế biên dịch JIT trong các trường hợp thích hợp.

Có thể hình dung:

~~~text
Không cache:
  Java bytecode -> JVM load/link -> chạy -> quan sát profile -> JIT tối ưu

CDS:
  Java bytecode + shared class metadata archive -> JVM -> chạy/JIT

HotSpot AOT cache:
  Training -> ghi thông tin -> tạo cache -> JVM tải artifact phù hợp -> chạy/JIT
~~~

AOT cache có thể rút ngắn phần công việc mà runtime phải làm lại; nó **không** sửa các bottleneck về network, database, lock contention hoặc code thuật toán chậm.

## 3. CDS: Class Data Sharing là gì?

### 3.1. Archive chia sẻ dữ liệu lớp

CDS cho phép HotSpot lưu dữ liệu của những lớp được chọn vào archive đã ở dạng phù hợp với VM. Khi khởi chạy, JVM có thể memory-map phần dữ liệu tương ứng, giảm việc đọc và xử lý lại class bytes từ JAR/runtime image.

Với những vùng dữ liệu có thể chia sẻ an toàn, nhiều tiến trình Java trên cùng máy cũng có thể sử dụng các trang vật lý chung thay vì mỗi tiến trình giữ bản sao hoàn toàn riêng biệt.

~~~mermaid
flowchart TB
    A[CDS archive .jsa] -->|memory map| B[JVM process A]
    A -->|memory map| C[JVM process B]
    A -->|memory map| D[JVM process C]
~~~

**Điểm cần hiểu:** shared pages không có nghĩa toàn bộ heap, thread stacks, JIT code cache hoặc object sống của các tiến trình được hợp nhất. Mỗi JVM vẫn có bộ nhớ và trạng thái riêng.

### 3.2. CDS archive mặc định

Nhiều bản phân phối HotSpot JDK hiện hành, bao gồm Oracle JDK, cung cấp một **default CDS archive** được tạo sẵn với những lớp platform phổ biến. Nếu không tắt, JVM thường thử dùng nó theo mặc định.

Trong bản phân phối Oracle JDK, archive thường được đặt gần thành phần VM, ví dụ dưới `JAVA_HOME/lib/server/classes.jsa` trên các hệ Unix-like; đường dẫn thực tế phụ thuộc layout nhà cung cấp và hệ điều hành. **Không hardcode đường dẫn này** trong ứng dụng: cần kiểm tra bản JDK thực tế và log JVM.

Có thể quan sát:

~~~bash
java -Xlog:cds=info -version
~~~

Nếu JVM không nhận tag log hoặc tùy chọn này, trước hết kiểm tra vendor/VM bằng `java -version` và `java -Xlog:help` thay vì khẳng định JDK đó chắc chắn có HotSpot CDS.

### 3.3. Kiểm soát chế độ CDS

| Cờ | Hành vi | Đề xuất |
|---|---|---|
| `-Xshare:auto` | Sử dụng shared class data nếu có thể | Chế độ mặc định và thường phù hợp |
| `-Xshare:off` | Không thử dùng CDS | So sánh/baseline hoặc chẩn đoán |
| `-Xshare:on` | Bắt buộc dùng CDS, nếu không được thì fail | Chỉ nên dùng cho kiểm tra, không làm default production |

Nếu chạy thành công với `-Xshare:off` mà lỗi khi `-Xshare:on`, vấn đề có thể nằm ở compatibility/archive, không nhất thiết là lỗi trong source code Java.

### 3.4. Vì sao CDS có thể giảm memory footprint?

Một archive được memory-map có thể khiến **virtual address space** trông lớn hơn trong một số công cụ, nhưng các trang read-only thực sự có thể được chia sẻ giữa nhiều tiến trình. Vì vậy, không kết luận “CDS dùng nhiều RAM hơn” chỉ từ một số liệu virtual memory.

Trong môi trường container, nên xem RSS/PSS hoặc số liệu phân bổ memory cgroup trong điều kiện đúng workload. Tùy OS/container/runtime layout, mức chia sẻ trang vật lý có thể khác nhau.

## 4. AppCDS: mở rộng archive tới lớp ứng dụng

### 4.1. CDS platform và AppCDS khác nhau ở đâu?

**CDS archive mặc định** thường tập trung vào các lớp core/platform có lợi cho nhiều chương trình.

**AppCDS** lưu thêm những class từ ứng dụng/dependencies được JVM quan sát và hỗ trợ archive, ví dụ các class trong `app.jar` hoặc JAR dependencies. Điều này có thể cải thiện startup riêng của workload có nhiều framework classes.

~~~text
Default CDS:
  classes JDK phổ biến

AppCDS:
  default classes + những classes của app/framework được archive
~~~

Không phải **mọi** class được load đều chắc chắn được archive; HotSpot kiểm tra class loader, classpath/module path và một số ràng buộc tương thích.

### 4.2. Dynamic AppCDS bằng ArchiveClassesAtExit

Mẫu hiện hành của Oracle Java SE 27:

~~~bash
# Training/run thử với application JAR đã build.
java -XX:ArchiveClassesAtExit=app.jsa \
     -cp app.jar com.example.Main

# Chạy lần sau dùng dynamic archive đã tạo.
java -XX:SharedArchiveFile=app.jsa \
     -cp app.jar com.example.Main
~~~

Đây là **mẫu command**, giả định `app.jar` có class `com.example.Main`. Trong những tình huống phù hợp, `app.jsa` chứa lớp được load trong lần chạy training và sử dụng default static archive làm nền.

`ArchiveClassesAtExit` được hỗ trợ nhưng là lựa chọn CDS-style; với workload trên HotSpot JDK 27 có **AOT cache** phù hợp, nên đánh giá AOT cache trước vì nó có thể thực hiện nhiều tối ưu hơn.

### 4.3. Dynamic archive và static archive

HotSpot có thể dùng tối đa hai archive CDS trong mô hình static/dynamic:

- **Static archive:** chứa bộ dữ liệu nền.
- **Dynamic archive:** bổ sung lớp trên nền static archive, có thể ghi nhận liên hệ đến archive nền.

Nếu chỉ cung cấp `app.jsa` tạo từ default static archive, JVM có thể tìm archive nền theo metadata phù hợp; không cần người dùng tự ghép đường dẫn trong mọi trường hợp.

Khi phải chỉ định cả hai archive:

~~~text
-XX:SharedArchiveFile=<static_archive>:<dynamic_archive>
~~~

Trên **Windows**, dùng `;` thay cho dấu `:` để phân cách hai đường dẫn theo quy tắc option này. Dấu phân cách đó không liên quan tới dấu phân cách của `java.class.path` trong source code.

### 4.4. Khi nào AppCDS đáng cân nhắc?

- Ứng dụng server khởi động nhiều framework classes.
- Nhiều instance cùng dùng các classes chung.
- Startup là một KPI thật và đã được đo.
- Có khả năng giữ binary/classpath ổn định từ training đến production.
- Không muốn hoặc không thể thay đổi quy trình hiện tại sang AOT cache ngay.

Nhưng với ứng dụng nhỏ chỉ vài class, chi phí thêm archive/CI/deployment có thể lớn hơn lợi ích thực tế.

## 5. AOT cache của HotSpot trong Java 27

### 5.1. Khái niệm và phạm vi

HotSpot AOT cache là nơi chứa những artifact chuẩn bị trước để dùng lại cho một application/JDK/nền tảng cụ thể. Nó phát triển từ CDS, gắn với **Project Leyden** và các cải tiến như:

- **JEP 483 (JDK 24):** Ahead-of-Time Class Loading & Linking.
- **JEP 514 (JDK 25):** Ahead-of-Time Command-Line Ergonomics, giảm công sức tạo và dùng cache.
- **JEP 515 (JDK 25):** Ahead-of-Time Method Profiling, giúp giảm một phần chi phí warm-up dựa trên profile thu trong training.
- **JEP 516 (JDK 26):** Ahead-of-Time Object Caching with Any GC, mở rộng khả năng dùng object caching với các garbage collectors, kể cả ZGC.

Các JEP trên đã trở thành một phần lịch sử phát triển tính năng đang được sử dụng trong JDK 27; không cần bật preview flag của những bản thử nghiệm cũ.

### 5.2. AOT cache lưu những gì?

Tùy JDK/HotSpot build và tối ưu hóa cụ thể, cache có thể bao gồm dữ liệu class loading/linking, object graph phù hợp với caching và thông tin hỗ trợ tối ưu warm-up như method profiling.

**Không mặc định AOT cache là một executable chứa sẵn mã máy cho toàn bộ ứng dụng.** Những artifact cụ thể, khả năng hỗ trợ và lợi ích phải đọc theo tài liệu **đúng bản JDK**.

Một cache có thể giúp tải nhanh classes mà ứng dụng hay dùng, nhưng không thể biết trước tất cả dữ liệu runtime như token đăng nhập, phản hồi API, thời gian mạng hay trạng thái DB.

### 5.3. Training và cache phải tương ứng application thật

AOT cache thường đặc thù theo:

1. Ứng dụng được biểu diễn bởi `-cp`, `-jar` hoặc `--module-path` / module graph.
2. JDK release/build phù hợp.
3. OS và CPU architecture.
4. Các VM options có ảnh hưởng đến class loading/module graph hoặc cơ chế AOT.
5. Nội dung và phiên bản JAR classes/dependencies đã training.

Thay `app.jar`, thêm agent hoặc đổi cách khởi động có thể khiến cache bị từ chối hoặc chỉ dùng một phần dữ liệu. Không dùng cache như artifact “build once, run on every platform”.

## 6. Quy trình AOT hiện hành: record, create, production

### 6.1. Ba pha logic

~~~mermaid
flowchart LR
    T[Training run: record] -->|*.aotconfig| A[Assembly: create]
    A -->|*.aot| P[Production JVM]
    P -->|runtime startup/warm-up| R[Application]
~~~

- **Record/training:** chạy ứng dụng với workload đại diện, ghi lại dữ liệu cần cho AOT.
- **Create/assembly:** biến dữ liệu training thành artifact AOT; ứng dụng thường **không** thực thi logic nghiệp vụ trong pha assembly.
- **Production:** nạp cache phù hợp và chạy ứng dụng như bình thường.

### 6.2. Hai lệnh: AOTCacheOutput rồi AOTCache

Ở HotSpot JDK 27, quy trình thuận tiện:

~~~bash
# Training. Khi kết thúc, JVM phối hợp tạo app.aot.
java -XX:AOTCacheOutput=app.aot \
     -cp app.jar com.example.Main

# Production. Dùng cache khi hợp lệ.
java -XX:AOTCache=app.aot \
     -cp app.jar com.example.Main
~~~

`-XX:AOTCacheOutput=app.aot` ở chế độ `AOTMode=auto` (mặc định) khởi động một training run và thực hiện assembly sau đó. Pha assembly có thể dùng **một JVM con**. Điều này tiêu tốn thêm bộ nhớ/CPU tạm thời trong quá trình tạo cache.

`-XX:AOTCache=app.aot` ở `auto` thường là lựa chọn production: nếu cache không tương thích, JVM có thể tiếp tục không dùng cache thay vì dừng ứng dụng.

### 6.3. Ba lệnh tách rời

Nếu muốn kiểm soát riêng training và assembly:

~~~bash
# 1. Record: ứng dụng chạy workload đại diện.
java -XX:AOTMode=record \
     -XX:AOTConfiguration=app.aotconfig \
     -cp app.jar com.example.Main

# 2. Create: chuẩn bị cache; app không chạy nghiệp vụ.
java -XX:AOTMode=create \
     -XX:AOTConfiguration=app.aotconfig \
     -XX:AOTCache=app.aot \
     -cp app.jar com.example.Main

# 3. Production: sử dụng cache.
java -XX:AOTCache=app.aot \
     -cp app.jar com.example.Main
~~~

Dùng **cùng application artifacts và các tùy chọn cấu hình có ý nghĩa** giữa các pha, thay vì chạy record với dependencies khác rồi đóng gói cache cho một binary khác.

Quy trình ba pha thích hợp khi môi trường tạo cache cần nhiều tài nguyên hơn môi trường ghi workload training, hoặc khi pipeline CI muốn kiểm tra artifact trung gian.

### 6.4. Kết thúc training thế nào?

Thông thường, training kết thúc khi JVM thoát một cách thích hợp. Với dịch vụ web không tự dừng, cần một phương án kết thúc training có kiểm soát:

- Cho service chạy các workload tiêu biểu và shutdown bình thường.
- Dùng diagnostic command `jcmd <pid> AOT.end_recording` khi HotSpot build hỗ trợ.
- Có thể dùng `HotSpotAOTCacheMXBean.endRecording()` trong `jdk.management` nếu API quản lý phù hợp với ứng dụng.

Không nên chèn logic chỉ dành cho training vào hàng loạt điểm code nghiệp vụ nếu điều đó khiến workload training khác xa cách ứng dụng vận hành thật. `endRecording()` kết thúc phần ghi AOT nhưng không nhất thiết **shutdown ứng dụng**; cần quy trình dừng service riêng.

## 7. Ý nghĩa các option AOTMode trong Java SE 27

### 7.1. Bảng tra cứu

| Option | Ý nghĩa | Dùng khi |
|---|---|---|
| `-XX:AOTMode=auto` | Mặc định: dựa trên cache/output mà chọn record, required hoặc off; có thể bỏ qua cache không dùng được | Production và workflow thông thường |
| `-XX:AOTMode=off` | Không dùng AOT cache | Baseline/chẩn đoán |
| `-XX:AOTMode=record` | Chạy training, ghi cấu hình và/hoặc tạo cache theo option | Training tường minh |
| `-XX:AOTMode=create` | Assembly từ `.aotconfig` thành `.aot` | Bước tạo artifact riêng |
| `-XX:AOTMode=required` | Yêu cầu phải load cache hợp lệ, nếu không fail startup | Kiểm tra fail-fast trong CI |
| `-XX:AOTMode=on` | Alias tương đương `required` trong Java SE 27, không khuyến nghị dùng mới | Tránh sử dụng trong script mới |

**Khuyến nghị:** dùng `required` khi cần kiểm chứng tương thích (ví dụ CI smoke test), nhưng **không biến nó thành cấu hình mặc định production** nếu JVM options có thể bị thay đổi bởi agent, APM hoặc nền tảng vận hành.

### 7.2. Các cặp option không được dùng cùng nhau

`-XX:AOTCache=...` dùng để chỉ cache đầu vào, hoặc trong chế độ create là file đầu ra. `-XX:AOTCacheOutput=...` là đích của quy trình training + assembly thuận tiện.

Theo tài liệu HotSpot 27, **không dùng `-XX:AOTCache` và `-XX:AOTCacheOutput` trong cùng một invocation**. Nếu chỉ muốn hai bước, dùng `AOTCacheOutput` ở training và `AOTCache` ở production.

### 7.3. Chẩn đoán fail-fast

~~~bash
java -XX:AOTMode=required \
     -XX:AOTCache=app.aot \
     -Xlog:aot=info \
     -cp app.jar com.example.Main
~~~

Nếu archive không tồn tại hoặc không tương thích, chế độ `required` sẽ fail startup. Đây là cách hữu ích để xác nhận cấu hình CI.

Sau khi xác minh, production thường dùng:

~~~bash
java -XX:AOTMode=auto \
     -XX:AOTCache=app.aot \
     -Xlog:aot=info \
     -cp app.jar com.example.Main
~~~

Không nên chỉ nhìn tiến trình khởi động thành công để kết luận cache đã được dùng, vì `auto` có thể fallback thành chạy không có AOT cache.

## 8. Ví dụ Java độc lập cho CDS/AOT

Đoạn dưới có thể chạy chỉ với JDK 27 và không yêu cầu framework, database hoặc service bên ngoài. Lưu tên `AotStartupDemo.java`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public final class AotStartupDemo {

    public static void main(String[] args) {
        int checksum = IntStream.rangeClosed(1, 1_000)
                .filter(n -> n % 7 == 0)
                .sum();

        List<String> topics = List.of(
                        "cds", "aot", "java-27", "startup")
                .stream()
                .map(String::toUpperCase)
                .sorted()
                .toList();

        System.out.println("Topics: " + topics);
        System.out.println("Checksum: " + checksum);
    }
}
~~~

### 8.1. Biên dịch và tạo JAR

~~~bash
javac AotStartupDemo.java
jar --create --file app.jar AotStartupDemo.class
~~~

Ví dụ này không cần `Main-Class` trong manifest vì các command phía sau chạy qua `-cp app.jar AotStartupDemo`.

### 8.2. Chạy bình thường với log class loading

~~~bash
java -Xlog:class+load=info \
     -cp app.jar AotStartupDemo
~~~

Log có thể cho biết một class được load từ runtime image, JAR hay shared archive. Đừng dựa vào thứ tự class loading log như một API ổn định giữa các HotSpot updates.

### 8.3. Tạo và dùng dynamic AppCDS

~~~bash
java -XX:ArchiveClassesAtExit=demo.jsa \
     -cp app.jar AotStartupDemo

java -Xlog:cds=info \
     -XX:SharedArchiveFile=demo.jsa \
     -cp app.jar AotStartupDemo
~~~

Nếu nhận thông báo archive không hợp lệ, hãy kiểm tra JDK, classpath và các option đồng nhất trước khi kết luận feature có lỗi.

### 8.4. Tạo và dùng AOT cache

~~~bash
java -XX:AOTCacheOutput=demo.aot \
     -cp app.jar AotStartupDemo

java -Xlog:aot=info \
     -XX:AOTCache=demo.aot \
     -cp app.jar AotStartupDemo
~~~

`demo.jsa` và `demo.aot` là **hai loại artifact khác nhau**. Không đổi tên file `.jsa` thành `.aot` rồi mong chúng có thể dùng thay nhau.

### 8.5. Đây là demo API, không phải benchmark đại diện

Vì ứng dụng quá nhỏ, mức chênh lệch có thể không đáng kể hoặc bị nhiễu bởi OS process launch và filesystem cache. Kết quả của một lần đo demo không chứng minh CDS/AOT luôn cải thiện dịch vụ production. Việc đánh giá phải theo workload và startup milestone thật.

## 9. Dùng jcmd với CDS hoặc AOT

### 9.1. jcmd VM.cds cho JVM đang chạy

Trong một số tình huống, không dễ chỉnh sửa startup script để ghi archive AppCDS. HotSpot cung cấp diagnostic command:

~~~bash
# Liệt kê JVM đang chạy để lấy PID.
jcmd -l

# Dump CDS archive cho JVM cụ thể.
jcmd <pid> VM.cds static_dump current-static.jsa

# Nếu chuẩn bị dynamic dump, JVM đích phải bật
# -XX:+RecordDynamicDumpInfo lúc startup.
jcmd <pid> VM.cds dynamic_dump current-dynamic.jsa
~~~

Các lệnh trên chỉ nên chạy khi bạn có quyền quan sát tiến trình đó. Đúng PID và user có quyền attach JVM là điều kiện cần. `VM.cds` có thể gây pause có chi phí tùy số lớp đã load; không tự động thực hiện trên mọi production replica cùng lúc.

### 9.2. AOT.end_recording

JDK 27 có diagnostic command:

~~~bash
jcmd <pid> AOT.end_recording
~~~

Lệnh này dùng khi **JVM đích đã bắt đầu một AOT training run** bằng option phù hợp. Nếu JVM đang chạy production bình thường và chưa ghi AOT, không thể gọi `AOT.end_recording` để tự động sinh archive từ đầu.

Thời điểm kết thúc training cần đủ để những luồng khởi tạo, dependency và đường code cần tối ưu đã chạy đại diện.

### 9.3. Không nhầm VM.cds với AOT.end_recording

| Công cụ | Đối tượng | Kết quả |
|---|---|---|
| `-XX:ArchiveClassesAtExit=...` | Dynamic CDS | `.jsa` khi JVM kết thúc phù hợp |
| `jcmd <pid> VM.cds ...` | CDS | Archive `.jsa` |
| `-XX:AOTCacheOutput=...` | AOT workflow | AOT artifact `.aot` sau training/assembly |
| `jcmd <pid> AOT.end_recording` | AOT đang record | Kết thúc phần ghi AOT đang chạy |
| `-XX:AOTCache=...` | AOT production | Nạp `.aot` khi tương thích |

Không lấy `jcmd VM.cds` để giả lập việc tạo đầy đủ HotSpot AOT cache hoặc ngược lại.

## 10. Cache compatibility: tại sao không dùng được?

### 10.1. Application identity và classpath

Một archive ứng dụng phụ thuộc tập class mà runtime dự kiến. Ví dụ:

~~~text
Training:
  -cp app.jar:lib/a.jar:lib/b.jar

Production:
  -cp app.jar:lib/b.jar:lib/a.jar
~~~

Đổi thứ tự classpath có thể làm thay đổi class resolution/identity hoặc các assumption mà archive cần. Không đoán rằng hai classpath “trông như nhau” luôn dùng chung cache.

Khác biệt giữa exploded classes directory, JAR đóng gói, nested JAR và fat JAR/boot loader cũng có thể tác động việc archive các classes; phải kiểm tra cách launcher/framework thực sự bố trí classpath.

### 10.2. JDK release/build và OS/architecture

Không tái sử dụng `app.aot` từ:

- JDK 26 sang JDK 27 như một artifact bất biến.
- Linux x86_64 sang Windows hoặc macOS.
- Linux x86_64 sang Linux aarch64.
- Một runtime khác vendor/implementation mà không có tài liệu bảo đảm tương thích.

JDK patch/build hoặc khác cấu hình runtime cũng có thể ảnh hưởng khả năng sử dụng. **Quy trình đáng tin cậy là tạo archive trong build matrix khớp target** và xác minh bằng fail-fast smoke test.

### 10.3. Module graph và instrumentation agents

Những option làm thay đổi module path hoặc class loading có thể làm archive không còn tương thích. Ví dụ tài liệu HotSpot ghi nhận `--upgrade-module-path`, `--patch-module` và `--limit-modules` có các hạn chế với CDS, còn một số JVMTI instrumentation/callback có thể làm AOT cache không nạp được.

Các công cụ APM/tracing dùng Java agents có thể thay đổi bytecode lúc startup. Vì vậy, training/assembly với **không agent** rồi production với **agent sửa classes** có thể làm cache bị bỏ qua.

Không tắt observability hoặc agent bảo mật chỉ để “ép” cache hoạt động. Hãy xác định lựa chọn ưu tiên, hỗ trợ của vendor và đo lợi ích thực.

### 10.4. Chênh lệch property, environment, framework mode

Nếu startup code dựa vào property để chọn module/classes, training khác production có thể làm đường code học được không đại diện.

~~~text
Training:  -Dapp.profile=dev
Production: -Dapp.profile=prod
~~~

Ngay cả khi archive vẫn có thể được nạp, cache có thể bỏ sót những classes mà production thực sự dùng. Tốt hơn nên chọn **workload và configuration training gần production**, không ghi trực tiếp secrets vào archive hay log.

### 10.5. Cache là artifact cần integrity

Archive ảnh hưởng đường class loading của JVM. Vì vậy cần:

- Lưu cache trong thư mục chỉ pipeline/release owner có quyền ghi.
- Dùng checksum/signature/provenance nếu cache được phân phối.
- Phân biệt cache theo application version, JDK build, OS và CPU.
- Không dùng `app.aot` do người dùng không tin cậy upload.
- Tạo lại cache sau khi thay classes/dependencies; không ép tải archive không khớp.
- Không công khai dữ liệu nhạy cảm trong quá trình training hoặc lưu artifacts mà không kiểm tra nội dung/nguồn.

`-XX:+VerifySharedSpaces` có thể thực hiện kiểm tra CRC32 phát hiện hỏng archive CDS ngoài ý muốn; **CRC32 không phải chữ ký số chống giả mạo**. Vẫn cần quản trị nguồn artifacts.

## 11. Quan sát bằng Unified Logging

### 11.1. Các log tags thường hữu ích

~~~bash
# Chẩn đoán class data sharing.
java -Xlog:cds=info -cp app.jar AotStartupDemo

# Chẩn đoán AOT cache.
java -Xlog:aot=info \
     -XX:AOTCache=demo.aot \
     -cp app.jar AotStartupDemo

# Nguồn class loading, mức độ chi tiết có thể lớn.
java -Xlog:class+load=info -cp app.jar AotStartupDemo
~~~

Kiểm tra tags và mức log mà **VM đang chạy** hỗ trợ:

~~~bash
java -Xlog:help
~~~

Không nên mặc định một JVM khác HotSpot có cùng tags hoặc cùng dòng output. Nên lưu **JDK vendor, build number, VM name và flags** cùng log khi so sánh các lần triển khai.

### 11.2. Hiểu log của auto mode

Nếu `AOTMode=auto` và archive không phù hợp, JVM có thể tiếp tục chạy bình thường. Điều này **không phải** bằng chứng cache đã giúp startup.

Cần tìm thông tin chấp nhận/từ chối archive và thống nhất cách kiểm tra trong pipeline. Một smoke test với `-XX:AOTMode=required` có thể dùng để **ép báo lỗi sớm khi archive không nạp được**; không nên làm yêu cầu cứng ở mọi production instance có cấu hình thay đổi.

### 11.3. Log nhiều không đồng nghĩa nhanh hơn

`-Xlog:class+load=info` có thể tạo lượng output lớn và làm biến dạng thời gian khởi động, đặc biệt khi ghi đồng bộ ra terminal hoặc log collector. Benchmark nên:

1. Dùng logging đủ để xác minh configuration ở lượt riêng.
2. Tắt hoặc giảm log ở các lượt đo hiệu năng.
3. Ghi nhận mọi khác biệt flags giữa các phép đo.

Chỉ bật log chi tiết khi cần chẩn đoán, không trộn thời gian xuất log vào “chi phí CDS/AOT”.

## 12. Đánh giá hiệu năng đúng phương pháp

### 12.1. So sánh ba biến thể

Để biết cơ chế nào có ích, so sánh:

- **Baseline:** JDK và ứng dụng không dùng custom AOT cache. Khi cần tách ảnh hưởng CDS, có thể đo thêm một lượt `-Xshare:off`.
- **CDS/AppCDS:** default archive hoặc `SharedArchiveFile=demo.jsa`.
- **AOT cache:** `AOTCache=demo.aot` và kiểm tra thực sự có nạp.

Mọi phép thử phải giữ ổn định application release, JDK build, machine resources, flags không liên quan, cấu hình DB/mock và trạng thái hệ thống.

### 12.2. Những KPI đáng đo

| Chỉ số | Mục tiêu quan sát |
|---|---|
| Process start → main | Phần khởi động JVM trước application logic |
| Process start → ready | Trải nghiệm sẵn sàng của CLI/service |
| First-request latency | Khả năng xử lý request ngay sau startup |
| p50/p95 latency trong warm-up | Độ trễ những phút đầu |
| Steady-state throughput | Hiệu suất khi JVM đã chạy ổn định |
| RSS/PSS/memory cgroup | Memory thực tế, mức chia sẻ trang giữa tiến trình |
| Archive file size | Chi phí disk image, phân phối và đọc cache |
| CPU cycles / I/O trong startup | Xác định bottleneck đã dịch chuyển chưa |
| Build/training time và CI resources | Chi phí để có artifact AOT |
| Cache acceptance rate | Bao nhiêu instance thật sự dùng cache |
| Error rate / correctness | Không được hy sinh tính đúng đắn vì tối ưu |

### 12.3. Cold vs warm filesystem cache

Một lần khởi chạy đầu sau khi cài đặt có thể phải đọc dữ liệu từ storage lạnh; những lần sau được OS page cache hỗ trợ. Nếu đo CDS/AOT mà không tách **filesystem cache** khỏi tác động JVM optimization, kết luận có thể sai.

Không nhất thiết phải drop OS caches trên môi trường production; nên có kịch bản đo lặp lại, ghi rõ điều kiện cold/warm và dùng cùng cách đo cho baseline/cached variant.

### 12.4. Phân phối nhiều tiến trình JVM

Với 10 tiến trình cùng dùng một archive trên cùng host, phần shared mapped pages có thể tiết kiệm bộ nhớ hệ thống. Nhưng process isolation/container image layers có thể ảnh hưởng liệu các trang có thực sự chung backing file hay không.

Đừng nhân “số byte archive” với “số instance” rồi khẳng định đó là tổng RAM tiết kiệm. Nên đo PSS hoặc chỉ số physical memory tương đương trong chính hạ tầng triển khai.

### 12.5. Đừng công bố con số tăng tốc từ demo cực nhỏ

Các JEP và bài benchmark của vendor có thể công bố mức tăng trên một tập workload cụ thể, nhưng không nên chuyển thành cam kết “startup nhanh hơn 30% trên mọi ứng dụng”.

Nếu ứng dụng phải chờ DB migration 10 giây hoặc chờ cấu hình mạng, tối ưu 200 ms ở class loading có thể không thay đổi đáng kể readiness tổng thể.

## 13. Training workload đại diện: chìa khóa của AOT cache

### 13.1. Tại sao không chỉ gọi main rồi thoát ngay?

Trong các framework lớn, nhiều lớp chỉ được load khi:

- HTTP server nhận request đầu tiên.
- Một module bắt đầu xử lý dữ liệu hoặc serialization.
- Một JDBC driver/database adapter được khởi tạo.
- Một endpoint hiếm gặp được gọi.
- Scheduler chạy batch hoặc job theo lịch.

Nếu chỉ chạy startup tối thiểu, cache có thể bỏ qua một phần lớp hoặc profile quan trọng. Một training run hữu ích nên bao gồm các code paths ảnh hưởng startup/warm-up của workload mục tiêu, trong điều kiện tài nguyên phù hợp.

### 13.2. Kế hoạch training service

~~~mermaid
flowchart TD
    S[Start training JVM với AOTCacheOutput] --> H[Chờ service ready]
    H --> W[Thực thi workload representative]
    W --> E[Kết thúc recording an toàn]
    E --> A[Assembly artifact .aot]
    A --> V[Smoke test required mode]
    V --> P[Publish cache cùng app và JDK target]
~~~

Có thể dùng integration tests đã tồn tại để tạo request workload, nhưng tránh các thao tác gây side effect không kiểm soát. Ví dụ training chỉ nên dùng database test/synthetic data, không gửi thanh toán thực hoặc email thật chỉ để warm-up.

### 13.3. Khi training có dữ liệu bí mật

Không đưa production credentials, personally identifiable information hoặc dữ liệu nhạy cảm vào một pipeline tạo artifact được chia sẻ rộng. Cache chứa các artifact tối ưu hóa gắn với ứng dụng/training và nên được xem là **file build có yêu cầu kiểm soát truy cập**.

Tùy threat model, có thể dùng dữ liệu giả lập tương ứng cấu trúc mà vẫn kích hoạt code paths cần thiết.

### 13.4. Không cố “preload toàn bộ classes” vô điều kiện

Việc buộc JVM load tất cả các classes trong một thư viện lớn có thể làm tăng thời gian/đĩa của training và archive, trong khi phần lớn classes không xuất hiện ở những đường code có ý nghĩa.

Mục tiêu là **workload đại diện**, không phải max số classes được archive. Cần đánh giá artifact footprint và lợi ích bằng số liệu.

## 14. Triển khai trong CI/CD và container

### 14.1. AOT artifact là một phần release

Một mô hình artifact:

~~~text
release/
  app.jar
  lib/
    dependency-a.jar
    dependency-b.jar
  aot/
    app-jdk27-linux-x86_64.aot
  run-app.sh
  manifest.json
~~~

`manifest.json` ở đây chỉ là ví dụ metadata do hệ thống phát hành của bạn quản lý, **không phải file JDK bắt buộc**. Có thể ghi application checksum, JDK vendor/build, OS/arch, cache checksum, flags và dấu mốc training.

Không nên phát hành một cache duy nhất cho tất cả nền tảng. Với đa kiến trúc, tạo artifact trong build matrix khớp target.

### 14.2. Container và đường dẫn tuyệt đối/relative

Một container production có thể sử dụng:

~~~bash
java -XX:AOTCache=/opt/app/aot/app.aot \
     -cp /opt/app/app.jar com.example.Main
~~~

Nếu classpath production ở `/opt/app` nhưng training dùng đường dẫn/layout khác, cần kiểm tra điều kiện tương thích của AOT. Đừng chỉ copy file `app.aot` vào container rồi giả định VM chắc chắn nạp được.

Nên train/assemble trong môi trường gần giống runtime image hoặc cung cấp được cấu hình/đường dẫn phù hợp theo tài liệu HotSpot.

### 14.3. Training + assembly có thể đòi RAM tạm thời lớn hơn

Quy trình `-XX:AOTCacheOutput` có thể khởi động JVM thứ hai cho assembly khi training JVM kết thúc. Trong môi trường resource-constrained, cấu hình heap lớn có thể khiến bước tạo cache thiếu memory dù ứng dụng chạy bình thường.

Giải pháp có thể là:

- Tách thành ba pha `record`/`create`/`production`.
- Dùng runner CI nhiều RAM hơn cho pha tạo cache.
- Giới hạn/tối ưu memory budget của các pha theo hướng dẫn vendor.
- Không ép cache generation chạy trong production pod với giới hạn bộ nhớ chặt.

### 14.4. Rollback và cache mismatch

Nếu rollback ứng dụng từ phiên bản B sang A nhưng vẫn trỏ đến cache tạo cho B, JVM có thể từ chối archive. Quy trình release nên gắn cache với đúng version và giữ lại artifact phù hợp cho rollback.

Với `AOTMode=auto`, service có thể tiếp tục chạy không cache; điều này bảo vệ availability nhưng có thể làm startup latency tăng. Cần quan sát tỷ lệ cache load thành công để tránh suy thoái hiệu năng âm thầm.

## 15. So sánh CDS, HotSpot AOT cache và native-image

### 15.1. Chúng giải quyết các mục tiêu khác nhau

| Tiêu chí | CDS/AppCDS HotSpot | HotSpot AOT cache | Native-image toolchain khác |
|---|---|---|---|
| Output | Archive `.jsa` | Cache `.aot` | Thường là executable hoặc shared library native |
| Runtime | JVM/HotSpot bình thường | JVM/HotSpot bình thường | Runtime/AOT model của toolchain tương ứng |
| Class linking/runtime | Tối ưu class data | Có thể cache thêm liên kết/đối tượng/profiling | Phân tích và biên dịch trước theo toolchain |
| JIT | Vẫn có thể hoạt động bình thường | Vẫn có thể hoạt động bình thường | Tùy implementation/native-image model |
| Dynamic features | Theo khả năng JVM và archive compatibility | Theo HotSpot và những ràng buộc cache | Có thể cần cấu hình reflection/resource/proxy |
| Tính di động cache/artifact | Phụ thuộc JDK/architecture và runtime | Phụ thuộc app/JDK/OS/CPU | Binary đặc thù OS/CPU/toolchain |
| Mục tiêu thường gặp | Startup và footprint | Startup và warm-up | Startup, memory, triển khai native theo sản phẩm |
| Chi phí vận hành | Archive generation/caching | Training, assembly, release alignment | Build native và quản lý metadata/compatibility |

**AOT của HotSpot không đồng nhất với “GraalVM Native Image”.** Không dùng `-XX:AOTCacheOutput` để giả định nó tạo `app.exe` hoặc binary native cho app Java.

### 15.2. Những JDK không dùng HotSpot

Một Java runtime triển khai JVM khác (ví dụ OpenJ9) có thể có cơ chế class sharing riêng. Các flag HotSpot `-XX:...` nêu trong bài có thể bị từ chối hoặc diễn giải khác.

Vì thế, trước khi hướng dẫn người khác bật CDS/AOT, cần ghi rõ:

~~~text
JDK vendor:
JDK full version/build:
JVM implementation:
OS / architecture:
Deployment packaging:
Supported CDS/AOT features:
~~~

Nếu `java -version` cho thấy runtime khác HotSpot, hãy mở tài liệu **của VM đó** thay vì sao chép command HotSpot.

### 15.3. Khi nào không nên sử dụng?

- Ứng dụng thường chạy hàng tuần, startup không quan trọng.
- Thời gian khởi động chủ yếu do external I/O, không phải class loading/warm-up.
- Build/deployment thay đổi classpath liên tục không kiểm soát.
- Môi trường có instrumentation class transformation không tương thích.
- Không có thời gian/nguồn lực kiểm thử cache trên ma trận JDK + OS + CPU.
- Lợi ích đo được nhỏ hơn chi phí training, disk, startup cache read và maintenance.

Không dùng AOT như “tối ưu miễn phí” khi chưa có bằng chứng hiệu quả.

## 16. Lỗi và anti-pattern thường gặp

| Vấn đề | Nguyên nhân thường gặp | Hướng khắc phục |
|---|---|---|
| Không thấy CDS được dùng | Archive mặc định thiếu hoặc bị tắt, JDK VM khác | `java -version`, `-Xlog:cds`, kiểm tra option |
| `-Xshare:on` làm ứng dụng không chạy | Archive không tương thích | Chỉ dùng kiểm tra; production thường dùng `auto` |
| AppCDS không nhận class ứng dụng | Layout classes/loader, classpath hoặc archive không khớp | Train với app đóng gói đúng, kiểm tra class loading log |
| `app.jsa` được đưa vào `-XX:AOTCache` | Nhầm loại artifact | Dùng `-XX:SharedArchiveFile` cho CDS |
| `app.aot` được đưa vào `-XX:SharedArchiveFile` | Nhầm AOT với CDS archive | Dùng `-XX:AOTCache` |
| App chạy được với AOT auto nhưng không nhanh hơn | Cache bị bỏ qua mà không fail | `-Xlog:aot`, smoke test required |
| `AOTMode=required` làm production fail | Runtime options/agent thay đổi | Không dùng required như mặc định; xác minh compatibility |
| Dùng `AOTMode=on` trong script mới | Alias không khuyến nghị | Dùng `required` khi muốn fail-fast |
| Gộp `AOTCache` và `AOTCacheOutput` một lần chạy | Option xung đột | Phân biệt training với production |
| Thay JAR nhưng giữ archive cũ | Cache gắn classpath/app identity | Tạo lại theo release |
| Copy cache Linux sang Windows | Cache không portable đa OS/CPU | Build matrix per target |
| Dùng JVM agent ở production nhưng không có khi training | Lệch class transformation/instrumentation | Đánh giá tương thích agent và chính sách thực thi |
| Training chỉ chạy `main` không kích hoạt workload | Cache thiếu code paths quan trọng | Chạy integration workload đại diện |
| Log quá nhiều trong benchmark | Logging làm nhiễu timing | Tách verification run khỏi measurement run |
| So sánh cold run với warm run khác kiểu | OS page cache/JIT khác nhau | Quy trình đo thống nhất, nhiều lần lặp |
| Đo thời gian bên trong `main` như tổng startup | Bỏ sót VM startup | Đo từ process launch tới readiness |
| Tưởng AOT cache tự giảm mọi độ trễ | Bottleneck thực ở DB/network | Phân tích performance profile và readiness |
| Không gắn cache với application version | Rollback mismatch, suy giảm âm thầm | Versioning, checksum, manifest |
| Tưởng mọi JVM đều hỗ trợ option HotSpot | `Unrecognized VM option` | Kiểm tra JDK implementation và docs phù hợp |

## 17. Checklist ứng dụng trước khi bật CDS/AOT

### 17.1. Checklist kỹ thuật

1. **Xác định JVM:** `java -version`, vendor, HotSpot hay VM khác, OS/arch và JDK build.
2. **Đặt KPI:** startup end-to-end, warm-up p95 hay memory sharing là mục tiêu?
3. **Kiểm tra CDS mặc định:** archive có sẵn và load được chưa?
4. **Chọn cơ chế:** chỉ cần default CDS, dynamic AppCDS, hay AOT cache đầy đủ?
5. **Đóng gói ổn định:** classpath/module path và dependency versions có được khóa không?
6. **Training đại diện:** workload và options gần production, không làm side effect không mong muốn?
7. **Chọn cache workflow:** hai bước `AOTCacheOutput` hoặc ba bước `record/create/production`?
8. **Chạy smoke test fail-fast:** xác minh cache có nạp được bằng `required` trong CI?
9. **Production auto:** có fallback khi cache không tương thích mà vẫn giữ khả năng quan sát?
10. **Logging hợp lý:** lưu log kiểm tra `cds`/`aot`, không bật class load debug thường xuyên?
11. **Giữ cache đúng release:** gắn với JDK build, app version và OS/CPU.
12. **Tài nguyên CI:** đủ disk/RAM/CPU cho training và assembly?
13. **Benchmark:** nhiều lần chạy, cold/warm, thống kê phân phối và đúng readiness milestone?
14. **Quan sát memory:** heap, RSS/PSS, cache file size và cgroup memory.
15. **Đảm bảo integrity:** cache artifact được tạo bởi pipeline tin cậy và được bảo vệ khỏi sửa đổi.
16. **Rollback:** app và cache cũ có được phát hành/khôi phục đồng bộ?
17. **Cập nhật JDK:** có bước tạo cache lại và integration test trên build mới?
18. **Vendor differences:** mọi tham số đều được đối chiếu với tài liệu của JDK sẽ triển khai?

### 17.2. Thứ tự thử nghiệm hợp lý

~~~text
Đo baseline -> kiểm tra default CDS -> đo AppCDS/AOT trên workload thật
              -> xác minh cache acceptance -> đánh giá chi phí CI/deployment
              -> quyết định có dùng production hay không.
~~~

Điểm dừng là **lợi ích đo được và sự đơn giản vận hành**, không phải số lượng VM flags được bật.

## 18. Câu hỏi tự kiểm tra

1. CDS và AppCDS giống và khác nhau ở điều gì?
2. Vì sao một default CDS archive có thể được nhiều JVM chia sẻ ở mức page memory?
3. Có thể dùng `-Xshare:off` để làm gì? Tại sao không nên dùng `-Xshare:on` làm mặc định production?
4. `-XX:ArchiveClassesAtExit=app.jsa` tạo artifact loại nào?
5. Vì sao `app.jsa` không thể đổi đuôi thành `app.aot` để dùng như AOT cache?
6. Các pha training, assembly, production trong HotSpot AOT cache có nhiệm vụ gì?
7. `-XX:AOTCacheOutput=app.aot` và `-XX:AOTCache=app.aot` được dùng ở bước nào?
8. Khi nào nên tách `record` và `create` thành hai JVM invocation riêng?
9. `AOTMode=auto` và `required` khác nhau ra sao khi cache bị từ chối?
10. Vì sao `AOTMode=on` không phải lựa chọn khuyến nghị cho script mới?
11. Kết quả chạy thành công với `AOTMode=auto` có chứng minh cache đã được nạp không?
12. Những khác biệt nào giữa classpath training và production có thể gây cache mismatch?
13. Vì sao archive tạo trên một JDK release hoặc OS có thể không dùng được ở release/OS khác?
14. `jcmd VM.cds` khác `jcmd AOT.end_recording` ở mục đích và đầu ra thế nào?
15. Vì sao một training run chỉ “hello world” có thể không đủ cho Spring/Quarkus service thực?
16. Việc bật JIT logging/class loading logging trong benchmark có thể làm sai kết quả ra sao?
17. Tại sao đồng hồ `System.nanoTime()` bắt đầu trong `main` không đo startup toàn bộ JVM?
18. Vì sao AOT cache của HotSpot không giống một GraalVM native executable?
19. Nếu Java runtime không phải HotSpot, cần làm gì trước khi sao chép `-XX:AOTCache`?
20. Khi triển khai hàng chục containers, nên đo RSS, PSS và archive footprint theo cách nào?
21. Nếu thêm Java instrumentation agent ở production, vì sao cache có thể mất hiệu lực?
22. Điều gì nên được đưa vào manifest/versioning của cache để rollback đúng?

## 19. Tài liệu tham khảo hiện hành

- [Java SE 27 — The java Command, Application Class Data Sharing và Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): các tùy chọn `-Xshare`, `-XX:SharedArchiveFile`, `-XX:ArchiveClassesAtExit`, `-XX:AOTCacheOutput`, `-XX:AOTCache`, `-XX:AOTConfiguration` và `-XX:AOTMode`.
- [Java SE 27 — Java Virtual Machine Guide: Class Data Sharing](https://docs.oracle.com/en/java/javase/27/vm/class-data-sharing.html): CDS, AppCDS, default archive và `-Xshare`.
- [Java SE 27 — jcmd Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): `VM.cds`, `AOT.end_recording` và các diagnostic commands.
- [Java SE 27 API — HotSpotAOTCacheMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.management/jdk/management/HotSpotAOTCacheMXBean.html): `endRecording()`, management interface trong module `jdk.management`.
- [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): nền tảng cho AOT cache của HotSpot.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): quy trình AOT cache thuận tiện và các option tương ứng.
- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): mở rộng thông tin warm-up qua method profile.
- [JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516): object caching của AOT với các garbage collectors, bao gồm ZGC.
- [Oracle — JDK 26 Release Notes, JEP 516](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận thay đổi hỗ trợ GC của AOT cache trước Java 27.
- [Inside Java — Run Into the New Year with Java’s AOT Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/): hướng dẫn workflow, tài nguyên training/assembly và lưu ý tính tương thích.

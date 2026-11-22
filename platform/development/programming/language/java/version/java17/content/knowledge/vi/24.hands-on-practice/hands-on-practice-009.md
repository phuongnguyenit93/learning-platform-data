# Đóng gói ứng dụng rồi quan sát bằng JFR

Một chương trình chạy ổn trên máy phát triển chưa chắc có hành vi giống khi được đóng gói và triển khai. Khi ứng dụng chạy từ JAR hoặc runtime image, nó sử dụng đúng classpath/module path, cấu hình JVM, thư viện và môi trường gần với cách vận hành thực tế hơn. Đây cũng là thời điểm phù hợp để thu thập dữ liệu Java Flight Recorder (JFR), từ đó quan sát CPU, allocation, garbage collection, thread, lock và I/O.

JFR là hệ thống ghi sự kiện runtime được tích hợp trong HotSpot JVM và có sẵn trong JDK 17. Có thể bắt đầu recording ngay khi khởi chạy ứng dụng hoặc gắn vào JVM đang chạy bằng `jcmd`. File `.jfr` sau đó được phân tích bằng JDK Mission Control (JMC) hoặc công cụ dòng lệnh `jfr`.

Bài thực hành đi qua toàn bộ vòng đời: chuẩn bị artifact, đóng gói JAR, chạy đúng artifact, bật JFR, thu thập recording, phân tích dữ liệu và rút ra giả thuyết tối ưu. Mục tiêu là hiểu quy trình quan sát ứng dụng sau khi đóng gói, không chỉ chạy một lệnh tạo file recording.

## 1. JFR quan sát điều gì?

Java Flight Recorder ghi các sự kiện có timestamp trong JVM và ứng dụng. Tùy cấu hình, recording có thể chứa:

- **CPU và thực thi:** mẫu stack của thread đang chạy, hoạt động compiler và thời gian thực thi.
- **Memory:** heap usage, allocation sample, thông tin object và garbage collection.
- **Threads và locks:** thread state, monitor contention, thread park và thời gian chờ.
- **I/O:** file read/write, socket read/write và thời gian chờ I/O.
- **Runtime:** class loading, exception, safepoint, JVM flags và thông tin môi trường.

JFR đặc biệt hữu ích khi cần tìm nguyên nhân của latency, CPU cao, allocation nhiều, GC pause hoặc lock contention. Recording giữ lại bối cảnh xảy ra sự kiện, giúp phân tích sau khi vấn đề đã kết thúc.

JFR có overhead thấp trong nhiều workload và được thiết kế để dùng trong production, nhưng overhead không bằng không. Mức dữ liệu và chi phí phụ thuộc template, event settings, stack trace, thời gian ghi và workload. Cần chọn cấu hình theo mục tiêu quan sát.

### 1.1. JFR, JMC và jfr command

| Thành phần | Vai trò |
| --- | --- |
| JFR trong JVM | Ghi sự kiện runtime và lưu recording |
| `jcmd` | Bắt đầu, kiểm tra, dump và dừng recording trên JVM đang chạy |
| `jfr` | Đọc, tóm tắt, lọc và xuất sự kiện từ file `.jfr` |
| JDK Mission Control (JMC) | Giao diện đồ họa để xem biểu đồ, event, stack trace và kết quả phân tích |

`jfr` nằm trong thư mục `bin` của JDK. JMC là công cụ riêng, không nằm trong cài đặt JDK thông thường; có thể cài riêng để phân tích recording.

## 2. Chuẩn bị ứng dụng trước khi đóng gói

Để recording có ý nghĩa, hãy xác định ứng dụng sẽ được đóng gói và chạy như thế nào:

1. Chọn JDK 17 làm toolchain build và runtime mục tiêu.
2. Xác định entry point của ứng dụng.
3. Xác định thư viện phụ thuộc và tài nguyên cần có trong artifact.
4. Chọn cách chạy: executable JAR, classpath, module path hoặc custom runtime image.
5. Chuẩn bị một workload có thể tái hiện để recording có dữ liệu cần phân tích.

JFR quan sát JVM đang chạy ứng dụng. Nếu chạy class trực tiếp trên IDE, recording có thể phản ánh classpath, agent và tham số của IDE thay vì artifact được triển khai. Vì vậy, hãy chạy chính artifact đã đóng gói trong bài thực hành.

### 2.1. Ví dụ cấu trúc dự án

Một dự án Java đơn giản có thể có cấu trúc:

~~~text
orders-app/
├── src/
│   └── com/example/orders/
│       └── OrdersApp.java
├── build/
│   └── classes/
└── recordings/
~~~

`build/classes` chứa bytecode đã biên dịch; `recordings` là thư mục riêng để lưu file JFR. Trong dự án Maven hoặc Gradle, dùng JAR hoặc distribution do build tool tạo ra. Các lệnh `jar` ở phần sau minh họa cách đóng gói cơ bản, không thay thế quy trình dependency management của build tool.

### 2.2. Mã ứng dụng dùng để quan sát

Ví dụ sau mô phỏng một service nhận công việc, tạo object, tính toán và chờ ngắn giữa các lần xử lý. Nó tạo đủ hoạt động để quan sát CPU sampling, allocation, thread và runtime events:

~~~java
package com.example.orders;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public final class OrdersApp {
    private static final AtomicLong completed = new AtomicLong();
    private static volatile long checksum;

    private OrdersApp() {
    }

    public static void main(String[] args) throws InterruptedException {
        int workers = Math.max(2,
                Runtime.getRuntime().availableProcessors() / 2);
        ExecutorService executor = Executors.newFixedThreadPool(workers);

        for (int i = 0; i < workers; i++) {
            executor.submit(OrdersApp::processOrders);
        }

        long end = System.nanoTime() + TimeUnit.MINUTES.toNanos(4);
        while (System.nanoTime() < end) {
            Thread.sleep(1000);
            System.out.printf("completed=%d checksum=%d%n",
                    completed.get(), checksum);
        }

        executor.shutdown();
        if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
            executor.shutdownNow();
        }
    }

    private static void processOrders() {
        while (!Thread.currentThread().isInterrupted()) {
            List<byte[]> payloads = new ArrayList<>();
            long local = 0;

            for (int i = 0; i < 40; i++) {
                payloads.add(new byte[16 * 1024]);
                local += calculate(i);
            }

            checksum = checksum ^ local;
            completed.incrementAndGet();

            try {
                Thread.sleep(10);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    private static long calculate(int seed) {
        long value = seed + 1;
        for (int i = 0; i < 20_000; i++) {
            value = (value * 31 + i) ^ (value >>> 3);
        }
        return value;
    }
}
~~~

Đây là workload minh họa, không phải benchmark. Số worker phụ thuộc số processor mà JVM nhìn thấy; kết quả và lượng dữ liệu sẽ thay đổi theo máy. Khi thực hành, giữ workload và cấu hình JVM giống nhau giữa các lần đo để so sánh có ý nghĩa.

## 3. Biên dịch và đóng gói thành executable JAR

JAR là định dạng archive chứa class và resource. Một executable JAR có manifest với thuộc tính `Main-Class` để launcher biết class bắt đầu.

Tạo thư mục output:

~~~bash
mkdir -p build/classes
mkdir -p recordings
~~~

Biên dịch bằng JDK 17:

~~~bash
javac --release 17 -d build/classes src/com/example/orders/OrdersApp.java
~~~

Tạo executable JAR:

~~~bash
jar --create \
    --file build/orders-app.jar \
    --main-class com.example.orders.OrdersApp \
    -C build/classes .
~~~

`--main-class` ghi entry point vào manifest. Có thể xem nội dung archive:

~~~bash
jar --list --file build/orders-app.jar
~~~

Với JAR modular, có thể kiểm tra module descriptor bằng công cụ phù hợp. Với JAR không modular, không cần bước này để chạy executable JAR.

### 3.1. Chạy JAR đã đóng gói

~~~bash
java -jar build/orders-app.jar
~~~

Nếu ứng dụng khởi động và in số lượng công việc hoàn tất, artifact có entry point đúng.

### 3.2. JAR thường không tự chứa dependency

Một JAR tạo bằng `jar` chỉ đóng gói những class/resource được chỉ định. Nó không tự động đưa mọi dependency bên ngoài vào archive.

Nếu ứng dụng dùng thư viện riêng, có thể:

- Dùng executable/fat JAR do build tool hoặc plugin đóng gói tạo ra.
- Phân phối thư mục `lib` và chạy qua classpath.
- Dùng manifest `Class-Path` theo cấu trúc phân phối.
- Dùng module path nếu ứng dụng modular.

Ví dụ chạy ứng dụng cùng thư viện trong thư mục `lib`:

~~~bash
java -cp "build/orders-app.jar:lib/*" com.example.orders.OrdersApp
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
java -cp "build/orders-app.jar;lib/*" com.example.orders.OrdersApp
~~~

Khi dùng `-jar`, launcher bỏ qua classpath bên ngoài được chỉ định bằng `-cp`/`-classpath`; nếu dùng executable JAR có dependency, hãy đóng gói dependency đúng cách hoặc khai báo `Class-Path` trong manifest.

## 4. Chạy ứng dụng đã đóng gói cùng JFR

JFR có thể được bật ngay khi JVM khởi chạy bằng tùy chọn `-XX:StartFlightRecording`. Tùy chọn JVM phải đứng trước `-jar`, tên class hoặc module entry point.

Ví dụ ghi profile trong ba phút:

~~~bash
java -XX:StartFlightRecording=name=orders-profile,settings=profile,duration=3m,filename=recordings/orders-profile.jfr -jar build/orders-app.jar
~~~

Các tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `name=orders-profile` | Tên recording để quản lý khi cần |
| `settings=profile` | Chọn template thu thập nhiều sự kiện hơn |
| `duration=3m` | Ghi trong ba phút rồi kết thúc recording |
| `filename=...` | Đường dẫn file JFR được ghi khi recording dừng |

Tạo thư mục đích trước khi chạy và bảo đảm user chạy JVM có quyền ghi. Khi thời lượng kết thúc, JFR ghi recording ra file đã chỉ định. Có thể thêm `dumponexit=true` nếu muốn lưu recording khi JVM shutdown trước khi hết thời lượng.

Ví dụ:

~~~bash
java -XX:StartFlightRecording=name=orders-profile,settings=profile,duration=3m,filename=recordings/orders-profile.jfr,dumponexit=true -jar build/orders-app.jar
~~~

`dumponexit` xử lý việc dump khi JVM shutdown bình thường. Không xem nó như bảo đảm file luôn được ghi sau mọi trường hợp mất điện, kill cưỡng bức hoặc crash nghiêm trọng.

### 4.1. Ghi recording khi ứng dụng đang chạy

Không cần restart ứng dụng để bắt đầu một recording ngắn. Dùng `jcmd` để attach vào JVM:

~~~bash
jcmd -l
~~~

Xác định PID của `OrdersApp`, sau đó:

~~~bash
jcmd 24680 JFR.start name=orders-profile settings=profile duration=3m filename=recordings/orders-profile.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd 24680 JFR.check
~~~

Nếu muốn lấy snapshot ngay mà recording vẫn tiếp tục:

~~~bash
jcmd 24680 JFR.dump name=orders-profile filename=recordings/orders-snapshot.jfr
~~~

`JFR.dump` xuất dữ liệu hiện có ra file và recording vẫn chạy. Khi muốn kết thúc recording, dùng:

~~~bash
jcmd 24680 JFR.stop name=orders-profile filename=recordings/orders-profile-final.jfr
~~~

Nếu gọi `JFR.stop` mà không chỉ định file output, dữ liệu recording có thể bị loại bỏ. Hãy kiểm tra `help JFR.start`, `help JFR.dump` và `help JFR.stop` trên JVM đích để biết đầy đủ tham số và hành vi.

`jcmd` phải chạy trên cùng máy với JVM và dưới effective user/group phù hợp với tiến trình đích. Trong container, hãy chạy công cụ trong môi trường có thể truy cập đúng PID namespace và attach endpoint.

## 5. Chọn cấu hình recording: default hay profile?

JDK 17 đi kèm hai template:

| Template | Mục tiêu | Khi nên dùng |
| --- | --- | --- |
| `default.jfc` | Thu thập thông tin hữu ích với overhead thấp | Ghi liên tục, quan sát dài hạn hoặc production |
| `profile.jfc` | Thu thập nhiều event và chi tiết hơn | Profiling ngắn hạn, điều tra một triệu chứng cụ thể |

Các template nằm trong thư mục `JAVA_HOME/lib/jfr`. Nếu không chỉ định `settings`, JFR dùng `default.jfc`.

`default` phù hợp với continuous recording và thường có overhead rất thấp. Tuy nhiên, nó không bật mọi event, ví dụ dữ liệu heap statistics hoặc allocation profiling có thể không đầy đủ. `profile` thu thập thêm thông tin, nhưng overhead và kích thước file có thể cao hơn.

Một cách làm thực tế:

1. Duy trì recording `default` nếu cần giữ bối cảnh runtime dài hạn.
2. Khi có triệu chứng, bắt đầu recording `profile` trong khoảng thời gian ngắn.
3. So sánh recording với metrics và log của cùng khoảng thời gian.
4. Chỉ bật event tùy chỉnh khi đã xác định dữ liệu mặc định chưa đủ.

Không nên chạy nhiều recording `profile` dài hạn chỉ để thu thập thêm dữ liệu. Chọn event theo câu hỏi điều tra giúp giảm overhead và làm dữ liệu dễ phân tích hơn.

## 6. Continuous recording và giới hạn dung lượng

Với ứng dụng chạy lâu dài, có thể bật continuous recording từ lúc khởi chạy. JFR giữ lại dữ liệu gần nhất theo giới hạn tuổi hoặc dung lượng, để khi xảy ra sự cố có thể dump phần lịch sử vừa qua.

Ví dụ:

~~~bash
java -XX:StartFlightRecording=name=orders-continuous,settings=default,disk=true,maxage=6h,maxsize=512m -XX:FlightRecorderOptions=repository=/var/tmp/orders-jfr -jar build/orders-app.jar
~~~

Trong cấu hình này:

- `settings=default` chọn template nhẹ cho recording liên tục.
- `disk=true` yêu cầu ghi dữ liệu tạm vào disk repository.
- `maxage=6h` giới hạn dữ liệu được giữ theo tuổi.
- `maxsize=512m` giới hạn dung lượng dữ liệu trên đĩa.
- `repository=...` chọn thư mục lưu các chunk tạm.

Trong Java 17, tham số `disk` của `StartFlightRecording` mặc định là `false`; nếu muốn dùng disk repository cho continuous recording, hãy bật `disk=true` rõ ràng. `maxage` và `maxsize` chỉ có hiệu lực khi disk recording được bật.

Các chunk trong repository là dữ liệu tạm. Khi cần giữ bằng chứng sự cố, dump recording ra file `.jfr` ở vị trí lưu trữ riêng:

~~~bash
jcmd 24680 JFR.dump name=orders-continuous filename=/var/tmp/orders-incident.jfr
~~~

Recording vẫn tiếp tục sau khi dump. Có thể dump lần nữa khi cần một snapshot mới. Hãy quản lý quyền truy cập, dung lượng và thời gian lưu trữ của repository cũng như file recording đã xuất.

### 6.1. Continuous recording không phải log vô hạn

JFR continuous recording giữ lại một cửa sổ dữ liệu gần nhất. Khi vượt `maxage` hoặc `maxsize`, dữ liệu cũ được loại bỏ theo giới hạn recording. Nếu sự cố xảy ra nhưng không dump trước khi dữ liệu cũ bị xoay vòng, bối cảnh có thể không còn.

Vì vậy, production nên có quy trình dump khi phát hiện sự cố hoặc trigger tự động theo ngưỡng phù hợp. Không đặt giới hạn vô hạn nếu thư mục repository có dung lượng hữu hạn.

## 7. Phân tích file bằng lệnh jfr

Sau khi có file `.jfr`, có thể bắt đầu kiểm tra mà không cần giao diện đồ họa.

### 7.1. Xem summary

~~~bash
jfr summary recordings/orders-profile.jfr
~~~

Summary hiển thị metadata recording, khoảng thời gian, số lượng event theo loại và kích thước. Đây là bước đầu tiên để xác nhận file có dữ liệu và xem loại event nào chiếm nhiều dung lượng.

### 7.2. In event cần quan tâm

Ví dụ chỉ in các event CPU sample và garbage collection:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection recordings/orders-profile.jfr
~~~

Có thể lọc theo category:

~~~bash
jfr print --categories GC recordings/orders-profile.jfr
~~~

Xuất dữ liệu JSON khi cần xử lý bằng script:

~~~bash
jfr print --json --events jdk.ExecutionSample recordings/orders-profile.jfr
~~~

Không nên in toàn bộ event của recording lớn ra terminal nếu chỉ cần một nhóm dữ liệu. Dùng `--events`, `--categories` và `--stack-depth` để giới hạn output.

### 7.3. Xem metadata event

~~~bash
jfr metadata recordings/orders-profile.jfr
~~~

Metadata cho biết event type, category và cấu trúc field có trong recording. Nó hữu ích khi cần biết event nào đã được ghi và tên field nào có thể dùng trong bộ phân tích.

### 7.4. Kiểm tra công cụ

~~~bash
jfr --version
jfr --help
jfr --help print
~~~

Các subcommand và tùy chọn phụ thuộc phiên bản JDK đi kèm công cụ. Với recording Java 17, ưu tiên dùng `jfr` từ JDK 17 hoặc phiên bản tương thích, sau đó kiểm tra kết quả bằng JMC khi cần trực quan hóa.

## 8. Phân tích recording bằng JDK Mission Control

JMC cung cấp giao diện để xem dữ liệu JFR theo nhóm. Mở file `.jfr` bằng JMC, sau đó xem trang Automated Analysis Results và các khu vực chi tiết.

Các khu vực thường hữu ích:

| Khu vực | Câu hỏi cần trả lời |
| --- | --- |
| Overview / Automated Analysis | Có dấu hiệu bất thường nào nổi bật trong recording? |
| Code | Package, class hoặc method nào tiêu thụ CPU nhiều? |
| Memory | Heap biến động ra sao, allocation đến từ đâu, GC có thường xuyên không? |
| Garbage Collections | GC nào xảy ra, pause kéo dài bao lâu, heap trước/sau GC thế nào? |
| Threads | Thread nào hoạt động nhiều, thread nào chờ hoặc bị block? |
| Locks | Có monitor contention hoặc lock wait kéo dài không? |
| I/O | Thời gian đọc/ghi file hoặc socket có cao không? |
| Environment | CPU, memory, OS và process khác ảnh hưởng thế nào? |

Automated Analysis Results là điểm bắt đầu để tìm khu vực cần xem sâu hơn. Các cảnh báo màu sắc là gợi ý điều tra, không phải kết luận tự động về nguyên nhân.

### 8.1. Tìm CPU hot spot

Trong Code hoặc Threads view:

1. Xem CPU usage và execution samples trong khoảng thời gian có latency.
2. Xếp hạng stack trace hoặc method xuất hiện thường xuyên.
3. Xác định phần code thuộc ứng dụng hay thư viện.
4. Mở stack trace để tìm đường gọi từ entry point.
5. Đối chiếu với endpoint, request type hoặc workload đang chạy.

Execution sample là dữ liệu lấy mẫu, không phải phép đo chính xác thời gian cho mọi method. Method xuất hiện nhiều trong sample là nơi đáng kiểm tra, nhưng vẫn cần xác nhận bằng workload và code.

### 8.2. Tìm allocation và áp lực GC

Trong Memory và Garbage Collections view:

- Quan sát heap usage theo thời gian.
- Xem số lượng và thời gian các lần GC.
- Xem allocation sample hoặc allocation by class nếu template có ghi.
- Tìm class hoặc call site tạo nhiều object.
- Phân biệt allocation tạm thời với object sống lâu và được giữ lại.

Heap tăng rồi giảm sau GC là hành vi thường thấy. Một đường heap tăng dần qua nhiều chu kỳ GC có thể gợi ý object bị giữ lại, nhưng một recording ngắn chưa đủ kết luận memory leak.

Nếu allocation profile không xuất hiện trong recording `default`, hãy cân nhắc recording ngắn bằng `profile` hoặc cấu hình event cụ thể. Đừng kết luận không có allocation chỉ vì template đang dùng không thu thập event đó.

### 8.3. Tìm lock contention

Trong Locks và Threads view:

1. Tìm event monitor enter/wait có duration dài.
2. Xem thread đang chờ và stack trace của nó.
3. Tìm thread giữ lock hoặc vùng code tạo contention.
4. Đối chiếu với số worker, throughput và latency của request.

Một thread `WAITING` hoặc `BLOCKED` không tự chứng minh deadlock. Hãy xem thời lượng, stack trace, quan hệ lock và trạng thái các thread liên quan.

### 8.4. Tìm I/O chậm

Trong I/O view, xem file read/write và socket read/write event. Nếu request dành nhiều thời gian chờ socket, bottleneck có thể nằm ở network hoặc service phụ thuộc. Nếu file I/O kéo dài, kiểm tra storage, kích thước dữ liệu và cách ứng dụng đọc/ghi.

JFR chỉ ghi các event được bật và thỏa threshold. Nếu không thấy event I/O, không thể kết luận ứng dụng không có I/O; kiểm tra event settings và ngưỡng ghi trước.

## 9. Thiết kế một phiên thực hành có thể lặp lại

Để so sánh các lần chạy, cần giữ điều kiện thử nghiệm ổn định.

### 9.1. Chuẩn bị

- Build một artifact duy nhất và ghi lại checksum/version.
- Chạy cùng JDK 17 và cùng JVM flags.
- Dùng cùng input/workload hoặc cùng thời gian chạy.
- Tạo thư mục output riêng cho từng lần recording.
- Ghi lại thời điểm bắt đầu, kết thúc và số lượng request/work item.

### 9.2. Chạy baseline

Chạy ứng dụng đã đóng gói mà chưa bật JFR:

~~~bash
java -jar build/orders-app.jar
~~~

Ghi nhận throughput, latency, CPU và memory từ hệ thống đo lường đang có. Đây là baseline để so sánh.

### 9.3. Chạy với JFR profile

~~~bash
java -XX:StartFlightRecording=name=orders-profile,settings=profile,duration=3m,filename=recordings/orders-profile.jfr -jar build/orders-app.jar
~~~

Giữ workload tương tự baseline. Sau khi recording kết thúc, chạy:

~~~bash
jfr summary recordings/orders-profile.jfr
~~~

Mở file bằng JMC và tìm CPU, allocation, GC, thread, locks hoặc I/O tùy triệu chứng.

### 9.4. Ghi nhận giả thuyết và đo lại

Ví dụ phát hiện nhiều allocation từ một phương thức xử lý request:

1. Ghi tên method và stack trace từ JFR.
2. Đọc code để xác định object nào được tạo lặp lại.
3. Đề xuất thay đổi cụ thể, ví dụ tái sử dụng buffer an toàn hoặc giảm chuyển đổi dữ liệu không cần thiết.
4. Build artifact mới.
5. Chạy cùng workload và cùng cấu hình JFR.
6. So sánh throughput, latency, allocation và GC giữa hai lần.

Không tối ưu chỉ dựa trên một biểu đồ. Một thay đổi có thể giảm allocation nhưng tăng lock contention hoặc CPU; hãy xem toàn bộ triệu chứng liên quan.

## 10. Chọn event settings theo câu hỏi điều tra

JFR dùng event settings để xác định event nào được bật, threshold nào được áp dụng và stack trace có được ghi hay không.

Nếu template mặc định không ghi đủ dữ liệu, có thể tạo một file `.jfc` tùy chỉnh:

1. Mở JMC Template Manager.
2. Sao chép template `default` hoặc `profile`.
3. Chỉ bật event cần thiết.
4. Điều chỉnh threshold hoặc stack trace nếu có lý do.
5. Lưu thành file mới và dùng trong lần recording tiếp theo.

Không chỉnh sửa trực tiếp các file template mặc định trong `JAVA_HOME/lib/jfr`. Hãy tạo bản sao riêng để có thể quản lý version và rollback.

Ví dụ dùng file cấu hình tùy chỉnh:

~~~bash
java -XX:StartFlightRecording=settings=config/orders-debug.jfc,filename=recordings/orders-debug.jfr,duration=2m -jar build/orders-app.jar
~~~

Đường dẫn `settings` có thể là tên template chuẩn hoặc đường dẫn file `.jfc`. Khi file không nằm trong thư mục template của JDK, chỉ định đường dẫn phù hợp.

### 10.1. Threshold và event không xuất hiện

Nhiều event dạng duration chỉ được ghi khi thời gian vượt threshold. Ví dụ, nếu threshold của monitor wait là 20 ms, những lần chờ ngắn hơn có thể không xuất hiện. Khi cần điều tra các lần chờ ngắn, có thể hạ threshold trong custom `.jfc`, nhưng dữ liệu và overhead sẽ tăng.

Không hạ mọi threshold xuống mức thấp nhất. Hãy bắt đầu từ event cụ thể liên quan tới giả thuyết, ghi trong khoảng thời gian ngắn rồi đánh giá chất lượng dữ liệu.

## 11. Ghi recording có chủ đích cho memory leak

JFR có event và cơ chế hỗ trợ điều tra object sống lâu. Tuy nhiên, thu thập đường dẫn tới GC roots có thể tốn thời gian và làm JVM pause.

Khi nghi ngờ memory leak:

1. Bắt đầu bằng recording có `profile` để thu thập allocation context phù hợp.
2. Quan sát xu hướng heap và object sống lâu qua thời gian.
3. Nếu cần tìm GC root, dùng tùy chọn `path-to-gc-roots` trong recording/dump theo cú pháp JDK 17.
4. Chỉ bật tùy chọn này khi đã có giả thuyết leak và chấp nhận chi phí bổ sung.
5. Kết hợp kết quả với heap dump nếu cần phân tích retained size và reference chain chi tiết.

Ví dụ dump một recording đang chạy và yêu cầu lưu path tới GC roots:

~~~bash
jcmd 24680 JFR.dump name=orders-continuous filename=recordings/orders-leak.jfr path-to-gc-roots=true
~~~

Đường dẫn GC root giúp tìm object nào giữ reference tới object nghi ngờ. Không bật nó thường trực chỉ để thu thập thêm dữ liệu; Oracle khuyến nghị chỉ dùng khi đang nghi ngờ memory leak vì thao tác này có thể làm ứng dụng pause.

## 12. Đóng gói ứng dụng modular hoặc custom runtime image

Nếu ứng dụng có `module-info.java`, có thể đóng gói modular JAR và chạy qua module path. Ví dụ:

~~~bash
jar --create --file build/orders-app.jar --main-class com.example.orders.OrdersApp -C build/classes .
~~~

Chạy modular application:

~~~bash
java -XX:StartFlightRecording=name=orders,settings=profile,duration=3m,filename=recordings/orders.jfr --module-path build/orders-app.jar --module com.example.orders/com.example.orders.OrdersApp
~~~

Tên module phải khớp với khai báo trong `module-info.java`; tên main class phải là class có `public static void main(String[] args)`.

Nếu dùng `jlink` tạo runtime image tối giản, hãy kiểm tra các module cần cho ứng dụng và chẩn đoán. Nếu runtime image phải chạy JFR API hoặc JFR recording, bảo đảm module `jdk.jfr` có mặt trong image. Công cụ phân tích `jfr` và `jcmd` có thể được cung cấp từ một JDK đầy đủ ở môi trường vận hành.

Ví dụ ý tưởng tạo image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:build/modules" --add-modules com.example.orders,jdk.jfr --output build/orders-runtime
~~~

Đường dẫn module path và tập module cần thiết phụ thuộc ứng dụng. Trên Windows, dấu phân cách module path khác Linux/macOS. Hãy dùng `jdeps` hoặc `jlink --suggest-providers` khi xác định module phụ thuộc và kiểm thử image được tạo trên môi trường triển khai thực tế.

## 13. Quyền truy cập và bảo vệ file recording

Recording có thể chứa thông tin nhạy cảm về môi trường và hành vi ứng dụng:

- Tên class, method, package và stack trace.
- Đường dẫn file, socket address hoặc thông tin môi trường.
- System properties và một số metadata runtime.
- Thông tin allocation hoặc object event tùy cấu hình.
- Dữ liệu do ứng dụng ghi vào custom event.

Hãy:

- Ghi file vào thư mục có quyền truy cập giới hạn.
- Không đưa file `.jfr` lên nơi công khai.
- Redact hoặc loại bỏ dữ liệu nhạy cảm trước khi chia sẻ.
- Đặt thời hạn lưu giữ và xóa file sau khi điều tra.
- Kiểm tra custom event để tránh ghi password, token hoặc payload riêng tư.

`jcmd` cần chạy trong môi trường có quyền attach phù hợp. Không mở cơ chế attach hoặc JMX rộng ra mạng chỉ để thu thập recording thuận tiện hơn.

## 14. Lỗi thường gặp khi đóng gói rồi quan sát bằng JFR

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `no main manifest attribute` | JAR không có `Main-Class` | Tạo executable JAR hoặc chạy class/module entry point trực tiếp |
| `ClassNotFoundException` khi chạy JAR | Dependency không nằm trong JAR hoặc classpath | Đóng gói dependency hoặc chạy với classpath/module path phù hợp |
| JFR không tạo file | Sai đường dẫn, thiếu quyền ghi hoặc recording chưa dừng | Kiểm tra `filename`, thư mục output, `JFR.check` và `JFR.stop` |
| File recording rất nhỏ hoặc thiếu event | Template không bật event cần thiết hoặc threshold quá cao | Xem `jfr summary`, dùng `profile` hoặc custom JFC |
| `jcmd` không tìm thấy PID | Khác user/namespace hoặc attach không khả dụng | Kiểm tra process trong đúng host/container và quyền attach |
| `JFR.dump` không dừng recording | Đây là hành vi đúng; dump chỉ tạo snapshot | Dùng `JFR.stop` khi muốn kết thúc recording |
| Recording liên tục chiếm nhiều đĩa | Thiếu `maxage`, `maxsize` hoặc không dump/rotate theo kế hoạch | Bật `disk=true`, đặt giới hạn và quản lý repository |
| Không thấy allocation trong default | Template default ưu tiên overhead thấp | Dùng profile hoặc bật event allocation cần thiết |
| File JFR không mở bằng JMC | File chưa hoàn chỉnh, lỗi truyền file hoặc JMC không tương thích | Kiểm tra `jfr summary`, sao chép file hoàn chỉnh và dùng JMC tương thích |
| Kết quả khác giữa IDE và JAR | Classpath, flags, agent hoặc JDK khác nhau | Chạy đúng artifact với cùng JDK và tham số đã ghi nhận |
| Recording gây overhead không mong muốn | Dùng profile lâu, nhiều event hoặc threshold quá thấp | Rút ngắn thời gian và giảm event settings |

## 15. Quy trình vận hành đề xuất

Một quy trình có thể dùng cho mỗi bản build:

1. Build và đóng gói artifact bằng JDK 17.
2. Ghi lại version, checksum và cấu hình runtime.
3. Chạy artifact bằng `java -jar`, classpath hoặc module path giống môi trường triển khai.
4. Bật recording `default` nếu cần quan sát dài hạn hoặc `profile` cho một phiên điều tra ngắn.
5. Lưu recording theo tên có ứng dụng, version và thời điểm.
6. Chạy `jfr summary` để xác nhận file và event.
7. Mở bằng JMC, xem Automated Analysis, Code, Memory, Threads, Locks, I/O và GC.
8. Ghi giả thuyết, sửa code hoặc cấu hình.
9. Build artifact mới và lặp lại cùng workload.
10. So sánh dữ liệu trước/sau và lưu kết luận có thể kiểm chứng.

Điều quan trọng là mỗi recording phải gắn với đúng artifact, JDK, JVM flags, workload và thời điểm. Nếu thiếu các thông tin này, so sánh hai file có thể dẫn tới kết luận sai.

## 16. Checklist cho một lần thực hành

- [ ] Đã build ứng dụng bằng JDK 17.
- [ ] Đã tạo artifact executable hoặc distribution có đủ dependency.
- [ ] Đã xác nhận entry point và cách chạy artifact.
- [ ] Đã chuẩn bị workload có thể tái hiện.
- [ ] Đã tạo thư mục recording và kiểm tra quyền ghi.
- [ ] Đã chọn `default` hoặc `profile` theo mục tiêu.
- [ ] Đã bật recording lúc startup hoặc bằng `jcmd`.
- [ ] Đã kiểm tra recording bằng `JFR.check` hoặc `jfr summary`.
- [ ] Đã phân tích CPU, allocation, GC, threads, locks hoặc I/O theo triệu chứng.
- [ ] Đã lưu giả thuyết và kết quả đo trước/sau.
- [ ] Đã bảo vệ và dọn dẹp file recording theo chính sách lưu trữ.

## 17. Câu hỏi tự kiểm tra

**1. JFR dùng để quan sát những gì?**  
JFR ghi sự kiện runtime như CPU sample, allocation, GC, thread, lock, I/O, class loading và thông tin JVM.

**2. JFR có sẵn trong JDK 17 không?**  
Có. JFR được tích hợp trong HotSpot JVM và có thể điều khiển qua startup option hoặc diagnostic command.

**3. Một JAR executable cần thông tin nào để chạy bằng `java -jar`?**  
Manifest cần thuộc tính `Main-Class` trỏ tới class có phương thức main hợp lệ.

**4. Vì sao phải chạy artifact đã đóng gói trước khi ghi JFR?**  
Để recording phản ánh đúng classpath/module path, dependency, JVM flags và môi trường triển khai.

**5. Khác biệt giữa `default` và `profile` là gì?**  
`default` thu thập dữ liệu với overhead thấp và phù hợp recording liên tục; `profile` thu thập nhiều event hơn, phù hợp điều tra ngắn hạn.

**6. Bắt đầu JFR ngay khi khởi chạy ứng dụng bằng tùy chọn nào?**  
`-XX:StartFlightRecording`.

**7. Bắt đầu recording trên JVM đang chạy bằng công cụ nào?**  
`jcmd <pid> JFR.start`.

**8. `JFR.dump` có dừng recording không?**  
Không. Nó xuất dữ liệu hiện có ra file và recording tiếp tục.

**9. `JFR.stop` có thể ghi file output không?**  
Có. Truyền `filename` để lưu dữ liệu khi recording dừng; nếu không chỉ định file, dữ liệu có thể bị loại bỏ.

**10. `disk=true`, `maxage` và `maxsize` dùng cho trường hợp nào?**  
Chúng quản lý dữ liệu của continuous recording trên disk repository; `maxage` và `maxsize` chỉ có hiệu lực khi disk recording được bật.

**11. Dùng lệnh nào để xem summary của file JFR?**  
`jfr summary recording.jfr`.

**12. JMC giúp gì khi phân tích JFR?**  
JMC hiển thị biểu đồ và bảng về code, memory, GC, threads, locks, I/O và automated analysis.

**13. Vì sao không thấy allocation event trong một recording?**  
Template có thể không bật allocation event hoặc threshold không phù hợp; cần kiểm tra settings và cân nhắc profile/custom JFC.

**14. Có thể bật `path-to-gc-roots` cho mọi recording không?**  
Không nên. Thu thập GC root có thể tốn thời gian và gây pause; chỉ bật khi điều tra memory leak.

**15. Vì sao cần ghi lại artifact version và JVM flags cùng recording?**  
Để có thể tái hiện và so sánh kết quả giữa các lần chạy.

## Tài liệu tham khảo chính thức

- [Java SE 17 — The jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): tạo executable JAR, modular JAR và manifest main class.
- [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): manifest, Main-Class, modular JAR và classpath.
- [Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cú pháp chạy JAR/module và tùy chọn `-XX:StartFlightRecording`.
- [Java SE 17 — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop` và tham số.
- [Java SE 17 — The jfr Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `jfr summary`, `jfr print`, `jfr metadata`, assemble và disassemble.
- [Java SE 17 — Diagnostic Tools: Flight Recorder](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): tạo recording lúc startup, bằng jcmd hoặc JMC và phân tích recording.
- [Java SE 17 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html): `default.jfc`, `profile.jfc` và custom event settings.

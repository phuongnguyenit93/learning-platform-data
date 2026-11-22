# Mô hình virtual thread, platform thread và carrier thread

Java 21 cung cấp virtual thread như một loại `java.lang.Thread` nhẹ do Java runtime quản lý. Để hiểu cách chúng hoạt động, cần phân biệt ba khái niệm: **virtual thread** là luồng logic của ứng dụng, **platform thread** là luồng Java gắn với một OS thread, còn **carrier thread** là platform thread đang thực thi một virtual thread.

Virtual thread giúp mô hình lập trình thread-per-task mở rộng tốt hơn cho ứng dụng có nhiều tác vụ chờ I/O. JVM quản lý việc lập lịch virtual thread lên một nhóm carrier platform thread; một virtual thread không bị gắn cố định với một carrier trong suốt vòng đời.

## 1. Ba loại thread trong mô hình Java 21

| Khái niệm | Vai trò | Quan hệ với OS thread |
|---|---|---|
| Virtual thread | Đại diện cho một tác vụ Java; được JVM lập lịch và tạm dừng/tiếp tục | Không sở hữu một OS thread riêng trong suốt vòng đời |
| Platform thread | Luồng Java truyền thống, phù hợp với tác vụ cần thực thi trực tiếp trên OS thread | Gắn với một OS thread |
| Carrier thread | Platform thread do JVM scheduler dùng để chạy một virtual thread tại một thời điểm | Chính là một platform thread đang làm carrier |

Carrier không phải một loại `Thread` riêng mà ứng dụng cần tạo. Nó là vai trò của một platform thread trong lúc thực thi virtual thread. Khi virtual thread được unmount, carrier có thể được dùng để chạy virtual thread khác.

## 2. Quan hệ giữa virtual thread và carrier thread

Virtual thread được JVM scheduler lập lịch và mount lên một carrier platform thread để chạy. Tại một thời điểm, một virtual thread chỉ chạy trên một carrier. Khi virtual thread thực hiện thao tác blocking mà JVM có thể xử lý bằng cách unmount, virtual thread được tạm dừng và carrier được giải phóng để chạy tác vụ khác.

```text
Các virtual thread của ứng dụng
  V1       V2       V3       V4       ...
   \        |        /        |
    \       |       /         |
     JVM virtual-thread scheduler
             |
     Carrier platform threads
       C1          C2          C3
        |           |           |
     OS thread   OS thread   OS thread
```

Một virtual thread có thể được mount lên carrier này, sau đó unmount khi chờ I/O, rồi được mount lại trên một carrier khác khi có thể tiếp tục. Vì vậy, không nên giả định virtual thread luôn chạy trên cùng một platform thread.

JVM không cần tạo một OS thread mới cho mỗi virtual thread. Một số lượng carrier platform thread có thể phục vụ một số lượng virtual thread lớn hơn nhiều, đặc biệt khi các tác vụ thường xuyên chờ I/O.

## 3. Platform thread và virtual thread khác nhau thế nào?

Platform thread là lựa chọn truyền thống. Mỗi platform thread gắn với một OS thread, nên số lượng luồng đồng thời bị giới hạn đáng kể bởi tài nguyên hệ điều hành và chi phí stack/native resources của từng luồng.

Virtual thread là đối tượng `Thread` do JVM quản lý. Stack của virtual thread được quản lý theo cách cho phép runtime tạm dừng và tiếp tục luồng mà không cần giữ một OS thread riêng trong suốt thời gian chờ. Điều này làm cho việc tạo nhiều luồng cho nhiều tác vụ blocking trở nên khả thi hơn.

Ví dụ tạo và nhận diện hai loại thread bằng API Java 21:

```java
static void printThreadKind(String label) {
    Thread current = Thread.currentThread();
    System.out.printf(
            "%s: name=%s, virtual=%s%n",
            label, current.getName(), current.isVirtual());
}

static void compareThreadKinds() throws InterruptedException {
    Thread platform = Thread.ofPlatform()
            .name("platform-example")
            .start(() -> printThreadKind("platform"));

    Thread virtual = Thread.ofVirtual()
            .name("virtual-example")
            .start(() -> printThreadKind("virtual"));

    platform.join();
    virtual.join();
}
```

`Thread.isVirtual()` trả về `false` cho platform thread và `true` cho virtual thread. Trong code chạy bên trong virtual thread, `Thread.currentThread()` trả về chính virtual thread đó; ứng dụng không cần truy cập carrier để thao tác với luồng hiện tại.

## 4. Vì sao carrier được giải phóng khi virtual thread chờ?

Giả sử một request cần gọi dịch vụ HTTP và chờ phản hồi. Với platform thread, OS thread thường bị giữ trong thời gian chờ. Với virtual thread, các API blocking tương thích có thể khiến JVM unmount virtual thread khỏi carrier trong lúc chờ.

```text
Virtual thread V1 chạy trên carrier C1
          |
          | gọi HTTP và chờ phản hồi
          v
V1 unmount khỏi C1
          |
          +---- C1 được dùng để chạy V2
          |
          v
HTTP response đến
          |
          v
V1 được lập lịch lại và mount lên carrier khả dụng
```

Khi I/O hoàn tất, virtual thread được đánh thức và scheduler đưa nó trở lại thực thi. Nó có thể tiếp tục trên một carrier khác. Đây là cơ chế giúp nhiều tác vụ chờ I/O cùng tồn tại mà không cần giữ một OS thread cho mỗi tác vụ.

Không phải mọi lời gọi blocking đều chắc chắn giải phóng carrier. Khả năng unmount phụ thuộc loại thao tác và trạng thái thực thi; một số trường hợp có thể làm virtual thread bị pin vào carrier.

## 5. Scheduler và số lượng carrier

JVM có virtual-thread scheduler để phân phối các virtual thread có thể chạy lên carrier platform thread. Trong triển khai mặc định của Java 21, scheduler sử dụng cơ chế dựa trên `ForkJoinPool` và một nhóm worker platform thread.

Số lượng virtual thread có thể lớn hơn số lượng carrier vì phần lớn virtual thread có thể đang chờ. Tuy nhiên, số virtual thread thực sự chạy đồng thời vẫn phụ thuộc số carrier và số lõi CPU có sẵn. Virtual thread không làm tăng số lõi xử lý của máy.

Carrier là chi tiết triển khai do JVM quản lý. Ứng dụng thông thường không cần tự tạo, giữ reference hoặc điều phối carrier. Hãy tạo và quản lý tác vụ bằng API thread/executor; để JVM thực hiện việc mount, unmount và lập lịch.

## 6. Ví dụ thread-per-task với virtual thread

`Executors.newVirtualThreadPerTaskExecutor()` tạo một virtual thread mới cho mỗi tác vụ được gửi vào executor. Cách dùng này thể hiện mô hình thread-per-task:

```java
import java.util.concurrent.Executors;

public class VirtualThreadExample {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var profile = executor.submit(() -> loadProfile(42));
            var orders = executor.submit(() -> loadOrders(42));

            System.out.println(profile.get());
            System.out.println(orders.get());
        }
    }

    static String loadProfile(int userId) {
        // Thay bằng lời gọi I/O, ví dụ truy vấn dịch vụ hồ sơ.
        return "profile-" + userId;
    }

    static String loadOrders(int userId) {
        // Thay bằng lời gọi I/O, ví dụ truy vấn dịch vụ đơn hàng.
        return "orders-" + userId;
    }
}
```

Executor đóng khi thoát khỏi `try` và chờ các tác vụ đã gửi hoàn tất. `Future.get()` chờ kết quả; trong ứng dụng thực tế, các phương thức tải dữ liệu thường gọi database hoặc HTTP client blocking.

Không cần tạo pool để tái sử dụng virtual thread. Mô hình phù hợp là một virtual thread cho mỗi tác vụ. Nếu cần giới hạn số kết nối database, request đến dịch vụ ngoài hoặc mức tải đồng thời, hãy giới hạn tài nguyên đó bằng connection pool, semaphore hoặc cơ chế backpressure phù hợp.

## 7. Virtual thread không phải carrier thread

Một số nhầm lẫn thường gặp:

- `Thread.currentThread()` trong tác vụ virtual thread trả về virtual thread, không phải carrier.
- Virtual thread có thể được mount lên carrier khác nhau ở những thời điểm khác nhau; không lưu trạng thái nghiệp vụ trong `ThreadLocal` của carrier.
- `ThreadLocal` được gắn với virtual thread và vẫn có ngữ nghĩa theo từng thread. Tuy nhiên, tạo rất nhiều virtual thread có thể làm tăng bộ nhớ nếu mỗi thread giữ nhiều dữ liệu trong `ThreadLocal`.
- Carrier thread không phải đơn vị tác vụ mà ứng dụng nên dùng để phân phối request. Đơn vị công việc của ứng dụng là virtual thread hoặc task được gửi vào executor.
- Virtual thread vẫn là thread thật trong mô hình Java: có thể bị interrupt, có tên, trạng thái, stack trace và các thuộc tính thread theo API Java.

## 8. Pinning: khi virtual thread giữ carrier trong lúc blocking

Trong Java 21, virtual thread có thể bị pin vào carrier khi thực hiện thao tác blocking trong một vùng `synchronized` hoặc khi chạy native method. Khi bị pin, virtual thread không thể unmount theo cơ chế thông thường; carrier bị giữ trong thời gian thao tác blocking đó.

Ví dụ một vùng đồng bộ chứa lời gọi blocking:

```java
synchronized (lock) {
    callBlockingService();
}
```

Nếu `callBlockingService()` chờ lâu, virtual thread có thể giữ carrier trong suốt thời gian đó. Một vùng `synchronized` ngắn, không có thao tác blocking thường không phải vấn đề; cần chú ý khi giữ monitor trong lúc chờ I/O hoặc chờ lâu.

Khi cần khóa quanh đoạn code có thể blocking trong Java 21, có thể cân nhắc `ReentrantLock` sau khi đánh giá đúng ngữ nghĩa đồng bộ và bảo đảm luôn unlock trong `finally`. Không thay thế `synchronized` một cách máy móc; trước hết cần xác định pinning có thực sự ảnh hưởng đến workload.

Có thể quan sát sự kiện pinning bằng Java Flight Recorder với event `jdk.VirtualThreadPinned`. Các chẩn đoán và hành vi pinning cần được xem theo đúng phiên bản JDK đang chạy: mô tả `synchronized` ở đây là hành vi của Java 21; các bản JDK mới hơn đã có thay đổi ở cơ chế monitor pinning.

## 9. Khi nào nên chọn virtual thread hoặc platform thread?

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Nhiều request đồng thời, phần lớn thời gian chờ database/HTTP | Virtual thread, một thread cho mỗi tác vụ |
| Code blocking theo phong cách tuần tự, cần tăng khả năng mở rộng I/O | Virtual thread |
| Tác vụ CPU-bound nặng | Pool có giới hạn theo năng lực CPU; virtual thread không làm phép tính chạy nhanh hơn |
| Công việc cần kiểm soát tài nguyên hữu hạn như connection hoặc API quota | Virtual thread kết hợp giới hạn tài nguyên |
| Tích hợp thư viện native hoặc vùng blocking có thể pin carrier | Đo đạc và đánh giá; có thể cần điều chỉnh cách đồng bộ hoặc dùng platform thread tùy trường hợp |

Virtual thread chủ yếu cải thiện khả năng mở rộng và thông lượng cho workload có nhiều thời gian chờ. Chúng không tự làm một truy vấn database nhanh hơn, không giảm độ trễ của từng thao tác I/O và không loại bỏ giới hạn của connection pool, bộ nhớ hoặc dịch vụ phụ thuộc.

## 10. Các nguyên tắc thiết kế

1. Dùng virtual thread cho đơn vị công việc, không dùng carrier thread làm abstraction của ứng dụng.
2. Không pool virtual thread; tạo một virtual thread cho mỗi task hoặc dùng `newVirtualThreadPerTaskExecutor()`.
3. Giới hạn tài nguyên bên ngoài bằng cơ chế chuyên dụng, không giới hạn số virtual thread chỉ để mô phỏng pool platform thread.
4. Tránh giữ monitor hoặc gọi native code trong thời gian blocking dài khi chạy Java 21; đo pinning trước khi thay đổi thiết kế.
5. Không giả định một virtual thread luôn chạy trên cùng carrier.
6. Không dùng virtual thread để tăng tốc công việc CPU-bound; hiệu năng vẫn phụ thuộc số lõi và thuật toán.
7. Đo thông lượng, độ trễ, CPU, heap, số kết nối và mức đồng thời với tải gần thực tế trước khi triển khai.

## 11. Sử dụng với Java 21

Virtual Threads được hoàn thiện trong Java 21 qua JEP 444. Các API như `Thread.ofVirtual()`, `Thread.isVirtual()` và `Executors.newVirtualThreadPerTaskExecutor()` có thể dùng trực tiếp, không cần bật Preview.

```bash
javac --release 21 -d out src/VirtualThreadExample.java
java -cp out VirtualThreadExample
```

Đặt compiler release hoặc toolchain về Java 21 để bảo đảm mã nguồn sử dụng đúng API của phiên bản mục tiêu. Không thêm `--enable-preview` cho virtual threads.

## 12. Tài liệu tham khảo

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Java SE 21 API — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Oracle — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle — Java Flight Recorder Events](https://docs.oracle.com/en/java/javase/21/docs/specs/jfr/jfr-event-reference.html)

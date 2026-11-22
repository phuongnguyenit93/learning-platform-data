# Trạng thái daemon và ảnh hưởng đến thời điểm JVM kết thúc

Trong Java 21, mọi virtual thread đều là daemon thread. Điều này có nghĩa là virtual thread không giữ cho Java Virtual Machine (JVM) tiếp tục chạy khi tất cả thread không phải daemon đã kết thúc. Nếu ứng dụng chỉ còn các virtual thread đang thực hiện công việc, JVM có thể bắt đầu quá trình shutdown mà không chờ các công việc đó hoàn tất.

Đặc điểm này ảnh hưởng trực tiếp đến cách tổ chức vòng đời ứng dụng. Virtual thread phù hợp để thực hiện nhiều tác vụ đồng thời, nhưng ứng dụng vẫn phải quản lý việc chờ kết quả, đóng executor và giữ thread điều phối sống đủ lâu để công việc quan trọng hoàn tất.

## 1. Daemon thread ảnh hưởng thế nào đến vòng đời JVM?

Java phân loại thread thành hai nhóm:

- **User thread (non-daemon):** thread không có trạng thái daemon. Khi còn user thread đang chạy, JVM chưa kết thúc chỉ vì thread main đã trả về.
- **Daemon thread:** thread nền không giữ JVM sống. Khi không còn user thread nào, JVM có thể bắt đầu shutdown dù daemon thread vẫn đang chạy.

Quy tắc này áp dụng cho cả platform thread và virtual thread. Điểm riêng của virtual thread trong Java 21 là chúng luôn có daemon status.

Ví dụ một platform thread được tạo theo cách thông thường mặc định là non-daemon nếu được tạo từ một non-daemon thread. Có thể thay đổi daemon status trước khi start bằng setDaemon(...). Virtual thread thì luôn daemon và không thể chuyển thành non-daemon.

Khi tất cả non-daemon thread đã kết thúc, JVM bắt đầu quá trình shutdown. Các shutdown hook đã đăng ký có thể được chạy trong quá trình này; tuy nhiên, ứng dụng không được xem việc shutdown hook chạy như một cơ chế bảo đảm cho mọi virtual thread đang thực hiện sẽ hoàn thành.

## 2. Virtual thread luôn là daemon thread

Virtual thread được tạo bằng API chính thức của Java 21, chẳng hạn Thread.ofVirtual() hoặc Thread.startVirtualThread(), luôn có isDaemon() trả về true.

~~~java
Thread worker = Thread.ofVirtual().unstarted(() -> {
    System.out.println("Working in a virtual thread");
});

System.out.println(worker.isVirtual()); // true
System.out.println(worker.isDaemon());  // true
~~~

Có thể kiểm tra trạng thái daemon trước khi start. Không cần gọi setDaemon(true) vì virtual thread đã có trạng thái này ngay từ khi được tạo.

Không thể đổi virtual thread thành non-daemon bằng setDaemon(false). Java từ chối yêu cầu thay đổi daemon status của virtual thread bằng IllegalArgumentException. Vì vậy, không nên thiết kế vòng đời ứng dụng dựa trên giả định có thể giữ JVM sống bằng cách chuyển một virtual thread thành user thread.

Daemon status không có nghĩa là virtual thread có độ ưu tiên thấp hơn, không được scheduler thực thi hoặc tự động bị dừng khi không có việc. Nó chỉ xác định vai trò của thread trong quy tắc kết thúc JVM.

## 3. Điều gì xảy ra nếu main kết thúc trước virtual thread?

Một lỗi thường gặp là start virtual thread rồi để phương thức main kết thúc ngay mà không chờ công việc. Nếu không còn non-daemon thread nào khác, JVM có thể bắt đầu shutdown trong khi virtual thread chưa hoàn tất.

~~~java
public class Main {
    public static void main(String[] args) {
        Thread worker = Thread.startVirtualThread(() -> {
            try {
                Thread.sleep(2_000);
                System.out.println("Task completed");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        System.out.println("Main is ending");
    }
}
~~~

Trong ví dụ này, main không chờ worker. Dòng Main is ending có thể được in ra, sau đó JVM có thể kết thúc khi chỉ còn virtual thread đang ngủ. Không có bảo đảm rằng Task completed sẽ được in.

Không nên dựa vào thời gian chạy tình cờ để kết luận rằng virtual thread sẽ luôn kịp thực hiện. Trên một lần chạy, tác vụ có thể hoàn thành trước khi main kết thúc; trên lần chạy khác, JVM có thể bắt đầu shutdown trước khi tác vụ hoàn thành.

Nếu kết quả của tác vụ là cần thiết, hãy chờ thread hoặc quản lý tác vụ thông qua executor và Future.

## 4. Dùng join() để chờ virtual thread hoàn tất

Thread.join() khiến thread gọi phương thức chờ cho đến khi thread đích kết thúc. Đây là cách trực tiếp khi ứng dụng tự tạo và quản lý một virtual thread riêng lẻ.

~~~java
public class Main {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual().start(() -> {
            try {
                Thread.sleep(1_000);
                System.out.println("Task completed");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        worker.join();
        System.out.println("Main continues after worker");
    }
}
~~~

Thứ tự kết quả bảo đảm là:

1. Virtual thread thực hiện tác vụ và in Task completed.
2. worker.join() kết thúc sau khi worker đã kết thúc.
3. Thread main tiếp tục và in Main continues after worker.

Trong ví dụ, main là non-daemon thread nên JVM vẫn sống trong lúc main đang chờ. join() không thay đổi daemon status của virtual thread; nó chỉ phối hợp vòng đời bằng cách chờ tác vụ kết thúc.

Nếu thread gọi join() bị interrupt, phương thức ném InterruptedException. Ứng dụng cần quyết định xử lý việc hủy chờ hoặc khôi phục interrupt status theo hợp đồng của phương thức đang thực hiện.

## 5. Dùng ExecutorService để quản lý nhiều virtual thread

Với nhiều tác vụ, Executors.newVirtualThreadPerTaskExecutor() cung cấp một ExecutorService tạo một virtual thread cho mỗi tác vụ được submit. Nên quản lý executor bằng try-with-resources để việc đóng executor gắn với phạm vi công việc.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class Main {
    public static void main(String[] args) {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            executor.submit(() -> {
                System.out.println("Task A");
            });

            executor.submit(() -> {
                System.out.println("Task B");
            });
        }

        System.out.println("All submitted tasks have completed");
    }
}
~~~

Khi rời khỏi khối try, close() của ExecutorService khởi tạo orderly shutdown và chờ các tác vụ đã submit hoàn tất trước khi trả về. Vì vậy, main không kết thúc phạm vi quản lý executor trong khi các tác vụ đã submit vẫn chưa hoàn thành.

ExecutorService.close() là API đã có từ trước Java 21 và được sử dụng bình thường với virtual-thread-per-task executor. Không cần dùng API preview để quản lý vòng đời của executor.

Cách này đặc biệt hữu ích khi có nhiều tác vụ độc lập. Nó giúp gom việc submit, chờ và đóng executor vào một phạm vi rõ ràng, thay vì tạo thread rồi tự theo dõi từng thread.

## 6. Dùng Future.get() khi cần kết quả cụ thể

submit() trả về một Future. Gọi get() khiến thread hiện tại chờ cho đến khi tác vụ hoàn thành và nhận kết quả hoặc lỗi của tác vụ.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class Main {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            Future<String> future = executor.submit(() -> {
                Thread.sleep(500);
                return "Result from virtual thread";
            });

            String result = future.get();
            System.out.println(result);
        }
    }
}
~~~

future.get() có hai ý nghĩa quan trọng:

- Chờ cho tác vụ tương ứng hoàn thành trước khi tiếp tục.
- Trả kết quả hoặc báo lỗi thực thi thông qua ExecutionException.

Nếu thread đang gọi get() bị interrupt, phương thức ném InterruptedException. Có thể dùng get(timeout, unit) khi cần giới hạn thời gian chờ; khi hết thời gian, TimeoutException được ném nhưng tác vụ không tự động bị hủy chỉ vì lần chờ bị timeout.

Future.get() phù hợp khi chương trình cần kết quả của một tác vụ cụ thể. Nếu chỉ cần bảo đảm toàn bộ tác vụ trong một phạm vi executor được hoàn thành, try-with-resources với ExecutorService.close() có thể là cách quản lý đơn giản hơn.

## 7. Phân biệt kết thúc main, đóng executor và kết thúc tác vụ

Ba sự kiện này có ý nghĩa khác nhau:

| Sự kiện | Ý nghĩa |
|---|---|
| Phương thức main kết thúc | Thread main đã hoàn thành; các non-daemon thread khác vẫn có thể giữ JVM sống |
| Virtual thread kết thúc | Một tác vụ cụ thể đã hoàn tất; việc này không tự kết thúc JVM nếu còn non-daemon thread |
| ExecutorService.close() trả về | Executor đã shutdown và các tác vụ đã submit hoàn tất theo quy tắc đóng executor |

Không nên suy luận rằng main kết thúc đồng nghĩa tất cả virtual thread kết thúc. Cũng không nên suy luận rằng một virtual thread còn chạy thì JVM chắc chắn tiếp tục chạy.

Hãy xác định rõ thành phần nào chịu trách nhiệm chờ công việc. Trong ứng dụng đơn giản, main có thể gọi join() hoặc Future.get(). Trong ứng dụng dùng executor, phạm vi try-with-resources có thể chịu trách nhiệm chờ và đóng executor.

## 8. Shutdown hook không thay thế việc quản lý vòng đời tác vụ

JVM hỗ trợ đăng ký shutdown hook bằng Runtime.addShutdownHook(...). Hook được chạy khi JVM bắt đầu shutdown theo các điều kiện của runtime. Hook thường được dùng để giải phóng tài nguyên hoặc hoàn tất một số thao tác dọn dẹp có giới hạn.

~~~java
Runtime.getRuntime().addShutdownHook(
    new Thread(() -> System.out.println("Shutdown hook running"))
);
~~~

Shutdown hook không biến virtual thread thành non-daemon và cũng không bảo đảm một tác vụ nền sẽ hoàn tất trước khi JVM shutdown. Không nên dùng shutdown hook như một cách thay thế cho join(), Future.get() hoặc việc đóng executor đúng cách.

Nếu ứng dụng cần hoàn tất ghi dữ liệu, gửi kết quả hoặc đóng tài nguyên trước khi kết thúc, hãy phối hợp các tác vụ đó trong luồng điều khiển chính và chỉ kết thúc ứng dụng sau khi hoàn tất hoặc xử lý timeout/hủy tác vụ theo yêu cầu.

## 9. Những hiểu nhầm thường gặp

| Hiểu nhầm | Hành vi đúng trong Java 21 |
|---|---|
| Virtual thread là non-daemon nếu được tạo từ main | Virtual thread luôn daemon, bất kể thread tạo ra nó là loại nào |
| Có thể gọi setDaemon(false) để giữ JVM sống | Không thể đổi daemon status của virtual thread; yêu cầu này bị từ chối |
| Executor tự giữ JVM sống vì có tác vụ | Virtual-thread-per-task executor chạy tác vụ trên virtual thread; cần quản lý và chờ executor đúng cách |
| Main kết thúc thì mọi virtual thread đã xong | Main có thể kết thúc khi virtual thread vẫn đang chạy |
| Chỉ cần start virtual thread là JVM sẽ chờ | JVM không chờ daemon thread khi không còn non-daemon thread |
| Future.get(timeout, unit) hết timeout sẽ hủy tác vụ | Timeout chỉ kết thúc lần chờ; muốn hủy phải yêu cầu hủy riêng và xử lý interruption |
| Shutdown hook bảo đảm mọi virtual thread hoàn tất | Shutdown hook là cơ chế dọn dẹp khi shutdown, không thay thế phối hợp tác vụ |

## 10. Checklist quản lý vòng đời virtual thread

Khi thiết kế ứng dụng Java 21 sử dụng virtual thread, hãy kiểm tra:

1. Tác vụ có cần hoàn tất trước khi ứng dụng kết thúc không?
2. Nếu cần, thread nào sẽ chờ kết quả: main, một thread điều phối hay Future.get()?
3. Nếu dùng executor, executor có được đóng đúng phạm vi bằng try-with-resources hoặc shutdown phù hợp không?
4. Có tác vụ nào có thể chờ vô hạn khiến join(), get() hoặc close() kéo dài không?
5. Timeout có được xử lý riêng với việc hủy tác vụ không?
6. Khi nhận InterruptedException, mã có xử lý interrupt status và dừng công việc phù hợp không?
7. Shutdown hook có đang bị dùng thay cho việc chờ tác vụ một cách không phù hợp không?

## Kết luận

Trong Java 21, virtual thread luôn là daemon thread và không giữ JVM sống khi tất cả non-daemon thread đã kết thúc. Vì vậy, việc start virtual thread không đồng nghĩa JVM sẽ chờ tác vụ hoàn thành. Hãy dùng join() cho thread riêng lẻ, Future.get() khi cần kết quả và quản lý ExecutorService bằng try-with-resources khi chạy nhiều tác vụ. Vòng đời của ứng dụng phải chủ động chờ hoặc hủy công việc theo hợp đồng, thay vì dựa vào daemon status.

## Tài liệu tham khảo

- [Java SE 21 API — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21 API — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java Language Specification, Java SE 21 — Program Exit (§12.8)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)

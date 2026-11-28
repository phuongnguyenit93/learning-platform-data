# Vì sao synchronized trên wrapper hoặc đối tượng value-based không an toàn

Trong Java, câu lệnh **synchronized** khóa một object thông qua intrinsic monitor gắn với identity của object đó. Cơ chế này hoạt động tốt khi chương trình sở hữu một object khóa riêng, có identity ổn định và được các luồng cần phối hợp sử dụng thống nhất.

Các lớp wrapper như **Integer**, **Long**, **Boolean** và nhiều lớp thư viện như **Optional**, **LocalDate** là value-based class. Hợp đồng của chúng tập trung vào giá trị và không bảo đảm identity riêng cho từng instance. Vì vậy, dùng một instance thuộc nhóm này làm monitor có thể khiến những đoạn code không liên quan vô tình khóa cùng object, hoặc khiến các luồng cần phối hợp lại khóa những object khác nhau.

JEP 390 được đưa vào JDK 16 để cảnh báo cách sử dụng này. Nguyên tắc vẫn áp dụng trong Java hiện đại: dùng object khóa chuyên biệt do chương trình kiểm soát, hoặc API đồng bộ phù hợp trong **java.util.concurrent**.

## 1. synchronized khóa monitor của object như thế nào?

Mỗi object trong Java gắn với một intrinsic monitor. Khi một luồng đi vào khối **synchronized**, nó phải lấy được monitor của object được chỉ định. Nếu luồng khác đang giữ monitor đó, luồng hiện tại phải chờ.

~~~java
private final Object lock = new Object();
private int balance;

public void deposit(int amount) {
    synchronized (lock) {
        balance += amount;
    }
}
~~~

Trong ví dụ, các lời gọi đồng bộ trên cùng instance sử dụng cùng object **lock**. Monitor bảo đảm chỉ một luồng tại một thời điểm thực thi đoạn code bên trong khối đó.

Monitor cũng tạo ra quan hệ visibility trong Java Memory Model: thao tác mở khóa trên monitor xảy ra trước một lần khóa thành công tiếp theo trên cùng monitor. Nhờ vậy, các thay đổi được thực hiện trong vùng đồng bộ có thể được luồng sau quan sát theo quy tắc happens-before.

Có hai điểm cần phân biệt:

- **Monitor dựa trên identity:** hai biến chỉ phối hợp qua cùng monitor khi chúng tham chiếu tới cùng một object.
- **equals() không quyết định monitor:** hai object có thể bằng nhau theo **equals()** nhưng vẫn là hai object khác nhau và có hai monitor riêng.

Do đó, một lớp có **equals()** so sánh theo giá trị không làm cho monitor của các instance bằng nhau tự động trở thành một monitor chung. Câu lệnh **synchronized** không gọi **equals()** hoặc **hashCode()** để tìm khóa.

## 2. Vì sao wrapper không phải object khóa phù hợp?

Wrapper biểu diễn giá trị nguyên thủy dưới dạng object. Ví dụ, **Integer** biểu diễn một giá trị **int**. Java cung cấp factory như **Integer.valueOf()** và autoboxing để tạo wrapper thuận tiện.

~~~java
Integer first = Integer.valueOf(10);
Integer second = Integer.valueOf(10);

System.out.println(first.equals(second)); // true
~~~

Hai wrapper biểu diễn cùng số nguyên. Tuy nhiên, hợp đồng value-based không cho chương trình quyền giả định rằng mỗi giá trị luôn có một object riêng hoặc các lần tạo giá trị bằng nhau luôn phải dùng chung object.

Một số factory có cache theo hợp đồng API. Chẳng hạn, **Integer.valueOf(int)** bảo đảm tái sử dụng instance trong phạm vi từ **-128** đến **127**, và implementation có thể cache thêm giá trị khác. Vì thế, hai đoạn code độc lập có thể nhận cùng một wrapper từ cache dù chúng không có ý định dùng chung khóa.

Ví dụ không an toàn:

~~~java
public class Inventory {
    private static final Integer LOCK = Integer.valueOf(1);
    private int quantity;

    public void add(int amount) {
        synchronized (LOCK) {
            quantity += amount;
        }
    }
}
~~~

Trường **LOCK** có vẻ là một khóa riêng vì được khai báo **private static final**. Nhưng object được tham chiếu vẫn là một **Integer** value-based và có thể là instance được chia sẻ từ cache. Một đoạn code khác trong cùng JVM cũng có thể lấy đúng instance đó:

~~~java
synchronized (Integer.valueOf(1)) {
    // Một thao tác không liên quan tới Inventory
}
~~~

Hai đoạn code có thể vô tình tranh chấp cùng monitor. Điều này làm giảm tính độc lập giữa các thành phần và có thể gây chờ đợi ngoài dự kiến.

Cách dùng sau cũng không an toàn:

~~~java
public void updateUser(int userId) {
    synchronized (Integer.valueOf(userId)) {
        // Cập nhật dữ liệu của user
    }
}
~~~

Nếu hai lời gọi nhận cùng wrapper instance, chúng dùng chung monitor. Nếu runtime không tái sử dụng instance ở một giá trị nào đó, các lời gọi có thể dùng monitor khác nhau dù chương trình nghĩ rằng chúng đang khóa theo cùng mã người dùng. Identity của wrapper không phải cơ chế quản lý khóa theo nghiệp vụ.

## 3. Rủi ro đến từ cả cache và hợp đồng value-based

Có hai tình huống cần hiểu rõ.

### Các giá trị khác nhau có thể dùng chung một monitor ngoài dự kiến

Với giá trị thuộc vùng cache, các lời gọi factory hoặc boxing phù hợp có thể nhận cùng object. Nếu nhiều thành phần dùng wrapper đó làm khóa, chúng vô tình phụ thuộc vào cùng monitor.

Hệ quả có thể là:

- Một đoạn code phải chờ một đoạn code khác vốn không liên quan.
- Hiệu năng giảm do tranh chấp monitor.
- Thứ tự khóa khó dự đoán khi các thành phần lồng nhau nhiều khối đồng bộ.
- Một thư viện hoặc đoạn code mới có thể tạo ra xung đột khóa mà người viết ban đầu không dự kiến.

### Các instance bằng nhau không nhất thiết là cùng monitor

Với giá trị nằm ngoài phạm vi cache được bảo đảm, factory có thể trả về instance khác nhau. Hai instance vẫn bằng nhau theo **equals()**, nhưng mỗi instance có monitor riêng.

Nếu hai luồng cần bảo vệ cùng một trạng thái mà mỗi luồng khóa một instance khác nhau, chúng không loại trừ lẫn nhau. Cả hai có thể cùng đi vào vùng code mà chương trình tưởng rằng đã được bảo vệ.

~~~java
Integer lockA = Integer.valueOf(1000);
Integer lockB = Integer.valueOf(1000);

// Không có bảo đảm lockA và lockB là cùng object
// Hai khối synchronized có thể khóa hai monitor khác nhau.
~~~

Không thể sửa vấn đề bằng cách chọn một giá trị nằm trong vùng cache. Khi đó, khóa lại có thể bị chia sẻ với code khác. Điều cần thiết là một object được tạo riêng cho mục đích đồng bộ và có quyền sở hữu rõ ràng.

## 4. Value-based class không cam kết identity ổn định

Value-based class được thiết kế để chương trình quan tâm tới giá trị của instance. Các instance bằng nhau theo **equals()** được xem là có thể thay thế cho nhau trong những thao tác được lớp định nghĩa.

Hợp đồng này cho phép thư viện và JVM linh hoạt hơn trong việc tạo, tái sử dụng hoặc biểu diễn các giá trị. Chương trình không nên dựa vào:

- Hai lần tạo giá trị bằng nhau chắc chắn nhận hai object khác nhau.
- Hai lần tạo giá trị bằng nhau chắc chắn nhận cùng object.
- Identity hash code của instance là định danh duy nhất cho giá trị.
- Monitor của instance là tài nguyên đồng bộ do riêng đoạn code hiện tại sở hữu.

Ngay cả khi một phiên bản JDK hiện tại vẫn cho phép khóa trên instance đó, điều này không tạo ra cam kết identity lâu dài cho ứng dụng. JDK có thể thay đổi cách biểu diễn hoặc tối ưu các value-based instance trong những phiên bản tương lai.

Điều này giải thích vì sao **synchronized** trên wrapper là sai về thiết kế ngay cả khi chương trình chưa quan sát thấy lỗi hoặc tranh chấp trong môi trường hiện tại.

## 5. JEP 390 giúp phát hiện cách dùng sai như thế nào?

JEP 390 được giới thiệu trong JDK 16 với tên **Warnings for Value-Based Classes**. JEP này đánh dấu các lớp value-based trong thư viện nền tảng để công cụ của JDK nhận diện và bổ sung cảnh báo khi chương trình dùng instance value-based ở nơi cần identity, đặc biệt là đồng bộ hóa.

Cảnh báo giúp phát hiện vấn đề trong lúc biên dịch và lúc chạy. Chúng là tín hiệu cần sửa thiết kế khóa, không phải cơ chế tự động thay thế monitor.

### Cảnh báo từ javac

Trên JDK hiện đại, có thể bật nhóm lint **identity**:

~~~bash
javac -Xlint:identity -d out src/example/Main.java
~~~

Nhóm cảnh báo này bao gồm việc sử dụng value-based class ở nơi cần identity. Nó được bật mặc định trong cấu hình javac hiện hành; việc chỉ định rõ tùy chọn giúp thể hiện chủ đích kiểm tra trong script build hoặc cấu hình CI.

Ví dụ có thể tạo cảnh báo:

~~~java
Integer lock = Integer.valueOf(1);

synchronized (lock) {
    System.out.println("Updating state");
}
~~~

Compiler có thể phát hiện trường hợp này vì kiểu tĩnh của biểu thức khóa là **Integer**. Tuy nhiên, không phải mọi trường hợp phụ thuộc identity đều có thể được phát hiện tĩnh. Không có cảnh báo không đồng nghĩa code chắc chắn an toàn.

### Chẩn đoán lúc chạy trên HotSpot

JEP 390 cũng bổ sung khả năng chẩn đoán đồng bộ trên value-based instance trong HotSpot. Khi kiểm tra một ứng dụng, có thể chạy với tùy chọn:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:DiagnoseSyncOnValueBasedClasses=2 -jar app.jar
~~~

Chế độ **2** yêu cầu HotSpot ghi nhận cảnh báo khi phát hiện đồng bộ trên instance value-based. Đây là tùy chọn chẩn đoán dành cho quá trình kiểm tra và di trú ứng dụng; hãy xác nhận tùy chọn trên đúng bản phân phối và phiên bản HotSpot đang dùng.

Cảnh báo compiler và chẩn đoán runtime bổ sung cho nhau: compiler kiểm tra các trường hợp có thể nhận diện từ mã nguồn, còn runtime giúp tìm các đường chạy thực tế. Khi phát hiện cảnh báo, hãy sửa object khóa trong code thay vì chỉ tắt cảnh báo.

## 6. Cách thay thế an toàn bằng object khóa riêng

Giải pháp phổ biến là tạo một object **Object** chuyên dùng làm khóa. Không dùng wrapper hoặc một value-based class khác.

### Khóa riêng cho từng instance

Nếu mỗi đối tượng quản lý trạng thái riêng, tạo khóa riêng trong instance:

~~~java
public class Account {
    private final Object lock = new Object();
    private long balance;

    public void deposit(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }

        synchronized (lock) {
            balance += amount;
        }
    }

    public long balance() {
        synchronized (lock) {
            return balance;
        }
    }
}
~~~

Mỗi **Account** có một object khóa riêng. Các thao tác trên cùng tài khoản phối hợp qua cùng monitor; thao tác trên hai tài khoản khác nhau có thể diễn ra đồng thời.

Giữ field khóa ở mức **private final** để code bên ngoài không thể lấy hoặc thay thế khóa. Không trả khóa qua getter và không dùng khóa này cho mục đích khác.

### Khóa chung cho trạng thái static

Nếu nhiều instance cùng bảo vệ một trạng thái static, khóa cần được chia sẻ ở cấp lớp:

~~~java
public class GlobalCounter {
    private static final Object LOCK = new Object();
    private static long count;

    public static void increment() {
        synchronized (LOCK) {
            count++;
        }
    }

    public static long value() {
        synchronized (LOCK) {
            return count;
        }
    }
}
~~~

Ở đây, tất cả lời gọi bảo vệ cùng biến **count** đều dùng một monitor. Chọn phạm vi khóa theo phạm vi trạng thái cần bảo vệ: trạng thái instance dùng khóa instance, trạng thái static dùng khóa static.

### Không dùng this hoặc Class object một cách tùy tiện

Phương thức instance khai báo **synchronized** khóa monitor của **this**. Phương thức static khai báo **synchronized** khóa monitor của đối tượng **Class** tương ứng.

~~~java
public synchronized void update() {
    // Khóa this
}

public static synchronized void updateAll() {
    // Khóa monitor của Class
}
~~~

Các cách này vẫn là cơ chế Java hợp lệ, nhưng chỉ nên dùng khi quyền sở hữu monitor rõ ràng và object không bị code bên ngoài sử dụng làm khóa ngoài ý muốn. Với thư viện hoặc lớp được chia sẻ rộng, khóa riêng **private final Object** thường giúp kiểm soát tốt hơn.

## 7. Khi nào nên dùng ReentrantLock hoặc API đồng bộ khác?

Intrinsic monitor với **synchronized** phù hợp cho vùng tới hạn ngắn và cấu trúc khóa đơn giản. Nếu cần khả năng điều khiển cao hơn, Java cung cấp các API hiện hành trong **java.util.concurrent**.

Ví dụ dùng **ReentrantLock**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class JobQueue {
    private final ReentrantLock lock = new ReentrantLock();
    private int completedJobs;

    public void markCompleted() {
        lock.lock();
        try {
            completedJobs++;
        } finally {
            lock.unlock();
        }
    }

    public int completedJobs() {
        lock.lock();
        try {
            return completedJobs;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Luôn đặt **unlock()** trong khối **finally** để khóa được nhả kể cả khi code trong vùng tới hạn phát sinh exception.

Có thể cân nhắc:

| Nhu cầu | API phù hợp |
| --- | --- |
| Bảo vệ một vùng code ngắn, đơn giản | **synchronized** với khóa riêng |
| Cần thử lấy khóa, timeout hoặc khả năng interrupt khi chờ | **ReentrantLock** |
| Đếm sự kiện đồng thời với nhiều luồng ghi | **LongAdder** |
| Cập nhật một giá trị nguyên tử đơn giản | **AtomicInteger**, **AtomicLong** |
| Trao đổi dữ liệu giữa các luồng | **BlockingQueue** |
| Chờ một nhóm tác vụ hoàn thành | **CountDownLatch** hoặc **Phaser** |

Chọn API dựa trên yêu cầu phối hợp luồng. Không tạo wrapper hoặc value-based instance làm khóa để mô phỏng các chức năng mà thư viện đồng thời đã cung cấp.

## 8. Quy trình rà soát synchronized trên wrapper trong dự án

Khi nâng cấp dự án lên JDK mới hoặc xử lý cảnh báo JEP 390, có thể rà soát theo các bước:

1. Tìm các khối **synchronized** có biểu thức khóa là wrapper như **Integer**, **Long**, **Boolean** hoặc một value-based class khác.
2. Kiểm tra các phương thức **synchronized** và những lời gọi **wait()**, **notify()**, **notifyAll()** trên các instance value-based.
3. Xác định trạng thái được bảo vệ thuộc về một instance, toàn lớp hay một tài nguyên dùng chung.
4. Tạo khóa **Object** riêng ở đúng phạm vi, hoặc chuyển sang API đồng bộ trong **java.util.concurrent**.
5. Chạy compiler với **-Xlint:identity** và kiểm tra các đường chạy quan trọng bằng chẩn đoán HotSpot nếu cần.
6. Kiểm tra lại phạm vi khóa, thứ tự lấy khóa và quan hệ visibility sau khi thay đổi.

Đừng chỉ đổi **Integer** thành **Long**, **Boolean**, **Optional** hoặc một lớp immutable khác. Nếu lớp đó là value-based, vấn đề identity vẫn còn. Cũng đừng chỉ tăng giá trị khóa ra ngoài vùng cache: điều đó làm hành vi phụ thuộc implementation thay vì giải quyết quyền sở hữu monitor.

## 9. Kết luận

**synchronized** dựa trên identity của object để lấy monitor. Wrapper và value-based class biểu diễn giá trị, không cung cấp cam kết identity ổn định hoặc độc quyền cho logic đồng bộ. Cache wrapper có thể làm các đoạn code không liên quan dùng chung monitor; các instance bằng nhau nhưng khác identity cũng có thể khiến những luồng cần phối hợp khóa nhầm monitor khác nhau.

JEP 390 giúp phát hiện một số cách sử dụng sai qua cảnh báo compiler và chẩn đoán HotSpot. Cách sửa bền vững là tạo khóa **Object** riêng, giữ quyền sở hữu khóa rõ ràng và chọn **ReentrantLock**, **AtomicInteger**, **BlockingQueue** hoặc API đồng thời khác khi nhu cầu phù hợp.

## Tài liệu tham khảo

- [JEP 390: Warnings for Value-Based Classes](https://openjdk.org/jeps/390)
- [Value-based Classes — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/doc-files/ValueBased.html)
- [JLS 27 — Synchronization (Section 17.1)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html#jls-17.1)
- [Integer — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Integer.html)
- [The javac Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [ReentrantLock — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [AtomicInteger — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
- [BlockingQueue — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/BlockingQueue.html)


# Đọc cảnh báo javac -Xlint:synchronization và sửa đúng thiết kế khóa

JEP 390 được đưa vào JDK 16 để giúp phát hiện việc dùng instance của value-based class ở nơi cần identity, đặc biệt là khi đồng bộ bằng **synchronized**. Khi biên dịch, **javac** có thể cảnh báo nếu biểu thức khóa có kiểu value-based như **Integer**, **Optional** hoặc **LocalDate**.

Cảnh báo ban đầu dùng nhóm lint **synchronization**. Trong javac hiện đại, nhóm này đã trở thành alias deprecated của **identity**; tài liệu JDK 27 khuyến nghị dùng **-Xlint:identity** cho các cấu hình mới. Vì vậy, cần hiểu cả cách đọc cảnh báo từ JDK 16 lẫn tên nhóm hiện hành, sau đó sửa đối tượng khóa theo đúng quyền sở hữu trạng thái.

## 1. JEP 390 cảnh báo vấn đề gì?

Value-based class được thiết kế để biểu diễn giá trị. Hai instance bằng nhau theo **equals()** được xem là có thể thay thế cho nhau trong những thao tác mà lớp định nghĩa. API không cam kết mỗi giá trị phải có một object identity riêng hoặc các lần tạo giá trị bằng nhau phải luôn trả về cùng một reference.

Các ví dụ thường gặp:

- Wrapper của kiểu nguyên thủy như **Integer**, **Long**, **Boolean** và **Double**.
- **Optional**, **OptionalInt**, **OptionalLong** và **OptionalDouble**.
- Nhiều kiểu ngày giờ trong **java.time** như **LocalDate**, **LocalDateTime**, **Instant** và **Duration**.

Trong khi đó, **synchronized** khóa intrinsic monitor gắn với identity của object. Hai instance bằng nhau theo **equals()** nhưng khác reference vẫn có hai monitor riêng. Ngược lại, hai đoạn code không liên quan có thể vô tình dùng chung monitor nếu factory hoặc cơ chế cache trả về cùng instance.

Ví dụ không an toàn:

~~~java
Integer lock = Integer.valueOf(1);

synchronized (lock) {
    updateSharedState();
}
~~~

**Integer** là value-based class. Dùng instance này làm monitor khiến chương trình dựa vào identity mà hợp đồng API không bảo đảm. Cơ chế cache của wrapper còn có thể làm các đoạn code khác lấy đúng instance đó và tranh chấp cùng monitor.

JEP 390 bổ sung cảnh báo từ compiler và khả năng chẩn đoán từ HotSpot để giúp phát hiện một số trường hợp như vậy. Cảnh báo chỉ ra một vấn đề trong thiết kế đồng bộ; việc sửa cần thay đổi object khóa mà chương trình sở hữu.

## 2. Đọc cảnh báo javac trên JDK 16

JDK 16 giới thiệu nhóm lint **synchronization** để cảnh báo khi câu lệnh **synchronized** dùng instance của value-based class làm monitor.

Có thể bật tường minh khi biên dịch:

~~~bash
javac -Xlint:synchronization -d out src/example/Main.java
~~~

Ví dụ với mã nguồn:

~~~java
public class BadLock {
    public static void main(String[] args) {
        Integer lock = Integer.valueOf(1);

        synchronized (lock) {
            System.out.println("Updating state");
        }
    }
}
~~~

Thông báo từ javac JDK 16 có dạng:

~~~text
BadLock.java:5: warning: [synchronization] attempt to synchronize on an instance of a value-based class
        synchronized (lock) {
        ^
1 warning
~~~

Cách đọc thông báo:

| Thành phần | Ý nghĩa |
| --- | --- |
| **BadLock.java:5** | File và dòng có vấn đề |
| **warning** | Đây là cảnh báo; compiler thường vẫn tiếp tục biên dịch |
| **[synchronization]** | Nhóm lint phát hiện vấn đề |
| **attempt to synchronize...** | Biểu thức khóa có kiểu được nhận diện là value-based |
| Dấu **^** | Vị trí câu lệnh cần xem lại |

Thông báo không có nghĩa chương trình chắc chắn deadlock hoặc đã xảy ra race condition. Nó cho biết chương trình đang dùng một object không có hợp đồng identity phù hợp làm monitor. Đây là lỗi thiết kế cần sửa ngay cả khi test hiện tại chưa tái hiện được sự cố.

## 3. Tên cảnh báo trong javac hiện đại

Tên **synchronization** phản ánh mục đích ban đầu của JEP 390. Trong tài liệu javac JDK 27, **synchronization** được ghi là alias deprecated của nhóm **identity**, có tác dụng giống hệt. Tài liệu khuyến nghị sử dụng **identity** cho các cấu hình hiện tại và tương lai.

| Phiên bản compiler | Nhóm lint nên dùng |
| --- | --- |
| JDK 16, khi nhóm cảnh báo được giới thiệu | **-Xlint:synchronization** |
| JDK hiện đại, ví dụ JDK 27 | **-Xlint:identity** |
| JDK hiện đại, cấu hình cũ | **-Xlint:synchronization** vẫn hoạt động như alias deprecated |

Với JDK hiện đại, lệnh khuyến nghị là:

~~~bash
javac -Xlint:identity -d out src/example/Main.java
~~~

Theo tài liệu javac JDK 27, **identity** là một trong những nhóm lint được bật mặc định. Việc chỉ định tường minh trong cấu hình build vẫn hữu ích vì nó thể hiện rõ yêu cầu kiểm tra và giúp tránh phụ thuộc vào cấu hình lint chung của dự án.

Có thể xem danh sách nhóm lint được compiler hỗ trợ bằng:

~~~bash
javac --help-lint
~~~

Nếu dùng JDK 27, kết quả sẽ liệt kê **identity** và **synchronization**; dòng **synchronization** cho biết đây là alias deprecated. Khi cập nhật cấu hình build, hãy chuyển sang **identity**.

Lưu ý: **--release 16** chỉ chọn quy tắc ngôn ngữ, API nền tảng và định dạng class file tương ứng với Java 16. Nó không biến một compiler JDK mới thành javac JDK 16. Nhóm lint và cách compiler phát ra cảnh báo vẫn phụ thuộc phiên bản javac đang thực thi.

## 4. Cảnh báo có thể được bật hoặc biến thành lỗi build

Cảnh báo lint không nhất thiết làm compilation thất bại. Đối với dự án cần ngăn cách dùng identity không an toàn được thêm vào, có thể cấu hình compiler coi cảnh báo này là lỗi.

Trên javac hiện đại:

~~~bash
javac -Xlint:identity -Werror:identity -d out src/example/Main.java
~~~

Khi compiler phát hiện cảnh báo thuộc nhóm **identity**, quá trình biên dịch sẽ thất bại. Tùy chọn **-Werror:identity** yêu cầu xử lý cảnh báo của nhóm đó như lỗi; nhóm lint cũng phải được bật.

Nếu dự án dùng javac cũ hơn chưa hỗ trợ dạng **-Werror:key**, có thể dùng **-Werror** để biến tất cả cảnh báo thành lỗi sau khi đã cân nhắc tác động tới những nhóm cảnh báo khác:

~~~bash
javac -Xlint:synchronization -Werror -d out src/example/Main.java
~~~

Không nên bật **-Werror** một cách máy móc trên dự án lớn chưa được rà soát warning hiện có. Có thể bắt đầu bằng nhóm lint cần kiểm soát, xử lý các vị trí vi phạm, sau đó đưa quy tắc vào CI.

Trong Maven, Gradle hoặc IDE, điều quan trọng là cấu hình đúng compiler thực sự được dùng trong build. Kiểm tra phiên bản bằng:

~~~bash
javac -version
~~~

Một dự án có thể chạy bằng JDK mới nhưng build vẫn gọi một compiler khác qua toolchain hoặc cấu hình của build system. Khi không thấy cảnh báo, hãy xác minh compiler và đối số compile trước khi kết luận code không có vấn đề.

## 5. Xác định nguyên nhân từ kiểu khóa

Cảnh báo thường xuất hiện khi kiểu tĩnh của biểu thức khóa là một value-based class:

~~~java
Integer lock = Integer.valueOf(10);

synchronized (lock) {
    performUpdate();
}
~~~

Các dạng tương tự cũng cần được sửa:

~~~java
Long lock = Long.valueOf(10L);
Boolean lock = Boolean.TRUE;
Optional<String> lock = Optional.of("task");
~~~

Không dùng những instance này làm monitor. Đổi **Integer** thành **Long**, **Boolean**, **Optional** hoặc một value-based class khác không giải quyết được vấn đề.

Compiler phân tích mã nguồn và kiểu mà nó nhìn thấy. Nếu reference được khai báo là **Object**, nhưng lúc chạy lại trỏ tới một value-based instance, compiler có thể không nhận ra trường hợp đó tại vị trí đồng bộ:

~~~java
Object lock = Integer.valueOf(10);

synchronized (lock) {
    performUpdate();
}
~~~

Không có cảnh báo ở một đoạn code như vậy không chứng minh monitor an toàn. Hãy kiểm tra nơi tạo object, kiểu thực tế có thể được gán và quyền sở hữu của khóa. Cũng cần xem những lời gọi **wait()**, **notify()** và **notifyAll()** vì chúng thao tác trên monitor của object.

Cảnh báo là công cụ hỗ trợ phát hiện, không phải một bộ chứng minh rằng toàn bộ chương trình không có lỗi đồng bộ.

## 6. Sửa bằng khóa Object riêng cho trạng thái instance

Nếu trạng thái thuộc về một object, tạo khóa riêng cho mỗi instance:

~~~java
public class Account {
    private final Object lock = new Object();
    private long balance;

    public void deposit(long amount) {
        synchronized (lock) {
            balance += amount;
        }
    }

    public long getBalance() {
        synchronized (lock) {
            return balance;
        }
    }
}
~~~

Mỗi **Account** có một object khóa riêng. Các luồng thao tác trên cùng tài khoản phối hợp qua cùng monitor; các tài khoản độc lập không cần tranh chấp một khóa toàn cục.

Đặc điểm của cách sửa:

- **private** giữ khóa bên trong lớp.
- **final** giữ nguyên tham chiếu khóa sau khi khởi tạo.
- **new Object()** tạo một identity riêng cho mục đích đồng bộ.
- Các thao tác đọc và ghi field được bảo vệ phải sử dụng cùng monitor.

Không trả khóa qua getter hoặc để field khóa ở mức **public**. Nếu code bên ngoài có thể lấy khóa và giữ monitor tùy ý, lớp sẽ mất quyền kiểm soát giao thức đồng bộ.

## 7. Sửa bằng khóa static cho trạng thái dùng chung

Nếu nhiều instance cùng bảo vệ một trạng thái static, dùng một khóa static:

~~~java
public class GlobalCounter {
    private static final Object LOCK = new Object();
    private static long count;

    public static void increment() {
        synchronized (LOCK) {
            count++;
        }
    }

    public static long getCount() {
        synchronized (LOCK) {
            return count;
        }
    }
}
~~~

Tất cả lời gọi truy cập **count** trong cùng class loader dùng chung monitor **LOCK**. Nếu thay bằng khóa instance, mỗi instance có một monitor khác nhau và không bảo vệ được biến static trước truy cập đồng thời từ nhiều instance.

Hãy chọn phạm vi khóa theo phạm vi dữ liệu:

| Dữ liệu cần bảo vệ | Cách khai báo khóa |
| --- | --- |
| Field mutable thuộc một instance | **private final Object lock = new Object()** |
| Field static dùng chung trong lớp | **private static final Object LOCK = new Object()** |
| Một giá trị số độc lập, chỉ cần cập nhật nguyên tử | Có thể dùng **AtomicInteger** hoặc **AtomicLong** |
| Hàng đợi trao đổi dữ liệu giữa các luồng | Có thể dùng **BlockingQueue** |

## 8. Đồng bộ nhất quán và tránh lỗi sau khi sửa

Thay biểu thức khóa mới chỉ là một phần của việc sửa. Cần bảo đảm tất cả đường đọc và ghi trạng thái liên quan cùng tuân theo một giao thức.

Ví dụ, nếu **balance** được cập nhật dưới **lock**, phương thức đọc cũng phải lấy cùng khóa:

~~~java
public long getBalance() {
    synchronized (lock) {
        return balance;
    }
}
~~~

Việc mở khóa trên một monitor xảy ra trước một lần khóa thành công tiếp theo trên cùng monitor theo Java Memory Model. Quan hệ **happens-before** này giúp luồng đọc quan sát được các thay đổi được thực hiện trong vùng đồng bộ.

Khi sửa một cảnh báo, hãy rà soát thêm:

1. Có đường đọc hoặc ghi nào đang truy cập field bên ngoài khóa không?
2. Nhiều field có tạo thành một invariant cần được cập nhật trong cùng vùng đồng bộ không?
3. Có đoạn code nào lấy nhiều khóa theo thứ tự ngược nhau không?
4. Có gọi I/O, mạng hoặc callback bên ngoài trong khi đang giữ monitor không?
5. Có dùng **wait()** hoặc **notify()** trên object khác với khóa đang bảo vệ trạng thái không?

Nếu cần timeout, thử lấy khóa hoặc khả năng interrupt khi chờ, có thể cân nhắc **ReentrantLock**. Nếu chỉ cần cập nhật một giá trị nguyên tử, **AtomicInteger** hoặc **AtomicLong** có thể phù hợp hơn. Hãy chọn công cụ theo trạng thái và thao tác cần bảo vệ.

## 9. Quy trình xử lý cảnh báo trong dự án

Khi compiler báo **[synchronization]** hoặc **[identity]**, có thể làm theo quy trình:

1. Đọc tên file, số dòng, nhóm lint và biểu thức mà dấu **^** chỉ tới.
2. Xác định kiểu tĩnh và kiểu thực tế của object được dùng làm monitor.
3. Xác định trạng thái mà khối đồng bộ đang bảo vệ và các luồng có thể truy cập trạng thái đó.
4. Chọn khóa **private final Object** cho trạng thái instance hoặc **private static final Object** cho trạng thái static dùng chung.
5. Chuyển tất cả thao tác đọc, ghi và phối hợp **wait/notify** sang cùng giao thức khóa.
6. Biên dịch lại bằng **-Xlint:identity** trên JDK hiện đại hoặc **-Xlint:synchronization** khi làm việc với JDK 16.
7. Chạy kiểm thử đồng thời và kiểm tra lại các invariant, thứ tự lấy khóa và khả năng deadlock.

Không nên xử lý cảnh báo bằng cách tắt lint, đổi sang wrapper khác hoặc thêm **@SuppressWarnings** mà không có phân tích rõ ràng. Mục tiêu là loại bỏ sự phụ thuộc identity không được bảo đảm khỏi thiết kế đồng bộ.

## 10. Kết luận

**-Xlint:synchronization** là tên nhóm cảnh báo được giới thiệu cùng JEP 390 trong JDK 16 để phát hiện việc đồng bộ trên value-based instance. Trong javac hiện đại, **synchronization** là alias deprecated của **identity**; cấu hình mới nên dùng **-Xlint:identity**.

Khi đọc cảnh báo, hãy xác định kiểu của biểu thức khóa, trạng thái được bảo vệ và những luồng cần phối hợp. Sửa bằng object khóa riêng có phạm vi phù hợp, giữ khóa private và final, đồng bộ nhất quán các thao tác đọc ghi, rồi biên dịch và kiểm thử lại. Cách làm này xử lý nguyên nhân của cảnh báo và duy trì thiết kế đồng bộ ổn định trong Java hiện đại.

## Tài liệu tham khảo

- [JEP 390: Warnings for Value-Based Classes](https://openjdk.org/jeps/390)
- [JDK 16 Release Notes — JEP 390](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html)
- [The javac Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/javac.html)
- [The javac Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [Value-based Classes — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/doc-files/ValueBased.html)
- [JLS 27 — Synchronized Statements (Section 14.19)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.19)
- [JLS 27 — Happens-before Order (Section 17.4.5)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html#jls-17.4.5)
- [ReentrantLock — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [AtomicInteger — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)


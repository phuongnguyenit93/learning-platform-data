# Rủi ro dùng đối tượng lớp bao làm khóa đồng bộ

## 1. Khái niệm: synchronized khóa đối tượng, không khóa giá trị số

Trong Java, câu lệnh `synchronized (monitor)` đồng bộ dựa trên monitor gắn với **đối tượng được biểu thức trả về**, không dựa trên kết quả `equals` hay ý nghĩa của giá trị bên trong.

Hai luồng chỉ loại trừ nhau bằng cơ chế này khi chúng dùng cùng một monitor thích hợp cho trạng thái cần bảo vệ.

Lớp bao như `Integer`, `Long`, `Boolean` được dùng để biểu diễn giá trị. Không nên dùng các đối tượng ấy làm khóa đồng bộ:

```java
// Minh họa thiết kế không nên dùng; không phải mẫu đồng bộ an toàn.
Integer lock = 42;

synchronized (lock) {
    // Một thao tác cần bảo vệ.
}
```

Tài liệu Java hiện đại mô tả `Integer` là lớp dựa trên giá trị (value-based class) và yêu cầu không dùng instance để đồng bộ. Đồng nhất một giá trị với một khóa có danh tính ổn định là sai trách nhiệm của đối tượng.

Các ví dụ thay thế trong bài dùng Java 17 trở lên. Chương trình chạy đầy đủ sử dụng khóa riêng và thao tác nguyên tử phù hợp, không dựa vào một cuộc chạy đua dữ liệu để tạo stdout kỳ vọng.

## 2. Vì sao đây không chỉ là vấn đề cú pháp?

Một biểu thức có kiểu tham chiếu có thể được viết ở vị trí monitor. Nhưng “viết được” hoặc “biên dịch được kèm cảnh báo” không chứng minh đó là một thiết kế đồng bộ đúng.

Một khóa phù hợp cần có:

- Danh tính ổn định trong thời gian bảo vệ trạng thái.
- Phạm vi chia sẻ khớp với dữ liệu cần bảo vệ.
- Quyền quản lý rõ ràng, tránh vô tình dùng chung với các thành phần không liên quan.
- Cùng một quy ước khóa cho mọi đường truy cập cần phối hợp.

Đối tượng lớp bao có thể vi phạm những yêu cầu này ngay cả khi giá trị số của nó trông không thay đổi.

Sự bất biến của `Integer` chỉ nói rằng một đối tượng `Integer` không bị sửa thành một số khác. Nó không làm phép tăng một biến tham chiếu trở thành nguyên tử và không tự bảo vệ những trạng thái khác được truy cập trong khối đồng bộ.

## 3. Rủi ro thứ nhất: cache khiến các phần độc lập dùng chung monitor

Boxing hoặc `valueOf` có thể tái sử dụng đối tượng. Ví dụ với hằng số nguyên nhỏ:

```java
// Minh họa trong một phương thức.
Integer lockA = 42;
Integer lockB = 42;

boolean shared = lockA == lockB;
```

Với hai hằng `42` trong ví dụ, kết quả so sánh tham chiếu là `true` theo bảo đảm boxing tương ứng của ngôn ngữ.

Nếu hai thành phần dùng `lockA` và `lockB` làm khóa cho các dữ liệu hoàn toàn độc lập, chúng có thể vô tình khóa cùng một monitor:

- Một thành phần đang giữ khóa sẽ chặn thành phần còn lại.
- Phạm vi phối hợp không còn nằm trong thiết kế của mỗi thành phần.
- Khi kết hợp thêm các khóa khác, sự phụ thuộc ngoài ý muốn có thể làm cách phân tích chờ đợi và thứ tự lấy khóa phức tạp hơn.

Không cần có một lần cấp phát lớp bao mới ở mọi lời gọi. Bộ nhớ đệm là một phần lý do không thể suy ra quyền sở hữu monitor từ việc vừa boxing một giá trị.

### Không khắc phục bằng cách chọn số lớn

Không nên đổi `42` thành một số ngoài vùng cache phổ biến rồi coi khóa là riêng. Việc không nằm trong một vùng được bảo đảm tái sử dụng không tạo ra một hợp đồng “luôn là đối tượng mới và chỉ mình sở hữu”.

Cũng không dùng constructor lớp bao đã lỗi thời để cố tạo một danh tính riêng. Nếu cần đối tượng có danh tính riêng cho khóa, tạo một đối tượng khóa có mục đích đó, chẳng hạn `new Object()`.

### Khóa theo một mã số nghiệp vụ cũng không tự an toàn

Việc hai mã số bằng nhau về giá trị không bảo đảm mọi đối tượng lớp bao của chúng là cùng một monitor. Ngược lại, cache có thể làm một số giá trị tình cờ dùng chung.

Không thiết kế khóa theo mã bằng cách dựa vào `Integer.valueOf(id)`. Nếu bài toán cần khóa theo khóa nghiệp vụ, phải có cơ chế quản lý danh tính và vòng đời khóa rõ ràng; bộ nhớ đệm lớp bao không đảm nhiệm vai trò đó.

## 4. Rủi ro thứ hai: tăng giá trị làm đổi đối tượng khóa

Đây là một mẫu sai thường gặp:

```java
// Khai báo minh họa không an toàn, không dùng trong ứng dụng.
class BrokenCounter {
    private Integer count = 0;

    void increment() {
        synchronized (count) {
            count++;
        }
    }
}
```

`count++` không sửa đối tượng `Integer` hiện tại. Nó lấy giá trị nguyên thủy, tăng giá trị và gán một kết quả lớp bao vào biến `count`.

Cách suy nghĩ theo một lần thực thi:

1. Biểu thức `count` được đánh giá để xác định đối tượng monitor cho lần vào khối hiện tại.
2. Luồng lấy monitor của đối tượng ấy.
3. Trong khối, `count++` gán một tham chiếu biểu diễn giá trị mới cho trường.
4. Các lần đánh giá `count` khác có thể chọn một đối tượng monitor khác.
5. Việc thoát khối hiện tại vẫn nhả monitor đã lấy ở bước trước, không tự chuyển khóa sang đối tượng mới.

Vì các luồng không còn nhất thiết cạnh tranh cùng một monitor, khối `synchronized` không cung cấp sự loại trừ mà người viết định dựa vào. Ngoài ra, việc đọc/ghi chính trường `count` cũng chưa được bảo vệ bởi một giao thức khóa ổn định.

Một lần chạy có thể tình cờ cho kết quả đúng. Một lần khác có thể mất cập nhật hoặc có hành vi phụ thuộc lịch chạy. Không lấy một kết quả tổng cố định của chương trình sai để coi như quy luật.

Đổi thành `Long` hay `Boolean` không giải quyết nguyên nhân. Vấn đề nằm ở việc dùng một đối tượng giá trị có danh tính không được quản lý đúng làm monitor.

## 5. Những cách “sửa” chưa giải quyết đủ vấn đề

### final Integer không tạo quyền sở hữu riêng

```java
// Minh họa thiết kế vẫn không nên dùng.
private final Integer lock = 42;
```

`final` giữ tham chiếu không bị gán lại, nên loại được một dạng đổi monitor. Nó không loại được việc đối tượng ấy do cache chia sẻ với nơi khác và không thay đổi hợp đồng value-based của lớp.

### Đổi kiểu biến thành Object không đổi đối tượng bên dưới

```java
// Minh họa thiết kế vẫn không đúng mục đích.
private final Object lock = Integer.valueOf(42);
```

Kiểu tĩnh `Object` không làm đối tượng `Integer` trở thành một đối tượng khóa riêng mới. Cảnh báo của công cụ có thể thay đổi, nhưng danh tính và vấn đề quyền sở hữu vẫn như cũ.

Cách phù hợp có một khác biệt quan trọng:

```java
// Minh họa trường khóa riêng.
private final Object lock = new Object();
```

Ở đây đối tượng được tạo cho mục đích khóa, không phải tái sử dụng một giá trị số.

### volatile không biến phép tăng thành nguyên tử

Đổi `count` thành `volatile Integer` không làm chuỗi đọc–tăng–gán trở thành một thao tác nguyên tử, cũng không làm các khối đồng bộ trên các đối tượng khác nhau trở thành cùng một monitor.

`volatile` và loại trừ tương hỗ là các cơ chế với mục đích khác nhau. Không dùng một từ khóa bổ sung để bỏ qua việc xác định đúng đối tượng khóa.

### Sửa một đường truy cập là chưa đủ

Nếu `increment` dùng khóa riêng nhưng `get` đọc trường ngoài mọi cơ chế phối hợp, hợp đồng truy cập trạng thái vẫn chưa hoàn chỉnh. Mọi thao tác cần tính nhất quán phải tuân theo cùng giao thức thích hợp.

## 6. Khóa riêng ổn định cho trạng thái của đối tượng

Một bộ đếm có thể dùng:

```java
// Khai báo minh họa an toàn cho các thao tác được cung cấp.
final class GuardedCounter {
    private final Object monitor = new Object();
    private int value;

    void increment() {
        synchronized (monitor) {
            value++;
        }
    }

    int get() {
        synchronized (monitor) {
            return value;
        }
    }
}
```

Ba điểm cần nhìn cùng nhau:

- `monitor` là một đối tượng riêng được tạo cho mỗi `GuardedCounter`.
- Tham chiếu monitor là `private final`, không bị đổi theo giá trị đếm.
- Cả đọc lẫn tăng `value` dùng cùng monitor.

Biến đếm dùng `int` vì nó là trạng thái số cần cập nhật, không cần lớp bao để làm khóa.

Đây là khóa theo **từng đối tượng counter**. Nếu trạng thái cần bảo vệ là `static` và chia sẻ giữa nhiều instance, các khóa riêng của từng instance không tự phối hợp với nhau. Khi đó cần một khóa có phạm vi chia sẻ phù hợp, chẳng hạn một `private static final Object` dùng nhất quán cho trạng thái tĩnh ấy.

Không công khai monitor hoặc gọi mã bên ngoài không rõ hành vi trong khối khóa nếu thiết kế không yêu cầu. Giữ phạm vi khóa và trách nhiệm bảo vệ dữ liệu rõ ràng giúp việc phân tích dễ hơn.

## 7. Khi thao tác đơn lẻ phù hợp với AtomicInteger

Với một bộ đếm chỉ cần tăng nguyên tử và đọc giá trị, có thể dùng `AtomicInteger`:

```java
// Minh họa trường và phương thức; cần import java.util.concurrent.atomic.AtomicInteger.
private final AtomicInteger count = new AtomicInteger();

void increment() {
    count.incrementAndGet();
}

int get() {
    return count.get();
}
```

`AtomicInteger` là công cụ đồng thời có hợp đồng cập nhật nguyên tử, không phải lớp bao `Integer` được tự động làm an toàn.

Không cần dùng chính nó làm monitor để tăng một giá trị bằng API nguyên tử. Cũng không suy ra rằng mọi chuỗi nhiều thao tác trên atomic đều là một giao dịch nguyên tử:

```java
// Minh họa một chuỗi có nhiều bước, không phải thao tác nguyên tử duy nhất.
if (count.get() < limit) {
    count.incrementAndGet();
}
```

Nếu phải giữ một điều kiện qua nhiều bước hoặc phối hợp nhiều trường, cần một thiết kế đồng bộ phù hợp cho toàn bộ quan hệ đó. Không thay mọi khóa bằng atomic theo thói quen.

## 8. Cảnh báo của công cụ và hợp đồng Java hiện đại

Với `javac` hiện đại, có thể kiểm tra cảnh báo đồng bộ trên lớp dựa trên giá trị bằng nhóm lint `synchronization`.

Lưu ví dụ chẩn đoán sau vào `BoxedMonitorWarning.java`:

```java
public class BoxedMonitorWarning {
    private final Integer lock = 42;

    void action() {
        synchronized (lock) {
            System.out.println("diagnostic example");
        }
    }
}
```

Biên dịch bằng JDK 21:

```shell
javac --release 17 -Xlint:synchronization BoxedMonitorWarning.java
```

Trình biên dịch cảnh báo về việc đồng bộ trên một instance của value-based class. Ví dụ chỉ dùng để nhận diện thiết kế sai; không cần chạy nó hoặc coi việc chưa thành lỗi biên dịch là một sự chấp thuận.

Không xử lý cảnh báo bằng cách đổi kiểu biến thành `Object` trong khi vẫn giữ cùng đối tượng lớp bao, và không tắt cảnh báo để tiếp tục dựa vào danh tính của giá trị.

## 9. Chương trình đầy đủ dùng cách thay thế phù hợp

Lưu vào `BoxedLockRisksDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class BoxedLockRisksDemo {
    static final class GuardedCounter {
        private final Object monitor = new Object();
        private int value;

        void increment() {
            synchronized (monitor) {
                value++;
            }
        }

        int get() {
            synchronized (monitor) {
                return value;
            }
        }
    }

    static void runWorkers(Runnable action) throws InterruptedException {
        List<Thread> workers = new ArrayList<>();

        for (int i = 0; i < 4; i++) {
            Thread worker = new Thread(() -> {
                for (int step = 0; step < 10_000; step++) {
                    action.run();
                }
            });
            workers.add(worker);
        }

        for (Thread worker : workers) {
            worker.start();
        }
        for (Thread worker : workers) {
            worker.join();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Integer lockA = 42;
        Integer lockB = 42;
        System.out.println("sharedBox=" + (lockA == lockB));

        Integer value = 0;
        Object before = value;
        value++;
        System.out.println("sameAfterIncrement=" + (before == value));

        GuardedCounter guarded = new GuardedCounter();
        runWorkers(guarded::increment);
        System.out.println("guarded=" + guarded.get());

        AtomicInteger atomic = new AtomicInteger();
        runWorkers(atomic::incrementAndGet);
        System.out.println("atomic=" + atomic.get());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BoxedLockRisksDemo.java
java BoxedLockRisksDemo
```

Stdout chính xác khi chương trình hoàn tất bình thường:

```text
sharedBox=true
sameAfterIncrement=false
guarded=40000
atomic=40000
```

Cách đọc:

1. Hai phép boxing hằng `42` dùng chung đối tượng trong trường hợp được bảo đảm của ví dụ; đây là bằng chứng về khả năng chia sẻ, không phải cách nên viết khóa.
2. Tăng biến lớp bao làm biến trỏ tới đối tượng biểu diễn giá trị khác; tham chiếu cũ không tự đổi theo.
3. Bốn luồng cùng tăng counter bằng khóa riêng ổn định, mỗi luồng `10_000` lần. Sau khi `join` mọi luồng, giá trị là `40_000`.
4. Cùng bài toán bộ đếm được thực hiện bằng thao tác nguyên tử của `AtomicInteger`.

Hai phép so sánh danh tính đầu tiên chỉ dùng để quan sát rủi ro trong bài học; không dùng danh tính lớp bao làm giao thức ứng dụng.

Chương trình không dự đoán một kết quả sai cố định cho `BrokenCounter` và không dùng `sleep` để giả lập sự an toàn. Tính đúng của counter đến từ hợp đồng đồng bộ, không từ việc các luồng tình cờ chạy theo một thứ tự thuận lợi.

## 10. Cách rà soát mã và tự luyện

Khi thấy một biểu thức dùng làm khóa:

1. Xác định đối tượng thực sự, không chỉ kiểu tĩnh của biến.
2. Kiểm tra đối tượng có được tạo riêng cho vai trò khóa hay có thể do cache/factory chia sẻ.
3. Kiểm tra tham chiếu có thể bị gán lại trong quá trình cập nhật hay không.
4. Liệt kê trạng thái được bảo vệ và mọi đường đọc/ghi cần phối hợp.
5. Đối chiếu phạm vi instance/static của khóa với phạm vi chia sẻ trạng thái.
6. Chọn khóa riêng ổn định hoặc một công cụ đồng thời phù hợp với thao tác cần bảo đảm.

Bài tập:

- Vì sao `private final Integer lock = 42` vẫn không trở thành một khóa riêng đáng tin cậy?
- Giải thích vì sao `synchronized (count) { count++; }` có thể không buộc hai lần cập nhật dùng cùng monitor.
- Đổi mẫu sai sang `private final Object monitor = new Object()`, rồi kiểm tra cả phương thức đọc và phương thức ghi.
- Nếu biến đếm là `static` nhưng mỗi instance có một khóa riêng, thiết kế sai ở quan hệ chia sẻ nào?
- Vì sao `volatile Integer` không giải quyết phép tăng đọc–sửa–ghi?
- Khi nào `AtomicInteger.incrementAndGet()` đủ cho yêu cầu, khi nào một chuỗi gồm `get()` rồi tăng vẫn cần thiết kế thêm?
- Dùng lint để tìm một cảnh báo trên khóa lớp bao, rồi sửa đối tượng khóa thay vì chỉ che cảnh báo bằng kiểu `Object`.

## Tài liệu đối chiếu

- [Java API — Integer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html): đặc tính value-based và yêu cầu không dùng instance để đồng bộ.
- [Java API — Value-based Classes](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/doc-files/ValueBased.html): giới hạn về danh tính và quyền sở hữu monitor.
- [Java Language Specification — Synchronization (§17.1)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.1): monitor và loại trừ tương hỗ.
- [Java Language Specification — Boxing (§5.1.7)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.7): bảo đảm chia sẻ trong trường hợp boxing hằng phù hợp.
- [Java API — AtomicInteger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): thao tác cập nhật số nguyên nguyên tử.

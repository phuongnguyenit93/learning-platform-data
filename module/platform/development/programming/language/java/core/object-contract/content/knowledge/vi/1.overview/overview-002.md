# Java `Object`: lớp gốc và các phương thức dùng chung

## 1. Vì sao mọi lớp Java đều liên quan đến `Object`?

`java.lang.Object` là lớp gốc của hệ phân cấp **class** trong Java. Một lớp không khai báo `extends` sẽ trực tiếp kế thừa `Object`; lớp đã `extends` lớp khác thì kế thừa `Object` gián tiếp qua chuỗi cha. Vì vậy, các đối tượng Java đều có một tập phương thức nền tảng để xác định kiểu khi chạy, so sánh, biểu diễn thành chuỗi và phối hợp giữa các luồng.

```java
class Animal { }                 // ngầm extends Object
class Dog extends Animal { }     // gián tiếp kế thừa Object
```

- `Object x = new Dog();` hợp lệ vì một `Dog` cũng là `Object`. Biến `x` có kiểu khai báo `Object` nhưng đối tượng thực tế vẫn là `Dog`.
- `null` không trỏ tới đối tượng nào; gọi phương thức qua tham chiếu `null` gây `NullPointerException`.
- `int`, `boolean` và các kiểu nguyên thủy khác **không** phải đối tượng. Các lớp bao như `Integer`, `Boolean` mới là đối tượng. Mảng là đối tượng và có thể gán cho biến kiểu `Object`.
- `Object` không định nghĩa `compareTo`, `size` hay các thao tác nghiệp vụ. Những khả năng đó thuộc interface/lớp khác hoặc do ứng dụng định nghĩa.

`java.lang` được import tự động, nên không cần viết `import java.lang.Object;`.

## 2. Danh mục phương thức quan trọng

| Phương thức trong `Object` | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `public final Class<?> getClass()` | Lấy kiểu lớp **thực tế lúc chạy** của đối tượng. | `final`: không override được. |
| `public boolean equals(Object obj)` | Kiểm tra hai đối tượng có được xem là bằng nhau hay không. | Mặc định là cùng tham chiếu; nhiều lớp override để so sánh theo giá trị. |
| `public int hashCode()` | Tạo mã băm phục vụ cấu trúc dữ liệu như `HashMap`, `HashSet`. | Phải nhất quán với `equals`; mã băm không phải ID duy nhất. |
| `public String toString()` | Tạo chuỗi mô tả đối tượng. | Nên override để thuận tiện log/debug, không lộ thông tin bí mật. |
| `protected Object clone()` | Cơ chế sao chép đối tượng. | Mặc định sao chép nông; có ràng buộc `Cloneable`; thường nên dùng cách sao chép rõ ràng hơn. |
| `protected void finalize()` | Hook dọn dẹp kiểu cũ trước khi thu gom rác. | Đã deprecated và đang hướng tới loại bỏ; không dựa vào nó để giải phóng tài nguyên. |
| `public final void wait()`, `wait(long)`, `wait(long, int)` | Chờ tín hiệu trên monitor của đối tượng. | Phải sở hữu monitor; `wait` giải phóng monitor đó trong lúc chờ. |
| `public final void notify()`, `notifyAll()` | Đánh thức một hoặc mọi luồng đang `wait` trên cùng monitor. | Không bàn giao khóa ngay; luồng tỉnh phải lấy lại monitor. |

`Object` còn có constructor công khai `Object()`; constructor không phải phương thức được override. Phần lớn ứng dụng gọi các phương thức trong bảng qua lớp con chứ hiếm khi tạo `new Object()` để biểu diễn dữ liệu nghiệp vụ.

## 3. `==`, `equals()` và khái niệm bằng nhau

Với **tham chiếu đối tượng**, `a == b` hỏi hai biến có trỏ đúng **cùng một đối tượng** không. Trong khi đó, `a.equals(b)` hỏi hai đối tượng có **bằng nhau theo quy tắc của lớp** hay không.

Triển khai mặc định của `Object.equals` tương đương kiểm tra `this == obj`. Vì thế, nếu một lớp không override, hai đối tượng khác nhau vẫn không bằng nhau dù các trường có cùng giá trị. Các lớp như `String`, lớp bao số và các `record` có quy tắc so sánh giá trị riêng.

```java
String first = new String("Java");
String second = new String("Java");
System.out.println(first == second);      // false: hai đối tượng khác nhau
System.out.println(first.equals(second)); // true: cùng nội dung
```

Đừng dùng `==` để so sánh **nội dung** của `String` hoặc đối tượng giá trị. Việc một số chuỗi literal có thể được intern không biến `==` thành phép so sánh nội dung.

### Hợp đồng khi override `equals`

Với các tham chiếu khác `null`, quan hệ bằng nhau hợp lệ phải có:

1. **Phản xạ:** `x.equals(x)` là `true`.
2. **Đối xứng:** `x.equals(y)` và `y.equals(x)` cho cùng kết quả.
3. **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
4. **Nhất quán:** các lần so sánh cho cùng kết quả nếu trạng thái tham gia so sánh không đổi.
5. **So với null:** `x.equals(null)` là `false`.

Override đúng chữ ký `equals(Object)`, dùng `@Override` để trình biên dịch phát hiện sai sót. Viết `equals(MyType)` chỉ **overload**, không thay thế `Object.equals(Object)`.

Khi thiết kế phân cấp lớp có thể kế thừa và bổ sung trạng thái, phải đặc biệt cẩn thận để không phá tính đối xứng/bắc cầu. Với đối tượng giá trị, một lớp `final` bất biến hoặc `record` thường giúp quy tắc đơn giản và an toàn hơn.

## 4. Hợp đồng `hashCode()` đi kèm `equals()`

Quy tắc bắt buộc: **nếu `a.equals(b)` là `true`, thì `a.hashCode() == b.hashCode()` phải là `true`.** Chiều ngược lại không đúng: hai đối tượng không bằng nhau vẫn có thể trùng mã băm (*collision*). Nếu cùng một đối tượng không đổi trạng thái liên quan đến `equals`, mã băm phải ổn định trong các lần gọi trong cùng quá trình chạy theo hợp đồng API.

`HashMap` và `HashSet` dùng `hashCode` để tìm nhóm ứng viên, sau đó dùng `equals` để phân biệt phần tử. Override `equals` nhưng quên `hashCode` có thể làm tập hợp nhận hai phần tử được xem là bằng nhau, hoặc không tìm được khóa tương đương.

- Tính hash từ đúng các thuộc tính mà `equals` sử dụng. Có thể viết `Objects.hash(field1, field2)` cho dễ đọc; lưu ý cách này có thể tạo thêm chi phí so với công thức trực tiếp.
- Đừng coi `hashCode` là mã định danh duy nhất, vị trí bộ nhớ hay giá trị ổn định giữa hai lần chạy JVM.
- Tránh thay đổi các trường tham gia `equals/hashCode` khi đối tượng đang là khóa của `HashMap` hoặc phần tử `HashSet`: sau khi thay đổi, cấu trúc có thể không tìm thấy nó theo mã băm mới.
- Khi cần hash dựa trên **định danh đối tượng** bất kể lớp đã override `hashCode`, có `System.identityHashCode(obj)`; hàm này cũng không bảo đảm duy nhất.

## 5. Ví dụ Java 17+: override đúng ba phương thức phổ biến

Tạo tệp `ObjectDemo.java` với toàn bộ nội dung sau:

```java
import java.util.HashSet;
import java.util.List;

public class ObjectDemo {
    static final class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Point other)) {
                return false;
            }
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return 31 * x + y;
        }

        @Override
        public String toString() {
            return "Point[x=" + x + ", y=" + y + "]";
        }
    }

    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);

        System.out.println("==: " + (a == b));
        System.out.println("equals: " + a.equals(b));
        System.out.println("same hash: " + (a.hashCode() == b.hashCode()));
        System.out.println("HashSet size: " + new HashSet<>(List.of(a, b)).size());
        System.out.println("toString: " + a);
        System.out.println("runtime class: " + a.getClass().getSimpleName());
    }
}
```

Chạy:

```bash
javac ObjectDemo.java
java ObjectDemo
```

Kết quả:

```text
==: false
equals: true
same hash: true
HashSet size: 1
toString: Point[x=2, y=3]
runtime class: Point
```

**Giải thích:** `a` và `b` được tạo bằng hai lệnh `new`, nên khác tham chiếu. Chúng bằng nhau theo cặp tọa độ `x/y` và có cùng mã băm, vì vậy `HashSet` chỉ giữ một giá trị tương đương. `final` ở lớp và trường khiến ví dụ tránh vấn đề thay đổi trạng thái hay lớp con sửa quy tắc so sánh. Công thức `31 * x + y` có thể trùng hash cho các điểm khác nhau nhưng không vi phạm hợp đồng.

## 6. Hiểu chính xác `getClass()` và `toString()`

### `getClass()`: kiểu tại runtime

```java
Object value = "hello";
System.out.println(value.getClass() == String.class); // true
```

Kiểu khai báo là `Object` nhưng kiểu thực tế là `String`. `getClass()` trả về đối tượng `Class` dùng trong reflection. Đừng nhầm `value.getClass() == SomeClass.class` (đúng **chính xác lớp đó**) với `value instanceof SomeClass` (chấp nhận cả lớp con hoặc lớp hiện thực interface). Với biến `null`, không thể gọi `getClass()`.

### `toString()`: bản mô tả hữu ích cho con người

Mặc định `Object.toString()` tạo chuỗi dạng tên lớp + `@` + biểu diễn thập lục phân của `hashCode()`, chẳng hạn `mypackage.Point@1a2b3c`; phần hex **không nhất thiết** là địa chỉ bộ nhớ hay identity hash nếu lớp đã override `hashCode`.

Override `toString()` để thể hiện các trường cần cho quan sát, ví dụ `Point[x=2, y=3]`. Ghép đối tượng với chuỗi hay gọi `System.out.println(obj)` thường dẫn đến biểu diễn `toString()` (với `null`, cách chuyển đổi chuỗi cho ra `"null"`). Không in mật khẩu, token, dữ liệu nhạy cảm hoặc những cấu trúc có thể đệ quy vô hạn.

## 7. `wait()`, `notify()`, `notifyAll()`: phối hợp qua monitor

Mỗi đối tượng có một monitor/khóa nội tại dùng bởi `synchronized`. Các phương thức `wait`/`notify` của `Object` thao tác với **monitor của chính đối tượng nhận lệnh**. Chúng là cơ chế nền tảng cho việc chờ điều kiện giữa các luồng; đây không phải cách thường dùng cho code ứng dụng mới nếu có thể sử dụng các tiện ích `java.util.concurrent` phù hợp.

- `wait()`: luồng phải đang giữ monitor của đối tượng; khi chờ sẽ **thả monitor đó** để luồng khác có thể thay đổi điều kiện. Khi được đánh thức, luồng phải giành lại monitor trước khi tiếp tục.
- `notify()`: đánh thức một luồng đang chờ trên cùng đối tượng, không có bảo đảm chọn luồng nào.
- `notifyAll()`: đánh thức mọi luồng đang chờ trên đối tượng; chúng vẫn phải lần lượt giành lại khóa và kiểm tra điều kiện.
- Gọi các phương thức này khi chưa sở hữu monitor tương ứng sẽ ném `IllegalMonitorStateException`. Thông thường bọc trong `synchronized (lock)` hoặc phương thức `synchronized` trên chính `lock`.
- Luôn gọi `wait` trong vòng `while` kiểm tra điều kiện vì có thể có *spurious wakeup*, bị đánh thức khi điều kiện chưa đúng hoặc điều kiện đã bị luồng khác thay đổi. Với `wait(long timeout)`, giá trị `0` có nghĩa chờ vô thời hạn; lời gọi có thời hạn cũng cần kiểm tra lại điều kiện.
- `wait` có thể ném `InterruptedException`. Xử lý đúng mục đích: truyền ra ngoài, hoặc khôi phục cờ interrupt nếu bắt lỗi nhưng không thể ném tiếp. `Thread.sleep` **không** tự giải phóng monitor đang giữ.

Ví dụ một hộp thư một ô. Tạo tệp độc lập `MonitorDemo.java`:

```java
public class MonitorDemo {
    static final class Mailbox {
        private String message;

        synchronized void put(String value) throws InterruptedException {
            while (message != null) {
                wait();
            }
            message = value;
            notifyAll();
        }

        synchronized String take() throws InterruptedException {
            while (message == null) {
                wait();
            }
            String value = message;
            message = null;
            notifyAll();
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Mailbox mailbox = new Mailbox();

        Thread consumer = new Thread(() -> {
            try {
                System.out.println("Nhận: " + mailbox.take());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        mailbox.put("hello");
        consumer.join();
    }
}
```

```bash
javac MonitorDemo.java
java MonitorDemo
```

Stdout của lần chạy bình thường:

```text
Nhận: hello
```

Dù producer hay consumer chạy trước, `while` bảo vệ điều kiện `message` và các lời gọi `wait/notifyAll` diễn ra khi giữ monitor của cùng một `Mailbox`. Đây là ví dụ học cơ chế; trong sản phẩm, `BlockingQueue`, `Lock`/`Condition` hoặc các công cụ concurrency cấp cao thường rõ ràng và dễ bảo trì hơn.

## 8. `clone()` và `finalize()`: nên biết giới hạn

### `clone()` thường là sao chép nông

`Object.clone()` có quyền truy cập `protected`; lớp muốn công khai cơ chế clone thường override, gọi `super.clone()` và thực hiện `Cloneable`. Nếu đối tượng không hỗ trợ `Cloneable`, cơ chế clone mặc định báo `CloneNotSupportedException` (mảng có quy tắc clone riêng). Sao chép nông tạo đối tượng mới nhưng các trường tham chiếu vẫn có thể trỏ tới **cùng đối tượng con**.

Ví dụ một đối tượng chứa `List<String>`: nếu clone nông, hai bản có thể cùng dùng một `List`; thay đổi danh sách của bản sao ảnh hưởng bản gốc. Muốn độc lập phải chủ động sao chép các thành phần cần thiết. `Cloneable` cũng không cung cấp sẵn một phương thức `clone()` public trong chính interface.

Trong thiết kế ứng dụng, constructor sao chép, factory hoặc kiểu giá trị bất biến thường diễn đạt ý định tốt hơn `clone()`. Không được mặc định rằng `clone` là deep copy.

### `finalize()` không dành cho quản lý tài nguyên

`finalize()` là cơ chế cũ đã bị deprecate, được định hướng loại bỏ. Không có bảo đảm nó chạy kịp thời hoặc chạy trước khi chương trình kết thúc; lạm dụng còn gây rủi ro hiệu năng và độ tin cậy. **Không sử dụng `finalize()` để đóng file, socket, kết nối hay giải phóng tài nguyên quan trọng.** Thay vào đó, dùng `AutoCloseable` và `try-with-resources`:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    // đọc dữ liệu từ reader; reader sẽ được đóng khi rời khối
}
```

Đoạn trên minh họa cú pháp khi `path` đã là một `java.nio.file.Path`; nó không phải chương trình độc lập. Việc thu gom bộ nhớ do GC đảm trách; đóng tài nguyên hệ điều hành là trách nhiệm cần thể hiện rõ trong logic ứng dụng.

## 9. Phân biệt `Object`, `Objects` và `record`

`java.util.Objects` là **lớp tiện ích** (khác `java.lang.Object`) cung cấp các phương thức tĩnh như `Objects.equals(a, b)`, `Objects.hash(...)`, `Objects.requireNonNull(value)` và `Objects.toString(value)`. `Objects.equals(a, b)` an toàn với `null`; còn `a.equals(b)` ném lỗi nếu `a == null`.

Với mô hình dữ liệu đơn giản, `record` (Java 16+) tự sinh `equals`, `hashCode` và `toString` dựa trên các thành phần record:

```java
record Position(int x, int y) {}
```

`new Position(2, 3).equals(new Position(2, 3))` là `true`. Record không cho phép gán lại các component, nhưng nếu component chứa một đối tượng mutable (ví dụ danh sách), chính đối tượng đó vẫn có thể thay đổi; vì vậy hãy cân nhắc bất biến sâu khi dùng record làm khóa băm. Record là lựa chọn hợp lý cho nhiều kiểu dữ liệu giá trị, nhưng không thay thế mọi lớp có hành vi nghiệp vụ.

## 10. Những lỗi phổ biến và checklist áp dụng

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| So sánh nội dung đối tượng bằng `==`. | Nhầm định danh với giá trị. | Dùng `equals` theo hợp đồng lớp; với giá trị có thể `null`, dùng `Objects.equals`. |
| Override `equals` mà không override `hashCode`. | `HashMap`/`HashSet` hành xử không đúng kỳ vọng. | Cập nhật hai phương thức cùng nhau và kiểm thử bằng các đối tượng tương đương. |
| Chỉ viết `equals(MyClass)` mà thiếu `equals(Object)`. | Không override; collection vẫn gọi bản từ `Object`. | Viết đúng chữ ký, luôn thêm `@Override`. |
| Thay đổi trường dùng tính hash của một khóa đã lưu. | Tra cứu hoặc xóa khóa có thể thất bại. | Dùng giá trị bất biến cho khóa hoặc tránh đổi trạng thái liên quan. |
| Coi `hashCode` là ID duy nhất hoặc địa chỉ bộ nhớ. | Nhận diện sai đối tượng khi có collision. | Sử dụng khóa/ID nghiệp vụ rõ ràng. |
| Gọi `wait` ngoài monitor hoặc dùng `if` thay `while`. | `IllegalMonitorStateException` hoặc lỗi tranh chấp. | Đồng bộ đúng đối tượng và kiểm tra lại điều kiện trong vòng lặp. |
| Nghĩ `notify` nhường khóa ngay. | Suy luận sai thứ tự thực thi giữa các luồng. | Hiểu luồng tỉnh phải chờ lấy lại monitor. |
| Cho rằng `clone` sao chép sâu hoặc `finalize` luôn chạy. | Chia sẻ trạng thái ngoài ý muốn hoặc rò rỉ tài nguyên. | Sao chép tường minh; dùng `try-with-resources`. |

**Tự kiểm tra kiến thức:**

1. Vì sao hai đối tượng mới tạo có thể `equals == true` nhưng `== false`?
2. Tại sao đối tượng bằng nhau bắt buộc có cùng hash, nhưng cùng hash chưa chắc bằng nhau?
3. Khi một luồng gọi `lock.wait()`, nó giải phóng khóa nào? Vì sao phải dùng `while`?
4. `getClass()` khác kiểm tra `instanceof` thế nào khi có kế thừa?
5. Vì sao copy constructor hoặc record có thể phù hợp hơn `clone()`/lớp mutable trong mô hình giá trị?

Ghi nhớ: `Object` đặt nền tảng chung cho các lớp Java; khi override, điều quan trọng nhất là **tuân thủ hợp đồng `equals`/`hashCode`, biểu diễn `toString` phù hợp và hiểu đúng monitor khi dùng `wait`/`notify`**.
# Đồng bộ từng phương thức không bảo đảm nguyên tử cho cả chuỗi thao tác với `StringBuffer`

`StringBuffer` là lớp dựng chuỗi **mutable** của Java, có các phương thức chính như `append()`, `insert()`, `delete()`, `length()` và `toString()` được đồng bộ hóa để hỗ trợ truy cập từ nhiều luồng. Tuy nhiên, một lỗi thiết kế rất thường gặp là cho rằng: **“Vì các lời gọi `StringBuffer` được đồng bộ, toàn bộ các lệnh liên tiếp của mình cũng tự động là một thao tác nguyên tử.”**

Điều đó **không đúng**.

Một lời gọi `append("A")` có thể được bảo vệ bởi khóa của `StringBuffer` trong thời gian phương thức thực hiện; nhưng sau khi lời gọi kết thúc, luồng khác có thể vào và sửa buffer **trước khi lời gọi tiếp theo của bạn bắt đầu**. Vì vậy, các thao tác kiểu **kiểm tra rồi sửa**, **đọc rồi xóa**, **ghép nhiều đoạn cần liền nhau** hoặc **kiểm tra nhiều điều kiện của cùng một trạng thái** cần được đồng bộ hóa như một **đơn vị logic**.

**Thông điệp cốt lõi:** *thread-safe ở cấp phương thức không tự động bảo đảm atomicity ở cấp quy trình nhiều phương thức.*

## 1. Ba khái niệm cần phân biệt

### Thread-safe ở cấp lời gọi

Một lời gọi đơn lẻ được thiết kế để nhiều luồng có thể sử dụng mà không làm hỏng trạng thái bên trong đối tượng. Ví dụ, hai luồng cùng `append()` vào một `StringBuffer` sẽ không có kiểu truy cập bộ đệm không được đồng bộ như khi cùng sửa một `StringBuilder`.

Điều này **không bảo đảm** thứ tự toàn cục mà lập trình viên mong muốn. Nếu hai luồng cùng thêm `"A"` và `"B"`, thứ tự phụ thuộc lịch chạy; kết quả có thể là `"AB"` hoặc `"BA"` nếu cả hai lần thêm đều thành công.

### Atomicity ở cấp một thao tác logic

Một thao tác *nguyên tử* là thao tác được quan sát như một đơn vị không bị xen ngang bởi các thao tác cạnh tranh vào cùng trạng thái. Nếu yêu cầu nghiệp vụ là “**chỉ thêm X nếu buffer đang rỗng**”, hai bước:

1. Đọc `buffer.length() == 0`.
2. Gọi `buffer.append("X")`.

phải được thực hiện trong **cùng một vùng tới hạn** (*critical section*). Hai bước tách rời, dù mỗi bước tự đồng bộ, **không** tạo thành một thao tác nguyên tử.

### Invariant — điều kiện luôn phải đúng

*Invariant* là điều kiện trên trạng thái mà chương trình phải duy trì, chẳng hạn “chỉ tồn tại một tiêu đề”, “mỗi bản ghi gồm prefix và suffix không xen lẫn”, “nếu buffer còn dữ liệu mới được xóa ký tự cuối”.

Khóa chỉ có ý nghĩa khi nó bảo vệ **đủ toàn bộ thao tác để invariant vẫn đúng**. Nếu chỉ khóa từng lời gọi nhỏ mà để luồng khác sửa trạng thái giữa các bước, invariant có thể bị phá vỡ.

## 2. Vì sao `StringBuffer` được coi là thread-safe?

`StringBuffer` có thiết kế đồng bộ các phương thức chính để các thao tác trên một instance không làm xung đột việc truy cập bộ đệm khi nhiều luồng cùng sử dụng. Nhiều thao tác sử dụng khóa màn hình nội tại (*intrinsic monitor*) của chính đối tượng `StringBuffer`, tương đương về mặt sử dụng khóa với `synchronized (buffer)` của phía gọi.

Ví dụ:

```java
StringBuffer buffer = new StringBuffer();

buffer.append("A");
buffer.append("B");
```

Mỗi lời gọi `append()` có thể thực hiện an toàn riêng lẻ. Nhưng giữa lúc lời gọi đầu kết thúc và lời gọi thứ hai bắt đầu, luồng khác vẫn có thể gọi `append()` hoặc thay đổi buffer.

Không có hợp đồng nào nói rằng hai lệnh Java liên tiếp ở cùng một luồng luôn giữ khóa xuyên suốt cả hai lời gọi.

Một cách mô tả lịch xen kẽ hợp lệ:

```text
Luồng 1                    Luồng 2
-------                    -------
append("A")  [xong]
                           append("X")  [xong]
append("B")  [xong]

Nội dung cuối: "AXB"
```

Không có lời gọi `append()` đơn lẻ nào bị thực hiện “nửa chừng”; nhưng **kết quả tổng thể không phải `"ABX"`** như người viết Luồng 1 có thể kỳ vọng.

Các thao tác synchronized giúp bảo vệ lần vào/ra phương thức, **không tự biến toàn bộ khối lệnh bên ngoài thành một transaction**.

## 3. Lỗi thứ nhất: *check-then-act* (kiểm tra rồi mới thực hiện)

Xét một quy tắc tưởng chừng đơn giản: **chỉ thêm ký hiệu `"X"` nếu buffer đang rỗng**.

```java
// Fragment minh họa cách làm SAI khi nhiều luồng cạnh tranh:
if (buffer.length() == 0) {
    buffer.append("X");
}
```

`length()` và `append()` riêng lẻ được bảo vệ, nhưng có thể xảy ra lịch:

```text
Ban đầu: buffer = ""

Luồng A: length() == 0   → true
Luồng B: length() == 0   → true
Luồng A: append("X")     → buffer = "X"
Luồng B: append("X")     → buffer = "XX"

Kết quả: "XX", vi phạm yêu cầu "chỉ thêm một lần".
```

Mỗi luồng đều đưa ra quyết định từ một **ảnh chụp trạng thái đã có thể lỗi thời** khi đến lúc thực hiện hành động. Đây là lỗi *time-of-check to time-of-use* (TOCTOU) ở mức trạng thái chia sẻ.

### Sửa bằng một vùng `synchronized` bao quanh cả kiểm tra lẫn thay đổi

```java
synchronized (buffer) {
    if (buffer.length() == 0) {
        buffer.append("X");
    }
}
```

Ở đây, luồng nắm giữ monitor của `buffer` **trong suốt** việc kiểm tra và `append`. Một luồng khác muốn chạy các phương thức `StringBuffer` sử dụng cùng monitor phải đợi vùng tới hạn kết thúc.

Sự đồng bộ hóa là **tái nhập (*reentrant*)**: khi đã giữ khóa của `buffer` ở khối `synchronized(buffer)`, luồng hiện tại vẫn có thể gọi các phương thức `synchronized` của chính `buffer`. Khóa không tự gây deadlock chỉ vì luồng giữ nó rồi gọi phương thức đồng bộ trên cùng đối tượng.

**Điều kiện bảo đảm:** mọi đường thay đổi trạng thái liên quan phải tôn trọng cùng quy tắc đồng bộ; nếu có dữ liệu liên quan nằm ở đối tượng khác hoặc thư viện tự ý sửa theo cách không tham gia khóa, phải mở rộng thiết kế bảo vệ phù hợp.

## 4. Ví dụ Java 17+ chạy độc lập, kết quả đa luồng được điều phối rõ ràng

Để tránh một ví dụ race condition “lúc chạy ra, lúc không”, chương trình dưới đây sử dụng `CountDownLatch` để **buộc cả hai luồng cùng kiểm tra trạng thái rỗng trước khi bất kỳ luồng nào được phép append**. Vì vậy đầu ra của trường hợp sai có thể dự đoán được.

Tạo tệp `StringBufferAtomicityDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class StringBufferAtomicityDemo {
    private static String unsafeCheckThenAppend()
            throws InterruptedException {
        StringBuffer buffer = new StringBuffer();
        CountDownLatch bothChecked = new CountDownLatch(2);
        CountDownLatch proceed = new CountDownLatch(1);

        Runnable task = () -> {
            boolean wasEmpty = buffer.length() == 0;
            bothChecked.countDown();

            try {
                proceed.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            if (wasEmpty) {
                buffer.append("X");
            }
        };

        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();

        bothChecked.await(); // Hai luồng đã thấy buffer rỗng.
        proceed.countDown(); // Cho phép cả hai cùng append.
        first.join();
        second.join();

        return buffer.toString();
    }

    private static String atomicCheckThenAppend()
            throws InterruptedException {
        StringBuffer buffer = new StringBuffer();

        Runnable task = () -> {
            synchronized (buffer) {
                if (buffer.length() == 0) {
                    buffer.append("X");
                }
            }
        };

        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        return buffer.toString();
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println(
                "nonAtomic = " + unsafeCheckThenAppend());
        System.out.println(
                "atomic = " + atomicCheckThenAppend());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac StringBufferAtomicityDemo.java
java StringBufferAtomicityDemo
```

Kết quả khi không có ngắt luồng ngoài ý muốn:

```text
nonAtomic = XX
atomic = X
```

**Tại sao kết quả xác định?**

- Trong `unsafeCheckThenAppend()`, mỗi luồng lưu `wasEmpty = true` từ trạng thái ban đầu. `bothChecked` chỉ mở cho luồng chính khi **cả hai** đã hoàn tất kiểm tra; `proceed` chặn việc append cho đến thời điểm đó. Vì thế cả hai đều `append("X")` và kết quả chắc chắn là `"XX"`, không phụ thuộc thứ tự ai append trước.
- Trong `atomicCheckThenAppend()`, luồng đầu vào vùng `synchronized(buffer)` kiểm tra chuỗi rỗng rồi append. Luồng còn lại chỉ có thể vào sau khi luồng đầu nhả monitor; lúc đó `length() != 0`, nên không append thêm. Kết quả là `"X"`.
- `Thread.join()` giúp luồng chính đợi hai luồng hoàn thành trước khi in nội dung buffer. Chỉ gọi `toString()` khi chưa đợi các luồng xong sẽ không bảo đảm đó là trạng thái cuối cùng.

**Lưu ý:** chương trình dùng `CountDownLatch` để minh họa lỗi có kiểm soát. Trong ứng dụng thực tế, cùng một race có thể xuất hiện ngẫu nhiên khi lịch chạy tình cờ khiến hai lần kiểm tra xảy ra trước cả hai lần ghi.

## 5. Lỗi thứ hai: nhiều `append()` tạo một bản ghi nhưng bị xen kẽ

Giả sử muốn tạo hai bản ghi độc lập `"[A]"` và `"[B]"` trong một buffer dùng chung.

```java
// Fragment minh họa: mỗi luồng có thể chạy đoạn này với id khác nhau.
buffer.append("[");
buffer.append(id);
buffer.append("]");
```

Mỗi `append()` riêng lẻ có thể an toàn, nhưng ba lời gọi **không được bảo đảm liền nhau**. Một lịch có thể tạo ra:

```text
Luồng A: append("[")   → "["
Luồng B: append("[")   → "[["
Luồng B: append("B")   → "[[B"
Luồng A: append("A")   → "[[BA"
Luồng A: append("]")   → "[[BA]"
Luồng B: append("]")   → "[[BA]]"
```

Kết quả `"[[BA]]"` không chứa hai bản ghi nguyên vẹn theo định dạng đã định, dù không phương thức `append()` nào thực hiện sai.

### Giải pháp 1: dùng một lời gọi `append()` cho bản ghi đã hoàn chỉnh

Nếu dễ tạo bản ghi ngắn độc lập, có thể dựng riêng trước:

```java
String record = "[" + id + "]";
buffer.append(record);
```

Lúc này việc thêm *một chuỗi kết quả đã hoàn chỉnh* vào buffer diễn ra qua một lời gọi `append(String)`. Các bản ghi khác có thể nằm trước hoặc sau bản ghi này, nhưng không chen giữa các phần nội dung của **một lời gọi append** trên cùng `StringBuffer`.

Cách này thường rõ ràng khi mỗi bản ghi nhỏ; nó có chi phí tạo `String` bản ghi riêng.

### Giải pháp 2: khóa cả quy trình thêm nhiều phần

```java
synchronized (buffer) {
    buffer.append("[");
    buffer.append(id);
    buffer.append("]");
}
```

Khối ngoài giữ monitor của `buffer` xuyên suốt cả ba lời gọi. Nếu các luồng cùng dùng buffer và cùng tuân theo monitor đó, nội dung bản ghi không bị xen lẫn bởi lời gọi cạnh tranh trên cùng buffer.

**Chú ý:** chuỗi gọi phương thức kiểu `buffer.append("[").append(id).append("]")` trông như một câu lệnh Java, nhưng nó vẫn gồm **nhiều lời gọi `append()` riêng biệt**. Một câu lệnh Java hay một chain fluent không đồng nghĩa một thao tác nguyên tử.

## 6. Đọc nhiều lần cũng có thể bị lỗi: *read-modify-write* và chỉ số thay đổi

Khi một luồng đọc trạng thái rồi quyết định sửa dựa theo kết quả, mọi giá trị đã đọc có thể trở nên lỗi thời nếu buffer thay đổi giữa các lời gọi.

Ví dụ: “xóa ký tự cuối nếu chuỗi không rỗng”.

```java
// Fragment SAI khi có luồng khác sửa cùng buffer:
if (buffer.length() > 0) {
    buffer.deleteCharAt(buffer.length() - 1);
}
```

Luồng A thấy chiều dài dương. Trước khi nó tính chỉ số hoặc xóa, luồng B có thể xóa hết nội dung. Khi A gọi `deleteCharAt()`, vị trí có thể không còn hợp lệ và Java có thể ném `StringIndexOutOfBoundsException`.

Ngay cả khi không ném ngoại lệ, A có thể xóa **ký tự khác** với ý định ban đầu vì nội dung đã bị thay đổi. Việc mỗi lời gọi có khóa không làm một giá trị đọc trước đó được cập nhật tự động.

Sửa bằng một vùng tới hạn:

```java
synchronized (buffer) {
    int length = buffer.length();
    if (length > 0) {
        buffer.deleteCharAt(length - 1);
    }
}
```

Bây giờ việc đọc chiều dài, tính chỉ số và xóa đều nằm trong **một giao dịch logic được khóa**. Điều kiện `length > 0` còn đúng trong suốt phần cần bảo vệ đối với các tác nhân cùng tuân theo khóa buffer.

### Trường hợp đọc một snapshot nhất quán

Với nhu cầu lấy **một snapshot văn bản** ở thời điểm cụ thể, lời gọi `buffer.toString()` trả về một `String` độc lập, bất biến. Nhưng các lời gọi tách biệt vẫn có thể cho các thời điểm khác nhau:

```java
int before = buffer.length();
// Luồng khác có thể append/delete ở đây.
String snapshot = buffer.toString();
```

`before` không nhất thiết bằng `snapshot.length()`. Nếu yêu cầu hai giá trị phải cùng phản ánh **một trạng thái**, hãy lấy chúng trong cùng vùng `synchronized(buffer)` hoặc chỉ dựa trên snapshot:

```java
String snapshot = buffer.toString();
int snapshotLength = snapshot.length();
```

Ở ví dụ sau, `snapshotLength` chắc chắn là độ dài của chính chuỗi snapshot vì `String` bất biến. Chúng không nhất thiết đại diện cho trạng thái buffer ở **thời điểm sau đó**.

## 7. Dùng đúng monitor: mọi thành phần phải cùng quy tắc khóa

Cách đơn giản khi quản lý độc quyền một buffer chia sẻ:

```java
private final StringBuffer shared = new StringBuffer();

public void appendEntry(String entry) {
    synchronized (shared) {
        shared.append("<").append(entry).append(">");
    }
}
```

Đây là **fragment đặt trong một lớp**, không phải chương trình chạy độc lập. `shared` được khởi tạo một lần rồi dùng như monitor thống nhất. Các phương thức khác thực hiện những quy trình phụ thuộc trạng thái của cùng buffer cũng phải chọn một quy ước đồng bộ tương thích.

Một lựa chọn thiết kế khác là dùng **khóa riêng**, nhất là khi muốn bảo vệ thêm trạng thái khác ngoài buffer:

```java
private final Object lock = new Object();
private final StringBuffer buffer = new StringBuffer();
private int entryCount;

public void appendEntry(String entry) {
    synchronized (lock) {
        buffer.append("<").append(entry).append(">");
        entryCount++;
    }
}
```

Trong thiết kế này, **mọi đường đọc/sửa cặp `buffer` và `entryCount` phải đi qua `lock`** nếu invariant của chúng cần tính nguyên tử. Khóa `lock` là khóa **khác** monitor nội tại của `buffer`, nên không được tưởng rằng các lời gọi trực tiếp `buffer.append()` ở nơi khác sẽ tự động tôn trọng khóa riêng đó. Giữ hai trường `private` và chỉ truy cập qua những phương thức của lớp sẽ giúp quản lý quy tắc khóa.

Tránh lẫn lộn:

- `synchronized(buffer)` và `synchronized(lock)` không bảo vệ cùng một vùng tới hạn nếu `lock != buffer`.
- `synchronized(this)` có thể phù hợp khi đối tượng bao bọc dùng `this` làm khóa nhất quán, nhưng không tự khóa monitor của một buffer khác.
- Khai báo biến tham chiếu `final StringBuffer buffer` chỉ cấm gán lại biến; **không** biến các chuỗi thao tác nhiều bước thành nguyên tử.
- Khai báo trường tham chiếu `volatile StringBuffer buffer` chủ yếu liên quan đến khả năng nhìn thấy thay đổi **tham chiếu**; nó không thay thế khóa để bảo vệ một quy trình đọc-rồi-sửa nội dung buffer.

## 8. Thế nào là “bảo vệ đủ phạm vi”?

Hãy xác định thao tác logic ở mức nghiệp vụ, rồi bảo vệ toàn bộ phần phụ thuộc trạng thái chung.

| Yêu cầu logic | Các lời gọi có thể cần gộp dưới cùng khóa | Rủi ro nếu tách khóa |
| --- | --- | --- |
| Chỉ thêm tiêu đề một lần | Kiểm tra `length() == 0` rồi `append(header)` | Hai luồng cùng thấy rỗng, thêm trùng. |
| Một bản ghi luôn liền mạch | `append(prefix)`, `append(body)`, `append(suffix)` | Nội dung hai bản ghi bị xen kẽ. |
| Xóa ký tự cuối nếu tồn tại | `length()`, kiểm tra điều kiện, `deleteCharAt()` | Chỉ số lỗi thời, xóa sai hoặc exception. |
| Đọc nhiều thuộc tính của cùng snapshot | `length()`, `charAt()` hoặc lấy một `toString()` rồi phân tích snapshot | Các phép đọc có thể từ nhiều thời điểm. |
| Cập nhật buffer đồng thời bộ đếm | `append()` và `entryCount++` | Buffer và counter không còn nhất quán. |
| Kiểm tra không có dữ liệu rồi ghi marker | `indexOf()` hoặc `toString()` để kiểm tra, sau đó `append()` | Hai luồng cùng quyết định dựa trên cùng trạng thái cũ. |

**Đừng giữ khóa rộng hơn cần thiết.** Ví dụ gọi network, đọc file chậm, chờ thao tác người dùng hoặc xử lý nặng bên trong `synchronized(buffer)` có thể khiến các luồng khác phải chờ lâu.

Một mẫu tốt là **chuẩn bị dữ liệu bất biến ngoài khóa**, sau đó giữ khóa chỉ đủ lâu để kiểm tra điều kiện chung và áp dụng cập nhật:

```java
String record = "[" + value + "]"; // Chuẩn bị trước.
synchronized (buffer) {
    // Kiểm tra thêm invariant, nếu có.
    buffer.append(record);
}
```

Khi chỉ cần thêm một bản ghi hoàn chỉnh và không có điều kiện khác, `buffer.append(record)` đơn lẻ đã có khóa ở cấp phương thức; không nhất thiết cần thêm vùng `synchronized` ngoài. Khóa ngoài cần thiết khi **quy trình có nhiều bước liên quan phải được thực hiện cùng nhau**.

## 9. Ví dụ Java 17+ thứ hai: xen kẽ nhiều `append()` có kiểm soát

Chương trình sau buộc Luồng B chen một bản ghi hoàn chỉnh vào giữa hai lần thêm của Luồng A. Không có dữ liệu bị hỏng ở cấp bộ đệm, nhưng định dạng tổng thể không còn như mong muốn.

Tạo tệp `StringBufferInterleavingDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class StringBufferInterleavingDemo {
    public static void main(String[] args) throws InterruptedException {
        StringBuffer buffer = new StringBuffer();
        CountDownLatch firstPartDone = new CountDownLatch(1);
        CountDownLatch otherPartDone = new CountDownLatch(1);

        Thread first = new Thread(() -> {
            buffer.append("[A");
            firstPartDone.countDown();

            try {
                otherPartDone.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            buffer.append("]");
        });

        Thread second = new Thread(() -> {
            try {
                firstPartDone.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            buffer.append("[B]");
            otherPartDone.countDown();
        });

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("interleaved = " + buffer);
    }
}
```

Chạy:

```bash
javac StringBufferInterleavingDemo.java
java StringBufferInterleavingDemo
```

Kết quả khi không bị ngắt ngoài ý muốn:

```text
interleaved = [A[B]]
```

Lịch thực hiện được điều phối: Luồng A thêm `"[A"` trước, rồi đợi; Luồng B thêm `"[B]"` vào giữa; sau đó A mới thêm `"]"`. Cả ba `append()` đều hợp lệ, nhưng chuỗi cuối không chứa hai record `"[A]"` và `"[B]"` liền mạch.

Để sửa cho ứng dụng thật, thay đổi **thiết kế quy trình**: hoặc xây bản ghi `"[A]"` rồi gọi một lần `append(record)`, hoặc dùng vùng tới hạn giữ khóa xuyên suốt các phần tạo một bản ghi. Ví dụ có chủ đích dùng một lock chung:

```java
private static void appendRecord(StringBuffer buffer, String label) {
    synchronized (buffer) {
        buffer.append("[");
        buffer.append(label);
        buffer.append("]");
    }
}
```

Đây là **fragment** của một phương thức static đặt trong lớp Java. Nếu cả hai luồng đều gọi phương thức này trên cùng buffer, thứ tự `"[A][B]"` hay `"[B][A]"` còn phụ thuộc lịch chạy, nhưng mỗi bản ghi riêng lẻ vẫn liền mạch. **Atomicity bảo vệ tính liền mạch; không tự quy định luồng nào đi trước.**

## 10. Nhìn rộng hơn: atomicity, visibility, ordering

Các chương trình đa luồng thường cần xem xét ít nhất ba khía cạnh:

1. **Atomicity**: các bước phải xuất hiện như một đơn vị logic, không bị các bước cạnh tranh chen giữa.
2. **Visibility**: khi một luồng ghi, luồng khác có thể quan sát giá trị đó theo quy tắc bộ nhớ Java hay không.
3. **Ordering**: những bước cần được quan sát theo một thứ tự nào; ví dụ `CountDownLatch`, `join()` và monitor tạo quan hệ phối hợp phù hợp.

Các phương thức đồng bộ của `StringBuffer` cung cấp những bảo đảm quan trọng ở cấp thao tác. Tuy nhiên, chúng **không thay thế** việc xác định một trình tự logic xuyên suốt nhiều lời gọi.

Ví dụ, nếu chương trình dựa vào việc một thread phải hoàn thành một bản ghi trước khi thread khác đọc toàn bộ bản ghi, có thể cần **quy trình phối hợp** ngoài một lần gọi `toString()`: monitor cho cả lần tạo record, hàng đợi thông điệp, latch hoặc thiết kế trao đổi dữ liệu thích hợp.

`toString()` lấy một giá trị `String` bất biến của nội dung tại thời điểm lời gọi; nó không “đợi” ứng dụng hoàn thành một transaction chưa được biểu diễn bằng đồng bộ hóa phù hợp.

## 11. So sánh `StringBuffer`, `StringBuilder` và `String`

| Loại | Mutable? | Đồng bộ hóa tích hợp | Phù hợp |
| --- | --- | --- | --- |
| `String` | Không | Không cần khóa chỉ để giữ nguyên nội dung | Giá trị văn bản đã xây xong, chia sẻ chuỗi đọc chung. |
| `StringBuilder` | Có | Không bảo đảm thread-safe khi nhiều luồng cùng sửa | Xây chuỗi ở một luồng hoặc builder cục bộ không chia sẻ. |
| `StringBuffer` | Có | Các thao tác chính đồng bộ hóa theo đối tượng | Khi thật sự cần một buffer mutable được các luồng cùng sử dụng và muốn các lời gọi được đồng bộ ở cấp phương thức. |

**Không nên kết luận “chọn `StringBuffer` là mọi thứ đã an toàn”.** Nó không giải quyết một điều kiện gồm nhiều bước, invariant trải trên nhiều đối tượng, hoặc thứ tự nghiệp vụ giữa các luồng.

Nếu builder/buffer **không bị chia sẻ** giữa các luồng, `StringBuilder` thường đơn giản và không phải trả chi phí đồng bộ của `StringBuffer`. Nếu cần nhiều luồng cùng sản xuất bản ghi, đôi khi giải pháp tốt hơn là để mỗi luồng xây chuỗi riêng rồi đưa vào một hàng đợi thread-safe, sau đó **một luồng chuyên trách** tổng hợp kết quả. Cách này có thể dễ kiểm soát thứ tự và định dạng hơn là khóa một buffer toàn cục.

Không nên tuyên bố chênh lệch hiệu năng chính xác nếu chưa đo trên phiên bản JVM và tải thực tế.

## 12. Đồng bộ trên buffer có thể gây vấn đề gì?

### Giữ khóa quá lâu

```java
synchronized (buffer) {
    buffer.append("begin");
    // Không nên chờ tác vụ I/O rất lâu tại đây nếu không cần.
    buffer.append("end");
}
```

Trong lúc giữ khóa, những luồng muốn vào phương thức đồng bộ của cùng buffer có thể phải đợi. Hãy rút ngắn vùng tới hạn, chuẩn bị dữ liệu trước khi khóa và chỉ giữ khóa trong phần bảo vệ invariant.

### Thứ tự lấy nhiều khóa

Nếu quy trình giữ khóa `bufferA` rồi lấy `bufferB`, trong khi luồng khác làm ngược lại, có thể xảy ra **deadlock**. Khi phải giữ nhiều khóa, xác định một thứ tự khóa nhất quán giữa các luồng hoặc thay đổi thiết kế để giảm việc giữ nhiều monitor.

### Dùng buffer công khai làm monitor

Nếu đưa `StringBuffer` cho mã không kiểm soát, thành phần ngoài có thể dùng `synchronized(buffer)` và giữ khóa lâu, gây chặn các thành phần khác. Trong hệ thống lớn, thường tốt hơn là **đóng gói trạng thái chia sẻ**, tránh lộ buffer mutable, sử dụng khóa nội bộ và API nghiệp vụ nguyên tử.

Nếu khóa nội bộ là đối tượng khác buffer, **đừng quên** mọi đường thao tác cùng invariant phải đi qua khóa đó. Khóa riêng không tự đồng bộ hóa với monitor của `StringBuffer` nếu ai đó truy cập buffer trực tiếp.

## 13. Lỗi phổ biến

| Ngộ nhận | Thực tế | Cách sửa |
| --- | --- | --- |
| “`StringBuffer` thread-safe nên hai lời gọi liền nhau là atomic.” | Mỗi lời gọi có thể nhả khóa trước lời gọi tiếp theo. | Khóa toàn bộ vùng tới hạn hoặc gộp công việc thành một lời gọi phù hợp. |
| “`if (length()==0) append()` luôn chỉ thêm một lần.” | Hai luồng có thể cùng thấy rỗng trước khi một luồng append. | Bao toàn bộ check-then-act trong cùng monitor. |
| “Viết `append(a).append(b)` là một thao tác.” | Đây vẫn là hai lời gọi phương thức riêng. | Bao chuỗi gọi trong `synchronized(buffer)` nếu cần atomicity. |
| “Mỗi `append()` riêng biệt an toàn nghĩa là một record nhiều phần không xen lẫn.” | Luồng khác có thể append giữa các phần. | Xây record hoàn chỉnh trước hoặc khóa toàn bộ record. |
| “`length()` vừa trả giá trị nên chắc chắn vẫn đúng tới lúc `deleteCharAt()`.” | Trạng thái có thể thay đổi sau khi `length()` trả về. | Đọc, kiểm tra và xóa trong một vùng tới hạn. |
| “`volatile StringBuffer` khiến compound operation an toàn.” | `volatile` không gom nhiều lời gọi thành một hành động nguyên tử. | Dùng monitor/lock hoặc thiết kế đồng bộ ở cấp giao dịch. |
| “Khóa đối tượng khác cũng tự khóa buffer.” | Hai monitor khác nhau là hai cơ chế khóa độc lập. | Thống nhất khóa và đóng gói mọi đường truy cập. |
| “Có synchronized thì thứ tự các thread sẽ đúng theo ý muốn.” | Loại trừ xen kẽ không xác định thứ tự ai vào trước. | Dùng cơ chế phối hợp thích hợp nếu thứ tự có ý nghĩa. |
| “`toString()` tạo view trực tiếp nên có thể đọc dở một record.” | Kết quả `String` là giá trị bất biến; nhưng bản ghi có thể đang ở trạng thái **logic chưa hoàn chỉnh** do quy trình không atomic. | Đồng bộ hóa toàn bộ quá trình tạo record hoặc xuất bản snapshot khi hoàn tất. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Hai thread cùng chạy đoạn sau trên một `StringBuffer`. Điều gì có thể xảy ra?

```java
if (buffer.length() == 0) {
    buffer.append("A");
}
```

**Đáp án:** cả hai có thể thấy `length() == 0` và cùng thêm `"A"`, cho kết quả `"AA"`. Không có vi phạm tính an toàn riêng lẻ của `length()` hay `append()`; lỗi nằm ở việc **hai bước không nguyên tử**.

**Câu 2.** Đổi thành `buffer.append("[A").append("]")` đã đủ bảo đảm `"[A]"` không bị xen ký tự từ luồng khác chưa?

**Chưa.** Chained calls vẫn là hai lời gọi. Muốn bảo vệ record nguyên vẹn, dùng `synchronized(buffer)` bao trùm cả hai hoặc xây `"[A]"` độc lập rồi append **một lần**.

**Câu 3.** Nếu hai thread đều viết bản ghi hoàn chỉnh qua một vùng `synchronized(buffer)`, ta có chắc thứ tự `"[A][B]"` không?

**Không.** Có thể là `"[A][B]"` hoặc `"[B][A]"` tùy lịch chạy. Điều được bảo đảm là các phần của mỗi record không bị xen ngang bởi lời gọi cạnh tranh dùng cùng monitor.

**Câu 4.** Tại sao `synchronized(lock)` không bảo đảm atomicity với mã khác trực tiếp gọi `buffer.append()` nếu `lock` khác `buffer`?

Vì `buffer.append()` dùng cơ chế khóa của buffer, còn `synchronized(lock)` dùng một monitor **khác**. Hai bên không chờ nhau theo cùng một khóa. Cần đóng gói buffer và tuân thủ **một quy ước khóa thống nhất**.

**Câu 5.** Nếu chỉ có một luồng xây văn bản, có bắt buộc dùng `StringBuffer` không?

**Không.** Một `StringBuilder` cục bộ thường phù hợp. Đồng bộ hóa ở `StringBuffer` chỉ hữu ích khi giải quyết nhu cầu chia sẻ đa luồng tương ứng, và nó không miễn trách nhiệm thiết kế tính nguyên tử cho nhiều bước.

## Kết luận

- Các lời gọi chính của `StringBuffer` được đồng bộ hóa để hỗ trợ nhiều luồng truy cập một đối tượng mutable.
- **Mỗi phương thức an toàn riêng không đồng nghĩa toàn bộ chuỗi lời gọi nguyên tử.** Luồng khác vẫn có thể chen giữa các lời gọi.
- Đặc biệt chú ý **check-then-act**, **read-modify-write**, **nhiều `append()` cho một record** và **nhiều lần đọc phải nhất quán**.
- Khi cần một giao dịch logic, gộp các bước dưới **cùng một monitor/lock** và bảo đảm tất cả bên liên quan tôn trọng quy tắc đó.
- Chọn API theo yêu cầu thật: `StringBuilder` cho xây chuỗi cục bộ, `StringBuffer` cho đồng bộ thao tác trên buffer chia sẻ, hoặc thiết kế hàng đợi/đóng gói khi invariant đa luồng phức tạp.
- **Atomicity, visibility và ordering là những thuộc tính khác nhau**. Một API thread-safe không tự giải quyết mọi quy tắc phối hợp của chương trình.

## Tài liệu tham khảo

- [Java SE 21 API — `java.lang.StringBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuffer.html): hợp đồng đồng bộ hóa các thao tác, `append()`, `length()`, `toString()`.
- [Java SE 21 API — `java.lang.StringBuilder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html): đối chiếu với builder mutable không đồng bộ hóa.
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): monitor, happens-before và mô hình bộ nhớ.
- [Java SE 21 API — `java.util.concurrent.CountDownLatch`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phối hợp tiến trình các luồng trong ví dụ tái hiện race.

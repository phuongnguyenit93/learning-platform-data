# Buffer không mặc nhiên an toàn cho nhiều luồng trong Java NIO

## 1. Vấn đề cần hiểu

`java.nio.Buffer` và các lớp con như `ByteBuffer`, `CharBuffer`, `IntBuffer` được thiết kế để thao tác hiệu quả với dữ liệu và giữ trạng thái đọc/ghi. Chúng **không mặc nhiên bảo đảm an toàn khi nhiều thread đồng thời sử dụng cùng một buffer**. Tài liệu API Java mô tả rõ buffer không an toàn cho nhiều thread truy cập đồng thời nếu không có cơ chế đồng bộ phù hợp.

Đây là vấn đề ngay cả khi nhiều thread **chỉ đọc các byte**. Với phương thức đọc tương đối như `get()`, việc đọc làm thay đổi `position`, nên các thread đang sửa **trạng thái con trỏ dùng chung**. Nếu thread khác vừa `flip()`, `clear()` hoặc `compact()` trong lúc đọc, còn có thể gặp lỗi giới hạn và dữ liệu không nhất quán.

Cần tách hai câu hỏi:

- **Trạng thái buffer có được chia sẻ không?** `position`, `limit`, `mark` và một số phép biến đổi chúng quyết định byte nào được đọc/ghi.
- **Vùng nhớ chứa dữ liệu có được chia sẻ không?** Hai buffer có thể có con trỏ riêng nhưng vẫn cùng trỏ đến một mảng hoặc vùng nhớ; đọc/ghi cùng vùng có thể gây data race.

Kết luận khi thiết kế: **Một buffer chỉ an toàn khi quyền sử dụng, thao tác và quan hệ đồng bộ giữa các thread được quy định rõ.** Không nên suy luận rằng `ByteBuffer` tự cung cấp lock chỉ vì nó thuộc Java NIO.

## 2. Position, limit, capacity, mark là trạng thái mutable

Một `Buffer` có bốn khái niệm cốt lõi:

| Thuộc tính | Ý nghĩa | Lưu ý với nhiều thread |
| --- | --- | --- |
| `capacity` | Kích thước bộ nhớ biểu diễn bởi buffer, không đổi trong vòng đời object | Không bảo vệ trạng thái khác |
| `limit` | Ranh giới kết thúc vùng đọc/ghi đang được phép | Thread thay đổi limit có thể làm các thread khác đọc sai phạm vi |
| `position` | Chỉ số cho thao tác đọc/ghi tương đối kế tiếp | `get()`/`put(...)` dịch chuyển position chung |
| `mark` | Vị trí được đánh dấu để `reset()` trở về | Thay đổi position/limit có thể làm mark mất hiệu lực |

Các ràng buộc được buffer duy trì trong thao tác đơn lẻ có dạng `0 ≤ position ≤ limit ≤ capacity`; nếu có mark thì `mark ≤ position`. Việc một method đơn lẻ duy trì bất biến của buffer **không có nghĩa chuỗi thao tác từ nhiều thread được thực hiện nguyên tử như một giao dịch**.

Ví dụ vòng đời buffer thường gặp:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(4);
buffer.put((byte) 10);
buffer.put((byte) 20);
buffer.flip();        // chuyển từ ghi sang đọc: limit=2, position=0
byte a = buffer.get(); // a=10; position=1
~~~

Đây là **đoạn minh họa** có thể đặt trong một method. Thao tác `put`, `flip` và `get` đều làm biến đổi trạng thái. `flip()` chuẩn bị đọc dữ liệu vừa ghi; `clear()` đặt position/limit cho một chu kỳ ghi mới nhưng **không xóa dữ liệu**, còn `compact()` có thể di chuyển các byte chưa đọc trong bộ nhớ.

Nếu một thread đọc khi thread khác gọi `flip()`/`clear()`/`compact()` mà không đồng bộ, reader có thể bị thay đổi phạm vi đọc, thấy byte cũ hoặc đọc dữ liệu ở vị trí ngoài dự kiến.

## 3. Đọc tương đối là một thao tác thay đổi trạng thái

Giả sử buffer chứa bốn byte:

~~~text
index:     0   1   2   3
data:     10  20  30  40
position:  0
limit:     4
~~~

Hai thread A và B đều gọi `get()` trên **chính object buffer đó**. Mỗi lần `get()` đọc byte ở `position` hiện tại rồi cập nhật vị trí kế tiếp. Ngay cả nếu không ai sửa nội dung mảng byte, hai thread vẫn tranh chấp **cùng một cursor**.

Một cách xen kẽ hợp lệ khi có thứ tự kiểm soát:

~~~text
A: get() -> 10, position=1
B: get() -> 20, position=2
B: get() -> 30, position=3
A: get() -> 40, position=4
~~~

Nếu A muốn nhận hai byte đầu, B muốn nhận hai byte cuối, cùng gọi `get()` trên một buffer **không thể tự đáp ứng ranh giới công việc**. Ngoài ra, khi hai thread thật sự gọi cùng lúc và không đồng bộ, các bước đọc/cập nhật position không có bảo đảm nguyên tử để phát mỗi byte chính xác một lần: có thể trùng dữ liệu, bỏ byte, hoặc ném `BufferUnderflowException`/`BufferOverflowException` tùy tình huống.

Cần phân biệt **xen kẽ thao tác có kiểm soát** với **data race**: ví dụ ở phần tiếp theo dùng latch để có kết quả ổn định, nhằm chứng minh cursor bị dùng chung. Nó không dựa vào việc kích hoạt data race ngẫu nhiên, nên không phải bài kiểm thử phát hiện mọi race.

## 4. Ví dụ Java 17+ chạy được: cùng cursor và các view riêng

Tạo tệp `BufferThreadsDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public class BufferThreadsDemo {
    public static void main(String[] args) throws InterruptedException {
        ByteBuffer shared = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
        CountDownLatch aReadFirst = new CountDownLatch(1);
        CountDownLatch bReadBoth = new CountDownLatch(1);
        int[] a = new int[2], b = new int[2];

        Thread threadA = new Thread(() -> {
            a[0] = Byte.toUnsignedInt(shared.get());
            aReadFirst.countDown();
            await(bReadBoth);
            a[1] = Byte.toUnsignedInt(shared.get());
        });
        Thread threadB = new Thread(() -> {
            await(aReadFirst);
            b[0] = Byte.toUnsignedInt(shared.get());
            b[1] = Byte.toUnsignedInt(shared.get());
            bReadBoth.countDown();
        });

        threadA.start();
        threadB.start();
        threadA.join();
        threadB.join();
        System.out.println("Shared A: " + Arrays.toString(a));
        System.out.println("Shared B: " + Arrays.toString(b));
        System.out.println("Shared position: " + shared.position());

        ByteBuffer source = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
        ByteBuffer left = source.slice(0, 2).asReadOnlyBuffer();
        ByteBuffer right = source.slice(2, 2).asReadOnlyBuffer();
        int[][] results = new int[2][2];

        Thread leftThread = new Thread(() -> {
            results[0][0] = Byte.toUnsignedInt(left.get());
            results[0][1] = Byte.toUnsignedInt(left.get());
        });
        Thread rightThread = new Thread(() -> {
            results[1][0] = Byte.toUnsignedInt(right.get());
            results[1][1] = Byte.toUnsignedInt(right.get());
        });
        leftThread.start();
        rightThread.start();
        leftThread.join();
        rightThread.join();
        System.out.println("View A: " + Arrays.toString(results[0]));
        System.out.println("View B: " + Arrays.toString(results[1]));
        System.out.println("Source position: " + source.position());
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BufferThreadsDemo.java
java BufferThreadsDemo
~~~

Stdout **chính xác** của chương trình (đã biên dịch và chạy trên JDK):

~~~text
Shared A: [10, 40]
Shared B: [20, 30]
Shared position: 4
View A: [10, 20]
View B: [30, 40]
Source position: 0
~~~

Giải thích:

1. Hai thread đầu tiên nhận cùng một `ByteBuffer shared`. `CountDownLatch` buộc thứ tự A đọc một byte, B đọc hai byte, rồi A đọc byte cuối. Kết quả A nhận `[10, 40]`, thay vì cặp byte liên tiếp giả định `[10, 20]`. Mọi thao tác get trong phần này được sắp thứ tự qua latch, vì thế **đây là chứng minh chia sẻ position chứ không phải mô phỏng race không đồng bộ**.
2. Với phần thứ hai, `slice(0, 2)` và `slice(2, 2)` tạo hai view trên những đoạn khác nhau của cùng dữ liệu. Mỗi view có position, limit, mark **riêng**. Phương thức `asReadOnlyBuffer()` cấm ghi **qua view đó**.
3. Mỗi thread thứ hai chỉ sử dụng view của mình, và không có thread nào thay đổi các byte nền; A đọc `[10, 20]` còn B đọc `[30, 40]`.
4. `source.position()` vẫn là 0 vì đọc bằng view không dịch chuyển con trỏ của `source`. Các thread được khởi động sau khi tạo và thiết lập các view; `Thread.start()` và `Thread.join()` cũng tạo quan hệ *happens-before* thích hợp cho dữ liệu đầu vào/đầu ra của ví dụ.

**Đừng kết luận rằng `slice` và `asReadOnlyBuffer` giúp mọi tình huống dùng chung trở nên thread-safe.** Các view vẫn chia sẻ cùng bộ nhớ byte; nếu thread khác còn tham chiếu đến buffer gốc hoặc mảng gốc và ghi vào đó, dữ liệu mà các view đọc có thể bị thay đổi đồng thời.

## 5. duplicate(), slice(), asReadOnlyBuffer(): tách con trỏ, không nhất thiết tách dữ liệu

Java NIO cho phép tạo nhiều view đến cùng vùng nhớ:

| Cách tạo | Trạng thái `position/limit/mark` của view | Nội dung byte | Cẩn trọng |
| --- | --- | --- | --- |
| `original.duplicate()` | Ban đầu sao chép giá trị trạng thái; về sau thay đổi độc lập | Chia sẻ backing storage | Hai view cùng ghi một byte vẫn có thể xung đột |
| `original.slice()` | View mới position 0, limit/capacity là vùng `remaining()` của source tại thời điểm tạo | Chia sẻ vùng từ position hiện tại của source | Không bị ràng buộc bởi các thay đổi cursor sau này của source, nhưng vẫn chia sẻ dữ liệu |
| `original.slice(index, length)` | View mới position 0, limit/capacity bằng length | Chia sẻ đúng vùng từ index tới index+length của source | Chỉ có trên Java phiên bản hỗ trợ overload, dùng tốt với Java 17+ |
| `original.asReadOnlyBuffer()` | Trạng thái con trỏ độc lập, ban đầu theo source | Chia sẻ dữ liệu nhưng **không cho put qua view** | Owner hoặc alias khác vẫn có thể sửa dữ liệu |
| `ByteBuffer.allocate(n)` | Trạng thái độc lập | Cấp vùng byte mới | Hữu ích khi mỗi worker cần ghi riêng, nhưng cần cơ chế trao đổi kết quả |
| `ByteBuffer.wrap(array)` | Trạng thái buffer độc lập | **Chia sẻ mảng array bên ngoài** | Bất kỳ ai giữ mảng gốc vẫn có thể thay đổi nội dung |

Điểm quyết định:

- Tách **cursor** bằng `duplicate`/`slice` giúp các thread không giẫm lên position của nhau khi mỗi thread sở hữu view riêng.
- Tách **dữ liệu** đòi hỏi vùng nhớ khác nhau, ví dụ `allocate` mới và copy bytes, hoặc bảo đảm các vùng ghi không giao nhau cùng với quy tắc không có alias ghi chồng.
- Đọc từ các view dùng chung vùng dữ liệu có thể an toàn trong thực hành nếu dữ liệu đã được hoàn tất, công bố đúng cách (*safe publication*) và không còn writer nào sửa vùng đó.
- Read-only view chỉ bảo vệ giao diện ghi của chính view; nó **không làm backing data trở thành bất biến**.

Ví dụ về view chỉ đọc nhưng dữ liệu vẫn có thể thay đổi:

~~~java
byte[] bytes = {1, 2, 3};
ByteBuffer readOnly = ByteBuffer.wrap(bytes).asReadOnlyBuffer();
bytes[0] = 9;
System.out.println(readOnly.get(0)); // 9
~~~

Đây là đoạn code minh họa có thể đặt trong một method. Không có concurrent access trong ví dụ này; nó chứng minh sự chia sẻ backing storage. Nếu việc thay đổi `bytes[0]` diễn ra đồng thời với việc đọc mà không có đồng bộ, còn phát sinh vấn đề *visibility* và data race.

Một buffer được tạo bằng `allocateDirect` cũng không tự động thread-safe. *Direct* chỉ nói đến cách cấp phát/khả năng sử dụng vùng nhớ ngoài heap; nó không cung cấp giao thức khóa, phân quyền ghi hoặc thứ tự bộ nhớ thay cho chương trình.

## 6. Absolute get/put tránh thay đổi position nhưng chưa giải quyết mọi race

ByteBuffer cung cấp thao tác **tương đối** và **tuyệt đối**:

~~~java
byte next = buffer.get();           // lấy ở position, làm tăng position
byte atThree = buffer.get(3);       // lấy ở index 3, không đổi position
buffer.put((byte) 7);               // ghi ở position, làm tăng position
buffer.put(3, (byte) 7);            // ghi ở index 3, không đổi position
~~~

Đây là đoạn minh họa, giả sử `buffer` tồn tại và các vị trí nằm trong limit hợp lệ. Một thao tác theo index tuyệt đối không thay đổi cursor, nên tránh được **một nguồn tranh chấp**. Tuy nhiên:

- Nếu thread khác đang thay đổi `limit`, kiểm tra chỉ số hợp lệ và phạm vi truy cập có thể không ổn định.
- Hai writer truy cập cùng index, hoặc reader đọc đồng thời writer ghi cùng byte, vẫn có khả năng data race và kết quả không được điều phối.
- Không có gì bảo đảm một chuỗi thao tác tuyệt đối như “đọc 4 byte, kiểm tra rồi ghi 4 byte” là nguyên tử.
- `getInt(index)` hoặc `putLong(index, value)` không tự biến thao tác cập nhật nhiều trường của record thành transaction. Tính nguyên tử và visibility phải được thiết kế theo các bảo đảm thực tế của API/JVM.

Có thể dùng absolute access trong **schema chỉ đọc, đã đóng băng dữ liệu** với các vùng byte rõ ràng, nhưng vẫn cần công bố buffer cho các thread một cách an toàn.

## 7. Các chiến lược an toàn khi chạy đa luồng

### 7.1. Thread confinement: mỗi thread sở hữu buffer riêng

Đây thường là lựa chọn dễ hiểu nhất: mỗi worker tự `ByteBuffer.allocate(...)` hoặc nhận bản copy của dữ liệu, sau đó chỉ worker đó được `put/get/flip/clear`. Không chia sẻ mutable cursor và không có writer khác chạm vào backing storage.

Ví dụ về logic xử lý một tác vụ đơn luồng:

~~~java
static int parseTwoBytes(byte[] input) {
    ByteBuffer own = ByteBuffer.wrap(input.clone());
    int a = Byte.toUnsignedInt(own.get());
    int b = Byte.toUnsignedInt(own.get());
    return (a << 8) | b;
}
~~~

Đoạn trên là **method minh họa**; caller phải bảo đảm input có ít nhất hai byte. `clone()` tạo bản sao tách nội dung khỏi mảng do caller giữ. Nếu chỉ một thread sở hữu `input` trong toàn bộ quá trình, copy có thể không cần thiết.

### 7.2. Phân chia vùng làm việc, mỗi thread một view

Nếu dữ liệu lớn và không muốn copy, có thể tạo các view không chồng lấn sau khi xác định ranh giới:

~~~java
ByteBuffer left  = source.slice(0, half);
ByteBuffer right = source.slice(half, source.limit() - half);
~~~

Đây là đoạn minh họa, giả sử `source` đã được tạo ổn định, `0 ≤ half ≤ source.limit()`. Chỉ giao `left` cho worker A, `right` cho worker B. Nếu có ghi, mọi alias (kể cả `source` hoặc mảng backing) phải tuân thủ **vùng sở hữu không giao nhau**. Nếu dữ liệu chỉ đọc, dùng thêm `asReadOnlyBuffer()` để phát hiện ghi nhầm qua view.

Cần hiểu rằng thao tác tạo view không tự khóa vùng dữ liệu. Nếu thành phần khác vẫn có quyền ghi cả mảng gốc thì việc phân đoạn giữa hai worker chưa đủ.

### 7.3. Chuyển quyền sở hữu thay vì cùng sử dụng

Một pipeline producer/consumer thường hoạt động như sau:

1. Producer được quyền duy nhất ghi vào buffer, hoàn tất ghi và gọi `flip()`.
2. Producer **bàn giao** buffer qua cơ chế đồng bộ như `BlockingQueue.put(buffer)`.
3. Consumer gọi `take()` và là thành phần duy nhất đọc/dịch chuyển position trong giai đoạn đó.
4. Consumer báo hoàn thành hoặc đưa buffer vào pool theo giao thức rõ ràng; **chỉ lúc ấy** producer/pool mới được `clear()` và tái sử dụng nó.

`BlockingQueue` có bảo đảm memory consistency: những hành động trước khi đặt đối tượng vào queue *happen-before* các hành động sau khi thread khác lấy đối tượng ra. Điều đó hỗ trợ **safe publication**, nhưng queue **không tự thu hồi quyền sở hữu** của producer. Nếu producer tiếp tục sửa buffer sau khi `put`, vẫn có lỗi dùng chung.

Trong hệ thống async I/O, cần chờ thao tác hoàn tất trước khi tái sử dụng buffer. Đừng `clear()`/`compact()` một buffer trong khi một tác vụ đọc/ghi bất đồng bộ còn đang sử dụng vùng đó.

### 7.4. Đồng bộ mọi thao tác trên buffer được chia sẻ

Nếu thật sự cần chia sẻ **cùng một cursor**, sử dụng khóa bao phủ một đơn vị công việc đủ lớn. Ví dụ method sau lấy ra byte kế tiếp an toàn **nếu tất cả code truy cập/mutate cùng buffer đều tuân theo khóa này**:

~~~java
static byte takeNext(ByteBuffer shared) {
    synchronized (shared) {
        if (!shared.hasRemaining()) {
            throw new java.nio.BufferUnderflowException();
        }
        return shared.get();
    }
}
~~~

Đây là **method minh họa**, không phải chương trình độc lập. `hasRemaining()` và `get()` nằm chung critical section nên không có thread cùng tuân theo monitor đó chen vào làm thay đổi position giữa kiểm tra và đọc.

Tuy nhiên, khóa này chỉ có ý nghĩa khi **mọi đường truy cập liên quan** (`put`, `get`, `position`, `limit`, `flip`, `clear`, `compact` và truy cập backing array nếu có) tuân thủ cùng giao thức. Chỉ khóa hàm đọc rồi để thread ghi dùng `shared.put(...)` ngoài lock sẽ làm mất bảo đảm. Ngoài ra, khóa từng byte có thể không đủ cho thao tác nghiệp vụ gồm nhiều byte cần nhất quán như một record; lúc đó phải khóa toàn bộ record/batch hoặc dùng thiết kế khác.

`ReentrantLock` hoặc cơ chế khóa khác có thể phù hợp khi cần timeout, fairness hay điều kiện chờ. Điều quan trọng là **phạm vi khóa**, không phải tên primitive.

### 7.5. Dữ liệu immutable và đọc đồng thời

Với dữ liệu được tạo một lần rồi không đổi, nhiều worker có thể cùng đọc **qua view độc lập**, miễn là:

- Các byte đã hoàn tất trước khi công bố cho worker; không còn writer hoặc alias còn khả năng sửa dữ liệu trong lúc đọc.
- Có safe publication (ví dụ `Thread.start()`, trao qua `BlockingQueue` hoặc cấu trúc đồng bộ phù hợp).
- Mỗi thread giữ cursor riêng (`duplicate`, `slice` hoặc dùng index tuyệt đối với giới hạn bất biến).

Không nên gắn nhãn “immutable” cho `ByteBuffer.asReadOnlyBuffer()` khi vẫn còn alias ghi vào backing storage. Với yêu cầu bất biến mạnh, sao chép dữ liệu vào đối tượng được quản lý và bảo vệ toàn bộ alias, hoặc cung cấp API chỉ đọc mà phần nội dung thực tế cũng không bị sửa.

## 8. Sai lầm thường gặp trong ứng dụng NIO

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Hai thread đều gọi `get()` trên cùng object | Cùng dịch chuyển position, mất phân vùng đọc | Giao view riêng, chuyển quyền sở hữu hoặc đồng bộ |
| Hai thread đều gọi `put()` trên cùng object | Tranh chấp vị trí ghi và dữ liệu | Vùng riêng, khóa hoặc kiến trúc producer/consumer |
| Một thread `flip()` khi thread kia còn `put()` | Thay đổi limit/position khi dữ liệu chưa hoàn chỉnh | Kết thúc ghi rồi bàn giao buffer bằng đồng bộ |
| Dùng `duplicate()` và cho rằng đã copy bytes | Hai view vẫn chia sẻ backing storage | Copy riêng nếu cần bộ nhớ độc lập |
| Dùng `asReadOnlyBuffer()` và cho rằng dữ liệu không thể đổi | Alias khác vẫn có thể ghi | Kiểm soát alias và quyền sửa dữ liệu |
| Đọc tuyệt đối `get(index)` rồi kết luận toàn bộ thao tác thread-safe | Vẫn có tranh chấp dữ liệu/limit và thiếu atomicity | Xác định bất biến dữ liệu hoặc dùng khóa |
| Cho nhiều thread dùng chung `ByteBuffer.wrap(array)` nhưng sửa `array` từ ngoài | Reader thấy dữ liệu thay đổi không đồng bộ | Không sửa array hoặc sao chép |
| Dùng `volatile ByteBuffer buffer` rồi nghĩ mọi `position/get/put` được đồng bộ | Volatile reference không đồng bộ hóa nội trạng thái mutable | Giao thức ownership/lock phù hợp |
| Lấy buffer từ pool rồi tái sử dụng trước khi consumer/async I/O xong | Byte cũ bị ghi đè, cursor/limit đổi giữa tác vụ | Chỉ trả pool khi có xác nhận hoàn tất |
| Dùng `clear()` để “xóa sạch dữ liệu” | Dữ liệu cũ còn trong backing storage | Nếu cần xóa nhạy cảm, ghi đè vùng cần thiết theo yêu cầu bảo mật riêng |

**Lưu ý về lỗi runtime:** một race có thể sinh `BufferUnderflowException`, `BufferOverflowException` hoặc `InvalidMarkException`, nhưng cũng có thể sinh **kết quả sai mà không ném exception**. Việc chạy thử 1.000 lần không lỗi không chứng minh chương trình an toàn đa luồng; lỗi phụ thuộc thời điểm thực thi và thứ tự truy cập bộ nhớ.

## 9. Hệ quả đối với SocketChannel, FileChannel và pipeline

Một ứng dụng NIO thường dùng `ByteBuffer` làm đầu vào/đầu ra của channel. Cần tách hai đối tượng và hợp đồng của chúng:

- Channel có thể có các bảo đảm đồng thời riêng của từng implementation/method, nhưng **bảo đảm đó không tự áp dụng lên cursor của một buffer đang được nhiều thread truyền vào**.
- Khi gọi `channel.read(buffer)`, channel **ghi bytes vào buffer và cập nhật position**; `channel.write(buffer)` **đọc bytes từ buffer và cập nhật position**. Nếu thread khác đồng thời thay đổi position/limit hoặc nội dung, dữ liệu gửi/nhận có thể sai.
- `SocketChannel` phi blocking có thể đọc/ghi được một phần: buffer phải giữ position chính xác để phần còn lại được xử lý tiếp. Không cho worker khác `rewind()`/`clear()` giữa các lần ghi tiếp phần còn lại.
- Trong pipeline xử lý packet, mỗi kết nối hoặc mỗi tác vụ có thể có buffer riêng; nếu chuyển buffer giữa event loop và worker, cần giao thức bàn giao ownership rõ ràng.
- Nếu dùng buffer pool, thời điểm trả pool phải sau thao tác channel/consumer hoàn tất; lưu một view vào nơi khác rồi trả backing storage quá sớm vẫn nguy hiểm.

Ví dụ một chu kỳ send thường gặp:

~~~java
buffer.flip();
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
buffer.clear();
~~~

Đây là **mã minh họa cho channel ở chế độ blocking**, giả sử `buffer` đã chứa dữ liệu và `channel` có sẵn, mở và ghi được. Với channel non-blocking, `write` có thể trả 0; cần đăng ký trạng thái có thể ghi hoặc cơ chế retry phù hợp, không busy-spin trong vòng lặp trên. Trong cả hai trường hợp, thread hiện tại phải giữ quyền thao tác buffer trong suốt chu kỳ, hoặc đồng bộ phù hợp.

## 10. Tính visibility và happens-before

Java Memory Model xác định khi nào ghi ở thread này được thread khác quan sát đúng. Nếu một thread ghi bytes rồi thread khác đọc cùng backing storage mà không có một quan hệ *happens-before* phù hợp, mã không có cơ sở bảo đảm visibility và thứ tự của các thao tác.

Một số cơ chế tạo quan hệ này:

- `Thread.start()`: các hành động của thread khởi tạo trước `start()` happen-before hành động của thread mới.
- `Thread.join()`: khi thread A kết thúc và thread B hoàn thành join A, các hành động của A happen-before các hành động tiếp theo của B.
- Release/acquire trên cùng monitor qua `synchronized`.
- Các thao tác trao đổi phần tử phù hợp qua `BlockingQueue`.
- Hợp đồng memory consistency của các cơ chế đồng bộ khác trong `java.util.concurrent`.

**Happens-before không đồng nghĩa với quyền được cùng sửa.** Ví dụ truyền buffer qua queue đúng cách tạo visibility cho dữ liệu đã ghi trước bàn giao, nhưng nếu producer và consumer tiếp tục ghi cùng byte một lúc, vẫn có vấn đề thiết kế. Cần kết hợp memory visibility với ownership và phối hợp concurrency.

## 11. Cách quyết định thiết kế

| Nhu cầu | Lựa chọn thường hợp lý | Giới hạn cần ghi nhớ |
| --- | --- | --- |
| Mỗi thread xử lý dữ liệu riêng | Buffer cấp phát riêng hoặc copy | Chi phí copy/cấp phát |
| Nhiều thread đọc một dataset không đổi | View độc lập, backing storage không còn writer, safe publication | Read-only view không tự đóng băng backing data |
| Chia dữ liệu lớn cho các worker | `slice(index,length)` theo vùng không chồng lấn | Alias bên ngoài phải tôn trọng ranh giới vùng |
| Producer ghi, consumer đọc theo lượt | Blocking queue hoặc cơ chế bàn giao độc quyền | Không reuse buffer trước acknowledgement |
| Nhiều consumer cần lấy byte kế tiếp từ cùng cursor | Đồng bộ quanh `hasRemaining/get` hoặc thiết kế hàng đợi rõ ràng | Khóa phải bao phủ cả phép đọc/sửa liên quan |
| Nhiều writer cập nhật cùng vùng byte | Khóa hoặc chia quyền sở hữu vùng nhớ; giao thức nhất quán | Positional access không phải transaction |
| Nhiều thread truyền cùng buffer cho I/O channel | Ưu tiên mỗi tác vụ buffer riêng hoặc một owner tại mỗi thời điểm | Channel thread safety không thay thế Buffer thread safety |

Không cần dùng lock cho mọi buffer trong chương trình. Khi chỉ một thread sử dụng một buffer tại một thời điểm, **quyền sở hữu đơn giản** thường dễ kiểm chứng hơn. Chỉ cần lock hoặc điều phối khi thực sự chia sẻ trạng thái/dữ liệu mutable.

## 12. Câu hỏi tự kiểm tra

1. Hai thread chỉ gọi `ByteBuffer.get()` (không gọi `put`), có được coi là chỉ đọc không có tranh chấp? **Không**. `get()` tương đối thay đổi position dùng chung.
2. Hai thread nhận `duplicate()` của cùng một buffer, có thể sửa position độc lập không? **Có**. Nhưng các byte backing storage vẫn được chia sẻ; không được cho hai writer ghi chồng mà thiếu đồng bộ.
3. Có thể dùng `asReadOnlyBuffer()` rồi cho thread khác ghi vào buffer gốc đồng thời mà tự động an toàn không? **Không**. Chỉ view bị cấm ghi, nội dung vẫn có thể bị alias khác thay đổi.
4. Có phải `ByteBuffer.get(index)` thay đổi position không? **Không**. Nhưng thao tác này một mình không bảo đảm an toàn khi có writer hoặc limit được đổi đồng thời.
5. Khi producer đưa buffer vào `BlockingQueue`, producer có thể `clear()` ngay lập tức không? **Không**, trừ khi một giao thức khác xác nhận consumer đã dùng xong và trả quyền sở hữu.
6. Sử dụng `allocateDirect()` có tự đồng bộ truy cập đa luồng không? **Không**; direct/heap là đặc tính lưu trữ, không phải hợp đồng thread safety.
7. Vì sao nhiều thread cùng `channel.write(sharedBuffer)` dễ lỗi dù channel có đồng bộ nội bộ? Vì việc đọc từ buffer làm thay đổi position và các thread còn có thể thay đổi buffer bên ngoài phạm vi đồng bộ của channel.
8. Viết code `synchronized(shared) { shared.get(); }` ở một nơi có đủ chưa? **Chưa chắc**; mọi đường truy cập liên quan phải tuân theo cùng giao thức và phạm vi critical section phải đủ lớn cho tính nhất quán cần thiết.

## Tài liệu tham khảo

- [Java SE 17 — Buffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): position, limit, mark, thao tác trạng thái và thread safety.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): relative/absolute access, `slice`, `duplicate`, `asReadOnlyBuffer`.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): thứ tự thực thi và memory consistency.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): bàn giao giữa producer/consumer và memory consistency.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): tương tác giữa channel và buffer.

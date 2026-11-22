# `Buffer.clear()` không xóa dữ liệu trong vùng nhớ — Java NIO Buffer

## 1. Vấn đề cốt lõi

Tên `clear()` dễ làm người mới hiểu nhầm: gọi `ByteBuffer.clear()` **không xóa các byte đã ghi và không đặt chúng về 0**. Lời gọi này chỉ đặt lại **trạng thái điều khiển việc đọc/ghi** của buffer để chuẩn bị ghi một lượt dữ liệu mới. Đây là hành vi theo hợp đồng API của `java.nio.Buffer`, không phải mẹo phụ thuộc JVM.

Điểm cần phân biệt:

- **Vùng nhớ lưu trữ (storage):** nơi các giá trị byte, char, int... thực sự nằm.
- **Trạng thái của buffer:** các chỉ số `position`, `limit`, `capacity` và `mark` cho biết ứng dụng nên đọc/ghi trong phạm vi nào.
- **Dữ liệu hợp lệ về mặt nghiệp vụ:** thường chỉ là phần đã được ghi ở lượt hiện tại và được giới hạn bằng `flip()`, chứ không phải mọi byte cũ còn nằm trong storage.

Trong module Java Core I/O, hiểu đúng `clear()` là điều kiện để dùng `ByteBuffer` với `FileChannel`, `SocketChannel`, bộ phân tích dữ liệu nhị phân và xử lý dữ liệu nhạy cảm mà không đọc nhầm byte của lượt trước.

## 2. Bốn thuộc tính quyết định cách buffer hoạt động

Một `Buffer` có bốn khái niệm chính:

| Thuộc tính | Ý nghĩa | Bất biến |
| --- | --- | --- |
| `capacity` | Số phần tử tối đa mà buffer có thể chứa theo góc nhìn của chính buffer đó | Không đổi trong vòng đời instance |
| `limit` | Vị trí đầu tiên không được phép đọc/ghi trong lượt thao tác hiện tại | `0 <= limit <= capacity` |
| `position` | Vị trí phần tử tiếp theo của thao tác đọc/ghi tương đối | `0 <= position <= limit` |
| `mark` | Vị trí đã đánh dấu để `reset()` quay lại | Hoặc không xác định, hoặc `mark <= position` |

Giả sử một `ByteBuffer` có `capacity=8` và vừa ghi ba byte:

```text
Chỉ số:       0   1   2   3   4   5   6   7
Storage:     'A' 'B' 'C'  0   0   0   0   0
Trạng thái:  position=3, limit=8, capacity=8
                                   ^
                      Có thể ghi tiếp từ vị trí 3
```

Các byte trong storage không tự động được gắn nhãn “đã cũ” hay “đang hợp lệ”. `position` và `limit` chỉ giúp code quản lý phần đã ghi hoặc có thể đọc. Một thao tác **absolute** như `get(0)` dùng chỉ số được truyền trực tiếp; thao tác **relative** như `get()` dùng `position` rồi tăng nó.

## 3. Hợp đồng chính xác của `clear()`

Đối với `Buffer.clear()` và các lớp con NIO như `ByteBuffer`, hành vi là:

```text
position = 0
limit    = capacity
mark     = undefined (bỏ mark cũ)
storage  = KHÔNG thay đổi do clear()
```

Hình dung trước và sau `clear()` với cùng một vùng nhớ:

```text
Trước clear:
  capacity = 8       limit = 8       position = 3
  storage  = [A, B, C, 0, 0, 0, 0, 0]

Sau clear:
  capacity = 8       limit = 8       position = 0
  storage  = [A, B, C, 0, 0, 0, 0, 0]
             ^
         Lượt ghi mới bắt đầu tại đây
```

**Vì sao Java thiết kế như vậy?** Buffer thường được tái sử dụng rất nhiều lần khi làm I/O. Phần mềm chỉ cần biết “được ghi lại từ đầu”, nên việc xóa từng byte là công việc thừa, tốn chi phí `O(capacity)`. `clear()` thay đổi metadata, thường có độ phức tạp hằng số, giúp vòng lặp đọc kênh hoạt động hiệu quả.

**Không nên hiểu `clear()` là một lệnh bảo mật, giải phóng RAM, thu nhỏ dung lượng hay xóa dữ liệu của file hoặc socket nguồn.** Nó chỉ sửa trạng thái của đối tượng buffer.

## 4. Ví dụ Java 17+ có thể chạy: byte cũ vẫn còn nguyên

Tạo tệp `BufferClearDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class BufferClearDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(6);

        buffer.put((byte) 'A');
        buffer.put((byte) 'B');
        buffer.put((byte) 'C');

        System.out.println("Before clear: position=" + buffer.position()
                + ", limit=" + buffer.limit());

        buffer.clear();

        System.out.println("After clear: position=" + buffer.position()
                + ", limit=" + buffer.limit());
        System.out.println("Old byte at index 2: " + (char) buffer.get(2));

        buffer.put((byte) 'X');
        buffer.put((byte) 'Y');
        buffer.flip();

        byte[] current = new byte[buffer.remaining()];
        buffer.get(current);

        System.out.println("Current logical data: "
                + new String(current, StandardCharsets.US_ASCII));
        System.out.println("Underlying bytes: "
                + Arrays.toString(buffer.array()));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac BufferClearDemo.java
java BufferClearDemo
```

Kết quả chuẩn xác:

```text
Before clear: position=3, limit=6
After clear: position=0, limit=6
Old byte at index 2: C
Current logical data: XY
Underlying bytes: [88, 89, 67, 0, 0, 0]
```

Phân tích:

1. `allocate(6)` tạo một heap `ByteBuffer` có mảng byte mới, ban đầu chứa 6 byte bằng 0. Đây là hệ quả khởi tạo của `byte[]`, không phải do `clear()`.
2. Sau ba lệnh `put`, `position=3`; trong storage có các mã ASCII 65, 66, 67 tại chỉ số 0, 1, 2.
3. `clear()` đặt `position=0, limit=6`. Lệnh `get(2)` là **absolute get**, không làm thay đổi `position`, nên vẫn đọc được byte `C` từ lượt trước.
4. Hai lệnh `put` tiếp theo ghi `X` và `Y` tại chỉ số 0 và 1, **không đụng đến** byte `C` tại chỉ số 2.
5. `flip()` đặt `limit=2, position=0`; vì thế lần đọc tương đối tiếp theo chỉ lấy `XY`. Mảng backing còn `[88,89,67,0,0,0]`: byte `C` vẫn tồn tại nhưng **không nằm trong đoạn dữ liệu hợp lệ của lượt mới**.

Đây là điểm quan trọng: việc `get(2)` nhìn thấy dữ liệu cũ sau `clear()` **không cho phép** coi dữ liệu đó là một phần thông điệp mới.

## 5. Khi nào stale data có thể vô tình được đọc?

Sau `clear()`, `limit=capacity`, nên nếu gọi ngay `get()` hoặc `get(index)` mà chưa ghi dữ liệu mới, API vẫn có thể đọc các giá trị từ storage cũ. Buffer không biết dữ liệu nào được ứng dụng coi là “hợp lệ”.

Ví dụ sai:

```java
ByteBuffer buffer = ByteBuffer.allocate(4);
buffer.put(new byte[] {10, 20, 30});
buffer.clear();

// Sai về mặt nghiệp vụ: đây là dữ liệu cũ, không phải lượt đọc mới.
byte old = buffer.get();
System.out.println(old); // 10
```

Đây là đoạn mã minh họa đặt trong phương thức; có thể chạy khi thêm import `java.nio.ByteBuffer`. Để đọc đúng lượt hiện tại, hãy ghi hoặc để channel điền byte mới, sau đó `flip()` và chỉ đọc trong `remaining()` đã giới hạn.

Các trường hợp dễ lộ dữ liệu cũ:

- Quên `flip()` sau khi ghi ít hơn `capacity` nhưng vẫn đọc theo toàn bộ buffer.
- Dùng `buffer.array()` rồi truyền **cả mảng** cho hàm ghi file, gửi mạng hoặc serialize. Heap `ByteBuffer.array()` có thể trả toàn bộ backing array với byte cũ phía ngoài vùng dữ liệu hiện tại; không dùng mảng đó như số byte hợp lệ.
- Dùng `get(index)` hoặc `put(index,...)` sai phạm vi logic, vì absolute index có quy tắc kiểm tra theo `limit`, không theo số byte hợp lệ mà nghiệp vụ mong muốn.
- Dùng chung buffer giữa các tác vụ/luồng mà không đồng bộ. Buffer không an toàn cho nhiều luồng cập nhật trạng thái cùng lúc.

Các lệnh `get()`/ `put()` tương đối sử dụng `position` và `limit`, nhưng **không có cơ chế tự đánh dấu byte thuộc yêu cầu mạng nào**. Phân định ranh giới thông điệp vẫn là nhiệm vụ của chương trình.

## 6. Quan hệ giữa `clear()`, `flip()`, `rewind()`, `compact()`

| Phương thức | `position` sau gọi | `limit` sau gọi | Storage có bị xóa không? | Mục đích |
| --- | --- | --- | --- | --- |
| `clear()` | `0` | `capacity` | Không | Chuẩn bị **ghi mới từ đầu** |
| `flip()` | `0` | `position` trước gọi | Không | Chuyển từ **ghi** sang **đọc lượng vừa ghi** |
| `rewind()` | `0` | Giữ nguyên | Không | Đọc/ghi lại trong giới hạn hiện tại |
| `compact()` | Số phần tử còn lại trước gọi | `capacity` | Không; có thể **dịch chuyển** dữ liệu còn lại | Giữ phần chưa tiêu thụ, tiếp tục ghi vào phía sau |

Cả bốn thao tác đều loại bỏ mark đã đặt trước đó. `compact()` khác ba thao tác trên vì nó **có thể ghi đè storage** khi dồn các byte từ đoạn `[position, limit)` về đầu buffer, nhưng vẫn **không xóa an toàn toàn bộ dữ liệu cũ**.

### `flip()`: giới hạn dữ liệu mới

Sau khi `put` 3 byte vào buffer dung lượng 8, `position=3`. Gọi `flip()` tạo `position=0, limit=3`, nên `remaining()=3`. Nếu gọi `clear()` thay `flip()` rồi đọc, `remaining()=8`, có nguy cơ đọc thêm byte chưa thuộc lượt hiện tại.

### `rewind()`: đọc lại chứ không làm trống

Với một buffer sau `flip()`, `rewind()` cho phép đọc lại cùng giới hạn `limit`. Nội dung vẫn giữ nguyên. Chọn `rewind` nếu cần duyệt lại dữ liệu đang hợp lệ; chọn `clear` khi muốn ghi lượt mới từ đầu.

### `compact()`: giữ phần còn lại

Giả sử buffer chứa `ABCDE` và đã đọc `AB`. Sau `compact()`, phần chưa đọc `CDE` được dồn về đầu, `position=3`, `limit=capacity`; lượt ghi tiếp nối sau `CDE`. Sau đó `flip()` mới chuyển lại chế độ đọc.

Không giả định các byte nằm ngoài phần hợp lệ sau `compact()` bằng 0: API không cam kết dọn vùng nhớ dư.

## 7. Vòng đời đọc/ghi đúng với `FileChannel` hoặc `SocketChannel`

```text
Chuẩn bị ghi vào buffer    Ghi byte vào buffer      Chuẩn bị đọc byte      Tiêu thụ
       clear()         ->   channel.read(buffer) ->   flip()           -> channel.write(buffer)
          ^                                                              |
          |_____________________ xử lý phần còn lại rồi dùng lại __________|
```

Với một `FileChannel` đọc dữ liệu trong khi `WritableByteChannel` ghi ra nơi khác, mẫu cơ bản là:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ReadableByteChannel;
import java.nio.channels.WritableByteChannel;

static void copy(ReadableByteChannel source,
                 WritableByteChannel destination) throws IOException {
    ByteBuffer buffer = ByteBuffer.allocate(8192);

    while (true) {
        buffer.clear();                // Chuẩn bị nhận dữ liệu mới
        int count = source.read(buffer);

        if (count == -1) {
            break;                     // Hết nguồn
        }
        if (count == 0) {
            continue;                  // Không có byte mới; tùy channel cần chờ phù hợp
        }

        buffer.flip();                 // Chỉ đọc count byte mới nhận
        while (buffer.hasRemaining()) {
            int written = destination.write(buffer);
            if (written == 0) {
                // Với kênh non-blocking, cần chờ khả năng ghi (Selector, v.v.).
                // Không spin vô hạn ở đây trong ứng dụng thực tế.
                throw new IOException("Destination did not accept data");
            }
        }
    }
}
```

Đây là **phương thức minh họa**, đặt bên trong lớp Java với các import nêu trên. Mẫu phù hợp cho kênh ghi kiểu blocking hoặc nơi có chính sách rõ ràng khi `write` không tiến triển; đối với I/O không đồng bộ và non-blocking cần quản lý buffer/lượt đọc khác nhau.

Trong thực tế:

1. `clear()` thông báo “buffer sẵn sàng nhận tối đa `capacity` byte”, không cần xóa byte cũ.
2. `source.read(buffer)` tăng `position` theo số byte đọc được. Số trả về có thể thấp hơn dung lượng buffer, bằng 0, hoặc `-1` khi hết dữ liệu.
3. `flip()` đặt `limit` bằng số byte đã nhận trong lượt này, không cho bộ tiêu thụ đọc nhầm phần còn sót của lượt trước bằng relative `get`.
4. `write` có thể tiêu thụ ít hơn toàn bộ byte còn lại. Cần xử lý phần chưa gửi xong; nếu chỉ gửi một phần rồi `clear()`, dữ liệu **chưa gửi sẽ bị bỏ khỏi phạm vi logic** dù các byte vẫn ở RAM.

Đặc biệt ở socket non-blocking, khi vừa đọc vừa ghi, `compact()` thường được dùng để giữ phần chưa xử lý; `clear()` chỉ hợp lý khi không còn dữ liệu cần giữ lại.

## 8. `clear()` không liên quan đến việc xóa tệp hoặc giải phóng bộ nhớ

Ba thao tác hoàn toàn khác nhau:

- **`buffer.clear()`**: đặt lại cursor/trạng thái đọc ghi của buffer, không chỉnh nội dung file.
- **Ghi đè dữ liệu bên trong buffer**: dùng `put` hoặc `Arrays.fill` với vùng nhớ có thể ghi, làm byte lưu trong vùng cụ thể thay đổi.
- **Đóng hoặc giải phóng tài nguyên**: ví dụ `FileChannel.close()` đóng handle của channel; riêng `ByteBuffer.clear()` không đóng channel, không `free()` và không bắt GC thu hồi bộ nhớ.

Với **heap buffer** tạo bằng `ByteBuffer.allocate(n)`, có thể lấy mảng backing qua `array()` khi buffer hỗ trợ; với **direct buffer** tạo qua `ByteBuffer.allocateDirect(n)`, `array()` thường ném `UnsupportedOperationException` vì không có mảng Java được truy xuất theo cách đó. Cả hai loại buffer vẫn có `clear()` mang ngữ nghĩa metadata giống nhau.

Với **read-only buffer** từ `asReadOnlyBuffer()`, việc thay đổi `position`/`limit` qua `clear()` vẫn hợp lệ, nhưng `put` sẽ ném `ReadOnlyBufferException`. Điều này cho thấy `clear()` không tự thực hiện ghi đè dữ liệu.

## 9. Cần xóa byte nhạy cảm thật sự thì làm gì?

Đối với dữ liệu như mật khẩu, khóa mật mã hay nội dung riêng tư, `clear()` **không bảo đảm xóa dữ liệu cũ**. Nếu muốn giảm thời gian dữ liệu còn nằm trong vùng lưu trữ của buffer có thể ghi, phải chủ động ghi đè phần vùng nhớ liên quan.

Ví dụ phương thức ghi đè toàn bộ **vùng nhìn thấy qua một `ByteBuffer` có thể ghi**:

```java
import java.nio.ByteBuffer;

static void overwriteVisibleBytes(ByteBuffer buffer) {
    buffer.clear();                         // Mở giới hạn đến capacity
    while (buffer.hasRemaining()) {
        buffer.put((byte) 0);              // Ghi đè từng byte
    }
    buffer.clear();                         // Chuẩn bị trạng thái tái sử dụng
}
```

Đây là **phương thức minh họa** được đặt trong một lớp Java. Nó thay đổi storage thực sự; thời gian thực hiện tỷ lệ với `capacity`. Nếu buffer là read-only, `put` sẽ ném `ReadOnlyBufferException`. Nếu buffer là một `slice()`, chỉ các byte nằm trong vùng mà slice có thể nhìn thấy được ghi đè. Việc ghi đè một vùng chia sẻ cũng làm thay đổi dữ liệu nhìn thấy qua các view/duplicate liên quan.

Với mảng byte thuần:

```java
java.util.Arrays.fill(secretBytes, (byte) 0);
```

**Giới hạn bảo mật phải nói rõ:** Java/JVM, thư viện, GC, hệ điều hành, file hoán đổi, bản sao trong heap/native memory hoặc JIT có thể giữ thêm bản dữ liệu. Ghi đè một buffer/mảng không phải bằng chứng đã xóa mọi bản sao trên toàn hệ thống, và không đảm bảo “secure erase”. Hạn chế sao chép dữ liệu nhạy cảm ngay từ thiết kế, kiểm soát vòng đời và sử dụng API chuyên dụng khi có yêu cầu bảo mật cao.

## 10. `slice()`, `duplicate()` và dữ liệu còn lưu

`slice()` và `duplicate()` tạo ra các buffer với trạng thái `position`/`limit` riêng nhưng **chia sẻ nội dung storage** với buffer gốc.

```java
ByteBuffer original = ByteBuffer.allocate(4);
original.put(new byte[] {1, 2, 3, 4});
original.flip();

ByteBuffer view = original.duplicate();
view.clear();

System.out.println(view.get(2));      // 3
System.out.println(original.get(2));  // 3
```

Đây là đoạn minh họa trong phương thức (cần `import java.nio.ByteBuffer;`). `view.clear()` chỉ đặt lại state của view; không xóa phần storage chia sẻ và không đặt lại `position` hay `limit` của `original`. Tương tự, `slice()` có offset và capacity tương ứng với phần vùng nhớ được chọn; `clear()` trên slice chỉ đặt lại state của slice.

Điều này quan trọng với ứng dụng tái sử dụng buffer pool: nếu một thành phần đọc thẳng từ backing storage hoặc một view khác, dữ liệu cũ vẫn có thể thấy được cho đến khi storage được ghi đè.

## 11. Sai lầm thường gặp và cách sửa

| Quan niệm/sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “`clear()` xóa toàn bộ byte/char.” | Byte cũ vẫn đọc được nếu phạm vi cho phép | Hiểu `clear` chỉ reset `position`, `limit`, `mark` |
| “`clear()` tương đương `Arrays.fill(...,0)`.” | Có thể rò dữ liệu hoặc bài kiểm tra bảo mật sai | Ghi đè chủ động khi cần, hiểu giới hạn bảo đảm của ghi đè |
| Ghi ít byte rồi `clear()` để bắt đầu đọc | `limit=capacity`, có thể đọc dữ liệu dư cũ | `flip()` sau ghi, đọc qua `remaining()` |
| Dùng `array().length` để xác định số byte mới | Độ dài storage thường lớn hơn lượng dữ liệu hợp lệ | Sử dụng `remaining()` sau `flip()` hoặc theo bộ đếm giao thức |
| Gọi `clear()` khi còn byte chưa gửi qua channel | Mất trạng thái theo dõi phần dữ liệu chưa gửi | Chờ ghi hết hoặc dùng `compact()` và quản lý backpressure |
| `clear()` khiến direct buffer được giải phóng | Tốn bộ nhớ native trong thời gian không mong muốn | Quản lý vòng đời đối tượng/tài nguyên và áp lực cấp phát |
| `clear()` thay đổi trạng thái mọi `duplicate()` | View còn chỉ số riêng; storage vẫn chia sẻ | Xem từng instance có state riêng, chia sẻ dữ liệu |
| Gọi `array()` với mọi `ByteBuffer` | Direct/read-only buffer có thể không hỗ trợ backing array công khai | Sử dụng `get`/`put` hoặc kiểm tra `hasArray()` trước |

## 12. Thực hành tự kiểm tra

### Câu 1: `clear()` đặt lại gì?

```java
ByteBuffer b = ByteBuffer.allocate(5);
b.put((byte) 7);
b.put((byte) 8);
b.clear();
```

**Đáp án:** `position=0`, `limit=5`, `capacity=5`; mark (nếu có) bị bỏ. Các byte `7`, `8` vẫn nằm tại vị trí 0, 1 cho đến khi bị ghi đè.

### Câu 2: Tại sao gọi `flip()` sau `clear()` ngay lập tức lại không trả dữ liệu đã viết ở lượt trước?

**Đáp án:** `clear()` đặt `position=0`; `flip()` lập tức đặt `limit=position=0`, làm `remaining()=0`. Byte cũ vẫn ở storage, nhưng vùng đọc tương đối hiện tại rỗng.

### Câu 3: Vì sao `get(2)` có thể đọc được byte cũ mà `get()` không đọc được cùng byte sau khi `flip()` với chỉ hai byte mới?

**Đáp án:** Sau `flip()`, `limit=2`. Cả absolute `get(2)` và relative `get()` khi đã đọc hết hai byte đều bị giới hạn bởi `limit`; `get(2)` sẽ ném `IndexOutOfBoundsException`, còn relative `get()` sẽ ném `BufferUnderflowException` nếu không còn phần tử. Trước `flip()`, `clear()` mở `limit=capacity` nên absolute `get(2)` mới có thể thấy byte cũ. Đây là hai **thời điểm trạng thái khác nhau**.

### Câu 4: Khi `FileChannel.read(buffer)` đọc được 3 byte vào buffer có `capacity=8192`, tại sao không được gửi cả 8192 byte đi?

**Đáp án:** Chỉ 3 byte mới thuộc lượt đọc. Sau `flip()`, `limit=3`; dùng `remaining()` hoặc `channel.write(buffer)` có kiểm soát để gửi đúng dữ liệu hợp lệ. Các byte còn lại không phải thông điệp hiện tại.

### Câu 5: Một view `duplicate()` gọi `clear()` có làm mất dữ liệu của buffer gốc không?

**Đáp án:** Không. Nó chỉ reset state của chính view; dữ liệu vẫn chia sẻ. Nếu view thực hiện `put`, lúc đó storage chia sẻ mới có thể thay đổi.

## Tóm tắt cần nhớ

```text
clear()   = sẵn sàng GHI từ đầu, không xóa storage
flip()    = sẵn sàng ĐỌC số phần tử vừa ghi
rewind()  = quay về đầu vùng đã giới hạn để đọc/ghi lại
compact() = giữ phần còn lại, dồn về đầu để ghi tiếp
overwrite = ghi đè byte nếu thực sự cần thay đổi storage
```

Quy tắc áp dụng thực tế: **dùng `clear()` để tái sử dụng buffer, `flip()` để xác định vùng dữ liệu mới có thể đọc, và ghi đè chủ động khi cần thay đổi nội dung lưu trữ.** Đừng coi bất kỳ thao tác chuyển state nào là cơ chế xóa an toàn dữ liệu.

## Tài liệu tham khảo

- Java SE 21, `java.nio.Buffer` (hợp đồng `clear`, `flip`, `rewind`, `mark`, `reset`): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/Buffer.html
- Java SE 21, `java.nio.ByteBuffer` (relative/absolute operations, `compact`, backing array, direct buffer): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 21, `java.nio.channels.ReadableByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ReadableByteChannel.html
- Java SE 21, `java.nio.channels.WritableByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/WritableByteChannel.html

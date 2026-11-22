# Java NIO Buffer: slice, duplicate, read-only buffer và trạng thái vị trí riêng

## 1. Mục tiêu của bài

Khi xử lý dữ liệu nhị phân bằng Java NIO, một `ByteBuffer` không chỉ là mảng byte. Nó gồm hai phần cần phân biệt:

- **Nội dung (content):** vùng nhớ chứa các byte.
- **Trạng thái của từng đối tượng buffer:** `capacity`, `limit`, `position`, `mark` và các thuộc tính như read-only, direct/heap, byte order.

Ba phương thức quan trọng:

- `slice()` tạo **cửa sổ con** bắt đầu từ `position` hiện tại tới `limit`.
- `duplicate()` tạo **một góc nhìn khác trên cùng vùng byte**, ban đầu có cùng capacity, limit, position và mark.
- `asReadOnlyBuffer()` tạo **góc nhìn chỉ đọc** trên cùng vùng byte, ban đầu có cùng trạng thái vị trí/giới hạn.

**Điểm cốt lõi:** các view này **chia sẻ dữ liệu**, nhưng **không chia sẻ biến `position`, `limit` và `mark`**. Đổi position của view A không làm position của view B thay đổi. Ngược lại, sửa một byte trong vùng nhớ chung qua view có quyền ghi thì các view cùng nhìn vào byte ấy thấy giá trị mới.

Đây là cơ chế khác với sao chép dữ liệu: tạo view thường không copy toàn bộ nội dung. Vì thế view phù hợp để truyền một đoạn buffer cho hàm xử lý mà không phải tạo mảng byte mới, đồng thời phải quản lý quyền sửa và vòng đời vùng nhớ cẩn thận.

## 2. Ôn lại capacity, limit, position và mark

Mỗi `Buffer` có các chỉ số thỏa bất biến:

```text
0 <= position <= limit <= capacity
```

- `capacity`: sức chứa tối đa của **view đó**. Không thay đổi trong vòng đời view.
- `limit`: ranh giới trên mà thao tác đọc/ghi thông thường không được vượt qua (không bao gồm phần tử tại limit).
- `position`: chỉ số phần tử kế tiếp sẽ được đọc/ghi bởi thao tác tương đối (`get()`, `put(...)`).
- `mark`: mốc tùy chọn do `mark()` ghi tại position hiện tại để `reset()` quay về. Mark có thể chưa được đặt (undefined).
- `remaining()`: bằng `limit - position`.
- `hasRemaining()`: đúng nếu `position < limit`.

Các phép biến đổi trạng thái hay dùng:

| Phép gọi | Ảnh hưởng |
|---|---|
| `get()` / `put(byte)` | Đọc/ghi từ position hiện tại rồi tăng position 1 |
| `get(index)` / `put(index, value)` | Truy cập tuyệt đối theo chỉ số trong view; **không đổi position** |
| `position(n)` | Đặt position; mark bị bỏ nếu mark lớn hơn position mới |
| `limit(n)` | Đặt limit; nếu position lớn hơn limit thì position hạ về limit; mark lớn hơn limit bị bỏ |
| `mark()` | Lưu position hiện tại làm mark |
| `reset()` | Đưa position về mark; lỗi `InvalidMarkException` nếu mark chưa có/hết hiệu lực |
| `flip()` | `limit = position` cũ, `position = 0`, bỏ mark; thường chuẩn bị đọc dữ liệu vừa ghi |
| `clear()` | `position = 0`, `limit = capacity`, bỏ mark; **không xóa byte vật lý** |
| `rewind()` | `position = 0`, giữ limit, bỏ mark |
| `compact()` | Dồn các byte còn lại lên đầu view, đặt position sau phần đã dồn, limit = capacity; **có sửa nội dung** và không dùng được với read-only buffer |

**Lưu ý:** `clear()` là thao tác trạng thái, tên của nó không có nghĩa là đặt mọi byte bằng 0. Một view có capacity riêng, vì vậy gọi `clear()` trên `slice` không mở rộng view ra ngoài vùng slice.

Ví dụ trạng thái một buffer 8 byte:

```text
ByteBuffer capacity=8, position=2, limit=6

Index:      0   1   2   3   4   5   6   7
Nội dung: [10, 11, 12, 13, 14, 15, 16, 17]
                   ^               ^
                position          limit
Vùng remaining: các index [2, 6) = 2, 3, 4, 5.
```

Các chỉ số nói trên là **chỉ số cục bộ của từng view**, không nhất thiết là vị trí trong mảng gốc hay trong tệp.

## 3. `slice()`: view con có chỉ số bắt đầu lại từ 0

`slice()` trên `ByteBuffer` tạo một view chứa vùng `[position, limit)` tại **thời điểm gọi**.

Nếu buffer gốc capacity 8, position 2, limit 6:

```text
Original index:  0  1  2  3  4  5  6  7
Original bytes: 10 11 12 13 14 15 16 17
                      |-----------|
                      Vùng [2,6)

Slice index:           0  1  2  3
Slice bytes:          12 13 14 15

Original: capacity=8, position=2, limit=6
Slice:    capacity=4, position=0, limit=4, mark=undefined
```

Ý nghĩa chính:

1. View slice nhìn vào **cùng bốn byte** tại index gốc 2–5. `slice.get(0)` chính là byte mà `original.get(2)` nhìn thấy.
2. `slice.put(0, value)` (nếu cho phép ghi) cập nhật byte ở vị trí gốc 2; hai bên cùng thấy giá trị mới.
3. Thay `slice.position(...)`, `slice.limit(...)`, `slice.mark()` chỉ đổi trạng thái **slice**. Vị trí của original vẫn giữ nguyên.
4. Thay original.position/limit **sau khi tạo** không làm thay đổi kích thước hay vùng nhớ mà slice đã đại diện.
5. Slice có capacity giới hạn bởi đoạn đã chọn. Nó không thể truy cập các byte bên ngoài đoạn đó bằng các API chỉ số thông thường.
6. Original là read-only thì slice cũng read-only; original direct thì slice cũng direct.

Đoạn minh họa (không phải chương trình độc lập):

```java
ByteBuffer original = ByteBuffer.wrap(
        new byte[]{10, 11, 12, 13, 14, 15, 16, 17});

original.position(2);
original.limit(6);

ByteBuffer slice = original.slice();

System.out.println(slice.capacity()); // 4
System.out.println(slice.get(0));      // 12

slice.put(1, (byte) 99);
System.out.println(original.get(3));   // 99
System.out.println(original.position()); // 2
```

Chú ý: `ByteBuffer.slice(int index, int length)` còn cho phép tạo view của một đoạn cụ thể theo **chỉ số tuyệt đối trong buffer nhận lời gọi**, không cần thay position trước. Biến thể này có từ Java 13, nên dùng được trong Java 17:

```java
ByteBuffer selected = original.slice(2, 3);
// selected chứa original ở các index 2, 3, 4.
// selected.position() == 0, selected.limit() == selected.capacity() == 3.
```

Ở đây `index` là chỉ số của `original` hiện tại, **không phải offset cộng thêm vào `original.position()`**. Cần `0 <= index` và `0 <= length <= original.limit() - index`; vi phạm gây `IndexOutOfBoundsException`.

### Hai lớp slice lồng nhau

Nếu `first = root.slice()` rồi `second = first.slice()`, mọi chỉ số của `second` được tính từ vị trí của `first` tại thời điểm tạo `second`. Các lớp view cùng chia sẻ vùng byte tương ứng, nhưng có các vị trí riêng. Khi cần quy đổi index để debug, nên ghi chú offset của từng lớp:

```text
root absolute index = rootOffsetOfFirst + firstOffsetOfSecond + secondIndex
```

Đây là quan hệ để tính chỉ số trong cây slice của **một vùng nhớ đã biết**, không phải API tự động của `ByteBuffer`. Khi xây dựng parser nhiều tầng, nên truyền offset và độ dài rõ ràng để tránh nhầm.

## 4. `duplicate()`: view toàn vùng với con trỏ riêng

`duplicate()` tạo một buffer mới trỏ tới **cùng vùng dữ liệu tương ứng** của buffer nguồn. Với `ByteBuffer`, view mới có ban đầu:

- `capacity` **bằng** nguồn.
- `limit` **bằng** nguồn.
- `position` **bằng** nguồn.
- `mark` được **sao trạng thái giá trị** từ nguồn nếu đã xác định; sau đó mark mỗi view hoạt động độc lập.
- Thuộc tính direct/heap và read-only được giữ tương ứng.
- **Dữ liệu vẫn dùng chung**, không có bản copy byte riêng.

Khác biệt lớn với `slice` là duplicate vẫn có **cùng hệ chỉ số/capacity** của buffer nguồn. Nó phù hợp để hai thành phần có con trỏ duyệt riêng nhưng cùng tham chiếu một tập byte.

```java
ByteBuffer original = ByteBuffer.wrap(new byte[]{10, 20, 30, 40, 50});
original.position(1);
original.limit(4);
original.mark();

ByteBuffer duplicate = original.duplicate();
duplicate.position(3);  // original vẫn position=1

duplicate.put(2, (byte) 99);  // absolute put: không đổi vị trí duplicate
System.out.println(original.get(2));  // 99
System.out.println(original.position()); // 1

duplicate.reset(); // Mark được sao khi duplicate() gọi: về position=1.
```

Đoạn này minh họa Java với import `java.nio.ByteBuffer`. Vì duplicate và original dùng chung byte, việc thay limit trên duplicate không cấm original dùng vùng dữ liệu tương ứng nếu original vẫn có phạm vi hợp lệ.

**Cảnh báo về `clear()` trên duplicate:** duplicate có capacity bằng original. Nếu original đang limit thấp hơn capacity để biểu thị số byte dữ liệu hợp lệ, `duplicate.clear()` sẽ mở rộng limit của **duplicate** lên capacity. Điều đó không copy và không “tạo” dữ liệu hợp lệ mới; có thể làm lộ dữ liệu cũ trong buffer nếu chương trình quên giới hạn logic.

## 5. `asReadOnlyBuffer()`: chặn ghi qua view, không đóng băng dữ liệu

`asReadOnlyBuffer()` tạo **view chỉ đọc** trên cùng bộ nhớ, có ban đầu cùng capacity/position/limit/mark với nguồn (tương tự duplicate). Phương thức `isReadOnly()` của view trả `true`.

- Cho phép `get()`, `get(index)`, thay `position`, `limit`, `mark`, `reset`, `flip`, `clear`, `rewind`. Read-only **không** có nghĩa trạng thái vị trí bị khóa.
- Cấm các thao tác sửa nội dung qua view này, ví dụ `put(...)`, `compact()`: ném `ReadOnlyBufferException`.
- Nếu nguồn gốc hoặc một writable view khác cập nhật các byte chung, read-only view **vẫn thấy nội dung mới**. Read-only bảo vệ **đường truy cập qua view**, không tạo immutable snapshot.
- Tạo `duplicate()` hoặc `slice()` từ read-only view vẫn tạo read-only view; không thể dùng chúng để khôi phục quyền ghi.
- Read-only heap `ByteBuffer` không cung cấp trực tiếp mảng nền qua `array()`; `hasArray()` sẽ là `false`. Tương tự, direct buffer thường không có mảng `byte[]` có thể truy cập.

Ví dụ:

```java
ByteBuffer writable = ByteBuffer.wrap(new byte[]{1, 2, 3});
ByteBuffer readOnly = writable.asReadOnlyBuffer();

readOnly.position(1);      // Hợp lệ: chỉ thay con trỏ của view.
writable.put(1, (byte) 9); // Hợp lệ: nguồn vẫn có quyền ghi.

System.out.println(readOnly.get(1));  // 9: thấy sửa đổi chung
System.out.println(readOnly.isReadOnly()); // true

// readOnly.put(1, (byte) 8); // Ném ReadOnlyBufferException.
```

Nếu cần **dữ liệu bất biến thực sự**, phải tạo **bản sao tách rời** rồi kiểm soát toàn bộ cách truy cập tới bản sao. Ví dụ: tạo `ByteBuffer.allocate(source.remaining())`, chuyển dữ liệu từ view duplicate, `flip()`, sau đó chỉ phân phối read-only view của bản sao đó và không để lộ buffer writable của bản sao.

> **Read-only view ≠ immutable storage ≠ thread-safe storage.** Read-only chỉ ngăn ghi thông qua đối tượng view cụ thể.

## 6. Bảng so sánh trạng thái khi vừa tạo

Giả sử `src` là writable `ByteBuffer` capacity=8, position=2, limit=6, mark đã được đặt ở position=2.

| View mới | Chia sẻ byte với src? | Capacity mới | Position mới | Limit mới | Mark mới | Có được ghi qua view? |
|---|---|---:|---:|---:|---|---|
| `src.slice()` | Có, vùng [2,6) | 4 | 0 | 4 | Chưa xác định | Có, nếu src writable |
| `src.slice(1,3)` | Có, vùng [1,4) | 3 | 0 | 3 | Chưa xác định | Có, nếu src writable |
| `src.duplicate()` | Có, toàn vùng src | 8 | 2 | 6 | Sao trạng thái mark 2 | Có, nếu src writable |
| `src.asReadOnlyBuffer()` | Có, toàn vùng src | 8 | 2 | 6 | Sao trạng thái mark 2 | **Không** |
| `ByteBuffer.allocate(8)` | **Không** | 8 | 0 | 8 | Chưa xác định | Có |

Mỗi cột trạng thái là **giá trị ban đầu của đối tượng view mới**, không phải biến dùng chung; sau khi tạo, mỗi đối tượng tự duy trì position/limit/mark. Khi gọi `duplicate()` hoặc `asReadOnlyBuffer()` trên buffer đã bị read-only, view mới cũng read-only.

Một số lời gọi thay đổi metadata của original trước khi tạo view sẽ thay đổi **trạng thái ban đầu** của view được tạo sau đó. Các view đã tạo trước vẫn giữ trạng thái riêng của chúng.

## 7. Ví dụ Java 17+ đầy đủ: cùng dữ liệu, các con trỏ độc lập

Ví dụ dưới đây trình diễn bốn đối tượng `root`, `slice`, `duplicate` và `readOnly`. Mọi kết quả đều xác định, không phụ thuộc vị trí file hay thiết bị.

Lưu thành **`BufferViewsDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;

public class BufferViewsDemo {
    public static void main(String[] args) {
        ByteBuffer root = ByteBuffer.wrap(
                new byte[]{10, 11, 12, 13, 14, 15, 16, 17});

        root.position(2);
        root.limit(6);
        root.mark(); // mark của root đặt tại position=2

        ByteBuffer slice = root.slice();
        ByteBuffer duplicate = root.duplicate();
        ByteBuffer readOnly = root.asReadOnlyBuffer();

        System.out.printf("root: p=%d, l=%d, c=%d%n",
                root.position(), root.limit(), root.capacity());
        System.out.printf("slice: p=%d, l=%d, c=%d%n",
                slice.position(), slice.limit(), slice.capacity());
        System.out.printf("duplicate: p=%d, l=%d, c=%d%n",
                duplicate.position(), duplicate.limit(), duplicate.capacity());
        System.out.printf("readOnly: p=%d, l=%d, c=%d%n",
                readOnly.position(), readOnly.limit(), readOnly.capacity());

        slice.position(1);
        duplicate.position(4);
        readOnly.position(3);

        System.out.printf("positions: root=%d, slice=%d, duplicate=%d, readOnly=%d%n",
                root.position(), slice.position(),
                duplicate.position(), readOnly.position());

        slice.put(0, (byte) 99); // slice index 0 -> root index 2
        root.put(3, (byte) 88);  // root index 3 -> slice index 1

        System.out.println("root[2]=" + root.get(2));
        System.out.println("readOnly[2]=" + readOnly.get(2));
        System.out.println("slice[1]=" + slice.get(1));
        System.out.println("readOnly.isReadOnly=" + readOnly.isReadOnly());

        try {
            readOnly.put(2, (byte) 7);
            System.out.println("unreachable");
        } catch (ReadOnlyBufferException ex) {
            System.out.println("write through readOnly: rejected");
        }

        duplicate.reset(); // duplicate được sao mark=2 lúc tạo
        root.reset();      // mark riêng của root vẫn là 2

        System.out.printf("after reset: root=%d, duplicate=%d, slice=%d%n",
                root.position(), duplicate.position(), slice.position());
    }
}
```

Chạy:

```bash
javac BufferViewsDemo.java
java BufferViewsDemo
```

**Stdout chính xác:**

```text
root: p=2, l=6, c=8
slice: p=0, l=4, c=4
duplicate: p=2, l=6, c=8
readOnly: p=2, l=6, c=8
positions: root=2, slice=1, duplicate=4, readOnly=3
root[2]=99
readOnly[2]=99
slice[1]=88
readOnly.isReadOnly=true
write through readOnly: rejected
after reset: root=2, duplicate=2, slice=1
```

Diễn giải:

1. `root.slice()` chọn dải root index 2–5; khi nhìn từ slice, dải này có index 0–3.
2. `duplicate` và `readOnly` được tạo khi root ở position=2, limit=6; chúng bắt đầu với cùng vị trí và giới hạn đó, nhưng không trói nhau về sau.
3. `slice.position(1)`, `duplicate.position(4)` và `readOnly.position(3)` không làm `root.position()` đổi khỏi 2.
4. `slice.put(0, 99)` thay byte root index 2. `readOnly.get(2)` thấy 99 dù read-only không cho phép tự ghi.
5. `root.put(3, 88)` thay byte tương ứng với `slice.get(1)`. Các phép `get(index)/put(index,...)` tuyệt đối không đổi position.
6. `readOnly.put(...)` ném `ReadOnlyBufferException` và được bắt; không in `unreachable`.
7. Mark của duplicate đã được sao khi tạo, nên `duplicate.reset()` đưa duplicate từ position 4 về 2; root reset riêng về 2; slice vẫn ở 1.

## 8. Bẫy byte order riêng của ByteBuffer view

Đây là chi tiết dễ bị bỏ qua khi buffer chứa `short`, `int`, `long` hay `double` thay vì chỉ byte:

**Theo API Java 17, `ByteBuffer.slice()`, `slice(index,length)`, `duplicate()` và `asReadOnlyBuffer()` tạo view có byte order ban đầu là `BIG_ENDIAN`**, kể cả khi buffer nguồn đã chọn `LITTLE_ENDIAN`. Vì vậy không nên tự giả định view mới tự kế thừa cài đặt order của nguồn.

Đoạn minh họa:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

ByteBuffer base = ByteBuffer.allocate(8);
base.order(ByteOrder.LITTLE_ENDIAN);

ByteBuffer view = base.duplicate();
System.out.println(base.order()); // LITTLE_ENDIAN
System.out.println(view.order()); // BIG_ENDIAN theo đặc tả Java 17

view.order(base.order());        // Đặt rõ khi cần đọc cùng định dạng.
```

Đoạn này **không phải chương trình độc lập**; các lệnh `import` cần đặt đầu file khi đưa vào một class. Thói quen an toàn khi thao tác nhiều byte: đặt `view.order(expectedOrder)` rõ ràng ngay sau khi tạo view; đừng dùng giá trị mặc định như một giả định ngầm.

Khác với điều đó, **typed view** như `asIntBuffer()` có quy tắc byte order và đơn vị index riêng: nó xem byte dưới dạng `int` (mỗi phần tử bốn byte) và dùng byte order của nguồn **tại thời điểm view được tạo**. Khi so sánh `ByteBuffer` với `IntBuffer` phải lưu ý đơn vị index (byte so với số nguyên), tránh áp dụng tùy tiện một công thức cho cả hai.

## 9. Slice theo phần dữ liệu hợp lệ thay vì toàn bộ capacity

Mẫu xử lý NIO thường gặp là:

1. Ghi byte vào `ByteBuffer` qua `put(...)`; position tiến theo số byte đã ghi.
2. `flip()` để đặt limit bằng số byte có dữ liệu hợp lệ và position về 0.
3. Tạo view tới một phân đoạn, chẳng hạn header hoặc payload.
4. Đưa từng view tới các hàm đọc; chúng duy trì position riêng.

Ví dụ (minh họa):

```java
ByteBuffer packet = ByteBuffer.allocate(32);
packet.put(new byte[]{1, 2, 3, 4, 5, 6});
packet.flip(); // position=0, limit=6, capacity=32

ByteBuffer header = packet.slice(0, 2);
ByteBuffer payload = packet.slice(2, 4);

// header  chứa hai byte [1,2]
// payload chứa bốn byte [3,4,5,6]
// packet.position() vẫn bằng 0.
```

Những view này có capacity đúng bằng vùng logic. Nếu parser đọc quá limit sẽ nhận `BufferUnderflowException` (đọc tương đối) hoặc `IndexOutOfBoundsException` (truy cập tuyệt đối vượt limit). Không nên xử lý ngoại lệ đó thay cho việc xác minh định dạng packet; luôn kiểm tra độ dài theo giao thức trước khi tạo slice.

Nếu dùng `slice()` không tham số:

```java
packet.position(2);
ByteBuffer payload = packet.slice();
// Bắt đầu tại index 2 của packet, đến packet.limit() hiện tại.
```

Khác biệt: `slice()` dựa vào **position hiện tại**, còn `slice(2, 4)` dùng **index 2 được nêu tường minh** mà không cần thay position. Chọn biến thể phù hợp để giảm tác dụng phụ lên con trỏ đọc của caller.

## 10. Tạo view an toàn trong API

Khi thiết kế API nhận và trả `ByteBuffer`, hãy xác định hàm có quyền thay position của caller hay không.

### Mẫu A: Hàm chỉ đọc, giữ position/limit của caller

```java
static int sumRemainingUnsignedBytes(ByteBuffer source) {
    ByteBuffer cursor = source.duplicate();
    int sum = 0;
    while (cursor.hasRemaining()) {
        sum += Byte.toUnsignedInt(cursor.get());
    }
    return sum;
}
```

Hàm trên là **đoạn phương thức minh họa**, cần import `java.nio.ByteBuffer` và được đặt trong một class. Nó dùng `duplicate()` để di chuyển con trỏ **riêng** mà không thay source.position/limit. Nó không ngăn tiến trình khác sửa nội dung chung đồng thời; nếu dữ liệu cần ổn định, phải phối hợp quyền sở hữu hoặc copy.

### Mẫu B: Chỉ cấp quyền đọc dữ liệu cho bên nhận

```java
static ByteBuffer payloadView(ByteBuffer packet, int offset, int length) {
    return packet.slice(offset, length).asReadOnlyBuffer();
}
```

Hàm trả view chỉ đọc, có vùng chỉ số cục bộ `0..length-1`. Bên nhận không sửa được qua view trả về, nhưng nếu giữ reference tới buffer nguồn, bên tạo vẫn có thể sửa dữ liệu. Không quảng bá “immutable data” hay “snapshot” cho loại API này.

### Mẫu C: Cần snapshot độc lập

```java
static ByteBuffer readOnlySnapshot(ByteBuffer source) {
    ByteBuffer cursor = source.duplicate();
    ByteBuffer copy = ByteBuffer.allocate(cursor.remaining());
    copy.put(cursor);
    copy.flip();
    return copy.asReadOnlyBuffer();
}
```

Đây là bản **copy độc lập** của vùng `remaining` tại thời điểm copy. Hàm dùng thêm bộ nhớ tương ứng và giữ nguyên position của `source`. Để thực sự bảo vệ snapshot theo ranh giới API, không để lộ view writable `copy` ở nơi khác; đồng thời đảm bảo nguồn không bị sửa đồng thời trong lúc sao chép nếu cần snapshot nhất quán.

Nếu dữ liệu chứa kiểu nguyên thủy đa byte, nên đặt `order` rõ ràng ở view nhận/trả vì các view byte có thể mặc định BIG_ENDIAN.

## 11. Concurrency và vòng đời bộ nhớ

**Position riêng không đồng nghĩa thread-safe.** Java NIO `Buffer` nhìn chung không được thiết kế để nhiều luồng thao tác đồng thời trên **cùng một đối tượng** mà không phối hợp.

Tạo duplicate riêng cho mỗi tác vụ giúp các tác vụ **không tranh chấp một biến position**. Tuy nhiên chúng vẫn chia sẻ byte. Nếu một luồng ghi root trong khi luồng khác đọc read-only view, vẫn có thể xảy ra tranh chấp dữ liệu, đọc không nhất quán hoặc yêu cầu về memory visibility. Read-only view không tự cấp khóa hay đảm bảo snapshot.

Một số nguyên tắc thực tế:

- Cho nhiều luồng **chỉ đọc trên dữ liệu không thay đổi**, có thể cấp mỗi luồng một duplicate/read-only view riêng để độc lập con trỏ, sau khi bảo đảm dữ liệu đã được công bố an toàn.
- Nếu có thể sửa vùng nhớ chung, cần đồng bộ thích hợp, chia vùng không chồng lấn với hợp đồng rõ ràng, hoặc sao chép để cô lập dữ liệu.
- Direct buffer (`ByteBuffer.allocateDirect`) và heap buffer đều có thể dùng slice/duplicate/read-only view. View chỉ giữ tham chiếu tới vùng nhớ chung; không suy ra thời điểm giải phóng tài nguyên chỉ từ việc bỏ một reference.
- Với buffer đến từ memory mapping hoặc các nguồn dữ liệu được quản lý vòng đời riêng, cần xem xét khả năng file/nguồn thay đổi, đồng bộ và tính sẵn sàng của vùng nhớ. Read-only view không bảo đảm tệp nguồn luôn còn nguyên.

## 12. Những lỗi phổ biến và cách tránh

1. **Cho rằng `slice()` đã copy dữ liệu.** Sai: slice chia sẻ byte; sửa một bên thấy ở bên kia. Nếu muốn dữ liệu tách rời, hãy copy.
2. **Cho rằng `duplicate()` dùng chung position.** Sai: nó sao trạng thái ban đầu, sau đó các con trỏ độc lập.
3. **Cho rằng read-only view là snapshot.** Sai: bên có quyền ghi vào cùng storage vẫn thay nội dung mà read-only view đọc thấy.
4. **Nhầm `slice.get(0)` là root.get(0).** Sai: `slice.get(0)` tương ứng với **root.position tại lúc tạo slice** (với `slice()`) hoặc root index được truyền (với `slice(index,length)`).
5. **Tính offset hai lần.** `slice(index,length)` đã chọn vùng theo index của buffer nhận; không cộng thêm buffer.position một lần nữa.
6. **Không kiểm tra limit trước khi tạo `slice(index,length)`.** Vượt `limit` sẽ ném `IndexOutOfBoundsException`; capacity lớn hơn không cứu được.
7. **Mong `clear()` xóa byte.** Sai: `clear` chỉ đặt lại position/limit/mark. Nếu cần tẩy dữ liệu nhạy cảm, phải thực hiện chính sách xóa/ghi đè riêng phù hợp với kiểu bộ nhớ và yêu cầu bảo mật.
8. **Đọc sai byte order sau khi duplicate/slice.** Với ByteBuffer Java 17, hãy đặt `order(...)` minh bạch khi đọc/ghi các primitive đa byte.
9. **Dùng `array()` trên read-only/direct buffer.** `hasArray()` có thể `false`; `array()` có thể ném `ReadOnlyBufferException` hoặc `UnsupportedOperationException`.
10. **Thay đổi `limit` rồi giả định view khác thay theo.** Mỗi view có limit riêng. Khi muốn áp dụng giới hạn logic mới cho nhiều view, phải quản lý/thiết lập ở từng view.
11. **Giữ mark cũ sau `flip/clear/rewind`.** Những thao tác này loại bỏ mark của **đối tượng được gọi**; `reset()` tiếp theo có thể ném `InvalidMarkException`.
12. **Cho nhiều luồng vừa đọc vừa sửa bộ nhớ chung mà không phối hợp.** View độc lập về con trỏ nhưng **không tự cô lập nội dung**.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Buffer A có `position=3, limit=9, capacity=12`. Gọi `B=A.slice()`. B có trạng thái gì?  
**Đáp án:** B có `capacity=limit=6`, `position=0` và mark chưa xác định. Byte `B.get(0)` tương ứng byte `A.get(3)`.

**Câu 2.** Tạo `B=A.duplicate()`, sau đó gọi `B.position(5)`. `A.position()` có đổi không?  
**Đáp án:** Không. Mỗi buffer giữ vị trí riêng dù dữ liệu chia sẻ.

**Câu 3.** `B=A.asReadOnlyBuffer()`. Gọi `A.put(0,(byte)7)` thì `B.get(0)` có thể thấy 7 không?  
**Đáp án:** Có, vì nội dung chung; B chỉ chặn ghi **thông qua B**. Điều kiện: index 0 nằm trong limit hợp lệ của cả hai view và không có ghi khác xen vào.

**Câu 4.** Nếu A có byte order `LITTLE_ENDIAN`, view `A.slice()` mới tạo có mặc định kế thừa không?  
**Đáp án:** Theo hợp đồng `ByteBuffer` Java 17, view mới có `BIG_ENDIAN`. Khi cần dữ liệu multi-byte, gọi `view.order(A.order())` hoặc thiết lập order theo giao thức.

**Câu 5.** Muốn parser tiến position riêng nhưng không làm thay đổi caller, chọn gì?  
**Đáp án:** `duplicate()` nếu cần cùng hệ chỉ số/limit ban đầu; `slice()` nếu muốn parser chỉ nhìn đoạn remaining với index mới bắt đầu từ 0. Nếu cần ngăn ghi qua view, thêm `asReadOnlyBuffer()`.

**Câu 6.** `slice()` tạo ở root position 2, limit 6. Sau đó root chuyển position 0, limit 8. Slice có mở rộng lên 8 byte không?  
**Đáp án:** Không. Slice vẫn capacity 4 và chia sẻ đúng vùng đã chọn lúc tạo.

## 14. Ghi nhớ

- `slice`: **cùng byte, một vùng con, position mới = 0**.
- `duplicate`: **cùng byte, toàn vùng, sao trạng thái vị trí ban đầu**.
- `asReadOnlyBuffer`: **cùng byte, không cho phép sửa qua view**, nhưng dữ liệu vẫn có thể bị sửa qua view writable khác.
- **Position, limit, mark độc lập giữa các view; nội dung được chia sẻ.**
- Đối với `ByteBuffer` Java 17, **đặt byte order tường minh** ở các view mới khi cần xử lý primitive nhiều byte.
- Không dùng read-only view để thay thế immutable snapshot hoặc đồng bộ đa luồng.

### Tham khảo API

- Java SE 17, `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17, `Buffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html

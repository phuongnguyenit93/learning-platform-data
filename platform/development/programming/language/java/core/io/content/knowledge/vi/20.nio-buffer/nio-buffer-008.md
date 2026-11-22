# `allocate`, `wrap` và vùng dữ liệu được chia sẻ trong Java NIO Buffer

## 1. Vì sao cần phân biệt tạo buffer với chia sẻ dữ liệu?

`java.nio.Buffer` là nền tảng của các bộ đệm NIO; các kiểu cụ thể như `ByteBuffer`, `CharBuffer`, `IntBuffer` cho phép thao tác dữ liệu thông qua một **vùng lưu trữ** và một tập thông số điều khiển **position**, **limit**, **capacity**. Hai lời gọi trông gần giống nhau có thể mang ý nghĩa quản lý dữ liệu hoàn toàn khác nhau:

```java
ByteBuffer allocated = ByteBuffer.allocate(4);
byte[] bytes = {10, 20, 30, 40};
ByteBuffer wrapped = ByteBuffer.wrap(bytes);
```

Đây là đoạn minh họa, cần import `java.nio.ByteBuffer`. Cả hai buffer đều có `capacity() == 4`, nhưng:

- `allocate(4)` cấp phát **vùng lưu trữ mới**. Không có mảng nguồn do caller cung cấp được chia sẻ ngay từ đầu.
- `wrap(bytes)` tạo một **buffer nhìn lên chính mảng `bytes` hiện có**. Không sao chép dữ liệu. Thay đổi phần tử bằng một phía được nhìn thấy qua phía còn lại.
- Cùng một vùng dữ liệu có thể có **nhiều buffer view**, mỗi view lại có `position`, `limit` và `mark` riêng. Thay đổi cursor của một view không đồng nghĩa cursor view khác thay đổi.
- “Độc lập về vị trí đọc/ghi” **không** có nghĩa “độc lập về nội dung”.

Bài học tập trung vào `allocate`, `wrap`, cách xác định vùng dữ liệu dùng chung, và những sai lầm khi coi các buffer như bản sao độc lập.

## 2. Mô hình bộ đệm: vùng dữ liệu và trạng thái truy cập

Một buffer thông thường có bốn khái niệm liên quan:

| Thuộc tính | Ý nghĩa |
|---|---|
| `capacity` | Số phần tử tối đa buffer có thể chứa; cố định trong suốt vòng đời buffer |
| `limit` | Chỉ số đầu tiên không được đọc/ghi qua thao tác tương đối; giới hạn phạm vi đang dùng |
| `position` | Vị trí của thao tác `get()`/`put()` tương đối tiếp theo |
| `mark` | Vị trí đã đánh dấu để có thể `reset()`; có thể không được đặt |

Bất biến quan trọng: `0 <= position <= limit <= capacity`. Trong code NIO, “chỉ số phần tử” là **chỉ số tương đối với buffer hiện tại**, không tự động là chỉ số trong mảng Java gốc.

Sơ đồ ví dụ, buffer có `capacity=8, position=2, limit=6`:

```text
index:       0    1    2    3    4    5    6    7
           +----+----+----+----+----+----+----+----+
storage:   |    |    |    |    |    |    |    |    |
           +----+----+----+----+----+----+----+----+
                      ^                   ^
                   position              limit
           <----------- capacity = 8 ----------->
                     <remaining = 4>
```

`remaining() == limit - position`. `get()` lấy ở `position` và tăng `position`; `put(value)` ghi ở `position` và tăng nó. `get(index)`/`put(index,value)` là thao tác **absolute** trong phạm vi chỉ số hợp lệ, không tự tăng `position`. Với `get(index)`/`put(index,value)` một phần tử, chỉ số phải nhỏ hơn `limit`. Khi tạo slice mới, chỉ số 0 của slice có thể ánh xạ tới một vị trí khác trong vùng lưu trữ chung.

**Lưu ý phân biệt:** gọi `clear()`, `flip()`, `rewind()` điều chỉnh trạng thái đọc/ghi; chúng **không** xóa nội dung vật lý của mảng hay cấp phát storage mới.

## 3. `ByteBuffer.allocate(capacity)` — cấp phát vùng lưu trữ mới

```java
import java.nio.ByteBuffer;

ByteBuffer buffer = ByteBuffer.allocate(5);
System.out.println(buffer.capacity());  // 5
System.out.println(buffer.position());  // 0
System.out.println(buffer.limit());     // 5
System.out.println(buffer.isDirect());  // false
System.out.println(buffer.hasArray());  // true
```

Đây là đoạn minh họa có thể đặt trong `main`. `ByteBuffer.allocate(5)` tạo một **heap byte buffer** mới có capacity 5. Các byte ban đầu bằng 0. Trạng thái ban đầu: `position=0`, `limit=capacity`, `mark` chưa được định nghĩa.

Các điểm thiết yếu:

- `allocate` tạo backing storage mới. Nếu tạo hai buffer bằng hai lời gọi `allocate` khác nhau, chúng không chia sẻ cùng mảng backing chỉ vì có cùng capacity.
- Heap `ByteBuffer` được tạo bằng `allocate` có backing `byte[]` truy cập được thông qua `array()`, và thông thường `arrayOffset() == 0` cho buffer ban đầu.
- `buffer.array()` trả **tham chiếu đến mảng backing**, **không tạo bản sao**. Nếu bạn đưa mảng này cho code khác, chính bạn đã mở đường chia sẻ dữ liệu và thay đổi ngoài buffer.
- Capacity âm gây `IllegalArgumentException`. Dung lượng rất lớn có thể gây `OutOfMemoryError`, không nên xem cấp phát là thao tác luôn thành công.

Ví dụ hai buffer cấp phát độc lập:

```java
ByteBuffer first = ByteBuffer.allocate(2);
ByteBuffer second = ByteBuffer.allocate(2);

first.put(0, (byte) 7);

System.out.println(first.get(0));  // 7
System.out.println(second.get(0)); // 0
```

Ở đây `first` và `second` có storage khác nhau. Ngược lại, biến `byte[] alias = first.array()` sẽ truy cập chính storage của `first`; đó là chia sẻ tham chiếu, dù buffer ban đầu được tạo bằng `allocate`.

### 3.1. `allocateDirect` là trường hợp riêng, không đồng nghĩa `allocate`

`ByteBuffer.allocateDirect(n)` yêu cầu direct byte buffer. Direct buffer thường giúp thực hiện một số thao tác I/O native với ít sao chép trung gian, nhưng chi phí cấp phát/quản lý khác heap buffer và không mặc định nhanh hơn cho mọi công việc.

```java
ByteBuffer heap = ByteBuffer.allocate(8);
ByteBuffer direct = ByteBuffer.allocateDirect(8);

System.out.println(heap.isDirect());   // false
System.out.println(direct.isDirect()); // true
System.out.println(heap.hasArray());   // true
System.out.println(direct.hasArray()); // false
```

Đoạn trên có thể đặt trong `main` cùng import `ByteBuffer`. Direct buffer không cho phép truy cập một `byte[]` backing qua `array()` như heap buffer. `hasArray()==false` cũng **chưa đủ để kết luận direct**, vì read-only heap buffer có thể không cho truy cập mảng. Khái niệm direct/heap thuộc lựa chọn lưu trữ; khái niệm shared/independent thuộc quan hệ các view và nguồn dữ liệu.

## 4. `ByteBuffer.wrap(byte[])` — dùng chung đúng mảng đã có

Khi có mảng byte:

```java
byte[] source = {10, 20, 30};
ByteBuffer buffer = ByteBuffer.wrap(source);

buffer.put(1, (byte) 99);
System.out.println(source[1]); // 99

source[2] = 77;
System.out.println(buffer.get(2)); // 77
```

Đây là đoạn minh họa dùng trong `main` với import `ByteBuffer`. Không có lần copy ngầm nào trong `wrap(source)`; cả `buffer` lẫn `source` đều nhìn cùng phần tử bộ nhớ.

Trạng thái ban đầu khi gọi `wrap(source)`:

```text
position = 0
limit    = source.length
capacity = source.length
backing array = source
arrayOffset = 0
```

`wrap` đặc biệt hữu ích khi một API tạo hoặc nhận `byte[]` còn phần xử lý NIO cần dùng các thao tác `get`, `put`, `flip`, `slice`, giải mã nhị phân hay tích hợp kênh I/O. Giá trị “không sao chép” giúp giảm copy, nhưng bắt buộc người viết code hiểu **ai sở hữu mảng và ai có quyền chỉnh sửa nó**.

### 4.1. Vì sao `wrap` không phải “chuyển đổi bất biến”?

`ByteBuffer.wrap(source)` giữ tham chiếu đến `source`. Ngay cả khi caller không còn giữ biến `source`, một đoạn khác đã nhận được mảng trước đó vẫn có thể thay đổi dữ liệu. Ngược lại, khi buffer được truyền cho người khác, người ấy có thể sửa dữ liệu mảng gốc thông qua buffer nếu nó còn writable.

Muốn có **bản sao nội dung độc lập**, phải sao chép chủ động, ví dụ:

```java
byte[] original = {1, 2, 3};
ByteBuffer shared = ByteBuffer.wrap(original);
ByteBuffer detached = ByteBuffer.wrap(original.clone());

original[0] = 9;
System.out.println(shared.get(0));   // 9
System.out.println(detached.get(0)); // 1
```

`clone()` tạo mảng byte khác trước khi `wrap`. Lưu ý với cấu trúc dữ liệu phức tạp, `clone` có thể là shallow copy; nhưng riêng `byte[]` chứa giá trị nguyên thủy nên tạo bản sao byte độc lập.

## 5. Bẫy nổi bật: `wrap(array, offset, length)` không tạo buffer capacity = length

Xét mảng:

```java
byte[] bytes = {10, 20, 30, 40, 50, 60};
ByteBuffer view = ByteBuffer.wrap(bytes, 1, 3);
```

Nhiều người đoán `view` có `capacity=3`, `position=0`, `limit=3`. Đây là **phỏng đoán sai**.

Theo contract `ByteBuffer.wrap(array, offset, length)`:

```text
capacity = array.length           = 6
position = offset                 = 1
limit    = offset + length        = 4
mark     = undefined
arrayOffset = 0 (ở buffer bao toàn mảng ban đầu)
```

Đối số `offset` và `length` xác định **phần mảng sẵn sàng cho thao tác tương đối ban đầu**, không thay đổi capacity của buffer thành `length`. Vì vậy:

```java
System.out.println(view.capacity()); // 6
System.out.println(view.position()); // 1
System.out.println(view.limit());    // 4
System.out.println(view.remaining()); // 3

System.out.println(view.get());      // 20 (position tăng thành 2)
System.out.println(view.get(0));     // 10 (absolute get, không đổi position)
```

Đây là đoạn minh họa tiếp từ khai báo `view`. `get(0)` có thể truy cập phần tử nằm **trước** offset, miễn chỉ số nằm dưới `limit`; `offset` không phải hàng rào cách ly bộ nhớ. Sau `clear()`, buffer này có thể thao tác tới capacity 6; `clear()` không sao chép hoặc giới hạn lại vào đoạn 3 byte.

### 5.1. Muốn có hệ chỉ số bắt đầu ở 0 cho đoạn được chọn: `slice()`

```java
byte[] bytes = {10, 20, 30, 40, 50, 60};
ByteBuffer window = ByteBuffer.wrap(bytes, 1, 3).slice();
```

Vì buffer gốc có `position=1` và `limit=4`, `slice()` tạo buffer mới chỉ nhìn **vùng còn lại** gồm ba byte `{20,30,40}`. Nó có:

```text
position    = 0
limit       = 3
capacity    = 3
arrayOffset = 1 (với heap buffer này)
```

Hệ chỉ số của `window` là 0..2, nhưng các byte **vẫn chia sẻ** với `bytes`:

```java
window.put(0, (byte) 99);
System.out.println(bytes[1]); // 99
```

Có thể xem phép ánh xạ ở đây là:

```text
window index:       0     1     2
                    |     |     |
underlying bytes:  [10]  [99]  [30]  [40]  [50]  [60]
array index:         0     1     2     3     4     5
                          ^-----------^
                     window's backing region
```

Nếu cần xác định chỉ số phần tử đầu của một accessible array-backed buffer, dùng `buffer.arrayOffset() + bufferIndex`. **Không giả định `buffer.array()[0]` luôn là byte ở `buffer.get(0)`.** Mệnh đề đó chỉ đúng với vài buffer ban đầu có `arrayOffset()==0`.

### 5.2. `slice(index, length)` — chọn một đoạn theo chỉ số xác định

Trong các phiên bản Java hiện đại (có trong Java 17), có thể gọi:

```java
ByteBuffer original = ByteBuffer.wrap(new byte[]{10, 20, 30, 40, 50});
ByteBuffer part = original.slice(1, 3);

System.out.println(part.capacity()); // 3
System.out.println(part.position()); // 0
System.out.println(part.get(0));     // 20
```

Chỉ số `1` ở đây là chỉ số **của buffer `original`**, không phải tham số offset truyền tới constructor của một mảng tùy ý. `slice(index,length)` tạo vùng nhìn gồm các byte từ `index` tới `index+length-1`, phụ thuộc `limit` của `original` và phải hợp lệ theo contract. Bộ đệm slice cũng dùng chung storage và mang trạng thái cursor riêng.

## 6. `duplicate`, `slice`, `asReadOnlyBuffer`: khác cursor, cùng dữ liệu

Từ một `ByteBuffer base` có thể tạo các view:

| API | Vùng dữ liệu nhìn thấy | `position` / `limit` ban đầu | Có chia sẻ byte với gốc? |
|---|---|---|---|
| `base.duplicate()` | Cùng toàn bộ vùng buffer gốc | Sao lại giá trị `position`, `limit`, `mark` ban đầu | Có |
| `base.slice()` | Vùng `base.position()` đến `base.limit()` | `position=0`, `limit=capacity=base.remaining()` | Có |
| `base.slice(index,length)` | Vùng chỉ định của base | `position=0`, `limit=capacity=length` | Có |
| `base.asReadOnlyBuffer()` | Cùng vùng buffer gốc nhưng không được ghi qua view đó | Sao lại các giá trị trạng thái cursor ban đầu | Có |
| `ByteBuffer.wrap(base.array().clone())` | Mảng copy (chỉ hợp lệ khi `array()` truy cập được) | `position=0`, `limit=capacity=độ dài mảng copy` | Không |

**Nguyên tắc:** `duplicate` và `slice` không copy bytes. `asReadOnlyBuffer` cũng không copy bytes; “read-only” chỉ chặn **ghi thông qua view đó**, không làm ảnh chụp snapshot bất biến trước thay đổi của view khác.

### 6.1. Cursor độc lập

```java
ByteBuffer original = ByteBuffer.wrap(new byte[]{5, 6, 7, 8});
ByteBuffer other = original.duplicate();

original.position(2);
other.position(1);

System.out.println(original.get()); // 7, original position thành 3
System.out.println(other.get());    // 6, other position thành 2
```

Hai view cùng nhìn byte gốc nhưng không chia sẻ biến `position`. Khi tạo duplicate, trạng thái ban đầu được sao chép; **sau đó** các cursor thay đổi độc lập. Tương tự, thay đổi `limit` hay `mark` của view này không phải thao tác lên state của view kia.

### 6.2. Dữ liệu không độc lập

```java
byte[] bytes = {5, 6, 7};
ByteBuffer a = ByteBuffer.wrap(bytes);
ByteBuffer b = a.duplicate();

b.put(1, (byte) 99);
System.out.println(a.get(1)); // 99
System.out.println(bytes[1]); // 99
```

Dù `a.position()` và `b.position()` riêng biệt, một thao tác ghi qua `b` vẫn đổi byte mà `a` và `bytes` nhìn thấy.

### 6.3. Read-only view không đồng nghĩa snapshot

```java
ByteBuffer writable = ByteBuffer.wrap(new byte[]{1, 2, 3});
ByteBuffer readOnly = writable.asReadOnlyBuffer();

writable.put(0, (byte) 9);
System.out.println(readOnly.get(0)); // 9

// readOnly.put(0, (byte) 5) sẽ ném ReadOnlyBufferException.
```

Read-only view nhìn thấy thay đổi từ writable alias. `readOnly.isReadOnly()` là `true`; `readOnly.array()` không cho truy cập backing array ghi được. Một buffer được tạo trực tiếp từ read-only view không đột nhiên trở thành writable; các view mới vẫn tuân theo hạn chế read-only.

**Nếu cần dữ liệu ổn định**, bạn phải copy bytes sang vùng riêng và kiểm soát quyền ghi vào bản đó. Gán “read-only” lên một góc nhìn không loại bỏ alias ghi khác.

## 7. Ví dụ Java 17+ biên dịch và chạy được

Ví dụ sau kết hợp `allocate`, `wrap(offset,length)`, `slice`, `duplicate`, `asReadOnlyBuffer` và **copy độc lập**, kèm số liệu cụ thể cho vị trí và nội dung.

**Tệp:** `BufferSharingDemo.java`

```java
import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.util.Arrays;

public class BufferSharingDemo {
    public static void main(String[] args) {
        ByteBuffer allocated = ByteBuffer.allocate(4);
        System.out.printf(
                "allocate: pos=%d limit=%d capacity=%d%n",
                allocated.position(), allocated.limit(), allocated.capacity());

        byte[] bytes = {10, 20, 30, 40, 50, 60};
        ByteBuffer wrapped = ByteBuffer.wrap(bytes, 1, 3);
        System.out.printf(
                "wrap(offset,length): pos=%d limit=%d capacity=%d%n",
                wrapped.position(), wrapped.limit(), wrapped.capacity());

        wrapped.put(2, (byte) 99);
        System.out.println("after wrap.put: " + Arrays.toString(bytes));

        ByteBuffer window = ByteBuffer.wrap(bytes, 1, 3).slice();
        System.out.printf(
                "slice: pos=%d limit=%d capacity=%d arrayOffset=%d%n",
                window.position(), window.limit(), window.capacity(),
                window.arrayOffset());

        window.put(0, (byte) 77);
        ByteBuffer duplicate = window.duplicate();
        duplicate.position(2);
        duplicate.put(1, (byte) 88);

        System.out.println("after views: " + Arrays.toString(bytes));
        System.out.println("positions: window=" + window.position()
                + ", duplicate=" + duplicate.position());

        ByteBuffer readOnly = window.asReadOnlyBuffer();
        System.out.println("read-only: " + readOnly.isReadOnly()
                + ", sees=" + readOnly.get(1));

        try {
            readOnly.put(0, (byte) 1);
        } catch (ReadOnlyBufferException ex) {
            System.out.println("read-only write: ReadOnlyBufferException");
        }

        ByteBuffer independent = ByteBuffer.allocate(window.remaining());
        independent.put(window.duplicate());
        independent.flip();

        window.put(0, (byte) 11);
        System.out.println("copy first=" + independent.get(0)
                + ", source first=" + window.get(0));
    }
}
```

Chạy bằng JDK 17+ tại thư mục chứa tệp nguồn:

```bash
javac BufferSharingDemo.java
java BufferSharingDemo
```

**Stdout dự kiến chính xác:**

```text
allocate: pos=0 limit=4 capacity=4
wrap(offset,length): pos=1 limit=4 capacity=6
after wrap.put: [10, 20, 99, 40, 50, 60]
slice: pos=0 limit=3 capacity=3 arrayOffset=1
after views: [10, 77, 88, 40, 50, 60]
positions: window=0, duplicate=2
read-only: true, sees=88
read-only write: ReadOnlyBufferException
copy first=77, source first=11
```

**Tại sao có các kết quả này?**

1. `allocate(4)` tạo buffer mới ở chế độ ghi với `position=0`, `limit=capacity=4`.
2. `wrap(bytes,1,3)` không thu nhỏ capacity của mảng; nó đặt `position=1` và `limit=4`. Absolute `put(2,99)` ghi vào `bytes[2]` mà không đổi position.
3. `slice()` tạo view riêng của đoạn `bytes[1..3]`; do đó capacity 3 và `arrayOffset=1`.
4. `window.put(0,77)` đổi `bytes[1]`; `duplicate.put(1,88)` đổi `bytes[2]`, mặc dù cursor của duplicate đã được đặt bằng 2. Hai phép `put(index,value)` không thay đổi position.
5. Read-only view không cho ghi qua nó, nhưng vẫn đọc được 88 từ storage chung.
6. `independent` có vùng lưu trữ mới và sao chép ba byte. Sau khi `window` đổi byte đầu từ 77 thành 11, buffer copy vẫn giữ 77.

Mã dùng các thao tác đồng bộ trong một thread để output tái lập, không dựa vào scheduler hoặc filesystem.

## 8. `get`, `put`, `flip`, `clear` khi các buffer chia sẻ mảng

Với một buffer thông thường:

```java
ByteBuffer buffer = ByteBuffer.allocate(4);
buffer.put((byte) 10);
buffer.put((byte) 20);
buffer.flip();

System.out.println(buffer.get()); // 10
System.out.println(buffer.get()); // 20
```

`flip()` đặt `limit` thành `position` cũ rồi `position=0` để chuẩn bị đọc lượng dữ liệu vừa ghi. Nếu buffer có nhiều view, `flip()` chỉ cập nhật trạng thái **view được gọi**, không tự cập nhật cursor của tất cả view kia.

### 8.1. `clear()` có thật sự xóa dữ liệu?

Không. `clear()` thường đưa `position=0`, `limit=capacity` và bỏ mark, chuẩn bị ghi đè. Dữ liệu cũ có thể vẫn nằm trong backing storage cho đến khi bị thay:

```java
byte[] bytes = {1, 2, 3};
ByteBuffer wrapped = ByteBuffer.wrap(bytes);
wrapped.clear();
System.out.println(Arrays.toString(bytes)); // [1, 2, 3]
```

Đoạn minh họa cần import `java.util.Arrays` và `java.nio.ByteBuffer`. Với dữ liệu nhạy cảm, `clear()` **không** phải biện pháp xóa an toàn hay zero memory.

### 8.2. Khi nào `BufferOverflowException` và `BufferUnderflowException` xảy ra?

Chính `position` và `limit` của view quyết định số phần tử còn lại. Một lời gọi relative `put` khi không còn chỗ trong vùng `remaining` sẽ ném `BufferOverflowException`; relative `get` khi không còn phần tử sẽ ném `BufferUnderflowException`. Đừng cho rằng còn chỗ trong **mảng gốc** thì buffer luôn ghi/đọc tiếp được: view có limit riêng.

Ví dụ, với `ByteBuffer.wrap(bytes,1,3)`, chỉ còn ba byte cho các thao tác tương đối ban đầu; sau ba lần `get()` tiếp theo, `get()` thứ tư sẽ underflow. Thay đổi limit hoặc dùng absolute access là lựa chọn khác nhưng phải phù hợp yêu cầu nghiệp vụ và kiểm tra bounds.

### 8.3. `compact()` có thể ảnh hưởng view khác vì nó di chuyển bytes

`compact()` sao chép các phần tử chưa đọc về đầu **vùng storage của buffer hiện tại**, đặt position để ghi tiếp và có thể làm thay đổi nội dung backing array được các view khác quan sát. Vì vậy, `compact()` không chỉ là cập nhật cursor đơn thuần như `clear()` hay `flip()`; với shared storage, đây là thao tác có tác dụng lên dữ liệu.

## 9. Vùng dữ liệu chia sẻ và quyền truy cập backing array

Với **heap ByteBuffer writable**, thường có thể:

```java
ByteBuffer heap = ByteBuffer.allocate(6);
byte[] backing = heap.array();
int offset = heap.arrayOffset();
```

`backing` là cùng mảng chứa bytes, không phải bản sao. `offset` cần cộng vào index khi buffer là một slice có vùng lưu trữ bắt đầu ở giữa mảng.

Có ba trường hợp cần phân biệt:

| Buffer | `hasArray()` | `array()` |
|---|---|---|
| Heap `ByteBuffer.allocate(...)` ban đầu writable | `true` | Trả cùng `byte[]` backing |
| Heap slice/duplicate writable có accessible array | `true` | Trả cùng mảng backing, `arrayOffset` có thể khác |
| Read-only view của heap buffer | `false` | Ném `ReadOnlyBufferException` |
| Direct `ByteBuffer` | `false` | Ném `UnsupportedOperationException` |

`hasArray()` chỉ cho biết có backing array **truy cập được theo contract**; không nói rằng bộ nhớ “không bị chia sẻ”. Một read-only buffer có thể share bytes qua view writable khác; một direct buffer có thể chia sẻ storage qua các direct slice dù không có accessible `byte[]`.

Khi viết thư viện tổng quát nhận `ByteBuffer`, cách vững chắc là dùng `get`/`put`/`slice`/`duplicate` và chỉ tối ưu sang `array()` khi `hasArray()` phù hợp, đồng thời xử lý đúng `position`, `remaining`, `arrayOffset` và quyền read-only.

### 9.1. Chuyển byte buffer thành array mới mà không sửa cursor caller

Ví dụ phương thức copy **chỉ vùng còn lại**:

```java
import java.nio.ByteBuffer;

public class BufferBytes {
    public static byte[] remainingBytes(ByteBuffer source) {
        ByteBuffer reader = source.duplicate();
        byte[] result = new byte[reader.remaining()];
        reader.get(result);
        return result;
    }
}
```

Đây là lớp helper có thể biên dịch độc lập (`BufferBytes.java`), không có `main` và không có stdout. `duplicate()` giữ cùng storage nhưng có cursor riêng; `get(result)` đọc dữ liệu vào mảng **mới**, nên `source.position()` không bị thay đổi. Lưu ý `source` có thể bị sửa đồng thời qua alias khác, khiến các byte copy được phản ánh một trạng thái trung gian; API này không cung cấp snapshot nguyên tử dưới ghi đồng thời.

**Tại sao không dùng `source.array()`?** Vì nó có thể ném ngoại lệ trên direct/read-only buffer, trả cả backing array lớn thay vì `remaining`, và có thể làm lộ dữ liệu ngoài vùng caller dự định cho phép đọc.

## 10. `CharBuffer.wrap` và các kiểu buffer khác

Ý tưởng “wrap dùng vùng dữ liệu có sẵn” không chỉ áp dụng cho `ByteBuffer`:

```java
char[] letters = {'J', 'a', 'v', 'a'};
CharBuffer characters = CharBuffer.wrap(letters);

characters.put(0, 'K');
System.out.println(letters[0]); // K
```

Đoạn minh họa với `import java.nio.CharBuffer;`. `CharBuffer.wrap(char[])` chia sẻ mảng `char[]`. Với các kiểu `IntBuffer`, `ShortBuffer`, `LongBuffer`, `FloatBuffer`, `DoubleBuffer`, cách wrap mảng primitive tương ứng cũng theo tư tưởng backing storage dùng chung.

**Ngoại lệ quan trọng khi gặp `CharSequence`:**

```java
CharBuffer text = CharBuffer.wrap("Java");
System.out.println(text.isReadOnly()); // true, đối với String
```

`CharBuffer.wrap(CharSequence)` tạo một char buffer đọc từ sequence; nó không giống wrap mutable `char[]`. Với `String` bất biến, view không cho sửa nội dung theo cách sửa mảng; cố `put` vào char buffer được tạo bởi overload này sẽ ném `ReadOnlyBufferException`. Với `CharSequence` có thể thay đổi, hãy xét contract của sequence và provider trước khi suy luận về tính ổn định của dữ liệu được quan sát.

Một kiểu buffer khác cũng có thể là **typed view** trên byte buffer, ví dụ `byteBuffer.asIntBuffer()`: nó cho một góc nhìn các phần tử `int` trên cùng byte storage (với quy tắc thứ tự byte và alignment tương ứng). Khi chỉnh byte bằng view này, dữ liệu cùng vùng có thể thay đổi ở các view khác. Không nên suy ra mọi buffer cùng capacity số phần tử bằng nhau: `IntBuffer` tính capacity theo số giá trị `int`, không theo số byte.

## 11. Rủi ro thiết kế và đồng thời

### 11.1. Chia sẻ backing storage là chia sẻ khả năng thay đổi dữ liệu

Ví dụ một API nhận mảng và giữ reference:

```java
static ByteBuffer parseLater(byte[] packet) {
    return ByteBuffer.wrap(packet);
}
```

Nếu caller sửa `packet` sau khi truyền, buffer mà parser dùng về sau sẽ nhìn dữ liệu mới. Trường hợp parser muốn “đóng băng đầu vào” để kiểm tra checksum, chữ ký, protocol frame hoặc cache, nó phải xác định rõ **sở hữu mảng** và cân nhắc copy chủ động. Không chỉ nhìn vào tên tham số kiểu `ByteBuffer` để đoán đối tượng được sở hữu độc quyền.

Các chiến lược phổ biến:

- **Chia sẻ có chủ đích:** nói rõ caller không được thay dữ liệu trong thời gian parser dùng buffer, giúp tránh copy nhưng cần phối hợp vòng đời.
- **Bản sao riêng:** `ByteBuffer.wrap(array.clone())` hoặc copy `remaining` vào mảng mới; tăng chi phí bộ nhớ/copy nhưng giảm alias với đầu vào.
- **Chỉ cấp read-only view:** hạn chế ghi từ người nhận, nhưng không ngăn owner hoặc alias khác thay backing storage.
- **Truyền dữ liệu theo luồng:** nếu không cần random access, cân nhắc stream/channel và quy tắc vòng đời nguồn; không phải mọi API đều cần backing array chia sẻ.

### 11.2. Buffer không mặc định thread-safe

Một `ByteBuffer` mutable có cursor và storage có thể thay đổi. Dùng cùng instance hoặc các view chung backing storage từ nhiều thread mà không đồng bộ có thể gây tranh chấp dữ liệu, trạng thái quan sát không nhất quán hoặc logic đọc sai.

Việc `duplicate()` tạo cursor riêng có thể giúp tách trạng thái vị trí đọc/ghi, nhưng **không làm bytes dùng chung trở thành thread-safe**. `asReadOnlyBuffer()` hạn chế ghi qua một alias, song alias khác vẫn có thể thay dữ liệu đồng thời. Khi có tác vụ concurrent, cần ownership/handoff, synchronization hoặc cấu trúc dữ liệu và cơ chế điều phối riêng phù hợp Java Memory Model.

### 11.3. Đọc dữ liệu ổn định không chỉ là đặt limit

`position` và `limit` kiểm soát API `get`/`put` trên view, **không phải rào chắn bảo mật đối với backing storage**. Một view khác hoặc mảng gốc vẫn có thể chạm phần tử ngoài vùng giới hạn của view này. Nếu có dữ liệu riêng tư ở trước/sau một vùng slice, đừng gửi cả mảng thông qua `array()` cho thành phần không đáng tin cậy; gửi bản sao chính xác vùng cho phép.

### 11.4. Lifetime của direct buffer và mapped buffer

Đối với direct buffer, cần lưu ý chi phí cấp phát native memory và vòng đời do JVM quản lý; không nên tích lũy vô hạn direct allocations. Với `MappedByteBuffer` ánh xạ tệp, thao tác qua các view có thể liên quan dữ liệu file được ánh xạ và việc đồng bộ/durability cần theo contract riêng. Các trường hợp này vẫn minh họa rằng “buffer” là mô hình truy cập dữ liệu, còn vị trí/vòng đời dữ liệu phụ thuộc cách tạo buffer.

## 12. Các lỗi thường gặp và cách sửa

1. **Nghĩ `wrap(array)` tạo bản sao.** Thực tế buffer chia sẻ mảng. Nếu cần độc lập, dùng `array.clone()` hoặc copy có chủ đích.
2. **Nghĩ `allocate` trả buffer không có backing array.** Heap buffer từ `ByteBuffer.allocate` có backing array; `allocateDirect` mới có direct storage.
3. **Nghĩ `wrap(array,offset,length)` đặt capacity = length.** Nó giữ capacity bằng `array.length`, đặt position/limit tương ứng. Muốn cửa sổ 0-based, sử dụng `slice()`.
4. **Quên `arrayOffset` ở slice.** `buffer.get(0)` có thể trỏ tới `backing[arrayOffset]`, không phải `backing[0]`.
5. **Nghĩ `slice` và `duplicate` sao chép bytes.** Chúng tạo views chia sẻ storage; cursor độc lập nhưng nội dung liên kết.
6. **Nghĩ `asReadOnlyBuffer` đóng băng dữ liệu.** View readonly không ngăn writer khác thay backing bytes.
7. **Cho rằng `hasArray()==false` tức là direct.** Read-only heap buffer cũng có thể không có accessible array; dùng `isDirect()` nếu câu hỏi là direct hay không.
8. **Nhầm `clear()` là zero/reset dữ liệu.** Nó thay trạng thái cursor, không ghi đè toàn bộ mảng.
9. **Truy cập `array()` mà không xét phạm vi.** Trả toàn mảng backing, có thể lớn hơn vùng `position..limit` muốn xuất.
10. **Dùng relative `put` mà không xét `remaining()`.** Chạm limit gây overflow dù array vẫn còn các index bên ngoài view.
11. **Nhầm absolute access với relative access.** `put(index,value)` không tăng position; `put(value)` có tăng.
12. **Cho rằng cùng backing là an toàn khi đa luồng.** Cần quy tắc đồng bộ và sở hữu; cursor riêng không ngăn data race.
13. **Nghĩ buffer chỉ có thể chia sẻ storage khi tạo qua `wrap`.** `duplicate`, `slice` và `array()` từ `allocate` cũng tạo đường chia sẻ.
14. **Dùng `wrap(CharSequence)` như wrap `char[]` để ghi.** Overload nhận chuỗi có ngữ nghĩa read-only tùy sequence; cần chọn overload phù hợp.
15. **Đồng nhất capacity với số byte hợp lệ để đọc.** Sau khi ghi cần `flip()` hoặc đặt limit phù hợp; dữ liệu nằm trong backing array không đồng nghĩa thuộc vùng readable dự định.

## 13. Kiểm tra nhanh khả năng dự đoán shared storage

**Câu 1.** Với:

```java
byte[] a = {1, 2, 3, 4};
ByteBuffer b = ByteBuffer.wrap(a, 1, 2);
```

`b.capacity()`, `b.position()`, `b.limit()` bằng bao nhiêu?  
**Đáp án:** `4`, `1`, `3`. `offset` và `length` chỉ thiết lập cursor/range ban đầu.

**Câu 2.** Nếu gọi `ByteBuffer c = b.slice()` ngay sau đó thì `c.capacity()` và `c.arrayOffset()` là gì?  
**Đáp án:** `2` và `1` với array-backed buffer này; `c.position()=0` và `c.limit()=2`. `c.get(0)` tương ứng `a[1]`.

**Câu 3.** `c.put(0, (byte) 8)` có thay `a` không?  
**Có.** `a[1]` thành 8. Slice vẫn chia sẻ backing.

**Câu 4.** Sau `ByteBuffer d = c.duplicate()`, gọi `d.position(1)` có thay `c.position()` không?  
**Không.** Cursor độc lập, storage chung.

**Câu 5.** `c.asReadOnlyBuffer()` có ngăn việc sửa dữ liệu qua `a[1]=9` không?  
**Không.** Nó chỉ chặn ghi qua view read-only đó; view vẫn có thể quan sát giá trị 9.

**Câu 6.** `ByteBuffer.allocate(4).array()` có tạo bản sao mới khi đọc `array()` không?  
**Không.** Đây là mảng backing của chính buffer.

**Câu 7.** Muốn tạo bản sao chính xác phần `remaining` của một buffer có thể là direct/read-only, dùng gì?  
**Gợi ý:** `source.duplicate()` để không đổi cursor caller, tạo `byte[]` kích thước `duplicate.remaining()` rồi `duplicate.get(bytes)`.

## 14. Ghi nhớ và tài liệu tham khảo

**Quy tắc học thuộc:** `allocate` tạo storage mới, `wrap` dùng storage đã có; `slice`/`duplicate` tạo view dùng chung storage nhưng quản lý position/limit riêng; `asReadOnlyBuffer` chặn ghi qua view, không tạo snapshot. Đối với `wrap(array,offset,length)`, nhớ `capacity=array.length` và muốn đoạn 0-based thực sự thì tiếp tục `slice()`. Khi cần độc lập hoàn toàn, hãy copy dữ liệu có chủ đích.

Tài liệu chính thức Java SE 21:

- `ByteBuffer` — `allocate`, `allocateDirect`, `wrap`, `slice`, `duplicate`, `asReadOnlyBuffer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- `Buffer` — position, limit, capacity, mark, `flip`, `clear`, `rewind`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/Buffer.html
- `CharBuffer` — wrap mảng và CharSequence: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/CharBuffer.html
- `ReadOnlyBufferException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ReadOnlyBufferException.html

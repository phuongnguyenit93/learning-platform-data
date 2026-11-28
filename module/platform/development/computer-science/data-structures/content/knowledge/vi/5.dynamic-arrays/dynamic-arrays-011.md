# Dọn các ô không còn dùng để tránh giữ đối tượng ngoài ý muốn

Mảng động (*dynamic array*) thường có một bộ đệm (*buffer*) lớn hơn số phần tử đang sử dụng. Nhờ các ô dự trữ, cấu trúc có thể thêm phần tử nhanh mà không phải cấp phát lại sau mỗi thao tác. Tuy nhiên, khi **xóa phần tử**, **thay phần tử** hoặc **làm rỗng mảng**, việc chỉ thay đổi số phần tử logic có thể chưa đủ nếu bộ đệm chứa **tham chiếu đến đối tượng**.

Một ô nằm ngoài phần đang sử dụng vẫn tồn tại trong bộ đệm. Nếu ô đó còn giữ tham chiếu đến một đối tượng không còn thuộc mảng động, đối tượng có thể tiếp tục được xem là *có thể truy cập* và chưa đủ điều kiện để được thu gom rác. Hiện tượng **giữ đối tượng ngoài ý muốn** này thường được gọi là *loitering objects* hoặc *unintentional object retention*.

Bài học tập trung vào cách dọn các ô không còn dùng để bảo đảm tính đúng đắn của cấu trúc và tránh tiêu tốn bộ nhớ không cần thiết, đặc biệt trong Java và các môi trường thu gom rác. Ta sẽ phân tích xóa cuối, xóa giữa, xóa toàn bộ, thay giá trị, cấp phát lại, cùng những trường hợp đối tượng vẫn phải tồn tại vì còn tham chiếu ở nơi khác.

## 1. Ô đã cấp phát khác với phần tử đang sử dụng

Một mảng động điển hình có:

| Thành phần | Ý nghĩa |
| --- | --- |
| `buffer` | Mảng nền chứa `capacity` ô |
| `size` | Số phần tử hợp lệ về mặt logic |
| `capacity` | Số ô được cấp phát cho bộ đệm hiện tại |

Bất biến cơ bản:

\[
0 \le \text{size} \le \text{capacity}.
\]

Các chỉ số thuộc **phần tử logic** là `0` đến `size - 1`; phần còn lại `[size, capacity)` là **ô dự trữ**. Ví dụ:

```text
Chỉ số:      0      1      2      3      4
           +------+------+------+------+------+
buffer:    |  A   |  B   |  C   | null | null |
           +------+------+------+------+------+
           <--- size = 3 ---><-- dự trữ -->
           <--------- capacity = 5 ---------->
```

Trong mảng động chứa đối tượng, mỗi ô thường lưu **tham chiếu** đến đối tượng, chứ không nhất thiết chứa toàn bộ dữ liệu của đối tượng đó. Chẳng hạn một ô `Object[]` của Java có thể tham chiếu đến một đối tượng chứa ảnh, bộ đệm dữ liệu hay cây các đối tượng khác.

**Quy tắc kiểm tra chỉ số** vẫn chỉ dựa trên `size`: đọc phần tử tại `i` hợp lệ khi `0 <= i < size`. Việc một ô dự trữ tình cờ còn chứa giá trị không cho phép truy cập ô đó qua API phần tử logic.

## 2. Vì sao một tham chiếu còn sót có thể giữ đối tượng?

Với trình thu gom rác (*garbage collector*, GC), khả năng một đối tượng được thu hồi liên quan đến việc nó còn **có thể truy cập từ các gốc GC** (*GC roots*) hay không. Một gốc có thể dẫn qua đối tượng chứa mảng động, tới bộ đệm, rồi tới đối tượng ở một ô không còn sử dụng.

```text
Gốc GC
   |
   v
Mảng động còn được dùng
   |
   v
buffer: [objA][objB][objC][ ? ][ ? ]
                 |
                 v
             Đối tượng B
                 |
                 v
           Vùng dữ liệu lớn

Nếu size đã giảm còn 1 nhưng buffer[1] vẫn là objB:
objB vẫn có đường tham chiếu từ buffer.
```

Hãy hình dung mảng động chứa một đối tượng `Document` kèm vùng dữ liệu vài megabyte. Khi ứng dụng xóa tài liệu này khỏi danh sách, `size` được giảm. Nếu ô cũ của `buffer` vẫn tham chiếu đến `Document` và mảng động còn tồn tại lâu dài, GC vẫn có thể thấy `Document` thông qua bộ đệm. Cả dữ liệu mà nó tham chiếu đến cũng có thể tiếp tục được giữ trong bộ nhớ.

Đây là sự khác biệt giữa hai trạng thái:

- **Đã xóa về mặt logic:** `get(i)` không được trả về phần tử cũ vì `i` nằm ngoài `size` hoặc phần tử đã bị thay thế.
- **Đã bỏ tham chiếu trong cấu trúc:** các ô không còn dùng của `buffer` không giữ đường tham chiếu không cần thiết đến đối tượng cũ.

Trong Java, gán `null` cho một ô tham chiếu giúp xóa **một đường tham chiếu**. Việc đó **không bảo đảm đối tượng lập tức được GC thu hồi**: đối tượng có thể còn được tham chiếu ở nơi khác, GC chạy theo lịch riêng, và bộ nhớ heap chưa chắc được trả ngay về hệ điều hành.

## 3. Xóa cuối: giảm `size` rồi dọn ô vừa bỏ

Đây là trường hợp dễ bỏ sót nhất vì không có phần tử nào cần dịch chuyển.

Giả sử đang có `[A, B, C]` trong bộ đệm bốn ô:

```text
Trước removeLast():
           +------+------+------+------+
buffer:    |  A   |  B   |  C   | null |
           +------+------+------+------+
size = 3, capacity = 4

Chỉ giảm size xuống 2 (chưa dọn):
           +------+------+------+------+
buffer:    |  A   |  B   |  C   | null |
           +------+------+------+------+
                          ^
                          C vẫn được buffer[2] tham chiếu
size = 2, capacity = 4

Giảm size và dọn ô:
           +------+------+------+------+
buffer:    |  A   |  B   | null | null |
           +------+------+------+------+
size = 2, capacity = 4
```

Mã giả cho mảng chứa tham chiếu:

```text
removeLast():
    nếu size == 0:
        báo lỗi vì mảng rỗng

    index = size - 1
    removed = buffer[index]  # Lấy phần tử cũ để trả về
    buffer[index] = null     # Bỏ tham chiếu khỏi bộ đệm
    size = index
    trả về removed
```

Một chi tiết quan trọng: nếu phương thức **trả về đối tượng vừa xóa**, biến `removed` (hoặc nơi nhận giá trị trả về) có thể tiếp tục tham chiếu đến nó. Dọn ô trong `buffer` chỉ bảo đảm **mảng động** không còn giữ đối tượng đó; chương trình gọi có quyền tiếp tục sử dụng đối tượng được trả về.

Với mảng nguyên thủy như `int[]`, ô lưu chính giá trị số nguyên chứ không tham chiếu đến đối tượng độc lập. Gán ô vừa bỏ về `0` có thể giúp việc quan sát hoặc tránh dữ liệu cũ xuất hiện trong bộ đệm nội bộ, nhưng **không có cùng mục đích giải phóng tham chiếu** như với `Object[]`.

## 4. Xóa giữa: dồn trái rồi xóa ô cuối cũ

Xóa tại vị trí bất kỳ trong mảng động bảo toàn thứ tự thường cần dịch các phần tử phía sau sang trái. Tuy nhiên, **dồn trái không tự xóa tham chiếu thừa ở ô cuối**.

Ví dụ, xóa `B` khỏi `[A, B, C, D]`:

```text
Ban đầu, size = 4, capacity = 5:
    [ A ][ B ][ C ][ D ][null]

Dồn trái từ vị trí 1:
    [ A ][ C ][ D ][ D ][null]
                     ^    ^
                bản sao D  ô dự trữ

Giảm size từ 4 xuống 3 mà không dọn:
    [ A ][ C ][ D ][ D ][null]
                     ^
              ô này đã nằm ngoài size

Dọn buffer[3] = null:
    [ A ][ C ][ D ][null][null]
    size = 3, capacity = 5
```

Trong ví dụ, sau khi dồn trái, hai ô có thể cùng tham chiếu đến `D`. Ngay lúc đó, `D` vẫn là phần tử logic ở chỉ số 2, nên ô thừa chưa nhất thiết tạo thêm một đối tượng bị giữ ngoài ý muốn. Nhưng nếu sau này xóa hoặc thay `D` mà không dọn đúng, các tham chiếu cũ bên ngoài `size` có thể khiến đối tượng tiếp tục được giữ. Dọn ô cuối sau **mỗi lần xóa** giúp duy trì một trạng thái nhất quán, dễ kiểm chứng.

Mã giả:

```text
removeAt(i):
    nếu i < 0 hoặc i >= size:
        báo lỗi chỉ số

    removed = buffer[i]
    for j từ i đến size - 2:
        buffer[j] = buffer[j + 1]

    size = size - 1
    buffer[size] = null
    trả về removed
```

Vòng lặp phải đi **từ trái sang phải**, bảo đảm không ghi đè phần tử cần đọc ở lượt sau. Số ô cần dồn là `size_cũ - i - 1`, vì thế xóa giữa có thời gian O(n) trong trường hợp xấu nhất. Việc dọn ô cuối chỉ thêm **O(1)** công việc.

Trong Java có thể dùng `System.arraycopy(buffer, i + 1, buffer, i, size - i - 1)` để dồn một đoạn ô tham chiếu. Sau đó vẫn cần giảm `size` và gán `null` vào ô cuối cũ.

## 5. Làm rỗng mảng: `size = 0` có đủ không?

Giả sử `buffer` chứa 1.000 đối tượng, và một thao tác `clear()` chỉ viết:

```java
void clear() {
    size = 0;  // Chỉ xóa logic
}
```

Theo API, mảng đã rỗng; tuy nhiên **1.000 ô đầu của bộ đệm có thể vẫn chứa tham chiếu** đến các đối tượng cũ. Nếu mảng động được giữ lại để sử dụng lâu dài, bộ đệm vẫn là một đường tham chiếu tới những đối tượng đó.

Với một bộ đệm `Object[]` và `size` hiện tại, cách dọn phù hợp là:

```java
void clear() {
    Arrays.fill(buffer, 0, size, null);
    size = 0;
}
```

Đoạn mã này xóa tham chiếu ở **toàn bộ phần tử đang dùng**, rồi đặt `size` về 0. Với điều kiện từ trước các ô dự trữ đã được dọn sau mỗi lần xóa, sau thao tác `clear` toàn bộ bộ đệm không còn tham chiếu đến phần tử cũ.

Nếu trước đó đã có tham chiếu còn sót **ngoài đoạn `[0, size)`** do một lỗi khác, chỉ dọn `[0, size)` sẽ **không sửa được toàn bộ lỗi cũ**. Vì vậy, nên duy trì quy tắc dọn ô dự trữ ngay trong từng thao tác thay đổi `size`; nếu cần sửa một cấu trúc từng vi phạm quy tắc này, có thể phải kiểm tra hoặc dọn cả bộ đệm.

Đối với một mảng đang giữ `n` phần tử, `Arrays.fill(..., 0, size, null)` cần O(n) thao tác gán ô. Đây là **chi phí cần thiết trong cài đặt này** để chấm dứt các đường tham chiếu của bộ đệm đến những phần tử cũ; không nên tuyên bố `clear()` luôn O(1) cho mảng động chứa đối tượng.

### `clear` không nhất thiết trả lại dung lượng

Sau `clear`, có thể có `size = 0` nhưng `capacity = 1.024`. Bộ đệm vẫn chiếm bộ nhớ cho 1.024 **ô tham chiếu**, dù các ô đã được đặt thành `null`. Sự khác biệt là:

| Thao tác | Có thể bỏ tham chiếu đến phần tử cũ? | Có thể giảm số ô bộ đệm? |
| --- | --- | --- |
| Dọn các ô bằng `null` | Có | Không |
| Chỉ giảm `size` | Không chắc | Không |
| Thay bộ đệm bằng một bộ đệm nhỏ hoặc rỗng | Có, nếu không còn bộ đệm cũ được tham chiếu từ nơi khác | Có |
| Thu gọn bộ đệm bằng API riêng | Tùy cài đặt, thông thường chỉ giữ các phần tử còn dùng | Có thể |

Việc thu nhỏ quá thường xuyên lại gây nhiều lần cấp phát và sao chép. Nếu dự kiến nạp tiếp một danh sách lớn, giữ `capacity` và chỉ dọn các tham chiếu cũ thường là một lựa chọn hữu ích.

## 6. Thay phần tử và cấp phát lại có cần dọn không?

### Thay giá trị tại một chỉ số

Nếu thực hiện `set(i, newValue)` với `0 <= i < size`, phép gán `buffer[i] = newValue` thay thế tham chiếu cũ bằng tham chiếu mới. Nó **không tạo ô dư** vì `size` không đổi. Nếu cần trả lại phần tử cũ, phương thức có thể lưu và trả về nó trước khi ghi:

```java
Object set(int index, Object value) {
    if (index < 0 || index >= size) {
        throw new IndexOutOfBoundsException();
    }
    Object previous = buffer[index];
    buffer[index] = value;
    return previous;
}
```

Nếu chương trình gọi còn giữ `previous`, đối tượng cũ vẫn có thể sống. Không có yêu cầu phải đặt `buffer[index]` thành `null` giữa hai phép gán.

### Tăng dung lượng

Khi mở rộng bộ đệm, một cài đặt đúng cần sao chép đúng `size` phần tử hợp lệ:

```java
Object[] enlarged = new Object[newCapacity];
System.arraycopy(buffer, 0, enlarged, 0, size);
buffer = enlarged;
```

Các ô mới được khởi tạo thành `null` trong Java. Nếu phần dự trữ của bộ đệm cũ còn tham chiếu sót do lỗi và chương trình chỉ sao chép đoạn `[0, size)`, những tham chiếu sót đó **không được chuyển sang bộ đệm mới**. Nhưng điều này không thay thế cho việc dọn ô đúng lúc, vì không biết khi nào mảng mới cần mở rộng; hơn nữa, vùng cũ có thể chưa được thu hồi ngay.

### Thu nhỏ dung lượng

Khi thu nhỏ, cài đặt cần bảo đảm `newCapacity >= size` và chỉ sao chép các phần tử đang dùng. Nếu bộ đệm cũ không còn được giữ từ nơi khác, việc thay nó bằng vùng nhỏ hơn có thể đồng thời loại bỏ những tham chiếu cũ nằm ngoài phần logic. Tuy vậy, **thu nhỏ không phải cách duy nhất hoặc luôn thích hợp để sửa tham chiếu sót**: nó có thể đòi hỏi một lần cấp phát và sao chép O(n).

## 7. Ví dụ Java hoàn chỉnh: giữ `buffer[size..capacity)` sạch

Lớp sau dùng `Object[]` để biểu diễn mảng động tổng quát. Trong cài đặt minh họa này, ta chọn thêm một bất biến quản lý tham chiếu:

> **Với mọi `i` thỏa `size <= i < capacity`, `buffer[i] == null`.**

Đây là quy tắc hữu ích cho bộ đệm tham chiếu trong Java, **không phải định nghĩa bắt buộc của mọi mảng động**. Một phần tử logic vẫn được phép có giá trị `null` ở chỉ số nhỏ hơn `size`, nên không thể dùng `null` thay cho bộ đếm `size`.

```java
import java.util.Arrays;
import java.util.NoSuchElementException;

public class CleanDynamicArrayDemo {
    static final class DynamicArray<T> {
        private Object[] buffer = new Object[2];
        private int size = 0;

        int size() {
            return size;
        }

        int capacity() {
            return buffer.length;
        }

        @SuppressWarnings("unchecked")
        T get(int index) {
            checkIndex(index);
            return (T) buffer[index];
        }

        void add(T value) {
            ensureRoomForOne();
            buffer[size] = value;
            size++;
        }

        @SuppressWarnings("unchecked")
        T set(int index, T value) {
            checkIndex(index);
            T previous = (T) buffer[index];
            buffer[index] = value;
            return previous;
        }

        @SuppressWarnings("unchecked")
        T removeAt(int index) {
            checkIndex(index);
            T removed = (T) buffer[index];

            int count = size - index - 1;
            if (count > 0) {
                System.arraycopy(buffer, index + 1, buffer, index, count);
            }

            size--;
            buffer[size] = null; // Bỏ tham chiếu cuối cũ.
            return removed;
        }

        T removeLast() {
            if (size == 0) {
                throw new NoSuchElementException("Array is empty");
            }
            return removeAt(size - 1);
        }

        void clear() {
            Arrays.fill(buffer, 0, size, null);
            size = 0;
        }

        private void checkIndex(int index) {
            if (index < 0 || index >= size) {
                throw new IndexOutOfBoundsException("index=" + index);
            }
        }

        private void ensureRoomForOne() {
            if (size < buffer.length) {
                return;
            }
            if (buffer.length > Integer.MAX_VALUE / 2) {
                throw new IllegalStateException("Capacity too large");
            }
            int nextCapacity = buffer.length == 0 ? 1 : buffer.length * 2;
            buffer = Arrays.copyOf(buffer, nextCapacity);
        }

        String debugBuffer() {
            return Arrays.toString(buffer);
        }
    }

    static final class Document {
        private final String name;

        Document(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        DynamicArray<Document> docs = new DynamicArray<>();
        docs.add(new Document("A"));
        docs.add(new Document("B"));
        docs.add(new Document("C"));
        docs.add(new Document("D"));
        System.out.println("Ban dau: " + docs.debugBuffer());

        Document removed = docs.removeAt(1);
        System.out.println("Xoa " + removed + ": " + docs.debugBuffer());
        System.out.println("size=" + docs.size()
                           + ", capacity=" + docs.capacity());

        docs.removeLast();
        System.out.println("Xoa cuoi: " + docs.debugBuffer());

        docs.clear();
        System.out.println("Clear: " + docs.debugBuffer());
        System.out.println("size=" + docs.size()
                           + ", capacity=" + docs.capacity());
    }
}
```

Kết quả dự kiến:

```text
Ban dau: [A, B, C, D]
Xoa B: [A, C, D, null]
size=3, capacity=4
Xoa cuoi: [A, C, null, null]
Clear: [null, null, null, null]
size=0, capacity=4
```

Ở đây `debugBuffer()` cố ý in toàn bộ bộ đệm để minh họa; API công khai thông thường chỉ nên trả về `size` phần tử logic. Việc in chữ `null` trong kết quả cho thấy các ô không còn dùng đã được gán `null`, **không chứng minh GC đã thu hồi các đối tượng**. Chẳng hạn, biến `removed` trong `main` vẫn giữ đối tượng `B` sau khi xóa nó khỏi mảng.

Đối với triển khai tổng quát, `Object[]` lưu tham chiếu của các phần tử kiểu `T`. Phép ép kiểu trong `get`, `set` và `removeAt` phù hợp trong phạm vi lớp này vì dữ liệu chỉ được thêm qua giao diện `T`; một thư viện thực tế có thể cần thêm hợp đồng về `null`, truy cập đồng thời và giới hạn dung lượng.

## 8. Độ phức tạp của việc dọn ô

Để hiểu chi phí, phân biệt thao tác thay đổi dữ liệu logic và phần dọn tham chiếu:

| Thao tác | Phần thao tác chính | Phần dọn ô | Chi phí điển hình |
| --- | --- | --- | --- |
| `removeLast()` | Giảm `size`, lấy phần tử cuối | Gán `buffer[size] = null` | O(1), nếu không tự thu nhỏ |
| `removeAt(i)` | Dồn `size - i - 1` phần tử sang trái | Gán ô cuối cũ thành `null` | O(n) trong trường hợp xấu |
| `set(i, x)` | Thay tham chiếu tại một ô đang dùng | Không cần dọn ô ngoài vùng logic | O(1) |
| `clear()` | Làm rỗng phần logic | Gán `null` cho `size` ô cũ | O(n) trong cài đặt `Object[]` này |
| Tăng `capacity` | Cấp phát vùng lớn hơn, sao chép `size` ô | Các ô mới mặc định `null` | O(n) cho lần cấp phát lại, còn phụ thuộc dung lượng mới |
| Thu nhỏ `capacity` | Cấp phát vùng nhỏ hơn và sao chép phần còn dùng | Bỏ bộ đệm cũ khi không còn cần | Thường O(n) nếu phải sao chép |

Với `n = size` trước thao tác, `clear()` có thể cần O(n) để dọn tham chiếu. Nếu phần tử là số nguyên trong `int[]` và không có ràng buộc phải dọn dữ liệu cũ, một cài đặt có thể thực hiện `clear()` bằng cách đặt `size = 0` với chi phí O(1). Khác biệt này đến từ **mục tiêu quản lý tài nguyên**, không phải thay đổi bản chất khái niệm `size` hay `capacity`.

Không phải việc gán `null` nào cũng giải phóng bộ nhớ đáng kể ngay lập tức. Chi phí gán ô và hành vi GC phụ thuộc runtime; lợi ích quan trọng của quy tắc là tránh để **các cấu trúc sống lâu giữ vô tình những đối tượng đã bị loại về mặt logic**.

## 9. Liên hệ với các ngôn ngữ và thư viện

### Java: `ArrayList`

`ArrayList` lưu các tham chiếu trong một mảng nội bộ. Các thao tác xóa phần tử hoặc `clear()` theo cài đặt chuẩn cần xử lý những tham chiếu không còn dùng, để các đối tượng bị loại không bị giữ chỉ bởi bộ đệm của danh sách. `ArrayList.clear()` làm `size()` về 0 nhưng không nên hiểu rằng `capacity` cũng bắt buộc về 0; việc giảm bộ đệm là lựa chọn quản lý dung lượng khác.

Nếu ứng dụng giữ đối tượng đã bị xóa trong một biến, một danh sách khác hoặc bộ nhớ đệm khác, đối tượng vẫn có thể được tham chiếu. Do đó, dọn tham chiếu của một cấu trúc chỉ giải quyết **các đường tham chiếu do cấu trúc đó quản lý**.

### C++: `std::vector` với đối tượng và con trỏ

`std::vector<T>` thường lưu **đối tượng `T` trực tiếp** trong vùng lưu trữ liên tiếp. Khi `erase` hoặc `pop_back`, các phần tử bị xóa được hủy theo ngữ nghĩa của kiểu; không có quy tắc chung phải gán `nullptr` cho một ô ngoài `size()` như với `Object[]` của Java. `clear()` hủy các phần tử còn lại nhưng không nhất thiết giải phóng dung lượng bộ đệm.

Nếu `T` là một con trỏ thô như `Widget*`, hủy phần tử con trỏ **không tự động hủy đối tượng được trỏ tới**; việc quản lý sở hữu là trách nhiệm riêng. Dùng `std::unique_ptr<Widget>` khi vector sở hữu đối tượng sẽ giúp giải phóng đối tượng theo RAII khi phần tử sở hữu bị hủy. Cần phân biệt **dọn tham chiếu trong cấu trúc** với **quản lý quyền sở hữu và vòng đời đối tượng**.

### Python: `list`

Python `list` giữ các tham chiếu đến đối tượng. Các thao tác như `pop`, `del` hoặc `clear` loại phần tử khỏi danh sách; cài đặt Python thông dụng cập nhật việc sở hữu/tham chiếu tương ứng. Đối tượng bị loại có thể tiếp tục tồn tại nếu vẫn được tham chiếu ở nơi khác.

Ví dụ:

```python
items = [{"id": 1}, {"id": 2}]
removed = items.pop()
print(items)    # [{'id': 1}]
print(removed)  # {'id': 2} - bien removed van giu doi tuong
items.clear()
print(items)    # []
```

Ở đây biến `removed` vẫn giữ một đối tượng sau khi nó rời danh sách. Người dùng Python thường không thao tác trực tiếp với các ô dự trữ của `list`; vấn đề chính là hiểu **ai còn đang giữ tham chiếu tới đối tượng**.

## 10. Những sai lầm dễ mắc

1. **Chỉ giảm `size` sau xóa cuối mà quên dọn ô.** Với `Object[]`, ô cuối cũ có thể tiếp tục giữ đối tượng đã bị xóa về mặt logic.
2. **Dồn trái khi xóa giữa nhưng không gán `null` cho ô cuối cũ.** Ô đó có thể còn tham chiếu trùng với một phần tử logic và làm bất biến vùng dự trữ bị vi phạm.
3. **Đặt `size = 0` trong `clear()` nhưng để nguyên các tham chiếu cũ.** Một bộ đệm sống lâu có thể giữ toàn bộ đối tượng từng được thêm.
4. **Cho rằng `null` nghĩa là ô không được dùng.** `null` có thể là một **giá trị phần tử hợp lệ** nếu cấu trúc cho phép. Phải kiểm tra chỉ số dựa trên `size`.
5. **Nhầm dọn tham chiếu với giải phóng bộ đệm.** Dọn ô không làm giảm `capacity`; thu nhỏ là thao tác quản lý dung lượng riêng.
6. **Cho rằng đối tượng chắc chắn được thu hồi ngay sau khi gán `null`.** GC còn phụ thuộc các tham chiếu khác và thời điểm thu gom.
7. **Dọn toàn bộ bộ đệm ở mọi lần xóa.** Nếu chỉ một ô vừa hết hiệu lực, thường chỉ cần dọn một ô sau khi dịch chuyển; xóa toàn bộ `capacity` ô mỗi lần có thể làm tăng chi phí không cần thiết.
8. **Dùng con trỏ thô trong C++ rồi nghĩ `vector.erase` sẽ `delete` đối tượng.** Hủy một giá trị con trỏ không đồng nghĩa giải phóng đối tượng do con trỏ trỏ tới.
9. **Dùng phép xóa trung gian làm hỏng thứ tự.** Nếu cần bảo toàn thứ tự, hãy dồn vùng phía sau sang trái trước khi dọn ô cuối.

## 11. Tự kiểm tra

**Câu 1.** Mảng động có `buffer = [A, B, C, null]`, `size = 3`. Khi xóa phần tử cuối, cần làm gì để mảng không tiếp tục giữ `C` qua bộ đệm?

**Đáp án:** Lưu `C` nếu cần trả về, gán `buffer[2] = null` và giảm `size` từ 3 xuống 2. `capacity` vẫn có thể bằng 4.

**Câu 2.** Sau khi xóa `B` khỏi `[A, B, C, D]` bằng cách dồn trái, vì sao còn phải dọn ô cuối cũ?

**Đáp án:** Dồn trái tạo trạng thái vật lý như `[A, C, D, D]`. Sau khi `size` giảm xuống 3, ô thứ tư nằm ngoài phần tử logic nhưng còn tham chiếu tới `D`. Gán `null` cho ô đó giữ vùng dự trữ sạch và ngăn tham chiếu sót trong các thao tác tiếp theo.

**Câu 3.** Một mảng động có `size = 100`, `capacity = 200`. Nếu `clear()` dọn 100 ô đang dùng rồi đặt `size = 0`, số ô bộ đệm còn được cấp phát là bao nhiêu?

**Đáp án:** Vẫn là 200 ô nếu `clear` không thu nhỏ bộ đệm. Những ô đã được dọn không còn giữ tham chiếu đến phần tử cũ thông qua mảng động.

**Câu 4.** Sau khi `removeAt` trả về một đối tượng, tại sao đối tượng đó vẫn có thể tồn tại dù ô cũ đã được dọn?

**Đáp án:** Biến nhận giá trị trả về hoặc một cấu trúc khác vẫn có thể tham chiếu đến đối tượng. Dọn ô chỉ bỏ đường tham chiếu của bộ đệm.

**Câu 5.** Với `Object[]`, `clear()` chỉ viết `size = 0` có thể gây vấn đề gì trong một mảng động tồn tại lâu dài?

**Đáp án:** Các ô cũ vẫn có thể giữ tham chiếu đến những đối tượng không còn thuộc danh sách logic, khiến chúng chưa đủ điều kiện được thu gom rác chỉ vì mảng động vẫn sống.

**Câu 6.** Tại sao không thể dùng `buffer[i] != null` để kiểm tra chỉ số `i` có hợp lệ trong một mảng động tổng quát?

**Đáp án:** Một phần tử logic hợp lệ có thể mang giá trị `null`, còn ô ngoài `size` có thể chứa tham chiếu sót nếu cài đặt có lỗi. Chỉ số hợp lệ phải thỏa `0 <= i < size`.

**Câu 7.** Nếu một mảng động chứa số nguyên nguyên thủy trong `int[]`, dọn ô bằng `0` có bắt buộc để giúp GC thu hồi các đối tượng không?

**Đáp án:** Không. Một ô `int` chứa trực tiếp giá trị số, không phải tham chiếu đến đối tượng độc lập. Quyết định xóa giá trị cũ có thể phục vụ hợp đồng dữ liệu hoặc kiểm tra trạng thái, nhưng không nhằm loại đường tham chiếu tới đối tượng.

**Câu 8.** Nếu đã xóa hết phần tử nhưng `capacity = 10.000`, việc dọn ô thành `null` có tự động giảm vùng lưu trữ về 0 ô không?

**Đáp án:** Không. Dọn tham chiếu và thay đổi dung lượng là hai thao tác riêng. Cấu trúc có thể giữ bộ đệm để tái sử dụng hoặc chủ động thu nhỏ nếu cần và thư viện hỗ trợ.

**Câu 9.** Trong C++, một `std::vector<std::unique_ptr<Widget>>` xóa phần tử sở hữu cuối cùng thì điều gì xảy ra với `Widget`, so với `std::vector<Widget*>`?

**Đáp án:** Khi phần tử `unique_ptr` bị hủy, nó hủy đối tượng `Widget` đang sở hữu theo cơ chế RAII. Với con trỏ thô `Widget*`, việc vector xóa/hủy giá trị con trỏ không tự động `delete` đối tượng được trỏ tới; cần có cơ chế quản lý quyền sở hữu phù hợp.

**Câu 10.** Cần thêm điều kiện quản lý bộ đệm nào để bảo đảm không có tham chiếu cũ sót ngoài phần tử logic trong ví dụ Java?

**Đáp án:** Duy trì `buffer[i] == null` cho mọi `i` thỏa `size <= i < capacity`. Khi xóa giữa hoặc cuối, dọn ô cuối cũ; khi `clear`, dọn toàn bộ đoạn đang dùng. Các thao tác thêm hoặc mở rộng phải bảo toàn điều kiện này.

**Điểm ghi nhớ:** `size` xác định **phần tử logic** của mảng động, còn các ô đã cấp phát có thể vẫn tồn tại sau khi xóa. Trong bộ đệm chứa tham chiếu đối tượng, hãy **bỏ tham chiếu ở ô vừa ngừng sử dụng** và dọn các ô đang dùng khi `clear`. Điều đó giúp tránh giữ đối tượng ngoài ý muốn mà không cần thu nhỏ bộ đệm sau mỗi lần xóa.

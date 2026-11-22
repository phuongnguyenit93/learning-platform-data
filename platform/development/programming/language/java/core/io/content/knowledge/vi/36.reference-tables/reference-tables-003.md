# Bảng biến đổi trạng thái Buffer trong Java NIO

`Buffer` trong `java.nio` là mô hình **cửa sổ truy cập dữ liệu có trạng thái**. Khi đọc hoặc ghi qua `ByteBuffer`, `CharBuffer` hay các buffer kiểu nguyên thủy khác, dữ liệu được quản lý bằng bốn mốc: `capacity`, `limit`, `position` và `mark`. Bảng dưới đây giúp dự đoán chính xác trạng thái trước và sau mỗi thao tác, đặc biệt trong chu trình **ghi dữ liệu → `flip()` → đọc dữ liệu → `clear()` hoặc `compact()`**.

## 1. Quy ước đọc bảng trạng thái

| Ký hiệu | Ý nghĩa | Quy tắc |
|---|---|---|
| `C` = `capacity()` | Tổng số phần tử mà buffer chứa được | Không đổi trong suốt vòng đời của buffer đó |
| `L` = `limit()` | Biên trên *loại trừ* của vùng hiện được phép truy cập | `0 ≤ L ≤ C` |
| `P` = `position()` | Chỉ số của phần tử kế tiếp khi đọc/ghi tương đối | `0 ≤ P ≤ L` |
| `M` = `mark` | Vị trí đã đánh dấu bằng `mark()`; không có getter công khai | Chưa đặt (ký hiệu `—`), hoặc `0 ≤ M ≤ P` |
| `R` = `remaining()` | Số phần tử còn lại từ vị trí hiện tại đến giới hạn | `R = L − P` |

**Bất biến:** nếu mark đang tồn tại thì `0 ≤ M ≤ P ≤ L ≤ C`. `P` chỉ là con trỏ logic: nó **không nhất thiết** phản ánh phần tử nào trong bộ nhớ đã được khởi tạo. Các thao tác thay đổi trạng thái có thể làm mất mark; Java sẽ ném `InvalidMarkException` khi gọi `reset()` mà không còn mark hợp lệ.

Ví dụ: `ByteBuffer.allocate(8)` tạo `(P=0, L=8, C=8, M=—)`; `remaining() = 8`. Vùng thao tác tương đối là `[P, L)`. Phần tử ở chỉ số `L` **không** thuộc vùng hợp lệ, kể cả khi `L < C`.

## 2. Bảng biến đổi trạng thái chuẩn

Trong bảng: `P₀, L₀, C₀, M₀` là trạng thái trước thao tác; `P₁, L₁, M₁` là trạng thái sau. `C` luôn bằng `C₀`. “Giữ nguyên” nghĩa là không đổi con trỏ/mark, không khẳng định dữ liệu bộ nhớ giống nhau.

| Thao tác | Điều kiện/ý nghĩa | Trạng thái sau | Tác động đến mark và dữ liệu |
|---|---|---|---|
| `allocate(C)` | Tạo buffer mới với `C ≥ 0` | `P₁=0, L₁=C` | `M₁=—`; phần tử ban đầu bằng giá trị mặc định của kiểu |
| `put(value)` | Ghi **tương đối** một phần tử, yêu cầu `P₀ < L₀` | `P₁=P₀+1, L₁=L₀` | Mark giữ nguyên; ghi dữ liệu tại vị trí `P₀` |
| `get()` | Đọc **tương đối** một phần tử, yêu cầu `P₀ < L₀` | `P₁=P₀+1, L₁=L₀` | Mark giữ nguyên; đọc dữ liệu tại `P₀` |
| `put(src)` / `get(dst)` | Ghi/đọc tương đối `n` phần tử; cần `n ≤ L₀−P₀` | `P₁=P₀+n, L₁=L₀` | Mark giữ nguyên nếu thao tác thành công; vùng dữ liệu liên quan được ghi/đọc |
| `get(i)` / `put(i, value)` | Truy cập **tuyệt đối**; yêu cầu `0 ≤ i < L₀` | `P₁=P₀, L₁=L₀` | Mark giữ nguyên; `put` thay đổi dữ liệu tại `i` |
| `flip()` | Chuyển từ giai đoạn ghi sang đọc **phần đã ghi** | `P₁=0, L₁=P₀` | Xóa mark; **không** sao chép/xóa dữ liệu |
| `clear()` | Chuẩn bị ghi lại toàn bộ vùng chứa | `P₁=0, L₁=C₀` | Xóa mark; **không** xóa byte/ký tự cũ |
| `rewind()` | Đọc lại từ đầu trong giới hạn hiện hành | `P₁=0, L₁=L₀` | Xóa mark; dữ liệu không đổi |
| `compact()` | Giữ phần **chưa đọc** `[P₀,L₀)`, chuẩn bị ghi nối tiếp | `P₁=L₀−P₀, L₁=C₀` | Xóa mark; dồn `L₀−P₀` phần tử chưa đọc về đầu buffer |
| `mark()` | Ghi nhớ vị trí hiện tại | `P₁=P₀, L₁=L₀, M₁=P₀` | Đặt/ghi đè mark; dữ liệu không đổi |
| `reset()` | Quay về mark đã đặt | `P₁=M₀, L₁=L₀, M₁=M₀` | Giữ mark; nếu không có mark thì ném `InvalidMarkException` |
| `position(p)` | Đặt vị trí mới, cần `0 ≤ p ≤ L₀` | `P₁=p, L₁=L₀` | Nếu `M₀ > p` thì xóa mark; ngược lại giữ |
| `limit(l)` | Đặt giới hạn mới, cần `0 ≤ l ≤ C₀` | `L₁=l, P₁=min(P₀,l)` | Nếu `M₀ > l` thì xóa mark; ngược lại giữ |
| `remaining()` / `hasRemaining()` | Truy vấn `L−P` / `P<L` | Mọi mốc giữ nguyên | Không làm thay đổi dữ liệu |

**Lưu ý về API:** `flip()`, `clear()`, `rewind()`, `mark()`, `reset()`, `position(int)` và `limit(int)` có ở `Buffer`. `get`, `put` và `compact` là phương thức trên các buffer có kiểu như `ByteBuffer`; `compact()` không phải phương thức dùng trực tiếp trên biến chỉ có kiểu `Buffer`. Không phải buffer nào cũng hỗ trợ ghi; buffer chỉ đọc sẽ từ chối `put` và `compact`.

## 3. Bảng diễn tiến thực tế: ghi, đọc một phần, dồn và ghi tiếp

Với buffer chứa tám byte, ví dụ sau cho thấy **mark**, phần dữ liệu chưa đọc và trạng thái sau `compact()`. Ký hiệu `—` là chưa có mark; chuỗi trong cột “Dữ liệu liên quan” chỉ mô tả phần đã ghi/còn cần đọc, không cam kết nội dung các ô ngoài phạm vi đó.

| Bước | Thao tác | P | L | C | M | R=L−P | Dữ liệu liên quan |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `allocate(8)` | 0 | 8 | 8 | — | 8 | Chưa ghi dữ liệu ứng dụng |
| 2 | `put("ABCD")` | 4 | 8 | 8 | — | 4 | `[0..3] = ABCD` |
| 3 | `flip()` | 0 | 4 | 8 | — | 4 | Cửa sổ đọc `ABCD` |
| 4 | `get(2 byte)` → `AB` | 2 | 4 | 8 | — | 2 | Chưa đọc: `CD` |
| 5 | `mark()` | 2 | 4 | 8 | 2 | 2 | Đánh dấu trước `C` |
| 6 | `get()` → `C` | 3 | 4 | 8 | 2 | 1 | Chưa đọc theo vị trí hiện tại: `D` |
| 7 | `reset()` | 2 | 4 | 8 | 2 | 2 | Quay lại trước `CD` |
| 8 | `compact()` | 2 | 8 | 8 | — | 6 | Dồn `CD` về chỉ số `0,1` |
| 9 | `put("EF")` | 4 | 8 | 8 | — | 4 | `[0..3] = CDEF` |
| 10 | `flip()` | 0 | 4 | 8 | — | 4 | Cửa sổ đọc `CDEF` |
| 11 | `get(4 byte)` → `CDEF` | 4 | 4 | 8 | — | 0 | Hết dữ liệu hợp lệ trong cửa sổ |
| 12 | `rewind()` | 0 | 4 | 8 | — | 4 | Có thể đọc lại `CDEF` |
| 13 | `clear()` | 0 | 8 | 8 | — | 8 | Dữ liệu cũ còn có thể nằm trong bộ nhớ, nhưng không còn được xem là một bản ghi hợp lệ |

Điểm dễ nhầm ở bước 8: `compact()` lấy **phần chưa đọc tính từ position hiện tại**, chứ không lấy toàn bộ dữ liệu từng ghi. Nếu không gọi `reset()` ở bước 7, `compact()` chỉ dồn `D` và cho `P=1`.

## 4. Chương trình Java 17+ chạy độc lập

Lưu tệp đúng tên `BufferStateDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class BufferStateDemo {
    private static void state(String action, ByteBuffer buffer) {
        System.out.printf(
                "%s: P=%d, L=%d, C=%d, R=%d%n",
                action,
                buffer.position(),
                buffer.limit(),
                buffer.capacity(),
                buffer.remaining()
        );
    }

    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(8);
        state("allocate", buffer);

        buffer.put("ABCD".getBytes(StandardCharsets.US_ASCII));
        state("put ABCD", buffer);

        buffer.flip();
        state("flip", buffer);

        byte[] firstTwo = new byte[2];
        buffer.get(firstTwo);
        System.out.println("read 2 = " + new String(firstTwo, StandardCharsets.US_ASCII));
        state("get 2", buffer);

        buffer.mark();
        state("mark", buffer);

        System.out.println("next = " + (char) buffer.get());
        state("get C", buffer);

        buffer.reset();
        state("reset", buffer);

        buffer.compact();
        state("compact", buffer);

        buffer.put("EF".getBytes(StandardCharsets.US_ASCII));
        state("put EF", buffer);

        buffer.flip();
        state("flip 2", buffer);

        byte[] finalBytes = new byte[buffer.remaining()];
        buffer.get(finalBytes);
        System.out.println("final = " + new String(finalBytes, StandardCharsets.US_ASCII));
        state("get all", buffer);

        buffer.rewind();
        state("rewind", buffer);

        buffer.clear();
        state("clear", buffer);
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac BufferStateDemo.java
java BufferStateDemo
~~~

Stdout dự kiến chính xác:

~~~text
allocate: P=0, L=8, C=8, R=8
put ABCD: P=4, L=8, C=8, R=4
flip: P=0, L=4, C=8, R=4
read 2 = AB
get 2: P=2, L=4, C=8, R=2
mark: P=2, L=4, C=8, R=2
next = C
get C: P=3, L=4, C=8, R=1
reset: P=2, L=4, C=8, R=2
compact: P=2, L=8, C=8, R=6
put EF: P=4, L=8, C=8, R=4
flip 2: P=0, L=4, C=8, R=4
final = CDEF
get all: P=4, L=4, C=8, R=0
rewind: P=0, L=4, C=8, R=4
clear: P=0, L=8, C=8, R=8
~~~

Kết quả minh họa việc `reset()` khôi phục `P=2` nhưng không đổi `L=4`, sau đó `compact()` giữ chính xác `CD`; `clear()` chỉ đặt lại giới hạn logic.

## 5. Những nhánh biến đổi thường bị bỏ sót

### Giảm position hoặc limit có thể vô hiệu hóa mark

Giả sử trạng thái là `(P=5, L=8, C=8, M=4)`.

- Gọi `position(2)` ⇒ `(P=2, L=8, M=—)` vì mark `4 > 2`. Gọi `reset()` lúc này ném `InvalidMarkException`.
- Gọi `limit(3)` **trên trạng thái gốc** ⇒ `(P=3, L=3, M=—)`; position bị ép xuống `3` và mark `4` bị bỏ.
- Gọi `limit(6)` **trên trạng thái gốc** ⇒ `(P=5, L=6, M=4)`; mark vẫn hợp lệ.
- Gọi `position(6)` **trên trạng thái gốc** ⇒ `(P=6, L=8, M=4)`; mark vẫn hợp lệ.

Hai setter chỉ thay đổi trạng thái nếu đối số trong khoảng hợp lệ. `position(p)` với `p > limit`, hoặc `limit(l)` với `l > capacity`, sẽ ném `IllegalArgumentException`.

### Truy cập tuyệt đối và truy cập tương đối

Giả sử `(P=2, L=5, C=8)`:

- `get()` lấy chỉ số `2` rồi tăng `P` lên `3`.
- `get(4)` lấy chỉ số `4` và **không tăng `P`**.
- `put(1, (byte) 7)` ghi chỉ số `1` và **không tăng `P`**.
- `get(5)` không hợp lệ vì `limit` là biên loại trừ, mặc dù `5 < capacity`.

Với `ByteBuffer`, đọc tương đối khi không đủ dữ liệu ném `BufferUnderflowException`; ghi tương đối khi không đủ chỗ ném `BufferOverflowException`; chỉ số tuyệt đối ngoài `[0, limit)` thường ném `IndexOutOfBoundsException`. Ghi vào buffer chỉ đọc ném `ReadOnlyBufferException`. Kiểm tra `hasRemaining()` hoặc `remaining()` giúp tránh đọc/ghi vượt cửa sổ.

### `slice()`, `duplicate()` và trạng thái của view

Các view chia sẻ **nội dung lưu trữ** nhưng có các mốc vị trí độc lập:

| Tạo từ buffer nguồn | Position của view | Limit / Capacity của view | Quan hệ với dữ liệu và mark |
|---|---|---|---|
| `slice()` | `0` | Bằng `remaining()` của nguồn tại lúc tạo | Chỉ ánh xạ vùng `[P,L)` của nguồn; mark mới chưa xác định; dùng chung dữ liệu |
| `duplicate()` | Bằng `P` của nguồn | Bằng `L/C` của nguồn | Copy trạng thái gồm mark (nếu có); dùng chung dữ liệu, từ đó các mốc được cập nhật độc lập |
| `asReadOnlyBuffer()` trên `ByteBuffer` | Bằng `P` của nguồn | Bằng `L/C` của nguồn | Chia sẻ dữ liệu và sao chép mốc/mark ban đầu; cấm ghi qua view |

Ví dụ: nguồn có `(P=2, L=5, C=8)` thì `slice()` tạo view `(P=0, L=3, C=3)`. Sau khi `slice()`, thay đổi position của view không di chuyển position của nguồn. Thay đổi **nội dung** qua một view cho phép ghi vẫn có thể nhìn thấy từ view khác vì chúng chia sẻ vùng lưu trữ.

## 6. Chọn đúng thao tác trong luồng I/O

| Nhu cầu | Thao tác | Lý do |
|---|---|---|
| Ghi vào buffer trống và chuẩn bị tiêu thụ dữ liệu vừa ghi | `flip()` | Giới hạn vùng đọc theo `position` cũ |
| Đọc lại dữ liệu trong giới hạn hiện tại | `rewind()` | Giữ `limit`, đưa `position` về `0` |
| Đã xử lý hết dữ liệu, muốn nhận mẻ mới từ đầu | `clear()` | Mở toàn bộ sức chứa để ghi; không cần giữ phần chưa đọc |
| Đã tiêu thụ một phần, cần nối mẻ mới vào phần chưa xử lý | `compact()` | Dồn phần `remaining()` xuống đầu và mở chỗ cho mẻ tiếp theo |
| Muốn thử đọc rồi quay lại | `mark()` → đọc → `reset()` | Khôi phục position nếu mark chưa bị vô hiệu hóa |
| Chỉ muốn nhìn phần tử tại chỉ số xác định | `get(index)` | Không làm lệch position của lần đọc tương đối tiếp theo |

Khi nhận dữ liệu phân mảnh từ `SocketChannel`, thường dùng **ghi từ channel → `flip()` → tiêu thụ các thông điệp hoàn chỉnh → `compact()` → đọc tiếp**. Nếu một thông điệp còn thiếu byte, `compact()` giữ phần dở dang để ghép với lần đọc tiếp. Chỉ dùng `clear()` khi chắc chắn không cần phần còn lại. Với việc ghi buffer ra channel, một lần `write(buffer)` có thể chưa tiêu thụ hết `remaining()`; phải dựa vào trạng thái sau ghi để xử lý phần còn lại, không giả định mọi byte đã được gửi.

**Quy tắc nhớ nhanh:** `flip` đặt `limit = position cũ` để đọc; `clear` đặt `limit = capacity` để ghi lại; `compact` giữ `remaining` và đặt `position = số phần tử vừa dồn`. Không thao tác nào trong ba thao tác này tự thực hiện I/O với tệp/socket.
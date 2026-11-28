# Thêm cuối khi còn chỗ và khi phải cấp phát lại

Trong **mảng động** (*dynamic array*), thao tác thêm một phần tử vào cuối thường được gọi là `append`, `push_back` hoặc `add` tùy ngôn ngữ và thư viện. Dù giao diện rất ngắn gọn, bên trong thao tác có **hai đường xử lý khác nhau**: ghi ngay vào ô còn trống, hoặc cấp phát một bộ đệm mới lớn hơn rồi sao chép dữ liệu trước khi ghi.

Sự khác biệt này giải thích vì sao thêm cuối thường có thời gian **O(1)** nhưng đôi khi một lần thêm riêng lẻ phải mất **O(n)**. Hiểu được quá trình đó cũng giúp phân tích độ phức tạp khấu hao, mức sử dụng bộ nhớ và tính đúng đắn của mảng động khi tự cài đặt.

## 1. Điều kiện quyết định: `size < capacity` hay `size == capacity`?

Giả sử mảng động được biểu diễn bằng:

- `buffer`: một mảng nền lưu các ô liên tiếp đã cấp phát.
- `size`: số phần tử hiện có, với chỉ số hợp lệ từ `0` đến `size - 1`.
- `capacity`: số ô mà `buffer` đang có, thường bằng `buffer.length`.

Tại mọi thời điểm, cấu trúc phải giữ bất biến:

\[
0 \le \text{size} \le \text{capacity}.
\]

| Trạng thái trước khi thêm | Cách xử lý | Chi phí chính |
| --- | --- | --- |
| `size < capacity` | Ghi vào `buffer[size]`, tăng `size` lên 1 | O(1) |
| `size == capacity` | Tạo bộ đệm lớn hơn, sao chép dữ liệu cũ, đổi bộ đệm, ghi phần tử mới, tăng `size` | O(n) cho một lần thêm, với `n = size` |

`capacity - size` là số ô còn trống trong bộ đệm hiện tại. Điều kiện **đầy** là `size == capacity`, không phải khi giá trị cuối cùng trong mảng bằng `0` hoặc `null`. Mỗi ô dự trữ có thể mang một giá trị vật lý, nhưng chỉ những ô có chỉ số nhỏ hơn `size` mới là phần tử hợp lệ.

## 2. Trường hợp 1: Còn chỗ — thêm cuối trong O(1)

Giả sử đang lưu `[10, 20, 30]` trong bộ đệm sức chứa năm ô:

```text
Trước append(40):

chỉ số:      0     1     2     3     4
          +-----+-----+-----+-----+-----+
buffer:   |  10 |  20 |  30 |  ?  |  ?  |
          +-----+-----+-----+-----+-----+
          <--- size = 3 ---><-- còn 2 -->
          <-------- capacity = 5 ------->

Sau append(40):

chỉ số:      0     1     2     3     4
          +-----+-----+-----+-----+-----+
buffer:   |  10 |  20 |  30 |  40 |  ?  |
          +-----+-----+-----+-----+-----+
          <------ size = 4 ------><- 1 ->
          <-------- capacity = 5 ------->
```

Các bước xử lý:

1. Kiểm tra `size < capacity`, tức `3 < 5`.
2. Ghi `40` vào `buffer[3]`, vì `3` chính là vị trí kế tiếp sau phần tử cuối.
3. Tăng `size` từ `3` lên `4`. `capacity` vẫn bằng `5`.

Mã giả:

```text
append(value):
    if size < capacity:
        buffer[size] = value
        size = size + 1
        return
    # Xử lý khi đầy ở phần tiếp theo
```

Không cần duyệt phần tử đang có, dời dữ liệu hay xin thêm vùng lưu trữ. Với giả định ghi một ô và cập nhật biến đếm đều tốn thời gian hằng số, thao tác này có độ phức tạp **O(1)**.

## 3. Trường hợp 2: Hết chỗ — cấp phát lại rồi thêm

Khi `size == capacity`, vị trí `buffer[size]` **không tồn tại trong bộ đệm hiện tại**. Không thể cứ ghi thẳng rồi hy vọng vùng nhớ tự mở rộng. Cần tạo bộ đệm lớn hơn trước.

Giả sử mảng chứa `[10, 20, 30, 40]` với `size = capacity = 4` và muốn thêm `50`. Nếu chọn chiến lược tăng gấp đôi, dung lượng mới bằng tám:

```text
1. Bộ đệm cũ đã đầy

       0     1     2     3
    +-----+-----+-----+-----+
    |  10 |  20 |  30 |  40 |    size = 4, capacity = 4
    +-----+-----+-----+-----+

2. Xin bộ đệm mới 8 ô và sao chép 4 phần tử

       0     1     2     3     4     5     6     7
    +-----+-----+-----+-----+-----+-----+-----+-----+
    |  10 |  20 |  30 |  40 |  ?  |  ?  |  ?  |  ?  |
    +-----+-----+-----+-----+-----+-----+-----+-----+

3. Dùng bộ đệm mới, ghi 50 vào vị trí 4, tăng size

       0     1     2     3     4     5     6     7
    +-----+-----+-----+-----+-----+-----+-----+-----+
    |  10 |  20 |  30 |  40 |  50 |  ?  |  ?  |  ?  |
    +-----+-----+-----+-----+-----+-----+-----+-----+
                                      size = 5, capacity = 8
```

Trình tự tổng quát:

1. Chọn `newCapacity > capacity`, thường theo hệ số tăng trưởng cố định lớn hơn một.
2. Yêu cầu cấp phát `newBuffer` có `newCapacity` ô.
3. **Sao chép đúng `size` phần tử hợp lệ**, từ chỉ số `0` đến `size - 1`, sang bộ đệm mới.
4. Chuyển cấu trúc sang dùng `newBuffer`; cập nhật `capacity` nếu lưu riêng. Bộ đệm cũ được giải phóng hoặc thu hồi theo cơ chế của ngôn ngữ.
5. Ghi phần tử mới tại `buffer[size]` và tăng `size` lên một.

Trong ví dụ, phải sao chép **bốn** phần tử cũ trước khi ghi `50`, nên độ phức tạp của lần thêm này là **O(4)**. Tổng quát với `n` phần tử đang có, chi phí sao chép là **O(n)**. Việc cấp phát/khởi tạo vùng mới còn có thể phụ thuộc vào dung lượng được yêu cầu.

### Lần đầu thêm khi dung lượng bằng 0

Với mảng động rỗng có `size = 0` và `capacity = 0`, không thể tính dung lượng mới đơn giản bằng `2 * capacity`: kết quả vẫn là `0`. Một quy tắc phổ biến để minh họa là:

```text
if capacity == 0:
    newCapacity = 1
else:
    newCapacity = 2 * capacity
```

Khi đó lần thêm đầu tiên cấp phát một ô, sao chép **0** phần tử cũ, ghi giá trị mới và chuyển `size` thành `1`. Những thư viện thực tế có thể bắt đầu với một dung lượng mặc định khác.

## 4. Mã giả đầy đủ và các bất biến

```text
append(value):
    if size == capacity:
        if capacity == 0:
            newCapacity = 1
        else:
            newCapacity = 2 * capacity   # minh họa, cần kiểm tra tràn số

        newBuffer = allocate(newCapacity)
        for i = 0 to size - 1:
            newBuffer[i] = buffer[i]

        buffer = newBuffer
        capacity = newCapacity

    buffer[size] = value
    size = size + 1
```

Để chứng minh thao tác đúng, xét hai trường hợp:

- **Còn chỗ:** từ `size < capacity` suy ra `size + 1 <= capacity`. Ghi vào vị trí `size` là hợp lệ và sau khi tăng `size`, bất biến `0 <= size <= capacity` vẫn đúng.
- **Phải mở rộng:** nếu `size = capacity`, chọn `newCapacity > capacity` sẽ tạo ít nhất một ô mới. Sau khi sao chép, các phần tử cũ vẫn đúng thứ tự tại đoạn `[0, size)`; ghi phần tử mới vào ô `size` là hợp lệ. Khi tăng `size`, bất biến tiếp tục đúng.

Điều kiện quan trọng là **phải bảo đảm bộ đệm có đủ chỗ trước khi ghi phần tử**. Nếu tăng `size` trước khi ghi mà quá trình cấp phát hoặc sao chép thất bại, trạng thái cấu trúc có thể không còn phản ánh dữ liệu thực tế.

## 5. Thử bằng Java: theo dõi từng lần mở rộng

Ví dụ sau dùng `int[]` làm bộ đệm, giữ `size` riêng và suy `capacity` từ `buffer.length`. Biến `totalCopied` đếm số phần tử cũ được chuyển trong các lần cấp phát lại, giúp thấy rõ sự khác nhau giữa hai đường đi của `append`.

```java
import java.util.Arrays;

public class AppendDynamicArray {
    static class IntDynamicArray {
        private int[] buffer = new int[0];
        private int size = 0;
        private long totalCopied = 0;

        int size() {
            return size;
        }

        int capacity() {
            return buffer.length;
        }

        long totalCopied() {
            return totalCopied;
        }

        void append(int value) {
            if (size == buffer.length) {
                int oldCapacity = buffer.length;

                // Giới hạn minh họa để tránh tràn số khi nhân đôi.
                if (oldCapacity > Integer.MAX_VALUE / 2) {
                    throw new IllegalStateException("Khong the nhan doi capacity");
                }
                int newCapacity = oldCapacity == 0 ? 1 : oldCapacity * 2;

                int[] newBuffer = new int[newCapacity];
                System.arraycopy(buffer, 0, newBuffer, 0, size);
                totalCopied += size;
                buffer = newBuffer;

                System.out.println(
                    "Mo rong: " + oldCapacity + " -> " + newCapacity
                    + ", sao chep " + size + " phan tu"
                );
            }

            buffer[size] = value;
            size++;
        }

        String state() {
            return Arrays.toString(Arrays.copyOf(buffer, size))
                + " | size=" + size
                + ", capacity=" + capacity()
                + ", totalCopied=" + totalCopied;
        }
    }

    public static void main(String[] args) {
        IntDynamicArray a = new IntDynamicArray();
        for (int value : new int[] {10, 20, 30, 40, 50}) {
            a.append(value);
            System.out.println(a.state());
        }
    }
}
```

Kết quả theo thứ tự:

```text
Mo rong: 0 -> 1, sao chep 0 phan tu
[10] | size=1, capacity=1, totalCopied=0
Mo rong: 1 -> 2, sao chep 1 phan tu
[10, 20] | size=2, capacity=2, totalCopied=1
Mo rong: 2 -> 4, sao chep 2 phan tu
[10, 20, 30] | size=3, capacity=4, totalCopied=3
[10, 20, 30, 40] | size=4, capacity=4, totalCopied=3
Mo rong: 4 -> 8, sao chep 4 phan tu
[10, 20, 30, 40, 50] | size=5, capacity=8, totalCopied=7
```

Đặc biệt, thêm `40` không kích hoạt mở rộng vì trước lần thêm đó `size = 3`, `capacity = 4`. Thêm `50` lại phải sao chép bốn phần tử vì lúc này `size = capacity = 4`. Sau năm lần thêm, tổng cộng chỉ sao chép bảy phần tử cũ qua những lần mở rộng, dù chuỗi có năm phần tử.

Đoạn mã dùng `new int[newCapacity]` nên có thể ném lỗi nếu hệ thống không đủ bộ nhớ hoặc yêu cầu mảng quá lớn. Đây là ví dụ học tập; mã thực tế cần chính sách dung lượng tối đa phù hợp với runtime và dữ liệu.

## 6. Tại sao O(1) khấu hao khi có những lần O(n)?

Nếu mỗi lần hết chỗ chỉ tăng `capacity` thêm đúng một ô, một chuỗi `n` lần thêm có thể phải sao chép:

\[
0 + 1 + 2 + \cdots + (n-1) = \frac{n(n-1)}{2} = O(n^2).
\]

Đó là nguyên nhân các mảng động thường dành **nhiều hơn một ô** khi phải mở rộng. Với chính sách nhân đôi, các lần phải sao chép xảy ra khi bộ đệm có sức chứa `1, 2, 4, 8, ...`. Tổng số phần tử cũ cần sao chép sau `n` lần thêm bị chặn trên bởi một tổng cấp số nhân:

\[
1 + 2 + 4 + \cdots < 2n.
\]

Vì vậy, tổng công ghi `n` phần tử mới là O(n), và tổng công sao chép giữa các đợt mở rộng cũng là O(n). **Tổng thời gian cho `n` lần thêm cuối là O(n)**; chia đều cho `n` lần thêm được chi phí **O(1) khấu hao (*amortized*)** cho mỗi lần.

Điều này có ba ý nghĩa khác nhau:

| Phát biểu | Đúng hay sai? | Lý do |
| --- | --- | --- |
| Một lần `append` khi còn ô trống chạy O(1) | Đúng | Không phải sao chép phần tử cũ |
| Một lần `append` khi đầy luôn chạy O(1) | Sai | Có thể phải sao chép toàn bộ `n` phần tử |
| Với chiến lược tăng dung lượng theo hệ số cố định > 1, nhiều lần `append` có trung bình khấu hao O(1) | Đúng | Chi phí sao chép được phân bổ cho nhiều lần thêm |

**Khấu hao không phải đo xác suất.** Đây là bảo đảm về tổng chi phí trên cả một chuỗi thao tác, kể cả khi những lần mở rộng là các đợt làm việc tốn kém. Nếu chương trình cần thời gian phản hồi thật ổn định cho từng thao tác, một lần cấp phát lại O(n) vẫn có thể là vấn đề cần tính đến.

## 7. Đánh đổi về bộ nhớ và tác động của cấp phát lại

Mở rộng dung lượng giúp giảm tần suất sao chép, nhưng đổi lại phải giữ những ô chưa dùng. Nếu `size = 5`, `capacity = 8` thì ba ô là chỗ dự trữ. Với chiến lược nhân đôi và mảng không bị thu nhỏ, ngay sau lần mở rộng từ `c` lên `2c`, nhiều ô còn trống; khi tăng dần đến `size = 2c` thì các ô đó sẽ được sử dụng.

Trong quá trình mở rộng, có lúc **cả bộ đệm cũ và bộ đệm mới cùng tồn tại** cho đến khi sao chép xong. Vì thế lượng bộ nhớ đỉnh có thể vượt mức chỉ tính từ `capacity` mới. Sau khi chuyển sang bộ đệm mới, bộ đệm cũ có thể được thu hồi theo cơ chế quản lý bộ nhớ.

Việc sao chép phần tử cũng phụ thuộc cách biểu diễn:

- Với `int[]` ở ví dụ Java, `System.arraycopy` sao chép các giá trị số nguyên.
- Với mảng tham chiếu đối tượng trong Java, việc sao chép mảng chuyển các **tham chiếu**, không nhân bản sâu từng đối tượng.
- Với `std::vector` trong C++, cấp phát lại có thể di chuyển hoặc sao chép đối tượng theo kiểu phần tử; con trỏ, tham chiếu và iterator trỏ vào vùng lưu trữ cũ có thể bị mất hiệu lực.

Các **chỉ số logic** `0, 1, ..., size - 1` vẫn chỉ đến đúng phần tử theo thứ tự sau khi mở rộng. Điều không được giả định là địa chỉ bộ nhớ vật lý của phần tử sẽ giữ nguyên.

Nếu đã biết trước sẽ thêm khoảng `k` phần tử, một số thư viện cho phép **dành sẵn dung lượng** (chẳng hạn `reserve(k)` trong C++ hoặc `ensureCapacity(k)` của Java `ArrayList`). Việc này có thể giảm số lần mở rộng trong lúc thêm. Nó **không** tự làm tăng số phần tử logic. Bản thân việc dành sẵn chỗ cũng có thể phải cấp phát và sao chép.

## 8. Lỗi dễ gặp khi tự viết `append`

1. **Ghi trước khi kiểm tra chỗ trống.** Khi `size == capacity`, viết `buffer[size] = value` sẽ truy cập ra ngoài bộ đệm. Phải mở rộng trước.
2. **Nhân đôi dung lượng 0.** `2 * 0` vẫn bằng 0. Cần dung lượng khởi đầu dương, ví dụ 1.
3. **Sao chép sai số ô.** Chỉ cần sao chép các phần tử hợp lệ trong `[0, size)`. Đọc ngoài vùng đó có thể đưa dữ liệu dự trữ vào phần tử logic.
4. **Quên thay `buffer` hoặc cập nhật `capacity`.** Dù đã cấp phát vùng mới, nếu cấu trúc vẫn dùng vùng cũ hoặc có trường dung lượng không đồng bộ, các thao tác sau sẽ sai.
5. **Quên tăng `size` đúng một lần.** Sau một lần thêm thành công phải có `size_new = size_old + 1`; tăng nhiều lần hoặc bỏ quên làm hỏng ranh giới truy cập.
6. **Cho rằng nhân đôi luôn an toàn.** Dung lượng có giới hạn; `2 * capacity` có thể gây tràn số nguyên. Cấp phát còn có thể thất bại do thiếu bộ nhớ.
7. **Giả định địa chỉ phần tử không đổi.** Cấp phát lại có thể thay vùng nhớ. Cần xét quy định về tham chiếu, con trỏ và iterator của thư viện đang dùng.

Một quy tắc thiết kế hữu ích là **cấp phát và sao chép trước khi thay bộ đệm đang hoạt động**. Nếu tạo vùng mới thất bại, bộ đệm cũ vẫn còn và `size` chưa thay đổi. Với các kiểu phần tử có phép sao chép/di chuyển có thể ném lỗi, mức bảo đảm khi thất bại còn phụ thuộc ngôn ngữ và cài đặt cụ thể.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Trước thao tác thêm, `size = 6` và `capacity = 10`. Thêm một phần tử cuối có cần cấp phát lại không? Các giá trị sau thao tác là gì?

**Đáp án:** Không. Ghi vào chỉ số `6`; sau đó `size = 7` và `capacity = 10`.

**Câu 2.** Trước thao tác thêm, `size = capacity = 8`. Nếu chiến lược là nhân đôi và việc cấp phát thành công, cần sao chép bao nhiêu phần tử và hai giá trị sau thao tác là gì?

**Đáp án:** Sao chép tám phần tử sang bộ đệm 16 ô, ghi phần tử mới tại chỉ số `8`; `size = 9`, `capacity = 16`.

**Câu 3.** Một mảng động dùng `capacity = 0` lúc ban đầu và nhân đôi khi đầy. Sau khi lần lượt thêm sáu phần tử, các lần cấp phát xảy ra ở những dung lượng nào?

**Đáp án:** Cấp phát lần lượt `1, 2, 4, 8` ô; cuối cùng `size = 6` và `capacity = 8`.

**Câu 4.** Vì sao không được kết luận rằng mọi lần thêm cuối đều O(1) chỉ từ việc O(1) khấu hao?

**Đáp án:** O(1) khấu hao là nhận xét cho **cả chuỗi thao tác**. Một lần thêm khi đầy vẫn phải cấp phát và sao chép O(n) phần tử; các lần không mở rộng bù lại chi phí đó trong phân tích tổng thể.

**Câu 5.** Sau khi mảng mở rộng, các phần tử có còn truy cập được bằng chỉ số cũ không? Địa chỉ bộ nhớ cũ có nhất thiết còn hợp lệ không?

**Đáp án:** Thứ tự và chỉ số logic của các phần tử cũ được giữ nguyên nếu sao chép đúng. Địa chỉ bộ nhớ, con trỏ hoặc iterator gắn với bộ đệm cũ có thể không còn hợp lệ.

Điều cốt lõi của thao tác thêm cuối là một quyết định rất cụ thể: **còn ô thì ghi ngay; hết ô thì bảo đảm có bộ đệm lớn hơn, sao chép phần đang dùng, rồi mới ghi**. Từ quyết định ấy phát sinh cả ưu điểm truy cập nhanh, thời gian thêm khấu hao O(1) và chi phí bộ nhớ dự trữ của mảng động.

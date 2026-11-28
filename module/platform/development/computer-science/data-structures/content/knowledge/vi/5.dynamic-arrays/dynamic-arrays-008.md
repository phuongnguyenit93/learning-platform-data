# Thu nhỏ dung lượng và tránh tăng–giảm liên tục quanh ngưỡng

Mảng động (*dynamic array*) thường dành sẵn nhiều ô hơn số phần tử thực tế để thêm cuối nhanh. Khi dữ liệu tăng, cấu trúc có thể cấp phát bộ đệm lớn hơn và sao chép các phần tử cũ. Nhưng khi xóa nhiều phần tử, một câu hỏi khác xuất hiện: **có nên thu nhỏ bộ đệm để trả lại bộ nhớ không?**

Nếu không thu nhỏ, chương trình có thể giữ một vùng nhớ lớn dù chỉ còn rất ít phần tử. Nếu thu nhỏ quá sớm, một chuỗi thêm rồi xóa quanh cùng ngưỡng có thể khiến bộ đệm liên tục tăng và giảm, dẫn đến cấp phát, sao chép dữ liệu lặp đi lặp lại. Hiện tượng này được gọi là **dao động cấp phát** (*resize thrashing*).

Bài học phân tích điều kiện thu nhỏ, chứng minh vì sao ngưỡng tăng và ngưỡng giảm cần cách nhau, minh họa chính sách **tăng gấp đôi khi đầy, giảm một nửa khi số phần tử không quá một phần tư dung lượng**, và chỉ rõ ảnh hưởng tới thời gian khấu hao, bộ nhớ dư và cách sử dụng các thư viện phổ biến.

## 1. Thu nhỏ bộ đệm có nghĩa là gì?

Một mảng động được biểu diễn bằng:

| Thành phần | Ý nghĩa |
| --- | --- |
| `buffer` | Vùng lưu trữ liên tiếp của các ô đã cấp phát |
| `size` | Số phần tử logic đang có |
| `capacity` | Số ô trong bộ đệm hiện tại |

Bất biến cần giữ:

\[
0\leq\text{size}\leq\text{capacity}.
\]

Giả sử bộ đệm có `capacity = 16` nhưng sau khi xóa chỉ còn `size = 3`:

```text
Chỉ số:  0    1    2    3    4              15
        +----+----+----+----+----+-- ... --+
buffer: | A  | B  | C  | ?  | ?  |    ?     |
        +----+----+----+----+----+-- ... --+
        <-- size = 3 --><---- còn 13 ô ---->
        <--------- capacity = 16 ----------->
```

Các phần tử hợp lệ chỉ nằm trong đoạn `[0, size)`. Một ô nằm trong bộ đệm nhưng có chỉ số từ `size` trở đi **không được coi là phần tử hiện có**.

Nếu quyết định giảm `capacity` từ 16 xuống 8, cấu trúc thường phải:

1. Cấp phát một bộ đệm mới có 8 ô.
2. Sao chép **3 phần tử hợp lệ** sang các chỉ số `0, 1, 2` của bộ đệm mới.
3. Thay bộ đệm cũ bằng bộ đệm mới; sau đó bộ đệm cũ có thể được thu hồi.
4. Giữ nguyên `size = 3` và cập nhật `capacity = 8`.

Không được giảm `capacity` xuống dưới `size` vì như vậy sẽ không còn chỗ để giữ toàn bộ dữ liệu. Việc thu nhỏ **không tự xóa thêm phần tử nào**: đó là quyết định quản lý dung lượng, tách biệt với thao tác xóa logic.

### Vì sao không thu nhỏ ngay sau mọi lần xóa?

Nếu một mảng từng chứa 1.000.000 phần tử rồi giảm xuống 10 phần tử, giữ nguyên bộ đệm có thể gây tốn bộ nhớ. Tuy nhiên, nếu ứng dụng chuẩn bị thêm lại gần một triệu phần tử, giữ vùng đã cấp phát giúp tránh phải cấp phát và sao chép nhiều lần.

Việc thu nhỏ cũng **có chi phí riêng**: cấp phát vùng mới, sao chép các phần tử còn lại, quản lý vùng cũ và đôi khi tạo đỉnh bộ nhớ tạm thời. Vì vậy, quyết định thu nhỏ nên dựa vào mức sử dụng còn lại, tần suất thêm/xóa và yêu cầu về bộ nhớ.

## 2. Sai lầm thường gặp: thu nhỏ ngay khi còn một nửa

Xét chính sách tưởng như tự nhiên:

- **Tăng:** khi `size == capacity` và cần thêm, tăng `capacity` lên gấp đôi.
- **Giảm:** sau khi xóa, nếu `size <= capacity / 2`, giảm `capacity` còn một nửa.

Lấy bộ đệm có bốn ô đã đầy:

```text
Ban đầu:
  size = 4, capacity = 4
  [A][B][C][D]

Thêm E: cần mở rộng 4 -> 8, sao chép A,B,C,D
  size = 5, capacity = 8
  [A][B][C][D][E][ ][ ][ ]

Xóa E: size trở lại 4, chạm ngưỡng capacity/2
  Thu nhỏ 8 -> 4, sao chép A,B,C,D
  size = 4, capacity = 4
  [A][B][C][D]

Lặp lại: thêm E -> mở rộng; xóa E -> thu nhỏ; ...
```

Mỗi cặp thao tác **thêm rồi xóa** đưa `size` về vị trí ban đầu, nhưng chính sách vẫn buộc chương trình cấp phát **hai lần**, đồng thời sao chép bốn phần tử khi tăng và bốn phần tử khi giảm.

Tổng quát, nếu trạng thái lặp là `size = capacity = C`, thì:

- Thêm một phần tử: mở rộng từ `C` lên `2C` và sao chép `C` phần tử cũ.
- Xóa phần tử đó: `size` trở lại `C`; nếu thu nhỏ khi không quá nửa, bộ đệm `2C` giảm về `C` và sao chép `C` phần tử còn lại.

Như vậy, **hai thao tác logic có thể gây 2C lần sao chép ô**, dù số phần tử cuối chuỗi không đổi. Lặp `k` cặp thao tác với `C` lớn có thể gây Θ(`kC`) công sao chép. Chi phí này không thể được phân bổ về O(1) cho từng thao tác theo cách lập luận thông thường của mảng động.

Đây là lý do **không nên dùng cùng một ranh giới khoảng 50% để vừa xác định trạng thái vừa đầy sau mở rộng, vừa kích hoạt thu nhỏ**. Cần tạo một vùng đệm giữa hai thời điểm quyết định tăng và giảm.

## 3. Giải pháp: hai ngưỡng cách nhau (*hysteresis*)

Một chính sách kinh điển cho thao tác thêm/xóa **ở cuối mảng** là:

| Tình huống | Quy tắc | Hệ quả |
| --- | --- | --- |
| Thêm cuối khi `size < capacity` | Ghi phần tử mới, tăng `size` | Không cấp phát lại |
| Thêm cuối khi `size == capacity` | Cấp phát bộ đệm mới có dung lượng gấp đôi, rồi thêm | Trả chi phí tăng dung lượng khi thật sự đầy |
| Xóa cuối, sau xóa `size > capacity / 4` | Chỉ giảm `size` | Giữ chỗ để thêm lại |
| Xóa cuối, sau xóa `size <= capacity / 4` | Cấp phát bộ đệm có dung lượng bằng một nửa, sao chép phần đang dùng | Trả bớt bộ nhớ khi mảng đã rất thưa |

Để đơn giản, ta bắt đầu với `capacity = 1` và luôn giữ **dung lượng tối thiểu bằng 1 ô**. Với các dung lượng là lũy thừa của hai, điều kiện thu nhỏ trong cài đặt số nguyên có thể viết `size <= capacity / 4`, sử dụng phép chia nguyên.

### Vì sao một phần tư giúp tránh dao động?

Nếu bộ đệm có `C` ô và sau xóa chỉ còn `C/4` phần tử, thu nhỏ còn `C/2` ô. Mức sử dụng của bộ đệm mới là:

\[
\frac{\text{size}}{\text{capacity mới}}
=\frac{C/4}{C/2}
=\frac12.
\]

Nghĩa là sau khi thu nhỏ, bộ đệm mới **mới chỉ đầy khoảng 50%**, còn nhiều chỗ cho các lần thêm tiếp theo. Muốn kích hoạt mở rộng trở lại, cần thêm khoảng `C/4` phần tử để lấp đầy và một lần thêm nữa để vượt sức chứa.

Ngược lại, ngay sau khi bộ đệm `C` ô đã đầy được tăng lên `2C` để thêm một phần tử, ta có `size = C + 1` và `capacity = 2C`, tức mức sử dụng hơi trên 50%. Để chạm ngưỡng thu nhỏ 25% của bộ đệm `2C`, phải xóa nhiều phần tử, thay vì chỉ xóa phần tử vừa thêm.

**Khoảng cách giữa hai ngưỡng** tạo ra cơ chế trễ quyết định (*hysteresis*): mảng không đổi dung lượng liên tục chỉ vì `size` tăng hoặc giảm một đơn vị gần cùng một ranh giới.

### Minh họa từng thao tác

Mảng có tám phần tử và bộ đệm tám ô. Xóa dần cho đến khi còn hai phần tử, sau đó thêm lại:

| Thao tác | `size` sau thao tác | `capacity` sau thao tác | Lý do |
| --- | ---: | ---: | --- |
| Ban đầu | 8 | 8 | Bộ đệm đầy |
| Xóa cuối lần 1 | 7 | 8 | Chưa chạm ngưỡng `8/4 = 2` |
| Xóa cuối lần 2 | 6 | 8 | Không thu nhỏ |
| Xóa cuối lần 3 | 5 | 8 | Không thu nhỏ |
| Xóa cuối lần 4 | 4 | 8 | Đang dùng 50%, vẫn giữ dung lượng |
| Xóa cuối lần 5 | 3 | 8 | Vẫn lớn hơn 25% |
| Xóa cuối lần 6 | 2 | 4 | Chạm 25%, giảm `8 -> 4` |
| Thêm một phần tử | 3 | 4 | Còn chỗ |
| Thêm một phần tử nữa | 4 | 4 | Vừa đầy |
| Thêm một phần tử nữa | 5 | 8 | Phải tăng `4 -> 8` |
| Xóa cuối một lần | 4 | 8 | Chưa đến ngưỡng 25%, không giảm |

Đặc biệt, ở dòng cuối `size = 4`, `capacity = 8`: **xóa từ năm xuống bốn phần tử không gây thu nhỏ**. Với chính sách thu nhỏ ở ngưỡng 50%, dòng này lại kích hoạt cấp phát và sao chép, mở đầu một chuỗi dao động.

## 4. Mã giả: tách thao tác xóa logic khỏi quyết định thu nhỏ

```text
buffer có capacity = 1
size = 0

append(value):
    if size == capacity:
        newCapacity = 2 * capacity
        cấp phát newBuffer có newCapacity ô
        sao chép size phần tử hợp lệ sang newBuffer
        buffer = newBuffer
        capacity = newCapacity

    buffer[size] = value
    size = size + 1

removeLast():
    nếu size == 0:
        báo lỗi vì mảng rỗng

    value = buffer[size - 1]
    size = size - 1
    xóa tham chiếu tại buffer[size] nếu cần

    nếu capacity > 1 và size <= capacity / 4:
        newCapacity = max(1, capacity / 2)
        cấp phát newBuffer có newCapacity ô
        sao chép size phần tử hợp lệ sang newBuffer
        buffer = newBuffer
        capacity = newCapacity

    trả về value
```

Có bốn quy tắc cần giữ:

1. **Không giảm dung lượng xuống dưới `size`.** Với ngưỡng một phần tư, dung lượng mới bằng một nửa luôn đủ chứa các phần tử còn lại.
2. **Chỉ sao chép đoạn `[0, size)`.** Các ô ngoài đoạn này là dự trữ, không phải dữ liệu logic cần bảo toàn.
3. **Giữ dung lượng tối thiểu dương** để `append` có thể tiếp tục mở rộng. Có thể dùng chính sách khởi tạo từ 0, nhưng phải xử lý riêng phép thêm đầu tiên.
4. **Cấp phát và sao chép trước khi thay `buffer`.** Nếu cấp phát thất bại, việc giải quyết lỗi cần được thiết kế rõ; các thư viện thực tế có quy định riêng về bảo đảm trạng thái khi lỗi xảy ra.

Một lưu ý về tính nhất quán: nếu `removeLast()` đã giảm `size` rồi thao tác thu nhỏ thất bại, mảng vẫn có thể giữ `buffer` cũ và `capacity` cũ mà không vi phạm `size <= capacity`. Tuy nhiên, API phải xác định rõ hành vi khi lỗi cấp phát xảy ra sau khi phần tử đã được xóa. Trong cài đặt sản xuất, lựa chọn xử lý lỗi cần phù hợp với hợp đồng của phương thức.

## 5. Cài đặt Java minh họa ngưỡng 25%

Đoạn mã sau dùng `int[]` làm bộ đệm, tăng gấp đôi khi thêm vào mảng đầy, giảm một nửa khi sau xóa còn tối đa một phần tư dung lượng và không giảm dưới một ô. Hai bộ đếm cho biết số lần cấp phát tăng, giảm và tổng phần tử cũ được sao chép.

```java
import java.util.Arrays;
import java.util.NoSuchElementException;

public class DynamicArrayShrinkDemo {
    static final class DynamicIntArray {
        private int[] buffer = new int[1];
        private int size = 0;
        private int growthCount = 0;
        private int shrinkCount = 0;
        private long copiedElements = 0;

        int size() {
            return size;
        }

        int capacity() {
            return buffer.length;
        }

        void append(int value) {
            if (size == buffer.length) {
                if (buffer.length > Integer.MAX_VALUE / 2) {
                    throw new IllegalStateException("Capacity too large");
                }
                changeCapacity(buffer.length * 2, true);
            }
            buffer[size] = value;
            size++;
        }

        int removeLast() {
            if (size == 0) {
                throw new NoSuchElementException("Dynamic array is empty");
            }

            int removed = buffer[size - 1];
            size--;
            buffer[size] = 0;

            if (buffer.length > 1 && size <= buffer.length / 4) {
                int newCapacity = Math.max(1, buffer.length / 2);
                changeCapacity(newCapacity, false);
            }

            return removed;
        }

        private void changeCapacity(int newCapacity, boolean growing) {
            // Sao chép phần tử đang dùng, giữ nguyên size và thứ tự.
            int[] nextBuffer = Arrays.copyOf(buffer, newCapacity);
            copiedElements += size;
            buffer = nextBuffer;
            if (growing) {
                growthCount++;
            } else {
                shrinkCount++;
            }
        }

        void printState(String label) {
            int[] logicalData = Arrays.copyOf(buffer, size);
            System.out.println(label + ": " + Arrays.toString(logicalData)
                + ", size=" + size
                + ", capacity=" + capacity()
                + ", grows=" + growthCount
                + ", shrinks=" + shrinkCount
                + ", copied=" + copiedElements);
        }
    }

    public static void main(String[] args) {
        DynamicIntArray a = new DynamicIntArray();
        for (int value = 1; value <= 8; value++) {
            a.append(value);
        }
        a.printState("Them 8");

        for (int i = 0; i < 6; i++) {
            a.removeLast();
        }
        a.printState("Xoa 6");

        a.append(9);
        a.append(10);
        a.append(11);
        a.printState("Them lai 3");

        a.removeLast();
        a.printState("Xoa 1");
    }
}
```

Kết quả dự kiến:

```text
Them 8: [1, 2, 3, 4, 5, 6, 7, 8], size=8, capacity=8, grows=3, shrinks=0, copied=7
Xoa 6: [1, 2], size=2, capacity=4, grows=3, shrinks=1, copied=9
Them lai 3: [1, 2, 9, 10, 11], size=5, capacity=8, grows=4, shrinks=1, copied=13
Xoa 1: [1, 2, 9, 10], size=4, capacity=8, grows=4, shrinks=1, copied=13
```

Giải thích số liệu: tăng từ 1 lên 2, từ 2 lên 4 và từ 4 lên 8 sao chép tổng `1 + 2 + 4 = 7` phần tử; giảm từ 8 xuống 4 khi còn hai phần tử sao chép thêm 2; tăng từ 4 lên 8 khi đầy sao chép thêm 4. Tổng là `7 + 2 + 4 = 13` phần tử được sao chép qua các lần thay bộ đệm.

Đoạn mã có mục đích minh họa nên đặt giới hạn đơn giản trước khi nhân đôi. Một triển khai thực tế cần xét giới hạn kích thước mảng của runtime, trường hợp không đủ bộ nhớ và hành vi khi cấp phát thu nhỏ thất bại. Với `Object[]`, khi xóa cần gán `null` cho ô vừa thôi sử dụng để tránh giữ tham chiếu đối tượng không cần thiết; ví dụ dùng `int[]` nên đặt ô về 0 chỉ để dễ quan sát.

## 6. Vì sao có thể giữ chi phí O(1) khấu hao?

Một lần thay bộ đệm vẫn có thể tốn O(`n`) vì phải sao chép các phần tử còn lại. Nhưng với chính sách tăng gấp đôi khi đầy và giảm một nửa khi còn tối đa một phần tư, **một lần thay dung lượng đắt tiền không thể lặp lại ngay sau một hoặc hai thao tác thêm/xóa gần cùng ngưỡng**, trừ những trường hợp dung lượng rất nhỏ có chi phí hằng số.

Sau khi mở rộng từ `C` lên `2C` để thêm một phần tử, mảng có `C + 1` phần tử. Muốn co bộ đệm `2C` xuống `C`, `size` phải giảm đến không quá `C/2`. Do đó cần ít nhất khoảng `C/2` lần xóa kể từ lần mở rộng.

Sau khi co từ `C` xuống `C/2` tại `size = C/4`, muốn mở rộng trở lại phải thêm khoảng `C/4` phần tử để làm đầy vùng `C/2`, rồi thêm tiếp để vượt sức chứa.

Nói cách khác, **mỗi lần thay dung lượng tốn Θ(C) công thường được ngăn cách với lần thay dung lượng ngược chiều bởi Θ(C) thao tác rẻ hơn**. Chi phí thay bộ đệm vì vậy có thể được phân bổ cho nhiều thao tác thêm/xóa, thay vì lặp lại trên từng cặp thao tác.

### Cách chứng minh bằng hàm thế năng (nâng cao)

Có thể diễn đạt lập luận bằng **hàm thế năng** (*potential method*). Gọi `s = size`, `c = capacity` và xét hàm không âm:

\[
\Phi(s,c)=
\begin{cases}
2s-c, & s\ge c/2,\\[4pt]
c/2-s, & s<c/2.
\end{cases}
\]

Hãy hình dung `\Phi` như tín dụng dùng để trả cho công sao chép ở lần thay bộ đệm. Theo mô hình mỗi thao tác ghi/xóa một ô tốn O(1) và sao chép một phần tử tốn O(1):

- **Thêm khi đầy:** trước khi tăng dung lượng, `s=c=C` nên `\Phi=C`. Sau khi cấp phát `2C` ô và thêm phần tử, `s=C+1`, thế năng chỉ còn `2`. Sự giảm khoảng `C` của thế năng trả cho `C` lần sao chép.
- **Xóa kích hoạt thu nhỏ:** với `C` chia hết cho 4, trước lần xóa, `s=C/4+1` nên `\Phi=C/4-1`. Sau khi xóa đến `s=C/4` và thu nhỏ xuống `c=C/2`, thế năng trở về 0. Phần thế năng giảm trả cho khoảng `C/4` phần tử phải sao chép.
- **Thêm/xóa không thay bộ đệm:** mỗi thao tác chỉ thay `s` một đơn vị, nên mức thay đổi của `\Phi` bị chặn bởi một hằng số.

Các dung lượng nhỏ (1 hoặc 2 ô) và sai số làm tròn chỉ làm thay đổi hằng số. Vì thế, nếu chỉ xét một chuỗi gồm `append` và `removeLast`, bắt đầu từ cấu trúc rỗng với dung lượng tối thiểu cố định, tổng công của `m` thao tác là **O(m)**. Chi phí khấu hao cho mỗi thao tác là **O(1)**.

Kết quả này có phạm vi rõ ràng: **một lần thêm/xóa cuối riêng lẻ** vẫn có thể tốn O(n) nếu phải cấp phát lại; còn **chèn hoặc xóa giữa mảng** vẫn có thể mất O(n) do phải dịch chuyển phần đuôi, ngay cả khi chính sách dung lượng đã tốt.

## 7. Đánh đổi: bộ nhớ dư, bộ nhớ đỉnh và tốc độ

Gọi `spare = capacity - size` là số ô đã cấp phát nhưng chưa sử dụng. Nếu `size = 2` và `capacity = 8`, còn sáu ô dư. Sau khi thu nhỏ xuống bốn ô, còn hai ô dư và cấu trúc không mất phần tử nào.

So sánh các chiến lược:

| Chính sách | Bộ nhớ giữ lại | Số lần cấp phát | Đặc điểm |
| --- | --- | --- | --- |
| Không thu nhỏ tự động | Có thể còn nhiều ô dư sau khi xóa mạnh | Ít cấp phát khi dữ liệu tăng lại | Phù hợp khi dự kiến tái sử dụng dung lượng |
| Thu nhỏ ngay khi còn 50% | Giảm dung lượng sớm | Có thể tăng–giảm liên tục quanh ngưỡng | Dễ phát sinh sao chép lặp lại |
| Thu nhỏ khi còn tối đa 25%, tăng khi đầy | Giữ khoảng an toàn giữa tăng và giảm | Tránh dao động sát ngưỡng | Cho O(1) khấu hao với thêm/xóa cuối theo điều kiện đã nêu |
| Chủ động thu gọn khi biết dữ liệu sẽ nhỏ lâu dài | Giảm chỗ dư theo nhu cầu | Cấp phát tại thời điểm được lựa chọn | Phù hợp khi ứng dụng có giai đoạn chuyển đổi rõ ràng |

Một điểm cần phân biệt là **bộ nhớ ổn định** với **bộ nhớ đỉnh lúc thay bộ đệm**. Khi co từ `C` xuống `C/2`, chương trình có thể phải giữ đồng thời hai vùng lưu trữ có tổng khoảng `1,5C` ô cho đến khi hoàn tất sao chép và có thể giải phóng vùng cũ. Một runtime quản lý bộ nhớ tự động cũng có thể chưa thu hồi ngay bộ đệm cũ.

Với kiểu dữ liệu lớn hoặc khi bộ nhớ hạn chế, đỉnh sử dụng bộ nhớ có thể quan trọng không kém `capacity` cuối cùng. Nếu cần thu nhỏ, có thể chọn thời điểm ít tải và kiểm tra sức chứa thực tế thay vì ép thu nhỏ sau mọi lần xóa.

## 8. Thư viện thực tế xử lý việc thu nhỏ thế nào?

Không nên mặc định tất cả mảng động đều tự co bộ đệm khi số phần tử giảm:

- **Java `ArrayList`:** `size()` cho số phần tử logic. `trimToSize()` yêu cầu thu gọn sức chứa nội bộ về số phần tử hiện có; `clear()` xóa phần tử logic nhưng không nên được hiểu là yêu cầu bắt buộc giải phóng toàn bộ dung lượng dự trữ.
- **C++ `std::vector`:** `size()` và `capacity()` cho hai đại lượng riêng. `clear()` xóa các phần tử nhưng không làm thay đổi `capacity()`; `shrink_to_fit()` là **yêu cầu không bắt buộc** (*non-binding request*) để giảm sức chứa. Nó có thể không cấp phát lại và không đảm bảo `capacity() == size()` sau lời gọi.
- **Python `list`:** `len(a)` biểu thị số phần tử, nhưng Python không có API chuẩn tương đương `capacity()`. Chi tiết tăng/giảm dung lượng thuộc cài đặt, nên không nên suy ra bộ nhớ còn giữ từ riêng `len(a)`.

Với `std::vector`, các thao tác thực sự cấp phát lại có thể làm mất hiệu lực con trỏ, tham chiếu và iterator trỏ vào vùng lưu trữ cũ. Do đó, thu nhỏ chủ động cũng cần được xem xét nếu chương trình đang giữ các tham chiếu kiểu này.

Một ví dụ ứng dụng: bộ nhớ đệm lưu một danh sách lớn trong giai đoạn nạp dữ liệu rồi chỉ cần giữ vài mục. Sau giai đoạn nạp, có thể cân nhắc thu gọn một lần nếu biết dữ liệu sẽ nhỏ trong thời gian dài. Ngược lại, nếu khối lượng dữ liệu thường xuyên tăng cao trở lại, giữ dung lượng dự trữ có thể tiết kiệm các đợt cấp phát.

## 9. Lỗi thường gặp

1. **Thu nhỏ khi vừa chạm 50% và tăng khi đầy.** Hai ngưỡng quá gần nhau có thể gây tăng–giảm luân phiên sau các cặp thêm/xóa.
2. **Cho rằng xóa phần tử phải giảm `capacity`.** Xóa làm `size` giảm; thay đổi `capacity` là chính sách riêng của cài đặt.
3. **Chọn dung lượng mới nhỏ hơn `size`.** Như vậy không đủ ô để chứa dữ liệu còn lại và làm hỏng bất biến `size <= capacity`.
4. **Sao chép toàn bộ `capacity` khi thu nhỏ.** Chỉ phần tử logic trong `[0, size)` cần được bảo toàn. Sao chép cả vùng dự trữ là không cần thiết và có thể vượt giới hạn bộ đệm mới.
5. **Thu nhỏ xuống 0 nhưng không xử lý lần thêm tiếp theo.** Nếu chọn dung lượng tối thiểu bằng 0, lần thêm từ rỗng phải cấp phát dung lượng dương trước khi ghi.
6. **Cho rằng thu nhỏ miễn phí và ngay lập tức trả bộ nhớ cho hệ điều hành.** Cấp phát lại có chi phí, và việc thu hồi bộ nhớ thực tế tùy trình cấp phát/runtime.
7. **Áp dụng O(1) khấu hao cho mọi thao tác xóa bất kỳ vị trí.** Xóa giữa mảng còn cần dồn dữ liệu về bên trái, thường là O(n) riêng cho phần dịch chuyển.
8. **Ép thu gọn sau từng thao tác dù sắp thêm lại.** Việc thu hẹp quá thường xuyên có thể làm phát sinh nhiều lần cấp phát lại và sao chép.

## 10. Tự kiểm tra

**Câu 1.** Một mảng có `size = 5`, `capacity = 16`. Theo quy tắc co một nửa khi sau xóa `size <= capacity / 4`, xóa cuối một phần tử có khiến mảng thu nhỏ không?

**Đáp án:** Có. Sau xóa còn `size = 4`, bằng `16 / 4`. Mảng co từ 16 xuống 8 ô, sao chép bốn phần tử còn lại.

**Câu 2.** Theo chính sách co khi còn 50%, vì sao cặp `append` rồi `removeLast` có thể gây sao chép lặp lại dù `size` cuối cùng không đổi?

**Đáp án:** Nếu ban đầu `size = capacity = C`, lần thêm sẽ tăng dung lượng lên `2C` và sao chép `C` phần tử; lần xóa đưa `size` về `C` đúng bằng một nửa `2C` và lại thu nhỏ, sao chép thêm `C` phần tử. Lặp cặp thao tác sẽ lặp cả hai đợt cấp phát.

**Câu 3.** Sau khi mảng co từ `capacity = 8` xuống `capacity = 4` tại `size = 2`, cần thêm ít nhất bao nhiêu phần tử để lại kích hoạt một lần tăng dung lượng?

**Đáp án:** Ba lần thêm: từ 2 lên 3, rồi lên 4 (vừa đầy), sau đó thêm lần thứ ba phải mở rộng từ 4 lên 8.

**Câu 4.** Mảng có `size = 4`, `capacity = 8`. Xóa một phần tử cuối theo ngưỡng một phần tư có làm giảm `capacity` không?

**Đáp án:** Không. Sau xóa `size = 3`, vẫn lớn hơn `8 / 4 = 2`; dung lượng giữ nguyên 8.

**Câu 5.** Một mảng còn 1.000 phần tử trong bộ đệm 8.192 ô. Nếu thực hiện thao tác thu gọn xuống 1.024 ô, mảng cần sao chép bao nhiêu phần tử logic và điều kiện an toàn nào phải thỏa mãn?

**Đáp án:** Cần sao chép 1.000 phần tử logic; dung lượng mới 1.024 phải **không nhỏ hơn `size = 1.000`**. Đây là ví dụ cho một thao tác thu gọn về mức đủ chỗ, không nhất thiết là kết quả của một bước giảm đúng một nửa.

**Câu 6.** Chính sách tăng gấp đôi khi đầy và co một nửa khi còn tối đa một phần tư đảm bảo điều gì cho chuỗi `m` lần thêm/xóa **ở cuối** từ mảng rỗng?

**Đáp án:** Trong mô hình sao chép một ô tốn O(1) và dung lượng tối thiểu cố định, tổng chi phí của `m` thao tác là O(m), tức O(1) khấu hao mỗi thao tác. Một lần thay bộ đệm riêng lẻ vẫn có thể tốn O(n).

**Câu 7.** Tại sao không nên gọi `shrink_to_fit()` sau mỗi lần xóa của `std::vector` khi chương trình thường xuyên thêm lại phần tử?

**Đáp án:** Việc yêu cầu co liên tục có thể gây cấp phát và chuyển/sao chép phần tử nhiều lần nếu thư viện thực hiện thu gọn, rồi mở rộng trở lại khi thêm. `shrink_to_fit()` cũng không đảm bảo sẽ thu nhỏ ở mọi lời gọi.

**Điểm ghi nhớ:** Thu nhỏ dung lượng giúp tiết kiệm ô dự trữ, nhưng thao tác này cũng có chi phí. Đặt **ngưỡng thu nhỏ thấp hơn rõ rệt so với mức đầy để tăng dung lượng** tạo vùng an toàn giữa hai quyết định, tránh cấp phát tăng–giảm liên tục. Với chính sách tăng gấp đôi khi đầy và co một nửa ở ngưỡng một phần tư, thêm/xóa cuối vẫn có O(1) khấu hao trong điều kiện phân tích chuẩn, đồng thời bộ đệm có thể trả bớt bộ nhớ khi dữ liệu giảm lâu dài.

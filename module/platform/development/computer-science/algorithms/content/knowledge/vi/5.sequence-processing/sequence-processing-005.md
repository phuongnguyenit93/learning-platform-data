# Mảng hiệu và cập nhật hàng loạt trên đoạn

Một yêu cầu thường gặp trong thuật toán xử lý dãy là: **có rất nhiều thao tác cộng một giá trị vào mọi phần tử thuộc một đoạn**, nhưng ta chỉ cần biết toàn bộ kết quả sau khi các thao tác đã hoàn thành. Nếu mỗi lần cập nhật lại chạy vòng lặp qua từng phần tử trong đoạn, tổng thời gian có thể rất lớn. **Mảng hiệu** (difference array) giúp biến mỗi lần cập nhật đoạn thành vài phép cộng ở **hai đầu mút**, sau đó khôi phục kết quả bằng **một lần tính tổng tiền tố**.

Kỹ thuật này còn được gọi là *difference-array technique* hoặc *Imos method* trong những bài toán đếm mức phủ, cộng dồn theo khoảng hay cập nhật hàng loạt. Đây là một ví dụ tiêu biểu cho việc **đổi cách biểu diễn dữ liệu để làm rẻ thao tác chi phối bài toán**.

## 1. Bài toán và lúc nào nên dùng mảng hiệu

Cho mảng số nguyên a có n phần tử, đánh chỉ số từ 0 đến n − 1. Có q thao tác:

**Cộng delta vào tất cả a[i] với l ≤ i ≤ r.**

Mỗi thao tác được mô tả bằng bộ ba (l, r, delta), với điều kiện 0 ≤ l ≤ r < n. delta có thể dương, bằng 0 hoặc âm. Sau khi thực hiện **tất cả** thao tác, cần in ra toàn bộ mảng cuối cùng.

Theo định nghĩa, kết quả tại vị trí i là:

~~~text
result[i] = a[i] + tổng delta của mọi cập nhật (l, r, delta)
                      thỏa l <= i <= r
~~~

### Cách trực tiếp

Với từng cập nhật, chạy một vòng lặp qua toàn bộ các phần tử trong [l, r]. Một cập nhật tốn O(r − l + 1), trường hợp xấu nhất là O(n). Nếu q đoạn đều dài gần n, tổng thời gian có thể lên tới **O(nq)**; bộ nhớ phụ chỉ cần O(1) ngoài mảng đang được sửa.

### Ý tưởng mảng hiệu

Thay vì ghi giá trị mới vào từng phần tử ngay lập tức, ta lưu lại **các thay đổi ở ranh giới**. Mỗi cập nhật đoạn chỉ đòi hỏi O(1) thao tác. Cuối cùng quét từ trái sang phải để tính lại toàn bộ giá trị.

Tổng thời gian là **O(n + q)**, với O(n) bộ nhớ cho mảng hiệu nếu muốn giữ nguyên mảng gốc. Lợi ích rõ nhất khi q lớn, các đoạn dài và **không cần đọc giá trị mới ngay giữa các cập nhật**.

## 2. Mảng hiệu là gì?

Với mảng a = [a[0], a[1], ..., a[n−1]], ta định nghĩa mảng hiệu d:

~~~text
d[0] = a[0]
d[i] = a[i] - a[i-1], với 1 <= i < n
~~~

Nếu n = 0 thì mảng hiệu không có phần tử dữ liệu nào.

Ví dụ:

~~~text
a = [5,  2,  7,  1,  4]
d = [5, -3,  5, -6,  3]
~~~

Ta có thể khôi phục a bằng cách cộng dồn d:

~~~text
a[0] = d[0]
a[1] = d[0] + d[1]
a[2] = d[0] + d[1] + d[2]
...
a[i] = d[0] + d[1] + ... + d[i]
~~~

Lý do: các hiệu liên tiếp triệt tiêu nhau khi cộng:

~~~text
d[0] + ... + d[i]
= a[0] + (a[1]-a[0]) + ... + (a[i]-a[i-1])
= a[i]
~~~

Đây là **tổng rút gọn** (*telescoping sum*). Mảng hiệu và phép tổng tiền tố có quan hệ nghịch đảo trong ngữ cảnh này: mảng hiệu giữ “mức thay đổi từ phần tử trước”, còn tổng tiền tố biến các thay đổi đó thành giá trị tại từng vị trí.

**Lưu ý về phần tử đầu:** d[0] phải chứa a[0], chứ không phải 0, nếu mục tiêu là khôi phục đúng mảng ban đầu. Nếu ban đầu a toàn số 0 thì có thể khởi tạo toàn bộ d bằng 0.

## 3. Vì sao cập nhật một đoạn chỉ cần hai đầu mút?

Xét một thao tác cộng delta vào **mọi phần tử từ l đến r, kể cả hai đầu**.

Trong biểu diễn hiệu, ta chỉ cần:

~~~text
d[l]     += delta
d[r + 1] -= delta   (nếu r + 1 < n)
~~~

Nếu d được cấp n + 1 ô thay vì n, ta có thể luôn ghi d[r + 1] mà không phải kiểm tra trường hợp r = n − 1. Ô cuối d[n] là **ô đệm**, không được dùng để dựng n phần tử kết quả.

Tại sao đúng?

- Trước l, tổng tiền tố chưa gặp thay đổi nào nên giá trị không đổi.
- Từ l đến r, tổng tiền tố đã cộng delta tại d[l] nhưng chưa gặp khoản trừ delta, nên mọi phần tử trong đoạn tăng đúng delta.
- Từ r + 1 trở đi, tổng tiền tố gặp cả +delta lẫn −delta, tổng tác động bằng 0; các phần tử ngoài đoạn không đổi.

Có thể biểu diễn tác động của một cập nhật riêng lẻ như sau:

| Chỉ số i | i < l | l ≤ i ≤ r | i > r |
| --- | ---: | ---: | ---: |
| Tác động lên a[i] | 0 | +delta | 0 |

Vì phép cộng có tính kết hợp và giao hoán, các cập nhật độc lập có thể tích lũy vào cùng mảng hiệu theo bất kỳ thứ tự nào, miễn tất cả đều hợp lệ và không xảy ra tràn số. Sau đó một lần quét tổng tiền tố sẽ tạo ra đúng tổng tác động của tất cả các đoạn.

**Đây là điểm mạnh nhất của kỹ thuật:** chi phí một cập nhật không phụ thuộc độ dài đoạn, kể cả khi đoạn bao phủ hàng triệu phần tử.

## 4. Tính từng bước với một ví dụ hoàn chỉnh

Cho mảng ban đầu:

~~~text
a = [5, 2, 7, 1, 4]
~~~

Thực hiện ba cập nhật theo đoạn đóng:
1. Cộng 3 vào [1, 3].
2. Cộng −2 vào [0, 2].
3. Cộng 4 vào [3, 4].

Nếu cập nhật trực tiếp:

~~~text
Ban đầu         [5, 2, 7, 1, 4]
Sau +3 [1, 3]   [5, 5, 10, 4, 4]
Sau -2 [0, 2]   [3, 3,  8, 4, 4]
Sau +4 [3, 4]   [3, 3,  8, 8, 8]
~~~

Dùng mảng hiệu có **6 ô**, trong đó chỉ 5 ô đầu biểu diễn dữ liệu:

~~~text
d ban đầu            [5, -3, 5, -6, 3,  0]
Sau +3 vào [1, 3]    [5,  0, 5, -6, 0,  0]
Sau -2 vào [0, 2]    [3,  0, 5, -4, 0,  0]
Sau +4 vào [3, 4]    [3,  0, 5,  0, 0, -4]
~~~

Tổng tiền tố của **5 ô đầu**:

~~~text
3
3 + 0       = 3
3 + 0 + 5   = 8
3 + 0 + 5 + 0 = 8
3 + 0 + 5 + 0 + 0 = 8

Kết quả: [3, 3, 8, 8, 8]
~~~

Ô d[5] đã nhận −4 do cập nhật kết thúc ở r = 4, nhưng không thuộc các vị trí a[0] đến a[4]. Đây chỉ là kỹ thuật cấp thêm một ô để thống nhất cách viết thao tác cập nhật, **không phải phần tử thứ sáu của kết quả**.

### Những điều cần quan sát

- Hai cập nhật có thể **chồng lấn** và tổng tác động tự cộng lại.
- delta âm tương đương giảm giá trị các phần tử trong đoạn.
- Cập nhật toàn bộ mảng [0, n − 1] vẫn chỉ ghi ở d[0] và ô đệm d[n].
- Không cần dựng lại a sau mỗi cập nhật; chỉ dựng một lần ở cuối.

## 5. Quy trình triển khai mảng hiệu một chiều

Với mảng ban đầu bất kỳ, độ dài n:

1. Cấp d có n + 1 phần tử, khởi tạo 0.
2. Nếu n > 0, đặt d[0] = a[0]; với i từ 1 đến n − 1, đặt d[i] = a[i] − a[i−1].
3. Với mỗi cập nhật hợp lệ [l, r], delta: thực hiện d[l] += delta và d[r+1] -= delta.
4. Khi tất cả q cập nhật đã xử lý xong, tính running = 0, quét i từ 0 đến n − 1: running += d[i]; result[i] = running.
5. Trả result. Không đưa d[n] vào phép khôi phục.

Có thể viết giả mã:

~~~text
buildDifference(a):
    n = length(a)
    d = array(n + 1, filledWith = 0)
    for i = 0 .. n-1:
        if i == 0:
            d[i] = a[i]
        else:
            d[i] = a[i] - a[i-1]
    return d

rangeAdd(d, l, r, delta):
    d[l]     += delta
    d[r + 1] -= delta

reconstruct(d, n):
    result = array(n)
    running = 0
    for i = 0 .. n-1:
        running += d[i]
        result[i] = running
    return result
~~~

Đoạn giả mã giả sử chỉ nhận các cập nhật có **0 ≤ l ≤ r < n**. Nó không tự xác thực chỉ số.

Nếu ban đầu tất cả phần tử là 0, bỏ qua bước xây dựng hiệu từ a và cấp d toàn 0. Đây là phiên bản rất phổ biến trong bài toán **đếm số lần các đoạn phủ lên một vị trí**, số người hiện diện theo thời điểm hoặc biến động tích lũy.

## 6. Ví dụ Java 17 chạy được: cập nhật đoạn 1D và hình chữ nhật 2D

Chương trình Java hoàn chỉnh sau áp dụng đúng ba cập nhật ở phần 4, sau đó minh họa luôn bản mở rộng sang ma trận 2 chiều. Mọi phần tử và delta dùng kiểu long để có miền giá trị rộng hơn int.

~~~java
import java.util.Arrays;

public class DifferenceArrayDemo {
    static long[] buildDifference(long[] original) {
        int n = original.length;
        long[] diff = new long[n + 1];

        for (int i = 0; i < n; i++) {
            diff[i] = original[i] - (i == 0 ? 0 : original[i - 1]);
        }
        return diff;
    }

    // Đoạn đóng [left, right], đánh chỉ số từ 0.
    static void addRange(
            long[] diff, int n, int left, int right, long delta) {
        if (left < 0 || right < left || right >= n) {
            throw new IllegalArgumentException("Invalid range");
        }
        diff[left] += delta;
        diff[right + 1] -= delta;
    }

    static long[] reconstruct(long[] diff, int n) {
        long[] result = new long[n];
        long running = 0;

        for (int i = 0; i < n; i++) {
            running += diff[i];
            result[i] = running;
        }
        return result;
    }

    // Hình chữ nhật đóng [top, bottom] x [left, right].
    static void addRectangle(
            long[][] diff, int rows, int cols,
            int top, int left, int bottom, int right, long delta) {
        if (top < 0 || top > bottom || bottom >= rows
                || left < 0 || left > right || right >= cols) {
            throw new IllegalArgumentException("Invalid rectangle");
        }

        diff[top][left] += delta;
        diff[bottom + 1][left] -= delta;
        diff[top][right + 1] -= delta;
        diff[bottom + 1][right + 1] += delta;
    }

    static long[][] reconstructGrid(long[][] diff, int rows, int cols) {
        long[][] result = new long[rows][cols];

        for (int row = 0; row < rows; row++) {
            for (int col = 0; col < cols; col++) {
                long up = row > 0 ? result[row - 1][col] : 0;
                long left = col > 0 ? result[row][col - 1] : 0;
                long diagonal = row > 0 && col > 0
                        ? result[row - 1][col - 1] : 0;

                result[row][col] = diff[row][col] + up
                        + left - diagonal;
            }
        }
        return result;
    }

    public static void main(String[] args) {
        long[] original = {5, 2, 7, 1, 4};
        long[] diff = buildDifference(original);

        addRange(diff, original.length, 1, 3, 3);
        addRange(diff, original.length, 0, 2, -2);
        addRange(diff, original.length, 3, 4, 4);

        System.out.println("1D: "
                + Arrays.toString(reconstruct(diff, original.length)));

        int rows = 2;
        int cols = 3;
        long[][] diff2D = new long[rows + 1][cols + 1];

        addRectangle(diff2D, rows, cols, 0, 0, 1, 1, 2);
        addRectangle(diff2D, rows, cols, 1, 1, 1, 2, 3);

        System.out.println("2D:");
        for (long[] row : reconstructGrid(diff2D, rows, cols)) {
            System.out.println(Arrays.toString(row));
        }
    }
}
~~~

Lưu mã thành tệp **DifferenceArrayDemo.java** và chạy bằng JDK 17+:

~~~bash
javac DifferenceArrayDemo.java
java DifferenceArrayDemo
~~~

Đầu ra:

~~~text
1D: [3, 3, 8, 8, 8]
2D:
[2, 2, 0]
[2, 5, 3]
~~~

**Giải thích 2D:** ma trận ban đầu toàn 0, có hai cập nhật hình chữ nhật:
- Cộng 2 vào các ô thuộc hàng 0 đến 1 và cột 0 đến 1.
- Cộng 3 vào các ô thuộc hàng 1 đến 1 và cột 1 đến 2.

Ô (1, 1) nhận cả hai cập nhật nên bằng 5; ô (0, 2) không thuộc cập nhật nào nên bằng 0. Hàm reconstructGrid khôi phục tổng tiền tố 2D, sẽ được giải thích đầy đủ ở phần tiếp theo.

Đoạn mã có chủ ý dùng một ô đệm bên phải trong 1D và thêm một hàng/cột đệm trong 2D; vòng lặp trả kết quả luôn chỉ chạy trên kích thước dữ liệu gốc. Các hàm kiểm tra chỉ số cập nhật, nhưng giả sử bộ nhớ đã cấp đủ theo kích thước n hoặc rows/cols. Phép tính long cũng có thể tràn nếu đầu vào vượt miền long; kiểu long không thay thế việc xác định giới hạn tổng lớn nhất từ đề bài.

## 7. Mở rộng sang mảng hiệu hai chiều

Bài toán 2D: cho ma trận R hàng, C cột, ban đầu toàn 0. Mỗi thao tác cộng delta vào mọi ô thuộc **hình chữ nhật đóng** từ (r1, c1) đến (r2, c2):

~~~text
r1 <= row <= r2
c1 <= col <= c2
~~~

Nếu cập nhật từng ô, một thao tác tốn O((r2−r1+1) × (c2−c1+1)); trong trường hợp xấu nhất, q thao tác tốn O(qRC).

Dùng một ma trận hiệu d kích thước **(R + 1) × (C + 1)**, mỗi cập nhật chỉ sửa bốn góc:

~~~text
d[r1][c1]         += delta
d[r2 + 1][c1]     -= delta
d[r1][c2 + 1]     -= delta
d[r2 + 1][c2 + 1] += delta
~~~

Bốn tác động này là phiên bản 2D của quy tắc “bắt đầu cộng, kết thúc trừ” trong mảng hiệu một chiều. Hai phép trừ loại bỏ ảnh hưởng nằm ngoài ranh giới dưới và phải; phép cộng ở góc dưới-phải bù lại vùng đã bị trừ hai lần.

### Khôi phục bằng tổng tiền tố 2D

Với 0 ≤ row < R, 0 ≤ col < C:

~~~text
result[row][col]
    = d[row][col]
    + result[row - 1][col]          (nếu row > 0)
    + result[row][col - 1]          (nếu col > 0)
    - result[row - 1][col - 1]      (nếu row > 0 và col > 0)
~~~

Các hạng có chỉ số âm được xem là 0. Đây là công thức tổng tiền tố 2D quen thuộc, dùng nguyên lý **bao hàm và loại trừ** (*inclusion–exclusion*). Ta cộng tổng phía trên và phía trái, rồi trừ vùng giao đã bị cộng hai lần.

**Độ phức tạp:** mỗi hình chữ nhật O(1) cập nhật hiệu; khôi phục toàn bộ ma trận O(RC), nên tổng **O(q + RC)**, bộ nhớ **O(RC)**. Nếu bài cho ma trận ban đầu khác 0, phải xây dựng hiệu 2D từ giá trị ban đầu trước khi cộng các cập nhật. Có thể dùng công thức:

~~~text
d[r][c] = a[r][c]
        - (r > 0 ? a[r-1][c] : 0)
        - (c > 0 ? a[r][c-1] : 0)
        + (r > 0 && c > 0 ? a[r-1][c-1] : 0)
~~~

Đây là mã giả công thức, không phải cú pháp hàm Java hoàn chỉnh. Sau khi dựng hiệu 2D như trên, vẫn có thể cập nhật bốn góc và khôi phục bằng tổng tiền tố 2D. Các ô đệm ở hàng R và cột C chỉ giúp ghi các điểm kết thúc mà không cần kiểm tra nhánh; không thuộc ma trận kết quả.

## 8. Phân tích độ phức tạp và lựa chọn công cụ

Giả sử có n phần tử và q cập nhật trên các đoạn đóng.

| Phương án | Một lần cộng đoạn | Lấy giá trị tại một vị trí sau cập nhật | Lấy toàn bộ mảng cuối | Bộ nhớ phụ |
| --- | --- | --- | --- | --- |
| Sửa từng phần tử trực tiếp | O(r − l + 1) | O(1) | O(n) để xuất | O(1) |
| Mảng hiệu, chưa khôi phục | O(1) | O(n) nếu cộng lại từ đầu tại vị trí i | O(n) một lần | O(n) nếu tách mảng d |
| Fenwick tree trên hiệu | O(log n) | O(log n) | O(n log n) nếu hỏi từng vị trí; có thể tối ưu khi truy xuất nội bộ | O(n) |
| Segment tree có lazy propagation | O(log n) | O(log n) | O(n) khi duyệt toàn bộ cây phù hợp | O(n) |

Bảng nêu các chi phí phổ biến; cách dựng/triển khai cụ thể có thể làm một số thao tác thay đổi. Với mảng hiệu, giá trị tại vị trí i = tổng từ d[0] đến d[i]. Nếu sau mỗi lần cập nhật lại cần truy vấn giá trị hiện tại của một vị trí, tính tiền tố lại nhiều lần sẽ mất ưu thế.

### Các kiểu yêu cầu nên phân biệt

**Tất cả cập nhật đến trước, cuối cùng mới cần kết quả:** mảng hiệu lý tưởng, O(n + q).

**Cập nhật đoạn xen kẽ truy vấn giá trị tại một chỉ số:** có thể dùng **Fenwick tree (BIT)** lưu các hiệu; cộng tại l và trừ tại r + 1 bằng hai cập nhật điểm O(log n), truy vấn tổng tiền tố đến i để biết giá trị tại i trong O(log n). Phải khởi tạo đúng giá trị ban đầu.

**Cập nhật đoạn xen kẽ truy vấn tổng đoạn:** một BIT duy nhất lưu hiệu không đủ để truy vấn tổng đoạn O(log n) theo cách trên. Thường dùng hai BIT theo công thức hỗ trợ range-add/range-sum hoặc **segment tree có lazy propagation**, cần bảo đảm công thức và quy ước chỉ số nhất quán.

**Chỉ có truy vấn tổng đoạn, không có cập nhật:** dùng **mảng tổng tiền tố (prefix sum)**. Dựng O(n), mỗi truy vấn tổng đoạn O(1).

**Có q cập nhật hàng loạt rồi thêm t truy vấn tổng đoạn:** dựng kết quả bằng mảng hiệu O(n + q), sau đó dựng prefix sum của kết quả O(n), trả mỗi truy vấn O(1); tổng **O(n + q + t)**, nếu chỉ cần truy vấn sau khi mọi cập nhật kết thúc.

### Mảng hiệu và prefix sum khác nhau thế nào?

- **Difference array:** làm cho **cập nhật đoạn** rẻ, nhưng muốn thấy toàn bộ giá trị thì cần tích lũy.
- **Prefix sum:** làm cho **truy vấn tổng đoạn trên dữ liệu cố định** rẻ, nhưng một cập nhật có thể ảnh hưởng nhiều tổng tiền tố.

Hai cấu trúc liên hệ với nhau về phép toán cộng và tính hiệu, nhưng giải quyết **hai loại thao tác khác nhau**. Không nên nhầm “cộng đoạn” với “tính tổng đoạn”.

## 9. Đoạn đóng, đoạn nửa mở và sai lệch một đơn vị

Có hai quy ước thông dụng, đều hợp lệ nếu dùng thống nhất.

### Đoạn đóng [l, r]

Cập nhật các vị trí l, l + 1, ..., r:

~~~text
d[l]     += delta
d[r + 1] -= delta
~~~

Điều kiện 0 ≤ l ≤ r < n. Khi r = n − 1, r + 1 = n, cần ô đệm nếu muốn ghi không điều kiện.

### Đoạn nửa mở [l, r)

Cập nhật các vị trí l, l + 1, ..., r − 1:

~~~text
d[l] += delta
d[r] -= delta
~~~

Điều kiện 0 ≤ l ≤ r ≤ n. Khi l = r, đoạn rỗng: hai phép cập nhật cùng chỉ số triệt tiêu nhau. Quy ước nửa mở đặc biệt phù hợp với chỉ số mảng Java, thao tác slice và các khoảng thời gian [start, end).

Ví dụ với n = 5, “cộng vào chỉ số 1, 2, 3” có thể viết [1, 3] nếu đoạn đóng hoặc [1, 4) nếu đoạn nửa mở. Nếu lấy công thức nửa mở nhưng dữ liệu đầu vào lại là đoạn đóng, phần tử r bị bỏ sót.

**Thói quen hữu ích:** viết một dòng ở đầu lời giải quy định rõ “đánh chỉ số từ 0; cập nhật đoạn đóng [l, r]” hoặc “đoạn nửa mở [l, r)”, đồng thời thử cập nhật đoạn dài một phần tử và cập nhật chạm cuối mảng.

## 10. Trường hợp biên, lỗi phổ biến và giới hạn

### Những ca cần thử

1. **n = 0, q = 0:** kết quả là mảng rỗng. Không có cập nhật đoạn đóng không rỗng nào hợp lệ nếu n = 0.
2. **n = 1:** chỉ cập nhật hợp lệ [0, 0]; khi dùng ô đệm, trừ delta tại d[1], chỉ xuất một phần tử.
3. **q = 0:** mảng khôi phục phải giống chính xác mảng ban đầu.
4. **delta = 0:** kết quả không thay đổi.
5. **delta âm:** phải giảm đúng các phần tử, không xử lý như số phần tử hay độ dài.
6. **Các đoạn chồng lấn:** tác động được cộng dồn trên phần giao.
7. **Cập nhật cùng đoạn nhiều lần:** tổng tác động bằng tổng các delta.
8. **Cập nhật toàn bộ [0, n − 1]:** đầu trái bằng 0, điểm kết thúc là ô đệm n.
9. **Đoạn đúng một phần tử [i, i]:** chỉ vị trí i thay đổi, các vị trí khác không đổi.
10. **Giá trị lớn và nhiều lần cộng:** tính trước cận trên của tổng có thể đạt tới; long cũng có giới hạn.

### Các lỗi thường gặp

**Quên d[r + 1] -= delta.** Nếu không có phép trừ tại r + 1, tác động kéo dài đến hết mảng thay vì dừng tại r.

**Ghi d[r] -= delta trong khi đầu vào là đoạn đóng.** Phần tử r sẽ không nhận cập nhật.

**Dùng mảng d dài n nhưng không kiểm tra r + 1 < n.** Cập nhật chạm cuối gây truy cập vượt giới hạn. Có thể dùng n + 1 ô đệm để đơn giản hóa.

**Khởi tạo d toàn 0 dù a ban đầu không phải toàn 0.** Phép khôi phục chỉ chứa tổng delta và làm mất mảng gốc; cần xây dựng hiệu từ a hoặc cộng kết quả thay đổi với a khi hoàn nguyên.

**Khôi phục sau mỗi cập nhật rồi lại tiếp tục chỉnh d không nhất quán.** Nên gom tất cả cập nhật vào d và khôi phục một lần. Nếu bắt buộc phải lấy kết quả hiện tại xen kẽ cập nhật, xem xét cấu trúc dữ liệu khác.

**Đọc d[i] và tưởng đó là a[i].** d[i] là *mức thay đổi so với phần tử trước*; giá trị cần xem là tổng tiền tố đến i.

**Tràn số ở phép hiệu hay tổng.** Chẳng hạn a[i] − a[i−1] có thể vượt miền int dù bản thân từng a[i] là int. Hãy xác định ràng buộc tổng quát và chọn long khi thích hợp; nếu yêu cầu vượt giới hạn long thì cần kiểu số hoặc kiểm tra tràn phù hợp.

**Chọn sai công cụ cho truy vấn trực tuyến.** Nếu giữa các lần cập nhật còn phải trả lời hàng chục nghìn truy vấn tổng đoạn, dựng lại toàn bộ mảng cho mỗi truy vấn có thể trở thành O(nq); dùng BIT/segment tree theo đúng loại thao tác.

**Nhầm lẫn hàng và cột trong 2D.** Phải thống nhất cặp tọa độ (row, column), thứ tự top/left/bottom/right, và đúng bốn góc có dấu +, −, −, +.

## 11. Chứng minh tính đúng đắn một cách ngắn gọn

Ta chứng minh thuật toán mảng hiệu một chiều cho cập nhật đoạn đóng.

**Bất biến dựng mảng:** sau khi xây dựng d từ a, tổng d[0] + ... + d[i] bằng a[i] với mọi 0 ≤ i < n, bởi tổng rút gọn.

**Bất biến cập nhật:** với một cập nhật [l, r], delta, hai thay đổi của d làm tổng tiền tố đến vị trí i tăng đúng delta khi l ≤ i ≤ r, và tăng 0 nếu i nằm ngoài đoạn. Điều này đúng cả khi r = n − 1, vì phép trừ được đặt ở ô đệm n nên không ảnh hưởng giá trị hợp lệ nào.

**Nhiều cập nhật:** tác động của các lần chỉnh d cộng tuyến tính. Do đó tổng tiền tố sau q lần cập nhật bằng a[i] cộng tổng delta của **tất cả** cập nhật chứa i, đúng theo đặc tả.

**Kết thúc:** vòng khôi phục chạy qua đúng n vị trí và lấy tổng tiền tố tại mỗi vị trí, nên xuất đúng toàn bộ mảng cuối cùng. Nếu n = 0 thì vòng lặp không chạy và kết quả rỗng, phù hợp đặc tả.

Chứng minh nêu rõ **mỗi thao tác giữ nguyên ngữ nghĩa của dữ liệu**, chứ không dựa vào việc thử thành công vài ví dụ.

## 12. Biến thể sự kiện và miền chỉ số rất lớn

Một bài toán có thể hỏi **bao nhiêu đoạn đang phủ lên từng thời điểm**, với các đoạn thời gian nửa mở [start, end). Nếu thời gian được đánh chỉ số nguyên và miền nhỏ, đặt:
- d[start] += 1
- d[end] -= 1

Tổng tiền tố tại thời điểm t cho biết số đoạn chứa t. Nếu mỗi sự kiện có trọng số w, dùng +w và −w thay cho ±1.

Nếu tọa độ có thể lên tới 10^9, cấp mảng dài 10^9 chỉ để lưu vài nghìn đầu mút là lãng phí. Có thể dùng **sự kiện thưa**: lưu các thay đổi tại start/end trong một map, sắp xếp các tọa độ có sự kiện rồi quét theo thứ tự tăng dần. Trên khoảng giữa hai sự kiện liên tiếp, tổng tích lũy không đổi.

Cần phân biệt:
- Nếu chỉ cần **mức phủ tại các điểm truy vấn**, có thể sắp xếp mốc sự kiện và thực hiện truy vấn theo tọa độ hoặc dùng tìm kiếm nhị phân trên các mốc.
- Nếu cần **tổng số đơn vị thời gian được phủ**, phải nhân mức phủ với **độ dài thực** giữa hai mốc liên tiếp, không được giả sử mỗi mốc nén đại diện cho đúng một đơn vị thời gian.
- Với đoạn đóng trên số nguyên, sự kiện kết thúc đặt tại r + 1; nên dùng kiểu đủ rộng để tránh tràn khi r ở cận lớn nhất, hoặc chuyển sang quy ước mốc phù hợp.

Đó là cùng một ý tưởng “ghi thay đổi tại ranh giới rồi tích lũy” nhưng áp dụng trên miền thưa bằng cấu trúc có thứ tự, không nhất thiết là mảng liên tục.

## 13. Kiểm thử bằng lời giải trực tiếp trên dữ liệu nhỏ

Để kiểm tra cách cài mảng hiệu, hãy tạo một **oracle** đơn giản:

1. Sinh mảng ban đầu nhỏ, ví dụ n từ 0 đến 6, giá trị từ −3 đến 3.
2. Sinh q cập nhật hợp lệ; với n = 0 chỉ cho q = 0.
3. Với bản sao thứ nhất, cập nhật trực tiếp từng phần tử trong [l, r].
4. Với bản sao thứ hai, dựng d và áp dụng hai đầu mút cho mỗi cập nhật, rồi khôi phục một lần.
5. So sánh từng phần tử. Nếu khác, in n, mảng gốc, danh sách cập nhật, đáp án trực tiếp và đáp án từ mảng hiệu.

Những ca nhỏ đáng ưu tiên là:
- Mảng [7], cập nhật [0, 0] cộng −4 → [3].
- Mảng [0, 0, 0], cập nhật [0, 2] cộng 5 → [5, 5, 5].
- Mảng [1, 1, 1, 1], cập nhật [1, 2] cộng 2, sau đó [2, 3] cộng −1 → [1, 3, 2, 0].
- Mảng [2, −2, 2] và q = 0 → kết quả không đổi.
- Mảng rỗng không cập nhật → [].

Kiểm thử đối chiếu là cách hiệu quả để phát hiện sai sót chỉ số, nhưng **không thay thế chứng minh** tính đúng đắn với mọi đầu vào hợp lệ. Khi một ca kiểm thử tìm ra lỗi, giữ lại ca đó để kiểm thử hồi quy sau khi sửa.

## 14. Tự luyện và lời giải định hướng

**Bài 1 — đếm phủ đoạn.** Có n = 6 vị trí ban đầu đều bằng 0. Ba đoạn đóng [0, 2], [1, 4] và [3, 5] mỗi đoạn cộng 1. Hãy cho biết số lần được phủ tại mỗi vị trí.

*Đáp án:* [1, 2, 2, 2, 2, 1]. Tại vị trí 2 có hai đoạn đầu phủ; tại vị trí 3 có hai đoạn sau phủ.

**Bài 2 — cập nhật âm.** Cho a = [4, 4, 4, 4]. Cộng −2 vào [1, 3], sau đó cộng 5 vào [0, 1]. Tìm mảng cuối bằng mảng hiệu.

*Đáp án:* [9, 7, 2, 2]. Từ [4,4,4,4] → [4,2,2,2] → [9,7,2,2].

**Bài 3 — phân biệt hai loại đoạn.** Muốn cộng 3 vào các chỉ số 2, 3, 4 trong mảng dài 7. Hãy viết hai công thức cập nhật tương đương cho đoạn đóng và nửa mở.

*Đáp án:* Đoạn đóng [2, 4] ghi d[2] += 3, d[5] -= 3. Đoạn nửa mở [2, 5) cũng ghi đúng hai thay đổi ấy. Nhãn đoạn khác nhau nhưng tập chỉ số nhận cập nhật giống nhau.

**Bài 4 — chọn cấu trúc.** Có 200.000 phần tử, 200.000 cập nhật đoạn, sau đó in toàn bộ mảng cuối. Có cần segment tree không?

*Đáp án:* Nếu không có truy vấn xen kẽ hoặc yêu cầu khác, mảng hiệu O(n + q) thường đơn giản và đủ tốt. Segment tree có ích hơn khi cần cập nhật và truy vấn trực tuyến.

**Bài 5 — ma trận 2D.** Ma trận 2 × 3 ban đầu 0. Cộng 2 cho hình chữ nhật [0, 0] đến [1, 1], rồi cộng 3 cho [1, 1] đến [1, 2]. Tính giá trị ô (1, 1) và ô (0, 2).

*Đáp án:* (1, 1) = 5 vì được cả hai hình chữ nhật phủ; (0, 2) = 0. Ma trận đầy đủ là [2,2,0] ở hàng đầu và [2,5,3] ở hàng sau.

## Ghi nhớ

- **Mảng hiệu** lưu chênh lệch giữa phần tử hiện tại và phần tử trước; **tổng tiền tố** khôi phục giá trị.
- Cộng delta lên **đoạn đóng [l, r]** chỉ cần d[l] += delta và d[r+1] -= delta.
- Gom **q cập nhật trước, khôi phục một lần** cho tổng thời gian O(n + q).
- Trong 2D, một cập nhật hình chữ nhật dùng **bốn góc** với dấu +, −, −, +; tổng chi phí O(q + RC).
- Mảng hiệu đặc biệt phù hợp với **cập nhật hàng loạt/offline**; nếu cần truy vấn và cập nhật xen kẽ, xem xét Fenwick tree hay segment tree.
- Quy ước chỉ số, đoạn đóng/nửa mở, ô đệm, giá trị gốc và giới hạn số nguyên phải được xác định rõ ngay từ đặc tả.
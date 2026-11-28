# Truy vấn hai chiều và chi phí tăng theo số chiều

Truy vấn đoạn một chiều thường hỏi tổng, số phần tử hoặc giá trị cực trị trên một khoảng. Khi mỗi phần tử có hai tọa độ, miền truy vấn trở thành một hình chữ nhật; với ba tọa độ, nó trở thành một hình hộp. Cách tổ chức dữ liệu phải xử lý đồng thời nhiều trục, và chi phí thường tăng theo số chiều.

Bài này tập trung vào **truy vấn trực giao** (*orthogonal range queries*): các cạnh của miền truy vấn song song với các trục tọa độ. Đây là dạng thường gặp khi tính tổng một vùng ảnh, đếm điểm trong bản đồ, thống kê ô lưới hoặc lọc bản ghi theo hai thuộc tính số.

Sau bài học, người học có thể:

- Biểu diễn truy vấn hình chữ nhật bằng hai khoảng tọa độ và dùng tổng tiền tố hai chiều để trả lời truy vấn tĩnh.
- Chọn Fenwick tree hai chiều, segment tree hai chiều hoặc cấu trúc cho tập điểm thưa khi dữ liệu thay đổi hay không nằm trên lưới đặc.
- Giải thích vì sao bộ nhớ, số phép toán và độ khó triển khai tăng khi số chiều tăng; nhận diện lúc nên nén tọa độ hoặc xử lý truy vấn ngoại tuyến.

## 1. Từ khoảng một chiều đến hình chữ nhật

Với mảng một chiều `A`, truy vấn tổng trên đoạn nửa mở `[l, r)` có thể được tính từ hai tổng tiền tố. Trong hai chiều, ta có ma trận `A` gồm `n` hàng và `m` cột. Một truy vấn hình chữ nhật nửa mở được xác định bởi:

\[
[x_1,x_2)\times[y_1,y_2),
\]

trong đó `x` là chỉ số hàng và `y` là chỉ số cột. Truy vấn tổng cần tính:

\[
\sum_{x=x_1}^{x_2-1}\sum_{y=y_1}^{y_2-1} A[x][y].
\]

Dùng khoảng nửa mở giúp độ dài mỗi trục bằng hiệu hai đầu mút, xử lý vùng rỗng tự nhiên và tránh nhiều trường hợp cộng/trừ `1`. Trong bài này, các ví dụ ma trận dùng chỉ số bắt đầu từ `0` và mọi hình chữ nhật đều có dạng `[x1, x2) × [y1, y2)`.

Không phải bài toán hai chiều nào cũng là ma trận đặc. Có hai mô hình khác nhau:

- **Lưới đặc:** phần lớn hoặc tất cả các ô trong ma trận đều tồn tại, ví dụ ảnh số có kích thước cố định.
- **Tập điểm thưa:** chỉ có `N` điểm `(x, y, w)` với trọng số `w`, trong khi tọa độ có thể rất lớn và phần lớn vị trí không có điểm.

Lưới đặc thường phù hợp với mảng tiền tố hoặc cấu trúc hai chiều có bộ nhớ theo số ô. Tập điểm thưa thường cần nén tọa độ, range tree, kd-tree hoặc thuật toán ngoại tuyến.

## 2. Tổng tiền tố hai chiều cho dữ liệu tĩnh

Định nghĩa `P[x][y]` là tổng của hình chữ nhật bắt đầu tại gốc và kết thúc trước hàng `x`, cột `y`:

\[
P[x][y]=\sum_{0\le i<x}\sum_{0\le j<y} A[i][j].
\]

Ta lưu thêm một hàng số `0` và một cột số `0`, vì vậy `P` có kích thước `(n+1) × (m+1)`. Công thức xây dựng là:

\[
P[x+1][y+1]=A[x][y]+P[x][y+1]+P[x+1][y]-P[x][y].
\]

Hai tổng tiền tố ở phía trên và bên trái bao phủ ô hiện tại hai lần; trừ `P[x][y]` để loại phần giao bị đếm lặp.

Để lấy tổng của hình chữ nhật `[x1,x2) × [y1,y2)`, dùng nguyên lý bao hàm và loại trừ:

\[
\begin{aligned}
S={}&P[x_2][y_2]-P[x_1][y_2]\\
&-P[x_2][y_1]+P[x_1][y_1].
\end{aligned}
\]

```python
class Prefix2D:
    def __init__(self, matrix):
        n = len(matrix)
        m = len(matrix[0]) if n else 0
        self.n, self.m = n, m
        self.p = [[0] * (m + 1) for _ in range(n + 1)]

        for x in range(n):
            row_sum = 0
            for y in range(m):
                row_sum += matrix[x][y]
                self.p[x + 1][y + 1] = self.p[x][y + 1] + row_sum

    def sum(self, x1, y1, x2, y2):
        if not (0 <= x1 <= x2 <= self.n):
            raise ValueError("Invalid row interval")
        if not (0 <= y1 <= y2 <= self.m):
            raise ValueError("Invalid column interval")
        p = self.p
        return (p[x2][y2] - p[x1][y2]
                - p[x2][y1] + p[x1][y1])


matrix = [
    [2, 1, 3],
    [4, 0, 5],
    [1, 2, 6],
]
prefix = Prefix2D(matrix)
print(prefix.sum(0, 1, 2, 3))  # 9
```

Truy vấn trong ví dụ lấy hai hàng đầu và hai cột cuối: `1 + 3 + 0 + 5 = 9`. Việc lưu hàng và cột đệm khiến công thức không cần nhánh riêng khi hình chữ nhật chạm biên trên hoặc biên trái.

| Công việc | Thời gian | Bộ nhớ |
| --- | ---: | ---: |
| Xây bảng tiền tố | \(O(nm)\) | \(O(nm)\) |
| Một truy vấn tổng hình chữ nhật | \(O(1)\) | \(O(1)\) phụ trợ |
| Cập nhật một ô sau khi đã xây bảng | Không hỗ trợ hiệu quả; có thể phải cập nhật \(\Theta(nm)\) ô tiền tố | \(O(nm)\) |

Tổng tiền tố hoạt động với số âm và số dương vì phép cộng có phép nghịch đảo là phép trừ. Không thể áp dụng cùng công thức để lấy `min` hoặc `max`: biết tổng của hai vùng không cho phép khôi phục cực trị của phần giao bằng phép trừ. Với cực trị, cần cấu trúc phù hợp như segment tree hai chiều hoặc sparse table đa chiều cho dữ liệu tĩnh.

## 3. Fenwick tree hai chiều cho cập nhật điểm

Nếu ma trận thay đổi qua các thao tác cộng thêm vào một ô và truy vấn tổng hình chữ nhật, **Fenwick tree hai chiều** (2D BIT) mở rộng ý tưởng Fenwick tree một chiều. Mỗi ô nội bộ lưu tổng của một vùng có kích thước được xác định bởi bit thấp nhất của hai chỉ số.

Với ma trận `n × m`, ta hỗ trợ:

- `add(x, y, delta)`: cộng `delta` vào ô `(x, y)`.
- `prefix(x, y)`: tính tổng trên `[0,x) × [0,y)`.
- `rectangle_sum(x1, y1, x2, y2)`: lấy bốn tổng tiền tố để tính tổng hình chữ nhật.

Mỗi cập nhật hoặc truy vấn tiền tố đi qua \(O(\log n)\) chỉ số theo trục hàng và \(O(\log m)\) chỉ số theo trục cột. Vì hai vòng lặp lồng nhau, chi phí là \(O(\log n\log m)\).

```python
class Fenwick2D:
    def __init__(self, n, m):
        self.n, self.m = n, m
        self.bit = [[0] * (m + 1) for _ in range(n + 1)]

    def add(self, x, y, delta):
        # x, y là tọa độ 0-based của ô cần cập nhật.
        i = x + 1
        while i <= self.n:
            j = y + 1
            while j <= self.m:
                self.bit[i][j] += delta
                j += j & -j
            i += i & -i

    def prefix(self, x, y):
        # Tổng trên [0, x) x [0, y).
        total = 0
        i = x
        while i > 0:
            j = y
            while j > 0:
                total += self.bit[i][j]
                j -= j & -j
            i -= i & -i
        return total

    def rectangle_sum(self, x1, y1, x2, y2):
        return (self.prefix(x2, y2) - self.prefix(x1, y2)
                - self.prefix(x2, y1) + self.prefix(x1, y1))


matrix = [
    [2, 1, 3],
    [4, 0, 5],
    [1, 2, 6],
]
bit = Fenwick2D(3, 3)
for x, row in enumerate(matrix):
    for y, value in enumerate(row):
        bit.add(x, y, value)
print(bit.rectangle_sum(0, 1, 2, 3))  # 9
bit.add(1, 1, 7)  # Ô (1, 1) tăng từ 0 lên 7.
print(bit.rectangle_sum(0, 1, 2, 3))  # 16
```

`add` nhận **độ thay đổi** (`delta`), không nhận giá trị mới. Nếu muốn gán ô từ `old_value` thành `new_value`, phải gọi `add(x, y, new_value - old_value)`. Đây là lỗi dễ gặp khi chuyển từ thao tác gán của mảng sang thao tác cộng của Fenwick tree.

| Thao tác | Độ phức tạp |
| --- | ---: |
| Cập nhật một ô | \(O(\log n\log m)\) |
| Tổng tiền tố | \(O(\log n\log m)\) |
| Tổng hình chữ nhật (bốn tiền tố) | \(O(\log n\log m)\) |
| Bộ nhớ cho lưới đặc | \(O(nm)\) |

Fenwick tree hai chiều phù hợp với tổng hoặc các phép toán có tính chất cộng/trừ tương ứng. Nó không tự giải quyết truy vấn `min`/`max` hình chữ nhật bằng công thức bốn góc. Khi lưới rất lớn nhưng chỉ có ít tọa độ được cập nhật, ma trận `bit` đặc có thể quá tốn bộ nhớ; khi đó cần nén tọa độ hoặc dùng cấu trúc thưa.

## 4. Segment tree hai chiều

Segment tree hai chiều tổ chức các đoạn trên cả hai trục. Một cách xây dựng phổ biến là đặt segment tree theo hàng; mỗi nút của cây hàng quản lý thêm một segment tree theo cột cho vùng hàng mà nó đại diện.

Khi cập nhật một ô, ta đi qua \(O(\log n)\) nút trên cây hàng và cập nhật cấu trúc cột tương ứng trong mỗi nút, mỗi lần tốn \(O(\log m)\). Khi truy vấn hình chữ nhật, đoạn hàng được tách thành \(O(\log n)\) nút chuẩn; mỗi nút trả lời đoạn cột trong \(O(\log m)\). Do đó, với cách cài đặt lưới đặc:

- Cập nhật một ô: \(O(\log n\log m)\).
- Truy vấn hình chữ nhật: \(O(\log n\log m)\).
- Bộ nhớ: thường là \(O(nm)\) với hệ số hằng lớn hơn mảng đầu vào do có nhiều nút cây.

Ưu điểm của segment tree là mỗi nút có thể lưu một giá trị tổng hợp theo phép gộp kết hợp được, chẳng hạn `sum`, `min`, `max` hoặc `gcd`. Phép gộp phải có tính kết hợp để các vùng con có thể ghép thành vùng cha. Một số phép toán có thể cần thông tin bổ sung ở nút; cập nhật trên cả hình chữ nhật (range update) còn đòi hỏi thiết kế lazy propagation hai chiều và phức tạp hơn cập nhật một ô.

Không nên chọn segment tree hai chiều chỉ vì nó hỗ trợ nhiều phép gộp. Hãy cân nhắc số ô, số truy vấn, loại cập nhật và chi phí bộ nhớ; với tổng trên lưới tĩnh, bảng tiền tố đơn giản và tiết kiệm thao tác hơn nhiều.

## 5. Tập điểm thưa: nén tọa độ và range tree

Giả sử có `N` điểm `(x, y, weight)` nằm trong mặt phẳng tọa độ rất lớn. Tạo một ma trận từ giá trị tọa độ lớn nhất có thể cần bộ nhớ khổng lồ dù chỉ có ít điểm. Hai kỹ thuật thường dùng là **nén tọa độ** và **range tree**.

### Nén tọa độ

Với một tập tọa độ đã biết, sắp xếp các giá trị phân biệt trên mỗi trục rồi thay chúng bằng thứ hạng `0, 1, 2, ...`. Ví dụ, các tọa độ hàng `[-1000, 7, 900000]` được ánh xạ thành `[0, 1, 2]`. Thứ tự được bảo toàn, còn khoảng cách số học giữa các tọa độ không được bảo toàn.

Nén tọa độ giúp cấu trúc mảng hoạt động trên số vị trí thực sự xuất hiện. Tuy nhiên, nếu truy vấn có biên không nằm trong danh sách điểm, phải dùng tìm kiếm nhị phân (`lower_bound`) để xác định số tọa độ nhỏ hơn biên. Với bài toán diện tích hoặc thể tích hình học, không được dùng chênh lệch thứ hạng làm độ dài: phải giữ tọa độ gốc hoặc độ rộng của từng khoảng giữa các tọa độ.

### Range tree hai chiều

Range tree là cấu trúc tìm kiếm tĩnh cho tập điểm. Cây chính sắp xếp theo `x`; tại mỗi nút, ta lưu thêm danh sách các điểm thuộc cây con được sắp theo `y`. Với truy vấn hình chữ nhật:

1. Tìm các nút chuẩn của cây `x` bao phủ khoảng `[x1,x2)`. Có tối đa \(O(\log N)\) nút.
2. Trong danh sách `y` của mỗi nút, tìm đoạn `[y1,y2)` bằng tìm kiếm nhị phân.
3. Đếm, cộng trọng số hoặc liệt kê các điểm trong các đoạn tìm được.

Với range tree hai chiều cơ bản, bộ nhớ là \(O(N\log N)\). Truy vấn báo cáo `K` điểm thường có chi phí \(O(\log^2 N + K)\); truy vấn đếm hoặc tổng có thể dùng thêm tổng tiền tố trong các danh sách `y` để không phải liệt kê từng điểm, cho chi phí \(O(\log^2 N)\). Kỹ thuật *fractional cascading* có thể giảm phần tìm kiếm trong trường hợp hai chiều xuống \(O(\log N + K)\), đổi lại cấu trúc và cài đặt phức tạp hơn.

Range tree phù hợp khi tập điểm ít thay đổi và cần nhiều truy vấn hình chữ nhật. Cập nhật động làm các danh sách thứ cấp phải thay đổi theo đường đi trong cây; chi phí và độ phức tạp triển khai cao hơn nhiều so với phiên bản tĩnh.

## 6. Xử lý truy vấn ngoại tuyến bằng sweep line

Nếu toàn bộ điểm và truy vấn đã biết trước, có thể sắp xếp truy vấn theo một trục rồi quét từ trái sang phải. Cách này thường được gọi là **sweep line**. Với truy vấn đếm hoặc tổng trọng số trong hình chữ nhật `[x1,x2) × [y1,y2)`, định nghĩa:

\[
F(x,y)=\sum_{p_x<x,\ p_y<y} w(p).
\]

Khi đó:

\[
\begin{aligned}
Q={}&F(x_2,y_2)-F(x_1,y_2)\\
&-F(x_2,y_1)+F(x_1,y_1).
\end{aligned}
\]

Ta chuyển mỗi truy vấn thành bốn sự kiện có dấu `+1`, `-1`, `-1`, `+1`. Sắp xếp các sự kiện theo hoành độ; trước khi trả lời sự kiện tại `x`, thêm vào Fenwick tree một chiều tất cả điểm có `p_x < x`. Fenwick tree theo trục `y` trả lời tổng của các điểm có `p_y < y`.

Với `N` điểm và `Q` truy vấn, sau khi sắp xếp điểm, tọa độ `y` và `4Q` sự kiện, tổng chi phí là \(O((N+Q)\log(N+Q))\), bộ nhớ \(O(N+Q)\). Cách này hữu ích cho truy vấn đếm/tổng trên tập điểm tĩnh, nhưng không trả lời trực tuyến khi truy vấn mới xuất hiện sau mỗi bước.

Điều kiện so sánh biên rất quan trọng: vì miền dùng khoảng nửa mở, chỉ thêm điểm khi `p_x < x` và truy vấn Fenwick cho `p_y < y`. Nếu dùng dấu `<=` ở một nơi nhưng vẫn giữ công thức nửa mở, các điểm nằm đúng trên biên có thể bị đếm sai.

## 7. Vì sao số chiều làm chi phí tăng?

Trong hai chiều, bao hàm và loại trừ cần bốn góc của hình chữ nhật. Với `d` chiều, mỗi tọa độ có hai lựa chọn: biên dưới hoặc biên trên. Do đó, tổng trên một hộp trực giao cần kết hợp \(2^d\) tổng tiền tố:

\[
\operatorname{sum}(B)=
\sum_{\epsilon\in\{0,1\}^d}
(-1)^{d-\|\epsilon\|_1}P(c_\epsilon),
\]

trong đó mỗi tọa độ của `c` lấy biên dưới hoặc biên trên tương ứng với bit trong `\epsilon`. Số hạng tăng theo cấp số nhân: 2 chiều cần 4, 3 chiều cần 8, 10 chiều cần 1024 tổng tiền tố.

Chi phí còn tăng ở phần lưu trữ và cập nhật:

| Kỹ thuật | Hai chiều | `d` chiều (mỗi trục có khoảng `n` vị trí) |
| --- | --- | --- |
| Lưới đặc / bảng tiền tố | Bộ nhớ \(O(n^2)\), truy vấn tổng \(O(1)\) | Bộ nhớ \(O(n^d)\), truy vấn tổng \(O(2^d)\) sau tiền xử lý |
| Fenwick tree đa chiều | Cập nhật/truy vấn \(O(\log^2 n)\), bộ nhớ \(O(n^2)\) | Cập nhật/truy vấn \(O(\log^d n)\), bộ nhớ \(O(n^d)\) |
| Range tree tĩnh | Bộ nhớ \(O(N\log N)\), truy vấn báo cáo \(O(\log^2 N+K)\) | Bộ nhớ \(O(N\log^{d-1}N)\), truy vấn \(O(\log^d N+K)\) trong mô hình range tree chuẩn |

Các biểu thức này cho thấy hai dạng tăng trưởng khác nhau. Cấu trúc trên lưới đặc chịu chi phí theo **tích kích thước các trục**; range tree tránh cấp phát mọi ô nhưng số danh sách thứ cấp tăng theo lũy thừa của logarit số điểm. Khi số chiều lớn, ngay cả cấu trúc thưa cũng có thể tốn nhiều bộ nhớ và khó cập nhật.

Một lựa chọn khác là **kd-tree**, phân hoạch điểm luân phiên theo các trục và lưu hộp bao của mỗi cây con. Khi hộp truy vấn không giao hộp bao, bỏ qua toàn bộ cây con; khi hộp bao nằm hoàn toàn trong truy vấn, có thể lấy kết quả tổng hợp đã lưu. Với kd-tree cân bằng trong mô hình hình học chuẩn, một chặn thường dùng cho truy vấn trực giao trong `d` chiều là khoảng \(O(N^{1-1/d}+K)\); đây không phải bảo đảm hiệu năng cho mọi cách phân hoạch và mọi phân bố dữ liệu. Trong trường hợp xấu, cấu trúc vẫn có thể phải thăm phần lớn điểm. Khi `d` tăng, số mũ `1-1/d` tiến gần `1`, nên lợi ích cắt tỉa suy giảm.

Đây là một biểu hiện của **lời nguyền số chiều** (*curse of dimensionality*): không có một cấu trúc đơn giản nào giữ chi phí thấp đồng đều cho mọi dữ liệu và mọi số chiều. Cần tận dụng đặc điểm bài toán, giảm số chiều không cần thiết, dùng chỉ mục theo nhóm thuộc tính hoặc chấp nhận xử lý gần đúng nếu yêu cầu cho phép.

## 8. Chọn cấu trúc theo kiểu dữ liệu và thao tác

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Ma trận cố định, nhiều truy vấn tổng | Tổng tiền tố 2D | Xây \(O(nm)\), mỗi truy vấn \(O(1)\) |
| Lưới đặc, cập nhật cộng tại ô và truy vấn tổng | Fenwick tree 2D | Cập nhật và truy vấn \(O(\log n\log m)\) |
| Lưới đặc, cần `min`/`max` hoặc phép gộp kết hợp khác | Segment tree 2D | Hỗ trợ phép gộp tổng quát hơn |
| Tập điểm thưa, tĩnh, cần báo cáo điểm trong hình chữ nhật | Range tree hoặc kd-tree | Không cấp phát theo toàn bộ miền tọa độ |
| Tập điểm tĩnh, mọi truy vấn có sẵn và chỉ cần đếm/tổng | Sweep line + Fenwick 1D | Đưa bài toán hai chiều về các truy vấn tiền tố một chiều |
| Tọa độ lớn nhưng số giá trị xuất hiện ít và biết trước | Nén tọa độ + cấu trúc mảng | Giảm miền chỉ số xuống số tọa độ phân biệt |

Trước khi chọn, hãy xác định rõ bốn điều: dữ liệu là lưới hay tập điểm; truy vấn cần tổng/đếm/cực trị hay liệt kê; cập nhật là điểm hay cả vùng; truy vấn có cần trả lời ngay khi đến hay có thể xử lý ngoại tuyến. Chỉ sau đó mới so sánh thời gian và bộ nhớ.

## 9. Lỗi biên và cách kiểm chứng

Các lỗi phổ biến trong truy vấn hai chiều thường xuất phát từ quy ước tọa độ hoặc giả định về phép gộp:

- **Trộn khoảng đóng và nửa mở:** dùng `[x1,x2]` trong một hàm và `[x1,x2)` trong hàm khác sẽ làm mất hoặc đếm lặp hàng/cột cuối. Ghi rõ quy ước ở chữ ký hàm.
- **Sai dấu ở bao hàm và loại trừ:** tổng hình chữ nhật phải cộng góc dưới bên trái sau khi trừ hai vùng tiền tố lớn hơn.
- **Nhầm cập nhật gán với cập nhật cộng:** Fenwick tree nhận `delta`; phải trừ giá trị cũ khỏi giá trị mới.
- **Bỏ qua tọa độ trùng:** nhiều điểm cùng `(x,y)` cần được cộng trọng số hoặc giữ thành nhiều phần tử theo đúng ngữ nghĩa bài toán.
- **Dùng thứ hạng nén làm khoảng cách:** nén bảo toàn thứ tự, không bảo toàn độ dài hình học.
- **Dùng phép trừ cho `min`/`max`:** tổng tiền tố có thể đảo bằng phép trừ, còn cực trị không có phép nghịch đảo tương ứng.
- **Đánh giá thấp bộ nhớ:** ma trận `n × m` cần `nm` ô; tăng số chiều có thể khiến cấp phát lưới đặc không còn khả thi.

Một bộ kiểm thử tốt nên có ma trận nhỏ để tính đáp án bằng vòng lặp trực tiếp rồi so sánh với cấu trúc tối ưu. Bao gồm hình chữ nhật rỗng, một ô, toàn ma trận, chạm từng biên, giá trị âm, tọa độ trùng và cập nhật liên tiếp. Với Fenwick tree, sau mỗi cập nhật hãy đối chiếu truy vấn với ma trận gốc. Với nén tọa độ, thử biên nằm giữa hai tọa độ đã xuất hiện và biên trùng đúng tọa độ điểm.

## 10. Bài tập tự kiểm tra

1. Một ma trận `1000 × 800` không thay đổi và có hàng triệu truy vấn tổng hình chữ nhật. Vì sao bảng tiền tố phù hợp hơn Fenwick tree hai chiều?
2. Với `P[x][y]` định nghĩa trên `[0,x) × [0,y)`, hãy viết công thức tổng của vùng `[2,5) × [1,4)`.
3. Một ô hiện có giá trị `12`, cần đổi thành `5` trong Fenwick tree hai chiều. Giá trị truyền vào `add` là bao nhiêu?
4. Có `N` điểm thưa và `Q` truy vấn hình chữ nhật đều biết trước. Khi nào sweep line có lợi thế so với range tree trực tuyến?
5. Tại sao nén tọa độ không được dùng trực tiếp để tính diện tích giữa hai tọa độ gốc?
6. Một bảng tiền tố 10 chiều cần bao nhiêu hạng trong công thức bao hàm và loại trừ? Điều đó gợi ý gì khi chọn cấu trúc?

**Gợi ý đáp án:** (1) Cả hai đều cần bộ nhớ theo lưới, nhưng bảng tiền tố chỉ xây một lần `O(nm)` và trả lời mỗi truy vấn trong `O(1)`; Fenwick tree tốn `O(log n log m)` cho mỗi truy vấn mà không có cập nhật để bù lại. (2) `P[5][4] - P[2][4] - P[5][1] + P[2][1]`. (3) `-7`, vì thao tác nhận độ thay đổi. (4) Khi mọi truy vấn đã có sẵn và chỉ cần đếm/tổng; sắp xếp sự kiện giúp xử lý toàn bộ trong `O((N+Q) log(N+Q))`. (5) Thứ hạng chỉ bảo toàn thứ tự, không bảo toàn khoảng cách số học; phải dùng tọa độ gốc hoặc độ rộng khoảng. (6) `2^10 = 1024` hạng; số chiều cao khiến chi phí tăng nhanh, nên cần giảm chiều hoặc dùng chỉ mục phù hợp thay vì mở rộng bảng đặc.

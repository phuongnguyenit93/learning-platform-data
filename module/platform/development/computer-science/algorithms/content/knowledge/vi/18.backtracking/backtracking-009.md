# Điền bảng theo ràng buộc và bài toán Sudoku

**Điền bảng theo ràng buộc** là một lớp bài toán mà mỗi ô, vị trí hoặc biến phải nhận một giá trị sao cho **mọi điều kiện** đều đúng. Với bảng nhỏ và tập lựa chọn hữu hạn, **quay lui (backtracking)** là hướng giải tự nhiên: chọn một ô chưa điền, thử giá trị hợp lệ, đi sâu vào trạng thái mới, và nếu không thể hoàn thành thì **hoàn tác** để thử khả năng khác.

**Sudoku chuẩn 9×9** là ví dụ điển hình. Điền các chữ số 1–9 vào ô trống, sao cho **mỗi hàng, mỗi cột và mỗi hộp 3×3** chứa từng chữ số đúng một lần; mọi số gợi ý có sẵn phải giữ nguyên. Một chương trình đúng còn phải phân biệt **đề sai ngay từ đầu**, **đề không có nghiệm**, **đề có đúng một nghiệm** và **đề có nhiều nghiệm**.

Bài học thuộc nhóm **Quay lui**. Nội dung đi từ mô hình CSP (*Constraint Satisfaction Problem*), kiểm tra ràng buộc, quay lui cơ bản, bitmask hàng/cột/hộp, heuristic **MRV – Minimum Remaining Values**, kiểm tra tính duy nhất bằng đếm có giới hạn, đến chương trình Java 17+ chạy độc lập và kiểm thử với một solver tham chiếu không dùng bitmask.

## 1. Mô hình bảng Sudoku chuẩn

Bảng có **81 ô**, được đánh chỉ số hàng `r=0..8` và cột `c=0..8`. Có 9 hộp 3×3, mỗi hộp là một vùng liên tiếp gồm ba hàng và ba cột.

Các luật:

1. Mỗi ô được điền phải chứa một chữ số từ `1` đến `9`.
2. Trong một **hàng**, không được có hai ô chứa cùng chữ số.
3. Trong một **cột**, không được có hai ô chứa cùng chữ số.
4. Trong một **hộp 3×3**, không được có hai ô chứa cùng chữ số.
5. Các chữ số gợi ý (*givens/clues*) là **cố định**, không được thay thế nhằm tạo ra nghiệm.

Ở bảng **chưa hoàn thành**, điều kiện là các số đã điền **không xung đột**. Khi bảng **đã hoàn thành**, do có 9 ô và chỉ có 9 giá trị cho phép, điều kiện không trùng tương đương với **mỗi số từ 1 đến 9 xuất hiện đúng một lần**.

Ví dụ câu đố:

```text
5 3 . | . 7 . | . . .
6 . . | 1 9 5 | . . .
. 9 8 | . . . | . 6 .
------+-------+------
8 . . | . 6 . | . . 3
4 . . | 8 . 3 | . . 1
7 . . | . 2 . | . . 6
------+-------+------
. 6 . | . . . | 2 8 .
. . . | 4 1 9 | . . 5
. . . | . 8 . | . 7 9
```

Một nghiệm:

```text
534678912
672195348
198342567
859761423
426853791
713924856
961537284
287419635
345286179
```

Trong mã Java, một câu đố được biểu diễn bằng `String[9]`, mỗi chuỗi đúng **9 ký tự**, chấp nhận `'.'` hoặc `'0'` để chỉ ô trống. Chữ số **0 không phải giá trị Sudoku**; nó chỉ là một cách ký hiệu ô chưa điền.

**Định nghĩa nghiệm:** một bảng đầy đủ hợp lệ, trùng mọi chữ số gợi ý ở đúng vị trí ban đầu.

## 2. Sudoku là bài toán thỏa mãn ràng buộc (CSP)

Mô hình CSP gồm:

| Thành phần | Trong Sudoku |
| --- | --- |
| **Biến** | Mỗi ô `X[r][c]` |
| **Miền giá trị** | Các chữ số `{1,2,...,9}`, có thể bị thu hẹp khi ô khác được điền |
| **Ràng buộc** | Các ô cùng hàng, cột hoặc hộp phải nhận những số khác nhau |
| **Dữ liệu cố định** | Các ô gợi ý được cho sẵn |
| **Mục tiêu** | Tìm một bảng hoàn chỉnh hoặc xác định số nghiệm theo yêu cầu |

Với `r,c∈{0,...,8}`:

```text
X[r][c] ∈ {1,2,...,9}

allDifferent(X[r][0], ..., X[r][8])          // từng hàng
allDifferent(X[0][c], ..., X[8][c])          // từng cột

allDifferent(X[3*br+dr][3*bc+dc])
với dr,dc∈{0,1,2}, br,bc∈{0,1,2}         // từng hộp 3×3
```

Những bài **Latin square**, **N-Queens**, tô màu đồ thị, xếp lịch/phân công, điền chữ vào ô chữ đều có cấu trúc tương tự: biến, miền giá trị và ràng buộc. **Tuy nhiên mỗi bài có hàm kiểm tra hợp lệ riêng**; không thể bê nguyên mask Sudoku sang một bảng có luật khác.

### Hợp lệ cục bộ không đồng nghĩa giải được

Một bảng không có chữ số trùng trong hàng/cột/hộp **vẫn có thể vô nghiệm**. Có thể tồn tại ô trống không còn chữ số hợp lệ, hoặc một sự kết hợp ràng buộc chỉ gây mâu thuẫn sau vài bước chọn.

Cần phân biệt:

- **Đầu vào sai định dạng:** số hàng/cột khác 9, ký tự bất hợp lệ;
- **Gợi ý mâu thuẫn:** hai chữ số giống nhau trong cùng hàng/cột/hộp;
- **Đầu vào hợp lệ cục bộ nhưng vô nghiệm:** không có gợi ý xung đột, nhưng không có cách hoàn thành;
- **Có nghiệm:** tồn tại ít nhất một cách hoàn thành;
- **Nghiệm duy nhất:** tồn tại đúng một bảng hoàn thành hợp lệ.

Chương trình ví dụ **ném `IllegalArgumentException`** cho hai trường hợp đầu, nhưng **trả kết quả 0 nghiệm** cho trường hợp thứ ba.

## 3. Quay lui cơ bản: đặt, thử, đi sâu và hoàn tác

Một cách triển khai dễ hiểu:

```text
search(board):
    (r,c) = ô trống đầu tiên theo thứ tự hàng/cột

    nếu không còn ô trống:
        ghi nhận một nghiệm
        return

    for digit = 1..9:
        nếu digit không nằm trong hàng r, cột c, hộp của (r,c):
            đặt digit vào (r,c)
            search(board)
            xóa digit vừa đặt khỏi (r,c)     // rollback/undo
```

Ví dụ một ô có miền `{2,7}`. Nếu đặt 2 rồi sau đó gặp ô không thể điền, ta **không kết luận đề vô nghiệm ngay**: phải quay lại thử 7. Chỉ khi mọi nhánh thử tại ô đều thất bại mới có thể kết luận **trạng thái cha** không dẫn đến nghiệm.

**Bất biến:** Trước và sau mỗi lần thử một digit tại ô đang trống, trạng thái của bảng và mọi cấu trúc hỗ trợ phải **giống hệt** khi quay lui trở về. Nếu bỏ quên bước hoàn tác, một chữ số của nhánh thất bại sẽ “rò rỉ” sang nhánh kế tiếp, làm kết quả sai.

### Đếm nghiệm khác tìm nghiệm đầu tiên

Nếu chỉ cần tìm một nghiệm, có thể dừng ngay sau khi thấy bảng hoàn chỉnh. Nhưng khi yêu cầu **đề có duy nhất một nghiệm**, phải kiểm tra xem còn nghiệm khác hay không.

Một giải pháp hiệu quả là **đếm tối đa hai nghiệm**:

```text
maxSolutions = 2

0: không có nghiệm
1: đúng một nghiệm, vì DFS đã duyệt xong mà không thấy nghiệm thứ hai
2: ít nhất hai nghiệm, có thể dừng ngay
```

Giá trị 2 khi dừng sớm **không có nghĩa chính xác hai nghiệm**. Trong báo cáo người dùng nên ghi **2+**.

Nếu chỉ dừng ở nghiệm đầu tiên, việc tìm được một nghiệm chứng minh **tồn tại**, không chứng minh **duy nhất**.

## 4. Kiểm tra hợp lệ: hàng, cột, hộp

Muốn đặt chữ số `d` vào ô trống `(r,c)`, kiểm tra rằng không có `d` trong:

- Hàng `r`;
- Cột `c`;
- Hộp 3×3 chứa ô đó.

Với chỉ số 0-based, hộp là:

```text
boxIndex(r,c) = (r/3)*3 + (c/3)
```

Vì `r,c` thuộc 0..8 nên các phép chia nguyên cho 3 nhận giá trị 0,1,2; kết quả hộp thuộc `0..8`.

Ví dụ:

| Ô `(r,c)` | Hộp |
| --- | ---: |
| `(0,0)` | 0 |
| `(1,7)` | 2 |
| `(4,5)` | 4 |
| `(8,8)` | 8 |

Một hàm kiểm tra đơn giản quét 9 ô hàng, 9 ô cột và 9 ô hộp. Đó là phương pháp đáng tin để làm **oracle độc lập** trong kiểm thử.

### Không được bỏ qua kiểm tra gợi ý ban đầu

Hai số 5 trong cùng một hàng gợi ý đã khiến đề sai ngay cả khi chưa thử gì. Nếu bộ giải chỉ kiểm tra những số nó **tự đặt**, bảng đã điền kín nhưng sai có thể bị coi là nghiệm.

Khi đọc gợi ý, kiểm tra xung đột **ngay tại thời điểm ghi mỗi digit**. Cũng cần kiểm tra định dạng đủ 9 hàng và 9 ký tự/hàng. Không thay đổi số gợi ý để làm một bảng sai trở thành giải được.

## 5. Bitmask cho các chữ số đã xuất hiện

Có 9 chữ số nên mỗi tập chữ số có thể chứa trong một `int`. Quy ước **bit thứ `d` đại diện chữ số `d`**, với `d∈{1,...,9}`. Bit 0 bỏ trống.

```text
bit(d) = 1 << d

bit(1) = 2
bit(2) = 4
bit(9) = 512

FULL = 0b11_1111_1110 = 1022
     = (1 << 10) - 2
```

Duy trì:

```java
int[] rowMask = new int[9];
int[] colMask = new int[9];
int[] boxMask = new int[9];
```

Với mỗi chữ số `d` đã xuất hiện trong hàng `r`, bit `d` của `rowMask[r]` là 1. Tương tự cho cột và hộp. Một ô `(r,c)` có các chữ số bị cấm:

```java
int used = rowMask[r] | colMask[c] | boxMask[boxIndex(r, c)];
int allowed = FULL & ~used;
int count = Integer.bitCount(allowed);
```

Vì toán tử `~` lật **mọi bit trong `int`**, phép AND với `FULL` là bắt buộc để loại các bit ngoài miền chữ số 1..9.

Ví dụ nếu hàng đã có `{1,3,5}`, cột có `{2,7}` và hộp có `{4,8}`, hợp những số cấm là `{1,2,3,4,5,7,8}`. Ô đang xét chỉ còn **`{6,9}`**.

### Duyệt các bit ứng viên, không phải luôn thử 1..9

```java
for (int rest = allowed; rest != 0; rest &= rest - 1) {
    int bit = rest & -rest;
    int digit = Integer.numberOfTrailingZeros(bit);
    // Duyệt digit hợp lệ, tăng dần từ 1 đến 9.
}
```

- `rest & -rest` lấy bit 1 thấp nhất;
- `rest & (rest-1)` xóa bit 1 thấp nhất;
- `Integer.numberOfTrailingZeros(bit)` trả chính số `d` nhờ quy ước bit thứ `d`.

Không gọi `numberOfTrailingZeros(0)` rồi dùng kết quả như một chữ số Sudoku. Vòng lặp yêu cầu `rest!=0`.

### Đặt và rollback đồng bộ

```text
board[r][c] = digit
rowMask[r] |= bit
colMask[c] |= bit
boxMask[b] |= bit

đệ quy...

board[r][c] = 0
rowMask[r] &= ~bit
colMask[c] &= ~bit
boxMask[b] &= ~bit
```

Hoàn tác bằng `& ~bit` an toàn vì ta chỉ được đặt một chữ số **chưa có** trong các đơn vị đó. Dùng XOR khi không biết chắc bit đã có có thể khiến bit từ 0 bị **bật lên** ngoài ý muốn.

## 6. MRV: ưu tiên ô có ít ứng viên nhất

**Minimum Remaining Values (MRV)** là heuristic chọn biến của CSP: trong tất cả ô trống, chọn ô có **ít giá trị hợp lệ nhất** ở trạng thái hiện tại.

Ví dụ:

```text
Ô A: {1,3,6,9}   -> 4 ứng viên
Ô B: {2}         -> 1 ứng viên
Ô C: {4,5}       -> 2 ứng viên

Chọn B trước: chỉ có một nhánh cần thử.
```

Nếu một ô trống có **0 ứng viên**, state hiện tại **không thể** mở rộng thành nghiệm, dù các ô khác còn nhiều khả năng. Trở lại ngay, không cần đợi điền hết bảng mới phát hiện mâu thuẫn.

Nếu nhiều ô trống cùng có số ứng viên ít nhất, có thể chọn ô xuất hiện trước theo thứ tự **hàng tăng, cột tăng**. Điều đó khiến thứ tự tìm kiếm ổn định và dễ kiểm thử.

MRV **không đổi tập nghiệm**, chỉ giảm số nhánh thường phải mở. Nó không phải toàn bộ kỹ thuật suy luận Sudoku: solver đơn giản này chưa có hidden singles, naked pairs, X-Wing hoặc arc consistency đầy đủ.

**Chi phí chọn ô:** Ở mỗi lời gọi DFS, bản đơn giản quét tối đa 81 ô và tính `Integer.bitCount`. Điều này có overhead so với chọn ô đầu tiên, nhưng nhiều bảng khó được lợi vì phát hiện ngõ cụt sớm. Không khẳng định MRV luôn nhanh hơn trên mọi input; nên đo cả số nút và thời gian thực tế.

## 7. Hoàn tác khi đếm nhiều nghiệm và lưu nghiệm đầu tiên

Khi bộ giải cần kiểm tra tính duy nhất, DFS sẽ tiếp tục chạy sau nghiệm đầu tiên. Nếu lưu **tham chiếu** đến bảng làm việc, các lệnh hoàn tác sẽ sửa mất nghiệm vừa thấy.

Giải pháp:

1. Khi bảng không còn ô trống, tăng `found`.
2. Nếu `found==1`, tạo **bản chụp** hoàn chỉnh của 9 hàng.
3. Trở về nhánh cha và **hoàn tác** bước vừa thử.
4. Nếu `found` đã đạt `maxSolutions`, dừng thử các nhánh tiếp theo.

Mẫu logic an toàn:

```text
đặt lựa chọn
DFS()
hoàn tác lựa chọn

nếu found >= maxSolutions:
    break
```

Chú ý **hoàn tác xảy ra trước khi break**. Nếu đảo thứ tự và thoát thẳng, state của board hoặc mask có thể bị bẩn. Chương trình ở mục 10 làm đúng thứ tự này.

API trả một cấu trúc kết quả:

```text
Result(
    foundUpToLimit,   // 0,1,2 nếu limit=2
    first,            // snapshot nghiệm đầu tiên; rỗng nếu vô nghiệm
    nodes             // số lần đi vào DFS
)
```

Số lần đi vào DFS là một thước đo khối lượng tìm kiếm, **không phải số nghiệm** và không phải số phép toán CPU chính xác.

## 8. Phân loại bốn tình huống quan trọng

### Đề unique

Câu đố ở mục 1 có nghiệm duy nhất như bảng 9 hàng đã minh họa. Với giới hạn đếm `2`, bộ giải trả `1` **sau khi xét các nhánh cần thiết để loại khả năng nghiệm khác**.

### Bảng đã điền kín

Một bảng đầy đủ hợp lệ có đúng một cách hoàn thành: chính bảng đó. Solver cần xử lý ngay base case **không còn ô trống**. Ngược lại, bảng đầy đủ nhưng **sai gợi ý** phải bị từ chối khi xây state, không được nhận là nghiệm chỉ vì không có dấu `.`.

### Đề sai ngay từ gợi ý

Thay hai ký tự đầu hàng đầu của một bảng hoàn chỉnh bằng hai số 5:

```text
554678912
672195348
...
```

Có hai chữ số 5 cùng hàng, constructor phải báo `IllegalArgumentException`. Không “sửa đại” một ô gợi ý rồi mới giải.

### Đề hợp lệ cục bộ nhưng vô nghiệm

Từ bảng hoàn chỉnh ở mục 1, đổi `(0,0)` từ 5 thành 1; xóa `(0,7)` (trước đó là 1) và `(2,0)` (trước đó là 1):

```text
1346789.2
672195348
.98342567
859761423
426853791
713924856
961537284
287419635
345286179
```

Các gợi ý còn lại **không trùng** trong từng hàng/cột/hộp. Tuy nhiên hàng 2 chỉ thiếu chữ số 1, và ô trống duy nhất là `(2,0)`; cột 0 đã có số 1 ở `(0,0)`. Vậy ô `(2,0)` **không có ứng viên**, toàn bảng **0 nghiệm**.

### Đề có nhiều nghiệm

Lấy bảng hoàn chỉnh, **xóa toàn bộ số 1 và 2**, giữ tất cả các số 3..9. Có ít nhất hai cách hoàn thành: bảng ban đầu và bảng hoán đổi toàn bộ chữ số 1↔2.

Phép hoán đổi toàn cục bảo toàn mỗi hàng/cột/hộp vì mọi chữ số vẫn xuất hiện đúng một lần; gợi ý từ 3 đến 9 không thay đổi. Đó là **chứng minh độc lập rằng đề không duy nhất**, không phải suy đoán từ thời gian chạy. Bộ giải với `limit=2` báo **2+**.

## 9. Chứng minh tính đúng bằng bất biến

**Bất biến trạng thái:** Mọi gợi ý ban đầu hợp lệ; trong một nhánh DFS, `board` và ba mảng mask luôn mô tả **cùng các số đã đặt**, không có chữ số trùng trong hàng/cột/hộp.

**Cơ sở:** Constructor đọc từng gợi ý và từ chối nếu số đó đã nằm trong bất kỳ đơn vị nào liên quan. Vì vậy bất biến đúng trước lần gọi DFS đầu tiên.

**Bước quy nạp:** Chữ số được thử chỉ lấy từ mask ứng viên `FULL & ~(row|col|box)`, nên không trùng các số đang có. Đặt digit và bật đúng ba bit giữ nguyên bất biến. Sau khi DFS con kết thúc, xóa digit và tắt đúng ba bit mới bật khiến state trở về như trước.

**Tính đúng của một nghiệm:** DFS chỉ ghi nhận nghiệm khi không còn ô trống. Bởi bất biến, bảng 81 số không trùng ở mỗi hàng/cột/hộp; mỗi đơn vị gồm 9 số trong 1..9, nên phải có đủ 1..9. Gợi ý không được ghi đè vì chỉ ô có giá trị 0 được chọn.

**Tính đầy đủ khi không dừng giới hạn:** Với bất kỳ nghiệm đích `T` mở rộng trạng thái hiện tại, chữ số `T[r][c]` tại ô MRV được chọn chắc chắn thuộc tập ứng viên; vòng lặp sẽ thử nó. Lặp suy luận với số ô trống giảm cho thấy tồn tại một nhánh dẫn đến `T`. Mỗi nghiệm được tìm theo đúng một chuỗi lựa chọn của thuật toán chọn ô, nên không có việc đếm cùng một bảng hai lần vì thay đổi thứ tự gán.

**Tính kết thúc:** Mỗi bước đi sâu điền đúng một ô trống; có tối đa `E≤81` mức đệ quy thêm. Mỗi ô có tối đa 9 chữ số để thử. Các nhánh không có ứng viên bị cắt; cây tìm kiếm hữu hạn.

Khi đặt giới hạn 2, tính đầy đủ **chỉ được dùng tới lúc tìm nghiệm thứ hai**. Kết luận “ít nhất hai nghiệm” vẫn đúng, nhưng không thể suy ra tổng số nghiệm chính xác nếu đã dừng sớm.

## 10. Java 17+ — bộ giải và kiểm thử độc lập

Chương trình đầy đủ **SudokuBacktrackingDemo.java** bao gồm:

- Đọc 9 chuỗi, kiểm tra định dạng và xung đột gợi ý;
- DFS với **MRV và bitmask**, giữ một snapshot bất biến của nghiệm đầu tiên;
- Đếm tối đa `maxSolutions` nghiệm, hoàn tác cả khi dừng sớm;
- Một **oracle** sử dụng cách chọn ô trống đầu tiên và kiểm tra hàng/cột/hộp bằng vòng quét, **không dùng bitmask/MRV**;
- Đối chiếu **243 câu đố gần hoàn chỉnh** với oracle, xác minh nghiệm giữ nguyên toàn bộ gợi ý;
- Demo các trường hợp **unique, complete, ambiguous, locally legal but impossible, invalid givens**.

### Mã nguồn: SudokuBacktrackingDemo.java

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class SudokuBacktrackingDemo {
    private static final int FULL = 0b11_1111_1110;

    record Result(int foundUpToLimit, List<String> first, long nodes) {}

    static int boxIndex(int row, int col) {
        return (row / 3) * 3 + col / 3;
    }

    static final class Search {
        private final int[][] board = new int[9][9];
        private final int[] rowMask = new int[9];
        private final int[] colMask = new int[9];
        private final int[] boxMask = new int[9];

        private List<String> first = List.of();
        private int found;
        private long nodes;
        private int limit;

        Search(String[] rows) {
            if (rows == null || rows.length != 9) {
                throw new IllegalArgumentException("need exactly 9 rows");
            }
            for (int r = 0; r < 9; r++) {
                if (rows[r] == null || rows[r].length() != 9) {
                    throw new IllegalArgumentException("row must have 9 chars");
                }
                for (int c = 0; c < 9; c++) {
                    char ch = rows[r].charAt(c);
                    if (ch == '.' || ch == '0') {
                        continue;
                    }
                    if (ch < '1' || ch > '9') {
                        throw new IllegalArgumentException("invalid symbol");
                    }
                    int digit = ch - '0';
                    int bit = 1 << digit;
                    int b = boxIndex(r, c);

                    if (((rowMask[r] | colMask[c] | boxMask[b]) & bit) != 0) {
                        throw new IllegalArgumentException(
                            "duplicate given at (" + r + "," + c + ")");
                    }

                    board[r][c] = digit;
                    rowMask[r] |= bit;
                    colMask[c] |= bit;
                    boxMask[b] |= bit;
                }
            }
        }

        Result run(int maxSolutions) {
            if (maxSolutions <= 0) {
                throw new IllegalArgumentException(
                    "maxSolutions must be positive");
            }
            limit = maxSolutions;
            dfs();
            return new Result(found, first, nodes);
        }

        private void saveFirst() {
            ArrayList<String> snapshot = new ArrayList<>(9);
            for (int r = 0; r < 9; r++) {
                StringBuilder line = new StringBuilder(9);
                for (int c = 0; c < 9; c++) {
                    line.append((char) ('0' + board[r][c]));
                }
                snapshot.add(line.toString());
            }
            first = List.copyOf(snapshot);
        }

        private void dfs() {
            if (found >= limit) {
                return;
            }
            nodes++;

            int bestR = -1, bestC = -1, bestMask = 0, bestCount = 10;
            for (int r = 0; r < 9; r++) {
                for (int c = 0; c < 9; c++) {
                    if (board[r][c] != 0) {
                        continue;
                    }
                    int b = boxIndex(r, c);
                    int allowed = FULL &
                        ~(rowMask[r] | colMask[c] | boxMask[b]);
                    int count = Integer.bitCount(allowed);

                    if (count == 0) {
                        return;           // Nhánh bất khả thi.
                    }
                    if (count < bestCount) {
                        bestCount = count;
                        bestR = r;
                        bestC = c;
                        bestMask = allowed;
                    }
                }
            }

            if (bestR == -1) {
                found++;
                if (found == 1) {
                    saveFirst();
                }
                return;
            }

            int b = boxIndex(bestR, bestC);
            for (int rest = bestMask; rest != 0; rest &= rest - 1) {
                int bit = rest & -rest;
                int digit = Integer.numberOfTrailingZeros(bit);

                board[bestR][bestC] = digit;
                rowMask[bestR] |= bit;
                colMask[bestC] |= bit;
                boxMask[b] |= bit;

                dfs();

                // Hoàn tác TRƯỚC khi kiểm tra dừng sớm.
                board[bestR][bestC] = 0;
                rowMask[bestR] &= ~bit;
                colMask[bestC] &= ~bit;
                boxMask[b] &= ~bit;

                if (found >= limit) {
                    break;
                }
            }
        }
    }

    static Result solve(String[] rows, int maxSolutions) {
        return new Search(rows).run(maxSolutions);
    }

    // Oracle: quét thủ công hàng/cột/hộp, không dùng mask.
    static boolean referenceAllowed(
            char[][] grid, int row, int col, char digit) {
        for (int k = 0; k < 9; k++) {
            if (grid[row][k] == digit || grid[k][col] == digit) {
                return false;
            }
        }
        int startR = row / 3 * 3;
        int startC = col / 3 * 3;
        for (int dr = 0; dr < 3; dr++) {
            for (int dc = 0; dc < 3; dc++) {
                if (grid[startR + dr][startC + dc] == digit) {
                    return false;
                }
            }
        }
        return true;
    }

    static int referenceCount(char[][] grid, int limit) {
        int row = -1, col = -1;
        findEmpty:
        for (int r = 0; r < 9; r++) {
            for (int c = 0; c < 9; c++) {
                if (grid[r][c] == '.') {
                    row = r;
                    col = c;
                    break findEmpty;
                }
            }
        }
        if (row == -1) {
            return 1;
        }

        int ways = 0;
        for (char digit = '1'; digit <= '9'; digit++) {
            if (referenceAllowed(grid, row, col, digit)) {
                grid[row][col] = digit;
                ways += referenceCount(grid, limit - ways);
                grid[row][col] = '.';
                if (ways >= limit) {
                    break;
                }
            }
        }
        return ways;
    }

    static String[] erase(String[] complete, int... positions) {
        char[][] rows = new char[9][];
        for (int r = 0; r < 9; r++) {
            rows[r] = complete[r].toCharArray();
        }
        for (int position : positions) {
            rows[position / 9][position % 9] = '.';
        }

        String[] result = new String[9];
        for (int r = 0; r < 9; r++) {
            result[r] = new String(rows[r]);
        }
        return result;
    }

    static String[] hideDigits(String[] complete, String digits) {
        String[] result = complete.clone();
        for (int r = 0; r < 9; r++) {
            char[] chars = result[r].toCharArray();
            for (int c = 0; c < 9; c++) {
                if (digits.indexOf(chars[c]) >= 0) {
                    chars[c] = '.';
                }
            }
            result[r] = new String(chars);
        }
        return result;
    }

    static boolean validCompleted(
            List<String> completed, String[] givens) {
        if (completed.size() != 9 || givens.length != 9) {
            return false;
        }
        int[] rows = new int[9], cols = new int[9], boxes = new int[9];
        for (int r = 0; r < 9; r++) {
            if (completed.get(r).length() != 9) {
                return false;
            }
            for (int c = 0; c < 9; c++) {
                char ch = completed.get(r).charAt(c);
                char given = givens[r].charAt(c);
                if (ch < '1' || ch > '9') {
                    return false;
                }
                if (given != '.' && given != '0' && given != ch) {
                    return false;
                }
                int bit = 1 << (ch - '0');
                int b = boxIndex(r, c);
                if (((rows[r] | cols[c] | boxes[b]) & bit) != 0) {
                    return false;
                }
                rows[r] |= bit;
                cols[c] |= bit;
                boxes[b] |= bit;
            }
        }
        for (int i = 0; i < 9; i++) {
            if (rows[i] != FULL || cols[i] != FULL || boxes[i] != FULL) {
                return false;
            }
        }
        return true;
    }

    static int verifyNearSolved(String[] complete) {
        int cases = 0;
        for (int start = 0; start < 81; start++) {
            for (int holes = 1; holes <= 3; holes++) {
                String[] puzzle;
                if (holes == 1) {
                    puzzle = erase(complete, start);
                } else if (holes == 2) {
                    puzzle = erase(complete, start, (start + 29) % 81);
                } else {
                    puzzle = erase(
                        complete, start,
                        (start + 17) % 81, (start + 41) % 81);
                }

                Result fast = solve(puzzle, 2);
                char[][] reference = new char[9][];
                for (int r = 0; r < 9; r++) {
                    reference[r] = puzzle[r].toCharArray();
                }
                int slow = referenceCount(reference, 2);
                if (fast.foundUpToLimit() != slow
                        || slow != 1
                        || !validCompleted(fast.first(), puzzle)) {
                    throw new AssertionError(
                        "disagreement at case " + cases);
                }
                cases++;
            }
        }
        return cases;
    }

    public static void main(String[] args) {
        String[] puzzle = {
            "530070000", "600195000", "098000060",
            "800060003", "400803001", "700020006",
            "060000280", "000419005", "000080079"
        };
        String[] unchanged = puzzle.clone();
        String[] complete = {
            "534678912", "672195348", "198342567",
            "859761423", "426853791", "713924856",
            "961537284", "287419635", "345286179"
        };

        Result unique = solve(puzzle, 2);
        System.out.println("Unique puzzle (cap=2): "
                           + unique.foundUpToLimit());
        System.out.println("Solution:");
        for (String line : unique.first()) {
            System.out.println(line);
        }
        System.out.println("Valid solution: "
                           + validCompleted(unique.first(), puzzle));
        System.out.println("Complete board (cap=2): "
                           + solve(complete, 2).foundUpToLimit());

        String[] ambiguous = hideDigits(complete, "12");
        Result many = solve(ambiguous, 2);
        String status = many.foundUpToLimit() == 2
                ? "2+" : Integer.toString(many.foundUpToLimit());
        System.out.println("Blank digits 1,2 (cap=2): " + status);
        System.out.println("Ambiguous witness valid: "
                           + validCompleted(many.first(), ambiguous));

        String[] impossible = complete.clone();
        char[] firstRow = impossible[0].toCharArray();
        firstRow[0] = '1';
        firstRow[7] = '.';
        impossible[0] = new String(firstRow);
        char[] thirdRow = impossible[2].toCharArray();
        thirdRow[0] = '.';
        impossible[2] = new String(thirdRow);
        System.out.println("Locally legal but impossible (cap=2): "
                           + solve(impossible, 2).foundUpToLimit());

        String[] invalid = complete.clone();
        invalid[0] = "554678912";
        boolean rejected = false;
        try {
            solve(invalid, 2);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Duplicate givens rejected: " + rejected);

        System.out.println("Near-solved cross-checks: "
                           + verifyNearSolved(complete) + " cases OK");
        System.out.println("Input unchanged: "
                           + Arrays.equals(puzzle, unchanged));
    }
}
```

Biên dịch bằng **JDK 17+**, lưu đúng tên tệp/class:

```bash
javac -encoding UTF-8 SudokuBacktrackingDemo.java
java SudokuBacktrackingDemo
```

**Stdout dự kiến:**

```text
Unique puzzle (cap=2): 1
Solution:
534678912
672195348
198342567
859761423
426853791
713924856
961537284
287419635
345286179
Valid solution: true
Complete board (cap=2): 1
Blank digits 1,2 (cap=2): 2+
Ambiguous witness valid: true
Locally legal but impossible (cap=2): 0
Duplicate givens rejected: true
Near-solved cross-checks: 243 cases OK
Input unchanged: true
```

### Kết quả có ý nghĩa gì?

- Câu đố chuẩn được giải ra **bảng hoàn chỉnh đúng**, và khi tìm tiếp đến giới hạn 2, DFS chỉ thấy **1** nghiệm.
- Bảng đã hoàn chỉnh hợp lệ có đúng 1 nghiệm là chính nó.
- Xóa mọi chữ số 1/2 tạo câu đố có **ít nhất hai** lời giải; solver dừng sau hai, nên hiển thị **2+**.
- Bảng mâu thuẫn từ suy luận sâu hơn nhưng không trùng gợi ý ban đầu trả **0 nghiệm**.
- Bảng có hai gợi ý trùng bị ném ngoại lệ trước khi giải.
- Phần kiểm thử độc lập xóa 1, 2 hoặc 3 ô ở mỗi trong 81 vị trí xuất phát, tạo **243 ca**. Solver MRV được đối chiếu với oracle **chọn ô đầu tiên và quét trực tiếp hàng/cột/hộp**; cả hai nhất trí và mỗi snapshot được kiểm tra đầy đủ.
- Dữ liệu `String[]` của caller không bị thay đổi, vì solver tạo board riêng.

**Giới hạn của bộ kiểm thử:** 243 ca gần hoàn chỉnh cùng một số ví dụ khó/đặc biệt chưa đại diện toàn bộ không gian Sudoku. Chứng minh bất biến, tính đầy đủ và tính kết thúc ở mục 9 là cơ sở tổng quát của thuật toán. Muốn đánh giá hiệu năng cần tập đề nhiều độ khó và công cụ đo thời gian/nút thực tế.

## 11. Độ phức tạp và tài nguyên

Nếu `E` là số ô trống, mỗi ô có tối đa 9 khả năng. Một cận rất thô cho số phép gán có thể thử là `9^E`. Cắt nhánh theo ràng buộc và MRV làm giảm rất nhiều nhánh trong nhiều đề, nhưng thời gian xấu nhất vẫn **hàm mũ** theo số biến, không phải `O(81)` chỉ vì mỗi phép kiểm tra mask nhanh.

Trong bản Java:

- Mỗi nút DFS quét tối đa 81 ô, tính mask ứng viên và chọn ô MRV.
- Sau khi chọn ô, thử tối đa 9 digit ứng viên bằng duyệt bit 1.
- Thời gian tổng có thể chặn thô bởi `O(81·9^E)` trên bài 9×9, không tính hằng số chi tiết.
- Bộ nhớ bảng `9×9`, ba mảng mask độ dài 9, snapshot nghiệm đầu tiên `9×9` và stack sâu tối đa `E≤81`. Không lưu tất cả nghiệm khi chỉ cần đếm đến 2.
- Đếm tới 2 có thể dừng nhanh khi đề nhiều nghiệm, nhưng để **chứng minh unique**, phải loại trừ những nhánh có khả năng mang nghiệm thứ hai.

Nếu mở rộng bài toán Latin/Sudoku lên bảng `N×N` với luật phù hợp, có `N²` biến, mỗi biến tối đa `N` giá trị. Cây thử thô có thể đạt bậc `N^(N²)`; phải đánh giá riêng bộ nhớ, tốc độ và cấu trúc vùng.

**Bitmask không làm cây tìm kiếm tự biến thành thời gian đa thức.** Nó cải thiện chi phí kiểm tra hợp lệ và biểu diễn miền; heuristic MRV cải thiện thứ tự khám phá. Chúng thường hữu ích, nhưng không làm biến mất bản chất tổ hợp của bài toán.

## 12. Nâng cấp thuật toán và những giới hạn

**Forward checking:** Sau khi đặt một chữ số, kiểm tra miền của các ô cùng hàng/cột/hộp; nếu ô khác mất mọi ứng viên, quay lui ngay. Khi duy trì miền ứng viên như state riêng, phải hoàn tác mọi thay đổi miền.

**Hidden singles:** Trong một đơn vị (hàng/cột/hộp), nếu một chữ số chỉ có đúng một ô có thể đặt, ô đó bị ép, dù ô có thể còn nhiều ứng viên từ góc nhìn riêng lẻ. Đây là suy luận bổ sung ngoài MRV đơn thuần.

**Least Constraining Value (LCV):** Khi ô có nhiều ứng viên, thử giá trị khiến các ô liên quan mất ít lựa chọn nhất trước. Đây là heuristic **chọn giá trị**, khác MRV là **chọn ô/biến**.

**Algorithm X / Dancing Links:** Sudoku có thể mã hóa thành bài toán **exact cover**: mỗi lựa chọn `(row,col,digit)` phải phủ chính xác các ràng buộc vị trí, hàng–số, cột–số, hộp–số. Khi cần solver hiệu quả hoặc nhiều biến thể, đây là hướng đáng tìm hiểu; nó phức tạp hơn ví dụ backtracking cơ bản.

**SAT/SMT/CP:** Với ràng buộc nhiều loại, solver thỏa mãn chuyên dụng có thể rất hữu ích. Tuy nhiên phải mã hóa đúng bài toán, nhất là các ô gợi ý và luật vùng bổ sung.

**Biến thể Sudoku đường chéo:** Nếu hai đường chéo chính cũng phải chứa 1..9 không lặp, cần bổ sung hai mask đường chéo, kiểm tra ứng viên ở các ô thuộc đường chéo, và thêm/xóa bit khi đặt/undo. Không chỉ kiểm tra đường chéo **sau khi tìm xong** nếu muốn cắt nhánh sớm.

**Bài toán N-Queens:** Dùng ràng buộc cột và hai hướng đường chéo; mỗi hàng đặt một hậu. Đây cũng là backtracking theo CSP, nhưng bitmask và công thức tương tác giữa hàng/cột khác Sudoku.

## 13. Lỗi phổ biến khi giải Sudoku bằng quay lui

**1. Không xác minh gợi ý ban đầu.** Bảng đã đầy nhưng có số trùng không được tính là nghiệm.

**2. Nhầm số 0 với digit Sudoku.** Zero chỉ là ký hiệu trống, phải được thay bằng 1..9.

**3. Sai công thức hộp.** Với chỉ số 0-based, phải là `(r/3)*3+c/3`, không bỏ nhân 3.

**4. Bỏ qua `FULL & ~used`.** `~used` chứa các bit không phải chữ số Sudoku.

**5. Chỉ sửa board mà quên mask.** Nhánh sau có thể đặt hai digit giống nhau trong cùng đơn vị.

**6. Chỉ sửa mask mà quên board.** Ô vẫn bị coi là trống, dẫn tới thử lại.

**7. Hoàn tác thiếu một mask.** Nhánh sau bị cấm digit không tồn tại hoặc thấy digit đang tồn tại là hợp lệ.

**8. Dùng XOR để xóa bit không chắc đang bật.** XOR có thể biến 0 thành 1, làm sai state. Dùng AND với phủ định bit.

**9. Đếm nghiệm mà không snapshot nghiệm đầu tiên.** Sau DFS, bảng làm việc đã bị hoàn tác.

**10. Dừng sau nghiệm đầu rồi kết luận đề có nghiệm duy nhất.** Một nghiệm chỉ xác nhận sự tồn tại.

**11. Dừng khi đạt 2 nhưng ghi “chính xác 2”.** Chỉ chứng minh **ít nhất hai**; còn bao nhiêu nghiệm chưa biết.

**12. Chọn ô không có ứng viên rồi cố thử tiếp.** Đó là dấu hiệu nhánh đã thất bại; quay lui ngay.

**13. Nhầm MRV với solver suy luận hoàn chỉnh.** MRV không triển khai mọi chiến thuật Sudoku nâng cao.

**14. Không phân biệt input không hợp lệ và input vô nghiệm.** Một bảng có gợi ý trùng khác với bảng hợp lệ cục bộ nhưng không thể hoàn thành.

**15. Tự sửa gợi ý khi gặp ngõ cụt.** Điều đó thay đổi đề bài, không còn là lời giải hợp lệ.

**16. Nghĩ thứ tự thử số tăng dần cùng MRV tạo bảng nghiệm nhỏ nhất theo thứ tự từ điển.** MRV có thể chọn ô sâu hơn trước; muốn đảm bảo thứ tự từ điển toàn bảng cần chính sách riêng.

**17. Tái sử dụng đối tượng solver với state chưa reset.** Mã mẫu tạo một `Search` mới cho mỗi lần gọi `solve` để tránh tồn dư masks/counter.

**18. Không kiểm tra toàn bộ nghiệm trả về.** 81 chữ số chưa đủ; phải kiểm chứng từng hàng/cột/hộp và mọi gợi ý.

## 14. Bài tập và checklist

**Bài 1 — Bài toán CSP:** Với Sudoku, chỉ rõ biến, miền giá trị, ràng buộc và trường hợp kết thúc. So sánh với bảng Latin và bài tô màu đồ thị.

**Bài 2 — Bitmask:** Hàng chứa 1,3,5; cột chứa 2,7; hộp chứa 4,8. Tính mask ứng viên. Đáp án là **6 và 9**.

**Bài 3 — Chỉ số hộp:** Tự tính hộp của `(0,0)`, `(2,8)`, `(3,3)`, `(8,8)`; kiểm tra ranh giới các vùng.

**Bài 4 — Hoàn tác:** Chứng minh rằng đặt một digit hợp lệ, chạy nhánh, rồi undo cả board và 3 mask sẽ khôi phục state ban đầu.

**Bài 5 — MRV:** Một ô có 0 ứng viên, một ô khác có 1 ứng viên. Nhánh hiện tại có thể dẫn đến nghiệm không? Vì sao phải phát hiện 0 trước khi tiếp tục?

**Bài 6 — Đề vô nghiệm:** Dùng bảng ở mục 8 có hai dấu chấm; chỉ ra một ô không có ứng viên dù gợi ý không trùng.

**Bài 7 — Nhiều nghiệm:** Xóa mọi số 1 và 2 từ bảng hoàn chỉnh hợp lệ. Chứng minh có ít nhất hai nghiệm bằng phép hoán đổi toàn cục.

**Bài 8 — Đếm có giới hạn:** Viết `countUpToTwo`; giải thích khi nào kết quả 1 đủ chứng minh unique và khi nào 2 phải được diễn giải 2+.

**Bài 9 — Kiểm thử:** Sinh bảng từ lời giải chuẩn rồi xóa 1–3 ô. So bộ giải MRV với solver chọn ô đầu tiên, xác minh cả đầu ra và gợi ý giữ nguyên.

**Bài 10 — Hiệu năng:** Đo số nút DFS của solver chọn ô đầu tiên và MRV trên các đề khó khác nhau. Vì sao một phép đo riêng không chứng minh MRV luôn tốt hơn?

**Bài 11 — Luật đường chéo:** Bổ sung hai mask cho Sudoku X, cập nhật hàm ứng viên và rollback, đối chiếu với oracle kiểm tra thêm đường chéo.

**Bài 12 — Backtracking tổng quát:** Xây bộ giải cho N-Queens, chỉ ra điểm giống và khác về trạng thái, miền giá trị và ràng buộc.

**Checklist trước khi nộp:**

1. Có đúng **9×9** ô và quy ước trống rõ ràng?
2. Mọi gợi ý có hợp lệ, không trùng hàng/cột/hộp?
3. Board, rowMask, colMask, boxMask luôn nhất quán?
4. Candidate mask chỉ gồm digit chưa bị cấm?
5. Khi một ô không có ứng viên, có quay lui ngay?
6. Chọn ô MRV có không làm bỏ sót bất kỳ giá trị hợp lệ nào?
7. Mỗi lần đặt có đúng thao tác hoàn tác tương ứng?
8. Có snapshot kết quả trước khi quay lui tiếp?
9. Đếm tối đa hai có phân biệt đúng **0 / 1 / 2+**?
10. Nếu cần không sửa input, API đã giữ nguyên mọi dữ liệu caller chưa?
11. Có chứng minh đúng bằng bất biến và quy nạp số ô trống?
12. Có đối chiếu với một oracle độc lập và thử các trường hợp unique, invalid, impossible, ambiguous?

**Tiêu chí hoàn thành:** Bạn có thể mô hình hóa một bài điền bảng thành CSP, viết quay lui **đặt–đệ quy–hoàn tác**, biểu diễn các ràng buộc Sudoku bằng mask, chọn ô MRV, phân biệt một nghiệm với nghiệm duy nhất, và chạy thử bộ giải Java 17+ với một cách kiểm tra độc lập.

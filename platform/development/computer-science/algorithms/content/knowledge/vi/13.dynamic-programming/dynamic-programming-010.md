# Đếm số lời giải tối ưu và xử lý trường hợp bằng nhau

## 1. Không chỉ tìm giá trị tối ưu, còn phải đếm nghiệm

Trong quy hoạch động (dynamic programming, DP), nhiều bài toán không chỉ hỏi **giá trị lớn nhất/nhỏ nhất** mà còn hỏi **có bao nhiêu cách khác nhau đạt đúng giá trị đó**. Hai câu hỏi phải được xử lý song song; chỉ biết điểm tốt nhất không thể suy ra số nghiệm.

Ví dụ, trên lưới 2×3 có trọng số mọi ô bằng 1, xuất phát từ góc trái trên và đi sang phải (R) hoặc xuống (D) tới góc phải dưới. Mỗi đường đi thăm 4 ô, có tổng điểm 4. Có ba đường đi khác nhau:

~~~text
1   1   1
1   1   1

RRD
RDR
DRR

Giá trị tối ưu: 4
Số lời giải tối ưu: 3
~~~

Muốn trả cả hai kết quả, một trạng thái DP cần mang **cặp thông tin**: giá trị tối ưu và số cách đạt chính giá trị ấy. Ở mỗi lựa chọn, kết quả mới có thể tốt hơn, kém hơn hoặc **bằng** kết quả đang có. Xử lý đúng trường hợp bằng nhau là trung tâm của bài toán.

Cần nói rõ bài toán tối ưu hóa **min** hay **max**, điều kiện hợp lệ, trạng thái cơ sở, quy ước lời giải nào được tính là khác, và số cách cần chính xác hay theo một phép modulo. Nếu thiếu các điều kiện này, phép cộng số cách có thể sai dù giá trị tối ưu đúng.

## 2. Hai lời giải khác nhau là như thế nào?

**Định danh nghiệm** phải được quy định trong hợp đồng:

| Bài toán | Một nghiệm | Hai nghiệm được xem là khác khi |
| --- | --- | --- |
| Đường đi lưới | Chuỗi bước phải/xuống từ nguồn tới đích | Khác ít nhất một bước |
| Knapsack 0/1 | Tập **chỉ số** vật phẩm được chọn | Khác ít nhất một chỉ số |
| Đổi tiền | Dãy đồng tiền *hoặc* đa tập đồng tiền, tùy đề | Theo thứ tự hoặc theo số lượng từng mệnh giá |
| LCS | Chuỗi ký tự chung dài nhất | Khác chuỗi ký tự, không chỉ khác cách căn chỉnh |
| Đường đi đồ thị | Chuỗi đỉnh hoặc chuỗi cạnh | Tùy cách xử lý đa cạnh song song |
| Chia nhóm | Một phân hoạch | Có thể coi hoán vị tên/thứ tự nhóm là cùng nghiệm |

Ví dụ đổi tiền bằng đồng 1 và 2 để được tổng 3, với yêu cầu **ít đồng nhất**:

- Nếu nghiệm là chuỗi thao tác, [1,2] và [2,1] là **hai nghiệm** cùng dùng hai đồng.
- Nếu nghiệm là đa tập mệnh giá, hai chuỗi trên biểu diễn **một nghiệm**: một đồng 1 và một đồng 2.

Vì vậy, công thức cộng số cách từ hai nhánh chỉ được dùng khi hai nhánh tạo thành các tập nghiệm **không giao nhau** theo định nghĩa đã chọn. Nếu hai nhánh cùng sinh một nghiệm, cộng trực tiếp sẽ **đếm trùng**.

Bài minh họa Java sau chọn nghiệm là **đường đi theo chuỗi bước** R/D. Với cách đi chỉ phải/xuống, mỗi đường đi kết thúc ở một ô khác gốc có bước cuối duy nhất, nên dễ chứng minh phép cộng của các nhánh hòa không bị đếm trùng.

## 3. Cặp trạng thái (best, ways) và trường hợp cơ sở

Với trạng thái s:

~~~text
best[s] = giá trị tối ưu có thể đạt tại s
ways[s] = số nghiệm phân biệt đạt đúng best[s]
~~~

Nếu s không có nghiệm hợp lệ, `best[s]` **không có nghĩa**; phải biểu diễn bằng `reachable[s]=false` hoặc kiểu `Optional`/sentinel được chứng minh không xung đột. Với trạng thái đạt được, `ways[s]` là số cách tương ứng với **giá trị tốt nhất**, không phải tổng số cách hợp lệ.

Trạng thái khởi đầu có một cách cơ sở, thường là một chuỗi lựa chọn rỗng trước khi thực hiện bước nào:

~~~text
reachable[start] = true
best[start] = điểm gốc, theo định nghĩa bài toán
ways[start] = 1
~~~

Một đường đi gồm riêng ô gốc là **một** đường, không phải không có đường. Nếu gốc bị chặn thì reachable=false và ways=0.

Trạng thái không thể đạt:

~~~text
reachable[s] = false
ways[s] = 0
best[s] = không so sánh / không sử dụng
~~~

Các trạng thái có thể **thật sự đạt giá trị 0 hoặc âm**. Vì vậy không được dùng `best==0` để biểu thị “chưa tính”; cũng không được dùng kết quả `ways mod M == 0` để kết luận “không có đường”, vì số cách thực tế có thể là bội của M.

## 4. Ba nhánh cập nhật: lớn hơn, nhỏ hơn, bằng nhau

Giả sử hai nhóm nghiệm **không giao nhau** có kết quả:

~~~text
A: (scoreA, countA)
B: (scoreB, countB)
~~~

Với bài toán **tối đa hóa**, quy tắc gộp đúng là:

| So sánh | best mới | ways mới | Vì sao? |
| --- | --- | --- | --- |
| scoreA > scoreB | scoreA | countA | B kém, không đếm |
| scoreA < scoreB | scoreB | countB | A kém, không đếm |
| scoreA = scoreB | scoreA | countA + countB | Cả hai nhóm đều tối ưu |

Mã giả:

~~~text
mergeMax((a, ca), (b, cb)):
    if a > b: return (a, ca)
    if a < b: return (b, cb)
    return (a, ca + cb)    // chỉ nếu hai nhóm nghiệm rời nhau
~~~

Với **tối thiểu hóa**, đảo chiều so sánh tốt/kém, nhưng khi hòa vẫn cộng số cách. Không được nhầm `ways` với số nhánh đã xét.

Ví dụ các lựa chọn cho một trạng thái lần lượt là (12,2), (15,3) và (15,4):

1. Sau lựa chọn đầu: best=12, ways=2.
2. Lựa chọn thứ hai tốt hơn: **thay** best=15, ways=3.
3. Lựa chọn thứ ba bằng 15: **cộng** ways=3+4=7.

Kết quả là (15,7), không phải (15,9) vì hai nghiệm đạt điểm 12 đã kém, và không phải (15,4) vì có hai nhóm cùng đạt điểm 15.

Đây là phép gộp cặp trạng thái tối ưu, không phải phép cộng mọi cách đi. **Tốt hơn thì thay, kém hơn thì bỏ, bằng nhau thì cộng** — sau khi đã bảo đảm các nhóm không trùng.

## 5. Công thức quy hoạch động trên lưới có ô chặn

Cho lưới R hàng, C cột. Mỗi ô (r,c) có một trọng số nguyên `w[r][c]` (âm, 0 hoặc dương), hoặc bị chặn. Xuất phát tại (0,0), đến (R−1,C−1), chỉ đi **phải** hoặc **xuống**; tổng điểm là tổng trọng số các ô đã thăm, **kể cả gốc và đích**.

Mục tiêu: trả (điểm tối đa, số đường đi tối ưu). Nếu không có đường hợp lệ, báo **không có đường**, không trả (0,0) như thể có một nghiệm điểm 0.

Trạng thái:

~~~text
best[r][c] = tổng điểm lớn nhất từ gốc đến (r,c)
ways[r][c] = số đường tới (r,c) đạt best[r][c]
~~~

Nếu ô gốc hợp lệ:

~~~text
best[0][0] = w[0][0]
ways[0][0] = 1
~~~

Với ô không phải gốc, chỉ có tối đa hai tiền nhiệm:

~~~text
up   = (r-1,c) nếu r > 0 và up đạt được
left = (r,c-1) nếu c > 0 và left đạt được
~~~

Nếu ô hiện tại bị chặn hoặc không có tiền nhiệm đạt được: **unreachable**, ways=0. Ngược lại:

~~~text
parentBest = max(best[p]) với p là tiền nhiệm đạt được
best[r][c] = w[r][c] + parentBest

ways[r][c] =
    tổng ways[p] với mọi tiền nhiệm p đạt được
    và có best[p] == parentBest
~~~

Vì mọi đường đi tới (r,c) đều cộng thêm **cùng trọng số ô hiện tại**, so sánh `best` của hai tiền nhiệm là đủ. Nếu hai tiền nhiệm hòa điểm tốt nhất, cộng số đường tối ưu từ cả hai.

### Vì sao phép cộng ở đây không đếm trùng?

Mỗi đường tới ô (r,c) khác gốc có **bước cuối duy nhất**: đi xuống từ `up` hoặc đi phải từ `left`. Một chuỗi bước không thể cùng lúc kết thúc bằng cả D và R, nên hai nhóm đường đi là **rời nhau**.

Nếu một tiền nhiệm có điểm thấp hơn, đường đi qua nó không thể bắt kịp tiền nhiệm tốt hơn khi cả hai phải cộng cùng `w[r][c]`. Chỉ cộng số cách từ các tiền nhiệm có **điểm tối ưu của ô hiện tại**.

## 6. Truy vết khi có nhiều trường hợp bằng nhau

Với lưới 2×3 toàn số 1:

~~~text
1   1   1
1   1   1
~~~

Mỗi trạng thái ghi `best/ways`:

| Ô | Các tiền nhiệm | best | ways | Giải thích |
| --- | --- | ---: | ---: | --- |
| (0,0) | Gốc | 1 | 1 | Một đường cơ sở |
| (0,1) | Trái (0,0) | 2 | 1 | Chỉ một cách đi |
| (0,2) | Trái (0,1) | 3 | 1 | Chỉ một cách đi |
| (1,0) | Trên (0,0) | 2 | 1 | Chỉ một cách đi |
| (1,1) | Trên 2/1 và trái 2/1 | 3 | 2 | Hòa: cộng 1+1 |
| (1,2) | Trên 3/1 và trái 3/2 | 4 | 3 | Hòa: cộng 1+2 |

Bảng:

~~~text
1/1   2/1   3/1
2/1   3/2   4/3
~~~

Tổng tối đa ở đích là **4** với **3** đường tối ưu (RRD, RDR, DRR). Số 3 không phải số ô, mà là số nghiệm đường đi khác nhau.

### Một nhánh tốt hơn: không cộng đường kém

~~~text
1   100
1     1
~~~

Đến góc phải dưới: đường qua ô 100 có tổng 102, đường còn lại có tổng 3. Kết quả là **best=102, ways=1**. Nếu chỉ cộng hai số cách vì có hai đường, sẽ sai bài toán đếm *đường tối ưu*.

### Trọng số âm

~~~text
-2   -3
-1   -4
~~~

Đường phải–xuống tổng −9, đường xuống–phải tổng −7. Vậy **best=−7, ways=1**. Một thuật toán khởi tạo mọi điểm bằng 0 rồi lấy max có thể tạo ra giá trị 0 từ một đường **không tồn tại**, sai hợp đồng.

## 7. Ô bị chặn, trạng thái không thể đạt và điểm bằng 0

Giả sử null biểu diễn ô bị chặn:

~~~text
1   X   1
1   1   1
~~~

Dù ô (0,2) không bị chặn, nó **không đạt được** từ gốc vì (0,1) bị chặn. Đường duy nhất tới đích là:

~~~text
(0,0) -> (1,0) -> (1,1) -> (1,2)
best = 4
ways = 1
~~~

Lưới khác:

~~~text
1   X
X   2
~~~

không có đường hợp lệ. Kết quả cần phân biệt với lưới toàn 0, trong đó có những đường đạt điểm 0. Quy ước nên là:

- **Ô chặn:** reachable=false, ways=0.
- **Ô không có tiền nhiệm đạt được:** reachable=false, ways=0.
- **Ô đạt được với best=0:** reachable=true và có ways>0 khi đếm chính xác.
- **Đếm modulo:** ways có thể bằng 0 theo modulo dù reachable=true.

Không nên gán một sentinel điểm rất nhỏ như `Long.MIN_VALUE` rồi cộng trọng số mà không kiểm tra: phép cộng có thể tràn, và nếu điểm tối ưu hợp lệ cũng bằng sentinel thì không phân biệt được. Cờ reachable là phương án rõ ràng.

## 8. Nén trạng thái xuống một hàng

Để tính (r,c), ta chỉ cần:

- Ô phía **trên** (r−1,c).
- Ô bên **trái** (r,c−1).

Vì vậy không nhất thiết cấp phát bảng R×C. Có thể dùng ba mảng chiều dài C:

~~~text
long[] best
BigInteger[] ways
boolean[] reachable
~~~

Duyệt **hàng từ trên xuống** và **cột từ trái sang phải**. Khi xử lý cột c:

- `best[c]`, `ways[c]`, `reachable[c]` trước ghi đè đang là trạng thái **ô trên**.
- `best[c-1]`, `ways[c-1]`, `reachable[c-1]` đã được cập nhật ở hàng hiện tại nên là trạng thái **ô trái**.
- Sau khi chọn tiền nhiệm tốt nhất, cộng trọng số ô hiện tại rồi ghi đè cột c.

Nếu ô bị chặn, phải đặt reachable[c]=false và ways[c]=0 để không cho các ô phía dưới nhầm nó là một tiền nhiệm hợp lệ. Khi không có tiền nhiệm, xử lý tương tự.

**Đừng duyệt từ phải sang trái** với cùng công thức: lúc đó `c-1` có thể vẫn thuộc hàng trước, không còn là ô trái hiện tại. Cũng đừng khởi tạo ways=1 cho mọi cột, vì chỉ trạng thái gốc mới có một đường cơ sở độc lập.

## 9. Java 17+ chạy độc lập: đếm đường đi tổng lớn nhất

Chương trình dùng `Integer[][]`, trong đó `null` là ô chặn. Kết quả là `Optional<Answer>`:

- `Optional.empty()`: không có đường hợp lệ.
- `Answer(bestSum, ways)`: tổng tốt nhất kiểu `long` và **số đường tối ưu chính xác** bằng `BigInteger`.

Hợp đồng Java:

1. `grid` không null; các hàng không null và **có cùng độ dài**. Mảng hàng không đều gây `IllegalArgumentException`.
2. Lưới có 0 hàng hoặc 0 cột trả `Optional.empty()`.
3. Ô null bị chặn; nếu nguồn hoặc đích bị chặn, không có đường.
4. Điểm ô có thể âm, 0 hoặc dương; điểm hai đầu được tính.
5. Không thay đổi mảng đầu vào; chỉ dùng bộ nhớ phụ theo chiều rộng.
6. `Math.addExact` báo `ArithmeticException` nếu tổng vượt `long`, không âm thầm trả số sai.

Lưu tệp **CountOptimalSolutions.java**:

~~~java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;
import java.util.Optional;

public final class CountOptimalSolutions {
    private CountOptimalSolutions() {}

    public record Answer(long bestSum, BigInteger ways) {}

    /**
     * Counts distinct right/down paths with maximum cell sum.
     * Null cells are blocked. Includes start and end scores.
     * Returns empty if the target cannot be reached.
     */
    public static Optional<Answer> countMaxPaths(Integer[][] grid) {
        Objects.requireNonNull(grid, "grid");

        if (grid.length == 0) {
            return Optional.empty();
        }

        Objects.requireNonNull(grid[0], "grid[0]");
        int cols = grid[0].length;
        for (int r = 0; r < grid.length; r++) {
            Objects.requireNonNull(grid[r], "grid[" + r + "]");
            if (grid[r].length != cols) {
                throw new IllegalArgumentException("ragged grid");
            }
        }

        if (cols == 0) {
            return Optional.empty();
        }

        long[] best = new long[cols];
        BigInteger[] ways = new BigInteger[cols];
        boolean[] reachable = new boolean[cols];
        Arrays.fill(ways, BigInteger.ZERO);

        for (int r = 0; r < grid.length; r++) {
            for (int c = 0; c < cols; c++) {
                Integer cell = grid[r][c];

                if (cell == null) {
                    reachable[c] = false;
                    ways[c] = BigInteger.ZERO;
                    continue;
                }

                if (r == 0 && c == 0) {
                    best[c] = cell.longValue();
                    ways[c] = BigInteger.ONE;
                    reachable[c] = true;
                    continue;
                }

                // Column c still represents the previous row (up).
                boolean up = reachable[c];

                // Column c-1 is already updated in this row (left).
                boolean left = c > 0 && reachable[c - 1];

                if (!up && !left) {
                    reachable[c] = false;
                    ways[c] = BigInteger.ZERO;
                    continue;
                }

                long parentBest = up ? best[c] : best[c - 1];
                BigInteger parentWays =
                        up ? ways[c] : ways[c - 1];

                if (left) {
                    if (!up || best[c - 1] > parentBest) {
                        parentBest = best[c - 1];
                        parentWays = ways[c - 1];
                    } else if (best[c - 1] == parentBest) {
                        parentWays = parentWays.add(ways[c - 1]);
                    }
                }

                best[c] = Math.addExact(
                        parentBest, cell.longValue());
                ways[c] = parentWays;
                reachable[c] = true;
            }
        }

        int target = cols - 1;
        if (!reachable[target]) {
            return Optional.empty();
        }
        return Optional.of(new Answer(best[target], ways[target]));
    }

    private static void show(String label, Integer[][] grid) {
        Optional<Answer> result = countMaxPaths(grid);
        String description = result.isPresent()
                ? "best=" + result.get().bestSum()
                    + ", ways=" + result.get().ways()
                : "unreachable";
        System.out.println(label + ": " + description);
    }

    public static void main(String[] args) {
        show("All ones", new Integer[][] {
            {1, 1, 1},
            {1, 1, 1}
        });
        show("Unique winner", new Integer[][] {
            {1, 100},
            {1, 1}
        });
        show("Blocked", new Integer[][] {
            {1, null, 1},
            {1, 1, 1}
        });
        show("No path", new Integer[][] {
            {1, null},
            {null, 2}
        });
        show("Negative", new Integer[][] {
            {-2, -3},
            {-1, -4}
        });
        show("All zero 3x3", new Integer[][] {
            {0, 0, 0},
            {0, 0, 0},
            {0, 0, 0}
        });
        show("Single", new Integer[][] {{-7}});
        show("Empty", new Integer[0][]);
        show("Empty width", new Integer[][] {{}, {}});

        try {
            countMaxPaths(new Integer[][] {{1, 2}, {3}});
        } catch (IllegalArgumentException ex) {
            System.out.println("Ragged: IllegalArgumentException");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CountOptimalSolutions.java
java CountOptimalSolutions
~~~

Stdout chính xác:

~~~text
All ones: best=4, ways=3
Unique winner: best=102, ways=1
Blocked: best=4, ways=1
No path: unreachable
Negative: best=-7, ways=1
All zero 3x3: best=0, ways=6
Single: best=-7, ways=1
Empty: unreachable
Empty width: unreachable
Ragged: IllegalArgumentException
~~~

Với lưới 3×3 toàn 0, có đúng 6 chuỗi bước khác nhau gồm hai R và hai D; mọi chuỗi đều đạt tổng 0 nên số đường tối ưu bằng 6. Đây là phản ví dụ rõ ràng cho quy tắc sai “điểm bằng 0 tức là không có đường”.

Chương trình chỉ lưu một hàng DP gồm ba mảng. `BigInteger` tránh tràn **số cách**; dùng `Math.addExact` để kiểm tra tràn **điểm tối ưu**. Hai đại lượng này độc lập.

## 10. Chứng minh tính đúng bằng quy nạp

Ta chứng minh hai bất biến sau cho mỗi ô đã duyệt:

1. Nếu `reachable` là false thì không có đường từ gốc tới ô; nếu true thì `best` là điểm lớn nhất của mọi đường hợp lệ tới ô.
2. Nếu true, `ways` bằng đúng số đường đi phân biệt đạt điểm `best`.

### Cơ sở

Nếu ô (0,0) đi được, có đúng một đường gồm riêng ô này, điểm bằng trọng số của nó; do đó best=w[0][0] và ways=1 là đúng. Nếu ô bị chặn, không có đường, nên unreachable. Lưới rỗng/không có cột không có đích theo hợp đồng và trả empty.

### Bước quy nạp

Giả sử các trạng thái trên và trái (nếu tồn tại) đã đúng. Mọi đường tới ô hiện tại khác gốc đều có bước cuối từ **một trong hai tiền nhiệm ấy**. Nếu không có tiền nhiệm đạt được, ô không thể đạt. Nếu có, vì mọi đường tới ô đều phải cộng cùng điểm của ô, đường tốt nhất phải bắt nguồn từ tiền nhiệm có best lớn nhất.

Khi một tiền nhiệm kém hơn, đường qua nó không thể thành tối ưu. Khi hai tiền nhiệm bằng nhau, tập đường qua trên và tập đường qua trái **rời nhau theo bước cuối**, nên số đường tối ưu là tổng hai ways. Điều đó duy trì hai bất biến tại ô mới.

Thứ tự duyệt trên xuống, trái sang phải bảo đảm hai tiền nhiệm đã được tính. Mảng một chiều chỉ ghi đè sau khi đọc trạng thái trên, trong khi trạng thái trái đã được cập nhật cho hàng hiện tại, nên không thay đổi logic truy hồi.

Đến ô đích, hai bất biến cho đúng **giá trị tối ưu và số nghiệm tối ưu**. Vòng lặp hữu hạn R×C nên kết thúc.

## 11. Độ phức tạp và kích thước BigInteger

Nếu xem cộng/so sánh các số nguyên là O(1):

- Có R×C trạng thái.
- Mỗi ô xét tối đa hai tiền nhiệm.
- Thời gian **O(RC)**.
- Ba mảng một chiều độ dài C cho bộ nhớ phụ **O(C) vị trí trạng thái**.

Nhưng số đường có thể tăng rất nhanh. Với lưới R×C không có chướng ngại, số đường từ gốc tới đích là:

~~~text
choose(R + C - 2, R - 1)
~~~

vì mỗi đường dùng R−1 bước xuống và C−1 bước phải. Trong lưới toàn 0, **tất cả** đường đều tối ưu. Số này có thể vượt giới hạn 64-bit nên `BigInteger` là phù hợp khi bài yêu cầu đếm chính xác.

Lưu một số BigInteger có b bit phải tốn O(b) bit; số cách tới một ô có nhiều nhất O(R+C) bit trong mô hình lưới phải/xuống. Do đó O(C) ô tham chiếu **không có nghĩa O(C) bit**; một cận bộ nhớ thô là O(C(R+C)) bit cho các giá trị cách đi, ngoài các mảng điểm/cờ. Phép cộng BigInteger cũng không phải O(1) theo mô hình chi phí bit; cận thô cho công việc cộng là O(RC(R+C)) phép toán bit.

Trong DP tổng quát có S trạng thái và E chuyển tiếp, nếu mỗi lần xử lý trạng thái/chuyển tiếp mất O(1) phép toán số học, thường có cận O(S+E). Nếu số cách lưu bằng số nguyên lớn, cần tính thêm chi phí số học và bộ nhớ biểu diễn.

## 12. Cẩn thận với đếm trùng khi cộng các nhánh hòa

Quy tắc **cộng ways khi bằng nhau** chỉ đúng nếu hai nhóm nghiệm không giao nhau. Đối với đường đi lưới, điều này đúng do bước cuối là duy nhất. Trong các bài toán khác phải chứng minh lại.

### Đổi tiền: thứ tự có quan trọng không?

Mệnh giá {1,2}, tổng tiền 3, số đồng tối thiểu 2:

- Đếm **dãy thao tác**: [1,2] và [2,1] → 2 nghiệm.
- Đếm **đa tập đồng tiền**: một đồng 1 và một đồng 2 → 1 nghiệm.

Một truy hồi chỉ theo tổng tiền rồi chọn đồng tiếp theo có thể đếm các hoán vị, không đúng nếu đề yêu cầu số **tổ hợp**. Có thể thêm trạng thái chỉ số loại tiền để buộc thứ tự chọn nhất quán.

### LCS: khác căn chỉnh chưa chắc khác chuỗi

Với X="aa" và Y="a", độ dài LCS là 1. Có hai cách dùng hai vị trí "a" trong X để căn với Y, nhưng **chỉ một chuỗi LCS phân biệt là "a"**. Cộng ways hai nhánh DP có cùng độ dài mà không loại trùng sẽ đếm **hai căn chỉnh**, không phải một chuỗi.

Muốn đếm các chuỗi LCS phân biệt, cần một truy hồi/chính sách khử trùng thích hợp; công thức cộng số cách thông thường chỉ chứng minh đúng cho một định nghĩa nghiệm cụ thể.

### Đồ thị có cạnh song song

Nếu u và v được nối bằng hai cạnh e1 và e2, có hai đường **theo cạnh** nhưng có thể chỉ một đường **theo chuỗi đỉnh**. Một DP đếm qua từng cạnh có thể đếm e1 và e2 riêng biệt; hợp đồng phải nói rõ loại đường nào cần đếm.

**Kết luận:** xử lý trường hợp bằng nhau không chỉ là cộng hai biến, mà là chứng minh rằng mỗi nghiệm tối ưu được tính **đúng một lần**.

## 13. Áp dụng sang những bài toán DP khác

### Knapsack 0/1: tối đa giá trị và đếm tập chọn tối ưu

Xét `dp[i][cap]` cho giá trị tốt nhất khi chỉ còn các vật phẩm từ i trở đi và dung lượng còn lại là cap. Có hai nhánh:

- Không chọn vật phẩm i.
- Chọn vật phẩm i (nếu còn dung lượng), cộng giá trị vật phẩm i với lời giải con.

Khi đếm theo **tập chỉ số được chọn**, hai nhánh rời nhau: một tập chứa i và tập kia không. Vì vậy có thể chọn giá trị tốt hơn hoặc cộng số cách khi hòa. Nếu cho phép chọn không vật phẩm nào, trạng thái cơ sở “không còn vật phẩm” có điểm 0 và **một** nghiệm tập rỗng.

Vật phẩm trọng lượng 0, giá trị 0 tạo hai tập chọn khác nhau (chọn/bỏ i) có cùng điểm, nên phải tính hai nếu nghiệm được định danh theo chỉ số. Nhưng nếu đề đếm tập **giá trị** sau khi bỏ nhãn chỉ số, hai lựa chọn có thể không tạo hai nghiệm phân biệt — cần đổi hợp đồng hoặc thuật toán.

### LIS: đếm dãy con tăng dài nhất theo vị trí

Cho mảng a, đặt `len[i]` là độ dài tốt nhất của dãy con tăng **kết thúc tại i**, `cnt[i]` là số dãy con theo **chỉ số** đạt độ dài ấy. Khởi tạo mỗi i bằng `len[i]=1, cnt[i]=1`. Với mọi j<i mà a[j]<a[i]:

~~~text
candidate = len[j] + 1

Nếu candidate > len[i]:
    len[i] = candidate
    cnt[i] = cnt[j]

Nếu candidate == len[i]:
    cnt[i] += cnt[j]
~~~

Sau khi duyệt, lấy L=max len[i] rồi cộng cnt[i] cho những i có len[i]=L. Các nhóm kết thúc ở chỉ số i khác nhau được phân biệt, nên phép cộng đúng khi đếm **dãy con theo chỉ số**. Nếu đếm **dãy giá trị phân biệt**, các vị trí khác nhau có cùng giá trị có thể tạo trùng nghiệm, cần cách khác.

### Đường đi ngắn nhất trên DAG

Với đồ thị có hướng không chu trình và trọng số cạnh, cần đếm đường **có tổng chi phí nhỏ nhất**. Thay `max` bằng `min`, lưu (dist, ways), xét các cạnh tới một đỉnh theo thứ tự topo. Nếu một cạnh cho khoảng cách nhỏ hơn, thay cả dist và ways; nếu bằng nhau, cộng ways. Bước cuối theo **cạnh** tạo phân hoạch nghiệm nếu định danh đường theo cạnh.

Không được áp dụng trật tự topo cho đồ thị có chu trình. Với chu trình trọng số 0, số **walk** tối ưu có thể là vô hạn; cần định nghĩa đường đơn hoặc giới hạn số bước trước khi bàn về “số lời giải tối ưu”.

## 14. BigInteger, modulo và tràn số

### Đếm chính xác

Số nghiệm tối ưu có thể lớn theo hàm tổ hợp. Nếu đề hỏi **toàn bộ số cách**, sử dụng `BigInteger` hoặc kiểu số nguyên lớn để không mất chữ số. `int` và `long` đều có giới hạn; không được lặng lẽ để phép cộng số cách tràn rồi báo một số âm hoặc nhỏ bất thường.

### Đếm modulo M

Nếu đề yêu cầu số cách `mod M`, khi hòa có thể cập nhật:

~~~text
ways = (ways + candidateWays) mod M
~~~

Chỉ áp modulo lên **số cách**, không áp lên `best` nếu điểm tối ưu vẫn phải so sánh chính xác: modulo có thể đảo thứ tự lớn/nhỏ. Một trạng thái có `ways mod M == 0` có thể vẫn đạt được với **M hoặc 2M đường**; không dùng phần dư để quyết định reachable.

Khi tính tổng hai phần dư trong Java `long`, vẫn phải đảm bảo **phép cộng trước modulo không tràn** đối với mô-đun đã chọn. Với M=1_000_000_007, tổng hai phần dư nhỏ hơn 2_000_000_014, an toàn trong long.

### Tràn giá trị tối ưu

`BigInteger ways` **không bảo vệ** `long best`. Nếu tổng điểm có thể vượt long, cần BigInteger cho điểm hoặc bắt tràn. Chương trình sử dụng `Math.addExact` để không âm thầm đổi dấu điểm khi vượt phạm vi.

### Chi phí bộ nhớ

Bộ nhớ O(C) trạng thái không có nghĩa O(C) bit khi dùng BigInteger. Cần nêu đúng mô hình phân tích và kích thước con số khi các giá trị rất lớn.

## 15. Kiểm thử tính đúng bằng oracle liệt kê

Một phép thử đáng tin là so cặp **(best, ways)** với một thuật toán độc lập trên lưới nhỏ. Với lưới phải/xuống, có thể DFS liệt kê **mọi đường hợp lệ** từ gốc tới đích:

~~~text
scores = []

DFS(r, c, currentSum):
    nếu ngoài lưới hoặc ô bị chặn: return
    currentSum += weight[r][c]

    nếu (r,c) là đích:
        thêm currentSum vào scores
        return

    DFS(r+1, c, currentSum)
    DFS(r, c+1, currentSum)

Nếu scores rỗng: không có đường
Ngược lại:
    best = max(scores)
    ways = số phần tử scores có giá trị best
~~~

Đây là **oracle kiểm thử** cho đầu vào nhỏ, không phải lời giải hiệu quả cho lưới lớn: số đường đi có thể tăng theo tổ hợp.

Các ca cố định cần có:

| Đầu vào | Kết quả |
| --- | --- |
| 2×3 toàn 1 | best=4, ways=3 |
| [[1,100],[1,1]] | best=102, ways=1 |
| [[1,null,1],[1,1,1]] | best=4, ways=1 |
| [[1,null],[null,2]] | Không có đường |
| [[−2,−3],[−1,−4]] | best=−7, ways=1 |
| 3×3 toàn 0 | best=0, ways=6 |
| [[−7]] | best=−7, ways=1 |
| [[null]] | Không có đường |
| Lưới 0 hàng hoặc 0 cột | Không có đường |
| Lưới có hàng dài khác nhau | IllegalArgumentException |
| Lưới null hoặc hàng null | NullPointerException |

Nên sinh nhiều lưới nhỏ có điểm âm/0/dương và ô chặn ngẫu nhiên, rồi so **cả điểm lẫn số cách** với oracle. Đặc biệt thử những ô có hai tiền nhiệm hòa điểm tốt nhất nhưng **ways khác nhau**, vì rất dễ viết nhầm thành gán đè thay vì cộng.

Những tính chất cần giữ: nếu trả kết quả chính xác thì ways>0; nếu không có đường thì DFS không tìm được đường; đầu vào không bị sửa; với lưới toàn 0 không chặn, số cách đúng bằng `choose(R+C−2,R−1)`.

## 16. Lỗi thường gặp và checklist

Các lỗi thường gặp:

1. **Chỉ lưu best, không lưu ways.** Không thể suy ra số nghiệm tối ưu từ riêng điểm số.
2. **Gặp lựa chọn tốt hơn vẫn cộng số cách cũ.** Các nghiệm kém hơn không còn tối ưu; phải thay best và ways.
3. **Gặp lựa chọn bằng nhau nhưng ghi đè ways.** Phải cộng nếu các nhóm nghiệm không giao nhau.
4. **Cộng cả những tiền nhiệm kém điểm.** Đó là đếm mọi nghiệm, không phải chỉ nghiệm tối ưu.
5. **Khởi tạo ways=0 cho nguồn hợp lệ.** Trạng thái cơ sở có một đường hợp lệ, phải là 1.
6. **Dùng best=0 làm dấu chưa đạt.** Có thể có đường điểm 0 hoặc âm; cần reachable riêng.
7. **Dùng ways%M==0 để kết luận không có nghiệm.** Số nghiệm thật có thể là bội của M.
8. **Cộng những nhánh tạo trùng nghiệm.** Thường gặp khi đếm chuỗi LCS phân biệt, đổi tiền không xét thứ tự và đồ thị đa cạnh.
9. **Không xóa trạng thái khi gặp ô chặn.** Các ô phía dưới có thể nhận đường đi giả từ ô bị chặn.
10. **Nén bảng và duyệt sai chiều.** Với phụ thuộc trên/trái, phải duyệt trái sang phải khi tái sử dụng hàng.
11. **Dùng int/long cho số cách không có kiểm soát tràn.** Dùng BigInteger hoặc modulo theo hợp đồng.
12. **Áp modulo lên điểm tối ưu.** Có thể làm sai so sánh tốt/kém.
13. **Không tính bộ nhớ BigInteger khi phân tích bit.** O(C) vị trí trạng thái không phải O(C) bit.
14. **Bỏ điều kiện dừng hoặc thứ tự phụ thuộc.** Với DP trên đồ thị có chu trình, cần thuật toán chuyên biệt.
15. **Chỉ kiểm thử best.** Sai ở xử lý hòa có thể để best đúng nhưng ways sai.

Checklist trước khi nộp lời giải:

- [ ] Đã định nghĩa một **nghiệm phân biệt** theo đúng đề?
- [ ] Đã chọn rõ tối đa hóa hay tối thiểu hóa, trạng thái và trường hợp cơ sở?
- [ ] Đã tách trạng thái không thể đạt khỏi trạng thái có điểm 0?
- [ ] Nhánh tốt hơn **thay**, kém hơn **bỏ**, bằng nhau **cộng**?
- [ ] Có chứng minh hai nhánh hòa đại diện cho **hai nhóm nghiệm không giao nhau**?
- [ ] Thứ tự duyệt DP có bảo đảm các tiền nhiệm đã được tính?
- [ ] Khi nén bộ nhớ, đã dùng đúng trạng thái của hàng trước/hàng hiện tại?
- [ ] Đã chọn BigInteger hay modulo đúng yêu cầu và xử lý tràn điểm?
- [ ] Đã kiểm thử bằng liệt kê nghiệm ở đầu vào nhỏ, kể cả trường hợp hòa và không thể đạt?
- [ ] Đã báo cáo chi phí thời gian, số trạng thái và bộ nhớ đúng mô hình tính toán?

**Kết luận:** để đếm số lời giải tối ưu, trạng thái DP lưu **(giá trị tối ưu, số cách đạt giá trị ấy)**. Lựa chọn tốt hơn thay cả hai; lựa chọn kém hơn bị loại; lựa chọn bằng nhau cộng số cách — **chỉ khi các nhóm nghiệm không giao nhau**. Tách trạng thái không thể đạt, xử lý số đếm lớn và xác định rõ tính phân biệt của nghiệm là ba điều kiện giúp truy hồi đúng trên mọi trường hợp biên.

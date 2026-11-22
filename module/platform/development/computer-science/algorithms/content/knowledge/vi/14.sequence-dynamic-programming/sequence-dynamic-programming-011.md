# Đường đi trên bảng với các trạng thái bị chặn

**Đường đi trên bảng với các trạng thái bị chặn** là một dạng bài toán **quy hoạch động (dynamic programming, DP)**: các ô hoặc trạng thái được tổ chức thành bảng, một số vị trí không được phép sử dụng, và ta cần tính **số đường đi**, **khả năng tới đích**, **chi phí nhỏ nhất**, hoặc **một đường đi hợp lệ**. Dạng thường gặp nhất là bảng chữ nhật `R × C`, bắt đầu ở góc trên trái, kết thúc ở góc dưới phải, chỉ đi **sang phải** hoặc **xuống dưới**.

Khác với lưới không có vật cản, một trạng thái bị chặn phải **cắt mọi đường đi đi vào nó**. Khi tính DP, không được để giá trị cũ hoặc giá trị mặc định của ô ấy lan sang các ô sau. Đồng thời, cần phân biệt:

- **Ô bị chặn:** bản thân ô không hợp lệ để đứng hoặc đi qua.
- **Ô không bị chặn nhưng không thể đến:** ô hợp lệ về địa hình, nhưng mọi đường từ điểm xuất phát đều bị ngăn.
- **Ô có thể đến:** có ít nhất một đường hợp lệ từ điểm xuất phát tới ô.
- **Ô có đường đi nhưng chi phí cao:** với bài toán tối ưu, ô ấy hợp lệ dù không nằm trên đường tối ưu.

Bài này trình bày mô hình trạng thái, công thức chuyển, chứng minh đúng, xử lý biên, nén bộ nhớ, đếm số đường đi bằng `BigInteger`, tìm đường đi chi phí nhỏ nhất và phục dựng đường đi trong Java 17+. Trọng tâm là **đọc đúng trạng thái hợp lệ, không cho trạng thái bị chặn đóng góp vào đáp án**.

## 1. Đặc tả và giả thiết chuyển động

Cho bảng `blocked[R][C]`:

- `blocked[r][c] = true`: ô tại hàng `r`, cột `c` bị chặn, không được đi vào.
- `blocked[r][c] = false`: ô có thể sử dụng.
- Điểm xuất phát `S=(0,0)`, đích `T=(R-1,C-1)`.
- Một bước hợp lệ từ `(r,c)` chỉ đi đến **`(r,c+1)`** hoặc **`(r+1,c)`**, nếu ô đích nằm trong bảng và không bị chặn.
- Không đi lên, trái hoặc chéo; không đứng lại để tạo thêm đường đi.
- Mỗi đường đi là một **chuỗi bước** hợp lệ từ S đến T. Hai chuỗi bước khác nhau được tính là hai đường đi, ngay cả khi tổng chi phí bằng nhau.

Ví dụ:

```text
S  .  .
.  #  .
.  .  T

S = (0,0)
T = (2,2)
# = ô bị chặn
. = ô có thể đi
```

Có đúng hai đường đi hợp lệ:

```text
RRDD: (0,0) -> (0,1) -> (0,2) -> (1,2) -> (2,2)
DDRR: (0,0) -> (1,0) -> (2,0) -> (2,1) -> (2,2)
```

Ở đây `R` trong chuỗi bước nghĩa là **right** (sang phải), `D` nghĩa là **down** (xuống). Ký hiệu `R` trong `R × C` lại biểu thị **số hàng**; hai ý nghĩa được phân biệt theo ngữ cảnh.

Với lưới không có vật cản, mọi đường từ `(0,0)` tới `(R-1,C-1)` gồm đúng `R-1` bước xuống và `C-1` bước phải. Số cách là `binomial(R+C-2,R-1)`. Có vật cản thì **không thể chỉ dùng công thức này** mà bỏ qua vị trí bị chặn.

## 2. Định nghĩa trạng thái đếm đường đi

Đặt `ways[r][c]` là **số đường đi hợp lệ từ S đến ô `(r,c)`**, với giả thiết chỉ đi phải/xuống.

Công thức:

```text
Nếu ô (r,c) bị chặn:
    ways[r][c] = 0

Nếu (r,c) = (0,0) và không bị chặn:
    ways[0][0] = 1

Nếu (r,c) không bị chặn và khác S:
    ways[r][c] =
        (r > 0 ? ways[r-1][c] : 0)
      + (c > 0 ? ways[r][c-1] : 0)
```

**Vì sao cộng hai nguồn?** Mỗi đường đi tới ô `(r,c)` khác S có **bước cuối** từ đúng một trong hai ô:

1. Từ `(r-1,c)` đi xuống, nếu `r>0`.
2. Từ `(r,c-1)` đi sang phải, nếu `c>0`.

Hai tập đường này **không giao nhau** vì bước cuối khác nhau. Mỗi đường hợp lệ tới ô trước có thể nối thêm một bước vào ô hiện tại khi ô hiện tại không bị chặn. Do đó số đường đến ô hiện tại bằng **tổng** số đường từ hai ô trước. Nếu ô hiện tại bị chặn, **không đường nào được kết thúc hoặc đi xuyên qua ô đó**, nên giá trị phải là 0 bất kể hai ô trước có bao nhiêu đường.

**Vì sao khởi tạo bằng 1 ở S?** Có một cách bắt đầu tại S mà chưa thực hiện bước nào: **đường rỗng** tới chính điểm xuất phát. Giá trị 1 là đơn vị đếm giúp các ô cạnh S nhận đúng một đường đầu tiên. Nếu S bị chặn thì `ways[0][0]=0`, không phải 1.

## 3. Bảng ví dụ và cách điền

Xét lưới 3 × 3 có vật cản ở giữa:

```text
blocked:            ways:
.  .  .             1  1  1
.  #  .             1  0  1
.  .  .             1  1  2
```

Diễn giải theo thứ tự từ trên xuống dưới, trái sang phải:

- `ways[0][0]=1`: điểm bắt đầu không bị chặn.
- Hàng đầu không có nguồn từ trên, nên `ways[0][1]=1`, `ways[0][2]=1`.
- `ways[1][0]=1`: đến từ ô `(0,0)`.
- `ways[1][1]=0`: ô bị chặn; **không** cộng `ways[0][1]` và `ways[1][0]`.
- `ways[1][2]=ways[0][2]+ways[1][1]=1+0=1`.
- `ways[2][1]=ways[1][1]+ways[2][0]=0+1=1`.
- `ways[2][2]=ways[1][2]+ways[2][1]=1+1=2`.

Đáp án là **2** đường, đúng với hai chuỗi `RRDD` và `DDRR` ở trên. Điều này cũng minh họa rằng **trạng thái bị chặn không đóng góp đường đi cho trạng thái khác**.

### Không thể tới không đồng nghĩa bị chặn

Xét bảng:

```text
S  #  .
#  .  T
```

Các ô `(0,2)`, `(1,1)`, `(1,2)` không bị chặn nhưng đều **không có đường từ S tới**. Giá trị DP của chúng vẫn bằng **0**, trong khi `blocked=false`. Đừng biến mọi ô có `ways=0` thành vật cản: một trạng thái có thể hợp lệ nhưng không thể tiếp cận.

Tương tự, nếu đích không bị chặn nhưng mọi đường tới đích đều bị cắt, **số đường bằng 0**; đây không phải một lỗi tính toán.

## 4. Cài đặt DP hai chiều và bất biến

Giả mã:

```text
ALGORITHM COUNT_PATHS_2D(blocked)
    R <- number of rows
    C <- number of columns
    IF R = 0 OR C = 0 THEN RETURN 0 END IF

    CREATE ways[R][C] filled with 0

    FOR r FROM 0 TO R-1 DO
        FOR c FROM 0 TO C-1 DO
            IF blocked[r][c] THEN
                ways[r][c] <- 0
            ELSE IF r = 0 AND c = 0 THEN
                ways[r][c] <- 1
            ELSE
                up <- (r > 0) ? ways[r-1][c] : 0
                left <- (c > 0) ? ways[r][c-1] : 0
                ways[r][c] <- up + left
            END IF
        END FOR
    END FOR

    RETURN ways[R-1][C-1]
END ALGORITHM
```

**Bất biến khi điền bảng:** trước khi tính ô `(r,c)` theo thứ tự hàng trước, cột sau, mọi trạng thái từ **hàng trước** và từ **cột bên trái ở hàng hiện tại** đã có số đường đúng; các trạng thái bị chặn trong vùng đã xử lý đều có giá trị 0.

Mỗi ô chỉ phụ thuộc vào **phía trên** và **bên trái**, nên thứ tự duyệt là một **thứ tự topo** của đồ thị phụ thuộc. Không có đường đi nào quay về ô cũ vì tổng `r+c` tăng đúng 1 sau mỗi bước. Bởi vậy, quy hoạch động có thể giải trong **một lần duyệt**, không cần tìm kiếm lặp hoặc thuật toán đường đi tổng quát.

**Chứng minh đúng bằng quy nạp:** xét chỉ số `r+c`. Cơ sở là S, có một đường rỗng nếu không bị chặn. Giả sử tất cả ô có tổng chỉ số nhỏ hơn `r+c` đã đúng. Mỗi đường tới ô `(r,c)` không bị chặn có bước cuối duy nhất từ trên hoặc trái, hai ô này có tổng chỉ số nhỏ hơn. Tổng số đường đúng bằng công thức truy hồi. Nếu bị chặn, không thể tồn tại đường hợp lệ tới ô ấy, nên bằng 0. Quy nạp chứng minh mọi ô và đặc biệt ô đích đúng.

**Tính kết thúc:** hai vòng chạy qua hữu hạn `R*C` ô, không có đệ quy; thuật toán luôn dừng khi bảng hợp lệ.

## 5. Rút gọn bộ nhớ xuống một hàng

Để tính số đường tới ô `(r,c)`, ta chỉ cần giá trị **ô trên từ hàng trước** và **ô trái vừa tính ở hàng hiện tại**. Không cần lưu tất cả các hàng DP, nếu chỉ yêu cầu **số đường tới đích**.

Dùng mảng một chiều `ways[c]` dài C:

```text
ALGORITHM COUNT_PATHS_1D(blocked)
    R <- number of rows
    C <- number of columns
    IF R = 0 OR C = 0 THEN RETURN 0 END IF

    CREATE ways[0..C-1] filled with 0
    ways[0] <- 1

    FOR r FROM 0 TO R-1 DO
        FOR c FROM 0 TO C-1 DO
            IF blocked[r][c] THEN
                ways[c] <- 0
            ELSE IF c > 0 THEN
                ways[c] <- ways[c] + ways[c-1]
            END IF
        END FOR
    END FOR

    RETURN ways[C-1]
END ALGORITHM
```

**Vì sao hướng trái → phải bắt buộc trong công thức này?** Trước khi xử lý ô `(r,c)`:

- `ways[c]` còn giữ **số đường từ ô phía trên `(r-1,c)`** (hàng trước).
- `ways[c-1]` đã được xử lý trong **hàng hiện tại**, nên là số đường từ ô bên trái.
- Vì vậy `ways[c] += ways[c-1]` tương ứng với công thức 2D.

Khi gặp ô bị chặn, phải đặt **`ways[c]=0` ngay lập tức**, kể cả khi ô đó trước đây có nhiều đường từ hàng trên. Nếu chỉ `continue` mà không xóa ô, các ô ở hàng tiếp theo có thể đọc **số đường cũ từ một trạng thái giờ bị cấm** và đếm đường đi xuyên vật cản.

### Ví dụ trạng thái 1D

Với vật cản giữa lưới 3 × 3:

```text
Khởi tạo:         [1, 0, 0]
Sau hàng 0 (...): [1, 1, 1]
Sau hàng 1 (.#.): [1, 0, 1]
Sau hàng 2 (...): [1, 1, 2]
```

Trên hàng 1, tại cột 1 bị chặn, giá trị `ways[1]` trước đó là 1 nhưng **phải bị thay bằng 0**. Tại cột 2, phép tính dựa vào `ways[2]` của hàng trên (1) và `ways[1]` của hàng hiện tại (0), thu được 1.

**Độ phức tạp số học:** cả bản 2D và 1D đều thực hiện O(RC) ô DP, mỗi ô chỉ cộng tối đa hai số; bản 2D có O(RC) **vị trí lưu**, bản 1D có O(C). Nếu dùng số nguyên tùy ý như `BigInteger`, thời gian của một phép cộng và số bit cần lưu tăng theo độ lớn của số đường; vì thế O(RC) là **số bước/cộng số học**, không mặc định là số phép bit hằng thời gian.

## 6. Số đường có thể vượt giới hạn số nguyên

Khi không có vật cản, số đường từ góc trên trái tới góc dưới phải là:

```text
Choose(R + C - 2, R - 1)
```

Với bảng đủ lớn, giá trị này tăng rất nhanh và có thể vượt `int`, `long`. Đếm bằng `int` rồi tràn sẽ dẫn đến số âm hoặc số không chính xác, mặc dù công thức DP đúng.

Có ba lựa chọn theo đặc tả:

1. **Đếm chính xác:** dùng `java.math.BigInteger`. Đây là cách trong ví dụ Java bên dưới.
2. **Đếm theo modulo M:** nếu đề bài yêu cầu kết quả `count mod M`, thực hiện cộng có kiểm soát modulo M. Không tự thêm modulo khi bài cần giá trị chính xác.
3. **Bảo đảm giới hạn đầu vào:** chỉ dùng `long` nếu chứng minh/đặc tả bảo đảm kết quả không vượt giới hạn, hoặc kiểm tra tràn và báo lỗi phù hợp.

**Không dùng `double` để lưu số đường chính xác**, vì số nguyên lớn không được biểu diễn chính xác bằng kiểu số thực dấu phẩy động.

## 7. Khả năng đi đến đích: DP Boolean

Nếu bài chỉ hỏi **có tồn tại ít nhất một đường đi hay không**, ta không cần đếm chính xác mọi đường. Định nghĩa:

`reachable[r][c] = true` khi có đường hợp lệ từ S đến ô `(r,c)`.

Công thức:

```text
Nếu ô bị chặn:
    reachable[r][c] = false

Nếu ô là S và không bị chặn:
    reachable[0][0] = true

Nếu ô khác S không bị chặn:
    reachable[r][c] =
        (r > 0 AND reachable[r-1][c])
        OR
        (c > 0 AND reachable[r][c-1])
```

Đây là **cùng đồ thị phụ thuộc** với bài đếm, nhưng thay phép cộng số đường bằng **OR**. Với bài tồn tại đường, ô không thể tới và ô bị chặn đều có `reachable=false`; tuy nhiên, vẫn cần giữ **lưới blocked riêng** nếu phải phân biệt lý do.

Có thể nén Boolean DP xuống một hàng và quét trái → phải. Dù vậy, vì chỉ có hai hướng đi và trạng thái đơn điệu theo hàng/cột, việc dùng `BigInteger` để đếm rồi kiểm tra `count.signum()>0` cũng cho kết quả tồn tại đường — nhưng thường tốn tài nguyên hơn khi chỉ cần Boolean.

## 8. Đường đi chi phí nhỏ nhất với trạng thái bị chặn

Một biến thể quan trọng: mỗi ô không bị chặn `(r,c)` có **chi phí đi vào `cost[r][c]`**, và cần tìm đường từ S đến T có **tổng chi phí nhỏ nhất**. Trong bài này, chi phí là số nguyên **không âm** và **bao gồm chi phí của cả ô xuất phát lẫn ô đích**.

Định nghĩa `best[r][c]` là **chi phí nhỏ nhất của một đường hợp lệ** từ S đến `(r,c)`. Nếu không có đường hoặc ô bị chặn, dùng **UNREACHABLE** riêng; **không dùng 0**, vì chi phí tối ưu có thể thật sự bằng 0.

```text
Nếu ô (r,c) bị chặn:
    best[r][c] = UNREACHABLE

Nếu ô là S và không bị chặn:
    best[0][0] = cost[0][0]

Nếu ô khác S và không bị chặn:
    candidates <- all reachable predecessors
                  among best[r-1][c], best[r][c-1]

    IF candidates is empty THEN
        best[r][c] <- UNREACHABLE
    ELSE
        best[r][c] <- cost[r][c] + MIN(candidates)
    END IF
```

**Không cộng vào một giá trị vô cực bằng mã số mà không kiểm tra.** Ví dụ nếu dùng `Integer.MAX_VALUE` biểu diễn UNREACHABLE, phép `INF + cost` có thể tràn rồi tạo ra một số âm cực nhỏ, vô tình biến một ô không thể tới thành ô có đường rất “rẻ”. Mã Java dùng `null` **chỉ trong bảng nội bộ** để biểu diễn không tới được, và `BigInteger` cho chi phí để không phát sinh tràn số.

### Ví dụ với vật cản giữa

```text
blocked:           cost:
.  .  .            1  2  3
.  #  .            4  #  1
.  .  .            5  2  1
```

Chỉ có hai đường:

| Chuỗi bước | Các ô đi qua, tính cả S và T | Tổng chi phí |
| --- | --- | ---: |
| `RRDD` | `1 + 2 + 3 + 1 + 1` | **8** |
| `DDRR` | `1 + 4 + 5 + 2 + 1` | 13 |

Vậy chi phí nhỏ nhất là **8**, và một đường tối ưu là `RRDD`. Con số 8 **không phải số đường đi**; số đường đi ở cùng ví dụ là **2**. Không nhầm kết quả của DP đếm với DP tối ưu.

### Truy vết đường đi chi phí nhỏ nhất

Để xuất chuỗi bước, ta có thể lưu `parent[r][c]`:

- `'D'`: đến ô hiện tại **từ phía trên** (bước cuối đi xuống).
- `'R'`: đến ô hiện tại **từ bên trái** (bước cuối sang phải).
- Không có parent ở S, ô bị chặn và ô không thể tới.

Khi cả hai nguồn có cùng chi phí, chương trình chọn **nguồn trên trước** để kết quả xác định. Quy tắc này chỉ là phá hòa giữa các đường **đều tối ưu**, không ảnh hưởng tổng chi phí nhỏ nhất.

Từ T, lần theo parent về S và **đảo ngược** chuỗi bước đã ghi. Vì mỗi bước ngược giảm `r+c` đúng 1, quy trình chắc chắn kết thúc khi parent hợp lệ.

**Lưu ý quan trọng:** nén mảng chi phí xuống một hàng có thể giữ đúng **chi phí tối ưu**, nhưng nếu còn phải phục dựng một đường, không được tự động cho rằng giá trị cuối là đủ. Chương trình dưới đây giữ bảng `best` và `parent` 2D cho bài có yêu cầu xuất đường đi.

## 9. Chứng minh đúng của bài chi phí nhỏ nhất

Mọi đường tới ô `(r,c)` khác S đều đi từ ô trên hoặc ô trái ở bước cuối. Do đó một đường tới ô này có dạng:

`(đường tới một ô trước) + (bước đi vào ô hiện tại)`.

Trong mọi đường hợp lệ đến từ cùng một ô trước, nếu phần đường trước **không tối ưu**, ta có thể thay nó bằng đường tới ô trước có chi phí nhỏ hơn mà vẫn giữ bước cuối hợp lệ; tổng chi phí toàn đường giảm. Vì vậy, chỉ cần xét **chi phí tối ưu của mỗi ô trước**.

Với mỗi ô không bị chặn:

`best[r][c] = cost[r][c] + min(best[top],best[left])`

với min chỉ xét những nguồn **reachable**. Nếu không có nguồn nào reachable, ô hiện tại không thể tới. Đây là **cấu trúc con tối ưu (optimal substructure)**.

**Quy nạp theo r+c** tương tự bài đếm: S đúng theo định nghĩa; các ô phụ thuộc vào ô có tổng chỉ số nhỏ hơn đã được giải đúng; lựa chọn nhỏ nhất trong các nguồn hợp lệ tạo đường tối ưu. Vật cản có giá trị UNREACHABLE nên không được đi qua. Đến T, kết quả là chi phí tối ưu hoặc trạng thái không tồn tại đường.

Với di chuyển chỉ phải/xuống, đồ thị trạng thái là **DAG** vì mỗi bước tăng `r+c`. Bản DP không cần Dijkstra. Nếu cho phép đi **lên, xuống, trái, phải** thì có thể xuất hiện chu trình; công thức phụ thuộc chỉ trên/trái **không còn đủ**, và bài toán đường đi tối thiểu phải được giải bằng mô hình đồ thị/thủ tục phù hợp với trọng số và điều kiện bài toán.

## 10. Java 17+: đếm 2D, đếm 1D và tìm đường rẻ nhất

Chương trình đầy đủ sau sử dụng:

- `boolean[][] blocked` cho bản đồ vật cản.
- `BigInteger` cho số đường đi chính xác, kể cả khi vượt `long`.
- `BigInteger[][] best` và `char[][] parent` cho chi phí tối thiểu cùng một đường tối ưu.
- `Optional<Route>` cho kết quả có/không đường; không dùng một chi phí đặc biệt để giả vờ không có nghiệm.
- Kiểm tra bảng chữ nhật, ô `null`, chi phí không âm và kích thước tương ứng.
- Hướng quét từ trên xuống, trái sang phải; cập nhật ô bị chặn **trước** khi cộng/tối ưu.

Tạo tệp **`BlockedGridPathsDemo.java`**:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;
import java.util.Optional;

public class BlockedGridPathsDemo {
    record Route(BigInteger cost, String moves) {}

    private static int columns(boolean[][] blocked) {
        Objects.requireNonNull(blocked, "blocked");
        if (blocked.length == 0) {
            return 0;
        }
        Objects.requireNonNull(blocked[0], "row");
        int cols = blocked[0].length;
        for (boolean[] row : blocked) {
            Objects.requireNonNull(row, "row");
            if (row.length != cols) {
                throw new IllegalArgumentException("Ragged grid");
            }
        }
        return cols;
    }

    private static void validateCosts(
            boolean[][] blocked, long[][] costs, int cols) {
        Objects.requireNonNull(costs, "costs");
        if (costs.length != blocked.length) {
            throw new IllegalArgumentException("Row count mismatch");
        }
        for (long[] row : costs) {
            Objects.requireNonNull(row, "cost row");
            if (row.length != cols) {
                throw new IllegalArgumentException("Column count mismatch");
            }
            for (long cost : row) {
                if (cost < 0) {
                    throw new IllegalArgumentException("Negative cell cost");
                }
            }
        }
    }

    public static BigInteger countPaths2D(boolean[][] blocked) {
        int cols = columns(blocked);
        int rows = blocked.length;
        if (rows == 0 || cols == 0) {
            return BigInteger.ZERO;
        }

        BigInteger[][] dp = new BigInteger[rows][cols];

        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (blocked[r][c]) {
                    dp[r][c] = BigInteger.ZERO;
                } else if (r == 0 && c == 0) {
                    dp[r][c] = BigInteger.ONE;
                } else {
                    BigInteger fromUp =
                            r > 0 ? dp[r - 1][c] : BigInteger.ZERO;
                    BigInteger fromLeft =
                            c > 0 ? dp[r][c - 1] : BigInteger.ZERO;
                    dp[r][c] = fromUp.add(fromLeft);
                }
            }
        }
        return dp[rows - 1][cols - 1];
    }

    public static BigInteger countPaths1D(boolean[][] blocked) {
        int cols = columns(blocked);
        int rows = blocked.length;
        if (rows == 0 || cols == 0) {
            return BigInteger.ZERO;
        }

        BigInteger[] dp = new BigInteger[cols];
        Arrays.fill(dp, BigInteger.ZERO);
        dp[0] = BigInteger.ONE;

        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (blocked[r][c]) {
                    dp[c] = BigInteger.ZERO;
                } else if (c > 0) {
                    dp[c] = dp[c].add(dp[c - 1]);
                }
            }
        }
        return dp[cols - 1];
    }

    public static Optional<Route> cheapestPath(
            boolean[][] blocked, long[][] costs) {
        int cols = columns(blocked);
        validateCosts(blocked, costs, cols);
        int rows = blocked.length;

        if (rows == 0 || cols == 0 ||
                blocked[0][0] || blocked[rows - 1][cols - 1]) {
            return Optional.empty();
        }

        BigInteger[][] best = new BigInteger[rows][cols];
        char[][] parent = new char[rows][cols];

        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (blocked[r][c]) {
                    continue;
                }

                BigInteger current = BigInteger.valueOf(costs[r][c]);

                if (r == 0 && c == 0) {
                    best[r][c] = current;
                    continue;
                }

                BigInteger up = r > 0 ? best[r - 1][c] : null;
                BigInteger left = c > 0 ? best[r][c - 1] : null;

                if (up == null && left == null) {
                    continue; // Ô mở nhưng không thể đến.
                }

                if (up != null &&
                        (left == null || up.compareTo(left) <= 0)) {
                    best[r][c] = up.add(current);
                    parent[r][c] = 'D'; // Bước cuối đi xuống.
                } else {
                    best[r][c] = left.add(current);
                    parent[r][c] = 'R'; // Bước cuối sang phải.
                }
            }
        }

        if (best[rows - 1][cols - 1] == null) {
            return Optional.empty();
        }

        StringBuilder backwards = new StringBuilder();
        int r = rows - 1;
        int c = cols - 1;

        while (r != 0 || c != 0) {
            char step = parent[r][c];
            backwards.append(step);
            if (step == 'D') {
                r--;
            } else if (step == 'R') {
                c--;
            } else {
                throw new AssertionError("Broken parent chain");
            }
        }

        return Optional.of(new Route(
                best[rows - 1][cols - 1],
                backwards.reverse().toString()));
    }

    private static String show(Optional<Route> route) {
        if (route.isEmpty()) {
            return "none";
        }
        Route r = route.get();
        String moves = r.moves().isEmpty() ? "(empty)" : r.moves();
        return r.cost() + " moves=" + moves;
    }

    public static void main(String[] args) {
        boolean[][] centerBlocked = {
            {false, false, false},
            {false, true,  false},
            {false, false, false}
        };
        long[][] costs = {
            {1, 2, 3},
            {4, 0, 1},
            {5, 2, 1}
        };

        System.out.println("center2D=" + countPaths2D(centerBlocked));
        System.out.println("center1D=" + countPaths1D(centerBlocked));
        System.out.println("centerMin=" +
                show(cheapestPath(centerBlocked, costs)));

        boolean[][] noPath = {
            {false, true},
            {true, false}
        };
        long[][] noPathCost = {{1, 1}, {1, 1}};
        System.out.println("noPathCount=" + countPaths1D(noPath));
        System.out.println("noPathMin=" +
                show(cheapestPath(noPath, noPathCost)));

        boolean[][] startBlocked = {
            {true, false},
            {false, false}
        };
        System.out.println("startBlocked=" + countPaths1D(startBlocked));

        boolean[][] oneCell = {{false}};
        System.out.println("oneCellCount=" + countPaths2D(oneCell));
        System.out.println("oneCellMin=" +
                show(cheapestPath(oneCell, new long[][]{{7}})));

        System.out.println("emptyGrid=" +
                countPaths1D(new boolean[0][]));
        System.out.println("zeroColumns=" +
                countPaths2D(new boolean[][]{{}, {}}));

        boolean[][] tie = {{false, false}, {false, false}};
        long[][] tieCosts = {{1, 1}, {1, 1}};
        System.out.println("tieCount=" + countPaths1D(tie));
        System.out.println("tieMin=" +
                show(cheapestPath(tie, tieCosts)));
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac BlockedGridPathsDemo.java
java BlockedGridPathsDemo
```

**Đầu ra chính xác:**

```text
center2D=2
center1D=2
centerMin=8 moves=RRDD
noPathCount=0
noPathMin=none
startBlocked=0
oneCellCount=1
oneCellMin=7 moves=(empty)
emptyGrid=0
zeroColumns=0
tieCount=2
tieMin=3 moves=RD
```

### Giải thích các kết quả

- `center2D` và `center1D` đều bằng **2**: hai phiên bản lưu trữ khác nhau nhưng cùng công thức đếm.
- `centerMin=8 moves=RRDD`: đường phía trên chi phí 8, đường phía dưới chi phí 13; vì vậy chương trình chọn chuỗi `RRDD`.
- `noPathCount=0`: cả ô ngay bên phải và ngay phía dưới S đều bị chặn. Đích không bị chặn nhưng **không thể tiếp cận**; `cheapestPath` trả `none`.
- `startBlocked=0`: ô xuất phát không được đi vào, nên không có đường.
- `oneCellCount=1`: với bảng một ô không bị chặn, đường rỗng từ S đến chính T được tính là một đường. Chi phí tối ưu bằng chi phí ô duy nhất là 7, với `moves=(empty)`.
- `emptyGrid` và `zeroColumns` trả 0 vì không có ô bắt đầu và đích. Mã chấp nhận bảng không có hàng hoặc có hàng nhưng không có cột.
- `tieCount=2`: lưới 2 × 2 toàn ô mở có hai chuỗi `RD`, `DR`. Mọi chi phí ô đều là 1, nên chi phí nhỏ nhất bằng 3 cho cả hai. Vì phá hòa **ưu tiên nguồn trên**, chương trình phục dựng `RD`.

**Chi phí và giới hạn:** đếm hai chiều giữ O(RC) đối tượng `BigInteger`; đếm một chiều giữ O(C) tham chiếu `BigInteger`. Tìm đường tối ưu có phục dựng dùng O(RC) cho hai bảng `best` và `parent`. Phần đếm và tối ưu đều đi qua O(RC) ô; chi phí phép cộng số lớn phụ thuộc số bit của số đường/chi phí.

## 11. Khi một chiều chưa đủ để phục dựng đường

Đối với bài **chỉ đếm số cách** hoặc **chỉ tìm chi phí nhỏ nhất**, công thức dựa trên trên/trái cho phép nén về một hàng. Nhưng nếu cần xuất **đường đi cụ thể**, chỉ lưu mảng `best[c]` thường làm mất thông tin về **ô trước** đã tạo ra giá trị tối ưu ở các hàng cũ.

Những cách xử lý:

1. **Giữ bảng parent 2D**, như Java ở trên, cùng bảng chi phí hoặc với đủ thông tin để phục dựng.
2. **Lưu toàn bộ bảng DP** khi kích thước cho phép; từ ô đích truy ngược theo các trạng thái đạt công thức tối ưu.
3. **Tính lại các phần DP** khi phục dựng, đánh đổi thêm thời gian để giảm bộ nhớ; phải thiết kế/chứng minh riêng.
4. Nếu chỉ cần **một đường bất kỳ** thay vì đường tối ưu, có thể lưu predecessor tại lần đầu reachable cho từng ô, nhưng vẫn cần đủ thông tin để tái dựng đường; không được tự nhận rằng mảng đếm một chiều đã lưu sẵn đường.

**Không nhầm “có ít bộ nhớ” với “đủ dữ liệu cho mọi dạng đầu ra”.** Việc nén DP phải căn cứ đồng thời vào **công thức chuyển** và **kết quả mà đề bài yêu cầu xuất**.

## 12. Các trường hợp biên và biến thể

| Trường hợp | Đếm đường đi | Tìm chi phí nhỏ nhất |
| --- | --- | --- |
| Bảng rỗng hoặc 0 cột | 0 | Không có đường. |
| S hoặc T bị chặn | 0 | Không có đường. |
| Bảng 1 × 1, ô mở | 1 đường rỗng | Chi phí của chính ô đó. |
| Ô mở nhưng mọi đường đến đều bị chặn | 0 tại ô đó | UNREACHABLE tại ô đó. |
| Một hàng hoặc một cột, mọi ô mở | 1 | Tổng chi phí các ô trên đường duy nhất. |
| Tất cả ô mở | Hệ số tổ hợp `C(R+C-2,R-1)` | DP min từ trên/trái. |
| Có nhiều đường cùng rẻ nhất | Đếm mọi đường hợp lệ, không chỉ tối ưu | Phá hòa tùy quy tắc nếu cần xuất một đường. |
| Cho phép đi chéo | Cần thêm trạng thái `(r-1,c-1)` vào công thức | Cũng cần xét đường chéo và điều kiện ô hợp lệ. |
| Cho phép di chuyển bốn hướng | Công thức hai nguồn trên/trái không đủ | Mô hình đồ thị có thể có chu trình; chọn thuật toán phù hợp. |

### Vật cản động

Nếu một vật cản được thêm hoặc xóa **sau khi đã tính DP**, không thể chỉ sửa `ways[r][c]` ở ô đó rồi coi các ô phía sau vẫn đúng. Mọi trạng thái có thể **phụ thuộc** vào ô thay đổi có khả năng bị ảnh hưởng. Với bài chỉ đi phải/xuống, vùng ảnh hưởng nằm ở các ô có hàng/cột **không nhỏ hơn** tọa độ thay đổi, dù không phải ô nào cũng nhất thiết đổi giá trị.

Nếu có rất nhiều truy vấn bật/tắt vật cản, chạy lại O(RC) cho mỗi truy vấn có thể đắt. Khi ấy cần tìm cấu trúc dữ liệu hoặc thuật toán cập nhật phù hợp với kích thước, số truy vấn và dạng di chuyển. Không được áp dụng nguyên xi một bảng DP tĩnh cho dữ liệu đã thay đổi mà không cập nhật phụ thuộc.

### Nhiều điểm xuất phát hoặc đích

Nếu đề bài cho nhiều điểm bắt đầu, có thể khởi tạo số đường của mỗi nguồn phù hợp, nhưng cần xác định **có đếm đường đi độ dài 0 ở từng nguồn không**, có được đi qua các nguồn khác hay không, và liệu các nguồn có thể nhận đóng góp từ những nguồn phía trước không. Tương tự, nhiều điểm đích cần xác định cách tổng hợp đầu ra. Công thức cơ bản ở bài này giả định **duy nhất S=(0,0)** và **duy nhất T=(R-1,C-1)**.

## 13. Những lỗi phổ biến

1. **Không gán 0 khi gặp ô bị chặn.** Trong DP nén một hàng, giá trị còn lưu từ hàng trước có thể khiến thuật toán đếm đường xuyên vật cản.
2. **Khởi tạo S=1 dù S bị chặn.** Phải xét `blocked[0][0]`; nếu S bị chặn thì không có đường.
3. **Trả 1 với mọi bảng 1×1.** Chỉ đúng khi ô duy nhất không bị chặn; nếu bị chặn, số đường là 0.
4. **Không phân biệt ô bị chặn và ô không thể tới.** Cả hai có `ways=0`, nhưng tính hợp lệ về địa hình khác nhau.
5. **Cộng nhầm từ ô dưới hoặc ô phải** trong công thức từ S tới T khi chỉ được di chuyển xuống/phải.
6. **Duyệt một hàng 1D từ phải sang trái.** Ô `ways[c-1]` chưa phải giá trị hàng hiện tại, phá công thức.
7. **Đếm cả ô chéo** dù đề chỉ cho đi phải và xuống; sẽ thừa đường đi.
8. **Quên kiểm tra ranh giới hàng/cột**, dẫn đến chỉ số âm hoặc vượt mảng.
9. **Dùng 0 làm dấu UNREACHABLE trong bài chi phí.** Chi phí hợp lệ có thể bằng 0; phải dùng một trạng thái phân biệt.
10. **Cộng với INF không kiểm tra**, làm tràn số hoặc tạo “chi phí âm tốt nhất” từ trạng thái không thể tới.
11. **Dùng `int` cho số đường khi kết quả lớn** và âm thầm tràn.
12. **Nhầm số đường với chi phí đường đi**: cùng một bảng có thể có hai đường nhưng đường tối ưu chi phí 8.
13. **Bỏ qua chi phí ô xuất phát** khi đặc tả yêu cầu tính tất cả ô đi qua.
14. **Tuyên bố DP một chiều có thể phục dựng đường mà không lưu gì thêm.** Giá trị cuối không chứa đủ thông tin về các bước đã chọn.
15. **Cho phép đi bốn hướng nhưng vẫn dùng công thức DAG hai nguồn.** Khi có chu trình, công thức và thứ tự quét phải được xem lại.
16. **Không kiểm tra bảng ragged** (các hàng dài khác nhau) mà vẫn dùng `C=blocked[0].length`.
17. **Xử lý mỗi ô bị chặn như chỉ có chi phí rất cao**: một ô bị chặn là **không hợp lệ**, không phải được phép đi qua nếu không còn lựa chọn nào khác.

## 14. Bài tập tự luyện có lời giải

**Câu 1.** Với lưới 3 × 3 có ô giữa `(1,1)` bị chặn, chỉ đi phải/xuống, có bao nhiêu đường từ `(0,0)` tới `(2,2)`? **Đáp án:** 2 đường, `RRDD` và `DDRR`; không đường nào đi qua ô giữa.

**Câu 2.** Trong cùng lưới, vì sao `ways[1][1]=0` dù cả ô trên và ô trái đều có một đường? **Đáp án:** vì chính ô `(1,1)` bị chặn; không đường hợp lệ nào được đi vào ô đó.

**Câu 3.** Với `blocked=[[false,true],[true,false]]`, đích không bị chặn. Số đường bằng bao nhiêu? **Đáp án:** 0. Cả hai bước đầu tiên đều dẫn tới vật cản nên không thể rời S một cách hợp lệ.

**Câu 4.** Vì sao `ways[c]=0` ngay khi xử lý vật cản là bắt buộc trong bản một chiều? **Đáp án:** vì giá trị `ways[c]` còn chứa số đường của ô ở hàng trước; giữ nó sẽ lan những đường bị cấm qua các ô phía dưới hoặc bên phải.

**Câu 5.** Một bảng 1 × 1 có ô duy nhất mở. Số đường từ S tới T là bao nhiêu? **Đáp án:** 1 đường có 0 bước. Nếu ô ấy bị chặn, số đường bằng 0.

**Câu 6.** Bảng 3 × 4 không có vật cản, chỉ đi xuống/phải. Số đường là bao nhiêu? **Đáp án:** `C(5,2)=10`, vì phải chọn vị trí cho hai bước xuống trong tổng 5 bước.

**Câu 7.** Với bảng chi phí và vật cản giữa ở mục 8, tại sao đường rẻ nhất là `RRDD`? **Đáp án:** tổng `1+2+3+1+1=8`, còn đường `DDRR` có tổng `1+4+5+2+1=13`. Không có đường khác.

**Câu 8.** Nếu mọi ô có chi phí 0, có thể dùng `best=0` để biểu diễn không có đường? **Đáp án:** không. Một đường hợp lệ cũng có chi phí 0, nên cần UNREACHABLE riêng.

**Câu 9.** Nếu chỉ cần số đường chính xác trong bảng rất lớn, nên chọn kiểu số gì trong Java? **Đáp án:** `BigInteger` nếu không có giới hạn đủ nhỏ; nếu đề yêu cầu modulo thì làm đúng phép đếm modulo đã nêu.

**Câu 10.** Đếm bằng bảng 2D và một hàng 1D khác nhau về độ phức tạp ra sao? **Đáp án:** cùng O(RC) ô DP; bản 2D giữ O(RC) giá trị, bản 1D giữ O(C) giá trị, chưa tính độ dài bit của số lớn.

**Câu 11.** Một bài cho phép đi sang trái, phải, lên và xuống. Có thể dùng công thức `ways[r][c]=ways[r-1][c]+ways[r][c-1]` không? **Đáp án:** không. Đồ thị có thể có chu trình và có thêm nguồn đi vào ô; cần đặc tả “đường” có cho đi lại không và chọn mô hình thuật toán phù hợp.

**Câu 12.** Nếu đề yêu cầu **chuỗi bước của đường rẻ nhất**, chỉ giữ `best[c]` cuối cùng đủ không? **Đáp án:** không mặc nhiên. Cần lưu parent/đường truy vết hoặc tổ chức tính lại DP để phục dựng.

## 15. Checklist khi giải đường đi có trạng thái bị chặn

1. **Mô hình:** xác định số hàng/cột, ô bị chặn, ô xuất phát/đích, hướng di chuyển.
2. **Định nghĩa kết quả:** đếm đường, kiểm tra reachable, tối thiểu chi phí hay cần xuất một đường?
3. **Điều kiện khởi tạo:** S bị chặn phải cho 0 đường/không có đường; S hợp lệ có một đường rỗng tới chính nó.
4. **Công thức:** chỉ lấy từ **các trạng thái tiền nhiệm hợp lệ**. Đếm dùng cộng; tồn tại dùng OR; tối ưu dùng min.
5. **Vật cản:** đặt 0 cho đếm/false cho reachable/UNREACHABLE cho min; không cho giá trị cũ lan qua ô bị chặn.
6. **Thứ tự duyệt:** với chỉ đi phải/xuống, trên xuống và trái sang phải là thứ tự topo.
7. **Nén 1D:** đọc ô trên **hàng cũ** và ô trái **hàng mới**; cập nhật vật cản đúng lúc.
8. **Miền số:** số đường có thể vượt `long`; chi phí không thể tới phải có trạng thái riêng, tránh tràn.
9. **Phục dựng:** nếu cần đường đi, chuẩn bị parent hoặc chiến lược truy vết đúng từ đầu.
10. **Độ phức tạp:** đếm đủ thời gian O(RC) phép chuyển, bộ nhớ theo lựa chọn 2D/1D và chi phí số lớn.
11. **Kiểm thử biên:** rỗng, 1×1, chặn S/T, chặn cả hai bước đầu, không có vật cản, một hàng/cột và nhiều đường cùng tối ưu.

**Ghi nhớ:** DP trên bảng với vật cản đúng khi mỗi trạng thái được tính từ **những tiền nhiệm thật sự hợp lệ**, và **ô bị chặn không phát sinh hay chuyển tiếp đường đi**. Đếm bằng một hàng giúp tiết kiệm bộ nhớ, nhưng phải xóa giá trị ô bị chặn đúng lúc. Với bài toán tối ưu, cần phân biệt **chi phí 0** và **không có đường**, đồng thời lưu thông tin truy vết nếu đề bài yêu cầu xuất đường đi.

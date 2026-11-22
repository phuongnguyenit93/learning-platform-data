# Giải hệ tuyến tính bằng khử Gauss và chọn phần tử trụ

## 1. Bài toán: giải hệ phương trình tuyến tính

Một **hệ phương trình tuyến tính** có m phương trình và n ẩn x₁,x₂,…,xₙ được viết:

~~~text
a11*x1 + a12*x2 + ... + a1n*xn = b1
a21*x1 + a22*x2 + ... + a2n*xn = b2
...
am1*x1 + am2*x2 + ... + amn*xn = bm
~~~

Dạng ma trận là **A·x=b**, trong đó A có kích thước m×n, x có n thành phần và b có m thành phần. Mục tiêu không chỉ là tìm một dãy số: ta còn phải biết hệ **có nghiệm duy nhất, vô số nghiệm hay vô nghiệm**.

Ví dụ ba phương trình ba ẩn:

~~~text
 2x +  y - z =  8
-3x -  y +2z = -11
-2x +  y +2z = -3
~~~

Nghiệm là **(x,y,z)=(2,3,−1)**. Thay vào từng phương trình:

~~~text
2*2+3-(-1) = 8
-3*2-3+2*(-1) = -11
-2*2+3+2*(-1) = -3
~~~

**Khử Gauss (Gaussian elimination)** biến đổi hệ thành dạng tam giác hoặc **dạng bậc thang theo hàng (row echelon form)** rồi dùng **thế ngược (back substitution)** để tìm nghiệm. **Chọn phần tử trụ (pivoting)** giúp tránh chia cho 0 và giảm sai số số thực trong nhiều tình huống.

### Các giả định trong bài

- Hệ số và vế phải là số thực biểu diễn bằng `double` trong chương trình Java 17.
- Một input có thể là hệ vuông (m=n), thiếu phương trình (m<n), hoặc thừa phương trình (m>n).
- Trình tự biến trong mảng là x[0] đến x[n−1]. Hàng i chứa các hệ số của phương trình i.
- Chúng ta dùng **partial pivoting**: chỉ **đổi hàng**, không đổi cột/đổi vị trí ẩn.
- Mã sử dụng một ngưỡng `epsilon` để coi giá trị nhỏ là 0; vì thế phân loại nghiệm bằng `double` là **xấp xỉ số**, khác với chứng minh hạng chính xác trên số hữu tỉ.

## 2. Ma trận mở rộng [A|b]

Thay vì mang theo ký hiệu x,y,z trong mỗi bước, ghép hệ số với vế phải thành **ma trận mở rộng**:

~~~text
[  2   1  -1 |   8 ]
[ -3  -1   2 | -11 ]
[ -2   1   2 |  -3 ]
~~~

Mỗi hàng biểu diễn một phương trình. Vạch dọc phân biệt hệ số các ẩn với vế phải; trong mã Java, đây chỉ là cột cuối cùng `aug[row][n]`, không có phần tử riêng cho vạch dọc.

### Ba phép biến đổi sơ cấp bảo toàn tập nghiệm

1. **Đổi hai hàng:** hoán đổi thứ tự phương trình.
2. **Nhân một hàng với số khác 0:** đổi hệ số phương trình nhưng không đổi các nghiệm.
3. **Cộng một bội của hàng này vào hàng khác:** thay phương trình i bởi phương trình i cộng λ lần phương trình j.

Đó là các biến đổi hàng khả nghịch trong số học chính xác. Tập nghiệm của hệ không đổi, dù các hệ số trung gian trông khác hẳn.

**Không được** chỉ áp dụng phép biến đổi vào các cột hệ số mà quên cột b: như vậy bạn thay ma trận A nhưng giữ nguyên vế phải và đã tạo một hệ khác.

### Mục đích của khử Gauss

Sau các biến đổi, ta muốn có các phần tử trụ từ trái sang phải và những số 0 **bên dưới mỗi trụ**:

~~~text
[ p11  *    *    | * ]
[  0   p22  *    | * ]
[  0    0   p33  | * ]
~~~

Những hệ thiếu hạng có thể có **cột không có trụ**, hàng toàn 0, hoặc hàng mâu thuẫn `0 0 ... 0 | c` với c≠0. Không phải mọi hệ đều biến thành một ma trận tam giác có trụ trên tất cả đường chéo.

## 3. Chọn phần tử trụ và khử một cột

Đang ở hàng `pivotRow` và cột hệ số `col`. Một phần tử trụ hợp lệ phải **khác 0** trong số học chính xác; nếu không, không thể chia khi tính hệ số khử.

**Partial pivoting** chọn hàng `best` trong các hàng từ `pivotRow` tới m−1 có giá trị tuyệt đối tại cột `col` lớn nhất:

~~~text
best = argmax_{r=pivotRow..m-1} |aug[r][col]|
~~~

Nếu `|aug[best][col]|` lớn hơn ngưỡng đã chọn:

1. Đổi hàng `pivotRow` với `best`.
2. Với mỗi hàng r ở dưới, tính:

~~~text
factor = aug[r][col] / aug[pivotRow][col]
row[r] = row[r] - factor * row[pivotRow]
~~~

3. Đặt `aug[r][col]=0` (đó là phần tử đã được khử).
4. Tiếp tục sang cột kế và hàng trụ kế.

Nếu tất cả ứng viên tại cột gần 0 theo `epsilon`, **bỏ qua cột đó**; cột không có trụ có thể tương ứng với một **biến tự do** nếu hệ nhất quán.

### Vì sao chọn phần tử có trị tuyệt đối lớn?

Nếu trụ rất nhỏ, hệ số `factor` có thể rất lớn, làm khuếch đại sai số làm tròn. Khi chọn trị tuyệt đối lớn nhất trong cột, ta tránh dùng một trụ cực nhỏ nếu có ứng viên tốt hơn ngay bên dưới.

Ví dụ:

~~~text
0*x + 2*y = 4
1*x + 1*y = 3

[0 2 | 4]
[1 1 | 3]
~~~

Trụ tại (hàng 0,cột 0) bằng 0, nhưng cột này còn giá trị 1 ở hàng dưới. Đổi hàng:

~~~text
[1 1 | 3]
[0 2 | 4]
~~~

Từ hàng 2 suy ra y=2, thế ngược vào hàng 1: x=1. **Không kết luận vô nghiệm và cũng không chia cho trụ 0**.

### Chọn phần tử trụ không chỉ là tránh số 0

Kể cả khi trụ đầu khác 0, trụ lớn hơn ở hàng dưới vẫn có thể hữu ích. Trong hệ thực tế, nên có ít nhất **partial pivoting** thay vì cố giữ nguyên thứ tự phương trình.

Đổi hàng **không đổi thứ tự biến**. Nếu dùng **complete pivoting** (đổi cả cột), phải theo dõi hoán vị các ẩn để đưa nghiệm trở về đúng thứ tự ban đầu.

## 4. Truy vết hệ 3×3 có nghiệm duy nhất

Xét hệ:

~~~text
 2x +  y - z =  8
-3x -  y +2z = -11
-2x +  y +2z = -3
~~~

Ma trận mở rộng ban đầu:

~~~text
[  2   1  -1 |   8 ]
[ -3  -1   2 | -11 ]
[ -2   1   2 |  -3 ]
~~~

Ở cột x, giá trị tuyệt đối lớn nhất là 3 của hàng thứ hai. Đổi hàng 1 với hàng 2:

~~~text
[ -3  -1   2 | -11 ]
[  2   1  -1 |   8 ]
[ -2   1   2 |  -3 ]
~~~

Dùng hàng trụ khử x ở hai hàng dưới, thu được (các số dạng phân số nhằm tránh làm tròn):

~~~text
[ -3   -1     2   | -11   ]
[  0   1/3   1/3  |  2/3 ]
[  0   5/3   2/3  | 13/3 ]
~~~

Đến cột y, chọn hàng có trị tuyệt đối lớn hơn trong hai hàng cuối: **5/3** lớn hơn **1/3**, nên đổi hai hàng cuối:

~~~text
[ -3   -1     2   | -11   ]
[  0   5/3   2/3  | 13/3 ]
[  0   1/3   1/3  |  2/3 ]
~~~

Khử y ở hàng cuối theo hệ số (1/3)/(5/3)=1/5:

~~~text
[ -3   -1     2   | -11   ]
[  0   5/3   2/3  | 13/3 ]
[  0    0    1/5  | -1/5 ]
~~~

Thế ngược:

~~~text
(1/5)*z = -1/5                  => z = -1
(5/3)*y + (2/3)*z = 13/3        => y = 3
-3*x - y + 2*z = -11            => x = 2
~~~

Vậy nghiệm (2,3,−1) đúng cả theo thế ngược và khi thế vào hệ gốc. Ở mã Java, số thực trung gian có thể hiển thị khác phân số chính xác nhưng được làm tròn **chỉ khi in kết quả**, không làm tròn trong vòng khử.

## 5. Dạng bậc thang, cột trụ và biến tự do

Một hệ không nhất thiết có n trụ. Ví dụ hai phương trình ba ẩn:

~~~text
x + 2y - z = 3
2x +4y -2z = 6
~~~

Phương trình thứ hai chính là hai lần phương trình thứ nhất; chúng chỉ có **một điều kiện độc lập**. Sau khử:

~~~text
[2 4 -2 | 6]
[0 0  0 | 0]
~~~

Chỉ cột x (cột số 0) có trụ. Cột y và z không có trụ là **hai biến tự do**. Đặt y=s, z=t:

~~~text
x + 2s - t = 3

x = 3 - 2s + t
y = s
z = t
~~~

Có vô số nghiệm khi s,t chạy qua số thực. Đặt hai biến tự do bằng 0 cho một **nghiệm riêng**:

~~~text
(x,y,z) = (3,0,0)
~~~

Đó là nghiệm **hợp lệ nhưng không phải nghiệm duy nhất**. Một chương trình trả `(3,0,0)` mà không kèm trạng thái `INFINITE` sẽ gây hiểu nhầm.

### Các cột không có trụ phải được ghi nhớ

Với hệ m×n, một thuật toán đúng cho cả ma trận chữ nhật cần lưu `pivotColumns`. Nếu ở cột nào không tìm được trụ, ta **không tăng hàng trụ** ở cột đó, nhưng vẫn xét cột tiếp theo.

Ví dụ:

~~~text
0*x + 2*y + z = 5
0*x + 0*y + z = 1
~~~

Cột x không có trụ; trụ có thể nằm ở y và z. Nếu mã giả định trụ ở các cột 0,1,... liên tục thì việc thế ngược sẽ sai.

## 6. Phân biệt vô nghiệm, duy nhất và vô số nghiệm bằng hạng

**Hạng (rank)** của ma trận là số hàng (hoặc cột) độc lập tuyến tính. Trong phép khử chính xác, hạng của A là số trụ tìm được trong các cột hệ số.

Ký hiệu:

~~~text
rankA   = rank(A)
rankAug = rank([A|b])
n       = so an
~~~

Định lý **Rouché–Capelli** cho hệ tuyến tính:

| Điều kiện | Kết luận |
| --- | --- |
| rankA < rankAug | **Vô nghiệm** |
| rankA = rankAug = n | **Nghiệm duy nhất** |
| rankA = rankAug < n | **Vô số nghiệm** (trên trường số thực) |

Nếu có hàng:

~~~text
[0 0 ... 0 | c], c != 0
~~~

hàng đó biểu diễn `0=c`, mâu thuẫn. Vì ma trận mở rộng thêm đúng **một cột**, rankAug chỉ có thể bằng rankA hoặc rankA+1. Do đó có thể ghi `rankAug = rankA+1` ngay khi phát hiện một hàng mâu thuẫn.

### Ví dụ vô nghiệm

~~~text
x + 2y - z = 3
2x +4y -2z = 7
~~~

Hai vế trái phụ thuộc nhưng vế phải không theo tỷ lệ tương ứng. Khử cho:

~~~text
[2 4 -2 |  7]
[0 0  0 | -1/2]
~~~

Vì hàng cuối đòi 0=−1/2, hệ vô nghiệm; `rank(A)=1`, `rank([A|b])=2`.

### Ví dụ duy nhất dù có thừa phương trình

~~~text
x + y = 3
2x + 2y = 6
x - y = 1
~~~

Có m=3 phương trình, n=2 ẩn. Hàng thứ hai dư thừa, nhưng hai điều kiện độc lập đủ xác định nghiệm `(2,1)`. `rankA=rankAug=2=n`, nên **nghiệm duy nhất**.

### Ví dụ toàn bộ hệ số 0

~~~text
0*x+0*y=0
0*x+0*y=0
~~~

RankA=rankAug=0<n=2, nên mọi cặp (x,y) đều là nghiệm: vô số nghiệm. Nếu một vế phải đổi thành 1 thì rankAug=1>rankA, hệ vô nghiệm.

## 7. Giả mã khử Gauss với partial pivoting

Dưới đây là cách tổng quát cho m phương trình và n ẩn:

~~~text
solve(A,b,epsilon):
    aug = copy of [A|b]
    pivotRow = 0
    pivotCols = []

    for col = 0..n-1:
        if pivotRow == m:
            break

        best = row argmax abs(aug[r][col])
               for r in [pivotRow, m-1]

        if abs(aug[best][col]) <= epsilon:
            continue      // column has no pivot

        swap aug[pivotRow] and aug[best]
        pivotCols.push(col)

        for r = pivotRow+1..m-1:
            factor = aug[r][col] / aug[pivotRow][col]
            aug[r][col] = 0

            for j = col+1..n:   // include RHS column n
                aug[r][j] -= factor*aug[pivotRow][j]

        pivotRow++

    rankA = length(pivotCols)

    if exists row with all abs(coeff)<=epsilon
                      AND abs(rhs)>epsilon:
        return NO_SOLUTION

    solution[0..n-1] = 0  // free variables = 0

    for pivot index i from rankA-1 down to 0:
        col = pivotCols[i]
        value = aug[i][n]
        for j = col+1..n-1:
            value -= aug[i][j] * solution[j]

        solution[col] = value / aug[i][col]

    if rankA == n:
        return UNIQUE, solution
    else:
        return INFINITE, solution, pivotCols
~~~

Trong lý thuyết số học chính xác, phép kiểm “bằng 0” đúng nghĩa **bằng 0**. Trong bản Java `double`, `epsilon` là một quyết định ngưỡng; mã trả hạng **ước lượng** và cần kiểm tính phù hợp của ngưỡng với thang dữ liệu.

### Bất biến của vòng khử

Sau khi chọn k trụ:

- Những cột trụ đã xử lý có giá trị 0 ở các hàng **bên dưới hàng trụ**.
- Các cột trụ tăng dần từ trái qua phải.
- Mỗi phép đổi hàng và trừ bội hàng giữ nguyên tập nghiệm **trong số học chính xác**.
- Phần ma trận chưa khử nằm dưới và bên phải các trụ; không cần xét lại cột trụ đã hoàn thành.

Điểm hay bị bỏ sót là cột b nằm tại `aug[r][n]` **phải** được cập nhật trong vòng trong, vì đó là vế phải đã biến đổi.

## 8. Thế ngược và khôi phục nghiệm

Sau khi khử, hàng trụ thứ i có dạng:

~~~text
aug[i][pivotCols[i]] * x[pivotCols[i]]
 + sum over j>pivotCols[i] of aug[i][j]*x[j]
 = aug[i][n]
~~~

Vì những phần tử bên dưới các trụ đã bằng 0, giải từ **hàng trụ cuối về hàng trụ đầu**:

~~~text
x[pivotCols[i]] =
   (aug[i][n] -
    SUM_{j>pivotCols[i]} aug[i][j]*x[j])
   / aug[i][pivotCols[i]]
~~~

Nếu hệ thiếu hạng, ta được phép đặt biến tự do bằng 0 để tìm **một nghiệm riêng**. Nhưng cần ghi rõ số lượng biến tự do `n−rankA`; nếu nhiều hơn 0 và hệ nhất quán thì có vô số nghiệm.

### Nghiệm tổng quát và cơ sở không gian nghiệm thuần nhất

Trong đại số tuyến tính, với hệ nhất quán A·x=b, tập nghiệm có dạng:

~~~text
x = particular + z
A*z = 0
~~~

Không gian các z thỏa A·z=0 gọi là **null space (hạt nhân)** của A, có số chiều `n−rankA`.

Nếu muốn trả **mọi nghiệm** hoặc tham số hóa đầy đủ, cần xây một cơ sở null space, chẳng hạn đặt từng biến tự do lần lượt bằng 1, các biến tự do khác bằng 0 rồi thế ngược trong hệ thuần nhất. Mã Java bài này **chỉ trả một nghiệm riêng** và danh sách cột trụ; không tuyên bố đã trả sẵn mọi vectơ của cơ sở null space.

### Gauss–Jordan khác khử Gauss thường

- **Gaussian elimination:** khử các phần tử **bên dưới** trụ, rồi thế ngược.
- **Gauss–Jordan elimination:** khử cả **trên và dưới** trụ, thường chuẩn hóa trụ thành 1, để đạt dạng bậc thang rút gọn (RREF).

Cả hai dùng biến đổi hàng hợp lệ và có thể kết hợp pivoting, nhưng số thao tác và cách xây nghiệm khác nhau. Bài Java dùng Gaussian forward elimination + back substitution, không khử toàn bộ các phần tử phía trên trụ.

## 9. Java 17: chương trình tự chạy, hỗ trợ ma trận chữ nhật

Chương trình `GaussianPivotDemo.java` sử dụng:

- `solve(double[][] A,double[] b,int variables,double epsilon)`; số ẩn được truyền rõ để xử lý cả **0 phương trình** hoặc **0 ẩn**.
- `Status` phân biệt `UNIQUE`, `INFINITE`, `NO_SOLUTION`.
- `Result` chứa rankA, rankAugmented, pivotColumns, nghiệm riêng (nếu có), và số lần đổi hàng.
- Chọn hàng có trị tuyệt đối lớn nhất tại mỗi cột giữa những hàng chưa dùng.
- Không đổi thứ tự cột, nên nghiệm được trả theo thứ tự x[0]..x[n−1].
- Kiểm input hình chữ nhật, `NaN/Infinity`, epsilon dương, kích thước, phép khử tạo số không hữu hạn.
- Dùng `String.format(Locale.ROOT,"%.4f",...)` chỉ để in ổn định; thuật toán không làm tròn sau mỗi phép khử.
- Kiểm độc lập **625 ma trận nguyên 2×2** với các hệ số trong {−2,−1,0,1,2}, đối chiếu định thức và nghiệm đã cấy vào vế phải.

**Lưu toàn bộ mã bên dưới vào `GaussianPivotDemo.java`:**

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.StringJoiner;

public class GaussianPivotDemo {

    public enum Status {
        UNIQUE,
        INFINITE,
        NO_SOLUTION
    }

    public record Result(
            Status status,
            int rankA,
            int rankAugmented,
            int[] pivotColumns,
            double[] particular,
            int rowSwaps) {}

    private static void validate(
            double[][] a, double[] b,
            int n, double epsilon) {

        if (a == null || b == null) {
            throw new IllegalArgumentException("null matrix or rhs");
        }
        if (n < 0 || n == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("invalid variable count");
        }
        if (!Double.isFinite(epsilon) || epsilon <= 0.0) {
            throw new IllegalArgumentException("invalid epsilon");
        }
        if (a.length != b.length) {
            throw new IllegalArgumentException("row count mismatch");
        }

        for (int i = 0; i < a.length; i++) {
            if (a[i] == null || a[i].length != n) {
                throw new IllegalArgumentException("ragged matrix");
            }
            if (!Double.isFinite(b[i])) {
                throw new IllegalArgumentException("non-finite rhs");
            }
            for (double v : a[i]) {
                if (!Double.isFinite(v)) {
                    throw new IllegalArgumentException(
                            "non-finite coefficient");
                }
            }
        }
    }

    public static Result solve(
            double[][] a, double[] b,
            int n, double epsilon) {

        validate(a, b, n, epsilon);
        int m = a.length;

        // Work on a copy, preserve caller's A and b.
        double[][] aug = new double[m][n + 1];
        for (int i = 0; i < m; i++) {
            System.arraycopy(a[i], 0, aug[i], 0, n);
            aug[i][n] = b[i];
        }

        int[] pivots = new int[Math.min(m, n)];
        int rank = 0;
        int swaps = 0;

        for (int col = 0; col < n && rank < m; col++) {
            // Partial pivoting: largest |entry| among unused rows.
            int best = rank;
            for (int r = rank + 1; r < m; r++) {
                if (Math.abs(aug[r][col])
                        > Math.abs(aug[best][col])) {
                    best = r;
                }
            }

            if (Math.abs(aug[best][col]) <= epsilon) {
                continue; // no pivot in this column
            }

            if (best != rank) {
                double[] tmp = aug[rank];
                aug[rank] = aug[best];
                aug[best] = tmp;
                swaps++;
            }

            pivots[rank] = col;
            double pivot = aug[rank][col];

            for (int r = rank + 1; r < m; r++) {
                double factor = aug[r][col] / pivot;
                aug[r][col] = 0.0;

                // Include the last column (RHS) in elimination.
                for (int j = col + 1; j <= n; j++) {
                    aug[r][j] -= factor * aug[rank][j];
                    if (!Double.isFinite(aug[r][j])) {
                        throw new ArithmeticException(
                                "non-finite elimination value");
                    }
                }
            }
            rank++;
        }

        int[] pivotCols = Arrays.copyOf(pivots, rank);

        // A zero coefficient row with nonzero RHS is 0 = c.
        boolean inconsistent = false;
        for (int r = 0; r < m; r++) {
            boolean allZero = true;
            for (int col = 0; col < n; col++) {
                if (Math.abs(aug[r][col]) > epsilon) {
                    allZero = false;
                    break;
                }
            }
            if (allZero && Math.abs(aug[r][n]) > epsilon) {
                inconsistent = true;
                break;
            }
        }

        if (inconsistent) {
            return new Result(
                    Status.NO_SOLUTION, rank, rank + 1,
                    pivotCols, null, swaps);
        }

        // Set all free variables to 0, then back substitute.
        double[] x = new double[n];
        for (int i = rank - 1; i >= 0; i--) {
            int col = pivotCols[i];
            double value = aug[i][n];

            for (int j = col + 1; j < n; j++) {
                value -= aug[i][j] * x[j];
            }

            x[col] = value / aug[i][col];
            if (!Double.isFinite(x[col])) {
                throw new ArithmeticException(
                        "non-finite solution value");
            }
            if (Math.abs(x[col]) <= epsilon) {
                x[col] = 0.0;
            }
        }

        return new Result(
                rank == n ? Status.UNIQUE : Status.INFINITE,
                rank, rank, pivotCols, x, swaps);
    }

    private static String showVector(double[] x) {
        if (x == null) {
            return "none";
        }
        StringJoiner joiner = new StringJoiner(", ", "[", "]");
        for (double value : x) {
            if (Math.abs(value) < 1e-10) {
                value = 0.0;
            }
            joiner.add(String.format(Locale.ROOT, "%.4f", value));
        }
        return joiner.toString();
    }

    private static void show(String name, Result result) {
        System.out.println(
                name + ": " + result.status()
                + ", ranks=" + result.rankA()
                + "/" + result.rankAugmented()
                + ", pivots="
                + Arrays.toString(result.pivotColumns())
                + ", x=" + showVector(result.particular()));
    }

    private static double residualInfinity(
            double[][] a, double[] b, double[] x) {
        double worst = 0.0;
        for (int i = 0; i < a.length; i++) {
            double sum = 0.0;
            for (int j = 0; j < x.length; j++) {
                sum += a[i][j] * x[j];
            }
            worst = Math.max(worst, Math.abs(sum - b[i]));
        }
        return worst;
    }

    private static int verifyAllSmallMatrices() {
        int checked = 0;
        int nonsingular = 0;
        int singular = 0;
        double eps = 1e-10;

        for (int aa = -2; aa <= 2; aa++) {
            for (int ab = -2; ab <= 2; ab++) {
                for (int ba = -2; ba <= 2; ba++) {
                    for (int bb = -2; bb <= 2; bb++) {
                        double[][] a = {
                                {aa, ab}, {ba, bb}
                        };
                        // Construct b from the known x=(2,-1).
                        double[] b = {
                                2.0 * aa - ab,
                                2.0 * ba - bb
                        };

                        Result result = solve(a, b, 2, eps);
                        int det = aa * bb - ab * ba;

                        if (det != 0) {
                            nonsingular++;
                            if (result.status() != Status.UNIQUE
                                    || Math.abs(
                                        result.particular()[0] - 2) > 1e-7
                                    || Math.abs(
                                        result.particular()[1] + 1) > 1e-7) {
                                throw new AssertionError(
                                        "Unexpected unique result");
                            }
                        } else {
                            singular++;
                            if (result.status() != Status.INFINITE) {
                                throw new AssertionError(
                                        "Unexpected singular result");
                            }
                        }

                        if (residualInfinity(a, b,
                                result.particular()) > 1e-8) {
                            throw new AssertionError("Residual mismatch");
                        }
                        checked++;
                    }
                }
            }
        }

        if (nonsingular != 496 || singular != 129) {
            throw new AssertionError("Determinant counts differ");
        }
        return checked;
    }

    public static void main(String[] args) {
        double eps = 1e-10;

        double[][] uniqueA = {
                { 2,  1, -1},
                {-3, -1,  2},
                {-2,  1,  2}
        };
        double[] uniqueB = {8, -11, -3};
        Result unique = solve(uniqueA, uniqueB, 3, eps);
        show("unique", unique);
        System.out.println("unique residual <= 1e-8: "
                + (residualInfinity(
                        uniqueA, uniqueB, unique.particular()) <= 1e-8));

        Result swap = solve(
                new double[][] {{0, 2}, {1, 1}},
                new double[] {4, 3}, 2, eps);
        show("zero initial pivot", swap);
        System.out.println("zero-pivot row swaps = "
                + swap.rowSwaps());

        double[][] dependent = {
                {1, 2, -1},
                {2, 4, -2}
        };
        show("infinite", solve(
                dependent, new double[] {3, 6}, 3, eps));
        show("inconsistent", solve(
                dependent, new double[] {3, 7}, 3, eps));

        show("overdetermined", solve(
                new double[][] {
                    {1, 1},
                    {2, 2},
                    {1, -1}
                },
                new double[] {3, 6, 1}, 2, eps));

        show("all-zero equations", solve(
                new double[][] {
                    {0, 0},
                    {0, 0}
                },
                new double[] {0, 0}, 2, eps));

        show("zero variables", solve(
                new double[][] {{}, {}},
                new double[] {0, 0}, 0, eps));
        show("zero-variable contradiction", solve(
                new double[][] {{}, {}},
                new double[] {0, 1}, 0, eps));

        show("no equations", solve(
                new double[0][0], new double[0], 2, eps));

        System.out.println(
                "small 2x2 systems checked = "
                + verifyAllSmallMatrices());
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac GaussianPivotDemo.java
java GaussianPivotDemo
~~~

**Stdout chính xác:**

~~~text
unique: UNIQUE, ranks=3/3, pivots=[0, 1, 2], x=[2.0000, 3.0000, -1.0000]
unique residual <= 1e-8: true
zero initial pivot: UNIQUE, ranks=2/2, pivots=[0, 1], x=[1.0000, 2.0000]
zero-pivot row swaps = 1
infinite: INFINITE, ranks=1/1, pivots=[0], x=[3.0000, 0.0000, 0.0000]
inconsistent: NO_SOLUTION, ranks=1/2, pivots=[0], x=none
overdetermined: UNIQUE, ranks=2/2, pivots=[0, 1], x=[2.0000, 1.0000]
all-zero equations: INFINITE, ranks=0/0, pivots=[], x=[0.0000, 0.0000]
zero variables: UNIQUE, ranks=0/0, pivots=[], x=[]
zero-variable contradiction: NO_SOLUTION, ranks=0/1, pivots=[], x=none
no equations: INFINITE, ranks=0/0, pivots=[], x=[0.0000, 0.0000]
small 2x2 systems checked = 625
~~~

### Giải thích output

- `unique` tìm đúng nghiệm (2,3,−1) và phần dư rất nhỏ.
- `zero initial pivot` buộc **đổi hàng** vì phần tử ở hàng đầu, cột đầu bằng 0; kết quả là (1,2), một lần đổi hàng.
- `infinite` có rank 1 nhỏ hơn 3; trả nghiệm riêng (3,0,0), nhưng còn hai biến tự do.
- `inconsistent` có rank(A)=1, rank([A|b])=2 và không có nghiệm.
- `overdetermined` có 3 phương trình, 2 ẩn, song rank=2 nên nghiệm duy nhất (2,1).
- Hệ toàn 0 với hai ẩn có vô số nghiệm; khi số ẩn bằng 0 mà mọi vế phải bằng 0, nghiệm rỗng `[]` là **duy nhất** trong không gian R⁰.
- Nếu số ẩn bằng 0 và có một phương trình `0=1`, hệ vô nghiệm.
- Nếu không có phương trình mà vẫn có hai ẩn, mọi cặp là nghiệm; mã trả nghiệm riêng (0,0).

### Điều gì đã được kiểm tự động?

Hàm `verifyAllSmallMatrices` duyệt mọi ma trận 2×2 có bốn hệ số thuộc {−2,−1,0,1,2}: có 5⁴=625 ma trận.

Với mỗi A, mã tạo b=A·(2,−1), nên **hệ nhất quán**. Một oracle hoàn toàn độc lập từ định thức 2×2:

~~~text
det(A) = a00*a11 - a01*a10

det != 0 -> unique
det == 0 -> infinite (because b was constructed as A*x)
~~~

Trong 625 ma trận có **496 ma trận không suy biến** và **129 ma trận suy biến**. Khi hệ có nghiệm duy nhất, nghiệm phải gần (2,−1); khi hệ vô số nghiệm, nghiệm riêng phải thỏa A·x≈b. Mã kiểm sai số phần dư không quá 1e−8 rồi mới in số ca.

Kiểm thử là đối chứng tốt cho **cách cài cụ thể**, nhưng không thay thế chứng minh phép biến đổi hàng bảo toàn nghiệm hoặc các giới hạn của số học double.

## 10. Chứng minh tính đúng của khử Gauss

Lập luận ở đây nói về **số học chính xác** trước, sau đó mới bàn tới sai số thực tế của double.

**Mệnh đề 1 – Mỗi bước bảo toàn tập nghiệm.** Đổi hàng chỉ đổi thứ tự các phương trình. Thêm bội của một phương trình vào phương trình khác là phép biến đổi có phép đảo (trừ lại đúng bội ấy). Do đó nếu x giải hệ ban đầu, x giải hệ sau biến đổi và ngược lại.

**Mệnh đề 2 – Sau k trụ, các phần tử dưới từng trụ bằng 0.** Ở cột trụ col, hàng r dưới trụ được cập nhật:

~~~text
newAug[r][col] =
  aug[r][col] -
  (aug[r][col]/aug[pivotRow][col]) *
  aug[pivotRow][col]
= 0
~~~

Các cột trụ trước đó đã bằng 0 ở các hàng dưới trụ, và phép cập nhật dùng hàng trụ ở vùng phù hợp không phá hỏng cấu trúc đã khử.

**Mệnh đề 3 – Phân loại theo hạng.** Nếu có hàng `0 0 ... 0 | c` (c≠0), hệ tương đương chứa phương trình bất khả thi `0=c`, nên vô nghiệm. Nếu không có hàng mâu thuẫn, các hàng trụ tạo các phương trình độc lập. Khi mọi biến có cột trụ, nghiệm được xác định duy nhất. Khi thiếu cột trụ, các biến tương ứng tự do; trên R, có vô số lựa chọn cho các biến tự do và nghiệm tương ứng được khôi phục bằng thế ngược.

**Mệnh đề 4 – Thế ngược đúng.** Ở hàng trụ cuối, các biến bên phải đã biết (hoặc được đặt 0 nếu là biến tự do), nên giải đúng biến trụ cuối. Tiếp tục ngược lên theo quy nạp, mọi hàng trụ đều được thỏa. Các hàng không có trụ đều là `0=0` nếu hệ nhất quán; vậy nghiệm thu được thỏa toàn hệ đã khử, cũng như hệ ban đầu nhờ mệnh đề 1.

Suy ra thuật toán Gaussian elimination với chọn các trụ khác 0 và các phép tính chính xác giải đúng hệ tuyến tính hoặc phân loại đúng ba trạng thái nghiệm.

## 11. Phân tích độ phức tạp

Gọi m là số phương trình, n là số ẩn, r là số trụ được chọn, với `r<=min(m,n)`.

- Sao chép m×n hệ số và b: **O(mn+m)** thời gian/bộ nhớ.
- Với mỗi cột, tìm hàng trụ bằng quét các hàng còn lại: tối đa **O(mn)** phép so sánh.
- Mỗi trụ có thể khử tối đa m−1 hàng dưới, mỗi hàng cập nhật tối đa n+1 phần tử: **O(mnr)** cận trên.
- Thế ngược r hàng, mỗi hàng đọc tối đa n hệ số: **O(nr)**.
- Kiểm hàng mâu thuẫn: **O(mn)**.
- Bộ nhớ sao chép ma trận mở rộng: **O(m(n+1))**; thêm nghiệm O(n), pivotColumns O(r).

Với m,n≥1, thời gian cận trên thường viết:

~~~text
O(m*n*min(m,n))
~~~

Khi m=n=N, trở thành **O(N³)** thời gian và **O(N²)** bộ nhớ. Nếu m=0 hoặc n=0, cần xét trực tiếp các thao tác khởi tạo và phân loại; không diễn đạt cận bằng biểu thức nhân với 0 rồi hiểu là tổng công việc bằng 0.

Nếu cần giải nhiều hệ với **cùng A nhưng nhiều vế phải b**, không nên khử A từ đầu cho từng b nếu bài lớn. Có thể phân tích một lần bằng phân rã **LU với pivoting**, rồi giải tam giác cho từng vế phải; phần này vượt ra ngoài mã khử đơn lẻ của bài.

### Độ phức tạp phép toán số học

Mô hình O(N³) giả định cộng/trừ/nhân/chia hệ số có chi phí O(1). Nếu dùng phân số hữu tỉ hoặc BigInteger để tránh sai số, kích thước tử/mẫu có thể tăng và chi phí phép toán không còn hằng số.

## 12. Chọn trụ: không chọn, partial, scaled và complete

### Không chọn trụ

Dùng phần tử hiện tại trên đường chéo mà không đổi hàng. Nếu nó bằng 0, chương trình có thể chia cho 0 dù hệ thực tế có nghiệm duy nhất. Nếu nó rất nhỏ, sai số có thể bùng lên.

### Partial pivoting

Đổi hàng để chọn **trị tuyệt đối lớn nhất trong một cột**, chỉ xét những hàng chưa có trụ. Đây là lựa chọn thường dùng trong giải hệ `double` vì tương đối đơn giản và cải thiện tính ổn định số trong nhiều bài.

### Scaled partial pivoting

Một biến thể xét **tỷ lệ** giữa |a[r][col]| và một thang đo của hàng (ví dụ max trị tuyệt đối các hệ số của hàng) để tránh ưu tiên hàng có giá trị lớn chỉ vì toàn bộ hàng được nhân với một hệ số rất lớn.

Khi dùng scaled pivoting, phải xác định rõ chuẩn hàng, xử lý hàng toàn 0 và theo dõi thang sau các biến đổi. Không thay tên một phép chọn |entry| lớn nhất thành “scaled” nếu chưa thực sự chia cho thang đo.

### Complete pivoting

Chọn phần tử có trị tuyệt đối lớn nhất trong **toàn bộ khối ma trận chưa khử**, có thể đổi cả hàng và cột. Vì đổi cột tương ứng **đổi thứ tự biến**, cần lưu hoán vị cột và giải hoán vị khi trả nghiệm.

**Mã Java trong bài chỉ có partial pivoting.** Nó không theo dõi hoán vị cột và không nên áp dụng trực tiếp cho complete pivoting.

### Pivoting không chữa được mọi bài gần suy biến

Một ma trận **ill-conditioned** vẫn có thể cho nghiệm nhạy mạnh với sai số, ngay cả khi dùng partial pivoting. Cần phân biệt ổn định của thuật toán và độ nhạy vốn có của bài toán.

## 13. Epsilon, chuẩn hóa và hệ gần suy biến

Trong **số học chính xác**, một phần tử là trụ hợp lệ khi khác 0. Trong `double`, một số gần 0 có thể là kết quả làm tròn hoặc một trụ thực sự rất nhỏ.

Mã Java dùng ngưỡng tuyệt đối:

~~~text
abs(value) <= epsilon
=> xu ly nhu gia tri 0
~~~

Điều này dễ hiểu và hữu ích cho ví dụ số nhỏ, nhưng **phụ thuộc thang đo**. Cùng một hệ khi nhân toàn bộ một phương trình với 10^−12 có thể thay đổi việc trụ bị xem là 0 nếu giữ epsilon=10^−10.

### Ví dụ sai phân loại do epsilon lớn

Xét hệ:

~~~text
x + y = 2
x + (1+10^(-12))*y = 2+10^(-12)
~~~

Định thức toán học bằng 10^−12, nên hệ có nghiệm **duy nhất (1,1)**. Nhưng khi khử bằng double và dùng `epsilon=10^−10`, trụ thứ hai có độ lớn khoảng 10^−12, nhỏ hơn ngưỡng; thuật toán có thể **ước lượng rank=1** và gọi hệ là vô số nghiệm.

Đây là giới hạn của **quy tắc ngưỡng**, không phải bằng chứng hệ đại số có vô số nghiệm. Với dữ liệu đã làm tròn thành các số thực quá gần nhau, tình trạng có thể còn khó hơn.

### Ngưỡng tương đối và chuẩn ma trận

Với input không đồng nhất về tỷ lệ, nên cân nhắc ngưỡng phụ thuộc chuẩn ma trận hoặc chuẩn cột/hàng, ví dụ `epsilonRelative * scale` đi kèm ngưỡng tuyệt đối trong một chính sách được thiết kế rõ. Thêm ngưỡng tương đối tùy tiện cũng có thể sai đối với các hàng có độ lớn chênh lệch cực lớn.

Trong ứng dụng số nghiêm túc, lựa chọn rank và phát hiện suy biến thường cần xem xét **SVD/QR**, condition number và tolerance theo bài toán, thay vì chỉ một con số epsilon cố định.

### Sai số phần dư khác sai số nghiệm

**Residual** của một nghiệm x là:

~~~text
r = A*x - b
||r||_infinity = max_i abs(r[i])
~~~

Residual nhỏ nghĩa là x gần thỏa các phương trình. Nó **không bảo đảm** x gần nghiệm toán học thật nếu A rất ill-conditioned. Một thay đổi cực nhỏ ở b có thể làm nghiệm thay đổi rất lớn.

Vì vậy báo cáo tốt nên ghi cả trạng thái nghiệm, rank ước lượng, các trụ và residual. Với yêu cầu chính xác cao, thêm kiểm tra condition/scale khi có thể.

## 14. Ma trận chữ nhật và các trường hợp biên

### Hệ thiếu phương trình (m<n)

Hai phương trình ba ẩn **không thể có nghiệm duy nhất** trên trường số thực nếu cả hai độc lập: rank≤m<n. Nó có thể **vô nghiệm hoặc vô số nghiệm**. Ví dụ phụ thuộc ở phần 5 có vô số nghiệm.

### Hệ thừa phương trình (m>n)

Hệ có thể vô nghiệm nếu các phương trình mâu thuẫn; nếu nhất quán và `rankA=n`, nó **có nghiệm duy nhất**. Nếu nhất quán nhưng rank<n, có vô số nghiệm.

### Hàng toàn 0

Hàng `0 0 ... 0 | 0` không tạo thêm ràng buộc. Hàng `0 0 ... 0 | c` với c khác 0 là mâu thuẫn. Hãy kiểm **vế phải** trước khi kết luận dựa vào hàng hệ số toàn 0.

### Không có phương trình (m=0)

Nếu còn n>0 ẩn, không có ràng buộc nên có vô số nghiệm; có thể trả nghiệm riêng toàn 0. Nếu m=n=0, không gian không có ẩn có đúng một bộ giá trị rỗng, nên nghiệm `[]` là duy nhất theo quy ước đại số.

### Không có ẩn (n=0)

Mọi phương trình trở thành `0=b[i]`. Nếu tất cả b[i]=0, nghiệm rỗng `[]` là duy nhất. Nếu có b[i] khác 0 thì vô nghiệm. Truyền n tường minh giúp chương trình hỗ trợ những ca này.

### Input không phải hình chữ nhật

Nếu một hàng có số cột khác n, hệ không có mô tả ma trận m×n nhất quán. Mã Java ném `IllegalArgumentException` thay vì tự điền số 0 hoặc đọc ngoài mảng.

### Dữ liệu không hữu hạn

`NaN` và `Infinity` không phải hệ số thực hữu hạn hợp lệ của mô hình đang dùng. Mã từ chối chúng để tránh phép chọn trụ có thứ tự không xác định hoặc phép khử lan truyền NaN.

## 15. So sánh với các cách giải khác

| Phương pháp | Phù hợp khi | Điểm cần lưu ý |
| --- | --- | --- |
| Thế trực tiếp | Hệ rất nhỏ hoặc cấu trúc đặc biệt | Không tổng quát khi n lớn |
| Quy tắc Cramer | Hệ vuông không suy biến rất nhỏ, mục tiêu lý thuyết | Đòi định thức; không phù hợp tính n lớn |
| Khử Gauss + pivot | Hệ dense vừa/nhỏ, một vế phải | O(N³), cần xử lý near-zero |
| Gauss–Jordan | Muốn RREF, dễ đọc nghiệm tổng quát | Khử cả trên và dưới |
| LU với pivot | Nhiều vế phải cùng A | Phân tích một lần, thế hai hệ tam giác |
| QR | Least squares, hệ thừa phương trình gần đủ hạng | Thường ổn định hơn normal equations |
| SVD | Rank, hệ gần suy biến, nghiệm tối thiểu norm | Tốn chi phí hơn nhưng có thông tin singular values |
| Cholesky | A đối xứng xác định dương | Cần đúng điều kiện của A |
| Khử modulo p | Hệ trên trường hữu hạn modulo nguyên tố | Dùng nghịch đảo modulo, không dùng double |
| Khử trên phân số | Đòi nghiệm hữu tỉ chính xác | Tử/mẫu có thể rất lớn |

### Least squares không phải giải đúng Ax=b

Nếu m>n và hệ vô nghiệm, có thể tìm x làm **tổng bình phương phần dư nhỏ nhất**. Đó là bài toán **least squares**, khác với “có x sao cho Ax=b chính xác”.

Mã trong bài trả `NO_SOLUTION` cho hệ vô nghiệm; nó **không** tự trả nghiệm least squares. Đừng nhầm một phương pháp xấp xỉ tối ưu phần dư với nghiệm đúng của hệ ban đầu.

### Nghịch đảo ma trận không phải lựa chọn mặc định

Với A vuông không suy biến, x=A⁻¹b về mặt đại số. Nhưng tính toàn bộ ma trận nghịch đảo chỉ để giải một vế phải thường tốn công hơn và có thể làm tăng sai số so với giải trực tiếp bằng Gaussian/LU.

## 16. Một số lỗi lập trình thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chia cho phần tử đường chéo bằng 0 | NaN/Infinity | Chọn trụ và đổi hàng |
| Chọn pivot bằng trị tuyệt đối nhỏ nhất | Khuếch đại sai số | Chọn lớn nhất trong cột chưa khử |
| Dùng pivot sau khi đã thay hàng mà không cập nhật | Khử sai | Đổi hàng trước rồi lấy trụ |
| Không biến đổi cột b | Thay đổi hệ | Khử cả vế phải |
| Duyệt vòng cột chỉ tới n−1 khi cập nhật hàng | Bỏ vế phải | `j <= n` |
| Đặt `factor = aug[pivot]/aug[r]` | Hệ số khử ngược | `aug[r][col]/aug[pivot][col]` |
| Tăng hàng trụ ngay khi cột toàn 0 | Hạng và nghiệm sai | Chỉ tăng rank khi tìm trụ |
| Coi cột không có trụ là vô nghiệm | Bỏ qua biến tự do | Xét rank và hàng mâu thuẫn |
| Chỉ kiểm rankA<n rồi kết luận vô số | Có thể hệ vô nghiệm | Kiểm rankAug trước |
| Chỉ giải hệ vuông | Không xử lý m≠n | Theo dõi m,n riêng |
| Giả định pivotColumns=[0,1,...] | Sai khi bỏ cột | Lưu chỉ số cột trụ |
| Đặt biến tự do bằng 0 rồi nói duy nhất | Sai diễn giải | Trả trạng thái INFINITE |
| Quên thế ngược từ trụ cuối | Dùng biến chưa biết | Duyệt trụ từ dưới lên |
| Không kiểm đầu vào rỗng | Lỗi chỉ số | Truyền số ẩn tường minh |
| Sử dụng `==0` trên double thiếu chính sách | Nhạy sai số | Đặt tolerance/scale có ý nghĩa |
| Dùng epsilon tuyệt đối bất chấp thang | Sai phân loại rank | Nêu giới hạn; cân nhắc relative/QR/SVD |
| Chuẩn hóa mỗi hàng sau phép khử rồi bỏ scale | Sai ngưỡng | Theo dõi thang nếu áp dụng |
| Nhầm nhỏ residual với nghiệm chính xác | Sai về conditioning | Kiểm độ nhạy |
| Dùng `int` cho ma trận hệ số chung | Không lưu được số thực | Dùng double hoặc rational đúng miền |
| Hoán vị cột rồi quên hoán vị biến về | Trả nghiệm sai thứ tự | Theo dõi permutation |
| Dùng phép chia thông thường modulo p | Sai trong trường hữu hạn | Nhân nghịch đảo modulo |
| Gọi hệ vô nghiệm là least squares | Đổi bài toán | Phân biệt exact/approx |
| Không so nghiệm với hệ gốc | Lỗi khó phát hiện | Tính residual trên A,b gốc |

## 17. Kiểm thử và oracle độc lập

### Ví dụ chuẩn cần có

| Dạng hệ | Dữ liệu | Kết quả |
| --- | --- | --- |
| 3×3 đủ hạng | Hệ 2x+y−z=8; −3x−y+2z=−11; −2x+y+2z=−3 | UNIQUE: (2,3,−1) |
| Trụ đầu bằng 0 | 0x+2y=4; x+y=3 | UNIQUE: (1,2), cần đổi hàng |
| Phụ thuộc nhất quán | x+2y−z=3; 2x+4y−2z=6 | INFINITE, nghiệm riêng (3,0,0) |
| Phụ thuộc mâu thuẫn | x+2y−z=3; 2x+4y−2z=7 | NO_SOLUTION |
| Thừa phương trình | x+y=3; 2x+2y=6; x−y=1 | UNIQUE (2,1) |
| Toàn 0 và b=0 | Hai hàng 0, hai ẩn | INFINITE |
| Không có ẩn, b=0 | n=0 | UNIQUE [] |
| Không có ẩn, b có phần tử 1 | n=0 | NO_SOLUTION |
| Không có phương trình, n=2 | m=0 | INFINITE |

### Oracle định thức 2×2

Với:

~~~text
A=[ a b ]
  [ c d ]

det(A) = a*d - b*c
~~~

Trên số thực **chính xác**, hệ 2×2 có nghiệm duy nhất khi det(A)≠0. Với det(A)=0 và b đã được xây từ một nghiệm cho trước, hệ luôn **nhất quán** nhưng không duy nhất.

Test sinh b=A·(2,−1) trên toàn bộ 5⁴=625 ma trận có hệ số nguyên từ −2 tới 2. Khi det≠0, nghiệm duy nhất phải là (2,−1). Khi det=0, nghiệm vô số và nghiệm riêng của thuật toán phải thỏa hệ. Đây là oracle khác cấu trúc với khử Gauss.

### Test tính chất

1. Nghiệm trả về phải có đúng n thành phần khi hệ nhất quán.
2. Nếu UNIQUE, rankA=rankAug=n.
3. Nếu INFINITE, rankA=rankAug<n và có n−rankA biến tự do.
4. Nếu NO_SOLUTION, rankAug>rankA.
5. `pivotColumns` tăng nghiêm ngặt, không trùng, thuộc [0,n).
6. Số trụ không vượt min(m,n).
7. Kết quả không phụ thuộc hoán vị các hàng trong **số học chính xác**; trong double có thể khác sai số nhỏ.
8. Thêm một hàng `0=0` không đổi tập nghiệm.
9. Nhân một phương trình với số khác 0 bảo toàn tập nghiệm toán học, dù epsilon tuyệt đối có thể làm thay đổi phân loại số học.
10. Nếu b=A·xKnown và A đủ hạng cột, nghiệm phải gần xKnown.
11. Tính `||Ax−b||∞` bằng dữ liệu gốc; đừng chỉ kiểm ma trận sau khử.
12. Với hàng `0=c` c khác 0 rõ ràng, phải phân loại vô nghiệm.
13. Nếu đổi hàng trước một trụ 0, nghiệm vẫn phải giống bài gốc.
14. Test m<n, m=n, m>n, m=0 và n=0.
15. Test hệ gần suy biến và nhiều thang dữ liệu, diễn giải sai lệch do epsilon.
16. Kiểm đầu vào có `NaN`, `Infinity`, số cột thiếu/thừa phải bị từ chối.

### Không chỉ nhìn stdout

Số học double có thể in đẹp với bốn chữ số thập phân dù phần dư không nhỏ. Vì vậy chương trình kiểm **residual riêng** với hệ gốc. Tương tự, nhìn một nghiệm riêng không đủ biết hệ UNIQUE hay INFINITE; cần đọc cả trạng thái/hạng.

## 18. Khi cần nghiệm chính xác hoặc mô hình số khác

### Số hữu tỉ chính xác

Nếu hệ số là các số nguyên nhỏ và đề đòi nghiệm phân số **chính xác**, có thể dùng phân số tử/mẫu BigInteger, rút gọn bằng gcd. Các phép khử vẫn như trên nhưng thay phép chia double bằng phép chia phân số.

Đổi lại, kích thước tử/mẫu có thể tăng nhanh; nên cân nhắc khử không phân số (fraction-free elimination, ví dụ Bareiss trong các điều kiện thích hợp) hoặc thuật toán đại số máy tính.

### Hệ modulo số nguyên tố

Với hệ trên trường F_p, một trụ khác 0 có nghịch đảo modulo p. Bước khử tương tự nhưng phép chia dùng **nghịch đảo nhân modulo**. Không thể lấy code double rồi ép kiểu khi cần nghiệm trong F_p; quy tắc hạng, số nghiệm và trường cơ sở cần phân biệt.

### Hệ bình phương tối thiểu và phân rã

Nếu cần tối ưu sai số của một hệ vô nghiệm Ax=b, có thể chuyển sang least squares, thường dùng QR/SVD. Nếu cần kiểm rank ổn định trên dữ liệu gần suy biến, SVD cho thông tin singular values và ngưỡng rank có ý nghĩa hơn một epsilon tuyệt đối trên từng trụ.

Mục tiêu của khử Gauss trong bài là **giải hệ tuyến tính bằng các phép biến đổi hàng**, chứ không phải tự động giải mọi bài xấp xỉ hình học, regression hoặc sparse large-scale optimization.

## 19. Bài tập thực hành

1. Viết ma trận mở rộng của hệ hai phương trình hai ẩn.
2. Nêu ba phép biến đổi hàng bảo toàn tập nghiệm.
3. Mô phỏng khử cột đầu của hệ ba phương trình ở phần 4.
4. Giải thích vì sao phải đổi hàng khi trụ ban đầu bằng 0.
5. Tính phần tử trụ lớn nhất theo trị tuyệt đối cho một cột có các giá trị −3,2,−2.
6. Tự khử tiếp hệ 3×3 để thu dạng bậc thang.
7. Thế ngược từ hàng cuối và kiểm nghiệm (2,3,−1).
8. Giải hệ 0x+2y=4; x+y=3 bằng đổi hàng.
9. Cài `partialPivot` chỉ đổi hàng.
10. Cài `gaussianForwardElimination` có cập nhật vế phải.
11. Cài `backSubstitution` sử dụng `pivotColumns`.
12. Tự tạo một hệ bỏ cột x nhưng có trụ tại y,z.
13. Tìm nghiệm tổng quát của x+2y−z=3.
14. Với hệ x+2y−z=3; 2x+4y−2z=7, chứng minh vô nghiệm.
15. Phân biệt rank(A) và rank([A|b]).
16. Tạo một hệ m>n có nghiệm duy nhất.
17. Tạo một hệ m<n có vô số nghiệm.
18. Tạo một hệ m<n nhưng vô nghiệm.
19. Giải thích vì sao hàng 0=0 không ảnh hưởng nghiệm.
20. Giải thích vì sao hàng 0=5 là mâu thuẫn.
21. Cài đọc input ma trận chữ nhật và kiểm mỗi hàng có đúng n hệ số.
22. Trả một nghiệm riêng khi tồn tại biến tự do, ghi rõ không phải duy nhất.
23. Tính cơ sở null space của hệ x+2y−z=3.
24. Thử m=0,n=2 và lý giải vì sao vô số nghiệm.
25. Thử m>0,n=0 với mọi b=0 và b có phần tử khác 0.
26. Cài hàm residualInfinity trên A,b gốc.
27. Kiểm định thức 2×2 làm oracle độc lập cho Gaussian.
28. Sinh 625 ma trận 2×2 với hệ số từ −2 tới 2; thống kê 496 không suy biến và 129 suy biến.
29. Tạo hệ gần suy biến với định thức 10^−12 và xem epsilon ảnh hưởng rank.
30. Đổi toàn bộ một phương trình theo tỷ lệ 10^−12 và phân tích rủi ro epsilon tuyệt đối.
31. So partial pivoting với không chọn pivot trên trụ đầu 0.
32. Tìm một hệ ill-conditioned có residual nhỏ nhưng nghiệm rất nhạy.
33. Nêu khác biệt giữa Gaussian elimination và Gauss–Jordan.
34. Trình bày cách đổi cột của complete pivoting làm đổi thứ tự ẩn.
35. Giải thích tại sao LU hữu ích với nhiều vế phải cùng A.
36. Phân biệt giải exact Ax=b với least squares khi hệ vô nghiệm.
37. Mô tả cách giải hệ modulo số nguyên tố bằng nghịch đảo nhân.
38. Mô tả lợi ích và chi phí dùng phân số BigInteger.
39. Chứng minh O(N³) thời gian khử Gauss cho ma trận vuông N×N.
40. Viết property test khẳng định hoán đổi thứ tự phương trình không đổi tập nghiệm.
41. Thử NaN/Infinity hoặc ma trận ragged và xác nhận API từ chối.
42. Giải thích vì sao không nên tính A⁻¹ chỉ để giải một vế phải.

## 20. Checklist và tổng kết

Trước khi áp dụng khử Gauss:

- Đã tách rõ **m phương trình, n ẩn và ma trận mở rộng [A|b]**?
- Mỗi phép biến đổi hàng có cập nhật vế phải b?
- Khi chọn trụ, đã xét các hàng chưa dùng và chọn **trị tuyệt đối lớn nhất** trong cột?
- Nếu một cột không có trụ, đã **bỏ cột** chứ không kết luận vô nghiệm ngay?
- Đã lưu **pivotColumns** để thế ngược đúng khi có biến tự do?
- Đã kiểm hàng `0...0 | c` với c khác 0 để phát hiện vô nghiệm?
- Đã phân biệt `rankA<rankAug`, `rankA=rankAug=n`, `rankA=rankAug<n`?
- Nếu INFINITE, có nói rõ nghiệm trả về chỉ là **nghiệm riêng**?
- Có xử lý m<n, m>n, hệ toàn 0, m=0 và n=0?
- Có nêu **epsilon** là ngưỡng xấp xỉ, không phải một định lý toán học?
- Có kiểm overflow/NaN/Infinity trong bước số thực và tính residual trên hệ gốc?
- Có kiểm nghiệm qua một oracle độc lập hoặc thế trực tiếp?
- Nếu bài yêu cầu độ chính xác cao/modulo, đã chọn mô hình số học phù hợp?

**Kết luận:** khử Gauss dựa trên các phép biến đổi hàng bảo toàn tập nghiệm, chọn **phần tử trụ** để loại hệ số phía dưới, và **thế ngược** để tính nghiệm. Partial pivoting đổi hàng nhằm tránh trụ bằng 0 và cải thiện ổn định số. Theo hạng của A và ma trận mở rộng [A|b], hệ có **vô nghiệm**, **nghiệm duy nhất**, hoặc **vô số nghiệm**. Với ma trận vuông N×N, cách khử dense tiêu chuẩn tốn **O(N³) thời gian và O(N²) bộ nhớ**. Trong triển khai `double`, luôn phân biệt các mệnh đề của đại số chính xác với ước lượng rank theo epsilon; với hệ gần suy biến, kết quả cần được diễn giải thận trọng và có thể phải dùng những phương pháp số ổn định hơn.

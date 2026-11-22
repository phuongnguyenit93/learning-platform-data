# Tổng tiền tố nhiều chiều

## 1. Bài toán: truy vấn tổng nhiều vùng trên ma trận và khối dữ liệu

Cho một mảng hai chiều A có R hàng và C cột. Nếu được hỏi một lần về tổng các phần tử trong hình chữ nhật, ta có thể duyệt từng ô của vùng cần tính. Nhưng khi có hàng nghìn hoặc hàng triệu truy vấn trên **cùng một ma trận ít thay đổi**, việc duyệt lại mọi ô cho từng truy vấn rất tốn thời gian.

**Tổng tiền tố nhiều chiều (multidimensional prefix sum)** tiền xử lý tổng của các hình chữ nhật, hình hộp hoặc siêu hình hộp bắt đầu từ gốc tọa độ. Nhờ **nguyên lý bao hàm–loại trừ (inclusion–exclusion)**, tổng của một vùng bất kỳ có thể được tính bằng một số ít tổng tiền tố.

Cần phân biệt:
- **1D:** mảng độ dài n, tiền tố lưu tổng từ đầu dãy tới một vị trí. Tổng đoạn lấy từ hai tiền tố.
- **2D:** ma trận R × C, tiền tố lưu tổng hình chữ nhật từ góc trên trái; tổng vùng lấy từ **bốn** giá trị tiền tố.
- **3D:** khối dữ liệu X × Y × Z, tiền tố lưu tổng hộp từ gốc; tổng hộp lấy từ **tám** giá trị tiền tố.
- **d chiều:** miền truy vấn hình hộp theo từng trục; công thức tổng quát có **\(2^d\)** góc cộng/trừ khi d là số chiều.

Ở đây, “tổng” là phép cộng các giá trị số; phương pháp trực tiếp còn áp dụng cho nhiều đại lượng cộng dồn khác, miễn có thể thực hiện phép trừ để loại phần nằm ngoài vùng truy vấn. Ví dụ dữ liệu có thể là số lượng vật thể trên lưới, nhiệt độ tích lũy hoặc điểm số tại các ô.

**Điều kiện sử dụng quan trọng:** thuật toán tối ưu cho dữ liệu tĩnh hoặc nhiều truy vấn hơn số cập nhật. Khi thay đổi một phần tử, nhiều giá trị tiền tố có thể phải tính lại; cần phân biệt bài toán truy vấn tĩnh và bài toán cập nhật động.

## 2. Nhắc lại tiền tố một chiều

Với mảng A chỉ số 0..n−1, định nghĩa một mảng tiền tố có thêm phần tử đệm:

\[
P[0]=0,\qquad
P[i+1]=P[i]+A[i]\quad(0\le i<n).
\]

Do đó, \(P[t]\) là tổng của **t phần tử đầu tiên**, tức vùng nửa mở [0,t).

Tổng đoạn nửa mở [l,r), với \(0\le l\le r\le n\), là:

\[
sum(l,r)=P[r]-P[l].
\]

Nếu đề bài dùng đoạn đóng [l,r] và chỉ số 0-based thì đổi sang \(P[r+1]-P[l]\).

Mảng đệm P[0]=0 giúp tính đúng những đoạn bắt đầu tại 0 và cho phép đoạn rỗng l=r có tổng 0, không phải xử lý riêng chỉ số −1.

## 3. Xây dựng tổng tiền tố hai chiều (2D)

Cho ma trận A gồm R hàng, C cột, chỉ số gốc 0. Tạo ma trận tiền tố P kích thước **(R+1) × (C+1)** với hàng 0 và cột 0 đều bằng 0.

**Định nghĩa chính xác:** \(P[i][j]\) là tổng các ô A thuộc các hàng [0,i) và cột [0,j), tức i hàng đầu và j cột đầu. Do vậy \(P[0][j]=P[i][0]=0\).

Công thức truy hồi cho \(1\le i\le R,\ 1\le j\le C\):

\[
\boxed{P[i][j]
= A[i-1][j-1] + P[i-1][j] + P[i][j-1] - P[i-1][j-1]}
\]

**Vì sao đúng?** P[i−1][j] chứa tất cả ô phía trên; P[i][j−1] chứa tất cả ô phía trái. Khi cộng hai vùng, phần giao ở góc trên trái P[i−1][j−1] bị tính hai lần, nên phải trừ một lần. Cuối cùng cộng ô mới A[i−1][j−1]. Đây là phiên bản hai chiều của cộng tích lũy một chiều.

Ví dụ:

~~~text
Ma trận A (3 × 3):
 1   2   3
 4   5   6
 7   8   9

Ma trận P (4 × 4), có hàng và cột đệm:
 0   0   0   0
 0   1   3   6
 0   5  12  21
 0  12  27  45
~~~

Chẳng hạn, \(P[2][2]=1+2+4+5=12\) và \(P[3][3]=45\), là tổng cả ma trận. Tổng hình chữ nhật góc phải dưới [5,6;8,9] là 28.

**Chi phí xây dựng:** Có R·C ô thật; mỗi ô chỉ cần vài phép cộng/trừ, nên thời gian **\(\Theta(RC)\)**. Lưu bảng tiền tố dùng bộ nhớ **\(\Theta(RC)\)** nếu R,C dương; ngoài bảng đầu ra, chỉ cần một số biến vòng lặp.

## 4. Truy vấn tổng hình chữ nhật bằng bốn góc

Giả sử truy vấn hình chữ nhật có góc trên trái (r1,c1) và góc dưới phải (r2,c2), **bao gồm cả hai đầu**, với:

\[
0\le r1\le r2<R,\qquad 0\le c1\le c2<C.
\]

Với bảng P dùng thêm một hàng/cột đệm, công thức là:

\[
\boxed{
S(r1,c1,r2,c2)=
P[r2+1][c2+1]
-P[r1][c2+1]
-P[r2+1][c1]
+P[r1][c1]
}
\]

Có thể đọc công thức theo bốn bước:

1. Lấy tổng từ gốc tới góc dưới phải: \(P[r2+1][c2+1]\).
2. Trừ vùng nằm **phía trên** hình chữ nhật: \(P[r1][c2+1]\).
3. Trừ vùng nằm **bên trái** hình chữ nhật: \(P[r2+1][c1]\).
4. Cộng lại vùng góc trên trái \(P[r1][c1]\), bởi vùng này bị trừ hai lần.

Ví dụ trên A=1..9:

- Tổng cả ma trận: \(S(0,0,2,2)=P[3][3]=45\).
- Tổng hình vuông 2×2 góc phải dưới: \(S(1,1,2,2)=45-6-12+1=28\).
- Một ô ở giữa: \(S(1,1,1,1)=12-3-5+1=5\).
- Một hàng hay một cột cũng được tính bằng đúng công thức này, không cần viết nhánh đặc biệt.

**Mỗi truy vấn chỉ dùng bốn lần đọc P và một số hằng số phép toán:** thời gian \(\Theta(1)\), sau khi đã xây dựng P. Với Q truy vấn trên một ma trận tĩnh, tổng chi phí là **\(\Theta(RC+Q)\)** cộng chi phí đọc/ghi dữ liệu. Quét trực tiếp từng vùng có chi phí tỷ lệ với diện tích của từng truy vấn, trong trường hợp xấu nhất O(QRC).

### Dạng chỉ số nửa mở

Nếu truy vấn được biểu diễn theo vùng hàng [r1,r2) và cột [c1,c2) với \(0\le r1\le r2\le R\), \(0\le c1\le c2\le C\), thì:

\[
S=P[r2][c2]-P[r1][c2]-P[r2][c1]+P[r1][c1].
\]

Dạng nửa mở phù hợp với định nghĩa P và cho phép một chiều có độ dài 0, khi đó tổng là 0. Tuy nhiên, **không trộn** công thức nửa mở với tọa độ đoạn đóng: sai lệch một đơn vị là lỗi thường gặp nhất.

## 5. Mở rộng lên ba chiều (3D)

Với mảng A có ba trục X × Y × Z, định nghĩa bảng P có kích thước (X+1) × (Y+1) × (Z+1):

\[
P[i][j][k]
=\sum_{0\le x<i}\sum_{0\le y<j}\sum_{0\le z<k}A[x][y][z].
\]

Mọi mặt có ít nhất một tọa độ bằng 0 đều có tổng 0.

Công thức xây dựng từ bảy vùng tiền tố lân cận và ô hiện tại:

\[
\begin{aligned}
P[i][j][k] ={}& A[i-1][j-1][k-1]\\
&+P[i-1][j][k]+P[i][j-1][k]+P[i][j][k-1]\\
&-P[i-1][j-1][k]-P[i-1][j][k-1]-P[i][j-1][k-1]\\
&+P[i-1][j-1][k-1].
\end{aligned}
\]

Ba vùng mặt được cộng; ba vùng giao đôi bị trừ; vùng giao ba bị cộng lại. Cấu trúc dấu **+ − +** phản ánh nguyên lý bao hàm–loại trừ.

Với hình hộp nửa mở [x1,x2) × [y1,y2) × [z1,z2), tổng là:

\[
\begin{aligned}
S={}&P[x2][y2][z2]\\
&-P[x1][y2][z2]-P[x2][y1][z2]-P[x2][y2][z1]\\
&+P[x1][y1][z2]+P[x1][y2][z1]+P[x2][y1][z1]\\
&-P[x1][y1][z1].
\end{aligned}
\]

Có **tám góc**: một góc toàn cận trên mang dấu +, ba góc thay một tọa độ bằng cận dưới mang dấu −, ba góc thay hai tọa độ bằng cận dưới mang dấu +, và góc toàn cận dưới mang dấu −.

Ví dụ khối 2×2×2:

~~~text
Lớp x=0:          Lớp x=1:
1   2             5   6
3   4             7   8
~~~

Tổng cả khối là \(1+2+\cdots+8=36\). Tổng riêng lớp x=1 (cả hai chiều y,z) bằng \(5+6+7+8=26\). Cả hai truy vấn chỉ lấy tối đa tám giá trị từ bảng P, không cần duyệt lại ô của hộp.

**Độ phức tạp:** xây dựng 3D tốn \(\Theta(XYZ)\) thời gian, lưu P tốn \(\Theta(XYZ)\) bộ nhớ và truy vấn hộp tốn \(\Theta(1)\) vì số góc cố định là 8.

## 6. Mã Java 17+ đầy đủ cho 2D và 3D

Tạo tệp **MultiDimensionalPrefixSumDemo.java**. Mã dùng kiểu long để chứa tổng và một lớp riêng cho mỗi số chiều. Giao diện sum dùng **tọa độ đóng, chỉ số bắt đầu từ 0**: đầu dưới và đầu trên đều thuộc vùng truy vấn.

~~~java
public final class MultiDimensionalPrefixSumDemo {
    private MultiDimensionalPrefixSumDemo() {
    }

    static final class Prefix2D {
        private final int rows;
        private final int cols;
        private final long[][] prefix;

        Prefix2D(int[][] a) {
            if (a == null || a.length == 0
                    || a[0] == null || a[0].length == 0) {
                throw new IllegalArgumentException("Matrix must be nonempty");
            }
            rows = a.length;
            cols = a[0].length;
            prefix = new long[rows + 1][cols + 1];

            for (int i = 1; i <= rows; i++) {
                if (a[i - 1] == null || a[i - 1].length != cols) {
                    throw new IllegalArgumentException("Ragged matrix");
                }
                for (int j = 1; j <= cols; j++) {
                    prefix[i][j] = a[i - 1][j - 1]
                            + prefix[i - 1][j]
                            + prefix[i][j - 1]
                            - prefix[i - 1][j - 1];
                }
            }
        }

        long sum(int top, int left, int bottom, int right) {
            if (top < 0 || left < 0
                    || bottom < top || right < left
                    || bottom >= rows || right >= cols) {
                throw new IllegalArgumentException("Invalid 2D rectangle");
            }
            return prefix[bottom + 1][right + 1]
                    - prefix[top][right + 1]
                    - prefix[bottom + 1][left]
                    + prefix[top][left];
        }
    }

    static final class Prefix3D {
        private final int xSize;
        private final int ySize;
        private final int zSize;
        private final long[][][] prefix;

        Prefix3D(int[][][] a) {
            if (a == null || a.length == 0
                    || a[0] == null || a[0].length == 0
                    || a[0][0] == null || a[0][0].length == 0) {
                throw new IllegalArgumentException("Volume must be nonempty");
            }

            xSize = a.length;
            ySize = a[0].length;
            zSize = a[0][0].length;

            for (int x = 0; x < xSize; x++) {
                if (a[x] == null || a[x].length != ySize) {
                    throw new IllegalArgumentException("Ragged volume");
                }
                for (int y = 0; y < ySize; y++) {
                    if (a[x][y] == null || a[x][y].length != zSize) {
                        throw new IllegalArgumentException("Ragged volume");
                    }
                }
            }

            prefix = new long[xSize + 1][ySize + 1][zSize + 1];
            for (int x = 1; x <= xSize; x++) {
                for (int y = 1; y <= ySize; y++) {
                    for (int z = 1; z <= zSize; z++) {
                        prefix[x][y][z] = a[x - 1][y - 1][z - 1]
                                + prefix[x - 1][y][z]
                                + prefix[x][y - 1][z]
                                + prefix[x][y][z - 1]
                                - prefix[x - 1][y - 1][z]
                                - prefix[x - 1][y][z - 1]
                                - prefix[x][y - 1][z - 1]
                                + prefix[x - 1][y - 1][z - 1];
                    }
                }
            }
        }

        long sum(int x1, int y1, int z1,
                 int x2, int y2, int z2) {
            if (x1 < 0 || y1 < 0 || z1 < 0
                    || x2 < x1 || y2 < y1 || z2 < z1
                    || x2 >= xSize || y2 >= ySize || z2 >= zSize) {
                throw new IllegalArgumentException("Invalid 3D box");
            }

            int xa = x1, xb = x2 + 1;
            int ya = y1, yb = y2 + 1;
            int za = z1, zb = z2 + 1;

            return prefix[xb][yb][zb]
                    - prefix[xa][yb][zb]
                    - prefix[xb][ya][zb]
                    - prefix[xb][yb][za]
                    + prefix[xa][ya][zb]
                    + prefix[xa][yb][za]
                    + prefix[xb][ya][za]
                    - prefix[xa][ya][za];
        }
    }

    public static void main(String[] args) {
        int[][] matrix = {
            {1, 2, 3},
            {4, 5, 6},
            {7, 8, 9}
        };
        Prefix2D p2 = new Prefix2D(matrix);
        System.out.println("2D whole = " + p2.sum(0, 0, 2, 2));
        System.out.println("2D lower-right = " + p2.sum(1, 1, 2, 2));
        System.out.println("2D center = " + p2.sum(1, 1, 1, 1));

        int[][][] cube = {
            {
                {1, 2},
                {3, 4}
            },
            {
                {5, 6},
                {7, 8}
            }
        };
        Prefix3D p3 = new Prefix3D(cube);
        System.out.println("3D whole = " + p3.sum(0, 0, 0, 1, 1, 1));
        System.out.println("3D second layer = " + p3.sum(1, 0, 0, 1, 1, 1));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MultiDimensionalPrefixSumDemo.java
java MultiDimensionalPrefixSumDemo
~~~

Kết quả stdout:

~~~text
2D whole = 45
2D lower-right = 28
2D center = 5
3D whole = 36
3D second layer = 26
~~~

Giải thích mã:
- **Prefix2D** tạo hàng/cột đệm và tính từng ô dựa trên hàng phía trên, cột phía trái và vùng giao. Hàm sum dùng công thức bốn góc.
- **Prefix3D** xác minh khối đầu vào có dạng chữ nhật ba chiều (không có tầng/hàng lệch kích thước), tính công thức bảy tiền tố lân cận và một ô dữ liệu. Hàm sum dùng công thức tám góc.
- Hàm main kiểm tra truy vấn cả miền, một vùng con, một ô 2D và một lớp 3D. Phép cộng nguyên được nâng lên kiểu long nhờ các toán hạng prefix kiểu long; vẫn cần lưu ý tổng vượt phạm vi long sẽ tràn số.
- Các hàm sum chỉ chấp nhận **vùng không rỗng** biểu diễn bằng tọa độ đóng. Một vùng rỗng có thể được hỗ trợ bằng giao diện nửa mở riêng nếu bài toán cần; không tự gán nó cho cách gọi bottom < top hiện tại.

Mã minh họa dữ liệu tĩnh; sau khi xây dựng bảng P, nếu sửa phần tử trong matrix hoặc cube thì P **không tự cập nhật**.

## 7. Công thức d chiều và bao hàm–loại trừ

Với d chiều, mỗi tọa độ theo trục t nằm trong [0, n_t). Ta dùng bảng tiền tố:

\[
P(b_1,\ldots,b_d)
=\sum_{0\le i_1<b_1}\cdots\sum_{0\le i_d<b_d}
 A(i_1,\ldots,i_d).
\]

Truy vấn siêu hình hộp nửa mở:

\[
[l_1,r_1)\times\cdots\times[l_d,r_d).
\]

Đối với mỗi vector nhị phân \(\varepsilon\in\{0,1\}^d\), chọn tọa độ góc \(t_j=l_j\) khi \(\varepsilon_j=1\), còn \(t_j=r_j\) khi \(\varepsilon_j=0\). Khi ấy:

\[
\boxed{
S=\sum_{\varepsilon\in\{0,1\}^{d}}
(-1)^{\varepsilon_1+\cdots+\varepsilon_d}
P(t_1,\ldots,t_d)
}
\]

Ý nghĩa: bắt đầu bằng vùng tiền tố có tất cả tọa độ là cận trên, trừ các vùng ngoài giới hạn thấp của từng trục, cộng lại các giao hai trục, rồi tiếp tục đổi dấu theo số trục được chọn về cận dưới. Có đúng **2^d lựa chọn góc**.

- Với d=1 có 2 góc, đúng công thức tiền tố một chiều.
- Với d=2 có 4 góc, đúng công thức hình chữ nhật.
- Với d=3 có 8 góc, đúng công thức hình hộp.

Nếu d cố định nhỏ, một truy vấn dùng O(1) phép toán theo kích thước mỗi chiều; nếu coi d là biến đầu vào, chi phí truy vấn là **O(2^d)**. Gọi \(N=\prod_{j=1}^{d}n_j\) là số phần tử của khối. Bảng tiền tố có \(\prod(n_j+1)\) ô; có thể xây dựng bằng **d lượt cộng dồn lần lượt trên từng trục**, tốn O(d·N) công việc cho vùng không tính các mặt đệm, hoặc dùng truy hồi bao hàm–loại trừ trực tiếp với O(2^d) thành phần cho mỗi ô. Bộ nhớ tỷ lệ số ô tiền tố được lưu, và có thể trở nên rất lớn khi số chiều tăng.

## 8. Độ phức tạp, cập nhật dữ liệu và lựa chọn cấu trúc

| Phương pháp | Tiền xử lý | Truy vấn tổng 2D | Cập nhật điểm |
|---|---|---|---|
| Duyệt từng hình chữ nhật | O(1) ngoài dữ liệu đầu vào | O(diện tích vùng) | O(1) |
| Bảng tổng tiền tố 2D | \(\Theta(RC)\) | \(\Theta(1)\) | Có thể ảnh hưởng \(\Theta(RC)\) giá trị tiền tố |
| Fenwick Tree 2D (BIT) | Tùy cách xây dựng, có thể O(RC log R log C) bằng cập nhật điểm | O(log R log C) | O(log R log C) |
| Segment Tree 2D | Phụ thuộc triển khai | Thường O(log R log C) | Thường O(log R log C) |

**Vì sao cập nhật điểm khó với bảng tiền tố?** Nếu thay A[r][c] thêm \(\Delta\), mọi P[i][j] với \(i>r\) và \(j>c\) đều tăng \(\Delta\). Số ô bị ảnh hưởng là (R−r)(C−c), trong trường hợp xấu nhất là RC. Nếu các cập nhật và truy vấn đan xen liên tục, Fenwick 2D hoặc một cấu trúc dữ liệu động phù hợp thường tốt hơn.

**Phân biệt với mảng sai phân nhiều chiều:** Khi yêu cầu là “cộng \(\Delta\) vào nhiều hình chữ nhật, rồi mới kết xuất ma trận cuối cùng”, mảng sai phân 2D có thể ghi một cập nhật vùng qua bốn góc và sau đó lấy tổng tiền tố để khôi phục giá trị. Đây là **bài toán cập nhật vùng hàng loạt**, khác với “tính tổng vùng nhiều lần trên ma trận tĩnh”. Không thay một cấu trúc bằng cấu trúc kia mà không xét loại truy vấn và thời điểm cập nhật.

**Lựa chọn kiểu dữ liệu:** Nếu A chứa int, tổng của nhiều ô có thể vượt phạm vi int; long giúp giảm nguy cơ nhưng không bảo đảm tuyệt đối. Khi dữ liệu cực lớn cần kết quả chính xác, phải xét kiểm tra tràn số hoặc kiểu số nguyên lớn hơn. Số thực dấu phẩy động có thể tích lũy sai số do thứ tự cộng/trừ; đặt dung sai kiểm thử phù hợp nếu dùng double.

## 9. Lỗi phổ biến và ca kiểm thử

1. **Trộn chỉ số 0-based và 1-based:** P được đệm một hàng/cột/mặt 0. Truy vấn tọa độ đóng [r1..r2] phải dùng r2+1 trong P.
2. **Quên dấu cộng lại vùng giao:** Trong 2D, sau hai phép trừ trên và trái, phần giao bị trừ hai lần; phải cộng P[r1][c1].
3. **3D thiếu một trong tám góc hoặc nhầm dấu:** Ba góc một cận dưới có dấu −, ba góc hai cận dưới có dấu +, góc ba cận dưới có dấu −.
4. **Thiếu hàng/cột đệm:** Truy vấn chạm cạnh trên hoặc trái dẫn tới chỉ số âm hoặc quá nhiều trường hợp đặc biệt. Dùng P kích thước R+1, C+1.
5. **Chỉ kiểm thử số dương:** Các công thức vẫn đúng với số âm và số 0; kiểm thử thêm âm/dương xen kẽ để phát hiện lỗi dấu.
6. **Cho rằng P thay đổi khi sửa A:** Bảng tiền tố là dữ liệu đã tiền xử lý; cần xây dựng lại hoặc chuyển sang cấu trúc động.
7. **Quên bộ nhớ tăng theo tích các chiều:** Khối 3D và d chiều có thể vượt giới hạn bộ nhớ ngay cả khi mỗi chiều không quá lớn.
8. **Dùng int để chứa tổng lớn:** Có thể tràn số âm thầm; cân nhắc long hoặc số nguyên chính xác lớn hơn.
9. **Chấp nhận ma trận bị lệch hàng:** Phải xác định rõ ma trận chữ nhật; mảng jagged trong Java cần được xác minh trước khi xây dựng P.
10. **Tuyên bố O(1) khi d thay đổi:** O(1) đúng khi số chiều cố định; tổng quát cần \(2^d\) góc.
11. **Không định nghĩa vùng rỗng:** Công thức nửa mở trả 0 khi một chiều có độ dài 0; API dùng tọa độ đóng cần quy định rõ đầu vào rỗng là lỗi hay kết quả 0.
12. **Nhầm tổng vùng với cực đại vùng:** Phép cộng/trừ theo bao hàm–loại trừ không áp dụng tương tự cho max/min; cần cấu trúc và lập luận khác.

Các ca kiểm thử nên có:
- Ma trận 1×1; truy vấn toàn miền, một ô, hàng/cột sát biên, góc trên trái và góc dưới phải.
- Ma trận có số âm/0; tổng vùng giao nhau; nhiều truy vấn lặp lại trên cùng một bảng.
- Khối 3D 1×1×1, 2×2×2, truy vấn riêng một lớp, một đường, một ô và toàn bộ khối.
- Tọa độ ngoài miền hoặc đảo chiều, ma trận rỗng và các hàng không đồng kích thước theo hợp đồng API.

**Kiểm thử chéo:** Với ma trận nhỏ, viết phép tính trực tiếp bằng vòng lặp qua các ô trong từng vùng, so sánh với tổng từ bảng tiền tố cho mọi hình chữ nhật hợp lệ. Với khối nhỏ 3D, làm tương tự qua ba vòng lặp cho mọi hình hộp. Cách này đặc biệt hữu ích để phát hiện lỗi cộng/trừ và lệch chỉ số.

## 10. Tự kiểm tra

**Câu 1.** Cho A = [[1,2,3],[4,5,6],[7,8,9]]. Tổng vùng có hai góc (1,1) và (2,2) là bao nhiêu?  
**Đáp án:** \(5+6+8+9=28\). Từ bảng P: \(45-6-12+1=28\).

**Câu 2.** Vì sao bảng P được tạo lớn hơn A một hàng và một cột?  
**Đáp án:** Để biểu diễn tiền tố rỗng bằng 0, cho phép truy vấn chạm biên trên/trái mà không cần tham chiếu chỉ số âm.

**Câu 3.** Một bảng tiền tố 3D cần đọc bao nhiêu góc để tính tổng hình hộp bất kỳ?  
**Đáp án:** Tám góc theo bao hàm–loại trừ. Với d chiều có \(2^d\) góc.

**Câu 4.** Sau khi xây P, sửa một ô A[0][0] thêm 10 rồi truy vấn P cũ có đúng không?  
**Đáp án:** Không. Tất cả tiền tố chứa ô đó phải được cập nhật thêm 10; nếu dùng bảng tĩnh, phải cập nhật hoặc xây lại trước khi truy vấn.

**Câu 5.** Nếu mỗi chiều có kích thước n và số chiều d là một biến, bảng tiền tố cần xấp xỉ bao nhiêu ô?  
**Đáp án:** \((n+1)^d\) ô khi có đệm, và một truy vấn hộp tổng quát sử dụng \(2^d\) tổ hợp góc. Đây là lý do phải cân nhắc số chiều và bộ nhớ ngay khi thiết kế.

**Ghi nhớ:** Tổng tiền tố nhiều chiều là cách **đánh đổi tiền xử lý và bộ nhớ lấy truy vấn tổng vùng nhanh**. Giữ nhất quán tọa độ nửa mở hoặc đóng, dùng các mặt đệm bằng 0, và áp dụng bao hàm–loại trừ với dấu chính xác theo số trục chọn cận dưới.

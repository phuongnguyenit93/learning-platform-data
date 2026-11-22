# Nhân chuỗi ma trận với chi phí nhỏ nhất

**Nhân chuỗi ma trận với chi phí nhỏ nhất** (*Matrix Chain Multiplication / Matrix Chain Order*) là bài toán kinh điển của **quy hoạch động cấu trúc**. Cho các ma trận \(A_1,A_2,\ldots,A_n\) có kích thước tương thích, cần xác định **cách đặt dấu ngoặc** khi nhân chúng theo đúng thứ tự ban đầu sao cho **tổng số phép nhân vô hướng** là ít nhất.

Điều dễ gây nhầm lẫn: phép nhân ma trận **có tính kết hợp về mặt đại số**, tức \((AB)C=A(BC)\) khi kích thước hợp lệ, nhưng **chi phí thực hiện hai cách đặt ngoặc có thể rất khác nhau**. Thuật toán không được hoán đổi vị trí các ma trận. Nó chỉ chọn **thứ tự nhóm phép nhân**, và trong phiên bản chuẩn còn không cần nhân các ma trận thật: chỉ cần biết **dãy kích thước**.

Bài học này trình bày cách biểu diễn dữ liệu, công thức chọn điểm tách, thứ tự tính bảng DP, chứng minh đúng, khôi phục chuỗi dấu ngoặc tối ưu, độ phức tạp, các lỗi thường gặp và chương trình Java 17 có kiểm thử đối chiếu vét cạn.

## 1. Phát biểu bài toán và mô hình chi phí

Có \(n\ge 1\) ma trận:

\[
A_1,A_2,\ldots,A_n.
\]

Mỗi \(A_i\) có kích thước:

\[
A_i:\ p_{i-1}\times p_i
\]

với một dãy **\(n+1\) số nguyên dương**:

\[
p=(p_0,p_1,\ldots,p_n).
\]

Ví dụ, dãy kích thước `p=[10,30,5,60]` biểu diễn **ba ma trận**:

| Ma trận | Số hàng | Số cột |
| --- | ---: | ---: |
| \(A_1\) | 10 | 30 |
| \(A_2\) | 30 | 5 |
| \(A_3\) | 5 | 60 |

Do số cột của \(A_i\) bằng số hàng của \(A_{i+1}\), phép nhân theo thứ tự \(A_1A_2\cdots A_n\) là hợp lệ.

### Chi phí nhân hai ma trận

Theo cách nhân ma trận cổ điển, nếu \(X\) có kích thước \(a\times b\) và \(Y\) có kích thước \(b\times c\), tích \(XY\) có kích thước \(a\times c\). Để tính tích này, số phép **nhân vô hướng** là:

\[
cost(XY)=a\cdot b\cdot c.
\]

Ví dụ: ma trận \(10\times30\) nhân với ma trận \(30\times5\) cần `10×30×5=1500` phép nhân vô hướng.

**Hàm mục tiêu** là tối thiểu tổng các chi phí \(a\cdot b\cdot c\) tại những nút nhân của một cây đặt ngoặc. Mô hình chuẩn giả định dùng thuật toán nhân cổ điển và chỉ đếm phép **nhân**; không tính riêng số phép cộng, cấp phát bộ nhớ, bộ nhớ đệm, truy xuất đĩa hoặc các tối ưu khác của thư viện đại số tuyến tính.

Với cùng một cây đặt ngoặc, kết quả cuối luôn có kích thước \(p_0\times p_n\). Đầu ra của bài toán **không phải ma trận tích**; nó là **chi phí nhỏ nhất** và, nếu đề yêu cầu, **một cách đặt ngoặc đạt chi phí ấy**.

### Những thao tác được và không được phép

Được phép:
- Thay đổi cách nhóm các phép nhân: \(((A_1A_2)A_3)\) hoặc \(A_1(A_2A_3)\).
- Chọn bất kỳ cây nhị phân đầy đủ nào mà các lá theo thứ tự vẫn là \(A_1,A_2,\ldots,A_n\).

Không được phép:
- Đổi \(A_1A_2A_3\) thành \(A_2A_1A_3\): phép nhân ma trận **không giao hoán** nói chung.
- Thêm, xóa hay nhân lặp một ma trận.
- Chọn một thứ tự không tương thích về kích thước.
- Tối ưu chi phí bằng cách thay **thuật toán nhân hai ma trận** nếu đề đã quy định mô hình \(abc\).

**Lưu ý số học:** với số thực dấu phẩy động, thứ tự nhân có thể ảnh hưởng sai số làm tròn và đôi khi khác biệt rất nhỏ ở các phần tử kết quả. Bài này xét tính kết hợp **đại số** và tối ưu số phép nhân theo mô hình chuẩn, không bảo đảm mọi kiểu số máy cho ra bit kết quả giống hệt giữa các thứ tự thực hiện.

## 2. Ví dụ ba ma trận: cùng kết quả nhưng chi phí khác

Với `p=[10,30,5,60]` có:

~~~text
A1: 10 x 30
A2: 30 x 5
A3:  5 x 60
~~~

Chỉ có **hai** cách đặt ngoặc hợp lệ cho ba ma trận theo đúng thứ tự.

### Cách 1: \((A_1A_2)A_3\)

- Nhân \(A_1A_2\): `10×30×5 = 1500` phép nhân, tạo ma trận \(10\times5\).
- Nhân kết quả với \(A_3\): `10×5×60 = 3000` phép nhân, tạo ma trận \(10\times60\).

Tổng:

\[
1500+3000=\boxed{4500}.
\]

### Cách 2: \(A_1(A_2A_3)\)

- Nhân \(A_2A_3\): `30×5×60 = 9000` phép nhân, tạo ma trận \(30\times60\).
- Nhân \(A_1\) với kết quả: `10×30×60 = 18000` phép nhân.

Tổng:

\[
9000+18000=\boxed{27000}.
\]

Hai cách đều cho tích cuối \(10\times60\), nhưng cách thứ hai tốn **sáu lần** số phép nhân vô hướng so với cách thứ nhất.

**Đáp án:** chi phí tối ưu **4500**, đặt ngoặc **\(((A_1A_2)A_3)\)**.

Ví dụ cho thấy không thể tùy tiện gọi phép nhân ma trận theo thứ tự từ trái sang phải hoặc từ phải sang trái mà bỏ qua chi phí. Khi n lớn, số cây ngoặc tăng rất nhanh nên cần một phương pháp có hệ thống hơn.

## 3. Vì sao bài toán có cấu trúc cây?

Một cách đặt ngoặc hoàn chỉnh tương ứng với một **cây nhị phân đầy đủ**:
- Mỗi **lá** là một ma trận gốc \(A_i\).
- Mỗi **nút trong** là một phép nhân hai tích ma trận con.
- Dãy lá theo thứ tự trái sang phải phải luôn là \(A_1,A_2,\ldots,A_n\).

Ví dụ với ba ma trận:

~~~text
       (A1 A2) A3                  A1 (A2 A3)
           (*)                         (*)
          /   \                       /   \
        (*)    A3                    A1   (*)
       /   \                              / \
      A1   A2                            A2 A3
~~~

Nếu có n ma trận, số cách đặt ngoặc hợp lệ là **số Catalan \(C_{n-1}\)**:

\[
C_{n-1}=\frac{1}{n}\binom{2n-2}{n-1}.
\]

Một vài giá trị:

| n ma trận | Số cách đặt ngoặc |
| ---: | ---: |
| 1 | 1 |
| 2 | 1 |
| 3 | 2 |
| 4 | 5 |
| 5 | 14 |
| 6 | 42 |
| 7 | 132 |
| 10 | 4862 |

Số cách tăng rất nhanh. Liệt kê tất cả cây đặt ngoặc rồi tính chi phí từng cây là một lời giải đúng về nguyên tắc, nhưng không phù hợp khi n lớn. Điểm mấu chốt của quy hoạch động là nhiều cây khác nhau chứa cùng những **đoạn con liên tiếp** \(A_i\cdots A_j\), nên có thể tính chi phí tối ưu của đoạn đó **một lần** và dùng lại.

### Vì sao trạng thái là một đoạn liên tiếp?

Bất kỳ nút nào trong cây giữ nguyên thứ tự lá đều bao phủ một đoạn liên tiếp của chuỗi ma trận. Nút gốc của đoạn \(A_i\cdots A_j\) phải tách thành:

\[
(A_i\cdots A_k)\ (A_{k+1}\cdots A_j)
\]

với **một vị trí tách \(k\)** thỏa \(i\le k<j\).

Không có trường hợp “lấy \(A_i\) ghép với \(A_j\) rồi xử lý phần giữa” nếu các lá phải giữ thứ tự. Chính đặc tính **đoạn liên tiếp** tạo ra cấu trúc DP theo khoảng (*interval DP*).

## 4. Trạng thái DP và bất biến kích thước tích

Dùng chỉ số ma trận **bắt đầu từ 1** trong công thức toán học:

\[
m[i][j]=\text{số phép nhân vô hướng nhỏ nhất cần để tính }A_iA_{i+1}\cdots A_j.
\]

Điều kiện `1 <= i <= j <= n`.

Ta cũng lưu:

\[
split[i][j]=\text{vị trí tách }k\text{ tạo ra chi phí tối ưu cho đoạn }[i,j].
\]

Một bất biến kích thước rất quan trọng là:

> Dù đoạn \(A_i\cdots A_j\) được đặt ngoặc ra sao, tích cuối của đoạn ấy luôn có kích thước \(p_{i-1}\times p_j\).

Chứng minh bằng tính tương thích kích thước của các ma trận, không cần biết giá trị phần tử trong chúng. Điều này có nghĩa **chi phí của phép nhân ở nút gốc** chỉ phụ thuộc vào **hai đầu đoạn và vị trí tách**, không phụ thuộc vào cách đặt ngoặc bên trong hai nửa.

### Trạng thái cơ sở

Một ma trận đứng riêng không cần phép nhân ma trận nào:

\[
m[i][i]=0.
\]

Nếu đoạn chỉ có hai ma trận, không có lựa chọn điểm tách:

\[
m[i][i+1]=p_{i-1}\,p_i\,p_{i+1}.
\]

Chi phí này là số phép **nhân vô hướng** để nhân hai ma trận, không phải số phép nhân ma trận ở cấp cao (luôn bằng một cho đoạn hai ma trận).

## 5. Công thức chuyển: thử tất cả điểm tách k

Xét đoạn có ít nhất hai ma trận \([i,j]\). Phép nhân cuối cùng của một cây đặt ngoặc hợp lệ phải tách tại một chỉ số \(k\) giữa i và j−1:

\[
(A_i\cdots A_k)(A_{k+1}\cdots A_j).
\]

Theo bất biến kích thước:
- Tích bên trái có kích thước \(p_{i-1}\times p_k\).
- Tích bên phải có kích thước \(p_k\times p_j\).
- Nhân hai tích này cần \(p_{i-1}p_kp_j\) phép nhân vô hướng.

Nếu bên trái và bên phải được tính bằng phương án tối ưu của riêng chúng, chi phí tổng là:

\[
candidate(i,k,j)
=m[i][k]+m[k+1][j]+p_{i-1}p_kp_j.
\]

Vì chưa biết điểm tách nào tốt nhất, ta thử **mọi \(k=i,i+1,\ldots,j-1\)**:

\[
\boxed{
m[i][j]=\min_{i\le k<j}
\left(m[i][k]+m[k+1][j]+p_{i-1}p_kp_j\right).
}
\]

Đồng thời:

\[
split[i][j]=\arg\min_{i\le k<j} candidate(i,k,j).
\]

Có thể có **nhiều k đồng tối ưu**. Nếu muốn kết quả tái lập được, hãy quy định chính sách phá hòa. Chương trình Java phía dưới duyệt k tăng dần và **chỉ cập nhật khi chi phí mới nhỏ hơn nghiêm ngặt**, nên chọn **k nhỏ nhất** trong những điểm tách đạt cùng chi phí.

### Tại sao không cần duyệt mọi cách đặt ngoặc?

Với một điểm tách k đã cố định, nếu bên trái không dùng phương án tối ưu của đoạn \([i,k]\), thay nó bằng phương án tối ưu sẽ **không tăng** chi phí cuối, vì kích thước tích bên trái vẫn là \(p_{i-1}\times p_k\). Điều tương tự đúng với bên phải.

Vì vậy ta không cần giữ mọi cách đặt ngoặc của hai đoạn con: chỉ cần **chi phí tối ưu** của mỗi đoạn, rồi thử các điểm tách k. Đây là **cấu trúc con tối ưu**, nền tảng của công thức DP.

## 6. Tính bảng theo độ dài đoạn tăng dần

Do `m[i][j]` phụ thuộc các đoạn \([i,k]\) và \([k+1,j]\), cả hai đều **ngắn hơn** đoạn \([i,j]\). Vậy một thứ tự tính đúng là tăng độ dài đoạn (*chain length*):

1. Khởi tạo `m[i][i]=0` cho mọi i.
2. Với độ dài `length=2,3,...,n`:
   - Duyệt mọi đoạn \([i,j]\) có `j=i+length-1`.
   - Thử mọi k từ i đến j−1.
   - Tính `candidate`, cập nhật `m[i][j]` và `split[i][j]`.
3. Trả `m[1][n]`, truy ngược từ `split[1][n]` nếu cần dấu ngoặc.

Giả mã dùng chỉ số ma trận từ 1:

~~~text
for i = 1 .. n:
    m[i][i] = 0

for length = 2 .. n:
    for i = 1 .. n-length+1:
        j = i + length - 1
        m[i][j] = +INF

        for k = i .. j-1:
            cost = m[i][k] + m[k+1][j]
                   + p[i-1]*p[k]*p[j]

            if cost < m[i][j]:
                m[i][j] = cost
                split[i][j] = k

answer = m[1][n]
~~~

**Vì sao không tính theo i tăng rồi j tăng một cách tùy tiện?** Nếu chưa đảm bảo các đoạn con đã tính trước, công thức có thể đọc giá trị **mặc định 0** từ một ô chưa tính và tạo chi phí sai. Thứ tự **độ dài tăng dần** tạo ra một thứ tự tô pô rõ ràng cho đồ thị phụ thuộc các đoạn.

Một cách khác là **top-down + memoization**: gọi `solve(i,j)`, nếu i=j trả 0; nếu trạng thái đã tính thì trả memo; nếu chưa, thử k và gọi đệ quy hai đoạn con. Khi mỗi lời gọi chỉ dùng đoạn ngắn hơn, có bảo đảm kết thúc. Top-down có cùng cận O(n³) thời gian và O(n²) bộ nhớ khi tính mọi trạng thái, cộng stack đệ quy O(n) trong trường hợp chuỗi phân tách lệch. Bottom-up thuận tiện để minh họa thứ tự phụ thuộc và tránh stack đệ quy khi điền bảng.

## 7. Mô phỏng bảng DP cho ba ma trận

Trở lại ví dụ `p=[10,30,5,60]`, tức n=3.

### Độ dài 1

Không có phép nhân cho một ma trận:

~~~text
m[1][1] = 0
m[2][2] = 0
m[3][3] = 0
~~~

### Độ dài 2

Có đúng một cách cho mỗi đoạn:
- `m[1][2] = 10×30×5 = 1500`.
- `m[2][3] = 30×5×60 = 9000`.

### Độ dài 3

Xét đoạn \([1,3]\), thử hai điểm tách:

| k | Cấu trúc | Chi phí trái | Chi phí phải | Chi phí nhân cuối | Tổng |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | \(A_1(A_2A_3)\) | 0 | 9000 | `10×30×60 = 18000` | **27000** |
| 2 | \((A_1A_2)A_3\) | 1500 | 0 | `10×5×60 = 3000` | **4500** |

Chọn k=2:

\[
m[1][3]=4500,\qquad split[1][3]=2.
\]

Bảng chi phí dạng tam giác trên (ô i>j không dùng):

| i \ j | 1 | 2 | 3 |
| ---: | ---: | ---: | ---: |
| 1 | 0 | 1500 | **4500** |
| 2 | — | 0 | 9000 |
| 3 | — | — | 0 |

Mấu chốt của cách lập bảng: trước khi tính `m[1][3]`, cả `m[1][2]` và `m[2][3]` đều đã được tính khi `length=2`. Không ô nào phải dùng lại phép tính chưa hoàn tất.

## 8. Ví dụ sáu ma trận: kết quả chuẩn 15125

Xét dãy kích thước thường dùng:

~~~text
p = [30, 35, 15, 5, 10, 20, 25]
~~~

Nó mô tả sáu ma trận:

| Ma trận | Kích thước |
| --- | --- |
| A1 | 30×35 |
| A2 | 35×15 |
| A3 | 15×5 |
| A4 | 5×10 |
| A5 | 10×20 |
| A6 | 20×25 |

Sau khi điền bảng, các giá trị m[i][j] là:

| i \ j | 1 | 2 | 3 | 4 | 5 | 6 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 15750 | 7875 | 9375 | 11875 | **15125** |
| 2 | — | 0 | 2625 | 4375 | 7125 | 10500 |
| 3 | — | — | 0 | 750 | 2500 | 5375 |
| 4 | — | — | — | 0 | 1000 | 3500 |
| 5 | — | — | — | — | 0 | 5000 |
| 6 | — | — | — | — | — | 0 |

Tại đoạn [1,6], điểm tách tối ưu là **k=3**, tức chia thành \((A_1A_2A_3)\) và \((A_4A_5A_6)\):

- Bên trái có chi phí `m[1][3]=7875` và thứ tự \(A_1(A_2A_3)\).
- Bên phải có chi phí `m[4][6]=3500` và thứ tự \((A_4A_5)A_6\).
- Kích thước tích trái \(30\times5\), tích phải \(5\times25\), nên phép nhân cuối cần `30×5×25=3750`.

Cộng lại:

\[
7875+3500+3750=\boxed{15125}.
\]

Một cách đặt ngoặc tối ưu là:

~~~text
((A1(A2A3))((A4A5)A6))
~~~

Có thể kiểm tra chi tiết:
- \(A_2A_3\) tốn `35×15×5 = 2625`.
- \(A_1(A_2A_3)\) tốn thêm `30×35×5 = 5250`, nên phần trái là `7875`.
- \(A_4A_5\) tốn `5×10×20 = 1000`.
- \((A_4A_5)A_6\) tốn thêm `5×20×25 = 2500`, nên phần phải là `3500`.
- Nhân hai tích tốn `30×5×25 = 3750`.

**Tổng = 15125**. Việc có cả chi phí và cây dấu ngoặc cho phép đối chiếu độc lập: cây được chọn phải có chi phí đúng bằng giá trị DP, không chỉ có hình thức dấu ngoặc đúng.

## 9. Chứng minh tính tối ưu bằng quy nạp trên độ dài

Ta chứng minh mệnh đề:

> Với mọi đoạn \([i,j]\), `m[i][j]` bằng số phép nhân vô hướng nhỏ nhất có thể đạt được bởi một cách đặt ngoặc hợp lệ của chuỗi \(A_i\cdots A_j\).

### Cơ sở: độ dài 1

Đoạn chỉ có \(A_i\) không yêu cầu phép nhân nào, nên chi phí tối ưu đúng bằng 0. Công thức `m[i][i]=0` là chính xác.

### Giả thiết quy nạp

Giả sử mọi đoạn có độ dài **nhỏ hơn L** đã được tính tối ưu theo công thức DP.

### Bước quy nạp cho độ dài L

Xét một cách đặt ngoặc **tối ưu bất kỳ** của đoạn \(A_i\cdots A_j\) dài L. Phép nhân cuối cùng của nó phải tách tại một k nào đó, với \(i\le k<j\), thành:
- Một cây cho đoạn \([i,k]\).
- Một cây cho đoạn \([k+1,j]\).
- Một phép nhân hai tích ở gốc.

Nếu cây bên trái không tối ưu, có thể thay bằng cây tối ưu của chính đoạn ấy mà vẫn giữ kích thước tích \(p_{i-1}\times p_k\) và không ảnh hưởng tính hợp lệ ở gốc. Điều này **không làm tăng chi phí**. Lập luận tương tự cho cây bên phải. Theo giả thiết quy nạp, chi phí hai cây con tối ưu là `m[i][k]` và `m[k+1][j]`; phép nhân cuối luôn có chi phí \(p_{i-1}p_kp_j\).

Vì thế, mọi cây có điểm tách gốc k có chi phí **ít nhất**:

\[
m[i][k]+m[k+1][j]+p_{i-1}p_kp_j.
\]

Ngược lại, ghép hai cây con tối ưu tại k **thực sự tạo được** một cách đặt ngoặc hợp lệ có đúng chi phí ấy. Bởi vậy giá trị nhỏ nhất trên mọi k chính là chi phí tối ưu của đoạn [i,j].

Quy nạp hoàn tất, suy ra `m[1][n]` là **chi phí nhỏ nhất toàn chuỗi**.

**Hai ý quan trọng trong chứng minh:** mọi phương án đều có một điểm tách k, nên công thức **không bỏ sót** trường hợp; và mỗi phương án mà công thức tính đều tương ứng với cây hợp lệ, nên **không tạo chi phí ảo**.

## 10. Khôi phục dấu ngoặc tối ưu bằng bảng split

Bảng `m` cho chi phí, nhưng nếu đề yêu cầu in thứ tự nhân, phải lưu **vị trí tách tối ưu**.

Với `split[i][j]=k`, việc khôi phục thực hiện đệ quy:

~~~text
printOrder(i, j):
    if i == j:
        in "A" + i
        return

    k = split[i][j]
    in "("
    printOrder(i, k)
    printOrder(k+1, j)
    in ")"
~~~

Hàm không thực hiện phép nhân ma trận; nó chỉ dựng **cú pháp biểu diễn một cây nhị phân**. Mỗi ma trận xuất hiện đúng một lần, từ trái sang phải theo thứ tự gốc.

Ví dụ với ba ma trận, `split[1][3]=2`, nên dấu ngoặc gốc chia \([1,2]\) và \([3,3]\). Đoạn [1,2] có điểm tách k=1; kết quả là:

~~~text
((A1A2)A3)
~~~

Với dãy sáu ma trận, bảng split cho dấu ngoặc:

~~~text
((A1(A2A3))((A4A5)A6))
~~~

Nếu có **nhiều thứ tự đạt cùng chi phí**, bảng split có thể lưu một trong chúng. Cách phá hòa quyết định thứ tự được in, nhưng không làm thay đổi giá trị tối ưu. Nếu bài yêu cầu **đếm tất cả thứ tự tối ưu** hoặc **liệt kê tất cả**, đó là một biến thể khác; bảng chỉ lưu một điểm tách tại mỗi đoạn là chưa đủ để đáp ứng.

### Phân biệt chỉ số 1-based và 0-based

Trong công thức sách giáo khoa: ma trận `A1..An`, kích thước `p[0..n]`, đoạn `[i,j]` với i bắt đầu từ 1:

\[
p_{i-1}\cdot p_k\cdot p_j.
\]

Trong mã Java dùng ma trận **0-based** `A1` ứng với chỉ số i=0, thì đoạn `[i,j]` với i,j từ 0 có:
- Kích thước tích trái: `p[i] × p[k+1]`.
- Kích thước tích phải: `p[k+1] × p[j+1]`.
- Chi phí nút gốc: `p[i] * p[k+1] * p[j+1]`.

Đây là một trong những vị trí dễ mắc lỗi **off-by-one** nhất. Trước khi triển khai, nên ghi chú quy ước chỉ số trực tiếp bên cạnh công thức.

## 11. Java 17: tối ưu thứ tự nhân và kiểm thử vét cạn

Chương trình sau thực hiện:
1. Kiểm tra dãy kích thước hợp lệ.
2. Tính bảng chi phí `cost[i][j]` theo độ dài đoạn tăng dần.
3. Lưu `split[i][j]` để dựng một chuỗi dấu ngoặc tối ưu.
4. So sánh kết quả với một hàm brute force **liệt kê tất cả cây tách** trên các chuỗi nhỏ.
5. In kết quả các ví dụ có đáp án xác định.

Trong mã, `i,j,k` là **chỉ số ma trận từ 0**, còn nhãn in ra là **A1, A2, ...** để dễ đọc. Chi phí dùng `long` và `Math.multiplyExact`/`Math.addExact` để tránh tính ra giá trị sai do tràn số im lặng.

~~~java
import java.util.Arrays;

public class MatrixChainOrderDemo {
    record Plan(long minMultiplications, String parentheses) {}

    static void validate(int[] dimensions) {
        if (dimensions == null || dimensions.length < 2) {
            throw new IllegalArgumentException(
                    "Need at least one matrix");
        }
        for (int d : dimensions) {
            if (d <= 0) {
                throw new IllegalArgumentException(
                        "Matrix dimensions must be positive");
            }
        }
    }

    static long rootCost(int[] p, int i, int k, int j) {
        // A_i..A_k: p[i] x p[k+1]
        // A_(k+1)..A_j: p[k+1] x p[j+1]
        long first = Math.multiplyExact(
                (long) p[i], (long) p[k + 1]);
        return Math.multiplyExact(first, (long) p[j + 1]);
    }

    static String parentheses(int[][] split, int i, int j) {
        if (i == j) {
            return "A" + (i + 1);
        }
        int k = split[i][j];
        return "(" + parentheses(split, i, k)
                + parentheses(split, k + 1, j) + ")";
    }

    static Plan optimize(int[] dimensions) {
        validate(dimensions);
        int n = dimensions.length - 1;
        long[][] cost = new long[n][n];
        int[][] split = new int[n][n];

        for (int[] row : split) {
            Arrays.fill(row, -1);
        }

        // Mỗi ma trận đơn lẻ không cần phép nhân: cost[i][i]=0.
        for (int length = 2; length <= n; length++) {
            for (int i = 0; i + length <= n; i++) {
                int j = i + length - 1;
                boolean found = false;
                long best = 0;
                int bestSplit = -1;

                for (int k = i; k < j; k++) {
                    long children = Math.addExact(
                            cost[i][k], cost[k + 1][j]);
                    long candidate = Math.addExact(
                            children, rootCost(dimensions, i, k, j));

                    // Chỉ dùng <, hòa thì giữ k nhỏ nhất.
                    if (!found || candidate < best) {
                        best = candidate;
                        bestSplit = k;
                        found = true;
                    }
                }
                cost[i][j] = best;
                split[i][j] = bestSplit;
            }
        }

        return new Plan(cost[0][n - 1],
                parentheses(split, 0, n - 1));
    }

    // Oracle: xét mọi điểm tách theo đệ quy, KHÔNG memo hóa.
    // Chỉ dùng cho chuỗi rất ngắn vì số cây tăng nhanh.
    static long brute(int[] p, int i, int j) {
        if (i == j) {
            return 0;
        }

        long best = Long.MAX_VALUE;
        for (int k = i; k < j; k++) {
            long left = brute(p, i, k);
            long right = brute(p, k + 1, j);
            long children = Math.addExact(left, right);
            long candidate = Math.addExact(
                    children, rootCost(p, i, k, j));
            best = Math.min(best, candidate);
        }
        return best;
    }

    static int verifySmall() {
        int checked = 0;

        // Với n=1..5, sinh mọi dãy kích thước dài n+1
        // với mỗi phần tử thuộc {1, 2, 3}.
        for (int n = 1; n <= 5; n++) {
            int combinations = 1;
            for (int t = 0; t <= n; t++) {
                combinations *= 3;
            }

            for (int code = 0; code < combinations; code++) {
                int remain = code;
                int[] p = new int[n + 1];
                for (int t = 0; t < p.length; t++) {
                    p[t] = 1 + remain % 3;
                    remain /= 3;
                }

                long expected = brute(p, 0, n - 1);
                Plan actual = optimize(p);
                if (actual.minMultiplications() != expected) {
                    throw new AssertionError(
                            "dimensions=" + Arrays.toString(p)
                            + ", expected=" + expected
                            + ", actual=" + actual.minMultiplications());
                }
                checked++;
            }
        }
        return checked;
    }

    static void printCase(String name, int[] dimensions) {
        Plan result = optimize(dimensions);
        System.out.println(name + "=" + result.minMultiplications()
                + " order=" + result.parentheses());
    }

    public static void main(String[] args) {
        printCase("simple", new int[]{10, 30, 5, 60});
        printCase("classic",
                new int[]{30, 35, 15, 5, 10, 20, 25});
        printCase("one", new int[]{7, 11});
        printCase("tie", new int[]{10, 10, 10, 10});
        System.out.println("verified=" + verifySmall());
    }
}
~~~

Lưu tệp **MatrixChainOrderDemo.java** và chạy bằng **JDK 17 trở lên**:

~~~bash
javac MatrixChainOrderDemo.java
java MatrixChainOrderDemo
~~~

**Đầu ra mong đợi:**

~~~text
simple=4500 order=((A1A2)A3)
classic=15125 order=((A1(A2A3))((A4A5)A6))
one=0 order=A1
tie=2000 order=(A1(A2A3))
verified=1089
~~~

### Giải thích các trường hợp chương trình in

- **simple:** dãy `[10,30,5,60]` có hai cách đặt ngoặc; chọn `((A1A2)A3)` với chi phí 4500, nhỏ hơn 27000.
- **classic:** dãy sáu ma trận có chi phí tối ưu 15125, dấu ngoặc như ví dụ ở phần 8.
- **one:** chỉ có ma trận A1 kích thước \(7\times11\); không có phép nhân ma trận nào, chi phí 0, dấu ngoặc là `A1`.
- **tie:** ba ma trận đều có kích thước \(10\times10\). Cả `((A1A2)A3)` và `(A1(A2A3))` đều tốn 2000. Do các k được thử tăng dần và không thay nghiệm khi bằng nhau, bản cài in `(A1(A2A3))` theo chính sách **k nhỏ nhất**.
- **verified:** tổng số dãy kích thước thử là `3²+3³+3⁴+3⁵+3⁶=9+27+81+243+729=1089`. Mỗi dãy được giải bằng DP và brute force trên **mọi cách tách hợp lệ**; hai chi phí phải bằng nhau.

Phép kiểm thử vét cạn là công cụ kiểm tra cài đặt, đặc biệt hữu ích để bắt lỗi chỉ số k, chiều mảng p, đoạn dài 1 và hòa chi phí. Nó **không thay thế** chứng minh quy nạp về tối ưu cho mọi dãy kích thước hợp lệ.

### Vì sao dùng boolean found thay cho chỉ Long.MAX_VALUE?

Trong bài có kích thước lớn, chi phí có thể bằng chính `Long.MAX_VALUE` nếu phép tính vẫn nằm trong miền `long`. Nếu khởi tạo `best=Long.MAX_VALUE` rồi chỉ cập nhật với điều kiện `candidate<best`, trường hợp bằng hẳn giá trị ấy sẽ **không ghi split**. Sử dụng cờ `found` bảo đảm ứng viên đầu tiên luôn được ghi; sau đó chỉ thay khi tốt hơn nghiêm ngặt.

**Giới hạn số học:** `Math.multiplyExact` hoặc `Math.addExact` có thể ném `ArithmeticException` khi kết quả trung gian vượt miền long, thay vì tạo đáp án sai. Khi cần xử lý kích thước cực lớn, có thể cân nhắc `BigInteger` với chi phí bộ nhớ và thời gian lớn hơn.

Tuy nhiên, chú ý một chi tiết nâng cao: trong cách cài dùng `long`, có thể một cách tách k không phù hợp vì chi phí **vượt long** dù tồn tại một cách tách khác có chi phí hợp lệ. Mã minh họa sẽ **báo lỗi ngay** khi gặp phép tính tràn; nó **không phải bộ giải BigInteger đầy đủ** có thể bỏ qua riêng một ứng viên tràn. Với đầu vào cần bảo đảm trên miền số rất lớn, phải chuyển **toàn bộ phép tính chi phí** sang kiểu hỗ trợ đủ độ lớn hoặc giới hạn đầu vào để mọi ứng viên vừa long.

## 12. Phân tích độ phức tạp

Với n ma trận:
- Có **\(n(n+1)/2 = Θ(n²)\)** đoạn \([i,j]\) không rỗng.
- Với một đoạn dài \(L\), phải thử \(L-1\) điểm tách.
- Tổng số ứng viên là:

\[
\sum_{L=2}^{n}(n-L+1)(L-1)
=\frac{n^3-n}{6}
=\Theta(n^3).
\]

Vì mỗi ứng viên tốn O(1) phép toán trên số có kích thước cố định trong mô hình chuẩn, **thời gian DP là Θ(n³)**. Nếu dùng BigInteger, phép toán trên số lớn không còn nhất thiết O(1), phải tính thêm chi phí theo độ dài bit.

**Bộ nhớ:** hai bảng `cost[n][n]` và `split[n][n]` tốn **Θ(n²)** ô. Hàm khôi phục dấu ngoặc gọi đệ quy theo cây, sâu nhiều nhất O(n) trong trường hợp lệch; chuỗi kết quả chứa n nhãn và \(n-1\) cặp ngoặc. Nếu coi độ dài nhãn `A1000` là nhiều ký tự, độ dài string tổng là O(n log n), còn theo số lượng ký hiệu ma trận là O(n).

Trong Java, việc nối chuỗi bằng toán tử `+` qua các lời gọi đệ quy có thể làm công việc xây chuỗi lớn hơn tuyến tính vì tạo nhiều chuỗi trung gian. Điều này **không thay đổi độ phức tạp Θ(n³) tổng quát của bước DP** trong bài học, nhưng nếu tối ưu phần in kết quả có thể dùng `StringBuilder` được truyền chung để tránh sao chép chuỗi nhiều lần.

### Vì sao không thể nói có O(n) thời gian?

Bài có n ma trận, nhưng phải quyết định cách nhóm **nhiều đoạn con** với **nhiều điểm tách**. Quy hoạch động giúp tránh việc duyệt số Catalan cây ngoặc, nhưng với công thức chuẩn vẫn có Θ(n³) phép thử. Đừng lẫn với:
- **Số phép nhân ma trận ở mọi cây đầy đủ:** luôn là n−1.
- **Số phép nhân vô hướng:** thay đổi theo kích thước trung gian, chính là giá trị muốn tối ưu.
- **Thời gian tìm thứ tự tối ưu:** số phép thử DP, thường Θ(n³) theo công thức trên.

Một cây luôn có đúng n−1 **nút nhân ma trận**, nhưng mỗi nút có thể tốn hàng nghìn hoặc hàng triệu phép nhân vô hướng khác nhau; vì vậy tối thiểu hóa **số nút** là vô nghĩa trong bài này.

## 13. Không thể chọn cặp rẻ nhất ngay lúc này rồi kỳ vọng tối ưu

Một heuristic dễ nghĩ: “tại mỗi bước, hãy nhân **hai ma trận kề nhau có chi phí thấp nhất** trước”. Nó có thể đúng trên một số ví dụ nhưng **không tối ưu tổng quát**.

Phản ví dụ ba ma trận với:

~~~text
p = [4, 1, 100, 5]

A1: 4 x 1
A2: 1 x 100
A3: 100 x 5
~~~

Chi phí **nhân cặp ban đầu**:
- \(A_1A_2\): `4×1×100 = 400`.
- \(A_2A_3\): `1×100×5 = 500`.

Heuristic “chọn cặp rẻ nhất trước” chọn \(A_1A_2\) vì 400 < 500. Nhưng:
- \((A_1A_2)A_3\): bước đầu 400; bước sau `4×100×5=2000` → **tổng 2400**.
- \(A_1(A_2A_3)\): bước đầu 500; bước sau `4×1×5=20` → **tổng 520**.

**520 < 2400**, nên heuristic chọn cặp có chi phí nhân ngay thấp nhất là **sai**.

Lý do: một phép nhân rẻ ở hiện tại có thể tạo ra **ma trận trung gian rất rộng hoặc cao**, khiến các phép nhân sau đắt hơn nhiều. Quy hoạch động phải cân nhắc cả chi phí các đoạn con **và chi phí nhân kết quả trung gian**, không chỉ một phép nhân kế cận.

Ví dụ này cũng nhấn mạnh: một chiến lược “có vẻ hợp lý” không thể được gọi là tối ưu nếu không có chứng minh. Một phản ví dụ hợp lệ đủ bác bỏ khẳng định “mọi chuỗi đều tối ưu”.

## 14. Điều kiện tiền đề và những biến thể dễ nhầm

### 14.1. Chuỗi ma trận phải tương thích

Mô hình p gồm n+1 số dương tự bảo đảm kích thước:

~~~text
A1: p0 x p1
A2: p1 x p2
...
An: p(n-1) x pn
~~~

Nếu đầu vào là danh sách các cặp `(rows[i],cols[i])` riêng biệt, phải kiểm tra `cols[i]==rows[i+1]` cho mọi i. Chẳng hạn \(10\times20\) và \(30\times5\) **không thể nhân trực tiếp**; không được gán bừa thành một dãy p liên tục.

### 14.2. Chỉ một ma trận, hoặc không có ma trận

- **n=1:** một ma trận duy nhất, chi phí nhân vô hướng là 0; in `A1`.
- **n=2:** chỉ có một cách tách, chi phí `p0*p1*p2`.
- **n=0:** không có chuỗi nhân theo định nghĩa bài này. Mã Java từ chối `dimensions.length < 2`, thay vì truy cập `cost[0][-1]`.

### 14.3. Kích thước 0, âm hoặc rất lớn

Trong bài học, mọi kích thước phải **dương**. Giá trị 0 hoặc âm không thuộc mô hình đã chọn; hàm validate từ chối. Trong các hệ thống toán học có thể định nghĩa ma trận suy biến với chiều 0, nhưng đó là quy ước khác, không nên tự động suy ra chi phí và trường hợp cơ sở của bài này.

Nếu `p[i]` lớn, tích ba kích thước có thể vượt `int`, nên không được tính bằng int rồi gán vào long sau. Phải nâng sang long **trước** phép nhân và xử lý tràn long khi cần. Dữ liệu đủ lớn có thể đòi BigInteger hoặc một giới hạn tài nguyên riêng.

### 14.4. Nhiều thứ tự cùng tối ưu

Với `p=[10,10,10,10]`, cả hai cách cho ba ma trận đều có tổng 2000. Không thể kết luận kết quả phải in đúng **một** chuỗi ngoặc nếu đề chỉ yêu cầu chi phí tối ưu. Khi kiểm thử, nên tách:
- **Kiểm tra chi phí:** đúng một giá trị min.
- **Kiểm tra cây:** hợp lệ, giữ thứ tự và có chi phí đúng bằng min.
- **Kiểm tra chuỗi in chính xác:** chỉ áp dụng nếu quy tắc phá hòa đã được định nghĩa.

### 14.5. Chi phí thời gian thực không nhất thiết tỷ lệ tuyệt đối số phép nhân

Khi dùng CPU/GPU, nhân block, thư viện BLAS, nhân ma trận thưa hoặc thuật toán nhân nhanh, hai thứ tự có thể khác nhau về chi phí đọc/ghi, bộ nhớ đệm, song song hóa và lượng phép cộng. Bài DP chuẩn chỉ tối ưu **tổng số phép nhân vô hướng theo mô hình \(a b c\)**.

Nếu muốn tối ưu **đỉnh bộ nhớ**, **thời gian wall-clock**, **trung gian thưa** hoặc **kích thước tensor**, trạng thái và hàm mục tiêu có thể thay đổi. Không thể tự khẳng định chuỗi ngoặc tối thiểu phép nhân cũng luôn tối thiểu RAM hay chạy nhanh nhất trên mọi phần cứng.

### 14.6. Cách đặt ngoặc khác việc đổi thứ tự ma trận

Tính kết hợp \((AB)C=A(BC)\) cho phép thay **vị trí dấu ngoặc**, không cho phép đổi thứ tự \((BA)C\). Đối với ma trận nói chung, \(AB\ne BA\), và đôi khi \(BA\) còn không xác định nếu kích thước không khớp. Trạng thái DP theo đoạn giữ nguyên thứ tự lá là bắt buộc.

## 15. Các lỗi lập trình thường gặp và cách tránh

| Lỗi | Hậu quả | Cách kiểm tra |
| --- | --- | --- |
| Nhầm số ma trận n với số kích thước p | Sai kích thước bảng hoặc vượt chỉ số | `n=p.length-1` |
| Dùng `p[i]*p[k]*p[j]` trong mã 0-based | Sai chi phí ở nút gốc | Mã 0-based dùng `p[i]*p[k+1]*p[j+1]` |
| Đọc `cost[i][j]` trước khi đoạn con sẵn sàng | Chi phí sai do ô 0 mặc định | Điền theo `length` tăng |
| Quên `m[i][i]=0` | Tính sai base case | Một ma trận không cần nhân |
| Chỉ thử k ở giữa | Bỏ qua thứ tự tối ưu lệch | Thử tất cả `i<=k<j` |
| Chọn phép nhân cặp rẻ nhất tại thời điểm hiện tại | Có thể không tối ưu | Dùng phản ví dụ p=[4,1,100,5] |
| Không lưu split | Có chi phí nhưng không thể in một thứ tự tối ưu từ bảng cuối | Lưu `split[i][j]` lúc cập nhật |
| Dùng `<=` khi muốn giữ k nhỏ nhất | Dấu ngoặc đổi khi hòa | Chỉ cập nhật với `<` |
| Lấy `Long.MAX_VALUE` làm sentinel rồi không ghi ứng viên bằng nó | split có thể chưa có giá trị | Dùng cờ `found` |
| Tính phép nhân trong int | Tràn trước khi gán long | Ép long trước và kiểm tra overflow |
| Khôi phục dấu ngoặc sai khoảng | Lặp lá, bỏ lá hoặc đệ quy vô hạn | [i,k] và [k+1,j] |
| Giả định DP tính ma trận tích | Hiểu sai đầu ra | DP chỉ tìm chi phí + thứ tự |
| Tối ưu số bước nhân ma trận n−1 | Đại lượng không thay đổi giữa các cây | Tối ưu số phép nhân **vô hướng** |
| Tuyên bố luôn nhanh nhất khi chạy thật | Bỏ qua mô hình bộ nhớ và thư viện | Nói rõ giả thiết mô hình \(abc\) |

### Một lỗi phụ thuộc ít được chú ý

Có người viết vòng `i` tăng từ 0 đến n−1, rồi `j` tăng từ i đến n−1, và tin rằng hai đoạn con của mọi điểm tách đã được điền. Điều này **không được bảo đảm**, vì `cost[k+1][j]` có thể nằm ở hàng lớn hơn i **chưa được tính**. Cần dùng vòng **length** tăng dần, hoặc một thứ tự có chứng minh khác, thay vì dựa vào thứ tự duyệt bảng tùy ý.

## 16. Kiểm thử tính đúng và đối chiếu bằng brute force

Bộ kiểm thử nên gồm:
- **Một ma trận:** chi phí 0, dấu ngoặc chỉ là A1.
- **Hai ma trận:** chi phí đúng bằng tích ba kích thước.
- **Ba ma trận lệch kích thước:** xác minh hai cách ngoặc có chi phí khác nhau.
- **Mọi chiều bằng nhau:** có nhiều cách tối ưu, kiểm tra chính sách phá hòa.
- **Kích thước bằng 1:** bắt lỗi lập chỉ số và xử lý các chi phí nhỏ.
- **Dãy dài hơn:** kiểm tra đoạn con nhiều tầng, như p có bảy số cho sáu ma trận.
- **Dữ liệu không hợp lệ:** null, p chỉ có một phần tử, chiều 0 hoặc âm, từ chối theo hợp đồng.
- **Chi phí lớn:** kiểm tra overflow long hoặc chọn dùng BigInteger, không để im lặng thành số âm.
- **Vị trí tách không ở giữa:** ví dụ phản ví dụ greedy hoặc chuỗi có kích thước rất khác nhau.

Một oracle đơn giản trên n rất nhỏ là **đệ quy thử mọi điểm tách** mà không ghi nhớ kết quả. Vì mỗi điểm tách sinh hai cây con, oracle liệt kê mọi cấu trúc cây ngoặc; lấy min các chi phí là đáp án chuẩn cho miền nhỏ.

Chương trình Java đi kèm đã đối chiếu **1089 dãy kích thước** với oracle này. Một phép kiểm thử mạnh hơn có thể tái tính chi phí trực tiếp từ **chuỗi split** và xác nhận:
1. Mọi ma trận xuất hiện đúng một lần theo thứ tự.
2. Mọi phép nhân có kích thước hợp lệ.
3. Tổng chi phí của cây khớp `minMultiplications`.

**Một triệu ca đúng không thay thế chứng minh tổng quát**, nhưng cùng với bất biến, kiểm thử giúp phát hiện bug cài đặt và các trường hợp biên.

## 17. Bài tập tự luyện và đáp án

**Bài 1 — hai cách đặt ngoặc.** Cho p=[10,30,5,60]. Tính chi phí của \((A_1A_2)A_3\) và \(A_1(A_2A_3)\).

*Đáp án:* Cách trái là `10×30×5 + 10×5×60 = 4500`; cách phải là `30×5×60 + 10×30×60 = 27000`. Tối ưu là 4500.

**Bài 2 — điền bảng hai độ dài.** Cho p=[5,10,3,12]. Tính `m[1][2]` và `m[2][3]`.

*Đáp án:* `m[1][2]=5×10×3=150`; `m[2][3]=10×3×12=360`.

**Bài 3 — chọn điểm tách.** Với p=[5,10,3,12], tính `m[1][3]` qua hai giá trị k.

*Đáp án:* k=1: `0+360+5×10×12=960`. k=2: `150+0+5×3×12=330`. Vậy `m[1][3]=330`, thứ tự `((A1A2)A3)`.

**Bài 4 — hiểu base case.** Nếu có đúng một ma trận A1 kích thước 7×11, vì sao chi phí tối ưu là 0 chứ không phải 77?

*Đáp án:* Không cần nhân A1 với ma trận nào. Số 77 là số phần tử trong ma trận, không phải số phép nhân vô hướng để tính chuỗi.

**Bài 5 — mô phỏng split.** Dãy sáu ma trận với p=[30,35,15,5,10,20,25] có `split[1][6]=3`, `split[1][3]=1`, `split[4][6]=5`. Viết dấu ngoặc đầy đủ.

*Đáp án:* `((A1(A2A3))((A4A5)A6))`. Chi phí tổng tối ưu 15125.

**Bài 6 — phản ví dụ greedy.** Với p=[4,1,100,5], việc chọn cặp kề có chi phí nhân ngay nhỏ nhất trước cho đáp án gì? Tối ưu là gì?

*Đáp án:* Greedy chọn A1A2 tốn 400 rồi nhân với A3 tốn 2000, tổng 2400. Chọn A2A3 trước tốn 500 rồi A1 nhân kết quả tốn 20, tổng tối ưu 520.

**Bài 7 — độ phức tạp.** Vì sao số trạng thái O(n²) nhưng thời gian lại O(n³)?

*Đáp án:* Mỗi đoạn [i,j] cần thử tới j−i điểm tách k. Tổng số ứng viên trên mọi độ dài là \((n^3-n)/6\), nên thời gian Θ(n³).

**Bài 8 — 0-based với Java.** Cho dimensions=[10,30,5,60], đoạn `i=0, j=2`, tách `k=1`. Chi phí nút gốc theo công thức 0-based là gì?

*Đáp án:* `p[0]*p[2]*p[3] = 10×5×60 = 3000`. Kết hợp với đoạn trái tốn 1500 được tổng 4500.

**Bài 9 — hòa chi phí.** Ba ma trận 10×10 có mấy cách đặt ngoặc, và chi phí của chúng?

*Đáp án:* Hai cách, cả hai đều có chi phí \(1000+1000=2000\). Nếu duyệt k tăng và cập nhật khi nhỏ hơn nghiêm ngặt, chọn k=1 trong hệ 1-based, in `(A1(A2A3))`.

**Bài 10 — biến thể mục tiêu.** Nếu đề yêu cầu ít bộ nhớ trung gian nhất thay vì ít phép nhân vô hướng nhất, có thể dùng nguyên m[i][j] và công thức min chi phí như trên không?

*Đáp án:* Không tự động. Kích thước và thời gian sống của các trung gian phụ thuộc lịch thực thi; có thể cần trạng thái hoặc hàm mục tiêu mới, thậm chí phải xét đánh đổi nhiều tiêu chí.

## Ghi nhớ

- **Bài toán:** tìm cách đặt ngoặc cho \(A_1A_2\cdots A_n\) theo **thứ tự cố định**, giảm tổng số phép nhân vô hướng.
- **Dữ liệu:** \(A_i\) có kích thước \(p_{i-1}\times p_i\), nên chỉ cần dãy kích thước p dài n+1.
- **Trạng thái:** `m[i][j]` là chi phí tối ưu của đoạn \(A_i\cdots A_j\); `m[i][i]=0`.
- **Chuyển:** thử mọi k giữa i và j−1, lấy `m[i][k]+m[k+1][j]+p[i-1]*p[k]*p[j]`.
- **Thứ tự tính:** tăng **độ dài đoạn**, vì các đoạn con ngắn hơn phải có giá trị trước.
- **Khôi phục:** lưu `split[i][j]`, đệ quy in hai cây con theo dấu ngoặc.
- **Độ phức tạp chuẩn:** Θ(n³) thời gian, Θ(n²) bộ nhớ cho hai bảng.
- **Đúng đắn:** chứng minh quy nạp theo độ dài đoạn và tính tối ưu của hai cây con.
- **Không dùng greedy tùy ý:** cặp rẻ nhất ở bước hiện tại có thể dẫn tới chi phí toàn chuỗi rất lớn.
- **Không đánh đồng mô hình:** min phép nhân vô hướng không mặc nhiên là min bộ nhớ, I/O hoặc wall-clock; Java 0-based cần công thức chỉ số đúng và kiểm tra tràn số.

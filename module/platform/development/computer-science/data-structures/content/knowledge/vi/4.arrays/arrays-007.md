# Mảng nhiều chiều và cách trải phẳng theo hàng hoặc theo cột

## 1. Từ bảng dữ liệu đến mảng nhiều chiều

Mảng một chiều dùng một chỉ số để xác định phần tử, chẳng hạn `A[3]`. Khi dữ liệu có cấu trúc bảng, ảnh, khối không gian hoặc nhiều thuộc tính phân cấp, ta thường muốn dùng **nhiều chỉ số**: `M[i][j]` cho phần tử ở hàng `i` và cột `j`, hoặc `V[i][j][k]` cho phần tử trong không gian ba chiều.

Ví dụ, một lớp học ghi số học sinh tham gia ba hoạt động trong hai ngày:

```text
                 Cột 0    Cột 1    Cột 2
Ngày / Hàng 0      11       12       13
Ngày / Hàng 1      21       22       23
```

Đây là ma trận `2 × 3`: có `2` hàng và `3` cột. Phần tử `M[1][2]` bằng `23`, vì chỉ số `1` chọn hàng thứ hai và chỉ số `2` chọn cột thứ ba theo quy ước đánh số từ `0`.

Ở mức **logic**, ta nhìn dữ liệu như một bảng. Nhưng bộ nhớ máy tính thường được địa chỉ hóa theo một dãy các vị trí. Nếu muốn lưu toàn bộ các phần tử trong **một vùng liên tiếp**, ta cần quy tắc biến cặp chỉ số `(i, j)` thành **một chỉ số tuyến tính**. Quá trình ấy gọi là **trải phẳng** (*flattening*, hay *linearization*).

Sau bài học, bạn có thể:

- Phân biệt **hình dạng** (*shape*), miền chỉ số và cách bố trí vật lý của mảng nhiều chiều.
- Trải phẳng ma trận theo **hàng** (*row-major*) hoặc **cột** (*column-major*) và tính chỉ số tuyến tính.
- Tính địa chỉ phần tử từ chỉ số và kích thước ô nhớ; đảo chỉ số tuyến tính về cặp `(i, j)`.
- Mở rộng phép tính sang ba chiều và số chiều bất kỳ.
- Hiểu `stride`, vùng đệm cuối hàng, khung nhìn chuyển vị và giới hạn của mảng lồng nhau.
- Giải thích tác động đến độ phức tạp, bộ nhớ đệm và lựa chọn cách lưu dữ liệu.

Đây là phần kiến thức của chương **Mảng** thuộc học phần **Cấu trúc dữ liệu**, kết nối cách tổ chức bộ nhớ, bất biến và độ phức tạp với việc lựa chọn các cấu trúc như danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Hình dạng và chỉ số hợp lệ

Cho ma trận `M` có `R` hàng, `C` cột. Hình dạng của ma trận là `(R, C)`, tổng số phần tử là `R × C` nếu tất cả hàng đều có đúng `C` phần tử.

Với quy ước bắt đầu từ `0`, một tọa độ `(i, j)` hợp lệ khi và chỉ khi:

\[
0 \le i < R,\qquad 0 \le j < C
\]

Ta có thể mô tả mảng hai chiều như ánh xạ:

\[
M:\{0,\ldots,R-1\}\times\{0,\ldots,C-1\}\longrightarrow T
\]

Trong đó `T` là tập giá trị của phần tử, ví dụ các số nguyên. Cặp `(i, j)` xác định vị trí logic, còn `M[i][j]` là giá trị tại vị trí ấy.

Một vài trường hợp biên cần ghi nhớ:

| Hình dạng | Số phần tử | Có thể truy cập phần tử không? |
|---|---:|---|
| `(2, 3)` | `6` | Có, `0 <= i < 2` và `0 <= j < 3` |
| `(1, 4)` | `4` | Có, chỉ hàng `0` |
| `(3, 1)` | `3` | Có, chỉ cột `0` |
| `(0, 5)` | `0` | Không có hàng hợp lệ |
| `(4, 0)` | `0` | Không có cột hợp lệ |

**Chỉ số hàng và chỉ số cột có vai trò khác nhau.** `(1, 2)` không phải `(2, 1)`. Kể cả khi `R = C`, đổi vị trí hai chỉ số thường dẫn tới hai phần tử khác nhau.

Không phải mọi danh sách lồng nhau đều tạo thành ma trận chữ nhật. Chẳng hạn `[[1, 2], [3]]` có hai hàng dài khác nhau (*jagged/ragged array*); với dữ liệu này, không thể mặc nhiên dùng một số cột `C` chung trong công thức trải phẳng.

## 3. Trải phẳng theo hàng: row-major

Trong cách bố trí **theo hàng**, các phần tử của hàng đầu tiên nằm liên tiếp, tiếp theo là tất cả phần tử của hàng thứ hai, rồi đến hàng thứ ba, v.v.

```text
Ma trận M:
              j=0    j=1    j=2
       i=0     11     12     13
       i=1     21     22     23

Dãy trải phẳng theo hàng:
        [11, 12, 13, 21, 22, 23]
Chỉ số:   0   1   2   3   4   5
                ↑           ↑
           hết hàng 0   hết hàng 1
```

Trước phần tử `M[i][j]` có:

1. `i` hàng hoàn chỉnh, mỗi hàng có `C` phần tử, đóng góp `i × C` ô.
2. `j` phần tử đứng trước nó trong chính hàng `i`.

Vì vậy, **chỉ số phẳng theo hàng** là:

\[
\boxed{\operatorname{index}_{row}(i,j)=i\times C+j}
\]

Ví dụ với `R = 2`, `C = 3`:

| Tọa độ `(i, j)` | Công thức | Chỉ số phẳng | Giá trị |
|---|---|---:|---:|
| `(0, 0)` | `0×3+0` | `0` | `11` |
| `(0, 2)` | `0×3+2` | `2` | `13` |
| `(1, 0)` | `1×3+0` | `3` | `21` |
| `(1, 1)` | `1×3+1` | `4` | `22` |
| `(1, 2)` | `1×3+2` | `5` | `23` |

Chỉ số lớn nhất là `R × C - 1` nếu `R > 0` và `C > 0`. Với tọa độ cuối `(R-1, C-1)`:

\[
(R-1)C+(C-1)=RC-1
\]

Đây cũng là một cách tự kiểm tra công thức. Nếu tính được chỉ số `RC` cho một phần tử hợp lệ thì đã có sai sót.

### Địa chỉ byte khi lưu theo hàng

Giả sử mỗi phần tử có kích thước `s` byte, ô đầu tiên ở địa chỉ `base`, tất cả ô nằm liên tiếp và có kích thước bằng nhau:

\[
\boxed{\operatorname{addr}_{row}(M[i][j])=base+(iC+j)s}
\]

Ví dụ, ma trận `3 × 4` dùng ô rộng `8` byte, `base = 2000`. Ô `M[2][1]` có chỉ số phẳng `2 × 4 + 1 = 9`, nên địa chỉ bắt đầu là `2000 + 9 × 8 = 2072`.

Mảng nhiều chiều thông thường khai báo dạng `int matrix[3][4]` trong C có cách bố trí **theo hàng**: các phần tử trong một hàng nằm sát nhau, kế tiếp mới tới hàng sau. Kích thước thực tế mỗi ô phụ thuộc `sizeof(int)` của nền tảng; không nên mặc định mọi `int` chiếm đúng bốn byte.

## 4. Trải phẳng theo cột: column-major

Trong cách bố trí **theo cột**, các phần tử của cột đầu tiên nằm liên tiếp; tiếp theo là cột thứ hai, rồi cột thứ ba.

```text
Vẫn là ma trận M:
              j=0    j=1    j=2
       i=0     11     12     13
       i=1     21     22     23

Dãy trải phẳng theo cột:
        [11, 21, 12, 22, 13, 23]
Chỉ số:   0   1   2   3   4   5
              ↑       ↑       ↑
            cột 0   cột 1   cột 2
```

Trước phần tử `M[i][j]` có:

1. `j` cột hoàn chỉnh, mỗi cột có `R` phần tử, đóng góp `j × R` ô.
2. `i` phần tử đứng trước nó trong chính cột `j`.

Vì vậy, **chỉ số phẳng theo cột** là:

\[
\boxed{\operatorname{index}_{col}(i,j)=j\times R+i}
\]

Với `R = 2`, `C = 3`:

| Tọa độ `(i, j)` | Công thức | Chỉ số phẳng | Giá trị |
|---|---|---:|---:|
| `(0, 0)` | `0×2+0` | `0` | `11` |
| `(1, 0)` | `0×2+1` | `1` | `21` |
| `(0, 1)` | `1×2+0` | `2` | `12` |
| `(1, 1)` | `1×2+1` | `3` | `22` |
| `(0, 2)` | `2×2+0` | `4` | `13` |
| `(1, 2)` | `2×2+1` | `5` | `23` |

Địa chỉ byte khi dữ liệu liên tiếp theo cột:

\[
\boxed{\operatorname{addr}_{col}(M[i][j])=base+(jR+i)s}
\]

Với cùng ví dụ ma trận `3 × 4`, `base = 2000`, `s = 8`, ô `M[2][1]` có chỉ số phẳng `1 × 3 + 2 = 5`, nên địa chỉ là `2000 + 5 × 8 = 2040`.

**Tọa độ logic và giá trị phần tử không thay đổi khi đổi cách trải phẳng.** `M[2][1]` vẫn chỉ cùng một ô trong ma trận; vị trí byte thay đổi vì thứ tự bố trí vật lý khác nhau. Các ngôn ngữ và thư viện có thể chọn những bố trí khác nhau: C dùng row-major cho mảng nhiều chiều thực sự; Fortran thường dùng column-major cho mảng thông thường.

## 5. So sánh trực tiếp hai quy ước

| Thuộc tính | Row-major (theo hàng) | Column-major (theo cột) |
|---|---|---|
| Các phần tử nằm cạnh nhau | Cùng hàng, cột tăng dần | Cùng cột, hàng tăng dần |
| Chỉ số phẳng `(i, j)` | `i*C + j` | `j*R + i` |
| Địa chỉ byte | `base + (i*C+j)*s` | `base + (j*R+i)*s` |
| Duyệt liên tiếp theo bộ nhớ | Vòng ngoài theo hàng, vòng trong theo cột | Vòng ngoài theo cột, vòng trong theo hàng |
| Bước giữa hai ô cùng hàng hoặc cột gần nhau | Tăng cột: `s` byte | Tăng hàng: `s` byte |
| Bước để sang hàng/cột kế tiếp | Tăng hàng: `C*s` byte | Tăng cột: `R*s` byte |

Một lỗi phổ biến là học thuộc `i*C+j` rồi áp dụng cho mọi mảng hai chiều. Công thức ấy chỉ đúng khi **đã biết bố trí theo hàng** và các ô thực sự nằm liên tiếp theo giả định đang xét. Với dữ liệu theo cột, công thức đúng là `j*R+i`.

## 6. Đổi chỉ số phẳng về tọa độ hàng và cột

Phép trải phẳng đúng có thể đảo ngược. Cho chỉ số phẳng `k` với `0 <= k < R*C` và ma trận không rỗng.

### Nếu mảng theo hàng

Vì mỗi hàng chứa `C` ô, phép chia nguyên cho `C` trả về số hàng hoàn chỉnh đứng trước `k`; phần dư cho biết vị trí trong hàng:

\[
\boxed{i=\left\lfloor\frac{k}{C}\right\rfloor,\qquad j=k\bmod C}
\]

Ví dụ `R = 3`, `C = 4`, `k = 9`:

\[
i=\lfloor9/4\rfloor=2,\quad j=9\bmod4=1
\]

Tọa độ thu được là `(2, 1)`, đúng với công thức `2×4+1=9`.

### Nếu mảng theo cột

Mỗi cột chứa `R` ô, nên:

\[
\boxed{i=k\bmod R,\qquad j=\left\lfloor\frac{k}{R}\right\rfloor}
\]

Với `R = 3`, `C = 4`, `k = 5`, ta được `i = 5 mod 3 = 2` và `j = floor(5/3) = 1`, vẫn là ô `(2, 1)`.

Để đảo chỉ số, cần biết cả **hình dạng** và **quy ước bố trí**. Một dãy `12` giá trị phẳng không tự cho biết nó là ma trận `3 × 4`, `2 × 6` hay `4 × 3`.

## 7. Triển khai và kiểm tra bằng Python

Ta có thể dùng một danh sách một chiều để tự mô phỏng cả hai cách bố trí. Các hàm sau kiểm tra chỉ số trước khi tính vị trí phẳng:

```python
def index_row_major(i: int, j: int, rows: int, cols: int) -> int:
    if rows < 0 or cols < 0:
        raise ValueError("Kích thước không được âm")
    if not (0 <= i < rows and 0 <= j < cols):
        raise IndexError("Tọa độ nằm ngoài ma trận")
    return i * cols + j


def index_column_major(i: int, j: int, rows: int, cols: int) -> int:
    if rows < 0 or cols < 0:
        raise ValueError("Kích thước không được âm")
    if not (0 <= i < rows and 0 <= j < cols):
        raise IndexError("Tọa độ nằm ngoài ma trận")
    return j * rows + i


matrix = [
    [11, 12, 13],
    [21, 22, 23],
]
rows = len(matrix)
cols = len(matrix[0]) if rows else 0
if any(len(row) != cols for row in matrix):
    raise ValueError("Các hàng phải có cùng số cột")

data_row = [matrix[i][j]
            for i in range(rows) for j in range(cols)]
data_col = [matrix[i][j]
            for j in range(cols) for i in range(rows)]

print(data_row)  # [11, 12, 13, 21, 22, 23]
print(data_col)  # [11, 21, 12, 22, 13, 23]

print(data_row[index_row_major(1, 2, rows, cols)])     # 23
print(data_col[index_column_major(1, 2, rows, cols)])  # 23
```

Trong mã này, `matrix` ban đầu là **danh sách các danh sách** của Python. Hai biến `data_row` và `data_col` mới là các danh sách một chiều mô phỏng việc trải phẳng. Không nên giả định danh sách lồng nhau ban đầu được CPython lưu như một khối số nguyên hai chiều liên tiếp.

Hàm đảo tọa độ cho hai quy ước:

```python
def coordinates_row_major(k: int, rows: int, cols: int) -> tuple[int, int]:
    if not 0 <= k < rows * cols:
        raise IndexError("Chỉ số phẳng không hợp lệ")
    return divmod(k, cols)  # (hàng, cột)


def coordinates_column_major(k: int, rows: int, cols: int) -> tuple[int, int]:
    if not 0 <= k < rows * cols:
        raise IndexError("Chỉ số phẳng không hợp lệ")
    col, row = divmod(k, rows)
    return row, col


print(coordinates_row_major(4, 2, 3))     # (1, 1)
print(coordinates_column_major(3, 2, 3))  # (1, 1)
```

Với `rows = 0` hoặc `cols = 0`, không tồn tại `k` thỏa `0 <= k < rows*cols`, nên hai hàm đều từ chối trước khi chia cho `0`. Trong chương trình sản xuất, nên kiểm tra riêng kích thước âm của các chiều ngay khi tạo cấu trúc; ví dụ trên tập trung vào điều kiện chỉ số.

## 8. Mảng ba chiều: thêm một chiều, thêm một hệ số

Một mảng ba chiều có hình dạng `(D_0, D_1, D_2)`, với tọa độ `(i, j, k)` thỏa:

\[
0\le i<D_0,\qquad0\le j<D_1,\qquad0\le k<D_2
\]

Ví dụ: dữ liệu `2` khung thời gian, mỗi khung có `3` hàng và `4` cột, tổng cộng `2×3×4=24` phần tử.

### Trải phẳng ba chiều theo hàng

Chiều cuối cùng thay đổi nhanh nhất. Để đến `V[i][j][k]`, ta đi qua `i` khối cỡ `D_1×D_2`, tiếp theo `j` hàng cỡ `D_2`, rồi `k` phần tử:

\[
\boxed{\operatorname{index}_{row}(i,j,k)
=iD_1D_2+jD_2+k
=(iD_1+j)D_2+k}
\]

Với `(D_0,D_1,D_2)=(2,3,4)` và tọa độ `(1,0,2)`, chỉ số phẳng là `1×3×4+0×4+2=14`.

### Trải phẳng ba chiều theo cột

Chiều đầu tiên thay đổi nhanh nhất. Công thức là:

\[
\boxed{\operatorname{index}_{col}(i,j,k)
=i+jD_0+kD_0D_1}
\]

Với cùng hình dạng và tọa độ `(1,0,2)`, chỉ số phẳng là `1+0×2+2×2×3=13`. Hai cách bố trí cho kết quả khác nhau nhưng đều truy cập cùng một phần tử logic.

### Tổng quát cho `d` chiều

Với hình dạng `(D_0,D_1,\ldots,D_{d-1})` và tọa độ `(i_0,i_1,\ldots,i_{d-1})`:

\[
\operatorname{index}_{row}
=\sum_{k=0}^{d-1}i_k\prod_{j=k+1}^{d-1}D_j
\]

\[
\operatorname{index}_{col}
=\sum_{k=0}^{d-1}i_k\prod_{j=0}^{k-1}D_j
\]

Tích rỗng được hiểu bằng `1`. Công thức row-major dùng **tích kích thước các chiều phía sau** làm hệ số; column-major dùng **tích các chiều phía trước**. Nếu mỗi phần tử rộng `s` byte, địa chỉ phần tử là `base + index × s`.

Trong thực hành, thay vì học thuộc công thức tổng quát, có thể suy ra từng bước từ cách các chiều tăng: chiều nào tăng nhanh nhất có bước `1` ô; mỗi chiều chậm hơn có bước bằng tích kích thước của các chiều nhanh hơn.

## 9. Stride: tổng quát hóa cách tính địa chỉ

Đối với mảng liên tiếp thông thường, bước giữa hai phần tử cùng hàng là `s` byte (row-major), còn bước giữa hai hàng kế tiếp là `C×s` byte. Hai giá trị bước này gọi là **stride**.

Đặt:

- `stride_row`: số byte tăng thêm khi chuyển từ `(i, j)` sang `(i+1, j)`.
- `stride_col`: số byte tăng thêm khi chuyển từ `(i, j)` sang `(i, j+1)`.

Khi tọa độ hợp lệ và dữ liệu dùng cách định địa chỉ tuyến tính đều đặn:

\[
\boxed{\operatorname{addr}(M[i][j])
=base+i\times stride_{row}+j\times stride_{col}}
\]

| Bố trí liên tiếp chuẩn | `stride_row` | `stride_col` |
|---|---:|---:|
| Theo hàng | `C*s` | `s` |
| Theo cột | `s` | `R*s` |

Các **view** (khung nhìn) hoặc bộ đệm có **khoảng đệm cuối hàng** có thể có stride khác công thức chuẩn.

### Ví dụ: ảnh có khoảng đệm ở cuối hàng

Một ảnh có `2` hàng, mỗi hàng `3` điểm ảnh; mỗi điểm ảnh một số nguyên rộng `4` byte. Dữ liệu hữu ích mỗi hàng chiếm `3×4 = 12` byte. Giả sử vùng đệm dành **16 byte cho một hàng** để đáp ứng yêu cầu căn chỉnh:

```text
Hàng 0: [pixel(0,0)][pixel(0,1)][pixel(0,2)][padding 4 byte]
Hàng 1: [pixel(1,0)][pixel(1,1)][pixel(1,2)][padding 4 byte]
         <-------------- 16 byte mỗi hàng -------------->
```

Khi đó `stride_row = 16` và `stride_col = 4`. Với `base = 1000`, điểm ảnh `(1, 2)` bắt đầu tại:

\[
1000+1\times16+2\times4=1024
\]

Nếu dùng công thức liên tiếp không có padding `base + (1×3+2)×4`, ta sẽ tính sai thành `1020`. Vì thế, khi làm việc với ảnh, tensor, ma trận từ thư viện ngoài hoặc dữ liệu được chia sẻ giữa các hệ thống, **phải đọc thông tin stride thực tế**.

### Chuyển vị có thể chỉ thay đổi cách nhìn

Chuyển vị ma trận biến tọa độ `(i,j)` thành `(j,i)`. Nếu giao diện thư viện hỗ trợ **view không sao chép**, có thể thực hiện phép chuyển vị bằng cách đổi hình dạng từ `(R,C)` thành `(C,R)` và hoán đổi hai stride; giá trị trong vùng nhớ gốc không cần di chuyển.

Điều này có nghĩa view chuyển vị của một ma trận row-major thường **không còn liên tiếp theo hàng** theo trật tự logic mới. Nếu cần một bản sao thực sự được sắp lại theo cách lưu mới, phải đi qua `R×C` phần tử để sao chép, tốn `O(RC)` thời gian và bộ nhớ cho bản sao.

## 10. Mảng lồng nhau khác một khối nhớ hai chiều liên tiếp

Ký hiệu `M[i][j]` nói lên **giao diện truy cập**, chưa đủ để kết luận dữ liệu nằm liền nhau trong bộ nhớ.

| Cách biểu diễn | Cách lưu thường gặp | Hệ quả |
|---|---|---|
| Mảng thực sự trong C, ví dụ `int a[2][3]` | Hai hàng liên tiếp trong một khối row-major | Có thể tính địa chỉ theo `(i*C+j)*sizeof(int)` |
| `list[list[int]]` trong Python | Danh sách ngoài chứa tham chiếu tới từng danh sách hàng | Các hàng và đối tượng số nguyên không bảo đảm nằm trong một khối liên tiếp |
| Mảng răng cưa, ví dụ `[[1,2,3],[4]]` | Mỗi hàng có độ dài riêng | Không có `C` cố định để dùng công thức `i*C+j` |
| Bộ đệm phẳng `data` kèm `shape` và `strides` | Một vùng dữ liệu tuyến tính với quy tắc định địa chỉ | Có thể hỗ trợ cả bố trí theo hàng, theo cột, padding, view |

Trong C, `int a[2][3]` không giống `int **p`: `a` chứa hai mảng con, mỗi mảng con ba `int` liên tiếp, còn `p` là con trỏ đến con trỏ. Nếu các hàng được cấp phát riêng, truy cập `p[i][j]` cần đi qua con trỏ hàng và không thể áp dụng địa chỉ `base+(i*C+j)*s` trên toàn cấu trúc.

Mảng lồng nhau có thể hữu ích khi số cột mỗi hàng khác nhau. Ngược lại, mảng phẳng thuận lợi khi dữ liệu chữ nhật, cần trao đổi một bộ đệm duy nhất hoặc cần kiểm soát cách truy cập bộ nhớ.

## 11. Độ phức tạp và tính cục bộ bộ nhớ

Với ma trận `R×C` có cách định địa chỉ trực tiếp đã biết, tính vị trí của một ô `(i,j)` chỉ cần số phép toán không phụ thuộc `R` hay `C`. Vì vậy:

- Truy cập một phần tử theo tọa độ hợp lệ thường **`O(1)`**.
- Duyệt toàn bộ ma trận có `R×C` phần tử mất **`O(RC)` thời gian**.
- Lưu tất cả phần tử cần **`O(RC)` ô nhớ** nếu mỗi ô có kích thước cố định.
- Tạo bản sao trải phẳng mới cũng cần **`O(RC)` thời gian** và **`O(RC)` bộ nhớ bổ sung**; tính riêng chỉ số phẳng không cần bản sao.

Hai thứ tự vòng lặp sau đều đọc đủ các phần tử, nhưng thứ tự đụng tới bộ nhớ khác nhau:

```c
int matrix[3][4] = {
    {1, 2, 3, 4},
    {5, 6, 7, 8},
    {9, 10, 11, 12}
};

long sum_by_rows = 0;
for (int i = 0; i < 3; ++i) {
    for (int j = 0; j < 4; ++j) {
        sum_by_rows += matrix[i][j];
    }
}

long sum_by_cols = 0;
for (int j = 0; j < 4; ++j) {
    for (int i = 0; i < 3; ++i) {
        sum_by_cols += matrix[i][j];
    }
}
```

Cả hai cho cùng tổng `78`. Tuy nhiên, mảng C này lưu theo hàng, nên vòng lặp có **`j` ở bên trong** thường truy cập các phần tử cạnh nhau. Với ma trận lớn, việc truy cập gần nhau thường tận dụng **cache** và cơ chế đọc trước của CPU hiệu quả hơn. Nếu dữ liệu liên tiếp theo cột, vòng lặp với **`i` ở bên trong** thường phù hợp hơn.

Thứ tự duyệt không làm đổi độ phức tạp tiệm cận `O(RC)`, nhưng có thể làm thay đổi nhiều thời gian thực tế. Mức chênh lệch phụ thuộc kích thước dữ liệu, phần cứng, trình biên dịch, stride và các thao tác trong vòng lặp; không nên kết luận một thứ tự luôn nhanh hơn trong mọi hoàn cảnh.

## 12. Tình huống thực tế: điểm ảnh nhiều kênh

Một ảnh màu có chiều cao `H`, chiều rộng `W` và ba kênh màu tại mỗi điểm ảnh (ví dụ đỏ, lục, lam). Có thể coi đây là mảng ba chiều `(H,W,3)` với tọa độ `(y,x,c)`.

Nếu dữ liệu được lưu liên tiếp theo hàng, ba kênh của một điểm ảnh nằm cạnh nhau và mỗi kênh chiếm một byte, chỉ số byte của kênh `c` trong điểm ảnh `(y,x)` là:

\[
\operatorname{offset}(y,x,c)=(yW+x)\times3+c
\]

Ví dụ ảnh `H=2`, `W=4`, hỏi kênh `c=1` của điểm ảnh hàng `y=1`, cột `x=2`:

\[
(1\times4+2)\times3+1=19
\]

Nếu `base = 5000`, byte này ở địa chỉ `5019`. Miền chỉ số hợp lệ là `0<=y<2`, `0<=x<4`, `0<=c<3`.

Trong hệ thống xử lý ảnh, một hàng có thể được đệm thêm để stride của hàng lớn hơn `W×3`. Khi đó, dùng công thức stride:

\[
\operatorname{addr}(y,x,c)=base+y\times stride_{row}+x\times3+c
\]

Nếu hàng rộng `16` byte thay vì `12` byte, kênh ở ví dụ trên có độ lệch `1×16+2×3+1=23` byte. Tìm hiểu shape, stride và kích thước kênh là bước thiết yếu khi đọc ảnh từ bộ đệm phần cứng hoặc một thư viện khác.

## 13. Những lỗi thường gặp

| Lỗi | Vì sao sai? | Cách sửa |
|---|---|---|
| Dùng `i*R+j` cho row-major | Nhân với số **hàng**, không phải số cột | Dùng `i*C+j` |
| Dùng `j*C+i` cho column-major | Mỗi cột có `R` phần tử | Dùng `j*R+i` |
| Đổi chỗ `(i,j)` nhưng không đổi shape | Hàng/cột là hai trục khác nhau | Xem tọa độ theo đúng trục và kích thước |
| Dùng chỉ số `i = R` hoặc `j = C` | Vượt giới hạn mảng | Giữ `0<=i<R` và `0<=j<C` |
| Quên nhân với kích thước ô `s` khi tính địa chỉ byte | Chỉ số phẳng tính theo **phần tử**, địa chỉ tính theo **byte** | `addr = base + index*s` |
| Coi Python `list` lồng nhau là một vùng số nguyên liên tiếp | Danh sách lưu các tham chiếu riêng | Kiểm tra cách biểu diễn của cấu trúc thực tế |
| Giả định không có padding hoặc stride phụ | Có thể bước giữa các hàng lớn hơn `C*s` | Sử dụng stride được cung cấp |
| Tìm tọa độ ngược nhưng dùng sai phép chia | Row-major chia cho `C`; column-major chia cho `R` | Chọn phép chia theo bố trí gốc |
| Coi view chuyển vị là một bản sao đã sắp lại | View có thể chỉ thay shape và stride | Phân biệt chuyển vị logic với sao chép vật lý |
| Đếm `RC` truy cập là `O(1)` vì một truy cập `O(1)` | Phải thực hiện thao tác trên mọi phần tử | Duyệt toàn bộ là `O(RC)` |
| Dùng công thức chữ nhật cho hàng có độ dài khác nhau | Không tồn tại số cột chung `C` | Dùng offset từng hàng hoặc cấu trúc răng cưa |

Khi tính chỉ số phẳng trong ngôn ngữ có kiểu số nguyên giới hạn, cần kiểm tra phép nhân `R*C` và các tích dùng tính offset có thể biểu diễn được. Một phép tính số học tràn không bảo đảm tạo ra địa chỉ hợp lệ.

## 14. Bài tập tự kiểm tra

Xét ma trận:

```text
            cột 0  cột 1  cột 2  cột 3
hàng 0         2       4       6       8
hàng 1         1       3       5       7
hàng 2         9      11      13      15
```

1. Ma trận có hình dạng nào, bao nhiêu phần tử? `M[2][1]` bằng bao nhiêu?
2. Trải phẳng ma trận theo **hàng** và theo **cột**; viết hai dãy kết quả.
3. Tính chỉ số phẳng của ô `(2,1)` theo cả hai cách. Nếu `base=1000`, mỗi phần tử có kích thước `4` byte, địa chỉ ô này là bao nhiêu trong mỗi cách?
4. Một chỉ số phẳng `k=7` trong vùng row-major của ma trận có tọa độ nào? Nếu cùng `k=7` nhưng dữ liệu column-major thì tọa độ là gì?
5. Với mảng ba chiều có shape `(2,3,4)`, tính chỉ số phẳng của `(1,0,2)` theo hàng và theo cột.
6. Ma trận row-major có `R=3, C=4, s=4` byte nhưng mỗi hàng cách nhau `20` byte do padding. Nếu `base=2000`, địa chỉ phần tử `(2,3)` là bao nhiêu?
7. Đối với ma trận C lưu theo hàng, trong hai vòng lặp lồng nhau, nên ưu tiên thay đổi chỉ số hàng hay chỉ số cột ở vòng lặp trong để có tính cục bộ bộ nhớ tốt?
8. Một danh sách `[[3, 4, 5], [6, 7]]` có thể áp dụng công thức row-major `i*C+j` với `C=3` cho mọi phần tử hay không? Vì sao?

### Đáp án và giải thích

1. Shape `(3,4)`, tổng `3×4=12` phần tử; `M[2][1]=11`.
2. Theo hàng: `[2,4,6,8,1,3,5,7,9,11,13,15]`. Theo cột: `[2,1,9,4,3,11,6,5,13,8,7,15]`.
3. Theo hàng: `2×4+1=9`, địa chỉ `1000+9×4=1036`. Theo cột: `1×3+2=5`, địa chỉ `1000+5×4=1020`.
4. Row-major: `i=7//4=1`, `j=7%4=3`, tức `(1,3)`. Column-major: `i=7%3=1`, `j=7//3=2`, tức `(1,2)`.
5. Row-major: `1×3×4+0×4+2=14`. Column-major: `1+0×2+2×2×3=13`.
6. `stride_row=20`, `stride_col=4` nên `addr=2000+2×20+3×4=2052`. Dùng `(2×4+3)×4` sẽ sai vì bỏ qua padding.
7. Nên duyệt **cột ở vòng lặp trong** vì các phần tử có chỉ số cột kề nhau nằm cạnh nhau trong bộ nhớ row-major.
8. Không thể giả định `C=3` cho hàng thứ hai: nó chỉ có hai phần tử. Đây là mảng răng cưa; cần lưu độ dài hoặc offset riêng cho từng hàng nếu muốn trải phẳng.

## 15. Ghi nhớ

Mảng nhiều chiều mô tả dữ liệu bằng nhiều chỉ số logic; khi lưu trong một vùng liên tiếp, phải chọn cách **trải phẳng**. Với ma trận `R×C`, cách **theo hàng** dùng chỉ số `i*C+j` và cách **theo cột** dùng `j*R+i`. Địa chỉ byte bằng `base + chỉ_số_phẳng*s` khi các ô liên tiếp, còn cấu trúc có padding hoặc view phải dùng stride thực tế. Truy cập một phần tử đã biết tọa độ thường đạt `O(1)`; duyệt hay sao chép cả ma trận vẫn cần `O(RC)`. Hiểu rõ shape, phạm vi chỉ số, thứ tự lưu và stride giúp xử lý chính xác ma trận, tensor và ảnh, đồng thời lựa chọn cách tổ chức dữ liệu phù hợp với chi phí thời gian và bộ nhớ.

# Cách tính địa chỉ phần tử trong bộ nhớ liên tiếp

## 1. Mục tiêu học tập

Mảng cho phép truy cập phần tử theo chỉ số, ví dụ `A[3]`, mà không cần đi qua lần lượt các phần tử trước đó. Khả năng này gắn với một cách tổ chức bộ nhớ rất quan trọng: **các ô lưu trữ của mảng có kích thước cố định và nằm liên tiếp theo thứ tự chỉ số**. Khi biết địa chỉ ô đầu và kích thước mỗi ô, máy tính có thể tính trực tiếp địa chỉ ô bất kỳ.

Sau bài học, bạn có thể:

- Phân biệt địa chỉ đầu (*base address*), chỉ số (*index*), số phần tử (*length*) và kích thước ô lưu trữ (*element size*).
- Tính địa chỉ phần tử một chiều bằng công thức `base + i × size` và giải thích nguồn gốc công thức.
- Kiểm tra điều kiện chỉ số để không truy cập ngoài vùng mảng.
- Hiểu sự khác biệt giữa **phép tính địa chỉ theo byte** và **phép cộng con trỏ theo đơn vị phần tử**.
- Mở rộng cách tính địa chỉ sang mảng hai chiều lưu theo hàng hoặc theo cột.
- Nhận ra khi nào công thức áp dụng trực tiếp và khi nào cần xét tham chiếu, khoảng cách bước (*stride*), căn chỉnh hay cấp phát lại.

Đây là nền tảng của chương **Mảng** trong học phần cấu trúc dữ liệu. Nắm được cách ánh xạ chỉ số sang địa chỉ giúp giải thích độ phức tạp truy cập, sử dụng bộ nhớ và những đánh đổi khi chọn mảng, danh sách liên kết, stack, queue, heap hoặc các cấu trúc phức tạp hơn.

## 2. Mảng liên tiếp được bố trí như thế nào?

Giả sử mảng `A` chứa `n` phần tử cùng kiểu, mỗi ô chiếm `s` byte. Trong cách biểu diễn mảng liên tiếp thông dụng, các ô nằm nối tiếp nhau trong một vùng bộ nhớ:

```text
         ô 0        ô 1        ô 2        ô 3
      ┌─────────┬─────────┬─────────┬─────────┐
      │  A[0]   │  A[1]   │  A[2]   │  A[3]   │
      └─────────┴─────────┴─────────┴─────────┘
      ↑         ↑         ↑         ↑         ↑
    base      base+s   base+2s   base+3s   base+4s
      │         │         │         │         │
      └── mỗi ô chiếm s byte ────────┘         │
                                               ranh giới cuối
```

Các đại lượng cần hiểu rõ:

| Ký hiệu | Ý nghĩa | Đơn vị |
|---|---|---|
| `n` | Số phần tử thuộc mảng | Phần tử |
| `i` | Chỉ số phần tử cần truy cập | Chỉ số nguyên |
| `base` | Địa chỉ byte đầu tiên của ô `A[0]` | Địa chỉ bộ nhớ |
| `s` | Kích thước của **một ô lưu trữ** | Byte/phần tử |
| `i × s` | Độ lệch của ô `i` tính từ ô đầu | Byte |

Với mảng đánh chỉ số từ `0`, các chỉ số phần tử hợp lệ là `0, 1, ..., n-1`. Khi `n = 0`, mảng không có ô nào để truy cập; mọi yêu cầu đọc phần tử đều không hợp lệ.

Khái niệm **liên tiếp** nói về các ô lưu trữ của mảng, không mặc định rằng tất cả đối tượng mà các ô tham chiếu đến cũng nằm liên tiếp. Sự khác biệt này đặc biệt quan trọng đối với mảng con trỏ và các cấu trúc dữ liệu của ngôn ngữ bậc cao.

## 3. Suy ra công thức địa chỉ một chiều

Đi từ đầu mảng đến ô `A[i]` cần vượt qua đúng `i` ô trước đó. Mỗi ô rộng `s` byte, nên độ lệch tính theo byte là `i × s`. Do đó:

\[
\boxed{\operatorname{addr}(A[i])=\operatorname{base}(A)+i\times s}
\]

Đây là công thức cho mảng có chỉ số đầu tiên bằng `0` và các ô lưu trữ liên tiếp, kích thước bằng nhau. Nếu dùng `sizeof(A[0])` trong C khi `A` thực sự là một mảng chứa các phần tử cùng kiểu, giá trị ấy cung cấp kích thước ô tính bằng byte.

**Ví dụ:** Một mảng gồm năm phần tử, mỗi phần tử chiếm `4` byte; địa chỉ ô đầu tiên giả sử là `4096`.

```text
Chỉ số    Giá trị minh họa    Độ lệch byte    Địa chỉ ô đầu
  0              10               0              4096
  1              20               4              4100
  2              30               8              4104
  3              40              12              4108
  4              50              16              4112
```

Địa chỉ của `A[3]` là:

\[
4096+3\times4=4108
\]

Ô `A[3]` chiếm các địa chỉ byte từ `4108` đến `4111`, nếu mỗi byte được đánh địa chỉ riêng. Ô cuối `A[4]` chiếm từ `4112` đến `4115`; **ranh giới ngay sau toàn bộ vùng mảng** là `4096 + 5 × 4 = 4116`. Ranh giới này hữu ích khi xác định phạm vi nhưng không chứa một phần tử `A[5]` hợp lệ.

Một cách tự kiểm tra phép tính là xác nhận ba trường hợp:

1. `i = 0` cho `addr(A[0]) = base`.
2. Tăng `i` thêm `1` làm địa chỉ tăng đúng `s` byte.
3. Phần tử cuối của mảng không rỗng bắt đầu tại `base + (n-1) × s`.

### Khi chỉ số bắt đầu từ giá trị khác 0

Không phải mọi ngôn ngữ hay mô hình toán học đều dùng chỉ số đầu tiên bằng `0`. Giả sử miền chỉ số được quy định từ `L` đến `U`, còn `base` là địa chỉ của `A[L]`. Khi đó:

\[
\boxed{\operatorname{addr}(A[i])=\operatorname{base}(A)+(i-L)\times s}
\]

Điều kiện hợp lệ là `L <= i <= U` và độ dài là `n = U-L+1`. Ví dụ, mảng được đánh chỉ số `1..4`, địa chỉ của `A[1]` là `8000`, mỗi ô `8` byte. Địa chỉ của `A[3]` là `8000 + (3-1) × 8 = 8016`, không phải `8000 + 3 × 8`. Công thức ban đầu là trường hợp riêng khi `L = 0`.

## 4. Tại sao chỉ số phải được kiểm tra trước?

Phép nhân và phép cộng trong công thức vẫn có thể tạo ra **một con số** ngay cả khi chỉ số không hợp lệ. Điều đó không khiến địa chỉ vừa tính trở thành vị trí có thể truy cập.

Với mảng có độ dài `n` và chỉ số từ `0`, bất biến cần giữ là:

\[
0\le i<n
\]

Chẳng hạn, mảng năm phần tử ở trên không có `A[5]` và cũng không có `A[-1]` theo mô hình chỉ số này. Giá trị `base + n × s` chỉ là địa chỉ **ngay sau** vùng chứa; trong C, có thể hình thành con trỏ một phần tử vượt cuối mảng để so sánh hoặc làm mốc cho vòng lặp, nhưng **không được giải tham chiếu** con trỏ đó. Tạo hoặc sử dụng con trỏ nằm xa hơn vùng mảng theo các quy tắc phép toán con trỏ của C có thể dẫn đến hành vi không xác định.

Đối với chương trình thực tế, cần chú ý thêm:

- **Sai đơn vị:** `i` là số ô, còn địa chỉ thường tính theo byte; không thể cộng trực tiếp `i` vào địa chỉ byte nếu một ô có nhiều byte.
- **Tràn số nguyên:** Phép tính `i × s` hoặc tổng `base + i × s` phải nằm trong miền biểu diễn phù hợp. Các giao diện cấp phát và thao tác bộ nhớ cần kiểm tra kích thước trước khi nhân/cộng, nhất là với dữ liệu có độ dài do bên ngoài cung cấp.
- **Quyền truy cập:** Một địa chỉ số học nhìn có vẻ hợp lệ chưa đủ; bộ nhớ phải thực sự được cấp phát và cho phép truy cập theo cách đó.

Như vậy, “tính được địa chỉ” và “được phép đọc/ghi tại địa chỉ” là hai vấn đề khác nhau.

## 5. Hiểu phép cộng con trỏ trong C

Ngôn ngữ C giúp thấy rõ mối liên hệ giữa chỉ số và bộ nhớ. Giả sử:

```c
#include <stddef.h>
#include <stdio.h>

int main(void) {
    int values[] = {10, 20, 30, 40, 50};
    size_t n = sizeof(values) / sizeof(values[0]);

    for (size_t i = 0; i < n; ++i) {
        size_t offset_bytes = i * sizeof(values[0]);
        printf("i=%zu, offset=%zu byte, addr=%p, value=%d\n",
               i, offset_bytes, (void *)&values[i], values[i]);
    }
    return 0;
}
```

Giá trị địa chỉ in ra khác nhau giữa các lần chạy và các máy. Điều cần quan sát là hiệu địa chỉ **theo byte** của hai phần tử kề nhau bằng `sizeof(values[0])`.

Trong C, phép cộng con trỏ được đo **theo phần tử**, không theo byte:

```c
int values[] = {10, 20, 30, 40, 50};

int *p = values;   // trỏ tới values[0]
int x = *(p + 3);  // x = values[3] = 40
int y = values[3]; // y = 40
```

Hai biểu thức `values + 3` và `&values[3]` chỉ cùng vị trí. Trình biên dịch tự tính độ lệch `3 × sizeof(int)` khi cộng `3` vào con trỏ kiểu `int *`. Vì vậy, viết `p + 3 * sizeof(int)` để đi đến phần tử thứ tư là **nhân kích thước hai lần** và cho vị trí sai.

Một phân biệt nữa:

| Biểu thức C | Ý nghĩa |
|---|---|
| `values[i]` | Đọc/ghi giá trị tại chỉ số `i` |
| `&values[i]` | Lấy địa chỉ phần tử `i` |
| `values + i` | Con trỏ tới phần tử `i`; trình biên dịch tự nhân theo kích thước kiểu |
| `sizeof(values[0])` | Kích thước một phần tử theo byte |
| `sizeof(values)` | Tổng số byte của cả mảng **tại nơi biến còn là kiểu mảng thực sự** |

Lưu ý: khi truyền mảng vào tham số hàm khai báo kiểu `int values[]`, tham số được điều chỉnh thành `int *values`. Khi ấy, `sizeof(values)` là kích thước con trỏ, **không phải** kích thước toàn bộ mảng; cần truyền độ dài vào hàm riêng. Cũng không nên mặc định `sizeof(int) == 4`: kích thước phụ thuộc nền tảng và kiểu dữ liệu được dùng.

## 6. Kích thước phần tử, căn chỉnh và khoảng đệm

Công thức dựa trên **kích thước của ô** chứ không dựa trên độ dài chuỗi ký tự hay kích thước nội dung đang được lưu. Ví dụ một mảng `char` thường có ô rộng một byte theo định nghĩa `sizeof(char) == 1` trong C, còn mảng `double` có kích thước ô bằng `sizeof(double)` trên nền tảng tương ứng.

Một kiểu cấu trúc (*struct*) có thể chứa **khoảng đệm** (*padding*) để các trường dữ liệu được căn chỉnh (*alignment*) phù hợp:

```c
struct Record {
    char flag;
    int count;
};

struct Record records[3];
```

Không thể tự suy ra `sizeof(struct Record)` bằng `sizeof(char) + sizeof(int)` trên mọi máy, vì trình biên dịch có thể chèn byte đệm giữa các trường và cuối cấu trúc. Tuy nhiên, với một mảng C thực sự, **bước giữa hai phần tử liền kề vẫn bằng `sizeof(struct Record)`**. Kích thước này đã bao gồm mọi phần đệm cần thiết:

\[
\operatorname{addr}(records[i])=\operatorname{base}(records)+i\times\operatorname{sizeof}(\texttt{struct Record})
\]

Hai khái niệm dễ lẫn:

- **Kích thước ô**: số byte từ điểm bắt đầu của một phần tử đến điểm bắt đầu của phần tử kế tiếp trong mảng thông thường.
- **Kích thước dữ liệu có ý nghĩa**: có thể nhỏ hơn kích thước ô nếu có vùng đệm hoặc ô chứa tham chiếu thay vì đối tượng.

Việc căn chỉnh có thể làm `base` phải thỏa điều kiện nhất định. Vì vậy, khi thao tác với con trỏ trong ngôn ngữ cấp thấp, hãy dùng con trỏ đúng kiểu và để hệ thống cấp phát cùng trình biên dịch xử lý các ràng buộc này.

## 7. Mảng hai chiều: từ cặp chỉ số đến một địa chỉ

Một ma trận `M` có `R` hàng và `C` cột sử dụng hai chỉ số `(i, j)` với `0 <= i < R` và `0 <= j < C`. Nếu các phần tử nằm trong một vùng liên tiếp, cần biết **thứ tự tuyến tính hóa** để đổi `(i, j)` thành độ lệch một chiều.

### 7.1. Lưu theo hàng (*row-major*)

Các phần tử của hàng trước được lưu hết rồi mới đến hàng tiếp theo:

```text
Ma trận 2 hàng × 3 cột:

        cột 0   cột 1   cột 2
hàng 0     11      12      13
hàng 1     21      22      23

Trong bộ nhớ theo hàng:
[11][12][13][21][22][23]
  0   1   2   3   4   5       chỉ số phẳng
```

Trước ô `(i, j)` có `i` hàng đầy đủ, mỗi hàng `C` ô, cộng thêm `j` ô trong hàng hiện tại. Do đó:

\[
\operatorname{flatIndex}_{row}(i,j)=i\times C+j
\]

\[
\boxed{\operatorname{addr}(M[i][j])=base+(i\times C+j)\times s}
\]

Với `R = 3`, `C = 4`, `base = 2000`, `s = 8` byte, ô `(2, 1)` có chỉ số phẳng `2 × 4 + 1 = 9`, nên bắt đầu ở địa chỉ `2000 + 9 × 8 = 2072`.

Trong C, khai báo `int matrix[3][4]` là một mảng của ba mảng con, mỗi mảng con có bốn phần tử `int` liên tiếp. Biểu thức `matrix[i][j]` hoạt động theo bố trí theo hàng như trên, với độ lớn phần tử cụ thể do `sizeof(int)` quyết định.

### 7.2. Lưu theo cột (*column-major*)

Một số hệ thống tính toán tổ chức phần tử của cột trước rồi mới đến cột tiếp theo. Lúc này, trước ô `(i, j)` có `j` cột đầy đủ, mỗi cột `R` ô, cộng thêm `i` ô:

\[
\operatorname{flatIndex}_{col}(i,j)=j\times R+i
\]

\[
\boxed{\operatorname{addr}(M[i,j])=base+(j\times R+i)\times s}
\]

Với cùng ma trận `R = 3`, `C = 4`, `base = 2000`, `s = 8`, ô `(2, 1)` có chỉ số phẳng `1 × 3 + 2 = 5`, nên địa chỉ là `2040`. Không thể dùng công thức theo hàng cho một vùng bộ nhớ được lưu theo cột, hoặc ngược lại.

| Thuộc tính | Theo hàng (*row-major*) | Theo cột (*column-major*) |
|---|---|---|
| Thứ tự các phần tử gần nhau | Cùng hàng, cột tăng dần | Cùng cột, hàng tăng dần |
| Chỉ số phẳng của `(i, j)` | `i*C + j` | `j*R + i` |
| Độ lệch byte | `(i*C + j)*s` | `(j*R + i)*s` |
| Điều kiện hợp lệ | `0 <= i < R`, `0 <= j < C` | Giống bên trái |

Đối với ma trận nhiều chiều hơn, tiếp tục nhân chỉ số với tích kích thước của các chiều nằm phía sau (theo hàng) hoặc phía trước (theo cột). Về bản chất, đây vẫn là công thức **địa chỉ đầu + độ lệch ô × kích thước ô**.

## 8. Khi có khoảng cách bước (*stride*)

Trong một mảng một chiều liên tiếp chuẩn, khoảng cách tính theo byte giữa hai ô liền kề là `s`. Trong một **khung nhìn dữ liệu** (*view*) hoặc bố trí có khoảng đệm giữa các phần tử được quan sát, khoảng cách ấy có thể là giá trị `stride` khác `s`:

\[
\operatorname{addr}(V[i])=base+i\times stride
\]

Ví dụ, dữ liệu gốc có các phần tử bốn byte ở địa chỉ `1000, 1004, 1008, 1012, 1016`. Nếu khung nhìn chỉ lấy phần tử ở chỉ số chẵn (`0, 2, 4`), ba phần tử được nhìn thấy ở `1000, 1008, 1016`: `stride = 8` byte. Phép truy cập theo chỉ số của view vẫn có thể tính trực tiếp nhưng **các phần tử được xem không còn kề nhau theo kích thước ô 4 byte**.

Với ma trận có bước theo byte của từng chiều là `stride_row` và `stride_col`, công thức tổng quát là:

\[
\operatorname{addr}(M[i,j])=base+i\times stride_{row}+j\times stride_{col}
\]

Khi ma trận liên tiếp theo hàng, `stride_row = C × s` và `stride_col = s`; khi liên tiếp theo cột, `stride_row = s` và `stride_col = R × s`. Một số hệ thống còn dùng khoảng đệm giữa các hàng để căn chỉnh dữ liệu, khiến `stride_row` lớn hơn `C × s`. Vì vậy, với dữ liệu ảnh hoặc ma trận nhận từ thư viện ngoài, hãy đọc thông tin bước của bộ đệm thay vì tự giả định mỗi hàng nằm sát hàng tiếp theo.

## 9. Có phải mọi cấu trúc hỗ trợ `A[i]` đều lưu giá trị liền nhau?

**Không.** Cú pháp truy cập chỉ số là một giao diện; cách biểu diễn bên dưới do ngôn ngữ và cấu trúc quyết định.

| Cấu trúc / cách biểu diễn | Các ô lưu trữ có liên tiếp không? | Điểm cần nhớ |
|---|---|---|
| Mảng kiểu cố định trong C như `int a[5]` | Có | Các phần tử nằm liền nhau; địa chỉ theo `i*sizeof(int)` |
| `std::vector<int>` trong C++ | Có đối với các phần tử hiện có | Thêm phần tử có thể làm cấp phát lại, khiến con trỏ/iterator cũ không còn hợp lệ |
| `list` của Python | Mảng tham chiếu liên tiếp theo cách triển khai CPython thông dụng | Các đối tượng Python được tham chiếu không nhất thiết nằm liền nhau |
| Mảng con trỏ `Node *a[5]` trong C | Các **con trỏ** nằm liền nhau | Các đối tượng `Node` được trỏ đến có thể phân tán |
| Danh sách liên kết | Các nút không cần liên tiếp | Muốn tới nút thứ `i` thường phải theo các liên kết từ đầu, mất `O(n)` |
| Danh sách các hàng được cấp phát riêng | Không bảo đảm toàn bộ bảng liên tiếp | `M[i][j]` có thể cần đọc tham chiếu đến hàng `i` trước |

Ví dụ, nếu một ô của mảng chứa **con trỏ** đến đối tượng, công thức địa chỉ tính vị trí của **ô con trỏ**, không tính địa chỉ đối tượng mà con trỏ đang trỏ tới. Lấy một phần tử có thể cần thêm một lần đọc con trỏ để đi đến dữ liệu thật.

Trong mảng động, **độ dài** là số phần tử hiện có còn **sức chứa** là số ô đã cấp phát dự phòng. Khi dung lượng không đủ, cấu trúc có thể cấp phát vùng mới và sao chép các phần tử; địa chỉ `base` sau đó có thể thay đổi. Vì thế không nên giữ và sử dụng lâu dài địa chỉ phần tử nếu cấu trúc có khả năng cấp phát lại mà không tuân thủ quy tắc của thư viện.

## 10. Công thức địa chỉ liên quan gì đến độ phức tạp và bộ nhớ đệm?

Với một mảng liên tiếp có độ dài `n`, biết trước `i` thì phép tính `base + i × s` chỉ sử dụng số phép toán không phụ thuộc `n`. Theo mô hình RAM thông dụng, **truy cập theo chỉ số là `O(1)`**. Trái lại, tìm một phần tử chỉ biết **giá trị** (chưa có chỉ số), trong mảng chưa sắp xếp, có thể phải đọc tới `n` phần tử nên mất `O(n)` ở trường hợp xấu nhất.

Tính liên tiếp còn thường giúp CPU tận dụng **bộ nhớ đệm** (*cache*) và cơ chế đọc trước (*prefetch*): khi duyệt `A[0], A[1], A[2], ...`, nhiều ô gần nhau được truy cập lần lượt. Tuy nhiên, `O(1)` không hứa hẹn thời gian thực thi bằng nhau cho mọi chỉ số. Cache miss, phân trang, kiến trúc bộ nhớ và cách cấp phát có thể làm một lần truy cập thực tế chậm hơn lần khác.

Với mảng hai chiều lưu theo hàng, duyệt từng hàng rồi qua các cột thường có tính cục bộ tốt hơn khi làm việc trên dữ liệu lớn:

```c
int matrix[3][4] = {
    {1, 2, 3, 4},
    {5, 6, 7, 8},
    {9, 10, 11, 12}
};

long sum = 0;
for (size_t i = 0; i < 3; ++i) {
    for (size_t j = 0; j < 4; ++j) {
        sum += matrix[i][j];  // đi theo thứ tự liên tiếp trong từng hàng
    }
}
```

Đổi thứ tự hai vòng lặp vẫn tính cùng một tổng, nhưng có thể thay đổi tính cục bộ dữ liệu và hiệu năng đối với ma trận đủ lớn. Nếu dữ liệu được lưu theo cột, thứ tự truy cập ưu tiên cũng thường đảo lại.

Mỗi lần tính địa chỉ có thể là `O(1)`, nhưng việc **duyệt toàn bộ `n` phần tử** vẫn tốn `O(n)` thời gian. Đừng suy từ “mỗi truy cập nhanh” thành “xử lý toàn bộ mảng trong thời gian hằng số”.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách nghĩ đúng |
|---|---|---|
| Dùng `base + i` cho mảng các ô `4` byte | Đang cộng byte thay vì số ô | Địa chỉ byte là `base + i*4` |
| Viết `p + i*sizeof(T)` với `T *p` trong C | Phép cộng con trỏ tự nhân theo kích thước `T` | Dùng `p + i` |
| Xem `A[n]` là phần tử cuối | Chỉ số hợp lệ dừng ở `n-1` | `base+n*s` là ranh giới sau mảng |
| Mặc định mọi kiểu `int` dài `4` byte | Kích thước phụ thuộc hệ thống | Dùng `sizeof(int)` trong C |
| Quên trừ chỉ số gốc `L` | Lệch vị trí khi mảng không bắt đầu từ 0 | `base+(i-L)*s` |
| Cộng kích thước các trường để suy `sizeof(struct)` | Có thể có byte đệm | Dùng kích thước ô thực tế |
| Xem mảng tham chiếu là vùng chứa mọi đối tượng liền nhau | Ô tham chiếu và đối tượng được trỏ tới khác nhau | Tính địa chỉ ô tham chiếu trước |
| Áp dụng row-major cho dữ liệu lưu theo cột | Thứ tự tuyến tính hóa khác nhau | Xác định cách lưu trước khi nhân chỉ số |
| Chỉ nhìn công thức mà bỏ kiểm tra giới hạn | Tính ra địa chỉ không đảm bảo đọc được | Kiểm tra miền chỉ số và vùng đã cấp phát |

Đối với thuật toán cần thao tác trực tiếp với bộ nhớ, hãy tự đặt ba câu hỏi: **Ô nào được tìm? Ô ấy rộng bao nhiêu byte? Và chỉ số đó có thuộc vùng lưu trữ hợp lệ không?** Nếu dữ liệu nhiều chiều, bổ sung câu hỏi về thứ tự lưu và stride.

## 12. Bài tập tự kiểm tra

**Bài 1.** Mảng `B` có `8` phần tử, mỗi ô chiếm `2` byte, `base = 5000`. Tính địa chỉ của `B[0]`, `B[5]`, `B[7]` và ranh giới ngay sau toàn bộ mảng. `B[8]` có hợp lệ không?

**Bài 2.** Một mảng đánh chỉ số từ `1` đến `6`, địa chỉ của phần tử đầu tiên `A[1]` là `1000`, kích thước ô `8` byte. Địa chỉ `A[4]` là bao nhiêu?

**Bài 3.** Trong C, cho `double numbers[10]` và con trỏ `double *p = numbers`. Vì sao `p + 3` trỏ tới phần tử thứ tư mà không cần nhân thêm `sizeof(double)`?

**Bài 4.** Ma trận `3 × 4` dùng ô `4` byte và `base = 1000`. Tính địa chỉ ô `(1, 2)` khi lưu theo hàng và khi lưu theo cột.

**Bài 5.** Giả sử một `struct` có trường `char` và `int`, trong một bản triển khai `sizeof(struct)` bằng `8` byte. Vì sao khoảng cách giữa `records[0]` và `records[1]` là `8` byte ngay cả khi tổng kích thước hai trường có thể nhỏ hơn `8`?

**Bài 6.** Một mảng `int` được lưu liên tiếp nhưng ta tạo một view chọn các phần tử ở chỉ số `1, 3, 5`. Nếu `sizeof(int) = 4`, bước theo byte giữa hai ô liên tiếp của view là bao nhiêu? Có thể dùng `base + i*4` để tính địa chỉ phần tử thứ `i` của view không?

### Đáp án và giải thích

1. `B[0]`: `5000`; `B[5]`: `5000 + 5×2 = 5010`; `B[7]`: `5014`; ranh giới cuối: `5000 + 8×2 = 5016`. `B[8]` không hợp lệ vì các chỉ số chỉ từ `0` đến `7`.
2. `1000 + (4-1)×8 = 1024`.
3. Phép cộng trên con trỏ kiểu `double *` tính theo đơn vị `double`; trình biên dịch tự chuyển độ lệch ba phần tử thành số byte tương ứng.
4. Theo hàng: `1000 + (1×4+2)×4 = 1024`. Theo cột: `1000 + (2×3+1)×4 = 1028`.
5. `sizeof(struct)` bao gồm cả byte đệm để đáp ứng căn chỉnh; hai phần tử của một mảng cấu trúc cách nhau đúng kích thước của cấu trúc ấy.
6. Bước của view là `2×4 = 8` byte. Nếu `base` là địa chỉ phần tử đầu tiên trong view (ô gốc ở chỉ số `1`), phải dùng `base + i×8`.

## 13. Ghi nhớ

Trong mảng một chiều có các ô liên tiếp, cố định kích thước, **địa chỉ phần tử bằng địa chỉ ô đầu cộng chỉ số nhân kích thước ô**: `addr(A[i]) = base + i*s` với `0 <= i < n`. Nếu miền chỉ số bắt đầu từ `L`, dùng `(i-L)*s`. Với mảng nhiều chiều, cần đổi các chỉ số thành độ lệch theo thứ tự lưu hoặc sử dụng stride của từng chiều. Công thức giải thích vì sao truy cập mảng thường đạt `O(1)`, đồng thời giúp nhận ra các ranh giới truy cập hợp lệ, chi phí bộ nhớ và ảnh hưởng của cách sắp xếp phần tử đến hiệu năng.

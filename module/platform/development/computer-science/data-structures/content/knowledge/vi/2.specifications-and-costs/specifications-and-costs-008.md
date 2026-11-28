# Phân tích khấu hao và sự khác biệt với lấy trung bình trên dữ liệu ngẫu nhiên

> **Chương:** Đặc tả và chi phí · **Bài học:** Phân tích khấu hao và sự khác biệt với lấy trung bình trên dữ liệu ngẫu nhiên

Một lần thêm phần tử vào mảng động đôi khi phải cấp phát vùng nhớ mới và sao chép hàng nghìn phần tử. Tuy vậy, khi xét một chuỗi dài các lần thêm liên tiếp, chi phí bình quân của mỗi lần lại có thể được chặn bởi một hằng số. Điều này **không có nghĩa** ta đang giả định các phần tử hoặc các vị trí thêm được chọn ngẫu nhiên.

Đó là ý tưởng của **phân tích khấu hao** (*amortized analysis*): cho phép một số thao tác riêng lẻ rất đắt, nhưng chứng minh rằng **tổng chi phí thực tế của mọi thao tác trong một chuỗi hợp lệ** được khống chế. Nó khác về cơ sở lập luận với **chi phí trung bình trên đầu vào ngẫu nhiên** (*average-case analysis*) và **chi phí kỳ vọng** (*expected cost*), vốn cần một mô hình xác suất.

Trong mô-đun Cấu trúc dữ liệu (`COMPUTER_SCIENCE_DATA_STRUCTURES`), sự khác biệt này quan trọng khi đánh giá mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Cùng một cài đặt có thể có chi phí từng thao tác xấu nhất cao, chi phí khấu hao thấp và chi phí kỳ vọng phụ thuộc vào phân bố dữ liệu. Muốn chọn cấu trúc phù hợp, cần biết mỗi phát biểu thực sự bảo đảm điều gì về thời gian, bộ nhớ và bất biến.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **khấu hao** là phân tích một chuỗi thao tác, không phải lấy trung bình theo xác suất đầu vào.
2. Phân biệt **xấu nhất của một thao tác**, **chi phí khấu hao**, **trung bình trên dữ liệu ngẫu nhiên** và **kỳ vọng do thuật toán ngẫu nhiên**.
3. Dùng ba phương pháp phân tích khấu hao: **tổng hợp**, **kế toán** và **hàm thế năng**.
4. Chứng minh chi phí O(1) khấu hao của việc thêm cuối mảng động khi dung lượng tăng gấp đôi.
5. Phân tích `multiPop` trên stack, bộ đếm nhị phân và queue tạo từ hai stack.
6. Nhận biết trường hợp chiến lược thu nhỏ vùng đệm gây chi phí khấu hao lớn do mở rộng/thu nhỏ lặp lại.
7. Đánh giá khi nào bảo đảm khấu hao đủ dùng và khi nào cần xem giới hạn thời gian xấu nhất của từng lời gọi.

## 2. Khấu hao đo điều gì?

Giả sử một cấu trúc dữ liệu bắt đầu ở trạng thái hợp lệ `D₀`. Một chuỗi `m` thao tác hợp lệ lần lượt biến trạng thái thành:

```text
D0 --op1--> D1 --op2--> D2 --op3--> ... --opm--> Dm
```

Gọi `cᵢ ≥ 0` là **chi phí thực tế** của thao tác thứ `i` theo mô hình tính toán đã chọn. Tổng chi phí là:

\[
C(m)=\sum_{i=1}^{m}c_i.
\]

Ta nói một nhóm thao tác có **chi phí O(1) khấu hao** nếu có thể chứng minh tổng chi phí cho **mọi chuỗi hợp lệ dài `m`** (trong phạm vi trạng thái khởi đầu và giả định đã nêu) bị chặn bởi O(m), dù riêng một thao tác có thể tốn Θ(m).

Phát biểu này không nhất thiết cho ta một số cụ thể bằng cách cộng chi phí của mọi thao tác. Nó cho một **chặn tổng đáng tin cậy**, từ đó suy ra lượng công việc bình quân tính trên số thao tác.

### 2.1. Ví dụ trực quan: sao chép vùng đệm

Một mảng động tăng gấp đôi sức chứa khi đầy. Khi có `n` phần tử và còn chỗ, thêm cuối chỉ cần ghi 1 ô. Khi đầy, lần thêm tiếp theo cần:

1. Cấp phát vùng đệm lớn hơn.
2. Sao chép `n` phần tử.
3. Ghi phần tử mới.

Nếu tính mỗi lần sao chép/ghi một phần tử là 1 đơn vị, chi phí lần thêm khi đầy là `n+1`; trường hợp xấu nhất của **một lần thêm** là Θ(n).

Nhưng không thể xảy ra chuyện **mỗi lần** thêm đều sao chép lại `n` phần tử: sau lần mở rộng, mảng có chỗ cho nhiều lần thêm rẻ tiếp theo. Các lần đắt được phân bổ thưa trong cả chuỗi, tạo cơ sở cho chặn O(1) khấu hao.

### 2.2. Bảng phân biệt bốn cách đánh giá

| Cách đánh giá | Lấy cực trị hoặc bình quân trên cái gì? | Có cần giả định xác suất? | Cho biết điều gì? |
| --- | --- | --- | --- |
| **Xấu nhất của một lời gọi** | Một thao tác ở trạng thái khó nhất có thể gặp | Không | Chi phí tối đa riêng lẻ trong phạm vi đang xét |
| **Khấu hao** | Tổng chi phí trên mọi chuỗi thao tác hợp lệ | Không | Chặn tổng và chi phí phân bổ trên chuỗi |
| **Trung bình trên đầu vào** | Các đầu vào được gán xác suất cụ thể | Có | Chi phí trung bình theo phân bố ấy |
| **Kỳ vọng theo ngẫu nhiên nội bộ** | Các lựa chọn ngẫu nhiên của thuật toán trên đầu vào cố định | Có | Chi phí trung bình theo lựa chọn ngẫu nhiên |

**Lưu ý về thuật ngữ:** Trung bình trên đầu vào cũng là **kỳ vọng toán học** theo phân bố đầu vào. Sự phân biệt ở bảng là **nguồn xác suất**, chứ không phải hai phép toán toán học hoàn toàn khác nhau.

## 3. Vì sao không được đồng nhất khấu hao với trung bình ngẫu nhiên?

Xét tìm kiếm tuyến tính trong mảng chưa sắp xếp gồm `n` phần tử:

```python
def find_index(values, target):
    for i, value in enumerate(values):
        if value == target:
            return i
    return -1
```

Nếu mục tiêu chắc chắn tồn tại và vị trí xuất hiện đầu tiên được **giả định phân bố đều** trong `n` vị trí, số phép so sánh trung bình là:

\[
\mathbb{E}[C]=\frac{1+2+\cdots+n}{n}=\frac{n+1}{2}.
\]

Phải nêu giả định rằng vị trí xuất hiện đầu tiên có xác suất bằng nhau. Nếu 90% truy vấn tìm phần tử đầu hoặc nếu nhiều truy vấn tìm khóa vắng mặt, chi phí trung bình sẽ khác.

Với mảng động, kết luận “O(1) khấu hao cho mỗi `append`” lại được chứng minh dựa trên **quy tắc nhân đôi sức chứa**, chứ không cần giả định vị trí chèn hay phần tử xuất hiện ngẫu nhiên. Dù người dùng cố tình thực hiện các lời gọi vào lúc bất lợi, tổng số lần sao chép trên chuỗi `m` lần thêm vẫn được chặn.

| Câu hỏi | Tìm kiếm tuyến tính: trung bình | Mảng động: khấu hao |
| --- | --- | --- |
| Dữ liệu ngẫu nhiên ở đâu? | Phân bố vị trí mục tiêu, có thể gồm xác suất vắng mặt | Không cần ngẫu nhiên |
| Nếu mọi truy vấn tìm phần tử cuối? | Mỗi truy vấn cần `n` so sánh | Không ảnh hưởng chứng minh nhân đôi dung lượng |
| Có một lời gọi rất đắt không? | Có thể; phụ thuộc đầu vào | Có; lời gọi gây mở rộng có thể Θ(n) |
| Có đảm bảo trên mọi chuỗi không? | Không, trừ khi có giả định bổ sung | Có, nếu chiến lược tăng trưởng và phạm vi thao tác đúng như chứng minh |

Hai phát biểu đều có thể dùng chữ “bình quân”, nhưng **mẫu số và cơ sở suy luận khác nhau**. Lấy trung bình trên một mẫu dữ liệu ngẫu nhiên **không tự tạo ra** bằng chứng khấu hao cho mọi chuỗi.

## 4. Phương pháp 1 — Phân tích tổng hợp (aggregate analysis)

**Phân tích tổng hợp** tính chặn trên của tổng chi phí thực tế cho cả chuỗi, rồi chia cho số thao tác. Đây là cách tự nhiên nhất khi các lần thao tác đắt xuất hiện theo một quy luật dễ đếm.

### 4.1. Mảng động nhân đôi sức chứa

Giả sử:

- Mảng ban đầu rỗng và có sức chứa `C=1`.
- Mỗi `append` ghi 1 phần tử mới.
- Nếu vùng đệm đang đầy, tạo vùng mới có sức chứa `2C` rồi sao chép `C` phần tử cũ.
- Trong chuỗi này chỉ có thao tác thêm cuối, **không thu nhỏ**.
- Ta đếm mỗi lần ghi phần tử mới hoặc sao chép một phần tử là 1 đơn vị; các thao tác quản lý hằng số khác không ảnh hưởng bậc tiệm cận.

Những lần sao chép khi vùng đệm đầy có kích thước:

```text
Sức chứa cũ:        1, 2, 4, 8, 16, ...
Số phần tử sao chép: 1, 2, 4, 8, 16, ...
```

Sau `m ≥ 1` lần thêm, chỉ xảy ra các lần mở rộng có sức chứa cũ **nhỏ hơn `m`**. Tổng số ô sao chép là một cấp số nhân:

\[
1+2+4+\cdots+2^j = 2^{j+1}-1 < 2m
\]

với `2^j` là sức chứa cũ lớn nhất thực sự đã phải mở rộng trước khi đạt `m` phần tử. Nếu không có lần mở rộng nào, tổng sao chép bằng 0.

Do đó, tổng chi phí theo mô hình đã nêu thỏa:

\[
C(m)=m+\text{số ô sao chép}<3m
\]

với `m≥1` và nếu có mở rộng; trường hợp không mở rộng có `C(m)=m≤3m`. Suy ra:

\[
C(m)=O(m),\qquad \frac{C(m)}{m}=O(1).
\]

Đây chính là **O(1) khấu hao cho `append`**.

### 4.2. Bảng đếm cụ thể với 9 lần thêm

| Lần `append` | Sức chứa trước → sau | Chi phí thực tế (ghi + sao chép) | Tổng tích lũy |
| --- | --- | --- | --- |
| 1 | 1 → 1 | 1 | 1 |
| 2 | 1 → 2 | 2 | 3 |
| 3 | 2 → 4 | 3 | 6 |
| 4 | 4 → 4 | 1 | 7 |
| 5 | 4 → 8 | 5 | 12 |
| 6 | 8 → 8 | 1 | 13 |
| 7 | 8 → 8 | 1 | 14 |
| 8 | 8 → 8 | 1 | 15 |
| 9 | 8 → 16 | 9 | 24 |

Có `9` lần ghi giá trị mới và `1+2+4+8=15` lần sao chép, tổng `24` đơn vị. Thao tác thứ 9 tốn `9` đơn vị, nhưng chi phí trung bình **trên chính chuỗi này** là `24/9≈2,67` đơn vị cho mỗi lần thêm.

Ví dụ số học chỉ minh họa; chứng minh bằng cấp số nhân mới cho phép kết luận cho **mọi `m`**.

### 4.3. Một chuỗi gồm cả thêm và lấy cuối thì sao?

Nếu `pop` chỉ giảm kích thước và **không thu nhỏ vùng đệm**, có thể mở rộng phân tích:

- Mỗi `push` ghi một phần tử với chi phí O(1) ngoài những lần mở rộng.
- `pop` thông thường mất O(1).
- Sức chứa chỉ tăng, nên tổng lượng sao chép do mở rộng phụ thuộc **mức kích thước lớn nhất từng đạt**.

Với chuỗi bắt đầu rỗng gồm `m` lần `push/pop` hợp lệ, số phần tử tối đa không vượt `m`; tổng sao chép bị chặn bởi O(m). Vì vậy **cả chuỗi** vẫn có chi phí O(m), và mỗi lời gọi có chi phí O(1) khấu hao theo mô hình này.

Nếu bổ sung chiến lược thu nhỏ, phải **chứng minh lại**; không được áp dụng máy móc kết quả khi chỉ tăng sức chứa.

## 5. Phương pháp 2 — Kế toán (accounting method)

Phương pháp kế toán gán cho từng thao tác một **chi phí khấu hao** có thể lớn hơn chi phí thực tế ở lần rẻ. Phần chênh lệch được xem như **tín dụng** để trả cho các lần đắt về sau.

Điều kiện then chốt: tổng tín dụng được tích lũy **không được âm tại bất kỳ tiền tố nào của chuỗi**. Ta không thể vay từ những thao tác chưa xảy ra để chứng minh chặn tổng cho tiền tố hiện tại.

### 5.1. Tính tín dụng cho mảng động

Với mảng có sức chứa ban đầu 1, tăng gấp đôi khi đầy, gán **3 đơn vị chi phí khấu hao** cho mỗi lần `append`.

- Mỗi lần thêm cần 1 đơn vị cho việc ghi phần tử mới.
- Để lại tối đa 2 đơn vị dưới dạng tín dụng dự phòng.
- Khi phải mở rộng, dùng tín dụng đã tích lũy để thanh toán việc sao chép các phần tử cũ.

Gọi `m` là số lần thêm đã diễn ra và `K(m)` là tổng số ô đã sao chép đến thời điểm đó. Ta có:

\[
\text{tín dụng}(m)=3m-\bigl(m+K(m)\bigr)
=2m-K(m).
\]

Vì `K(m)<2m` khi có sao chép và `K(m)=0` khi chưa có, nên tín dụng **luôn không âm tại mỗi tiền tố**. Do đó mức thu 3 đơn vị cho mỗi `append` đủ thanh toán tất cả công việc của chuỗi.

Tổng chi phí thực tế sau `m` thao tác không vượt `3m`:

\[
\sum_{i=1}^{m}c_i\leq\sum_{i=1}^{m}\widehat c_i=3m.
\]

Ký hiệu `\widehat c_i` là chi phí khấu hao được gán cho thao tác thứ `i`. Mức 3 ở đây là một **chặn thuận tiện**, không phải số bước chính xác mà chương trình luôn thực hiện.

### 5.2. Vì sao phương pháp kế toán hữu ích?

Khi một cấu trúc có một số phép toán rẻ tạo “tài nguyên dự trữ” cho phép toán đắt, tín dụng là cách giải thích trực quan. Ví dụ, mỗi lần thêm một phần tử có thể đóng góp sẵn tín dụng cho việc di chuyển phần tử ấy sau này.

Phương pháp kế toán và phân tích tổng hợp đưa đến cùng một chặn O(1) khấu hao, nhưng trình bày khác nhau:

- **Tổng hợp:** đếm tất cả lần sao chép và chỉ ra tổng O(m).
- **Kế toán:** chủ động phân bổ chi phí vào từng lần thêm, chứng minh tài khoản không bao giờ âm.

Không được tự đặt mức thu 3 nếu chiến lược tăng trưởng thay đổi hoặc thao tác mới làm mất tín dụng cần thiết. Khi thay hợp đồng thao tác, cần kiểm tra lại chứng minh.

## 6. Phương pháp 3 — Hàm thế năng (potential method)

Phương pháp thế năng gán một giá trị `\Phi(D)` cho mỗi trạng thái hợp lệ `D`. Giá trị này đại diện cho phần “công việc đã dự trữ” hoặc “công việc còn tiềm ẩn” mà ta có thể dùng để cân bằng các lần thao tác đắt.

Với thao tác thứ `i` chuyển `D_{i-1}` thành `D_i`:

\[
\widehat c_i=c_i+\Phi(D_i)-\Phi(D_{i-1}).
\]

Trong đó `c_i` là chi phí thực tế, `\widehat c_i` là chi phí khấu hao.

Cộng từ `1` đến `m`, các số hạng thế năng giữa chừng triệt tiêu:

\[
\sum_{i=1}^{m}\widehat c_i
=\sum_{i=1}^{m}c_i+\Phi(D_m)-\Phi(D_0).
\]

Suy ra:

\[
\sum_{i=1}^{m}c_i
=\sum_{i=1}^{m}\widehat c_i
+\Phi(D_0)-\Phi(D_m).
\]

Nếu `\Phi(D_0)=0` và `\Phi(D_i)\geq0` với mọi trạng thái có thể đạt, thì:

\[
\sum_{i=1}^{m}c_i\leq\sum_{i=1}^{m}\widehat c_i.
\]

Điều này giải thích vì sao chứng minh **mỗi thao tác có chi phí khấu hao bị chặn** đủ để suy ra chặn tổng.

### 6.1. Hàm thế năng cho mảng động chỉ có `append`

Gọi `n` là số phần tử, `C` là sức chứa. Với trạng thái ban đầu `n=0, C=1` và **chỉ có thao tác thêm cuối**, chọn:

\[
\Phi(n,C)=2n-C+1.
\]

Trong những trạng thái **có thể đạt được** của mảng tăng gấp đôi sức chứa khi đầy, thế năng này luôn không âm:

- Ban đầu: `\Phi(0,1)=0`.
- Sau lần mở rộng từ `C` lên `2C` với phần tử mới vừa thêm, `n=C+1` và `\Phi(C+1,2C)=3`.
- Giữa hai lần mở rộng, `n` tăng dần còn `C` giữ nguyên, nên thế năng chỉ tăng.

Hãy tính chi phí khấu hao theo hai trường hợp.

**Trường hợp 1 — Mảng còn chỗ.** Một `append` có chi phí thực tế `c=1`, `n` tăng 1, `C` không đổi. Thế năng tăng `2`:

\[
\widehat c=1+2=3.
\]

**Trường hợp 2 — Mảng đầy.** Trước lời gọi có `n=C`. Sau khi mở rộng và thêm, `n'=C+1`, `C'=2C`. Chi phí thực tế là `c=C+1`.

Thế năng trước và sau:

\[
\Phi_{\mathrm{before}}=2C-C+1=C+1,
\]

\[
\Phi_{\mathrm{after}}=2(C+1)-2C+1=3.
\]

Vậy:

\[
\widehat c=(C+1)+(3-(C+1))=3.
\]

**Kết quả:** cả hai trường hợp đều có chi phí khấu hao **3 đơn vị**. Trường hợp resize có chi phí thực tế lớn nhưng phần thế năng giảm đã bù lại chi phí đó.

### 6.2. Đối chiếu vài trạng thái

| Lần thêm | `n` sau thêm | `C` sau thêm | `\Phi=2n-C+1` | `c` thực tế | `\widehat c` |
| --- | --- | --- | --- | --- | --- |
| Trước thao tác | 0 | 1 | 0 | — | — |
| 1 | 1 | 1 | 2 | 1 | 3 |
| 2 | 2 | 2 | 3 | 2 | 3 |
| 3 | 3 | 4 | 3 | 3 | 3 |
| 4 | 4 | 4 | 5 | 1 | 3 |
| 5 | 5 | 8 | 3 | 5 | 3 |

Lưu ý miền áp dụng: `\Phi=2n-C+1` đã được chứng minh không âm cho **chuỗi chỉ thêm** bắt đầu ở trạng thái trên. Nếu cho phép xóa mà không thu nhỏ, `n` có thể giảm mạnh trong khi `C` giữ nguyên, khiến hàm này âm. Khi đó phải chọn hàm thế năng khác hoặc thay chứng minh; **không được tái sử dụng một công thức ngoài phạm vi đã chứng minh**.

### 6.3. Chọn thế năng như thế nào?

Hàm thế năng tốt thường:

1. Dễ tính từ một vài đại lượng nội bộ như kích thước, sức chứa, số phần tử trong stack hoặc số bit 1.
2. Không âm trên những trạng thái được phép đi qua, hoặc ít nhất có chặn dưới phù hợp và kiểm soát được thế năng cuối.
3. Tăng sau các thao tác rẻ chuẩn bị cho thao tác đắt.
4. Giảm đủ khi thao tác đắt xảy ra để chi phí khấu hao của nó nhỏ.

Hàm thế năng không phải “năng lượng vật lý”. Nó là công cụ toán học để phân bổ tổng chi phí.

## 7. Ví dụ Stack: `multiPop(k)` có thể đắt nhưng khấu hao rẻ

Xét Stack hỗ trợ ba thao tác:

- `push(x)`: thêm một phần tử vào đỉnh.
- `pop()`: lấy một phần tử từ đỉnh khi không rỗng.
- `multiPop(k)`: lấy tối đa `k` phần tử từ đỉnh; nếu stack có ít hơn `k` phần tử, dừng khi rỗng.

Nếu trước lời gọi có `n` phần tử, chi phí thực tế của `multiPop(k)` theo số phần tử bị lấy là:

\[
\Theta(1+\min(k,n)).
\]

Số `1` tính chi phí kiểm tra và kết thúc lời gọi; do đó ngay cả khi `k=0` vẫn có chi phí hằng số.

### 7.1. Phân tích tổng hợp

Giả sử stack bắt đầu rỗng. Trong một chuỗi `m` lời gọi hợp lệ:

- Mỗi `push` tạo **một** phần tử mới.
- Mỗi phần tử được tạo chỉ có thể bị lấy ra **một lần**, bằng `pop` hoặc trong một lần `multiPop`.
- Tổng số phần tử bị lấy ra **không vượt tổng số phần tử đã được thêm**.

Vì số lần `push` không vượt `m`, tổng chi phí của tất cả các lần lấy phần tử là O(m); cộng phần kiểm tra hằng số của `m` lời gọi, tổng vẫn O(m). Như vậy mỗi lời gọi có O(1) **khấu hao** theo chuỗi, dù một `multiPop(k)` đơn lẻ có thể lấy Θ(n) phần tử.

Nếu stack ban đầu đã chứa `n₀` phần tử, chặn tổng là O(m+n₀); phải tính đến những phần tử ban đầu chưa được “thanh toán” bằng các lần `push` trong chuỗi.

### 7.2. Chứng minh bằng thế năng

Chọn `\Phi(D)=size(D)`, luôn không âm; stack bắt đầu rỗng có `\Phi_0=0`.

| Phép toán | Chi phí thực tế theo đơn vị phần tử | Đổi thế năng | Chi phí khấu hao |
| --- | --- | --- | --- |
| `push` | 1 | +1 | 2 |
| `pop` thành công | 1 | −1 | 0 |
| `multiPop` lấy `t` phần tử | `t+1` (có phần kiểm tra) | `−t` | 1 |
| `multiPop` trên stack rỗng | 1 | 0 | 1 |

Chi phí khấu hao của mỗi lời gọi bị chặn bởi một hằng số. Dấu 0 ở `pop` không có nghĩa phép toán được máy thực hiện miễn phí; nó nghĩa **tín dụng từ lần `push` trước đã thanh toán cho việc lấy phần tử**.

### 7.3. Mã minh họa

```python
def multi_pop(stack, k):
    if k < 0:
        raise ValueError("k phải không âm")

    removed = []
    for _ in range(k):
        if not stack:
            break
        removed.append(stack.pop())
    return removed


data = ["A", "B", "C", "D"]
assert multi_pop(data, 3) == ["D", "C", "B"]
assert data == ["A"]
assert multi_pop(data, 100) == ["A"]
assert data == []
```

Ở mã này, danh sách `removed` là **đầu ra** có kích thước bằng số phần tử được lấy. Nếu tính bộ nhớ cấp phát cho đầu ra thì lời gọi `multi_pop` cần Θ(t) ô; phân tích khấu hao ở trên đang tập trung vào **thời gian** và không làm chi phí đầu ra biến mất.

## 8. Ví dụ bộ đếm nhị phân: một lần đổi nhiều bit, tổng vẫn tuyến tính

Xét bộ đếm nhị phân khởi đầu ở 0, được tăng từng đơn vị. Ta đo chi phí bằng **số bit bị lật** trong mỗi lần tăng.

Ví dụ:

```text
0000 -> 0001     1 bit đổi
0001 -> 0010     2 bit đổi
0010 -> 0011     1 bit đổi
0011 -> 0100     3 bit đổi
0100 -> 0101     1 bit đổi
0101 -> 0110     2 bit đổi
0110 -> 0111     1 bit đổi
0111 -> 1000     4 bit đổi
```

Một lần tăng có thể phải lật rất nhiều bit 1 ở cuối thành 0, rồi lật bit 0 đầu tiên thành 1. Nếu bộ đếm đang có `k` bit 1 liên tiếp ở cuối, lần tăng thường lật `k+1` bit. Chi phí xấu nhất của **một lần tăng** sau khi đếm tới khoảng `m` có thể là Θ(log m).

### 8.1. Cách đếm tổng hợp

Trong `m` lần tăng từ 0:

- Bit thấp nhất đổi trong mỗi lần: nhiều nhất `m` lần.
- Bit thứ hai đổi khoảng một nửa số lần.
- Bit thứ ba đổi khoảng một phần tư số lần.
- Tổng số lần lật bị chặn bởi:

\[
m+\left\lfloor\frac{m}{2}\right\rfloor
+\left\lfloor\frac{m}{4}\right\rfloor+\cdots <2m
\]

với `m≥1` và dãy dừng khi các số hạng bằng 0.

Do đó tổng chi phí O(m), nghĩa là O(1) khấu hao cho mỗi lần tăng.

### 8.2. Cách dùng thế năng

Chọn `\Phi(D)` bằng **số bit có giá trị 1**. Bắt đầu từ 0, thế năng bằng 0.

Nếu lần tăng gặp `t` bit 1 liên tiếp ở cuối, các bit đó đổi thành 0 và một bit 0 kế tiếp đổi thành 1:

- Chi phí thực tế `c=t+1`.
- Thế năng thay đổi `\Delta\Phi=1-t`.
- Chi phí khấu hao:

\[
\widehat c=(t+1)+(1-t)=2.
\]

Vì thế, mỗi lần tăng có chi phí khấu hao đúng 2 đơn vị trong mô hình này. Điều này vẫn đúng khi có những lần tăng thực tế phải lật nhiều bit.

Có thể xem bộ đếm là số nguyên không giới hạn về độ rộng, hoặc đảm bảo bộ đếm có thêm bit 0 khi cần; nếu dùng bộ đếm `w` bit cố định và cho phép tràn về 0, lần tràn phải được xét theo quy tắc riêng.

## 9. Ví dụ Queue bằng hai Stack: chuyển hàng loạt nhưng O(1) khấu hao

Một Queue FIFO có thể được cài từ hai stack:

- `in_stack` nhận phần tử mới bằng `push`.
- `out_stack` giữ các phần tử sẵn sàng được lấy theo FIFO.
- Khi cần `dequeue` mà `out_stack` rỗng, chuyển tất cả phần tử từ `in_stack` sang `out_stack` bằng `pop/push`; sự đảo ngược thứ tự đưa phần tử đến trước lên trên cùng của `out_stack`.

### 9.1. Mã minh họa

```python
class TwoStackQueue:
    def __init__(self):
        self._in = []
        self._out = []

    def enqueue(self, value):
        self._in.append(value)

    def dequeue(self):
        if not self._out:
            while self._in:
                self._out.append(self._in.pop())

        if not self._out:
            raise IndexError("empty queue")

        return self._out.pop()

    def __len__(self):
        return len(self._in) + len(self._out)


q = TwoStackQueue()
q.enqueue("A")
q.enqueue("B")
assert q.dequeue() == "A"
q.enqueue("C")
assert q.dequeue() == "B"
assert q.dequeue() == "C"
assert len(q) == 0
```

Bất biến hành vi là FIFO: những phần tử đã chuyển sang `out_stack` được lấy trước những phần tử mới đang ở `in_stack`. Mỗi phần tử được thêm đúng một lần vào `in_stack`, nhiều nhất một lần được chuyển sang `out_stack`, và cuối cùng nhiều nhất một lần bị lấy ra.

### 9.2. Phân tích tổng hợp

Với `m` lời gọi `enqueue/dequeue` bắt đầu từ Queue rỗng:

- Mỗi `enqueue` thực hiện 1 thao tác `push` vào `in_stack`.
- Mỗi phần tử chuyển nhiều nhất một lần: cần 1 `pop` khỏi `in_stack` và 1 `push` vào `out_stack`.
- Mỗi phần tử bị lấy ra nhiều nhất một lần: cần 1 `pop` khỏi `out_stack`.

Như vậy mỗi phần tử chỉ gây ra **một số hằng số các thao tác stack**. Tổng thời gian O(m); mỗi `enqueue` và `dequeue` có chi phí O(1) **khấu hao**.

Dù có lần `dequeue` đầu tiên phải chuyển `n` phần tử, lần kế tiếp không cần chuyển lại chính những phần tử ấy.

### 9.3. Chứng minh bằng thế năng

Chọn `\Phi(D)=2|in\_stack|`, là hai lần số phần tử còn trong stack đầu vào.

Giả sử mỗi lần `push/pop` trên stack tốn 1 đơn vị; chi phí kiểm tra trạng thái thêm một hằng số không đổi bậc.

| Thao tác | Chi phí thực tế chính | Thay đổi thế năng | Chi phí khấu hao chính |
| --- | --- | --- | --- |
| `enqueue` | 1 | +2 | 3 |
| `dequeue` khi `out` không rỗng | 1 | 0 | 1 |
| `dequeue` chuyển `t` phần tử rồi lấy một | `2t+1` | −2t | 1 |

Trong trường hợp `dequeue` trên Queue rỗng, phương thức ném lỗi sau kiểm tra hằng số, thế năng không đổi, nên chi phí khấu hao vẫn O(1).

Hàm thế năng luôn không âm và bằng 0 tại trạng thái ban đầu. Vì vậy, tổng chi phí thực tế bị chặn bởi tổng chi phí khấu hao O(m).

### 9.4. Khấu hao không bảo đảm từng lần `dequeue` nhanh

Nếu `out_stack` rỗng mà `in_stack` có một triệu phần tử, một `dequeue` cụ thể phải chuyển khoảng một triệu phần tử: đó là Θ(n) thời gian cho **lời gọi ấy**.

Nếu ứng dụng có hạn thời gian rất chặt cho từng `dequeue`, có thể cân nhắc một queue dùng mảng vòng hoặc danh sách liên kết có đầu/đuôi để đạt O(1) cho lời gọi lấy đầu theo mô hình thích hợp. Queue hai stack vẫn là ví dụ hữu ích về **đúng FIFO và hiệu quả tổng thể**.

## 10. Khi một chiến lược mở rộng/thu nhỏ làm khấu hao thất bại

Khấu hao phải gắn với **cài đặt cụ thể**, không thể suy từ tên “mảng động”.

Giả sử cài đặt có hai quy tắc:

1. Khi thêm vào mảng đầy, tăng sức chứa từ `C` lên `2C`.
2. Khi xóa làm số phần tử còn lại `n≤C/2`, lập tức thu nhỏ sức chứa từ `C` xuống `C/2`.

Có thể xảy ra dao động lặp lại:

```text
Trước: size = 5, capacity = 8
pop cuối:
  size giảm còn 4
  vì 4 <= 8/2, thu nhỏ capacity 8 -> 4 (sao chép 4 phần tử)

append:
  mảng capacity = 4 đang đầy
  tăng capacity 4 -> 8 (sao chép 4 phần tử)
  ghi thêm phần tử, size = 5

Lặp lại pop rồi append...
```

Mỗi cặp thao tác đều phải sao chép Θ(C) phần tử khi `C` đủ lớn. Lặp lại `r` cặp có tổng chi phí Θ(rC) trong khi chỉ có `2r` lời gọi. Vì vậy **không thể khẳng định O(1) khấu hao độc lập với `C`** đối với chiến lược có ngưỡng này.

### 10.1. Cách khắc phục: ngưỡng có khoảng đệm

Một chiến lược thông dụng là:

- Tăng gấp đôi khi vùng đệm **đầy**.
- Chỉ thu nhỏ một nửa khi số phần tử giảm tới khoảng **một phần tư sức chứa**.
- Luôn giữ sức chứa tối thiểu hợp lệ.

Khoảng đệm giữa ngưỡng tăng và giảm giúp tránh việc ngay sau thu nhỏ đã phải tăng lại chỉ bằng một lần thêm. Có thể chứng minh O(1) khấu hao cho `push/pop` với chiến lược và mô hình cụ thể này bằng hàm thế năng phù hợp, thường phải xét các miền kích thước so với sức chứa.

**Không nên thay đổi ngưỡng rồi giữ nguyên kết luận cũ mà chưa chứng minh.** Bài học chính là: bất biến kích thước, chính sách cấp phát và loại chuỗi thao tác được cho phép đều là phần của giả định phân tích.

### 10.2. Đánh đổi về bộ nhớ

Nếu mảng động chỉ tăng mà không thu nhỏ, thời gian `push/pop` có thể tốt về khấu hao nhưng vùng đệm vẫn giữ dung lượng lớn sau khi nhiều phần tử bị xóa. Nếu có thu nhỏ hợp lý, bộ nhớ đang giữ có thể gần hơn với kích thước hiện tại, đổi lại có thêm những lần sao chép trong quá trình chạy.

Cả hai cách có thể dùng O(n) bộ nhớ theo số phần tử lớn nhất đã lưu hoặc theo kích thước hiện tại dưới những chính sách tương ứng, nhưng **thời điểm đo bộ nhớ và mô hình cấp phát phải được ghi rõ**.

## 11. Bảng băm: kỳ vọng và khấu hao có thể cùng xuất hiện

Bảng băm (*hash table*) thường hỗ trợ truy cập khóa nhanh nếu:

- Tính hash và so sánh khóa có chi phí O(1), hoặc ta tính thêm chi phí theo độ dài khóa.
- Hệ số tải được kiểm soát.
- Hàm băm và phân bố khóa giảm khả năng va chạm quá mức.

Khi các giả định này đúng, `get`/`put`/`remove` có thể có **thời gian kỳ vọng O(1)** về chi phí tra bucket. Nhưng `put` cũng có thể kích hoạt **rehash** toàn bảng khi cần mở rộng.

Ta đang đối diện **hai lý do khác nhau gây thao tác đắt**:

| Nguồn chi phí | Cách phân tích phù hợp | Ví dụ |
| --- | --- | --- |
| Nhiều khóa va chạm vào một bucket | Kỳ vọng theo băm/đầu vào hoặc chặn xấu nhất | Một `get` có thể phải so sánh nhiều khóa |
| Định kỳ phải tái băm khi tăng sức chứa | Khấu hao trên chuỗi cập nhật | Một `put` có thể chuyển `n` khóa sang bảng mới |

Trong chiến lược tăng trưởng thích hợp, tổng công việc tái băm có thể O(m) trên `m` lần thêm, **nếu** chi phí xử lý từng khóa trong lần tái băm được xem là hằng số phù hợp. Đồng thời, chi phí xử lý va chạm có thể O(1) kỳ vọng mỗi thao tác dưới giả định băm hợp lý.

Do đó, một cài đặt thường được mô tả là “O(1) kỳ vọng và khấu hao” đối với một số phép toán. Câu này mang **hai nhóm giả định**; không có nghĩa từng lời gọi thực tế đều O(1).

Nếu tất cả khóa cố tình va chạm hoặc hash chuỗi dài có chi phí cao, chỉ chứng minh resize thưa **không đủ** để kết luận tổng thời gian O(m) theo số lời gọi.

## 12. Các cấu trúc khác: khi nào nên dùng khấu hao, kỳ vọng hoặc xấu nhất?

| Cấu trúc/phép toán | Kết luận thường gặp | Loại phân tích | Điều kiện |
| --- | --- | --- | --- |
| Mảng động `append` | O(1) | Khấu hao | Tăng sức chứa nhân hệ số lớn hơn 1 |
| Mảng động `append` khi đầy | Θ(n) | Xấu nhất một lời gọi | Phải sao chép `n` phần tử |
| Stack `multiPop(k)` | O(1) | Khấu hao trên chuỗi thao tác | Mỗi phần tử chỉ bị lấy một lần, bắt đầu rỗng hoặc tính trạng thái ban đầu |
| Queue hai Stack `dequeue` | O(1) | Khấu hao | Mỗi phần tử chỉ chuyển một lần giữa hai stack |
| Hash Map `get` | O(1) | Kỳ vọng | Băm/so sánh khóa rẻ, phân bố và hệ số tải phù hợp |
| Hash Map `get` khi va chạm nặng | O(n) | Xấu nhất với xử lý va chạm kiểu tuyến tính | Có thể phải xét nhiều khóa |
| BST tự cân bằng `find/insert/delete` | O(log n) | Xấu nhất | Duy trì bất biến chiều cao |
| Heap nhị phân `insert/extract_min` | O(log n) | Xấu nhất | Điều chỉnh dọc một đường của heap |
| Đồ thị danh sách kề, BFS toàn đồ thị | O(V+E) | Xấu nhất theo kích thước đồ thị | Duyệt các thành phần, kiểm tra đánh dấu hiệu quả |
| Đồ thị, BFS từ nguồn được chọn ngẫu nhiên | Phụ thuộc phân bố thành phần nguồn | Trung bình/kỳ vọng | Phải nêu phân bố đồ thị và đỉnh nguồn |

### 12.1. Cây cân bằng: lợi ích từ chặn xấu nhất

Một cây tìm kiếm cân bằng như AVL hoặc đỏ-đen giữ chiều cao O(log n). Vì vậy, tìm kiếm, chèn và xóa theo khóa có thể có giới hạn O(log n) ngay trong trường hợp xấu nhất (theo mô hình so sánh khóa O(1)).

Đây là một kiểu bảo đảm khác với Hash Map O(1) kỳ vọng. Nếu yêu cầu độ trễ của mỗi truy vấn phải có giới hạn tiệm cận rõ, cây cân bằng có thể là lựa chọn phù hợp dù tốc độ kỳ vọng theo khóa của bảng băm thường tốt.

### 12.2. Heap: không nhất thiết phải dùng khấu hao

Trong heap nhị phân, một lần thêm hoặc lấy phần tử ưu tiên nhất chỉ đi theo đường từ nút tới gốc hoặc ngược lại; độ dài đường O(log n). Do đó ngay **mỗi thao tác** có chặn O(log n) trường hợp xấu nhất.

Khấu hao không phải thứ bắt buộc để giải thích mọi cấu trúc dữ liệu. Chỉ áp dụng khi nó tạo ra kết luận có ích hoặc chặt hơn phân tích từng lời gọi.

### 12.3. Duyệt đồ thị: trung bình cần mô hình xác suất rõ

BFS từ một đỉnh nguồn trên danh sách kề có chi phí theo các đỉnh/cạnh có thể tới được `V_r, E_r`. Một nguồn trong thành phần nhỏ có chi phí ít; nguồn trong thành phần lớn có thể phải thăm phần lớn đồ thị.

Muốn nói chi phí trung bình của BFS, cần biết **phân bố chọn đỉnh nguồn và cấu trúc đồ thị**, không thể tự lấy `(V+E)/2` làm trung bình.

Nếu chạy BFS trên mọi thành phần, cận thời gian O(V+E) vẫn là một bảo đảm theo kích thước đồ thị cho cách biểu diễn danh sách kề thông dụng.

## 13. Chi phí thời gian khấu hao khác chi phí bộ nhớ và độ trễ đỉnh

Một kết luận O(1) khấu hao về **thời gian** không tự động cho biết:

- Mỗi lời gọi có thời gian thực tế nhỏ hơn một ngưỡng.
- Bộ nhớ phụ luôn O(1).
- Không có lần cấp phát nào gây tăng RAM đỉnh.
- Hệ thống sẽ phản hồi ổn định ở phần đuôi phân bố độ trễ.

Ví dụ mảng động khi `capacity=C` phải cấp phát vùng mới `2C` trước khi giải phóng vùng cũ. Trong thời gian sao chép, cả hai vùng có thể cùng tồn tại và cần tới khoảng `3C` ô (bỏ qua metadata và vùng nhớ khác). Big-O của vùng đệm vẫn O(C), nhưng hệ số đỉnh có thể quan trọng trên thiết bị hạn chế RAM.

### 13.1. Throughput và latency không cùng một mục tiêu

- **Throughput (thông lượng):** số thao tác hoàn thành trong một khoảng thời gian. Một chuỗi O(m) tổng công việc thường có lợi.
- **Latency (độ trễ một lời gọi):** thời gian xử lý từng yêu cầu cụ thể. Một lời gọi resize Θ(n) có thể gây chậm đáng kể, dù trung bình trên chuỗi vẫn thấp.

Một hệ thống batch có thể chấp nhận vài lần đắt. Một dịch vụ tương tác hoặc hệ thống thời gian thực có thể cần cơ chế cấp phát trước, mở rộng tăng dần, hoặc cấu trúc đảm bảo chặn xấu nhất cho từng thao tác.

### 13.2. Kỳ vọng thấp cũng không bảo đảm độ trễ đuôi thấp

Giả sử 99 yêu cầu tốn 1 đơn vị, còn 1 yêu cầu tốn 101 đơn vị. Chi phí trung bình là:

\[
\frac{99\cdot1+1\cdot101}{100}=2.
\]

Con số 2 không nói rằng mọi yêu cầu chỉ tốn 2 đơn vị. Khi yêu cầu ổn định, cần đánh giá thêm **chặn xấu nhất**, phân vị như p95/p99 và sự kiện tái cấp phát hiếm.

### 13.3. Kiểm tra cả bất biến

Một Queue hai Stack chỉ có chứng minh khấu hao đúng nếu mỗi phần tử thực sự chỉ bị chuyển một lần và thứ tự FIFO được giữ. Một bảng băm chỉ có phân tích tải hợp lý nếu chính sách mở rộng duy trì hệ số tải trong ngưỡng đã đặt.

**Tính đúng của cấu trúc dữ liệu** và **chứng minh độ phức tạp** cùng dựa vào bất biến, hợp đồng và phạm vi thao tác. Không thể “tối ưu” bằng cách bỏ qua một phép cập nhật cần thiết rồi tính chi phí trên cài đặt sai.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Khấu hao nghĩa là trung bình trên các đầu vào ngẫu nhiên.” | Phân tích khấu hao có thể áp dụng cho mọi chuỗi mà không dùng xác suất. | Xét tổng chi phí của các thao tác và chứng minh chặn cho mọi chuỗi hợp lệ. |
| “O(1) khấu hao nghĩa là mỗi lời gọi O(1).” | Một lần resize có thể tốn Θ(n). | Chỉ có chặn O(m) tổng cho `m` thao tác dưới giả định. |
| “Hễ có một lời gọi O(n), tổng `m` lời gọi là O(mn).” | Những lần đắt có thể rất thưa và chia sẻ chi phí. | Đếm số lần sự kiện đắt thực sự xảy ra. |
| “Muốn dùng kỳ vọng phải có thuật toán ngẫu nhiên.” | Đầu vào cũng có thể được mô hình hóa bằng phân bố xác suất. | Chỉ rõ kỳ vọng lấy theo đầu vào, thuật toán hay cả hai. |
| “Chi phí kỳ vọng thấp nghĩa là xấu nhất thấp.” | Có thể có sự kiện hiếm gây chi phí cao. | Trình bày riêng chặn xấu nhất. |
| “Mảng tăng gấp đôi nên cả chèn giữa cũng O(1) khấu hao.” | Chèn giữa vẫn phải dịch nhiều phần tử. | O(1) khấu hao ở đây áp dụng cho **thêm cuối**. |
| “Hàm thế năng âm cũng không sao.” | Chứng minh chặn tổng có thể không còn hiệu lực. | Kiểm tra `\Phi(D_m)\geq\Phi(D_0)` hoặc điều kiện chặn dưới tương ứng. |
| “Có thể dùng một thế năng cho mọi loại thao tác.” | Một công thức chỉ được chứng minh trên miền trạng thái cụ thể. | Viết lại phép chứng minh khi thêm `pop`, thu nhỏ hoặc tái cấu trúc. |
| “Hash Map O(1) hoàn toàn do khấu hao.” | Va chạm liên quan đến kỳ vọng; rehash liên quan đến khấu hao. | Tách hai nguồn chi phí và giả định. |
| “Cấp phát có O(n) nên bộ nhớ phụ chỉ O(1) khấu hao.” | Khấu hao thời gian không suy ra chặn bộ nhớ. | Phân tích riêng thời gian, bộ nhớ lưu và bộ nhớ đỉnh. |

## 15. Bài tập vận dụng có lời giải gợi ý

### Bài 1 — Tổng số lần sao chép của mảng động

Mảng rỗng có sức chứa ban đầu 1, tăng gấp đôi khi đầy. Thêm liên tiếp 9 phần tử, không xóa. Hãy tính số lần sao chép phần tử cũ, số lần ghi phần tử mới và tổng chi phí theo mô hình mỗi lần ghi/sao chép bằng 1.

**Gợi ý đáp án:** Các lần resize sao chép `1+2+4+8=15` phần tử. Có 9 lần ghi mới. Tổng chi phí `24`. Lần thứ 9 đắt nhưng tổng vẫn không vượt một hằng số nhân 9. Không có giả định nào về giá trị phần tử hay vị trí ngẫu nhiên.

### Bài 2 — Phân biệt kỳ vọng và khấu hao

Một nhóm nói: “Vì gần như mọi lần `append` không cần mở rộng, nên `append` O(1) khấu hao do xác suất phải mở rộng rất nhỏ.”

**Gợi ý đáp án:** Câu giải thích chưa phải chứng minh khấu hao. Cần đếm tổng lượng sao chép trên **mọi tiền tố** của chuỗi thêm, hoặc dùng phương pháp kế toán/thế năng. Xác suất gặp resize chỉ liên quan nếu đã thiết lập một mô hình chọn trạng thái/lời gọi ngẫu nhiên, và đó là lập luận kỳ vọng khác.

### Bài 3 — `multiPop` trên Stack

Một stack bắt đầu rỗng. Thực hiện 100 lần `push`, sau đó gọi `multiPop(90)` và `multiPop(90)`. Tổng số phần tử bị lấy là bao nhiêu? Vì sao có thể nói O(1) khấu hao cho `multiPop` trong chuỗi này dù lời gọi đầu tốn Θ(90)?

**Gợi ý đáp án:** Lần đầu lấy 90 phần tử, lần sau lấy 10; tổng 100 phần tử bị lấy, không vượt 100 lần `push`. Tổng công việc của các lời gọi là O(số lời gọi + số lần `push`), nên chi phí phân bổ trên chuỗi là hằng số.

### Bài 4 — Thế năng của mảng động

Với mảng chỉ hỗ trợ `append`, có `n=4, C=4` và `\Phi=2n-C+1`. Thêm phần tử mới làm sức chứa tăng lên 8. Tính chi phí thực tế, thế năng mới và chi phí khấu hao.

**Gợi ý đáp án:** Sao chép 4 ô và ghi 1 ô nên `c=5`. Trước thao tác `\Phi=5`; sau thao tác `n=5,C=8` nên `\Phi'=3`. Chi phí khấu hao `5+(3-5)=3`.

### Bài 5 — Bộ đếm nhị phân

Bộ đếm chuyển từ `0111` sang `1000`. Có bao nhiêu bit đổi? Chọn thế năng bằng số bit 1, tính chi phí khấu hao.

**Gợi ý đáp án:** Có 4 bit đổi, số bit 1 giảm từ 3 xuống 1, tức `\Delta\Phi=-2`. Chi phí khấu hao `4-2=2`.

### Bài 6 — Queue hai Stack

Một Queue hai Stack nhận `A,B,C,D`, sau đó thực hiện `dequeue` hai lần rồi `enqueue(E)` và `dequeue` thêm một lần. Thứ tự trả về là gì? Giải thích tại sao phần tử không bị chuyển nhiều lần.

**Gợi ý đáp án:** Kết quả lấy ra lần lượt `A,B,C`. Những phần tử `A,B,C,D` có thể được chuyển một lần từ stack đầu vào sang đầu ra; `E` chờ trong stack đầu vào cho đến khi đầu ra rỗng. Không có phần tử nào quay lại stack đầu vào, do đó mỗi phần tử chỉ chuyển tối đa một lần.

### Bài 7 — Thu nhỏ vùng đệm quá sớm

Mảng có `size=5, capacity=8`. Thu nhỏ một nửa ngay khi `size≤capacity/2`. Lặp lại `pop` rồi `append` tại cuối. Phân tích việc sao chép.

**Gợi ý đáp án:** `pop` đưa `size` về 4 rồi thu nhỏ 8→4, sao chép 4 phần tử. `append` gặp mảng đầy và tăng 4→8, lại sao chép 4 phần tử. Cặp thao tác lặp lại gây Θ(capacity) công việc cho mỗi lời gọi trong vùng này; cần khoảng đệm giữa hai ngưỡng và chứng minh lại.

### Bài 8 — Trung bình trên phân bố không đều

Có mảng 5 phần tử. Xác suất tìm khóa ở phần tử đầu là 70%, ở phần tử thứ hai là 20%, không tìm thấy là 10%. Tính số phép so sánh kỳ vọng khi tìm tuyến tính.

**Gợi ý đáp án:**

\[
\mathbb E[C]=0,7\cdot1+0,2\cdot2+0,1\cdot5=1,6.
\]

Đó là kỳ vọng trên **phân bố truy vấn đã cho**, không phải chi phí khấu hao của chuỗi tìm kiếm.

### Bài 9 — Chọn cấu trúc cho yêu cầu độ trễ

Dịch vụ xử lý nhiều thao tác trên Queue. Phương án A dùng Queue hai Stack với `dequeue` O(1) khấu hao nhưng có lần chuyển Θ(n) phần tử. Phương án B dùng Queue liên kết có đầu/đuôi, `enqueue` và `dequeue` O(1) trường hợp xấu nhất theo giả định cấp phát nút thông thường.

**Gợi ý đáp án:** Nếu mục tiêu là tổng công việc và bộ nhớ O(n), cả hai đều có thể phù hợp. Nếu cần giới hạn thời gian từng `dequeue`, phương án B dễ đáp ứng tiêu chí tiệm cận hơn. Cần xem thêm chi phí cấp phát nút, quản lý bộ nhớ và yêu cầu đồng thời thực tế.

### Bài 10 — Hash Map có hai loại kết luận O(1)

Một Hash Map phải định kỳ tái băm toàn bộ khóa, đồng thời xử lý bucket bằng danh sách liên kết. Hãy nêu điều kiện để nói `put` có chi phí kỳ vọng và khấu hao nhỏ.

**Gợi ý đáp án:** Chi phí tìm bucket và xử lý va chạm phụ thuộc phân bố/họ hàm băm, hệ số tải và chi phí hash/so sánh khóa. Việc tái băm phụ thuộc chiến lược tăng trưởng và tổng số phần tử di chuyển trên chuỗi cập nhật. Hai điều kiện phải được phân tích riêng rồi mới kết hợp.

## 16. Quy trình viết một chứng minh khấu hao

Với một cấu trúc dữ liệu mới, có thể làm theo thứ tự:

1. **Định nghĩa trạng thái và bất biến.** Ví dụ mảng có `0≤size≤capacity`; Queue hai Stack bảo đảm FIFO.
2. **Đặt đơn vị chi phí.** Một lần ghi ô, so sánh, đổi bit, pop/push liên kết hoặc chuyển phần tử được tính như thế nào?
3. **Chọn loại chuỗi hợp lệ.** Chỉ thêm, thêm/xóa, thay đổi tùy ý hay có điều kiện giới hạn?
4. **Chỉ ra sự kiện đắt.** Resize, rehash, chuyển hàng loạt, lật nhiều bit, tái cân bằng.
5. **Chọn cách chứng minh:** đếm tổng bằng tổng hợp, tích tín dụng kế toán hoặc tìm hàm thế năng.
6. **Chứng minh cho mọi tiền tố.** Nếu dùng tín dụng, tài khoản không âm; nếu dùng thế năng, kiểm tra điều kiện chặn dưới và trạng thái khởi đầu.
7. **Kết luận trên chuỗi, rồi phát biểu cho mỗi thao tác.** Ví dụ tổng O(m) dẫn tới O(1) khấu hao mỗi lời gọi trong phạm vi đang xét.
8. **Đối chiếu chặn từng lời gọi và bộ nhớ.** O(1) khấu hao có thể đi kèm Θ(n) ở một lần resize và O(n) vùng đệm.

Có thể dùng mẫu sau:

```text
Cấu trúc / phép toán:
Trạng thái ban đầu:
Bất biến và hợp đồng cần giữ:
Loại chuỗi thao tác được phép:
Số thao tác m; kích thước dữ liệu n:

Chi phí thực tế từng nhánh:
Chi phí của các sự kiện hiếm:
Cách chứng minh:
  - Tổng hợp: Tổng các lần đắt bị chặn bởi gì?
  - Kế toán: Thu bao nhiêu tín dụng cho mỗi thao tác?
  - Thế năng: Chọn Phi(D) nào, có không âm không?

Chứng minh chặn tổng:
Độ phức tạp khấu hao:
Chi phí xấu nhất của một lời gọi:

Có giả định xác suất không?
Nếu có: nguồn ngẫu nhiên và phân bố là gì?
Thời gian kỳ vọng / trung bình (nếu cần):

Bộ nhớ đang dùng và bộ nhớ đỉnh:
Điều kiện khiến chứng minh không còn áp dụng:
```

Khi phân tích một mảng động, một Stack có `multiPop`, một Queue hai Stack hoặc một bảng băm mở rộng theo tải, hãy nhớ: **khấu hao là lời hứa về tổng chi phí của một chuỗi**. Trong khi đó, **trung bình và kỳ vọng là kết quả của một mô hình xác suất đã nêu rõ**. Kết hợp chúng với chặn xấu nhất, bất biến biểu diễn và bộ nhớ sử dụng sẽ giúp chọn cấu trúc dữ liệu đúng cho cả tính năng và yêu cầu hiệu năng của ứng dụng.

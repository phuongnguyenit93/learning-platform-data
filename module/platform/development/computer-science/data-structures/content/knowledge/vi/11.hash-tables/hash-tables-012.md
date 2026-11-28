# Chi phí kỳ vọng, khấu hao và trường hợp xấu nhất

## 1. Vì sao cùng một thao tác bảng băm lại được gọi là O(1) và O(n)?

**Bảng băm (hash table)** lưu cặp khóa–giá trị và dùng hàm băm để tìm nơi bắt đầu tra cứu. Khi giải quyết va chạm bằng nối chuỗi (*separate chaining*) hoặc địa chỉ mở (*open addressing*), số bước xử lý phụ thuộc vào cách khóa phân bố và mức độ đầy của bảng. Khi bảng tự mở rộng, một vài lần chèn còn phải chuyển nhiều bản ghi sang mảng mới.

Do đó, ba câu sau **có thể đồng thời đúng**, nhưng trả lời ba câu hỏi khác nhau:

- **Chi phí kỳ vọng (expected cost):** trong một mô hình xác suất về hàm băm hoặc đầu vào, *trung bình theo các khả năng có thể xảy ra*, thao tác tìm khóa thường tốn `O(1)` nếu hệ số tải được kiểm soát.
- **Chi phí khấu hao/phân bổ (amortized cost):** dù một số lần chèn phải băm lại `O(n)` phần tử, *tổng chi phí của cả chuỗi thao tác* có thể chỉ là `O(n)`, tương ứng `O(1)` khấu hao cho mỗi lần chèn.
- **Chi phí trường hợp xấu nhất (worst-case cost):** với một cách bố trí khóa bất lợi, tra cứu có thể phải duyệt `O(n)` nút của một chuỗi hoặc `O(m)` ô của bảng địa chỉ mở.

Điều quan trọng là **không đồng nhất** ba loại bảo đảm. Một thao tác có kỳ vọng `O(1)` không có nghĩa mọi lần gọi đều nhanh; một chuỗi có chi phí khấu hao `O(1)` không có nghĩa không có lần gọi tốn `O(n)`.

## 2. Mô hình đo: tính những chi phí nào?

Gọi:

- `n`: số khóa khác nhau đang hoạt động;
- `m>0`: số ngăn trong bảng nối chuỗi, hoặc số ô trong bảng địa chỉ mở;
- `α = n/m`: **hệ số tải** (*load factor*);
- `L`: độ dài một khóa kiểu chuỗi, nếu cần xét thời gian đọc và so sánh toàn bộ khóa.

Khi phân tích cơ bản, thường **giả định việc tính mã băm và so sánh hai khóa có chi phí `O(1)`**. Với khóa là chuỗi dài `L`, tính hash từ đầu có thể cần `O(L)`; so sánh có thể cần đọc nhiều ký tự. Do đó, `O(1)` của bảng băm **không tự bao gồm chi phí xử lý khóa có độ dài biến đổi**.

Một mô hình đếm các bước chính:

| Cơ chế | Đơn vị chi phí tự nhiên | Vì sao phát sinh? |
| --- | --- | --- |
| Nối chuỗi | Số nút hoặc số khóa phải so sánh | Nhiều khóa chung ngăn thì phải duyệt chuỗi |
| Địa chỉ mở | Số ô thăm dò | Va chạm khiến phải thử các vị trí kế tiếp |
| Rehash/resize | Số bản ghi phải chuyển và số ô phải khởi tạo | Dung lượng mới có thể thay đổi vị trí lưu |

Ta có thể đếm một đơn vị cho mỗi phép kiểm tra ô, phép so sánh khóa, thao tác ghi nút hoặc chuyển bản ghi; các cận tiệm cận sẽ phụ thuộc cách gộp những chi phí này. Khi đưa ra kết quả, cần nói rõ giả định và thao tác được đo.

## 3. Chi phí kỳ vọng: xác suất đến từ đâu?

Ký hiệu `T` là biến ngẫu nhiên biểu diễn số bước của thao tác. Chi phí kỳ vọng là:

\[
\mathbb{E}[T]=\sum_{t}t\,\Pr(T=t).
\]

Ví dụ giả sử một phép tìm tốn 1 bước với xác suất `0,9`, và tốn 11 bước với xác suất `0,1`. Khi đó:

\[
\mathbb{E}[T]=0{,}9\cdot1+0{,}1\cdot11=2.
\]

**Kỳ vọng chỉ bằng 2 bước**, nhưng một phép tìm cụ thể vẫn có thể tốn 11 bước. Kỳ vọng là trung bình theo mô hình xác suất, không phải giới hạn tối đa.

Với bảng băm, nguồn ngẫu nhiên thường được mô hình hóa theo một trong những cách:

1. **Phân bố khóa đầu vào:** dữ liệu có một phân bố xác suất nhất định, còn hàm băm cố định.
2. **Hàm băm được chọn ngẫu nhiên:** ví dụ chọn từ một họ hàm băm, còn tập khóa cố định trước khi chọn hàm.
3. **Mô hình băm đều lý tưởng:** các khóa được giả định phân bố phù hợp giữa những ngăn hoặc các dãy thăm dò.

Nếu cả tập khóa và hàm băm đều **cố định**, kết quả tra cứu là một số bước xác định; chỉ việc nhìn thấy một bảng băm không đủ để khẳng định có kỳ vọng `O(1)`. Khi phát biểu một cận kỳ vọng, phải nêu được **điều gì đang được lấy trung bình**.

## 4. Chi phí kỳ vọng của bảng nối chuỗi

Trong **separate chaining**, mảng có `m` ngăn; mỗi ngăn chứa danh sách các cặp khóa–giá trị. Giả sử các khóa được băm **đều** vào các ngăn theo mô hình xác suất thích hợp, số khóa kỳ vọng tại một ngăn là:

\[
\mathbb{E}[\text{độ dài chuỗi}]=\frac{n}{m}=\alpha.
\]

Sau một lần tính chỉ số `O(1)`, chương trình kiểm tra những nút trong chuỗi đó. Với cách cài đặt dùng danh sách liên kết:

| Thao tác | Chi phí kỳ vọng dưới giả định băm đều | Trường hợp xấu nhất |
| --- | --- | --- |
| `get(k)` tìm thấy | `O(1+α)` | `O(n)` |
| `get(k)` không tìm thấy | `O(1+α)` | `O(n)` |
| `put(k,v)` kiểm tra khóa cũ trước khi thêm/cập nhật | `O(1+α)` | `O(n)` |
| `remove(k)` tìm và gỡ nút | `O(1+α)` | `O(n)` |

Nếu luôn giữ `α\leq c` với một hằng số `c`, ta suy ra các thao tác có **chi phí kỳ vọng `O(1)`** trong mô hình trên. Không có mâu thuẫn với cận xấu nhất `O(n)`: tất cả khóa vẫn có thể rơi vào cùng một ngăn.

### Một ví dụ cụ thể

Cho `m=8` và bốn khóa `1,9,17,25` với `h(k)=k`. Vì mọi khóa đều có `k mod 8=1`, cả bốn nằm cùng một chuỗi. Nếu các nút được giữ theo thứ tự thêm, tìm khóa 25 có thể phải so sánh 4 nút.

Trong khi đó, tập khóa `1,2,3,4` có cùng `n=4`, cùng `m=8`, cùng hệ số tải `α=0,5`, nhưng nằm ở bốn ngăn khác nhau. **Hệ số tải thấp không tự bảo đảm không có va chạm bất lợi**.

Việc chèn một nút mới **đã biết chắc khóa chưa có** vào đầu chuỗi có thể là `O(1)`. Tuy nhiên, thao tác `put` chuẩn của *map* thường phải kiểm tra trùng khóa để không tạo hai bản ghi cùng khóa logic; chi phí này phụ thuộc độ dài chuỗi.

## 5. Chi phí kỳ vọng của địa chỉ mở

Trong **open addressing**, mỗi ô chứa tối đa một bản ghi đang hoạt động. Khi va chạm, thao tác thử những ô kế tiếp theo quy tắc thăm dò. Muốn chèn khóa mới vào bảng chưa mở rộng, phải còn vị trí dùng được; thường duy trì `α<1`.

Ở **mô hình băm đều lý tưởng cho địa chỉ mở** (mỗi khóa có thứ tự thăm dò phân bố đều như một hoán vị ngẫu nhiên của `m` ô, phù hợp với các khóa khác), khi **không xét xóa**, các cận số lần thăm dò kỳ vọng quen thuộc là:

\[
\begin{aligned}
\mathbb{E}[\text{tìm không thấy}]&\leq\frac{1}{1-\alpha},\\
\mathbb{E}[\text{tìm thấy}]&\leq
\frac{1}{\alpha}\ln\frac{1}{1-\alpha},
\qquad 0<\alpha<1.
\end{aligned}
\]

| `α` | Cận trên: tìm không thấy | Cận trên: tìm thấy |
| ---: | ---: | ---: |
| 0,50 | 2,00 lần thăm dò | Khoảng 1,39 lần |
| 0,75 | 4,00 lần thăm dò | Khoảng 1,85 lần |
| 0,90 | 10,00 lần thăm dò | Khoảng 2,56 lần |

Đây là **cận trên kỳ vọng theo một mô hình xác suất mạnh**, không phải kết quả đo thực tế hoặc bảo đảm cho từng lần tìm. Đặc biệt:

- **Linear probing** có thể tạo cụm ô liên tiếp (*primary clustering*), nên không được tự áp dụng các công thức của mô hình hoán vị thăm dò ngẫu nhiên chỉ vì chỉ số ban đầu phân bố đều.
- **Quadratic probing** có thể lặp ô trước khi duyệt hết bảng; băm kép cần chọn bước nhảy phù hợp, chẳng hạn `gcd(h_2(k),m)=1`, nếu muốn dãy đi qua đủ mọi ô.
- **Tombstone** do xóa làm kéo dài đường thăm dò. Nếu có `d` ô đã xóa, `β=(n+d)/m` cho biết tỷ lệ ô chưa phải `EMPTY`, có thể quan trọng hơn `α=n/m` đối với tìm thất bại.

Khi các giả định về phân bố và tải được giữ phù hợp, số ô cần thử kỳ vọng thường được xem là `O(1)`. Nhưng một lần tìm trong bảng gần đầy hoặc bị kết cụm nặng có thể tốn **`O(m)`** lần thăm dò.

## 6. Trường hợp xấu nhất: khi mọi giả định thuận lợi đều thất bại

**Trường hợp xấu nhất** hỏi: trong những trạng thái/đầu vào hợp lệ có kích thước đang xét, **nhiều nhất** một thao tác có thể cần bao nhiêu bước?

### Với nối chuỗi

Giả sử một bảng 16 ngăn có `n` khóa nhưng hàm băm đưa tất cả vào ngăn 0. Nếu khóa cần tìm ở cuối chuỗi hoặc không tồn tại, thao tác phải kiểm tra `n` nút: **`O(n)`**. Tăng từ 16 lên 32 ngăn chưa chắc sửa được vấn đề nếu các khóa tiếp tục cho cùng chỉ số mới.

Nếu chèn tuần tự `n` khóa khác nhau đều chung ngăn và mỗi `put` phải kiểm tra khóa đã tồn tại, tổng số lần so sánh có thể là:

\[
0+1+2+\cdots+(n-1)
=\frac{n(n-1)}2
=\Theta(n^2).
\]

Chính sách resize có thể giữ `α` nhỏ nhưng **không thay đổi được** cận này nếu các khóa vẫn dồn vào cùng một chuỗi.

### Với địa chỉ mở

Một thao tác tìm, thêm hoặc xóa có thể phải kiểm tra gần như toàn bộ `m` ô, tức **`O(m)` bước thăm dò**. Với bảng thường giữ `m=\Theta(n)`, cận này cũng có thể biểu diễn là `O(n)`; tuy nhiên cần nói rõ kích thước nào đang được dùng.

Nếu dùng quadratic probing không có độ phủ đủ, phép chèn có thể **không tìm được ô trống hợp lệ dù `n<m`**. Đó là vấn đề tính đúng đắn/điều kiện áp dụng, không chỉ vấn đề tốc độ.

### Tình huống dữ liệu không đáng tin cậy

Khi khóa do người bên ngoài chủ động chọn, một hàm băm dễ bị tạo va chạm có thể dẫn đến **hash flooding**, làm các thao tác chậm bất thường. Khi đánh giá rủi ro, cần cân nhắc thiết kế hàm băm/seed, khả năng kẻ tấn công quan sát kết quả và giới hạn tài nguyên. Không được dùng một kỳ vọng trên dữ liệu ngẫu nhiên để khẳng định chắc chắn tốc độ với dữ liệu đối kháng.

## 7. Chi phí khấu hao: nhìn vào cả chuỗi thao tác

Giả sử bảng tự **nhân đôi dung lượng** khi cần. Một lần chèn thường chỉ đặt một bản ghi, nhưng đúng lúc bảng đầy, chương trình phải tạo mảng mới và chuyển nhiều khóa cũ. Chi phí lần chèn đó không hằng số.

**Phân tích khấu hao (amortized analysis)** không giả định rằng các thao tác xảy ra ngẫu nhiên. Nó phân bổ chi phí của một số thao tác đắt lên toàn bộ một chuỗi đủ dài các thao tác, để tìm cận tổng:

\[
\text{Chi phí khấu hao mỗi thao tác}
\approx \frac{\text{tổng chi phí cả chuỗi}}{\text{số thao tác}}.
\]

Đây là **cận toán học cho tổng chi phí**, không phải số đo trung bình của các lần gọi thực tế và không phải kỳ vọng xác suất.

### Ví dụ đếm số bản ghi được chuyển

Xét bảng với dung lượng ban đầu `m=4`, tăng gấp đôi **trước khi thêm khóa mới vào bảng đã đầy**. Bỏ qua chi phí tra cứu khóa cũ và chỉ đếm:

- 1 đơn vị cho việc ghi bản ghi mới;
- 1 đơn vị cho mỗi bản ghi cũ phải chuyển khi tăng dung lượng.

| Lần thêm | Dung lượng trước → sau | Bản ghi cũ phải chuyển | Chi phí lần thêm theo mô hình |
| ---: | --- | ---: | ---: |
| 1 | 4 → 4 | 0 | 1 |
| 2 | 4 → 4 | 0 | 1 |
| 3 | 4 → 4 | 0 | 1 |
| 4 | 4 → 4 | 0 | 1 |
| 5 | 4 → 8 | 4 | 5 |
| 6–8 | 8 → 8 | 0 | 1 mỗi lần |
| 9 | 8 → 16 | 8 | 9 |

Sau 9 lần thêm, có **9 lần ghi bản ghi mới** và **4+8=12 lần chuyển bản ghi cũ**, tổng 21 đơn vị. Lần thêm thứ 9 tốn 9 đơn vị, nhưng trung bình của cả chuỗi theo mô hình chỉ là `21/9\approx2,33` đơn vị.

Với `N` lần thêm, các đợt chuyển khi tăng gấp đôi có kích thước tăng theo cấp số nhân:

\[
4+8+16+\cdots+2^r < 2^{r+1}=O(N).
\]

Vì mỗi lần nhân đôi chỉ xuất hiện sau khi có thêm đủ khóa, **tổng số lần chuyển bản ghi trong `N` lần thêm là `O(N)`** (với dung lượng khởi đầu là hằng số). Cộng thêm `N` lần ghi bản ghi mới, chi phí phân bổ cho phần **chèn và mở rộng** là **`O(1)` trên mỗi lần thêm**.

Nếu tính cả việc khởi tạo mảng mới, tổng số ô được khởi tạo qua các lần nhân đôi cũng là tổng một cấp số nhân, nên vẫn là `O(N)` trong thiết kế thông thường. Tuy nhiên, chi phí **so sánh khóa do va chạm** phải được phân tích riêng.

## 8. Cách nhìn khấu hao bằng “tiền dành trước”

Ta có thể hình dung mỗi lần chèn rẻ **để dành một khoản tín dụng** để chi trả cho việc chuyển dữ liệu sau này. Giữa hai lần nhân đôi, nhiều khóa đã được thêm; mỗi khóa mới đóng góp một ít tín dụng. Khi cần rehash, tổng tín dụng đó trả cho việc chuyển các bản ghi cũ.

Một cách viết chặt chẽ hơn là **phương pháp thế năng (potential method)**:

\[
\widehat{c}_i=c_i+\Phi(S_i)-\Phi(S_{i-1}),
\]

trong đó `c_i` là chi phí thật của thao tác thứ `i`, còn `\Phi(S_i)\geq0` là “năng lượng dự trữ” sau thao tác. Khi cộng nhiều thao tác, các hiệu thế năng triệt tiêu:

\[
\sum_{i=1}^{N}\widehat{c}_i
=\sum_{i=1}^{N}c_i+\Phi(S_N)-\Phi(S_0).
\]

Nếu `\Phi(S_0)=0`, thế năng không âm và mỗi `\widehat c_i\leq C`, ta có tổng chi phí thật không vượt quá `CN`.

Với **mô hình mảng chỉ tăng gấp đôi khi đầy**, một ví dụ thế năng là:

\[
\Phi(n,m)=\max(0,2n-m).
\]

Trong mô hình chỉ đếm **1 lần ghi khóa mới + số khóa cũ chuyển khi tăng**, mỗi lần thêm thông thường làm thế năng tăng không quá 2, nên chi phí khấu hao không quá 3. Khi bảng đầy có `n=m`, lần thêm tiếp theo chuyển `m` khóa và tăng dung lượng lên `2m`; thế năng giảm từ `m` còn 2, bù cho chi phí chuyển `m` khóa. Do đó chi phí khấu hao theo mô hình này vẫn không quá 3.

Phân tích thế năng trên dành cho **tăng dung lượng** với chi phí chuyển bản ghi; nếu tính cả khởi tạo ô, xóa và giảm dung lượng, cần mở rộng mô hình chi phí và chọn thế năng thích hợp. Không thể tự áp dụng nguyên công thức cho mọi bảng băm có resize.

## 9. Khấu hao không chữa được va chạm: mã Python để quan sát

Đoạn mã sau minh họa một bảng **nối chuỗi** cho khóa nguyên. Nó đếm riêng số bản ghi chuyển khi rehash và số lần so sánh khóa. Bảng nhân đôi **trước khi thêm khóa mới khi đã có `n=m`**, để minh họa đúng chuỗi chi phí ở mục trước. Mã chỉ phục vụ học thuật và không chạy thử tự động trong bước biên soạn.

```python
class BangBamDemChiPhi:
    def __init__(self, m=4):
        if m <= 0:
            raise ValueError("Dung lượng phải dương")
        self.ngan = [[] for _ in range(m)]
        self.so_khoa = 0
        self.so_chuyen = 0
        self.so_so_sanh = 0

    def _bam_lai(self, m_moi):
        ngan_moi = [[] for _ in range(m_moi)]
        for chuoi in self.ngan:
            for khoa, gia_tri in chuoi:
                ngan_moi[khoa % m_moi].append((khoa, gia_tri))
                self.so_chuyen += 1
        self.ngan = ngan_moi

    def gan(self, khoa: int, gia_tri):
        i = khoa % len(self.ngan)
        for j, (khoa_cu, _) in enumerate(self.ngan[i]):
            self.so_so_sanh += 1
            if khoa_cu == khoa:
                self.ngan[i][j] = (khoa, gia_tri)
                return  # Cập nhật, không tăng n hoặc resize

        if self.so_khoa == len(self.ngan):
            self._bam_lai(2 * len(self.ngan))
            i = khoa % len(self.ngan)

        self.ngan[i].append((khoa, gia_tri))
        self.so_khoa += 1

    def lay(self, khoa: int):
        for khoa_cu, gia_tri in self.ngan[khoa % len(self.ngan)]:
            self.so_so_sanh += 1
            if khoa_cu == khoa:
                return gia_tri
        raise KeyError(khoa)


# Trường hợp A: 9 khóa khác nhau, ít va chạm
a = BangBamDemChiPhi()
for k in range(9):
    a.gan(k, str(k))
print(a.so_khoa, len(a.ngan), a.so_chuyen, a.so_so_sanh)
# 9 16 12 2

# Trường hợp B: 9 khóa cùng chia hết cho 16
b = BangBamDemChiPhi()
for k in range(9):
    b.gan(16 * k, str(k))
print(b.so_khoa, len(b.ngan), b.so_chuyen, b.so_so_sanh)
# 9 16 12 36

print(b.lay(128))    # "8": cần đi tới khóa cuối trong chuỗi
print(b.so_so_sanh)  # 45, gồm 36 so sánh khi thêm và 9 khi tìm
```

Hai trường hợp cùng có **9 lần thêm, 12 bản ghi chuyển, dung lượng cuối 16**, tức phần chi phí resize giống nhau. Ở A chỉ có **2 phép so sánh**: khóa mới `4` và `8` trùng ngăn với khóa `0` **trước lúc tăng dung lượng**, rồi được phân bố lại vào ngăn riêng. Nhưng ở B, các khóa `0,16,32,...,128` luôn nằm chung ngăn 0 khi `m` là `4,8,16`: kiểm tra khóa trùng trong các lần thêm cần `0+1+...+8=36` phép so sánh.

Kết luận quan trọng: **khấu hao `O(1)` cho việc mở rộng không chứng minh `put` đầy đủ là `O(1)` trong mọi trường hợp**. Muốn phát biểu **chi phí kỳ vọng, khấu hao `O(1)`** cho `put`, ta cần kết hợp hai lập luận độc lập:

1. **Kỳ vọng:** phân bố băm và hệ số tải được kiểm soát làm chi phí tìm đúng ngăn/ô nhỏ về trung bình.
2. **Khấu hao:** những đợt resize đắt được trải trên nhiều lần chèn.

## 10. Khi có xóa và giảm dung lượng

Nếu bảng cũng tự **thu nhỏ (shrink)**, phép xóa có thể kích hoạt rehash và trở thành thao tác tốn `O(n+m)`. Chi phí phân bổ cho chuỗi thêm–xóa vẫn có thể tốt nếu chính sách tránh **co–giãn liên tục**.

Một cách là đặt hai ngưỡng cách nhau rõ rệt, ví dụ:

- Tăng khi tải vượt `0,75`.
- Giảm khi tải xuống dưới `0,20`, và không giảm dưới dung lượng tối thiểu.

Vì hai ngưỡng đủ xa, việc thêm/xóa một vài khóa gần điểm kích hoạt không lập tức gây resize theo chiều ngược lại. Ngược lại, nếu giảm ngay sau khi vừa tăng hoặc tăng lại ngay sau khi vừa giảm, một chuỗi thao tác qua lại có thể liên tục trả chi phí chuyển toàn bộ bản ghi.

Ở bảng **địa chỉ mở có tombstone**, số khóa đang hoạt động `n` có thể giảm trong khi số ô chưa trống `n+d` vẫn cao. Rehash **cùng dung lượng** có thể dọn tombstone, còn tăng/giảm dung lượng thay đổi mức sử dụng bộ nhớ. Chi phí của các lần dọn định kỳ cũng cần được tính vào phân tích phân bổ, không thể giả định là miễn phí.

Các phép `get` chỉ đọc không trực tiếp “đóng góp” thêm khóa để chi trả resize; chính sách chọn thời điểm dọn tombstone và hỗn hợp thao tác có thể ảnh hưởng cận phân bổ tổng thể. Khi đánh giá thuật toán, cần xác định rõ chuỗi thao tác nào và điều kiện nào đang được bảo đảm.

## 11. Đọc đúng một bảng độ phức tạp

Các kết luận sau giả định khóa có chi phí băm và so sánh `O(1)`, và một bảng có resize thích hợp khi được nêu:

| Phát biểu | Điều kiện chính | Ý nghĩa thực sự |
| --- | --- | --- |
| `get` kỳ vọng `O(1)` | Băm phân bố phù hợp, tải được kiểm soát | Trung bình theo mô hình xác suất, **không** phải mọi lần gọi |
| `put` không resize kỳ vọng `O(1)` | Như trên, kiểm tra va chạm không kéo dài | Một lần chèn/cập nhật thông thường |
| Riêng resize là `O(n+m)` | Chuyển `n` bản ghi, khởi tạo mảng kích thước `m` | Một lần chuyển bảng có thể đắt |
| Chi phí resize khấu hao `O(1)` mỗi lần thêm | Nhân đôi và có đủ lần thêm giữa các lần tăng | Cận của **tổng nhiều thao tác**, không cần ngẫu nhiên |
| `put` kỳ vọng, khấu hao `O(1)` | Đồng thời có giả định băm tốt và resize hợp lý | Kết hợp **hai kiểu lập luận** |
| Tra cứu xấu nhất nối chuỗi `O(n)` | Có thể có một chuỗi dài `n` | Một thao tác bất lợi phải duyệt tất cả nút |
| Tra cứu xấu nhất địa chỉ mở `O(m)` | Có thể phải thử gần như toàn bộ các ô | Một thao tác bất lợi đi qua nhiều vị trí |

Ba câu hỏi nên đặt ra khi đọc một phát biểu về bảng băm:

1. **Chi phí của thao tác nào?** `get`, `put`, `remove` hay một đợt rehash?
2. **Tính theo loại bảo đảm nào?** kỳ vọng, trường hợp xấu nhất, phân bổ, hay kỳ vọng kết hợp phân bổ?
3. **Giả định là gì?** phân bố hàm băm, hệ số tải, chiến lược va chạm, chính sách resize, độ dài khóa, mức tin cậy của đầu vào?

Không nên viết chung chung “bảng băm luôn `O(1)`”. Nên viết: **“Tra cứu kỳ vọng `O(1)` khi băm phân bố phù hợp và tải được kiểm soát; trường hợp xấu nhất có thể tuyến tính theo số bản ghi hoặc số ô.”**

## 12. Tự kiểm tra

**Câu 1.** Một phép tìm cần 1 bước với xác suất `0,8` và 6 bước với xác suất `0,2`. Chi phí kỳ vọng là bao nhiêu? Nó có giới hạn mọi lần tìm ở mức đó không?

**Đáp án:** `E[T]=0,8\cdot1+0,2\cdot6=2` bước. Không; vẫn có những lần cần 6 bước.

**Câu 2.** Bảng nối chuỗi có `n=80` và `m=100`, vậy `α=0,8`. Có thể bảo đảm một phép tìm luôn `O(1)` không?

**Đáp án:** Không. Nếu phân bố băm phù hợp, có thể lập luận chi phí **kỳ vọng** `O(1+α)=O(1)`. Nhưng một ngăn vẫn có thể chứa nhiều khóa, nên trường hợp xấu nhất là `O(n)`.

**Câu 3.** Khi thêm khóa thứ 9 làm bảng tăng từ 8 lên 16 ô, chuyển 8 bản ghi cũ và chèn 1 bản ghi mới, chi phí theo mô hình đơn vị là bao nhiêu? Vì sao vẫn có thể nói chi phí resize khấu hao `O(1)`?

**Đáp án:** Lần đó có chi phí 9 đơn vị, không phải `O(1)` riêng lẻ. Các lần tăng xảy ra thưa dần theo số khóa, tổng số bản ghi chuyển qua `N` lần thêm khi nhân đôi dung lượng là `O(N)`, nên phần chi phí resize **khấu hao** `O(1)` mỗi lần thêm.

**Câu 4.** Tại sao khấu hao tốt cho resize chưa chứng minh `put` với bất kỳ tập khóa nào cũng nhanh?

**Đáp án:** Mỗi `put` vẫn có thể phải so sánh nhiều khóa trong một chuỗi va chạm hoặc thăm dò nhiều ô. Với `n` khóa dồn một ngăn, các lần kiểm tra trùng khóa có thể tốn tổng `\Theta(n^2)` dù số bản ghi chuyển khi resize chỉ là `O(n)`.

**Câu 5.** Một bảng địa chỉ mở có `m=100`, `n=20` và `d=50` tombstone. Vì sao không thể chỉ nhìn `α=0,2` để kết luận tìm thất bại sẽ rẻ?

**Đáp án:** Có `β=(n+d)/m=0,7` ô không phải EMPTY; tìm thất bại phải đi xuyên qua tombstone. Số bước còn phụ thuộc cách chúng phân bố trên những dãy thăm dò.

**Câu 6.** Sự khác biệt cốt lõi giữa “kỳ vọng `O(1)`” và “khấu hao `O(1)`” là gì?

**Đáp án:** Kỳ vọng là lấy trung bình theo **mô hình ngẫu nhiên**; khấu hao là chia chi phí đắt của một số thao tác trên **cả chuỗi thao tác**, có thể hoàn toàn xác định. Khi nói `put` **kỳ vọng, khấu hao `O(1)`**, cả hai loại giả định đều cần được làm rõ.

**Ghi nhớ:** Phân tích bảng băm phải tách ba góc nhìn: **kỳ vọng** để đánh giá ảnh hưởng của phân bố băm, **khấu hao** để giải thích vì sao resize thỉnh thoảng đắt nhưng tổng chi phí tăng trưởng vẫn tốt, và **trường hợp xấu nhất** để nhận diện chuỗi va chạm hoặc thăm dò dài. Chỉ khi kết hợp đúng các giả định về khóa, tải và chính sách quản lý bảng mới có thể kết luận một thao tác có chi phí kỳ vọng, khấu hao `O(1)`.

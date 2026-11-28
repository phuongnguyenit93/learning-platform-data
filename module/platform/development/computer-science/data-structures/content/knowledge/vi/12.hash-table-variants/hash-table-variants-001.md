# Băm phổ dụng và lựa chọn ngẫu nhiên từ một họ hàm băm

Một bảng băm (hash table) lưu cặp **khóa – giá trị** bằng cách đưa khóa vào một vị trí trong mảng thông qua hàm băm. Trong cấu trúc dữ liệu, vấn đề quan trọng không chỉ là tính chỉ số thật nhanh, mà còn là tránh tình trạng nhiều khóa cùng rơi vào một vị trí. **Băm phổ dụng** (*universal hashing*) giải quyết vấn đề này bằng cách chọn ngẫu nhiên một hàm băm từ một **họ hàm** có tính chất toán học được bảo đảm.

Bài học tập trung vào ý nghĩa của tính phổ dụng, cách chọn hàm ngẫu nhiên, một họ hàm cụ thể cho khóa nguyên, và tác động của cách chọn đó đến số va chạm và độ phức tạp của bảng băm. Đây là một kỹ thuật để lựa chọn và đánh giá cấu trúc dữ liệu dựa trên bất biến, thời gian và bộ nhớ.

## 1. Tại sao một hàm băm cố định có thể gây vấn đề?

Giả sử bảng băm có `m = 7` ô và dùng hàm:

\[
h(k)=k\bmod 7.
\]

Các khóa `10, 17, 24, 31` đều có chỉ số bằng `3`. Nếu bảng dùng **separate chaining** (mỗi ô trỏ tới một danh sách các phần tử), cả bốn khóa phải nằm trong cùng danh sách:

```text
Chỉ số:  0    1    2    3                    4    5    6
          ·    ·    ·    [10 → 17 → 24 → 31]  ·    ·    ·
```

Để tìm một khóa trong danh sách này, bảng có thể phải duyệt nhiều phần tử dù vẫn còn các ô trống. Nếu có `n` khóa và tất cả cùng va chạm, tìm kiếm trong chuỗi có thể tốn `O(n)` thời gian.

Việc cố định `h(k) = k mod m` còn làm các khóa có cùng phần dư dễ bị gom lại. Khi dữ liệu có quy luật, hoặc một bên khác có thể chủ động chọn khóa, việc tính chỉ số nhanh không đủ để bảo đảm thao tác nhanh.

Ta muốn một cách chọn hàm sao cho **với bất kỳ hai khóa phân biệt được xác định trước**, xác suất chúng va chạm là nhỏ. Tính ngẫu nhiên nằm ở việc *chọn hàm*, không nhất thiết ở bản thân dữ liệu.

## 2. Họ hàm băm và phép chọn ngẫu nhiên

Gọi:

- `U` là tập các khóa có thể xuất hiện (*key universe*).
- `m` là số ô của bảng băm, với chỉ số thuộc `{0, 1, ..., m-1}`.
- `H` là một tập gồm nhiều hàm băm `h: U → {0, 1, ..., m-1}`, gọi là **họ hàm băm**.

Khi tạo bảng băm, ta chọn ngẫu nhiên một hàm `h` trong `H`, rồi **giữ nguyên hàm đó** để chèn, tìm kiếm và xóa khóa trong bảng. Mọi lần tra cứu cùng khóa phải cho ra cùng chỉ số khi bảng chưa được xây dựng lại.

```mermaid
flowchart TD
    A[Khởi tạo bảng băm] --> B[Chọn ngẫu nhiên h từ họ H]
    B --> C[Cố định h cho bảng hiện tại]
    C --> D[Chèn / tìm / xóa khóa k]
    D --> E[Tính i = h(k)]
    E --> F[Truy cập ô i và xử lý va chạm]
```

Điểm cần phân biệt:

| Cách làm | Điều gì xảy ra? |
| --- | --- |
| Dùng mãi một hàm cố định | Dễ gặp các mẫu khóa bất lợi đã biết trước. |
| Chọn ngẫu nhiên một hàm trong họ khi tạo bảng | Có thể giới hạn **xác suất va chạm** đối với các cặp khóa cố định, nếu họ hàm có tính phổ dụng. |
| Chọn hàm mới mỗi lần tra cứu | **Sai**: cùng khóa có thể được đưa đến các vị trí khác nhau, làm hỏng thao tác tìm kiếm. |

Không phải cứ tạo ra vài hàm rồi chọn ngẫu nhiên là có bảo đảm tốt. Chất lượng của cả **họ hàm** mới quyết định xác suất va chạm.

## 3. Định nghĩa băm phổ dụng

Họ `H` được gọi là **phổ dụng** (*universal*) đối với bảng có `m` ô nếu, khi chọn `h` **đều và ngẫu nhiên** trong `H`, mọi cặp khóa phân biệt `x, y ∈ U` đều thỏa:

\[
\boxed{\Pr_{h\sim H}\big[h(x)=h(y)\big]\leq\frac{1}{m},\qquad x\neq y.}
\]

Ví dụ, với `m = 100`, xác suất hai khóa phân biệt **đã được xác định trước khi chọn hàm** rơi vào cùng ô không vượt quá `1/100`.

Ý nghĩa của công thức:

1. Xác suất được tính trên **lựa chọn ngẫu nhiên của hàm `h`**, không phải do mỗi lần gọi `h(x)` đều tung xúc xắc.
2. Điều kiện áp dụng cho **từng cặp** khóa khác nhau; không chỉ nói rằng các khóa có vẻ phân bố đều trong một bộ dữ liệu mẫu.
3. Bảo đảm là về **xác suất**, không khẳng định bảng không bao giờ có va chạm. Một lần chọn hàm cụ thể vẫn có thể cho phân bố không thuận lợi.

Một thuộc tính mạnh hơn thường gặp là **độc lập từng đôi** (*pairwise independence*, đôi khi gọi là *strongly 2-universal*): với mọi `x ≠ y` và mọi chỉ số `i, j`, ta có

\[
\Pr[h(x)=i\ \land\ h(y)=j]=\frac{1}{m^2}.
\]

Nếu mỗi cặp giá trị băm độc lập và đều trên `m` ô thì họ đó cũng phổ dụng. **Chiều ngược lại không bắt buộc đúng**: chỉ giới hạn xác suất va chạm chưa đủ để suy ra độc lập từng đôi.

## 4. Xây dựng một họ hàm phổ dụng cho khóa nguyên

Một xây dựng kinh điển sử dụng phép toán trên trường số nguyên modulo số nguyên tố.

Giả sử khóa là số nguyên trong tập `U = {0, 1, ..., p-1}`, trong đó `p` là **số nguyên tố** và số ô của bảng thỏa `1 ≤ m ≤ p`. Với hai tham số `a, b`, định nghĩa:

\[
\boxed{h_{a,b}(k)=\big((ak+b)\bmod p\big)\bmod m.}
\]

Chọn tham số **đều và độc lập** theo quy tắc:

\[
a\in\{1,2,\dots,p-1\},\qquad b\in\{0,1,\dots,p-1\}.
\]

Mỗi cặp `(a, b)` xác định một hàm. Toàn bộ các hàm đó tạo thành họ `H`. Khi khởi tạo bảng, chỉ cần chọn ngẫu nhiên **một cặp `(a, b)`**, rồi giữ cặp này cho tới khi xây dựng lại bảng.

**Tại sao cần `p` là số nguyên tố và `a ≠ 0`?** Với hai khóa phân biệt `x, y` trong `[0, p-1]`, hiệu `x-y` có nghịch đảo modulo `p`. Do đó, khi `(a, b)` được chọn như trên, hai giá trị

\[
u=(ax+b)\bmod p,\qquad v=(ay+b)\bmod p
\]

trở thành một cặp **phần dư phân biệt** được chọn đều trong các cặp có `u ≠ v` trên `{0, ..., p-1}`. Với một `u` cố định, chỉ có tối đa `⌈p/m⌉−1` giá trị `v ≠ u` cho cùng phần dư modulo `m`. Vì vậy:

\[
\Pr[h_{a,b}(x)=h_{a,b}(y)]
\leq\frac{\lceil p/m\rceil-1}{p-1}
\leq\frac{1}{m}.
\]

Đó chính là tính phổ dụng. Phép `mod p` tạo cấu trúc đại số cần thiết cho chứng minh; phép `mod m` cuối cùng đưa kết quả về chỉ số của bảng.

**Giới hạn của xây dựng:** Nếu hai khóa khác nhau nhưng bị quy về **cùng một giá trị modulo `p` trước khi băm**, chúng chắc chắn va chạm với mọi `(a, b)`. Vì thế, điều kiện khóa thuộc `[0, p-1]` và là các giá trị phân biệt trong miền đó là thiết yếu. Muốn xử lý khóa âm, chuỗi hoặc số nguyên lớn hơn `p`, phải thiết kế thêm một phép biểu diễn/biến đổi thích hợp và kiểm tra rằng phép đó không phá vỡ bảo đảm đang sử dụng.

## 5. Ví dụ tính tay: cùng dữ liệu, hai cách chọn hàm

Ta tạo một bảng có `m = 7` ô, chọn `p = 101` (số nguyên tố) và có năm khóa:

```text
12, 23, 42, 57, 68
```

Tất cả khóa đều nằm trong `[0, 100]`, nên đáp ứng miền của họ hàm. So sánh hai thành viên trong cùng họ:

- `h₁(k) = ((1·k + 0) mod 101) mod 7`.
- `h₂(k) = ((7·k + 3) mod 101) mod 7`.

| Khóa `k` | `(k mod 101) mod 7` với `(a,b)=(1,0)` | `(7k+3) mod 101` | `h₂(k)` |
| ---: | ---: | ---: | ---: |
| 12 | 5 | 87 | 3 |
| 23 | 2 | 63 | 0 |
| 42 | 0 | 95 | 4 |
| 57 | 1 | 99 | 1 |
| 68 | 5 | 75 | 5 |

Với `h₁`, khóa `12` và `68` va chạm ở ô `5`. Với `h₂`, cả năm khóa đi vào năm ô khác nhau. Điều này **không chứng minh `h₂` luôn tốt hơn `h₁`**: nếu đổi bộ khóa, tình hình có thể ngược lại. Bảo đảm phổ dụng nói về xác suất khi chọn đều từ **toàn bộ họ** chứ không phải chất lượng tuyệt đối của một cặp tham số.

Trong cả hai trường hợp, số khóa `n = 5`, số ô `m = 7`, nên **hệ số tải** (*load factor*) là:

\[
\alpha=\frac{n}{m}=\frac{5}{7}\approx0{,}714.
\]

Hệ số tải cho biết lượng dữ liệu trung bình trên mỗi ô khi dùng chaining, nhưng không mô tả trọn vẹn mức độ tập trung của khóa. Hai bảng có cùng `α` vẫn có thể có độ dài chuỗi khác nhau.

## 6. Cài đặt Python: chọn hàm một lần khi khởi tạo

Ví dụ sau dùng `secrets.randbelow` để chọn đều tham số trong miền hợp lệ. Việc dùng nguồn ngẫu nhiên khó dự đoán là lựa chọn triển khai hữu ích, **không biến họ hàm minh họa này thành hàm băm mật mã**.

```python
from secrets import randbelow


def choose_universal_hash(p: int, m: int):
    """Trả về (h, (a, b)); yêu cầu p là số nguyên tố và 1 <= m <= p."""
    if p < 2 or not (1 <= m <= p):
        raise ValueError("Cần p >= 2 và 1 <= m <= p")

    # a thuộc [1, p-1], b thuộc [0, p-1].
    a = 1 + randbelow(p - 1)
    b = randbelow(p)

    def h(key: int) -> int:
        if type(key) is not int or not (0 <= key < p):
            raise ValueError("Khóa phải là số nguyên trong [0, p-1]")
        return ((a * key + b) % p) % m

    return h, (a, b)


p, m = 101, 7
keys = [12, 23, 42, 57, 68]
h, parameters = choose_universal_hash(p, m)
buckets = [[] for _ in range(m)]  # Separate chaining

for key in keys:
    buckets[h(key)].append(key)

print("Tham số (a, b):", parameters)
for index, chain in enumerate(buckets):
    print(index, chain)

# Khi tìm một khóa, sử dụng lại h đã chọn:
target = 42
found = target in buckets[h(target)]
print("Tìm thấy:", found)
```

Kết quả về tham số và cách phân bố khóa **có thể khác ở mỗi lần chạy**. Tuy nhiên, trong **một lần chạy**, hàm `h` được giữ cố định và mọi khóa đã chèn đều có thể được tìm lại trong đúng chuỗi. Phần kiểm tra đầu vào chỉ xác minh miền giá trị; ứng dụng thực tế còn cần kiểm tra hoặc bảo đảm từ trước rằng `p` thực sự là số nguyên tố.

Nếu ngôn ngữ sử dụng số nguyên có giới hạn bit, phép `a * key + b` có thể tràn số trước khi lấy modulo. Cài đặt cần dùng kiểu nguyên đủ rộng hoặc phép nhân modulo an toàn; Python xử lý số nguyên độ dài tùy ý nên ví dụ trên không bị tràn theo cách đó.

## 7. Băm phổ dụng giúp gì cho độ phức tạp?

Giả sử đã cố định trước một tập `n` khóa **phân biệt** và chọn ngẫu nhiên hàm `h` từ một họ phổ dụng vào bảng có `m` ô.

### 7.1. Số cặp va chạm kỳ vọng

Với mỗi cặp khóa `i < j`, đặt biến chỉ báo `Iᵢⱼ = 1` khi hai khóa va chạm và bằng `0` nếu không. Số **cặp khóa** va chạm là:

\[
C=\sum_{i<j} I_{ij}.
\]

Vì `E[Iᵢⱼ] = Pr[h(kᵢ)=h(kⱼ)] ≤ 1/m`, tính tuyến tính của kỳ vọng cho:

\[
\boxed{\mathbb{E}[C]\leq\binom{n}{2}\frac{1}{m}
=\frac{n(n-1)}{2m}.}
\]

Ta **không cần** giả sử các sự kiện va chạm của những cặp khác nhau là độc lập để cộng kỳ vọng. Lưu ý `C` là số *cặp khóa va chạm*, không phải số ô có va chạm.

### 7.2. Thời gian tìm kiếm với separate chaining

Xét một khóa `x` cố định. Với mỗi khóa `y ≠ x` đang có trong bảng, xác suất `y` nằm trong cùng chuỗi với `x` không vượt quá `1/m`. Vì thế, số phần tử khác cùng ô với `x` có kỳ vọng không vượt quá:

\[
\frac{n-1}{m}<\frac{n}{m}=\alpha.
\]

Nếu duyệt tuyến tính trong mỗi chuỗi, độ dài cần xem xét cho một phép tìm kiếm thành công có kỳ vọng `O(1 + α)`. Với một khóa vắng mặt được cố định trước, độ dài chuỗi cần xem xét cũng có kỳ vọng `O(α)`, cộng với chi phí tính chỉ số là `O(1)`. Khi duy trì `α = n/m = O(1)`, các thao tác tra cứu cơ bản với chaining đạt **thời gian kỳ vọng `O(1)`** theo mô hình chi phí băm hằng số.

| Tình huống | Thời gian tìm kiếm với chaining |
| --- | --- |
| Hàm được chọn có phân bố rất xấu | Có thể lên tới `O(n)` trong trường hợp xấu nhất. |
| Họ phổ dụng, tập khóa cố định độc lập với lần chọn hàm | `O(1 + α)` **theo kỳ vọng** trên lựa chọn hàm. |
| Duy trì số ô `m = Θ(n)` | `O(1)` theo kỳ vọng với các giả thiết trên. |

**Phạm vi bảo đảm:** Những kết luận trên xét dữ liệu hoặc chuỗi thao tác được xác định độc lập với tham số bí mật/ngẫu nhiên đã chọn. Nếu một đối thủ nhìn thấy kết quả băm và **chọn thêm khóa thích ứng** để gây va chạm, chỉ riêng định nghĩa phổ dụng không đủ chứng minh cùng giới hạn kỳ vọng. Tương tự, không được tự suy ra giới hạn cho **linear probing** hoặc các chiến lược thăm dò khác chỉ từ tính phổ dụng; phân tích của chúng có thể cần tính độc lập mạnh hơn.

## 8. Quyết định thiết kế và những nhầm lẫn thường gặp

| Vấn đề | Cách hiểu đúng |
| --- | --- |
| Băm phổ dụng có loại bỏ hoàn toàn va chạm? | Không. Nó khống chế xác suất va chạm của từng cặp khóa cố định. |
| Băm phổ dụng có giống **perfect hashing**? | Không. Perfect hashing nhằm tạo ánh xạ không va chạm trên một tập khóa cụ thể; universal hashing vẫn có thể va chạm. |
| Băm phổ dụng có đồng nghĩa với băm mật mã? | Không. Bảo đảm cặp va chạm `≤ 1/m` không tương đương khả năng chống giả mạo, kháng va chạm theo nghĩa mật mã hoặc chống đối thủ thích ứng. |
| Có cần đổi `(a,b)` sau mỗi lần gọi? | Không. Chọn một lần cho bảng hiện tại, giữ ổn định; nếu xây dựng lại hoặc tái băm toàn bộ bảng mới có thể chọn lại. |
| Có thể băm thẳng chuỗi bằng công thức số nguyên này? | Chưa thể. Cần biểu diễn khóa phù hợp và bảo đảm phép chuyển đổi không gộp các khóa phân biệt thành cùng đầu vào modulo `p`. |
| Tăng `m` có đủ để chữa mọi va chạm? | Tăng `m` giúp giảm `α`, nhưng vẫn cần chọn hàm có phân bố phù hợp và xử lý va chạm đúng. |

Khi dùng bảng băm để cài đặt từ điển, tập hợp, bộ đếm tần suất hoặc bộ nhớ đệm, quy trình thiết kế hợp lý là: xác định miền khóa; chọn chiến lược xử lý va chạm; chọn `m`, `p` và họ hàm phù hợp; chọn ngẫu nhiên tham số khi khởi tạo; giám sát hệ số tải để tăng kích thước và tái băm khi cần.

Đối với các dịch vụ phải đối diện đầu vào không đáng tin cậy, cần đánh giá riêng nguy cơ **hash flooding**. Một họ phổ dụng đơn giản có thể hữu ích để phân tích thuật toán nhưng không tự động đủ khả năng chống đối thủ biết hoặc suy ra tham số. Trong trường hợp đó, có thể cần cơ chế băm có khóa bí mật được thiết kế cho môi trường đối kháng, tùy yêu cầu bảo mật và hiệu năng của hệ thống.

## 9. Tự kiểm tra hiểu biết

**Câu 1.** Với `m = 50`, phát biểu nào là đúng cho một họ băm phổ dụng?

- A. Mọi bảng được khởi tạo đều không có va chạm.
- B. Với hai khóa khác nhau cố định trước, xác suất va chạm khi chọn đều một hàm không vượt `1/50`.
- C. Mỗi lần tìm kiếm một khóa phải chọn lại hàm băm.

**Đáp án:** B. A nhầm bảo đảm theo xác suất với kết quả chắc chắn; C phá vỡ tính nhất quán giữa chèn và tìm.

**Câu 2.** Cho `p = 11`, `m = 5`, `a = 3`, `b = 1`. Hãy tính chỉ số của `k = 2`, `k = 6` và `k = 9`.

**Lời giải:**

\[
\begin{aligned}
h(2)&=((3\cdot2+1)\bmod11)\bmod5=7\bmod5=2,\\
h(6)&=((3\cdot6+1)\bmod11)\bmod5=8\bmod5=3,\\
h(9)&=((3\cdot9+1)\bmod11)\bmod5=6\bmod5=1.
\end{aligned}
\]

Ba khóa đi vào ba ô khác nhau trong lần chọn `(a,b)=(3,1)` này. Kết quả đó không đủ để kết luận hàm này không va chạm trên **mọi** tập khóa.

**Câu 3.** Một bảng chứa `n = 100` khóa phân biệt và có `m = 200` ô. Hãy chặn trên số cặp va chạm kỳ vọng nếu chọn ngẫu nhiên từ họ phổ dụng.

**Lời giải:**

\[
\mathbb{E}[C]\leq\frac{100\cdot99}{2\cdot200}=24{,}75.
\]

Đây là kỳ vọng của **số cặp** va chạm qua nhiều lần chọn ngẫu nhiên hàm, không khẳng định một bảng cụ thể sẽ có đúng `24,75` cặp.

## 10. Ghi nhớ

**Băm phổ dụng** là cách thiết kế **một họ hàm băm** sao cho mọi cặp khóa phân biệt có xác suất va chạm không quá `1/m` khi chọn đều một hàm. Với khóa nguyên nằm trong `[0, p-1]`, một họ kinh điển là `hₐ,ᵦ(k) = ((ak+b) mod p) mod m`, với `p` nguyên tố, `a` khác `0` và `(a,b)` được chọn ngẫu nhiên trong miền quy định.

Khi kết hợp với **separate chaining** và duy trì hệ số tải `α = O(1)`, tính phổ dụng đưa đến thời gian tra cứu **`O(1)` theo kỳ vọng** cho các khóa được xác định độc lập với lựa chọn hàm. Phân biệt rõ **kỳ vọng** với **trường hợp xấu nhất**, đồng thời giữ nguyên hàm trong suốt thời gian sử dụng bảng, là hai điều thiết yếu khi áp dụng kỹ thuật này.

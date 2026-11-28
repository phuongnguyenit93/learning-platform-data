# Thăm dò bậc hai, băm kép và điều kiện để duyệt được vị trí cần thiết

## 1. Vấn đề: bảng còn ô trống nhưng vẫn không thêm được khóa?

Một **bảng băm (hash table)** dùng **địa chỉ mở (open addressing)** lưu các cặp khóa–giá trị trực tiếp trong một mảng có `m` ô. Hàm băm xác định vị trí đầu tiên dành cho khóa; nếu ô đó đã chứa khóa khác, bảng thử các vị trí tiếp theo theo một **dãy thăm dò (probe sequence)**.

Thăm dò tuyến tính thử lần lượt `h(k), h(k)+1, h(k)+2, ...` (theo modulo `m`). Thăm dò bậc hai (*quadratic probing*) và băm kép (*double hashing*) thay đổi khoảng cách giữa các lần thử nhằm hạn chế hiện tượng nhiều khóa cùng bị dồn vào một cụm ô.

Tuy nhiên, có một câu hỏi quan trọng hơn chuyện “có bao nhiêu ô trống”:

> **Dãy thăm dò của khóa có đi đến được một ô trống hay không?**

Một dãy có thể **lặp lại những vị trí cũ** trước khi đi hết mảng. Khi đó, phép thêm có thể thất bại dù ở nơi khác vẫn còn ô trống. Bài học này tập trung vào điều kiện toán học và bất biến cài đặt giúp tránh lỗi đó.

### Ký hiệu chung

- `k`: khóa cần chèn hoặc tìm.
- `m > 0`: số ô của bảng, có chỉ số `0, 1, ..., m-1`.
- `h_1(k)`: chỉ số ban đầu đã chuẩn hóa về `[0,m-1]`.
- `j = 0,1,2,...`: số thứ tự lần thử, với `j=0` là lần thử đầu tiên.
- `p(k,j)`: ô được kiểm tra ở lần thử `j`.
- `n`: số khóa đang hoạt động; `α=n/m` là **hệ số tải**.

Ở đây ta giả sử khóa có phép so sánh bằng nhau nhất quán với hàm băm. Các ví dụ dùng khóa nguyên, nên có thể tính mã băm và các chỉ số bằng số học đơn giản.

## 2. Thế nào là duyệt đủ vị trí?

Một quy tắc thăm dò có **chu kỳ đầy đủ (full cycle / full permutation)** nếu, với một khóa cố định, `m` lần thử đầu tiên ghé **tất cả `m` ô đúng một lần**. Khi đó, nếu còn bất kỳ ô có thể nhận khóa mới, dãy thăm dò sẽ đến được ô ấy trong tối đa `m` lần thử.

Ngược lại, một quy tắc chỉ ghé `r < m` ô khác nhau có thể bỏ qua `m-r` ô còn lại. Nếu toàn bộ `r` ô có thể ghé đều đã bận, không thể chèn theo quy tắc đó cho dù toàn bảng chưa đầy.

```text
Có 8 ô:        0  1  2  3  4  5  6  7
Dãy thăm dò:   3 -> 4 -> 7 -> 4 -> 3 -> ...
                                      (lặp)

Nếu 3, 4, 7 đã bận thì dãy không chạm tới 0,1,2,5,6 đang trống.
```

Điều kiện “đi qua mọi ô” là **điều kiện đủ rất hữu ích**, nhưng không phải lúc nào cũng bắt buộc trong mọi thiết kế. Một số phương pháp chỉ bảo đảm chèn thành công khi hệ số tải thấp và dãy có đủ nhiều vị trí khác nhau; ta cần phát biểu đúng **giả định** gắn với bảo đảm ấy.

## 3. Thăm dò bậc hai (quadratic probing)

Công thức thường gặp là:

\[
p(k,j) = \big(h_1(k)+c_1j+c_2j^2\big)\bmod m.
\]

Hai hệ số `c_1,c_2` quyết định độ dịch của lần thử. Chọn chúng không phù hợp có thể làm dãy lặp sớm, vì thế **không tồn tại bảo đảm tổng quát** rằng mọi biến thể của quadratic probing đều thăm đủ `m` ô.

### Ví dụ: bình phương `j²` trên bảng 11 ô

Chọn `m=11`, `c_1=0`, `c_2=1` và khóa có `h_1(k)=3`:

\[
p(k,j)=(3+j^2)\bmod11.
\]

| Lần thử `j` | `j² mod 11` | Ô `(3+j²) mod 11` | Ghi chú |
| ---: | ---: | ---: | --- |
| 0 | 0 | 3 | Ô đầu tiên |
| 1 | 1 | 4 | Mới |
| 2 | 4 | 7 | Mới |
| 3 | 9 | 1 | Mới |
| 4 | 5 | 8 | Mới |
| 5 | 3 | 6 | Mới |
| 6 | 3 | 6 | **Lặp ô 6** |
| 7 | 5 | 8 | Lặp ô 8 |
| 8 | 9 | 1 | Lặp ô 1 |
| 9 | 4 | 7 | Lặp ô 7 |
| 10 | 1 | 4 | Lặp ô 4 |

Trong `11` lần thử, dãy chỉ đến **sáu ô khác nhau**: `3,4,7,1,8,6`. Năm ô `0,2,5,9,10` không xuất hiện.

Giả sử các khóa `14,25,36,47,58,69` đều có chỉ số đầu `k mod11=3`. Nếu thêm lần lượt vào bảng trống bằng quy tắc trên, chúng được đặt tại:

```text
Khóa      14   25   36   47   58   69
Ô lưu      3    4    7    1    8    6

Chỉ số:    0    1    2    3    4    5    6    7    8    9   10
          [ ] [47] [ ] [14] [25] [ ] [69] [36] [58] [ ] [ ]
```

Thêm tiếp khóa `80` (cũng bắt đầu ở ô 3) **không tìm được ô đặt** trong dãy, dù bảng mới có `6/11` ô đang hoạt động và còn năm ô trống. Nguyên nhân nằm ở **tập vị trí có thể đi tới**, không phải ở tổng số ô trống.

### Vì sao các bình phương lặp?

Khi `m=11`, ta có `6^2\equiv5^2\pmod{11}`, `7^2\equiv4^2\pmod{11}`, ... vì `(11-j)^2\equiv j^2\pmod{11}`. Các số dư bình phương bị ghép thành từng cặp.

Đây không phải “lỗi của phép modulo”: nó là tính chất toán học của việc dùng `j^2` trên bảng có dung lượng đã chọn.

## 4. Bảo đảm hữu ích cho `j²` với dung lượng nguyên tố

Với `m=p` là **số nguyên tố lẻ** và công thức:

\[
p(k,j)=(h_1(k)+j^2)\bmod p,
\]

các giá trị `j=0,1,...,(p-1)/2` tạo **`(p+1)/2` vị trí khác nhau**.

**Lập luận ngắn:** Nếu hai chỉ số `a,b` trong phạm vi trên cho cùng ô, ta có

\[
a^2\equiv b^2\pmod p
\quad\Rightarrow\quad
(a-b)(a+b)\equiv0\pmod p.
\]

Do `p` nguyên tố, `p` phải chia `a-b` hoặc `a+b`. Nhưng `|a-b|<p` và `0\leq a+b\leq p-1`; vì vậy, với `a,b` không âm, chỉ có thể xảy ra `a=b`. Các ô tương ứng là khác nhau.

**Hệ quả về chèn:** Trước khi thêm một khóa mới, nếu bảng đang có `n < p/2` khóa hoạt động và **không có dấu đã xóa hoặc sai lệch khác làm hỏng quy tắc**, thì nhiều nhất `n` trong `(p+1)/2` ô của nửa dãy đầu đã bị chiếm; ít nhất một ô còn trống, nên phép thêm sẽ thành công.

Đây là một bảo đảm **đủ**, thường được diễn đạt là “quadratic probing dạng `j^2` với bảng nguyên tố và tải dưới 1/2 bảo đảm có chỗ chèn”. Không nên hiểu rằng khi tải vượt 1/2, mọi phép thêm sẽ thất bại: có thể vẫn chèn được nếu dãy của khóa chạm ô trống.

Ví dụ `p=11`: sáu vị trí đầu `3,4,7,1,8,6` đều khác nhau. Nếu trước khi thêm chỉ có tối đa 5 ô đang chiếm trong toàn bảng, chắc chắn còn ít nhất một ô trống trong sáu vị trí này. Sau khi có sáu khóa chặn cả sáu vị trí, khóa tiếp theo có thể không chèn được.

**Cẩn thận:** Bảo đảm này gắn với dạng `j^2` cụ thể và dung lượng nguyên tố lẻ. Thay `c_1,c_2`, chọn dung lượng hợp số hoặc giả định dãy bất kỳ thì không thể dùng lại chứng minh trên một cách máy móc.

## 5. Một biến thể bậc hai thăm đủ bảng lũy thừa hai

Không phải mọi công thức bậc hai đều bị giới hạn như `j^2`. Chẳng hạn, với `m=2^r`, có thể dùng **độ dịch số tam giác**:

\[
p(k,j)=\left(h_1(k)+\frac{j(j+1)}{2}\right)\bmod m.
\]

Với `m=8`, các độ dịch ở `j=0,...,7` là:

```text
j:              0   1   2   3   4   5   6   7
j(j+1)/2:       0   1   3   6  10  15  21  28
mod 8:          0   1   3   6   2   7   5   4
```

Tập số dư `{0,1,2,3,4,5,6,7}` xuất hiện đầy đủ, không lặp trong tám lần đầu. Trên thực tế, quy tắc số tam giác này tạo một hoán vị của mọi ô khi `m` là lũy thừa hai và triển khai phép tính chỉ số chính xác.

Ví dụ này cho thấy **lựa chọn hàm dịch và dung lượng phải đi cùng nhau**. Không thể chỉ nói “dùng quadratic probing” rồi mặc nhiên suy ra độ phủ toàn bảng. Đồng thời, vì những khóa có cùng `h_1` vẫn đi theo cùng độ dịch nên dạng này chưa tự loại bỏ **kết cụm thứ cấp**.

## 6. Băm kép: lấy bước nhảy từ khóa

Thay vì dùng cùng độ dịch `j` hay `j^2` cho tất cả khóa, **băm kép (double hashing)** tính thêm một giá trị `h_2(k)` làm **bước nhảy**:

\[
p(k,j)=\big(h_1(k)+j\cdot h_2(k)\big)\bmod m.
\]

- `h_1(k)` quyết định ô đầu tiên.
- `h_2(k)` quyết định khoảng cách giữa hai lần thử kế tiếp, theo modulo `m`.
- Hai khóa có cùng `h_1` nhưng khác `h_2` có thể đi theo hai dãy khác nhau, giảm hiện tượng các khóa phải cùng đi một dãy (secondary clustering).

Để **đi qua đủ `m` ô**, bước nhảy `s=h_2(k)` phải thỏa:

\[
\gcd(s,m)=1.
\]

Trong đó `\gcd` là **ước chung lớn nhất**. Điều kiện này cũng loại trừ bước nhảy `0\bmod m` khi `m>1`.

### Chứng minh qua chu kỳ modulo

Dãy thăm dò quay lại ô đầu tại lần thử dương nhỏ nhất `t` sao cho:

\[
ts\equiv0\pmod m.
\]

Số vị trí khác nhau được đi qua trước khi lặp là:

\[
\boxed{\text{số ô khác nhau}=\frac{m}{\gcd(s,m)}}.
\]

Nếu `\gcd(s,m)=1`, chu kỳ dài đúng `m`. Nếu `\gcd(s,m)>1`, dãy chỉ ghé một phần các ô.

Ví dụ `m=12`, `h_1=3`:

| Bước nhảy `s` | `gcd(s,12)` | Số ô khác nhau | Một chu kỳ thăm dò |
| ---: | ---: | ---: | --- |
| 4 | 4 | 3 | `3 → 7 → 11` |
| 6 | 6 | 2 | `3 → 9` |
| 5 | 1 | 12 | `3 → 8 → 1 → 6 → 11 → 4 → 9 → 2 → 7 → 0 → 5 → 10` |

Nếu bước nhảy bằng 4, các ô khác dù trống vẫn không giúp ích nếu ba ô 3, 7, 11 đã bận. Với bước nhảy bằng 5, phép chèn đi qua đủ 12 ô trước khi lặp.

## 7. Chọn `h_2(k)` thế nào để thăm đủ ô?

Có hai cách tổ chức dung lượng phổ biến:

### Khi `m` là số nguyên tố

Với `m=p` nguyên tố, mọi `s\in\{1,2,...,p-1\}` đều nguyên tố cùng nhau với `p`. Một **ví dụ minh họa cho khóa nguyên không âm** là:

\[
h_1(k)=k\bmod p,\qquad
h_2(k)=1+(k\bmod(p-1)).
\]

Hàm thứ hai cho bước nhảy trong `1,...,p-1`, nên dãy của mỗi khóa đi đủ `p` ô. Tuy nhiên, nó vẫn có thể cho nhiều khóa cùng cặp `(h_1,h_2)`, và không tự bảo đảm phân bố đều trên dữ liệu thực tế.

### Khi `m` là lũy thừa hai

Nếu `m=2^r` với `r\geq1`, thì `\gcd(s,m)=1` **khi và chỉ khi `s` lẻ**. Có thể thiết kế hàm bước nhảy sao cho luôn tạo số lẻ, chẳng hạn lấy các bit trộn của khóa rồi ép bit thấp thành 1. Cần tránh phụ thuộc vào một vài bit kém phân bố trong đầu vào.

### Sai lầm dễ mắc

- Dùng `h_2(k)=0`: dãy đứng yên ở một ô.
- Dùng `h_2(k)=2` trên bảng `m=8`: chỉ duyệt bốn ô.
- Dùng `h_2(k)=m`: bước nhảy tương đương 0 modulo `m`.
- Chọn `h_2` thay đổi giữa **chèn** và **tìm** cùng khóa: đường tra cứu có thể không đi tới ô đã lưu.
- Nghĩ rằng `h_2` khác 0 là đủ: với `m` hợp số, còn cần kiểm tra `\gcd(h_2,m)=1`.

## 8. Cùng một tập khóa: bậc hai gặp giới hạn, băm kép vẫn còn đường

Xét lại `m=11` và các khóa `14,25,36,47,58,69,80`. Cả bảy khóa đều có chỉ số đầu tiên:

\[
h_1(k)=k\bmod11=3.
\]

Với **quadratic probing `j^2`**, sáu khóa đầu chiếm hết các ô `3,4,7,1,8,6`; khóa 80 không thể đến ô trống.

Với **double hashing** dùng `h_2(k)=1+(k\bmod10)`:

| Khóa | `h_1(k)` | `h_2(k)` | Các ô đã thử | Ô lưu |
| ---: | ---: | ---: | --- | ---: |
| 14 | 3 | 5 | `3` | 3 |
| 25 | 3 | 6 | `3 → 9` | 9 |
| 36 | 3 | 7 | `3 → 10` | 10 |
| 47 | 3 | 8 | `3 → 0` | 0 |
| 58 | 3 | 9 | `3 → 1` | 1 |
| 69 | 3 | 10 | `3 → 2` | 2 |
| 80 | 3 | 1 | `3 → 4` | 4 |

```text
Chỉ số:    0    1    2    3    4    5    6    7    8    9   10
          [47] [58] [69] [14] [80] [ ]  [ ]  [ ]  [ ] [25] [36]
```

Trong ví dụ này, bước nhảy khác nhau khiến sáu khóa sau khóa đầu đi tới sáu ô khác nhau chỉ trong **hai lần thử**. Đây là một trường hợp minh họa, **không phải bảo đảm** rằng double hashing luôn có tối đa hai lần thử. Nếu bảng gần đầy, hàm băm phân bố lệch hoặc các khóa trùng cả `h_1` và `h_2`, thời gian thăm dò vẫn có thể tăng mạnh.

## 9. Python: tạo dãy và mô phỏng chèn vào bảng cố định

Đoạn mã sau tách hai quy tắc thăm dò để tự quan sát **số ô có thể duyệt** và **đường đi cho từng khóa**. Nó không dùng `dict` làm bảng và không tự resize, nhằm bộc lộ rõ giới hạn của dãy.

```python
def probe_quadratic(k: int, m: int):
    """Dãy h1(k) + j*j, giới hạn m lần thử."""
    h1 = k % m
    for j in range(m):
        yield (h1 + j * j) % m


def probe_double(k: int, m: int):
    """Dành cho m là số nguyên tố; các khóa ví dụ là số nguyên."""
    h1 = k % m
    step = 1 + (k % (m - 1))
    for j in range(m):
        yield (h1 + j * step) % m


def chen_mo_phong(bang: list, khoa: int, tao_day):
    da_thu = []
    for i in tao_day(khoa, len(bang)):
        da_thu.append(i)
        if bang[i] is None:
            bang[i] = khoa
            return i, da_thu
    return None, da_thu


keys = [14, 25, 36, 47, 58, 69, 80]
m = 11

for ten, tao_day in [
    ("quadratic j^2", probe_quadratic),
    ("double hashing", probe_double),
]:
    bang = [None] * m
    print(ten)
    for key in keys:
        vi_tri, da_thu = chen_mo_phong(bang, key, tao_day)
        print(f"  {key}: vi_tri={vi_tri}, thu={da_thu}")
    print("Bang:", bang)
```

Với `quadratic j^2`, khóa `80` trả về `vi_tri=None` do dãy thăm dò lặp lại các ô đã chiếm. Với `double hashing`, cả bảy khóa đều được chèn; các vị trí lần lượt là `3,9,10,0,1,2,4`.

Đây chỉ là mô phỏng thao tác **chèn khóa mới**; bản đồ khóa–giá trị đầy đủ còn phải kiểm tra khóa đã tồn tại, xử lý cập nhật, `get`, xóa, `EMPTY/DELETED` và phân bố lại khi đổi dung lượng. Nếu số ô quá nhỏ (`m=1`), công thức `probe_double` minh họa sẽ không hợp lệ vì `m-1=0`; hãy dùng số nguyên tố `m\geq2`, như `11` trong ví dụ.

## 10. Những bất biến quan trọng khi triển khai

**Thăm dò nhất quán:** Tìm kiếm cùng khóa phải lặp lại chính xác dãy đã dùng khi thêm. Quy tắc chọn hệ số, bước nhảy và dung lượng bảng không thể bị thay đổi tùy tiện giữa hai thao tác.

**Kiểm tra khóa thay vì chỉ kiểm tra chỉ số:** Nhiều khóa khác nhau có thể cùng `h_1`, thậm chí cùng cả `h_1` và `h_2`. Muốn cập nhật đúng khóa, phải so sánh khóa logic.

**Giới hạn số lần thăm dò:** Mỗi thao tác chỉ nên kiểm tra một số lần hữu hạn. Với dãy có chu kỳ đầy đủ, tối đa `m` lần đủ để quyết định còn ô phù hợp hay không; với dãy không đầy đủ, lặp thêm cũng không giúp khám phá các ô ngoài chu kỳ.

**Đảm bảo có đường đến ô trống:** Với `j^2` trên bảng nguyên tố lẻ, có thể dựa trên bảo đảm tải dưới 1/2 trước khi chèn. Với băm kép, chọn bước nhảy nguyên tố cùng nhau với `m` để bao phủ toàn bảng. Không đánh đồng hai kiểu bảo đảm.

**Xóa không làm đứt đường tìm:** Trong địa chỉ mở, xóa bằng cách lập tức đánh dấu ô là `EMPTY` có thể khiến tìm kiếm dừng trước vị trí khóa nằm phía sau. Thường dùng **tombstone (DELETED)** hoặc một thuật toán xóa và sắp lại có chứng minh đúng riêng cho quy tắc thăm dò.

**Xử lý tombstone khi thêm:** Được phép ghi nhớ vị trí đã xóa để tái sử dụng, nhưng phải tiếp tục dò để tránh tạo bản sao của một khóa đang tồn tại ở phía sau.

**Resize phải tái chèn:** Đổi `m` có thể làm thay `h_1(k)`, `h_2(k)` và tính chất chu kỳ. Cần tạo bảng mới với các tham số hợp lệ và tái chèn toàn bộ bản ghi đang hoạt động; không chỉ sao chép nguyên vị trí cũ.

## 11. Độ phức tạp và cách lựa chọn

Nếu `m` là số ô và chi phí tính băm, so sánh khóa được coi là `O(1)`, một thao tác có thể tốn tới **`O(m)` lần kiểm tra ô** trong trường hợp xấu nhất. Điều kiện **duyệt đủ vị trí** bảo đảm khả năng tìm được ô trống nếu còn, chứ **không tự bảo đảm thời gian trung bình `O(1)`**.

Thời gian kỳ vọng tốt còn phụ thuộc phân bố của cặp hàm băm, mô hình xác suất, hệ số tải và cách xóa. Nói “băm kép thăm đủ mọi ô” không đồng nghĩa “băm kép luôn nhanh hơn quadratic probing”. Khi tải cao, ngay cả dãy đầy đủ vẫn có thể phải thử rất nhiều ô.

| Tiêu chí | Quadratic probing | Double hashing |
| --- | --- | --- |
| Độ dịch | Hàm bậc hai của `j` | `j` nhân với bước nhảy theo khóa |
| Độ phủ | Phụ thuộc hệ số và `m`; dạng `j^2` trên nguyên tố lẻ chỉ ghé `(m+1)/2` ô | Đủ `m` ô nếu `gcd(h_2(k),m)=1` |
| Kết cụm | Có thể giảm cụm sơ cấp nhưng các khóa cùng `h_1` có cùng dãy | Các khóa cùng `h_1` có thể có dãy khác nhau |
| Tính toán | Không cần hàm bước nhảy thứ hai | Phải thiết kế và tính thêm `h_2` |
| Cần giám sát | Dung lượng, hệ số, ngưỡng tải, điều kiện chèn thành công | Dung lượng, bước nhảy, tính nguyên tố cùng nhau, tải |

Nếu workload có nhiều phép tìm không thành công hoặc bảng thường gần đầy, cần đặc biệt chú ý **số ô đã kiểm tra** và chính sách mở rộng; sự khác nhau giữa hai phương pháp thể hiện rõ hơn qua phép đo trên dữ liệu thực tế.

## 12. Tự kiểm tra

**Câu 1.** Với `m=11`, `p(k,j)=(3+j^2) mod 11`, dãy có thể đi qua bao nhiêu ô khác nhau trong 11 lần thử đầu?

**Đáp án:** Sáu ô: `3,4,7,1,8,6`. Sau đó các vị trí lặp. Không thể khẳng định sẽ tìm được ô trống bất kỳ nằm ở nơi khác trong bảng.

**Câu 2.** Tại sao khi `p=11` và bảng đang có không quá 5 khóa, quy tắc `(h_1+j^2) mod11` bảo đảm tìm được một ô trống cho khóa mới?

**Đáp án:** Sáu vị trí ứng với `j=0,1,2,3,4,5` khác nhau; tối đa năm ô của toàn bảng đang có khóa, nên ít nhất một trong sáu vị trí vẫn trống.

**Câu 3.** Với băm kép có `m=12` và `h_2(k)=4`, dãy đi qua bao nhiêu ô khác nhau? Nếu chọn `h_2(k)=5` thì sao?

**Đáp án:** Bước 4 đi qua `12/gcd(12,4)=3` ô. Bước 5 đi qua `12/gcd(12,5)=12` ô, tức đủ cả bảng.

**Câu 4.** Khi `m=16`, bước nhảy của double hashing phải có đặc điểm gì để thăm đủ bảng?

**Đáp án:** Phải **lẻ** (tương đương nguyên tố cùng nhau với 16). Bước nhảy chẵn sẽ chỉ thăm một phần các ô.

**Câu 5.** Băm kép bảo đảm chu kỳ đầy đủ. Có thể kết luận phép tìm lúc nào cũng mất `O(1)` không?

**Đáp án:** Không. Chu kỳ đầy đủ nói về **khả năng tiếp cận tất cả các ô**, không về số lần thử ít nhất. Hiệu năng còn phụ thuộc tải, phân bố hàm băm và cách xử lý xóa; trường hợp xấu vẫn có thể thăm `O(m)` ô.

**Ghi nhớ:** Với địa chỉ mở, điều quyết định không chỉ là bảng còn ô trống mà là **dãy thăm dò có thể đi đến ô đó**. Quadratic probing phải kết hợp hệ số, dung lượng và ngưỡng tải đúng; double hashing muốn duyệt đủ bảng cần `gcd(h_2(k),m)=1`. Cả hai vẫn phải duy trì bất biến tìm–thêm–xóa nhất quán và đánh giá hiệu năng dưới giả định phân bố khóa phù hợp.

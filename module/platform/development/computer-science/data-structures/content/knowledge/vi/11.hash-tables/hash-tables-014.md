# Băm chuỗi, khóa tổ hợp và chi phí tính hàm băm

## 1. Từ khóa số nguyên sang khóa có cấu trúc

Trong **bảng băm (hash table)**, ta dùng một **khóa (key)** để định vị giá trị, chẳng hạn mã sinh viên để lấy hồ sơ. Nếu khóa là số nguyên nhỏ, việc tính chỉ số ban đầu có thể chỉ là phép chia lấy dư. Nhưng trong ứng dụng thực tế, khóa thường là:

- Chuỗi như `"SV-2026-014"`, email hoặc tên tài khoản.
- Cặp `(mã_lớp, mã_sinh_viên)` để phân biệt sinh viên có mã trùng giữa các lớp.
- Bộ nhiều thuộc tính như `(tenant_id, project_id, document_id)`.

Để dùng các khóa ấy, bảng phải tính **mã băm (hash code)** từ nội dung khóa, sau đó đưa về phạm vi ngăn hoặc ô của bảng. Ví dụ, với `m` ngăn:

\[
i(k)=h(k)\bmod m,\qquad 0\le i(k)<m,
\]

trong đó `h(k)` là mã băm và `i(k)` là **chỉ số ngăn**. Mã băm không phải địa chỉ bộ nhớ của bản ghi và cũng không phải định danh duy nhất: nhiều khóa khác nhau có thể tạo cùng mã băm hoặc cùng chỉ số ngăn.

Bài này đi sâu vào ba câu hỏi: **băm chuỗi như thế nào**, **băm khóa gồm nhiều thành phần ra sao**, và **việc tính hash thực sự tốn bao nhiêu thời gian**. Những câu hỏi này quan trọng khi so sánh lựa chọn bảng băm với cây tìm kiếm hoặc cấu trúc dữ liệu khác.

## 2. Băm chuỗi bằng cách duyệt từng ký tự

Một cách dạy học dễ quan sát là **băm đa thức lặp (polynomial-style rolling hash)**. Khởi đầu `h=0`; với mỗi ký tự `c`, cập nhật:

\[
h_{t+1}=(31h_t+\operatorname{code}(c_t))\bmod P,
\qquad h_0=0.
\]

Ở đây `\operatorname{code}(c)` là mã số của ký tự; trong Python, `ord(c)` trả về điểm mã Unicode. `P=1\,000\,000\,007` được dùng làm số mô-đun trong ví dụ. Hệ số `31` và mô-đun này chỉ để **minh họa**; không nên coi đây là một hàm băm bảo mật hoặc mặc định tối ưu cho mọi ứng dụng.

Với chuỗi `"ab"`:

| Bước | Ký tự | Mã ký tự | Mã băm sau bước |
| ---: | --- | ---: | ---: |
| Ban đầu | — | — | `0` |
| 1 | `a` | `97` | `31·0+97=97` |
| 2 | `b` | `98` | `31·97+98=3105` |

Với `"ba"`, kết quả là `31·98+97=3135`. Cùng hai ký tự nhưng đổi thứ tự sẽ **thường** đổi mã băm; việc đưa thứ tự vào phép trộn giúp tránh băm hai chuỗi chỉ theo tổng mã ký tự.

```python
P = 1_000_000_007


def bam_chuoi_minh_hoa(s: str) -> int:
    h = 0
    for ch in s:
        h = (31 * h + ord(ch)) % P
    return h


print(bam_chuoi_minh_hoa("ab"))  # 3105
print(bam_chuoi_minh_hoa("ba"))  # 3135
print(bam_chuoi_minh_hoa(""))    # 0
```

Hàm tính dần từ trái sang phải, không cần ghép chuỗi trung gian. Với chuỗi dài `L` ký tự Unicode, vòng lặp thực hiện `L` bước nên **thời gian tính mã băm từ đầu là `O(L)`** và bộ nhớ phụ của phép lặp là `O(1)` nếu coi kích thước số mô-đun cố định.

Sau khi có mã băm, bảng còn phải ánh xạ nó vào `m` ngăn hoặc ô và xử lý va chạm. Hai bước **tính mã băm** và **tìm trong bảng** cần được tính riêng khi phân tích hiệu năng.

## 3. Va chạm vẫn xảy ra dù đã băm toàn bộ chuỗi

Độ dài chuỗi có thể không giới hạn, còn không gian mã băm khi dùng mô-đun `P` là hữu hạn. Vì vậy, theo nguyên lý Dirichlet, **không thể** băm tất cả chuỗi phân biệt vào các giá trị hữu hạn mà không có va chạm.

Ngay trong ví dụ với hệ số `31`, hai chuỗi khác nhau có cùng mã:

\[
\begin{aligned}
h(\texttt{"Aa"}) &=31\cdot65+97=2112,\\
h(\texttt{"BB"}) &=31\cdot66+66=2112.
\end{aligned}
\]

```python
assert bam_chuoi_minh_hoa("Aa") == 2112
assert bam_chuoi_minh_hoa("BB") == 2112
assert "Aa" != "BB"
```

Khi hai khóa có cùng mã băm, bảng vẫn phải dùng **phép so sánh khóa thực sự** để phân biệt chúng:

- **Nối chuỗi:** hai cặp khóa–giá trị có thể cùng nằm trong một ngăn, rồi so sánh chuỗi khi tìm.
- **Địa chỉ mở:** khóa thứ hai có thể được đặt ở một ô khác trong dãy thăm dò, và khi tìm vẫn phải so sánh khóa lưu trong ô.

Ngay cả khi mã băm **khác nhau**, việc lấy phần dư theo `m` vẫn có thể đưa hai khóa vào cùng ngăn. Vì vậy, `hash(a)==hash(b)` **không suy ra** `a==b`.

**Hợp đồng bắt buộc theo chiều còn lại** là:

\[
a=b\quad\Longrightarrow\quad h(a)=h(b).
\]

Nếu hai khóa được xem là bằng nhau nhưng nhận mã băm khác nhau, bảng có thể không tìm lại được bản ghi hoặc lưu trùng một khóa logic.

## 4. Chuỗi Unicode: “nhìn giống” chưa chắc là cùng khóa

Băm chuỗi phải được định nghĩa trên một **biểu diễn cụ thể**: điểm mã Unicode, byte UTF-8 hoặc một dạng đã chuẩn hóa. Trong Unicode, những chuỗi có vẻ ngoài giống nhau có thể gồm các điểm mã khác nhau.

Ví dụ ký tự `é` có thể được biểu diễn bằng:

- Một điểm mã `U+00E9` (ký tự ghép sẵn).
- Hai điểm mã `U+0065` và `U+0301` (`e` cộng dấu sắc kết hợp).

Nếu chương trình xem hai chuỗi đó là **hai khóa khác nhau**, việc băm theo từng điểm mã cũng phải phân biệt chúng nhất quán. Nếu nghiệp vụ muốn xem chúng là **cùng một khóa**, phải **chuẩn hóa trước cả khi so sánh và khi băm**.

```python
import unicodedata

a = "é"             # Một điểm mã U+00E9
b = "e\u0301"       # e + dấu sắc kết hợp U+0301

print(a == b)       # False: chuỗi Python khác dãy điểm mã
print([hex(ord(x)) for x in a])  # ['0xe9']
print([hex(ord(x)) for x in b])  # ['0x65', '0x301']

a_nfc = unicodedata.normalize("NFC", a)
b_nfc = unicodedata.normalize("NFC", b)
print(a_nfc == b_nfc)  # True
```

Ngoài chuẩn hóa Unicode, một ứng dụng có thể cần **không phân biệt chữ hoa/chữ thường** hoặc bỏ khoảng trắng ở đầu/cuối. Các quyết định này phụ thuộc nghiệp vụ. Chẳng hạn, `"User42"` và `"user42"` có phải cùng tài khoản hay không không thể suy ra chỉ từ cấu trúc bảng băm.

Một cách tổ chức nhất quán là tạo **khóa chuẩn (canonical key)** trước khi đưa vào map:

```python
def chuan_hoa_ma(s: str) -> str:
    # Chỉ dùng khi nghiệp vụ muốn không phân biệt hoa/thường.
    return unicodedata.normalize("NFC", s).casefold()


bang = {}
bang[chuan_hoa_ma("TÀI KHOẢN")] = 10
print(bang[chuan_hoa_ma("tài khoản")])  # 10
```

Đối với một hệ thống thực tế, quy trình chuẩn hóa phải được quy định ổn định và kiểm tra với các trường hợp Unicode đặc biệt. Nếu đổi quy trình chuẩn hóa, các khóa lưu trước đó có thể cần di chuyển hoặc dựng lại chỉ mục.

### Băm byte khác băm điểm mã

Nếu xử lý từng byte của `s.encode("utf-8")` thay vì từng ký tự Python, số phần tử được duyệt là **số byte `B`**, không nhất thiết bằng số điểm mã `L`. Ví dụ `"é"` ở dạng ghép sẵn có 1 điểm mã nhưng UTF-8 chiếm 2 byte. Hai cách băm có thể trả mã khác nhau; cả hai đều có thể hợp lệ nếu việc tạo khóa và so sánh tuân thủ cùng quy ước.

Không nên trộn một nhánh chương trình băm theo điểm mã với nhánh khác băm theo byte rồi giả định kết quả phải giống nhau.

## 5. Khóa tổ hợp là gì?

**Khóa tổ hợp (composite key)** gồm từ hai thành phần trở lên, khi phải phối hợp tất cả các thành phần mới xác định duy nhất bản ghi.

Ví dụ trong hệ thống học tập:

```text
(course_id, student_id) -> kết quả học tập
("CS101", "SV022")       -> 8.5
("CS102", "SV022")       -> 9.0
```

Nếu dùng riêng `student_id`, hai kết quả của cùng sinh viên có thể ghi đè nhau. Ghép hai trường thành một khóa logic giúp map phân biệt các cặp khác nhau.

Nhưng **không nên ghép thẳng các thành phần mà không xác định ranh giới**:

```text
("ab", "c")  -> "abc"
("a", "bc")  -> "abc"
```

Hai khóa tổ hợp khác nhau bị biến thành cùng chuỗi trước cả khi tính hash: đây là lỗi **mã hóa mơ hồ**, không chỉ là va chạm băm thông thường.

Tương tự, cách làm `str(1) + str(23)` cho kết quả `"123"`, giống `str(12) + str(3)`. Ép mọi kiểu dữ liệu sang chuỗi còn có thể làm mất phân biệt giữa số nguyên `7` và chuỗi `"7"`.

**Giải pháp:** giữ cấu trúc thành phần rõ ràng, dùng tuple/record bất biến, hoặc tuần tự hóa theo quy tắc có **thông tin kiểu, độ dài và ranh giới** đủ để giải mã không nhập nhằng.

## 6. Hash cho khóa tổ hợp phải tôn trọng thứ tự, kiểu và phép bằng nhau

Một khái niệm thường dùng là **kết hợp hash**: tính mã băm từng thành phần rồi trộn chúng theo một thứ tự xác định. Ví dụ sơ đồ tư duy:

\[
H(k_1,k_2,\ldots,k_r)
=\operatorname{mix}(h(k_1),h(k_2),\ldots,h(k_r)).
\]

Hàm `mix` không nhất thiết là phép cộng. Nếu chỉ cộng mã của các thành phần, khóa `(a,b)` và `(b,a)` luôn có cùng tổng, dù thứ tự có ý nghĩa. Một phép trộn tốt nên đưa **thứ tự, ranh giới và thông tin kiểu** vào quy trình theo hợp đồng của hệ thống.

Tuy nhiên, bất kỳ mã băm hữu hạn nào cũng có thể va chạm. Điều cần đạt không phải là **không bao giờ trùng mã**, mà là:

1. Hai khóa tổ hợp bằng nhau theo quy tắc ứng dụng phải nhận cùng hash.
2. Các khóa khác nhau được trộn đủ tốt để giảm va chạm trên tập dữ liệu thực tế.
3. Bảng vẫn so sánh **toàn bộ các thành phần** khi cần phân biệt hai khóa cùng hash.

Trong Python, **tuple gồm các thành phần hashable** là cách biểu diễn đơn giản:

```python
diem = {}
diem[("CS101", "SV022")] = 8.5
diem[("CS102", "SV022")] = 9.0

print(diem[("CS101", "SV022")])  # 8.5
print(("ab", "c") == ("a", "bc"))  # False

# Dùng danh sách như một thành phần của tuple thì không hợp lệ:
# diem[("CS101", ["SV022"])] = 8.5  # TypeError: unhashable type: 'list'
```

Tuple giữ **thứ tự và ranh giới thành phần**. Python tính hash tổng hợp cho tuple bằng thuật toán của runtime; không nên tự giả định thuật toán đó luôn giống nhau giữa các phiên bản Python.

### Một khóa có tên trường rõ ràng

Với nhiều trường, đối tượng bất biến giúp tránh nhầm vị trí:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class KhoaKetQua:
    ma_khoa_hoc: str
    ma_sinh_vien: str
    lan_thi: int


ket_qua = {
    KhoaKetQua("CS101", "SV022", 1): 8.5,
    KhoaKetQua("CS101", "SV022", 2): 9.0,
}

print(ket_qua[KhoaKetQua("CS101", "SV022", 2)])  # 9.0
```

`@dataclass(frozen=True)` ngăn gán lại các thuộc tính thông thường, nhưng **không tự làm bất biến sâu** dữ liệu nằm trong trường. Nếu trường chứa cấu trúc mutable và tham gia hash/equality, vẫn có nguy cơ khóa bị thay đổi hoặc không hash được. Với `str`, `int` và các kiểu bất biến trong ví dụ, danh tính khóa ổn định.

## 7. Khi phải tuần tự hóa khóa tổ hợp thành byte

Một số hệ thống cần tạo khóa dạng byte để lưu lên đĩa, gửi qua mạng hoặc tính một giá trị băm bên ngoài tiến trình. Khi đó, chỉ nối các chuỗi thường không đủ. Cần một **quy tắc tuần tự hóa không nhập nhằng**.

Với khóa gồm toàn bộ **thành phần chuỗi**, một cách đơn giản là tiền tố độ dài:

```text
Số thành phần | Độ dài phần 1 | Byte phần 1 | Độ dài phần 2 | Byte phần 2 | ...
```

Ví dụ Python minh họa, dùng số nguyên không dấu 4 byte theo thứ tự big-endian:

```python
def ma_hoa_cac_chuoi(parts: tuple[str, ...]) -> bytes:
    chunks = [len(parts).to_bytes(4, "big")]
    for part in parts:
        b = part.encode("utf-8")
        chunks.append(len(b).to_bytes(4, "big"))
        chunks.append(b)
    return b"".join(chunks)


x = ma_hoa_cac_chuoi(("ab", "c"))
y = ma_hoa_cac_chuoi(("a", "bc"))
print(x == y)  # False
```

Quy tắc này cố tình giới hạn đầu vào ở tuple của **chuỗi**, với số thành phần và độ dài từng đoạn biểu diễn được bằng 4 byte. Một giao thức dùng trong sản xuất phải kiểm tra giới hạn, quy ước chuẩn hóa Unicode, phiên bản định dạng và **thẻ kiểu** nếu hỗ trợ thêm số nguyên, boolean, byte hoặc giá trị rỗng.

Mã hóa thành byte không làm hash trở nên một-một: hai dãy byte khác nhau **vẫn có thể cho cùng mã băm**. Lợi ích của mã hóa có ranh giới là tránh biến hai khóa logic khác nhau thành **cùng dãy byte** từ đầu.

## 8. Chi phí tính hàm băm: không thể mặc nhiên coi mọi khóa là O(1)

Các bảng độ phức tạp thường ghi `get`, `put`, `remove` có **thời gian kỳ vọng `O(1)`** khi hàm băm phân bố tốt, tải được kiểm soát. Phát biểu đó thường **giả định chi phí tính hash và so sánh khóa là `O(1)`**.

Với khóa chuỗi hoặc khóa tổ hợp, phải tách các phần chi phí:

\[
T_{\text{thao tác}}
=T_{\text{hash}}
+T_{\text{duyệt ngăn/thăm dò}}
+T_{\text{so sánh các khóa liên quan}}.
\]

| Loại khóa | Chi phí tính hash **từ đầu** | Chi phí so sánh bằng nhau ở trường hợp xấu | Lưu ý |
| --- | --- | --- | --- |
| Số nguyên có kích thước cố định | Thường `O(1)` | `O(1)` | Giả định phép toán số nguyên đơn vị |
| Chuỗi `L` ký tự | `O(L)` nếu duyệt toàn chuỗi | `O(L)` | Có thể phải so sánh tới ký tự cuối |
| Tuple có `r` số nguyên cố định | `O(r)` | `O(r)` | Tỷ lệ với số thành phần |
| Tuple có các chuỗi độ dài `L_1,...,L_r` | `O(r+\sum_i L_i)` nếu băm từ đầu | `O(r+\sum_i L_i)` | Thường cần duyệt nội dung các trường |
| Khóa đã có mã băm hợp lệ được cache | Có thể `O(1)` để lấy mã đã lưu | Vẫn có thể tuyến tính theo độ dài khóa | Chỉ đúng khi khóa không thay đổi và cache hợp lệ |

Ví dụ, nếu tìm một chuỗi dài `L=100{,}000` ký tự và thuật toán băm **đọc toàn bộ chuỗi**, riêng việc tạo mã băm đã cần `\Theta(L)` bước, cho dù sau đó tra cứu đúng một ô của bảng.

### Kỳ vọng O(1) là kỳ vọng cho phần nào?

Với bảng **nối chuỗi**, dưới mô hình băm đều, số nút kỳ vọng trong ngăn là `\alpha=n/m`, nên chi phí cấu trúc thường ghi là `O(1+\alpha)`. Nếu phép so sánh mỗi khóa lại có thể tốn `O(L)`, tổng chi phí không tự động còn `O(1+\alpha)` theo `L`.

Một cận diễn đạt an toàn là:

\[
T=O(H(k)+C)+\sum_{j=1}^{C}O(E(k,k_j)),
\]

trong đó `H(k)` là chi phí băm khóa tra cứu, `C` là số khóa/ô phải kiểm tra, và `E(k,k_j)` là chi phí so sánh với khóa được gặp. Nếu mọi khóa dài không quá `L`, một cận thô là `O(H(k)+CL)`. Khi `H(k)=O(L)`, cận trở thành `O(L+CL)`; các phép so sánh thường dừng sớm nhưng không nên xem đó là bảo đảm.

Với **địa chỉ mở**, số ô thăm dò kỳ vọng cũng có thể là hằng số trong những mô hình xác suất thích hợp, song vẫn cần cộng chi phí băm khóa và so sánh khóa trong những ô `OCCUPIED`. Trường hợp xấu có thể phải thử `O(m)` ô; với mỗi khóa dài `L`, chi phí so sánh có thể khiến tổng lớn hơn `O(m)` phép toán ký tự.

**Kết luận:** Khi độ dài khóa là tham số quan trọng, cách phát biểu chính xác thường là **“kỳ vọng số lần thăm dò `O(1)`, cộng chi phí tính hash và so sánh khóa”**, không phải “truy cập chuỗi dài bất kỳ luôn `O(1)`”.

## 9. Cache hash, chuẩn hóa và hiệu năng thực tế

Với **khóa bất biến**, có thể lưu mã băm đã tính để không phải duyệt lại nội dung khóa mỗi lần. Một số runtime triển khai kiểu chuỗi có cơ chế cache hash nội bộ, nhưng đó là **chi tiết cài đặt**; không được mặc định rằng mọi ngôn ngữ hoặc mọi cách tạo khóa đều được hưởng chi phí `O(1)` ở các lần sau.

Một số đánh đổi cần nhớ:

1. **Cache tiết kiệm thời gian băm**, nhưng tốn bộ nhớ lưu mã và không loại bỏ nhu cầu so sánh khi va chạm.
2. **Không cache trên khóa mutable** nếu những trường tham gia hash có thể đổi; mã băm cũ không còn phản ánh khóa hiện tại, còn việc thay mã trong bảng cũng không tự di chuyển bản ghi.
3. **Chuẩn hóa Unicode** có chi phí riêng, thường phụ thuộc độ dài chuỗi, và có thể cần bộ nhớ để tạo chuỗi chuẩn.
4. **Khóa tổ hợp có nhiều trường** có thể tốn chi phí đọc và trộn từng trường; với khóa nhỏ, chi phí cấp phát nhiều đối tượng trung gian còn đáng kể ở thực tế.
5. **Chọn hàm băm phân bố tốt** giúp giảm va chạm, nhưng một hàm phức tạp hơn cũng có thể tăng chi phí tính mã; cần cân bằng trên dữ liệu thật.

### Hash của Python không phải ID bền vững

Trong Python, có thể sử dụng `hash("abc")` và `hash(("a", 7))` để hỗ trợ `dict`/`set`. Tuy nhiên, giá trị `hash` của chuỗi có thể thay đổi giữa các tiến trình do cơ chế ngẫu nhiên hóa; **không được dùng `hash()` làm mã nhận dạng lâu dài hoặc so sánh trực tiếp qua các máy**.

Nếu cần một checksum hay digest ổn định để truyền hoặc lưu trữ, phải chọn thuật toán và định dạng byte có quy ước rõ ràng, ví dụ một hàm trong `hashlib` khi phù hợp. Nếu cần mục đích bảo mật, cũng phải phân biệt **hàm băm mật mã** với **hàm băm tối ưu cho tra cứu bảng**, vì chúng có yêu cầu và chi phí khác nhau. Digest ổn định cũng không bảo đảm không va chạm.

## 10. Ví dụ Python: bảng băm chuỗi với chi phí được quan sát rõ

Ví dụ sau cài đặt **nối chuỗi** bằng các danh sách ngăn để minh họa vị trí được tính từ `bam_chuoi_minh_hoa`. Chương trình lưu cặp `(key, value)`, kiểm tra khóa thật khi trùng mã băm, và đếm số ký tự được duyệt lúc tính mã.

```python
P = 1_000_000_007


def bam_va_dem(s: str):
    h = 0
    so_ky_tu = 0
    for ch in s:
        h = (31 * h + ord(ch)) % P
        so_ky_tu += 1
    return h, so_ky_tu


class BangBamChuoi:
    def __init__(self, so_ngan=8):
        if so_ngan <= 0:
            raise ValueError("Số ngăn phải dương")
        self.ngan = [[] for _ in range(so_ngan)]
        self.so_ky_tu_bam = 0
        self.so_so_sanh = 0

    def _chi_so(self, khoa: str):
        ma_bam, so_ky_tu = bam_va_dem(khoa)
        self.so_ky_tu_bam += so_ky_tu
        return ma_bam % len(self.ngan)

    def gan(self, khoa: str, gia_tri):
        i = self._chi_so(khoa)
        chuoi = self.ngan[i]
        for j, (k_cu, _) in enumerate(chuoi):
            self.so_so_sanh += 1
            if k_cu == khoa:
                chuoi[j] = (khoa, gia_tri)
                return
        chuoi.append((khoa, gia_tri))

    def lay(self, khoa: str):
        for k_cu, gia_tri in self.ngan[self._chi_so(khoa)]:
            self.so_so_sanh += 1
            if k_cu == khoa:
                return gia_tri
        raise KeyError(khoa)


bang = BangBamChuoi(8)
bang.gan("Aa", "Giá trị A")
bang.gan("BB", "Giá trị B")

print(bam_va_dem("Aa"))  # (2112, 2)
print(bam_va_dem("BB"))  # (2112, 2)
print(bang.ngan[0])
# [('Aa', 'Giá trị A'), ('BB', 'Giá trị B')]

print(bang.lay("BB"))        # Giá trị B
print(bang.so_ky_tu_bam)     # 6: 2+2 ký tự khi chèn, 2 khi tìm
print(bang.so_so_sanh)       # 3: 1 khi chèn BB, 2 khi tìm BB
```

Ở đây hai chuỗi khác nhau nhận cùng mã băm và nằm trong **một ngăn**, nhưng bảng vẫn phân biệt chúng vì phép tìm so sánh **toàn bộ khóa**.

Chú ý rằng `so_so_sanh` chỉ đếm **số lần so sánh chuỗi**, không đếm tổng số ký tự bên trong các phép so sánh ấy. Muốn đo chi phí từng ký tự khi so sánh, phải cài đặt hoặc đo thêm phép so sánh; không được đánh đồng “3 lần so sánh” với “3 thao tác ký tự”.

Hàm băm kiểu đa thức và bảng cố định trong ví dụ chỉ phục vụ học tập. Một hệ thống sản xuất cần lựa chọn hàm băm, bảo vệ trước dữ liệu bất lợi, xử lý dung lượng và đo hiệu năng trên tập khóa thực.

## 11. Các lỗi thiết kế thường gặp

1. **Dùng nối chuỗi trực tiếp làm khóa tổ hợp:** `("ab","c")` và `("a","bc")` bị nhập làm một nếu cùng biến thành `"abc"`.
2. **Bỏ qua quy tắc về Unicode hoặc chữ hoa/thường:** khóa mà nghiệp vụ coi là bằng nhau có thể bị băm và tìm như hai khóa khác nhau.
3. **Tưởng hai mã băm bằng nhau tức hai khóa bằng nhau:** bảng vẫn phải so sánh khóa thật khi có va chạm.
4. **Tưởng `O(1)` truy cập bảng bao gồm mọi chi phí xử lý chuỗi:** băm mới một chuỗi dài `L` thường cần `O(L)` thời gian.
5. **Dùng khóa tổ hợp chứa danh sách hoặc đối tượng mutable làm thành phần định danh:** có thể không hash được, hoặc thay đổi sau khi chèn làm mất khả năng tìm.
6. **Cache hash khi khóa còn có thể bị sửa:** có nguy cơ mã băm không nhất quán với trạng thái và vị trí lưu.
7. **Dùng `hash()` của runtime như ID cố định giữa nhiều tiến trình:** thuật toán hoặc seed có thể thay đổi.
8. **Chỉ xem phân bố hash mà quên chi phí tính hash:** hàm băm phức tạp có thể giảm va chạm nhưng tốn thời gian đọc/trộn khóa.

## 12. Tự kiểm tra

**Câu 1.** Với công thức `h=31h+ord(c)`, bắt đầu từ `h=0` và chưa chạm mô-đun `P`, hash của `"ab"` và `"ba"` là bao nhiêu?

**Đáp án:** `"ab"` là `31·97+98=3105`; `"ba"` là `31·98+97=3135`. Thứ tự ký tự ảnh hưởng kết quả.

**Câu 2.** Vì sao `"Aa"` và `"BB"` có cùng mã 2112 vẫn phải được xem là hai khóa khác nhau?

**Đáp án:** Mã băm là một giá trị hữu hạn có thể va chạm; `"Aa" != "BB"`. Bảng dùng hash để xác định nơi bắt đầu, rồi so sánh khóa thật để quyết định trùng hay không.

**Câu 3.** Vì sao không dùng `course_id + student_id` làm khóa nếu không có dấu phân cách hay độ dài từng trường?

**Đáp án:** Các bộ khác nhau, ví dụ `("ab","c")` và `("a","bc")`, có thể tạo cùng chuỗi `"abc"`. Nên dùng tuple, record bất biến hoặc mã hóa có ranh giới rõ ràng.

**Câu 4.** Nếu một chuỗi dài `L` ký tự và hàm băm phải đọc từng ký tự, một lần tìm trong bảng có kỳ vọng một lần thăm dò có nhất thiết là `O(1)` tổng thời gian không?

**Đáp án:** Không. Riêng tính hash từ đầu đã là `O(L)`. Phải cộng chi phí xử lý khóa và so sánh với chi phí thăm dò.

**Câu 5.** Hai chuỗi Unicode nhìn giống nhau nhưng có biểu diễn điểm mã khác nhau. Khi nghiệp vụ coi chúng là cùng khóa, cần làm gì?

**Đáp án:** Quy định một cách chuẩn hóa (ví dụ NFC) và sử dụng nhất quán **trước khi so sánh và trước khi băm**; không chỉ thay đổi một trong hai.

**Câu 6.** Khóa gồm `r` chuỗi với tổng độ dài `L`, băm từ đầu từng thành phần và trộn hash của chúng thường tốn bao nhiêu thời gian?

**Đáp án:** Thông thường `O(r+L)`, với giả định mỗi ký tự và phép trộn có chi phí hằng số. Nếu các mã băm thành phần đã được lưu an toàn, chi phí có thể khác; vẫn phải xét so sánh khóa khi va chạm.

**Câu 7.** Vì sao không nên lưu giá trị `hash("ma-sinh-vien")` của Python làm mã nhận dạng bền vững?

**Đáp án:** Hash của chuỗi có thể phụ thuộc seed và thay đổi giữa các tiến trình hoặc môi trường. Nó phục vụ cấu trúc tra cứu trong runtime, không phải giao thức định danh lâu dài.

**Ghi nhớ:** Băm chuỗi thường phải duyệt nội dung ký tự hoặc byte; khóa tổ hợp cần giữ **thứ tự, kiểu và ranh giới thành phần**. Hash chỉ hỗ trợ định vị, không thay thế phép so sánh bằng nhau. Khi phân tích bảng băm, cần tách **chi phí tạo mã băm `O(L)` đối với chuỗi dài**, số lần thăm dò và chi phí so sánh khóa, rồi mới kết luận về thời gian kỳ vọng của thao tác.

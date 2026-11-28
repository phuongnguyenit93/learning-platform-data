# Bloom filter và kiểm tra một phần tử có thể đã tồn tại

Trong hệ thống chứa hàng triệu khóa — ID người dùng, mã sự kiện, đường dẫn tài nguyên, khóa cơ sở dữ liệu — câu hỏi **“X đã từng xuất hiện chưa?”** được đặt ra liên tục. Một tập hợp chính xác (*set*) có thể trả lời dứt khoát, nhưng phải lưu đủ thông tin để phân biệt từng khóa. Khi bộ nhớ đắt hoặc phần lớn truy vấn tìm khóa **không tồn tại**, ta có thể dùng một bộ lọc nhỏ để loại nhanh những trường hợp chắc chắn vắng mặt.

**Bloom filter** là cấu trúc xác suất kiểm tra **membership** (*một phần tử có thể thuộc tập hay không*). Hai kết quả của nó có ý nghĩa **không đối xứng**:

- **False — chắc chắn chưa được thêm:** Trong mô hình chỉ-thêm hợp lệ, có thể kết luận khóa không thuộc tập đã insert vào bộ lọc.
- **True — có thể đã được thêm:** Khóa thực sự có thể tồn tại, **hoặc** đây là **dương tính giả** (*false positive*) do các khóa khác đã bật đủ vị trí băm.

Bloom filter **không phải set chính xác được nén lại**: nó không lưu đầy đủ tên khóa, không liệt kê được tập đã thêm và không hỗ trợ xóa riêng từng khóa an toàn theo cách thông thường. Đổi lại, nó chỉ cần một mảng bit nhỏ và rất phù hợp làm **bộ lọc trước nguồn dữ liệu chính xác**.

Bài thuộc chương **Cấu trúc xác suất** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo định hướng học cấu trúc dữ liệu qua bất biến, thao tác và độ phức tạp thời gian/bộ nhớ để lựa chọn cấu trúc phù hợp, bài đi sâu vào **Bloom filter và cách diễn giải “có thể đã tồn tại”**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **set chính xác** và Bloom filter trong truy vấn membership.
2. Hiểu **true positive, false positive, true negative, false negative**, và chiều sai số mà Bloom filter chuẩn cho phép.
3. Mô tả mảng **m bit**, **h vị trí băm** của mỗi khóa và thao tác add/might_contain.
4. Truy vết việc bật bit và tạo **dương tính giả** khi những khóa khác nhau chia sẻ các vị trí băm.
5. Chứng minh bằng bất biến vì sao Bloom filter **chỉ thêm, không mất cập nhật** không có **âm tính giả** đối với các khóa đã thêm.
6. Đọc và áp dụng công thức FPR theo m, h, n; chọn tham số theo mục tiêu bộ nhớ/sai số.
7. Cài đặt Bloom filter Python tự chứa với cách mã hóa/băm tái lập; tính đúng đơn vị bit/byte.
8. Thiết kế tra cứu hai bước **Bloom → nguồn chính xác**, biết khi nào kết quả False không còn đáng tin do thiếu đồng bộ.
9. Giải thích giới hạn về **xóa, mở rộng dung lượng, hợp nhất, serialization, đổi seed, Unicode, đồng thời**.
10. Phân tích thời gian O(h), bộ nhớ O(m) bit trong mô hình cố định, và chi phí thực tế khi băm khóa dài.
11. Phân biệt **FPR của các truy vấn thật sự âm tính** với tỷ lệ trả lời sai trong nhóm câu trả lời **True**.
12. Chọn Bloom filter hoặc set/DB/counting Bloom filter theo yêu cầu xóa, xác minh chính xác, quy mô và an toàn.

## 2. Bài toán membership: lưu từng khóa hay lưu dấu vết?

Giả sử dịch vụ đã ghi nhận ID các sự kiện:

~~~text
ID "evt-129" đã được ghi nhận chưa?
ID "evt-792" đã được ghi nhận chưa?
ID "evt-993" đã được ghi nhận chưa?
~~~

Giải pháp chính xác thường gặp:

~~~python
seen = {"evt-129", "evt-437", "evt-792"}

assert "evt-129" in seen
assert "evt-993" not in seen
~~~

Set có thể trả membership nhanh trung bình nhờ bảng băm, nhưng vẫn phải giữ đủ thông tin cho **từng khóa phân biệt**. Khi số khóa tăng, bộ nhớ và chi phí duy trì của set cũng tăng.

Bloom filter chỉ giữ **mảng bit đại diện cho dấu vết băm**:

~~~text
Set chính xác:
{"evt-129", "evt-437", "evt-792", ...}

Bloom filter:
010110101001010001... (m bit)
~~~

Một kiến trúc phổ biến:

~~~text
Nhận yêu cầu với khóa X
            |
            v
 Bloom.might_contain(X)?
       /          \
     False        True
       |            |
  Loại nhanh   Truy vấn DB / set
  trường hợp   có thẩm quyền
  chắc chắn    để xác nhận
  vắng mặt     tồn tại thật
~~~

Nếu cần câu trả lời cuối **chính xác**, kết quả True từ Bloom **không đủ làm bằng chứng tồn tại**; nó chỉ cho biết “có thể có”. Bloom có ích khi đọc nhiều, tỷ lệ khóa vắng mặt lớn và việc tra cứu nguồn chính xác tương đối đắt.

**Không dùng Bloom True làm căn cứ duy nhất** để cấp quyền, xác nhận thanh toán, xóa dữ liệu hoặc kết luận một bệnh nhân đã được điều trị: dương tính giả có thể gây hậu quả nghiêm trọng.

### 2.1. Bốn loại kết quả

| Sự thật | Trả True / “có thể có” | Trả False / “không có” |
| --- | --- | --- |
| Khóa thật đã thêm | **True positive (TP)** | **False negative (FN)** |
| Khóa thật chưa thêm | **False positive (FP)** | **True negative (TN)** |

Với **Bloom filter insert-only chuẩn, đúng trạng thái**:

- **FN = 0** đối với những khóa đã add thành công.
- **FP có thể > 0** đối với khóa chưa thêm.
- Trả True là **khẳng định yếu**; trả False là **khẳng định mạnh**.

Bảo đảm FN = 0 chỉ áp dụng cho **tập khóa đã thực sự được add vào Bloom**. Nếu database có khóa nhưng cập nhật Bloom bị bỏ lỡ, đó là **lỗi đồng bộ hệ thống**, không phải ví dụ Bloom cho phép sai âm tính trong mô hình chuẩn.

## 3. Cấu tạo: mảng bit và nhiều vị trí băm

Bloom filter có:

- **m**: Số bit trong mảng, khởi tạo toàn **0**.
- **h**: Số vị trí băm cho mỗi khóa, h ≥ 1.
- Các phép ánh xạ **H₀, H₁, ..., H_(h−1)**, đưa khóa vào các vị trí từ 0 tới m−1.

Với khóa x:

\[
H_i(x)\in\{0,1,\ldots,m-1\},\quad i=0,\ldots,h-1.
\]

Trong ví dụ thủ công, ta **cho trước các vị trí băm**, không cần tính hash cụ thể.

### 3.1. Add: bật bit, không tăng bộ đếm

~~~text
ADD(x):
    với từng vị trí j trong H0(x), H1(x), ..., H(h-1)(x):
        bits[j] = 1
~~~

Ví dụ m=12, h=3, A có vị trí {1,4,10}:

~~~text
Vị trí:  0 1 2 3 4 5 6 7 8 9 10 11
Ban đầu: 0 0 0 0 0 0 0 0 0 0  0  0

Sau ADD(A):
         0 1 0 0 1 0 0 0 0 0  1  0
~~~

Thêm B có vị trí {4,7,10}:

~~~text
Sau ADD(A), ADD(B):
         0 1 0 0 1 0 0 1 0 0  1  0
~~~

A và B cùng sử dụng bit **4,10**. Bloom **không nhớ** bit nào do A hay B bật; bit 1 chỉ thể hiện **đã từng có ít nhất một lần đặt**.

### 3.2. Query: phải kiểm tra toàn bộ h vị trí

~~~text
MIGHT_CONTAIN(x):
    với từng vị trí j trong H0(x), ..., H(h-1)(x):
        nếu bits[j] == 0:
            trả False       # Chắc chắn chưa add.
    trả True                # Có thể đã add.
~~~

Trong trạng thái sau A và B:

~~~text
H(C) = {0,4,7}
bit[0] = 0
=> MIGHT_CONTAIN(C) = False

H(D) = {1,7,10}
Cả ba bit đều bằng 1
=> MIGHT_CONTAIN(D) = True
~~~

Giả sử D **chưa từng được thêm**. Trả True cho D là một **false positive**, không phải lỗi thuật toán: các khóa khác đã bật đủ ba vị trí.

### 3.3. Hai cách hiểu sai

**Sai lầm 1:** “Tất cả h bit bằng 1 chứng minh khóa tồn tại.” Không đúng, vì có thể là tổ hợp bit từ khóa khác.

**Sai lầm 2:** “Chỉ cần một bit 1 thì trả True.” Không đúng; Bloom chuẩn cần **tất cả h vị trí đều 1**. Chỉ **một bit 0** đã đủ để loại khóa.

### 3.4. Add trùng khóa

Add cùng x nhiều lần sẽ bật chính các vị trí như lần đầu:

~~~text
ADD(A), ADD(A), ADD(A)

Trạng thái bit sau lần thứ ba bằng sau lần thứ nhất
nếu không có khóa khác được thêm ở giữa.
~~~

+

## 4. Bất biến và chứng minh không có âm tính giả

**Bất biến đơn điệu:** Trong Bloom filter chỉ-thêm, mọi bit chỉ chuyển từ **0 thành 1** hoặc giữ nguyên. Không có thao tác đổi bit 1 thành 0.

Gọi B_t[j] là bit ở vị trí j sau t lần add. Khi đó:

\[
B_{t+1}[j]\ge B_t[j],\qquad B_t[j]\in\{0,1\}.
\]

Giả sử khóa x đã được thêm thành công ở thời điểm t. Theo định nghĩa add:

\[
B_t[H_i(x)]=1\quad\text{với mọi }i=0,\ldots,h-1.
\]

Vì trạng thái bit chỉ tăng, **mọi bit của x vẫn bằng 1 ở mọi thời điểm về sau**. Do đó:

\[
x\in S_{\mathrm{inserted}}
\Longrightarrow \mathrm{mightContain}(x)=\mathrm{True}.
\]

Lấy phản đảo:

\[
\mathrm{mightContain}(x)=\mathrm{False}
\Longrightarrow x\notin S_{\mathrm{inserted}}.
\]

Đây là **bảo đảm không âm tính giả**, không phải bảo đảm theo xác suất 99%. Nó đúng cho các khóa **đã thêm thành công**, ngay cả nếu số lượng false positive rất cao.

### 4.1. Các điều kiện phải giữ

1. **Add đã hoàn tất** trước khi query được coi là nhìn thấy khóa.
2. Không có cập nhật bit bị mất do hai luồng ghi đè nhau.
3. Add và query dùng **cùng m, h, hash, seed, encoding và chuẩn hóa khóa**.
4. Bit của khóa đã thêm không bị tắt, bị xóa sau khi restart hoặc khôi phục từ snapshot cũ.
5. Nội dung mảng bit không bị hỏng.
6. Nếu dùng bộ lọc trước database, tập khóa được biểu diễn phải **bao phủ** tập khóa thực có tại thời điểm được phép loại bằng False.

Nếu một điều kiện bị vi phạm, sai âm tính có thể xuất hiện **ở cấp hệ thống**, dù chứng minh trên mô hình Bloom đơn điệu vẫn đúng.

### 4.2. Đừng suy diễn sai phía còn lại

Từ \(x\in S\Rightarrow\mathrm{mightContain}(x)\), **không được** đảo thành \(\mathrm{mightContain}(x)\Rightarrow x\in S\). Đây là lỗi suy luận đảo mệnh đề: các bit có thể được bật bởi nhiều khóa khác.

Ngược lại, mệnh đề phản đảo **False ⇒ không có** là hợp lệ theo những điều kiện trên.

### 4.3. Bất biến membership không là chứng chỉ bảo mật

Một đối thủ có thể thử nhiều khóa cho tới khi tìm được một dương tính giả. Với bộ lọc và hash cố định, cùng một khóa chưa thêm thường cho **cùng kết quả True/False**, không có “tung đồng xu mới” ở mỗi lần hỏi.

Không được dùng Bloom True như **bằng chứng người dùng có quyền truy cập**, hoặc như bằng chứng khóa đã được ghi nhận trong một giao dịch quan trọng.

## 5. False positive: xác suất, mẫu số và công thức

Tỷ lệ false positive (*false positive rate*, FPR) là xác suất Bloom trả True **cho một khóa thực sự chưa thêm**, theo mô hình phân bố hash/khóa truy vấn:

\[
\mathrm{FPR}=\frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}
\]

khi đo trên các truy vấn được gắn nhãn sự thật.

Mẫu số chỉ tính những truy vấn **thực sự âm tính**, không bao gồm true positive.

### 5.1. Xác suất một bit vẫn là 0

Giả sử:

- Mảng có m bit.
- Đã thêm n khóa phân biệt.
- Mỗi khóa chọn h vị trí.
- Các vị trí được phân bố đều và đủ độc lập trong mô hình gần lý tưởng.

Xác suất một lần chọn vị trí không trúng một bit cố định:

\[
1-\frac{1}{m}.
\]

Sau hn lần đặt vị trí, xác suất bit ấy vẫn bằng 0:

\[
P(B[j]=0)=\left(1-\frac{1}{m}\right)^{hn}
\approx e^{-hn/m}.
\]

Suy ra xác suất bit bằng 1:

\[
q=P(B[j]=1)\approx 1-e^{-hn/m}.
\]

### 5.2. Xác suất cả h vị trí đã bật

Một khóa chưa từng thêm bị false positive khi **cả h vị trí băm tương ứng đều bằng 1**. Theo xấp xỉ độc lập:

\[
\boxed{p_{\mathrm{FP}}\approx\left(1-e^{-hn/m}\right)^h}.
\]

Đây là **xấp xỉ theo mô hình**, không phải định luật bảo đảm đúng với mọi hash tự viết, mọi dữ liệu và mọi truy vấn đối thủ chọn. Trong Bloom filter thực, chất lượng hash, số khóa và phân bố truy vấn ảnh hưởng tỷ lệ đo được.

Một khóa chưa thêm có thể bị false positive **liên tiếp**: nếu trạng thái filter không đổi, query cùng khóa thường trả lại kết quả cũ. Không được giả định các lời gọi lặp độc lập từng lần.

### 5.3. n tăng làm tỷ lệ false positive tăng

Khi m và h cố định, thêm nhiều khóa phân biệt hơn làm nhiều bit được bật. Gần như toàn bit 1 thì gần như **mọi khóa lạ cũng trả True**.

~~~text
Mới tạo:       0000000000000000
Sau ít khóa:   0101000001100010
Sau nhiều:     1111010111111011
Bão hòa:       1111111111111111
~~~

Khi bão hòa, Bloom vẫn không âm tính giả đối với khóa đã thêm, nhưng đã **mất giá trị lọc**.

### 5.4. False positive không giống tỷ lệ “True nhưng sai”

Giả sử trong 100.000 truy vấn:

- 10% hỏi khóa **thực sự có**: 10.000.
- 90% hỏi khóa **thực sự không có**: 90.000.
- FPR trên truy vấn âm tính là khoảng 1%.

Số câu trả lời True kỳ vọng:

~~~text
True positive:       10 000
False positive:         900   (1% của 90 000)
-----------------------------------------------
Tổng True:           10 900

Trong các trả lời True, tỷ lệ sai:
900 / 10 900 ≈ 8,26%
~~~

**FPR 1% không có nghĩa chỉ 1% câu trả lời True là sai.** Tỷ lệ sai trong nhóm True còn phụ thuộc **tỷ lệ khóa thực sự tồn tại** (*base rate*). Bởi vậy cần phân biệt **FPR** và **precision/positive predictive value**.

### 5.5. Cần phân biệt số lần add và số khóa phân biệt

Nếu add một khóa 100 lần, các vị trí bit của nó giống nhau; về mặt tập hợp, việc lặp lại không làm xuất hiện 100 khóa mới. Tham số n trong công thức thiết kế thông thường là **số khóa phân biệt dự kiến**, không đơn thuần là số lượt gọi add.

## 6. Chọn m và h theo dung lượng và độ chính xác

Với m, n cố định, số vị trí băm gần tối ưu theo mô hình lý tưởng là:

\[
\boxed{h_{\mathrm{opt}}\approx\frac{m}{n}\ln2}.
\]

Trong chương trình, h phải là **số nguyên dương**, nên chọn số nguyên gần giá trị ấy. Nếu h quá nhỏ, mỗi query kiểm tra quá ít bit; nếu h quá lớn, mảng bit bão hòa nhanh và CPU tăng.

Để thiết kế cho n khóa phân biệt và FPR mục tiêu p:

\[
\boxed{m\approx-\frac{n\ln p}{(\ln2)^2}}.
\]

Số bit trên mỗi khóa:

\[
\frac{m}{n}\approx-\frac{\ln p}{(\ln2)^2}.
\]

**Ví dụ:** Dự kiến n = 1.000.000 khóa, FPR mục tiêu p = 0,01:

~~~text
m ≈ 9 585 059 bit
  ≈ 1 198 133 byte
  ≈ 1,14 MiB mảng bit

h ≈ (m/n) ln2 ≈ 6,64 → chọn 7 vị trí
~~~

Các con số **chỉ cho vùng mảng bit**; bộ lọc thật còn có metadata, code hash, vùng nhớ đối tượng và bộ đệm.

### 6.1. Bảng tham số tham khảo

Với **một triệu khóa phân biệt**:

| FPR mục tiêu p | Bit trên khóa (xấp xỉ) | Tổng bit (xấp xỉ) | Vùng mảng bit | h gần tối ưu |
| --- | ---: | ---: | ---: | ---: |
| 10% | 4,79 | 4,79 triệu | 0,57 MiB | 3 |
| 1% | 9,59 | 9,59 triệu | 1,14 MiB | 7 |
| 0,1% | 14,38 | 14,38 triệu | 1,71 MiB | 10 |
| 0,01% | 19,17 | 19,17 triệu | 2,29 MiB | 13 |

Giảm FPR mục tiêu mười lần cần **thêm bit** và thường **thêm phép băm trên mỗi add/query**. Bloom filter không tự tăng dung lượng khi vượt n; nếu m và h giữ nguyên, chất lượng lọc giảm khi số khóa phân biệt tăng.

### 6.2. Khi nào tăng h lại làm tình hình xấu đi?

Số vị trí h lớn có hai tác động trái chiều:

1. Một khóa lạ phải có **nhiều bit 1 hơn** mới bị false positive.
2. Nhưng **mỗi khóa thêm cũng bật nhiều bit hơn**, làm bit bão hòa nhanh hơn.

Vì thế **h có điểm tối ưu**. Đặt h = 100 trên một mảng quá nhỏ thường vừa tốn CPU, vừa không giúp đúng hơn.

### 6.3. Chi phí băm không phải miễn phí

Với khóa có độ dài L byte, nếu mã băm toàn bộ khóa **h lần**, chi phí có thể là **O(hL)**, chứ không chỉ O(h). Các cách thực thi tạo nhiều vị trí từ một vài hash cơ sở có thể giảm CPU, nhưng cần phân tích chất lượng phân bố và tính tương thích theo thuật toán đã chọn.

Trên workload nhỏ và database cache tốt, tính nhiều hash đôi khi **chậm hơn** tra cứu nguồn trực tiếp. Quyết định tối ưu cần đo **độ trễ đầu-cuối**, không chỉ số bit.

### 6.4. FPR mục tiêu không tự là bảo đảm mọi truy vấn

Ngay cả khi công thức cho p = 1%, một tập truy vấn có nhiều khóa tương quan hoặc do đối thủ chọn có thể có tỷ lệ false positive khác. Để đánh giá thực tế, cần truy vấn thử **những khóa được biết chắc là chưa thêm**, có phân bố phản ánh workload, và đo FPR trên đúng tập ấy.


## 7. Cài đặt Python tự chứa: Bloom filter bằng bytearray

Ví dụ dùng Python 3.10 trở lên, không phụ thuộc thư viện ngoài. Mã chỉ nhận **khóa kiểu str** để hợp đồng mã hóa nhất quán; nó dùng **UTF-8**, **SHA-256** với tiền tố định danh phiên bản và chỉ số hash, rồi ánh xạ kết quả về khoảng [0,m).

Đây là **mã minh họa giáo dục**, không phải một thư viện sản xuất đã được đánh giá về chống tấn công hay họ hash độc lập. Việc tính h kết quả từ các lời gọi SHA-256 có tiền tố khác nhau không tự chứng minh rằng mọi giả định xác suất độc lập của công thức lý tưởng được thỏa đúng tuyệt đối.

~~~python
from __future__ import annotations

import hashlib
import math


class BloomFilter:
    """Bloom filter chỉ-thêm cho khóa str.

    False: khóa chắc chắn không nằm trong tập đã add thành công.
    True: khóa có thể đã được add (có thể dương tính giả).
    """

    def __init__(self, expected_items: int, false_positive_rate: float):
        if (
            isinstance(expected_items, bool)
            or not isinstance(expected_items, int)
            or expected_items <= 0
        ):
            raise ValueError("expected_items phải là số nguyên dương")
        if not (0.0 < false_positive_rate < 1.0):
            raise ValueError("false_positive_rate phải thuộc (0, 1)")

        self.expected_items = expected_items
        self.target_fp = false_positive_rate

        ln2 = math.log(2.0)
        self.m = max(
            1,
            math.ceil(
                -expected_items * math.log(false_positive_rate)
                / (ln2 * ln2)
            ),
        )
        self.h = max(1, round(self.m * ln2 / expected_items))

        # Ceil(m/8) byte, bit có chỉ số 0 đến m-1.
        self.bits = bytearray((self.m + 7) // 8)

    def _positions(self, key: str):
        if not isinstance(key, str):
            raise TypeError("Ví dụ chỉ chấp nhận khóa str")

        encoded = key.encode("utf-8")

        for i in range(self.h):
            digest = hashlib.sha256(
                b"bloom-lesson-v1|"
                + i.to_bytes(8, byteorder="big")
                + b"|"
                + encoded
            ).digest()
            yield int.from_bytes(digest, "big") % self.m

    def add(self, key: str) -> None:
        """Bật các bit tương ứng; không có thao tác xóa."""
        for pos in self._positions(key):
            byte_index = pos // 8
            bit_mask = 1 << (pos % 8)
            self.bits[byte_index] |= bit_mask

    def might_contain(self, key: str) -> bool:
        """Không tìm thấy một bit 0 => có thể đã tồn tại."""
        for pos in self._positions(key):
            byte_index = pos // 8
            bit_mask = 1 << (pos % 8)
            if (self.bits[byte_index] & bit_mask) == 0:
                return False

        return True

    def set_bits(self) -> int:
        """Đếm số bit được bật để quan sát mức bão hòa."""
        return sum(byte.bit_count() for byte in self.bits)


# Bộ lọc cho khoảng 1000 khóa phân biệt, FPR mục tiêu 1%.
bf = BloomFilter(1000, 0.01)
known = [f"item-{i}" for i in range(1000)]

# Tất cả khóa sau khi add phải trả True.
for key in known:
    bf.add(key)

assert len(bf.bits) == (bf.m + 7) // 8
assert bf.h >= 1
assert all(bf.might_contain(key) for key in known)

# Một khóa lạ có thể trả False HOẶC True.
answer = bf.might_contain("a-key-never-inserted")
assert isinstance(answer, bool)

# Add trùng khóa không tắt hoặc bật thêm bit mới.
before = bytes(bf.bits)
bf.add("item-5")
assert bytes(bf.bits) == before

# Một bộ lọc mới không có bit 1, mọi khóa chưa thêm trả False.
empty = BloomFilter(10, 0.05)
assert empty.set_bits() == 0
assert not empty.might_contain("anything")

# Lỗi cấu hình được từ chối.
try:
    BloomFilter(0, 0.01)
except ValueError:
    pass
else:
    raise AssertionError("Số khóa dự kiến phải dương")

try:
    BloomFilter(10, 1.0)
except ValueError:
    pass
else:
    raise AssertionError("FPR mục tiêu phải nhỏ hơn 1")
~~~

### 7.1. Cách chuyển chỉ số bit thành byte và mặt nạ

Với vị trí bit j:

~~~text
byte_index = j // 8
bit_index  = j % 8
bit_mask   = 1 << bit_index
~~~

Thao tác bật bit:

~~~python
bits[byte_index] |= bit_mask
~~~

Thao tác kiểm tra:

~~~python
(bits[byte_index] & bit_mask) != 0
~~~

Nếu m không chia hết cho 8, byte cuối có những bit **không thuộc khoảng [0,m)**. Các hàm _positions không bao giờ trả chỉ số nằm ngoài khoảng ấy. Do đó dung lượng dùng là **ceil(m/8) byte**, không phải m byte.

### 7.2. Vì sao không dựa vào hash() mặc định của Python?

Python có thể thay đổi cách khởi tạo hash của một số kiểu như str qua các process. Nếu ghi mảng bit ra đĩa rồi khởi động lại với hash khác, vị trí của cùng khóa có thể thay đổi, khiến **query trả False cho khóa từng add**.

Ví dụ dùng SHA-256 với **tiền tố/version xác định** để các lần khởi động nhận cùng vị trí. Dù thế, hệ thống sản xuất còn cần lưu rõ **kiểu encoding, normalization, m, h, hash version và seed/secret nếu có**.

### 7.3. Thời gian và bộ nhớ của mã

Với m bit, h phép băm và độ dài khóa L byte:

| Công việc | Thời gian | Bộ nhớ |
| --- | --- | --- |
| Khởi tạo m bit | Θ(m) theo đơn vị bit/byte cấp phát | Θ(m) bit |
| add | O(h) nếu coi hash một khóa là O(1) | O(1) ngoài digest/encoding tạm |
| might_contain | O(h) trường hợp xấu nhất | O(1) ngoài digest/encoding tạm |
| add/query với mã hash toàn khóa h lần | O(hL) với L-byte key | Dữ liệu băm tạm O(L) |
| Đếm bit bật của cả mảng | O(m) theo đơn vị byte/từ | O(1) phụ |

Bytearray trong Python vẫn có overhead object; mỗi digest SHA-256 tạm cũng cần vùng nhớ. Tính toán O(h) là mô hình thường dùng khi **phép hash khóa coi như hằng số**.

### 7.4. Kiểm tra bằng assertion có giới hạn gì?

Các assertion cho **khóa đã add** kiểm tra đúng tính không âm tính giả theo hợp đồng. Không có assertion kiểu:

~~~text
Mọi khóa chưa thêm đều phải trả False.
~~~

Vì đó sẽ bác bỏ chính định nghĩa Bloom filter. Muốn đo FPR, cần một tập khóa thử **chắc chắn không nằm trong known**, tính số lần trả True và chia cho tổng số khóa thật sự âm tính.

## 8. Dùng Bloom filter để giảm truy vấn database

### 8.1. Quy trình hai tầng

~~~text
Client hỏi khóa X có tồn tại?
             |
             v
       Bloom filter
             |
        +----+----+
        |         |
      False      True
        |         |
   Trả không   Query database
   tồn tại*    chính xác
                  |
               Trả kết quả

*Chỉ khi Bloom bao phủ đầy đủ khóa của database
 và cập nhật đã đồng bộ trong phạm vi đọc được phép.
~~~

Thay vì buộc mọi request chạm database:

- Trường hợp **True positive** vẫn được tra chính xác.
- Trường hợp **False positive** cũng phải tra chính xác, gây thêm tải nhưng **không gây kết luận sai cuối cùng**.
- Trường hợp **True negative** được trả nhanh, tiết kiệm truy vấn đắt tiền.

### 8.2. Mã minh họa xác minh chính xác

Đoạn mã dưới đây dùng lớp **BloomFilter** đã định nghĩa ở mục 7; hãy thực thi định nghĩa lớp đó trước khi chạy ví dụ này.

Mô hình sau sử dụng một **set làm nguồn sự thật** và khởi tạo Bloom từ **ảnh chụp nhất quán** của set. Trong mô hình này, nguồn chính xác **không được sửa độc lập** sau khi Bloom đã được xây.

~~~python
from collections.abc import Iterable


class ExactMembershipWithBloom:
    def __init__(self, keys: Iterable[str], target_fp: float):
        # Chụp đủ bộ khóa chính xác trước khi tạo bộ lọc.
        self.exact = set(keys)

        self.filter = BloomFilter(
            expected_items=max(1, len(self.exact)),
            false_positive_rate=target_fp,
        )

        for key in self.exact:
            self.filter.add(key)

        self.exact_lookups = 0

    def contains(self, key: str) -> bool:
        if not self.filter.might_contain(key):
            # Chắc chắn không có trong snapshot nhất quán.
            return False

        # Có thể có => xác minh lại bằng nguồn chính xác.
        self.exact_lookups += 1
        return key in self.exact


index = ExactMembershipWithBloom(
    ["apple", "banana", "carrot"],
    target_fp=0.01,
)

assert index.contains("apple")
assert not index.contains("something-never-added")
assert not index.contains("pear")

# Những khóa đã có luôn được trả đúng.
assert all(index.contains(k) for k in index.exact)
~~~

Dù khóa “pear” vô tình gây false positive tại Bloom, hàm contains vẫn trả False sau khi kiểm tra set. **Kết quả cuối cùng luôn chính xác** trong phạm vi snapshot đồng bộ, chỉ có số lần tra set khác nhau.

### 8.3. Khi cập nhật database diễn ra song song

Nếu có thao tác:

~~~text
T1: database INSERT(X) thành công
T2: client QUERY(X)
T3: Bloom ADD(X) thành công
~~~

Client tại T2 có thể nhận **Bloom False**, mặc dù X **đã tồn tại trong database**. Đây là **false negative so với nguồn dữ liệu thật**, do filter chưa phản ánh bản ghi mới.

Một thiết kế an toàn phải quy định rõ **thứ tự hiển thị cập nhật và truy vấn**, chẳng hạn:

- Xuất bản Bloom **sau khi xây đầy đủ từ snapshot**, đồng thời định nghĩa phạm vi snapshot mà nó bảo vệ.
- Đưa các khóa mới vào **lớp delta/overlay** được đọc cùng Bloom và cập nhật nhất quán với transaction.
- Hoặc **không dùng Bloom False để loại** đối với các bản ghi nằm ngoài phạm vi bộ lọc đã cập nhật.

Chỉ “thêm vào Bloom trước database” cũng không tự giải quyết **mọi** trường hợp race, rollback, replica lag và khả năng nhìn thấy của giao dịch. Với hệ thống thực, phải thiết kế một **giao thức nhất quán**.

### 8.4. Lợi ích phụ thuộc base rate và chi phí truy vấn

Nếu 1 triệu request gồm 10% khóa thật có và 90% khóa thật không có, Bloom có FPR 1%:

~~~text
Không dùng Bloom:
  1 000 000 lượt tra database.

Có Bloom trên snapshot nhất quán:
  100 000 truy vấn thật có       → vẫn tra database.
    9 000 false positive        → vẫn tra database.
  891 000 true negative         → không tra database.

Tra database kỳ vọng ≈ 109 000 lượt
so với 1 000 000 lượt trước đó.
~~~

Tỷ lệ giảm lượt tra cứu không đồng nghĩa cùng tỷ lệ giảm **độ trễ tổng thể**: mỗi request còn phải hash h lần và đọc mảng bit. Nếu database lookup vốn rẻ hoặc tỷ lệ truy vấn có thật rất cao, bộ lọc có thể không đáng với CPU/bộ nhớ.

## 9. Xóa khóa: tại sao Bloom chuẩn không thể tắt bit?

Sau khi add A và B, giả sử cả hai dùng bit 4:

~~~text
A → {1,4,10}
B → {4,7,10}

Bloom sau add:
bit[1], bit[4], bit[7], bit[10] = 1.
~~~

Nếu muốn xóa A bằng cách đặt **bit[1], bit[4], bit[10] = 0**, bit 4 và 10 cũng là bằng chứng duy nhất cho một số vị trí băm của B. Query B có thể nhìn thấy bit 0 và trả **False**, tạo **âm tính giả** cho khóa B vẫn còn.

**Bloom filter bit chuẩn không hỗ trợ xóa riêng từng khóa** bằng cách xóa bit tùy ý. Tập bit chỉ mang thông tin “đã từng được bật”, không mang thông tin **ai bật** và **bao nhiêu khóa cần bit ấy**.

### 9.1. Counting Bloom filter

Một biến thể thay mỗi bit bằng **bộ đếm**:

- add(x): tăng những bộ đếm ở các vị trí băm x.
- delete(x): giảm những bộ đếm tương ứng.
- query(x): tất cả bộ đếm phải **lớn hơn 0**.

Điều kiện để xóa đúng:

1. Biết khóa x **thật sự đã được add**, không chỉ biết Bloom trả True.
2. Không xóa quá số lần thêm của khóa đó, có quy tắc riêng khi cùng khóa xuất hiện nhiều lần.
3. Bộ đếm đủ độ rộng, không bị **overflow/saturation** âm thầm.
4. Thao tác tăng/giảm được đồng bộ chính xác khi nhiều luồng ghi.

Nếu xóa một **khóa chưa hề add** chỉ vì một câu trả lời false positive, có thể làm giảm bộ đếm dùng chung của những khóa thật và tạo âm tính giả. Counting Bloom dùng **nhiều bit hơn** cho mỗi vị trí và cần quản lý trạng thái xóa.

### 9.2. Không cần xóa? Có thể xây lại theo vòng đời

Nếu tập dữ liệu có version hoặc được chia theo **ngày/giờ**, có thể xây bộ lọc cho từng phân vùng bất biến rồi **bỏ cả phân vùng** khi hết hạn. Với các tập thay đổi theo lô, xây lại một Bloom mới từ tập khóa chính xác thường đơn giản và an toàn hơn việc phát minh cơ chế xóa bit.

Không nên thay đổi một Bloom bit chuẩn thành “bộ lọc cửa sổ trượt” bằng việc tự đặt một số bit về 0 mà vẫn tuyên bố không âm tính giả.


## 10. Khi bộ lọc lớn dần, đầy bit hoặc cần hợp nhất

### 10.1. Bloom có tự mở rộng không?

Bloom filter bit chuẩn được tạo với **m và h cố định**. Việc add thêm khóa không làm mảng bit dài ra: nó chỉ bật nhiều bit cũ hơn.

Nếu bộ lọc thiết kế cho 1 triệu khóa mà thực tế nhận 3 triệu khóa phân biệt, FPR thường tăng rõ rệt so với mục tiêu. Nếu gần hết bit đã bật, bộ lọc trả True cho hầu hết khóa chưa thêm và gần như vô ích.

**Không được tăng m của bộ lọc cũ rồi giữ các bit đã lưu.** Vị trí băm được tính theo modulo m, nên khóa cũ sẽ băm vào chỉ số mới; query có thể gặp bit 0 và trả âm tính sai.

Những lựa chọn đúng hơn:

1. **Xây lại từ nguồn khóa chính xác** với m và h mới, rồi xuất bản version mới một cách nhất quán.
2. Dùng **scalable Bloom filter** gồm nhiều lớp có quy tắc bổ sung khóa và phân bổ ngân sách FPR.
3. Chia khóa theo **phân vùng/tập con hoặc thời gian**; quản lý nhiều Bloom khác nhau và chọn bộ lọc có liên quan.
4. Nếu dữ liệu thường xuyên xóa, cân nhắc **counting Bloom** hoặc cấu trúc khác phù hợp hơn.

### 10.2. Nhiều lớp có thể tăng tổng FPR

Giả sử có hai lớp Bloom, query trả True nếu **bất kỳ lớp nào** trả True.

Nếu khóa thực sự không có trong cả hai lớp, xác suất ít nhất một lớp false positive thỏa cận:

\[
P(\mathrm{FP\ ở\ bất\ kỳ\ lớp})\le p_1+p_2.
\]

Đó là **union bound**, không cần giả định hai sự kiện độc lập. Nếu giả định độc lập thật sự hợp lý, có thể tính:

\[
P(\mathrm{FP})\approx 1-(1-p_1)(1-p_2).
\]

Vì vậy, không thể tạo mười lớp đều có FPR 1% rồi khẳng định tổng hệ thống vẫn 1%. Một thiết kế mở rộng phải **chia ngân sách sai số** giữa các lớp.

### 10.3. Hợp nhất hai Bloom filter

Hai bộ lọc có thể được hợp nhất bằng **OR từng bit**, với điều kiện:

- Cùng m và cùng h.
- Cùng hàm băm, seed, domain separation và version.
- Cùng cách mã hóa/chuẩn hóa khóa.
- Cùng ý nghĩa về membership và thời điểm dữ liệu được bao phủ.

Khi các điều kiện trên đúng, đối với mỗi khóa thuộc một trong hai bộ lọc, mọi bit của khóa ấy đã bật ở ít nhất một bên, nên kết quả OR vẫn **không âm tính giả** cho tập hợp.

~~~text
Bloom_A: 0010010100
Bloom_B: 0100010010
--------------------------------
OR:      0110010110
~~~

Nếu hai bộ lọc dùng **hash khác nhau**, phép OR trên các bit cùng vị trí không cho một cấu trúc membership hợp lệ theo bất kỳ hash nào được xác định rõ. Không được thực hiện phép này chỉ vì mảng bit có độ dài bằng nhau.

### 10.4. FPR sau hợp nhất được tính theo số khóa phân biệt

Nếu A có n_A khóa, B có n_B khóa nhưng có khóa trùng nhau, số khóa phân biệt trong hợp là:

\[
|A\cup B|=|A|+|B|-|A\cap B|.
\]

Bloom filter không tự cung cấp chính xác **|A∩B|**; vì thế không thể luôn tính FPR của bản hợp bằng cách thay n = n_A+n_B mà coi đó là kích thước tập chính xác.

OR giữa các bộ lọc tương thích vẫn bảo toàn chức năng membership một phía, nhưng độ bão hòa và FPR có thể tăng so với mỗi bộ lọc riêng.

### 10.5. Lưu và phục hồi bộ lọc

Một snapshot dùng để khôi phục đúng phải gồm:

~~~text
version dữ liệu / snapshot
m: số bit
h: số vị trí băm
hash_algorithm / hash_version
seed hoặc thông số băm khác
encoding / normalization của khóa
bit_array
checksum / thông tin kiểm tra toàn vẹn nếu có
~~~

Nếu chỉ lưu bytearray và bỏ m, h hoặc cách băm, tiến trình mới có thể hiểu cùng vùng bit theo vị trí khác và trả âm tính sai cho khóa cũ.

**Đồng nhất bit array chưa đủ để đồng nhất bộ lọc.** Phải đồng nhất cả “ngữ nghĩa vị trí băm”.

## 11. Chuẩn hóa khóa, hash và các vấn đề dữ liệu

### 11.1. Cùng ý nghĩa nghiệp vụ phải có cùng bytes

Nếu ứng dụng coi “Alice” và “alice” là cùng người dùng, nhưng add “Alice” rồi query “alice” mà không chuẩn hóa, Bloom sẽ xử lý chúng như **hai chuỗi khác nhau**. Kết quả False cho “alice” không trái với bảo đảm Bloom: khóa **“alice”** thực sự chưa được add.

Cần định nghĩa một hàm **canonicalize** trước mọi add/query, phù hợp quy tắc nghiệp vụ (ví dụ, chuẩn hóa Unicode, trim khoảng trắng nếu hợp đồng cho phép, case-fold trong những miền dữ liệu được xác định).

Không áp dụng việc bỏ khoảng trắng hoặc đổi chữ hoa tùy tiện với mã định danh phân biệt chữ hoa: **chuẩn hóa sai có thể biến hai khóa khác nhau thành một**, tạo nhầm membership ở cấp ứng dụng.

### 11.2. Hash tốt khác với “hash không va chạm”

Bloom chấp nhận các vị trí băm **va chạm**; đó là nguồn thông tin mất đi và false positive. Mục tiêu của hash là **phân bố đều và đủ độc lập** để công thức FPR có ý nghĩa, chứ không phải bảo đảm không bao giờ va chạm.

Hai vị trí từ cùng một khóa thậm chí có thể bằng nhau. Khi đó add vẫn bật đầy đủ các vị trí đã tính, query cũng kiểm tra đúng cùng vị trí nên **không có âm tính giả**, nhưng hiệu quả lọc thực tế có thể khác lý tưởng.

### 11.3. Khóa rất dài và chi phí CPU

Nếu một ID dài hàng nghìn byte, mỗi vị trí băm tính lại từ toàn bộ ID sẽ tốn CPU nhiều hơn một ID 16 byte. Có những kỹ thuật phát sinh nhiều vị trí từ ít giá trị băm cơ sở để giảm chi phí, nhưng phải xem mô hình hash, ràng buộc bảo mật và điều kiện phân bố.

Mã Python trong bài ưu tiên tính dễ hiểu và tính tái lập, **không cố tối ưu h phép băm cho throughput tối đa**.

### 11.4. Đối thủ thích nghi và rủi ro bảo mật

Với filter được công khai như một oracle membership, người tấn công có thể thử nhiều khóa để tìm khóa lạ được trả True. Xác suất một truy vấn ngẫu nhiên bị false positive không phải bảo đảm chống **chuỗi truy vấn có chủ đích**.

Nếu bộ lọc được dùng trên đường xử lý nhạy cảm, cần:

- Không dùng kết quả True như xác thực/ủy quyền.
- Bảo vệ nguồn dữ liệu thật.
- Cân nhắc giới hạn tốc độ truy vấn, cách dùng hash có seed/secret được quản lý và mô hình đe dọa.
- Đo và theo dõi số truy vấn sai dương tính phát sinh trên workload thật.

Một SHA-256 không có seed bí mật **không tự biến Bloom thành công cụ an ninh**.

## 12. Đồng thời, giao dịch và trạng thái đáng tin cậy

### 12.1. Cập nhật bit song song

Khi hai luồng thực hiện:

~~~text
Thread A: đọc byte cũ, bật mask A, ghi lại byte
Thread B: đọc byte cũ, bật mask B, ghi lại byte
~~~

Nếu cả hai cùng đọc trạng thái ban đầu rồi ghi chồng nhau, một bit do luồng khác đặt **có thể bị mất** trong một cách cài đặt read-modify-write không nguyên tử. Khi đó khóa đã add có thể không còn đủ bit 1 và bị âm tính sai.

Cần dùng cơ chế **atomic bitwise OR**, khóa hoặc phân vùng ghi phù hợp; chỉ thấy rằng phép toán logic OR có tính giao hoán **không có nghĩa** mọi phép đọc–sửa–ghi của ngôn ngữ/thư viện đều nguyên tử.

### 12.2. Query đang xảy ra giữa một thao tác add

Nếu add đang bật lần lượt h bit, query đồng thời có thể nhìn thấy **một phần** các bit mới và trả False dù cuối cùng add sẽ thành công.

Một hợp đồng đúng có thể định nghĩa rằng **chỉ các add đã hoàn tất và được công bố** mới phải được quan sát bởi query; hoặc cần đồng bộ snapshot/trạng thái để có tính nhất quán mạnh hơn.

**Không áp đặt kết luận “không âm tính giả với cả thao tác add đang thực hiện dở”** nếu API không có điều kiện nhất quán đó.

### 12.3. Snapshot cũ và cache âm tính

Một filter được xây từ ảnh chụp **S₀** chỉ có thể khẳng định chắc chắn vắng mặt **trong S₀**. Nếu nguồn dữ liệu đã sang phiên bản S₁ có các khóa mới, kết quả False không đủ để khẳng định vắng mặt trong S₁.

Ví dụ:

~~~text
t0: X chưa có; Bloom của snapshot S0 trả False.
t1: X được insert vào DB.
t2: Truy vấn DB ở trạng thái S1 muốn biết X.

Dùng Bloom S0 để loại X tại t2 => sai ứng dụng.
~~~

Có thể chọn một trong các hướng:

- **Bloom per immutable snapshot** và chỉ tra trong chính dữ liệu snapshot ấy.
- Duy trì **delta index** bao phủ các khóa mới, tra cả delta trước khi loại.
- Tái xây và **thay thế nguyên tử** các version của filter sau khi dữ liệu mới đã được phủ đầy đủ.
- Khi không chắc tính đầy đủ, **bỏ qua kết quả Bloom False và tra nguồn thật**.

### 12.4. Rollback, lỗi và mất nguồn cập nhật

Nếu ghi DB thành công nhưng add Bloom thất bại, có thể xảy ra âm tính sai cấp hệ thống. Nếu add Bloom thành công nhưng giao dịch DB rollback, có thể chỉ gây **false positive so với DB**; điều đó làm tăng tải tra cứu nhưng không nhất thiết làm kết luận sai nếu có bước xác minh.

Tuy nhiên, thứ tự cập nhật một mình chưa đủ: vẫn phải xử lý **race giữa đọc và ghi, độ trễ replica, crash recovery, thiếu thông điệp và việc xuất bản version**. Những ràng buộc này thuộc hợp đồng nhất quán của hệ thống, không nằm trong bit array của Bloom.

## 13. Bloom filter thường được áp dụng ở đâu?

### 13.1. Tránh truy cập đĩa không cần thiết trong hệ thống lưu trữ

Một ví dụ tiêu biểu là đường đọc của **LSM-tree** có nhiều **SSTable bất biến**. Với mỗi SSTable, bộ lọc chứa các khóa của chính SSTable đó. Nếu Bloom trả False, hệ thống có thể **bỏ qua việc tìm khóa ở SSTable ấy**; nếu trả True, vẫn phải đọc chỉ mục/khối liên quan để xác nhận.

~~~text
Tra khóa K qua nhiều SSTable:
  SSTable 1 Bloom(K) = False → bỏ qua bảng 1.
  SSTable 2 Bloom(K) = True  → có thể đọc bảng 2 để xác minh.
  SSTable 3 Bloom(K) = False → bỏ qua bảng 3.
~~~

**Lưu ý:** Một Bloom cho SSTable **không quyết định K có trong toàn bộ database**. Khóa có thể nằm ở bảng khác, memtable mới hơn hoặc đã bị đánh dấu xóa; hệ thống lưu trữ phải áp dụng đúng quy tắc version/tombstone của mình.

### 13.2. Lọc truy vấn tới bộ nhớ đệm hoặc dịch vụ từ xa

Nếu phần lớn truy vấn chưa từng được thêm vào tập ID đã ghi nhận, Bloom có thể loại nhanh trước khi phải gửi RPC hoặc truy vấn database. Lợi ích tăng khi **chi phí tra nguồn chính xác đắt** và **tỷ lệ truy vấn âm tính cao**.

### 13.3. Chống xử lý trùng lặp: chỉ làm bước sơ bộ

Đối với một luồng sự kiện, có thể dùng Bloom để nhanh chóng biết event_id **có khả năng đã xử lý**. Nhưng nếu bỏ qua mọi event_id được Bloom trả True mà không xác minh, một **false positive sẽ làm mất sự kiện chưa xử lý**.

Đối với nghiệp vụ “xử lý chính xác một lần”, cần **dedup store chính xác**, giao dịch idempotency hoặc cơ chế bền vững có thẩm quyền. Bloom chỉ dùng để **giảm lượt kiểm tra** chứ không thay thế điều kiện cuối.

### 13.4. Chống truy cập URL trùng trong crawler

Trong một crawler với độ chấp nhận bỏ sót nhất định, Bloom có thể giữ dấu vết những URL từng gặp để tiết kiệm bộ nhớ. Nhưng cần định nghĩa chính sách **canonicalization của URL** và nhận thức rằng false positive có thể khiến một URL mới bị coi là đã biết.

Nếu hệ thống yêu cầu thu thập **đầy đủ mọi URL**, không thể chỉ dùng Bloom True để bỏ qua một URL mà không có kiểm chứng.

### 13.5. Những yêu cầu không thích hợp

Bloom bit chuẩn **không phù hợp** khi cần:

- Liệt kê mọi khóa đã thêm.
- Đếm chính xác số khóa hoặc số lần xuất hiện của mỗi khóa.
- Xóa nhiều khóa tùy ý mà không có nguồn xác minh.
- Membership chính xác với cả hai phía True/False.
- Xác thực quyền và bằng chứng nghiệp vụ.
- Trả về thông tin payload gắn với khóa.

Nếu dữ liệu nhỏ, có thể dùng **set** đơn giản hơn; nếu dữ liệu thay đổi và yêu cầu xóa, cân nhắc **counting Bloom, cuckoo filter** hoặc cấu trúc chính xác, đồng thời đọc rõ hợp đồng và giới hạn của từng biến thể.


## 14. Đánh đổi: Bloom so với những lựa chọn khác

| Tiêu chí | Set/hash table chính xác | Bloom bit chuẩn | Counting Bloom |
| --- | --- | --- | --- |
| Câu hỏi membership | Trả đúng True/False | **False chắc chắn, True có thể** | Tương tự Bloom nếu quản lý update/delete đúng |
| False positive | Không, theo hợp đồng dữ liệu chính xác | Có thể có | Có thể có |
| False negative | Không, với trạng thái đúng | Không trong insert-only hợp lệ | Không nếu counter/cập nhật/xóa đúng mô hình |
| Bộ nhớ | Tăng theo số khóa và bản ghi | **m bit** được cấp phát | m bộ đếm, mỗi bộ đếm nhiều bit |
| Thêm khóa | Hỗ trợ | Bật h bit | Tăng h bộ đếm |
| Xóa khóa | Hỗ trợ | **Không xóa trực tiếp an toàn** | Có điều kiện, biết khóa đã add |
| Liệt kê khóa | Có | **Không** | Không tự có |
| Đếm số lần xuất hiện | Cần dictionary/counter riêng | Không | Các counter vị trí không phải tần suất của từng khóa |
| Hợp nhất tập | Cần hợp các khóa/định nghĩa cụ thể | OR bit khi tương thích | Cộng counter khi tương thích và phù hợp hợp đồng |
| Phù hợp | Tính đúng tuyệt đối, tập đủ nhỏ hoặc lưu trữ được | Lọc âm tính nhanh, footprint nhỏ | Tập biến động có xóa và metadata phù hợp |

**Cuckoo filter** là một lựa chọn membership gần đúng khác, có thể hỗ trợ xóa trong các điều kiện thiết kế, nhưng cũng có rủi ro false positive, giới hạn tải/cấp phát và điều kiện quản lý xóa. Không nên khẳng định nó luôn tốt hơn Bloom trong mọi workload.

**Blocked Bloom filter** tổ chức bit theo các khối để cải thiện tính cục bộ cache cho một số tải công việc, đánh đổi chi tiết phân bố FPR. **Scalable Bloom filter** dùng nhiều lớp để mở rộng quy mô. Mỗi biến thể có bất biến và chi phí khác; bài này tập trung **Bloom chỉ-thêm chuẩn**.

### 14.1. Thời gian O(1) hay O(h)?

Nếu chọn h là một **hằng số cố định khi cấu hình**, add/query có thể được gọi là O(1) theo số khóa n (không phụ thuộc n). Nhưng khi thiết kế để thay đổi **độ chính xác**, h là **tham số quan trọng**: công việc thực sự là O(h) phép băm/đọc bit, và với khóa dài là O(hL).

Vì thế nên công bố cả **cận theo tham số** và **giả định h cố định**. “O(1)” không có nghĩa CPU không thay đổi khi nâng FPR mục tiêu từ 1% xuống 0,01%.

### 14.2. So sánh hiệu quả bộ nhớ một cách công bằng

Đối với mảng bit lý thuyết, 1 triệu khóa với p≈1% cần khoảng **1,14 MiB**. Một set Python lưu 1 triệu chuỗi thường tiêu tốn nhiều hơn vì giữ object khóa và bảng băm, nhưng kết quả chính xác còn tùy độ dài ID, biểu diễn chuỗi, bộ cấp phát và runtime.

Không nên trích một số byte bộ nhớ set chung cho mọi ngôn ngữ và mọi độ dài khóa. Đồng thời, mảng bit Bloom **không tự cung cấp ID hoặc payload**, nên trong nhiều kiến trúc ta vẫn phải có nguồn lưu trữ chính xác ở nơi khác.

### 14.3. Quyết định theo mức độ chính xác cho phép

- Chỉ cần biết **“có thể từng thấy”** và false positive chấp nhận được → Bloom trực tiếp có thể phù hợp.
- Cần trả lời **đúng tồn tại** nhưng tra nguồn đắt → Bloom làm **prefilter**, True phải xác minh.
- Cần xóa hoặc hết hạn thường xuyên → chọn biến thể xóa phù hợp hoặc tổ chức snapshot/phân vùng.
- Cần tìm danh tính, payload hoặc đếm → Bloom không đủ.
- Cần bảo đảm an ninh → không tin câu trả lời True như bằng chứng.

## 15. Thiết kế và kiểm chứng một Bloom filter trong hệ thống thật

### 15.1. Chọn ngân sách sai số

Hãy xác định:

1. **n tối đa dự kiến**: số khóa phân biệt mà một bộ lọc phục vụ trong suốt vòng đời.
2. **FPR mục tiêu p**: đo trên những truy vấn thật sự không tồn tại.
3. **Mức bộ nhớ**: bao nhiêu MiB được dành cho mảng bit và metadata?
4. **CPU**: chấp nhận bao nhiêu lần băm mỗi add/query?
5. **Chi phí lookup nguồn chính xác**: có đáng tránh bằng Bloom không?
6. **Tỷ lệ âm tính của workload**: bao nhiêu truy vấn có thể loại nhanh?
7. **Tính nhất quán cập nhật**: các khóa mới có được bảo đảm add trước khi query False được tin hay không?
8. **Vòng đời**: khi n tăng quá dự kiến, bộ lọc được xây lại như thế nào?

**Ví dụ lựa chọn:** Nếu n=1.000.000 và p=1%, cấp phát khoảng 9,59 triệu bit, h khoảng 7. Nếu tăng quy mô lên 5 triệu khóa nhưng không đổi m, FPR sẽ tăng; giải pháp đúng không phải thay đổi công thức trong báo cáo mà phải **cấp thêm bit/đổi kiến trúc**.

### 15.2. Thống kê độ bão hòa của mảng bit

Đếm số bit 1 trong vùng m bit cho tỷ lệ thực nghiệm:

\[
q_{\mathrm{observed}}=
\frac{\#\mathrm{bit\ đang\ bằng\ 1}}{m}.
\]

Dưới mô hình lý tưởng, có thể so q với:

\[
q_{\mathrm{expected}}\approx 1-e^{-hn/m}.
\]

Độ bão hòa không đủ để **suy ra chính xác n** khi có trùng khóa, hash không đều và các va chạm; nhưng nó là tín hiệu giúp biết **bộ lọc đã quá đầy** hay chưa.

### 15.3. Đo FPR bằng nguồn sự thật

Một cách kiểm định hợp lý:

1. Xây bộ lọc từ tập khóa known, xác định rõ snapshot.
2. Chuẩn bị tập **positive** thật đã thêm và tập **negative** thật chưa thêm.
3. Kiểm tra mọi positive trả True; bất kỳ trường hợp False nào cần điều tra lỗi cập nhật/hash/serialization.
4. Trên negative, tính **số query trả True / tổng negative**.
5. Đối chiếu tỷ lệ đo được với p mục tiêu và các giả định workload.
6. Đo thời gian hash/query, bộ nhớ thực, throughput, và số lượt tra nguồn chính xác thực sự tiết kiệm được.

Không nên kiểm tra FPR bằng một vài khóa lạ rồi tuyên bố “đúng 1%” hoặc bằng cách lặp đúng một khóa lạ hàng nghìn lần: các phép thử ấy **không phải mẫu khóa âm tính độc lập/đại diện** theo phân bố cần đánh giá.

### 15.4. Độ tin cậy khi khởi động lại

Kiểm tra rằng một filter được **lưu rồi khôi phục** với đúng m/h/hash/encoding vẫn trả True cho mọi khóa đã add trước khi lưu. Kiểm tra checksum và version nếu dùng snapshot trong storage lâu dài.

Với cập nhật phân tán, phải biết bộ lọc đại diện **phiên bản dữ liệu nào**. Nếu bản sao bộ lọc bị trễ sau bản sao DB, truy vấn False có thể không đáng tin đối với dữ liệu mới.

### 15.5. Thử đồng thời và vòng đời

Những tình huống cần kiểm chứng:

- Hai luồng add các khóa khác nhau, có bit thuộc **cùng byte**.
- Query chạy đồng thời với một add chưa hoàn tất.
- Một tiến trình crash giữa cập nhật DB và Bloom.
- Nhiều phiên bản filter được chuyển đổi từ cũ sang mới.
- Khóa có Unicode, chữ hoa/thường, rỗng, byte đặc biệt hoặc cách biểu diễn khác nhau.
- Bộ lọc quá n dự kiến, gần như toàn bit 1.
- OR hai bộ lọc cùng cấu hình; từ chối OR nếu khác cấu hình.

Một phần kiểm thử học thuật chuyên sâu được dành cho bước QA của quy trình, nhưng **hợp đồng hành vi** phải được nêu rõ ngay trong bài học.

## 16. Lỗi thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi True là bằng chứng tồn tại | False positive tạo quyết định sai | True chỉ là “có thể có”; xác minh khi cần |
| Coi False là kết luận cho DB đang cập nhật bất đồng bộ | Sai âm tính cấp hệ thống | Snapshot/delta/nhất quán trạng thái |
| Kiểm tra chỉ một bit thay vì tất cả h bit | Quá nhiều dương tính giả, sai thuật toán | Query cần mọi vị trí băm đều là 1 |
| Add chỉ một trong h bit | Có thể âm tính giả với khóa vừa thêm | Bật đủ h bit |
| Lưu bytearray nhưng quên m, h, hash version | Khôi phục query sai vị trí | Lưu metadata đầy đủ |
| Thay m hoặc seed trên filter cũ | Các vị trí của khóa cũ thay đổi | Tái xây hoặc thay version nhất quán |
| Xóa khóa bằng cách tắt bit | Tắt bit dùng chung của khóa khác | Không xóa trực tiếp ở Bloom chuẩn |
| Dùng counting Bloom rồi xóa khóa chỉ vì query True | Dương tính giả có thể làm giảm nhầm counter | Chỉ xóa khi biết khóa thật đã add |
| Cho counter tràn hoặc giảm quá mức | Mất bất biến không âm tính giả | Kiểm soát độ rộng và số lần update |
| Giả định nhiều hash luôn giảm FPR | Bit có thể bão hòa nhanh hơn | Chọn h theo m/n |
| Chỉ đếm số lượt add làm n | Khóa trùng không sinh thêm vị trí | Thiết kế theo số khóa phân biệt |
| Gọi tỷ lệ FP trên tất cả request là FPR | Mẫu số sai | FPR = FP/(FP+TN) |
| Nghĩ p=1% nghĩa là 1% True sai | Không xét tỷ lệ khóa thật có | Tính tỷ lệ có điều kiện |
| Bắt mọi khóa chưa thêm phải trả False | Bác bỏ sai số cho phép của Bloom | Đo tỷ lệ FP trên nhiều negative |
| Nghĩ cùng khóa sẽ có xác suất mới ở mỗi query | Hash và bit thường cố định | Kết quả một khóa cố định thường lặp lại |
| Dùng hash(key) của runtime rồi lưu bit vĩnh viễn | Seed/phiên bản có thể thay đổi | Dùng băm/version có thể tái lập |
| Quên chuẩn hóa khóa nhất quán | Cùng danh tính nghiệp vụ bị xem là hai khóa | Cấu hình canonicalization |
| OR hai bộ lọc khác seed/h | Không còn ngữ nghĩa bit cùng vị trí | Chỉ OR cấu hình tương thích |
| Đo O(1) mà bỏ qua độ dài key và số hash | Ước lượng CPU thiếu | Nêu O(hL) khi hash h lần |
| Dùng Bloom để ngăn xử lý trùng mà không tra nguồn | Có thể bỏ lỡ sự kiện mới | Verify True nếu không được phép bỏ sót |
| Đồng thời ghi bit bằng read-modify-write không nguyên tử | Một cập nhật bị mất | Dùng atomic OR/lock phù hợp |
| Coi Bloom là cơ chế bảo mật | Có thể bị khai thác qua FP/oracle | Nguồn ủy quyền chính xác |
| Không giám sát số bit đã bật và số khóa | FPR tăng âm thầm | Đo độ bão hòa và tái thiết kế |

**Cách nhớ:** Bloom filter có **một phía chính xác** và một phía **chỉ nghi ngờ**. Thực thi đúng cần bảo toàn tính đơn điệu của bit **và** ngữ nghĩa snapshot, hash, metadata ở cấp hệ thống.


## 17. Bài tập tự luyện có đáp án

### Nhóm A — Nguyên lý và bất biến

**Bài 1 — Hai câu trả lời.** Bloom filter chuẩn trả False và True có ý nghĩa gì?

*Đáp án:* **False = chắc chắn không có trong tập khóa đã add thành công** theo mô hình chuẩn; **True = có thể đã add**, vẫn có thể là false positive.

**Bài 2 — Dương tính giả.** Khóa D chưa thêm nhưng tất cả h bit băm của D đều bằng 1. Đây là lỗi gì?

*Đáp án:* **False positive**, vì các khóa khác có thể đã bật đủ vị trí của D.

**Bài 3 — Âm tính giả.** Khóa A đã được add hoàn tất, mọi bit chỉ chuyển 0→1 và hash không đổi. Query A có thể trả False không?

*Đáp án:* **Không** trong mô hình chỉ-thêm hợp lệ. Tất cả bit của A vẫn bằng 1.

**Bài 4 — Kiểm tra bit.** Một khóa có ba vị trí [2,5,9]; trạng thái các bit ấy là [1,0,1]. Query phải trả gì?

*Đáp án:* **False**, vì chỉ cần một bit 0 là đủ để kết luận chưa thêm.

**Bài 5 — Truy vết hai khóa.** Trong mảng 12 bit, add A ở {1,4,10}, rồi B ở {4,7,10}. Các bit nào bằng 1?

*Đáp án:* **{1,4,7,10}**.

**Bài 6 — Dương tính giả minh họa.** Sau hai lần add ở bài 5, D chưa thêm có vị trí {1,7,10}. Query D trả gì?

*Đáp án:* **True**, dù D chưa thêm; đó là **false positive**.

**Bài 7 — Add trùng.** Nếu add(A) 100 lần, số bit 1 có nhất thiết tăng sau lần đầu không?

*Đáp án:* **Không**. Cùng khóa dùng lại cùng vị trí; add là thao tác idempotent về trạng thái bit.

**Bài 8 — Đếm tần suất.** Bloom filter chuẩn có trả được chính xác số lần A xuất hiện không?

*Đáp án:* **Không**. Mảng bit không chứa số lần add của từng khóa.

**Bài 9 — Liệt kê.** Có thể khôi phục danh sách tên toàn bộ khóa từ bit array không?

*Đáp án:* **Không**. Nhiều tập khóa khác nhau có thể tạo cùng mảng bit.

**Bài 10 — Chứng minh.** Bất biến nào bảo đảm không âm tính giả?

*Đáp án:* Với khóa đã add, mọi vị trí băm của nó được bật; bit **chỉ 0→1**, không bị tắt. Vì vậy query luôn thấy mọi vị trí bằng 1.

### Nhóm B — Công thức xác suất và chọn tham số

**Bài 11 — Ý nghĩa m, h, n.** Trong công thức FPR, m, h và n lần lượt là gì?

*Đáp án:* **m:** số bit; **h:** số vị trí băm mỗi khóa; **n:** số khóa phân biệt đã thêm theo mô hình.

**Bài 12 — Công thức FPR.** Viết xấp xỉ xác suất dương tính giả theo m, h, n.

*Đáp án:* \(p\approx(1-e^{-hn/m})^h\).

**Bài 13 — Vì sao tăng n làm FPR tăng?** Giữ m và h cố định, add thêm rất nhiều khóa phân biệt gây điều gì?

*Đáp án:* **Nhiều bit 1 hơn**, nên khóa lạ dễ gặp đủ h bit 1; FPR tăng.

**Bài 14 — Hash tối ưu.** Với m/n=10 bit trên khóa, số vị trí băm gần tối ưu là bao nhiêu?

*Đáp án:* \(h\approx 10\ln2\approx 6,93\), chọn **7**.

**Bài 15 — Tính dung lượng.** Với n=10.000 khóa và FPR 1%, cần khoảng bao nhiêu bit?

*Đáp án:* \(m\approx -10.000\ln(0,01)/(\ln2)^2\approx95.851\) bit, khoảng **11,7 KiB** mảng bit.

**Bài 16 — Dung lượng byte.** Mảng có m=1001 bit cần tối thiểu bao nhiêu byte lưu bit?

*Đáp án:* **⌈1001/8⌉ = 126 byte**, chưa tính metadata.

**Bài 17 — Số bit luôn 1.** Nếu tất cả m bit đều bằng 1, một khóa lạ có thể nhận False không?

*Đáp án:* **Không**. Mọi vị trí truy vấn đều là 1, nên mọi query trả True; bộ lọc không còn loại được khóa lạ.

**Bài 18 — Nhiều hash.** Tăng h mãi có chắc làm FPR giảm không?

*Đáp án:* **Không**. Nhiều hash hơn còn làm mảng bão hòa nhanh và tăng CPU; h có điểm gần tối ưu theo m/n.

**Bài 19 — Định nghĩa FPR.** Có 20.000 truy vấn thực sự âm tính, 300 lần trả True sai. FPR đo được là bao nhiêu?

*Đáp án:* **300/20.000 = 1,5%**, không phụ thuộc số truy vấn thực sự có.

**Bài 20 — Base rate.** Trong 100.000 truy vấn có 10.000 truy vấn thật có, 90.000 thật không, FPR 1%. Khoảng bao nhiêu câu trả True là sai?

*Đáp án:* Khoảng **900** false positive trên tổng 10.900 câu True, tức khoảng **8,26% True là sai**, không phải 1%.

**Bài 21 — Lặp một khóa lạ.** Hỏi cùng một khóa lạ 1000 lần trên Bloom không đổi có phải 1000 phép thử độc lập về false positive không?

*Đáp án:* **Không**. Khóa và trạng thái bit không đổi, kết quả thường giống hệt qua mọi lần hỏi.

### Nhóm C — Cài đặt và vòng đời

**Bài 22 — Chỉ số bit.** Với vị trí j=29, byte_index và bit_index trong bytearray bằng bao nhiêu?

*Đáp án:* **byte_index=29//8=3**, **bit_index=29%8=5**.

**Bài 23 — Mặt nạ.** Để bật bit_index=5 của một byte, mặt nạ cần dùng là gì?

*Đáp án:* **1 << 5 = 32**; gán byte |= 32.

**Bài 24 — Hash mặc định.** Vì sao không nên dùng hash() mặc định trên str làm vị trí bit rồi lưu bộ lọc lâu dài mà không quản lý seed/version?

*Đáp án:* Vị trí băm có thể thay đổi giữa process/version, khiến khóa đã add không còn tra đúng vị trí.

**Bài 25 — Chuẩn hóa.** Add “Alice” rồi query “alice” có chắc phải True không?

*Đáp án:* **Không**, nếu chưa có quy tắc chuẩn hóa xem hai chuỗi là một khóa; Bloom nhận hai chuỗi khác nhau.

**Bài 26 — Xóa bit.** Vì sao không được xóa A bằng cách tắt mọi bit của A?

*Đáp án:* Các khóa còn tồn tại có thể dùng chung những bit đó; tắt tạo nguy cơ **false negative**.

**Bài 27 — Counting Bloom.** Nếu counting Bloom trả True cho X nhưng X thực sự chưa từng add, có được gọi delete(X) không?

*Đáp án:* **Không**. Dương tính giả không chứng minh X đã được thêm; giảm bộ đếm có thể làm sai các khóa khác.

**Bài 28 — Tăng m.** Có thể đổi m từ 1000 lên 2000 trên Bloom cũ mà giữ bit nguyên để bảo toàn membership không?

*Đáp án:* **Không**. Vị trí hash modulo m thay đổi. Phải tái xây hoặc dùng kiến trúc nhiều lớp đúng hợp đồng.

**Bài 29 — Merge.** Hai Bloom cùng m nhưng khác seed có thể OR bit rồi dùng như một filter hợp lệ không?

*Đáp án:* **Không**. Ngoài m, còn phải khớp **h, hash/seed/version và encoding**.

**Bài 30 — Đồng thời.** Hai luồng cùng bật hai bit khác nhau thuộc một byte bằng phép đọc–sửa–ghi không nguyên tử có thể gây điều gì?

*Đáp án:* **Mất cập nhật bit** nếu luồng ghi đè giá trị cũ, gây nguy cơ âm tính sai; cần atomic OR hoặc đồng bộ.

**Bài 31 — Snapshot cũ.** Database đã thêm X sau khi tạo bộ lọc, nhưng bộ lọc chưa cập nhật. Bloom False có chứng minh X không có trong DB mới không?

*Đáp án:* **Không**. Bộ lọc chỉ bao phủ snapshot cũ; phải tra nguồn mới hoặc delta/overlay trước khi loại.

**Bài 32 — Lưu/khôi phục.** Ngoài bit array, cần lưu metadata gì để query chính xác sau restart?

*Đáp án:* Ít nhất **m, h, hash algorithm/version, seed, encoding/normalization và phạm vi snapshot**.

### Nhóm D — Kiến trúc và chọn cấu trúc

**Bài 33 — Tăng tốc DB.** Bloom trả True khi kiểm tra khóa X. Hệ thống yêu cầu kết luận membership chính xác. Bước tiếp theo là gì?

*Đáp án:* **Tra DB/set có thẩm quyền**, bởi True có thể là dương tính giả.

**Bài 34 — Bloom False.** Bloom trả False khi kiểm tra một SSTable bất biến có filter đã xây đầy đủ từ các khóa của SSTable. Có thể bỏ qua đọc SSTable ấy không?

*Đáp án:* **Có**, trong điều kiện filter đúng, đồng bộ và bao phủ khóa của **chính SSTable ấy**; điều đó chưa chứng minh khóa vắng mặt trong mọi SSTable khác.

**Bài 35 — Chống xử lý trùng.** Một event_id mới bị Bloom trả True do va chạm. Nếu bỏ sự kiện luôn, điều gì xảy ra?

*Đáp án:* Có thể **bỏ sót một sự kiện mới**; phải xác minh khi nghiệp vụ không cho phép mất sự kiện.

**Bài 36 — Tra cứu rẻ.** Nếu mọi khóa đều được hỏi vào một set nhỏ đang nằm trong cache, thêm Bloom có chắc làm hệ thống nhanh hơn không?

*Đáp án:* **Không**. Chi phí h hash và quản lý filter có thể lớn hơn lợi ích tránh tra cứu.

**Bài 37 — Nhiều lớp.** Hai Bloom độc lập, mỗi cái có FPR 1%; query trả True nếu một trong hai True. Tổng FPR chắc chắn vẫn 1% không?

*Đáp án:* **Không**. Union bound cho cận trên **2%**; nếu độc lập, xác suất gần **1−0,99² = 1,99%**.

**Bài 38 — Phân biệt với set.** Nếu cần xóa và liệt kê mọi khóa chính xác, nên dùng Bloom bit chuẩn làm cấu trúc duy nhất không?

*Đáp án:* **Không**. Cần set/DB hoặc cấu trúc có hợp đồng xóa và lưu khóa phù hợp.

**Bài 39 — Bảo mật.** Có được cấp quyền truy cập tài nguyên chỉ vì Bloom trả True cho ID không?

*Đáp án:* **Không**. False positive có thể cấp quyền sai; cần nguồn xác thực/ủy quyền chính xác.

**Bài 40 — Đánh đổi ngân sách.** Muốn giảm FPR 10 lần nhưng m và n giữ nguyên, có thể chỉ tăng h tùy ý và kỳ vọng đạt mục tiêu không?

*Đáp án:* **Không**. Với m/n cố định, h có mức gần tối ưu; muốn FPR thấp hơn đáng kể thường cần **thêm m bit** hoặc đổi kiến trúc/giả định.

## 18. Tổng kết

**Bloom filter** là bộ lọc membership xác suất, sử dụng một **mảng m bit** và **h vị trí băm cho mỗi khóa**. Khi add, nó chỉ bật bit 1. Khi query, **một bit 0 đủ kết luận “chưa được thêm”**, còn **tất cả h bit 1 chỉ kết luận “có thể đã thêm”**.

Bất biến chỉ-thêm **0→1** bảo đảm không có **âm tính giả đối với khóa đã add thành công** nếu trạng thái, hash, encoding và đồng bộ đúng. Dương tính giả xuất hiện vì nhiều khóa có thể dùng chung vị trí bit. Công thức thường dùng:

\[
p_{\mathrm{FP}}\approx\left(1-e^{-hn/m}\right)^h,\qquad
h_{\mathrm{opt}}\approx\frac{m}{n}\ln2,\qquad
m\approx-\frac{n\ln p}{(\ln2)^2}.
\]

Nhờ đó có thể chọn dung lượng theo **n khóa phân biệt dự kiến** và FPR mục tiêu. Bộ nhớ cơ bản là **O(m) bit**, add/query tốn **O(h)** phép băm/bit theo mô hình hằng số hoặc chi phí cao hơn với khóa dài.

Để trả membership **chính xác**, dùng Bloom như **prefilter**: False có thể loại nhanh chỉ khi filter **bao phủ và nhất quán với tập cần hỏi**; True phải được **xác minh tại nguồn chính xác**. Việc xóa, thay m/h/seed, cập nhật đồng thời, khôi phục sai version hoặc dùng filter snapshot cũ có thể phá điều kiện không âm tính giả **ở cấp hệ thống**.

**Ghi nhớ:** **Bloom filter = mảng bit + nhiều vị trí băm + “False chắc chắn, True có thể” theo hợp đồng chỉ-thêm.** Chọn số bit và số hash bằng ngân sách FPR, nhưng quyết định dùng nó phải dựa vào **độ chính xác nghiệp vụ, chi phí xác minh, tính nhất quán và vòng đời dữ liệu** — không chỉ một công thức xác suất.

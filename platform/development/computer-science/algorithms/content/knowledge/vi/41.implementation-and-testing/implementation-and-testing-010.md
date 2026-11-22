# Đối chiếu lời giải tối ưu với vét cạn trên dữ liệu nhỏ

## Mục tiêu học tập

Trong nhóm **Cài đặt và kiểm thử**, việc một thuật toán có độ phức tạp tốt như O(n), O(n log n) hay O(log n) **không tự chứng minh chương trình trả lời đúng**. Một cài đặt tối ưu có thể mắc lỗi lệch chỉ số, bỏ sót trường hợp biên, xử lý dấu bằng sai, dùng quy tắc tham lam không hợp lệ hoặc hỏng khi dữ liệu có phần tử trùng.

Một cách kiểm thử rất hiệu quả là **đối chiếu lời giải tối ưu với lời giải vét cạn đúng nhưng chậm trên dữ liệu nhỏ**. Ý tưởng:

1. Viết một lời giải đơn giản, ưu tiên **dễ chứng minh đúng** hơn tốc độ.
2. Viết lời giải tối ưu độc lập về cách tiếp cận.
3. Sinh nhiều input đủ nhỏ để lời giải vét cạn chạy được.
4. Chạy cả hai, **so sánh theo cùng đặc tả**.
5. Nếu khác nhau, lưu seed, input và kết quả; thu nhỏ phản ví dụ.
6. Phân tích nguyên nhân, sửa lỗi, rồi thêm ca đó vào bộ regression.

Phương pháp còn gọi là **differential testing** khi đối chiếu các triển khai độc lập; nếu một triển khai là bộ kiểm tra chân lý cho input nhỏ thì ta thường gọi nó là **oracle vét cạn** (*brute-force oracle*).

Kết thúc bài, bạn có thể:

- Xác định rõ bài toán, miền dữ liệu và điều kiện kết quả hợp lệ.
- Xây dựng oracle độc lập bằng liệt kê tất cả phương án nhỏ.
- Phân biệt **tối ưu giá trị**, **tối ưu lời giải** và **quy tắc phá hòa**.
- Tạo bộ test liệt kê đầy đủ và bộ test giả ngẫu nhiên tái lập bằng seed.
- Phát hiện lỗi bằng đối chiếu Kadane O(n) với tìm đoạn con lớn nhất O(n²).
- Kiểm chứng greedy chọn số khoảng không giao nhau nhiều nhất bằng xét mọi tập con O(2^n n²).
- Hiểu vì sao một vài nghìn ca random đúng chưa đủ chứng minh thuật toán.
- Thu nhỏ phản ví dụ, dùng invariant, metamorphic testing, kiểm thử biên và regression.
- Thiết kế chương trình **Java 17+ độc lập**, với lệnh biên dịch/chạy, stdout và lỗi được giải thích.

---

## 1. Vì sao cần oracle khi đã có thuật toán tối ưu?

Giả sử bạn giải bài:

> Cho một mảng số nguyên không rỗng. Tìm tổng lớn nhất của một đoạn con liên tiếp không rỗng.

Thuật toán **Kadane** có thể làm O(n) thời gian. Nhưng chương trình chạy nhanh không có nghĩa nó đúng.

Các lỗi thường gặp:

- Khởi tạo kết quả bằng 0 khiến trường hợp **toàn số âm** sai.
- Cho phép đoạn rỗng dù đề chỉ cho đoạn không rỗng.
- So sánh `>` thay vì `>=` làm thay đổi quy tắc chọn khi nhiều lời giải cùng tổng.
- Dùng `int` cho tổng có thể vượt phạm vi int.
- Cập nhật chỉ số bắt đầu đoạn sau khi đã tính ứng viên, gây lệch 1.
- Tối ưu đúng giá trị tổng nhưng sai chỉ số đoạn mà đề yêu cầu.

Đối với n nhỏ, ta có thể **duyệt mọi đoạn [l,r]** rồi lấy tổng lớn nhất. Dù chậm hơn, cách này dễ lập luận:

> Mọi đoạn con liên tiếp không rỗng được xác định duy nhất bằng cặp l,r với 0≤l≤r<n. Nếu liệt kê tất cả cặp và chọn tốt nhất, không thể bỏ sót nghiệm.

Đó chính là một oracle.

### 1.1. "Chậm nhưng đúng" không có nghĩa "mã nào chậm cũng đúng"

Một oracle đáng tin phải có:

1. Đặc tả đầu vào và đầu ra rõ ràng.
2. Không bỏ sót phương án hợp lệ.
3. Không chấp nhận phương án không hợp lệ.
4. Tính điểm của từng phương án chính xác.
5. Quy tắc so sánh kết quả đúng với đặc tả.
6. Ít tối ưu vi mô hoặc thủ thuật dễ sai.
7. Không sao chép cùng lỗi từ lời giải tối ưu.

Nhiều lỗi kiểm thử bắt nguồn từ việc **oracle cũng sai** hoặc hai triển khai dùng chung một hàm xử lý chỉ số có lỗi.

### 1.2. Tính đúng và hiệu năng là hai câu hỏi riêng

Với input n=8, vét cạn có thể chạy tức thời; với n=100000, nó có thể không phù hợp. Không nên cố vét cạn input lớn trong production.

- **Oracle** được dùng trên dữ liệu nhỏ, ưu tiên minh bạch và độc lập.
- **Thuật toán tối ưu** được dùng trên dữ liệu lớn, ưu tiên hiệu quả mà vẫn phải đúng.
- **Benchmark** được dùng để đánh giá thời gian/bộ nhớ, không dùng để thay thế kiểm thử tính đúng.

---

## 2. Thiết kế phép đối chiếu trước khi viết code

Một quy trình có thể mô tả bằng:

```text
               +----------------------+
               | Input nhỏ được sinh  |
               +-----------+----------+
                           |
                +----------+----------+
                |                     |
                v                     v
       +----------------+   +--------------------+
       | Oracle vét cạn |   | Lời giải tối ưu    |
       +-------+--------+   +----------+---------+
               |                       |
               v                       v
       +---------------+       +---------------+
       | Expected      |       | Actual        |
       +-------+-------+       +-------+-------+
               |                       |
               +-----------+-----------+
                           |
                    So sánh đúng
                   đặc tả/tie-break
                           |
                +----------+-----------+
                |                      |
             Khớp                   Khác
                |                      |
            Ca PASS          In seed, input, outputs
                                       |
                                Thu nhỏ phản ví dụ
                                       |
                                 Sửa và regression
```

### 2.1. Đầu vào

Hãy xác định:

- n có thể bằng 0 không?
- Chỉ số 0-based hay 1-based?
- Khoảng [l,r] đóng hai đầu hay [l,r) nửa mở?
- Phần tử có thể âm, 0, trùng nhau không?
- Có ràng buộc không tràn số không?
- Có yêu cầu tìm **giá trị tối ưu** hay **cấu hình phương án**?
- Khi có nhiều nghiệm tối ưu, phải chọn nghiệm nào?

Nếu hai thuật toán nhận **hai đặc tả khác nhau**, kết quả khác không nhất thiết là bug.

### 2.2. Đầu ra

Có ba mức đối chiếu:

| Mức | Ví dụ | Điều cần so sánh |
| --- | --- | --- |
| Boolean | Có tồn tại tập con thỏa điều kiện? | true/false |
| Giá trị tối ưu | Tổng lớn nhất / số khoảng tối đa | Giá trị số |
| Một nghiệm cụ thể | Vị trí đoạn, danh sách khoảng | Giá trị + tính hợp lệ + quy tắc phá hòa |

Hai cách chọn tập khoảng có thể khác danh sách nhưng **cùng số lượng tối ưu**. Nếu đề không yêu cầu thứ tự tie-break, so trực tiếp danh sách là sai cách kiểm thử.

Ngược lại, nếu đề yêu cầu đoạn con tối ưu có vị trí trái nhỏ nhất rồi phải nhỏ nhất, chỉ so tổng là **không đủ**.

### 2.3. So sánh output theo ngữ nghĩa

- Với **tập hợp**, nên so tính thành viên sau chuẩn hóa, không so thứ tự in nếu thứ tự không quan trọng.
- Với **đồ thị**, nếu yêu cầu một đường đi bất kỳ có độ dài ngắn nhất, xác minh cạnh hợp lệ, điểm đầu/cuối và độ dài; hai đường ngắn nhất có thể khác nhau.
- Với **số thực**, nên dùng sai số tuyệt đối/tương đối hợp lý thay vì bằng bit tuyệt đối, trừ khi đề yêu cầu tái lập bit.
- Với **bài tối ưu**, phải xác minh **nghiệm hợp lệ** và **giá trị mục tiêu đạt tối ưu**.

---

## 3. Ví dụ chính 1: đoạn con liên tiếp có tổng lớn nhất

### 3.1. Đặc tả đầy đủ

Input: mảng `a[0..n-1]` số nguyên có dấu, `n≥1`.

Tìm đoạn **không rỗng**, liên tiếp, ký hiệu [l,r] đóng hai đầu, sao cho:

\[
\boxed{
sum(l,r)=\sum_{i=l}^{r}a[i]
}
\]

lớn nhất.

Để một kết quả là duy nhất khi nhiều đoạn cùng tổng, quy định:

1. Ưu tiên **tổng lớn hơn**.
2. Nếu tổng bằng nhau, ưu tiên **l nhỏ hơn**.
3. Nếu l cũng bằng nhau, ưu tiên **r nhỏ hơn**.

Đây là thứ tự từ điển theo bộ:

\[
(-sum,l,r).
\]

**Không** ưu tiên đoạn ngắn nhất, và **không** cho đoạn rỗng.

### 3.2. Ví dụ

```text
Index:  0  1   2  3   4  5  6   7  8
a:     -2  1  -3  4  -1  2  1  -5  4
```

Đoạn [3,6]:

\[
4+(-1)+2+1=\boxed6.
\]

Đó là tổng lớn nhất theo đặc tả.

Kết quả:

```text
sum=6
left=3
right=6
```

### 3.3. Vét cạn O(n²) với tổng cộng dồn

Liệt kê mọi đầu trái l; với mỗi l, mở rộng đầu phải r:

```text
best = chưa có

for l = 0..n-1:
    running = 0

    for r = l..n-1:
        running += a[r]

        if (running,l,r) tốt hơn best:
            best = (running,l,r)

return best
```

Điểm độc lập quan trọng: oracle **không dựa vào minimum prefix hay Kadane**. Nó thử từng đoạn trực tiếp và cập nhật tổng khi r tăng.

### 3.4. Vì sao liệt kê là đúng?

Mỗi đoạn hợp lệ ứng với đúng một cặp (l,r) thỏa:

\[
0\le l\le r<n.
\]

Số cặp là:

\[
1+2+\cdots+n=\boxed{\frac{n(n+1)}2}.
\]

Hai vòng l/r xét tất cả cặp, mỗi đoạn chỉ một lần. Với mỗi cặp, `running` bằng tổng từ a[l] tới a[r] theo bất biến vòng trong. Nếu chỉ thay `best` bằng ứng viên tốt hơn theo đúng thứ tự ưu tiên, cuối cùng `best` là tối ưu và có tie-break đúng.

### 3.5. Độ phức tạp

- Có O(n²) cặp l/r.
- Mỗi lần tăng r chỉ cộng một phần tử.
- Thời gian: **O(n²)**.
- Bộ nhớ phụ: O(1) ngoài kết quả.

Nếu với mỗi cặp lại quét từ l tới r để tính tổng từ đầu, chi phí có thể thành O(n³). Điều đó vẫn là vét cạn hợp lệ trên n rất nhỏ, nhưng bản O(n²) vừa dễ đọc vừa ít overhead hơn.

**Vét cạn không nhất thiết phải là thuật toán chậm nhất có thể; nó phải rõ ràng và đúng.**

---

## 4. Lời giải tối ưu bằng tổng tiền tố nhỏ nhất

Có thể tìm đoạn con tổng lớn nhất O(n) thời gian bằng cách duy trì **prefix sum nhỏ nhất đã thấy**.

Định nghĩa:

\[
P[0]=0,\qquad P[i+1]=P[i]+a[i].
\]

Tổng đoạn [l,r]:

\[
\boxed{sum(l,r)=P[r+1]-P[l].}
\]

Với một r cố định, muốn tổng lớn nhất thì phải chọn:

\[
\boxed{P[l]=\min_{0\le l\le r}P[l].}
\]

Vậy khi quét từ trái sang phải:

- `prefix`: P[r+1] của đoạn đã đọc.
- `minPrefix`: giá trị nhỏ nhất trong `P[0..r]`.
- `minIndex`: chỉ số sớm nhất đạt `minPrefix`.
- Ứng viên hiện tại:
  \[
  (prefix-minPrefix,\ minIndex,\ r).
  \]
- Cập nhật kết quả nếu ứng viên tốt hơn.
- Sau đó mới xét liệu prefix mới trở thành minPrefix cho vòng tương lai.

### 4.1. Vì sao phải cập nhật minPrefix **sau** khi xét ứng viên?

Đoạn yêu cầu **không rỗng**: nếu điểm trái là l và phải là r thì:

\[
l\le r.
\]

Giá trị `P[r+1]` không được dùng để trừ chính nó tạo đoạn [r+1,r] rỗng. Vì vậy tại bước xử lý r, `minPrefix` chỉ được lấy từ `P[0..r]`, rồi mới đưa `P[r+1]` vào tập giá trị tiền tố cho vòng sau.

Thứ tự:

```text
prefix += a[r]
candidate = prefix - minPrefix
compare candidate with best

if prefix < minPrefix:
    minPrefix = prefix
    minIndex = r + 1
```

là đúng.

### 4.2. Vì sao không cập nhật minIndex khi prefix bằng minPrefix?

Theo tie-break, ưu tiên l nhỏ nhất. Nếu có hai chỉ số tiền tố khác nhau có **cùng giá trị tối thiểu**, cả hai cho cùng tổng; chỉ số nhỏ hơn tạo đoạn có l nhỏ hơn. Vì thế:

```java
if (prefix < minPrefix) { ... }
```

và **không** dùng `<=`.

Nếu thay bằng `<=`, khi tổng bằng nhau thuật toán có thể chọn đoạn trái lớn hơn, trái quy ước tie-break.

### 4.3. Bất biến của vòng quét

Ngay trước khi xét phần tử r:

1. `prefix=P[r]`.
2. `minPrefix=min(P[0],...,P[r])`.
3. `minIndex` là chỉ số nhỏ nhất đạt `minPrefix`.
4. `best` là đoạn tốt nhất trong mọi đoạn có đầu phải ≤r−1.

Sau khi cộng a[r], ứng viên tối ưu trong các đoạn có đầu phải r được tính từ `minPrefix`. So với `best` rồi cập nhật minPrefix cho r+1 bảo toàn bất biến.

Do đó khi r=n−1 kết thúc, `best` là đoạn tốt nhất toàn mảng theo đặc tả.

### 4.4. Độ phức tạp

- Một vòng for qua n phần tử.
- Mỗi lần làm O(1) phép cộng, trừ và so sánh.
- Thời gian **O(n)**, bộ nhớ phụ **O(1)**.

Cách này là một biểu diễn bằng prefix min của tinh thần Kadane: giữ thông tin tối thiểu để quyết định đoạn tốt nhất mà không thử lại mọi đoạn.

### 4.5. Các trường hợp biên

**Toàn số âm:**

```text
a = [-4,-1,-7]
best = -1, range=[1,1]
```

Nếu khởi tạo best=0 và cho phép rỗng ngầm, kết quả sai.

**Tất cả bằng 0:**

```text
a = [0,0,0]
best = 0, range=[0,0]
```

Các đoạn khác cũng có tổng 0, nhưng tie-break chọn l=0 và sau đó r nhỏ nhất, tức r=0.

**Có nhiều đoạn cùng tổng tốt nhất:**

```text
a = [2,-2,2]
best = 2, range=[0,0]
```

Đoạn [0,2] và [2,2] cũng tổng 2, nhưng quy tắc ưu tiên [0,0].

**Một phần tử:**

```text
a = [-7]
best = -7, range=[0,0]
```

**Mảng rỗng:** theo đặc tả bài này là input không hợp lệ, nên từ chối rõ ràng thay vì trả đoạn rỗng hoặc dùng chỉ số âm giả.

---

## 5. So sánh hai thuật toán: điều gì thực sự độc lập?

Với đoạn con tổng lớn nhất:

| Yếu tố | Oracle | Lời giải tối ưu |
| --- | --- | --- |
| Cách duyệt | Tất cả cặp (l,r) | Quét r một lần |
| Cách tính | Cộng trực tiếp từ l khi mở r | Tổng tiền tố và tiền tố nhỏ nhất |
| Số phương án xét | n(n+1)/2 | Một ứng viên tối ưu cho mỗi r |
| Thời gian | O(n²) | O(n) |
| Bộ nhớ phụ | O(1) | O(1) |
| Khả năng tìm bug | Làm chuẩn expected | Là đối tượng được kiểm tra |

Hai thuật toán cùng áp dụng **một đặc tả tie-break**, nhưng không sao chép quy tắc tìm đoạn tối ưu. Trong mã Java cuối bài, oracle sử dụng điều kiện so sánh tách riêng để tránh phụ thuộc quá mức vào helper cập nhật kết quả của lời giải nhanh.

### 5.1. Phần chung nào vẫn phải được kiểm tra?

Cả hai có thể dùng kiểu `long` và cùng giả định không tràn số. Nếu dữ liệu vượt miền long, cả hai có thể thất bại hoặc tràn theo cùng kiểu. Vì thế:

- Đặt hợp đồng phạm vi số học rõ.
- Dùng `Math.addExact`/`Math.subtractExact` để phát hiện overflow nếu cần.
- Có thêm oracle toán học như `BigInteger` cho trường hợp biên số rất lớn, nếu đề yêu cầu.
- Không chỉ dựa vào sự trùng nhau giữa hai đáp án để chứng minh không overflow.

### 5.2. Tách lỗi logic khỏi lỗi in kết quả

Nếu oracle trả tổng 6 và fast cũng tổng 6 nhưng chỉ số khác, có ít nhất hai khả năng:

- Đề chỉ yêu cầu tổng: hai kết quả có thể đều đúng.
- Đề yêu cầu tie-break như đã nêu: phải xem một trong hai hoặc cả hai đang sai quy tắc chọn.

Vì vậy test nên so **đúng loại output mà đặc tả yêu cầu**.

---

## 6. Kiểm thử vét cạn toàn bộ miền nhỏ

Thay vì chỉ sinh ngẫu nhiên, ta có thể **liệt kê tất cả mảng nhỏ**.

Chọn:

\[
n\in\{1,2,3,4,5,6\},
\]

và mỗi phần tử thuộc:

\[
a[i]\in\{-2,-1,0,1,2\}.
\]

Với n cố định, số mảng là:

\[
5^n.
\]

Tổng số mảng cho n từ 1 đến 6:

\[
5+25+125+625+3125+15625=\boxed{19530}.
\]

Mỗi mảng được tạo từ một số `code` trong `[0,5^n)` bằng cách đọc các chữ số cơ số 5 rồi trừ 2. Ta có ánh xạ một–một giữa mã số và mảng.

### 6.1. Lợi ích của full enumeration

Mọi tổ hợp trong **miền nhỏ đã chọn** đều được kiểm tra. Bao gồm:

- Toàn âm.
- Toàn 0.
- Nhiều đoạn cùng tổng.
- Nhiều phần tử trùng.
- Đoạn tối ưu ở đầu, giữa hoặc cuối.
- Các dao động dương/âm.
- Đoạn dài và đoạn một phần tử.

Nếu toàn bộ 19.530 ca khớp, ta có bằng chứng mạnh **trong miền đó**. Không có nghĩa chứng minh cho n bất kỳ hay giá trị lên tới Long.MAX_VALUE.

### 6.2. Cách viết test

```text
for n = 1..6:
    for code = 0 .. 5^n-1:
        a = decodeBase5(code, n) - 2

        expected = bruteMaxSubarray(a)
        actual = fastMaxSubarray(a)

        assert actual == expected
```

Điểm cần có khi mismatch:

- Giá trị n.
- Mảng cụ thể.
- Expected.
- Actual.
- Quy tắc tie-break đang được dùng.

---

## 7. Kiểm thử ngẫu nhiên có thể tái lập

Liệt kê đầy đủ chỉ thực tế khi n và miền giá trị nhỏ. Để bao phủ những tổ hợp khác, sinh input giả ngẫu nhiên bằng **seed cố định**.

Ví dụ:

```java
SplittableRandom random =
        new SplittableRandom(20261110L);
```

Từng vòng:

1. Chọn n từ 1 đến 12.
2. Sinh n phần tử trong [−20,20].
3. Chạy oracle O(n²).
4. Chạy thuật toán O(n).
5. So tổng và hai chỉ số.
6. Nếu mismatch, in seed, vòng lặp, mảng, expected và actual; dừng.

Chương trình cuối bài chạy **10.000 ca ngẫu nhiên** cho max-subarray và **2.500 ca ngẫu nhiên** cho bài lịch khoảng.

### 7.1. Vì sao phải lưu seed và input?

Một báo cáo lỗi chỉ ghi "sai tại test 237" không đủ nếu:

- Generator thay đổi.
- Random state trước đó khác.
- Dữ liệu được sinh bằng thời gian hiện tại.
- Không biết điều kiện biên của input.

Báo cáo nên có:

```text
seed=20261110
trial=237
input=[...]
expected=...
actual=...
```

Nhờ đó người sửa lỗi chạy lại cùng ca chính xác.

### 7.2. Seed cố định không loại bỏ nhu cầu lưu input

Mã generator cũng có thể thay đổi. Khi một lỗi quan trọng xuất hiện, lưu **input gốc dạng độc lập** bên cạnh seed là cách tốt hơn chỉ lưu seed.

### 7.3. Seed cố định và nhiều seed

Trong CI, seed cố định giúp regression ổn định. Khi khám phá lỗi, có thể chạy thêm nhiều seed khác nhau rồi lưu lại seed của ca thất bại.

Một chiến lược thực tế:

- Chạy bộ seed cố định nhanh trong mỗi commit.
- Chạy một số seed mới ở jobs kiểm tra sâu.
- Khi tìm lỗi, lưu input thu nhỏ vào bộ regression cố định.

---

## 8. Ví dụ chính 2: chọn nhiều khoảng không giao nhau nhất

Cho n khoảng thời gian **nửa mở**:

\[
[start_i,end_i),
\]

với:

\[
\boxed{start_i<end_i}.
\]

Hai khoảng [s1,e1) và [s2,e2) không giao nhau nếu:

\[
\boxed{e_1\le s_2\quad\text{hoặc}\quad e_2\le s_1}.
\]

**Quan trọng:** Nếu một khoảng kết thúc tại t và khoảng kế tiếp bắt đầu tại t, chúng **tương thích** trong mô hình nửa mở. Với [l,r] đóng hai đầu, điều kiện sẽ khác.

Mục tiêu: chọn **số lượng khoảng tối đa** sao cho mọi cặp được chọn không giao nhau.

### 8.1. Lời giải greedy tối ưu

Sắp khoảng theo:

1. `end` tăng dần.
2. Nếu `end` bằng nhau, `start` tăng dần để kết quả có thứ tự xác định.

Duyệt:

```text
lastEnd = -infinity
chosen = []

for interval in sortedByEnd:
    if interval.start >= lastEnd:
        chosen.add(interval)
        lastEnd = interval.end

return chosen
```

Độ phức tạp O(n log n) do sắp xếp; phần duyệt O(n).

### 8.2. Chứng minh trao đổi (*exchange argument*)

Gọi g là khoảng có thời điểm kết thúc sớm nhất. Xét một lời giải tối ưu O bất kỳ, trong đó khoảng đầu tiên theo thời gian kết thúc là o.

Vì:

\[
end(g)\le end(o),
\]

ta có thể thay o bằng g mà vẫn để mọi khoảng sau o bắt đầu không trước `end(o)`, nên cũng không trước `end(g)`. Số lượng khoảng không đổi.

Vì thế tồn tại một lời giải tối ưu bắt đầu bằng g. Sau khi chọn g, bài toán còn lại là chọn nhiều khoảng nhất trong những khoảng bắt đầu không trước `end(g)`. Áp dụng lập luận tương tự cho phần còn lại, greedy đúng theo quy nạp.

**Điều kiện quan trọng:** đây là bài **tối đa số lượng** khoảng không giao nhau. Nếu mỗi khoảng có trọng số khác nhau và mục tiêu là **tổng trọng số**, greedy kết thúc sớm nhất không còn luôn đúng; bài đó thường dùng quy hoạch động weighted interval scheduling.

### 8.3. Vét cạn độc lập bằng mọi tập con

Với n nhỏ, mỗi tập con được biểu diễn bằng bitmask:

\[
mask\in[0,2^n).
\]

Với mỗi mask:

1. Đếm số bit 1 = số khoảng được chọn.
2. Nếu số lượng không thể vượt best hiện tại, có thể bỏ qua.
3. Kiểm tra **từng cặp** khoảng có bit 1:
   \[
   end_i\le start_j
   \quad\lor\quad
   end_j\le start_i.
   \]
4. Nếu mọi cặp không giao nhau, mask hợp lệ.
5. Cập nhật số lượng lớn nhất.

Oracle **không sắp theo thời điểm kết thúc** và không dựa vào lập luận tham lam, nên độc lập rõ ràng với greedy.

### 8.4. Chi phí

- Có `2^n` tập con.
- Một tập con có thể cần kiểm tra O(n²) cặp.
- Thời gian oracle: 
  \[
  \boxed{O(2^n n^2)}.
  \]
- Bộ nhớ phụ: O(1) nếu kiểm tra trực tiếp mask, không lưu mọi tập con.

Mã ví dụ giới hạn n≤20 để tránh số tập con và số bit vượt phạm vi thiết kế của `1<<n`. Khi n=20, số mask đã là 1.048.576; thử toàn bộ có thể chậm đáng kể. Với random test n≤10, tối đa 1.024 mask mỗi test.

### 8.5. Ví dụ lịch khoảng

```text
[1,4)
[3,5)
[0,6)
[5,7)
[8,9)
[5,9)
```

Greedy theo end có thể chọn:

```text
[1,4), [5,7), [8,9)
```

Số lượng:

\[
\boxed3.
\]

Vét cạn mọi tập con cũng trả tối ưu 3.

### 8.6. Vì sao "ưu tiên bắt đầu sớm nhất" có thể sai?

Xét:

```text
[0,10)
[1,2)
[2,3)
[3,4)
```

Nếu chọn khoảng bắt đầu sớm nhất [0,10), ta chỉ chọn được **1** khoảng.

Greedy kết thúc sớm nhất chọn:

```text
[1,2), [2,3), [3,4)
```

được **3** khoảng, cũng là tối ưu theo oracle.

Phản ví dụ n=4 ngắn gọn giúp phát hiện một chiến lược tham lam sai **ngay cả trước khi viết code**.

### 8.7. So sánh số lượng hay danh sách?

Một input có thể có nhiều tập khoảng khác nhau cùng số lượng tối đa. Nếu đề chỉ yêu cầu **số lượng**, thì:

```text
greedyCount == bruteBestCount
```

là phép so sánh đúng.

Nếu đề yêu cầu xuất chính danh sách các khoảng:

- Kiểm tra từng khoảng được chọn có trong input.
- Không chọn một phần tử nhiều lần ngoài số lần nó xuất hiện.
- Kiểm tra mọi cặp không giao nhau.
- Kiểm tra kích thước bằng tối ưu oracle.
- Chỉ so danh sách bằng nhau nếu đề quy định rõ tie-break cho danh sách.

Không được báo lỗi chỉ vì hai nghiệm tối ưu hợp lệ khác thứ tự hoặc khác phần tử.

---

## 9. Đối chiếu giá trị tối ưu không thay thế kiểm tra nghiệm

Giả sử một thuật toán trả:

```text
value=3
chosen=[I0,I1,I2]
```

Oracle trả optimum=3. Điều đó **chưa đủ** nếu `chosen` chứa hai khoảng chồng lấn. Một thuật toán có thể in số lượng đúng nhưng danh sách sai.

Kiểm tra thêm:

\[
\operatorname{feasible}(chosen)=true,
\]

\[
|chosen|=\operatorname{optimum}.
\]

Cùng ý tưởng áp dụng:

- Tìm đường đi ngắn nhất: đường đi phải dùng cạnh hợp lệ và trọng số đúng.
- Tối ưu ba lô: tổng khối lượng không quá giới hạn, giá trị đạt optimum.
- Ghép cặp: không dùng cùng đỉnh ở hai cặp, số cặp tối đa.
- Cây khung: phải là cây, nối tất cả đỉnh và tổng trọng số tối thiểu.
- Tô màu: mọi cặp đỉnh kề nhau khác màu, số màu theo đặc tả.

**Expected score bằng actual score chưa chứng minh actual witness hợp lệ.**

---

## 10. Phân biệt tính đúng của greedy, DP và cấu trúc dữ liệu

Vét cạn là một oracle **theo đặc tả**, nên có thể kiểm tra nhiều họ thuật toán khác nhau.

### 10.1. Greedy

Ví dụ interval scheduling, coin change ở hệ mệnh giá không chuẩn, lịch tối ưu có điều kiện.

Oracle duyệt các phương án và đo mục tiêu. Rất phù hợp để tìm **phản ví dụ làm greedy thất bại**.

**Lưu ý:** greedy không đúng cho mọi bài; trước khi "tối ưu", cần chứng minh lựa chọn tham lam.

### 10.2. Quy hoạch động

Ví dụ subset sum, knapsack 0/1, LCS, TSP trên ít đỉnh.

Oracle:

- Liệt kê mọi tập con cho subset sum/knapsack.
- Liệt kê hoán vị cho TSP với n nhỏ.
- Liệt kê các subsequence cho LCS.

DP phải cho cùng giá trị tối ưu.

Nếu DP dùng trạng thái bị thiếu chiều hoặc chuyển sai thứ tự, vét cạn nhỏ thường phát hiện.

### 10.3. Cấu trúc dữ liệu

Ví dụ Fenwick, segment tree lazy, heap, union-find:

- Oracle thường là **mảng hoặc danh sách trực tiếp**.
- Sinh ngẫu nhiên nhiều thao tác update/query.
- Với mỗi query, so đáp án ngay tại thời điểm tương ứng.
- Đối chiếu bất biến sau từng thao tác.

Cần tránh việc cả oracle và thuật toán chính cùng dùng một hàm cập nhật phức tạp, vì sẽ làm giảm độc lập.

### 10.4. Thuật toán đồ thị

Với n nhỏ:

- BFS shortest path so với liệt kê đường đơn hợp lệ hoặc Bellman–Ford trong điều kiện trọng số phù hợp.
- MST Kruskal/Prim so với liệt kê tập cạnh có đúng n−1 cạnh rồi kiểm tra nối liên thông và không chu trình.
- Matching bipartite so với thử mọi cách ghép có ràng buộc đỉnh.
- Max flow trên đồ thị nhỏ so với liệt kê lát cắt s–t và kiểm tra định lý max-flow/min-cut.

Đặc tả, loại trọng số, hướng cạnh, đa cạnh và disconnected cases phải thống nhất. Không phải oracle nào cũng có chi phí rẻ, nên giữ n nhỏ thực sự.

---

## 11. Test generator: sinh nhỏ nhưng đủ đa dạng

Một generator tốt không chỉ sinh "đều ngẫu nhiên" rồi hy vọng lỗi xuất hiện.

### 11.1. Phân phối kích thước

Chọn n từ tập:

```text
0, 1, 2, 3, ... 12
```

hoặc chia tần suất:

- Nhiều test n=0,1,2 để chạm trường hợp biên.
- Nhiều test n=3..10 để tạo tương tác.
- Một số test n=11..15 nếu oracle vẫn chạy nhanh.

Đối với bài max-subarray đề yêu cầu n≥1, input n=0 phải kiểm thử **từ chối**, không coi là một ca cần trả nghiệm.

### 11.2. Phân phối giá trị

Đừng chỉ sinh số dương. Dùng:

- Số âm.
- 0.
- Nhiều giá trị bằng nhau.
- Dãy tăng/giảm.
- Dãy toàn cùng dấu.
- Dãy xen kẽ dấu.
- Những giá trị cực đại của miền hợp lệ.
- Nhiều đoạn tối ưu cùng điểm.

Với bài tổng đoạn, các mảng như `[-1]`, `[0,0,0]`, `[2,-2,2]` thường phát hiện lỗi nhanh hơn mảng dài ngẫu nhiên.

### 11.3. Cấu trúc đặc thù

Với interval scheduling:

- Hai khoảng cùng end.
- Hai khoảng cùng start.
- Khoảng chạm nhau ở biên: `endA=startB`.
- Khoảng lồng nhau.
- Nhiều khoảng giống hệt.
- Khoảng có start âm.
- Tập khoảng rỗng.
- Một khoảng duy nhất.
- Dãy khoảng rời nhau hoàn toàn.
- Một khoảng dài phủ nhiều khoảng ngắn.

### 11.4. Sinh input hợp lệ trước

Nếu đề yêu cầu `start<end`, generator nên sinh:

```java
int start = random.nextInt(-5, 15);
int end = start + random.nextInt(1, 8);
```

Bằng cách này chắc chắn có `end>start` và không cần sửa dữ liệu sau sinh. Nếu muốn test input không hợp lệ, hãy xây bộ test riêng để xác nhận chương trình từ chối đúng.

---

## 12. Shrinking: thu nhỏ phản ví dụ

Khi có mismatch trên input dài 100 phần tử, việc đọc cả mảng khó giúp hiểu lỗi. **Shrinking** cố tìm một input nhỏ hơn **vẫn gây mismatch**.

Ví dụ:

```text
Input lỗi:
[4,-2,0,0,-3,5,-1,7,-8,2,...]
```

Ta có thể:

1. Xóa nửa đầu rồi kiểm tra mismatch còn không.
2. Nếu còn, giữ phần nhỏ; nếu mất, thử xóa nửa sau.
3. Tiếp tục xóa từng đoạn hoặc từng phần tử.
4. Thử giảm trị tuyệt đối của từng giá trị về 0, ±1.
5. Lặp cho đến khi không thể giảm theo chiến lược đã chọn.

### 12.1. Delta debugging

Một cách tổng quát là **ddmin**: chia input thành các phần, thử xóa từng phần hoặc chỉ giữ từng phần, tăng mức chia khi cần.

Mục tiêu là tìm **phản ví dụ tối giản theo các phép biến đổi đã thử**, không nhất thiết là phản ví dụ nhỏ nhất toàn cục.

### 12.2. Shrink phải giữ input hợp lệ

Nếu giảm thời gian một khoảng làm `start>=end`, input đã vi phạm đặc tả và mismatch không còn có ý nghĩa cho bài gốc. Hãy ràng buộc shrinker:

- Không tạo khoảng rỗng khi đề cấm.
- Không phá thứ tự/số lượng đỉnh cần thiết.
- Không tạo chỉ số ngoài phạm vi.
- Không làm thay đổi định nghĩa của query.
- Không cắt mất phần bắt buộc của một cấu trúc đầu vào.

### 12.3. Cần bảo toàn đúng tiêu chí thất bại

Nếu bug là khác **chỉ số tie-break**, shrinker phải tiếp tục so cả (sum,left,right), không chỉ so sum. Nếu chỉ giữ giá trị mục tiêu, phản ví dụ có thể "biến mất" dù bug vẫn còn.

### 12.4. Khi tìm được ca nhỏ

Chuyển thành regression test có expected rõ ràng. Ví dụ:

```text
a=[0,0]
expected: sum=0,left=0,right=0
```

Nếu thuật toán chọn [1,1], lỗi không ở tổng mà ở tie-break.

---

## 13. Metamorphic testing khi không đủ oracle

Một **metamorphic relation** là quan hệ giữa input ban đầu và input được biến đổi mà output phải tuân theo, dù không biết đáp án chính xác của mọi input lớn.

### 13.1. Max-subarray: nhân hệ số dương

Nếu mọi phần tử nhân một hằng `c>0`, không xảy ra overflow, mọi tổng đoạn nhân c và thứ tự so sánh tổng không thay đổi. Do đó:

- Đoạn tối ưu theo quy tắc tie-break vẫn có cùng chỉ số.
- Giá trị tối ưu nhân c.

Ví dụ:

```text
a=[-2,3,-1,2]
b=3*a=[-6,9,-3,6]
```

Nếu đáp án a là (sum=4,[1,3]), đáp án b phải là (sum=12,[1,3]).

**Không suy rộng cho c=0 hoặc c âm.** Khi c=0, mọi đoạn có tổng bằng nhau và tie-break có thể chọn đoạn khác; khi c<0, bài tối đa đổi thứ tự so sánh.

### 13.2. Scheduling: tịnh tiến thời gian

Nếu cộng cùng một k vào mọi start/end mà không overflow int, hai khoảng giao/không giao theo cùng quan hệ. Vì vậy số lượng khoảng tối ưu **không đổi**.

### 13.3. Scheduling: hoán vị input

Nếu chỉ yêu cầu số lượng tối đa, **đảo thứ tự danh sách input** không đổi optimum. Tuy nhiên danh sách nghiệm cụ thể có thể khác khi có nhiều nghiệm tối ưu và tie-break phụ thuộc thứ tự gốc.

### 13.4. Scheduling: thêm một khoảng

Thêm một khoảng mới không thể làm **giảm** số lượng tối ưu: mọi nghiệm cũ vẫn là phương án chọn hợp lệ trong tập mới.

Nếu optimum giảm sau khi thêm khoảng, gần như chắc chắn có lỗi (hoặc đã âm thầm đổi đặc tả/miền dữ liệu).

### 13.5. Giới hạn metamorphic testing

Một thuật toán sai vẫn có thể bảo toàn nhiều quan hệ biến hình. Vì vậy metamorphic tests là **lớp bổ sung**, không thay oracle và chứng minh thuật toán.

---

## 14. Những lỗi oracle phổ biến

### 14.1. Cùng mã xử lý logic trong cả hai lời giải

Nếu cả fast và brute đều gọi một helper `calcScore` có bug, chúng có thể cùng trả kết quả sai và vẫn "PASS".

Giảm dùng chung những phần chứa logic cốt lõi:

- Oracle tính score trực tiếp.
- Fast dùng cấu trúc tối ưu độc lập.
- Có expected thủ công cho một số ca.
- Có kiểm tra thuộc tính bổ sung.

### 14.2. Vét cạn không vét hết

Ví dụ duyệt `r<n-1` sẽ bỏ mọi đoạn kết thúc tại n−1. Hoặc duyệt subset mask từ 1 có thể bỏ tập rỗng, gây sai khi bài cho tập rỗng là nghiệm hợp lệ.

Trong bài scheduling, tập rỗng cần hợp lệ với score0.

### 14.3. Sai ranh giới nửa mở

Hai khoảng `[1,2)` và `[2,3)` **không chồng nhau**. Nếu oracle dùng điều kiện `end<start` thay vì `end<=start` thì cả oracle hoặc fast có thể sai.

### 14.4. Sai phép phá hòa

Nếu đề yêu cầu l nhỏ nhất rồi r nhỏ nhất, mà oracle ưu tiên đoạn ngắn nhất, mismatch có thể do **hai đặc tả khác nhau**.

### 14.5. Tràn số

Nếu cả fast và brute dùng `int` cho tổng n phần tử, chúng có thể cùng overflow và cho giá trị sai.

Mã Java trong bài dùng `long` với `Math.addExact`/`Math.subtractExact` để phát hiện overflow ở các phép tính cần thiết; oracle cũng có giới hạn kiểu số. Với input lớn vượt long, có thể dùng `BigInteger` cho phép đối chiếu độc lập.

### 14.6. Test chỉ sinh dữ liệu dễ

Sinh duy nhất giá trị dương sẽ bỏ sót lỗi max-subarray toàn âm. Sinh interval không có trường hợp chạm biên sẽ bỏ sót lỗi `<`/`<=`.

### 14.7. Test dừng quá sớm

Thấy 100 ca PASS rồi suy ra chứng minh đúng là sai. Một bộ test cần nhiều lớp và có báo cáo phạm vi.

---

## 15. Java 17+: hai bài toán, hai oracle, test tái lập

Tệp độc lập: **`BruteForceDifferentialDemo.java`**.

Chương trình cung cấp:

- `Best`: kết quả đoạn con (sum,left,right), đoạn không rỗng, tie-break rõ.
- `fastMaxSubarray`: prefix-min O(n), chọn l sớm nhất khi cùng min.
- `bruteMaxSubarray`: hai vòng l/r O(n²), không dựa vào prefix-min.
- `Interval`: khoảng thời gian nửa mở, tự kiểm tra `start<end`.
- `greedySchedule`: sort theo thời điểm kết thúc O(n log n).
- `bruteIntervalCount`: liệt kê mọi tập con, kiểm tra mọi cặp khoảng; giới hạn n≤20.
- `exhaustiveMaxTests`: kiểm tra tất cả **19.530 mảng** n=1..6 và giá trị −2..2.
- `randomMaxTests`: **10.000 mảng** được sinh bằng `SplittableRandom` có seed cố định.
- `randomIntervalTests`: **2.500 bộ khoảng** với n=0..10, bao gồm phần tử trùng/âm/chạm biên.
- Trường hợp all-negative, tie-break, khoảng rỗng và từ chối input ngoài miền.

**Đây là chương trình kiểm thử tính đúng**, không phải benchmark thời gian chạy tối ưu/vét cạn. Trên input lớn, không được chạy oracle brute scheduling có số tập con tăng theo cấp số nhân.

### 15.1. Mã nguồn đầy đủ

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.SplittableRandom;

public final class BruteForceDifferentialDemo {

    private static final long SEED = 20261110L;

    public record Best(long sum, int left, int right) {
    }

    // [start,end), end point excluded.
    public record Interval(int start, int end) {
        public Interval {
            if (start >= end) {
                throw new IllegalArgumentException(
                        "Expected start < end");
            }
        }
    }

    private static void requireNonempty(long[] a) {
        if (a == null || a.length == 0) {
            throw new IllegalArgumentException(
                    "Max-subarray input must be nonempty");
        }
    }

    // Tie rule: larger sum; then smaller left; then smaller right.
    private static boolean better(Best c, Best b) {
        return b == null
                || c.sum() > b.sum()
                || (c.sum() == b.sum()
                    && (c.left() < b.left()
                        || (c.left() == b.left()
                            && c.right() < b.right())));
    }

    // O(n) time, O(1) auxiliary memory.
    public static Best fastMaxSubarray(long[] a) {
        requireNonempty(a);

        long prefix = 0L;
        long minPrefix = 0L;
        int minIndex = 0;
        Best best = null;

        for (int r = 0; r < a.length; r++) {
            prefix = Math.addExact(prefix, a[r]);

            Best candidate = new Best(
                    Math.subtractExact(prefix, minPrefix),
                    minIndex, r);

            if (better(candidate, best)) {
                best = candidate;
            }

            // Only add P[r+1] AFTER evaluating ending at r.
            // Use <, not <=, to preserve earliest min index.
            if (prefix < minPrefix) {
                minPrefix = prefix;
                minIndex = r + 1;
            }
        }

        return best;
    }

    // Independent O(n^2) oracle: enumerate every [l,r].
    // Comparison intentionally written directly, not via better().
    public static Best bruteMaxSubarray(long[] a) {
        requireNonempty(a);

        Best best = null;

        for (int l = 0; l < a.length; l++) {
            long running = 0L;

            for (int r = l; r < a.length; r++) {
                running = Math.addExact(running, a[r]);

                if (best == null
                        || running > best.sum()
                        || (running == best.sum()
                            && (l < best.left()
                                || (l == best.left()
                                    && r < best.right())))) {

                    best = new Best(running, l, r);
                }
            }
        }

        return best;
    }

    private static void validateIntervals(Interval[] a) {
        if (a == null) {
            throw new IllegalArgumentException(
                    "Intervals must not be null");
        }

        for (Interval x : a) {
            if (x == null) {
                throw new IllegalArgumentException(
                        "Null interval");
            }
        }
    }

    // O(n log n) greedy algorithm for maximum cardinality.
    public static List<Interval> greedySchedule(
            Interval[] intervals) {

        validateIntervals(intervals);

        Interval[] sorted = intervals.clone();

        Arrays.sort(sorted,
                Comparator.comparingInt(Interval::end)
                        .thenComparingInt(Interval::start));

        List<Interval> chosen = new ArrayList<>();
        int lastEnd = Integer.MIN_VALUE;

        for (Interval x : sorted) {
            if (x.start() >= lastEnd) {
                chosen.add(x);
                lastEnd = x.end();
            }
        }

        return chosen;
    }

    // Independent oracle, up to 20 intervals:
    // enumerate all masks and check ALL selected pairs.
    public static int bruteIntervalCount(Interval[] a) {
        validateIntervals(a);

        if (a.length > 20) {
            throw new IllegalArgumentException(
                    "Brute oracle accepts at most 20 intervals");
        }

        int best = 0;
        int limit = 1 << a.length;

        for (int mask = 0; mask < limit; mask++) {
            int count = Integer.bitCount(mask);

            if (count <= best) {
                continue;
            }

            boolean feasible = true;

            for (int i = 0; i < a.length && feasible; i++) {
                if ((mask & (1 << i)) == 0) {
                    continue;
                }

                for (int j = i + 1; j < a.length; j++) {
                    if ((mask & (1 << j)) == 0) {
                        continue;
                    }

                    Interval x = a[i];
                    Interval y = a[j];

                    boolean disjoint =
                            x.end() <= y.start()
                            || y.end() <= x.start();

                    if (!disjoint) {
                        feasible = false;
                        break;
                    }
                }
            }

            if (feasible) {
                best = count;
            }
        }

        return best;
    }

    private static void verifyMax(long[] a, String context) {
        Best expected = bruteMaxSubarray(a);
        Best actual = fastMaxSubarray(a);

        if (!expected.equals(actual)) {
            throw new AssertionError(
                    context + " input=" + Arrays.toString(a)
                    + " expected=" + expected
                    + " actual=" + actual);
        }
    }

    private static void verifyIntervals(
            Interval[] a, String context) {

        int expected = bruteIntervalCount(a);
        List<Interval> actual = greedySchedule(a);

        // Verify the witness as well as its cardinality.
        for (int i = 0; i < actual.size(); i++) {
            for (int j = i + 1; j < actual.size(); j++) {
                Interval x = actual.get(i);
                Interval y = actual.get(j);

                if (!(x.end() <= y.start()
                        || y.end() <= x.start())) {
                    throw new AssertionError(
                            context + ": overlapping witness "
                            + actual);
                }
            }
        }

        if (expected != actual.size()) {
            throw new AssertionError(
                    context + " input=" + Arrays.toString(a)
                    + " expectedCount=" + expected
                    + " actualCount=" + actual.size()
                    + " chosen=" + actual);
        }
    }

    // All n=1..6 arrays over {-2,-1,0,1,2}.
    private static long exhaustiveMaxTests() {
        long checked = 0L;

        for (int n = 1; n <= 6; n++) {
            long combinations = 1L;

            for (int i = 0; i < n; i++) {
                combinations *= 5L;
            }

            for (long code = 0; code < combinations; code++) {
                long[] a = new long[n];
                long remainder = code;

                for (int i = 0; i < n; i++) {
                    a[i] = (remainder % 5L) - 2L;
                    remainder /= 5L;
                }

                verifyMax(a,
                        "exhaustive n=" + n + " code=" + code);
                checked++;
            }
        }

        return checked;
    }

    private static long randomMaxTests(
            SplittableRandom rng, int trials) {

        for (int trial = 0; trial < trials; trial++) {
            int n = rng.nextInt(1, 13);
            long[] a = new long[n];

            for (int i = 0; i < n; i++) {
                a[i] = rng.nextInt(-20, 21);
            }

            verifyMax(a,
                    "seed=" + SEED + " arrayTrial=" + trial);
        }

        return trials;
    }

    private static long randomIntervalTests(
            SplittableRandom rng, int trials) {

        for (int trial = 0; trial < trials; trial++) {
            int n = rng.nextInt(0, 11);
            Interval[] a = new Interval[n];

            for (int i = 0; i < n; i++) {
                int start = rng.nextInt(-5, 15);
                int end = start + rng.nextInt(1, 8);
                a[i] = new Interval(start, end);
            }

            verifyIntervals(a,
                    "seed=" + SEED + " intervalTrial=" + trial);
        }

        return trials;
    }

    private static String describe(Best best) {
        return "sum=" + best.sum()
                + " range=[" + best.left()
                + "," + best.right() + "]";
    }

    public static void main(String[] args) {
        long[] sample =
                {-2, 1, -3, 4, -1, 2, 1, -5, 4};

        System.out.println(
                "Max sample fast: "
                + describe(fastMaxSubarray(sample)));

        System.out.println(
                "Max sample brute: "
                + describe(bruteMaxSubarray(sample)));

        System.out.println(
                "All negative: "
                + describe(fastMaxSubarray(
                        new long[] {-4, -1, -7})));

        System.out.println(
                "Tie rule: "
                + describe(fastMaxSubarray(
                        new long[] {0, 0, 0})));

        Interval[] sampleIntervals = {
                new Interval(1, 4),
                new Interval(3, 5),
                new Interval(0, 6),
                new Interval(5, 7),
                new Interval(8, 9),
                new Interval(5, 9)
        };

        System.out.println(
                "Intervals greedy/brute: "
                + greedySchedule(sampleIntervals).size()
                + "/"
                + bruteIntervalCount(sampleIntervals));

        Interval[] badEarliestStart = {
                new Interval(0, 10),
                new Interval(1, 2),
                new Interval(2, 3),
                new Interval(3, 4)
        };

        System.out.println(
                "Earliest-finish optimum: "
                + bruteIntervalCount(badEarliestStart));

        System.out.println(
                "Exhaustive max arrays: "
                + exhaustiveMaxTests() + " PASS");

        SplittableRandom rng =
                new SplittableRandom(SEED);

        System.out.println(
                "Random max arrays: "
                + randomMaxTests(rng, 10_000) + " PASS");

        System.out.println(
                "Random interval sets: "
                + randomIntervalTests(rng, 2_500) + " PASS");

        System.out.println(
                "Empty interval optimum: "
                + bruteIntervalCount(new Interval[0]));

        boolean emptyMaxRejected = false;

        try {
            fastMaxSubarray(new long[0]);
        } catch (IllegalArgumentException ex) {
            emptyMaxRejected = true;
        }

        System.out.println(
                "Empty max rejected: " + emptyMaxRejected);

        boolean tooLargeRejected = false;

        try {
            bruteIntervalCount(new Interval[21]);
        } catch (IllegalArgumentException ex) {
            tooLargeRejected = true;
        }

        System.out.println(
                "Large oracle input rejected: "
                + tooLargeRejected);
    }
}
```

### 15.2. Cách biên dịch và chạy

Với **JDK 17+**:

```bash
javac BruteForceDifferentialDemo.java
java BruteForceDifferentialDemo
```

**Stdout kỳ vọng:**

```text
Max sample fast: sum=6 range=[3,6]
Max sample brute: sum=6 range=[3,6]
All negative: sum=-1 range=[1,1]
Tie rule: sum=0 range=[0,0]
Intervals greedy/brute: 3/3
Earliest-finish optimum: 3
Exhaustive max arrays: 19530 PASS
Random max arrays: 10000 PASS
Random interval sets: 2500 PASS
Empty interval optimum: 0
Empty max rejected: true
Large oracle input rejected: true
```

**Phạm vi cam kết:** stdout trên là các giá trị tất định khi chương trình chạy xong bình thường; nếu kiểm thử phát hiện mismatch, `AssertionError` sẽ làm chương trình dừng và in phản ví dụ thay vì in "PASS".

### 15.3. Vì sao mã Java độc lập?

Lớp public, các record, import và main nằm cùng một file. Không cần thư viện ngoài Java 17. Hai oracle nhận dữ liệu trực tiếp, không cần mạng, file input hoặc cấu hình hệ điều hành.

Các phép cộng và trừ liên quan tổng được kiểm tra bằng `Math.addExact` và `Math.subtractExact`. Điều kiện thí nghiệm dùng số nhỏ để không tràn long.

### 15.4. Oracle max không dùng chung thuật toán fast

`bruteMaxSubarray` liệt kê cặp l/r và tính running sum. Nó không hỏi `minPrefix` và không gọi `fastMaxSubarray`.

Phép so sánh tie-break được viết trực tiếp trong oracle, không gọi helper `better` mà fast sử dụng. Điều này giúp giảm rủi ro hai hàm cùng phụ thuộc vào một lỗi so sánh.

### 15.5. Oracle interval kiểm tra từng cặp

`bruteIntervalCount` không sort intervals theo end. Nó chọn các phần tử theo mask rồi kiểm tra từng cặp được chọn xem có rời nhau không.

Do đó nếu comparator `greedySchedule` bị sửa sai (ví dụ theo start), oracle vẫn là một tiêu chuẩn độc lập.

### 15.6. Vì sao có giới hạn n≤20?

Số subset là `2^n`. Với n=20:

\[
2^{20}=1\,048\,576.
\]

Với n=30:

\[
2^{30}\approx1.07\ \text{tỷ}.
\]

Không phù hợp cho test lặp nhanh. Hơn nữa mã dùng int mask; dịch `1<<n` ở n lớn có vấn đề giới hạn bit. Giới hạn n≤20 là **chính sách an toàn của oracle**, không phải giới hạn của thuật toán greedy tối ưu.

### 15.7. Vì sao test scheduling so count?

Đề mục 8 yêu cầu tối đa **số lượng**. Có thể có nhiều lịch tối ưu nên count là phần phải khớp. Mã còn kiểm tra rằng các khoảng greedy đã chọn **không chồng lấn**.

Nếu đề thực tế còn yêu cầu định dạng/lựa chọn danh sách cụ thể, hãy bổ sung kiểm tra witness/tie-break theo đúng đề ấy.

### 15.8. Vì sao mã không benchmark?

Các vòng 19.530 + 10.000 + 2.500 test có mục tiêu là tìm **mismatch**, không đo latency. Máy khác nhau có thời gian chạy khác, nhưng kết quả PASS/FAIL của các bộ kiểm thử hợp lệ vẫn phải phản ánh logic, không được kết luận tốc độ từ một lần chạy.

---

## 16. Những phép kiểm thử cần có ngoài random

### 16.1. Test mẫu do người tính tay

Với max-subarray:

| Input | Kết quả theo đặc tả |
| --- | --- |
| `[-7]` | sum=−7,[0,0] |
| `[0,0,0]` | sum=0,[0,0] |
| `[-4,-1,-7]` | sum=−1,[1,1] |
| `[2,-2,2]` | sum=2,[0,0] |
| `[1,2,3]` | sum=6,[0,2] |
| `[-2,1,-3,4,-1,2,1,-5,4]` | sum=6,[3,6] |

Các ca này có ý nghĩa riêng và không phụ thuộc vào generator.

### 16.2. Biên interval

| Input | Optimum |
| --- | ---: |
| Không có khoảng | 0 |
| Một khoảng [1,2) | 1 |
| [1,2),[2,3) | 2 |
| [1,3),[2,4) | 1 |
| [1,2),[1,2) | 1 |
| [0,10),[1,2),[2,3),[3,4) | 3 |

### 16.3. Kiểm tra giới hạn số

Với long, nên có chính sách:

- Nếu đề bảo đảm tổng luôn trong long, dùng long.
- Nếu có thể vượt long, dùng `BigInteger` trong cài đặt cần chính xác.
- Nếu đầu vào trái giới hạn, ném exception rõ.

Đừng lấy việc fast/brute cùng tràn int thành bằng chứng đúng.

### 16.4. Tính độc lập của dữ liệu

Oracle và fast nên nhận **bản sao input** nếu một trong hai có thể sửa dữ liệu tại chỗ:

```java
Result fast = fastSolve(input.clone());
Result brute = bruteSolve(input.clone());
```

Nếu chạy fast làm thay đổi mảng rồi brute dùng chính mảng đã đổi, phép so sánh không còn trên cùng input ban đầu.

Trong mã minh họa, hai hàm max-subarray chỉ đọc `long[]`; greedy clone mảng interval trước khi sort, nên không sửa thứ tự input.

### 16.5. Kiểm tra determinism

Hai lần chạy cùng input/seed cần cho cùng kết quả nếu thuật toán được thiết kế deterministic. Với thuật toán có nhiều nghiệm tối ưu được chấp nhận, phải xác định có cần cùng witness hay chỉ cùng score.

---

## 17. Công thức độ phức tạp và ngân sách test

### 17.1. Bài đoạn con tổng lớn nhất

Với n:

\[
T_{\text{brute}}(n)=\Theta(n^2),
\]

\[
T_{\text{fast}}(n)=\Theta(n).
\]

Cho n=12, chỉ có:

\[
12\cdot13/2=78
\]

đoạn con, rất nhỏ cho một test.

Cho n=100000, số đoạn:

\[
100000\cdot100001/2=5\,000\,050\,000,
\]

quá nhiều nếu mỗi test đều xét hết.

### 17.2. Bài chọn khoảng

Với n khoảng:

\[
T_{\text{brute}}(n)=O(2^n n^2),
\]

\[
T_{\text{greedy}}(n)=O(n\log n).
\]

Với n=10, `2^{10}=1024` subset, có thể kiểm tra nhiều lần.

Với n=20, `2^{20}=1048576` subset, đã khá lớn. Với n=30, sẽ rất đắt.

### 17.3. Chọn ngân sách test

Một bộ test thực tế có thể chia:

- **Unit cases thủ công:** rất ít nhưng mạnh về lỗi biên.
- **Exhaustive tiny:** đủ để chứng minh trên một miền hữu hạn nhỏ.
- **Random differential:** nhiều ca đa dạng hơn.
- **Metamorphic:** kiểm tra thêm quan hệ mà không cần oracle.
- **Regression:** luôn giữ phản ví dụ đã tìm thấy.
- **Performance:** riêng biệt, dùng input lớn nhưng không bắt brute chạy.

Không nhất thiết phải sinh hàng triệu input nếu mỗi oracle dùng O(2^n) với n lớn; quan trọng là **phân phối test và tổng ngân sách phù hợp**.

---

## 18. Phân tích một mismatch đúng cách

Giả sử log:

```text
seed=20261110
trial=237
input=[0,0,0]
expected=sum=0 left=0 right=0
actual=sum=0 left=2 right=2
```

Cần làm:

1. Kiểm tra đặc tả tie-break: l nhỏ nhất rồi r nhỏ nhất.
2. Kiểm tra oracle có bao phủ mọi đoạn và tie-break đúng.
3. Kiểm tra fast giữ chỉ số sớm nhất khi minPrefix bằng nhau chưa.
4. Xem có dùng `<=` thay cho `<` khi cập nhật minPrefix không.
5. Thu nhỏ input, có thể `[0,0]` đã đủ gây lỗi.
6. Viết regression với expected cho `[0,0]`.
7. Sửa thuật toán, chạy lại toàn bộ test.

Không nên chỉ đổi expected theo actual để "xanh" CI mà không xác định logic.

### 18.1. Phân loại lỗi

| Triệu chứng | Nghi vấn |
| --- | --- |
| Fast sai tổng, brute đúng | Sai trạng thái, chuyển, chỉ số, overflow |
| Tổng bằng nhưng index khác | Tie-break hoặc hai nghiệm đều hợp lệ |
| Witness không hợp lệ | Kiểm tra ràng buộc trong thuật toán |
| Mismatch chỉ ở n=0/1 | Khởi tạo, đoạn rỗng, biên |
| Mismatch ở giá trị lớn | Overflow hoặc so sánh |
| Mismatch sau khi sort | Comparator, sửa input gốc |
| Mismatch chỉ khi trùng | Quy tắc strict/non-strict, tie-break |
| Random pass nhưng hand case fail | Generator chưa bao phủ cấu trúc quan trọng |

### 18.2. Cần sửa oracle khi nào?

Nếu phân tích toán học cho thấy oracle thiếu phương án hoặc tính score sai, oracle phải được sửa. Hãy giữ một vài đáp án tính tay để kiểm tra cả oracle.

Đừng mặc định **fast luôn sai** khi có mismatch: đôi khi oracle mới là nguyên nhân.

### 18.3. Mismatch do khác định nghĩa

Ví dụ bài chọn khoảng dùng [start,end) còn một cài đặt dùng [start,end] sẽ khác ở hai khoảng chạm biên. Lúc ấy cần thống nhất đề trước khi sửa code.

---

## 19. Khi nào không nên dùng oracle brute?

### 19.1. Input lớn

Nếu brute có O(n!) hay O(2^n), không dùng nó cho n lớn. Chia test thành vùng n nhỏ có oracle và vùng n lớn có invariant/metamorphic/benchmark.

### 19.2. Kết quả không xác định duy nhất

Nếu đề cho phép nhiều nghiệm, chỉ so output như chuỗi có thể tạo lỗi giả (*false positive*). Kiểm tra tính hợp lệ và mục tiêu tối ưu thay vì đòi witness giống tuyệt đối.

### 19.3. Input khó biểu diễn

Một số vấn đề có dữ liệu đầu vào rất lớn hoặc dữ liệu bên ngoài; không thể đơn giản vét cạn toàn bộ. Hãy xây mô hình nhỏ, trừu tượng hóa điều kiện cốt lõi và oracle theo mô hình ấy.

### 19.4. Bài có xác suất

Với thuật toán ngẫu nhiên, không phải mọi lần chạy đều có cùng witness. Có thể kiểm tra phân phối, xác suất lỗi hoặc quy định seed, tùy đặc tả. Không ép so bit từng run nếu output hợp lệ có nhiều lựa chọn.

### 19.5. Bài có thời gian thực/concurrency

Một oracle tuần tự có thể kiểm tra **giá trị cuối** nhưng không chứng minh hệ thống không có race, deadlock hoặc vi phạm linearizability. Cần thêm test lập lịch, phân tích happens-before hoặc model checking phù hợp.

---

## 20. Các phương pháp bổ trợ

### 20.1. Assertions và invariant

Ví dụ:

```java
assert left >= 0;
assert right < n;
assert left <= right;
```

Assertions có thể bị tắt tùy cấu hình JVM, nên với điều kiện input cần được kiểm tra trong production, dùng exception rõ ràng thay vì dựa hoàn toàn vào `assert`.

### 20.2. Property-based testing

Sinh input có cấu trúc và kiểm tra nhiều tính chất:

- Kết quả là nghiệm hợp lệ.
- Giá trị không tệ hơn một phương án cơ sở.
- Kết quả không đổi dưới phép biến đổi bảo toàn bài toán.
- Cấu trúc dữ liệu giữ invariant sau mỗi thao tác.

Thư viện property-based testing có thể tự shrink; tuy nhiên người học vẫn cần hiểu vì sao quan hệ được kiểm tra là đúng.

### 20.3. Model checking nhỏ

Với các hệ hữu hạn ít trạng thái, có thể duyệt các trạng thái và chuyển tiếp, hoặc các lịch xen kẽ hợp lệ. Khác với vét cạn phương án của bài toán tối ưu, model checking thường tập trung vào **tính an toàn và trạng thái** của một hệ thống.

### 20.4. Sanitizers và các công cụ bổ trợ

Với ngôn ngữ phù hợp, static analyzer và sanitizer giúp phát hiện lỗi bộ nhớ/undefined behavior. Với Java, lỗi out-of-bounds thường ném exception thay vì âm thầm ghi qua bộ nhớ, nhưng vẫn có thể có race condition, lỗi logic và resource leak.

Các công cụ đó **bổ sung**, không thay chứng minh tính đúng hay oracle.

---

## 21. Danh sách lỗi thường gặp

1. **Viết fast trước rồi dùng chính fast làm expected.**
2. **Sao chép cùng logic giữa fast và oracle**, khiến lỗi chung không bị phát hiện.
3. **Không định nghĩa output khi nhiều nghiệm tối ưu**, so witness sai.
4. **Chỉ so score nhưng quên kiểm tra witness hợp lệ.**
5. **Dùng số lớn làm brute quá chậm**, không giới hạn n.
6. **Không tính 2^n/n! trước khi đặt số test.**
7. **Vét cạn thiếu mask0**, sai với bài cho nghiệm rỗng.
8. **Vét cạn thiếu l=r**, bỏ đoạn một phần tử.
9. **Vét cạn thiếu r=n−1**, bỏ đoạn kết thúc cuối.
10. **Cho phép đoạn rỗng ở max-subarray**, sai nếu đề yêu cầu không rỗng.
11. **Khởi tạo best=0 cho mảng toàn âm.**
12. **Dùng minPrefix cập nhật trước khi xét ứng viên**, tạo đoạn rỗng.
13. **Dùng <= thay < khi chọn minPrefix**, phá tie-break sớm nhất.
14. **So sánh int trong tổng lớn**, bị overflow.
15. **Tin rằng hai chương trình cùng overflow thì kết quả đúng.**
16. **Dùng Comparator trả a.end-b.end**, có thể overflow int; nên dùng comparingInt/Integer.compare.
17. **Nhầm [start,end) với [start,end]**, xử lý khoảng chạm biên sai.
18. **Dùng greedy earliest start cho interval scheduling**, có phản ví dụ.
19. **Dùng greedy earliest finish cho weighted intervals**, có thể sai.
20. **Sort input tại chỗ rồi cho oracle nhận input đã đổi**, giảm tính độc lập.
21. **Random chỉ sinh toàn số dương**, không test toàn âm.
22. **Random không sinh số trùng**, bỏ bug tie-break.
23. **Random không sinh n=0,1**, bỏ lỗi khởi tạo/biên.
24. **Không dùng seed cố định**, khó tái hiện lỗi.
25. **Chỉ lưu seed không lưu input**, generator thay đổi làm mất phản ví dụ.
26. **Đang có mismatch nhưng vẫn in PASS**, báo cáo giả.
27. **Thu nhỏ phản ví dụ làm input không hợp lệ**, dẫn đến kết luận sai.
28. **Shrinker chỉ so score, mất lỗi tie-break.**
29. **Mặc định fast sai khi mismatch**, dù oracle có thể sai.
30. **Sửa expected theo actual mà không giải thích**, che lỗi.
31. **Chỉ so kết quả ở cuối nhiều thao tác cập nhật**, bỏ lỗi tạm thời ở giữa.
32. **Với graph path, chỉ so khoảng cách mà không xác minh đường đi.**
33. **Với matching, chỉ so số cặp mà không kiểm tra đỉnh trùng.**
34. **Với MST, chỉ so trọng số mà không kiểm tra tính chất cây.**
35. **Với floating point, so bằng bit bất chấp sai số do thứ tự cộng.**
36. **Dùng metamorphic relation sai**, như nhân c âm rồi mong nguyên nghiệm max-subarray.
37. **Tin rằng metamorphic PASS thay được oracle và chứng minh.**
38. **Chỉ test P=1 với thuật toán song song rồi kết luận không có race.**
39. **Đo tốc độ của brute rồi cho đó là kiểm thử tính đúng.**
40. **Không giữ regression sau khi sửa bug**, lỗi tái diễn.
41. **Thiếu kiểm tra null/empty và giới hạn n**, lỗi khó hiểu.
42. **Sinh dữ liệu ngoài ràng buộc rồi chê thuật toán sai**, sai phạm vi test.
43. **Không phân biệt số ca test với số phương án được oracle xét**, đánh giá chi phí sai.
44. **Tuyên bố test hữu hạn chứng minh đúng cho mọi input**, vượt giới hạn bằng chứng.
45. **Không ghi rõ phiên bản đặc tả và quy tắc tie-break**, test lâu dài mất nhất quán.

---

## 22. Bài tập tự kiểm tra

### Bài 1
Vì sao một thuật toán O(n) vẫn cần kiểm thử với oracle O(n²)?

### Bài 2
Định nghĩa brute-force oracle.

### Bài 3
Điều gì khiến hai cài đặt có thể cùng sai dù kết quả khớp?

### Bài 4
Phân biệt giá trị tối ưu và nghiệm đạt tối ưu.

### Bài 5
Với max-subarray, tại sao phải định nghĩa rõ có cho đoạn rỗng hay không?

### Bài 6
Theo đặc tả bài này, nếu hai đoạn có cùng tổng, chọn đoạn nào?

### Bài 7
Với a=[-4,-1,-7], đáp án là gì?

### Bài 8
Với a=[0,0,0], đáp án là gì?

### Bài 9
Với a=[2,-2,2], quy tắc tie-break chọn đoạn nào?

### Bài 10
Với n phần tử, có bao nhiêu đoạn [l,r] không rỗng?

### Bài 11
Tại sao vòng l/r với running sum có O(n²), không phải O(n³)?

### Bài 12
Viết công thức tổng đoạn từ prefix.

### Bài 13
Với một r cố định, tìm tổng đoạn lớn nhất bằng min prefix thế nào?

### Bài 14
Tại sao cập nhật minPrefix sau khi xét candidate?

### Bài 15
Tại sao dùng dấu < chứ không dùng <= khi cập nhật minPrefix?

### Bài 16
Độ phức tạp của fast max-subarray và brute max-subarray?

### Bài 17
Với n=1..6 và 5 giá trị mỗi phần tử, tổng số mảng là bao nhiêu?

### Bài 18
Tại sao exhaustive tiny không phải chứng minh cho mọi n?

### Bài 19
Seed có lợi gì trong differential fuzzing?

### Bài 20
Tại sao phải lưu input khi thấy mismatch?

### Bài 21
Cho hai khoảng [1,2) và [2,3). Chúng có tương thích không?

### Bài 22
Greedy chọn khoảng không giao nhau nhiều nhất nên sort theo yếu tố gì?

### Bài 23
Cho phản ví dụ greedy "bắt đầu sớm nhất" sai.

### Bài 24
Oracle interval scheduling liệt kê những gì?

### Bài 25
Vì sao oracle interval kiểm tra từng cặp là độc lập với greedy sort theo end?

### Bài 26
Với n=10, oracle có tối đa bao nhiêu mask?

### Bài 27
Với n=20, có bao nhiêu subset?

### Bài 28
Nếu đề chỉ yêu cầu số khoảng tối đa, có nên so nguyên danh sách greedy với danh sách oracle không?

### Bài 29
Nếu phải trả danh sách, cần kiểm tra thêm gì ngoài kích thước?

### Bài 30
Greedy earliest-finish có tự đúng cho weighted interval scheduling không?

### Bài 31
Shrinking có mục đích gì?

### Bài 32
Khi shrink một khoảng, cần giữ điều kiện hợp lệ nào?

### Bài 33
Nêu metamorphic relation đúng cho max-subarray khi nhân c>0.

### Bài 34
Nêu metamorphic relation cho interval scheduling khi tịnh tiến thời gian.

### Bài 35
Thêm một khoảng vào tập có thể làm optimum giảm không?

### Bài 36
Vì sao metamorphic PASS không chứng minh thuật toán đúng?

### Bài 37
Nếu hai lời giải cùng tràn int, đối chiếu có thể báo PASS giả không?

### Bài 38
Vì sao cần test toàn âm, tất cả 0 và các giá trị trùng?

### Bài 39
Với thuật toán đồ thị trả đường đi, vì sao so độ dài chưa đủ?

### Bài 40
Phân biệt oracle test và performance benchmark.

### Bài 41
Nếu hiện mismatch, ba thông tin nào tối thiểu nên in?

### Bài 42
Khi nào nên thêm ca vào regression suite?

### Bài 43
Tại sao một oracle có thể cần n≤20 dù greedy chạy được n lớn?

### Bài 44
Bài toán cho phép nhiều nghiệm tối ưu nhưng không có tie-break. Hãy thiết kế phép so sánh phù hợp.

### Bài 45
Sau 10.000 test random đều đúng, có được kết luận thuật toán đúng với mọi input không?

### Đáp án gợi ý

1. Độ phức tạp là chi phí, không chứng minh cài đặt không mắc lỗi logic/biên/tie-break.
2. Cài đặt đơn giản liệt kê đầy đủ phương án trong miền nhỏ, dùng làm expected.
3. Cùng dùng helper hoặc giả định sai; cùng lỗi tràn số; cùng đặc tả sai.
4. Giá trị tối ưu là score; nghiệm phải thỏa ràng buộc và đạt score ấy.
5. Toàn âm sẽ khác: nếu cho rỗng có thể nhận 0, nếu không phải chọn phần tử lớn nhất.
6. Ưu tiên tổng lớn, tiếp đó l nhỏ nhất, rồi r nhỏ nhất.
7. Sum−1, đoạn [1,1].
8. Sum0, đoạn [0,0].
9. Sum2, đoạn [0,0].
10. `n(n+1)/2`.
11. Mỗi r mở rộng chỉ thêm a[r] một lần, không quét lại đoạn.
12. `P[r+1]-P[l]`.
13. `P[r+1]-min(P[0..r])`.
14. Để minPrefix không bao gồm P[r+1], tránh ứng viên đoạn rỗng.
15. Giữ chỉ số l sớm nhất khi nhiều prefix bằng nhau.
16. O(n) và O(n²), cùng bộ nhớ phụ O(1).
17. 19.530.
18. Chỉ bao phủ tập n/giá trị nhỏ đã chọn.
19. Tái hiện thứ tự sinh ca để debug/regression.
20. Generator có thể đổi; input cụ thể là phản ví dụ trực tiếp.
21. Có, hai khoảng nửa mở chỉ chạm tại biên.
22. Thời điểm kết thúc tăng dần.
23. [0,10),[1,2),[2,3),[3,4): earliest start được1, tối ưu3.
24. Mọi tập con qua bitmask và kiểm tra từng cặp tương thích.
25. Vì không dùng comparator/quy tắc greedy để quyết định tính hợp lệ.
26. `2^{10}=1024`.
27. `2^{20}=1048576`.
28. Không; so số lượng và tính hợp lệ vì có thể nhiều lịch tối ưu.
29. Các khoảng thuộc input, không lặp sai, đôi một không chồng lấn, số lượng tối ưu.
30. Không; phải xét tổng trọng số, thường dùng DP.
31. Tìm phản ví dụ ngắn và dễ hiểu hơn mà vẫn còn mismatch.
32. `start<end` và mọi ràng buộc input khác.
33. Nhân c dương giữ đoạn tối ưu và nhân tổng với c nếu không overflow.
34. Cộng một hằng k vào mọi start/end giữ optimum.
35. Không, vì mọi nghiệm cũ vẫn hợp lệ trong tập mới.
36. Thuật toán sai vẫn có thể giữ một số quan hệ biến hình.
37. Có, cả hai có thể cùng sai do cùng kiểu dữ liệu.
38. Chúng chạm các nhánh khởi tạo, strict comparison và tie-break.
39. Đường đi có thể không dùng cạnh hợp lệ hoặc không tới đúng đích.
40. Oracle kiểm tra đáp án; benchmark đo thời gian/tài nguyên.
41. Input, expected, actual; nên kèm seed/trial.
42. Ngay sau khi tìm và xác minh nguyên nhân, nhất là với input đã shrink.
43. Số phương án oracle tăng theo `2^n`; greedy chỉ O(n log n).
44. Kiểm tra witness hợp lệ và score=optimum, không bắt hai witness giống nhau.
45. Không; cần chứng minh tính đúng và kiểm thử thêm trường hợp ngoài phân phối đã sinh.

---

## Ghi nhớ

**Đối chiếu lời giải tối ưu với vét cạn** là một kỹ thuật phát hiện lỗi rất hiệu quả khi có thể tạo input nhỏ.

Công thức:

\[
\boxed{
\text{Input nhỏ}
\to
(\text{oracle độc lập},\ \text{thuật toán tối ưu})
\to
\text{so sánh theo đặc tả}
}
\]

Với **đoạn con tổng lớn nhất**:

- Oracle liệt kê tất cả [l,r]: O(n²).
- Lời giải prefix min/Kadane: O(n).
- Phải so cả tổng và chỉ số theo tie-break nếu đề yêu cầu.

Với **chọn khoảng không giao nhau nhiều nhất**:

- Oracle liệt kê tập con và kiểm tra mọi cặp: O(2^n n²).
- Greedy kết thúc sớm nhất: O(n log n).
- Phải so optimum và tính hợp lệ của lịch; có thể có nhiều nghiệm tối ưu.

Sử dụng **expected thủ công + exhaustive tiny + random có seed + shrinking + metamorphic + regression**. Không sử dụng một bộ test hữu hạn làm chứng minh phổ quát, không lấy tốc độ làm bằng chứng tính đúng và không để fast/oracle chia sẻ cùng một lỗi cốt lõi.

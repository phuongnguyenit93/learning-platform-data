# Hàm tiền tố và thuật toán KMP

## 1. Bài toán tìm kiếm chuỗi và ý tưởng cốt lõi

Cho một **chuỗi văn bản** `T` dài `n` và một **chuỗi mẫu** (*pattern*) `P` dài `m`. Ta cần tìm mọi vị trí `s` sao cho:

\[
T[s..s+m-1]=P[0..m-1].
\]

Ví dụ:

```text
T = "bananana"
P = "ana"

Các vị trí xuất hiện theo chỉ số bắt đầu từ 0: 1, 3, 5.
```

Những lần xuất hiện **có thể chồng lấn** nhau. Trong ví dụ trên, hai lần xuất hiện `ana` tại `1` và `3` cùng dùng một số ký tự của văn bản.

Cách trực tiếp thử mọi điểm bắt đầu rồi so từng ký tự có thời gian **`O(nm)` trong trường hợp xấu**. Đặc biệt với văn bản và mẫu có rất nhiều ký tự giống nhau, phép so sánh có thể lặp lại nhiều lần sau khi vừa gần khớp hết mẫu.

**KMP (Knuth–Morris–Pratt)** cải thiện điều này bằng một kiến thức quan trọng về **chính chuỗi mẫu**: phần đầu nào của mẫu cũng đồng thời là phần cuối của đoạn đã khớp. Kiến thức đó được lưu trong **hàm tiền tố `pi[]` (prefix function)**.

Nhờ hàm tiền tố, khi so sánh không khớp, KMP **không cần lùi chỉ số của văn bản**. Nó chỉ đổi độ dài phần tiền tố của mẫu đang khớp, giữ lại thông tin chắc chắn vẫn đúng. Kết quả:

\[
\boxed{\text{Tiền xử lý mẫu }O(m),\quad
\text{tìm kiếm }O(n),\quad
\text{tổng }O(n+m).}
\]

Bài học giải thích định nghĩa border và hàm tiền tố, công thức `pi[j-1]`, chứng minh thời gian tuyến tính, cách dùng KMP để tìm tất cả lần xuất hiện kể cả chồng lấn, các trường hợp mẫu rỗng và Unicode, tìm kiếm theo luồng nhiều khối (*streaming*), chương trình **Java 17+ chạy độc lập**, các lỗi thường gặp và kiểm thử bằng phương pháp độc lập.

## 2. Tiền tố, hậu tố và border

Với chuỗi `S` dài `L`:

- **Tiền tố (prefix)** độ dài `k` là `S[0..k-1]`.
- **Hậu tố (suffix)** độ dài `k` là `S[L-k..L-1]`.
- **Tiền tố thực sự (proper prefix)** có độ dài **nhỏ hơn `L`**; tức không phải cả chuỗi.
- **Hậu tố thực sự (proper suffix)** tương tự, không được là cả chuỗi.
- **Border** là một chuỗi vừa là **tiền tố thực sự**, vừa là **hậu tố thực sự** của `S`.

Border có thể dài `0` (chuỗi rỗng), nhưng **không** được dài bằng toàn bộ `S`.

### 2.1. Ví dụ border

```text
S = "ababa"

Prefix dài 1: "a"
Prefix dài 2: "ab"
Prefix dài 3: "aba"
Prefix dài 4: "abab"

Suffix dài 1: "a"
Suffix dài 2: "ba"
Suffix dài 3: "aba"
Suffix dài 4: "baba"

Các border không rỗng: "a", "aba".
Border dài nhất: "aba", độ dài 3.
```

Do đó, nếu xét toàn bộ `ababa`, border dài nhất có độ dài `3`, không phải `5`.

### 2.2. Vì sao border giúp khi so sánh thất bại?

Giả sử khi tìm kiếm, ta đã khớp `j` ký tự đầu tiên của `P` với hậu tố vừa đọc của văn bản:

\[
T[i-j..i-1]=P[0..j-1].
\]

Khi ký tự tiếp theo `T[i]` không bằng `P[j]`, phần dài `j` vừa khớp không thể tiếp tục. Nhưng một **hậu tố** của đoạn vừa khớp có thể đồng thời là một **tiền tố ngắn hơn** của `P`.

Nếu `k` là độ dài border dài nhất của `P[0..j-1]`, ta có:

\[
P[0..k-1]=P[j-k..j-1].
\]

Vì đoạn dài `j` vừa khớp với văn bản, hậu tố dài `k` của nó cũng khớp với tiền tố dài `k` của mẫu. Vậy ta có thể đặt:

\[
j\gets k
\]

mà không cần đọc lại các ký tự đã duyệt trong văn bản.

Hàm tiền tố cho chính giá trị `k` này bằng:

\[
\boxed{k=pi[j-1].}
\]

**Cần nhớ:** `j` là **số ký tự mẫu đang khớp**, không phải chỉ số ký tự cuối. Do đó phải truy cập `pi[j-1]`, không phải `pi[j]`.

## 3. Định nghĩa hàm tiền tố pi[]

Cho mẫu `P` dài `m`. Với mỗi vị trí `i`, `pi[i]` là **độ dài border dài nhất** của đoạn:

\[
P[0..i].
\]

Nói chính xác:

\[
\boxed{
pi[i]=\max\bigl\{
k:0\le k<i+1,\;
P[0..k-1]=P[i-k+1..i]
\bigr\}.
}
\]

Nếu không tồn tại border không rỗng, `pi[i]=0`.

Các tính chất cơ bản:

1. `pi[0]=0`: đoạn dài `1` không có border không rỗng.
2. `0\le pi[i]\le i`: border luôn **ngắn hơn** đoạn dài `i+1`.
3. `pi[i]` chỉ phụ thuộc vào ký tự `P[0..i]`.
4. Các border có độ dài dương của `P[0..i]` có thể được truy theo một chuỗi **failure links**:
   `pi[i]`, `pi[pi[i]-1]`, ... cho tới `0`.

### 3.1. Ví dụ kinh điển: P = "ababaca"

Chỉ số mẫu bắt đầu từ `0`:

| `i` | `P[i]` | `P[0..i]` | Border dài nhất | `pi[i]` |
|---:|:---:|---|---|---:|
| 0 | a | a | rỗng | 0 |
| 1 | b | ab | rỗng | 0 |
| 2 | a | aba | a | 1 |
| 3 | b | abab | ab | 2 |
| 4 | a | ababa | aba | 3 |
| 5 | c | ababac | rỗng | 0 |
| 6 | a | ababaca | a | 1 |

Kết quả:

```text
P  = a b a b a c a
i  = 0 1 2 3 4 5 6
pi = 0 0 1 2 3 0 1
```

Hoặc ở dạng mảng:

\[
\boxed{pi=[0,0,1,2,3,0,1].}
\]

### 3.2. Ví dụ ký tự lặp

```text
P = "aaaa"

i  = 0 1 2 3
pi = 0 1 2 3
```

Với đoạn `aaaa`, tiền tố và hậu tố dài nhất đều là `aaa`, nên `pi[3]=3`.

Trường hợp lặp ký tự quan trọng vì nó tạo nhiều border và là một trong những mẫu có thể khiến tìm kiếm trực tiếp lặp lại rất nhiều phép so sánh.

### 3.3. Ví dụ có nhiều lần lùi

```text
P  = "aabaaab"
pi = [0, 1, 0, 1, 2, 2, 3]
```

Đoạn đầu `aa` có border `a`. Ở một số vị trí, border dài nhất thất bại nhưng border ngắn hơn vẫn còn khả năng; vì thế **không được luôn đưa j về 0 ngay khi có một lần so sánh không bằng nhau**.

## 4. Cách tính pi[] trong thời gian tuyến tính

Ý tưởng: đã biết `pi[0..i-1]`, muốn tính `pi[i]`.

Đặt:

\[
j=pi[i-1].
\]

`j` là độ dài border dài nhất của đoạn kết thúc ở `i-1`. Ta thử mở rộng border đó bằng ký tự mới `P[i]`.

Nếu:

\[
P[i]=P[j],
\]

thì border dài thêm một ký tự:

\[
j\gets j+1.
\]

Nếu không bằng nhau, border dài `j` không thể mở rộng. Ta thử border thực sự ngắn hơn tiếp theo:

\[
j\gets pi[j-1],
\]

và lặp cho đến khi có thể mở rộng hoặc `j=0`.

Pseudocode:

```text
pi[0] = 0

for i = 1 .. m-1:
    j = pi[i-1]

    while j > 0 and P[i] != P[j]:
        j = pi[j-1]

    if P[i] == P[j]:
        j = j + 1

    pi[i] = j
```

Với mẫu rỗng `m=0`, hàm tiền tố trả mảng rỗng, vòng lặp không chạy; code mẫu xử lý riêng trường hợp này một cách tự nhiên.

### 4.1. Tại sao bắt đầu từ pi[i-1]?

Giả sử đoạn `P[0..i-1]` có border dài nhất `j`. Muốn có border của đoạn mới `P[0..i]` dài `k>0`, hai phần dài `k-1` trước ký tự cuối phải là border của đoạn cũ.

Vì vậy, các ứng viên `k` chỉ có thể đến từ những border của đoạn cũ rồi **tăng thêm một ký tự**. Độ dài border dài nhất cũ `pi[i-1]` là ứng viên lớn nhất hợp lý để thử trước.

### 4.2. Tại sao khi thất bại lại về pi[j-1]?

Ta đang thử border độ dài `j` của đoạn cũ. Nếu ký tự mới không thể mở rộng border này, một border ngắn hơn `k<j` vẫn có thể mở rộng.

Vì bản thân đoạn dài `j` đang là **tiền tố của mẫu**, mọi border ngắn hơn phù hợp với đoạn cũ phải nằm trong chuỗi border của `P[0..j-1]`. Border dài nhất ngắn hơn `j` chính là:

\[
pi[j-1].
\]

Đó là **lựa chọn ngắn hơn lớn nhất chưa loại**. Nếu nó cũng thất bại, tiếp tục:

\[
j\gets pi[j-1]
\]

trên giá trị `j` mới.

Không cần so từ đầu mọi độ dài `j-1,j-2,\ldots`: rất nhiều độ dài chưa từng là border và chắc chắn không thể là ứng viên.

### 4.3. Truy vết vị trí i=5 của "ababaca"

Trước khi đọc ký tự `c` tại `i=5`:

\[
j=pi[4]=3.
\]

Thử:

```text
P[5] = 'c'
P[3] = 'b'     mismatch
j = pi[2] = 1

P[5] = 'c'
P[1] = 'b'     mismatch
j = pi[0] = 0

P[5] = 'c'
P[0] = 'a'     mismatch

pi[5] = 0
```

Đến `i=6`, `P[6]='a'` và `P[0]='a'`, nên `pi[6]=1`.

### 4.4. Hai lỗi chỉ số đặc biệt nguy hiểm

Sai:

```java
j = pi[j];     // sai: j là độ dài, không phải vị trí cuối
```

Đúng:

```java
j = pi[j - 1]; // chỉ khi j > 0
```

Sai khác:

```java
while (P.charAt(i) != P.charAt(j)) {
    j = pi[j - 1]; // có thể truy cập pi[-1] nếu j==0
}
```

Đúng: vòng `while` phải có điều kiện `j>0`. Sau khi thoát, mới so `P[i]` với `P[j]` để có thể tăng `j` lên `1` nếu ký tự đầu mẫu phù hợp.

## 5. Chứng minh công thức pi[] và độ phức tạp O(m)

### 5.1. Tính đúng

Giả sử các giá trị `pi[0..i-1]` đã đúng. Ta cần tìm border dài nhất của `P[0..i]`.

Một border dương độ dài `k` của đoạn mới phải thỏa:

\[
P[0..k-2]=P[i-k+1..i-1],
\]

và:

\[
P[k-1]=P[i].
\]

Phần đầu là điều kiện `k-1` là border của đoạn cũ `P[0..i-1]`. Ta xem các border của đoạn cũ theo thứ tự giảm dần, bắt đầu `j=pi[i-1]` rồi đi qua các failure links `j=pi[j-1]`.

Ứng viên đầu tiên có `P[i]=P[j]` cho border mới dài `j+1`, và do đang xét từ lớn xuống nhỏ, đó là border **dài nhất**. Nếu mọi ứng viên đều không mở rộng được, đáp án bằng `0`.

Điều này chứng minh phép tính `pi[i]` đúng theo quy nạp.

### 5.2. Vì sao while lồng trong for vẫn O(m)?

Nhìn vào mã có `for` bên ngoài và `while` bên trong, có thể nhầm là `O(m^2)`. Nhưng biến `j` có hai kiểu thay đổi:

- Khi mở rộng thành công, `j` **tăng đúng 1**.
- Khi thất bại, `j` được gán `pi[j-1]<j`, nên **giảm ít nhất 1**.

Qua toàn bộ quá trình, số lần tăng đơn vị tối đa `m-1`. Giá trị `j` không âm, nên tổng lượng giảm không thể vượt tổng lượng đã tăng cộng một lượng hằng. Mỗi vòng while giảm `j` ít nhất `1`; do đó tổng số lần thực hiện while trên **mọi `i` cộng lại** là `O(m)`.

Các phép còn lại mỗi vòng for là hằng số. Suy ra:

\[
\boxed{\text{Tính prefix function: }O(m)\text{ thời gian và }O(m)\text{ bộ nhớ}.}
\]

Đây là phân tích **khấu hao (amortized analysis)**. Một lần tính `pi[i]` riêng lẻ có thể lùi qua nhiều border, nhưng toàn bộ dãy không lùi quá nhiều lần.

## 6. KMP: dùng pi[] để tìm tất cả lần xuất hiện

Sau khi đã có `pi[]` của mẫu `P`, duyệt văn bản `T` từ trái sang phải **chỉ một lượt**.

Đặt `j` là số ký tự đầu mẫu đã khớp với **hậu tố của phần văn bản vừa duyệt**. Với ký tự mới `c=T[i]`:

1. Trong khi `j>0` và `c\ne P[j]`, đặt `j=pi[j-1]`.
2. Nếu `c=P[j]`, tăng `j` thêm `1`.
3. Nếu `j=m`, vừa phát hiện một lần xuất hiện của mẫu kết thúc tại `i`. Vị trí bắt đầu:

\[
\boxed{start=i-m+1.}
\]

4. Sau khi báo một lần khớp, **không đưa `j` về 0 một cách mù quáng**. Đặt:

\[
\boxed{j=pi[m-1]}
\]

để tiếp tục nhận ra những lần xuất hiện **chồng lấn**.

Pseudocode với `m>0`:

```text
pi = prefixFunction(P)
j = 0

for i = 0 .. n-1:
    while j > 0 and T[i] != P[j]:
        j = pi[j-1]

    if T[i] == P[j]:
        j = j + 1

    if j == m:
        answer.add(i-m+1)
        j = pi[m-1]
```

**Tại sao không truy cập ngoài mảng khi `j==m`?** Vì sau khi phát hiện đủ `m` ký tự, mã đặt `j=pi[m-1]` **ngay trong cùng vòng lặp**, trước lần đọc ký tự văn bản tiếp theo. Do đó khi bước sang `i+1`, luôn có `0\le j<m`.

### 6.1. Ví dụ T="ababa", P="aba"

`P="aba"` có:

\[
pi=[0,0,1].
\]

Duyệt:

| `i` | `T[i]` | `j` sau xử lý | Sự kiện |
|---:|:---:|---:|---|
| 0 | a | 1 | Khớp `a` |
| 1 | b | 2 | Khớp `ab` |
| 2 | a | 3 ⇒ 1 | Tìm tại `0`, quay về `pi[2]=1` |
| 3 | b | 2 | Mở rộng hậu tố `ab` |
| 4 | a | 3 ⇒ 1 | Tìm tại `2` |

Đáp án:

```text
T = a b a b a
P = a b a
    a b a      (bắt đầu tại 2)

Vị trí: [0, 2]
```

Nếu sau lần khớp tại `0` ta gán `j=0`, có thể bỏ qua lần khớp tại `2` vì hai mẫu **chồng lấn một ký tự**.

### 6.2. Ví dụ mẫu lặp

```text
T = "aaaaa"
P = "aaa"
pi = [0,1,2]

Khớp tại: [0,1,2].
```

Mỗi lần khớp đủ `m=3`, KMP đặt `j=pi[2]=2`, tức giữ lại hai ký tự `aa` làm tiền tố của lần khớp kế tiếp. Vì vậy tìm được ba vị trí liên tiếp.

### 6.3. Ví dụ nhiều lần xuất hiện

```text
T = "bananana"
P = "ana"

Các vị trí: [1,3,5].
```

Không dùng `indexOf` với bước tăng `m` sau một lần khớp nếu yêu cầu **tất cả** vị trí, vì có thể bỏ những lần khớp chồng lấn.

### 6.4. Ví dụ gây nhiều lặp cho cách tìm trực tiếp

```text
T = "aaaaaaaaab"   (9 chữ 'a' rồi 'b')
P = "aaaaab"       (5 chữ 'a' rồi 'b')

Khớp tại vị trí: [4].
```

Ở nhiều điểm bắt đầu trước `4`, cách tìm trực tiếp sẽ khớp hàng loạt chữ `a` rồi thất bại tại chữ `b` của mẫu. KMP dùng failure links để giữ lại lượng tiền tố vẫn hợp lệ, không phải đọc lại những chữ `a` trước đó trong văn bản.

## 7. Chứng minh KMP tìm đúng và chạy O(n+m)

### 7.1. Bất biến khi duyệt T

Trước khi xử lý `T[i]` (với `m>0`), biến `j` biểu diễn độ dài **tiền tố dài nhất của `P`** đồng thời là **hậu tố của phần văn bản `T[0..i-1]`**, sau khi đã phát hiện/ghi nhận các lần khớp hoàn chỉnh.

Khi `T[i]\ne P[j]`, tiền tố dài `j+1` không thể tiếp tục. Ta lần theo các border ngắn hơn của đoạn mẫu đã khớp bằng `j=pi[j-1]`. Mỗi lần lùi vẫn giữ hậu tố văn bản phù hợp với một tiền tố mẫu, không bỏ qua ứng viên có thể tạo khớp dài hơn.

Khi gặp `T[i]=P[j]`, tăng `j` lên `1` tạo một tiền tố mới dài thêm một ký tự khớp với hậu tố văn bản.

Khi `j=m`, đúng `m` ký tự cuối của phần văn bản vừa duyệt khớp toàn bộ mẫu, nên vị trí bắt đầu là `i-m+1`. Gán `j=pi[m-1]` giữ border dài nhất, không bỏ qua những lần khớp tương lai có phần đầu nằm trong lần khớp vừa tìm được.

Vì mọi lựa chọn border có thể tiếp tục đều được xét theo thứ tự giảm dần và không bỏ qua ứng viên hợp lệ, thuật toán tìm **mọi lần xuất hiện** và không báo vị trí sai.

### 7.2. Tại sao chỉ số văn bản không lùi?

KMP không cần bắt đầu lại tại `i-j+1` mỗi khi có mismatch. Thay vì lùi `i`, nó thay đổi `j` đến một border đã biết của mẫu; các ký tự văn bản đã đọc được mô tả đầy đủ bởi độ dài tiền tố đang khớp.

Do đó vòng ngoài tăng `i` từ `0` tới `n-1` đúng một lần.

### 7.3. Số lần lùi trong vòng while bị chặn

Trong khi duyệt văn bản:

- Mỗi ký tự mới có thể làm `j` tăng tối đa `1`.
- Mỗi lần thực hiện vòng while làm `j` giảm ít nhất `1`.
- Sau một lần khớp đầy đủ, phép gán `j=pi[m-1]<m` cũng là phép **giảm**, không phải tăng.

Vì `j\ge0` trong toàn bộ quá trình, tổng số lần giảm trong while và sau full match không thể vượt tổng số lần tăng cộng số hằng. Tổng lần tăng không vượt `n`, nên tổng bước lùi `O(n)`.

Kết hợp với tiền xử lý `pi[]` trong `O(m)`:

\[
\boxed{\text{Tổng thời gian KMP: }O(m+n).}
\]

Cần thêm `O(m)` để lưu `pi[]` và `O(occ)` để lưu `occ` vị trí tìm được nếu trả toàn bộ kết quả. Nếu chỉ cần biết **có khớp hay không** hoặc tìm **lần đầu**, có thể dừng sớm mà không lưu danh sách tất cả vị trí.

## 8. Chuỗi rỗng, chỉ số, Unicode và quy ước API

### 8.1. Mẫu rỗng khớp ở đâu?

Một mẫu rỗng có độ dài `m=0`. Nếu chạy công thức KMP thông thường rồi đọc `P.charAt(j)`, chương trình sẽ truy cập ngoài chuỗi. **Phải xử lý riêng**.

Trong bài này, chọn quy ước rõ ràng:

> **Mẫu rỗng xuất hiện tại mọi ranh giới ký tự của văn bản, gồm cả trước ký tự đầu và sau ký tự cuối.**

Vì vậy với văn bản dài `n` (đếm theo đơn vị chỉ số của API), kết quả là:

\[
\boxed{[0,1,\ldots,n].}
\]

Ví dụ:

```text
findAll("abc", "") -> [0,1,2,3]
findAll("", "")    -> [0]
findAll("", "a")   -> []
```

Hàm `firstIndex` chọn `0` khi mẫu rỗng. API streaming của ví dụ **không nhận mẫu rỗng** để tránh phải quy ước ranh giới giữa những khối dữ liệu và việc trả lặp lại ranh giới cùng một vị trí; dùng `findAll` khi cần trường hợp này.

Cách định nghĩa mẫu rỗng không giống nhau ở tất cả bài thi và thư viện. **Luôn đọc hợp đồng đề bài** trước khi áp dụng.

### 8.2. Chỉ số bắt đầu từ 0

Trong Java, `charAt(i)` và `substring(start,end)` sử dụng chỉ số **bắt đầu từ 0**; `end` là mốc **không bao gồm**. Với khớp kết thúc tại `i` và độ dài mẫu `m`:

\[
start=i-m+1.
\]

Không được dùng `i-m` (thiếu 1) hoặc `i` (đó là vị trí kết thúc).

### 8.3. Java String sử dụng UTF-16 code units

Trong Java:

- `String.length()` là số **đơn vị UTF-16**, không nhất thiết là số ký tự Unicode người đọc nhìn thấy.
- `charAt(i)` trả một `char` UTF-16.
- Một emoji như `🙂` thường gồm **hai đơn vị UTF-16** (surrogate pair).

Ví dụ:

```text
Text    = "🙂🙂"
Pattern = "🙂"

Chỉ số khớp theo String/UTF-16: [0,2].
```

Hai emoji nằm ở **vị trí code point `0` và `1`**, nhưng theo chỉ số `String` Java, emoji thứ hai bắt đầu tại `2`. Thuật toán KMP trong bài dùng `charAt` nên trả **UTF-16 offsets**, tương thích với `String.substring` và các phép tìm kiếm Java theo đơn vị UTF-16.

Nếu đề yêu cầu vị trí theo **Unicode code point** hoặc **grapheme cluster**, cần chuyển dữ liệu thành dãy code point hoặc phân đoạn ký tự mở rộng, sau đó quản lý ánh xạ chỉ số. Không được tự coi `String.length()` là số emoji/chữ nhìn thấy.

### 8.4. Phân biệt hoa/thường và Unicode normalization

KMP cơ bản so bằng **bằng nhau chính xác** giữa các `char`:

```text
"Hello" != "hello"
```

Chuỗi `é` dạng một code point và chuỗi biểu diễn bằng `e` + dấu kết hợp có thể trông giống nhau nhưng có các đơn vị mã khác nhau. Nếu cần tìm kiếm không phân biệt kiểu chuẩn hóa, phải **chuẩn hóa cả văn bản và mẫu bằng cùng một chính sách**.

Cần lưu ý phép chuẩn hóa hoặc biến đổi hoa/thường có thể làm thay đổi độ dài, nên chỉ số trong chuỗi đã biến đổi **không mặc nhiên** là vị trí trong chuỗi đầu vào. Nếu cần vị trí gốc, phải thiết kế ánh xạ offset riêng.

## 9. KMP streaming: tìm mẫu qua nhiều khối văn bản

KMP đặc biệt hữu ích khi văn bản không có sẵn thành một `String` lớn. Ví dụ nhận dữ liệu từ tệp hoặc mạng theo từng khối:

```text
Các khối nhận được:
"ab"
"ab"
"aba"

Ghép lại: "abababa"
Mẫu:    "aba"

Các vị trí xuất hiện: [0,2,4].
```

Nếu tìm riêng trong từng khối:

```text
"ab"  -> không có "aba"
"ab"  -> không có "aba"
"aba" -> có "aba" tại offset cục bộ 0
```

ta sẽ bỏ hai lần xuất hiện **băng qua ranh giới khối**.

### 9.1. Giữ lại trạng thái KMP giữa các khối

Chỉ cần lưu:

- Mẫu `P` và mảng `pi[]`.
- `j`: số ký tự mẫu đang khớp sau khối trước.
- `processed`: tổng số đơn vị ký tự văn bản đã đọc.

Khi nhận khối mới, xử lý lần lượt từng ký tự giống KMP bình thường, **không reset `j`**. Khi khớp đủ mẫu:

\[
start=processed-m.
\]

Ở đây `processed` được tăng sau khi tiêu thụ ký tự hoàn tất lần khớp.

### 9.2. Độ phức tạp streaming

Nếu tổng dữ liệu qua mọi khối có `N` đơn vị UTF-16:

- Tính `pi[]` một lần `O(m)`.
- Xử lý tổng cộng `N` ký tự `O(N)`.
- Trạng thái KMP lưu `O(m)` bộ nhớ, chưa kể danh sách kết quả đã trả.
- Một lần khớp có thể trải qua nhiều khối mà vẫn được nhận ra chính xác.

Gọi `feed("")` với một khối rỗng không thay đổi trạng thái và không tạo thêm kết quả. Điều này quan trọng khi dữ liệu đầu vào có những lần nhận khối độ dài `0`.

### 9.3. Cảnh báo với ranh giới UTF-16

Mẫu Java streaming nhận `String` theo đơn vị UTF-16. Nếu một surrogate pair bị chia làm hai khối, mã vẫn so khớp từng code unit xuyên ranh giới, phù hợp với hợp đồng **UTF-16 literal matching**.

Nếu mục tiêu là diễn giải/chuẩn hóa Unicode ở mức code point hoặc grapheme, việc phân đoạn và ghép dữ liệu đầu vào phải thực hiện đúng trước khi tìm mẫu; không được coi mọi `char` Java là một code point hoàn chỉnh.

## 10. Java 17+ hoàn chỉnh: prefix function, KMP và streaming

Chương trình độc lập bên dưới cung cấp:

1. `prefixFunction(String p)` tính toàn bộ mảng `pi[]`.
2. `findAll(String text,String pattern)` trả **mọi vị trí khớp**, gồm chồng lấn; quy ước mẫu rỗng khớp ở tất cả ranh giới.
3. `firstIndex(String text,String pattern)` trả vị trí đầu tiên, hoặc `-1` nếu không có; trả `0` cho mẫu rỗng.
4. `StreamMatcher.feed(String chunk)` nhận nhiều khối văn bản liên tiếp, giữ trạng thái `j` và trả vị trí **tuyệt đối** dưới dạng `long`; mẫu streaming bắt buộc không rỗng.
5. `brutePrefix` và `bruteFindAll` là hai **oracle kiểm thử độc lập** bằng so sánh từng vị trí, không dùng recurrence KMP.
6. Kiểm thử có seed gồm **3.000 cặp chuỗi ngẫu nhiên**, đối chiếu mảng tiền tố, danh sách vị trí, lần khớp đầu và kết quả streaming theo các khối bị cắt ngẫu nhiên.

**Hợp đồng:** các phương thức từ chối `null` bằng `NullPointerException`; chúng **phân biệt hoa/thường** và trả chỉ số **UTF-16**, giống `String.charAt`. Mã không thực hiện normalization, không biến đổi dữ liệu đầu vào, không yêu cầu bộ thư viện ngoài Java 17.

Tạo tệp **`KmpPrefixFunctionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public final class KmpPrefixFunctionDemo {
    private KmpPrefixFunctionDemo() {
    }

    // pi[i] = do dai border dai nhat cua p[0..i].
    public static int[] prefixFunction(String p) {
        Objects.requireNonNull(p, "pattern");

        int m = p.length();
        int[] pi = new int[m];

        for (int i = 1; i < m; i++) {
            int j = pi[i - 1];

            while (j > 0 && p.charAt(i) != p.charAt(j)) {
                j = pi[j - 1];
            }
            if (p.charAt(i) == p.charAt(j)) {
                j++;
            }
            pi[i] = j;
        }
        return pi;
    }

    // Moi lan xuat hien, bao gom cac lan chong lan.
    // Mau rong khop o n+1 ranh gioi: 0..n.
    public static List<Integer> findAll(
            String text, String pattern) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(pattern, "pattern");

        int n = text.length();
        int m = pattern.length();
        List<Integer> hits = new ArrayList<>();

        if (m == 0) {
            for (int i = 0; i <= n; i++) {
                hits.add(i);
            }
            return hits;
        }

        int[] pi = prefixFunction(pattern);
        int j = 0;

        for (int i = 0; i < n; i++) {
            char c = text.charAt(i);

            while (j > 0 && c != pattern.charAt(j)) {
                j = pi[j - 1];
            }
            if (c == pattern.charAt(j)) {
                j++;
            }

            if (j == m) {
                hits.add(i - m + 1);
                j = pi[m - 1];
            }
        }
        return hits;
    }

    // Tim lan dau; khong can thu thap moi ket qua.
    public static int firstIndex(
            String text, String pattern) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(pattern, "pattern");

        int n = text.length();
        int m = pattern.length();
        if (m == 0) {
            return 0;
        }

        int[] pi = prefixFunction(pattern);
        int j = 0;

        for (int i = 0; i < n; i++) {
            char c = text.charAt(i);
            while (j > 0 && c != pattern.charAt(j)) {
                j = pi[j - 1];
            }
            if (c == pattern.charAt(j)) {
                j++;
            }
            if (j == m) {
                return i - m + 1;
            }
        }
        return -1;
    }

    // Goi feed nhieu lan tren cac chunk lien tiep
    // cua CUNG MOT luong van ban. Chi nhan mau khac rong.
    public static final class StreamMatcher {
        private final String pattern;
        private final int[] pi;

        private int matched;
        private long processed;

        public StreamMatcher(String pattern) {
            this.pattern = Objects.requireNonNull(
                pattern, "pattern"
            );
            if (pattern.isEmpty()) {
                throw new IllegalArgumentException(
                    "stream pattern must be nonempty"
                );
            }

            this.pi = prefixFunction(pattern);
            this.matched = 0;
            this.processed = 0L;
        }

        // Vi tri tra ve la UTF-16 offset tinh tu dau stream.
        public List<Long> feed(String chunk) {
            Objects.requireNonNull(chunk, "chunk");
            List<Long> hits = new ArrayList<>();
            int m = pattern.length();

            for (int i = 0; i < chunk.length(); i++) {
                char c = chunk.charAt(i);

                while (matched > 0
                        && c != pattern.charAt(matched)) {
                    matched = pi[matched - 1];
                }
                if (c == pattern.charAt(matched)) {
                    matched++;
                }

                processed = Math.addExact(processed, 1L);
                if (matched == m) {
                    hits.add(processed - m);
                    matched = pi[m - 1];
                }
            }
            return hits;
        }

        public long processedUnits() {
            return processed;
        }
    }

    // Oracle KHONG dung KMP: duyet moi border proper.
    private static int[] brutePrefix(String p) {
        int m = p.length();
        int[] result = new int[m];

        for (int i = 0; i < m; i++) {
            // Prefix p[0..i] co do dai i+1.
            // Border proper dai toi da i.
            for (int k = i; k >= 1; k--) {
                boolean same = true;

                for (int x = 0; x < k; x++) {
                    if (p.charAt(x)
                            != p.charAt(i - k + 1 + x)) {
                        same = false;
                        break;
                    }
                }
                if (same) {
                    result[i] = k;
                    break;
                }
            }
        }
        return result;
    }

    // Oracle KHONG dung KMP: so sanh tung vi tri.
    private static List<Integer> bruteFindAll(
            String text, String p) {
        List<Integer> hits = new ArrayList<>();

        for (int start = 0;
                start <= text.length() - p.length();
                start++) {
            if (text.regionMatches(
                    start, p, 0, p.length())) {
                hits.add(start);
            }
        }
        return hits;
    }

    private static String randomWord(
            Random random, int length) {
        String alphabet = "aabccà";
        StringBuilder result = new StringBuilder(length);

        for (int i = 0; i < length; i++) {
            result.append(
                alphabet.charAt(
                    random.nextInt(alphabet.length()))
            );
        }
        return result.toString();
    }

    private static void require(
            boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        System.out.println(
            "pi(ababaca): "
            + Arrays.toString(prefixFunction("ababaca"))
        );
        System.out.println(
            "pi(aaaa): "
            + Arrays.toString(prefixFunction("aaaa"))
        );
        System.out.println(
            "pi(aabaaab): "
            + Arrays.toString(prefixFunction("aabaaab"))
        );

        System.out.println(
            "bananana / ana: "
            + findAll("bananana", "ana")
        );
        System.out.println(
            "ababa / aba: "
            + findAll("ababa", "aba")
        );
        System.out.println(
            "aaaaa / aaa: "
            + findAll("aaaaa", "aaa")
        );
        System.out.println(
            "abababababa / ababa: "
            + findAll("abababababa", "ababa")
        );
        System.out.println(
            "xyxy / xyz: "
            + findAll("xyxy", "xyz")
        );
        System.out.println(
            "abc / empty: " + findAll("abc", "")
        );
        System.out.println(
            "empty / empty: " + findAll("", "")
        );
        System.out.println(
            "first(bananana,ana): "
            + firstIndex("bananana", "ana")
        );
        System.out.println(
            "Unicode UTF-16 offsets: "
            + findAll("🙂🙂", "🙂")
        );

        StreamMatcher stream = new StreamMatcher("aba");
        List<Long> h1 = stream.feed("ab");
        List<Long> h2 = stream.feed("ab");
        List<Long> h3 = stream.feed("aba");

        System.out.println(
            "Stream hits: " + h1 + " | "
            + h2 + " | " + h3
        );
        System.out.println(
            "Stream processed units: "
            + stream.processedUnits()
        );

        boolean emptyStreamingRejected = false;
        try {
            new StreamMatcher("");
        } catch (IllegalArgumentException expected) {
            emptyStreamingRejected = true;
        }
        System.out.println(
            "Empty streaming pattern rejected: "
            + emptyStreamingRejected
        );

        Random random = new Random(368L);
        int ordinaryChecks = 0;
        int streamingChecks = 0;

        for (int trial = 0; trial < 3_000; trial++) {
            int textLength = random.nextInt(40);
            int patternLength = random.nextInt(16);
            String text = randomWord(random, textLength);
            String pattern = randomWord(random, patternLength);

            int[] actualPi = prefixFunction(pattern);
            int[] expectedPi = brutePrefix(pattern);
            require(Arrays.equals(actualPi, expectedPi),
                "prefix-function mismatch trial=" + trial
            );

            List<Integer> actual =
                findAll(text, pattern);
            List<Integer> expected =
                bruteFindAll(text, pattern);
            require(actual.equals(expected),
                "KMP matches mismatch trial=" + trial
            );

            int expectedFirst = expected.isEmpty()
                ? -1 : expected.get(0);
            require(firstIndex(text, pattern) == expectedFirst,
                "first-index mismatch trial=" + trial
            );
            ordinaryChecks++;

            // Streaming can giu mau khac rong.
            String streamPattern = pattern.isEmpty()
                ? "a" : pattern;
            StreamMatcher matcher =
                new StreamMatcher(streamPattern);

            List<Long> streamHits = new ArrayList<>();
            int at = 0;

            while (at < text.length()) {
                int remaining = text.length() - at;
                int take = 1 + random.nextInt(
                    Math.min(remaining, 7)
                );

                streamHits.addAll(
                    matcher.feed(text.substring(at, at + take))
                );
                at += take;

                if (at % 4 == 0) {
                    streamHits.addAll(matcher.feed(""));
                }
            }
            streamHits.addAll(matcher.feed(""));

            List<Long> expectedStream = new ArrayList<>();
            for (int hit : bruteFindAll(text, streamPattern)) {
                expectedStream.add((long) hit);
            }
            require(streamHits.equals(expectedStream),
                "streaming mismatch trial=" + trial
            );
            require(matcher.processedUnits() == text.length(),
                "stream offset mismatch trial=" + trial
            );
            streamingChecks++;
        }

        System.out.println(
            "Random prefix/search checks: "
            + ordinaryChecks
        );
        System.out.println(
            "Random streaming checks: "
            + streamingChecks
        );
    }
}
```

Biên dịch và chạy trên **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 KmpPrefixFunctionDemo.java
java KmpPrefixFunctionDemo
```

**Đầu ra chuẩn**:

```text
pi(ababaca): [0, 0, 1, 2, 3, 0, 1]
pi(aaaa): [0, 1, 2, 3]
pi(aabaaab): [0, 1, 0, 1, 2, 2, 3]
bananana / ana: [1, 3, 5]
ababa / aba: [0, 2]
aaaaa / aaa: [0, 1, 2]
abababababa / ababa: [0, 2, 4, 6]
xyxy / xyz: []
abc / empty: [0, 1, 2, 3]
empty / empty: [0]
first(bananana,ana): 1
Unicode UTF-16 offsets: [0, 2]
Stream hits: [] | [0] | [2, 4]
Stream processed units: 7
Empty streaming pattern rejected: true
Random prefix/search checks: 3000
Random streaming checks: 3000
```

### 10.1. Tại sao Java charAt an toàn trong vòng while?

Trong `prefixFunction`, trước khi so `p.charAt(j)`, ta có `j=pi[i-1]\le i-1<m`. Khi lùi, `j` càng nhỏ. Khi so ký tự thành công và tăng `j`, giá trị tối đa ở vòng `i` là `i<m`.

Trong `findAll` và `firstIndex`, trường hợp `m=0` đã được xử lý riêng. Với `m>0`, sau khi `j` tăng đến `m`, chương trình ngay lập tức báo khớp và hạ `j=pi[m-1]<m` trước khi xử lý ký tự văn bản kế tiếp.

Trong `StreamMatcher`, constructor từ chối mẫu rỗng và `feed` cũng reset `matched` ngay sau lần khớp đủ. Không có lần đọc `pattern.charAt(m)`.

### 10.2. Vì sao streaming tìm được hai lần khớp xuyên ranh giới?

`StreamMatcher` duy trì `matched` sau mỗi khối. Với ba khối `"ab"`, `"ab"`, `"aba"`:

- Khối 1: đã khớp hai ký tự `"ab"`, chưa đủ mẫu ⇒ `[]`.
- Khối 2: đọc ký tự `a` đầu khối, hoàn tất mẫu bắt đầu `0` ⇒ `[0]`; trạng thái border còn `1` nên tiếp tục.
- Khối 3: lần lượt hoàn tất hai mẫu bắt đầu tại `2` và `4` ⇒ `[2,4]`.

Tổng cộng đã đọc `7` code units và có các vị trí `[0,2,4]`, đúng như tìm trên toàn bộ `"abababa"` một lần.

### 10.3. Phân biệt oracle và KMP

`brutePrefix` thử tất cả border proper bằng so từng ký tự. `bruteFindAll` thử mọi điểm bắt đầu bằng `String.regionMatches`. **Cả hai không sử dụng bảng failure links** của KMP.

Nếu KMP tính sai `pi[]` hoặc sai bước lùi và bỏ sót một vị trí chồng lấn, kết quả nhiều khả năng không khớp oracle trên tập ngẫu nhiên. Kiểm thử như vậy có ý nghĩa hơn việc chạy **hai bản KMP giống hệt nhau** rồi so kết quả.

### 10.4. Trường hợp Java source và console encoding

Mã Java dùng Unicode literal trong dữ liệu kiểm thử, gồm dấu `à` và emoji. Lệnh `javac -encoding UTF-8` bảo đảm trình biên dịch đọc tệp đúng mã hóa UTF-8.

Kết quả trong chương trình chủ yếu là số và ký hiệu ASCII; việc hiển thị dấu tiếng Việt khi in chuỗi còn phụ thuộc cấu hình terminal. **Chỉ số trả về vẫn là UTF-16 offsets**, không thay đổi theo cách terminal hiển thị.

## 11. Độ phức tạp và chi phí thực tế

Đặt `n=|T|`, `m=|P|` và `occ` là số lần xuất hiện của mẫu.

| Công việc | Thời gian | Bộ nhớ phụ |
|---|---|---|
| Tính `pi[]` | `O(m)` | `O(m)` |
| Tìm lần đầu bằng KMP | `O(m+n)` trường hợp xấu | `O(m)` |
| Tìm tất cả bằng KMP | `O(m+n+occ)` bao gồm ghi kết quả | `O(m+occ)` |
| Streaming trên tổng `N` ký tự | `O(m+N+occ)` | `O(m)` trạng thái, cộng kết quả từng khối |
| Brute force khớp từng vị trí | `O(nm)` trường hợp xấu | `O(1)` nếu chỉ báo có/không |
| Brute force prefix như mã oracle | `O(m^3)` trường hợp xấu | `O(m)` |
| KMP với mẫu rỗng theo hợp đồng này | `O(n)` để liệt kê `n+1` vị trí | `O(n)` cho kết quả |

Khi mẫu rỗng, số vị trí khớp là `n+1`, nên nếu API buộc **trả toàn bộ danh sách**, riêng việc cấp phát danh sách đó đã tốn `O(n)` bộ nhớ và thời gian. Muốn kiểm tra **có tồn tại mẫu rỗng** chỉ cần trả `true` ngay.

### 11.1. Vì sao KMP không luôn nhanh nhất trên mọi văn bản thực tế?

Độ phức tạp `O(n+m)` là một bảo đảm **trường hợp xấu** rất mạnh. Nhưng thực tế còn có:

- Overhead xây `pi[]`, cấp phát mảng và danh sách vị trí.
- Các tối ưu bộ nhớ, vector hóa và thuật toán nội bộ của `String.indexOf`.
- Mẫu cực ngắn, văn bản nhỏ hoặc chỉ tìm một lần.

Vì vậy, với code ứng dụng Java bình thường chỉ tìm chuỗi con, `String.indexOf` thường đơn giản và đáng cân nhắc. KMP đặc biệt có giá trị khi cần **hiểu cơ chế tuyến tính**, làm việc với dữ liệu streaming, xử lý nhiều dữ liệu dưới một mẫu, hoặc giải bài thuật toán có yêu cầu rõ về độ phức tạp.

Không cần tự khẳng định KMP nhanh hơn mọi implementation thư viện trên mọi đầu vào.

### 11.2. Một mẫu, nhiều văn bản

Nếu có một mẫu `P` và nhiều văn bản `T_1,\ldots,T_q`, có thể tính `pi[]` **một lần**, rồi tìm lần lượt trên mỗi văn bản:

\[
O\left(m+\sum_{i=1}^{q}|T_i|+
\text{tổng số lần xuất hiện}\right).
\]

Code `findAll` ở trên tính lại `pi[]` ở mỗi lần gọi cho dễ dùng độc lập. Nếu cần tối ưu nhiều văn bản dùng chung mẫu, có thể đóng gói `P` và `pi[]` trong một đối tượng matcher bất biến, rồi tạo riêng biến `j` cho mỗi lượt tìm/stream.

**Không dùng chung một biến `j` mutable giữa hai văn bản độc lập** nếu không muốn coi văn bản thứ hai là phần tiếp nối của văn bản thứ nhất.

## 12. Hàm tiền tố ngoài tìm kiếm: border, chu kỳ và cấu trúc chuỗi

Hàm `pi[]` có thể giải nhiều bài toán khác ngoài KMP.

### 12.1. Liệt kê tất cả border của cả chuỗi

Nếu `m>0`, border dương dài nhất của toàn chuỗi là:

\[
k=pi[m-1].
\]

Để liệt kê các border tiếp theo, lặp:

```text
while k > 0:
    record k
    k = pi[k-1]
```

Ví dụ với `S="ababa"`:

```text
pi = [0,0,1,2,3]

k=3 -> border "aba"
k=1 -> border "a"
k=0 -> stop

Độ dài border dương: [3,1].
```

Chuỗi failure links giúp liệt kê các border thực sự của cả chuỗi, không phải mọi độ dài từ `1` đến `m-1`.

### 12.2. Chu kỳ và lặp chuỗi

Với chuỗi `S` dài `m>0`, đặt:

\[
p=m-pi[m-1].
\]

Đây là một **độ dài chu kỳ ứng viên**. Nếu:

\[
m\bmod p=0
\]

và `p<m`, chuỗi `S` được tạo bằng cách lặp lại một khối độ dài `p` ít nhất hai lần.

Ví dụ:

```text
S="ababab"
m=6
pi[m-1]=4
p=6-4=2

6 % 2 == 0, S="ab" lặp 3 lần.
```

Với `S="ababa"`, `p=5-3=2` nhưng `5\bmod2\ne0`, nên không thể biểu diễn toàn chuỗi bằng cách lặp **một khối nguyên vẹn** độ dài `2`. Dù vậy `2` vẫn là một chu kỳ theo khái niệm so khớp tại các vị trí mà cả hai ký tự tồn tại. Phải phân biệt **có chu kỳ** và **là lũy thừa nguyên lần của một chuỗi con**.

### 12.3. Đếm số lần tiền tố xuất hiện như hậu tố của prefix

Trong những bài nâng cao, thông tin `pi[]` có thể dùng để đếm số lần mỗi độ dài tiền tố đóng vai trò hậu tố của các đoạn `S[0..i]`. Người giải có thể cộng số lần `pi[i]` xuất hiện và lan truyền số đếm ngược theo failure links, sau đó cộng lần xuất hiện của chính tiền tố.

Cần phân biệt bài **đếm vị trí xuất hiện của mọi tiền tố** với bài **liệt kê border của toàn chuỗi**; chúng liên quan nhưng không đồng nhất.

## 13. KMP không làm gì?

KMP giải chính xác một bài: **tìm một mẫu cố định trong văn bản theo phép so sánh ký tự bằng nhau**, với thời gian tuyến tính.

Nó không tự giải:

- **Tìm một trong rất nhiều mẫu** với thời gian tiền xử lý tối ưu cho tổng tập mẫu: có thể cân nhắc **Aho–Corasick**.
- **Tìm gần đúng** cho phép thay/xóa/chèn ký tự: cần edit distance hoặc thuật toán approximate matching.
- **So khớp wildcard/regex đầy đủ** như `a.*b`: cần mô hình khác.
- **Tìm chuỗi con chung dài nhất** giữa hai chuỗi theo nghĩa tổng quát.
- **Tìm không phân biệt hoa/thường hoặc Unicode normalization** khi không có bước tiền xử lý được định nghĩa rõ.

**Không dùng KMP như hộp đen cho mọi bài có chữ “chuỗi”**. Hãy xác định xem đề cần khớp literal một mẫu, nhiều mẫu, so khớp xấp xỉ, đếm chu kỳ hay điều kiện cấu trúc khác.

## 14. Kiểm thử: so với phương pháp trực tiếp trên nhiều loại dữ liệu

Một bộ kiểm thử tốt cho KMP nên so cả **bảng pi** và **vị trí xuất hiện**; chỉ so vị trí cuối không đủ vì bảng pi có thể sai mà vô tình vẫn qua vài mẫu dễ.

### 14.1. Kiểm thử pi[] độc lập

Với mẫu nhỏ `P`, oracle làm:

1. Ở mỗi `i`, xét các độ dài `k=i,i-1,\ldots,1`.
2. So trực tiếp `P[0..k-1]` với hậu tố dài `k` của `P[0..i]`.
3. Dừng ở `k` đầu tiên bằng nhau, hoặc trả `0`.

Đây là cách triển khai chậm nhưng **không cần failure link**, nên hữu ích để đối chiếu thuật toán `pi[]` tuyến tính.

### 14.2. Kiểm thử vị trí khớp độc lập

Với mọi điểm bắt đầu `s=0..n-m`, so trực tiếp `T[s..s+m-1]` với `P`. Nếu khớp, thêm `s` vào danh sách.

Với mẫu rỗng, vòng lặp sẽ xét `s=0..n`, phù hợp chính sách liệt kê mọi ranh giới.

Sau đó so **toàn bộ danh sách có thứ tự** với kết quả KMP, không chỉ so số lượng. Như vậy có thể phát hiện lỗi bỏ vị trí chồng lấn hoặc lỗi lệch một đơn vị.

### 14.3. Kiểm thử streaming bằng cách cắt khối ngẫu nhiên

Với mỗi văn bản, tạo nhiều cách cắt thành các khối liên tiếp kích thước khác nhau, trong đó có thể xen khối rỗng. Gọi `feed` lần lượt, nối **danh sách kết quả**, rồi so với cách tìm trực tiếp trên toàn văn bản.

Cách này kiểm tra hai bất biến:

- `matched` được giữ đúng qua ranh giới khối.
- `processed` tăng đúng tổng độ dài đã đọc; vị trí báo phải là **offset toàn cục**, không phải offset trong khối.

### 14.4. Các ca biên nên có

```text
Pattern rỗng:
  text="abc", p="" -> [0,1,2,3]
  text="",    p="" -> [0]

Văn bản rỗng, mẫu không rỗng:
  text="", p="a" -> []

Mẫu dài hơn văn bản:
  text="ab", p="aba" -> []

Mẫu dài đúng bằng văn bản:
  text="abc", p="abc" -> [0]

Không có lần xuất hiện:
  text="xyxy", p="xyz" -> []

Nhiều lần chồng lấn:
  text="ababa", p="aba" -> [0,2]
  text="aaaaa", p="aaa" -> [0,1,2]

Ký tự lặp:
  p="aaaa" -> pi=[0,1,2,3]

Border nhiều cấp:
  p="ababaca" -> pi=[0,0,1,2,3,0,1]

Mismatch sau gần hết mẫu:
  text="aaaaaaaaab", p="aaaaab" -> [4]

Chỉ số Unicode UTF-16:
  text="🙂🙂", p="🙂" -> [0,2]

Streaming qua ranh giới:
  chunks="ab","ab","aba", p="aba" -> [0,2,4]

Streaming khối rỗng:
  feed("") không đổi processed hoặc matched

Pattern streaming rỗng:
  từ chối bằng IllegalArgumentException
```

Với dữ liệu ngẫu nhiên, nên dùng alphabet nhỏ như `a,b,c` để tạo **nhiều đoạn trùng lặp và border sâu**, không chỉ các ký tự ngẫu nhiên ít bao giờ khớp nhau. Thêm ký tự tiếng Việt như `à` giúp kiểm tra việc xử lý UTF-16 đơn vị ký tự cơ bản.

### 14.5. Kết quả kiểm thử mẫu Java

Chương trình tạo 3.000 cặp văn bản/mẫu bằng `Random(368L)`. Với mỗi cặp:

- `prefixFunction` đối chiếu với `brutePrefix`.
- `findAll` đối chiếu với `bruteFindAll`.
- `firstIndex` đối chiếu vị trí đầu tiên từ oracle.
- Một mẫu không rỗng được đưa vào `StreamMatcher`; văn bản được cắt thành các khối ngẫu nhiên, đôi khi thêm khối rỗng, rồi so các vị trí tuyệt đối với oracle.

Vì vậy kết quả cuối in:

```text
Random prefix/search checks: 3000
Random streaming checks: 3000
```

Các phép đối chứng giúp phát hiện nhiều lỗi lập trình, **không thay thế chứng minh toán học** về công thức và tính tuyến tính.

## 15. Các lỗi KMP phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Định nghĩa `pi[i]` là border dài bằng toàn đoạn | `pi[i]=i+1` sai, có thể tạo vòng failure không giảm | Chỉ xét **border proper** |
| Nhầm `pi[i]` là vị trí ký tự thay vì độ dài border | Sai các bước fallback | Nhớ `pi[i]` là **độ dài** |
| Khi mismatch viết `j=pi[j]` | Sai chỉ số, có thể không giảm hoặc vượt miền | Dùng **`j=pi[j-1]`** |
| Đọc `pi[j-1]` khi `j=0` | Truy cập chỉ số âm | Điều kiện `while(j>0 && ...)` |
| Mismatch thì luôn đặt `j=0` | Bỏ những border ngắn hơn vẫn hợp lệ | Lần qua chuỗi failure links |
| Tăng `i` của văn bản lùi lại sau mismatch | Mất ưu thế tuyến tính, dễ sai | Chỉ đổi `j`; `i` tăng một lượt |
| Quên tăng `j` khi ký tự trùng | Không tiến tới full match | So `P[j]` và tăng khi bằng nhau |
| Sau khi khớp đủ mẫu không reset `j` | Lần tới đọc `P[m]` ngoài chuỗi | Đặt `j=pi[m-1]` ngay |
| Sau full match đặt `j=0` | Bỏ các lần xuất hiện chồng lấn | Giữ border `pi[m-1]` |
| Vị trí bắt đầu ghi `i-m` | Lệch chỉ số | Dùng **`i-m+1`** |
| Không xử lý mẫu rỗng | `charAt(0)` lỗi hoặc semantics sai | Định nghĩa và xử lý riêng |
| Dùng vòng `i<=n` khi đọc văn bản | Truy cập ngoài chỉ số cuối | Với ký tự: `0<=i<n` |
| Đếm ký tự Java String như code point | Sai offset với emoji/surrogate pairs | Nêu rõ UTF-16 index hoặc chuyển đổi |
| Chuẩn hóa chuỗi rồi trả offset gốc không đổi | Có thể báo vị trí sai | Quản lý ánh xạ offset |
| Streaming reset `matched=0` ở mỗi chunk | Bỏ match băng qua ranh giới | Giữ trạng thái KMP |
| Streaming dùng chỉ số trong chunk làm vị trí toàn cục | Các lần khớp sau bị sai offset | Lưu `processed` tích lũy |
| Chỉ kiểm tra một ví dụ không chồng lấn | Không phát hiện lỗi full-match fallback | Test `ababa/aba` và `aaaaa/aaa` |
| Kiểm tra KMP bằng một bản KMP giống hệt | Hai bản có thể mắc cùng lỗi | Dùng oracle so từng vị trí |
| Dùng KMP cho so khớp xấp xỉ/regex | Giải sai loại bài toán | Chọn thuật toán đúng mô hình |
| Không xét chi phí tạo danh sách tất cả match | Tốn `O(n)` khi có nhiều kết quả | Trả iterator/callback nếu cần streaming |
| Tuyên bố luôn nhanh hơn `String.indexOf` | Không có bảo đảm về hằng số | Phân biệt worst-case và performance thực tế |

## 16. Bài tập tự luyện có đáp án

**Bài 1.** Border là gì? Toàn bộ chuỗi có được tính là border của chính nó không?

*Đáp án:* Border là chuỗi vừa là tiền tố thực sự vừa là hậu tố thực sự. **Không** tính toàn bộ chuỗi; border phải ngắn hơn chuỗi gốc.

**Bài 2.** Tính `pi[]` của `P="aaaa"`.

*Đáp án:* `[0,1,2,3]`.

**Bài 3.** Tính `pi[]` của `P="ababaca"`.

*Đáp án:* `[0,0,1,2,3,0,1]`.

**Bài 4.** Tại sao ở `i=5` của `ababaca`, `j` giảm từ `3` về `1` rồi `0`?

*Đáp án:* `P[5]='c'` không khớp `P[3]='b'`, chuyển `j=pi[2]=1`; vẫn không khớp `P[1]='b'`, chuyển `j=pi[0]=0`. `c` không bằng `P[0]='a'` nên `pi[5]=0`.

**Bài 5.** Khi đã khớp `j=5` ký tự đầu mẫu nhưng ký tự văn bản mới không khớp, chỉ số nào của `pi` được đọc đầu tiên?

*Đáp án:* `pi[4]`, tức `pi[j-1]`.

**Bài 6.** `T="ababa"`, `P="aba"`. Có bao nhiêu khớp và tại đâu?

*Đáp án:* 2 lần tại `[0,2]`; hai lần chồng lấn nhau.

**Bài 7.** `T="aaaaa"`, `P="aaa"`. Vị trí khớp?

*Đáp án:* `[0,1,2]`.

**Bài 8.** Khi KMP tìm một lần khớp đầy đủ ở `i=12` và mẫu dài `m=5`, vị trí bắt đầu là gì?

*Đáp án:* `12-5+1=8`.

**Bài 9.** Vì sao sau full match không nên đặt `j=0`?

*Đáp án:* có thể bỏ mất lần khớp chồng lấn; border dài nhất của mẫu có thể tiếp tục khớp với văn bản. Đặt `j=pi[m-1]`.

**Bài 10.** Mẫu `P="aba"` có `pi=[0,0,1]`. Sau khi khớp đủ mẫu, `j` trở về bao nhiêu?

*Đáp án:* `pi[2]=1`.

**Bài 11.** Vì sao xây `pi[]` bằng vòng while lồng trong for vẫn `O(m)`?

*Đáp án:* tổng lần `j` tăng tối đa `m-1`; mỗi lần while giảm `j` ít nhất `1`, và `j` không âm. Vì vậy tổng số lần giảm trên tất cả vòng lặp là `O(m)`.

**Bài 12.** KMP tìm kiếm văn bản dài `n` với mẫu dài `m` có độ phức tạp nào?

*Đáp án:* `O(n+m)` thời gian để xử lý, cộng chi phí ghi kết quả `O(occ)` khi trả toàn bộ; bộ nhớ phụ `O(m+occ)` khi lưu mảng pi và danh sách vị trí.

**Bài 13.** `findAll("abc","")` theo hợp đồng bài là gì?

*Đáp án:* `[0,1,2,3]`.

**Bài 14.** `findAll("","")` là gì?

*Đáp án:* `[0]`.

**Bài 15.** Chuỗi `🙂🙂` có hai emoji. Tại sao tìm `🙂` bằng `charAt` trả vị trí `[0,2]`, không phải `[0,1]`?

*Đáp án:* chỉ số Java `String` đếm **đơn vị UTF-16**; mỗi emoji này gồm hai code units.

**Bài 16.** Vì sao `StreamMatcher` phải giữ `matched` qua các lần `feed`?

*Đáp án:* một lần xuất hiện của mẫu có thể bắt đầu ở cuối khối trước và kết thúc ở khối sau. Reset sẽ bỏ các lần khớp xuyên ranh giới.

**Bài 17.** Với các chunk `"ab","ab","aba"` và mẫu `"aba"`, vị trí khớp tuyệt đối?

*Đáp án:* `[0,2,4]`.

**Bài 18.** `P="ababa"` có các border dương nào?

*Đáp án:* `"aba"` (dài 3) và `"a"` (dài 1). Truy `pi[4]=3` rồi `pi[2]=1`.

**Bài 19.** `S="ababab"` có thể biểu diễn bằng một chuỗi con lặp nguyên lần không?

*Đáp án:* có; `m=6`, `pi[5]=4`, `p=m-pi[5]=2`, `6\bmod2=0`, nên `"ab"` lặp 3 lần.

**Bài 20.** Tại sao `"ababa"` không được coi là `"ab"` lặp nguyên lần, dù có chu kỳ `2`?

*Đáp án:* độ dài `5` không chia hết cho `2`. Nó có tính chất chu kỳ với các vị trí so sánh được, nhưng không là phép lặp một khối `"ab"` số nguyên lần.

**Bài 21.** Với mẫu rỗng và văn bản dài `n`, vì sao trả toàn bộ kết quả phải tốn `O(n)` bộ nhớ?

*Đáp án:* theo quy ước bài có `n+1` vị trí khớp; riêng danh sách kết quả đã chứa `n+1` phần tử.

**Bài 22.** Muốn tìm **nhiều mẫu** trong một văn bản lớn, có nên chạy KMP riêng từng mẫu hay xét cấu trúc khác?

*Đáp án:* chạy KMP từng mẫu luôn là cách đúng cho từng mẫu, nhưng khi số mẫu lớn có thể xét **Aho–Corasick** để chia sẻ công việc; phải dựa vào ràng buộc cụ thể.

## 17. Checklist khi giải bài KMP

1. Đề yêu cầu một mẫu literal, hay nhiều mẫu/regex/so khớp gần đúng?
2. Độ dài `n,m` đã được hiểu đúng, chỉ số bắt đầu từ `0`?
3. Có phân biệt **proper prefix/suffix** và border, không lấy toàn chuỗi?
4. `pi[i]` có được hiểu là **độ dài border dài nhất** của `P[0..i]`?
5. `pi[0]=0` và `0\le pi[i]\le i`?
6. Tính pi: khởi đầu `j=pi[i-1]`, fallback `j=pi[j-1]` khi `j>0`?
7. Khi ký tự khớp có tăng `j` lên đúng `1`?
8. Trong tìm kiếm, chỉ số văn bản `i` có chạy tuyến tính, không lùi sau mismatch?
9. Khi `j=m` có thêm `i-m+1` vào kết quả?
10. Sau full match có reset `j=pi[m-1]` để phát hiện **overlap**?
11. Đã xử lý trường hợp mẫu rỗng theo đúng hợp đồng?
12. Đã thử văn bản rỗng, mẫu dài hơn văn bản, không có match và match tại vị trí `0`?
13. Đã thử các mẫu tự lặp như `aaaa` và border nhiều cấp như `ababaca`?
14. Nếu streaming, có giữ `matched` và `processed` xuyên qua chunk boundaries?
15. Nếu dùng Java, vị trí trả về là **UTF-16 code-unit offset**, không nhầm với Unicode code point?
16. Nếu cần ignore-case/normalization, đã xác định chính sách biến đổi và ánh xạ offset?
17. Có phân biệt `O(n+m)` xử lý và `O(occ)` bộ nhớ/ghi kết quả?
18. Có kiểm chứng bằng oracle so từng border và từng vị trí trên chuỗi nhỏ?
19. Có trình bày rõ một đường diễn tiến failure link khi mismatch, không chỉ chép mã?
20. Có giữ nguyên thứ tự vị trí khớp tăng dần và không bỏ kết quả chồng lấn?

## Ghi nhớ

Hàm tiền tố:

\[
\boxed{
pi[i]=\text{độ dài border proper dài nhất của }P[0..i].
}
\]

Khi muốn mở rộng border và ký tự không khớp, **không thử lại từ đầu**:

\[
\boxed{j\gets pi[j-1]\quad\text{(chỉ khi }j>0\text{)}.}
\]

Khi tìm kiếm, giữ `i` của văn bản tăng từ trái sang phải và đổi `j` theo failure links. Khi đã khớp đủ `m` ký tự mẫu tại vị trí kết thúc `i`:

\[
\boxed{start=i-m+1,\qquad j\gets pi[m-1].}
\]

Bước reset về `pi[m-1]` giúp tìm đầy đủ các lần xuất hiện **chồng lấn**.

\[
\boxed{
\text{KMP: thời gian }O(n+m),\
\text{bộ nhớ tiền xử lý }O(m).
}
\]

Với Java `String`, nhớ chỉ số là **UTF-16 offsets**, phải xử lý mẫu rỗng riêng và nêu chính sách rõ. **KMP nhanh không phải vì bỏ qua việc so ký tự, mà vì tận dụng các border đã biết để không làm lại những so sánh không cần thiết.**

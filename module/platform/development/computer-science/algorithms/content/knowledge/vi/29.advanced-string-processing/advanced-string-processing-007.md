# Đếm chuỗi con phân biệt và số lần xuất hiện

## Mục tiêu và phạm vi

Trong nhóm **Xử lý chuỗi nâng cao**, hai câu hỏi thường xuất hiện cùng nhau nhưng **không đồng nghĩa**:

1. Một chuỗi s có bao nhiêu **chuỗi con liên tiếp, không rỗng, phân biệt** (*distinct nonempty substrings*)?
2. Một chuỗi con cụ thể p xuất hiện **bao nhiêu lần** trong s (*number of occurrences*)?

Ví dụ s = `"ababa"` có **9 chuỗi con không rỗng phân biệt**, nhưng tổng số **lần xuất hiện** của tất cả chuỗi con không rỗng là **15**, vì một số chuỗi xuất hiện nhiều lần. Riêng p = `"aba"` xuất hiện **2 lần** ở vị trí 0 và 2, kể cả khi hai đoạn **chồng lấn**.

Bài học xây dựng lời giải bằng **suffix automaton (SAM)** — một máy trạng thái hữu hạn biểu diễn tất cả chuỗi con của văn bản, đồng thời cho phép đếm số lần xuất hiện theo nhóm các chuỗi có chung tập vị trí kết thúc (*endpos equivalence*).

Bạn sẽ học:

- Phân biệt **substring** (liên tiếp) với **subsequence** (không cần liên tiếp), phân biệt **số chuỗi con** với **số chuỗi con phân biệt**, và phân biệt **số mẫu khác nhau** với **tần suất từng mẫu**.
- Đếm chuỗi con phân biệt bằng công thức của suffix automaton: `sum(len[v]-len[link[v]])`.
- Đếm số lần xuất hiện của mẫu bằng cách khởi tạo `occ=1` cho trạng thái tạo mới, `occ=0` cho **clone**, rồi cộng dồn theo suffix links từ trạng thái dài sang ngắn.
- Giải thích tại sao mọi chuỗi được biểu diễn bởi cùng một trạng thái SAM có **cùng tần suất xuất hiện**.
- Xử lý mẫu rỗng, văn bản rỗng, chuỗi lặp, khớp chồng lấn, giới hạn bảng chữ cái và số nguyên lớn.
- Cài đặt Java 17+ chạy được, có mẫu đầu ra xác minh.
- So sánh suffix automaton với cách liệt kê ngây thơ, suffix array + LCP, KMP và rolling hash.

---

## 1. Định nghĩa phải rõ trước khi tính

### 1.1. Chuỗi con liên tiếp — substring

Với chuỗi s độ dài n, chuỗi con là một đoạn ký tự **liên tiếp**:

\[
s[l..r),\quad 0\le l<r\le n.
\]

Cách viết `s[l..r)` nghĩa là lấy các vị trí từ l tới r−1. Độ dài đoạn bằng `r-l`.

Ví dụ s=`"abc"` có các chuỗi con **không rỗng**:

```text
"a", "b", "c", "ab", "bc", "abc"
```

`"ac"` **không** phải chuỗi con của `"abc"` vì a và c không liền nhau. Tuy nhiên `"ac"` là một **subsequence** (dãy con không liên tiếp). Bài học này **chỉ** đếm substring, không đếm subsequence.

### 1.2. Tổng số lần xuất hiện của tất cả đoạn không rỗng

Mỗi cặp biên `(l,r)` với `0≤l<r≤n` xác định **một lần xuất hiện** của một chuỗi con. Số cặp như vậy:

\[
n+(n-1)+\cdots+1
=\boxed{\frac{n(n+1)}2}.
\]

Với n=5, tổng là 15.

Đây **không** phải số chuỗi con phân biệt nếu có những đoạn tạo ra cùng một giá trị chuỗi.

### 1.3. Số chuỗi con không rỗng phân biệt

Hai đoạn ở vị trí khác nhau **chỉ được tính một lần** nếu dãy ký tự của chúng bằng nhau.

Ví dụ s=`"aaaa"`:

```text
Các chuỗi con phân biệt: "a", "aa", "aaa", "aaaa"
Số phân biệt: 4
```

Trong khi tổng số lần xuất hiện của tất cả chuỗi con là:

\[
4\cdot5/2=10.
\]

Đây là sự khác nhau giữa **cardinality của tập chuỗi** và **cardinality của các lần xuất hiện theo vị trí**.

### 1.4. Số lần xuất hiện của một mẫu

Với văn bản s độ dài n và mẫu p độ dài m>0, một lần xuất hiện là chỉ số i thỏa:

\[
0\le i\le n-m,\quad s[i..i+m)=p.
\]

**Khớp chồng lấn vẫn được tính.**

Ví dụ:

```text
s = "aaaa"
p = "aa"

Vị trí khớp: 0, 1, 2
occ("aa") = 3
```

Nếu chỉ xét khớp không chồng lấn, đáp án sẽ khác; đó là một bài toán có ràng buộc riêng.

### 1.5. Mẫu rỗng và chuỗi rỗng

**Quy ước nhất quán trong bài:**

- Đếm **chuỗi con không rỗng phân biệt**, nên chuỗi rỗng `""` **không** được cộng vào kết quả distinct.
- Nếu cần tính cả `""` là một chuỗi con phân biệt, cộng **1** vào kết quả, kể cả khi s rỗng.
- Số lần xuất hiện của mẫu rỗng bằng số **ranh giới giữa các ký tự**: `n+1`. Vì vậy `occ("")=n+1`.
- Khi s rỗng, số chuỗi con **không rỗng** phân biệt bằng 0; `occ("")=1`; mọi mẫu không rỗng xuất hiện 0 lần.

Quy ước đếm mẫu rỗng có thể khác tùy đề bài. API Java trong bài chọn `n+1` để tránh nhập nhằng.

---

## 2. Ví dụ kiểm chứng trước khi học thuật toán

### 2.1. Chuỗi "ababa"

Liệt kê theo độ dài:

| Độ dài | Các chuỗi con phân biệt | Số loại |
| ---: | --- | ---: |
| 1 | `a, b` | 2 |
| 2 | `ab, ba` | 2 |
| 3 | `aba, bab` | 2 |
| 4 | `abab, baba` | 2 |
| 5 | `ababa` | 1 |

Tổng:

\[
2+2+2+2+1=\boxed{9}.
\]

Tần suất:

| Chuỗi con | Số lần xuất hiện |
| --- | ---: |
| a | 3 |
| b | 2 |
| ab | 2 |
| ba | 2 |
| aba | 2 |
| bab | 1 |
| abab | 1 |
| baba | 1 |
| ababa | 1 |

Có **5** chuỗi con phân biệt xuất hiện **ít nhất hai lần**: `a,b,ab,ba,aba`.

Tổng số lần xuất hiện trên bảng:

\[
3+2+2+2+2+1+1+1+1=15,
\]

đúng bằng `5\cdot6/2`. Đây là một **bất biến kiểm thử** rất hữu ích.

### 2.2. Chuỗi "banana"

S có n=6 nên tổng số đoạn không rỗng theo vị trí:

\[
6\cdot7/2=21.
\]

Liệt kê các chuỗi con khác nhau:

| Độ dài | Giá trị phân biệt |
| ---: | --- |
| 1 | `b, a, n` |
| 2 | `ba, an, na` |
| 3 | `ban, ana, nan` |
| 4 | `bana, anan, nana` |
| 5 | `banan, anana` |
| 6 | `banana` |

Số loại:

\[
3+3+3+3+2+1=\boxed{15}.
\]

Một số tần suất:

```text
"banana"   -> 1
"ana"      -> 2  (vị trí 1 và 3)
"na"       -> 2  (vị trí 2 và 4)
"an"       -> 2  (vị trí 1 và 3)
"a"        -> 3  (vị trí 1, 3, 5)
"n"        -> 2  (vị trí 2, 4)
"x"        -> 0
""         -> 7  (quy ước mẫu rỗng)
```

Có **5** chuỗi con phân biệt xuất hiện ít nhất hai lần: `a,n,an,na,ana`. Các đoạn `"ana"` tại vị trí 1 và 3 **chồng lấn ở một ký tự** nhưng vẫn được tính hai lần.

### 2.3. Chuỗi một ký tự lặp lại

Với `s="aaaa"`, các chuỗi con phân biệt và tần suất là:

| Chuỗi con | Số lần |
| --- | ---: |
| a | 4 |
| aa | 3 |
| aaa | 2 |
| aaaa | 1 |

Vậy:

- Số loại không rỗng phân biệt = **4**.
- Số loại xuất hiện ít nhất hai lần = **3**.
- Tổng số lần xuất hiện = `4+3+2+1=10`.

Trường hợp chuỗi lặp là bộ kiểm thử rất quan trọng để phát hiện việc **bỏ khớp chồng lấn** hoặc nhầm “số loại” với “số lần”.

---

## 3. Cách ngây thơ và vì sao cần cấu trúc nâng cao

### 3.1. Liệt kê mọi đoạn

Với n ký tự có `n(n+1)/2` đoạn không rỗng. Có thể dùng hai vòng:

```text
set = {}
for l = 0..n-1:
    for r = l+1..n:
        set.add(s[l..r))
answer = set.size()
```

Một cách mở rộng là dùng `Map<String,Integer>` để tăng số lần xuất hiện của mỗi chuỗi con, rồi truy vấn tần suất.

### 3.2. Chi phí của cách liệt kê

Số cặp `(l,r)` là O(n²), nhưng trong Java hiện đại, việc tạo một substring có thể **sao chép O(độ dài đoạn)**. Tổng độ dài của tất cả những đoạn:

\[
\sum_{m=1}^n m(n-m+1)
=\boxed{\frac{n(n+1)(n+2)}6},
\]

có bậc **Θ(n³)**. Vì vậy không nên nói cách `HashSet<String>` này luôn O(n²) thời gian.

Bộ nhớ cũng có thể rất lớn do nhiều chuỗi khác nhau được cấp phát; giới hạn chi tiết phụ thuộc cách String được lưu và số đoạn thực sự phân biệt.

### 3.3. Hash không tuyệt đối

Một cách cải thiện là dùng **rolling hash** để tính hash của từng đoạn trong O(1) sau tiền xử lý prefix/power O(n). Có thể đếm các hash khác nhau, nhưng:

- Hai chuỗi khác nhau **vẫn có thể cùng hash**.
- Nếu cần kết quả **đúng tuyệt đối**, không thể coi một cặp hash bằng nhau là bằng chứng chuỗi bằng nhau.
- Muốn loại collision bằng so ký tự thì cần bổ sung bước xác minh, ảnh hưởng thời gian.

Kỹ thuật hash hữu ích trong nhiều bài, nhưng **suffix automaton** cho công thức đếm **xác định, không phụ thuộc xác suất collision**.

---

## 4. Suffix automaton (SAM) là gì?

**Suffix automaton** của chuỗi s là một máy trạng thái hữu hạn có hướng, gồm:

- Một trạng thái gốc 0, biểu diễn chuỗi rỗng.
- Các cạnh chuyển theo ký tự.
- Mỗi trạng thái v lưu `len[v]` và `link[v]`.
- Trong mã, `next[v][c]` là trạng thái nhận được khi đọc ký tự c.

Khi bắt đầu từ gốc rồi đọc một chuỗi p qua các cạnh chuyển:

- Nếu mọi cạnh tồn tại, p là **một chuỗi con của s**.
- Nếu thiếu một cạnh, p **không xuất hiện** trong s.

SAM có thể được xây **tăng dần**, xử lý từng ký tự của s từ trái sang phải. Với bảng chữ cái cố định, số trạng thái là **O(n)**, tối đa **2n−1 trạng thái khi n≥1** (với n=1, có 2 trạng thái; do đó cận thường viết tối đa 2n cho mọi n≥1). Chuỗi rỗng có đúng trạng thái gốc.

### 4.1. Trường len[v]

`len[v]` là **độ dài lớn nhất** của một chuỗi con được biểu diễn bởi trạng thái v.

Ví dụ một trạng thái có `len=5` và suffix link đến một trạng thái có `len=2` sẽ đại diện cho các độ dài 3,4,5; đó là **3 chuỗi khác nhau**.

### 4.2. Trường link[v]

`link[v]` là **suffix link**, đưa trạng thái v đến trạng thái biểu diễn một hậu tố thích hợp dài nhất thuộc **lớp endpos khác**.

Với mọi trạng thái v khác gốc:

\[
len[link[v]]<len[v].
\]

Gốc có `link[0]=-1`.

Suffix link không phải một cạnh chuyển ký tự; nó là cấu trúc liên hệ giữa **những lớp hậu tố** và được dùng khi tạo SAM cũng như khi cộng dồn số lần xuất hiện.

### 4.3. End positions — tập vị trí kết thúc

Với một chuỗi con p không rỗng của s, định nghĩa:

\[
endpos(p)=\{r\mid s[r-|p|+1..r+1)=p\}.
\]

Đây là tập các **chỉ số kết thúc** của mọi lần xuất hiện của p trong s.

Ví dụ s=`"ababa"`:

```text
endpos("aba") = {2, 4}
endpos("ba")  = {2, 4}
endpos("a")   = {0, 2, 4}
```

Vì `"aba"` và `"ba"` có cùng tập vị trí kết thúc, chúng có **cùng số lần xuất hiện = 2**.

Các chuỗi con có cùng `endpos` thuộc cùng một **lớp tương đương endpos**, được biểu diễn bởi **một trạng thái SAM**.

### 4.4. Một trạng thái có thể biểu diễn nhiều chuỗi

Đây là điểm dễ nhầm nhất: **mỗi trạng thái SAM không tương ứng một chuỗi duy nhất**.

Với v khác gốc, các chuỗi được đại diện bởi v có những độ dài liên tiếp:

\[
len[link[v]]+1,\ len[link[v]]+2,\ \ldots,\ len[v].
\]

Số chuỗi con khác nhau được biểu diễn bởi v là:

\[
\boxed{\Delta(v)=len[v]-len[link[v]].}
\]

Các nhóm này **rời nhau theo giá trị chuỗi**, và hợp của chúng là toàn bộ tập chuỗi con **không rỗng** của s.

### 4.5. Cạnh chuyển và suffix link có nhiệm vụ khác nhau

- Dùng `next` để **đọc một chuỗi mẫu p** từ root rồi tìm trạng thái tương ứng.
- Dùng `link` để **liên hệ các lớp hậu tố**, cập nhật cấu trúc và truyền số đếm.
- Không đi theo suffix link để đọc ký tự kế tiếp của mẫu; làm vậy sẽ thay đổi bài toán.

---

## 5. Tạo SAM từ trái sang phải

Ta duy trì biến `last`: trạng thái biểu diễn toàn bộ prefix s đã xây xong. Ban đầu:

```text
root = 0
len[root] = 0
link[root] = -1
last = root
```

Mỗi khi thêm ký tự c vào cuối prefix, tạo một trạng thái `cur`:

```text
len[cur] = len[last] + 1
occ[cur] = 1
```

Giá trị `occ=1` ở cur biểu thị **một vị trí kết thúc mới** của prefix hiện tại. Chưa cộng dồn gì ở bước này.

### 5.1. Thêm các cạnh chuyển còn thiếu

Bắt đầu `p=last`. Khi `p!=-1` và chưa có cạnh chuyển theo c từ p, thêm:

```text
next[p][c] = cur
p = link[p]
```

Ta đi theo suffix links để mọi hậu tố trước đó chưa có nối bằng c nay có thể chuyển đến cur.

### 5.2. Nếu đi đến ngoài gốc

Nếu p trở thành −1, không có một trạng thái cũ nào xử lý cạnh chuyển phù hợp theo c. Khi đó:

```text
link[cur] = root
```

### 5.3. Nếu gặp một cạnh đã tồn tại

Giả sử `q=next[p][c]`.

Có hai trường hợp:

- Nếu `len[p]+1==len[q]`, có thể đặt `link[cur]=q`.
- Nếu `len[p]+1<len[q]`, q đang biểu diễn lớp có độ dài quá rộng so với liên kết mới. Phải tạo một **clone**.

### 5.4. Clone là gì?

Tạo một trạng thái `clone`:

- Sao chép mọi cạnh chuyển của q.
- Sao chép suffix link cũ của q.
- Đặt `len[clone]=len[p]+1`.
- Đặt `occ[clone]=0` vì clone **không ứng với một vị trí prefix kết thúc mới**.
- Chuyển các cạnh theo c trước đó đi tới q trên chuỗi suffix links thích hợp sang clone.
- Đặt `link[q]=clone` và `link[cur]=clone`.

Clone là một bước **tách lớp endpos** để bảo toàn những bất biến của SAM, không có nghĩa vừa thêm một ký tự mới vào văn bản lần nữa.

### 5.5. Vì sao clone có occ=0?

Mỗi lần thật sự đọc thêm một ký tự của text, ta tạo đúng một `cur` đại diện cho prefix mới, tương ứng **một vị trí kết thúc mới**. Clone chỉ sao chép trạng thái để tách cấu trúc, **không thêm vị trí trong text**.

Nếu gán occ[clone]=1 trước khi truyền theo suffix links, ta sẽ **đếm thừa** các lần xuất hiện. Đây là lỗi khó thấy vì countDistinct có thể vẫn đúng nhưng occurrence count sai.

### 5.6. Giả mã xây SAM

```text
EXTEND(c):
    cur = newState()
    len[cur] = len[last] + 1
    occ[cur] = 1

    p = last
    while p != -1 and next[p][c] missing:
        next[p][c] = cur
        p = link[p]

    if p == -1:
        link[cur] = root
    else:
        q = next[p][c]

        if len[p] + 1 == len[q]:
            link[cur] = q
        else:
            clone = newState()
            next[clone] = copy(next[q])
            len[clone] = len[p] + 1
            link[clone] = link[q]
            occ[clone] = 0

            while p != -1 and next[p][c] == q:
                next[p][c] = clone
                p = link[p]

            link[q] = clone
            link[cur] = clone

    last = cur
```

Tại cuối mỗi lần thêm, `last=cur`. Sau khi xử lý hết n ký tự, máy đã nhận biết mọi substring của s.

---

## 6. Công thức đếm chuỗi con phân biệt

Với mọi trạng thái v khác root, số chuỗi con phân biệt được biểu diễn bởi v:

\[
\Delta(v)=len[v]-len[link[v]].
\]

Vì các lớp endpos chia toàn bộ chuỗi con không rỗng thành các nhóm không giao nhau:

\[
\boxed{
DistinctNonEmpty(s)
=
\sum_{v\ne root}
\bigl(len[v]-len[link[v]]\bigr).
}
\]

### 6.1. Vì sao không đơn giản bằng số trạng thái −1?

Một trạng thái có thể biểu diễn **nhiều chuỗi** với các độ dài trong một khoảng. Nếu chỉ đếm trạng thái, ta sẽ bỏ những chuỗi khác nhau nhưng có cùng endpos.

Chính chênh lệch `len[v]-len[link[v]]` cho biết có **bao nhiêu giá trị chuỗi khác nhau** thuộc trạng thái ấy.

### 6.2. Cận trên của kết quả

Một chuỗi dài n có tổng cộng `n(n+1)/2` đoạn không rỗng theo vị trí, do đó:

\[
0\le DistinctNonEmpty(s)\le\frac{n(n+1)}2.
\]

Với n đủ lớn, `n(n+1)/2` **vượt int 32-bit**. Vì vậy chương trình Java dùng **long** cho số chuỗi con phân biệt và tổng số lần xuất hiện.

### 6.3. Xây theo prefix

Khi nối thêm một ký tự mới vào cuối s, các chuỗi con mới xuất hiện nếu có đều phải **kết thúc ở ký tự vừa thêm**, tức là những hậu tố mới của prefix.

Trong SAM đã cập nhật, số chuỗi con mới ở bước này bằng:

\[
len[last]-len[link[last]].
\]

Cộng cho từng prefix cũng cho tổng số distinct cuối cùng. Tuy nhiên công thức tổng qua **tất cả trạng thái** ở trên thuận tiện hơn khi cần đồng thời dùng endpos/occ.

---

## 7. Đếm số lần xuất hiện của mọi substring

### 7.1. Occ ban đầu chưa phải tần suất cuối

Khi tạo `cur` cho mỗi ký tự mới, đặt:

```text
occ[cur] = 1
```

Khi tạo clone:

```text
occ[clone] = 0
```

Sau khi xây xong toàn bộ SAM, giá trị này **chưa** phải số lần xuất hiện của các chuỗi trong trạng thái. Ta cần **truyền số đếm theo suffix link**.

### 7.2. Truyền từ trạng thái dài sang ngắn

Vì:

\[
len[link[v]]<len[v],
\]

ta sắp các trạng thái theo `len` **giảm dần**. Với từng v khác root:

```text
occ[link[v]] += occ[v]
```

Ý nghĩa: mọi vị trí kết thúc đóng góp cho lớp của v cũng đóng góp cho lớp hậu tố `link[v]`.

Thực hiện ở thứ tự độ dài **giảm dần** đảm bảo rằng khi truyền từ v lên link[v], v đã nhận đủ những đóng góp từ các hậu duệ dài hơn.

### 7.3. Kết quả ở từng trạng thái

Sau khi truyền:

\[
\boxed{occ[v]=|endpos(v)|.}
\]

Mọi substring p được nhận tại trạng thái v có **chính xác occ[v] lần xuất hiện** trong text.

### 7.4. Tìm tần suất của mẫu p

Để trả `countOccurrences(p)`:

1. Nếu p rỗng, trả `n+1` theo quy ước của bài.
2. Bắt đầu từ trạng thái root.
3. Với từng ký tự c của p, đi theo cạnh `next[state][c]`.
4. Nếu một cạnh không tồn tại, trả 0.
5. Khi đọc xong p, trả `occ[state]`.

Thời gian truy vấn:

\[
\boxed{O(|p|)}
\]

với bảng chữ cái cố định và lookup transition O(1).

Không cần quét lại toàn bộ s cho mỗi mẫu. Đây là ưu thế lớn khi phải trả **nhiều câu hỏi tần suất** trên cùng text.

### 7.5. Mẫu rỗng là ngoại lệ

Root biểu diễn chuỗi rỗng nhưng giá trị occ[root] sau propagation không được dùng trực tiếp để trả `n+1`. Mẫu rỗng theo quy ước xuất hiện ở **n+1 ranh giới**, còn cách khởi tạo occ theo n lần thêm prefix thường cộng cho root theo **n vị trí kết thúc**.

Vì vậy mã phải xử lý:

```java
if (pattern.isEmpty()) {
    return textLength + 1L;
}
```

trước khi đi qua transitions. Đây không phải một trường hợp “đếm sai”, mà là **sự khác nhau trong quy ước định nghĩa endpos của chuỗi rỗng**.

---

## 8. Hai đại lượng tổng hợp từ len và occ

Một trạng thái v khác root biểu diễn `Delta(v)` chuỗi con phân biệt. Các chuỗi ấy đều có cùng số lần xuất hiện `occ[v]`.

### 8.1. Số chuỗi con phân biệt xuất hiện ít nhất hai lần

\[
\boxed{
RepeatedDistinct(s)=
\sum_{\substack{v\ne root\\occ[v]\ge2}}
\Delta(v).
}
\]

Đây là số **giá trị chuỗi khác nhau** có ít nhất hai lần xuất hiện, **không** phải tổng số cặp vị trí lặp.

Ví dụ `"ababa"` có 5 chuỗi con phân biệt lặp: `a,b,ab,ba,aba`.

### 8.2. Tổng số lần xuất hiện của mọi chuỗi con không rỗng

\[
\boxed{
TotalOccurrences=
\sum_{v\ne root}\Delta(v)\cdot occ[v].
}
\]

Mỗi trạng thái chứa Delta chuỗi khác nhau, mỗi chuỗi xuất hiện occ lần, nên tích là số lần xuất hiện mà nhóm ấy đóng góp.

Ta phải có:

\[
\boxed{
\sum_{v\ne root}\Delta(v)\cdot occ[v]
=\frac{n(n+1)}2.
}
\]

Vế phải là tổng số cặp biên `(l,r)` với `l<r`, tức tổng số đoạn không rỗng **theo vị trí**.

Đây là một **bất biến kiểm thử rất mạnh**: nếu tổng bên trái khác `n(n+1)/2`, việc xây SAM, clone hoặc truyền occ có thể bị sai.

### 8.3. Ví dụ

Với `"banana"`:

- DistinctNonEmpty = **15**.
- RepeatedDistinct = **5**.
- TotalOccurrences = **21**.
- countOccurrences("ana") = **2**.
- countOccurrences("a") = **3**.

Tuy có 15 chuỗi con khác nhau, tổng cộng vẫn có 21 lần xuất hiện khi tính tất cả các đoạn theo vị trí.

---

## 9. Sắp trạng thái theo len để truyền occ

Có thể sắp các id trạng thái bằng `Comparator.comparingInt(v -> len[v])`, nhưng vì `0≤len[v]≤n`, ta có thể dùng **counting sort** tuyến tính theo độ dài.

### 9.1. Đếm theo độ dài

```text
count[length] = số trạng thái có len bằng length
```

Tính prefix sum để biết vùng chỉ số của từng nhóm độ dài trong mảng order. Đi qua id trạng thái và đặt từng id vào vị trí phù hợp.

### 9.2. Duyệt ngược

Mảng order sau counting sort có `len` **không giảm**. Duyệt từ cuối mảng tới đầu (bỏ root):

```text
for id in order reversed except root:
    if link[id] >= 0:
        occ[link[id]] += occ[id]
```

Vì mọi suffix link dẫn đến trạng thái có len **nhỏ hơn**, đóng góp luôn đi theo chiều đúng.

### 9.3. Tại sao không được propagate trong lúc đang thêm ký tự?

Khi thêm ký tự về sau, SAM có thể tạo clone và đổi các suffix links. Nếu cộng dồn occ quá sớm rồi tiếp tục sửa các liên kết mà không có cơ chế cập nhật bổ sung, kết quả sẽ không còn nhất quán.

Cách dễ chứng minh và cài đúng là:

1. Xây **toàn bộ** cấu trúc SAM.
2. Khởi tạo occ của state thật và clone **ngay khi tạo**.
3. Sau cùng, **truyền đúng một lần** theo thứ tự len giảm dần.

---

## 10. Java 17+ chạy độc lập

Bản dưới đây dành cho văn bản và mẫu gồm **các chữ cái Latin thường a..z**. Để giữ cấu trúc dễ học, mỗi trạng thái có mảng chuyển `int[26]`. Ký tự ngoài phạm vi bị từ chối rõ ràng, thay vì âm thầm xử lý sai index.

Với bảng chữ cái cố định kích thước 26, quá trình xây SAM và truyền occ mất **O(n)** thời gian, lưu O(n) trạng thái và O(26n) ô chuyển, tức O(n) bộ nhớ theo n.

Tệp: **`DistinctSubstringOccurrenceDemo.java`**.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class DistinctSubstringOccurrenceDemo {

    public static final class SuffixAutomaton {
        private static final int ALPHABET = 26;

        private static final class State {
            int len = 0;
            int link = -1;
            final int[] next = new int[ALPHABET];
            long occ = 0;

            State() {
                Arrays.fill(next, -1);
            }
        }

        private final List<State> states = new ArrayList<>();
        private final int textLength;
        private int last = 0;

        public SuffixAutomaton(String text) {
            Objects.requireNonNull(text, "text");

            for (int i = 0; i < text.length(); i++) {
                toIndex(text.charAt(i));
            }

            textLength = text.length();

            // Root state: empty string.
            states.add(new State());

            for (int i = 0; i < text.length(); i++) {
                extend(toIndex(text.charAt(i)));
            }

            propagateOccurrences();
        }

        private static int toIndex(char ch) {
            if (ch < 'a' || ch > 'z') {
                throw new IllegalArgumentException(
                        "Only lowercase a..z is supported");
            }
            return ch - 'a';
        }

        private void extend(int c) {
            int cur = states.size();
            State current = new State();
            current.len = states.get(last).len + 1;
            current.occ = 1;
            states.add(current);

            int p = last;

            while (p != -1 && states.get(p).next[c] == -1) {
                states.get(p).next[c] = cur;
                p = states.get(p).link;
            }

            if (p == -1) {
                current.link = 0;
            } else {
                int q = states.get(p).next[c];

                if (states.get(p).len + 1
                        == states.get(q).len) {
                    current.link = q;
                } else {
                    int clone = states.size();
                    State copy = new State();
                    State original = states.get(q);

                    copy.len = states.get(p).len + 1;
                    copy.link = original.link;

                    System.arraycopy(
                            original.next, 0,
                            copy.next, 0, ALPHABET);

                    // Clone is NOT a new ending position.
                    copy.occ = 0;
                    states.add(copy);

                    while (p != -1
                            && states.get(p).next[c] == q) {
                        states.get(p).next[c] = clone;
                        p = states.get(p).link;
                    }

                    original.link = clone;
                    current.link = clone;
                }
            }

            last = cur;
        }

        private void propagateOccurrences() {
            int n = textLength;
            int size = states.size();

            int[] count = new int[n + 1];

            for (State state : states) {
                count[state.len]++;
            }

            for (int len = 1; len <= n; len++) {
                count[len] += count[len - 1];
            }

            // States ordered by nondecreasing len.
            int[] order = new int[size];

            for (int v = size - 1; v >= 0; v--) {
                int length = states.get(v).len;
                order[--count[length]] = v;
            }

            // Longer endpos classes contribute to
            // their shorter suffix-link classes.
            for (int i = size - 1; i > 0; i--) {
                int v = order[i];
                int parent = states.get(v).link;

                if (parent >= 0) {
                    states.get(parent).occ +=
                            states.get(v).occ;
                }
            }
        }

        private long lengthContribution(int v) {
            State state = states.get(v);
            return (long) state.len
                    - states.get(state.link).len;
        }

        public long countDistinctNonEmpty() {
            long total = 0;

            for (int v = 1; v < states.size(); v++) {
                total += lengthContribution(v);
            }

            return total;
        }

        public long countRepeatedDistinctNonEmpty() {
            long total = 0;

            for (int v = 1; v < states.size(); v++) {
                if (states.get(v).occ >= 2) {
                    total += lengthContribution(v);
                }
            }

            return total;
        }

        public long totalNonEmptyOccurrences() {
            long total = 0;

            for (int v = 1; v < states.size(); v++) {
                total += lengthContribution(v)
                        * states.get(v).occ;
            }

            return total;
        }

        public long occurrences(String pattern) {
            Objects.requireNonNull(pattern, "pattern");

            // Validate the complete query even if its
            // first prefix does not occur in the text.
            for (int i = 0; i < pattern.length(); i++) {
                toIndex(pattern.charAt(i));
            }

            if (pattern.isEmpty()) {
                return (long) textLength + 1L;
            }

            int v = 0;

            for (int i = 0; i < pattern.length(); i++) {
                int c = toIndex(pattern.charAt(i));
                int nextState = states.get(v).next[c];

                if (nextState == -1) {
                    return 0;
                }

                v = nextState;
            }

            return states.get(v).occ;
        }

        public int stateCount() {
            return states.size();
        }
    }

    public static void main(String[] args) {
        SuffixAutomaton first =
                new SuffixAutomaton("ababa");

        System.out.println(
                "ababa distinct nonempty: "
                        + first.countDistinctNonEmpty());
        System.out.println(
                "ababa repeated distinct: "
                        + first.countRepeatedDistinctNonEmpty());
        System.out.println(
                "ababa total nonempty occurrences: "
                        + first.totalNonEmptyOccurrences());
        System.out.println(
                "ababa occ(aba): "
                        + first.occurrences("aba"));
        System.out.println(
                "ababa occ(ba): "
                        + first.occurrences("ba"));
        System.out.println(
                "ababa occ(a): "
                        + first.occurrences("a"));
        System.out.println(
                "ababa occ(bab): "
                        + first.occurrences("bab"));
        System.out.println(
                "ababa occ(c): "
                        + first.occurrences("c"));
        System.out.println(
                "ababa occ(empty): "
                        + first.occurrences(""));

        SuffixAutomaton banana =
                new SuffixAutomaton("banana");

        System.out.println(
                "banana distinct nonempty: "
                        + banana.countDistinctNonEmpty());
        System.out.println(
                "banana repeated distinct: "
                        + banana.countRepeatedDistinctNonEmpty());
        System.out.println(
                "banana total nonempty occurrences: "
                        + banana.totalNonEmptyOccurrences());
        System.out.println(
                "banana occ(ana): "
                        + banana.occurrences("ana"));
        System.out.println(
                "banana occ(na): "
                        + banana.occurrences("na"));
        System.out.println(
                "banana occ(a): "
                        + banana.occurrences("a"));
        System.out.println(
                "banana occ(banana): "
                        + banana.occurrences("banana"));
        System.out.println(
                "banana states: " + banana.stateCount());

        SuffixAutomaton same =
                new SuffixAutomaton("aaaa");

        System.out.println(
                "aaaa distinct nonempty: "
                        + same.countDistinctNonEmpty());
        System.out.println(
                "aaaa occ(aa): "
                        + same.occurrences("aa"));

        SuffixAutomaton empty =
                new SuffixAutomaton("");

        System.out.println(
                "empty distinct nonempty: "
                        + empty.countDistinctNonEmpty());
        System.out.println(
                "empty occ(empty): "
                        + empty.occurrences(""));

        boolean invalidTextRejected = false;

        try {
            new SuffixAutomaton("baNaNa");
        } catch (IllegalArgumentException ex) {
            invalidTextRejected = true;
        }

        System.out.println(
                "nonlowercase text rejected: "
                        + invalidTextRejected);

        boolean invalidPatternRejected = false;

        try {
            first.occurrences("A");
        } catch (IllegalArgumentException ex) {
            invalidPatternRejected = true;
        }

        System.out.println(
                "nonlowercase pattern rejected: "
                        + invalidPatternRejected);
    }
}
```

### Biên dịch và chạy

Dùng JDK 17 hoặc mới hơn:

```bash
javac DistinctSubstringOccurrenceDemo.java
java DistinctSubstringOccurrenceDemo
```

**Đầu ra chuẩn:**

```text
ababa distinct nonempty: 9
ababa repeated distinct: 5
ababa total nonempty occurrences: 15
ababa occ(aba): 2
ababa occ(ba): 2
ababa occ(a): 3
ababa occ(bab): 1
ababa occ(c): 0
ababa occ(empty): 6
banana distinct nonempty: 15
banana repeated distinct: 5
banana total nonempty occurrences: 21
banana occ(ana): 2
banana occ(na): 2
banana occ(a): 3
banana occ(banana): 1
banana states: 10
aaaa distinct nonempty: 4
aaaa occ(aa): 3
empty distinct nonempty: 0
empty occ(empty): 1
nonlowercase text rejected: true
nonlowercase pattern rejected: true
```

### 10.1. Ý nghĩa các trường dữ liệu

- `State.len`: chiều dài lớn nhất của chuỗi con thuộc lớp endpos.
- `State.link`: suffix link tới lớp hậu tố dài nhất khác lớp hiện tại.
- `State.next[c]`: cạnh chuyển theo ký tự c từ bảng chữ cái a..z.
- `State.occ`: **trước truyền** là 1 ở state được tạo khi đọc ký tự mới, 0 ở clone; **sau truyền** là số lần xuất hiện của mỗi chuỗi thuộc lớp đó.
- `last`: state của toàn bộ prefix vừa xử lý.
- `textLength`: độ dài n cần cho count array, quy ước empty pattern và các thống kê.

### 10.2. Tại sao lưu transitions bằng int[26]?

Bài mẫu giả định alphabet cố định 26 chữ thường, nên tra một cạnh O(1). Mỗi state cấp phát một mảng 26 phần tử, không phụ thuộc vào độ dài text.

Đây là một **giả thiết cố ý** cho Java 17 đơn giản. Mọi ký tự ngoài `'a'..'z'` được từ chối; không được nhập Unicode, chữ hoa, khoảng trắng hay dấu tiếng Việt rồi mong code tự hỗ trợ.

Nếu cần chuỗi Unicode tổng quát:

- Có thể mã hóa thành dãy **code point** và **nén bảng chữ cái** nếu biết trước tất cả ký tự.
- Hoặc thay `int[26]` bằng cấu trúc map chuyển theo ký tự/code point.
- Phải phân biệt chỉ số **UTF-16 code unit**, **Unicode code point** và **grapheme cluster** khi trả vị trí.

Bản mẫu **chỉ trả số lần**, không trả từng vị trí, nên không gặp vấn đề ánh xạ chỉ số ra ngoài. Tuy vậy quy tắc alphabet phải được nêu rõ.

### 10.3. Vì sao kiểm tra query trước khi tìm?

Mã quét pattern để kiểm tra tất cả ký tự thuộc a..z trước khi đi theo edges. Nhờ thế một query có ký tự không hợp lệ **luôn ném IllegalArgumentException**, kể cả khi một prefix hợp lệ trước đó đã thiếu cạnh.

Nếu kiểm tra từng ký tự và trả 0 ngay khi thiếu cạnh, có thể vô tình **không phát hiện ký tự sai** nằm ở phần còn lại. Đây là lựa chọn hợp đồng API chứ không phải bắt buộc của toán học SAM.

### 10.4. Vì sao dùng long?

Số distinct có thể lên tới `n(n+1)/2`. Nếu n=100000 thì cận trên bằng **5,000,050,000**, vượt `int`.

Bởi vậy các phép tính tổng và `occ` được lưu bằng `long`. Số state, len và id vẫn dùng int vì Java array/list index dùng int và kích thước dữ liệu có giới hạn thực tế.

### 10.5. Vì sao clone không cộng occ?

Clone không xuất hiện như một prefix mới trong text. Nó chỉ tách trạng thái do việc sửa suffix link. `copy.occ=0` là điều kiện cốt lõi; nếu gán `copy.occ=1`, tần suất có thể bị tăng sai mà công thức distinct vẫn cho giá trị có vẻ hợp lý.

### 10.6. Vì sao truyền occ sau khi xây xong?

Các suffix links có thể đổi khi tạo clone. Chỉ sau khi thêm toàn bộ ký tự, cấu trúc đã ổn định. Counting sort theo len đảm bảo **mọi state dài được truyền lên link ngắn** trước khi link ấy tiếp tục truyền lên trên.

### 10.7. Vì sao banana có 10 trạng thái?

S=`"banana"` gồm 6 ký tự nhưng một số lớp endpos cần tách clone. SAM được xây có **10 trạng thái** (kể cả root), khác số ký tự và khác số substring distinct 15.

Không có mối quan hệ “mỗi trạng thái tương đương đúng một chuỗi con”. Số trạng thái vẫn O(n), còn distinct có thể O(n²).

---

## 11. Chứng minh công thức đếm distinct

Một SAM biểu diễn các substring của s qua đường đi từ root. Hai chuỗi khác nhau có thể dẫn tới cùng v, chính khi chúng nằm trong một lớp endpos.

Mỗi state v khác root đại diện cho những chuỗi có độ dài:

\[
len[link[v]]+1,\ldots,len[v].
\]

Trong mỗi độ dài thuộc khoảng này, v đại diện **đúng một chuỗi con cụ thể**; các độ dài khác nhau cho chuỗi khác nhau.

Vậy số chuỗi con đại diện bởi v bằng:

\[
len[v]-len[link[v]].
\]

Không có chuỗi con nào nằm đồng thời ở hai lớp endpos khác nhau; các lớp phân hoạch toàn bộ tập chuỗi con không rỗng. Cộng qua các v khác root:

\[
DistinctNonEmpty(s)=
\sum_{v>0}(len[v]-len[link[v]]).
\]

### 11.1. Hai bước để kiểm tra chứng minh trên ví dụ

Đối với s=`"ababa"`:

- Kết quả distinct bằng 9 theo công thức SAM.
- Liệt kê trực tiếp theo độ dài ở mục 2 cũng cho 9.

Đối với s=`"banana"`:

- Công thức SAM cho 15.
- Liệt kê 15 chuỗi khác nhau ở mục 2.

Các ví dụ không thay thế chứng minh tổng quát, nhưng là kiểm chứng thực dụng của các bất biến SAM.

### 11.2. Vì sao công thức có thể cho số lớn hơn số state?

Vì một state đóng góp `Delta(v)`, có thể bằng 2,3,... chứ không nhất thiết bằng 1. Trạng thái là **lớp tương đương**, không phải nút của trie chứa một chuỗi đơn lẻ.

---

## 12. Chứng minh cách đếm occurrence

### 12.1. Khi đọc một ký tự mới, điều gì tăng?

Mỗi ký tự mới của text tạo ra một **vị trí kết thúc mới**. State `cur` của prefix mới nhận dấu `occ[cur]=1`; điều này tương đương đánh dấu “prefix kết thúc ở đây”.

Với n ký tự, có đúng n dấu terminal được đặt vào n state tạo mới tương ứng; clone không nhận dấu vì không tạo vị trí mới.

### 12.2. Vì sao truyền theo suffix link?

Mọi hậu tố của một prefix cùng **kết thúc tại vị trí cuối prefix**. Các lớp endpos của các hậu tố đi theo chuỗi suffix links từ state prefix tới root.

Do đó dấu terminal của một prefix cần đóng góp cho:

- State của chính prefix.
- Các state suffix link đại diện các hậu tố thích hợp.
- Tiếp tục lên root.

Tổng đóng góp nhận được tại v chính là số vị trí kết thúc của mọi chuỗi trong lớp v:

\[
occ[v]=|endpos(v)|.
\]

### 12.3. Vì sao thứ tự len giảm dần quan trọng?

Với mọi v khác root, `len[link[v]]<len[v]`. Nếu truyền theo độ dài giảm, mọi hậu duệ có độ dài lớn hơn đã gửi số đếm lên v trước khi v gửi tiếp lên parent.

Nếu truyền theo thứ tự id tạo trạng thái, clone có thể xuất hiện **sau** state mà nó liên kết, làm các đóng góp đến muộn không được truyền tiếp. Vì thế không nên phụ thuộc vào id hay thứ tự tạo trạng thái; hãy sắp rõ theo len.

### 12.4. Vì sao mọi chuỗi trong cùng state có số lần xuất hiện bằng nhau?

Tính chất định nghĩa của lớp endpos: mọi chuỗi tương đương được biểu diễn bởi v có **cùng tập vị trí kết thúc**. Số lần xuất hiện của mỗi chuỗi bằng cardinality của tập ấy, tức `occ[v]`.

Vì vậy một mẫu p sau khi đi các transitions đến v có số lần xuất hiện chính xác bằng `occ[v]`, không cần biết nó tương ứng độ dài nào trong khoảng của v.

### 12.5. Tổng occurrence bằng n(n+1)/2

Mỗi vị trí kết thúc r của s có r+1 đoạn không rỗng kết thúc tại đó. Nếu cộng số lần xuất hiện theo **tất cả giá trị substring phân biệt**, mỗi đoạn ở vị trí được đếm đúng một lần trong tần suất của giá trị chuỗi tương ứng.

Vì vậy:

\[
\sum_{p\in DistinctNonEmptySubstrings(s)}occ(p)
=\sum_{r=0}^{n-1}(r+1)
=\frac{n(n+1)}2.
\]

Chia các p theo state v cho công thức:

\[
\sum_{v>0}\Delta(v)\,occ[v]
=\frac{n(n+1)}2.
\]

Đây vừa là chứng minh toán học vừa là **oracle kiểm thử** cho mã.

---

## 13. Suffix array + LCP: một cách đếm distinct khác

**Suffix array (SA)** sắp xếp mọi hậu tố s[i..n) theo thứ tự từ điển. Một suffix dài k có k prefix không rỗng; mỗi prefix ấy là một substring của s.

Nếu cộng độ dài của tất cả suffix, ta nhận:

\[
1+2+\cdots+n=\frac{n(n+1)}2
\]

ứng viên theo vị trí.

Nhưng nhiều prefix của các suffix khác nhau trùng nhau. Khi suffix được sắp từ điển, những prefix trùng với suffix đứng trước được đo bằng **longest common prefix (LCP)**.

### 13.1. Công thức

Gọi `LCP[i]` là độ dài prefix chung dài nhất của suffix ở vị trí i và suffix ngay trước nó trong SA, với `LCP[0]=0`:

\[
\boxed{
DistinctNonEmpty(s)
=
\frac{n(n+1)}2-\sum_{i=1}^{n-1}LCP[i].
}
\]

Mỗi suffix trong thứ tự SA chỉ đóng góp những prefix **dài hơn LCP với suffix trước**, bởi các prefix còn lại đã xuất hiện trong nhóm suffix trước đó.

### 13.2. Ví dụ banana

Các hậu tố đã sắp:

| Thứ tự | Suffix | LCP với suffix trước |
| ---: | --- | ---: |
| 0 | a | 0 |
| 1 | ana | 1 |
| 2 | anana | 3 |
| 3 | banana | 0 |
| 4 | na | 0 |
| 5 | nana | 2 |

Tổng LCP:

\[
1+3+0+0+2=6.
\]

Có tổng 21 đoạn theo vị trí, nên:

\[
DistinctNonEmpty("banana")=21-6=\boxed{15}.
\]

### 13.3. Đếm số lần xuất hiện bằng suffix array

Mọi suffix bắt đầu bằng mẫu p nằm **liên tiếp** trong thứ tự từ điển. Có thể tìm đoạn chỉ số suffix phù hợp bằng hai lần tìm kiếm nhị phân biên trong SA.

- Mỗi suffix trong đoạn khớp ứng với một **vị trí bắt đầu** của p.
- Kích thước đoạn chính là `occ(p)`.
- Nếu muốn danh sách vị trí, có thể trả về các chỉ số bắt đầu ấy.

Việc so sánh một suffix với p có thể tốn O(|p|); với SA tiêu chuẩn, truy vấn biên thường O(|p| log n) nếu không dùng những tối ưu LCP bổ sung.

### 13.4. Chọn SAM hay suffix array?

- **SAM:** xây O(n) với alphabet cố định; đếm distinct O(n); tần suất mỗi mẫu O(|p|); cấu trúc dễ thích hợp cho **nhiều truy vấn chuỗi con**.
- **SA + LCP:** sắp xếp hậu tố bằng thuật toán phù hợp (thường O(n log n) ở các phiên bản xây đơn giản), LCP O(n), distinct bằng công thức trừ tổng LCP; thuận lợi cho các bài về thứ tự từ điển và vị trí hậu tố.

Hai cấu trúc đều giải chính xác, không cần giả thiết hash không collision.

---

## 14. Những lỗi thường gặp

1. **Nhầm substring với subsequence**, tính cả các ký tự không liên tiếp.
2. **Nhầm tổng số đoạn n(n+1)/2 với số distinct**, bỏ qua các giá trị trùng.
3. **Không đếm khớp chồng lấn**, ví dụ `"aa"` trong `"aaaa"` phải có 3 lần.
4. **Coi mỗi SAM state là một chuỗi**, quên `len[v]-len[link[v]]`.
5. **Đếm cả chuỗi rỗng trong distinct** trong khi đề yêu cầu nonempty.
6. **Trả occ(root) cho mẫu rỗng**, thay vì áp dụng quy ước n+1.
7. **Gán occ=1 cho clone**, khiến occurrence count bị thừa.
8. **Chỉ gán occ=1 cho state cuối**, quên mỗi prefix mới tạo một vị trí kết thúc.
9. **Cộng occ theo thứ tự state id**, không bảo đảm suffix link được xử lý sau hậu duệ.
10. **Propagate trước khi kết thúc xây SAM**, rồi thay đổi clone/suffix links mà không cập nhật lại.
11. **Quên clone khi len[p]+1<len[q]**, phá bất biến endpos.
12. **Sao chép len của q sang clone**, trong khi clone phải có `len=len[p]+1`.
13. **Không sao chép transitions hoặc suffix link của q sang clone**, dẫn tới automaton thiếu đường.
14. **Quên sửa link[q] và link[cur] thành clone**, làm sai cấu trúc suffix links.
15. **Redirect mọi transition đi tới q**, thay vì chỉ những transition phù hợp dọc chuỗi suffix links.
16. **Không khởi tạo next=-1**, khiến giá trị mặc định 0 bị hiểu nhầm là cạnh tới root.
17. **Truy vấn từ last thay vì root**, làm kiểm tra chuỗi con không đúng.
18. **Đi theo suffix link khi đọc mẫu**, trong khi truy vấn phải dùng next theo ký tự.
19. **Dùng int cho số distinct**, có thể tràn khi n lớn.
20. **Nghĩ long cho phép mọi kích thước**, dù RAM, mảng và số state còn giới hạn.
21. **Nhập chữ hoa/khoảng trắng/Unicode vào bản a..z**, gây lỗi nếu không kiểm tra alphabet.
22. **Nhầm code unit UTF-16 với code point**, khi mở rộng sang Unicode.
23. **Nhầm số chuỗi con lặp phân biệt với tổng số lần lặp**, hai đại lượng khác nhau.
24. **Tin hash bằng nhau là chuỗi bằng nhau tuyệt đối**, quên collision.
25. **Dùng HashSet<String> và tuyên bố chắc chắn O(n²)**, bỏ qua chi phí tạo/chép chuỗi.
26. **Bỏ test text rỗng**, nơi chỉ có root và query rỗng phải trả 1.
27. **Bỏ test một ký tự lặp**, khiến lỗi propagation không lộ rõ.
28. **Không kiểm tra tổng trọng số occurrences**, bỏ mất bất biến `sum Delta·occ=n(n+1)/2`.
29. **Tưởng SAM tự trả danh sách vị trí khớp**, trong khi `occ` chỉ lưu số đếm; lấy toàn bộ vị trí cần thêm dữ liệu/cơ chế.
30. **Đếm cả những mẫu không có trong text**, dù truy vấn không theo được transitions phải trả 0.

---

## 15. Kiểm thử và xác minh độc lập

### 15.1. Oracle vét cạn cho chuỗi ngắn

Với n nhỏ, xây bảng tần suất hoàn toàn độc lập:

```text
NAIVE_FREQUENCIES(s):
    freq = empty map

    for l = 0..n-1:
        for r = l+1..n:
            p = s[l..r)
            freq[p] = freq.getOrDefault(p,0) + 1

    return freq
```

Từ bảng này có thể tính:

```text
distinct = freq.size()
repeatedDistinct = count p with freq[p] >= 2
totalOccurrences = sum(freq.values())
occ(pattern) = freq.getOrDefault(pattern,0)
```

Riêng pattern rỗng cần xử lý theo quy ước n+1 vì oracle chỉ liệt kê **đoạn không rỗng**.

Phương pháp vét cạn chậm, nhưng **độc lập về mặt thuật toán** nên là oracle tốt cho những input ngắn.

### 15.2. Bộ test bắt buộc

| Văn bản | Distinct không rỗng | Tổng occurrences | Truy vấn / kỳ vọng |
| --- | ---: | ---: | --- |
| `""` | 0 | 0 | `occ("")=1` |
| `"a"` | 1 | 1 | `occ("a")=1` |
| `"aaaa"` | 4 | 10 | `occ("aa")=3` |
| `"ababa"` | 9 | 15 | `occ("aba")=2` |
| `"banana"` | 15 | 21 | `occ("ana")=2` |
| `"abc"` | 6 | 6 | `occ("ab")=1` |
| `"abcabc"` | 15 | 21 | `occ("abc")=2` |
| `"abababba"` | 23 | 36 | `occ("bab")=2` |
| `"abc"` | 6 | 6 | `occ("xyz")=0` |
| `"abc"` | 6 | 6 | `occ("")=4` |

### 15.3. Tính đúng của danh sách đếm

Với mọi text s:

1. `0≤distinct≤n(n+1)/2`.
2. `0≤repeatedDistinct≤distinct`.
3. `totalOccurrences==n(n+1)/2`.
4. Query p không rỗng có `occ(p)≥1` **nếu và chỉ nếu** p là substring của s.
5. `occ(p)≤n-|p|+1` khi |p|>0 và |p|≤n.
6. Với mẫu dài hơn text, count=0.
7. Với mẫu rỗng, count=n+1 theo quy ước.
8. Các state khác root đều có `len[link[v]]<len[v]`.
9. Clone có giá trị occ ban đầu 0, prefix-cur có giá trị occ ban đầu 1.
10. Sau propagate, mọi occ hợp lệ không âm.
11. `numberOfStates≤2n` cho n≥1 trong SAM chuẩn.
12. Nếu text chỉ gồm một ký tự 'a' lặp n lần, distinct=n và `occ("a"^k)=n-k+1` với 1≤k≤n.

### 15.4. Kiểm thử ngẫu nhiên trên alphabet nhỏ

Dùng alphabet `{a,b,c}` và n từ 0 tới 8:

1. Sinh nhiều chuỗi ngẫu nhiên.
2. Xây SAM.
3. Dùng oracle vét cạn `Map<String,Integer>`.
4. So distinct, repeatedDistinct và totalOccurrences.
5. Với mọi key trong map, kiểm tra `occurrences(key)==freq[key]`.
6. Sinh thêm mẫu không có trong text để kiểm tra trả 0.
7. Kiểm tra query rỗng trả n+1.

Lỗi clone hoặc propagation có thể **không lộ** ở chuỗi không lặp, nhưng thường xuất hiện khi có cấu trúc hậu tố lặp như `"banana"`. Vì vậy luôn giữ cả test ngẫu nhiên lẫn test có chủ đích.

### 15.5. Tại sao phải thử nhiều loại chuỗi?

- **Mọi ký tự khác nhau:** gần như mọi đoạn mới đều phân biệt.
- **Mọi ký tự giống nhau:** nhiều lần xuất hiện, ít distinct.
- **Chuỗi chu kỳ** như `"ababa"`: các khớp chồng lấn.
- **Chuỗi có clone** như `"banana"`: kiểm tra việc tách lớp endpos.
- **Chuỗi rỗng:** xử lý trường hợp không có state nào ngoài root.
- **Mẫu không tồn tại:** kiểm tra chuyển cạnh thiếu.
- **Ký tự ngoài alphabet:** xác minh hợp đồng API từ chối rõ ràng.

---

## 16. Chọn cách giải theo yêu cầu

### 16.1. Chỉ cần đếm distinct cho một chuỗi

- Với n nhỏ, liệt kê các đoạn rồi dùng set là dễ triển khai nhưng có thể tốn nhiều RAM.
- Với n lớn và yêu cầu đúng tuyệt đối, SAM hoặc suffix array + LCP thích hợp.
- Nếu đề chỉ chấp nhận hash với xác suất collision nhỏ, prefix/rolling hash có thể dùng theo hợp đồng chấp nhận rủi ro, nhưng phải nói rõ giới hạn.

### 16.2. Nhiều câu hỏi “mẫu p xuất hiện bao nhiêu lần?”

Xây SAM **một lần** trên text s. Sau đó mỗi query p chỉ đi qua `next` và trả `occ[state]`:

\[
Preprocess=O(n),\quad Query=O(|p|)
\]

với alphabet cố định.

Nếu chỉ có một query, dùng **KMP** để đếm khớp (kể cả chồng lấn) trong O(n+|p|) có thể đơn giản hơn về lập trình.

### 16.3. Cần liệt kê tất cả vị trí của mẫu

SAM trong bài chỉ lưu **số lượng**. Muốn truy xuất tất cả chỉ số bắt đầu, có thể dùng:

- KMP để quét toàn văn bản và trả các match.
- Suffix array để tìm đoạn suffix bắt đầu bằng mẫu, rồi xuất các vị trí.
- Mở rộng SAM với tập vị trí kết thúc có cơ chế lưu/truy xuất riêng, lưu ý bộ nhớ và chi phí.

Không được suy ra vị trí từ một số `occ` duy nhất.

### 16.4. Cần chuỗi con lặp dài nhất

Có thể dựa vào SAM: trạng thái v có `occ[v]≥2` thể hiện những substring lặp. Độ dài lớn nhất của một substring lặp là:

\[
\max_{v:\,occ[v]\ge2}len[v].
\]

Nếu cần chính nội dung chuỗi ấy, phải lưu/khôi phục một vị trí kết thúc đại diện và cắt ra đoạn độ dài thích hợp. Đây là một ứng dụng khác của cấu trúc đã xây.

### 16.5. Cần đếm distinct của nhiều văn bản khác nhau

Bản SAM hiện tại là cho **một text cố định**. Khi đổi text, cần xây lại; không được tái sử dụng occurrences hoặc suffix links của text cũ.

Có kỹ thuật **generalized suffix automaton** cho nhiều văn bản, nhưng cần các quy tắc phân tách, quyền sở hữu và occurrence riêng. Không đồng nhất với việc ghép text bằng một ký tự delimiter tùy tiện rồi dùng nguyên công thức một văn bản.

---

## 17. Bài tập tự kiểm tra

### Bài 1 — Định nghĩa
Phân biệt substring và subsequence. `"ac"` có phải substring của `"abc"` không?

### Bài 2 — Đoạn theo vị trí
Một chuỗi độ dài n có bao nhiêu đoạn không rỗng tính theo vị trí? Với n=6, con số là bao nhiêu?

### Bài 3 — Distinct cơ bản
Liệt kê chuỗi con không rỗng phân biệt của `"aaaa"`.

### Bài 4 — Occurrence
`"aa"` xuất hiện bao nhiêu lần trong `"aaaa"` nếu tính cả chồng lấn?

### Bài 5 — Ababa
Đếm distinct của `"ababa"` và tần suất của `"aba"`, `"ba"`, `"a"`.

### Bài 6 — Banana
Đếm distinct của `"banana"` và tần suất của `"ana"`, `"na"`, `"a"`.

### Bài 7 — Empty pattern
Theo quy ước bài này, `occ("")` của một text độ dài n bằng gì? Với text rỗng thì sao?

### Bài 8 — Len và link
Một state v có `len[v]=8` và `len[link[v]]=3`. Nó biểu diễn bao nhiêu chuỗi con phân biệt?

### Bài 9 — Công thức distinct
Viết công thức tính `DistinctNonEmpty` từ các trạng thái SAM.

### Bài 10 — Endpos
`endpos("aba")` trong `"ababa"` gồm các vị trí kết thúc nào?

### Bài 11 — Một state có nhiều chuỗi
Vì sao `"ba"` và `"aba"` trong `"ababa"` có thể thuộc cùng endpos class?

### Bài 12 — Clone
Clone có được gán `occ=1` ngay khi tạo không? Vì sao?

### Bài 13 — Propagation
Vì sao cần cộng `occ[v]` vào `occ[link[v]]` theo chiều `len` giảm dần?

### Bài 14 — Query
Làm sao dùng SAM để trả số lần xuất hiện của một pattern p trong O(|p|)?

### Bài 15 — Tổng tần suất
Chứng minh `sum Delta(v)*occ[v]=n(n+1)/2`.

### Bài 16 — Repeated distinct
Viết công thức số chuỗi con phân biệt xuất hiện ít nhất hai lần.

### Bài 17 — Java type
Vì sao kết quả distinct nên dùng `long` khi n lớn?

### Bài 18 — Giới hạn alphabet
Bản Java có thể nhận `"Banana"` hoặc chuỗi có dấu tiếng Việt không? Nếu cần Unicode, phải điều chỉnh gì?

### Bài 19 — State count
Số trạng thái SAM có bằng số chuỗi con distinct không? Với `"banana"`, mã in số state bao nhiêu?

### Bài 20 — Suffix array
Viết công thức distinct bằng tổng độ dài suffix trừ tổng LCP kề nhau trong thứ tự SA.

### Bài 21 — Banana SA
Với `"banana"`, tổng `n(n+1)/2` và tổng LCP là bao nhiêu? Tính distinct.

### Bài 22 — Rolling hash
Vì sao hai hash trùng nhau chưa đủ chứng minh hai substring bằng nhau?

### Bài 23 — So sánh thuật toán
Nếu chỉ có một pattern cần đếm trong một text và không cần số distinct, khi nào KMP thuận tiện hơn SAM?

### Bài 24 — Nhiều query
Nếu có Q mẫu dài lần lượt `m_1,\ldots,m_Q` trên cùng text dài n, thời gian dùng SAM là bao nhiêu?

### Bài 25 — Oracle
Mô tả phép vét cạn để kiểm thử cả distinct lẫn occurrences của từng mẫu trên text ngắn.

### Bài 26 — Chuỗi mọi ký tự giống nhau
Với text gồm n ký tự 'a', distinct không rỗng và `occ("a"^k)` bằng bao nhiêu?

### Bài 27 — Vị trí khớp
Vì sao chỉ có `occ[v]` không đủ để liệt kê tất cả vị trí bắt đầu của một pattern?

### Bài 28 — Test bất biến
Nêu ba kiểm tra độc lập quan trọng để phát hiện sai sót khi cài SAM.

### Đáp án gợi ý

1. Substring liên tiếp; subsequence giữ thứ tự nhưng có thể bỏ ký tự. `"ac"` không phải substring của `"abc"`.
2. `n(n+1)/2`; với n=6 là 21.
3. `a,aa,aaa,aaaa`; có 4 loại.
4. Ba lần: bắt đầu ở 0,1,2.
5. Distinct=9; `occ("aba")=2`, `occ("ba")=2`, `occ("a")=3`.
6. Distinct=15; `occ("ana")=2`, `occ("na")=2`, `occ("a")=3`.
7. `n+1`; text rỗng trả 1.
8. `8-3=5` chuỗi, với độ dài 4..8.
9. `sum_{v>root}(len[v]-len[link[v]])`.
10. `{2,4}` theo chỉ số 0-based.
11. Hai chuỗi có cùng tập vị trí kết thúc `{2,4}`, nên thuộc cùng lớp endpos.
12. Không. Clone chỉ tách lớp trạng thái, không thêm vị trí prefix kết thúc mới; phải đặt 0.
13. Suffix link luôn dẫn tới trạng thái có len nhỏ hơn; truyền từ dài xuống ngắn giúp parent nhận đủ đóng góp trước khi gửi tiếp.
14. Từ root theo từng transition của p; thiếu cạnh trả 0, đọc hết trả `occ[v]`.
15. Mỗi state biểu diễn Delta chuỗi phân biệt, mỗi chuỗi xuất hiện occ lần; tổng các lần xuất hiện chính là số cặp biên l<r, bằng n(n+1)/2.
16. `sum_{v>root,occ[v]>=2}(len[v]-len[link[v]])`.
17. Với n=100000, số đoạn theo vị trí có thể tới 5,000,050,000, vượt int.
18. Không; mẫu chỉ nhận a..z. Có thể dùng mapping alphabet động hoặc code point và map transitions nếu cần.
19. Không. Với `"banana"`, chương trình có 10 state gồm root, còn distinct là 15.
20. `n(n+1)/2-sum_{i=1}^{n-1}LCP[i]`.
21. Tổng đoạn=21, tổng LCP=6, distinct=15.
22. Hash có collision, có thể hai chuỗi khác nhau cùng giá trị hash; cần xác minh thật hoặc cấu trúc exact.
23. KMP có O(n+m) xấu nhất và cài đơn giản hơn SAM cho một query.
24. Xây O(n) rồi truy vấn O(`sum m_i`); tổng `O(n+sum m_i)` với alphabet cố định.
25. Duyệt mọi `(l,r)` với `l<r`, lấy substring làm key map và tăng đếm; distinct=map.size, occurrences lấy từ map.
26. Distinct=n; `occ("a"^k)=n-k+1` nếu 1≤k≤n.
27. Occ chỉ là cardinality của endpos class, không lưu riêng từng vị trí; muốn xuất vị trí cần thêm cấu trúc hoặc quét.
28. So kết quả distinct với vét cạn; so mọi tần suất với map; kiểm tra `sum Delta·occ=n(n+1)/2`, thêm test có clone và chuỗi rỗng.

---

## Ghi nhớ

Một chuỗi dài n có **n(n+1)/2 lần xuất hiện substring không rỗng theo vị trí**, nhưng số **giá trị substring phân biệt** có thể nhỏ hơn rất nhiều. **Suffix automaton** gom các substring có cùng tập vị trí kết thúc (*endpos class*) vào state v.

Hai công thức chính:

\[
\boxed{
DistinctNonEmpty(s)=
\sum_{v\ne root}(len[v]-len[link[v]]).
}
\]

\[
\boxed{
occurrences(p)=occ[stateReachedBy(p)].
}
\]

Để có occ đúng, tạo state thật khi thêm mỗi ký tự với **occ=1**, tạo **clone với occ=0**, rồi **cộng dồn từ trạng thái dài sang ngắn theo suffix links**. Có thể kiểm tra bằng bất biến:

\[
\sum_{v\ne root}(len[v]-len[link[v]])occ[v]
=\frac{n(n+1)}2.
\]

Với bảng chữ cái cố định a..z, SAM dùng O(n) thời gian/bộ nhớ xây dựng, đếm distinct O(n) và trả mỗi truy vấn tần suất trong O(|p|), kể cả các khớp **chồng lấn**. Nếu cần số distinct mà thích cấu trúc hậu tố sắp xếp, **suffix array + LCP** cho công thức thay thế. Đừng nhầm distinct với tổng occurrences, và phải xử lý rõ **mẫu rỗng, độ rộng số nguyên và giới hạn alphabet**.

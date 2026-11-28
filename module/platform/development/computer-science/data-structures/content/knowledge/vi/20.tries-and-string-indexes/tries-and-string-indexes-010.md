# Cây hậu tố và biểu diễn các hậu tố bằng đoạn của chuỗi gốc

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Cây hậu tố và biểu diễn các hậu tố bằng đoạn của chuỗi gốc

Một ứng dụng cần tìm mọi lần xuất hiện của `"ana"` trong `"banana"`. Nếu mỗi lần truy vấn đều quét toàn bộ văn bản, thời gian sẽ phụ thuộc chiều dài văn bản. Nếu ứng dụng có hàng nghìn truy vấn trên **cùng một văn bản**, ta có thể xây một **chỉ mục chuỗi** để tái sử dụng thông tin giữa các lần tìm.

**Cây hậu tố** (*suffix tree*) là một trie được **nén đường đi**, chứa tất cả các hậu tố của một chuỗi. Điều đặc biệt là ta không cần lưu bản sao của từng hậu tố hay sao chép nội dung vào mỗi nhãn cạnh. Các cạnh có thể giữ **cặp chỉ số đầu–cuối trỏ vào chính chuỗi gốc**. Nhờ vậy, dù tổng độ dài của mọi hậu tố là bậc hai, một cây hậu tố nén chuẩn có **số nút và số cạnh tuyến tính** theo chiều dài chuỗi.

Bài học thuộc chương **Trie và chỉ mục chuỗi** của mô-đun `COMPUTER_SCIENCE_DATA_STRUCTURES`. Nó kết nối trie, cây, bảng băm và thao tác trên mảng/đoạn chỉ số để phân tích **bất biến**, **chi phí xây dựng**, **bộ nhớ** và **chi phí truy vấn**. Trọng tâm là hiểu chính xác *cái gì được chia sẻ*, *cái gì được lưu dưới dạng đoạn của chuỗi gốc*, và *độ phức tạp nào áp dụng cho thuật toán xây minh họa so với các thuật toán xây tối ưu*.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **hậu tố** (*suffix*), **tiền tố** (*prefix*) và **chuỗi con liên tiếp** (*substring*).
2. Liệt kê hậu tố của một chuỗi và giải thích lý do thêm một **ký hiệu kết thúc duy nhất**.
3. So sánh **suffix trie không nén** và **suffix tree nén cạnh**.
4. Diễn giải nhãn cạnh dưới dạng khoảng chỉ số **nửa mở `[start,end)`** trong chuỗi đã gắn ký hiệu kết thúc.
5. Phát biểu các bất biến của cây hậu tố: các cạnh đầu khác ký hiệu, nhãn không rỗng, lá ứng với hậu tố và các nút trong phân nhánh.
6. Thực hiện thao tác **tách cạnh** khi chèn một hậu tố có đoạn chung với hậu tố đã có.
7. Dùng cây hậu tố để tìm chuỗi con, **kể cả khi mẫu kết thúc giữa một nhãn cạnh**.
8. Liệt kê vị trí xuất hiện, đếm số lần xuất hiện và phân biệt thứ tự chỉ số với thứ tự từ điển.
9. Cài đặt một cây hậu tố minh họa bằng Python mà **các cạnh chỉ lưu chỉ số và tham chiếu nút**, không lưu chuỗi hậu tố riêng.
10. Phân tích vì sao cây có O(n) nút/cạnh nhưng **thuật toán chèn tuần tự mọi hậu tố vẫn có thể O(n²)**, và khi nào dùng thuật toán tuyến tính như Ukkonen.
11. Nhận biết ảnh hưởng của Unicode, chuẩn hóa và quy tắc chỉ số khi triển khai tìm kiếm văn bản.
12. So sánh cây hậu tố với suffix array, suffix automaton và phép tìm kiếm trực tiếp theo nhu cầu ứng dụng.

## 2. Ba khái niệm nền: prefix, suffix và substring

Cho một chuỗi `s` có độ dài `n` ký hiệu, đánh số vị trí từ `0` tới `n-1`.

- **Tiền tố** (*prefix*): `s[0:j]` với `0≤j≤n`.
- **Hậu tố** (*suffix*): `s[i:n]` với `0≤i≤n`.
- **Chuỗi con liên tiếp** (*substring*): `s[i:j]` với `0≤i≤j≤n`.

Tất cả dùng ký hiệu Python với khoảng **nửa mở**: lấy từ `i` tới trước `j`. Khi `i=j`, kết quả là chuỗi rỗng.

### 2.1. Ví dụ `banana`

```text
s = "banana"
index: 0 1 2 3 4 5
char:  b a n a n a
```

Các hậu tố của `s`:

| Vị trí bắt đầu `i` | Hậu tố `s[i:]` |
| ---: | --- |
| 0 | `banana` |
| 1 | `anana` |
| 2 | `nana` |
| 3 | `ana` |
| 4 | `na` |
| 5 | `a` |
| 6 | `""` (hậu tố rỗng) |

Mỗi chuỗi con liên tiếp đều là **tiền tố của một hậu tố**. Chẳng hạn `"ana"` là tiền tố của hai hậu tố `s[1:] = "anana"` và `s[3:] = "ana"`.

Đây là tính chất cốt lõi:

\[
p\text{ xuất hiện tại vị trí }i\text{ trong }s
\iff p\text{ là tiền tố của }s[i:].
\]

Vì vậy, nếu tổ chức **mọi hậu tố thành một trie**, câu hỏi “`p` xuất hiện trong `s` không?” có thể được chuyển thành “có đường nào trong trie hậu tố bắt đầu bằng `p` không?”.

### 2.2. Phân biệt substring với subsequence

`"bnn"` là một *subsequence* của `banana` theo nghĩa có thể chọn các ký tự không liền nhau, nhưng **không phải substring liên tiếp** của `banana`.

Cây hậu tố trong bài hỗ trợ **chuỗi con liên tiếp**, không trực tiếp giải bài toán subsequence tùy ý.

### 2.3. Hậu tố có thể trùng không?

Các hậu tố của một **chuỗi đơn** có vị trí bắt đầu khác nhau và độ dài khác nhau, nên với việc giữ độ dài, chúng là những chuỗi khác nhau. Nhưng nếu một hậu tố là tiền tố của một hậu tố dài hơn, chỉ dùng nút lá không đủ bảo đảm mỗi hậu tố kết thúc ở một lá. Ta sẽ thêm ký hiệu kết thúc để xử lý vấn đề này một cách thống nhất.

## 3. Ký hiệu kết thúc duy nhất `$` và chuỗi mở rộng

Đặt:

\[
T=s+\$,
\]

trong đó `$` là **ký hiệu mới không xuất hiện ở bất kỳ vị trí nào của `s`**. Trong mã Python minh họa, ta dùng chính ký tự `"$"` và **từ chối văn bản gốc có ký tự ấy**.

Nếu `n=len(s)`, thì:

\[
N=len(T)=n+1.
\]

Ta xây cây cho **`N=n+1` hậu tố**:

\[
T[0:N],\ T[1:N],\ \ldots,\ T[n:N].
\]

Hậu tố cuối cùng chỉ là `"$"`. Nó tương ứng với **hậu tố rỗng của văn bản gốc**, nhưng khi lưu trong cây vẫn có một ký hiệu kết thúc.

### 3.1. Bảng hậu tố của `banana$`

```text
T = "banana$"
index: 0 1 2 3 4 5 6
char:  b a n a n a $
```

| `i` | Hậu tố mở rộng `T[i:]` |
| ---: | --- |
| 0 | `banana$` |
| 1 | `anana$` |
| 2 | `nana$` |
| 3 | `ana$` |
| 4 | `na$` |
| 5 | `a$` |
| 6 | `$` |

Chính ký hiệu `$` làm cho **không hậu tố mở rộng nào là tiền tố của hậu tố mở rộng khác**. Nếu một hậu tố đã tới `$` thì nó phải kết thúc; không có ký tự nào phía sau `$` trong `T`.

### 3.2. Lợi ích đối với biểu diễn cây

Khi mọi hậu tố là phân biệt và không hậu tố nào là tiền tố của hậu tố khác:

- Mỗi hậu tố mở rộng có thể kết thúc tại **một lá riêng**.
- Không cần đánh dấu terminal ở các nút trong để biểu diễn hậu tố kết thúc giữa đường.
- Ta có chính xác **`n+1` lá** nếu xây đầy đủ mọi hậu tố `T[i:]`, `0≤i≤n`.

Điều này giúp cả thuật toán xây, chứng minh số nút và truy vấn vị trí xuất hiện trở nên rõ ràng.

### 3.3. Ký hiệu kết thúc không phải dữ liệu cần tìm

`$` là **ký hiệu kỹ thuật**. Khi tìm chuỗi con của văn bản gốc, ta thường **không cho phép mẫu chứa `$`**. Các kết quả xuất ra là vị trí trong `s`, không phải một lần xuất hiện tưởng tượng của ký hiệu kết thúc.

Riêng **mẫu rỗng**, bài học chọn quy ước nó xuất hiện tại **`n+1` ranh giới** giữa các ký hiệu, kể cả trước ký hiệu đầu và sau ký hiệu cuối, nên vị trí là `0,1,\ldots,n`.

## 4. Từ suffix trie không nén đến suffix tree nén cạnh

Một *suffix trie* không nén chèn tất cả hậu tố vào một trie mà **mỗi cạnh mang một ký hiệu**. Nó chia sẻ các tiền tố chung của các hậu tố, nhưng có thể vẫn giữ rất nhiều nút **không terminal chỉ có một con**.

**Suffix tree** thường hiểu là dạng **trie hậu tố đã nén**: mỗi đường một con không cần thiết được gộp thành **một cạnh mang chuỗi nhãn**.

### 4.1. Vì sao không thể chỉ lưu bản sao từng hậu tố?

Tổng độ dài của tất cả hậu tố mở rộng bằng:

\[
N+(N-1)+\cdots+1=\frac{N(N+1)}2=\Theta(n^2).
\]

Với `n=1.000.000`, nếu tạo chuỗi `T[i:]` cho mọi `i` và giữ toàn bộ, lượng dữ liệu hậu tố lặp lại theo bậc hai, không khả thi cho bộ nhớ thông thường.

Tuy nhiên, suffix tree **không cần giữ các bản sao ấy**.

### 4.2. Chia sẻ tiền tố và nén đường

Nếu hai hậu tố có chung phần đầu `"ana"`, cây chỉ cần giữ **một đường chung** cho phần ấy rồi rẽ nhánh tại ký hiệu phân biệt.

Nếu một đoạn đường không tạo ra nhánh mới, có thể đặt **cả đoạn chuỗi trên một cạnh**.

Điểm quan trọng: khi nén, ta vẫn cần biểu diễn nhãn của cạnh, nhưng có thể biểu diễn nhãn bằng **hai chỉ số trỏ vào chuỗi `T` duy nhất**.

### 4.3. Suffix tree là một cấu trúc cụ thể, không chỉ một tập hậu tố

Một danh sách gồm các hậu tố hoặc tập các chuỗi hậu tố chưa phải suffix tree. Cấu trúc cây phải bảo đảm:

- Đường từ gốc tới mỗi lá khôi phục đúng một hậu tố mở rộng.
- Các cạnh cùng cha không có ký hiệu đầu giống nhau.
- Các đoạn đường không phân nhánh được nén.
- Nhãn cạnh tham chiếu dữ liệu gốc đúng ranh giới.

Những bất biến ấy mới cho phép tìm mẫu theo **đường trên cây**, thay vì phải so sánh lần lượt với mọi hậu tố.

## 5. Nhãn cạnh bằng đoạn chỉ số `[start,end)`

Thay vì lưu chuỗi nhãn `"ana"`, một cạnh giữ:

```text
Edge:
    start: chỉ số bắt đầu trong T
    end:   chỉ số kết thúc loại trừ trong T
    child: nút con
```

Nhãn cạnh được hiểu là:

\[
label(edge)=T[edge.start:edge.end].
\]

Ta dùng **khoảng nửa mở** `[start,end)`: bao gồm `start` và loại trừ `end`. Độ dài nhãn là:

\[
length(edge)=end-start.
\]

### 5.1. Ví dụ cùng `T=banana$`

```text
index:    0 1 2 3 4 5 6
T:        b a n a n a $
```

| Khoảng | Nhãn nhìn thấy | Độ dài |
| --- | --- | ---: |
| `[0,7)` | `banana$` | 7 |
| `[1,4)` | `ana` | 3 |
| `[2,4)` | `na` | 2 |
| `[4,7)` | `na$` | 3 |
| `[6,7)` | `$` | 1 |

Một cạnh mang `(2,4)` có nhãn `"na"` nhưng **không chứa một bản sao chuỗi `"na"`**. Khi so khớp, thuật toán đọc `T[2]` rồi `T[3]` trực tiếp.

### 5.2. Những khoảng khác nhau có thể mang nhãn giống nhau

`T[2:4]` và `T[4:6]` cùng là `"na"`. Hai cạnh ở các vị trí khác nhau của cây có thể tham chiếu hai khoảng khác nhau hoặc cùng một khoảng, miễn **nội dung nhãn đúng**.

**Không yêu cầu** một nhãn bằng chuỗi con ở “đúng vị trí xuất hiện” của mọi hậu tố sử dụng cạnh ấy. Một cạnh chia sẻ là đại diện cho nội dung ký hiệu, không phải mỗi lần xuất hiện.

### 5.3. Tại sao giữ chỉ số tiết kiệm bộ nhớ?

Nếu `T` được lưu **một lần** và không bị thay đổi, mỗi cạnh cần:

- Một chỉ số `start`.
- Một chỉ số `end`.
- Một tham chiếu tới nút con.

Trong mô hình word-RAM, các giá trị chỉ số có độ rộng hữu hạn và được coi là O(1) từ máy mỗi cạnh. Tổng byte nhãn không còn tỷ lệ với tổng độ dài những đoạn nhãn được nhìn thấy; nó tỷ lệ với **số cạnh**.

Trong Python thực tế, `int`, tuple và đối tượng cạnh vẫn có overhead. “O(1) từ máy/cạnh” là mô hình phân tích, không phải khẳng định một cạnh thực tế chỉ chiếm đúng 16 hay 24 byte.

### 5.4. Điều kiện sở hữu chuỗi gốc

Mọi cạnh phụ thuộc vào `T`. Nếu `T` bị đổi nội dung hoặc giải phóng trong khi cây còn dùng các chỉ số, **toàn bộ nhãn có thể sai**.

Một cài đặt đúng phải giữ `T` bất biến và sống ít nhất bằng vòng đời của cây. Với Python `str` bất biến, đối tượng cây có thể giữ tham chiếu `self.text=T`. Nếu hệ thống sử dụng buffer có thể sửa được, cần cơ chế kiểm soát vòng đời hoặc snapshot rõ ràng.

## 6. Sơ đồ cây hậu tố cho `banana$`

Một suffix tree nén của `T="banana$"` có thể mô tả:

```text
                             root
                  ____________|________________
                 /           /       \          \
           "banana$"       "a"       "na"        "$"
               |            |         |           |
             leaf 0         A         C         leaf 6
                          /   \      /  \
                        "$"   "na"  "$"  "na$"
                         |      |    |     |
                      leaf 5    B  leaf 4 leaf 2
                               / \
                             "$" "na$"
                              |    |
                           leaf 3 leaf 1
```

Mỗi lá ghi **vị trí bắt đầu hậu tố** trong `T`:

- `leaf 0`: `banana$`.
- `leaf 1`: `anana$`.
- `leaf 2`: `nana$`.
- `leaf 3`: `ana$`.
- `leaf 4`: `na$`.
- `leaf 5`: `a$`.
- `leaf 6`: `$`.

Ví dụ, đường tới `leaf 1` là:

```text
root --"a"--> A --"na"--> B --"na$"--> leaf 1
```

Ghép nhãn được `"a"+"na"+"na$" = "anana$"`, chính là `T[1:]`.

### 6.1. Các đoạn chỉ số cụ thể

Có thể chọn những đoạn nhãn cạnh như sau:

| Cạnh | Khoảng trong `T` | Nhãn |
| --- | --- | --- |
| root → leaf 0 | `[0,7)` | `banana$` |
| root → A | `[1,2)` | `a` |
| A → leaf 5 | `[6,7)` | `$` |
| A → B | `[2,4)` | `na` |
| B → leaf 3 | `[6,7)` | `$` |
| B → leaf 1 | `[4,7)` | `na$` |
| root → C | `[2,4)` | `na` |
| C → leaf 4 | `[6,7)` | `$` |
| C → leaf 2 | `[4,7)` | `na$` |
| root → leaf 6 | `[6,7)` | `$` |

Ta không cần tạo bất kỳ chuỗi nhãn mới nào để lưu các cạnh; khi cần hiển thị, có thể tính tạm `T[start:end]`.

### 6.2. Vì sao một mẫu có thể kết thúc giữa cạnh?

Xét mẫu `"ban"`. Ở gốc có cạnh mang `"banana$"`, và ba ký hiệu đầu của cạnh là `ban`. Mẫu kết thúc **giữa cạnh** nhưng rõ ràng xuất hiện tại vị trí 0.

Tương tự, `"an"` đi qua cạnh `"a"` rồi khớp ký hiệu `n` ở đầu cạnh `"na"`. Mẫu kết thúc trước khi cạnh `"na"` hết, nhưng vẫn khớp ở các vị trí 1 và 3.

Vì vậy, thuật toán tìm chuỗi con **không được yêu cầu mẫu phải kết thúc đúng ở một nút**.

## 7. Các bất biến của suffix tree chuẩn

Trong phần này, ta xét cây hậu tố **đã xây đầy đủ** cho `T=s+$`, với `$` xuất hiện đúng một lần ở cuối.

1. Gốc luôn tồn tại.
2. Mọi cạnh có khoảng `[start,end)` hợp lệ, thỏa `0≤start<end≤N`.
3. Nhãn cạnh là `T[start:end]` và không rỗng.
4. Các cạnh đi ra khỏi cùng một nút có **ký hiệu đầu khác nhau**: mỗi ký hiệu chọn tối đa một cạnh.
5. Mỗi lá có đúng một `suffix_start∈[0,n]`, và các lá biểu diễn **toàn bộ `n+1` hậu tố**, không trùng vị trí.
6. Đường nhãn từ gốc tới lá `i` khôi phục chính xác `T[i:N]`.
7. Mọi nút trong **khác gốc** có ít nhất **hai con**; các đường không phân nhánh được nén.
8. Mỗi nút là một đối tượng cây riêng, không dùng chung nút con giữa nhiều cha và không có chu trình.
9. Nếu lưu `leaf_count(v)`, nó bằng số lá trong cây con của `v`.

Công thức bộ đếm lá:

\[
leafCount(v)=
\begin{cases}
1, & v \text{ là lá};\\
\sum_{u\in children(v)}leafCount(u), & v\text{ là nút trong}.
\end{cases}
\]

### 7.1. Lá không mang ký hiệu `$` trong khóa tìm kiếm

`$` nằm trong các đường biểu diễn hậu tố, nhưng không thuộc văn bản gốc. Việc tìm một mẫu chứa `$` không phải truy vấn chuỗi con hợp lệ của `s` trong hợp đồng bài này.

### 7.2. Nút trong không cần terminal

Vì mọi hậu tố có ký hiệu kết thúc duy nhất, không có hậu tố mở rộng nào là tiền tố của hậu tố khác. Do đó mọi hậu tố có thể kết thúc tại một **lá**.

Cây không cần cờ `terminal=True` ở những nút trong như một trie Set tổng quát. Thay vào đó, lá ghi **vị trí bắt đầu hậu tố**.

### 7.3. Tại sao nút trong có ít nhất hai con?

Nếu nút trong không phải gốc có đúng một con, nhãn cạnh từ cha tới nó có thể được nối với nhãn cạnh tới con rồi loại nút ấy. Cây nén chuẩn không giữ nút thừa như vậy.

Nút trong có ít nhất hai con ứng với một **điểm phân kỳ** giữa các hậu tố.

## 8. Xây cây: chèn lần lượt tất cả hậu tố

Để minh họa rõ các đoạn chỉ số, ta dùng thuật toán **đơn giản**:

```text
T = s + "$"
root = node rỗng

for i = 0, 1, ..., n:
    chèn hậu tố T[i:N] vào trie nén
```

Điều quan trọng là **không thực sự tạo `T[i:N]` thành chuỗi mới**. Ta giữ `i` và một con trỏ `pos` vào `T`.

### 8.1. Nếu không có cạnh bắt đầu bằng ký hiệu cần đọc

Tại nút hiện tại và vị trí `pos`:

- Đọc `T[pos]`.
- Nếu không có cạnh đi ra với ký hiệu đầu ấy, tạo **một lá mới** ghi `suffix_start=i`.
- Tạo một cạnh nhãn `[pos,N)` đi tới lá.

Một cạnh chứa toàn bộ phần hậu tố còn lại; không cần tạo từng nút cho mỗi ký hiệu.

### 8.2. Nếu có cạnh, so khớp ngay trên chuỗi gốc

Giả sử cạnh đang có khoảng `[l,r)`. Đặt `j` là số ký hiệu chung liên tiếp giữa:

```text
T[pos:N]  và  T[l:r]
```

Ta so sánh trực tiếp:

```python
T[pos + j] == T[l + j]
```

với các điều kiện chỉ số hợp lệ, **không cần cắt hai chuỗi tạm**.

### 8.3. Khớp hết nhãn cạnh

Nếu `j=r-l`:

- Đi xuống nút con của cạnh.
- Tăng `pos` thêm `j`.
- Tiếp tục xử lý hậu tố.

### 8.4. Phân kỳ giữa nhãn cạnh

Nếu `0<j<r-l`, tạo nút giữa `middle`, chia cạnh cũ:

```text
trước:
parent --T[l:r]--> old_child

sau:
parent --T[l:l+j]--> middle
middle --T[l+j:r]--> old_child
middle --T[pos+j:N]--> new_leaf
```

Ở đây `new_leaf.suffix_start=i`. Do đã chọn cạnh theo ký hiệu đầu, `j≥1`. Do các hậu tố mở rộng kết thúc bằng `$` duy nhất và không hậu tố nào là tiền tố của hậu tố khác, hậu tố mới chưa thể hết trước khi cạnh cũ hết mà không xuất hiện một ký hiệu **khác** để rẽ nhánh.

### 8.5. Tại sao không cần lưu chuỗi sau split?

Khi tách, ta chỉ thay **các chỉ số**:

- Cạnh chung `[l,l+j)`.
- Đuôi cũ `[l+j,r)`.
- Đuôi mới `[pos+j,N)`.

Không phải tạo các chuỗi `T[l:l+j]`, `T[l+j:r]` hay `T[pos+j:N]` để lưu cố định. Chúng chỉ là **nhãn logic** của các đoạn `T`.

## 9. Mô phỏng các lần chèn với `banana$`

Cho `T="banana$"`, `N=7`.

### 9.1. Chèn hậu tố `i=0`: `banana$`

Cây rỗng chưa có cạnh `b`:

```text
root --"banana$"--> leaf 0
```

Cạnh có thể giữ `[0,7)`.

### 9.2. Chèn `i=1`: `anana$`

Gốc chưa có cạnh `a`:

```text
root --"banana$"--> leaf 0
     \
      --"anana$"--> leaf 1
```

### 9.3. Chèn `i=2`: `nana$`

Gốc chưa có cạnh `n` nên thêm cạnh `[2,7)` tới leaf 2.

### 9.4. Chèn `i=3`: `ana$`

Gốc đã có cạnh `"anana$"` cho ký hiệu đầu `a`. Hai chuỗi:

```text
anana$
ana$
^^^
LCP = "ana" (3 ký hiệu)
```

Tách cạnh:

```text
root --"ana"--> B
                  / \
                "$" "na$"
                 |    |
              leaf 3 leaf 1
```

Các nhãn mới chỉ là các đoạn của `T`.

### 9.5. Chèn `i=4`: `na$`

Gốc có cạnh `"nana$"`. LCP của `nana$` và `na$` là `"na"`:

```text
root --"na"--> C
                / \
              "$" "na$"
               |    |
            leaf 4 leaf 2
```

### 9.6. Chèn `i=5`: `a$`

Gốc đang có cạnh `"ana"`. LCP với `a$` chỉ là `"a"`, tạo nút `A`:

```text
root --"a"--> A
               / \
             "$" "na"
              |    |
           leaf 5  B
                  / \
                "$" "na$"
                 |    |
              leaf 3 leaf 1
```

### 9.7. Chèn `i=6`: `$`

Gốc chưa có cạnh `$`. Thêm cạnh `[6,7)` tới leaf 6; ta thu được cây đầy đủ ở mục 6.

**Nhận xét:** Sau tất cả các lần chèn, không có hậu tố nào bị sao chép thành chuỗi mới. Mỗi lá giữ chỉ số `i`; mỗi cạnh giữ các chỉ số `start,end` trỏ vào `T` duy nhất.

## 10. Cài đặt Python: nút và cạnh lưu chỉ số, không lưu nhãn chuỗi

Ta viết một cài đặt **giáo dục**, dùng chèn từng hậu tố, chưa dùng suffix link hay Ukkonen. Nó chính xác về cấu trúc và minh họa khả năng dùng **đoạn chỉ số** nhưng **không phải thuật toán xây tuyến tính**.

### 10.1. Nút và cạnh

```python
class Edge:
    __slots__ = ("start", "end", "child")

    def __init__(self, start, end, child):
        self.start = start
        self.end = end
        self.child = child


class Node:
    __slots__ = ("edges", "suffix_start", "leaf_count")

    def __init__(self, suffix_start=None):
        # Ký hiệu đầu của nhãn cạnh -> Edge.
        self.edges = {}
        # Lá giữ vị trí bắt đầu hậu tố, nút trong là None.
        self.suffix_start = suffix_start
        self.leaf_count = 0
```

- `Edge.start` và `Edge.end` trỏ vào **cùng `T`** do cây giữ.
- `Edge.child` là nút cuối cạnh.
- `Node.edges` là Hash Map theo ký hiệu đầu của nhãn.
- `Node.suffix_start` chỉ có giá trị ở **lá**.
- `Node.leaf_count` đếm lá trong cây con; nó sẽ được tính sau khi xây xong.

### 10.2. Khởi tạo cây và xây các hậu tố

```python
class SuffixTree:
    def __init__(self, text):
        if not isinstance(text, str):
            raise TypeError("text phải là str")
        if "$" in text:
            raise ValueError("ký hiệu '$' được dành làm kết thúc")

        self.original = text
        self.text = text + "$"
        self.n = len(text)
        self.root = Node()

        # Chèn cả hậu tố '$', tương ứng hậu tố rỗng
        # của văn bản gốc.
        for start in range(self.n + 1):
            self._insert_suffix(start)

        self._compute_leaf_counts()

    def _insert_suffix(self, suffix_start):
        source = self.text
        total = len(source)

        node = self.root
        pos = suffix_start

        while pos < total:
            first = source[pos]
            edge = node.edges.get(first)

            if edge is None:
                leaf = Node(suffix_start=suffix_start)
                node.edges[first] = Edge(pos, total, leaf)
                return

            # So sánh trực tiếp ký hiệu của source,
            # không tạo source[pos:] hay nhãn chuỗi.
            common = 0

            while (
                common < edge.end - edge.start
                and pos + common < total
                and source[edge.start + common]
                    == source[pos + common]
            ):
                common += 1

            if common == edge.end - edge.start:
                pos += common
                node = edge.child
                continue

            # Split giữa cạnh: common >= 1 vì first
            # đã chọn đúng cạnh. Hậu tố mới chưa thể
            # kết thúc giữa cạnh nhờ ký hiệu '$'.
            assert common > 0
            assert pos + common < total

            old_start = edge.start
            old_end = edge.end
            old_child = edge.child

            middle = Node()
            node.edges[first] = Edge(
                old_start, old_start + common, middle
            )

            old_tail_start = old_start + common
            middle.edges[source[old_tail_start]] = Edge(
                old_tail_start, old_end, old_child
            )

            new_tail_start = pos + common
            leaf = Node(suffix_start=suffix_start)
            middle.edges[source[new_tail_start]] = Edge(
                new_tail_start, total, leaf
            )
            return

        # Với mọi hậu tố của T có '$' cuối cùng
        # và không trùng nhau, không thể hết hậu tố
        # ở một nút đã có mà không tạo lá mới.
        raise AssertionError("hậu tố không tách biệt")
```

**Chú ý về mã:** phần `_insert_suffix` nằm **trong lớp `SuffixTree`** sau `__init__`. Ở mọi nhánh thêm cạnh, ta tạo **một lá** ghi vị trí bắt đầu hậu tố. Khi split, ta chỉ tạo một nút giữa và lá mới; nút con cũ được giữ nguyên.

### 10.3. Tính bộ đếm lá sau khi hoàn tất xây

Sau khi xây xong toàn bộ cây, mỗi lá tương ứng đúng một hậu tố. Ta dùng DFS hậu tự bằng Stack, không cần đệ quy:

```python
    def _compute_leaf_counts(self):
        stack = [(self.root, False)]

        while stack:
            node, expanded = stack.pop()

            if not expanded:
                stack.append((node, True))
                for edge in node.edges.values():
                    stack.append((edge.child, False))
                continue

            if node.suffix_start is not None:
                node.leaf_count = 1
            else:
                node.leaf_count = sum(
                    edge.child.leaf_count
                    for edge in node.edges.values()
                )
```

`leaf_count` là số **lá bên dưới nút**, tương đương số vị trí bắt đầu hậu tố có đường qua nút ấy. Với `T=s+$`, gốc có `n+1` lá.

Cách tính này mất O(số nút và cạnh) sau khi xây. Nếu muốn chèn thêm ký tự vào văn bản sau khi cây đã xây, các vị trí và bộ đếm phải được cập nhật theo thuật toán online phù hợp; mã này xem văn bản **bất biến sau khởi tạo**.

## 11. Tìm một mẫu, kể cả khi hết giữa cạnh

Gọi `m=len(pattern)`. Vì mọi chuỗi con của văn bản gốc là tiền tố của ít nhất một hậu tố nếu nó xuất hiện, ta chỉ cần lần theo nhãn cạnh cho đến khi:

- Mẫu **không khớp**: kết luận không xuất hiện.
- Mẫu **được đọc hết**: đã tìm được một *locus* (vị trí tương ứng trên cây), có thể là nút hoặc điểm giữa cạnh.

### 11.1. Locus ở giữa cạnh

Nếu mẫu hết giữa cạnh, ta vẫn có thể dùng **nút con ở cuối cạnh** để đại diện cho tập các hậu tố khớp. Mọi hậu tố trong cây con ấy đi qua cùng phần nhãn vừa đọc, nên đều bắt đầu bằng mẫu.

Không cần tách cạnh hay sửa cây để phục vụ truy vấn.

### 11.2. Phương thức định vị mẫu

Bổ sung vào lớp `SuffixTree`:

```python
    @staticmethod
    def _validate_pattern(pattern):
        if not isinstance(pattern, str):
            raise TypeError("pattern phải là str")
        if "$" in pattern:
            raise ValueError("pattern không được chứa '$'")

    def _locus_node(self, pattern):
        """Nút cuối cạnh chứa điểm kết thúc của pattern.

        Trả None khi pattern không phải tiền tố của
        bất kỳ hậu tố nào. Pattern rỗng -> root.
        """
        node = self.root
        pos = 0

        while pos < len(pattern):
            edge = node.edges.get(pattern[pos])
            if edge is None:
                return None

            common = 0
            edge_length = edge.end - edge.start

            while (
                common < edge_length
                and pos + common < len(pattern)
                and self.text[edge.start + common]
                    == pattern[pos + common]
            ):
                common += 1

            if pos + common == len(pattern):
                # Pattern có thể hết giữa cạnh.
                return edge.child

            if common < edge_length:
                # Mismatch trước khi pattern hết.
                return None

            pos += common
            node = edge.child

        return node
```

Thuật toán không cần tạo `self.text[edge.start:edge.end]` thành chuỗi mới. Nó đọc các ký hiệu của `T` theo chỉ số.

### 11.3. Vì sao trả `edge.child` khi mẫu kết thúc giữa cạnh?

Giả sử `pattern="an"` trong `banana`. Sau nhánh `"a"`, mẫu dùng ký hiệu đầu `n` của cạnh `"na"` rồi kết thúc.

Mọi hậu tố bên dưới nút cuối cạnh `"na"` đều có cùng đoạn `"an"` đầu đường, nên đều là vị trí xuất hiện của `an`. **Không có hậu tố nào khác rời cạnh ở giữa nhãn**, vì suffix tree nén không có điểm phân nhánh ẩn ở đó.

## 12. Kiểm tra tồn tại, đếm và liệt kê vị trí xuất hiện

Sau khi tìm được locus, mỗi **lá trong cây con** tương ứng một lần xuất hiện của mẫu trong văn bản gốc.

### 12.1. Chỉ kiểm tra có xuất hiện không

```python
    def contains(self, pattern):
        self._validate_pattern(pattern)
        if pattern == "":
            return True
        return self._locus_node(pattern) is not None
```

Mẫu rỗng được coi là xuất hiện tại mọi ranh giới, kể cả khi văn bản gốc rỗng.

### 12.2. Đếm số lần xuất hiện

```python
    def count(self, pattern):
        self._validate_pattern(pattern)

        if pattern == "":
            return self.n + 1

        node = self._locus_node(pattern)
        if node is None:
            return 0

        return node.leaf_count
```

Nếu đã tính `leaf_count` sau khi xây, `count` chỉ cần định vị mẫu rồi đọc **một số nguyên**. Không cần duyệt mọi lá để đếm.

### 12.3. Liệt kê vị trí

```python
    def occurrences(self, pattern):
        """Mọi vị trí xuất hiện, tăng theo chỉ số trong s."""
        self._validate_pattern(pattern)

        if pattern == "":
            return list(range(self.n + 1))

        node = self._locus_node(pattern)
        if node is None:
            return []

        result = []
        stack = [node]

        while stack:
            current = stack.pop()

            if current.suffix_start is not None:
                result.append(current.suffix_start)
                continue

            for edge in current.edges.values():
                stack.append(edge.child)

        # Thứ tự duyệt cây không nhất thiết là vị trí tăng.
        return sorted(result)
```

**Vì sao phải sắp?** Trie tổ chức hậu tố theo nội dung ký hiệu, không theo vị trí bắt đầu. Trật tự DFS hoặc thứ tự dictionary không tự bảo đảm `[1,3]` thay vì `[3,1]`. Hàm này chọn hợp đồng trả **vị trí tăng dần**.

Nếu ứng dụng không cần thứ tự vị trí, có thể trả kết quả DFS để tránh bước sắp. Nếu muốn giới hạn `k` vị trí nhỏ nhất một cách hiệu quả, cần thêm cấu trúc hoặc thuật toán lựa chọn; chỉ trả `k` lá đầu tiên của DFS **không** bảo đảm đó là các vị trí nhỏ nhất.

## 13. Kiểm thử chức năng với `banana`

Đặt các phương thức ở mục 10–12 **trong cùng lớp `SuffixTree`**; sau đó chạy ví dụ sau. Các `assert` là bộ kiểm tra hành vi, **không phải benchmark**.

### 13.1. Tìm mẫu trong văn bản

```python
tree = SuffixTree("banana")

assert tree.text == "banana$"
assert tree.n == 6
assert tree.root.leaf_count == 7

assert tree.contains("ana")
assert tree.contains("an")
assert tree.contains("ban")
assert tree.contains("banana")
assert tree.contains("")
assert not tree.contains("apple")
assert not tree.contains("bananas")

assert tree.occurrences("ana") == [1, 3]
assert tree.occurrences("an") == [1, 3]
assert tree.occurrences("na") == [2, 4]
assert tree.occurrences("a") == [1, 3, 5]
assert tree.occurrences("ban") == [0]
assert tree.occurrences("banana") == [0]
assert tree.occurrences("x") == []

assert tree.count("ana") == 2
assert tree.count("a") == 3
assert tree.count("na") == 2
assert tree.count("banana") == 1
assert tree.count("z") == 0

# Mẫu rỗng khớp 7 ranh giới của văn bản dài 6.
assert tree.occurrences("") == [0, 1, 2, 3, 4, 5, 6]
assert tree.count("") == 7
```

### 13.2. Kết thúc giữa nhãn cạnh

```python
# "ban" kết thúc giữa cạnh "banana$".
assert tree.occurrences("ban") == [0]

# "an" kết thúc giữa nhãn "na" sau cạnh "a".
assert tree.occurrences("an") == [1, 3]

# Mismatch giữa nhãn không được coi là khớp.
assert tree.occurrences("bax") == []
assert tree.occurrences("anz") == []
```

### 13.3. Văn bản lặp ký hiệu

```python
repeat = SuffixTree("aaaa")

assert repeat.occurrences("a") == [0, 1, 2, 3]
assert repeat.occurrences("aa") == [0, 1, 2]
assert repeat.occurrences("aaa") == [0, 1]
assert repeat.occurrences("aaaa") == [0]
assert repeat.occurrences("aaaaa") == []
assert repeat.count("aa") == 3
assert repeat.root.leaf_count == 5
```

Những lần xuất hiện **được phép chồng lấn**. Trong `aaaa`, mẫu `aa` xuất hiện tại 0, 1 và 2, không chỉ hai đoạn không giao nhau.

### 13.4. Văn bản rỗng và ký hiệu kết thúc

```python
empty = SuffixTree("")

assert empty.text == "$"
assert empty.root.leaf_count == 1
assert empty.contains("")
assert empty.count("") == 1
assert empty.occurrences("") == [0]
assert not empty.contains("a")
assert empty.occurrences("a") == []

try:
    SuffixTree("a$b")
except ValueError:
    pass
else:
    raise AssertionError("phải từ chối '$' trong văn bản gốc")

try:
    tree.occurrences("$")
except ValueError:
    pass
else:
    raise AssertionError("pattern không được chứa '$'")
```

Nếu ứng dụng cần chứa ký hiệu `$` như dữ liệu thật, phải chọn một ký hiệu kết thúc khác chắc chắn không xuất hiện trong văn bản, hoặc biểu diễn sentinel **ngoài miền ký tự dữ liệu**. Không nên âm thầm dùng ký tự đã có trong dữ liệu làm terminator.

## 14. Xác minh bất biến cây và đoạn chỉ số

Một cây có thể trả đúng một số kết quả mẫu ngắn nhưng vẫn chứa **nút thừa**, **đoạn chỉ số sai**, hoặc hai lá cùng một vị trí. Ta có thể kiểm tra độc lập toàn bộ cấu trúc.

### 14.1. Các điều kiện cần xác minh

- `start<end` và mọi chỉ số nằm trong `[0,N]`.
- Ký hiệu đầu của đoạn đúng với khóa dictionary `first`.
- Mỗi nút được đi tới từ đúng một cha.
- Lá không có cạnh con và giữ một `suffix_start` hợp lệ.
- Đường tới lá có **độ dài bằng `N-suffix_start`** và nội dung chính là hậu tố tương ứng.
- Mọi nút trong không phải gốc có ít nhất hai con.
- Các lá mang các vị trí `0,\ldots,n` đúng một lần.
- `leaf_count` tại mọi nút bằng tổng số lá thực.

### 14.2. Hàm kiểm tra cấu trúc và nội dung đường

```python
def validate_suffix_tree(tree):
    source = tree.text
    total = len(source)

    visited = set()
    leaf_positions = []
    counts = {}
    stack = [(tree.root, False, "")]

    while stack:
        node, expanded, path = stack.pop()

        if not expanded:
            assert id(node) not in visited
            visited.add(id(node))

            if node.suffix_start is not None:
                assert not node.edges
                i = node.suffix_start
                assert 0 <= i < total
                assert path == source[i:]
            elif node is not tree.root:
                assert len(node.edges) >= 2

            stack.append((node, True, path))

            for first, edge in node.edges.items():
                assert 0 <= edge.start < edge.end <= total
                assert first == source[edge.start]
                assert isinstance(edge.child, Node)
                label = source[edge.start:edge.end]
                stack.append((
                    edge.child,
                    False,
                    path + label,
                ))
        else:
            if node.suffix_start is not None:
                counts[id(node)] = 1
                leaf_positions.append(node.suffix_start)
            else:
                counts[id(node)] = sum(
                    counts[id(edge.child)]
                    for edge in node.edges.values()
                )

            assert node.leaf_count == counts[id(node)]

    assert sorted(leaf_positions) == list(range(tree.n + 1))
    assert counts[id(tree.root)] == tree.n + 1


for text in ("", "a", "aaaa", "banana", "abababa", "mississippi"):
    validate_suffix_tree(SuffixTree(text))
```

Ở đây phép `path+label` **cố ý tạo chuỗi mới để kiểm thử tính đúng của đường**, nên có thể tốn nhiều bộ nhớ và thời gian trên văn bản lớn. Đó **không phải** cách cây chính lưu nhãn cạnh.

Nếu muốn validator dùng ít bộ nhớ hơn, có thể duy trì **danh sách đoạn chỉ số trên đường** và so sánh tuần tự với hậu tố tại lá, thay vì sao chép nguyên chuỗi `path`.

### 14.3. Đối chiếu với cách tìm trực tiếp

Một kiểm thử chức năng mạnh dùng thuật toán quét chuỗi đơn giản làm mô hình tham chiếu:

```python
def naive_occurrences(text, pattern):
    if pattern == "":
        return list(range(len(text) + 1))

    result = []
    m = len(pattern)

    for i in range(len(text) - m + 1):
        if text[i:i + m] == pattern:
            result.append(i)

    return result


for text in ("", "banana", "aaaaa", "abababa", "mississippi"):
    tree = SuffixTree(text)

    patterns = [
        "", "a", "ana", "na", "issi", "ss",
        "aba", "abab", "xyz", text,
    ]

    for p in patterns:
        assert tree.occurrences(p) == naive_occurrences(text, p)
        assert tree.count(p) == len(naive_occurrences(text, p))
```

`naive_occurrences` quét nhiều vị trí và cắt chuỗi, nên nó có thể kém hiệu quả hơn. Nhưng nó có giá trị như **một mô hình tham chiếu độc lập** trên dữ liệu thử nhỏ.

## 15. Chứng minh ý tưởng: vì sao truy vấn bằng cây hậu tố đúng?

### 15.1. Mọi chuỗi con là tiền tố của một hậu tố

Nếu `pattern` xuất hiện tại vị trí `i`, thì:

\[
s[i:i+m]=pattern.
\]

Do đó `pattern` là tiền tố của `T[i:N]`. Vì cây chứa hậu tố này, đường từ gốc tới lá `i` bắt đầu bằng `pattern`.

### 15.2. Đường khớp mẫu xác định đúng các hậu tố ứng viên

Khi tìm mẫu:

- Nếu không có cạnh theo ký hiệu cần đọc hoặc ký hiệu ở giữa nhãn không khớp, **không hậu tố nào** có tiền tố bằng mẫu.
- Nếu đọc hết mẫu tại nút hoặc giữa cạnh, **mọi lá trong cây con cuối cạnh** có đường bắt đầu bằng mẫu.

Sở dĩ vế sau đúng là vì **không có điểm rẽ nhánh ẩn giữa một nhãn cạnh**. Nếu hai hậu tố đã khác trước vị trí kết thúc mẫu, cây buộc phải có nút phân nhánh ở điểm khác đó.

### 15.3. Lá chính là vị trí xuất hiện

Mỗi lá `i` biểu diễn đúng hậu tố `T[i:N]`. Khi đường tới lá bắt đầu bằng `pattern`, ta có:

\[
T[i:i+m]=pattern.
\]

Với mẫu không chứa `$`, đoạn ấy nằm trong phần văn bản gốc, tức là một lần xuất hiện thật tại `i`. Ngược lại, mọi lần xuất hiện tại `i` đều có lá `i` trong cây con khớp.

Bởi vậy, tập lá bên dưới locus **tương ứng một-một** với tập vị trí xuất hiện của mẫu không rỗng.

### 15.4. Vì sao `leaf_count` cho đúng số lần xuất hiện?

Theo bất biến, mỗi lá là một vị trí bắt đầu hậu tố riêng biệt. Khi locus khớp mẫu, mọi lá dưới đó là một lần xuất hiện. Vì vậy `leaf_count` của locus bằng số lần xuất hiện, kể cả khi các lần xuất hiện **chồng lấn**.

Riêng mẫu rỗng được xử lý theo hợp đồng trả `n+1` ranh giới, tránh nhập nhằng giữa “chuỗi rỗng” và ký hiệu kết thúc kỹ thuật.

## 16. Độ phức tạp: hình dạng cây tuyến tính, cách xây demo bậc hai

Đặt:

- `n`: số ký hiệu của văn bản gốc `s`.
- `N=n+1`: số ký hiệu của chuỗi mở rộng `T`.
- `m`: số ký hiệu của mẫu tìm kiếm.
- `occ`: số lần xuất hiện của mẫu.
- `R`: số nút trong cây con được duyệt để lấy vị trí.
- `σ`: kích thước bảng ký hiệu, bao gồm ký hiệu kết thúc.

### 16.1. Số lá là `N=n+1`

Tính duy nhất của `$` bảo đảm `N` hậu tố mở rộng đều kết thúc tại lá riêng.

Cho `L=N` lá. Trong cây nén chuẩn, mọi nút trong **khác gốc** có ít nhất hai con. Khi `n>0`, gốc cũng có ít nhất hai con (nhánh `$` và ít nhất một nhánh ký hiệu dữ liệu).

Nếu `I` là số nút trong bao gồm gốc và mọi nút trong có ít nhất hai con, thì:

\[
I\le L-1.
\]

Vì vậy tổng số nút và cạnh thỏa:

\[
V=L+I\le 2L-1=2n+1,
\]

\[
E=V-1\le 2n.
\]

Với **văn bản rỗng `n=0`**, cây minh họa có gốc một con và một lá cho `$`, tức 2 nút, 1 cạnh. Đây là trường hợp đặc biệt; kết luận tổng quát vẫn là **O(n+1) nút/cạnh**.

### 16.2. Bộ nhớ của cây khi chỉ giữ đoạn chỉ số

Nếu mỗi nút, cạnh và chỉ số có overhead được chặn hằng số trong mô hình word-RAM:

- Chuỗi `T` duy nhất: O(n) ký hiệu.
- `O(n+1)` nút.
- `O(n+1)` cạnh.
- Mỗi cạnh lưu `(start,end,child)`, không lưu bản sao nhãn.

Suy ra:

\[
M_{\mathrm{suffix\ tree}}=O(n+1)
\]

đơn vị ký hiệu và từ máy, theo mô hình ấy.

Nếu lưu **chuỗi nhãn cạnh riêng** bằng `T[start:end]`, tổng lượng ký hiệu được sao chép vào các nhãn có thể lớn hơn; vì thế biểu diễn đoạn chỉ số là một phần quan trọng của bảo đảm không gian.

### 16.3. Thời gian xây của cài đặt minh họa

Mã ở mục 10 chèn lần lượt **`N` hậu tố**. Một lần chèn có thể phải so khớp một lượng ký hiệu tỷ lệ độ dài hậu tố:

\[
N-i.
\]

Tổng lượng ký hiệu có thể phải xét là:

\[
\sum_{i=0}^{N-1}(N-i)
=\frac{N(N+1)}2=\Theta(n^2).
\]

Với tra cạnh dictionary kỳ vọng O(1) cho mỗi lựa chọn và đọc ký hiệu trực tiếp, thuật toán chèn từng hậu tố có chặn **O(n²)** kỳ vọng theo mô hình này, và có những dữ liệu như chuỗi lặp nhiều ký hiệu làm chi phí đạt bậc hai.

**Rất quan trọng:** Cây sau khi xây có **O(n) không gian** không đồng nghĩa rằng cách xây lần lượt từng hậu tố ở đây có thời gian **O(n)**.

### 16.4. Một bẫy khác: tạo chuỗi hậu tố tạm

Nếu viết:

```python
for i in range(len(text)):
    suffix = text[i:]
    # chèn suffix vào một trie
```

ta đã tạo các bản sao hậu tố với tổng độ dài Θ(n²). Nếu tiếp tục dùng `suffix[j:]` và `edge_label[k:]` nhiều lần trong vòng lặp, còn có thể phát sinh các khoản sao chép làm triển khai chậm hơn rất nhiều.

Bản demo tránh điều đó bằng **chỉ số `pos`** và các phép so sánh `T[pos+j]`. Nó có thể vẫn O(n²) thời gian vì cần so khớp nhiều ký hiệu, nhưng không bắt buộc giữ O(n²) byte hậu tố.

### 16.5. Chi phí tìm một mẫu

Trong quá trình tìm, mã đọc mỗi ký hiệu mẫu theo thứ tự, tối đa một lần trên đường khớp; phần chọn cạnh dựa trên dictionary của nút.

Với giả định tra dictionary theo ký hiệu O(1) kỳ vọng, tìm locus có thời gian:

\[
T_{\mathrm{locate}}=O(m+1)\quad\text{kỳ vọng}.
\]

Nếu dùng một mảng cạnh sắp hoặc cây cân bằng ở mỗi nút, chi phí chọn cạnh có thể phụ thuộc `d_v` hay `σ`, không thể tự gọi O(1) cho mọi biểu diễn.

### 16.6. Chi phí liệt kê vị trí

Khi locus có `occ` lá, cây con cần duyệt có **O(occ) nút** trong cây hậu tố nén chuẩn (bỏ qua trường hợp gốc đặc biệt). Vì mọi nút trong không phải gốc có ít nhất hai con, số nút ở cây con bị chặn tuyến tính theo số lá của nó.

- Liệt kê vị trí **không sắp**: O(m+occ) kỳ vọng theo mô hình con của bài.
- Trả vị trí **tăng dần bằng `sorted`**: O(m+occ log(occ+1)) thời gian theo số phép so sánh vị trí.
- Đếm với `leaf_count` đã có: O(m+1) kỳ vọng.

Nếu mẫu không xuất hiện, không có cây con cần duyệt.

## 17. Tại sao những thuật toán xây suffix tree tuyến tính khó hơn?

Có những thuật toán xây suffix tree trong **O(n)** thời gian dưới các giả định thích hợp, nổi bật là các họ thuật toán của Weiner, McCreight và Ukkonen. Chúng **không** đơn giản là vòng lặp chèn mọi hậu tố như mục 10.

### 17.1. Vấn đề của cách xây đơn giản

Khi chèn hai hậu tố liền nhau:

```text
T[i:N]   và   T[i+1:N]
```

chúng có liên hệ rất mạnh: hậu tố sau chỉ bỏ ký hiệu đầu của hậu tố trước. Cách chèn từ gốc mỗi lần lại **đọc lại nhiều đoạn ký hiệu đã được so khớp trước đó**, dẫn đến O(n²) thời gian.

Thuật toán xây tối ưu tái sử dụng thông tin giữa các lần xử lý thay vì làm lại công việc.

### 17.2. Suffix link: nhảy giữa các đoạn có liên hệ

Một **suffix link** là liên kết phụ giữa các nút trong, về mặt trực giác đưa trạng thái ứng với chuỗi `aX` sang trạng thái ứng với `X`, tức bỏ ký hiệu đầu.

Ví dụ:

```text
"a" + "na" = "ana"
        |
        | suffix link (ý tưởng)
        v
       "na"
```

Suffix link giúp không phải quay về gốc để đi lại từ đầu khi xử lý hậu tố liên tiếp. Cách đặt và duy trì suffix link cụ thể phụ thuộc thuật toán và các trạng thái *explicit/implicit* trong cây nén.

### 17.3. Ukkonen và các khái niệm chủ chốt

Trong một cài đặt Ukkonen điển hình, ta gặp:

- **Pha** (*phase*): xử lý thêm một ký hiệu mới của văn bản.
- **Mở rộng** (*extension*): bảo đảm các hậu tố liên quan được biểu diễn sau pha.
- **Điểm hoạt động** (*active point*): trạng thái đang xét, có thể nằm ở nút hoặc giữa cạnh.
- **Suffix link**: tái sử dụng quan hệ giữa các hậu tố.
- **Đầu cạnh lá động** (*shared leaf end*): nhiều cạnh lá có thể cùng tham chiếu một điểm kết thúc đang tăng khi văn bản được xử lý.
- **Skip/count trick**: bỏ qua toàn bộ nhãn cạnh dựa trên độ dài, thay vì so từng ký hiệu khi vị trí đã được biết hợp lệ.

Những kỹ thuật này cùng tạo bảo đảm xây tuyến tính dưới điều kiện rõ ràng, không phải chỉ nhờ dùng một kiểu dictionary nhanh.

### 17.4. Đầu cạnh lá động khác với đoạn tĩnh của bài

Mã demo luôn xây từ `T` đã hoàn chỉnh; mọi cạnh có `end` là **một số nguyên cố định** khi tạo.

Trong Ukkonen trực tuyến, nhiều cạnh lá có thể giữ **tham chiếu đến cùng một biến end đang tăng**. Khi thêm ký hiệu, các lá hiện hành mở rộng mà không phải lần lượt sửa mọi `end`.

Do đó, dù cùng có ý tưởng **đoạn của chuỗi gốc**, cách biểu diễn `end` ở thuật toán trực tuyến có thể khác đáng kể cách tĩnh `[start,end)` trong bài.

### 17.5. Điều kiện của chặn O(n)

Các phát biểu “xây suffix tree O(n)” thường giả định:

- Một bảng ký hiệu có thể xử lý trong thời gian phù hợp.
- Có thể đọc ký hiệu và chỉ số đoạn hiệu quả.
- Phép tìm/cập nhật nhánh được hỗ trợ với chi phí phù hợp, ví dụ bảng chữ cái cố định nhỏ.
- Sử dụng **thuật toán xây tuyến tính thực sự**, chứ không phải chèn lại mọi hậu tố từ gốc.

Nếu ký hiệu cần so sánh tốn nhiều thời gian, bảng chữ cái lớn hoặc xử lý cạnh bằng cấu trúc có chi phí logarithmic, phải bổ sung những hệ số tương ứng. Không thể suy “O(n) trong mọi ngôn ngữ/runtime và mọi encoding”.

## 18. Truy vấn mẫu là bài toán nhạy với đầu ra

Cây hậu tố được dùng để tìm vị trí xuất hiện, không chỉ để trả Boolean.

### 18.1. Ví dụ có nhiều lần xuất hiện

Trong `"aaaaa"`, mẫu `"aa"` xuất hiện tại:

```text
0: aa...
1:  aa...
2:   aa...
3:    aa
```

Vị trí là `[0,1,2,3]`, tức 4 lần xuất hiện **có chồng lấn**.

Ngay cả một chỉ mục hoàn hảo cũng phải tạo **4 chỉ số** nếu người dùng yêu cầu tất cả. Nếu mẫu xuất hiện `occ` lần, phần xuất kết quả có cận dưới:

\[
\Omega(occ).
\]

### 18.2. Tìm tồn tại, đếm và liệt kê khác nhau

| Yêu cầu | Cần làm sau khi tìm locus | Chi phí thêm |
| --- | --- | --- |
| Có xuất hiện không? | Không cần duyệt lá | O(1) |
| Có bao nhiêu lần? | Đọc `leaf_count` | O(1) sau tiền xử lý |
| Trả mọi vị trí, không cần thứ tự | Duyệt cây con | O(occ) |
| Trả vị trí tăng dần như mã | Duyệt và sắp | O(occ log(occ+1)) |
| Chỉ trả `k` vị trí nhỏ nhất | Cần chọn đúng `k` nhỏ nhất | Không tự O(k) chỉ vì có `limit` |

### 18.3. Tại sao gợi ý dạng “vị trí đầu tiên” cần chỉ mục phụ?

Nếu muốn vị trí xuất hiện nhỏ nhất cho mọi mẫu, có thể lưu `min_suffix_start` tại mỗi nút, tương tự `leaf_count`. Sau khi tìm locus, trả giá trị nhỏ nhất của các lá dưới đó trong O(1) thời gian sau tiền xử lý.

Nhưng việc lưu metadata như vậy phải được cập nhật nếu văn bản/chỉ mục thay đổi. Với cây tĩnh, tiền xử lý `min` theo hậu tự rất đơn giản; với chỉ mục động, cần xem thuật toán cập nhật.

## 19. Những ứng dụng khác của cấu trúc hậu tố

### 19.1. Đếm số chuỗi con phân biệt

Mọi chuỗi con không rỗng của `s` tương ứng một **điểm duy nhất trên đường đi trong cây hậu tố** mà chưa đi qua ký hiệu `$`. Với nhãn cạnh gồm nhiều ký hiệu, mỗi vị trí dọc cạnh thêm một chuỗi tiền tố mới.

Có thể đếm số chuỗi con phân biệt bằng cách cộng **độ dài phần nhãn không chứa `$`** của mọi cạnh:

\[
D=\sum_{e\in E}
\big((e.end-e.start)-\mathbf{1}_{e.end=N}\big).
\]

Trong cây của `T=s+$`, ký hiệu `$` chỉ ở cuối `T` và nằm ở **cạnh kết thúc một lá**. Vì vậy mỗi cạnh có `end=N` chứa đúng một ký hiệu kết thúc và phải trừ một; các đoạn còn lại chỉ dùng ký hiệu của `s`.

Với `banana`, số chuỗi con phân biệt không rỗng là **15**. Có thể kiểm tra thủ công theo độ dài:

| Độ dài | Các chuỗi con phân biệt | Số lượng |
| ---: | --- | ---: |
| 1 | `b, a, n` | 3 |
| 2 | `ba, an, na` | 3 |
| 3 | `ban, ana, nan` | 3 |
| 4 | `bana, anan, nana` | 3 |
| 5 | `banan, anana` | 2 |
| 6 | `banana` | 1 |
| **Tổng** |  | **15** |

Công thức đếm là một ứng dụng của **nhãn cạnh nén**: có nhiều chuỗi con khác nhau kết thúc **giữa cạnh**, không chỉ tại nút.

### 19.2. Chuỗi con lặp dài nhất

Một chuỗi con xuất hiện ít nhất hai lần khi locus của nó có **ít nhất hai lá** bên dưới. Do đó bài toán *longest repeated substring* có thể tìm bằng cách:

1. Duyệt các nút trong, theo dõi **độ dài đường nhãn từ gốc**.
2. Chọn nút có độ sâu ký hiệu lớn nhất mà `leaf_count≥2`.
3. Khôi phục chuỗi trên đường hoặc dùng một hậu tố đại diện để cắt ra đoạn tương ứng.

Với `banana`, một chuỗi con lặp dài nhất là `"ana"`, dài 3, xuất hiện tại vị trí 1 và 3.

Đoạn lặp **được phép chồng lấn**. Nếu bài toán yêu cầu hai lần xuất hiện **không chồng lấn**, cần thêm điều kiện về khoảng cách vị trí, không thể dùng mỗi `leaf_count≥2`.

### 19.3. Chuỗi con chung giữa nhiều văn bản

Có thể mở rộng tư duy sang **generalized suffix tree** cho nhiều chuỗi, mỗi chuỗi có ký hiệu kết thúc riêng không xuất hiện trong dữ liệu. Các lá ghi cả **ID văn bản và vị trí**.

Muốn tìm chuỗi con chung, cần xác định cây con chứa lá từ những văn bản nào. Nhưng thuật toán và bộ nhớ sẽ thay đổi; không nên ghép các văn bản bằng cùng một sentinel rồi suy ra ngay các kết quả đúng.

### 19.4. Chỉ mục văn bản đọc nhiều, ít thay đổi

Nếu văn bản được giữ cố định và có rất nhiều truy vấn substring, tiền xử lý bằng cây hậu tố có thể có lợi. Nếu văn bản thay đổi liên tục, phải cân nhắc chi phí xây lại hoặc dùng thuật toán/chỉ mục động phù hợp.

Cây hậu tố không tự là cấu trúc sửa văn bản bất kỳ trong O(1); những chỉ số đoạn có thể trở nên sai khi thay đổi nội dung `T`.

## 20. So sánh suffix tree, suffix array và tìm trực tiếp

Cùng phục vụ tìm chuỗi con, nhưng các biểu diễn có đánh đổi khác nhau.

| Tiêu chí | Tìm trực tiếp trên `s` | Suffix tree | Suffix array |
| --- | --- | --- | --- |
| Tiền xử lý | Không cần | Có, có thể O(n) với thuật toán phù hợp | Xây mảng các chỉ số hậu tố có thứ tự |
| Cấu trúc | Chuỗi gốc | Cây nén, cạnh bằng đoạn chỉ số | Mảng chỉ số bắt đầu hậu tố |
| Bộ nhớ chỉ mục | O(1) ngoài văn bản | O(n) nút/cạnh và metadata | O(n) chỉ số, thường gọn hơn cây |
| Tìm có xuất hiện? | Phụ thuộc thuật toán tìm mẫu | O(m) theo mô hình chọn cạnh hằng số sau xây | Tìm nhị phân theo thứ tự hậu tố, chi phí so chuỗi |
| Trả mọi vị trí | Quét hoặc dùng thuật toán match | Duyệt lá dưới locus | Lấy dải hậu tố phù hợp trong mảng |
| Đếm số lần | Có thể cần quét | Đọc `leaf_count` sau tìm | Đếm độ dài dải hậu tố khớp |
| Thứ tự kết quả | Theo cách quét | Theo thứ tự cây hoặc sắp vị trí | Theo thứ tự hậu tố, không mặc định theo vị trí |

### 20.1. Suffix array lưu gì?

**Suffix array** giữ một mảng `SA` gồm các vị trí bắt đầu hậu tố, sắp theo thứ tự từ điển của `T[i:]`.

Ví dụ với `banana$`, thứ tự hậu tố tăng là:

```text
$       (6)
a$      (5)
ana$    (3)
anana$  (1)
banana$ (0)
na$     (4)
nana$   (2)
```

Vì vậy:

```text
SA = [6, 5, 3, 1, 0, 4, 2]
```

Chỉ cần giữ **7 số nguyên** làm chỉ mục hậu tố, ngoài văn bản gốc. Một triển khai thực tế còn có thể giữ mảng LCP, chỉ mục rank hoặc dữ liệu phụ để tăng tốc tìm.

### 20.2. Tìm mẫu bằng suffix array

Các hậu tố có tiền tố bằng mẫu tạo thành **một khoảng liên tiếp** trong thứ tự từ điển. Có thể dùng tìm nhị phân để xác định khoảng ấy.

Nếu so một mẫu dài `m` với một hậu tố từ đầu mất tới O(m), một phân tích đơn giản cho việc xác định khoảng là **O(m log n)** theo số ký hiệu so sánh trong trường hợp xấu, chưa kể xuất kết quả. Các thuật toán tối ưu dùng LCP và dữ liệu phụ có thể cải thiện việc lặp lại so sánh.

### 20.3. Suffix automaton không phải suffix tree

**Suffix automaton** là một automaton hữu hạn biểu diễn các chuỗi con của một văn bản qua **trạng thái và chuyển trạng thái**, thường có kích thước tuyến tính. Nó rất hữu ích cho một số truy vấn substring nhưng **không phải** trie các hậu tố và không có các cạnh nhãn đoạn của chuỗi gốc theo cùng định nghĩa.

Không nên gán trực tiếp một lá cho mỗi vị trí bắt đầu hậu tố trong suffix automaton như đang làm với suffix tree.

### 20.4. Tiêu chí chọn

Suffix tree có lợi khi cần nhiều truy vấn khác nhau trên một văn bản và muốn khai thác cấu trúc các nhánh tiền tố hậu tố. Suffix array thường có bố trí bộ nhớ liên tục, dễ tận dụng cache và ít đối tượng con trỏ hơn. Tìm trực tiếp phù hợp khi văn bản nhỏ hoặc số truy vấn ít, tránh chi phí xây chỉ mục.

**Không có kết luận “suffix tree luôn nhanh nhất”** nếu chưa đo workload, bộ nhớ, số truy vấn và cách triển khai cụ thể.

## 21. Unicode, vị trí ký tự và trách nhiệm chuẩn hóa

Trong mã Python, `str` được đánh chỉ số theo **Unicode code point**. Điều này ảnh hưởng trực tiếp đến ý nghĩa `start,end` và các vị trí xuất hiện.

### 21.1. Byte UTF-8 không giống vị trí Python `str`

```python
text = "bàn"

print(len(text))                  # Số code point.
print(len(text.encode("utf-8")))  # Số byte UTF-8.
```

Nếu xây cây trên `str`, các chỉ số cạnh và vị trí xuất hiện là **chỉ số code point** trong `str`. Nếu xây cây trên `bytes` UTF-8, chúng là **chỉ số byte**, và mẫu phải được mã hóa cùng cách.

Không được báo một vị trí byte là “vị trí ký tự hiển thị” mà không có bảng ánh xạ hoặc quy tắc chuyển đổi.

### 21.2. Dấu kết hợp và chuẩn hóa

```python
import unicodedata

composed = "bàn"
decomposed = "ba\u0300n"

assert composed != decomposed
assert (
    unicodedata.normalize("NFC", composed)
    == unicodedata.normalize("NFC", decomposed)
)
```

Hai chuỗi có thể hiển thị giống nhau nhưng là các dãy code point khác nhau, dẫn đến **cây hậu tố và vị trí khác nhau**.

Nếu ứng dụng muốn xem chúng là tương đương, hãy chuẩn hóa **trước khi xây chỉ mục** và chuẩn hóa **mọi mẫu truy vấn** bằng cùng quy tắc.

### 21.3. Vị trí trong văn bản chuẩn hóa khác vị trí trong nguồn ban đầu

Chuẩn hóa có thể đổi số lượng code point và các offset. Vì vậy, `occurrences` trả vị trí trong **văn bản đã đưa vào cây**, không mặc nhiên là vị trí trong văn bản thô trước chuẩn hóa.

Nếu giao diện cần tô sáng đúng vị trí trong bản gốc, hệ thống phải duy trì **bảng ánh xạ offset** từ văn bản chỉ mục sang văn bản ban đầu hoặc một cơ chế tương đương.

### 21.4. Grapheme cluster là một đơn vị khác

Người dùng có thể coi nhiều code point là một “ký tự nhìn thấy”. Nếu cần chỉ số theo **cụm tự vị** (*grapheme cluster*), nên phân đoạn chuỗi theo quy tắc Unicode thích hợp trước khi xây chỉ mục, rồi điều chỉnh các thao tác truy vấn và chuyển đổi vị trí.

Không thể chỉ đổi tên `len(text)` từ “code point” sang “ký tự hiển thị” mà giữ nguyên các công thức chỉ số.

## 22. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Giữ bản sao `T[i:]` cho mọi hậu tố | Dữ liệu hậu tố có tổng độ dài Θ(n²) | Giữ một `T` và nhãn bằng chỉ số đoạn |
| Dùng khoảng đóng nhưng thao tác như nửa mở | Lỗi lệch 1, thiếu hoặc thừa ký hiệu | Quy ước `[start,end)` nhất quán |
| Quên hậu tố `"$"` | Thiếu lá cho hậu tố rỗng của văn bản gốc | Chèn cả `i=n` |
| Dùng ký hiệu kết thúc đã xuất hiện trong văn bản | Các hậu tố không được tách biệt đúng | Chọn sentinel mới hoặc từ chối đầu vào |
| Coi `$` là ký tự truy vấn thường | Trả vị trí không thuộc dữ liệu gốc | Không cho pattern chứa sentinel |
| Giữ cạnh nhãn rỗng | Có thể tạo vòng lặp hoặc biểu diễn mơ hồ | Yêu cầu `start<end` |
| Hai cạnh ra cùng ký hiệu đầu | Mất tính duy nhất phép chọn cạnh | Split đúng tại LCP |
| Tạo nút không terminal chỉ một con | Cây không còn dạng nén chuẩn | Gộp các đoạn không phân nhánh |
| Khi split thì sao chép chuỗi nhãn thật | Phá lợi thế lưu đoạn tham chiếu | Chỉ tính lại `start,end` |
| Mẫu hết giữa cạnh mà báo không có | Bỏ sót substring hợp lệ | Chấp nhận locus ở giữa nhãn |
| Chỉ đếm số nút terminal ở đường mẫu | Bỏ sót vị trí trong các lá con | Đọc `leaf_count` hoặc duyệt lá bên dưới |
| Coi DFS là thứ tự vị trí tăng | Danh sách vị trí trả sai hợp đồng | Sắp chỉ số hoặc có index phụ |
| Cho rằng `limit=k` làm truy vấn O(k) | Có thể phải xét nhiều lá để biết k vị trí nhỏ nhất | Phân tích số lá duyệt và chọn lọc |
| Coi O(n) nút nghĩa xây O(n) | Thuật toán chèn tuần tự vẫn O(n²) | Phân biệt không gian và thời gian xây |
| Gọi vòng for chèn hậu tố là “Ukkonen” | Gán sai độ phức tạp tuyến tính | Chỉ gọi Ukkonen khi có đầy đủ cơ chế của nó |
| Sửa `self.text` sau khi xây | Mọi nhãn cạnh có thể đổi nghĩa | Giữ nguồn bất biến và sống cùng cây |
| Không tính trường hợp text rỗng | Sai số lá/nút hoặc xử lý mẫu rỗng | Đặc tả `n=0` và `count("")=1` |
| Tính vị trí byte như vị trí code point | Tô sáng hoặc trả offset sai | Ghi rõ đơn vị và chuyển đổi offset |
| Chuẩn hóa văn bản mà không chuẩn hóa mẫu | Truy vấn không nhất quán | Chuẩn hóa đầu vào và mẫu theo cùng chính sách |

## 23. Bài tập vận dụng có gợi ý giải

### Bài 1 — Liệt kê hậu tố

Cho `s="aba"`. Viết `T` sau khi thêm `$` và liệt kê mọi hậu tố mở rộng kèm vị trí bắt đầu.

**Gợi ý:** `T="aba$"`, các hậu tố bắt đầu tại 0,1,2,3 lần lượt là `aba$`, `ba$`, `a$`, `$`.

### Bài 2 — Tổng độ dài các hậu tố

Văn bản gốc dài `n=5`, chuỗi mở rộng dài `N=6`. Tổng độ dài các hậu tố mở rộng là bao nhiêu?

**Gợi ý:** `6+5+4+3+2+1=21=N(N+1)/2`. Đó là lý do không nên giữ bản sao mọi hậu tố.

### Bài 3 — Đoạn chỉ số nửa mở

Với `T="banana$"`, `T[2:4]` và `T[4:7]` là những chuỗi nào?

**Gợi ý:** `T[2:4]="na"` và `T[4:7]="na$"`. Chỉ số kết thúc không được lấy vào.

### Bài 4 — Nhãn cạnh có thật sự là chuỗi mới?

Một cạnh lưu `start=2,end=4` với tham chiếu tới `T`. Khi tìm mẫu, phải tạo `T[2:4]` thành `str` mới không?

**Gợi ý:** Không. Có thể đọc trực tiếp `T[2]` và `T[3]` để so khớp.

### Bài 5 — Cây của `banana$`

Từ sơ đồ mục 6, những lá nào nằm bên dưới locus của mẫu `"ana"`?

**Gợi ý:** Lá 1 và 3, nên vị trí xuất hiện là `[1,3]` và số lần là 2.

### Bài 6 — Mẫu hết giữa cạnh

Trong `banana`, truy vấn `"ban"` kết thúc giữa cạnh `"banana$"`. Có nên trả không tìm thấy không?

**Gợi ý:** Không. Mẫu khớp tiền tố của cạnh và xuất hiện ở vị trí 0.

### Bài 7 — Chồng lấn

Trong `"aaaa"`, mẫu `"aa"` xuất hiện ở những vị trí nào?

**Gợi ý:** `[0,1,2]`. Các lần xuất hiện chồng lấn vẫn được tính.

### Bài 8 — Hậu tố rỗng và mẫu rỗng

Với văn bản gốc `"ab"`, cây có bao nhiêu lá? Theo hợp đồng của bài, `occurrences("")` và `count("")` bằng gì?

**Gợi ý:** Có 3 lá cho `ab$`, `b$`, `$`. Mẫu rỗng có các vị trí `[0,1,2]` và count bằng 3.

### Bài 9 — Split cạnh theo LCP

Cạnh cũ mang `"anana$"`. Chèn hậu tố `"ana$"`. LCP là gì, và ba nhãn mới sau split là gì?

**Gợi ý:** LCP `"ana"`. Tạo nhãn chung `"ana"`, nhánh cũ `"na$"` và nhánh mới `"$"`.

### Bài 10 — Bất biến đầu ký hiệu

Có thể để hai cạnh `"cat"` và `"car"` trực tiếp đi ra cùng một nút trong suffix tree nén chuẩn không?

**Gợi ý:** Không; cả hai bắt đầu bằng `c`. Phải gộp phần chung `ca` và tách ở `t`, `r`.

### Bài 11 — Số nút tối đa

Với văn bản gốc dài `n=100`, có bao nhiêu lá? Chặn số nút và số cạnh của suffix tree nén chuẩn khi `n>0` là gì?

**Gợi ý:** 101 lá, tối đa `2n+1=201` nút và `2n=200` cạnh; chặn là theo hình dạng cây đầy đủ đã nén.

### Bài 12 — Đếm bằng metadata

Nếu mẫu tìm tới locus có `leaf_count=37`, phải duyệt cả 37 lá để trả số lần xuất hiện không?

**Gợi ý:** Không, nếu bộ đếm đã được tính đúng. Có thể trả 37 ngay sau bước tìm mẫu; duyệt lá chỉ cần khi yêu cầu vị trí cụ thể.

### Bài 13 — Vì sao xây minh họa không O(n)?

Cây có O(n) cạnh, nhưng tại sao vòng lặp chèn `T[i:]` cho mọi `i` có thể mất O(n²)?

**Gợi ý:** Mỗi hậu tố có thể khiến thuật toán đọc lại O(n-i) ký hiệu. Tổng theo `i` bằng Θ(n²) trong trường hợp xấu.

### Bài 14 — Ukkonen khác chèn đơn giản thế nào?

Kể tên ba ý tưởng giúp thuật toán Ukkonen tránh làm lại nhiều phép so khớp.

**Gợi ý:** Suffix link, active point, end của cạnh lá dùng chung, và skip/count trick (chỉ cần nêu ba).

### Bài 15 — So sánh suffix tree với suffix array

Với `banana$`, suffix array tăng theo từ điển là gì? Nó lưu nhãn cạnh không?

**Gợi ý:** `[6,5,3,1,0,4,2]`. Suffix array giữ vị trí đầu hậu tố đã sắp, không có các đối tượng cạnh như suffix tree.

### Bài 16 — Số chuỗi con phân biệt

Hãy đếm số chuỗi con liên tiếp khác nhau của `banana` không kể chuỗi rỗng.

**Gợi ý:** 15. Có thể đếm theo độ dài hoặc cộng các độ dài cạnh không chứa `$` của suffix tree.

### Bài 17 — Unicode và vị trí

Cây xây trên `str` Python nhưng giao diện đánh dấu theo byte UTF-8. Có thể dùng trực tiếp `occurrences` làm offset byte không?

**Gợi ý:** Không. Chỉ số trong cây là số code point; cần cơ chế chuyển đổi sang offset byte hoặc xây chỉ mục trên bytes với hợp đồng phù hợp.

### Bài 18 — Chọn cấu trúc theo workload

Một hệ thống có văn bản dài ít thay đổi, hàng triệu truy vấn substring. Hệ khác chỉ tìm một mẫu duy nhất trên văn bản ngắn. Bạn nên cân nhắc gì?

**Gợi ý:** Hệ nhiều truy vấn có thể lợi từ tiền xử lý suffix tree/array; hệ ít truy vấn thường không cần trả chi phí xây chỉ mục. So thời gian xây, RAM, độ dài mẫu, số lần xuất hiện và yêu cầu thứ tự.

## 24. Checklist trước khi xây chỉ mục hậu tố

```text
1. Đặc tả:
   - Mục tiêu là contains, count hay occurrences?
   - Mẫu rỗng có n+1 vị trí không?
   - Có cho phép lần xuất hiện chồng lấn?
   - Kết quả trả vị trí tăng hay thứ tự từ điển?

2. Nguồn:
   - Ký hiệu là byte, code point hay grapheme?
   - Có một terminator duy nhất không xuất hiện trong text?
   - Text có bất biến trong vòng đời của cây?
   - Nếu chuẩn hóa Unicode, offset trả về tương ứng bản nào?

3. Biểu diễn:
   - Mỗi cạnh có start/end theo khoảng [start,end)?
   - Đọc nhãn qua self.text mà không tạo chuỗi lưu riêng?
   - Mọi nhãn không rỗng, ký hiệu đầu khác nhau?
   - Mỗi lá giữ một suffix_start từ 0 đến n?
   - Nút trong không phải gốc có ít nhất hai con?

4. Xây:
   - Chèn cả n+1 hậu tố của text+"$"?
   - Khi mismatch đã split cạnh đúng LCP?
   - Lá mới giữ đúng vị trí bắt đầu hậu tố?
   - Tổng số nút/cạnh được giới hạn O(n)?
   - Thuật toán xây là naïve O(n²) hay loại tuyến tính thật?

5. Truy vấn:
   - Mẫu được phép hết giữa cạnh?
   - Mismatch giữa nhãn có trả không tìm thấy?
   - Count đọc leaf_count sau khi tìm locus?
   - Occurrences duyệt lá và sắp nếu hợp đồng cần vị trí tăng?
   - Truy vấn không được chứa terminator?

6. Kiểm chứng:
   - Từng lá có đường đúng T[suffix_start:]?
   - Các suffix_start có đủ 0..n, không lặp?
   - leaf_count có bằng tổng lá trong cây con?
   - Đã thử "banana", ký tự lặp, text rỗng và Unicode?
   - Có đối chiếu với quét substring trên tập dữ liệu nhỏ?

7. Hiệu năng:
   - n, m, occ và phân bố truy vấn?
   - Có cần đánh đổi RAM suffix tree lấy suffix array?
   - Có cần thuật toán tuyến tính như Ukkonen?
   - Có đo RAM giữ lại và bộ nhớ đỉnh khi xây?
```

## 25. Tổng kết

**Cây hậu tố** biến việc tìm một chuỗi con thành bài toán **đi theo đường tiền tố của các hậu tố**. Mỗi hậu tố mở rộng `T[i:]` kết thúc ở một lá ghi vị trí `i`; một mẫu xuất hiện khi nó khớp một đường từ gốc, **kể cả khi dừng giữa nhãn cạnh**.

Hai quyết định biểu diễn tạo nên lợi ích lớn:

- **Gắn ký hiệu kết thúc duy nhất:** mọi hậu tố mở rộng có lá riêng, giúp vị trí xuất hiện được biểu diễn minh bạch.
- **Lưu nhãn cạnh bằng `[start,end)` trong một `T` duy nhất:** không cần sao chép nội dung hậu tố hoặc nhãn cạnh, nên cây nén có **O(n) nút/cạnh và O(n) bộ nhớ trong mô hình phù hợp**.

Nhưng **không gian tuyến tính không tự đồng nghĩa thời gian xây tuyến tính**. Cài đặt đơn giản bằng cách chèn lần lượt tất cả hậu tố vẫn có thể O(n²) thời gian; muốn đạt O(n) với giả định thích hợp cần thuật toán xây chuyên dụng như Ukkonen, cùng suffix link, active point và cách cập nhật đầu cạnh lá.

Khi nắm rõ hậu tố, đoạn chỉ số, bất biến cây, locus giữa cạnh, chi phí xuất vị trí và điều kiện mô hình tính toán, ta có thể sử dụng suffix tree một cách đúng đắn và chọn giữa cây hậu tố, suffix array hoặc tìm trực tiếp dựa trên workload thực tế.

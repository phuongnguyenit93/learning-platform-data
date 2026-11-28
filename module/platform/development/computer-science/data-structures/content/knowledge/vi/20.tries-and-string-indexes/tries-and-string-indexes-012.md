# So sánh cây hậu tố với mảng hậu tố theo bộ nhớ và phép truy vấn

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** So sánh cây hậu tố với mảng hậu tố theo bộ nhớ và phép truy vấn

Một hệ thống lưu văn bản `"banana"` và cần trả lời những câu hỏi: `"ana"` có xuất hiện không, xuất hiện bao nhiêu lần, ở những vị trí nào, chuỗi con lặp dài nhất là gì? Có ít nhất hai cách xây chỉ mục hậu tố:

- **Cây hậu tố** (*suffix tree*): trie của tất cả hậu tố, đã nén các đường không phân nhánh; nhãn cạnh thường lưu **khoảng chỉ số** của chuỗi gốc.
- **Mảng hậu tố** (*suffix array*, ký hiệu `SA`): một **mảng chỉ số bắt đầu hậu tố** được sắp theo thứ tự từ điển; thường kết hợp **mảng tiền tố chung dài nhất** `LCP`.

Cả hai khai thác tính chất mọi chuỗi con liên tiếp đều là tiền tố của một hậu tố. Nhưng chúng chọn **hình thức chia sẻ thông tin khác nhau**: cây hậu tố giữ cấu trúc nhánh để lần theo mẫu trực tiếp; mảng hậu tố giữ một thứ tự tuyến tính để tìm kiếm nhị phân. Điều đó tạo ra khác biệt về **bộ nhớ thực tế, locality, thời gian xây và kiểu truy vấn** — dù cả hai đều có thể dùng O(n) từ máy trong các mô hình thích hợp.

Bài học thuộc chương **Trie và chỉ mục chuỗi** của mô-đun `COMPUTER_SCIENCE_DATA_STRUCTURES`. Mục tiêu chung của mô-đun là xây nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; học bất biến và phân tích chi phí thời gian–bộ nhớ để lựa chọn cấu trúc phù hợp. Ở đây ta sử dụng chính sự khác nhau giữa **cây liên kết** và **mảng liên tục** làm trọng tâm lựa chọn.

**Nguyên tắc xuyên suốt:** không gán “O(n) bộ nhớ” thành “cùng số byte”, cũng không gán “O(n) thời gian xây tồn tại trong lý thuyết” thành “mọi đoạn mã xây chỉ mục đều chạy O(n)”.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa hậu tố, chuỗi con và điều kiện để một mẫu khớp tại vị trí `i`.
2. Mô tả cấu trúc của suffix tree và suffix array trên cùng một văn bản.
3. Giải thích vai trò **ký hiệu kết thúc duy nhất** trong cây hậu tố và quy ước có/không có hậu tố rỗng.
4. Phát biểu bất biến của các nhãn cạnh `[start,end)`, lá hậu tố, `SA`, `rank` và `LCP`.
5. Đối chiếu độ phức tạp tìm tồn tại, đếm và liệt kê vị trí xuất hiện theo số ký hiệu mẫu và số kết quả.
6. Chứng minh hai chỉ mục đều có thể dùng **O(n) từ máy** nhưng triển khai cây thường có nhiều metadata và con trỏ hơn.
7. Phân biệt **xây cây hậu tố tuyến tính** bằng thuật toán chuyên dụng với **chèn lần lượt hậu tố O(n²)**.
8. Phân biệt xây SA bằng prefix doubling và những thuật toán xây SA tuyến tính.
9. Tính số chuỗi con phân biệt và tìm chuỗi con lặp dài nhất bằng cả hai cách.
10. Nêu cách dùng LCA trên cây hoặc RMQ trên `LCP` để tìm tiền tố chung của hai hậu tố bất kỳ.
11. Cài đặt hai chỉ mục minh họa có cùng API `contains`, `count`, `occurrences` và kiểm thử đối chiếu.
12. Thiết kế benchmark so sánh **RAM còn giữ, bộ nhớ đỉnh, thời gian xây, độ trễ truy vấn và chi phí xuất kết quả**.
13. Chọn chỉ mục theo workload, Unicode, tính bất biến văn bản và giới hạn tài nguyên.

## 2. Đặc tả chung trước khi so sánh

Cho văn bản gốc `s` có `n` ký hiệu và mẫu `p` có `m` ký hiệu. Trong bài, ký hiệu là **Unicode code point của Python `str`**.

Hậu tố bắt đầu tại `i` là `s[i:n]` với `0≤i<n`. Mẫu `p` xuất hiện tại vị trí `i` nếu:

\[
0\le i\le n-m
\quad\text{và}\quad
s[i:i+m]=p.
\]

Với mẫu không rỗng, ta dùng ba phép toán:

\[
contains(p)=\text{có ít nhất một vị trí khớp},
\]

\[
count(p)=|\{i:s[i:i+m]=p\}|,
\]

\[
occurrences(p)=\operatorname{sort}\{i:s[i:i+m]=p\}.
\]

### 2.1. Quy ước về mẫu rỗng

Mẫu rỗng xuất hiện tại **mọi ranh giới** giữa các ký hiệu, cả trước ký hiệu đầu và sau ký hiệu cuối:

\[
occurrences("")=[0,1,\ldots,n].
\]

Do đó `count("")=n+1` và `contains("")=True`, kể cả `s=""`. Đây là **quy ước API**, được áp dụng giống nhau cho cả cây và mảng.

### 2.2. Cho phép các lần xuất hiện chồng lấn

Trong `"aaaa"`, mẫu `"aa"` xuất hiện tại `[0,1,2]`, không chỉ những đoạn đôi một không giao nhau.

Nếu bài toán yêu cầu **các kết quả không chồng lấn**, đó là một bài toán khác; không được thay đổi ngầm ý nghĩa `count` trong quá trình so sánh hai chỉ mục.

### 2.3. Đơn vị của vị trí

Vì dùng `str` Python, các vị trí là **chỉ số code point**, không mặc nhiên là offset byte UTF-8 hoặc vị trí cụm ký tự người dùng nhìn thấy (*grapheme cluster*).

Để benchmark công bằng, cả hai chỉ mục phải dùng **cùng văn bản đã chuẩn hóa, cùng loại ký hiệu và cùng hợp đồng kết quả**.

## 3. Mô hình của hai chỉ mục

### 3.1. Cây hậu tố: giữ các nhánh chung

Một suffix tree là trie nén của các hậu tố. Mỗi cạnh mang **một đoạn chuỗi không rỗng**; mỗi lá ghi một vị trí bắt đầu hậu tố.

Để các hậu tố luôn kết thúc ở lá riêng, ta dùng:

\[
T=s+\$,
\]

với `$` là **ký hiệu kết thúc không xuất hiện trong `s`**.

Với `n` ký hiệu của `s`, có **`n+1` hậu tố** của `T`, ứng với vị trí bắt đầu `0,\ldots,n`. Hậu tố cuối chỉ gồm `$` và đại diện cho hậu tố rỗng của văn bản gốc.

Cây thường có dạng:

```text
Node:
    edges[first_character] -> Edge

Edge:
    start, end     # nhãn logic = T[start:end]
    child

Leaf:
    suffix_start   # vị trí bắt đầu hậu tố
```

**Nhãn cạnh `[start,end)` trỏ vào một `T` duy nhất**, không cần tạo bản sao chuỗi nhãn. Nếu dùng mảng cạnh, cây tìm kiếm con hay Hash Map thay vì dictionary ở mỗi nút, chi phí tìm nhánh sẽ khác.

### 3.2. Mảng hậu tố: giữ thứ tự các hậu tố

`SA` chứa `n` chỉ số bắt đầu hậu tố **không rỗng** của `s`, sao cho:

\[
s[SA[0]:]<s[SA[1]:]<\cdots<s[SA[n-1]:]
\]

theo thứ tự từ điển.

Ví dụ:

```text
s = "banana"
SA = [5, 3, 1, 0, 4, 2]
```

Nếu cần thêm hỗ trợ truy vấn tiền tố chung, ta giữ:

\[
LCP[0]=0,
\]

\[
LCP[r]=
lcp(s[SA[r-1]:],s[SA[r]:])
\quad (1\le r<n).
\]

Mảng nghịch đảo `rank` thỏa `rank[SA[r]]=r`. `SA`, `LCP` và `rank` có thể lưu trong các mảng liên tục.

### 3.3. Hai quy ước n và n+1 không mâu thuẫn

- **Suffix tree trong bài:** xây cho `T=s+$`, có **`n+1` lá**.
- **Suffix array trong bài:** xây trực tiếp cho `s`, có **`n` chỉ số**.

Đây là hai cách biểu diễn khác nhau, nhưng với **mẫu không chứa `$`**, chúng trả cùng vị trí trong văn bản gốc. Khi mẫu rỗng, cả hai dùng quy ước `n+1` ranh giới đã nêu.

Có thể xây SA cho `T` và thu `n+1` phần tử; khi ấy cần điều chỉnh chỉ số, logic sentinel và các công thức. Không được trộn các quy ước trong một đoạn mã.

## 4. Ví dụ song song với `banana`

Xét:

```text
s = "banana"
vị trí:  0 1 2 3 4 5
ký tự:   b a n a n a

T = "banana$"
```

### 4.1. Mảng hậu tố và LCP

| Hạng `r` | `SA[r]` | Hậu tố `s[SA[r]:]` | `LCP[r]` |
| ---: | ---: | --- | ---: |
| 0 | 5 | `a` | 0 |
| 1 | 3 | `ana` | 1 |
| 2 | 1 | `anana` | 3 |
| 3 | 0 | `banana` | 0 |
| 4 | 4 | `na` | 0 |
| 5 | 2 | `nana` | 2 |

```text
SA  = [5, 3, 1, 0, 4, 2]
LCP = [0, 1, 3, 0, 0, 2]
```

Hạng 1 và 2 có hậu tố bắt đầu bằng `ana`. Vì thế mẫu `ana` khớp trong **khoảng SA `[1,3)`**, nhưng vị trí trả theo thứ tự văn bản là `sorted([3,1])=[1,3]`.

### 4.2. Hình dạng cây hậu tố nén

Một suffix tree của `banana$` có thể biểu diễn:

```text
                               root
                     ___________|____________________
                    /           |         |           \
               "banana$"       "a"       "na"         "$"
                   |            |         |            |
                 leaf 0         A         C          leaf 6
                              /   \      / \
                            "$"   "na"  "$" "na$"
                             |     |     |    |
                           leaf5   B   leaf4 leaf2
                                  / \
                                "$" "na$"
                                 |    |
                               leaf3 leaf1
```

Locus của `ana` là nút `B`; dưới nó có các lá 3 và 1. Số lá ở cây con `B` bằng 2.

Mẫu `an` khớp cạnh `a` rồi **dừng giữa cạnh `na`**. Cây không cần tạo nút mới cho mẫu `an`: toàn cây con cuối cạnh `na` vẫn là tập các hậu tố khớp.

### 4.3. Nhãn cạnh bằng các khoảng chỉ số

Trong `T="banana$"`:

| Nhãn logic | Khoảng chỉ số ví dụ |
| --- | --- |
| `banana$` | `[0,7)` |
| `a` | `[1,2)` |
| `na` | `[2,4)` |
| `na$` | `[4,7)` |
| `$` | `[6,7)` |

Một nhãn `na` có thể xuất hiện ở **nhiều cạnh** khác nhau nhưng không nhất thiết cần một đối tượng chuỗi `"na"` riêng cho từng cạnh: chỉ cần `start`, `end` và `T` bất biến.

### 4.4. Một bảng đối chiếu kết quả

| Mẫu | Khoảng hậu tố khớp trong SA | Vị trí đã sắp | Số lá dưới locus |
| --- | --- | --- | ---: |
| `ana` | `SA[1:3]=[3,1]` | `[1,3]` | 2 |
| `an` | `SA[1:3]=[3,1]` | `[1,3]` | 2 |
| `na` | `SA[4:6]=[4,2]` | `[2,4]` | 2 |
| `ban` | `SA[3:4]=[0]` | `[0]` | 1 |
| `x` | Khoảng rỗng | `[]` | 0 |
| `""` | Quy ước riêng | `[0,1,2,3,4,5,6]` | 7 |

Hai chỉ mục mã hóa **cùng quan hệ giữa mẫu và hậu tố**; khác biệt nằm ở cách tìm tập hậu tố phù hợp.

## 5. Bất biến cốt lõi của suffix tree

Một suffix tree nén chuẩn của `T=s+$` cần bảo đảm:

1. Mọi cạnh có nhãn không rỗng: `0≤start<end≤len(T)`.
2. Nhãn của cạnh là **đúng chuỗi `T[start:end]`**, không đổi trong vòng đời cây tĩnh.
3. Hai cạnh ra khỏi một nút không có **ký hiệu đầu trùng nhau**.
4. Đường từ gốc tới lá `i` ghép lại thành đúng `T[i:]`.
5. Có một lá cho mỗi `i∈[0,n]`, không trùng vị trí.
6. Mọi nút trong ngoài gốc có ít nhất hai con; các đoạn một con không terminal được nén.
7. Mỗi nút có tối đa một cha, không có chu trình.
8. Nếu lưu `leaf_count(v)`, nó bằng số lá trong cây con `v`.

Công thức bộ đếm:

\[
leafCount(v)=
\begin{cases}
1,&v\text{ là lá};\\
\sum_{u\in children(v)}leafCount(u),&v\text{ là nút trong}.
\end{cases}
\]

Khi tìm một mẫu kết thúc giữa nhãn cạnh, ta dùng **nút con cuối cạnh ấy** làm đại diện để đếm hoặc duyệt các lá phù hợp.

### 5.1. Nếu không nén nhãn cạnh thì sao?

Suffix trie không nén có thể có O(n²) nút trên một văn bản dài. Các cam kết không gian O(n) của suffix tree dựa trên việc **nén các đường một con** và lưu nhãn cạnh bằng những đoạn tham chiếu thay vì giữ mọi ký tự riêng.

### 5.2. Nếu lưu mảng con đầy đủ ở mỗi nút?

Giả sử bảng chữ cái có `σ` ký hiệu, mỗi nút cấp hẳn mảng `σ` con trỏ. Khi đó phần cấu trúc nhánh có thể tốn O(nσ) ô, dù số nút chỉ O(n).

Phát biểu “suffix tree O(n) bộ nhớ” cần điều kiện về **biểu diễn nhánh**, ví dụ lưu chỉ các cạnh hiện hữu trong dictionary/cấu trúc động hoặc bảng chữ cái cố định nhỏ.

## 6. Bất biến cốt lõi của suffix array và LCP

Với `SA` không chứa hậu tố rỗng:

1. `len(SA)=n`.
2. `SA` là **hoán vị** của `0,1,\ldots,n-1`.
3. Các hậu tố `s[SA[r]:]` tăng theo thứ tự từ điển.
4. `LCP` có đúng `n` phần tử, `LCP[0]=0`.
5. Với `r≥1`, `LCP[r]` là LCP giữa hai hậu tố ở **hạng `r-1` và `r`**, không phải hai hậu tố ở vị trí văn bản `r-1` và `r`.
6. Nếu có `rank`, thì `rank[SA[r]]=r`.

Một chặn hiển nhiên:

\[
0\le LCP[r]\le
\min(n-SA[r-1],n-SA[r])
\quad (1\le r<n).
\]

### 6.1. Vì sao cần ghi rõ quy ước LCP?

Một số tài liệu dùng mảng dài `n-1` với giá trị `LCP[r]` so hậu tố `SA[r]` và `SA[r+1]`. Bài này dùng mảng dài `n`, ô đầu bằng 0 và so với **hậu tố kề trước**.

Hai quy ước tương đương về thông tin nhưng **lệch chỉ số**. Trộn một công thức RMQ của quy ước này với dữ liệu của quy ước kia thường gây lỗi khó tìm.

### 6.2. Tại sao cần rank?

`rank[i]` trả **thứ hạng** của hậu tố bắt đầu ở vị trí `i` trong `SA`. Nó đặc biệt hữu ích khi tính `LCP` bằng Kasai và trả lời LCP của hai hậu tố bất kỳ qua RMQ.

Không được nhầm `SA[r]` (vị trí bắt đầu) với `rank[r]` (thứ hạng của hậu tố bắt đầu tại vị trí r).

## 7. Tìm kiếm mẫu: đi theo cạnh hay tìm khoảng đã sắp

Ta xét mẫu `p` có `m>0` ký hiệu.

### 7.1. Suffix tree: đi theo nhãn cạnh

Tại nút đang xét:

1. Tìm cạnh có ký hiệu đầu `p[j]`.
2. So khớp từng ký hiệu của nhãn `T[start:end]` với phần mẫu còn lại.
3. Nếu mẫu hết **giữa cạnh hoặc đúng cuối cạnh**: tìm thấy locus.
4. Nếu nhãn cạnh hết trước mẫu, đi xuống nút con và tiếp tục.
5. Nếu ký hiệu lệch hoặc thiếu cạnh: không có mẫu.

Với chọn cạnh bằng Hash Map có thời gian O(1) kỳ vọng và so ký hiệu O(1), thời gian tìm locus:

\[
T_{\mathrm{tree,locate}}=O(m+1)\quad\text{kỳ vọng}.
\]

Nếu nút dùng cây cân bằng hoặc tìm tuyến tính trong danh sách cạnh, thời gian chọn cạnh phải được tính thêm.

### 7.2. Suffix array: xác định khoảng hậu tố

Vì `SA` đã xếp các hậu tố theo từ điển, những hậu tố bắt đầu bằng cùng mẫu `p` nằm **liền nhau**.

Tìm hai biên:

- `left`: hạng đầu tiên có hậu tố **không nhỏ hơn** mẫu theo phép so dùng cho truy vấn tiền tố.
- `right`: hạng đầu tiên có hậu tố **lớn hơn nhóm có tiền tố `p`**.

Ta quy ước phép so `cmp(suffix,p)`:

```text
-1 : suffix nhỏ hơn p theo từ điển
 0 : suffix bắt đầu bằng toàn bộ p
+1 : suffix lớn hơn p theo từ điển
```

Khi đó tìm `left` với `cmp≥0` và `right` với `cmp>0`. Các vị trí trong `SA[left:right]` chính là những lần xuất hiện.

Vì có O(log(n+1)) vòng tìm nhị phân và một lần so có thể đọc O(m+1) ký hiệu:

\[
T_{\mathrm{SA,locate}}=
O((m+1)\log(n+1))
\]

cho bản tìm trực tiếp, không tái sử dụng LCP trong quá trình binary search.

### 7.3. Trường hợp chỉ hỏi có hay không

| Cấu trúc | Bước cần làm | Chi phí theo mô hình |
| --- | --- | --- |
| Suffix tree | Tìm đường khớp mẫu | O(m+1) kỳ vọng |
| Suffix array cơ bản | Tìm khoảng `[left,right)` | O((m+1) log(n+1)) |
| SA với kỹ thuật so sánh có tăng tốc LCP | Tái sử dụng tiền tố chung đã biết giữa các phép so | Có thể đạt O(m+log(n+1)) với cấu trúc/thuật toán phù hợp |

**Không được tự suy** hàm tìm nhị phân trong một SA có thêm mảng `LCP` sẽ chạy O(m+log n). Phải thực sự **sửa thuật toán tìm** để tận dụng thông tin tiền tố chung.

## 8. Đếm số lần xuất hiện

### 8.1. Suffix tree

Khi đã tìm được locus của `p`:

- Mỗi lá bên dưới locus đại diện một hậu tố bắt đầu bằng `p`.
- Mỗi hậu tố ấy đại diện một vị trí xuất hiện trong `s`.

Nếu đã lưu và tiền xử lý `leaf_count`:

\[
count(p)=leafCount(locus).
\]

Sau bước tìm mẫu, đọc một số nguyên tốn O(1).

### 8.2. Suffix array

Khoảng hậu tố khớp là `[left,right)`. Do đó:

\[
count(p)=right-left.
\]

Sau hai lần binary search, tính hiệu hai chỉ số là O(1).

### 8.3. So sánh

Điểm khác biệt chủ yếu **không nằm ở bước đếm cuối** — cả hai đều chỉ đọc metadata/khoảng — mà ở chi phí tìm locus hay tìm hai biên.

Nếu `leaf_count` chưa có, cây phải duyệt các lá bên dưới locus để đếm, tốn thêm O(occ). Đây là ví dụ quan trọng về **một metadata nhỏ làm thay đổi chi phí truy vấn**, và việc phải trả chi phí tiền xử lý để có metadata ấy.

## 9. Liệt kê các vị trí xuất hiện và thứ tự đầu ra

Gọi `occ` là số lần xuất hiện của mẫu không rỗng.

### 9.1. Suffix tree

Sau khi tìm locus, duyệt các lá ở cây con. Mỗi lá ghi `suffix_start`.

Nếu cây nén chuẩn và mọi nút trong có ít nhất hai con, cây con chứa `occ` lá có O(occ) nút; do đó:

\[
T_{\mathrm{tree,enumerate}}
=O(m+occ)
\]

kỳ vọng cho việc chọn cạnh và **chưa yêu cầu sắp theo vị trí**.

### 9.2. Suffix array

Với `SA[left:right]`, các vị trí xuất hiện **đã nằm liên tiếp trong mảng**. Có thể sao chép `occ` chỉ số hoặc duyệt trực tiếp đoạn ấy:

\[
T_{\mathrm{SA,enumerate}}
=O((m+1)\log(n+1)+occ).
\]

### 9.3. Sắp theo vị trí văn bản

Cả hai cách trên thường sinh vị trí theo **thứ tự từ điển của các hậu tố**, không tự theo vị trí bắt đầu tăng dần.

Trong `banana`:

```text
Mẫu "ana"

Suffix tree DFS theo thứ tự nhãn: 3, 1
Suffix array SA[1:3]:           3, 1
Kết quả theo vị trí văn bản:   [1, 3]
```

Nếu API yêu cầu vị trí tăng dần, có thể thêm:

\[
O(occ\log(occ+1))
\]

phép so sánh vị trí để sắp `occ` chỉ số.

Có thể thiết kế metadata khác để trả theo thứ tự vị trí nhanh hơn, nhưng điều đó cần chi phí bộ nhớ/tiền xử lý bổ sung. **Không được tuyên bố rằng suffix tree luôn trả vị trí tăng dần chỉ nhờ DFS.**

### 9.4. Cận dưới do đầu ra

Nếu phải trả `occ` số nguyên, riêng việc xuất chúng đã có cận dưới:

\[
\Omega(occ)
\]

đơn vị thao tác. Một cấu trúc dữ liệu không thể trả hàng triệu vị trí trong O(1) thời gian chỉ vì phần tìm kiếm locus hoặc biên mất O(m).

### 9.5. Truy vấn top-k vị trí nhỏ nhất

Muốn lấy **k vị trí xuất hiện nhỏ nhất** khác với “k lá đầu tiên của DFS” hoặc “k phần tử đầu của SA”. Cả hai chỉ mục cần một kế hoạch bổ sung:

- Duyệt tất cả và chọn/sắp.
- Lưu `min_suffix_start` hoặc cấu trúc RMQ theo vị trí.
- Dùng cấu trúc **range selection** hoặc một chỉ mục phụ nếu truy vấn rất thường xuyên.

Vì thế cần xác định chính xác **thứ tự và tiêu chí của top-k** trước khi so sánh hiệu năng.

## 10. Số nút và cạnh của suffix tree

Cho `n≥1`, chuỗi `T=s+$` có:

\[
L=n+1
\]

hậu tố, mỗi hậu tố kết thúc tại một lá riêng.

Với một suffix tree nén chuẩn, mọi nút trong đều có ít nhất hai con. Nếu `I` là số nút trong và `E` là số cạnh:

\[
E=(I+L)-1.
\]

Vì mỗi nút trong có ít nhất hai con:

\[
E\ge2I.
\]

Do đó:

\[
I\le L-1=n.
\]

Suy ra:

\[
V=I+L\le2n+1,
\qquad E=V-1\le2n.
\]

### 10.1. Ý nghĩa của chặn

Số **nút và cạnh** là O(n), dù tổng độ dài của mọi hậu tố là:

\[
(n+1)+(n)+\cdots+1
=\frac{(n+1)(n+2)}2
=\Theta(n^2).
\]

Cây nén chỉ giữ các điểm phân nhánh và lá. Các đoạn một con dài được **gộp thành nhãn cạnh**, và nhãn được giữ bằng chỉ số `start,end` trong chuỗi `T`.

### 10.2. Trường hợp văn bản rỗng

Nếu `s=""`, `T="$"`. Một cài đặt có thể giữ gốc và một cạnh `"$"` tới một lá: 2 nút, 1 cạnh. Trường hợp đặc biệt này không thỏa công thức `V≤2n+1=1` vì gốc chỉ có một con.

Chặn chính xác theo bài dùng cho `n≥1`; tổng quát ta vẫn có:

\[
V=O(n+1),\qquad E=O(n+1).
\]

### 10.3. Không được nhầm với suffix trie không nén

Nếu mỗi cạnh lưu một ký hiệu và giữ mọi nút không phân nhánh, số nút có thể tăng theo tổng độ dài các hậu tố, tức O(n²).

Lợi ích tuyến tính của suffix tree phụ thuộc **cả nén đường** và **đại diện nhãn cạnh phù hợp**.

## 11. Bộ nhớ của suffix array, LCP và rank

Một suffix array của `s` có đúng `n` chỉ số:

```text
SA = [position_0, position_1, ..., position_(n-1)]
```

Trong mô hình word-RAM, mỗi chỉ số từ 0 tới n−1 chiếm O(1) từ máy nếu từ máy đủ lớn để đánh địa chỉ. Vì thế:

\[
M_{\mathrm{SA}}=\Theta(n)
\]

từ máy, ngoài văn bản gốc.

Nếu cần `LCP` và `rank`:

\[
M_{\mathrm{SA+LCP+rank}}=\Theta(n)
\]

từ máy, với các hằng số lớn hơn `SA` thuần.

### 11.1. Ví dụ đếm byte trên mảng phẳng 64 bit

Giả sử `n=100\,000` và mỗi chỉ số được lưu bằng **số nguyên 64 bit trong một mảng phẳng**:

| Mục | Số ô 64 bit | Byte lý thuyết |
| --- | ---: | ---: |
| `SA` | 100.000 | 800.000 |
| `LCP` | 100.000 | 800.000 |
| `rank` | 100.000 | 800.000 |
| **Ba mảng** | **300.000** | **2.400.000** |

Chưa tính văn bản, header mảng, bộ nhớ làm việc khi xây, allocator hoặc chỉ mục phụ.

**Quan trọng:** Python `list[int]` không phải một mảng `uint64` phẳng. Danh sách giữ tham chiếu tới các đối tượng `int`, nên số byte thực có thể lớn hơn nhiều. Bảng trên minh họa **mô hình mảng số nguyên cố định**, không phải kết quả đo Python.

### 11.2. LCP có phải luôn cần không?

Không. Nếu chỉ cần tìm mẫu bằng binary search thông thường và liệt kê khoảng vị trí, có thể giữ **SA đơn thuần**.

`LCP` hữu ích khi cần:

- Đếm chuỗi con phân biệt.
- Tìm chuỗi con lặp dài nhất.
- Hỏi tiền tố chung giữa hai hậu tố.
- Tăng tốc một số thuật toán tìm hoặc xử lý khoảng hậu tố.

`rank` chủ yếu cần cho xây LCP, truy vấn theo vị trí hậu tố và các thuật toán phụ. Nếu không có truy vấn cần tới nó, có thể không giữ rank sau tiền xử lý.

### 11.3. Mảng LCP không làm mọi truy vấn O(1)

`LCP` chứa thông tin giữa **cặp hậu tố kề nhau**. Muốn hỏi LCP của hai hậu tố bất kỳ, còn cần thao tác **min trên một đoạn LCP** hoặc một cấu trúc RMQ được tiền xử lý.

Một sparse table đơn giản cho RMQ dùng O(n log n) ô nhớ, không còn giới hạn đúng `3n` ô của ba mảng cơ bản; tồn tại phương pháp RMQ tuyến tính bộ nhớ trong những mô hình thích hợp.

## 12. Tại sao suffix tree thường tốn RAM hơn SA?

Cả hai có chặn O(n) từ máy, nhưng **hằng số** và bố trí bộ nhớ khác nhau.

### 12.1. Những đối tượng cần có trong cây

Một cài đặt suffix tree theo nút và cạnh thường giữ:

- Nút trong và lá.
- Mỗi nút có bảng nhánh (dictionary, mảng, map hoặc cấu trúc khác).
- Mỗi cạnh có `start`, `end`, tham chiếu nút con.
- Lá có chỉ số bắt đầu hậu tố.
- Metadata tùy chọn: `leaf_count`, `suffix_link`, độ sâu chuỗi, vị trí tối thiểu, v.v.
- Overhead đối tượng, cấp phát và tham chiếu.

Ngay cả khi số nút ≤`2n+1`, một nút trong có thể đòi nhiều byte hơn **một ô số nguyên** của SA.

### 12.2. Bố trí bộ nhớ và locality

SA nằm trong các mảng liên tục, thuận lợi cho:

- Truy cập tuần tự.
- Nạp các ô chỉ số gần nhau vào cache.
- Serialize/deserialize đơn giản.
- Dùng kiểu số nguyên có độ rộng cố định, thậm chí nén delta tùy workload.

Suffix tree đi qua nhiều đối tượng liên kết, có thể phát sinh:

- Cache miss khi nhảy giữa các nút ở vùng nhớ khác nhau.
- Overhead của dictionary/map nhỏ ở rất nhiều nút.
- Phân mảnh bộ nhớ và áp lực bộ cấp phát.

Vì vậy SA thường có lợi về **mật độ lưu trữ**, dù một truy vấn SA cơ bản có thể cần nhiều phép so mẫu hơn.

### 12.3. Không gán số byte cố định cho suffix tree

Không thể suy “mỗi nút cây đúng 24 byte” chỉ từ việc có ba con trỏ, vì:

- Nút có thể là đối tượng với header.
- Dictionary có capacity, bảng băm và metadata.
- Chỉ số có thể là đối tượng số nguyên.
- Bộ nhớ allocator thường cấp phát theo block, có padding.
- Có/không suffix link hoặc leaf count làm thay đổi cấu trúc.

Cần đo **đúng triển khai thực tế** bằng công cụ đo bộ nhớ phù hợp, không dùng công thức Big-O để suy thẳng ra MB.

### 12.4. Cây cũng có thể được lưu bằng mảng phẳng

Một suffix tree có thể được mã hóa bằng mảng nút/cạnh liên tục hoặc cấu trúc succinct, giảm pointer overhead và cải thiện locality.

Do đó phát biểu “cây luôn tốn nhiều RAM hơn SA” là quá tuyệt đối. Chính xác hơn: **triển khai cây liên kết thông thường có xu hướng overhead lớn hơn mảng chỉ số phẳng**, nhưng cần so cùng chức năng và cùng runtime.

## 13. Bộ nhớ giữ lại khác bộ nhớ đỉnh khi xây

Một hệ thống có thể xây chỉ mục rồi phục vụ truy vấn trong thời gian dài. Cần đo ít nhất hai đại lượng:

1. **Retained memory:** bộ nhớ chỉ mục còn giữ sau khi xây xong và bỏ biến tạm.
2. **Peak build memory:** mức bộ nhớ tối đa đã dùng **trong quá trình xây**.

### 13.1. Prefix doubling có nhiều mảng tạm

Một cách xây SA phổ biến dùng:

- `SA`.
- `rank` hiện tại.
- `new_rank`.
- Khóa cặp hạng để sắp.
- Bộ nhớ làm việc của sort.

Vì vậy đỉnh RAM trong lúc xây **lớn hơn kích thước SA cuối cùng**.

Sau khi xây, nếu ứng dụng chỉ cần contains/count cơ bản, có thể bỏ `rank` và `LCP` không cần thiết để giảm retained memory.

### 13.2. Thuật toán xây suffix tree cũng cần metadata tạm

Thuật toán Ukkonen hoặc các phương pháp tuyến tính khác có thể cần:

- Active point.
- Suffix link.
- Vị trí mở rộng.
- Đầu cạnh lá động.
- Bảng nhánh, nút trong và lá.

Các mục này có thể tồn tại trong và sau thời điểm xây, tùy thiết kế. Không nên so `SA` đã giải phóng toàn bộ biến tạm với suffix tree vẫn giữ cả cấu trúc debug/validator.

### 13.3. Văn bản gốc có được tính không?

Cần chọn một trong hai thước đo:

- **Index-only:** không tính bản văn gốc nếu cả hai cùng dùng chung.
- **Total service memory:** tính cả văn bản gốc, chỉ mục, metadata, cache và kết quả đang giữ.

Nhưng hãy giữ cách tính **nhất quán**. Nếu cây giữ `T=s+$` là một chuỗi mới, còn SA dùng trực tiếp `s`, phép so cũng cần nêu chi phí bản sao/terminator đó.

### 13.4. Đỉnh bộ nhớ do kết quả truy vấn

Nếu một truy vấn trả một triệu vị trí, danh sách kết quả có thể tốn RAM đáng kể ở **cả hai chỉ mục**. Nên đo riêng bộ nhớ phục vụ truy vấn hoặc dùng iterator/streaming nếu API cho phép.

## 14. Thời gian xây chỉ mục: phải gắn với thuật toán cụ thể

Không có một con số thời gian xây duy nhất cho “suffix tree” hay “suffix array”.

### 14.1. Cây hậu tố chèn lần lượt từng hậu tố

Một cài đặt dễ hiểu thường làm:

```text
T = s + "$"

for i from 0 to n:
    insert_suffix(T, i)  # đi từ gốc, so từng nhãn cạnh
```

Mỗi lần chèn có thể đọc O(n−i) ký hiệu. Tổng:

\[
\sum_{i=0}^{n}(n+1-i)
=\Theta(n^2).
\]

Ngay cả nếu **mỗi cạnh chỉ lưu chỉ số đoạn** và cây sau cùng có O(n) nút, **cách xây đơn giản vẫn có thể O(n²) thời gian**.

### 14.2. Cây hậu tố với thuật toán chuyên dụng

Các họ thuật toán Weiner, McCreight và Ukkonen có thể xây suffix tree trong **O(n)** thời gian với các giả định thích hợp về bảng ký hiệu, truy cập nhánh và phép xử lý đoạn.

Chúng tận dụng quan hệ giữa những hậu tố và tránh lặp lại việc so ký hiệu từ đầu bằng các kỹ thuật như:

- **Suffix link**.
- **Active point**.
- **Skip/count trick**.
- **Đầu cạnh lá động** trong một số phương pháp online.

Không được gọi vòng lặp `insert_suffix` đơn giản là thuật toán Ukkonen nếu không có cơ chế cần thiết.

### 14.3. Mảng hậu tố xây bằng prefix doubling

Một thuật toán minh họa dùng:

\[
key_k(i)=(rank_k[i],rank_k[i+k]),
\]

với `-1` khi nửa thứ hai đã hết. Sau mỗi vòng sort theo cặp hạng, độ dài đoạn được phân biệt tăng gấp đôi.

Nếu dùng sort so sánh thông thường:

- Mỗi vòng O(n log n).
- Có O(log(n+1)) vòng.

Suy ra:

\[
T_{\mathrm{SA,doubling}}=O(n\log^2(n+1)).
\]

Nếu mỗi vòng sắp cặp hạng bằng **counting/radix sort** phù hợp, có thể đạt O(n log n).

### 14.4. Thuật toán xây SA tuyến tính

Các họ SA-IS, DC3/skew và các thuật toán liên quan có thể xây suffix array trong O(n) thời gian dưới các giả định về bảng chữ cái/định danh ký hiệu và mô hình tính toán.

Điểm cần nhớ:

> **Suffix tree có thuật toán xây O(n), suffix array cũng có thuật toán xây O(n)**; nhưng không có nghĩa mọi chương trình minh họa hai cấu trúc đều đạt các chặn ấy.

### 14.5. LCP sau SA

Thuật toán **Kasai** xây mảng `LCP` trong O(n) thời gian sau khi đã có `SA`, bằng cách duyệt vị trí văn bản và tái sử dụng độ dài tiền tố chung đã biết.

Vậy nếu bản xây SA tốn O(n log² n), việc thêm Kasai O(n) **không làm thay đổi bậc tổng thời gian xây**.

## 15. Bảng độ phức tạp so sánh theo chức năng

Giả định:

- `n≥1` là số ký hiệu văn bản.
- `m≥1` là số ký hiệu mẫu.
- `occ` là số kết quả.
- Đọc/so một ký hiệu tốn O(1).
- Cây chọn cạnh theo ký hiệu đầu với O(1) **kỳ vọng**.
- SA dùng **binary search cơ bản**, so từ đầu mỗi lần, chưa dùng tăng tốc LCP.
- Các chỉ mục **đã được xây hoàn chỉnh**.

| Chức năng | Cây hậu tố nén | Mảng hậu tố cơ bản |
| --- | --- | --- |
| Tìm có mẫu không? | O(m) kỳ vọng | O(m log n) |
| Đếm số lần | O(m) với `leaf_count` | O(m log n) để tìm hai biên |
| Liệt kê `occ` vị trí, chưa sắp theo vị trí | O(m+occ) kỳ vọng | O(m log n+occ) |
| Trả vị trí tăng | Thêm O(occ log(occ+1)) nếu sort | Thêm O(occ log(occ+1)) nếu sort |
| LCP của hai hậu tố bất kỳ | Qua LCA của lá, nếu có cấu trúc hỗ trợ | Qua RMQ trên LCP nếu có cấu trúc hỗ trợ |
| Số chuỗi con phân biệt | O(n) một lượt theo cạnh | O(n) từ SA/LCP |
| Chuỗi con lặp dài nhất | O(n) duyệt nút trong | O(n) lấy max LCP |
| Xây bằng cách minh họa đơn giản | O(n²) có thể xảy ra | O(n log² n) với doubling + sort |
| Xây bằng thuật toán tối ưu thích hợp | Có thể O(n) | Có thể O(n) |
| Nút/cạnh hoặc chỉ số lưu | O(n) nút/cạnh | O(n) ô chỉ số |

Các biểu thức O(m log n) được hiểu là O((m+1)log(n+1)) nếu cần bao quát mọi biên nhỏ. Mẫu rỗng có quy ước riêng.

### 15.1. Khi cần xác suất/kỳ vọng

Nếu cây lưu cạnh bằng Hash Map, lựa chọn cạnh có thời gian **O(1) kỳ vọng** với giả định băm và tải phù hợp. Không nên khẳng định mọi thao tác Hash Map luôn O(1) trong trường hợp xấu.

Nếu dùng bảng nhánh kích thước cố định của một bảng chữ cái **nhỏ, cố định**, chọn nhánh có thể O(1) trường hợp xấu nhưng tốn thêm nhiều ô trống.

### 15.2. Khi SA có tăng tốc tìm bằng LCP

Với thuật toán binary search khai thác tiền tố chung và thông tin LCP/RMQ thích hợp, có thể cải thiện chặn của tìm mẫu tới **O(m+log n)** trong mô hình so ký hiệu O(1).

Tuy nhiên, việc thêm mỗi mảng LCP mà **không thay đổi comparator/binary search** không tạo ra cải thiện tự động. Phải ghi rõ biến thể triển khai trong benchmark.

## 16. LCP của hai hậu tố bất kỳ: LCA so với RMQ

Một phép truy vấn khác với tìm mẫu là:

> Hai hậu tố `s[i:]` và `s[j:]` giống nhau tối đa bao nhiêu ký hiệu đầu?

### 16.1. Với suffix tree

Để hỏi nhanh, lưu ánh xạ từ vị trí bắt đầu hậu tố tới lá tương ứng. Hai lá đại diện `i` và `j` có **tổ tiên chung thấp nhất** (*Lowest Common Ancestor*, LCA).

Độ sâu ký hiệu từ gốc tới LCA chính là:

\[
lcp(s[i:],s[j:])
=\operatorname{stringDepth}(LCA(leaf_i,leaf_j)).
\]

`stringDepth` là tổng độ dài nhãn các cạnh trên đường, **không phải số cạnh**.

Với cây tĩnh và tiền xử lý LCA thích hợp, có thể trả truy vấn rất nhanh, tới O(1) ở những mô hình và thuật toán LCA cho phép. Nếu chỉ đi ngược con trỏ cha để tìm LCA, thời gian có thể phụ thuộc độ sâu cây, không phải O(1).

### 16.2. Với suffix array

Gọi `a=rank[i]`, `b=rank[j]` và `a<b`. Theo quy ước `LCP[r]` so với hạng trước:

\[
lcp(s[i:],s[j:])
=\min_{a<r\le b}LCP[r].
\]

Nếu `i=j`, kết quả là `n-i`.

Đây là truy vấn **RMQ (Range Minimum Query)** trên `LCP`:

- Dùng `min` trực tiếp trên đoạn: O(b−a).
- Sparse table: O(n log n) tiền xử lý/ô, O(1) phép hỏi.
- Những cấu trúc RMQ tối ưu hơn có thể đạt O(n) từ máy và O(1) phép hỏi với giả định phù hợp.

### 16.3. Vết trên `banana`

`SA=[5,3,1,0,4,2]`, `rank[1]=2` và `rank[3]=1`.

\[
lcp(s[1:],s[3:])=\min(LCP[2])=3.
\]

Quả thật:

```text
s[1:] = anana
s[3:] = ana
        ^^^
```

Cây hậu tố cho cùng kết quả bằng độ sâu ký hiệu của nút `B` biểu diễn `ana`.

### 16.4. Kết luận chức năng

Cả hai có thể trả lời LCP giữa hai hậu tố trong thời gian nhỏ sau tiền xử lý. Cần so **tổng chi phí**:

- Cây: ánh xạ lá, độ sâu ký hiệu, cấu trúc LCA.
- SA: rank, LCP và cấu trúc RMQ.

Đừng so cây đã có LCA tối ưu với SA chỉ dùng `min` tuyến tính mà không nêu rõ khác biệt metadata.

## 17. Đếm số chuỗi con phân biệt bằng hai chỉ mục

Một ứng dụng quan trọng là đếm số **substring liên tiếp khác nhau**, không kể chuỗi rỗng.

### 17.1. Công thức qua mảng hậu tố

Mỗi hậu tố `s[SA[r]:]` dài `n-SA[r]` có từng ấy tiền tố không rỗng.

Nhưng `LCP[r]` tiền tố đầu đã có ở các hậu tố trước theo thứ tự từ điển. Số chuỗi con mới ở hạng `r` là:

\[
(n-SA[r])-LCP[r].
\]

Cộng toàn bộ:

\[
\boxed{
D=\frac{n(n+1)}2-\sum_{r=0}^{n-1}LCP[r].
}
\]

### 17.2. Công thức qua suffix tree

Mỗi vị trí **trên một nhãn cạnh** từ gốc tương ứng một chuỗi con khác nhau, trừ vị trí mà đường đã chứa ký hiệu `$` kỹ thuật.

Nếu `length(e)=end_e-start_e` và `T` chỉ có `$` tại cuối, ta có:

\[
D=\sum_{e\in E}
\left(length(e)-\mathbf1_{end_e=|T|}\right).
\]

Vì mọi cạnh có `end=|T|` chứa ký hiệu `$` ở cuối, ta trừ một đơn vị của cạnh ấy. Các đoạn dọc cạnh còn lại tương ứng những chuỗi con của văn bản gốc.

Công thức này dùng **nhãn cạnh lưu đoạn chỉ số**; không cần dựng chuỗi ứng với từng điểm giữa cạnh.

### 17.3. Kiểm tra với `banana`

Văn bản dài `n=6`. Từ `SA/LCP`:

\[
\frac{6\cdot7}{2}-(0+1+3+0+0+2)
=21-6=15.
\]

Từ cây, cộng độ dài phần nhãn **không có `$`** ở mọi cạnh cũng bằng 15.

Các chuỗi con phân biệt theo độ dài:

| Độ dài | Các chuỗi con phân biệt | Số lượng |
| ---: | --- | ---: |
| 1 | `b, a, n` | 3 |
| 2 | `ba, an, na` | 3 |
| 3 | `ban, ana, nan` | 3 |
| 4 | `bana, anan, nana` | 3 |
| 5 | `banan, anana` | 2 |
| 6 | `banana` | 1 |
| **Tổng** | | **15** |

### 17.4. Đánh đổi

- Với SA+LCP có sẵn, chỉ cần tính `sum(LCP)` một lần O(n).
- Với cây, duyệt tất cả cạnh O(n) và cộng độ dài hiệu dụng.
- Không cấu trúc nào buộc phải **liệt kê mọi chuỗi con phân biệt** — số chuỗi con có thể là Θ(n²), nên xuất toàn bộ vẫn có thể rất lớn.

## 18. Chuỗi con lặp dài nhất

Một chuỗi con `p` được gọi là **lặp** nếu nó xuất hiện ít nhất hai lần tại hai vị trí bắt đầu khác nhau. Trong phần này cho phép các lần xuất hiện **chồng lấn**.

### 18.1. Qua mảng hậu tố

Độ dài chuỗi con lặp dài nhất là:

\[
\max_{r}LCP[r].
\]

Lý do: những hậu tố có chung một tiền tố dài `k` nằm liên tiếp trong thứ tự từ điển. Nếu có hai hậu tố với tiền tố chung dài `k`, có một cặp hậu tố **kề nhau** đạt LCP ít nhất `k`.

Với `banana`, `max(LCP)=3`, nên một kết quả là `ana`.

### 18.2. Qua suffix tree

Một chuỗi con xuất hiện ít nhất hai lần nếu cây con dưới locus có ít nhất hai lá.

Vì vậy có thể tìm nút trong có:

- `leaf_count≥2`.
- `stringDepth` lớn nhất.

Đường nhãn từ gốc tới nút ấy biểu diễn một chuỗi con lặp dài nhất. Cần tránh đưa ký hiệu `$` vào kết quả; nút trong của cây có sentinel duy nhất không cần chứa `$` trong đường.

### 18.3. Vì sao chọn nút trong là đủ?

Nếu một vị trí ở **giữa cạnh** có ít nhất hai lá bên dưới, có thể đi tiếp tới **cuối cạnh** mà tập lá bên dưới vẫn không thay đổi, vì không có điểm phân nhánh giữa nhãn. Do đó vị trí sâu nhất với ít nhất hai lá sẽ ở một **nút phân nhánh**.

### 18.4. Nếu yêu cầu không chồng lấn

Trong `aaaaa`, chuỗi `aaaa` xuất hiện tại 0 và 1 nhưng hai đoạn giao nhau. Dùng `max(LCP)` hoặc nút sâu nhất có hai lá **không đủ** để tìm chuỗi lặp không chồng lấn.

Cần kiểm tra khoảng cách vị trí hoặc duy trì metadata bổ sung. Hai chỉ mục đều phải điều chỉnh thuật toán cho ràng buộc mới.

## 19. Nhiều văn bản: generalized suffix tree và generalized SA

Khi cần tìm **chuỗi con chung giữa nhiều tài liệu**, ta có thể mở rộng cả hai cách.

### 19.1. Cây hậu tố tổng quát

Ghép các văn bản với **ký hiệu phân cách/kết thúc riêng biệt** không xuất hiện trong dữ liệu:

```text
T = s1 + $1 + s2 + $2 + ...
```

Mỗi lá ghi:

- ID văn bản nguồn.
- Vị trí bắt đầu trong văn bản đó.

Để tìm một chuỗi con chung, xét những cây con có lá thuộc nhiều văn bản. Có thể duy trì bitset/tập ID ở mỗi nút sau tiền xử lý.

### 19.2. Generalized suffix array

Tương tự, xây SA cho các hậu tố của chuỗi ghép đã phân cách. Mỗi vị trí bắt đầu hậu tố có **ID văn bản nguồn**; LCP phải được tính/giới hạn đúng tại ranh giới phân cách nếu truy vấn không cho phép vượt tài liệu.

Một chuỗi con chung dài nhất giữa hai văn bản có thể tìm thông qua LCP của những hậu tố phù hợp thuộc **hai nguồn khác nhau**, kết hợp sắp thứ tự và xử lý ranh giới.

### 19.3. Không dùng một sentinel trùng dữ liệu

Nếu ký hiệu kết thúc cũng có trong văn bản thật, một đường hậu tố có thể tiếp tục qua thứ vốn phải là ranh giới. Dữ liệu cần được mã hóa không mơ hồ hoặc dùng ký hiệu ngoài miền dữ liệu.

### 19.4. Bộ nhớ metadata nguồn

Cả cây và mảng cần thêm thông tin ID nguồn/ranh giới. So sánh RAM phải tính cả metadata ấy; không thể so generalized tree với SA của một văn bản duy nhất rồi kết luận về bài toán nhiều văn bản.

## 20. Văn bản thay đổi: chỉ mục tĩnh và cập nhật

Một thay đổi nhỏ trong văn bản có thể ảnh hưởng **rất nhiều hậu tố**.

### 20.1. Suffix array thường là chỉ mục tĩnh

`SA` và `LCP` xác định thứ tự của mọi hậu tố văn bản. Nếu chèn một ký tự vào giữa văn bản:

- Nhiều vị trí bắt đầu hậu tố phía sau thay đổi.
- Thứ tự từ điển của nhiều hậu tố có thể đổi.
- Các giá trị LCP có thể phải tính lại.

Một giải pháp đơn giản là **xây lại chỉ mục**. Có những kỹ thuật dynamic suffix array nhưng phức tạp hơn bản mảng tĩnh.

### 20.2. Suffix tree có thể xây online theo kiểu nối thêm

Một số thuật toán như Ukkonen xử lý **nối thêm ký tự vào cuối văn bản** trong quá trình xây, thông qua active point, suffix links và đầu cạnh lá động.

Tuy nhiên, điều đó **không** có nghĩa suffix tree hỗ trợ chèn/xóa một đoạn ở vị trí bất kỳ trong O(1). Cập nhật văn bản trong giữa hoặc sửa ký tự vẫn là vấn đề phức tạp.

### 20.3. Khoảng chỉ số và nguồn bất biến

Cây lưu `[start,end)` trỏ vào `T`; SA giữ vị trí trong `s`. Nếu nguồn bị thay đổi mà không cập nhật chỉ mục, **cả hai đều có thể trả lời sai**.

Một thiết kế thực tế có thể:

- Đóng băng snapshot văn bản để lập chỉ mục.
- Gắn phiên bản văn bản với chỉ mục.
- Xây lại định kỳ hoặc khi đạt ngưỡng số sửa.
- Dùng cấu trúc động chuyên dụng khi cập nhật là yêu cầu cốt lõi.

## 21. Cài đặt so sánh: một API cho hai chỉ mục

Ta xây hai lớp minh họa:

```text
SuffixTreeIndex
SuffixArrayIndex

Cùng API:
    contains(pattern)      -> bool
    count(pattern)         -> int
    occurrences(pattern)   -> list[int] tăng dần
    distinct_count()       -> int
```

**Giới hạn của mã minh họa:**

- Văn bản là `str` Python.
- Chỉ mục cây sử dụng `"$"` làm sentinel và từ chối văn bản/mẫu chứa ký hiệu đó; chỉ mục mảng không cần sentinel.
- Cây xây bằng **chèn từng hậu tố O(n²)**, nhằm giải thích biểu diễn đoạn chỉ số; **không phải Ukkonen**.
- SA xây bằng **prefix doubling + sort O(n log² n)**; `LCP` tính bằng Kasai O(n).
- Những điều kiện về thời gian và bộ nhớ phải gắn với **đúng hai chương trình này**, không tự suy từ các thuật toán tối ưu khác.

### 21.1. Nút/cạnh suffix tree

```python
class _TreeEdge:
    __slots__ = ("start", "end", "child")

    def __init__(self, start, end, child):
        self.start = start
        self.end = end
        self.child = child


class _TreeNode:
    __slots__ = ("edges", "suffix_start", "leaf_count")

    def __init__(self, suffix_start=None):
        self.edges = {}     # first_char -> _TreeEdge
        self.suffix_start = suffix_start
        self.leaf_count = 0
```

### 21.2. Khởi tạo và xây suffix tree bằng đoạn tham chiếu

```python
class SuffixTreeIndex:
    def __init__(self, text):
        if not isinstance(text, str):
            raise TypeError("text phải là str")
        if "$" in text:
            raise ValueError("'$' dành làm ký hiệu kết thúc")

        self.original = text
        self.text = text + "$"
        self.n = len(text)
        self.root = _TreeNode()

        for i in range(len(self.text)):
            self._insert_suffix(i)

        self._count_leaves()

    @staticmethod
    def _check_pattern(pattern):
        if not isinstance(pattern, str):
            raise TypeError("pattern phải là str")
        if "$" in pattern:
            raise ValueError("pattern không được chứa '$'")

    def _insert_suffix(self, suffix_start):
        source = self.text
        total = len(source)
        node = self.root
        pos = suffix_start

        while pos < total:
            first = source[pos]
            edge = node.edges.get(first)

            if edge is None:
                leaf = _TreeNode(suffix_start=suffix_start)
                node.edges[first] = _TreeEdge(
                    pos, total, leaf
                )
                return

            common = 0
            width = edge.end - edge.start

            while (
                common < width
                and pos + common < total
                and source[edge.start + common]
                    == source[pos + common]
            ):
                common += 1

            if common == width:
                pos += common
                node = edge.child
                continue

            # Có chung ký hiệu đầu; các hậu tố của
            # T với sentinel duy nhất không là
            # tiền tố của nhau.
            assert common > 0
            assert pos + common < total

            old_start = edge.start
            old_end = edge.end
            old_child = edge.child

            middle = _TreeNode()

            node.edges[first] = _TreeEdge(
                old_start,
                old_start + common,
                middle,
            )

            old_tail = old_start + common
            middle.edges[source[old_tail]] = _TreeEdge(
                old_tail, old_end, old_child
            )

            new_tail = pos + common
            leaf = _TreeNode(suffix_start=suffix_start)
            middle.edges[source[new_tail]] = _TreeEdge(
                new_tail, total, leaf
            )
            return

        raise AssertionError("hậu tố đã trùng")
```

**Tại sao không cần `source[pos:]`?** Vòng lặp chỉ lưu `pos`, truy cập trực tiếp ký hiệu của `source`. Cạnh mới chỉ chứa `start,end`; split cạnh chỉ thay các chỉ số và nút liên kết, không tạo bản sao nhãn chuỗi.

### 21.3. Đếm lá và định vị mẫu trong cây

Thêm các phương thức vào cùng lớp `SuffixTreeIndex`:

```python
    def _count_leaves(self):
        stack = [(self.root, False)]

        while stack:
            node, done = stack.pop()

            if not done:
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

    def _locus(self, pattern):
        node = self.root
        pos = 0

        while pos < len(pattern):
            edge = node.edges.get(pattern[pos])
            if edge is None:
                return None

            common = 0
            width = edge.end - edge.start

            while (
                common < width
                and pos + common < len(pattern)
                and self.text[edge.start + common]
                    == pattern[pos + common]
            ):
                common += 1

            if pos + common == len(pattern):
                # Mẫu có thể hết giữa nhãn cạnh.
                return edge.child

            if common < width:
                return None

            pos += common
            node = edge.child

        return node

    def contains(self, pattern):
        self._check_pattern(pattern)

        if pattern == "":
            return True
        return self._locus(pattern) is not None

    def count(self, pattern):
        self._check_pattern(pattern)

        if pattern == "":
            return self.n + 1

        node = self._locus(pattern)
        return 0 if node is None else node.leaf_count

    def occurrences(self, pattern):
        self._check_pattern(pattern)

        if pattern == "":
            return list(range(self.n + 1))

        node = self._locus(pattern)
        if node is None:
            return []

        result = []
        stack = [node]

        while stack:
            current = stack.pop()

            if current.suffix_start is not None:
                result.append(current.suffix_start)
            else:
                for edge in current.edges.values():
                    stack.append(edge.child)

        return sorted(result)
```

### 21.4. Đếm chuỗi con phân biệt từ các cạnh

```python
    def distinct_count(self):
        """Số substring phân biệt không rỗng."""
        result = 0
        total = len(self.text)
        stack = [self.root]

        while stack:
            node = stack.pop()

            for edge in node.edges.values():
                visible = edge.end - edge.start

                # '$' duy nhất ở cuối T, không phải
                # ký hiệu của substring trong s.
                if edge.end == total:
                    visible -= 1

                result += visible
                stack.append(edge.child)

        return result
```

Vì các nhãn cạnh chỉ trỏ vào `T` và `$` duy nhất ở cuối, trừ 1 ở cạnh có `end==len(T)` là cách đếm số ký hiệu “thật” trên đoạn nhãn. Trong cây đầy đủ, các cạnh như vậy kết thúc bằng sentinel.

## 22. Cài đặt suffix array + Kasai và truy vấn cùng API

### 22.1. Xây SA bằng prefix doubling

```python
def make_suffix_array(text):
    n = len(text)
    if n == 0:
        return []

    sa = list(range(n))
    rank = [ord(ch) for ch in text]
    gap = 1

    while True:
        sa.sort(
            key=lambda i: (
                rank[i],
                rank[i + gap] if i + gap < n else -1,
            )
        )

        updated = [0] * n

        for r in range(1, n):
            previous = sa[r - 1]
            current = sa[r]

            pair_previous = (
                rank[previous],
                rank[previous + gap]
                if previous + gap < n else -1,
            )
            pair_current = (
                rank[current],
                rank[current + gap]
                if current + gap < n else -1,
            )

            updated[current] = (
                updated[previous]
                + int(pair_previous != pair_current)
            )

        rank = updated

        if rank[sa[-1]] == n - 1:
            return sa

        gap *= 2
```

Nếu đoạn thứ hai của hậu tố vượt quá cuối văn bản, dùng hạng `-1`, nhỏ hơn mọi hạng hợp lệ. Điều này bảo đảm hậu tố **ngắn hơn** đứng trước khi nó là tiền tố của hậu tố dài.

### 22.2. Xây LCP bằng Kasai

```python
def make_lcp(text, sa):
    n = len(text)
    rank = [0] * n

    for r, start in enumerate(sa):
        rank[start] = r

    lcp = [0] * n
    h = 0

    for i in range(n):
        r = rank[i]
        if r == 0:
            h = 0
            continue

        j = sa[r - 1]

        while (
            i + h < n
            and j + h < n
            and text[i + h] == text[j + h]
        ):
            h += 1

        lcp[r] = h

        if h > 0:
            h -= 1

    return lcp, rank
```

`rank` là mảng nghịch đảo của `SA` cuối cùng. `h` tái sử dụng phần tiền tố chung từ lượt trước khi duyệt các vị trí văn bản, giúp Kasai đạt O(n) thời gian sau khi đã có SA.

### 22.3. Lớp chỉ mục mảng

```python
class SuffixArrayIndex:
    def __init__(self, text):
        if not isinstance(text, str):
            raise TypeError("text phải là str")

        self.text = text
        self.sa = make_suffix_array(text)
        self.lcp, self.rank = make_lcp(text, self.sa)

    @staticmethod
    def _check_pattern(pattern):
        if not isinstance(pattern, str):
            raise TypeError("pattern phải là str")

    def _compare_at(self, start, pattern):
        """-1: suffix nhỏ hơn; 0: khớp prefix; +1: lớn hơn."""
        text = self.text
        n = len(text)
        j = 0

        while j < len(pattern) and start + j < n:
            left = text[start + j]
            right = pattern[j]

            if left < right:
                return -1
            if left > right:
                return 1

            j += 1

        if j == len(pattern):
            return 0
        return -1     # Hậu tố hết trước mẫu.

    def _range(self, pattern):
        size = len(self.sa)
        low, high = 0, size

        # Biên đầu: cmp >= 0.
        while low < high:
            mid = (low + high) // 2
            if self._compare_at(self.sa[mid], pattern) < 0:
                low = mid + 1
            else:
                high = mid

        left = low
        low, high = left, size

        # Biên sau: cmp > 0.
        while low < high:
            mid = (low + high) // 2
            if self._compare_at(self.sa[mid], pattern) <= 0:
                low = mid + 1
            else:
                high = mid

        return left, low

    def contains(self, pattern):
        self._check_pattern(pattern)

        if pattern == "":
            return True

        left, right = self._range(pattern)
        return left < right

    def count(self, pattern):
        self._check_pattern(pattern)

        if pattern == "":
            return len(self.text) + 1

        left, right = self._range(pattern)
        return right - left

    def occurrences(self, pattern):
        self._check_pattern(pattern)

        if pattern == "":
            return list(range(len(self.text) + 1))

        left, right = self._range(pattern)
        return sorted(self.sa[left:right])

    def distinct_count(self):
        n = len(self.text)
        return n * (n + 1) // 2 - sum(self.lcp)

    def longest_repeated(self):
        """Trả một chuỗi con lặp dài nhất, hoặc ''."""
        if not self.lcp:
            return ""

        length = max(self.lcp)
        if length == 0:
            return ""

        rank_of_pair = self.lcp.index(length)
        start = self.sa[rank_of_pair]
        return self.text[start:start + length]
```

Bản này dùng O(n log² n) thời gian xây SA, O(n) cho Kasai và O(m log n) cho tìm hai biên theo mô hình đã nêu. Dù có lưu `LCP`, phương thức `_range` **chưa sử dụng thông tin LCP để tăng tốc binary search**.

## 23. Kiểm tra hai chỉ mục trên cùng tập dữ liệu

Hai lớp ở mục 21–22 có cùng nghĩa của `contains`, `count`, `occurrences` và `distinct_count`. Ta dùng một phép quét trực tiếp làm **mô hình tham chiếu**.

### 23.1. Mô hình tham chiếu

```python
def scan_occurrences(text, pattern):
    if pattern == "":
        return list(range(len(text) + 1))

    m = len(pattern)

    return [
        i
        for i in range(len(text) - m + 1)
        if text[i:i + m] == pattern
    ]


def scan_distinct(text):
    n = len(text)

    return len({
        text[i:j]
        for i in range(n)
        for j in range(i + 1, n + 1)
    })
```

Hai hàm quét được dùng để **kiểm thử trên văn bản nhỏ**, không phải giải pháp phục vụ truy vấn quy mô lớn. `scan_distinct` có thể giữ rất nhiều chuỗi tạm trong một Set.

### 23.2. Cùng các mẫu thử

```python
def check_both_indexes(text, patterns):
    tree = SuffixTreeIndex(text)
    array = SuffixArrayIndex(text)

    assert tree.distinct_count() == array.distinct_count()
    assert tree.distinct_count() == scan_distinct(text)

    for pattern in patterns:
        expected = scan_occurrences(text, pattern)

        assert tree.contains(pattern) == bool(expected)
        assert array.contains(pattern) == bool(expected)

        assert tree.count(pattern) == len(expected)
        assert array.count(pattern) == len(expected)

        assert tree.occurrences(pattern) == expected
        assert array.occurrences(pattern) == expected


for text in [
    "", "a", "banana", "aaaaa",
    "abababa", "mississippi", "bàn", "🍎a🍎",
]:
    check_both_indexes(
        text,
        [
            "", "a", "aa", "ana", "an", "na",
            "b", "ban", "abab", "issi",
            "xyz", text,
        ],
    )
```

Các phép thử có cả:

- Văn bản rỗng.
- Một ký hiệu.
- Ký hiệu lặp nhiều.
- Những lần xuất hiện chồng lấn.
- Mẫu là tiền tố/hậu tố của văn bản.
- Mẫu không xuất hiện.
- Unicode code point nhiều byte UTF-8.

### 23.3. Kiểm tra mẫu `banana`

```python
tree = SuffixTreeIndex("banana")
array = SuffixArrayIndex("banana")

assert array.sa == [5, 3, 1, 0, 4, 2]
assert array.lcp == [0, 1, 3, 0, 0, 2]

for index in (tree, array):
    assert index.contains("ana")
    assert index.occurrences("ana") == [1, 3]
    assert index.occurrences("an") == [1, 3]
    assert index.occurrences("na") == [2, 4]
    assert index.occurrences("ban") == [0]
    assert index.occurrences("x") == []
    assert index.occurrences("") == list(range(7))
    assert index.count("") == 7
    assert index.distinct_count() == 15

assert tree.root.leaf_count == 7
assert array.longest_repeated() == "ana"
```

### 23.4. Lưu ý về tính công bằng của hai miền ký tự

`SuffixTreeIndex` dùng `"$"` làm ký hiệu kết thúc kỹ thuật và từ chối nó trong đầu vào; `SuffixArrayIndex` không cần điều kiện này. Vì vậy các kiểm thử so sánh phải dùng văn bản/mẫu **không chứa `"$"`**.

Trong ứng dụng thực tế muốn hỗ trợ mọi ký tự, cần thay sentinel bằng một ký hiệu ngoài miền dữ liệu hoặc một encoding không mơ hồ. Không được lấy kết quả lỗi sentinel ở một bên để kết luận bên kia có thuật toán tìm mẫu tốt hơn.

## 24. Đo RAM và tốc độ thế nào cho đáng tin?

Độ phức tạp lý thuyết chỉ cho biết xu hướng theo `n,m,occ`. Để chọn công nghệ, cần đo **trên workload đại diện** và kiểm soát nguồn nhiễu.

### 24.1. Đo cả phần xây và phần truy vấn

Tối thiểu nên ghi:

| Nhóm chỉ số | Mục cần đo |
| --- | --- |
| Xây | Thời gian dựng chỉ mục, đỉnh bộ nhớ khi dựng |
| Sau xây | RAM chỉ mục còn giữ, số nút/cạnh hoặc ô mảng |
| Contains | Độ trễ mẫu có/không có, độ dài m |
| Count | Độ trễ đếm mẫu ít/nhiều kết quả |
| Occurrences | Độ trễ và số lượng kết quả `occ` |
| Bộ nhớ truy vấn | Bộ nhớ của danh sách kết quả, phần sort |
| Đặc điểm dữ liệu | Độ dài văn bản, kích thước bảng chữ cái, mức lặp tiền tố |

Nếu mục tiêu là **đếm** chứ không trả mọi vị trí, không nên lấy thời gian `occurrences` có sort rồi gọi đó là chi phí count.

### 24.2. Các phân bố dữ liệu cần thử

Nên dùng nhiều nhóm văn bản:

1. **Ký hiệu lặp mạnh** như `aaaa...`: nhiều hậu tố có tiền tố chung dài.
2. **Văn bản tự nhiên**: phân bố ký tự, từ và chuỗi lặp không đồng đều.
3. **Ký hiệu gần ngẫu nhiên**: ít tiền tố chung dài.
4. **Bảng chữ cái nhỏ** so với bảng chữ cái lớn.
5. **Nhiều đoạn giống nhau** hoặc tài liệu template.
6. **Unicode gồm ký tự nhiều byte và dấu kết hợp** nếu sản phẩm xử lý văn bản thực.

Kết quả trên duy nhất `banana` hoặc một chuỗi ngẫu nhiên ngắn không đại diện cho cả hệ thống.

### 24.3. Tập truy vấn cần cân bằng

Bộ truy vấn nên bao gồm:

- Mẫu độ dài 1, 2, 4, 8, 16, v.v.
- Mẫu chắc chắn tồn tại.
- Mẫu chắc chắn không tồn tại.
- Mẫu có `occ` rất lớn.
- Mẫu có đúng một lần xuất hiện.
- Mẫu nằm giữa đoạn nhãn dài của suffix tree.
- Mẫu rỗng nếu API hỗ trợ.
- Nhiều lần lặp lại cùng một mẫu để quan sát cache.

Lưu `m` và `occ` cùng độ trễ; nếu không, rất khó giải thích tại sao hai truy vấn có cùng `m` nhưng thời gian khác nhau.

### 24.4. Minh họa đo bằng Python

Đoạn dưới đây là **ví dụ phương pháp**, không phải bảng số đo hiệu năng. Với phép đo thực tế nên chạy mỗi cấu trúc trong **một tiến trình sạch riêng** để tránh việc chỉ mục khác còn chiếm bộ nhớ.

```python
import gc
import time
import tracemalloc


def measure_build(factory, text):
    gc.collect()
    tracemalloc.start()

    start_time = time.perf_counter()
    index = factory(text)
    build_seconds = time.perf_counter() - start_time

    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return index, build_seconds, current_bytes, peak_bytes


# Chỉ dùng với text nhỏ khi so hai bản demo.
text = "banana" * 100

for factory in (SuffixTreeIndex, SuffixArrayIndex):
    index, build_s, current, peak = measure_build(
        factory, text
    )

    print(
        factory.__name__,
        "build_seconds:", build_s,
        "tracemalloc_current:", current,
        "tracemalloc_peak:", peak,
    )

    del index
    gc.collect()
```

**Cảnh báo về `tracemalloc`:** nó theo dõi các cấp phát Python được hỗ trợ, không phải lúc nào cũng phản ánh đầy đủ RSS của tiến trình hoặc mọi vùng nhớ native từ thư viện C. Nếu cần đánh giá RAM vận hành, bổ sung phép đo **resident set size** ở cấp tiến trình.

### 24.5. Vì sao không so tốc độ của mã demo để kết luận lý thuyết?

Mã cây trong bài xây từng hậu tố O(n²), còn mã SA dùng doubling với `sort` O(n log² n). Nếu SA xây nhanh hơn cây trong phép đo trên văn bản dài, điều đó **không phủ nhận** tồn tại thuật toán xây suffix tree O(n).

Ngược lại, nếu một thư viện suffix tree tối ưu bằng C++ nhanh hơn bản SA thuần Python, không thể từ đó suy rằng cấu trúc cây **luôn** nhanh hơn mảng. Cần so:

- Thuật toán được dùng thực sự.
- Ngôn ngữ và triển khai.
- Bảng chữ cái và encoding.
- Chi phí chuyển đổi dữ liệu.
- Bộ nhớ giữ lại và bộ nhớ đỉnh.
- Workload truy vấn sau khi xây.

### 24.6. Các phép đo thời gian có tính lặp

Nên làm ấm cache nếu muốn đo trạng thái ổn định, chạy nhiều vòng, báo median/p95 thay vì một lần đo, tách chi phí tạo chuỗi mẫu và hiển thị kết quả khỏi thời gian truy vấn. Nếu benchmark `occurrences`, hãy giữ cùng quy tắc sort kết quả cho hai bên.

Nếu dữ liệu quá lớn, cần cân nhắc thời gian xây O(n²) của bản cây minh họa; không dùng nó để benchmark triển khai production trên hàng chục triệu ký hiệu.

## 25. Chọn cấu trúc theo workload

### 25.1. Chỉ mục cần rất gọn trong RAM

Nếu ứng dụng có dữ liệu lớn, chủ yếu tìm mẫu, đếm, liệt kê khoảng hậu tố và ưu tiên bộ nhớ:

**Suffix array** thường là lựa chọn đáng cân nhắc trước, nhờ các mảng chỉ số phẳng và locality tốt. Chỉ giữ `LCP`/`rank` nếu truy vấn yêu cầu, dùng loại số nguyên đủ miền.

### 25.2. Rất nhiều truy vấn mẫu dài

Nếu đã có một suffix tree được xây bằng thuật toán phù hợp và chọn cạnh hiệu quả, tìm locus trực tiếp O(m) kỳ vọng có thể hấp dẫn khi nhiều mẫu dài.

Tuy nhiên cần so RAM và cache miss. Một suffix array với tìm kiếm tận dụng LCP cũng có thể giảm số phép so ký hiệu mẫu; không nên chỉ so cây O(m) với SA cơ bản O(m log n) rồi kết luận không cần benchmark.

### 25.3. Rất nhiều truy vấn đếm

Cả hai đều có thể trả count ngay sau khi tìm khoảng/locus:

- Cây: `leaf_count`.
- SA: `right-left`.

Vì vậy phần khác biệt lại nằm ở **định vị mẫu**, RAM và chi phí xây. Nếu mẫu rỗng, kết quả O(1) là `n+1`.

### 25.4. Liệt kê lượng kết quả lớn

Nếu `occ` rất lớn, chi phí sao chép/xuất kết quả và sort vị trí có thể thống trị thời gian ở cả hai chỉ mục.

Nếu giao diện chấp nhận **thứ tự từ điển của hậu tố**, SA có lợi vì kết quả nằm trong **một đoạn liên tiếp của mảng**; có thể đọc tuần tự mà không cần duyệt nhiều nút cây.

### 25.5. Bài toán nhiều LCP/chuỗi con lặp

Suffix array + LCP rất tự nhiên cho:

- `max(LCP)` tìm chuỗi con lặp dài nhất.
- `n(n+1)/2-sum(LCP)` đếm substring phân biệt.
- RMQ theo hạng hậu tố.

Suffix tree có thể giải tương đương bằng độ sâu nút trong, đếm lá và LCA, nhưng thường phải duy trì thêm metadata cây và đường duyệt.

### 25.6. Tìm mẫu chỉ một vài lần

Nếu văn bản ngắn hoặc chỉ có một số ít truy vấn, chi phí xây chỉ mục có thể **không thu hồi được**. Thuật toán tìm chuỗi trực tiếp, KMP, Boyer–Moore/Horspool hoặc một hàm tìm tối ưu của runtime có thể phù hợp hơn.

Không nên xây cả suffix tree hoặc suffix array chỉ vì bài toán có từ “substring”.

### 25.7. Văn bản cần chỉnh sửa liên tục

Nếu thường xuyên thay ký tự hoặc chèn/xóa ở giữa văn bản, cần thiết kế lại yêu cầu:

- Xây lại chỉ mục theo đợt.
- Dùng chỉ mục phân đoạn.
- Chọn cấu trúc dữ liệu động chuyên biệt.

Suffix tree có biến thể online cho **nối thêm**, nhưng không tự giải quyết sửa tùy ý; SA truyền thống cũng không hỗ trợ sửa giữa văn bản đơn giản.

## 26. Một bảng quyết định nhanh

| Ưu tiên chính | Cân nhắc trước | Lý do | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| RAM chỉ mục thấp | Suffix array phẳng | Ít metadata con trỏ, bố trí liên tục | Có cần LCP/rank/RMQ không? |
| Truy vấn mẫu dài thường xuyên | Suffix tree hoặc SA tăng tốc LCP | Giảm số ký hiệu phải so lại | RAM cây, cache, thuật toán tìm SA thực tế |
| Đếm rất nhiều mẫu | Cả hai | Sau locate chỉ đọc count/độ dài khoảng | Chi phí locate, tần suất cache |
| Liệt kê theo thứ tự hậu tố | Suffix array | Kết quả là một đoạn SA liên tiếp | Có yêu cầu vị trí tăng không? |
| Lặp dài nhất, đếm substring khác nhau | SA+LCP hoặc cây có metadata | Cả hai có thuật toán tuyến tính sau xây | Bộ nhớ và dạng dữ liệu cần xuất |
| LCP của hai suffix tùy ý | SA+RMQ hoặc tree+LCA | Trả lời nhanh sau tiền xử lý | RAM phụ và số truy vấn |
| Dữ liệu lớn cần xây tuyến tính | Thư viện chuyên dụng cả hai | Có thuật toán O(n) cho mỗi bên | Đúng biến thể và giả định bảng ký hiệu |
| Ít truy vấn trên văn bản nhỏ | Tìm trực tiếp | Tránh tiền xử lý | So thời gian xây và thời gian tìm |
| Nhiều lần sửa giữa văn bản | Xem lại kiến trúc chỉ mục | Cả hai phiên bản tĩnh khó duy trì | Có thể rebuild/segment không? |

Bảng là hướng dẫn ra quyết định, **không phải xếp hạng tuyệt đối**. Các cột “cần kiểm chứng” mới quyết định lựa chọn cuối.

## 27. Unicode, sentinel và tính nhất quán của vị trí

### 27.1. Code point không phải byte UTF-8

Trong Python:

```python
text = "bàn"

print(len(text))                 # Số code point.
print(len(text.encode("utf-8"))) # Số byte UTF-8.
```

Nếu cây và SA đều xây trên `str`, chỉ số trả về đều là vị trí **code point**. Nếu hệ thống tệp hoặc trình hiển thị cần offset byte, phải ánh xạ hoặc xây chỉ mục trên bytes và mô tả chính xác đơn vị vị trí.

### 27.2. Hai biểu diễn Unicode của một chữ

```python
import unicodedata

a = "bàn"
b = "ba\u0300n"

assert a != b
assert (
    unicodedata.normalize("NFC", a)
    == unicodedata.normalize("NFC", b)
)
```

Nếu muốn coi `a` và `b` là cùng nội dung, phải chuẩn hóa **văn bản trước khi xây** và **mọi mẫu trước khi tìm** theo cùng quy tắc. Chuẩn hóa có thể thay đổi số code point và offset.

### 27.3. Khi cần tô sáng bản gốc

Nếu chỉ mục được xây trên văn bản đã chuẩn hóa, các vị trí trả về thuộc **văn bản chuẩn hóa**, không tự khớp offset của văn bản gốc trước chuẩn hóa.

Nên giữ bản đồ offset hoặc một cơ chế truy hồi ranh giới ký tự để tô sáng chính xác.

### 27.4. Quy ước sentinel

Suffix tree trong mã dùng `"$"` kỹ thuật và giả định nó **không xuất hiện trong văn bản**. Với sản phẩm hỗ trợ mọi ký tự Unicode, nên dùng một đối tượng sentinel nằm ngoài bảng chữ cái dữ liệu hoặc một encoding đơn ánh, tránh va chạm.

Nếu dùng SA có sentinel và phát biểu sentinel nhỏ hơn mọi ký hiệu, điều đó phải đúng theo **quan hệ so sánh thực tế**. Không nên mặc định ký tự `$` luôn nhỏ hơn mọi Unicode code point.

### 27.5. Thứ tự từ điển và collation

Thứ tự `SA` theo Python `str` là thứ tự **Unicode code point**, không nhất thiết là thứ tự từ điển ngôn ngữ Việt Nam.

Nếu cần collation ngôn ngữ tự nhiên, phải xác định lại khóa so sánh và các quy tắc phù hợp với tìm tiền tố. Không thể đổi comparator sau khi xây SA/T mà vẫn chắc mọi đường hoặc mảng sắp còn hợp lệ.

## 28. Các lỗi hiểu sai khi so sánh

| Nhận định sai | Điều gì bị bỏ qua? | Cách diễn đạt đúng |
| --- | --- | --- |
| “Cả hai O(n) nên tốn RAM như nhau.” | Số con trỏ, đối tượng, bảng nhánh, LCP/RMQ | O(n) chỉ mô tả bậc, cần đo byte |
| “Cây có O(n) nút nên chèn hậu tố O(n).” | Mỗi lần chèn có thể so O(n) ký hiệu | Bản naïve xây O(n²) |
| “SA luôn xây O(n log n).” | Phụ thuộc sort/cách xây | Doubling+sort O(n log² n), có cách nhanh hơn |
| “Suffix tree luôn dùng O(n) byte.” | Word size, bảng nhánh, metadata | O(n) từ máy với biểu diễn và giả định phù hợp |
| “Chỉ cần giữ SA, truy vấn substring luôn O(log n).” | So mẫu với hậu tố có thể O(m) | Binary search cơ bản O(m log n) |
| “Thêm LCP là binary search tự O(m+log n).” | Thuật toán so sánh chưa tận dụng LCP | Cần tìm kiếm có tăng tốc LCP thật |
| “Đếm trong cây phải duyệt tất cả lá.” | Có thể lưu leaf_count | O(m) locate + O(1) đọc count |
| “Đếm trong SA phải duyệt đoạn.” | Khoảng đã biết hai biên | `count=right-left` |
| “Cây trả vị trí theo thứ tự xuất hiện.” | DFS thường theo nhánh từ điển | Sort nếu muốn vị trí tăng |
| “SA[lower:upper] luôn có vị trí tăng.” | SA sắp hậu tố, không sắp vị trí | Sort hoặc chỉ mục phụ |
| “Có thể trả triệu vị trí trong O(1).” | Đầu ra có độ dài occ | Luôn cần Ω(occ) thao tác xuất |
| “LCP hai hậu tố bất kỳ lấy ngay một ô LCP.” | Ô LCP chỉ dành cho cặp kề nhau | Dùng RMQ trên đoạn rank |
| “Cây LCA luôn O(1) ngay khi có cây.” | Cần tiền xử lý LCA và độ sâu ký hiệu | Nêu rõ thuật toán LCA |
| “Cây có online construction nên sửa giữa text O(1).” | Online append khác sửa tùy ý | Cần cấu trúc động chuyên biệt |
| “Thay một code point là thay một byte.” | UTF-8 đa byte và chuẩn hóa | Ghi rõ đơn vị và offset |
| “Cây và SA đang xử lý cùng n+1 hậu tố.” | Có nhiều quy ước sentinel | Nêu `n+1` lá cây và `n` ô SA của bài |
| “Cứ có '$' là sentinel hợp lệ.” | Nó có thể trùng dữ liệu | Chọn sentinel ngoài miền dữ liệu |
| “Một lần đo là đủ chứng minh nhanh hơn.” | Nhiễu cache, GC, runtime, phân bố dữ liệu | Lặp lại phép đo, báo phương pháp |
| “Bộ nhớ `sys.getsizeof(index)` là toàn cây.” | Đo nông, bỏ các đối tượng tham chiếu | Đo đệ quy/heap profiler/RSS |
| “So bản tree naïve với thư viện SA tối ưu là công bằng.” | Khác thuật toán và ngôn ngữ | Nêu rõ cấp độ và mục tiêu so sánh |

## 29. Bài tập vận dụng có gợi ý giải

### Bài 1 — Hậu tố của một văn bản

Cho `s="aba"`. Liệt kê các hậu tố không rỗng và tính SA.

**Gợi ý:** Hậu tố: `aba` ở 0, `ba` ở 1, `a` ở 2. Thứ tự `a<aba<ba`, nên `SA=[2,0,1]`.

### Bài 2 — Số lá của cây có sentinel

Với `s="aba"` dài 3, cây của `T="aba$"` có bao nhiêu lá?

**Gợi ý:** 4 lá tương ứng hậu tố bắt đầu ở 0,1,2,3; lá 3 dành cho hậu tố `"$"`.

### Bài 3 — LCP và mảng hậu tố

Với `s="aba"` và `SA=[2,0,1]`, LCP theo quy ước bài là gì?

**Gợi ý:** `LCP=[0,1,0]`.

### Bài 4 — Hậu tố rỗng

Vì sao SA của bài có 3 phần tử nhưng cây hậu tố có 4 lá đối với `aba`?

**Gợi ý:** SA không chứa hậu tố rỗng; cây thêm sentinel và một lá `"$"`. Mẫu không rỗng vẫn cho cùng vị trí.

### Bài 5 — Kết thúc giữa cạnh

Nếu cây có cạnh `"banana$"` từ gốc tới lá 0, tìm mẫu `ban` phải trả kết quả gì?

**Gợi ý:** Khớp ngay giữa cạnh; kết quả vị trí 0. Không được yêu cầu mẫu kết thúc tại một nút.

### Bài 6 — Khoảng SA của `ana`

Cho `SA=[5,3,1,0,4,2]` của `banana`. Khoảng hậu tố khớp `ana` là gì và danh sách vị trí tăng là gì?

**Gợi ý:** `SA[1:3]=[3,1]`; sau sort là `[1,3]`.

### Bài 7 — Đếm không duyệt kết quả

Nếu cây có locus với `leaf_count=125`, hoặc SA có biên `left=200,right=325`, số lần xuất hiện là bao nhiêu?

**Gợi ý:** Đều là 125. Không cần tạo 125 số nguyên chỉ để trả count.

### Bài 8 — Cận dưới đầu ra

Một mẫu có 500.000 vị trí xuất hiện. Có thể trả một danh sách đầy đủ trong O(1) thời gian không?

**Gợi ý:** Không. Phải xuất ít nhất 500.000 chỉ số, nên có cận dưới Ω(occ).

### Bài 9 — Số nút cây hậu tố

Với `n=1000`, cây hậu tố nén chuẩn của `s+$` có tối đa bao nhiêu lá, nút và cạnh nếu `n≥1`?

**Gợi ý:** 1001 lá, tối đa 2001 nút và 2000 cạnh, theo lập luận nút trong có ít nhất hai con.

### Bài 10 — Mô hình mảng phẳng 64 bit

Với `n=100000`, ba mảng `SA,LCP,rank` dạng `uint64` chiếm bao nhiêu byte dữ liệu ô?

**Gợi ý:** `3×100000×8=2.400.000` byte, chưa tính văn bản và overhead. `list[int]` Python có thể tốn hơn.

### Bài 11 — Phân biệt O(n) bộ nhớ với byte thực

Vì sao suffix tree và SA cùng O(n) từ máy nhưng thường có RAM thực tế khác nhau?

**Gợi ý:** Cây giữ nút, cạnh, con trỏ, bảng nhánh, metadata; SA có thể là mảng số nguyên liên tục.

### Bài 12 — Xây chỉ mục naïve

Nếu chèn lần lượt mọi hậu tố và mỗi lần so từ gốc, thời gian có thể đạt bậc gì?

**Gợi ý:** Tổng độ dài hậu tố Θ(n²); nén cạnh và giữ chỉ số không tự giảm lượng so lặp.

### Bài 13 — Xây SA bằng doubling

Prefix doubling có O(log n) vòng; dùng sort so cặp hạng O(n log n) mỗi vòng. Tổng là bao nhiêu?

**Gợi ý:** O(n log² n). Radix/counting sort mỗi vòng có thể làm thời gian khác.

### Bài 14 — LCP giữa hai hậu tố

Cho `rank[i]=a<rank[j]=b`. Dùng LCP array so hạng trước như bài, công thức lcp là gì?

**Gợi ý:** `min(LCP[a+1:b+1])`. Nếu `i=j`, trả `n-i`.

### Bài 15 — Tổ tiên chung thấp nhất

Trong suffix tree, LCP của hai hậu tố liên hệ với LCA của hai lá như thế nào?

**Gợi ý:** Bằng độ sâu **theo ký hiệu** từ gốc tới LCA, không phải số cạnh.

### Bài 16 — Đếm substring phân biệt

Với `banana`, tổng độ dài hậu tố 21 và tổng LCP bằng 6. Số chuỗi con phân biệt không rỗng là bao nhiêu?

**Gợi ý:** 15. Có thể đối chiếu bằng tổng độ dài các phần nhãn cạnh cây không chứa `$`.

### Bài 17 — Lặp dài nhất

Với `LCP=[0,1,3,0,0,2]`, độ dài chuỗi con lặp dài nhất của `banana` là bao nhiêu?

**Gợi ý:** 3, một kết quả là `ana`. Cho phép hai lần xuất hiện chồng lấn.

### Bài 18 — Mẫu rỗng

Với `s="banana"` dài 6, hai API theo hợp đồng bài trả `count("")` bằng bao nhiêu?

**Gợi ý:** 7, ứng với các ranh giới 0 đến 6; khác với số phần tử SA là 6.

### Bài 19 — So truy vấn trên dữ liệu rất lặp

Vì sao nên đưa văn bản như `aaaa...` vào benchmark?

**Gợi ý:** Nhiều hậu tố có tiền tố chung dài; chi phí so mẫu và cấu trúc nhánh có thể khác so với dữ liệu gần ngẫu nhiên.

### Bài 20 — Bộ nhớ đỉnh

Vì sao chỉ đo kích thước SA sau khi xây chưa đủ để dự báo một tiến trình có bị thiếu RAM khi xây hay không?

**Gợi ý:** Sort, rank, mảng tạm và allocator có thể làm đỉnh RAM cao hơn retained memory sau xây.

### Bài 21 — Cùng chức năng, khác thuật toán

Một suffix tree được xây bằng chèn từng hậu tố chậm hơn SA dùng thư viện tối ưu. Có chứng minh SA luôn xây nhanh hơn mọi suffix tree không?

**Gợi ý:** Không; có thuật toán cây tuyến tính. Phải so cùng loại thuật toán, runtime và tập dữ liệu.

### Bài 22 — Unicode và offset

Một API trả chỉ số code point trong Python `str` nhưng giao diện cần byte offset UTF-8. Có thể dùng trực tiếp không?

**Gợi ý:** Không. Cần bảng ánh xạ hoặc chỉ mục trên bytes và quy ước nhất quán.

### Bài 23 — Chọn chỉ mục cho hệ thống

Một hệ cần bộ nhớ thấp, 10 triệu ký hiệu và đa số yêu cầu là tìm rồi liệt kê theo thứ tự từ điển hậu tố. Bạn nên cân nhắc cấu trúc nào trước?

**Gợi ý:** SA phẳng, vì kết quả là khoảng liên tiếp và ít metadata. Nhưng phải đo cách xây, RAM đỉnh, độ dài mẫu, số kết quả và nhu cầu thêm LCP.

### Bài 24 — Truy vấn mẫu dài nhiều lần

Một hệ RAM dồi dào và có nhiều truy vấn mẫu dài trên văn bản tĩnh. Vì sao nên benchmark cả suffix tree và SA dùng LCP-aware search?

**Gợi ý:** Cây có thể định vị O(m); SA tìm cơ bản O(m log n) nhưng biến thể tận dụng LCP có thể cải thiện. RAM và cache có thể đảo chiều kết quả.

## 30. Checklist trước khi quyết định cấu trúc

```text
1. Hợp đồng:
   - Contains, count, occurrences hay tất cả?
   - Mẫu rỗng có n+1 vị trí?
   - Có cho phép lần xuất hiện chồng lấn?
   - Kết quả phải theo vị trí văn bản hay theo suffix order?

2. Dữ liệu:
   - Text bất biến hay cập nhật?
   - Đơn vị ký hiệu byte, code point hay grapheme?
   - Có chuẩn hóa Unicode nhất quán?
   - Sentinel của tree có bảo đảm không trùng dữ liệu?

3. Cây hậu tố:
   - Mỗi cạnh chỉ giữ [start,end) trỏ vào T?
   - Các cạnh ra cùng nút có ký hiệu đầu khác nhau?
   - Có n+1 lá và root/empty-text được xử lý đúng?
   - Có leaf_count cho count O(1) sau locate?
   - Cách chọn cạnh có chi phí nào?
   - Đã dùng thuật toán xây naïve hay tuyến tính thật?

4. Mảng hậu tố:
   - SA là hoán vị 0..n-1 tăng theo từ điển?
   - Có cần LCP, rank, RMQ không?
   - Comparator coi khớp toàn mẫu là 0?
   - Có dùng hai binary search để tìm khoảng?
   - Xây bằng doubling+sort hay thuật toán khác?
   - Kiểu chỉ số lưu phẳng hay Python object?

5. Đo bộ nhớ:
   - So index-only hay total service memory?
   - Có đo peak lúc xây, không chỉ retained sau xây?
   - Có tính LCP/rank/suffix links/dictionary?
   - Có tính bộ nhớ kết quả nhiều occ?
   - Có kiểm tra byte thực và RSS, không chỉ Big-O?

6. Đo thời gian:
   - n, m, occ và phân bố tiền tố chung?
   - Mẫu có/không, ngắn/dài, ít/nhiều kết quả?
   - Đã tách contains/count/occurrences?
   - Có cần sắp vị trí trước khi trả?
   - Có chạy nhiều vòng, báo median/p95?

7. Ứng dụng:
   - Đếm substring phân biệt bằng LCP/nhãn cạnh?
   - Lặp dài nhất có cho phép chồng lấn?
   - LCP giữa hai suffix cần RMQ hay LCA?
   - Nhiều văn bản có separator/owner metadata?
   - Nếu chỉ vài truy vấn, có nên tìm trực tiếp?

8. Kiểm chứng:
   - Hai chỉ mục có cùng kết quả theo oracle quét?
   - Text rỗng, một ký hiệu, ký hiệu lặp và Unicode?
   - Kiểm tra cả khoảng SA, leaf_count và thứ tự đầu ra?
   - Không suy thời gian xây của một thuật toán từ cấu trúc khác?
```

## 31. Tổng kết

**Cây hậu tố** và **mảng hậu tố** đều tận dụng việc tìm chuỗi con quy về tìm tiền tố của các hậu tố. Nhưng chúng khác nhau ở **cách biểu diễn**:

- Cây hậu tố nén giữ **nút phân nhánh, lá hậu tố và nhãn cạnh bằng đoạn tham chiếu**. Nó thuận tiện cho việc đi theo mẫu O(m) kỳ vọng nếu chọn cạnh hiệu quả; đếm bằng `leaf_count` và liệt kê bằng duyệt lá.
- Mảng hậu tố giữ **thứ tự hậu tố trong một mảng chỉ số**, thường thêm `LCP`/`rank` theo nhu cầu. Tìm mẫu cơ bản dùng hai biên nhị phân O(m log n); khoảng kết quả liên tục trong SA, phù hợp lưu trữ gọn và duyệt tuần tự.

Cả hai có thể dùng **O(n) từ máy** theo giả định thích hợp, nhưng **không cùng số byte**. Suffix tree liên kết thường có overhead con trỏ và bảng nhánh lớn hơn, còn SA phẳng tận dụng locality. Ngược lại, tìm mẫu trên cây có thể tránh nhiều lần so mẫu mà binary search cơ bản thực hiện.

Điều quan trọng nhất khi lựa chọn là **tách ba loại chi phí**: thời gian xây, bộ nhớ đỉnh/giữ lại và độ trễ của đúng phép truy vấn cần phục vụ. Một chương trình suffix tree chèn mọi hậu tố có thể xây O(n²) dù cây cuối có O(n) nút; một chương trình SA dùng prefix doubling + sort có thể tốn O(n log² n), dù tồn tại thuật toán xây SA tuyến tính.

Khi hợp đồng trả kết quả, đơn vị Unicode, cách sắp thứ tự và thuật toán triển khai được công bố rõ ràng, việc chọn suffix tree hay suffix array trở thành một quyết định **đo được bằng workload**, thay vì một kết luận dựa trên một dòng Big-O.

# Cây rope cho chuỗi dài và các thao tác ghép–cắt

## 1. Vì sao chuỗi dài cần một cấu trúc khác mảng ký tự?

Giả sử bạn xây dựng trình soạn thảo tài liệu. Người dùng có thể mở tệp dài hàng triệu ký tự, chèn một câu ở giữa, xóa một đoạn, cắt–dán một chương rồi hoàn tác. Nếu toàn bộ văn bản nằm trong **một chuỗi liên tiếp**, nhiều thao tác phải dời hoặc sao chép lượng lớn dữ liệu.

Ví dụ, từ:

```text
ABCDE | FGHIJ
```

chèn `"--"` tại vị trí sau `B` tạo ra:

```text
AB--CDEFGHIJ
```

Với chuỗi bất biến kiểu Python `str`, phép `s[:i] + text + s[i:]` tạo ra các chuỗi kết quả mới; lượng ký tự bị đọc/sao chép có thể tỷ lệ với độ dài `n` của văn bản, ngay cả khi `text` chỉ gồm vài ký tự.

**Rope** là một **cây biểu diễn chuỗi theo nhiều đoạn nhỏ** (*chunks*) thay vì bắt buộc lưu toàn bộ chuỗi trong một mảng liên tiếp. Nhờ lưu độ dài của các cây con, rope có thể **định vị vị trí**, **tách chuỗi**, **ghép chuỗi** và **thay đổi đoạn** chủ yếu bằng thay đổi liên kết giữa các nút.

### Những câu hỏi mà rope giúp giải quyết

- Làm sao truy cập ký tự tại chỉ số `i` mà không ghép toàn bộ tài liệu thành một chuỗi lớn?
- Làm sao ghép hai văn bản mà không sao chép tất cả ký tự của cả hai?
- Làm sao cắt tài liệu ở vị trí `i` và giữ nguyên phần lớn các khối cũ?
- Vì sao một cấu trúc rope **không cân bằng** vẫn có thể chậm tới `O(n)`?
- Chỉ số `i` là **byte**, **Unicode code point** hay **cụm ký tự hiển thị**?
- Khi nào rope đáng dùng hơn mảng động, gap buffer, piece table hoặc cây đoạn?

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả rope cổ điển: **lá chứa văn bản**, nút trong chứa liên kết và `weight`.
2. Nêu đúng bất biến `weight = length(left subtree)` và cách lần theo vị trí 0-based.
3. Mô phỏng `concat`, `split`, `insert`, `delete`, `substring`.
4. Phân biệt **chi phí con trỏ** với **chi phí sao chép một chunk** ở biên cắt.
5. Phân tích các cận `O(h)` và điều kiện để có `O(\log m)`, với `m` là số nút/khối.
6. Hiểu sự khác nhau giữa **rope bất biến/persistent** và **rope sửa tại chỗ/mutable**.
7. Cài biến thể rope theo **implicit treap chứa chunk**, sử dụng `subtree length` và `split/merge`.
8. Kiểm tra tính đúng đắn, xử lý Unicode, cân nhắc bộ nhớ, locality và độ trễ cho bài toán thực tế.

Chủ đề thuộc chương **Cây tăng cường** trong học phần **Cấu trúc dữ liệu**. Rope kết hợp ý tưởng cây cân bằng, chuỗi, mảng nhỏ và metadata cây con để minh họa cách bảo trì bất biến và chọn biểu diễn phù hợp giữa mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Rope là gì? Tư duy “cây chứa các đoạn”

Một rope có thể biểu diễn văn bản `"Hello world"` như sau:

```text
                      root (weight = 5)
                     /                 \
              "Hello"              node (weight = 1)
                                     /            \
                                   " "          "world"

Đọc từ lá trái sang lá phải:
    "Hello" + " " + "world" = "Hello world"
```

**Rope cổ điển** thường được mô tả bằng:

- **Nút lá:** lưu một đoạn ký tự không rỗng hoặc một tham chiếu tới lát cắt của vùng lưu trữ ký tự.
- **Nút trong:** có `left`, `right` và **`weight` bằng độ dài văn bản của toàn bộ cây con trái**.
- Có thể lưu thêm `total_length`, `height`, số dòng, tổng số code point hay metadata khác để tối ưu.

Văn bản logic là phép **nối các lá theo thứ tự duyệt in-order từ trái sang phải**. Không cần tồn tại một khối bộ nhớ liên tiếp chứa toàn bộ văn bản.

### Rope có phải cây tìm kiếm nhị phân theo khóa không?

Không nhất thiết. Trong BST thông thường, các nút được sắp **theo khóa**; với rope, thứ tự **đến từ vị trí trái–phải của các đoạn**. Chỉ số là **ẩn** (*implicit index*) và được xác định bằng tổng độ dài.

Ví dụ, nếu cây con trái chứa 5 ký tự thì vị trí `0..4` ở bên trái; vị trí `5` trở đi thuộc cây phải. Khi chèn trước vị trí `3`, chỉ số các ký tự sau đó thay đổi; ta **không phải cập nhật một khóa vị trí riêng ở từng nút** nếu đã có tổng độ dài cây con.

Đây chính là ý tưởng **augmentation**: lưu số lượng ký tự của cây con để chuyển một phép truy vấn theo vị trí thành phép đi theo đường gốc–lá.

## 3. Bất biến quan trọng nhất: độ dài cây con

Gọi `len(T)` là số **đơn vị chỉ số** trong văn bản của cây `T`. Trong ví dụ lý thuyết, ta xem mỗi phần tử chuỗi là một đơn vị chỉ số.

Với rope lá chỉ chứa chuỗi `chunk`:

\[
\boxed{len(leaf)=length(chunk).}
\]

Với nút trong `v`:

\[
\boxed{\begin{aligned}
weight(v)&=len(v.left),\\
len(v)&=len(v.left)+len(v.right).
\end{aligned}}
\]

Rope rỗng có `len(None)=0`.

### Ví dụ kiểm tra

```text
Lá A: "Data"      -> length = 4
Lá B: " stru"     -> length = 5
Lá C: "ctures"    -> length = 6

                root (weight=4, len=15)
                /                   \
       "Data" (len=4)         node (weight=5, len=11)
                             /                  \
                      " stru" (len=5)       "ctures" (len=6)

Kết quả: "Data structures", length=15
```

Một cách cài khác lưu **`size(v)` là tổng độ dài cả cây con** thay vì chỉ `weight`. Khi đó tại một nút ta có thể tính `weight=len(v.left)` bằng cách đọc `size` của con trái. Hai biểu diễn tương đương về khả năng định vị, miễn là mọi phép sửa cây **bảo trì metadata nhất quán**.

### Phân biệt ba đại lượng

| Đại lượng | Ý nghĩa |
|---|---|
| `len(T)` | Tổng số ký tự/đơn vị chỉ số thuộc cây `T` |
| `weight(v)` | Số đơn vị chỉ số trong **cây con trái của nút trong `v`** |
| `height(T)` | Chiều cao cây, ảnh hưởng số tầng phải đi qua khi tìm vị trí |

**Độ dài không phải chiều cao.** Một cây chứa một triệu ký tự có thể gồm một lá rất lớn hoặc hàng nghìn lá. Chi phí đọc một vị trí phụ thuộc chiều cao và cách tổ chức chunk, không chỉ tổng độ dài.

## 4. Truy cập ký tự tại vị trí i bằng trọng số

Dùng chỉ số **0-based**, hợp lệ khi:

\[
0\le i<len(root).
\]

Ở một **nút trong** có `weight=w`:

- Nếu `i<w`, ký tự nằm trong **cây trái**; giữ nguyên `i`.
- Nếu `i\ge w`, ký tự nằm trong **cây phải**; cập nhật `i\gets i-w`.
- Khi tới lá, đọc `chunk[i]`.

### Mã giả

```text
CHAR_AT(root, i):
    require 0 <= i < length(root)
    node = root
    while node is internal:
        if i < node.weight:
            node = node.left
        else:
            i -= node.weight
            node = node.right
    return node.chunk[i]
```

### Mô phỏng trên “Data structures”

```text
                 root weight=4
                 /           \
              "Data"      node weight=5
                          /           \
                       " stru"       "ctures"
```

Tìm `char_at(7)`:

1. Tại root, `7\ge4`: đi phải và đặt `i=7-4=3`.
2. Tại nút phải, `3<5`: đi trái, `i=3`.
3. Lá `" stru"` có các vị trí `0=" "`, `1="s"`, `2="t"`, `3="r"`, `4="u"`. Trả `"r"`.

Đối chiếu chuỗi thực: `"Data structures"[7] == "r"`.

**Độ phức tạp:** `O(h)` nút trên đường tìm, cộng chi phí đọc một ký tự trong chunk. Nếu lá là chuỗi có truy cập theo đúng đơn vị chỉ số trong `O(1)`, kết quả là **`O(h)`**.

## 5. Độ cao cây và tính cân bằng quyết định hiệu quả

Giả sử rope chứa `m` lá/chunk. Nếu cân bằng tốt, chiều cao thường:

\[
h=O(\log(m+1)).
\]

Khi đó tìm ký tự, xác định vị trí split hoặc các bước nối/sửa cấu trúc được thực hiện chủ yếu trên một số tầng logarithmic.

Nhưng nếu mỗi lần append tạo một nút gốc mới mà **không cân bằng**, có thể hình thành cây lệch:

```text
             (((("A" + "B") + "C") + "D") + "E")

                 root
                 /  \
                ... "E"
               /   \
              ...  "D"
             ...
```

Sau `m` lần ghép như vậy, một số đường có thể dài `\Theta(m)`. Truy cập ký tự ở đầu có thể cần `\Theta(m)` bước dù rope không sao chép nội dung trong quá trình ghép.

**Kết luận quan trọng:** việc tạo một nút mới khi nối hai rope có thể là `O(1)` **cho riêng lần nối**, nhưng nếu không bảo trì cân bằng thì **không thể kết luận mọi thao tác tiếp theo có `O(\log m)`**.

Các chiến lược cân bằng có thể gồm AVL/weight-balanced rope, các dạng tree rank, treap ngẫu nhiên hoặc tái xây theo lô. Mỗi chiến lược có chi phí và bảo đảm riêng; không nên dùng từ “rope” như thể nó ngầm bảo đảm một loại cân bằng.

## 6. Chunk: vì sao không đặt mỗi ký tự vào một nút?

Nếu mỗi ký tự có một nút, một tài liệu dài `n` ký tự cần tới `n` nút liên kết và nhiều con trỏ, gây cấp phát và cache miss.

Rope thực tế thường lưu **một đoạn ký tự liên tiếp trong một lá**. Gọi `B` là kích thước chunk mục tiêu/tối đa:

```text
Thay vì:
  [D] [a] [t] [a] [ ] [s] [t] [r] ...

Lưu thành:
  ["Data"] [" stru"] ["ctures"]
```

### Chunk quá nhỏ

- Rất nhiều nút, tốn con trỏ và metadata.
- Cây có thể sâu hơn và phải cấp phát nhiều lần.
- Duyệt toàn văn bản phải đi qua rất nhiều nút nhỏ.

### Chunk quá lớn

- Ít nút, truy cập tuần tự tốt hơn.
- Nhưng cắt **giữa chunk** có thể phải sao chép một phần chunk lớn.
- Việc thay một ký tự trong một chunk bất biến có thể sao chép cả đoạn.

Chọn `B` là đánh đổi giữa **độ sâu/overhead con trỏ** và **chi phí sao chép ở biên sửa**. Không có một kích thước chunk tối ưu cho mọi runtime và kiểu dữ liệu.

### Quản lý chunk sau nhiều lần chỉnh sửa

Sau nhiều lần split ở giữa, một chunk có thể bị chia thành nhiều chunk rất nhỏ. Nhiều lần ghép có thể đặt các chunk nhỏ cạnh nhau mà chưa hợp nhất lại. Một triển khai production thường cần **coalesce/rechunk**:

- Ghép các chunk kề đủ nhỏ.
- Chia chunk quá lớn.
- Tái cân bằng khi cây mất hình dạng tốt.

Những thao tác bảo trì này có chi phí thật, cần đưa vào phân tích **khấu hao hoặc benchmark**, thay vì coi chúng tự xảy ra miễn phí.

## 7. CONCAT: ghép hai rope

Cho hai rope `A` và `B` biểu diễn chuỗi `SA` và `SB`. Ta cần:

\[
concat(A,B)\text{ biểu diễn }SA\Vert SB.
\]

### Cách ghép đơn giản

Tạo nút trong mới có:

```text
new.left  = A
new.right = B
new.weight = length(A)
new.length = length(A) + length(B)
```

Ví dụ:

```text
R1 = "Hello "
R2 = "world"

            CONCAT (weight=6)
             /             \
         "Hello "         "world"

Văn bản logic: "Hello world"
```

Nếu chỉ **tạo nút gốc nối**, số phép gán con trỏ là hằng số và **không cần sao chép nội dung các lá**. Tuy nhiên, cách này không duy trì cân bằng qua chuỗi ghép tùy ý.

### CONCAT cân bằng

Một rope có thuật toán **join cân bằng** có thể cần đi vào một số nhánh, sửa metadata và xoay/tái cấu trúc để giữ chiều cao logarithmic. Với nhiều biểu diễn cân bằng, chi phí nối có thể ở mức `O(\log(m_A+m_B))` hoặc cận chi tiết hơn phụ thuộc độ cao hai cây.

**Đừng gộp hai phát biểu “tạo gốc mới `O(1)`” và “rope luôn cân bằng” thành một bảo đảm chung.** Muốn biết cận thật, phải xét **thuật toán cân bằng cụ thể**.

## 8. SPLIT: cắt một rope tại vị trí k

`split(R,k)` chia văn bản `S` thành hai phần:

\[
\boxed{
S=S_{left}\Vert S_{right},\quad
|S_{left}|=k,\quad |S_{right}|=n-k
}
\]

với `0\le k\le n`.

Đây là **vị trí biên** (*boundary index*), không phải chỉ số của một ký tự cần lấy:

```text
S = "ABCDEFGHIJ"

Biên: 0 1 2 3 4 5 6 7 8 9 10
      |A|B|C|D|E|F|G|H|I|J|

split(S,6) -> "ABCDEF"  và "GHIJ"
split(S,0) -> ""        và "ABCDEFGHIJ"
split(S,10)-> "ABCDEFGHIJ" và ""
```

### Ba tình huống

1. **Biên nằm giữa hai cây con:** chỉ cần tách liên kết và nối các phần phù hợp.
2. **Biên trùng ranh giới lá/chunk:** không cần sao chép ký tự; có thể tái sử dụng nguyên các lá.
3. **Biên nằm giữa một chunk:** phải chia chunk thành hai đoạn, ví dụ `"ABCDE"` tại `k=2` thành `"AB"` và `"CDE"`. Với chuỗi bất biến, việc tạo hai chuỗi mới sao chép ký tự trong chunk ấy.

### Trực giác thuật toán

Nếu dùng rope cổ điển có nút trong `weight`:

- `k<weight`: cắt trong cây trái; phần phải của cây trái cần **ghép trước** cây phải cũ.
- `k>weight`: cắt trong cây phải tại `k-weight`; phần trái cũ đứng trước phần trái mới của cây phải.
- `k=weight`: hai cây con trái/phải chính là hai kết quả.

Để giữ cân bằng, các lần ghép lại phải dùng một phép **join có bảo đảm cân bằng**. Trên cây cân bằng với chunk dài tối đa `B`, một lần split thường làm việc trên `O(\log m)` tầng và có thể cần sao chép `O(B)` ký tự ở chunk bị cắt.

### Không mất dữ liệu khi split

Khi split đúng, kết quả phải thỏa:

```text
to_string(left) + to_string(right) == original
len(left) == k
len(right) == len(original) - k
```

Đây là ba bất biến kiểm thử cơ bản mà một implementation rope phải vượt qua.

## 9. INSERT: kết hợp split và concat

Chèn chuỗi `X` vào vị trí `i` của rope `R`:

1. `(A,B)=split(R,i)`.
2. Tạo một rope `T` biểu diễn `X`, thường chia `X` thành các chunk.
3. `R'=concat(concat(A,T),B)`.

Mô phỏng:

```text
R = "ABCDE"
i = 2
X = "--"

split(R,2) -> A="AB", B="CDE"
concat(A,X) -> "AB--"
concat("AB--",B) -> "AB--CDE"
```

Tính đúng dựa trên **thứ tự nối**:

\[
\boxed{insert(R,i,X)=R[0:i]\Vert X\Vert R[i:n].}
\]

### Chi phí

Chèn không phải di chuyển toàn bộ hậu tố văn bản như mảng phẳng. Tuy nhiên, nếu `X` chứa `q` ký tự, ta vẫn phải **nhận/lưu ít nhất `q` ký tự**, và có thể tạo nhiều chunk mới.

Do đó, không nên nói “chèn một chuỗi tùy dài vào rope tốn `O(\log n)`” mà bỏ qua `q`. Một biểu thức có ý nghĩa hơn là:

\[
O(\text{chi phí split/join}+\text{chi phí tạo chunk cho }X).
\]

Với đoạn `X` rất ngắn, thao tác cây có thể chiếm phần lớn; với đoạn `X` rất dài, xử lý chính `X` có thể chiếm ưu thế.

## 10. DELETE và REPLACE: xóa một khoảng nửa kín

Xóa đoạn **`[l,r)`**:

```text
0 <= l <= r <= len(R)
```

Sử dụng hai lần split:

```text
(A,rest) = split(R,l)
(middle,C) = split(rest,r-l)
discard middle
R' = concat(A,C)
```

Ví dụ:

```text
R = "AB--CDE"
delete(R,2,4)

A = "AB"
middle = "--"
C = "CDE"
R' = "ABCDE"
```

Độ dài kết quả:

\[
\boxed{len(R')=len(R)-(r-l).}
\]

**Không phải sao chép toàn bộ hậu tố** nếu các chunk được giữ và nối lại bằng thao tác cấu trúc. Nhưng nếu xóa cắt ngang hai chunk, có thể phải sao chép các đoạn nhỏ ở hai biên.

### Thay một đoạn bằng đoạn khác

`replace(l,r,X)` có thể xem là:

```text
delete(l,r)
insert(l,X)
```

Hoặc làm trực tiếp bằng `split` để tránh dựng lại không cần thiết:

```text
A, rest = split(R,l)
middle, C = split(rest,r-l)
R' = join(join(A, rope(X)), C)
```

Khi viết mã cần quyết định điều gì xảy ra với `middle`: bị hủy, được trả về để **undo**, hay được giữ trong phiên bản tài liệu cũ. Đây là lựa chọn **ownership/persistence**, không phải chi tiết nhỏ của phép xóa.

## 11. SUBSTRING và truy xuất một khoảng

Để lấy chuỗi con `R[l:r]`, có hai chiến lược:

**Cách A — split rồi lấy giữa:** tách tại `l` và `r`, lấy rope phần giữa; nếu cấu trúc mutable phải nối lại phần gốc hoặc chấp nhận chuyển quyền sở hữu các đoạn.

**Cách B — chỉ đọc qua cây:** đi vào các cây con giao với đoạn `[l,r)`, gom các lát cắt của chunk thành kết quả. Cách này không sửa cây, thích hợp khi chỉ muốn đọc.

Với `k=r-l` ký tự xuất ra và `t` chunk giao với đoạn, chi phí thường có dạng:

\[
\boxed{O(h+t+k)}
\]

trong mô hình sao chép ký tự vào chuỗi kết quả, vì phải chạm tới những chunk có nội dung được yêu cầu.

**Nếu API trả một rope con** thay vì một `str` phẳng, phần lớn các chunk có thể được tái sử dụng qua một phép split/join (đặc biệt trong cấu trúc persistent). **Nếu API yêu cầu một chuỗi liên tiếp**, luôn có chi phí vật chất hóa `\Omega(k)` ký tự.

### Truy xuất toàn bộ chuỗi

`to_string(R)` duyệt lá từ trái qua phải và ghép các chunk:

```text
chunks = ["Hello", " ", "world"]
result = "".join(chunks)
```

Việc tạo chuỗi phẳng dài `n` vẫn tốn `O(n)` thời gian và bộ nhớ kết quả, không được quảng bá là `O(\log n)` chỉ vì cấu trúc gốc là rope.

## 12. Tách ghép và bất biến: chứng minh ngắn

Hãy định nghĩa `text(T)` là chuỗi tạo bởi các chunk theo thứ tự.

**Bất biến concat:** với mọi cây `A,B` hợp lệ,

\[
text(join(A,B))=text(A)\Vert text(B).
\]

**Bất biến split:** với `0\le k\le len(T)`,

\[
\begin{aligned}
split(T,k)&=(A,B),\\
text(T)&=text(A)\Vert text(B),\\
len(A)&=k.
\end{aligned}
\]

### Chứng minh bằng cách đi theo cây

Ở mỗi nút, văn bản logic là:

```text
text(left) + text(node hoặc leaf) + text(right)
```

So sánh `k` với độ dài cây trái và chunk tại nút cho biết **bao nhiêu ký tự chắc chắn đứng trước biên cắt**. Khi rẽ vào một nhánh, phần không liên quan được **giữ nguyên thứ tự** và ghép vào bên thích hợp.

Nếu biên nằm giữa chunk, `chunk[:j]+chunk[j:]==chunk` đúng theo định nghĩa lát cắt. Ghép các thành phần theo đúng thứ tự ban đầu cho ra `text(A)+text(B)==text(T)`.

Từ đó:

\[
text(insert(T,i,X))
=text(T[:i])\Vert X\Vert text(T[i:]).
\]

Và:

\[
text(delete(T,l,r))
=text(T[:l])\Vert text(T[r:]).
\]

**Điều kiện bắt buộc:** metadata length phải đúng sau mỗi lần sửa; chỉ một nút mang độ dài sai có thể khiến những lần truy cập và cắt sau đó đi **nhầm nhánh** dù các chunk nội dung chưa bị hỏng.

## 13. So sánh rope cổ điển và biến thể chunked implicit treap

Có nhiều cách hiện thực hóa một rope.

| Đặc điểm | Rope cổ điển lá chứa chunk | Rope dùng implicit treap có chunk tại nút |
|---|---|---|
| Nơi chứa ký tự | **Chỉ ở lá** | Mỗi nút có thể chứa một chunk không rỗng |
| Metadata định vị | `weight=length(left)` ở nút trong | `size=length(left)+len(chunk)+length(right)` |
| Quan hệ thứ tự | Thứ tự trái–phải trong cây | Thứ tự in-order, chỉ số ẩn |
| Cân bằng | Chọn AVL/weight-balanced/khác | Priority treap ngẫu nhiên |
| Ghép | Cần phép join thích hợp với cân bằng | `merge` theo priority ngẫu nhiên |
| Tách | Split theo trọng số | Split theo kích thước con trái và chunk |
| Độ cao | `O(\log m)` nếu bảo trì cân bằng | `O(\log m)` **kỳ vọng** với priority ngẫu nhiên độc lập |
| Worst-case | Tùy cấu trúc cân bằng | Có thể `O(m)` nếu priority xấu |

**Phần cài đặt Python của bài dùng phương án thứ hai** để thể hiện rõ các phép `split/merge` mà không phải triển khai một thuật toán **join AVL** phức tạp. Nó là **một biến thể rope dựa trên các đoạn**, không phải mô hình nút trong chỉ lưu `weight` như sơ đồ đầu bài.

Các ví dụ lý thuyết ban đầu sử dụng `weight` của rope cổ điển; khi đọc mã, hãy chú ý trường `size` đã **bao gồm độ dài chunk ngay tại nút**.

## 14. Implicit treap: dùng subtree size để mô phỏng chỉ số

Một **treap** kết hợp hai bất biến:

1. Thứ tự **in-order** của cây biểu diễn văn bản, không lưu khóa chỉ số tường minh.
2. Mỗi nút có `priority` ngẫu nhiên; cây duy trì **max-heap-order theo priority**:

\[
priority(parent)\ge priority(child).
\]

Ở biến thể chunked, một nút `v` có:

```text
v.chunk
v.priority
v.left
v.right
v.size
```

Bất biến độ dài:

\[
\boxed{
size(v)=size(v.left)+len(v.chunk)+size(v.right).
}
\]

Nhờ đó, khi tìm một chỉ số `i`:

```text
L = size(v.left)
C = len(v.chunk)

if i < L:              đi trái, giữ i
elif i < L + C:        ký tự nằm trong chunk, offset i-L
else:                  đi phải, offset i-L-C
```

### Vì sao ưu tiên ngẫu nhiên giúp cân bằng?

Khi các priority là những giá trị ngẫu nhiên độc lập, hình dạng treap có **chiều cao kỳ vọng logarithmic theo số nút**, tương tự BST ngẫu nhiên. Đó là nguồn gốc cận kỳ vọng của `split` và `merge`.

Tuy nhiên:

- Không có bảo đảm **worst-case `O(\log m)`** cho mọi lần gọi.
- Một chuỗi priority bất lợi có thể tạo cây cao `\Theta(m)`.
- Các bước Python đệ quy có thể chạm giới hạn recursion nếu cây cực lệch.
- Nếu cần độ trễ worst-case chặt, cân nhắc rope dùng AVL/weight-balanced tree hoặc thuật toán cân bằng có bảo đảm cụ thể.

## 15. MERGE của treap: ghép hai dãy có thứ tự trái–phải

Giả sử mọi chunk của `A` phải đứng **trước** mọi chunk của `B` trong văn bản kết quả.

```text
MERGE(A,B):
    if A is empty: return B
    if B is empty: return A

    if A.priority >= B.priority:
        A.right = MERGE(A.right, B)
        RECALC(A)
        return A
    else:
        B.left = MERGE(A, B.left)
        RECALC(B)
        return B
```

### Hai bất biến của MERGE

**Thứ tự văn bản:** nếu gốc `A` được giữ, mọi thứ trong `A.left + A.chunk` vẫn đứng trước `A.right` mới. `MERGE(A.right,B)` nối phần đuôi của `A` với toàn bộ `B`, nên:

\[
text(result)=text(A)\Vert text(B).
\]

**Heap-order theo priority:** nếu `A.priority\ge B.priority` thì `A` có priority không nhỏ hơn gốc của `MERGE(A.right,B)`. Đối với nhánh trái cũ, heap-order đã đúng từ trước. Trường hợp giữ gốc `B` đối xứng.

Thời gian là `O(h_A+h_B)` theo những đường được duyệt; trong mô hình treap ngẫu nhiên, `O(\log(m_A+m_B+1))` **kỳ vọng**, với chi phí sửa liên kết/metadata hằng số mỗi nút.

### MERGE không được chia sẻ nút sai quyền sở hữu

Phép `merge` viết bằng cách sửa trực tiếp các liên kết của nút. Nếu một nút vẫn được coi là thuộc hai rope **mutable độc lập**, sửa rope thứ nhất có thể làm rope thứ hai thay đổi không mong muốn.

Trong mã sẽ quy định `concat(other)` **chuyển quyền sở hữu**: rope nguồn `other` bị làm rỗng sau khi ghép. Đây là chính sách **destructive meld**, khác với persistent rope cần tạo phiên bản mới và dùng chia sẻ bất biến.

## 16. SPLIT của implicit treap: vị trí có thể rơi giữa một chunk

Với nút `v`:

```text
L = size(v.left)
C = len(v.chunk)
```

Tách theo `k` ký tự đầu:

1. `k<L`: biên nằm trong cây trái; split cây trái rồi cập nhật liên kết.
2. `k>L+C`: biên nằm trong cây phải; split cây phải tại `k-L-C`.
3. `k=L`: tách riêng `v.left`; phần còn lại bắt đầu từ `v.chunk`.
4. `k=L+C`: phần trái kết thúc tại `v.chunk`; tách riêng cây phải.
5. `L<k<L+C`: biên nằm **giữa chunk**; chia chunk thành hai mảnh rồi ghép với các cây trái/phải cũ.

### Ví dụ giữa chunk

```text
v.chunk = "ABCDE"
size(v.left) = 3
k = 5

offset trong chunk = k - size(left) = 2
split chunk:
    "AB" | "CDE"

Kết quả:
    left_tree + "AB"
    "CDE" + right_tree
```

Nếu `B` là độ dài chunk tối đa và biểu diễn chuỗi bất biến, phần sao chép hai lát cắt có thể tốn `O(B)` ký tự.

### Tại sao không thể luôn split trong O(log m) theo số ký tự?

Khi biên rơi giữa một chunk dài hàng triệu ký tự, tạo hai chuỗi bất biến mới cần xử lý các ký tự ấy. Rope chỉ có lợi thế rõ ràng khi **chunk đủ nhỏ** hoặc có cơ chế **lát cắt tham chiếu vào bộ đệm gốc** thay vì sao chép.

Vì vậy, với chunk tối đa `B`, **một thuật toán split treap tối ưu** có thể đạt cận:

\[
\boxed{\text{split}=O(\log(m+1)+B)\ \text{kỳ vọng}}
\]

trong mô hình ngẫu nhiên với triển khai split duy trì heap-order hiệu quả. **Mã giảng dạy phía dưới** chọn cách `merge` lại các nhánh khi trả về từ split để dễ chứng minh đúng đắn; do có thể phải merge ở nhiều tầng, ta dùng cận bảo thủ **`O(\log^2(m+1)+B)` kỳ vọng** cho riêng mã này, không nhận nó là triển khai tối ưu.

## 17. Python: nút rope, subtree size và phép merge

Sau đây là một cài đặt Python mang tính **minh họa nhưng có thể chạy độc lập**. Ta dùng:

- `str` chứa chunk (tính chiều dài theo **Unicode code point** của Python).
- `size` là tổng số code point trong toàn bộ cây con.
- `priority` là số ngẫu nhiên, giữ heap-order của treap.
- `left` và `right` là hai nhánh lưu những chunk trước/sau.

Đặt tất cả các khối mã từ phần 17 đến 19 **theo thứ tự** trong một tệp Python. Ví dụ không phụ thuộc thư viện ngoài chuẩn Python.

### 17.1. Nút và hàm bảo trì kích thước

```python
from __future__ import annotations

from dataclasses import dataclass, field
import random


@dataclass
class Node:
    chunk: str
    priority: int = field(
        default_factory=lambda: random.getrandbits(128)
    )
    left: Node | None = None
    right: Node | None = None
    size: int = field(init=False)

    def __post_init__(self) -> None:
        if not self.chunk:
            raise ValueError("Node phải có chunk không rỗng")
        self.size = len(self.chunk)


def node_size(node: Node | None) -> int:
    return 0 if node is None else node.size


def recalc(node: Node) -> None:
    node.size = (
        node_size(node.left)
        + len(node.chunk)
        + node_size(node.right)
    )
```

**Điểm cần phân biệt:** `size` của một nút trong biến thể này **bao gồm chunk ngay tại nút**, không phải chỉ riêng cây trái như `weight` của rope cổ điển.

### 17.2. Merge hai cây theo thứ tự văn bản

```python
def merge(a: Node | None, b: Node | None) -> Node | None:
    """Ghép tất cả chunk của a đứng trước mọi chunk của b."""
    if a is None:
        return b
    if b is None:
        return a

    if a.priority >= b.priority:
        a.right = merge(a.right, b)
        recalc(a)
        return a

    b.left = merge(a, b.left)
    recalc(b)
    return b
```

Không sao chép toàn bộ văn bản của `a` và `b`. Hàm chỉ sửa liên kết trên những nhánh được duyệt. Thứ tự in-order luôn là:

```text
Tất cả chunk của a, rồi tất cả chunk của b.
```

**Tính đúng của heap-order:** gốc có priority lớn hơn giữ vai trò cha; sau khi merge đệ quy vào nhánh tương ứng, gọi `recalc` để cập nhật `size`. Khi treap có priority ngẫu nhiên độc lập và ít va chạm, chiều cao là `O(\log m)` kỳ vọng.

### 17.3. Xây rope từ một chuỗi lớn

```python
def build_chunks(text: str, chunk_size: int) -> Node | None:
    """Chia text thành các chunk dài tối đa chunk_size."""
    root = None
    for start in range(0, len(text), chunk_size):
        piece = text[start : start + chunk_size]
        root = merge(root, Node(piece))
    return root
```

Đặt `q=\lceil|text|/B\rceil` là số chunk của chuỗi không rỗng, với `B=chunk_size`. Bản minh họa này xây bằng `q` lần gọi merge, nên cận bảo thủ là `O(|text|+q\log(q+1))` **kỳ vọng**. Có thể xây treap từ một chuỗi priority bằng thuật toán stack tuyến tính `O(q)` theo số nút, nhưng không cần tối ưu đó để hiểu các phép chỉnh sửa.

Không được nói `build_chunks` chỉ mất `O(\log q)` khi bản thân nó phải chia và nhận `|text|` ký tự.

## 18. Python: SPLIT theo số ký tự đầu

Hàm `split(root,k)` trả một cặp cây biểu diễn `text[:k]` và `text[k:]`. Đầu vào phải thỏa `0\le k\le node_size(root)`; lớp công khai sẽ kiểm tra điều kiện ấy.

```python
def split(
    node: Node | None, k: int
) -> tuple[Node | None, Node | None]:
    """Chia theo k code point đầu; sửa các nút theo ownership."""
    if node is None:
        return None, None

    left_size = node_size(node.left)
    chunk_len = len(node.chunk)

    if k < left_size:
        a, b = split(node.left, k)
        node.left = None
        recalc(node)
        # b có thể chứa chunk mới có priority cao hơn node.
        # Merge bảo toàn heap-order thay vì nối b trực tiếp.
        return a, merge(b, node)

    if k > left_size + chunk_len:
        a, b = split(
            node.right, k - left_size - chunk_len
        )
        node.right = None
        recalc(node)
        # a có thể chứa chunk mới có priority cao hơn node.
        return merge(node, a), b

    # Biên rơi TRƯỚC toàn bộ chunk hiện tại.
    if k == left_size:
        a = node.left
        node.left = None
        recalc(node)
        return a, node

    # Biên rơi SAU toàn bộ chunk hiện tại.
    if k == left_size + chunk_len:
        b = node.right
        node.right = None
        recalc(node)
        return node, b

    # Biên nằm BÊN TRONG chunk.
    cut = k - left_size
    before = Node(node.chunk[:cut])
    after = Node(node.chunk[cut:])

    # Nối các cây đã có với hai chunk mới.
    a = merge(node.left, before)
    b = merge(after, node.right)

    # Node cũ không còn thuộc hai kết quả.
    node.left = None
    node.right = None
    return a, b
```

### Vì sao không cần sao chép các cây con nguyên vẹn?

Khi biên ở trong `node.chunk`, ta tạo **hai chunk mới**. Các cây `node.left` và `node.right` được tái sử dụng trực tiếp bằng `merge`, không dựng lại tất cả hậu duệ. Chỉ văn bản trong chunk bị cắt cần chia/copy.

### Những điều cần giữ sau split

1. `text(a)+text(b)==text(root_cũ)`.
2. `node_size(a)==k` và `node_size(b)==n-k`.
3. `size` đúng tại **mọi nút** trong cả hai cây.
4. Heap-order theo `priority` vẫn đúng trong mỗi kết quả, **kể cả khi hai chunk mới nhận priority cao hơn tổ tiên cũ**.
5. Hai cây kết quả **không dùng chung nút mutable** trong phiên bản này.

Mã dùng recursion và ngẫu nhiên để tập trung vào ý tưởng; nếu chuỗi thao tác có khả năng gây chiều cao bất lợi, nên dùng cấu trúc có cân bằng worst-case hoặc thêm biện pháp giới hạn độ sâu trong sản phẩm thực tế.

## 19. Python: API Rope đầy đủ

Lớp sau triển khai:

- `len(rope)`, `rope.char_at(i)`.
- `rope.insert(i,text)`, `rope.delete(l,r)`, `rope.replace(l,r,text)`.
- `rope.substring(l,r)` chỉ đọc, trả `str`.
- `rope.split_at(k)` trả hai rope mới và **làm rỗng rope nguồn**.
- `rope.concat(other)` nối hai rope, **làm rỗng rope `other`**.
- `rope.to_string()` vật chất hóa toàn bộ văn bản.
- `rope.check_invariants()` kiểm tra metadata và giới hạn chunk (dành cho học tập/debug).

### 19.1. Duyệt chuỗi con mà không sửa cây

```python
def collect_range(
    node: Node | None,
    start: int,
    end: int,
    parts: list[str],
) -> None:
    """Lấy đoạn [start,end) theo chỉ số trong cây node."""
    if node is None or start >= end:
        return

    left_size = node_size(node.left)
    middle_end = left_size + len(node.chunk)

    if start < left_size:
        collect_range(
            node.left, start, min(end, left_size), parts
        )

    chunk_start = max(0, start - left_size)
    chunk_end = min(len(node.chunk), end - left_size)
    if chunk_start < chunk_end:
        parts.append(node.chunk[chunk_start:chunk_end])

    if end > middle_end:
        collect_range(
            node.right,
            max(0, start - middle_end),
            end - middle_end,
            parts,
        )
```

**Lưu ý:** `collect_range` tạo các lát cắt `str` mới trong Python. Nếu muốn API trả **một rope con không sao chép toàn bộ ký tự**, cần thiết kế chia sẻ chunk bất biến hoặc cấu trúc persistent phù hợp; việc trả `str` phẳng yêu cầu vật chất hóa kết quả.

### 19.2. Các thao tác công khai

```python
class Rope:
    def __init__(self, text: str = "", chunk_size: int = 256):
        if chunk_size < 1:
            raise ValueError("chunk_size phải >= 1")
        self.chunk_size = chunk_size
        self.root = build_chunks(text, chunk_size)

    def __len__(self) -> int:
        return node_size(self.root)

    @classmethod
    def _from_root(
        cls, root: Node | None, chunk_size: int
    ) -> Rope:
        result = cls(chunk_size=chunk_size)
        result.root = root
        return result

    def _require_position(self, index: int) -> None:
        if not 0 <= index <= len(self):
            raise IndexError("Vị trí phải nằm trong [0,len]")

    def _require_range(self, start: int, end: int) -> None:
        if not 0 <= start <= end <= len(self):
            raise IndexError("Khoảng [start,end) không hợp lệ")

    def char_at(self, index: int) -> str:
        if not 0 <= index < len(self):
            raise IndexError("Chỉ số ký tự ngoài miền")

        node = self.root
        while node is not None:
            left_size = node_size(node.left)
            chunk_end = left_size + len(node.chunk)
            if index < left_size:
                node = node.left
            elif index < chunk_end:
                return node.chunk[index - left_size]
            else:
                index -= chunk_end
                node = node.right
        raise RuntimeError("Metadata size không nhất quán")

    def insert(self, index: int, text: str) -> None:
        self._require_position(index)
        if not text:
            return
        left, right = split(self.root, index)
        middle = build_chunks(text, self.chunk_size)
        self.root = merge(merge(left, middle), right)

    def delete(self, start: int, end: int) -> None:
        self._require_range(start, end)
        if start == end:
            return
        left, tail = split(self.root, start)
        removed, right = split(tail, end - start)
        self.root = merge(left, right)
        # removed không còn thuộc rope; Python quản lý vòng đời.
        del removed

    def replace(self, start: int, end: int, text: str) -> None:
        self._require_range(start, end)
        self.delete(start, end)
        self.insert(start, text)

    def substring(self, start: int, end: int) -> str:
        self._require_range(start, end)
        parts: list[str] = []
        collect_range(self.root, start, end, parts)
        return "".join(parts)

    def split_at(self, index: int) -> tuple[Rope, Rope]:
        """Chuyển ownership sang hai Rope mới; self rỗng."""
        self._require_position(index)
        left, right = split(self.root, index)
        self.root = None
        return (
            Rope._from_root(left, self.chunk_size),
            Rope._from_root(right, self.chunk_size),
        )

    def concat(self, other: Rope) -> None:
        """Ghép vào self; other rỗng sau thao tác."""
        if self is other:
            raise ValueError("Không thể concat rope với chính nó")
        if self.chunk_size != other.chunk_size:
            raise ValueError("Hai rope phải dùng cùng chunk_size")
        self.root = merge(self.root, other.root)
        other.root = None

    def to_string(self) -> str:
        parts: list[str] = []

        def visit(node: Node | None) -> None:
            if node is None:
                return
            visit(node.left)
            parts.append(node.chunk)
            visit(node.right)

        visit(self.root)
        return "".join(parts)

    def check_invariants(self) -> bool:
        def visit(node: Node | None) -> int:
            if node is None:
                return 0

            assert 1 <= len(node.chunk) <= self.chunk_size
            if node.left is not None:
                assert node.priority >= node.left.priority
            if node.right is not None:
                assert node.priority >= node.right.priority

            left = visit(node.left)
            right = visit(node.right)
            expected = left + len(node.chunk) + right
            assert node.size == expected
            return expected

        try:
            return visit(self.root) == len(self)
        except AssertionError:
            return False
```

### Vì sao `split_at` và `concat` làm rỗng rope nguồn?

`merge` và `split` ở đây **sửa trực tiếp nút cũ**. Nếu `self` và `other` tiếp tục cùng sở hữu các nút đã nối vào một cây, việc thay một bên sẽ ảnh hưởng bên kia; thậm chí có thể hình thành liên kết sai sau lần chỉnh sửa tiếp theo.

Để tránh aliasing không chủ ý, API quy định một **chủ sở hữu mutable** cho mỗi nút:

- `split_at` chuyển các nút từ `self` sang hai rope trả về.
- `concat` chuyển toàn bộ nút từ `other` sang `self`.

Đây là giao ước minh họa, **không phải persistent rope** và cũng không chứng minh an toàn thread hay exception-safety của một thư viện production.

### Các giới hạn có chủ ý

1. `random.getrandbits(128)` tạo priority ngẫu nhiên; cận chiều cao là **kỳ vọng**, không worst-case. Đây không phải giải pháp mật mã hay chống input đối kháng hoàn chỉnh.
2. Trong một triển khai thật, các lần cấp phát chunk/Node có thể thất bại giữa lúc sửa cây; mã học thuật không triển khai rollback giao dịch khi xảy ra `MemoryError`.
3. `check_invariants` duyệt toàn cây trong `O(m)`; không nên tự gọi sau mỗi thao tác production.
4. Không tự hợp nhất các chunk quá nhỏ sau chỉnh sửa; số nút có thể tăng qua nhiều lần cắt.
5. Không hỗ trợ snapshot bất biến hoặc chia sẻ nút giữa hai phiên bản văn bản mutable.
6. Các chỉ số là **code point của Python `str`**, không phải byte UTF-8 hay grapheme hiển thị.

## 20. Chạy ví dụ: ghép, cắt, chèn, xóa và truy cập

Các đoạn sau sử dụng lớp và hàm đã định nghĩa trong phần 17–19.

```python
rope = Rope("ABCDE", chunk_size=3)
assert rope.to_string() == "ABCDE"
assert len(rope) == 5
assert rope.char_at(0) == "A"
assert rope.char_at(4) == "E"
assert rope.check_invariants()

rope.insert(2, "--")
print(rope.to_string())            # AB--CDE
assert rope.substring(2, 4) == "--"
assert rope.check_invariants()

rope.delete(2, 4)
print(rope.to_string())            # ABCDE
assert rope.check_invariants()

rope.replace(1, 3, "XY")
print(rope.to_string())            # AXYDE
assert rope.check_invariants()

left, right = rope.split_at(3)
print(left.to_string())            # AXY
print(right.to_string())           # DE
print(len(rope))                   # 0: nguồn chuyển ownership.

left.concat(right)
print(left.to_string())            # AXYDE
print(len(right))                  # 0: nguồn của concat rỗng.
assert left.check_invariants()
```

### Kiểm tra các trường hợp biên

```python
empty = Rope("", chunk_size=3)
assert len(empty) == 0
assert empty.to_string() == ""
assert empty.substring(0, 0) == ""
assert empty.check_invariants()

empty.insert(0, "Hi")
assert empty.to_string() == "Hi"

before, after = empty.split_at(0)
assert before.to_string() == ""
assert after.to_string() == "Hi"
assert len(empty) == 0

after.delete(0, len(after))
assert after.to_string() == ""
assert after.check_invariants()
```

**Không chạy kiểm thử trong phạm vi biên soạn bài:** các ví dụ này được cung cấp để người học tự ghép thành một tệp Python, thực thi và tự mở rộng. Phần kiểm tra chuyên sâu và xác thực thuật toán là bước học thuật riêng.

## 21. Phân tích độ phức tạp một cách trung thực

Phải phân biệt:

- `n`: **tổng số code point** trong rope.
- `m`: **số nút chứa chunk**.
- `B`: **độ dài tối đa của một chunk**.
- `q`: số chunk mới khi đưa đoạn văn bản dài `L` vào, `q=\lceil L/B\rceil` (với `L>0`).
- `h`: chiều cao cây thực tế; với treap priority ngẫu nhiên độc lập, `E[h]=O(\log(m+1))` trong mô hình thông thường.

| Thao tác | Chi phí với cây cao `h` | Trên implicit treap ngẫu nhiên |
|---|---|---|
| `len(rope)` | `O(1)` | `O(1)` |
| `char_at(i)` | `O(h)` | `O(\log(m+1))` kỳ vọng |
| `concat(other)` | `O(h_1+h_2)` trên các đường merge | `O(\log(m_1+m_2+1))` kỳ vọng |
| `split_at(k)` | `O(h^2+B)` cận bảo thủ do có thể merge khi trả về từ nhiều tầng | `O(\log^2(m+1)+B)` kỳ vọng, cận bảo thủ cho mã mẫu |
| `delete(l,r)` | `O(h^2+B)` cho sửa cấu trúc, chưa tính thu hồi nút | `O(\log^2(m+1)+B)` kỳ vọng, cận bảo thủ |
| `insert(i,text)` | Split/join + xây rope cho đoạn chèn | `O(\log^2(m+q+1)+B+L+q\log(q+1))` kỳ vọng, cận bảo thủ cho mã mẫu |
| `substring(l,r)` trả `str` | `O(h+t+k)` với `t` chunk được duyệt, `k` ký tự xuất | `O(\log(m+1)+t+k)` kỳ vọng |
| `to_string()` | `O(n+m)` | `O(n+m)` |
| `check_invariants()` | `O(m)` | `O(m)` |

**Cần đọc bảng đúng cách:**

1. `split_at` có thể sao chép một chunk dài tối đa `B`. Mã mẫu dùng lại `merge` khi quay ngược đệ quy để giữ **heap-order của priority mới**; một thuật toán split treap chuyên biệt có thể tránh phần merge lặp và đạt `O(\log m+B)` kỳ vọng. Nếu dùng **slice tham chiếu vào buffer bất biến** thay cho `str` được cắt mới, chi phí ký tự cũng có thể khác.
2. `delete` chỉ tính sửa liên kết ở đây; trong một runtime giải phóng tức thời theo ref-count hoặc destructor phức tạp, **thu hồi cả đoạn bị loại** có thể gây chi phí tỷ lệ với số nút bị xóa.
3. `insert` không thể bỏ qua `L` ký tự đầu vào. Mã xây treap bằng nhiều lần merge nên chi phí có thêm `q\log q` kỳ vọng; một bản cài xây treap tuyến tính theo số chunk có thể cải thiện hạng này.
4. `substring` trả **chuỗi mới** nên luôn phải trả giá cho việc xuất `k` ký tự.
5. Các cận logarithmic của treap là **kỳ vọng**, không tự đổi thành cận xấu nhất.
6. Nếu không cân bằng, `h` có thể `\Theta(m)`; khi mỗi chunk rất nhỏ, `m` có thể cùng cấp với `n`.

### Đánh đổi bộ nhớ

Rope lưu tổng cộng `O(n)` ký tự và `O(m)` metadata nút, nên bộ nhớ tiệm cận **`O(n+m)`** với chunk không rỗng, thường viết `O(n)` nếu mỗi nút đóng góp ít nhất một đơn vị ký tự. Nhưng hằng số bộ nhớ gồm:

- `left`/`right`, `priority`, `size`.
- Metadata đối tượng Python và bộ cấp phát.
- Dung lượng của từng đối tượng `str` nhỏ.
- Các cấu trúc tạm khi split, join, đọc chuỗi con hoặc quản lý phiên bản.

Do đó, **rope không nhất thiết dùng ít RAM hơn một chuỗi phẳng**. Lợi thế chính của nó nằm ở **sửa nhiều đoạn trên văn bản lớn mà không phải sao chép toàn bộ văn bản sau mỗi lần sửa**.

## 22. Unicode: “ký tự thứ i” không phải lúc nào cũng hiển nhiên

Trong văn bản tiếng Việt và các ngôn ngữ dùng Unicode, “độ dài chuỗi” có ít nhất ba cách hiểu:

| Đơn vị | Ví dụ ý nghĩa | Điều cần chú ý |
|---|---|---|
| **Byte UTF-8** | Dung lượng khi lưu hoặc truyền | Một code point có thể chiếm nhiều byte |
| **Unicode code point** | Các phần tử mà `len(str)` và `str[i]` thường dùng trong Python | Một ký tự hiển thị có thể gồm nhiều code point |
| **Grapheme cluster** | Một đơn vị người dùng thường xem là một ký tự | Có thể gồm chữ cơ sở, dấu kết hợp hoặc nhiều emoji |

### Ví dụ cùng hiển thị một ký tự nhưng nhiều code point

```python
composed = "á"        # U+00E1
decomposed = "a\u0301" # 'a' + combining acute accent

print(len(composed))    # 1 code point
print(len(decomposed))  # 2 code point
print(composed == decomposed)  # False nếu chưa chuẩn hóa
```

Hai chuỗi có thể **trông giống nhau** với người đọc, nhưng vị trí cắt theo code point khác nhau. Nếu split `decomposed` tại `1`, bạn có thể tách chữ `a` khỏi dấu kết hợp.

### Emoji và các hệ sinh thái khác

```python
face = "🙂"
print(len(face))                     # 1 code point trong Python.
print(len(face.encode("utf-8")))     # 4 byte UTF-8.
```

Trong một hệ sinh thái dùng **UTF-16 code unit** để đánh chỉ số chuỗi, một emoji ngoài Basic Multilingual Plane có thể chiếm **hai code unit**. Với các emoji ghép bằng *zero-width joiner*, một hình hiển thị có thể gồm **nhiều code point**.

### Thiết kế rope đúng yêu cầu

1. **Chọn đơn vị chỉ số chính thức**: UTF-8 byte offset, code point index, UTF-16 code unit hay grapheme index.
2. **Duy trì metadata theo đúng đơn vị** ấy; không trộn `len(bytes)` với `len(str)` trong phép `split`.
3. **Không cắt giữa một đơn vị nguyên tử** của chính sách đã chọn. Với byte-based rope UTF-8, không được tạo chuỗi con UTF-8 độc lập bắt đầu giữa một chuỗi byte của code point.
4. Nếu editor cần con trỏ “theo ký tự hiển thị”, cần thêm thuật toán phân đoạn grapheme theo chuẩn Unicode phù hợp, không chỉ đọc `str[i]`.
5. Nếu có chuẩn hóa Unicode như NFC/NFD, phải xác định thời điểm chuẩn hóa vì việc chuẩn hóa có thể thay đổi độ dài theo code point.

**Mã Python của bài** sử dụng **code point index** theo `str`. Nó đúng theo hợp đồng ấy nhưng **không tự bảo đảm split tại ranh giới grapheme**.

## 23. Chỉ số byte, số dòng và cột: metadata có thể mở rộng

Đối với trình soạn thảo mã nguồn, ngoài hỏi ký tự theo vị trí, ta còn muốn:

- “Dòng số `k` bắt đầu ở vị trí nào?”
- “Từ offset `i`, số dòng/cột tương ứng là gì?”
- “Một đoạn văn bản có bao nhiêu ký tự xuống dòng?”

Một ý tưởng là bổ sung:

```text
node.size          # Tổng số đơn vị chỉ số trong cây con.
node.newline_count # Tổng số '\n' trong cây con.
```

Với biến thể chunked:

\[
newlines(v)=newlines(v.left)+count_{\text{'\textbackslash n'}}(v.chunk)+newlines(v.right).
\]

Nếu lưu sẵn số xuống dòng của **chunk** tại mỗi nút, metadata cây con có thể cập nhật bằng `O(1)` phép cộng sau mỗi lần sửa liên kết, bên cạnh việc tính số xuống dòng cho chunk **mới/chỉnh sửa**.

### Tìm dòng thứ k

Để tìm ký tự xuống dòng thứ `k`:

1. Xem `newlines(left)` của cây trái.
2. Nếu `k` nằm trong cây trái, rẽ trái.
3. Nếu nằm trong chunk hiện tại, tìm ký tự xuống dòng tương ứng **bên trong chunk**.
4. Nếu nằm bên phải, trừ số xuống dòng cây trái và chunk rồi rẽ phải.

Với cây cân bằng, phần đi theo nút mất `O(\log m)`; tìm vị trí xuống dòng trong chunk có thể tốn `O(B)` nếu quét tuyến tính. Có thể lưu thêm bảng vị trí newline trong chunk nếu truy vấn dày đặc.

### Cột không chỉ là số code point

Một tab có thể chiếm nhiều ô hiển thị; một grapheme có thể gồm nhiều code point; ký tự East Asian có thể chiếm bề rộng hiển thị khác nhau. Vì vậy, **số code point từ đầu dòng** không luôn là **cột vẽ trên màn hình**.

Metadata rope có thể giúp tìm dòng nhanh, nhưng **layout/rendering** là một bài toán riêng, có thể phụ thuộc font, kích thước cửa sổ và cách xuống dòng mềm (*soft wrap*).

## 24. Rope mutable và rope persistent: hai hợp đồng khác nhau

### 24.1. Mutable rope

Các thao tác `insert`, `delete`, `merge` của ví dụ **sửa trực tiếp liên kết**. Sau khi `concat(A,B)`, `B` không còn sở hữu các nút đã chuyển. Ưu điểm:

- Ít phải cấp phát bản sao các nút trên đường sửa.
- Logic phù hợp khi một tài liệu chỉ có một trạng thái đang chỉnh sửa.
- Có thể giải phóng các chunk/nút không còn được dùng.

Nhược điểm:

- Không thể an toàn giữ nhiều “phiên bản” bằng cách chỉ lưu nhiều con trỏ gốc tới **cùng những nút mutable**.
- Snapshot có thể bị thay đổi ngoài ý muốn sau lần sửa tiếp theo.
- Cần quy tắc ownership và đồng bộ rõ ràng.

### 24.2. Persistent rope

Một **persistent rope** lưu các nút như cấu trúc **bất biến**. Khi tạo phiên bản mới:

1. Sao chép những nút trên các đường bị thay đổi (*path copying*).
2. Tái sử dụng **các cây con không bị sửa** bằng chia sẻ an toàn.
3. Trả về **gốc mới** mà không thay đổi gốc cũ.

Ví dụ:

```text
Version 1:
    "ABCDEF"

Version 2 sau insert(3, "--"):
    "ABC--DEF"

Hai version có thể chia sẻ các cây con của "ABC" hoặc "DEF"
nếu chúng bất biến và giao thức join/split hỗ trợ chia sẻ.
```

Lợi ích là xây dựng **undo/redo**, snapshot và truy vấn các phiên bản lịch sử mà không sao chép toàn bộ văn bản mỗi lần sửa.

### Chi phí của persistence

- Cần cấp phát các nút mới trên đường bị đổi, thường `O(h)` nút cho một đường tìm, cộng những nút để tái cấu trúc; với cây cân bằng là mức logarithmic theo `m`.
- Các version còn sống giữ các cây con cũ trong bộ nhớ; bộ nhớ tổng có thể tăng theo **số và hình dạng các lần sửa**.
- Phải quản lý tham chiếu/garbage collection để thu hồi các cây con không còn version nào dùng.
- Các chunk phải được **bất biến** hoặc có copy-on-write, nếu không sửa chunk chia sẻ sẽ làm hỏng snapshot.

**Cảnh báo:** đừng dùng `copy.copy(rope)` với mã mutable trong bài rồi gọi đó là persistent rope. Bản sao nông có thể chia sẻ gốc/nút đang bị sửa, vi phạm độc lập giữa hai phiên bản.

## 25. Undo/redo: dùng phiên bản hoặc nhật ký thao tác

Một editor có thể hỗ trợ hoàn tác theo ít nhất hai cách.

### Cách A — persistent versions

```text
versions = [root0, root1, root2, ...]
current = version_index
```

Mỗi lần sửa tạo một gốc mới, còn gốc cũ vẫn tồn tại. Undo/redo đổi chỉ số version. Cách này đơn giản về truy cập snapshot nhưng cần cấu trúc bất biến và chiến lược giữ/thu hồi version.

### Cách B — operation log trên mutable rope

Với mỗi thao tác, lưu **thao tác nghịch đảo**:

```text
insert(i, "abc")
  -> inverse: delete(i, i+3)

delete(l,r) với removed_text="xyz"
  -> inverse: insert(l, "xyz")
```

Đối với delete, cần ghi lại **nội dung đã xóa** hoặc giữ một cây con tương ứng, chứ không thể khôi phục từ vị trí `l,r` đơn thuần.

Trong mã học thuật có thể lấy `removed_text=substring(l,r)` trước khi xóa; điều này sao chép `r-l` ký tự. Một hệ thống phức tạp hơn có thể chuyển ownership của cây con bị cắt sang undo log để tránh sao chép ký tự.

### Vấn đề thay đổi tọa độ

Nếu các thao tác đến từ nhiều người dùng hoặc nhiều phiên bản tài liệu, chỉ số `i` của một thao tác cũ có thể **không còn trỏ cùng vị trí** sau các chỉnh sửa khác. Rope **không tự giải quyết** bài toán hợp nhất thao tác cộng tác; cần một giao thức đồng bộ riêng như OT/CRDT hoặc một mô hình phiên bản/neo vị trí thích hợp.

## 26. So sánh rope với chuỗi phẳng, gap buffer và piece table

| Cấu trúc | Tư tưởng | Điểm mạnh | Hạn chế |
|---|---|---|---|
| **Chuỗi phẳng** (*flat string*) | Một vùng dữ liệu liên tiếp | Duyệt tuần tự và truy cập theo chỉ số thuận lợi | Chèn/xóa giữa có thể cần `O(n)` sao chép/dời |
| **Mảng động ký tự** | Vùng liên tiếp có sức chứa dự phòng | Append cuối thường `O(1)` khấu hao | Chèn giữa dời hậu tố |
| **Gap buffer** | Một mảng có khoảng trống gần con trỏ | Nhiều chỉnh sửa gần một vị trí nhanh | Di chuyển gap xa có thể tốn `O(n)` |
| **Piece table** | Giữ buffer gốc và buffer thêm; tài liệu là danh sách “mảnh” tham chiếu | Hạn chế sao chép dữ liệu gốc, thuận tiện lịch sử | Tìm vị trí nhanh cần chỉ mục cây; quản lý pieces/versions |
| **Rope cân bằng** | Cây các chunk, metadata độ dài cây con | Ghép–cắt–chèn–xóa theo vị trí mà không sao chép toàn bộ hậu tố | Con trỏ, allocator, cache, rebalance/chunk maintenance |
| **Danh sách liên kết ký tự/đoạn** | Nối các nút tuần tự | Chèn tại nút đã biết thuận lợi | Truy cập theo vị trí số có thể `O(n)` |
| **B-tree dạng rope** | Nhiều con/chunk trong mỗi nút, metadata tích lũy | Giảm độ sâu và cải thiện locality trong một số thiết kế | Cài split/merge/rebalance phức tạp hơn |

### Một người dùng soạn thảo chủ yếu tại một chỗ

**Gap buffer** có thể rất hiệu quả vì cursor ít di chuyển, khoảng trống sẵn có giúp chèn/xóa gần con trỏ rẻ. Rope không tự động thắng trường hợp này.

### Một tài liệu rất dài với nhiều vùng chỉnh sửa

Rope hoặc piece table có chỉ mục cây có thể phù hợp: các đoạn chưa bị tác động được tái sử dụng; không cần dời phần lớn văn bản sau mỗi lần sửa.

### Văn bản được xử lý tuần tự và gần như bất biến

Một chuỗi phẳng có thể đơn giản, ít metadata và nhanh hơn nhờ cache locality. Đừng chọn rope chỉ vì văn bản “dài” nếu workload chủ yếu là đọc tuần tự một lần.

## 27. Ranh giới chunk, tìm kiếm và sao chép dữ liệu

### Tìm kiếm mẫu có thể đi qua ranh giới chunk

Giả sử rope có các chunk:

```text
["ab"] ["cd"]
```

Văn bản logic là `"abcd"`. Mẫu `"bc"` **tồn tại**, dù không xuất hiện trọn trong chunk nào. Nếu áp `chunk.find("bc")` riêng từng chunk rồi kết luận “không có”, chương trình sai.

Các lựa chọn:

- Vật chất hóa toàn bộ chuỗi rồi tìm: đơn giản, nhưng thêm `O(n)` bộ nhớ.
- Duyệt chunk tuần tự và dùng một thuật toán tìm kiếm **có trạng thái xuyên ranh giới** như KMP, hoặc bộ đệm giao nhau đủ dài.
- Bổ sung metadata/chỉ mục văn bản chuyên biệt nếu tìm kiếm lặp rất nhiều.

Với KMP, một lần quét toàn văn bản có thể `O(n+p)` theo số ký tự và độ dài mẫu `p`, không cần flatten toàn bộ nếu triển khai bộ duyệt streaming.

### Số byte được sao chép mới là chỉ số quan trọng

Một thao tác split/concat có thể chỉ sửa `O(\log m)` nút, nhưng:

- Cắt giữa chunk `str` bất biến vẫn sao chép ký tự của chunk.
- Tạo `str` đầu ra từ `substring` phải sao chép phần yêu cầu.
- Gộp chunk nhỏ sau nhiều chỉnh sửa cũng có thể sao chép lại nội dung.
- Nếu editor thường xuyên tạo cả chuỗi để vẽ lại màn hình, chi phí flatten có thể chi phối.

Vì thế, khi benchmark rope, ngoài thời gian, nên đo **số byte sao chép**, số nút cấp phát, peak memory, chiều cao cây và số chunk.

## 28. Cập nhật metadata khác: số dòng, hash và định vị nhanh

Rope là **cây tăng cường**, nên ngoài `size` còn có thể lưu:

| Metadata | Mục tiêu | Cách kết hợp thường gặp |
|---|---|---|
| `length` | Tìm ký tự/split theo vị trí | Cộng độ dài |
| `newline_count` | Định vị dòng thứ k | Cộng số xuống dòng |
| `hash` và `length` | So sánh nhanh tóm tắt đoạn | Rolling hash phụ thuộc thứ tự |
| `byte_length` | Chuyển giữa code point và UTF-8 byte | Cộng byte của chunk |
| `grapheme_count` | Chỉ số theo ký tự hiển thị | **Không luôn cộng đơn giản** khi grapheme có thể ghép qua ranh giới |
| `summary style/layout` | Phục vụ định dạng | Phụ thuộc kiểu tổng hợp và ngữ cảnh |

### Cần thận trọng với grapheme_count

Nếu một chunk kết thúc bằng chữ `"a"` và chunk tiếp theo bắt đầu bằng dấu kết hợp `"\u0301"`, khi nối hai chunk chúng có thể tạo thành **một grapheme hiển thị**. Khi ấy:

```text
graphemes(left) + graphemes(right)
```

không nhất thiết bằng `graphemes(left + right)` nếu chỉ lưu một số đếm đơn giản và không có thông tin trạng thái biên. Một augmentation đúng có thể cần **metadata ngữ cảnh ở đầu/cuối chunk** hoặc một thuật toán phân đoạn Unicode có khả năng ghép kết quả.

Tương tự, rolling hash chuỗi không giao hoán: `hash(A+B)` thường khác `hash(B+A)`. Nếu xây metadata cho phép nối, phải giữ **thứ tự in-order**.

## 29. Lựa chọn cân bằng và chiến lược chunk trong sản phẩm thật

Một rope production phải chọn đồng thời **chiến lược cây** và **chiến lược chunk**.

### Cân bằng chiều cao

AVL hoặc red-black tree (có thuật toán join/split thích hợp) cho bảo đảm chiều cao logarithmic trong trường hợp xấu nhất. Nhưng không thể chỉ lấy mã xoay AVL cho BST theo khóa rồi chèn nguyên vào rope mà không bảo trì **trọng số độ dài** và thứ tự lá sau mỗi phép nối/cắt.

### Cân bằng theo trọng số

Một số rope cân bằng theo **kích thước/khối lượng của cây con**, thay vì chỉ theo số nút. Điều này có thể giúp kiểm soát sự phân bố ký tự, đặc biệt khi các chunk dài ngắn khác nhau. Tuy nhiên, muốn phát biểu cận worst-case phải có **điều kiện cân bằng chính xác** và thuật toán sửa tương ứng.

### Treap ngẫu nhiên

Mã trong bài dùng `priority` ngẫu nhiên, cho height `O(\log m)` **kỳ vọng**. Mã đơn giản nhưng không thích hợp với yêu cầu **worst-case latency cứng** nếu không có biện pháp bổ sung.

### Chunk size và compaction

Nếu chunk quá lớn, split giữa chunk đắt; nếu quá nhỏ, có nhiều nút và overhead. Trong ứng dụng thường:

1. Đặt mục tiêu kích thước chunk dựa trên thực nghiệm.
2. Khi cắt, giữ các phần hợp lệ và không sao chép cây con khác.
3. Khi có nhiều chunk bé cạnh nhau, **coalesce** thành chunk lớn hơn có giới hạn.
4. Nếu cây mất cân bằng, **rebalance** theo cấu trúc đã chọn.
5. Nếu giữ snapshots, tránh compaction phá chia sẻ bất biến giữa các phiên bản.

Để đánh giá compaction, đừng chỉ nhìn số nút giảm; cần xét **tổng số ký tự bị sao chép thêm** và tần suất bảo trì.

## 30. Cách kiểm thử rope bằng mô hình chuỗi tham chiếu

Một kiểm thử thực tế nên giữ song song:

- `reference`: chuỗi Python phẳng, dùng làm **đáp án đúng** cho từng thao tác.
- `rope`: cấu trúc cần kiểm tra.

Sau mỗi thao tác:

```text
rope.to_string() == reference
len(rope) == len(reference)
rope.check_invariants() == True
```

### Mã kiểm thử mô hình, dành cho người học tự chạy

```python
rope = Rope("abcdef", chunk_size=2)
reference = "abcdef"

rope.insert(3, "XY")
reference = reference[:3] + "XY" + reference[3:]
assert rope.to_string() == reference
assert rope.check_invariants()

rope.delete(1, 5)
reference = reference[:1] + reference[5:]
assert rope.to_string() == reference
assert rope.check_invariants()

rope.replace(0, 1, "Ω")
reference = "Ω" + reference[1:]
assert rope.to_string() == reference
assert rope.check_invariants()

for i in range(len(reference)):
    assert rope.char_at(i) == reference[i]

for start in range(len(reference) + 1):
    for end in range(start, len(reference) + 1):
        assert rope.substring(start, end) == reference[start:end]

before = reference
left, right = rope.split_at(len(before) // 2)
assert left.to_string() + right.to_string() == before
assert len(rope) == 0

left.concat(right)
assert left.to_string() == before
assert len(right) == 0
assert left.check_invariants()
```

### Thử cả chuỗi thao tác ngẫu nhiên

Với một bộ sinh ngẫu nhiên có seed cố định:

1. Chọn ngẫu nhiên chèn/xóa/thay một khoảng hợp lệ.
2. Áp cùng thao tác lên `reference` và rope.
3. Kiểm tra chuỗi, chiều dài, ký tự ở vài chỉ số và invariants.
4. Lặp trên kích thước chunk `1,2,3,16,256`.
5. Thêm chuỗi chứa dấu tiếng Việt, combining mark, emoji và xuống dòng.

Đừng chỉ thử thao tác đơn lẻ: nhiều lỗi `size` hoặc liên kết chỉ lộ ra **sau chuỗi split → merge → delete → split**.

## 31. Những lỗi dễ mắc khi dùng hoặc cài rope

| Sai lầm | Vì sao nguy hiểm? | Cách khắc phục |
|---|---|---|
| Nhầm `weight` với tổng chiều dài cây | Khi đi phải trừ sai offset | Rope cổ điển: `weight=len(left)`; treap chunked: `size=left+chunk+right` |
| Dùng chỉ số 1-based trong mã 0-based | Cắt lệch một ký tự | Quy định `char_at` 0-based, `split(k)` là biên |
| Cho rằng split ở `k=n` là không hợp lệ | Không tạo được suffix rỗng | Cho phép `0\le k\le n` |
| Khi rẽ phải quên trừ length cây trái và chunk | Truy cập nhầm ký tự | Dùng đúng offset cục bộ |
| Chỉ sửa liên kết nhưng quên `recalc` | Các lần split/char_at sau đi nhầm nhánh | Cập nhật size sau mọi sửa con |
| Dùng `concat` tạo gốc `O(1)` mãi mà không rebalance | Cây lệch, truy cập `O(m)` | Cân bằng/tái xây theo chính sách |
| Ghi `O(\log m)` worst-case cho treap ngẫu nhiên | Cận chỉ là kỳ vọng | Nói rõ loại bảo đảm |
| Tuyên bố chèn một triệu ký tự `O(\log m)` | Phải lưu/copy đoạn mới | Tính cả `L` và tạo chunk |
| Cắt giữa chunk nhưng nghĩ không copy byte nào | Python `str` bất biến, slice mới cần dữ liệu | Tính `O(B)` hoặc dùng slice-backed buffer |
| Chia thành chunk một ký tự không giới hạn | Overhead nút cực lớn | Dùng chunk kích thước hợp lý |
| Không gom các chunk cực nhỏ sau nhiều lần cắt | Số nút `m` tăng không cần thiết | Coalesce/rechunk định kỳ |
| Dùng `to_string` sau mỗi lần sửa rồi đòi `O(\log m)` | Flatten toàn bộ là `O(n)` | Chỉ vật chất hóa đoạn cần hiển thị |
| Chỉ tìm mẫu bên trong từng chunk | Bỏ sót mẫu qua ranh giới | Duyệt streaming hoặc KMP |
| Nhầm byte UTF-8 với code point index | Cắt giữa byte của một ký tự | Định nghĩa đơn vị chỉ số |
| Coi code point như grapheme hiển thị | Có thể tách dấu kết hợp/emoji ghép | Dùng phân đoạn grapheme |
| Lấy `copy.copy` làm snapshot persistent | Nút mutable vẫn chia sẻ | Path-copy nút bất biến |
| Sau `concat(other)` vẫn sửa `other` như owner cũ | Aliasing và hỏng liên kết | Định nghĩa chuyển ownership rõ ràng |
| `concat` một rope với chính nó | Có thể tạo chu trình | Từ chối self-concat |
| Dùng hai rope có quy ước chunk/index khác nhau | Invariants không nhất quán | Chuẩn hóa/chuyển đổi trước ghép |
| Quên xử lý chuỗi rỗng | Truy cập None hoặc tạo chunk rỗng | Rope rỗng có root None |
| Không tính phí giải phóng đoạn đã xóa | Độ trễ delete có thể lớn | Đo destructor/GC, cân nhắc trì hoãn/phiên bản |
| Tuyên bố thread-safe vì dùng Python | Split/merge có nhiều cập nhật con trỏ | Đồng bộ hoặc immutable snapshot |
| Đo mỗi microbenchmark concat đơn lẻ | Bỏ qua chi phí cân bằng và phân mảnh về sau | Benchmark chuỗi thao tác thực tế |

## 32. Bài tập tự kiểm tra

**Bài 1.** Giải thích vì sao rope là một **cây tăng cường** dù không sắp nút theo khóa như BST thông thường.

**Bài 2.** Trong rope cổ điển, `weight(v)` của nút trong là gì? Phân biệt với `len(v)`.

**Bài 3.** Với ba lá `"Data"`, `" stru"`, `"ctures"`, nếu root có cây trái là `"Data"` và cây phải ghép hai lá còn lại thì `weight(root)`, `weight(right)` và `len(root)` bằng bao nhiêu?

**Bài 4.** Dùng cây của bài 3, mô phỏng `char_at(7)` và cho biết ký tự trả về.

**Bài 5.** Rope biểu diễn `"ABCDEFGHIJ"`. `split(6)` trả hai chuỗi gì? `split(0)` và `split(10)` có hợp lệ không?

**Bài 6.** Chèn `"--"` vào `"ABCDE"` tại vị trí `2` bằng hai phép split/concat. Kết quả?

**Bài 7.** Xóa đoạn nửa kín `[2,4)` của `"AB--CDE"`. Độ dài sau xóa là bao nhiêu?

**Bài 8.** Vì sao `concat(A,B)` có thể tạo một nút gốc mới trong `O(1)` nhưng không bảo đảm truy cập `char_at` luôn `O(\log m)` sau hàng nghìn lần concat?

**Bài 9.** Nếu mỗi chunk dài tối đa `B` ký tự, chi phí sao chép khi split ở giữa một chunk `str` bất biến có thể tới bậc nào?

**Bài 10.** Với implicit treap chunked, viết công thức `size(v)` và quy tắc rẽ khi tìm ký tự chỉ số `i`.

**Bài 11.** Khi merge hai treap `A` và `B`, tại sao mọi chunk của `A` phải đứng trước mọi chunk của `B` và priority ảnh hưởng điều gì?

**Bài 12.** Một treap có priority ngẫu nhiên có chiều cao `O(\log m)` theo **kỳ vọng**. Có thể dùng kết luận ấy để khẳng định mọi lần split có worst-case `O(\log m)` không?

**Bài 13.** Rope chứa `n` ký tự trong `m` chunk và mỗi chunk dài tối đa `B`. Nêu các thành phần chi phí khi chèn đoạn mới dài `L` ký tự.

**Bài 14.** Tại sao `substring(l,r)` trả về `str` mới không thể có thời gian `O(\log m)` độc lập với `r-l`?

**Bài 15.** Mã mutable của bài quy định `split_at` và `concat` làm rỗng đối tượng nguồn. Vì sao?

**Bài 16.** Vì sao `copy.copy(rope)` không phải một cách đúng để làm persistent snapshot cho mã dùng `merge` sửa nút tại chỗ?

**Bài 17.** So sánh ý tưởng của rope persistent và operation log khi cài undo/redo.

**Bài 18.** Giải thích sự khác nhau giữa số byte UTF-8, số Unicode code point và số grapheme hiển thị. Tại sao hai biểu diễn `"á"` và `"a\u0301"` có thể có độ dài khác nhau?

**Bài 19.** Hai chunk `"ab"` và `"cd"` tạo thành chuỗi `"abcd"`. Tìm `"bc"` bằng cách gọi `find` riêng từng chunk có đúng không?

**Bài 20.** Nếu muốn tìm dòng thứ `k` nhanh, nên tăng cường metadata nào? Chi phí quét trong chunk có thể phát sinh ở đâu?

**Bài 21.** Một editor chủ yếu gõ gần một con trỏ duy nhất. Nêu lý do **gap buffer** có thể là lựa chọn tốt hơn rope.

**Bài 22.** Nêu lý do rope hoặc piece table có chỉ mục cây phù hợp khi một văn bản dài liên tục bị sửa ở nhiều vị trí khác nhau.

**Bài 23.** Vì sao phải đo **số chunk, chiều cao cây và số byte sao chép** ngoài thời gian của mỗi thao tác?

**Bài 24.** Khi xóa đoạn rất dài bằng cách bỏ nguyên một cây con, vì sao chi phí thu hồi bộ nhớ có thể khác chi phí chỉnh liên kết?

**Bài 25.** Nếu hai version của một rope persistent dùng chung các chunk bất biến, khi một version bị xóa thì có được giải phóng tất cả chunk của nó không?

**Bài 26.** Nêu ba bất biến có thể kiểm tra sau mỗi chuỗi `split → insert → delete → concat`.

**Bài 27.** Một ứng dụng có yêu cầu mỗi thao tác phải có cận worst-case logarithmic nghiêm ngặt. Có nên chọn trực tiếp implicit treap trong mã minh họa không? Vì sao?

**Bài 28.** Nếu rope lưu số grapheme cho từng chunk bằng phép cộng đơn giản, chuyện gì có thể sai khi chunk trái kết thúc bằng chữ cơ sở và chunk phải bắt đầu bằng dấu kết hợp?

### Đáp án và giải thích

1. Nó lưu **độ dài của cây con** để truy vấn theo vị trí ẩn, thay vì lưu khóa vị trí tại từng nút. Đây là một trường hợp tăng cường metadata cây.
2. `weight(v)=len(v.left)`, còn `len(v)=len(v.left)+len(v.right)` cho nút trong cổ điển.
3. `weight(root)=4`; `weight(right)=5`; `len(root)=4+5+6=15`.
4. `7\ge4` nên rẽ phải với offset `3`; tại nút phải `3<5` nên rẽ trái tới `" stru"`, ký tự ở offset `3` là `"r"`.
5. `split(6)` trả `"ABCDEF"` và `"GHIJ"`. Cả `split(0)` và `split(10)` đều hợp lệ vì split dùng **biên**, có thể cho một bên rỗng.
6. `"AB--CDE"`, vì `"ABCDE"="AB"+"CDE"` và phải ghép `"AB"+"--"+"CDE"`.
7. Xóa hai ký tự `"--"` thu được `"ABCDE"`, độ dài `5`.
8. Cứ tạo một gốc mới mà không cân bằng có thể cho cây lệch `\Theta(m)` tầng; `char_at` phải đi theo một đường dài như vậy.
9. `O(B)` ký tự, vì có thể phải tạo hai lát cắt mới từ chunk dài gần `B`.
10. `size(v)=size(left)+len(chunk)+size(right)`. Nếu `i<size(left)` rẽ trái; nếu `i<size(left)+len(chunk)` đọc trong chunk tại `i-size(left)`; nếu không rẽ phải và trừ hai phần đứng trước.
11. Merge phải bảo toàn **thứ tự nối văn bản**. Priority được dùng để chọn gốc và giữ heap-order, qua đó tạo cân bằng kỳ vọng; nó **không quyết định thứ tự ký tự**.
12. Không. `O(\log m)` là **kỳ vọng** khi priority phù hợp; treap vẫn có thể lệch với chiều cao `\Theta(m)` trong trường hợp bất lợi.
13. Gồm chi phí định vị/split (mã mẫu lấy cận bảo thủ `O(\log^2(m+1)+B)` kỳ vọng), tạo và lưu `L` ký tự trong `q\approx L/B` chunk, xây cây cho chunk mới và merge hai lần; mã minh họa dùng xây `O(L+q\log(q+1))` kỳ vọng.
14. Phải tạo `k=r-l` ký tự trong kết quả, nên riêng phần xuất nội dung có cận dưới `\Omega(k)`.
15. Vì `merge/split` sửa các nút mutable và **chuyển quyền sở hữu**. Để hai rope nguồn tiếp tục cùng sở hữu một nút có thể làm aliasing và hỏng cấu trúc khi sửa.
16. Bản sao nông có thể giữ chung con trỏ gốc/nút với rope nguồn; một phép sửa trực tiếp làm thay đổi dữ liệu được cả hai “version” nhìn thấy.
17. Persistent rope lưu những root bất biến và chia sẻ subtree để đổi version; operation log trên mutable rope ghi phép sửa nghịch đảo hoặc nội dung bị cắt để hoàn tác. Hai cách có chi phí bộ nhớ/ownership khác nhau.
18. UTF-8 mã hóa code point thành nhiều byte; grapheme có thể gồm nhiều code point. `"á"` dạng dựng sẵn có `len=1` trong Python, `"a\u0301"` dạng tách có `len=2`, dù hiển thị tương tự.
19. Không. Mẫu `"bc"` đi qua ranh giới chunk. Cần thuật toán tìm kiếm streaming như KMP hoặc bộ đệm chứa phần giao giữa các chunk.
20. Lưu `newline_count` trong subtree và số xuống dòng trong chunk. Đi theo cây mất `O(\log m)` kỳ vọng, nhưng xác định vị trí xuống dòng trong một chunk có thể cần quét `O(B)` nếu không có chỉ mục cục bộ.
21. Nếu cursor ít di chuyển, gap buffer cho chèn/xóa gần khoảng trống với chi phí thấp và mảng liên tiếp có locality tốt; không cần overhead nhiều nút như rope.
22. Rope và piece table tránh phải dời/sao chép toàn bộ hậu tố sau mỗi sửa; cây chỉ mục giúp tìm vị trí trong nhiều chunk/piece, thích hợp văn bản dài có chỉnh sửa rải rác.
23. Một triển khai có thể chạy nhanh ban đầu nhưng tạo quá nhiều chunk nhỏ, khiến `m` tăng, cây sâu, bộ nhớ nhiều hoặc phải sao chép thêm khi compact. Cần đo cả hiệu ứng tích lũy.
24. Tháo một con trỏ khỏi cây có thể chỉ tốn các bước cấu trúc logarithmic, nhưng thu hồi hàng nghìn nút không còn được tham chiếu có thể cần duyệt/giải phóng từng nút hoặc nhiều công việc GC.
25. Không. Chunk vẫn được giữ nếu version khác còn tham chiếu. Chỉ những nút/chunk **không còn bất kỳ chủ sở hữu/tham chiếu hợp lệ nào** mới có thể thu hồi an toàn.
26. Ví dụ: `to_string()==reference`; `len(rope)==len(reference)`; tại mọi nút `size=size(left)+len(chunk)+size(right)` và heap-order priority đúng; đồng thời các kết quả split nối lại đúng chuỗi gốc.
27. Không nên mặc định. Mã treap có bảo đảm **kỳ vọng**, không phải worst-case logarithmic. Cần cấu trúc cân bằng với bảo đảm xấu nhất, hoặc một thiết kế khác có phân tích deadline cụ thể.
28. Một grapheme có thể **ghép xuyên ranh giới chunk**; cộng số grapheme riêng của hai chunk có thể đếm dư. Cần thông tin ngữ cảnh biên hoặc thuật toán phân đoạn có trạng thái.

## 33. Ghi nhớ

**Rope** biểu diễn chuỗi dài bằng **một cây các đoạn ký tự**. Ở rope cổ điển, nút trong lưu **`weight=length(left subtree)`** để tìm vị trí; ở biến thể chunked implicit treap, mỗi nút chứa chunk và lưu **`size=size(left)+len(chunk)+size(right)`**. Các thao tác **ghép–cắt** (*concat/split*) là nền tảng để xây **insert, delete, replace** mà không phải dời toàn bộ hậu tố văn bản như chuỗi phẳng. Tuy nhiên, **không phải mọi rope tự cân bằng**: chiều cao `h` có thể `\Theta(m)` nếu ghép lệch; với treap ngẫu nhiên, `O(\log m)` là **kỳ vọng**, còn rope AVL/weight-balanced cần thuật toán join/split phù hợp để có bảo đảm cụ thể. Cắt giữa một chunk bất biến có thể sao chép `O(B)` ký tự, xây văn bản mới tốn theo độ dài đoạn chèn, và trả `str` phẳng từ rope vẫn tốn **`O(n)`** để vật chất hóa toàn bộ. Ngoài độ phức tạp, cần xác định **đơn vị chỉ số Unicode**, quy tắc **ownership/persistence**, kiểm soát **số chunk/độ cao**, cùng chi phí cấp phát và cache. Chọn rope khi workload có nhiều chỉnh sửa, ghép và cắt trên văn bản lớn; với dữ liệu tĩnh hoặc thao tác tập trung gần một con trỏ, chuỗi phẳng, gap buffer hoặc piece table có thể phù hợp hơn.

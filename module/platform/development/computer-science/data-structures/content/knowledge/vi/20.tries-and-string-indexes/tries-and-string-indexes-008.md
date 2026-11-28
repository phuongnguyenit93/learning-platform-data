# Cây radix, Patricia trie và cách phân biệt bit của khóa

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Cây radix, Patricia trie và cách phân biệt bit của khóa

Giả sử một hệ thống lưu bốn mã khóa 8 bit:

```text
00010010
00010110
00110010
00110110
```

Nhìn từ trái sang phải, các khóa có những đoạn bit chung rất dài. Nếu lưu bằng trie nhị phân thông thường, mỗi vị trí bit có thể tương ứng một cạnh và nhiều nút trung gian sẽ chỉ có đúng một con. **Radix tree** và **Patricia trie** tìm cách bỏ bớt những nút không cần thiết, nhưng chúng không nhất thiết làm việc theo cùng một biểu diễn.

Trong **radix tree nén cạnh**, một cạnh có thể mang cả chuỗi ký hiệu, ví dụ `"00010"`. Trong một dạng **Patricia/crit-bit tree nhị phân**, mỗi nút rẽ nhánh chỉ ghi **vị trí bit đầu tiên phân biệt các khóa**, và các lá lưu khóa đầy đủ để xác nhận kết quả. Hai cách đều khai thác tiền tố chung, song thao tác chèn/xóa và cách kiểm chứng tìm đúng khóa có những điểm khác nhau.

Bài học thuộc chương **Trie và chỉ mục chuỗi**, mô-đun `COMPUTER_SCIENCE_DATA_STRUCTURES`. Theo mục tiêu của mô-đun, ta sẽ phân tích bất biến, thao tác và độ phức tạp thời gian–bộ nhớ nhằm lựa chọn cấu trúc dữ liệu phù hợp giữa mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Trọng tâm ở đây là **bit nào tạo ra rẽ nhánh, nút nào có thể loại bỏ và tại sao chỉ đi đúng nhánh chưa đủ để xác nhận một khóa tồn tại**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **radix trie theo các ký hiệu**, **radix tree nén đường** và **Patricia/crit-bit trie** theo bit.
2. Đọc và đánh số bit theo chiều **MSB trước** (*most significant bit first*), xác định **bit khác nhau đầu tiên** của hai khóa.
3. Giải thích vì sao các nút có một con không cần được giữ trong dạng cây rẽ nhánh nén.
4. Xây sơ đồ Patricia nhị phân có **nút rẽ nhánh ghi chỉ số bit** và **lá lưu khóa nguyên vẹn**.
5. Viết thuật toán tìm: kiểm tra bit ở các nút quyết định, sau đó **đối chiếu khóa đầy đủ tại lá**.
6. Chèn một khóa mới bằng cách tìm lá ứng viên, tìm bit phân biệt đầu tiên rồi **chèn nút rẽ nhánh đúng thứ tự chỉ số**.
7. Xóa khóa bằng cách bỏ lá và **nối trực tiếp nhánh còn lại của nút cha**.
8. Hiểu vì sao truy vấn tiền tố phải kiểm tra cả các **bit bị bỏ qua** do nén.
9. Cài đặt và kiểm thử một `CritBitTrie` Python với khóa nguyên không âm có độ rộng bit cố định.
10. Phân tích số nút, số phép thử bit, bộ nhớ lưu khóa, và các vấn đề khi chuyển sang chuỗi/byte có độ dài thay đổi.

## 2. Radix là gì? Không nên đồng nhất mọi biến thể

Từ *radix* chỉ **cơ số** hay số lựa chọn theo từng đơn vị khóa. Cụm “radix tree” được dùng với nhiều ý nghĩa trong tài liệu và thư viện; cần đọc **cấu trúc nút thực tế** trước khi gán độ phức tạp.

### 2.1. Trie theo cơ số r

Cho khóa nhị phân độ dài `W` bit. Nếu mỗi bước xử lý `b` bit, một nút có thể chọn trong tối đa:

\[
r=2^b
\]

nhánh.

Ví dụ:

| Số bit mỗi bước `b` | Số nhánh tối đa `r` | Đơn vị xử lý |
| ---: | ---: | --- |
| 1 | 2 | Một bit |
| 2 | 4 | Hai bit |
| 4 | 16 | Một nibble |
| 8 | 256 | Một byte |

Trie theo byte có thể có ít bước chọn nhánh hơn trie theo bit, nhưng nếu cấp **mảng `r` ô ở mỗi nút**, bộ nhớ có thể tăng mạnh khi `r` lớn.

### 2.2. Radix tree nén đường

Một radix tree nén đường có thể gộp các nút **không terminal, một con** thành cạnh mang đoạn ký hiệu:

```text
Trie bit thông thường:
root -0-> v1 -0-> v2 -0-> v3 -1-> v4 -0-> leaf

Trie nén đường:
root ----"00010"----> leaf
```

Trong biến thể này, thuật toán phải so khớp **toàn bộ nhãn cạnh**. Khi hai khóa phân kỳ giữa nhãn, phải tách nhãn; sau xóa có thể nối lại hai nhãn.

### 2.3. Patricia trie theo bit phân biệt

Một cách biểu diễn khác bỏ các nút không rẽ nhánh nhưng **không lưu đoạn bit trên mỗi cạnh**. Thay vào đó:

- **Nút trong** ghi một chỉ số bit `i`, nghĩa là “đọc bit thứ `i` của khóa”.
- **Cạnh 0** dành cho khóa có bit `i=0`.
- **Cạnh 1** dành cho khóa có bit `i=1`.
- **Lá** giữ khóa đầy đủ.
- Những bit không cần để phân biệt các nhóm khóa **không xuất hiện thành nút riêng**.

Trong bài, ta gọi biến thể đầy đủ hai nhánh này là **Patricia kiểu crit-bit**. Tên PATRICIA còn được dùng cho những biến thể khác, ví dụ biểu diễn có liên kết quay lui (*threaded links*) hoặc cấu trúc không lưu khóa ở lá theo đúng kiểu dưới đây. **Không nên lấy mã hay công thức của một biến thể áp thẳng cho biến thể khác**.

### 2.4. So sánh nhanh

| Biểu diễn | Nút/cạnh giữ thông tin nào? | Cách đi tiếp |
| --- | --- | --- |
| Trie nhị phân thông thường | Một cạnh ứng với một bit | Đọc lần lượt từng bit |
| Radix tree nén cạnh | Cạnh giữ một đoạn bit/ký tự | So khớp cả đoạn, rồi đi xuống |
| Patricia/crit-bit nhị phân | Nút rẽ nhánh ghi vị trí bit; lá giữ toàn khóa | Đọc bit đúng vị trí của nút |
| Hash Set | Mục bảng băm lưu khóa | Băm khóa rồi so sánh ứng viên |

Mục tiêu của bài là hiểu cả **radix** lẫn **Patricia**, nhưng phần cài đặt trung tâm sẽ chọn một biến thể Patricia rõ ràng để tránh lẫn các bất biến khác nhau.

## 3. Quy ước bit: phải thống nhất MSB và chiều đánh số

Ta dùng **khóa nguyên không âm có chính xác `W` bit**, với các số 0 đứng đầu được phép. Chỉ số bit bắt đầu từ 0 ở **bit cao nhất (MSB)** và tăng dần về phía bit thấp nhất.

Với `W=8`:

```text
Vị trí i:   0 1 2 3 4 5 6 7
Trọng số: 128 64 32 16 8 4 2 1

Khóa 18:    0 0 0 1 0 0 1 0  = 00010010
Khóa 22:    0 0 0 1 0 1 1 0  = 00010110
Khóa 50:    0 0 1 1 0 0 1 0  = 00110010
Khóa 54:    0 0 1 1 0 1 1 0  = 00110110
```

### 3.1. Đọc bit thứ i

Với khóa `x` trong khoảng từ 0 đến `2^W-1`:

\[
bit(x,i)=\left(x\gg(W-1-i)\right)\mathbin{\&}1,
\qquad 0\le i<W.
\]

Dấu `\gg` là phép dịch phải bit; `\&` là AND bit.

Ví dụ khóa 18 có bit thứ 2 bằng 0 và bit thứ 5 bằng 0; khóa 22 có bit thứ 5 bằng 1. Hai khóa này giống nhau ở các vị trí 0 đến 4, nhưng **khác ở vị trí 5**.

### 3.2. Bit khác nhau đầu tiên

Với hai khóa phân biệt `a` và `b`, gọi:

\[
j=\min\{i\mid bit(a,i)\ne bit(b,i)\}.
\]

`j` là **chỉ số bit khác nhau đầu tiên tính từ MSB**. Nó quyết định vị trí cần thêm một nút rẽ nhánh để phân biệt hai khóa.

Trong Python, với số nguyên không âm cùng độ rộng `W`:

```python
def first_differing_bit(a, b, width):
    if a == b:
        return None

    xor = a ^ b
    return width - xor.bit_length()
```

Giải thích: bit 1 cao nhất của `a XOR b` chính là bit khác đầu tiên khi đọc từ trái sang phải. `bit_length()` cho vị trí của bit 1 cao nhất tính từ phía LSB.

### 3.3. Ví dụ tính LCP theo bit

Với `a=18` và `b=22`:

```text
a: 00010010
b: 00010110
        ^         khác đầu tại i=5
```

`18 XOR 22 = 4`, `4.bit_length()=3`, do đó `j=8-3=5`. Hai khóa có **5 bit đầu giống nhau**.

Với `18` và `50`:

```text
18: 00010010
50: 00110010
      ^           khác đầu tại i=2
```

`18 XOR 50=32`, `32.bit_length()=6`, nên `j=8-6=2`. Hai khóa chỉ có **2 bit đầu giống nhau**.

## 4. Sơ đồ Patricia cho bốn khóa 8 bit

Xét:

```text
K = {18, 22, 50, 54}
```

Ở chỉ số bit `2`:

- 18 và 22 có bit 0.
- 50 và 54 có bit 1.

Trong mỗi nhóm, chỉ số `5` tách hai khóa còn lại.

Cây Patricia kiểu crit-bit:

```text
                      [bit 2]
                      /     \
                    0/       \1
                    /         \
                [bit 5]     [bit 5]
                 /   \       /   \
                0     1     0     1
                |     |     |     |
               18    22    50    54

Lá giữ nguyên khóa 8 bit.
```

Đường tìm `22` chỉ thử bit 2 (0), rồi bit 5 (1), đến lá 22. Ta **không cần nút cho các bit 0, 1, 3, 4, 6 hoặc 7** vì chúng không tạo rẽ nhánh cần thiết trên đường ấy.

### 4.1. Tại sao phải giữ khóa đầy đủ ở lá?

Giả sử hỏi khóa 23:

```text
22: 00010110
23: 00010111
```

Hai khóa có **cùng bit 2 và bit 5**. Truy vấn 23 đi tới **lá 22**, nhưng 23 **không phải** khóa đã lưu.

Do đó:

> **Đi đúng đường đến một lá chưa đủ để kết luận “tồn tại”. Phải so sánh khóa đầy đủ tại lá với khóa truy vấn.**

Một cài đặt chỉ đi tới lá rồi trả True sẽ nhận nhầm nhiều khóa chưa từng được chèn.

### 4.2. Nút có đúng hai con

Trong biến thể crit-bit này, mỗi nút trong có **đúng hai nhánh 0 và 1, cả hai đều có lá khóa trong cây con**. Không có nút một con.

Tính chất đó cho phép cắt gọn một nút trong khi xóa lá: nối nhánh còn lại của cha trực tiếp với ông/bà.

### 4.3. Thứ tự bit trên đường phải tăng

Trên mỗi đường từ gốc tới lá:

\[
0\le i_1<i_2<\cdots<i_q<W.
\]

Ví dụ đường tới 22 xét `2` rồi `5`. Không được chèn nút bit 3 **sau** một nút bit 5 trên cùng đường; vị trí bit quyết định cấu trúc và sự phân nhóm khóa.

## 5. Bất biến của biến thể Patricia/crit-bit sử dụng trong bài

Với các khóa **phân biệt, cố định `W` bit**, ta dùng hợp đồng sau:

1. Khi rỗng, `root=None`.
2. Khi chỉ có một khóa, gốc là **một lá lưu toàn khóa**.
3. Nếu có từ hai khóa, nút trong ghi `bit_index∈[0,W-1]` và có đúng hai con `zero`, `one`.
4. Mỗi lá lưu **đúng một khóa đầy đủ**; không có hai lá trùng khóa.
5. Mọi khóa ở cây con `zero` của nút bit `i` có bit `i=0`; mọi khóa ở `one` có bit `i=1`.
6. Các chỉ số bit trên mỗi đường gốc → lá **tăng nghiêm ngặt**.
7. Tập khóa logic `K` bằng chính tập khóa được lưu ở tất cả lá.
8. Không có nút trong một con sau chèn hoặc xóa.

Bất biến 5 và 6 làm rõ **điểm phân biệt**: mỗi nút trong mã hóa một phép thử bit thực sự chia hai nhóm khóa sống.

### 5.1. Bit bị bỏ qua có ý nghĩa gì?

Không phải bit bị bỏ qua có “giá trị không xác định” trong khóa. Nó vẫn tồn tại ở các lá. Chúng ta chỉ **không tạo nút rẽ nhánh** ở vị trí ấy nếu việc kiểm tra bit đó không cần để phân biệt các khóa trong cây con.

Ví dụ trong nhóm `{18,22}`, bit 3 đều bằng 1, bit 4 đều bằng 0. Vì chúng **không phân nhóm**, không cần nút bit 3 hoặc bit 4.

### 5.2. Liên hệ với nén đường một con

Trong trie nhị phân không nén, các nút ở bit 3, 4 của đường chung sẽ có đúng một con sống. Patricia bỏ các nút ấy, thay bằng **chỉ số bit 5** ở nút rẽ nhánh tiếp theo.

So với radix tree nén chuỗi, thông tin “đã bỏ qua các bit nào” không được đặt thành nhãn `"10"` trên cạnh; nó được suy ra từ **chỉ số bit của các nút rẽ nhánh** và **khóa đầy đủ lưu ở lá**.

## 6. Tìm khóa: rẽ theo bit rồi so sánh lá

Giả mã:

```text
CONTAINS(root, key):
    node = root

    while node là BRANCH:
        i = node.bit_index
        if bit(key, i) == 0:
            node = node.zero
        else:
            node = node.one

    if node là NONE:
        return FALSE

    return node.key == key
```

### 6.1. Vết tìm 22

Với cây ở mục 4:

1. Tại `[bit 2]`, khóa 22 có bit 2 bằng 0 → đi trái.
2. Tại `[bit 5]`, khóa 22 có bit 5 bằng 1 → đi phải.
3. Tới lá 22, so sánh `22==22` → True.

### 6.2. Vết tìm khóa thiếu 23

1. Bit 2 của 23 bằng 0 → đi trái.
2. Bit 5 của 23 bằng 1 → đi phải.
3. Tới lá 22.
4. `22==23` là False → không có khóa 23.

### 6.3. Vì sao tìm trong cây rỗng và cây một lá cũng đúng?

- Cây rỗng: `root=None`, trả False.
- Cây một lá: không có nút phân biệt; so sánh ngay khóa ở lá.

Không cần cấp phát một nút rẽ nhánh chỉ để lưu một khóa.

## 7. Chèn: tìm lá ứng viên và bit phân biệt đầu tiên

Một phép chèn trong Patricia có **hai lần đi theo cây**, không phải chỉ thêm lá tại vị trí vừa tìm được.

### 7.1. Bước một: tìm lá ứng viên

Dùng các phép thử bit hiện có để đi tới một lá `old_leaf`. Nếu `old_leaf.key==key`, đây là khóa trùng: trả False, giữ nguyên cây.

Nếu khác, tìm chỉ số:

\[
j=firstDiff(key,oldLeaf.key).
\]

Hai khóa có cùng mọi bit trước `j`, nhưng có bit `j` khác nhau. Nút rẽ nhánh mới phải thử **đúng bit `j`**.

### 7.2. Bước hai: tìm vị trí chèn nút mới

Từ gốc đi lại, nhưng **chỉ đi qua các nút trong có `bit_index<j`**.

Dừng tại `current` khi:

- `current` là lá; hoặc
- `current` là nút trong có `bit_index≥j`.

Chèn nút `new_branch(bit_index=j)` **trước** `current`. Gắn:

- Cây con cũ `current` vào nhánh có giá trị bit `j` của `old_leaf.key`.
- Lá mới chứa `key` vào nhánh có giá trị bit `j` của `key`.

Hai giá trị này khác nhau do `j` là bit khác đầu tiên.

### 7.3. Vì sao có thể chuyển nguyên cả cây con cũ?

Tại vị trí dừng, những nút trên đường trước đó có chỉ số nhỏ hơn `j`. Trong Patricia hợp lệ, các khóa nằm trong cây con `current` có cùng bit ở vị trí `j` khi `current` đang thử một bit **lớn hơn `j`** (hoặc `current` chỉ là một lá): nếu không, đã phải có rẽ nhánh ở bit `j` hoặc sớm hơn bên trong cây con.

Bởi vậy, ta có thể đặt cả cây con `current` vào một phía của nút mới mà không phá phân loại khóa.

### 7.4. Vì sao không chèn luôn ở đáy?

Giả sử cây đã có các nút kiểm tra bit 2 và bit 5. Chèn khóa mới có bit khác đầu tiên với lá ứng viên ở **bit 0**.

Nếu đặt nút `[bit 0]` **sau** nút bit 5, ta tạo đường 2→5→0, vi phạm chỉ số tăng. Đồng thời các khóa có bit 0 khác nhau đáng ra phải được phân tách **trước** khi kiểm tra bit 2.

Phép chèn vì vậy phải tìm đúng **vị trí theo thứ tự bit**, có thể là **ngay trên gốc cũ**.

## 8. Mô phỏng chèn khóa vào Patricia

Bắt đầu bằng cây của bốn khóa:

```text
                      [2]
                     /   \
                   [5]   [5]
                  /  \   /  \
                 18  22 50  54
```

### 8.1. Thêm khóa 146 = `10010010`

So với lá 18 = `00010010`, khác đầu tiên ở `bit 0`:

```text
  18: 00010010
 146: 10010010
      ^
      bit 0
```

Vì `j=0` nhỏ hơn chỉ số nút gốc cũ là 2, tạo nút mới **trên gốc**:

```text
                        [bit 0]
                       /       \
                      0         1
                      |         |
                cây cũ [2]    146
```

Cả bốn khóa cũ có bit 0 bằng 0, nên có thể chuyển **nguyên cây cũ** sang nhánh 0.

### 8.2. Thêm khóa 2 = `00000010`

So với 18 = `00010010`, khác đầu tiên ở `bit 3`:

```text
 18: 00010010
  2: 00000010
        ^
        bit 3
```

Ta đi từ gốc qua những nút có chỉ số nhỏ hơn 3. Trong cây ban đầu, sau khi đi theo bit 2 bằng 0, ta gặp nút bit 5. Vì `5≥3`, phải đặt nút bit 3 **ngay trước** nút bit 5 của nhóm `{18,22}`:

```text
                   [bit 2]
                   /     \
               [bit 3]   [bit 5]
               /     \    /    \
              2    [bit 5] 50  54
                    /    \
                   18    22
```

Nút bit 3 không được đặt xuống dưới bit 5.

### 8.3. Chèn trùng

Nếu chèn lại 22, quá trình tìm tới lá 22; so sánh khóa đầy đủ bằng nhau, nên **không tạo nút**, không tăng số khóa. Đây là ngữ nghĩa Set; với Map phải đặc tả riêng cách cập nhật payload.

## 9. Xóa: bỏ lá và nối nhánh còn lại

Trong biến thể Patricia có **đúng hai con tại mỗi nút trong**, xóa thường đơn giản hơn split của radix tree nén nhãn.

### 9.1. Quy trình

1. Tìm đường tới lá bằng các bit quyết định, lưu những nút trong đã đi qua.
2. Nếu lá không có khóa đúng bằng truy vấn, trả False, không sửa cây.
3. Nếu gốc chính là lá cần xóa, đặt `root=None`.
4. Nếu lá có cha `parent`, lấy **nhánh anh em** `sibling` còn lại của cha.
5. Thay liên kết từ ông/bà tới `parent` bằng liên kết thẳng tới `sibling`; nếu `parent` là gốc thì `root=sibling`.
6. Giảm số khóa đi một.

Như vậy cả lá bị xóa lẫn nút cha giờ chỉ phục vụ một nhánh đều bị loại.

### 9.2. Ví dụ xóa 22

Trước:

```text
         [bit 2]
        /       \
      [5]       [5]
     /   \     /   \
    18   22   50   54
```

Xóa 22, cây con trái chỉ còn lá 18. Ta bỏ cả lá 22 và nút `[bit 5]` bên trái:

```text
         [bit 2]
        /       \
       18       [5]
               /   \
              50   54
```

Không giữ nút bit 5 một con. Các khóa khác vẫn đi đúng đường.

### 9.3. Xóa khóa không tồn tại

Nếu hỏi xóa 23, quá trình lần nhánh có thể tới lá 22. Vì `23!=22`, thao tác trả False **trước khi thay liên kết**.

Nếu chỉ xét nhánh và không kiểm tra lá, thuật toán có thể xóa nhầm khóa 22.

### 9.4. Xóa từ cây một khóa

Cây chỉ có lá 18; xóa 18 đưa `root=None`. Không còn nút cha nào cần xử lý.

## 10. Truy vấn tiền tố: những bit bị bỏ qua vẫn phải kiểm tra

Đây là bẫy thường gặp khi chuyển từ trie thường sang Patricia.

Trong trie thường, đi qua `p` cạnh đầu thường tương ứng kiểm tra `p` bit đầu. Nhưng Patricia **chỉ kiểm tra các vị trí bit phân biệt**. Một tiền tố có thể bao gồm nhiều vị trí **chưa từng được kiểm tra** trên đường rẽ nhánh.

### 10.1. Truy vấn tiền tố có độ dài t

Ta biểu diễn một tiền tố bởi cặp:

```text
(prefix_value, prefix_len)
```

trong đó `prefix_value` là số nguyên biểu diễn **chính xác `t` bit đầu**, `0≤t≤W`. Ví dụ với `W=8`:

```text
prefix_value = 0b00010
prefix_len   = 5
```

Mẫu này khớp khóa 18 = `00010010` và 22 = `00010110`. Khi đó:

\[
prefixMatch(x,p,t)\iff
(x\gg(W-t))=p
\]

với `t>0`. Với `t=0`, tiền tố rỗng khớp mọi khóa.

### 10.2. Chỉ xét nút có chỉ số bit nhỏ hơn t

Để thu hẹp vùng tìm ứng viên:

- Tại nút bit `i<t`, đọc bit thứ `i` của **tiền tố** và đi theo nhánh tương ứng.
- Khi gặp lá hoặc nút `i≥t`, dừng việc rẽ theo tiền tố.
- **Phải xác thực đầy đủ các bit đầu của khóa ứng viên**, vì có những bit nhỏ hơn `t` bị bỏ qua giữa các nút quyết định.

### 10.3. Phản ví dụ quan trọng

Cho `K={18,22}`:

```text
18 = 00010010
22 = 00010110

root [bit 5]
       /    \
      18    22
```

Hỏi tiền tố `00011` có độ dài 5. Cả hai khóa đều bắt đầu bằng `00010`, **không** bắt đầu bằng `00011`.

Nhưng nút rẽ nhánh đầu tiên có chỉ số `5`, tức **không có nút nào kiểm tra năm bit đầu**. Nếu trả toàn bộ cây con ngay khi thấy `bit_index≥prefix_len`, thuật toán sẽ **trả sai**.

Phải so sánh tiền tố 5 bit với ít nhất một khóa đại diện của cây con, hoặc kiểm tra từng lá trước khi xuất.

### 10.4. Cách đơn giản, an toàn

Một thuật toán dễ hiểu và chính xác:

1. Đi theo các nút rẽ nhánh có `bit_index<t`.
2. Duyệt tất cả lá trong cây con ứng viên.
3. Chỉ xuất những lá có `(key>>(W-t))==prefix_value`.
4. Sắp kết quả nếu API yêu cầu thứ tự.

Cách này không luôn tối ưu nhưng **không nhận nhầm** tiền tố ở các bit đã bị nén khỏi đường.

### 10.5. Có thể tối ưu hơn không?

Với một Patricia chuẩn, sau khi đã đi hết mọi nút rẽ nhánh có chỉ số nhỏ hơn `t`, **các khóa trong cây con ứng viên chia sẻ cùng t bit đầu**. Nếu kiểm tra một khóa đại diện và thấy khớp, cả cây con có thể được chấp nhận; nếu không, không có khóa nào khớp.

Để làm điều đó hiệu quả, có thể lưu một **khóa đại diện** hoặc metadata tiền tố ở mỗi nút. Nhưng cập nhật metadata phải giữ đúng khi chèn/xóa; nếu dùng cách đi xuống lấy một lá để kiểm tra, cần tính chi phí lần đi thêm ấy. Phần mã dưới dùng **lọc từng lá** để làm rõ tính đúng trước.

## 11. Cài đặt Python: khóa nguyên cố định W bit

Ta sẽ viết một `CritBitTrie` cho **Set các số nguyên không âm**, với `width=W≥1`. Mỗi khóa nằm trong miền `[0,2^W-1]`; ví dụ `W=8` hỗ trợ các mã từ 0 đến 255.

Các phương thức:

- `contains(key)`: tìm khóa đầy đủ.
- `insert(key)`: thêm khóa mới, trả True; trùng trả False.
- `delete(key)`: xóa khóa tồn tại, trả True; thiếu trả False.
- `keys()`: trả mọi khóa dạng số tăng dần.
- `keys_with_prefix(prefix_value,prefix_len)`: trả khóa có t bit đầu khớp.
- `__len__()`: trả số khóa phân biệt.

### 11.1. Loại nút

```python
class Leaf:
    __slots__ = ("key",)

    def __init__(self, key):
        self.key = key


class Branch:
    __slots__ = ("bit_index", "zero", "one")

    def __init__(self, bit_index, zero, one):
        self.bit_index = bit_index
        self.zero = zero
        self.one = one
```

`Leaf` chứa toàn khóa; `Branch` chứa chỉ số phân biệt và hai con. Không có nút một con, không có nhãn cạnh chuỗi và không có cờ terminal ở `Branch`.

### 11.2. Hàm kiểm tra dữ liệu, bit và lá ứng viên

```python
class CritBitTrie:
    def __init__(self, width):
        if type(width) is not int or width < 1:
            raise ValueError("width phải là số nguyên dương")
        self.width = width
        self.root = None
        self.size = 0

    def __len__(self):
        return self.size

    def _check_key(self, key):
        if type(key) is not int:
            raise TypeError("key phải là số nguyên, không phải bool")
        if key < 0 or key >= (1 << self.width):
            raise ValueError("key nằm ngoài miền W bit")

    def _check_prefix(self, prefix, prefix_len):
        if type(prefix_len) is not int:
            raise TypeError("prefix_len phải là int")
        if not (0 <= prefix_len <= self.width):
            raise ValueError("prefix_len ngoài miền")
        if type(prefix) is not int:
            raise TypeError("prefix phải là int")
        if prefix < 0 or prefix >= (1 << prefix_len):
            raise ValueError("prefix không vừa prefix_len bit")

    def _bit(self, key, bit_index):
        return (key >> (self.width - 1 - bit_index)) & 1

    def _candidate_leaf(self, key):
        node = self.root

        while isinstance(node, Branch):
            if self._bit(key, node.bit_index) == 0:
                node = node.zero
            else:
                node = node.one

        return node

    def contains(self, key):
        self._check_key(key)
        leaf = self._candidate_leaf(key)
        return leaf is not None and leaf.key == key
```

Khi `root=None`, `_candidate_leaf` trả None. Khi gốc là lá, chỉ so sánh khóa; khi có nhánh, đi theo bit quyết định rồi so sánh **lá cuối**.

### 11.3. Chèn: thêm nút phân biệt đúng vị trí

Bổ sung vào **cùng lớp `CritBitTrie`**:

```python
    def insert(self, key):
        """True nếu thêm khóa mới; False nếu trùng."""
        self._check_key(key)

        if self.root is None:
            self.root = Leaf(key)
            self.size = 1
            return True

        old_leaf = self._candidate_leaf(key)
        if old_leaf.key == key:
            return False

        # Chỉ số bit khác nhau đầu tiên, tính từ MSB.
        diff = self.width - (key ^ old_leaf.key).bit_length()

        # Tìm vị trí chèn sao cho bit_index tăng dọc đường.
        parent = None
        parent_side = None
        current = self.root

        while (
            isinstance(current, Branch)
            and current.bit_index < diff
        ):
            parent = current
            parent_side = self._bit(key, current.bit_index)
            if parent_side == 0:
                current = current.zero
            else:
                current = current.one

        # Khóa mới và toàn bộ cây con current khác tại bit diff.
        new_bit = self._bit(key, diff)
        old_bit = self._bit(old_leaf.key, diff)
        assert new_bit != old_bit

        new_leaf = Leaf(key)

        if new_bit == 0:
            new_branch = Branch(diff, new_leaf, current)
        else:
            new_branch = Branch(diff, current, new_leaf)

        if parent is None:
            self.root = new_branch
        elif parent_side == 0:
            parent.zero = new_branch
        else:
            parent.one = new_branch

        self.size += 1
        return True
```

**Cốt lõi:** vòng `while` chỉ đi qua các nút có `bit_index<diff`. Khi gặp nút với chỉ số **lớn hơn hoặc bằng** `diff`, phải chèn **trước** nút ấy, có thể ở trên gốc cũ. Nếu quên điều kiện này, chỉ số bit sẽ không còn tăng trên đường và thuật toán tìm có thể đi sai.

### 11.4. Xóa: loại lá và nút cha một con

```python
    def delete(self, key):
        """True nếu xóa thành công; False nếu khóa thiếu."""
        self._check_key(key)

        if self.root is None:
            return False

        if isinstance(self.root, Leaf):
            if self.root.key != key:
                return False
            self.root = None
            self.size = 0
            return True

        path = []  # (branch, side) trên đường tới lá.
        node = self.root

        while isinstance(node, Branch):
            side = self._bit(key, node.bit_index)
            path.append((node, side))
            node = node.zero if side == 0 else node.one

        if node.key != key:
            return False

        parent, side = path[-1]
        sibling = parent.one if side == 0 else parent.zero

        if len(path) == 1:
            # Cha của lá chính là gốc.
            self.root = sibling
        else:
            grandparent, parent_side = path[-2]
            if parent_side == 0:
                grandparent.zero = sibling
            else:
                grandparent.one = sibling

        self.size -= 1
        return True
```

Mã này không cần xoay cân bằng và không cần ghép nhãn chuỗi. Việc nối `sibling` trực tiếp thay `parent` giữ lại tất cả khóa của nhánh còn sống và loại bỏ nút kiểm tra bit không còn tạo rẽ nhánh.

### 11.5. Liệt kê khóa và truy vấn tiền tố

```python
    def keys(self):
        """Trả danh sách khóa nguyên tăng dần."""
        if self.root is None:
            return []

        result = []
        stack = [self.root]

        while stack:
            node = stack.pop()
            if isinstance(node, Leaf):
                result.append(node.key)
            else:
                stack.append(node.one)
                stack.append(node.zero)

        return sorted(result)

    def keys_with_prefix(self, prefix, prefix_len):
        """Khớp đúng prefix_len bit đầu, trả số nguyên tăng."""
        self._check_prefix(prefix, prefix_len)

        if self.root is None:
            return []

        node = self.root

        # Chỉ đi theo những bit rẽ nhánh nằm trong tiền tố.
        while (
            isinstance(node, Branch)
            and node.bit_index < prefix_len
        ):
            shift = prefix_len - 1 - node.bit_index
            side = (prefix >> shift) & 1
            node = node.zero if side == 0 else node.one

        # Những bit bỏ qua vẫn phải được xác minh.
        result = []
        stack = [node]

        while stack:
            current = stack.pop()
            if isinstance(current, Leaf):
                if prefix_len == 0 or (
                    current.key >> (self.width - prefix_len)
                ) == prefix:
                    result.append(current.key)
            else:
                stack.append(current.zero)
                stack.append(current.one)

        return sorted(result)
```

**Điểm cần nhớ:** sau khi dừng tại một cây con ứng viên, mã **lọc các khóa lá theo đủ `prefix_len` bit đầu**. Nhờ đó nó không bị sai khi cây Patricia bỏ qua một số vị trí bit nhỏ hơn chiều dài tiền tố. Không được thay `keys_with_prefix` bằng “lấy tất cả lá bên dưới nút cuối” mà không xác minh điều kiện này.

### 11.6. Các đoạn mã có thể dùng cùng nhau như thế nào?

Đặt hai lớp `Leaf` và `Branch` trước. Sau đó khai báo **một lớp `CritBitTrie`** bắt đầu bằng `__init__` ở mục 11.2, và lần lượt đặt các phương thức ở mục 11.3–11.5 với mức thụt lề 4 dấu cách bên trong lớp đó.

Đây là mã giáo dục nhằm làm rõ bất biến và thao tác. Nó không dùng liên kết quay lui của một biến thể PATRICIA khác và không hỗ trợ đồng thời sửa dữ liệu trong khi một trình duyệt đang liệt kê.

## 12. Chạy ví dụ chức năng với các phép assert

### 12.1. Tạo bốn khóa

```python
trie = CritBitTrie(width=8)

assert len(trie) == 0
assert not trie.contains(18)
assert trie.keys() == []

for x in (18, 22, 50, 54):
    assert trie.insert(x)

assert len(trie) == 4
assert trie.keys() == [18, 22, 50, 54]
assert all(trie.contains(x) for x in (18, 22, 50, 54))
assert not trie.contains(23)
assert not trie.insert(22)

# Gốc kiểm tra bit 2; hai nhóm kiểm tra bit 5.
assert isinstance(trie.root, Branch)
assert trie.root.bit_index == 2
assert trie.root.zero.bit_index == 5
assert trie.root.one.bit_index == 5
```

### 12.2. Chèn bit phân biệt sớm hơn gốc

```python
assert trie.insert(146)         # 10010010
assert trie.root.bit_index == 0
assert trie.keys() == [18, 22, 50, 54, 146]
assert trie.contains(146)

assert trie.delete(146)
assert trie.root.bit_index == 2
assert trie.keys() == [18, 22, 50, 54]
```

### 12.3. Chèn giữa hai mức bit

```python
assert trie.insert(2)           # 00000010
assert trie.root.bit_index == 2
assert trie.root.zero.bit_index == 3
assert trie.root.zero.one.bit_index == 5

assert trie.keys() == [2, 18, 22, 50, 54]
assert trie.delete(2)
assert trie.keys() == [18, 22, 50, 54]
assert trie.root.zero.bit_index == 5
```

### 12.4. Tìm tiền tố và kiểm tra các bit bị bỏ qua

```python
# 00010: hai khóa 18 và 22.
assert trie.keys_with_prefix(0b00010, 5) == [18, 22]

# 00110: hai khóa 50 và 54.
assert trie.keys_with_prefix(0b00110, 5) == [50, 54]

# 00011 khác ở bit thứ 4, vốn không có nút rẽ nhánh.
assert trie.keys_with_prefix(0b00011, 5) == []

# 000100: chỉ khóa 18, vì bit 5 bằng 0.
assert trie.keys_with_prefix(0b000100, 6) == [18]

# Tiền tố rỗng khớp mọi khóa.
assert trie.keys_with_prefix(0, 0) == [18, 22, 50, 54]

# Tiền tố dài đủ W bit tương đương tìm đúng khóa.
assert trie.keys_with_prefix(22, 8) == [22]
assert trie.keys_with_prefix(23, 8) == []
```

### 12.5. Xóa và giữ các khóa còn lại

```python
assert not trie.delete(23)
assert len(trie) == 4

assert trie.delete(22)
assert not trie.contains(22)
assert trie.contains(18)
assert trie.keys() == [18, 50, 54]

assert trie.delete(18)
assert trie.keys() == [50, 54]

assert trie.delete(50)
assert trie.keys() == [54]
assert isinstance(trie.root, Leaf)

assert trie.delete(54)
assert trie.root is None
assert len(trie) == 0
assert not trie.delete(54)
```

### 12.6. Miền khóa hợp lệ

```python
one_bit = CritBitTrie(width=1)
assert one_bit.insert(0)
assert one_bit.insert(1)
assert one_bit.keys() == [0, 1]
assert one_bit.delete(0)
assert one_bit.keys() == [1]

try:
    one_bit.insert(2)
except ValueError:
    pass
else:
    raise AssertionError("key=2 vượt miền 1 bit")

try:
    one_bit.insert(True)
except TypeError:
    pass
else:
    raise AssertionError("bool không được coi là khóa int")
```

Dùng `type(key) is int` thay vì chỉ `isinstance(key,int)` vì trong Python, `bool` là lớp con của `int`. Đây là một lựa chọn trong hợp đồng API nhằm tránh nhận `True` như khóa 1 mà người dùng không chủ ý.

## 13. Kiểm chứng bất biến bằng mô hình Set

Để kiểm tra cài đặt Patricia, ta không nên chỉ dựa vào một vài ví dụ hình vẽ. Dùng `set[int]` làm **mô hình tham chiếu** để đối chiếu các kết quả tìm/chèn/xóa.

### 13.1. Đối chiếu theo vết thao tác

```python
def check_against_set(trie, reference):
    assert len(trie) == len(reference)
    assert trie.keys() == sorted(reference)

    for candidate in range(256):
        assert trie.contains(candidate) == (candidate in reference)

    # So một số tiền tố ở nhiều độ dài khác nhau.
    for bits, prefix in [
        (0, 0), (1, 0), (1, 1),
        (3, 0b000), (5, 0b00010),
        (5, 0b00011), (8, 22)
    ]:
        expected = sorted(
            x for x in reference
            if bits == 0 or x >> (8 - bits) == prefix
        )
        assert trie.keys_with_prefix(prefix, bits) == expected


trie = CritBitTrie(width=8)
reference = set()

operations = [
    ("insert", 18), ("insert", 22), ("insert", 50),
    ("insert", 54), ("insert", 22), ("delete", 23),
    ("insert", 146), ("insert", 2), ("delete", 18),
    ("delete", 146), ("delete", 2), ("delete", 50),
    ("delete", 54), ("delete", 22)
]

for action, key in operations:
    if action == "insert":
        expected_change = key not in reference
        actual_change = trie.insert(key)
        reference.add(key)
    else:
        expected_change = key in reference
        actual_change = trie.delete(key)
        reference.discard(key)

    assert actual_change == expected_change
    check_against_set(trie, reference)
```

Bộ kiểm tra quét mọi khóa miền 8 bit và nhiều tiền tố; nó dùng để **chứng thực hợp đồng**, không dùng làm benchmark thời gian tìm trong Patricia.

## 14. Kiểm tra hình dạng Patricia và chỉ số bit

Một cây có thể trả kết quả đúng trên vài khóa nhưng giữ **nút một con**, hoặc có chỉ số bit **giảm** khi đi xuống. Nên bổ sung bộ kiểm tra cấu trúc.

### 14.1. Hàm xác minh

```python
def validate_critbit(trie):
    root = trie.root

    if root is None:
        assert len(trie) == 0
        return

    seen_ids = set()
    seen_keys = set()
    stack = [(root, -1, ())]

    while stack:
        node, previous_index, decisions = stack.pop()

        assert id(node) not in seen_ids
        seen_ids.add(id(node))

        if isinstance(node, Leaf):
            assert 0 <= node.key < (1 << trie.width)
            assert node.key not in seen_keys
            seen_keys.add(node.key)

            for bit_index, side in decisions:
                assert trie._bit(node.key, bit_index) == side
            continue

        assert isinstance(node, Branch)
        assert previous_index < node.bit_index < trie.width
        assert node.zero is not None
        assert node.one is not None

        stack.append((
            node.zero,
            node.bit_index,
            decisions + ((node.bit_index, 0),),
        ))
        stack.append((
            node.one,
            node.bit_index,
            decisions + ((node.bit_index, 1),),
        ))

    assert len(seen_keys) == len(trie)

    n = len(trie)
    if n > 0:
        # Mỗi nút trong có đúng 2 con:
        # I = n - 1 và tổng nút = 2*n - 1.
        assert len(seen_ids) == 2 * n - 1
```

Ở đây `decisions` lưu các bit đã được thử trên đường. Tại lá, ta kiểm tra mọi quyết định ấy với **khóa đầy đủ**.

Hàm có thể dùng nhiều bộ nhớ tạm cho các tuple đường đi; nó chỉ dành cho **kiểm thử phát triển**. Không chạy sau mọi truy vấn trong hệ thống sản xuất.

### 14.2. Kiểm tra qua nhiều thứ tự thao tác

```python
sequences = [
    [18, 22, 50, 54, 146, 2],
    [2, 146, 54, 50, 22, 18],
    [54, 18, 2, 22, 146, 50],
]

for sequence in sequences:
    trie = CritBitTrie(width=8)

    for key in sequence:
        assert trie.insert(key)
        validate_critbit(trie)

    for key in reversed(sequence):
        assert trie.delete(key)
        validate_critbit(trie)
```

Các thứ tự chèn khác nhau có thể tác động hình dạng/cách tham chiếu, nhưng kết quả tập khóa luôn phải đúng; với biến thể crit-bit chuẩn, **vị trí phân biệt** bị chi phối bởi những khóa đang lưu và thứ tự bit, không phải bởi các nút một con thừa.

## 15. Chứng minh ý tưởng: vì sao chèn và xóa giữ đúng các khóa?

### 15.1. Tìm

Tại mỗi nút bit `i`, bất biến quy định mọi khóa ở nhánh 0 có bit `i=0` và mọi khóa ở nhánh 1 có bit `i=1`. Vì vậy nếu `key` tồn tại, nó phải đi theo nhánh được chọn ở từng nút.

Đến lá, chỉ có **một khóa đầy đủ**. So sánh bằng nhau là điều kiện cần và đủ để xác nhận khóa đang tìm.

### 15.2. Chèn

Nếu khóa đã có, hàm không thay đổi gì.

Nếu chưa có, khóa mới khác lá ứng viên ở bit đầu tiên `j`. Những nút trước vị trí `j` kiểm tra các bit sớm hơn nên quyết định của khóa mới vẫn phù hợp với đường cũ. Nút mới đặt tại **vị trí chỉ số đúng** và tách hai phía dựa trên bit `j`:

\[
K'=K\cup\{key\}.
\]

Toàn bộ cây con cũ được giữ nguyên về nội dung; chỉ thay liên kết từ cha tới nó bằng một nút rẽ nhánh mới có thêm lá chứa khóa mới.

### 15.3. Xóa

Nếu lá ứng viên không trùng khóa cần xóa, trạng thái giữ nguyên.

Nếu trùng, bỏ lá và nút cha. Nhánh anh em chứa **tất cả các khóa khác** vốn nằm dưới cha. Thay cha bằng nhánh anh em giữ đúng tập khóa sống, đồng thời không để lại nút trong một con.

\[
K'=K\setminus\{key\}.
\]

### 15.4. Quy nạp theo chuỗi cập nhật

Cây rỗng ban đầu hợp lệ. Chèn và xóa bảo toàn các bất biến như trên; do đó theo quy nạp trên số thao tác, cây vẫn biểu diễn đúng tập khóa sau mọi chuỗi cập nhật hợp lệ.

## 16. Độ phức tạp theo số bit và số nhánh quyết định

Đặt:

- `W`: số bit mỗi khóa.
- `n`: số khóa phân biệt.
- `q`: số nút rẽ nhánh trên đường gốc → lá được đi qua.
- `w`: số bit trong một từ máy của mô hình word-RAM.
- `P`: số bit của tiền tố cần hỏi.
- `C`: số lá ứng viên phải duyệt trong truy vấn tiền tố.

Trong Patricia có chỉ số bit tăng và mỗi nút có hai con:

\[
q\le W,\qquad q\le n-1
\]

khi `n≥1`. Chặn thứ hai xuất phát từ tổng số nút rẽ nhánh `n-1` trong toàn cây.

### 16.1. Tìm

Thuật toán thử một bit tại mỗi nút trong rồi so sánh khóa đầy đủ ở lá.

Nếu **toàn khóa W bit vừa một từ máy** và các phép bit, so sánh khóa là O(1):

\[
T_{\mathrm{contains}}=O(q+1)\subseteq O(W+1).
\]

Điều này không bảo đảm O(log n): cây không cần cân bằng theo số lá; độ sâu phụ thuộc những bit thực sự phân biệt khóa.

### 16.2. Chèn

Chèn gồm:

1. Đi xuống tới lá: O(q+1) phép thử bit.
2. Tìm bit phân biệt đầu tiên của hai khóa: O(1) trong mô hình bitwise từ máy với độ rộng cố định.
3. Đi từ gốc tới vị trí chèn, tối đa O(q+1) phép thử bit.
4. Tạo một lá và một nút trong: O(1) nút.

Vậy:

\[
T_{\mathrm{insert}}=O(q+1)
\]

theo mô hình từ máy đã nêu, với trường hợp chèn khóa đầu tiên chỉ tạo một lá.

### 16.3. Xóa

Tìm lá và giữ đường đã đi qua tốn O(q+1), rồi nối nhánh anh em qua một số hữu hạn liên kết O(1):

\[
T_{\mathrm{delete}}=O(q+1).
\]

Không có chi phí xoay cây hay nối các chuỗi nhãn dài trong biến thể crit-bit này.

### 16.4. Nếu khóa W bit dài hơn một từ máy

Trong Python, số nguyên lớn không phải một phép toán từ máy duy nhất. Các thao tác XOR, so sánh hai số nguyên hoặc tìm `bit_length()` có thể phụ thuộc số từ máy cần biểu diễn `W` bit.

Khi đó cần cộng chi phí xử lý khóa, thường ở bậc theo `\lceil W/w\rceil` từ máy cho những phép xử lý toàn khóa. Không được tuyên bố **O(1) tuyệt đối** cho XOR trên số nguyên một triệu bit.

### 16.5. Tiền tố và đầu ra

Trong `keys_with_prefix` ở mục 11:

- Đi theo các nút có `bit_index<P`: tối đa O(P+1) phép thử bit.
- Duyệt **cây con ứng viên** có `C` lá và tối đa O(C) nút.
- Kiểm tra các bit tiền tố cho mỗi lá.
- Sắp danh sách `M≤C` kết quả trong O(M log(M+1)) phép so sánh khóa.

Trong mô hình khóa vừa một từ máy, một chặn trên là:

\[
O(P+C+M\log(M+1)).
\]

Nếu khóa lớn nhiều từ, cần cộng chi phí dịch/so sánh số nguyên lớn. Nếu chỉ muốn **đếm** và cần truy vấn thường xuyên, có thể lưu metadata số lá trong cây con; vẫn phải kiểm tra tính khớp những bit bị bỏ qua hoặc duy trì thông tin đại diện phù hợp.

## 17. Bộ nhớ: từ O(nW) nút xuống O(n) nút

### 17.1. Trie nhị phân không nén

Với `n` khóa, mỗi khóa dài `W` bit, một trie nhị phân không nén có thể có đến:

\[
1+nW
\]

nút theo chặn tổng số tiền tố, dù chia sẻ tiền tố có thể giảm con số ấy.

### 17.2. Patricia đầy đủ hai con

Trong biến thể có `n` lá và mỗi nút trong có đúng hai con, đặt `I` là số nút trong. Với một cây hữu hạn, tổng cạnh là:

\[
E=(n+I)-1.
\]

Mặt khác, mỗi nút trong đóng góp hai cạnh con, nên:

\[
E=2I.
\]

Suy ra:

\[
I=n-1,\qquad N=n+I=2n-1
\]

khi `n≥1`. Với `n=0`, cây rỗng, không có nút.

**Kết quả:** số nút Patricia tỷ lệ với số **khóa phân biệt**, không tỷ lệ trực tiếp với tổng số bit của các đường một con đã bị bỏ.

### 17.3. Nhưng khóa đầy đủ ở lá vẫn cần bộ nhớ

Mỗi lá giữ `W` bit khóa. Tổng phần dữ liệu khóa khoảng O(nW) bit, chưa kể liên kết, chỉ số bit, metadata đối tượng và cách biểu diễn số nguyên.

Nút trong giữ:

- Chỉ số bit, cần biểu diễn giá trị từ 0 đến `W-1`.
- Hai liên kết con.
- Metadata của node và bộ cấp phát.

Vì vậy **O(n) nút** không có nghĩa **O(n) bit tổng bộ nhớ** khi khóa có độ dài `W` biến động.

### 17.4. So với radix tree nén nhãn

Radix tree nén cạnh có thể giữ đoạn bit/ký tự **trên cạnh**; Patricia kiểu crit-bit ở đây giữ **chỉ số bit rẽ nhánh ở nút trong** và **khóa nguyên vẹn ở lá**.

Radix tree có thể chia sẻ cả dữ liệu nhãn của tiền tố giữa nhiều khóa. Trong Patricia lưu nguyên khóa mỗi lá, các bit chung vẫn nằm trong mỗi khóa lá; bù lại không phải tạo chuỗi nhãn riêng và không cần split/merge một chuỗi bất biến dài.

Cách nào tiết kiệm byte hơn phụ thuộc hình dạng dữ liệu, encoding khóa, metadata và runtime — không thể quyết định chỉ bằng số nút.

## 18. Khóa chuỗi độ dài thay đổi: phải định nghĩa cách mã hóa

Ví dụ Python dùng khóa **W bit cố định**. Khi chuyển sang chuỗi văn bản hoặc mảng byte có độ dài thay đổi, cần giải quyết một vấn đề nền tảng: **khi một khóa kết thúc nhưng khóa khác còn tiếp, “bit tiếp theo” có nghĩa gì?**

### 18.1. Khóa là tiền tố của khóa khác

Ví dụ byte của `a` là tiền tố của byte của `ab`. Nếu một thuật toán chỉ so sánh các bit hiện có mà không mã hóa **ranh giới kết thúc khóa**, nó có thể không tìm được một bit khác nhau hợp lệ để tách hai khóa.

Cần chọn một trong các phương án:

- **Lưu cả độ dài khóa** và định nghĩa quy tắc so sánh đặc biệt khi một dãy kết thúc.
- Thêm ký hiệu **kết thúc khóa** được mã hóa theo cách không mơ hồ.
- Dùng một quy tắc mã hóa **prefix-free**, tức không có mã khóa hợp lệ nào là tiền tố của mã khóa khác.
- Dùng một biến thể radix/Patricia có trạng thái terminal riêng cho khóa kết thúc tại nút.

### 18.2. Không tùy tiện thêm một byte 0

Nếu dữ liệu khóa có thể chứa byte `0x00`, việc đơn giản thêm `0x00` làm sentinel không đủ phân biệt khóa và dấu kết thúc trong mọi trường hợp.

Một mã hóa đúng phải bảo đảm **giải mã duy nhất**. Ví dụ có thể mã hóa từng byte thành dãy bit có đánh dấu hoặc dùng tiền tố độ dài, nhưng phải phân tích thêm chi phí chuyển đổi và độ dài mới.

### 18.3. Unicode và chuẩn hóa

Hai chuỗi hiển thị giống nhau có thể khác dãy code point:

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

Nếu ứng dụng muốn coi chúng là cùng khóa, phải chuẩn hóa thống nhất **trước khi mã hóa thành bit** ở cả tìm, chèn, xóa và truy vấn tiền tố.

Với UTF-8, `W` là số **bit của chuỗi byte đã mã hóa**, có thể khác `8×len(str)` do code point không nhất thiết chiếm một byte. Nếu dùng độ rộng cố định bằng padding, quy tắc padding phải tránh làm các khóa khác nhau biến thành cùng một biểu diễn.

## 19. Chọn radix, Patricia hay Hash Set cho bài toán nào?

| Yêu cầu | Trie/radix theo ký hiệu | Patricia/crit-bit theo bit | Hash Set |
| --- | --- | --- | --- |
| Tìm đúng khóa | Theo đường ký hiệu/nhãn | Theo bit rẽ nhánh, xác nhận ở lá | Theo hash và so sánh khóa |
| Truy vấn tiền tố | Tự nhiên theo đường tiền tố | Cần tính đến bit bị bỏ qua; có thể bổ sung metadata | Không có chỉ mục tiền tố mặc định |
| Khóa có tiền tố chung dài | Có thể nén cạnh để giảm nút | Bỏ các nút bit không rẽ nhánh | Tùy biểu diễn khóa và hash |
| Khóa cố định độ rộng bit | Dùng radix 2, 4, 16, 256... | Rất tự nhiên cho crit-bit | Dễ dùng với hash số nguyên |
| Khóa chuỗi biến độ dài | Có terminal ở nút | Cần quy tắc độ dài/đánh dấu kết thúc hoặc biến thể khác | Tự lưu cả nội dung và độ dài |
| Duyệt có thứ tự | Có thể theo nhãn con | Có thể duyệt nhánh 0 trước 1, kết hợp so sánh khóa | Không tự bảo đảm thứ tự |
| Bộ nhớ metadata | Phụ thuộc số nút, nhãn và cách lưu con | `2n-1` nút với biến thể đầy đủ hai con | Phụ thuộc bảng, tải và khóa |

### 19.1. Khi Patricia có lợi

- Cần lưu nhiều khóa **bit/byte có miền rõ ràng**, ví dụ mã nhị phân hoặc địa chỉ được chuẩn hóa.
- Có nhiều bit chung không giúp rẽ nhánh.
- Muốn tránh hàng loạt nút một con của trie bit thông thường.
- Muốn cập nhật mà không phải nối/cắt một nhãn cạnh `str` rất dài như ở radix tree nén chuỗi bất biến.

### 19.2. Khi radix tree nén nhãn thuận tiện hơn

- Khóa là chuỗi và thao tác **tiền tố ở bất kỳ vị trí ký tự nào** rất quan trọng.
- Muốn lưu cấu trúc nhãn cạnh rõ ràng để giải thích autocomplete.
- Có chiến lược xử lý nhãn và bộ nhớ phù hợp với số lần split/merge.

### 19.3. Khi Hash Set đủ dùng

Nếu chỉ cần `contains/insert/delete` của **khóa đầy đủ**, không cần duyệt tiền tố hay thứ tự, Hash Set thường đơn giản và có chi phí kỳ vọng tốt dưới giả định băm hợp lệ. Nhưng thời gian hash khóa dài và bộ nhớ bảng vẫn phải được tính; không nên nói Hash Set luôn nhanh hơn Patricia.

## 20. Các lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Nhầm vị trí bit 0 là LSB | Cấu trúc rẽ nhánh sai với ví dụ MSB | Công bố quy ước MSB và dùng nhất quán |
| Tính bit khác nhau cuối thay vì đầu | Nút mới nằm sai vị trí trong đường tăng chỉ số | Dùng bit 1 cao nhất của XOR |
| Đi tới lá là trả True | Nhận nhầm khóa thiếu có cùng đường quyết định | So sánh **toàn khóa lá** |
| Luôn chèn nút mới ngay trên lá | Có thể làm bit_index giảm trên đường | Đi lại từ gốc và chèn trước nút có index≥j |
| Chỉ xét một lá khi truy vấn tiền tố rồi chấp nhận nguyên cây con | Có thể bỏ qua bit khác trong phần tiền tố | Xác minh các bit bị bỏ qua |
| Xóa lá nhưng giữ cha một con | Không còn dạng nén chuẩn | Thay cha bằng sibling |
| Xóa khóa thiếu nhưng vẫn nối sibling | Xóa nhầm khóa khác | Kiểm tra leaf.key trước khi sửa |
| Giữ nút trong một con từ ban đầu | Công thức `2n-1` không còn đúng | Duy trì cây đầy đủ hai con |
| Cho phép hai lá trùng khóa | Set sai số lượng | So lá ứng viên trước chèn |
| Bỏ qua độ dài khóa biến thiên | Không phân biệt `a` với `ab` khi thiếu bit kết thúc | Dùng encoding có ranh giới rõ |
| Chèn sentinel trùng dữ liệu | Mã hóa khóa không đơn ánh | Thiết kế prefix-free/escaping phù hợp |
| Xem XOR số nguyên rất lớn là O(1) tuyệt đối | Sai mô hình tính toán | Phân biệt word-RAM và big integer |
| Đồng nhất Patricia với mọi radix tree | Áp sai cài đặt và bất biến | Chỉ rõ biến thể |
| Khẳng định Patricia luôn O(log n) | Độ sâu theo bit phân biệt, không cần cân bằng | Phân tích theo q≤W |
| Nói O(n) nút nghĩa O(n) bit | Bỏ chi phí giữ W bit tại mỗi lá | Cộng O(nW) bit khóa |
| Không chuẩn hóa chuỗi trước mã hóa | Một từ có nhiều biểu diễn khóa | Quy định Unicode và encoding nhất quán |

## 21. Bài tập vận dụng có gợi ý

### Bài 1 — Xác định bit khác nhau đầu tiên

Hai khóa 8 bit `00010010` và `00010110` khác đầu tiên ở vị trí nào theo MSB?

**Gợi ý:** Bit thứ 5. XOR bằng 4, `8-4.bit_length()=5`.

### Bài 2 — Tách hai nhóm khóa

Với `18,22,50,54`, nút bit nào phải là gốc và các nhánh của nó chứa khóa nào?

**Gợi ý:** Bit 2: nhánh 0 chứa 18,22; nhánh 1 chứa 50,54. Mỗi nhóm tiếp tục rẽ tại bit 5.

### Bài 3 — Tìm khóa không tồn tại

Tại sao `contains(23)` phải trả False khi đường đi bit 2→bit 5 dẫn tới lá 22?

**Gợi ý:** `23` và `22` có các bit quyết định giống nhau nhưng khác bit 7; phải so sánh lá với toàn khóa.

### Bài 4 — Chèn nút mới trên gốc

Từ cây `{18,22,50,54}`, chèn 146 = `10010010`. Nút mới đặt ở đâu?

**Gợi ý:** Bit khác đầu tiên là 0, nhỏ hơn bit gốc cũ 2. Nút bit 0 làm gốc mới, nhánh 0 là cây cũ, nhánh 1 là lá 146.

### Bài 5 — Chèn giữa hai nút quyết định

Thêm 2 = `00000010` vào cây bốn khóa. Nút bit 3 đặt ở đâu?

**Gợi ý:** Dưới nhánh bit 2=0 và **trên** nút bit 5 phân biệt 18 với 22.

### Bài 6 — Xóa một lá

Từ cây bốn khóa, xóa 22. Điều gì xảy ra với nút bit 5 bên trái?

**Gợi ý:** Nút ấy còn một lá 18, nên bị loại. Gốc bit 2 nối trực tiếp tới lá 18.

### Bài 7 — Xóa tới khi còn một khóa

Nếu Patricia còn đúng một khóa thì gốc là loại nút nào?

**Gợi ý:** Một `Leaf` chứa toàn khóa; không cần nút rẽ nhánh.

### Bài 8 — Đếm số nút

Một Patricia đầy đủ hai con có `n=100` khóa phân biệt. Có bao nhiêu lá, nút trong và tổng nút?

**Gợi ý:** 100 lá, 99 nút trong, 199 nút tổng cộng.

### Bài 9 — Prefix có bit bị bỏ qua

Cây chỉ có khóa 18 và 22, nút gốc thử bit 5. Truy vấn tiền tố 5 bit `00011` có được phép trả cả hai khóa không?

**Gợi ý:** Không. Hai khóa cùng bắt đầu bằng `00010`. Các bit 0–4 không có nút rẽ nhưng vẫn phải được xác minh.

### Bài 10 — Tiền tố rỗng

`keys_with_prefix(0,0)` nên trả gì khi cây có bốn khóa?

**Gợi ý:** Toàn bộ khóa, vì tiền tố rỗng là tiền tố của mọi dãy bit.

### Bài 11 — Tiền tố đủ chiều rộng

Với `W=8`, `keys_with_prefix(22,8)` có quan hệ thế nào với `contains(22)`?

**Gợi ý:** Tương đương về điều kiện khớp; kết quả danh sách là `[22]` nếu tồn tại, `[]` nếu không.

### Bài 12 — Bộ nhớ Patricia

Vì sao số nút bằng `2n-1` nhưng bộ nhớ dữ liệu khóa vẫn có thể là O(nW) bit?

**Gợi ý:** Mỗi lá vẫn giữ toàn bộ khóa W bit, dù các nút rẽ nhánh chỉ lưu chỉ số và liên kết.

### Bài 13 — Trie radix theo byte

Với khóa dài 32 bit và mỗi nhánh xử lý 8 bit, trie radix theo byte có tối đa bao nhiêu bước chọn nhánh? Đánh đổi gì nếu mỗi nút cấp mảng 256 ô?

**Gợi ý:** Tối đa 4 nhóm byte; mỗi nút có thể tốn 256 ô kể cả khi chỉ có vài cạnh.

### Bài 14 — Chuỗi có độ dài thay đổi

Tại sao không thể mặc định xem hai khóa `a` và `ab` có một bit khác nhau đầu tiên mà không định nghĩa bit sau điểm kết thúc `a`?

**Gợi ý:** `a` kết thúc trước khi `ab` kết thúc. Cần mã hóa ranh giới hoặc dùng biến thể có terminal.

### Bài 15 — Thứ tự MSB và LSB

Nếu hai phần của chương trình đánh số bit theo các chiều khác nhau thì lỗi nào xuất hiện?

**Gợi ý:** Nút rẽ nhánh đọc nhầm bit; phép tính firstDiff và kiểm tra đường không còn nhất quán. Hãy chọn một quy ước và viết test theo mã nhị phân cụ thể.

### Bài 16 — Kiểm thử bất biến

Nêu ba điều kiện `validate_critbit` phải kiểm tra ở mọi nút trong.

**Gợi ý:** Có hai con không None, `bit_index` tăng trên đường, mọi khóa lá ở nhánh 0/1 có bit tương ứng đúng bằng giá trị nhánh.

### Bài 17 — Tính thời gian cập nhật

Một khóa W bit không vừa một từ máy. Vì sao chèn không thể tự động được xem là O(q) tuyệt đối?

**Gợi ý:** Phải tính XOR, bit_length, so sánh khóa toàn phần và các thao tác xử lý nhiều từ máy, bên cạnh số nút rẽ nhánh `q`.

### Bài 18 — Chọn cấu trúc

Một ứng dụng lưu mã số nhị phân độ rộng cố định, thường tìm chính xác và đôi khi lọc tiền tố. Một ứng dụng khác lưu từ tiếng Việt độ dài thay đổi và thường autocomplete. Hãy đề xuất cấu trúc phù hợp và giải thích.

**Gợi ý:** Patricia/crit-bit phù hợp với mã bit cố định; radix tree có terminal và nhãn chuỗi có thể tự nhiên hơn cho autocomplete văn bản. Cả hai cần đo hiệu năng, bộ nhớ và đặc tả chuẩn hóa.

## 22. Checklist khi thiết kế Patricia trie

```text
1. Hợp đồng khóa:
   - Khóa là chuỗi, byte hay số nguyên W bit?
   - Có cho phép độ dài thay đổi không?
   - Nếu có, kết thúc khóa được mã hóa như thế nào?
   - Trùng khóa xử lý theo Set hay cập nhật payload Map?

2. Quy ước bit:
   - i=0 là MSB hay LSB?
   - Hàm đọc bit có dùng đúng width?
   - Bit khác đầu tiên tìm bằng XOR / phép so sánh nào?
   - Cùng khóa có được nhận diện trước khi tìm firstDiff?

3. Bất biến:
   - Lá lưu đúng một khóa đầy đủ?
   - Nút trong có hai con không rỗng?
   - Chỉ số bit tăng dọc đường?
   - Mỗi nhánh 0/1 chứa đúng nhóm bit?
   - Không có chu trình hoặc khóa trùng?

4. Tìm:
   - Đi qua các chỉ số bit của nút trong?
   - Có so toàn khóa tại lá trước khi trả True?
   - Cây rỗng và một lá được xử lý?

5. Chèn:
   - Tìm lá ứng viên và bit j khác đầu tiên?
   - Tìm lại vị trí chèn có index < j?
   - Có thể chèn trên gốc hoặc giữa hai nút?
   - Hai nhánh của nút mới có bit j khác nhau?

6. Xóa:
   - Kiểm tra lá trước khi sửa?
   - Bỏ cả lá và nút cha một con?
   - Nối sibling vào grandparent hoặc root?
   - Xóa tới rỗng không để nút thừa?

7. Prefix:
   - Có tính cả những bit bị bỏ qua?
   - Đã kiểm tra điều kiện khớp toàn tiền tố?
   - Có cần metadata đại diện/count để tăng tốc?
   - Đầu ra có cần thứ tự tăng hay top-k?

8. Chi phí:
   - W, q, n, độ rộng từ máy w?
   - Có tính giá xử lý số nguyên lớn/chuỗi byte?
   - Số nút 2n-1 chỉ đúng cho biến thể đầy đủ hai con?
   - Bộ nhớ khóa ở lá đã được tính riêng?

9. Kiểm thử:
   - Chèn trùng, xóa thiếu, cây rỗng, một lá?
   - Bit khác đầu tiên trước gốc/giữa hai mức?
   - Prefix có bit bỏ qua, prefix rỗng, prefix đủ W?
   - So kết quả với Set tham chiếu qua nhiều thứ tự cập nhật?
```

## 23. Tổng kết

**Radix tree** và **Patricia trie** đều tận dụng những đoạn khóa không tạo rẽ nhánh, nhưng làm điều đó bằng các biểu diễn khác nhau. Radix tree nén cạnh có thể giữ **nhãn chuỗi**; Patricia kiểu **crit-bit nhị phân** giữ **chỉ số bit phân biệt ở nút trong** và khóa nguyên vẹn ở lá.

Ba ý quan trọng nhất:

- **Tìm:** đi theo các bit quyết định rồi **so sánh toàn khóa ở lá**; không được nhận một khóa chỉ vì tới được một lá.
- **Chèn/xóa:** chèn nút tại **bit khác nhau đầu tiên theo thứ tự MSB**, đúng vị trí chỉ số tăng; khi xóa, bỏ lá và nối nhánh anh em để không giữ nút một con.
- **Tiền tố và chi phí:** những bit không được thử ở nút vẫn quan trọng khi truy vấn tiền tố; số nút của biến thể nhị phân đầy đủ là `2n-1` khi `n≥1`, nhưng mỗi lá vẫn giữ khóa `W` bit và phép xử lý khóa lớn cần được tính.

Khi phân biệt rõ **dạng radix nén nhãn** với **Patricia thử bit**, cùng các giả định về độ rộng, mã hóa khóa và mô hình tính toán, ta có thể chọn cấu trúc chỉ mục đúng theo workload mà không nhầm giữa việc ít nút hơn và thời gian xử lý luôn nhỏ hơn.

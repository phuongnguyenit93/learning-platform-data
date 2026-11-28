# Trie bit cho khóa số nguyên và truy vấn theo bit

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Trie bit cho khóa số nguyên và truy vấn theo bit

Cho tập số nguyên `{3, 5, 10, 12}`, giả sử mỗi khóa được biểu diễn bằng đúng **4 bit**:

```text
3  = 0011
5  = 0101
10 = 1010
12 = 1100
```

Ta cần trả lời không chỉ “số 5 có trong tập không?” mà còn những câu như: “Với `x=6`, khóa nào tạo giá trị `x XOR key` lớn nhất?”, “Có bao nhiêu khóa cho kết quả XOR nhỏ hơn 8?”, “Khóa nhỏ thứ ba là gì?”, hoặc “Có bao nhiêu khóa bắt đầu bằng tiền tố bit `01`?”.

Một **trie bit** (*binary trie*, *bitwise trie*) tổ chức các khóa theo **dãy bit từ trái sang phải**, mỗi nút có tối đa hai con: bit `0` và bit `1`. Nó đặc biệt phù hợp với những truy vấn cần quyết định lần lượt từ **bit quan trọng nhất** (*MSB — most significant bit*) tới bit thấp nhất (*LSB*), vì thứ tự số không dấu cũng được quyết định bởi **bit khác đầu tiên từ MSB**.

Bài này thuộc chương **Trie và chỉ mục chuỗi** trong mô-đun `COMPUTER_SCIENCE_DATA_STRUCTURES`. Theo mục tiêu của mô-đun, ta sẽ làm rõ bất biến, thao tác, thời gian và bộ nhớ của một cấu trúc dữ liệu, rồi so sánh với mảng, bảng băm, cây tìm kiếm và biến thể Patricia. Trọng tâm là **trie bit cho khóa số nguyên cố định W bit**, không phải trie ký tự cho từ vựng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đổi số nguyên không âm thành dãy `W` bit có giữ các số `0` ở đầu.
2. Giải thích hai nhánh `zero/one`, độ sâu nút và bất biến đếm khóa.
3. Cài đặt `insert`, `contains`, `delete` cho **Set khóa phân biệt**.
4. Đếm khóa theo **tiền tố bit** và giải thích tại sao phải truyền cả giá trị lẫn chiều dài tiền tố.
5. Tìm khóa tạo **XOR lớn nhất/nhỏ nhất** với một số truy vấn.
6. Tính số khóa thỏa `(key XOR x)<limit` bằng cách cộng nhánh con theo bit.
7. Tìm khóa nhỏ thứ `k` và đếm các khóa nhỏ hơn một ngưỡng số.
8. Tìm phần tử đứng thứ `k` khi sắp theo giá trị `key XOR x`.
9. Phát biểu độ phức tạp O(W) **trong mô hình thao tác bit có chi phí hằng số** và các giới hạn của mô hình này.
10. Đánh giá bộ nhớ O(nW), khả năng chia sẻ tiền tố, và so với trie bit nén Patricia.
11. Phân biệt thứ tự bit, số có dấu, phép XOR số học và khoảng cách Hamming.
12. Kiểm thử bất biến với những trường hợp rỗng, trùng khóa, xóa thiếu, ngưỡng biên và độ rộng nhỏ.

## 2. Mô hình dữ liệu: chọn rõ độ rộng W

Ta dùng **Set các số nguyên không âm** có độ rộng **`W≥1` bit**, tức mọi khóa thỏa:

\[
0\le key<2^W.
\]

Dãy bit được bổ sung số `0` ở đầu để đủ đúng `W` vị trí.

Với `W=4`:

| Khóa | Biểu diễn 4 bit |
| ---: | --- |
| 0 | `0000` |
| 1 | `0001` |
| 3 | `0011` |
| 5 | `0101` |
| 10 | `1010` |
| 12 | `1100` |
| 15 | `1111` |

### 2.1. Vì sao phải chọn W trước?

Nếu không quy định `W`, khóa 3 có thể được xem là `11`, `0011` hoặc `00000011`. Những biểu diễn ấy có **độ dài đường đi khác nhau** trong trie.

Trong bài, `W` là **cấu hình cố định của một trie**. Ví dụ một trie `W=4` chỉ nhận khóa từ 0 đến 15. Số 16 không hợp lệ: nó cần ít nhất 5 bit.

### 2.2. Đánh số bit từ MSB

Dùng chỉ số `i=0,1,\ldots,W-1`, trong đó `i=0` là bit trái nhất. Với khóa `x`, bit ở vị trí `i` là:

\[
bit(x,i)=\big(x\gg(W-1-i)\big)\mathbin{\&}1.
\]

Còn khi lập trình, ta có thể duyệt chỉ số dịch `shift` từ `W-1` xuống 0:

```python
def bits_msb_first(x, width):
    return [
        (x >> shift) & 1
        for shift in range(width - 1, -1, -1)
    ]

assert bits_msb_first(10, 4) == [1, 0, 1, 0]
assert bits_msb_first(3, 4) == [0, 0, 1, 1]
```

### 2.3. Quy ước Set, không phải Multiset

Bài này lưu **mỗi giá trị nhiều nhất một lần**:

- Chèn khóa chưa có: trả `True` và tăng số khóa.
- Chèn khóa trùng: trả `False`, **không tăng bộ đếm**.
- Xóa khóa đang có: trả `True`.
- Xóa khóa thiếu: trả `False` và không thay đổi trie.

Nếu ứng dụng cần lưu tần suất lặp lại, phải đổi sang **Multiset** có số lần xuất hiện tại lá; không được lấy mã Set rồi tự diễn giải `count` thành tần suất.

## 3. Cấu trúc một trie bit nhị phân

Mỗi nút có hai liên kết:

```text
                  node
                 /    \
              bit 0   bit 1
               /        \
            zero         one
```

Một đường từ gốc tới độ sâu `d` biểu diễn đúng `d` bit đầu của các khóa trong cây con đó.

**Gốc có độ sâu 0**, chưa tiêu thụ bit nào. **Lá ở độ sâu W** biểu diễn một khóa hoàn chỉnh.

### 3.1. Hình minh họa cho W=4

Tập `K={3,5,10,12}` tạo những đường sau:

```text
                     root (depth 0)
                    /              \
                  0                  1
                 /                    \
              [0]                     [1]
             /   \                   /   \
            0     1                 0     1
            |     |                 |     |
           [00]  [01]             [10]  [11]
             |     |                |     |
             1     0                1     0
             |     |                |     |
           [001] [010]            [101] [110]
             |     |                |     |
             1     1                0     0
             |     |                |     |
           0011  0101             1010  1100
            (3)   (5)              (10)  (12)
```

Mỗi nút ở độ sâu `d` không phải “một khóa có độ dài d”, mà biểu diễn **tiền tố d bit**. Chỉ sau đúng `W` bước mới đi tới biểu diễn khóa đầy đủ.

### 3.2. Khác với Trie từ vựng

Trie ký tự có thể lưu khóa ngắn `"a"` và khóa dài `"an"`, cần cờ **terminal** ở một nút có thể còn con.

Trong trie bit của bài, **mọi khóa dài đúng W bit**, nên tất cả khóa kết thúc ở **cùng độ sâu W**. Vì lưu Set, mỗi lá hiện diện biểu diễn đúng một khóa; có thể dùng `count=1` tại lá thay cờ terminal.

### 3.3. Hai con trỏ không có nghĩa hai con luôn tồn tại

Nút có thể chỉ có nhánh `zero` hoặc chỉ có nhánh `one`. Đây là điều bình thường: chẳng hạn khi tập chỉ có khóa 3, mọi nút trên đường `0011` có đúng một con.

Việc giữ các nút một con là khác biệt quan trọng giữa **binary trie không nén** và **Patricia/crit-bit tree**.

## 4. Bất biến cốt lõi của trie bit

Đặt `count(v)` là số **khóa phân biệt đang lưu trong cây con của nút v**.

Với trie của các khóa đúng W bit:

1. Gốc luôn tồn tại; `count(root)=|K|`.
2. Mỗi nút có tối đa hai con `zero` và `one`.
3. Đi cạnh `zero` bổ sung bit 0, đi cạnh `one` bổ sung bit 1.
4. Một nút độ sâu `d` ứng với một tiền tố gồm đúng `d` bit.
5. Không có nút nào ở độ sâu lớn hơn W.
6. Với nút trong `d<W`:
   \[
   count(v)=count(zero(v))+count(one(v)),
   \]
   trong đó con không tồn tại có count bằng 0.
7. Mỗi lá tại độ sâu W có `count=1` và không có con; một khóa không thể có hai lá.
8. Mọi nút **không phải gốc** còn được lưu đều có `count>0`; khi con đếm về 0 thì xóa liên kết tới con ấy.
9. Nếu `K` rỗng, gốc có `count=0` và cả hai con đều `None`.

Những bất biến này cho phép dùng **cùng một metadata `count`** cho truy vấn tiền tố, rank, chọn phần tử thứ k và đếm theo XOR.

### 4.1. Ý nghĩa của công thức cộng count

Ở một nút, các khóa dưới nhánh 0 và dưới nhánh 1 **rời nhau** vì một khóa không thể đồng thời có bit kế tiếp bằng cả 0 và 1. Do đó có thể cộng số khóa:

\[
|K_v|=|K_{zero(v)}|+|K_{one(v)}|.
\]

Không cần đếm trùng giữa hai nhánh. Nhưng nếu vô tình chèn cùng một khóa hai lần, con đường đi sẽ tăng count hai lần và metadata sẽ không còn phản ánh **Set**.

### 4.2. Đường đến lá là một biểu diễn khóa duy nhất

Hai số nguyên không âm khác nhau trong miền `[0,2^W)` có hai dãy `W` bit khác nhau. Chúng phải tách nhánh ở **ít nhất một vị trí bit**. Vì thế một lá không thể đồng thời biểu diễn hai khóa phân biệt.

### 4.3. Nút không cần lưu lại số nguyên hoàn chỉnh

Số nguyên của lá có thể dựng lại khi đi từ gốc:

```text
value = 0
mỗi bước:
    value = 2 * value + bit_cạnh
```

Trong Python:

```python
value = (value << 1) | bit
```

Khi tới độ sâu W, `value` chính là khóa.

## 5. Chèn một khóa mới

Để chèn `x`:

1. Kiểm tra `x` thuộc miền W bit.
2. Kiểm tra khóa đã tồn tại chưa; nếu có, trả False.
3. Tăng `count(root)` thêm 1.
4. Duyệt từng bit `x` từ MSB tới LSB.
5. Nếu nhánh cần đi chưa có, tạo nút mới.
6. Đi vào con và tăng `count` của con đó thêm 1.
7. Khi đã đi đủ W bit, tới một lá mới có `count=1`.

Giả mã:

```text
INSERT(x):
    if CONTAINS(x): return FALSE

    node = root
    node.count += 1

    for shift from W-1 down to 0:
        b = (x >> shift) & 1
        if child(node,b) is missing:
            child(node,b) = new Node
        node = child(node,b)
        node.count += 1

    return TRUE
```

### 5.1. Vết chèn 3 và 5 (W=4)

Chèn 3 = `0011`:

```text
root -> 0 -> 0 -> 1 -> 1 (leaf 3)
 count: 1    1    1    1    1
```

Chèn 5 = `0101`:

- Cùng bit đầu 0 nên nhánh đầu được chia sẻ.
- Bit thứ hai khác: 3 đi 0, 5 đi 1.
- Các nhánh dưới vị trí khác nhau được tạo riêng.

```text
root.count = 2
prefix 0.count = 2
prefix 00.count = 1
prefix 01.count = 1
```

### 5.2. Vì sao phải kiểm tra khóa trùng trước khi tăng count?

Giả sử `insert(3)` được gọi lại sau khi 3 đã tồn tại. Nếu vẫn tăng count trên đường `0011`, gốc sẽ báo 3 khóa dù Set chỉ có hai phần tử `{3,5}`.

Một cách đơn giản và an toàn là gọi `contains` trước. Điều đó cần **tối đa hai lần đi W bit**, vẫn có độ phức tạp O(W).

## 6. Tìm chính xác và xóa khóa

### 6.1. Tìm chính xác

Với `contains(x)`:

- Đi đủ W bit của `x` theo nhánh tương ứng.
- Nếu thiếu một nhánh, trả False.
- Nếu tới lá có `count=1`, trả True.

Không được kết luận True chỉ vì tìm thấy **một tiền tố** của khóa.

### 6.2. Xóa khóa

Để xóa `x`:

1. Xác nhận `x` đang tồn tại; thiếu thì trả False, không thay đổi cây.
2. Lưu các nút trên đường từ gốc tới lá và các liên kết cha–con.
3. Giảm count ở **mọi nút trên đường**, kể cả gốc và lá.
4. Đi ngược từ lá về gốc, gỡ một liên kết nếu nút con giờ có `count=0`.
5. Dừng gỡ khi gặp nút con còn khóa sống.

Mã giả:

```text
DELETE(x):
    if not CONTAINS(x): return FALSE
    path = path_to_leaf(x)

    for node in path:
        node.count -= 1

    for edge in reversed(edges_on_path):
        if edge.child.count == 0:
            remove edge.parent -> edge.child
        else:
            break

    return TRUE
```

### 6.3. Vì sao không xóa toàn bộ đường?

Khi xóa 3 khỏi `{3,5}`, hai khóa vẫn chia sẻ nhánh bit đầu 0. Không được xóa nhánh đó vì sẽ làm mất 5.

Chỉ gỡ phần đuôi đường có `count=0`. Những nút có `count>0` phải được giữ.

### 6.4. Xóa khóa cuối cùng

Nếu trie chỉ có một khóa, sau khi xóa sẽ không còn nhánh con nào của gốc. **Gốc vẫn tồn tại**, với `count=0`, tiện để tái sử dụng trie mà không cần tạo lại đối tượng root.

## 7. Đếm theo tiền tố bit

Cho một **tiền tố** được biểu diễn bằng cặp:

```text
(prefix_value, prefix_length)
```

trong đó:

\[
0\le prefixLength\le W,
\qquad
0\le prefixValue<2^{prefixLength}.
\]

Ví dụ với W=4:

- `(0b0,1)` nghĩa là bit đầu bằng 0.
- `(0b00,2)` nghĩa là hai bit đầu `00`.
- `(0b001,3)` nghĩa là ba bit đầu `001`.
- `(0,0)` là tiền tố rỗng, khớp mọi khóa.

### 7.1. Vì sao phải truyền chiều dài?

Giá trị số nguyên `0` không cho biết muốn tiền tố `0`, `00`, `000` hay tiền tố rỗng. Mỗi trường hợp có thể cho số khóa khác nhau.

Vì vậy API `count_prefix(prefix_value,prefix_length)` **không thể chỉ nhận một số** nếu muốn hỗ trợ các số 0 đứng đầu.

### 7.2. Thuật toán

Từ gốc, đi theo `prefix_length` bit của `prefix_value`, đọc từ MSB của **chính đoạn tiền tố** tới LSB:

- Nếu thiếu nhánh → kết quả 0.
- Nếu đi hết đoạn tiền tố → kết quả là `count` tại nút hiện tại.
- Nếu độ dài 0 → trả `count(root)=|K|`.

Với `K={3,5,10,12}`:

| Tiền tố | Các khóa khớp | count |
| --- | --- | ---: |
| `""` | `3,5,10,12` | 4 |
| `0` | `3,5` | 2 |
| `00` | `3` | 1 |
| `01` | `5` | 1 |
| `10` | `10` | 1 |
| `11` | `12` | 1 |
| `001` | `3` | 1 |
| `000` | Không có | 0 |

### 7.3. Độ phức tạp

Chỉ cần đi `P` cạnh với `P=prefix_length`:

\[
T_{\mathrm{prefix}}=O(P+1).
\]

Sau khi tới nút, lấy count trong O(1); không cần liệt kê mọi khóa để đếm.

## 8. XOR bit: phép toán nào đang được tối ưu?

XOR (`\oplus`) trả 1 ở vị trí hai bit khác nhau, trả 0 khi chúng bằng nhau:

| `a` | `b` | `a XOR b` |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | 0 |

Ví dụ:

```text
x   = 0110  (6)
key = 1010 (10)
XOR = 1100  (12)
```

### 8.1. Trị XOR lớn không phải số bit 1 nhiều nhất

So sánh như **số nguyên không dấu**:

```text
1000₂ = 8
0111₂ = 7
```

Mặc dù `1000` chỉ có một bit 1 và `0111` có ba bit 1, giá trị XOR `8` vẫn **lớn hơn** `7`.

Do đó, tối đa hóa XOR **không đồng nghĩa** tối đa hóa khoảng cách Hamming (số bit khác nhau). Đây là hai mục tiêu khác nhau.

### 8.2. Bit khác đầu tiên quyết định thứ tự số

Hai số nhị phân W bit có cùng độ dài: tại bit đầu tiên tính từ MSB mà chúng khác nhau, số có bit 1 sẽ lớn hơn số có bit 0, bất kể các bit thấp hơn.

Vì vậy, nếu muốn XOR **lớn nhất**, tại mỗi mức ta ưu tiên tạo ra bit XOR bằng **1**. Muốn XOR **nhỏ nhất**, ta ưu tiên bit XOR bằng **0**.

Đó là lý do trie theo bit MSB-first rất thích hợp cho những truy vấn này.

## 9. Tìm khóa tạo XOR lớn nhất và nhỏ nhất

Cho truy vấn `x`, muốn chọn `y∈K` để tối đa hóa:

\[
x\oplus y.
\]

Tại một bit:

- Nếu `xbit=0`, XOR=1 khi `ybit=1`.
- Nếu `xbit=1`, XOR=1 khi `ybit=0`.

Nên khi tìm XOR lớn nhất, **ưu tiên nhánh đối bit** `1-xbit`. Nếu nhánh ấy rỗng, phải dùng nhánh cùng bit `xbit`.

Ngược lại, để tìm XOR nhỏ nhất, **ưu tiên nhánh cùng bit**.

### 9.1. Ví dụ đầy đủ

Cho:

```text
W = 4
K = {3, 5, 10, 12}
x = 6 = 0110
```

Bảng XOR:

| Khóa `y` | 4 bit | `x XOR y` | Giá trị |
| ---: | --- | --- | ---: |
| 3 | `0011` | `0101` | 5 |
| 5 | `0101` | `0011` | 3 |
| 10 | `1010` | `1100` | 12 |
| 12 | `1100` | `1010` | 10 |

Vì thế:

\[
\arg\max_{y\in K}(6\oplus y)=10,
\quad \max(6\oplus y)=12.
\]

\[
\arg\min_{y\in K}(6\oplus y)=5,
\quad \min(6\oplus y)=3.
\]

### 9.2. Vết tìm XOR lớn nhất

`x=0110` có bit MSB bằng 0. Trie có nhánh bit 1 (khóa 10,12), nên chọn nhánh ấy để tạo bit XOR MSB bằng 1.

Tại bit tiếp theo `xbit=1`, ưu tiên nhánh bit 0, tức nhóm chứa 10. Đi theo các mức thấp hơn để thu được `y=1010` và `x XOR y=1100=12`.

**Chọn tham lam đúng** vì quyết định ở bit cao hơn có trọng số lớn hơn tổng mọi bit thấp hơn có thể bù lại.

### 9.3. Trả gì nếu trie rỗng?

Không có khóa nào để chọn, nên `min_xor(x)` và `max_xor(x)` trong bài trả **`None`**, không trả 0. Trả 0 sẽ mơ hồ vì XOR bằng 0 là một kết quả hợp lệ khi khóa `x` có trong trie.

### 9.4. Phải phân biệt khóa và trị XOR

API bài học trả cặp:

```text
(stored_key, xor_value)
```

Với ví dụ trên:

```text
max_xor(6) -> (10, 12)
min_xor(6) -> (5, 3)
```

Điều này tránh hiểu nhầm giá trị tối ưu 12 là **khóa được chọn** — thực ra khóa được chọn để có XOR 12 là 10.

## 10. Đếm khóa có XOR nhỏ hơn ngưỡng

Bây giờ không chỉ hỏi cực đại mà hỏi:

\[
countXorLessThan(x,t)
=
|\{y\in K:(x\oplus y)<t\}|.
\]

Đây là bài toán khó hơn một chút, nhưng vẫn xử lý được trong **O(W)** bằng cách sử dụng `count` của các nút con.

Giả sử tất cả số là W bit không dấu, và ngưỡng cho phép:

\[
0\le t\le2^W.
\]

### 10.1. So sánh nhị phân từ MSB

Ta so từng bit của `z=x XOR y` với `t`, bắt đầu từ MSB.

Khi các bit cao hơn đang bằng ngưỡng:

- Nếu `tbit=0`, để không vượt ngưỡng, `zbit` **phải bằng 0**. Chỉ tiếp tục nhánh `ybit=xbit`.
- Nếu `tbit=1`:
  - Mọi khóa có `zbit=0` ở vị trí này đã **nhỏ hơn ngưỡng**; cộng **toàn bộ count** của nhánh `ybit=xbit`.
  - Những khóa có `zbit=1` vẫn **bằng ngưỡng ở phần đã xét**; tiếp tục nhánh `ybit=1-xbit`.

Không bao giờ cộng các khóa mà `z` đã lớn hơn ngưỡng ở một bit trước đó.

### 10.2. Giả mã

```text
COUNT_XOR_LESS_THAN(x, t):
    if t == 0:
        return 0

    if t == 2^W:
        return size

    result = 0
    node = root

    for shift from W-1 down to 0:
        if node == NONE:
            break

        xb = bit(x, shift)
        tb = bit(t, shift)
        same = child(node, xb)
        opposite = child(node, 1-xb)

        if tb == 0:
            # Để <= phần ngưỡng đã xét:
            node = same
        else:
            # Chọn XOR bit 0 -> chắc chắn < t.
            result += same.count if same exists
            # Chọn XOR bit 1 -> còn đang bằng t.
            node = opposite

    return result
```

Cụm “`<= phần ngưỡng đã xét`” trong ghi chú trên chỉ nói **tiền tố bit** chưa vượt ngưỡng; API cuối cùng dùng **so sánh nghiêm ngặt `<t`**. Nếu kết thúc W bit và XOR **bằng hệt `t`**, đường ấy không được cộng.

### 10.3. Ví dụ

Với `K={3,5,10,12}` và `x=6`, ta có các giá trị XOR `5,3,12,10`.

- `count_xor_less_than(6,4)=1`, chỉ khóa 5 cho XOR 3.
- `count_xor_less_than(6,8)=2`, có khóa 3 và 5.
- `count_xor_less_than(6,12)=3`, nhận các giá trị XOR 3,5,10 nhưng không nhận 12.
- `count_xor_less_than(6,16)=4`, vì mọi kết quả XOR W=4 đều dưới 16.
- `count_xor_less_than(6,0)=0`.

### 10.4. Tại sao tổng thời gian vẫn O(W)?

Mỗi mức chỉ:

- Đọc bit của `x` và `t`.
- Lấy tối đa hai liên kết.
- Cộng **một bộ đếm đã có**.
- Chỉ đi tiếp **một** nhánh.

Không có việc duyệt tất cả những lá thuộc nhánh vừa được cộng. Vì thế chỉ có tối đa W bước.

### 10.5. So sánh `<` khác `≤`

Nếu muốn đếm:

\[
(x\oplus y)\le t,
\]

có thể gọi truy vấn nhỏ hơn với ngưỡng `t+1` (khi `t` là số W bit), vì miền ngưỡng cho phép tới `2^W`.

Không được dùng hàm `<t` để đếm `≤t` mà quên xử lý bằng nhau.

## 11. Chọn phần tử thứ k theo thứ tự số

Nhờ `count` ở mỗi nhánh, trie bit còn hỗ trợ **order statistics** giống cây tìm kiếm có kích thước cây con.

Cho các khóa phân biệt sắp tăng:

```text
sorted(K) = [3, 5, 10, 12]
```

Ta chọn `k` **đánh số từ 0**:

```text
kth_smallest(0) = 3
kth_smallest(1) = 5
kth_smallest(2) = 10
kth_smallest(3) = 12
```

### 11.1. Thuật toán

Trong thứ tự số không dấu, **mọi khóa có bit tiếp theo bằng 0 đứng trước mọi khóa có bit bằng 1** khi các bit cao hơn giống nhau.

Tại một nút, gọi `c0` là số khóa trong nhánh 0:

- Nếu `k<c0`, phần tử cần tìm nằm ở nhánh 0.
- Nếu `k≥c0`, bỏ qua `c0` phần tử của nhánh 0, đặt `k←k-c0` rồi đi nhánh 1.

Lặp W lần, dựng lại khóa từ các bit đã chọn.

### 11.2. Trường hợp ngoài miền

Nếu `k<0` hoặc `k≥len(trie)`, không có phần tử thứ k. API trong bài ném `IndexError`, giống thao tác truy cập phần tử ngoài giới hạn của mảng.

### 11.3. Độ phức tạp

Mỗi mức chỉ đọc một `count` và chọn một nhánh:

\[
T_{\mathrm{kth}}=O(W).
\]

Đây là một khác biệt với cách dùng Hash Set thuần: Hash Set không có **cấu trúc thứ tự số** để trả phần tử thứ k mà không làm thêm việc.

## 12. Rank và đếm trong khoảng số

Đặt:

\[
countLessThan(t)=|\{y\in K:y<t\}|.
\]

Ngưỡng `t` có miền:

\[
0\le t\le2^W.
\]

### 12.1. Phân nhánh để đếm nhỏ hơn

Duyệt các bit của `t` từ MSB:

- Nếu `tbit=0`, khóa muốn có tiền tố chưa vượt ngưỡng phải đi nhánh 0.
- Nếu `tbit=1`, **toàn bộ nhánh 0** đã nhỏ hơn `t` tại bit đang xét: cộng `count(zero)` rồi tiếp tục nhánh 1.

Nếu đường cần đi thiếu, dừng. Khóa có giá trị **bằng `t`** không được cộng, vì chỉ thêm nhánh 0 khi `tbit=1`.

### 12.2. Ví dụ

Với `K={3,5,10,12}`:

```text
count_less_than(0)  = 0
count_less_than(5)  = 1     # chỉ 3
count_less_than(10) = 2     # 3, 5
count_less_than(11) = 3     # 3, 5, 10
count_less_than(16) = 4     # toàn bộ miền W=4
```

### 12.3. Đếm trong khoảng nửa mở

Với `0≤lo≤hi≤2^W`:

\[
countRange(lo,hi)
=countLessThan(hi)-countLessThan(lo).
\]

Ví dụ:

```text
count_range(4,11) = 2    # 5 và 10
count_range(3,13) = 4    # 3, 5, 10, 12
count_range(7,7)  = 0    # khoảng rỗng
```

Nếu muốn đếm khoảng đóng `[lo,hi]`, dùng `count_range(lo,hi+1)` khi `hi` là khóa W bit hợp lệ.

## 13. Chọn phần tử thứ k theo giá trị XOR

Một biến thể thú vị là tìm khóa `y` có giá trị `x XOR y` đứng thứ `k` khi **sắp tăng các trị XOR**.

Với `x=6` và tập ví dụ:

| `key` | `6 XOR key` |
| ---: | ---: |
| 5 | 3 |
| 3 | 5 |
| 12 | 10 |
| 10 | 12 |

Vậy:

```text
kth_by_xor(6,0) = (5,3)
kth_by_xor(6,1) = (3,5)
kth_by_xor(6,2) = (12,10)
kth_by_xor(6,3) = (10,12)
```

### 13.1. Thay đổi thứ tự nhánh, không thay đổi cấu trúc

Ở mỗi bit:

- Để tạo bit XOR bằng 0, ưu tiên nhánh khóa có bit **bằng bit của x**.
- Gọi `c0` là số khóa ở nhánh cho XOR bit 0.
- Nếu `k<c0`, đi nhánh ấy.
- Nếu `k≥c0`, trừ `c0` rồi đi nhánh cho XOR bit 1.

Đây là cùng nguyên tắc với `kth_smallest`, chỉ thay ý nghĩa “nhánh 0” thành “nhánh tạo bit XOR 0”.

### 13.2. Lấy min/max XOR từ kth

Với Set không rỗng:

```text
min_xor(x) = kth_by_xor(x, 0)
max_xor(x) = kth_by_xor(x, len(trie)-1)
```

Không cần hai thuật toán riêng nếu ta đã có hàm chọn thứ k theo XOR.

### 13.3. Không có hai trị XOR trùng trong một Set

Với `x` cố định, ánh xạ:

\[
y\longmapsto x\oplus y
\]

là **song ánh** trên các số W bit: `x XOR y1 = x XOR y2` kéo theo `y1=y2`.

Vì thế với các khóa phân biệt, các giá trị XOR cũng phân biệt. `kth_by_xor` không cần chính sách phá hòa giữa hai khóa khác nhau.

Nếu chuyển sang Multiset, các giá trị XOR **có thể trùng theo số lần xuất hiện**, phải quyết định có đếm tần suất hay không.

## 14. Cài đặt Python hoàn chỉnh: `BitTrieSet`

Đoạn sau là một cài đặt **tự chứa** cho Set các số nguyên không âm, khóa đúng `W` bit. Mọi truy vấn dựa vào cùng bất biến `count`.

### 14.1. Nút trie

```python
class _BitNode:
    __slots__ = ("zero", "one", "count")

    def __init__(self):
        self.zero = None
        self.one = None
        self.count = 0
```

### 14.2. Khởi tạo, kiểm tra miền, tìm và chèn

```python
class BitTrieSet:
    def __init__(self, width):
        if type(width) is not int or width < 1:
            raise ValueError("width phải là int dương")

        self.width = width
        self.limit = 1 << width
        self.root = _BitNode()

    def __len__(self):
        return self.root.count

    def _check_key(self, key):
        if type(key) is not int:
            raise TypeError("key phải là int, không phải bool")

        if not 0 <= key < self.limit:
            raise ValueError("key vượt miền W bit không dấu")

    def _check_bound(self, bound):
        if type(bound) is not int:
            raise TypeError("bound phải là int, không phải bool")

        if not 0 <= bound <= self.limit:
            raise ValueError("bound phải thuộc [0, 2**W]")

    def contains(self, key):
        self._check_key(key)

        node = self.root

        for shift in range(self.width - 1, -1, -1):
            bit = (key >> shift) & 1
            node = node.one if bit else node.zero

            if node is None:
                return False

        return node.count == 1

    def insert(self, key):
        self._check_key(key)

        # Ngữ nghĩa Set: khóa trùng không thay count.
        if self.contains(key):
            return False

        node = self.root
        node.count += 1

        for shift in range(self.width - 1, -1, -1):
            bit = (key >> shift) & 1

            if bit == 0:
                if node.zero is None:
                    node.zero = _BitNode()
                node = node.zero
            else:
                if node.one is None:
                    node.one = _BitNode()
                node = node.one

            node.count += 1

        return True
```

Trong Python, `bool` là lớp con của `int`. Ta dùng `type(key) is int` để **không** chấp nhận `True` như khóa 1 một cách vô tình.

### 14.3. Xóa và dọn các nhánh không còn khóa

Bổ sung vào **cùng lớp `BitTrieSet`**:

```python
    def delete(self, key):
        self._check_key(key)

        if not self.contains(key):
            return False

        node = self.root
        nodes = [node]
        edges = []

        for shift in range(self.width - 1, -1, -1):
            bit = (key >> shift) & 1
            child = node.one if bit else node.zero

            edges.append((node, bit, child))
            nodes.append(child)
            node = child

        # Đường khóa đang có, mọi child đều hợp lệ.
        for current in nodes:
            current.count -= 1

        # Xóa từ lá lên, chỉ khi count == 0.
        for parent, bit, child in reversed(edges):
            if child.count != 0:
                break

            if bit == 0:
                parent.zero = None
            else:
                parent.one = None

        return True
```

Những nút dưới một nhánh `count=0` không được giữ lại. Với trie rỗng, chỉ còn `root` đếm 0 và cả hai con là `None`.

### 14.4. Đếm tiền tố bit

```python
    def count_prefix(self, prefix, prefix_length):
        if type(prefix_length) is not int:
            raise TypeError("prefix_length phải là int")

        if not 0 <= prefix_length <= self.width:
            raise ValueError("prefix_length ngoài [0, W]")

        if type(prefix) is not int:
            raise TypeError("prefix phải là int")

        if not 0 <= prefix < (1 << prefix_length):
            raise ValueError("prefix không vừa prefix_length bit")

        node = self.root

        for shift in range(prefix_length - 1, -1, -1):
            bit = (prefix >> shift) & 1
            node = node.one if bit else node.zero

            if node is None:
                return 0

        return node.count
```

Với tiền tố độ dài 0, vòng lặp rỗng và `prefix` bắt buộc bằng 0; phương thức trả `root.count`.

### 14.5. Đếm khóa nhỏ hơn và trong khoảng

```python
    def count_less_than(self, bound):
        """Số khóa key < bound, 0 <= bound <= 2**W."""
        self._check_bound(bound)

        if bound == self.limit:
            return len(self)

        total = 0
        node = self.root

        for shift in range(self.width - 1, -1, -1):
            if node is None:
                break

            bit = (bound >> shift) & 1

            if bit == 1:
                # key bit 0 -> chắc chắn nhỏ hơn bound.
                if node.zero is not None:
                    total += node.zero.count
                node = node.one
            else:
                # Chỉ key bit 0 còn có thể bằng.
                node = node.zero

        return total

    def count_range(self, low, high):
        """Đếm khóa thuộc [low, high)."""
        self._check_bound(low)
        self._check_bound(high)

        if low > high:
            raise ValueError("low phải <= high")

        return (
            self.count_less_than(high)
            - self.count_less_than(low)
        )
```

`bound==2**W` là ngưỡng **hợp lệ** dù không phải khóa hợp lệ, vì nó đại diện “ngay sau số W bit lớn nhất”.

### 14.6. Chọn khóa thứ k theo giá trị số

```python
    def kth_smallest(self, k):
        """Trả khóa thứ k theo thứ tự tăng, k bắt đầu 0."""
        if type(k) is not int or not 0 <= k < len(self):
            raise IndexError("k nằm ngoài [0, size)")

        node = self.root
        value = 0

        for _ in range(self.width):
            count_zero = (
                node.zero.count
                if node.zero is not None else 0
            )

            if k < count_zero:
                bit = 0
                node = node.zero
            else:
                bit = 1
                k -= count_zero
                node = node.one

            value = (value << 1) | bit

        return value
```

Do đã kiểm tra `k` hợp lệ và các count là nhất quán, nhánh được chọn luôn tồn tại khi đi đủ W bước.

### 14.7. Đếm khóa có XOR nhỏ hơn ngưỡng

```python
    def count_xor_less_than(self, x, bound):
        """Số khóa key sao cho (key ^ x) < bound."""
        self._check_key(x)
        self._check_bound(bound)

        if bound == 0:
            return 0

        if bound == self.limit:
            return len(self)

        total = 0
        node = self.root

        for shift in range(self.width - 1, -1, -1):
            if node is None:
                break

            xb = (x >> shift) & 1
            tb = (bound >> shift) & 1

            if xb == 0:
                same = node.zero
                different = node.one
            else:
                same = node.one
                different = node.zero

            if tb == 0:
                # XOR bit phải là 0 để chưa vượt ngưỡng.
                node = same
            else:
                # XOR bit 0 -> đã nhỏ hơn ngưỡng.
                if same is not None:
                    total += same.count

                # XOR bit 1 -> vẫn đang bằng ngưỡng.
                node = different

        return total

    def count_xor_range(self, x, low, high):
        """Đếm khóa có low <= (key ^ x) < high."""
        self._check_key(x)
        self._check_bound(low)
        self._check_bound(high)

        if low > high:
            raise ValueError("low phải <= high")

        return (
            self.count_xor_less_than(x, high)
            - self.count_xor_less_than(x, low)
        )
```

Với ngưỡng nhỏ hơn `2**W`, chỉ những nhánh làm XOR **nhỏ nghiêm ngặt** hơn ngưỡng ở bit đầu tiên khác mới được cộng. Đường còn bằng ngưỡng sau W bước không được cộng thêm.

### 14.8. Chọn phần tử thứ k theo XOR và tìm cực trị

```python
    def kth_by_xor(self, x, k):
        """(stored_key, xor_value) ở hạng k theo XOR."""
        self._check_key(x)

        if type(k) is not int or not 0 <= k < len(self):
            raise IndexError("k nằm ngoài [0, size)")

        node = self.root
        key = 0

        for shift in range(self.width - 1, -1, -1):
            xb = (x >> shift) & 1

            if xb == 0:
                xor_zero = node.zero
                xor_one = node.one
            else:
                xor_zero = node.one
                xor_one = node.zero

            count_zero = (
                xor_zero.count if xor_zero is not None else 0
            )

            if k < count_zero:
                chosen_bit = xb
                node = xor_zero
            else:
                k -= count_zero
                chosen_bit = 1 - xb
                node = xor_one

            key = (key << 1) | chosen_bit

        return key, key ^ x

    def min_xor(self, x):
        self._check_key(x)

        if len(self) == 0:
            return None

        return self.kth_by_xor(x, 0)

    def max_xor(self, x):
        self._check_key(x)

        if len(self) == 0:
            return None

        return self.kth_by_xor(x, len(self) - 1)
```

Hai hàm cực trị gọi `kth_by_xor`; độ phức tạp vẫn O(W), vì mỗi hàm chỉ thực hiện một lượt đi đủ W bit.

### 14.9. Liệt kê khóa tăng dần

```python
    def iter_keys(self):
        """Sinh các khóa theo thứ tự tăng, không đệ quy."""
        stack = [(self.root, 0, 0)]

        while stack:
            node, depth, value = stack.pop()

            if node is None or node.count == 0:
                continue

            if depth == self.width:
                yield value
                continue

            # Stack LIFO: đẩy nhánh 1 trước để thăm 0 trước.
            if node.one is not None:
                stack.append((
                    node.one, depth + 1, (value << 1) | 1
                ))

            if node.zero is not None:
                stack.append((
                    node.zero, depth + 1, value << 1
                ))
```

`iter_keys` có thể duyệt toàn bộ nút còn tồn tại. Nó không làm `kth_smallest` thành thuật toán phụ thuộc `n`; truy vấn kth dùng count để chọn ngay một nhánh ở mỗi mức.

## 15. Kiểm thử chức năng trên cùng bộ khóa

Các phương thức ở mục 14.3–14.9 được đặt vào **cùng lớp `BitTrieSet`** sau `__init__`, `contains` và `insert` ở mục 14.2.

### 15.1. Tạo trie và kiểm tra Set

```python
trie = BitTrieSet(width=4)

assert len(trie) == 0
assert not trie.contains(3)
assert list(trie.iter_keys()) == []
assert trie.min_xor(6) is None
assert trie.max_xor(6) is None

for key in (3, 5, 10, 12):
    assert trie.insert(key)

assert len(trie) == 4
assert list(trie.iter_keys()) == [3, 5, 10, 12]
assert all(trie.contains(x) for x in (3, 5, 10, 12))
assert not trie.contains(6)

# Chèn trùng không làm tăng size hoặc count.
assert not trie.insert(3)
assert len(trie) == 4
```

### 15.2. Tiền tố

```python
assert trie.count_prefix(0, 0) == 4
assert trie.count_prefix(0b0, 1) == 2
assert trie.count_prefix(0b00, 2) == 1
assert trie.count_prefix(0b01, 2) == 1
assert trie.count_prefix(0b10, 2) == 1
assert trie.count_prefix(0b11, 2) == 1
assert trie.count_prefix(0b001, 3) == 1
assert trie.count_prefix(0b000, 3) == 0
assert trie.count_prefix(0b0011, 4) == 1
assert trie.count_prefix(0b0010, 4) == 0
```

### 15.3. XOR, cực trị và thứ k theo XOR

```python
assert trie.max_xor(6) == (10, 12)
assert trie.min_xor(6) == (5, 3)

assert trie.kth_by_xor(6, 0) == (5, 3)
assert trie.kth_by_xor(6, 1) == (3, 5)
assert trie.kth_by_xor(6, 2) == (12, 10)
assert trie.kth_by_xor(6, 3) == (10, 12)

assert trie.count_xor_less_than(6, 0) == 0
assert trie.count_xor_less_than(6, 4) == 1
assert trie.count_xor_less_than(6, 8) == 2
assert trie.count_xor_less_than(6, 12) == 3
assert trie.count_xor_less_than(6, 16) == 4

assert trie.count_xor_range(6, 4, 12) == 2
assert trie.count_xor_range(6, 12, 16) == 1
```

### 15.4. Thứ tự số, rank và khoảng

```python
assert [
    trie.kth_smallest(k) for k in range(len(trie))
] == [3, 5, 10, 12]

assert trie.count_less_than(0) == 0
assert trie.count_less_than(5) == 1
assert trie.count_less_than(10) == 2
assert trie.count_less_than(11) == 3
assert trie.count_less_than(16) == 4

assert trie.count_range(4, 11) == 2
assert trie.count_range(3, 13) == 4
assert trie.count_range(7, 7) == 0
```

### 15.5. Xóa và giữ đúng bộ đếm

```python
assert not trie.delete(6)
assert trie.delete(5)
assert not trie.contains(5)
assert len(trie) == 3
assert list(trie.iter_keys()) == [3, 10, 12]

assert trie.count_prefix(0b0, 1) == 1
assert trie.count_xor_less_than(6, 8) == 1

assert trie.delete(3)
assert trie.delete(10)
assert trie.delete(12)
assert len(trie) == 0
assert trie.root.zero is None
assert trie.root.one is None
assert not trie.delete(12)

assert trie.insert(0)
assert trie.contains(0)
assert trie.count_prefix(0b0000, 4) == 1
```

### 15.6. Độ rộng W=1

```python
one_bit = BitTrieSet(1)

assert one_bit.insert(0)
assert one_bit.insert(1)
assert list(one_bit.iter_keys()) == [0, 1]
assert one_bit.max_xor(0) == (1, 1)
assert one_bit.min_xor(0) == (0, 0)
assert one_bit.count_xor_less_than(1, 1) == 1

assert one_bit.delete(0)
assert one_bit.kth_smallest(0) == 1
assert one_bit.delete(1)
assert len(one_bit) == 0
```

## 16. Kiểm tra dữ liệu lỗi và ranh giới miền

Một trie W bit phải **từ chối** số nguyên âm, số vượt W bit, khóa không phải `int` và ngưỡng vượt `2^W`.

### 16.1. Các ngưỡng biên

Với W=4:

- Khóa hợp lệ: `0..15`.
- `bound` hợp lệ cho `count_less_than` hoặc XOR less-than: `0..16`.
- `bound=16` đếm toàn bộ khóa.
- `bound=0` trả 0.
- Prefix độ dài 0 bắt buộc có giá trị 0.
- Prefix độ dài 4 có giá trị `0..15`.

### 16.2. Test từ chối khóa ngoài miền

```python
tree = BitTrieSet(4)

for invalid in (-1, 16, 100):
    try:
        tree.insert(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("phải từ chối khóa ngoài miền")

for invalid in (True, False, 2.5, "3"):
    try:
        tree.insert(invalid)
    except TypeError:
        pass
    else:
        raise AssertionError("phải yêu cầu int đúng kiểu")
```

### 16.3. Test tiền tố và ngưỡng

```python
for prefix, length in ((1, 0), (4, 2), (0, 5)):
    try:
        tree.count_prefix(prefix, length)
    except ValueError:
        pass
    else:
        raise AssertionError("prefix không hợp lệ")

for bad_bound in (-1, 17):
    try:
        tree.count_less_than(bad_bound)
    except ValueError:
        pass
    else:
        raise AssertionError("bound ngoài miền")

try:
    tree.count_range(9, 2)
except ValueError:
    pass
else:
    raise AssertionError("khoảng đảo phải bị từ chối")
```

### 16.4. Test kth ngoài miền

```python
try:
    tree.kth_smallest(0)
except IndexError:
    pass
else:
    raise AssertionError("trie rỗng không có kth=0")

try:
    tree.kth_by_xor(0, 0)
except IndexError:
    pass
else:
    raise AssertionError("trie rỗng không có kth xor")
```

## 17. Validator bất biến của một trie bit

Kiểm thử đầu ra tốt là cần thiết nhưng chưa đủ: một bug có thể khiến `contains` đúng trên một số khóa trong khi `count` ở một nhánh đã sai.

Ta xây một hàm kiểm tra **từ dưới lên**:

- Không có chu trình hay nút dùng chung ở hai cha.
- Nút trong có `count` bằng tổng count hai con.
- Lá ở độ sâu W có count=1 và không có con.
- Nút không phải gốc luôn có count>0.
- Nếu gốc count=0 thì gốc không còn con.
- Số khóa lấy từ `iter_keys` bằng `len(tree)`.

### 17.1. Hàm kiểm tra

```python
def validate_bit_trie(trie):
    seen = set()
    totals = {}
    stack = [(trie.root, 0, False)]

    while stack:
        node, depth, expanded = stack.pop()

        if not expanded:
            assert id(node) not in seen
            seen.add(id(node))
            assert 0 <= depth <= trie.width

            stack.append((node, depth, True))

            if depth == trie.width:
                assert node.zero is None
                assert node.one is None
            else:
                if node.zero is not None:
                    stack.append((
                        node.zero, depth + 1, False
                    ))
                if node.one is not None:
                    stack.append((
                        node.one, depth + 1, False
                    ))

        else:
            if depth == trie.width:
                assert node.count == 1
            else:
                count_zero = (
                    totals[id(node.zero)]
                    if node.zero is not None else 0
                )
                count_one = (
                    totals[id(node.one)]
                    if node.one is not None else 0
                )

                assert node.count == count_zero + count_one

                if depth > 0:
                    assert node.count > 0

            totals[id(node)] = node.count

    if trie.root.count == 0:
        assert trie.root.zero is None
        assert trie.root.one is None

    values = list(trie.iter_keys())
    assert len(values) == len(trie)
    assert values == sorted(set(values))
```

Validator dùng O(số nút) thời gian và bộ nhớ phụ để duyệt; đây là công cụ **kiểm thử phát triển**, không phải bước cần thực hiện sau mỗi truy vấn ở môi trường sản xuất.

### 17.2. Kiểm tra qua các thứ tự chèn/xóa

```python
sequences = [
    [3, 5, 10, 12],
    [12, 10, 5, 3],
    [5, 3, 12, 10],
]

for sequence in sequences:
    tree = BitTrieSet(4)

    for key in sequence:
        assert tree.insert(key)
        validate_bit_trie(tree)

    assert list(tree.iter_keys()) == [3, 5, 10, 12]

    for key in reversed(sequence):
        assert tree.delete(key)
        validate_bit_trie(tree)

    assert len(tree) == 0
```

Với Set khóa cố định, đường bit của mỗi khóa được quyết định **duy nhất bởi giá trị khóa**, không phải bởi thứ tự chèn. Vì vậy hình dạng trie sau khi chèn cùng một tập khóa (và dọn nút rỗng đúng cách) giống nhau theo các bit, khác với một BST không cân bằng.

## 18. Kiểm thử đối chiếu với Python Set

Để bắt các lỗi khó phát hiện ở truy vấn XOR và kth, dùng `set[int]` làm mô hình tham chiếu.

### 18.1. Hàm đối chiếu độc lập

```python
def compare_with_set(trie, reference):
    expected = sorted(reference)

    assert len(trie) == len(reference)
    assert list(trie.iter_keys()) == expected

    for key in range(trie.limit):
        assert trie.contains(key) == (key in reference)

    for bound in range(trie.limit + 1):
        assert trie.count_less_than(bound) == sum(
            y < bound for y in reference
        )

    for k, value in enumerate(expected):
        assert trie.kth_smallest(k) == value

    for x in range(trie.limit):
        xor_sorted = sorted(
            (y ^ x, y) for y in reference
        )

        for k, (xor_value, key) in enumerate(xor_sorted):
            assert trie.kth_by_xor(x, k) == (
                key, xor_value
            )

        for bound in range(trie.limit + 1):
            expected_count = sum(
                (y ^ x) < bound for y in reference
            )
            assert (
                trie.count_xor_less_than(x, bound)
                == expected_count
            )

        if reference:
            assert trie.min_xor(x) == (
                xor_sorted[0][1], xor_sorted[0][0]
            )
            assert trie.max_xor(x) == (
                xor_sorted[-1][1], xor_sorted[-1][0]
            )
        else:
            assert trie.min_xor(x) is None
            assert trie.max_xor(x) is None

    validate_bit_trie(trie)
```

### 18.2. Duyệt một vết thao tác

```python
tree = BitTrieSet(width=4)
reference = set()

operations = [
    ("insert", 3),
    ("insert", 10),
    ("insert", 5),
    ("insert", 3),   # Trùng.
    ("delete", 12),  # Thiếu.
    ("insert", 12),
    ("delete", 5),
    ("insert", 0),
    ("delete", 3),
    ("insert", 15),
    ("delete", 10),
    ("delete", 0),
    ("delete", 12),
    ("delete", 15),
]

for action, value in operations:
    if action == "insert":
        expected_change = value not in reference
        actual_change = tree.insert(value)
        reference.add(value)
    else:
        expected_change = value in reference
        actual_change = tree.delete(value)
        reference.discard(value)

    assert actual_change == expected_change
    compare_with_set(tree, reference)
```

Bộ kiểm tra trên cố tình xét mọi `x` và `bound` của miền 4 bit, rất tốt để phát hiện lỗi biên **ở dữ liệu nhỏ**. Không dùng vòng quét toàn bộ miền `2^W` trong hệ thống sản xuất với W=32 hoặc W=64.

### 18.3. Tại sao không chỉ so max XOR?

Nếu code chọn sai một nhánh nhỏ, truy vấn `max_xor` trên vài khóa có thể vẫn cho đúng. Nhưng `count_xor_less_than` và `kth_by_xor` dùng metadata đếm ở từng mức, dễ bộc lộ lỗi bị che khuất. Kiểm thử nhiều loại API độc lập làm tăng độ tin cậy.

## 19. Chứng minh tính đúng: chèn, xóa và tìm

### 19.1. Chèn giữ `count` chính xác

Giả sử trie đang biểu diễn đúng tập khóa `K`. Nếu khóa `x` đã có, thuật toán không sửa gì.

Nếu chưa có, chỉ **một** đường từ gốc đến lá biểu diễn đúng dãy W bit của `x`. Mọi nút trên đường ấy có thêm **một khóa trong cây con**, nên phải tăng count đúng 1. Mọi nút ngoài đường không chứa khóa `x`, nên giữ nguyên.

Do đó cây mới biểu diễn:

\[
K'=K\cup\{x\}.
\]

### 19.2. Xóa giữ `count` chính xác

Nếu `x` không thuộc `K`, không được giảm count hay xóa nút.

Nếu `x` có trong `K`, chỉ các nút trên đường bit của `x` có ít đi **một khóa**. Giảm count chính xác trên đường ấy cho:

\[
K'=K\setminus\{x\}.
\]

Một nút có count=0 không còn khóa nào trong cây con, nên gỡ liên kết tới nó an toàn. Nút có count>0 không được gỡ vì có ít nhất một khóa sống.

### 19.3. Tìm là đúng vì đường bit là duy nhất

Mỗi khóa W bit xác định đúng một chuỗi các lựa chọn 0/1. Nếu một nhánh trên đường đó vắng mặt, không thể có khóa cần tìm.

Nếu đi đủ W bit tới lá count=1, khóa tương ứng tồn tại. Không có hai khóa khác nhau cùng dãy W bit, nên tìm không thể bị nhầm giữa hai khóa.

### 19.4. Quy nạp theo số thao tác

Cây rỗng ban đầu đúng với `K=\varnothing`. Chèn và xóa giữ bất biến. Vì vậy, theo quy nạp trên số thao tác, trie biểu diễn đúng tập khóa sau mọi chuỗi thao tác hợp lệ.

## 20. Chứng minh tham lam cho truy vấn XOR

Giả sử ở vị trí bit `i` từ MSB, hai phương án có cùng mọi bit XOR cao hơn `i`.

- Phương án A tạo `XORbit_i=1`.
- Phương án B tạo `XORbit_i=0`.

Nếu còn `r` bit thấp hơn `i`, bit ở vị trí hiện tại có trọng số `2^r`, còn tổng trọng số mọi bit thấp hơn tối đa:

\[
2^r-1.
\]

Vì:

\[
2^r>2^r-1,
\]

bất kỳ kết quả chọn XOR bit 1 tại vị trí đang xét đều **lớn hơn** mọi kết quả chọn XOR bit 0, nếu các bit cao hơn bằng nhau.

Do đó:

- Để tối đa XOR, ưu tiên bit 1 ở mỗi vị trí còn có khóa sống.
- Để tối thiểu XOR, ưu tiên bit 0.
- Để chọn thứ k theo XOR, nhóm bit 0 đứng trước nhóm bit 1 và có thể dùng count để bỏ qua cả nhóm.

Đây là lập luận **theo thứ tự từ điển của dãy bit MSB-first**, tương đương thứ tự số nguyên không dấu W bit.

## 21. Chứng minh phương pháp đếm XOR nhỏ hơn t

Xét một tập các khóa đang có cùng phần XOR phía trên **bằng đúng tiền tố** của ngưỡng `t`. Ở bit hiện tại:

- Nếu `tbit=0`, phần XOR muốn nhỏ hơn t **không thể chọn bit 1** ở đây, vì như thế số XOR đã lớn hơn t. Chỉ nhánh XOR bit 0 còn được xem xét.
- Nếu `tbit=1`, mọi khóa chọn XOR bit 0 đã **nhỏ hơn t tại bit khác đầu tiên**, nên toàn bộ chúng đều hợp lệ bất kể các bit thấp hơn. Cộng count nhánh ấy. Những khóa chọn XOR bit 1 vẫn cần xét tiếp vì phần đầu còn bằng t.

Mỗi khóa được đếm **đúng một lần**, tại **bit đầu tiên** mà kết quả XOR của khóa nhỏ hơn ngưỡng; những khóa bằng t tới hết W bit không được cộng.

Đó là lý do chỉ cần một đường tiếp tục và những phép cộng count cho các nhánh đã xác định chắc chắn nhỏ hơn.

### 21.1. Ví dụ xét t có bit 1 cao

Với `W=4` và `t=8=1000`, tại MSB:

- Nếu XOR bit 0, kết quả chắc chắn nhỏ hơn 8, bất kể ba bit sau. Cộng tất cả khóa trong nhánh XOR bit 0.
- Nếu XOR bit 1, còn phải so với các bit tiếp theo của `t` là `000`; chỉ các kết quả XOR đúng `1000` mới bằng 8, còn `1001..1111` lớn hơn 8.

Với `x=6` và tập ví dụ, nhánh XOR bit 0 tại MSB chứa khóa 3 và 5, nên đáp án `count_xor_less_than(6,8)=2`.

## 22. Độ phức tạp trong mô hình từ máy

Ký hiệu:

- `W`: số bit mỗi khóa.
- `n`: số khóa **phân biệt** đang lưu.
- `P`: số bit tiền tố được hỏi, `0≤P≤W`.
- `N`: số nút hiện có trong trie.
- `w`: số bit trong một từ máy.

Giả sử việc đọc một bit, dịch, AND, XOR các giá trị vừa từ máy và truy cập con trỏ mất O(1).

| Thao tác | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| `contains(x)` | O(W) | O(1) |
| `insert(x)` | O(W), có thể đi hai lượt | O(1) ngoài nút được tạo |
| `delete(x)` | O(W) | O(W) đường cha–con |
| `count_prefix(p,P)` | O(P+1) | O(1) |
| `min_xor(x)`, `max_xor(x)` | O(W) | O(1) |
| `count_xor_less_than(x,t)` | O(W) | O(1) |
| `kth_by_xor(x,k)` | O(W) | O(1) |
| `kth_smallest(k)` | O(W) | O(1) |
| `count_less_than(t)` | O(W) | O(1) |
| `count_range(lo,hi)` | O(W) | O(1) |
| `iter_keys()` hết toàn bộ | O(N) lần thăm nút | Stack O(N), đầu ra O(n) khóa nếu gom danh sách |

### 22.1. Không được gọi O(log n) mặc định

Đường từ gốc tới lá luôn có **W mức**, không phụ thuộc trực tiếp vào `n`. Với W=64 và n=1, vẫn có 64 cạnh.

Vì thế chặn của trie bit là **theo độ rộng khóa W**, không phải tự động O(log n) như một cây nhị phân cân bằng theo số phần tử.

### 22.2. Không được gọi O(1) tuyệt đối khi W rất lớn

Với W=32 hoặc W=64 trên máy hỗ trợ phép toán từ máy tương ứng, các thao tác bit cố định thường rất nhanh và có thể coi từng bước O(1).

Nhưng trong Python, `int` là số nguyên có độ chính xác tùy ý. Với W rất lớn, biểu thức như:

```python
(key >> shift) & 1
```

có thể phải xử lý **nhiều từ máy** cho mỗi lần dịch. Việc làm W phép đọc bit bằng dịch trên big integer không nhất thiết chỉ cần O(W) phép toán bit mức thấp.

Nếu cần xử lý khóa hàng triệu bit, có thể dùng mảng byte/bit hoặc cách truy cập bit đã tiền xử lý để phân tích chi phí đúng theo số từ máy.

### 22.3. Cộng chi phí đối tượng Python

Ngay cả khi mỗi bước bit O(1) trong mô hình trừu tượng, triển khai bằng đối tượng `_BitNode` vẫn có:

- Cấp phát nút.
- Tham chiếu con.
- Overhead `int` của count.
- Cấp phát tuple trong stack hoặc path.
- Thu gom rác.

Độ phức tạp giúp dự đoán xu hướng, không đủ để khẳng định số byte hoặc thời gian đo thực tế.

## 23. Bộ nhớ: chia sẻ tiền tố và giới hạn nút

### 23.1. Chặn thô

Mỗi khóa tạo một đường dài W. Nếu không có chia sẻ, tối đa W nút mới cho mỗi khóa, cộng một gốc:

\[
N\le1+nW.
\]

Vì vậy bộ nhớ cấu trúc của trie bit không nén có chặn:

\[
O(1+nW)
\]

nút khi lưu n khóa phân biệt W bit.

### 23.2. Chặn tốt hơn theo từng độ sâu

Ở độ sâu `d`, một nút tương ứng một tiền tố `d` bit. Có tối đa `2^d` tiền tố khả dĩ và tối đa `n` tiền tố thực sự được các khóa sử dụng.

Vì thế:

\[
N\le
1+\sum_{d=1}^{W}\min(2^d,n).
\]

Công thức này cho thấy:

- Ở các độ sâu nhỏ, số nút bị chặn bởi `2^d`.
- Ở các độ sâu lớn, số nút bị chặn bởi số khóa `n`.
- Khóa có tiền tố chung dài chia sẻ nhiều nút.
- Khóa khác nhau sớm sẽ tạo nhiều nhánh hơn.

### 23.3. Trường hợp tất cả khóa W bit

Nếu Set chứa toàn bộ `2^W` giá trị, trie đầy đủ:

\[
N=1+2+4+\cdots+2^W
=2^{W+1}-1.
\]

Đặt `n=2^W`, ta được:

\[
N=2n-1.
\]

Đây chỉ là một trường hợp đặc biệt của **binary trie đầy đủ**, không phải số nút luôn bằng `2n-1` với mọi Set.

### 23.4. Một khóa đơn lẻ có thể tốn nhiều nút

Nếu `n=1` và W=64, trie không nén giữ:

- Một nút gốc.
- 64 nút trên đường của khóa.

Tổng 65 nút chỉ để biểu diễn một số nguyên. Trong khi một Hash Set thông thường có thể chỉ cần một mục khóa cộng overhead bảng; một **Patricia trie nén** có thể giữ một lá chứa toàn khóa.

Đây là nhược điểm nổi bật của trie bit không nén khi `W` lớn và `n` nhỏ.

### 23.5. Bộ nhớ count và liên kết

Mỗi nút bài học giữ:

- Hai tham chiếu con.
- Một số `count`.
- Metadata của đối tượng và bộ cấp phát.

Một nút không chứa trực tiếp cả số nguyên khóa, nhưng **đường bit và con trỏ** vẫn tiêu tốn bộ nhớ. Không thể suy “không lưu số nguyên ở lá” nghĩa là **không tốn bộ nhớ theo W**.

## 24. Trie bit không nén và Patricia/crit-bit

Cả hai tổ chức khóa theo bit, nhưng có khác biệt quan trọng về biểu diễn.

| Tiêu chí | Binary trie không nén trong bài | Patricia/crit-bit nhị phân |
| --- | --- | --- |
| Mỗi bước | Một vị trí bit liên tiếp | Chỉ những bit cần phân biệt khóa |
| Nút một con | Có thể rất nhiều | Bị loại trong dạng đầy đủ hai con |
| Lá | Ở độ sâu đúng W | Lưu khóa đầy đủ, độ sâu thay đổi |
| Nhãn/chỉ số | Cạnh 0 hoặc 1 | Nút rẽ nhánh ghi vị trí bit |
| Kiểm tra khóa | Đi đủ W bit | Đi theo bit phân biệt **rồi so toàn khóa tại lá** |
| Bộ nhớ nút | Tối đa `1+nW` | `2n-1` nút với n≥1 ở biến thể đầy đủ |
| Đếm XOR theo bit | Tự nhiên, chỉ cần count ở các nhánh | Cần xử lý những bit bị bỏ qua và metadata phù hợp |
| Truy vấn prefix | Đi đúng P bit | Phải kiểm tra các bit chưa được kiểm tra trên đường |
| Cài đặt | Đơn giản, nhiều nút | Ít nút hơn, thao tác splice phức tạp hơn |

### 24.1. Vì sao Patricia có ít nút hơn?

Patricia bỏ các đoạn **chỉ có một con**, giữ lại những vị trí bit thật sự phân tách các khóa. Một nút trong có đúng hai con và lá lưu toàn khóa, nên với n khóa phân biệt:

\[
I=n-1,\qquad N=2n-1.
\]

Trong binary trie thường, mỗi vị trí bit của mỗi đường phải có một nút, kể cả khi mọi khóa trong cây con có cùng bit ở đó.

### 24.2. Vì sao không thay mọi bit trie bằng Patricia?

Số nút ít hơn không tự làm **mọi thao tác** dễ và nhanh hơn.

Ở binary trie, `count_xor_less_than` có thể cộng nhánh `count` ở **từng bit** đơn giản. Trong Patricia, nhiều bit bị bỏ qua, phải suy giá trị của chúng từ khóa đại diện hoặc metadata để biết các nhóm XOR có thuộc ngưỡng hay không.

Khi chọn, cần so số nút, chi phí xây, tính phức tạp cập nhật và các phép truy vấn cần hỗ trợ.

### 24.3. Trie bit có thể nén thành radix nhiều bit mỗi bước

Một biến thể khác là dùng `b` bit mỗi bước, tối đa `2^b` nhánh. Nó giảm số mức xuống khoảng `W/b` nhưng có thể tăng số ô con trỏ mỗi nút, nhất là khi cấp phát mảng con đầy đủ.

Không được chỉ lấy số mức ít hơn rồi kết luận bộ nhớ và thời gian luôn thấp hơn; số nhánh, phân bố dữ liệu và cách lưu nhánh cũng rất quan trọng.

## 25. So sánh với Hash Set, BST và mảng đã sắp

| Cấu trúc | Tìm khóa | MAX XOR | Rank/kth | Prefix bit | Bộ nhớ/chú ý |
| --- | --- | --- | --- | --- | --- |
| Binary bit trie | O(W) | O(W) | O(W) với count | O(P) | Có thể O(nW) nút |
| Hash Set | Kỳ vọng tốt với giả định băm | Không có đường chọn bit; có thể phải quét | Không hỗ trợ tự nhiên | Phải thêm chỉ mục | O(n) mục bảng, phụ thuộc tải/hash |
| BST cân bằng | O(log n) phép so khóa | Không tự tương ứng thứ tự XOR | O(log n) nếu thêm size | Không có chỉ mục tiền tố mặc định | Con trỏ/cân bằng, cần so khóa |
| Mảng số nguyên đã sắp | O(log n) tìm | Có thể phải quét hoặc cấu trúc phụ | O(1) truy cập kth | Tìm biên trên một khoảng số | Chèn/xóa thường O(n) do dịch phần tử |
| Patricia/crit-bit | Theo số nút bit phân biệt + so khóa | Cần thuật toán/metadata bổ sung | Có thể thêm subtree counts | Cần xét bit bị bỏ qua | O(n) nút ở dạng chuẩn |

### 25.1. Tại sao trie bit mạnh ở truy vấn XOR?

Thứ tự khóa trong trie trực tiếp phản ánh **bit cao xuống thấp**. XOR của hai khóa cũng xét từng bit, nên ta có thể chọn nhánh tham lam hoặc cộng count mà không cần sắp lại tập theo mỗi giá trị truy vấn `x`.

Trong mảng số nguyên sắp tăng, thứ tự của các số `key` **không trùng** thứ tự của `key XOR x` khi `x` thay đổi. Vì vậy một binary search số học thông thường không đủ để tối đa XOR.

### 25.2. Khi Hash Set vẫn là lựa chọn hợp lý

Nếu chỉ cần `insert/contains/delete` của số nguyên đầy đủ và không cần tiền tố bit, XOR, rank hoặc kth, Hash Set thường gọn về mã và có hiệu năng kỳ vọng tốt.

Không nên áp trie bit cho mọi bài toán chỉ vì khóa là số nguyên.

### 25.3. Khi mảng đã sắp có lợi

Nếu dữ liệu gần như bất biến, truy vấn chủ yếu là rank, kth và khoảng số, một mảng sắp tăng có **locality tốt**, cho kth O(1) và đếm khoảng bằng hai lần binary search.

Trie bit thuận tiện khi cần **cập nhật thường xuyên** cùng các truy vấn bit có cấu trúc; mảng thường cần dịch phần tử khi chèn hoặc xóa.

## 26. Số có dấu và cách mã hóa thứ tự

Bài học cốt lõi chỉ nhận số nguyên không âm trong miền `[0,2^W)`. Nếu cần khóa có dấu, không được đưa số âm Python vào phép dịch trong cùng thuật toán mà không quy định cách mã hóa.

### 26.1. Hai's complement có độ rộng cố định

Trong biểu diễn bù hai `W` bit, số có dấu nằm trong:

\[
-2^{W-1}\le x<2^{W-1}.
\]

Ví dụ W=4:

```text
-1  -> 1111
-2  -> 1110
 0  -> 0000
 3  -> 0011
```

Nếu xem chuỗi bit đó như **số không dấu**, `1111` là 15 chứ không phải -1. Vì vậy `kth_smallest` không tự cho **thứ tự có dấu**.

### 26.2. Biến đổi để bảo toàn thứ tự có dấu

Một kỹ thuật là lật **bit dấu MSB**:

\[
encoded(x)=twosComplement_W(x)\oplus2^{W-1}.
\]

Khi đó thứ tự không dấu của `encoded(x)` tương ứng với thứ tự tăng của số có dấu trong miền W bit. Tuy nhiên:

- Prefix bit lúc này được hiểu theo **khóa đã biến đổi**, không phải trực tiếp dãy bù hai ban đầu.
- Nếu dùng XOR, cần mã hóa **cả khóa lưu và x truy vấn** cùng phép lật bit dấu. Khi đó:
  \[
  (a\oplus mask)\oplus(b\oplus mask)=a\oplus b
  \]
  với các dãy W bit tương ứng.
- Các phương thức trả khóa cần **giải mã** trở lại số có dấu, không chỉ trả số không dấu.

### 26.3. Tránh nhầm XOR có dấu với so sánh có dấu

Trong bài, giá trị `x XOR key` được **so như số không dấu W bit**. Nếu sản phẩm muốn **so kết quả XOR như số có dấu**, thứ tự MSB cần xử lý theo bit dấu; quy tắc ưu tiên XOR bit 1 ở MSB không còn là quy tắc tối đa số có dấu.

Không được áp nguyên thuật toán max XOR không dấu cho mục tiêu max XOR có dấu mà không biến đổi quan hệ so sánh.

## 27. Multiset và dữ liệu chứa giá trị trùng

Một số bài toán thực tế nhận **dãy số có phần tử lặp**. Khi đó có hai ngữ nghĩa:

1. **Set:** mỗi giá trị phân biệt chỉ được tính một lần.
2. **Multiset:** mỗi lần xuất hiện của giá trị được tính là một phần tử, có thể có nhiều bản sao.

### 27.1. Ví dụ hai ngữ nghĩa khác nhau

Dữ liệu:

```text
[3, 3, 5]
```

Với `W=4`:

- Trong Set: `size=2`, `count_prefix(0,1)=2`.
- Trong Multiset: `size=3`, `count_prefix(0,1)=3`.

Với truy vấn `count_xor_less_than(6,8)`:

- Set đếm khóa 3 và 5, kết quả 2.
- Multiset đếm cả hai bản sao 3 và một bản sao 5, kết quả 3.

### 27.2. Cần thay gì để hỗ trợ Multiset?

Có thể đổi hợp đồng:

- Lá có `frequency≥1` thay vì count chỉ là 0 hoặc 1.
- `count(v)` là **tổng tần suất** mọi khóa trong cây con.
- Chèn mỗi lần tăng count trên đường, tăng frequency của lá.
- Xóa một lần giảm count và frequency; chỉ gỡ nhánh khi tổng tần suất về 0.
- `kth_smallest` và `kth_by_xor` chọn theo **thứ tự có lặp**.

Các thuật toán `count_xor_less_than` và rank vẫn dùng cách cộng subtree counts, nhưng ý nghĩa mỗi count đã chuyển từ **số khóa phân biệt** sang **số lần xuất hiện**.

### 27.3. Không sửa một nửa cấu trúc

Nếu chỉ bỏ kiểm tra khóa trùng trong `insert` mà vẫn giữ `contains` hay validator giả định lá count=1, chương trình sẽ vi phạm bất biến.

Khi đổi Set sang Multiset, phải sửa **đồng bộ** đặc tả, leaf frequency, chèn/xóa, kích thước, kth, validator và bộ kiểm thử.

## 28. Ứng dụng thường gặp

### 28.1. Tối đa XOR với một phần tử của tập

Cho một tập khóa W bit và nhiều truy vấn `x`, xây trie một lần rồi trả `max_xor(x)` trong O(W) mỗi truy vấn.

Nếu muốn **cặp số trong tập có XOR lớn nhất**, với n≥2, có thể truy vấn `max_xor(x)` cho từng `x∈K` rồi chọn giá trị lớn nhất. Tổng chi phí sau khi xây là O(nW) trong mô hình đã nêu.

Với n=1, không có **cặp hai vị trí phân biệt**; cần đặc tả rõ có cho phép ghép một phần tử với chính nó hay không. Một số bài toán cạnh tranh cho phép, một số thì không.

### 28.2. Đếm số cặp XOR nhỏ hơn K

Giả sử dữ liệu **không có phần tử trùng**. Duyệt dãy từ trái sang phải:

1. Trước khi chèn phần tử hiện tại `x`, trie chứa các phần tử ở vị trí trước.
2. Cộng `count_xor_less_than(x,K)` vào đáp án.
3. Chèn `x` vào trie.

Mỗi cặp vị trí `i<j` được xét đúng một lần tại thời điểm xử lý `j`. Tổng thời gian O(nW).

**Nhưng:** nếu dãy có phần tử trùng, `BitTrieSet` sẽ bỏ các bản sao và **đếm thiếu cặp**. Khi ấy phải dùng Multiset hoặc lưu tần suất theo cách khác.

### 28.3. Chỉ mục địa chỉ/khối bit

Các địa chỉ mạng có độ dài bit cố định có thể được nhìn như khóa nhị phân; truy vấn theo tiền tố bit giúp thống kê các địa chỉ chung một đoạn đầu.

Đây chỉ là phép **đếm các khóa trong một Set**, không tự là thuật toán định tuyến *longest prefix match* hoàn chỉnh: định tuyến thường lưu **các tiền tố độ dài khác nhau** cùng payload tại các nút trung gian, một đặc tả khác với lá W bit.

### 28.4. Thống kê theo khoảng số

`count_less_than` và `count_range` hỗ trợ đếm động số phần tử nằm trong một khoảng, khi khóa có độ rộng cố định.

Nếu miền giá trị nhỏ và dày, một mảng tần suất + prefix sums có thể đơn giản hơn, đặc biệt khi dữ liệu bất biến. Nếu miền rất lớn nhưng dữ liệu thưa, trie bit có thể tránh cấp phát một mảng `2^W` ô — đánh đổi bằng các nút con trỏ.

### 28.5. Các truy vấn có biến đổi XOR

Trong một số bài toán, người ta muốn hỏi phần tử thứ k sau khi XOR tất cả giá trị với một `mask`. Thay vì thực sự sửa tất cả khóa, có thể giữ khóa gốc trong trie và dùng `kth_by_xor(mask,k)` để đọc thứ tự XOR.

Nếu **mask thay đổi theo từng truy vấn**, vẫn không cần xây lại trie, miễn dữ liệu khóa gốc không thay đổi. Đây là một lợi thế lớn của cách tổ chức theo bit.

## 29. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Không quy định W | Một khóa có nhiều biểu diễn bit khác độ dài | Chọn W cố định khi tạo trie |
| Đọc LSB trước khi muốn tối ưu số không dấu | Greedy max XOR chọn sai bit ưu tiên | Đi từ MSB xuống LSB |
| Dùng số âm Python trực tiếp | Dịch phải giữ dấu, sai miền khóa | Kiểm tra khóa không âm và W bit |
| Chấp nhận `key=2^W` | Đường W bit bỏ bit cao, va chạm khóa khác | Yêu cầu `key<2^W` |
| Tăng count khi chèn trùng | Count/size/rank/kth sai | Chặn khóa trùng trước tăng |
| Xóa khóa thiếu nhưng vẫn giảm count | Count âm, mất nút hoặc mất khóa khác | Xác nhận contains trước xóa |
| Xóa cả đường dù còn khóa chia sẻ tiền tố | Mất các khóa khác | Chỉ gỡ nhánh count về 0 |
| Gắn terminal ở độ sâu giữa rồi dùng API W bit | Đếm sai khóa hoàn chỉnh | Mọi khóa phải kết thúc ở độ sâu W |
| Tiền tố `0` không kèm chiều dài | Nhầm `0` với `00` hoặc tiền tố rỗng | Dùng cặp `(prefix,length)` |
| Tối đa XOR bằng số bit 1 lớn nhất | Nhầm với khoảng cách Hamming | So giá trị số không dấu từ MSB |
| Tìm max XOR bằng nhánh cùng bit | Thực ra ưu tiên XOR 0 | Max chọn **đối bit** khi có |
| Tìm min XOR bằng nhánh đối bit | Tạo XOR bit 1 không cần thiết | Min chọn **cùng bit** khi có |
| Cộng count nhánh XOR 1 khi threshold bit 1 | Đếm sai `(x XOR y)<t` | Cộng nhánh XOR 0, tiếp tục XOR 1 |
| Tính cả đường có XOR bằng threshold | Biến `<` thành `≤` | Không cộng đường bằng sau hết W bit |
| Từ chối ngưỡng `2^W` | Không thể biểu diễn “đếm toàn bộ” | Bound thuộc `[0,2^W]` |
| `kth` không trừ count nhánh bị bỏ | Chọn sai thứ hạng | Khi đi nhánh 1, `k-=count0` |
| Quên trường hợp trie rỗng | Lấy nhánh None hoặc trả XOR 0 giả | Trả None cho min/max, IndexError cho kth |
| Gọi trie bit luôn O(log n) | Đường dài W, không theo số phần tử | Ghi O(W) theo độ rộng bit |
| Gọi mọi phép Python big-int O(1) | Bỏ chi phí xử lý nhiều từ máy | Nêu giả định word-RAM/bit-array |
| Nói trie bit luôn O(n) nút | Có thể tới `1+nW` | Tính số nút theo n và W |
| Áp dụng mã Set cho dãy có trùng | Đếm thiếu theo tần suất hoặc cặp | Dùng Multiset nếu cần |
| Đổi sang thứ tự signed mà không đổi encoding | Kth/rank có dấu sai | Quy định bù hai và biến đổi bit dấu |
| Quên kiểm thử W=1, khóa 0, bound tối đa | Lỗi biên khó phát hiện | Thử toàn miền nhỏ với oracle Set |

## 30. Bài tập vận dụng có gợi ý

### Bài 1 — Biểu diễn khóa

Với W=5, hãy viết dãy bit của các khóa 0, 3, 17 và 31. Khóa 32 có hợp lệ không?

**Gợi ý:** `00000,00011,10001,11111`; 32 không hợp lệ vì `32=2^5`.

### Bài 2 — Đọc bit MSB

Với W=4, khóa 10 = `1010`, các bit khi đi trie theo MSB-first lần lượt là gì?

**Gợi ý:** `1,0,1,0`.

### Bài 3 — Vẽ đường trie

Chèn 3 = `0011` và 5 = `0101` vào trie W=4. Hai khóa chia sẻ mấy bit đầu và tách nhau ở đâu?

**Gợi ý:** Cùng bit đầu 0, khác ở bit thứ hai: 0 so với 1.

### Bài 4 — Chèn trùng

Trie chứa `{3,5}`. Gọi `insert(3)` lần nữa. `count(root)` và số khóa hợp lệ là bao nhiêu?

**Gợi ý:** Đều vẫn bằng 2. Chèn trùng trả False.

### Bài 5 — Xóa khóa chia sẻ tiền tố

Trie có khóa 3 và 5, cùng bắt đầu bằng 0. Xóa 3 thì có được xóa nhánh bit đầu 0 không?

**Gợi ý:** Không. Nhánh này còn chứa khóa 5, count phải còn 1.

### Bài 6 — Tiền tố có số 0 ở đầu

Với `K={3,5,10,12}` W=4, `count_prefix(0b00,2)` và `count_prefix(0b0,1)` lần lượt bằng bao nhiêu?

**Gợi ý:** 1 và 2; chiều dài tiền tố rất quan trọng.

### Bài 7 — Tiền tố rỗng

Nếu trie có 4 khóa, `count_prefix(0,0)` bằng bao nhiêu?

**Gợi ý:** 4; mọi khóa đều có tiền tố rỗng.

### Bài 8 — XOR thủ công

Cho `x=6` và `y=10` trong W=4. Tính XOR dạng nhị phân và thập phân.

**Gợi ý:** `0110 XOR 1010 = 1100 = 12`.

### Bài 9 — XOR lớn nhất

Cho `K={3,5,10,12}` và `x=6`. Khóa nào tạo XOR lớn nhất?

**Gợi ý:** Khóa 10, giá trị XOR 12.

### Bài 10 — XOR nhỏ nhất

Với cùng K và x, khóa nào tạo XOR nhỏ nhất?

**Gợi ý:** Khóa 5, giá trị XOR 3.

### Bài 11 — XOR và Hamming

Với `x=0`, hai khóa 8 và 7 có giá trị XOR nào lớn hơn? Khóa nào có nhiều bit khác x hơn?

**Gợi ý:** XOR 8 lớn hơn 7, nhưng 7 có nhiều bit 1 hơn 8. Giá trị số XOR khác khoảng cách Hamming.

### Bài 12 — Đếm XOR nhỏ hơn t

Với `K={3,5,10,12}` và `x=6`, có bao nhiêu khóa cho XOR nhỏ hơn 8?

**Gợi ý:** Hai khóa 3 và 5, tạo XOR 5 và 3.

### Bài 13 — Ngưỡng bằng toàn miền

Với W=4 và trie có n khóa, `count_xor_less_than(x,16)` bằng bao nhiêu cho x hợp lệ?

**Gợi ý:** Bằng n, vì XOR của hai số W bit luôn nhỏ hơn `2^W`.

### Bài 14 — So sánh nghiêm ngặt

Với K ví dụ, `count_xor_less_than(6,12)` có đếm khóa 10 không?

**Gợi ý:** Không. Khóa 10 tạo XOR đúng 12; hàm đếm `<12` nên trả 3.

### Bài 15 — Phần tử nhỏ thứ k

Với K sắp `[3,5,10,12]`, `kth_smallest(2)` là gì nếu k bắt đầu 0?

**Gợi ý:** 10.

### Bài 16 — Thứ k theo XOR

Với `x=6`, liệt kê bốn cặp `(key,xor)` theo XOR tăng.

**Gợi ý:** `(5,3),(3,5),(12,10),(10,12)`.

### Bài 17 — Đếm nhỏ hơn

Với K ví dụ, `count_less_than(11)` và `count_range(4,11)` là gì?

**Gợi ý:** 3 và 2.

### Bài 18 — Bộ nhớ một khóa duy nhất

Với W=64 và một khóa, binary trie không nén có bao nhiêu nút nếu tính cả gốc?

**Gợi ý:** 65 nút. Patricia có thể lưu một lá toàn khóa trong biến thể đầy đủ hai con.

### Bài 19 — Giới hạn nút

Với n khóa W bit, nêu chặn trên đơn giản của số nút binary trie.

**Gợi ý:** `N≤1+nW`. Chia sẻ tiền tố làm số nút thực tế ít hơn.

### Bài 20 — Signedness

Tại sao các giá trị bù hai W=4 của -1 và 3 không thể được xếp theo signed order bằng `kth_smallest` không dấu của bài?

**Gợi ý:** -1 mã hóa `1111` = 15 nếu xem không dấu; nó đứng sau 3. Cần đổi encoding, ví dụ lật bit dấu.

### Bài 21 — Dãy có phần tử trùng

Dãy `[3,3,5]` được dùng để đếm **cặp vị trí** XOR nhỏ hơn ngưỡng. Tại sao `BitTrieSet` có thể đếm sai?

**Gợi ý:** Nó chỉ lưu 3 một lần; cần Multiset giữ tần suất.

### Bài 22 — Mô hình thời gian

Tại sao hàm `count_xor_less_than` là O(W) trong mô hình word-RAM nhưng không được khẳng định chạy O(W) thao tác máy cho khóa một triệu bit trong Python?

**Gợi ý:** Phép dịch trên số nguyên nhiều từ máy có thể tốn chi phí phụ thuộc độ dài số.

### Bài 23 — Chọn cấu trúc

Một hệ chỉ cần kiểm tra khóa nguyên có trong tập không. Một hệ khác thường hỏi max XOR và count XOR less-than. Hãy đề xuất cấu trúc.

**Gợi ý:** Hash Set phù hợp hệ chỉ kiểm tra; trie bit có lợi hệ cần truy vấn theo bit, nhưng phải đo RAM và W.

### Bài 24 — Kiểm chứng bất biến

Nêu ba điều kiện quan trọng cho hàm `validate_bit_trie`.

**Gợi ý:** Count tại nút trong bằng tổng count hai con; lá độ sâu W có count=1; nút không phải gốc không có count=0.

## 31. Checklist trước khi dùng trie bit

```text
1. Hợp đồng:
   - Khóa là số nguyên không âm W bit?
   - W cố định khi tạo trie?
   - Có cho phép bản sao (Multiset) không?
   - Mục tiêu là unsigned XOR hay signed XOR?
   - Phần tử kth đánh số từ 0 hay 1?

2. Biểu diễn:
   - Duyệt từ MSB tới LSB?
   - Mỗi mức đúng một bit?
   - Root ở độ sâu 0, lá ở độ sâu W?
   - Count của nút trong bằng tổng count hai con?
   - Không có con count=0 sau xóa?

3. Cập nhật:
   - Chèn trùng không làm thay đổi count?
   - Xóa thiếu không làm thay đổi count?
   - Chỉ tăng/giảm count ở đường khóa?
   - Chỉ gỡ nhánh đã hết khóa sống?
   - Xóa khóa cuối cùng có về root rỗng?

4. Tiền tố và thứ tự:
   - Prefix truyền cả giá trị và độ dài?
   - Count prefix lấy count ở nút sau P bước?
   - Kth theo số chọn nhánh 0 trước 1?
   - Khi đi nhánh 1, có trừ count nhánh 0?
   - Khoảng số dùng [low,high) nhất quán?

5. XOR:
   - Max ưu tiên bit XOR 1 từ MSB?
   - Min ưu tiên bit XOR 0?
   - Kth_by_xor ưu tiên nhánh XOR 0 rồi 1?
   - Count XOR < t cộng nhánh XOR 0 khi tbit=1?
   - Ngưỡng bằng 2^W có trả toàn bộ size?
   - So sánh < có loại bỏ trường hợp bằng không?

6. Chi phí:
   - O(W) có dựa trên bit operation O(1)?
   - Nếu W rất lớn, có tính chi phí big-int?
   - Số nút có thể O(nW), không mặc định O(n)?
   - Có cần Patricia để giảm nút một con?
   - Có đo RAM đối tượng, không chỉ đếm nút?

7. Kiểm thử:
   - W=1, key=0, key=2^W-1?
   - Trie rỗng, chèn trùng, xóa thiếu?
   - Prefix có nhiều bit 0 đầu?
   - Bound=0, bound=2^W, bound ngoài miền?
   - Max/min XOR và kth_by_xor theo oracle Set?
   - Count_xor_less_than đối chiếu brute-force?
   - Count tại nút có đúng qua nhiều vết cập nhật?
```

## 32. Tổng kết

**Trie bit nhị phân** tổ chức các số nguyên không âm có độ rộng cố định `W` thành những đường gồm W bit, đọc từ **MSB tới LSB**. Mỗi nút có nhánh `zero`, `one` và bộ đếm số khóa trong cây con.

Từ một bất biến `count` nhất quán, ta có thể hỗ trợ:

- **Set cơ bản:** tìm, chèn và xóa khóa trong O(W).
- **Tiền tố bit:** đếm trong O(P) theo số bit của tiền tố.
- **Tối ưu XOR:** max/min XOR trong O(W), nhờ ưu tiên bit XOR cao nhất.
- **Đếm theo XOR:** đếm `(key XOR x)<t` trong O(W), bằng cách cộng cả nhánh khi kết quả đã chắc chắn nhỏ hơn ngưỡng.
- **Thứ tự số và XOR:** kth, rank, đếm khoảng số và thứ k theo XOR trong O(W).

Những chặn này dựa trên **mô hình thao tác bit/đọc con trỏ O(1)**. Trie bit không nén có thể giữ tới `1+nW` nút, nên kém tiết kiệm bộ nhớ khi W lớn và số khóa ít; Patricia có thể nén các đường một con nhưng làm xử lý các bit bị bỏ qua phức tạp hơn.

Trước khi áp dụng, hãy xác định **độ rộng, signedness, Set hay Multiset, chiều dài tiền tố, quy ước ngưỡng nghiêm ngặt và mô hình chi phí thực tế**. Một cấu trúc dữ liệu chỉ phát huy ưu thế khi bất biến của nó khớp với đúng phép truy vấn mà ứng dụng cần.

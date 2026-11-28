# Trie nhị phân và đường đi theo các bit của khóa

Với tập khóa số nguyên, ta thường nghĩ tới mảng, bảng băm hoặc cây tìm kiếm cân bằng. Nhưng mỗi khóa nguyên còn có một cách nhìn khác: **một dãy bit có độ dài xác định**. Thay vì so sánh toàn bộ khóa với các khóa ở một nút, ta có thể đi qua một cây mà **mỗi tầng đọc một bit của khóa**, chọn cạnh 0 hoặc cạnh 1. Cấu trúc này gọi là **trie nhị phân** (*binary trie*, *bitwise trie*).

Ví dụ, số `13` có biểu diễn 4 bit là `1101`. Nếu đọc từ bit cao xuống bit thấp, đường đi của nó là:

```text
                     (gốc)
                        |
                      bit 1
                        |
                      bit 1
                        |
                      bit 0
                        |
                      bit 1
                        |
                    khóa 1101
```

Trong một trie chứa nhiều khóa, **các khóa có cùng tiền tố bit chia sẻ đoạn đường đầu**, nên ta không phải lưu một cây đường đi hoàn toàn riêng cho từng khóa. Ta có thể dùng trie để kiểm tra khóa có tồn tại, thêm/xóa, tìm khóa nhỏ nhất/lớn nhất theo một quy ước thứ tự, tìm tiền nhiệm/kế nhiệm, đếm khóa có cùng tiền tố và tìm khóa tối ưu theo XOR.

Trong chương **Khóa số nguyên**, trie nhị phân là một ví dụ điển hình của việc khai thác **miền khóa hữu hạn và kích thước từ máy**. Nó bổ sung góc nhìn cho bảng địa chỉ trực tiếp, bitset, bảng băm và cây cân bằng: thay vì phụ thuộc vào số khóa `n` một cách trực tiếp, chiều dài đường đi phụ thuộc vào **số bit `w` của khóa**.

Bài này bắt đầu từ biểu diễn bit, xây bất biến nút và thuật toán, phân tích O(w) và O(nw), rồi cài đặt một **binary trie Java cho toàn bộ miền `int` có dấu** với thêm/xóa, truy vấn thứ tự, đếm tiền tố, cực đại XOR và bộ kiểm tra độc lập bằng `TreeSet`.

## 1. Miền khóa, số bit và tham số độ phức tạp

Cho tập `S` gồm `n` khóa nguyên phân biệt thuộc một miền hữu hạn có `U` giá trị khả dĩ. Nếu chuẩn hóa chỉ số miền về `0..U-1`, số bit tối thiểu để mã hóa các khả năng là:

\[
b=\lceil\log_2 U\rceil
\]

với `U\ge2`. Để minh họa thuật toán, ta thường dùng các khóa có **đúng `w` bit**, kể cả những bit 0 ở đầu.

| Đại lượng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `U` | Số khóa có thể có trong miền | Các mẫu bit của `int`: `2^{32}` |
| `n` | Số khóa đang lưu | Có 10.000 ID đang hoạt động |
| `w` | Độ dài bit của biểu diễn khóa dùng trong trie | `w=32` với `int` Java |
| `h` | Chiều sâu đường từ gốc tới khóa trong trie chưa nén | `h=w` |

Với trie cố định `w` tầng, một đường đi tới lá có **đúng `w` cạnh**. Nếu `w=32`, tìm một khóa tiêu chuẩn cần xét tối đa 32 bit. Nếu coi `w` là **hằng số của môi trường**, số bước bị chặn; nhưng trong phân tích cấu trúc dữ liệu tổng quát, ta nên ghi rõ:

\[
T_{\text{lookup}}=O(w),
\]

không chỉ viết O(1) mà bỏ qua giả định về độ rộng khóa.

### Vì sao `w` không nhất thiết bằng `\lceil\log_2 n\rceil`?

Tập có 100 ID `int` bất kỳ vẫn phải phân biệt được **các ID trong miền 32 bit**, dù hiện tại `n=100`. Ta không thể tự gán cho mỗi ID một mã 7 bit nếu không có thêm **bảng ánh xạ** và cơ chế duy trì nó.

Trie có thể tận dụng các tiền tố chung, nhưng đường đi biểu diễn từng khóa nguyên gốc vẫn dựa vào **độ dài mã khóa**, không phải chỉ số thứ tự của khóa trong tập.

### Trie bit khác cây tìm kiếm nhị phân (BST)

| Đặc điểm | Trie nhị phân theo bit | BST |
| --- | --- | --- |
| Hai cạnh con | Chọn theo bit `0` hay `1` ở tầng hiện tại | Chọn theo so sánh khóa `<` hay `>` khóa tại nút |
| Khóa dữ liệu | Thường nằm ở lá sau `w` bit, hoặc nút kết thúc | Thường nằm tại mỗi nút |
| Chiều dài đường tìm | O(w) với trie chưa nén | O(h), phụ thuộc độ cao cây |
| Cân bằng bằng phép quay | Không cần quay để bảo đảm đường bit dài `w` | AVL/Red-Black dùng quay/đổi màu |
| Dùng tiền tố | Tự nhiên vì các khóa chia sẻ tiền tố bit | Không phải mục tiêu chính |
| Bộ nhớ | Có thể cần O(nw) nút | O(n) nút |

Tên gọi “nhị phân” trong hai cấu trúc **không có nghĩa chúng cùng một bất biến**. Trie chọn đường theo **chữ số nhị phân của khóa**; BST chọn theo **quan hệ thứ tự với khóa chứa tại nút**.

## 2. Chọn hướng đọc bit: từ cao xuống thấp

Một số nguyên 4 bit `x` có dạng:

\[
x=b_3b_2b_1b_0,\quad b_i\in\{0,1\}.
\]

Trie trong bài đọc theo thứ tự **MSB-first** (*most significant bit first*): `b_3`, sau đó `b_2`, `b_1`, cuối cùng `b_0`.

Ví dụ tập:

\[
S=\{2,3,8,10,11,13\}
\]

với biểu diễn 4 bit:

| Khóa | Bit cố định 4 bit |
| ---: | --- |
| 2 | `0010` |
| 3 | `0011` |
| 8 | `1000` |
| 10 | `1010` |
| 11 | `1011` |
| 13 | `1101` |

Trie có thể hình dung:

```text
                         root
                       /0    \1
                      /        \
                    [0]        [1]
                    /0         /0  \1
                   /          /     \
                 [00]       [10]    [11]
                   \1        /0 \1    \0
                    \       /    \     \
                   [001]  [100] [101] [110]
                   / \      /    / \     \1
                  0   1    0    0   1     \
                 2    3    8   10  11     13
```

Sơ đồ chỉ hiển thị các nhánh **đang có khóa**. Trong cài đặt thực tế, mỗi nút chỉ cần hai tham chiếu `child[0]` và `child[1]`, cộng thông tin bổ trợ nếu muốn đếm khóa hoặc phục vụ truy vấn.

### Vì sao MSB-first hữu ích cho thứ tự?

Với **các số không dấu có cùng `w` bit**, so sánh thứ tự từ bit cao tới thấp có tính chất:

1. Tìm vị trí bit **đầu tiên khác nhau** của hai khóa.
2. Ở vị trí ấy, khóa có bit 0 nhỏ hơn khóa có bit 1.
3. Những bit thấp hơn không thể đảo ngược kết luận.

Vì vậy, nếu một nút có cả hai con và các khóa được hiểu theo **thứ tự không dấu**, toàn bộ khóa dưới nhánh 0 **nhỏ hơn** toàn bộ khóa dưới nhánh 1.

Đi từ gốc **ưu tiên nhánh 0** ở mỗi tầng tìm khóa nhỏ nhất; ưu tiên nhánh 1 tìm khóa lớn nhất. Quy tắc này **chỉ đúng với thứ tự khóa tương ứng với biểu diễn bit**. Với Java `int` có dấu, cần chú ý thêm bit dấu.

## 3. Khóa có dấu: làm thế nào để trie giữ đúng thứ tự Java `int`?

`int` của Java có 32 bit, từ:

\[
-2^{31}\le x\le 2^{31}-1.
\]

Số âm có **bit dấu 1**, số không âm có **bit dấu 0**. Nếu cứ duyệt nhánh 0 trước nhánh 1 trên biểu diễn nguyên gốc, các số không âm sẽ đứng **trước số âm**, tương ứng thứ tự **không dấu**, không phải thứ tự số nguyên có dấu của Java.

Ví dụ `-1` có mẫu bit `111\ldots111`, còn `0` là `000\ldots000`. Theo so sánh có dấu:

\[
-1<0.
\]

Nhưng theo thứ tự **mẫu bit không dấu**, `0` lại đứng trước `-1`.

### Biến đổi bằng cách đảo bit dấu

Một kỹ thuật rất tiện là chuẩn hóa khóa:

```java
int code = key ^ Integer.MIN_VALUE;
```

Vì `Integer.MIN_VALUE` có mẫu bit `1000...0000`, phép XOR đảo **duy nhất bit dấu**:

- Số âm (bit dấu 1) → mã có bit cao 0.
- Số không âm (bit dấu 0) → mã có bit cao 1.

Khi so sánh các mã `code` theo **thứ tự không dấu/MSB-first**, thứ tự thu được **trùng với thứ tự có dấu của khóa gốc**.

### Minh họa trên 8 bit

Nếu mô phỏng kiểu số nguyên **có dấu 8 bit**, đảo bit dấu bằng XOR `1000\,0000`:

| Giá trị có dấu | Bit gốc | Bit sau XOR dấu |
| ---: | --- | --- |
| -128 | `1000 0000` | `0000 0000` |
| -3 | `1111 1101` | `0111 1101` |
| -1 | `1111 1111` | `0111 1111` |
| 0 | `0000 0000` | `1000 0000` |
| 2 | `0000 0010` | `1000 0010` |
| 127 | `0111 1111` | `1111 1111` |

Duyệt mã từ thấp tới cao theo thứ tự từ bit cao (ưu tiên 0) sẽ gặp đúng:

```text
-128, -3, -1, 0, 2, 127
```

Trong chương trình Java 32 bit, phép biến đổi tương tự trên 32 bit; muốn chuyển **mã đi qua trie** về **khóa có dấu ban đầu**, chỉ cần XOR lần nữa:

```java
int key = code ^ Integer.MIN_VALUE;
```

Vì `(x XOR m) XOR m = x`, đây là phép đổi **song ánh**, không làm mất thông tin.

### Lấy từng bit an toàn trong Java

Với `shift` từ 31 xuống 0:

```java
int bit = (code >>> shift) & 1;
```

Toán tử `>>>` là **dịch phải không dấu**, điền bit 0 ở đầu. Phần `& 1` lấy đúng bit cần dùng dù `code` được lưu dưới dạng số `int` âm hay dương.

**Không dùng** phép `key & (1 << shift)` rồi so sánh `> 0` để xác định bit, vì khi `shift=31`, mask có bit dấu và là số âm: kiểm tra `>0` có thể trả sai. Dùng `!=0` hoặc `(code >>> shift)&1`.

## 4. Cấu trúc nút và các bất biến

Một trie nhị phân cơ bản có thể dùng:

```text
Node:
    zero      -> nút con ứng với bit 0, có thể null
    one       -> nút con ứng với bit 1, có thể null
    pass      -> số khóa hiện có trong cây con của nút
    terminal  -> true nếu đường đi đã biểu diễn đủ khóa
```

Trong mô hình **khóa cố định 32 bit, không trùng** của bài:

- Gốc ở **độ sâu 0**.
- Mỗi cạnh đi xuống đọc **một bit**.
- Một khóa hoàn chỉnh kết thúc ở **độ sâu 32** (sau 32 cạnh).
- Các nút chưa tới độ sâu 32 **không phải nút kết thúc khóa**.
- Một lá hoàn chỉnh có `terminal=true` và giữ **một khóa**.
- `pass` của nút bằng số khóa phân biệt hiện có trong toàn bộ cây con của nó.

### Bất biến bộ đếm cây con

Với nút trong ở độ sâu nhỏ hơn 32:

\[
\boxed{
pass(node)=pass(node.zero)+pass(node.one)
}
\]

trong đó con trỏ `null` đóng góp 0.

Với nút lá ở độ sâu 32 có khóa:

\[
pass(leaf)=1,\qquad terminal(leaf)=true.
\]

Ở gốc:

\[
\boxed{pass(root)=size=n.}
\]

Số `pass` giúp thực hiện `countWithPrefix` và xác minh cấu trúc. Nếu không cần đếm tiền tố và không lưu khóa trùng, có thể tạo một trie gọn hơn chỉ gồm các con trỏ và dấu kết thúc; nhưng ví dụ này cố ý có `pass` để minh họa bất biến.

### Những bất biến về cấu trúc

1. Mỗi nút có tối đa hai con: nhánh 0 và nhánh 1.
2. Từ một nút, cạnh 0 và cạnh 1 không được cùng trỏ tới **một đối tượng con**.
3. Không có chu trình và không có một nút dùng chung theo hai đường cha–con trong mô hình cây.
4. Khi đã xóa hết khóa của một nhánh, có thể **cắt nhánh rỗng**, thay vì giữ các nút `pass=0` ngoài gốc.
5. Với trie chưa nén, mọi khóa kết thúc sau đúng 32 bit; không có khóa là tiền tố đầy đủ của khóa khác, vì độ dài luôn bằng nhau.
6. Gốc có thể tồn tại với `pass=0`, nhưng phải không còn con trỏ tới nút hoạt động.

Đây là các điều kiện bộ kiểm tra sẽ đọc **trực tiếp từ cấu trúc**, không tin rằng thuật toán thêm/xóa đã cập nhật đúng.

## 5. Tìm một khóa: đi theo bit và không suy từ tiền tố

Để kiểm tra một khóa `x`:

1. Chuẩn hóa `code=x XOR SIGN_MASK` nếu cần giữ thứ tự có dấu.
2. Bắt đầu tại gốc.
3. Với `bitIndex=31,30,\ldots,0`, lấy bit của `code`.
4. Đi tới `zero` hoặc `one` tương ứng.
5. Nếu thiếu con trỏ, khóa không tồn tại.
6. Sau đủ 32 bước, kiểm tra nút kết thúc.

Mã giả:

```text
contains(x):
    code = x XOR signMask
    node = root
    for shift = 31 down to 0:
        b = (code unsignedRightShift shift) AND 1
        node = (b == 0) ? node.zero : node.one
        if node == null:
            return false
    return node.terminal
```

Một đường đi có thể tồn tại **một phần** vì nhiều khóa chia sẻ tiền tố. **Không được kết luận một khóa có mặt chỉ vì đi được 5 bit đầu**: phải xét đủ độ dài biểu diễn khóa.

### Ví dụ

Giả sử trie 4 bit có `0010` và `0011`:

```text
root
  └─0─0─1
           ├─0  -> 0010
           └─1  -> 0011
```

Hỏi `0001`: đường đi từ gốc tới `000` không có con phù hợp, nên trả `false`. Hỏi `0010`: phải đi đủ 4 cạnh và tìm thấy dấu khóa ở lá.

**Độ phức tạp:** O(w) bước, bất kể số khóa hiện lưu là bao nhiêu, với phép đọc bit và truy cập con trỏ O(1) mỗi tầng trong mô hình RAM.

## 6. Chèn khóa mới và chia sẻ tiền tố

Thuật toán `add(x)`:

1. Nếu `contains(x)` đã đúng, trả `false` để tránh khóa trùng.
2. Chuẩn hóa và đọc lần lượt các bit từ cao xuống thấp.
3. Nếu cạnh cần đi chưa tồn tại, tạo nút con mới.
4. Đi qua các nút trên đường và tăng `pass` mỗi nút đúng một.
5. Đánh dấu `terminal=true` ở lá 32 bit.
6. Tăng `size` đúng một và trả `true`.

```text
add(x):
    if contains(x):
        return false
    code = encodeSigned(x)
    root.pass++
    node = root
    for shift = 31 down to 0:
        b = bitAt(code, shift)
        if child(node, b) == null:
            create child(node, b)
        node = child(node, b)
        node.pass++
    node.terminal = true
    size++
    return true
```

### Chèn hai khóa cùng tiền tố

Xét khóa không dấu 4 bit:

```text
add(10) -> 1010
add(11) -> 1011
```

Sau khi thêm:

```text
                 root (pass=2)
                       |
                      1 (2)
                       |
                      0 (2)
                       |
                      1 (2)
                     /   \
                0 (1)     1 (1)
                 10        11
```

Hai khóa dùng chung ba bit `101`; chỉ ở bit cuối chúng tách thành nhánh 0 và 1. Các nút trên tiền tố chung có `pass=2`, hai lá có `pass=1`.

Nếu thêm lại 10, tập không thay đổi. **Không tăng `pass`** khi gặp khóa trùng, nếu không `pass(root)` sẽ lớn hơn số khóa thực sự có mặt.

### Chứng minh bảo toàn bất biến

Trước khi thêm, mỗi nút trên các đường đang có lưu đúng số khóa trong cây con. Khóa mới `x` đi qua đúng một đường gốc–lá. Mọi cây con trên đường ấy có thêm chính xác **một** khóa, nên tăng `pass` đúng một; các nút ở đường khác không đổi. Lá `x` được đánh dấu hoạt động, do đó:

\[
size_{\mathrm{new}}=size_{\mathrm{old}}+1.
\]

Những nhánh đi theo 0/1 từ bit khóa không thay đổi thứ tự hoặc sự hiện diện của khóa cũ.

## 7. Xóa khóa và cắt các nút không còn phần tử

Xóa không chỉ tắt dấu ở lá. Nếu các nút vẫn chứa `pass` cho các truy vấn tiền tố, ta phải cập nhật toàn bộ đường đi và có thể **giải phóng nhánh không còn khóa**.

Để `remove(x)`:

1. Kiểm tra `contains(x)`; nếu vắng, trả `false` và giữ nguyên trie.
2. Lưu lại các nút và lựa chọn cạnh trên đường từ gốc xuống lá của `x`.
3. Tắt dấu `terminal` ở lá.
4. Giảm `pass` đúng một cho mọi nút trên đường, kể cả gốc và lá.
5. Đi ngược từ lá lên, cắt những nút có `pass=0` khỏi cha.
6. Giảm `size`, trả `true`.

### Ví dụ hai khóa có chung ba bit

```text
Trước xóa:

                 root (2)
                   |
                  1 (2)
                   |
                  0 (2)
                   |
                  1 (2)
                 /   \
            0 (1)     1 (1)
             10        11
```

Xóa 10:

```text
Sau xóa:

                 root (1)
                   |
                  1 (1)
                   |
                  0 (1)
                   |
                  1 (1)
                    \
                    1 (1)
                     11
```

Nút lá của 10 bị cắt, nhưng **những nút tiền tố chung còn lại** vì khóa 11 vẫn đi qua chúng.

### Xóa khóa duy nhất

Nếu cây chỉ chứa một khóa, sau khi xóa, các nút `pass=0` trên toàn bộ đường đều được cắt, gốc còn `pass=0` và hai con đều `null`. Trie là tập rỗng hợp lệ.

### Vì sao không được cắt nhánh chỉ vì một khóa bị xóa?

Nếu một nút trên đường có `pass=2` trước xóa, nó vẫn có `pass=1` sau xóa và còn phục vụ khóa khác. Cắt luôn nút đó sẽ làm mất toàn bộ cây con chứa những khóa còn lại. Tiêu chuẩn cắt là **`pass==0` sau khi giảm**, không phải “nút nằm trên đường của khóa đã xóa”.

## 8. Đếm số khóa có cùng tiền tố bit

Các đường đi dùng chung tiền tố cho phép trả lời:

> Có bao nhiêu khóa hiện có bắt đầu bằng `p` bit cao giống một mã `x`?

Giả sử dùng trie 4 bit với:

\[
S=\{0010,0011,1000,1010,1011,1101\}.
\]

| Tiền tố | Khóa phù hợp | Số lượng |
| --- | --- | ---: |
| `0` | `0010,0011` | 2 |
| `00` | `0010,0011` | 2 |
| `10` | `1000,1010,1011` | 3 |
| `101` | `1010,1011` | 2 |
| `11` | `1101` | 1 |
| Tiền tố rỗng | Toàn bộ `S` | 6 |

Để trả lời, chỉ cần đi theo **`k` bit đầu** của tiền tố:

```text
countWithPrefix(x, k):
    require 0 <= k <= w
    node = root
    for k bits from highest to lower:
        follow selected child
        if child is null:
            return 0
    return node.pass
```

Vì `pass` đã là số khóa trong cây con:

\[
\boxed{T_{\text{prefixCount}}=O(k)\le O(w).}
\]

Trường hợp `k=0`, tiền tố rỗng khớp tất cả khóa, nên kết quả là `size`. Trường hợp `k=w`, tiền tố là cả mã khóa: kết quả 1 nếu khóa đó có mặt và 0 nếu không.

### Tiền tố đang đếm mã nào?

Trong chương trình Java 32 bit của bài, ta lưu `code=key XOR MIN_VALUE`. Vì vậy `countWithPrefix(x,k)` đếm tiền tố của **mã đã đảo bit dấu**, không phải tiền tố ASCII hay chữ số thập phân của khóa.

Đặc biệt:

- Tiền tố dài 1 của một số **âm** sau mã hóa có bit đầu **0**.
- Tiền tố dài 1 của một số **không âm** sau mã hóa có bit đầu **1**.

Vì thế có thể dùng `countWithPrefix(-1,1)` để đếm khóa âm và `countWithPrefix(0,1)` để đếm khóa không âm, theo quy ước mã hóa này.

### Không nhầm đếm tiền tố với rank

`countWithPrefix` chỉ đếm khóa trong **một cây con xác định bởi bit**, không trực tiếp trả lời `rank(x)` (“bao nhiêu khóa nhỏ hơn `x`?”).

Nếu muốn rank, có thể duyệt bit theo thứ tự: khi bit của ngưỡng là 1, cộng toàn bộ `pass` của nhánh 0 trước khi đi tiếp sang nhánh 1. Với cách mã hóa bảo toàn thứ tự, đây là một nền tảng để thực hiện `rank` trong O(w). Muốn `select(k)` (khóa thứ `k` theo thứ tự) cũng có thể dùng `pass` để quyết định xuống nhánh trái hay phải.

## 9. Tìm minimum và maximum bằng đường bit

Vì các mã đã được sắp đúng theo thứ tự có dấu sau biến đổi bit:

- **Minimum:** từ gốc, nếu còn nhánh 0 có khóa thì đi 0, nếu không thì đi 1.
- **Maximum:** từ gốc, nếu còn nhánh 1 có khóa thì đi 1, nếu không thì đi 0.

Mỗi bước tái tạo một bit của `code`. Sau 32 bước, giải mã:

```java
int originalKey = code ^ Integer.MIN_VALUE;
```

### Ví dụ có khóa âm

Giả sử tập:

\[
S=\{-5,-1,0,7,100\}.
\]

Trie dùng mã đảo bit dấu. Nhánh gốc 0 chứa `-5,-1`; nhánh gốc 1 chứa `0,7,100`. Do đó:

```text
minimum() -> -5
maximum() -> 100
```

**Nếu không đảo bit dấu** mà vẫn chọn nhánh 0 cho minimum, ta có thể trả 0 thay vì -5 — sai với thứ tự `int` có dấu.

### Tập rỗng

Nếu `root.pass=0`, `minimum()` và `maximum()` phải trả **không có kết quả**, không phải 0 hay `-1`, vì các giá trị này có thể là khóa hợp lệ. Trong ví dụ Java, dùng kiểu `Integer` có thể trả `null`.

### Độ phức tạp

Mỗi phép min/max đi tối đa `w` cạnh:

\[
\boxed{T_{\min}=T_{\max}=O(w).}
\]

Có thể lưu thêm `min`/`max` được cập nhật ở các nút để trả lời nhanh hơn trong một số thiết kế, nhưng việc đó làm tăng bất biến và chi phí bảo trì. Trie cơ bản ở đây chọn giải pháp **đi theo bit** để đơn giản và đúng.

## 10. Tiền nhiệm, kế nhiệm, floor và ceiling

Cho tập `S` có thứ tự. Ta phân biệt:

\[
\begin{aligned}
\operatorname{predecessor}(x)&=\max\{y\in S:y<x\},\\
\operatorname{floor}(x)&=\max\{y\in S:y\le x\},\\
\operatorname{ceiling}(x)&=\min\{y\in S:y\ge x\},\\
\operatorname{successor}(x)&=\min\{y\in S:y>x\}.
\end{aligned}
\]

Không có kết quả nếu tập phù hợp rỗng. Với `S=\{-5,-1,0,7,100\}`:

| Ngưỡng | Predecessor | Floor | Ceiling | Successor |
| ---: | ---: | ---: | ---: | ---: |
| -6 | Không có | Không có | -5 | -5 |
| -1 | -5 | -1 | -1 | 0 |
| 1 | 0 | 0 | 7 | 7 |
| 7 | 0 | 7 | 7 | 100 |
| 101 | 100 | 100 | Không có | Không có |

### Ý tưởng tìm ceiling theo cây bit

Ta xét bit của **ngưỡng đã mã hóa** từ cao xuống thấp, với quy tắc nhánh 0 nhỏ hơn nhánh 1:

1. Nếu bit ngưỡng là 0, thử theo **nhánh 0** để giữ tiền tố bằng ngưỡng. Nếu không có khóa phù hợp trong nhánh 0, có thể chuyển sang nhánh 1 và lấy **khóa nhỏ nhất** trong nhánh đó.
2. Nếu bit ngưỡng là 1, nhánh 0 chứa toàn khóa **nhỏ hơn** ngưỡng tại bit đầu khác biệt, nên chỉ có thể theo nhánh 1.
3. Nếu đi đủ `w` bit và gặp lá của khóa đang có, đó là ceiling chính xác.
4. Nếu không có nhánh hoặc nhánh thử không chứa khóa hợp lệ, trả về lựa chọn dự phòng gần nhất ở tổ tiên (nếu có).

Một dạng đệ quy rất rõ:

```text
ceil(node, bit, builtPrefix, targetCode):
    if node is absent:
        return NOT_FOUND
    if bit < 0:
        return keyAtThisLeaf

    targetBit = bitAt(targetCode, bit)

    if targetBit == 0:
        answer = ceil(node.zero, bit-1, prefixWith0, targetCode)
        if answer exists:
            return answer
        return minimumOfSubtree(node.one, prefixWith1)

    # targetBit == 1
    return ceil(node.one, bit-1, prefixWith1, targetCode)
```

Khi nhánh 0 ở bước hiện tại cho ceiling thất bại, mọi khóa ở nhánh 1 **lớn hơn ngưỡng** (vì bit đầu khác biệt bằng 1), nên chọn min của nhánh 1 là đúng.

### Tìm floor đối xứng

```text
floor(node, bit, builtPrefix, targetCode):
    if node is absent:
        return NOT_FOUND
    if bit < 0:
        return keyAtThisLeaf

    targetBit = bitAt(targetCode, bit)

    if targetBit == 1:
        answer = floor(node.one, bit-1, prefixWith1, targetCode)
        if answer exists:
            return answer
        return maximumOfSubtree(node.zero, prefixWith0)

    # targetBit == 0
    return floor(node.zero, bit-1, prefixWith0, targetCode)
```

Nếu bit ngưỡng là 1, nhánh 0 tại cùng nút chứa các khóa nhỏ hơn ngưỡng. Khi nhánh 1 không cho một floor hợp lệ, lấy max trong nhánh 0.

### Vì sao không phải duyệt toàn bộ trie?

Ở mỗi tầng, thuật toán đệ quy chỉ **thử đi tiếp một nhánh theo bit ngưỡng**. Một nhánh khác, khi được chọn làm dự phòng, chỉ cần **đi một đường duy nhất tới min hoặc max**. Một lần truy vấn có nhiều nhất O(w) tầng tìm và O(w) bước của đường dự phòng, nên:

\[
\boxed{T_{\mathrm{floor}}=T_{\mathrm{ceiling}}=O(w).}
\]

Không phải O(n), dù tập có nhiều khóa. Cách trình bày đệ quy cũng tránh phải lưu một ngăn xếp các ứng viên bên cạnh mỗi bước.

### Từ floor/ceiling tới truy vấn nghiêm ngặt

Với khóa **nguyên rời rạc**:

\[
\operatorname{predecessor}(x)=\operatorname{floor}(x-1),
\qquad
\operatorname{successor}(x)=\operatorname{ceiling}(x+1),
\]

nếu tính `x-1` và `x+1` an toàn.

Với Java `int`, ở cận cực trị:

- Nếu `x=Integer.MIN_VALUE`, **không có** giá trị `int` nào nhỏ hơn `x`, nên predecessor trả rỗng.
- Nếu `x=Integer.MAX_VALUE`, không có giá trị `int` nào lớn hơn `x`, nên successor trả rỗng.

Không được tính `Integer.MIN_VALUE-1` hoặc `Integer.MAX_VALUE+1` trong `int` rồi dùng kết quả tràn số như một khóa thật.

## 11. Khóa cho XOR lớn nhất: một ứng dụng riêng của trie bit

Ngoài truy vấn thứ tự, trie bit có thể trả lời:

> Cho số `q`, tìm khóa `x` đang có để mẫu bit `q XOR x` là **lớn nhất theo thứ tự không dấu**.

Điểm khác với floor/ceiling: ở đây **không muốn khóa `x` lớn nhất**, mà muốn **kết quả XOR lớn nhất**.

### Thuật toán tham lam

Xét từng bit của `q` từ cao xuống thấp:

- Nếu bit ngưỡng là 0, ưu tiên đi nhánh lưu khóa có bit 1.
- Nếu bit ngưỡng là 1, ưu tiên đi nhánh lưu khóa có bit 0.
- Nếu nhánh mong muốn không có phần tử, đi nhánh còn lại.

Vì XOR bằng 1 ở một bit cao có giá trị lớn hơn mọi đóng góp từ các bit thấp hơn, lựa chọn “bit đối lập trước” là tối ưu theo **thứ tự số không dấu**.

### Ví dụ 4 bit

Cho:

```text
S = {0010, 0101, 1110}
q = 0110
```

Ta có:

```text
0110 XOR 0010 = 0100 = 4
0110 XOR 0101 = 0011 = 3
0110 XOR 1110 = 1000 = 8
```

Lựa chọn tốt nhất là `x=1110` vì bit cao nhất của kết quả XOR là 1.

### Có cần bỏ biến đổi dấu khi dùng XOR?

Không. Với mã lưu trong trie:

\[
code(x)=x\oplus M,\qquad code(q)=q\oplus M,
\]

trong đó `M` là mask chỉ có bit dấu 1. Khi XOR:

\[
code(x)\oplus code(q)
=(x\oplus M)\oplus(q\oplus M)
=x\oplus q.
\]

Mask xuất hiện hai lần nên triệt tiêu. Vì vậy có thể dùng cùng trie đã chuẩn hóa thứ tự có dấu để tìm **max-XOR unsigned** bằng cách tham lam trên **mã của ngưỡng và mã của khóa**.

**Lưu ý:** “lớn nhất theo mẫu bit không dấu” khác “lớn nhất theo số `int` có dấu”. Trong Java, nên hiển thị kết quả bằng `Integer.toUnsignedLong(q ^ partner)` khi muốn giải thích giá trị XOR 32 bit không dấu.

## 12. Độ phức tạp và chi phí bộ nhớ

Một trie nhị phân **chưa nén** có đường đi dài `w`; các giả định phân tích là đọc bit, truy cập con trỏ, cấp phát một nút và cập nhật bộ đếm trên một từ có thể tính là O(1).

| Phép toán | Thời gian | Ghi chú |
| --- | --- | --- |
| `contains(x)` | O(w) worst-case | Đọc tối đa `w` bit |
| `add(x)` | O(w) worst-case | Tìm trùng và tạo đường nếu cần |
| `remove(x)` | O(w) worst-case | Lưu đường, giảm `pass` và cắt nhánh |
| `minimum()/maximum()` | O(w) worst-case | Đi theo nhánh 0/1 |
| `floor()/ceiling()` | O(w) worst-case | Duyệt nhánh theo ngưỡng + min/max dự phòng |
| `predecessor()/successor()` | O(w) worst-case | Dựa vào floor/ceiling |
| `countWithPrefix(x,k)` | O(k) | `0\le k\le w` |
| `maxUnsignedXorPartner(q)` | O(w) | Ưu tiên bit đối lập |
| Liệt kê `n` khóa | O(số nút có mặt) | Tối đa O(nw) cho trie chưa nén |
| Bộ nhớ | O(nw) nút trong trường hợp xấu | Một đường mới tạo tối đa `w` nút |

### Vì sao bộ nhớ có thể là O(nw)?

Giả sử mỗi khóa phải tạo gần `w` nút riêng vì ít chia sẻ tiền tố. Với `n` khóa:

\[
\text{số nút}\le1+n\,w
\]

khi chỉ cấp phát các nút thực sự nằm trên đường của ít nhất một khóa và mỗi khóa mới tạo tối đa `w` nút. Đây là một cận trên, không phải số nút chính xác; khi các khóa chia sẻ tiền tố dài, số nút ít hơn nhiều.

Nếu `n=0`, trie chỉ còn gốc rỗng theo mô hình Java của bài. Nếu `n>0`, mọi khóa có một đường đầy đủ từ gốc tới lá.

### Không đồng nhất “32 bước” với “nhanh nhất”

Với `int` Java, `w=32` là một hằng số, nên có thể gọi số bước O(1) theo `n` trong một hệ thống có độ rộng cố định. Tuy nhiên:

- 32 lần đọc nhánh có thể gây **pointer chasing** và cache miss.
- Mỗi nút có con trỏ và metadata, dùng nhiều bộ nhớ hơn 1 bit/khóa của bitset.
- Một bảng băm tốt thường cần ít lần truy cập bộ nhớ hơn cho membership.
- Một cây cân bằng có thể giữ số nút O(n), dù chiều cao theo `\log n`.

Vì vậy, trong phân tích học thuật, biểu thức **O(w)** nêu rõ nguồn chi phí; trong tối ưu thực tế, cần benchmark trên workload và môi trường cụ thể.

### Trie nén đường: Patricia/radix trie

Một **Patricia trie** hoặc *compressed binary trie* có thể **gộp các chuỗi nút chỉ có một con** thành một cạnh mang thông tin số bit cần bỏ qua/so sánh. Thay vì lưu mỗi bit bằng một đối tượng nút:

```text
Trie chưa nén:

root --0--0--0--1--0--1--> leaf

Trie nén:

root --[000101]----------> leaf
```

Với các khóa có cùng độ dài và được tổ chức bằng các **nút phân nhánh thực sự**, một trie nén thích hợp có thể giảm số nút về O(n). Tuy nhiên, cần lưu **vị trí bit phân nhánh hoặc nhãn cạnh**, và khi tìm kiếm phải xác minh phần tiền tố đã nén. Không được lấy trực tiếp code `Node.zero/one` của trie chưa nén rồi tuyên bố nó đã là Patricia trie.

### So sánh với các cấu trúc khác

| Cấu trúc | Membership | Truy vấn thứ tự | Bộ nhớ theo mô hình cơ bản |
| --- | --- | --- | --- |
| Bitset dày đặc | O(1) đọc bit | Tìm kế tiếp có thể quét O(U/w) từ nếu không có summary | O(U) bit |
| Sparse set hai mảng | O(1) | Không sắp; có thể phải quét `n` khóa | O(U+n) ô |
| Bảng băm | O(1) trung bình/kỳ vọng | Không duy trì thứ tự | O(n) theo tải |
| AVL/Red-Black tree | O(log n) worst-case | O(log n) cho floor/ceiling | O(n) nút |
| Binary trie chưa nén | O(w) worst-case | O(w) qua bit | O(nw) nút |
| Patricia trie | Phụ thuộc biến thể; thường theo số bit/độ sâu nén | Cần logic định tuyến và xác minh bit nén | Có thể O(n) nút |

**Khi miền `U` cực lớn và `n` rất nhỏ**, trie vẫn có thể phù hợp hơn bitset dày đặc vì nó chỉ cấp phát các đường dùng tới. Nhưng nếu `w` rất lớn và các đường ít chia sẻ, chi phí nút có thể vượt bảng băm hoặc cây cân bằng.

## 13. Java hoàn chỉnh: `IntBinaryTrie` 32 bit có dấu

Ví dụ sau dùng **một lớp Java tự chứa**, chạy được trên Java 8 trở lên. Các thiết kế quan trọng:

- Biến đổi mã bằng `key ^ Integer.MIN_VALUE` để duy trì **thứ tự có dấu** khi đi nhánh 0 trước nhánh 1.
- Mỗi nút có `zero`, `one`, `pass` và `terminal`.
- Chỉ nút ở **độ sâu 32** được đánh dấu khóa hoàn chỉnh.
- `add` ngăn khóa trùng; `remove` giảm bộ đếm, cắt nhánh rỗng.
- `minimum`/`maximum` xây lại khóa bằng đường bit.
- `floor`/`ceiling` dùng một nhánh theo ngưỡng và dự phòng bằng max/min của nhánh phù hợp.
- `lower`/`higher` là tên tương đương **predecessor/successor strict**.
- `countWithPrefix` trả số khóa dưới một tiền tố của **mã đã chuẩn hóa**.
- `maxUnsignedXorPartner` tìm khóa làm cực đại mẫu `query XOR key` theo thứ tự không dấu.
- `verify` kiểm tra độc lập bộ đếm, nút hoạt động, độ sâu lá, không chu trình/alias.

Mã dùng `int` cho `size` và `pass`, vì vậy không thiết kế để chứa hơn `Integer.MAX_VALUE` mục; đó là giới hạn của **bản minh họa trong RAM**, không phải khẳng định tổng miền 32 bit chỉ có từng ấy khóa.

```java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.TreeSet;

public class SignedIntegerBinaryTrieDemo {
    private static final int WIDTH = 32;
    private static final int SIGN_MASK = Integer.MIN_VALUE;

    static final class Node {
        Node zero;
        Node one;
        int pass;               // Number of active keys below node.
        boolean terminal;       // Only true at full 32-bit leaves.
    }

    static final class IntBinaryTrie {
        private final Node root = new Node();
        private int size;

        private static int encode(int key) {
            return key ^ SIGN_MASK;
        }

        private static int decode(int encoded) {
            return encoded ^ SIGN_MASK;
        }

        private static int bitAt(int code, int shift) {
            return (code >>> shift) & 1;
        }

        int size() {
            return size;
        }

        boolean contains(int key) {
            int code = encode(key);
            Node current = root;
            for (int shift = WIDTH - 1; shift >= 0; shift--) {
                current = bitAt(code, shift) == 0
                        ? current.zero : current.one;
                if (current == null) {
                    return false;
                }
            }
            return current.terminal;
        }

        boolean add(int key) {
            if (contains(key)) {
                return false;
            }
            if (size == Integer.MAX_VALUE) {
                throw new IllegalStateException("Size limit reached");
            }

            int code = encode(key);
            Node current = root;
            current.pass++;
            for (int shift = WIDTH - 1; shift >= 0; shift--) {
                int bit = bitAt(code, shift);
                if (bit == 0) {
                    if (current.zero == null) {
                        current.zero = new Node();
                    }
                    current = current.zero;
                } else {
                    if (current.one == null) {
                        current.one = new Node();
                    }
                    current = current.one;
                }
                current.pass++;
            }
            current.terminal = true;
            size++;
            return true;
        }

        boolean remove(int key) {
            if (!contains(key)) {
                return false;
            }

            int code = encode(key);
            Node[] path = new Node[WIDTH + 1];
            int[] edges = new int[WIDTH];
            path[0] = root;

            for (int depth = 0; depth < WIDTH; depth++) {
                int shift = WIDTH - 1 - depth;
                int bit = bitAt(code, shift);
                edges[depth] = bit;
                Node parent = path[depth];
                path[depth + 1] =
                    bit == 0 ? parent.zero : parent.one;
            }

            path[WIDTH].terminal = false;
            for (Node node : path) {
                node.pass--;
            }

            // Detach dead descendants from deepest to shallowest.
            for (int depth = WIDTH; depth >= 1; depth--) {
                if (path[depth].pass != 0) {
                    break;
                }
                Node parent = path[depth - 1];
                if (edges[depth - 1] == 0) {
                    parent.zero = null;
                } else {
                    parent.one = null;
                }
            }

            size--;
            return true;
        }

        // Complete the remaining bits by always taking the lowest branch.
        private static Integer minimumBelow(
                Node current, int nextShift, int prefix) {
            if (current == null || current.pass == 0) {
                return null;
            }
            int code = prefix;
            for (int shift = nextShift; shift >= 0; shift--) {
                if (current.zero != null && current.zero.pass > 0) {
                    current = current.zero;
                } else {
                    if (current.one == null || current.one.pass == 0) {
                        throw new IllegalStateException("Broken trie");
                    }
                    code |= (1 << shift);
                    current = current.one;
                }
            }
            return decode(code);
        }

        // Complete the remaining bits by always taking the highest branch.
        private static Integer maximumBelow(
                Node current, int nextShift, int prefix) {
            if (current == null || current.pass == 0) {
                return null;
            }
            int code = prefix;
            for (int shift = nextShift; shift >= 0; shift--) {
                if (current.one != null && current.one.pass > 0) {
                    code |= (1 << shift);
                    current = current.one;
                } else {
                    if (current.zero == null || current.zero.pass == 0) {
                        throw new IllegalStateException("Broken trie");
                    }
                    current = current.zero;
                }
            }
            return decode(code);
        }

        Integer minimum() {
            return minimumBelow(root, WIDTH - 1, 0);
        }

        Integer maximum() {
            return maximumBelow(root, WIDTH - 1, 0);
        }

        private static Integer ceilingAt(
                Node current, int shift, int prefix, int target) {
            if (current == null || current.pass == 0) {
                return null;
            }
            if (shift < 0) {
                return current.terminal ? decode(prefix) : null;
            }

            if (bitAt(target, shift) == 0) {
                Integer inZero =
                    ceilingAt(current.zero, shift - 1, prefix, target);
                if (inZero != null) {
                    return inZero;
                }
                // The first differing bit becomes 1: take minimum.
                return minimumBelow(
                    current.one, shift - 1, prefix | (1 << shift));
            }
            // A zero branch would be smaller than the threshold.
            return ceilingAt(
                current.one, shift - 1,
                prefix | (1 << shift), target);
        }

        private static Integer floorAt(
                Node current, int shift, int prefix, int target) {
            if (current == null || current.pass == 0) {
                return null;
            }
            if (shift < 0) {
                return current.terminal ? decode(prefix) : null;
            }

            if (bitAt(target, shift) == 1) {
                Integer inOne = floorAt(
                    current.one, shift - 1,
                    prefix | (1 << shift), target);
                if (inOne != null) {
                    return inOne;
                }
                // The first differing bit becomes 0: take maximum.
                return maximumBelow(current.zero, shift - 1, prefix);
            }
            // A one branch would be larger than the threshold.
            return floorAt(current.zero, shift - 1, prefix, target);
        }

        // Smallest active key >= key in signed integer order.
        Integer ceiling(int key) {
            return ceilingAt(root, WIDTH - 1, 0, encode(key));
        }

        // Largest active key <= key in signed integer order.
        Integer floor(int key) {
            return floorAt(root, WIDTH - 1, 0, encode(key));
        }

        // Strict predecessor (TreeSet.lower).
        Integer lower(int key) {
            if (key == Integer.MIN_VALUE) {
                return null;
            }
            return floor(key - 1);
        }

        // Strict successor (TreeSet.higher).
        Integer higher(int key) {
            if (key == Integer.MAX_VALUE) {
                return null;
            }
            return ceiling(key + 1);
        }

        int countWithPrefix(int key, int prefixLength) {
            if (prefixLength < 0 || prefixLength > WIDTH) {
                throw new IllegalArgumentException(
                    "Prefix length must be 0..32");
            }
            int code = encode(key);
            Node current = root;
            for (int shift = WIDTH - 1;
                    shift >= WIDTH - prefixLength; shift--) {
                current = bitAt(code, shift) == 0
                    ? current.zero : current.one;
                if (current == null) {
                    return 0;
                }
            }
            return current.pass;
        }

        // Maximizes unsigned (query XOR storedKey).
        Integer maxUnsignedXorPartner(int query) {
            if (size == 0) {
                return null;
            }
            int queryCode = encode(query);
            int selectedCode = 0;
            Node current = root;

            for (int shift = WIDTH - 1; shift >= 0; shift--) {
                int preferred = bitAt(queryCode, shift) ^ 1;
                Node preferredChild =
                    preferred == 0 ? current.zero : current.one;

                int chosen = preferred;
                if (preferredChild == null || preferredChild.pass == 0) {
                    chosen = preferred ^ 1;
                }
                if (chosen == 1) {
                    selectedCode |= (1 << shift);
                    current = current.one;
                } else {
                    current = current.zero;
                }
                if (current == null || current.pass == 0) {
                    throw new IllegalStateException("Broken trie");
                }
            }
            return decode(selectedCode);
        }

        // Values in signed ascending order; traversal visits active nodes.
        private static void traverse(
                Node current, int shift, int prefix, List<Integer> out) {
            if (current == null || current.pass == 0) {
                return;
            }
            if (shift < 0) {
                if (!current.terminal) {
                    throw new IllegalStateException("Missing terminal");
                }
                out.add(decode(prefix));
                return;
            }
            traverse(current.zero, shift - 1, prefix, out);
            traverse(
                current.one, shift - 1,
                prefix | (1 << shift), out);
        }

        List<Integer> keysInOrder() {
            List<Integer> out = new ArrayList<>(size);
            traverse(root, WIDTH - 1, 0, out);
            return out;
        }

        // Independent validator: do not use add/remove/contains.
        private static int verifyNode(
                Node current, int depth,
                IdentityHashMap<Node, Boolean> seen) {
            if (current == null) {
                return 0;
            }
            if (seen.put(current, Boolean.TRUE) != null) {
                throw new IllegalStateException(
                    "Cycle or shared child detected");
            }
            if (current.pass < 0 || (depth > 0 && current.pass == 0)) {
                throw new IllegalStateException("Invalid pass counter");
            }
            if (depth == WIDTH) {
                if (!current.terminal || current.zero != null
                        || current.one != null || current.pass != 1) {
                    throw new IllegalStateException(
                        "Invalid full-length leaf");
                }
                return 1;
            }
            if (current.terminal) {
                throw new IllegalStateException(
                    "Internal node marked terminal");
            }
            int childTotal =
                verifyNode(current.zero, depth + 1, seen)
                + verifyNode(current.one, depth + 1, seen);
            if (current.pass != childTotal) {
                throw new IllegalStateException(
                    "Subtree size mismatch at depth " + depth);
            }
            return childTotal;
        }

        void verify() {
            if (root.pass != size || size < 0) {
                throw new IllegalStateException("Wrong root size");
            }
            int actual = verifyNode(
                root, 0, new IdentityHashMap<Node, Boolean>());
            if (actual != size) {
                throw new IllegalStateException("Wrong key count");
            }
            if (size == 0 && (root.zero != null || root.one != null)) {
                throw new IllegalStateException(
                    "Empty root still has children");
            }
        }
    }

    private static void require(boolean valid, String explanation) {
        if (!valid) {
            throw new IllegalStateException(explanation);
        }
    }

    // Differential test: TreeSet is independent of trie bit logic.
    private static void compareAgainst(
            IntBinaryTrie trie, TreeSet<Integer> oracle) {
        trie.verify();
        require(trie.size() == oracle.size(), "Size mismatch");
        require(trie.keysInOrder().equals(new ArrayList<>(oracle)),
                "Ordered keys mismatch");

        Integer expectedMin = oracle.isEmpty() ? null : oracle.first();
        Integer expectedMax = oracle.isEmpty() ? null : oracle.last();
        require(Objects.equals(trie.minimum(), expectedMin),
                "Minimum mismatch");
        require(Objects.equals(trie.maximum(), expectedMax),
                "Maximum mismatch");

        int[] probes = {
            Integer.MIN_VALUE, -101, -20, -1, 0,
            1, 7, 64, 100, Integer.MAX_VALUE
        };
        for (int q : probes) {
            require(trie.contains(q) == oracle.contains(q),
                    "Contains mismatch at " + q);
            require(Objects.equals(trie.lower(q), oracle.lower(q)),
                    "Predecessor mismatch at " + q);
            require(Objects.equals(trie.floor(q), oracle.floor(q)),
                    "Floor mismatch at " + q);
            require(Objects.equals(trie.ceiling(q), oracle.ceiling(q)),
                    "Ceiling mismatch at " + q);
            require(Objects.equals(trie.higher(q), oracle.higher(q)),
                    "Successor mismatch at " + q);
        }

        int negativeCount = oracle.headSet(0, false).size();
        int nonnegativeCount = oracle.tailSet(0, true).size();
        require(trie.countWithPrefix(-1, 1) == negativeCount,
                "Negative prefix mismatch");
        require(trie.countWithPrefix(0, 1) == nonnegativeCount,
                "Nonnegative prefix mismatch");

        Integer partner = trie.maxUnsignedXorPartner(0);
        if (oracle.isEmpty()) {
            require(partner == null, "Unexpected XOR partner");
        } else {
            long bestScore = -1L;
            for (int x : oracle) {
                long score = Integer.toUnsignedLong(x);
                if (score > bestScore) {
                    bestScore = score;
                }
            }
            require(partner != null
                    && Integer.toUnsignedLong(partner) == bestScore,
                    "Max-XOR mismatch");
        }
    }

    public static void main(String[] args) {
        IntBinaryTrie trie = new IntBinaryTrie();
        TreeSet<Integer> reference = new TreeSet<>();

        int[] original = {
            Integer.MIN_VALUE, -20, -5, -1, 0,
            1, 7, 64, 70, Integer.MAX_VALUE
        };
        for (int key : original) {
            require(trie.add(key) == reference.add(key),
                    "Initial insert mismatch");
        }
        compareAgainst(trie, reference);

        System.out.println("size=" + trie.size());
        System.out.println("minimum=" + trie.minimum());
        System.out.println("maximum=" + trie.maximum());
        System.out.println("lower(0)=" + trie.lower(0));
        System.out.println("floor(0)=" + trie.floor(0));
        System.out.println("ceiling(2)=" + trie.ceiling(2));
        System.out.println("higher(7)=" + trie.higher(7));
        System.out.println("negative keys="
            + trie.countWithPrefix(-1, 1));
        System.out.println("nonnegative keys="
            + trie.countWithPrefix(0, 1));

        Integer partner = trie.maxUnsignedXorPartner(0);
        System.out.println("max XOR partner for 0=" + partner
            + ", unsigned XOR="
            + Integer.toUnsignedLong(partner));

        System.out.println("remove(-20)=" + trie.remove(-20));
        reference.remove(-20);
        System.out.println("remove(-20) again=" + trie.remove(-20));
        System.out.println("remove(MIN_VALUE)="
            + trie.remove(Integer.MIN_VALUE));
        reference.remove(Integer.MIN_VALUE);
        System.out.println("minimum after removals="
            + trie.minimum());
        System.out.println("reinsert(MIN_VALUE)="
            + trie.add(Integer.MIN_VALUE));
        reference.add(Integer.MIN_VALUE);
        compareAgainst(trie, reference);

        // Reproducible mixed updates, including duplicate/missing keys.
        Random random = new Random(20261128L);
        for (int step = 0; step < 400; step++) {
            int key = step % 19 == 0
                ? Integer.MIN_VALUE
                : (step % 23 == 0
                    ? Integer.MAX_VALUE
                    : random.nextInt(201) - 100);
            boolean adding = random.nextBoolean();
            boolean expected = adding
                ? reference.add(key) : reference.remove(key);
            boolean actual = adding
                ? trie.add(key) : trie.remove(key);
            require(expected == actual,
                    "Update result mismatch at step " + step);
            compareAgainst(trie, reference);
        }

        System.out.println("Randomized checks passed: 400");
        System.out.println("All invariants: OK");
    }
}
```

Đầu ra của phần minh họa cố định trước chuỗi ngẫu nhiên:

```text
size=10
minimum=-2147483648
maximum=2147483647
lower(0)=-1
floor(0)=0
ceiling(2)=7
higher(7)=64
negative keys=4
nonnegative keys=6
max XOR partner for 0=-1, unsigned XOR=4294967295
remove(-20)=true
remove(-20) again=false
remove(MIN_VALUE)=true
minimum after removals=-5
reinsert(MIN_VALUE)=true
Randomized checks passed: 400
All invariants: OK
```

### Vì sao mã tìm floor/ceiling là O(w)?

Hàm `ceilingAt` hoặc `floorAt` chỉ đệ quy theo nhánh **có cùng bit với ngưỡng**. Nếu cần, hàm lấy `minimumBelow` hoặc `maximumBelow` trên nhánh đối diện, mỗi hàm chỉ đi xuống **một đường** còn lại. Không có bước duyệt qua toàn bộ các khóa.

Đường đệ quy dài tối đa 32 tầng. Nếu dùng bit đầu phân nhánh để chọn nhánh dự phòng, kết quả thu được là khóa gần ngưỡng nhất theo thứ tự **mã không dấu**, tức thứ tự **khóa Java có dấu** sau khi đã đảo bit dấu.

### Vì sao `remove` lưu mảng `path`?

Khi đã tới lá, cần giảm `pass` của **mọi nút tổ tiên** và cắt những nút hết khóa. Lưu 33 nút (gốc và 32 mức tiếp theo) cùng 32 lựa chọn cạnh giúp đi ngược đường một cách chắc chắn. Không cần mỗi nút mang con trỏ `parent` thường trực.

**Chi phí bổ sung:** O(w) bộ nhớ tạm cho một lần xóa. Với `w=32`, đây là hai mảng nhỏ.

### Vì sao có `IdentityHashMap` trong bộ kiểm tra?

Nếu cùng một đối tượng `Node` vô tình được gán làm con ở hai đường hoặc một con trỏ trỏ ngược về tổ tiên, cấu trúc không còn là cây hợp lệ. `IdentityHashMap` kiểm tra **danh tính đối tượng**, không phụ thuộc việc có ai định nghĩa `equals` so sánh nội dung nút hay không.

Bộ kiểm tra còn xác nhận `pass(node)` bằng tổng các `pass` con và lá hoàn chỉnh có `pass=1`, do đó phát hiện lỗi quên tăng/giảm bộ đếm sau cập nhật.

### Vì sao oracle là `TreeSet`?

`TreeSet<Integer>` trong Java duy trì thứ tự số nguyên **có dấu**. Các hàm `lower/floor/ceiling/higher` có hợp đồng trùng với bốn truy vấn của bài. Khi so sánh kết quả với một cấu trúc độc lập, ta dễ phát hiện:

- Quên đảo bit dấu.
- Sai thứ tự nhánh 0/1.
- Sai tìm floor/ceiling ở cận bit 31.
- Lỗi `remove` làm mất khóa khác.
- Đếm tiền tố âm/không âm không khớp sau cập nhật.

Bài kiểm thử ngẫu nhiên có **seed cố định**, dùng cả hai khóa cực trị và khóa trong miền hẹp để thường gặp **thêm trùng, xóa vắng, nhánh được tái sử dụng**. Việc kiểm tra sau từng bước giúp tìm **lần cập nhật đầu tiên gây sai**.

### Giới hạn của ví dụ

Mã không triển khai khóa trùng, payload theo khóa, trie nén, lưu trên đĩa hay truy cập đồng thời. Số nút có thể lớn so với số khóa vì mỗi khóa cần đường 32 bit. Các kết quả test hữu hạn **không thay thế chứng minh hình thức hoặc vòng kiểm tra nội dung độc lập**.

## 14. Ứng dụng và những biến thể đáng biết

### 14.1. Kiểm tra tiền tố bit của địa chỉ, mã phân vùng

Trie theo bit phù hợp để lưu và tìm các tiền tố có ý nghĩa, chẳng hạn tiền tố địa chỉ mạng hoặc mã phân vùng. Tuy nhiên, **longest prefix match** trong bảng định tuyến IP thường đánh dấu **nút tiền tố có độ dài biến thiên** là quy tắc hợp lệ, chứ không chỉ đánh dấu lá đủ 32 bit như trie khóa nguyên trong bài.

Ví dụ, một quy tắc mang tiền tố 8 bit phải có thể kết thúc ở độ sâu 8. Cần bổ sung `terminal`/payload ở nút trong, ưu tiên **quy tắc có tiền tố dài nhất** khi đi xuống; không bê nguyên ràng buộc “chỉ lá độ sâu 32 mới là khóa” áp vào router.

### 14.2. Tìm cặp XOR lớn nhất trong một tập

Nếu muốn tìm hai khóa `x,y` có XOR lớn nhất, có thể lần lượt đưa các khóa vào trie rồi với mỗi khóa hỏi **đối tác max-XOR**. Với `n` khóa `w` bit, phương pháp cơ bản có thời gian:

\[
O(nw),
\]

bỏ qua chi phí cấp phát/GC và với định nghĩa XOR tối đa theo **thứ tự không dấu**. Cần quyết định một khóa có được **ghép với chính nó** hay chỉ được ghép với khóa khác; có thể chèn trước/truy vấn sau hoặc duy trì số lượng để tránh trường hợp tự ghép.

### 14.3. Kết hợp bộ đếm cho rank/select

Với `pass` ở mỗi nút:

- **`rank(x)`:** khi đi theo bit của `x`, cứ gặp bit 1 thì cộng số khóa ở nhánh 0 của cùng nút (những khóa có bit khác biệt 0 nhỏ hơn `x`). Tiếp tục đi nhánh 1 nếu có.
- **`select(k)`:** tại mỗi nút, so `k` với `pass` của con 0; nếu `k` nhỏ hơn, đi nhánh 0, nếu không, trừ đi kích thước con 0 và đi nhánh 1.

Hai thuật toán có thể đạt O(w) trong trie không nén có bộ đếm đúng, nhưng cần chốt `rank` dùng dấu `<` hay `\le` và `k` đánh số từ 0 hay 1.

### 14.4. Persistent binary trie

Trong các bài toán truy vấn phiên bản (ví dụ “XOR lớn nhất với các khóa ở một khoảng thời gian”), có thể dùng **persistent trie**: khi chèn một khóa ở phiên bản mới, tạo bản sao các nút **trên đường cập nhật** và chia sẻ các cây con không đổi.

Điều này khác trie mutable của ví dụ:

- Cần cơ chế quản lý phiên bản gốc.
- Phải cẩn thận với bộ đếm của các phiên bản.
- Thời gian và bộ nhớ bổ sung có thể O(w) mỗi lần chèn.
- Không được sửa nút đã được phiên bản cũ dùng chung.

### 14.5. Trie nén và bảng băm khác nhau về tối ưu

Tập thưa với mã 64 bit rải rác có thể khiến trie chưa nén tạo rất nhiều nút một-con. Patricia trie nén các đoạn đó; bảng băm không duy trì đường tiền tố nhưng thường gọn hơn khi chỉ cần `contains`. Muốn chọn đúng, phải dựa vào **những phép toán thực sự cần**: tiền tố, thứ tự, XOR hay chỉ tìm chính xác.

## 15. Kiểm thử các ca biên cần thiết

| Nhóm thử | Kịch bản | Bất biến/nguy cơ |
| --- | --- | --- |
| Rỗng | Tất cả truy vấn trước khi thêm | Không có phần tử, `root.pass=0` |
| Một khóa | Thêm rồi tìm, min/max, floor/ceiling, xóa | Đường 32 bit đầy đủ |
| Khóa trùng | `add(x)` hai lần | Không tăng `size` hay `pass` lần thứ hai |
| Xóa vắng | `remove(x)` khi chưa có | Không đổi bất kỳ cây con nào |
| Tiền tố chung | Thêm `10` và `11` (4 bit minh họa) | Hai nhánh chia sẻ đúng tiền tố |
| Xóa một trong hai khóa chung tiền tố | Xóa 10, giữ 11 | Không cắt nhánh vẫn có khóa |
| Xóa đến rỗng | Xóa khóa cuối | Gốc không giữ các con `pass=0` |
| Bit cao | Khóa âm và không âm | Thứ tự signed đúng |
| Cận nguyên | `Integer.MIN_VALUE/MAX_VALUE` | Không tràn và không bỏ bit 31 |
| Kiểm thử thứ tự | So `lower/floor/ceiling/higher` với `TreeSet` | Tìm lân cận chính xác |
| Tiền tố | `k=0`, `k=1`, `k=32` | Đếm toàn tập / nhánh dấu / một khóa |
| XOR | Kết quả có bit 31 bật | So sánh unsigned |
| Tính độc nhất nút | Mỗi nút chỉ có một cha | Phát hiện cycle/alias |
| Ngẫu nhiên có seed | Trộn thêm/xóa nhiều lần | Kiểm tra sau mỗi cập nhật |

### Kiểm chứng phép đếm tiền tố

Ngoài trường hợp bit dấu, có thể tạo một tập `TreeSet` chuẩn và đếm trực tiếp:

```text
expected = 0
for each stored key y:
    if highest k bits of encode(y) == highest k bits of encode(x):
        expected++

assert trie.countWithPrefix(x,k) == expected
```

Với `k=0`, tất cả khóa luôn phù hợp; với `k=32`, chỉ có khóa đúng mã `x` phù hợp. Khi so sánh tiền tố, **không dịch trái/phải quá độ rộng `w`** và không tự coi số âm là tiền tố của chuỗi ký tự có dấu trừ.

### Lỗi thời gian thực

Nếu trie có nhiều luồng cùng thêm/xóa và truy vấn, một luồng có thể quan sát **nút mới chưa cập nhật `pass`** hoặc một nút đã bị cắt trong lúc đang duyệt. Bộ cài đặt Java trong bài **không thread-safe**. Để dùng trong môi trường đồng thời, cần khóa, bản sao bất biến, snapshot hoặc cơ chế đồng bộ thích hợp.

## 16. Những lỗi triển khai thường gặp

1. **Dùng biểu diễn có độ dài biến thiên mà không đánh dấu kết thúc khóa.** Một khóa có thể trở thành tiền tố của khóa khác, gây nhầm membership.
2. **Đọc bit từ thấp lên cao nhưng vẫn dùng quy tắc min/max theo nhánh từ cao xuống.** Lập luận về thứ tự không còn đúng.
3. **Quên dấu bit cao trong Java `int`.** Nhánh 0 của bit gốc không đồng nghĩa số âm nhỏ hơn số dương.
4. **Đảo bit dấu khi chèn nhưng không đảo khi tìm/xóa.** Cùng một khóa bị ánh xạ ra hai đường khác nhau.
5. **Khôi phục `code` thành khóa bằng phép cộng thay vì XOR ngược.** Cần dùng đúng phép song ánh `code ^ MIN_VALUE`.
6. **Kiểm tra bit bằng `(key & (1<<31)) > 0`.** Mask bit 31 là số âm; nên dùng `!=0` hoặc `>>>`.
7. **Nhầm `>>` và `>>>` trong xử lý bit.** Dịch phải có dấu sao chép bit dấu; với logic bit, nên rõ ràng dùng `>>>` và `&1`.
8. **Cho rằng đi được một phần tiền tố nghĩa là khóa đã tồn tại.** Phải đọc đủ 32 bit và kiểm tra lá.
9. **Tăng `pass` khi thêm khóa trùng.** Tổng đếm cây con sẽ sai.
10. **Giảm `pass` khi xóa khóa vắng.** Có thể tạo số âm và mất liên kết.
11. **Cắt mọi nút trên đường xóa mà không kiểm tra `pass==0`.** Có thể xóa mất khóa khác dùng chung tiền tố.
12. **Quên cập nhật `size` đồng bộ với `root.pass`.** Các truy vấn tiền tố và empty check có thể sai.
13. **Lấy min trong nhánh rỗng rồi dùng kết quả `trailingZeros(0)`.** Cần kiểm tra còn khóa.
14. **Viết floor/ceiling mà không có phương án quay sang nhánh đối diện.** Dễ bỏ sót khóa hợp lệ gần nhất.
15. **Nhầm strict predecessor với floor.** Nếu ngưỡng đang có, hai kết quả không nhất thiết bằng nhau.
16. **Dùng `x+1` hoặc `x-1` trên `int` tại MIN/MAX.** Tràn và trả kết quả sai.
17. **Hiểu kết quả XOR là số `int` có dấu khi bài yêu cầu unsigned.** Bit 31 bật cho kết quả âm theo cách in mặc định nhưng lại có giá trị unsigned lớn.
18. **Cho rằng max-XOR chọn khóa lớn nhất trong tập.** Tối ưu XOR phụ thuộc từng bit ngưỡng, không chỉ thứ tự khóa.
19. **Gọi bộ nhớ trie chưa nén O(n) mà bỏ qua `w`.** Mỗi khóa mới có thể tạo O(w) nút.
20. **Gọi mọi thao tác O(1) không điều kiện vì hiện tại Java có 32 bit.** Cần nêu mô hình khóa cố định và chi phí thực tế.
21. **Quên kiểm tra alias/cycle và độ sâu lá trong validator.** Con trỏ sai có thể khiến đường bit không còn biểu diễn cây đúng.
22. **Dùng trie có thứ tự unsigned để đối chiếu trực tiếp với `TreeSet<Integer>` signed.** Hai quy ước thứ tự khác nhau.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Binary trie chọn nhánh con dựa trên điều gì, khác gì BST?

**Đáp án:** Dựa trên **bit 0/1 của khóa ở tầng đang xét**; BST chọn dựa trên so sánh khóa với khóa tại nút.

**Câu 2.** Với khóa `13` biểu diễn trên 4 bit, đường đi MSB-first là gì?

**Đáp án:** `1101`, lần lượt chọn nhánh 1, 1, 0, 1.

**Câu 3.** Tại sao cần thống nhất độ dài bit khi triển khai trie số nguyên?

**Đáp án:** Để xác định mỗi tầng kiểm tra bit nào và điểm kết thúc khóa; nếu độ dài biến thiên, cần cơ chế terminal phù hợp.

**Câu 4.** Tìm kiếm một khóa `w` bit trong trie chưa nén cần bao nhiêu bước trong trường hợp xấu?

**Đáp án:** O(w), tức tối đa `w` lần chọn cạnh.

**Câu 5.** Với `int` Java, tại sao dùng bit gốc và ưu tiên nhánh 0 không đủ để tìm minimum có dấu?

**Đáp án:** Bit dấu 0 thuộc số không âm, bit dấu 1 thuộc số âm; thứ tự unsigned theo bit gốc xếp số không âm trước số âm.

**Câu 6.** Phép chuẩn hóa nào biến thứ tự `int` có dấu thành thứ tự mã bit unsigned?

**Đáp án:** `code=key ^ Integer.MIN_VALUE`. Giải mã bằng cùng phép XOR một lần nữa.

**Câu 7.** Với khóa `int`, câu lệnh nào lấy bit ở vị trí `shift` an toàn?

**Đáp án:** `(code >>> shift) & 1` với `shift` từ 31 xuống 0.

**Câu 8.** Nút trie có `pass=5` có ý nghĩa gì?

**Đáp án:** Có **5 khóa phân biệt hiện diện** trong cây con của nút theo mô hình set không trùng.

**Câu 9.** Khi thêm một khóa mới, các `pass` trên đường gốc–lá thay đổi thế nào?

**Đáp án:** Tăng đúng một ở từng nút trên đường, kể cả gốc và lá mới/hiện có.

**Câu 10.** Tại sao thêm lại một khóa đã tồn tại không được tăng `pass`?

**Đáp án:** Vì tập khóa phân biệt không đổi; tăng sẽ phá bất biến đếm số khóa trong cây con.

**Câu 11.** Sau khi xóa một khóa, khi nào được cắt một nhánh?

**Đáp án:** Khi `pass` của nút con đã giảm về 0, nghĩa là không còn khóa nào đi qua nó.

**Câu 12.** Với `S=\{1010,1011\}` trên 4 bit, `countWithPrefix(1010,3)` là bao nhiêu?

**Đáp án:** 2, vì cả hai khóa có ba bit đầu `101`.

**Câu 13.** `countWithPrefix(x,0)` và `countWithPrefix(x,w)` có ý nghĩa gì?

**Đáp án:** Độ dài 0 đếm toàn tập; độ dài `w` đếm 1 nếu khóa `x` có mặt, ngược lại 0.

**Câu 14.** Tại sao tìm minimum trong trie MSB-first cần ưu tiên nhánh 0 theo **mã đã chuẩn hóa**?

**Đáp án:** Ở bit đầu tiên khác nhau, mã có bit 0 nhỏ hơn mã có bit 1 theo unsigned, tương ứng thứ tự có dấu sau biến đổi.

**Câu 15.** Với `S=\{-5,-1,0,7,100\}`, `floor(1)` và `ceiling(1)` là gì?

**Đáp án:** `floor(1)=0` và `ceiling(1)=7`.

**Câu 16.** `predecessor(-1)` và `successor(-1)` của tập đó là gì?

**Đáp án:** `predecessor(-1)=-5`, `successor(-1)=0`.

**Câu 17.** Vì sao phép `predecessor(Integer.MIN_VALUE)` phải trả rỗng?

**Đáp án:** Không có khóa `int` nào nhỏ hơn giá trị nhỏ nhất của miền 32 bit có dấu; trừ 1 trong `int` sẽ tràn.

**Câu 18.** Với `q=0110` và các khóa 4 bit `0010`, `0101`, `1110`, đối tác max-XOR unsigned là khóa nào?

**Đáp án:** `1110` vì `0110 XOR 1110 = 1000` có giá trị unsigned 8, lớn hơn các kết quả còn lại.

**Câu 19.** Vì sao cùng mã đảo bit dấu có thể dùng cho max-XOR unsigned?

**Đáp án:** `(q XOR M) XOR (x XOR M)=q XOR x`; mask dấu xuất hiện hai lần và triệt tiêu.

**Câu 20.** Cận trên số nút của trie chưa nén chứa `n` khóa `w` bit là bao nhiêu?

**Đáp án:** Không quá `1+n\,w` nút nếu chỉ tạo các nút nằm trên đường khóa, vì mỗi khóa mới tạo tối đa `w` nút dưới gốc.

**Câu 21.** Trie nén kiểu Patricia giảm nút bằng cách nào?

**Đáp án:** Nén các chuỗi nút chỉ có một con thành cạnh ghi nhận vị trí bit/nhãn tiền tố, giảm nhiều nút trung gian nhưng cần logic xác minh các bit bị bỏ qua.

**Câu 22.** Bài toán tiền tố trong router IP khác trie khóa nguyên 32 bit chỉ có terminal ở lá thế nào?

**Đáp án:** Quy tắc mạng có thể kết thúc tại các độ dài tiền tố khác nhau, nên cần terminal/payload tại nút trong và chọn **tiền tố dài nhất khớp**, không chỉ lá ở độ sâu 32.

**Điểm ghi nhớ:** **Binary trie** biến khóa nguyên thành **đường đi theo bit**, với hai nhánh 0 và 1 ở mỗi tầng. Khi cố định độ dài khóa `w`, thêm/tìm/xóa và nhiều truy vấn theo thứ tự có thể thực hiện trong **O(w)**; đổi lại trie chưa nén có thể dùng **O(nw)** nút. Với Java `int` có dấu, **đảo bit dấu bằng XOR `Integer.MIN_VALUE`** trước khi duyệt MSB-first để giữ thứ tự signed. Bộ đếm `pass` hỗ trợ đếm tiền tố và bảo đảm cắt nhánh sau xóa không làm mất khóa khác. Nếu chỉ cần membership, hãy so sánh với bảng băm/bitset; nếu cần tiền tố, thứ tự hoặc tối ưu XOR, trie bit có lợi thế riêng. Luôn kiểm tra bất biến, ca MIN/MAX, bit 31 và dấu của kết quả XOR trước khi chọn cấu trúc.

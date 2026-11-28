# Cây nhị phân đầy đủ (full), hoàn chỉnh (complete), hoàn hảo (perfect) và suy biến

## 1. Vì sao phải phân biệt hình dạng cây nhị phân?

Trong học phần **Cấu trúc dữ liệu**, **cây nhị phân (binary tree)** là cây có gốc mà mỗi nút có **tối đa hai vị trí con**, phân biệt là **con trái (left)** và **con phải (right)**. Mỗi vị trí có thể chứa một nút hoặc rỗng. Vì thế, nút có không, một hoặc hai con đều hợp lệ.

Cùng một số nút, cây có thể rất rộng và thấp, hoặc rất hẹp và sâu:

```text
Cùng có 7 nút:

Gần cân đối:                   Một nhánh dài:

        A                             A
       / \                           /
      B   C                         B
     / \ / \                       /
    D  E F  G                     C
                                 /
                                D
                               /
                              E
                             /
                            F
                           /
                          G

Chiều cao: 2 cạnh            Chiều cao: 6 cạnh
```

Khác biệt hình dạng ảnh hưởng trực tiếp tới:

- **Chiều cao `h`** và số bước tối đa khi đi dọc một đường từ gốc tới nút.
- **Bộ nhớ call stack** khi xử lý đệ quy và số trạng thái phải giữ khi quay lui.
- **Cách lưu trữ**: cây khít các mức thuận tiện cho mảng, cây thưa thuận tiện cho nút liên kết.
- **Bất biến hình dạng** mà thuật toán chèn, xóa hoặc cân bằng cần duy trì.

Bài này đi sâu vào bốn nhóm thuật ngữ dễ bị nhầm:

| Thuật ngữ | Tên tiếng Anh | Điều kiện cốt lõi |
|---|---|---|
| Cây nhị phân **đầy đủ** | **Full** (còn gọi proper/strict) | Mỗi nút có **0 hoặc đúng 2 con** |
| Cây nhị phân **hoàn chỉnh** | **Complete** | Mọi mức trừ có thể mức cuối đều đầy; mức cuối lấp **liền từ trái sang phải** |
| Cây nhị phân **hoàn hảo** | **Perfect** | **Tất cả** các mức đều đầy |
| Cây nhị phân **suy biến** | **Degenerate** | Mỗi nút có **tối đa 1 con**, nên toàn cây thành một đường đi |

**Lưu ý về thuật ngữ:** cách dịch *full*, *complete*, *perfect* trong các giáo trình tiếng Việt không phải lúc nào cũng thống nhất. Trong bài này, **tên tiếng Anh kèm định nghĩa** là tiêu chuẩn phân loại, không chỉ dựa vào từ “đầy đủ” hay “hoàn chỉnh”.

## 2. Quy ước và các khái niệm nền

Ta xét **cây nhị phân hữu hạn, có gốc, không có chu trình và không chia sẻ cùng một nút dưới nhiều cha**. Cây rỗng được biểu diễn bằng `None`; các công thức liên hệ số nút và chiều cao dưới đây áp dụng cho cây **không rỗng**, trừ khi có ghi rõ.

Quy ước:

- `n`: số nút thực sự của cây.
- `h`: **chiều cao theo số cạnh** trên đường dài nhất từ gốc xuống một lá.
- `depth(u)`: số cạnh từ gốc tới nút `u`.
- Gốc ở **mức 0**; lá có chiều cao **0**.
- Cây rỗng có chiều cao **-1** trong những hàm đệ quy dùng quy ước này.
- “Đầy một mức” nghĩa là có mặt ở **tất cả các vị trí trái/phải khả dĩ** của mức đó.

Trong cây nhị phân, mức `d` có **nhiều nhất `2^d` vị trí nút**:

```text
Mức 0:              □                        tối đa 1 nút
                   / \
Mức 1:            □   □                      tối đa 2 nút
                 / \ / \
Mức 2:          □  □ □  □                    tối đa 4 nút
                ...
Mức d:                                       tối đa 2^d nút
```

Vì vậy, một cây không rỗng cao `h` có thể có từ `h+1` đến `2^(h+1)-1` nút:

\[
h+1 \le n \le \sum_{d=0}^{h}2^d=2^{h+1}-1.
\]

Chặn dưới đạt được ở **một đường đi duy nhất**; chặn trên đạt được khi **tất cả các vị trí của mọi mức đều được lấp đầy**. Các hình dạng full/complete/perfect/degenerate là những tập con cụ thể trong khoảng khả dĩ này.

### Hai ví dụ để đối chiếu

```text
Cây X:                        Cây Y:

       A                             A
      / \                           / \
     B   C                         B   C
    / \                               / \
   D   E                             D   E

Hai cây đều có n=5 nút, h=2 cạnh.
Ở X, D và E là con của B; ở Y, D và E là con của C.
```

Cây X **full và complete**; cây Y **full nhưng không complete**, dù cả hai có cùng số nút và chiều cao. Điều quan trọng khi phân loại là **vị trí trái/phải của mọi nút** và **những mức nào có lỗ**, không phải chỉ đếm số nút hoặc chiều cao.

## 3. Full binary tree — cây nhị phân đầy đủ

### 3.1. Định nghĩa chính xác

Một cây nhị phân là **full** nếu mỗi nút thỏa **một trong hai trường hợp**:

- Không có con trái và không có con phải: **lá**.
- Có **cả con trái và con phải**: **nút trong**.

Không được tồn tại nút chỉ có **một** con.

```text
FULL:                            KHÔNG FULL:

        A                               A
       / \                             / \
      B   C                           B   C
         / \                         /
        D   E                       D

A, C có 2 con.                B chỉ có con trái.
B, D, E là lá.                Vi phạm điều kiện 0 hoặc 2.
```

**Định nghĩa full chỉ kiểm tra số con của từng nút.** Nó **không yêu cầu các lá ở cùng độ sâu** và **không yêu cầu các mức được lấp từ trái sang phải**.

### 3.2. Công thức số nút trong và số lá

Gọi:

- `I` là số **nút trong** (có con).
- `L` là số **lá** (không có con).
- `n=I+L` là tổng số nút.

Trong một cây full không rỗng, mỗi nút trong có **đúng hai cạnh đi xuống**, nên tổng số cạnh là `2I`. Mặt khác, mọi cây có gốc hợp lệ với `n` nút có `n-1` cạnh:

\[
2I=n-1=I+L-1.
\]

Suy ra:

\[
\boxed{L=I+1},\qquad
\boxed{n=2I+1=2L-1}.
\]

Hệ quả:

- Số nút của cây full **luôn là số lẻ**.
- Với `I=4` nút trong, ta phải có `L=5` lá và `n=9` nút.
- Cây **một nút** là full: `I=0` và `L=1`.

**Chiều ngược lại không đúng:** một cây có số nút lẻ chưa chắc full. Ví dụ đường thẳng ba nút có `n=3` nhưng có hai nút chỉ có một con.

### 3.3. Full không đồng nghĩa cân đối hoặc complete

```text
       A
      / \
     B   C
        / \
       D   E

A, C: hai con; B, D, E: lá.
→ Full.

Mức cuối có D, E dưới nhánh phải,
trong khi hai vị trí dưới B ở bên trái còn trống.
→ Không complete, không perfect.
```

Cây này có `5` nút và cao `2` cạnh. Dù full, nó không lấp các vị trí ở mức cuối từ trái sang phải. Vì vậy **full không kéo theo complete**, và cũng không kéo theo perfect.

## 4. Complete binary tree — cây nhị phân hoàn chỉnh

### 4.1. Định nghĩa theo từng mức

Một cây nhị phân không rỗng là **complete** nếu:

1. **Mọi mức trước mức cuối đều đầy**.
2. Ở **mức cuối**, các nút được điền **liên tục từ trái sang phải**, không có vị trí trống nằm trước một vị trí có nút.

Ví dụ complete:

```text
        A
       / \
      B   C
     / \ /
    D  E F

Mức 0: [A]         đầy
Mức 1: [B, C]      đầy
Mức 2: [D, E, F]   chiếm ba vị trí trái nhất
→ Complete.
```

Ví dụ không complete:

```text
        A
       / \
      B   C
         /
        D

Ở mức 2, các vị trí dưới B bị trống,
nhưng dưới C lại có D.
→ Không complete.
```

Ví dụ không complete ngay tại mức 1:

```text
       A
        \
         B

B là con PHẢI của A; vị trí con trái còn trống.
→ Không complete.
```

**Khác biệt cốt lõi so với full:** complete cho phép một nút chỉ có **con trái** ở phần cuối của cây, miễn các vị trí được lấp đúng thứ tự. Nhưng một nút chỉ có **con phải** mà không có con trái sẽ vi phạm complete.

### 4.2. Không chỉ kiểm tra “con phải phải có con trái”

Quy tắc “nút có con phải thì phải có con trái” là **cần nhưng chưa đủ** cho complete.

```text
        A
       / \
      B   C
     /     \
    D       E
```

Từng nút vẫn có thể làm ta nghĩ cấu trúc gần đầy; nhưng ở mức cuối, vị trí ngay sau `D` (con phải của `B`) bị trống trong khi `E` (con phải của `C`) tồn tại. **Mức cuối không liên tục từ trái sang phải**, nên cây không complete.

Thực tế ví dụ này còn có nút `C` chỉ có con phải, nhưng ngay cả khi tránh mọi nút chỉ có con phải, vẫn có thể gặp sai mức:

```text
         A
        / \
       B   C
      /   /
     D   E

B có con trái D, C có con trái E.
Vị trí B.right trống trước vị trí C.left có E.
→ Không complete.
```

Phải kiểm tra **toàn bộ thứ tự vị trí ở các mức**, không chỉ từng cặp con tại một nút.

### 4.3. Kiểm tra complete bằng BFS và “đã gặp lỗ”

Khi duyệt cây theo mức bằng **queue (FIFO)**, xét con trái rồi con phải của từng nút:

- Ban đầu chưa thấy vị trí trống.
- Khi gặp một vị trí con rỗng, bật cờ `seen_gap = True`.
- Kể từ đó, **nếu gặp bất kỳ con nào còn tồn tại, cây không complete**.
- Nếu quét hết mà không gặp trường hợp sai, cây complete.

Vì BFS đi từ mức thấp tới cao và trái tới phải, một nút xuất hiện **sau khi đã có lỗ** chính là dấu hiệu vi phạm quy tắc điền từ trái qua phải.

Phần mã đầy đủ nằm ở mục 9. Thuật toán chỉ cần duyệt mỗi nút một lần: **`O(n)` thời gian**, **`O(w)` bộ nhớ queue** với `w` là số nút lớn nhất cùng chờ trong queue, và `w \le n`.

### 4.4. Complete tree có chiều cao gần nhỏ nhất

Với cây complete gồm `n\ge1` nút, mọi mức trước mức cuối đều đầy. Do đó:

\[
2^h\le n\le 2^{h+1}-1,
\]

suy ra:

\[
\boxed{h=\lfloor\log_2 n\rfloor}.
\]

Ví dụ:

| `n` | Chiều cao complete `h` (theo cạnh) | Số nút mức cuối |
|---:|---:|---:|
| 1 | 0 | 1 |
| 2 | 1 | 1 |
| 3 | 1 | 2 |
| 4 | 2 | 1 |
| 6 | 2 | 3 |
| 7 | 2 | 4 |
| 8 | 3 | 1 |
| 10 | 3 | 3 |

Ở mức cuối `h`, số nút đúng bằng:

\[
\text{lastLevelCount}=n-(2^h-1).
\]

Ví dụ `n=10`, `h=3`; các mức `0,1,2` đã chiếm `1+2+4=7` nút, nên mức `3` có `10-7=3` nút, nằm ở **ba vị trí trái nhất**.

**Lưu ý:** công thức `h=\lfloor\log_2 n\rfloor` là cho **complete tree**, không áp dụng cho mọi cây nhị phân.

## 5. Perfect binary tree — cây nhị phân hoàn hảo

### 5.1. Định nghĩa

Một cây nhị phân **perfect** nếu:

- Mọi nút trong đều có **đúng hai con**.
- **Mọi lá có cùng độ sâu**.

Tương đương: **tất cả các mức từ `0` đến `h` đều đầy**.

```text
           A
         /   \
        B     C
       / \   / \
      D   E F   G

Mức 0 có 1 nút.
Mức 1 có 2 nút.
Mức 2 có 4 nút.
→ Perfect.
```

Một cây perfect **luôn full** (không có nút một con) và **luôn complete** (không có lỗ ở mức cuối). Nhưng điều ngược lại **không đúng cho từng điều kiện riêng rẽ**, thậm chí một cây có thể **vừa full vừa complete nhưng chưa perfect**.

### 5.2. Công thức số nút và số lá

Với chiều cao theo cạnh `h\ge0`:

\[
\boxed{n=1+2+\cdots+2^h=2^{h+1}-1}
\]

và tất cả lá ở mức `h`:

\[
\boxed{L=2^h},\qquad \boxed{I=2^h-1}.
\]

Vì vậy `n=2L-1` và `L=I+1`, phù hợp với tính chất cây full.

Ví dụ:

- `h=0`: `n=1`, `L=1`.
- `h=1`: `n=3`, `L=2`.
- `h=2`: `n=7`, `L=4`.
- `h=3`: `n=15`, `L=8`.

Nếu `n=11`, **không thể** có một cây perfect gồm đúng `11` nút vì `11` không thuộc dãy `1,3,7,15,\ldots`.

**Tuy nhiên**, chỉ có `n=7` **chưa đủ** xác nhận một cây bất kỳ là perfect: bảy nút có thể sắp thành cây lệch. Cần kiểm tra **hình dạng**, hoặc biết trước cây complete rồi dùng số nút thích hợp.

### 5.3. Đặc trưng bằng số nút và chiều cao

Một cây nhị phân không rỗng là perfect **khi và chỉ khi** số nút của nó đạt chặn trên ứng với chiều cao:

\[
n=2^{h+1}-1.
\]

Nếu đạt đúng chặn trên, mọi vị trí nút ở các mức phải tồn tại; thiếu bất kỳ vị trí nào sẽ làm tổng nhỏ hơn. Nhờ đó có thể nhận diện perfect bằng cách **đếm số nút và tính chiều cao**, nhưng một cách khác là kiểm tra trực tiếp **tất cả nút trong có hai con và lá ở cùng độ sâu**.

## 6. Cây nhị phân suy biến (degenerate) và cây lệch (skewed)

### 6.1. Cây suy biến: mỗi nút tối đa một con

Một cây nhị phân **suy biến** nếu tại mọi nút, **không bao giờ đồng thời có cả con trái và con phải**. Nói cách khác, mỗi nút có **0 hoặc 1 con**. Vì mọi nút thuộc cùng một cây, các nút tạo thành một đường đi từ gốc đến lá.

```text
Suy biến dạng thẳng:            Suy biến ngoằn ngoèo:

      A                                A
     /                                /
    B                                B
   /                                  \
  C                                    C
 /                                    /
D                                    D
```

Cả hai đều **degenerate**: không nút nào có hai con. Đối với cây không rỗng gồm `n` nút:

\[
\boxed{h=n-1},\qquad
\boxed{L=1},\qquad
\boxed{I=n-1}.
\]

Trong những công thức này, chiều cao tính theo cạnh. Cây suy biến chỉ có **một lá** là nút cuối cùng trên đường đi; mọi nút còn lại có một con.

### 6.2. Cây lệch trái/phải và sự khác biệt với suy biến

**Cây lệch trái (left-skewed):** mọi nút trong chỉ có **con trái**.

**Cây lệch phải (right-skewed):** mọi nút trong chỉ có **con phải**.

Đây là hai trường hợp đặc biệt của degenerate tree.

```text
Left-skewed:    Right-skewed:     Degenerate, nhưng không skewed thẳng:

      A               A                      A
     /                 \                    /
    B                   B                  B
   /                     \                  \
  C                       C                  C
 /                         \                /
D                           D              D
```

Đôi khi tài liệu dùng “skewed” như tên gọi chung cho mọi cây suy biến. Để chính xác, bài này dùng **degenerate** cho mọi đường đi một con, kể cả đường **đổi hướng trái–phải**, và **left/right-skewed** cho đường chỉ đi **một hướng nhất quán**.

Với cây một nút, không tồn tại cạnh định hướng. Bài này coi nó là **degenerate**, đồng thời thỏa điều kiện left/right-skewed **theo nghĩa không có cạnh nào vi phạm**; nếu cần phân loại độc quyền “trái” hoặc “phải”, ứng dụng có thể trả một nhãn riêng như `single-node`.

### 6.3. Cây suy biến liên quan thế nào tới full/complete/perfect?

- Nếu `n=1`: cây một nút là **full, complete, perfect và degenerate**.
- Nếu `n=2` và nút thứ hai là **con trái** của gốc: cây **complete và degenerate**, nhưng **không full, không perfect**.
- Nếu `n=2` và nút thứ hai chỉ là **con phải**: cây **degenerate**, nhưng **không complete**, không full, không perfect.
- Nếu `n\ge3` và cây degenerate: **không complete** (vì muốn có nút ở mức 2 thì mức 1 phải đầy hai vị trí; cây degenerate không thể có đủ), đồng thời **không full và không perfect**.

Lý do cây suy biến với `n\ge2` không full: ít nhất gốc có **một con**, vi phạm điều kiện 0 hoặc 2. Nó cũng không perfect vì không thể lấp đủ hai con ở mức 1.

### 6.4. Hệ quả về độ phức tạp

Cây suy biến có chiều cao `h=n-1`. Nếu một thuật toán phải lần theo một đường từ gốc tới lá, độ dài đường đi là **`O(n)`**, không phải `O(\log n)`.

Với DFS **đệ quy**, số khung lời gọi đang hoạt động có thể tỷ lệ với `n`, dẫn đến chi phí bộ nhớ **`O(n)`** và nguy cơ chạm giới hạn đệ quy của runtime. Tuy nhiên, BFS trên cây suy biến chỉ có thể có một nút chờ tại mỗi thời điểm (theo cách duyệt thông thường), nên riêng **queue BFS** chỉ cần `O(1)` phần tử chờ. Không nên mặc định mọi thuật toán đều dùng `O(n)` bộ nhớ phụ trên cây suy biến.

**Không có thứ tự khóa thì cây suy biến vẫn chỉ là một hình dạng**, chưa phải BST. Nếu gắn thêm bất biến BST vào một đường lệch, việc tìm khóa trong BST không cân bằng có thể suy giảm từ `O(\log n)` kỳ vọng ở cây cân bằng xuống **`O(n)` trong trường hợp xấu nhất**.

## 7. Quan hệ giữa bốn nhóm: không được suy luận ngược

Bốn loại hình dạng không tạo thành một chuỗi bao hàm đơn giản.

### Những quan hệ luôn đúng

- **Perfect ⇒ Full.**
- **Perfect ⇒ Complete.**
- **Perfect ⇒ Full và Complete.**
- **Degenerate ⇒ có nhiều nhất một con mỗi nút**; vì thế nếu cây có hơn một nút thì **không Full**.
- **Left-skewed/Right-skewed ⇒ Degenerate.**

### Những suy luận sai thường gặp

- **Full ⇒ Complete**: sai.
- **Complete ⇒ Full**: sai.
- **Full và Complete ⇒ Perfect**: **vẫn sai**.
- **Cây có số nút bằng `2^k-1` ⇒ Perfect**: sai nếu không biết hình dạng.
- **Cây có chiều cao nhỏ ⇒ Perfect**: sai, trừ khi còn các điều kiện lấp đầy cần thiết.

### Phản ví dụ quan trọng: vừa full vừa complete nhưng chưa perfect

```text
          A
         / \
        B   C
       / \
      D   E

A có 2 con, B có 2 con; C, D, E là lá.
→ FULL.

Các mức trước mức cuối đều đầy.
Mức cuối có D và E chiếm hai vị trí trái nhất.
→ COMPLETE.

Nhưng C là lá ở độ sâu 1,
trong khi D, E là lá ở độ sâu 2.
→ KHÔNG PERFECT.
```

Bất kỳ lập luận nào kết luận “full + complete = perfect” đều bỏ sót điều kiện **mọi lá cùng độ sâu**. Perfect yêu cầu tất cả các vị trí ở mức cuối được lấp kín, còn complete chỉ yêu cầu **lấp liên tục từ trái qua phải**.

### Bảng so sánh nhiều hình dạng

| Hình dạng cây không rỗng | Full | Complete | Perfect | Degenerate |
|---|:---:|:---:|:---:|:---:|
| Một nút `A` | Có | Có | Có | Có |
| `A` chỉ có con trái `B` | Không | Có | Không | Có |
| `A` chỉ có con phải `B` | Không | Không | Không | Có |
| Gốc và hai lá con | Có | Có | Có | Không |
| Gốc có hai con; chỉ **con trái** có hai lá con | Có | Có | Không | Không |
| Gốc có hai con; chỉ **con phải** có hai lá con | Có | Không | Không | Không |
| Đường ngoằn ngoèo bốn nút | Không | Không | Không | Có |
| Cây bảy nút có mọi mức từ 0 tới 2 đều đầy | Có | Có | Có | Không |

## 8. Công thức, giới hạn và các tình huống tính toán

Gọi `n` là số nút, `h` là chiều cao theo cạnh, `I` là số nút trong và `L` là số lá. Các công thức trong bảng sau áp dụng cho **cây không rỗng**.

| Loại cây | Số nút `n` | Số lá `L` | Chiều cao `h` |
|---|---|---|---|
| Nhị phân bất kỳ | `h+1≤n≤2^(h+1)-1` | Phụ thuộc hình dạng | `⌈log₂(n+1)⌉-1≤h≤n-1` |
| Full | `n=2I+1=2L-1` | `L=I+1` | Có thể lớn nếu nhánh sâu |
| Complete | `2^h≤n≤2^(h+1)-1` | `⌈n/2⌉` | `h=⌊log₂ n⌋` |
| Perfect | `n=2^(h+1)-1` | `L=2^h` | `h=log₂(n+1)-1` |
| Degenerate | `n=h+1` | `1` | `h=n-1` |

### 8.1. Tại sao complete tree có `⌈n/2⌉` lá?

Một cây complete lưu theo level-order có thể đánh số nút liên tiếp từ `0` tới `n-1`. Với nút ở chỉ số `i`:

- Con trái, nếu có, ở `2i+1`.
- Con phải, nếu có, ở `2i+2`.

Một nút là **nút trong** nếu tồn tại con trái, tức `2i+1<n`. Những chỉ số này chính là `0,1,\ldots,\lfloor n/2\rfloor-1`, gồm **`⌊n/2⌋` nút trong**. Do đó:

\[
L=n-\lfloor n/2\rfloor=\boxed{\lceil n/2\rceil}.
\]

Ví dụ complete tree có `n=10` nút: `I=5` và `L=5`. Với `n=9`, `I=4` và `L=5`.

**Công thức này không áp dụng cho cây nhị phân tùy ý.** Một cây suy biến mười nút chỉ có **một lá**, không phải năm lá.

### 8.2. Tối đa mấy nút với chiều cao cho trước?

Ví dụ `h=4`:

- Nhị phân bất kỳ: tối đa `2^5-1=31` nút.
- Perfect cao `4`: **đúng** `31` nút và `16` lá.
- Complete cao `4`: có từ `2^4=16` tới `31` nút.
- Degenerate cao `4`: **đúng** `5` nút.
- Full cao `4`: có ít nhất một đường 4 cạnh và mỗi nút trong trên đường phải có một con bổ sung; vì thế tối thiểu **`2h+1=9` nút**, nhiều nhất `31` nút.

Chặn dưới `2h+1` cho cây full có chiều cao `h` được chứng minh bằng cách xét một đường sâu nhất gồm `h` nút trong và một lá cuối: mỗi nút trong trên đường có **một nhánh con còn lại**, chứa ít nhất một nút lá khác; tổng tối thiểu `(h+1)+h=2h+1` nút.

### 8.3. Biết số nút có thể suy ra dạng cây không?

Chỉ từ `n`:

- Có thể suy ra **khoảng chiều cao khả dĩ** cho cây nhị phân.
- **Không thể** kết luận nó full, complete, perfect hay degenerate.
- Nếu cây **đã biết complete**, có thể suy ra chiều cao bằng `⌊log₂n⌋` và số lá bằng `⌈n/2⌉`.
- Nếu cây **đã biết full**, có thể suy ra `L=(n+1)/2`, nhưng không biết mức cuối có lỗ hay không.
- Nếu cây **đã biết perfect**, `n+1` phải là lũy thừa của `2`.
- Nếu cây **đã biết degenerate**, chiều cao bắt buộc bằng `n-1`.

**Hệ quả đáng chú ý:** một cây complete có đúng `n=2^k-1` nút (`k\ge1`) sẽ là perfect. Khi complete và số nút lấp đầy tới ranh giới mức `k-1`, không còn lỗ nào ở mức cuối. Nhưng nếu chỉ biết `n=2^k-1` mà không có điều kiện complete thì chưa thể kết luận perfect.

## 9. Cài đặt Python: phân loại hình dạng cây

Ta dùng nút liên kết với hai tham chiếu `left` và `right`. Các hàm dưới đây giả định **đầu vào đã là một cây nhị phân hợp lệ**: không có chu trình, không có nút bị chia sẻ giữa nhiều đường đi. Việc xác thực một đồ thị tham chiếu bất kỳ là bài toán riêng; nếu không có giả định này, một số phép duyệt có thể thăm lặp hoặc không kết thúc.

### 9.1. Lớp nút

```python
from collections import deque


class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right
```

### 9.2. Kiểm tra full bằng DFS

Một nút vi phạm full khi có **chính xác một** trong hai con:

```python
def is_full(root):
    if root is None:
        return True

    stack = [root]

    while stack:
        node = stack.pop()

        has_left = node.left is not None
        has_right = node.right is not None

        if has_left != has_right:
            return False

        if has_left:
            stack.append(node.left)
            stack.append(node.right)

    return True
```

Giải thích:

- Nếu `has_left` và `has_right` đều sai: đây là lá, hợp lệ.
- Nếu đều đúng: nút trong có đúng hai con, hợp lệ; tiếp tục kiểm tra hai cây con.
- Nếu khác nhau: nút có đúng một con, **không full**.

**Độ phức tạp:** tối đa `O(n)` thời gian, stack DFS `O(h+1)` phần tử trong cách duyệt nhị phân này.

### 9.3. Kiểm tra complete bằng BFS và cờ `seen_gap`

```python
def is_complete(root):
    if root is None:
        return True

    pending = deque([root])
    seen_gap = False

    while pending:
        node = pending.popleft()

        # Thứ tự trái rồi phải là bắt buộc.
        for child in (node.left, node.right):
            if child is None:
                seen_gap = True
            else:
                if seen_gap:
                    return False
                pending.append(child)

    return True
```

**Bất biến:** trước khi gặp lỗ đầu tiên, các vị trí con đã xét đều có nút. Một khi `seen_gap=True`, không được xuất hiện nút ở **bất kỳ vị trí con nào đến sau** theo thứ tự level-order. Nếu gặp, tồn tại lỗ ở bên trái/trước một nút đang có, vi phạm complete.

**Độ phức tạp:** `O(n)` thời gian, queue tối đa `O(n)` bộ nhớ phụ. Kiểm tra `seen_gap` ở cấp độ **toàn bộ quá trình BFS**, không đặt lại cờ sau mỗi nút.

### 9.4. Kiểm tra perfect: đủ hai con và lá cùng độ sâu

```python
def is_perfect(root):
    if root is None:
        return True

    pending = [(root, 0)]
    expected_leaf_depth = None

    while pending:
        node, depth = pending.pop()
        left = node.left
        right = node.right

        if left is None and right is None:
            if expected_leaf_depth is None:
                expected_leaf_depth = depth
            elif depth != expected_leaf_depth:
                return False

        elif left is None or right is None:
            # Nút trong chỉ có một con: không perfect.
            return False

        else:
            pending.append((left, depth + 1))
            pending.append((right, depth + 1))

    return True
```

Hàm kết hợp **hai điều kiện**:

1. Tất cả nút trong có hai con (full).
2. Tất cả lá xuất hiện cùng một mức (perfect).

Chỉ kiểm tra các lá cùng độ sâu **không đủ**, vì cây một đường đi cũng chỉ có một lá nhưng không perfect khi có hơn một nút. Tương tự, chỉ kiểm tra full **không đủ** vì lá có thể nằm ở các độ sâu khác nhau.

**Độ phức tạp:** `O(n)` thời gian, `O(h+1)` bộ nhớ stack DFS cho cây nhị phân hợp lệ.

### 9.5. Kiểm tra degenerate, left-skewed và right-skewed

Vì một cây degenerate chỉ có một đường đi, không cần queue hoặc stack. Ta đi dọc nhánh duy nhất:

```python
def is_degenerate(root):
    if root is None:
        return False  # Quy ước: không phân loại cây rỗng là suy biến

    node = root

    while node is not None:
        if node.left is not None and node.right is not None:
            return False

        node = node.left if node.left is not None else node.right

    return True


def is_left_skewed(root):
    if root is None:
        return False

    node = root
    while node is not None:
        if node.right is not None:
            return False
        node = node.left

    return True


def is_right_skewed(root):
    if root is None:
        return False

    node = root
    while node is not None:
        if node.left is not None:
            return False
        node = node.right

    return True
```

- `is_degenerate` chỉ yêu cầu tối đa một con, **không quan tâm hướng**.
- `is_left_skewed` loại mọi nút có con phải.
- `is_right_skewed` loại mọi nút có con trái.

**Độ phức tạp:** mỗi hàm đi qua tối đa `n` nút, nên `O(n)` thời gian và **`O(1)` bộ nhớ phụ**. Với một nút duy nhất, cả ba hàm đều trả `True` theo quy ước đã nêu.

### 9.6. Về trường hợp cây rỗng

Các hàm `is_full(None)`, `is_complete(None)` và `is_perfect(None)` ở đây trả `True` theo **quy ước mệnh đề đúng một cách rỗng (vacuous truth)**: không có nút nào vi phạm điều kiện. `is_degenerate(None)` trả `False` vì bài này chỉ phân loại cây suy biến khi **có ít nhất một nút**.

Đây là **quyết định về hợp đồng API**, không phải một quy tắc thống nhất ở mọi tài liệu. Một hệ thống có thể chọn trả `False` cho tất cả dạng cây khi rỗng; điều quan trọng là **quy định rõ và kiểm thử nhất quán**. Các công thức `L=I+1` hay `n=2^{h+1}-1` ở trên chỉ áp dụng cho cây **không rỗng**.

## 10. Thử phân loại trên các hình dạng tiêu biểu

Tạo các cây khác nhau và gọi các hàm đã định nghĩa. Mỗi ví dụ dùng **những đối tượng nút riêng**, tránh vô ý dùng chung nút giữa các cây.

```python
# 1. Perfect: 7 nút, h=2.
perfect = Node(
    "A",
    Node("B", Node("D"), Node("E")),
    Node("C", Node("F"), Node("G"))
)

# 2. Full nhưng không complete: nhánh phải có hai con.
full_not_complete = Node(
    "A",
    Node("B"),
    Node("C", Node("D"), Node("E"))
)

# 3. Complete nhưng không full: B chỉ có con trái D.
complete_not_full = Node(
    "A",
    Node("B", Node("D")),
    Node("C")
)

# 4. Full và complete nhưng không perfect:
#    lá C ở mức 1, D và E ở mức 2.
full_complete_not_perfect = Node(
    "A",
    Node("B", Node("D"), Node("E")),
    Node("C")
)

# 5. Degenerate ngoằn ngoèo: đổi hướng trái-phải-trái.
zigzag = Node("A", Node("B", right=Node("C", Node("D"))))

# 6. Left-skewed: mọi cạnh đi sang trái.
left_chain = Node("A", Node("B", Node("C")))

# 7. Cây chỉ có một nút.
single = Node("A")


def describe(root):
    return {
        "full": is_full(root),
        "complete": is_complete(root),
        "perfect": is_perfect(root),
        "degenerate": is_degenerate(root),
        "left_skewed": is_left_skewed(root),
        "right_skewed": is_right_skewed(root),
    }


print(describe(perfect))
# {'full': True, 'complete': True, 'perfect': True,
#  'degenerate': False, 'left_skewed': False, 'right_skewed': False}

print(describe(full_complete_not_perfect))
# {'full': True, 'complete': True, 'perfect': False,
#  'degenerate': False, 'left_skewed': False, 'right_skewed': False}

print(describe(zigzag))
# {'full': False, 'complete': False, 'perfect': False,
#  'degenerate': True, 'left_skewed': False, 'right_skewed': False}

print(describe(single))
# {'full': True, 'complete': True, 'perfect': True,
#  'degenerate': True, 'left_skewed': True, 'right_skewed': True}
```

### Những phép kiểm tra nhanh

```python
assert is_perfect(perfect)
assert is_full(perfect)
assert is_complete(perfect)

assert is_full(full_not_complete)
assert not is_complete(full_not_complete)

assert is_complete(complete_not_full)
assert not is_full(complete_not_full)

assert is_full(full_complete_not_perfect)
assert is_complete(full_complete_not_perfect)
assert not is_perfect(full_complete_not_perfect)

assert is_degenerate(zigzag)
assert not is_left_skewed(zigzag)
assert not is_right_skewed(zigzag)

assert is_degenerate(left_chain)
assert is_left_skewed(left_chain)
assert not is_complete(left_chain)

assert is_full(single)
assert is_complete(single)
assert is_perfect(single)
assert is_degenerate(single)

assert is_complete(Node("A", left=Node("B")))
assert not is_complete(Node("A", right=Node("B")))
```

Những đoạn mã là **ví dụ học tập** để tự thực hành. Độ phức tạp tổng thể của mỗi phép kiểm tra không đổi giữa các hình dạng, nhưng dữ liệu khác nhau sẽ khiến thuật toán dừng sớm hay đi tới cuối cây.

## 11. Mảng level-order và ưu thế của complete tree

Cây complete có các nút lấp liên tục theo thứ tự mức. Vì thế, ta có thể lưu `n` phần tử vào một mảng từ chỉ số `0` tới `n-1`:

```text
Cây complete:

         A
        / \
       B   C
      / \ /
     D  E F

Mảng:
Chỉ số:   0  1  2  3  4  5
Giá trị:  A  B  C  D  E  F
```

Các công thức chỉ số **0-based**:

\[
\begin{aligned}
\operatorname{left}(i)&=2i+1,\\
\operatorname{right}(i)&=2i+2,\\
\operatorname{parent}(i)&=\left\lfloor\frac{i-1}{2}\right\rfloor \quad(i>0).
\end{aligned}
\]

Nếu chỉ số con không nhỏ hơn `n`, vị trí con đó không tồn tại.

### Vì sao dùng mảng đặc không đúng cho cây bất kỳ?

Xét:

```text
       A
      / \
     B   C
          \
           D
```

Nếu tạo mảng `[A,B,C,D]` và áp công thức trên, chỉ số `3` sẽ được hiểu là **con trái của B**, không phải con phải của `C`. Để giữ chính xác cấu trúc theo vị trí mức, phải chừa các lỗ:

```text
[A, B, C, None, None, None, D]
```

Trên cây suy biến rất sâu, chỉ số vị trí lớn nhất có thể tăng **theo lũy thừa của 2 theo độ sâu**, dù chỉ có `n` nút thật. Cấp phát một mảng tới chỉ số ấy gây lãng phí bộ nhớ nghiêm trọng.

Vì vậy:

- **Complete tree:** mảng đặc thường rất phù hợp; điển hình là binary heap.
- **Perfect tree:** cũng complete, nên lưu mảng đặc hiệu quả.
- **Full nhưng không complete:** có thể có lỗ; không nên nén mảng như thể complete.
- **Degenerate tree:** thường phù hợp hơn với nút liên kết; với một đường dài, chỉ cần `n` nút thay vì mảng vị trí rất lớn.

### Kiểm tra số lá của complete tree qua chỉ số

Với `n=6`, chỉ số nút trong là `0,1,2`; chỉ số lá là `3,4,5`. Với `n=7`, chỉ số nút trong vẫn `0,1,2` và lá là `3,4,5,6`.

Tổng quát:

- Nút trong: chỉ số `0` tới `⌊n/2⌋-1`.
- Lá: chỉ số `⌊n/2⌋` tới `n-1`.

Đây là cách nhìn trực tiếp cho công thức **`L=⌈n/2⌉`** của complete tree.

## 12. Hình dạng ảnh hưởng thế nào đến thuật toán?

### 12.1. Truy vấn đi theo một nhánh

Nếu một thuật toán **mỗi bước chỉ chọn một con** để đi tiếp, số bước nhiều nhất tỷ lệ với chiều cao `h`:

- Complete/perfect: `h=\Theta(\log n)` khi `n` tăng.
- Degenerate: `h=n-1=\Theta(n)`.
- Full: **không tự bảo đảm** `h=O(\log n)`; cây full vẫn có thể có một nhánh rất sâu.

Ví dụ **BST** tìm kiếm dựa trên so sánh khóa và chỉ đi trái hoặc phải; nếu BST suy biến, tìm kiếm có thể mất `O(n)`. Nhưng đây là **tính chất kết hợp hình dạng với bất biến BST**, không có nghĩa mọi cây complete tự tìm khóa nhanh khi giá trị được đặt tùy ý.

### 12.2. Thuật toán duyệt toàn bộ cây

Đếm nút, tính tổng giá trị hoặc duyệt tất cả nút cần xử lý mỗi nút ít nhất một lần, nên thông thường tốn **`O(n)` thời gian** trên mọi hình dạng hợp lệ.

Thay đổi hình dạng chủ yếu ảnh hưởng **bộ nhớ phụ**:

- DFS **đệ quy** có thể cần `O(h+1)` khung gọi.
- DFS preorder nhị phân bằng stack tường minh có thể cần `O(h+1)` nút đang chờ.
- BFS bằng queue có thể cần `O(w)`, trong đó `w` là số nút chờ lớn nhất, và có chặn trên `O(n)`.

Với cây suy biến, `h=n-1` nhưng mức rộng nhất chỉ có **một nút**. Khi BFS, queue có thể chỉ giữ một nút, còn call stack của DFS đệ quy có thể sâu `O(n)`.

Với cây perfect, chiều cao chỉ `O(\log n)` nhưng một mức dưới cùng có `\Theta(n)` nút, nên BFS vẫn có thể cần **`O(n)` bộ nhớ**.

### 12.3. Chèn và xóa

**Full:** chèn một nút đơn lẻ vào vị trí con trống của một lá sẽ tạo nút có một con, làm **mất tính full**. Một thao tác muốn giữ full thường phải tổ chức thêm con theo cặp hoặc tái cấu trúc.

**Complete:** chèn phải lấp **vị trí còn thiếu tiếp theo theo level-order**; xóa phải có quy tắc tránh tạo lỗ trước các nút còn lại. Binary heap thường đưa nút cuối lên vị trí bị xóa và điều chỉnh giá trị để giữ cả hình dạng complete lẫn bất biến heap.

**Perfect:** không thể tăng từ `n=2^{h+1}-1` lên `n+1` bằng cách thêm một nút mà vẫn perfect; muốn tăng chiều cao lên `h+1` và vẫn perfect phải có `2^{h+2}-1` nút, tức bổ sung **`2^{h+1}` nút** nếu giữ cấu trúc gốc theo mức.

**Degenerate:** chèn một nút như con duy nhất của lá có thể giữ suy biến; chèn thêm con thứ hai cho một nút trong sẽ làm mất tính suy biến. Nếu muốn giữ left-skewed/right-skewed, còn phải giữ đúng **hướng** của liên kết.

Không có chính sách chèn/xóa duy nhất được suy ra từ tên “cây nhị phân”. Hãy xác định **bất biến cần giữ** trước khi thiết kế thao tác cập nhật.

## 13. Lỗi nhận diện và phân tích thường gặp

1. **Hiểu full là mọi nút có đúng hai con.** Lá có **0 con** vẫn hợp lệ trong full; cây một nút là full.
2. **Nhầm full với complete.** Full xét từng nút có 0/2 con; complete xét **vị trí theo mức**, không chỉ số con tại mỗi nút.
3. **Tưởng complete bắt buộc mọi mức đầy.** Mức cuối được phép chưa đầy, miễn các nút đứng liên tục từ trái sang phải.
4. **Tưởng full + complete chắc chắn perfect.** Cây có gốc hai con, chỉ con trái có hai lá là phản ví dụ.
5. **Quên rằng nút có con phải nhưng thiếu con trái không complete.** Đó là một lỗ xuất hiện trước nút có mặt.
6. **Chỉ kiểm tra một nút mà bỏ qua các lỗ ở mức khác.** Cờ `seen_gap` trong BFS phải tồn tại xuyên suốt toàn bộ quá trình.
7. **Chỉ kiểm tra lá cùng độ sâu để kết luận perfect.** Cây đường thẳng chỉ có một lá, nhưng không perfect nếu có hơn một nút.
8. **Dùng `L=I+1` cho mọi cây nhị phân.** Đó là công thức cho **full**, không phải cây bất kỳ.
9. **Dùng `L=⌈n/2⌉` cho cây tùy ý.** Công thức này cần **complete tree**.
10. **Cho rằng có `n=2^k-1` là perfect.** Cần biết hình dạng; con số phù hợp chưa chứng minh mọi mức đầy.
11. **Cho rằng suy biến luôn chỉ có cạnh trái hoặc chỉ có cạnh phải.** Có cây degenerate **ngoằn ngoèo** đổi hướng.
12. **Dùng công thức `h=⌊log₂n⌋` cho mọi cây nhị phân.** Cây suy biến cao `n-1`.
13. **Cho rằng full tự cân bằng.** Một cây full có thể có một nhánh dài và nhiều lá nhỏ bên cạnh.
14. **Nhầm số nút với số cạnh trên đường đi.** Đường có `k` nút chứa `k-1` cạnh; chiều cao theo cạnh và theo nút khác nhau một.
15. **Lưu cây thưa bằng mảng nén mà không giữ ô rỗng.** Công thức chỉ số cha–con sẽ trả sai vị trí.
16. **Bỏ qua cây rỗng và cây một nút.** Phải quy định đầu ra nhất quán trước khi viết bộ phân loại.
17. **Đo độ phức tạp chỉ bằng `h` cho mọi phép toán.** Một phép duyệt tất cả nút vẫn mất `O(n)` dù cây thấp.
18. **Dùng các hàm phân loại trên đồ thị có chu trình hoặc nút dùng chung.** Phải xác thực đầu vào là cây thực sự; không nên giả định mọi đối tượng có trường `left/right` đều hợp lệ.

## 14. Bài tập luyện tập có đáp án

### Bài 1. Full hay không?

Cho cây:

```text
      A
     / \
    B   C
       / \
      D   E
```

Cây có full không? Có complete không?

**Đáp án:** **Full** vì `A,C` có hai con, `B,D,E` là lá. **Không complete** vì có hai vị trí trống ở đầu mức cuối dưới `B` trước các nút `D,E` dưới `C`.

### Bài 2. Complete nhưng không full

Cho cây có gốc `A`, con trái `B`, con phải `C`, và `B` có duy nhất con trái `D`. Cây thuộc các loại nào?

**Đáp án:** **Complete** vì mức cuối có đúng một nút `D` tại vị trí trái nhất. **Không full** vì `B` có một con; **không perfect** vì mức cuối chưa đầy.

### Bài 3. Full và complete có chắc perfect không?

Cây `A` có hai con `B,C`; `B` có hai con `D,E`; `C` là lá. Phân loại cây.

**Đáp án:** **Full** và **complete**, nhưng **không perfect** vì `C` là lá ở mức 1 còn `D,E` ở mức 2.

### Bài 4. Cây hoàn hảo cao 4

Một perfect tree có chiều cao `h=4` cạnh. Hỏi số nút, số lá và số nút trong?

**Đáp án:** `n=2^5-1=31`, `L=2^4=16` và `I=15`.

### Bài 5. Tính từ số nút

Một cây complete có `n=10` nút. Chiều cao theo cạnh, số lá và số nút mức cuối là bao nhiêu?

**Đáp án:** `h=⌊log₂10⌋=3`; `L=⌈10/2⌉=5`. Số nút mức cuối là `10-(2³-1)=10-7=3`.

### Bài 6. Định lý cây full

Một cây full có `I=8` nút trong. Số lá và tổng số nút là bao nhiêu?

**Đáp án:** `L=I+1=9`, `n=2I+1=17`.

### Bài 7. Có đúng 9 nút thì chắc full?

Một cây nhị phân có `9` nút. Có thể kết luận nó full không?

**Đáp án:** **Không.** Full bắt buộc có số nút lẻ, nhưng số nút lẻ chỉ là **điều kiện cần**, chưa đủ. Một cây đường thẳng chín nút không full.

### Bài 8. Degenerate nhưng không skewed

Cho cây:

```text
    A
   /
  B
   \
    C
   /
  D
```

Cây có degenerate không? Có left-skewed hoặc right-skewed không? Chiều cao bằng mấy?

**Đáp án:** **Degenerate** vì mỗi nút tối đa một con. **Không** left-skewed và **không** right-skewed vì đường đi đổi hướng. Có `4` nút nên `h=3` cạnh.

### Bài 9. Suy biến có thể complete không?

Một cây degenerate có `n=2` nút. Khi nào nó complete? Nếu có `n=5` thì còn complete được không?

**Đáp án:** Với `n=2`, chỉ **con trái của gốc** tạo complete tree; chỉ con phải thì không. Với `n=5`, cây degenerate **không thể complete**, vì để có nút ở mức 2 thì mức 1 phải đầy hai con của gốc.

### Bài 10. Độ cao tối thiểu và tối đa

Một cây nhị phân bất kỳ có `n=13` nút. Chiều cao theo cạnh có thể nhỏ nhất và lớn nhất bao nhiêu?

**Đáp án:** Nhỏ nhất `⌈log₂(14)⌉-1=3`; lớn nhất `13-1=12` cạnh.

### Bài 11. Giữ bất biến khi chèn

Một cây full có `7` nút. Nếu thêm đúng một nút mới bằng cách đặt nó làm con của một lá đang có, cây có còn full không? Vì sao?

**Đáp án:** **Không.** Lá cũ trở thành nút trong chỉ có **một con**, vi phạm điều kiện của full.

### Bài 12. Mảng complete

Một cây complete có `n=9` nút được lưu trong mảng đánh chỉ số từ `0`. Nút ở vị trí `i=3` có con trái và con phải không?

**Đáp án:** Vị trí con trái là `2×3+1=7`, con phải là `2×3+2=8`; cả hai chỉ số đều nhỏ hơn `9` nên **đều tồn tại**.

### Bài 13. Nhận diện perfect qua số nút và complete

Một cây complete có `n=15` nút. Nó có perfect không? Nếu một cây bất kỳ có `n=15` thì sao?

**Đáp án:** Cây **complete có 15 nút** là perfect vì `15=2^4-1`, đủ lấp mọi mức tới `3`. Với **cây bất kỳ** có `15` nút, chưa thể kết luận perfect nếu không biết hình dạng.

### Bài 14. Truy vấn trên cây suy biến

Một cây suy biến có `n=1000` nút. DFS đệ quy đi từ gốc đến lá sâu nhất cần giữ bao nhiêu khung gọi theo bậc tăng trưởng? BFS cần bao nhiêu nút chờ?

**Đáp án:** Độ sâu lời gọi đệ quy có thể đạt **`Θ(n)`**, tức cỡ 1000 khung nếu mỗi nút tạo một lời gọi. Với queue BFS trên cây một đường đi, mỗi lần chỉ có tối đa **một nút chờ**, nên riêng queue cần **`O(1)`** bộ nhớ phụ.

### Bài 15. Full height cho trước

Một cây full có chiều cao `h=3` cạnh. Số nút ít nhất và nhiều nhất có thể là bao nhiêu?

**Đáp án:** Ít nhất `2h+1=7` nút: trên một đường dài 3 cạnh, mỗi nút trong của đường có thêm một lá ở nhánh kia. Nhiều nhất `2^(h+1)-1=15` nút nếu mọi mức đều đầy.

### Bài 16. Chiều cao theo số nút

Một complete tree có `n=8` nút. Tính chiều cao theo cạnh và theo số nút.

**Đáp án:** Theo cạnh `⌊log₂8⌋=3`; theo số nút là `3+1=4`.

### Bài 17. Phân loại cây rỗng

Vì sao một hàm có thể trả `True` cho `is_full(None)` nhưng trả `False` cho `is_degenerate(None)`?

**Đáp án:** Đây là **quy ước API**: các điều kiện full/complete/perfect có thể được coi là đúng khi không có nút nào vi phạm; trong khi degenerate được bài này định nghĩa cho cây không rỗng. Một thư viện khác có thể chọn quy ước khác, nhưng phải nêu rõ và áp dụng nhất quán; các công thức đếm luôn cần kiểm tra `n\ge1`.

### Bài 18. Phân biệt hoàn chỉnh với tìm kiếm nhanh

Một cây complete có `10000` nút lưu các giá trị không có thứ tự. Có thể chắc chắn tìm một giá trị bất kỳ trong `O(\log n)` thời gian không?

**Đáp án:** **Không.** Complete bảo đảm chiều cao thấp, nhưng **không có bất biến giá trị** để biết nên đi trái hay phải. Trong trường hợp xấu nhất vẫn phải xem nhiều nhất `n` nút, tức `O(n)`. Muốn tìm kiếm theo đường đi cần quy tắc khóa phù hợp, chẳng hạn BST cân bằng.

## 15. Tổng kết

Bốn thuật ngữ mô tả **những ràng buộc hình dạng khác nhau** của cây nhị phân:

- **Full**: mỗi nút có **0 hoặc 2 con**; suy ra `L=I+1` và số nút luôn lẻ.
- **Complete**: mọi mức trước mức cuối đầy, mức cuối điền **từ trái qua phải**; suy ra `h=⌊log₂n⌋` và `L=⌈n/2⌉`.
- **Perfect**: mọi mức đều đầy; suy ra `n=2^(h+1)-1` và `L=2^h`. Perfect luôn full và complete, nhưng **full + complete chưa chắc perfect**.
- **Degenerate**: mỗi nút tối đa **một con**, toàn cây là đường đi; có `h=n-1`. Cây skewed trái/phải là trường hợp đường đi luôn theo một hướng, còn degenerate có thể đổi hướng.

Để áp dụng đúng, hãy phát biểu rõ **bất biến**, **quy ước chiều cao và cây rỗng**, xử lý đúng **vị trí trái/phải**, rồi chọn thuật toán kiểm tra phù hợp: **DFS** để phát hiện nút có một hoặc hai con và độ sâu lá; **BFS với cờ gặp lỗ** để kiểm tra complete; duyệt dọc nhánh duy nhất để kiểm tra degenerate.

Cuối cùng, hình dạng quyết định chiều cao và cách lưu trữ, nhưng **không thay thế cho bất biến về giá trị**. Một cây complete không tự trở thành BST, và một cây full không tự cân bằng. Lựa chọn đúng cấu trúc dữ liệu luôn phải dựa đồng thời trên yêu cầu thao tác, bất biến cần duy trì, thời gian và bộ nhớ.

# Bộ đệm khoảng trống (gap buffer) cho chỉnh sửa văn bản cục bộ

## 1. Vì sao một trình soạn thảo văn bản cần cấu trúc dữ liệu chuyên biệt?

Khi dùng trình soạn thảo, người dùng thường đặt con trỏ tại một vị trí rồi thực hiện **nhiều thao tác liên tiếp quanh vị trí đó**: gõ chữ, nhấn Backspace, xóa ký tự phía trước, thay thế từ hoặc chèn đoạn văn ngắn. Mặc dù một tệp có thể chứa hàng trăm nghìn ký tự, phần lớn thao tác gõ trong một khoảng thời gian ngắn chỉ tập trung vào **vùng quanh con trỏ**.

Bài toán là biểu diễn một dãy ký tự với các yêu cầu:

- Chèn ký tự hoặc chuỗi tại con trỏ.
- Xóa ký tự ngay trước/sau con trỏ.
- Di chuyển con trỏ tới một vị trí mới.
- Đọc đoạn hoặc xuất toàn bộ văn bản.
- Không phải dời toàn bộ phần đuôi sau **mỗi lần gõ**.

Một cách đơn giản là dùng **mảng động**. Nếu đang có:

```text
Văn bản:    A B C D E F G
Chỉ số:     0 1 2 3 4 5 6
Con trỏ:          ^
                 trước D, tại vị trí 3
```

và người dùng gõ `X` ở vị trí `3`, mảng thông thường phải tạo chỗ cho `X` bằng cách dịch chuyển `D,E,F,G` sang phải. Nếu tiếp tục gõ thêm `Y` ở cùng khu vực, lại phải dịch một phần đuôi khác.

**Gap buffer** giải quyết bằng cách duy trì **một khoảng ô trống liên tiếp ngay tại con trỏ**. Mỗi lần gõ chỉ cần lấp vào một phần khoảng trống; chỉ khi con trỏ di chuyển xa hoặc khoảng trống hết chỗ mới cần dời dữ liệu đáng kể.

> **Ý tưởng cốt lõi:** gom những ô chưa dùng trong một mảng thành một vùng trống liên tiếp, gọi là **gap**, và cố gắng giữ gap ở đúng vị trí người dùng đang chỉnh sửa.

Cần phân biệt về phạm vi học phần: **gap buffer không phải là một loại cây**, dù được học trong chương về các cấu trúc tăng cường và tổ chức dãy động. Nó là **cấu trúc dựa trên mảng**, rất hữu ích để so sánh với rope, cây cân bằng lưu độ dài cây con và implicit treap khi lựa chọn cách lưu văn bản. Sự khác biệt về **bất biến, thao tác và độ phức tạp** chính là điều người học cần nắm được.

## 2. Gap buffer là gì?

### 2.1. Biểu diễn vật lý và biểu diễn logic

Một gap buffer gồm:

1. Một **mảng liên tục** có `C` ô.
2. Hai mốc `gap_start` và `gap_end` xác định vùng trống nửa mở `[gap_start,gap_end)`.
3. Các ký tự thực nằm ở **bên trái** và **bên phải** vùng trống.

Ví dụ:

```text
Chỉ số vật lý:
  0   1   2   3   4   5   6   7   8   9  10  11
┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐
│ A │ B │ C │ · │ · │ · │ · │ · │ D │ E │ F │ G │
└───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘
              ↑                   ↑
        gap_start = 3         gap_end = 8

Ký hiệu · là một ô trống, KHÔNG phải ký tự của văn bản.

Dãy logic:    A B C D E F G
Con trỏ:      A B C | D E F G
                      ↑ vị trí logic 3
```

Ở đây:

- Dung lượng vật lý: `C=12` ô.
- Độ dài vùng trống: `G=8-3=5` ô.
- Độ dài văn bản logic: `n=12-5=7` ký tự.
- Con trỏ đặt trước `D`, tức ở **vị trí logic `3`**.

**Khoảng trống không xuất hiện trong văn bản.** Nó chỉ là phần dung lượng dự phòng của cấu trúc dữ liệu.

### 2.2. Bất biến cơ bản

Với mảng `buffer` dung lượng `C`:

\[
0\le gapStart\le gapEnd\le C.
\]

Độ dài gap:

\[
\boxed{gapSize=gapEnd-gapStart}.
\]

Độ dài logic:

\[
\boxed{n=C-gapSize}.
\]

Dãy ký tự thật là phép nối:

\[
\boxed{
text=buffer[0:gapStart]\mathbin{+\!\!+}buffer[gapEnd:C].
}
\]

Trong đó `+\!\!+` là phép nối dãy, không phải phép cộng số.

Bất biến lưu trữ:

- Mọi ô ở `[gapStart,gapEnd)` là **ô trống**.
- Mọi ô ngoài vùng đó chứa một đơn vị văn bản hợp lệ.
- Thứ tự văn bản logic bằng **phần trái rồi phần phải**, không có gap xen vào.
- Gap có thể có độ dài `0` khi hết chỗ; khi đó việc chèn tiếp sẽ cần tăng dung lượng.

### 2.3. Con trỏ có phải là một trường riêng không?

Trong mô hình cơ bản, vị trí con trỏ **chính là `gap_start`**. Vì trước gap có đúng `gap_start` ký tự, con trỏ đứng ngay sau phần trái.

Điều này cho phép:

- Lấy vị trí con trỏ trong **`O(1)`**.
- Backspace bằng cách mở rộng gap **sang trái**.
- Delete bằng cách mở rộng gap **sang phải**.
- Gõ chữ bằng cách lấp từ **đầu trái** của gap.

Một trình soạn thảo thực tế có thể lưu thêm **vùng chọn (selection)**, nhiều con trỏ, vị trí dòng/cột hoặc trạng thái hiển thị. Những tính năng đó là lớp giao diện/điều phối bổ sung, không làm thay đổi công thức gap buffer cơ bản.

## 3. Ánh xạ chỉ số logic sang ô vật lý

### 3.1. Văn bản có một dãy chỉ số liên tục

Dù mảng vật lý chứa một vùng trống, văn bản logic vẫn có chỉ số:

```text
Logical index:    0 1 2 3 4 5 6
Character:        A B C D E F G
```

Xét một chỉ số logic hợp lệ `i`, với `0≤i<n`.

Nếu `i<gapStart`, ký tự nằm trước gap nên chỉ số vật lý **bằng chính `i`**.

Nếu `i≥gapStart`, ký tự nằm sau gap nên phải **bỏ qua `gapSize` ô trống**:

\[
\boxed{
physical(i)=
\begin{cases}
i,&i<gapStart,\\
i+gapSize,&i\ge gapStart.
\end{cases}
}
\]

Với ví dụ ở trên, `gapStart=3` và `gapSize=5`:

| Chỉ số logic `i` | Ký tự | Chỉ số vật lý |
|---:|:---:|---:|
| 0 | A | 0 |
| 1 | B | 1 |
| 2 | C | 2 |
| 3 | D | `3+5=8` |
| 4 | E | `4+5=9` |
| 5 | F | `5+5=10` |
| 6 | G | `6+5=11` |

**Không được dùng `buffer[i]` trực tiếp cho mọi `i`**. Nếu `i` nằm ở phía sau gap, `buffer[i]` có thể là ô trống.

### 3.2. Truy cập ngẫu nhiên

Vì ánh xạ chỉ cần một phép so sánh và phép cộng, đọc **ký tự ở chỉ số logic `i`** mất **`O(1)` thời gian**, miễn là mảng vật lý hỗ trợ truy cập ô trong `O(1)`.

Đây là một lợi thế của gap buffer so với danh sách liên kết đơn: vẫn có thể đọc ký tự ở vị trí bất kỳ một cách trực tiếp mà **không phải đi qua từng nút**.

Tuy nhiên, **đọc tại vị trí xa** và **di chuyển gap tới vị trí đó để chỉnh sửa** là **hai thao tác khác nhau**:

- `char_at(i)`: đọc một ký tự, `O(1)`.
- `move_gap(i)`: đưa con trỏ tới vị trí `i`, có thể cần dời rất nhiều ký tự.

### 3.3. Đọc một đoạn văn bản

Với đoạn logic nửa mở `[l,r)`:

- Nếu toàn bộ đoạn nằm trước gap, đọc một lát mảng ở phần trái.
- Nếu toàn bộ đoạn nằm sau gap, cộng `gapSize` vào hai đầu chỉ số.
- Nếu đoạn cắt qua con trỏ, nối hai lát **trước và sau gap**.

Thời gian tạo chuỗi kết quả dài `k=r-l` là **`O(k)`**; riêng việc đọc metadata và xác định vị trí hai lát là `O(1)`.

## 4. Di chuyển gap: thao tác quan trọng nhất

### 4.1. Di chuyển gap không giống dịch chuyển con trỏ đồ họa

Trong giao diện, người dùng thấy con trỏ nhảy từ vị trí `p` tới `q`. Nhưng về cấu trúc mảng, để **đặt khoảng trống mới đúng tại `q`**, phải di chuyển những ký tự nằm **giữa hai vị trí** qua khoảng trống.

Gọi:

\[
d=|q-p|.
\]

Khi gap đang đặt tại `p` và người dùng muốn chỉnh sửa tại `q`, thao tác di chuyển gap cần **`O(d)` lần chuyển ký tự**.

Nếu `q=p`, không cần chuyển ký tự nào. Nếu `q` cách con trỏ một ký tự, chỉ cần chuyển **một ký tự**.

### 4.2. Di chuyển gap sang phải

Ban đầu:

```text
Vật lý:
[A][B][C][·][·][·][·][·][D][E][F][G]
             ↑                   ↑
             3                   8

Logic: A B C | D E F G
```

Muốn con trỏ tới vị trí `5`, tức sau `E`:

1. Chuyển `D` từ **sau gap** sang **đầu trái gap**.
2. Chuyển `E` tương tự.
3. Tăng đồng thời `gap_start` và `gap_end` thêm `2`.

Kết quả:

```text
[A][B][C][D][E][·][·][·][·][·][F][G]
                     ↑                   ↑
                     5                   10

Logic: A B C D E | F G
```

**Dãy logic không đổi**. Chỉ có vị trí gap/con trỏ thay đổi.

### 4.3. Di chuyển gap sang trái

Nếu con trỏ đang sau `E` ở vị trí `5` và muốn về trước `C` tại vị trí `2`:

- Chuyển lần lượt các ký tự ngay trước gap sang **cuối gap**.
- Giảm đồng thời `gap_start` và `gap_end` mỗi lần một đơn vị.

Kết quả logic vẫn là:

```text
A B | C D E F G
```

Không nên đảo thứ tự các ký tự trong lúc dịch. Nếu xử lý một khối dài, phải chú ý các vùng nguồn và đích **có thể chồng lấn**.

### 4.4. Mã giả dịch từng ký tự an toàn

```text
MOVE_GAP(pos):
    require 0 <= pos <= length

    if gap_start == gap_end:
        gap_start = pos
        gap_end = pos
        return

    while gap_start > pos:
        gap_start = gap_start - 1
        gap_end   = gap_end - 1
        buffer[gap_end] = buffer[gap_start]
        buffer[gap_start] = EMPTY

    while gap_start < pos:
        buffer[gap_start] = buffer[gap_end]
        buffer[gap_end] = EMPTY
        gap_start = gap_start + 1
        gap_end   = gap_end + 1
```

Ở mỗi bước, ký tự được chuyển sang phía bên kia gap rồi ô nguồn trở thành trống. Cách viết dịch **từng ô** này dễ chứng minh đúng và tránh bẫy do **sao chép hai lát mảng chồng lấn**.

**Trường hợp gap rỗng (độ dài bằng 0):** khi `gap_start=gap_end`, không có ô trống để chuyển ký tự qua. Ta có thể đổi **cả hai mốc thành `pos` ngay lập tức**, vì mảng đang chứa toàn bộ văn bản liên tục và việc dời một ranh giới có độ dài 0 không thay đổi bất kỳ ký tự nào. Khi cần chèn sau đó, hàm nới gap sẽ cấp phát một khoảng trống tại vị trí mới. Không được chạy nguyên vòng sao chép dành cho gap có độ dài dương, vì có thể tự ghi đè ký tự đang tồn tại.

### 4.5. Bẫy khi dùng slicing hoặc `memcpy`

Một hiện thực tối ưu có thể dịch **cả khối ký tự** bằng hàm sao chép bộ nhớ. Nhưng nếu vùng nguồn và đích chồng lấn, thứ tự ghi có thể ghi đè dữ liệu chưa đọc.

Ví dụ gap có độ dài `1` nhưng ta muốn chuyển gap qua một đoạn `100` ký tự: hai vùng nguồn/đích của thao tác dịch khối có thể **chồng lấn trên phần lớn độ dài**.

Vì vậy:

- Khi viết C/C++, sử dụng thao tác kiểu **`memmove`** với hỗ trợ vùng chồng lấn, thay vì giả định `memcpy` luôn an toàn.
- Khi viết Python, có thể dùng **vòng lặp dịch từng ký tự** như trong bài.
- Nếu dùng slice assignment, phải chứng minh rõ thứ tự đọc/ghi và thao tác dọn vùng trống không xóa nhầm dữ liệu vừa chuyển.

Độ phức tạp vẫn là **`O(d)`**, dù cách chuyển khối có thể giảm hệ số hằng đáng kể.

## 5. Chèn văn bản tại con trỏ

### 5.1. Chèn một ký tự

Giả sử:

```text
[A][B][C][·][·][·][·][·][D][E][F][G]
             ↑
          cursor 3
```

Người dùng gõ `X`. Ta điền `X` vào ô đầu tiên của gap, rồi tăng `gap_start`:

```text
[A][B][C][X][·][·][·][·][D][E][F][G]
                 ↑
               cursor 4

Logic: A B C X | D E F G
```

Nếu gap còn trống, **không cần dịch toàn bộ đuôi**. Một ký tự tại con trỏ được chèn bằng **`O(1)` thời gian**.

### 5.2. Chèn một chuỗi dài `k` ký tự

Nếu gap có đủ `k` ô trống:

1. Ghi `k` ký tự vào từ `gap_start`.
2. Tăng `gap_start` thêm `k`.
3. Giữ nguyên `gap_end`.

Ví dụ sau khi đã chuyển gap tới vị trí `5`:

```text
Trước:
[A][B][C][D][E][·][·][·][·][·][F][G]

Chèn "XY":
[A][B][C][D][E][X][Y][·][·][·][F][G]

Logic: A B C D E X Y | F G
```

Chi phí ghi dữ liệu là **`O(k)`**, không phụ thuộc độ dài phần đuôi `F,G`.

### 5.3. Không còn chỗ trống thì sao?

Nếu `gapSize<k`, phải **mở rộng dung lượng** trước khi chèn. Một chiến lược là cấp phát mảng mới có dung lượng đủ lớn, thường **tăng theo cấp số nhân**, rồi sao chép:

```text
Phần trái cũ  +  GAP MỚI RỘNG HƠN  +  Phần phải cũ
```

Nhờ phần trống được nới rộng ngay tại con trỏ, con trỏ vẫn giữ đúng vị trí logic.

Một lần cấp phát lại có thể tốn **`O(n+k)` thời gian** vì phải sao chép phần văn bản đang tồn tại. Nhưng nếu dùng quy tắc tăng dung lượng hình học, các lần cấp phát lại không xảy ra sau mọi lần gõ.

### 5.4. Phân biệt chi phí xấu nhất và chi phí khấu hao

Với **một ký tự** chèn ở vị trí gap:

- Nếu có chỗ: **`O(1)`**.
- Nếu phải tăng mảng: một lần có thể **`O(n)`**.

Với nhiều lần chèn liên tiếp **tại cùng khu vực**, dung lượng được nhân đôi khi cần:

\[
1+2+4+\cdots+2^j=O(2^j).
\]

Do tổng dung lượng được sao chép qua các lần nhân đôi tăng hình học, chi phí **cấp phát lại** tính khấu hao (*amortized*) trên các lần chèn có thể là **`O(1)` mỗi ký tự**.

**Điều kiện phải nêu:** kết luận này áp dụng cho chi phí thêm ký tự và tăng dung lượng theo chính sách hình học, **không bao gồm** việc con trỏ nhảy xa trước mỗi lần chèn. Nếu mỗi lần gõ lại cần chuyển gap qua `n` ký tự, tổng chi phí thao tác vẫn có thể lớn.

## 6. Backspace và Delete: mở rộng gap thay vì dồn mảng

### 6.1. Backspace — xóa ngay trước con trỏ

Tiếp tục từ trạng thái sau khi chèn `XY` vào dãy `ABCDEFG`:

```text
Văn bản logic: A B C D E X Y | F G
                             ↑ cursor 7

Vật lý trước Backspace:
[A][B][C][D][E][X][Y][·][·][·][F][G]
```

Nhấn Backspace sẽ xóa **`Y`**, ký tự nằm **ngay bên trái gap**. Ta chỉ cần:

1. Giảm `gap_start` một đơn vị.
2. Đặt ô vừa trở thành gap thành trống.

```text
Vật lý sau Backspace:
[A][B][C][D][E][X][·][·][·][·][F][G]

Văn bản logic: A B C D E X | F G
                           ↑ cursor 6
```

Nếu muốn xóa tiếp `X`, nhấn Backspace **lần thứ hai**. Không có ký tự nào ở phần đuôi `F,G` bị dịch.

Ở góc độ bất biến, quy tắc rất đơn giản:

\[
gapStart' = gapStart - 1,\qquad gapEnd' = gapEnd.
\]

Độ dài gap tăng một và độ dài văn bản giảm một.

**Backspace một ký tự** tại con trỏ tốn **`O(1)`** nếu trước con trỏ có ký tự.

### 6.2. Delete — xóa ngay sau con trỏ

Nếu muốn xóa ký tự đầu tiên **sau gap**, ta:

1. Đặt ô tại `gap_end` thành trống.
2. Tăng `gap_end` một đơn vị.

```text
Trước:
[A][B][C][D][E][X][·][·][·][·][F][G]
                                 ^
                           gap_end=10

Sau Delete:
[A][B][C][D][E][X][·][·][·][·][·][G]

Logic: A B C D E X | G
```

Tương tự Backspace, **Delete một ký tự** tại con trỏ tốn **`O(1)`**, không cần kéo toàn bộ phần đuôi về phía trước.

### 6.3. Xóa nhiều ký tự liên tiếp

Nếu muốn xóa `k` ký tự **ngay trước** con trỏ, ta mở rộng gap về trái tối đa `k` ô.

Nếu muốn xóa `k` ký tự **ngay sau** con trỏ, ta mở rộng gap về phải tối đa `k` ô.

Chi phí **`O(k')`** nếu phải dọn `k'` ô và trả lại chuỗi đã xóa; với `k'` là số ký tự thực sự tồn tại ở phía tương ứng. Không cần dời những ký tự còn lại.

### 6.4. Hành vi tại hai đầu văn bản

- Backspace tại con trỏ `0`: không có ký tự bên trái; thường là **không làm gì**.
- Delete tại con trỏ `n`: không có ký tự bên phải; thường là **không làm gì**.
- Xóa `k` lớn hơn số ký tự còn lại một phía: có thể xóa tối đa số ký tự hiện có, hoặc báo lỗi tùy API.

Trong cài đặt Python ở bài này, hai thao tác **xóa tối đa số ký tự có sẵn**, trả lại chuỗi đã xóa. Quy tắc này được công bố rõ để tránh nhập nhằng.

## 7. Thay thế vùng chọn (selection replacement)

Trình soạn thảo thường có **vùng chọn** được biểu diễn bằng đoạn chỉ số nửa mở:

\[
[start,end),\qquad 0\le start\le end\le n.
\]

Ví dụ:

```text
Văn bản: "abcdefg"
Chọn [2,5): "cde"
Gõ thay thế: "XYZ"

Kết quả: "abXYZfg"
Con trỏ: sau "XYZ", tại vị trí 5
```

Thao tác này có thể được phân rã:

1. Chuyển gap tới vị trí `start`.
2. Xóa `end-start` ký tự ngay sau gap.
3. Chèn chuỗi mới tại gap.

Nếu vị trí con trỏ cũ là `p` và chuỗi thay thế dài `k`, phần việc có:

\[
O(|p-start|+(end-start)+k)
\]

cộng chi phí cấp phát lại nếu gap chưa đủ rộng.

**Đây là điểm mạnh của gap buffer:** sửa một đoạn nhỏ **gần con trỏ** có chi phí chủ yếu theo **lượng văn bản thật sự thay đổi**. Một lần sửa xa con trỏ có thể phải trả chi phí di chuyển gap trước.

## 8. Tăng dung lượng gap: chiến lược hình học

### 8.1. Tại sao không nới thêm đúng một ô?

Nếu mỗi khi gap hết chỗ ta cấp phát mảng mới chỉ lớn hơn **một ô**, rồi sao chép toàn bộ `n` ký tự cũ, việc gõ thêm `m` ký tự có thể phải sao chép lượng dữ liệu tăng dần:

\[
n+(n+1)+(n+2)+\cdots+(n+m-1).
\]

Tổng chi phí có thể lên đến **`O(mn+m^2)`** trong tình huống bất lợi.

### 8.2. Nhân đôi dung lượng

Giải pháp phổ biến là tăng dung lượng từ `C` lên ít nhất `2C` khi cần (hoặc đủ lớn để chứa toàn bộ chuỗi chèn một lần).

Giả sử:

```text
Dung lượng cũ:  C = 12
Độ dài logic:   n = 9
Gap cũ:        G = 3
Chèn yêu cầu:  k = 5
```

Vì `G<k`, ta có thể cấp phát mảng mới dung lượng `24`, rồi bố trí:

```text
[9 ký tự logic, chia trái/phải như cũ] + gap mới
```

Cụ thể phải giữ thứ tự:

```text
left_old + (24 - 9) ô trống + right_old
```

Gốc gap vẫn nằm tại **cùng chỉ số logic trước khi tăng**.

### 8.3. Cách bố trí lại mảng

Nếu:

- Phần trái dài `L=gap_start`.
- Phần phải dài `R=C-gap_end`.
- Dung lượng mới là `C'`.

Thì:

\[
gapStart'=L,
\]

\[
gapEnd'=C'-R.
\]

Kích thước gap mới:

\[
gapSize'=C'-(L+R)=C'-n.
\]

Sao chép:

```text
new_buffer[0:L] = old_buffer[0:L]

new_buffer[gapEnd':C'] = old_buffer[gapEnd:C]
```

Những ô từ `L` đến `gapEnd'-1` được giữ trống.

**Đây là cách tăng dung lượng mà không đổi con trỏ logic hoặc thứ tự văn bản.**

### 8.4. Khi văn bản đã xóa rất nhiều thì sao?

Gap buffer có thể giữ lại dung lượng lớn sau khi người dùng xóa một lượng văn bản lớn. Điều đó giúp tránh cấp phát lại khi gõ tiếp nhưng tăng mức sử dụng bộ nhớ.

Có thể thêm thao tác **shrink/compact** theo ngưỡng, nhưng phải tránh co rồi nới liên tục (*thrashing*). Ví dụ chỉ thu nhỏ khi dung lượng đã vượt xa số ký tự đang lưu và vẫn chừa một khoảng gap tối thiểu.

Mã minh họa của bài **chỉ mở rộng, không tự thu nhỏ** để quy tắc và phân tích chi phí rõ ràng.

## 9. Python đầy đủ: GapBuffer cho chuỗi văn bản

### 9.1. Hợp đồng cài đặt

Ta viết một lớp `GapBuffer` với các lựa chọn:

- Mảng vật lý là một `list` Python.
- Mỗi ô đang chứa dữ liệu là **một phần tử chuỗi Python có độ dài `1`**.
- Mỗi ô gap chứa `None`, để dễ kiểm tra bất biến.
- Chỉ số văn bản bắt đầu từ **`0`**.
- Vị trí con trỏ thuộc `[0,n]`.
- Đoạn chọn/trích thuộc **`[start,end)`**.
- Nếu gap thiếu chỗ, dung lượng tăng hình học.
- Các hàm xóa trả lại **chuỗi ký tự đã xóa**, giữ đúng thứ tự xuất hiện.
- Thao tác chỉnh sửa không tự tạo undo history hay chức năng layout dòng.

**Lưu ý Unicode:** chuỗi Python được duyệt theo **điểm mã Unicode** (*code point*), không phải theo **cụm ký tự người dùng nhìn thấy** (*grapheme cluster*). Phần hạn chế này sẽ được phân tích ở cuối bài.

### 9.2. Khởi tạo và các bất biến cơ sở

```python
class GapBuffer:
    def __init__(self, text="", initial_gap=16):
        if not isinstance(text, str):
            raise TypeError("text phải là chuỗi")
        if type(initial_gap) is not int or initial_gap < 1:
            raise ValueError("initial_gap phải là số nguyên dương")

        # Đặt gap ở CUỐI văn bản ban đầu.
        self._cells = list(text) + [None] * initial_gap
        self._gap_start = len(text)
        self._gap_end = len(self._cells)

    @property
    def capacity(self):
        return len(self._cells)

    @property
    def gap_size(self):
        return self._gap_end - self._gap_start

    @property
    def cursor(self):
        # Số ký tự thực nằm trước gap.
        return self._gap_start

    def __len__(self):
        return self.capacity - self.gap_size

    def _check_position(self, pos):
        if type(pos) is not int:
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= pos <= len(self):
            raise IndexError("Vị trí ngoài phạm vi [0,n]")

    def _check_index(self, index):
        if type(index) is not int:
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= index < len(self):
            raise IndexError("Chỉ số ký tự ngoài phạm vi [0,n)")

    def _check_range(self, start, end):
        if type(start) is not int or type(end) is not int:
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= start <= end <= len(self):
            raise IndexError("Đoạn [start,end) không hợp lệ")

    @staticmethod
    def _check_count(count):
        if type(count) is not int or count < 0:
            raise ValueError("count phải là số nguyên không âm")
```

Khi mới khởi tạo với `text="abc"` và `initial_gap=4`:

```text
_cells     = ["a", "b", "c", None, None, None, None]
_gap_start = 3
_gap_end   = 7
cursor     = 3
len        = 7 - 4 = 3
```

Điểm quan trọng là **văn bản không được chứa `None` như dữ liệu**. `None` chỉ biểu thị một ô chưa dùng; giá trị ký tự thật đều là `str` có độ dài `1`.

### 9.3. Di chuyển gap an toàn với vùng nguồn–đích chồng lấn

Các hàm sau vẫn được định nghĩa **bên trong lớp `GapBuffer`**. Khi ghép các đoạn mã thành một chương trình, hãy đặt chúng cùng cấp thụt lề với `__len__` và các phương thức ở mục 9.2.

```python
    def move_cursor(self, pos):
        """Đưa gap tới vị trí logic pos, không đổi văn bản."""
        self._check_position(pos)

        # Gap có thể đầy (độ dài 0) sau khi chèn.
        # Khi đó đổi vị trí ranh giới mà KHÔNG sao chép ô nào.
        if self.gap_size == 0:
            self._gap_start = pos
            self._gap_end = pos
            return

        # Sang trái: chuyển ký tự ngay trước gap ra CUỐI gap.
        while self._gap_start > pos:
            self._gap_start -= 1
            self._gap_end -= 1

            self._cells[self._gap_end] = (
                self._cells[self._gap_start]
            )
            self._cells[self._gap_start] = None

        # Sang phải: chuyển ký tự ngay sau gap vào ĐẦU gap.
        while self._gap_start < pos:
            self._cells[self._gap_start] = (
                self._cells[self._gap_end]
            )
            self._cells[self._gap_end] = None

            self._gap_start += 1
            self._gap_end += 1
```

**Chú ý:** khối mã trên là **phần tiếp nối của lớp**, nên không chạy riêng ở mức top-level. Khi dùng trong tệp Python, ghép các phương thức theo đúng thứ tự trong cùng một lớp.

Sau mỗi lần lặp, gap vẫn liên tiếp và có cùng độ dài; ký tự vừa chuyển vẫn ở đúng vị trí **logic** của văn bản.

**Độ phức tạp:** thời gian `O(|pos-cursor_{\text{old}}|)`, bộ nhớ phụ `O(1)` do chỉ dùng vài biến và không tạo chuỗi trung gian.

### 9.4. Nới gap theo dung lượng hình học

```python
    def _ensure_gap(self, required):
        """Bảo đảm gap có ít nhất required ô."""
        if self.gap_size >= required:
            return

        old_capacity = self.capacity
        logical_length = len(self)

        new_capacity = max(
            8,
            2 * old_capacity,
            logical_length + required,
        )

        right_length = old_capacity - self._gap_end
        new_gap_end = new_capacity - right_length

        expanded = [None] * new_capacity
        expanded[:self._gap_start] = (
            self._cells[:self._gap_start]
        )
        expanded[new_gap_end:] = (
            self._cells[self._gap_end:]
        )

        self._cells = expanded
        self._gap_end = new_gap_end
```

Đúng theo mục 8, hàm giữ nguyên `_gap_start`, nên **vị trí con trỏ logic không đổi**. Số ký tự ở bên phải gap cũng được giữ nguyên, chỉ chuyển tới sát cuối mảng mới.

### 9.5. Chèn chuỗi tại con trỏ

```python
    def insert(self, text):
        """Chèn text tại cursor; cursor đứng sau phần vừa chèn."""
        if not isinstance(text, str):
            raise TypeError("text phải là chuỗi")
        if not text:
            return

        required = len(text)
        self._ensure_gap(required)

        end = self._gap_start + required
        self._cells[self._gap_start:end] = list(text)
        self._gap_start = end
```

Ở đây, phép slice assignment thay đúng `required` ô trống bằng đúng `required` ký tự, nên **không làm dài mảng vật lý**. Độ dài văn bản logic tăng, còn độ dài gap giảm tương ứng.

Nếu chèn chuỗi `"XYZ"` dài `3` tại con trỏ, `cursor` mới tăng đúng `3` vị trí mã Unicode theo cách đếm của Python.

### 9.6. Backspace và Delete

```python
    def backspace(self, count=1):
        """Xóa tối đa count ký tự ngay trước cursor."""
        self._check_count(count)

        actual = min(count, self._gap_start)
        start = self._gap_start - actual

        removed = "".join(
            self._cells[start:self._gap_start]
        )

        self._cells[start:self._gap_start] = [None] * actual
        self._gap_start = start

        return removed

    def delete_forward(self, count=1):
        """Xóa tối đa count ký tự ngay sau cursor."""
        self._check_count(count)

        available = self.capacity - self._gap_end
        actual = min(count, available)
        stop = self._gap_end + actual

        removed = "".join(self._cells[self._gap_end:stop])

        self._cells[self._gap_end:stop] = [None] * actual
        self._gap_end = stop

        return removed
```

Hai hàm trả phần bị xóa theo **thứ tự gốc**, không đảo chuỗi đã xóa. Điều này hữu ích khi muốn xây lệnh undo về sau.

Ví dụ `backspace(3)` xóa ba ký tự liên tiếp bên trái gap, rồi con trỏ lùi ba vị trí. `delete_forward(3)` xóa ba ký tự bên phải gap, nhưng **vị trí con trỏ logic không đổi**.

### 9.7. Thay thế vùng chọn

```python
    def replace_range(self, start, end, text):
        """Thay [start,end) bằng text; trả đoạn đã bị thay."""
        self._check_range(start, end)
        if not isinstance(text, str):
            raise TypeError("text phải là chuỗi")

        self.move_cursor(start)
        removed = self.delete_forward(end - start)
        self.insert(text)

        return removed
```

Hàm thực hiện đúng mô hình:

```text
move_gap(start)
delete_forward(end-start)
insert(text)
```

Với đoạn rỗng `start=end`, thao tác là **chèn tại vị trí đó**. Với `text=""`, thao tác là **xóa đoạn**.

### 9.8. Đọc một ký tự theo chỉ số logic

```python
    def char_at(self, index):
        self._check_index(index)

        if index < self._gap_start:
            physical = index
        else:
            physical = index + self.gap_size

        return self._cells[physical]
```

Khác `move_cursor`, hàm này **không di chuyển gap**. Nó dùng công thức ánh xạ logic–vật lý, tốn **`O(1)` thời gian và bộ nhớ phụ**.

### 9.9. Đọc đoạn và xuất toàn bộ văn bản

```python
    def substring(self, start, end):
        """Trả văn bản logic [start,end), không chuyển gap."""
        self._check_range(start, end)

        if end <= self._gap_start:
            return "".join(self._cells[start:end])

        if start >= self._gap_start:
            shift = self.gap_size
            return "".join(
                self._cells[start + shift:end + shift]
            )

        # Đoạn cắt qua gap: ghép hai lát thật.
        left_part = self._cells[start:self._gap_start]
        right_part = self._cells[
            self._gap_end:
            self._gap_end + (end - self._gap_start)
        ]
        return "".join(left_part) + "".join(right_part)

    def to_string(self):
        return (
            "".join(self._cells[:self._gap_start])
            + "".join(self._cells[self._gap_end:])
        )
```

Độ phức tạp:

- `substring(start,end)`: `O(end-start)` thời gian để tạo chuỗi.
- `to_string()`: `O(n)` thời gian và bộ nhớ cho kết quả.
- Hai hàm **không thay đổi vị trí con trỏ**.

Một ứng dụng cần lưu tệp thường gọi `to_string()` hoặc phát trực tiếp hai đoạn dữ liệu `left/right` sang hệ thống lưu trữ. **Không được ghi cả mảng vật lý** có các ô gap rỗng vào tệp.

### 9.10. Hàm kiểm tra bất biến để học và gỡ lỗi

```python
    def validate(self):
        """Duyệt toàn bộ ô để kiểm tra tính nhất quán."""
        capacity = self.capacity
        a = self._gap_start
        b = self._gap_end

        if not (0 <= a <= b <= capacity):
            return False

        if any(cell is not None for cell in self._cells[a:b]):
            return False

        outside = self._cells[:a] + self._cells[b:]
        if any(
            not isinstance(cell, str) or len(cell) != 1
            for cell in outside
        ):
            return False

        if len(outside) != len(self):
            return False
        if len(self.to_string()) != len(self):
            return False

        return True
```

Đây là **validator phục vụ tự kiểm tra**, mất `O(C)` thời gian và tạo bộ nhớ trung gian `O(n)` do phép nối hai lát. Không nên gọi sau **mỗi ký tự gõ** trong đường vận hành nếu mục tiêu là giữ thao tác cục bộ nhanh.

### 9.11. Ghép toàn bộ lớp để sử dụng

Các mục 9.2–9.10 là **một lớp `GapBuffer` duy nhất**, được tách thành nhiều code block để diễn giải từng phép toán. Khi tạo tệp Python, ghép tất cả phương thức bên dưới định nghĩa `class GapBuffer:`, bảo đảm chúng có cùng mức thụt lề, ví dụ:

```python
class GapBuffer:
    def __init__(self, text="", initial_gap=16):
        ...

    def move_cursor(self, pos):
        ...

    def _ensure_gap(self, required):
        ...

    def insert(self, text):
        ...

    # Các phương thức còn lại cùng mức thụt lề.
```

Các dấu `...` trong sơ đồ cuối chỉ minh họa cấu trúc lớp, **không thay thế định nghĩa thực tế** đã trình bày ở các mục trước.

## 10. Ví dụ sử dụng và truy vết trạng thái

### 10.1. Chèn tại vị trí bất kỳ

```python
g = GapBuffer("ABCDEFG", initial_gap=5)

print(g.to_string())     # ABCDEFG
print(len(g))            # 7
print(g.cursor)          # 7: gap đặt cuối khi khởi tạo
print(g.capacity)        # 12

g.move_cursor(3)
print(g.cursor)          # 3

g.insert("XY")
print(g.to_string())     # ABCXYDEFG
print(g.cursor)          # 5
print(len(g))            # 9
```

Chú ý: ví dụ minh họa ban đầu ở mục 2 có gap ở vị trí `3` ngay từ đầu để dễ vẽ. **Lớp Python khởi tạo gap ở cuối**, nên phải gọi `move_cursor(3)` trước khi gõ vào vị trí đó.

### 10.2. Backspace và Delete

```python
g = GapBuffer("abcdef", initial_gap=4)
g.move_cursor(3)

print(g.to_string())        # abcdef
print(g.cursor)             # 3

print(g.backspace())        # c
print(g.to_string())        # abdef
print(g.cursor)             # 2

print(g.delete_forward())   # d
print(g.to_string())        # abef
print(g.cursor)             # 2

print(g.backspace(10))      # ab
print(g.to_string())        # ef
print(g.cursor)             # 0

print(g.delete_forward(10)) # ef
print(g.to_string())        # ""
print(len(g))               # 0
```

Hàm xóa nhiều ký tự **giới hạn ở phần thực sự có** trong phạm vi tương ứng, thay vì báo lỗi khi người dùng nhấn Backspace nhiều lần ở đầu văn bản.

### 10.3. Thay thế vùng chọn

```python
g = GapBuffer("abcdefg", initial_gap=2)

removed = g.replace_range(2, 5, "XYZ")

print(removed)           # cde
print(g.to_string())     # abXYZfg
print(g.cursor)          # 5
print(g.substring(1, 6)) # bXYZf
print(g.char_at(5))      # f
assert g.validate()
```

Vì gap ban đầu chỉ có `2` ô nhưng chuỗi mới dài `3`, việc chèn có thể kích hoạt **nới gap**. Hàm vẫn phải giữ đúng phần trái/phải và chỉ số con trỏ.

### 10.4. Gõ ở cuối, đầu và giữa

```python
g = GapBuffer("", initial_gap=1)

g.insert("world")
assert g.to_string() == "world"
assert g.cursor == 5

g.move_cursor(0)
g.insert("hello ")
assert g.to_string() == "hello world"
assert g.cursor == 6

g.move_cursor(len(g))
g.insert("!")
assert g.to_string() == "hello world!"
assert g.cursor == len(g)

assert g.char_at(0) == "h"
assert g.char_at(len(g) - 1) == "!"
assert g.validate()
```

### 10.5. Kiểm tra văn bản có ký tự lặp

```python
g = GapBuffer("aaaa", initial_gap=3)
g.move_cursor(2)
g.insert("a")

assert g.to_string() == "aaaaa"
assert g.substring(1, 4) == "aaa"

g.backspace(1)
assert g.to_string() == "aaaa"
assert g.validate()
```

Gap buffer quản lý **vị trí**, không dùng giá trị ký tự làm khóa. Vì thế các ký tự trùng nhau không gây yêu cầu sắp xếp hoặc xử lý khóa trùng như BST.

## 11. Chứng minh tính đúng của các thao tác

### 11.1. Bất biến vòng lặp của `move_cursor`

Trước mỗi lần chuyển một ký tự:

- Văn bản logic là `left + right`.
- Gap là một đoạn ô trống liên tiếp.
- Vị trí con trỏ bằng độ dài phần trái.

**Khi chuyển sang phải:**

- Chuyển ký tự đầu tiên của phần phải sang **cuối phần trái**.
- Độ dài phần trái tăng một, độ dài phần phải giảm một.
- Thứ tự `left+right` không đổi.
- Gap cùng độ dài nhưng bắt đầu/kết thúc đều tăng một.

**Khi chuyển sang trái:**

- Chuyển ký tự cuối cùng của phần trái sang **đầu phần phải**.
- Độ dài phần trái giảm một, độ dài phần phải tăng một.
- Thứ tự `left+right` không đổi.
- Gap cùng độ dài nhưng hai đầu giảm một.

Do mỗi bước làm khoảng cách giữa vị trí gap và `pos` giảm một, vòng lặp dừng sau đúng:

\[
|pos-cursor_{\text{old}}|
\]

bước. Sau khi dừng, gap ở vị trí yêu cầu và văn bản logic không thay đổi.

### 11.2. Tính đúng của chèn

Giả sử gap đang ở vị trí con trỏ `p`, văn bản là:

\[
S=A+B,\qquad |A|=p.
\]

Chèn chuỗi `X` vào đầu gap và tăng `gap_start` đúng `|X|` ô:

- Phần trái mới là `A+X`.
- Phần phải vẫn là `B`.
- Văn bản mới là `A+X+B`.
- Con trỏ mới là `p+|X|`.

Nếu đã nới gap trước khi chèn, thao tác nới chỉ sao chép hai phần thật và bảo toàn thứ tự nên lập luận vẫn đúng.

### 11.3. Tính đúng của Backspace

Với `S=A+B` và con trỏ ở giữa, xóa `k` ký tự **cuối của `A`**:

- Phần đầu còn lại là `A[0:|A|-k]`.
- Phần cuối `B` không đổi.
- Gap mở rộng sang trái đúng `k` ô.
- Con trỏ lùi `k`.

Tương tự, Delete xóa `k` ký tự đầu của `B`, gap mở sang phải và vị trí con trỏ không đổi.

### 11.4. Tính đúng của thay thế đoạn

Với:

\[
S=P+M+Q,
\]

trong đó `M=S[start:end]`, thao tác `replace_range(start,end,X)`:

1. Di chuyển gap đến cuối `P`, không đổi `S`.
2. Xóa `M` ở bên phải gap, nhận `P+Q`.
3. Chèn `X` tại gap, nhận `P+X+Q`.

Đây đúng là ngữ nghĩa thay thế vùng chọn.

### 11.5. Tính đúng của phép ánh xạ chỉ số

Phần trái vật lý chứa `gap_start` ký tự, tương ứng các chỉ số logic từ `0` đến `gap_start-1`.

Phần phải vật lý bắt đầu tại `gap_end=gap_start+gap_size`, tương ứng chỉ số logic đầu tiên bằng `gap_start`.

Vì vậy, một chỉ số logic `i≥gap_start` phải dịch sang vật lý bằng:

\[
i+gapSize.
\]

Suy ra `char_at(i)` trả đúng ký tự theo cả hai trường hợp, với tiền điều kiện `0≤i<n`.

## 12. Phân tích thời gian và bộ nhớ

Gọi:

- `n`: số ký tự logic hiện có.
- `C`: dung lượng vật lý của mảng.
- `G=C-n`: số ô gap.
- `d`: khoảng cách con trỏ di chuyển.
- `k`: số ký tự được chèn/xóa/đọc.

| Thao tác | Thời gian | Bộ nhớ phụ | Điều kiện/ghi chú |
|---|---|---|---|
| Đọc độ dài `len` | `O(1)` | `O(1)` | Từ `C-(gapEnd-gapStart)` |
| Lấy vị trí con trỏ | `O(1)` | `O(1)` | `gap_start` |
| Đọc ký tự `char_at(i)` | `O(1)` | `O(1)` | Ánh xạ logic–vật lý |
| Di chuyển gap đi `d` vị trí | `O(d)` | `O(1)` | Dịch `d` ký tự |
| Chèn một ký tự tại gap còn chỗ | `O(1)` | `O(1)` | Không có realloc |
| Chèn `k` ký tự tại gap còn chỗ | `O(k)` | `O(k)` tạm thời trong code | `list(text)` tạo mảng `k` phần tử |
| Một lần nới dung lượng | `O(n+k)` | `O(C')` cấp phát mảng mới | `C'` là dung lượng mới |
| Backspace một ký tự | `O(1)` | `O(1)` | Ở sát con trỏ |
| Delete một ký tự | `O(1)` | `O(1)` | Ở sát con trỏ |
| Xóa `k` ký tự sát con trỏ | `O(k)` | `O(k)` cho chuỗi trả về | Không dời đuôi |
| Thay đoạn `[l,r)` bằng `k` ký tự | `O(d+(r-l)+k)`, chưa tính realloc | Phụ thuộc kết quả và realloc | `d=|cursor-l|` |
| Đọc chuỗi con độ dài `k` | `O(k)` | `O(k)` | Không di chuyển gap |
| Xuất toàn bộ văn bản | `O(n)` | `O(n)` | Ghép hai phần thật |
| Kiểm tra toàn bộ bất biến | `O(C)` | `O(n)` trong ví dụ | Chỉ phục vụ validation |

### 12.1. Bộ nhớ cấu trúc

Gap buffer giữ mảng `C` ô:

\[
Memory=O(C).
\]

Với chính sách nới dung lượng theo cấp số nhân và **không chủ động thu nhỏ**, `C` có thể lớn hơn `n` hiện tại sau nhiều lần xóa. Vì vậy không nên phát biểu vô điều kiện rằng bộ nhớ tại mọi thời điểm là **`\Theta(n)`**: nếu xóa gần hết văn bản, `n` nhỏ nhưng `C` vẫn lớn.

Với một chuỗi thao tác chỉ **chèn tăng dần** từ rỗng và nới theo nhân đôi, dung lượng thường được giới hạn bởi một hằng số lần độ dài đã đạt, nhưng sau xóa lớn thì mức dư thừa có thể tồn tại cho tới khi ta chủ động compact/shrink.

### 12.2. Tại sao có thao tác đọc `O(1)` nhưng thao tác sửa lại `O(n)`?

Đọc một ký tự chỉ cần biết nó nằm trước hay sau gap, nên truy cập vật lý trực tiếp.

Nhưng nếu gap đang tại `p` và muốn **gõ** ở `q`, cấu trúc phải dịch những ký tự giữa `p` và `q`. Với `|p-q|=\Theta(n)`, riêng bước di chuyển gap đã mất **`\Theta(n)` thời gian**.

**Không được suy ra** từ `char_at(i)=O(1)` rằng chèn tại chỉ số bất kỳ cũng `O(1)`.

### 12.3. Kỳ vọng, khấu hao và trường hợp xấu nhất khác nhau thế nào?

Với gap buffer:

- **Chèn tại con trỏ còn chỗ** là bảo đảm **`O(1)` worst-case** cho một ký tự.
- **Chèn tại con trỏ có thể phải nới mảng** có **`O(1)` khấu hao** theo chính sách hình học trên nhiều lần chèn đơn ký tự, nhưng một lần có thể **`O(n)`**.
- **Di chuyển con trỏ** tới nơi xa có **`O(d)` theo khoảng cách**, không phải ngẫu nhiên/kỳ vọng logarit.

Trong so sánh với **implicit treap**:

- Treap có **`O(\log n)` kỳ vọng** cho nhiều thao tác theo vị trí, dưới giả thiết priority ngẫu nhiên phù hợp.
- Gap buffer có hiệu quả tốt nhờ **tính cục bộ của hành vi chỉnh sửa**, không phải nhờ một cây cân bằng ngẫu nhiên.

**“Amortized” và “expected” không phải hai từ đồng nghĩa.** Một cái nói về phân bổ chi phí qua chuỗi thao tác, cái kia nói về kỳ vọng trên phân phối ngẫu nhiên.

## 13. Mô hình chi phí theo một chuỗi thao tác chỉnh sửa

Xét một người dùng thực hiện `m` lần chèn ký tự, có thể di chuyển con trỏ trước mỗi lần. Gọi `d_i` là quãng đường dịch gap trước lần chèn thứ `i`.

Bỏ qua chi phí cấp phát lại đã được khấu hao, tổng công việc có dạng:

\[
T=O\left(m+\sum_{i=1}^{m}d_i\right).
\]

Điều này mô tả rõ **điểm mạnh và điểm yếu** của gap buffer.

### 13.1. Gõ liên tục tại một vị trí

Nếu người dùng đặt con trỏ một lần rồi gõ `m` ký tự liên tiếp:

\[
d_1=d,\qquad d_2=\cdots=d_m=0.
\]

Chi phí tổng:

\[
O(d+m)
\]

cộng chi phí nới mảng hình học đã được khấu hao vào các lần chèn.

Nếu con trỏ ban đầu đã ở đúng vị trí, `d=0`, thì gõ liên tục gần như tuyến tính theo **số ký tự mới**, không theo độ dài văn bản cũ.

### 13.2. Chỉnh sửa luân phiên ở hai đầu văn bản

Giả sử văn bản dài khoảng `n` ký tự, và người dùng liên tục:

1. Gõ một ký tự ở **đầu**.
2. Chuyển tới **cuối** và gõ một ký tự.
3. Quay lại **đầu**.

Mỗi lần nhảy có thể khiến gap phải dịch **`\Theta(n)` ký tự**. Với `m` lần chỉnh sửa như vậy:

\[
T=\Theta(mn)
\]

khi độ dài xấp xỉ `n` trong giai đoạn xét.

**Gap buffer không phù hợp bằng một số cấu trúc cây** nếu các thao tác nhỏ liên tục phân tán xa nhau trên văn bản rất lớn.

### 13.3. Điểm cục bộ theo thời gian

Một trình soạn thảo thường có các “đợt chỉnh sửa”:

```text
Di chuyển con trỏ một lần (có thể xa)
   ↓
Gõ nhiều ký tự
   ↓
Backspace vài lần
   ↓
Thay một đoạn nhỏ
   ↓
Di chuyển sang vị trí khác
```

Trong một đợt, gap đã ở đúng khu vực thao tác nên nhiều phép sửa liên tiếp rẻ. Mô hình này lý giải vì sao gap buffer là một lựa chọn thực dụng cho **chỉnh sửa văn bản cục bộ**.

## 14. So sánh gap buffer với mảng, danh sách liên kết, rope và treap

### 14.1. Bảng tổng hợp

| Cấu trúc | Truy cập ký tự thứ `i` | Chèn/xóa cục bộ | Chỉnh sửa tại vị trí xa | Đặc điểm |
|---|---|---|---|---|
| Mảng động / string builder | Thường `O(1)` | Ở giữa thường `O(n)` do dời đuôi | Thường `O(n)` mỗi sửa ở giữa | Đơn giản, bộ nhớ liên tục |
| Danh sách liên kết | `O(n)` từ đầu | `O(1)` nếu đã có nút/vị trí | Tìm vị trí `O(n)` | Chi phí con trỏ cao |
| **Gap buffer** | **`O(1)`** | **`O(1)` một ký tự** nếu gap ở ngay đó và còn chỗ | **`O(d)`** để di chuyển gap | Mạnh với chỉnh sửa tập trung quanh con trỏ |
| Rope cân bằng | Thường `O(\log n)` để định vị | Theo cấu trúc và độ lớn khối | Thường phù hợp hơn cho nhiều đoạn xa nhau | Cây lưu các khối chuỗi và độ dài |
| Implicit treap | `O(\log n)` **kỳ vọng** | `O(\log n)` kỳ vọng | `O(\log n)` kỳ vọng | Cây theo vị trí, hỗ trợ split/merge |
| Piece table | Phụ thuộc chỉ mục và hiện thực | Có thể chèn bằng tham chiếu tới vùng bổ sung | Phụ thuộc quản lý các đoạn và chỉ mục | Giữ văn bản gốc + vùng thêm, phù hợp undo |

**Các độ phức tạp của rope và piece table phụ thuộc thiết kế cụ thể**: loại cây cân bằng, kích thước lá, cách quản lý đoạn, bộ chỉ mục và cơ chế cập nhật. Không nên gán một bảo đảm Big-O duy nhất cho mọi hiện thực.

### 14.2. Tại sao gap buffer không phải một treap?

Gap buffer:

- Lưu các ký tự trong **một mảng liên tiếp**.
- Có **một gap liên tiếp** được định vị bằng hai chỉ số.
- Di chuyển con trỏ bằng **dịch ký tự**.
- Không có nút cha/con, priority, phép xoay hay split–merge trên cây.

Implicit treap:

- Lưu mỗi phần tử trong một nút cây.
- Vị trí được suy ra từ **size của cây con**.
- Tách và ghép bằng tái liên kết các cây con.
- Thao tác theo đường cây có **`O(\log n)` kỳ vọng** trong mô hình ngẫu nhiên chuẩn.

Hai cấu trúc đều hỗ trợ **chỉnh sửa dãy**, nhưng bất biến và cách trả chi phí hoàn toàn khác nhau.

### 14.3. Khi nào gap buffer là lựa chọn phù hợp?

Cân nhắc gap buffer nếu:

- Người dùng chủ yếu gõ và xóa **gần một con trỏ**.
- Cần truy cập ký tự ngẫu nhiên tương đối đơn giản.
- Dữ liệu có thể lưu trong một mảng đủ lớn.
- Muốn code lõi gọn hơn một cấu trúc cây cân bằng phức tạp.
- Không có quá nhiều thao tác chỉnh sửa đồng thời ở những vị trí xa nhau.

### 14.4. Khi nào nên cân nhắc rope hoặc treap?

Nếu tài liệu lớn và thường xuyên:

- Cắt–dán những đoạn dài.
- Đảo một đoạn.
- Chỉnh sửa xen kẽ ở các vị trí rất xa.
- Quản lý nhiều con trỏ hoặc nhiều vùng sửa độc lập.
- Cần chia sẻ phiên bản hoặc các thao tác bền vững (*persistent*).

thì cấu trúc dạng cây lưu độ dài/khối văn bản có thể thuận lợi hơn. Tuy nhiên, cây có chi phí nút, con trỏ và thuật toán bảo trì lớn hơn.

**Không có một cấu trúc tối ưu cho mọi mẫu tương tác.** Hãy lựa chọn dựa trên phân bố vị trí sửa và loại thao tác thực tế.

## 15. Unicode, ký tự hiển thị và giới hạn của chỉ số

### 15.1. Một ký tự người dùng nhìn thấy không nhất thiết là một code point

Ví dụ chuỗi Unicode có thể chứa một ký tự cơ sở và dấu kết hợp:

```python
text = "e\u0301"
print(len(text))  # 2 code point trong Python
```

Trên màn hình, `e` và dấu sắc kết hợp có thể hiển thị như **một cụm ký tự**. Nhưng `list(text)` tạo hai phần tử:

```text
["e", "\u0301"]
```

Nếu con trỏ đặt giữa hai code point này, người dùng có thể thấy một hành vi chỉnh sửa không mong muốn.

Tương tự, một số emoji chứa nhiều code point được ghép bằng ký tự nối. **Backspace một code point** không nhất thiết tương đương **xóa một ký tự hiển thị**.

### 15.2. Đơn vị chỉ số phải được công bố

Một trình soạn thảo có thể định nghĩa chỉ số theo:

- Byte của chuỗi UTF-8.
- Code point Unicode.
- Code unit UTF-16.
- Grapheme cluster (cụm ký tự hiển thị).
- Vị trí dòng/cột hoặc vị trí trực quan trên màn hình.

Mỗi quy ước có tác động khác nhau tới việc di chuyển con trỏ, xóa, chọn và ánh xạ vị trí.

**Code Python trong bài chỉ hỗ trợ chính xác ngữ nghĩa theo code point**. Đây là lựa chọn để học cấu trúc, không phải một hệ thống biên tập Unicode hoàn chỉnh.

### 15.3. Muốn hỗ trợ grapheme cluster cần thêm gì?

Một trình soạn thảo hướng tới người dùng cuối nên:

1. Dùng bộ phân đoạn grapheme phù hợp với chuẩn Unicode.
2. Không cho con trỏ dừng giữa các code point thuộc cùng một grapheme cluster, trừ khi có lý do rõ ràng.
3. Định nghĩa Backspace/Delete theo **cụm ký tự** hoặc theo chính sách editor.
4. Đồng bộ chỉ số văn bản logic với layout, dòng/cột và thao tác chuột.
5. Xử lý đúng việc Unicode có thể thay đổi cách phân đoạn khi các code point được chèn cạnh nhau.

Nếu các ô gap buffer được thiết kế theo byte hoặc code unit, cần một **lớp ánh xạ** để chuyển từ vị trí người dùng nhìn thấy sang vị trí lưu trữ.

### 15.4. Xuống dòng và cặp CRLF

Một số tệp sử dụng `"\r\n"` để xuống dòng. Nếu coi `"\r"` và `"\n"` là hai phần tử riêng:

- Di chuyển con trỏ qua mỗi phần tử có thể dẫn tới trạng thái nằm giữa cặp CRLF.
- Xóa một trong hai phần tử có thể thay đổi quy ước kết thúc dòng.
- Chỉ số dòng/cột và cách hiển thị cần một lớp xử lý riêng.

Gap buffer quản lý **dãy đơn vị dữ liệu**; nó không tự hiểu “dòng văn bản” hay “đoạn văn”.

## 16. Những phần một trình soạn thảo thật còn cần

### 16.1. Undo/redo

Gap buffer chỉ lưu **trạng thái hiện tại** của văn bản. Nó **không tự ghi lại lịch sử**.

Muốn undo/redo, ứng dụng có thể lưu các lệnh:

```text
Insert(position, text)
Delete(position, removed_text)
Replace(start, old_text, new_text)
```

Khi hoàn tác một lệnh, áp dụng phép biến đổi ngược vào gap buffer. Có thể gộp nhiều ký tự gõ liên tiếp thành một hành động để tránh tạo quá nhiều mục lịch sử.

**Không nên lưu ảnh chụp toàn bộ văn bản sau mỗi lần gõ** nếu tài liệu lớn, vì có thể tốn bộ nhớ rất nhiều. Việc thiết kế undo là một bài toán riêng.

### 16.2. Tìm kiếm và thay thế nhiều kết quả

Gap buffer giúp sửa tốt gần con trỏ, nhưng **không tự tạo chỉ mục tìm kiếm chuỗi**. Tìm một mẫu văn bản tổng quát vẫn cần thuật toán tìm kiếm thích hợp trên chuỗi logic, hoặc một chỉ mục được duy trì riêng.

Nếu thay thế nhiều vị trí xa nhau, việc dịch gap đi lại có thể tốn kém. Một chiến lược khác là thực hiện các sửa đổi theo **thứ tự vị trí** để giảm quãng đường di chuyển, đồng thời điều chỉnh chỉ số sau các phép thay thế.

### 16.3. Nhiều con trỏ và cộng tác đồng thời

Một gap buffer đơn có **một vùng trống**, nên tối ưu cho **một con trỏ đang hoạt động**. Nếu có nhiều con trỏ ở các khu vực khác nhau:

- Các thao tác xen kẽ có thể liên tục di chuyển gap xa.
- Có thể dùng nhiều gap, các khối/chunk hoặc cấu trúc cây.
- Chỉnh sửa cộng tác còn cần cơ chế thống nhất thứ tự thao tác (ví dụ các thuật toán OT/CRDT tùy hệ thống), không thể chỉ dựa vào cấu trúc mảng.

**Gap buffer giải quyết chi phí lưu trữ và sửa cục bộ**, không giải quyết tự động bài toán hợp nhất chỉnh sửa từ nhiều người dùng.

### 16.4. Đọc/ghi tệp và lưu bền

Khi đọc tệp, có thể:

1. Giải mã byte thành văn bản theo mã hóa được chọn.
2. Tạo gap buffer với nội dung logic đã giải mã.
3. Đặt gap tại vị trí con trỏ mong muốn.

Khi lưu:

1. Lấy phần trái và phần phải của văn bản.
2. Ghép hoặc ghi nối hai phần theo đúng thứ tự.
3. Mã hóa lại thành byte phù hợp và ghi tệp an toàn.

Việc ghi tệp có thể cần tệp tạm, flush, rename nguyên tử hoặc cơ chế phục hồi lỗi. **Mã trong bài không làm I/O**, vì mục tiêu chính là bất biến và thao tác của gap buffer.

## 17. Tình huống biên và cách kiểm thử có hệ thống

### 17.1. Các trường hợp biên bắt buộc

| Tình huống | Hành vi mong đợi |
|---|---|
| Văn bản rỗng | `len=0`, `cursor=0` |
| Con trỏ ở đầu | Backspace không xóa gì |
| Con trỏ ở cuối | Delete không xóa gì |
| Gap hết chỗ | Nới mảng rồi chèn đúng |
| Gap nằm giữa văn bản | Truy cập ký tự phải bỏ qua vùng trống |
| Chèn chuỗi rỗng | Không thay đổi |
| Xóa số lượng `0` | Không thay đổi |
| Chọn đoạn `[i,i)` | Thay thế bằng chuỗi tương đương chèn |
| Chọn cả văn bản `[0,n)` | Thay thế hoặc xóa toàn bộ |
| Nhiều ký tự giống nhau | Vẫn giữ đúng số lượng và vị trí |
| Con trỏ nhảy xa qua gap nhỏ | Không mất/đảo ký tự |
| Di chuyển từ đầu tới cuối rồi quay lại | Văn bản logic giữ nguyên |
| Chèn sau một chuỗi xóa lớn | Tận dụng gap lớn |
| Chỉ số âm hoặc quá `n` | Báo lỗi rõ ràng |
| Dấu kết hợp Unicode | Chỉ số theo code point, cần lớp grapheme khi làm editor thật |

### 17.2. Đối chiếu với một chuỗi tham chiếu đơn giản

Có thể tự kiểm tra bằng cách duy trì một chuỗi Python `reference` cùng với gap buffer:

```python
g = GapBuffer("abcdef", initial_gap=1)
reference = "abcdef"

g.move_cursor(2)
g.insert("XYZ")
reference = reference[:2] + "XYZ" + reference[2:]

assert g.to_string() == reference
assert g.validate()

removed = g.replace_range(1, 4, "Q")
reference = reference[:1] + "Q" + reference[4:]

assert removed == "bXY"
assert g.to_string() == reference
assert g.validate()
```

Khi kiểm thử lớn hơn, có thể tạo nhiều chuỗi thao tác và so sánh sau mỗi bước:

```text
Reference model:
    một chuỗi/list thông thường, dễ hiểu nhưng có thể chậm

GapBuffer:
    cấu trúc đang cần kiểm chứng

Với mỗi thao tác:
    áp dụng vào cả hai theo cùng hợp đồng chỉ số
    kiểm tra hai văn bản cuối bằng nhau
    kiểm tra cursor đúng
    kiểm tra validate()
```

**Đây là một phương pháp học và tự kiểm tra**, không phải xác nhận đã chạy bộ kiểm thử trong quy trình biên soạn.

### 17.3. Truy vết dịch qua gap chỉ một ô

Một trường hợp dễ làm lộ lỗi sao chép chồng lấn là gap có đúng **một ô**:

```text
Vật lý: [A][B][C][·][D][E][F]
                   ^
                gap 1 ô

Di chuyển con trỏ từ vị trí 3 sang 6:

Sau 1 bước: [A][B][C][D][·][E][F]
Sau 2 bước: [A][B][C][D][E][·][F]
Sau 3 bước: [A][B][C][D][E][F][·]

Logic sau mọi bước: ABCDEF
```

Chú ý gap không thay đổi độ dài; chỉ chuyển dịch vị trí. Nếu mã dùng các phép slice rồi **dọn vùng nguồn không đúng thứ tự**, có thể xóa nhầm một ký tự khi hai vùng chồng lấn.

### 17.4. Tính đúng quan trọng hơn vẻ ngoài của mảng vật lý

Một validator tốt cần phân biệt hai cấp:

- **Bất biến vật lý:** gap là một vùng liên tiếp, mọi ô trong đó trống, không có ô trống ngoài gap.
- **Bất biến ngữ nghĩa:** chuỗi logic thu được bằng cách nối phần trái/phải đúng bằng kết quả mong đợi của mọi thao tác.

Chỉ kiểm tra rằng `gap_start≤gap_end` là **không đủ**. Mảng có thể mất một ký tự khi di chuyển nhưng vẫn giữ hai chỉ số hợp lệ.

## 18. Những sai lầm thường gặp

1. **Ghi gap thành các ký tự khoảng trắng thật.** Gap là **ô chưa dùng**, không phải dấu cách người dùng đã gõ.
2. **Nhầm dung lượng vật lý với độ dài văn bản.** `len=C-(gapEnd-gapStart)`, không phải `C`.
3. **Nhầm `gap_start` với chỉ số vật lý của ký tự phía sau con trỏ.** Ký tự đầu tiên phía sau gap nằm tại `gap_end`.
4. **Đọc `buffer[i]` mà không ánh xạ qua gap.** Những chỉ số logic sau con trỏ phải cộng `gapSize`.
5. **Cho rằng truy cập ngẫu nhiên `O(1)` kéo theo chèn tại vị trí bất kỳ `O(1)`.** Cần tính chi phí dịch gap.
6. **Di chuyển con trỏ đồ họa nhưng không di chuyển gap trước khi gõ.** Sửa sẽ xảy ra sai vị trí logic.
7. **Dịch gap sang trái/phải sai thứ tự sao chép.** Có thể đảo hoặc mất ký tự.
8. **Dùng phép copy không hỗ trợ vùng chồng lấn.** Gap nhỏ và quãng dịch dài là trường hợp dễ hỏng.
9. **Dịch gap nhưng không cập nhật đồng thời hai đầu.** Độ dài gap sẽ bị sai.
10. **Chèn thêm ký tự bằng thao tác làm dài list vật lý ngay giữa gap.** Có thể làm sai công thức dung lượng và vị trí gap.
11. **Tăng `gap_start` mà không thực sự ghi ký tự vào ô vừa lấp.** Văn bản logic có thể chứa `None`.
12. **Chèn khi gap không đủ dung lượng.** Có thể ghi đè phần văn bản bên phải.
13. **Nới mảng nhưng đặt lại phần phải ở chỉ số sai.** Có thể làm lẫn các ô gap với ký tự thật.
14. **Nới thêm một ô mỗi lần và vẫn kết luận chèn khấu hao `O(1)`.** Chi phí sao chép có thể là bậc hai theo số lần chèn.
15. **Backspace giảm `gap_end` thay vì `gap_start`.** Backspace phải xóa ký tự **bên trái** con trỏ.
16. **Delete tăng `gap_start` thay vì `gap_end`.** Delete phải xóa ký tự **bên phải** con trỏ.
17. **Xóa ở đầu/cuối nhưng không kiểm tra còn ký tự hợp lệ.** Có thể truy cập ngoài phạm vi.
18. **Đếm độ dài xóa sai khi `count` lớn hơn phần có sẵn.** Phải xác định hợp đồng giới hạn hay báo lỗi.
19. **Thay vùng chọn nhưng quên di chuyển gap tới đầu vùng.** Sẽ xóa sai nội dung.
20. **Nhầm đoạn nửa mở `[start,end)` với đoạn đóng.** Xóa `end-start` ký tự, không phải `end-start+1`.
21. **Xuất cả mảng vật lý để lưu tệp.** Các ô gap không thuộc văn bản thật.
22. **Cho rằng di chuyển gap là `O(1)` vì chỉ sửa hai chỉ số.** Còn phải di chuyển `d` ký tự.
23. **Tính nhầm khấu hao của nới mảng thành bảo đảm worst-case.** Một lần cấp phát lại vẫn có thể `O(n)`.
24. **Bỏ qua chi phí dịch gap khi phân tích một chuỗi thao tác.** Các lần nhảy xa có thể chi phối tổng thời gian.
25. **Tuyên bố bộ nhớ luôn `O(n)` theo độ dài hiện tại sau khi đã xóa phần lớn văn bản.** Dung lượng cũ có thể vẫn được giữ lại.
26. **Coi một code point Unicode luôn là một ký tự hiển thị.** Dấu kết hợp và emoji có thể gồm nhiều code point.
27. **Cho Backspace một code point nhưng giao diện lại cam kết xóa một grapheme.** Cần lớp phân đoạn Unicode.
28. **Quên xử lý CRLF, dòng/cột và tab trong editor thật.** Gap buffer chỉ lưu dãy, không tự xử lý layout.
29. **Cho rằng gap buffer tự cung cấp undo/redo.** Cần lịch sử lệnh hoặc cơ chế phiên bản.
30. **Cho rằng gap buffer phù hợp cho mọi mô hình nhiều con trỏ.** Một gap đơn có thể bị dịch xa liên tục.
31. **Dùng gap buffer như một cây cân bằng hoặc mô tả nó có phép xoay.** Nó là mảng với vùng trống liên tiếp, không phải AVL/treap.
32. **Kiểm tra chỉ số nhưng không kiểm tra nội dung gap.** Có thể mất dữ liệu mà hai mốc vẫn hợp lệ.
33. **Gọi validator `O(C)` sau từng lần gõ rồi tuyên bố thao tác chỉ `O(1)`.** Hãy tách đường vận hành khỏi kiểm thử.
34. **Không xác định kiểu dữ liệu ô gap.** Trong bài, `None` chỉ dùng cho ô trống, ký tự thật là `str` độ dài `1`.
35. **Dùng đầu vào `bool` cho chỉ số mà không chú ý `bool` là lớp con của `int` trong Python.** Nếu API muốn chỉ số nguyên thật, kiểm tra `type(x) is int`.
36. **Giữ mảng ở dung lượng lớn mãi mà không có chính sách tài nguyên.** Một editor thật có thể cần compact theo ngưỡng hoặc chuyển sang cấu trúc khác khi tài liệu lớn.

## 19. Bài tập thực hành có đáp án

### Bài 1. Xác định văn bản logic

Cho mảng:

```text
[A][B][·][·][·][C][D]
gap_start=2
gap_end=5
```

Văn bản logic là gì, con trỏ ở đâu?

**Đáp án:** Văn bản **`"ABCD"`**. Con trỏ ở vị trí logic **`2`**, giữa `B` và `C`.

### Bài 2. Tính độ dài và dung lượng

Mảng có `C=30` ô, gap là `[12,20)`. Độ dài gap và độ dài văn bản?

**Đáp án:** `gapSize=20-12=8`, độ dài logic `n=30-8=22`.

### Bài 3. Ánh xạ chỉ số

Với `gap_start=3`, `gap_end=8`, chỉ số logic `i=5` tương ứng vật lý bao nhiêu?

**Đáp án:** `gapSize=5`, vì `5≥3` nên `physical(5)=5+5=10`.

### Bài 4. Chỉ số trước gap

Cũng trạng thái Bài 3, chỉ số logic `i=1` nằm ở ô vật lý nào?

**Đáp án:** Ô vật lý **`1`**, vì `1<gap_start=3`.

### Bài 5. Di chuyển gap sang phải

Văn bản `"ABCDEFG"`, gap đang ở vị trí `3`. Chuyển tới vị trí `5` cần dịch bao nhiêu ký tự?

**Đáp án:** **Hai ký tự `D,E`** từ bên phải gap sang bên trái gap. Văn bản logic vẫn là `"ABCDEFG"`.

### Bài 6. Di chuyển gap sang trái

Văn bản `"ABCDEFG"`, gap ở vị trí `5`. Chuyển tới vị trí `2` cần dịch bao nhiêu ký tự?

**Đáp án:** **Ba ký tự `C,D,E`** từ trước gap sang sau gap, giữ thứ tự văn bản logic.

### Bài 7. Chèn một ký tự

Văn bản `"abcde"`, con trỏ trước `c` ở vị trí `2`, gap còn chỗ. Gõ `X`. Văn bản và con trỏ mới?

**Đáp án:** Văn bản **`"abXcde"`**, con trỏ ở vị trí **`3`**.

### Bài 8. Chèn chuỗi

Văn bản `"abcd"`, con trỏ ở vị trí `2`, chèn `"XYZ"`. Kết quả?

**Đáp án:** **`"abXYZcd"`**, con trỏ ở vị trí `5`.

### Bài 9. Backspace

Văn bản `"abXYZcd"`, con trỏ ở vị trí `5`. Backspace một lần trả ký tự gì và kết quả gì?

**Đáp án:** Trả **`"Z"`**, văn bản thành **`"abXYcd"`**, con trỏ lùi về **`4`**.

### Bài 10. Delete

Văn bản `"abcdef"`, con trỏ ở vị trí `3`. Delete một lần xóa ký tự gì?

**Đáp án:** Xóa **`"d"`**, văn bản thành **`"abcef"`**, con trỏ vẫn ở vị trí **`3`**.

### Bài 11. Backspace ở đầu

Văn bản `"abc"`, con trỏ ở vị trí `0`. Theo API của bài, Backspace trả gì?

**Đáp án:** Trả chuỗi rỗng **`""`** và không thay đổi văn bản hoặc con trỏ.

### Bài 12. Delete ở cuối

Văn bản `"abc"`, con trỏ ở vị trí `3`. Delete trả gì?

**Đáp án:** Trả **`""`** và không thay đổi văn bản.

### Bài 13. Thay vùng chọn

Văn bản `"abcdefg"`, thay `[2,5)` bằng `"XYZ"`. Kết quả và đoạn bị xóa?

**Đáp án:** Kết quả **`"abXYZfg"`**, đoạn bị xóa **`"cde"`**, con trỏ sau `XYZ` tại vị trí **`5`**.

### Bài 14. Xóa toàn bộ văn bản

Văn bản `"hello"`, thay `[0,5)` bằng `""`. Độ dài mới bằng bao nhiêu?

**Đáp án:** **`0`**. Gap có thể chiếm toàn bộ dung lượng vật lý đã cấp phát; không nhất thiết phải giải phóng mảng.

### Bài 15. Chèn chuỗi rỗng

Gọi `insert("")` khi con trỏ ở giữa văn bản. Điều gì thay đổi?

**Đáp án:** **Không có gì thay đổi**. Không phải chuyển gap hay nới dung lượng.

### Bài 16. Chi phí đọc một ký tự

Tại sao `char_at(i)` có thể là `O(1)` dù gap nằm giữa mảng?

**Đáp án:** Vì chỉ cần kiểm tra `i<gap_start` hay không, rồi đọc vật lý ở `i` hoặc `i+gapSize`; không cần dịch gap.

### Bài 17. Chi phí di chuyển xa

Tài liệu dài `n`, con trỏ đang ở đầu và người dùng muốn chỉnh sửa ở cuối. Di chuyển gap có thể mất bao nhiêu?

**Đáp án:** **`O(n)`**, vì phải chuyển khoảng `n` ký tự qua gap.

### Bài 18. Khấu hao khi chèn

Vì sao chính sách **nhân đôi dung lượng** có thể làm chi phí cấp phát lại khấu hao nhỏ khi gõ liên tục?

**Đáp án:** Các lần cấp phát lại cách nhau theo dung lượng tăng hình học. Tổng số ô phải sao chép qua các lần nới được chặn bởi một cấp số nhân có tổng cùng bậc với dung lượng cuối, nên phân bổ trên nhiều lần chèn cho **`O(1)` chi phí khấu hao mỗi ký tự** (chưa tính dịch gap).

### Bài 19. Nới thêm từng ô

Nếu mỗi khi gap hết chỗ chỉ tăng dung lượng đúng một ô và sao chép toàn bộ dữ liệu, vấn đề là gì?

**Đáp án:** Phải sao chép gần như toàn bộ văn bản **sau mỗi ký tự**, có thể tạo tổng chi phí bậc hai theo số lần chèn từ dữ liệu nhỏ.

### Bài 20. Chi phí sửa một đoạn

Con trỏ đang ở `p=100`, cần thay đoạn `[110,115)` bằng chuỗi dài `3`. Không tính realloc, độ lớn chi phí theo bài là gì?

**Đáp án:** Di chuyển gap `10` ký tự, xóa `5` ký tự và chèn `3` ký tự; tổng **`O(10+5+3)=O(18)`** thao tác ký tự.

### Bài 21. Tính đúng khi gap có một ô

Tại sao di chuyển gap dài bằng cách sao chép hai lát không được giả định vùng nguồn và đích không chồng lấn?

**Đáp án:** Gap có thể chỉ rộng **một ô** trong khi phải chuyển hàng trăm ký tự. Nguồn và đích khi dịch khối có thể chồng lấn mạnh; cần thứ tự sao chép đúng hoặc thao tác tương đương `memmove`.

### Bài 22. Bộ nhớ sau xóa lớn

Văn bản từng có một triệu ký tự nhưng sau đó bị xóa còn mười ký tự, mảng không thu nhỏ. Có thể khẳng định bộ nhớ hiện tại là `O(10)` không?

**Đáp án:** **Không.** Bộ nhớ thực phụ thuộc **dung lượng `C` vẫn giữ lại**, có thể lớn dù `n=10`. Nếu cần, phải có chiến lược compact/shrink.

### Bài 23. Khi nào mảng thường đủ tốt?

Tài liệu nhỏ, chỉ được đọc nhiều và hiếm khi chèn ở giữa. Có nhất thiết dùng gap buffer không?

**Đáp án:** **Không.** Mảng/chuỗi đơn giản có thể dễ triển khai và có hiệu năng thực tế tốt hơn khi ít sửa.

### Bài 24. Nhiều vị trí chỉnh sửa xa

Một ứng dụng luân phiên gõ ở đầu và cuối tài liệu lớn. Gap buffer có thể gặp bất lợi gì?

**Đáp án:** Phải dịch gap gần như toàn bộ văn bản **mỗi lần đổi đầu**, khiến chi phí có thể là **`\Theta(n)` mỗi lần**. Rope hoặc cây theo vị trí là lựa chọn đáng cân nhắc.

### Bài 25. Gap buffer và implicit treap

Sự khác biệt cốt lõi về biểu diễn thứ tự của hai cấu trúc là gì?

**Đáp án:** Gap buffer lưu hai đoạn ký tự thật trong **một mảng với vùng trống liên tiếp**. Implicit treap lưu dãy theo **thứ tự inorder của cây**, suy vị trí từ `size` cây con và thao tác split–merge.

### Bài 26. Unicode và Backspace

Chuỗi Python `"e\u0301"` có `len=2`. Vì sao một Backspace theo code point có thể không tương ứng với việc xóa một ký tự hiển thị?

**Đáp án:** `"e"` và dấu sắc kết hợp tạo thành một **grapheme cluster** khi hiển thị. Xóa một code point có thể chỉ xóa dấu sắc hoặc ký tự cơ sở, làm thay đổi cụm ký tự theo cách người dùng không mong đợi.

### Bài 27. CRLF

Một editor lưu `"\r\n"` thành hai code point. Cần lưu ý gì về con trỏ?

**Đáp án:** Có thể phải **tránh đặt con trỏ giữa `\r` và `\n`** hoặc có một lớp quy ước xuống dòng để Backspace/Delete không phá cặp CRLF ngoài ý muốn.

### Bài 28. Undo/redo

Gap buffer có tự lưu được lịch sử chỉnh sửa không? Nếu không, cần bổ sung gì?

**Đáp án:** **Không.** Có thể bổ sung lịch sử lệnh chèn/xóa/thay thế với vị trí và nội dung cũ/mới, hoặc một cơ chế phiên bản khác.

### Bài 29. Lưu văn bản xuống tệp

Tại sao không được ghi nguyên mảng vật lý có `None` ra tệp?

**Đáp án:** Vì ô gap **không phải dữ liệu văn bản**. Phải xuất đúng **phần bên trái nối phần bên phải**, bỏ hoàn toàn khoảng trống.

### Bài 30. Validator có đủ không?

Một hàm kiểm tra `0≤gap_start≤gap_end≤C` có đủ chứng minh gap buffer đã giữ đúng văn bản sau khi di chuyển không?

**Đáp án:** **Chưa.** Đây chỉ là điều kiện về hai chỉ số. Còn phải kiểm tra ô gap rỗng, ô ngoài gap chứa dữ liệu hợp lệ và **chuỗi logic đúng bằng kết quả mong đợi**.

### Bài 31. Tổng chi phí nhiều lần nhảy

Có `m` lần gõ, lần thứ `i` cần dịch gap `d_i` ký tự. Bỏ qua cấp phát lại đã khấu hao, viết một chặn trên thời gian theo `m` và `d_i`.

**Đáp án:**

\[
O\left(m+\sum_{i=1}^{m}d_i\right).
\]

Nếu mọi `d_i=0`, việc gõ liên tục rẻ. Nếu mọi `d_i=\Theta(n)`, chi phí có thể tăng thành `\Theta(mn)`.

### Bài 32. Thiết kế một editor văn bản thật

Ngoài gap buffer, nêu ít nhất ba chức năng một editor cần để hỗ trợ tốt người dùng cuối.

**Đáp án:** Ví dụ: **phân đoạn grapheme Unicode**, **chỉ số dòng/cột và layout**, **undo/redo**, **tìm kiếm**, **quản lý vùng chọn/nhiều con trỏ**, **lưu tệp có xử lý lỗi** hoặc **đồng bộ chỉnh sửa**. Gap buffer chỉ xử lý lưu trữ và sửa dãy cục bộ.

## 20. Tổng kết

**Gap buffer** là một mảng văn bản có **một vùng ô trống liên tiếp** đặt tại con trỏ. Cấu trúc được mô tả bằng:

\[
\boxed{
0\le gapStart\le gapEnd\le C,
\qquad n=C-(gapEnd-gapStart).
}
\]

Văn bản logic là phần **trước gap** nối với phần **sau gap**; ký tự ở chỉ số logic `i` được ánh xạ sang vật lý bằng `i` nếu nằm trước gap, hoặc `i+gapSize` nếu nằm sau gap.

- **Chèn/Backspace/Delete gần con trỏ** rất nhanh khi gap còn chỗ: một ký tự thường là **`O(1)`**.
- **Di chuyển gap `d` vị trí** phải chuyển `d` ký tự: **`O(d)`**.
- **Nới mảng theo cấp số nhân** giúp chi phí cấp phát lại được **khấu hao**, nhưng một lần nới vẫn có thể tốn `O(n)`.
- **Truy cập ký tự theo chỉ số** là **`O(1)`**, còn xuất toàn bộ văn bản là **`O(n)`**.
- **Bộ nhớ** phụ thuộc dung lượng mảng đã cấp phát, không chỉ số ký tự hiện tại.
- Đối với Unicode và editor thực tế, cần thêm lớp xử lý grapheme, xuống dòng, vùng chọn, undo/redo và I/O.

Điểm mạnh của gap buffer đến từ **tính cục bộ của thao tác chỉnh sửa**, không phải từ tính cân bằng của cây. Đây là một **cấu trúc dựa trên mảng**, khác với rope hay implicit treap: khi thao tác tập trung quanh một con trỏ, gap buffer đơn giản và hiệu quả; khi các sửa đổi thường xuyên phân tán xa nhau hoặc cần chia/ghép những đoạn lớn, cấu trúc dạng cây có thể thích hợp hơn.

Bất biến quan trọng nhất cần nhớ là: **mọi ô trống phải tập trung trong một gap liên tiếp, gap ở đúng con trỏ, và phép nối hai phần dữ liệu thật luôn bằng chính xác văn bản logic**. Giữ được bất biến ấy sau di chuyển, chèn, xóa và tăng dung lượng là điều kiện để xây một bộ đệm chỉnh sửa văn bản vừa đúng vừa hiệu quả.

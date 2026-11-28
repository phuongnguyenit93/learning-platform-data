# Biểu diễn cây nhị phân bằng mảng và công thức chỉ số

Khi học **cây nhị phân** (*binary tree*), ta thường vẽ các nút liên kết bằng đường nối từ cha xuống con trái và con phải. Trong chương trình, một cách cài đặt là dùng đối tượng nút cùng hai con trỏ; cách khác là đưa các nút vào **mảng** và tính quan hệ cha–con bằng **chỉ số**. Cách thứ hai đặc biệt hữu ích đối với cây nhị phân **hoàn chỉnh** (*complete binary tree*) và các cấu trúc như **binary heap**.

Bài học thuộc chương **Cây cơ bản** trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Nội dung tập trung vào bất biến vị trí trái/phải, cách đánh chỉ số từ **0** và từ **1**, công thức cha–con–tầng, truy cập và duyệt cây, chi phí thời gian–bộ nhớ. Đồng thời, bài giải thích vì sao biểu diễn mảng gọn cho cây hoàn chỉnh nhưng có thể lãng phí nghiêm trọng cho cây thưa, và cách chọn biểu diễn đúng cho từng bài toán.

> **Điểm cần nhớ:** Công thức **con trái = \(2i+1\)** và **con phải = \(2i+2\)** đúng cho cách **đánh chỉ số từ 0 theo vị trí trong cây nhị phân hoàn hảo tưởng tượng**. Đối với cây hoàn chỉnh, các vị trí từ 0 đến \(n-1\) đều có nút nên có thể lưu gọn. Đối với cây nhị phân bất kỳ, muốn giữ nguyên công thức phải **dành chỗ cho các vị trí thiếu**; không thể tùy ý xóa ô trống rồi tiếp tục sử dụng công thức đó.

## 1. Cây nhị phân và hai vị trí con phân biệt

**Cây nhị phân có gốc** là cây mà mỗi nút có tối đa **hai vị trí con**, gọi là:

- **Con trái** (*left child*).
- **Con phải** (*right child*).

Một vị trí có thể không có nút. Do đó, **chỉ có con trái** và **chỉ có con phải** là hai trạng thái khác nhau, ngay cả khi số con đều bằng một.

~~~text
Cây T1:                    Cây T2:

       A                          A
      /                            \
     B                              B

 A.left = B                 A.left = None
 A.right = None             A.right = B
~~~

Nếu bỏ mất thông tin **trái/phải**, ta không còn khôi phục được đúng cây. Đây là lý do không thể lấy mọi danh sách nút theo chiều rộng, bỏ các ô trống rồi áp dụng công thức vị trí một cách máy móc.

Trong bài này, **gốc có độ sâu 0**, độ sâu của một nút là số cạnh từ gốc đến nút. **Chiều cao cây** là độ sâu lớn nhất của một nút, đếm theo **cạnh**. Với cây không rỗng có chiều cao \(h\), các tầng được đánh số \(0,1,\ldots,h\).

### Hai cách lưu cơ bản

**Nút liên kết bằng con trỏ:**

~~~text
Node:
    value
    left  -> Node hoặc None
    right -> Node hoặc None
~~~

**Mảng theo vị trí cấu trúc:**

~~~text
index:    0    1    2    3    4    5    6
value:   [A,   B,   C,   D,   E,   F,   G]
~~~

Ở cách thứ hai, chỉ số của một nút cho biết vị trí tương đối của nút trong cây. Ta không cần lưu trực tiếp hai con trỏ left/right cho mỗi nút, **nếu** cách biểu diễn và sự tồn tại của các vị trí đã được quy định nhất quán.

## 2. Công thức đánh chỉ số từ 0 (*0-based indexing*)

Đây là cách tự nhiên đối với mảng trong Python, Java, C/C++, JavaScript và nhiều ngôn ngữ khác. Đặt gốc ở **chỉ số 0**.

Với một nút có chỉ số \(i\ge0\):

\[
\boxed{\operatorname{left}(i)=2i+1,\qquad
\operatorname{right}(i)=2i+2.}
\]

Với một nút không phải gốc, tức \(i>0\):

\[
\boxed{\operatorname{parent}(i)=
\left\lfloor\frac{i-1}{2}\right\rfloor.}
\]

Trong phép chia nguyên không âm, công thức cha cũng thường được viết **\((i-1)//2\)** hoặc **\((i-1)/2\)** với phép chia nguyên.

### Ví dụ một cây bảy nút

~~~text
             A (0)
           /       \
        B (1)     C (2)
        /  \       /  \
     D(3) E(4)  F(5) G(6)

Mảng:  [A, B, C, D, E, F, G]
Chỉ số: 0  1  2  3  4  5  6
~~~

| Nút | Chỉ số \(i\) | Chỉ số cha | Con trái | Con phải |
| --- | ---: | ---: | ---: | ---: |
| A | 0 | Không có | 1 (B) | 2 (C) |
| B | 1 | 0 (A) | 3 (D) | 4 (E) |
| C | 2 | 0 (A) | 5 (F) | 6 (G) |
| D | 3 | 1 (B) | 7 (ngoài mảng) | 8 (ngoài mảng) |
| E | 4 | 1 (B) | 9 (ngoài mảng) | 10 (ngoài mảng) |
| F | 5 | 2 (C) | 11 (ngoài mảng) | 12 (ngoài mảng) |
| G | 6 | 2 (C) | 13 (ngoài mảng) | 14 (ngoài mảng) |

**Có công thức không có nghĩa là có nút.** Chẳng hạn con trái theo vị trí của G là 13, nhưng mảng chỉ có bảy phần tử nên **G là lá**.

### Vì sao công thức này đúng?

Nếu đánh số theo **từng tầng từ trái sang phải**, gốc có chỉ số 0, hai con của gốc là 1 và 2, hai con của nút 1 là 3 và 4, hai con của nút 2 là 5 và 6. Khi đi từ tầng hiện tại xuống tầng tiếp theo, **mỗi vị trí cha đóng góp hai vị trí con liên tiếp**; bởi vậy hai vị trí con của chỉ số \(i\) là \(2i+1\) và \(2i+2\).

Ngược lại:

- Nếu \(i=2p+1\) là vị trí con trái, \(\lfloor(i-1)/2\rfloor=p\).
- Nếu \(i=2p+2\) là vị trí con phải, \(\lfloor(i-1)/2\rfloor=\lfloor(2p+1)/2\rfloor=p\).

Do đó cùng một công thức cha dùng được cho **cả con trái và con phải**.

## 3. Công thức đánh chỉ số từ 1 (*1-based indexing*)

Một số tài liệu thuật toán, bài chứng minh và hiện thực heap dùng mảng bắt đầu tại **chỉ số 1**. Khi đó gốc nằm ở ô 1 và ô 0 được bỏ trống hoặc không sử dụng.

Với \(i\ge1\):

\[
\boxed{\operatorname{left}(i)=2i,\qquad
\operatorname{right}(i)=2i+1.}
\]

Với \(i>1\):

\[
\boxed{\operatorname{parent}(i)=
\left\lfloor\frac{i}{2}\right\rfloor.}
\]

~~~text
             A (1)
           /       \
        B (2)     C (3)
        /  \       /  \
     D(4) E(5)  F(6) G(7)

Mảng có ô 0 không dùng:
index:  0    1   2   3   4   5   6   7
value: [·,   A,  B,  C,  D,  E,  F,  G]
~~~

| Quy ước | Chỉ số gốc | Con trái của \(i\) | Con phải của \(i\) | Cha của \(i\) |
| --- | ---: | --- | --- | --- |
| **Từ 0** | 0 | \(2i+1\) | \(2i+2\) | \(\lfloor(i-1)/2\rfloor\), \(i>0\) |
| **Từ 1** | 1 | \(2i\) | \(2i+1\) | \(\lfloor i/2\rfloor\), \(i>1\) |

**Không trộn hai quy ước.** Nếu root là A tại index 0 mà dùng con trái \(2i\), công thức sẽ trả về chính index 0, tạo một “liên kết” sai từ A về A.

Đổi chỉ số từ 0 sang từ 1 bằng \(j=i+1\). Ví dụ con trái theo cách từ 0 là \(2i+1\), khi đổi sang cách từ 1 được \(2i+2=2(i+1)=2j\), đúng công thức một-based.

## 4. Vị trí tầng, độ sâu và đường từ nút về gốc

Với cách 0-based và **các vị trí cấu trúc** được đánh theo quy tắc trên:

- Mức \(0\) có chỉ số bắt đầu là \(0\).
- Mức \(1\) có các chỉ số \(1,2\).
- Mức \(2\) có các chỉ số \(3,4,5,6\).
- Mức \(3\) có các chỉ số \(7,\ldots,14\).

Tổng quát, **các vị trí có thể có** ở độ sâu \(d\) thuộc đoạn:

\[
\boxed{2^d-1\le i\le 2^{d+1}-2.}
\]

Số vị trí ở mức \(d\) là:

\[
(2^{d+1}-2)-(2^d-1)+1=\boxed{2^d}.
\]

Vì vậy **độ sâu của một vị trí** \(i\ge0\) là:

\[
\boxed{d(i)=\left\lfloor\log_2(i+1)\right\rfloor.}
\]

Đây là công thức cho **vị trí có chỉ số \(i\)** trong cách đánh số hình cây; muốn gọi đó là độ sâu của một **nút hiện hữu**, phải kiểm tra ô \(i\) thực sự có nút.

| Độ sâu \(d\) | Khoảng index từ 0 | Số vị trí tối đa |
| ---: | --- | ---: |
| 0 | 0 | 1 |
| 1 | 1–2 | 2 |
| 2 | 3–6 | 4 |
| 3 | 7–14 | 8 |
| 4 | 15–30 | 16 |

### Tìm đường từ một chỉ số về gốc

Lặp phép tính cha cho đến index 0:

~~~text
i = 12
parent(12) = (12 - 1) // 2 = 5
parent(5)  = (5 - 1)  // 2 = 2
parent(2)  = (2 - 1)  // 2 = 0

Đường từ gốc đến vị trí 12:
0 → 2 → 5 → 12
~~~

Với một cây **được lưu hợp lệ**, nếu ô 12 có nút thì **mọi ô tổ tiên 5, 2, 0 cũng phải có nút**. Không được có một nút tồn tại mà thiếu cha trên đường tới gốc.

### Lấy vị trí trái hay phải từ tính chẵn lẻ

Với cách 0-based:

- \(i>0\) **lẻ** \(\Rightarrow i\) là **vị trí con trái** của cha.
- \(i>0\) **chẵn** \(\Rightarrow i\) là **vị trí con phải** của cha.

Ví dụ, 5 là con trái của 2, còn 6 là con phải của 2. **Gốc index 0 là ngoại lệ:** nó không phải con phải của nút nào.

Với cách 1-based, quy tắc chẵn/lẻ đổi lại: **chỉ số chẵn** là con trái, **chỉ số lẻ lớn hơn 1** là con phải.

## 5. Cây hoàn chỉnh: điều kiện để mảng không có lỗ

**Cây nhị phân hoàn chỉnh** (*complete binary tree*) là cây có mọi tầng, trừ có thể tầng cuối, được lấp đầy; tầng cuối được lấp **từ trái sang phải** mà không có khoảng trống.

Với cây hoàn chỉnh có \(n\ge1\) nút, biểu diễn từ 0 chứa **đúng \(n\) phần tử liên tiếp ở các index**:

\[
\boxed{0,1,2,\ldots,n-1.}
\]

Không có ô trống ở giữa. Đây là bất biến giúp công thức cha–con hoạt động cùng kiểm tra biên đơn giản.

~~~text
Cây complete với n=6:

              A(0)
             /    \
           B(1)   C(2)
           / \     /
         D(3) E(4) F(5)

Mảng:
 index:  0  1  2  3  4  5
 value: [A, B, C, D, E, F]
~~~

Đối với nút \(i=2\) (C), vị trí con trái là \(2(2)+1=5<n\) nên có F; vị trí con phải là 6, vượt biên \(n-1=5\), nên **không có con phải**.

### Khi nào nút có con?

Với mảng hoàn chỉnh 0-based dài \(n\):

\[
\begin{aligned}
\text{có con trái}&\iff 2i+1<n,\\
\text{có con phải}&\iff 2i+2<n,\\
\text{là lá}&\iff 2i+1\ge n.
\end{aligned}
\]

Nút trong có các chỉ số:

\[
\boxed{0\le i<\left\lfloor\frac n2\right\rfloor.}
\]

Các lá có chỉ số:

\[
\boxed{\left\lfloor\frac n2\right\rfloor\le i\le n-1.}
\]

Số lá và chiều cao lần lượt là:

\[
\boxed{L=\left\lceil\frac n2\right\rceil,\qquad
h=\left\lfloor\log_2n\right\rfloor.}
\]

Ví dụ với \(n=6\): nút trong là các chỉ số 0,1,2 (A,B,C); lá là 3,4,5 (D,E,F); \(L=3\) và \(h=2\).

**Lưu ý:** Kết quả \(L=\lceil n/2\rceil\) và \(h=\lfloor\log_2n\rfloor\) đúng cho **cây complete**, không đúng cho **cây nhị phân bất kỳ** chỉ vì dùng mảng để lưu.

## 6. Full, perfect, complete và mảng: không phải cùng một khái niệm

Các thuật ngữ mô tả **hình dạng cây** cần được hiểu riêng:

| Khái niệm | Định nghĩa dùng trong bài | Có chắc lưu gọn tại chỉ số 0 đến \(n-1\)? |
| --- | --- | --- |
| **Binary tree bất kỳ** | Mỗi nút tối đa hai vị trí con trái/phải | Không |
| **Full binary tree** (*cây nhị phân đầy đủ*) | Mỗi nút trong có đúng hai con | Không |
| **Perfect binary tree** (*cây nhị phân hoàn hảo*) | Full và mọi lá ở cùng độ sâu | Có |
| **Complete binary tree** (*cây nhị phân hoàn chỉnh*) | Các mức trước mức cuối đầy; mức cuối lấp từ trái sang phải | Có |

Một cây **perfect** đồng thời **complete**. Nhưng một cây **full** không nhất thiết complete; cũng có cây complete **không full**.

### Ví dụ full nhưng không complete

~~~text
           A
         /   \
        B     C
             / \
            D   E

         Mỗi nút trong có đúng 2 con.
         Nhưng tầng sâu nhất chưa lấp từ trái.
~~~

Nếu đặt nút theo **vị trí trong khung nhị phân** 0-based:

| Nút | A | B | C | D | E |
| --- | ---: | ---: | ---: | ---: | ---: |
| Vị trí | 0 | 1 | 2 | 5 | 6 |

Các ô **3 và 4** phải để trống. Năm nút này **không** được lưu như một cây complete ở mảng \([A,B,C,D,E]\), vì với biểu diễn đó D và E sẽ trở thành **con của B**.

### Ví dụ complete nhưng không full

~~~text
          A
        /   \
       B     C
      /
     D
~~~

Mảng \([A,B,C,D]\) hoàn toàn hợp lệ vì các vị trí hiện hữu là \(0,1,2,3\) liên tiếp. Nhưng B chỉ có **một con**, nên cây **không full**.

Do đó, **khả năng lưu gọn theo công thức chỉ số gắn với complete**, không gắn với thuộc tính full hay việc số con tối đa là hai.

## 7. Cây nhị phân thưa: chỉ số có thể tạo rất nhiều ô trống

Với cây nhị phân **bất kỳ**, có thể vẫn dùng công thức vị trí \(2i+1\) và \(2i+2\), nhưng phải phân biệt:

1. **Vị trí cấu trúc** (*structural position*): index toán học của một ô trong khung cây nhị phân hoàn hảo.
2. **Nút thực sự hiện hữu**: vị trí đó có một bản ghi đang lưu.

Xét cây:

~~~text
      A
       \
        B
       /
      C
~~~

Với 0-based:

- Gốc A ở index **0**.
- B là con **phải** của A, nên ở index \(2\cdot0+2=\mathbf{2}\).
- C là con **trái** của B, nên ở index \(2\cdot2+1=\mathbf{5}\).

Mảng vị trí phải có đủ các ô từ 0 đến 5:

~~~text
index:    0       1       2       3       4       5
value:   [A,      ·,      B,      ·,      ·,      C]

         · là vị trí không có nút (khác với một giá trị hợp lệ).
~~~

Trong ví dụ, **\(n=3\) nút** nhưng cần **6 ô vật lý** nếu dùng mảng trực tiếp tới chỉ số lớn nhất. Chiều cao cây là 2, còn số phần tử mảng là 6; **không** được lấy \(\lfloor\log_2n\rfloor=1\) làm chiều cao của cây này.

### Bất biến khi có ô trống

Nếu vị trí \(i>0\) chứa một nút, vị trí cha \(\lfloor(i-1)/2\rfloor\) **phải có nút**. Nói cách khác, các vị trí hiện hữu phải **đóng dưới phép lấy cha** (*ancestor-closed*).

Không được có:

~~~text
index:     0      1      2      3      4      5
value:    [A,     ·,     ·,     ·,     ·,     C]

Sai: C ở index 5 nhưng cha tại index 2 không tồn tại.
~~~

Để biểu diễn chính xác, cần biết ô nào **có nút**. Nếu **None/null** là một **giá trị dữ liệu hợp lệ** của nút, không thể dùng chính None/null làm dấu vắng mặt; phải dùng **sentinel riêng**, **bitmap occupancy** hoặc một cờ tồn tại.

### Trường hợp suy biến: chỉ \(h+1\) nút nhưng chỉ số tăng theo hàm mũ

Xét cây chỉ có nhánh phải, mỗi nút có đúng một **con phải**:

~~~text
     R
       \
        A
          \
           B
             \
              C
                \
                 D
~~~

Đặt \(i_0=0\) và \(i_{d+1}=2i_d+2\). Giải truy hồi:

\[
\boxed{i_d=2^{d+1}-2.}
\]

Với nút sâu nhất ở độ sâu \(h\), chỉ số lớn nhất là \(2^{h+1}-2\), nên mảng trực tiếp cần tối thiểu:

\[
\boxed{M=i_h+1=2^{h+1}-1\text{ ô}.}
\]

Nhưng cây chỉ có:

\[
\boxed{n=h+1\text{ nút}.}
\]

Ví dụ:

| Chiều cao \(h\) | Số nút thực \(n=h+1\) | Số ô mảng trực tiếp \(2^{h+1}-1\) |
| ---: | ---: | ---: |
| 3 | 4 | 15 |
| 8 | 9 | 511 |
| 15 | 16 | 65.535 |
| 20 | 21 | 2.097.151 |

Như vậy, mảng vị trí có thể cần **bộ nhớ tăng theo hàm mũ của chiều cao** trong khi số nút chỉ tăng tuyến tính. Đây là lý do không nên tự động chọn biểu diễn này cho cây rất thưa hoặc nghiêng một phía.

**Lưu ý toán học:** \(O(2^h)\) là số vị trí có thể phải cấp theo chỉ số lớn nhất; không phải mọi cây cao \(h\) đều dùng nhiều ô đến thế. Nếu sử dụng **map từ index sang nút** thay cho mảng đặc, chỉ các vị trí đang có nút mới chiếm bản ghi, đánh đổi lấy overhead của map.

## 8. Mảng vị trí khác với danh sách duyệt theo chiều rộng

Hai cách biểu diễn trông giống nhau nhưng **không được phép tráo đổi**:

### Cách A — Mảng vị trí trực tiếp (*heap-indexed positional array*)

Với cây A → con phải B → con trái C:

~~~text
positions: [A, null, B, null, null, C]
indexes:    0    1    2    3     4    5
~~~

Ở đây **mỗi index chính là vị trí cấu trúc**, nên dùng được công thức con trái \(2i+1\), con phải \(2i+2\).

### Cách B — Tuần tự hóa theo hàng đợi có dấu null

Một định dạng khác phát ra các nút theo BFS và ghi dấu null khi gặp **con bị thiếu**, nhưng **không tiếp tục sinh con của những null đó**. Dãy có thể rút gọn bỏ các null ở cuối:

~~~text
tokens: [A, null, B, C]
~~~

Quy tắc **giải mã** là:

1. Lấy A làm gốc.
2. Hai token tiếp theo cho **con trái và con phải của A**: null, B.
3. B là nút có thật nên hai token tiếp theo (nếu có) cho **con trái và con phải của B**: C, null.

Kết quả vẫn là cây A → phải B → trái C.

Nhưng trong dãy token đó, **C ở vị trí mảng số 3** không đồng nghĩa C có **chỉ số cấu trúc 3**. Chỉ số cấu trúc đúng của C là **5**.

| Thuộc tính | Mảng vị trí | Token BFS có null |
| --- | --- | --- |
| Mỗi ô là một vị trí trong cây hoàn hảo tưởng tượng | Có | Không nhất thiết |
| Dùng trực tiếp công thức \(2i+1,2i+2\) trên index của token | Có | **Không** |
| Có thể bỏ những null ở giữa mà vẫn giữ nguyên công thức | Không | Phải giải mã theo hàng đợi |
| Có thể bỏ null ở cuối | Có thể cắt phần đuôi sau vị trí lớn nhất có nút | Có, theo quy tắc của định dạng |
| Khôi phục trái/phải | Theo chỉ số cấu trúc | Theo thứ tự giải mã các token |

**Lỗi đặc biệt nguy hiểm:** Bỏ hết các vị trí null khỏi \([A,\text{null},B,\text{null},\text{null},C]\) để được \([A,B,C]\) rồi áp dụng công thức 0-based sẽ tạo **cây khác**: A có hai con B và C.

Nếu cần mảng **không có lỗ cho cây tùy ý**, hãy lưu **con trỏ/chỉ số con riêng** hoặc một định dạng tuần tự hóa có thuật toán giải mã rõ ràng.

## 9. Các cách lưu cây thưa mà không lãng phí vị trí

Ngoài mảng vị trí trực tiếp, ta có thể chọn một trong các cách sau:

### 9.1. Mảng các bản ghi nút, mỗi bản ghi lưu chỉ số con

Đặt các bản ghi hiện hữu liên tiếp trong mảng và lưu riêng left/right:

~~~text
Cây:     A
           \
            B
           /
          C

record index | value | left_index | right_index
-------------+-------+------------+------------
      0      |   A   |    None    |     1
      1      |   B   |      2     |    None
      2      |   C   |    None    |    None
~~~

Chỉ có **3 bản ghi cho 3 nút**, không cần ô trống tại chỉ số cấu trúc 1,3,4. Nhưng **chỉ số con lúc này là trường dữ liệu**, không còn tính bằng \(2i+1\) hay \(2i+2\) từ **index bản ghi**.

Ưu điểm: bộ nhớ \(O(n)\) cho cả cây thưa; có thể giữ các bản ghi trong một vùng liên tục. Đánh đổi: mỗi bản ghi cần hai chỉ số hoặc dấu không có con, và khi di chuyển/sắp lại bản ghi phải cập nhật liên kết.

### 9.2. Nút có con trỏ trái/phải

~~~text
Node(value, left, right)
~~~

Đây là cách tự nhiên cho BST, cây cú pháp hoặc các cây cần thường xuyên thay đổi cấu trúc. Mỗi nút có thể được cấp phát độc lập, nên chèn cây con không buộc cấp phát cả dải vị trí không có nút.

Đổi lại, các nút có thể nằm ở nhiều vị trí bộ nhớ khác nhau, gây chi phí con trỏ và cache miss. Không có kết luận rằng cây con trỏ luôn chậm hơn mảng trong mọi workload.

### 9.3. Map từ chỉ số vị trí đến nút

Có thể giữ công thức vị trí nhưng chỉ lưu các ô thực sự hiện hữu:

~~~text
positions = {0: "A", 2: "B", 5: "C"}
~~~

Kiểm tra con trái của index 2 bằng khóa 5 trong map, con phải bằng khóa 6. Cách này giữ nguyên **ngữ nghĩa index cấu trúc** mà không cấp phát toàn bộ mảng tới index lớn nhất.

Chi phí bộ nhớ gồm **nút, khóa index và metadata của map**; tra cứu thường \(O(1)\) **kỳ vọng** với hàm băm phù hợp. Đối với cây cực sâu, index có thể rất lớn và cần kiểu số nguyên đủ rộng.

### Bảng lựa chọn nhanh

| Biểu diễn | Bộ nhớ theo số nút | Tra con trái/phải | Phù hợp nhất |
| --- | --- | --- | --- |
| Mảng đặc của cây complete | \(O(n)\) | \(O(1)\) tính index và đọc ô | Binary heap, cây complete |
| Mảng vị trí cho cây thưa | Có thể tới \(O(2^h)\) | \(O(1)\) nếu index hợp lệ và nằm trong mảng | Cây nông, nhiều vị trí có nút |
| Mảng bản ghi với chỉ số con | \(O(n)\) | \(O(1)\) qua trường left/right | Cây tùy ý, cần dữ liệu mảng liên tục |
| Nút và con trỏ | \(O(n)\) | \(O(1)\) qua con trỏ | Cây thay đổi cấu trúc linh hoạt |
| Map theo index cấu trúc | \(O(n)\) bản ghi cộng overhead map | \(O(1)\) kỳ vọng | Cây thưa cần giữ công thức vị trí |

## 10. Các thao tác trên mảng complete: truy cập, chèn và xóa

Giả sử có mảng **không lỗ** \(\text{A}[0..n-1]\), biểu diễn một cây nhị phân **complete**.

### 10.1. Truy cập cha và con

Nếu \(i>0\), cha ở \((i-1)//2\). Con trái ở \(2i+1\) nếu index này nhỏ hơn \(n\); con phải ở \(2i+2\) nếu nhỏ hơn \(n\). Mỗi phép tính chỉ số và đọc mảng có chi phí **\(O(1)\)** trong mô hình RAM thông thường.

Không được truy cập cha của **gốc** hoặc truy cập index con chưa tồn tại mà không kiểm tra biên.

### 10.2. Thêm nút ở cuối để giữ hình dạng complete

Muốn thêm nút mới **như vị trí tiếp theo theo thứ tự tầng**, chỉ cần nối phần tử vào cuối mảng:

~~~text
Trước: [A, B, C, D, E, F]     n=6
Sau:   [A, B, C, D, E, F, G]  n=7

G ở index 6:
parent(6) = (6-1)//2 = 2  → C
Index 6 là vị trí con phải của C.
~~~

Với mảng động hỗ trợ append, thao tác thêm cuối thường **\(O(1)\) phân bổ (*amortized*)**, chưa tính các bất biến **giá trị** bổ sung như heap-order hoặc thứ tự khóa.

### 10.3. Xóa nút cuối để giữ hình dạng complete

Nếu xóa đúng **nút cuối cùng** ở index \(n-1\), mảng còn lại vẫn là dãy vị trí 0 đến \(n-2\) của một cây complete. Pop cuối mảng động thường tốn \(O(1)\).

Ngược lại, xóa một nút giữa không thể chỉ loại phần tử rồi **dịch mọi phần tử sau sang trái** nếu muốn giữ nguyên quan hệ cha–con. Khi index thay đổi, nhiều phần tử có thể có **cha mới**.

Một số cấu trúc như **heap** thay nút bị xóa bằng phần tử cuối rồi khôi phục bất biến heap. Đây là thuật toán có chủ đích, **không phải** cách xóa đúng cho mọi cây nhị phân có nhãn hoặc BST.

### 10.4. Duyệt

Với cây complete lưu theo index tầng:

- Đọc lần lượt \(\text{A}[0],\ldots,\text{A}[n-1]\) chính là **duyệt theo chiều rộng BFS** từ trái sang phải.
- **Preorder** và **postorder** không tương đương đọc tuyến tính mảng; chúng phải lần theo công thức con trái và con phải.
- **Inorder** (trái – nút – phải) cũng cần thuật toán duyệt cấu trúc; không thể coi là dữ liệu đã sắp tăng dần nếu cây không có bất biến BST.

Ví dụ với \([A,B,C,D,E,F]\):

| Kiểu duyệt | Thứ tự nút |
| --- | --- |
| BFS | A, B, C, D, E, F |
| Preorder (*nút – trái – phải*) | A, B, D, E, C, F |
| Inorder (*trái – nút – phải*) | D, B, E, A, F, C |
| Postorder (*trái – phải – nút*) | D, E, B, F, C, A |

Mỗi phép duyệt đầy đủ xử lý \(n\) nút nên tốn **\(O(n)\)** thời gian. Đối với cây complete, độ sâu \(O(\log n)\) nên DFS theo đường đi thường có ngăn xếp \(O(\log n)\), chưa tính bộ nhớ lưu kết quả.

## 11. Python: cây complete lưu trong một mảng gọn

Đoạn mã sau minh họa chính xác cách **index từ 0**. Mỗi phần tử của mảng là giá trị một nút, còn **sự tồn tại của nút** được xác định bởi điều kiện \(0\le i<n\), không dựa vào nội dung giá trị.

Lớp này chỉ duy trì bất biến **hình dạng cây complete**. Nó **không tự duy trì thứ tự BST hoặc heap-order**; khi dùng cho heap cần thêm thuật toán so sánh và hoán đổi riêng.

~~~python
class CompleteBinaryTree:
    def __init__(self, values=()):
        # Mọi phần tử liên tiếp là một nút, kể cả khi value=None.
        self.values = list(values)

    def __len__(self):
        return len(self.values)

    def _check_index(self, index):
        if type(index) is not int or not (0 <= index < len(self.values)):
            raise IndexError("Vị trí nút không tồn tại")

    def parent(self, index):
        self._check_index(index)
        if index == 0:
            return None  # Gốc không có cha.
        p = (index - 1) // 2
        return p, self.values[p]

    def children(self, index):
        self._check_index(index)
        left = 2 * index + 1
        right = 2 * index + 2
        n = len(self.values)

        # Trả về (index, value) nếu có, None nếu không có.
        left_child = (left, self.values[left]) if left < n else None
        right_child = (right, self.values[right]) if right < n else None
        return left_child, right_child

    def append(self, value):
        self.values.append(value)
        return len(self.values) - 1

    def pop_last(self):
        if not self.values:
            raise IndexError("Không có nút nào để xóa")
        return self.values.pop()

    def height(self):
        n = len(self.values)
        if n == 0:
            return -1  # Quy ước riêng cho cây rỗng trong ví dụ.
        return n.bit_length() - 1  # floor(log2(n)).

    def leaves(self):
        n = len(self.values)
        return self.values[n // 2:]

    def breadth_first(self):
        return list(self.values)  # Chính là thứ tự tầng.

    def preorder(self):
        if not self.values:
            return []

        result = []
        stack = [0]
        n = len(self.values)

        while stack:
            index = stack.pop()
            result.append(self.values[index])
            right = 2 * index + 2
            left = 2 * index + 1

            # Stack LIFO: đẩy phải trước để xử lý trái trước.
            if right < n:
                stack.append(right)
            if left < n:
                stack.append(left)
        return result

    def inorder(self):
        result = []
        stack = []
        n = len(self.values)
        current = 0 if n else None

        while current is not None or stack:
            while current is not None:
                stack.append(current)
                left = 2 * current + 1
                current = left if left < n else None

            current = stack.pop()
            result.append(self.values[current])
            right = 2 * current + 2
            current = right if right < n else None
        return result

    def postorder(self):
        if not self.values:
            return []

        result = []
        stack = [(0, False)]
        n = len(self.values)

        while stack:
            index, visited = stack.pop()
            if visited:
                result.append(self.values[index])
                continue

            # Xếp để xử lý trái, phải, rồi nút.
            stack.append((index, True))
            right = 2 * index + 2
            left = 2 * index + 1
            if right < n:
                stack.append((right, False))
            if left < n:
                stack.append((left, False))
        return result


tree = CompleteBinaryTree(["A", "B", "C", "D", "E", "F"])

print(tree.parent(5))         # (2, 'C')
print(tree.children(2))       # ((5, 'F'), None)
print(tree.height())          # 2
print(tree.leaves())          # ['D', 'E', 'F']
print(tree.breadth_first())   # ['A','B','C','D','E','F']
print(tree.preorder())        # ['A','B','D','E','C','F']
print(tree.inorder())         # ['D','B','E','A','F','C']
print(tree.postorder())       # ['D','E','B','F','C','A']

index = tree.append("G")
print(index)                  # 6
print(tree.parent(index))     # (2, 'C')
print(tree.pop_last())        # G
print(len(tree))              # 6

# None vẫn có thể là GIÁ TRỊ của một nút hiện hữu.
with_none = CompleteBinaryTree([None, "B", "C"])
print(len(with_none))         # 3
print(with_none.children(0))  # ((1, 'B'), (2, 'C'))
~~~

### Giải thích các quyết định trong mã

**Gốc** chỉ nằm ở index 0 khi mảng không rỗng. Hàm parent không trả index \(-1\) cho gốc vì index âm trong Python còn có nghĩa đặc biệt là truy cập từ cuối mảng; dùng \(-1\) như một chỉ số thật có thể gây lỗi logic.

**Con trái và con phải** được tính bằng chỉ số và kiểm tra biên. Hai nhánh trả về một cặp \((index,value)\) nếu nút tồn tại; dấu **None ở cấp độ cặp** nghĩa là không có con. Cách này vẫn cho phép giá trị thực của một nút là None.

**Chiều cao** của cây complete được suy trực tiếp từ số nút. Hàm bit_length cho số nguyên dương \(n\) trả số bit cần biểu diễn \(n\); do đó \(n.\operatorname{bit\_length}()-1=\lfloor\log_2n\rfloor\).

**Mảng trống** được lớp ví dụ quy ước có chiều cao \(-1\), chỉ để thuận tiện lập trình. Các công thức với \(n\ge1\) không bị thay đổi; khi đọc giáo trình khác cần kiểm tra quy ước về cây rỗng.

**Duyệt DFS** sử dụng stack chứa các index, không sửa quan hệ cấu trúc; các phép duyệt cho cùng kết quả như trên cây con trỏ có hình dạng tương ứng.

## 12. Python: cây thưa dùng chỉ số vị trí và sentinel riêng

Khi cây có lỗ, cần quản lý cả **vị trí** lẫn **tình trạng hiện hữu**. Mã dưới đây cố ý dùng một mảng các ô; vị trí vắng mặt được đánh dấu bằng đối tượng sentinel **MISSING**, không phải None, vì None có thể là một giá trị dữ liệu hợp lệ.

Đây là một cách minh họa cho **cây thưa nông**. Với một nhánh sâu, mảng có thể rất lớn như đã chứng minh ở mục 7; khi đó nên dùng map theo chỉ số hoặc nút liên kết.

~~~python
from collections import deque


MISSING = object()


class PositionalBinaryTree:
    def __init__(self):
        self.slots = []

    def exists(self, index):
        return (
            type(index) is int
            and 0 <= index < len(self.slots)
            and self.slots[index] is not MISSING
        )

    def set_root(self, value):
        if self.slots:
            raise ValueError("Gốc đã được thiết lập")
        self.slots.append(value)

    def add_child(self, parent_index, side, value):
        if not self.exists(parent_index):
            raise ValueError("Cha không tồn tại")
        if side not in ("left", "right"):
            raise ValueError("side phải là left hoặc right")
        if value is MISSING:
            raise ValueError("Không được dùng sentinel làm giá trị nút")

        index = 2 * parent_index + (1 if side == "left" else 2)
        if self.exists(index):
            raise ValueError("Vị trí con đã có nút")

        if index >= len(self.slots):
            self.slots.extend([MISSING] * (index + 1 - len(self.slots)))

        self.slots[index] = value
        return index

    def get(self, index):
        if not self.exists(index):
            raise IndexError("Nút tại vị trí này không tồn tại")
        return self.slots[index]

    def breadth_first(self):
        if not self.exists(0):
            return []

        queue = deque([0])
        result = []
        while queue:
            index = queue.popleft()
            result.append((index, self.slots[index]))
            for child in (2 * index + 1, 2 * index + 2):
                if self.exists(child):
                    queue.append(child)
        return result

    def node_count(self):
        return sum(value is not MISSING for value in self.slots)

    def height(self):
        # Chỉ dùng cho mô hình có cấu trúc hợp lệ.
        if not self.exists(0):
            return -1
        return max(
            (index + 1).bit_length() - 1
            for index, value in enumerate(self.slots)
            if value is not MISSING
        )

    def remove_subtree(self, index):
        """Xóa nguyên cây con để không bỏ lại nút mồ côi."""
        if not self.exists(index):
            return 0

        stack = [index]
        removed = 0
        while stack:
            current = stack.pop()
            if not self.exists(current):
                continue

            # Duyệt các con TRƯỚC khi xóa vị trí hiện tại.
            for child in (2 * current + 1, 2 * current + 2):
                if self.exists(child):
                    stack.append(child)

            self.slots[current] = MISSING
            removed += 1

        # Chỉ bỏ các ô trống ở CUỐI mảng.
        while self.slots and self.slots[-1] is MISSING:
            self.slots.pop()
        return removed


tree = PositionalBinaryTree()
tree.set_root("A")                 # index 0
b = tree.add_child(0, "right", "B")  # index 2
c = tree.add_child(b, "left", "C")   # index 5

print(b, c)                      # 2 5
print(tree.node_count())         # 3 nút
print(len(tree.slots))           # 6 ô được cấp
print(tree.breadth_first())      # [(0,'A'), (2,'B'), (5,'C')]
print(tree.height())             # 2
print(tree.get(5))               # C
print(tree.exists(1))            # False: không có con trái của A

print(tree.remove_subtree(2))    # 2: xóa B và C
print(tree.node_count())         # 1
print(len(tree.slots))           # 1 (chỉ còn A)

# None là giá trị thực, khác MISSING.
another = PositionalBinaryTree()
another.set_root(None)
assert another.exists(0)
assert another.get(0) is None
~~~

### Những bất biến được bảo vệ

1. **Chỉ thêm con của nút đã tồn tại.** Điều này ngăn tạo một nút mồ côi có index cha trống.
2. **Không ghi đè vị trí có nút.** Thêm một nút ở con trái/phải đã bị chiếm phải bị từ chối hoặc được xử lý bằng thao tác cập nhật khác có ngữ nghĩa rõ ràng.
3. **Sentinel khác giá trị dữ liệu.** Nếu để None làm dấu rỗng, ta không thể lưu một nút có payload None.
4. **Xóa toàn bộ cây con.** Chỉ xóa B nhưng giữ C ở index 5 sẽ làm C thiếu cha ở index 2; phương thức remove_subtree xóa luôn các hậu duệ.
5. **Chỉ cắt ô trống ở cuối.** Không được dịch các phần tử còn lại sang trái khi xóa vị trí giữa, vì chỉ số của các nút khác sẽ đổi.

**Độ phức tạp đáng chú ý:** Khi add_child phải mở rộng mảng tới index rất lớn, chi phí cấp phát và điền MISSING tỷ lệ với **số ô mới**, không chỉ số nút thêm vào. Hàm node_count quét toàn bộ mảng, còn remove_subtree có thể tốn thêm thời gian cắt các ô rỗng ở đuôi. Đây là ví dụ cụ thể vì sao một cây thưa nên được biểu diễn bằng **map hoặc các node liên kết** nếu chiều cao lớn.

## 13. Ứng dụng điển hình: binary heap

**Binary heap** là cây nhị phân thỏa hai bất biến:

1. **Hình dạng:** cây **complete** nên biểu diễn gọn bằng mảng index từ 0.
2. **Giá trị:** với **max-heap**, giá trị của cha **không nhỏ hơn** giá trị của mỗi con; với **min-heap**, quan hệ đảo chiều.

Ví dụ max-heap:

~~~text
             90(0)
           /       \
        70(1)     85(2)
        /  \       /
     20(3) 50(4) 60(5)

Mảng: [90, 70, 85, 20, 50, 60]
~~~

### Chèn vào heap

Chèn giá trị **95**:

1. **Append 95** vào cuối mảng, index 6. Cây vẫn **complete**.
2. Cha của index 6 là \((6-1)//2=2\), giá trị 85; vì \(95>85\), **đổi chỗ**.
3. 95 tới index 2. Cha của index 2 là 0, giá trị 90; vì \(95>90\), tiếp tục **đổi chỗ**.
4. 95 tới gốc; điều kiện max-heap được khôi phục.

~~~text
Ban đầu:       [90, 70, 85, 20, 50, 60]
Append 95:     [90, 70, 85, 20, 50, 60, 95]
Đổi 95 với 85: [90, 70, 95, 20, 50, 60, 85]
Đổi 95 với 90: [95, 70, 90, 20, 50, 60, 85]
~~~

Quá trình đi ngược theo công thức cha gọi là **sift-up**. Mỗi bước tính index cha trong \(O(1)\); số bước tối đa bằng chiều cao:

\[
\boxed{T_{\mathrm{insert\ heap}}=O(\log n).}
\]

### Xóa gốc khỏi heap

Khi xóa phần tử lớn nhất 95:

1. Thay giá trị gốc bằng **phần tử cuối** 85.
2. Xóa phần tử cuối để mảng vẫn **complete**.
3. So 85 với hai con 70 và 90; đổi với **con lớn hơn là 90**.
4. Kết thúc khi bất biến max-heap được giữ.

~~~text
Trước:      [95, 70, 90, 20, 50, 60, 85]
Lấy 95:     [85, 70, 90, 20, 50, 60]
Sift-down:  [90, 70, 85, 20, 50, 60]
~~~

Sift-down đi xuống nhiều nhất \(h=O(\log n)\) mức, do đó xóa gốc tốn **\(O(\log n)\)** với các phép so sánh \(O(1)\).

**Không nhầm hình dạng với thứ tự dữ liệu:** Mảng heap **không** có thứ tự tăng/giảm toàn cục. Việc phần tử cha lớn hơn con **không** có nghĩa mọi phần tử bên trái nhỏ hơn hoặc lớn hơn mọi phần tử bên phải như BST. Duyệt inorder một heap **không** sinh dãy có thứ tự tổng thể.

## 14. Độ phức tạp thời gian và bộ nhớ

Gọi \(n\) là số nút thật, \(h\) là chiều cao tính bằng cạnh, \(M\) là số ô đã cấp phát của một **mảng vị trí** và \(d\) là độ sâu vị trí cần truy cập.

| Thao tác/tài nguyên | Cây complete bằng mảng | Cây thưa bằng mảng vị trí |
| --- | --- | --- |
| Số ô cần lưu | Đúng \(n\) ô, \(O(n)\) | \(M\) có thể tới \(O(2^h)\) |
| Tính index cha/con | \(O(1)\) | \(O(1)\) phép toán số học nếu không tràn |
| Đọc một vị trí từ index hợp lệ | \(O(1)\) | \(O(1)\) nếu ô đã cấp; phải kiểm tra có nút |
| Thêm nút vào cuối | \(O(1)\) phân bổ với mảng động | Thêm con có thể cần cấp nhiều ô trống |
| Xóa cuối | \(O(1)\) điển hình | Không thể xóa giữa rồi dịch index mà giữ nguyên cấu trúc |
| BFS toàn cây | \(O(n)\) bằng quét mảng | \(O(n)\) nếu duyệt **các nút hiện hữu**; quét mọi ô tốn \(O(M)\) |
| DFS toàn cây | \(O(n)\) | \(O(n)\) nếu chỉ đi qua các nút hiện hữu |
| Chiều cao | \(\lfloor\log_2n\rfloor\) | Có thể tới \(n-1\) |
| Bộ nhớ phụ DFS | \(O(h)=O(\log n)\) với triển khai theo đường | \(O(h)\), có thể thành \(O(n)\) |

Các độ phức tạp này giả định chỉ số nằm trong kiểu dữ liệu số nguyên phù hợp và việc truy cập mảng là hằng số trong mô hình RAM. Với khóa hoặc giá trị rất lớn, chi phí sao chép và so sánh cũng cần tính riêng.

### Vấn đề tràn số khi tính index

Trong Python, số nguyên có thể tăng độ dài khi cần, nhưng **mảng vẫn có giới hạn bộ nhớ**. Trong các ngôn ngữ dùng số nguyên có độ rộng cố định như 32 hoặc 64 bit, phép tính \(2i+2\) có thể **tràn số** khi \(i\) lớn.

Khi cài đặt bằng số nguyên có giới hạn, cần kiểm tra an toàn trước khi nhân:

\[
2i+2\le\operatorname{MAX\_INDEX}.
\]

Nếu không kiểm tra, index có thể thành số âm hoặc quay vòng, gây truy cập sai bộ nhớ. Điều này đặc biệt quan trọng với mảng vị trí của cây **rất sâu**, vì index tăng theo hàm mũ dù số nút ít.

### Khi nào nên ưu tiên mảng?

Biểu diễn mảng là một lựa chọn mạnh khi:

- Cây gần **complete** và có thể giữ invariant về **vị trí lấp từ trái sang phải**.
- Cần truy cập cha/con thường xuyên mà không muốn lưu hai con trỏ trên mỗi nút.
- Dữ liệu nằm gọn trong RAM, muốn có **cục bộ bộ nhớ (*cache locality*)** và ít lần cấp phát đối tượng.
- Các thao tác chủ yếu là **thêm cuối, lấy/xóa cuối hoặc điều chỉnh giá trị** dọc một đường ngắn, như trong heap.

Nếu cây thay đổi hình dạng không theo mức, có nhiều nhánh thiếu hoặc cần chuyển cây con, nên xem xét **nút liên kết**, **mảng bản ghi có trường chỉ số con**, hoặc **map index → node** thay vì ép mọi cây vào một mảng vị trí đặc.

## 15. Mối liên hệ thú vị giữa chỉ số và đường đi bằng bit

Công thức \(2i+1,2i+2\) có một cách hiểu rất trực quan qua **biểu diễn nhị phân**.

Đặt:

\[
\boxed{q=i+1.}
\]

Ở gốc \(i=0\), ta có \(q=1\), biểu diễn nhị phân là **1**. Từ một nút có \(q=i+1\):

- Đi **sang con trái**: \(i'=2i+1\), nên \(q'=i'+1=2(i+1)=2q\): viết thêm bit **0** bên phải.
- Đi **sang con phải**: \(i'=2i+2\), nên \(q'=2(i+1)+1=2q+1\): viết thêm bit **1** bên phải.

Vì vậy, viết \(i+1\) ở hệ nhị phân, **bỏ bit 1 cao nhất**, ta thu được một chuỗi bit mô tả **đường từ gốc tới vị trí \(i\)**:

- Bit **0** nghĩa là đi sang con **trái**.
- Bit **1** nghĩa là đi sang con **phải**.

| Index \(i\) | \(i+1\) ở dạng nhị phân | Sau khi bỏ bit 1 đầu | Đường từ gốc |
| ---: | --- | --- | --- |
| 0 | 1 | (rỗng) | Gốc |
| 1 | 10 | 0 | Trái |
| 2 | 11 | 1 | Phải |
| 3 | 100 | 00 | Trái → trái |
| 5 | 110 | 10 | Phải → trái |
| 6 | 111 | 11 | Phải → phải |
| 12 | 1101 | 101 | Phải → trái → phải |

**Ví dụ index 12:** \(i+1=13=(1101)_2\). Bỏ bit 1 đầu còn 101, nên đường là **phải – trái – phải**:

~~~text
Gốc index 0
  → phải index 2
  → trái index 5
  → phải index 12
~~~

Số bit còn lại đúng bằng **độ sâu**:

\[
\boxed{d(i)=\operatorname{bitlength}(i+1)-1
=\lfloor\log_2(i+1)\rfloor.}
\]

### Mã minh họa chuyển đổi hai chiều

~~~python
def index_to_path(index):
    if type(index) is not int or index < 0:
        raise ValueError("index phải là số nguyên không âm")
    # bin(index+1) bắt đầu bằng '0b1'; bỏ ba ký tự này.
    bits = bin(index + 1)[3:]
    return "".join("L" if bit == "0" else "R" for bit in bits)


def path_to_index(path):
    q = 1
    for direction in path:
        if direction not in ("L", "R"):
            raise ValueError("Đường đi chỉ được chứa L hoặc R")
        q = 2 * q + (1 if direction == "R" else 0)
    return q - 1


assert index_to_path(0) == ""
assert index_to_path(1) == "L"
assert index_to_path(2) == "R"
assert index_to_path(5) == "RL"
assert index_to_path(12) == "RLR"
assert path_to_index("RLR") == 12
assert path_to_index("LL") == 3
~~~

Ứng dụng của cách nhìn bằng bit là **định vị cây con**, diễn giải tổ tiên, và xây các công cụ gỡ lỗi chỉ số. Tuy nhiên, chuỗi bit chỉ cho biết **vị trí lý thuyết**, không bảo đảm tại đó có nút. Với cây thưa, vẫn phải kiểm tra mọi nút trên đường đi thực sự tồn tại.

## 16. Lỗi thường gặp khi dùng công thức chỉ số

1. **Trộn 0-based với 1-based.** Nếu gốc index 0, con trái là \(2i+1\), không phải \(2i\).
2. **Truy cập cha của gốc.** Index 0 không có cha. Trong Python, lấy \(-1\) làm cha có thể âm thầm đọc **phần tử cuối mảng**.
3. **Quên kiểm tra \(2i+1<n\) hoặc \(2i+2<n\).** Công thức trả về **vị trí tiềm năng**, không phải bảo đảm tồn tại nút.
4. **Nhầm \(\text{A}[i]=\text{None}\) với vị trí trống.** Nếu None là giá trị hợp lệ, cần sentinel/cờ occupancy riêng.
5. **Bỏ ô trống giữa mảng rồi tính cha–con theo index mới.** Việc dồn phần tử thay đổi **cấu trúc cây**.
6. **Cho rằng mọi cây nhị phân đều có thể lưu trong đúng \(n\) ô bằng công thức heap.** Chỉ đúng nếu cây có hình dạng **complete** hoặc dùng thêm trường liên kết/định dạng khác.
7. **Nhầm mảng vị trí với danh sách tuần tự hóa BFS.** Token số 3 trong một luồng BFS có null **chưa chắc** tương ứng vị trí cấu trúc số 3.
8. **Dùng \(h=\lfloor\log_2n\rfloor\) cho cây thưa.** Công thức này cần bất biến **complete**, không chỉ cần một mảng chứa nút.
9. **Nhầm full với complete.** Cây full có thể có lỗ ở các vị trí giữa, dù mọi nút trong có hai con.
10. **Cho rằng việc xóa phần tử mảng giữa là xóa một nút hợp lệ.** Dịch các phần tử có thể đổi quan hệ trái/phải của nhiều nút.
11. **Xóa một nút có con nhưng vẫn giữ con tại vị trí cũ.** Khi cha biến mất, sẽ xuất hiện nút mồ côi, vi phạm cấu trúc cây có gốc.
12. **Nhầm giá trị trong heap đã được sắp toàn cục.** Heap chỉ bảo đảm quan hệ cha–con và hình dạng complete, không phải dãy tăng/giảm theo inorder.
13. **Không dự trù ô rỗng của cây thưa.** Một nhánh phải sâu 20 cạnh có thể cần hơn 2 triệu ô dù chỉ có 21 nút.
14. **Không kiểm tra tràn số nguyên khi nhân đôi index.** Trong môi trường số nguyên cố định, \(2i+2\) có thể vượt giới hạn kiểu dữ liệu.
15. **Đánh đồng chi phí truy cập index với tổng chi phí thao tác.** Việc tính \(2i+1\) là \(O(1)\), nhưng chèn để giữ heap-order vẫn có thể \(O(\log n)\), còn mở rộng mảng thưa có thể tốn \(O(M)\).
16. **Duyệt tuyến tính mảng thưa rồi coi số ô là số nút.** Một mảng 6 ô có thể chỉ chứa 3 nút; cần phân biệt \(n\) với \(M\).
17. **Không tách giá trị của nút khỏi định danh nút.** Nếu nhiều nút có cùng giá trị, việc so sánh giá trị không xác định chúng là cùng một nút hoặc cùng vị trí.
18. **Không xác định rõ quy ước vị trí trong API.** Tài liệu phải nói rõ gốc ở 0 hay 1, có cho phép lỗ hay không và cách mã hóa vị trí vắng mặt.

## 17. Bài tập tự kiểm tra kèm lời giải

### Câu 1. Tính cha và con theo 0-based

Một nút có index \(i=14\) trong mảng vị trí từ 0. Tính index cha, con trái và con phải.

**Lời giải:**

\[
\operatorname{parent}(14)=\lfloor(14-1)/2\rfloor=6,
\]

\[
\operatorname{left}(14)=29,\qquad
\operatorname{right}(14)=30.
\]

Nếu mảng chỉ có 15 phần tử thì **cha index 6 tồn tại**, còn hai vị trí con 29 và 30 đều **chưa có nút**.

### Câu 2. Tính cha và con theo 1-based

Trong mảng heap bắt đầu từ index 1, một nút có chỉ số 13. Tính cha, con trái và con phải.

**Lời giải:**

\[
\operatorname{parent}(13)=\lfloor13/2\rfloor=6,
\]

\[
\operatorname{left}(13)=26,\qquad
\operatorname{right}(13)=27.
\]

Lưu ý index **13** theo 1-based không có cùng vị trí cấu trúc với index 13 theo 0-based.

### Câu 3. Tìm lá trong mảng complete

Một cây nhị phân complete có \(n=10\) nút, index từ 0. Các nút trong và lá có chỉ số nào? Chiều cao là bao nhiêu?

**Lời giải:** Với \(n//2=5\), nút trong có index **0–4**, lá có index **5–9**. Số lá \(L=\lceil10/2\rceil=5\). Chiều cao \(h=\lfloor\log_2 10\rfloor=3\) cạnh.

### Câu 4. Con cuối cùng khi thêm vào cây complete

Cho mảng \([A,B,C,D,E,F]\). Khi append nút G, G có index và cha nào? G là con trái hay con phải?

**Lời giải:** G nhận index \(6\). Cha là \((6-1)//2=2\), tức C. Vì index 6 chẵn và lớn hơn 0 nên G là **con phải** của C. Mảng sau thêm là \([A,B,C,D,E,F,G]\).

### Câu 5. Duyệt theo ba cách

Cho mảng complete \([A,B,C,D,E,F]\). Hãy viết thứ tự BFS, preorder, inorder và postorder.

**Lời giải:**

| Phép duyệt | Thứ tự |
| --- | --- |
| BFS | A, B, C, D, E, F |
| Preorder | A, B, D, E, C, F |
| Inorder | D, B, E, A, F, C |
| Postorder | D, E, B, F, C, A |

Đọc tuyến tính mảng tương đương **BFS** ở cây complete, không phải mọi kiểu duyệt.

### Câu 6. Cây thưa cần bao nhiêu ô?

Cây có gốc A, chỉ có con phải B; B chỉ có con trái C. Hãy xác định chỉ số 0-based của A, B, C và số ô tối thiểu trong mảng vị trí trực tiếp.

**Lời giải:** A ở 0, B ở \(2\cdot0+2=2\), C ở \(2\cdot2+1=5\). Mảng cần index từ 0 tới 5, tức **6 ô**:

~~~text
[A, ·, B, ·, ·, C]
~~~

Số nút thực chỉ là **3**. Không được dồn thành \([A,B,C]\) rồi dùng công thức heap nếu cần giữ quan hệ trái/phải ban đầu.

### Câu 7. Danh sách token BFS và index trực tiếp

Một định dạng BFS có null, bỏ null ở cuối, xuất dãy \([A,\text{null},B,C]\). Theo cách giải mã bằng hàng đợi, C là con của ai? Index cấu trúc trực tiếp của C bằng bao nhiêu?

**Lời giải:** A có con trái trống, con phải B. Token C tiếp theo là **con trái của B**. Vì B ở index cấu trúc 2, C phải ở index **5**, **không** phải index 3 như vị trí C trong danh sách token.

### Câu 8. Nhánh phải sâu

Một cây chỉ gồm gốc và các con phải liên tiếp có chiều cao \(h=6\). Cây có bao nhiêu nút? Index của lá sâu nhất là bao nhiêu? Mảng vị trí phải có ít nhất bao nhiêu ô?

**Lời giải:** Cây có \(n=h+1=7\) nút. Index lá sâu nhất là:

\[
i_h=2^{h+1}-2=2^7-2=126.
\]

Do index bắt đầu từ 0, mảng phải chứa **127 ô**. Chỉ 7 trong số đó có nút.

### Câu 9. Full nhưng chưa chắc complete

Cho cây có gốc A, hai con B,C; C có hai con D,E; B là lá. Cây có full không? Complete không? Nếu dùng mảng vị trí trực tiếp, D và E ở đâu?

**Lời giải:** Cây **full** vì các nút trong A và C đều có đúng hai con. Cây **không complete** vì tầng cuối có các vị trí bên trái trống trước D và E. Index: A=0, B=1, C=2, D=5, E=6. Hai ô 3 và 4 **trống**; mảng vị trí phải dài ít nhất 7.

### Câu 10. Hai cách hiểu của None

Một cây complete lưu \([None, "B", "C"]\). Có phải cây chỉ có hai nút không? Phải biểu diễn thế nào để không nhầm lẫn?

**Lời giải:** **Không.** Nếu dùng quy ước **độ dài mảng quyết định các vị trí hiện hữu**, cây có **ba nút**: gốc có giá trị None, con trái B và con phải C. Với cây thưa, nên dùng **MISSING riêng** hoặc bitmap occupancy; None có thể vẫn là payload hợp lệ.

### Câu 11. Tính đường đi từ index

Index 12 trong cách 0-based tương ứng đường nào từ gốc? Hãy kiểm chứng bằng công thức cha.

**Lời giải:** \(12+1=13=(1101)_2\). Bỏ bit 1 đầu được 101, nghĩa là **phải – trái – phải**. Công thức cha cho:

\[
12\rightarrow5\rightarrow2\rightarrow0.
\]

Đảo ngược thành đường từ gốc \(0\rightarrow2\rightarrow5\rightarrow12\), đúng hướng **R–L–R**.

### Câu 12. Chuyển đường đi thành chỉ số

Từ gốc, đi **trái – phải – trái**. Tính index cuối theo công thức 0-based.

**Lời giải:**

\[
0\xrightarrow{L}1
\xrightarrow{R}4
\xrightarrow{L}9.
\]

Vậy index là **9**. Kiểm tra bằng bit: từ gốc \(q=1\), thêm các bit 0,1,0 được \((1010)_2=10\), nên \(i=q-1=9\).

### Câu 13. Chiều cao không tính từ số nút trong cây thưa

Cây thưa có A ở index 0, B ở index 2 và C ở index 5. Số nút \(n\) là bao nhiêu? Chiều cao là bao nhiêu? Vì sao công thức của cây complete không dùng được?

**Lời giải:** Có **3 nút**, C ở độ sâu \(\lfloor\log_2(5+1)\rfloor=2\) nên cây cao **2 cạnh**. Nhưng \(\lfloor\log_2n\rfloor=\lfloor\log_2 3\rfloor=1\). Hai kết quả khác nhau vì các vị trí **không được lấp liên tục từ 0 tới \(n-1\)**; cây không complete.

### Câu 14. Vì sao không xóa phần tử giữa rồi dồn mảng?

Một cây complete là \([A,B,C,D,E,F,G]\). Nếu xóa phần tử B ở index 1 rồi dồn các phần tử sau một ô, cấu trúc có được giữ nguyên không?

**Lời giải:** **Không.** Mảng mới \([A,C,D,E,F,G]\) đặt C ở index 1, khiến C trở thành **con trái của A**, trong khi trước đó C là **con phải**. Các quan hệ khác cũng đổi theo. Xóa một nút bất kỳ cần quy tắc tái cấu trúc cụ thể; không được xem việc dồn mảng là phép xóa “giữ nguyên mọi cạnh”.

### Câu 15. Vận dụng công thức vào max-heap

Cho heap mảng \([90,70,85,20,50,60]\), chèn 95. Mảng sau khi thực hiện sift-up là gì?

**Lời giải:** Append 95 tại index 6:

~~~text
[90, 70, 85, 20, 50, 60, 95]
~~~

Đổi 95 với cha 85 tại index 2, rồi đổi với cha 90 tại index 0:

~~~text
[95, 70, 90, 20, 50, 60, 85]
~~~

Cây vẫn complete vì **vị trí không đổi** trong quá trình sift-up; chỉ các giá trị được hoán đổi. Đường từ lá tới gốc có \(O(\log n)\) cạnh.

### Câu 16. Chọn biểu diễn cho hai bài toán

Ứng dụng X thường thêm/xóa phần tử ưu tiên ở một heap nhị phân. Ứng dụng Y lưu cây cú pháp nhiều nhánh trái/phải thiếu, thường chuyển cây con. Nên dùng loại biểu diễn nào?

**Lời giải:** Với X, **mảng complete** rất phù hợp vì heap duy trì hình dạng complete và cần tính cha/con nhanh. Với Y, **nút liên kết** hoặc **mảng bản ghi có chỉ số con** thường phù hợp hơn vì có nhiều vị trí thiếu và phép di chuyển cây con có thể khiến mảng vị trí trực tiếp rất lãng phí.

### Câu 17. Kiểm tra cấu trúc hợp lệ

Một mảng vị trí ghi A ở index 0, B ở index 6, còn index 2 trống. Đây có phải biểu diễn hợp lệ của một cây có gốc theo công thức 0-based không?

**Lời giải:** **Không.** Cha của index 6 là \((6-1)//2=2\), nhưng index 2 **không có nút**. B đã bị “mồ côi”. Muốn B tồn tại ở index 6, index 2 và mọi tổ tiên trên đường về gốc cũng phải có nút.

### Câu 18. Ước lượng bộ nhớ của cây suy biến

Cây nhánh phải có \(h=20\). Số nút thực và số ô cần trong mảng vị trí là bao nhiêu?

**Lời giải:** \(n=h+1=21\) nút, trong khi:

\[
M=2^{h+1}-1=2^{21}-1=2\,097\,151\text{ ô}.
\]

Hơn hai triệu ô cho 21 nút cho thấy **biểu diễn mảng vị trí đặc không phù hợp với cây rất thưa và sâu**. Dùng nút con trỏ hoặc map theo index sẽ tránh cấp phát các ô vắng mặt.

## 18. Tổng kết và cách chọn biểu diễn

**Trong mảng 0-based**, gốc ở index 0, con trái của \(i\) là \(2i+1\), con phải là \(2i+2\), cha của \(i>0\) là \(\lfloor(i-1)/2\rfloor\). **Trong mảng 1-based**, gốc ở index 1, con trái \(2i\), con phải \(2i+1\), cha \(\lfloor i/2\rfloor\).

Đối với **cây nhị phân complete**, các nút nằm đúng ở index \(0,\ldots,n-1\), nên không cần ô trống giữa mảng:

\[
\boxed{h=\lfloor\log_2n\rfloor,\quad
L=\lceil n/2\rceil,\quad
\text{lá bắt đầu từ index }\lfloor n/2\rfloor.}
\]

Biểu diễn này cho truy cập cha/con bằng **phép tính \(O(1)\)**, duyệt toàn bộ \(O(n)\) và lưu trữ \(O(n)\). Đây là cách phù hợp cho **binary heap**, cùng những cấu trúc luôn duy trì thứ tự lấp vị trí theo tầng.

Với **cây nhị phân bất kỳ**, công thức index vẫn mô tả vị trí trong khung cây nhưng có thể xuất hiện các **lỗ**. Một nhánh phải sâu \(h\) có thể buộc mảng trực tiếp dài tới \(2^{h+1}-1\), dù cây chỉ có \(h+1\) nút. Khi đó, hãy chọn **nút có con trỏ**, **mảng bản ghi lưu left/right index**, hoặc **map theo vị trí**. Đừng nhầm mảng vị trí với một dãy token BFS có cách giải mã null riêng.

**Nguyên tắc thực hành:** Trước khi áp dụng công thức, luôn xác nhận **chỉ số bắt đầu từ 0 hay 1**, **cây có complete không**, **ô trống được biểu diễn thế nào**, **vị trí cha có tồn tại không**, và **phép cập nhật có làm thay đổi hình dạng cây hay không**. Cùng một công thức số học có thể chính xác về vị trí nhưng vẫn gây truy vấn sai nếu bất biến cấu trúc bị vi phạm.

# So sánh B-tree, B+-tree và cây nhị phân cân bằng

**B-tree**, **B+ tree** và **cây tìm kiếm nhị phân cân bằng** (*balanced binary search tree*, thường gặp dưới dạng **AVL tree** hoặc **Red-Black tree**) đều tổ chức khóa theo thứ tự để tìm kiếm hiệu quả. Chúng có thể đạt thời gian tìm kiếm O(log n) trong mô hình bộ nhớ RAM với kích thước nút được xem là hằng số. Tuy nhiên, **cách lưu khóa, số nhánh trên mỗi nút, cách duy trì cân bằng và chi phí truy cập bộ nhớ/lưu trữ** rất khác nhau.

Một cây nhị phân cân bằng thường giữ **một khóa ở một nút**, có tối đa hai liên kết con và sử dụng **phép quay** để giữ chiều cao nhỏ. B-tree giữ **nhiều khóa trên một nút**, có nhiều con và sử dụng **tách, mượn hoặc gộp nút**. Trong mô hình B+ tree phổ biến, **nút trong chỉ giữ khóa phân cách**, còn **mục dữ liệu có thể truy xuất theo khóa nằm ở lá**; các lá thường nối nhau, hỗ trợ quét khoảng.

Lựa chọn giữa chúng không nên chỉ dựa vào ký hiệu O(log n). Với chỉ mục lưu trên SSD, việc đi qua ba trang có thể khác đáng kể việc lần theo hàng chục đối tượng nút nằm rải rác trong bộ nhớ; ngược lại, một AVL tree trong RAM với dữ liệu nhỏ có thể đơn giản và phù hợp hơn một B+ tree phải quản lý trang.

**Mục tiêu học tập:** sau bài này, bạn có thể phân biệt bất biến và nơi lưu mục dữ liệu, mô phỏng đường tìm kiếm, giải thích quy tắc cân bằng của mỗi họ cây, so sánh chi phí truy vấn điểm/khoảng và chọn cấu trúc phù hợp theo môi trường sử dụng.

## 1. Ba cấu trúc cùng giải quyết vấn đề gì?

Giả sử chúng ta cần quản lý một **tập khóa có thứ tự**, với các thao tác:

- `find(x)`: kiểm tra khóa `x` hoặc lấy giá trị gắn với nó.
- `insert(x)`: thêm một khóa mới và giữ cấu trúc hợp lệ.
- `delete(x)`: xóa một khóa mà không phá thứ tự.
- `range(a,b)`: trả các khóa thuộc `[a,b]` theo thứ tự.
- `min()`, `max()`, `predecessor(x)`, `successor(x)`: truy vấn có thứ tự.

Mảng đã sắp cũng cho phép tìm kiếm nhị phân, nhưng **chèn/xóa ở giữa** có thể cần dịch O(n) mục. Cả ba họ cây được so sánh ở đây đều nhằm duy trì **thứ tự động**, cho phép tìm/chèn/xóa mà không phải dồn toàn bộ tập dữ liệu sau mỗi lần cập nhật.

Điều kiện chung là **quy tắc so sánh khóa nhất quán**: khóa được đặt vào cây bằng cách so sánh nào thì khi tìm cũng phải dùng chính quy tắc ấy. Với khóa trùng, mỗi cấu trúc cần có chính sách cụ thể (ghi đè giá trị, bộ đếm, danh sách bản ghi, khóa ghép…), không thể tự suy từ thuật toán dùng khóa phân biệt.

### Các quy ước dùng xuyên suốt bài

Để tránh nhầm lẫn vì tên “bậc” có nhiều định nghĩa:

1. **B-tree:** dùng **bậc tối thiểu `t \ge 2`**; một nút không phải gốc có từ `t-1` đến `2t-1` khóa. Khóa ở nút trong **có thể là khóa dữ liệu thực sự**, và khi tìm thấy tại đó, có thể dừng.
2. **B+ tree:** dùng mô hình **khóa dữ liệu phân biệt ở lá**, separator trong nút trong bằng **khóa nhỏ nhất của cây con ngay bên phải** (`separator=min(right subtree)`). Mọi lá cùng độ sâu và có liên kết `next` theo thứ tự.
3. **Cây nhị phân cân bằng:** mỗi nút giữ một khóa; ta phân tích cả **AVL** (giới hạn chênh lệch chiều cao) và **Red-Black** (các bất biến màu). Đây là **hai thuật toán cân bằng khác nhau** trong cùng họ cây tìm kiếm nhị phân.

Các mô hình B-tree/B+ tree trên đây mang tính học thuật. Cơ sở dữ liệu thật có thể lưu `RID` thay vì cả bản ghi, nén separator, dùng bố cục trang riêng và quy ước mức lấp đầy khác.

## 2. Bức tranh trực quan trên cùng tám khóa

Ta dùng cùng tập khóa:

```text
10, 20, 40, 50, 60, 70, 80, 90
```

### 2.1. B-tree: khóa dữ liệu có thể nằm ở nút trong

Đây là một B-tree hợp lệ với `t=2`:

```text
                             [40 | 70]
                            /    |     \
                      [10,20] [50,60] [80,90]

Gốc có 2 khóa và 3 con.
Các khóa 40 và 70 là khóa dữ liệu nằm ngay tại gốc.
```

Tất cả lá ở độ sâu 1. Gốc có hai khóa thuộc giới hạn 1–3; các lá có hai khóa, cũng thuộc giới hạn. Tìm `70` có thể **kết thúc tại gốc**.

### 2.2. B+ tree: separator ở nút trong, mục dữ liệu ở lá

Với cùng tập khóa:

```text
                             [40 | 70]         (separator)
                            /    |     \
                    [10,20] [40,50,60] [70,80,90]
                       L0       L1          L2

Chuỗi lá:   L0 ------> L1 ------> L2 ------> null
```

Giá trị `40` và `70` xuất hiện ở cả gốc lẫn lá, nhưng ở gốc chúng **chỉ là bản sao khóa định tuyến**. Chỉ có **tám mục dữ liệu tại lá**, không phải mười mục.

Theo quy ước separator là min của nhánh phải:

- `P0` chứa khóa `<40`.
- `P1` chứa khóa `40\le x<70`.
- `P2` chứa khóa `\ge70`.

Tìm `70` **phải đi xuống lá `L2`**, vì mục dữ liệu `70` không nằm tại gốc.

### 2.3. AVL tree: một khóa trên một nút, tối đa hai con

Một cách tổ chức AVL hợp lệ của cùng tám khóa:

```text
                              (50)
                             /    \
                           (20)   (70)
                          /   \   /   \
                       (10) (40)(60) (80)
                                        \
                                        (90)
```

Mỗi nút chứa đúng **một khóa**, mọi khóa bên trái nhỏ hơn nút cha, mọi khóa bên phải lớn hơn. Chiều cao hai cây con của mỗi nút chênh nhau không quá một nên đây là một cấu trúc AVL hợp lệ.

Lá `10`, `40`, `60` và `90` **không cần cùng độ sâu**. Đó là điểm khác với B-tree/B+ tree: AVL kiểm soát **độ lệch chiều cao tại từng nút**, không bắt buộc mọi lá ngang hàng.

### Cùng khóa, đường tìm kiếm khác nhau

| Tìm khóa | B-tree | B+ tree | AVL minh họa |
| --- | --- | --- | --- |
| `70` | Gặp `70` ở gốc, dừng | Gốc chọn `P2` → lá `[70,80,90]` | `50→70`, dừng |
| `60` | Gốc chọn `P1` → lá `[50,60]` | Gốc chọn `P1` → lá `[40,50,60]` | `50→70→60` |
| `65` không có | Gốc → lá `[50,60]` → thất bại | Gốc → lá `[40,50,60]` → thất bại | `50→70→60→null` |

Điểm chung là các nút loại bỏ những miền giá trị không thể chứa khóa cần tìm. Điểm khác là **một nút lọc được bao nhiêu miền** và **nơi có thể trả về mục dữ liệu**.

## 3. So sánh bất biến cốt lõi

| Thuộc tính | B-tree (minimum degree `t`) | B+ tree (quy ước bài) | AVL tree | Red-Black tree |
| --- | --- | --- | --- | --- |
| Khóa trên một nút trong | Nhiều khóa dữ liệu | Nhiều separator | 1 khóa | 1 khóa |
| Số nhánh của nút trong | `k+1` với `k` khóa | `k+1` với `k` separator | Tối đa 2 | Tối đa 2 |
| Dữ liệu gắn với khóa | Có thể ở mọi tầng | Mục dữ liệu tại lá | Tại mỗi nút có khóa | Tại mỗi nút có khóa |
| Thứ tự trong nút | Các khóa tăng | Separator tăng | Một khóa | Một khóa |
| Điều kiện cân bằng | Mọi lá cùng độ sâu và nút đáp ứng mức lấp đầy | Mọi lá cùng độ sâu và điều kiện mức lấp đầy của biến thể | Mọi nút có chênh lệch chiều cao hai con tối đa 1 | Bất biến màu đỏ/đen và black-height |
| Cấu trúc liên kết lá | Không phải đặc điểm cốt lõi | Thường có `next`, có thể `prev` | Không mặc định | Không mặc định |
| Cách sửa khi cập nhật | Tách/mượn/gộp khóa và các con | Tách/mượn/gộp; duy trì separator và liên kết lá | Phép quay và cập nhật chiều cao | Phép quay và đổi màu |

### 3.1. B-tree: giới hạn số khóa và độ sâu lá

Với `t\ge2`:

\[
t-1\le k\le2t-1
\]

áp dụng cho **mọi nút không phải gốc**. Gốc của cây không rỗng có thể chỉ có một khóa, kể cả khi `t` lớn. Nút trong có `k` khóa phải có `k+1` con, từ `t` tới `2t` con nếu không phải gốc. **Tất cả lá cùng độ sâu**.

B-tree không phải cây nhị phân theo định nghĩa số con, vì một nút có thể có nhiều hơn hai nhánh. Các khóa của nút phân chia không gian tìm kiếm thành nhiều khoảng, ví dụ `[20|40|60]` tạo bốn nhánh.

### 3.2. B+ tree: phân tách định tuyến và mục dữ liệu

Với separator tăng `S_0<\cdots<S_{k-1}`, nút trong có `k+1` con. Trong quy ước của bài:

\[
S_i=\minKey(children[i+1]).
\]

Đặc biệt, nếu `x=S_i`, nó được định tuyến sang **con phải**. B+ tree cũng phải cân bằng tất cả lá cùng độ sâu, nhưng **cận lấp đầy chính xác có thể được định nghĩa theo số khóa, số con, số mục hay số byte** tùy biến thể và định dạng trang. Không nên tự áp bộ công thức `t-1..2t-1` của B-tree vào một B+ tree chưa chỉ rõ quy ước.

### 3.3. AVL tree: cân bằng theo chiều cao

Định nghĩa **balance factor** tại nút `v`:

\[
BF(v)=height(v.left)-height(v.right).
\]

AVL yêu cầu:

\[
BF(v)\in\{-1,0,1\}
\]

với **mọi nút**. Nếu chèn hoặc xóa làm điều kiện không đúng, thuật toán sửa bằng các phép quay trái/phải, có thể là quay đơn hoặc quay kép. Các phép quay thay đổi liên kết cha/con nhưng vẫn giữ thứ tự tìm kiếm nhị phân.

AVL bảo đảm chiều cao O(log n) với giới hạn tương đối chặt; **không bắt buộc tất cả lá cùng độ sâu**.

### 3.4. Red-Black tree: cân bằng bằng quy tắc màu

Mỗi nút thật được gán **đỏ** hoặc **đen**. Một mô hình quy tắc chuẩn:

- Gốc là nút đen.
- Các lá NIL/sentinel được coi là đen.
- Một nút đỏ không có con đỏ.
- Mọi đường từ cùng một nút đến một lá NIL hậu duệ chứa **cùng số nút đen** (*black-height*).

Các quy tắc cho phép một số đường dài hơn các đường khác nhưng khống chế chiều cao **O(log n)**. Khi chèn/xóa, thuật toán có thể đổi màu, quay và truyền việc điều chỉnh lên các tổ tiên.

Không thể lấy điều kiện `|BF|\le1` của AVL áp cho Red-Black tree; hai họ có **bất biến khác nhau**, dù cả hai đều thuộc cây tìm kiếm nhị phân cân bằng.

## 4. So sánh đường tìm kiếm một khóa

### B-tree: có thể tìm thấy trước khi tới lá

Giả sử nút hiện tại có dãy khóa `K_0<K_1<\dots<K_{k-1}`. Tìm `lower_bound(x)` — chỉ số đầu tiên có `K_i\ge x`:

1. Nếu `i<k` và `K_i=x`, trả về mục dữ liệu ngay tại nút.
2. Nếu không bằng và nút là lá, kết luận không tìm thấy.
3. Nếu không bằng và là nút trong, đi `children[i]`.

```text
B-tree node: [20 | 40 | 60]
x = 40 -> gặp tại node, dừng.
x = 50 -> lower_bound = 2 -> đi con P2 (40 < x < 60).
```

Với B-tree cổ điển, điều kiện “bằng khóa thì dừng” là hợp lý **khi nút trong thực sự lưu khóa dữ liệu đó**.

### B+ tree: luôn đi tới lá để lấy mục dữ liệu

Với separator `S_i=minKey(children[i+1])`, cần tìm `upper_bound(x)` — chỉ số đầu tiên có `S_i>x` — để chọn con. Nếu `x` bằng separator thì **đi sang phải**, không dừng ở nút trong.

```text
B+ tree internal: [20 | 40 | 60]
x = 40 -> upper_bound = 2 -> đi P2, tiếp tục tới lá.
x = 50 -> upper_bound = 2 -> cũng đi P2.
```

Sau khi tới lá, dùng `lower_bound(x)` để tìm mục dữ liệu có khóa bằng `x`. Đừng đồng nhất khóa phân cách với bản ghi thực.

**Lưu ý:** một số B+ tree dùng ranh giới hoặc separator theo quy ước khác, chẳng hạn khóa lớn nhất nhánh trái. Trong trường hợp đó, điều kiện dấu bằng phải được điều chỉnh. Quy tắc `upper_bound` nói trên là kết quả của **chính quy ước separator=min(right)**.

### Cây tìm kiếm nhị phân cân bằng: một so sánh với khóa nút

```text
bstFind(root, x):
    node = root
    while node != null:
        if x == node.key:
            return FOUND
        else if x < node.key:
            node = node.left
        else:
            node = node.right
    return NOT_FOUND
```

Mỗi bước quyết định **trái hoặc phải**. Bất biến AVL/Red-Black khống chế số bước theo chiều cao O(log n), nhưng chỉ một khóa được kiểm tra trực tiếp ở mỗi nút.

### Bảng so sánh của một lần tìm

| Câu hỏi | B-tree | B+ tree | AVL/Red-Black |
| --- | --- | --- | --- |
| Có thể dừng ở nút trong khi bằng khóa không? | **Có**, theo mô hình bài | **Không**, cần mục ở lá | **Có**, vì mỗi nút là nút dữ liệu |
| Chọn tiếp mấy nhánh? | Một trong `k+1` nhánh | Một trong `k+1` nhánh | Trái hoặc phải |
| Số khóa xét trong một nút | Tối đa `2t-1` theo quy ước | Tùy sức chứa separator/mục | Một khóa |
| Đi sâu trong cây cân bằng | O(log fan-out của n) tầng | O(log fan-out của n) tầng | O(log n) nút |

## 5. Chèn và xóa: tách/gộp khác phép quay

Tất cả các cấu trúc đều phải sửa hình dạng cây sau cập nhật, nhưng **đơn vị sửa** khác nhau.

### 5.1. B-tree: tách nút đầy

Với `t=2`, nút đầy có ba khóa:

```text
Ban đầu:              [10 | 20 | 30]

Tách nút đầy:
                            [20]
                           /    \
                         [10]  [30]
```

Khóa giữa `20` được **đẩy lên cha**. Nếu nút bị tách là nút trong, các con trỏ con cũng phải chia theo đúng khoảng. Khi gốc đầy, tạo **gốc mới**, làm toàn bộ các lá cùng tăng một độ sâu.

Khi xóa, nếu một nút không phải gốc sắp thiếu khóa, có thể **mượn khóa qua cha từ anh em** hoặc **gộp hai nút cùng khóa phân cách**. Nếu gốc trở nên rỗng mà còn một con, nâng con ấy làm gốc mới.

### 5.2. B+ tree: tách lá khác tách nút trong

Với sức chứa lá tối đa ba mục:

```text
Lá sau khi chèn và tạm tràn:
        [10:A | 20:B | 30:C | 40:D]

Tách lá:
        [10:A | 20:B] -> [30:C | 40:D]

Sao chép separator 30 lên cha:
                         [30]
                        /    \
             [10:A,20:B] -> [30:C,40:D]
```

Khóa `30` **vẫn giữ mục dữ liệu `30:C` ở lá phải**. Đây là **copy-up**, khác với việc đẩy hẳn khóa dữ liệu ra khỏi nút khi tách B-tree cổ điển.

Nếu **nút trong** của B+ tree tràn, có thể **push-up** một separator lên cha và chia cả dãy separator lẫn các con; separator được đẩy lên **không cần nằm lại** trong hai nút trong con. Các mục dữ liệu ở lá không bị chuyển lên tầng trong.

Khi xóa, B+ tree ngoài mượn/gộp để phục hồi mức lấp đầy còn phải cập nhật **separator theo khóa nhỏ nhất của cây con phải**, và khi tách/gộp lá phải sửa **`next`/`prev`** nếu có. Cây có thể tìm đúng một khóa nhưng quét khoảng sai nếu liên kết lá bị đứt.

### 5.3. AVL và Red-Black: phép quay

Ví dụ chèn `10`, `20`, `30` liên tiếp vào một cây tìm kiếm nhị phân không cân bằng:

```text
Trước sửa:
   10
     \
      20
        \
         30

Quay trái tại 10:

       20
      /  \
    10    30
```

Phép quay không tạo thêm khóa và không làm mất thứ tự tìm kiếm. **AVL** có thể dùng phép quay để khôi phục chênh lệch chiều cao; **Red-Black** dùng quay kết hợp đổi màu để giữ black-height và quy tắc nút đỏ.

Khác với B-tree/B+ tree, phép quay điển hình sửa một nhóm nhỏ **liên kết giữa các nút nhị phân**, không chia một trang chứa hàng trăm khóa. Tuy nhiên, số nút cần thăm và chi phí di chuyển con trỏ trong RAM còn phụ thuộc bố cục và quản lý bộ nhớ.

| Cập nhật | B-tree | B+ tree | AVL | Red-Black |
| --- | --- | --- | --- | --- |
| Chèn khi nút đích đầy/mất cân bằng | Tách nút đầy | Tách lá/nút trong, đưa separator lên | Quay để giữ `|BF|\le1` | Đổi màu và/hoặc quay |
| Xóa gây thiếu/mất cân bằng | Mượn/gộp, có thể hạ gốc | Mượn/gộp, sửa separator và liên kết lá | Có thể sửa cân bằng dọc nhiều tổ tiên | Đổi màu và/hoặc quay |
| Chiều cao thay đổi | Khi tách gốc hoặc hạ gốc | Khi tách/hạ gốc | Theo các phép cập nhật và quay | Theo các phép cập nhật và quay |
| Bất biến cần giữ | Mức lấp đầy, số con, độ sâu lá | Thêm vai trò separator và chuỗi lá | Chênh lệch chiều cao mỗi nút | Màu, nút đỏ và black-height |

## 6. Truy vấn khoảng: nơi B+ tree thường có lợi thế bố cục

Xét yêu cầu trả các khóa trong `[40,80]` của tập ví dụ:

```text
Kết quả: 40, 50, 60, 70, 80
```

### B-tree: duyệt thứ tự và không bỏ qua khóa ở nút trong

Trong cây `[40|70]`, dữ liệu của khóa 40 và 70 **nằm ở gốc**. Để liệt kê đúng thứ tự, thuật toán phải xen kẽ việc duyệt **cây con** với việc xuất **khóa của chính nút trong**:

```text
                 [40 | 70]
                 /   |    \
              [10,20][50,60][80,90]

Duyệt có chọn lọc cho [40,80]:
  40 (ở gốc)
  50, 60 (con giữa)
  70 (ở gốc)
  80 (con phải)
```

Chi phí trường hợp tốt có thể là O(log n+r) cho `r` mục trả về nếu triển khai duyệt khoảng theo thứ tự và cắt tỉa các nhánh nằm ngoài khoảng. Nhưng trong mô hình mỗi nút là trang lưu trữ, việc đi giữa nút trong và các cây con có thể phức tạp hơn một chuỗi lá nối tiếp.

### B+ tree: tìm lá đầu rồi theo `next`

```text
                  [40 | 70]
                 /    |      \
        [10,20] -> [40,50,60] -> [70,80,90] -> null

Truy vấn [40,80]:
  1. Gốc chọn lá [40,50,60] theo cận dưới 40.
  2. Đọc 40,50,60.
  3. Theo next tới [70,80,90], đọc 70,80.
  4. Gặp 90 > 80, dừng.
```

Cây B+ dùng nút trong để **định vị** rồi dùng **liên kết lá để quét**. Đây là ưu thế bố cục thường được tận dụng trong chỉ mục phân trang, truy vấn `BETWEEN`, duyệt có thứ tự và phân trang theo khóa.

### Cây nhị phân cân bằng: duyệt theo thứ tự có cắt tỉa

Với AVL/Red-Black tree, cần:

1. Tìm vị trí bắt đầu bằng cách đi xuống cây.
2. Đi tới **phần tử kế tiếp theo thứ tự** (*in-order successor*) bằng liên kết cha, ngăn xếp đường đi hoặc một iterator có trạng thái.
3. Dừng khi vượt cận trên.

Một thuật toán duyệt có cắt tỉa có thể đạt **O(log n+r)** trên cây cân bằng, nên **không đúng** nếu nói cây nhị phân cân bằng bắt buộc duyệt O(n) cho mọi truy vấn khoảng. Sự khác biệt nổi bật của B+ tree là **chuỗi lá và tính cục bộ theo trang**, không phải nó là cấu trúc duy nhất hỗ trợ độ phức tạp O(log n+r).

| Tính chất quét khoảng | B-tree | B+ tree | AVL/Red-Black |
| --- | --- | --- | --- |
| Bắt đầu bằng tìm điểm đầu | Có | Có | Có |
| Mục dữ liệu chỉ nằm tại lá | Không theo mô hình B-tree cổ điển | Có theo mô hình bài | Không |
| Liên kết lá để đi tới mục tiếp theo | Không bắt buộc | Thường có `next` | Không bắt buộc |
| Cần xử lý mục ở nút trong khi duyệt | Có thể có | Separator không phải mục trả về | Mỗi nút là một mục |
| Trường hợp điển hình với cây cân bằng | O(log n+r) | O(log n+r) | O(log n+r) |
| Đặc điểm nổi bật | Thứ tự nhiều nhánh | Quét nhiều mục liên tiếp ở các lá | Duyệt theo thứ tự trên các nút nhị phân |

## 7. So sánh độ phức tạp: đừng trộn các mô hình

Gọi:

- `n` là tổng số **khóa dữ liệu thực** (với B+ tree, không cộng separator lặp ở nút trong).
- `M` là số khóa tối đa trong một nút nhiều nhánh; bậc tối thiểu hoặc sức chứa trang quyết định `M`.
- `F` là số nhánh hiệu dụng của nút trong, với B-tree/B+ tree được duy trì mức lấp đầy.
- `h` là số cạnh từ gốc đến lá.
- `r` là số mục cần trả trong truy vấn khoảng.

Với B-tree/B+ tree cân bằng và các ràng buộc lấp đầy phù hợp, chiều cao theo fan-out có bậc:

\[
h=O(\log_F n).
\]

Với AVL/Red-Black tree, mỗi nút có tối đa hai con và bất biến cân bằng bảo đảm:

\[
h=O(\log n).
\]

### 7.1. Chi phí CPU bên trong một nút nhiều nhánh

Một nút chứa `k` khóa hoặc separator:

- Tìm tuyến tính: O(k) phép so sánh, tối đa O(M).
- Tìm nhị phân: O(log(`k+1`)) phép so sánh, tối đa O(log M).

Vì vậy, trên một đường đi:

| Cấu trúc | Chi phí trên một nút | Số tầng | Tổng chi phí tìm kiếm (ước lượng) |
| --- | --- | --- | --- |
| B-tree/B+ tree, quét tuyến tính | O(M) | O(log_F n) | O(M log_F n) |
| B-tree/B+ tree, tìm nhị phân trong nút | O(log M) | O(log_F n) | O(log M · log_F n) |
| AVL/Red-Black | O(1) so sánh khóa/nút | O(log n) | O(log n) |

Nếu `M` và `F` là các hằng số cố định theo cấu hình cây, cả ba cách đều có tìm kiếm **O(log n)**. Khi `M` lớn, phép so sánh, việc di chuyển byte và truy cập cache trong một nút không còn là yếu tố có thể bỏ qua.

### 7.2. Bảng thao tác với kích thước nút cố định

| Thao tác | B-tree | B+ tree | AVL | Red-Black |
| --- | --- | --- | --- | --- |
| Tìm chính xác | O(log n) | O(log n) | O(log n) | O(log n) |
| Chèn | O(log n) | O(log n) | O(log n) | O(log n) |
| Xóa | O(log n) | O(log n) | O(log n) | O(log n) |
| Truy vấn khoảng trả `r` mục | O(log n+r) khi duyệt có cắt tỉa | O(log n+r) khi quét lá | O(log n+r) với iterator có thứ tự | O(log n+r) với iterator có thứ tự |
| Tìm min/max | O(log n) trường hợp xấu | O(log n), hoặc O(1) nếu lưu sẵn lá biên | O(log n) | O(log n) |

Đây là **bảng Big-O theo RAM**, không phải bảng xếp hạng tốc độ thực tế. Một phép tra cứu trên nhiều trang có thể bị giới hạn bởi I/O; cùng thuật toán tìm kiếm trong RAM có thể bị giới hạn bởi cache miss CPU.

### 7.3. Số tầng có thể nhỏ hơn rất nhiều trong cây nhiều nhánh

Ví dụ giả định chỉ mục có `n=10\,000\,000` mục, trang 4 KiB, sức chứa lá xấp xỉ **98 mục thực tế**, và nút trong cho khoảng **142 con** ở mức gần đầy. Một phép ước lượng lạc quan:

```text
10.000.000 mục
    -> 102.041 trang lá
    ->     719 trang cha
    ->       6 trang cha
    ->       1 trang gốc

Đường từ gốc đến lá: khoảng 4 trang logic.
```

Một cây nhị phân **hoàn toàn cân bằng lý tưởng** có khoảng `log_2(10\,000\,000)\approx23.25` tầng cạnh ở mức lá sâu nhất, tương đương **khoảng 24 nút trên đường dài nhất** nếu hình dạng gần đầy. AVL và Red-Black vẫn có chiều cao O(log n), nhưng hằng số và hình dạng cụ thể có thể khác cây nhị phân lý tưởng.

**Không kết luận “4 I/O so với 24 I/O” từ hình vẽ.** Trong RAM, các nút nhị phân có thể nằm sẵn trong cache; còn trong B+ tree, một số hoặc toàn bộ trang trên đường tìm cũng có thể được cache. Hơn nữa, số tầng bốn trong ví dụ phụ thuộc giả định kích thước trang, mức đầy và fan-out, không phải bảo đảm cho mọi B+ tree.

## 8. Bộ nhớ RAM, cache và trang lưu trữ

### 8.1. B-tree/B+ tree khi lưu theo trang

Giả sử mỗi nút chiếm một trang, ví dụ 4 KiB. Một lượt đọc trang đưa vào RAM:

- **Nhiều khóa phân cách** để chọn giữa rất nhiều nhánh.
- Có thể cả **hàng chục hoặc hàng trăm mục ở lá**, tùy kích thước mục.
- Một số metadata và phần trống dự phòng.

Lợi ích là **ít tầng hơn** và truy cập tập trung vào một trang mỗi tầng. Nhưng nếu chỉ muốn một khóa đơn lẻ, hệ thống có thể đọc nhiều byte trang **không dùng hết**.

Với B+ tree, nút trong chỉ giữ separator và con trỏ nên thường có fan-out lớn; lá có liên kết cho truy vấn khoảng. B-tree có thể cho phép kết thúc sớm khi khóa nằm ở nút trong, nhưng nó có thể phải dành nhiều chỗ hơn cho dữ liệu gắn với khóa tại các tầng trong.

### 8.2. Cây nhị phân cân bằng trong RAM

Một nút nhị phân thường giữ:

```text
key | value/reference | left pointer | right pointer
    | parent pointer (tùy cách cài) | height/color metadata
```

Nếu các nút được cấp phát riêng lẻ, đường đi có thể lần theo nhiều con trỏ đến các vị trí bộ nhớ khác nhau. Điều này có nguy cơ gây **cache miss** và **pointer chasing**, nhưng không phải lúc nào cũng nghiêm trọng: allocator, kiểu khóa, dữ liệu nhỏ và cách bố trí nút có thể cải thiện tính cục bộ.

Một AVL/Red-Black tree tổ chức dữ liệu trong RAM có thể thuận lợi khi:

- Cần cài đặt đơn giản cho tập dữ liệu vừa.
- Không dùng một cơ chế lưu trang đĩa.
- Mỗi lần cập nhật thao tác trên các nút nhỏ.
- Thư viện sẵn có cung cấp iterator, `lower_bound` và bảo đảm thời gian phù hợp.

### 8.3. So sánh bố cục theo trường hợp

| Yếu tố | B-tree/B+ tree dạng trang | AVL/Red-Black với nút riêng lẻ |
| --- | --- | --- |
| Đơn vị truy cập thường dùng | Trang nhiều khóa | Nút một khóa |
| Số tầng lý thuyết | Ít hơn nếu fan-out lớn | Nhiều hơn, nhưng O(log n) |
| Tính cục bộ trong một nút | Tốt nếu khóa xếp gọn trong trang | Không có nhiều khóa trong một nút |
| Đi giữa các nút | Page ID hoặc tham chiếu nút | Con trỏ trái/phải |
| Lợi ích cho chỉ mục đĩa | Thường rõ rệt | Không phải lựa chọn mặc định cho chỉ mục phân trang lớn |
| Chi phí byte đọc thừa | Có thể đáng kể với truy vấn điểm | Phụ thuộc kích thước nút và cache line |
| Quét dữ liệu liên tiếp | B+ tree thường mạnh nhờ chuỗi lá | Có thể dùng in-order iterator, không nhất thiết tuần tự trong bộ nhớ |

Không có cấu trúc nào **luôn thắng** trong mọi môi trường; tính phù hợp phụ thuộc thiết bị lưu trữ, kích thước tập dữ liệu và tỷ lệ truy vấn.

## 9. Java minh họa cùng một phép tìm và một phép quét

Chương trình Java dưới đây **không xây dựng toàn bộ thuật toán chèn/xóa** của ba họ cây. Nó dựng ba cây nhỏ hợp lệ với cùng tám khóa để tập trung vào **quy tắc tìm kiếm và vị trí chứa dữ liệu**. Với B+ tree, các bản ghi chỉ ở lá và có liên kết `next`; với B-tree, khóa dữ liệu có thể nằm ở nút trong; với AVL, mỗi nút có một khóa.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class OrderedTreeComparisonDemo {
    // B-tree: khóa dữ liệu có thể nằm cả ở nút trong.
    static final class BNode {
        final int[] keys;
        final BNode[] children;

        BNode(int[] keys, BNode... children) {
            this.keys = keys.clone();
            this.children = children.clone();
        }

        boolean isLeaf() {
            return children.length == 0;
        }
    }

    // B+ tree: chỉ lá có mục dữ liệu.
    static final class PlusLeaf {
        final int[] keys;
        final String[] values;
        PlusLeaf next;

        PlusLeaf(int... keys) {
            this.keys = keys.clone();
            this.values = new String[keys.length];
            for (int i = 0; i < keys.length; i++) {
                this.values[i] = "V" + keys[i];
            }
        }
    }

    static final class PlusRoot {
        final int[] separators;
        final PlusLeaf[] children;

        PlusRoot(int[] separators, PlusLeaf... children) {
            if (children.length != separators.length + 1) {
                throw new IllegalArgumentException("Need k+1 children");
            }
            this.separators = separators.clone();
            this.children = children.clone();
        }
    }

    // Nút BST; hình dạng dựng bên dưới thỏa cân bằng AVL.
    static final class BinaryNode {
        final int key;
        final BinaryNode left;
        final BinaryNode right;

        BinaryNode(int key, BinaryNode left, BinaryNode right) {
            this.key = key;
            this.left = left;
            this.right = right;
        }
    }

    static int lowerBound(int[] a, int x) {
        int lo = 0, hi = a.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (a[mid] < x) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo; // chỉ số đầu tiên có a[i] >= x
    }

    static int upperBound(int[] a, int x) {
        int lo = 0, hi = a.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (a[mid] <= x) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo; // chỉ số đầu tiên có a[i] > x
    }

    static boolean findBTree(BNode root, int target) {
        BNode node = root;
        while (node != null) {
            int i = lowerBound(node.keys, target);
            if (i < node.keys.length && node.keys[i] == target) {
                return true; // có thể dừng ở nút trong
            }
            if (node.isLeaf()) {
                return false;
            }
            node = node.children[i];
        }
        return false;
    }

    static String findBPlus(PlusRoot root, int target) {
        if (root == null) {
            return null;
        }
        // Mô hình hai tầng: gốc trong và các lá.
        int child = upperBound(root.separators, target);
        PlusLeaf leaf = root.children[child];
        int i = lowerBound(leaf.keys, target);
        if (i < leaf.keys.length && leaf.keys[i] == target) {
            return leaf.values[i]; // mục dữ liệu chỉ ở lá
        }
        return null;
    }

    static boolean findBinary(BinaryNode root, int target) {
        BinaryNode node = root;
        while (node != null) {
            if (target == node.key) {
                return true;
            }
            node = target < node.key ? node.left : node.right;
        }
        return false;
    }

    static List<Integer> rangeBPlus(PlusRoot root, int a, int b) {
        List<Integer> result = new ArrayList<>();
        if (root == null || a > b) {
            return result;
        }
        PlusLeaf leaf = root.children[upperBound(root.separators, a)];
        int pos = lowerBound(leaf.keys, a);
        while (leaf != null) {
            while (pos < leaf.keys.length) {
                int key = leaf.keys[pos++];
                if (key > b) {
                    return result;
                }
                result.add(key);
            }
            leaf = leaf.next;
            pos = 0;
        }
        return result;
    }

    static void rangeBinary(BinaryNode node, int a, int b,
                            List<Integer> result) {
        if (node == null) {
            return;
        }
        if (a < node.key) {
            rangeBinary(node.left, a, b, result);
        }
        if (a <= node.key && node.key <= b) {
            result.add(node.key);
        }
        if (node.key < b) {
            rangeBinary(node.right, a, b, result);
        }
    }

    static BNode makeBTree() {
        return new BNode(new int[] {40, 70},
            new BNode(new int[] {10, 20}),
            new BNode(new int[] {50, 60}),
            new BNode(new int[] {80, 90}));
    }

    static PlusRoot makeBPlus() {
        PlusLeaf left = new PlusLeaf(10, 20);
        PlusLeaf middle = new PlusLeaf(40, 50, 60);
        PlusLeaf right = new PlusLeaf(70, 80, 90);
        left.next = middle;
        middle.next = right;
        return new PlusRoot(new int[] {40, 70},
            left, middle, right);
    }

    static BinaryNode makeAVLShape() {
        return new BinaryNode(50,
            new BinaryNode(20,
                new BinaryNode(10, null, null),
                new BinaryNode(40, null, null)),
            new BinaryNode(70,
                new BinaryNode(60, null, null),
                new BinaryNode(80, null,
                    new BinaryNode(90, null, null))));
    }

    public static void main(String[] args) {
        BNode bt = makeBTree();
        PlusRoot bp = makeBPlus();
        BinaryNode avl = makeAVLShape();

        System.out.println("B-tree contains 70: "
            + findBTree(bt, 70));
        System.out.println("B+ tree get 70: "
            + findBPlus(bp, 70));
        System.out.println("AVL contains 70: "
            + findBinary(avl, 70));
        System.out.println("B+ tree get 65: "
            + findBPlus(bp, 65));
        System.out.println("B+ range [40,80]: "
            + rangeBPlus(bp, 40, 80));

        List<Integer> bstRange = new ArrayList<>();
        rangeBinary(avl, 40, 80, bstRange);
        System.out.println("AVL range [40,80]: " + bstRange);
    }
}
```

Đầu ra dự kiến:

```text
B-tree contains 70: true
B+ tree get 70: V70
AVL contains 70: true
B+ tree get 65: null
B+ range [40,80]: [40, 50, 60, 70, 80]
AVL range [40,80]: [40, 50, 60, 70, 80]
```

### Những điểm nên quan sát trong mã

1. `findBTree` dùng `lowerBound` rồi **kiểm tra bằng khóa** trước khi đi con: khóa `70` được tìm tại gốc.
2. `findBPlus` dùng `upperBound` trên separator `[40,70]`, rồi dùng `lowerBound` ở **lá**: khóa bằng separator thuộc cây con phải.
3. `findBinary` chỉ so sánh **một khóa tại mỗi nút** và chọn trái hoặc phải.
4. `rangeBPlus` dùng `next` để chuyển lá, không tìm lại từ gốc khi đọc hết một lá.
5. `rangeBinary` chỉ đệ quy vào những nhánh có thể chứa khóa thuộc khoảng, vẫn trả theo thứ tự tăng.

**Phạm vi của ví dụ:** B+ tree Java chỉ mô hình hóa **một nút trong làm gốc cùng các lá**, không phải một bộ chèn/xóa B+ tree nhiều tầng. Cây nhị phân được dựng sẵn với **hình dạng AVL hợp lệ**, nhưng mã không cài đặt các phép quay AVL/Red-Black. Các hàm được xây để minh họa **đường tìm và quét**, không chứng minh một thư viện cân bằng hoàn chỉnh.

## 10. Chọn cấu trúc cho từng loại ứng dụng

Không có đáp án chung cho mọi bài toán. Các câu hỏi hữu ích trước khi chọn là:

1. **Dữ liệu chủ yếu nằm trong RAM hay trên thiết bị lưu trữ phân trang?**
2. **Truy vấn điểm nhiều hơn hay truy vấn khoảng/duyệt có thứ tự nhiều hơn?**
3. **Khóa dài bao nhiêu, giá trị có lớn không, lá chỉ chứa `RID` hay cả bản ghi?**
4. **Tập dữ liệu có thay đổi thường xuyên không? Chèn có theo thứ tự tăng hay phân tán ngẫu nhiên?**
5. **Có cần thao tác đồng thời, khôi phục sau sự cố và tính bền vững không?**

### Bảng định hướng lựa chọn

| Nhu cầu | Lựa chọn đáng cân nhắc | Lý do |
| --- | --- | --- |
| Chỉ mục cơ sở dữ liệu lớn trên SSD/HDD, nhiều truy vấn điểm và khoảng | **B+ tree** | Nút trong có fan-out lớn; mục ở lá và chuỗi lá thuận lợi cho quét khoảng |
| Chỉ mục đa nhánh mà bản ghi/giá trị có thể nằm ở cả các tầng | **B-tree** | Tìm có thể kết thúc ở nút trong; cấu trúc vẫn có số tầng thấp khi fan-out lớn |
| Tập khóa có thứ tự ở RAM, dùng API map/set tiêu chuẩn | **AVL hoặc Red-Black** | Nút nhỏ, tra cứu/chèn/xóa O(log n), nhiều thư viện hỗ trợ iterator |
| Tìm kiếm rất nhạy với chiều cao, đọc điểm thường xuyên trong RAM | **AVL** có thể phù hợp | Cân bằng chiều cao chặt hơn; đánh đổi với công sửa cân bằng |
| Tập khóa trong RAM có cập nhật động dày đặc | **Red-Black** là ứng viên phổ biến | Cân bằng theo màu, đảm bảo O(log n), thường được dùng trong ordered containers |
| Quét một dải khóa dài trên dữ liệu lưu theo trang | **B+ tree** thường có lợi thế | Định vị lá đầu, quét chuỗi lá liên tiếp |
| Chỉ tìm chính xác, không cần thứ tự hay truy vấn khoảng | Xem xét **bảng băm** ngoài ba cấu trúc | Có thể đạt O(1) trung bình theo khóa trong điều kiện phù hợp |
| Dữ liệu không đổi, đã sắp, chủ yếu đọc | Xem xét **mảng đã sắp** | Tìm nhị phân và quét liên tiếp rất đơn giản, cục bộ bộ nhớ tốt |

### Vì sao bảng này không phải một bảng xếp hạng tốc độ?

Một thư viện ordered map dựa trên Red-Black tree có thể nhanh hơn một B+ tree viết chưa tối ưu trong RAM; một B+ tree đã nén khóa và có buffer pool tốt có thể phù hợp hơn khi dữ liệu nằm trên đĩa. **API, cách cấp phát bộ nhớ, độ dài khóa và thiết bị lưu trữ** có thể quan trọng hơn chênh lệch Big-O ở cùng bậc.

Với lựa chọn cho hệ thống thật, nên thử nghiệm các workload đại diện và đo:

- **Point lookup:** độ trễ trung vị và p95/p99, cache hit/miss.
- **Range scan:** thông lượng mục/giây, số trang/byte được đọc.
- **Updates:** số lần tách/gộp/quay, số trang dirty và lượng log nếu có lưu trữ bền vững.
- **Bộ nhớ:** dung lượng chỉ mục, số nút và mức dư thừa.

## 11. Các ngộ nhận cần tránh

1. **“B-tree là cây nhị phân có khóa lớn hơn.”** Không. B-tree là cây **nhiều nhánh**, nút trong có thể có `k+1` con.
2. **“B+ tree không chứa khóa ở nút trong.”** Sai. Nó chứa **separator**, chỉ không giữ mục dữ liệu theo mô hình bài.
3. **“Gặp khóa bằng separator trong B+ tree thì tìm xong.”** Sai. Cần xuống lá để lấy mục dữ liệu.
4. **“B+ tree có nhiều khóa hơn B-tree vì separator xuất hiện ở cả gốc và lá.”** Separator không phải mục dữ liệu; không được cộng bản sao vào số bản ghi.
5. **“Tất cả lá của AVL cũng phải cùng độ sâu như B-tree.”** Sai. AVL chỉ yêu cầu chênh lệch chiều cao của hai con tại từng nút tối đa một.
6. **“AVL và Red-Black có cùng bất biến cân bằng.”** Sai. AVL dựa vào chiều cao; Red-Black dựa vào màu và black-height.
7. **“Quay cây nhị phân giống tách một nút B-tree.”** Sai. Quay thay liên kết giữa vài nút, còn tách phân phối nhiều khóa và con.
8. **“Tách lá B+ tree phải đưa hẳn khóa đầu lá phải ra khỏi lá.”** Sai. Separator được **sao chép**, mục dữ liệu vẫn ở lá.
9. **“B-tree luôn tìm nhanh hơn B+ tree vì có thể dừng ở nút trong.”** Không. Còn phụ thuộc số tầng, fan-out, cache và phần dữ liệu lưu ở nút.
10. **“B+ tree là cấu trúc duy nhất hỗ trợ O(log n+r) cho truy vấn khoảng.”** Sai. Cây tìm kiếm nhị phân cân bằng cũng có thể đạt bậc này với iterator phù hợp.
11. **“Mỗi nút trên đường tìm tương ứng một I/O đĩa.”** Không. Cache có thể giữ toàn bộ hoặc một phần các nút/trang.
12. **“B-tree/B+ tree luôn dùng ít RAM hơn cây nhị phân.”** Không có bảo đảm chung; còn phụ thuộc trang trống, con trỏ, separator và payload.
13. **“B-tree có độ cao O(log_F n) nên CPU luôn O(log_F n).”** Xử lý bên trong nút còn có các phép so sánh, dịch mảng và chi phí dữ liệu.
14. **“B+ tree luôn giữ toàn bộ bản ghi thật ở lá.”** Lá có thể giữ `RID` hoặc tham chiếu tới dữ liệu ở ngoài chỉ mục.
15. **“Red-Black tree có chiều cao đúng bằng AVL.”** Hai họ cùng O(log n), nhưng độ chặt và hằng số có thể khác.
16. **“Truy vấn khoảng trên B-tree không thể tối ưu.”** B-tree vẫn hỗ trợ duyệt có thứ tự và cắt tỉa nhánh; khác biệt là cách bố trí dữ liệu và liên kết.
17. **“Khóa trùng được tự động xử lý như nhau ở mọi cây.”** Cần chính sách riêng cho từng cấu trúc và API.
18. **“Cứ có nhiều nhánh là tốt nhất trên RAM.”** Nút lớn có thể gây đọc byte thừa và chi phí tìm trong nút; phải đo với dữ liệu thật.

## 12. Tự kiểm tra

**Câu 1.** Cây B-tree có bậc tối thiểu `t=3`. Nút không phải gốc được chứa bao nhiêu khóa?

**Đáp án:** Từ `t-1=2` tới `2t-1=5` khóa.

**Câu 2.** Một nút trong B-tree hoặc B+ tree chứa bốn khóa/separator thì cần bao nhiêu con nếu không phải lá?

**Đáp án:** Năm con, vì `k` khóa/separator chia miền tìm kiếm thành `k+1` khoảng.

**Câu 3.** Với B-tree minh họa có gốc `[40,70]`, tìm `70` kết thúc ở đâu?

**Đáp án:** Ngay tại gốc, vì khóa dữ liệu 70 nằm ở nút trong của B-tree theo mô hình bài.

**Câu 4.** Với B+ tree có gốc separator `[40,70]`, tìm `70` theo quy ước min của nhánh phải chọn con nào?

**Đáp án:** Chọn `P2` (con thứ ba); sau đó tìm mục 70 tại lá phải `[70,80,90]`.

**Câu 5.** Vì sao B+ tree có thể lặp giá trị khóa 40 ở gốc và lá mà không có hai bản ghi 40?

**Đáp án:** 40 ở gốc chỉ là separator; mục dữ liệu thật có khóa 40 nằm ở lá.

**Câu 6.** Tại sao tất cả lá của B-tree/B+ tree phải cùng độ sâu, còn lá của AVL không nhất thiết như vậy?

**Đáp án:** B-tree/B+ tree duy trì cân bằng theo tầng của mọi lá. AVL cân bằng cục bộ bằng giới hạn chênh lệch chiều cao hai con tại mỗi nút.

**Câu 7.** Khi thêm `10,20,30` khiến cây nhị phân lệch phải, phép sửa AVL đơn giản là gì?

**Đáp án:** Quay trái tại 10, đưa 20 lên làm gốc của phần cây với hai con 10 và 30.

**Câu 8.** Khi tách một lá B+ tree, separator đưa lên cha có làm mất mục dữ liệu tương ứng ở lá không?

**Đáp án:** Không. Đây là `copy-up`: giá trị khóa được sao chép lên cha nhưng mục dữ liệu vẫn ở lá.

**Câu 9.** Vì sao tách một nút trong B+ tree phải chia cả con trỏ con, không chỉ chia separator?

**Đáp án:** Mỗi nút trong có số con bằng số separator cộng một, và từng con phải giữ đúng khoảng khóa.

**Câu 10.** Điều kiện cân bằng cơ bản của AVL và Red-Black khác nhau thế nào?

**Đáp án:** AVL giới hạn `|height(left)-height(right)|\le1` tại mọi nút. Red-Black dùng màu đỏ/đen, không có cạnh đỏ–đỏ và giữ cùng black-height trên các đường tới NIL.

**Câu 11.** Một B+ tree có lá nối nhau theo `next`. Truy vấn `[40,80]` hoạt động thế nào?

**Đáp án:** Tìm lá chứa vị trí bắt đầu 40 từ gốc, đọc mục tới hết lá, rồi theo `next` cho tới khi gặp khóa lớn hơn 80.

**Câu 12.** Cây AVL/Red-Black có đạt O(log n+r) cho truy vấn khoảng trả `r` mục không?

**Đáp án:** Có, nếu triển khai iterator/duyệt theo thứ tự có cắt tỉa đúng. B+ tree có thêm lợi thế bố cục liên kết lá cho dữ liệu phân trang.

**Câu 13.** Vì sao không nên tuyên bố B+ tree luôn nhanh hơn B-tree cho tìm chính xác?

**Đáp án:** B-tree có thể dừng ở nút trong, nhưng hiệu năng còn phụ thuộc fan-out, cache, kích thước dữ liệu/nút và cách bố trí trang.

**Câu 14.** Fan-out tối đa có nghĩa gì khi một nút trong chứa `k_{\max}` separator?

**Đáp án:** Số con tối đa của nút trong, bằng `k_{\max}+1`.

**Câu 15.** Với cây nhiều nhánh có fan-out hiệu dụng `F`, số tầng được mô tả thế nào?

**Đáp án:** O(log_F n) dưới điều kiện cân bằng và mức lấp đầy phù hợp. Sức chứa tối đa một nút không tự động bằng fan-out thực tế.

**Câu 16.** Một đường tìm đi qua bốn trang B+ tree nhưng ba trang trên đã ở RAM. Có thể có bao nhiêu lần nạp trang từ lưu trữ?

**Đáp án:** Có thể chỉ một lần cho lá chưa ở RAM, hoặc không lần nào nếu lá cũng đã cache. Không được đồng nhất bốn nút với bốn lần đọc đĩa.

**Câu 17.** Nếu chỉ cần tìm khóa chính xác mà không cần thứ tự, còn cấu trúc nào nên so sánh với ba họ cây?

**Đáp án:** Bảng băm, vì tra cứu chính xác có thể đạt O(1) trung bình với hàm băm và hệ số tải phù hợp, nhưng không trực tiếp cung cấp thứ tự khóa.

**Câu 18.** Vì sao B+ tree thường được chọn cho chỉ mục hỗ trợ nhiều truy vấn khoảng trên lưu trữ phân trang?

**Đáp án:** Nút trong có fan-out cao để tìm nhanh lá bắt đầu; các mục ở lá được sắp và lá nối nhau, thuận tiện quét nhiều mục liên tiếp.

**Câu 19.** Khi nào AVL/Red-Black tree có thể là lựa chọn hợp lý hơn B+ tree?

**Đáp án:** Khi cần tập/map có thứ tự chủ yếu trong RAM, kích thước vừa, không cần quản lý trang lưu trữ, và có thư viện cân bằng sẵn có phù hợp.

**Câu 20.** Ba thông số thực tế nên đo trước khi kết luận cấu trúc nào nhanh hơn là gì?

**Đáp án:** Ví dụ độ trễ truy vấn (p50/p95), cache miss/I/O và thông lượng dưới tỷ lệ tìm/chèn/xóa/quét khoảng đại diện; cũng nên xét dung lượng chỉ mục.

**Điểm ghi nhớ:** **B-tree** giữ nhiều khóa dữ liệu trên một nút, có thể tìm thấy ở nút trong; **B+ tree** dùng nút trong để định tuyến, giữ mục dữ liệu ở lá và thường liên kết các lá để quét khoảng; **AVL/Red-Black** giữ một khóa trên mỗi nút nhị phân và dùng phép quay (kèm quy tắc chiều cao hoặc màu) để cân bằng. Cả ba có thể hỗ trợ tìm/chèn/xóa O(log n) trong mô hình phù hợp. Hãy chọn dựa trên **nơi lưu dữ liệu, kiểu truy vấn, chi phí I/O/cache, tần suất cập nhật và yêu cầu thư viện**, chứ không dựa vào một dòng Big-O.

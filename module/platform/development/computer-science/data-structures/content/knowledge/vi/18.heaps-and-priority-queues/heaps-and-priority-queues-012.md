# Heap Fibonacci, cập nhật lười và bảo đảm khấu hao

## 1. Vì sao heap Fibonacci được thiết kế?

Một **hàng đợi ưu tiên** (*priority queue*) cần quản lý một tập đối tượng có khóa ưu tiên. Trong **min-priority queue**, khóa nhỏ nhất được lấy trước. Những thao tác cơ bản gồm:

- `insert(x)`: thêm một đối tượng.
- `find-min()`: xem phần tử có khóa nhỏ nhất.
- `extract-min()`: lấy và xóa một phần tử có khóa nhỏ nhất.
- `decrease-key(x, new_key)`: giảm khóa của một phần tử **đã biết**.
- `meld(H1,H2)`: gộp hai hàng đợi ưu tiên thành một.
- `delete(x)`: xóa một phần tử **đã biết**.

Với binary min-heap biểu diễn bằng mảng, thêm mới, lấy gốc và giảm khóa tại vị trí đã biết đều có cận `O(\log n)` trong trường hợp xấu nhất. Điều đó tốt trong rất nhiều ứng dụng, nhưng có những thuật toán cần **rất nhiều lần giảm khóa** so với số lần lấy gốc, chẳng hạn một số cách triển khai thuật toán đồ thị.

**Heap Fibonacci** (*Fibonacci heap*) đánh đổi cách tổ chức dữ liệu để các thao tác thường xuyên trở nên rất rẻ **khi xét trên cả chuỗi thao tác**:

| Thao tác trên Fibonacci min-heap | Thời gian **khấu hao** điển hình |
|---|---|
| Thêm một nút `insert` | `O(1)` |
| Xem nhỏ nhất `find-min` | `O(1)` |
| Gộp hai heap `meld` | `O(1)` |
| Giảm khóa nút đã biết `decrease-key` | `O(1)` |
| Lấy và xóa nhỏ nhất `extract-min` | `O(\log n)` |
| Xóa một nút đã biết `delete` | `O(\log n)` |

Điểm nổi bật là **`decrease-key` chỉ `O(1)` khấu hao**, chứ không phải `O(1)` trường hợp xấu nhất của mỗi lần gọi. Để đạt điều này, Fibonacci heap **trì hoãn** việc gom các cây thành hình dạng gọn cho tới khi cần lấy gốc.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả Fibonacci heap là một **rừng cây có thứ tự heap**, không phải một cây nhị phân hoàn chỉnh.
2. Giải thích danh sách gốc, con trỏ `min`, bậc `degree` và cờ `mark`.
3. Mô phỏng `insert`, `meld`, `find-min`, `extract-min` và **hợp nhất theo bậc** (*consolidation*).
4. Hiểu `decrease-key`, **cut** và **cascading cut** (cắt dây chuyền).
5. Phân biệt **cập nhật cấu trúc lười** với **lazy deletion** tạo bản ghi lỗi thời trong heap khác.
6. Phát biểu hàm thế năng `\Phi(H)=t(H)+2m(H)` và giải thích các cận khấu hao.
7. Hiểu vai trò của dãy Fibonacci trong cận `O(\log n)` cho **bậc lớn nhất** của một nút.
8. Phân tích nhu cầu có **handle tới nút**, đánh đổi bộ nhớ và khả năng dùng heap Fibonacci trong thuật toán đồ thị.

Đây là bài của chương **Heap và hàng đợi ưu tiên** trong học phần **Cấu trúc dữ liệu**. Tư duy về bất biến, chi phí thời gian và bộ nhớ ở đây giúp hiểu cách chọn giữa mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Tư tưởng cốt lõi: trì hoãn công việc cho tới khi thật sự cần

Heap nhị phân cố duy trì **một cây hoàn chỉnh** sau mỗi lần thêm hoặc xóa. Fibonacci heap không làm vậy.

Thay vào đó, nó giữ **nhiều cây** trong một rừng:

```text
Danh sách các gốc:

        [3] <----> [7] <----> [2] <----> [9]
         |                    |
       [11]                [5] [8]
                            |
                           [13]

Con trỏ min -----------> [2]
```

Các cây riêng lẻ thỏa **min-heap-order**: khóa của mỗi cha không lớn hơn khóa của các con. Tuy nhiên:

- Các **gốc không cần sắp theo khóa**.
- Cây không bắt buộc hoàn chỉnh hoặc cân bằng.
- Số cây có thể tăng sau nhiều lần thêm.
- Fibonacci heap giữ **con trỏ trực tiếp tới gốc nhỏ nhất**.

Vì vậy, khi thêm nút mới, ta có thể đặt nó thành **một cây riêng có một nút**, nối vào danh sách gốc và cập nhật `min` nếu cần. Không có lý do phải ghép cây ngay tại thời điểm thêm.

**Hợp nhất các cây có cùng bậc được trì hoãn tới `extract-min`**. Công việc chưa làm không biến mất; nó được trả sau, và được phân tích bằng **chi phí khấu hao**.

> “Lười” ở đây có nghĩa **lười tái cấu trúc rừng cây**. Nó không đồng nghĩa với việc thêm bản ghi trùng rồi bỏ bản ghi lỗi thời theo kiểu *lazy deletion* trong `heapq`; hai kỹ thuật khác nhau.

## 3. Cấu trúc dữ liệu bên trong một nút

Một nút của Fibonacci heap thường giữ:

| Trường | Ý nghĩa |
|---|---|
| `key` | Khóa ưu tiên được so sánh |
| `value` hoặc `id` | Dữ liệu/định danh nghiệp vụ tùy thiết kế |
| `parent` | Con trỏ tới cha; `null` nếu là gốc |
| `child` | Con trỏ tới **một** nút con, nếu có |
| `left`, `right` | Liên kết vòng đôi tới các anh em hoặc các gốc |
| `degree` | Số **con trực tiếp**, không phải số hậu duệ |
| `mark` | Dấu cho biết nút không phải gốc đã mất một con kể từ khi được gắn dưới cha hiện tại |

Heap tổng thể thường có:

```text
FibonacciHeap:
    min : con trỏ tới một gốc có khóa nhỏ nhất
    n   : số nút đang thuộc heap
```

Danh sách **gốc** và danh sách các **con của mỗi nút** thường đều là **danh sách liên kết đôi vòng**. Một nút chưa có anh em có thể tự trỏ `left = right = self`.

```text
Một cây trong Fibonacci heap:

                          (2)  root, parent=null
                         /   \
                       (5)   (7)
                      /   \
                   (10)  (12)

degree(2)=2
degree(5)=2
degree(7)=degree(10)=degree(12)=0
```

### Vì sao dùng danh sách đôi vòng?

Khi đã có con trỏ tới một nút, ta có thể:

- Nối nút vào danh sách các gốc bằng **một số phép cập nhật con trỏ cố định**.
- Tháo nút khỏi danh sách anh em khi cắt khỏi cha.
- Nối hai danh sách gốc bằng `O(1)` phép cập nhật con trỏ, nếu thao tác nối vòng được cài chính xác.

Điều này giải thích phần chi phí cấu trúc `O(1)` của `insert` và `meld`. Nhưng mã hệ thống còn phải cấp phát, thu hồi bộ nhớ, kiểm soát vòng đời và tránh con trỏ treo theo hợp đồng sở hữu.

## 4. Các bất biến cần được giữ đúng

Fibonacci heap không dựa trên một bất biến hình dạng hoàn chỉnh như binary heap. Thay vào đó, nó dựa trên **quan hệ cây** và **trạng thái mất con**:

1. **Rừng có thứ tự heap:** mọi nút con `x` có cha `p` phải thỏa `key(p)\le key(x)` trong min-heap.
2. **Mỗi nút thuộc đúng một cây**; mọi cây có đúng một gốc.
3. **Danh sách gốc** liên kết các nút có `parent = null`.
4. Với mọi nút, `degree` bằng số **con trực tiếp** đang có.
5. Các vòng liên kết `left/right` phải khép kín, hai chiều nhất quán.
6. `min` trỏ tới **một gốc có khóa nhỏ nhất** trong rừng khi heap không rỗng.
7. `mark=false` cho các gốc. Nút không phải gốc bị mất **một con** có thể được đánh dấu; khi mất con tiếp theo, nó được cắt khỏi cha và trở thành gốc.
8. Số nút `n` bằng tổng số nút trong tất cả các cây.

Nếu nhiều nút có cùng khóa nhỏ nhất, `min` có thể trỏ tới **bất kỳ một** trong số chúng; không có yêu cầu ổn định theo thứ tự chèn.

### So sánh với binary heap

| Đặc điểm | Binary heap | Fibonacci heap |
|---|---|---|
| Hình dạng | Một cây nhị phân hoàn chỉnh | Rừng nhiều cây, không yêu cầu hoàn chỉnh |
| Nơi chứa phần tử nhỏ nhất | Mảng `A[0]` | Con trỏ `min` tới gốc |
| Cách lưu phổ biến | Mảng liên tiếp | Các nút liên kết qua con trỏ |
| Thêm nút | Đặt cuối rồi đẩy lên | Nối một cây một nút vào danh sách gốc |
| Lấy gốc | Đưa phần tử cuối lên, đẩy xuống | Đưa con của gốc vào root list, rồi hợp nhất theo bậc |
| Giảm khóa | Đẩy lên theo đường cha | Có thể cắt nút và cắt dây chuyền |
| Tính cục bộ cache | Thường thuận lợi hơn | Có thể kém hơn vì nút phân tán |

Không phải heap nào cũng dùng mảng hay con trỏ giống ví dụ; bảng so sánh những cách triển khai điển hình.

## 5. Insert: thêm một cây mới mà chưa gom cây

Để thêm khóa `x` vào min-heap:

1. Tạo nút mới `v` có `degree=0`, `child=null`, `parent=null` và `mark=false`.
2. Nối `v` thành một **gốc mới** trong danh sách gốc.
3. Nếu heap rỗng hoặc `v.key` nhỏ hơn khóa của gốc `min` hiện tại, cập nhật `min=v`.
4. Tăng `n` thêm một.

```text
Trước:
  roots: [3] <--> [8] <--> [5]
  min -> [3]

insert(1):
  roots: [3] <--> [8] <--> [5] <--> [1]
  min ---------------------------------> [1]
```

Không có vòng lặp đẩy lên và **không hợp nhất** các cây. Số phép sửa con trỏ chỉ là hằng số, nên chi phí thao tác cấu trúc là **`O(1)`**.

Nếu heap có rất nhiều thao tác `insert` mà chưa `extract-min`, danh sách gốc có thể chứa rất nhiều cây một nút. Điều này **được phép**: cấu trúc đang trì hoãn việc gom cây.

### Điều kiện để phát biểu O(1)

Độ phức tạp của thao tác heap giả định rằng:

- Cấp phát nút đã sẵn sàng hoặc chi phí cấp phát được xét riêng theo mô hình thông dụng.
- Thao tác nối danh sách đôi vòng là hằng số.
- So sánh hai khóa tốn `O(1)`.

Không được suy ra mọi lời gọi `malloc` hoặc `new` đều được bảo đảm `O(1)` trường hợp xấu nhất trên mọi nền tảng.

## 6. Find-min: không cần duyệt toàn bộ danh sách gốc

Danh sách gốc Fibonacci heap **không được sắp xếp theo khóa**, nên nếu không có con trỏ `min` thì việc tìm nhỏ nhất có thể cần duyệt nhiều gốc.

Fibonacci heap giải quyết bằng cách **duy trì con trỏ `min` sau mọi thao tác**:

```text
roots: [9] <--> [4] <--> [12] <--> [2]
                                     ^
                                   min
```

`find-min()` chỉ kiểm tra heap có rỗng không rồi trả khóa (hoặc handle) tại `min`:

```text
FIND_MIN(H):
    if H.min is null: report empty
    return H.min
```

Thời gian là **`O(1)` trường hợp xấu nhất** trong mô hình thao tác con trỏ. Việc chỉ **xem** phần tử không thay đổi cấu trúc, nên hàm thế năng cũng không đổi.

Phải phân biệt:

- `find-min` **không xóa** nút khỏi heap.
- `extract-min` **xóa** nút và phải xử lý lại các cây để giữ bảo đảm cho những thao tác sau.

## 7. Meld: nối hai danh sách gốc trong O(1)

Giả sử có hai Fibonacci min-heap độc lập `H1` và `H2` dùng **cùng thứ tự so sánh khóa**:

```text
H1 roots: [3] <--> [8]      min1 = 3, n1 = 2
H2 roots: [4] <--> [1]      min2 = 1, n2 = 2
```

Để **gộp** (*meld/union*):

1. Nối hai **danh sách gốc vòng đôi** thành một danh sách.
2. Chọn `min` mới là nút có khóa nhỏ hơn giữa `H1.min` và `H2.min`.
3. Đặt `n=n1+n2`.
4. Làm rõ quyền sở hữu: trong phiên bản **meld phá hủy nguồn**, các heap nguồn không còn được dùng như hai container độc lập sau gộp.

```text
Hợp nhất:

roots: [3] <--> [8] <--> [4] <--> [1]
                                       ^
                                      min
```

Không cần đi qua toàn bộ nút của hai heap. Thao tác nối vòng đôi và so sánh hai cực trị dùng số bước hằng số, nên `meld` có **`O(1)` thời gian cấu trúc**, ngay cả khi mỗi heap chứa rất nhiều nút.

**Điều kiện:** cả hai heap phải dùng **cùng quy tắc so sánh**; nếu một heap là min-heap còn một heap là max-heap, hoặc cùng priority nhưng bộ so sánh không tương thích, nối danh sách không giữ được ý nghĩa của `min` và bất biến thứ tự.

Các triển khai dùng **indexed heap `id\to node`** hoặc cơ chế owner phức tạp có thể cần hợp nhất thêm bảng băm/chỉ mục, khiến **toàn bộ API gộp** không còn `O(1)`. Bảo đảm meld `O(1)` nói về **Fibonacci heap thuần với handle trực tiếp**, không phải mọi lớp bao và dịch vụ phụ trợ.

## 8. Extract-min: thời điểm trả món nợ tái cấu trúc

Đây là thao tác phức tạp nhất trong Fibonacci heap cơ bản.

Giả sử `z=H.min` là gốc có khóa nhỏ nhất:

1. **Tách `z` khỏi danh sách gốc**.
2. Đưa **tất cả con trực tiếp của `z`** lên thành các gốc mới. Mỗi con có `parent=null` và `mark=false`.
3. **Hợp nhất** (*consolidate*) các gốc để không còn hai gốc có cùng `degree`.
4. Duyệt các gốc còn lại để chọn `min` mới.
5. Giảm `n` một và trả nút `z` hoặc dữ liệu của nó theo hợp đồng.

```text
Trước extract-min:

    roots:      (2) <--> (5) <--> (7)
                 |
               (4) -- (8)        [hai con của 2]

Đưa con của 2 lên root list, bỏ 2:

    roots:      (5) <--> (7) <--> (4) <--> (8)

Sau đó mới CONSOLIDATE các gốc có cùng degree.
```

Các con được đưa lên thành gốc **không còn chịu quan hệ cha–con với `z`**, vì `z` đã bị xóa. Những cây con bên dưới chúng vẫn thỏa heap-order.

### Vì sao phải hợp nhất ở bước này?

Nếu chỉ chuyển con lên root list rồi dừng, số gốc có thể tăng không giới hạn qua chuỗi thao tác. Khi gốc nhỏ nhất bị xóa, ta cần tìm gốc nhỏ nhất mới trong một danh sách có thể rất dài. Fibonacci heap dùng `extract-min` để **trả chi phí gom cây**, giảm số gốc còn lại xuống `O(\log n)` sau bước hợp nhất.

Trong binary heap, khôi phục thứ tự thường đi theo một đường từ gốc xuống lá. Trong Fibonacci heap, việc lấy gốc có thể làm việc với **nhiều cây** và **nhiều gốc**, trước khi chọn lại min.

## 9. Consolidation: ghép các cây cùng bậc

**Bậc** (*degree*) của một nút là số **con trực tiếp** của nó. Trong `consolidate`, ta muốn sau khi kết thúc:

> **Mỗi bậc chỉ còn tối đa một gốc.**

Giả sử hai gốc `x` và `y` đều có bậc `k`. Khi dùng min-heap:

1. So khóa của hai gốc.
2. Giữ gốc có **khóa nhỏ hơn** làm cha (nếu bằng nhau, chọn một quy tắc nhất quán).
3. Tháo gốc còn lại khỏi root list.
4. Nối gốc còn lại làm **con** của gốc nhỏ hơn.
5. Tăng `degree` của cha từ `k` thành `k+1`.
6. Đặt `parent(child)=parent`, `mark(child)=false`.

```text
Trước:        Hai cây đều degree=1

      (3)                (5)
       |                  |
      (7)                (9)

Liên kết 5 làm con của 3 vì 3 < 5:

             (3)             degree(3)=2
            /   \
          (7)   (5)          degree(5)=1
                 |
                (9)
```

Sau một lần liên kết, **số cây giảm một**. Nếu gốc mới lại đụng một gốc khác có cùng bậc `k+1`, tiếp tục liên kết.

### Bảng bậc tạm thời

Một cách cài `consolidate` thường dùng mảng hoặc bảng ánh xạ tạm:

```text
A[degree] = gốc đang đại diện cho bậc đó.
```

Với mỗi gốc còn sống:

```text
CONSOLIDATE(H):
    A = empty degree table
    roots = snapshot of current root list

    for each root x in roots:
        if x is no longer a root:
            continue

        while A[x.degree] contains a root y:
            remove y from A
            ensure x.key <= y.key (swap x,y if needed)
            LINK(y under x)
        A[x.degree] = x

    rebuild root list from nonempty A slots
    reset H.min to the smallest remaining root
```

Mỗi lần `LINK` làm tăng degree của một gốc và giảm số gốc đi một. Sau khi xử lý hết, những gốc có bậc trùng nhau đã được ghép.

### Ví dụ ghép từ bốn gốc có bậc 0

```text
roots:    (3)   (7)   (11)   (5)
degree:    0     0     0      0
```

Có thể thực hiện:

1. Ghép `7` dưới `3` → cây gốc `3` bậc `1`.
2. Ghép `11` dưới `5` → cây gốc `5` bậc `1`.
3. Ghép cây gốc `5` dưới gốc `3` → cây gốc `3` bậc `2`.

```text
           (3)
          /   \
        (7)   (5)
               |
             (11)

Một cây, degree(gốc)=2.
```

Kết quả có thể khác tùy thứ tự xử lý gốc và quy tắc hòa khóa, nhưng phải giữ **heap-order**, **degree chính xác** và **mỗi bậc tối đa một gốc** sau hợp nhất.

## 10. Decrease-key: giảm khóa nhưng không đẩy cả cây lên

Trong min-heap, thao tác `decrease-key(x,k)` yêu cầu:

\[
k\le key(x).
\]

Nếu giảm khóa của **một gốc**, chỉ cần đổi khóa và cập nhật `min` nếu gốc ấy trở nên nhỏ nhất. Không phải cắt hoặc hợp nhất cây.

Nếu `x` là **nút con** của `p`:

- Nếu khóa mới vẫn thỏa `key(p)\le key(x)`, không phải thay đổi liên kết.
- Nếu khóa mới `key(x)<key(p)`, cạnh `p\to x` vi phạm min-heap-order. Ta **cắt `x` khỏi cha** và đưa cả cây con gốc `x` lên danh sách gốc.

```text
Trước:

             (2)
              |
             (6)
            /   \
          (9)   (12)
           |
          (14)

Giảm khóa nút (9) thành (1):

             (2)             (1)  <-- gốc mới
              |               |
             (6)             (14)
              |
             (12)

min -> (1)
```

Ta không cần thay đổi nội bộ cây con của `x`: giảm khóa gốc của cây con chỉ giúp nó **nhỏ hơn các hậu duệ**, nên quan hệ với những nút con của chính nó vẫn hợp lệ.

**Cut không tự xóa nút khỏi heap**. Nó chỉ đổi **membership** của nút từ cây con sang danh sách gốc; `n` không đổi.

## 11. Cắt một nút: thao tác O(1) khi đã có handle

Giả sử `x` đang là con của `y`, và ta có **con trỏ trực tiếp tới `x`**:

```text
CUT(x, y, H):
    remove x from y's circular children list
    y.degree -= 1
    if y.child pointed to x:
        update y.child to another child or null

    x.parent = null
    x.mark = false
    append x to H.root_list
    update H.min if necessary
```

Nhờ danh sách liên kết đôi vòng, tháo `x` từ vòng các con và nối sang vòng gốc chỉ cần một số phép sửa con trỏ cố định: **`O(1)` bước thực tế**, khi handle và mọi liên kết đều hợp lệ.

Khi đưa `x` trở thành gốc:

- Cờ `mark` của nó được xóa.
- `degree(x)` **không đổi**, vì các con **của `x`** vẫn ở dưới nó.
- `degree(y)` giảm một, vì `y` vừa mất một **con trực tiếp**.
- Số cây trong root list tăng một.

### Tại sao không cắt tất cả tổ tiên?

Nếu cứ cắt mọi tổ tiên sau một thay đổi khóa, một lần `decrease-key` trên nút rất sâu có thể quá đắt. Fibonacci heap dùng cờ `mark` để **kiểm soát lúc nào tổ tiên cũng cần bị cắt**, từ đó có được cận khấu hao.

## 12. Mark và cascading cut: mất một con thì đánh dấu, mất hai thì cắt

Đây là phần làm nên Fibonacci heap.

### Quy tắc của cờ mark

Đối với một nút `y` **không phải gốc**:

1. Khi `y` vừa được gắn dưới một cha trong thao tác `LINK`, đặt `mark(y)=false`.
2. Nếu `y` mất **con đầu tiên** kể từ khi được gắn dưới cha ấy, đánh dấu `mark(y)=true`.
3. Nếu `y` đã được đánh dấu mà lại mất **một con khác**, cắt **chính `y`** khỏi cha của nó và chuyển `y` thành gốc. Tiếp tục xem cha cũ của `y` có cần đánh dấu hay cắt hay không.

**Gốc không được đánh dấu**: gốc không có cha để phải bảo vệ quan hệ bậc của cha. Khi trở thành gốc, nút được đặt `mark=false`.

### Mã giả cắt dây chuyền

```text
CASCADING_CUT(y, H):
    z = y.parent

    if z is null:
        return                # y đã là gốc

    if y.mark == false:
        y.mark = true         # lần mất con thứ nhất
    else:
        CUT(y, z, H)          # mất thêm một con -> cắt y
        CASCADING_CUT(z, H)   # xét cha cũ của y
```

Thao tác giảm khóa đầy đủ:

```text
DECREASE_KEY(H, x, k):
    require k <= x.key
    x.key = k
    y = x.parent

    if y is not null and x.key < y.key:
        CUT(x, y, H)
        CASCADING_CUT(y, H)

    if x.key < H.min.key:
        H.min = x
```

### Ví dụ cắt dây chuyền

Giả sử `r` là gốc, `y` là con của `r`, `x` và `a` là hai con của `y`:

```text
Ban đầu (min-heap):

                  r(1)                root
                   |
                  y(4) [mark=false]
                 /    \
               a(9)   x(7)
```

**Lần 1:** giảm khóa `a` xuống `2`, vi phạm với `y(4)`.

- Cắt `a` khỏi `y`, đưa `a` thành một gốc.
- `y` còn con `x` và **mất một con**, nên `mark(y)=true`.

```text
roots: r(1), a(2)
         |
        y(4) [mark=true]
         |
        x(7)
```

**Lần 2:** giảm khóa `x` xuống `0`, lại vi phạm với `y(4)`.

- Cắt `x` khỏi `y`, đưa `x` lên root list.
- `y` đang `mark=true` và lại mất thêm một con, nên **cắt cả `y` khỏi `r`**.
- `y` trở thành gốc và đặt `mark(y)=false`.
- `r` là gốc nên không được đánh dấu hoặc cắt tiếp.

```text
roots: r(1), a(2), x(0), y(4)
                     ^
                    min

y hiện là gốc, mark=false.
```

Một lần giảm khóa có thể làm **nhiều cây con trở thành gốc**, không chỉ cắt chính nút được cập nhật. Về số bước **thực tế**, cắt dây chuyền có thể dài; cận `O(1)` của `decrease-key` là **khấu hao**, không phải chặn số lát cắt trong từng lần gọi.

## 13. Vì sao cần cờ mark để bảo đảm bậc nút không quá lớn?

Con số `degree` ảnh hưởng trực tiếp đến chi phí `extract-min`: khi gỡ một gốc có nhiều con, ta phải chuyển các con thành gốc; khi hợp nhất, phải quản lý bậc của các cây.

Nếu không có quy tắc cắt dây chuyền, một nút có thể **mất rất nhiều con** nhưng vẫn nằm dưới cha, khiến thông tin “nút bậc lớn thường đại diện cho một cây có nhiều nút” không còn đáng tin cậy.

Fibonacci heap bảo vệ thông tin ấy bằng quy tắc:

> Một nút đang là con của một cha có thể **mất tối đa một con** mà chưa bị cắt khỏi cha đó. Nếu mất thêm con, nó phải rời khỏi cha.

Điều này dẫn đến mối quan hệ giữa `degree` và **kích thước cây con**, là nền tảng của giới hạn `degree=O(\log n)`.

### Trực giác qua thứ tự gắn con

Giả sử một nút `x` hiện có `k` con, xét chúng theo **thứ tự lần lượt được gắn làm con của `x`**:

```text
y1, y2, y3, ..., yk
```

Ở thời điểm `yj` được liên kết dưới `x`, `x` đã có ít nhất `j-1` con; vì phép `LINK` gộp hai **gốc có cùng bậc**, `yj` lúc đó cũng có bậc ít nhất `j-1` (với cách đánh số trong suy luận chuẩn).

Sau khi trở thành con của `x`, `yj` được phép mất **tối đa một con** trước khi bị cắt khỏi `x`. Vì thế, tại thời điểm đang xét:

\[
degree(y_j)\ge j-2
\]

với `j\ge2`; với `j=1`, cận hiển nhiên là `degree(y_1)\ge0`.

Kết hợp cận bậc của các con theo thứ tự này tạo ra một cận dưới cho số nút trong cây gốc `x`.

## 14. Vì sao lại tên là Fibonacci heap?

Gọi `S(k)` là **số nút tối thiểu** trong cây có gốc bậc `k`, dưới các bất biến của Fibonacci heap. Từ quy tắc mất tối đa một con, ta thu được cận dưới liên quan đến dãy Fibonacci:

\[
\boxed{S(k)\ge F_{k+2}}
\]

với dãy:

\[
F_0=0,\quad F_1=1,\quad F_{j+2}=F_{j+1}+F_j.
\]

Ví dụ:

| Bậc gốc `k` | Cận dưới `F_{k+2}` cho số nút trong cây |
|---:|---:|
| `0` | `1` |
| `1` | `2` |
| `2` | `3` |
| `3` | `5` |
| `4` | `8` |
| `5` | `13` |
| `6` | `21` |

Ta không khẳng định **mọi cây có đúng số nút Fibonacci**. Đây là **cận dưới**: gốc bậc `k` phải có **ít nhất** chừng ấy nút, do quy tắc tổ chức và cắt con.

Vì:

\[
F_{k+2}=\Omega(\varphi^k),\qquad
\varphi=\frac{1+\sqrt5}{2}\approx1{,}618,
\]

nếu toàn heap có `n` nút thì mọi cây có tối đa `n` nút, suy ra:

\[
\varphi^k=O(n)
\quad\Longrightarrow\quad
\boxed{k=O(\log_\varphi n)=O(\log n).}
\]

Do đó, **bậc lớn nhất** của bất kỳ nút nào trong Fibonacci heap có kích thước `n` bị chặn bởi `O(\log n)`.

### Cần phân biệt bậc và chiều cao

Cận vừa chứng minh là về **số con trực tiếp** `degree`, **không phải** cam kết mọi cây đều là cây cân bằng hoặc có chiều cao `O(\log n)`. Fibonacci heap không giữ bất biến chiều cao mạnh như cây nhị phân hoàn chỉnh.

Cận bậc là thứ `consolidate` cần: sau khi gộp đến mức **mỗi bậc chỉ có một gốc**, số gốc tối đa là `O(\log n)`, vì bậc của gốc nằm trong phạm vi `0,\ldots,D(n)` với `D(n)=O(\log n)`.

## 15. Khấu hao là gì? Không được nhầm với trung bình xác suất

Một thao tác được gọi là có **chi phí khấu hao `O(1)`** nếu, khi xét một **chuỗi thao tác hợp lệ**, tổng chi phí của những thao tác cùng kiểu và công việc liên quan được phân bổ theo một giới hạn thích hợp.

**Khấu hao không phải là:**

- Giả định đầu vào phân bố ngẫu nhiên.
- Giá trị trung bình thống kê đo được trong benchmark.
- Bảo đảm mỗi lần gọi chạy `O(1)` trong trường hợp xấu nhất.

Ví dụ mảng động tăng sức chứa theo tỷ lệ có một số lần `append` phải sao chép `O(n)` phần tử, nhưng qua một chuỗi `n` lần thêm cuối, tổng số phần tử bị sao chép là `O(n)`, nên chi phí thêm cuối **`O(1)` khấu hao**.

Fibonacci heap dùng cùng tư tưởng “một số lần gọi đắt, nhưng không thể đắt quá thường xuyên nếu tính tất cả công việc đã tích lũy”, được phân tích bằng **phương pháp thế năng** (*potential method*).

### Phương pháp thế năng

Cho trạng thái cấu trúc trước thao tác thứ `i` là `H_{i-1}`, sau thao tác là `H_i`:

\[
\boxed{\hat c_i=c_i+\Phi(H_i)-\Phi(H_{i-1})}
\]

trong đó:

- `c_i`: chi phí **thực tế**.
- `\hat c_i`: chi phí **khấu hao**.
- `\Phi(H)`: giá trị **thế năng** không âm của trạng thái heap.

Cộng theo chuỗi `m` thao tác:

\[
\sum_{i=1}^{m}\hat c_i
=\sum_{i=1}^{m}c_i
+\Phi(H_m)-\Phi(H_0).
\]

Suy ra:

\[
\sum_{i=1}^{m}c_i
=\sum_{i=1}^{m}\hat c_i
+\Phi(H_0)-\Phi(H_m)
\le \sum_{i=1}^{m}\hat c_i+\Phi(H_0),
\]

vì `\Phi(H_m)\ge0`. Nếu bắt đầu từ heap rỗng có `\Phi(H_0)=0`, tổng chi phí thực tế không vượt quá tổng chi phí khấu hao được tính.

## 16. Hàm thế năng của Fibonacci heap

Ta định nghĩa:

- `t(H)`: số **cây**, tức số **gốc** trong root list.
- `m(H)`: số **nút được đánh dấu** (*marked nodes*) trong heap.

Hàm thế năng kinh điển:

\[
\boxed{\Phi(H)=t(H)+2m(H).}
\]

Vì `t(H)\ge0` và `m(H)\ge0`, thế năng không âm. Một heap rỗng có `t=m=0` nên `\Phi=0`.

### Trực giác “tín dụng công việc”

- **Mỗi cây/gốc** mang một đơn vị thế năng, đại diện cho việc cần gom các cây vào lần `extract-min` trong tương lai.
- **Mỗi nút được mark** mang thêm hai đơn vị, đại diện cho khả năng nó sẽ bị cắt dây chuyền khi mất thêm con.

Không cần tưởng tượng đây là tiền thật hay số phép so sánh chính xác; đây là **cách phân bổ đại số** để chứng minh một chuỗi thao tác không thể tích lũy chi phí quá lớn so với công việc đã thực hiện.

### Ví dụ tính thế năng

| Trạng thái | `t(H)` | `m(H)` | `\Phi(H)` |
|---|---:|---:|---:|
| Heap rỗng | 0 | 0 | 0 |
| Sau bốn lần insert nút đơn | 4 | 0 | 4 |
| Bốn gốc, hai nút được mark | 4 | 2 | 8 |
| Một gốc, không nút được mark | 1 | 0 | 1 |

`insert` làm tăng số gốc, tức tăng thế năng. `consolidate` làm giảm số gốc, tức **giải phóng** phần thế năng đã tích lũy. Cắt dây chuyền làm tăng số gốc nhưng thường **giảm số nút được mark**, nên cũng có thể được thế năng bù chi phí.

## 17. Chứng minh khấu hao cho insert, find-min và meld

### 17.1. Insert

Thao tác thêm một nút đơn:

- Chi phí thực tế `c=O(1)`.
- Số gốc tăng một: `\Delta t=+1`.
- Nút mới chưa mark: `\Delta m=0`.

Vì vậy:

\[
\Delta\Phi=1,\qquad
\hat c=c+\Delta\Phi=O(1)+1=\boxed{O(1)}.
\]

Phần thế năng tăng thêm là “khoản dự trữ” cho việc gộp cây sau này.

### 17.2. Find-min

Chỉ đọc `min`:

- `c=O(1)`.
- Không đổi số cây hay số nút mark: `\Delta\Phi=0`.

\[
\hat c=\boxed{O(1)}.
\]

### 17.3. Meld

Gộp hai rừng bằng nối root list, không tạo/xóa nút và không đánh lại mark:

- Chi phí cấu trúc `O(1)`.
- Nếu chỉ gộp các danh sách mà không gom cây, `t(H)=t(H_1)+t(H_2)` và `m(H)=m(H_1)+m(H_2)`.

Vì thế:

\[
\Phi(H)=\Phi(H_1)+\Phi(H_2).
\]

Với phép gộp phá hủy hai heap nguồn thành một heap kết quả, thay đổi thế năng **tổng cộng** là `0`, nên chi phí khấu hao `meld` là **`O(1)`**.

**Lưu ý:** phân tích này không bao gồm việc phải hợp nhất một bảng `id\to handle` hay một container phụ có nhiều phần tử; nếu API bao thêm chức năng đó, phải cộng chi phí tương ứng.

## 18. Chứng minh khấu hao cho decrease-key và cắt dây chuyền

Đây là phần giải thích vì sao `decrease-key` có thể có nhiều lần cắt mà vẫn **`O(1)` khấu hao**.

Giả sử một lần `decrease-key` thực hiện tổng cộng **`c` lần cắt** (bao gồm nút ban đầu nếu bị cắt, cộng các tổ tiên bị cắt dây chuyền).

### Chi phí thực tế

Mỗi lần cắt sửa một số con trỏ và bậc nút cố định:

\[
T_{\text{actual}}=O(c+1).
\]

### Số gốc thay đổi

Mỗi nút được cắt khỏi cha trở thành **một gốc mới**:

\[
\Delta t=c.
\]

### Số nút được mark thay đổi

Trong một chuỗi có `c\ge1` lần cắt:

- Các nút tổ tiên **bị cắt tiếp** trong cascading cut đều đã `mark=true` trước khi cắt.
- Có ít nhất `c-1` nút như vậy (trừ nút đầu tiên vừa giảm khóa, vốn có thể chưa được mark).
- Khi bị cắt thành gốc, mark của chúng được **xóa**.
- Sau khi chuỗi cắt dừng lại, tối đa **một** nút không phải gốc mới được đánh dấu.

Do đó:

\[
\Delta m\le1-(c-1)=2-c.
\]

Suy ra:

\[
\begin{aligned}
\Delta\Phi
&=\Delta t+2\Delta m\\
&\le c+2(2-c)\\
&=4-c.
\end{aligned}
\]

Để không bỏ qua hệ số hằng số trong ký hiệu `O`, chọn một hằng số `a>0` đủ lớn sao cho chi phí thực tế của thao tác không vượt `a(c+1)`, và nhân thế năng với cùng hệ số: `\Phi_a(H)=a(t(H)+2m(H))`. Khi đó:

\[
\begin{aligned}
\hat c
&=c_{\mathrm{actual}}+\Delta\Phi_a\\
&\le a(c+1)+a(4-c)\\
&=5a=\boxed{O(1)}.
\end{aligned}
\]

Như vậy, **chi phí tăng theo số lần cắt được bù bởi việc giảm thế năng từ các nút đã mark**. Nhân toàn bộ hàm thế năng với một hằng số dương không thay đổi bản chất phép phân tích.

Nếu **không xảy ra cắt** (`c=0`), thao tác chỉ giảm khóa và có thể cập nhật `min`: chi phí `O(1)` và thế năng không tăng đáng kể. Do đó, mọi trường hợp đều có cận `O(1)` khấu hao.

### Không phải O(1) worst-case

Một lần `decrease-key` có thể kích hoạt cắt qua nhiều tổ tiên đã đánh dấu, vì vậy **không có bảo đảm mỗi lần gọi chỉ cắt một số nút hằng số**. Cận khấu hao nói về **tổng công qua chuỗi thao tác**, nhờ các lần đánh dấu và tích lũy thế năng trước đó.

## 19. Chứng minh khấu hao cho extract-min

Gọi:

- `t`: số gốc trước `extract-min`.
- `D(n)`: bậc lớn nhất của một nút; đã có `D(n)=O(\log n)`.
- `d_z`: số con của gốc nhỏ nhất `z`, với `d_z\le D(n)`.

### Công việc thực tế

Phép lấy nhỏ nhất gồm:

1. Tách gốc `z` khỏi danh sách.
2. Đưa `d_z` con của nó lên thành gốc.
3. Duyệt và hợp nhất các gốc có cùng bậc.
4. Chọn lại gốc nhỏ nhất.

Chi phí thực tế có thể viết:

\[
c=O(t+d_z+D(n)).
\]

Vì `d_z\le D(n)`:

\[
c=O(t+D(n)).
\]

Sau hợp nhất, mọi bậc gốc đều khác nhau và không vượt quá `D(n)`, nên số gốc còn lại:

\[
t'\le D(n)+1.
\]

Các nút con chuyển thành gốc được xóa mark; việc liên kết các cây cũng không tạo thêm mark. Do đó:

\[
m'\le m.
\]

Thay đổi thế năng:

\[
\begin{aligned}
\Delta\Phi
&=(t'-t)+2(m'-m)\\
&\le D(n)+1-t.
\end{aligned}
\]

Khi tính chi phí khấu hao, chọn hằng số `a>0` đủ lớn để chi phí thực tế không vượt `a(t+D(n))` và dùng thế năng đã nhân hệ số `\Phi_a=a\Phi`. Khi đó:

\[
\begin{aligned}
\hat c
&=c_{\mathrm{actual}}+\Delta\Phi_a\\
&\le a(t+D(n))+a(D(n)+1-t)\\
&=a(2D(n)+1).
\end{aligned}
\]

Hạng công việc **duyệt `t` gốc** được bù bởi khoản **giảm thế năng `t-t'`**. Vì vậy:

\[
\boxed{\hat c_{\text{extract-min}}=O(D(n))=O(\log n)}.
\]

### Vì sao trường hợp xấu nhất của một lần gọi có thể O(n)?

Sau `n` lần `insert` mà chưa từng hợp nhất, heap có thể có **`n` gốc một nút**. Một lần `extract-min` phải duyệt và gom nhiều gốc; chi phí thực tế có thể tới **`\Theta(n)`** trong tình huống này.

Không mâu thuẫn với `O(\log n)` **khấu hao**: `n` lần thêm trước đó đã làm tăng thế năng lên `\Theta(n)`, cung cấp “tín dụng” cho phép lấy lớn này.

### Bậc không phụ thuộc chiều cao đường đi

Giới hạn `D(n)=O(\log n)` ở đây là **bậc tối đa**, không phải bảo đảm mọi cây có chiều cao logarithmic. Việc phân tích `extract-min` dựa trên **số con trực tiếp** và **số loại bậc sau consolidate**, chứ không cần toàn bộ cây cân bằng.

## 20. Bảng độ phức tạp: khấu hao khác worst-case

Xét Fibonacci min-heap thuần, có **handle hợp lệ đến nút** khi cập nhật/xóa, so sánh khóa và thao tác con trỏ cơ bản tính `O(1)`.

| Thao tác | Khấu hao | Nhận xét về một lần gọi |
|---|---|---|
| `make-heap` | `O(1)` | Khởi tạo rỗng |
| `insert` | `O(1)` | Nối một nút làm gốc; cấp phát xét riêng |
| `find-min` | `O(1)` | Chỉ đọc con trỏ `min` |
| `meld` | `O(1)` | Nối hai root list; không gộp chỉ mục phụ |
| `decrease-key` | `O(1)` | Có thể cắt dây chuyền qua nhiều tổ tiên |
| `extract-min` | `O(\log n)` | Có thể `O(n)` thực tế nếu nhiều gốc |
| `delete(x)` | `O(\log n)` | Kết hợp cắt/đổi min với lấy gốc |
| Tìm một phần tử theo ID **không có handle** | `O(n)` xấu nhất | Heap-order không phải chỉ mục ID |
| `increase-key` tổng quát | Không có cận `O(1)` tương tự trong thiết kế chuẩn | Có thể xóa và chèn lại |

Một số thuật toán/biến thể heap Fibonacci có các bảo đảm chi tiết khác, nhưng bảng này nói về **Fibonacci heap kinh điển**.

### Bộ nhớ

Một heap có `n` nút cần `O(n)` bộ nhớ, nhưng mỗi nút có **nhiều trường con trỏ, bậc và mark**, thường nhiều overhead hơn một binary heap lưu trong mảng.

Hàm `consolidate` thường dùng bảng bậc tạm cỡ `O(\log n)`, còn việc trích danh sách gốc thành một snapshot có thể dùng thêm `O(t)` trong một bản cài đặt đơn giản. Vì thế, đừng khẳng định **mọi cài đặt** của `extract-min` chỉ cần `O(1)` bộ nhớ phụ; điều này phụ thuộc chiến lược duyệt và hợp nhất.

## 21. Mã Python minh họa Fibonacci min-heap

Sau đây là một **phiên bản giảng dạy** với:

- Các nút có liên kết đôi vòng.
- Danh sách gốc và danh sách con đều dùng cùng quy tắc nối vòng.
- `insert`, `minimum`, `meld`, `extract_min`, `decrease_key` và `delete`.
- `consolidate` dùng một `dict` tạm theo bậc.

Để mã dễ đọc, ta giả định **khóa là số nguyên**, phép so sánh nhất quán, không có thao tác đồng thời; handle truyền vào phải thật sự thuộc đúng heap còn hoạt động. Đây không phải một thư viện production có bảo vệ ownership, exception safety và nhiều luồng.

### 21.1. Nút và các thao tác vòng liên kết

```python
class FibNode:
    def __init__(self, key: int, value: str) -> None:
        self.key = key
        self.value = value
        self.parent: FibNode | None = None
        self.child: FibNode | None = None
        self.left: FibNode = self
        self.right: FibNode = self
        self.degree = 0
        self.mark = False
        self.active = True


class FibonacciMinHeap:
    def __init__(self) -> None:
        self.min: FibNode | None = None
        self.n = 0

    def __len__(self) -> int:
        return self.n

    @staticmethod
    def _snapshot(start: FibNode | None) -> list[FibNode]:
        """Lấy các nút hiện có trong một vòng; dùng khi chuẩn bị sửa vòng."""
        if start is None:
            return []
        nodes = [start]
        current = start.right
        while current is not start:
            nodes.append(current)
            current = current.right
        return nodes

    @staticmethod
    def _insert_after(anchor: FibNode, node: FibNode) -> None:
        """Nối node đang độc lập vào ngay sau anchor."""
        node.left = anchor
        node.right = anchor.right
        anchor.right.left = node
        anchor.right = node

    @staticmethod
    def _detach(node: FibNode) -> None:
        """Tháo node khỏi vòng hiện tại và biến nó thành vòng một nút."""
        node.left.right = node.right
        node.right.left = node.left
        node.left = node
        node.right = node

    def _add_root(self, node: FibNode) -> None:
        node.parent = None
        node.mark = False
        if self.min is None:
            node.left = node
            node.right = node
            self.min = node
        else:
            self._insert_after(self.min, node)
            if node.key < self.min.key:
                self.min = node

    def insert(self, key: int, value: str) -> FibNode:
        node = FibNode(key, value)
        self._add_root(node)
        self.n += 1
        return node  # Handle dùng cho decrease_key/delete.

    def minimum(self) -> tuple[int, str]:
        if self.min is None:
            raise IndexError("Heap rỗng")
        return self.min.key, self.min.value
```

Khi một nút mới được thêm, `degree=0` và `mark=false`; chưa cần gắn nó dưới nút khác. `_snapshot` là tiện ích cài đặt để có thể sửa vòng trong khi vẫn biết danh sách nút ban đầu; nó **không** làm cho thao tác `insert` trở thành tuyến tính vì `insert` không gọi nó.

### 21.2. Link, hợp nhất theo bậc và lấy gốc

Đoạn sau thuộc **cùng lớp `FibonacciMinHeap`**, viết tiếp vào bên trong định nghĩa lớp ở phần 21.1.

```python
    def _link(self, child: FibNode, parent: FibNode) -> None:
        """Ghép hai gốc: child trở thành con trực tiếp của parent."""
        self._detach(child)
        child.parent = parent
        child.mark = False

        if parent.child is None:
            parent.child = child
        else:
            self._insert_after(parent.child, child)
        parent.degree += 1

    def _consolidate(self) -> None:
        roots = self._snapshot(self.min)
        by_degree: dict[int, FibNode] = {}

        for root in roots:
            if root.parent is not None:
                continue  # Đã bị ghép làm con trong vòng xử lý trước.

            x = root
            while x.degree in by_degree:
                y = by_degree.pop(x.degree)
                if y.key < x.key:
                    x, y = y, x
                self._link(y, x)
            by_degree[x.degree] = x

        # Tái tạo danh sách gốc từ những cây có degree khác nhau.
        # Sau khi hoàn tất ghép, không dùng vòng gốc cũ nữa.
        self.min = None
        for root in by_degree.values():
            root.left = root
            root.right = root
            self._add_root(root)

    def extract_min(self) -> tuple[int, str]:
        z = self.min
        if z is None:
            raise IndexError("Heap rỗng")

        # Các con của z trở thành các gốc độc lập.
        for child in self._snapshot(z.child):
            self._detach(child)
            self._add_root(child)
        z.child = None
        z.degree = 0

        if z.right is z:
            self.min = None
        else:
            next_root = z.right
            self._detach(z)
            self.min = next_root
            self._consolidate()

        self.n -= 1
        z.active = False
        z.parent = None
        z.left = z
        z.right = z
        z.mark = False
        return z.key, z.value
```

**Cách đọc `_consolidate`:** bảng `by_degree` giữ tối đa một gốc của mỗi bậc. Khi trùng bậc, gốc có khóa lớn hơn được gắn dưới gốc có khóa nhỏ hơn, làm bậc gốc mới tăng. Sau đó, root list được dựng lại và con trỏ `min` được chọn lại.

**Cách đọc `extract_min`:** sau khi đưa các con của `z` lên root list, ta bỏ `z` rồi mới hợp nhất. `_snapshot(z.child)` giúp tránh lặp trên một vòng đang bị chỉnh sửa. Nếu heap có đúng một nút và không có con, sau khi xóa heap trở thành rỗng.

Trong một triển khai thực tế, phải đặc biệt chú ý **trạng thái khi có ngoại lệ** phát sinh giữa các lần cập nhật con trỏ hoặc khi cấp phát bảng `by_degree`. Mã trên minh họa cấu trúc và độ phức tạp trong mô hình thao tác thành công.

### 21.3. Giảm khóa, cắt dây chuyền và xóa theo handle

Các phương thức sau cũng thuộc **cùng lớp `FibonacciMinHeap`**:

```python
    def _cut(self, node: FibNode, parent: FibNode) -> None:
        if parent.child is node:
            parent.child = node.right if node.right is not node else None
        self._detach(node)
        parent.degree -= 1
        self._add_root(node)

    def _cascading_cut(self, node: FibNode) -> None:
        parent = node.parent
        if parent is None:
            return
        if not node.mark:
            node.mark = True
        else:
            self._cut(node, parent)
            self._cascading_cut(parent)

    def decrease_key(self, node: FibNode, new_key: int) -> None:
        if not node.active:
            raise ValueError("Handle đã bị loại khỏi heap")
        if new_key > node.key:
            raise ValueError("decrease_key không được tăng khóa")

        node.key = new_key
        parent = node.parent
        if parent is not None and node.key < parent.key:
            self._cut(node, parent)
            self._cascading_cut(parent)

        if self.min is None or node.key < self.min.key:
            self.min = node

    def delete(self, node: FibNode) -> tuple[int, str]:
        """Xóa đúng handle node, không cần khóa -vô-cực."""
        if not node.active:
            raise ValueError("Handle đã bị loại khỏi heap")

        if node.parent is not None:
            parent = node.parent
            self._cut(node, parent)
            self._cascading_cut(parent)

        # Ép node làm gốc được chọn CHỈ BÊN TRONG thao tác delete.
        # extract_min tháo node rồi tái tạo min đúng từ các gốc còn lại.
        self.min = node
        return self.extract_min()
```

**Vì sao `delete` không cần khóa âm vô cực?** Một cách giảng dạy khác là giảm khóa nút cần xóa tới một giá trị thấp hơn mọi khóa, rồi `extract-min`. Nhưng nếu khóa đã có giá trị `-\infty` hoặc kiểu dữ liệu không có phần tử nhỏ nhất đặc biệt, có thể phát sinh nhập nhằng. Trong ví dụ này, `delete` trước hết cắt nút khỏi cha (nếu có), rồi **chọn tạm chính gốc đó làm nút cần loại**, dùng logic tháo nút và hợp nhất của `extract_min`. Con trỏ `min` chỉ có thể không trỏ tới khóa nhỏ nhất **bên trong** lời gọi `delete` đang chạy; nó được khôi phục trước khi API trả về. Cách này không dành cho cấu trúc đồng thời không khóa.

**Điều kiện quan trọng:** handle truyền vào `decrease_key` hoặc `delete` phải thuộc **chính heap hiện tại**. Cờ `active` giúp phát hiện một số handle đã bị lấy/xóa, nhưng không phải là cơ chế xác thực owner; truyền handle từ heap khác vẫn là lỗi của người gọi. Sau `meld`, handle thuộc heap nguồn đã chuyển quyền sử dụng sang heap đích.

### 21.4. Meld hai heap và sử dụng

Phương thức tiếp theo thuộc lớp `FibonacciMinHeap`:

```python
    def meld(self, other: "FibonacciMinHeap") -> None:
        """Chuyển toàn bộ nút của other vào self; other trở thành rỗng."""
        if self is other:
            raise ValueError("Không gộp heap với chính nó")
        if other.min is None:
            return

        if self.min is None:
            self.min = other.min
        else:
            a, b = self.min, other.min
            a_next, b_next = a.right, b.right
            # Nối hai vòng root list bằng đúng 4 phép gán liên kết.
            a.right = b_next
            b_next.left = a
            b.right = a_next
            a_next.left = b
            if b.key < a.key:
                self.min = b

        self.n += other.n
        other.min = None
        other.n = 0
```

Ví dụ gọi sau khi ghép **cả bốn đoạn mã lớp**:

```python
heap = FibonacciMinHeap()
a = heap.insert(7, "A")
b = heap.insert(3, "B")
c = heap.insert(9, "C")
heap.insert(1, "D")

print(heap.minimum())         # (1, "D")
heap.decrease_key(c, 0)
print(heap.minimum())         # (0, "C")
print(heap.extract_min())     # (0, "C")
print(heap.extract_min())     # (1, "D")
print(heap.delete(a))         # (7, "A")
print(heap.extract_min())     # (3, "B")

left = FibonacciMinHeap()
right = FibonacciMinHeap()
left.insert(5, "left")
right.insert(2, "right")
left.meld(right)
print(left.minimum())        # (2, "right")
print(len(right))            # 0: heap nguồn đã bị rút hết nút.
```

### Những giới hạn cố ý của mã minh họa

1. Đây là mã **giảng dạy**, không phải API Python tiêu chuẩn. Python `heapq` không tự dùng cấu trúc Fibonacci heap.
2. Phương thức `_snapshot` tạo danh sách Python tạm khi hợp nhất/chuyển con, nên thời gian và **bộ nhớ phụ thực tế** của đoạn mã có thể lớn hơn một triển khai thao tác trực tiếp trên vòng liên kết.
3. Chưa có hệ thống owner/handle-generation để phát hiện mọi trường hợp dùng sai handle, nhất là qua nhiều heap trước/sau meld.
4. Không bảo đảm rollback nếu xảy ra lỗi cấp phát bộ nhớ trong lúc sửa các vòng con trỏ.
5. Không đồng bộ cho nhiều luồng; mọi cập nhật cấu trúc và `min` cần được bảo vệ nhất quán nếu chia sẻ giữa luồng.
6. Bản Python thường có chi phí object và pointer lớn hơn đáng kể so với `heapq` dùng mảng; mã không được dùng để kết luận hiệu năng bằng một phép đo nhỏ.

## 22. Tìm theo ID: O(1) decrease-key chỉ đúng khi đã có handle

Khi nói `decrease-key` của Fibonacci heap có `O(1)` **khấu hao**, một tiền đề rất quan trọng là:

> Người gọi đã có **handle/con trỏ hợp lệ tới đúng nút** cần giảm khóa.

Nếu ứng dụng chỉ biết:

```text
decrease_priority("job-218", 1)
```

thì cấu trúc heap tự thân không tự xác định `"job-218"` đang là nút nào. Việc duyệt tất cả `n` nút để tìm ID có thể mất `O(n)`, làm mất lợi thế cập nhật.

Giải pháp thường là:

```text
id_to_node: ID -> handle tới FibNode
```

Ví dụ:

```python
heap = FibonacciMinHeap()
handles = {}

handles["A"] = heap.insert(7, "A")
handles["B"] = heap.insert(3, "B")

heap.decrease_key(handles["A"], 1)
print(heap.minimum())  # (1, "A")
```

Với bảng băm tra cứu `O(1)` kỳ vọng, ta có thể xác định handle nhanh, rồi thực hiện `decrease-key` `O(1)` **khấu hao**. Tuy nhiên:

- Cần **xóa hoặc vô hiệu hóa mapping** khi nút bị pop/delete.
- Nếu cùng một ID được dùng lại, cần chính sách version/generation tránh dùng handle của đối tượng cũ.
- `meld` hai heap không tự gộp hai bảng ID trong `O(1)` nếu bảng được quản lý riêng.
- Phải thống nhất owner của các nút, nhất là nếu container trả về đối tượng và giải phóng bộ nhớ.

**Không nên chỉ nói “Fibonacci heap tìm theo ID trong `O(1)`”.** Đó là khả năng của **chỉ mục phụ**, không phải bất biến của bản thân rừng heap.

## 23. Khác biệt với lazy deletion trên binary heap

Hai cách “lười” có thể cùng được nhắc tới trong thuật toán đồ thị nhưng cơ chế khác nhau:

### Fibonacci heap: trì hoãn gom các cây

```text
insert(x)    -> thêm cây một nút
decrease(x)  -> có thể cắt cây con, chưa gom lại
extract-min  -> gom các gốc theo degree
```

Nút trong heap vẫn đại diện cho **một đối tượng logic đang hoạt động**, và thao tác giảm khóa tác động trực tiếp tới nút đó qua handle. Các gốc có thể nhiều cho tới khi consolidate.

### Lazy deletion: chèn phiên bản mới và bỏ bản cũ

Với `heapq` hoặc một heap nhị phân khác, chương trình có thể:

```text
priority của A: 9 -> 4

Thay vì sửa mục cũ:
  push (4, version=2, A)
  giữ (9, version=1, A) nhưng đánh dấu stale.

Khi pop:
  nếu gặp phiên bản stale -> bỏ qua.
```

Ở đây, heap có thể chứa **nhiều bản ghi vật lý cho cùng một ID**. Số mục trong heap có thể lớn hơn số công việc đang hoạt động; mỗi lần `pop` có thể phải bỏ qua nhiều bản ghi lỗi thời.

| Câu hỏi | Fibonacci heap | Lazy deletion với heap mảng |
|---|---|---|
| “Lười” ở đâu? | Trì hoãn gom rừng gốc | Trì hoãn xóa các bản ghi cũ |
| `decrease-key` | Sửa **nút hiện hữu**; có thể cut | Thêm một phiên bản mới |
| Một ID có nhiều bản ghi vật lý? | Không bắt buộc; thường một nút/ID | Có thể có nhiều bản ghi stale |
| Chi phí cập nhật | `O(1)` khấu hao nếu có handle | Thêm bản ghi thường `O(\log m)` |
| Chi phí `extract-min` | `O(\log n)` khấu hao | Một lần gọi nghiệp vụ có thể phải pop nhiều mục stale |
| Bộ nhớ | `O(n)` nút hoạt động, nhiều con trỏ mỗi nút | Có thể `O(m)` với `m\gg n` do stale |

Không được thay hai thuật ngữ này cho nhau trong một bài phân tích. **Fibonacci heap không đạt `O(1)` decrease-key bằng cách giữ các bản ghi cũ lỗi thời**; nó đạt kết quả nhờ **cut, cascading cut và thế năng**.

## 24. Ứng dụng đồ thị: tại sao decrease-key quan trọng?

Một ví dụ kinh điển là thuật toán Dijkstra cho đồ thị có **trọng số cạnh không âm**.

Trong quá trình tìm đường ngắn nhất:

1. Chọn đỉnh chưa xử lý có khoảng cách tạm thời nhỏ nhất: `extract-min`.
2. Xét các cạnh kề và thử cải thiện khoảng cách của các đỉnh khác.
3. Khi tìm được đường ngắn hơn tới một đỉnh còn trong hàng đợi, thực hiện `decrease-key`.

Gọi:

- `V`: số đỉnh.
- `E`: số cạnh.

Nếu mỗi đỉnh có **một nút đang hoạt động** trong Fibonacci heap, và ứng dụng có handle để cập nhật trực tiếp:

- Có `O(V)` lần `extract-min`, mỗi lần `O(\log V)` khấu hao.
- Có tối đa `O(E)` lần thử cải thiện dẫn tới `decrease-key`, mỗi lần `O(1)` khấu hao.
- Khởi tạo hoặc thêm các đỉnh mất `O(V)` công việc cấu trúc.

Vì vậy, với mô hình so sánh thông dụng và adjacency list:

\[
\boxed{T_{\text{Dijkstra+Fib heap}}=O(E+V\log V)}
\]

cho phần chạy thuật toán và thao tác hàng đợi.

So với cách phân tích quen thuộc của binary heap có indexed decrease-key:

\[
O((V+E)\log V),
\]

Fibonacci heap **loại bỏ hệ số `\log V` khỏi phần giảm khóa** ở cận khấu hao.

### Những điều kiện không được bỏ qua

- Dijkstra chuẩn yêu cầu **trọng số cạnh không âm**; heap Fibonacci không sửa được giới hạn này.
- Ứng dụng phải có **handle tới nút của từng đỉnh còn trong heap** hoặc một chỉ mục phù hợp.
- Nếu dùng cách thêm nhiều bản ghi cho một đỉnh rồi bỏ qua stale, đó là **biến thể cài đặt khác**; không thể áp nguyên cận decrease-key trực tiếp của Fibonacci heap vào nó.
- Cận `O(E+V\log V)` là **bảo đảm tiệm cận**; trên đồ thị nhỏ hoặc trong hệ thống cần cache locality tốt, binary heap hay d-ary heap có thể nhanh hơn trong thực tế.

Fibonacci heap cũng xuất hiện trong phân tích thuật toán Prim và những thuật toán sử dụng rất nhiều lần thay khóa, nhưng lựa chọn thực tế phải dựa trên workload, hiện thực và hằng số chi phí.

## 25. Đánh đổi hiệu năng và lựa chọn cấu trúc

### Ưu điểm của Fibonacci heap

- **Giảm khóa `O(1)` khấu hao:** hấp dẫn khi số lần giảm khóa lớn.
- **Meld `O(1)`:** thuận tiện nếu thường xuyên hợp nhất hàng đợi mà không cần gộp chỉ mục phụ.
- **Insert `O(1)`:** không bắt buộc gom cây sau mỗi lần thêm.
- **Find-min `O(1)`:** con trỏ `min` luôn được duy trì.
- **Extract-min `O(\log n)` khấu hao:** hợp nhất làm giảm số gốc về `O(\log n)`.

### Chi phí và nhược điểm

- **Nhiều con trỏ trên mỗi nút:** `parent`, `child`, `left`, `right`, cùng `degree` và `mark` làm tăng bộ nhớ so với một heap mảng.
- **Truy cập rải rác:** các nút có thể nằm ở nhiều nơi trong heap bộ nhớ, gây *pointer chasing* và cache miss.
- **Mã phức tạp:** cắt dây chuyền, cập nhật vòng liên kết, hợp nhất theo bậc, hủy nút và xử lý ngoại lệ dễ sinh lỗi.
- **Không phải thời gian xấu nhất của từng lần gọi:** `decrease-key` có thể cắt nhiều tổ tiên; `extract-min` có thể phải duyệt nhiều gốc.
- **Cần handle và chính sách vòng đời:** nếu ứng dụng chỉ có ID, phải thêm bảng ánh xạ; nếu không thì tìm tuyến tính.
- **Khó tối ưu trong ngôn ngữ quản lý đối tượng:** overhead cấp phát nhiều object có thể che khuất ưu thế Big-O trong bài toán nhỏ.

### So sánh với một số lựa chọn

| Nhu cầu | Cấu trúc nên cân nhắc | Vì sao |
|---|---|---|
| Chủ yếu `push` và `pop`, dữ liệu vừa phải | Binary heap | Đơn giản, dùng mảng, locality tốt |
| Nhiều `decrease-key`, cần điều chỉnh chiều cao/so sánh | Indexed d-ary heap | Giảm số tầng, nhưng sift-down phải quét nhiều con |
| Rất nhiều `decrease-key`, phân tích tiệm cận là trọng tâm | Fibonacci heap | `O(1)` khấu hao cho decrease-key |
| Thường xuyên gộp hai hàng đợi và có handle | Fibonacci heap | Meld `O(1)` với cấu trúc thuần |
| Tìm/xóa theo ID là thao tác chính | Heap + bảng ID hoặc cây tìm kiếm | Heap-order không tự tìm ID nhanh |
| Cần cận xấu nhất nghiêm ngặt cho từng lời gọi | Cấu trúc có bảo đảm worst-case phù hợp | Fibonacci heap kinh điển chủ yếu cho bảo đảm khấu hao |

**Không có một heap “nhanh nhất” cho mọi ứng dụng.** Số lần thao tác, kích thước khóa, cách cấp phát bộ nhớ, cache, yêu cầu worst-case và độ tin cậy triển khai đều quan trọng.

## 26. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm hoặc lỗi | Vì sao sai? | Cách ghi nhớ |
|---|---|---|
| “Fibonacci heap là cây nhị phân hoàn chỉnh.” | Nó là **rừng** các cây heap-ordered, không yêu cầu hoàn chỉnh | Tách Fibonacci heap khỏi binary heap |
| “Mọi gốc phải được sắp theo khóa.” | Root list không có thứ tự toàn phần | Duy trì một con trỏ `min` |
| “Insert phải consolidate ngay.” | Cơ chế lười cố ý trì hoãn | Thêm cây một nút vào root list |
| “`decrease-key` là `O(1)` worst-case.” | Có thể cut dây chuyền | `O(1)` **khấu hao** |
| “`extract-min` luôn `O(\log n)` worst-case.” | Có thể có `\Theta(n)` gốc trước khi gom | `O(\log n)` **khấu hao** |
| “Cắt nút làm mất cả các con của nó.” | Cắt nút cùng **toàn bộ cây con** | `degree(x)` giữ nguyên khi cắt `x` |
| “Khi một nút mất con đầu tiên phải cắt ngay.” | Nếu không phải gốc, lần đầu thường chỉ **mark** | Mất lần hai mới cắt dây chuyền |
| “Root cũng có thể mark=true.” | Root không có cha để kiểm soát mất con | Đặt `mark=false` cho gốc |
| “Khi link dưới cha mới, giữ nguyên mark.” | Dấu phản ánh mất con kể từ **lần link mới** | Reset mark khi LINK |
| “Gộp bất kỳ hai cây là được.” | Consolidate cần hai **gốc cùng degree** | Link theo degree, chọn cha có khóa nhỏ hơn |
| “`degree` là số hậu duệ.” | `degree` là số **con trực tiếp** | Dùng `child` list để đếm/check |
| “Bậc tối đa là `O(n)` vì không cân bằng.” | Mark+cascading cut đảm bảo cận dưới kích thước cây | `degree=O(\log n)` |
| “Bậc `O(\log n)` nghĩa là chiều cao cũng `O(\log n)`.” | Hai đại lượng khác nhau | Không suy ra chiều cao từ degree bound |
| “Khấu hao là trung bình trên dữ liệu ngẫu nhiên.” | Không cần giả định xác suất đầu vào | Phương pháp thế năng |
| “`\Phi=t+2m` là thời gian thực đo được.” | Thế năng là công cụ phân tích | Nhìn nó như khoản tín dụng |
| “Meld luôn `O(1)` cho cả bảng ID ngoài heap.” | Gộp bảng ánh xạ có thể tốn chi phí | Phân biệt heap thuần với hệ thống bọc |
| “Biết ID thì đã có handle.” | Heap không tự lập chỉ mục theo ID | Duy trì `id→node` nếu cần |
| “Lazy deletion của `heapq` chính là Fibonacci heap.” | Một bên giữ stale records, một bên trì hoãn gom cây | Phân biệt hai loại “lười” |
| “Có thể dùng handle sau khi nút đã bị xóa.” | Dẫn tới con trỏ treo hoặc sửa mục không còn trong heap | Quản lý vòng đời/active flag |
| “Nối vòng đôi không cần xử lý danh sách một nút.” | Dễ hỏng liên kết khi xóa gốc/con cuối | Kiểm tra self-link và empty |
| “Hai heap meld xong vẫn là hai owner độc lập.” | Có thể chia sẻ cùng vòng nút, dẫn tới sửa/hủy hai lần | Quy định rõ heap nguồn bị rút rỗng |
| “Cấu trúc đã nhanh Big-O nên chắc nhanh hơn `heapq`.” | Pointer chasing, cấp phát và mã phức tạp có overhead | Benchmark theo workload thật |

## 27. Bài tập tự kiểm tra

**Bài 1.** Nêu hai khác biệt quan trọng giữa **binary heap** và **Fibonacci heap** về hình dạng và thao tác thêm mới.

**Bài 2.** Một Fibonacci min-heap có danh sách gốc với khóa `[9,4,12,2]`. Gốc `min` phải trỏ tới nút nào? Phép `find-min` cần duyệt bao nhiêu gốc?

**Bài 3.** Bắt đầu heap rỗng, thực hiện `insert(8)`, `insert(3)`, `insert(6)`, `insert(1)` mà chưa `extract-min`. Heap có bao nhiêu gốc, bao nhiêu nút mark và thế năng bằng bao nhiêu?

**Bài 4.** Hai heap có lần lượt `t_1=3,m_1=1` và `t_2=2,m_2=2`. Sau khi meld thuần bằng nối root list, tổng số gốc, tổng số mark và thế năng mới là bao nhiêu?

**Bài 5.** Hai gốc `x` và `y` cùng bậc `2`, có khóa lần lượt `5` và `3`. Khi consolidate, nút nào làm cha? Degree của gốc mới là bao nhiêu?

**Bài 6.** Tại sao `extract-min` phải đưa các con của gốc bị xóa vào danh sách gốc trước khi hợp nhất?

**Bài 7.** Một nút `x` là con của `y`, có khóa `7`; `y` có khóa `4`. Nếu `decrease-key(x,5)` thì có phải cut không? Nếu giảm thành `2` thì sao?

**Bài 8.** Một nút không phải gốc `y` có `mark=false` và vừa mất một con. Hành động đối với `y` là gì? Nếu `mark=true` thì hành động khác như thế nào?

**Bài 9.** Vì sao khi `CUT(x,y)` chuyển `x` lên root list, `degree(y)` giảm một nhưng `degree(x)` không đổi?

**Bài 10.** Khi hai nút `a` và `b` đang là gốc, có thể giữ `mark(a)=true` để ghi nhận chúng từng mất con không? Vì sao?

**Bài 11.** Nêu ý nghĩa của `t(H)`, `m(H)` và công thức `\Phi(H)`. Một heap có `t=5`, `m=3` thì thế năng bằng bao nhiêu?

**Bài 12.** Nếu một lần giảm khóa thực hiện `c=4` lần cut, số gốc tăng bao nhiêu? Theo phân tích thế năng, số nút mark có thể tăng tối đa bao nhiêu?

**Bài 13.** Vì sao không thể kết luận `decrease-key` chạy `O(1)` **trong mọi lần gọi** chỉ từ kết quả `O(1)` khấu hao?

**Bài 14.** Sau `100` lần insert vào heap rỗng mà chưa gom, một lần `extract-min` có thể phải làm `\Theta(100)` bước. Điều đó có mâu thuẫn với `O(\log n)` khấu hao không? Giải thích ngắn bằng thế năng.

**Bài 15.** Hãy phát biểu cận dưới kích thước cây có gốc bậc `k` theo Fibonacci và hệ quả cho bậc lớn nhất khi heap có `n` nút.

**Bài 16.** Vì sao `degree=O(\log n)` không tương đương “mỗi cây của Fibonacci heap cân bằng với chiều cao `O(\log n)`”?

**Bài 17.** Ứng dụng chỉ có ID `"job-17"` chứ không có con trỏ tới nút. Có thể viện dẫn ngay `O(1)` decrease-key của Fibonacci heap cho thao tác theo ID không? Cần bổ sung gì?

**Bài 18.** So sánh “trì hoãn gom cây” của Fibonacci heap với “xóa lười bằng bản ghi stale” trong binary heap.

**Bài 19.** Với `V` đỉnh và `E` cạnh không âm trong Dijkstra, nêu cận thời gian thường dùng khi có handle và dùng Fibonacci heap. Lợi ích đến từ thao tác nào?

**Bài 20.** Một nhóm định dùng Fibonacci heap để xử lý một triệu yêu cầu, chủ yếu `push/pop` và ít `decrease-key`. Cần cân nhắc những yếu tố gì trước khi chọn thay vì binary heap?

### Đáp án và giải thích

1. Binary heap là **một cây nhị phân hoàn chỉnh**, thường lưu bằng mảng; Fibonacci heap là **rừng nhiều cây heap-ordered**, thường lưu bằng liên kết đôi vòng. Binary heap thêm cuối rồi đẩy lên; Fibonacci heap có thể nối một **cây một nút** vào root list.
2. `min` trỏ nút có khóa `2`. `find-min` đọc trực tiếp con trỏ ấy, không cần duyệt các gốc, nên `O(1)`.
3. Có `4` gốc một nút, `m=0`, `\Phi=4+2\cdot0=4`; `min` trỏ nút khóa `1`.
4. `t=3+2=5`, `m=1+2=3`, `\Phi=5+2\cdot3=11`. Thế năng tổng bằng tổng thế năng hai heap trước meld.
5. Nút khóa `3` làm cha của nút khóa `5`; bậc cha mới tăng từ `2` lên `3`; con vừa được link có `parent` mới và `mark=false`.
6. Chúng là những cây con còn tồn tại sau khi gốc cũ bị xóa, nên phải trở thành gốc để không mất nút. Sau đó mới hợp nhất những gốc cùng degree.
7. Giảm từ `7` xuống `5` vẫn thỏa `4\le5` nên không cắt. Giảm xuống `2` tạo `2<4`, phải cắt `x` khỏi `y` rồi có thể đánh dấu/cắt dây chuyền từ `y`.
8. Nếu `mark=false`, đánh dấu `mark(y)=true` vì mới mất con đầu tiên. Nếu `mark=true` mà lại mất con, cắt `y` khỏi cha, xóa mark khi thành gốc và tiếp tục xét cha cũ.
9. `y` vừa mất một **con trực tiếp** nên degree giảm. Các con **của `x`** vẫn ở dưới `x`, vì cả cây con đi cùng khi cắt; degree của `x` không đổi.
10. Không. Gốc không có cha nên không có ý nghĩa đánh dấu theo quy tắc mất con. Khi thành gốc, `mark=false`.
11. `t` là số cây/gốc, `m` là số nút mark; `\Phi=t+2m`. Với `t=5,m=3`, `\Phi=5+6=11`.
12. `\Delta t=4`. Có ít nhất `3` tổ tiên đã mark bị cắt và tối đa một mark mới, nên `\Delta m\le1-3=-2`. Số nút mark **giảm ít nhất hai**, không phải tăng.
13. Một lần gọi có thể gây nhiều lần cut theo đường tổ tiên. Cận `O(1)` chỉ có ý nghĩa **khấu hao trên chuỗi thao tác**, khi dùng thế năng để bù chi phí của lần đắt.
14. Không. `100` lần insert làm tăng `t` và thế năng lên `100`; một lần extract-min có thể dùng khoản thế năng ấy khi gom nhiều gốc. Khấu hao không yêu cầu lần nào cũng chỉ `O(\log n)` thực tế.
15. Cây có gốc bậc `k` có ít nhất `F_{k+2}` nút. Vì `F_{k+2}=\Omega(\varphi^k)`, nếu toàn heap có `n` nút thì `k=O(\log_\varphi n)=O(\log n)`.
16. Degree đếm **con trực tiếp**, không phải số cạnh đường gốc–lá. Những cây vẫn có thể có hình dạng không cân bằng; phân tích heap dựa vào ràng buộc mất con và cận degree.
17. Không, vì tìm nút theo ID có thể `O(n)`. Cần giữ bảng `id\to node` hoặc handle hợp lệ để truy cập đúng nút trước khi gọi `decrease-key`.
18. Fibonacci heap giữ một nút logic và **trì hoãn hợp nhất root list**; lazy deletion thường thêm bản ghi mới và giữ bản ghi cũ **stale** cho tới khi pop/dọn. Chúng khác bất biến, chi phí và bộ nhớ.
19. Với trọng số không âm, adjacency list và handle cho mỗi đỉnh, Dijkstra với Fibonacci heap có cận `O(E+V\log V)`. Lợi ích chủ yếu đến từ tối đa `O(E)` lần `decrease-key` có `O(1)` **khấu hao**.
20. Cân nhắc tỷ lệ push/pop so với decrease-key, overhead của nhiều con trỏ/object, cache locality, chi phí cấp phát/hủy, độ phức tạp triển khai, yêu cầu worst-case/khấu hao và benchmark trên tải thực. Binary heap thường đơn giản hơn nếu ít giảm khóa.

## 28. Tổng kết

**Fibonacci heap** là một **rừng cây có thứ tự heap**, duy trì danh sách gốc và con trỏ `min`. Cấu trúc này **trì hoãn hợp nhất các cây** khi thêm hoặc giảm khóa, rồi thực hiện **consolidation theo bậc** khi lấy gốc. Với `decrease-key`, Fibonacci heap dùng **cut, mark và cascading cut** để bảo vệ cận kích thước cây theo dãy Fibonacci, từ đó giữ bậc lớn nhất `O(\log n)`. Hàm thế năng **`\Phi(H)=t(H)+2m(H)`** giải thích vì sao `insert`, `meld`, `find-min` và `decrease-key` có **`O(1)` khấu hao**, trong khi `extract-min` và `delete` có **`O(\log n)` khấu hao**. Những cận này **không phải** bảo đảm thời gian xấu nhất của từng lần gọi. Ưu thế tiệm cận đặc biệt đáng chú ý khi thuật toán thực hiện rất nhiều **decrease-key** và đã có **handle** đến nút, chẳng hạn Dijkstra. Trong ứng dụng thực, cần cân bằng lợi ích lý thuyết với chi phí con trỏ, bộ nhớ đệm, cấp phát, quản lý vòng đời và độ phức tạp cài đặt trước khi chọn Fibonacci heap thay cho binary heap hoặc d-ary heap.

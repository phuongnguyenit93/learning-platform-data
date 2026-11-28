# Skip list và các tầng liên kết bỏ qua

Một **danh sách liên kết đơn có thứ tự** giúp chèn/xóa một nút khi đã biết vị trí với chi phí O(1), nhưng muốn tìm khóa `k` vẫn phải đi qua từng nút từ đầu: thời gian **O(n)** trong trường hợp xấu nhất. Ngược lại, **mảng đã sắp xếp** cho phép tìm nhị phân O(log n), nhưng chèn/xóa ở giữa có thể phải dịch O(n) phần tử.

**Skip list** (danh sách bỏ qua) giải quyết sự đánh đổi này bằng cách bổ sung **nhiều tầng con trỏ chuyển tiếp**. Tầng thấp nhất chứa mọi khóa; tầng cao chỉ chứa một số khóa, giúp ta “nhảy” qua những đoạn dài. Với cách lựa chọn chiều cao nút bằng xác suất phù hợp, tìm, chèn, xóa đều đạt **O(log n) kỳ vọng**, còn duyệt khóa tăng dần chỉ cần đi theo một dãy liên kết ở tầng đáy.

Bài **“Skip list và các tầng liên kết bỏ qua”** thuộc chương **Cấu trúc ngẫu nhiên**, module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong phạm vi module học mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, ta tiếp tục đặt trọng tâm vào **bất biến cấu trúc**, các thao tác **tìm–thêm–xóa**, **vòng đời liên kết** và **độ phức tạp thời gian/bộ nhớ** để chọn cấu trúc đúng với bài toán. Skip list là ví dụ điển hình cho việc **ngẫu nhiên hóa cấu trúc**, không phải đòi dữ liệu nhập phải có thứ tự ngẫu nhiên.

**Sau bài học, bạn có thể:**

- Vẽ các tầng của skip list và giải thích vai trò của `head`, `forward[i]`, tầng đáy và nút có nhiều liên kết.
- Mô phỏng đường tìm kiếm **đi sang phải khi chưa vượt khóa, rồi đi xuống một tầng**; tìm `lower_bound` và tiền nhiệm.
- Xây mảng `update[]` để nối hoặc bỏ nút đúng ở từng tầng khi chèn/xóa.
- Giải thích phân phối chiều cao hình học theo xác suất `p`, tính số con trỏ kỳ vọng và phân biệt **kỳ vọng** với **worst-case**.
- Cài đặt một **skip list set** Python hoàn chỉnh có `contains`, `insert`, `discard`, `lower_bound`, duyệt khoảng, kiểm định và kiểm thử.
- Phân tích tác động của `MAX_LEVEL`, seed/PRNG, va chạm khóa, quản lý con trỏ, iterator và cập nhật đồng thời.
- Nhận biết khi nào nên mở rộng skip list bằng **span/width** để hỗ trợ `rank`/`select`, và khi nào cây cân bằng tất định có lợi hơn.

## 1. Vì sao cần “bỏ qua” những nút ở giữa?

### 1.1. Danh sách liên kết có thứ tự

Xét tập khóa:

```text
HEAD -> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 70 -> 80 -> NULL
```

Để biết `70` có trong danh sách không, ta phải kiểm tra từ 10, 20, 30 ... đến 70. Nếu tìm một khóa lớn hơn mọi khóa đã có, ta có thể đi qua toàn bộ `n` nút.

Với một danh sách liên kết thông thường:

| Thao tác | Chi phí |
| --- | --- |
| Tìm một khóa bất kỳ | O(n) |
| Tìm tiền nhiệm để chèn/xóa | O(n) |
| Nối nút mới sau khi **đã có con trỏ tiền nhiệm** | O(1) |
| Bỏ nút sau khi **đã có con trỏ tiền nhiệm** | O(1) |
| Duyệt toàn bộ từ bé đến lớn | O(n) |

Vì phần tốn kém nằm ở **định vị**, skip list chủ yếu tìm cách tạo ra các **đường đi tắt**.

### 1.2. Thêm những “làn nhanh” có thứ tự

Ta giữ nguyên toàn bộ chuỗi tầng đáy, rồi thêm các liên kết từ một số nút lên các tầng cao hơn:

```text
L3: HEAD ---------------------> 40 ---------------------> NULL
L2: HEAD ----> 10 ------------> 40 ----------------> 80 -> NULL
L1: HEAD ----> 10 ----> 30 ---> 40 ----> 60 --------> 80 -> NULL
L0: HEAD ----> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 70 -> 80 -> NULL
                 ^                     ^
            Một node 10          Một node 40
            ở L0,L1,L2         ở L0,L1,L2,L3
```

**L0** là tầng đáy (chỉ số 0 trong code), **L3** là tầng cao nhất. Trong ví dụ, nút 40 xuất hiện ở bốn tầng nhưng **không phải bốn bản sao dữ liệu**: đó là **một node** có bốn ô `forward[0..3]`.

Một cách biểu diễn giản lược:

```text
Nút key=40:
+----------------+
| key: 40        |
| forward[3] ->  |
| forward[2] ->  |
| forward[1] ->  |
| forward[0] ->  |
+----------------+

Mỗi forward[i] nhảy tới NODE KẾ TIẾP có mặt ở tầng i,
không phải tới một bản sao của node ấy.
```

### 1.3. Tại sao không phải “tìm nhị phân trên danh sách”?

Tìm nhị phân trên mảng dựa vào phép truy cập `array[mid]` O(1). Danh sách liên kết đơn không có truy cập ngẫu nhiên theo chỉ số: muốn tới phần tử giữa cũng phải đi qua các liên kết.

Skip list **không** liên tục chia mảng đôi theo chỉ số. Nó cho phép một bước đi sang phải **bỏ qua nhiều nút** vì liên kết tầng cao đã được lưu sẵn. Do đó, cấu trúc vẫn dựa trên danh sách liên kết, nhưng có **chỉ mục phân cấp** để giảm số bước định vị theo kỳ vọng.

## 2. Mô hình nút, tầng và năm bất biến cốt lõi

Với các khóa nguyên duy nhất, một mô hình đơn giản là:

```text
SkipNode:
    key        : khóa (chỉ có ở nút dữ liệu)
    forward[0] : nút kế tiếp trên tầng đáy
    forward[1] : nút kế tiếp trên tầng 1 (nếu có)
    ...
    forward[L-1] : nút kế tiếp trên tầng cao nhất của nó

SkipList:
    head       : sentinel trước mọi khóa
    level      : số tầng hiện đang sử dụng
    size       : số khóa dữ liệu
    p          : xác suất nâng thêm một tầng
    MAX_LEVEL  : giới hạn số tầng được phép
```

**Độ cao nút `H`** là **số tầng** node tham gia, ít nhất 1. Nút có `H=3` tham gia các tầng **0, 1, 2**. Không nhầm `H=3` với “chỉ số tầng cao nhất bằng 3”.

### 2.1. Bất biến I — tầng 0 chứa mọi khóa đúng một lần

```text
L0: HEAD -> k1 -> k2 -> ... -> kn -> NULL
           k1 < k2 < ... < kn
```

Trong phiên bản **set**, khóa không trùng. Nếu dữ liệu là multiset, phải đặt quy tắc rõ về khóa lặp (ví dụ đếm `count` tại một node hoặc dùng khóa ghép `(value, unique_id)`).

### 2.2. Bất biến II — mỗi tầng cao là một dãy con có thứ tự

Tầng `i>0` chỉ chứa các nút có `H≥i+1`; thứ tự khóa vẫn tăng dần. Một nút có mặt ở tầng i thì cũng có mặt ở **tất cả các tầng thấp hơn**, không có “lỗ thủng” giữa các tầng.

Ví dụ độ cao trên hình:

| Khóa | `H` | Các tầng có mặt |
| --- | ---: | --- |
| 10 | 3 | L0, L1, L2 |
| 20 | 1 | L0 |
| 30 | 2 | L0, L1 |
| 40 | 4 | L0, L1, L2, L3 |
| 50 | 1 | L0 |
| 60 | 2 | L0, L1 |
| 70 | 1 | L0 |
| 80 | 3 | L0, L1, L2 |

### 2.3. Bất biến III — mỗi `forward[i]` có ý nghĩa duy nhất

Nếu `u.forward[i] = v` thì `v` là **nút tiếp theo có mặt ở tầng i**, lớn hơn `u.key` và **không có nút ở tầng i nào nằm giữa u và v**. Một con trỏ không bao giờ được trỏ về khóa nhỏ hơn hoặc trỏ lại chính nó.

Điều này khác với node của cây nhị phân: mỗi liên kết trong skip list là **“next trên một tầng”**, không phải quan hệ cha–con. Không được chạy một destructor cây theo từng `forward[i]` rồi giải phóng cùng một node nhiều lần.

### 2.4. Bất biến IV — head và mức cao nhất

`head` là **nút sentinel**, đứng trước mọi khóa. Nó không được xem là khóa số nhỏ nhất nếu loại khóa không có giá trị “âm vô cùng” hợp lệ. Một sentinel có thể dùng `key=None` và các phép so sánh chỉ áp dụng lên node dữ liệu.

Nếu có dữ liệu, tầng cao nhất đang dùng nên chứa ít nhất một node thật. Nếu danh sách rỗng, giữ đúng **một tầng 0** làm trạng thái đơn giản; mọi liên kết `head.forward[i]` đều rỗng.

### 2.5. Bất biến V — liên kết được quản lý theo danh tính nút

Dù node 40 xuất hiện ở bốn tầng, nó chỉ là **một đối tượng** và một khóa logic. Thống kê `size` đếm số node ở **tầng đáy**, không đếm tổng số mũi tên `forward`.

Trong C/C++, nếu node bị xóa, phải loại nó khỏi **mọi tầng đang tham gia trước khi giải phóng**. Nếu còn một `forward[i]` trỏ tới vùng đã hủy, truy cập skip list về sau có thể gây use-after-free.

## 3. Tìm kiếm: sang phải, rồi xuống tầng

Tìm kiếm một khóa `target` bắt đầu từ `HEAD` ở tầng cao nhất.

**Quy tắc:**

1. Xét `next = current.forward[level]`.
2. Nếu `next` có khóa **nhỏ hơn** target, đi sang phải: `current = next`.
3. Nếu `next` rỗng hoặc khóa next **không nhỏ hơn** target, xuống một tầng.
4. Ở tầng 0, `current.forward[0]` là node đầu tiên có khóa **≥ target**, nếu tồn tại.

Tại sao dùng `next.key < target` thay vì `<=`? Vì ta muốn **dừng trước** khóa bằng target để kiểm tra nó, đồng thời lấy được **tiền nhiệm** cho chèn/xóa.

### 3.1. Ví dụ tìm `55`

Dùng các tầng ở Mục 1:

```text
L3: HEAD -------> 40 -------> NULL
L2: HEAD -> 10 -> 40 -------> 80 -> NULL
L1: HEAD -> 10 -> 30 -> 40 -> 60 -> 80 -> NULL
L0: HEAD -> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 70 -> 80 -> NULL
```

Dấu vết:

| Tầng | Vị trí khi vào | Hành động | Tiền nhiệm khi xuống |
| --- | --- | --- | --- |
| L3 | HEAD | `40 < 55` nên đi phải tới 40; tiếp theo NULL | 40 |
| L2 | 40 | Liên kết tiếp đến 80, không đi vì `80 ≥ 55` | 40 |
| L1 | 40 | Liên kết tiếp đến 60, không đi vì `60 ≥ 55` | 40 |
| L0 | 40 | `50 < 55` nên đi tới 50; tiếp theo 60 không nhỏ hơn 55 | 50 |

Sau khi hết tầng, ứng viên ở `50.forward[0]` là **60**, nhưng `60 != 55`; kết luận **55 chưa có**. Đồng thời ta đã tìm được vị trí cần chèn 55 ở tầng 0: **nằm giữa 50 và 60**.

### 3.2. Ví dụ tìm `60`

Dấu vết có thể dừng ở tầng 1 trước nút 60 vì quy tắc dùng `<`, không đi ngang qua khóa bằng target. Ở tầng 0, node kế tiếp có key 60 nên `contains(60) == True`.

### 3.3. Pseudocode tìm khóa

```text
CONTAINS(target):
    current = head

    for level from highest_used_level down to 0:
        while current.forward[level] != null
              and current.forward[level].key < target:
            current = current.forward[level]

    candidate = current.forward[0]
    return candidate != null and candidate.key == target
```

Bộ duyệt **không bắt đầu lại từ HEAD ở mỗi tầng**: vì `current` đã nằm trước target, khi xuống tầng thấp hơn nó vẫn là tiền nhiệm khả dĩ. Đây là chi tiết làm thuật toán tận dụng tối đa các đường nhảy.

### 3.4. Bất biến của vòng tìm kiếm

Ở cuối quá trình xử lý tầng `i`, `current` là nút có khóa **nhỏ hơn target** xa bên phải nhất có thể đến được theo tầng i từ vị trí đã chọn. Không có liên kết forward ở tầng i nào cho phép đi tiếp sang phải mà vẫn giữ key nhỏ hơn target.

Khi xuống tầng i−1, node `current` cũng thuộc tầng đó; ta có thể tiếp tục từ nó. Đến tầng 0, node ngay sau `current` là **ứng viên nhỏ nhất ≥ target**. Vì L0 chứa tất cả node, thuật toán không thể bỏ qua một khóa bằng target.

## 4. Từ tìm kiếm sang `lower_bound`, tiền nhiệm và duyệt khoảng

Quá trình tìm kiếm ở trên cung cấp nhiều thao tác chỉ bằng cách đổi kết quả cuối:

- `contains(k)`: ứng viên tồn tại và key bằng k.
- **`lower_bound(k)`**: ứng viên nhỏ nhất có key **≥ k**, kể cả khi k chưa xuất hiện.
- **Tiền nhiệm chặt (`predecessor(k)`)**: khóa lớn nhất **< k**, nếu có. `current` có thể là HEAD, khi ấy chưa có tiền nhiệm.
- **Phần tử kế tiếp (`successor(k)`)**: khóa nhỏ nhất **> k**; tìm bằng việc đi ngang qua khóa bằng k ở tầng 0 (hoặc dùng tìm với điều kiện `<=` trên các tầng).

Ví dụ trên `[10,20,30,40,50,60,70,80]`:

| Truy vấn | Kết quả |
| --- | --- |
| `contains(55)` | False |
| `lower_bound(55)` | 60 |
| `predecessor(55)` | 50 |
| `lower_bound(60)` | 60 |
| `successor(60)` | 70 |
| `lower_bound(99)` | Không có |
| `predecessor(10)` | Không có |

### 4.1. Range query

Muốn trả các khóa trong khoảng **`[low, high)`**:

1. Dùng skip list tìm `lower_bound(low)`.
2. Đi theo các con trỏ `forward[0]`, trả từng khóa khi `key < high`.
3. Dừng khi tới NULL hoặc gặp key ≥ high.

Với `k` kết quả, thời gian kỳ vọng là **O(log n + k)** (khởi tạo tìm điểm đầu và xuất k phần tử), khi các giả định xác suất của skip list đúng. Nếu `low>=high`, có thể trả rỗng mà không cần duyệt.

**Cần phân biệt thời gian định vị với thời gian xuất kết quả:** dù tìm bắt đầu O(log n), xuất 100.000 khóa vẫn cần ít nhất Ω(100.000) bước.

### 4.2. Tại sao range query thuận tiện hơn trên tầng đáy?

Các node có thứ tự tăng sẵn và mỗi node ở tầng 0 có con trỏ đến node tiếp. Sau khi định vị `low`, không cần tìm lại từ HEAD cho từng khóa. Trong ứng dụng cần xử lý luồng dữ liệu, có thể yield từng khóa thay vì tạo list O(k) trước khi trả.

## 5. Mảng tiền nhiệm `update[]`: chìa khóa để chèn và xóa

Để **tìm** chỉ cần biết tiền nhiệm tầng 0. Nhưng để **chèn** một node có độ cao `H`, ta cần biết **tiền nhiệm đúng trên từng tầng `0..H-1`**.

Thay vì tìm lại từ đầu `H` lần, ta lưu các tiền nhiệm trong quá trình đi từ tầng cao xuống thấp:

```text
update[i] = node đứng ngay trước vị trí target ở tầng i
            (có thể là HEAD)
```

### 5.1. Ví dụ `update` khi chèn 55

Trên hình L3..L0:

```text
update[3] = 40
update[2] = 40
update[1] = 40
update[0] = 50
```

Giả sử node 55 được bốc **H=2** (tham gia L0 và L1). Ta chỉ cập nhật:

```text
Tầng L0 trước: 50 ------> 60
Tầng L0 sau : 50 -> 55 -> 60

Tầng L1 trước: 40 ------> 60
Tầng L1 sau : 40 -> 55 -> 60

Tầng L2/L3: giữ nguyên; node 55 không xuất hiện ở đó.
```

Mỗi tầng chèn cần hai phép nối:

```text
fresh.forward[i]    = update[i].forward[i]
update[i].forward[i] = fresh
```

**Thứ tự gán rất quan trọng.** Phải lưu successor cũ vào `fresh.forward[i]` **trước khi** thay `update[i].forward[i]`; nếu đảo thứ tự và đọc successor sau, có thể tự tạo vòng `fresh -> fresh` hoặc làm mất đoạn danh sách.

### 5.2. Pseudocode tạo `update[]`

```text
FIND_PREDECESSORS(key):
    update = array of size MAX_LEVEL
    current = head

    for level from current_highest down to 0:
        while current.forward[level] exists
              and current.forward[level].key < key:
            current = current.forward[level]
        update[level] = current

    return update
```

Các tầng đang chưa dùng không được ghi bằng một node ngẫu nhiên. Khi node mới cao hơn mức hiện tại, tiền nhiệm ở những tầng mới đó chính là **HEAD**, vì trước đó các tầng ấy chưa chứa node nào.

### 5.3. Cần lưu `update` tới đâu?

Trong một phiên bản có `MAX_LEVEL=L`, ta có thể cấp một mảng `update` kích thước L mỗi lần chèn/xóa, hoặc chỉ kích thước bằng mức đang dùng rồi mở rộng khi biết chiều cao node mới.

- Mảng kích thước L: đơn giản, chi phí O(L) bộ nhớ tạm.
- Mảng kích thước mức đang dùng `H_current`: tiết kiệm hơn khi `H_current << L`, nhưng phải xử lý việc node mới được bốc cao hơn mức đang dùng.

Trong code thực hành, ta chọn **mảng L cố định** để hợp đồng về giới hạn tài nguyên và cách cập nhật dễ kiểm chứng. Với L được cấu hình nhỏ theo workload, sự đánh đổi này thường chấp nhận được.

## 6. Chọn chiều cao ngẫu nhiên theo phân phối hình học

Thay vì mỗi node có cùng độ cao, skip list bốc **số tầng tham gia** bằng những lần “tung đồng xu” độc lập.

Chọn `p` là xác suất **nâng thêm một tầng**, với `0 < p < 1`:

```text
H = 1

while H < MAX_LEVEL and random() < p:
    H += 1

return H
```

Nếu `p=1/2`, mỗi lần tung thành công làm node lên thêm một tầng. Từng node bốc chiều cao **độc lập với giá trị khóa** và độc lập với chiều cao của node khác theo mô hình lý tưởng.

### 6.1. Phân phối khi không đặt trần

Với `H≥1` (mức 1 nghĩa là chỉ có tầng 0):

\[
\Pr(H\ge k)=p^{k-1}, \quad k\ge1.
\]

Để đạt ít nhất mức k, cần `k-1` lần nâng thành công liên tiếp. Xác suất node có **đúng mức k** là:

\[
\Pr(H=k)=(1-p)p^{k-1}.
\]

Với `p=1/2`:

| Số tầng `H` | Xác suất đúng `H` |
| --- | ---: |
| 1 | 1/2 |
| 2 | 1/4 |
| 3 | 1/8 |
| 4 | 1/16 |
| 5 | 1/32 |
| ≥ 6 | 1/32 |

Vì tổng xác suất trên các mức k≥1 bằng 1, đây là một **phân phối hình học** hợp lệ.

### 6.2. Số liên kết forward kỳ vọng của một node

Một node có chiều cao `H` thì có đúng H **ô forward**. Theo đẳng thức cộng xác suất đuôi:

\[
\begin{aligned}
\mathbb E[H]
&=\sum_{k=1}^{\infty}\Pr(H\ge k)\\
&=\sum_{k=1}^{\infty}p^{k-1}\\
&=\frac{1}{1-p}.
\end{aligned}
\]

Với `p=1/2`, trung bình mỗi node có **2 ô forward**. Với n node, tổng số ô forward kỳ vọng **`2n`** (không tính sentinel, overhead object hoặc allocator).

Điều này giải thích vì sao nhiều tầng **không nhất thiết tạo O(n log n) ô con trỏ**: đa số node rất thấp, số node ở tầng cao giảm theo cấp số nhân.

### 6.3. Khi có trần `MAX_LEVEL=L`

Với `L≥1`, các lần bốc dừng khi `H=L`. Do đó:

\[
\mathbb E[H]
=\sum_{k=1}^{L}p^{k-1}
=\frac{1-p^L}{1-p}
\le \frac{1}{1-p}.
\]

Số ô forward mỗi node không vượt L và không còn khả năng nhận chiều cao vô hạn. **Đổi lại**, nếu L cố định trong khi n tăng không giới hạn, không thể khẳng định thời gian tìm kiếm vẫn O(log n) cho mọi n. Ta sẽ phân tích chi tiết ở Mục 12.

### 6.4. Số nút kỳ vọng trên từng tầng

Một node xuất hiện ở tầng chỉ số i nếu `H≥i+1`, xác suất `p^i`. Với n node có chiều cao độc lập:

\[
\mathbb E[N_i]=n p^i.
\]

Với `p=1/2` và n=1024:

| Tầng i | Số node kỳ vọng |
| --- | ---: |
| L0 | 1024 |
| L1 | 512 |
| L2 | 256 |
| L3 | 128 |
| L4 | 64 |
| L5 | 32 |
| L6 | 16 |
| L7 | 8 |
| L8 | 4 |
| L9 | 2 |
| L10 | 1 |

Đây là **kỳ vọng**, không phải yêu cầu cứng rằng tầng i **phải** chứa đúng `n/2^i` node. Một phân phối ngẫu nhiên hợp lệ có thể có tầng cao trống, hai node liền kề cùng chiều cao lớn hoặc một run dài node chỉ ở tầng 0.

## 7. Độ cao cực đại và chi phí tìm kiếm kỳ vọng

Gọi `M=\max(H_1,\ldots,H_n)` là chiều cao cao nhất trong n node. Với các độ cao độc lập và không trần:

\[
\Pr(M\ge k)\le n p^{k-1}.
\]

Bất đẳng thức này đến từ **union bound**: xác suất ít nhất một trong n node có chiều cao ≥k không vượt tổng xác suất của từng node.

Đặt k khoảng `1+\log_{1/p}n`, ta thấy số tầng sử dụng điển hình tăng theo **logarit của n**, không tuyến tính.

### 7.1. Vì sao đường tìm không phải đi qua n nút?

Hình dung tìm kiếm **theo chiều ngược** từ vị trí đích trên tầng 0: trên một tầng, ta đi ngược qua các node thấp cho đến khi gặp một node có mặt ở tầng cao hơn. Mỗi node có xác suất được nâng thêm một tầng khoảng p (theo mô hình độc lập).

- Số bước ngang kỳ vọng trên mỗi mức liên quan đến `1/p`.
- Số tầng hữu ích có cỡ `\log_{1/p}n`.
- Cộng hai nguồn chi phí thu được dạng:

\[
\mathbb E[T_{\mathrm{search}}]
=O\!\left(\frac{1}{p}\log_{1/p}n\right)
=O(\log n)
\]

khi p là một hằng số cố định trong khoảng (0,1), n≥2 và độ cao được hỗ trợ đủ để phản ánh phân phối. Hệ số hằng phụ thuộc p và chi tiết thuật toán.

Đây là **lập luận trực giác theo đường ngược** cho kết quả chuẩn; một chứng minh chặt cần xử lý xác suất đường tìm và tầng cao nhất. Không nên dùng trực giác ấy như bằng chứng cho một cài đặt PRNG tùy ý hay giới hạn tầng quá thấp.

### 7.2. Thời gian của từng thao tác

Khi đã có tiền nhiệm ở các tầng:

- `contains`: đi tìm một lần.
- `insert`: tìm tiền nhiệm, bốc H, nối tối đa H liên kết.
- `discard`: tìm tiền nhiệm, gỡ liên kết ở các tầng của node bị xóa.
- `lower_bound`: tìm vị trí rồi trả ứng viên.

Theo mô hình hình học độc lập và cấu hình chiều cao thích hợp, tìm/chèn/xóa đều có **O(log n) thời gian kỳ vọng** và **O(n) tổng dung lượng liên kết kỳ vọng**. Chi phí duyệt toàn bộ tầng 0 luôn **O(n)**, không cần lập luận xác suất.

### 7.3. Tình huống xấu không bị loại trừ

Giả sử **mọi node chỉ có H=1**, khi đó skip list thực chất là danh sách liên kết đơn. Tìm phần tử cuối cần Θ(n) bước. Tình huống ấy hiếm nếu n lớn, nhưng nó **có thể xảy ra**.

Nếu số tầng là biến ngẫu nhiên không giới hạn, còn có những lần bốc tạo chiều cao rất lớn; lúc ấy chi phí đi xuống các tầng có thể lớn theo H. Vì vậy với implementation cụ thể, worst-case nên nói theo **n và số tầng thực tế H**, thay vì khẳng định “luôn O(n)” trong mọi biến thể không giới hạn tầng.

**Không được nhầm expected với worst-case.** Một deadline thời gian thực cứng có thể yêu cầu cây AVL/đỏ–đen hoặc một cơ chế fallback với bảo đảm được chứng minh.


## 8. Chèn khóa: bốc chiều cao rồi nối ở từng tầng

Quy trình chèn một khóa `k` vào skip list set:

1. Chạy `FIND_PREDECESSORS(k)`, lấy `update[i]` cho mọi tầng đang dùng.
2. Kiểm tra `update[0].forward[0]`: nếu key đã có, trả **không chèn**, giữ nguyên set.
3. Chỉ khi khóa mới, bốc `new_height` theo phân phối hình học.
4. Nếu `new_height > current_level`, tạo thêm tầng từ mức cũ tới `new_height-1`; mọi tiền nhiệm ở các tầng mới là `HEAD`.
5. Tạo node mới với đúng `new_height` ô forward ban đầu rỗng.
6. Với mỗi tầng `i < new_height`, nối `fresh` vào giữa `update[i]` và successor cũ.
7. Tăng `size` đúng 1 và cập nhật metadata thay đổi cấu trúc nếu có.

### 8.1. Pseudocode chèn

```text
INSERT(k):
    update = FIND_PREDECESSORS(k)
    successor = update[0].forward[0]

    if successor != null and successor.key == k:
        return false

    H = RANDOM_HEIGHT()

    if H > current_level:
        for i in [current_level, H):
            update[i] = HEAD
        current_level = H

    new_node = Node(k, forward[0..H-1] = null)

    for i in [0, H):
        new_node.forward[i] = update[i].forward[i]
        update[i].forward[i] = new_node

    size += 1
    return true
```

**Hai quy tắc quan trọng:**

- **Khóa trùng không nhất thiết phải bốc số ngẫu nhiên.** Code bài chọn tìm trùng trước để chuỗi RNG không bị thay khi `insert` bị từ chối.
- **Không phân bổ nhiều node cùng key cho các tầng.** Mọi tầng trỏ tới **một object `new_node`** với mảng forward của nó.

### 8.2. Khi node mới cao hơn tầng cao nhất

Giả sử list đang có L0..L2 (`current_level=3`), còn node `k` bốc `H=5`. Hai tầng L3 và L4 chưa có node dữ liệu, nên:

```text
update[3] = HEAD
update[4] = HEAD

L4: HEAD -> k -> NULL
L3: HEAD -> k -> NULL
L2/L1/L0: chèn k đúng vị trí sorted của các tầng ấy.
```

**Không được dùng `update[3]` hay `update[4]` chưa khởi tạo.** Đây là một lỗi rất phổ biến khi mảng `update` chỉ được ghi trong vòng tìm trên các tầng cũ.

### 8.3. Trạng thái khi cấp phát thất bại

Trong C/C++, việc cấp phát node, mảng forward hoặc mảng `update` có thể thất bại. Một thiết kế an toàn nên:

- Tìm vị trí và chuẩn bị cấp phát đầy đủ **trước** khi thay liên kết công khai.
- Nếu cấp phát không thành công, giữ nguyên skip list nguồn; trả trạng thái lỗi tách biệt với “khóa đã tồn tại”.
- Sau khi có node và các buffer cần thiết, mới thực hiện những phép gán liên kết ngắn có hợp đồng rõ.
- Nếu cập nhật thực hiện qua nhiều tầng và có concurrent readers, cần cơ chế đồng bộ/commit; các phép gán đúng thứ tự trong một chương trình tuần tự **không tự tạo atomic insertion đa luồng**.

Trong Python, lỗi cấp phát có thể xuất hiện khi tạo danh sách/đối tượng mới. Code thực hành sẽ cấp phát node **trước khi nối nó vào các tầng**, để tránh công bố node mới nửa chừng chỉ vì thiếu bộ nhớ.

## 9. Xóa khóa: tìm tiền nhiệm, bỏ liên kết rồi hạ mức

Xóa `k` thực chất là thao tác **gỡ cùng một node khỏi tất cả các tầng mà nó tham gia**, không phải xóa độc lập H bản sao.

1. Chạy `FIND_PREDECESSORS(k)`.
2. Kiểm tra `target = update[0].forward[0]`.
3. Nếu không có target hoặc `target.key != k`, trả **False** và không thay cấu trúc.
4. Với `i=0..target_height-1`, nối:

```text
update[i].forward[i] = target.forward[i]
```

5. Giảm `size` đúng 1.
6. Khi tầng cao nhất không còn nút dữ liệu, giảm `current_level` nhưng giữ ít nhất tầng 0.

### 9.1. Minh họa xóa node có nhiều tầng

Giả sử 40 có H=4:

```text
Trước xóa 40:

L3: HEAD -------------------> 40 -------------------> NULL
L2: HEAD -> 10 -------------> 40 -------------> 80 -> NULL
L1: HEAD -> 10 -> 30 -------> 40 -> 60 -------> 80 -> NULL
L0: HEAD -> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 70 -> 80 -> NULL
```

Khi xóa, ta sửa **bốn** chuỗi liên kết. Nếu sau đó không còn node nào ở L3, hạ `current_level` từ 4 xuống 3:

```text
Sau xóa 40:

L2: HEAD -> 10 ------------------------------------> 80 -> NULL
L1: HEAD -> 10 -> 30 -> 60 ------------------------> 80 -> NULL
L0: HEAD -> 10 -> 20 -> 30 -> 50 -> 60 -> 70 -> 80 -> NULL
```

Tầng 3 không còn được coi là tầng đang dùng. Tùy cách cài đặt, có thể giữ ô `HEAD.forward[3]` rỗng để tái dùng về sau hoặc thu nhỏ mảng cấp phát.

### 9.2. Vì sao phải cập nhật tất cả các tầng?

Nếu chỉ xóa 40 khỏi L0:

- 40 vẫn nằm trong các đường nhảy tầng cao.
- `contains(40)` có thể có hành vi không nhất quán vì đường tìm đi qua các liên kết cũ.
- Trong C/C++, nếu đã `free(node40)`, các tầng cao có thể chứa **con trỏ treo**; truy cập sau đó gây use-after-free.
- `size` có thể nói đã xóa nhưng cấu trúc thật chưa được tách hoàn toàn.

Thứ tự an toàn trong chương trình tuần tự là **gỡ toàn bộ liên kết → giải phóng node**, không phải ngược lại.

### 9.3. Ngữ nghĩa khóa trùng và xóa không tồn tại

Bài dùng **set**: một khóa chỉ có một node; `insert(k)` lần hai trả False, `discard(k)` với khóa vắng cũng trả False. Các thao tác không thành công **không làm đổi số lượng khóa**.

Với map, multiset hoặc cấu trúc đếm tần suất, cần thiết kế lại payload và điều kiện chèn/xóa; không tự biến một skip list set thành multiset chỉ bằng cách cho nhiều node cùng khóa mà giữ nguyên `<`/`==` trong mọi vòng tìm kiếm.

## 10. Python: cài đặt skip list set hoàn chỉnh

Đoạn này chạy độc lập trên **Python 3.10+**. Để thuật toán không phụ thuộc đệ quy, mọi phép tìm–chèn–xóa đều dùng vòng lặp. Kiểu nút dùng `@dataclass(eq=False)` để kiểm thử có thể phân biệt node bằng **danh tính đối tượng** ngay cả khi hai node mang cùng giá trị (vốn phải bị ngăn trong chính sách set).

Ta cấu hình `MAX_LEVEL` cố định (mặc định 32) để có **giới hạn số ô forward trên mỗi node**, cho phép seed để tái lập test, và dùng `_version` nhằm minh họa **fail-fast iterator** khi cấu trúc bị sửa bởi chính API.

### 10.1. Mã Python đầy đủ

```python
from __future__ import annotations

import random
from dataclasses import dataclass
from collections.abc import Iterator


@dataclass(eq=False)
class SkipNode:
    key: int | None
    forward: list[SkipNode | None]


class SkipList:
    """Skip list set: key nguyên duy nhất, thứ tự tăng dần."""

    def __init__(
        self,
        *,
        p: float = 0.5,
        max_level: int = 32,
        seed: int | None = None,
    ) -> None:
        if not (0.0 < p < 1.0):
            raise ValueError("p phải thuộc (0, 1)")
        if max_level < 1:
            raise ValueError("max_level phải >= 1")

        self._p = p
        self._max_level = max_level
        self._level = 1
        self._size = 0
        self._version = 0
        self._rng = random.Random(seed)

        # Head có slot cho mọi tầng, dù chỉ L0 đang dùng.
        self._head = SkipNode(None, [None] * max_level)

    def __len__(self) -> int:
        return self._size

    @property
    def level_count(self) -> int:
        """Số tầng đang sử dụng, luôn ít nhất 1."""
        return self._level

    def _random_height(self) -> int:
        height = 1
        while height < self._max_level and self._rng.random() < self._p:
            height += 1
        return height

    def _find_predecessors(self, key: int) -> list[SkipNode]:
        """update[i] đứng ngay trước key ở tầng i đang dùng."""
        update = [self._head] * self._max_level
        current = self._head

        for level in range(self._level - 1, -1, -1):
            while True:
                nxt = current.forward[level]
                if nxt is None or nxt.key >= key:
                    break
                current = nxt
            update[level] = current

        return update

    def contains(self, key: int) -> bool:
        update = self._find_predecessors(key)
        candidate = update[0].forward[0]
        return candidate is not None and candidate.key == key

    def lower_bound(self, key: int) -> int | None:
        """Khóa nhỏ nhất >= key, hoặc None nếu không tồn tại."""
        update = self._find_predecessors(key)
        candidate = update[0].forward[0]
        return None if candidate is None else candidate.key

    def predecessor(self, key: int) -> int | None:
        """Khóa lớn nhất < key, hoặc None nếu không có."""
        update = self._find_predecessors(key)
        node = update[0]
        return None if node is self._head else node.key

    def insert(self, key: int) -> bool:
        update = self._find_predecessors(key)
        candidate = update[0].forward[0]

        if candidate is not None and candidate.key == key:
            return False

        height = self._random_height()
        fresh = SkipNode(key, [None] * height)

        # Mọi tầng mới hiện đều chỉ có HEAD.
        if height > self._level:
            for level in range(self._level, height):
                update[level] = self._head
            self._level = height

        for level in range(height):
            fresh.forward[level] = update[level].forward[level]
            update[level].forward[level] = fresh

        self._size += 1
        self._version += 1
        return True

    def discard(self, key: int) -> bool:
        update = self._find_predecessors(key)
        target = update[0].forward[0]

        if target is None or target.key != key:
            return False

        for level in range(len(target.forward)):
            assert update[level].forward[level] is target
            update[level].forward[level] = target.forward[level]

        # Thu hẹp số tầng dùng nếu các tầng trên cùng trống.
        while (
            self._level > 1
            and self._head.forward[self._level - 1] is None
        ):
            self._level -= 1

        self._size -= 1
        self._version += 1
        return True

    def range_keys(
        self,
        low: int | None = None,
        high: int | None = None,
    ) -> Iterator[int]:
        """Sinh sorted keys thuộc [low, high).

        Mỗi None nghĩa là không có biên ở phía tương ứng.
        Nếu dữ liệu thay đổi qua insert/discard khi đang duyệt,
        lần lấy tiếp theo ném RuntimeError (fail-fast).
        """
        if low is not None and high is not None and low >= high:
            return iter(())

        if low is None:
            start = self._head.forward[0]
        else:
            update = self._find_predecessors(low)
            start = update[0].forward[0]

        expected_version = self._version

        def generate() -> Iterator[int]:
            node = start

            while node is not None:
                if self._version != expected_version:
                    raise RuntimeError("Skip list đã thay đổi khi đang duyệt")

                if high is not None and node.key >= high:
                    return

                yield node.key
                if self._version != expected_version:
                    raise RuntimeError("Skip list đã thay đổi khi đang duyệt")
                node = node.forward[0]

            if self._version != expected_version:
                raise RuntimeError("Skip list đã thay đổi khi đang duyệt")

        return generate()

    def keys(self) -> Iterator[int]:
        return self.range_keys()

    def assert_valid(self) -> None:
        """Validator O(n + số forward slots) cho trạng thái tĩnh.

        Chỉ dùng debug/test, không phải đồng bộ đa luồng.
        """
        assert 1 <= self._level <= self._max_level
        assert len(self._head.forward) == self._max_level
        assert all(
            self._head.forward[i] is None
            for i in range(self._level, self._max_level)
        )

        # Kiểm tra L0 và thu mọi node theo identity.
        bottom: set[SkipNode] = set()
        node = self._head.forward[0]
        last_key: int | None = None
        max_height = 1

        while node is not None:
            assert node not in bottom, "Chu trình tại tầng 0"
            bottom.add(node)
            assert node.key is not None
            assert 1 <= len(node.forward) <= self._max_level
            assert last_key is None or last_key < node.key

            max_height = max(max_height, len(node.forward))
            last_key = node.key
            node = node.forward[0]

        assert len(bottom) == self._size
        assert self._level == max_height

        # Đếm số node PHẢI có mặt ở từng tầng.
        wanted = [0] * self._level
        for node in bottom:
            for level in range(len(node.forward)):
                wanted[level] += 1

        for level in range(self._level):
            at_level: set[SkipNode] = set()
            node = self._head.forward[level]
            previous_key: int | None = None

            while node is not None:
                assert node not in at_level, "Chu trình tầng cao"
                assert node in bottom
                assert len(node.forward) > level
                assert previous_key is None or previous_key < node.key

                at_level.add(node)
                previous_key = node.key
                node = node.forward[level]

            assert len(at_level) == wanted[level], (
                "Tầng thiếu node có độ cao tương ứng"
            )


if __name__ == "__main__":
    sl = SkipList(seed=2026, p=0.5, max_level=32)

    # Đầu vào tăng dần, không cần xáo trộn trước.
    for key in range(1, 1001):
        assert sl.insert(key)

    sl.assert_valid()
    assert len(sl) == 1000
    assert list(sl.keys()) == list(range(1, 1001))

    assert sl.contains(500)
    assert not sl.contains(1001)
    assert sl.lower_bound(501) == 501
    assert sl.predecessor(501) == 500
    assert list(sl.range_keys(10, 15)) == [10, 11, 12, 13, 14]

    assert not sl.insert(500)   # Set: không có khóa trùng.
    assert sl.discard(500)
    assert not sl.contains(500)
    assert not sl.discard(500)

    sl.assert_valid()
    assert len(sl) == 999
    assert sl.lower_bound(500) == 501
    print("size =", len(sl), "levels =", sl.level_count)
```

### 10.2. Vì sao code tạo node trước khi sửa các tầng?

Mã Python gọi `fresh = SkipNode(key, [None]*height)` **trước khi** cập nhật `self._level` và `forward`. Nếu tạo object hoặc mảng forward thất bại, skip list chưa bị nối thêm node dở.

Đây là **nguyên tắc triển khai an toàn ở mức thuật toán tuần tự**, không phải bảo đảm tuyệt đối cho mọi loại lỗi Python hoặc một cơ chế transaction. Một hiện thực production còn phải quy định lỗi từ so sánh key, lỗi cấp phát các mảng tạm, khả năng đồng thời, và nếu có payload riêng thì ai sở hữu payload ấy.

### 10.3. Quy tắc `assert_valid` kiểm tra gì?

Để tránh việc một liên kết tầng cao bị rơi khỏi cấu trúc mà tầng 0 vẫn đúng, validator làm nhiều hơn kiểm tra `sorted`:

1. L0 chứa các node **khác nhau theo identity**, không tạo chu trình.
2. Khóa trên L0 tăng chặt, và `size` bằng số node L0.
3. `_level` bằng chiều cao lớn nhất của các node còn sống (hoặc 1 khi rỗng).
4. Mọi node ở tầng i thuộc L0 và thật sự có `len(forward)>i`.
5. Trong tầng i, không thăm lặp và khóa tăng chặt.
6. Số node được tìm thấy ở tầng i bằng số node L0 **có độ cao đủ lớn** để tham gia tầng i.
7. Những ô `head.forward` trên mức đang dùng phải rỗng.

Như vậy, nếu một node có `H=4` nhưng thiếu khỏi tầng 2, số node thực tế ở L2 sẽ không khớp `wanted[2]`. Việc dùng `set` ở đây dành cho **kiểm thử/chẩn đoán**; một phép tìm thực tế không xây `set` toàn bộ.

### 10.4. Độ phức tạp của cài đặt

Gọi `n` là số khóa, `H` số tầng đang dùng, `L` là `max_level`, và `k` số phần tử của một range query:

| Phép toán | Kỳ vọng với cấu hình tầng đủ lớn và phân phối đúng | Giới hạn theo trạng thái thực tế |
| --- | --- | --- |
| `contains`, `lower_bound`, `predecessor` | O(log n + L) với mảng update dài L; nếu L=O(log n) thì O(log n) | O(n+H+L) |
| `insert` | O(log n + L) | O(n+H+L) |
| `discard` | O(log n + L) | O(n+H+L) |
| `range_keys(low,high)` xuất k khóa | O(log n+L+k) | O(n+H+L+k) |
| `keys()` xuất toàn bộ | O(n) | O(n) |
| `assert_valid()` | O(n+S+L) với S là tổng ô forward, dùng hash-set theo identity | O(n+S+L) kỳ vọng cho hash/set |
| Bộ nhớ cho node | O(n) ô forward kỳ vọng khi p cố định | O(nL) là chặn cứng, ngoài head O(L) |
| Bộ nhớ tạm `update` | O(L) | O(L) |

**Lưu ý về chi phí Python cụ thể:** `_find_predecessors` cấp hẳn list độ dài L ở **mọi lần tìm**, kể cả `contains`. Vì vậy nếu một chương trình chọn L tăng rất nhanh so với n, không được bỏ qua **O(L)** và chỉ nói O(log n). Với **L=32 cố định** và n trong quy mô cấu hình này được thiết kế, O(L) là hằng số triển khai, còn độ dài đường skip list mới là phần biến thiên chính.

Một phiên bản tối ưu có thể tách:
- **tìm kiếm chỉ đọc:** không cấp `update[]`, giữ một cursor và đi tầng cao xuống thấp;
- **chèn/xóa:** cấp `update` với chiều dài H đang dùng, cộng phần mở rộng khi node mới cao hơn.

Với cấu trúc không bị giới hạn tầng quá thấp so với n, kỳ vọng tổng bước tìm vẫn đạt O(log n); với L cố định và n tiến tới vô hạn, chỉ còn bảo đảm tiệm cận tệ hơn. Đừng đánh đồng **L=32 đủ lớn cho workload đã định** với **chứng minh vô hạn trên mọi n**.

### 10.5. Một ghi chú quan trọng về tính ổn định khi duyệt

`range_keys` ghi `expected_version` **khi được gọi**, rồi trả một generator nội bộ. Do đó, nếu bên gọi tạo iterator, thay đổi skip list rồi mới gọi `next`, lần lấy đầu tiên cũng phát hiện thay đổi. Khi một generator `yield` một khóa, trạng thái node và các con trỏ còn giữ giữa hai lần lấy; mọi thay đổi cấu trúc qua API của lớp sẽ tăng `_version` và khiến lần lấy sau báo lỗi.

Đây chỉ là cơ chế **fail-fast best effort trong chương trình tuần tự**: nó **không** làm iterator thread-safe, không đồng bộ con trỏ và không đảm bảo an toàn nếu bên ngoài truy cập/sửa trực tiếp `_head` hoặc các `SkipNode` nội bộ.

**Khi phần tử cuối vừa được yield rồi có cập nhật**, một lần `next` tiếp theo sẽ so sánh version trước khi báo hết. Khi khoảng truy vấn rỗng ngay từ đầu (`low>=high`), hàm trả iterator rỗng không ghi nhận phiên bản; đó là lựa chọn ngữ nghĩa đã được xác định, không ảnh hưởng các truy vấn có phần tử.


## 11. Theo dõi một chuỗi chèn và xóa bằng tay

Để hiểu skip list, hãy mô phỏng **các mức đã được bốc sẵn** thay vì để kết quả phụ thuộc vào seed.

Giả sử ban đầu chỉ có `HEAD`. Các thao tác:

| Lần | Thao tác | Chiều cao được cấp (nếu chèn mới) |
| --- | --- | ---: |
| 1 | insert(30) | 1 |
| 2 | insert(10) | 3 |
| 3 | insert(50) | 2 |
| 4 | insert(40) | 4 |
| 5 | insert(20) | 1 |
| 6 | insert(40) | Không bốc, khóa đã có |
| 7 | discard(10) | Không bốc |
| 8 | discard(40) | Không bốc |

### 11.1. Sau năm lần chèn thành công

```text
L3: HEAD ---------------------> 40 -> NULL
L2: HEAD -> 10 --------------> 40 -> NULL
L1: HEAD -> 10 -------------> 40 -> 50 -> NULL
L0: HEAD -> 10 -> 20 -> 30 -> 40 -> 50 -> NULL

size = 5; current_level = 4
```

Phân tích:

- Khóa 10 có ba ô `forward[0..2]`.
- Khóa 40 có bốn ô `forward[0..3]` và là nút duy nhất ở L3.
- Khóa 20 và 30 chỉ có ở tầng 0.
- Khóa 50 có ở L0 và L1.
- Dù trình tự yêu cầu không tăng đều, L0 **luôn sorted**.

**Điểm dễ nhầm:** tại L1, node 10 nhảy thẳng đến 40, bỏ qua 20 và 30. Nhưng 20, 30 vẫn **tồn tại ở L0** và vẫn được truy vấn tìm thấy.

### 11.2. Chèn trùng `40`

Dùng `update[0]` để nhìn ứng viên có key 40, hàm nhận ra khóa đã tồn tại và trả False. `size` vẫn 5, số tầng vẫn 4, không cấp node 40 thứ hai.

Nếu bốc level trước khi kiểm tra duplicate, cấu trúc vẫn có thể đúng về nội dung nhưng **trạng thái RNG** đã bị tiêu thụ một lần; để test tái lập và dễ suy luận, bài chọn kiểm tra trùng trước.

### 11.3. Xóa `10`

Node 10 có H=3 nên bỏ nó tại L0, L1, L2:

```text
L3: HEAD ---------------------> 40 -> NULL
L2: HEAD ---------------------> 40 -> NULL
L1: HEAD ---------------------> 40 -> 50 -> NULL
L0: HEAD -> 20 -> 30 --------> 40 -> 50 -> NULL

size = 4; current_level = 4
```

Không hạ `current_level` vì node 40 vẫn ở L3.

### 11.4. Xóa `40`

Sau khi bỏ 40 khỏi L0..L3, L3 và L2 trống. Node 50 cao 2 nên tầng cao nhất còn dữ liệu là L1:

```text
L1: HEAD -------------------> 50 -> NULL
L0: HEAD -> 20 -> 30 -------> 50 -> NULL

size = 3; current_level = 2
```

Xóa chính node cao nhất có thể làm biến `current_level` giảm **nhiều tầng liên tiếp**. Không được chỉ giảm đúng một lần hoặc giữ một mức đang dùng mà tầng cao nhất luôn rỗng, nếu invariant đòi tầng cao nhất có nút.

### 11.5. Khôi phục trạng thái rỗng

Khi xóa hết khóa 20, 30, 50, skip list trở thành:

```text
L0: HEAD -> NULL

size = 0; current_level = 1
```

**Head vẫn tồn tại** như sentinel; không được xóa head mỗi lần xóa phần tử cuối. Một lần chèn sau có thể tái sử dụng head và các slot forward đã cấp.

## 12. Chọn `p` và `MAX_LEVEL` theo quy mô dữ liệu

### 12.1. Ý nghĩa của xác suất `p`

`p` là xác suất một node được **nâng thêm** từ mức hiện tại lên mức kế tiếp. Thay đổi p sẽ đổi số liên kết và hình dạng đường tìm:

| p | Số ô forward kỳ vọng/node khi không trần | Tác động thường gặp |
| --- | ---: | --- |
| 1/4 | 4/3 | Ít link hơn, mỗi tầng thưa hơn; tìm ngang có thể dài hơn |
| 1/2 | 2 | Điểm cân bằng phổ biến, dễ tính xác suất |
| 3/4 | 4 | Nhiều tầng và liên kết hơn; tốn bộ nhớ hơn |

Với p rất nhỏ, số tầng hữu ích ít và khoảng cách ngang trên tầng cao có thể dài; với p rất gần 1, nhiều node có chiều cao cao, làm tăng số liên kết và cả chi phí đi xuống tầng.

**Không có một p tối ưu tuyệt đối** cho mọi kiểu khóa, kích thước node, allocator, cache hoặc tần suất đọc/ghi. `p=1/2` là lựa chọn học thuật và triển khai phổ biến, không phải quy luật phải tuân theo.

### 12.2. Ý nghĩa của `MAX_LEVEL`

Giới hạn `MAX_LEVEL=L`:

- Bảo đảm không node nào có quá L ô forward.
- Giới hạn số mức phải đi xuống tối đa L.
- Có thể cho head một mảng L slot để cấp phát không đổi về sau.
- Giới hạn số lần bốc cấp độ cho một node.
- Nhưng nếu L quá nhỏ so với n, tầng cao nhất vẫn có thể chứa **rất nhiều node**, không còn bỏ qua được phần lớn dữ liệu.

Ví dụ: p=1/2, L=16, n khoảng `2^{24}`. Tầng cao nhất L15 có số node kỳ vọng:

\[
\mathbb E[N_{15}] = 2^{24}(1/2)^{15} = 2^9 = 512.
\]

Nếu tìm khóa gần cuối, chỉ riêng việc đi ngang trên tầng cao nhất đã có thể phải đi qua rất nhiều node. Giới hạn 16 mức **không** tự đủ cho mọi n.

### 12.3. Vì sao cố định L rồi cho n→∞ không còn O(log n)?

Xét cấu hình p cố định, L cố định. Xác suất một node có mặt ở **tầng cao nhất** là `p^{L-1}`, một hằng số dương. Khi n tăng, số node ở tầng này tăng tỷ lệ với n.

Không có tầng cao hơn để bỏ qua chuỗi ấy. Vì vậy, trong miền n tăng vô hạn, thuật toán tìm những khóa xa có thể tốn **Θ(n)** bước ngang trên tầng cao nhất theo kỳ vọng đối với cấu hình L cố định.

Trong một cấu hình thực tế, người thiết kế thường chọn L đủ lớn so với **n lớn nhất được hỗ trợ**, hoặc dùng thiết kế có thể nâng giới hạn khi cấu trúc phát triển. Khi nói “skip list expected O(log n)”, phải ngầm có **chính sách mức phù hợp với quy mô** và mô hình xác suất đúng.

### 12.4. Cấp head cố định hay tăng động?

Có hai chính sách:

- **Head cố định L slot:** dễ triển khai, O(L) bộ nhớ sentinel ngay cả khi rỗng; node có thể bị chặn mức tối đa.
- **Head mở rộng khi cần:** cấp dần số slot theo mức đã xuất hiện; hạn chế bộ nhớ sentinel khi nhỏ nhưng phải xử lý `realloc`/mở rộng và lỗi cấp phát.

Một implementation sản xuất có thể giữ một **mức trần cứng** để khống chế tài nguyên nhưng tăng nó theo dự báo quy mô. Dù dùng cách nào, cần ghi rõ phép đo worst-case và phạm vi được thiết kế.

### 12.5. Có phải càng nhiều tầng càng nhanh?

Không nhất thiết. Tăng L có thể giảm một số bước ngang nhưng thêm:

- Các bước **đi xuống tầng**.
- Bộ nhớ forward/pointer metadata.
- Tải cache khi tìm predecessor.
- Thời gian tạo/xóa liên kết qua nhiều tầng.
- Chi phí bộ nhớ cho `update[]`.

Benchmark cần đo trên **workload thật** (tỷ lệ find/insert/delete, kiểu range query, kích thước tập khóa), thay vì chỉ so `L` hoặc `p` bằng số.

## 13. Skip list nâng cao: `rank` và `select` bằng span/width

Skip list cơ bản rất tốt cho **tìm theo khóa** nhưng không trực tiếp cho **tìm theo thứ hạng**:

- `rank(k)`: có bao nhiêu khóa nhỏ hơn k?
- `select(r)`: khóa nhỏ thứ r theo thứ tự tăng (quy ước r bắt đầu từ 1).

Nếu chỉ có `forward[]`, ta có thể đi tầng đáy và đếm, mất O(n) trong trường hợp xấu nhất. Để hỗ trợ các truy vấn theo thứ hạng ở mức kỳ vọng O(log n), một phiên bản **indexable skip list** lưu thêm **span/width** cho từng con trỏ forward.

### 13.1. Span là khoảng cách tính bằng số phần tử tầng đáy

Giả sử tại node `u`, `u.forward[i]=v`. Định nghĩa:

> `span[i]` là số **nút dữ liệu tầng 0** nằm sau u, tới **v và tính cả v**.

Sentinel HEAD có vị trí thứ tự 0; node nhỏ nhất có thứ tự 1.

Ví dụ L0 có:

```text
HEAD -> 10 -> 20 -> 30 -> 40 -> 50

Với cạnh ở một tầng cao:
HEAD ---------------------> 40

span của cạnh HEAD -> 40 là 4:
  các nút tầng đáy 10,20,30,40.
```

Chỉ với các cạnh có successor thật, định nghĩa này là đủ để suy luận rank/select. Các giá trị span của một con trỏ rỗng phải theo **một quy ước sentinel/null thống nhất** riêng trong implementation.

### 13.2. Đếm rank khi đi ngang

Mỗi lần đi qua một cạnh tầng i, cộng `span[i]` vào một biến đếm.

```text
RANK_LESS_THAN(k):
    traversed = 0
    current = HEAD

    for level from highest down to 0:
        while current.forward[level] exists
              and current.forward[level].key < k:
            traversed += current.span[level]
            current = current.forward[level]

    return traversed
```

Với dãy `[10,20,30,40,50]`, `rank_less_than(40)=3` vì có ba khóa nhỏ hơn 40.

### 13.3. Tìm phần tử thứ r

Đặt `r` là thứ tự **1-based**. Ta giữ `traversed` là số phần tử đã vượt qua:

```text
SELECT(r):
    if r < 1 or r > size:
        return NOT_FOUND

    traversed = 0
    current = HEAD

    for level from highest down to 0:
        while current.forward[level] exists
              and traversed + current.span[level] <= r:
            traversed += current.span[level]
            current = current.forward[level]

    return current if traversed == r else NOT_FOUND
```

Nếu các span đúng và thuật toán luôn ưu tiên tầng cao, số bước tìm rank/select có **O(log n) kỳ vọng** theo cấu trúc random chuẩn.

### 13.4. Cập nhật span khó hơn chỉ cập nhật forward

Một phép chèn một node có thể đổi span **ngay cả tại tầng mà node mới không xuất hiện**, vì khoảng cách đếm theo tầng đáy của các cạnh nhảy qua vị trí chèn cũng tăng.

Một phép xóa có thể giảm span của các cạnh nhảy qua vị trí xóa. Vì vậy, nếu bổ sung `span` vào mã `SkipList` Mục 10, **không được chỉ sửa `forward` và mong span tự đúng**.

Cần giữ đồng thời:

1. `update[i]`: tiền nhiệm tại mỗi tầng.
2. `traversed_rank[i]`: số nút tầng đáy đã đi qua đến tiền nhiệm ấy.
3. Công thức chia span của cạnh cũ thành hai cạnh mới khi chèn.
4. Công thức cộng/gỡ span khi xóa và cập nhật cả các tầng không chứa node.

Đây là bài toán mở rộng phù hợp sau khi hiểu bản skip list cơ bản; không nên thêm một đoạn span tùy ý nếu chưa có kiểm thử invariant theo thứ hạng.

## 14. C: một node được liên kết nhiều tầng nhưng chỉ giải phóng một lần

Trong C, có thể biểu diễn node skip list bằng **flexible array member** để lưu đúng số slot forward cần thiết:

```c
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct SkipNode {
    int key;
    size_t height;
    struct SkipNode *forward[];
} SkipNode;

/* Cấp đúng height slot, khởi tạo NULL, kiểm tra tràn byte. */
static SkipNode *node_create(int key, size_t height) {
    if (height == 0 ||
        height > (SIZE_MAX - sizeof(SkipNode)) / sizeof(SkipNode *)) {
        return NULL;
    }

    size_t bytes = sizeof(SkipNode) + height * sizeof(SkipNode *);
    SkipNode *node = malloc(bytes);
    if (node == NULL) return NULL;

    node->key = key;
    node->height = height;

    for (size_t i = 0; i < height; ++i) {
        node->forward[i] = NULL;
    }

    return node;
}

/* Chỉ áp dụng khi L0 chứa đúng mọi node, không có chu trình.
   Hàm tiêu thụ cả head và các node, không dùng nữa sau khi gọi.
   Không có người đọc nào khác và không có ownership dùng chung. */
static void list_destroy(SkipNode *head) {
    if (head == NULL) return;

    SkipNode *node = head->forward[0];

    while (node != NULL) {
        SkipNode *next = node->forward[0];
        free(node);                   /* Mỗi object chỉ free 1 lần. */
        node = next;
    }

    free(head);
}

int main(void) {
    /* Ví dụ thủ công: H(10)=2, H(20)=1, H(30)=2. */
    SkipNode *head = node_create(0, 2);  /* key head không dùng. */
    SkipNode *a = node_create(10, 2);
    SkipNode *b = node_create(20, 1);
    SkipNode *c = node_create(30, 2);

    if (head == NULL || a == NULL || b == NULL || c == NULL) {
        free(head);
        free(a);
        free(b);
        free(c);
        return EXIT_FAILURE;
    }

    /* L0: HEAD -> 10 -> 20 -> 30 */
    head->forward[0] = a;
    a->forward[0] = b;
    b->forward[0] = c;

    /* L1: HEAD -> 10 -------> 30 */
    head->forward[1] = a;
    a->forward[1] = c;

    for (SkipNode *cur = head->forward[0];
         cur != NULL;
         cur = cur->forward[0]) {
        printf("%d ", cur->key);
    }
    puts("");     /* 10 20 30 */

    list_destroy(head);
    return EXIT_SUCCESS;
}
```

### 14.1. Tại sao destructor chỉ đi theo `forward[0]`?

Tầng 0 chứa **tất cả node dữ liệu đúng một lần**, nên nó đủ để hủy toàn bộ object. Nếu đi qua từng tầng và gọi `free`, node 10 hoặc 30 sẽ bị hủy nhiều lần vì xuất hiện ở nhiều tầng.

Trong vòng dọn, `next` được lấy **trước khi `free(node)`**; sau khi giải phóng, không đọc `node->forward` nữa. Bộ nhớ chứa các ô forward ở tầng cao thuộc **cùng lần `malloc` của node**, được giải phóng cùng node, không phải đối tượng cần `free` riêng.

### 14.2. Hợp đồng và giới hạn của ví dụ

- Đây là ví dụ về **bố trí bộ nhớ và destructor**, không phải toàn bộ implementation skip list bằng C.
- `head` sở hữu một mảng forward độ dài cố định 2; các node dữ liệu có độ cao theo ví dụ.
- Nếu một node bị gỡ khỏi tầng 0 nhưng vẫn còn trong tầng cao, destructor trên không thể biết node đó; **bất biến đã bị phá** và cần sửa nguyên nhân, không dựa vào destructor để vá.
- Nếu đầu vào là một đồ thị có chu trình hoặc dùng chung node giữa nhiều danh sách khác, không được dùng `list_destroy` của skip list set sở hữu riêng.
- Với payload cấp phát động như `char*` hoặc buffer, phải giải phóng đúng tài nguyên của node trước `free(node)`.
- Nếu chương trình có iterator/luồng khác đang dùng node, cần quản lý vòng đời và đồng bộ trước khi hủy.

### 14.3. Chi phí bộ nhớ thực tế

Node của skip list thường gồm `key`, metadata chiều cao, pointer forward và padding do căn chỉnh. Nếu mỗi pointer 8 byte (trên nhiều môi trường 64-bit), với p=1/2, **riêng forward slots** trung bình khoảng **16 byte mỗi node**, *không tính* key, height, padding hay overhead allocator. Kích thước pointer và padding phụ thuộc nền tảng thực tế; không nên viết con số 16 byte như một bảo đảm portable.

Dù expected tổng forward slots là O(n), các cấp phát nhỏ rời rạc vẫn có thể kém locality cache hơn mảng đã sắp xếp hoặc cấu trúc cây theo khối như B-tree.


## 15. Iterator, đồng thời và giải phóng bộ nhớ

Skip list thường được giới thiệu như cấu trúc đơn giản hơn cây cân bằng, nhưng **mức độ khó tăng nhiều** khi có người đọc/ghi đồng thời. Random levels không tự bảo đảm **thread safety**.

### 15.1. Trạng thái chưa đồng nhất trong quá trình chèn/xóa

Ở thao tác chèn node có H=3, một implementation tuần tự có thể nối tầng 0 trước rồi tới tầng 1, tầng 2. Giữa các phép gán ấy, nếu luồng khác đọc mà không đồng bộ, nó có thể thấy:

- Node mới đã xuất hiện ở L0 nhưng chưa xuất hiện ở tầng cao.
- Một predecessor đã đổi `forward[i]` nhưng successor ở tầng khác chưa cập nhật.
- Trong ngôn ngữ có memory model và data race, hành vi không chỉ là “đọc snapshot chưa hoàn chỉnh” mà còn có thể **không hợp lệ**.

Trong chương trình **tuần tự**, các trạng thái tạm này không bị quan sát ngoài thao tác và bất biến được khôi phục khi thao tác trả về. Trong chương trình **đồng thời**, cần thiết kế một hợp đồng quan sát riêng.

### 15.2. Khóa bảo vệ cấu trúc (coarse-grained lock)

Cách dễ giải thích nhất là có một **mutex chung** bảo vệ mọi thao tác đọc/ghi qua các liên kết:

```text
LOCK(skiplist)
    find / insert / discard / range operation
UNLOCK(skiplist)
```

Ưu điểm: tư duy gần với bản tuần tự, dễ bảo đảm mọi phép đọc nhìn thấy cấu trúc nhất quán khi tất cả bên truy cập tuân thủ cùng khóa.

Đánh đổi: một thao tác tìm dài hoặc duyệt một khoảng lớn có thể **giữ khóa lâu**, làm các thao tác khác phải đợi. Nếu trả một iterator để đi nhiều lần ngoài phạm vi khóa, vẫn cần chính sách snapshot, phiên bản hoặc kiểm soát vòng đời; **không được giữ con trỏ thô rồi âm thầm thả khóa mà không có bảo đảm**.

### 15.3. Skip list lock-free là thuật toán khác về an toàn

Có các thiết kế concurrent skip list dùng **CAS (compare-and-swap)** và các cơ chế chuyên biệt:

- Đánh dấu node bị xóa về mặt **logic** trước khi tháo vật lý khỏi các tầng.
- Chọn **điểm tuyến tính hóa** (*linearization point*) cho insert/remove/contains.
- Giúp hoàn tất những liên kết còn dang dở (*helping*) khi một thread dừng giữa thao tác.
- Dùng quy tắc **memory ordering** đúng theo nền tảng.
- Thu hồi node bằng **hazard pointers, epoch-based reclamation, reference counting** hoặc cơ chế tương đương, tránh dùng vùng nhớ đã free.
- Xử lý ABA và tương tác giữa đọc con trỏ, CAS và xóa node.

Bộ code Python và C trong bài **không** phải hiện thực lock-free, dù cả hai có thể được dùng làm cơ sở hiểu tầng liên kết. Không thể chỉ thay phép gán `forward[i] = node` bằng một CAS đơn lẻ để có skip list concurrent đúng.

### 15.4. Fail-fast iterator không phải snapshot

Lớp `SkipList` ở Mục 10 tăng `_version` khi chèn/xóa thành công và từ chối generator tiếp tục khi version khác. Cơ chế này:

- Phát hiện những thay đổi **qua API của chính lớp** trong chương trình tuần tự.
- Không đảm bảo phát hiện sửa tay trực tiếp vào `SkipNode.forward`.
- Không đảm bảo safe traversal nếu luồng khác đang ghi mà không đồng bộ.
- Không cố định nội dung dãy khóa tại thời điểm bắt đầu iterator.
- Không thay thế ownership của node trong ngôn ngữ có `free/delete`.

Nếu cần phân trang hoặc xử lý dãy kết quả xuyên nhiều request, có thể dùng **snapshot bất biến**, khóa phù hợp hoặc cursor theo khóa được tính lại, tùy yêu cầu về nhất quán.

### 15.5. Xóa một node vẫn đang được tham chiếu

Trong Python, generator có thể giữ tham chiếu mạnh tới một `SkipNode` đã bị gỡ khỏi danh sách. Object chưa chắc bị thu hồi ngay, nhưng **không còn thuộc tập khóa hiện hành**.

Trong C/C++, nếu một iterator giữ `Node*` tới node vừa `free`, đó có thể là dangling pointer và dùng tiếp gây use-after-free. Một thư viện cần công bố quy tắc **iterator invalidation**, không chỉ hàm `discard` trả thành công.

## 16. So sánh skip list với các cấu trúc thay thế

Không phải mọi set có thứ tự đều nên là skip list. Chọn cấu trúc nên dựa trên **truy vấn**, **cập nhật**, **kiểu bảo đảm**, **bộ nhớ** và **locality**.

| Cấu trúc | Tìm khóa | Chèn/xóa | Bộ nhớ/đặc điểm |
| --- | --- | --- | --- |
| Danh sách liên kết có thứ tự | O(n) | O(n) để tìm vị trí, sau đó O(1) để nối/gỡ | Ít metadata; dễ duyệt tuần tự |
| Mảng đã sắp xếp | O(log n) bằng binary search | O(n) khi phải dịch phần tử | Tính cục bộ dữ liệu tốt; hỗ trợ truy cập ngẫu nhiên |
| BST thường không tự cân bằng | O(h), worst O(n) | O(h), worst O(n) | Chiều cao chịu ảnh hưởng của thứ tự chèn |
| AVL / red-black tree chuẩn | O(log n) worst-case | O(log n) worst-case | Bất biến cân bằng tất định, mã phức tạp hơn |
| Treap với priority ngẫu nhiên | O(log n) kỳ vọng | O(log n) kỳ vọng | BST+heap; worst O(n) |
| Skip list với cấu hình random phù hợp | O(log n) kỳ vọng | O(log n) kỳ vọng | Liên kết nhiều tầng; worst có thể tuyến tính |
| Hash table thông thường | O(1) kỳ vọng cho tìm khóa chính xác theo giả định hash | O(1) kỳ vọng cho thao tác tập hợp cơ bản | Không tự duy trì thứ tự để hỗ trợ range |
| B-tree / B+ tree | O(log n) theo số nút, với fanout phù hợp | O(log n) theo số nút | Tổ chức theo khối, thường hữu ích cho storage/cache |

Các bậc nêu ở bảng là kết quả chuẩn trong mô hình thao tác thích hợp. Với hash table, worst-case còn phụ thuộc collision, resize và đối thủ; với B-tree, chi phí I/O và fanout là những đại lượng quan trọng ngoài số phép so sánh.

### 16.1. Khi nào skip list là lựa chọn hợp lý?

- Cần một **tập hoặc map có thứ tự** với tìm/chèn/xóa trực tuyến.
- Muốn duyệt **khoảng khóa tăng dần** thuận tiện sau khi định vị điểm đầu.
- Chấp nhận bảo đảm **kỳ vọng** thay vì yêu cầu worst-case O(log n) tuyệt đối.
- Mô hình liên kết nhiều tầng dễ áp dụng và kiểm chứng hơn các phép tái cân bằng cây trong môi trường cụ thể.
- Có chiến lược metadata, đồng bộ và vòng đời node phù hợp với workload.

### 16.2. Khi nào nên xem xét cấu trúc khác?

- **Deadline cứng:** ưu tiên cấu trúc có worst-case đã chứng minh, ví dụ AVL/red-black.
- **Chủ yếu đọc, ít cập nhật:** mảng sorted có thể tiết kiệm bộ nhớ và locality tốt.
- **Tìm khóa chính xác không cần thứ tự:** hash table có thể đơn giản và nhanh hơn.
- **Dữ liệu trên đĩa / block storage:** B-tree/B+ tree giảm số truy cập khối.
- **Cần rank/select theo chỉ số:** dùng indexable skip list có span hoặc cây có subtree-size, không giả định skip list basic đã O(log n) cho chỉ số.
- **Bảo mật hoặc đầu vào đối kháng:** phải xét mô hình RNG, adaptive adversary và giới hạn tài nguyên.

## 17. Chứng minh ngắn tính đúng của tìm, chèn và xóa

Một cấu trúc dữ liệu không chỉ cần thời gian chạy tốt. Các phép cập nhật phải bảo toàn **bất biến tầng**.

### 17.1. Tìm kiếm không bỏ qua khóa

Giả sử tất cả tầng đều là dãy con **sorted** của L0.

Tại một tầng i, nếu `current.forward[i].key < k`, đi sang phải an toàn: mọi khóa trước successor ấy đều nhỏ hơn k, nên không thể là khóa đang tìm.

Nếu successor ở tầng i có key ≥k hoặc rỗng, đi xuống tầng i−1 là cần thiết vì các node bị bỏ qua ở tầng cao có thể xuất hiện ở tầng thấp. Đến tầng 0, ngay sau tiền nhiệm có khóa <k là ứng viên nhỏ nhất ≥k, nên việc so sánh bằng k xác định đúng `contains(k)`.

### 17.2. Chèn giữ thứ tự ở mọi tầng

Trước `insert(k)`, `update[i]` đứng ngay trước vị trí k tại tầng i:

```text
update[i].key < k < successor.key
```

với các trường hợp biên dùng HEAD hoặc NULL. Khi nối `update[i] -> fresh -> successor`, chuỗi tầng i vẫn tăng chặt. Các tầng `i ≥ H` không đổi, nên vẫn sorted.

Vì `fresh` xuất hiện chính xác ở các tầng `0..H-1`, bất biến **tầng cao là tập con của tầng thấp** được giữ. Không có nhiều node cùng khóa nhờ kiểm tra duplicate trước khi nối.

### 17.3. Xóa giữ thứ tự ở mọi tầng

Nếu target có mặt, việc nối `predecessor.forward[i] = target.forward[i]` ở từng tầng của target chỉ **bỏ một phần tử** khỏi một dãy sorted; không thay thứ tự các node còn lại.

Sau khi gỡ toàn bộ tầng và giảm size, bất biến “một node dữ liệu chỉ tính một lần” vẫn đúng. Việc hạ mức cao nhất khi không còn node ở đó chỉ loại các tầng rỗng, không làm mất dữ liệu tầng đáy.

### 17.4. Chứng minh tính đúng không phụ thuộc random seed

Các lập luận tìm/chèn/xóa trên chỉ dùng **sorted order, quan hệ subset và vị trí tiền nhiệm**. Chúng đúng với **mọi dãy chiều cao hợp lệ**, kể cả khi mọi node chỉ có H=1.

Ngẫu nhiên xuất hiện trong **phân tích chi phí**, không phải điều kiện để thao tác trả ra đúng khóa. Đây là điểm phân biệt rất quan trọng giữa:

- **Tính đúng đắn tất định của thao tác**.
- **Hiệu năng kỳ vọng do hình dạng ngẫu nhiên**.

## 18. Kiểm thử chức năng, bất biến và tính tái lập

### 18.1. Những trường hợp bắt buộc

1. Skip list rỗng: `contains` False, `lower_bound`/`predecessor` None, `keys` rỗng.
2. Một node: tìm đúng, xóa về rỗng, `level_count` trở lại 1.
3. Chèn khóa tăng dần, giảm dần và thứ tự trộn.
4. Nhiều khóa âm, số 0, khóa lớn; sentinel `None` không bị coi là khóa dữ liệu.
5. Chèn trùng: trả False và không tăng `size`.
6. Xóa khóa chưa tồn tại: trả False và không làm hỏng liên kết.
7. Xóa khóa nhỏ nhất, lớn nhất và ở giữa.
8. Xóa node có nhiều tầng, đặc biệt node duy nhất trên tầng cao nhất.
9. Chèn node bốc chiều cao lớn hơn mức đang dùng: các `update[i]` mới đúng HEAD.
10. `MAX_LEVEL=1`: cấu trúc suy biến thành danh sách liên kết nhưng vẫn đúng.
11. `p` ngoài khoảng (0,1), `max_level<1`: từ chối tham số không hợp lệ.
12. `lower_bound` ở dưới min, bằng khóa có sẵn, giữa hai khóa, trên max.
13. `predecessor` dùng điều kiện **nhỏ hơn chặt**, không lấy khóa bằng target.
14. Range query có `low>=high`, biên None và nhiều kết quả.
15. Tạo hai instance với seed độc lập; không dùng state RNG global ngoài ý muốn.
16. Duyệt nửa chừng rồi `insert/discard`: iterator fail-fast theo hợp đồng.
17. Kiểm tra validator thấy node cao bị thiếu khỏi một tầng.
18. Kiểm tra validator phát hiện chu trình hoặc liên kết tự trỏ tại tầng 0.
19. Phân biệt node có giá trị trùng và node identity khi kiểm định.
20. Đánh giá n rất lớn: giới hạn bộ nhớ mảng `update`, số tầng, thời gian, GC.
21. Trên C/C++: kiểm tra lỗi cấp phát và không còn con trỏ treo sau xóa.
22. Trên concurrent implementation: có test và chứng minh riêng về linearizability, memory reclamation.

### 18.2. Kiểm thử đối chiếu với `set` Python

Tạo một **mô hình tham chiếu** bằng `set` để so nội dung. Mỗi lần thao tác trên skip list thì làm thao tác tương ứng trên set, rồi so `sorted(reference)` với kết quả đi tầng đáy.

```python
import random


def test_against_set(seed: int) -> None:
    rng = random.Random(seed)
    sl = SkipList(seed=seed, max_level=24)
    model: set[int] = set()

    for step in range(300):
        key = rng.randrange(-70, 71)
        action = rng.randrange(3)

        if action == 0:  # Insert
            existed = key in model
            result = sl.insert(key)
            assert result == (not existed)
            model.add(key)

        elif action == 1:  # Discard
            existed = key in model
            result = sl.discard(key)
            assert result == existed
            model.discard(key)

        else:  # Contains
            assert sl.contains(key) == (key in model)

        sl.assert_valid()
        assert len(sl) == len(model)
        assert list(sl.keys()) == sorted(model)

    expected = sorted(model)

    for query in (-100, -50, 0, 50, 100):
        greater_or_equal = [x for x in expected if x >= query]
        smaller = [x for x in expected if x < query]

        assert sl.lower_bound(query) == (
            greater_or_equal[0] if greater_or_equal else None
        )
        assert sl.predecessor(query) == (
            smaller[-1] if smaller else None
        )

    assert list(sl.range_keys(-20, 20)) == [
        x for x in expected if -20 <= x < 20
    ]


for seed in range(20):
    test_against_set(seed)
```

Đây là test **tính đúng đắn**. Nó không chứng minh chi phí kỳ vọng O(log n) chỉ vì chạy qua 20 seed. Cũng không nên bật `assert_valid` sau mỗi thao tác trong đường chạy production nếu cần hiệu năng, vì nó kiểm tra toàn cấu trúc.

### 18.3. Kiểm thử iterator bị vô hiệu

```python
sl = SkipList(seed=7)

for key in (10, 20, 30, 40):
    assert sl.insert(key)

it = sl.range_keys(10, 40)
assert next(it) == 10

assert sl.insert(15)  # Thay đổi cấu trúc sau khi đã lấy 10.

try:
    next(it)
    raise AssertionError("Phải từ chối iterator cũ")
except RuntimeError:
    pass

assert list(sl.range_keys(10, 40)) == [10, 15, 20, 30]
```

Một lần `discard` thành công cũng tăng version. **Không thay đổi** do chèn trùng hoặc xóa khóa vắng thì **không** tăng version trong code bài; iterator cũ vẫn tiếp tục.

### 18.4. Kiểm thử dạng dữ liệu “cực đoan”

```python
# MAX_LEVEL=1: chỉ L0, vẫn là một set có thứ tự.
linear = SkipList(max_level=1, seed=42)
for key in range(100):
    assert linear.insert(key)
linear.assert_valid()
assert linear.level_count == 1
assert list(linear.keys()) == list(range(100))

# Xóa mọi node phải trả về đúng trạng thái rỗng.
for key in range(100):
    assert linear.discard(key)
linear.assert_valid()
assert len(linear) == 0
assert linear.level_count == 1

# Tham số không hợp lệ.
for p in (0.0, 1.0, -0.5):
    try:
        SkipList(p=p)
        raise AssertionError("Phải báo lỗi p")
    except ValueError:
        pass
```

### 18.5. Không dùng một seed để “chứng minh xác suất”

Một benchmark xác suất cần lặp qua **nhiều seed**, **nhiều n**, và xem các đại lượng như:

- Số tầng đang dùng `H`.
- Tổng số con trỏ forward thực tế.
- Số bước ngang/đi xuống trong mỗi truy vấn.
- Số cấp phát và bộ nhớ peak.
- Thời gian trung bình, độ lệch, phân vị cao của độ trễ.

Một phép đo đơn lẻ `height=12` ở `n=1000` không chứng minh công thức expected O(log n), cũng không phải lỗi nếu đôi lần thấy height 20 hay 25. **Xác suất** mô tả phân phối qua các lần rút random theo mô hình, không áp đặt giá trị cứng cho mọi lần chạy.

## 19. Các lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Quy tắc sửa |
| --- | --- | --- |
| Dùng `<=` thay `<` khi tìm tiền nhiệm để chèn | Có thể vượt qua node bằng target, chèn trùng | Dừng tại ứng viên đầu tiên ≥ target |
| Duyệt lại từ HEAD ở từng tầng | Bỏ phí đường nhảy, tăng số bước | Giữ `current` khi đi xuống |
| Quên gán `fresh.forward[i]` trước khi đổi liên kết tiền nhiệm | Mất successor hoặc tạo vòng tự trỏ | Lưu successor cũ trước |
| Chỉ cấp một node cho mỗi tầng | Nhân bản dữ liệu, sai identity và `size` | Một node chứa nhiều ô forward |
| Không thêm HEAD làm tiền nhiệm cho tầng mới | Đọc `update[i]` chưa khởi tạo | Điền HEAD tại mọi tầng vừa mở |
| Đếm tổng số liên kết thành `size` | `size` lớn hơn số khóa | Đếm node tầng đáy |
| Chèn trùng mà không có chính sách | Vỡ set, thứ tự không tăng chặt | Kiểm tra candidate trước khi bốc level |
| Xóa node chỉ khỏi L0 | Còn liên kết tầng cao tới node cũ | Gỡ ở mọi tầng node tham gia |
| Xóa mà `free` node trước khi lấy `forward[0]` | Use-after-free | Lưu successor trước khi free |
| Gọi `free` node theo từng tầng | Double free | Destructor đi L0, mỗi object một lần |
| Không hạ tầng cao nhất sau xóa | Vòng tìm đi qua nhiều tầng rỗng, metadata sai | Giảm level tới tầng có node hoặc mức 1 |
| Giới hạn L rất nhỏ nhưng tuyên bố O(log n) cho mọi n | Sai phân tích tiệm cận | Chọn trần theo quy mô và công bố phạm vi |
| Nói random height luôn tạo cây/danh sách thấp | Nhầm expected với worst-case | Phân biệt O(log n) kỳ vọng với trường hợp xấu |
| Chọn p=0 hoặc p=1 | Cơ chế phân phối không còn như giả định | Kiểm tra `0<p<1` |
| Dùng `random.Random(seed)` như một biện pháp bảo mật | Dễ đoán trạng thái RNG trong mô hình đối kháng | Đánh giá threat model và nguồn random phù hợp |
| Duyệt lúc đang thay liên kết | Kết quả không nhất quán hoặc data race | Snapshot, khóa hoặc iterator policy |
| Thêm span nhưng chỉ sửa forward | Rank/select trả sai | Cập nhật span trên mọi đường bị ảnh hưởng |
| Dùng hash/set dựa trên value để kiểm tra node identity | Gộp nhầm các node | Identity hoặc ID duy nhất |
| Chỉ benchmark đầu vào đã shuffle | Che tình huống sorted/reversed | Test dữ liệu có cấu trúc và nhiều seed |

Một bộ kiểm định nên nêu rõ **lỗi invariant nào** (mất node trên tầng cao, chu trình, sai thứ tự, khóa lặp, sai size) thay vì chỉ báo “sai” chung chung. Các lỗi liên kết thường khó gỡ hơn khi dữ liệu lớn, nên kiểm tra trên ví dụ nhỏ trước khi thử hàng triệu khóa.


## 20. Bài tập thực hành có lời giải

### Bài 1. Vì sao gọi là “skip” list?

Với danh sách khóa `10,20,30,40,50,60`, một danh sách liên kết thông thường tìm khóa 60 ra sao? Skip list thay đổi điều gì?

**Lời giải:** Danh sách thường đi qua nhiều liên kết liên tiếp từ HEAD tới 60, tốn O(n) xấu nhất. Skip list thêm những liên kết ở tầng cao để **bỏ qua** một số node trung gian; sau khi đến gần đích, thuật toán xuống tầng thấp hơn để tìm chính xác khóa. Nó không xóa các node bị bỏ qua khỏi tầng 0.

### Bài 2. Một node có mặt tại mấy tầng?

Một node có `H=4`. Nó tham gia những tầng có chỉ số nào? Có phải bốn object khác nhau không?

**Lời giải:** Nó tham gia **L0, L1, L2, L3**, nhưng là **một object** chứa bốn ô `forward[0..3]`. `size` chỉ tăng 1 khi node được chèn.

### Bài 3. Tầng đáy chứa những khóa nào?

Cho L2 gồm `10,40` và L1 gồm `10,30,40,60`. Tầng 0 phải chứa những khóa nào?

**Lời giải:** Tầng 0 **ít nhất** phải chứa `10,30,40,60`, vì mọi node ở tầng cao phải có mặt ở các tầng thấp hơn. Tầng 0 có thể chứa thêm node chỉ có H=1. Không thể xác định toàn bộ L0 nếu chưa có thông tin khác.

### Bài 4. Tại sao chỉ đi ngang khi `next.key < target`?

Khi tìm khóa 30 trong tầng có chuỗi `HEAD → 10 → 30 → 50`, vì sao không đi qua node 30 khi điều kiện tìm tiền nhiệm dùng `<`?

**Lời giải:** Ta muốn đứng **ngay trước ứng viên đầu tiên ≥30** để có thể kiểm tra khóa 30 tồn tại và giữ tiền nhiệm cho chèn/xóa. Nếu đi qua ứng viên bằng target, thuật toán dễ bỏ qua chỗ kiểm tra trùng.

### Bài 5. Tìm khóa không có trong list

Trên cấu trúc ở Mục 3, tìm 55. `lower_bound(55)` và `predecessor(55)` là gì?

**Lời giải:** `lower_bound(55)=60`, `predecessor(55)=50`. `contains(55)=False` vì ứng viên 60 không bằng 55.

### Bài 6. Truy vấn tại hai biên

Với dãy `10,20,30`, kết quả `lower_bound(5)`, `lower_bound(35)`, `predecessor(10)` và `predecessor(25)` lần lượt là gì?

**Lời giải:** Lần lượt **10, không có (None), không có (None), 20**. Predecessor là quan hệ nhỏ hơn **chặt**, nên không trả khóa bằng target.

### Bài 7. Mảng `update[]`

Trong skip list mẫu ở Mục 3, khi tìm tiền nhiệm để chèn `55`, các mục `update[3], update[2], update[1], update[0]` lần lượt là gì?

**Lời giải:** Lần lượt là `40,40,40,50`. Ở các tầng cao, không có nút giữa 40 và 55; ở tầng 0 còn có nút 50.

### Bài 8. Chèn node mới cao hai tầng

Một node mới key=55 có H=2. Với `update[0]=50`, `update[1]=40`, successor tương ứng là 60, cần sửa các liên kết nào?

**Lời giải:** Ở L0: `55.forward[0]=60` rồi `50.forward[0]=55`. Ở L1: `55.forward[1]=60` rồi `40.forward[1]=55`. Không sửa L2/L3.

### Bài 9. Đảo thứ tự hai phép gán khi chèn

Tại một tầng i, chương trình làm `update[i].forward[i]=fresh` trước rồi mới `fresh.forward[i]=update[i].forward[i]`. Lỗi là gì?

**Lời giải:** Khi phép gán thứ hai chạy, `update[i].forward[i]` đã là `fresh`; do đó `fresh.forward[i]=fresh`, tạo self-loop và làm mất successor cũ. Cần lưu successor **trước** khi đổi con trỏ tiền nhiệm.

### Bài 10. Node mới cao hơn danh sách

Skip list đang dùng ba tầng (L0–L2). Một node được bốc H=5. `update[3]` và `update[4]` phải là gì?

**Lời giải:** Cả hai phải là **HEAD**, vì L3 và L4 trước đó chưa có node dữ liệu. Sau khi nối, `current_level=5`.

### Bài 11. Thao tác trùng khóa

`insert(20)` được gọi khi 20 đã có, và skip list là một set. Theo code bài, có cấp node mới hoặc bốc level mới không?

**Lời giải:** Không. Hàm trả False sau khi kiểm tra ứng viên bằng 20, `size` không đổi và không tiêu thụ một lần bốc random trong chính sách này.

### Bài 12. Xóa node ở ba tầng

Node key=10 có H=3. Để xóa đúng, chương trình phải gỡ liên kết ở các tầng nào?

**Lời giải:** **L0, L1 và L2**. Không được chỉ gỡ ở L0, vì những tầng khác vẫn còn đường trỏ tới node 10. Nếu ngôn ngữ cấp phát thủ công, chỉ giải phóng node **sau khi** mọi liên kết đang sở hữu tới nó đã được xử lý theo hợp đồng.

### Bài 13. Khi nào hạ tầng cao nhất?

Skip list đang dùng bốn tầng và node vừa xóa là node duy nhất trên L3. Những tầng L2, L1 còn dữ liệu. `current_level` sau xóa là gì?

**Lời giải:** Là **3**, tương ứng L0–L2. Nếu cả L2 cũng rỗng thì tiếp tục hạ tới tầng cao nhất còn node; khi danh sách rỗng giữ `current_level=1`.

### Bài 14. Cây/danh sách rỗng

Theo quy ước code bài, skip list rỗng có `size` và `level_count` là bao nhiêu?

**Lời giải:** `size=0` và `level_count=1`. HEAD còn tồn tại, `head.forward[0]=None`; các ô cao hơn cũng rỗng.

### Bài 15. Xác suất đạt ít nhất bốn tầng

Với `p=1/2` và mô hình không trần, xác suất một node có `H≥4` là bao nhiêu?

**Lời giải:** `p^{4-1}=(1/2)^3=1/8`. Phải được nâng thành công ba lần từ mức 1 tới mức 4.

### Bài 16. Xác suất có đúng ba tầng

Với `p=1/2` và không trần, `Pr(H=3)` là bao nhiêu?

**Lời giải:** `(1-p)p^{3-1}=(1/2)(1/2)^2=1/8`. Cần hai lần nâng thành công rồi một lần dừng.

### Bài 17. Trần mức làm đổi phân phối đuôi

Với `p=1/2` và `MAX_LEVEL=3`, `Pr(H=3)` bằng 1/8 hay 1/4?

**Lời giải:** **1/4**. Khi đã đạt H=3 thì hàm dừng do trần, không phải tung thêm đồng xu để quyết định nâng/dừng. Vì thế `Pr(H=3)=Pr(H≥3)=p²=1/4`. Công thức `(1-p)p^{k-1}` cho đúng H=k chỉ dùng nguyên xi **trước mức trần**.

### Bài 18. Kỳ vọng số tầng/node

Với p=1/2 và không đặt trần, số ô forward kỳ vọng mỗi node là bao nhiêu? Với n node?

**Lời giải:** `E[H]=1/(1-p)=2` slot/node; tổng số slot kỳ vọng `2n`, chưa tính HEAD, metadata và allocator overhead. Đây là O(n) bộ nhớ liên kết kỳ vọng.

### Bài 19. Kỳ vọng với trần mức

Với `p=1/2` và `MAX_LEVEL=3`, `E[H]` là bao nhiêu?

**Lời giải:** `1+1/2+1/4=7/4=1.75` slot/node. Công thức tổng quát là `(1-p^L)/(1-p)`.

### Bài 20. Số node kỳ vọng ở tầng i

Với 1024 node, p=1/2 và mức trần cho phép ít nhất L7, số node kỳ vọng ở tầng L5 là bao nhiêu?

**Lời giải:** `1024*(1/2)^5=32` node. Không được hiểu là **chắc chắn đúng 32** trong mỗi lần chạy.

### Bài 21. Xác suất có tầng cực cao

Với n node, xác suất có ít nhất một node cao ≥k được chặn trên như thế nào?

**Lời giải:** Theo union bound, `Pr(max H_i≥k)≤n p^{k-1}`. Đây là **chặn trên xác suất**, có thể lớn hơn 1 khi k nhỏ (khi ấy chỉ chặn tầm thường), không phải một phương trình chính xác cho mọi k.

### Bài 22. Tình huống xấu nhất

Nếu tất cả node của skip list đều có H=1, tìm một khóa rất lớn có thể mất bao nhiêu bước?

**Lời giải:** Θ(n), vì cấu trúc suy biến thành danh sách liên kết tầng đáy. Ngẫu nhiên hóa chỉ cải thiện **kỳ vọng**, không loại trừ trường hợp này.

### Bài 23. Worst-case với mức không giới hạn

Một implementation cho phép random level cao tùy ý. Có đủ chính xác khi tuyên bố worst-case tìm chỉ là O(n), không nhắc gì tới số tầng H?

**Lời giải:** Không. Một lượt tìm phải đi xuống H tầng, có thể tốn Ω(H) bước ngay cả khi n nhỏ. Chặn nên viết theo **O(n+H)** cho phần đi ngang/đi xuống (cộng chi phí metadata), hoặc đặt chính sách giới hạn H rõ ràng.

### Bài 24. Giới hạn L cố định và n tăng mãi

Với p=1/2, `MAX_LEVEL=10` không đổi nhưng n tăng vô hạn, có thể cam kết expected O(log n) cho mọi n?

**Lời giải:** Không. Tầng cao nhất L9 có số node kỳ vọng `n/512`, tăng tuyến tính theo n; khi không có tầng cao hơn để nhảy qua, tìm xa có thể tốn nhiều bước ngang. Cần chọn mức tối đa tương ứng với quy mô dự kiến.

### Bài 25. Range query

Dãy khóa là `[10,20,30,40,50,60,70]`. `range_keys(25,60)` trả các khóa nào, và tại sao 60 không xuất hiện?

**Lời giải:** `[30,40,50]`. Khoảng được định nghĩa là **`[low, high)`**, bao gồm low nếu bằng một khóa, nhưng **loại high**. Thuật toán định vị `lower_bound(25)=30` rồi đi tầng đáy đến khi gặp 60.

### Bài 26. Rank và select

Với dãy `[10,20,30,40,50]`, `rank_less_than(40)` và `select(4)` (1-based) bằng gì?

**Lời giải:** `rank_less_than(40)=3`, `select(4)=40`. Nếu chỉ có forward, đếm tuần tự có thể O(n). Với span/width được duy trì đúng, hai thao tác có thể đạt O(log n) kỳ vọng.

### Bài 27. Span của cạnh HEAD → 40

Ở tầng đáy `HEAD→10→20→30→40→50`, một liên kết tầng cao đi thẳng `HEAD→40`. Span theo quy ước bài là bao nhiêu?

**Lời giải:** **4**, vì vượt qua các node 10,20,30 và đến node 40, tính cả node đích. Head đứng ở vị trí thứ tự 0.

### Bài 28. Cập nhật span khi chèn

Một node mới H=1 được chèn vào tầng 0 dưới một liên kết tầng cao `u→v`. Có thể bỏ qua cập nhật span của cạnh `u→v` vì node mới không xuất hiện ở tầng đó không?

**Lời giải:** Không. Span đếm **số node tầng đáy** mà cạnh nhảy qua, nên chèn vào đoạn ấy làm span tăng 1 dù liên kết forward ở tầng cao không đổi. Rank/select sẽ sai nếu quên.

### Bài 29. Giải phóng node trong C

Node key=40 có H=4 và xuất hiện ở bốn tầng. Khi hủy toàn bộ skip list sở hữu riêng, nên gọi `free` mấy lần cho object đó?

**Lời giải:** **Một lần**. Mọi ô forward nằm trong **cùng object node**; đi theo L0 để thu mỗi node đúng một lần. Không duyệt các tầng cao để giải phóng cùng node lần nữa.

### Bài 30. Iterator sau khi xóa

Một iterator đang giữ con trỏ tới node 30. Thao tác `discard(30)` đã thành công. Có được giả định iterator an toàn để lấy phần tử tiếp theo trong mọi ngôn ngữ không?

**Lời giải:** Không. Trong C/C++ con trỏ có thể treo; trong Python object có thể còn sống nhưng không còn thuộc set. Phải tuân theo chính sách invalidation, khóa hoặc snapshot. Mã Python của bài dùng `_version` để báo lỗi khi tiếp tục sau cập nhật qua API.

### Bài 31. Fail-fast có thay thế khóa không?

Hai thread cùng truy cập `forward` mà không có đồng bộ, một thread chỉ kiểm tra `_version` đầu và cuối. Điều này có bảo đảm skip list thread-safe không?

**Lời giải:** Không. Trong C/C++ còn có nguy cơ data race; version check không thay thế memory ordering, lifetime và atomicity. Cần mutex hoặc concurrent skip list được thiết kế với CAS, reclamation và linearization points đúng.

### Bài 32. Chọn cấu trúc dữ liệu

Một ứng dụng cần set khóa có thứ tự, rất nhiều truy vấn range, chèn/xóa trực tuyến và chấp nhận độ trễ kỳ vọng. Skip list có phù hợp không? Nếu yêu cầu worst-case O(log n) cứng thì sao?

**Lời giải:** Skip list là **ứng viên phù hợp** cho workload thứ nhất vì lower_bound rồi duyệt L0 trả range theo thứ tự. Nếu cần worst-case O(log n) cho mọi thao tác, nên ưu tiên một cấu trúc cân bằng tất định như AVL/red-black hoặc một giải pháp khác có bảo đảm được chứng minh.

### Bài 33. Chọn p

So sánh số slot forward kỳ vọng mỗi node với p=1/4 và p=1/2 trong mô hình không trần.

**Lời giải:** Với p=1/4, `E[H]=1/(1-1/4)=4/3`. Với p=1/2, `E[H]=2`. Giá trị p nhỏ hơn giảm số slot kỳ vọng nhưng có thể làm đường đi ngang dài hơn; không thể chọn p chỉ dựa trên một phép đo.

### Bài 34. Kiểm định tầng cao bị thiếu node

Node 50 có `len(forward)=3` và xuất hiện ở L0, L2 nhưng vì một lỗi liên kết không có trong chuỗi L1. Cấu trúc còn hợp lệ không?

**Lời giải:** Không. Một node có chiều cao 3 phải có mặt ở L0, L1, L2. Validator kiểm đếm số node có chiều cao đủ lớn so với node thực tế ở từng tầng có thể phát hiện lỗi thiếu node, ngay cả khi L0 vẫn sorted.

### Bài 35. Độ phức tạp của việc xuất k kết quả

Nếu skip list có phân phối tầng phù hợp, duyệt mọi khóa trong `[a,b)` và nhận k kết quả có kỳ vọng bao nhiêu thời gian?

**Lời giải:** **O(log n + k)**, gồm tìm lower_bound(a) kỳ vọng O(log n) và đi qua k node liên tiếp ở tầng đáy. Với implementation cụ thể luôn cấp `update` độ dài L, cần tính thêm **O(L)** cho bước khởi đầu, tức O(log n+L+k) khi L là tham số cấu hình có thể thay đổi.

## 21. Tổng kết và checklist triển khai

**Skip list là một cấu trúc liên kết có thứ tự, được gia tốc bằng các tầng nhảy qua node.** Nó không đòi dữ liệu vào được shuffle và không dùng phép truy cập ngẫu nhiên vào mảng như binary search; thay vào đó, nó dùng những **con trỏ forward ở các tầng được chọn ngẫu nhiên**.

Ghi nhớ các nguyên tắc quan trọng:

1. **Tầng 0 chứa toàn bộ khóa**, các tầng cao là những dãy con tăng dần. Node cao H có đúng H ô forward và chỉ là **một node dữ liệu**.
2. **Tìm kiếm:** bắt đầu từ HEAD ở tầng cao nhất, đi sang phải khi khóa kế tiếp nhỏ hơn target, rồi đi xuống. Ở L0, successor của tiền nhiệm là ứng viên đầu tiên ≥ target.
3. **Chèn:** lưu `update[i]` cho mỗi tầng, xử lý khóa trùng, bốc H, điền HEAD ở tầng mới, nối `fresh.forward[i]` trước khi nối tiền nhiệm.
4. **Xóa:** xác định đúng node, bỏ liên kết ở **mọi tầng node tham gia**, hạ mức cao nhất khi rỗng; trong ngôn ngữ cấp phát thủ công, **hủy object đúng một lần**.
5. **Xác suất:** với mỗi lần nâng thành công xác suất p, `Pr(H≥k)=p^{k-1}`, `E[H]=1/(1-p)` không trần; p=1/2 cho trung bình 2 forward slots/node.
6. **Chi phí:** với tầng được hỗ trợ đủ và nguồn random đúng giả định, tìm/chèn/xóa O(log n) kỳ vọng; tổng metadata forward O(n) kỳ vọng. Trường hợp xấu vẫn có thể tuyến tính hoặc phụ thuộc số tầng H thực tế.
7. **`MAX_LEVEL` là quyết định thiết kế:** giới hạn bộ nhớ mỗi node và số lần xuống tầng, nhưng nếu cố định quá nhỏ so với n thì mất bảo đảm logarit tiệm cận.
8. **Duyệt khoảng:** sau một lần lower_bound, đi theo `forward[0]`, cho thời gian kỳ vọng O(log n+k) khi xuất k khóa. Muốn rank/select nhanh hơn cần **span/width** và cập nhật metadata cẩn thận.
9. **Bất biến không phụ thuộc seed:** dù bốc level thế nào, cấu trúc vẫn phải sorted, không chu trình, không node lặp, `size` đúng và mọi tầng cao là tập con của tầng thấp.
10. **Vòng đời và đồng thời phải được thiết kế riêng:** fail-fast không phải snapshot; mutex/CAS, hủy node và iterator invalidation không được bỏ qua.

Trước khi chọn skip list cho một bài toán thực tế, hãy trả lời: **Có cần giữ thứ tự và duyệt khoảng không? Tỷ lệ chèn/xóa so với đọc là bao nhiêu? Ứng dụng chấp nhận expected O(log n) hay đòi worst-case cứng? `p` và `MAX_LEVEL` có phù hợp n tối đa? Ai sở hữu node và ai có thể duyệt đồng thời?**

Nếu trả lời rõ những câu hỏi đó, skip list trở thành một ví dụ dễ kiểm chứng cho tư duy cấu trúc dữ liệu: **thêm một lượng metadata kỳ vọng tuyến tính để rút ngắn đường tìm từ tuyến tính xuống logarit kỳ vọng, trong khi vẫn giữ đầy đủ bất biến của các danh sách liên kết có thứ tự**.

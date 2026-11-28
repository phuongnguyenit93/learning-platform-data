# Tìm kiếm, chèn và xóa trong skip list

**Skip list** là một cấu trúc dữ liệu có thứ tự sử dụng nhiều tầng danh sách liên kết để tìm kiếm nhanh hơn một danh sách đơn thông thường. Tầng đáy chứa toàn bộ khóa theo thứ tự; những tầng cao chứa tập con các nút và đóng vai trò **đường đi tắt**. Mỗi nút được bốc một chiều cao ngẫu nhiên khi tạo, nhờ đó cấu trúc có **chi phí tìm, chèn và xóa O(log n) kỳ vọng** dưới các giả định xác suất phù hợp, trong khi vẫn giữ được cách nối và tháo liên kết tương đối trực quan.

Bài **“Tìm kiếm, chèn và xóa trong skip list”** thuộc chương **Cấu trúc ngẫu nhiên**, module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo định hướng module, chúng ta sử dụng kiến thức về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị để nhận diện **bất biến**, thực hiện thao tác đúng và phân tích **thời gian/bộ nhớ**. Trọng tâm ở đây là **ba thao tác cốt lõi trên skip list**: tìm vị trí bằng các tầng, gắn một nút vào đúng những chuỗi liên kết, và tháo một nút khỏi tất cả những tầng nó tham gia. Cách chọn phân phối độ cao được giải thích vừa đủ để tính chi phí, nhưng **ngẫu nhiên không thay thế được chứng minh tính đúng của các phép nối**.

Sau bài, bạn có thể:

- Biểu diễn rõ một node có khóa và các `forward[i]`; phân biệt **số tầng** với **chỉ số tầng**, sentinel `HEAD` và node dữ liệu.
- Mô phỏng tìm kiếm **từ trên xuống, sang phải khi next.key < key**, rồi giải thích vì sao kết thúc ở tiền nhiệm chính xác tại tầng 0.
- Dùng mảng `update[]` để lưu **tiền nhiệm trên từng tầng**, áp dụng cho cả chèn và xóa mà không tìm lại từ HEAD cho mỗi cấp.
- Chèn khóa mới với chiều cao ngẫu nhiên, xử lý khóa trùng và trường hợp nút mới cao hơn mức đang dùng.
- Xóa khóa hiện có khỏi **tất cả** các tầng, thu hẹp tầng cao nhất, tránh con trỏ treo và giải phóng nhiều lần.
- Cài đặt skip list dạng **set khóa nguyên** bằng Python theo vòng lặp; viết bộ kiểm định bất biến và test đối chiếu với `set`.
- Lý giải O(log n) **kỳ vọng**, O(n) trường hợp bất lợi (khi số tầng được giới hạn hợp lý), chi phí mảng `update` và ảnh hưởng của `MAX_LEVEL`.
- Nhận diện các lỗi như `<=` thay `<`, tự tạo vòng, quên nối tầng cao, giữ liên kết sau xóa hoặc thay đổi cấu trúc trong lúc đang duyệt.

## 1. Nhắc lại đúng mô hình: những tầng liên kết bỏ qua

Trước hết, ta lưu tập khóa nguyên phân biệt:

```text
S = {10, 20, 30, 40, 50, 60, 70, 80}

Tầng 3: HEAD ----------------------> 40 --------------------> NIL
Tầng 2: HEAD -----> 10 -----------> 40 -----------> 80 ---> NIL
Tầng 1: HEAD -----> 10 ---> 30 ---> 40 ---> 60 -----> 80 ---> NIL
Tầng 0: HEAD -----> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 70 -> 80 -> NIL
```

Trong ví dụ:

- **Tầng 0** có **mọi khóa** của tập, chính là danh sách liên kết có thứ tự.
- **Tầng 1–3** là các tập con được chọn theo chiều cao của từng node.
- Node 40 tham gia tầng 0, 1, 2, 3, nhưng **vẫn là một object duy nhất**.
- Node 20 tham gia đúng một tầng 0; nó vẫn tồn tại và vẫn tìm được.
- Mọi liên kết ở một tầng đưa ta sang **khóa lớn hơn**, không trỏ ngược về khóa nhỏ hơn.

### 1.1. Node có những trường nào?

Với node cao `H`, ta lưu:

```text
Node {
    key: khóa
    forward[0]: node kế tiếp ở tầng 0, hoặc NIL
    forward[1]: node kế tiếp ở tầng 1, hoặc NIL
    ...
    forward[H-1]: node kế tiếp ở tầng H-1, hoặc NIL
}
```

Mảng `forward` được đánh chỉ số **từ 0**. Nếu node có `H=3` thì các chỉ số hợp lệ là **0, 1, 2**, không có `forward[3]`. Một node chỉ xuất hiện ở tầng i nếu nó **có ô forward[i]**.

### 1.2. `HEAD` và `NIL`

Ta dùng một sentinel **HEAD** đứng trước tất cả khóa. HEAD **không phải** node mang khóa nhỏ nhất, tránh xung đột khi người dùng có khóa âm hoặc khóa rất nhỏ. Trong Python, có thể cho `HEAD.key = None` và **không bao giờ so sánh `None` với int**.

Cuối mỗi tầng dùng `None`/`NULL` (trong sơ đồ ghi `NIL`). Đây là **liên kết rỗng**, không phải một node có dữ liệu.

### 1.3. Năm bất biến không được phá

Một skip list **set** hợp lệ cần:

1. `forward[0]` từ HEAD đi qua **mỗi node đúng một lần** và khóa tăng chặt.
2. Mọi tầng `i>0` đi qua một **dãy con tăng chặt** của tầng 0.
3. Một node có `H` ô forward phải có mặt **ở tất cả tầng `0..H-1`**, không được bỏ sót giữa chừng.
4. `size` đếm node dữ liệu ở tầng 0, không đếm số slot liên kết; `level_count` là tầng cao nhất hiện dùng cộng 1, ít nhất bằng 1 kể cả khi rỗng.
5. Cùng một node có thể được nhìn thấy trên nhiều tầng, nhưng chỉ có **một danh tính** và một chủ sở hữu vòng đời.

Các thuật toán tìm/chèn/xóa bên dưới đúng vì chúng **giữ lại hoặc khôi phục** những bất biến ấy sau mỗi thao tác.

## 2. Tìm kiếm từ trên xuống: nguyên tắc đi phải rồi đi xuống

Với khóa đích `k`, hãy tưởng tượng đang ở vị trí `current` trên tầng `i`:

- Nếu `current.forward[i]` có khóa **nhỏ hơn k**, có thể **đi sang phải** tới node đó.
- Nếu liên kết kế tiếp rỗng hoặc khóa kế tiếp **lớn hơn hoặc bằng k**, **không đi qua**; xuống tầng i−1.
- Lặp cho tới tầng 0.
- Node ngay sau `current` ở tầng 0 là khóa **nhỏ nhất ≥ k**, nếu có.

**Tại sao điều kiện là `< k`, không phải `<= k`?** Vì ta cần dừng **trước** nút có khóa đúng bằng k. Điều này vừa giúp kiểm tra tồn tại, vừa thu được tiền nhiệm để nối/chỉnh liên kết.

### 2.1. Mô phỏng tìm khóa có mặt: `k=60`

Dùng cấu trúc ở Mục 1:

```text
L3: HEAD ----------------> 40 ----------------------> NIL
L2: HEAD ---> 10 -------> 40 -------------> 80 ----> NIL
L1: HEAD ---> 10 -> 30 -> 40 -> 60 -------> 80 ----> NIL
L0: HEAD ---> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 70 -> 80
```

| Bước | Tầng | `current` | Kiểm tra liên kết kế tiếp | Hành động |
| ---: | --- | --- | --- | --- |
| 1 | L3 | HEAD | `40 < 60` | Đi phải tới 40 |
| 2 | L3 | 40 | Không còn node L3 | Xuống L2 |
| 3 | L2 | 40 | `80 ≥ 60` | Xuống L1 |
| 4 | L1 | 40 | `60 ≥ 60` | Xuống L0 |
| 5 | L0 | 40 | `50 < 60` | Đi phải tới 50 |
| 6 | L0 | 50 | `60 ≥ 60` | Kết thúc, ứng viên là 60 |

Kết quả: `contains(60)=True` vì `current.forward[0].key == 60`.

Chú ý nút 60 đã xuất hiện ở L1, nhưng thuật toán **không cần đi vào node 60 ở tầng cao**. Nó dừng trước đích, xuống L0 và kiểm tra đúng ứng viên.

### 2.2. Mô phỏng tìm khóa vắng: `k=55`

| Tầng | Tiền nhiệm xa nhất có khóa `<55` |
| --- | --- |
| L3 | 40 |
| L2 | 40 |
| L1 | 40 |
| L0 | 50 |

Ứng viên sau tiền nhiệm L0 là 60, nên:

```text
contains(55)      = False
lower_bound(55)   = 60
predecessor(55)   = 50
```

Đây chính là điểm sẽ dùng để chèn 55 ở tầng 0: **giữa 50 và 60**.

### 2.3. Ba trường hợp biên khi tìm

Với các khóa tầng 0 `[10,20,30]`:

| Truy vấn | `contains` | `lower_bound` | Tiền nhiệm nhỏ hơn chặt |
| --- | --- | --- | --- |
| `k=5` | False | 10 | Không có |
| `k=20` | True | 20 | 10 |
| `k=25` | False | 30 | 20 |
| `k=99` | False | Không có | 30 |
| Cấu trúc rỗng | False | Không có | Không có |

Không có tiền nhiệm **không phải là lỗi**: `current` đơn giản vẫn là sentinel HEAD.

## 3. Bất biến của vòng tìm kiếm và chứng minh ngắn tính đúng

Gọi `u` là vị trí hiện tại trên một tầng. Khi ta đi từ u tới v qua `forward[i]` vì `v.key < k`, ta biết v **không thể** là khóa k, và mọi node đã vượt qua trên tầng ấy cũng có khóa nhỏ hơn k.

Nếu `next.key ≥ k`, ta không được vượt tiếp bằng liên kết đó, vì sẽ bỏ qua một ứng viên hợp lệ. Nhưng các node **không xuất hiện ở tầng i** có thể hiện diện ở tầng i−1, nên ta **đi xuống** để tìm chi tiết hơn.

### 3.1. Bất biến

Sau khi hoàn thành tìm kiếm trên tầng i, `current`:

- là HEAD hoặc một node có key **nhỏ hơn k**;
- không thể đi xa thêm sang phải ở tầng i mà vẫn giữ key nhỏ hơn k;
- cũng nằm ở mọi tầng thấp hơn, nên có thể tiếp tục tìm mà không trở về HEAD.

Tầng 0 có **toàn bộ** khóa. Do đó, khi đi hết tầng 0, `current.forward[0]` là **node nhỏ nhất có key ≥ k**, nếu tồn tại.

### 3.2. Pseudocode `search` không cần `update[]`

Nếu chỉ cần trả có/không, chưa cần mảng tiền nhiệm từng tầng:

```text
SEARCH(k):
    current = HEAD

    for i from level_count - 1 down to 0:
        while current.forward[i] != NIL
              and current.forward[i].key < k:
            current = current.forward[i]

    candidate = current.forward[0]

    if candidate != NIL and candidate.key == k:
        return candidate
    else:
        return NOT_FOUND
```

Vòng lặp này chỉ mang một con trỏ `current` và biến `i`. Nó dùng **O(1) bộ nhớ phụ trợ** cho tìm khóa chính xác nếu bỏ qua nội bộ RNG/cấu trúc đã tồn tại.

### 3.3. Dừng tại lần gặp khóa bằng k trên tầng cao có được không?

Nếu `current.forward[i].key == k`, ta đã tìm được một node có khóa k nên **có thể trả True sớm** với thao tác `contains`, miễn là các tầng đúng bất biến.

Tuy nhiên, để dùng **cùng thủ tục** phục vụ chèn/xóa, ta cố tình **không dừng sớm**: cần thu được tiền nhiệm **trên mọi tầng**. Đây là lý do một hàm tìm phục vụ update thường có thêm mảng `update[]`, còn hàm tìm chỉ đọc có thể đơn giản và ít cấp phát hơn.

## 4. Mảng `update[]`: lưu đường sửa liên kết

Tìm thấy khóa chưa đủ để **chèn** hoặc **xóa**. Trong danh sách liên kết đơn, ta cần **con trỏ tới node đứng ngay trước** vị trí định sửa.

Với skip list, có **nhiều tầng**, nên phải tìm các tiền nhiệm ở **từng tầng**:

\[
update[i]=\text{node tiền nhiệm của k trên tầng }i.
\]

Nếu không có node có key < k ở tầng i, `update[i]=HEAD`.

### 4.1. Cách tạo `update[]` trong cùng lượt tìm

```text
FIND_UPDATE(k):
    current = HEAD
    create update[level_count]

    for i from level_count - 1 down to 0:
        while current.forward[i] != NIL
              and current.forward[i].key < k:
            current = current.forward[i]
        update[i] = current

    return update
```

Chúng ta **không đi lại từ HEAD** cho mỗi tầng. `current` ở tầng i luôn có mặt tại tầng i−1, nên tiếp tục đi ngang từ đúng vị trí này.

### 4.2. Ví dụ `update[]` cho `k=55`

Trên cấu trúc mẫu:

```text
update[3] = node(40)
update[2] = node(40)
update[1] = node(40)
update[0] = node(50)
```

Các phần tử `update[i]` là **tham chiếu đến node thật**, không chỉ là giá trị 40 hoặc 50. Khi sửa liên kết, ta cần thao tác với **chính object** tại vị trí đó.

### 4.3. Chi phí và phạm vi của `update[]`

- Nếu đang dùng H tầng, bản tối giản cần lưu **H con trỏ**.
- Có thể dùng mảng dung lượng cố định L=`MAX_LEVEL` để đơn giản hóa code, đổi lại mỗi lần chèn/xóa cấp/phải giữ O(L) ô.
- Khi node mới được bốc cao hơn H, các vị trí `update[i]` mới (i≥H) **phải điền HEAD**, vì những tầng ấy trước đó trống.

Tránh lỗi **đọc `update[i]` chưa khởi tạo** khi một node mới cao hơn mọi node cũ.

## 5. Chèn một khóa mới: ba giai đoạn rõ ràng

Chèn khóa `k` gồm ba giai đoạn:

1. **Tìm chỗ chèn và kiểm tra trùng khóa**.
2. **Bốc chiều cao và chuẩn bị nút mới**.
3. **Nối node vào đúng các tầng mà nó tham gia**.

Phép nối ở mỗi tầng tương tự chèn một node vào danh sách đơn, nhưng phải thực hiện **đồng bộ trên nhiều tầng**.

### 5.1. Giai đoạn I — tìm vị trí và chống trùng

```text
update = FIND_UPDATE(k)
candidate = update[0].forward[0]

if candidate != NIL and candidate.key == k:
    return ALREADY_EXISTS
```

Ví dụ đã có 55, gọi `insert(55)` lần nữa phải **không tạo thêm node** nếu cấu trúc theo chính sách set.

Việc chỉ bốc random **sau khi biết khóa mới** cũng giúp test với seed cố định dễ tái lập: một lần chèn thất bại do trùng khóa không tiêu thụ thêm số random.

### 5.2. Giai đoạn II — bốc chiều cao H

Mỗi node mới nhận một chiều cao **H≥1**, thường bốc bằng các lần nâng mức có xác suất p:

```text
RANDOM_HEIGHT(p, MAX_LEVEL):
    H = 1
    while H < MAX_LEVEL and coin_flip(p) succeeds:
        H += 1
    return H
```

Ví dụ `H=2` nghĩa là node mới tham gia tầng 0 và tầng 1. Nó không xuất hiện ở tầng 2 dù `update[2]` đã được tìm.

Nếu H cao hơn `level_count` hiện tại, các tầng mới có `update[i]=HEAD`. Ta chỉ nâng biến `level_count` sau khi đã chuẩn bị thành công những dữ liệu cần thiết để gắn node.

### 5.3. Giai đoạn III — sửa hai liên kết tại mỗi tầng

Giả sử trên tầng i trước chèn:

```text
update[i] ----> successor
```

Ta thực hiện đúng thứ tự:

```text
fresh.forward[i]     = update[i].forward[i]
update[i].forward[i] = fresh
```

Sau chèn:

```text
update[i] ----> fresh ----> successor
```

**Tuyệt đối không đảo hai lệnh nếu lệnh sau vẫn đọc `update[i].forward[i]`.** Nếu thay con trỏ tiền nhiệm trước, rồi mới dùng nó để lấy successor, ta sẽ đọc ra chính `fresh` và có thể tạo **vòng tự trỏ**.

### 5.4. Mô phỏng chèn 55 với H=2

Trước:

```text
L3: HEAD ----------------> 40 ----------------------> NIL
L2: HEAD -> 10 ---------> 40 -----------> 80 -----> NIL
L1: HEAD -> 10 -> 30 ---> 40 -> 60 -----> 80 -----> NIL
L0: HEAD -> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 70 -> 80
```

Các tiền nhiệm cần dùng là `update[1]=40` và `update[0]=50`. Khi chèn:

```text
L1: ... -> 40 -> 55 -> 60 -> 80 -> NIL
L0: ... -> 40 -> 50 -> 55 -> 60 -> 70 -> 80 -> NIL
```

L2/L3 giữ nguyên. Node 55 là **một object mới** với hai ô `forward[0]`, `forward[1]`. `size` tăng đúng 1.

### 5.5. Mô phỏng node mới cao hơn mức hiện tại

Giả sử skip list trước đó chỉ dùng L0 và L1 (`level_count=2`). Chèn khóa 25 bốc H=4. Khi ấy:

```text
update[2] = HEAD
update[3] = HEAD

L3: HEAD -> 25 -> NIL
L2: HEAD -> 25 -> NIL
L1: HEAD -> ... -> 25 -> ... -> NIL
L0: HEAD -> ... -> 25 -> ... -> NIL
```

Sau khi nối đủ các tầng, `level_count=4`. Không cần tạo “bản sao” node 25 ở mỗi tầng.

### 5.6. Chứng minh bất biến sau chèn

Trước khi chèn, mỗi tầng là một dãy tăng chặt. Vì `update[i]` là tiền nhiệm cuối cùng có key < k, và `candidate` không bằng k:

\[
key(update[i]) < k < key(successor)
\]

ở các vị trí có hai node dữ liệu; với HEAD hoặc NIL ta thay bằng các điều kiện biên tương ứng.

Khi thay cạnh `update[i]→successor` thành hai cạnh `update[i]→fresh→successor`, thứ tự tăng vẫn đúng. Nút mới xuất hiện **chính xác** ở những tầng `0..H−1`, nên bất biến tầng cao là dãy con tầng thấp vẫn đúng. Tất cả tầng khác không đổi, `size` tăng một, không mất node cũ.

Đây là chứng minh **tất định**: nó đúng với mọi H hợp lệ, không cần H đã được bốc ngẫu nhiên “đẹp”.

## 6. Xóa một khóa: gỡ ở tất cả tầng và co chiều cao

Xóa là phép đảo ngược liên kết của chèn, nhưng có thêm hai vấn đề:

- Node bị xóa có thể có **nhiều tầng**.
- Nếu nó là node duy nhất trên một số tầng cao, phải **hạ số tầng đang dùng**.

### 6.1. Tìm đúng node

```text
update = FIND_UPDATE(k)
target = update[0].forward[0]

if target == NIL or target.key != k:
    return NOT_FOUND
```

Nếu khóa k không có, **không sửa** bất kỳ liên kết nào và **không giảm** `size`.

### 6.2. Tháo từ từng tầng

Với node `target` cao H, tại mỗi tầng i từ 0 tới H−1:

```text
Trước:
update[i] ---> target ---> successor

Thực hiện:
update[i].forward[i] = target.forward[i]

Sau:
update[i] ---------------> successor
```

Chỉ xóa khỏi tầng 0 **không đủ**: những tầng cao sẽ còn tham chiếu tới node không còn thuộc set; trong C/C++ đây còn có thể trở thành **con trỏ treo** nếu node đã `free`.

### 6.3. Mô phỏng xóa node cao 4 tầng

Giả sử:

```text
L3: HEAD -------------------------> 40 -------------> NIL
L2: HEAD -> 10 ------------------> 40 ----> 80 ----> NIL
L1: HEAD -> 10 -> 30 ------------> 40 -> 60 -> 80 -> NIL
L0: HEAD -> 10 -> 20 -> 30 -----> 40 -> 50 -> 60 -> 70 -> 80
```

Xóa khóa 40:

1. `target` là node có key 40, `H=4`.
2. Dùng `update[0..3]` để sửa **bốn** liên kết.
3. L3 trống; giảm `level_count` từ 4 xuống 3.
4. L2 vẫn có 10 và 80; không giảm tiếp.

Kết quả:

```text
L2: HEAD -> 10 --------------------------> 80 -> NIL
L1: HEAD -> 10 -> 30 -> 60 -------------> 80 -> NIL
L0: HEAD -> 10 -> 20 -> 30 -> 50 -> 60 -> 70 -> 80 -> NIL
```

`size` giảm 1, không phải giảm 4.

### 6.4. Xóa node cuối cùng

Nếu sau xóa không còn node dữ liệu, trạng thái chuẩn:

```text
L0: HEAD -> NIL
level_count = 1
size = 0
```

Có thể giữ một số slot rỗng trong mảng forward của HEAD đã cấp trước, nhưng **không được** để metadata nói tầng cao đang có dữ liệu khi nó rỗng. Với code dùng head cố định `MAX_LEVEL` slot, các slot ngoài phạm vi đang dùng vẫn để `None`.

### 6.5. Chứng minh bất biến sau xóa

Trên mỗi tầng mà target tham gia, thay đoạn `predecessor→target→successor` bằng `predecessor→successor` chỉ **bỏ đúng một khóa** khỏi dãy tăng. Các tầng không chứa target không đổi.

Sau khi tháo target khỏi **tất cả** tầng, quan hệ “tầng cao là dãy con của tầng thấp” vẫn đúng. Thu hẹp `level_count` chỉ bỏ **những tầng rỗng**, không mất node. Vì L0 bỏ đúng một node, `size−=1`.

Trong C/C++, chỉ được giải phóng node sau khi mọi liên kết sở hữu đến node ấy đã được cập nhật và các trình đọc khác không còn dùng nó theo hợp đồng.

## 7. Giải quyết ba lớp lỗi khi thao tác: không thấy, cấp phát lỗi và liên kết sai

Một API cập nhật cấu trúc cần phân biệt các trường hợp không thành công.

| Trạng thái | Ý nghĩa | Thay đổi dữ liệu? |
| --- | --- | --- |
| `INSERTED` | Khóa mới đã được gắn đủ tầng | Có |
| `ALREADY_EXISTS` | Khóa đã có; không tạo node khác | Không |
| `REMOVED` | Đã gỡ khóa khỏi mọi tầng | Có |
| `NOT_FOUND` | Xóa khóa không tồn tại | Không |
| `OUT_OF_MEMORY` | Không chuẩn bị được node/metadata cho phép chèn | Lý tưởng là không |
| `INVARIANT_ERROR` | Cấu trúc đã sai, không thể tiếp tục đáng tin | Không âm thầm làm như thành công |

### 7.1. Xử lý lỗi cấp phát trước khi sửa cấu trúc

Trong C/C++, có thể thất bại khi cấp:

- Node mới và mảng forward.
- Mảng `update`.
- Payload riêng của node.
- Chỉ mục/bộ nhớ bổ sung như span, reference counts.

**Nguyên tắc an toàn:** hoàn thành mọi cấp phát cần thiết **trước khi công bố node mới**. Nếu cấp phát thất bại, giải phóng tài nguyên tạm và trả lỗi; cấu trúc nguồn vẫn đúng bất biến ban đầu.

Trong Python, phép cấp một list và object cũng có thể raise `MemoryError`; do đó chuẩn bị `fresh` trước khi nối. Không nên nói một thao tác nhiều phép gán là **atomic đa luồng** chỉ vì code tuần tự đã khởi tạo xong.

### 7.2. Dùng assert ở đâu?

Trong bản học thuật, `assert update[i].forward[i] is target` giúp bắt lỗi lập trình khi xóa. Nhưng `assert` có thể bị tắt bởi chế độ tối ưu của Python và không thay cho một **API kiểm tra hợp đồng đầu vào**.

Trong production, lỗi bộ nhớ, lỗi tham số và cấu trúc hỏng cần có cách xử lý rõ: exception, trạng thái lỗi hoặc dừng thao tác. Đừng dựa vào `assert` như cơ chế an toàn duy nhất.

### 7.3. Thao tác cùng lúc với iterator

Nếu một iterator đang giữ con trỏ node/đường tầng 0, phép xóa có thể khiến iterator lạc hướng hoặc trỏ tới node đã hủy. Với cập nhật đồng thời, những phép nối đa tầng đòi **đồng bộ, ownership và bảo đảm nhất quán**; bản skip list tuần tự không tự trở thành thread-safe.


## 8. Python: cài đặt đầy đủ tìm, chèn và xóa

Ta xây một **skip list set** chứa khóa `int`, không có khóa trùng. Mã dùng Python 3.10+ và chỉ dùng vòng lặp, nên bản thân thuật toán không bị hạn chế bởi độ sâu đệ quy. Những biến quan trọng:

- `_head`: sentinel có `max_level` ô forward.
- `_level`: số tầng **đang sử dụng**, ít nhất 1.
- `_size`: số node dữ liệu ở tầng 0.
- `_rng`: PRNG riêng cho mỗi skip list, có thể truyền `seed` để tái lập.
- `_p`: xác suất nâng lên tầng kế tiếp.
- `_max_level`: giới hạn số tầng/chiều cao của một node.
- `_version`: tăng sau thao tác **thay đổi tập**; dùng để giải thích iterator invalidation.

### 8.1. Code Python độc lập, không đệ quy

```python
from __future__ import annotations

import random
from dataclasses import dataclass
from collections.abc import Iterator


@dataclass(eq=False)
class SkipNode:
    key: int | None
    forward: list[SkipNode | None]

    @property
    def height(self) -> int:
        return len(self.forward)


class SkipListSet:
    """Set khóa int, tăng dần; các thao tác đơn luồng."""

    def __init__(
        self,
        *,
        p: float = 0.5,
        max_level: int = 24,
        seed: int | None = None,
    ) -> None:
        if not (0.0 < p < 1.0):
            raise ValueError("p phải trong khoảng (0, 1)")
        if max_level < 1:
            raise ValueError("max_level phải >= 1")

        self._p = p
        self._max_level = max_level
        self._rng = random.Random(seed)
        self._head = SkipNode(None, [None] * max_level)
        self._level = 1
        self._size = 0
        self._version = 0

    def __len__(self) -> int:
        return self._size

    @property
    def level_count(self) -> int:
        return self._level

    def _random_height(self) -> int:
        height = 1
        while height < self._max_level and self._rng.random() < self._p:
            height += 1
        return height

    def _find_update(self, key: int) -> list[SkipNode]:
        """Với mọi i đang dùng: update[i] là tiền nhiệm < key."""
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

    def find(self, key: int) -> SkipNode | None:
        """Tìm chỉ đọc, không cấp mảng update."""
        current = self._head

        for level in range(self._level - 1, -1, -1):
            while True:
                nxt = current.forward[level]
                if nxt is None or nxt.key >= key:
                    break
                current = nxt

        candidate = current.forward[0]
        if candidate is not None and candidate.key == key:
            return candidate
        return None

    def contains(self, key: int) -> bool:
        return self.find(key) is not None

    def lower_bound(self, key: int) -> int | None:
        """Khóa nhỏ nhất >= key, hoặc None nếu không có."""
        current = self._head

        for level in range(self._level - 1, -1, -1):
            while True:
                nxt = current.forward[level]
                if nxt is None or nxt.key >= key:
                    break
                current = nxt

        candidate = current.forward[0]
        return None if candidate is None else candidate.key

    def predecessor(self, key: int) -> int | None:
        """Khóa lớn nhất < key, hoặc None."""
        current = self._head

        for level in range(self._level - 1, -1, -1):
            while True:
                nxt = current.forward[level]
                if nxt is None or nxt.key >= key:
                    break
                current = nxt

        return None if current is self._head else current.key

    def insert(self, key: int) -> bool:
        """True khi thêm khóa mới; False khi khóa đã có."""
        update = self._find_update(key)
        candidate = update[0].forward[0]

        if candidate is not None and candidate.key == key:
            return False

        height = self._random_height()
        fresh = SkipNode(key, [None] * height)

        # Những tầng mới trước đó chưa có node dữ liệu.
        if height > self._level:
            for i in range(self._level, height):
                update[i] = self._head
            self._level = height

        # Lưu successor TRƯỚC, rồi mới đổi con trỏ tiền nhiệm.
        for i in range(height):
            fresh.forward[i] = update[i].forward[i]
            update[i].forward[i] = fresh

        self._size += 1
        self._version += 1
        return True

    def discard(self, key: int) -> bool:
        """True khi đã xóa, False khi khóa không tồn tại."""
        update = self._find_update(key)
        target = update[0].forward[0]

        if target is None or target.key != key:
            return False

        for i in range(target.height):
            # Kiểm tra nội bộ: target có mặt ở mọi tầng dưới height.
            assert update[i].forward[i] is target
            update[i].forward[i] = target.forward[i]

        # Giảm tầng cao nhất tới khi nó chứa một node,
        # hoặc chỉ còn tầng 0 khi cấu trúc rỗng.
        while (
            self._level > 1
            and self._head.forward[self._level - 1] is None
        ):
            self._level -= 1

        # Tách các tham chiếu của node cũ, không dùng lại trong list.
        for i in range(target.height):
            target.forward[i] = None

        self._size -= 1
        self._version += 1
        return True

    def iter_keys(self) -> Iterator[int]:
        """Duyệt tầng 0, yêu cầu không sửa cấu trúc khi đang chạy."""
        current = self._head.forward[0]
        expected_version = self._version

        while current is not None:
            if expected_version != self._version:
                raise RuntimeError("Skip list thay đổi khi đang duyệt")

            yield current.key
            current = current.forward[0]

        if expected_version != self._version:
            raise RuntimeError("Skip list thay đổi khi đang duyệt")

    def range_keys(self, low: int, high: int) -> Iterator[int]:
        """Duyệt khóa thuộc [low, high), không tạo mảng kết quả."""
        if low >= high:
            return

        current = self._head

        for level in range(self._level - 1, -1, -1):
            while True:
                nxt = current.forward[level]
                if nxt is None or nxt.key >= low:
                    break
                current = nxt

        current = current.forward[0]
        expected_version = self._version

        while current is not None and current.key < high:
            if expected_version != self._version:
                raise RuntimeError("Skip list thay đổi khi đang duyệt")

            yield current.key
            current = current.forward[0]

        if expected_version != self._version:
            raise RuntimeError("Skip list thay đổi khi đang duyệt")

    def assert_valid(self) -> None:
        """Kiểm tra toàn bộ tầng/identity, dành cho test/debug."""
        assert 1 <= self._level <= self._max_level
        assert self._head.height == self._max_level
        assert all(
            self._head.forward[i] is None
            for i in range(self._level, self._max_level)
        )

        # 1. Duyệt L0, gom node theo identity.
        bottom: set[SkipNode] = set()
        node = self._head.forward[0]
        previous_key: int | None = None
        max_height = 1

        while node is not None:
            assert node not in bottom, "Chu trình ở tầng 0"
            bottom.add(node)

            assert node.key is not None
            assert 1 <= node.height <= self._max_level
            assert previous_key is None or previous_key < node.key

            max_height = max(max_height, node.height)
            previous_key = node.key
            node = node.forward[0]

        assert len(bottom) == self._size
        assert max_height == self._level

        # 2. Với mỗi tầng, phải xuất hiện ĐÚNG các node đủ cao.
        for level in range(self._level):
            expected_nodes = {
                node for node in bottom
                if node.height > level
            }
            observed: set[SkipNode] = set()
            node = self._head.forward[level]
            previous_key = None

            while node is not None:
                assert node not in observed, "Chu trình tầng cao"
                assert node in bottom
                assert node.height > level
                assert previous_key is None or previous_key < node.key

                observed.add(node)
                previous_key = node.key
                node = node.forward[level]

            assert observed == expected_nodes, (
                "Thiếu hoặc thừa node ở một tầng"
            )


def demo() -> None:
    sl = SkipListSet(seed=2026, p=0.5, max_level=24)

    assert len(sl) == 0
    assert sl.level_count == 1
    assert sl.lower_bound(10) is None

    # Người dùng gửi đầu vào tăng dần, KHÔNG phải shuffle.
    for key in range(1, 101):
        assert sl.insert(key)

    assert list(sl.iter_keys()) == list(range(1, 101))
    assert sl.contains(25)
    assert not sl.contains(999)
    assert sl.find(25) is not None
    assert sl.predecessor(25) == 24
    assert sl.lower_bound(25) == 25
    assert sl.lower_bound(25 + 1) == 26
    assert list(sl.range_keys(20, 25)) == [20, 21, 22, 23, 24]

    assert not sl.insert(25)
    assert sl.discard(25)
    assert not sl.contains(25)
    assert not sl.discard(25)
    assert sl.lower_bound(25) == 26

    sl.assert_valid()
    assert len(sl) == 99
    print("size:", len(sl), "levels:", sl.level_count)


if __name__ == "__main__":
    demo()
```

### 8.2. Vai trò khác nhau của `find` và `_find_update`

`find` chỉ cần một con trỏ `current` và các tầng có sẵn, nên không cấp thêm list theo số tầng: **O(1) bộ nhớ phụ trợ**. `_find_update` tạo một list kích thước `max_level` để chèn/xóa có sẵn **mọi tiền nhiệm** cần sửa.

Điều này là tối ưu hóa nhỏ nhưng quan trọng trong hệ thống có số lượt `contains` lớn hơn nhiều so với `insert/discard`. Không cần duy trì `update[]` khi chỉ trả kết quả tìm.

### 8.3. `eq=False` và kiểm tra danh tính node

Trong code, `@dataclass(eq=False)` không tạo so sánh hai node theo nội dung các trường. Điều đó giúp `set[SkipNode]` trong `assert_valid` hoạt động theo **danh tính object**.

Nếu vô tình dùng `@dataclass` mặc định `eq=True`, node chứa list và nhiều liên kết có thể không hash được theo mặc định; nếu tự định nghĩa equality theo payload, hai node khác nhau cùng `key` có thể bị gộp sai khi kiểm tra. Một validator liên kết cần phát hiện **cùng object xuất hiện hai lần** chứ không chỉ so khóa.

### 8.4. Hành vi khi `max_level=1`

`_random_height` luôn trả 1; không còn tầng nhảy. Nhưng `insert`, `find` và `discard` **vẫn đúng về ngữ nghĩa**, vì L0 vẫn sorted và mọi update/next hoạt động như danh sách liên kết đơn.

Thời gian tìm trở thành O(n), thể hiện rõ sự khác biệt giữa **đúng thuật toán** và **hiệu năng do ngẫu nhiên hóa**.

### 8.5. Quy ước lỗi và cấp phát

Mã minh họa dùng `bool` cho việc có thay đổi tập hay không và exception chuẩn của Python cho tham số/cấp phát lỗi. Việc tạo `fresh` trước khi đổi các liên kết giúp giảm nguy cơ cấu trúc dở vì lỗi cấp phát node, nhưng nó **không phải một giao dịch đa luồng** hay bảo đảm tuyệt đối với mọi ngoại lệ từ logic người dùng.

Nếu chuyển sang C/C++, cần phân biệt `ALREADY_EXISTS` với `OUT_OF_MEMORY`, bảo đảm mọi con trỏ tạm được quản lý, và chỉ công bố node mới sau khi đã chuẩn bị đầy đủ mảng forward/payload.

## 9. Ba bản ghi thao tác chi tiết

Phần này theo dõi một chuỗi nhỏ với **chiều cao node đã cho trước** để bạn có thể tính bằng tay, không cần biết PRNG tạo ra số nào.

### 9.1. Tạo cấu trúc bằng các lần chèn

Ban đầu `HEAD`, `size=0`, `level_count=1`. Thực hiện:

| Lần | Thao tác | Chiều cao H |
| ---: | --- | ---: |
| 1 | `insert(30)` | 1 |
| 2 | `insert(10)` | 3 |
| 3 | `insert(50)` | 2 |
| 4 | `insert(40)` | 4 |
| 5 | `insert(20)` | 1 |

Kết quả:

```text
L3: HEAD --------------------------> 40 -> NIL
L2: HEAD -> 10 --------------------> 40 -> NIL
L1: HEAD -> 10 --------------------> 40 -> 50 -> NIL
L0: HEAD -> 10 -> 20 -> 30 -------> 40 -> 50 -> NIL

size = 5
level_count = 4
```

**Kiểm tra:** 10 có mặt ở L0..L2; 40 có mặt ở L0..L3; 50 có mặt ở L0..L1; 20 và 30 chỉ có ở L0. Mọi tầng tăng dần và là dãy con của L0.

### 9.2. Chèn 35 với H=2

Tìm `update[]`:

```text
L3: update[3] = HEAD  (cạnh tới 40, 40 không < 35)
L2: update[2] = 10    (10 < 35, tiếp theo 40 không < 35)
L1: update[1] = 10    (10 < 35, tiếp theo 40 không < 35)
L0: update[0] = 30    (đi qua 20, 30 rồi gặp 40)
```

Kết quả sau khi chèn:

```text
L3: HEAD --------------------------> 40 -> NIL
L2: HEAD -> 10 --------------------> 40 -> NIL
L1: HEAD -> 10 -----> 35 ---------> 40 -> 50 -> NIL
L0: HEAD -> 10 -> 20 -> 30 -> 35 -> 40 -> 50 -> NIL

size = 6
level_count = 4
```

L2/L3 không đổi vì H=2. Đây là một ví dụ cho thấy `update[3]` và `update[2]` **vẫn được xác định**, nhưng không phải tầng nào cũng phải sửa liên kết.

### 9.3. Xóa 10, rồi xóa 40

**Xóa 10** (H=3) bỏ nó khỏi L0, L1, L2, L3 giữ node 40:

```text
L3: HEAD --------------------------> 40 -> NIL
L2: HEAD --------------------------> 40 -> NIL
L1: HEAD -> 35 --------------------> 40 -> 50 -> NIL
L0: HEAD -> 20 -> 30 -> 35 -------> 40 -> 50 -> NIL

size = 5; level_count = 4
```

**Xóa 40** (H=4) bỏ nó khỏi L0..L3. Khi đó tầng L3, L2 đều rỗng; vì 35 và 50 còn ở L1, hạ `level_count` xuống 2:

```text
L1: HEAD -> 35 -> 50 -> NIL
L0: HEAD -> 20 -> 30 -> 35 -> 50 -> NIL

size = 4; level_count = 2
```

Cả hai lần xóa đều giảm `size` một, bất kể độ cao node được tháo. Nếu chỉ giảm số tầng một lần sau xóa 40, metadata sẽ còn sai vì L2 cũng rỗng.

## 10. Điều kiện biên cho ba thao tác

Các trường hợp này nên có test riêng, không được chỉ dựa vào ví dụ dữ liệu “đẹp”:

| Trường hợp | Tìm | Chèn | Xóa |
| --- | --- | --- | --- |
| Danh sách rỗng | Không thấy | Node mới nối sau HEAD | Không thấy, không đổi |
| Chỉ một node | So sánh khóa duy nhất | Chèn trước/sau tùy khóa | Trở về rỗng |
| Khóa nhỏ hơn min | Ứng viên là min | HEAD là tiền nhiệm trên mọi tầng tham gia | Không thấy |
| Khóa lớn hơn max | Ứng viên NULL | Chèn ở cuối các tầng tham gia | Không thấy |
| Khóa đã tồn tại | Trả đúng node | Không tạo node trùng | Gỡ node tại các tầng có mặt |
| Node mới cao hơn toàn cấu trúc | Không liên quan | `update[i]=HEAD` cho tầng mới | Không liên quan |
| Xóa node duy nhất trên tầng cao nhất | Không liên quan | Không liên quan | Thu hẹp nhiều tầng nếu cần |
| `max_level=1` | Duyệt L0 tuyến tính | Vẫn nối được | Vẫn gỡ được |
| Nhiều node cùng giá trị nếu API multiset | Phải có chính sách riêng | Không dùng nguyên mã set | Không dùng nguyên mã set |
| Một iterator đang chạy | Tùy hợp đồng | Có thể vô hiệu iterator | Có thể vô hiệu iterator |
| Hai thread không đồng bộ | Không an toàn | Không an toàn | Không an toàn |

### 10.1. Khóa và kiểu so sánh

Code Python giả định **`key` là int**. Nếu dùng khóa khác, cần một **thứ tự toàn phần nhất quán**, để điều kiện `<` và `==` không mâu thuẫn.

Ví dụ, với float có `NaN`, các phép so sánh `<`/`==` có thể không tạo quan hệ thứ tự đầy đủ. Không nên chuyển code set nguyên này sang khóa tùy ý mà không có comparator thích hợp. Nếu dùng key mutable rồi thay key sau chèn, cấu trúc sorted có thể hỏng dù con trỏ không đổi.

### 10.2. Thao tác không thành công không thay `size`

Đây là bất biến dễ kiểm tra:

```text
insert(k) khi k đã có:       size' = size
discard(k) khi k không có:   size' = size
insert(k) khi k mới:         size' = size + 1
discard(k) khi k có:         size' = size - 1
```

Nếu `size` thay đổi nhưng tầng 0 không phản ánh đúng số node, thuật toán đang có lỗi nối/gỡ hoặc cập nhật metadata.


## 11. Chi phí thời gian và bộ nhớ: kỳ vọng khác trường hợp xấu nhất

Gọi:

- `n`: số node dữ liệu trong skip list.
- `H`: số tầng **đang sử dụng** tại thời điểm thao tác, ít nhất 1.
- `L`: `max_level` được cấu hình, với `H≤L`.
- `p`: xác suất một node được nâng thêm một tầng, `0<p<1`.
- `k`: số phần tử thực tế được xuất bởi một truy vấn khoảng.

### 11.1. Phân phối chiều cao các node

Mỗi node mới ban đầu có `height=1`. Khi chưa xét trần L, muốn cao ít nhất t tầng cần t−1 lần nâng thành công liên tiếp:

\[
\Pr(\mathrm{height}\ge t)=p^{t-1}.
\]

Số tầng node có kỳ vọng:

\[
\mathbb E[\mathrm{height}]
  =\sum_{t=1}^{\infty}p^{t-1}
  =\frac{1}{1-p}.
\]

Với p=1/2, node trung bình có **2 ô forward**; điều này lý giải tổng số ô forward cần lưu chỉ **O(n) kỳ vọng**, không phải O(n log n), khi mỗi node chỉ cấp đúng số ô bằng chiều cao của nó.

Với trần cố định L:

\[
\mathbb E[\mathrm{height}]
  =\sum_{t=1}^{L}p^{t-1}
  =\frac{1-p^L}{1-p}.
\]

Vì vậy, dung lượng forward mỗi node ≤L, nhưng phân phối tầng cao nhất bị cắt tại L.

### 11.2. Vì sao tìm kiếm kỳ vọng O(log n)?

Ở tầng thấp, nhiều node nằm gần nhau; ở tầng cao, xác suất một node xuất hiện giảm theo `p^i`, nên ta có thể đi qua những đoạn dài trong ít bước.

Một phân tích chuẩn xem đường tìm ngược và dùng các lần nâng cấp độc lập:

- Số bước ngang kỳ vọng trên mỗi mức phụ thuộc vào p, ở bậc O(1/p) khi p cố định.
- Số tầng hữu ích tăng theo `\log_{1/p} n`.
- Tổng số bước tìm/chèn/xóa **O(log n) kỳ vọng** trong mô hình xác suất thích hợp, khi số tầng được hỗ trợ đủ lớn so với n.

Đây là **kỳ vọng trên lựa chọn mức ngẫu nhiên của cấu trúc**, với tập khóa/chuỗi thao tác phù hợp giả định độc lập; **không cần xáo trộn thứ tự khóa do người dùng gửi**.

### 11.3. Không có chặn O(log n) cho mọi lần chạy

Một lần bốc chiều cao bất lợi có thể khiến tất cả node chỉ có H=1:

```text
L0: HEAD -> k1 -> k2 -> ... -> kn -> NIL
```

Khi đó tìm k_n hoặc khóa lớn hơn k_n cần Θ(n) bước. Thuật toán **vẫn đúng**, nhưng không đạt logarit ở lần chạy ấy.

Với code giới hạn L, chi phí một lượt tìm/bảo trì theo trạng thái thực tế là **O(n+L)**: con trỏ `current` luôn tiến sang phải theo thứ tự khóa nên tổng bước ngang không quá n trên một lượt tìm, cùng tối đa L lần xuống tầng và O(L) khởi tạo mảng `update[]` nếu có.

Nếu cho số tầng ngẫu nhiên **không giới hạn**, phải nêu chi phí theo H; ngay một cấu trúc ít node mà được bốc rất nhiều tầng cũng cần Ω(H) bước để đi xuống hết. Không thể nói worst-case luôn chỉ O(n) khi bỏ qua H.

### 11.4. Bảng chi phí của cài đặt Python

| Thao tác | Kỳ vọng với chiều cao được hỗ trợ đủ & p cố định | Worst-case theo n,L | Bộ nhớ phụ ngoài cấu trúc |
| --- | --- | --- | --- |
| `find/contains` | O(log n) khi L=O(log n) và cấu hình đủ rộng | O(n+L) | O(1) |
| `lower_bound/predecessor` | O(log n) theo cùng giả định | O(n+L) | O(1) |
| `_find_update` | O(log n+L) | O(n+L) | O(L) |
| `insert` | O(log n+L) | O(n+L) | O(L) mảng update; H ô node mới |
| `discard` | O(log n+L) | O(n+L) | O(L) |
| `iter_keys` sinh đủ n khóa | O(n) | O(n) | O(1) trạng thái duyệt |
| `range_keys(low,high)` sinh k khóa | O(log n+k) theo cấu hình phù hợp | O(n+L+k) | O(1) ngoài iterator |
| `assert_valid` | Dùng để debug, không gọi mỗi update | O(nL+S) với S là tổng forward slots | O(n+L) metadata tạm |

**Quan trọng:** `_find_update` trong mã cấp list có đúng **L** mục, nên dù trường hợp tìm đường ngắn chỉ O(log n), vẫn phải tính **O(L)** để tạo list. Bảng tách rõ phần đó thay vì gọi mọi thao tác đều O(log n) một cách vô điều kiện khi L là tham số biến thiên.

Trong bảng, O(log n) đối với `find`/`contains` dùng quy mô mà L **đủ lớn** để không cắt mất các tầng logarit hữu ích, đồng thời L không phình to hơn bậc logarit một cách vô lý. Với `L=24` cố định, đó là cấu hình cho một **phạm vi n hữu hạn dự kiến**; không phải tuyên bố O(log n) tiệm cận khi n tăng vô hạn.

### 11.5. Vì sao L cố định quá thấp làm mất kỳ vọng logarit về lâu dài?

Khi L cố định, xác suất một node có mặt ở tầng cao nhất L−1 là `p^{L-1}`, một **hằng số**. Với n node, số node tầng cao nhất kỳ vọng bằng `n p^{L-1}`. Không có tầng cao hơn để nhảy qua tất cả chúng.

Khi n tăng đủ lớn, số bước ngang trên tầng cao nhất có thể tăng tuyến tính theo n; phân tích “O(log n) kỳ vọng” theo n không còn áp dụng nguyên xi. Do đó:

- Đặt L dựa trên **n tối đa** dự kiến.
- Hoặc hỗ trợ tăng giới hạn khi n tăng, kèm chính sách phân phối/cập nhật.
- Hoặc dùng cấu trúc có chặn worst-case nếu workload không chấp nhận rủi ro.

Đừng nhầm **mức trần cấp phát của mỗi node** với **bảo đảm độ dài đường đi luôn ngắn**.

### 11.6. Kích thước thực tế và cache

Skip list cần các con trỏ forward, metadata chiều cao, node có thể nằm rải rác trong heap. Với p=1/2, mỗi node có trung bình 2 ô forward, nhưng còn chi phí:

- Object header, khóa/payload.
- Alignment/padding và overhead allocator.
- HEAD và các ô forward tối đa L.
- Chi phí bộ nhớ tạm cho `update[]`.
- Cache miss khi tìm qua các node rời rạc.

Vì thế, `O(n)` bộ nhớ kỳ vọng không nói rõ skip list **dùng ít byte hơn** mảng sorted hoặc cây theo khối. Khi lựa chọn cấu trúc, phải đo chi phí thực tế trên workload phù hợp.

## 12. C: phiên bản nhỏ minh họa đúng con trỏ khi tìm, chèn và xóa

Phần C dưới đây chủ động **nhận chiều cao khi chèn** để tách rõ hai vấn đề: thuật toán cập nhật **liên kết** và cách sinh **chiều cao ngẫu nhiên**. Trong ứng dụng thực, `height` phải được bốc từ RNG với phân phối/giới hạn phù hợp; trong test, truyền chiều cao xác định giúp tính lại các tầng bằng tay.

Để mã đơn giản và độc lập, mọi node giữ mảng `next[MAX_LEVEL]` cố định. Kiểu này dùng **O(nL)** ô con trỏ nếu L là tham số tăng, khác với triển khai node cấp đúng H ô và có **O(n)** tổng forward slots kỳ vọng khi p cố định.

### 12.1. Code C tự chứa

```c
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

enum { MAX_LEVEL = 12 };

typedef struct Node {
    int key;
    int height;
    struct Node *next[MAX_LEVEL];
} Node;

typedef struct SkipList {
    Node head;      /* Sentinel nằm trực tiếp trong struct. */
    int levels;     /* Số tầng đang dùng, ít nhất 1. */
    size_t size;
} SkipList;

typedef enum InsertResult {
    INSERTED,
    ALREADY_EXISTS,
    OUT_OF_MEMORY,
    BAD_HEIGHT
} InsertResult;

static void sl_init(SkipList *list) {
    *list = (SkipList){0}; /* Mọi con trỏ head.next đều NULL. */
    list->levels = 1;
    list->head.height = MAX_LEVEL;
}

/* Ghi update ở các tầng đang dùng. */
static void sl_find_update(
    SkipList *list,
    int key,
    Node *update[MAX_LEVEL]
) {
    Node *current = &list->head;

    for (int i = 0; i < MAX_LEVEL; ++i) {
        update[i] = &list->head;
    }

    for (int i = list->levels - 1; i >= 0; --i) {
        while (current->next[i] != NULL &&
               current->next[i]->key < key) {
            current = current->next[i];
        }
        update[i] = current;
    }
}

static bool sl_contains(const SkipList *list, int key) {
    const Node *current = &list->head;

    for (int i = list->levels - 1; i >= 0; --i) {
        while (current->next[i] != NULL &&
               current->next[i]->key < key) {
            current = current->next[i];
        }
    }

    const Node *candidate = current->next[0];
    return candidate != NULL && candidate->key == key;
}

static InsertResult sl_insert(
    SkipList *list,
    int key,
    int height
) {
    if (height < 1 || height > MAX_LEVEL) {
        return BAD_HEIGHT;
    }

    Node *update[MAX_LEVEL];
    sl_find_update(list, key, update);
    Node *candidate = update[0]->next[0];

    if (candidate != NULL && candidate->key == key) {
        return ALREADY_EXISTS;
    }

    /* calloc khởi tạo mọi liên kết NULL trước khi công bố node. */
    Node *fresh = calloc(1, sizeof *fresh);
    if (fresh == NULL) {
        return OUT_OF_MEMORY;
    }

    fresh->key = key;
    fresh->height = height;

    if (height > list->levels) {
        for (int i = list->levels; i < height; ++i) {
            update[i] = &list->head;
        }
        list->levels = height;
    }

    for (int i = 0; i < height; ++i) {
        fresh->next[i] = update[i]->next[i];
        update[i]->next[i] = fresh;
    }

    ++list->size;
    return INSERTED;
}

static bool sl_discard(SkipList *list, int key) {
    Node *update[MAX_LEVEL];
    sl_find_update(list, key, update);

    Node *target = update[0]->next[0];
    if (target == NULL || target->key != key) {
        return false;
    }

    for (int i = 0; i < target->height; ++i) {
        assert(update[i]->next[i] == target);
        update[i]->next[i] = target->next[i];
    }

    while (list->levels > 1 &&
           list->head.next[list->levels - 1] == NULL) {
        --list->levels;
    }

    free(target);   /* Mỗi node dữ liệu free đúng một lần. */
    --list->size;
    return true;
}

/* Chỉ hủy qua tầng 0, vì mỗi node có mặt đúng một lần tại L0. */
static void sl_destroy(SkipList *list) {
    Node *current = list->head.next[0];

    while (current != NULL) {
        Node *next = current->next[0]; /* Đọc TRƯỚC free. */
        free(current);
        current = next;
    }

    /* Khôi phục sentinel và metadata về trạng thái rỗng. */
    sl_init(list);
}

static void sl_print(const SkipList *list) {
    printf("size=%zu, levels=%d\n", list->size, list->levels);

    for (int i = list->levels - 1; i >= 0; --i) {
        printf("L%d: HEAD", i);

        const Node *current = list->head.next[i];
        while (current != NULL) {
            printf(" -> %d", current->key);
            current = current->next[i];
        }
        puts(" -> NIL");
    }
}

/* Kiểm thử luôn thực thi cả biểu thức, kể cả khi bật NDEBUG. */
static void check(bool ok) {
    if (!ok) {
        fputs("Check failed\n", stderr);
        exit(EXIT_FAILURE);
    }
}

int main(void) {
    SkipList list;
    sl_init(&list);

    check(sl_insert(&list, 30, 1) == INSERTED);
    check(sl_insert(&list, 10, 3) == INSERTED);
    check(sl_insert(&list, 50, 2) == INSERTED);
    check(sl_insert(&list, 40, 4) == INSERTED);
    check(sl_insert(&list, 20, 1) == INSERTED);

    check(list.size == 5);
    check(list.levels == 4);
    check(sl_contains(&list, 40));
    check(!sl_contains(&list, 35));
    check(sl_insert(&list, 40, 2) == ALREADY_EXISTS);

    check(sl_insert(&list, 35, 2) == INSERTED);
    check(sl_discard(&list, 10));
    check(sl_discard(&list, 40));
    check(!sl_discard(&list, 40));
    check(list.size == 4);
    check(list.levels == 2);

    sl_print(&list); /* L0: 20, 30, 35, 50. */

    sl_destroy(&list);
    check(list.size == 0);
    check(list.levels == 1);
    return EXIT_SUCCESS;
}
```

### 12.2. Thao tác C sử dụng quyền sở hữu như thế nào?

- `list` sở hữu mọi Node dữ liệu reachable từ `head.next[0]`.
- Mỗi node là **một lần `calloc`**, dù có mặt trên nhiều tầng.
- `sl_discard` gỡ mọi tầng rồi **`free(target)` đúng một lần**.
- `sl_destroy` đi **chỉ tầng 0** để `free` từng node một lần; không duyệt từng tầng để free node lặp.
- Chỉ mục `next[i]` của node cần được giữ hợp lệ cho tới khi node đã được tháo; không đọc trường của node sau `free`.
- Không dùng con trỏ node sau khi nó đã bị xóa, trừ khi API thiết kế một cơ chế reclamation riêng.

**Hợp đồng:** đây là skip list **đơn luồng, sở hữu riêng**, không có external alias đang dùng node khi xóa/hủy, không có chu trình do dữ liệu bị làm hỏng, và không có payload cần cấp phát lồng nhau. Nếu các giả định sai, destructor tầng 0 không phải bộ sửa graph tự động.

### 12.3. Những khác biệt với cài đặt tổng quát

- Bản C truyền `height` vào `sl_insert`, **không phải một randomized skip list tự bốc**. Ghép thêm hàm `random_height(p,L)` đúng nguồn RNG/seed mới thành cấu trúc randomized hoàn chỉnh.
- Mỗi Node giữ **MAX_LEVEL con trỏ**, nên dùng nhiều bộ nhớ hơn phiên bản cấp đúng H ô. Đổi lại, tránh flexible array member và việc cấp một vùng biến độ dài cho ví dụ đầu tiên.
- Code dùng `assert` để làm lộ lỗi lập trình, không phải một chiến lược xử lý dữ liệu hỏng do người dùng.
- Trong code production, nên có kiểm tra tham số `list`, quản lý trạng thái khởi tạo/hủy và kiểm thử lỗi cấp phát. Không dùng `sl_destroy` trên một `SkipList` chưa được `sl_init`.


## 13. Kiểm thử với chiều cao được ấn định: không phụ thuộc seed

Seed giúp lặp lại chuỗi random, nhưng để kiểm tra **chính xác từng liên kết**, ta có thể dùng một nguồn chiều cao cố định trong **môi trường test**. Lớp kế thừa bên dưới chỉ thay hàm `_random_height`; các hàm tìm/chèn/xóa vẫn y nguyên.

```python
class ScriptedSkipList(SkipListSet):
    def __init__(self, heights: list[int]):
        super().__init__(seed=0, max_level=8)
        self._heights = iter(heights)

    def _random_height(self) -> int:
        height = next(self._heights)
        assert 1 <= height <= self._max_level
        return height


sl = ScriptedSkipList([1, 3, 2, 4, 1, 2])

# 30(H1), 10(H3), 50(H2), 40(H4), 20(H1).
for key in (30, 10, 50, 40, 20):
    assert sl.insert(key)

assert sl.level_count == 4
assert list(sl.iter_keys()) == [10, 20, 30, 40, 50]
sl.assert_valid()

# 35 nhận H2.
assert sl.insert(35)
sl.assert_valid()
assert list(sl.iter_keys()) == [10, 20, 30, 35, 40, 50]

assert sl.discard(10)
assert sl.level_count == 4
assert sl.discard(40)
assert sl.level_count == 2
assert list(sl.iter_keys()) == [20, 30, 35, 50]
sl.assert_valid()
```

Bài test xác nhận đúng trace ở Mục 9: sau khi bỏ node cao nhất và node cao thứ hai, số tầng giảm từ 4 xuống 2.

### 13.1. Chèn trùng không tiêu thụ random height

```python
sl = ScriptedSkipList([3, 1])

assert sl.insert(20)      # Dùng H3.
assert not sl.insert(20)  # Không bốc height mới.
assert sl.insert(10)      # Dùng H1, không phải hết plan.

assert sl.level_count == 3
assert len(sl) == 2
sl.assert_valid()
```

Nếu một thay đổi khiến `insert` bốc mức **trước khi** kiểm tra duplicate, test này sẽ lộ ra sự khác biệt. Việc không tiêu thụ PRNG khi thao tác không thành công là **chính sách của code bài**, không phải quy tắc duy nhất của mọi thư viện skip list.

### 13.2. Xóa hết rồi thêm lại

```python
sl = SkipListSet(seed=17, max_level=12)

for key in (50, 10, 30, 20, 40):
    assert sl.insert(key)

for key in (10, 20, 30, 40, 50):
    assert sl.discard(key)

assert len(sl) == 0
assert sl.level_count == 1
assert list(sl.iter_keys()) == []
sl.assert_valid()

assert sl.insert(99)
assert list(sl.iter_keys()) == [99]
sl.assert_valid()
```

Ở trạng thái rỗng, sentinel HEAD vẫn tồn tại và được tái sử dụng. Không có lý do tạo lại object skip list chỉ vì xóa phần tử cuối.

## 14. Kiểm thử đối chiếu với `set` và các phép tìm biên

Một cấu trúc randomized có hai lớp tính chất:

- **Đúng kết quả** với mọi chiều cao hợp lệ, bất kể seed nào.
- **Chi phí kỳ vọng** theo nguồn random và các giả định xác suất đã nêu.

Ta kiểm tra lớp thứ nhất bằng mô hình tham chiếu `set` của Python.

### 14.1. Chuỗi thao tác có seed tái lập

```python
import random


def test_against_reference(seed: int) -> None:
    rng = random.Random(seed)  # Chọn THAO TÁC thử.
    sl = SkipListSet(seed=seed, max_level=16)  # Bốc MỨC node.
    reference: set[int] = set()

    for _ in range(250):
        key = rng.randrange(-50, 51)
        operation = rng.randrange(3)

        if operation == 0:
            existed = key in reference
            assert sl.insert(key) == (not existed)
            reference.add(key)

        elif operation == 1:
            existed = key in reference
            assert sl.discard(key) == existed
            reference.discard(key)

        else:
            assert sl.contains(key) == (key in reference)

        sl.assert_valid()
        assert len(sl) == len(reference)
        assert list(sl.iter_keys()) == sorted(reference)

    sorted_keys = sorted(reference)

    for key in (-100, -51, 0, 33, 51, 100):
        ge = [x for x in sorted_keys if x >= key]
        lt = [x for x in sorted_keys if x < key]

        assert sl.lower_bound(key) == (ge[0] if ge else None)
        assert sl.predecessor(key) == (lt[-1] if lt else None)


for seed in range(10):
    test_against_reference(seed)
```

Hai RNG độc lập làm rõ rằng **lựa chọn thao tác kiểm thử** không sử dụng cùng state với **chiều cao node**. Bộ test kiểm tra nội dung, số lượng, thứ tự và bất biến sau mỗi bước, nhưng **không thay thế** chứng minh thời gian O(log n) kỳ vọng.

### 14.2. Thử dữ liệu có thứ tự tăng, giảm và xen kẽ

```python
def test_orderings() -> None:
    base = list(range(100))

    orders = [
        base,
        list(reversed(base)),
        base[::2] + base[1::2],
    ]

    for seed, order in enumerate(orders):
        sl = SkipListSet(seed=seed, max_level=16)

        for key in order:
            assert sl.insert(key)

        sl.assert_valid()
        assert list(sl.iter_keys()) == base

        for key in reversed(order):
            assert sl.discard(key)

        sl.assert_valid()
        assert len(sl) == 0
        assert sl.level_count == 1


test_orderings()
```

Các thứ tự này làm lộ lỗi ở tiền nhiệm đầu/cuối và phép nối khi node mới đứng trước toàn bộ node cũ. Skip list **không cần shuffle input** để làm đúng hoặc để phân tích expected dưới mô hình mức random thích hợp.

### 14.3. Trường hợp biên của `lower_bound` và tiền nhiệm

```python
sl = SkipListSet(seed=2, max_level=8)

for key in (-10, 0, 10):
    assert sl.insert(key)

# (key, contains?, lower_bound, predecessor)
cases = [
    (-100, False, -10, None),
    (-10, True, -10, None),
    (-5, False, 0, -10),
    (0, True, 0, -10),
    (9, False, 10, 0),
    (10, True, 10, 0),
    (11, False, None, 10),
]

for key, found, lower, previous in cases:
    assert sl.contains(key) == found
    assert sl.lower_bound(key) == lower
    assert sl.predecessor(key) == previous

sl.assert_valid()
```

Đặc biệt, `predecessor(10)=0` chứ không phải 10, vì tiền nhiệm là khóa **nhỏ hơn chặt**.

### 14.4. Cố ý tạo lỗi để thử validator

Trong test cô lập, có thể làm hỏng liên kết của một node cao:

```python
sl = ScriptedSkipList([3, 1])
assert sl.insert(10)  # H3: phải có ở L0, L1 và L2.
assert sl.insert(20)  # H1.
sl.assert_valid()

sl._head.forward[1] = None  # Cố tình loại node 10 khỏi L1.

detected = False
try:
    sl.assert_valid()
except AssertionError:
    detected = True

assert detected, "Validator phải phát hiện lỗi tầng L1"
```

Bản code chỉ dùng cho **minh họa phá bất biến**; việc sửa trực tiếp `_head.forward` không phải API bình thường. Cờ `detected` bảo đảm ta chỉ chấp nhận ngoại lệ do **validator phát ra**, không bắt nhầm một ngoại lệ mà chính bài test cố tình `raise` sau đó. Có thể thay bằng `pytest.raises` nếu dùng framework kiểm thử.

Tương tự, `assert` trong Python có thể bị vô hiệu khi chạy `python -O`; nếu validator là một yêu cầu sản phẩm, hãy dùng kiểm tra ném exception tường minh.

## 15. Tìm khoảng khóa sau khi biết `lower_bound`

Với skip list, một truy vấn khoảng `[low, high)` có thể xử lý bằng:

1. Tìm node đầu tiên có key ≥ low qua các tầng.
2. Đi theo `forward[0]`.
3. Xuất các khóa nhỏ hơn high và dừng khi gặp node key ≥ high hoặc hết danh sách.

```text
Tập: {10, 20, 30, 40, 50, 60, 70}
range_keys(25, 60):

lower_bound(25) = 30
30 -> 40 -> 50 -> (gặp 60 thì dừng)

Kết quả = [30, 40, 50]
```

Với k kết quả, chi phí **O(log n+k) kỳ vọng** khi phân phối tầng phù hợp; việc xuất k khóa luôn cần ít nhất Ω(k) bước, nên không thể tuyên bố toàn bộ range query chỉ O(log n) khi k lớn.

### 15.1. Tìm theo khóa khác tìm theo thứ hạng

`lower_bound(k)` hỏi node có khóa **đầu tiên ≥ k**. Nó không trực tiếp trả **phần tử thứ r** theo vị trí.

Nếu muốn `rank(k)` (đếm khóa <k) và `select(r)` (phần tử thứ r), bản skip list chỉ có forward có thể phải đếm theo L0 O(n). Một biến thể **indexable skip list** lưu thêm **span/width** (số nút tầng đáy mà một liên kết nhảy qua), rồi cập nhật span khi chèn/xóa để đạt O(log n) kỳ vọng.

**Mỗi lần chèn hoặc xóa có thể thay span ngay cả ở tầng không trực tiếp chứa node bị đổi.** Vì thế không được lấy code skip list set cơ bản, thêm trường span mà quên bảo trì các khoảng cách.

## 16. Sửa lỗi thao tác theo dấu vết `update[]`

| Sai sót | Dấu hiệu | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| `<= k` thay vì `< k` khi tìm predecessor | Có thể vượt khóa trùng | Dừng trước ứng viên ≥k |
| Mỗi tầng lại bắt đầu từ HEAD | Bỏ phí các đường nhảy | Giữ `current` khi xuống |
| Nhầm `height=H` với chỉ số `forward[H]` | Truy cập ngoài mảng | Chỉ số hợp lệ 0..H−1 |
| Tầng mới không ghi `update[i]=HEAD` | Đọc ô chưa chuẩn bị | Điền HEAD khi H cao hơn mức cũ |
| Gán predecessor tới fresh trước khi lưu successor | Fresh tự trỏ hoặc mất node cũ | Đọc successor trước |
| Chỉ nối fresh tại L0 | Tầng cao thiếu node đủ H | Nối tất cả tầng 0..H−1 |
| Chèn trùng vẫn cấp node | Set chứa duplicate | Kiểm tra candidate trước khi bốc H |
| Xóa chỉ tại L0 | Tầng cao giữ node đã xóa | Tháo toàn bộ chiều cao target |
| Hủy node rồi mới đọc `forward` | Use-after-free | Lưu successor trước khi `free` |
| Giảm `size` theo số tầng của node | Kích thước bị sai | Mỗi node tương ứng một khóa |
| Chỉ giảm mức một lần khi nhiều tầng trống | `level_count` sai | Dùng `while` hạ tới tầng còn node |
| Duyệt rồi thay đổi cấu trúc không có hợp đồng | Có thể bỏ/lặp khóa | Version, khóa hoặc snapshot |
| Coi O(log n) kỳ vọng là worst-case | Báo sai deadline | Xét trạng thái lệch và giới hạn tầng |
| Quên O(L) cho mảng `update` cố định | Thiếu chi phí bộ nhớ/thời gian | Tính L hoặc cấp theo H hiện có |

### 16.1. Quy trình debug khi một khóa không tìm thấy sau chèn

1. In **tất cả tầng từ cao xuống thấp**.
2. Kiểm tra L0 có còn sorted và có khóa cần tìm không.
3. In `update[i]` trước khi nối node.
4. In H của node vừa chèn và tất cả successor trước phép gán.
5. Kiểm tra từng tầng `i<H` có **đúng một** đường tới node.
6. Kiểm tra tầng `i≥H` không bất ngờ chứa node ấy.
7. Chạy validator so `size` với số node thật ở L0.
8. Dùng test chiều cao cố định để tách lỗi liên kết khỏi phân phối RNG.

### 16.2. Quy trình debug khi xóa xong vẫn thấy khóa

1. Xác định `target` theo **identity**, không chỉ theo giá trị.
2. Kiểm tra `target.height` và các cạnh tới target ở từng tầng.
3. Kiểm tra `update[i].forward[i] is target` trước khi sửa.
4. Xác nhận mọi `i<target.height` đã nối thẳng tới successor cũ.
5. Xác nhận `size` giảm **một** và các tầng cao trống được bỏ khỏi metadata.
6. Với C/C++, kiểm tra không còn người đọc giữ con trỏ treo và không hủy node hai lần.

Một lỗi trong `update[]` có thể biểu hiện như lỗi xóa hoặc lỗi tìm sau chèn. Vì vậy việc quan sát **tiền nhiệm/successor trước và sau từng cấp** thường hiệu quả hơn việc chỉ in kết quả cuối.


## 17. Cập nhật khi có nhiều luồng: không được giả định nối đa tầng là atomic

Bản `SkipListSet` và bản C ở trên là **tuần tự**. Chúng giả định không có tác nhân khác đọc/sửa các liên kết trong khi một thao tác đang cập nhật.

### 17.1. Một node được nối nhiều tầng qua nhiều phép gán

Giả sử chèn node cao H=3:

```text
Tại thời điểm t1: nối node vào L0.
Tại thời điểm t2: nối node vào L1.
Tại thời điểm t3: nối node vào L2.
```

Một luồng đọc đúng lúc giữa t1 và t3 có thể thấy trạng thái “node đã ở tầng đáy nhưng chưa có đầy đủ các tầng dự định”. Trong môi trường C/C++ không có đồng bộ, việc đọc và ghi con trỏ không atomic theo hợp đồng có thể gây **data race**, không chỉ là đọc snapshot chưa hoàn chỉnh.

### 17.2. Cách đơn giản: khóa bảo vệ toàn bộ thao tác

Một **mutex** có thể bảo vệ cả thao tác tìm/chèn/xóa/duyệt nếu mọi bên truy cập tuân thủ cùng quy tắc:

```text
LOCK(skip_list)
    search / insert / discard trên một trạng thái nhất quán
UNLOCK(skip_list)
```

Nếu một iterator được trả ra để bên gọi dùng **sau khi mở khóa**, nó vẫn cần quy tắc vòng đời/snapshot/phiên bản riêng. Khóa trong một lệnh `insert` không bảo vệ an toàn cho một con trỏ node mà bên gọi giữ qua các lệnh sau.

### 17.3. Lock-free skip list là một thuật toán chuyên biệt

Các thiết kế concurrent skip list thực sự có thể dùng:

- `CAS` (*compare-and-swap*) thay đổi con trỏ.
- Đánh dấu xóa **logic** trước khi tháo node vật lý.
- Điểm **linearization** rõ cho insert/search/delete.
- Trình đọc giúp hoàn tất liên kết còn dang dở.
- `Hazard pointers`, `epoch-based reclamation` hoặc kỹ thuật tương đương để không `free` node mà luồng khác còn dùng.
- Giải quyết `ABA` và thứ tự bộ nhớ của CPU/compiler.

Không thể thay các phép gán `forward[i] = fresh` trong bản tuần tự bằng CAS đơn lẻ rồi tuyên bố cấu trúc lock-free đúng. Đó là một bài toán đồng bộ và quản lý vòng đời riêng.

### 17.4. Phiên bản và iterator trong Python

Trong ví dụ, `iter_keys` lưu `expected_version` khi **bắt đầu chạy generator** và kiểm tra sự thay đổi ở mỗi lần lấy. Nó giúp phát hiện cập nhật thông qua chính API lớp trong bối cảnh tuần tự.

Nhưng:

- Generator Python thường chỉ chạy phần thân khi lần đầu được lấy bằng `next`, không phải lúc ta vừa gọi hàm tạo generator.
- Chỉ sửa trực tiếp node nội bộ không tăng `_version` nên có thể không được phát hiện.
- Kiểm tra version không đồng bộ các luồng; không biến một iterator thành snapshot bất biến.
- Nếu node cũ còn được một tham chiếu Python giữ, object có thể vẫn sống dù đã bị gỡ, nhưng không còn thuộc skip list hiện tại.

Vì vậy **hợp đồng iterator** phải nêu rõ trạng thái nào được phép quan sát và cách xử lý nếu cấu trúc đổi.

## 18. Chọn skip list hay cấu trúc khác cho bài toán cụ thể?

Skip list là một lựa chọn rất đáng cân nhắc khi cần tập/map **có thứ tự** và chèn/xóa trực tuyến. Nhưng hiệu năng kỳ vọng không giải quyết mọi mục tiêu.

| Cấu trúc | Tìm khóa | Chèn/xóa | Đặc điểm |
| --- | --- | --- | --- |
| Danh sách liên kết sorted | O(n) | O(n) để tìm chỗ, O(1) để nối/gỡ khi có tiền nhiệm | Ít metadata, dễ triển khai |
| Mảng sorted | O(log n) tìm nhị phân | O(n) do dịch phần tử | Locality tốt, rất hợp đọc nhiều |
| BST thường không cân bằng | O(h), worst O(n) | O(h), worst O(n) | Nhạy với thứ tự chèn |
| AVL hoặc red-black tree | O(log n) worst-case | O(log n) worst-case | Bảo đảm cân bằng tất định |
| Treap có priority random | O(log n) kỳ vọng | O(log n) kỳ vọng | BST theo key + heap theo priority |
| Skip list có mức random phù hợp | O(log n) kỳ vọng | O(log n) kỳ vọng | Nhiều tầng link, range dễ |
| Hash table | O(1) kỳ vọng cho exact-key theo giả định hash | O(1) kỳ vọng cơ bản | Không tự duy trì thứ tự/range |
| B-tree/B+ tree | O(log n) theo số node/khối | O(log n) theo số node/khối | Thuận lợi cho truy cập theo block |

### 18.1. Ba câu hỏi khi ra quyết định

**1. Cần tìm theo khóa chính xác hay theo khoảng?** Nếu chỉ hỏi `contains(k)` và không cần thứ tự, hash table có thể hấp dẫn hơn. Nếu thường hỏi `lower_bound` hoặc `[a,b)`, skip list có ưu thế duy trì dãy sorted.

**2. Có chấp nhận xác suất không?** Skip list có expected O(log n) khi cấu hình/random đúng, nhưng vẫn có trường hợp xấu tuyến tính. Nếu mỗi thao tác phải có deadline worst-case cứng, hãy xem xét AVL/red-black hoặc giải pháp có giới hạn đã chứng minh.

**3. Dữ liệu thay đổi nhiều không?** Nếu gần như không bao giờ chèn/xóa, mảng đã sắp xếp có thể gọn và tận dụng cache tốt hơn. Skip list hữu ích hơn khi cập nhật liên tục mà vẫn phải tìm và duyệt theo thứ tự.

### 18.2. Tại sao không nên so chỉ mỗi ký hiệu O(log n)?

Hai cấu trúc đều có O(log n) nhưng khác:

- Số lần dereference qua node.
- Số byte pointer/metadata.
- Cache miss và phân bổ bộ nhớ.
- Số phép so sánh và cập nhật liên kết.
- Chi phí lock/reclamation nếu concurrent.
- Độ khó kiểm thử và xử lý lỗi.

Bài benchmark nên dùng **cùng tập khóa, dãy thao tác và kết quả**, đo latency trung bình lẫn phân vị cao, đồng thời giám sát peak memory. Một seed ngẫu nhiên tốt duy nhất không đại diện cho phân phối.

### 18.3. Khi giữ nguyên dữ liệu đầu vào nhưng ngẫu nhiên hóa cấu trúc

Skip list không bắt buộc hoán đổi thứ tự chèn do người dùng gửi. Các khóa `1,2,3,...,n` có thể được chèn theo thứ tự tăng; mỗi node vẫn nhận chiều cao được bốc nội bộ.

Tuy nhiên, mô hình expected chi phí thường giả định các lần rút mức **độc lập** theo phân phối thích hợp và không bị một đối thủ chọn thao tác dựa trên việc lộ toàn bộ trạng thái ngẫu nhiên. Nếu môi trường bảo mật/đối kháng, `random.Random(seed)` không phải giải pháp chống tấn công độ phức tạp theo mặc định; cần threat model, nguồn random và giới hạn tài nguyên phù hợp.


## 19. Bài tập thực hành có lời giải

### Bài 1. Phân biệt một node và nhiều tầng

Một node khóa 40 có chiều cao H=4. Nó có mặt ở những tầng nào? `size` tăng bao nhiêu khi thêm?

**Lời giải:** Node có mặt ở L0, L1, L2, L3. Nó là **một object** với bốn slot forward, nên `size` tăng đúng **1**, không phải 4.

### Bài 2. Điều kiện sang phải khi tìm

Tại một tầng, node hiện tại có successor khóa 30. Cần tìm `k=30`. Thuật toán với điều kiện `next.key<k` có đi sang successor không?

**Lời giải:** Không. Vì `30<30` sai nên ta xuống tầng thấp hơn; cuối cùng dừng trước ứng viên 30 để xác minh bằng nhau. Cách này bảo toàn việc tìm tiền nhiệm cho chèn/xóa.

### Bài 3. Vì sao giữ `current` khi xuống tầng?

Trong skip list, nếu mỗi lần xuống tầng lại về HEAD rồi đi tìm tiếp, thuật toán mất lợi thế gì?

**Lời giải:** Nó bỏ qua tiến độ định vị đã có ở tầng cao. Node `current` thuộc cả các tầng thấp nên vị trí hiện tại vẫn nằm trước key cần tìm; tiếp tục từ đó tiết kiệm số bước ngang và là cơ sở cho đường tìm kỳ vọng ngắn.

### Bài 4. Tìm khóa vắng

Với tập `[10,20,30,40,50,60,70,80]`, tìm 55. `contains(55)`, `lower_bound(55)` và `predecessor(55)` trả gì?

**Lời giải:** Lần lượt **False, 60, 50**. Sau khi tìm theo `<55` ở L0, node đứng trước vị trí chèn là 50, ứng viên là 60.

### Bài 5. Khóa ngoài biên dưới

Danh sách có khóa `[10,20,30]`. `lower_bound(5)` và `predecessor(5)` trả gì?

**Lời giải:** `lower_bound(5)=10`, `predecessor(5)=None`. HEAD đứng trước mọi khóa; không có tiền nhiệm dữ liệu nhỏ hơn 5.

### Bài 6. Khóa ngoài biên trên

Vẫn tập `[10,20,30]`. Tìm 99.

**Lời giải:** `contains(99)=False`, `lower_bound(99)=None`, `predecessor(99)=30`. Vòng đi ngang kết thúc ở node lớn nhất của L0 và successor là NULL.

### Bài 7. Tính `update[]` cho 55

Với skip list mẫu ở Mục 1, `update[3], update[2], update[1], update[0]` khi tìm vị trí chèn 55 là gì?

**Lời giải:** `[40,40,40,50]`. Dãy ấy lưu **tiền nhiệm tương ứng từng tầng**, không nhất thiết là các node khác nhau.

### Bài 8. Chèn node H=2

Sau khi tìm `update[0]=50`, `update[1]=40`, node 55 có H=2. Phải sửa mấy tầng?

**Lời giải:** Hai tầng L0, L1. Ở L0 nối `50→55→60`, ở L1 nối `40→55→60`. Không sửa tầng L2/L3; `size` tăng 1.

### Bài 9. Đảo thứ tự gán con trỏ

Một chương trình thực hiện `update[i].forward[i]=fresh` rồi mới `fresh.forward[i]=update[i].forward[i]`. Sai ở đâu?

**Lời giải:** Sau phép gán đầu, `update[i].forward[i]` đã trỏ tới `fresh`; phép gán sau khiến `fresh.forward[i]` tự trỏ lại chính nó, làm mất successor cũ. Phải lưu successor **trước khi** thay liên kết tiền nhiệm.

### Bài 10. Node mới cao hơn mọi node cũ

Skip list đang dùng L0–L1 (`level_count=2`). Một khóa mới được bốc H=4. `update[2]` và `update[3]` là gì?

**Lời giải:** Cả hai là HEAD, vì trước đó các tầng L2, L3 chưa có node dữ liệu. Sau chèn `level_count=4`.

### Bài 11. Vì sao kiểm tra trùng khóa trước khi bốc H?

Một set đã có khóa 30. Nếu gọi `insert(30)` lần nữa, code học thuật ở Mục 8 có bốc mức mới không?

**Lời giải:** Không. Hàm tìm thấy candidate bằng 30 và trả False trước khi `_random_height` chạy. Nhờ vậy không cấp node trùng và state RNG không bị tiêu thụ không cần thiết.

### Bài 12. Xóa node cao ba tầng

Node khóa 10 có H=3. Nếu chỉ gỡ `forward[0]`, hậu quả gì?

**Lời giải:** Node 10 vẫn được tham chiếu ở L1/L2, khiến cấu trúc không còn đúng bất biến. Nếu `free` node, các liên kết cao có thể thành con trỏ treo. Phải gỡ ở cả L0, L1, L2.

### Bài 13. Đếm `size` sau xóa

Một node cao H=7 được xóa thành công. `size` thay đổi bao nhiêu?

**Lời giải:** Giảm **1**, vì chỉ một khóa/object đã bị xóa. Số tầng liên kết bị tháo không phải số node được xóa.

### Bài 14. Xóa tầng cao nhất

Danh sách đang có bốn tầng. Xóa node duy nhất ở L3, nhưng L2 còn dữ liệu. `level_count` mới là bao nhiêu?

**Lời giải:** 3. Thu hẹp từ L3 xuống L2; không xóa L2 vì vẫn có node.

### Bài 15. Nhiều tầng rỗng liên tiếp

Sau xóa, L3 và L2 đều rỗng còn L1 có node. Cần cập nhật `level_count` ra sao?

**Lời giải:** Dùng vòng `while` giảm tới **2 tầng đang sử dụng** (L0 và L1), không chỉ giảm một lần. Sau khi xóa hết node, mức nhỏ nhất luôn là 1.

### Bài 16. Xóa một khóa không có

`discard(999)` chạy khi set không chứa 999. Có nên giảm `size` hoặc đổi bất kỳ liên kết nào không?

**Lời giải:** Không. Trả False và giữ nguyên cấu trúc, số tầng, số node và version trong chính sách code bài.

### Bài 17. Chiều cao và chỉ số forward

Nếu H=3, chỉ số `forward[3]` có hợp lệ không?

**Lời giải:** Không. Node có ba ô `forward[0], forward[1], forward[2]`. Chỉ số 3 sẽ vượt mảng.

### Bài 18. Skip list rỗng

Sau khi xóa node cuối cùng, HEAD có bị giải phóng không? Metadata nào còn lại?

**Lời giải:** HEAD vẫn là sentinel thuộc skip list. `size=0`, `level_count=1` và `HEAD.forward[0]=None`. Những slot HEAD cao hơn nếu tồn tại cũng rỗng.

### Bài 19. Xác suất node đạt ít nhất bốn tầng

Với `p=1/2`, không có trần trước H=4, xác suất `H≥4` bằng bao nhiêu?

**Lời giải:** `(1/2)^3=1/8`. Cần ba lần nâng thành công từ H=1 tới H=4.

### Bài 20. Xác suất node đúng ba tầng

Với `p=1/2` và không trần, xác suất `H=3` là bao nhiêu?

**Lời giải:** `(1-p)p^{H-1}=(1/2)^3=1/8`, gồm hai lần nâng thành công và lần tiếp theo thất bại.

### Bài 21. Trần mức làm thay đổi công thức ở đỉnh

Với `p=1/2`, `MAX_LEVEL=3`, xác suất `H=3` là `1/8` hay `1/4`?

**Lời giải:** **1/4**. Chỉ cần nâng thành công hai lần để đạt trần; không có lần tung tiếp theo để quyết định dừng. Do đó `Pr(H=3)=Pr(H≥3)=p²`.

### Bài 22. Kỳ vọng số ô forward

Với `p=1/2` và chiều cao không trần, trung bình một node có bao nhiêu ô forward?

**Lời giải:** `E[H]=1/(1-p)=2` ô. Với n node, tổng số forward slots kỳ vọng `2n`, ngoài metadata/allocator/sentinel.

### Bài 23. Worst-case nếu mọi node H=1

Khi tất cả node nằm trên L0, tìm phần tử lớn nhất mất bao nhiêu thời gian?

**Lời giải:** Θ(n), như danh sách đơn có thứ tự. Cấu trúc vẫn đúng, nhưng lần ngẫu nhiên này không tạo các đường nhảy có lợi.

### Bài 24. Vì sao không ghi worst-case chỉ O(n) cho chiều cao không trần?

Một skip list có một vài node nhưng được bốc một số tầng H cực lớn. Một thao tác phải đi xuống bao nhiêu tầng?

**Lời giải:** Tối đa H tầng, có thể mất Ω(H) bước dù n nhỏ. Cần ghi chi phí theo n **và H**, hoặc nêu rõ H bị chặn bởi MAX_LEVEL thích hợp.

### Bài 25. Mảng `update[]` thêm bao nhiêu bộ nhớ?

Code Python cấp mảng dài `L=max_level` cho mỗi chèn/xóa. Nếu L tăng theo n, có được bỏ qua O(L) không?

**Lời giải:** Không. Mảng dùng O(L) bộ nhớ tạm và có chi phí khởi tạo O(L). Với L=O(log n) có thể gộp vào O(log n), còn nếu L tăng nhanh hơn, tổng chi phí phải ghi thêm L.

### Bài 26. Tìm chỉ đọc có cần `update[]` không?

Một `contains(k)` chỉ trả True/False. Có bắt buộc dùng mảng L phần tử không?

**Lời giải:** Không. Giữ một con trỏ `current` và đi từ trên xuống đủ để xác định candidate L0, dùng O(1) bộ nhớ phụ trợ ngoài cấu trúc. Mảng `update[]` phục vụ cập nhật liên kết.

### Bài 27. Xóa trong C và double free

Một node xuất hiện ở bốn tầng. Nếu destructor duyệt lần lượt L0, L1, L2, L3 rồi `free` node tại mỗi tầng, điều gì xảy ra?

**Lời giải:** Node có thể bị `free` nhiều lần, hoặc các tầng sau đọc con trỏ đã hủy. Với skip list set sở hữu riêng, mọi node đều có mặt **một lần ở L0**, nên destructor đi L0 và hủy mỗi node một lần.

### Bài 28. Vì sao lấy `next` trước `free`?

Trong C:

```c
Node *next = current->next[0];
free(current);
current = next;
```

Tại sao thứ tự này quan trọng?

**Lời giải:** Sau `free(current)` không được đọc `current->next[0]` nữa (use-after-free). Lưu next trước khi hủy giúp tiếp tục theo L0 mà không đọc vùng đã giải phóng.

### Bài 29. Range query

Tập `{10,20,30,40,50,60,70}`. `range_keys(25,60)` trả gì và chi phí theo k kết quả là bao nhiêu?

**Lời giải:** Trả `[30,40,50]`, vì khoảng là `[25,60)` loại khóa 60. Chi phí O(log n+k) **kỳ vọng** với phân phối tầng đủ, cần tính thêm chi phí cấu hình nếu hàm dùng mảng update dài L.

### Bài 30. Rank/select có sẵn không?

Skip list cơ bản chỉ lưu `forward[i]`. Có thể thực hiện `select(r)` kỳ vọng O(log n) chỉ từ các liên kết ấy không?

**Lời giải:** Không có công thức trực tiếp theo chỉ số, vì các con trỏ chỉ biết node kế tiếp chứ không biết nhảy qua bao nhiêu node tầng 0. Cần thêm span/width và cập nhật đúng khi chèn/xóa để đạt chi phí kỳ vọng logarit.

### Bài 31. Kiểm tra hậu điều kiện của `insert`

Nêu ba điều phải đúng sau `insert(k)` thành công.

**Lời giải:** (1) K xuất hiện **đúng một lần** tại L0 và mọi tầng dưới H mới. (2) Mọi tầng vẫn sorted và tầng cao là dãy con tầng thấp. (3) `size` tăng 1, node cũ không bị mất; `level_count` phản ánh mức cao nhất hiện dùng.

### Bài 32. Kiểm tra hậu điều kiện của `discard`

Nêu ba điều phải đúng sau `discard(k)` thành công.

**Lời giải:** (1) K không còn reachable từ bất kỳ tầng nào của skip list. (2) Các tầng còn lại sorted, liên kết nối qua node đã xóa tới successor cũ. (3) `size` giảm 1, tầng cao rỗng được bỏ khỏi metadata, không còn con trỏ treo trong các liên kết thuộc cấu trúc.

### Bài 33. Cập nhật trong khi duyệt

Một iterator đang yield khóa theo L0, và chương trình xóa node mà iterator chuẩn bị đọc. Có được chắc chắn vẫn duyệt đúng không?

**Lời giải:** Không. Ở Python, node có thể còn sống vì tham chiếu nhưng đã rời cấu trúc; ở C/C++, con trỏ có thể treo. Cần chính sách cấm sửa, fail-fast, snapshot hoặc đồng bộ/ownership phù hợp.

### Bài 34. Vì sao seed cố định không biến skip list thành cân bằng tất định?

Một chương trình dùng `random.Random(123)` cho mọi lần chạy. Vậy nó có chặn O(log n) worst-case không?

**Lời giải:** Không. Seed cố định tạo chuỗi có thể tái lập, chứ không áp đặt bất biến chiều cao. Phân phối hình dạng có thể chứa trạng thái xấu; với môi trường đối kháng, tính dự đoán của PRNG còn có thể làm giả định phân tích không phù hợp.

### Bài 35. Chọn cấu trúc cho deadline cứng

Một hệ thống đòi hỏi mỗi phép tìm trong set có thứ tự đều phải O(log n) worst-case theo mô hình chuẩn. Skip list random thuần có đủ không?

**Lời giải:** Không. Skip list thông thường bảo đảm O(log n) kỳ vọng, nhưng có trạng thái xấu tuyến tính. Nên cân nhắc AVL/red-black tree hoặc cấu trúc khác có chặn worst-case được chứng minh.

## 20. Tổng kết: công thức thao tác cần nhớ

Ba thao tác cốt lõi của skip list có thể tóm gọn bằng **một đường tìm chung** và **một cặp phép nối ở mỗi tầng**.

### 20.1. Công thức tìm

```text
for i = level_count - 1 down to 0:
    while next[i] exists and next[i].key < target:
        current = next[i]

candidate = current.forward[0]
```

- `candidate.key == target`: tìm thấy.
- `candidate` rỗng hoặc khóa lớn hơn: không thấy.
- `current` là tiền nhiệm nghiêm ngặt trên L0.
- Nếu cần chèn/xóa, **lưu `update[i]`** ở mỗi tầng trước khi xuống.

### 20.2. Công thức chèn tại tầng i

```text
fresh.forward[i]      = update[i].forward[i]
update[i].forward[i]  = fresh
```

- Chỉ thực hiện cho `0 ≤ i < fresh.height`.
- Điền HEAD cho những tầng mới chưa từng dùng.
- Bốc chiều cao **sau** khi kiểm tra khóa trùng.
- `size += 1` đúng một lần, không theo số tầng.

### 20.3. Công thức xóa tại tầng i

```text
update[i].forward[i]  = target.forward[i]
```

- Chỉ thực hiện cho `0 ≤ i < target.height`.
- Tất cả liên kết tới target phải được gỡ trước khi hủy node.
- Hạ `level_count` bằng `while` khi nhiều tầng trên cùng trống.
- `size -= 1` đúng một lần.

### 20.4. Khi lựa chọn thuật toán cho dự án

- Bất biến **tầng đáy chứa mọi khóa**, các tầng cao là dãy con sorted phải luôn đúng.
- Ngẫu nhiên hóa chiều cao với p phù hợp giúp **tìm/chèn/xóa O(log n) kỳ vọng** trong phạm vi số tầng được thiết kế.
- Cần phân biệt **chi phí tìm kiếm**, **O(L) mảng update** nếu cấp cố định và **O(n) tổng forward slots kỳ vọng** với node cấp theo H.
- Chi phí worst-case có thể **O(n+L)** cho phiên bản giới hạn số tầng; không được dùng ký hiệu expected như một deadline cứng.
- Mã học thuật dùng các phép gán con trỏ tuần tự; hệ thống đồng thời cần cơ chế khóa/CAS, reclamation và iterator validity riêng.
- Mỗi node là **một đối tượng**, dù xuất hiện ở nhiều tầng. Xóa và hủy phải quản lý **đúng một vòng đời**.

**Quy tắc kiểm tra cuối:** bất cứ khi nào thay đổi một liên kết `forward[i]`, hãy xác định rõ **tiền nhiệm, node mục tiêu, successor, tầng i và hậu điều kiện sorted**. Nếu làm được điều đó ở mọi tầng, ba thao tác tìm–chèn–xóa sẽ trở nên có thể mô phỏng, chứng minh và kiểm thử một cách hệ thống.

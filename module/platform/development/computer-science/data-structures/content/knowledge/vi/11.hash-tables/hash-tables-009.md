# Hệ số tải và ảnh hưởng đến tìm kiếm, chèn, xóa

## 1. Hệ số tải trả lời câu hỏi nào?

Trong **bảng băm (hash table)**, hàm băm chuyển khóa thành một mã số, từ đó bảng xác định nơi bắt đầu tìm một cặp khóa–giá trị. Nhiều khóa có thể cùng hướng đến một ngăn hoặc một ô, nên hiệu năng còn phụ thuộc cách xử lý **va chạm (collision)** và số lượng dữ liệu đang lưu.

**Hệ số tải (load factor)** là đại lượng cơ bản để mô tả mức sử dụng bảng:

\[
\boxed{\alpha=\frac{n}{m}}
\]

Trong đó:

- `n` là **số khóa khác nhau đang hoạt động**, không phải số lần gọi thao tác thêm;
- `m > 0` là số **ngăn (bucket)** của bảng nối chuỗi, hoặc số **ô (slot)** của bảng địa chỉ mở;
- `α` đọc là “alpha”, biểu thị trung bình có bao nhiêu bản ghi trên một ngăn/ô xét theo toàn bảng.

Ví dụ: một bảng có `n=12` khóa và `m=16` ô có `α=12/16=0,75`. Nếu thêm ba khóa mới mà không đổi kích thước, `α=15/16=0,9375`. Nếu cập nhật giá trị của ba **khóa đã tồn tại**, `n` không đổi nên `α` cũng không đổi.

**Điểm then chốt:** hệ số tải là **tỷ số tổng**, không phải số khóa thực tế trong từng ngăn hay số bước cần để tìm một khóa. Hai bảng có cùng `α` vẫn có thể có số lần va chạm và thời gian truy cập rất khác nhau.

## 2. Vì sao cùng một tỷ số lại có ý nghĩa khác nhau?

Hai chiến lược xử lý va chạm thường gặp có cách dùng không gian khác nhau:

| Thuộc tính | Nối chuỗi (separate chaining) | Địa chỉ mở (open addressing) |
| --- | --- | --- |
| Nơi lưu bản ghi | Chuỗi/nhiều bản ghi gắn với mỗi ngăn | Trực tiếp trong các ô của mảng |
| Một ngăn/ô chứa tối đa bao nhiêu bản ghi đang hoạt động? | Một ngăn có thể chứa nhiều nút | Một ô chứa nhiều nhất một bản ghi |
| Miền `α` | `α ≥ 0`, **có thể lớn hơn 1** | `0 ≤ α ≤ 1`; để chèn khóa mới khi chưa đầy cần `n < m` |
| Khi `α` tăng | Số phần tử cần duyệt trong các chuỗi có xu hướng tăng | Ít ô trống hơn; số bước thăm dò có thể tăng rất nhanh |
| Xóa một bản ghi | Gỡ bản ghi khỏi chuỗi; chuỗi ngắn lại | Có thể để dấu `DELETED`, khiến đường thăm dò chưa ngắn đi |
| Bộ nhớ thường gặp | `O(m+n)` cho đầu ngăn và các nút | `O(m)` ô, cộng dữ liệu nằm trong mỗi ô |

Với **nối chuỗi**, bảng 8 ngăn vẫn có thể giữ 20 khóa: `α=20/8=2,5`. Với **địa chỉ mở**, 8 ô không thể giữ 20 khóa đang hoạt động vì mỗi ô chỉ chứa một bản ghi.

Do đó, không nên áp dụng máy móc một “ngưỡng tải chuẩn” cho mọi bảng băm. Việc chọn ngưỡng còn phụ thuộc chiến lược va chạm, chất lượng hàm băm, ngân sách bộ nhớ, tỷ lệ thao tác tìm thất bại và chi phí mở rộng.

## 3. Hệ số tải không đồng nghĩa với phân bố đều

Giả sử `m=8`, `n=4`, nên **cả hai tập khóa** đều có `α=0,5`. Dùng chỉ số `i(k)=k\bmod8`:

| Tập khóa | Các chỉ số nhận được | Độ dài chuỗi khi dùng nối chuỗi |
| --- | --- | --- |
| `{1,2,3,4}` | `1,2,3,4` | Bốn ngăn có 1 nút, các ngăn khác rỗng |
| `{1,9,17,25}` | `1,1,1,1` | Ngăn 1 có 4 nút, các ngăn khác rỗng |

```text
Bảng A:  0  1  2  3  4  5  6  7      Bảng B:  0  1  2  3  4  5  6  7
         .  1  1  1  1  .  .  .               .  4  .  .  .  .  .  .

   Mỗi số là số khóa trong ngăn; dấu . là ngăn rỗng.
```

Ở bảng B, tìm khóa trong ngăn 1 có thể phải duyệt một chuỗi bốn nút; ở bảng A, mỗi ngăn có dữ liệu chỉ chứa một nút. **Cùng `α` nhưng chất lượng phân bố khác nhau.**

Đối với địa chỉ mở với thăm dò tuyến tính, tập `{1,9,17,25}` có thể lấp các ô `1,2,3,4`, tạo **một cụm liên tiếp**. Lần tìm khóa `33` chưa tồn tại bắt đầu ở ô 1, rồi kiểm tra `1→2→3→4→5`; chỉ tới ô 5 trống mới dừng, tức 5 lần kiểm tra dù `α` mới là `0,5`.

Kết luận: **hệ số tải và chất lượng hàm băm phải được xem cùng nhau**; `α` nhỏ không tự bảo đảm mọi chuỗi ngắn hoặc mọi đường thăm dò ngắn.

## 4. Ảnh hưởng đối với bảng băm nối chuỗi

Với **separate chaining**, mỗi ngăn có một danh sách các cặp khóa–giá trị. Sau khi tính ngăn, bảng duyệt những nút thuộc ngăn đó để kiểm tra khóa.

Gọi `L_i` là số nút của ngăn `i`. Ta luôn có:

\[
\sum_{i=0}^{m-1} L_i=n,\qquad
\frac{\sum_i L_i}{m}=\alpha.
\]

Nếu mô hình băm **đều và đủ độc lập** giữa các khóa, số nút kỳ vọng của một ngăn là `E[L_i]=n/m=α`. Từ đó xuất hiện kết quả quen thuộc:

| Thao tác | Cách làm | Thời gian kỳ vọng nếu băm, so sánh khóa có chi phí hằng số |
| --- | --- | --- |
| Tìm thấy `get(k)` | Chọn ngăn, duyệt tới nút có khóa `k` | `O(1+α)` |
| Tìm không thấy | Duyệt hết chuỗi của ngăn cần tìm | `O(1+α)` |
| Chèn/cập nhật `put(k,v)` | Kiểm tra khóa đã có; cập nhật hoặc thêm nút | `O(1+α)` |
| Xóa `remove(k)` | Tìm nút, sửa liên kết của chuỗi | `O(1+α)` |

**Tìm kiếm.** Khi `α` tăng mà `m` giữ nguyên, số nút trung bình trên mỗi ngăn tăng. Dưới giả định phân bố tốt, thời gian kỳ vọng tìm kiếm cũng tăng theo `1+α`. Khi mọi khóa cùng ngăn, trường hợp xấu nhất vẫn có thể là `O(n)`.

**Chèn.** Nếu đã biết chắc khóa chưa tồn tại, việc chèn **vào đầu danh sách** có thể là `O(1)` sau khi tính chỉ số, bất kể `α`. Nhưng một *map* thông thường phải kiểm tra trùng khóa trước khi thêm; nếu bỏ qua, có thể tạo hai nút cùng khóa logic. Vì vậy, thao tác `put` đầy đủ thường tính cả chi phí duyệt chuỗi.

**Xóa.** Khi tìm thấy nút, gỡ nó bằng cập nhật tham chiếu đầu hoặc `next`; số khóa `n` giảm một và `α` giảm `1/m` nếu `m` không đổi. Chi phí **tìm nút** vẫn phụ thuộc độ dài chuỗi hiện tại. Không cần tombstone như địa chỉ mở.

**Bộ nhớ.** Nối chuỗi dùng một mảng `m` đầu ngăn và `n` nút, thường là `O(m+n)`, chưa tính chi phí nội dung khóa/giá trị. Tăng `m` giảm `α` nhưng tăng bộ nhớ của mảng ngăn.

Vì vậy, nếu duy trì `α ≤ c` với một hằng số `c` và giả định băm phù hợp, thời gian kỳ vọng cho những thao tác trên là `O(1)`.

## 5. Ảnh hưởng đối với bảng băm địa chỉ mở

Trong **open addressing**, một khóa được tìm bằng cách thử lần lượt các ô do quy tắc thăm dò tạo ra: tuyến tính (linear probing), bậc hai (quadratic probing) hoặc băm kép (double hashing). Khi `α` gần 1, ngày càng ít ô chưa được sử dụng, nên phép tìm không thành công hoặc thêm khóa mới dễ phải thử nhiều ô.

**Tìm kiếm thành công:** phải đi trên đúng dãy đã dùng khi chèn, qua các ô chứa khóa khác cho đến khi gặp khóa cần tìm. Khóa đã được chèn lúc bảng ít đầy có thể nằm gần vị trí ban đầu; khóa chèn muộn thường có khả năng bị đẩy xa hơn.

**Tìm kiếm thất bại:** tiếp tục thăm dò cho đến khi gặp ô `EMPTY` thực sự chưa từng dùng, hoặc hết số vị trí hợp lệ của dãy. Khi bảng gần đầy, việc gặp ô `EMPTY` thường mất nhiều bước hơn.

**Chèn mới:** trước hết phải xác định khóa chưa có, sau đó tìm được ô có thể lưu nó. Nếu `n=m` và không có ô trống, phải mở rộng bảng trước khi thêm khóa mới. Ngay cả khi `n<m`, một dãy thăm dò bậc hai thiết kế không phù hợp vẫn có thể không chạm tới ô trống.

**Cập nhật khóa cũ:** chỉ thay giá trị, nên `n` và `α` giữ nguyên; tuy nhiên, việc tìm đúng ô trước khi cập nhật vẫn có thể đắt khi dãy thăm dò dài.

### Các con số chỉ đúng dưới giả định xác suất cụ thể

Trong mô hình **uniform hashing lý tưởng cho địa chỉ mở** (mỗi khóa có thứ tự thăm dò như một hoán vị ngẫu nhiên độc lập của các ô), không xét xóa, số lần thử kỳ vọng có cận:

\[
\begin{aligned}
E[\text{tìm thất bại}]&\leq\frac{1}{1-\alpha},\\
E[\text{tìm thành công}]&\leq
\frac{1}{\alpha}\ln\frac{1}{1-\alpha},
\qquad 0<\alpha<1.
\end{aligned}
\]

| Hệ số tải `α` | Cận trên kỳ vọng: tìm thất bại | Cận trên kỳ vọng: tìm thành công |
| ---: | ---: | ---: |
| 0,25 | 1,33 lần thử | 1,15 lần thử |
| 0,50 | 2,00 lần thử | 1,39 lần thử |
| 0,75 | 4,00 lần thử | 1,85 lần thử |
| 0,90 | 10,00 lần thử | 2,56 lần thử |

Con số cho **tìm thành công** có thể nhỏ hơn nhiều so với tìm thất bại vì một phần khóa đã được chèn khi bảng còn thưa. Đây là **cận theo mô hình**, không phải kết quả đo hay bảo đảm áp dụng trực tiếp cho mọi kỹ thuật thăm dò.

Đặc biệt, **linear probing** dễ tạo cụm ô liên tiếp; mô hình “chỉ số ban đầu phân bố đều” của nó khác giả định “thứ tự thăm dò là một hoán vị ngẫu nhiên”. Do đó không dùng các cận trên như kết luận chính xác cho linear probing hay cho bảng có nhiều tombstone.

## 6. Xóa và vấn đề tải hiệu dụng của tombstone

Khi dùng địa chỉ mở, xóa một khóa bằng cách biến ngay ô của nó thành `EMPTY` có thể khiến việc tìm những khóa nằm phía sau **dừng sớm và trả sai**. Cách thông dụng là đặt dấu **`DELETED` (tombstone)**.

Trong tìm kiếm, chương trình phải **đi qua tombstone** vì có thể còn khóa nằm sau nó. Khi thêm khóa mới, chương trình có thể tái sử dụng tombstone, nhưng phải kiểm tra tiếp để tránh tạo thêm một bản sao của khóa đã có.

Gọi `d` là số ô đang mang dấu `DELETED`, ta có hai tỷ số khác nhau:

\[
\underbrace{\alpha=\frac{n}{m}}_{\text{tải khóa hoạt động}},
\qquad
\underbrace{\beta=\frac{n+d}{m}}_{\text{tỷ lệ ô không phải EMPTY}}.
\]

Nếu xóa một khóa bằng tombstone mà `m` không đổi:

- `n` giảm 1, nên **`α` giảm `1/m`**;
- `d` tăng 1, nên **`β` không đổi**.

Điều này giải thích nghịch lý: **xóa nhiều khóa nhưng việc tìm vẫn chậm**. Bảng có ít bản ghi đang hoạt động hơn, song đường thăm dò vẫn đi qua các ô đã từng dùng. Cần phân biệt `α` với `β`, và quan sát cả **phân bố vị trí tombstone** chứ không chỉ các tỷ số.

Ví dụ bảng có `m=8`, chứa bốn khóa `1,9,17,25` bằng linear probing tại các ô `1,2,3,4`. Sau khi xóa khóa 9 ở ô 2, bảng có `n=3` và `d=1`:

```text
Chỉ số       0      1      2       3       4      5      6      7
Trước xóa  [EMPTY] [1]    [9]     [17]    [25] [EMPTY] [EMPTY] [EMPTY]
Sau xóa    [EMPTY] [1]    [DEL]   [17]    [25] [EMPTY] [EMPTY] [EMPTY]
```

Trước khi xóa, `α=β=4/8=0,5`. Sau khi xóa, `α=3/8=0,375` nhưng `β=4/8=0,5`. Tìm `25` vẫn cần thử `1→2→3→4` (4 ô); tìm `33` không tồn tại vẫn thử `1→2→3→4→5` (5 ô).

Nếu **dựng lại** bảng 8 ô chỉ với các khóa đang hoạt động `1,17,25`, chúng sẽ chiếm `1,2,3`. Khi đó tìm 25 cần 3 lần kiểm tra và tìm 33 cần 4 lần. Việc dọn tombstone đã rút ngắn cụm dù số khóa không đổi.

## 7. Python: quan sát khi xóa làm giảm `α` nhưng chưa giảm số lần thử

Chương trình sau chỉ **mô phỏng ba trạng thái của cùng một bảng** với linear probing và khóa nguyên, không xây dựng một lớp `dict` hoàn chỉnh. Các mảng minh họa đúng các kết quả chèn, xóa bằng tombstone và dựng lại vừa trình bày.

```python
DA_XOA = object()


def thong_ke(bang):
    m = len(bang)
    n = sum(x is not None and x is not DA_XOA for x in bang)
    d = sum(x is DA_XOA for x in bang)
    return n / m, (n + d) / m


def so_o_kiem_tra(bang, khoa: int):
    m = len(bang)
    bat_dau = khoa % m

    for j in range(m):
        i = (bat_dau + j) % m
        muc = bang[i]
        if muc is None:
            return False, j + 1
        if muc is DA_XOA:
            continue
        if muc == khoa:
            return True, j + 1
    return False, m


truoc_xoa = [None, 1, 9, 17, 25, None, None, None]
sau_xoa = [None, 1, DA_XOA, 17, 25, None, None, None]
sau_dung_lai = [None, 1, 17, 25, None, None, None, None]

for ten, bang in [
    ("Truoc xoa", truoc_xoa),
    ("Sau xoa", sau_xoa),
    ("Sau dung lai", sau_dung_lai),
]:
    alpha, beta = thong_ke(bang)
    tim_25 = so_o_kiem_tra(bang, 25)
    tim_33 = so_o_kiem_tra(bang, 33)
    print(f"{ten}: alpha={alpha:.3f}, beta={beta:.3f}, "
          f"tim 25={tim_25}, tim 33={tim_33}")
```

Kết quả:

```text
Truoc xoa: alpha=0.500, beta=0.500, tim 25=(True, 4), tim 33=(False, 5)
Sau xoa: alpha=0.375, beta=0.500, tim 25=(True, 4), tim 33=(False, 5)
Sau dung lai: alpha=0.375, beta=0.375, tim 25=(True, 3), tim 33=(False, 4)
```

Một bản cài đặt thực tế phải giữ đúng dãy thăm dò khi thêm/tìm/xóa, không tái sử dụng tombstone trước khi kiểm tra khóa trùng, đồng thời kiểm soát việc mở rộng và dọn tombstone. Ví dụ này cố ý không thay đổi bảng bằng hàm chèn để tập trung vào **số bước tìm kiếm trước và sau khi xóa**.

## 8. Mở rộng, dựng lại và thu nhỏ: đánh đổi thời gian với bộ nhớ

Để giới hạn chi phí do tải tăng, nhiều bảng băm tự thay đổi dung lượng:

1. **Mở rộng (grow):** khi `α` vượt một ngưỡng, cấp phát mảng lớn hơn và đưa các bản ghi đang hoạt động vào đúng vị trí mới.
2. **Dựng lại để dọn tombstone (rebuild/rehash):** khi `d` nhiều hoặc `β` lớn, tạo lại bảng, có thể **giữ nguyên dung lượng** để loại dấu đã xóa.
3. **Thu nhỏ (shrink):** khi số khóa giảm đáng kể, có thể dùng bảng nhỏ hơn nhằm giảm bộ nhớ, nhưng phải tránh co–giãn liên tục khi số phần tử dao động gần ngưỡng.

Ví dụ: bảng có `n=12`, `m=16` nên `α=0,75`. Mở rộng lên `m=32` mà số khóa chưa đổi sẽ đưa `α` về `12/32=0,375`. Tuy nhiên, **không thể chỉ thêm 16 ô rỗng**: chỉ số băm hoặc thứ tự thăm dò có thể thay đổi theo dung lượng. Các khóa cần được **phân bố lại**.

Một lần dựng lại có thể tốn `O(m_{mới}+n)` thời gian kỳ vọng để cấp phát/khởi tạo mảng mới và phân bố `n` khóa khi hàm băm, phép so sánh và thăm dò có hành vi phù hợp. Trường hợp va chạm cực đoan có thể tốn hơn.

Nếu dung lượng tăng theo cấp số nhân và giữ tải trong ngưỡng phù hợp, chi phí của những lần mở rộng thỉnh thoảng xảy ra có thể **phân bổ (amortized)** cho nhiều thao tác thêm. Khi kết hợp giả định băm tốt, người ta thường nói `put` có **chi phí kỳ vọng, phân bổ `O(1)`**, không phải từng lần `put` đều `O(1)`.

**Không có ngưỡng duy nhất:** chọn ngưỡng thấp thường giảm độ dài chuỗi hoặc số bước thăm dò, nhưng dành nhiều bộ nhớ hơn. Chọn ngưỡng cao tiết kiệm chỗ trống nhưng có thể khiến tìm thất bại và thêm khóa mới chậm, đặc biệt với linear probing hoặc nhiều tombstone.

## 9. Xem xét độ phức tạp một cách đầy đủ

| Tình huống | Nối chuỗi | Địa chỉ mở |
| --- | --- | --- |
| Kỳ vọng khi phân bố phù hợp, tải được giữ trong ngưỡng | `get/put/remove: O(1)` | `get/put/remove: O(1)` |
| Tăng tải mà không đổi dung lượng | Chiều dài chuỗi trung bình tăng cùng `α` | Ít ô trống, có thể phải thử nhiều ô hơn |
| Trường hợp xấu nhất khi tìm một khóa | `O(n)` nút trong một ngăn | `O(m)` lần thăm dò |
| Xóa một khóa | Chuỗi ngắn đi; không cần dấu đã xóa | Có thể tạo tombstone; cần quản lý `β` |
| Bộ nhớ cấu trúc | `O(m+n)` | `O(m)` |
| Khi thay đổi dung lượng | Phân bố lại bản ghi theo ngăn mới | Tái chèn theo dãy thăm dò của bảng mới |

Các biểu thức `O(1)` kỳ vọng trong bảng **giả định tính băm và so sánh khóa là `O(1)`**, và tính cả việc duy trì ngưỡng tải bằng chính sách mở rộng hợp lý. Nếu khóa là chuỗi dài `L`, tính mã băm từ đầu có thể tốn `O(L)`; phép so sánh cũng có thể phải kiểm tra nhiều ký tự. Vì thế, phân tích thực tế cần cộng hoặc tách riêng chi phí xử lý khóa.

Cũng cần phân biệt ba kiểu phát biểu:

- **Trung bình/kỳ vọng:** dựa trên mô hình phân bố khóa hoặc hàm băm; không đảm bảo mọi thao tác đều nhanh.
- **Trường hợp xấu nhất:** khi nhiều khóa va chạm hoặc bảng gần đầy, một thao tác có thể tốn số bước tuyến tính theo kích thước bảng.
- **Phân bổ:** một lần resize đắt được trải trên nhiều lần cập nhật; không có nghĩa lần resize trở thành thao tác tức thời.

## 10. Cách đo và lựa chọn ngưỡng cho ứng dụng

Thay vì chỉ theo dõi một tỷ số `α`, nên quan sát các chỉ số sát với công việc của chương trình:

- **Nối chuỗi:** chiều dài trung bình và lớn nhất của chuỗi, số phép so sánh khóa khi tìm thấy/không thấy, bộ nhớ dành cho nút và tham chiếu.
- **Địa chỉ mở:** số ô thăm dò theo từng thao tác, tỷ lệ tìm thất bại, chiều dài cụm, số tombstone `d`, tỷ lệ `β=(n+d)/m`.
- **Cả hai:** tần suất resize/rehash, thời gian của lần resize, dung lượng đỉnh và độ dài khóa thực tế.

Thử nghiệm nên bao gồm trường hợp khóa gần ngẫu nhiên, khóa có mẫu đều đặn, thao tác thêm–xóa xen kẽ và trường hợp tìm khóa không tồn tại thường xuyên. Dữ liệu đầu vào có cấu trúc hoặc do bên ngoài điều khiển có thể tạo va chạm bất lợi; một `α` thấp đơn lẻ không đủ chứng minh hiệu năng hoặc khả năng chống tấn công gây va chạm.

## 11. Tự kiểm tra

**Câu 1.** Bảng có `m=20` ngăn, `n=30` khóa. `α` là bao nhiêu? Cấu trúc nào có thể chứa dữ liệu như vậy?

**Đáp án:** `α=30/20=1,5`. Nối chuỗi có thể lưu nhiều khóa trong mỗi ngăn. Địa chỉ mở với 20 ô không thể chứa 30 bản ghi đang hoạt động.

**Câu 2.** Bảng có `n=9`, `m=16`. Cập nhật giá trị của hai khóa cũ và thêm ba khóa mới. `α` cuối cùng là bao nhiêu?

**Đáp án:** Chỉ ba khóa mới làm `n` tăng: `n=12`. Vì `m=16`, `α=12/16=0,75`.

**Câu 3.** Trong bảng địa chỉ mở `m=100`, `n=40`, `d=30`, hãy tính `α` và `β`. Vì sao tìm kiếm vẫn có thể chậm?

**Đáp án:** `α=40/100=0,4` và `β=(40+30)/100=0,7`. Tombstone không chứa khóa hoạt động nhưng vẫn có thể kéo dài đường thăm dò vì tìm kiếm không được dừng tại đó.

**Câu 4.** Hai bảng nối chuỗi đều có `α=0,5`, nhưng một bảng dồn nhiều khóa vào một ngăn. Có thể nói độ dài chuỗi tìm kiếm của chúng như nhau không?

**Đáp án:** Không. Hệ số tải chỉ cho biết số khóa trung bình trên mỗi ngăn; phân bố cụ thể và va chạm quyết định độ dài chuỗi cần duyệt.

**Câu 5.** Vì sao “tra cứu bảng băm là `O(1)`” cần bổ sung điều kiện?

**Đáp án:** Đây thường là **kỳ vọng** khi hàm băm phân bố phù hợp, tải được kiểm soát và chi phí xử lý khóa được giả định là hằng số. Trường hợp xấu nhất có thể phải duyệt nhiều nút/ô; resize và khóa dài cũng phát sinh chi phí.

**Ghi nhớ:** `α=n/m` là thước đo mức tải, nhưng **không mô tả đầy đủ phân bố va chạm**. Với nối chuỗi, tải cao làm chuỗi trung bình dài hơn; với địa chỉ mở, tải cao và tombstone làm đường thăm dò dài hơn, đặc biệt khi tìm thất bại. Muốn bảng băm nhanh và đúng qua các thao tác tìm–chèn–xóa, cần chọn hàm băm phù hợp, quản lý tải, xử lý xóa đúng cách và tái phân bố dữ liệu khi cần.

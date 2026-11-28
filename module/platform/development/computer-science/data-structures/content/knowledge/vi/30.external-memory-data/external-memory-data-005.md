# Cây B+-tree dưới góc nhìn chỉ mục lưu trên thiết bị

## 1. Bài toán: tìm kiếm khi dữ liệu lớn hơn RAM

Ở các bài về mảng, danh sách liên kết, cây và bảng băm, ta thường đếm số phép so sánh hoặc thao tác trong RAM. Khi dữ liệu nằm trên SSD, HDD hoặc một thiết bị lưu trữ khác, cách đếm đó chưa đủ: đọc một phần tử thường kéo theo việc đọc **cả một trang (page)**. Cơ sở dữ liệu thường tổ chức tệp thành các trang có kích thước cố định, chẳng hạn 4 KiB, 8 KiB hoặc 16 KiB.

Giả sử một bảng có hàng triệu bản ghi và ứng dụng cần:

- Tìm chính xác bản ghi theo khóa: “Đơn hàng 84521 nằm ở đâu?”
- Đọc các bản ghi có khóa từ 1000 đến 2000, đúng thứ tự tăng dần.
- Thêm, xóa, sửa khóa mà không phải sắp xếp lại toàn bộ tệp.
- Đọc ít trang từ thiết bị nhất có thể, tận dụng những trang đang nằm trong bộ đệm (buffer pool).

Một **B+-tree** giải quyết nhóm yêu cầu này bằng cách lưu một cây tìm kiếm cân bằng, trong đó **mỗi nút thường vừa vào một trang**. Mỗi trang trong của cây chứa nhiều khóa phân cách và nhiều địa chỉ trang con, nên một lần đọc trang giúp loại trừ một phạm vi rất lớn. Các khóa và vị trí bản ghi được lưu có thứ tự tại **các lá**; lá được liên kết để hỗ trợ quét khoảng.

Trong học phần *Cấu trúc dữ liệu*, B+-tree là ví dụ tiêu biểu cho nguyên tắc **lựa chọn cấu trúc theo môi trường lưu trữ**: ngoài độ phức tạp thời gian và bộ nhớ, cần xem xét số lượt truy cập trang (page I/O), tính cục bộ và chi phí cập nhật.

## 2. Một cây B+-tree lưu những gì?

Các thành phần chính:

| Thành phần | Nội dung | Vai trò |
| --- | --- | --- |
| Trang trong (internal page) | Các khóa phân cách đã sắp xếp và ID/địa chỉ trang con | Dẫn đường tìm kiếm |
| Trang lá (leaf page) | Các mục chỉ mục đã sắp xếp theo khóa | Nơi tìm thấy khóa và thông tin trỏ đến dữ liệu, hoặc bản ghi nếu tổ chức theo kiểu clustered |
| Liên kết giữa các lá | Thường là ID trang lá kế tiếp; có thể có cả trang trước | Quét các khóa liên tiếp mà không cần trở lại từ gốc |
| Gốc (root page) | Điểm bắt đầu tìm kiếm, có thể đồng thời là lá khi cây nhỏ | Xác định nhánh cần đi |
| Siêu dữ liệu của trang | Loại trang, số mục, vùng trống, ID trang, thông tin phục hồi tùy hệ thống | Giúp bộ quản lý lưu trữ đọc và cập nhật trang an toàn |

Ví dụ với các khóa duy nhất:

~~~text
                         Trang gốc
                    [   30   |   60   ]
                     /       |         \
                    v        v          v
Lá A:           [10, 20] -> [30, 40, 50] -> [60, 70, 90]
                khóa <30    30<=khóa<60    khóa>=60
                   ^             ^              ^
              Trang lá A     Trang lá B      Trang lá C
~~~

Mũi tên giữa các lá diễn tả **thứ tự logic của khóa**. Các trang lá không nhất thiết nằm sát nhau về địa chỉ vật lý trên thiết bị.

Với quy ước minh họa ở trên, một trang trong có các khóa phân cách **K1, K2, ...** và các trang con **P0, P1, ...**: P0 chứa khóa nhỏ hơn K1; P1 chứa khóa từ K1 đến trước K2; trang con cuối chứa khóa từ khóa phân cách cuối trở lên. Một phép tìm khóa 45 chỉ cần đi từ gốc tới lá B.

### Các bất biến quan trọng

1. **Tính có thứ tự:** các khóa trong từng trang được sắp xếp; các miền khóa của các trang con không chồng lấn theo quy tắc phân nhánh đã chọn.
2. **Cân bằng theo chiều cao:** mọi lá ở cùng độ sâu, nên không có một nhánh dài bất thường.
3. **Giới hạn sức chứa:** trang trong có tối đa **f** con và tối đa **f − 1** khóa phân cách; trang lá có tối đa **b** mục chỉ mục. Các trang ngoài gốc thường phải giữ mức lấp đầy tối thiểu theo quy tắc triển khai.
4. **Khóa thực được truy cập ở lá:** với B+-tree, trang trong chủ yếu chứa khóa để định tuyến. Một khóa phân cách như 30 có thể **xuất hiện lại** tại lá.
5. **Thứ tự lá:** duyệt các lá kế tiếp cho ra dãy khóa không giảm, thuận tiện cho truy vấn khoảng và sắp xếp.

Đây là mô hình B+-tree cơ bản. Hệ quản trị cơ sở dữ liệu thực tế có thể dùng khóa tiền tố, nén, trang biến độ dài, chính sách tách trang hoặc xử lý khóa trùng khác nhau; không nên coi một quy tắc chia trang cụ thể là quy tắc chung của mọi hệ thống.

**Khóa trùng** cần được xử lý tường minh: một cách phổ biến là sắp thứ tự mục lá theo cặp **(khóa tìm kiếm, mã định danh bản ghi)** hoặc lưu nhiều vị trí bản ghi cho một khóa. Với trường hợp khóa trùng trải qua nhiều lá, phép tìm tất cả bản ghi phải xét ranh giới trang; thuật toán tìm chính xác ở mục tiếp theo giả định khóa duy nhất cho dễ theo dõi.

## 3. Từ đường đi trong cây đến số lần đọc trang

Đối với cây nhị phân, một nút chỉ có tối đa hai con; với B+-tree, một trang trong có thể có hàng trăm con. Khi cây lưu trên thiết bị, điều quan trọng là **mỗi cấp cây thường cần đọc tối đa một trang** trên đường tìm kiếm.

Giả sử ta đã biết ID trang gốc và mỗi trang đọc được qua thao tác **read_page(page_id)**:

~~~text
function find(root_page_id, target):
    page_id = root_page_id

    loop:
        page = read_page(page_id)  // Có thể được phục vụ từ buffer pool

        if page.is_leaf:
            i = lower_bound(page.entries, target)
            if i < page.entry_count and page.entries[i].key == target:
                return page.entries[i].record_reference
            return NOT_FOUND

        // Quy ước: khóa bằng một separator đi về nhánh bên phải.
        child_index = upper_bound(page.separators, target)
        page_id = page.children[child_index]
~~~

**lower_bound** tìm vị trí đầu tiên có khóa không nhỏ hơn khóa đích; **upper_bound** trên tập separator tìm vị trí đầu tiên có separator lớn hơn khóa đích. Hai thao tác này có thể dùng tìm kiếm nhị phân **bên trong trang đang ở RAM**. Các hệ thống có cơ chế phân cách khác có thể dùng quy tắc rẽ nhánh tương ứng.

Nếu cây có **h cấp trang** từ gốc đến lá, một lần tìm thường truy cập khoảng **h trang** ở trường hợp không có trang nào nằm sẵn trong cache. Nếu gốc và một số trang trong thường trú trong bộ đệm, số lần I/O vật lý có thể thấp hơn; tuy nhiên thuật toán vẫn cần đi qua các cấp logic.

### Tìm một khoảng khóa

B+-tree thuận lợi khi trả về nhiều khóa liền nhau:

~~~text
function range_scan(root_page_id, low, high):
    if low > high:
        return

    leaf = find_leaf_for_key(root_page_id, low)
    i = lower_bound(leaf.entries, low)

    while leaf exists:
        while i < leaf.entry_count:
            entry = leaf.entries[i]
            if entry.key > high:
                return

            yield entry
            i = i + 1

        if leaf.next_leaf_id == NONE:
            return

        leaf = read_page(leaf.next_leaf_id)
        i = 0
~~~

Thuật toán chỉ đi từ gốc xuống **một lần** để xác định điểm bắt đầu, sau đó lần lượt đọc các lá theo liên kết **next_leaf_id**. Với thứ tự giảm dần, cần thêm liên kết về lá trước hoặc một cơ chế duyệt ngược tương ứng.

Ví dụ: truy vấn các mã sản phẩm thuộc đoạn **[3500, 3700]** sẽ tìm đến lá chứa khóa đầu tiên không nhỏ hơn 3500, đọc tiếp đến khi gặp khóa lớn hơn 3700 rồi dừng. Đây là sự khác biệt quan trọng so với chỉ mục băm vốn chủ yếu tối ưu tra cứu theo khóa chính xác.

## 4. Tính sức chứa từ kích thước trang

Hãy thiết kế một ví dụ đơn giản để thấy vì sao B+-tree thường có chiều cao thấp:

| Giả định | Giá trị |
| --- | ---: |
| Kích thước một trang | 4096 byte |
| Dữ liệu đầu trang (header) dành trước | 128 byte |
| Kích thước một khóa | 8 byte |
| Địa chỉ một trang con | 8 byte |
| Mã tham chiếu bản ghi (RID) | 8 byte |
| Địa chỉ trang lá kế tiếp | 8 byte |

Một trang trong có **f** con cần **f** địa chỉ con và **f − 1** khóa phân cách:

~~~text
128 + 8*f + 8*(f - 1) <= 4096
120 + 16*f          <= 4096
f <= 248
~~~

Trong mô hình này, một trang trong có thể có **tối đa 248 con**.

Một trang lá có **b** mục dạng **(khóa 8 byte, RID 8 byte)** và một địa chỉ trang lá kế tiếp:

~~~text
128 + 8 + (8 + 8)*b <= 4096
b <= 247
~~~

Vậy một lá có thể chứa **tối đa 247 mục**. Đây là tính toán minh họa đã đơn giản hóa: chưa tính slot directory, kiểm tra toàn vẹn, thông tin khóa độ dài thay đổi, nén hay các chi tiết của một hệ quản trị cụ thể.

Giả sử ta có **1.000.000 mục chỉ mục** và trung bình mỗi lá hoặc trang trong sử dụng khoảng **70% sức chứa**. Khi đó, mỗi lá chứa xấp xỉ **173 mục**, và mỗi trang trong có khoảng **173 con**:

~~~text
Số lá cần dùng             ≈ ceil(1.000.000 / 173) = 5.781
Số trang trong ngay trên lá ≈ ceil(5.781 / 173)     = 34
Số trang gốc               = 1 (đủ trỏ đến 34 trang)
Chiều cao tính theo trang  ≈ 3 cấp: gốc -> trong -> lá
~~~

Vì thế, một phép tìm chính xác có thể chỉ cần đọc **3 trang** nếu cả ba cấp đều chưa được cache. Nếu cần đọc **1.000 mục liên tiếp**, phần quét thường qua khoảng **6–7 trang lá**, tùy vị trí bắt đầu và độ đầy thực tế, cộng với các trang trên đường đến lá đầu tiên. Việc quét theo liên kết lá giúp tránh đi từ gốc xuống cho từng mục.

### Mô hình chi phí I/O

Đặt:

- **N:** tổng số mục chỉ mục.
- **f:** số con trung bình hữu hiệu của một trang trong (fanout).
- **b:** số mục trung bình hữu hiệu của một trang lá.
- **k:** số mục chỉ mục được trả về.
- **h:** số cấp từ gốc đến lá (tính cả gốc và lá).

Khi các trang được lấp đầy tương đối ổn định:

| Thao tác | Số trang cần truy cập theo bậc lớn | Giải thích |
| --- | --- | --- |
| Tìm một khóa | O(h) ≈ O(log_f N) | Mỗi cấp đọc một trang trên đường đi |
| Tìm và duyệt khoảng chứa k mục | O(h + k/b) | Tìm lá đầu rồi quét những lá kế tiếp |
| Chèn một khóa | O(h) | Tìm lá; có thể tách trang và lan lên tổ tiên |
| Xóa một khóa | O(h) | Tìm lá; có thể phân phối lại hoặc gộp các trang |
| Dung lượng trang chỉ mục | O(N/b) trong điều kiện lấp đầy bị chặn dưới | Các trang trong tạo thêm chi phí quản lý |

Các biểu thức trên xem mỗi lần đọc/ghi trang là một đơn vị chi phí và lược bỏ hằng số. Khi **k = 0**, truy vấn khoảng vẫn có chi phí tìm điểm bắt đầu **O(h)**. Chi phí cập nhật tính cả số cấp có thể bị ảnh hưởng bởi tách/gộp trang; trong thực tế còn có ghi log, đồng bộ, latch và bộ đệm.

**Phân biệt “đọc mục chỉ mục” với “đọc bản ghi”:** nếu lá chỉ lưu RID và bản ghi thực nằm rải rác ở các trang dữ liệu, trả về k bản ghi có thể phát sinh tới khoảng k lần đọc trang dữ liệu bổ sung trong trường hợp xấu. Do đó, quét khoảng trên chỉ mục có thể hiệu quả, nhưng truy xuất các bản ghi rời rạc vẫn đắt. Đây là lý do cần hiểu sự khác nhau giữa chỉ mục **clustered** và **secondary/unclustered**.

## 5. Chèn, tách trang và bảo toàn bất biến

Phép chèn bắt đầu bằng việc tìm trang lá phù hợp:

1. **Lá còn chỗ:** chèn mục vào vị trí đúng thứ tự. Có thể cần cập nhật khóa phân cách trong tổ tiên nếu khóa nhỏ nhất của một nhánh thay đổi, tùy cách lưu separator.
2. **Lá đầy:** tạo trang lá mới, phân phối các mục giữa hai trang và nối lại liên kết lá. Ghi khóa phân cách của trang phải vào trang cha.
3. **Trang cha đầy:** tách tiếp trang trong và đưa khóa phân cách thích hợp lên cấp cao hơn.
4. **Gốc đầy:** tạo gốc mới; chiều cao cây tăng một cấp.

Ví dụ giả định **mỗi lá tối đa 3 khóa**, khóa duy nhất và các lá không phải gốc cần giữ **ít nhất 2 khóa**. Ban đầu một lá có **[10, 20, 30]**. Chèn **40** khiến nó tràn, nên ta chia thành hai lá:

~~~text
Trước:           [10, 20, 30] + 40

Sau:                 [30]            (gốc mới)
                     /  \
                    v    v
               [10, 20] -> [30, 40]
~~~

Khóa phân cách **30** được *sao chép* lên gốc trong khi khóa **30** vẫn hiện diện ở lá phải. Tiếp tục chèn **25**:

~~~text
                     [30]
                     /  \
                    v    v
            [10, 20, 25] -> [30, 40]
~~~

Tất cả lá vẫn ở cùng độ sâu. Khi tách **trang trong**, khóa phân cách được đưa lên cha theo quy tắc của triển khai; việc phân chia con phải giữ miền khóa nhất quán. Không được sao chép máy móc quy tắc tách lá cho mọi loại nút.

### Xóa, mượn khóa và gộp trang

Sau khi xóa một mục khỏi lá, nếu số mục còn lại thấp hơn ngưỡng tối thiểu, cây có thể:

- **Mượn/phân phối lại** mục từ lá anh em có dư; cập nhật separator của cha.
- **Gộp** với lá anh em nếu không thể mượn; xóa một separator/địa chỉ con ở cha và có thể xử lý thiếu hụt tiếp ở cha.
- **Co gốc** khi gốc chỉ còn một con, làm cây thấp đi một cấp.

Tiếp tục cây sau khi chèn 25: xóa **30** khiến lá phải chỉ còn **[40]**, ít hơn 2 mục. Lá trái có 3 mục nên có thể chuyển mục lớn nhất **25** sang lá phải:

~~~text
Trước khi xóa 30:             Sau khi cân bằng:
        [30]                          [25]
       /    \                        /    \
[10,20,25] -> [30,40]          [10,20] -> [25,40]
~~~

Giá trị separator ở gốc chuyển từ **30** sang **25**, vì khóa nhỏ nhất của lá phải đã đổi. Nếu cả hai lá đều ở mức tối thiểu và một lá bị thiếu mục, thao tác gộp có thể cần thiết.

Ví dụ này dùng quy tắc cân bằng điển hình của B+-tree để giải thích cơ chế; cách chọn điểm tách, mức lấp đầy mục tiêu và xử lý xóa trong hệ thống lưu trữ thực tế có thể khác.

## 6. Vì sao thiết bị lưu trữ làm thay đổi quyết định thiết kế?

Giả sử có 1 triệu khóa. Với một cây nhị phân cân bằng, đường tìm kiếm có bậc **log₂ N**, khoảng 20 nút; nếu mỗi nút nằm ở một trang khác nhau, đây có thể là 20 lần đọc trang. B+-tree với fanout hàng trăm có thể chỉ cao 3–4 cấp. Trong bộ nhớ, tìm kiếm nhị phân giữa hàng trăm separator vẫn cần CPU; nhưng so với độ trễ truy cập thiết bị, thường có lợi khi gom nhiều khóa vào một trang.

Các yếu tố vật lý cần ghi nhớ:

| Yếu tố | Hệ quả đối với B+-tree |
| --- | --- |
| **Kích thước trang** | Trang lớn tăng fanout và giảm chiều cao, nhưng có thể làm tăng lượng dữ liệu đọc thừa hoặc chi phí ghi khi cập nhật ít mục |
| **Buffer pool** | Trang gốc và các trang trong thường xuyên truy cập có thể nằm trong RAM, giảm I/O vật lý |
| **Liên kết lá** | Tốt cho quét có thứ tự; hiệu năng quét còn tùy bố trí vật lý của các trang và khả năng đọc trước (prefetch) |
| **Tách và gộp** | Cần cấp phát, ghi trang, cập nhật tham chiếu; có thể tạo phân mảnh theo thời gian |
| **SSD và HDD** | SSD giảm đáng kể độ trễ truy cập ngẫu nhiên so với HDD, nhưng giảm số lượt truy cập trang và tăng tính cục bộ vẫn có giá trị |
| **Khả năng phục hồi** | Cơ sở dữ liệu thường kết hợp cấu trúc chỉ mục với ghi log, kiểm soát đồng thời và quy trình phục hồi; B+-tree riêng lẻ không tự đảm bảo tính bền vững giao dịch |

Một cây liên kết các lá theo thứ tự khóa **không đảm bảo** các trang lá được ghi liên tiếp trên thiết bị. Bộ quản lý tệp, cấp phát trang, vùng trống, bộ đệm và lịch sử cập nhật đều ảnh hưởng đến hiệu năng thực tế.

## 7. B+-tree làm chỉ mục trong cơ sở dữ liệu

### Khác nhau giữa chỉ mục và bản ghi dữ liệu

Một **secondary index** thường lưu tại lá các mục dạng **(giá trị khóa, tham chiếu đến bản ghi)**. Tìm khóa trong cây chỉ là bước đầu; để đọc các cột không nằm trong chỉ mục, bộ máy có thể phải lấy bản ghi ở vị trí được tham chiếu.

Với **clustered index** hoặc cách tổ chức bảng mà lá chứa bản ghi, dữ liệu được duy trì gần với thứ tự khóa logic; truy vấn phạm vi có thể được lợi do tránh nhiều bước truy hồi bản ghi rời rạc. Từ “clustered” phụ thuộc mô hình lưu trữ của từng hệ quản trị, nhưng ý chính là **mức độ gắn kết giữa thứ tự khóa của chỉ mục và dữ liệu được lấy ra**.

Nếu các cột mà truy vấn cần đã có trong chỉ mục, bộ máy có thể thực hiện **index-only scan** (tùy điều kiện khả dụng, như khả năng kiểm tra tính nhìn thấy của bản ghi), giúp giảm số trang dữ liệu phải đọc.

### Chỉ mục nhiều cột và quy tắc tiền tố trái

Giả sử có bảng đơn hàng và thường hỏi: “Lấy đơn hàng của khách hàng 42 trong tháng 1/2026, theo thứ tự ngày tạo.”

~~~sql
CREATE INDEX idx_orders_customer_time
    ON orders (customer_id, created_at);

SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at;
~~~

Trong B+-tree có khóa ghép **(customer_id, created_at)**, mọi mục của **customer_id = 42** nằm trong một đoạn liên tục, và bên trong đoạn đó các mục được sắp theo **created_at**. Bộ máy có thể tìm điểm đầu rồi quét cho tới khi vượt giới hạn thời gian.

Ngược lại, truy vấn chỉ lọc theo **created_at** mà không ràng buộc **customer_id** thường không có một đoạn liên tục duy nhất để quét hiệu quả trên chỉ mục này. Cách bộ máy tối ưu tùy hệ quản trị và thống kê dữ liệu, nhưng **thứ tự cột của khóa ghép** là một quyết định thiết kế quan trọng.

Truy vấn ở trên lấy cả **order_id** và **total**. Nếu chỉ mục không chứa các cột cần thiết và lá không lưu toàn bộ bản ghi, hệ thống phải đọc dữ liệu tương ứng sau khi tìm RID/khóa chính; không thể mặc nhiên xem mọi truy vấn phạm vi là truy vấn chỉ đọc trang chỉ mục.

### Ví dụ lựa chọn theo loại truy vấn

| Nhu cầu | B+-tree phù hợp vì | Điều cần kiểm tra |
| --- | --- | --- |
| Tìm chính xác mã đơn hàng | Đường đi ngắn từ gốc đến lá | Nếu chỉ cần tra cứu đúng khóa, bảng băm cũng có thể là phương án tốt |
| Lấy đơn hàng trong khoảng ngày | Lá có thứ tự và liên kết để quét liên tục | Chỉ mục ghép có đặt cột lọc và cột khoảng đúng thứ tự không |
| Duyệt theo thứ tự giá tăng dần | Có thể duyệt theo khóa của chỉ mục | Truy vấn có cần lấy thêm cột ngoài chỉ mục không |
| Thường xuyên chèn bản ghi mới | Hỗ trợ chèn cục bộ, có tách trang khi cần | Khóa tăng dần, lấp đầy trang, tranh chấp trên trang nóng |
| Truy vấn theo tiền tố chuỗi | Có thể khai thác miền giá trị liên tiếp trong một số cách so sánh khóa | Collation, biểu thức tìm kiếm và khả năng dùng chỉ mục của hệ quản trị |

## 8. So sánh với một số cấu trúc chỉ mục khác

| Cấu trúc | Tra cứu theo khóa | Quét khoảng theo thứ tự | Cập nhật trên dữ liệu lưu ngoài RAM |
| --- | --- | --- | --- |
| **B+-tree** | O(log_f N) lần truy cập trang theo bậc lớn | Hiệu quả nhờ các lá đã sắp xếp và liên kết | Tách/gộp trang, thường chỉ tác động dọc một đường đi |
| **Bảng băm trên đĩa** | Thường tốt cho khóa chính xác khi phân bố phù hợp | Không có thứ tự khóa tự nhiên | Có thể phải chia bucket/rehash, tùy biến thể |
| **Mảng đã sắp xếp trên tệp** | Tìm nhị phân được nhưng có thể cần nhiều truy cập trang ngẫu nhiên | Tốt nếu dữ liệu được lưu liên tiếp | Chèn/xóa tại giữa có thể phải dịch chuyển nhiều dữ liệu |
| **LSM-tree** | Thường phối hợp nhiều tầng và bộ lọc để tìm | Quét khoảng cần hợp nhất các dãy/tầng đã sắp xếp | Tối ưu ghi theo lô, đổi lại chi phí compaction và có thể khuếch đại đọc/ghi |

Không tồn tại lựa chọn tốt nhất cho mọi tải công việc. B+-tree thường là phương án cân bằng cho **đọc theo khóa, duyệt có thứ tự và cập nhật trực tiếp trên các trang**. Bảng băm hấp dẫn nếu yêu cầu gần như toàn tra cứu chính xác; LSM-tree có thể phù hợp khi khối lượng ghi lớn và chấp nhận đánh đổi ở đọc, hợp nhất dữ liệu.

## 9. Những lỗi tư duy dễ gặp

- **Nhầm B+-tree với cây tìm kiếm nhị phân:** một nút B+-tree có nhiều con; fanout lớn mới là yếu tố giảm số cấp và số lần truy cập trang.
- **Cho rằng separator ở trang trong chính là nơi chứa bản ghi:** separator dùng để rẽ nhánh; mục dữ liệu cần đọc ở lá trong mô hình B+-tree.
- **Cho rằng các lá nối nhau tức là các trang liền nhau trên SSD/HDD:** liên kết logic không quyết định vị trí vật lý.
- **Đếm O(log N) rồi bỏ qua kích thước trang:** trên thiết bị, **O(log_f N) lượt truy cập trang** thể hiện lợi ích thực tế rõ hơn.
- **Bỏ qua fetch bản ghi:** chỉ mục thứ cấp có thể quét rất ít trang lá nhưng lại đọc nhiều trang dữ liệu rải rác.
- **Quên sửa separator sau khi đổi khóa nhỏ nhất của trang con:** một thao tác chèn/xóa có thể làm sai đường đi tìm kiếm nếu miền khóa của cha không còn khớp.
- **Nhầm lẫn với B-tree:** B-tree có các biến thể lưu giá trị ở nút trong; B+-tree đưa các mục cần quét về lá và liên kết lá, nên thường thuận tiện cho range scan.

## 10. Tự kiểm tra và thực hành

**Bài 1 — Ước lượng I/O.** Cho một cây có 3 cấp trang từ gốc đến lá. Gốc đã nằm trong RAM, các trang còn lại chưa được cache. Tìm một khóa chính xác cần đọc tối đa bao nhiêu trang từ thiết bị nếu không tính trang dữ liệu ngoài chỉ mục?

**Đáp án:** Tối đa **2 trang** (một trang trong, một trang lá). Đường tìm kiếm vẫn đi qua 3 cấp logic.

**Bài 2 — Quét một khoảng.** Một lá có trung bình 100 mục; một truy vấn trả về 450 mục liên tục. Vì sao không thể kết luận chính xác “quét 5 lá” nếu chưa biết vị trí mục đầu tiên?

**Đáp án:** 450/100 = 4,5 gợi ý khoảng 5 lá khi quét bắt đầu đầu trang. Nếu bắt đầu sát cuối một lá, quét có thể cần thêm một lá; hơn nữa số mục thực trên mỗi lá không nhất thiết bằng trung bình. Chi phí nên được mô tả là **O(h + k/b)** và đo bằng phân bố trang thực tế.

**Bài 3 — Kiểm tra bất biến.** Một lá phải có tối thiểu 2 khóa, đang chứa **[30, 40]** và lá trái có **[10, 20, 25]**; cha chứa separator **30**. Sau khi xóa 30, thao tác cân bằng nào bảo toàn thứ tự khóa và separator phải là bao nhiêu?

**Đáp án:** Chuyển **25** từ lá trái sang lá phải; hai lá thành **[10, 20]** và **[25, 40]**. Separator mới là **25**.

**Bài 4 — Thiết kế chỉ mục.** Hệ thống có truy vấn chủ đạo: “Lấy giao dịch của một tài khoản trong khoảng thời gian cho trước, theo thời gian tăng dần”. Hãy đề xuất khóa ghép phù hợp và giải thích.

**Gợi ý đáp án:** Khóa **(account_id, transaction_time)** đặt các giao dịch của một tài khoản vào cùng một đoạn và sắp xếp theo thời gian, giúp seek một lần rồi quét. Cần xét thêm các cột được trả về để giảm truy hồi bản ghi và tính chọn lọc của truy vấn thực tế.

### Ghi nhớ để vận dụng

Khi đánh giá B+-tree, trước tiên hãy hỏi **một trang chứa được bao nhiêu khóa**, **cây cần bao nhiêu cấp**, **tìm hay quét khoảng**, và **lá chứa bản ghi hay chỉ chứa tham chiếu**. Sau đó mới xem tác động của kích thước trang, tỷ lệ lấp đầy, cache, tách/gộp và đặc điểm thiết bị. Cách nhìn này nối các bất biến của cấu trúc dữ liệu với chi phí I/O mà hệ thống thật phải trả.

# Phân biệt ưu tiên ngẫu nhiên với độ ưu tiên nghiệp vụ

**Ưu tiên ngẫu nhiên** (*random priority*) và **độ ưu tiên nghiệp vụ** (*business priority*) đều có thể được biểu diễn bằng một con số, nhưng chúng trả lời **hai câu hỏi hoàn toàn khác nhau**. Trong treap, priority ngẫu nhiên là một **khóa kỹ thuật nội bộ** để định hình cây tìm kiếm theo thứ tự khóa. Trong hệ thống xử lý công việc, độ ưu tiên nghiệp vụ diễn tả **công việc nào nên được phục vụ trước** theo quy định của sản phẩm hoặc vận hành.

Nhầm hai khái niệm có thể dẫn tới hai lỗi đối lập: một cây tra cứu trở nên lệch tuyến tính vì dùng điểm khẩn cấp thay cho random, hoặc một hệ thống xếp lịch phục vụ sai khách hàng vì lấy priority ngẫu nhiên của treap làm độ quan trọng của công việc.

Bài **“Phân biệt ưu tiên ngẫu nhiên với độ ưu tiên nghiệp vụ”** thuộc chương **Cấu trúc ngẫu nhiên** trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo định hướng xây dựng nền tảng từ mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, ta sẽ dùng **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** để quyết định cấu trúc phù hợp với từng yêu cầu.

## 1. Mục tiêu và một tình huống mở đầu

Sau khi học, bạn có thể:

- Phân biệt **khóa BST**, **priority ngẫu nhiên**, **priority nghiệp vụ**, **payload** và **thứ tự xử lý**.
- Giải thích vì sao treap có thể tìm theo `id` trong O(log n) **kỳ vọng** mà không hề chọn tác vụ khẩn cấp nhất.
- Chứng minh việc đặt `priority_treap=business_priority` **không** giữ giả định random và có thể tạo cây lệch.
- Chọn cấu trúc dữ liệu cho các truy vấn: tìm theo ID, duyệt ID theo thứ tự, lấy tác vụ khẩn nhất, cập nhật điểm ưu tiên, phân trang hoặc lấy theo hai thứ tự.
- Biết dùng **hai chỉ mục** trên cùng tập bản ghi: một treap theo `id` và một heap theo `business_priority`, cùng cơ chế đồng bộ.
- Hiểu duplicate, tie-breaker, cập nhật priority, stale heap entries, aging và khái niệm starvation.
- Cài đặt mô phỏng Python dùng treap + priority queue, có bất biến và bộ test.
- Phân biệt kỳ vọng hiệu năng của randomized structure với bảo đảm ưu tiên/đúng đắn của quy trình nghiệp vụ.
- Đánh giá chi phí O(log n), O(n), O(k) và rủi ro version, ownership, concurrent updates.

### 1.1. Tình huống: xử lý phiếu hỗ trợ

Một nền tảng hỗ trợ khách hàng có ba phiếu:

| ID phiếu | Độ ưu tiên nghiệp vụ (số nhỏ hơn khẩn hơn) | Mô tả |
| --- | ---: | --- |
| 120 | 1 | Thanh toán dịch vụ bị gián đoạn |
| 150 | 5 | Hỏi tài liệu hướng dẫn |
| 180 | 2 | Người dùng không đăng nhập được |

Ta cần trả lời **hai loại câu hỏi khác nhau**:

- “Phiếu có ID 150 ở đâu?” → truy vấn **theo khóa ID**.
- “Phiếu nào phải xử lý trước?” → truy vấn **theo business priority**: ID 120 trước, sau đó ID 180, rồi ID 150.

Nếu lưu các ID trong một treap, root **không bắt buộc** là ID 120. Root là node có **priority kỹ thuật nhỏ nhất**, do một bộ sinh số giả ngẫu nhiên chọn. Hệ thống không được lấy “node đang ở root treap” làm phiếu đầu tiên xử lý.

## 2. Bốn trường dữ liệu: ID, random priority, business priority, payload

Một bản ghi trong hệ thống có thể được mô hình hóa:

```text
Ticket:
    id                 : khóa định danh nghiệp vụ duy nhất
    business_priority  : điểm xử lý theo quy tắc sản phẩm
    payload            : dữ liệu phiếu, trạng thái, chủ sở hữu ...
    created_sequence   : thứ tự tạo phiếu để hòa điểm bằng nhau

TreapNode:
    key                : ticket.id
    random_priority    : số nội bộ dùng làm min-heap trong treap
    left, right        : hai liên kết BST
    subtree_size       : metadata hỗ trợ rank/select
```

**Quyết định quan trọng:** `TreapNode.random_priority` **không** đại diện cho `Ticket.business_priority`. Nhiều hệ thống thực tế lưu payload hoặc reference tới ticket trong node treap; sự khác biệt **ngữ nghĩa** vẫn cần được bảo toàn dù hai trường nằm chung một object.

### 2.1. Bất biến của treap

Bài dùng treap set với key tăng nghiêm ngặt:

\[
\forall x\in subtree(u.left): x.key<u.key,
\qquad
\forall y\in subtree(u.right): u.key<y.key.
\]

Min-heap theo ưu tiên ngẫu nhiên:

\[
u.random\_priority < child.random\_priority
\]

trên mọi cạnh cha–con khi priority có thứ tự toàn phần nghiêm ngặt.

Ta có thể thêm:

\[
size(u)=1+size(u.left)+size(u.right).
\]

Những bất biến này **không đề cập đến business priority**. Cây vẫn hợp lệ dù một phiếu khẩn cấp nhất nằm sâu hoặc mang ID lớn nhất.

### 2.2. Bất biến của priority queue nghiệp vụ

Một hàng đợi ưu tiên có thể dùng **min-heap** với khóa so sánh:

\[
(business\_priority,\ created\_sequence,\ id).
\]

Khi quy tắc là **số nhỏ hơn cần phục vụ trước**:

1. Ưu tiên nghiệp vụ nhỏ hơn được lấy trước.
2. Nếu cùng ưu tiên, phiếu được tạo trước (`created_sequence` nhỏ hơn) đi trước.
3. Nếu vẫn hòa, dùng ID như tie-breaker tất định.

Đây là **chính sách nghiệp vụ**, không phải randomization. Trong Python, `heapq` cũng dùng min-heap, nhưng min-heap của **business key** khác min-heap của **treap random priority**.

Nếu doanh nghiệp quy ước **số lớn hơn quan trọng hơn**, phải đảo comparator nghiệp vụ hoặc dùng `-priority` trên số có kiểu phù hợp. Không được tự đảo comparator random treap theo chiều ấy: đó là một bất biến kỹ thuật riêng.

### 2.3. Một bảng so sánh ngắn

| Thuộc tính | Khóa BST | Priority ngẫu nhiên của treap | Priority nghiệp vụ |
| --- | --- | --- | --- |
| Chức năng | Định danh/tìm theo thứ tự | Quyết định hình dạng cây | Quyết định thứ tự phục vụ |
| Ai đặt? | Dữ liệu đầu vào | Cơ chế random nội bộ | Quy tắc sản phẩm/vận hành |
| Ví dụ | `id=120` | `priority=0.143...` | `critical=1` |
| Bất biến | Trái < gốc < phải | Cha ưu tiên tốt hơn con | Phần tử đầu là công việc cần phục vụ |
| Có thể thay đổi? | Thường phải remove+insert | Thường giữ cố định trong vòng đời node | Có thể đổi theo SLA/aging/escalation |
| Cần độc lập với key? | Không áp dụng | Có, trong mô hình phân tích kỳ vọng chuẩn | Không, do nghiệp vụ quyết định |
| Có nên lộ trực tiếp cho người dùng? | Tùy ID | Thường không | Có thể có |
| Root treap có phải phiếu đầu? | Không | Root có random priority tốt nhất | Không được suy ra |

## 3. Ví dụ: root ngẫu nhiên không phải phiếu khẩn cấp nhất

Giả sử treap chứa các cặp `(id, random_priority)`:

```text
(120, 80), (150, 10), (180, 50)

                     (150,10)
                     /      \
                (120,80)   (180,50)
```

Phần **business priority** trong ba ticket là:

```text
Ticket(id=120, business_priority=1)
Ticket(id=150, business_priority=5)
Ticket(id=180, business_priority=2)
```

Hai bất biến treap đúng: `120<150<180`; random priority `10<80` và `10<50`. Nhưng root ID 150 có **business priority 5**, nên **không** phải phiếu cần phục vụ trước.

Thứ tự đúng của nghiệp vụ là:

```text
Lấy theo business_priority:
120 (1) -> 180 (2) -> 150 (5)

Duyệt treap inorder theo ID:
120 -> 150 -> 180

Root treap theo random_priority:
150
```

Ba kết quả khác nhau hoàn toàn nhưng **cùng đúng trong ba cách diễn giải**.

### 3.1. Nếu đổi business priority thì treap có cần quay không?

Giả sử phiếu ID 150 được nâng cấp mức khẩn từ 5 lên 0. Nếu treap dùng **random priority riêng**, ta chỉ sửa `Ticket.business_priority`; bất biến BST theo ID và heap theo random priority **không đổi**.

Tuy nhiên, nếu hệ thống còn lưu một priority queue nghiệp vụ, **chỉ mục đó bắt buộc phải được cập nhật** để ID 150 được phục vụ trước ID 120. Không quay treap **không** đồng nghĩa hệ thống đa chỉ mục đã hoàn tất cập nhật.

### 3.2. Nếu đổi ID thì sao?

Nếu đổi ID 150 thành 190 trong khi node vẫn nằm ở gốc có con phải ID 180, bất biến BST sẽ hỏng (`180<190` nhưng vẫn ở bên phải). Phải xóa khóa cũ và chèn khóa mới, hoặc thiết kế key không thể đổi.

**Kết luận:** thay **business priority** khác thay **key BST**, và cả hai khác việc thay **random priority** của node treap.

## 4. Vì sao priority của treap cần ngẫu nhiên?

Một BST thông thường có thể suy biến khi nhập khóa theo thứ tự tăng. Treap bổ sung priority ngẫu nhiên độc lập để hình dạng cuối tương ứng một **Cartesian tree** của các cặp khóa–priority.

Giả sử:

- Có n khóa phân biệt `k_1<k_2<\cdots<k_n` đã cố định.
- Các priority được chọn **độc lập, cùng phân phối liên tục**.
- Không có adversary được quan sát priority rồi thích nghi chọn bộ khóa sống theo một cách làm thay đổi mô hình.

Vì priority liên tục nên xác suất bằng nhau là 0. Mọi thứ tự tương đối của n priority có xác suất `1/n!`. Treap có phân phối hình dạng tương tự BST được xây từ một hoán vị random, với:

\[
E[\text{độ sâu một khóa}]=O(\log n),
\qquad E[\text{chiều cao}]=O(\log n).
\]

Từ đó tìm/chèn/xóa trên đường cây có `O(\log n)` **kỳ vọng** dưới mô hình phù hợp.

### 4.1. Đổi random priority sang điểm nghiệp vụ phá giả định nào?

Điểm nghiệp vụ có thể:

- Chỉ thuộc 3–5 mức, gây rất nhiều **giá trị trùng**.
- Tương quan mạnh với ID, thời gian tạo, khách hàng hoặc loại lỗi.
- Bị con người cập nhật sau khi node đã được chèn.
- Có phân phối phụ thuộc vào thời điểm và nguồn dữ liệu.
- Bị đối thủ hoặc người dùng có quyền chọn theo ý muốn.

Vì vậy `business_priority` **không phải** mẫu IID liên tục độc lập với key. Không được gán `random_priority=business_priority` rồi sao chép kết luận expected O(log n) từ treap chuẩn.

### 4.2. Một trạng thái xấu nhưng hợp lệ

Giả sử mọi ticket có:

\[
key=i,\quad business\_priority=i,\quad i=1,\ldots,n.
\]

Nếu gán `priority_treap=business_priority`, với quy ước min-heap, treap bắt buộc là:

```text
(1,1)
    \
    (2,2)
        \
        (3,3)
            \
            ...
              (n,n)
```

Nó **đúng BST và đúng heap**, nhưng chiều cao n, tìm khóa cuối Θ(n). Dù bốc priority ngẫu nhiên độc lập thì worst-case tuyến tính vẫn có thể xảy ra, nhưng khi priority gắn tất định với ID, **kết quả xấu có thể được bảo đảm xảy ra** trên họ đầu vào ấy.

### 4.3. Nếu business priority trùng nhau thì sao?

Một treap cần cách xử lý tie nhất quán, ví dụ so cặp:

```text
(business_priority, insertion_serial)
```

Nhưng nếu dùng cặp này làm **priority định hình treap**, serial thường tăng theo thứ tự chèn và có thể tương quan với ID. Đối với dãy ID tăng, ở cùng mức business priority, thứ tự theo serial cũng tăng, tiếp tục tạo cây lệch.

**Tie-breaker tạo thứ tự toàn phần không biến một trường nghiệp vụ thành ngẫu nhiên độc lập.**

## 5. Không chỉ là vấn đề hiệu năng: còn là vấn đề đúng ngữ nghĩa

Có hai sai lầm độc lập:

**Sai lầm A — dùng business priority để định hình treap.** Treap có thể vẫn trả kết quả đúng theo ID nếu các invariant được duy trì, nhưng tính ngẫu nhiên và expected performance không còn được bảo đảm theo mô hình gốc; cập nhật business priority còn khiến heap của treap phải tái cấu trúc.

**Sai lầm B — dùng random priority để quyết định việc cần xử lý.** Cấu trúc vẫn có thể có hiệu năng tốt, nhưng sẽ phục vụ phiếu theo thứ tự **không có ý nghĩa kinh doanh**, vi phạm chính sách khẩn cấp và tie-breaker.

### 5.1. Một thiết kế tưởng hợp lý nhưng sai

```text
function next_ticket():
    return treap.root.ticket
```

Lệnh này lấy node có random priority tốt nhất, **không** phải node có business priority tốt nhất.

Ngay cả một lần duyệt inorder treap cũng chỉ trả thứ tự **theo ID**, không theo độ khẩn. Nếu cần “phiếu nào được phục vụ trước?”, phải dùng một chỉ mục nghiệp vụ tương ứng hoặc quét tất cả phiếu.

### 5.2. Một phép đổi business priority không được làm lại random seed

Nếu phiếu bị nâng mức độ ưu tiên, một triển khai sai có thể bốc lại `random_priority` cho node rồi quay treap, cho rằng điều này giúp nghiệp vụ nhanh hơn. Thực tế:

- Nó thay hình dạng chỉ mục tìm theo ID mà **không cần thiết**.
- Việc root thay đổi **không** đảm bảo phiếu khẩn nhất nằm ở root.
- Tính tái lập và iterator của treap trở nên khó kiểm soát hơn.
- Nếu không có một priority queue riêng, truy vấn “khẩn nhất” vẫn chưa được giải quyết.

**Tách trách nhiệm:** giữ random priority cho cân bằng kỳ vọng của chỉ mục khóa, giữ business priority cho chính sách phân phối công việc.


## 6. Chọn cấu trúc theo thao tác, không theo tên “priority”

Khi một yêu cầu nhắc tới từ “ưu tiên”, cần đặt câu hỏi: **đang ưu tiên điều gì?**

| Yêu cầu | Dữ liệu đem so sánh | Cấu trúc phù hợp |
| --- | --- | --- |
| Tìm ticket bằng ID | `id` | Hash map trung bình O(1), hoặc BST cân bằng/treap expected O(log n) |
| Liệt kê ID từ 100 đến 200 | `id` | Treap/AVL/red-black tree với inorder hoặc range query |
| Lấy ticket có mức khẩn nhỏ nhất | `business_priority`, tie-break theo thứ tự tạo | Binary heap / priority queue |
| Cập nhật độ khẩn của một ticket theo ID | `id` để tìm, `business_priority` để cập nhật chỉ mục | Hash map + indexed heap hoặc hai chỉ mục |
| Cả truy vấn ID theo khoảng và lấy việc khẩn nhất | **Hai quan hệ thứ tự khác nhau** | Treap theo ID + heap nghiệp vụ; cùng chung bản ghi |
| Đếm ID nhỏ hơn một ngưỡng | `id` + metadata `size` | Treap order-statistics |
| Lấy tất cả ticket cùng mức P1 | `business_priority` rồi ID/creation order | Ordered multimap hoặc secondary index theo composite key |
| Tra ID bất kỳ mà không cần thứ tự | `id` | Hash table thường đơn giản hơn treap |
| Sắp xếp toàn bộ backlog theo độ khẩn | Composite business key | Sorted index / sort hoặc heap pop liên tiếp, tùy workload |

**Không có một thứ tự nào tự giải quyết mọi truy vấn.** BST theo ID có thể hỗ trợ range theo ID, nhưng không tự có cách biết ID nào đang có business priority cao nhất nếu không có metadata hoặc chỉ mục phụ thích hợp.

### 6.1. Có thể dùng treap theo business priority không?

**Có**, nếu trường **BST key** của treap được đặt thành:

\[
key=(business\_priority,\ created\_sequence,\ id),
\]

và vẫn có một trường **random_priority độc lập** khác để duy trì heap ngẫu nhiên.

Khi đó inorder trả ticket theo business priority, không theo ID. Nhưng tìm theo ID bất kỳ không còn trực tiếp O(log n), vì ID lúc này là **một phần sau** của composite key, không phải thứ tự chính. Cần thêm một map từ ID tới bản ghi/composite key hoặc một chỉ mục theo ID khác.

Điều cấm nhầm không phải “treap không bao giờ được chứa business priority”, mà là:

> **Business priority có thể thuộc BST key; không được tùy tiện dùng nó làm random heap priority rồi vẫn viện dẫn bảo đảm random treap.**

### 6.2. Có thể lưu business priority làm metadata tổng hợp?

Nếu mỗi node theo ID lưu `business_priority`, ta có thể duy trì **minimum business priority của cả cây con**:

\[
subtree\_best(u)=\min\bigl(
priority(u),
subtree\_best(u.left),
subtree\_best(u.right)
\bigr).
\]

Khi đó root biết mức ưu tiên nghiệp vụ tốt nhất trong cả tập mà **không cần đổi random priority**. Nếu còn lưu tie-breaker và ID chiến thắng, ta có thể truy ngược ticket phù hợp.

Nhưng muốn điều đó đúng, **mọi phép insert, delete, rotate, split, merge và update business priority** phải cập nhật metadata từ dưới lên. Nếu một record nằm ngoài treap thay đổi mà không thông báo cho chỉ mục, `subtree_best` bị stale.

Cách này có thể phù hợp cho một chỉ mục duy nhất với aggregate; nó có chi phí cài đặt và đồng bộ riêng. Bài sẽ minh họa **hai chỉ mục** vì đơn giản hơn khi tách ngữ nghĩa và kiểm thử.

### 6.3. Hash map cộng binary heap, không cần treap?

Nếu hệ thống chỉ cần:

- Tìm ticket theo ID;
- Thay mức khẩn;
- Lấy ticket khẩn nhất;

thì một **dictionary/hash map + binary heap** thường đủ. Treap theo ID chỉ thực sự đáng cân nhắc nếu còn cần **duyệt ID theo thứ tự, predecessor/successor, range, rank/select** hoặc các phép split/merge theo miền ID.

Tư duy “đã học treap thì mọi yêu cầu phải dùng treap” là sai. Chọn cấu trúc dựa vào **tập thao tác thực tế** và loại bảo đảm cần.

## 7. Hai chỉ mục trên một tập record: một sơ đồ chính xác

Ta lưu bản ghi nghiệp vụ ở một nơi quản lý tập trung, còn hai chỉ mục trỏ tới cùng **định danh**.

```text
                     +----------------------+
                     | authoritative dict   |
                     | id -> Ticket          |
                     | (priority, version,   |
                     |  created_sequence)    |
                     +----------+-----------+
                                |
                +---------------+----------------+
                |                                |
                v                                v
    +-------------------------+       +-------------------------+
    | Treap index by ID       |       | Business priority heap  |
    | BST key       = id      |       | order = (priority,       |
    | random heap p = RNG()   |       |         created_seq, id) |
    | range, rank, lookup     |       | next most urgent        |
    +-------------------------+       +-------------------------+
```

Các thao tác có trách nhiệm:

- **Add(id,p):** thêm record vào dict; chèn id vào treap; thêm entry vào heap.
- **ChangePriority(id,new_p):** giữ nguyên id/priority ngẫu nhiên trong treap; thay record nghiệp vụ và cập nhật entry heap.
- **PopNext():** chọn entry hợp lệ tốt nhất trong heap; loại record khỏi dict và ID khỏi treap.
- **Cancel(id):** xóa record và ID; entry heap cũ phải bị vô hiệu.
- **ListIdRange(lo,hi):** truy vấn treap theo ID và đọc record từ dict.
- **PeekNext():** lấy ticket được ưu tiên nhất mà chưa xóa khỏi backlog.

### 7.1. Định nghĩa “nguồn sự thật”

Trong ví dụ, dictionary `id -> Ticket` là **nguồn sự thật** về ticket đang chờ. Treap và heap là **chỉ mục dẫn xuất**.

Bất biến tối thiểu:

\[
keys(treap)=keys(dictionary).
\]

Heap không nhất thiết có số entry bằng số ticket vì có thể tồn tại **entry cũ (stale)** sau khi cập nhật business priority. Thay vào đó phải có bảo đảm:

> Với mỗi ticket đang hoạt động, có **chính xác một entry đang hợp lệ** trong heap; các entry cũ không bao giờ được trả cho người dùng.

### 7.2. Vì sao không nên nhân bản payload trong hai index?

Nếu cả treap node và heap entry lưu một bản sao đầy đủ của ticket, việc cập nhật mức ưu tiên có thể đổi một bản sao mà quên bản còn lại. Từ đó truy vấn theo ID và theo độ khẩn trả **hai phiên bản khác nhau**.

Một thiết kế thường dùng:

- Dict giữ record hiện tại.
- Treap node chỉ giữ key ID và random priority kỹ thuật.
- Heap entry chỉ giữ composite business key, ID và **version** để kiểm tra hợp lệ.

Cách này giảm rủi ro **dữ liệu nghiệp vụ trùng lặp**. Tuy nhiên, nếu hai index được cập nhật tuần tự mà không có transaction, vẫn có trạng thái trung gian không nhất quán.

## 8. Cập nhật độ ưu tiên nghiệp vụ: hai lựa chọn heap

Binary heap trong nhiều thư viện cung cấp `push` và `pop` nhưng không có API “sửa khóa tại vị trí bất kỳ” tích hợp sẵn.

### 8.1. Indexed heap: sửa entry tại chỗ

Có thể duy trì:

```text
heap_array[index] = TicketPriorityEntry
position[id] = index
```

Khi cập nhật `business_priority`:

1. Tìm vị trí bằng `position[id]`.
2. Sửa business key.
3. `sift_up` hoặc `sift_down` để phục hồi heap.
4. Cập nhật `position[...]` ở **mọi phép swap**.

Với n ticket:

- Peek: O(1).
- Add: O(log n).
- Update priority: O(log n).
- Remove bất kỳ ID: O(log n).
- Pop: O(log n).
- Bộ nhớ: O(n) cho heap và map vị trí.

**Bẫy:** quên cập nhật map vị trí khi hoán đổi sẽ làm lần sửa sau tác động sai ticket.

### 8.2. Lazy invalidation: thêm entry mới và bỏ entry cũ

Một cách dễ cài bằng `heapq` của Python:

- Mỗi ticket có `generation` tăng khi business priority đổi.
- Mỗi lần đổi priority, **push một entry mới** với generation mới.
- Entry cũ vẫn nằm trong heap nhưng được coi là **không hợp lệ**.
- `peek/pop` kiểm tra entry ở đỉnh: nếu record không còn tồn tại hoặc generation không trùng, **pop bỏ entry cũ**, lặp đến khi gặp entry hợp lệ.

Ví dụ:

```text
Ticket ID=150, created_seq=2:

Ban đầu:
  record: business_priority=5, generation=0
  heap:   (5,2,150,0)  [hợp lệ]

Nâng độ khẩn:
  record: business_priority=0, generation=1
  heap:   (5,2,150,0)  [cũ, không hợp lệ]
          (0,2,150,1)  [hợp lệ]

peek_next():
  chọn entry (0,2,150,1) -> ID=150
```

Nếu một ticket bị hủy hoặc hoàn tất, dictionary không còn ID ấy: mọi entry còn lại của nó đều bị xem là stale.

**Điểm quan trọng:** khi cập nhật business priority, **không cần đổi `random_priority` của node treap**; chỉ thay record và chỉ mục heap nghiệp vụ.

### 8.3. Giá phải trả của lazy invalidation

Gọi:

- n = số ticket đang hoạt động;
- u = số lần cập nhật priority/hủy kể từ khi làm gọn heap;
- m = số entry hiện có trong heap, có thể lớn hơn n.

Khi dùng `heapq`, mỗi lần push/pop entry tốn O(log(m+1)). Một lần `peek_next` có thể phải loại **nhiều entry stale liên tiếp** trước khi thấy ticket thật:

- Không được hứa worst-case O(1) cho mọi `peek`.
- Không được thay `m` bằng `n` trong công thức nếu có thể tích tụ nhiều entry cũ.
- Tổng số entry stale bị loại không lớn hơn số entry đã từng được push và sau đó mất hiệu lực, nên có thể phân tích chi phí **amortized trên chuỗi thao tác**.

Một hệ thống có lịch sử cập nhật rất dài nên cân nhắc **compaction**: dựng lại heap từ các record hiện tại bằng `heapq.heapify` trong O(n), hoặc dùng indexed heap. Compaction làm thời gian một lần có thể O(n); không được gọi nó là worst-case O(log n) cho mỗi request.

## 9. Chính sách nghiệp vụ và tie-breaker phải được đặc tả rõ

Độ ưu tiên nghiệp vụ không có một quy ước toàn cầu. Trong dịch vụ xử lý công việc, doanh nghiệp phải tự trả lời:

- Số **nhỏ hơn** hay số **lớn hơn** là khẩn hơn?
- Hai công việc cùng mức độ khẩn xử lý FIFO, LIFO, theo deadline hay theo tài khoản khách hàng?
- Có cho phép nâng/hạ mức khi đang chờ không?
- Công việc đã hoàn tất có thể được đưa trở lại hàng chờ không?
- Hủy công việc có xóa ngay entry khỏi heap hay chỉ đánh dấu không hợp lệ?
- Có giới hạn số lần điều chỉnh ưu tiên hoặc chính sách chống starvation không?

### 9.1. Một thứ tự nghiệp vụ tổng quát

Ví dụ một sản phẩm quy định:

```text
business_key(ticket) =
    (severity_rank, created_sequence, id)

severity_rank: 0 = khẩn nhất, 5 = ít khẩn
created_sequence: số tăng dần khi ticket được tạo
id: tie-breaker cuối
```

Quy tắc này giúp hành vi **tất định** khi hai ticket có cùng `severity_rank`.

Không nên dùng **random_priority** của treap làm tie-breaker cho nghiệp vụ, vì như vậy thứ tự phục vụ của hai phiếu cùng mức sẽ phụ thuộc seed/chi tiết chỉ mục nội bộ — trừ khi sản phẩm **cố ý** chọn một chính sách random fairness và đã công bố nó.

### 9.2. Randomized load balancing khác business priority

Một bộ phân phối tải có thể **bốc ngẫu nhiên giữa những công việc có cùng mức** để phân phối đều, hoặc dùng lottery scheduling. Khi đó randomness là **một phần chính sách đã thiết kế**, không phải priority ngẫu nhiên của treap mặc định.

Hai luồng random cần phân biệt:

1. **Internal structural randomness**: bốc priority để treap cân đối theo kỳ vọng.
2. **Business scheduling randomness**: cố ý dùng random để chọn tác vụ theo quy tắc được phê duyệt.

Chúng có thể cùng dùng PRNG về mặt công cụ, nhưng **không nên dùng cùng trường priority hoặc phụ thuộc ngẫu nhiên vào hình dạng treap**. Việc tách nguồn RNG giúp test và tái lập nghiệp vụ.

### 9.3. Deadline và aging không tự là “priority số nhỏ nhất”

Một chính sách có thể ưu tiên deadline sớm nhất thay vì severity, hoặc tính:

\[
effective\_priority(t)=base\_priority-\alpha\cdot waiting\_time(t).
\]

Đây là một ví dụ **aging** để giảm nguy cơ tác vụ ưu tiên thấp bị chờ vô hạn. Nhưng khi thứ tự hiệu dụng thay đổi theo thời gian, heap chứa điểm cũ có thể trở thành **stale dù không có lệnh update rõ ràng**.

Các giải pháp thực tế gồm:

- Định kỳ tính lại các key và cập nhật/rebuild heap.
- Thiết kế lịch tăng điểm/tăng mức khi quá ngưỡng chờ.
- Dùng nhiều queue và cơ chế phân phối lượt theo quota/fairness.
- Sử dụng thuật toán có chứng minh về deadline hoặc fairness nếu có yêu cầu cứng.

**Không thể** đặt một công thức ưu tiên phụ thuộc thời gian rồi mong heap tự tái sắp đúng khi thời gian trôi qua mà không có bước cập nhật.

## 10. Loại bảo đảm: đúng thứ tự nghiệp vụ và nhanh kỳ vọng là hai lời hứa khác nhau

Một hệ thống hai chỉ mục có hai nhóm yêu cầu:

**Yêu cầu tính đúng:**

- `pop_next` chỉ trả một ticket **đang hoạt động**.
- Ticket trả về phải có **business key tốt nhất** trong các ticket đang hoạt động tại thời điểm chọn.
- Sau pop/cancel, ticket không còn trong treap và dictionary.
- Cập nhật business priority không làm thay key/heap-priority kỹ thuật của node treap.
- Không có hai ticket hoạt động cùng ID.

**Yêu cầu hiệu năng:**

- Treap có tìm/chèn/xóa theo ID O(log n) **kỳ vọng** dưới mô hình priority IID phù hợp; worst-case O(n).
- Heap có push/pop O(log m) theo m entry trong heap.
- Lazy invalidation có thể làm một lần peek/pop quét nhiều entry cũ.
- Dictionary lookup thường O(1) kỳ vọng với giả định hash phù hợp.
- Một thao tác nghiệp vụ cập nhật nhiều chỉ mục cần tính **tổng chi phí và công việc phục hồi**.

Không được dùng chứng minh expected treap để cam kết SLA “mọi ticket được xử lý trong 1 ms”, bởi còn có allocation, GC, concurrency, network, database, queueing delay và xử lý nghiệp vụ.

### 10.1. Ngẫu nhiên hóa không tự là bảo mật

`random.Random(seed)` rất hữu ích cho test tái lập nhưng không phải nguồn random mật mã. Nếu threat model có đối thủ được biết seed/hình dạng treap và chọn đầu vào, phải phân tích riêng.

Dùng CSPRNG để khó đoán hơn **không** biến random treap thành cây worst-case O(log n) trên mọi lần rút. Lựa chọn cấu trúc có chặn cứng như AVL/red-black có thể cần thiết với deadline cứng.

### 10.2. Tương quan nghiệp vụ và cấu trúc

Trong tập ticket thực, ID có thể tăng theo thời gian, còn business priority được chọn bởi loại sự cố và sự kiện. Vì vậy priority nghiệp vụ thường có cấu trúc **rất không ngẫu nhiên**. Dù một benchmark nhỏ thấy treap “cũng khá cân” khi dùng business priority, điều đó không cho phép áp dụng định lý cho priority IID liên tục trên mọi workload.

Một **chính sách nghiệp vụ đúng** cũng không có nghĩa “priority số nào cũng hợp lý”; nó là thỏa thuận sản phẩm, cần test bằng các tình huống domain, không chỉ test cấu trúc cây.


## 11. Python: hai chỉ mục, hai loại priority, một tập ticket

Đây là chương trình **Python 3.10+ độc lập**, chỉ dùng thư viện chuẩn. Nó lưu:

1. Một **treap theo ID**, có `random_priority` được bốc nội bộ và không biết business priority.
2. Một **min-heap nghiệp vụ** với tuple `(business_priority, created_sequence, ticket_id, generation)`.
3. Một **dictionary** `id -> Ticket` là nguồn sự thật.

Bản cài đặt tập trung vào **tính đúng của ngữ nghĩa và bất biến**, không phải một queue có thể thay thế sản phẩm nghiệp vụ thật. Nó dùng đệ quy trong treap, không có transaction nhiều index, không hỗ trợ nhiều thread.

### 11.1. Node treap và phép split/merge theo ID

```python
from __future__ import annotations

import heapq
import itertools
import random
from dataclasses import dataclass, replace
from collections.abc import Iterator


@dataclass(eq=False, slots=True)
class IdNode:
    ticket_id: int
    random_priority: tuple[int, int]
    left: IdNode | None = None
    right: IdNode | None = None
    size: int = 1


def subtree_size(node: IdNode | None) -> int:
    return 0 if node is None else node.size


def pull(node: IdNode) -> None:
    node.size = 1 + subtree_size(node.left) + subtree_size(node.right)


def split_ids(
    root: IdNode | None, key: int
) -> tuple[IdNode | None, IdNode | None]:
    """(< key, >= key); chỉ so ID, không so business priority."""
    if root is None:
        return None, None

    if root.ticket_id < key:
        less, greater_or_equal = split_ids(root.right, key)
        root.right = less
        pull(root)
        return root, greater_or_equal

    less, greater_or_equal = split_ids(root.left, key)
    root.left = greater_or_equal
    pull(root)
    return less, root


def merge_ids(
    left: IdNode | None, right: IdNode | None
) -> IdNode | None:
    """Mọi ticket_id(left) < mọi ticket_id(right)."""
    if left is None:
        return right
    if right is None:
        return left

    if left.random_priority < right.random_priority:
        left.right = merge_ids(left.right, right)
        pull(left)
        return left

    right.left = merge_ids(left, right.left)
    pull(right)
    return right


def erase_id(
    root: IdNode | None, key: int
) -> tuple[IdNode | None, bool]:
    """Xóa đúng một ID, dùng merge hai cây con của node mục tiêu."""
    if root is None:
        return None, False

    if key < root.ticket_id:
        root.left, removed = erase_id(root.left, key)
        pull(root)
        return root, removed

    if key > root.ticket_id:
        root.right, removed = erase_id(root.right, key)
        pull(root)
        return root, removed

    result = merge_ids(root.left, root.right)
    root.left = None
    root.right = None
    root.size = 1
    return result, True
```

Ở những primitive này:

- BST sử dụng **`ticket_id`**.
- Heap property của treap sử dụng **`random_priority`**.
- Không có tham số `business_priority`, nên việc đổi độ khẩn không thể vô tình làm quay treap qua các hàm này.
- `size` được bảo trì sau những lần đổi con trỏ, cho phép `rank` và kiểm thử.

### 11.2. Wrapper quản lý chỉ mục treap

```python
class IdTreap:
    """Chỉ mục ID có thứ tự, độc lập hoàn toàn với business priority."""

    def __init__(self, seed: int = 2026) -> None:
        self.root: IdNode | None = None
        self.rng = random.Random(seed)
        self.serial = 0

    def __len__(self) -> int:
        return subtree_size(self.root)

    def contains(self, ticket_id: int) -> bool:
        node = self.root
        while node is not None:
            if ticket_id == node.ticket_id:
                return True
            node = (
                node.left if ticket_id < node.ticket_id
                else node.right
            )
        return False

    def add(self, ticket_id: int) -> bool:
        if self.contains(ticket_id):
            return False

        # Serial chỉ phá hòa khi 128 bit random trùng nhau.
        priority = (self.rng.getrandbits(128), self.serial)
        self.serial += 1
        node = IdNode(ticket_id, priority)

        left, right = split_ids(self.root, ticket_id)
        self.root = merge_ids(merge_ids(left, node), right)
        return True

    def discard(self, ticket_id: int) -> bool:
        self.root, removed = erase_id(self.root, ticket_id)
        return removed

    def rank(self, ticket_id: int) -> int:
        """Đếm ID nhỏ hơn ticket_id."""
        answer = 0
        node = self.root

        while node is not None:
            if ticket_id <= node.ticket_id:
                node = node.left
            else:
                answer += 1 + subtree_size(node.left)
                node = node.right

        return answer

    def range_ids(self, low: int, high: int) -> Iterator[int]:
        """Sinh ID trong [low,high), theo thứ tự tăng."""
        if low >= high:
            return

        stack: list[IdNode] = []
        current = self.root

        while current is not None or stack:
            while current is not None:
                if current.ticket_id < low:
                    current = current.right
                else:
                    stack.append(current)
                    current = current.left

            if not stack:
                break

            current = stack.pop()
            if current.ticket_id >= high:
                break

            yield current.ticket_id
            current = current.right

    def keys(self) -> Iterator[int]:
        """Duyệt tất cả ID theo inorder."""
        stack: list[IdNode] = []
        current = self.root

        while current is not None or stack:
            while current is not None:
                stack.append(current)
                current = current.left

            current = stack.pop()
            yield current.ticket_id
            current = current.right

    def assert_valid(self) -> None:
        """Chỉ kiểm tra debug: BST, heap, size, node identity."""
        seen: set[IdNode] = set()

        def visit(
            node: IdNode | None,
            lower: int | None,
            upper: int | None,
            parent_priority: tuple[int, int] | None,
        ) -> int:
            if node is None:
                return 0

            assert node not in seen, "Cycle hoặc node lặp identity"
            seen.add(node)

            assert lower is None or lower < node.ticket_id
            assert upper is None or node.ticket_id < upper
            assert (
                parent_priority is None
                or parent_priority < node.random_priority
            ), "Min-heap random của treap bị sai"

            left_size = visit(
                node.left, lower, node.ticket_id,
                node.random_priority,
            )
            right_size = visit(
                node.right, node.ticket_id, upper,
                node.random_priority,
            )

            expected = 1 + left_size + right_size
            assert node.size == expected, "Sai subtree_size"
            return expected

        counted = visit(self.root, None, None, None)
        assert counted == len(self) == len(seen)
```

**Đặc điểm cố ý:** `IdTreap` không có trường độ khẩn nghiệp vụ. Nó lưu một tập ID có thứ tự. `range_ids` dùng đường BST để bỏ qua những nhánh nhỏ hơn biên; mỗi lần duyệt không sao chép toàn bộ node.

### 11.3. Ticket bất biến và heap entry có version

```python
@dataclass(frozen=True, slots=True)
class Ticket:
    ticket_id: int
    business_priority: int
    created_sequence: int
    generation: int = 0


# Entry = (business_priority, creation_order, ticket_id, generation).
# Ba phần đầu thực hiện so sánh nghiệp vụ, phần cuối chỉ kiểm tra cũ/mới.
QueueEntry = tuple[int, int, int, int]


class TicketBoard:
    """Hai chỉ mục trên cùng tập Ticket đang hoạt động."""

    def __init__(self, seed: int = 2026) -> None:
        self._records: dict[int, Ticket] = {}
        self._id_index = IdTreap(seed=seed)
        self._business_heap: list[QueueEntry] = []
        self._creation_orders = itertools.count()

    @staticmethod
    def _check_id(ticket_id: int) -> None:
        if type(ticket_id) is not int or ticket_id < 0:
            raise ValueError("ticket_id phải là int không âm")

    @staticmethod
    def _check_priority(priority: int) -> None:
        if type(priority) is not int or priority < 0:
            raise ValueError("Độ khẩn phải là int không âm")

    @staticmethod
    def _heap_entry(ticket: Ticket) -> QueueEntry:
        return (
            ticket.business_priority,
            ticket.created_sequence,
            ticket.ticket_id,
            ticket.generation,
        )

    def __len__(self) -> int:
        return len(self._records)

    def get(self, ticket_id: int) -> Ticket | None:
        self._check_id(ticket_id)
        return self._records.get(ticket_id)

    def add(self, ticket_id: int, business_priority: int) -> None:
        """Thêm một ticket; ID trùng bị từ chối."""
        self._check_id(ticket_id)
        self._check_priority(business_priority)

        if ticket_id in self._records:
            raise ValueError("ID đã tồn tại")

        created = next(self._creation_orders)
        ticket = Ticket(
            ticket_id=ticket_id,
            business_priority=business_priority,
            created_sequence=created,
        )

        inserted = self._id_index.add(ticket_id)
        if not inserted:
            raise AssertionError("Treap ID và records không nhất quán")

        self._records[ticket_id] = ticket
        heapq.heappush(self._business_heap, self._heap_entry(ticket))

    def change_priority(
        self, ticket_id: int, new_priority: int
    ) -> bool:
        """True nếu ID tồn tại; False nếu ID vắng."""
        self._check_id(ticket_id)
        self._check_priority(new_priority)

        old = self._records.get(ticket_id)
        if old is None:
            return False

        if old.business_priority == new_priority:
            return True  # Không tạo entry mới không cần thiết.

        current = replace(
            old,
            business_priority=new_priority,
            generation=old.generation + 1,
        )

        # Push trước khi commit record: nếu push thất bại,
        # record và entry cũ còn nhất quán ở mức nghiệp vụ.
        heapq.heappush(self._business_heap, self._heap_entry(current))
        self._records[ticket_id] = current
        # Đặc biệt: KHÔNG sửa _id_index hoặc random_priority.
        return True

    def cancel(self, ticket_id: int) -> bool:
        """Xóa ticket; entry cũ trên heap thành stale."""
        self._check_id(ticket_id)
        if ticket_id not in self._records:
            return False

        removed = self._id_index.discard(ticket_id)
        if not removed:
            raise AssertionError("Thiếu ID trong treap")

        del self._records[ticket_id]
        return True

    def _is_live_entry(self, entry: QueueEntry) -> bool:
        ticket = self._records.get(entry[2])
        return (
            ticket is not None
            and self._heap_entry(ticket) == entry
        )

    def _purge_stale_top(self) -> None:
        while (
            self._business_heap
            and not self._is_live_entry(self._business_heap[0])
        ):
            heapq.heappop(self._business_heap)

    def peek_next(self) -> Ticket | None:
        """Ticket khẩn nhất hiện tại; không xóa khỏi backlog."""
        self._purge_stale_top()
        if not self._business_heap:
            return None

        entry = self._business_heap[0]
        ticket = self._records[entry[2]]
        assert self._heap_entry(ticket) == entry
        return ticket

    def pop_next(self) -> Ticket | None:
        """Lấy và gỡ ticket có business key nhỏ nhất."""
        self._purge_stale_top()
        if not self._business_heap:
            return None

        entry = heapq.heappop(self._business_heap)
        ticket = self._records[entry[2]]

        removed = self._id_index.discard(ticket.ticket_id)
        if not removed:
            raise AssertionError("Thiếu ID được chọn trong treap")

        del self._records[ticket.ticket_id]
        return ticket

    def tickets_by_id(
        self, low: int, high: int
    ) -> list[Ticket]:
        """Đọc [low,high) theo ID; không sắp xếp theo độ khẩn."""
        self._check_id(low)
        self._check_id(high)
        return [
            self._records[ticket_id]
            for ticket_id in self._id_index.range_ids(low, high)
        ]

    def all_ids(self) -> list[int]:
        return list(self._id_index.keys())

    def count_id_range(self, low: int, high: int) -> int:
        self._check_id(low)
        self._check_id(high)
        if low >= high:
            return 0
        return self._id_index.rank(high) - self._id_index.rank(low)

    def compact_heap(self) -> int:
        """Loại stale entries; O(n) dựng lại heap nghiệp vụ."""
        before = len(self._business_heap)
        entries = [
            self._heap_entry(ticket)
            for ticket in self._records.values()
        ]
        heapq.heapify(entries)
        self._business_heap = entries
        return before - len(entries)

    def heap_entry_count(self) -> int:
        """Bao gồm cả entry stale chưa được dọn."""
        return len(self._business_heap)
```

Ở đây **không có hai nguồn sự thật cho business priority**: dictionary chứa record hiện tại, heap entry có thể cũ và phải đối chiếu với dictionary trước khi trả kết quả.

Một điểm dễ bị bỏ qua: việc tạo lại một ticket mang cùng ID sau khi hủy **không** làm entry cũ hợp lệ trở lại, vì `created_sequence` tăng và được đối chiếu đầy đủ cùng priority/generation. Chỉ kiểm tra `id` và `generation` (nếu generation reset về 0) có thể mắc lỗi **“hồi sinh entry cũ”**.

### 11.4. Validator liên chỉ mục

Thêm phương thức sau **bên trong lớp `TicketBoard`**:

```python
    def assert_valid(self) -> None:
        """Dùng trong test/debug, O(n+m), m=heap entries."""
        self._id_index.assert_valid()

        ids_from_tree = self.all_ids()
        ids_from_records = sorted(self._records)

        assert ids_from_tree == ids_from_records
        assert len(ids_from_tree) == len(self._records)
        assert len(set(ids_from_tree)) == len(ids_from_tree)

        # Mỗi record active có chính xác một heap entry hợp lệ.
        live_entries: list[QueueEntry] = []
        for entry in self._business_heap:
            if self._is_live_entry(entry):
                live_entries.append(entry)

        assert len(live_entries) == len(self._records)
        assert len(set(live_entries)) == len(live_entries)
        assert {
            entry[2] for entry in live_entries
        } == set(self._records)

        assert all(
            ticket.ticket_id == ticket_id
            and ticket.generation >= 0
            for ticket_id, ticket in self._records.items()
        )

        if live_entries:
            # Đối chiếu độc lập business key từ nguồn sự thật.
            best = min(
                self._records.values(),
                key=lambda t: (
                    t.business_priority,
                    t.created_sequence,
                    t.ticket_id,
                ),
            )
            assert min(live_entries) == self._heap_entry(best)
```

Validator này kiểm tra **bất biến của cả hai chỉ mục**, không chỉ treap. Đặc biệt, mỗi ID còn trong dictionary phải có một entry heap đang hợp lệ; nếu một lần thay đổi business priority quên push entry mới, kiểm tra sẽ phát hiện.

**Vì sao không gọi `peek_next` trong validator?** Phương thức `peek_next` có thể dọn stale entries ở đỉnh, tức **sửa heap**. Một validator chỉ đọc dễ phân tích hơn khi có test gây lỗi, và không che khuất một số vấn đề do tự động dọn entry.

### 11.5. Demo kết hợp cả hai thứ tự

Ghép các khối mã trong Mục 11.1–11.4 vào cùng một file; phương thức `assert_valid` ở Mục 11.4 cần thụt **bốn khoảng trắng bên trong class `TicketBoard`**.

```python
def demo() -> None:
    board = TicketBoard(seed=2026)

    board.add(120, 1)
    board.add(150, 5)
    board.add(180, 2)
    board.assert_valid()

    # Thứ tự ID khác thứ tự khẩn cấp.
    assert board.all_ids() == [120, 150, 180]
    assert [
        t.ticket_id for t in board.tickets_by_id(120, 180)
    ] == [120, 150]
    assert board.count_id_range(120, 181) == 3

    urgent = board.peek_next()
    assert urgent is not None and urgent.ticket_id == 120

    # Nâng ID 150 thành ưu tiên nghiệp vụ tốt nhất.
    changed = board.change_priority(150, 0)
    assert changed
    board.assert_valid()
    assert board.all_ids() == [120, 150, 180]

    next_ticket = board.peek_next()
    assert next_ticket is not None and next_ticket.ticket_id == 150

    served = board.pop_next()
    assert served is not None and served.ticket_id == 150
    board.assert_valid()
    assert board.all_ids() == [120, 180]

    cancelled = board.cancel(120)
    cancelled_again = board.cancel(120)
    assert cancelled and not cancelled_again
    board.assert_valid()
    assert board.peek_next() is not None
    assert board.peek_next().ticket_id == 180

    board.compact_heap()
    board.assert_valid()

    last = board.pop_next()
    assert last is not None and last.ticket_id == 180
    assert board.peek_next() is None
    assert len(board) == 0
    board.assert_valid()
    print("Two-index ticket board: OK")


if __name__ == "__main__":
    demo()
```

**Ý nghĩa chính:** thứ tự `all_ids()` không đổi sau khi ticket 150 được nâng mức khẩn, vì chỉ mục treap theo ID không cần sửa. Nhưng `peek_next()` chuyển từ ID 120 sang ID 150, chứng tỏ heap nghiệp vụ đã được cập nhật đúng.


## 12. Kiểm thử các ngữ nghĩa nghiệp vụ cốt lõi

Không chỉ kiểm tra `assert_valid` của treap, bài học này cần test **thứ tự phục vụ** như một điều kiện đúng đắn độc lập. Mã trong mục này tiếp nối các định nghĩa ở Mục 11; chúng không yêu cầu thư viện kiểm thử bên thứ ba.

### 12.1. Cùng độ khẩn phải FIFO theo thời điểm tạo

Giả sử tất cả ticket có business priority 2, nhưng ID không được tạo theo thứ tự tăng:

```python
def test_business_ties() -> None:
    board = TicketBoard(seed=77)

    board.add(900, 2)  # Được tạo trước.
    board.add(100, 2)
    board.add(500, 2)
    board.assert_valid()

    # Chỉ mục ID có thứ tự tăng, KHÔNG là thứ tự xử lý.
    assert board.all_ids() == [100, 500, 900]

    # Tie-break của business heap là created_sequence.
    served = []
    for _ in range(3):
        ticket = board.pop_next()
        assert ticket is not None
        served.append(ticket.ticket_id)

    assert served == [900, 100, 500]
    assert len(board) == 0
    board.assert_valid()


test_business_ties()
```

Nếu ta thay `created_sequence` bằng `random_priority` của treap trong heap nghiệp vụ, bộ test trên có thể thất bại dù các phép quay của treap đều đúng. Chính sách tie được xác định bởi **sản phẩm**, không được âm thầm phụ thuộc vào seed.

### 12.2. Chỉnh business priority không được chỉnh random priority

```python
def random_priority_map(index: IdTreap) -> dict[int, tuple[int, int]]:
    """Dùng trong test: chụp key kỹ thuật của mọi node."""
    out: dict[int, tuple[int, int]] = {}
    stack = [index.root]

    while stack:
        node = stack.pop()
        if node is None:
            continue

        out[node.ticket_id] = node.random_priority
        stack.extend((node.left, node.right))

    return out


def test_priority_update_is_isolated() -> None:
    board = TicketBoard(seed=123)

    for ticket_id, p in ((40, 5), (20, 3), (60, 2), (10, 8)):
        board.add(ticket_id, p)

    before_ids = board.all_ids()
    before_random = random_priority_map(board._id_index)
    old_next = board.peek_next()
    assert old_next is not None and old_next.ticket_id == 60

    changed = board.change_priority(10, 0)
    assert changed

    # Treap chỉ mục ID không hề thay đổi.
    assert board.all_ids() == before_ids
    assert random_priority_map(board._id_index) == before_random

    # Nhưng ngữ nghĩa business đã đổi đúng.
    new_next = board.peek_next()
    assert new_next is not None and new_next.ticket_id == 10
    assert board.get(10) is not None
    assert board.get(10).business_priority == 0
    board.assert_valid()


test_priority_update_is_isolated()
```

Test này tách **hai dạng cập nhật**: business key có thay đổi, random key định hình cây thì không.

### 12.3. Hủy rồi tái sử dụng cùng ID

Một bug quen thuộc của lazy invalidation: ticket ID 7 bị hủy rồi tạo lại, phiên bản mới quay về generation 0. Nếu chỉ kiểm tra ID và generation, entry cũ có thể bị nhận nhầm là hợp lệ.

Mã bài kiểm tra cả `created_sequence`:

```python
def test_reuse_id_does_not_revive_stale_entry() -> None:
    board = TicketBoard(seed=2026)

    board.add(7, 1)
    board.add(8, 3)

    cancelled = board.cancel(7)
    assert cancelled

    # ID 7 mới có created_sequence khác, dù generation lại là 0.
    board.add(7, 9)

    first = board.pop_next()
    second = board.pop_next()

    assert first is not None and first.ticket_id == 8
    assert second is not None and second.ticket_id == 7
    assert second.business_priority == 9
    assert board.pop_next() is None

    board.assert_valid()


test_reuse_id_does_not_revive_stale_entry()
```

Entry cũ của ID 7 có business priority 1, nên nếu nó được “hồi sinh”, ticket ID 7 sẽ bị phục vụ trước ID 8, sai nghiêm trọng. Bộ test này trực tiếp phát hiện lỗi đó.

### 12.4. Nhiều lần thay độ khẩn rồi compact

```python
def test_stale_entries_and_compaction() -> None:
    board = TicketBoard(seed=15)
    board.add(1, 5)
    board.add(2, 2)

    for i in range(30):
        new_priority = 1 if i % 2 == 0 else 9
        changed = board.change_priority(1, new_priority)
        assert changed

    assert board.heap_entry_count() > len(board)
    board.assert_valid()

    removed_entries = board.compact_heap()
    assert removed_entries > 0
    assert board.heap_entry_count() == len(board)
    board.assert_valid()

    # Lượt cập nhật cuối đặt ID 1 ở mức 9.
    top = board.peek_next()
    assert top is not None and top.ticket_id == 2


test_stale_entries_and_compaction()
```

Compaction xây lại heap từ **record hiện tại**. Nó xóa các entry stale, không sửa random priority trong treap, và có chi phí O(n) cho lần rebuild. Vì vậy nếu một API chọn tự compact theo ngưỡng, phải tính cả spike O(n) vào phân tích độ trễ.

### 12.5. Đầu vào sai kiểu hoặc âm

```python
def test_invalid_business_values() -> None:
    board = TicketBoard()

    rejected = 0
    for bad_priority in (-1, True, "urgent", 1.5):
        try:
            board.add(100 + rejected, bad_priority)
        except ValueError:
            rejected += 1

    assert rejected == 4
    assert len(board) == 0


test_invalid_business_values()
```

Ví dụ sử dụng **integer không âm** để tránh các vấn đề comparator như `NaN` trong floating-point. Với hệ thống thật, domain có thể dùng enum như `P0,P1,P2,P3`, deadline với timezone rõ ràng hoặc score cấu thành từ nhiều trường. Comparator phải nhất quán, có thứ tự đầy đủ theo hợp đồng.

## 13. Kiểm thử dài với một mô hình tham chiếu độc lập

Ta có thể chạy nhiều thao tác add, update, cancel và pop, rồi so với một mô hình Python đơn giản. Ở mô hình này, dùng dictionary lưu `(priority, created_sequence)` và tính ticket tiếp theo bằng `min` trên toàn tập. Mô hình tham chiếu có thể chậm O(n) nhưng dễ hiểu và độc lập về cách cài đặt heap/treap.

```python
def test_workload(seed: int) -> None:
    rng = random.Random(100000 + seed)
    board = TicketBoard(seed=seed)

    # id -> (business_priority, created_sequence)
    reference: dict[int, tuple[int, int]] = {}
    next_created = 0

    for step in range(500):
        ticket_id = rng.randrange(1, 71)
        action = rng.randrange(4)

        if action == 0:  # Add nếu chưa có.
            if ticket_id not in reference:
                priority = rng.randrange(0, 8)
                board.add(ticket_id, priority)
                reference[ticket_id] = (priority, next_created)
                next_created += 1

        elif action == 1:  # Update mức khẩn.
            priority = rng.randrange(0, 8)
            was_present = ticket_id in reference
            changed = board.change_priority(ticket_id, priority)
            assert changed == was_present

            if was_present:
                _, created = reference[ticket_id]
                reference[ticket_id] = (priority, created)

        elif action == 2:  # Cancel.
            was_present = ticket_id in reference
            cancelled = board.cancel(ticket_id)
            assert cancelled == was_present
            reference.pop(ticket_id, None)

        else:  # Lấy ticket tốt nhất theo business key.
            popped = board.pop_next()

            if not reference:
                assert popped is None
            else:
                expected_id = min(
                    reference,
                    key=lambda i: (
                        reference[i][0],
                        reference[i][1],
                        i,
                    ),
                )
                assert popped is not None
                assert popped.ticket_id == expected_id
                assert popped.business_priority == reference[expected_id][0]
                del reference[expected_id]

        # Sau MỌI bước: hai chỉ mục phải nhất quán.
        board.assert_valid()
        assert board.all_ids() == sorted(reference)
        assert len(board) == len(reference)

        best = board.peek_next()
        if reference:
            expected_id = min(
                reference,
                key=lambda i: (
                    reference[i][0],
                    reference[i][1],
                    i,
                ),
            )
            assert best is not None and best.ticket_id == expected_id
        else:
            assert best is None

        if step % 73 == 0:
            removed = board.compact_heap()
            assert removed >= 0
            board.assert_valid()


for seed in range(10):
    test_workload(seed)
```

Đây là một kiểu **property-based test thủ công**: nhiều chuỗi cập nhật khác nhau phải duy trì tính đúng. Nó không chứng minh hệ thống là transaction-safe khi hết bộ nhớ, không chứng minh mọi trường hợp concurrency, và không suy ra một chặn worst-case O(log n) từ 10 seed.

### 13.1. Vì sao nên tách RNG tạo workload khỏi RNG của treap?

Nếu test sử dụng cùng một PRNG cho cả việc chọn ticket nào được cập nhật lẫn việc bốc priority của treap, một thay đổi trong số lần rút random của treap có thể **đổi cả chuỗi thao tác kiểm thử**, khiến khó tái lập lỗi.

Mô phỏng dùng:

- `rng` bên ngoài để quyết định thao tác/ID/priority nghiệp vụ kiểm thử;
- `IdTreap.rng` để định hình cây.

Đây là tách **nguồn random kỹ thuật**, vẫn không làm PRNG nội bộ trở thành nguồn mật mã.

## 14. Cập nhật hai chỉ mục như một giao dịch logic

Mã minh họa ở Mục 11 thực hiện các lệnh tuần tự, thích hợp để giải thích dữ liệu. Nhưng cập nhật nhiều index trong production còn cần **tính nguyên tử**.

### 14.1. Rủi ro khi add thất bại giữa chừng

Ví dụ:

```text
index_by_id.add(ticket_id)     # Đã thành công
records[ticket_id] = ticket    # Đã thành công
heap.push(entry)               # Thất bại vì hết bộ nhớ
```

Khi đó ID có trong treap và dictionary nhưng không có entry hợp lệ trong heap. Kết quả `peek_next` không còn đại diện cho toàn bộ backlog. Bất biến liên chỉ mục bị phá dù **mỗi cấu trúc riêng lẻ có thể vẫn hợp lệ**.

### 14.2. Rủi ro khi pop thất bại giữa chừng

```text
entry = heap.pop()               # Đã loại entry hợp lệ
treap.discard(entry.ticket_id)   # Gặp lỗi do recursion/allocator ...
records.pop(entry.ticket_id)     # Chưa chạy
```

Dictionary vẫn còn ticket nhưng heap đã mất entry hợp lệ; tác vụ có thể trở thành **không bao giờ được phục vụ** nếu không có phục hồi.

Điều này cho thấy “chương trình đã dùng hai cấu trúc đúng” **chưa đủ để đảm bảo nghiệp vụ đúng qua lỗi runtime**.

### 14.3. Một vài hướng thiết kế giao dịch

- Dùng **lock** bảo vệ mọi thay đổi và các truy vấn cần snapshot nhất quán trong cùng process.
- Chuẩn bị dữ liệu có thể cấp phát lỗi **trước** khi thay nhiều chỉ mục, nếu khả thi.
- Nếu update có thể lỗi giữa chừng, dùng **rollback** có chứng minh các hành động hoàn tác.
- Xây các chỉ mục **immutable/persistent** cho phiên bản mới, rồi atomic-publish một state object chứa cả các root.
- Với dữ liệu bền vững, dùng database transaction/log sự kiện cùng quy trình phục hồi sau crash; không coi transaction trong bộ nhớ là thay thế durability.
- Thêm công cụ **rebuild index từ nguồn sự thật** và chạy kiểm tra nhất quán sau recovery.

Một mutex ngăn thread thấy trạng thái trung gian, nhưng **không tự phục hồi** các chỉ mục khi một exception đã xảy ra bên trong vùng khóa. Cần hai loại bảo đảm riêng.

### 14.4. Không dùng optimistic version như một lock

`generation` trong heap entry chỉ nhận biết phiên bản **nghiệp vụ của một ticket**. Nó không cung cấp mutual exclusion cho treap và heap, không ngăn race giữa `get` và `cancel`, và không bảo vệ iterator đang giữ con trỏ node.

Một concurrent data structure cần mô hình riêng về atomic update, memory ordering, snapshot/linearization và thu hồi node. Mã Python trong bài **cố tình đơn luồng**.

## 15. Độ phức tạp tổng hợp của giải pháp hai chỉ mục

Đặt:

- `n` = số ticket đang hoạt động trong dictionary và treap ID;
- `m` = tổng số entry còn nằm trong heap nghiệp vụ, bao gồm stale entries;
- `k` = số ticket cần xuất trong một khoảng ID;
- `s` = số entry stale đứng trên đỉnh heap mà một lần peek/pop phải bỏ;
- `h` = chiều cao thực tế của treap.

| Thao tác | Treap theo ID | Business heap / dict | Nhận xét |
| --- | --- | --- | --- |
| `get(id)` | Không cần | Dict O(1) kỳ vọng | Không cần treap nếu chỉ đọc ID |
| `add(id,p)` | O(h) | Dict + heap push O(log(m+1)) | Treap O(log n) kỳ vọng |
| `change_priority(id,p)` | Không sửa cây | Dict + push O(log(m+1)) | Entry cũ stale |
| `cancel(id)` | O(h) | Dict remove O(1) kỳ vọng | Heap cũ lazy |
| `peek_next()` | Không cần | O((s+1)log(m+1)) chặn thô | Có thể phải bỏ nhiều stale |
| `pop_next()` | O(h) để xóa ID | O((s+1)log(m+1)) chặn thô + dict | Một ticket hợp lệ được xóa khỏi cả hai index |
| `tickets_by_id(lo,hi)` | O(h+k) | k lượt dict lookup | Expected O(log n+k) |
| `count_id_range(lo,hi)` | O(h) qua 2 rank | Không cần | Expected O(log n) |
| `compact_heap()` | Không sửa | O(n) heapify | Xóa stale entries, có spike |
| `assert_valid()` | O(n) | O(n+m) | Chỉ test/debug |

**Chi phí `peek_next`:** nếu không cần bỏ stale và đỉnh đang hợp lệ, peek heap là O(1) để đọc entry; bảng dùng O(log(m+1)) như một **chặn trên thô** có tính cả thao tác cleanup. Một lần bỏ nhiều stale có thể tốn Θ(s log m) theo chặn trên; không suy ra worst-case O(1).

**Bộ nhớ:** treap O(n) node, dictionary O(n) record, business heap O(m) entry. Nếu cập nhật priority liên tục không làm gọn heap, `m` có thể lớn hơn `n` tùy ý trong một chuỗi lịch sử dài.

### 15.1. Expected là của thao tác nào và dưới phân phối nào?

Treap random dùng priority độc lập với key để có expected O(log n) cho đường tìm/chèn/xóa. Heap nghiệp vụ không cần ngẫu nhiên; `heapq` duy trì bất biến heap bằng `sift` với **O(log m) worst-case** cho một lần push/pop trên m entry, trong mô hình so sánh O(1).

Trong cùng một thao tác `pop_next`, tổng chi phí còn gồm:

- Dọn stale entries của heap;
- Xóa ID khỏi treap;
- Cập nhật dictionary;
- Có thể thêm logging/persistence/business action.

Không được lấy chặn expected của một thành phần để cam kết **toàn bộ lời gọi** có worst-case O(log n).

### 15.2. Nếu chỉ cần một thứ tự nghiệp vụ

Nếu không cần range theo ID, có thể bỏ treap ID. Một dictionary + heap (hoặc indexed heap) sẽ đơn giản hơn:

- Lookup theo ID: dict;
- Pop theo business key: heap;
- Update: indexed heap hoặc lazy invalidation;
- Chỉ mục thứ hai theo ID không cần thiết.

Nếu muốn **vừa** lấy theo business order **vừa** hỗ trợ range theo business score, có thể dùng ordered map/treap với **BST key composite business key**, còn random priority vẫn riêng, cộng dictionary ID→composite key để cập nhật. Đó là một lựa chọn kiến trúc khác với hai chỉ mục trong ví dụ.


## 16. Các kiến trúc thay thế và cách ra quyết định

Không phải lúc nào mô hình `treap + heap + dict` cũng tối ưu. Hãy tách rõ **những truy vấn bắt buộc** với các thao tác “có thể sau này cần”.

### 16.1. Chỉ cần ID lookup và lấy ticket khẩn nhất

Lựa chọn:

```text
dict[id] -> Ticket
indexed_min_heap[ (business_priority, created_seq, id) ]
position[id] -> heap index
```

Không cần treap. Lookup ID thường O(1) kỳ vọng; sửa key nghiệp vụ và pop O(log n) worst-case trên heap nếu `position` được cập nhật đúng. Dữ liệu trong heap phải đối chiếu với dict hoặc chứa reference hợp lệ, và nếu hai cấu trúc cùng được sửa thì vẫn có vấn đề transaction.

### 16.2. Cần range theo ID và lấy phiếu khẩn nhất

Chọn:

```text
treap/AVL/red-black by ID
+
min-heap/indexed heap by business key
+
dict records
```

Nếu yêu cầu **worst-case tìm theo ID O(log n)** cho mỗi thao tác, cây AVL/red-black phù hợp hơn treap randomized. Treap chỉ hứa O(log n) expected trong mô hình random thích hợp.

### 16.3. Cần lấy và phân trang theo chính độ khẩn

Có thể dùng cây có thứ tự theo composite key:

\[
K=(business\_priority,\ created\_sequence,\ id).
\]

Một treap cho K có hai trường tách biệt:

```text
Node.key              = (business_priority, created_sequence, id)
Node.random_priority  = RNG()
```

Như vậy inorder thực sự sắp theo độ khẩn. Nếu business priority thay đổi, phải:

1. Tìm bản ghi bằng ID qua dictionary hoặc index ID.
2. Xóa **composite key cũ** khỏi treap.
3. Thay record nghiệp vụ.
4. Chèn **composite key mới**.
5. Giữ bất biến liên chỉ mục và cập nhật transaction phù hợp.

**Không được** chỉ thay phần business priority trong `Node.key` đang nằm giữa cây, vì điều đó có thể phá BST. Ngẫu nhiên ở `Node.random_priority` vẫn là khái niệm độc lập.

### 16.4. Cần điểm khẩn nhất nhưng muốn chỉ một treap

Có thể chọn treap theo ID với metadata:

```text
subtree_best_business_key
subtree_best_ticket_id
```

Dưới giả định metadata được duy trì đúng, root cho biết ticket có business key tốt nhất; truy ngược node tương ứng có thể thực hiện theo những metadata đó. Tuy nhiên, khi business priority của một ticket thay đổi, cần tìm đường từ root đến node ID và **cập nhật metadata của mọi tổ tiên**, O(h). Nếu chỉ sửa payload trong dictionary mà bỏ bước ấy, root giữ thông tin cũ.

Cách này có thể tiết kiệm một heap riêng và không có stale entries, nhưng đòi code `pull`, cập nhật payload và xóa node cẩn thận. Nếu có nhiều quy tắc nghiệp vụ thay đổi động theo thời gian, duy trì aggregate có thể không đơn giản.

### 16.5. Một bảng quyết định

| Yêu cầu nổi bật | Nên cân nhắc | Không nên suy diễn |
| --- | --- | --- |
| Exact-key lookup theo ID | Hash map | Có hash map là hỗ trợ range ID |
| Range ID + update thường xuyên | AVL/red-black hoặc treap by ID | Random treap có worst-case O(log n) |
| Lấy khẩn nhất + chỉnh điểm thường xuyên | Indexed heap | Priority ngẫu nhiên treap là business key |
| Lấy khẩn nhất + ít update, muốn code ngắn | Heapq + lazy invalidation | Mọi peek worst O(1) |
| Phân trang theo business priority | Ordered index theo composite business key | Sorted theo ID cũng sorted theo business key |
| Deadline cứng cho tìm theo thứ tự | Cấu trúc có bảo đảm worst-case phù hợp | Benchmark trung bình đủ chứng minh deadline |
| Chạy nhiều thread/worker | Index có transaction/lock, dữ liệu bền vững | GIL hoặc generation đủ cho atomicity |
| Khả năng chống starvation | Chính sách aging/weighted scheduling | Random treap tự bảo đảm fairness |

## 17. Những sai lầm cần phát hiện khi review code

| Phát biểu hoặc đoạn code | Sai ở đâu? | Cách sửa |
| --- | --- | --- |
| `node.priority = ticket.business_priority` trong treap theo ID | Priority kỹ thuật không còn random độc lập | Dùng hai trường riêng |
| `next_job = treap.root.ticket` | Root có random priority tốt nhất, không phải khẩn nhất | Lấy từ business index |
| `for node in treap.inorder(): ...` rồi gọi đó là priority order | Inorder sắp theo ID | Ordered index theo business key |
| `business_priority = random()` để quyết định SLA | Ngẫu nhiên không đại diện quy tắc nghiệp vụ | Định nghĩa severity, deadline, fairness |
| `priority_random = hash(id)` và mặc định IID | Hash tất định không tự thỏa mọi giả định random | Chứng minh mô hình hash hoặc bốc random đúng |
| `priority_random = created_sequence` | Tương quan thứ tự chèn/ID, dễ lệch | Giữ priority nội bộ được random hóa |
| Gọi `change_priority` rồi quay treap theo ID | Không cần; có thể phá cấu trúc nếu làm sai | Chỉ cập nhật business index/aggregate |
| Chỉ sửa `Ticket.business_priority`, quên heap | Heap còn entry cũ đứng đầu | Indexed update hoặc generation+push |
| Xóa ticket khỏi dict nhưng không vô hiệu heap | Pop có thể trả công việc đã hủy | Kiểm tra record hiện tại khi pop |
| Reuse ID và chỉ so `(id,generation)` | Entry cũ generation 0 có thể “hồi sinh” | Dùng creation/order token độc nhất |
| Dùng random priority làm tie-break FIFO | Phá thứ tự ổn định với cùng độ khẩn | Dùng created_sequence |
| Dùng ID làm tie-break FIFO | ID có thể không theo thứ tự tạo | Lưu creation order riêng |
| Business score đổi theo thời gian nhưng heap không được refresh | Thứ tự nghiệp vụ trở nên stale | Aging scheduler/reheapify theo lịch |
| Dùng floating priority có `NaN` | Comparator có thể không có thứ tự toàn phần | Chuẩn hóa/loại NaN, comparator rõ |
| Gọi `heapq.heappush` trong `assert` | Với `python -O`, lệnh mất tác dụng | Gọi thao tác riêng, assert kiểm chứng |
| Dùng `heapq` rồi hứa update arbitrary ID O(log n) | Heap chuẩn không có map vị trí | Indexed heap hoặc lazy invalidation |
| Tính O(log n) heap theo n active dù có m stale | m có thể lớn hơn n | Phân tích theo m, compact khi cần |
| Nói `peek_next` luôn O(1) | Có thể dọn nhiều stale entries | Phân biệt peek thuần với cleanup |
| Dựa vào kiểm tra riêng treap để xác nhận backlog đúng | Business index có thể thiếu record | Validator liên chỉ mục |
| Coi `generation` là mutex | Không ngăn race giữa hai index | Transaction/lock/snapshot |
| Dùng treap cho mọi nhiệm vụ vì tên có “heap” | Bỏ qua workload thực tế | Chọn theo thao tác cần |
| Dựa vào expected O(log n) của treap để hứa mọi request nhanh | Worst-case cây lệch và hệ thống nhiều thành phần | Chọn bảo đảm phù hợp |

### 17.1. Một quy trình code review theo bốn câu hỏi

1. **Key BST là gì?** ID, business priority hay composite key? Các truy vấn inorder thực sự sắp theo trường nào?
2. **Heap priority dùng để làm gì?** Định hình treap bằng random hay chọn công việc theo nghiệp vụ?
3. **Cập nhật nào ảnh hưởng chỉ mục nào?** Nếu đổi ID, sửa business priority hoặc xóa ticket thì phải cập nhật những cấu trúc nào?
4. **Bảo đảm nào được chứng minh?** Tính đúng sau update, expected performance, worst-case, consistency trước lỗi, hay fairness? Không được thay một loại bảo đảm bằng loại khác.

### 17.2. Quy trình debug khi “lấy nhầm ticket khẩn nhất”

Giả sử `peek_next()` trả ID 150 có độ khẩn 5, trong khi ID 120 có độ khẩn 1.

Hãy kiểm tra theo thứ tự:

- Định nghĩa “số nhỏ hơn là khẩn hơn” có được dùng đúng ở mọi nơi không?
- Ticket ID 120 có đang hoạt động trong dict không?
- Heap có một entry hợp lệ cho ID 120 không?
- Entry có `created_sequence` và `generation` trùng record không?
- Heap có stale entry bị hiểu nhầm là hợp lệ không?
- Đã gọi `heappush` sau khi sửa độ khẩn chưa?
- Có đang lấy `treap.root` thay vì business heap không?
- Nếu có nhiều thread, bản ghi và heap có cùng snapshot không?

Không nên sửa lỗi bằng cách **đổi random priority của các node treap**, vì đó không phải nguồn quyết định thứ tự nghiệp vụ.

### 17.3. Mô hình hai chỉ mục vẫn cần một hợp đồng định lượng

Một đặc tả có thể viết:

> Ở trạng thái không có cập nhật đồng thời, `pop_next` phải trả record đang hoạt động có business key nhỏ nhất trong tập tại thời điểm chọn. Tập ID của record đang hoạt động phải bằng tập ID của chỉ mục treap. Những entry heap có version cũ phải bị bỏ qua.

Đó là **hợp đồng correctness**. Nếu muốn thêm SLO độ trễ hay deadline thực, phải đo và phân tích cấu trúc, m stale entries, lock, GC, lưu trữ và tải hệ thống riêng.


## 18. Bài tập có lời giải

### Bài 1. Ba loại thứ tự cùng lúc

Một hệ thống có ba ticket: ID 200 với business priority 2, ID 100 với priority 5, ID 300 với priority 0. Treap dùng `id` làm BST key và priority ngẫu nhiên riêng. Inorder treap theo ID là gì? Thứ tự xử lý nghiệp vụ là gì?

**Lời giải:** Inorder ID: **100, 200, 300**. Thứ tự nghiệp vụ (số nhỏ hơn khẩn hơn): **300, 200, 100**. Random priority không xuất hiện trong hai kết quả này; nó chỉ ảnh hưởng hình dạng treap.

### Bài 2. Gốc treap không phải việc khẩn nhất

Cho ba node `(id,random_priority)` là `(120,80),(150,10),(180,50)`. Ticket ID120 có business priority1, ID150 có 5, ID180 có 2. Root treap và ticket cần phục vụ đầu là gì?

**Lời giải:** Root treap là **ID 150** vì random priority10 nhỏ nhất. Ticket cần phục vụ đầu là **ID 120** vì business priority1 nhỏ nhất. Hai tiêu chí hoàn toàn độc lập.

### Bài 3. Quay treap có thay đổi thứ tự nghiệp vụ?

Một lần chèn ID mới làm treap quay trái hai lần. Không có ticket nào được đổi business priority. Thứ tự xử lý của các ticket đã có theo business key có tự thay đổi không?

**Lời giải:** **Không**, nếu business key của các ticket cũ không đổi. Phép quay chỉ đổi hình dạng treap, bảo toàn key và payload. Nếu ticket mới có business key tốt hơn, thứ tự nghiệp vụ toàn tập thay đổi do **thêm một ticket**, không phải do phép quay.

### Bài 4. Vì sao lấy treap root để phân phối công việc là sai?

Một lập trình viên viết `next_job=treap.root` vì root “có priority tốt nhất”. Vì sao sai?

**Lời giải:** Root có **random priority tốt nhất** của cấu trúc treap, không phải **business priority tốt nhất** của công việc. Phải dùng heap/sorted index nghiệp vụ hoặc metadata subtree_best đã được duy trì đúng.

### Bài 5. Mức độ khẩn bằng nhau thì ai trước?

Ba ticket cùng business priority2 được tạo lần lượt ID900, ID100, ID500. Chính sách FIFO theo thứ tự tạo. Thứ tự xử lý là gì?

**Lời giải:** **900,100,500**. Thứ tự ID tăng lại là 100,500,900. Tie-breaker nghiệp vụ phải là `created_sequence`, không đơn giản lấy ID hoặc random priority của treap.

### Bài 6. Thay business priority có cần thay random priority không?

Treap theo ID chứa ticket ID150, random priority kỹ thuật 42, business priority5. Nâng mức khẩn thành 0. Trường nào cần đổi?

**Lời giải:** Đổi `Ticket.business_priority` từ 5 thành 0 và cập nhật **chỉ mục nghiệp vụ**. Không cần đổi `random_priority=42` hoặc quay treap theo ID; BST key cũng không thay.

### Bài 7. Thay ID khác thay độ khẩn

Ticket ID150 đang ở gốc BST có con phải ID180. Đổi ID150 thành 190 mà không di chuyển node có hợp lệ không?

**Lời giải:** Không. BST đòi mọi key cây phải lớn hơn key gốc, nhưng `180<190`. Phải remove key cũ và reinsert key mới, hoặc khóa ID bất biến theo hợp đồng. Đổi business priority không có vấn đề tương tự với BST theo ID.

### Bài 8. Vì sao business priority thường không IID?

Business priority chỉ có 4 mức P0–P3, nhiều ticket cùng mức, và loại ticket quyết định mức. Nó có phải priority IID liên tục phù hợp định lý treap không?

**Lời giải:** Không. Nó có **nhiều giá trị trùng**, có quan hệ với loại sự cố và có thể với ID/thời điểm. Không thể tự áp dụng chứng minh random treap IID liên tục cho việc dùng business priority làm heap key kỹ thuật.

### Bài 9. Priority bằng key tạo hình dạng gì?

Treap min-heap có `key=i` và `priority_treap=i` với i từ 1 đến n. Hình dạng và chiều cao?

**Lời giải:** Node key nhỏ nhất luôn có priority nhỏ nhất, trở thành root. Mọi key còn lại lớn hơn nên tạo **đường lệch phải**. Chiều cao là **n node**, tìm khóa cuối Θ(n). Cây vẫn đúng cả BST và heap.

### Bài 10. Tie-breaker serial có tạo ngẫu nhiên không?

Một hệ thống dùng `treap_priority=(business_priority,creation_order)`. Mọi ticket cùng business priority3 và ID tăng cùng thời gian tạo. Treap có tự cân đối theo kỳ vọng không?

**Lời giải:** Không thể khẳng định. Thứ tự tuple theo created_order tăng cùng ID nên có thể tạo cây lệch theo key, dù tuple không trùng. **Tạo thứ tự duy nhất** không đồng nghĩa **random độc lập**.


### Bài 11. Business priority có được làm BST key không?

Bạn muốn liệt kê ticket theo mức độ khẩn. Có thể xây treap với `key=(business_priority,created_order,id)` không?

**Lời giải:** **Có.** BST key có thể là composite business key nếu cần duyệt theo thứ tự ấy. Nhưng vẫn phải có **random_priority riêng** làm heap priority của treap; tìm theo ID cần dictionary/secondary index.

### Bài 12. Sửa key composite ngay trong cây

Một node trong treap theo composite business key có key `(5,2,150)`. Nâng độ khẩn lên 0 rồi chỉ đổi key thành `(0,2,150)` tại chỗ. Vì sao có thể sai?

**Lời giải:** Node đã ở vị trí BST cho key cũ; key mới phải có thể nằm ở nhánh khác. Phải **xóa composite key cũ rồi chèn composite key mới**, giữ bất biến BST và cập nhật index ID.

### Bài 13. Có cần treap không?

Một ứng dụng chỉ cần tra ticket theo ID, thay độ khẩn và lấy ticket khẩn nhất; không bao giờ cần duyệt ID theo thứ tự. Cấu trúc đơn giản hơn treap + heap + dict là gì?

**Lời giải:** **Dictionary/hash map + indexed heap** hoặc dictionary + heap lazy invalidation. Không cần treap ID nếu không có ordered/range/rank query theo ID.

### Bài 14. Khi nào hai chỉ mục có lợi?

Ứng dụng vừa cần liệt kê các ticket có ID trong khoảng nửa mở từ 100 tới 200, vừa cần pop ticket khẩn nhất. Bạn chọn tổ hợp nào?

**Lời giải:** Một **ordered index theo ID** (treap/AVL/red-black) cộng **priority index theo business key**, với dictionary làm nguồn sự thật. Treap theo ID không tự pop đúng business priority.

### Bài 15. Lazy invalidation sau một cập nhật

Một ticket ID150 có entry heap cũ `(5,2,150,0)`. Nâng mức khẩn thành 0, generation mới 1. Entry hợp lệ là gì và entry cũ xử lý thế nào?

**Lời giải:** Push `(0,2,150,1)`; entry cũ `(5,2,150,0)` trở thành **stale**, phải bị bỏ khi nó lên đỉnh. Không lấy entry cũ làm record hiện tại.

### Bài 16. Priority thay đi rồi quay lại

Ticket có business priority1, generation0. Sau hai cập nhật 1→5→1, entry heap cũ và mới cùng business priority1. Có thể chỉ so ID, priority và created_order để biết entry nào hợp lệ không?

**Lời giải:** Không. Phải kiểm tra thêm `generation` (và token nhận dạng vòng đời ticket). Entry cũ có generation0, mới là generation2; nếu bỏ generation, entry cũ có thể bị chấp nhận nhầm.

### Bài 17. Hủy rồi tái sử dụng cùng ID

Ticket ID7 bị hủy, sau đó tạo một ticket mới cũng ID7. Generation của cả hai lần tạo là 0. Làm sao phân biệt entry heap cũ với mới?

**Lời giải:** Dùng một **created_sequence/epoch token duy nhất cho mỗi lần tạo** và đối chiếu đầy đủ với record hiện tại. Chỉ dùng `(id,generation)` không đủ nếu generation reset khi ID được tái sử dụng.

### Bài 18. Vì sao heap có thể lớn hơn backlog?

Có n=100 ticket đang hoạt động, mỗi ticket được cập nhật priority 10 lần mà không dọn stale entries. Heap có thể chứa tối đa khoảng bao nhiêu entry chỉ từ các lần tạo và cập nhật ấy?

**Lời giải:** Ban đầu 100 entry, mỗi update push một entry mới, có 1.000 update; tổng lên tới **1.100 entry** nếu chưa pop/compact, dù chỉ có 100 ticket active. Heap memory phải tính theo `m`, không chỉ n.

### Bài 19. Một lần `peek_next` có luôn O(1) không?

Dùng heapq với lazy invalidation, m entry và s entry stale đứng trên một entry hợp lệ. Chi phí loại stale tối đa theo bậc nào?

**Lời giải:** Mỗi `heappop` tốn O(log m); bỏ s stale có chặn trên **O(s log(m+1))**. Đọc top hợp lệ sau đó O(1), nhưng toàn `peek_next` không còn worst O(1) nếu có cleanup.

### Bài 20. Compaction giúp gì và tốn bao nhiêu?

Một heap có m=10.000 entry nhưng n=500 ticket active. `compact_heap` dựng lại từ tất cả record hiện tại. Sau compact có bao nhiêu entry? Chi phí thuật toán heapify là gì?

**Lời giải:** Có **500 entry hợp lệ**, loại 9.500 stale entry nếu mỗi active có đúng một entry hợp lệ. Dựng list record O(n) và `heapq.heapify` O(n), nên tổng **O(n)**. Một lần compact có thể gây spike độ trễ, không phải O(log n).


### Bài 21. Kiểm tra bất biến liên chỉ mục

Dictionary có ID 10,20,30; treap chỉ chứa 10,20 và heap có entry hợp lệ cho cả ba. Hệ thống đã đúng chưa?

**Lời giải:** **Chưa**. Bất biến `keys(treap)=keys(dictionary)` bị sai vì thiếu ID30 ở treap. Pop theo business có thể còn hoạt động, nhưng truy vấn range theo ID sẽ bỏ sót ticket. Validator phải kiểm tra **cả hai index**.

### Bài 22. Heap có một entry hợp lệ cho mỗi ticket

Dictionary có 2 ticket. Heap có 20 entry, trong đó 18 stale và 2 hợp lệ, mỗi ticket một entry. Điều này có vi phạm bất biến nghiệp vụ không?

**Lời giải:** **Không**, nếu thuật toán peek/pop luôn bỏ qua stale và mỗi ticket active có chính xác một entry hợp lệ. Tuy nhiên, bộ nhớ tăng theo m=20 và chi phí dọn stale chưa được tính. Tính đúng và hiệu suất phải được kiểm tra riêng.

### Bài 23. FIFO khi cùng mức nhưng khác ID

Hai ticket A(ID900) và B(ID100) có business priority0. A tạo trước B. Nếu comparator heap chỉ là `(business_priority,id)`, ai được chọn? Có đúng FIFO không?

**Lời giải:** Heap chọn **B(ID100)** vì ID100 nhỏ hơn ID900. Điều đó **sai FIFO** nếu A tạo trước. Phải dùng `(business_priority,created_sequence,id)` với created_sequence nhỏ của A.

### Bài 24. Chọn comparator theo quy ước ngược

Sản phẩm quy định **điểm càng lớn càng khẩn**: ticket A điểm90, B điểm20. Dùng Python min-heap có khóa `(score,created_seq,id)` trực tiếp thì ai được lấy trước và sửa như thế nào?

**Lời giải:** Min-heap trực tiếp chọn **B(20)**, sai chính sách. Với score là số nguyên có miền rõ, có thể dùng khóa `(-score,created_seq,id)` để A được lấy trước, hoặc thiết kế comparator riêng. Việc đảo business key này **không liên quan** đến min/max random priority trong treap.

### Bài 25. Sửa heap và treap trong một transaction

Sau khi thêm ticket, treap và dictionary cập nhật thành công nhưng `heappush` bị lỗi cấp phát. Đâu là vi phạm và giải pháp?

**Lời giải:** Ticket active có ID trong treap/dict nhưng **không có entry hợp lệ trong heap**, nên có thể không bao giờ được phục vụ. Cần rollback, persistent state/atomic publish hoặc giao dịch có khả năng phục hồi; riêng việc các thao tác thành phần đúng không tạo atomicity tự động.

### Bài 26. Pop bị lỗi sau khi đã lấy từ heap

`heappop` đã lấy entry hợp lệ ID42, nhưng xóa ID42 khỏi treap gặp `RecursionError` trước khi kết thúc. Có được coi pop thành công và retry không cần kiểm tra không?

**Lời giải:** Không. Dictionary có thể còn ID42 trong khi entry hợp lệ đã mất và treap có thể bị sửa dở. Cần cơ chế transaction/recovery và xác minh lại invariant; retry ngây thơ có thể tạo một trạng thái sai khác.

### Bài 27. Có nên gọi `heappush` trong `assert` không?

Một test viết `assert heapq.heappush(heap,entry) is None`. Điều gì xảy ra nếu chạy Python với `-O`?

**Lời giải:** Biểu thức `assert` bị loại, nên **lệnh push cũng không chạy**. Phải gọi `heapq.heappush(heap,entry)` tách biệt, rồi dùng `assert` để kiểm tra hậu điều kiện không có side effect.

### Bài 28. Heap indexed khác heap lazy thế nào?

Một dịch vụ phải cập nhật business priority hàng nghìn lần mỗi giây và yêu cầu bộ nhớ O(n) với n ticket active. Nên ưu tiên thiết kế heap nào?

**Lời giải:** **Indexed heap** với `position[id]` có thể sửa khóa tại chỗ O(log n) và dùng O(n) bộ nhớ, thường thích hợp hơn nếu việc tích tụ stale entry không chấp nhận được. Lazy heap vẫn có thể dùng nếu có chính sách compaction và được chấp nhận chi phí memory/spike, nhưng bản đơn giản không tự O(n) theo số active.

### Bài 29. Thêm timestamp có thay FIFO đúng đắn hơn không?

Nếu hai ticket cùng business priority và dùng timestamp millisecond làm tie-breaker, có chắc chúng luôn khác nhau không?

**Lời giải:** Không. Hai ticket có thể tạo trong cùng millisecond hoặc timestamp có thể thiếu độ phân giải/không đơn điệu. Dùng **sequence tăng đơn điệu được quản lý nhất quán**, hoặc một tie-breaker khác có thứ tự toàn phần rõ ràng.

### Bài 30. Xử lý số thực `NaN` như business priority

Một ứng dụng nhận business score kiểu float và có thể có `NaN`. Vì sao cần kiểm tra dữ liệu trước khi cho vào heap?

**Lời giải:** So sánh với `NaN` không tuân theo thứ tự toàn phần thông thường: `NaN < x`, `NaN > x` và `NaN == x` đều có thể không cho hành vi mong đợi. Heap cần một comparator có thứ tự nhất quán; nên **từ chối NaN hoặc chuẩn hóa score** theo hợp đồng nghiệp vụ.


### Bài 31. Aging có tự diễn ra trong heap không?

Một ticket có business score thay đổi liên tục theo công thức phụ thuộc thời gian chờ. Nếu tạo heap entry một lần rồi không cập nhật, heap có còn chọn đúng thứ tự theo score hiện tại không?

**Lời giải:** Không được giả định. Heap chỉ so những **giá trị được lưu ở entry**, không tự tính lại điểm khi thời gian thay đổi. Cần một cơ chế scheduler cập nhật score/rebuild theo mốc thời gian hoặc một cấu trúc hỗ trợ chính sách đặc biệt.

### Bài 32. Priority nhỏ luôn bị đói?

Một hệ thống cứ tiếp nhận ticket P0 liên tục, và P3 chỉ được phục vụ khi không còn ticket P0–P2. Có bảo đảm mọi ticket P3 sẽ được phục vụ sau thời gian hữu hạn không?

**Lời giải:** **Không** nếu luồng ticket ưu tiên cao không ngừng và scheduler không có fairness/aging/quota. Đây là vấn đề **starvation nghiệp vụ**, không liên quan đến expected height của treap.

### Bài 33. Có nên dùng random treap priority làm lottery scheduling?

Một đội muốn chọn ngẫu nhiên giữa các ticket cùng business priority. Họ dùng luôn `TreapNode.random_priority` làm thứ tự lựa chọn. Có nên không?

**Lời giải:** Không nên mặc định. Random priority của treap được sinh cho **hình dạng cấu trúc** và có thể giữ ổn định theo node, dẫn tới cùng ticket luôn thắng trong nhóm. Nếu sản phẩm muốn lottery scheduling, phải có **thuật toán chọn random riêng** với phân phối, seed, fairness và chính sách tái chọn rõ ràng.

### Bài 34. Truy vấn ID theo khoảng có liên quan business priority không?

Ticket có ID 10,20,30,40 và business priorities lần lượt 5,0,3,1. Gọi `tickets_by_id(15,35)` trả ID nào và theo thứ tự gì?

**Lời giải:** Trả **ID 20 rồi ID 30**, theo ID tăng; business priorities tương ứng 0 và 3. Đây không phải “lấy hai ticket khẩn nhất toàn hệ thống”, vì ID40 có business priority1 có thể khẩn hơn ID30 nhưng không nằm trong khoảng ID.

### Bài 35. Chọn cấu trúc khi phải bảo đảm worst-case

Một dịch vụ yêu cầu tra ID trong O(log n) **worst-case** cho mọi trạng thái hợp lệ. Có thể dựa trực tiếp vào treap priority random không?

**Lời giải:** Không. Treap có tìm theo ID O(log n) **kỳ vọng** dưới giả định random chuẩn, nhưng worst-case O(n). Có thể thay chỉ mục ID bằng **AVL/red-black tree** hoặc một cấu trúc có bảo đảm worst-case đã chứng minh, trong khi business heap vẫn phục vụ theo độ khẩn.

### Bài 36. Đổi seed có sửa chính sách nghiệp vụ sai không?

Một ticket P5 đang bị phục vụ trước ticket P0 vì code chọn `treap.root`. Nếu đổi seed, có bảo đảm P0 được chọn đầu không?

**Lời giải:** Không. Seed mới chỉ thay hình dạng treap và do đó có thể thay root; root vẫn không được chọn theo business key. Sửa **cách truy vấn** bằng chỉ mục nghiệp vụ, không đổi seed để vá lỗi logic.

### Bài 37. Tổng bộ nhớ của hai chỉ mục

Có n ticket active, n node treap ID, n record dict và m entry business heap. Bậc bộ nhớ tính theo n và m là gì?

**Lời giải:** **O(n+m)** bộ nhớ, với O(n) node treap/dict và O(m) heap entry. Nếu m có thể tăng không giới hạn so với n do lazy updates, không thể nói toàn hệ thống luôn O(n) theo số ticket active mà không có compaction/giới hạn khác.

### Bài 38. Phân biệt nhiều loại bảo đảm

Một hệ thống có treap O(log n) kỳ vọng và heap `heappush` O(log m) worst-case, nhưng `peek_next` có thể bỏ s stale entries. Có được kết luận mọi request O(log n) worst-case không?

**Lời giải:** Không. Treap có worst O(n), heap có kích thước m khác n, và cleanup có thể mất O(s log m). Chi phí tổng phải xét **tất cả thành phần và đường lỗi**, không chỉ lấy giới hạn tốt của một cấu trúc.

### Bài 39. Xác định invariant quan trọng nhất khi phối hợp chỉ mục

Một ticket đã bị hủy khỏi dictionary nhưng heap vẫn còn entry cũ. Điều gì phải đúng khi gọi `pop_next` để không trả ticket đã hủy?

**Lời giải:** `pop_next` phải kiểm tra entry ở đỉnh với **record hiện tại**, nhận ra ID không còn trong dictionary và **bỏ entry stale**. Đồng thời ID phải đã được xóa khỏi treap. Nếu không đối chiếu với nguồn sự thật, hệ thống có thể phục vụ một ticket đã hủy.

### Bài 40. Đặc tả một API hai chỉ mục

Hãy viết ít nhất năm điều khoản cho API `TicketBoard` hỗ trợ tìm theo ID, duyệt ID theo khoảng và lấy ticket khẩn nhất.

**Lời giải:** Một đặc tả đạt yêu cầu cần nêu: (1) `id` duy nhất và bất biến trong vòng đời ticket; (2) business priority có comparator rõ, ví dụ số nhỏ hơn khẩn hơn; (3) tie-breaker FIFO bằng `created_sequence`; (4) treap có **random priority riêng**, không ảnh hưởng thứ tự phục vụ; (5) dictionary là nguồn sự thật, `keys(treap)=keys(dict)`, mọi record active có đúng một heap entry hợp lệ; (6) update/cancel/pop phải đồng bộ chỉ mục với cơ chế transaction/recovery; (7) chi phí expected/worst theo n/m, bao gồm stale cleanup, và (8) các yêu cầu concurrency, fairness, TTL/deadline nếu sản phẩm cần. Không được thay hợp đồng tính đúng bằng một kết quả benchmark.

## 19. Tổng kết và checklist thiết kế

Một chương trình có cả treap và hàng đợi nghiệp vụ thực ra đang duy trì **hai quan hệ thứ tự độc lập**:

\[
\boxed{\text{Treap: BST theo key ID, heap theo random priority}}
\]

\[
\boxed{\text{Business queue: ưu tiên theo business key và tie-breaker}}
\]

Chỉ vì cả hai đều dùng từ **“priority”** và đều có thể so theo min-heap **không** có nghĩa chúng cùng mục đích.

### 19.1. Năm nguyên tắc cần ghi nhớ

1. **Random priority điều khiển hình dạng cấu trúc.** Nó được rút để treap có chiều cao tốt **theo kỳ vọng**, không diễn tả SLA hay độ khẩn.
2. **Business priority điều khiển thứ tự phục vụ.** Nó do sản phẩm xác định, có thể được cập nhật, và phải có comparator cùng tie-breaker rõ.
3. **Không thay random bằng business priority rồi giữ nguyên định lý treap.** Business score có thể trùng, tương quan với key và thay đổi theo thời gian.
4. **Một chỉ mục không tự trả lời hai thứ tự khác nhau.** Hãy dùng hai index, metadata aggregate hoặc composite BST key tùy tập truy vấn.
5. **Cập nhật nhiều index cần bảo đảm nhất quán.** Một treap đúng và một heap đúng riêng lẻ vẫn chưa chắc cùng mô tả một backlog đúng.

### 19.2. Checklist ngắn khi review thiết kế

| Câu hỏi | Kỳ vọng trả lời rõ |
| --- | --- |
| Định danh chính là gì? | `id`, duy nhất, chính sách reuse ID |
| Business score có chiều so sánh nào? | Số nhỏ/lớn khẩn hơn, các mức hợp lệ |
| Khi cùng mức thì ai trước? | FIFO/deadline/quota, tie-breaker tổng quát |
| Random priority được dùng ở đâu? | Chỉ định hình treap, không bị đổi vì escalation |
| Range query sắp theo cái gì? | ID hoặc composite business key, không nhập nhằng |
| Khi đổi business score có thay index nào? | Heap/index nghiệp vụ; treap ID thường không đổi |
| Xóa/hủy/pop có đồng bộ các index? | Dict, treap, heap version/position và transaction |
| Có stale entries không? | Chính sách generation, cleanup và compact |
| Bộ nhớ tính theo n hay m? | n active records, m heap entries có thể lớn hơn n |
| Loại bảo đảm hiệu năng nào? | Treap expected, heap worst, cleanup/amortized |
| Có deadline hoặc fairness cứng không? | Thiết kế scheduler/thuật toán, không dựa random treap |
| Có đồng thời và lỗi giữa chừng không? | Lock, transaction, rollback, persistent hoặc recovery |

### 19.3. Một câu hỏi quyết định rất hữu ích

Trước khi sử dụng một biến tên `priority` trong code, hãy hỏi:

> **Giá trị này quyết định vị trí của node trong cấu trúc để tối ưu tra cứu, hay quyết định công việc nào được làm trước theo hợp đồng nghiệp vụ?**

Nếu câu trả lời là **“vị trí trong treap”**, hãy giữ nó là một priority kỹ thuật ngẫu nhiên độc lập theo mô hình đã chọn. Nếu là **“công việc nào trước”**, hãy để business policy quyết định và dùng một chỉ mục thích hợp để thực thi. Nếu cần cả hai, hãy lưu **hai trường riêng biệt** và bảo trì những bất biến tương ứng.

**Kết luận:** phân biệt được hai loại ưu tiên giúp tránh cả lỗi **hiệu năng** (treap biến thành cây lệch vì priority không ngẫu nhiên) lẫn lỗi **nghiệp vụ** (phân phối sai công việc vì lấy root treap). Khi tính đúng, giả định ngẫu nhiên, tie-breaker, chi phí và đồng bộ được phát biểu độc lập, việc chọn treap, heap, hash map hay cây cân bằng sẽ dựa trên mục tiêu thực sự của hệ thống.

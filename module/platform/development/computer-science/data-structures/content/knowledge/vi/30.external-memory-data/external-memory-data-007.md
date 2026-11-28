# SSTable, chỉ mục khối và bộ lọc khóa

## 1. Khi dữ liệu lớn hơn bộ nhớ, tra cứu phải tính đến I/O

Trong các cấu trúc dữ liệu chạy hoàn toàn trong RAM, ta thường đếm phép so sánh hoặc truy cập phần tử. Khi một bảng có hàng triệu đến hàng tỷ mục và dữ liệu nằm trên SSD/HDD, một thao tác tra cứu có thể phải đọc **một hoặc nhiều khối dữ liệu** từ thiết bị. Chi phí đọc khối thường đáng kể hơn việc so sánh vài chục khóa đã ở trong RAM.

Chủ đề **SSTable, chỉ mục khối và bộ lọc khóa** thuộc chương **Dữ liệu ngoài bộ nhớ**. Nó mở rộng cách nhìn quen thuộc về mảng đã sắp xếp, tìm kiếm nhị phân, bảng băm và cây: cùng một mục tiêu tìm khóa, nhưng cần tổ chức dữ liệu để **giảm số lần đọc khối**, tận dụng **đọc tuần tự** và kiểm soát chi phí cập nhật.

Hãy xét một kho sự kiện lưu khóa dạng **(mã thiết bị, thời điểm)**. Hệ thống cần trả lời:

- Giá trị của khóa **sensor:42:08:00** đang là bao nhiêu?
- Có xuất hiện khóa **sensor:99:08:00** trong một tệp dữ liệu cũ không?
- Đọc tất cả khóa từ **sensor:42:08:00** đến **sensor:42:09:00** theo thứ tự.
- Ghi thêm dữ liệu đều đặn mà không phải sửa trực tiếp hàng nghìn trang cũ.

Một thiết kế phổ biến là ghi dữ liệu mới vào cấu trúc trong RAM, sau đó xuất chúng thành các **tệp có thứ tự và bất biến**. Mỗi tệp có chỉ mục để xác định khối chứa khóa và bộ lọc để loại bỏ nhanh những tệp chắc chắn không có khóa cần tìm.

### Mục tiêu sau bài học

Người học có thể: giải thích cách SSTable được tạo và đọc; phân biệt **chỉ mục thưa theo khối** với chỉ mục cho từng bản ghi; vận dụng quy tắc tìm khối bằng khóa ranh giới; hiểu kết quả **chắc chắn không có / có thể có** của Bloom filter; và ước lượng lợi ích I/O trong tra cứu chính xác, quét khoảng, xóa logic và hợp nhất dữ liệu.

## 2. SSTable là gì?

**SSTable** (Sorted String Table) là một cấu trúc lưu trữ có các mục **được sắp theo khóa** và thường được ghi thành **tệp bất biến (immutable)**. Tên gọi có từ lịch sử của hệ thống lưu trữ khóa–giá trị, nhưng khóa có thể là chuỗi, số nguyên hoặc khóa ghép được mã hóa thành một thứ tự so sánh nhất quán.

Một mục có thể mô tả đơn giản là:

~~~text
(key, value)
~~~

Trong hệ thống hỗ trợ nhiều phiên bản, mục thực tế có thể mang thêm **sequence number**, loại thao tác (**value**, **tombstone**) hoặc siêu dữ liệu khác. Phạm vi bài này dùng **khóa duy nhất trong một SSTable** để giải thích tìm kiếm cơ bản; khi có nhiều phiên bản cùng khóa, thứ tự khóa nội bộ và quy tắc chọn phiên bản mới nhất phải được xử lý thêm.

Tính chất chính:

1. **Có thứ tự:** khi đọc các mục trong một SSTable theo thứ tự lưu trữ, khóa không giảm theo bộ so sánh đã chọn.
2. **Bất biến sau khi xuất bản:** thay vì sửa trực tiếp tệp cũ, hệ thống tạo SSTable mới hoặc hợp nhất các SSTable thành tệp mới.
3. **Chia thành khối:** nhiều mục liên tiếp được đóng trong một **data block** để đọc/nén/kiểm tra tính toàn vẹn theo khối.
4. **Có metadata hỗ trợ đọc:** thường có **block index**, **bộ lọc khóa**, thông tin phạm vi khóa và các con trỏ cần thiết để tìm tới những vùng trong tệp.

Một tệp SSTable đơn giản có thể được hình dung như sau:

~~~text
                    SSTable bất biến
  +------------------------------------------------------+
  | Data block 0 | Data block 1 | Data block 2 | ...    |
  | khóa a..d    | khóa e..k    | khóa m..z    |        |
  +------------------------------------------------------+
  | Block index: khóa ranh giới -> offset/length của block |
  +------------------------------------------------------+
  | Key filter: Bloom filter hoặc biến thể tương đương    |
  +------------------------------------------------------+
  | Footer / metadata: vị trí các vùng, phiên bản định dạng|
  +------------------------------------------------------+
~~~

Đây là **bố cục khái niệm**. Một số định dạng có các khối chỉ mục nhiều cấp, khối filter riêng, metadata đặt ở nhiều vị trí, khóa ranh giới được rút gọn, nén dữ liệu và checksum. Không nên giả định mọi SSTable đều có chính xác thứ tự vật lý trên.

### Vì sao chọn tệp bất biến?

Giả sử 1.000 giá trị mới đến trong một giây. Nếu mỗi lần ghi đều sửa một vị trí ngẫu nhiên trong tệp lớn, thiết bị có thể chịu nhiều lượt đọc–ghi ngẫu nhiên. Cách tổ chức thường gặp trong họ **LSM-tree** là:

~~~text
put / delete
     |
     v
MemTable có thứ tự (RAM) ----> flush ----> SSTable mới trên thiết bị
     |                                         |
     |                                  nhiều SSTable
     |                                         |
     +------------------------------- compaction (merge)
                                               |
                                               v
                                        SSTable mới
~~~

**MemTable** có thể là skip list, cây cân bằng hoặc một cấu trúc khác phù hợp cho cập nhật trong RAM. Khi MemTable đạt ngưỡng, hệ thống xuất các mục theo thứ tự thành SSTable. **Compaction** đọc các dãy đã sắp xếp, trộn chúng và tạo SSTable thay thế.

SSTable tự nó không phải toàn bộ cơ chế lưu trữ: cơ sở dữ liệu còn có thể cần **write-ahead log (WAL)** để phục hồi ghi chưa flush, metadata để biết tệp nào đang có hiệu lực, bộ đệm khối, kiểm soát đồng thời và chính sách compaction. Các thành phần đó phối hợp với SSTable để tạo thành một hệ thống lưu trữ hoàn chỉnh.

## 3. Định vị một khóa trong các data block

Giả sử một SSTable gồm ba khối, mỗi khối chứa các cặp khóa–giá trị đã sắp:

~~~text
Data block 0 (offset 0):     [11, 18, 26]
Data block 1 (offset 4096):  [37, 41, 58]
Data block 2 (offset 8192):  [66, 70, 95]
~~~

Khóa **52** chắc chắn chỉ có thể nằm trong khoảng khóa của **block 1**. Nếu không có chỉ mục, ta có thể phải đọc các khối để kiểm tra ranh giới; với một **chỉ mục khối** trong RAM, ta chọn trước khối cần đọc.

### Chỉ mục thưa theo khối (sparse block index)

Một thiết kế dễ hiểu lưu **khóa nhỏ nhất của mỗi khối** cùng địa chỉ của khối đó:

| Khóa ranh giới đầu khối | Vị trí khối | Khóa hiện có trong khối |
| ---: | ---: | --- |
| 11 | offset 0 | 11, 18, 26 |
| 37 | offset 4096 | 37, 41, 58 |
| 66 | offset 8192 | 66, 70, 95 |

Để tìm **52**, chọn entry có **khóa ranh giới lớn nhất không vượt quá 52**, tức **37**, rồi đọc block 1 và tìm kiếm bên trong. Kết quả là **không tồn tại 52**, dù block 1 chứa vùng khóa mà 52 có thể thuộc về.

Để tìm **66**, chọn block 2 và tìm được mục tương ứng. Nếu khóa đích **nhỏ hơn 11**, không khối nào trong SSTable có thể chứa khóa đó theo mô hình này.

~~~text
Tìm khóa 52
      |
      v
Block index (ở RAM): [11 -> B0] [37 -> B1] [66 -> B2]
                                  |
                             chọn B1
                                  v
Thiết bị: đọc block 1 [37, 41, 58]
                                  |
                            tìm nhị phân
                                  |
                                  v
                              NOT_FOUND
~~~

Chỉ mục này có **một entry cho mỗi block**, không phải một entry cho mỗi bản ghi; vì vậy nó còn được gọi là **sparse index**. Nếu một block trung bình chứa 100 mục thì chỉ mục có thể nhỏ hơn một chỉ mục dày đặc khoảng 100 lần về số entry.

**Bất biến định tuyến:** mỗi mục của block phải nằm trong miền khóa được ranh giới và thứ tự khối mô tả. Khi dùng khóa nhỏ nhất của block, chỉ mục phải được sắp tăng và phép tìm phải chọn đúng khối có ranh giới lớn nhất **≤ khóa đích**. Một số định dạng dùng **fence key**, separator hoặc khóa rút gọn thay vì khóa nhỏ nhất nguyên vẹn; khi đó phải tuân thủ quy tắc định tuyến của định dạng đó.

### Mã giả tìm bằng chỉ mục khối

~~~text
function get_from_sstable(table, target):
    index = table.block_index

    // Tìm entry cuối cùng có first_key <= target.
    candidate = upper_bound(index.first_keys, target) - 1

    if candidate < 0:
        return NOT_FOUND

    location = index.entries[candidate].block_location
    block = read_and_decode_block(location)

    i = lower_bound(block.entries, target)

    if i < block.entry_count and block.entries[i].key == target:
        return FOUND(block.entries[i].value_or_tombstone)

    return NOT_FOUND
~~~

**upper_bound** trên dãy first_key có thứ tự trả về vị trí đầu tiên có khóa **lớn hơn** khóa đích. **lower_bound** trong data block trả về vị trí đầu tiên có khóa **không nhỏ hơn** khóa đích. Khi index và block đã nằm trong RAM, hai phép tìm kiếm nhị phân này chủ yếu tốn thao tác CPU; khi cần tải block từ thiết bị mới phát sinh I/O.

Mã giả giả định các khóa logic là duy nhất trong một SSTable. Với nhiều phiên bản cùng khóa nằm ở các block khác nhau, hệ thống có thể sắp theo **(user_key, thứ tự phiên bản)** và dùng khóa tìm kiếm nội bộ cùng quy tắc ranh giới phù hợp để không bỏ sót phiên bản cần đọc.

### Block index trên RAM hay trên thiết bị?

Nếu chỉ mục vừa RAM, ta có thể tải hoặc cache toàn bộ chỉ mục; tra cứu cần thêm **khoảng một lần đọc data block** khi không có cache. Nếu chỉ mục quá lớn, hệ thống có thể lưu nó thành **nhiều index block**, thậm chí có **chỉ mục của chỉ mục**, nên một phép tìm có thể phải đọc thêm index block.

Do đó, câu “tra cứu một SSTable chỉ mất một lần đọc khối” chỉ đúng khi phần metadata cần thiết đã có trong RAM và data block chưa được cache. Chi phí thực còn phụ thuộc buffer cache, nén, kích thước block và định dạng tệp.

## 4. Quét khoảng trong SSTable

Điểm mạnh của dữ liệu đã sắp là **range scan**. Muốn lấy các khóa từ **35 đến 70** trong ví dụ trên:

1. Dùng block index để tìm khối đầu tiên có thể chứa khóa ≥ 35: block 1 với ranh giới **37**. Block 0 kết thúc tại 26 nên không cần đọc.
2. Đọc block 1 và phát các mục **37, 41, 58**.
3. Đọc block 2 và phát **66, 70**.
4. Dừng trước mục 95 vì đã vượt giới hạn trên.

Nếu việc chọn điểm bắt đầu chỉ dựa vào **khóa đầu block**, ta thường bắt đầu từ khối có **first_key lớn nhất ≤ low** rồi tiến tiếp; khi **low** nằm giữa ranh giới đầu của hai block như 35 trong ví dụ, muốn bỏ qua block 0 an toàn cần biết **khóa cuối** của block 0 là 26 (hoặc separator tương đương). Nếu không có thông tin đó, thuật toán bảo thủ có thể đọc block 0 trước và loại các mục nhỏ hơn 35. Chỉ mục với fence key và miền khóa giúp giảm phần đọc thừa.

Mã giả tổng quát:

~~~text
function scan_range(table, low, high):
    if low > high:
        return

    block_id = find_starting_block(table.block_index, low)

    while block_id exists:
        block = read_and_decode_block(block_id)

        for entry in block.entries in ascending_key_order:
            if entry.key < low:
                continue
            if entry.key > high:
                return
            yield entry

        block_id = table.next_data_block(block_id)
~~~

Khác với tìm chính xác, quét khoảng có thể đọc **nhiều khối liên tiếp**. Cơ chế đọc trước (prefetch) và cache có thể hỗ trợ việc này. **Bloom filter theo khóa đơn lẻ** nhìn chung không giúp quyết định một khoảng rộng có dữ liệu hay không; nếu cần bỏ qua khoảng, phải dùng ranh giới khóa, chỉ mục hoặc các dạng bộ lọc chuyên biệt cho phạm vi.

## 5. Bộ lọc khóa: chắc chắn không có hay có thể có?

Giả sử hệ thống có **12 SSTable** và muốn tra khóa **sensor:99:08:00**. Nếu mỗi SSTable đều phải đọc ít nhất một data block trước khi biết không chứa khóa, truy vấn âm tính có thể tiêu tốn nhiều I/O không cần thiết.

Một **bộ lọc khóa** lưu tóm tắt nhỏ gọn của tập khóa để trả lời câu hỏi:

> “Có chắc khóa này không thuộc SSTable không?”

Loại phổ biến là **Bloom filter**, một cấu trúc dữ liệu xác suất dùng **mảng bit** cùng **k hàm băm**. Nó ưu tiên kết quả phủ định chính xác, chấp nhận đôi khi báo dương tính giả.

| Kết quả Bloom filter | Ý nghĩa | Hành động phù hợp |
| --- | --- | --- |
| **Definitely not present** (âm tính) | Khóa chắc chắn không thuộc tập đã đưa vào filter, khi filter đúng và đầy đủ | Bỏ qua SSTable, không đọc data block |
| **May be present** (dương tính) | Khóa có thể tồn tại; cũng có thể là **false positive** | Dùng block index và đọc/kiểm tra data block trước khi kết luận |

Bloom filter chuẩn **không có false negative** nếu mọi khóa cần tìm đều đã được đưa vào filter, các hàm băm và tham số không thay đổi và filter không bị hỏng. Một filter thiếu khóa, bị dùng sai phiên bản, hoặc không biểu diễn đúng loại mục tìm kiếm có thể khiến hệ thống bỏ sót dữ liệu; đó là lỗi xây dựng/sử dụng filter, không phải đặc tính xác suất mong muốn.

### Cách tạo Bloom filter

Cho một bit array gồm **m** bit, ban đầu đều bằng 0. Với mỗi khóa, tính **k** vị trí băm và đặt những bit đó thành 1:

~~~text
function bloom_add(filter, key):
    for j from 1 to filter.k:
        pos = hash_j(key) mod filter.m
        filter.bits[pos] = 1
~~~

Khi kiểm tra khóa, nếu có **bất kỳ** bit nào cần thiết vẫn là 0 thì khóa chắc chắn chưa được chèn vào filter:

~~~text
function bloom_may_contain(filter, key):
    for j from 1 to filter.k:
        pos = hash_j(key) mod filter.m

        if filter.bits[pos] == 0:
            return false    // Chắc chắn không có

    return true             // Có thể có: cần đọc dữ liệu để xác nhận
~~~

Ví dụ giả định **k = 3**:

~~~text
                    Mảng bit
vị trí:       0 1 2 3 4 5 6 7 8 9 10 11
sau chèn:     0 1 0 1 0 0 1 1 0 1  0  0

Kiểm tra A:  vị trí 1,3,9 đều là 1  -> MAYBE
Kiểm tra B:  vị trí 1,4,9 có bit 4=0 -> NO
~~~

Với A, ta **không thể** suy ra A chắc chắn có trong SSTable: các bit 1, 3, 9 có thể đã được đặt bởi các khóa khác. Với B, vì bit 4 bằng 0, B chắc chắn không thuộc tập khóa đã chèn.

Bloom filter chuẩn không lưu khóa, không lưu vị trí bản ghi và **không hỗ trợ xóa từng khóa một cách an toàn bằng cách đưa bit về 0**: một bit có thể được chia sẻ bởi nhiều khóa. Với SSTable bất biến, đây thường không phải vấn đề vì filter được tạo cùng tệp và không cần cập nhật sau khi xuất bản. Việc xóa logic bằng tombstone cần giữ đúng nghĩa của khóa, như phần sau trình bày.

### Xác suất dương tính giả

Đặt:

- **n:** số khóa khác nhau đưa vào filter.
- **m:** số bit của filter.
- **k:** số vị trí băm kiểm tra cho mỗi khóa.

Với giả định các vị trí băm phân bố gần độc lập và đều, xác suất false positive xấp xỉ:

~~~text
p ≈ (1 - exp(-k*n/m))^k

Số hàm băm gần tối ưu:
k_opt ≈ (m/n) * ln(2)

Khi chọn k gần tối ưu:
p ≈ (0.6185)^(m/n)
~~~

Giả sử **n = 1.000** khóa và dùng **10 bit/khóa**:

~~~text
m = 10.000 bit = 1.250 byte ≈ 1,22 KiB
k_opt ≈ 10 * ln(2) ≈ 6,93  -> chọn k = 7
p ≈ (1 - exp(-0,7))^7
  ≈ 0,0082 ≈ 0,82%
~~~

Nghĩa là trong một tập lớn các truy vấn **không có khóa**, khoảng **0,82%** có thể bị filter báo “có thể có” và buộc hệ thống kiểm tra sâu hơn, dưới các giả định của mô hình. Giá trị thực còn phụ thuộc hiện thực hàm băm, cách chia filter, số khóa khác nhau và đặc điểm dữ liệu.

**Điểm đánh đổi:** tăng số bit trên mỗi khóa thường giảm false positive nhưng tốn RAM/dung lượng hơn. Tăng **k** quá cao cũng không luôn tốt: nhiều lần băm hơn và nhiều bit bị đặt thành 1 hơn có thể khiến tỷ lệ dương tính giả tăng trở lại.

## 6. Ghép bộ lọc khóa với chỉ mục khối

Một đường đọc cho **một SSTable** thường kiểm tra từ rẻ đến đắt:

~~~text
                   GET(key) cho một SSTable
                             |
                             v
                  Key có ngoài min/max?
                         /      \
                       Có       Không
                       |          |
                      MISS        v
                           Bloom filter
                              /     \
                         NO  /       \ MAYBE
                            v         v
                           MISS    Block index
                                      |
                                      v
                            Chọn vị trí data block
                                      |
                                      v
                          Đọc/giải nén/kiểm tra block
                                      |
                                      v
                             So sánh khóa thật
                                  /        \
                                Có         Không
                                |            |
                         VALUE/TOMBSTONE    MISS
~~~

Trong mô hình này, câu hỏi **min/max** nghĩa là khóa nằm **ngoài** miền min/max của tệp hay không; nếu ngoài miền, trả MISS ngay, không cần filter. Bộ lọc tiếp tục giúp bỏ qua tệp khi khóa nằm trong miền nhưng thực ra không tồn tại.

Mã giả:

~~~text
function lookup_one_table(table, key):
    if key < table.min_key or key > table.max_key:
        return MISS

    if not table.key_filter.may_contain(key):
        return MISS

    result = get_from_sstable(table, key)

    if result is NOT_FOUND:
        return MISS

    return result             // VALUE hoặc TOMBSTONE
~~~

Trong ứng dụng thực tế, **thứ tự kiểm tra** có thể khác nhau theo cache, filter của từng block/partition, khả năng kiểm tra khóa biên và cách phân bố metadata. Mô hình trên chỉ cho thấy đúng trách nhiệm của từng thành phần:

- **Min/max range:** loại bỏ tệp không thể chứa khóa vì nằm ngoài khoảng.
- **Key filter:** loại bỏ nhanh những tệp **chắc chắn** không có khóa, kể cả khi khóa nằm trong khoảng min/max.
- **Block index:** xác định **khối nào cần đọc** nếu khóa có thể tồn tại.
- **Data block:** kiểm tra **khóa và giá trị thật**, quyết định FOUND/MISS cuối cùng.

Không được trả giá trị thành công chỉ dựa trên kết quả “MAYBE” của filter.

## 7. Ước lượng bộ nhớ, lượt đọc khối và độ phức tạp

Giả định một SSTable có **N = 1.000.000 mục**, trung bình **b = 100 mục/data block**. Mỗi entry chỉ mục gồm khóa ranh giới **8 byte** và vị trí khối **8 byte**. Tạm bỏ qua độ dài khối, checksum, nén và metadata khác để tiện tính.

~~~text
Số data block:
B = ceil(N / b) = 10.000 block

Số entry của chỉ mục thưa:
10.000 entry

Dung lượng chỉ mục tối thiểu theo giả định:
10.000 * (8 + 8) = 160.000 byte ≈ 156,25 KiB

Bloom filter ở mức 10 bit/khóa:
1.000.000 * 10 / 8 = 1.250.000 byte ≈ 1,19 MiB
~~~

Bài toán cho thấy một **chỉ mục khối vài trăm KiB** và **Bloom filter cỡ MiB** có thể hỗ trợ tra cứu một tệp chứa triệu mục. Con số thực có thể lớn hơn vì block index cần offset, length, key thay đổi độ dài và cấu trúc hỗ trợ; filter cũng có header, căn chỉnh và có thể chia partition.

### Phân tích chi phí

Đặt **B** là số data block; **k** là số mục cần quét; **b** là số mục trung bình/khối; **T** là số SSTable được xem xét cho một phép tra cứu.

| Thao tác | Chi phí theo bậc lớn | Ghi chú về I/O |
| --- | --- | --- |
| Xây một SSTable từ dãy đã sắp | O(N) xử lý mục | Ghi tuần tự khoảng O(B) data block; thêm index/filter |
| Tìm khóa trong index thưa ở RAM | O(log B) phép so sánh | Không cần đọc thiết bị nếu index đã cache |
| Kiểm tra Bloom filter | O(k_hash) phép kiểm tra bit | Thường phục vụ từ RAM/cache; không xác nhận khóa tồn tại |
| Đọc khóa có thể tồn tại | O(log B) CPU + đọc data block | Thường khoảng 1 data block nếu index/filter đã cache |
| Quét khoảng trả về k mục | O(log B + k) xử lý mục | Khoảng O(1 + k/b) data block, còn tùy vị trí bắt đầu |
| Tìm khóa vắng trong T SSTable | O(T) lần kiểm tra metadata/filter | Data block đọc do false positive hoặc filter không sẵn có |

Ở hàng quét khoảng, **O(1 + k/b)** là mô hình I/O thuận lợi khi khối lấp đầy ổn định và các mục cần trả về nằm liên tiếp. Chi phí thực có thể tăng nếu nhiều phiên bản, tombstone, lấp đầy không đều hoặc đang hợp nhất nhiều dãy từ các SSTable khác nhau.

Giả sử **8 SSTable** được kiểm tra cho một khóa thực sự không có ở tệp nào; mỗi filter có tỷ lệ false positive **p = 1%**. Nếu bỏ qua mọi tối ưu từ min/max và giả sử filter hoạt động độc lập:

~~~text
Số data block bị đọc thừa kỳ vọng ≈ T * p
                                  = 8 * 0,01
                                  = 0,08 block / truy vấn âm tính

Xác suất có ít nhất một false positive:
1 - (1 - 0,01)^8 ≈ 7,73%
~~~

Đây là **kỳ vọng**, không phải giới hạn cứng: một truy vấn riêng lẻ vẫn có thể gặp nhiều false positive. Nếu index/filter chưa nằm trong RAM, sẽ còn I/O metadata; nếu metadata phạm vi loại bớt tệp, số tệp phải xét cũng giảm. Các chính sách phân tầng của LSM-tree quyết định một khóa có thể nằm trong bao nhiêu tệp cần tra.

### Tăng block size: lợi và hại

Khối lớn chứa nhiều mục hơn, khiến chỉ mục thưa nhỏ hơn và hỗ trợ đọc tuần tự tốt. Tuy nhiên, tìm một khóa duy nhất có thể phải đọc/giải nén **nhiều byte không dùng tới**. Khối nhỏ giảm lượng dữ liệu thừa cho point lookup nhưng tăng số entry index và có thể khiến quét khoảng phát sinh nhiều I/O hơn.

Khi đánh giá kích thước block, cần xét **tần suất point lookup và range scan**, cache, kích thước giá trị, nén và đặc tính thiết bị. Không có một block size tối ưu cho mọi tải.

## 8. Nhiều SSTable: phiên bản mới, tombstone và compaction

Một SSTable bất biến không sửa trực tiếp mục cũ. Giả sử tồn tại các tệp theo thời gian:

~~~text
SSTable S1 (cũ):  (A, 10) (B, 20) (C, 30)
SSTable S2 (mới): (B, 25) (D, 40)
SSTable S3 (mới hơn): (C, TOMBSTONE)
~~~

Khi truy vấn:

- **B**, giá trị hợp lệ mới nhất là **25** từ S2, không phải 20 từ S1.
- **C**, tombstone ở S3 nghĩa là khóa đã bị xóa logic; không được quay lại lấy giá trị 30 từ S1.
- **D**, chỉ có ở S2 nên trả **40**.

Trong một ví dụ đơn giản, có thể tra từ tệp mới đến cũ và dừng ở phiên bản mới nhất đã xác nhận. Trong một LSM-tree thực, thứ tự đó được tổ chức bằng sequence number, mức/level, phạm vi khóa và metadata, vì nhiều SSTable có thể được tạo hoặc hợp nhất theo thứ tự khác nhau so với thời điểm cập nhật logic.

**Tombstone** là một mục mang nghĩa “đã xóa”, được ghi như một cập nhật có thứ tự. Bloom filter phải phù hợp với nội dung bảng, kể cả khóa của tombstone nếu thao tác tra cứu cần thấy tombstone để chặn phiên bản cũ. Nếu loại nhầm khóa tombstone khỏi filter rồi bỏ qua cả tệp, dữ liệu cũ có thể bị “hồi sinh” trong kết quả đọc.

### Compaction làm gì?

Compaction là quá trình hợp nhất các dãy đã sắp thành dãy mới:

~~~text
S1: (A,10) (B,20) (C,30)
S2:        (B,25)        (D,40)
S3:               (C,TOMBSTONE)
            |
       merge theo khóa và phiên bản
            |
            v
S4: (A,10) (B,25) [C bị xóa] (D,40)
~~~

Mô hình trên giả định không còn phiên bản cũ cần giữ và việc bỏ tombstone là an toàn. Trong hệ thống hỗ trợ snapshot, hoặc khi còn dữ liệu cũ ở nơi khác chưa được compaction phủ hết, **không được tùy tiện xóa tombstone hay phiên bản cũ**: còn cần xét các snapshot đang hoạt động và phạm vi hợp nhất để tránh trả lại dữ liệu đã xóa.

Compaction thường giúp:

- Giảm số tệp phải tìm và số phiên bản cũ còn tồn tại.
- Xây lại **block index** và **key filter** chính xác cho SSTable mới.
- Khôi phục bố cục theo thứ tự khóa để hỗ trợ đọc tuần tự.
- Đánh đổi bằng **I/O đọc/ghi thêm** vì nhiều mục có thể bị ghi lại nhiều lần.

LSM-tree chọn đổi một phần chi phí đọc và compaction lấy việc gom ghi thành những đợt tuần tự. Sự đánh đổi thường được mô tả bằng **read amplification**, **write amplification** và **space amplification**.

### Đường đọc tổng quát của kho LSM

~~~text
function get(key):
    if mutable_memtable.contains(key):
        return resolve(mutable_memtable[key])

    for memtable in immutable_memtables newest_first:
        if memtable.contains(key):
            return resolve(memtable[key])

    for table in candidate_sstables_according_to_version_and_level:
        result = lookup_one_table(table, key)

        if result is VALUE:
            return result.value

        if result is TOMBSTONE:
            return NOT_FOUND

        // MISS: tiếp tục sang SSTable ứng viên khác.

    return NOT_FOUND
~~~

**resolve** phải hiểu tombstone, còn **candidate_sstables_according_to_version_and_level** phải xét đúng phiên bản mới nhất; mã giả không mô tả chính sách duyệt chung cho mọi biến thể LSM. Trong triển khai đầy đủ, đọc cũng có thể dùng snapshot sequence number, cache và phạm vi tệp.

## 9. Chỉ mục khối, Bloom filter và các cấu trúc đã học khác nhau thế nào?

| Cấu trúc | Câu hỏi nó giải quyết | Thế mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Mảng khóa đã sắp** | Khóa nằm ở vị trí nào? | Tìm nhị phân; duyệt liên tục | Chèn giữa mảng lớn có thể tốn dịch chuyển |
| **SSTable** | Làm sao giữ dữ liệu đã sắp trên thiết bị và ghi theo đợt? | Bất biến, hỗ trợ xây/đọc tuần tự, làm nền cho LSM | Một mình nó không giải quyết cập nhật trực tiếp hoặc phiên bản mới nhất trên nhiều tệp |
| **Block index thưa** | Data block nào có thể chứa khóa? | Ít entry hơn chỉ mục từng bản ghi; giảm đọc khối để định vị | Không xác nhận khóa thực sự có trong block |
| **Bloom filter** | Có chắc khóa không tồn tại trong tập không? | Loại bỏ point lookup âm tính với bộ nhớ nhỏ | Có false positive; không cho biết vị trí, giá trị hay thứ tự |
| **B+-tree** | Làm sao tìm và cập nhật dữ liệu có thứ tự theo trang? | Cây cân bằng, tra cứu và quét khoảng, cập nhật tại chỗ theo trang | Cập nhật có thể dẫn đến tách/gộp trang và ghi ngẫu nhiên |
| **Bảng băm** | Giá trị của khóa chính xác ở đâu? | Tra cứu chính xác thường nhanh | Không duy trì thứ tự tự nhiên phục vụ range scan |

Điểm cần nhớ là **SSTable + block index + Bloom filter** là những thành phần **bổ sung cho nhau**. SSTable giữ dữ liệu theo thứ tự; index tìm được khối; filter cho phép không đọc khối khi khóa chắc chắn không hiện diện. Chúng không thay thế lẫn nhau.

### Khi nào Bloom filter ít hữu ích?

- Truy vấn gần như luôn hỏi khóa **có tồn tại**: Bloom thường trả “MAYBE”, cuối cùng vẫn cần đọc dữ liệu.
- Truy vấn là **quét khoảng rộng**: filter theo từng khóa không xác định nhanh một khoảng có rỗng hay không.
- Chỉ có rất ít SSTable và chúng đã được loại nhanh nhờ **min/max** hoặc phạm vi khóa các level.
- Filter quá nhỏ so với số khóa khiến nhiều bit thành 1, tăng tỷ lệ false positive.

Khi nào filter đặc biệt đáng giá? Khi hệ thống phải xét nhiều tệp, point lookup âm tính xuất hiện thường xuyên và I/O data block là thành phần chi phí đáng kể.

## 10. Những sai lầm dễ gặp khi thiết kế hoặc phân tích

**1. Nhầm “Bloom trả true” với “khóa tồn tại”.** True chỉ nghĩa là **có thể**; luôn xác nhận trong data block hoặc cấu trúc chứa dữ liệu thật.

**2. Nghĩ chỉ mục thưa có một entry cho mỗi bản ghi.** Chỉ mục khối thông thường có entry theo **block**, đủ để thu hẹp phạm vi tìm kiếm.

**3. Bỏ qua bộ so sánh khóa.** Thứ tự byte của khóa ghép, xử lý số âm, mã hóa chuỗi hoặc collation phải nhất quán giữa lúc ghi, xây index và lúc tìm. Chỉ mục được tạo theo một thứ tự nhưng truy vấn dùng thứ tự khác có thể dẫn đến tìm sai khối.

**4. Đọc key filter khi chưa kiểm tra phiên bản/tombstone.** Bộ lọc chỉ cho biết khả năng hiện diện trong một tập khóa, không thay thế quy tắc quyết định giá trị mới nhất. Phải chặn đúng các giá trị cũ sau tombstone.

**5. Nghĩ tệp bất biến nghĩa là không thể xóa dữ liệu.** Có thể ghi tombstone vào SSTable mới và loại bỏ bản ghi trong compaction khi an toàn.

**6. Cho rằng index và filter luôn nằm trong RAM.** Chúng có thể được cache, chia partition hoặc phải đọc từ thiết bị. Các bảng chi phí phải ghi rõ giả định bộ đệm.

**7. Cho rằng mọi thứ có thứ tự thì có thể trả lời range query chỉ bằng Bloom filter.** Bloom filter thông thường không lưu thứ tự và không cho biết vị trí khối. Range scan dựa vào SSTable đã sắp và block index.

**8. Xóa trực tiếp một bit trong Bloom filter chuẩn.** Bit có thể được chia sẻ bởi nhiều khóa; xóa tùy tiện có thể tạo false negative. SSTable bất biến tạo filter mới khi tạo tệp mới.

## 11. Ví dụ thiết kế hoàn chỉnh

Một ứng dụng lưu **5 triệu sự kiện** thành nhiều SSTable. Phần lớn yêu cầu là tìm sự kiện theo ID; khoảng 30% ID được hỏi không tồn tại trong các SSTable ứng viên. Đôi khi ứng dụng cần đọc tất cả sự kiện theo một phạm vi thời gian.

Một giải pháp cơ sở:

1. **MemTable có thứ tự** nhận ghi; khi đủ lớn, flush thành SSTable bất biến. Ghi log phục hồi nếu cần bảo đảm độ bền trước khi flush.
2. **Data block** gom các mục khóa liên tiếp, có thể nén; lựa chọn kích thước block dựa trên tần suất tìm từng khóa và quét khoảng.
3. **Block index thưa** lưu separator và địa chỉ/độ dài data block; cache index hoặc index block nóng.
4. **Bloom filter** theo khóa của mỗi SSTable hoặc từng partition, đặt ngân sách bit/khóa dựa trên tỷ lệ truy vấn âm tính và mức RAM.
5. **Min/max metadata** giúp bỏ qua tệp nằm ngoài phạm vi trước khi kiểm tra Bloom.
6. **Compaction** hợp nhất các dãy đã sắp và tái tạo index/filter, đồng thời tôn trọng các phiên bản và tombstone còn cần giữ.

Để kiểm tra lựa chọn, cần đo **số data block đọc mỗi truy vấn**, tỷ lệ hit của block cache, **Bloom false-positive rate thực**, số SSTable ứng viên, thông lượng compaction, lượng byte ghi lại và độ trễ ở các phân vị. Chỉ nhìn vào độ phức tạp tìm nhị phân trong RAM sẽ bỏ qua yếu tố quyết định của dữ liệu ngoài bộ nhớ.

## 12. Bài tập thực hành và lời giải

### Bài 1 — Xác định data block

Có một SSTable với block index chứa first_key:

~~~text
B0 -> 10
B1 -> 30
B2 -> 55
B3 -> 80
~~~

Cho biết block đầu tiên cần kiểm tra để tìm khóa **58**, **30**, **8** khi dùng quy tắc **first_key lớn nhất ≤ khóa đích**.

**Lời giải:** 58 → **B2**; 30 → **B1**; 8 → **không có block ứng viên**, vì nhỏ hơn khóa đầu tiên của toàn tệp.

### Bài 2 — Không nhầm filter với dữ liệu

Bloom filter báo **MAYBE** đối với khóa 47. Block index chọn đúng data block nhưng sau khi đọc, block không có khóa 47. Có phải filter sai không?

**Lời giải:** Không. Đây là một **false positive** hợp lệ. Bloom filter không cam kết “MAYBE” là có thật. Nếu filter báo **NO** nhưng khóa thực sự có trong tập đã thêm vào đúng filter, đó mới là bất thường cần điều tra.

### Bài 3 — Dung lượng chỉ mục khối

SSTable có **600.000 mục**; trung bình **150 mục/data block**. Mỗi entry của chỉ mục khối cần **24 byte**, bỏ qua metadata khác. Ước lượng số data block và dung lượng chỉ mục.

~~~text
B = ceil(600.000 / 150) = 4.000 data block
Index = 4.000 * 24 = 96.000 byte ≈ 93,75 KiB
~~~

**Lời giải:** Khoảng **4.000 block**, chỉ mục khoảng **96 KB** (hay **93,75 KiB**), với giả định mỗi block đúng trung bình 150 mục.

### Bài 4 — Bộ lọc và tra cứu âm tính

Một truy vấn không có khóa nào trong **20 SSTable**. Mỗi Bloom filter có false-positive rate **2%**. Giả sử độc lập và mọi metadata ở RAM, kỳ vọng có bao nhiêu lượt đọc data block thừa?

~~~text
E = T * p = 20 * 0,02 = 0,4 block
~~~

**Lời giải:** Trung bình khoảng **0,4 lượt đọc data block thừa trên mỗi truy vấn âm tính**, nếu mỗi kết quả MAYBE dẫn đến đọc đúng một data block. Đây là trung bình xác suất qua nhiều truy vấn, không phải mỗi truy vấn phải đọc 0,4 khối.

### Bài 5 — Xóa và phiên bản cũ

Tệp cũ **S1** chứa **(K, "active")**. Tệp mới **S2** chứa **(K, TOMBSTONE)**. Vì sao không được bỏ tombstone khi vẫn còn S1 được xét trong đường đọc? Bloom filter của S2 phải đối xử với K thế nào?

**Lời giải:** Nếu xóa tombstone quá sớm, truy vấn có thể thấy phiên bản **"active"** cũ và trả dữ liệu đã bị xóa. Filter của S2 phải bao phủ **K** để đường đọc không bỏ qua tệp mang tombstone. Chỉ xóa tombstone khi việc hợp nhất hoặc chính sách phiên bản bảo đảm không còn dữ liệu cũ cần bị chặn, đồng thời tôn trọng snapshot.

### Bài 6 — Lựa chọn cấu trúc

Một hệ thống chỉ thực hiện các point lookup chính xác trên khóa số và rất hiếm cập nhật. Hệ thống khác liên tục ghi dữ liệu và thường xuyên quét khoảng theo thời gian. Có nên áp dụng cùng một thiết kế không?

**Lời giải gợi ý:** Không nhất thiết. Với hệ thứ nhất, bảng băm hoặc một chỉ mục thích hợp có thể rất hiệu quả; SSTable cũng có thể hoạt động tốt nếu dữ liệu tĩnh. Hệ thứ hai có thể được lợi từ MemTable + SSTable đã sắp + compaction, nhưng cần kiểm tra thứ tự khóa, chi phí hợp nhất và độ trễ khi quét. Lựa chọn nên dựa vào tỷ lệ đọc/ghi, quét khoảng, RAM dành cho index/filter và chi phí I/O.

## 13. Ghi nhớ để vận dụng

Có ba câu hỏi riêng biệt trong một phép đọc SSTable:

- **Có thể bỏ qua tệp này không?** Dùng phạm vi **min/max** và **bộ lọc khóa** để loại các tệp không thể chứa khóa.
- **Nếu phải kiểm tra, đọc khối nào?** Dùng **block index** để chọn vùng cần đọc.
- **Khóa và giá trị thật là gì, phiên bản nào đang có hiệu lực?** Đọc **data block** và áp dụng quy tắc phiên bản/tombstone.

Khi kết hợp với cấu trúc ghi trong RAM và compaction, SSTable biến luồng cập nhật thành những dãy trên thiết bị có thứ tự. Hiểu đúng **bất biến sắp xếp**, **định tuyến theo ranh giới khối** và **giới hạn của Bloom filter** giúp người học phân tích chi phí thời gian, bộ nhớ và truy cập thiết bị để chọn cấu trúc lưu trữ phù hợp với từng bài toán.

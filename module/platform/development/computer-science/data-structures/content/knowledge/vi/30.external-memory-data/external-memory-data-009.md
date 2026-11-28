# So sánh B+-tree với LSM-tree theo tải tra cứu và cập nhật

## 1. Bài toán: cùng là cấu trúc lưu trữ có thứ tự, vì sao hiệu năng khác nhau?

Trong RAM, ta thường so sánh mảng, danh sách liên kết, bảng băm, cây và heap qua số phép toán hoặc dung lượng bộ nhớ. Khi dữ liệu lớn hơn RAM và nằm trên SSD/HDD, **số lần đọc/ghi trang**, lượng dữ liệu phải viết lại và khả năng tận dụng bộ đệm (cache/buffer pool) trở thành yếu tố quyết định.

**B+-tree** và **LSM-tree** (Log-Structured Merge-tree) đều có thể hỗ trợ tra cứu theo khóa và duyệt khóa có thứ tự, nhưng dùng hai chiến lược cập nhật rất khác nhau:

- **B+-tree:** duy trì một cây chỉ mục cân bằng với các trang có thể cập nhật tại chỗ (in-place) về mặt logic. Phép ghi thường tìm đúng lá rồi sửa trang đó, đôi khi tách hoặc gộp trang.
- **LSM-tree:** tích lũy thay đổi trong cấu trúc RAM (**MemTable**), xuất thành các tệp đã sắp và bất biến (**SSTable**), rồi định kỳ hợp nhất (**compaction**) để giảm số phiên bản và số tệp phải tìm.

Sự khác nhau này tạo nên đánh đổi giữa **point lookup** (tra cứu một khóa), **range scan** (quét một khoảng khóa), **insert/update/delete**, độ trễ đuôi và **read/write/space amplification**.

Trong học phần *Cấu trúc dữ liệu*, mục tiêu không phải học thuộc “cây nào nhanh hơn”, mà là nối **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** với **đặc điểm tải công việc** để lựa chọn cấu trúc phù hợp.

### Tình huống xuyên suốt

Một hệ thống thu thập sự kiện có **20 triệu khóa**, ghi thêm liên tục, đôi khi sửa trạng thái của một sự kiện. Người dùng gửi các truy vấn:

1. “Sự kiện ID = 812345 có tồn tại không?” — **point lookup**.
2. “Lấy toàn bộ sự kiện của thiết bị A trong một giờ” — **range scan**, nếu khóa được tổ chức theo thiết bị và thời gian.
3. “Ghi thêm 50.000 sự kiện mỗi giây” — **tải ghi**.
4. “Xóa/ghi đè một khóa nhưng truy vấn sau đó phải nhìn thấy phiên bản mới” — **cập nhật và phiên bản**.

Để so sánh đúng, ta cần hiểu đường đọc/ghi của từng cấu trúc trước khi nhìn vào bảng độ phức tạp.

## 2. B+-tree: cân bằng chiều cao, truy cập theo trang

B+-tree là cây tìm kiếm nhiều nhánh (**multiway search tree**). Một nút thường được đóng trong một **trang** có kích thước cố định hoặc gần cố định. Các trang trong giữ khóa phân cách và địa chỉ trang con; các trang lá giữ các mục chỉ mục đã sắp, có thể kèm tham chiếu đến bản ghi. Các lá thường có liên kết để duyệt theo thứ tự khóa.

~~~text
                       [K30 | K60]              <- trang gốc
                     /      |       \
                    v       v        v
              [K10,K20] [K30,K45] [K60,K70]
                     \      |      /
                  Các trang lá theo thứ tự khóa
~~~

Ở hình trên, các miền khóa được phân chia qua separator. Một số separator có thể xuất hiện cả ở trang trong lẫn lá; đây là đặc điểm bình thường của B+-tree.

### Bất biến cần bảo toàn

1. **Khóa có thứ tự:** separator của trang trong xác định đúng miền khóa của các con.
2. **Các lá cùng độ sâu:** cây luôn cân bằng theo chiều cao.
3. **Sức chứa trang bị giới hạn:** trang trong có tối đa một số lượng con (**fanout**), trang lá có tối đa một số mục; trang không phải gốc thường phải đạt ngưỡng lấp đầy tối thiểu theo quy tắc triển khai.
4. **Lá đi theo thứ tự khóa:** quét lá theo liên kết cho các mục theo thứ tự tăng.
5. **Đường tìm cập nhật nhất quán:** sau tách, mượn hoặc gộp trang, separator của cha phải khớp với miền khóa mới.

### Đường đọc: từ gốc xuống một lá

~~~text
function bplus_get(root, key):
    page = read_page(root)

    while page.is_internal:
        child = choose_child_by_separators(page, key)
        page = read_page(child)

    pos = lower_bound(page.entries, key)

    if pos < page.count and page.entries[pos].key == key:
        return page.entries[pos].record_reference_or_value

    return NOT_FOUND
~~~

Đặt **N** là số mục, **f** là số con trung bình hữu hiệu của trang trong, **h** là chiều cao tính theo số cấp trang. Khi các trang được lấp đầy tương đối ổn định:

\[
h \approx O(\log_f N).
\]

Mỗi cấp cần truy cập một trang trên đường đi. Nếu gốc và một số trang trong đã nằm ở buffer pool, một truy vấn có thể chỉ phải đọc **một trang lá** từ thiết bị. Ngược lại, cache lạnh có thể phải đọc nhiều cấp.

**Chú ý:** Nếu lá của **secondary index** chỉ chứa tham chiếu bản ghi, trả về các cột không có trong chỉ mục có thể cần **đọc thêm trang dữ liệu**. Không nên đếm chỉ số trang cây rồi mặc nhiên coi toàn bộ truy vấn đã hoàn tất.

### Đường ghi: cập nhật lá và xử lý tràn/thiếu

- **Insert:** tìm đến lá, thêm mục theo thứ tự. Nếu lá đầy, tách trang và đưa separator phù hợp vào cha; sự tách có thể lan tới gốc.
- **Update:** nếu thay đổi giá trị nhưng giữ nguyên khóa và giá trị vừa trong trang, có thể sửa lá hoặc trang dữ liệu liên quan. Nếu thay đổi khóa, về logic có thể cần xóa mục cũ và chèn mục mới.
- **Delete:** xóa mục; nếu lá thiếu mức lấp đầy, có thể phân phối lại từ anh em hoặc gộp trang; thay đổi separator và có thể lan lên.

B+-tree thường làm **cập nhật tập trung vào một đường đi và vài trang gần nó**, thay vì ghi lại toàn bộ dãy đã sắp. Tuy nhiên, ghi trực tiếp vào trang đang chứa nhiều mục có thể sinh **I/O ngẫu nhiên**, phân mảnh trang, tranh chấp latch trên trang nóng hoặc chi phí phân tách.

Một B+-tree có giao dịch thường đi kèm **write-ahead log (WAL)**, bộ đệm và cơ chế phục hồi. “Cập nhật tại chỗ” mô tả tổ chức dữ liệu logic, **không có nghĩa** mỗi thao tác lập tức ghi đúng một trang vật lý và không dùng log.

### Range scan

Muốn lấy các khóa trong đoạn **[a, b]**, hệ thống tìm lá chứa khóa đầu tiên không nhỏ hơn **a**, sau đó đi tiếp các lá cho đến khi gặp khóa lớn hơn **b**:

~~~text
seek(a) -> leaf 17 -> leaf 18 -> leaf 19 -> ... -> stop at key > b
~~~

Nếu một lá chứa trung bình **b** mục và kết quả có **k** mục liên tục, chi phí đọc các trang chỉ mục xấp xỉ:

\[
O(h+\lceil k/b\rceil)
\]

với giả định lấp đầy tương đối ổn định, đã biết điểm bắt đầu và không tính đọc các trang bản ghi ở ngoài chỉ mục. Liên kết lá là **liên kết logic**: không bảo đảm các trang vật lý nằm cạnh nhau, dù buffer pool và prefetch có thể hỗ trợ.

## 3. LSM-tree: chuyển nhiều ghi nhỏ thành ghi theo đợt

LSM-tree không phải một cây tìm kiếm nhiều nhánh duy nhất như B+-tree. Nó là một **kiến trúc gồm nhiều thành phần có thứ tự**:

- **MemTable:** nhận ghi trong RAM, thường dùng skip list, cây cân bằng hoặc cấu trúc khác.
- **WAL:** thường ghi nối đuôi để có thể phục hồi các cập nhật chưa flush.
- **SSTable:** tệp đã sắp và **bất biến**; mỗi tệp thường có block index, metadata về khoảng khóa và bộ lọc khóa (ví dụ Bloom filter).
- **Compaction:** hợp nhất các SSTable, loại phiên bản không cần nữa khi an toàn và tạo ra các tệp mới.

~~~text
                  PUT / DELETE / UPDATE
                           |
                   +-------+-------+
                   |               |
              WAL (append)     MemTable (RAM)
                                   |
                            đầy -> flush
                                   v
                  L0: [SST A] [SST B] [SST C]
                       vùng khóa có thể chồng lấn
                                   |
                           compaction
                                   v
                  L1: [SST D] [SST E] [...]
                                   |
                           compaction
                                   v
                  L2: [SST F] [SST G] [...]
~~~

Hình minh họa **leveled LSM**: ở L0 có thể có các SSTable chồng lấn miền khóa; tại những level sâu hơn, nhiều triển khai duy trì các tệp có miền khóa **không chồng lấn trong cùng level**. Những chính sách khác như **tiering** hoặc hybrid cho phép nhiều run chồng lấn hơn. Không nên lấy sơ đồ của một chính sách làm bất biến cho mọi LSM-tree.

### Đường ghi

~~~text
function lsm_put(key, value):
    append_wal_record(key, value)  // theo chính sách độ bền
    memtable.insert_or_replace(key, value)

    if memtable_is_full():
        schedule_flush_to_new_sstable()
~~~

Ghi một cập nhật vào MemTable thường chỉ tốn thao tác trong RAM, và ghi WAL có thể được gom thành các đợt nối đuôi. Khi đầy, MemTable được xuất thành SSTable theo thứ tự khóa. Tệp cũ **không phải sửa tại chỗ** để lưu phiên bản mới.

**Nhưng ghi không biến mất:** về sau, compaction đọc nhiều SSTable và ghi lại các mục vào tệp mới. Cách tổ chức này **dịch chuyển** phần lớn công việc sắp xếp/ghi lại sang nền và gom chúng thành I/O tuần tự. Vì thế thông lượng ghi cao không đồng nghĩa chi phí ghi vật lý luôn thấp.

### Đường đọc

Một phép GET phải chọn **phiên bản hợp lệ mới nhất** theo quy tắc thứ tự ghi và snapshot:

~~~text
function lsm_get(key, snapshot):
    result = seek_visible_entry_in_memtables(key, snapshot)
    if result is authoritative:
        return resolve_value_or_tombstone(result)

    for candidate_table in version_aware_search_order:
        if key_outside_table_range(candidate_table, key):
            continue

        if candidate_table.filter_says_definitely_absent(key):
            continue

        entry = seek_in_table(candidate_table, key, snapshot)

        if entry is a visible latest value:
            return entry.value

        if entry is an authoritative visible tombstone:
            return NOT_FOUND

    return NOT_FOUND
~~~

Mã giả mô tả **một thứ tự đọc hợp lệ khi đã được hệ thống bảo đảm về phiên bản**. Trong triển khai thực tế, không thể chỉ dựa vào thời gian tạo file: các phiên bản được phân biệt bằng sequence number, level, snapshot và chính sách compaction. Tùy hệ thống, có thể phải tập hợp ứng viên rồi xác định phiên bản mới nhất trước khi kết luận.

**Bloom filter** giúp trả lời “khóa **chắc chắn không có trong SSTable này**” hoặc “**có thể có**”. Kết quả *có thể có* phải được xác nhận bằng đọc data block. Bloom filter chuẩn có thể có **false positive**, nhưng không được có **false negative** khi xây dựng và sử dụng đúng. Filter là công cụ **tránh đọc dữ liệu vắng mặt**, không lưu giá trị hay xác nhận khóa tồn tại.

### Xóa bằng tombstone

Giả sử:

~~~text
SSTable cũ:  (A, 10)   (B, 20)
MemTable mới:          (B, TOMBSTONE)
~~~

Truy vấn **B** phải trả **không tồn tại**, vì tombstone mới hơn phủ lên giá trị cũ. Không được bỏ qua tombstone rồi “hồi sinh” bản ghi cũ. Compaction chỉ loại bỏ tombstone khi đã chắc chắn không còn phiên bản cũ cần bị che khuất và không vi phạm snapshot/điều kiện giữ lịch sử.

### Range scan

Mỗi MemTable/SSTable đã sắp có một iterator. Truy vấn khoảng tạo iterator tại khóa bắt đầu, rồi **hợp nhất nhiều dãy đã sắp** (thường dùng heap), loại các phiên bản cũ và tôn trọng tombstone:

~~~text
iterator M (MemTable) ->  [13, 22, 34, ...]
iterator S1         ->  [10, 22, 31, ...]
iterator S2         ->  [11, 20, 34, ...]
                              |
                       merge theo khóa,
                    phiên bản và snapshot
                              |
                              v
                  [10, 11, 13, 20, 22, 31, 34, ...]
~~~

Sơ đồ chỉ minh họa **hợp nhất thứ tự**; kết quả thật phải bỏ khóa bị xóa và chọn đúng phiên bản cho các khóa trùng. Nếu có nhiều run chồng lấn và nhiều khóa cũ, range scan có thể phải đọc **nhiều mục hơn số mục thực sự trả về**, đồng thời tốn CPU cho bước merge. Một LSM đã compaction tốt với phạm vi tệp hẹp có thể giảm đáng kể chi phí này.

## 4. So sánh theo thao tác

| Thao tác/đặc tính | B+-tree | LSM-tree |
| --- | --- | --- |
| **Điểm mạnh cốt lõi** | Đường tìm ngắn, dữ liệu có thứ tự trên các lá, cập nhật trực tiếp theo trang | Gom cập nhật trong RAM, xuất tệp bất biến và hợp nhất theo đợt |
| **Tìm một khóa tồn tại** | Đi theo một đường gốc → lá; thường ít trang nếu cấp trên được cache | Kiểm tra MemTable và các SSTable ứng viên; index/filter/cache quyết định số khối |
| **Tìm một khóa không tồn tại** | Vẫn đến lá/miền khóa phù hợp để kết luận | Có thể bỏ qua nhiều SSTable nhờ min/max và Bloom filter |
| **Quét khoảng khóa** | Seek một lần rồi duyệt lá có thứ tự | Seek các run liên quan rồi merge; có thể phải xử lý phiên bản cũ |
| **Chèn/cập nhật đơn lẻ** | Sửa trang chứa khóa; đôi khi tách/gộp và cập nhật tổ tiên | Ghi WAL + MemTable, flush và compaction về sau |
| **Nhiều ghi ngẫu nhiên** | Có thể đụng nhiều trang lá, tăng I/O ngẫu nhiên | Thường gom thành các đợt ghi tuần tự; chịu chi phí compaction |
| **Xóa** | Có thể xóa mục khỏi lá và cân bằng lại cây | Thường ghi tombstone rồi thu dọn khi compaction an toàn |
| **Lặp lại nhiều lần trên một khóa** | Có thể cập nhật cùng trang nóng nhiều lần | Tích lũy phiên bản; nhiều cập nhật có thể được gộp trước/trong compaction |
| **Bộ nhớ hỗ trợ** | Cache trang gốc, trang trong, lá, bản ghi | MemTable, block cache, index/filter cache và compaction buffer |
| **Chi phí nền** | Dọn trang, checkpoint/vacuum/maintenance tùy hệ thống | Flush và compaction là một phần trọng yếu của thiết kế |
| **Độ trễ đuôi** | Chịu ảnh hưởng cache miss, trang nóng, tách/gộp và ghi bền | Chịu ảnh hưởng compaction, backlog flush, stall và số run cần tra |
| **Quản lý không gian** | Khoảng trống trong trang, trang đã xóa, phân mảnh | Nhiều bản sao/phiên bản/tombstone trong thời gian chờ compaction |

Bảng này mô tả **xu hướng thiết kế**, không phải bảng xếp hạng hiệu năng tuyệt đối. Cả hai cấu trúc có nhiều biến thể; thông lượng và độ trễ còn phụ thuộc bộ đệm, thiết bị, bộ máy giao dịch, cấu hình và cách đo.

## 5. Hiểu đúng ba dạng “amplification”

Để so sánh kho dữ liệu trên thiết bị, cần phân biệt **công việc logic mà ứng dụng yêu cầu** và **công việc vật lý mà hệ thống thật thực hiện**.

### 5.1. Read amplification — đọc nhiều hơn yêu cầu

Ví dụ ứng dụng yêu cầu **một giá trị**, nhưng phải đọc thêm nhiều index page, data block hoặc phiên bản:

- **B+-tree:** đường đi qua các cấp cây; cache các cấp trên giảm số I/O. Secondary index có thể phải fetch thêm bản ghi nằm ở trang khác.
- **LSM-tree:** có thể kiểm tra nhiều SSTable, bao gồm tệp trả false positive từ Bloom filter; range scan có thể đọc nhiều phiên bản cũ để tạo kết quả hợp lệ.

Cách đo thực tế: **số khối/byte đọc từ thiết bị trên mỗi truy vấn logic**, tách đọc index, data block và bản ghi nếu có thể. Nên quan sát **cả cache hit/miss** để biết vì sao số liệu thay đổi.

### 5.2. Write amplification — ghi vật lý nhiều hơn dữ liệu logic

Định nghĩa đo lường thường dùng là:

\[
WA = \frac{\text{số byte thực sự ghi xuống thiết bị trong khoảng đo}}
          {\text{số byte dữ liệu logic ứng dụng ghi trong khoảng đo}}.
\]

Cần nêu rõ tử số có gồm WAL, metadata, checkpoint và compaction hay không; các hệ thống có cách báo chỉ số không hoàn toàn giống nhau.

- **B+-tree:** một bản cập nhật nhỏ có thể khiến trang lớn bị ghi lại; còn có WAL, trang bị tách/gộp và dữ liệu phân mảnh.
- **LSM-tree:** một mục có thể được ghi khi flush và **ghi lại nhiều lần** khi đi qua các lần compaction, ngoài WAL và metadata.

Không được kết luận “LSM luôn có write amplification thấp hơn B+-tree”: LSM thường **tốt cho gom nhiều cập nhật**, nhưng compaction nhiều tầng có thể làm WA lớn. B+-tree có buffer cache, batch và cơ chế ghi tối ưu cũng có thể đạt hiệu quả cao.

### 5.3. Space amplification — dung lượng vượt dữ liệu sống

Ví dụ ứng dụng lưu 100 GB dữ liệu đang còn hiệu lực nhưng thiết bị cần 160 GB cho dữ liệu, chỉ mục, bản sao tạm, tombstone và vùng trống. Tùy định nghĩa, hệ thống có thể nói tỷ số **1,6 lần** hoặc phần dư **60%**.

- **B+-tree:** chi phí từ trang chưa lấp đầy, index, vùng trống sau xóa và thông tin quản lý.
- **LSM-tree:** chi phí từ nhiều phiên bản chưa compaction, tệp cũ/mới cùng tồn tại trong hợp nhất, tombstone, index/filter và snapshot.

**Quan hệ đánh đổi:** ép LSM compaction mạnh hơn có thể giảm read/space amplification nhưng tăng write amplification. Trì hoãn compaction để ghi nhanh hơn có thể làm nhiều run tồn tại, tăng chi phí đọc. B+-tree cũng có đánh đổi giữa độ lấp đầy trang, số lần split và chi phí cập nhật.

## 6. Mô hình chi phí và giả định cần ghi rõ

Đặt:

- **N:** số mục đang được chỉ mục hoặc lưu trữ.
- **f:** fanout hữu hiệu của trang trong B+-tree.
- **b:** số mục trung bình mỗi trang lá B+-tree hoặc mỗi data block của SSTable, tùy ngữ cảnh.
- **h:** số cấp của B+-tree tính cả gốc và lá.
- **R:** số SSTable/run có thể cần xét cho một khóa hoặc khoảng.
- **k:** số mục kết quả cần trả về.
- **p:** tỷ lệ false positive của Bloom filter cho khóa **thật sự không có** trong tệp đang xét.

### 6.1. B+-tree

Trong mô hình trang, với độ lấp đầy ổn định:

\[
h = O(\log_f N).
\]

| Thao tác | Mô hình chi phí |
| --- | --- |
| Point lookup | \(O(h)\) lượt truy cập trang trên đường đi; I/O vật lý ít hơn nếu cache tốt |
| Insert/update/delete | \(O(h)\) để định vị lá, cộng ghi các trang bị tác động; split/merge có thể lan theo đường tổ tiên |
| Range scan trả k mục liên tục | \(O(h + \lceil k/b\rceil)\) lượt truy cập trang **chỉ mục** trong mô hình thuận lợi |

Với các bản ghi nằm ngoài lá (secondary index), phải cộng chi phí đọc **trang dữ liệu thực**; một range scan nhiều RID phân tán có thể phát sinh rất nhiều I/O ngẫu nhiên.

### 6.2. LSM-tree

LSM không có một công thức chi phí duy nhất nếu chưa xác định **MemTable, chính sách level/tier, kích thước SSTable, filter, cách cache, snapshot và compaction**.

| Thao tác | Mô hình chi phí |
| --- | --- |
| Ghi một mục | Cập nhật MemTable trong RAM + append WAL theo chính sách độ bền; flush/compaction tạo I/O amortized về sau |
| Point lookup | Tìm MemTable; kiểm tra một số SSTable ứng viên theo phiên bản, phạm vi khóa và filter; đọc data block khi cần |
| Khóa vắng trong R SSTable | Nếu R filter độc lập có cùng tỷ lệ false positive p, số data block đọc thừa **kỳ vọng** xấp xỉ \(R p\), khi mỗi dương tính giả gây một lần đọc |
| Range scan | Định vị điểm bắt đầu của các run liên quan, đọc các khối liên tiếp và merge; xử lý thêm phiên bản cũ, tombstone |
| Compaction | Đọc và ghi lại các dãy đã sắp; khối lượng tùy số level, tỷ lệ tăng kích thước và chính sách hợp nhất |

Nếu **r** run đồng thời tham gia range scan, k-way merge dùng heap có thể tốn khoảng **O(x log r)** thao tác CPU với **x** là số entry thực tế được xử lý. Thường **x ≥ k** vì có phiên bản cũ và tombstone. Chi phí I/O phụ thuộc số data block ở từng run được quét, không chỉ số kết quả k.

**Tuyệt đối không thay mọi trường hợp LSM bằng một công thức “O(1) ghi, O(log N) đọc”** khi phân tích thiết bị. Độ phức tạp RAM của MemTable không thể hiện chi phí compaction và các lần đọc/ghi khối.

### 6.3. Ví dụ fanout B+-tree

Giả sử **1.000.000 mục**, một lá B+-tree chứa trung bình **100 mục** và mỗi trang trong có trung bình **100 con**:

~~~text
Số lá:                  ceil(1.000.000 / 100) = 10.000
Trang trong phía trên:  ceil(10.000 / 100)    = 100
Gốc:                   1 trang đủ trỏ đến 100 trang trong

Cấp 1: gốc
Cấp 2: 100 trang trong
Cấp 3: 10.000 lá
=> Chiều cao: 3 cấp trang.
~~~

Với cache lạnh, point lookup sẽ đi qua khoảng **3 trang cây**. Nếu gốc và trang trong đã được cache, có thể chỉ cần **1 lần đọc trang lá** để tìm khóa. Đây là ví dụ giả định, không phải số đo chung cho mọi thiết kế B+-tree.

### 6.4. Ví dụ Bloom filter trong LSM-tree

Giả sử một khóa thực sự **không có trong 12 SSTable ứng viên**, tất cả filter đã nằm trong RAM, tỷ lệ false positive mỗi filter là **1%** và mọi kết quả dương tính giả buộc đọc một data block:

\[
E[\text{đọc data block thừa}] \approx R p=12\times0{,}01=0{,}12.
\]

Trong nhiều truy vấn âm tính, trung bình sẽ phát sinh khoảng **0,12 lần đọc data block thừa mỗi truy vấn**, trước khi tính cache dữ liệu. Đây **không có nghĩa** mỗi truy vấn đọc được “0,12 khối” hoặc LSM luôn chỉ đọc 0,12 khối: nếu filter chưa được cache, có thể có I/O metadata; nếu khóa thật sự có trong một SSTable thì phải đọc khối tương ứng; nếu một số tệp có miền khóa loại trừ khóa, số ứng viên giảm.

Với giả định các sự kiện false positive độc lập:

\[
P(\text{ít nhất một false positive})=1-(1-p)^R
  =1-0{,}99^{12}\approx11{,}36\%.
\]

Kết quả phản ánh **rủi ro phải kiểm tra khối không cần thiết** đối với truy vấn âm tính. Bloom filter không giúp ích nhiều khi truy vấn dương tính chiếm phần lớn, vì filter vẫn trả **MAYBE** cho khóa thực sự có.

## 7. Leveling và tiering: cùng tên LSM, khác hiệu năng

Các SSTable được phân nhóm thành level/run theo chính sách compaction. Hai họ chiến lược thường gặp:

| Đặc điểm | Leveling | Tiering |
| --- | --- | --- |
| Bố trí dữ liệu | Các level sâu thường giữ những SSTable có miền khóa không chồng lấn trong cùng level | Cho phép nhiều run cùng tồn tại và có thể chồng lấn miền khóa |
| Tìm chính xác | Thường ít ứng viên hơn ở level sâu | Có thể phải xem nhiều run hơn |
| Quét khoảng | Thường ít dãy trùng lặp cần merge hơn | Có thể cần merge nhiều dãy, nhiều phiên bản cũ |
| Compaction | Có thể ghi lại dữ liệu nhiều hơn vì hợp nhất với vùng đã tồn tại ở level đích | Có thể gom nhiều run lớn khi đủ điều kiện, thường giảm tần suất ghi lại trong một số tải |
| Đánh đổi thường thấy | Ưu tiên đọc/không gian hơn, có thể tăng write amplification | Ưu tiên giảm ghi compaction, có thể tăng read/space amplification |

Một hệ thống có thể sử dụng **lai ghép**: tiering ở level nhỏ và leveling ở level sâu, hoặc điều chỉnh compaction theo tải. Kích thước level tăng theo một tỷ số **T** là tham số thiết kế quan trọng, nhưng chỉ từ T không thể dự đoán chính xác hiệu năng mà không biết chính sách tệp, kích thước bộ đệm và thứ tự truy cập.

**Thông điệp chính:** Khi một người nói “LSM-tree đọc chậm” hoặc “LSM-tree ghi nhanh”, cần hỏi ngay **LSM đang dùng chính sách compaction nào và có bao nhiêu SSTable/run cần đọc?**

## 8. Quyết định theo tải công việc

### 8.1. Chủ yếu point lookup, ít cập nhật

Giả sử hệ thống đọc khóa chính xác rất thường xuyên, cập nhật hiếm, yêu cầu thời gian phản hồi ổn định ở phân vị cao.

**B+-tree thường là ứng viên mạnh:** một đường gốc → lá có chiều cao thấp, các trang trong dễ nằm trong RAM; không cần quét qua nhiều phiên bản của nhiều tệp để xác định giá trị mới nhất.

**LSM-tree vẫn có thể cạnh tranh:** khi Bloom filter/index cache hiệu quả, miền khóa ở các level không chồng lấn nhiều và compaction được giữ ổn định. Đặc biệt, nếu một tỷ lệ đáng kể truy vấn là **miss**, Bloom filter có thể tránh nhiều lượt đọc data block.

Câu hỏi cần đo: **point lookup hit/miss ratio, trang trên mỗi GET, cache hit, p95/p99 latency và số tệp ứng viên**.

### 8.2. Tải ghi ngẫu nhiên cao, đọc có thể chấp nhận thêm bước

Giả sử liên tục tạo bản ghi mới và cập nhật nhiều khóa khác nhau, thiết bị có chi phí truy cập ngẫu nhiên đáng kể.

**LSM-tree thường có lợi về tổ chức ghi:** WAL nối đuôi, MemTable gom cập nhật, flush tạo tệp có thứ tự, compaction ghi thành những đợt lớn. Có thể đạt thông lượng ghi tốt nếu bộ máy có đủ I/O nền.

**B+-tree** vẫn có thể hoạt động tốt nhờ cache, batch, ghi WAL và phân bố trang hợp lý, nhưng nếu mỗi cập nhật rơi vào một lá khác nhau thì buffer miss và ghi trang ngẫu nhiên dễ tăng.

Câu hỏi cần đo: **write throughput bền vững, byte ghi vật lý/byte logic, compaction backlog, stalls và độ trễ ghi ở p99**. Nếu compaction không theo kịp tốc độ sinh SSTable, lợi thế ghi trước mắt có thể đổi thành đột biến độ trễ về sau.

### 8.3. Quét khoảng lớn hoặc trả kết quả theo thứ tự

Nếu yêu cầu là “lấy tất cả giao dịch của khách hàng X trong tháng, sắp theo thời điểm”, cả hai đều có thể khai thác **thứ tự khóa** khi khóa ghép là **(customer_id, timestamp)**.

- **B+-tree:** seek một lần tới khóa bắt đầu rồi đọc lá liên tiếp. Nếu chỉ mục chứa đủ cột, truy vấn có thể ít cần truy hồi dữ liệu ngoài chỉ mục.
- **LSM-tree:** seek các run có phạm vi liên quan, merge những dãy đã sắp, bỏ tombstone/phiên bản cũ. Nếu compaction tốt và số run nhỏ, hiệu năng có thể cạnh tranh; nếu nhiều run chồng lấn, CPU và I/O thêm có thể lớn.

**Thứ tự trường trong khóa ghép** quan trọng ở cả hai: chỉ mục theo **(device_id, timestamp)** phù hợp với khoảng thời gian của **một thiết bị** nhưng có thể không tối ưu cho mọi dữ liệu ở một thời điểm khi không lọc device_id.

### 8.4. Cập nhật lặp lại nhiều lần trên cùng khóa

Nếu một khóa bị cập nhật hàng trăm lần trước khi giá trị được đọc:

- **B+-tree:** có thể sửa cùng một trang nóng trong buffer; điều này giảm nhiều cache miss nhưng có thể tạo tranh chấp nếu nhiều luồng cập nhật cùng vùng.
- **LSM-tree:** MemTable có thể gộp nhiều cập nhật trước flush; các phiên bản đã flush thành SSTable có thể còn tồn tại và bị xử lý ở compaction. Việc gộp trong MemTable phụ thuộc chính sách phiên bản và snapshot.

Không nên dựa chỉ vào số lần ghi logic. Phải xét **tỷ lệ giá trị được ghi lại, kích thước value, snapshot, chu kỳ flush và lịch compaction**.

### 8.5. Cần vừa ghi nhiều vừa duy trì độ trễ đọc ổn định

Đây là trường hợp khó nhất: LSM có thể đạt thông lượng ghi cao nhưng compaction tạo thêm cạnh tranh I/O; B+-tree có thể cho đường đọc rõ ràng nhưng dễ chịu ảnh hưởng của cập nhật trang nóng và split.

Cả hai cần cơ chế quản trị tải: giới hạn đợt ghi, cache, phân vùng (partition/shard), lịch tác vụ nền và kiểm soát đồng thời. Quyết định phải dựa trên đo đạc dưới **cùng mức tải đồng thời và cùng yêu cầu bền vững**.

## 9. Bảng lựa chọn nhanh dựa trên đặc điểm tải

| Đặc điểm tải quan sát được | Ưu tiên khảo sát trước | Cần kiểm chứng |
| --- | --- | --- |
| 90–95% đọc khóa chính xác, phần lớn hit, ít cập nhật | B+-tree | Cache cấp trong, fetch bản ghi, p99 |
| Chủ yếu ghi append/update trên rất nhiều khóa, chấp nhận compaction nền | LSM-tree | WA, backlog compaction, stall |
| Truy vấn âm tính nhiều trên tập SSTable lớn | LSM có Bloom filter phù hợp | Chi phí filter/index, false positive, số ứng viên thực |
| Quét khoảng dài, yêu cầu thứ tự ổn định, cập nhật vừa phải | B+-tree hoặc LSM đã tối ưu range scan | Read amp, fetch bản ghi, số run cần merge |
| Cập nhật giá trị nhỏ rải rác trên tập khóa lớn | Đánh giá cả hai | Cache page của B+-tree so với compaction của LSM |
| Khối lượng ghi biến động mạnh, có đỉnh lớn | LSM có khả năng hấp thụ ghi theo đợt | RAM MemTable, flush rate, compaction debt |
| Thiết bị hoặc bộ nhớ có giới hạn chặt | Không thể chọn chỉ bằng tên cấu trúc | RAM cho index/filter/cache, byte I/O và dung lượng dự phòng |

Bảng là **điểm khởi đầu để lập giả thuyết**, không phải kết luận thay cho benchmark. Ví dụ, workload “95% đọc” có thể gồm 95% **miss** hoặc 95% **hit**, và hai kiểu đọc đó có thể ưu ái cấu hình khác nhau.

## 10. Ví dụ so sánh có kiểm soát

Giả sử ta xây dịch vụ khóa–giá trị với 20 triệu khóa, một số giá trị được cập nhật nhiều lần. Hai cách triển khai đều dùng cùng loại SSD, kích thước bộ đệm và bảo đảm ghi bền tương đương.

### Thiết kế A: B+-tree

- Trang trong chứa separator và con; trang lá chứa khóa và tham chiếu/giá trị.
- Bộ đệm ưu tiên các trang gốc, cấp trong và vùng lá nóng.
- Thao tác ghi đi qua WAL, cập nhật trang, xử lý split/merge khi cần.
- Range scan tìm lá đầu rồi đi theo lá kế.

### Thiết kế B: LSM-tree

- WAL + MemTable, flush thành SSTable bất biến.
- SSTable có chỉ mục khối và Bloom filter; các level được compaction.
- Bộ đệm dành cho MemTable, cache filter/index và data block nóng.
- Range scan lấy iterator của các run liên quan rồi merge theo khóa/phiên bản.

### So sánh theo ba đợt tải

| Đợt | Tải giả định | Kỳ vọng cần kiểm chứng |
| --- | --- | --- |
| A | 95% GET, 5% PUT; tỷ lệ khóa tồn tại cao | B+-tree có thể có đường đọc ổn định; LSM vẫn tốt nếu ít tệp ứng viên và cache hiệu quả |
| B | 15% GET, 80% PUT, 5% DELETE; khóa phân bố rộng | LSM có thể tăng thông lượng ghi nhờ gom I/O; phải theo dõi compaction và write stalls |
| C | 40% quét khoảng, 40% GET, 20% PUT | B+-tree được lợi từ lá liên kết; LSM phụ thuộc số run/phiên bản phải hợp nhất và phạm vi quét |

**Không gán trước số IOPS hay thời gian phản hồi** cho các đợt này: đó là kết quả phải đo trên triển khai thật, vì cấu hình, dữ liệu và cache có thể đảo thứ tự.

### Những gì bắt buộc phải giữ giống nhau khi benchmark

1. **Cùng dữ liệu và phân bố khóa:** khóa ngẫu nhiên hay tăng dần, số khóa sống, độ dài khóa/giá trị, tỷ lệ khóa nóng.
2. **Cùng yêu cầu độ bền:** ví dụ cùng cam kết về WAL/fsync; so “ghi đã bền” với “ghi chỉ trong RAM” sẽ sai.
3. **Cùng phần cứng và ngân sách RAM:** RAM được dùng cho page cache/index/filter/MemTable phải được tính công bằng.
4. **Cùng dạng truy vấn:** phân biệt point hit, point miss, range scan ngắn/dài và có/không đọc bản ghi ngoài chỉ mục.
5. **Đo sau khi hệ thống ổn định:** đặc biệt với LSM, phải tính cả trạng thái compaction liên tục, không chỉ thời gian chạy nhanh trước khi backlog hình thành.
6. **Cùng mức đồng thời và thời gian chạy đủ dài:** đo p50/p95/p99 latency, throughput và stalls trong cả chu kỳ tải.

### Chỉ số tối thiểu nên thu thập

| Nhóm chỉ số | Vì sao cần |
| --- | --- |
| GET hit/miss, p50/p95/p99 latency | Tách tra cứu có dữ liệu và không có dữ liệu |
| PUT/DELETE throughput, p99 latency | Hiểu tốc độ ghi ổn định và các đột biến |
| Số block/page đọc và byte đọc mỗi truy vấn | Đo read amplification thực tế |
| Byte ghi vật lý / byte ghi logic | Đo write amplification với định nghĩa nhất quán |
| Dung lượng live, on-disk, tạm thời | Đo space amplification |
| Cache hit ratio (page/index/filter/data) | Giải thích khác biệt giữa cache lạnh và nóng |
| Số SSTable ứng viên, thời gian/byte compaction | Hiểu chi phí đọc và công việc nền của LSM |
| Số lần split/merge, hot-page contention | Hiểu biến động cập nhật của B+-tree |

## 11. So sánh theo mặt bằng thiết bị và mô hình dữ liệu

### SSD và HDD

HDD phạt truy cập ngẫu nhiên nhiều hơn đọc tuần tự; do đó khả năng gom ghi thành luồng lớn của LSM thường đặc biệt có ích. SSD giảm độ trễ truy cập ngẫu nhiên, khiến B+-tree cạnh tranh tốt hơn trong nhiều tình huống. Tuy nhiên SSD vẫn có giới hạn IOPS, băng thông, độ bền ghi và độ trễ đuôi; compaction cũng tiêu tốn tài nguyên SSD.

Không có kết luận “SSD làm LSM không cần thiết” hay “HDD luôn phải dùng LSM”. Sự phù hợp tùy cường độ ghi, độ dài quét, cache và yêu cầu phục hồi.

### Chỉ mục thứ cấp và truy vấn nhiều cột

B+-tree thường được dùng như chỉ mục có thứ tự trong cơ sở dữ liệu quan hệ. Nếu chỉ mục lá chỉ chứa **RID/khóa chính**, truy vấn phải đọc thêm trang chứa bản ghi. LSM cũng có thể hỗ trợ chỉ mục thứ cấp tùy thiết kế hệ thống, nhưng phải đồng bộ cập nhật giữa các cấu trúc và quản lý phiên bản.

Ví dụ truy vấn:

~~~sql
SELECT event_id, payload
FROM events
WHERE device_id = 42
  AND event_time >= '2026-01-01'
  AND event_time <  '2026-02-01'
ORDER BY event_time;
~~~

Khóa ghép **(device_id, event_time)** giúp hai kiểu lưu trữ định vị vùng khóa và đọc theo thời gian cho **một** thiết bị. Tuy nhiên nếu **payload** nằm ngoài chỉ mục, chi phí truy hồi payload có thể vượt chi phí duyệt cây/SSTable. Định dạng bản ghi, độ lớn giá trị và bố trí dữ liệu có thể quan trọng hơn nhãn “B+-tree hay LSM-tree”.

### Phục hồi và snapshot

Cả hai có thể cung cấp độ bền và đọc nhất quán nếu **hệ thống xung quanh** được thiết kế đầy đủ: WAL, điểm checkpoint, metadata, quy tắc đồng bộ, giao dịch và kiểm soát phiên bản. B+-tree không tự động có ACID; LSM-tree không tự động kém nhất quán.

Snapshot có thể giữ nhiều phiên bản cũ lâu hơn, làm tăng nhu cầu lưu trữ và ảnh hưởng compaction của LSM. Hệ thống B+-tree dùng MVCC cũng cần giữ lịch sử phiên bản hoặc vùng dữ liệu tương ứng. Đây là vấn đề của **cấu trúc cộng với chính sách giao dịch**, không chỉ của một thao tác tìm kiếm.

## 12. Các kết luận sai thường gặp

**Sai lầm 1 — “B+-tree luôn đọc nhanh hơn LSM-tree”.** B+-tree có đường đi rõ ràng; LSM có thể lọc truy vấn âm tính rất hiệu quả và cache/compaction tốt. Cần so với cùng hit ratio và cùng ngân sách RAM.

**Sai lầm 2 — “LSM ghi O(1), nên luôn ghi nhanh”.** Chi phí MemTable chỉ là phần đầu. WAL, flush, compaction, stalls và thao tác phục hồi làm nên chi phí thực.

**Sai lầm 3 — “B+-tree chỉ dùng cho RAM, LSM mới dành cho ổ đĩa”.** Cả hai là cấu trúc chủ lực cho dữ liệu ngoài bộ nhớ; B+-tree thiết kế theo trang để giảm chiều cao và số I/O.

**Sai lầm 4 — “Bloom filter trả true nghĩa là có khóa”.** True chỉ là **MAYBE**; phải đọc dữ liệu để xác nhận. False positive không làm sai kết quả, chỉ phát sinh thêm việc.

**Sai lầm 5 — “Range scan trên LSM chỉ quét một tệp có thứ tự”.** Dữ liệu có thể nằm ở nhiều SSTable/run; cần merge và chọn phiên bản hợp lệ.

**Sai lầm 6 — “Chỉ cần tối ưu thời gian trung bình”.** Tải thực tế có thể yêu cầu p99 hoặc p99.9; một đợt compaction hay trang nóng có thể quyết định chất lượng dịch vụ.

**Sai lầm 7 — “B+-tree sửa một khóa thì chỉ ghi vài byte”.** Việc sửa logic có thể đòi ghi lại trang, WAL, metadata hoặc trang bị split; nên đo byte ghi vật lý.

**Sai lầm 8 — “LSM xóa là bỏ ngay bản ghi khỏi mọi tệp”.** Xóa thường dùng tombstone; việc giải phóng không gian diễn ra sau, khi compaction và snapshot cho phép.

**Sai lầm 9 — “LSM nào cũng có cùng đặc tính”.** Leveling, tiering, bộ lọc, số run và chính sách compaction ảnh hưởng trực tiếp tới đường đọc/ghi.

## 13. Bài tập thực hành có đáp án

### Bài 1 — Tính đường đi trong B+-tree

Một B+-tree lưu **2.000.000 mục**, mỗi lá chứa trung bình **200 mục**, mỗi trang trong chứa trung bình **100 con**. Ước lượng số cấp trang, giả định có thể bố trí cân bằng và lấp đầy như mô hình.

**Lời giải:**

~~~text
Số lá   = ceil(2.000.000 / 200) = 10.000
Cấp cha = ceil(10.000 / 100)    = 100 trang
Gốc     = 1 trang trỏ tới 100 trang cha
=> 3 cấp: gốc -> trong -> lá
~~~

Nếu gốc và trang trong đã có trong RAM, một GET trên chỉ mục có thể chỉ cần **1 data-page I/O tới lá** (trừ đọc bản ghi ngoài chỉ mục).

### Bài 2 — Bloom filter và chi phí đọc âm tính

Một truy vấn âm tính phải xét **15 SSTable**, mỗi filter có false-positive rate **2%**; giả sử độc lập, các filter đều ở RAM và một false positive dẫn đến một lần đọc data block.

**Hỏi:** kỳ vọng số lượt đọc block thừa là bao nhiêu?

**Lời giải:**

~~~text
E[unnecessary data block reads] = 15 * 0,02 = 0,3
~~~

Đây là **kỳ vọng trung bình**, không phải số khối mà một truy vấn cụ thể phải đọc. Nếu phạm vi khóa loại bớt tệp, số ứng viên nhỏ hơn và kỳ vọng giảm.

### Bài 3 — Chọn kiến trúc cho nhật ký sự kiện

Một dịch vụ nhận dữ liệu cảm biến liên tục, gần như chỉ chèn bản ghi mới. Thỉnh thoảng cần đọc một dải thời gian dài; hiếm khi sửa mục cũ. Bạn sẽ thử cấu trúc nào trước? Những số liệu nào cần đo?

**Lời giải gợi ý:** **LSM-tree** là ứng viên tốt để thử nhờ ghi theo đợt và SSTable có thứ tự; một B+-tree theo khóa thời gian cũng là đối chứng hợp lý. Cần đo throughput ghi bền vững, chi phí compaction, p99 độ trễ ghi, bytes written, tốc độ quét khoảng và mức tiêu thụ RAM. Kết quả phụ thuộc thứ tự khóa và mức độ phân vùng.

### Bài 4 — Chọn kiến trúc cho hệ thống đọc là chính

Một danh mục sản phẩm ít thay đổi nhưng có nhiều GET, đa số là khóa **tồn tại**, và yêu cầu p99 chặt chẽ.

**Lời giải gợi ý:** **B+-tree** là ứng viên ưu tiên vì đường tìm ổn định và các trang trên cao có thể cache. Tuy nhiên vẫn benchmark LSM được cấu hình tốt; đặc biệt phải đo hit ratio, fetch bản ghi ngoài chỉ mục, cache và độ trễ cao nhất trong những giai đoạn có tác vụ nền.

### Bài 5 — Phiên bản và tombstone

SSTable cũ lưu **(K, 10)**, MemTable mới lưu **(K, TOMBSTONE)**. Nếu đọc không thấy ở bảng mới rồi tiếp tục lấy **K = 10** từ bảng cũ thì sai ở đâu?

**Lời giải:** Tombstone là một **kết quả có hiệu lực**, không phải “không tìm thấy”. Đọc phải dừng với kết quả **đã xóa** khi tombstone là phiên bản nhìn thấy mới nhất. Chỉ xóa tombstone khỏi lưu trữ khi không còn phiên bản cũ/snapshot nào cần nó che khuất.

### Bài 6 — So sánh dựa trên thước đo công bằng

Một benchmark báo LSM-tree ghi nhanh gấp ba B+-tree, nhưng LSM chỉ xác nhận sau khi đưa dữ liệu vào RAM, còn B+-tree xác nhận sau khi WAL được đồng bộ xuống thiết bị. Có thể dùng kết quả này để kết luận không?

**Lời giải:** **Không.** Hai bên đang dùng **mức bảo đảm độ bền khác nhau**. Cần chạy lại với cùng điều kiện WAL/fsync, đồng thời đo cả flush, compaction bền vững, RAM, ổ đĩa, p95/p99 và lỗi phục hồi.

### Bài 7 — Nhận diện chi phí quét khoảng

B+-tree trả 2.000 mục liên tiếp trên những lá đã sắp. LSM có bốn run chồng lấn, mỗi run chứa một số phiên bản cũ của 2.000 khóa. Vì sao không thể so sánh chi phí chỉ bằng “hai bên đều có 2.000 kết quả”?

**Lời giải:** B+-tree chủ yếu seek rồi đọc các lá liên tiếp; LSM có thể phải seek nhiều run, đọc **nhiều hơn 2.000 entry** vì các phiên bản trùng và tombstone, sau đó merge và lọc để trả kết quả. Nếu chỉ mục B+-tree trỏ đến bản ghi rải rác, phía B+-tree lại có thể trả thêm I/O. Cần đo số khối thực đọc, số entry đã duyệt và có/không fetch dữ liệu.

## 14. Checklist khi áp dụng vào bài toán thật

Trước khi chọn B+-tree hay LSM-tree, hãy trả lời rõ các câu hỏi sau:

1. **Tỷ lệ GET/PUT/DELETE là bao nhiêu?** GET có bao nhiêu phần trăm hit và miss?
2. **Tra cứu nào là chính?** Một khóa chính xác, quét khoảng ngắn, quét dài hay truy vấn nhiều cột?
3. **Khóa được phân bố ra sao?** Tăng dần, ngẫu nhiên, có vùng nóng, có nhiều lần ghi lại cùng khóa không?
4. **Mức bền vững và đồng thời nào bắt buộc?** Một thao tác được xác nhận khi đã vào RAM, WAL hay đã được đồng bộ?
5. **Giới hạn tài nguyên ra sao?** Ngân sách RAM cho cache, dung lượng SSD/HDD, băng thông I/O, độ bền ghi và dung lượng tạm cho compaction?
6. **Có yêu cầu độ trễ đuôi không?** p99 của GET/PUT/scan có quan trọng hơn throughput trung bình không?
7. **Cần giữ lịch sử hoặc snapshot không?** Các phiên bản cũ và tombstone ảnh hưởng ra sao đến lưu trữ và đọc?
8. **Đo bằng gì?** Page/block reads, byte ghi vật lý, tỷ lệ cache, compaction backlog, split/merge và latency theo phân vị.

**Cách hiểu cần giữ lại:** B+-tree trả lời câu hỏi “**làm sao duy trì một cây chỉ mục theo trang để tìm và cập nhật trực tiếp?**”, còn LSM-tree trả lời “**làm sao gom cập nhật thành các dãy có thứ tự rồi hợp nhất chúng theo thời gian?**”. Quyết định hợp lý phải dựa trên **mẫu truy vấn và ghi thực tế**, đồng thời tính đến bất biến cấu trúc, độ phức tạp, RAM, I/O và công việc nền của hệ thống.

# Hợp nhất tệp và các kiểu khuếch đại đọc, ghi, không gian

Trong một hệ thống lưu trữ dùng **LSM-tree** (*Log-Structured Merge-tree*), mỗi lần cập nhật thường được gom vào bộ đệm RAM rồi ghi thành một tệp bất biến có thứ tự (**SSTable**). Cách làm này giúp hấp thụ nhiều thao tác ghi nhỏ, nhưng sau một thời gian, cùng một khóa có thể xuất hiện ở nhiều tệp với các giá trị khác nhau. Để việc đọc không phải kiểm tra ngày càng nhiều tệp và để giải phóng dữ liệu cũ, hệ thống phải **hợp nhất tệp** (*compaction*).

Compaction là một ví dụ điển hình về sự đánh đổi trong thiết kế **cấu trúc dữ liệu ngoài bộ nhớ**: ghi lại nhiều dữ liệu hơn có thể làm truy vấn nhanh hơn và giảm dung lượng lưu trữ, nhưng chiếm băng thông I/O. Bài này giải thích cách trộn các tệp có thứ tự, các bất biến cần giữ, cách đo **khuếch đại ghi**, **khuếch đại đọc**, **khuếch đại không gian** và cách chọn chính sách phù hợp với tải công việc.

## 1. Vì sao phải hợp nhất các tệp?

Hãy xét một kho dữ liệu khóa–giá trị có các thao tác **PUT(k, v)**, **GET(k)** và **DELETE(k)**:

1. Một **memtable** trong RAM chứa những cập nhật gần đây.
2. Khi memtable đủ lớn, hệ thống **flush** dữ liệu theo thứ tự khóa xuống một SSTable trên SSD/HDD.
3. Những lần flush tiếp theo tạo thêm các SSTable, thay vì sửa từng SSTable cũ tại chỗ.
4. Một tác vụ nền chọn các tệp liên quan, trộn chúng và công bố những tệp kết quả.

Ví dụ, ba lần flush có thể để lại:

~~~text
SSTable F1:  a=10, b=20, d=40
SSTable F2:  a=15, c=30
SSTable F3:  b=DELETE, d=42
~~~

Các tệp **đều được sắp xếp theo khóa**, nhưng khóa **a**, **b**, **d** xuất hiện nhiều lần. Nếu không compaction, một GET hoặc truy vấn theo khoảng có thể phải kiểm tra nhiều phiên bản; các giá trị không còn hiệu lực vẫn chiếm đĩa.

~~~text
             Các tệp bất biến, có thứ tự
          F1              F2              F3
       [a b d]          [a c]           [b d]
          \               |               /
           \______________|______________/
                          |
                k-way merge + lọc phiên bản
                          |
               Tệp đầu ra có thứ tự
                  [a b c d]
                          |
              Công bố tệp mới an toàn
                          |
              Thu hồi tệp cũ khi được phép
~~~

**Hợp nhất tệp không đồng nghĩa với nối các tệp lại.** Vì mỗi tệp đã có thứ tự, hệ thống phải trộn các luồng theo khóa, giải quyết những phiên bản trùng và quyết định phiên bản nào còn cần được giữ. Nếu chỉ nối các byte, thứ tự toàn cục và tính đúng đắn của GET sẽ không được bảo đảm.

## 2. Bất biến khi compaction

Một cơ chế compaction đúng cần giữ đồng thời những tính chất sau:

| Bất biến | Ý nghĩa |
|---|---|
| **Thứ tự khóa** | Các mục trong tệp đầu ra vẫn được sắp xếp theo khóa; các phiên bản của một khóa được tổ chức theo quy tắc phiên bản của hệ thống. |
| **Thứ tự cập nhật** | Mỗi cập nhật có dấu mốc thứ tự, thường là *sequence number* tăng dần. Khi cùng khóa có nhiều bản ghi, GET phải chọn bản ghi phù hợp mới nhất với tầm nhìn của truy vấn. |
| **Dấu xóa có hiệu lực** | **Tombstone** của DELETE che những giá trị cũ hơn. Không được tùy tiện xóa tombstone khi vẫn còn bản ghi cũ có thể được truy cập ở tệp khác. |
| **Snapshot còn hợp lệ** | Nếu có snapshot hoặc giao dịch đọc dữ liệu tại thời điểm cũ, các phiên bản cần cho những lượt đọc đó chưa được phép thu hồi. |
| **Chuyển trạng thái an toàn** | Tệp kết quả phải hoàn chỉnh và được công bố qua metadata/manifest theo giao thức bền vững trước khi bỏ tham chiếu đến tệp nguồn. |

Đây là những bất biến của **trạng thái logic**, độc lập với việc một khóa nằm ở L0, L1 hay mức sâu hơn. Compaction có thể thay đổi vị trí vật lý của dữ liệu nhưng không được làm GET hoặc RANGE trả kết quả sai.

## 3. Cách trộn nhiều SSTable đã sắp xếp

### 3.1. Trộn nhiều luồng theo khóa

Giả sử có \(k\) tệp đầu vào. Ta mở một con trỏ trên mỗi tệp, dùng **min-heap** giữ mục nhỏ nhất hiện tại theo khóa, rồi liên tục lấy khóa nhỏ nhất và bổ sung mục tiếp theo từ tệp vừa đọc. Khi một khóa có nhiều phiên bản, cần thu thập và xử lý **tất cả phiên bản liên quan** trước khi phát ra kết quả cho khóa tiếp theo.

~~~text
function COMPACT(input_files, snapshots, lower_levels):
    cursors = open_sorted_iterators(input_files)
    heap = min_heap_by_key(cursors.current_entries)
    output = new_sorted_file()

    while heap is not empty:
        key = heap.min_key()
        versions = consume_all_entries_for_key(heap, cursors, key)
        versions = sort_by_sequence_descending(versions)

        kept = choose_versions_to_preserve(
            versions, snapshots, lower_levels
        )
        output.append_in_sorted_order(key, kept)

    finish_and_validate(output)
    publish_new_file_set_atomically()
    reclaim_old_files_when_no_reader_needs_them()
~~~

Đây là **giả mã mô tả nguyên lý**, không phải mã engine hoàn chỉnh. Trong thực tế, việc chọn đầu vào và xác định phiên bản phải giữ tùy thuộc miền khóa chồng lấn, snapshot, chính sách TTL và trạng thái các mức khác.

Nếu tổng cộng có **\(N\)** mục đầu vào và **\(k\)** luồng, phép trộn bằng heap tốn khoảng **\(O(N\log k)\)** thời gian CPU cho thao tác chọn mục (chưa kể sắp các phiên bản cùng khóa), dùng **\(O(k)\)** vị trí con trỏ/heap cộng bộ đệm đọc ghi. Với kích thước khối đĩa **\(B\)** và tổng kích thước dữ liệu đọc là **\(I\)** byte, kích thước đầu ra là **\(O_{\text{out}}\)** byte, luồng đọc ghi tuần tự cần xấp xỉ:

\[
\text{Số lượt I/O khối} \approx
\frac{I}{B}+\frac{O_{\text{out}}}{B}
\]

Ước lượng này bỏ qua metadata, cache, nén, I/O không tuần tự và các lần ghi đồng bộ. Nó mô tả **một lần compaction**; dữ liệu có thể bị ghi lại nhiều lần qua nhiều mức.

### 3.2. Ví dụ có cập nhật và xóa

Giả sử mỗi thao tác được gắn một số thứ tự (**seq**) tăng dần. Hai SSTable chứa:

| Tệp cũ F1 | Tệp mới F2 |
|---|---|
| (a, 10, seq=1) | (a, 15, seq=4) |
| (b, 20, seq=2) | (b, **TOMBSTONE**, seq=6) |
| (d, 40, seq=3) | (c, 30, seq=5) |

Trước compaction, **GET(a)** trả 15 vì seq=4 mới hơn seq=1; **GET(b)** trả *không tìm thấy* vì tombstone seq=6 che giá trị 20; **GET(c)** trả 30; **GET(d)** trả 40.

Nếu chưa thể chứng minh rằng dấu xóa của **b** là an toàn để bỏ, đầu ra logic có thể là:

~~~text
a -> 15        (seq=4)
b -> TOMBSTONE (seq=6)
c -> 30        (seq=5)
d -> 40        (seq=3)
~~~

Giá trị cũ của **a** có thể được bỏ nếu không snapshot nào cần nó. Với **b**, có hai trường hợp:

- Nếu vẫn có tệp **không tham gia compaction** chứa bản ghi b cũ hơn, phải giữ tombstone hoặc có cơ chế khác bảo đảm bản ghi cũ không xuất hiện trở lại.
- Nếu engine đã xác minh toàn bộ những phiên bản b cũ hơn có thể gây hồi sinh đều đã bị loại bỏ và không snapshot nào cần chúng, tombstone có thể được bỏ an toàn.

Điểm quan trọng: **tombstone cũng là dữ liệu điều khiển tính đúng đắn**. Xóa tombstone quá sớm có thể khiến GET bất ngờ trả về giá trị đã bị người dùng xóa.

### 3.3. Công bố tệp mới và phục hồi

Trong compaction, các tệp đầu vào thường vẫn có thể phục vụ GET. Engine ghi tệp mới, hoàn thiện chỉ mục và metadata, rồi thay đổi tập tệp hiện hành một cách an toàn. Chỉ sau đó mới thu hồi tệp cũ khi không còn truy vấn đang đọc nó. Nếu máy hỏng giữa chừng, giao thức khôi phục phải nhận diện được trạng thái tệp hợp lệ; không được để một tệp đầu ra chưa hoàn chỉnh thay thế nguồn dữ liệu duy nhất.

Tác vụ nền cũng tiêu thụ **băng thông đọc, ghi và CPU**, nên một compaction lớn có thể làm tăng độ trễ của truy vấn đang chạy, dù bản thân PUT nhỏ có vẻ rất nhanh.

## 4. Khuếch đại ghi (*write amplification*)

**Khuếch đại ghi** cho biết hệ thống thực sự ghi xuống thiết bị lưu trữ bao nhiêu dữ liệu để đáp ứng một lượng dữ liệu ghi logic từ ứng dụng:

\[
WA = \frac{\text{Tổng byte ghi vật lý trong phạm vi đo}}
{\text{Tổng byte ghi logic mà ứng dụng gửi trong cùng phạm vi}}
\]

Cần nêu rõ phạm vi đo. Có thống kê chỉ tính byte **SSTable flush + compaction**; có thống kê còn tính **WAL**, chỉ mục, metadata hoặc việc ghi lại do tầng lưu trữ. Không nên so sánh hai con số WA lấy từ hai quy ước khác nhau.

**Ví dụ tính WA.** Trong một giai đoạn đo, ứng dụng gửi **1 GiB dữ liệu ghi logic**. Engine ghi **1 GiB SSTable khi flush**, sau đó ghi thêm **4 GiB SSTable trong các lần compaction**:

\[
WA_{\text{SST}} = \frac{1+4}{1}=5
\]

Nếu cùng giai đoạn đó còn có **1 GiB WAL** và ta chọn tính WAL nhưng bỏ qua metadata, thì:

\[
WA_{\text{SST+WAL}} = \frac{1+4+1}{1}=6
\]

Đây là phép tính minh họa cho một cửa sổ quan sát đã chọn, không phải giá trị WA mặc định của LSM-tree. Cửa sổ quá ngắn dễ làm sai lệch kết quả: dữ liệu được flush hôm nay có thể chỉ được compaction vào ngày mai. Khi có nhiều cập nhật ghi đè cùng một khóa, **byte ghi logic** cũng không bằng **mức tăng dung lượng dữ liệu còn sống**.

Vì sao compaction làm tăng WA? Một bản ghi có thể lần lượt được flush vào L0, hợp nhất sang mức kế, rồi tiếp tục bị ghi lại khi các tệp khác chồng lên miền khóa của nó. Càng nhiều lần ghi lại cùng dữ liệu, WA càng lớn. Việc đọc tệp trong compaction là chi phí đọc I/O, **không trực tiếp cộng vào tử số byte ghi** của công thức WA nói trên.

## 5. Khuếch đại đọc (*read amplification*)

**Khuếch đại đọc** diễn tả công việc I/O phải thực hiện để trả lời một yêu cầu đọc, so với phần dữ liệu tối thiểu cần lấy. Nó đặc biệt rõ khi một khóa hoặc miền khóa có thể nằm trong nhiều SSTable.

Với một **GET khóa có tồn tại**, ta có thể minh họa:

\[
RA_{\text{GET}} =
\frac{\text{Số khối phải đọc từ lưu trữ}}
{\text{Số khối lý tưởng cần đọc}}
\]

Ví dụ một truy vấn lý tưởng chỉ cần **1 khối**, nhưng vì phải dò các tệp chồng lấn mà engine đọc **4 khối dữ liệu**, thì **RA = 4** theo cách đếm khối này. Nếu chỉ mục/Bloom filter chưa ở cache và cũng phải đọc đĩa, các lần đọc đó cần được tính khi quy ước đo bao gồm chúng.

**Không có một công thức RA duy nhất áp dụng cho mọi kiểu truy vấn.** Với GET khóa **không tồn tại**, số khối tối thiểu có thể bằng 0 nên không thể lấy 0 làm mẫu số. Khi ấy nên đo **số lần đọc đĩa hoặc số byte đọc trung bình trên mỗi GET thất bại**. Với **RANGE**, thường đo **byte/khối phải đọc so với byte/khối của các kết quả hữu ích**, vì còn phải duyệt bản ghi cũ, tombstone và khoảng dữ liệu bị chồng lấn.

Các yếu tố giảm read amplification:

- **Bloom filter:** với khóa không có trong một SSTable, bộ lọc có thể khẳng định chắc chắn *không có*, nên tránh đọc khối dữ liệu của tệp đó. Bloom filter có thể dương tính giả; kết luận *có thể có* vẫn cần kiểm tra thật.
- **Chỉ mục thưa và miền khóa min/max:** bỏ qua tệp hoặc khối không thể chứa khóa cần tìm.
- **Cache khối và cache chỉ mục:** tránh đọc đĩa lại khi dữ liệu được truy cập thường xuyên.
- **Compaction và bố trí mức:** thu gọn số tệp chứa cùng một miền khóa; trong leveled compaction, các tệp ở mỗi mức từ L1 trở đi thường không chồng miền khóa.

Các biện pháp này xử lý các khía cạnh khác nhau: Bloom filter chủ yếu cải thiện **point lookup**, nhất là khi khóa không tồn tại; nó không biến việc quét một khoảng khóa dài thành O(1).

## 6. Khuếch đại không gian (*space amplification*)

**Khuếch đại không gian** đo phần dung lượng vật lý phải giữ so với dữ liệu logic còn hiệu lực:

\[
SA =
\frac{\text{Dung lượng lưu trữ vật lý trong phạm vi đo}}
{\text{Dung lượng dữ liệu logic còn sống}}
\]

Ví dụ ứng dụng hiện có **100 GiB dữ liệu logic còn sống**. Các SSTable trên đĩa chứa 100 GiB dữ liệu còn sống, 30 GiB phiên bản cũ/tombstone và 5 GiB metadata:

\[
SA_{\text{ổn định}}=\frac{100+30+5}{100}=1{,}35
\]

Khi compaction đang tạo thêm **45 GiB tệp đầu ra tạm thời**, tệp cũ chưa thể thu hồi ngay, nên trong thời gian đó:

\[
SA_{\text{đỉnh}}=\frac{100+30+5+45}{100}=1{,}80
\]

Hai phép tính này giả sử chỉ tính SSTable và metadata liên quan, **không tính WAL, bản sao lưu, replication hay dung lượng trống do hệ thống tệp đặt trước**. Một số tài liệu dùng *space overhead* \(=(\text{physical}-\text{live})/\text{live}\); với ví dụ trên, overhead ổn định là **35%**, tương ứng SA **1,35 lần**. Cần phân biệt tỷ số và phần trăm dư thừa.

SA tăng khi có nhiều phiên bản ghi đè, tombstone chờ xử lý, tệp chồng lấn hoặc khi phải giữ đồng thời tệp cũ và mới trong quá trình compaction. Cơ chế TTL, snapshot dài và việc thiếu băng thông cho compaction cũng có thể trì hoãn thu hồi không gian.

## 7. Ba kiểu khuếch đại liên hệ với nhau thế nào?

| Quyết định | Khuếch đại ghi (WA) | Khuếch đại đọc (RA) | Khuếch đại không gian (SA) |
|---|---|---|---|
| **Compaction thường xuyên hơn** | Thường tăng vì viết lại nhiều byte. | Thường giảm nhờ ít tệp trùng miền khóa hơn. | Thường giảm khi phiên bản cũ được thu hồi sớm. |
| **Trì hoãn compaction** | Có thể giảm WA tức thời. | Có thể tăng khi tệp chồng lấn tích tụ. | Có thể tăng do giữ nhiều phiên bản và tombstone. |
| **Tăng Bloom filter/cache** | Không trực tiếp loại bỏ byte ghi do compaction; dùng thêm tài nguyên. | Thường giảm I/O đọc điểm. | Có thể tăng nhẹ nếu tính thêm metadata/bộ lọc. |
| **Giữ snapshot lâu** | Có thể khiến compaction phải giữ/ghi lại nhiều phiên bản. | Có thể tăng khi tìm phiên bản phù hợp. | Thường tăng vì chưa được loại dữ liệu cũ. |

Những mũi tên này là **xu hướng**, không phải định luật cứng: phụ thuộc phân phối khóa, tỷ lệ ghi đè, số tệp, chính sách chọn tệp, phần cứng và cache. Chẳng hạn một compaction nhỏ có thể làm giảm SA đáng kể mà không tăng WA nhiều nếu nó loại bỏ hàng loạt giá trị hết hiệu lực.

Một câu hỏi thiết kế thường gặp là: **có thể tối ưu đồng thời cả ba về mức tối thiểu không?** Trong cấu hình thực tế, thường phải chấp nhận đánh đổi: ít ghi lại dữ liệu giúp giảm WA nhưng để lại nhiều tệp cũ hơn; thu gọn dữ liệu quyết liệt có thể cải thiện RA/SA nhưng tiêu thụ I/O nền.

## 8. Các chiến lược hợp nhất phổ biến

### 8.1. Size-tiered compaction

**Size-tiered** gom một số SSTable có kích thước tương tự nhau thành tệp lớn hơn. Hệ thống có thể để nhiều tệp hoặc nhiều nhóm tệp cùng chứa một miền khóa. Đây là xu hướng thiên về **giảm số lần ghi lại dữ liệu**; đổi lại, GET và quét khoảng có thể phải xét thêm tệp, đồng thời có nhiều phiên bản cũ chưa được xử lý.

~~~text
F1 (10 MB) ─┐
F2 (11 MB) ─┼──> Merge ──> Fbig (~30 MB, có thể nhỏ hơn do bỏ trùng)
F3 (10 MB) ─┘
~~~

### 8.2. Leveled compaction

**Leveled** tổ chức tệp vào các mức dung lượng tăng dần, thường ký hiệu **L0, L1, L2, ...**. L0 có thể chứa tệp chồng miền khóa; từ L1 trở đi, một cấu hình thường gặp duy trì các SSTable **không chồng miền khóa trong cùng một mức**. Khi đưa dữ liệu xuống mức sâu, phải hợp nhất với những tệp ở mức đích có miền khóa giao nhau.

~~~text
L0:  [a..f] [c..j]       (có thể chồng lấn)
          \    /
L1:    [a..d] [e..h] [i..m]
             |
       hợp nhất miền khóa liên quan
             v
L2: [a..c] [d..f] [g..j] [k..m]
~~~

Nhờ miền khóa rõ ràng, tại mỗi mức không chồng lấn thường chỉ cần xét **tối đa một SSTable** cho một GET khóa (ngoài L0), thay vì nhiều tệp bất kỳ. Tuy nhiên một thao tác chuyển mức có thể làm tệp ở mức đích bị ghi lại; vì thế leveled compaction **thường đổi WA cao hơn để giảm RA và SA** so với size-tiered trong các cấu hình tương đương.

### 8.3. Time-window compaction và biến thể lai

Trong dữ liệu chuỗi thời gian được ghi chủ yếu theo thời gian tăng, có thể nhóm tệp theo **cửa sổ thời gian**. Khi toàn bộ dữ liệu của một cửa sổ đã hết hạn và không còn phụ thuộc nào phải giữ, engine có thể thu hồi cả nhóm tệp, tránh việc trộn nhiều phiên bản giữa các cửa sổ. Cách này hữu ích khi dữ liệu có TTL, nhưng cập nhật muộn hoặc xóa xuyên nhiều cửa sổ làm việc thu hồi và tính đúng đắn phức tạp hơn.

Một số engine phối hợp nhiều chiến lược hoặc chuyển chính sách tùy tải. Tên gọi và thuật toán cụ thể khác nhau giữa các sản phẩm; nên đánh giá **bất biến, số lần viết lại và số tệp phải đọc** thay vì chỉ dựa vào tên chiến lược.

| Chính sách | Lợi thế thường gặp | Rủi ro/chi phí cần đo | Tải phù hợp để thử |
|---|---|---|---|
| Size-tiered | Thông lượng ghi cao, giảm viết lại. | Nhiều tệp cần dò, dữ liệu cũ và không gian tạm có thể lớn. | Nạp dữ liệu liên tục, ít GET nhạy độ trễ. |
| Leveled | Đọc điểm có thể ổn định hơn; ít tệp chồng lấn ở mức sâu. | Compaction có thể ghi lại nhiều byte, tranh I/O với yêu cầu trực tuyến. | Đọc–ghi hỗn hợp, GET khóa quan trọng. |
| Time-window | Tối ưu thu hồi theo lô thời gian và TTL phù hợp. | Cập nhật ngoài thứ tự, dữ liệu đến muộn, snapshot/tombstone liên cửa sổ. | Time series có vòng đời dữ liệu rõ ràng. |

## 9. Compaction debt, write stall và độ trễ

**Compaction debt** là lượng công việc hợp nhất còn tồn đọng theo cách ước lượng của engine. Nếu tốc độ tạo SSTable mới liên tục vượt tốc độ compaction xử lý, các tệp L0 và mức khác sẽ tích tụ. Hệ quả thường thấy:

- GET phải xem nhiều tệp hơn; metadata/filter và cache chịu thêm tải.
- Phiên bản cũ chưa được thu hồi, làm SA tăng.
- Nền tảng dùng chung SSD và CPU giữa truy vấn với compaction nên độ trễ **p95/p99** có thể tăng khi đợt hợp nhất lớn chạy.
- Engine có thể áp dụng **write slowdown** hoặc **write stall** để ngăn L0 và backlog tăng vô hạn. Khi đó thông lượng PUT giảm, dù PUT vào memtable vốn rẻ.

Vì vậy, muốn đánh giá hệ thống phải quan sát **trạng thái ổn định** sau khi chạy đủ lâu, thay vì chỉ đo một đợt ghi ngắn lúc compaction chưa kịp phát sinh. WAL và flush tuần tự khiến ghi ban đầu có vẻ nhanh; khả năng vận hành lâu dài còn phụ thuộc băng thông dành cho ghi lại trong compaction.

## 10. Hai bài toán chọn cấu trúc và cấu hình

### Bài toán A — Ghi sự kiện lớn, đọc theo lô

Một dịch vụ thu thập hàng triệu sự kiện mỗi phút. Dữ liệu thường được thêm mới và cuối ngày mới chạy truy vấn tổng hợp. Ưu tiên là **ingest throughput**; độ trễ GET đơn lẻ ít quan trọng hơn.

Hướng thử nghiệm: memtable đủ lớn để gom cập nhật; thử size-tiered hoặc nhóm theo cửa sổ thời gian khi dữ liệu phù hợp; cấp đủ băng thông cho flush và compaction. Đánh giá **byte ghi lại trên mỗi byte ingest**, dung lượng tạm thời cần dùng và độ trễ truy vấn theo khoảng.

### Bài toán B — Tra cứu hồ sơ trực tuyến với ghi cập nhật

Một hệ thống phục vụ GET theo khóa liên tục, đồng thời nhận nhiều PUT ghi đè hồ sơ. Nếu có quá nhiều SSTable chồng miền khóa, GET phải duyệt nhiều ứng viên và p99 độ trễ tăng.

Hướng thử nghiệm: leveled compaction với Bloom filter, chỉ mục và cache phù hợp. Đo **khối đĩa đọc/GET**, p95/p99, WA của compaction và tình trạng write stall. Lợi ích đọc phải được cân bằng với chi phí ghi lại và giới hạn SSD.

Hai bài toán đều dùng LSM-tree nhưng có **hàm mục tiêu khác nhau**. Một cấu hình rất tốt cho lượng ghi tuần tự có thể kém khi truy vấn đọc điểm là nút thắt.

## 11. Đo lường và chẩn đoán trong thực tế

Trước khi thay đổi chính sách compaction, hãy xác định cách đo và khoảng thời gian đo:

| Số liệu | Cách hiểu | Dấu hiệu cần kiểm tra |
|---|---|---|
| Byte ghi logic, byte flush, byte compaction, byte WAL | Dùng để tính WA với phạm vi rõ ràng. | Byte compaction tăng nhiều lần so với byte người dùng ghi. |
| Byte/khối đọc trên GET, GET thất bại và RANGE | Phản ánh RA theo từng loại truy vấn. | Nhiều lần đọc khối cho một GET; quét lượng dữ liệu lớn so với kết quả trả về. |
| Tổng dung lượng SSTable, dữ liệu còn sống, tệp tạm | Dùng để tính SA ổn định và SA đỉnh. | Đĩa đầy khi compaction vì cần chỗ cho cả đầu vào lẫn đầu ra. |
| Số SSTable mỗi mức, miền khóa chồng lấn | Cho biết compaction đang thu gọn được bao nhiêu tệp. | L0 và tệp trùng miền khóa tăng liên tục. |
| Pending compaction bytes/debt, write stall | Báo backlog và khả năng theo kịp tải ghi. | Thời gian stall tăng khi tốc độ ingest vượt khả năng compaction. |
| Độ trễ GET/PUT p50, p95, p99; CPU và I/O thiết bị | Cho thấy ảnh hưởng vận hành tới người dùng. | Đuôi độ trễ cao trùng giai đoạn compaction nặng. |

Ba điểm cần nhớ khi phân tích benchmark:

1. **Nhất quán mẫu số:** WA chia cho byte ứng dụng ghi trong cùng khoảng thời gian, SA chia cho dữ liệu *còn sống*; không đổi mẫu số mà vẫn so con số như cũ.
2. **Phân biệt cache và đĩa:** một GET trúng cache có thể đọc 0 khối vật lý dù cấu trúc SSTable vẫn phân tán; đo riêng truy vấn nóng và lạnh.
3. **Đo cả lúc ổn định lẫn lúc áp lực:** lấy mẫu khi dữ liệu đã đủ lớn, có cập nhật ghi đè, tombstone, snapshot (nếu dùng) và compaction đang diễn ra.

Ngoài ra, nếu **write amplification** tăng, cần xác định do chuyển mức quá nhiều, kích thước mức chưa phù hợp hay phân phối cập nhật tập trung. Nếu **read amplification** tăng, kiểm tra tệp chồng lấn, Bloom filter và tỉ lệ cache. Nếu **space amplification** tăng, tìm phiên bản cũ, tombstone chưa thể bỏ, snapshot kéo dài và dung lượng tệp compaction tạm.

## 12. Bài tập suy luận có đáp án

**Câu 1 — Tính WA.** Trong một khoảng đo, ứng dụng ghi 2 GiB logic, hệ thống flush 2 GiB và compaction ghi thêm 6 GiB. Nếu chỉ tính SSTable, WA bằng bao nhiêu?

**Đáp án:** \((2+6)/2=4\). Nếu còn 2 GiB WAL và quy ước tính cả WAL thì WA bằng \((2+6+2)/2=5\).

**Câu 2 — Tính SA.** Dữ liệu logic còn sống là 80 GiB. Tổng SSTable hiện hành chiếm 112 GiB, chưa kể 24 GiB tệp tạm đang được tạo. SA ổn định và SA đỉnh bằng bao nhiêu?

**Đáp án:** SA ổn định \(112/80=1{,}4\) lần. SA đỉnh \((112+24)/80=1{,}7\) lần. Overhead so với dữ liệu còn sống lần lượt là 40% và 70%.

**Câu 3 — Kiểm tra bất biến.** Một tệp không tham gia compaction còn chứa ("k", 7, seq=10). Trong tập tệp được chọn có ("k", TOMBSTONE, seq=15). Có được bỏ tombstone chỉ vì tệp được chọn không còn bản ghi k nào khác không?

**Đáp án:** **Không.** Bỏ tombstone có thể làm phiên bản seq=10 ở tệp chưa hợp nhất xuất hiện trở lại. Chỉ được bỏ khi có bằng chứng an toàn về các phiên bản còn lại và những snapshot có liên quan.

**Câu 4 — Chọn chính sách.** Một dịch vụ nhiều PUT liên tục, ít GET, muốn giảm byte ghi do compaction. Một dịch vụ khác chủ yếu GET điểm, rất nhạy p99. Nên thử hướng nào trước?

**Đáp án:** Dịch vụ đầu có thể thử **size-tiered** để giảm chi phí ghi lại; dịch vụ sau có thể thử **leveled** và bộ lọc/cache để giảm số tệp cần đọc. Quyết định cuối cùng phải dựa trên đo đạc với dữ liệu và tải thật.

## 13. Tổng kết

Compaction **trộn các SSTable đã có thứ tự**, giữ các phiên bản cần thiết, xử lý tombstone theo điều kiện an toàn và công bố tệp kết quả mà không làm sai trạng thái logic. Nó cải thiện cách bố trí dữ liệu nhưng tốn I/O đọc/ghi nền.

Ba thước đo phản ánh ba chi phí khác nhau: **WA** là byte phải ghi lại so với byte ứng dụng ghi, **RA** là công việc đọc phải làm so với phần dữ liệu hữu ích, còn **SA** là dung lượng vật lý phải giữ so với dữ liệu logic còn sống. Trong thiết kế cấu trúc dữ liệu ngoài bộ nhớ, việc chọn compaction là chọn **mức đánh đổi giữa ba chi phí**, dựa trên tần suất PUT/GET/RANGE, phân phối khóa, snapshot, đặc tính SSD/HDD và yêu cầu độ trễ của ứng dụng.

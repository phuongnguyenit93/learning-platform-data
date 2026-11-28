# Cấu trúc LSM-tree: bộ đệm trong RAM và các tệp có thứ tự

Khi một hệ thống lưu hàng triệu đến hàng tỷ cặp **khóa – giá trị**, việc sửa trực tiếp từng vị trí nhỏ trên đĩa có thể gây nhiều lần truy cập ngẫu nhiên. **LSM-tree** (*Log-Structured Merge-tree*) tổ chức dữ liệu theo hướng khác: gom các thay đổi trong RAM, ghi thành những tệp **đã sắp xếp và không sửa tại chỗ**, rồi hợp nhất các tệp ở nền. Đây là cách nhiều kho khóa–giá trị và hệ thống lưu trữ dùng để cân bằng thông lượng ghi, tốc độ đọc và chi phí dung lượng.

Bài học thuộc chương **Dữ liệu ngoài bộ nhớ**. Trọng tâm là nhìn LSM-tree như một cấu trúc dữ liệu có **bất biến**, **phép toán** và **chi phí I/O** riêng, để biết khi nào nên chọn nó thay cho một cấu trúc cập nhật trực tiếp trên đĩa.

## 1. Vấn đề: ghi ngẫu nhiên và ghi tuần tự

Giả sử ứng dụng liên tục nhận sự kiện:

- Ghi nhiệt độ mới nhất theo khóa thiết bị: **PUT("sensor:17", 28.5)**.
- Cập nhật giá trị cũ: **PUT("sensor:17", 29.1)**.
- Xóa một khóa: **DELETE("sensor:17")**.
- Đọc một khóa: **GET("sensor:17")**, hoặc duyệt các khóa trong một khoảng.

Nếu mỗi cập nhật phải tìm đúng trang đĩa cũ rồi sửa ngay, hệ thống có thể phải đọc và ghi nhiều trang rời rạc. LSM-tree chọn cách **ghi nối tiếp** vào nhật ký và **gom nhiều cập nhật** trước khi chuyển xuống đĩa. Việc ghi ra một dải dữ liệu đã sắp xếp thường phù hợp hơn với I/O khối so với vô số lần sửa rải rác. Tuy vậy, dữ liệu sẽ tạm thời xuất hiện ở nhiều tệp và phải được hợp nhất về sau; LSM-tree không biến chi phí ghi thành số không.

Các thành phần thường gặp:

| Thành phần | Nơi lưu | Vai trò |
|---|---|---|
| **Memtable** | RAM | Chứa các thay đổi gần nhất, duy trì khóa có thứ tự để tra cứu và xuất ra tệp đã sắp xếp. |
| **WAL** (*write-ahead log*) | Bộ nhớ bền vững | Ghi nhật ký thao tác để khôi phục những cập nhật chưa kịp chuyển thành tệp. Đây là cơ chế thông dụng, không phải điều kiện định nghĩa duy nhất của mọi LSM-tree. |
| **Immutable memtable** | RAM | Memtable đã được đóng băng, chờ ghi xuống đĩa; vẫn có thể phục vụ đọc. |
| **SSTable** (*Sorted String Table*) | SSD/HDD | Tệp các mục sắp theo khóa, bất biến sau khi được tạo. |
| **Compaction** | Tác vụ nền | Trộn các SSTable, xử lý bản ghi cũ hoặc dấu xóa, và tổ chức lại các mức tệp. |
| **Manifest/metadata** | Bộ nhớ bền vững | Ghi nhận những tệp nào thuộc trạng thái hợp lệ của kho dữ liệu. |

Một hình dung tổng quan:

~~~text
                       yêu cầu PUT / DELETE
                               |
                    ghi nối tiếp vào WAL
                               |
                               v
                    MEMTABLE (RAM, có thứ tự)
                               |
                          đủ ngưỡng?
                               |
                       đóng băng memtable
                               |
                          flush tuần tự
                               v
                    SSTable mới (thường L0)
                               |
                      compaction ở nền
                               v
                   SSTable ở các mức sâu hơn

GET / RANGE: xem memtable -> immutable memtable -> những SSTable có thể chứa khóa
~~~

Trong các triển khai thực tế, bộ nhớ đệm khối, chỉ mục, Bloom filter và chiến lược bố trí mức sẽ làm đường đọc nhanh hơn sơ đồ tối giản này.

## 2. Bất biến giữ cho dữ liệu nhất quán

**Bất biến 1 — Thứ tự khóa:** các mục trong một SSTable được sắp theo khóa, chẳng hạn **"an" < "binh" < "chi"**. Memtable thường dùng cây cân bằng hoặc skip list để hỗ trợ duy trì thứ tự trước khi flush. WAL có thể theo thứ tự thời gian ghi, không bắt buộc sắp theo khóa.

**Bất biến 2 — Tệp bất biến:** sau khi SSTable được công bố hợp lệ, hệ thống không sửa trực tiếp các bản ghi bên trong. Cập nhật tiếp theo tạo phiên bản mới ở memtable/SSTable khác; compaction sinh tệp mới rồi thay đổi tập tệp đang được tham chiếu.

**Bất biến 3 — Phiên bản mới nhất quyết định kết quả:** nếu cùng một khóa nằm ở nhiều nơi, kết quả đọc phải tuân theo thứ tự cập nhật (thường được biểu diễn bằng **số thứ tự tăng dần**, hay *sequence number*). Mức tệp hoặc thời điểm flush giúp tối ưu tìm kiếm, nhưng chỉ nhìn vị trí tệp không đủ để định nghĩa dữ liệu nào mới nhất trong mọi cấu hình.

**Bất biến 4 — Xóa cũng có thứ tự:** thao tác DELETE ghi một **tombstone** (dấu xóa) mang số thứ tự mới hơn dữ liệu cũ. Khi GET gặp dấu xóa đang có hiệu lực, kết quả là không tồn tại; không được lấy lại giá trị cũ từ tệp sâu hơn.

**Bất biến 5 — Công bố trạng thái bền vững an toàn:** tệp mới chỉ được coi là một phần của kho dữ liệu sau khi dữ liệu và metadata cần thiết được ghi bền vững theo giao thức của hệ thống. Nhật ký tương ứng chỉ được dọn khi các thay đổi đã được bảo vệ bằng trạng thái bền vững khác.

Các bất biến này quan trọng hơn hình dạng cụ thể của cây. Một LSM-tree thông thường là **một tập memtable và nhiều tệp đã sắp xếp theo cấp**, chứ không nhất thiết có cấu trúc nút–con trên đĩa như cây tìm kiếm nhị phân.

## 3. Đường ghi: từ RAM đến SSTable

### Bước 1 — Nhận PUT hoặc DELETE

Với **PUT(k, v)**, hệ thống gán thứ tự cập nhật, thường ghi thay đổi vào WAL và đưa phiên bản mới vào memtable. Với **DELETE(k)**, memtable chứa tombstone thay cho giá trị. Những lần cập nhật liên tiếp một khóa có thể được gộp trong memtable nếu không cần giữ các phiên bản cũ cho snapshot.

WAL giúp phục hồi sau sự cố nhưng **bảo đảm bền vững phụ thuộc chính sách đồng bộ**. Nếu hệ thống chỉ giữ dữ liệu trong bộ đệm hệ điều hành và chưa buộc nhật ký xuống thiết bị lưu trữ, một sự cố mất điện có thể làm mất các thao tác đã được trả lời thành công, tùy chế độ cấu hình.

### Bước 2 — Đóng băng memtable và flush

Khi memtable đến ngưỡng dung lượng, hệ thống chuyển nó thành **immutable memtable**, tạo một memtable mới để tiếp nhận ghi và lần lượt duyệt các khóa có thứ tự của bảng cũ để tạo SSTable. Vì khóa đã được sắp xếp, bước này chủ yếu là **ghi theo luồng**. Những thiết kế thông dụng cho phép ghi mới và phục vụ đọc tiếp tục trong lúc flush.

SSTable mới thường xuất hiện ở **L0** (level 0). Ở cấp này nhiều tệp có thể chứa cùng miền khóa, vì các đợt flush độc lập diễn ra theo thời gian. Dữ liệu cũ chưa biến mất chỉ vì có tệp mới.

### Bước 3 — Compaction

Sau nhiều lần flush, số lượng tệp tăng lên. **Compaction** đọc những SSTable được chọn, trộn các mục theo khóa, giải quyết các phiên bản trùng, rồi tạo những SSTable mới. Chỉ sau khi tệp mới được ghi an toàn và metadata chuyển sang tập tệp mới, hệ thống mới có thể thu hồi các tệp cũ không còn được tham chiếu.

Khi có snapshot hoặc giao dịch còn cần phiên bản cũ, compaction phải giữ những phiên bản đó. Tombstone chỉ được bỏ khi có thể chứng minh rằng việc bỏ nó **không làm hồi sinh bản ghi cũ** và không phá hỏng những snapshot còn hiệu lực.

## 4. Ví dụ từng bước: cùng một khóa có nhiều phiên bản

Giả sử kho dữ liệu rỗng, mỗi lần ghi nhận một số thứ tự tăng dần:

| Thao tác | Số thứ tự | Trạng thái mới nhất |
|---|---:|---|
| PUT("an", 5) | 1 | an = 5 |
| PUT("binh", 7) | 2 | binh = 7 |
| PUT("an", 8) | 3 | an = 8 |

Memtable có thể gộp hai lần cập nhật khóa **"an"**. Khi flush, ta được tệp **F1** đã sắp theo khóa:

~~~text
F1 (SSTable)
  ("an",   8, seq=3)
  ("binh", 7, seq=2)
~~~

Tiếp đó ứng dụng thực hiện **PUT("an", 11)** ở thứ tự 4 và **DELETE("binh")** ở thứ tự 5. Một lần flush khác tạo **F2**:

~~~text
F2 (SSTable mới hơn)
  ("an",   11,        seq=4)
  ("binh", TOMBSTONE, seq=5)
~~~

Khi hai tệp còn cùng tồn tại, **GET("an")** trả **11** vì phiên bản 4 mới hơn phiên bản 3. **GET("binh")** trả **không tìm thấy** vì tombstone ở thứ tự 5 che bản ghi giá trị 7 ở F1. Đọc F1 một mình sẽ cho kết quả sai.

Sau compaction, trạng thái logic mới nhất là:

~~~text
("an",   11,        seq=4)
("binh", TOMBSTONE, seq=5)  # giữ cho đến khi an toàn để bỏ
~~~

Ví dụ này cho thấy **thứ tự vật lý trong một SSTable** và **thứ tự thời gian giữa các phiên bản** là hai khái niệm khác nhau. Việc compaction đổi vị trí vật lý nhưng không được đổi kết quả logic của GET.

## 5. Bên trong một SSTable

SSTable là tệp bất biến với phần dữ liệu được lưu thành các **khối** (*data blocks*), mỗi khối chứa các khóa theo thứ tự. Một định dạng thường có thêm:

1. **Chỉ mục thưa (*sparse index*):** lưu các khóa mốc cùng vị trí khối, giúp chọn khối liên quan thay vì quét toàn tệp.
2. **Bloom filter (tùy chọn):** nhanh chóng kết luận khóa **chắc chắn không có** trong tệp; nếu báo *có thể có* thì vẫn phải tra cứu thật. Bộ lọc có thể dương tính giả, không được có âm tính giả đối với tập khóa đã lập chỉ mục đúng.
3. **Metadata:** khóa nhỏ nhất/lớn nhất, cách nén, vị trí chỉ mục, thông tin kiểm tra tính toàn vẹn, v.v.

~~~text
SSTable (min="an", max="duong")
 +------------------------+
 | Data block 0: an..binh |
 +------------------------+
 | Data block 1: chi..duong|
 +------------------------+
 | Sparse index           | --> "an" -> block 0; "chi" -> block 1
 +------------------------+
 | Bloom filter (tùy chọn)|
 +------------------------+
 | Footer / metadata      |
 +------------------------+
~~~

Ví dụ GET("chi") có thể bỏ qua mọi tệp có khoảng khóa không bao gồm **"chi"**, kiểm tra Bloom filter ở các tệp còn lại, dùng chỉ mục tìm khối phù hợp và tra trong khối. Vì SSTable đã sắp xếp, truy vấn **RANGE("an", "chi")** cũng có thể đọc các mục theo thứ tự từ một vị trí mốc. Nếu dữ liệu nằm trong nhiều tệp, hệ thống trộn các luồng đã sắp xếp và giải quyết khóa trùng.

Bloom filter tối ưu rõ nhất cho **GET khóa không tồn tại**. Nó không giúp chứng minh chắc chắn khóa có giá trị gì, và thường không thay thế được quá trình quét thực tế khi truy vấn một khoảng khóa.

## 6. Đường đọc: GET và RANGE

Với **GET(k)**, hệ thống kiểm tra memtable đang ghi, các immutable memtable còn chờ flush, rồi những SSTable có thể chứa khóa. Ở một số mức, các tệp có miền khóa không chồng nhau nên chỉ cần chọn tối đa một tệp trong mức đó; L0 thường phải cân nhắc nhiều tệp chồng lấn. Các chỉ mục và bộ lọc giảm số lần truy cập khối, còn bộ đệm có thể tránh đọc đĩa lặp lại.

Để mô tả kết quả đúng mà không phụ thuộc cách bố trí tệp, có thể hình dung thuật toán logic sau (triển khai thật sẽ dùng thông tin thứ tự phiên bản để dừng sớm và bỏ qua tệp không liên quan):

~~~text
function GET(key):
    newest = NONE
    for source in sources_that_might_contain(key):
        candidate = source.find_latest_version(key)
        if candidate exists and (
            newest is NONE or candidate.seq > newest.seq
        ):
            newest = candidate

    if newest is NONE or newest.kind == TOMBSTONE:
        return NOT_FOUND
    return newest.value
~~~

**RANGE(lo, hi)** sử dụng lợi thế thứ tự: mở con trỏ ở vị trí **lo** trong từng nguồn có thể giao với khoảng truy vấn, trộn các luồng theo khóa (thường với heap), chọn phiên bản hợp lệ mới nhất của mỗi khóa, bỏ qua tombstone rồi xuất kết quả cho đến **hi**. Công việc bổ sung phụ thuộc số nguồn tham gia và số phiên bản cũ phải xử lý. Trường hợp có snapshot, quy tắc chọn phiên bản còn phải xét số thứ tự tối đa mà snapshot được phép nhìn thấy.

## 7. Phân cấp SSTable và hai chiến lược compaction

LSM-tree thường sắp xếp SSTable thành nhiều mức (**L0, L1, L2, ...**) hoặc nhiều nhóm tệp theo kích thước. Số mức, hệ số tăng trưởng dung lượng và quy tắc chọn tệp do triển khai quyết định.

| Tiêu chí | **Size-tiered compaction** | **Leveled compaction** |
|---|---|---|
| Cách hợp nhất | Gom nhiều tệp có kích thước gần nhau thành tệp lớn hơn. | Duy trì giới hạn dung lượng theo mức; đưa dữ liệu xuống mức sâu, thường giữ các tệp không chồng miền khóa trong cùng mức từ L1 trở đi. |
| Ưu điểm điển hình | Giảm số lần ghi lại dữ liệu, phù hợp tải ghi lớn. | Giảm số tệp ứng viên khi đọc một khóa và giảm phần dữ liệu trùng ở các mức. |
| Đánh đổi điển hình | Có thể giữ nhiều tệp/phiên bản hơn, tốn đọc và dung lượng tạm. | Có thể viết lại nhiều byte hơn qua các lần chuyển mức; compaction gây tải I/O nền. |
| Khi cân nhắc | Hệ thống thiên về ingest, ghi liên tục. | Hệ thống cần cân bằng ghi với độ trễ đọc khóa và mức dùng đĩa. |

Đây là xu hướng thường gặp chứ không phải bảo đảm tuyệt đối: kết quả phụ thuộc tỷ lệ đọc/ghi, kích thước khóa và giá trị, kích thước memtable, Bloom filter, cache, mức độ chồng lấn và cấu hình của từng công cụ.

Ba đại lượng thường dùng để đánh giá:

- **Write amplification:** tổng số byte phải ghi lên thiết bị lưu trữ chia cho số byte dữ liệu logic được cập nhật. Ghi trong compaction làm hệ số này tăng.
- **Read amplification:** lượng công việc/khối phải đọc để giải quyết một truy vấn so với lượng thông tin tối thiểu cần thiết. Nhiều tệp ứng viên thường làm tăng chi phí này.
- **Space amplification:** dung lượng vật lý dùng để lưu dữ liệu so với dung lượng dữ liệu logic còn hiệu lực. Phiên bản cũ, tombstone và tệp compaction tạm làm tăng tỷ lệ.

Tối ưu một đại lượng có thể làm đại lượng khác xấu đi; vì vậy phải đánh giá theo loại truy vấn quan trọng nhất của hệ thống.

## 8. Độ phức tạp và mô hình I/O

Ký hiệu **m** là số khóa đang có trong memtable, **f** là số SSTable có thể cần xét, **k** là số khóa kết quả của truy vấn khoảng và **B** là kích thước khối I/O. Bảng dưới trình bày **xu hướng của cấu trúc**, không gán một cận Big-O cố định cho mọi triển khai LSM:

| Phép toán | CPU / bộ nhớ | I/O đáng chú ý |
|---|---|---|
| PUT / DELETE | Chèn vào cây cân bằng thường **O(log m)**; skip list thường **O(log m)** kỳ vọng. | Ghi nối tiếp WAL; về sau chịu chi phí flush và compaction được phân bổ trên nhiều cập nhật. |
| GET(khóa) | Tra memtable thường **O(log m)**, cộng tìm ứng viên trong các SSTable. | Có thể phải đọc các chỉ mục/khối ở nhiều tệp; Bloom filter, cache và cách bố trí mức làm giảm I/O. |
| RANGE(lo, hi) | Duyệt các nguồn đã sắp xếp và trộn kết quả; heap trộn **f** luồng tốn khoảng **O(log f)** mỗi lần chọn mục. | Đọc tuần tự các khối liên quan; có thêm chi phí phiên bản cũ và các tệp chồng lấn. |
| Flush | Duyệt toàn bộ memtable theo thứ tự. | Ghi xấp xỉ **O(M/B)** khối cho **M** byte dữ liệu xuất ra, bỏ qua chi phí metadata và hiệu ứng nén. |
| Compaction | Trộn nhiều luồng sắp xếp, lọc phiên bản theo quy tắc. | Đọc và ghi lại các vùng dữ liệu được chọn; đây thường là phần tốn I/O nền nhất. |

Lưu ý: trong hàng **Flush**, **M** được tính bằng byte và **B** bằng byte/khối; đây là ước lượng số khối của một lượt ghi tuần tự. Số mức, số tệp trùng miền khóa, dung lượng cache và chính sách compaction quyết định chi phí tổng thể. Không nên khẳng định mọi thao tác GET hoặc PUT của LSM-tree đều là **O(1)** trên đĩa.

So với cấu trúc B-tree/B+tree cập nhật theo trang, LSM-tree thường có lợi khi cần hấp thụ rất nhiều **ghi nhỏ**. Đổi lại, nó cần **compaction** và đường đọc có thể phải xét nhiều phiên bản. B+tree có lợi ở việc duy trì dữ liệu theo vị trí có chỉ mục rõ ràng và thường có đường đọc điểm trực tiếp hơn; tuy nhiên ghi cập nhật có thể dẫn tới I/O ngẫu nhiên và phân tách trang. Lựa chọn còn chịu ảnh hưởng lớn từ SSD/HDD, cache và các tối ưu triển khai.

## 9. Khả năng phục hồi khi máy dừng đột ngột

Xét tình huống ứng dụng vừa PUT một khóa, giá trị mới đã nằm trong RAM nhưng chưa flush:

1. Nếu bản ghi WAL đã được ghi bền vững theo cấu hình, sau khi khởi động lại có thể **phát lại** WAL để tái tạo memtable.
2. Nếu một SSTable đang flush dở và chưa được công bố trong manifest, hệ thống phải bỏ qua tệp chưa hoàn chỉnh hoặc xử lý nó theo giao thức khôi phục.
3. Sau khi một SSTable hoàn chỉnh đã được công bố bền vững và chứa đầy đủ những thao tác tương ứng, các đoạn WAL đã được bảo vệ mới có thể được thu hồi.

Điều kiện **"trả lời ghi thành công"** và **"ghi bền vững trước mất điện"** chỉ trùng nhau nếu chính sách đồng bộ và giao thức phục hồi bảo đảm điều đó. Người thiết kế cần hiểu rõ thiết lập durability của engine, đặc biệt khi có ghi theo lô hoặc tắt đồng bộ WAL để tăng thông lượng.

## 10. Khi nào chọn và cách điều chỉnh

**LSM-tree là lựa chọn hợp lý** cho luồng sự kiện, bộ đếm/khóa–giá trị được cập nhật nhiều, hệ thống nạp dữ liệu khối lượng lớn hoặc kho lưu trữ nơi việc ghi tuần tự và quét theo khoảng là lợi thế. Nó không tự động tốt nhất cho mọi tải: ứng dụng đòi hỏi độ trễ GET cực thấp, có số lượng lớn khóa không tồn tại hoặc thường xuyên gặp đợt compaction nặng cần được đo đạc kỹ.

Các nút điều chỉnh phổ biến gồm:

- **Kích thước memtable:** lớn hơn giúp flush ít lần và tạo tệp đầu ra lớn hơn, nhưng dùng nhiều RAM và có thể kéo dài thời gian phục hồi/phát lại nhật ký.
- **Bộ nhớ đệm và Bloom filter:** tăng xác suất tìm trong RAM và tránh đọc tệp không chứa khóa, đổi lại tốn RAM/không gian metadata.
- **Chiến lược và tốc độ compaction:** quyết định tốc độ thu gom phiên bản cũ, write amplification và tác động của I/O nền lên độ trễ.
- **Số mức/hệ số kích thước:** ảnh hưởng lượng dữ liệu mỗi mức, số lần viết lại và số tệp có thể liên quan đến truy vấn.
- **Nén dữ liệu và kích thước khối:** giúp tiết kiệm băng thông/không gian lưu trữ nhưng có thêm chi phí CPU và có thể thay đổi độ khuếch đại đọc.

Khi thử nghiệm, nên đo **p95/p99 độ trễ GET/PUT**, throughput ghi, lượng byte compaction, tỷ lệ trúng cache, số lần truy cập đĩa cho GET thất bại và dung lượng vật lý sau khi hệ thống hoạt động đủ lâu. Một bài benchmark ngắn khi chưa phát sinh compaction có thể cho kết luận quá lạc quan.

## 11. Tự kiểm tra cách hiểu

**Tình huống A.** F1 chứa ("x", 10, seq=8), F2 chứa ("x", 12, seq=11) và cả hai tệp vẫn tồn tại. GET("x") phải trả **12**. Việc F1 hay F2 nằm ở mức nào không thay thế được quy tắc ưu tiên phiên bản mới hơn.

**Tình huống B.** F3 chứa ("x", TOMBSTONE, seq=13). GET("x") bây giờ là **không tìm thấy**. Nếu compaction xóa tombstone nhưng để sót ("x", 10, seq=8) ở một tệp sâu hơn, GET có thể trả sai **10** — một lỗi hồi sinh dữ liệu đã xóa.

**Tình huống C.** Có hàng chục SSTable chồng lấn và phần lớn GET hỏi khóa không tồn tại. Cấu hình Bloom filter phù hợp có thể giảm đáng kể số lần đọc khối; tuy nhiên nó không giảm chi phí ghi do compaction miễn phí, và bản thân Bloom filter cần thêm dung lượng.

**Ghi nhớ:** memtable hấp thụ cập nhật trong RAM; flush tạo **SSTable có thứ tự, bất biến**; GET phải xét **phiên bản mới nhất và tombstone**; compaction giảm dữ liệu trùng lặp bằng cách đổi lấy I/O nền. Hiểu bốn ý này giúp đánh giá đúng chi phí thời gian, bộ nhớ và lưu trữ của LSM-tree trong từng bài toán.

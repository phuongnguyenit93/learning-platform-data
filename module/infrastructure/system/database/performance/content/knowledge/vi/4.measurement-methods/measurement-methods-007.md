# Phân biệt tương quan với nguyên nhân khi đọc chỉ số hiệu năng

## Vì sao phải phân biệt tương quan và nguyên nhân?

Khi hệ thống cơ sở dữ liệu chậm, dashboard thường hiển thị nhiều chỉ số cùng thay đổi: CPU tăng, số phiên hoạt động tăng, I/O tăng, cache hit giảm, hàng đợi kết nối dài hơn và độ trễ p95 tăng. Những biến động đồng thời là manh mối quan trọng, nhưng chúng chưa chứng minh chỉ số nào gây ra sự chậm trễ.

**Tương quan** mô tả việc hai đại lượng thay đổi có liên hệ với nhau trong dữ liệu quan sát. **Quan hệ nhân quả** mô tả việc thay đổi một yếu tố làm thay đổi kết quả, trong những điều kiện xác định. Hai chỉ số có thể tương quan vì một yếu tố thứ ba tác động lên cả hai; một chỉ số có thể là hậu quả của sự cố; hoặc mối liên hệ chỉ xuất hiện do cách lấy mẫu và tổng hợp dữ liệu.

Ví dụ, CPU và độ trễ truy vấn cùng tăng vào giờ cao điểm. Có thể CPU bão hòa làm truy vấn chậm. Cũng có thể lưu lượng tăng là nguyên nhân chung khiến cả CPU và độ trễ tăng. Hoặc một truy vấn mới đọc quá nhiều hàng vừa tiêu thụ CPU vừa kéo dài thời gian phản hồi. Chỉ nhìn hai đường biểu đồ không đủ để chọn kết luận.

Trong tối ưu hiệu năng cơ sở dữ liệu, nhầm tương quan với nguyên nhân có thể dẫn đến thay đổi sai: tăng connection pool khi cơ sở dữ liệu đã quá tải, thêm chỉ mục khi nút thắt là tranh chấp khóa, tăng bộ nhớ khi truy vấn đang đọc quá nhiều dữ liệu, hoặc điều chỉnh SQL trong khi tải nền mới là yếu tố làm thay đổi kết quả. Phương pháp tốt cần kết hợp đo đạc tải, thống kê truy vấn, kế hoạch thực thi, trạng thái giao dịch và kiểm chứng sau điều chỉnh.

## Các khái niệm cần nắm

### Tương quan không đồng nghĩa với nhân quả

Nếu hai chỉ số thường tăng giảm cùng nhau, ta có thể nói chúng có tương quan dương. Nếu một chỉ số tăng khi chỉ số kia giảm, chúng có thể có tương quan âm. Nếu không thấy quan hệ ổn định, tương quan có thể yếu hoặc không đáng kể.

Hệ số tương quan Pearson thường được ký hiệu là r và nằm trong khoảng từ -1 đến 1. Giá trị gần 1 biểu thị quan hệ tuyến tính dương mạnh; gần -1 biểu thị quan hệ tuyến tính âm mạnh; gần 0 cho thấy không có quan hệ tuyến tính rõ ràng. Tuy nhiên, r không chứng minh quan hệ nhân quả, không phát hiện tốt mọi dạng quan hệ phi tuyến và có thể bị ảnh hưởng bởi ngoại lệ hoặc xu hướng theo thời gian.

Một ví dụ đơn giản: số lượng kết nối và độ trễ có thể cùng tăng. Điều đó không có nghĩa bản thân số kết nối luôn gây chậm. Số kết nối có thể chỉ là dấu hiệu cho thấy có nhiều yêu cầu đồng thời. Nếu tăng giới hạn kết nối trong lúc CPU, bộ nhớ hoặc I/O đã bão hòa, số phiên chạy đồng thời có thể tăng thêm và làm độ trễ tệ hơn.

### Nguyên nhân chung và biến gây nhiễu

Một **biến gây nhiễu (confounder)** là yếu tố liên quan đến cả yếu tố đang xem xét và kết quả, khiến mối liên hệ quan sát được dễ bị diễn giải sai.

Ví dụ:

- Lưu lượng tăng làm số truy vấn tăng.
- Số truy vấn tăng làm CPU tăng.
- Số truy vấn tăng cũng làm độ trễ tăng khi hệ thống tiến gần giới hạn xử lý.

Khi đó CPU và độ trễ tương quan, nhưng lưu lượng và đặc điểm workload có thể là nguyên nhân chung. CPU vẫn có thể góp phần tạo nút thắt, nhưng cần đo thêm mức sử dụng CPU theo tiến trình, thời gian chờ, hàng đợi và loại truy vấn trước khi kết luận.

Các yếu tố gây nhiễu thường gặp trong cơ sở dữ liệu gồm:

- Lưu lượng yêu cầu, số giao dịch đồng thời và tỷ lệ đọc/ghi.
- Kích thước dữ liệu, phân bố khóa, độ lệch dữ liệu và số hàng trả về.
- Thời điểm chạy báo cáo, backup, vacuum, checkpoint, đồng bộ hoặc tác vụ bảo trì.
- Thay đổi phiên bản ứng dụng, câu SQL, schema, chỉ mục hoặc cấu hình.
- Cache nóng/lạnh, độ mới của thống kê và thay đổi kế hoạch thực thi.
- Khác biệt giữa node, shard, tenant, vùng địa lý hoặc loại phần cứng.
- Sự cố mạng, lưu trữ dùng chung hoặc dịch vụ phụ thuộc.

Nếu không ghi nhận những yếu tố này, so sánh hai khoảng thời gian có thể không còn công bằng.

### Nhân quả ngược và quan hệ trung gian

Không phải lúc nào chỉ số được xem là nguyên nhân cũng xuất hiện trước kết quả. Đôi khi chính độ trễ cao làm số phiên đang hoạt động tăng vì yêu cầu tồn tại lâu hơn. Khi đó số phiên hoạt động cao một phần là hậu quả của truy vấn chậm.

Một quan hệ trung gian xảy ra khi yếu tố A tác động đến B, rồi B tác động đến C. Chẳng hạn, truy vấn quét nhiều hàng làm tăng I/O; I/O tạo hàng đợi; hàng đợi làm tăng độ trễ. Nếu chỉ nhìn I/O và độ trễ, ta có thể bỏ qua truy vấn và kế hoạch thực thi là điểm bắt đầu của chuỗi tác động.

Cần phân biệt:

- **Nguyên nhân gốc:** thay đổi ban đầu làm hệ thống lệch khỏi trạng thái bình thường.
- **Cơ chế trung gian:** đường đi mà qua đó nguyên nhân tác động đến kết quả.
- **Chỉ số biểu hiện:** tín hiệu cho thấy hệ thống đang chịu tác động.
- **Hậu quả:** điều xảy ra sau khi chất lượng dịch vụ đã suy giảm.

Một chỉ số có thể đảm nhiệm nhiều vai trò tùy câu hỏi đang phân tích. Ví dụ, hàng đợi I/O có thể là cơ chế trung gian giữa truy vấn đọc nhiều trang và độ trễ; nhưng khi phân tích thời gian phản hồi ứng dụng, hàng đợi I/O cũng là một chỉ số biểu hiện của nút thắt lưu trữ.

## Mô hình hóa đường đi nguyên nhân

Trước khi truy vấn thêm dữ liệu hoặc thay đổi cấu hình, hãy viết ra giả thuyết về đường đi có thể dẫn đến độ trễ. Một sơ đồ đơn giản giúp nhóm nhìn thấy yếu tố nào là đầu vào, yếu tố nào là trung gian và kết quả nào cần giải thích.

Ví dụ khi tải tăng:

~~~mermaid
flowchart TD
    A[Lưu lượng yêu cầu tăng] --> B[Số truy vấn đồng thời tăng]
    B --> C[CPU và hàng đợi tăng]
    B --> D[Tranh chấp khóa tăng]
    C --> E[Độ trễ truy vấn tăng]
    D --> E
    E --> F[Yêu cầu tồn tại lâu hơn]
    F --> B
~~~

Sơ đồ này thể hiện một vòng phản hồi có thể xảy ra: tải tăng làm truy vấn chậm; truy vấn chậm giữ phiên lâu hơn; số phiên đồng thời tiếp tục tăng. Sơ đồ chỉ là giả thuyết ban đầu, không phải bằng chứng. Dữ liệu theo thời gian, trace, thống kê truy vấn và thử nghiệm cần xác nhận những mũi tên nào thực sự có tác động trong hệ thống đang xét.

Có thể bắt đầu bằng câu hỏi cụ thể:

- Điều gì thay đổi ngay trước khi độ trễ tăng?
- Chỉ số nào tăng trước, chỉ số nào tăng sau?
- Thay đổi đó có tác động trực tiếp đến đường thực thi truy vấn không?
- Có yếu tố thứ ba giải thích được cả hai biến động không?
- Nếu giảm hoặc loại bỏ yếu tố nghi ngờ, độ trễ có cải thiện trong điều kiện tương đương không?
- Có chỉ số nào khác xấu đi sau khi áp dụng biện pháp đó không?

Không cần mô hình hóa toàn bộ hệ thống. Chỉ cần mô hình đủ nhỏ để có thể đo và kiểm chứng.

## Quy trình phân tích từ dấu hiệu đến giả thuyết

### 1. Xác định kết quả cần giải thích

Bắt đầu bằng một kết quả đo cụ thể, chẳng hạn:

- p95 của truy vấn đọc tăng từ 40 ms lên 180 ms.
- Tỷ lệ thao tác hoàn tất trong 100 ms giảm từ 99,5% xuống 96%.
- Thời gian commit giao dịch tăng trong khi tỷ lệ lỗi vẫn ổn định.
- API bị timeout dù thời gian thực thi SQL trên máy chủ không tăng tương ứng.

Nêu rõ phạm vi, cửa sổ thời gian, nhóm thao tác, node hoặc phân vùng, đơn vị và nguồn dữ liệu. Tránh bắt đầu bằng nhận định chung như “database đang chậm”.

Phân biệt thời gian ứng dụng quan sát với thời gian thực thi tại máy chủ. Một yêu cầu có thể mất 300 ms nhưng SQL chỉ chạy 40 ms; phần còn lại có thể nằm ở chờ connection pool, mạng, chờ khóa, truyền kết quả hoặc xử lý phía ứng dụng. Nếu đo sai ranh giới, giả thuyết về nguyên nhân sẽ sai ngay từ đầu.

### 2. Thiết lập mốc thời gian

Đặt các mốc quan trọng lên cùng một dòng thời gian:

- Thời điểm độ trễ bắt đầu tăng.
- Thời điểm lưu lượng hoặc tỷ lệ đọc/ghi thay đổi.
- Thời điểm triển khai ứng dụng, thay đổi cấu hình hoặc schema.
- Thời điểm chạy backup, báo cáo, checkpoint hoặc tác vụ nền.
- Thời điểm thay đổi kế hoạch truy vấn hoặc thống kê.
- Thời điểm lỗi kết nối, chờ khóa hoặc độ trễ lưu trữ tăng.

Dùng cùng múi giờ và kiểm tra độ lệch đồng hồ giữa ứng dụng, máy chủ cơ sở dữ liệu và hệ thống giám sát. Chọn độ phân giải phù hợp với hiện tượng: biểu đồ 5 phút có thể che mất một đợt nghẽn kéo dài 20 giây; biểu đồ 1 giây có thể quá nhiễu để đánh giá xu hướng dài.

Một chỉ số xuất hiện trước kết quả là điều kiện cần để xem xét một số giả thuyết nhân quả, nhưng chưa đủ để chứng minh. Có thể có dữ liệu bị trễ, đồng hồ lệch hoặc nguyên nhân chưa được quan sát.

### 3. So sánh những khoảng thời gian tương đương

Khi so sánh trước và sau, cần giữ các điều kiện quan trọng càng giống nhau càng tốt:

- Cùng khung giờ và ngày trong tuần.
- Cùng nhóm truy vấn hoặc fingerprint.
- Lưu lượng, concurrency và tỷ lệ đọc/ghi gần tương đương.
- Cùng node, loại phần cứng và cấu hình.
- Cùng trạng thái cache hoặc có ghi nhận khác biệt cache nóng/lạnh.
- Cùng cách tính phân vị, histogram, timeout và mẫu số.
- Không có tác vụ nền khác biệt đáng kể.

Nếu workload thay đổi, hãy phân nhóm trước khi so sánh. Chẳng hạn, tổng p95 của toàn hệ thống có thể tăng vì tỷ lệ truy vấn báo cáo dài tăng lên, dù p95 của từng nhóm truy vấn không đổi. Ngược lại, p95 tổng thể có thể giảm do nhiều truy vấn ngắn hơn, trong khi một nhóm giao dịch quan trọng lại chậm hơn.

Đây là một dạng nghịch lý Simpson: xu hướng trong dữ liệu gộp có thể khác với xu hướng bên trong từng nhóm. Khi thấy số liệu tổng hợp bất ngờ, hãy phân tích theo workload, tenant, node, loại truy vấn và mức độ quan trọng.

### 4. Tạo các giả thuyết có thể bác bỏ

Một giả thuyết hữu ích phải dự đoán được dấu hiệu có thể quan sát và điều kiện khiến giả thuyết bị bác bỏ.

Ví dụ:

| Quan sát | Giả thuyết cần kiểm tra | Bằng chứng hỗ trợ hoặc bác bỏ |
|---|---|---|
| p95 tăng, CPU gần 100% | CPU là nút thắt | CPU bão hòa kéo dài, hàng đợi runnable tăng, truy vấn tiêu thụ CPU cao; nếu CPU thấp và phiên chủ yếu chờ khóa thì giả thuyết yếu đi |
| Độ trễ tăng cùng I/O latency | Lưu trữ đang giới hạn tải | I/O queue và thời gian chờ đọc/ghi tăng trên cùng node; kiểm tra xem có truy vấn đọc nhiều trang hay tác vụ nền |
| Số phiên hoạt động tăng | Concurrency làm tăng tranh chấp | Lock wait, pool wait hoặc hàng đợi tăng; nếu phiên tăng nhưng không có chờ và throughput vẫn ổn định thì chưa đủ bằng chứng |
| Cache hit giảm | Cache thiếu dung lượng hoặc working set thay đổi | Physical read tăng, áp lực bộ nhớ tăng, dữ liệu nóng bị đẩy ra; cần loại trừ việc workload chuyển sang tập dữ liệu khác |
| Một fingerprint chậm sau triển khai | Thay đổi SQL hoặc kế hoạch gây hồi quy | So sánh câu lệnh, tham số, kế hoạch, ước lượng và số hàng thực tế trước/sau |

Không nên viết giả thuyết theo cách không thể kiểm chứng, ví dụ “có vẻ database quá tải”. Hãy nêu rõ chỉ số nào phải thay đổi, thay đổi theo hướng nào và trong khoảng thời gian nào nếu giả thuyết đúng.

### 5. Kiểm tra bằng nhiều nguồn dữ liệu

Một nguồn số liệu thường chỉ phản ánh một phần của vấn đề. Kết hợp các lớp quan sát:

- **Ứng dụng và trace:** thời gian chờ pool, thời gian gọi SQL, thời gian nhận kết quả, timeout và retry.
- **Thống kê truy vấn:** số lần gọi, tổng thời gian, thời gian trung bình, số hàng đọc/trả về, số lần đọc vật lý và fingerprint.
- **Kế hoạch thực thi:** scan, join, sort, ước lượng số hàng, số hàng thực tế và việc sử dụng chỉ mục.
- **Giao dịch và khóa:** thời gian chờ khóa, deadlock, giao dịch lâu, phiên chặn và chuỗi blocking.
- **Tài nguyên:** CPU, bộ nhớ, cache, IOPS, throughput, độ trễ lưu trữ và hàng đợi I/O.
- **Lưu lượng:** QPS/TPS, concurrency, tỷ lệ đọc/ghi, kích thước giao dịch và phân bố tham số.

Nếu thống kê truy vấn cho thấy một fingerprint có tổng thời gian rất cao, điều đó có thể do mỗi lần chạy chậm hoặc do nó được gọi quá thường xuyên. Hãy tách hai yếu tố bằng cách xem số lần gọi và thời gian mỗi lần. Nếu kế hoạch thực thi cho thấy quét nhiều hàng, hãy đối chiếu với số hàng thực tế và điều kiện lọc. Nếu truy vấn có vẻ hiệu quả nhưng thời gian thực tế cao, hãy kiểm tra thời gian chờ khóa, I/O và truyền kết quả.

## Đọc các cặp chỉ số thường gây nhầm lẫn

### CPU và độ trễ truy vấn

CPU cao cùng độ trễ cao là dấu hiệu cần điều tra, không phải kết luận tự động. Hãy kiểm tra:

- CPU có bão hòa liên tục hay chỉ tăng trong thời gian ngắn?
- Phiên hoạt động có đang chạy trên CPU hay phần lớn đang chờ?
- Truy vấn nào đóng góp nhiều CPU nhất?
- Số hàng được xử lý có tăng do thay đổi workload hoặc kế hoạch?
- Có tác vụ nền, backup, nén, tạo chỉ mục hoặc bảo trì chạy đồng thời?
- Throughput tăng cùng CPU hay CPU tăng nhưng throughput giảm?

Nếu CPU cao, throughput tăng tương ứng và độ trễ vẫn trong mục tiêu, hệ thống có thể đang xử lý tải lớn một cách bình thường. Nếu CPU tăng nhưng throughput không tăng, hàng đợi và độ trễ tăng mạnh, có thể đã chạm giới hạn xử lý hoặc gặp một truy vấn tiêu tốn tài nguyên bất thường.

CPU thấp cũng không loại trừ nút thắt. Các phiên có thể chờ I/O, khóa, mạng hoặc kết nối. Một hệ thống có CPU 20% vẫn có thể phản hồi rất chậm nếu tất cả giao dịch quan trọng đều chờ cùng một khóa.

### I/O và cache hit

I/O cao có thể là nguyên nhân trực tiếp làm truy vấn chậm, nhưng cũng có thể là hệ quả của việc truy vấn quét nhiều dữ liệu. Cần xem độ trễ I/O, hàng đợi, throughput, số trang đọc và loại thao tác.

Cache hit cao không đồng nghĩa không có vấn đề bộ nhớ. Chỉ số hit có thể được tính trên một loại truy cập hoặc phạm vi trang nhất định; một truy vấn vẫn có thể đọc nhiều trang trong cache và tiêu thụ CPU đáng kể. Một tỷ lệ hit giảm cũng không nhất thiết do thiếu bộ nhớ: workload có thể chuyển sang dữ liệu ít được truy cập, hoặc cache vừa được làm nóng lại sau khi khởi động.

Hãy kết hợp cache hit với physical read, working set, memory pressure, page eviction, I/O latency và thống kê theo truy vấn. Không tăng bộ nhớ chỉ vì một biểu đồ cache hit giảm mà chưa xác định dữ liệu nào bị đẩy khỏi cache và tác động đến độ trễ ra sao.

### Số kết nối, phiên hoạt động và lock wait

Số kết nối là số kênh kết nối đã mở; số phiên hoạt động phản ánh các phiên đang xử lý hoặc chờ công việc tùy cách hệ quản trị định nghĩa. Hai số này không đồng nghĩa.

Nếu kết nối tăng nhưng phần lớn ở trạng thái idle, nguyên nhân có thể nằm ở pool hoặc cách quản lý kết nối. Nếu phiên hoạt động tăng cùng lock wait và giao dịch lâu, cần kiểm tra chuỗi blocking, thứ tự cập nhật tài nguyên và phạm vi giao dịch. Nếu tăng pool làm nhiều câu lệnh chạy đồng thời hơn, nó có thể khuếch đại tranh chấp và làm độ trễ tăng.

Hãy kiểm tra thời gian chờ lấy kết nối riêng với thời gian chờ khóa. Chờ pool cao nhưng lock wait thấp có thể chỉ ra giới hạn ở pool hoặc giới hạn concurrency có chủ đích. Lock wait cao cần xem giao dịch giữ khóa, câu lệnh chặn và thời gian giao dịch mở.

### Throughput và độ trễ

Throughput là số thao tác hoàn thành trong một đơn vị thời gian; độ trễ là thời gian một thao tác cần để hoàn tất. Hai đại lượng thường có quan hệ nhưng không thể thay thế nhau.

Khi tải thấp, tăng concurrency có thể làm throughput tăng mà độ trễ chỉ thay đổi ít. Khi tài nguyên tiến gần bão hòa, throughput có thể chững lại trong khi độ trễ tăng nhanh do hàng đợi. Nếu throughput giảm cùng độ trễ tăng, cần tìm sự cố, tranh chấp hoặc thay đổi workload. Nếu throughput tăng và độ trễ tăng nhẹ, cần so sánh với mục tiêu dịch vụ và dung lượng dự phòng trước khi kết luận có hồi quy.

Không đánh giá throughput riêng lẻ. Một hệ thống hoàn thành nhiều truy vấn hơn bằng cách trả về ít dữ liệu hơn, bỏ qua tác vụ hoặc tăng lỗi không phải là cải thiện chất lượng dịch vụ.

## Kiểm chứng quan hệ nhân quả

### Dự đoán điều gì sẽ xảy ra nếu giả thuyết đúng

Một giả thuyết nhân quả cần tạo ra dự đoán cụ thể. Ví dụ:

**Giả thuyết:** truy vấn danh sách đơn hàng chậm vì kế hoạch quét quá nhiều hàng.

Dự đoán:

- Fingerprint đó có số hàng đọc cao so với số hàng trả về.
- Kế hoạch có scan rộng hoặc sort trên tập dữ liệu lớn.
- Thời gian thực thi chiếm phần lớn thời gian lời gọi.
- Một chỉ mục phù hợp hoặc điều kiện truy vấn chọn lọc hơn sẽ giảm số hàng cần đọc.
- Sau thay đổi, thời gian truy vấn và tỷ lệ thao tác trong ngưỡng cải thiện ở cùng workload; chi phí ghi và dung lượng chỉ mục có thể tăng.

Nếu dữ liệu cho thấy thời gian truy vấn chủ yếu là lock wait, thêm chỉ mục có thể không giải quyết vấn đề. Dự đoán bị bác bỏ là thông tin hữu ích, giúp chuyển sang giả thuyết khác.

### Thử nghiệm có kiểm soát

Khi có thể, thay đổi một yếu tố trong môi trường thử nghiệm hoặc trên một nhóm nhỏ có kiểm soát. Quy trình cơ bản:

1. Ghi lại giả thuyết, chỉ số kết quả chính và các chỉ số bảo vệ.
2. Tạo tải đại diện với dữ liệu, phân bố tham số và concurrency gần thực tế.
3. Đo baseline nhiều lần để biết mức dao động tự nhiên.
4. Thay đổi một yếu tố chính, giữ các điều kiện khác ổn định.
5. Chạy lại cùng workload và cùng cách đo.
6. So sánh kết quả chính, các chỉ số phụ và tác động lên nhóm tải khác.
7. Lặp lại để kiểm tra tính ổn định; hoàn nguyên nếu kết quả xấu hoặc có rủi ro.

Ví dụ, để kiểm tra tác động của một chỉ mục mới, chạy cùng tập truy vấn trước và sau trên dữ liệu tương đương. So sánh số hàng đọc, thời gian thực thi, p95/p99, CPU, I/O và thời gian ghi. Chỉ mục có thể làm đọc nhanh hơn nhưng tăng chi phí INSERT/UPDATE, dung lượng lưu trữ và thời gian bảo trì. Một phép thử chỉ đo truy vấn đọc sẽ bỏ sót các tác động này.

Không thay đổi nhiều tham số cùng lúc nếu mục tiêu là xác định nguyên nhân. Nếu đồng thời tăng bộ nhớ, tăng pool và thêm chỉ mục, dù kết quả tốt hơn cũng khó biết thay đổi nào tạo ra cải thiện hoặc thay đổi nào gây tác dụng phụ.

### Đối chứng và canary

Nếu không thể tạo môi trường thử nghiệm giống production, có thể triển khai thay đổi theo canary hoặc nhóm đối chứng:

- Áp dụng thay đổi cho một phần nhỏ node, tenant hoặc lưu lượng.
- Giữ một nhóm tương đương không thay đổi trong cùng thời gian.
- So sánh xu hướng trước/sau giữa hai nhóm.
- Kiểm tra hai nhóm có workload và đặc điểm dữ liệu tương đồng không.
- Mở rộng dần khi chỉ số chính cải thiện và các chỉ số bảo vệ ổn định.

Cách làm này giảm ảnh hưởng của biến động chung như lưu lượng toàn hệ thống. Tuy nhiên, nó chỉ đáng tin khi nhóm đối chứng thực sự tương đồng và không bị tác động lan truyền từ nhóm thử nghiệm. Với cơ sở dữ liệu dùng chung, một thay đổi trên một tenant có thể ảnh hưởng CPU, cache hoặc I/O của tenant khác; cần xem xét sự can thiệp giữa các nhóm.

### So sánh trước và sau khi không có đối chứng

Trong một số trường hợp, chỉ có thể quan sát một thay đổi trước/sau. Khi đó:

- Chọn cửa sổ đủ dài để bao quát biến động tải.
- So sánh cùng khung giờ và loại workload.
- Ghi nhận triển khai, tác vụ nền và thay đổi dữ liệu.
- Dùng nhiều chỉ số để kiểm tra cơ chế dự kiến.
- Lặp lại quan sát nếu có thể.
- Diễn đạt kết luận ở mức phù hợp: “kết quả phù hợp với giả thuyết” thay vì “đã chứng minh chắc chắn”.

Nếu có dữ liệu của một nhóm không thay đổi, có thể dùng phương pháp sai khác-trong-sai khác (difference-in-differences): so sánh mức thay đổi trước/sau của nhóm thử nghiệm với mức thay đổi cùng kỳ của nhóm đối chứng. Phương pháp này vẫn cần giả định xu hướng trước can thiệp của hai nhóm tương đương và không có thay đổi riêng chỉ tác động đến một nhóm.

### Dùng mô hình thống kê đúng giới hạn

Hồi quy có thể giúp kiểm soát một số yếu tố như QPS, tỷ lệ ghi, kích thước kết quả, giờ trong ngày hoặc node. Tuy nhiên, mô hình chỉ kiểm soát được những biến đã đo và được đưa vào đúng cách. Biến bị bỏ sót, quan hệ phi tuyến, dữ liệu phụ thuộc theo thời gian hoặc lựa chọn mẫu sai vẫn có thể tạo kết luận sai.

Phân tích tương quan có độ trễ (lag correlation) có thể cho biết một biến thường thay đổi trước biến khác bao lâu. Đây là công cụ tạo giả thuyết, không phải bằng chứng nhân quả: hai biến có thể cùng phản ứng với một sự kiện thứ ba, hoặc dữ liệu có chu kỳ chung.

Khi phân tích chuỗi thời gian, cần chú ý xu hướng dài hạn, mùa vụ, tự tương quan và thay đổi chế độ vận hành. Hai chuỗi cùng tăng theo thời gian có thể có tương quan cao dù không có liên hệ trực tiếp. Có thể phân tích phần thay đổi quanh baseline hoặc loại xu hướng theo cách phù hợp, nhưng kết quả vẫn cần kiểm chứng bằng cơ chế và thử nghiệm.

## Ví dụ thực tế: độ trễ tăng cùng số phiên hoạt động

Một dịch vụ giao dịch ghi nhận p95 của thao tác cập nhật tăng từ 70 ms lên 260 ms. Cùng lúc, số phiên hoạt động tăng gấp đôi. Nhóm ban đầu nghi ngờ connection pool quá nhỏ và đề xuất tăng giới hạn kết nối.

Trước khi thay đổi, nhóm tách thời gian thành các phần:

| Chỉ số | Trước khi sự cố | Trong sự cố |
|---|---:|---:|
| p95 thao tác cập nhật | 70 ms | 260 ms |
| Phiên hoạt động | 80 | 165 |
| Thời gian chờ pool p95 | 8 ms | 10 ms |
| Lock wait p95 | 2 ms | 145 ms |
| CPU trung bình | 55% | 61% |
| Throughput ghi | 1.200/s | 1.180/s |

Thời gian chờ pool chỉ tăng nhẹ, trong khi lock wait tăng mạnh và throughput gần như không tăng. Dữ liệu này làm giả thuyết “pool quá nhỏ” yếu đi. Số phiên hoạt động tăng có thể là hậu quả của giao dịch bị giữ lâu vì chờ khóa.

Nhóm kiểm tra trace và phát hiện một tác vụ cập nhật theo lô giữ khóa trên cùng nhóm bản ghi trong thời gian dài. Một luồng cập nhật trực tuyến phải chờ tác vụ này. Sau khi chia lô nhỏ hơn và rút ngắn thời gian giao dịch, nhóm chạy lại cùng tải:

| Chỉ số | Trong sự cố | Sau điều chỉnh |
|---|---:|---:|
| p95 thao tác cập nhật | 260 ms | 82 ms |
| Phiên hoạt động | 165 | 92 |
| Lock wait p95 | 145 ms | 7 ms |
| Throughput ghi | 1.180/s | 1.230/s |

Kết quả phù hợp với giả thuyết tranh chấp khóa là nguyên nhân chính. Tuy vậy, nhóm vẫn theo dõi các giao dịch khác, deadlock, tính nhất quán dữ liệu và chi phí xử lý lô. Ví dụ này cho thấy số phiên hoạt động có tương quan với độ trễ nhưng không nhất thiết là điểm cần tăng cấu hình.

## Một ví dụ khác: I/O tăng sau khi truy vấn chậm

Một truy vấn báo cáo có thời gian thực thi tăng từ 1 giây lên 8 giây; đồng thời I/O đọc và hàng đợi lưu trữ tăng. Có ít nhất hai hướng giải thích:

- Truy vấn đọc nhiều trang hơn do kế hoạch thực thi thay đổi, khiến I/O tăng và truy vấn chậm.
- Một tác vụ khác làm thiết bị lưu trữ bận, khiến truy vấn phải chờ I/O dù số trang đọc không đổi.

Để phân biệt, nhóm so sánh fingerprint, số trang đọc, kế hoạch thực thi, thời gian chờ I/O theo phiên và tác vụ nền. Nếu số trang đọc của truy vấn tăng đột biến cùng thay đổi kế hoạch, giả thuyết về truy vấn có cơ sở hơn. Nếu số trang đọc ổn định nhưng độ trễ mỗi lần đọc và hàng đợi thiết bị tăng đồng loạt trên nhiều truy vấn, cần điều tra tải lưu trữ dùng chung.

Nhóm có thể thử chạy báo cáo trên bản sao dữ liệu hoặc ở thời điểm không có tác vụ nền, đồng thời giữ nguyên tham số và kế hoạch nếu có thể. Việc di chuyển báo cáo sang thời điểm khác có thể cải thiện trải nghiệm, nhưng không chứng minh truy vấn đã được tối ưu; cần đánh giá riêng chi phí tài nguyên và yêu cầu hoàn thành báo cáo.

## Những sai lầm thường gặp

- **Kết luận từ hai đường biểu đồ cùng tăng:** bỏ qua biến gây nhiễu như lưu lượng, workload hoặc tác vụ nền.
- **Coi chỉ số xuất hiện trước là nguyên nhân:** thứ tự thời gian giúp loại một số giả thuyết nhưng không đủ chứng minh quan hệ nhân quả.
- **Tối ưu theo chỉ số dễ nhìn nhất:** tăng pool, CPU hoặc bộ nhớ mà chưa xác định thời gian đang bị tiêu thụ ở đâu.
- **So sánh dữ liệu gộp:** che khuất khác biệt giữa truy vấn, tenant, node và tỷ lệ đọc/ghi.
- **Thay đổi nhiều biến cùng lúc:** không thể xác định yếu tố nào tạo ra kết quả.
- **Chỉ đo chỉ số mục tiêu:** bỏ qua chi phí ghi, dung lượng chỉ mục, lỗi, deadlock hoặc tác động đến workload khác.
- **Bỏ qua độ trễ đo lường:** ghép dữ liệu từ các hệ thống có đồng hồ lệch hoặc cửa sổ lấy mẫu khác nhau.
- **Coi tương quan thống kê là bằng chứng:** hệ số cao hoặc p-value nhỏ không tự chứng minh cơ chế nhân quả.
- **Không lặp lại phép đo:** một lần chạy có thể bị ảnh hưởng bởi cache, checkpoint, tải nền hoặc nhiễu ngẫu nhiên.
- **Không nêu mức độ chắc chắn:** biến một giả thuyết hợp lý thành kết luận tuyệt đối dù chưa có đối chứng.

## Checklist phân tích trước khi thay đổi hệ thống

- [ ] Xác định rõ chỉ số kết quả, phạm vi, đơn vị và cửa sổ thời gian.
- [ ] Phân biệt thời gian ứng dụng quan sát với thời gian thực thi SQL tại máy chủ.
- [ ] Ghi lại các sự kiện triển khai, thay đổi cấu hình và tác vụ nền.
- [ ] So sánh cùng workload, lưu lượng, concurrency và nhóm truy vấn.
- [ ] Kiểm tra biến gây nhiễu, nhân quả ngược và các yếu tố có thể tác động đồng thời.
- [ ] Viết giả thuyết có dự đoán cụ thể và điều kiện bác bỏ.
- [ ] Đối chiếu trace, thống kê truy vấn, kế hoạch thực thi, khóa và tài nguyên.
- [ ] Thử nghiệm một thay đổi chính trong điều kiện có thể so sánh.
- [ ] Theo dõi cả chỉ số mục tiêu lẫn các chỉ số bảo vệ.
- [ ] Lặp lại, ghi nhận giới hạn và diễn đạt kết luận theo mức bằng chứng.

## Cách trình bày kết luận kỹ thuật

Một báo cáo phân tích tốt nên tách rõ quan sát, giả thuyết, bằng chứng và kết luận:

- **Quan sát:** điều gì đã thay đổi, trong phạm vi và thời gian nào?
- **Giả thuyết:** cơ chế nào có thể giải thích biến động?
- **Bằng chứng:** số liệu nào hỗ trợ hoặc làm yếu giả thuyết?
- **Kiểm chứng:** đã can thiệp hoặc đối chứng như thế nào?
- **Kết quả:** chỉ số nào thay đổi, có lặp lại được không, tác động phụ là gì?
- **Giới hạn:** yếu tố nào chưa đo được hoặc giả định nào chưa kiểm tra?

Ví dụ về cách diễn đạt có căn cứ: “Trong cùng nhóm truy vấn và mức tải tương đương, lock wait tăng trước khi p95 cập nhật tăng. Trace xác định các giao dịch trực tuyến chờ một tác vụ cập nhật theo lô. Sau khi chia nhỏ lô, lock wait và p95 cùng giảm trong ba lần chạy tải đại diện; kết quả hỗ trợ giả thuyết tranh chấp khóa là nguyên nhân chính trong tình huống này.”

Cách diễn đạt này cho người đọc biết điều đã quan sát, cơ chế được kiểm tra và giới hạn của kết luận. Nếu chưa có thử nghiệm hoặc nhóm đối chứng, hãy ghi rõ đó là giả thuyết có bằng chứng hỗ trợ và cần kiểm chứng thêm.

Phân biệt tương quan với nguyên nhân là nền tảng của phương pháp đo hiệu năng có trách nhiệm. Khi kết nối chỉ số với workload, kế hoạch thực thi, thống kê giao dịch và cơ chế tài nguyên, nhóm có thể chọn đúng điểm cần điều chỉnh, tránh tối ưu nhầm và chứng minh thay đổi thực sự cải thiện chất lượng dịch vụ.
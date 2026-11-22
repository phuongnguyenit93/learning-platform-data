# Kiểm soát dữ liệu, cấu hình, phiên bản và tài nguyên môi trường đo

Một phép đo hiệu năng cơ sở dữ liệu chỉ có ý nghĩa khi ta biết chính xác điều kiện tạo ra kết quả đó. Cùng một câu SQL có thể chạy nhanh ở máy phát triển nhưng chậm ở production vì dữ liệu khác nhau, thống kê khác nhau, cấu hình bộ nhớ khác nhau, phiên bản hệ quản trị khác nhau hoặc tài nguyên CPU, RAM và I/O bị giới hạn. Ngay cả hai lần chạy trên cùng một máy cũng có thể cho kết quả khác nhau nếu cache, tải đồng thời hoặc tác vụ nền thay đổi.

Trong tối ưu hiệu năng, đo đạc cần trả lời hai câu hỏi: truy vấn tiêu thụ tài nguyên như thế nào và kết quả có thể so sánh được với lần đo trước hay không. Muốn trả lời đáng tin cậy, cần kiểm soát và ghi lại bốn nhóm yếu tố: dữ liệu thử nghiệm, cấu hình cơ sở dữ liệu, phiên bản phần mềm và tài nguyên của toàn bộ môi trường đo. Đây là nền tảng để xác định một thay đổi SQL hoặc chỉ mục thực sự tạo ra cải thiện.

## 1. Vì sao phải kiểm soát môi trường đo?

Hiệu năng không chỉ phụ thuộc vào câu lệnh SQL. Bộ tối ưu lập kế hoạch dựa trên thống kê và cấu hình; bộ máy thực thi phụ thuộc vào cache, CPU, bộ nhớ và I/O; ứng dụng còn chịu chi phí kết nối, truyền dữ liệu và xử lý kết quả.

Ví dụ, một truy vấn lọc đơn hàng theo ngày có thể dùng Index Seek khi bảng chỉ có vài nghìn hàng. Khi bảng tăng lên hàng chục triệu hàng và phân bố ngày không đồng đều, bộ tối ưu có thể chọn kế hoạch khác. Nếu lần đo thứ hai đồng thời có buffer cache nóng hơn, ta có thể nhầm lợi ích của cache với lợi ích từ chỉ mục vừa tạo.

Một phép so sánh chỉ đáng tin khi các yếu tố không thuộc phạm vi thử nghiệm được giữ tương đương. Nếu chủ đích đánh giá tác động của một chỉ mục, dữ liệu, tham số, phiên bản, cấu hình, tải đồng thời và trạng thái cache cần được kiểm soát. Nếu chủ đích đánh giá nâng cấp phiên bản, cần giữ tương đương dữ liệu, workload và tài nguyên, đồng thời ghi lại các khác biệt cấu hình mặc định giữa hai phiên bản.

Hãy phân biệt:

- **Biến cần thử nghiệm:** yếu tố ta cố ý thay đổi, chẳng hạn câu SQL, chỉ mục, cấu hình bộ nhớ hoặc phiên bản.
- **Biến cần kiểm soát:** yếu tố phải giữ ổn định để kết quả có thể quy về biến thử nghiệm, chẳng hạn dữ liệu, tham số, tải đồng thời và tài nguyên.
- **Nhiễu đo lường:** biến động ngoài ý muốn như tác vụ backup, checkpoint, autovacuum, truy vấn của người dùng khác, máy ảo dùng chung CPU hoặc độ trễ mạng thay đổi.

Không thể loại bỏ mọi biến động trong hệ thống thực. Mục tiêu là ghi nhận các biến quan trọng, giảm nhiễu có thể kiểm soát và lặp lại phép đo đủ số lần để nhận ra xu hướng thay vì kết luận từ một kết quả đơn lẻ.

## 2. Kiểm soát dữ liệu thử nghiệm

Dữ liệu là một phần của môi trường thực thi. Hai cơ sở dữ liệu có cùng số hàng vẫn có thể tạo ra kế hoạch và thời gian rất khác nhau nếu phân bố giá trị, độ rộng hàng, số giá trị khác nhau hoặc mức độ tập trung dữ liệu không giống nhau.

### 2.1. Giữ quy mô và cấu trúc dữ liệu tương đương

Khi chuẩn bị dữ liệu, cần ghi nhận ít nhất:

- Số hàng của từng bảng chính và các bảng tham gia join.
- Kích thước bảng, chỉ mục và các phân vùng nếu có.
- Số lượng giá trị phân biệt (cardinality) của các cột lọc và cột join.
- Tỷ lệ NULL, giá trị mặc định, hàng bị xóa logic và các giá trị ngoại lệ.
- Độ rộng trung bình của hàng, đặc biệt với VARCHAR/TEXT, JSON và dữ liệu nhị phân.
- Mức độ phân bố theo thời gian, trạng thái, khách hàng, khu vực hoặc khóa nghiệp vụ.

Ví dụ, bảng orders có 10 triệu hàng nhưng 80% đơn hàng tập trung vào 5% khách hàng sẽ tạo hành vi khác với dữ liệu phân bố đều. Một chỉ mục trên customer_id có thể rất hữu ích cho một khách hàng ít đơn, nhưng truy vấn của khách hàng lớn có thể phải đọc một phần đáng kể bảng. Dữ liệu kiểm thử chỉ gồm các khách hàng có quy mô trung bình sẽ bỏ sót trường hợp lệch phân bố quan trọng.

### 2.2. Bảo toàn phân bố và độ lệch dữ liệu

Không nên chỉ tạo dữ liệu giả bằng cách tăng số hàng theo phân bố đều. Dữ liệu thực thường có:

- **Skew:** một số giá trị xuất hiện nhiều hơn hẳn phần còn lại.
- **Hot keys:** một số khóa được truy cập thường xuyên, gây tập trung tải.
- **Tương quan giữa cột:** ví dụ trạng thái đơn hàng có tương quan với thời điểm tạo đơn.
- **Phân bố theo thời gian:** dữ liệu mới được truy cập thường xuyên hơn dữ liệu cũ.
- **Giá trị hiếm:** các trường hợp ít gặp nhưng có thể làm kế hoạch hoặc logic truy vấn thay đổi.

Một bộ dữ liệu đại diện nên giữ các đặc điểm này ở mức phù hợp với mục tiêu thử nghiệm. Nếu không thể sao chép dữ liệu production, hãy tạo dữ liệu tổng hợp dựa trên thống kê phân bố đã được phê duyệt, thay vì chỉ mô phỏng số lượng hàng.

### 2.3. Dùng snapshot nhất quán

Khi so sánh trước và sau một thay đổi, nên sử dụng cùng một snapshot dữ liệu hoặc hai bản sao được tạo từ cùng thời điểm. Nếu dữ liệu tiếp tục được thêm, cập nhật hoặc xóa giữa các lần đo, truy vấn có thể phải đọc lượng dữ liệu khác nhau và bộ tối ưu có thể chọn kế hoạch khác.

Với hệ thống thử nghiệm, có thể chuẩn bị bản sao cơ sở dữ liệu từ backup hoặc snapshot đã xác định. Ghi lại thời điểm tạo snapshot, phạm vi dữ liệu, trạng thái migration và các bước nạp dữ liệu. Nếu phải nạp lại dữ liệu giữa các lượt chạy, dùng cùng quy trình và kiểm tra số hàng, kích thước bảng cùng các ràng buộc quan trọng.

Snapshot cũng cần phản ánh trạng thái chỉ mục và phân vùng. Một bản sao dữ liệu có cùng hàng nhưng thiếu chỉ mục, thiếu phân vùng hoặc khác trạng thái bảo trì không phải là môi trường so sánh tương đương.

### 2.4. Kiểm soát thống kê của bộ tối ưu

Bộ tối ưu dùng thống kê để ước lượng số hàng, độ chọn lọc và chi phí của các phương án thực thi. Thống kê cũ hoặc khác nhau giữa hai môi trường có thể khiến kế hoạch khác nhau dù dữ liệu tương tự.

Trước khi đo, hãy ghi nhận:

- Thời điểm cập nhật thống kê gần nhất.
- Cấu hình lấy mẫu hoặc mức độ chi tiết của thống kê nếu hệ quản trị cung cấp.
- Thống kê histogram, số giá trị phân biệt hoặc thống kê mở rộng liên quan đến các cột quan trọng.
- Sự khác biệt giữa số hàng ước lượng và số hàng thực tế trong execution plan.

Khi cần cập nhật thống kê, thực hiện theo quy trình phù hợp với hệ quản trị và môi trường thử nghiệm. Sau khi cập nhật, hãy ghi lại thao tác vì nó có thể làm thay đổi kế hoạch. Không cập nhật thống kê chỉ ở một phía rồi coi hai kết quả là phép so sánh thuần túy về SQL hoặc chỉ mục.

### 2.5. Bảo vệ dữ liệu nhạy cảm

Nếu dùng bản sao production, cần tuân thủ quy trình bảo vệ dữ liệu của tổ chức. Có thể che hoặc thay thế thông tin định danh, token, thông tin thanh toán và dữ liệu cá nhân trước khi đưa vào môi trường thử nghiệm. Việc che dữ liệu cần giữ được kiểu dữ liệu, độ dài, phân bố, quan hệ khóa và đặc điểm truy cập đủ gần với workload cần đánh giá.

Che dữ liệu quá đơn giản có thể làm mất skew hoặc tương quan giữa các cột, khiến kết quả benchmark không còn đại diện. Ngược lại, sao chép nguyên dữ liệu nhạy cảm vào môi trường không được bảo vệ tạo rủi ro không cần thiết. Hãy chọn phương pháp tạo dữ liệu tổng hợp hoặc masking đã được kiểm chứng cho mục tiêu đo.

## 3. Kiểm soát cấu hình cơ sở dữ liệu

Cấu hình ảnh hưởng đến kế hoạch và khả năng thực thi. Cần ghi lại cấu hình liên quan trực tiếp đến workload, thay vì chỉ lưu một bản chụp cấu hình tổng quát mà không biết giá trị nào tác động đến phép đo.

### 3.1. Bộ nhớ và cache

Các cấu hình bộ nhớ thường ảnh hưởng rõ rệt đến truy vấn:

- Bộ nhớ dành cho buffer cache hoặc buffer pool.
- Bộ nhớ làm việc cho sort, hash join, aggregate và thao tác trung gian.
- Bộ nhớ dành cho mỗi kết nối hoặc mỗi phiên.
- Giới hạn bộ nhớ của tiến trình, container hoặc máy ảo.
- Cấu hình cache phía hệ điều hành và các giới hạn cgroup nếu có.

Nếu bộ nhớ đủ lớn để giữ working set trong cache, truy vấn có thể giảm đọc vật lý ở các lần chạy sau. Khi bộ nhớ nhỏ hoặc nhiều truy vấn cạnh tranh, cùng truy vấn có thể phải đọc lại trang từ storage hoặc spill dữ liệu tạm ra đĩa.

Không tăng bộ nhớ tùy tiện chỉ để làm một truy vấn benchmark nhanh hơn. Một giá trị cấp cho từng phiên có thể nhân lên theo số phiên đồng thời và gây áp lực RAM toàn hệ thống. Hãy ghi nhận cả cấu hình trên mỗi truy vấn/phiên và số phiên chạy đồng thời.

### 3.2. Cấu hình song song và kết nối

Mức độ song song, số worker, giới hạn kết nối và hàng đợi có thể thay đổi throughput cũng như độ trễ. Một truy vấn chạy đơn lẻ có thể hưởng lợi từ nhiều worker, nhưng nhiều truy vấn song song cùng lúc có thể tranh chấp CPU và I/O.

Khi đo, ghi lại:

- Giới hạn worker hoặc mức độ parallelism.
- Số kết nối hoạt động và pool size phía ứng dụng.
- Số phiên đồng thời thực tế trong workload.
- Giới hạn hàng đợi, timeout và các giới hạn tài nguyên theo người dùng hoặc workload group.

Nếu đang kiểm tra hiệu năng một truy vấn đơn, hãy giữ số phiên đồng thời ổn định. Nếu đang kiểm tra tải tổng thể, cần tái tạo mức concurrency, tỷ lệ đọc/ghi và thời gian suy nghĩ của client gần với thực tế.

### 3.3. Cấu hình I/O và hành vi lưu trữ

Hệ quản trị có thể có cấu hình liên quan đến checkpoint, flush, read-ahead, prefetch, số luồng I/O, giới hạn IOPS hoặc cách đồng bộ ghi. Các giá trị này cần được ghi nhận khi phép đo liên quan đến đọc/ghi lưu trữ.

Ngoài cấu hình database, cần biết loại volume, filesystem, mức IOPS và throughput được cấp, độ trễ lưu trữ, chính sách burst và giới hạn của nhà cung cấp cloud. Một volume có thể đạt tốc độ cao trong thời gian ngắn nhờ burst credit rồi giảm khi tín dụng cạn. Nếu không ghi lại điều kiện này, hai lần benchmark có thể không so sánh được.

### 3.4. Cấu hình giao dịch và phiên

Isolation level, autocommit, transaction timeout, lock timeout, deadlock detection và cách ứng dụng giữ transaction mở có thể ảnh hưởng đến blocking và thời gian chờ. Một phép đo chạy SELECT độc lập không phản ánh được workload thực nếu production thường chạy trong transaction dài hoặc có nhiều thao tác ghi đồng thời.

Ghi lại các thuộc tính phiên có thể tác động đến kết quả: isolation level, timezone, collation, encoding, schema mặc định, biến session và kiểu tham số truyền vào. Cùng một giá trị tham số nhưng khác kiểu dữ liệu có thể làm thay đổi khả năng dùng chỉ mục hoặc cách chuyển kiểu.

### 3.5. Cấu hình phải được chụp cùng thời điểm đo

Không nên chỉ ghi cấu hình lúc dựng môi trường rồi giả định nó không thay đổi. Tự động hóa, DBA, autoscaling hoặc công cụ quản lý có thể thay đổi cấu hình trong quá trình chạy. Lưu bản chụp trước và sau lượt đo, đồng thời ghi lại thay đổi có chủ đích.

Một bảng kiểm cấu hình có thể gồm:

| Nhóm | Thông tin cần lưu | Vì sao cần |
|---|---|---|
| Bộ nhớ | Buffer pool/shared buffers, work memory, giới hạn RAM | Ảnh hưởng cache, sort/hash và spill |
| CPU/parallelism | Số vCPU, quota, worker, giới hạn song song | Ảnh hưởng tốc độ xử lý và tranh chấp |
| Kết nối | Max connections, pool size, số phiên thực tế | Ảnh hưởng concurrency và bộ nhớ |
| I/O | Loại volume, IOPS, throughput, giới hạn burst | Ảnh hưởng đọc/ghi và độ trễ |
| Giao dịch | Isolation, timeout, autocommit | Ảnh hưởng khóa và thời gian chờ |
| Bộ tối ưu | Cost settings, thống kê, plan cache | Ảnh hưởng lựa chọn kế hoạch |
| Phiên ứng dụng | Kiểu tham số, timezone, collation, encoding | Ảnh hưởng ngữ nghĩa và khả năng dùng chỉ mục |

## 4. Kiểm soát phiên bản phần mềm

Phiên bản hệ quản trị, hệ điều hành, driver và thư viện client đều có thể ảnh hưởng đến hiệu năng. Bản nâng cấp có thể thay đổi bộ tối ưu, thuật toán thực thi, quản lý bộ nhớ, giao thức hoặc mặc định cấu hình.

Thông tin nên ghi lại:

- Tên hệ quản trị, phiên bản chính, phiên bản phụ và build.
- Phiên bản engine/storage engine và các extension hoặc plugin đang sử dụng.
- Phiên bản hệ điều hành, kernel, filesystem và runtime/container.
- Phiên bản driver JDBC/ODBC hoặc thư viện kết nối.
- Phiên bản framework ORM, connection pool và ứng dụng phát workload.
- Phiên bản công cụ benchmark và cấu hình chạy công cụ đó.

Không nên chỉ ghi “PostgreSQL 16” hoặc “MySQL 8”. Bản vá và build cụ thể có thể bao gồm thay đổi hiệu năng hoặc sửa lỗi quan trọng. Khi so sánh hai phiên bản, cần liệt kê cả các giá trị cấu hình mặc định thay đổi giữa phiên bản và những extension đã được nâng cấp.

### 4.1. Kế hoạch thực thi và plan cache

Phiên bản mới có thể chọn kế hoạch khác cho cùng SQL vì bộ tối ưu hoặc cách thu thập thống kê thay đổi. Prepared statement, parameter sniffing, generic/custom plan hoặc plan cache cũng có thể làm kết quả phụ thuộc thứ tự tham số đã chạy trước đó.

Khi so sánh, xác định rõ đang đo:

- Truy vấn ad hoc hay prepared statement.
- Lần đầu biên dịch kế hoạch hay lần thực thi đã tái sử dụng kế hoạch.
- Một bộ tham số cố định hay phân bố tham số đại diện.
- Kế hoạch được giữ trong cache hay được tạo mới theo mỗi lượt.

Nếu production có nhiều kiểu tham số, chỉ đo một giá trị thuận lợi có thể che khuất trường hợp xấu. Hãy chọn một tập tham số gồm giá trị phổ biến, giá trị hiếm và trường hợp có độ chọn lọc khác biệt đáng kể.

### 4.2. Migration và khả năng tương thích

Trước khi đo phiên bản mới, xác nhận schema migration đã hoàn tất, chỉ mục được tạo đầy đủ, extension tương thích và dữ liệu đã được nâng cấp theo đúng quy trình. Một môi trường đang chạy migration hoặc rebuild chỉ mục sẽ tiêu thụ tài nguyên khác với môi trường ổn định.

Nếu nâng cấp làm thay đổi định dạng lưu trữ, collation hoặc hành vi kiểu dữ liệu, cần xác nhận tính đúng đắn của kết quả trước khi so sánh hiệu năng. Không được coi hai kết quả là tương đương nếu ngữ nghĩa truy vấn hoặc tập hàng trả về đã thay đổi.

## 5. Kiểm soát tài nguyên của toàn bộ môi trường đo

Môi trường đo gồm máy chủ cơ sở dữ liệu, máy phát tải, mạng, storage và các dịch vụ phụ trợ. Chỉ ghi cấu hình database là chưa đủ.

### 5.1. CPU và giới hạn thực tế

Ghi số CPU logic/vCPU, loại CPU nếu biết, quota và giới hạn của container hoặc máy ảo, mức CPU sử dụng trước và trong lúc đo. Một container có thể nhìn thấy nhiều CPU trên host nhưng chỉ được cấp quota nhỏ. CPU steal hoặc noisy neighbor trên máy ảo dùng chung cũng có thể làm thời gian chạy dao động.

Theo dõi cả mức sử dụng CPU của tiến trình database và CPU của máy phát tải. Nếu client không đủ CPU để gửi yêu cầu hoặc xử lý kết quả, throughput quan sát được có thể bị giới hạn ở client thay vì database.

### 5.2. RAM và áp lực bộ nhớ

Ghi tổng RAM, giới hạn container, bộ nhớ database được phép sử dụng, mức sử dụng thực tế và tình trạng swap. Khi máy bị memory pressure, hệ điều hành có thể thu hồi cache hoặc swap trang bộ nhớ, làm độ trễ tăng đột biến.

Đừng chỉ nhìn mức RAM còn trống. Cần quan sát working set, page faults, swap-in/swap-out, cache hit và các dấu hiệu spill của database. Nếu chạy nhiều workload cùng host, ghi lại tiến trình khác đang tiêu thụ bộ nhớ.

### 5.3. Storage và I/O

Các thuộc tính cần theo dõi gồm:

- Loại lưu trữ: local SSD, network block storage, SAN hoặc loại volume cloud.
- IOPS và throughput được cấp, mức sử dụng thực tế và giới hạn burst.
- Độ trễ đọc/ghi, queue depth và thời gian chờ I/O.
- Dung lượng trống, filesystem, mount options và tình trạng phân mảnh nếu phù hợp.
- Vị trí data file, transaction log/WAL, temporary files và backup.

Đặt data file, log và temporary files trên các volume khác nhau có thể thay đổi tranh chấp I/O. Khi đo cần giữ cách bố trí tương đương hoặc ghi rõ khác biệt. Một benchmark trên ổ local NVMe không thể dùng trực tiếp để dự báo hiệu năng trên volume mạng có giới hạn IOPS.

### 5.4. Mạng và máy phát tải

Độ trễ mạng, băng thông, TLS, DNS, connection establishment và vị trí địa lý của client ảnh hưởng đến thời gian end-to-end. Nếu chỉ muốn đo thời gian thực thi bên trong database, cần tách phần thời gian server khỏi thời gian client gửi câu lệnh và nhận kết quả.

Máy phát tải phải đủ năng lực tạo concurrency dự kiến. Nếu công cụ benchmark chạy trên cùng máy với database, CPU và RAM của hai bên có thể cạnh tranh. Nếu chạy từ máy khác, hãy ghi vị trí, RTT, băng thông và số kết nối. Không thay đổi topology mạng giữa hai lượt đo mà không ghi nhận.

### 5.5. Tác vụ nền và hàng xóm dùng chung tài nguyên

Backup, restore, checkpoint, vacuum, index maintenance, replication, ETL, antivirus scan, log rotation, batch job và các truy vấn của người dùng khác đều có thể ảnh hưởng đến phép đo. Trên môi trường cloud hoặc cluster dùng chung, cần lưu ý workload của tenant khác và giới hạn tài nguyên do nền tảng áp đặt.

Trước mỗi lượt đo, ghi lại các tác vụ nền đang chạy và mức tải nền. Nếu không thể dừng chúng, hãy đo tải nền cùng thời điểm và thực hiện nhiều lượt để hiểu biên độ dao động. Không tắt các cơ chế bảo vệ hoặc tác vụ vận hành production chỉ để có kết quả benchmark đẹp.

## 6. Phân biệt trạng thái cache và điều kiện khởi động

Cache là một trong những nguyên nhân phổ biến khiến phép đo không thể so sánh trực tiếp. Cần xác định rõ mục tiêu là đo cache lạnh, cache nóng hay hỗn hợp gần với workload production.

- **Cache lạnh:** dữ liệu chưa nằm trong buffer cache của database hoặc hệ điều hành tại thời điểm bắt đầu. Phép đo chịu ảnh hưởng nhiều hơn bởi I/O nạp dữ liệu.
- **Cache nóng:** working set đã được nạp vào cache sau một hoặc nhiều lần chạy. Phép đo thể hiện hành vi khi dữ liệu thường xuyên được truy cập.
- **Cache hỗn hợp:** một phần dữ liệu nóng, phần còn lại ít được truy cập. Đây thường là trạng thái thực tế của hệ thống có workload dài hạn.

Không mặc định lần chạy đầu là cache lạnh hoàn toàn. Database cache, OS page cache, storage cache và cache của nền tảng có thể có trạng thái khác nhau. Nếu không có cách xác nhận hoặc kiểm soát cache một cách an toàn, hãy mô tả điều kiện thực tế và tránh gắn nhãn “cold” tuyệt đối.

Không xóa cache trên production để phục vụ benchmark. Việc đó có thể gây suy giảm dịch vụ cho người dùng. Hãy dùng môi trường thử nghiệm riêng hoặc quy trình kiểm thử đã được phê duyệt. Khi đo cache nóng, chạy warm-up theo một kịch bản cố định và ghi số vòng warm-up hoặc điều kiện dừng.

## 7. Tái tạo workload và tham số

Một truy vấn đơn lẻ không đại diện cho tải thực nếu production có nhiều loại truy vấn, nhiều tham số và tỷ lệ đọc/ghi khác nhau. Bộ dữ liệu và cấu hình giống nhau nhưng workload khác có thể tạo mức tranh chấp hoàn toàn khác.

Khi chuẩn bị workload, ghi lại:

- Tập câu SQL hoặc transaction được phát.
- Tỷ lệ đọc/ghi và tỷ trọng từng loại truy vấn.
- Phân bố tham số đầu vào, gồm cả giá trị phổ biến và giá trị lệch.
- Số client, concurrency, tốc độ phát yêu cầu và thời gian think time.
- Kích thước batch, transaction boundary và cách quản lý kết nối.
- Cách client fetch kết quả: lấy toàn bộ, đọc theo trang hay stream.
- Thời gian warm-up, thời gian đo chính thức và thời gian nghỉ giữa các lượt.

Nếu dùng công cụ replay log, cần kiểm soát dữ liệu nhạy cảm, thứ tự giao dịch và các phụ thuộc thời gian. Một bản replay không giữ nguyên thứ tự có thể làm thay đổi khóa nóng, deadlock hoặc tỷ lệ cache hit. Nếu workload chứa transaction ghi, cần chuẩn bị dữ liệu và cơ chế khôi phục để mỗi lượt bắt đầu từ trạng thái có thể so sánh.

### Ví dụ: cùng SQL nhưng khác tham số

Giả sử ứng dụng thường chạy:

~~~sql
SELECT id, customer_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND created_at >= :from_time
  AND created_at < :to_time;
~~~

Nếu customer_id A có 12 đơn hàng, còn customer_id B có 1,2 triệu đơn, hai tham số tạo ra lượng dữ liệu và tính chọn lọc rất khác nhau. Đo riêng customer_id A có thể cho thấy chỉ mục hoạt động rất tốt nhưng không phản ánh trường hợp B. Nên chọn tập tham số đại diện và ghi rõ số hàng thực tế cho từng trường hợp.

Khi client dùng prepared statement, hãy ghi lại kiểu dữ liệu bind. Truyền một chuỗi thay vì số nguyên hoặc truyền timestamp với timezone khác có thể làm phát sinh chuyển kiểu, ảnh hưởng điều kiện lọc hoặc làm thay đổi kết quả.

## 8. Lập hồ sơ môi trường đo

Trước khi chạy benchmark, tạo một hồ sơ ngắn mô tả trạng thái môi trường. Hồ sơ này cho phép người khác tái hiện phép đo và giúp giải thích chênh lệch giữa các lần chạy.

Mẫu hồ sơ:

| Trường | Ví dụ nội dung cần ghi |
|---|---|
| Mã phép đo | PERF-ORDERS-2026-01 |
| Mục tiêu | So sánh hai phương án chỉ mục cho truy vấn lọc đơn hàng |
| Database | Hệ quản trị, phiên bản, build, extension |
| Schema | Migration/version, bảng, chỉ mục, phân vùng |
| Dữ liệu | Snapshot ID, thời điểm, số hàng, kích thước, phân bố chính |
| Thống kê | Thời điểm và phương pháp cập nhật thống kê |
| Cấu hình | Buffer/cache, work memory, parallelism, connection limits |
| Máy chủ | CPU/vCPU, RAM, quota, OS, container/VM |
| Storage | Loại volume, IOPS, throughput, độ trễ và vị trí file |
| Mạng/client | Máy phát tải, driver, RTT, pool kết nối |
| Workload | SQL, tham số, concurrency, tỷ lệ đọc/ghi, thời gian chạy |
| Cache | Cold/warm/mixed, cách warm-up và điều kiện bắt đầu |
| Nhiễu | Backup, vacuum, checkpoint, batch job, tải nền |
| Kết quả | Execution plan, thời gian, CPU, I/O, số hàng và lỗi |

Ví dụ cấu hình môi trường có thể được lưu dưới dạng YAML để quản lý cùng hồ sơ benchmark:

~~~yaml
measurement:
  id: PERF-ORDERS-2026-01
  purpose: compare-order-indexes
  database:
    engine: PostgreSQL
    version: "16.x"
    dataset_snapshot: orders-snapshot-2026-01-15
    statistics_updated_at: "2026-01-15T08:00:00Z"
  server:
    vcpu: 8
    memory_gb: 32
    storage: network-ssd
    provisioned_iops: 12000
  workload:
    clients: 32
    read_write_ratio: "95:5"
    warmup_seconds: 120
    measure_seconds: 600
  cache_state: warm
~~~

Các giá trị trong ví dụ chỉ minh họa cách ghi hồ sơ, không phải cấu hình khuyến nghị. Không sao chép chúng sang môi trường thật mà chưa đánh giá tải, giới hạn và yêu cầu vận hành.

## 9. Thu thập thông tin phiên bản và cấu hình

Có thể bắt đầu bằng các truy vấn chỉ đọc để ghi nhận một phần thông tin từ hệ quản trị. Tên biến và quyền truy cập khác nhau theo phiên bản; hãy xác nhận với tài liệu của hệ quản trị đang sử dụng.

### PostgreSQL

~~~sql
SELECT version();

SHOW shared_buffers;
SHOW work_mem;
SHOW effective_cache_size;
SHOW max_connections;
SHOW random_page_cost;
~~~

version() cho biết phiên bản/build; các lệnh SHOW ghi lại một số cấu hình quan trọng. Cần bổ sung thông tin hệ điều hành, RAM, CPU, storage và trạng thái workload từ công cụ giám sát bên ngoài.

### MySQL

~~~sql
SELECT VERSION();

SHOW VARIABLES
WHERE Variable_name IN (
    'innodb_buffer_pool_size',
    'tmp_table_size',
    'max_heap_table_size',
    'max_connections',
    'innodb_flush_log_at_trx_commit'
);
~~~

Các biến trên giúp ghi nhận phiên bản, bộ nhớ buffer pool, giới hạn bảng tạm, kết nối và một thiết lập liên quan đến flush log. Không thay đổi chính sách durability chỉ để cải thiện benchmark; kết quả phải phản ánh yêu cầu an toàn dữ liệu của hệ thống.

### SQL Server

~~~sql
SELECT @@VERSION AS version_info;

SELECT
    name,
    value,
    value_in_use,
    is_dynamic,
    is_advanced
FROM sys.configurations
WHERE name IN (
    'max server memory (MB)',
    'min server memory (MB)',
    'max degree of parallelism',
    'cost threshold for parallelism',
    'max worker threads'
);
~~~

@@VERSION cung cấp thông tin phiên bản; sys.configurations cho biết giá trị cấu hình và giá trị đang có hiệu lực. Một số thiết lập có phạm vi instance, database hoặc session; cần ghi đúng phạm vi khi lập hồ sơ.

Các truy vấn trên không thay thế việc ghi nhận cấu hình của ứng dụng, driver, hệ điều hành, máy ảo, container, mạng và storage. Một hồ sơ đầy đủ phải kết hợp dữ liệu từ database với số liệu giám sát hạ tầng.

## 10. Quy trình kiểm soát trước, trong và sau phép đo

### Trước khi đo

1. Xác định giả thuyết và biến duy nhất sẽ thay đổi trong lượt thử nghiệm.
2. Chọn snapshot dữ liệu, xác nhận số hàng, kích thước và phân bố đại diện.
3. Xác nhận schema, chỉ mục, phân vùng và thống kê ở trạng thái đã định.
4. Ghi phiên bản database, extension, driver, ứng dụng và công cụ benchmark.
5. Chụp cấu hình bộ nhớ, parallelism, kết nối, giao dịch và các thiết lập liên quan.
6. Ghi tài nguyên CPU, RAM, storage, mạng và giới hạn container/VM.
7. Xác định trạng thái cache và quy trình warm-up.
8. Xác nhận workload, tham số, concurrency và cách fetch kết quả.
9. Kiểm tra tác vụ nền và tải đồng thời; ghi lại những yếu tố không thể loại bỏ.

### Trong khi đo

1. Dùng cùng kịch bản, cùng dữ liệu và cùng cách phát tải cho các phương án.
2. Theo dõi CPU, RAM, I/O, network, connection count và các wait event.
3. Ghi lại thời điểm bắt đầu/kết thúc, lỗi, timeout và thay đổi tải nền.
4. Thu thập execution plan và số hàng thực tế khi công cụ cho phép.
5. Phân biệt thời gian phía server với thời gian end-to-end ở client.
6. Lặp lại đủ số lượt để nhận biết độ biến động; không chỉ chọn lượt chạy nhanh nhất.

### Sau khi đo

1. Chụp lại cấu hình và trạng thái tài nguyên để phát hiện thay đổi ngoài dự kiến.
2. Xác nhận snapshot, schema và số hàng vẫn phù hợp với điều kiện ban đầu.
3. So sánh các chỉ số theo cùng cách tính: p50/p95/p99, throughput, CPU, I/O, logical reads, physical reads, temp usage và số hàng trả về.
4. Kiểm tra kế hoạch thực thi có thay đổi hay không và xác định nguyên nhân.
5. Ghi lại mọi sai lệch môi trường hoặc lượt đo bị loại cùng lý do.
6. Khôi phục môi trường thử nghiệm về trạng thái chuẩn trước lượt tiếp theo nếu workload đã làm thay đổi dữ liệu.

## 11. Cách diễn giải khi môi trường không hoàn toàn giống nhau

Trong thực tế, đôi khi không thể giữ mọi yếu tố giống hệt. Có thể database phiên bản mới chạy trên máy chủ mới, hoặc workload production không thể sao chép nguyên vẹn. Khi đó, cần phân loại khác biệt và giới hạn kết luận.

| Khác biệt | Rủi ro với kết luận | Cách xử lý |
|---|---|---|
| Số hàng hoặc phân bố khác | Kế hoạch và số trang truy cập thay đổi | Dùng snapshot tương đương hoặc chuẩn hóa workload theo nhóm dữ liệu |
| Thống kê khác | Bộ tối ưu chọn kế hoạch khác | Ghi thời điểm cập nhật và so sánh ước lượng/thực tế |
| Phiên bản khác | Thuật toán, mặc định và plan cache thay đổi | Ghi build, cấu hình mặc định và kế hoạch từng phiên bản |
| RAM/cache khác | Tỷ lệ cache hit và spill thay đổi | Đo cả trạng thái cache và giới hạn bộ nhớ |
| Storage khác | Độ trễ I/O và throughput thay đổi | Ghi loại volume, IOPS, throughput và latency |
| Concurrency khác | Tranh chấp CPU, khóa và I/O thay đổi | Dùng cùng workload hoặc phân tích riêng theo mức tải |
| Client/network khác | Thời gian end-to-end thay đổi | Tách thời gian server, network và xử lý kết quả |
| Tác vụ nền khác | Nhiễu làm thời gian dao động | Ghi nhận tải nền, lặp lại phép đo và báo rõ giới hạn |

Nếu thay đổi đồng thời nhiều yếu tố, không thể khẳng định chênh lệch thời gian chỉ do câu SQL hoặc chỉ mục. Hãy mô tả kết quả là so sánh giữa hai cấu hình môi trường tổng thể. Khi cần xác định nguyên nhân, thiết kế thêm phép thử cô lập từng yếu tố.

## 12. Ví dụ thực tế: kết quả benchmark bị lệch do dữ liệu và tài nguyên

Một nhóm kỹ thuật muốn đánh giá chỉ mục mới cho truy vấn tìm đơn hàng theo trạng thái và ngày tạo. Lượt đo ban đầu chạy trên máy phát triển với 2 triệu đơn hàng, 4 vCPU, 16 GB RAM và SSD local. Sau khi triển khai lên môi trường staging, nhóm thấy truy vấn chậm hơn dù đã tạo cùng chỉ mục.

Kiểm tra hồ sơ môi trường cho thấy:

- Staging có 40 triệu đơn hàng và dữ liệu cũ chiếm phần lớn dung lượng.
- Trạng thái COMPLETED chiếm 85% dữ liệu, trong khi bộ dữ liệu phát triển phân bố gần đều.
- Staging chỉ có 8 GB RAM dành cho máy ảo và buffer cache nhỏ hơn.
- Storage mạng bị giới hạn IOPS, đồng thời có backup chạy trong một phần thời gian đo.
- Thống kê ở staging được cập nhật sau một đợt nạp dữ liệu lớn, còn máy phát triển dùng thống kê cũ hơn.

Kết quả ở hai môi trường không thể được dùng để kết luận chỉ mục mới tốt hoặc xấu. Dữ liệu, cache, storage và tác vụ nền đều khác nhau. Nhóm cần tạo snapshot đại diện, xác định thống kê chuẩn, tắt hoặc lên lịch backup ngoài cửa sổ đo nếu được phép, rồi chạy cùng workload trên môi trường có tài nguyên được ghi nhận.

Sau khi kiểm soát các yếu tố, nhóm nên đo nhiều nhóm tham số: trạng thái hiếm và phổ biến, khoảng thời gian ngắn và dài, cache nóng và trạng thái hỗn hợp. Execution plan sẽ cho biết chỉ mục được dùng như thế nào; các chỉ số đọc và I/O giúp giải thích chi phí; p95 và throughput cho biết tác động trong tải đồng thời.

Ví dụ này cho thấy việc kiểm soát môi trường không phải thủ tục hành chính. Nó giúp tránh quy nhầm nguyên nhân và ngăn quyết định tối ưu dựa trên một benchmark không đại diện.

## 13. Các lỗi thường gặp

- **Chỉ ghi số hàng:** bỏ qua skew, cardinality, độ rộng hàng và tương quan giữa cột.
- **Dùng dữ liệu tổng hợp quá đều:** không tái tạo hot key, giá trị hiếm và phân bố theo thời gian.
- **Đo trên hai snapshot khác nhau:** số hàng và dữ liệu thay đổi giữa các lượt.
- **Không kiểm tra thống kê:** bộ tối ưu có thể dùng ước lượng cũ hoặc khác nhau.
- **Bỏ qua phiên bản phụ và driver:** thay đổi nhỏ cũng có thể ảnh hưởng engine, giao thức hoặc plan cache.
- **Chỉ nhìn RAM của host:** bỏ qua quota container, giới hạn VM và memory pressure.
- **Coi mọi SSD là tương đương:** bỏ qua IOPS, throughput, latency, burst và storage dùng chung.
- **Không đo máy phát tải:** client có thể trở thành nút thắt mà ta lại đổ lỗi cho database.
- **Không kiểm soát cache:** so sánh một lượt lạnh với một lượt nóng.
- **Để tác vụ nền chạy không ghi nhận:** backup, vacuum, checkpoint hoặc batch job làm sai lệch kết quả.
- **Thay nhiều yếu tố cùng lúc:** không xác định được nguyên nhân của cải thiện hoặc suy giảm.
- **Chọn kết quả tốt nhất:** bỏ qua biến động và độ tin cậy của phép đo.
- **Bỏ qua tính đúng đắn:** dữ liệu khác hoặc truy vấn thay đổi ngữ nghĩa có thể tạo kết quả nhanh nhưng không tương đương.

## 14. Checklist kiểm soát môi trường đo

- [ ] Đã xác định mục tiêu, giả thuyết và biến sẽ thay đổi.
- [ ] Đã ghi snapshot dữ liệu, số hàng, kích thước và phân bố quan trọng.
- [ ] Đã xác nhận schema, chỉ mục, phân vùng và thống kê.
- [ ] Đã ghi phiên bản/build database, extension, OS, driver và ứng dụng.
- [ ] Đã ghi cấu hình bộ nhớ, cache, parallelism, kết nối và giao dịch.
- [ ] Đã ghi CPU, RAM, quota, storage, IOPS, throughput và độ trễ.
- [ ] Đã ghi mạng, vị trí máy phát tải và cấu hình connection pool.
- [ ] Đã cố định workload, tham số, concurrency và cách fetch kết quả.
- [ ] Đã mô tả trạng thái cache và quy trình warm-up.
- [ ] Đã ghi tác vụ nền và tải đồng thời trong cửa sổ đo.
- [ ] Đã lưu execution plan, số liệu tài nguyên và kết quả từng lượt.
- [ ] Đã xác nhận môi trường sau đo và giải thích mọi sai lệch.

## Kết luận

Kiểm soát dữ liệu, cấu hình, phiên bản và tài nguyên giúp biến một lần chạy thử thành phép đo có thể giải thích và tái lập. Dữ liệu cần đại diện cả quy mô lẫn phân bố; cấu hình cần được ghi ở đúng phạm vi; phiên bản phải đủ chi tiết để nhận diện thay đổi của engine và client; tài nguyên phải bao gồm database, storage, mạng và máy phát tải.

Khi các điều kiện này được ghi nhận và giữ ổn định, ta có thể đánh giá một thay đổi SQL, chỉ mục hoặc cấu hình bằng bằng chứng đáng tin cậy. Nếu môi trường buộc phải khác nhau, hãy công khai khác biệt và giới hạn kết luận. Đó là cách tránh nhầm lẫn giữa cải thiện thực sự và biến động do môi trường đo.

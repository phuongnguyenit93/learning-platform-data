# Phân tích sự kiện chờ (wait events) và chuỗi phiên chặn nhau

## Mục tiêu bài học

Khi người dùng phản ánh cơ sở dữ liệu chậm, thời gian phản hồi tăng không nhất thiết do câu SQL thực hiện nhiều phép tính. Một phiên có thể đang chờ đọc dữ liệu từ đĩa, chờ ghi nhật ký giao dịch, chờ khóa do phiên khác giữ, hoặc chờ ứng dụng nhận kết quả. Nếu chỉ xem câu SQL và thời gian chạy tổng thể, ta dễ tối ưu nhầm thành phần.

Trong chương **Quan sát hệ thống** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn cách đọc sự kiện chờ (wait events), phân biệt chờ tài nguyên với thời gian thực thi, dựng chuỗi phiên chặn nhau và tìm phiên giữ khóa ở gốc. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; vì vậy mọi kết luận trong bài cần được xác nhận bằng số liệu quan sát được và phép đo trước/sau điều chỉnh.

Sau bài học, bạn có thể:

- Giải thích wait event cho biết điều gì và vì sao một mẫu chờ đơn lẻ chưa đủ kết luận nguyên nhân.
- Phân nhóm các sự kiện chờ thường gặp liên quan đến khóa, I/O, bộ nhớ, đồng bộ nội bộ, nhật ký và ứng dụng.
- Phân biệt phiên đang chờ, phiên đang giữ tài nguyên và phiên chặn gốc.
- Đọc chuỗi blocking/waiting, xác định phạm vi ảnh hưởng và thu thập bằng chứng trước khi xử lý.
- Kiểm chứng tác động của thay đổi bằng độ trễ, thời gian chờ, thông lượng và mức sử dụng tài nguyên.

## 1. Wait event là gì?

Một phiên kết nối (session) gửi yêu cầu tới hệ quản trị cơ sở dữ liệu. Trong quá trình xử lý, phiên có thể thực thi trên CPU hoặc tạm dừng để chờ một điều kiện hay tài nguyên. **Wait event** là thông tin hệ quản trị ghi nhận về nguyên nhân một tác vụ đang chờ tại một thời điểm hoặc trong một khoảng đo, tùy cơ chế quan sát của sản phẩm.

Ví dụ:

- Một truy vấn cần đọc trang dữ liệu chưa có trong bộ nhớ đệm và phải đợi I/O hoàn tất.
- Một giao dịch muốn cập nhật dòng đang bị giao dịch khác khóa.
- Một phiên cần ghi log commit xuống thiết bị lưu trữ trước khi xác nhận giao dịch.
- Một truy vấn sắp xếp hoặc nối dữ liệu cần cấp phát bộ nhớ, hoặc phải ghi dữ liệu tạm khi không đủ bộ nhớ.
- Cơ sở dữ liệu đã tạo kết quả nhưng đang chờ ứng dụng đọc hết dữ liệu qua kết nối.

Wait event giúp trả lời câu hỏi **phiên đang chờ điều gì**. Nó không tự động trả lời câu hỏi **vì sao hệ thống chậm**. Chẳng hạn, chờ I/O có thể do thiết bị lưu trữ chậm, truy vấn đọc quá nhiều trang, cache không hiệu quả, hoặc một lần quét toàn bảng vốn không cần thiết. Chờ khóa có thể do giao dịch giữ khóa quá lâu, truy cập dữ liệu theo thứ tự không nhất quán, hoặc nhiều yêu cầu cùng cập nhật một dòng nóng.

### 1.1. Ba trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Hướng quan sát |
|---|---|---|
| Đang chạy (running/on CPU) | Phiên đang được lập lịch thực thi hoặc sử dụng CPU | CPU, kế hoạch thực thi, số dòng xử lý, phép tính và mức cạnh tranh CPU |
| Đang chờ (waiting) | Phiên tạm dừng để đợi một sự kiện hoặc tài nguyên | Loại wait, thời gian chờ, tài nguyên liên quan và phiên sở hữu tài nguyên nếu có |
| Nhàn rỗi (idle) | Phiên không có công việc cần thực thi tại thời điểm quan sát | Xác định phiên đang chờ ứng dụng, đang giữ transaction mở hay chỉ là kết nối pool bình thường |

Một truy vấn tốn CPU có thể không xuất hiện như một wait event cụ thể. Vì thế, không thấy wait event không đồng nghĩa truy vấn nhanh hoặc cơ sở dữ liệu không có vấn đề. Cần kết hợp thống kê CPU của hệ điều hành, mức sử dụng CPU của tiến trình cơ sở dữ liệu, số phiên runnable, thời gian CPU của câu lệnh và độ trễ đầu cuối.

### 1.2. Wait event hiện thời và thống kê tích lũy

Hai kiểu dữ liệu quan sát thường gặp:

- **Ảnh chụp hiện thời:** cho biết phiên đang chờ gì ngay lúc truy vấn trạng thái được lấy. Nó hữu ích để tìm sự cố đang diễn ra, nhưng một ảnh chụp có thể bỏ lỡ sự kiện ngắn hoặc ghi nhận một trạng thái thoáng qua.
- **Thống kê tích lũy hoặc theo khoảng thời gian:** tổng hợp số lần chờ, tổng thời gian chờ hoặc thời gian trung bình kể từ thời điểm bắt đầu thống kê hay lần reset. Nó giúp tìm nhóm sự kiện tiêu tốn thời gian lớn, nhưng có thể che khuất thay đổi gần đây nếu khoảng tích lũy quá dài.

Khi đọc thống kê tích lũy, cần biết thời điểm reset, thời gian uptime và khoảng lấy mẫu. Nên so sánh chênh lệch giữa hai lần lấy mẫu trong một khoảng xác định thay vì mặc định tổng thời gian lớn nhất là vấn đề hiện tại. Nếu hệ thống có nhiều phiên chờ đồng thời, tổng thời gian chờ cộng dồn của các phiên có thể lớn hơn thời gian đồng hồ thực tế.

## 2. Các nhóm wait event thường gặp

Tên wait event và cách nhóm khác nhau giữa PostgreSQL, MySQL, SQL Server, Oracle và các hệ quản trị khác. Hãy dùng tài liệu đúng phiên bản và hiểu ngữ nghĩa của từng event trước khi so sánh. Các nhóm dưới đây là cách phân loại theo bản chất vấn đề.

### 2.1. Chờ khóa giao dịch (lock waits)

Phiên cần đọc hoặc thay đổi dữ liệu nhưng phải chờ một giao dịch khác nhả khóa xung đột. Ví dụ, phiên A cập nhật một dòng trong bảng `inventory` nhưng chưa commit; phiên B muốn cập nhật cùng dòng sẽ phải chờ tùy mức cô lập và cơ chế khóa.

Các dấu hiệu cần kiểm tra:

- Phiên chờ có đang chờ loại khóa nào, trên bảng, dòng, trang hay tài nguyên nào?
- Phiên nào đang giữ khóa và giao dịch đó bắt đầu từ khi nào?
- Phiên giữ khóa còn thực thi SQL, đang chờ ứng dụng, hay đã ở trạng thái nhàn rỗi nhưng transaction chưa kết thúc?
- Có nhiều phiên cùng chờ một phiên, tạo thành một nhánh chặn lớn hay không?

Lock wait thường là dấu hiệu trực tiếp của blocking. Tuy nhiên, phiên chặn có thể không phải câu SQL tiêu tốn CPU nhiều nhất. Một phiên mở transaction, cập nhật xong rồi chờ người dùng hoặc dịch vụ khác có thể giữ khóa trong thời gian dài và làm nhiều phiên phía sau bị dồn lại.

### 2.2. Chờ I/O dữ liệu và I/O log

Nhóm này liên quan đến đọc hoặc ghi dữ liệu trên thiết bị lưu trữ:

- **Đọc trang dữ liệu:** truy vấn cần trang chưa có trong cache, phải chờ đọc từ file dữ liệu.
- **Ghi trang hoặc checkpoint:** hệ quản trị ghi các trang đã thay đổi xuống lưu trữ theo cơ chế của engine.
- **Ghi log/redo/WAL:** giao dịch phải đợi log được ghi bền vững theo cam kết commit.
- **Đọc/ghi vùng tạm:** thao tác sort, hash join hoặc materialization vượt khả năng giữ trong bộ nhớ và phát sinh I/O tạm.

Không nên kết luận thiết bị lưu trữ chậm chỉ vì thấy nhiều wait I/O. Cần xem thêm độ trễ từng thao tác, IOPS, throughput, độ sâu hàng đợi, tỷ lệ cache hit, số trang đọc/ghi và phân bố tải giữa các file hoặc thiết bị. Một truy vấn quét lượng dữ liệu lớn có thể tạo ra thời gian chờ I/O cao dù thiết bị vẫn đáp ứng đúng năng lực.

Chờ ghi log khi commit cũng khác với chờ đọc dữ liệu. Nếu thời gian xác nhận giao dịch tăng do flush log, hãy xem độ trễ thiết bị log, lượng log sinh ra, tần suất commit, cấu hình đồng bộ và cơ chế xác nhận từ replica nếu đang dùng sao chép đồng bộ.

### 2.3. Chờ latch, lightweight lock và đồng bộ nội bộ

Hệ quản trị dùng các cơ chế đồng bộ nội bộ để bảo vệ cấu trúc bộ nhớ, trang đệm, metadata hoặc hàng đợi. Một số sản phẩm gọi các cơ chế này là latch, lightweight lock, mutex hoặc spinlock; chúng khác với khóa giao dịch mà ứng dụng dùng để bảo vệ dữ liệu nghiệp vụ.

Chờ đồng bộ nội bộ có thể tăng khi nhiều phiên tranh chấp cùng một trang, cấu trúc metadata, bộ đếm hoặc tài nguyên dùng chung. Một event ngắn xuất hiện thường xuyên chưa chắc đáng lo; cần xem tổng thời gian, tỷ lệ trên tổng thời gian xử lý, mức đồng thời và tài nguyên cụ thể. Nếu nhiều phiên cùng đụng vào một trang nóng, có thể cần xem lại cách phân bố khóa, thiết kế chỉ mục, thứ tự ghi hoặc cách chia tải.

### 2.4. Chờ bộ nhớ, sort/hash và dữ liệu tạm

Truy vấn cần bộ nhớ để sắp xếp, hash join, hash aggregate hoặc giữ các tập kết quả trung gian. Khi bộ nhớ cấp phát không đủ hoặc bị giới hạn, hệ quản trị có thể chia thao tác thành nhiều lượt và ghi dữ liệu tạm xuống đĩa. Kết quả có thể xuất hiện dưới dạng wait I/O tạm, chờ cấp phát bộ nhớ hoặc sự kiện riêng của engine.

Hãy kiểm tra kích thước đầu vào, số dòng ước lượng so với thực tế, độ rộng dòng, số nhóm, kiểu nối và dấu hiệu spill. Tăng bộ nhớ cấu hình có thể giúp một số truy vấn nhưng cũng làm tăng nguy cơ tổng mức cấp phát vượt RAM khi nhiều truy vấn lớn chạy đồng thời. Cần đánh giá cả bộ nhớ mỗi truy vấn lẫn mức đồng thời toàn hệ thống.

### 2.5. Chờ mạng và phía ứng dụng

Một số event phản ánh cơ sở dữ liệu đang chờ dữ liệu từ client hoặc chờ client nhận kết quả. Ví dụ, ứng dụng đọc kết quả chậm, mạng có độ trễ cao, hoặc truy vấn trả về quá nhiều dòng. Trong PostgreSQL, trạng thái chờ client như `ClientRead` hoặc `ClientWrite` có thể giúp nhận diện tình huống này; tên cụ thể tùy hệ quản trị.

Không nên quy mọi thời gian chờ client thành lỗi mạng. Hãy kiểm tra kích thước kết quả, tốc độ ứng dụng tiêu thụ dữ liệu, số round trip, thời gian xử lý ở tầng ứng dụng, connection pool và độ trễ mạng. Một phiên đang chờ client nhưng vẫn giữ transaction mở có thể tiếp tục giữ khóa hoặc giữ snapshot lâu, gây ảnh hưởng đến các phiên khác.

### 2.6. Chờ replication và các tài nguyên khác

Kiến trúc có replica hoặc cơ chế đồng bộ có thể phát sinh chờ xác nhận từ replica, chờ gửi log, chờ apply dữ liệu hoặc chờ tài nguyên điều phối. Cần đối chiếu event với replication lag, trạng thái replica, thông lượng truyền, thời gian apply và yêu cầu nhất quán.

Ngoài ra còn có các sự kiện liên quan đến scheduler, worker, parallel query, metadata, backup và maintenance. Hãy phân loại theo tài liệu của engine. Đừng gom tất cả event có chữ `wait` thành một loại nguyên nhân duy nhất.

## 3. Blocking và blocking chain

### 3.1. Phiên chờ và phiên chặn

Trong tình huống khóa xung đột, phiên **blocked** là phiên đang phải chờ. Phiên **blocker** là phiên đang giữ tài nguyên khiến phiên kia chưa thể tiếp tục. Quan hệ này có hướng: phiên chờ phụ thuộc vào phiên chặn.

Ví dụ:

```text
Session 101: BEGIN; UPDATE inventory ...;  (giữ khóa, chưa COMMIT)
       |
       +---- chặn ----> Session 202: UPDATE inventory ...; (đang chờ)
```

Nếu Session 101 tiếp tục giữ khóa, Session 202 không thể hoàn thành phần cập nhật xung đột. Khi Session 101 commit hoặc rollback, khóa được giải phóng và Session 202 có thể tiếp tục nếu không còn blocker khác.

### 3.2. Chuỗi chặn nhiều tầng

Blocking chain xuất hiện khi một phiên đang chờ lại đang giữ tài nguyên mà phiên khác cần. Ví dụ:

```text
Session 101                 Session 202                 Session 303
Giữ khóa A                  Giữ khóa B                  Chờ khóa B
     ^                           |
     |                           +---- chặn -----------> Session 303
     +------ chặn ---------------+
             Session 202 chờ khóa A
```

Diễn giải theo quan hệ phụ thuộc:

- Session 202 đang chờ Session 101 nhả khóa A.
- Trong lúc chờ, Session 202 vẫn giữ khóa B.
- Session 303 cần khóa B nên bị Session 202 chặn.
- Session 101 là root blocker trong chuỗi quan sát được vì nó đang giữ khóa nhưng không bị một phiên khác chặn trong chuỗi đó.

Root blocker là điểm cần điều tra đầu tiên vì giải phóng được phiên này có thể làm nhiều phiên phía sau tiếp tục. Root blocker không nhất thiết là phiên chạy lâu nhất hoặc dùng CPU nhiều nhất. Nó có thể ở trạng thái `idle in transaction`, nghĩa là câu lệnh gần nhất đã kết thúc nhưng transaction vẫn mở.

### 3.3. Blocking chain khác deadlock

Blocking chain là quan hệ chờ có thể được giải quyết khi blocker hoàn tất hoặc nhả tài nguyên. Deadlock xảy ra khi các giao dịch tạo thành vòng phụ thuộc, ví dụ A giữ tài nguyên 1 và chờ tài nguyên 2, trong khi B giữ tài nguyên 2 và chờ tài nguyên 1. Hệ quản trị thường phát hiện vòng chờ và hủy một giao dịch để phá deadlock.

Một ảnh chụp blocking chain không đủ để khẳng định có deadlock. Cần xem log deadlock hoặc công cụ chẩn đoán của hệ quản trị, thứ tự truy cập tài nguyên và các giao dịch liên quan. Deadlock thường cần điều chỉnh thứ tự truy cập, phạm vi transaction hoặc cách chia lô; còn blocking kéo dài thường cần tìm phiên giữ tài nguyên quá lâu.

## 4. Quy trình phân tích wait event và chuỗi phiên chặn

### Bước 1 — Xác định thời điểm và phạm vi sự cố

Ghi lại thời điểm bắt đầu, thời điểm kết thúc, nhóm người dùng bị ảnh hưởng, endpoint hoặc tác vụ gặp vấn đề, và thay đổi tải gần thời điểm đó. Đối chiếu với biểu đồ độ trễ p50/p95/p99, thông lượng, lỗi, timeout và số kết nối. Nếu chỉ một truy vấn bị chậm, phạm vi điều tra khác với trường hợp toàn bộ giao dịch cùng tăng độ trễ.

### Bước 2 — Lấy mẫu wait event theo khoảng thời gian

Thu thập các phiên đang hoạt động, trạng thái, loại wait, event, thời gian bắt đầu truy vấn, transaction start, câu SQL, người dùng, ứng dụng và host nếu có. Lặp lại nhiều lần trong khoảng ngắn phù hợp với sự cố. Một mẫu duy nhất có thể bỏ lỡ blocker đã kết thúc hoặc nhầm một wait rất ngắn thành nguyên nhân chính.

Với thống kê tích lũy, lưu số liệu ở hai mốc để tính mức tăng theo khoảng thời gian. Không reset thống kê toàn hệ thống chỉ để phục vụ một lần kiểm tra nếu chưa đánh giá tác động và quy trình vận hành.

### Bước 3 — Phân loại sự kiện và tìm nhóm chiếm thời gian

Nhóm event theo lock, I/O, log, đồng bộ nội bộ, bộ nhớ, client/network, replication và scheduler theo cách phân loại của engine. Đánh giá số lần chờ, tổng thời gian, thời gian trung bình, số phiên đồng thời và mối tương quan với độ trễ người dùng.

Không chỉ xếp hạng theo tổng thời gian. Một event có tổng thời gian lớn có thể là hoạt động nền bình thường; một lock wait chỉ xảy ra trong vài phút cao điểm lại có thể trực tiếp làm giao dịch thanh toán timeout. Luôn liên hệ event với nhóm workload và mục tiêu dịch vụ.

### Bước 4 — Dựng các cạnh blocked-by

Với mỗi phiên đang chờ khóa, xác định phiên giữ khóa trực tiếp. Ghi lại quan hệ `blocked_session -> blocker_session`, tài nguyên bị tranh chấp và thời điểm quan sát. Từ mỗi blocker, kiểm tra xem chính nó có đang chờ một phiên khác hay không. Lặp lại cho tới khi gặp phiên không bị chặn trong chuỗi quan sát, hoặc phát hiện vòng chờ.

Nên dựng đồ thị hoặc bảng có các cột: waiter, blocker, wait type, resource, wait age, transaction age, SQL hiện tại/gần nhất và application. Nếu một blocker có nhiều waiter, đánh dấu số phiên phía sau để đánh giá phạm vi ảnh hưởng.

### Bước 5 — Điều tra root blocker và câu lệnh liên quan

Thu thập transaction start, trạng thái phiên, câu SQL hiện tại hoặc câu SQL gần nhất, thời gian giữ transaction, ứng dụng/host, loại khóa và kế hoạch thực thi nếu có. Đặc biệt chú ý:

- Phiên có mở transaction nhưng quên commit/rollback không?
- Ứng dụng có gọi API, chờ nhập liệu hoặc xử lý lâu khi transaction vẫn mở không?
- Cùng một dòng hoặc khóa có bị nhiều yêu cầu cập nhật liên tục không?
- Các giao dịch có lấy khóa theo thứ tự khác nhau không?
- Câu SQL có quét quá nhiều dòng hoặc giữ khóa lâu vì thiếu chỉ mục phù hợp không?
- Có batch job, migration, báo cáo hoặc maintenance trùng thời điểm với sự cố không?

Nếu blocker ở trạng thái nhàn rỗi nhưng transaction vẫn mở, cần tìm nguyên nhân ở luồng điều khiển ứng dụng và quản lý transaction. Nếu blocker đang chạy SQL, phân tích kế hoạch thực thi và lượng dữ liệu cần xử lý.

### Bước 6 — Chọn xử lý theo nguyên nhân

Các hướng xử lý có thể gồm rút ngắn transaction, bảo đảm mọi nhánh code đều commit/rollback, giảm thời gian chờ bên ngoài khi đang giữ transaction, chuẩn hóa thứ tự cập nhật nhiều tài nguyên, thêm hoặc điều chỉnh chỉ mục sau khi xem kế hoạch, chia batch thành các phần nhỏ, giảm truy cập đồng thời vào dòng nóng, hoặc tách workload phân tích khỏi đường giao dịch.

Chấm dứt một phiên blocker có thể giải phóng chuỗi chờ, nhưng thao tác hủy phiên thường dẫn đến rollback, tạo thêm I/O và có thể ảnh hưởng nghiệp vụ. Chỉ thực hiện theo quy trình vận hành đã được phê duyệt, sau khi xác nhận đúng phiên, tác động rollback và chủ sở hữu workload. Không tự động kill phiên chỉ vì transaction age lớn hoặc wait time cao.

### Bước 7 — Kiểm chứng sau điều chỉnh

Chạy lại kịch bản có cùng dữ liệu, mức đồng thời và khoảng thời gian tương đương. So sánh:

- p95/p99 và tỷ lệ timeout của giao dịch bị ảnh hưởng;
- số lần lock wait, tổng thời gian chờ và độ dài blocking chain;
- số giao dịch/giây hoặc truy vấn/giây;
- CPU, bộ nhớ, I/O dữ liệu, I/O log và dữ liệu tạm;
- số deadlock và lỗi giao dịch;
- tác động tới workload khác và độ trễ ứng dụng.

Một thay đổi chỉ được xem là hiệu quả khi giảm được triệu chứng mục tiêu mà không tạo ra điểm nghẽn nghiêm trọng ở thành phần khác.

## 5. Ví dụ truy vấn quan sát trên PostgreSQL

PostgreSQL cung cấp `pg_stat_activity` để xem trạng thái phiên và wait event, cùng hàm `pg_blocking_pids(pid)` để lấy PID đang chặn một phiên. Truy vấn dưới đây liệt kê các quan hệ chặn trực tiếp tại thời điểm chạy:

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocker.pid AS blocker_pid,
    blocked.usename AS blocked_user,
    blocker.usename AS blocker_user,
    blocked.application_name AS blocked_application,
    blocker.application_name AS blocker_application,
    blocked.wait_event_type,
    blocked.wait_event,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    blocked.state AS blocked_state,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    blocker.state AS blocker_state,
    blocked.query AS blocked_sql,
    blocker.query AS blocker_current_or_last_sql
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid
WHERE blocked.pid <> pg_backend_pid()
ORDER BY blocker.xact_start NULLS LAST, blocked.query_start;
```

Lưu ý khi đọc kết quả:

- `blocked_query_age` là tuổi của câu truy vấn tính từ `query_start`, không phải bộ đếm chính xác thời gian lock wait. `pg_stat_activity` phản ánh wait event hiện thời; muốn biết diễn biến cần lấy mẫu lặp lại hoặc dùng hệ thống giám sát lịch sử.
- `blocker_xact_age` cho biết transaction của blocker đã mở bao lâu nếu có `xact_start`. Transaction lâu không tự động là lỗi, nhưng là tín hiệu cần kiểm tra khi nó đang giữ khóa.
- Nếu blocker ở trạng thái `idle in transaction`, cột SQL có thể là câu lệnh gần nhất chứ không phải một câu đang chạy. Cần xem ứng dụng và luồng transaction để tìm lý do chưa kết thúc.
- Truy vấn thể hiện quan hệ chặn trực tiếp. Nếu blocker cũng đang bị chặn, hãy tìm PID đó trong cột `blocked_pid` để lần tiếp chuỗi về phía root blocker.
- PID có thể biến mất hoặc thay đổi giữa hai lần lấy mẫu khi phiên kết thúc. Kết quả là ảnh chụp tại thời điểm chạy, không phải lịch sử đầy đủ.

Để xem các phiên đang hoạt động và wait event mà không chỉ giới hạn ở lock wait:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    xact_start,
    query
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND state IS DISTINCT FROM 'idle'
ORDER BY query_start NULLS LAST;
```

Các truy vấn trên yêu cầu quyền đọc các thông tin thống kê phiên phù hợp. Quyền xem nội dung SQL và phiên của người dùng khác phụ thuộc cấu hình quyền PostgreSQL. Trong môi trường thật, giới hạn quyền truy cập kết quả vì câu SQL có thể chứa dữ liệu nhạy cảm hoặc thông tin nghiệp vụ.

## 6. Ví dụ quan sát trên MySQL

Trên MySQL có `sys` schema, view `sys.innodb_lock_waits` có thể giúp xem quan hệ chờ khóa InnoDB cùng phiên chặn trực tiếp:

```sql
SELECT
    waiting_pid,
    blocking_pid,
    wait_age,
    locked_table,
    locked_index,
    waiting_query,
    blocking_query
FROM sys.innodb_lock_waits
ORDER BY wait_age_secs DESC;
```

View và cột khả dụng tùy phiên bản MySQL và cấu hình Performance Schema. Nếu không có view này, có thể truy vấn các bảng `performance_schema.data_lock_waits`, `performance_schema.data_locks` và thông tin thread tương ứng theo tài liệu của phiên bản đang chạy. Hãy xác minh tên cột và quyền đọc trước khi đưa truy vấn vào runbook vận hành.

Kết quả cho biết waiter, blocker và đối tượng khóa trực tiếp. Để tìm root blocker, tiếp tục kiểm tra xem `blocking_pid` có xuất hiện như một `waiting_pid` ở quan hệ khác không. Nếu có, lần theo tiếp cho đến phiên không bị chặn trong ảnh chụp hiện tại. Kết hợp với transaction age và câu lệnh đang chạy/gần nhất để xác định vì sao khóa chưa được nhả.

## 7. Tình huống thực tế: một phiên chặn nhiều giao dịch

Giả sử hệ thống bán hàng có ba nhóm phiên:

| Phiên | Công việc | Trạng thái quan sát |
|---|---|---|
| 410 | Cập nhật tồn kho trong transaction | `idle in transaction`, đang giữ khóa dòng |
| 522 | Xác nhận đơn hàng | Chờ khóa do phiên 410 giữ |
| 638 | Cập nhật trạng thái giao hàng | Chờ khóa do phiên 522 giữ |
| 701 | Truy vấn báo cáo | Đang chạy, đọc nhiều dữ liệu nhưng không nằm trong chuỗi khóa này |

Phiên 410 có thể là root blocker. Phiên 522 vừa chờ phiên 410 vừa giữ một khóa khác mà phiên 638 cần. Nếu chỉ nhìn phiên 638, có thể tưởng rằng phiên 522 là nguyên nhân cuối cùng. Lần theo chuỗi sẽ cho thấy cần điều tra transaction của phiên 410 trước.

Giả sử phiên 410 đã cập nhật tồn kho xong nhưng ứng dụng gọi dịch vụ vận chuyển trước khi commit. Thời gian gọi dịch vụ kéo dài khiến transaction mở lâu. Biện pháp phù hợp là thiết kế lại ranh giới transaction để không giữ khóa trong lúc chờ dịch vụ bên ngoài, đồng thời dùng cơ chế nghiệp vụ như outbox hoặc quy trình xử lý bất đồng bộ khi cần bảo đảm sự kiện được phát đi sau commit. Chỉ thêm chỉ mục cho câu lệnh của phiên 638 sẽ không giải phóng khóa đang bị phiên 410 giữ.

Sau khi điều chỉnh, cần đo lại số transaction mở lâu, số lock wait, p95/p99 của xác nhận đơn hàng và tỷ lệ timeout. Đồng thời xác nhận quy trình nghiệp vụ vẫn xử lý đúng khi dịch vụ vận chuyển lỗi hoặc phản hồi chậm.

## 8. Các sai lầm thường gặp khi đọc wait events

- **Xem event đứng đầu là nguyên nhân gốc.** Tổng thời gian chờ cao chỉ là điểm bắt đầu. Phải đối chiếu workload, tài nguyên, thời điểm và mục tiêu dịch vụ.
- **Nhầm query age với wait duration.** Thời gian từ lúc truy vấn bắt đầu không đồng nghĩa toàn bộ thời gian đó là thời gian chờ. Dùng metric đúng nghĩa hoặc lấy mẫu để ước lượng khoảng chờ.
- **Chỉ tìm phiên blocked mà bỏ qua blocker.** Phiên chờ thường là nạn nhân. Hãy lần theo quan hệ chặn để tìm phiên giữ tài nguyên ở gốc.
- **Cho rằng blocker luôn chạy câu SQL nặng.** Một transaction nhàn rỗi nhưng chưa commit có thể giữ khóa lâu hơn một truy vấn đang hoạt động.
- **Đồng nhất mọi wait với lock wait.** I/O, log flush, đồng bộ nội bộ, client và replication có cơ chế cũng như hướng xử lý khác nhau.
- **Kết luận từ một ảnh chụp.** Phiên có thể kết thúc ngay sau khi lấy mẫu; cần lịch sử hoặc nhiều mẫu liên tiếp để hiểu diễn biến.
- **Tăng timeout để che triệu chứng.** Timeout dài hơn có thể làm hàng đợi và số kết nối bị giữ lâu hơn. Trước tiên phải tìm nguyên nhân chờ và đánh giá SLA.
- **Hủy phiên mà chưa đánh giá rollback.** Rollback có thể kéo dài, sinh I/O và tác động đến dữ liệu nghiệp vụ. Xác nhận chủ sở hữu và quy trình vận hành trước khi can thiệp.
- **Tăng bộ nhớ hoặc I/O mà không xem kế hoạch.** Nguyên nhân có thể là truy vấn quét quá nhiều dữ liệu, transaction kéo dài hoặc tranh chấp tài nguyên dùng chung.

## 9. Checklist điều tra sự kiện chờ

- [ ] Đã ghi nhận thời điểm, workload, endpoint và nhóm người dùng bị ảnh hưởng.
- [ ] Đã đối chiếu wait event với p95/p99, thông lượng, lỗi và timeout.
- [ ] Đã phân biệt ảnh chụp hiện thời với thống kê tích lũy và biết khoảng lấy mẫu.
- [ ] Đã phân loại event theo lock, I/O, log, bộ nhớ, đồng bộ nội bộ, client hoặc replication.
- [ ] Đã thu thập waiter, blocker, tài nguyên, transaction age và SQL liên quan.
- [ ] Đã lần theo blocking chain để xác định root blocker hoặc vòng deadlock.
- [ ] Đã kiểm tra phiên nhàn rỗi nhưng transaction còn mở và các lời gọi bên ngoài trong transaction.
- [ ] Đã xem kế hoạch thực thi, thống kê và số dòng thực tế khi nghi ngờ truy vấn giữ tài nguyên quá lâu.
- [ ] Đã chọn biện pháp phù hợp nguyên nhân và đánh giá tác động rollback nếu phải kết thúc phiên.
- [ ] Đã chạy lại kịch bản đại diện và so sánh wait, độ trễ, thông lượng cùng tài nguyên sau điều chỉnh.

## Kết luận

Wait event cho biết phiên đang chờ tài nguyên hoặc điều kiện nào; blocking chain cho biết phiên chờ phụ thuộc vào phiên nào. Hai góc nhìn này bổ sung cho nhau khi điều tra hiệu năng. Cần phân biệt chờ khóa với I/O, log, bộ nhớ, đồng bộ nội bộ và phía ứng dụng; đồng thời nhận biết truy vấn CPU-bound có thể không thể hiện như một wait event.

Khi có chuỗi phiên chặn nhau, hãy lần theo quan hệ waiter và blocker để tìm root blocker, kiểm tra transaction age, trạng thái phiên và SQL liên quan. Chọn thay đổi dựa trên nguyên nhân đã xác minh, sau đó đo lại độ trễ phân vị, thời gian chờ, thông lượng và tài nguyên trong cùng điều kiện tải. Đó là cách biến dữ liệu quan sát thành quyết định tối ưu có thể kiểm chứng.

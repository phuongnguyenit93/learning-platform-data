# Thu hồi hệ thống cũ và xử lý dữ liệu còn lại

## 1. Vì sao việc di chuyển chưa kết thúc khi hệ thống mới chạy ổn định?

Trong một chương trình **di chuyển và hiện đại hóa** (migration and modernization), đưa ứng dụng lên đám mây hoặc chuyển sang kiến trúc mới mới chỉ giải quyết một nửa bài toán. Phần còn lại là **thu hồi hệ thống cũ** (decommissioning/retirement) và xử lý những dữ liệu, kết nối, tài nguyên cùng nghĩa vụ vận hành còn tồn tại. Nếu bỏ qua bước này, tổ chức có thể phải trả tiền cho hai hệ thống, duy trì lỗ hổng bảo mật, vận hành những đường tích hợp không ai chịu trách nhiệm hoặc mất dữ liệu cần thiết cho kiểm toán.

Ví dụ, một doanh nghiệp thay ứng dụng quản lý đơn hàng chạy trên máy chủ tại chỗ bằng dịch vụ trên đám mây. Người dùng đã thao tác trên ứng dụng mới, nhưng hệ thống cũ vẫn có:

- Cơ sở dữ liệu chứa lịch sử đơn hàng và hóa đơn của nhiều năm.
- Tác vụ định kỳ xuất báo cáo cuối tháng và một tích hợp chỉ chạy cuối quý.
- Bản sao lưu, snapshot, bản xuất CSV và log có dữ liệu cá nhân.
- Tên miền, chứng chỉ, tài khoản dịch vụ, khóa API, kết nối VPN và máy chủ giám sát.
- Nghĩa vụ giữ một số hồ sơ theo hợp đồng hoặc quy định pháp luật.

Tắt máy chủ ngay có thể làm mất tác vụ cuối quý hoặc khiến người dùng không truy xuất được hóa đơn cũ. Giữ toàn bộ hệ thống chạy vô thời hạn lại tạo chi phí và rủi ro không cần thiết. Kiến trúc sư đám mây phải thiết kế **trạng thái đích sau di chuyển**: chức năng nào chuyển sang hệ thống mới, dữ liệu nào còn cần, dữ liệu ở đâu, truy xuất bằng cách nào, ai sở hữu, và thời điểm được xóa an toàn.

> **Nguyên tắc:** Một hệ thống chỉ thực sự được thu hồi khi chức năng của nó đã được thay thế hoặc chấm dứt có chủ đích, các phụ thuộc đã được xử lý, dữ liệu còn lại có quyết định rõ ràng và bằng chứng hoàn tất được lưu giữ.

## 2. Phân biệt các trạng thái và phạm vi thu hồi

Không nên dùng các thuật ngữ sau như thể chúng đồng nghĩa:

| Trạng thái | Ý nghĩa | Điều cần lưu ý |
|---|---|---|
| **Cutover** | Chuyển lưu lượng hoặc nghiệp vụ chính sang hệ thống mới | Hệ thống cũ có thể vẫn nhận sự kiện, xử lý tác vụ nền hoặc giữ dữ liệu |
| **Read-only** | Ngừng ghi mới, còn cho phép đọc trong thời gian chuyển tiếp | Vẫn cần quản lý truy cập, vá lỗi và theo dõi |
| **Quarantine / isolated** | Cô lập hệ thống cũ khỏi luồng sản xuất, giữ khả năng khôi phục có kiểm soát | Cô lập không thay thế cho quản trị dữ liệu và chính sách lưu giữ |
| **Decommission** | Ngừng vận hành và tháo bỏ thành phần hạ tầng, kết nối, tài khoản liên quan | Chỉ thực hiện sau khi xác minh hết phụ thuộc |
| **Data disposition** | Đưa từng tập dữ liệu đến trạng thái đã quyết định: chuyển, lưu trữ, giữ, ẩn danh hoặc xóa | Có thể tiếp tục sau khi compute đã được thu hồi |

Phạm vi thu hồi không chỉ gồm máy ảo hoặc container. Cần xem cả **compute, mạng, dữ liệu, danh tính và quyền truy cập, khóa mã hóa, tích hợp, công cụ vận hành, chi phí và quy trình nghiệp vụ**.

### 2.1. Ba câu hỏi cần trả lời

1. **Còn ai hoặc cái gì phụ thuộc hệ thống cũ?** Người dùng, API, batch job, webhook, hệ thống báo cáo, đối tác, môi trường khôi phục thảm họa và các chu kỳ ít diễn ra đều có thể là phụ thuộc.
2. **Dữ liệu còn lại có giá trị hoặc nghĩa vụ gì?** Dữ liệu giao dịch, tài liệu pháp lý, thông tin cá nhân, log kiểm toán, cache, bản sao phát sinh và bản sao lưu không có cùng cách xử lý.
3. **Làm sao chứng minh có thể tắt/xóa an toàn?** Cần các chỉ số và bằng chứng có thể kiểm tra, không chỉ dựa vào nhận định “không ai dùng nữa”.

## 3. Khảo sát hệ thống cũ và lập bản đồ phụ thuộc

Thu hồi bắt đầu bằng **inventory** và **dependency mapping**. Đối với mỗi tài sản, xác định chủ sở hữu nghiệp vụ, chủ sở hữu kỹ thuật, môi trường, mức độ quan trọng, thời hạn lưu giữ và trạng thái sử dụng thực tế.

| Nhóm tài sản | Cần kiểm kê | Rủi ro nếu bỏ sót |
|---|---|---|
| Compute | VM, máy chủ vật lý, container, job scheduler, function, agent, license | Tác vụ ngầm vẫn chạy; phát sinh chi phí hoặc lỗi nghiệp vụ |
| Network & entry point | DNS, load balancer, IP, NAT, firewall, VPN, private endpoint, certificate | Client cũ tiếp tục gọi hoặc lộ endpoint không còn được bảo trì |
| Database & storage | Bảng, schema, file, object, volume, snapshot, replica, search index | Mất dữ liệu, tồn dư dữ liệu nhạy cảm, phí lưu trữ kéo dài |
| Messaging & integration | Queue, topic, webhook, ETL/ELT, CDC, SFTP, hợp đồng API | Mất sự kiện, xử lý trùng, đứt luồng dữ liệu hạ nguồn |
| Identity & secret | IAM role, service account, token, API key, SSH key, KMS key | Đường truy cập không còn chủ sở hữu, rò rỉ hoặc không giải mã được archive |
| Operations | Backup, monitoring, log, alert, CMDB, runbook, DR plan | Báo động giả, khôi phục sai hệ thống, không có bằng chứng kiểm toán |
| Business & vendor | Báo cáo, quy trình phê duyệt, tích hợp đối tác, hợp đồng hỗ trợ | Chấm dứt nhầm nghĩa vụ hoặc tăng rủi ro vận hành |

**Nguồn xác minh nên kết hợp:** sơ đồ kiến trúc, danh mục tài sản, mã triển khai, cấu hình scheduler, access log, network flow log, metric, truy vấn DB, danh mục báo cáo, hợp đồng và phỏng vấn người sở hữu nghiệp vụ. Quan sát lưu lượng trong thời gian ngắn không phát hiện được quy trình chạy theo tháng, quý hoặc năm; vì thế phải đối chiếu với lịch nghiệp vụ và các hợp đồng tích hợp.

### 3.1. Xác định “nguồn sự thật” sau cutover

Đặc biệt cần làm rõ hệ thống nào là **system of record** cho từng thực thể như khách hàng, đơn hàng, hóa đơn và tồn kho. Nếu hệ thống cũ còn ghi trong khi hệ thống mới cũng ghi, dữ liệu có thể phân kỳ:

- Nếu **đã chuyển nguồn ghi sang hệ thống mới**: khóa hoặc chặn đường ghi cũ, xử lý những sự kiện đang chờ và kiểm tra không còn writer.
- Nếu **cần chạy song song tạm thời**: nêu rõ hướng đồng bộ, xử lý xung đột, idempotency, thứ tự sự kiện và điều kiện kết thúc chạy song song.
- Nếu **một phần nghiệp vụ không được thay thế**: giao lại chức năng đó cho hệ thống được chỉ định hoặc ra quyết định chấm dứt có sự đồng ý của chủ sở hữu.

Sơ đồ sau cho thấy trạng thái đích thường gặp khi chuyển một ứng dụng nguyên khối sang các dịch vụ đám mây:

~~~mermaid
flowchart LR
    U[Người dùng và đối tác] --> E[DNS / API gateway mới]
    E --> N[Ứng dụng mới trên cloud]
    N --> D[(Cơ sở dữ liệu vận hành)]
    N --> Q[Queue / Event bus mới]
    O[Ứng dụng cũ] -. Đã dừng ghi .-> D
    O --> H[Kho dữ liệu lịch sử]
    H --> R[Truy xuất có kiểm soát]
    O -. Thu hồi sau nghiệm thu .-> X[Đóng compute, mạng, định danh]
    B[(Backup / snapshot cũ)] --> P{Phân loại và hạn lưu giữ}
    P --> H
    P --> Z[Xóa theo chính sách]
~~~

**Lưu ý:** Mũi tên từ hệ thống cũ đến kho lịch sử chỉ biểu diễn quá trình xuất/chuyển dữ liệu trước khi thu hồi; không phải luồng đồng bộ cần giữ mãi. Kho lịch sử cần có cơ chế truy xuất độc lập với ứng dụng cũ nếu mục tiêu là loại bỏ ứng dụng cũ.

## 4. Phân loại và quyết định số phận dữ liệu còn lại

Không có một cách xử lý chung cho mọi dữ liệu. Mỗi tập dữ liệu (dataset) cần được gắn **chủ sở hữu, phân loại bảo mật, mục đích sử dụng, nơi lưu, thời hạn và căn cứ lưu giữ, phụ thuộc, phương án truy xuất và hành động cuối vòng đời**.

### 4.1. Năm hướng xử lý

| Quyết định | Chọn khi nào | Cách triển khai | Đánh đổi chính |
|---|---|---|---|
| **Migrate** (chuyển sang hệ thống mới) | Còn tham gia nghiệp vụ thường ngày hoặc cần truy vấn trực tuyến | Chuyển đổi schema, đối soát bản ghi, nạp vào dữ liệu đích | Tốn chi phí chuyển đổi, kiểm thử và vận hành dữ liệu nóng |
| **Archive** (lưu trữ dài hạn) | Ít truy cập nhưng vẫn cần tra cứu, kiểm toán, đối chiếu | Xuất định dạng bền vững, mã hóa, lưu ở lớp phù hợp, xây đường truy xuất | Rẻ hơn vận hành cả ứng dụng cũ nhưng có độ trễ lấy dữ liệu |
| **Retain in place temporarily** (giữ tạm có hạn) | Chưa giải quyết xong phụ thuộc, tranh chấp hoặc điều kiện khôi phục | Cô lập, tối thiểu quyền, đặt ngày rà soát và chủ sở hữu | Tiếp tục chịu chi phí/bảo mật; phải có hạn chót rõ ràng |
| **Transform / anonymize** (chuyển đổi hoặc ẩn danh) | Chỉ cần phân tích thống kê, không cần định danh cá nhân | Tổng hợp, loại bỏ định danh hoặc dùng phương pháp ẩn danh được kiểm chứng | Có thể mất chi tiết; giả danh hóa vẫn có thể là dữ liệu cá nhân |
| **Delete** (xóa) | Hết nhu cầu, hết nghĩa vụ lưu giữ và không có lệnh giữ dữ liệu | Xóa theo quy trình, theo dõi cả bản sao, log, snapshot, backup | Có thể không thể hoàn tác; cần bằng chứng và phê duyệt |

**Không suy luận thời hạn lưu giữ từ loại công nghệ.** Một bảng hóa đơn, log truy cập hay file đính kèm có thể chịu các nghĩa vụ khác nhau tùy khu vực pháp lý, hợp đồng, mục đích xử lý và chính sách doanh nghiệp. Bộ phận pháp chế, bảo mật và chủ dữ liệu phải xác nhận chính sách áp dụng. “Giữ lại phòng khi cần” không phải chính sách lưu giữ hoàn chỉnh.

### 4.2. Ma trận quyết định theo dữ liệu

| Dữ liệu hệ thống quản lý đơn hàng | Cách xử lý minh họa | Điểm kiểm tra bắt buộc |
|---|---|---|
| Đơn hàng còn mở, tồn kho, phiên giao dịch đang hoạt động | Migrate sang cơ sở dữ liệu mới | Có thể xử lý tiếp, không mất trạng thái và không có ghi kép |
| Lịch sử đơn hàng đã đóng | Migrate một phần hoặc archive | Người có quyền vẫn tra cứu/đối soát được |
| Hóa đơn, chứng từ, hợp đồng | Archive theo lịch và nghĩa vụ lưu giữ được phê duyệt | Có tính toàn vẹn, giải mã/đọc được, kiểm soát truy cập |
| Bản export CSV tạm, cache tái tạo được | Delete khi hết nhu cầu và không bị yêu cầu giữ | Không còn job/hệ thống nào cần dùng |
| Log có thông tin cá nhân | Giữ/xóa theo mục đích, thời hạn và chính sách log | Không lưu vô hạn chỉ vì dễ bật log |
| Bản sao DB, snapshot, backup | Đánh giá riêng từng loại và chu kỳ | Không nhầm bản sao lưu với archive có khả năng tra cứu |
| Bộ dữ liệu đang chịu legal hold | Hold và hạn chế quyền; trì hoãn xóa | Quyết định giữ được ghi nhận, phạm vi rõ, có người gỡ hold |
| Khóa mã hóa dùng cho archive | Giữ và quản lý vòng đời đủ để đọc dữ liệu được phép giữ | Không vô hiệu hóa/xóa khóa trước dữ liệu cần giải mã |

### 4.3. Bản sao dữ liệu và điểm khó khi xóa

Dữ liệu gốc không phải là nơi duy nhất tồn tại thông tin. Có thể còn **replica, snapshot, database dump, staging table, cache, search index, object version, CDN, dead-letter queue, file export, log, dữ liệu gửi đối tác và bản sao phục vụ DR**.

Khi có yêu cầu xóa dữ liệu, kiến trúc sư phải xác định phạm vi xử lý cho từng bản sao và khả năng thực thi của từng nền tảng. Với backup bất biến, có thể không hỗ trợ xóa một bản ghi riêng lẻ ngay lập tức; khi đó phải thiết kế thời hạn hết hạn của backup, hạn chế khôi phục, cơ chế áp dụng lại yêu cầu xóa nếu restore và tài liệu hóa giới hạn phù hợp với yêu cầu pháp lý. Không được khẳng định rằng xóa một hàng trong DB đồng nghĩa dữ liệu đã biến mất khỏi toàn bộ hệ thống.

**Crypto-erasure** (hủy khóa để khiến dữ liệu mã hóa không thể đọc) có thể là phương án trong một số kiến trúc, nhưng chỉ thích hợp khi phạm vi khóa đúng, không tồn tại bản dữ liệu rõ hoặc bản sao dùng khóa khác, và yêu cầu lưu giữ không bị vi phạm. Không xóa khóa dùng chung cho dữ liệu vẫn phải giữ.

## 5. Thiết kế kho lưu trữ lịch sử độc lập

Nếu phải giữ dữ liệu nhưng không muốn tiếp tục vận hành ứng dụng cũ, cần thiết kế một **historical archive** có thể truy cập mà không phụ thuộc vào máy chủ hoặc cơ sở dữ liệu đã thu hồi.

Một phương án phổ biến:

1. Xuất dữ liệu từ nguồn cũ ở thời điểm được kiểm soát; chọn tập dữ liệu đầy đủ theo tiêu chí nghiệp vụ.
2. Chuẩn hóa định dạng và schema: CSV/Parquet/JSON cho dữ liệu có cấu trúc tùy mục đích; PDF và định dạng gốc cho chứng từ khi phù hợp.
3. Tạo metadata: phiên bản schema, nguồn, thời điểm xuất, số bản ghi, checksum, khóa liên kết nghiệp vụ, chính sách lưu giữ, owner.
4. Mã hóa khi truyền và lưu; chọn vùng lưu trữ, quyền truy cập, khóa và mức lưu trữ theo yêu cầu.
5. Cung cấp cách tìm kiếm/tra cứu: giao diện cho người có thẩm quyền, truy vấn qua catalog hoặc quy trình yêu cầu xuất dữ liệu được kiểm soát.
6. Thử truy xuất và kiểm tra tính toàn vẹn bằng mẫu nghiệp vụ trước khi tắt nguồn cũ.

Lựa chọn kho archive ảnh hưởng trực tiếp đến **chi phí, độ trễ truy xuất và tính sẵn sàng**:

| Thiết kế | Phù hợp | Hạn chế cần tính |
|---|---|---|
| Cơ sở dữ liệu read-only được quản lý | Cần truy vấn tương tác thường xuyên, quan hệ phức tạp | Chi phí compute và vận hành cao hơn lưu trữ đối tượng |
| Object storage + catalog/query | Dữ liệu lớn, chủ yếu tra cứu/đối soát không thường xuyên | Phải quản lý schema, partition, quyền theo dữ liệu và quy trình truy xuất |
| Tầng lưu trữ archive/deep archive | Hiếm khi truy cập, chấp nhận thời gian khôi phục dài | Phí lấy lại, thời gian khôi phục, thời gian lưu tối thiểu tùy dịch vụ |
| Ứng dụng chuyên biệt quản lý hồ sơ | Cần luồng phê duyệt, tìm kiếm và bằng chứng pháp lý | Có phụ thuộc nhà cung cấp và hợp đồng dịch vụ |

**Archive khác backup.** Backup chủ yếu phục vụ phục hồi sau sự cố về một trạng thái hệ thống; archive phục vụ lưu giữ và truy xuất dữ liệu lịch sử theo chính sách, thường qua định dạng, quyền và chỉ mục độc lập. Không lấy sự tồn tại của bản backup làm bằng chứng người dùng có thể tra cứu lịch sử.

### 5.1. Đối soát dữ liệu khi chuyển hoặc lưu trữ

So sánh **định lượng** (số lượng bản ghi, tổng giá trị giao dịch, phân bố theo ngày/trạng thái) và **định tính** (quy tắc nghiệp vụ, quan hệ, định dạng, quyền truy cập). Hash/checksum phù hợp để phát hiện lỗi toàn vẹn của một artifact hoặc tập dữ liệu được chuẩn hóa, nhưng không tự chứng minh hai schema có ý nghĩa nghiệp vụ tương đương.

Ví dụ truy vấn đọc để đối soát dữ liệu đơn hàng (cú pháp minh họa theo PostgreSQL):

~~~sql
SELECT
    DATE(created_at) AS order_date,
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
WHERE created_at >= :start_time
  AND created_at < :end_time
GROUP BY DATE(created_at), status
ORDER BY order_date, status;
~~~

Chạy truy vấn tương đương ở nguồn và đích cho cùng **mốc chốt dữ liệu**; giải thích mọi khác biệt hợp lệ do chuyển đổi schema, tiền tệ, timezone hoặc quy tắc làm tròn. Đối với dữ liệu cần tính chính xác cao, bổ sung đối soát ở mức ID, khóa ngoại, tập mẫu có chủ đích và kiểm tra tổng thể sau cutover.

### 5.2. Kiểm soát lưu giữ và quyền truy xuất

- **Retention:** xác định sự kiện bắt đầu tính hạn (ngày tạo, đóng hợp đồng, kết thúc giao dịch...), thời gian giữ, cách tính và hành động khi hết hạn. Dùng lifecycle rule nếu tương thích chính sách; quản lý ngoại lệ và legal hold riêng.
- **Access:** áp dụng least privilege, phân quyền theo nhóm hồ sơ và mục đích, ghi log hoạt động truy xuất. Quyền đọc dữ liệu lịch sử không mặc nhiên cấp cho mọi quản trị viên ứng dụng.
- **Encryption:** xác định ai sở hữu khóa, cách xoay/thu hồi quyền và khả năng giải mã trong toàn bộ thời gian dữ liệu còn phải giữ.
- **Integrity:** lưu checksum, metadata phiên bản và nhật ký xuất/nhập; kiểm tra định kỳ khả năng đọc dữ liệu và phục hồi quy trình truy xuất.
- **Location & transfer:** đánh giá yêu cầu vùng dữ liệu, chuyển dữ liệu xuyên biên giới, đối tác xử lý, và đường truyền trước khi quyết định nơi archive.
- **End of life:** khi hết hạn và không còn lệnh giữ, tạo tác vụ disposition có xác nhận, kiểm tra bản sao và ghi bằng chứng hoàn tất.

## 6. Quy trình thu hồi theo từng cổng kiểm soát

Một quy trình có thể kiểm toán được nên tiến theo các **gate** thay vì đặt một lịch xóa hạ tầng rồi hy vọng mọi phụ thuộc đã biến mất.

### Giai đoạn A — Khám phá và thống nhất phạm vi

- Lập inventory tài sản, dữ liệu và bên tiêu thụ; xác nhận ai ký nghiệm thu.
- Xác định hệ thống mới tiếp quản những chức năng nào, phần nào được chấm dứt và phần nào phải giữ.
- Đánh giá chu kỳ nghiệp vụ dài, báo cáo theo quý/năm, tích hợp đối tác và quy trình khôi phục thảm họa.
- Định nghĩa SLO và chỉ số ổn định sau cutover, dữ liệu phải đối soát, khoảng thời gian quan sát và điều kiện dừng.

**Gate A:** có danh sách tài sản và phụ thuộc với chủ sở hữu, phạm vi di chuyển, quyết định sơ bộ cho từng tập dữ liệu và kế hoạch kiểm chứng.

### Giai đoạn B — Chuyển chức năng và dữ liệu

- Triển khai hệ thống đích, định tuyến người dùng/API, di chuyển dữ liệu và đối soát.
- Xác nhận các job cũ đã được chuyển hoặc chấm dứt. Kiểm tra độ trễ hàng đợi, CDC lag, các sự kiện lỗi và dead-letter queue.
- Chuyển hệ thống đích thành nguồn ghi có thẩm quyền; ghi nhận thời điểm cutover và xử lý delta phát sinh trước thời điểm đó.
- Kiểm tra chức năng chính lẫn tình huống ít gặp: hoàn tiền, sửa hóa đơn, đối soát tháng, xử lý khi đối tác gửi lại thông điệp cũ.

**Gate B:** nghiệp vụ vận hành được trên hệ thống mới, đối soát đạt ngưỡng đã thống nhất, không còn writer không được kiểm soát trên nguồn cũ.

### Giai đoạn C — Đóng băng, giám sát và cách ly

- Đặt nguồn cũ ở trạng thái read-only hoặc chặn ghi tại lớp ứng dụng, DB và integration phù hợp.
- Duy trì khoảng quan sát (soak period) theo rủi ro và chu kỳ nghiệp vụ; dùng metrics, logs, tracing, flow log để tìm truy cập bất thường.
- Chuyển DNS, webhook, chứng chỉ, scheduler và cảnh báo còn sử dụng sang đích mới.
- Cô lập quyền và đường mạng cũ; khóa service account không còn phục vụ hệ thống đang hoạt động.

**Gate C:** không có lưu lượng/phụ thuộc nghiệp vụ cần thiết, các cảnh báo chuyển tuyến chính xác, khả năng phục hồi hoặc quay lui trong cửa sổ cho phép đã được xác minh.

### Giai đoạn D — Xử lý dữ liệu và tháo hạ tầng

- Đối chiếu ma trận disposition: migrate, archive, giữ có hạn, ẩn danh hoặc delete.
- Kiểm tra archive có thể truy xuất được **trước khi** gỡ database/compute cũ.
- Thu hồi theo lớp, ưu tiên thành phần có thể hoàn tác: chuyển endpoint, vô hiệu hóa job, tắt compute, sau đó mới tháo tài nguyên và xử lý dữ liệu theo phê duyệt.
- Gỡ network rule, DNS record, load balancer, service account, API key, secret, chứng chỉ, storage, database instance và lịch backup theo quan hệ phụ thuộc.
- Cập nhật inventory, sơ đồ, runbook, DR plan, catalog, billing tags, hợp đồng/license và hồ sơ kiểm toán.

**Gate D:** từng tài sản được đóng với trạng thái và bằng chứng; các dữ liệu buộc giữ vẫn truy xuất/giải mã được; không còn tài nguyên “mồ côi” hoặc quyền truy cập cũ.

### Giai đoạn E — Xác nhận sau thu hồi

- Theo dõi lỗi nghiệp vụ, truy vấn vào endpoint cũ, job thất bại, alert và tình trạng bảo mật.
- Đối chiếu hóa đơn/chi phí thực tế trong các kỳ phù hợp; storage, snapshot, egress, IP tĩnh, license và support contract có thể còn tạo chi phí.
- Kiểm tra lịch retention và quy trình truy xuất archive, kể cả khả năng tìm đúng một hồ sơ cụ thể theo quyền được cấp.
- Đóng biên bản nghiệm thu khi chủ nghiệp vụ, vận hành, bảo mật và chủ dữ liệu hoàn tất phần việc.

**Gate E:** việc thu hồi được chứng minh bằng trạng thái tài sản, kết quả thử nghiệm và dữ liệu chi phí, không chỉ bằng “server đã tắt”.

## 7. Rủi ro kiến trúc khi tháo các thành phần cloud

### 7.1. Tài nguyên dùng chung

Một security group, subnet, route, KMS key, storage bucket, cluster, private DNS zone, observability workspace hoặc CI/CD agent có thể phục vụ nhiều ứng dụng. Xóa tài nguyên có tên giống hệ thống cũ chưa đủ căn cứ để xem là an toàn. Cần tìm **consumer** và **owner** độc lập cho từng tài nguyên.

### 7.2. Hệ thống bất đồng bộ và dữ liệu đang di chuyển

Chặn traffic HTTP không có nghĩa hết thông điệp. Trước khi tắt worker và broker, kiểm tra các chỉ số như **queue depth, consumer lag, in-flight messages, retry, dead-letter, CDC replication lag** và đối chiếu event ID. Với tác vụ có thể chạy lại, yêu cầu idempotency để tránh mất hoặc trùng tác động nghiệp vụ.

### 7.3. Backup và khôi phục thảm họa

Backup của hệ thống cũ có thể được giữ theo chính sách dù ứng dụng đã ngừng hoạt động. Cần phân biệt:

- **Backup để quay lui ngắn hạn:** dùng trong cửa sổ rollback đã xác định, có kiểm soát và diễn tập.
- **Backup theo nghĩa vụ lưu giữ:** tồn tại đến ngày hết hạn hợp lệ, giới hạn quyền và có lịch xóa.
- **Archive cho tra cứu:** vận hành độc lập, có quy trình tìm và xuất dữ liệu.

Không tiếp tục sao lưu một máy chủ đã thu hồi chỉ vì lịch backup chưa được xóa. Ngược lại, không hủy khóa hoặc backup khi vẫn cần khả năng giải mã hoặc khôi phục dữ liệu đã được phép giữ.

### 7.4. Tính không thể đảo ngược

Tắt VM thường có thể khởi động lại; xóa storage, snapshot, khóa hoặc cấu hình định danh có thể khiến khôi phục rất khó hoặc không thể. Vì vậy, kế hoạch phải nêu rõ **điểm không thể quay lui**, người phê duyệt và bằng chứng yêu cầu trước điểm đó. Nếu dữ liệu đã xóa vĩnh viễn theo quy trình, “rollback” hệ thống cũ không còn là phương án hợp lệ.

## 8. Thiết kế kế hoạch rollback và tiêu chí nghiệm thu

Rollback phù hợp nhất ở giai đoạn chuyển lưu lượng hoặc cách ly tạm thời, khi dữ liệu nguồn còn nhất quán và được phép lưu. Có thể dùng lại hệ thống cũ chỉ nếu đã phân tích các bản ghi mới trên đích, cơ chế đồng bộ ngược, xung đột và nghĩa vụ xử lý dữ liệu. Không được giả định chỉ cần đổi DNS về máy cũ là dịch vụ sẽ an toàn.

Một kế hoạch cần xác định:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Trigger | Lỗi nào khiến phải dừng hoặc quay lui: mất giao dịch, đối soát lệch, độ trễ vượt ngưỡng, lỗi truy cập archive? |
| Decision owner | Ai có quyền ra quyết định trong cửa sổ change? |
| Window | Đến thời điểm nào vẫn có thể quay lui mà không gây phân kỳ dữ liệu? |
| State/data | Dữ liệu ghi sau cutover được xử lý thế nào nếu quay về nguồn cũ? |
| Verification | Chỉ số, thử nghiệm và bước xác nhận nào cho biết đã phục hồi? |
| Irreversible actions | Những tài nguyên/khóa/dữ liệu nào chưa được xóa cho tới khi hết khả năng quay lui? |

Ví dụ **acceptance criteria** có thể đo được:

- 100% chức năng quan trọng đã có chủ sở hữu ở hệ thống mới hoặc có quyết định chấm dứt.
- Không còn request nghiệp vụ hợp lệ đi vào endpoint cũ trong cửa sổ giám sát đã thỏa thuận, sau khi xét đủ chu kỳ ít phát sinh.
- Toàn bộ dữ liệu bắt buộc chuyển/giữ đã được đối soát và kiểm tra truy xuất theo tiêu chí được phê duyệt.
- Không còn writer hoặc consumer quan trọng chạy trên hạ tầng cũ; backlog và sự kiện lỗi đã được xử lý.
- Các tài sản, quyền truy cập, khóa, backup và hợp đồng được đóng hoặc có lịch xử lý, người chịu trách nhiệm rõ ràng.
- Dấu vết phê duyệt, kiểm thử và xóa/lưu trữ được lưu vào hồ sơ thay đổi.

Các ngưỡng cụ thể (ví dụ sai lệch số bản ghi bằng 0 với giao dịch tài chính hay mức lỗi SLO) phải được đặt theo đặc tính hệ thống; không áp dụng một ngưỡng chung cho mọi loại dữ liệu.

## 9. Hồ sơ thu hồi và bằng chứng kiểm toán

Một **decommission manifest** giúp các nhóm nghiệp vụ, dữ liệu và vận hành nhìn cùng một trạng thái. Dưới đây là mẫu minh họa, không phải cấu hình có thể tự động xóa tài nguyên:

~~~yaml
system_id: order-legacy
business_owner: order-operations
technical_owner: cloud-platform
target_system: order-service-v2
cutover_at: "YYYY-MM-DDTHH:MM:SSZ"
rollback_deadline: "Theo change record đã phê duyệt"

dependencies:
  - name: monthly-invoice-job
    disposition: migrated
    evidence: "Link đến kết quả chạy thử và nghiệm thu"
  - name: partner-sftp
    disposition: retired
    evidence: "Xác nhận của chủ tích hợp"

datasets:
  - name: open_orders
    classification: confidential
    disposition: migrate
    destination: order-service-v2
    owner: order-data
    verification: "Đối soát theo ID, trạng thái, tổng tiền"
  - name: closed_invoices
    classification: restricted
    disposition: archive
    destination: controlled-records-store
    retention_policy: "Tham chiếu chính sách đã duyệt"
    legal_hold: false
    retrieval_test: passed
  - name: obsolete_temp_export
    classification: internal
    disposition: delete
    approval: "Tham chiếu change record và chủ dữ liệu"

infrastructure:
  - resource: old-app-vm
    action: decommission
    dependency_check: passed
  - resource: shared-kms-key
    action: retain
    reason: "Archive khác vẫn phụ thuộc"

evidence:
  migration_reconciliation: "Link kết quả đối soát"
  archive_retrieval: "Link biên bản thử truy xuất"
  access_revocation: "Link nhật ký thu hồi quyền"
  cost_verification: "Kỳ kiểm tra chi phí sau thu hồi"
approvals:
  business: pending
  data_governance: pending
  security: pending
  operations: pending
~~~

Để vận hành ở quy mô nhiều ứng dụng, có thể quản lý manifest này trong hệ thống change management hoặc asset catalog. Tự động hóa chỉ được thực thi sau khi các trường điều kiện và bằng chứng đã được kiểm tra; **không suy luận rằng trường có chữ “delete” là lệnh xóa được phép chạy**.

### 9.1. Kiểm tra kỹ thuật trước các thao tác không thể hoàn tác

Logic quyết định có thể biểu diễn ở mức giả mã:

~~~text
can_destroy(asset):
    require asset.owner is known
    require dependencies(asset) are resolved
    require workload_is_not_receiving_valid_traffic(asset)
    require business_and_technical_signoff(asset)

    for dataset in datasets_affected_by(asset):
        require dataset.disposition is approved
        require required_migration_or_archive_is_verified(dataset)
        require retention_and_legal_hold_are_respected(dataset)
        require restoration_or_retrieval_path_is_tested_if_needed(dataset)

    require shared_resources_are_excluded_or_separately_approved(asset)
    require rollback_window_is_closed_for_irreversible_actions(asset)
    return true
~~~

Đây là **mô hình kiểm soát**, không phải thuật toán phát hiện phụ thuộc tự động. Danh mục phụ thuộc và chữ ký phê duyệt vẫn phải đến từ các nguồn có trách nhiệm.

### 9.2. Ma trận trách nhiệm gợi ý

| Vai trò | Trách nhiệm chính |
|---|---|
| Business owner | Xác nhận chức năng được thay thế/chấm dứt, nhu cầu tra cứu và nghiệm thu nghiệp vụ |
| Data owner / governance | Phân loại, quyết định migrate/archive/delete, retention, legal hold và quyền dữ liệu |
| Cloud architect | Thiết kế trạng thái đích, dependency, cổng nghiệm thu và các đánh đổi kiến trúc |
| Platform / SRE | Thực hiện cutover, theo dõi, thu hồi hạ tầng, xác nhận vận hành và chi phí |
| Security / compliance | Kiểm tra quyền, mã hóa, vòng đời khóa, yêu cầu tuân thủ và bằng chứng |
| Application / integration team | Di chuyển batch job, API, event consumer và kiểm thử các trường hợp nghiệp vụ |

Với hệ thống nhỏ, một người có thể đảm nhiệm nhiều vai trò, nhưng **quyền ra quyết định và bằng chứng phê duyệt** vẫn cần rõ.

## 10. Đánh đổi theo nguyên tắc Well-Architected

Thu hồi hệ thống cũ là một quyết định kiến trúc kết hợp nhiều trụ cột, không chỉ là tối ưu hóa chi phí:

| Góc nhìn | Quyết định kiến trúc | Chỉ số hoặc bằng chứng nên theo dõi |
|---|---|---|
| **Operational Excellence** | Gate rõ, runbook, inventory, owner, tự động hóa có phê duyệt | Tỷ lệ tài sản đã đóng, số ngoại lệ, hồ sơ thay đổi hoàn chỉnh |
| **Security** | Xóa đường truy cập cũ, phân loại và mã hóa dữ liệu, kiểm soát khóa | IAM/secret không còn sử dụng, log truy cập archive, số dữ liệu tồn dư |
| **Reliability** | Xác minh phụ thuộc, đối soát, xử lý queue, rollback window | Lỗi sau cutover, tỷ lệ dữ liệu hợp lệ, kết quả thử truy xuất |
| **Performance Efficiency** | Chọn kho lịch sử và phương án truy xuất theo tần suất thực | Độ trễ tìm/khôi phục dữ liệu lịch sử, tài nguyên duy trì |
| **Cost Optimization** | Loại bỏ compute, license và tài nguyên mồ côi; chọn storage tier hợp lý | Chi phí cloud/on-prem, chi phí archive và retrieval sau thu hồi |
| **Sustainability** | Dừng hạ tầng không còn sử dụng, chọn lưu trữ tương xứng nhu cầu | Tài nguyên luôn bật đã loại bỏ, dung lượng lưu trữ không cần thiết |

Hai tình huống đối lập giúp thấy rõ đánh đổi:

- **Truy xuất lịch sử mỗi ngày:** kho dữ liệu có chỉ mục và giao diện tìm kiếm có thể tốn hơn object storage lạnh nhưng giảm độ trễ và công sức của đội hỗ trợ.
- **Chỉ tra cứu vài lần mỗi năm:** archive ở tầng rẻ hơn có thể tiết kiệm, nhưng phải chấp nhận thời gian lấy lại, phí retrieval và có quy trình phục vụ yêu cầu đúng hạn.

Chi phí mục tiêu là **tổng chi phí vòng đời**: lưu trữ + truy xuất + xử lý + bảo mật + vận hành + nghĩa vụ giữ dữ liệu, chứ không chỉ giá lưu trữ trên mỗi GB.

## 11. Tình huống thực hành: ngừng hệ thống đặt hàng cũ

**Bối cảnh:** Doanh nghiệp đã chuyển chức năng đặt hàng sang microservice trên đám mây. Ứng dụng cũ còn một database 2 TB, 12 VM, job đối soát cuối tháng, API của một đối tác gửi dữ liệu theo quý, các snapshot lưu theo nhiều mốc và hóa đơn điện tử cần giữ theo chính sách.

**Mục tiêu:** loại bỏ hạ tầng vận hành cũ nhưng duy trì được việc xử lý đơn hàng, đối soát và tra cứu hóa đơn.

**Thiết kế đề xuất theo bước:**

1. **Phân rã phụ thuộc:** xác định người dùng, đối tác, lịch job, queue, DB và hệ thống báo cáo. Chuyển API đối tác qua gateway mới, thay lịch job bằng tác vụ đích; chạy thử với dữ liệu được phép sử dụng.
2. **Chốt nguồn ghi:** chuyển order writes sang database đích; dừng writer cũ và kiểm tra delta, CDC lag, backlog. Dùng cùng một mốc thời gian và timezone khi đối soát dữ liệu.
3. **Xử lý dữ liệu:** migrate đơn hàng đang mở; archive hóa đơn và lịch sử cần lưu; xóa export tạm theo phê duyệt; đánh giá snapshot/backup riêng theo retention.
4. **Xây khả năng tra cứu:** cung cấp công cụ tìm chứng từ theo ID đơn hàng, phân quyền theo vai trò, ghi log truy cập; thử tìm và mở một tập hồ sơ đại diện trước khi thu hồi DB.
5. **Quan sát đủ chu kỳ:** kiểm tra ít nhất một lần chạy thành công của job cuối tháng và phối hợp với đối tác để kiểm tra tích hợp theo quý hoặc có bằng chứng thử nghiệm phù hợp nếu không thể đợi đến quý.
6. **Thu hồi hạ tầng:** vô hiệu hóa endpoint cũ, theo dõi; tắt 12 VM, gỡ các tài nguyên riêng biệt và quyền cũ sau khi gate đạt; tránh xóa subnet/KMS dùng chung.
7. **Chốt kết quả:** lưu biên bản đối soát, thử truy xuất, quyền đã gỡ, danh mục tài sản còn giữ có hạn, và kiểm tra chi phí trong kỳ sau.

**Quyết định cần trao đổi với nghiệp vụ:** nếu mỗi tháng bộ phận kế toán phải truy vấn linh hoạt hàng triệu hóa đơn, lưu ở tầng archive rất lạnh có thể không đáp ứng yêu cầu; khi đó một lớp chỉ mục hoặc cơ sở dữ liệu phục vụ truy xuất là khoản chi phí có căn cứ. Nếu chỉ có yêu cầu tra cứu theo ID vài lần một năm, giữ nguyên cả DB engine cũ thường không phải lựa chọn tối ưu.

### Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Tắt hệ thống sau vài ngày không thấy traffic | Bỏ sót job theo tháng/quý, tích hợp đối tác | Kết hợp telemetry, danh mục nghiệp vụ và xác nhận owner |
| Xem snapshot là phương án archive | Không tra cứu được, restore mất thời gian, phụ thuộc công nghệ cũ | Thử truy xuất độc lập qua định dạng/công cụ lưu trữ lịch sử |
| Giữ toàn bộ dữ liệu vô hạn | Tăng chi phí, rủi ro bảo mật và nghĩa vụ quản lý | Retention matrix có owner, trigger, hạn và xử lý ngoại lệ |
| Xóa bucket, role hoặc khóa theo tên ứng dụng | Làm gián đoạn hệ thống khác hoặc mất khả năng giải mã | Kiểm tra quan hệ tài nguyên dùng chung và người tiêu thụ |
| Chỉ đối soát số dòng | Không phát hiện sai giá trị, mapping hoặc quan hệ nghiệp vụ | Kết hợp đối soát định lượng, semantic và mẫu giao dịch |
| Xóa tài nguyên nhưng không cập nhật vận hành | Alert sai, tài liệu DR lỗi thời, chi phí còn sót | Đóng change, CMDB, runbook, billing, license và kiểm tra sau |

## 12. Checklist trước khi tuyên bố hoàn tất

Một bài thu hồi được xem là hoàn thành về mặt kiến trúc khi trả lời **Có** cho toàn bộ câu hỏi áp dụng:

- [ ] Chức năng nghiệp vụ, khách hàng, đối tác và các job định kỳ đã được thay thế hoặc có quyết định chấm dứt được phê duyệt?
- [ ] Mọi data owner đã phân loại và quyết định **migrate / archive / giữ tạm / ẩn danh / xóa** với chính sách retention và legal hold phù hợp?
- [ ] Dữ liệu đã chuyển và lưu trữ được đối soát; archive có thể **tìm, đọc, giải mã** bằng công cụ và quyền đích?
- [ ] Không còn writer, consumer, webhook hay luồng mạng hợp lệ cần hệ thống cũ; các hàng đợi và retry đã được xử lý?
- [ ] Cửa sổ rollback và điểm không thể hoàn tác đã được hiểu rõ; việc xóa chỉ diễn ra sau các cổng nghiệm thu tương ứng?
- [ ] Tài nguyên dùng chung, backup, snapshot, object version, log, secret và khóa mã hóa đã được kiểm kê và có quyết định riêng?
- [ ] DNS, chứng chỉ, IAM, monitoring, backup policy, DR plan, runbook, asset catalog, license và tài liệu tích hợp đã được cập nhật?
- [ ] Hồ sơ đổi trạng thái, phê duyệt, bằng chứng đối soát/thu hồi và lịch xử lý dữ liệu còn giữ đã được lưu?
- [ ] Có người chịu trách nhiệm tiếp tục quản lý kho archive, xử lý yêu cầu xóa và kiểm tra chi phí sau khi hệ thống cũ biến mất?

**Kết luận:** Thu hồi hệ thống cũ là thiết kế và thực thi một trạng thái vận hành mới có thể chứng minh được. Đích đến đúng là ứng dụng mới đảm nhiệm chức năng cần thiết, dữ liệu còn giá trị được giữ và truy xuất theo chính sách, dữ liệu hết nghĩa vụ được xử lý an toàn, tài nguyên cũ không còn tạo phụ thuộc hay chi phí vô ích. Đây là bước cuối quan trọng để chương trình hiện đại hóa thực sự đạt lợi ích về độ tin cậy, bảo mật, khả năng vận hành và chi phí.

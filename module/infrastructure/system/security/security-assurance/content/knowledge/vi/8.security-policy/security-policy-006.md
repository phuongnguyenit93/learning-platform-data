# Chính sách retention – Lưu giữ và hủy dữ liệu có thể kiểm chứng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **retention policy (chính sách lưu giữ)** và phân biệt lưu giữ, lưu trữ dài hạn, sao lưu, xóa, ẩn danh, tạm giữ phục vụ điều tra và bảo quản bằng chứng.
- Xác định mục đích, loại dữ liệu, thời điểm bắt đầu tính hạn, thời hạn, địa điểm lưu, chủ sở hữu và cách kết thúc vòng đời cho từng nhóm dữ liệu.
- Phân tích rủi ro **giữ quá lâu** và **xóa quá sớm**, từ quyền riêng tư, rò rỉ dữ liệu đến mất bằng chứng phục vụ an ninh, audit và khôi phục.
- Chuyển chính sách thành các **security requirements**, security controls, tiêu chí kiểm thử và bằng chứng có thể đối chiếu ở development, CI/CD và production.
- Thiết kế luồng retention trong ứng dụng Java/Spring Boot với quy tắc thời gian, xử lý trường hợp legal hold, trạng thái chờ xóa và cơ chế kiểm tra việc xóa.
- Tổ chức đánh giá, audit, quản lý ngoại lệ, khắc phục phát hiện và **đánh giá lại liên tục** khi dữ liệu, hệ thống hoặc nghĩa vụ thay đổi.

## 1. Vì sao retention là một chính sách bảo mật?

**Retention** là việc xác định **dữ liệu nào cần được lưu trong bao lâu, vì mục đích gì và phải xử lý thế nào sau khi không còn lý do hợp lệ để giữ**. Một *retention policy* biến các quyết định đó thành yêu cầu có người chịu trách nhiệm và có thể kiểm tra.

Retention không chỉ liên quan chi phí lưu trữ:

- **Bí mật và quyền riêng tư:** dữ liệu tồn tại càng lâu và được sao chép càng nhiều nơi thì càng có nhiều cơ hội bị truy cập hoặc lộ ngoài phạm vi cho phép.
- **Toàn vẹn và chống chối bỏ:** nếu log, chứng cứ phê duyệt hoặc thông tin truy vết bị xóa trước hạn, tổ chức khó giải thích ai đã làm gì và chứng minh security controls có hoạt động hay không.
- **Tính sẵn sàng và khôi phục:** phải giữ các bản backup, snapshot hoặc lịch sử khôi phục phù hợp với mục tiêu phục hồi được phê duyệt; giữ bản sao quá lâu cũng tạo rủi ro.
- **Trách nhiệm giải trình và audit:** người đánh giá cần bằng chứng đúng phiên bản, thời điểm, nguồn gốc và phạm vi để kết luận mục tiêu bảo mật đã được đáp ứng.
- **Tuân thủ và nghĩa vụ:** loại dữ liệu, hợp đồng, khu vực pháp lý, quyền của chủ thể dữ liệu hoặc vụ việc đang điều tra có thể tác động tới giới hạn lưu giữ và xóa.

Trong module **SECURITY_SECURITY_ASSURANCE**, retention là một phần của chương trình chứng minh bằng bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật. Nhóm kỹ thuật cần nối **phân tích rủi ro → yêu cầu → control → kiểm thử → bằng chứng → audit → finding → khắc phục/retest**. Không nên coi việc viết tài liệu “xóa sau N ngày” là bằng chứng quá trình xóa thật đã vận hành.

### Ví dụ khởi đầu

Một dịch vụ thanh toán lưu bốn loại dữ liệu:

1. **Báo cáo giao dịch chính thức**: có thể phải lưu theo nghĩa vụ áp dụng và mục đích nghiệp vụ đã được duyệt.
2. **File CSV xuất tạm cho người dùng tải**: chỉ nên tồn tại đủ để hoàn thành thao tác; bản sao lâu ngày làm tăng rủi ro lộ dữ liệu.
3. **Security audit log**: cần giữ đủ thời gian để điều tra, truy vết, nhận diện và xác minh sự kiện bảo mật.
4. **Access token/secret tạm**: phải có vòng đời ngắn, xử lý thu hồi và không đưa giá trị nhạy cảm vào log chỉ để “lưu bằng chứng”.

Dùng **một thời hạn duy nhất** cho tất cả những loại dữ liệu đó vừa có thể giữ thừa vừa có thể làm mất dữ liệu cần thiết.

## 2. Phân biệt các khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Điểm cần kiểm tra |
| --- | --- | --- |
| **Retention period** | Khoảng thời gian dữ liệu phải/được lưu theo quy tắc áp dụng | Tính từ **sự kiện nào**, theo lịch nào, đến khi nào? |
| **Retention schedule** | Danh mục loại dữ liệu và các quy tắc lưu giữ tương ứng | Có owner, căn cứ, version, trigger và phạm vi không? |
| **Archival** | Chuyển dữ liệu ít được dùng sang lớp lưu trữ phù hợp | Có giữ nguyên quyền, khả năng kiểm chứng và thời hạn không? |
| **Backup** | Bản sao phục vụ phục hồi khi có sự cố | Backup có vòng đời riêng, quyền truy cập, lịch thử restore không? |
| **TTL (time to live)** | Thời hạn tồn tại dự kiến của một đối tượng/tài nguyên | TTL có bảo đảm xóa đúng lúc hay chỉ đánh dấu hết hạn/chờ job? |
| **Deletion / purge** | Xóa dữ liệu khỏi một phạm vi lưu trữ theo phương pháp định nghĩa | Xóa logic hay vật lý, có backup/cache/bản sao nào chưa xử lý? |
| **Anonymization** | Xử lý để dữ liệu không còn liên hệ được với cá nhân theo tiêu chí phù hợp | Có thật sự không thể tái nhận dạng với dữ liệu còn lại và bối cảnh thực tế? |
| **Pseudonymization** | Thay/giấu định danh nhưng còn có thể liên kết lại theo điều kiện | Thường vẫn cần quản lý như dữ liệu cá nhân; không đồng nhất với ẩn danh. |
| **Legal hold / preservation hold** | Tạm dừng xóa theo căn cứ và thẩm quyền phù hợp | Ai ban hành, đối tượng nào, ngày hiệu lực, khi nào được dỡ? |
| **Evidence preservation** | Bảo vệ hiện vật phục vụ audit/điều tra trước việc sửa hoặc xóa trái phép | Có nguồn gốc, hash, quyền, lịch sử truy cập và thời gian thu thập? |

**Lưu trữ lâu dài không đồng nghĩa bất biến tuyệt đối.** Kho lưu trữ có chế độ bất biến hoặc WORM có thể giúp chống sửa/xóa trái phép trong thời gian cần bảo vệ, nhưng phải thiết kế phù hợp với yêu cầu xóa hợp lệ, thời gian giữ và khả năng có legal hold. Không nên tự động bật giữ vĩnh viễn để giải quyết bài toán audit.

**Xóa một dòng database cũng không chứng minh mọi bản sao đã biến mất.** Dữ liệu có thể còn trong cache, search index, data warehouse, object storage, backup, log, hệ thống phân tích và dịch vụ bên thứ ba.

## 3. Chính sách retention phải trả lời những câu hỏi nào?

Một chính sách đủ khả năng thực thi nên xác định ít nhất:

| Thành phần | Nội dung bắt buộc làm rõ | Ví dụ câu hỏi |
| --- | --- | --- |
| **Phạm vi** | Hệ thống, môi trường, loại dữ liệu, đối tượng lưu trữ và bên xử lý | Áp dụng cho production, staging, bản xuất CSV hay toàn bộ backup? |
| **Mục đích/căn cứ** | Lý do lưu giữ về nghiệp vụ, bảo mật, hợp đồng và nghĩa vụ áp dụng | Vì sao cần giữ log này, ai đã phê duyệt? |
| **Phân loại dữ liệu** | Độ nhạy cảm, dữ liệu cá nhân, dữ liệu xác thực, dữ liệu mật | Có token, thông tin tài chính hay dữ liệu định danh không? |
| **Điểm bắt đầu tính thời gian** | Event tạo, kết thúc hợp đồng, đóng tài khoản, hoàn thành giao dịch hoặc kết thúc vụ việc | Thời điểm tạo file có khác thời điểm hoàn tất giao dịch? |
| **Thời hạn và điều kiện** | Khoảng thời gian, hạn tối thiểu/tối đa nếu có, ngoại lệ, version quy tắc | “180 ngày” là ngày lịch, 180×24 giờ hay sáu tháng? |
| **Hành động khi đến hạn** | Xóa, chuyển archive, ẩn danh, khóa xử lý hoặc review trước xóa | Khi legal hold tồn tại, job phải làm gì? |
| **Địa điểm và bản sao** | Database, file, cache, queue, backup, disaster-recovery copy, đối tác | Ai chịu trách nhiệm với bản sao ở data warehouse? |
| **Bảo vệ khi còn lưu** | Mã hóa, quyền truy cập, phân tách nhiệm vụ, log truy cập | Ai đọc, sửa, trích xuất hoặc thay retention policy được? |
| **Kiểm chứng** | Test, giám sát, kết quả job, đối chiếu record và bằng chứng xóa | Làm sao biết bản hết hạn đã được xử lý hết? |
| **Vai trò và phê duyệt** | Data owner, risk owner, Developer, Ops, Security, Legal/Privacy, audit | Ai quyết định thời hạn; ai được tạo/dỡ legal hold? |
| **Review và thay đổi** | Trigger đánh giá lại, ngày review, audit, ngoại lệ có thời hạn | Nếu có quy định mới hoặc thay đổi hệ thống thì xử lý dữ liệu cũ ra sao? |

Không có một thời hạn “chuẩn bảo mật” dùng chung cho mọi dữ liệu và quốc gia. Các ví dụ số ngày trong bài chỉ minh họa thiết kế kỹ thuật, **không phải tư vấn pháp lý hay thời hạn bắt buộc**. Thời hạn thực tế cần được các vai trò có thẩm quyền xác định dựa trên nghĩa vụ áp dụng và rủi ro.

## 4. Xây dựng bảng retention schedule theo loại dữ liệu

Bắt đầu từ **data inventory** có thể đối chiếu với thực tế, không chỉ từ sơ đồ cơ sở dữ liệu. Inventory cần có data owner, data processor, mục đích, luồng thu thập, nơi sao chép, người được truy cập và trường hợp xóa.

Bảng dưới đây là **ví dụ đào tạo**. Những thời hạn mang tính giả định, phải được thay bằng chính sách thực của tổ chức.

| Loại dữ liệu | Trigger bắt đầu tính hạn | Thời hạn minh họa | Hành động dự kiến | Những điều cần bảo vệ |
| --- | --- | --- | --- | --- |
| CSV xuất báo cáo tạm | Khi file được tạo hoàn chỉnh | **7 ngày** | Hết hiệu lực URL và xóa file theo quy trình | Quyền tải, dữ liệu nhạy cảm, bản sao trong object storage |
| Security authentication event | Khi sự kiện được ghi nhận và lưu thành công | **180 ngày** | Xóa hoặc xử lý theo quy tắc đã duyệt | Tính toàn vẹn và khả năng tra cứu trong thời gian cần điều tra |
| Phê duyệt thay đổi hệ thống | Khi change record được đóng | **365 ngày** | Xem xét hết hạn, xử lý nếu không có hold | Bằng chứng ai phê duyệt, phiên bản, thời điểm |
| Hồ sơ người dùng đã đóng | Khi quá trình đóng tài khoản hoàn tất | **30 ngày** cho phần có thể xóa sớm | Xóa/ẩn danh theo phân loại và nghĩa vụ liên quan | Phân biệt dữ liệu cần giữ theo luật/hợp đồng với dữ liệu không cần giữ |
| Backup ứng dụng | Khi backup hoàn tất và được xác minh | Theo **backup/DR policy riêng** | Hết hạn vòng backup, hủy bản sao theo thiết kế | RPO/RTO, bảo vệ bản sao, kiểm tra restore và yêu cầu hold |

Một bản ghi có thể thuộc **nhiều nhóm** hoặc **nhiều mục đích**. Ví dụ thông tin người nhận thanh toán vừa là dữ liệu cá nhân, vừa xuất hiện trong bản ghi giao dịch có nghĩa vụ lưu. Không thể chỉ áp dụng “xóa mọi dữ liệu người dùng sau 30 ngày” mà bỏ qua yêu cầu khác. Ngược lại, không nên viện dẫn một nghĩa vụ lưu hồ sơ giao dịch để giữ **mọi dữ liệu phân tích hoặc file tạm** vô thời hạn.

### Xác định đúng sự kiện bắt đầu

Chính sách “xóa bảy ngày sau khi tạo” cần nêu rõ:
- Dùng `createdAt`, `completedAt` hay thời điểm đóng tài khoản?
- Giá trị timestamp được phát sinh bởi hệ thống có kiểm soát hay do client tự cung cấp?
- Nếu job thất bại trước khi hoàn tất, file một phần có được dọn không?
- Nếu file được tải lại, hạn có được gia hạn không? Ai cho phép?
- Chính sách mới có tác động hồi tố lên dữ liệu đã tồn tại không?
- Khi chuyển vùng giờ hoặc dùng “tháng”, cách tính mốc hạn có còn nhất quán không?

Thực hành phổ biến là dùng **UTC/`Instant` cho các thời điểm**, đồng thời mô tả rõ ý nghĩa “ngày lịch”, “tháng” hoặc “ngày làm việc” nếu chính sách sử dụng các đơn vị đó. Không tự đổi “6 tháng” thành 180 ngày nếu quy định yêu cầu tính theo tháng lịch.

## 5. Cân bằng hai nhóm rủi ro: giữ quá lâu và xóa quá sớm

### 5.1. Giữ dữ liệu quá thời hạn

- Dữ liệu cá nhân hoặc nhạy cảm còn ở một môi trường không cần thiết, tăng **exposure** nếu tài khoản, secret hoặc hệ thống lưu trữ bị chiếm.
- Các bản sao không kiểm soát ở object storage, cache, backup, dữ liệu phân tích hoặc vendor trở thành **shadow data** không có owner.
- Log chứa token, password hoặc payload nhạy cảm làm tăng rủi ro nghiêm trọng ngay cả khi chỉ dự định phục vụ điều tra.
- Quyền truy cập vào kho archive rộng hơn production, dẫn đến “chuyển vào archive” nhưng thực chất làm giảm bảo vệ.
- Dữ liệu giữ ngoài mục đích hoặc quá giới hạn đã được duyệt có thể tạo **nghĩa vụ và rủi ro quyền riêng tư**.

### 5.2. Xóa dữ liệu quá sớm

- Không đủ audit trail để xác minh một thay đổi quyền IAM, giao dịch hoặc hoạt động vận hành đã được thực hiện đúng chính sách.
- Mất dữ liệu cần cho kiểm toán, điều tra sự cố, giải quyết tranh chấp hoặc nghĩa vụ được áp dụng.
- Backup/restore không đáp ứng mục tiêu phục hồi đã thống nhất; hệ thống phát hiện ransomware muộn hơn chu kỳ backup khả dụng.
- Việc đối chiếu sự kiện giữa nhiều dịch vụ thất bại do một nguồn log đã bị xóa, làm đứt **chain of evidence**.
- Những lần sửa lỗi hoặc release không còn bằng chứng để kiểm tra lại claim về security control trong kỳ đánh giá.

Vì vậy, **retention là bài toán tối ưu có ràng buộc**, không phải mục tiêu “càng ngắn càng tốt” hoặc “càng dài càng chắc”.

### Hai risk scenario minh họa

| Risk ID | Tình huống | Mục tiêu bị ảnh hưởng | Hành động kiểm soát |
| --- | --- | --- | --- |
| RISK-RET-01 | File CSV tạm chứa thông tin khách hàng tồn tại quá thời hạn và URL được chia sẻ ngoài quyền | Bí mật, quyền riêng tư | TTL có kiểm chứng, quyền tải, purge job, kiểm tra bản sao |
| RISK-RET-02 | Authentication log được xóa trước hạn khi hệ thống đang điều tra truy cập trái phép | Trách nhiệm giải trình, phát hiện, chống chối bỏ ở phạm vi chứng cứ | Retention rule, bảo quản bằng chứng, hold có phê duyệt, test truy xuất |

Hai rủi ro có thể cùng tồn tại trong một hệ thống. Một quy định giữ log lâu không phải lý do lưu toàn bộ payload giao dịch trong log; có thể giữ **metadata cần thiết, hạn chế dữ liệu nhạy cảm và bảo vệ chuỗi bằng chứng**.

## 6. Khi nhiều quy tắc áp dụng cùng một dữ liệu

Một record có thể nằm trong phạm vi của chính sách bảo mật, nghiệp vụ, hợp đồng, quy định pháp lý và yêu cầu điều tra. Không nên tự động chọn **thời hạn dài nhất** hoặc **ngắn nhất** mà chưa kiểm tra mục đích và tính hợp lệ của việc lưu tiếp.

Quy trình ra quyết định:

1. Xác định **dữ liệu, các mục đích xử lý** và mọi bản sao nằm trong phạm vi.
2. Liệt kê quy tắc áp dụng: hạn tối thiểu, giới hạn tối đa, sự kiện khởi đầu, quyền xóa và nghĩa vụ lưu.
3. Kiểm tra **xung đột giữa nghĩa vụ**. Nếu có xung đột hoặc điều kiện pháp lý không rõ, chuyển người phụ trách Legal/Privacy và chủ sở hữu dữ liệu theo quy trình.
4. Ghi nhận quyết định có căn cứ, phiên bản quy tắc, người phê duyệt, phạm vi và ngày đánh giá lại.
5. Thiết kế **legal/preservation hold** chỉ cho những dữ liệu liên quan, có lý do, người ra quyết định, thời điểm và quy trình dỡ.
6. Khi hold được dỡ, **đánh giá lại điều kiện hiện hành** và xử lý bản ghi đã hết hạn; không mặc nhiên giữ vĩnh viễn vì từng có hold.

### Ví dụ thứ tự kiểm tra một bản ghi

~~~mermaid
flowchart TD
    A["Bản ghi đến thời điểm đánh giá"] --> B["Xác định policy version, loại dữ liệu và mục đích"]
    B --> C{"Có hold hợp lệ, còn hiệu lực?"}
    C -- "Có" --> H["Giữ trong phạm vi hold, hạn chế truy cập và review"]
    C -- "Không" --> D{"Quy tắc được xác định đầy đủ, không xung đột?"}
    D -- "Không" --> R["Đưa vào hàng chờ review, không xóa mù"]
    D -- "Có" --> E{"Đã đến hạn xử lý?"}
    E -- "Chưa" --> K["Giữ và bảo vệ theo chính sách"]
    E -- "Rồi" --> P["Tạo ứng viên purge/archival theo hành động quy định"]
    P --> V["Kiểm tra lại trạng thái, thực thi có kiểm soát"]
    V --> Q["Xác minh kết quả, lưu evidence và xử lý lỗi"]
    H --> B
~~~

**Hold không tương đương vô thời hạn.** Việc tạo, gia hạn, thay đổi phạm vi và dỡ hold phải có người được ủy quyền, lịch sử và kiểm soát truy cập. Trong thiết kế kỹ thuật, việc **đánh giá điều kiện xóa và thao tác xóa** cần chống race condition: hold có thể được ban hành sau lúc job lấy danh sách ứng viên nhưng trước lúc job thực hiện xóa.

## 7. Kiến trúc kỹ thuật cho retention trong hệ thống nhiều dịch vụ

Một hệ thống phân tán có thể lưu cùng dữ liệu tại database, cache, search index, storage, event log, data lake, backup và hệ thống của đối tác. Chính sách phải theo **dòng dữ liệu và nơi lưu**, không chỉ theo một bảng.

~~~mermaid
flowchart LR
    SRC["Nguồn dữ liệu / nghiệp vụ"] --> META["Metadata: loại dữ liệu, owner, policy version, mốc hạn"]
    META --> RULE["Retention rules + hold registry"]
    RULE --> SEL["Bộ chọn ứng viên đã hết hạn"]
    SEL --> EXEC["Purge / archive executor"]
    EXEC --> DB[("Database / Storage / Cache / Search")]
    EXEC --> AUD["Audit event tối thiểu, không giữ payload đã xóa"]
    DB --> VERIFY["Đối chiếu kết quả, coverage và lỗi"]
    AUD --> VERIFY
    VERIFY --> ASS["Evidence register / assurance review"]
    HOLD["Legal / preservation hold có phê duyệt"] --> RULE
    OPS["Monitoring, retry, change management"] --> EXEC
~~~

### Những yêu cầu triển khai quan trọng

**1. Metadata đáng tin:** mỗi đối tượng cần có loại dữ liệu, retention rule ID/version, sự kiện bắt đầu tính hạn, thời điểm hết hạn dự kiến và link tới hold nếu có. Metadata phải được kiểm soát quyền và không phụ thuộc input client tùy ý.

**2. Tách hạn khỏi hành động:** `expiresAt` hoặc TTL biểu thị điều kiện; một job đã chạy, kết quả purge và verification mới giúp chứng minh việc xử lý. “Đã đến hạn” khác với “đã xóa”.

**3. Thiết kế an toàn khi chạy lại:** job có thể retry sau timeout, mất kết nối hoặc failover. Hành động xóa nên **idempotent** trong phạm vi thích hợp: chạy lại không gây xóa nhầm bản ghi khác hoặc làm lệch lịch sử.

**4. Chống xung đột:** trước khi xóa cần kiểm tra lại trạng thái hold và rule, dùng giao dịch/khóa hoặc cơ chế đồng bộ phù hợp với storage. Không dựa vào snapshot cũ nếu trạng thái có thể thay đổi.

**5. Giới hạn batch và ảnh hưởng hệ thống:** purge theo lô, có rate limit, tránh lock lớn, có monitoring backlog và phương án xử lý khi storage API trả lỗi. Không đưa việc xóa vào request người dùng nếu có thể gây timeout hoặc làm giảm tính sẵn sàng.

**6. Bản sao và phụ thuộc:** xóa tại database không đồng nghĩa xóa tại search, cache, data lake hoặc object storage. Sử dụng sự kiện xóa/đồng bộ có kiểm tra, danh sách nơi nhận, retry và đối soát khi cần.

**7. Quyền và bí mật:** tài khoản purge có quyền vừa đủ cho phạm vi tài sản; quyền thay đổi retention rule và quyền tạo hold được phân tách theo chính sách. Giám sát thao tác bất thường như thay hạn lưu hàng loạt hoặc vô hiệu hóa job.

**8. Audit evidence:** ghi nhận ID/batch, phạm vi, thời điểm, phương pháp, kết quả, số lượng đã xử lý và số lượng bị giữ hoặc lỗi. Không lưu lại toàn bộ nội dung nhạy cảm trong “log xóa” khiến chính log trở thành bản sao lưu không được kiểm soát.

### Lưu ý về backup, snapshot và bản sao bất biến

Một yêu cầu xóa có thể cần được thực thi khác nhau với dữ liệu sống và backup:

- **Bản dữ liệu đang hoạt động:** có thể xóa theo từng đối tượng khi đến hạn.
- **Backup/snapshot:** thường có chu kỳ lưu giữ và hủy theo lô; cần tài liệu về **mức trễ xóa, quyền truy cập và rủi ro phục hồi lại dữ liệu đã xóa**.
- **Bản sao có hold:** chỉ giữ đúng phạm vi và thời gian theo quyết định có hiệu lực.
- **Bản sao đối tác:** cần cơ chế thông báo/đối soát và trách nhiệm theo hợp đồng, phạm vi hệ thống liên quan.
- **Bản ghi bất biến phục vụ audit:** thời hạn và cơ chế hủy/đóng kỳ phải được thiết kế phù hợp với yêu cầu bảo quản, không hứa xóa tức thời nếu hạ tầng không hỗ trợ.

Nếu restore một backup cũ, dữ liệu đã hết hạn hoặc đã được xóa ở production **có thể xuất hiện lại**. Quy trình phục hồi cần có bước áp dụng lại quy tắc retention/xóa đã ghi nhận, đồng thời bảo vệ bằng chứng phục vụ việc kiểm tra kết quả.

## 8. Mẫu chính sách retention có thể quản trị

Mẫu YAML sau là **đặc tả minh họa** để người học hiểu cách định nghĩa rule. Nó **không tự chạy** trong Spring Boot, không xác nhận một thời hạn có giá trị pháp lý, và cần được review trước khi áp dụng.

~~~yaml
policy_id: SEC-RET-001
version: 1
status: approved
service: payment-report-service
owner: "<DATA_OWNER>"
risk_owner: "<RISK_OWNER>"
approved_by: "<AUTHORIZED_APPROVER>"
effective_at: "<ISO_8601_UTC>"
review_due: "<REVIEW_DATE>"
scope:
  environments: [production]
  regions: ["<APPROVED_REGION>"]
  data_stores: [database, object-storage, security-event-store]
rules:
  - rule_id: RET-CSV-01
    data_class: temporary-csv-export
    purpose: "Cung cấp file đã được xuất cho người có quyền"
    start_event: export-completed
    example_retention_days: 7
    action: purge
    includes_copies: [object-storage, cache, signed-url-records]
    hold_check_required: true
    verify: "Expired objects and links are not retrievable"
  - rule_id: RET-AUDIT-01
    data_class: authentication-security-events
    purpose: "Truy vết và điều tra sự kiện bảo mật"
    start_event: event-persisted
    example_retention_days: 180
    action: controlled-purge-after-retention
    includes_copies: [security-event-store, archive]
    hold_check_required: true
    verify: "Event retained while required; lifecycle end verified"
exceptions:
  legal_hold_registry: "<APPROVED_HOLD_REGISTRY>"
  conflict_escalation_owner: "<LEGAL_PRIVACY_AND_DATA_OWNER>"
controls:
  access_review_ref: "<ACCESS_REVIEW_CONTROL>"
  integrity_check_ref: "<EVIDENCE_INTEGRITY_CONTROL>"
  backup_lifecycle_ref: "<BACKUP_POLICY_ID>"
  monitoring_ref: "<PURGE_MONITORING_CONTROL>"
evidence:
  implementation_ref: "<CONFIG_OR_COMMIT>"
  test_ref: "<TEST_RUN_ID>"
  production_validation_ref: "<RUNTIME_CHECK>"
limitations: "<UNTESTED_STORES_AND_KNOWN_GAPS>"
~~~

**Ví dụ 7 và 180 ngày ở trên là giả định cho bài học**, không phải khuyến nghị áp dụng cho mọi hệ thống. Trong triển khai thật cần thay trường `example_retention_days` bằng quy tắc đã được phê duyệt, gắn nguồn căn cứ và cơ chế versioning. Với dữ liệu tồn tại trước khi có quy tắc, cần chỉ rõ chính sách migration hoặc xử lý riêng.

### Quản trị version chính sách

Khi một chính sách đổi từ “90 ngày” thành “30 ngày”, không chỉ cập nhật một số trong code:

1. Xác định những loại bản ghi/bản sao nào nằm trong phạm vi thay đổi.
2. Kiểm tra căn cứ, nghĩa vụ và đối tượng đã bị/đang có hold.
3. Quy định quy tắc mới áp dụng từ ngày nào, có hồi tố không và cách xử lý dữ liệu cũ.
4. Đánh giá tác động tới audit, điều tra, khả năng khôi phục và quyền riêng tư.
5. Review/approve, kiểm thử ở môi trường phù hợp, triển khai theo change management.
6. Đối chiếu hiệu lực tại runtime, quan sát job sau thay đổi và lưu bằng chứng.

**Không để một Developer tự rút ngắn retention của audit log để giải phóng dung lượng mà không qua chủ sở hữu và phê duyệt cần thiết.** Cũng không cho phép thay đổi “giữ vĩnh viễn” như một biện pháp chữa lỗi job bị xóa nhầm.

## 9. Ví dụ Java 17: xác định ứng viên đến hạn xử lý

Mã dưới đây **chỉ quyết định bản ghi có phải ứng viên để đưa sang bước xử lý hay không**. Nó không tự xóa dữ liệu, không thay thế authorization/legal hold registry, và không nên coi là engine retention production hoàn chỉnh.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class RetentionEligibility {
    public enum Outcome {
        RETAIN,
        DELETE_CANDIDATE,
        MANUAL_REVIEW
    }

    public record Record(
            String id,
            Instant expiresAt,
            boolean preservationHold) {}

    public static Outcome evaluate(Record record, Clock clock) {
        Objects.requireNonNull(record, "record");
        Objects.requireNonNull(clock, "clock");

        // Hold hợp lệ phải được xác định bằng registry có kiểm soát.
        if (record.preservationHold()) {
            return Outcome.RETAIN;
        }

        // Thiếu hạn lưu: không xóa theo phỏng đoán.
        if (record.expiresAt() == null) {
            return Outcome.MANUAL_REVIEW;
        }

        Instant now = clock.instant();
        if (!now.isBefore(record.expiresAt())) {
            return Outcome.DELETE_CANDIDATE;
        }
        return Outcome.RETAIN;
    }
}
~~~

Một bài kiểm thử với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class RetentionEligibilityTest {
    private final Clock fixedClock = Clock.fixed(
            Instant.parse("2026-11-28T00:00:00Z"), ZoneOffset.UTC);

    @Test
    void expirationBoundaryProducesCandidate() {
        var record = new RetentionEligibility.Record(
                "csv-01", Instant.parse("2026-11-28T00:00:00Z"), false);
        assertEquals(RetentionEligibility.Outcome.DELETE_CANDIDATE,
                RetentionEligibility.evaluate(record, fixedClock));
    }

    @Test
    void validHoldPreventsCandidateSelection() {
        var record = new RetentionEligibility.Record(
                "csv-01", Instant.parse("2026-11-20T00:00:00Z"), true);
        assertEquals(RetentionEligibility.Outcome.RETAIN,
                RetentionEligibility.evaluate(record, fixedClock));
    }

    @Test
    void missingExpiryRequiresReviewInsteadOfBlindDeletion() {
        var record = new RetentionEligibility.Record("csv-01", null, false);
        assertEquals(RetentionEligibility.Outcome.MANUAL_REVIEW,
                RetentionEligibility.evaluate(record, fixedClock));
    }

    @Test
    void unexpiredRecordIsRetained() {
        var record = new RetentionEligibility.Record(
                "csv-01", Instant.parse("2026-12-01T00:00:00Z"), false);
        assertEquals(RetentionEligibility.Outcome.RETAIN,
                RetentionEligibility.evaluate(record, fixedClock));
    }
}
~~~

Trong production, `preservationHold` không nên là một cờ tin từ client hoặc bản sao không nhất quán. Trước thao tác xóa không thể đảo ngược, hệ thống cần **tra lại hold và policy hiện hành trong cơ chế đồng bộ thích hợp**, kiểm tra quyền và phạm vi, rồi bảo đảm không có thay đổi hợp lệ chen vào giữa bước kiểm tra và thực thi.

`DELETE_CANDIDATE` cũng không có nghĩa “đã xóa”: job tiếp theo phải thực hiện xử lý theo data store, ghi nhận kết quả, retry nếu lỗi và kiểm tra bản sao. Đối với đối tượng có thời điểm phát sinh theo **tháng lịch hoặc ngày làm việc**, đừng trực tiếp dùng `Duration.ofDays(30)` nếu rule nghiệp vụ không quy định như vậy.

## 10. Thiết kế security controls và các tiêu chí kiểm chứng

Một policy có thể được xem là **security requirement** khi đủ rõ để quan sát hành vi. Dưới đây là bộ yêu cầu minh họa cho CSV xuất tạm và security logs.

| Requirement ID | Yêu cầu có thể kiểm tra | Control cần thiết | Evidence / phép kiểm tra |
| --- | --- | --- | --- |
| **RET-REQ-01** | Mọi file CSV tạm phải có rule ID, thời điểm phát sinh và thời điểm hết hạn theo rule đang áp dụng | Metadata và version policy được quản lý | Kiểm tra object metadata, bảng rule, build/config và mẫu bản ghi |
| **RET-REQ-02** | File hết hạn không có hold phải bị xử lý trong cửa sổ vận hành được phê duyệt | Scheduler/queue/batch purge, retry và giám sát backlog | Job run, event ID, đối chiếu object trước/sau, báo lỗi |
| **RET-REQ-03** | File trong hold hợp lệ không được xóa khi hold còn hiệu lực | Hold registry, kiểm tra quyền và điều kiện trước xóa | Test bật/dỡ hold, test race condition, log thay đổi hold |
| **RET-REQ-04** | API và storage URL không cho đọc file đã hết quyền hoặc hết hạn | Authorization, expiry enforcement, object lifecycle | Negative test HTTP và truy cập storage thực trong phạm vi test |
| **RET-REQ-05** | Security log phải còn truy xuất/kiểm tra toàn vẹn trong kỳ lưu theo chính sách | Retention rule, quyền, integrity verification, backup phù hợp | Truy vấn log ở thời điểm biên, kiểm tra quyền, kết quả đối chiếu |
| **RET-REQ-06** | Bản sao trong cache, search, archive, backup được xử lý theo lifecycle đã tài liệu hóa | Copy inventory, retention per store, reconciliation | Coverage report, API kết quả, backup expiry/restore test |
| **RET-REQ-07** | Thay đổi rule phải qua review và để lại lịch sử | Versioning, change approval, phân tách nhiệm vụ | PR/change ID, người duyệt, deployment và audit trail |
| **RET-REQ-08** | Việc thiếu job/pipeline hoặc backlog quá ngưỡng phải có tín hiệu phát hiện | Monitoring, cảnh báo, owner, runbook | Event thử, alert delivery, incident/finding nếu thất bại |

**Tiêu chí cần đo được**: thay vì viết “xóa kịp thời”, chính sách vận hành cần nêu rõ **độ trễ purge tối đa được chấp nhận, cơ chế báo lỗi, ngưỡng backlog và người chịu trách nhiệm**. Giá trị cụ thể do tổ chức phê duyệt theo mức rủi ro và năng lực hệ thống.

### Những ca kiểm thử không được bỏ qua

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Bản ghi chưa đến hạn | Không bị xóa hoặc mất quyền truy cập trái thiết kế |
| Đúng thời điểm hết hạn | Trở thành ứng viên theo cách tính thời gian đã quy định |
| Có hold hợp lệ | Không xóa; ghi nhận lý do giữ và owner của hold |
| Hold được tạo giữa lúc chọn và lúc thực thi | Không xóa nếu hold đã có hiệu lực tại điểm kiểm tra quyết định theo thiết kế |
| Hold được dỡ sau khi đã quá hạn | Được đánh giá lại, không giữ vô thời hạn vì trạng thái cũ |
| Thiếu hoặc sai metadata expiry | Không xóa mù; tạo finding/manual review, theo dõi xử lý |
| Job chạy trùng hoặc retry | Không xóa sai đối tượng, không mất log kết quả |
| Storage API bị timeout/partial failure | Có ghi nhận lỗi, retry/reconciliation, không báo thành công giả |
| File đã xóa khỏi DB nhưng còn ở storage | Phát hiện sai lệch và tiếp tục xử lý đúng phạm vi |
| Log audit chưa đến hạn nhưng purge rule bị thay | Có kiểm tra rule/version và bảo vệ dữ liệu cần lưu |
| Restore backup có bản ghi đã hết hạn | Có bước kiểm tra và áp dụng lifecycle hiện hành trước khi dữ liệu được sử dụng bình thường |
| Thay đổi policy version | Bản ghi cũ/mới được xử lý theo quy tắc chuyển đổi đã duyệt |

### Test chứng minh điều gì?

- **Unit test** như ví dụ Java chứng minh cách ra quyết định theo những input đã cho.
- **Integration test** với database/object storage thử cơ chế xóa, backup/hold và handling lỗi.
- **End-to-end test** chứng minh kết quả với workflow và danh tính thật trong môi trường thử.
- **Runtime validation** đối chiếu job, cấu hình, permissions và dữ liệu đang tồn tại tại môi trường cần kết luận.
- **Audit/review** đánh giá phạm vi, căn cứ, ngoại lệ, tính toàn vẹn và những đường dữ liệu chưa bao phủ.

Không dùng test `RET-REQ-01` đạt để suy ra `RET-REQ-06` đã đạt. Có metadata expiry không tự chứng minh bản sao ở storage, backup và đối tác đã được xử lý.

## 11. Bảo vệ bằng chứng bảo mật trong chính sách retention

Bản thân **security evidence** cũng là dữ liệu phải được phân loại và có retention rule. Nó có thể bao gồm:

- Lịch sử thay đổi IAM, network và cấu hình production.
- Security event logs, intrusion detection, kết quả quét và cảnh báo.
- PR review, CI test results, bằng chứng deployment, artifact digest.
- Hồ sơ phê duyệt, quyết định chấp nhận rủi ro, finding, remediation và retest.
- Incident timeline, hiện vật điều tra và lịch sử chain of custody.

Cần xác định **bằng chứng nào phải giữ**, cho **claim nào**, **kỳ đánh giá nào** và **có thể xác minh lại bằng cách nào**. Không giữ vô hạn tất cả raw logs chỉ vì cần audit; có thể phân tầng lưu trữ, giảm dữ liệu thừa và giữ các hiện vật cần thiết ở dạng được bảo vệ.

### Chống sửa/xóa trái phép và khả năng kiểm chứng

Các cơ chế có thể dùng tùy rủi ro:

- Phân quyền đọc, ghi, thay đổi rule và xóa độc lập; giảm quyền ứng dụng trên kho bằng chứng.
- Cơ chế phát hiện sửa đổi: hash, chữ ký, chuỗi hash có neo tin cậy hoặc lưu trữ bất biến được cấu hình phù hợp.
- Ghi lịch sử lấy mẫu, export, chuyển giao, review và kiểm tra toàn vẹn khi cần cho chain of custody.
- Đồng bộ thời gian đáng tin phù hợp, ghi nhận nguồn sự kiện, môi trường và ID giao dịch.
- Kiểm tra việc truy xuất bằng chứng **trong kỳ retention**, kể cả khi hệ thống nguồn đã được nâng cấp hoặc thay thế.

**Hash đơn lẻ không xác định ai đã tạo dữ liệu** và không ngăn người có quyền viết lại cả file lẫn hash. WORM không tự chứng minh sự kiện được ghi là đúng. Những cơ chế này là từng lớp của lập luận assurance, không phải bảo đảm tuyệt đối.

### Bằng chứng tối thiểu về việc xử lý đúng hạn

| Claim | Bằng chứng được xem xét | Giới hạn cần nêu |
| --- | --- | --- |
| “CSV quá hạn đã được xử lý” | Kết quả batch, truy vấn/kiểm tra object storage, link hết hạn, đối soát bản sao | Backup hoặc hệ thống đích có thể có vòng đời khác |
| “Log được giữ đủ kỳ” | Kiểm tra record tại ranh giới kỳ, cấu hình retention/immutability, quyền truy xuất | Một lần sample không chứng minh mọi nguồn đều đầy đủ |
| “Hold được tôn trọng” | Hold record có phê duyệt, thử xử lý record đang hold, nhật ký thay đổi | Cần kiểm tra race condition và copy ngoài phạm vi |
| “Job purge liên tục hoạt động” | Metrics backlog, các lần chạy, cảnh báo mất job, bài test failure/retry | Dashboard xanh không chứng minh không bỏ sót data store |
| “Sau khắc phục control đã đạt” | Finding, PR, test, deployment ID, runtime validation và reviewer | Claim chỉ đúng với phạm vi/môi trường đã xác minh |

## 12. Hồ sơ evidence và chuỗi truy vết cho security assurance

Ví dụ xây dựng assurance case cho vấn đề file tạm tồn tại quá hạn:

| Thành phần | Minh họa |
| --- | --- |
| **RISK-RET-01** | File CSV chứa dữ liệu khách hàng quá hạn còn tải được từ storage. |
| **OBJ-CONF-01** | Giảm khả năng lộ dữ liệu không còn cần dùng và bảo đảm thực thi nghĩa vụ lưu giữ đã phê duyệt. |
| **REQ-RET-01** | File CSV hết hạn không có hold được xóa/khóa truy cập theo rule trong phạm vi áp dụng. |
| **CTRL-RET-01** | Policy engine, authorization tải, TTL, purge scheduler, copy inventory và monitoring. |
| **TEST-RET-01** | Test biên hạn, hold, xóa storage, access sau hết hạn, retry và restore. |
| **EV-RET-01** | Test run, rule version, object IDs đã làm sạch, job result, runtime policy snapshot. |
| **FIND-RET-01** | Phát hiện một bucket backup giữ file quá hạn ngoài phạm vi được mô tả. |
| **RETEST-RET-01** | Kiểm tra bản sửa và đối chiếu bucket/backup đúng môi trường sau triển khai. |

### Mẫu bản ghi đánh giá

Dưới đây là một **mẫu evidence register**, các giá trị trong dấu `<...>` phải được thay bằng thông tin có thật:

~~~yaml
evidence_id: EV-RET-001
claim_id: CLAIM-RET-01
risk_id: RISK-RET-01
policy_id: SEC-RET-001
policy_version: 1
requirement_ids: [RET-REQ-01, RET-REQ-02, RET-REQ-03, RET-REQ-06]
control_ids: [CTRL-RET-01]
service: payment-report-service
environment: production
asset_scope: "<OBJECT_STORE_BUCKET_AND_RELATED_COPIES>"
evaluation_period: "<START_END_UTC>"
change_id: "<APPROVED_CHANGE_ID>"
build_or_config_version: "<COMMIT_OR_CONFIG_REVISION>"
deployment_id: "<DEPLOYMENT_ID>"
test_run_id: "<CI_OR_CONTROLLED_RUNTIME_TEST>"
purge_job_id: "<BATCH_OR_WORKFLOW_ID>"
hold_registry_check: "<HOLD_STATUS_VERIFICATION>"
method: "Kiểm tra retention, hold và purge end-to-end"
result: "<PASS_FAIL_INCONCLUSIVE>"
collected_at: "<ISO_8601_UTC>"
reviewer: "<AUTHORIZED_REVIEWER>"
artifact_refs:
  - "<SANITIZED_TEST_REPORT>"
  - "<PURGE_EXECUTION_LOG>"
  - "<RUNTIME_STORAGE_RECONCILIATION>"
  - "<BACKUP_LIFECYCLE_EVIDENCE>"
limitations: "<UNTESTED_COPIES_AND_REMAINING_RISKS>"
next_review_trigger: "<CHANGE_INCIDENT_OR_DATE>"
~~~

Bản YAML này chỉ là **chỉ mục hiện vật**, không tự tạo ra bằng chứng. Người đánh giá phải kiểm tra được nguồn, tính toàn vẹn, thời điểm, version, phạm vi, kết quả thực tế và những giới hạn chưa được xử lý. Evidence metadata cũng cần retention riêng: nếu log của job xóa bị giữ vĩnh viễn và chứa nguyên payload, đó chính là một nguồn rủi ro cần quản lý.

## 13. Phân vai và thẩm quyền thực hiện

Retention liên quan cả bảo mật, nghiệp vụ và nghĩa vụ xử lý dữ liệu. Không nên giao mọi quyết định cho một scheduled job hoặc một người phát triển phần mềm.

| Vai trò | Trách nhiệm điển hình | Đầu ra |
| --- | --- | --- |
| **Data / Business Owner** | Xác định mục đích sử dụng, tài sản, mức quan trọng, quyết định nghiệp vụ và owner dữ liệu | Phân loại dữ liệu, phạm vi và yêu cầu retention |
| **Legal / Privacy / Compliance** | Giải thích nghĩa vụ áp dụng, quyền xóa, trường hợp hold và giải quyết xung đột cần thiết | Căn cứ/chính sách được review, quyết định hold |
| **Security / AppSec** | Phân tích rủi ro lưu quá lâu hoặc xóa quá sớm, kiểm tra security controls | Risk scenarios, tiêu chí bảo vệ và assessment |
| **Developer / Service Team** | Hiện thực metadata, lifecycle, purge logic, authorization và negative tests | Commit, review, test results và remediation |
| **Ops / SRE / Platform** | Vận hành scheduler, storage, backup, IAM, giám sát drift và restore | Job run, config, backup evidence và monitoring |
| **Risk Owner / Người có thẩm quyền** | Quyết định ngoại lệ và xử lý rủi ro tồn dư theo chính sách | Decision record, thời hạn, yêu cầu review |
| **Assessor / Audit** | Đối chiếu bằng chứng, phạm vi và kết luận độc lập khi được yêu cầu | Audit record, finding, verification report |

Tổ chức nên lập RACI cho từng hoạt động: ai **Responsible** xử lý, ai **Accountable** cuối cùng, ai được tham vấn và ai cần được thông báo. Người triển khai purge không tự động có quyền **định lại thời hạn**, **dỡ hold** hoặc **chấp nhận vi phạm**.

### Ngoại lệ retention

Một ngoại lệ nên có: phạm vi loại dữ liệu/tài sản, lý do, ảnh hưởng, người đề xuất, người có thẩm quyền phê duyệt, biện pháp bù trừ, ngày hết hạn và trigger review. **Ngoại lệ được chấp nhận không biến control không đạt thành đạt**; phải báo cáo trạng thái kỹ thuật thực tế và residual risk riêng.

## 14. Theo dõi liên tục và chỉ số vận hành

Một chương trình retention assurance cần được kích hoạt khi phát sinh sự kiện, không chỉ trước ngày audit.

| Trigger | Việc cần làm | Bằng chứng |
| --- | --- | --- |
| Thêm data class, API export hoặc tích hợp mới | Cập nhật data inventory, nguồn bản sao và retention rule | DFD, change record, owner, policy review |
| Thay đổi thời hạn hoặc trigger bắt đầu | Đánh giá tương thích dữ liệu cũ, hold và nghĩa vụ | Rule version, approval, test migration |
| Thêm storage/cache/backup/vendor | Đánh giá đường dữ liệu mới và cách xử lý khi đến hạn | Copy inventory, test purge/reconciliation |
| Job purge lỗi, backlog tăng hoặc alert mất | Phân loại rủi ro và phục hồi kiểm soát | Alert, incident, retry log, retest |
| Ban hành hoặc dỡ legal hold | Kiểm tra phạm vi, thời điểm và xung đột | Hold decision, registry change, validation |
| Restore từ backup cũ | Kiểm tra bản ghi đã hết hạn có bị phục hồi không | Restore drill, post-restore retention check |
| Phát hiện dữ liệu nhạy cảm trong log | Điều tra phơi lộ, che/giảm nội dung, thay đổi nguồn log | Finding, schema/log review, scan và retest |
| Thay đổi quy định/hợp đồng hoặc tổ chức | Review mục đích, hạn, owner và ngoại lệ | Policy review/sign-off và kế hoạch triển khai |

### Chỉ số tham khảo

- **Coverage:** tỷ lệ data store và loại dữ liệu quan trọng có owner và retention rule được phê duyệt.
- **Overdue population:** số lượng/kích thước đối tượng quá hạn chưa được xử lý trong cửa sổ cho phép, phân theo lý do (hold, lỗi, chưa xác định rule).
- **Purge success và retry:** tỷ lệ thực thi thành công kèm kiểm chứng thực tế, không chỉ HTTP 200 từ API storage.
- **Hold correctness:** số hold quá hạn chưa được review; số tình huống xóa sai đối tượng có hold trong bài test hoặc sự cố.
- **Backup lifecycle:** độ bao phủ backup có quy tắc và kết quả thử restore xử lý dữ liệu đã hết hạn.
- **Policy drift:** số khác biệt giữa rule được duyệt và cấu hình đang chạy.
- **Evidence readiness:** tỷ lệ control có test/evidence còn hiệu lực, số finding và ngoại lệ quá hạn.

Không tối ưu **“xóa càng nhiều càng tốt”**. Một tỷ lệ purge cao có thể che việc xóa dữ liệu chưa đủ hạn. Cần đo đồng thời **đúng đối tượng, đúng thời điểm, đúng phạm vi và giữ được dữ liệu cần giữ**.

## 15. Case study: CSV tạm, audit log và legal hold

### Bối cảnh

Dịch vụ `payment-report-service` viết bằng Java/Spring Boot tạo CSV nhạy cảm khi người dùng xuất báo cáo. Dự kiến file hết hạn sau **7 ngày** theo chính sách minh họa. Security event lưu trong hệ thống log tập trung để phục vụ điều tra. Một khách hàng thông báo nghi ngờ bị truy cập trái phép; nhóm điều tra yêu cầu giữ những log và dữ liệu liên quan tới một giao dịch đang xem xét.

Khi audit, nhóm đánh giá phát hiện:

- File CSV tạm đã hết hạn nhưng còn tồn tại trong bucket phụ vì job chỉ xóa bucket chính.
- Link tải vẫn dùng được trên một đường đi cũ; gateway mới không quản lý đường này.
- Một số log của sự kiện đang điều tra sắp đến kỳ purge.
- Registry legal hold chưa được liên kết với scheduled purge.
- Dashboard purge hiện “SUCCESS” nhưng không thống kê các bản sao bị bỏ sót.

### Phân tích rủi ro

| Finding | Hậu quả có thể xảy ra | Điều cần xác minh |
| --- | --- | --- |
| F-RET-01: bucket phụ giữ CSV quá hạn | Tăng bề mặt lộ dữ liệu ngoài hạn cần thiết | Inventory các bucket, object age, IAM, link và kết quả purge |
| F-RET-02: đường tải cũ còn hiệu lực | Truy cập được file hết hạn hoặc trái quyền | Runtime ingress, signed URL, test tải sau hết hạn |
| F-RET-03: log sắp bị xóa khi đang điều tra | Mất khả năng đối chiếu sự kiện trong vụ việc | Căn cứ và phạm vi hold, thời điểm hiệu lực, quyền ban hành |
| F-RET-04: purge không kiểm tra hold | Có thể xóa dữ liệu cần bảo quản | Test hold, concurrency, version rule và log job |
| F-RET-05: dashboard báo thành công không có đối soát | False assurance, finding tồn tại kéo dài | Reconciliation giữa danh sách nguồn và dữ liệu thực còn |

### Kế hoạch khắc phục

1. **Khoanh vùng và bảo vệ hiện vật:** đánh giá nguy cơ hiện tại, giới hạn truy cập bucket/link nếu cần; điều tra log theo quyền và quy trình cho phép. Đối với dữ liệu cần bảo toàn, xác minh hold hợp lệ trước khi xóa.
2. **Sửa data inventory:** thêm bucket phụ, đường tải cũ và mọi storage/backup liên quan; xác định owner của từng bản sao.
3. **Sửa control:** bổ sung purge/reconciliation ở bucket phụ; vô hiệu hóa đường tải cũ theo chính sách; liên kết hold registry với bước quyết định xóa trong cơ chế đồng bộ phù hợp.
4. **Viết negative tests:** file hết hạn không truy cập được; file chưa hết hạn vẫn tải hợp lệ; file đang hold được giữ; thiếu metadata dẫn đến review, không bị xóa mù.
5. **Kiểm tra production:** đối chiếu commit/build, cấu hình job, IAM, bucket policy, deployment và kết quả chạy trên môi trường thực; kiểm tra backup lifecycle riêng.
6. **Đánh giá bằng chứng và đóng finding:** assessor xác minh kết quả, lưu bằng chứng trước/sau, xác định còn dữ liệu nào ngoài phạm vi và residual risk cần quyết định.

**Không nên khắc phục bằng cách tắt toàn bộ purge vô thời hạn.** Cần thu hẹp hold đúng phạm vi và kiểm soát quyền, tránh biến một yêu cầu bảo quản chứng cứ thành lý do giữ mọi dữ liệu mãi mãi.

## 16. Bài tập thực hành

**Tình huống:** nền tảng thương mại điện tử có một service Java lưu thông tin đơn hàng, bản export CSV, security logs, cache Redis và backup. Nhóm sản phẩm muốn xóa tất cả dữ liệu tài khoản ngay khi người dùng đóng tài khoản. Nhóm điều tra muốn giữ tất cả log vô thời hạn. Nhóm vận hành đề xuất chỉ cần bật TTL của Redis và lifecycle rule cho storage.

Hãy trả lời:

1. Vì sao ba đề xuất trên **chưa đủ điều kiện** để trở thành chính sách retention đáng tin?
2. Hãy lập danh mục ít nhất **năm loại dữ liệu/bản sao**; với mỗi loại, ghi mục đích, owner, trigger bắt đầu hạn và phương án xử lý khi hết hạn. Không cần tự đặt một thời hạn mang tính pháp lý.
3. Viết **bốn yêu cầu có thể kiểm thử** để phân biệt lưu đủ hạn, xóa đúng hạn, tôn trọng hold và xử lý backup/restore.
4. Đề xuất test cho **race condition**: một legal hold được ban hành trong lúc purge job chuẩn bị xóa dữ liệu.
5. Nêu bộ bằng chứng tối thiểu để một auditor kết luận **file CSV tạm được xử lý đúng vòng đời** trong phạm vi production.
6. Phân công Developer, Ops/SRE, Security, Data Owner, Legal/Privacy và Risk Owner trong quá trình xử lý xung đột hoặc ngoại lệ.

### Hướng giải quyết

- **Không xóa tất cả theo một trigger:** hồ sơ giao dịch, dữ liệu cá nhân, log và bản xuất có thể có mục đích và ràng buộc khác nhau. Cần phân loại và xác định quy tắc áp dụng trước khi xử lý.
- **Không giữ toàn bộ log vô thời hạn:** mục đích và giới hạn lưu cần được review; log có thể chứa dữ liệu nhạy cảm và phải có quản lý quyền, che dữ liệu và ngày hủy theo chính sách.
- **Không chỉ dựa vào TTL:** Redis và storage không bao phủ database, search, backup, nhà cung cấp hoặc trường hợp hold; TTL cũng có thể không đồng nghĩa xóa tức thời.
- **Trường hợp hold:** job chọn ứng viên trước nhưng phải đối chiếu hold ở điểm quyết định xóa có kiểm soát; một test tích hợp nên chứng minh hold được ban hành đúng lúc ngăn hành động xóa không hợp lệ.
- **Evidence:** metadata đối tượng và version rule, test ở biên hạn, purge run có ID, kết quả đối soát storage, negative access test, backup lifecycle, bản ghi hold/reviewer và deployment reference.
- **Quyết định:** Data Owner cùng Legal/Privacy xác định căn cứ; Security phân tích rủi ro; Developer/Ops triển khai và vận hành; Risk Owner hoặc thẩm quyền phù hợp phê duyệt phần rủi ro tồn dư; audit đối chiếu độc lập theo nhiệm vụ.

## 17. Các lỗi thường gặp

| Nhận định sai | Vấn đề | Thực hành phù hợp |
| --- | --- | --- |
| “Có trường `expiresAt` nên data đã được xóa đúng hạn.” | Metadata không chứng minh thao tác xóa và bản sao | Xác minh job, storage, quyền truy cập và đối soát |
| “Chỉ cần xóa database row.” | Có thể còn cache, storage, search, backup hoặc vendor copy | Data flow inventory và lifecycle cho từng store |
| “Backup không cần retention vì chỉ dùng để restore.” | Backup cũng chứa dữ liệu, có quyền, thời hạn và rủi ro riêng | Backup policy, expiry, restore testing và kiểm tra sau restore |
| “Audit yêu cầu giữ tất cả log mãi mãi.” | Không có mục đích/giới hạn cụ thể, tăng exposure | Phân loại evidence, retention đã phê duyệt và kiểm tra toàn vẹn |
| “Có legal hold nên không bao giờ được xóa.” | Hold có phạm vi, thẩm quyền và điều kiện chấm dứt | Registry, review định kỳ, dỡ hold và đánh giá lại |
| “Thay YAML policy là runtime đổi ngay.” | Bản deploy, job config, object lifecycle và các nơi lưu có thể khác | Đối chiếu version, deployment, actual config và test |
| “Một job `SUCCESS` chứng minh mọi object hết hạn đã được xóa.” | Có thể bỏ sót bucket, partition, retry hoặc bản sao | Reconciliation và kiểm tra ngẫu nhiên có phạm vi |
| “Cho người vận hành tự rút ngắn thời hạn vì thiếu dung lượng.” | Có thể xóa mất chứng cứ hoặc dữ liệu phải lưu | Thay đổi có đánh giá tác động, approval và retest |
| “Giữ lại payload trong log xóa là cách làm bằng chứng tốt nhất.” | Tạo thêm bản sao dữ liệu nhạy cảm không quản lý | Lưu metadata, identifier phù hợp và proof không tái lưu toàn bộ nội dung |
| “Đã được chấp nhận ngoại lệ thì control đạt.” | Chấp nhận rủi ro không thay đổi trạng thái kỹ thuật | Báo rõ control fail/inconclusive, ngoại lệ và rủi ro còn lại |

## Ghi nhớ

- **Retention policy** quy định mục đích, phạm vi, thời hạn, điều kiện, cách xử lý, trách nhiệm và bằng chứng cho **toàn vòng đời dữ liệu**.
- Phải đồng thời kiểm soát rủi ro **giữ quá lâu** và **xóa quá sớm**; audit logs, CSV tạm, dữ liệu nghiệp vụ và backup không mặc nhiên có chung hạn.
- **Legal/preservation hold** chỉ có hiệu lực trong phạm vi được duyệt; thay đổi và dỡ hold cần được theo dõi, đặc biệt khi cạnh tranh với purge job.
- **TTL, metadata và dashboard xanh không đủ chứng minh đã xóa**; cần kiểm tra ở các bản sao, trên bản triển khai thật, với kết quả và giới hạn rõ.
- Security assurance liên kết **rủi ro → yêu cầu → control → test → evidence → audit/finding → khắc phục/retest**, kể cả với chính sách retention.
- Retention là **trách nhiệm phối hợp** của Data Owner, Legal/Privacy, Security, Developer, Ops, Risk Owner và Audit; thay đổi phải được đánh giá lại liên tục khi dữ liệu, nghĩa vụ, hệ thống và bằng chứng thay đổi.

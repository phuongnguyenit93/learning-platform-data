# Evidence chain: Xây dựng chuỗi bằng chứng có thể truy vết trong Security Assurance

Một bản chụp màn hình hiển thị “MFA enabled”, một báo cáo scanner ghi “0 critical findings” hoặc một dashboard màu xanh có thể tạo cảm giác hệ thống đang an toàn. Nhưng auditor vẫn phải hỏi: **bằng chứng này nói về hệ thống nào, trong kỳ nào, ai thu thập, từ nguồn nào, có đủ bao phủ mục tiêu kiểm soát, có bị chỉnh sửa và phép kiểm tra nào đưa đến kết luận?** Nếu không trả lời được, tài liệu có thể tồn tại mà mức bảo đảm vẫn thấp.

**Evidence chain** (chuỗi bằng chứng) trong security assurance là hệ thống liên kết có thể kiểm chứng giữa **mục tiêu bảo mật → yêu cầu/control → đối tượng và kỳ đánh giá → phương pháp kiểm tra → bằng chứng nguồn → kết quả đánh giá → phát hiện/rủi ro → khắc phục và tái kiểm tra**. Song song, một chuỗi khác bảo vệ **nguồn gốc, tính toàn vẹn và lịch sử xử lý** của từng artifact. Khi dùng bằng chứng trong điều tra có yêu cầu pháp chứng, phần lịch sử xử lý này có thể trở thành **chain of custody** chặt chẽ.

Bài học thuộc chương **Audit và evidence**, module **SECURITY_SECURITY_ASSURANCE**. Trọng tâm của module là chứng minh bằng dữ kiện rằng hệ thống đáp ứng mục tiêu bảo mật từ phân tích rủi ro, security controls, kiểm thử, audit đến khắc phục phát hiện, rồi duy trì assurance liên tục trong phát triển và vận hành. Vì vậy, một evidence chain tốt không đơn giản là kho lưu file: nó phải giúp người đánh giá **tái dựng được căn cứ dẫn đến một kết luận** và nhận biết rõ các giới hạn chưa được xác minh.

Sau bài học, người học có thể lập sơ đồ chuỗi truy vết, đặt tiêu chí chất lượng bằng chứng, thu thập và bảo vệ artifact đúng cách, thiết kế manifest/audit trail, kết luận PASS/FAIL/INCONCLUSIVE trên phạm vi xác định và xử lý thiếu sót của evidence chain.

## 1. Evidence chain là gì và khác gì với một tập tài liệu?

Hãy xét nhận định: **“Tài khoản quản trị production đều phải dùng MFA.”** Người triển khai đưa ra một ảnh chụp trang cấu hình IdP có dòng “MFA required”. Đây là một artifact hữu ích, nhưng chưa đủ để kết luận toàn bộ tài khoản quản trị đáp ứng chính sách:

- Chính sách áp dụng cho **tenant, ứng dụng, nhóm và loại identity** nào?
- Có tài khoản đặc quyền sử dụng token, API key hoặc federation khác đường xác thực không?
- Có tài khoản ngoại lệ, break-glass hay access policy loại trừ không?
- Config xuất vào thời điểm nào; có hiệu lực trong **toàn bộ kỳ đánh giá** không?
- Ảnh do ai chụp, từ môi trường thật hay môi trường thử, có thể đối chiếu bằng truy vấn nào?
- Người đánh giá đã thử hành vi đăng nhập hoặc kiểm tra effective policy chưa?

**Tập tài liệu** chỉ trả lời “có những file nào”. **Evidence chain** phải trả lời “file nào được tạo như thế nào, chứng minh điều gì, ai đã kiểm tra, kết luận nào hợp lệ và phần nào chưa được chứng minh”.

### Ba lớp của evidence chain

| Lớp | Câu hỏi trọng tâm | Ví dụ |
|---|---|---|
| **Traceability chain (chuỗi truy vết khẳng định)** | Điều kiện an toàn nào được yêu cầu, phép kiểm tra và bằng chứng nào hỗ trợ kết luận? | Mục tiêu hạn chế truy cập → control IAM → test quyền → log/config → PASS/FAIL. |
| **Provenance & integrity chain (chuỗi nguồn gốc/toàn vẹn)** | Artifact đến từ đâu, có được biến đổi không, ai có quyền truy cập/sửa và bản nào được xem xét? | Audit export → object ID → hash → manifest → audit trail → bản ghi duyệt. |
| **Chain of custody (chuỗi quản lý, bàn giao chứng cứ)** | Với chứng cứ cần xử lý theo yêu cầu điều tra/pháp lý, ai thu giữ, bàn giao, tiếp nhận, lưu giữ và phân tích ở từng thời điểm? | Disk image → biên bản thu thập → hash → niêm giữ → bàn giao → phân tích bản sao. |

Ba lớp có liên quan nhưng **không đồng nghĩa**. Không phải mỗi báo cáo kiểm tra control đều cần thủ tục pháp chứng đầy đủ. Ngược lại, khi dùng log/snapshot làm chứng cứ điều tra, chỉ có đường dẫn file hoặc một hash đơn lẻ chưa đủ để chứng minh toàn bộ chain of custody.

## 2. Mô hình từ claim đến verdict

Một chuỗi bảo đảm có thể mô hình hóa như một đồ thị, trong đó mỗi kết luận có đường dẫn đến tiêu chí và nguồn bằng chứng cụ thể.

~~~mermaid
flowchart TD
    O["Security objective / rủi ro cần kiểm soát"] --> C["Control + yêu cầu chấp nhận"]
    C --> S["Scope: tài sản, nhân sự, thời kỳ, phạm vi mẫu"]
    S --> T["Test procedure + test run"]
    T --> E1["Artifact A: cấu hình / policy"]
    T --> E2["Artifact B: log / hành vi thực tế"]
    T --> E3["Artifact C: inventory / xác nhận độc lập"]
    E1 --> V["Đánh giá tính phù hợp, toàn vẹn, đầy đủ"]
    E2 --> V
    E3 --> V
    V --> R{"Verdict"}
    R -->|PASS| A["Assurance record + reviewer sign-off"]
    R -->|FAIL| F["Finding, owner, remediation"]
    R -->|INCONCLUSIVE| G["Evidence gap, thu thập bổ sung"]
    F --> RT["Retest và bằng chứng mới"]
    G --> RT
    RT --> V
~~~

Trong đó:

- **Security objective:** mục tiêu cần bảo vệ, ví dụ ngăn truy cập trái phép dữ liệu khách hàng.
- **Control:** biện pháp tổ chức/kỹ thuật như phân quyền tối thiểu, MFA, audit logging, review quyền.
- **Claim:** khẳng định có thể kiểm tra về control, ví dụ “mọi principal đặc quyền trong scope đã được review trong kỳ”.
- **Scope:** tài sản, tenant, nhóm, môi trường, loại sự kiện, mốc thời gian và các giới hạn.
- **Test:** cách người đánh giá thu thập mẫu, đo và so sánh với tiêu chí chấp nhận.
- **Artifact/evidence:** dữ liệu nguồn hoặc sản phẩm kiểm tra có nguồn gốc xác minh được.
- **Verdict:** kết quả có căn cứ và giới hạn, không chỉ một nhãn màu.
- **Finding/retest:** vòng phản hồi khi thiếu hoặc không đạt tiêu chí.

### 2.1. Không nhảy thẳng từ artifact đến PASS

Một ảnh IAM cho thấy role tồn tại không chứng minh role đã được cấp đúng người. Một bản báo cáo kiểm thử xâm nhập có phát hiện đã sửa không chứng minh bản sửa được triển khai trên mọi instance. Một chứng nhận của nhà cung cấp không chứng minh cấu hình tenant khách hàng tuân thủ.

Cần xây dựng **đường giải thích logic**: từ chính sách đến điều kiện có thể quan sát, từ điều kiện đến phép kiểm tra, từ phép kiểm tra đến dữ liệu, từ dữ liệu đến kết luận.

### 2.2. Một claim có thể cần nhiều loại evidence

Ví dụ claim “Log thao tác quản trị không thể bị xóa trái phép trong kỳ lưu bắt buộc” có thể cần:

1. Export policy retention và phân quyền từ kho log.
2. Audit trail lịch sử thay đổi chính sách/xóa dữ liệu.
3. Kiểm thử quyền đối với tài khoản không được phép xóa.
4. Kết quả truy vấn chứng minh log cũ còn truy xuất được trong kỳ.
5. Inventory nguồn và phạm vi tài khoản/region để đánh giá completeness.

Không loại nào một mình chứng minh toàn bộ claim. Nếu không thể kiểm tra một tài khoản hoặc region, kết luận phải giới hạn scope hoặc ghi INCONCLUSIVE phù hợp.

## 3. Tiêu chí đánh giá chất lượng bằng chứng

Một artifact có thể là file hợp lệ nhưng không phải bằng chứng đủ sức hỗ trợ nhận định. Có thể dùng các thuộc tính sau:

| Thuộc tính | Câu hỏi để đánh giá | Dấu hiệu yếu hoặc cần bổ sung |
|---|---|---|
| **Relevance – tính liên quan** | Bằng chứng có đo đúng control và tình huống cần chứng minh? | Dashboard uptime được dùng thay cho audit logging completeness. |
| **Authenticity – tính xác thực** | Có xác định nguồn sinh, hệ thống, chủ thể và đường lấy artifact? | Ảnh chụp không có tenant/account, không có provenance. |
| **Integrity – tính toàn vẹn** | Có cơ chế phát hiện hoặc kiểm soát thay đổi artifact sau thu thập? | CSV bị sửa bằng tay, không giữ bản gốc hoặc lịch sử biến đổi. |
| **Completeness – tính đầy đủ** | Bao phủ đúng population, kỳ đánh giá, tài sản, sự kiện và ngoại lệ? | Chỉ xuất một trang đầu của API, bỏ các tài khoản khác. |
| **Accuracy – tính chính xác** | Dữ liệu, phép tính, timestamp và ánh xạ trường có được kiểm tra? | Parser gán sai outcome, clock lệch hoặc dữ liệu trùng. |
| **Timeliness – tính kịp thời** | Artifact có phản ánh trạng thái và kỳ đánh giá đang kết luận? | Policy hiện tại được dùng chứng minh kỳ sáu tháng trước. |
| **Reliability – tính đáng tin cậy** | Nguồn có kiểm soát và phương pháp thu thập có ổn định? | Chỉ có lời xác nhận không đối chiếu dù có nguồn kỹ thuật. |
| **Reproducibility – khả năng tái lập** | Người có thẩm quyền khác có thể chạy lại phép kiểm tra trong điều kiện tương tự? | Thiếu truy vấn, bộ lọc, phiên bản parser và scope. |
| **Sufficiency – tính đủ** | Tập bằng chứng có đủ để hỗ trợ kết luận với độ tin cậy phù hợp? | Có cấu hình nhưng không có kiểm chứng hành vi hay coverage. |
| **Independence – mức độc lập** | Nguồn/tác nhân đánh giá có xung đột lợi ích hay cùng một điểm lỗi? | Chủ hệ thống tự khai và tự phê duyệt không có review phù hợp. |
| **Availability & confidentiality** | Auditor có truy xuất được bằng quyền hợp lệ mà không làm lộ dữ liệu? | Evidence chứa secrets hoặc mất khi hệ thống nguồn bị xóa. |

Một số thuộc tính cần cân bằng. Ví dụ ghi toàn bộ dữ liệu vào evidence package có thể cải thiện khả năng tái kiểm tra nhưng làm tăng rủi ro quyền riêng tư; nên giữ **bản gốc trong kho kiểm soát quyền**, cung cấp tập đã lọc và metadata đủ để đánh giá mà không sao chép dữ liệu nhạy cảm không cần thiết.

### 3.1. Thứ bậc bằng chứng phụ thuộc claim

Dữ liệu do hệ thống sinh và test quan sát trực tiếp thường cung cấp cơ sở kỹ thuật tốt cho nhiều control; nhưng không có bảng thứ bậc tuyệt đối áp dụng mọi trường hợp. Đối với chính sách nhân sự, tài liệu phê duyệt và chứng cứ đào tạo có thể là nguồn phù hợp. Đối với “MFA thực sự được thực thi”, kiểm tra effective policy và sự kiện xác thực đáng tin thường mạnh hơn ảnh chụp màn hình cấu hình.

**Không nhầm bằng chứng cấu hình với bằng chứng hiệu lực**, hoặc bằng chứng một thời điểm với bằng chứng vận hành liên tục trong cả kỳ.

## 4. Xác định scope, population và kỳ đánh giá

Một evidence chain thiếu scope có thể dẫn đến kết luận quá rộng. Trước khi thu thập, cần tạo **evidence request** gắn với control:

- **Control ID và claim:** lời khẳng định kiểm thử được, tiêu chí chấp nhận.
- **Population:** toàn bộ tài sản/tài khoản/giao dịch hoặc event có thể áp dụng.
- **Thời kỳ:** trạng thái tại một thời điểm, trong một khoảng, hay cả hai.
- **Môi trường:** production, development, region, account, tenant, cluster, dự án.
- **Chủ sở hữu:** người vận hành nguồn, evidence collector, assessor và người duyệt.
- **Đầu vào:** inventory, chuẩn chính sách, yêu cầu pháp lý/hợp đồng nếu áp dụng.
- **Phương pháp:** API query, export, test hành vi, lấy mẫu, review tài liệu, phỏng vấn.
- **Kỳ vọng:** artifact, định dạng, độ mới, định danh tài sản và tiêu chí PASS/FAIL.
- **Ngoại lệ:** loại tài sản được loại trừ có lý do hay còn trong population.

### 4.1. Population completeness trước sampling

Giả sử có 60 cloud accounts theo hệ thống quản lý tài sản, nhưng script chỉ xuất danh sách từ 52 account. Nếu 52 account đều có logging bật, báo cáo “100% accounts compliant” là sai phạm vi. Phải đối chiếu nguồn population độc lập và phân loại 8 account chưa được kiểm tra.

**Coverage kiểm chứng = số đối tượng đã kiểm tra thành công / tổng đối tượng áp dụng theo inventory đáng tin**, kèm thời điểm inventory và cách xử lý đối tượng mới/xóa. Nếu inventory không đầy đủ, coverage cũng có giới hạn.

### 4.2. Kỳ đánh giá và kiểu evidence

| Kiểu claim | Evidence cần có | Giới hạn cần ghi |
|---|---|---|
| **Point-in-time**: policy hiện đang bật | Export trực tiếp từ API tại mốc đo, phiên bản và identity nguồn. | Không chứng minh policy luôn bật trong kỳ trước. |
| **Period-of-time**: audit log được thu liên tục trong quý | Cấu hình lịch sử, event samples có phạm vi, freshness/ingest telemetry và thay đổi policy trong kỳ. | Chỉ một ngày “healthy” chưa chứng minh cả quý. |
| **Event-driven**: mọi thay đổi IAM đặc quyền phải được review | Population change events, ticket review, phân loại exception, đối chiếu kết quả. | Không đủ nếu chỉ chọn những ticket đã được duyệt. |
| **Recovery/DR**: restore đạt RTO/RPO | Test timeline, dữ liệu đối soát, phạm vi và tiêu chí nghiệm thu. | Thử staging không tự chứng minh điều kiện production. |
| **Vendor assurance**: subprocessor có kiểm soát tương ứng | DPA, scope report, kỳ hiệu lực, exceptions, shared responsibility. | Báo cáo nhà cung cấp không chứng minh mọi cấu hình tenant. |

## 5. Thu thập evidence: Nguồn gốc, phương pháp và bằng chứng gốc

### 5.1. Bảo đảm nguồn có thể nhận diện

Một artifact nên mang theo:

| Trường metadata | Nội dung |
|---|---|
| **artifact_id** | Định danh ổn định và duy nhất trong evidence package. |
| **source_system / source_type** | Hệ thống tạo dữ liệu: IdP, cloud API, scanner, SIEM, CI/CD, GRC, ticketing hoặc thiết bị. |
| **source_locator** | Resource/account/tenant, event ID, query scope hoặc đường dẫn đối tượng tại nguồn. |
| **observed_at / event_time** | Thời điểm sự kiện hoặc trạng thái được quan sát, với timezone rõ. |
| **collected_at_utc** | Thời điểm bản sao evidence được thu thập. |
| **collector_identity / method** | Principal, phiên bản tool/connector, API endpoint hoặc phương pháp export. |
| **scope / filters** | Khoảng thời gian, tham số truy vấn, phân trang, tài sản và điều kiện loại trừ. |
| **format / schema_version** | Kiểu dữ liệu và phiên bản schema/parser. |
| **hash / signature** | Thông tin để phát hiện thay đổi artifact, khi phù hợp; cùng thuật toán và điều kiện xác minh. |
| **storage_reference** | Kho, object version hoặc URI nội bộ có kiểm soát truy cập. |
| **classification / retention** | Độ nhạy cảm, chính sách lưu và quyền truy cập. |

Tập metadata tạo **provenance** – khả năng giải thích artifact đến từ đâu và qua bước nào – chứ chưa tự bảo đảm dữ liệu nguồn đã đầy đủ hoặc không bị can thiệp trước khi thu thập.

### 5.2. Lấy evidence từ API thay vì chỉ ảnh chụp

Một API export có thể cho dữ liệu có cấu trúc, truy vấn có thể lặp và audit trail tốt. Tuy nhiên, API cũng có bẫy: phân trang, rate limit, các region không được truy vấn, quyền token thiếu, trạng thái eventual consistency hoặc response bị cắt.

Ví dụ quy trình xuất quyền truy cập:

1. Xác định population người dùng và role trong scope từ inventory.
2. Gọi API bằng identity chỉ-đọc có quyền đủ để liệt kê toàn bộ scope.
3. Đi hết các trang kết quả, kiểm tra status/continuation token, lưu lỗi API và đối chiếu số lượng.
4. Giữ bản raw response hoặc artifact nguồn cần thiết trong kho có kiểm soát.
5. Tạo bản chuẩn hóa (normalization) có ghi phiên bản parser và mapping.
6. Lưu truy vấn, tham số, mốc thời gian, số đối tượng, exception và checksum/hash nếu áp dụng.
7. Kiểm tra ngẫu nhiên hoặc đối chiếu độc lập để phát hiện nguồn bị thiếu.

Không tự xóa lỗi truy vấn rồi xuất kết quả “success” với tập dữ liệu còn thiếu.

### 5.3. Khi buộc phải dùng ảnh chụp

Ảnh chụp có thể hữu ích khi hệ thống không hỗ trợ export hoặc cần chứng minh một màn hình/ngữ cảnh cụ thể. Để mạnh hơn, nên ghi application, tenant, URL/định danh resource không nhạy cảm, thời điểm, bộ lọc, người thu, phiên bản, trạng thái liên quan và lý do ảnh chụp đại diện cho phạm vi. Không đưa mật khẩu, token hoặc dữ liệu cá nhân không cần thiết vào ảnh. Nếu là ảnh có thể dễ dàng chỉnh sửa, cần thêm nguồn độc lập hoặc ghi giới hạn tin cậy.

## 6. Bảo toàn raw evidence và các phép biến đổi có thể truy vết

Thực tế audit thường cần xử lý CSV/JSON, hợp nhất file, chuẩn hóa trường, loại dữ liệu nhạy cảm hoặc tạo bảng tổng hợp. Đây là những **derived artifacts**; mỗi bước biến đổi cần có lineage.

~~~mermaid
flowchart TD
    A["Raw source export v1"] --> B["Bản gốc lưu read-only / versioned"]
    B --> C["Parser phiên bản 3.1 + mapping"]
    C --> D["Normalized dataset"]
    D --> E["Lọc theo scope + tiêu chí"]
    E --> F["Test results / exceptions"]
    F --> G["Verdict và audit report"]
    B --> H["Hash + source metadata"]
    C --> H
    D --> H
    E --> H
    H --> I["Evidence manifest / lineage"]
    G --> I
~~~

### 6.1. Quy tắc biến đổi

- **Giữ nguyên bản nguồn** trong phạm vi retention đã duyệt, tránh ghi đè lên raw export.
- **Ghi phép biến đổi**: tên và version script/parser, input artifact IDs, tham số, filter, thời gian và output IDs.
- **Không mất hàng âm thầm**: log số dòng ban đầu, bị lọc có chủ đích, bị lỗi parse, trùng hoặc không map được.
- **Không sửa dữ liệu gốc để “làm đẹp”**: ghi correction ở bản dẫn xuất có lý do và nguồn tham chiếu.
- **Có thể tái chạy** khi có quyền và điều kiện phù hợp; kết quả không tái lập phải được giải thích.
- **Ẩn thông tin nhạy cảm có kiểm soát** trong bản gửi auditor, nhưng giữ liên kết xác minh được về nguồn.

### 6.2. Redaction và chứng minh cùng một nguồn

Ví dụ raw log chứa địa chỉ email và địa chỉ IP. Bản báo cáo có thể dùng pseudonym hoặc xóa trường không cần thiết để giảm rủi ro. Cần ghi: policy redaction, công cụ/version, dữ liệu trường nào đã thay, và bản redacted dẫn xuất từ artifact ID nào. Hash của bản redacted sẽ **khác** hash raw; phải lưu hash riêng cho từng artifact. Không nói “hash giống nhau” để chứng minh hai bản khác nội dung.

## 7. Hash, chữ ký và tính toàn vẹn: Giá trị và giới hạn

Hash mật mã có thể giúp phát hiện artifact thay đổi khi so sánh một giá trị digest đáng tin với nội dung hiện tại. Ví dụ SHA-256 thường được dùng cho file evidence.

~~~text
Artifact nguồn A (raw export)
    |-- SHA-256 digest: H_A
    |-- lưu tại kho có version và kiểm soát quyền
    |
    +--> Artifact B (bản redacted)
           |-- lineage: derived_from = A
           |-- SHA-256 digest: H_B (khác H_A)
           +-- transformation: redaction-rule-v2
~~~

**Hash không chứng minh mọi điều**:

- Một file có hash đúng vẫn có thể chứa dữ liệu nguồn **sai, thiếu hoặc bị thao túng trước khi thu thập**.
- Người có khả năng thay cả file lẫn bản manifest/digest lưu chung có thể làm suy giảm giá trị kiểm tra. Cần bảo vệ vị trí lưu digest và audit trail.
- Hash không xác định **ai tạo file**. Chữ ký số hoặc xác thực nguồn có thể hỗ trợ khi khóa và identity được quản lý đáng tin cậy.
- Việc tính hash sau nhiều lần sửa không chứng minh file đã nguyên trạng kể từ thời điểm sự kiện.
- Một chain of custody có hash nhưng không ghi nhận người truy cập, sao chép và bàn giao vẫn có khoảng trống quản lý.

### 7.1. Các biện pháp bổ trợ

| Biện pháp | Đóng góp | Giới hạn |
|---|---|---|
| **Cryptographic hash** | Phát hiện thay đổi nội dung kể từ mốc digest đáng tin. | Không chứng minh nguồn đầy đủ, danh tính người tạo hoặc thời điểm sự kiện. |
| **Digital signature** | Gắn dữ liệu với khóa ký và kiểm tra tính toàn vẹn/xác thực theo trust model. | Phụ thuộc an toàn khóa và việc xác nhận signer. |
| **Object versioning** | Giữ lịch sử các phiên bản artifact. | Không tự chống sửa/xóa bởi quản trị viên có đặc quyền vượt mức. |
| **Immutable/WORM retention** | Hạn chế sửa/xóa trong kỳ lưu nếu cấu hình và quyền phù hợp. | Không thể đảo ngược việc dữ liệu sai đã được nhập ban đầu. |
| **Append-only audit trail** | Theo dõi hoạt động tạo, đọc, sửa quyền và quy trình xử lý. | Cần bảo vệ nguồn audit khỏi cùng một phạm vi xâm nhập. |
| **Separation of duties** | Tách collector, assessor, approver và custodian khi rủi ro yêu cầu. | Vẫn cần kiểm tra quyền hiệu lực và ngoại lệ. |
| **Independent time/source corroboration** | Giảm rủi ro lệ thuộc một nguồn thời gian hoặc một hệ thống. | Hai nguồn có thể vẫn chung cơ chế lỗi hoặc bị điều khiển cùng cấp quyền. |

### 7.2. Quyền quản trị vẫn quan trọng

Nếu người có quyền production cũng có thể sửa evidence bucket, tắt audit và thay đổi retention, chuỗi bằng chứng dễ bị vô hiệu hóa. Thiết kế nên dùng **quyền tối thiểu**, phân tách quyền thu/đọc/xóa/quản trị policy và giám sát hoạt động đặc quyền. Với bằng chứng trọng yếu, cân nhắc lưu ở tài khoản/kho độc lập hoặc kiểm soát chống sửa phù hợp.

## 8. Chain of custody trong điều tra và audit

**Chain of custody** nhấn mạnh lịch sử nắm giữ, thao tác, chuyển giao và bảo vệ một vật chứng hoặc chứng cứ số. Đây là yêu cầu đặc biệt quan trọng trong điều tra nội bộ có nguy cơ tranh chấp, forensics hoặc quy trình pháp lý; mức chính thức phải theo chính sách và yêu cầu pháp luật liên quan.

### 8.1. Một bản ghi bàn giao tối thiểu

| Trường | Mục đích |
|---|---|
| Case/evidence ID | Liên hệ chứng cứ với vụ việc, tránh nhầm lẫn. |
| Mô tả, nguồn và phạm vi | Chứng cứ là gì, thu từ đâu, hệ thống nào, trạng thái ban đầu. |
| Người thực hiện, tổ chức và thẩm quyền | Ai thu và có quyền làm gì. |
| Ngày giờ, timezone, phương pháp | Khi nào và cách nào thu; ghi sai lệch đồng hồ nếu biết. |
| Hash/định danh bản sao | Kiểm tra artifact đã được thay đổi giữa các mốc. |
| Nơi lưu và điều kiện bảo vệ | Kho, quyền, niêm phong/chính sách không sửa và nhật ký truy cập. |
| Mỗi lần bàn giao/tiếp nhận | Người giao, người nhận, thời điểm, mục đích, trạng thái, xác nhận. |
| Hoạt động phân tích | Bản sao nào dùng, công cụ/version, kết quả tạo ra và tác động đến artifact. |
| Tình trạng hoặc ngoại lệ | Mất dữ liệu, lỗi thiết bị, thiếu chữ ký, khoảng thời gian không kiểm soát và cách xử lý. |

### 8.2. Giữ bản gốc và làm việc trên bản sao

Trong điều tra số, có thể cần thu disk image, memory capture, log export hoặc cấu hình theo quy trình forensics được ủy quyền. Nên tránh thao tác thay đổi chứng cứ gốc không cần thiết, lưu bản gốc trong môi trường kiểm soát và làm việc trên bản sao đã xác minh khi khả thi. Với hệ thống đang chạy, mọi thao tác thu thập có thể làm thay đổi một số trạng thái; ghi lại phương pháp, hạn chế và tác động đó.

Không thực hiện thu giữ thiết bị hoặc truy cập tài khoản ngoài phạm vi được phép. Yêu cầu pháp lý, bảo vệ dữ liệu và nghĩa vụ giữ chứng cứ có thể thay đổi theo quốc gia và vụ việc; cần phối hợp đội phụ trách.

### 8.3. Ví dụ nhật ký bàn giao

~~~text
Evidence ID: IR-FORENSIC-014
Incident ID: IR-2026-014
Nguồn: máy chủ ứng dụng được cô lập
Thu thập: 2026-11-28T02:15:00Z
Người thu: IR Collector A (ủy quyền theo incident)
Artifact: disk-image-014
Hash: SHA-256 = [giá trị digest thực tế trong kho evidence]
Vị trí ban đầu: secure-evidence-store / object-version-01
02:20Z - A bàn giao cho Evidence Custodian B, mục đích lưu giữ
03:00Z - B cấp bản sao đã xác minh cho Analyst C, mục đích phân tích
04:10Z - C xuất report riêng, không sửa bản gốc
Các bước: chữ ký/ACK, audit access, hash check trước/sau và ghi chú ngoại lệ
~~~

Mẫu chỉ để hiểu cấu trúc, không thay thế biểu mẫu pháp chứng hoặc quy trình điều tra chính thức.

## 9. Lưu trữ, bảo mật, retention và khả năng truy xuất

Evidence có thể chứa chi tiết hạ tầng, user IDs, log truy cập, địa chỉ, dữ liệu khách hàng hoặc thông tin dễ bị lạm dụng. Kho evidence vì vậy là **tài sản bảo mật**, không phải chỗ chia sẻ file tự do.

### 9.1. Yêu cầu kho evidence

- **Truy cập phân quyền:** collector chỉ ghi vào khu vực cần thiết; assessor có quyền đọc phù hợp; approver không tự chỉnh kết quả đã duyệt; quyền xóa/retention policy được giới hạn.
- **Mã hóa:** đường truyền và dữ liệu lưu theo chính sách; kiểm soát khóa, quyền giải mã và khả năng phục hồi.
- **Audit truy cập và thao tác:** tạo, đọc, tải xuống, chia sẻ, sửa quyền, retention policy, delete, export và thay đổi metadata quan trọng.
- **Integrity/version control:** object version, checksum, tính bất biến hoặc cơ chế chống sửa nếu phù hợp với threat model.
- **Retention và legal hold:** bảo toàn theo kỳ kiểm toán, điều tra, hợp đồng và yêu cầu pháp lý; có quy trình cho ngoại lệ giữ dữ liệu.
- **Availability:** sao lưu/khả năng phục hồi kho, thử truy xuất theo mẫu và khả năng cung cấp đúng hạn cho auditor.
- **Classification/redaction:** xác định mức nhạy cảm, đối tượng được chia sẻ và thông tin phải ẩn.
- **Deletion:** sau thời hạn phù hợp, có quy trình xóa/kiểm chứng và xử lý các bản sao.

Không đặt một con số “giữ evidence N năm” cho mọi tình huống. Thời hạn phụ thuộc loại hồ sơ, nghĩa vụ pháp luật/hợp đồng và mục đích xử lý. Không nên giữ vô hạn dữ liệu cá nhân chỉ vì “có thể audit trong tương lai”.

### 9.2. Audit trail cũng cần được bảo vệ

Nếu event audit của kho evidence nằm ở cùng một hệ thống mà người quản trị kho có thể xóa, tính độc lập của bằng chứng bị suy giảm. Với rủi ro cao, cần tách nơi lưu log/audit, quyền thay đổi policy và người giám sát. Thử tình huống người không có quyền cố sửa/xóa để xác nhận kiểm soát hoạt động, chỉ thực hiện trong phạm vi được phép.

## 10. Thiết kế quy trình Evidence chain theo vòng đời

~~~mermaid
flowchart TD
    A["Control và claim được duyệt"] --> B["Xác định population, kỳ, tiêu chí"]
    B --> C["Lập evidence request và collector"]
    C --> D["Thu raw artifact + provenance"]
    D --> E["Kiểm tra completeness, timestamp, integrity"]
    E --> F{"Evidence đủ tin cậy?"}
    F -->|Không| G["Gap: bổ sung nguồn, sửa collector, mở finding"]
    G --> C
    F -->|Có| H["Normalize / test có version"]
    H --> I["Đánh giá control, đối chiếu exceptions"]
    I --> J{"Kết luận"}
    J -->|PASS| K["Reviewer approval + retention"]
    J -->|FAIL| L["Finding + remediation owner"]
    J -->|INCONCLUSIVE| M["Thu thập bổ sung, giới hạn kết luận"]
    L --> N["Retest với evidence mới"]
    M --> N
    N --> E
    K --> O["Continuous monitoring, review khi đổi control"]
~~~

### Bước 1 — Viết claim và tiêu chí chấp nhận

Ví dụ: “100% cloud accounts production trong inventory tại thời điểm kết thúc quý có audit control-plane log được bật, log quan trọng chuyển vào kho tập trung và chính sách không cho operator bình thường xóa trong kỳ giữ.” Tách thành các subclaim: coverage của tài khoản, log generation, end-to-end ingestion, quyền xóa, retention. Mỗi subclaim có tiêu chí riêng.

Tránh claim mơ hồ như “hệ thống logging bảo mật tốt”. Nó không chỉ rõ phương pháp đo hoặc điều kiện thất bại.

### Bước 2 — Chốt population và dữ liệu nguồn

Dùng danh mục tài sản có owner và mốc cập nhật để biết hệ thống nào thuộc phạm vi. Với cloud, xét account/region, tài nguyên mới được tạo và những account vừa ngừng sử dụng trong kỳ. Với IAM, xét cả human, service, break-glass, federated identities và tài khoản đặc quyền độc lập.

### Bước 3 — Thu thập có phương pháp

Sử dụng API/query hoặc phương án thích hợp; kiểm tra lỗi, phân trang, phạm vi quyền và timezone. Lưu raw artifact cùng tham số, ID, thời gian, phiên bản collector và trạng thái đầy đủ.

### Bước 4 — Kiểm tra chất lượng bản thu

Đối chiếu số lượng, định dạng, phiên bản, hash, các trường bắt buộc và độ mới. Nếu thiếu một nguồn quan trọng, không chạy tiếp rồi đưa ra PASS tổng thể; ghi rõ evidence gap.

### Bước 5 — Chạy test và tạo output có lineage

Mọi test run phải nêu control, tiêu chí, input artifact IDs, version script hoặc phương pháp review, thời gian chạy, kết quả cho từng đối tượng, exceptions và file output. Nếu script biến đổi dữ liệu, lưu tên/version/mapping và checksum bản đầu ra.

### Bước 6 — Reviewer đánh giá và kết luận

Đánh giá cả chất lượng evidence và kết quả kỹ thuật. Một control có thể **FAIL dù bằng chứng rất tốt** nếu phép kiểm tra chứng minh chính sách bị vi phạm; ngược lại, một config có vẻ đạt nhưng evidence thiếu scope thì nên **INCONCLUSIVE**.

### Bước 7 — Lưu quyết định, xử lý findings và tái kiểm tra

Tạo finding có asset, control, nguyên nhân, tác động, owner, deadline, biện pháp sửa và evidence cần để retest. Lưu **phiên bản kết quả mới** thay vì ghi đè báo cáo cũ. Mọi thay đổi của conclusion sau retest phải có lịch sử và người phê duyệt.

## 11. Test of design và test of operating effectiveness

Một bằng chứng mạnh phải phù hợp loại kiểm tra:

| Loại kiểm tra | Mục tiêu | Ví dụ và giới hạn |
|---|---|---|
| **Design effectiveness** | Thiết kế control có đủ để đáp ứng mục tiêu nếu được thực hiện đúng? | Review chính sách RBAC, approval workflow, architecture; chưa chứng minh vận hành thực tế. |
| **Implementation** | Control có được cấu hình/triển khai tại đối tượng thuộc scope? | Export IAM, audit config, agent deployment; chưa tự chứng minh áp dụng liên tục. |
| **Operating effectiveness** | Control có hoạt động như mong muốn trong kỳ hoặc trước sự kiện rủi ro? | Log thay đổi quyền và approval, test phân quyền, event pipeline, review định kỳ. |
| **Remediation effectiveness** | Sau sửa lỗi, control có đạt điều kiện và không tái diễn trong phạm vi retest? | Test lại có version, thời điểm, đối tượng, log và kết quả mới. |

**Design PASS không suy ra Operating PASS.** Một quy định “mọi deployment phải qua code review” có thể tồn tại trong policy nhưng vẫn có tài khoản bypass pipeline; cần bằng chứng từ branch protection, PR approvals, deployment log và các đường triển khai khác.

### 11.1. Bằng chứng thay đổi theo thời gian

Đối với vận hành liên tục, evidence chỉ chụp tại một thời điểm không chứng minh kỳ dài. Có thể kết hợp configuration history, event stream, thay đổi policy, synthetic test định kỳ và kiểm tra exception. Cần nêu rõ thời kỳ đo, khoảng gián đoạn telemetry và mức tin cậy khi suy diễn.

## 12. Lấy mẫu, sai lệch chọn mẫu và giới hạn suy luận

Trong audit có thể cần lấy mẫu khi population lớn. Việc chọn mẫu phải tương thích với mục tiêu đánh giá và rủi ro; không thể coi kiểm tra mẫu là xác nhận tuyệt đối toàn bộ population.

### 12.1. Các chiến lược lấy mẫu

- **Toàn bộ population:** dùng query tự động kiểm tra mọi đối tượng nếu khả thi, đồng thời đối chiếu độ đầy đủ của nguồn.
- **Random sample:** giảm thiên lệch chọn thuận tiện; cần ghi số lượng, phương pháp và seed nếu tái lập có ý nghĩa.
- **Risk-based sample:** ưu tiên đối tượng đặc quyền, hệ thống dữ liệu nhạy cảm, sự kiện ngoại lệ và thay đổi lớn.
- **Stratified sample:** chia theo vùng, service tier, account, loại identity, đội vận hành hoặc quý/tháng.
- **Targeted follow-up:** mở rộng mẫu khi phát hiện lỗi, nhưng không trộn kết quả mẫu mục tiêu với mẫu đại diện mà không giải thích.

### 12.2. Một ví dụ

Giả sử có 200 lần thay đổi quyền đặc quyền trong kỳ. Auditor chọn 25 giao dịch, gồm 15 ngẫu nhiên và 10 rủi ro cao, để kiểm tra approval và audit log. Kết quả 24 đạt và 1 thiếu bằng chứng phê duyệt. Không thể công bố “96% của toàn bộ 200 thay đổi đã được duyệt” chỉ từ phép tính 24/25 vì mẫu pha trộn rủi ro không đại diện thống kê. Có thể kết luận **24/25 mẫu được kiểm tra đạt**, ghi finding cho trường hợp còn lại và mở rộng đánh giá nếu cần.

**Không có lỗi trong mẫu không chứng minh không có lỗi trong population.** Quyết định mức tin cậy, cỡ mẫu và cách ngoại suy phải tuân theo phương pháp audit được phê duyệt; không tự áp dụng tỷ lệ từ mẫu cho mọi tổ chức.

### 12.3. Định nghĩa loại trừ hợp lệ

Nếu một account vừa bị xóa khỏi inventory cuối kỳ nhưng có thay đổi IAM giữa kỳ, không nên loại nó khỏi population của claim “mọi thay đổi trong quý”. Phạm vi kiểm tra phải theo **định nghĩa thời gian của claim**, không chỉ trạng thái tài sản hiện tại.

## 13. Hồ sơ kết quả và trạng thái có trách nhiệm

Có thể dùng một ma trận:

| Trạng thái | Khi nào áp dụng | Điều tuyệt đối không nên làm |
|---|---|---|
| **PASS** | Có evidence đủ tin cậy, đúng scope/thời kỳ, test đáp ứng toàn bộ tiêu chí bắt buộc. | Kết luận PASS dựa trên một ảnh cấu hình nếu claim đòi hoạt động trong cả kỳ. |
| **FAIL** | Test hoặc bằng chứng chứng minh không đáp ứng điều kiện. | Gọi FAIL là INCONCLUSIVE chỉ để tránh finding đã xác nhận. |
| **INCONCLUSIVE** | Không đủ bằng chứng, scope hoặc chất lượng để khẳng định đạt/không đạt. | Đổi thành PASS vì không tìm thấy dấu hiệu lỗi. |
| **NOT_APPLICABLE** | Control hoặc đối tượng thực sự không áp dụng, có lý do rõ và người xác nhận. | Dùng để che giấu nguồn không được kiểm tra. |

### Risk acceptance không phải bằng chứng PASS

Một đơn vị có thể chấp nhận vận hành tạm thời một control chưa đạt vì lý do nghiệp vụ, với người có thẩm quyền và biện pháp bù trừ. Điều đó phải được quản lý ở **risk exception record** riêng. Kết quả kỹ thuật vẫn giữ FAIL hoặc INCONCLUSIVE theo bằng chứng; review định kỳ và kế hoạch khắc phục không được bị bỏ quên.

### Evidence chain khi kết luận thay đổi

Nếu một control FAIL ở ngày 1, được sửa ngày 5 và retest PASS ngày 6, không xóa hoặc thay nội dung bản ngày 1. Chuỗi cần giữ:

~~~text
Assessment v1 (2026-11-01): FAIL
    -> Finding F-123, lỗi phân quyền
    -> Remediation C-456, cấu hình sửa và người phê duyệt
    -> Evidence A2/B2, thu 2026-11-05
    -> Retest v2 (2026-11-06): PASS với scope đã nêu
    -> Residual risk / monitoring plan

Lịch sử vẫn cho thấy kỳ trước đã từng FAIL.
~~~

Điều này quan trọng khi audit một **period-of-time**: việc sửa vào ngày 5 không thay đổi sự thật rằng control chưa hiệu lực vào ngày 1–4. Cần phân biệt kết luận hiện tại với hiệu lực cả kỳ.

## 14. Mẫu Evidence manifest và assurance record

Một **manifest** là điểm chỉ mục liên kết claim, nguồn, phép kiểm tra, artifact, biến đổi, kết quả và người duyệt. Mẫu YAML sau chỉ minh họa; không phải schema chính thức của một framework.

~~~yaml
evidence_package:
  id: "ASSURANCE-EVIDENCE-EXAMPLE-007"
  module: "SECURITY_SECURITY_ASSURANCE"
  control_id: "LOG-COV-EXAMPLE-01"
  objective: "Bảo đảm audit log thao tác quản trị production được thu thập"
  claim: "Mọi account thuộc scope có sự kiện audit được thu và truy vấn"
  assessment_period:
    start_utc: "2026-11-01T00:00:00Z"
    end_utc: "2026-11-28T00:00:00Z"
  scope:
    environment: "production"
    inventory_snapshot: "INVENTORY-2026-11-28"
    expected_accounts: 12
    excluded_accounts: []
  responsibility:
    control_owner: "Platform Security Owner"
    collector: "Evidence Automation Service"
    assessor: "Security Assurance Analyst"
    approver: "Independent Reviewer"

collection:
  method: "read-only API export and synthetic event verification"
  connector_version: "3.1.0"
  collected_at_utc: "2026-11-28T01:00:00Z"
  source_pagination_completed: true
  api_errors: 0
  accounts_with_data: 11
  missing_accounts:
    - "account-example-12"

artifacts:
  - artifact_id: "RAW-AUDIT-001"
    kind: "raw-export"
    source_system: "cloud-control-plane-audit"
    source_scope: "production accounts"
    stored_at: "restricted-evidence/007/raw-audit-001"
    hash_algorithm: "SHA-256"
    digest_reference: "restricted-evidence/007/digests/raw-audit-001"
    collected_by: "Evidence Automation Service"
    classification: "CONFIDENTIAL"
  - artifact_id: "NORMALIZED-002"
    kind: "derived"
    derived_from: ["RAW-AUDIT-001"]
    transform_version: "parser-3.1.0"
    stored_at: "restricted-evidence/007/normalized-002"
  - artifact_id: "TEST-REPORT-003"
    kind: "test-result"
    inputs: ["NORMALIZED-002", "INVENTORY-2026-11-28"]
    method_version: "coverage-check-v2"
    stored_at: "restricted-evidence/007/test-report-003"

assessment:
  criteria:
    expected_coverage_percent: 100
    end_to_end_event_verified_for_each_account: true
  verified_accounts: 11
  coverage_percent: 91.67
  verdict: "FAIL"
  rationale: "Một account production thiếu bằng chứng sự kiện tại đích"
  limitations:
    - "Chưa xác định lỗi thuộc collector, nguồn hay quyền API"
  reviewer_signed_at_utc: "2026-11-28T02:00:00Z"

finding:
  id: "FINDING-LOG-007"
  owner: "Cloud Platform Team"
  action: "Khôi phục audit export, kiểm tra đường đi và retest"
  target_evidence:
    - "synthetic-event-with-source-and-ingest-IDs"
    - "config-and-collector-health"
  status: "OPEN"

governance:
  retention_policy: "POLICY-TO-BE-APPLIED"
  access_policy: "SECURITY-AUDIT-READERS"
  immutable_or_versioned_storage: true
  audit_access_enabled: true
~~~

Các ID, thời gian và con số đều **giả định**. Giá trị **91,67%** là tỷ lệ 11/12 đã được xác minh, không tự diễn đạt là tỷ lệ bảo mật tổng thể của hệ thống. Control đặt mục tiêu 100% tài khoản trong scope và có một account chưa kiểm chứng. Nếu bài kiểm tra chứng minh một account thật sự không được thu, kết luận là FAIL; nếu chỉ thiếu quyền thu evidence nhưng trạng thái thực chưa rõ, cần phân biệt **control outcome = INCONCLUSIVE** và **evidence-collection failure**. Trong manifest này, bản ghi nhận “thiếu bằng chứng” là chưa đủ để khẳng định một log nguồn không tồn tại; nên xem **FAIL của tiêu chí về bằng chứng bao phủ** và ghi giới hạn khi suy luận về trạng thái hoạt động thực tế.

### 14.1. Phân biệt control result và evidence result trong manifest

Để tránh nhầm lẫn, có thể tách hai trường:

~~~yaml
verification_outcome:
  evidence_completeness: "FAIL"
  control_operating_effectiveness: "INCONCLUSIVE"
  reason: "Không quan sát được account cuối; chưa biết do thu thập hay log không được bật"
  next_test: "Kiểm tra sự kiện tại nguồn và pipeline bằng dữ liệu thử an toàn"
~~~

Với kết quả này, reviewer không thể phê duyệt claim “mọi account đều có audit log”, nhưng cũng không được tuyên bố chắc chắn account đó không ghi log. Đây là khác biệt quan trọng giữa **thiếu bằng chứng** và **bằng chứng về thất bại**.

### 14.2. Traceability register cho nhiều control

| Claim ID | Control | Test ID | Raw evidence | Derived evidence | Verdict | Owner |
|---|---|---|---|---|---|---|
| CL-IAM-01 | MFA đặc quyền | T-IAM-01 | Export IdP + role inventory | Effective policy report | PASS theo scope | IAM Owner |
| CL-LOG-02 | Log tập trung | T-LOG-02 | Event nguồn + ingest | Coverage matrix | INCONCLUSIVE | Observability |
| CL-DR-03 | Phục hồi dữ liệu | T-DR-03 | Backup/transaction log | Restore/reconciliation report | FAIL | Data Owner |
| CL-VUL-04 | Vá lỗ hổng | T-VUL-04 | Asset + scanner + package | Patch effectiveness report | PASS tại thời điểm đo | Platform Owner |

Các dòng chỉ là ví dụ cấu trúc; trong thực tế cần gắn thời kỳ, phạm vi, phương pháp, người duyệt và kết quả theo tài sản để tránh một dòng tổng hợp che đi ngoại lệ.

## 15. Bằng chứng từ nhà cung cấp và shared responsibility

Với cloud, SaaS hoặc dịch vụ được quản lý, khách hàng không quan sát trực tiếp toàn bộ hạ tầng của nhà cung cấp. Điều này không có nghĩa có thể bỏ qua evidence chain; chỉ có nghĩa **loại bằng chứng và giới hạn truy cập khác đi**.

Có thể kết hợp:

- Cấu hình và sự kiện trong tenant của khách hàng.
- Báo cáo assurance/chứng nhận từ nhà cung cấp có phạm vi và kỳ đánh giá phù hợp.
- Cam kết DPA, SLA, phân chia trách nhiệm và quyền truy cập log.
- Kết quả thử chức năng, synthetic event, DR exercise hoặc export mà khách hàng được phép thực hiện.
- Thông báo thay đổi, incident, exception và biện pháp xử lý được nhà cung cấp xác nhận.

Ví dụ, báo cáo SOC 2 của cloud provider có thể hỗ trợ đánh giá các control thuộc phía provider trong phạm vi báo cáo, nhưng không chứng minh rằng khách hàng đã bật logging, cấu hình IAM hoặc phân quyền tenant đúng. Cần map **provider controls → customer responsibilities → nguồn evidence tương ứng**.

### 15.1. Đọc scope báo cáo bên thứ ba

Xác nhận pháp nhân/dịch vụ, kỳ báo cáo, khu vực, hệ thống trong phạm vi, ngoại lệ, subservice organizations và những control mà khách hàng phải thực hiện. Nếu báo cáo đánh giá một giai đoạn cũ, ghi những thay đổi lớn kể từ ngày báo cáo và nguồn bổ sung thích hợp; không tự gán nó là bằng chứng hiện tại cho một hệ thống đã chuyển nền tảng.

### 15.2. Confidential evidence và quyền của auditor

Nhà cung cấp có thể cấm phân phối công khai báo cáo audit. Giữ tài liệu trong kho được phân quyền theo thỏa thuận, lưu metadata/trích yếu đủ dùng và cung cấp đúng đối tượng. Tránh sao chép nguyên báo cáo bên thứ ba vào các ticket hoặc repository không kiểm soát.

## 16. Automation và continuous evidence

Thu thập thủ công mỗi năm có thể chậm phát hiện drift. **Continuous evidence** là cách thu thập, xác minh và liên kết bằng chứng tự động hoặc định kỳ theo sự thay đổi của hệ thống và rủi ro, trong khi vẫn có người chịu trách nhiệm đánh giá.

### 16.1. Pipeline đề xuất

~~~mermaid
flowchart LR
    A["Inventory + yêu cầu controls"] --> B["Scheduler / event trigger"]
    B --> C["Read-only collectors"]
    C --> D["Raw evidence store + provenance"]
    D --> E["Schema/coverage/integrity validation"]
    E --> F["Test engine + result manifest"]
    F --> G["Reviewer queue + findings"]
    G --> H["Remediation, retest, dashboards"]
    H -.-> B
~~~

Hệ thống automation phải tuân thủ nguyên tắc bảo mật: identity riêng theo scope, quyền đọc tối thiểu, mã hóa, quản lý secret, audit hoạt động, hạn chế export dữ liệu nhạy cảm, kiểm tra API rate limit và fail-closed đối với kết quả không đủ bằng chứng.

**Pipeline xanh không chứng minh control PASS** nếu collector chỉ truy vấn được một phần tài sản. Cần có kiểm soát để đo sức khỏe **của chính quy trình evidence**.

### 16.2. Các chỉ số hữu ích

| Chỉ số | Ý nghĩa | Cần tránh |
|---|---|---|
| **Claim coverage** | Số claim/control bắt buộc có phép thử và kết quả còn hiệu lực / tổng claim áp dụng. | Đếm các claim chưa đủ scope là đã kiểm chứng. |
| **Population coverage** | Đối tượng trong scope có evidence đầy đủ / tổng population đáng tin. | Lấy mẫu số chỉ gồm những đối tượng đã tìm thấy. |
| **Evidence freshness** | Thời gian từ lần thu thập/kiểm chứng gần nhất so với chu kỳ rủi ro. | Coi artifact cũ là trạng thái hiện tại. |
| **Integrity validation rate** | Tỷ lệ artifact có phép kiểm tra toàn vẹn đạt theo chính sách. | Dùng hash làm bằng chứng rằng control hoạt động. |
| **Collection error rate** | Lỗi API, permission, pagination, parser, storage hoặc timeout. | Bỏ lỗi âm thầm và phát PASS mặc định. |
| **Traceability completeness** | Tỷ lệ verdict có đủ link claim/test/input/reviewer. | Báo cáo chỉ có trạng thái và ảnh minh họa không có provenance. |
| **Evidence gap age** | Thời gian tồn tại các khoảng trống theo severity và owner. | Để INCONCLUSIVE vô thời hạn mà không có escalation. |
| **Finding closure effectiveness** | Finding được sửa và retest có chứng cứ / tổng finding cần xử lý. | Đóng finding ngay sau khi ticket ghi “done”. |

### 16.3. Drift và sự kiện kích hoạt thu lại

Khi có tài khoản mới, dịch vụ cloud thêm region, role IAM đổi, parser logging thay version, scanner tăng coverage, vendor cập nhật scope audit hoặc security policy điều chỉnh, evidence chain cần cập nhật. Một artifact cũ không nhất thiết sai, nhưng **không còn đủ đại diện** cho kiến trúc hoặc population mới.

## 17. Tình huống thực hành: “Logging đã đạt” nhưng bằng chứng bị đứt

Một doanh nghiệp vận hành 12 cloud accounts production. Đội vận hành nộp báo cáo “100% centralized audit logging compliant” dựa trên ảnh chụp dashboard của hệ thống thu log ngày cuối tháng. Dashboard xanh, tổng lượng sự kiện vẫn tăng. Auditor yêu cầu xác nhận mọi account production có log hoạt động quản trị trong 30 ngày gần nhất.

Trong quá trình kiểm tra:

- Inventory GRC liệt kê 12 account, nhưng collector chỉ có quyền đọc 11 account.
- Tệp CSV do đội vận hành cung cấp có 11 account; không ghi rõ pagination, query filter hoặc thời kỳ.
- Mọi event đã xuất được chuyển sang CSV chuẩn hóa, nhưng bản raw source đã bị xóa.
- Một analyst đã lọc bỏ các dòng lỗi parser để làm bảng thống kê dễ đọc hơn.
- Hash SHA-256 được tạo sau khi CSV đã chỉnh sửa.
- Báo cáo cuối cùng ghi PASS mà không có reviewer khác xác nhận.
- Một account vừa được thêm giữa kỳ; nhóm vận hành chưa biết nó có bật control-plane audit logging hay không.

### 17.1. Câu hỏi

1. Có thể chấp nhận kết luận PASS cho claim “toàn bộ account production có centralized audit logging” không?
2. Hash hiện có chứng minh điều gì và không chứng minh điều gì?
3. Những mắt xích nào của evidence chain bị thiếu?
4. Cần thu thập và kiểm thử lại thế nào để đưa ra kết luận đúng?
5. Cách nào giúp quy trình không tái diễn khi account mới được tạo?

### 17.2. Phân tích

**Bước 1 — Kiểm tra claim và population.** Mẫu số là 12 account production thuộc phạm vi, không phải 11 account mà collector đã truy cập. Cần đối chiếu cả account mới được tạo trong kỳ và thời điểm bắt buộc bắt đầu logging đối với account đó. Không dùng dashboard tổng volume để suy ra tất cả nguồn có event.

**Bước 2 — Đánh giá source provenance.** CSV thiếu raw export, filter, pagination và thời kỳ. Analyst đã loại lỗi parser nhưng không giữ artifact lỗi nên không còn phân tích được các sự kiện bị bỏ. Hash sau chỉnh sửa chỉ hỗ trợ phát hiện **các thay đổi xảy ra sau lúc tính hash**, nếu digest được lưu đáng tin; nó không chứng minh CSV đầy đủ hoặc đúng với nguồn ban đầu.

**Bước 3 — Tách kết luận.** Evidence completeness cho 12/12 account **FAIL** vì chưa kiểm tra account cuối. Operating effectiveness của logging tại account đó là **INCONCLUSIVE** cho tới khi có bằng chứng nguồn/đích. Kết luận PASS toàn hệ thống **không được hỗ trợ**; tùy định nghĩa control, đánh giá tổng thể không đạt tiêu chí coverage hoặc chưa đủ bằng chứng, phải ghi chính xác lý do.

**Bước 4 — Thu lại bằng chứng.** Cập nhật quyền chỉ-đọc cho collector, truy vấn đủ 12 account với audit về API status, pagination, thời kỳ và tất cả region áp dụng. Lưu raw events/config, event ID, timestamp, parameters, source IDs và hashes, tạo bảng chuẩn hóa có lineage, xử lý parser errors ở khu riêng. Kiểm tra synthetic event an toàn hoặc bản ghi đại diện từ từng account đi qua pipeline tới kho tập trung.

**Bước 5 — Test lại và phê duyệt độc lập.** Tạo test run version mới, đối chiếu yêu cầu, nêu account có/không đạt và nguồn evidence. Reviewer đánh giá đủ scope, dữ liệu và retention. Nếu có account bị tắt log, mở finding khắc phục, chứng minh sửa và retest; không ghi đè báo cáo sai ban đầu.

**Bước 6 — Ngăn tái diễn.** Gắn collector với inventory tài sản/asset onboarding, báo khi account mới không xuất log hoặc bị mất quyền truy vấn, kiểm tra parser errors, coverage và freshness, yêu cầu signed-off evidence manifest. Định kỳ chọn một mẫu account mới để thử end-to-end.

### 17.3. Kết luận tình huống

Một báo cáo tổng hợp “100% compliant” không thể thay thế đường truy vết từ claim đến dữ liệu nguồn. Điều cần sửa không chỉ là bổ sung account thứ 12 mà còn là **tái xây dựng provenance, completeness, lineage và quy trình review** để lần kiểm tra sau có giá trị bảo đảm.

## 18. Sai lầm thường gặp trong Evidence chain

| Sai lầm | Hệ quả | Hướng khắc phục |
|---|---|---|
| Lưu nhiều screenshot nhưng không có claim/test mapping. | Không biết ảnh hỗ trợ kết luận gì. | Traceability register liên kết control, scope, test, artifact và verdict. |
| Dùng snapshot hiện tại chứng minh cả kỳ. | Có thể bỏ sót khoảng thời gian control tắt hoặc sai. | Dùng lịch sử cấu hình/event, nêu time window và giới hạn. |
| Lấy mẫu số từ những tài sản API trả về. | Bỏ các tài sản thiếu quyền hoặc lỗi collector. | Đối chiếu population độc lập, theo dõi missing sources. |
| Không giữ raw export và biến đổi không có version. | Không thể tái lập kết quả hoặc điều tra mapping lỗi. | Raw immutable/versioned, lineage và nhật ký xử lý. |
| Coi hash chứng minh nguồn trung thực. | File sai trước lúc hash vẫn có digest đúng. | Kết hợp provenance, xác thực nguồn, controls thu thập và đối chiếu độc lập. |
| Không kiểm soát quyền sửa evidence và audit trail. | Bằng chứng có thể bị thay mà không phát hiện. | RBAC, tách nhiệm vụ, versioning, audit độc lập. |
| Bỏ lỗi API/parse rồi báo PASS. | Phần thiếu bị che, kết luận vượt phạm vi. | Fail-closed đối với completeness, quarantine, log lỗi và retest. |
| Đóng finding ngay khi có ảnh “đã sửa”. | Control có thể vẫn không hiệu lực ở runtime/scope khác. | Retest đúng tiêu chí, giữ before/after evidence và review. |
| Gọi mọi trường hợp chưa có dữ liệu là FAIL kỹ thuật. | Kết luận nguyên nhân không được hỗ trợ. | Tách evidence gap khỏi actual control failure. |
| Ngược lại, gọi thiếu evidence là PASS vì không thấy lỗi. | Tạo assurance giả. | INCONCLUSIVE hoặc FAIL coverage theo định nghĩa; mở gap. |
| Gắn nhiều tài liệu vendor nhưng không đọc scope/kỳ. | Bằng chứng không phù hợp service hoặc trách nhiệm khách hàng. | Map provider/customer controls, xem ngoại lệ và ngày hiệu lực. |
| Sao chép evidence nhạy cảm vào ticket công khai. | Rò rỉ secrets, PII, dữ liệu điều tra. | Phân loại, redaction, kho phân quyền và link kiểm soát. |
| Ghi đè verdict lịch sử sau retest. | Không thể biết control từng thất bại trong kỳ. | Versioned assessment, lưu evidence/finding/retest riêng. |

## 19. Checklist thiết kế và đánh giá Evidence chain

Trước khi sử dụng một kết luận assurance, kiểm tra:

1. **Claim:** Mục tiêu bảo mật, control ID và tiêu chí chấp nhận có cụ thể, đo được, được phê duyệt không?
2. **Scope:** Population, asset IDs, account, region, môi trường, thời kỳ và ngoại lệ có được xác định, đối chiếu độc lập không?
3. **Nguồn:** Mỗi artifact có source identity, cách lấy, timestamp, phiên bản công cụ và phạm vi truy vấn không?
4. **Completeness:** Có kiểm tra pagination, lỗi quyền, timeout, dữ liệu rỗng, schema mismatch và tài sản mới không?
5. **Integrity:** Có cơ chế phát hiện thay đổi bằng hash/signature/version/audit phù hợp không; digest được lưu ở nơi đáng tin không?
6. **Lineage:** Raw/derived artifacts có liên kết input-output, transformation, filter và số dòng bị loại rõ không?
7. **Confidentiality:** Bằng chứng được phân quyền, mã hóa, redaction theo mục đích và truy cập hợp lệ không?
8. **Retention:** Kỳ lưu, legal hold khi áp dụng, khả năng truy xuất và chính sách xóa đã được xác định không?
9. **Custody:** Nếu phục vụ điều tra, ai thu, ai bàn giao, ai nhận và thao tác nào làm trên bản gốc/bản sao đã được ghi lại chưa?
10. **Test:** Có phương pháp có thể tái lập, input IDs, kết quả theo đối tượng và giới hạn kỹ thuật không?
11. **Kết luận:** PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE có dựa trên dữ liệu đủ để hỗ trợ claim và không vượt scope không?
12. **Độc lập:** Người phê duyệt/reviewer có thẩm quyền và mức tách biệt hợp lý với người thực hiện control không?
13. **Finding:** Các thiếu sót, ngoại lệ, nguyên nhân và rủi ro được phân biệt, có owner, deadline và cách retest không?
14. **Lịch sử:** Kết quả cũ và mới có version, bằng chứng trước/sau và người duyệt không bị ghi đè không?
15. **Liên tục:** Pipeline thu evidence có giám sát sức khỏe, coverage, freshness và trigger thu lại khi hệ thống thay đổi không?

**Evidence chain tạo ra giá trị assurance khi mọi kết luận đều có thể đi ngược về tiêu chí, phép kiểm tra và nguồn bằng chứng đáng tin, đồng thời mỗi artifact được quản lý có nguồn gốc, toàn vẹn, phạm vi, thời kỳ, quyền truy cập và lịch sử xử lý rõ ràng. Một kết luận mạnh không phải là kết luận luôn PASS, mà là kết luận không che giấu thiếu sót và cho phép người khác kiểm chứng, điều tra và cải tiến.**

# Sensitive data – Nhận diện và bảo đảm bảo vệ dữ liệu nhạy cảm

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **sensitive data (dữ liệu nhạy cảm)** trong phạm vi **privacy assurance**; phân biệt dữ liệu cá nhân, dữ liệu cá nhân cần bảo vệ tăng cường, bí mật doanh nghiệp, thông tin xác thực và dữ liệu nhạy cảm **theo ngữ cảnh**.
- Phân loại dữ liệu dựa trên **mục đích xử lý, khả năng định danh, khả năng liên kết, mức độ gây hại, chủ thể có quyền và bối cảnh pháp lý áp dụng**, thay vì chỉ dựa vào tên cột.
- Lập **data inventory**, sơ đồ luồng dữ liệu và ranh giới tin cậy; phát hiện dữ liệu nhạy cảm ở API, database, cache, queue, logs, traces, analytics, AI, backup, môi trường thử và bên thứ ba.
- Lựa chọn security/privacy controls cho **thu thập, sử dụng, chia sẻ, lưu giữ, truy cập, mã hóa, che giấu, giả danh, xóa và ứng phó sự cố**.
- Thiết kế các yêu cầu và bài test có thể kiểm chứng, bao gồm **positive/negative authorization**, việc chặn rò rỉ ở log, phân tách tenant, vòng đời bản sao và quản trị secret/key.
- Xây dựng hồ sơ **security assurance** theo chuỗi **risk → objective → requirement → control → test → evidence → finding → remediation/retest**, gắn đúng phiên bản và môi trường vận hành.
- Xác định vai trò quyết định, tình huống ngoại lệ, trigger đánh giá lại và chỉ số giám sát, không đồng nhất “có policy” với “đã chứng minh control hiệu quả”.

## 1. Sensitive data là gì?

**Sensitive data** là dữ liệu mà việc truy cập, tiết lộ, kết hợp, sửa đổi hoặc xử lý ngoài phạm vi cho phép có thể gây tác động đáng kể đến cá nhân, tổ chức, hoạt động kinh doanh hoặc hệ thống. Trong **privacy assurance**, trọng tâm là **quyền, lợi ích và tác động đến người mà dữ liệu liên quan**, đồng thời xem xét yêu cầu bảo mật và quản trị để kiểm soát rủi ro.

Không có một danh sách “sensitive data” duy nhất áp dụng cho mọi công ty, ngành nghề và quốc gia. Một trường dữ liệu cần được đánh giá theo **quy định thực sự áp dụng, mục đích và bối cảnh xử lý, khả năng định danh và hậu quả nếu bị sử dụng sai**.

Ví dụ:

- Địa chỉ nhà kết hợp lịch sử mua hàng có thể tiết lộ thói quen cá nhân và tăng rủi ro khi rò rỉ.
- Mã định danh nội bộ tưởng vô hại có thể kết nối với dữ liệu khách hàng ở hệ thống khác.
- Dữ liệu vị trí theo thời gian có thể suy ra nơi ở, thói quen hoặc sự hiện diện tại một địa điểm nhạy cảm.
- Dữ liệu sức khỏe, sinh trắc học, tình trạng tài chính và một số thông tin đời sống riêng tư thường đòi hỏi xem xét và bảo vệ tăng cường.
- Một token truy cập không nhất thiết là “dữ liệu cá nhân” về nội dung, nhưng là **bí mật an ninh quan trọng** vì người có token có thể truy cập dữ liệu cá nhân.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là xây dựng phương pháp đánh giá **có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật: từ đánh giá rủi ro và yêu cầu đến các security controls, kiểm thử, audit và khắc phục. Với sensitive data, cần chứng minh **dữ liệu được xử lý đúng phạm vi, đúng actor, đúng mục đích, đúng thời hạn và đúng biện pháp bảo vệ**, không chỉ có dấu checkbox “encrypted”.

### Phân biệt thuật ngữ

| Thuật ngữ | Trọng tâm | Lưu ý trong đánh giá |
| --- | --- | --- |
| **Personal data** | Dữ liệu liên quan đến cá nhân được xác định hoặc có thể xác định theo quy tắc áp dụng | Có thể định danh gián tiếp khi kết hợp nhiều nguồn |
| **Sensitive personal data / special categories** | Các loại dữ liệu cá nhân được văn bản áp dụng hoặc tổ chức xác định cần bảo vệ cao hơn | Danh mục, điều kiện và nghĩa vụ **phụ thuộc khu vực pháp lý**, không tự suy một danh sách toàn cầu |
| **Confidential business data** | Bí mật công nghệ, hợp đồng, chiến lược, tài sản doanh nghiệp | Có thể rất nhạy cảm dù không liên quan cá nhân |
| **Credentials / secrets** | Khóa riêng, mật khẩu, API key, bearer token, recovery codes | Cần bảo vệ vì có thể mở quyền truy cập; không log hay xuất để làm “bằng chứng” |
| **Derived/inferred data** | Điểm rủi ro, hồ sơ phân loại, dữ liệu suy luận, embeddings | Cần đánh giá khả năng suy ra thông tin nhạy cảm hoặc liên kết danh tính |
| **Pseudonymized data** | Dữ liệu thay định danh nhưng còn khả năng liên kết lại | **Không tự động** trở thành dữ liệu ẩn danh |
| **Anonymized data** | Dữ liệu đã xử lý để không còn nhận dạng theo tiêu chí phù hợp | Phải đánh giá bối cảnh và nguy cơ tái nhận dạng; không chỉ bỏ tên/email |
| **Masked/redacted data** | Giá trị bị che hoặc cắt ở một điểm xử lý | Bản gốc có thể vẫn tồn tại tại nguồn, log, cache hoặc backup |

**Nhạy cảm không chỉ là thuộc tính của một field.** Độ nhạy có thể xuất hiện từ **quan hệ** giữa các field, phạm vi population, độ chính xác, lịch sử theo thời gian và quyền của bên nhận.

## 2. Vì sao privacy assurance phải nhìn khác một bảng phân loại tĩnh?

Một tổ chức thường có hệ phân loại như Public, Internal, Confidential, Restricted. Đó là nền tảng tốt, nhưng chưa đủ nếu chỉ đặt nhãn lên database rồi không kiểm tra hệ thống xử lý thực tế.

### Bốn câu hỏi bổ sung

1. **Đối tượng dữ liệu là ai?** Khách hàng, nhân viên, người dùng, đối tác, trẻ em hoặc người có khả năng bị tác động đặc biệt trong bối cảnh cụ thể.
2. **Những kết luận nào có thể suy ra?** Một tập vị trí, tìm kiếm, lịch sử giao dịch hoặc metadata có thể tiết lộ điều nhạy cảm dù không chứa trường tên `healthCondition`.
3. **Ai nhận và sử dụng dữ liệu cho mục đích gì?** Cùng một trường có thể phù hợp cho đội chăm sóc khách hàng nhưng không phù hợp đưa vào công cụ analytics bên thứ ba.
4. **Điều gì xảy ra nếu người khác biết, sửa hoặc xử lý sai?** Lộ riêng tư, phân biệt đối xử, gian lận, theo dõi trái phép, nguy cơ cho cá nhân hoặc hậu quả nghiệp vụ.

### Ba lớp quyết định phân loại

| Lớp | Câu hỏi | Đầu ra cần thiết |
| --- | --- | --- |
| **Phân loại theo quy định/nghĩa vụ** | Dữ liệu thuộc loại nào theo văn bản và phạm vi áp dụng? | Căn cứ/điều khoản được người có trách nhiệm xác nhận |
| **Phân loại theo nội dung và khả năng liên kết** | Có định danh trực tiếp, gián tiếp, dữ liệu suy luận, secret hay nhóm dữ liệu đặc biệt không? | Data catalog, linkability/inference assessment |
| **Phân loại theo bối cảnh và hậu quả** | Actor, mục đích, thời điểm, độ chi tiết, người nhận và khả năng gây hại thế nào? | Risk scenario, impact, control requirements |

**Ví dụ:** một chuỗi `customerSegment=VIP` có thể mang ít ý nghĩa trong một thống kê tổng hợp, nhưng nếu được liên kết với danh tính và lịch sử giao dịch, nó có thể ảnh hưởng quyền riêng tư, cách phục vụ hoặc khả năng suy luận tình trạng kinh tế. Không phân loại dựa duy nhất vào tên `segment`.

### Không tự biến khuyến nghị kỹ thuật thành lời khẳng định pháp lý

Các chế độ bảo vệ quyền riêng tư có thể yêu cầu điều kiện riêng khi xử lý dữ liệu đặc biệt, thông báo, căn cứ xử lý, lưu giữ hoặc chuyển dữ liệu. **Bài học không đặt ra một nghĩa vụ pháp lý áp dụng chung** hoặc thời hạn lưu cố định; thiết kế thực cần được Data/Privacy/Legal Owner kiểm tra theo khu vực, hợp đồng, ngành và tình huống cụ thể.

## 3. Nhận diện sensitive data trong toàn bộ vòng đời

Một trường có thể được bảo vệ tốt trong database chính nhưng bị sao chép sang những nơi ít được theo dõi hơn: event bus, cache, DLQ, logs, traces, object storage, hệ thống thử nghiệm, notebook phân tích, công cụ AI hoặc vendor.

### Bản đồ vòng đời

~~~mermaid
flowchart TD
    SUB["Chủ thể dữ liệu / nguồn được phép"] --> IN["Collection / API ingestion"]
    IN --> APP["Spring Boot services"]
    APP --> DB[("Database")]
    APP --> CACHE[("Cache / Search")]
    APP --> QUEUE["Queue / DLQ / Events"]
    APP --> OBS["Logs / Traces / Monitoring"]
    APP --> OUT["Exports / File downloads"]
    APP --> VENDOR["Third-party service"]
    DB --> BACKUP[("Backup / DR replicas")]
    QUEUE --> ANALYTICS["Analytics / ML / Feature store"]
    OUT --> USER["Người nhận / đối tác"]
    DB --> PURGE["Retention / deletion"]
    CACHE --> PURGE
    QUEUE --> PURGE
    OBS --> PURGE
    BACKUP --> PURGE
    ANALYTICS --> PURGE
~~~

Đây là DFD minh họa. Trong hệ thống thật, mỗi đường cần chỉ rõ **tài sản, actor, trust boundary, dữ liệu, mục đích, quyền, người nhận, thời hạn và hình thức bảo vệ**.

### Các bước inventory có thể kiểm chứng

1. Liệt kê **hệ thống và nguồn dữ liệu**: schema, APIs, object stores, brokers, logs, SaaS, pipelines.
2. Thu thập **mục đích xử lý đã duyệt** và danh mục data classes/owners.
3. Xác định **field và derived data**: không chỉ PII dễ nhận dạng, mà cả metadata, join keys, embeddings, scoring.
4. Vẽ luồng **ingress, nội bộ, egress và bản sao**; ghi ranh giới tenant/môi trường/khu vực/đối tác.
5. Kiểm tra **điều kiện truy cập**: user role, workload identity, resource policy, debug access, BI queries, operator privileges.
6. So sánh **design với actual runtime**: manifest, config, query, event schema, logging flags, sample đã được làm sạch.
7. Ghi **điểm chưa đủ chứng cứ**: vùng chưa scan, vendor chưa phản hồi, cache chưa inventory, backup chưa xác minh.
8. Gán owner và thời điểm review; tạo trigger khi thêm field, service, tenant, region hoặc recipient.

### Mẫu data inventory tối thiểu

| Field | Cần trả lời |
| --- | --- |
| Data class và sensitivity | Dữ liệu nào, nhạy cảm theo căn cứ và ngữ cảnh nào? |
| Purpose và approved uses | Vì sao xử lý, có giới hạn sử dụng thứ cấp không? |
| Data subject và source | Liên quan ai, thu ở đâu, có được xác minh chính xác không? |
| Store/copy/recipient | Có những bản sao nào và ai là owner? |
| Actors và effective permissions | User/service/vendor nào đọc, sửa, chuyển hoặc xóa? |
| Protection | Encryption, access, segmentation, redaction, DLP, key governance |
| Retention/deletion | Khi nào kết thúc mục đích, rule/hold/backup xử lý thế nào? |
| Control/evidence refs | Yêu cầu, test và hiện vật chứng minh ở môi trường nào? |
| Open gaps | Chỗ nào chưa kiểm tra hoặc đã phát hiện sai lệch? |

**Một data dictionary có 100% field names không chứng minh đã thấy 100% dữ liệu**, nếu raw payload ở logging agent, API legacy hay replica không nằm trong phạm vi khảo sát.

## 4. Phân loại theo mức độ phơi lộ và nguy cơ suy luận

### Ví dụ dữ liệu cần đánh giá trong ứng dụng

| Dữ liệu | Vì sao có thể nhạy cảm | Rủi ro thường gặp |
| --- | --- | --- |
| Tên + email + số điện thoại | Có thể định danh/liên lạc cá nhân | Lạm dụng liên lạc, phishing, kết hợp với nguồn khác |
| Địa chỉ chính xác và thời điểm giao hàng | Liên hệ vị trí và lịch sinh hoạt | Theo dõi, suy đoán nơi ở/vắng mặt |
| Lịch sử mua hàng hoặc giao dịch | Có thể bộc lộ sở thích và tình trạng kinh tế | Hồ sơ hóa hành vi, lộ giao dịch |
| Dữ liệu sức khỏe | Có thể gây hậu quả nghiêm trọng khi sử dụng sai | Lộ tình trạng sức khỏe, phân biệt đối xử trong một số bối cảnh |
| Hình ảnh sinh trắc học hoặc template xác thực | Có thể gắn danh tính lâu dài | Lạm dụng danh tính/khó thay đổi nếu bị lộ |
| Thiết bị, IP, vị trí, ad identifiers | Có thể liên kết người dùng qua thời gian | Tracking, re-identification |
| Fraud score hoặc mô hình phân loại | Có thể suy ra thông tin và ảnh hưởng quyết định với cá nhân | Dùng sai mục đích, rò logic, thiên lệch |
| Export CSV của khách hàng | Tập nhiều bản ghi nhạy cảm ở một nơi | Tải về ngoài phạm vi, URL còn hiệu lực quá lâu |
| Token/session/secret | Trao khả năng truy cập dù bản thân không là PII | Account takeover, truy cập hàng loạt |
| Hash/embedding/feature vector | Có thể hỗ trợ khôi phục/liên kết thông tin | Linkability, membership inference theo hệ thống |
| Security audit log | Có danh tính, IP, hành động nhạy cảm | Lộ hoạt động, tạo hồ sơ theo dõi, sửa/xóa bằng chứng |

**Một trường có mức rủi ro nhỏ khi đứng riêng có thể trở thành dữ liệu rất nhạy cảm khi kết hợp với nhóm khác.** Không nên xây hệ thống phân loại chỉ dựa vào regex `email|phone|password` rồi tuyên bố mọi dữ liệu nhạy cảm đã được quản lý.

### Dữ liệu phái sinh và suy luận

Ví dụ nhóm ML xây mô hình dự báo churn từ lịch sử giao dịch. Output `churnProbability` có thể gắn với user ID, kết hợp với dữ liệu thu nhập hoặc vị trí. Dù không lưu raw transactions trong feature store, hệ thống vẫn cần đánh giá **tính nhạy cảm của profile, quyền truy cập, thời hạn, sử dụng thứ cấp và khả năng lạm dụng**.

Một embedding không tự vô hại vì con người không đọc được trực tiếp. Có thể tồn tại rủi ro truy xuất, liên kết, suy ra membership hoặc phục hồi thông tin tùy mô hình và dữ liệu. Cần áp dụng threat model phù hợp, không tự kết luận mọi vector là dữ liệu ẩn danh.

## 5. Từ mục đích xử lý tới privacy control objectives

Bảo vệ dữ liệu nhạy cảm bắt đầu bằng việc xác định **mục đích được phép** và **mức thông tin cần cho mục đích**.

Giả sử ứng dụng cần hiển thị trạng thái đơn hàng.

| Trường | Xem trạng thái đơn | Xử lý giao hàng có phê duyệt | Điều tra sự cố được phép |
| --- | --- | --- | --- |
| `orderId` | Cần | Cần | Có thể cần |
| `status` | Cần | Cần | Tùy trường hợp |
| `customerEmail` | Không mặc định | Có thể cần cho kênh thông báo | Theo scope điều tra |
| `deliveryAddress` | Không cần để xem trạng thái | Có thể cần cho giao nhận | Chỉ trong trường hợp liên quan |
| `paymentDetails` | Không cần | Không mặc định | Không mặc định; cần scope riêng |
| `fraudRiskScore` | Không cần hiển thị | Không cần mặc định | Có thể liên quan nhưng cần thẩm quyền |
| `auditEventId` | Không cần hiển thị | Không mặc định | Có thể cần truy vết |
| `userAccessToken` | Không cần | Không cần | Không được sử dụng như “bằng chứng” ở dạng raw |

Từ bảng này thiết lập mục tiêu:

- **OBJ-PRIV-01:** xử lý chỉ những trường cần thiết cho use case đã được duyệt.
- **OBJ-CONF-01:** người/service chỉ truy cập được sensitive data trong phạm vi quyền.
- **OBJ-INT-01:** dữ liệu và quyết định xử lý có kiểm tra nguồn, toàn vẹn và tính đúng đắn cần thiết.
- **OBJ-TRACE-01:** hành động đặc biệt có audit trail đủ cho điều tra nhưng không ghi raw sensitive payload thừa.
- **OBJ-LIFE-01:** dữ liệu/bản sao có vòng đời, retention và deletion phù hợp với mục đích/nghĩa vụ.
- **OBJ-ACCOUNT-01:** những claim về privacy controls có nguồn bằng chứng, owner, thời điểm và phạm vi rõ.

**“Cần cho nghiệp vụ” không tự động “được phép chia sẻ cho bất kỳ bên nhận nào”.** Một trường cần trong backend vẫn có thể không được gửi tới UI, logs, analytics hoặc đối tác.

## 6. Threat modeling cho sensitive data

### Đặt ra các kịch bản cụ thể

| Risk ID | Kịch bản | Tài sản/ảnh hưởng | Control cần thiết |
| --- | --- | --- | --- |
| RISK-SD-01 | User tenant A lấy hồ sơ của tenant B do API chỉ kiểm tra role chung | Bí mật dữ liệu, quyền riêng tư | Object/tenant-level authorization, negative tests |
| RISK-SD-02 | API trả thừa địa chỉ/email trong DTO và gateway log raw response | Lan truyền dữ liệu không cần | DTO allowlist, logging policy và sampling |
| RISK-SD-03 | Worker dùng wildcard IAM role đọc mọi bucket | Workload compromise làm lộ dữ liệu diện rộng | Scoped IAM, workload identity, deny tests |
| RISK-SD-04 | BI export chứa thông tin định danh trong bucket public | Dữ liệu bị tiết lộ ngoài phạm vi | Export approval, storage policy, object lifecycle |
| RISK-SD-05 | Debug trace chứa bearer token | Mạo danh user/service, truy cập tiếp | Không log secrets, rotate, incident response |
| RISK-SD-06 | Dataset giả danh ghép với bảng mapping không kiểm soát | Tái liên kết danh tính | Segregate mappings, purpose/access, reidentification review |
| RISK-SD-07 | Backup phục hồi đưa dữ liệu đã xóa quay lại hệ thống hoạt động | Truy cập ngoài vòng đời | Backup lifecycle, post-restore reconciliation |
| RISK-SD-08 | Nhà cung cấp có quyền dùng dữ liệu cho mục đích chưa duyệt | Secondary use và tăng phơi lộ | Contract/data-flow review, processor controls, evidence |
| RISK-SD-09 | Internal operator tải toàn bộ danh sách khách khi chỉ cần một đơn | Lộ tập dữ liệu lớn, abuse | Least privilege, query limits, approval/monitoring |
| RISK-SD-10 | Mô hình phân tích tạo profile nhạy cảm ngoài mục đích | Phân loại/suy luận sai mục đích | Purpose review, derived-data governance, access controls |

### Attack path qua nhiều lớp

~~~mermaid
flowchart LR
    A["Attacker lấy credential hỗ trợ"] --> B["Support API có role hợp lệ"]
    B --> C["Thiếu kiểm tra resource/tenant"]
    C --> D["Endpoint trả full customer profile"]
    D --> E["Proxy và APM ghi raw response"]
    E --> F["Log warehouse nhiều người đọc"]
    D --> G["CSV export / object storage"]
    F --> H["Rò rỉ, profiling hoặc sử dụng sai mục đích"]
    G --> H
~~~

Chặn một nhánh bằng TLS **không sửa được** các thiếu hụt khác: quyền cấp đối tượng, payload thừa, log raw response và storage access. Một privacy assurance case phải nhận diện **đúng đường gây hại**, không chỉ đánh dấu “HTTPS enabled”.

### Quyết định ưu tiên rủi ro

Xem xét **độ nhạy, kích thước population, khả năng tái liên kết, actor có thể truy cập, exposure mạng, thời gian phơi lộ, blast radius, hiệu lực control hiện tại và độ tin cậy của bằng chứng**. Không dùng đơn thuần số lượng field PII làm điểm rủi ro; một trường chứa dữ liệu định danh sinh trắc học có thể nghiêm trọng hơn nhiều field cấu hình ít nhạy cảm.

## 7. Data minimization cho sensitive data: chỉ lấy và truyền những gì cần

Tối thiểu hóa giúp giảm lượng dữ liệu có thể bị xâm nhập, lộ hoặc sử dụng sai. Với sensitive data, cần thực hiện **tại nguồn và tại mỗi ranh giới**, không chỉ lúc serialize HTTP response.

### Hướng thực hiện

1. **Request:** định nghĩa request DTO có allowlist, xác thực input, tránh yêu cầu thêm dữ liệu không có mục đích.
2. **Business logic:** không lấy trường nhạy cảm vào memory/cache khi tác vụ không cần.
3. **Database:** projection và filter theo **trusted tenant/resource scope** thay vì `SELECT *`.
4. **Response:** response DTO riêng theo use case, user role và mục đích; không serialize JPA Entity.
5. **Events:** publish schema theo consumer purpose; không gửi nguyên customer profile mặc định.
6. **Logs/APM:** chỉ phát metadata cần cho phát hiện, truy vết và vận hành; loại raw token/payload.
7. **Analytics:** dùng aggregate/độ chính xác phù hợp, đánh giá nhóm nhỏ và khả năng tái nhận dạng.
8. **Export:** chọn đúng cột, population, quyền, thời hạn link và vị trí lưu.
9. **Copies:** giảm dataflow và các bản sao không owner; áp dụng retention/deletion cho dữ liệu cũ.

### Vì sao DTO nhỏ vẫn chưa đủ?

Nếu controller tạo `CustomerView(email=null)` nhưng repository đã load toàn bộ lịch sử sức khỏe/địa chỉ, APM log vẫn ghi raw entity hoặc một event consumer nhận profile đầy đủ, thì chỉ có **HTTP response** được tối thiểu. Không được kết luận **end-to-end minimization PASS**.

### Cách ghi nhận một quyết định

Mỗi field nhạy cảm nên có:
- ID data class, mô tả nội dung, nơi dùng và nguồn.
- Mục đích/căn cứ xử lý được người có trách nhiệm xác nhận.
- Actor/recipient cần trường đó; cách cấp quyền và thời hạn.
- Phương án ít chi tiết hơn được cân nhắc và lý do chấp nhận/không chấp nhận.
- Reviewer và version policy/data contract.
- Test/evidence ở môi trường liên quan, cùng hạn chế cần đánh giá thêm.

## 8. Bảo vệ truy cập: authorization, purpose và field-level disclosure

**Authentication** trả lời “ai đang gọi?”. **Authorization** trả lời “người/service này có được làm gì trên tài nguyên nào?”. Với sensitive data, còn cần xem **mục đích được phê duyệt và phạm vi dữ liệu được phép tiết lộ**.

### Ví dụ sự khác biệt

- Một support agent được xem `orderStatus` để hỗ trợ, nhưng không mặc nhiên được tải `customerHealthRecord` nếu dữ liệu này tồn tại.
- Một user được xem **hồ sơ của chính họ** khi được xác thực, nhưng không thể sửa hồ sơ người khác chỉ bằng thay `customerId`.
- Một background worker có quyền xử lý dữ liệu cho một job được phê duyệt, nhưng không được tự lấy toàn bộ customer table.
- Một auditor cần xem một số sự kiện để chứng minh control, nhưng không nhất thiết cần raw token, mật khẩu hay payload.

### Policy decision nên xét nhiều thuộc tính

| Thuộc tính | Ví dụ | Sai lầm nếu bỏ qua |
| --- | --- | --- |
| Authenticated principal | User/workload ID đáng tin | Tin `X-User-ID` từ client |
| Role và quyền hiệu lực | Support agent, case reviewer, customer owner | Chỉ dựa vào tên role chung |
| Resource và ownership | Record thuộc tenant/người nào | BOLA/IDOR, cross-tenant leak |
| Sensitivity label | Restricted, special handling, secret | Một policy cho mọi data class |
| Purpose/case context | Case hỗ trợ đã được duyệt, thao tác user tự phục vụ | Dùng chuỗi `purpose=support` do client tự khai |
| Session/device/risk | Authn level, thời gian, điều kiện truy cập nếu cần | Dùng session cũ/đường khẩn cấp ngoài policy |
| Data contract | Những field được phép hiển thị | Endpoint trả full entity |
| Audit/approval | Ai cho phép và lý do | Quyền đặc biệt không truy vết |

**Purpose string trong API không phải căn cứ tin cậy.** Nếu endpoint nhận `purpose=incident` từ client rồi tự cấp quyền xem hồ sơ nhạy cảm, đó là một đường leo thang. Case assignment, phê duyệt và danh tính caller phải được **kiểm chứng phía server** từ hệ thống thẩm quyền.

### Phân tách nhiệm vụ

Một người có quyền tạo dataset, cấp quyền truy cập và xóa audit logs có thể che giấu việc sử dụng sai dữ liệu. Kiểm soát separation of duties (SoD) nên xem cả **quyền kỹ thuật ở cloud/IAM và quyền nghiệp vụ**, các ngoại lệ khẩn cấp có thời hạn, người phê duyệt và bằng chứng sau sử dụng.

## 9. Java 17 / Spring Boot: quyết định tiết lộ thông tin nhạy cảm

Ví dụ dưới đây minh họa **policy quyết định khi nào có thể trả thông tin liên hệ đầy đủ**. Nó không tự đưa ra kết luận pháp lý về căn cứ xử lý và không dùng một field `purpose` tự khai từ request làm quyền.

### 9.1. Policy thuần Java, kiểm thử độc lập được

~~~java
import java.util.Objects;

public final class ContactDisclosurePolicy {

    public enum Purpose {
        SELF_SERVICE,
        APPROVED_SUPPORT_CASE
    }

    public record Actor(
            String principalId,
            String tenantId,
            boolean authenticated,
            boolean trainedSupportOperator) {}

    public record Subject(
            String principalId,
            String tenantId) {}

    public boolean mayDiscloseRawContact(
            Actor actor,
            Subject subject,
            Purpose purpose,
            boolean caseVerifiedByServer) {

        Objects.requireNonNull(actor, "actor");
        Objects.requireNonNull(subject, "subject");
        Objects.requireNonNull(purpose, "purpose");

        if (!actor.authenticated()) {
            return false;
        }
        if (actor.tenantId() == null ||
                !actor.tenantId().equals(subject.tenantId())) {
            return false;
        }

        // Self-service: đã xác minh đúng chủ thể và tenant.
        if (purpose == Purpose.SELF_SERVICE) {
            return actor.principalId() != null &&
                    actor.principalId().equals(subject.principalId());
        }

        // Hệ thống bên ngoài policy này phải kiểm tra case assignment,
        // quyền theo vai trò và phê duyệt/điều kiện áp dụng tại server.
        return purpose == Purpose.APPROVED_SUPPORT_CASE
                && actor.trainedSupportOperator()
                && caseVerifiedByServer;
    }
}
~~~

**Giới hạn quan trọng:** biến `caseVerifiedByServer` chỉ được lấy từ **trạng thái case đã được hệ thống xác minh**, không được gán theo một boolean do client gửi. `trainedSupportOperator` phải tương ứng quyền hiệu lực đã kiểm chứng, không dựa trên header tự khai. Kiểm tra cùng tenant chỉ là một phần của chính sách: hệ thống hỗ trợ xuyên tenant cần **mô hình ủy quyền khác được đánh giá riêng**, không bỏ kiểm tra.

### 9.2. Unit tests minh họa với JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class ContactDisclosurePolicyTest {
    private final ContactDisclosurePolicy policy =
            new ContactDisclosurePolicy();

    @Test
    void selfServiceMayViewOwnContact() {
        var actor = new ContactDisclosurePolicy.Actor(
                "u-01", "tenant-A", true, false);
        var subject = new ContactDisclosurePolicy.Subject(
                "u-01", "tenant-A");

        assertTrue(policy.mayDiscloseRawContact(
                actor, subject,
                ContactDisclosurePolicy.Purpose.SELF_SERVICE, false));
    }

    @Test
    void anotherTenantMustBeDenied() {
        var actor = new ContactDisclosurePolicy.Actor(
                "u-01", "tenant-A", true, true);
        var subject = new ContactDisclosurePolicy.Subject(
                "u-02", "tenant-B");

        assertFalse(policy.mayDiscloseRawContact(
                actor, subject,
                ContactDisclosurePolicy.Purpose.APPROVED_SUPPORT_CASE, true));
    }

    @Test
    void supportRoleWithoutApprovedCaseIsInsufficient() {
        var actor = new ContactDisclosurePolicy.Actor(
                "support-01", "tenant-A", true, true);
        var subject = new ContactDisclosurePolicy.Subject(
                "u-02", "tenant-A");

        assertFalse(policy.mayDiscloseRawContact(
                actor, subject,
                ContactDisclosurePolicy.Purpose.APPROVED_SUPPORT_CASE, false));
    }

    @Test
    void untrustedActorIsDeniedEvenWithCaseFlag() {
        var actor = new ContactDisclosurePolicy.Actor(
                "support-01", "tenant-A", false, true);
        var subject = new ContactDisclosurePolicy.Subject(
                "u-02", "tenant-A");

        assertFalse(policy.mayDiscloseRawContact(
                actor, subject,
                ContactDisclosurePolicy.Purpose.APPROVED_SUPPORT_CASE, true));
    }
}
~~~

Các test chỉ kiểm chứng **logic hàm với input giả định**. Chúng không chứng minh user/token đã được xác thực, case assignment là đáng tin hoặc database không trả dữ liệu nhạy cảm qua endpoint khác. Muốn có assurance phải thêm **integration tests và runtime verification**.

### 9.3. DTO tách mục đích, tránh trả Entity

~~~java
// DTO dành cho tính năng chỉ cần xem trạng thái yêu cầu hỗ trợ.
public record SupportCaseSummary(
        String caseId,
        String status,
        java.time.Instant updatedAt) {}

// DTO nhạy cảm chỉ dành cho hành động disclosure đã được cấp quyền.
public record ContactDetails(
        String subjectId,
        String email,
        String phone) {}
~~~

Controller/service thực tế nên **chỉ tạo `ContactDetails` sau khi policy phía server cho phép**. Đừng serialize nguyên entity rồi trông chờ UI ẩn trường bằng CSS; dữ liệu vẫn đã được truyền tới trình duyệt, proxy và công cụ quan sát.

### 9.4. Những điều code chưa chứng minh

- Luồng authentication, token issuer/audience và session có hợp lệ không?
- Data Subject/tenant lấy từ nguồn nào, có đúng record trong database không?
- Role support đã qua review và có scope tối thiểu chưa?
- Case được phê duyệt thật hay chỉ có cờ trong request?
- HTTP response, cache, access logs và tracing có chứa email/phone ngoài policy không?
- Quyền export, BI, vendor và backup có thể bỏ qua policy trong service không?
- Xử lý revocation, time-bounded access và audit event đã được test chưa?

Bằng chứng phải mở rộng **qua trust boundaries**, không dừng ở unit test `true/false`.

## 10. Mã hóa dữ liệu nhạy cảm: đúng mục tiêu, đúng key, đúng chỗ

Mã hóa là control quan trọng cho **confidentiality**, nhưng không tự hoàn tất privacy assurance.

### 10.1. Encryption in transit

- Dùng TLS phù hợp giữa các bên có ranh giới tin cậy, không chỉ gateway phía Internet.
- Xác thực endpoint/certificate và cấu hình trust phù hợp; không vô hiệu hóa certificate verification để “chạy được”.
- Xem đường kết nối giữa service–database, service–queue, service–object storage, replication và vendor.
- Nếu TLS termination ở proxy, phải xác định cách bảo vệ đoạn proxy–backend.
- Có bằng chứng config **runtime**, bài test truy cập bất thường và certificate/rotation lifecycle.

**TLS không hạn chế ai được phép xem dữ liệu sau khi request được chấp nhận.** Một API over HTTPS vẫn có thể trả dữ liệu tenant khác hoặc truyền quá nhiều thuộc tính.

### 10.2. Encryption at rest

- Xác định phạm vi: database volume, table/column, application-level, object store và backup.
- Quản lý khóa bằng cơ chế phù hợp, có **owner, quyền sử dụng, rotation, backup, revocation/destruction policy và audit**.
- Tách quyền xem dữ liệu và quyền thay đổi key/policy khi rủi ro yêu cầu.
- Kiểm tra cả **bản sao**: snapshot, restore copy, export, cache persist, temporary files và storage của bên thứ ba.
- Đánh giá giới hạn: mã hóa ổ đĩa/volume bảo vệ một số kịch bản, nhưng không ngăn người có quyền database/application đọc plaintext khi đang xử lý.

Không tự viết thuật toán mã hóa, không tự tạo giao thức bảo quản key, không dùng hashing không phù hợp làm “mã hóa” dữ liệu cần đọc lại. Ưu tiên thư viện và dịch vụ cryptography được đánh giá phù hợp với yêu cầu.

### 10.3. Độ phù hợp của cryptographic control

| Mục tiêu | Cách tiếp cận khả dĩ | Điều phải kiểm chứng |
| --- | --- | --- |
| Bảo vệ kênh khi truyền | TLS với xác thực server hoặc mTLS theo rủi ro | Trust, config, downgrade/bypass, tất cả đường liên quan |
| Bảo vệ bản sao lưu | Encryption at rest và kiểm soát quyền backup | Key access, restore process, backup lifecycle |
| Hạn chế người vận hành hạ tầng đọc trường nhạy cảm | Application/field-level encryption hoặc tách dịch vụ xử lý | Key separation, nơi giải mã, quyền truy cập plaintext |
| Hạn chế lan truyền định danh | Tokenization hoặc pseudonymization | Kho mapping, khả năng đổi ngược, quyền, liên kết dữ liệu |
| Bảo vệ mật khẩu xác thực | Password hashing thích hợp cùng salt và chính sách hiện hành | Không lưu plaintext, migration/credential compromise response |
| Chứng minh integrity/evidence | Hash/signature/audit chain trong mô hình tin cậy | Nguồn tạo, key ownership, đối chiếu, chống sửa cả evidence |

**Hash một email không tự ẩn danh.** Với không gian giá trị có thể đoán được, một hash tĩnh có thể bị thử từ điển hoặc dùng liên kết giữa các datasets. Phải đánh giá mục đích, khả năng đảo/suy đoán và dữ liệu kết hợp.

## 11. Tokenization, pseudonymization, masking và ẩn danh

Các phương pháp này khác nhau về mức độ giảm khả năng nhận dạng và mô hình vận hành.

### 11.1. Masking cho một tình huống hiển thị

Ví dụ support agent chỉ cần xác nhận khách hàng đang dùng đúng email mà không cần đọc toàn bộ địa chỉ. Có thể cho hiển thị một gợi ý đã được duyệt; nhưng **gợi ý cũng có thể làm lộ thông tin** với một số loại dữ liệu. Cần đo rủi ro, độ dễ đoán, population và khả năng kết hợp.

Không tự dùng “hiển thị bốn chữ số cuối” cho mọi loại dữ liệu. Bốn chữ số cuối của một trường có không gian giá trị nhỏ có thể đủ để xác định cá nhân trong một bối cảnh cụ thể.

### 11.2. Pseudonymization

Thay mã khách hàng bằng ID giả danh có thể giảm lộ định danh trực tiếp. Tuy nhiên nếu tồn tại **mapping table**, khóa tái liên kết hoặc các nguồn khác ghép được, dữ liệu vẫn có rủi ro quyền riêng tư. Control phải xét:
- Ai có quyền đọc mapping và những dataset nào?
- Có dùng cùng pseudonym ở nhiều mục đích/đối tác khiến liên kết không mong muốn?
- Key/mapping được giữ và thu hồi thế nào?
- Dataset có trường gián tiếp nhận dạng khác không?
- Khi xóa/điều chỉnh hồ sơ, những bản phái sinh nào bị ảnh hưởng?

### 11.3. Anonymization và aggregation

Để kết luận dữ liệu đã được ẩn danh theo tiêu chí áp dụng, cần **đánh giá khả năng tái nhận dạng trong bối cảnh thực**, không chỉ xóa tên/email. Aggregate theo ngày/quận có thể vẫn lộ hành vi một người nếu nhóm quá nhỏ hoặc truy vấn chồng chéo làm rò dữ liệu.

Với mô hình thống kê hoặc ML, có thể cần các kỹ thuật bảo vệ riêng tư bổ sung, kiểm soát truy vấn hoặc giới hạn kết quả. Không tự khẳng định kỹ thuật nào là bảo đảm tuyệt đối nếu chưa đánh giá dữ liệu, attacker và các giới hạn của phương pháp.

## 12. Logs, traces, metrics và security evidence

Những hệ thống dùng để **bảo đảm bảo mật** cũng có thể chứa dữ liệu nhạy cảm. Ví dụ JWT raw, thông tin thanh toán hoặc nội dung phiếu hỗ trợ được ghi vào log, rồi chuyển tới SIEM/SaaS có nhiều người được phép xem.

### 12.1. Cần ghi điều gì?

Để truy vết hành động nhạy cảm, thường cần metadata như:
- Event/action ID, loại hành động, outcome/decision.
- Principal/service đã xác thực và role/đường cấp quyền ở mức cần thiết.
- Resource reference hoặc correlation ID ít tiết lộ hơn payload.
- Thời điểm, môi trường, phiên bản deployment và nguồn sự kiện.
- Lý do/phê duyệt khi xử lý đặc biệt, ID của hồ sơ case.
- Tình trạng reject/denied và sự kiện thay đổi quyền/chính sách.

**Không lưu raw password, refresh token, access token, private key hoặc full sensitive payload** chỉ để thuận tiện tìm lỗi.

### 12.2. Anti-pattern Java

~~~java
// Không nên: request có thể chứa dữ liệu cá nhân và token.
log.info("Support request received: {}", request);
~~~

Ưu tiên phát một **structured event** được thiết kế rõ nội dung:

~~~java
// logEventId, actorReference và caseReference phải đến từ nguồn
// đáng tin; các biến này là giá trị minh họa đã được xác định.
log.info("sensitive_contact_access event={} actorRef={} caseRef={} result={}",
        logEventId, actorReference, caseReference, "allowed");
~~~

Không nên coi format string trên là bảo vệ toàn diện: một ID có thể vẫn liên kết đến cá nhân; lưu log theo **purpose, permission, retention và classification** thích hợp, kiểm tra nguồn collector và tránh log nhầm PII trong `toString()` hoặc exception message.

### 12.3. Kiểm thử logging end-to-end

Một phép test có giá trị:
1. Gửi request test với **marker giả** được thiết kế để phát hiện rò thông tin.
2. Kiểm tra app logs, reverse proxy, gateway, tracing/APM, queue/DLQ và log collector trong scope.
3. Xác nhận marker nhạy cảm **không xuất hiện trái quy tắc**, nhưng security event cần thiết vẫn đến đầy đủ.
4. Xác minh quyền xem log, retention, người sở hữu và sự cố mất log.
5. Gắn test run với deployment/config version và nơi thu evidence.

**Log trống không đồng nghĩa kiểm soát tốt.** Collector có thể bị lỗi hoặc mất quyền đọc nguồn, nên phải đồng thời kiểm tra **telemetry completeness**. Một cơ chế chỉ trả “không tìm thấy PII” nhưng đã mất 70% nguồn log là bằng chứng không đủ.

### 12.4. Privacy của chính bằng chứng audit

Bằng chứng assurance có thể chứa danh tính, hành động, risk profile hoặc thông tin khách hàng. Nên dùng **metadata, hash/digest có mục đích, marker test, counts, schema/version, sanitized report**, thay vì sao chép toàn bộ bản ghi nhạy cảm vào ticket hoặc spreadsheet audit.

Cần quản lý owner, access, integrity, retention và chain of custody khi phục vụ điều tra. **Giữ chứng cứ đúng mục đích** không đồng nghĩa giữ raw data mãi mãi.

## 13. Sensitive data ở non-production và trong CI/CD

Test và staging không tự động ít nhạy cảm. Một staging chứa bản sao hồ sơ khách hàng thật có thể mang **rủi ro gần production**, nhất là nếu public ingress, account dùng chung hoặc vendor truy cập rộng.

### Các đường lộ thường gặp

| Đường | Ví dụ lỗi | Yêu cầu |
| --- | --- | --- |
| Database snapshot | Clone production sang dev laptop | Data-owner approval, dữ liệu giả/đã xử lý phù hợp, quyền và vòng đời |
| Test fixtures | Commit CSV khách hàng vào repository | Fixture tổng hợp, secret/PII scanning, xử lý dữ liệu đã lộ |
| CI pipeline | In request body hoặc token vào build logs | Log minimization, quyền CI, redaction tại nguồn |
| Staging gateway | Bật debug raw response khi test | Config policy, effective runtime check |
| Preview environment | URL công khai, data tồn đọng sau PR | Access isolation, TTL/decommission |
| Data science notebook | Copy dữ liệu vào workspace cá nhân | Controlled datasets, scope, output/share review |
| Vendor sandbox | Dùng dữ liệu thật vì thiếu fixture | Hợp đồng/mục đích, test data strategy, chứng cứ xóa |
| Backup của test | Snapshot tồn tại sau khi staging bị xóa | Retention/backup inventory và purge |

**Một tập dữ liệu “đã ẩn tên” chưa chắc ẩn danh.** Nếu còn ngày sinh đầy đủ, vị trí hoặc ID liên kết với CRM, rủi ro vẫn tồn tại. Muốn dùng dữ liệu sản xuất để test cần có phương pháp và thẩm quyền phù hợp, không tự coi là hợp lệ.

### Chiến lược test data

Ưu tiên:
- Synthetic fixtures có cấu trúc giống nghiệp vụ nhưng không chứa người thật.
- Dataset đã được xử lý phù hợp cho mục đích kiểm thử, có đánh giá khả năng tái liên kết.
- Identifier cố ý không hợp lệ hoặc domain test như `example.invalid`.
- Quy trình phân quyền, hạn lưu, xóa và kiểm chứng khi test kết thúc.
- Negative tests về quyền, tenant và log với **marker giả**, không cần dữ liệu thật.

Nếu test phải dựa vào đặc tính hiếm trong dữ liệu thật, tài liệu hóa lý do, phạm vi giới hạn và các control bổ sung; không mặc định dùng toàn bộ bản sao production.

## 14. Chia sẻ và chuyển sensitive data tới bên thứ ba

Các tổ chức thường gửi dữ liệu tới đối tác giao hàng, dịch vụ thanh toán, CRM, analytics, identity provider hoặc SaaS monitoring. Đây là **trust boundary** riêng, không chỉ là lời gọi HTTP.

### Câu hỏi đánh giá

1. Ai là bên nhận, vai trò và trách nhiệm được xác định thế nào theo bối cảnh áp dụng?
2. Mục đích chia sẻ và trường dữ liệu **thực sự cần** của bên nhận là gì?
3. Bên nhận có được sử dụng cho mục đích phụ, lưu tiếp, chia sẻ tiếp hoặc huấn luyện mô hình không? Những điều khoản nào được áp dụng?
4. Dữ liệu đi qua vùng địa lý, lưu trữ, backup và nhà thầu phụ nào?
5. Những identity/API keys được cấp quyền như thế nào? Có giới hạn theo hành động/resource và ngày hết hạn không?
6. Có cơ chế bảo vệ khi truyền/lưu, log, incident response và xóa theo hợp đồng không?
7. Ai có thể thu thập evidence bên nhận và kiểm chứng lời khẳng định?
8. Nếu nhà cung cấp thay đổi API, scope hoặc subprocessor thì trigger review ở đâu?

Không kết luận “vendor compliant” chỉ dựa vào badge trên website. Cần bằng chứng phù hợp **đúng dịch vụ/phạm vi/thời kỳ**, xem các giới hạn, ngoại lệ và quyền của tổ chức đối với dữ liệu.

### Outbound schema contract

Một phương án thực tiễn là định nghĩa **schema field allowlist cho từng vendor use case**, rồi có contract/integration tests đảm bảo không phát sinh trường nhạy cảm mới khi Entity được mở rộng.

Với webhook, nếu bên nhận chỉ cần `trackingId` và `deliveryStatus`, đừng gửi kèm toàn bộ hồ sơ người mua. Chữ ký webhook bảo vệ tính toàn vẹn và nguồn gửi trong một mô hình, nhưng **không chứng minh dữ liệu được chia sẻ là cần thiết**.

## 15. Data retention, deletion và legal hold

Sensitive data cần có **retention rule theo loại dữ liệu, mục đích và nghĩa vụ**, cùng lifecycle cho bản sao. Thời hạn không thể được chọn bằng nguyên tắc “dữ liệu nhạy cảm phải xóa sau X ngày” áp dụng cho mọi trường hợp.

### Những loại bản sao cần xét

- Database chính, archive và replica.
- Cache và search index.
- Object storage chứa file tạm, export hoặc attachment.
- Queue retry, DLQ, event replay.
- Logs, traces, SIEM, security evidence repository.
- Data warehouse, feature store, ML training snapshots.
- Backup, DR replica, restore copy.
- Vendor copies và hệ thống bên thứ ba.

### Trình tự xử lý khi đến hạn

~~~mermaid
flowchart TD
    A["Data class + policy version + deadline"] --> B{"Có hold/điều kiện giữ hợp lệ?"}
    B -- "Có" --> H["Bảo quản đúng scope, review và giới hạn truy cập"]
    B -- "Không" --> C{"Đến hạn và rule đủ rõ?"}
    C -- "Không/thiếu" --> R["REVIEW, không xóa theo phỏng đoán"]
    C -- "Có" --> D["Purge/anonymize/archive theo rule đã duyệt"]
    D --> E["Xử lý bản sao/caches/events liên quan"]
    E --> F["Reconcile storage và xác minh quyền truy xuất"]
    F --> G["Lưu evidence tối thiểu, finding nếu có lỗi"]
    H --> A
~~~

**TTL không phải bằng chứng đã xóa.** `expiresAt` chỉ biểu thị điều kiện. Cần kiểm tra job, backlog, lỗi từng store và quyền tải thực tế. Một bản backup có thể được xử lý theo chu kỳ khác với dữ liệu sống; quy trình restore phải tránh **làm sống lại bản ghi đã hết hạn hoặc đã bị xóa hợp lệ**.

### Trường hợp legal/preservation hold

Một hold có thể yêu cầu giữ dữ liệu liên quan đến điều tra/tranh chấp trong phạm vi được phép. Nhưng hold cần **thẩm quyền, lý do, phạm vi, thời điểm, review và điều kiện dỡ**. Không dùng hold để kéo dài mọi dữ liệu vô hạn, cũng không xóa mù khi vụ việc cần bảo toàn evidence.

### Data subject requests và yêu cầu liên quan

Yêu cầu truy cập, chỉnh sửa, xóa hoặc hạn chế xử lý có thể xuất hiện tùy quyền và quy định áp dụng. Quy trình cần:
- Xác minh danh tính/người đại diện theo mức độ rủi ro.
- Tra cứu phạm vi dữ liệu và bản sao có thể xử lý, không bỏ sót nguồn phái sinh.
- Kiểm tra **các ngoại lệ, nghĩa vụ và thời hạn hợp lệ** thay vì áp dụng quyền một cách máy móc.
- Thực hiện đúng thao tác ở data stores liên quan, xác minh kết quả.
- Bảo vệ đáp ứng và audit trail khỏi tiết lộ dữ liệu của người khác.
- Nêu giới hạn kỹ thuật/ngoại lệ đã được phê duyệt và nơi cần review.

Đừng tự cho phép người gửi email bất kỳ nhận toàn bộ hồ sơ nhạy cảm chỉ vì yêu cầu “hãy gửi dữ liệu của tôi”. Đây là một **kịch bản identity/authorization** cần kiểm chứng riêng.

## 16. Requirements và security controls có thể đánh giá

Một yêu cầu như “sensitive data phải được bảo vệ tốt” không thể đánh giá. Cần chia thành control objectives đo được và gắn nguồn bằng chứng.

| Requirement ID | Yêu cầu minh họa | Control | Phép kiểm chứng |
| --- | --- | --- | --- |
| **SD-REQ-01** | Data classes nhạy cảm trong service production có owner, purpose, source và copy inventory | Data catalog, DFD review | Đối chiếu schema/API/storage/inventory, xử lý gaps |
| **SD-REQ-02** | Dữ liệu nhạy cảm chỉ được tiết lộ theo actor/resource/purpose đã được duyệt | Fine-grained authorization | Positive/negative tests, cross-tenant và case approval |
| **SD-REQ-03** | API/queue/vendor chỉ gửi field nằm trong approved contract | DTO và schema allowlist | Contract tests, runtime payload sample an toàn |
| **SD-REQ-04** | Dữ liệu trên các ranh giới yêu cầu bảo vệ kênh được truyền có kiểm soát | TLS/mTLS và endpoint trust | Effective config, kết nối không hợp lệ bị chặn |
| **SD-REQ-05** | Sensitive stores và bản sao có bảo vệ lưu/key management theo policy | Encryption, KMS, access separation | Effective config, quyền key, restore test |
| **SD-REQ-06** | Logs/traces không lưu raw secret hoặc payload nhạy cảm ngoài phạm vi | Source logging policy, field filtering | Synthetic marker test, collector sample, coverage |
| **SD-REQ-07** | Service identities và admin roles chỉ có quyền tối thiểu | IAM policy, role review, JIT | Effective grants, deny tests, access review |
| **SD-REQ-08** | Non-prod không dùng dữ liệu thật trái quy tắc | Synthetic test data và transfer gate | Fixture scan, environment inventory, review |
| **SD-REQ-09** | Export/temp data và bản sao được giữ/xóa đúng policy | TTL + purge + reconciliation + backup lifecycle | Test deadline, storage negative access, job evidence |
| **SD-REQ-10** | Chia sẻ với bên thứ ba theo purpose, scope và approval | Vendor agreement/control register | Contract, outbound test, review recipient |
| **SD-REQ-11** | Derived/analytics data có phân loại và đánh giá linkability | Derived-data catalog, aggregation/re-id review | Assessment, query/test, permissions |
| **SD-REQ-12** | Cấu hình hoặc schema đổi phải trigger privacy risk review | CI contract gates, change management | PR, DFD update, tests, deployment validation |
| **SD-REQ-13** | Yêu cầu của data subject được xác minh danh tính và thực hiện đúng phạm vi | Request workflow, authorization và copy tracking | Test impersonation, completion evidence |
| **SD-REQ-14** | Control failed hoặc evidence missing không được báo PASS | Evidence register và finding workflow | Assessment report, reviewer, corrective action |

Tùy framework và nghĩa vụ áp dụng, một số yêu cầu có thể cần mức mạnh hơn hoặc bằng chứng riêng. **Không tự coi đây là bảng chuẩn pháp lý**; đây là cấu trúc kỹ thuật để học cách lập assurance case.

## 17. Thiết kế bộ kiểm thử nhạy cảm theo rủi ro

### Các kiểm thử chức năng và bảo mật

| Test ID | Scenario | Expected result |
| --- | --- | --- |
| **SD-T01** | Actor đọc dữ liệu nhạy cảm của chính mình trong use case được phép | Chỉ nhận field thuộc contract và quyền hợp lệ |
| **SD-T02** | Actor tenant A yêu cầu record tenant B | Bị từ chối; không rò dữ liệu qua body, cache hay lỗi |
| **SD-T03** | Support agent có role nhưng chưa có approved case | Không được tiết lộ raw contact |
| **SD-T04** | Client tự gửi `purpose=incident` hoặc fake role header | Không được tăng quyền |
| **SD-T05** | Entity thêm field nhạy cảm nhưng DTO/schema chưa duyệt | API/queue không tự tăng field |
| **SD-T06** | Request có field ngoài hợp đồng, ví dụ `paymentToken` | Bị từ chối hoặc bỏ qua an toàn, không lưu/chuyển ngoài scope |
| **SD-T07** | Truy cập DB/storage trực tiếp bằng service role ngoài resource được phép | Bị từ chối theo effective IAM policy |
| **SD-T08** | Đổi cấu hình TLS hoặc issuer/trust | Peer/token không hợp lệ bị chặn; đường được phép vẫn hoạt động |
| **SD-T09** | Synthetic request với marker “PII” giả | Không rò marker trái policy ở logs/traces/APM |
| **SD-T10** | Collector hoặc scanner mất quyền và trả ít dữ liệu | Phát hiện missing source; không ghi PASS |
| **SD-T11** | File export hết hạn, có link cũ và bản copy | Không tải được ngoài thời hạn; purge/reconcile theo rule |
| **SD-T12** | Backup cũ được restore vào môi trường thử | Không mở rộng quyền; retention/deletion được kiểm tra lại |
| **SD-T13** | Thêm consumer mới vào event chứa sensitive data | Trigger data purpose review và kiểm soát consumer quyền |
| **SD-T14** | BI aggregate nhóm nhỏ có khả năng suy ra cá nhân | Bị hạn chế, xử lý theo approved re-id risk rule |
| **SD-T15** | DSR/access request do người không có quyền gửi | Không tiết lộ record, có xác minh danh tính và audit |
| **SD-T16** | Cấp quyền khẩn cấp và kết thúc sự cố | Quyền có hạn, thao tác được ghi nhận, revoke được kiểm chứng |
| **SD-T17** | Vendor outbound schema thêm field nhạy cảm | Review/gate hoặc test phát hiện chưa phê duyệt |
| **SD-T18** | Production config drift bật debug body logging | Alert/finding và remediation/retest |
| **SD-T19** | Purge job mất kết nối storage | Không báo thành công giả, retry/backlog, evidence |
| **SD-T20** | Chuyển từ staging sang prod với cấu hình khác | Bằng chứng đúng runtime/deployment, không suy PASS từ staging |

### Cần test những gì ngoài trường hợp “happy path”?

- **Coverage:** endpoints/API versions, tenants, internal APIs, jobs, admin paths, object storage và vendor routes.
- **Identity:** user, support, system account, break-glass, impersonation hoặc subject representation.
- **Context:** purpose, approved case, sở hữu tài nguyên, quyền theo vai trò và điều kiện thời gian.
- **Failure modes:** issuer/collector/KMS lỗi, token hết hạn, backup restore, queue retry, network bypass.
- **Data contract:** field-level allowlist, population, data generated/inferred và độ chính xác.
- **Operational reality:** cấu hình đang chạy, deploy đúng build, cache/replica, evidence freshness.
- **Negative tests:** thao tác bị cấm thực sự bị từ chối, không chỉ “test chính chạy 200 OK”.

Test phải dùng tài nguyên/dữ liệu **được cấp phép**, tránh thao tác nguy hiểm hoặc ghi thêm dữ liệu nhạy cảm vào CI/logs. Với một production-like test, ghi rõ môi trường nào đã được thử để kết luận không vượt quá phạm vi.

## 18. Evidence register và kết luận có căn cứ

### Chuỗi kiểm chứng mẫu

~~~text
RISK-SD-01: User tenant A xem dữ liệu nhạy cảm tenant B
  -> OBJ-CONF-01: Không tiết lộ ngoài quyền tài nguyên/tenant
  -> SD-REQ-02: Field-level và object-level authorization
  -> CTRL-SD-01: Trusted identity + resource ownership + purpose policy
  -> SD-T02 / SD-T03: Cross-tenant và unapproved-case negative tests
  -> EV-SD-01: Policy, CI test, runtime deployment, review
  -> FIND-SD-01: Nếu support API còn đường bypass
  -> REMED-SD-01: Sửa policy/controller, deploy, test lại
  -> RISK-REVIEW-01: Giới hạn còn lại và phê duyệt
~~~

### Mẫu YAML evidence record

Các trường `<...>` là placeholder, **không phải bằng chứng đã được thu thập**. Không ghi raw PII/secret vào ví dụ hoặc hồ sơ nếu không cần thiết.

~~~yaml
assessment_id: SD-ASSURANCE-001
module: SECURITY_SECURITY_ASSURANCE
service: customer-support-api
environment: production
assessment_period: "<START_END_UTC>"
risk_ids: [RISK-SD-01, RISK-SD-02]
objective_ids: [OBJ-CONF-01, OBJ-PRIV-01]
requirement_ids: [SD-REQ-01, SD-REQ-02, SD-REQ-03, SD-REQ-06]
control_ids: [CTRL-SD-01]
claim: "Sensitive contact is disclosed only to approved actors and use cases"
scope:
  endpoints: ["<SUPPORTED_API_PATHS>"]
  resources: ["customer-contact-record"]
  actors: ["verified-data-subject", "authorized-case-operator"]
  data_classes: ["customer-contact"]
  stores: ["application-db", "gateway-log", "audit-event-store"]
  excluded_flows: "<KNOWN_UNTESTED_COPIES_OR_VENDORS>"
data_governance:
  data_owner: "<AUTHORIZED_DATA_OWNER>"
  approved_purpose_refs: ["<PURPOSE_REGISTER_IDS>"]
  sensitivity_policy_version: "<VERSIONED_CLASSIFICATION_POLICY>"
  data_flow_ref: "<DFD_AND_COPY_INVENTORY>"
implementation:
  source_commit: "<COMMIT_ID>"
  artifact_digest: "<ARTIFACT_DIGEST>"
  deployment_id: "<PRODUCTION_DEPLOYMENT_ID>"
  authorization_policy_ref: "<EFFECTIVE_POLICY_VERSION>"
  gateway_logging_config_ref: "<ACTUAL_RUNTIME_CONFIG>"
  retention_policy_ref: "<APPLICABLE_RETENTION_RULE>"
verification:
  observed_at: "<ISO_8601_UTC>"
  positive_test_ref: "<AUTHORIZED_VIEW_RESULT>"
  negative_test_refs: ["<CROSS_TENANT_RESULT>", "<UNAPPROVED_CASE_RESULT>"]
  log_test_ref: "<SANITIZED_MARKER_SCAN_AND_SOURCE_HEALTH>"
  runtime_evidence_refs: ["<AUTHZ_RUNTIME_CHECK>", "<ACCESS_POLICY_SNAPSHOT>"]
  result: "<PASS_FAIL_INCONCLUSIVE>"
  reviewer: "<AUTHORIZED_ASSESSOR>"
findings: ["<FINDING_IDS_IF_ANY>"]
exception_ref: "<APPROVED_EXCEPTION_IF_ANY>"
limitations: "<MISSING_STORES_OR_UNTESTED_RUNTIME_PATHS>"
residual_risk: "<REVIEWED_RISK_RATIONALE>"
reassessment_triggers:
  - "New sensitive field, service, consumer or recipient"
  - "Change in role, IAM, API contract, logging or retention"
  - "Security incident, privacy request, drift or audit finding"
~~~

### Ba nhóm bằng chứng

| Nhóm | Ví dụ | Chưa đủ để suy ra |
| --- | --- | --- |
| **Design** | Data classification, DFD, purpose–field matrix, policy và owner | Production thực tế đang triển khai như tài liệu |
| **Implementation/test** | PR, schema, DTO, query, SAST, contract/negative tests | Không có route cũ, log/bản sao nào ngoài test |
| **Operational effectiveness** | Effective IAM/config, sanitized runtime sampling, access deny, purge, monitoring | Mọi thời điểm, region, tenant và vendor chưa xét đều an toàn |

Một dashboard ghi `encryption=enabled` có thể là **implementation evidence** cho một control, nhưng chưa đủ chứng minh **purpose, authorization, key separation, data minimization, retention và response an toàn**.

### Trạng thái kết luận

- **PASS:** có bằng chứng đủ cho requirement trong phạm vi/môi trường/kỳ đã đánh giá.
- **FAIL:** có dữ liệu kiểm chứng cho thấy control không đáp ứng, ví dụ cross-tenant disclosure.
- **INCONCLUSIVE:** thiếu nguồn quan sát, vendor không có evidence hoặc chưa kiểm tra bản sao quan trọng.
- **NOT_RUN / OVERDUE:** hoạt động chưa diễn ra hoặc trễ lịch đánh giá.
- **EXCEPTION_APPROVED:** quyết định quản trị với phạm vi/thời hạn, không tự biến control FAIL thành PASS.

**Bằng chứng mới không đồng nghĩa bằng chứng tốt.** Một report vừa chạy nhưng đã mất quyền đọc các bucket nhạy cảm có thể trả “0 findings”; cần kiểm chứng **source health, population coverage và sự phù hợp của test**.

## 19. Privacy impact assessment và sự tham gia của các vai trò

Với thay đổi có thể gây ảnh hưởng đáng kể đến quyền riêng tư, có thể cần **privacy impact assessment (PIA)** hoặc **data protection impact assessment (DPIA)** theo chính sách/nghĩa vụ áp dụng. Không mặc định mọi thay đổi đều cần cùng biểu mẫu hoặc một ngưỡng cố định; yêu cầu và thẩm quyền phụ thuộc bối cảnh.

### Những câu hỏi cốt lõi của một assessment

1. **Mục đích:** dùng dữ liệu để làm gì; có hoạt động xử lý mới/thứ cấp không?
2. **Tính cần thiết:** tại sao cần từng loại dữ liệu, độ chi tiết, số lượng và thời hạn đó?
3. **Rủi ro cá nhân:** điều gì có thể gây hại cho chủ thể, kể cả suy luận/profiling và quyết định tự động nếu có?
4. **Data flows:** nguồn, receiver, vendor, region, environments, derived data, backup/retention.
5. **Threat/control:** actor, trust boundary, likelihood/impact và các biện pháp hiện tại.
6. **Residual risk:** sau kiểm soát còn điểm nào chưa xử lý, ai có thẩm quyền quyết định?
7. **Security/privacy testing:** negative tests, contract tests, data inventory verification và bằng chứng runtime.
8. **Chủ thể bị ảnh hưởng:** có cách xử lý yêu cầu, phản hồi, khiếu nại hoặc sự cố thích hợp không?
9. **Review và change triggers:** điều gì khiến kết luận cũ không còn hiệu lực?

### Trách nhiệm điển hình

| Vai trò | Trách nhiệm chính | Bằng chứng cung cấp |
| --- | --- | --- |
| **Business/Product Owner** | Xác định mục đích, nhu cầu nghiệp vụ và phạm vi use case | Approved purpose, acceptance criteria |
| **Data Owner / Data Steward** | Phân loại dữ liệu, owner bản sao, decision field-level | Catalog, purpose–field mapping, inventory |
| **Privacy / Legal / Compliance** | Đối chiếu nghĩa vụ, quyền, điều kiện xử lý và assessment theo bối cảnh | Review, obligations, decisions |
| **Security/AppSec** | Threat modeling, control objectives, test design, phân tích residual risk | Risk register, control mapping, findings |
| **Developer / Tech Lead** | DTO, authorization, query/event/log contract, tests và remediation | PR, CI test, artifact IDs |
| **Ops / SRE / Platform** | IAM, KMS, TLS, storage, backup, logging, runtime config, evidence | Effective policies, deployment, monitoring |
| **Vendor / Procurement Owner** | Quản lý đối tác xử lý dữ liệu, điều khoản/luồng và đánh giá | Vendor agreement, control evidence |
| **Risk Owner / Thẩm quyền** | Quyết định ưu tiên, ngoại lệ, risk treatment theo quyền hạn | Acceptance/exception records |
| **Assessor / Audit** | Đánh giá design và operating effectiveness, giới hạn và retest | Audit trail, review report |

Một tổ chức nhỏ có thể gộp vài vai trò, nhưng vẫn cần xác định **ai đề xuất, ai phê duyệt, ai triển khai, ai review độc lập khi cần và ai chấp nhận residual risk**. Người viết API không mặc nhiên có quyền tự quyết dùng dữ liệu nhạy cảm vào một mục đích mới.

## 20. Case study: sensitive data trong report-service đa tenant

### Bối cảnh

Dịch vụ `report-service` viết bằng Java/Spring Boot cung cấp báo cáo tài chính cho nhiều khách hàng. Các thành phần:
- `report-api` và một `export-worker` trên Kubernetes.
- PostgreSQL chứa giao dịch, email liên lạc, metadata tài khoản.
- Queue và object storage cho file CSV tạm.
- API gateway, APM/tracing và SIEM.
- Data warehouse dùng cho số liệu sản phẩm.
- Backup/DR ở một vùng khác.
- Một vendor hỗ trợ ticket; nhóm support có quyền tìm báo cáo khách hàng.

Khi review, nhóm nhận thấy:
1. API `GET /reports/{id}` trả nguyên `ReportEntity` gồm email, số tài khoản đã được lưu rút gọn, điểm rủi ro nội bộ.
2. Support role có quyền xem tài liệu của mọi tenant nhưng không cần case được phê duyệt.
3. APM lưu raw request/response cho một endpoint export khi debug.
4. CSV sau khi hết hạn vẫn tồn tại tại bucket backup phụ, không có owner.
5. Data warehouse dùng một pseudonym chung trên các sản phẩm, có thể liên kết profile với CRM.
6. Test staging dùng ảnh chụp database sản xuất chứa dữ liệu liên hệ thật.
7. Dashboard chỉ hiển thị `TLS=ON` và `DB_ENCRYPTED=YES`.

### Phân tích finding

| Finding | Vì sao control hiện tại chưa đủ? | Evidence phải tìm |
| --- | --- | --- |
| **F-SD-01:** response thừa field | TLS không chứng minh field cần thiết hoặc được phép tiết lộ | Response contract, field mapping, runtime sample |
| **F-SD-02:** support cross-tenant | Role hợp lệ chưa chứng minh purpose/case/resource authorization | Effective role, case approval policy, negative tests |
| **F-SD-03:** APM raw payload | Bản sao nhạy cảm ở pipeline khác, có người nhận rộng | Runtime APM config, trace sample, access, retention |
| **F-SD-04:** bucket backup chứa CSV cũ | Object lifecycle tại bucket chính không bao phủ bản sao | Store inventory, purge/backups, reconciling evidence |
| **F-SD-05:** liên kết pseudonym | Giả danh chưa đủ ngăn profiling hoặc tái nhận dạng | Join key review, mapping permissions, derived-data assessment |
| **F-SD-06:** staging dùng dữ liệu thật | Non-prod không tự được miễn yêu cầu bảo vệ | Data transfer approval, fixtures, IAM, cleanup |
| **F-SD-07:** dashboard xanh nhưng scope hẹp | Hai thông số không chứng minh privacy control effectiveness | Requirement mapping, control/test/evidence coverage |

### Kế hoạch remediation

1. **Xác nhận rủi ro và scope:** Data Owner/Privacy/Security phân loại các trường nhạy cảm, tenant, bản sao và đường dữ liệu; xem có dấu lộ đã xảy ra cần incident response không.
2. **Giảm phơi lộ ngay nếu cần:** giới hạn support privilege, debug logging và download route theo quy trình được duyệt, đồng thời giữ hiện vật điều tra cần thiết.
3. **Sửa dữ liệu và API contract:** tạo response DTO cho use case, projection ở database, không trả field risk score/email ngoài mục đích.
4. **Sửa authorization:** policy theo actor + case assignment + tenant/resource, không tin purpose/tenant do client tự khai; test các trường hợp denied.
5. **Xử lý telemetry:** bỏ raw body/header ở nguồn và APM; tạo synthetic marker kiểm tra collector; đánh giá bản log cũ theo retention/hold.
6. **Sửa export và các bản sao:** quản lý object TTL, download authorization, bucket inventory, backup lifecycle và reconciliation; kiểm tra restore.
7. **Đánh giá analytics:** giới hạn khả năng liên kết pseudonyms, phân quyền mapping, kiểm tra nhóm nhỏ và mục đích dataset.
8. **Thay test data:** dùng synthetic fixtures hoặc giải pháp giảm nhận dạng phù hợp; kiểm kê bản clone đã tồn tại.
9. **Deploy + verify:** gắn PR, build digest, deployment, actual config, IAM, test results và reviewer; không chỉ kết luận từ staging.
10. **Đóng finding có căn cứ:** retest các đường đã sửa, ghi rõ các vendor/store chưa kiểm chứng, residual risk, owner và hạn review.

### Viết assurance claim đúng phạm vi

**Không nên viết:** “Dữ liệu khách hàng hoàn toàn được bảo vệ vì toàn bộ database đã mã hóa.”

**Có thể viết nếu có bằng chứng:** “Trong phạm vi production `report-api` bản triển khai D được đánh giá, response của endpoint báo cáo chỉ gồm field được Data Owner phê duyệt; actor không có case/tenant quyền phù hợp bị từ chối; logs/APM thuộc phạm vi đã kiểm tra không chứa raw payload nhạy cảm; file export quá hạn ở các bucket được kiểm kê đã được xử lý theo policy. Các bản sao, vendor hoặc trường hợp chưa kiểm chứng được liệt kê.”

Claim không phải bảo đảm tuyệt đối. Nó là **kết luận dựa trên chứng cứ** tại thời điểm, môi trường, phiên bản và phạm vi xác định.

## 21. Đánh giá liên tục, phát hiện drift và chỉ số

### Khi nào cần đánh giá lại?

| Trigger | Việc cần làm | Evidence cần cập nhật |
| --- | --- | --- |
| API/Entity thêm field | Kiểm tra purpose, schema, DTO, query, log/event và người nhận | Data catalog, PR, contract tests |
| Thêm vendor/analytics consumer | Review data sharing, mục đích, scope, retention | DFD, vendor control, outbound tests |
| IAM/role/service account thay đổi | Review quyền hiệu lực, SoD, tenant exposure | Actual IAM policy, positive/negative tests |
| Bật debug/APM/tracing mới | Kiểm tra raw payload/header, source health | Runtime config, sanitized log tests |
| Tạo staging hoặc copy dữ liệu thật | Data classification, bảo vệ, cleanup | Transfer approval, fixture/data checks |
| Thay key/KMS/TLS | Xem trust, key access, restore và rotation | Effective encryption config, tests |
| Thay backup/DR/lifecycle | Bản sao nhạy cảm còn tồn tại/chuyển vùng nào | Backup policy, restore/purge verification |
| Data subject request hoặc incident | Kiểm tra identity, inventory, evidence preservation | Workflow records, test và finding |
| Derived model/feature mới | Re-identification và purpose review | Dataset inventory, model/data assessment |
| Finding hoặc ngoại lệ hết hạn | Reassess residual risk, sửa, retest và approval | Remediation, evidence, decision |

### Metrics cần diễn giải có giới hạn

| Metric | Hữu ích để đo | Không chứng minh |
| --- | --- | --- |
| % sensitive data classes có owner/purpose | Độ bao phủ catalog và quản trị | Dữ liệu đã được tối thiểu hay an toàn |
| % flows có test và runtime evidence | Mức quan sát thực tế | Mọi luồng chưa được tìm đều an toàn |
| Số unauthorized/cross-tenant disclosure findings | Rủi ro đã phát hiện | “0 finding” = không có rủi ro |
| % privileged access được review | Bao phủ review | Mọi quyền hiệu lực đã phù hợp |
| % logs qua synthetic data-leak tests | Kiểm soát ghi dữ liệu ngoài chính sách | Các nguồn log chưa được scan đã sạch |
| Số bản sao/bucket không owner | Shadow data cần xử lý | Ít bản sao hơn luôn ít rủi ro hơn |
| Thời gian từ finding tới verified retest | Khả năng khắc phục và xác minh | Ticket Done = issue đã biến mất |
| Tỷ lệ purge backlog và backup coverage | Vòng đời dữ liệu | Dữ liệu đã xóa đúng mọi nơi |
| Số ngoại lệ/hold quá hạn | Quyết định quản trị cần xử lý | Có exception thì control PASS |
| Freshness của evidence | Hiện vật còn gần runtime không | Report mới tự động đáng tin |

**Không đặt KPI “giảm số field càng nhiều càng tốt”** khi nó có thể phá yêu cầu nghiệp vụ hoặc bằng chứng cần giữ. Mục tiêu là **đúng dữ liệu, đúng mục đích, đúng chủ thể, đúng quyền, đúng thời gian, với kiểm chứng đáng tin**.

## 22. Bài tập thực hành

**Tình huống:** một nền tảng Java/Spring Boot xử lý hồ sơ khách hàng. Hệ thống có API hồ sơ, queue thông báo, Redis cache, audit logs, data warehouse, file export, công cụ support, môi trường staging và backup. Các vấn đề:
- `GET /customers/{id}` trả email, địa chỉ chính xác, lịch sử đơn, điểm rủi ro nội bộ trong mọi response.
- Support role có thể đọc hồ sơ mọi tenant, chỉ khai báo `purpose=support` trong request.
- Consumer analytics nhận cả số điện thoại và lịch sử thanh toán dù chỉ cần doanh thu theo ngày.
- Gateway log lưu `Authorization` header.
- Staging dùng bản sao database khách hàng thật không có lịch xóa.
- Một file CSV export tạm hết hạn vẫn tải được bằng URL cũ.
- Một bảng giả danh trong warehouse có khóa mapping mà quá nhiều tài khoản BI đọc được.
- Risk dashboard hiển thị “privacy compliant” vì storage đã bật encryption.

### Yêu cầu

1. **Phân loại** ít nhất tám trường/loại dữ liệu theo sensitivity, mục đích, chủ thể liên quan và rủi ro liên kết; chỉ rõ vì sao hash hoặc pseudonym có thể vẫn nhạy cảm.
2. Lập **data flow diagram** với các trust boundaries quan trọng, gồm API, tenant, queue, logs, analytics, staging và backup.
3. Viết **ba risk scenarios** mô tả actor, điểm vào, dữ liệu, đường gây hại và hậu quả.
4. Thiết kế **Purpose–Data Matrix** cho chức năng xem profile, hỗ trợ có case được duyệt và thống kê tổng hợp.
5. Đề xuất **năm security/privacy controls** cùng requirements có thể kiểm tra.
6. Viết **ít nhất tám tests**, trong đó có cross-tenant, fake purpose, field allowlist, token/log leakage, queue, export, staging data và warehouse re-linking.
7. Giải thích vì sao encryption at rest, TLS và pseudonymization **không đủ để chấm PASS toàn bộ**.
8. Lập evidence register mẫu gồm data owner, field purpose, actual IAM/config, deployment, tests, reviewer và limitations.
9. Xác định cách xử lý bản sao cũ/backup mà vẫn tôn trọng retention/hold phù hợp.
10. Phân vai Data Owner, Privacy/Legal, Developer, Ops/SRE, Security, Risk Owner và Assessor trong các quyết định xử lý.

### Gợi ý hướng giải

| Vấn đề | Kiểm soát đúng hướng | Bằng chứng cần có |
| --- | --- | --- |
| API trả nhiều field | Response DTO theo use case và actor, query projection phù hợp | API contract tests, runtime response, field mapping |
| Support tin `purpose` | Server-side case approval, object/tenant authorization | Policy, approved-case test và fake-purpose negative test |
| Analytics nhận raw dữ liệu | Consumer purpose schema, aggregate, giới hạn link keys | Data product approval, event sample, query review |
| Gateway log token | Ngừng log tại nguồn, đánh giá token đã lộ, rotate/revoke khi cần | Config diff, synthetic log test, sanitized incident record |
| Staging dùng dữ liệu thật | Dữ liệu giả/đã xử lý phù hợp và vòng đời bản sao | Data-transfer record, scan, access/cleanup evidence |
| File CSV quá hạn còn tải | Expiry enforcement, purge, copy inventory và reconciliation | Negative download test, job/storage evidence |
| Mapping pseudonym rộng quyền | Giới hạn mapping, tách nhiệm vụ, review joinability | Effective access test, derived-data assessment |
| Dashboard dựa vào encryption | Map thêm purpose/access/log/retention/recipient controls | Control/evidence coverage, findings, reviewer |

### Câu hỏi nâng cao

Một team nói: “Chúng tôi đã bỏ email khỏi response và thay customer ID bằng hash, vì vậy dữ liệu trong analytics không còn nhạy cảm.” Nhưng cùng một hash được dùng ở ba sản phẩm, và nhân viên có thể kết hợp thời gian/địa điểm để nhận ra một cá nhân.

**Bạn sẽ đánh giá claim nào PASS, claim nào FAIL hoặc INCONCLUSIVE?**

**Hướng trả lời:** có thể kiểm chứng **response field giảm**, nhưng không suy ra **dataset đã ẩn danh**. Phải đánh giá linkability, reidentification risk, quyền truy cập, mục đích, dataset khác và các đường nhận dữ liệu; kết luận trên bằng chứng đúng phạm vi. Một thay đổi tốt ở HTTP response không khắc phục tự động rủi ro của warehouse.

## 23. Những sai lầm thường gặp

| Nhận định sai | Vấn đề | Thực hành phù hợp |
| --- | --- | --- |
| “Sensitive data chỉ là email và số điện thoại.” | Dữ liệu nhạy cảm còn từ ngữ cảnh, suy luận, vị trí, profile, secret | Xem nội dung, linkability, rủi ro và obligations |
| “Dữ liệu được mã hóa nên có thể chia sẻ rộng.” | Encryption không chứng minh quyền hay mục đích | Purpose, actor/resource authorization, contracts |
| “Một bản hash/ID giả đã ẩn danh hoàn toàn.” | Có thể bị suy đoán hoặc liên kết | Pseudonym mapping và re-identification assessment |
| “Support đã đăng nhập là được đọc mọi hồ sơ.” | Authentication không chứng minh quyền cấp đối tượng/mục đích | Server-side case approval, tenant/resource checks |
| “Không ghi PII trong app logs nên SIEM sạch.” | Proxy/APM/queue/vendor có thể lưu raw payload | E2E inventory, marker tests, source completeness |
| “Collector báo 0 dữ liệu nhạy cảm tức là không có.” | Có thể thiếu quyền hoặc nguồn log đang ngắt | Health/population coverage, INCONCLUSIVE nếu thiếu |
| “Đã có vault/KMS nên secrets không thể lộ.” | Ứng dụng/log có thể đọc hoặc in plaintext | Least privilege, logging controls, runtime tests |
| “Dữ liệu staging không cần chuẩn production.” | Có thể chứa dữ liệu thật và public endpoints | Phân loại theo data/exposure, tách môi trường |
| “Bớt trường trên UI là data minimization end-to-end.” | API, database và event có thể vẫn xử lý thừa | Contract/query/event/log validation |
| “Xóa row database là đã thực hiện deletion.” | Có cache, backup, warehouse, DLQ, vendor | Copy inventory, lifecycle/reconciliation |
| “Legal hold đồng nghĩa giữ mọi dữ liệu vô hạn.” | Hold phải có thẩm quyền, scope và điều kiện dỡ | Hold registry, review, xử lý khi kết thúc |
| “Có quyền truy xuất dữ liệu của tôi thì ai gửi yêu cầu cũng được nhận.” | Có thể tiết lộ dữ liệu cho kẻ giả mạo | Identity verification, case workflow, audit |
| “Privacy audit chỉ cần policy và màn hình cấu hình.” | Control có thể drift hoặc không bao phủ route thực | Runtime evidence, negative tests, retest |
| “Exception được duyệt nghĩa là control đã đạt.” | Risk acceptance không thay effective security control | Báo FAIL/INCONCLUSIVE riêng và residual risk |
| “Bài test staging chứng minh production đạt.” | Quyền, data, log, vendor, version có thể khác | Scope/deployment verification |
| “Đã đóng PR thì finding cũng đã được sửa.” | Fix có thể chưa deploy hoặc thiếu copy/route | Runtime retest và evidence hậu khắc phục |
| “100% data classes được phân loại là đủ.” | Phân loại không chứng minh mục đích/quyền/thời hạn | Mapping kiểm soát trên luồng và đánh giá định kỳ |

## Ghi nhớ

- **Sensitive data là khái niệm phụ thuộc nội dung, ngữ cảnh, khả năng liên kết và hậu quả**, không chỉ một danh sách tên field cố định.
- Privacy assurance cần biết **dữ liệu gì, của ai, vì mục đích nào, đang ở đâu, ai truy cập, được giữ bao lâu và kiểm chứng bằng cách nào**.
- **Authentication, encryption, masking và pseudonymization không tự chứng minh authorization, purpose limitation, minimization, deletion hoặc anonymization.** Các mục tiêu cần được kiểm tra độc lập.
- Dữ liệu nhạy cảm có thể tồn tại trong **derived profiles, queue/DLQ, logs/APM, exports, analytics/ML, backup, staging và vendor** dù API/database chính được bảo vệ.
- Chương trình **SECURITY_SECURITY_ASSURANCE** phải nối **risk → requirement → control → test → evidence → audit/finding → remediation/retest**, gắn scope, environment, version, time, reviewer và limitations.
- **Không có bằng chứng đủ không được tự chấm PASS**; báo FAIL/INCONCLUSIVE và xử lý đúng thẩm quyền, nhất là khi thiếu population hoặc kiểm chứng bản sao.
- **Privacy assurance là hoạt động liên tục** theo vòng đời dữ liệu và thay đổi hệ thống: thêm field, role, consumer, vendor, model, cấu hình log hoặc backup đều có thể làm mất hiệu lực của kết luận cũ.

# Personal Data (Dữ liệu cá nhân) trong Privacy Assurance

## 1. Từ dữ liệu khách hàng tới câu hỏi bảo đảm quyền riêng tư

Một nền tảng hóa đơn SaaS phục vụ nhiều doanh nghiệp lưu tên, email, địa chỉ giao hàng, thông tin giao dịch, lịch sử hỗ trợ và các định danh tài khoản. Đội kỹ thuật có thể đã bật mã hóa database, xác thực nhiều yếu tố và phân quyền theo tenant. Nhưng một job phân tích vẫn tự động gửi email và địa chỉ của khách hàng cho công cụ analytics bên ngoài, dù mục đích báo cáo chỉ cần tổng doanh thu theo tháng.

**Hệ thống có thể chưa bị xâm nhập và mọi API đều hoạt động như thiết kế, nhưng cách xử lý dữ liệu vẫn tạo rủi ro quyền riêng tư.** Đây là lý do phải phân biệt bảo vệ hệ thống khỏi tấn công với đánh giá xem dữ liệu liên quan tới con người **được thu thập, sử dụng, chia sẻ, giữ và xóa có chính đáng, tương xứng, minh bạch, có kiểm soát hay không**.

**Personal data (dữ liệu cá nhân)**, theo cách hiểu nền tảng, là thông tin liên quan tới một cá nhân đã được nhận diện hoặc có thể được nhận diện bằng các phương tiện phù hợp với bối cảnh và quy định áp dụng. Phạm vi pháp lý cụ thể của khái niệm này **thay đổi theo khu vực pháp lý**; tổ chức phải đối chiếu văn bản có hiệu lực và tiêu chí nhận diện của chính mình thay vì mặc định một danh sách duy nhất.

**Privacy assurance** là hoạt động xây dựng và kiểm tra **các tuyên bố có bằng chứng** về cách tổ chức xử lý dữ liệu cá nhân và kiểm soát rủi ro đối với con người. Nó bao gồm data inventory, mục đích xử lý, nghĩa vụ được xác định theo phạm vi, thiết kế control, kiểm tra vận hành, giám sát, audit, khắc phục và đánh giá lại.

Trong module **SECURITY_SECURITY_ASSURANCE**, trọng tâm không chỉ là biết một định nghĩa. Người học cần theo được chuỗi:

**Loại dữ liệu / chủ thể → mục đích và ngữ cảnh → yêu cầu privacy/security → control → phép kiểm chứng → evidence → finding → remediation → residual risk.**

> **Mã hóa và xác thực mạnh không tự chứng minh một hoạt động xử lý dữ liệu là phù hợp.** Privacy assurance phải đánh giá cả các hành vi được hệ thống cho phép nhưng có thể không đáp ứng mục đích, giới hạn sử dụng hoặc kỳ vọng hợp lý của cá nhân.

## 2. Nhận diện dữ liệu cá nhân: trực tiếp, gián tiếp và theo ngữ cảnh

Không nên giới hạn dữ liệu cá nhân vào trường có tên “full_name” hoặc “identity_number”. Khả năng nhận diện có thể xuất hiện khi một giá trị được kết hợp với thông tin mà tổ chức hoặc bên liên quan có thể truy cập hợp lý.

| Dạng dữ liệu | Ví dụ | Vì sao cần xem xét |
| --- | --- | --- |
| **Định danh trực tiếp** | Tên cùng thông tin liên hệ, số định danh cá nhân, thông tin tài khoản định danh. | Có thể chỉ ra một người hoặc hỗ trợ nhận diện trực tiếp. |
| **Liên hệ** | Email cá nhân, số điện thoại, địa chỉ. | Có thể liên kết với một cá nhân; email công việc cũng có thể là dữ liệu cá nhân tùy ngữ cảnh. |
| **Định danh trực tuyến** | User ID, cookie ID, device ID, advertising ID, IP address trong bối cảnh liên kết được. | Có thể nhận diện hoặc theo dõi một người qua phiên, thiết bị hay dịch vụ. |
| **Dữ liệu giao dịch** | Lịch sử mua hàng, hóa đơn, lịch trình sử dụng, yêu cầu hỗ trợ. | Dữ liệu gắn với khách hàng có thể tiết lộ hành vi, tình trạng tài chính hoặc thói quen. |
| **Dữ liệu vị trí/thời gian** | Vị trí chi tiết, thời điểm di chuyển và mẫu truy cập. | Dù không có tên, tổ hợp vị trí và thời gian có thể giúp nhận diện. |
| **Dữ liệu suy ra/phái sinh** | Điểm tín nhiệm, phân nhóm hành vi, sở thích dự đoán. | Một kết quả suy luận vẫn có thể liên quan đến người xác định được. |
| **Thông tin từ người khác** | Nội dung email hỗ trợ chứa số điện thoại người nhận hoặc địa chỉ liên hệ bên thứ ba. | Một bản ghi có thể chứa dữ liệu của nhiều người, không chỉ chủ tài khoản. |

### Ba câu hỏi thực hành

1. **Thông tin có liên quan tới người không?** Ví dụ một mã đơn hàng có thể gắn với một người mua qua hệ thống tra cứu.
2. **Ai có khả năng liên kết thông tin với người đó?** Tổ chức có bảng ánh xạ ID→email, còn đối tác có thể có nguồn bổ sung.
3. **Ngữ cảnh hoặc tập dữ liệu kết hợp có thay đổi mức nhận diện không?** Một thống kê nhóm nhỏ hoặc vị trí chính xác có thể làm tăng khả năng suy ra danh tính.

Ví dụ số hóa đơn không chứa tên trực tiếp nhưng nếu nhân viên support tra được khách hàng từ số hóa đơn, nó có thể thuộc phạm vi dữ liệu cá nhân trong hoạt động xử lý đó. Ngược lại, thông tin thuần mô tả một máy chủ không gắn với người trong ngữ cảnh cụ thể có thể không phải dữ liệu cá nhân; cần tránh gắn nhãn theo tên trường mà bỏ qua **khả năng liên kết thực tế**.

### Dữ liệu của tổ chức và dữ liệu của cá nhân có thể cùng tồn tại

Tên công ty là thông tin doanh nghiệp, nhưng hồ sơ công ty chứa **tên người đại diện, email nhân viên hoặc ghi chú về khách hàng** vẫn có thể có dữ liệu cá nhân. Một bảng B2B không mặc nhiên nằm ngoài phạm vi privacy chỉ vì khách hàng thanh toán là pháp nhân.

## 3. Dữ liệu cần bảo vệ tăng cường và ảnh hưởng khi xử lý sai

Một số loại thông tin có thể gây ảnh hưởng lớn hơn đối với người liên quan khi bị tiết lộ, sử dụng sai, liên kết hoặc quyết định không phù hợp. Tùy khung pháp lý và mục đích, chúng có thể được gọi là **dữ liệu nhạy cảm**, **dữ liệu đặc biệt** hoặc một nhóm bảo vệ tăng cường khác.

| Loại/bối cảnh minh họa | Nguy cơ đối với cá nhân | Hướng kiểm soát cần cân nhắc |
| --- | --- | --- |
| Thông tin sức khỏe, điều trị hoặc tình trạng nhạy cảm. | Phân biệt đối xử, tổn hại danh dự, xâm phạm đời sống riêng. | Giới hạn mục đích/người nhận, bảo vệ chặt và đánh giá nghĩa vụ chuyên biệt. |
| Thông tin sinh trắc học dùng nhận diện, nếu thuộc phạm vi áp dụng. | Khó thay đổi khi bị lộ; tác động lâu dài tới xác thực và riêng tư. | Kiểm soát mục đích, mẫu/khóa, retention và quy trình thay thế. |
| Thông tin tài chính/giao dịch có thể liên hệ cá nhân. | Gian lận, quấy rối hoặc suy đoán hành vi và tình trạng kinh tế. | Giới hạn quyền, audit truy cập/xuất và chia sẻ đúng mục đích. |
| Vị trí chi tiết, lịch sử di chuyển. | Theo dõi, xâm phạm an toàn cá nhân. | Giảm độ chính xác, thời hạn giữ, kiểm soát kết hợp dữ liệu. |
| Thông tin về trẻ em hoặc nhóm dễ bị tổn thương trong ngữ cảnh áp dụng. | Khả năng ảnh hưởng lâu dài và bất cân xứng. | Cơ chế bảo vệ và thủ tục bổ sung theo nghĩa vụ được xác định. |
| Dữ liệu suy luận về đặc điểm nhạy cảm. | Phân loại hoặc quyết định gây bất lợi dù không trực tiếp thu thập thuộc tính. | Đánh giá mô hình suy luận, mục đích, minh bạch và độ chính xác. |

**Không dùng bảng này để suy ra mọi trường trong mọi nước có cùng danh mục pháp lý.** Tổ chức cần lập **data classification standard** và xác định các nghĩa vụ thực sự áp dụng theo loại dữ liệu, chủ thể, hoạt động xử lý, hợp đồng và địa bàn.

### Nhạy cảm không chỉ là “bí mật”

Thông tin đã được công khai ở một ngữ cảnh có thể vẫn liên quan đến quyền riêng tư khi được **thu thập lại, tổng hợp, lập hồ sơ hoặc sử dụng cho mục đích khác**. Ngoài ra dữ liệu sai còn có thể làm cá nhân bị từ chối dịch vụ, nhận thông báo sai hoặc bị ra quyết định không công bằng; vì vậy privacy assurance phải xét **confidentiality, integrity, availability** và cả **mục đích, quyền kiểm soát, khả năng dự đoán và tác động tới con người**.

## 4. Privacy assurance khác gì information security?

Security assurance thường hỏi: “Hệ thống có chống truy cập trái phép, mất toàn vẹn và gián đoạn theo mục tiêu được đặt không?”. Privacy assurance còn hỏi: “Ngay cả khi truy cập được **cho phép về mặt kỹ thuật**, việc xử lý này có phù hợp mục đích và các quyền/lợi ích áp dụng đối với cá nhân hay không?”.

| Tình huống | Góc nhìn security | Góc nhìn privacy |
| --- | --- | --- |
| Database bị đọc bởi tài khoản không có quyền. | Lỗi authorization/confidentiality. | Có thể là sự cố dữ liệu cá nhân, cần xem loại và số người bị ảnh hưởng. |
| Đội analytics được cấp quyền hợp lệ nhưng nhận email không cần thiết. | IAM có thể hoạt động như thiết kế. | Vấn đề **data minimization/purpose limitation**. |
| Hồ sơ khách hàng bị cập nhật sai. | Integrity thất bại. | Có thể tác động tới quyền sửa dữ liệu, chất lượng quyết định và người bị ảnh hưởng. |
| Log lưu token, email và request payload quá lâu. | Rủi ro lộ bí mật và truy cập log. | Thu thập/retention vượt mục đích, khó đáp ứng yêu cầu liên quan dữ liệu cá nhân. |
| Dùng dữ liệu hành vi để suy luận thuộc tính ngoài mục đích ban đầu. | Không nhất thiết có tấn công. | Có thể là rủi ro profiling, sử dụng ngoài phạm vi và tác động tới quyền của cá nhân. |

### Hai chương trình phải liên kết

Privacy assurance không thay thế các security controls như MFA, encryption, logging và access reviews. Ngược lại, chỉ có security controls không chứng minh các yêu cầu privacy về **minh bạch, giới hạn mục đích, vòng đời, quyền cá nhân, bên nhận và trách nhiệm giải trình**.

Một hệ thống tốt nên tạo được **chuỗi truy vết chung** giữa data asset, loại dữ liệu cá nhân, requirement, control, test, evidence và quyết định rủi ro.

## 5. Vai trò trong hoạt động xử lý dữ liệu cá nhân

Các thuật ngữ và trách nhiệm cụ thể khác nhau theo luật áp dụng. Ở mức thiết kế, nên phân biệt các vai trò sau:

| Vai trò chức năng | Câu hỏi cần trả lời | Ví dụ SaaS |
| --- | --- | --- |
| **Cá nhân có dữ liệu được xử lý (data subject)** | Dữ liệu liên quan ai và quyền/lợi ích nào có thể bị ảnh hưởng? | Người mua hàng, nhân viên khách hàng, người liên hệ trong hóa đơn. |
| **Bên quyết định mục đích và phương thức xử lý** | Ai quyết định tại sao và ở mức cốt lõi dữ liệu được dùng ra sao? | Doanh nghiệp khách hàng hoặc SaaS tùy hoạt động thực tế. |
| **Bên xử lý thay cho bên khác** | Ai thực hiện xử lý theo chỉ dẫn/thỏa thuận trong phạm vi? | SaaS xử lý dữ liệu hóa đơn cho khách hàng trong một dịch vụ. |
| **Bên cùng hoặc độc lập quyết định hoạt động xử lý** | Có nhiều tổ chức quyết định mục đích hoặc có mục đích riêng không? | Một SaaS dùng metadata cho phân tích sản phẩm riêng; cần đánh giá vai trò theo thực tế và luật áp dụng. |
| **Data owner / privacy owner nội bộ** | Ai giải trình về tập dữ liệu, mục đích và yêu cầu bảo vệ? | Chủ sở hữu sản phẩm hoặc bộ phận dữ liệu được chỉ định. |
| **Control owner / system owner** | Ai triển khai và duy trì controls kỹ thuật/quy trình? | Đội IAM, nền tảng dữ liệu, sản phẩm, bảo mật. |
| **Assessor / assurance** | Ai kiểm chứng thiết kế/vận hành và đưa kết luận có phạm vi? | Security/privacy assurance hoặc bộ phận đánh giá được giao. |

**Đừng suy chức năng pháp lý chỉ từ tên hợp đồng hay hạ tầng.** Một tổ chức có thể có vai trò khác nhau đối với dữ liệu khách hàng được xử lý theo hướng dẫn và telemetry của chính dịch vụ. Việc xác định tư cách cụ thể, trách nhiệm, cơ sở xử lý, nghĩa vụ thông báo và thời hạn phải được kiểm tra cùng privacy/legal theo phạm vi có hiệu lực.

### Ví dụ hai mục đích trên cùng một hệ thống

Invoice SaaS nhận địa chỉ người mua để **phát hành chứng từ theo yêu cầu doanh nghiệp**. Đồng thời SaaS muốn dùng các email đó cho **tiếp thị sản phẩm trực tiếp của mình**. Hai hoạt động có thể có **mục đích, vai trò, yêu cầu minh bạch và điều kiện hợp lệ khác nhau**. Không được tự hợp nhất chúng chỉ vì thông tin nằm trong một database.

## 6. Những nguyên tắc cần chuyển thành yêu cầu kiểm chứng

Các nguyên tắc xử lý dữ liệu xuất hiện dưới nhiều tên trong các hệ thống quản trị privacy. Dưới đây là cấu trúc thực hành, **không phải bản thay thế cho văn bản pháp luật cụ thể**.

| Nguyên tắc | Câu hỏi thiết kế | Bằng chứng cần có |
| --- | --- | --- |
| **Mục đích rõ ràng và hợp lệ** | Vì sao cần xử lý? Có mục đích đã duyệt cho từng dòng dữ liệu? | Processing register, quyết định owner, bản mô tả mục đích. |
| **Minh bạch** | Cá nhân nhận được thông tin phù hợp về việc xử lý và bên nhận khi cần? | Nội dung thông báo/notice, phiên bản, test UI/API và quy trình cập nhật. |
| **Giới hạn theo mục đích** | Dữ liệu có bị dùng cho hoạt động mới chưa đánh giá? | Purpose mapping, allowlist của consumer, change approvals. |
| **Data minimization** | Có thể giảm trường, độ chính xác, lượng dữ liệu hoặc thời gian giữ? | Schema/field contract, negative tests, dữ liệu thực ở đích. |
| **Accuracy** | Dữ liệu có chính xác đủ cho mục đích và có cách sửa khi sai? | Validation, correction flow, audit sửa dữ liệu. |
| **Storage limitation** | Có lịch giữ/xóa theo từng mục đích và bản sao? | Retention schedule, job results, verification và ngoại lệ. |
| **Security & confidentiality** | Ai có quyền; dữ liệu được bảo vệ trên các luồng và nơi lưu ra sao? | IAM, encryption/KMS, object-level tests, log access. |
| **Accountability** | Ai quyết định, thực hiện, kiểm tra và xử lý ngoại lệ? | Role/RACI, evidence, audit log, finding, risk register. |
| **Quyền của cá nhân khi áp dụng** | Có quy trình xác minh và xử lý yêu cầu hợp lệ? | Request register, policy, tests, kết quả và giới hạn. |
| **Đánh giá tác động thay đổi** | Thêm dữ liệu/người nhận/mục đích có trigger review không? | PIA/DPIA, threat model, release gate, review decision. |

### Chuyển từ khẩu hiệu sang điều kiện có thể thử

**Mơ hồ:** “Chúng tôi chỉ sử dụng dữ liệu cá nhân phù hợp và an toàn.”

**Có thể đánh giá:** “Luồng báo cáo doanh thu theo tháng chỉ chuyển các trường đã được Data owner phê duyệt; email, số điện thoại, địa chỉ và token không xuất hiện trong event hoặc dataset phân tích thuộc phạm vi; thay đổi schema phải kích hoạt contract test và review.”

**Verification:** so schema nguồn/đích, chạy test với canary field, kiểm tra dataset thật đã làm sạch thông tin, kiểm tra quyền và mapping consumers. **Evidence:** data contract, approval, CI run, warehouse sample và cấu hình quyền trong release được đánh giá.

## 7. Data inventory: biết cá nhân nào, dữ liệu nào và ở đâu

Không thể bảo đảm quyền riêng tư nếu không có **kiểm kê data assets và các hoạt động xử lý**. Một dữ liệu có thể xuất hiện trong bảng production, cache, search index, log, analytics, export file, backup, staging và đối tác.

### Metadata nên có

| Trường inventory | Câu hỏi | Ví dụ minh họa |
| --- | --- | --- |
| **data_asset_id** | Định danh ổn định của tập dữ liệu. | PERSONAL-CONTACT-001 |
| **data subjects** | Dữ liệu liên quan nhóm người nào? | Người mua, người liên hệ doanh nghiệp, nhân viên hỗ trợ. |
| **fields / categories** | Loại trường và độ nhận diện? | Email, phone, địa chỉ, user ID, lịch sử hỗ trợ. |
| **source** | Thu trực tiếp, qua khách hàng, từ IdP hay suy luận? | Customer-provided invoice, SaaS support. |
| **purpose_id** | Mục đích cụ thể được phê duyệt? | INVOICE_DELIVERY; SUPPORT_REQUEST. |
| **applicability / processing condition** | Nghĩa vụ và điều kiện hợp lệ nào áp dụng? | Quyết định theo privacy/legal và hợp đồng đã xác minh. |
| **owner / processor / recipient** | Ai quyết định và ai xử lý/nhận? | Customer organization, SaaS service, email vendor. |
| **classification/impact** | Mức độ nhạy cảm và rủi ro đối với cá nhân? | Confidential; tác động disclosure cao. |
| **storage / lineage** | Data gốc và bản sao ở đâu? | SQL DB, broker, warehouse, cache, backup. |
| **retention/deletion** | Lịch lưu, hold và xử lý bản sao? | Schedule theo mục đích/nghĩa vụ, workflow xóa. |
| **controls/evidence** | Kiểm tra đúng phạm vi bằng gì? | FIELD-ALLOW-01, AUTHZ-02, DEL-03 và test runs. |
| **last_review/trigger** | Khi nào phải đánh giá lại? | Thêm trường, thay mục đích, vendor hoặc khu vực. |

**Data catalog không thể chỉ có tên bảng.** Một bảng tên CUSTOMER_EVENTS chứa định danh, email và thông tin suy ra có thể thuộc nhiều hoạt động xử lý. Cần trace **từ data asset tới purpose và các nơi nhận**, chứ không chỉ ghi classification.

### Derived data vẫn cần xem xét

Một điểm số rủi ro giao dịch, lịch sử click hoặc vector đặc trưng được sinh từ hành vi người dùng có thể vẫn liên quan tới cá nhân có thể được nhận diện. **Việc biến đổi không tự biến dữ liệu cá nhân thành dữ liệu không cá nhân**. Cần đánh giá khả năng liên kết, truy cập ở đích và mục đích.

## 8. Data flow và trust boundaries cho dữ liệu cá nhân

Ví dụ Invoice SaaS có các đường xử lý sau:

~~~mermaid
flowchart LR
    PERSON["Cá nhân / Người mua"] -->|Thông tin hóa đơn| CUSTOMER["Doanh nghiệp khách hàng"]
    CUSTOMER -->|API nhập thông tin| API["Invoice SaaS API"]
    EMP["Nhân viên hỗ trợ"] -->|Yêu cầu hỗ trợ có kiểm soát| API
    API --> DB[("Invoice & Contact DB")]
    API --> EVENT[("Event Bus / DLQ")]
    EVENT --> ETL["Analytics ETL"]
    ETL --> WH[("Warehouse")]
    API -->|Trường được duyệt| MAIL["Email/Delivery Vendor"]
    DB --> BK[("Backup / Archive")]
    API --> LOG[("Security Logging")]
    DB -->|Trả thông tin đã giới hạn| API
~~~

### Ranh giới cần ghi trên bản đồ

- **TB-1 – Cá nhân/doanh nghiệp → SaaS:** mục đích xử lý, dữ liệu cung cấp và tính đúng đắn của các trường.
- **TB-2 – SaaS API → database:** object/tenant authorization, service identity, audit, encryption.
- **TB-3 – API → event/ETL/warehouse:** data minimization, schema evolution, quyền consumer và thời gian lưu.
- **TB-4 – SaaS → vendor:** vai trò mỗi bên, hợp đồng, vùng xử lý, các trường được phép, kiểm tra quyền của vendor.
- **TB-5 – Dữ liệu chính → backup/archive:** quyền phục hồi, retention và xử lý dữ liệu đã phải xóa sau restore.
- **TB-6 – SaaS → security logs:** tránh tự tạo bản sao email/token/địa chỉ không cần thiết trong kho observability.
- **TB-7 – Support → dữ liệu khách:** mục đích truy cập, phạm vi ticket, audit và hạn quyền của nhân viên.

Nếu sơ đồ chỉ có một mũi tên “SaaS → Analytics” mà không liệt kê loại trường, người nhận, quyền, retention và bản sao, nó chỉ là **mô hình ban đầu**. Để làm security/privacy assurance cần đối chiếu schema, cấu hình, tài khoản và telemetry thực tế.

## 9. Bản ghi hoạt động xử lý (processing record) theo mục đích

Nhiều chương trình privacy dùng **record of processing activities** hoặc một sổ quản trị tương đương. Mục tiêu là trả lời **tổ chức đang xử lý dữ liệu cá nhân nào, cho mục đích gì và theo trách nhiệm nào**.

| Activity ID | Chủ thể | Dữ liệu | Mục đích | Nơi nhận | Kiểm tra quan trọng |
| --- | --- | --- | --- | --- | --- |
| PROC-01 | Người mua | Tên, email, hóa đơn | Phát hành/gửi chứng từ theo yêu cầu. | SaaS và dịch vụ gửi được duyệt. | Field minimization, tenant authz, nhà cung cấp, retention. |
| PROC-02 | Nhân viên khách hàng | Account ID, role, login events | Quản lý truy cập vào SaaS. | IAM/IdP, SaaS, log nền tảng. | MFA, account linking, access lifecycle, audit log. |
| PROC-03 | Người liên hệ hỗ trợ | Ticket content, contact details | Giải quyết yêu cầu hỗ trợ. | Helpdesk, support team được phép. | Ticket-scoped access, log redaction, thời hạn. |
| PROC-04 | Người dùng SaaS | Event usage được giảm thiểu | Đo hiệu năng và độ ổn định dịch vụ. | Observability platform. | Purpose, field allowlist, nhận diện gián tiếp, retention. |
| PROC-05 | Người mua/đại diện doanh nghiệp | Dữ liệu giao dịch đã biến đổi | Thống kê doanh thu phục vụ khách hàng. | Analytics/warehouse được phê duyệt. | Schema, aggregation, quyền truy cập, suy diễn và xóa. |

Đây là **ví dụ hoạt động xử lý**, không khẳng định mọi hoạt động đều có cùng căn cứ pháp lý hoặc điều kiện hợp lệ. Cùng một trường email có thể xuất hiện trong PROC-01 và PROC-03 nhưng có **mục đích, bên nhận, thời gian giữ và yêu cầu kiểm chứng khác nhau**.

### Traceability quan trọng

Mỗi activity nên ánh xạ tới **data assets → data flows → control IDs → evidence IDs**. Khi đội kỹ thuật thêm event chứa email, hệ thống cần nhận ra **PROC-05 đã thay đổi**, chứ không chỉ coi đó là một thay đổi JSON không ảnh hưởng privacy.

## 10. Xác định điều kiện hợp lệ, mục đích và consent

Một sai lầm thường gặp là giả định **mọi hoạt động xử lý dữ liệu cá nhân đều phải xin consent** hoặc ngược lại, **có consent cho một mục đích thì dùng cho mọi mục đích**. Các hệ thống pháp lý có thể có nhiều điều kiện/căn cứ khác nhau; loại hoạt động, loại dữ liệu, chủ thể và tư cách các bên cũng ảnh hưởng.

### Quy trình xác định yêu cầu hợp lệ

1. Mô tả hoạt động xử lý **cụ thể**, tránh mục đích mơ hồ như “cải thiện trải nghiệm” nếu không làm rõ dữ liệu, thao tác và người nhận.
2. Xác định vai trò các bên, nhóm người liên quan, loại dữ liệu và địa bàn.
3. Cùng privacy/legal xác định **điều kiện/căn cứ áp dụng**, yêu cầu minh bạch, thời hạn, ngoại lệ và cách chứng minh.
4. Thiết kế thực thi ở application/data pipeline và các thành phần downstream.
5. Kiểm tra vận hành, ghi evidence về version notice, lựa chọn/quyết định, quyền và xử lý yêu cầu khi có.

### Nếu hoạt động dựa vào consent

Cần xem điều kiện đồng ý có thực sự áp dụng và cách thu nhận có đạt yêu cầu tương ứng về nội dung, sự tự nguyện, tính rõ ràng, phạm vi và khả năng rút lại **theo pháp luật áp dụng**. Về kỹ thuật, nên quản lý:

| Thuộc tính | Vai trò |
| --- | --- |
| **subject reference** | Liên kết lựa chọn với đúng cá nhân/tài khoản trong phạm vi. |
| **purpose_id** | Consent dành cho hoạt động nào, không gom mọi mục đích vào một cờ không rõ. |
| **notice/version** | Người dùng đã được trình bày thông tin gì tại thời điểm lựa chọn? |
| **choice/action/timestamp** | Đồng ý, từ chối, cập nhật hoặc rút lại theo hành vi thực và thời gian. |
| **channel/source** | Lựa chọn được thu ở ứng dụng, website, API hay hệ thống được ủy quyền? |
| **applicable context** | Tenant, ứng dụng, phạm vi và điều kiện được phê duyệt. |
| **downstream propagation** | Consumer/job nào phải ngừng hoặc điều chỉnh xử lý khi trạng thái đổi? |
| **retention and evidence** | Bản ghi nào cần giữ để chứng minh trong thời hạn được phép? |

**Không đặt giá trị mặc định “đã đồng ý” khi chưa có căn cứ hợp lệ.** Cũng không tự tuyên bố một lần bấm nút chung là đủ cho những mục đích hoàn toàn khác nhau. Nếu điều kiện hợp lệ không phải consent, vẫn phải lưu **quyết định và evidence phù hợp của điều kiện đó**, thay vì tạo consent giả.

## 11. Transparency: trình bày rõ cách xử lý dữ liệu

**Privacy notice** hoặc một cơ chế thông báo tương ứng giúp cá nhân hiểu trong phạm vi áp dụng: dữ liệu nào được thu thập, vì sao, ai xử lý/nhận, giữ thế nào, quyền liên quan và cách liên hệ.

### Rủi ro về transparency

- UI chỉ thông báo dữ liệu dùng để tạo hóa đơn, trong khi backend âm thầm gửi sang analytics phục vụ mục đích khác.
- Thông báo tồn tại nhưng mô tả quá chung, không phản ánh bên nhận/loại dữ liệu mới.
- Notice được sửa, nhưng không có version để biết người dùng đã thấy thông tin nào.
- App không cập nhật các luồng xử lý khi thay vendor hoặc thêm một loại dữ liệu suy luận.
- Quá nhiều banner nhưng không có khả năng tìm hiểu hoạt động thật sự hoặc thực hiện lựa chọn hợp lệ.

### Các phép kiểm chứng

1. Đối chiếu bản notice và danh sách processing activities thực tế.
2. Kiểm tra các hành trình onboarding, profile, API và ứng dụng di động trong scope.
3. Đối chiếu phiên bản notice với ngày release, thay đổi schema/vender.
4. Kiểm tra nội dung có thể truy cập bởi người dùng và phù hợp ngôn ngữ/kênh được quy định.
5. Nếu có consent, kiểm tra trạng thái ở UI, backend và downstream sau thay đổi lựa chọn.

**Bằng chứng notice được đăng** không tự chứng minh mọi hoạt động xử lý phù hợp. Phải chứng minh **thông báo tương ứng với data flow và mục đích thật**.

## 12. Privacy by Design, Privacy by Default và data minimization

**Privacy by Design** đưa yêu cầu privacy vào kiến trúc và SDLC từ giai đoạn thiết kế; **Privacy by Default** giúp trạng thái mặc định giới hạn việc xử lý và chia sẻ theo mục đích cần thiết, thay vì mở rộng quyền rồi yêu cầu người dùng tự tìm cách tắt.

### Giảm dữ liệu theo nhiều chiều

| Chiều giảm thiểu | Ví dụ | Phép kiểm chứng |
| --- | --- | --- |
| **Trường dữ liệu** | Báo cáo doanh thu chỉ cần amount, period, tenant scope thay vì email/địa chỉ. | Field allowlist, schema contract test và scan warehouse. |
| **Độ chi tiết** | Dùng nhóm vùng thay vì tọa độ chính xác khi mục đích không cần. | Kiểm tra transform và dữ liệu đích. |
| **Số lượng chủ thể** | Chỉ chọn đơn hàng cần xử lý, không tải toàn bộ lịch sử khách hàng. | Test phạm vi truy vấn, export audit. |
| **Thời gian lưu** | File export có vòng đời ngắn phù hợp mục đích. | Storage lifecycle, negative download test sau hết hạn. |
| **Người nhận** | Không gửi dữ liệu đến analytics, marketing hoặc vendor ngoài nhu cầu. | Consumer inventory, network/API logs, contract và tests. |
| **Khả năng liên kết** | Dùng định danh giả thay thế nếu mục đích cho phép và bảo vệ bảng ánh xạ. | Test reidentification risk, key/vault access. |

### Ví dụ: event contract tối thiểu

~~~json
{
  "event_type": "INVOICE_PAID",
  "schema_version": 2,
  "event_id": "sample-event-001",
  "occurred_at": "2026-11-28T02:00:00Z",
  "tenant_id": "example-tenant",
  "invoice_id": "sample-invoice-8",
  "amount_minor": 125000,
  "currency": "VND"
}
~~~

Đây là **dữ liệu giả định**, không phải sự kiện production. Không có email trong payload **không đồng nghĩa** hoàn toàn không có dữ liệu cá nhân: invoice_id vẫn có thể liên kết tới một người trong hệ thống nguồn. Tuy vậy, contract có thể giảm lượng thông tin gửi cho consumer không cần biết email.

### Test chống schema drift

Khi producer thêm một trường vào Invoice Entity, contract test phải chứng minh sự kiện dành cho analytics **không tự nhận trường mới** qua auto-serialization. Nếu consumer được nhận field mới, cần review mục đích, privacy implications, data classification, retention và quyền.

## 13. Privacy risk assessment, PIA/DPIA và mô hình tác động tới cá nhân

Một số hoạt động xử lý có thể cần **Privacy Impact Assessment (PIA)**, **Data Protection Impact Assessment (DPIA)** hoặc một hình thức đánh giá tương tự theo yêu cầu thực sự áp dụng. Dù tên khác nhau, mục tiêu thực hành là **xác định tác động tới con người trước khi triển khai hoặc thay đổi hoạt động xử lý**.

### Cấu trúc đánh giá

1. **Mô tả hoạt động:** mục đích, loại dữ liệu, người liên quan, bên xử lý/nhận, vùng xử lý và lifecycle.
2. **Tính cần thiết/tương xứng:** liệu có thể giảm fields, volume, precision, retention hoặc sử dụng một phương pháp ít xâm lấn hơn?
3. **Risk scenarios:** rò rỉ, nhận diện lại, sử dụng ngoài mục đích, theo dõi, phân loại sai, quyết định bất lợi, thiếu khả năng sửa/xóa, dữ liệu quá hạn.
4. **Impact:** hậu quả đối với cá nhân và khả năng xảy ra, theo rubric rõ ràng; xem tính bất cân xứng của nhóm dễ bị ảnh hưởng.
5. **Existing controls:** những gì đang thực sự vận hành, phân biệt với kế hoạch.
6. **Proposed treatments:** controls bổ sung, giảm scope, tạm ngừng hoặc thay phương án.
7. **Ownership và quyết định:** ai chịu trách nhiệm, ai đánh giá, ai phê duyệt hoặc cần tham vấn theo nghĩa vụ.
8. **Evidence và review triggers:** cách thử controls và thời điểm đánh giá lại.

### Privacy harms khác rủi ro security thuần túy

| Kịch bản | Privacy harm có thể xảy ra | Bằng chứng cần xét |
| --- | --- | --- |
| Người dùng bị theo dõi xuyên dịch vụ ngoài mục đích. | Mất quyền kiểm soát, suy luận về đời sống riêng. | SDK inventory, tracking requests, lựa chọn người dùng, data flow. |
| Phân tích suy ra một thuộc tính nhạy cảm từ hành vi. | Phân loại bất lợi, tiết lộ thông tin chưa từng trực tiếp cung cấp. | Feature lineage, model outputs, mục đích, kiểm tra suy luận. |
| Hồ sơ cá nhân lỗi thời gây từ chối dịch vụ. | Thiệt hại thực tế do dữ liệu không chính xác. | Quy trình sửa dữ liệu, trace quyết định, thời gian đồng bộ. |
| Consumer nhận email không cần thiết nhưng không có hacker. | Mất giới hạn mục đích, mở rộng chia sẻ và thời gian lưu. | Contract, warehouse schema, access logs, retention. |
| Bản xóa chậm ở search index. | Dữ liệu vẫn có thể xuất hiện sau yêu cầu được xử lý ở database. | Deletion events, index check, SLA, exception. |

### LINDDUN như một phương pháp hỗ trợ

Một số nhóm sử dụng **LINDDUN** để lập mô hình nguy cơ quyền riêng tư như **linkability, identifiability, non-repudiation, detectability, information disclosure, unawareness, non-compliance** theo phiên bản phương pháp được áp dụng. Đây là **công cụ gợi ý phân tích**, không phải checklist tự động đảm bảo tuân thủ. Cần gắn mọi kịch bản với **data flow và tác động thật**, không đếm số nhãn threat để suy ra mức bảo vệ.

## 14. Privacy controls trên hệ thống truy cập đa tenant

Trong SaaS, một account được xác thực có thể vẫn truy cập sai dữ liệu khi thiếu **object-level/tenant-level authorization**.

### Cơ chế cần xét

- Identity được xác minh từ IdP/session, không tin header tự khai.
- Quyền đối với **từng hành động và từng object**, không chỉ role chung.
- Tenant context gắn với principal và dữ liệu đích qua logic đã được duyệt.
- Service account/worker không có quyền mặc định đọc mọi tenant nếu không cần.
- Phân quyền tại export, batch, GraphQL, search, file download và hỗ trợ khách hàng.
- Giới hạn fields trả về, ngay cả khi user được phép xem một đối tượng.
- Audit hành động nhạy cảm và truy cập đặc quyền với tối thiểu dữ liệu cần ghi.

### Người support có thể được phép truy cập nhưng vẫn vượt mục đích

Tài khoản support có vai trò được duyệt nhưng **không mặc nhiên cần đọc tất cả hóa đơn mọi thời điểm**. Có thể cần ticket-scoped access, JIT, approval, masking, theo dõi lý do và thời hạn. Privacy assurance phải kiểm tra **nhu cầu thực sự theo nhiệm vụ** và cách chứng minh từng lần sử dụng.

### Những ca negative test bắt buộc cân nhắc

1. User tenant A yêu cầu hóa đơn tenant B, cả qua API và export.
2. Nhân viên support không có ticket hợp lệ thử xem hồ sơ nhạy cảm.
3. User chỉ có quyền xem cố xuất hàng loạt.
4. Token đã thu hồi hoặc role đổi nhưng phiên cũ còn mở.
5. Worker nhận message có tenantId bị sửa.
6. CDN/object storage trả file với link biết trước nhưng thiếu kiểm tra quyền.

Một test GET HTTP 403 không chứng minh **mọi đường dữ liệu** đáp ứng yêu cầu.

## 15. Mã hóa, key management và giới hạn của kỹ thuật bảo vệ

Mã hóa khi truyền/lưu, quản lý khóa, tokenization và kỹ thuật che dữ liệu là những controls quan trọng. Tuy nhiên, cần đánh giá **rủi ro mà mỗi control xử lý**.

| Control | Hỗ trợ giảm rủi ro | Không tự chứng minh |
| --- | --- | --- |
| **TLS hoặc cơ chế bảo vệ đường truyền** | Giảm nguy cơ đọc/sửa trên kênh. | Người nhận được phép xử lý, giữ và chia sẻ dữ liệu. |
| **Encryption at rest** | Giảm một số rủi ro mất phương tiện hoặc truy cập lớp lưu trữ. | Ứng dụng có quyền giải mã không thể trả dữ liệu sai người. |
| **KMS/secret manager** | Quản trị khóa, quyền sử dụng và vòng đời tốt hơn khi thiết kế đúng. | Quyền gọi API giải mã không bị cấp quá rộng. |
| **Tokenization/pseudonymization** | Giảm tiếp xúc với định danh gốc và có thể hạn chế liên kết. | Dữ liệu đã trở thành vô danh trong mọi bối cảnh. |
| **Masking** | Giới hạn phần dữ liệu hiển thị/đầu ra. | Bản gốc tại API, database, log hoặc warehouse đã được che. |
| **Anonymization** | Có thể giảm khả năng liên hệ với cá nhân nếu phương pháp đạt tiêu chí áp dụng. | Không bao giờ bị tái nhận diện trong mọi dữ liệu/bối cảnh tương lai. |

### Pseudonymization khác anonymization

Thay email bằng một mã ngẫu nhiên nhưng vẫn giữ **bảng ánh xạ** để nối lại là pseudonymization. Dữ liệu như vậy **thường vẫn cần được xem trong phạm vi rủi ro riêng tư và có thể vẫn là dữ liệu cá nhân theo luật áp dụng** khi còn khả năng liên kết hợp lý.

Một tập dữ liệu được tổng hợp/biến đổi có thể ít nhận diện hơn, nhưng nguy cơ **linkage, singling out và inference** còn phụ thuộc độ lớn nhóm, nguồn bổ sung và khả năng của bên nhận. Không được tuyên bố một tập đã ẩn danh chỉ vì xóa cột full_name.

### Các kỹ thuật tăng cường quyền riêng tư

Tùy use case, có thể xét synthetic data, secure aggregation, privacy-preserving computation, differential privacy hoặc cơ chế hạn chế truy vấn. Những phương pháp này có **giả định và tham số bảo vệ riêng**; chẳng hạn một hệ thống dùng differential privacy cần định nghĩa mô hình đe dọa, đơn vị bảo vệ, ngân sách privacy và cách quản lý truy vấn. Không coi việc đặt tên kỹ thuật là bằng chứng đã giải quyết mọi rủi ro reidentification.

## 16. Logging, monitoring và dữ liệu cá nhân trong evidence

Hệ thống cần audit và monitoring để chứng minh security controls nhưng có thể vô tình tạo **một kho dữ liệu cá nhân thứ hai** trong logs/traces.

### Dữ liệu nên tránh ghi thừa

- Password, OTP, access token, refresh token, session cookie, private key.
- Toàn bộ request/response có hóa đơn, địa chỉ, thông tin hỗ trợ hoặc chi tiết sức khỏe.
- URL signed download hoặc headers có secret.
- Chẩn đoán lỗi kèm dữ liệu cá nhân không cần thiết.
- Query chứa tìm kiếm tên, email hoặc nội dung chat nếu không có mục đích được duyệt.

### Một security event cân đối

~~~json
{
  "event_type": "PERSONAL_DATA_EXPORT_DENIED",
  "occurred_at": "2026-11-28T02:30:00Z",
  "request_id": "sample-request-19",
  "actor_ref": "user-ref-example",
  "tenant_ref": "tenant-example",
  "resource_type": "INVOICE_EXPORT",
  "action": "EXPORT",
  "outcome": "DENIED",
  "reason_code": "TENANT_SCOPE_MISMATCH"
}
~~~

Ngay cả các mã tham chiếu cũng có thể được liên kết đến cá nhân; vì vậy **event vẫn có thể cần controls quyền riêng tư, quyền truy cập, retention và purpose**. Không lưu raw request body để “chứng minh” một lần từ chối nếu có thể dùng metadata tối thiểu.

### Evidence chất lượng cần kiểm tra gì?

**Thiết kế:** event schema, field allowlist, lý do thu, quyền collector/SIEM, retention.

**Vận hành:** canary tests chứng minh secret/PII không xuất hiện ngoài mục đích, kiểm tra end-to-end nguồn→collector→store, xử lý log injection, giám sát mất nguồn và review quyền truy cập logs.

**Giới hạn:** không có log về exfiltration **không chứng minh exfiltration không xảy ra** khi source, completeness hoặc thời gian lưu không đủ.

## 17. Data subject requests: quyền cá nhân và kiểm tra thực thi

Quyền được yêu cầu **truy cập, sửa, xóa, hạn chế, phản đối, rút lại consent, nhận/chuyển dữ liệu hoặc các quyền khác** có thể tồn tại với **phạm vi, điều kiện, ngoại lệ và thời hạn khác nhau theo luật áp dụng**. Không phải mọi quyền áp dụng cho mọi hoạt động và không phải mọi yêu cầu đều được thực hiện bằng cách xóa vô điều kiện.

Privacy assurance cần kiểm tra **một quy trình quản trị yêu cầu phù hợp**, không tự phát minh deadline chung.

### Luồng xử lý yêu cầu

~~~mermaid
flowchart TD
    A["Tiếp nhận privacy request"] --> B["Xác minh danh tính và phạm vi thẩm quyền"]
    B --> C["Phân loại yêu cầu, dữ liệu, vai trò và nghĩa vụ"]
    C --> D{"Đủ điều kiện xử lý theo quy tắc áp dụng?"}
    D -- "Chưa / ngoại lệ" --> E["Yêu cầu bổ sung / giải thích / quyết định có thẩm quyền"]
    D -- "Có" --> F["Tìm nguồn, bản sao, processor và recipient"]
    F --> G["Thực thi access / correction / deletion / action phù hợp"]
    G --> H["Kiểm tra nguồn và downstream, xử lý lỗi"]
    H --> I["Ghi kết quả, giới hạn, evidence và phản hồi"]
    E --> I
    I --> J["Theo dõi tái phát, xóa sau restore, reassessment"]
~~~

### Xác minh đúng người nhưng không thu thêm dữ liệu quá mức

Trước khi tiết lộ hoặc sửa hồ sơ phải xác định người yêu cầu có thẩm quyền. Tuy nhiên, bắt mọi người gửi ảnh giấy tờ tùy thân qua email không được bảo vệ có thể **tạo rủi ro privacy mới**. Phương pháp xác minh phải phù hợp mức rủi ro và các kênh tin cậy đã có, giới hạn việc thu thập và lưu thêm tài liệu xác minh.

### Tình huống B2B cần phân rõ trách nhiệm

Trong Invoice SaaS, người mua không nhất thiết có account trực tiếp tại nền tảng; doanh nghiệp khách hàng có thể là đầu mối quan hệ với cá nhân theo hoạt động. Khi nhận yêu cầu, SaaS cần xác định:

- Ai có quyền quyết định/ra chỉ dẫn xử lý đối với mục đích đó?
- Có cần định tuyến yêu cầu tới doanh nghiệp khách hàng hoặc bộ phận privacy không?
- Xác minh người yêu cầu theo cơ chế nào?
- Dữ liệu đã được chia sẻ với email vendor, kho phân tích hoặc bên thứ ba chưa?
- Có nghĩa vụ giữ lại một số hồ sơ trong thời hạn cụ thể không?
- Cần thông báo và ghi nhận kết quả theo quy tắc nào?

**Một nút “Delete” trên portal không đủ để chứng minh toàn bộ quyền và nghĩa vụ đã được thực hiện.**

## 18. Retention, deletion và bản sao downstream

**Retention** phải gắn với loại dữ liệu, mục đích, nghĩa vụ đã xác định và các bản sao cụ thể; không mặc định dữ liệu giữ “để phòng khi cần”.

### Các nơi thường bị bỏ sót

| Nơi dữ liệu tồn tại | Nguy cơ | Kiểm tra cần có |
| --- | --- | --- |
| **Database chính** | Xóa nhầm, xóa thiếu hoặc giữ quá thời hạn. | Retention job, kiểm tra đối tượng, phân quyền xóa và audit. |
| **Cache/search index** | Bản sao còn xuất hiện sau khi nguồn đã xóa. | Propagation/consistency tests, negative lookup. |
| **Event bus và DLQ** | Message chứa dữ liệu cá nhân sống theo retention riêng. | Topic/DLQ inventory, payload scan, ACL và lifecycle. |
| **Analytics warehouse** | Bản sao theo purpose khác và khó định vị từng chủ thể. | Lineage, lookup/deletion/aggregation plan và test ở đích. |
| **File export/object storage** | Link chia sẻ hoặc file tồn tại sau khi hết nhu cầu. | Lifecycle, revoke access, negative download tests. |
| **Logs/observability** | Email và định danh tồn tại lâu hoặc được chuyển vendor. | Log schema, retention, access reviews và các bản sao. |
| **Backups/archives** | Dữ liệu đã xóa có thể quay lại khi restore. | Backup retention, restore-time deletion reconciliation, giới hạn được ghi. |
| **Đối tác ngoài** | Bên nhận không xóa hoặc giữ bản sao phụ. | Transfer record, hợp đồng, cơ chế yêu cầu/xác nhận và evidence đủ phạm vi. |

### Ba mốc cần phân biệt

1. **Request received:** hệ thống biết có yêu cầu, chưa xử lý.
2. **Action applied:** một số nơi đã sửa/xóa/hạn chế theo quyết định.
3. **Result verified:** dữ liệu ở các đích thuộc scope được kiểm tra hoặc giới hạn chưa xác minh đã được ghi nhận.

### Backup và nghĩa vụ giữ lại

Không tự hứa xóa tức thì khỏi mọi bản backup nếu kiến trúc không cho phép hoặc có điều kiện giữ hồ sơ. Có thể cần **lịch vòng đời backup, cơ chế hạn chế truy cập/phục hồi, quy trình tái áp dụng quyết định xóa sau restore** và đánh giá cụ thể của privacy/legal. Một ngoại lệ có lý do và thời hạn phải được ghi rõ, không đổi trạng thái thành “đã xóa mọi bản sao” khi chưa có evidence.

## 19. Đối tác, bên xử lý phụ và chuyển dữ liệu qua ranh giới

Khi dữ liệu cá nhân đi tới email vendor, analytics SaaS, nhà cung cấp cloud, hỗ trợ khách hàng hoặc dịch vụ AI, phải xem xét **bên nhận, mục đích, điều kiện, vai trò, khu vực xử lý và các bản sao**.

### Một lần chuyển dữ liệu cần xác định

1. **Người nhận:** đơn vị và hệ thống nào, có bên xử lý phụ không?
2. **Mục đích:** vì sao chuyển, có cần đủ trường và số lượng như đang chuyển không?
3. **Tư cách và trách nhiệm:** ai quyết định mục đích, ai làm theo chỉ dẫn, đầu mối xử lý yêu cầu?
4. **Phạm vi địa lý/khu vực:** dữ liệu được truyền, xử lý, sao lưu hoặc truy cập từ đâu?
5. **Security/privacy controls:** TLS, IAM, encryption, key ownership, isolation, monitoring, retention.
6. **Contract/procurement evidence:** điều khoản xử lý, giới hạn sử dụng, sự cố, hủy dữ liệu và kiểm tra nhà cung cấp.
7. **Downstream sharing:** bên nhận có dùng nhà cung cấp phụ, chia sẻ tiếp hoặc lưu dữ liệu cho mục đích khác?
8. **Termination:** sau hết hợp đồng hoặc thay mục đích, dữ liệu được chuyển, lưu hoặc hủy ra sao?

**Không mặc định dữ liệu đi qua biên giới luôn được hoặc không được phép.** Nghĩa vụ phụ thuộc pháp luật hiện hành, loại dữ liệu, vai trò các bên, địa bàn và trường hợp cụ thể. Phải được rà soát theo văn bản có hiệu lực và chuyên môn pháp lý tương ứng.

### Bằng chứng vendor không thay thế phần việc nội bộ

Một chứng nhận, báo cáo audit hoặc cam kết của nhà cung cấp có thể hỗ trợ kết luận **trong scope và kỳ đánh giá của họ**, nhưng không chứng minh SaaS đã chỉ gửi các trường cần thiết, cấu hình tenant đúng hoặc xử lý đủ quyền cá nhân. Đây là vấn đề **shared responsibility**.

## 20. Java/Spring: giới hạn dữ liệu cá nhân ở API và event

Để minh họa, giả sử Invoice Entity chứa đầy đủ địa chỉ, email, ghi chú hỗ trợ và trường nghiệp vụ. API hiển thị hóa đơn chỉ nên trả những trường mà principal được phép xem theo mục đích.

### Ví dụ service đọc hóa đơn theo tenant với DTO giới hạn

~~~java
// Mẫu minh họa: các kiểu domain do ứng dụng định nghĩa.
@Service
public class InvoicePrivacyReadService {
    private final InvoiceRepository repository;

    public InvoicePrivacyReadService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public InvoiceSummary readSummary(
            UUID invoiceId, VerifiedPrincipal principal) {

        String tenant = principal.tenantId();
        if (tenant == null || !principal.mayViewInvoiceSummary()) {
            throw new AccessDeniedException("Not authorized");
        }

        Invoice invoice = repository
                .findByIdAndTenantId(invoiceId, tenant)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));

        // Không serialize nguyên Entity (email, address, internal notes).
        return new InvoiceSummary(
                invoice.getId(),
                invoice.getIssueDate(),
                invoice.getAmount(),
                invoice.getCurrency(),
                invoice.getStatus());
    }
}
~~~

**VerifiedPrincipal phải đến từ security context đã xác minh** và tenant không được lấy từ header/client tự khai. Đoạn code chỉ cho thấy ý tưởng **thu hẹp dữ liệu đầu ra và object-level authorization**, không tự chứng minh toàn bộ quyền privacy hoặc xử lý đúng mục đích trong các luồng export, queue và warehouse.

### Ví dụ event DTO dành riêng cho analytics

~~~java
public record InvoicePaidAnalyticsEvent(
        String eventId,
        String tenantId,
        UUID invoiceId,
        long amountMinor,
        String currency,
        Instant occurredAt) {}

// Mapping chỉ từ các trường đã được phê duyệt trong data contract.
InvoicePaidAnalyticsEvent eventForAnalytics(
        Invoice invoice, String trustedTenant, String eventId) {
    return new InvoicePaidAnalyticsEvent(
            eventId,
            trustedTenant,
            invoice.getId(),
            invoice.getAmountMinor(),
            invoice.getCurrency(),
            Instant.now());
}
~~~

Phải kiểm tra **trustedTenant** có nguồn xác thực, event có phát sau transaction đúng quy tắc, idempotency và retry không tạo side effect sai, đồng thời consumer chỉ có quyền cần thiết. ID và amount vẫn có thể là dữ liệu cá nhân **theo khả năng liên kết**, dù không chứa email.

### Bài test thiết yếu

- API trả các trường được phép, không để lộ nội dung khách hàng thuộc tenant khác.
- Khi thêm field nhạy cảm vào Invoice Entity, response/event DTO không tự mở rộng.
- Người dùng không có quyền export không tạo được file hoặc job ở backend.
- Logging và exception handler không ghi raw Entity/headers.
- Data deletion/correction được đồng bộ tới các nơi nhận thuộc scope và có evidence.

## 21. Case study: Analytics nhận dữ liệu cá nhân ngoài mục đích

### 21.1. Bối cảnh và claim ban đầu

Invoice SaaS xử lý hóa đơn cho 200 doanh nghiệp. Mục đích analytics đã được xác định là **đo doanh thu theo tháng và độ ổn định hệ thống**. Data contract phê duyệt số tiền, tháng, mã tenant và event ID; không có nhu cầu chuyển email hoặc địa chỉ người mua.

Đội sản phẩm khẳng định: **“Warehouse chỉ chứa những trường cần cho tổng hợp doanh thu.”**

### 21.2. Phát hiện

Sau khi Invoice Entity được thêm trường customerEmail, producer chuyển sang serialize toàn Entity trong event INVOICE_PAID. Kho analytics nhận email trong ba tuần. Một bảng dashboard có quyền đọc rộng hơn quyền cần thiết.

Đây là **privacy control failure** về data minimization và purpose boundary, ngay cả khi broker và warehouse được mã hóa.

### 21.3. Điều tra phải phân biệt những gì?

| Câu hỏi | Bằng chứng | Tránh suy luận sai |
| --- | --- | --- |
| Email xuất hiện từ thời điểm nào? | Schema diff, release timeline, event mẫu đã bảo vệ, ingestion history. | Không giả định ngày phát hiện là ngày bắt đầu. |
| Bao nhiêu người/tenant có thể liên quan? | Dataset queries được phép, inventory, phạm vi field. | Không khẳng định số người chính xác nếu thiếu data. |
| Ai được quyền xem dữ liệu? | Warehouse grants, group membership, query/export logs. | Quyền rộng không tự chứng minh đã có truy cập thực tế. |
| Dữ liệu đã tới đâu? | Lineage, broker topics, DLQ, dashboards, backups, vendor records. | Không coi warehouse là bản sao cuối cùng. |
| Có mục đích hoặc điều kiện xử lý hợp lệ cho dữ liệu thêm này? | Purpose register, privacy/legal assessment, processing agreement. | Không tự suy “có consent chung” là đủ. |
| Có những hậu quả tiềm tàng nào? | Privacy impact assessment, mức nhạy cảm, data access, retention. | Không chỉ đếm bản ghi mà bỏ tác động tới người. |

### 21.4. Containment, remediation và phối hợp

**Containment:** giới hạn quyền truy cập dataset và các bản export có liên quan, xử lý luồng dữ liệu tiếp diễn theo playbook được phép và bảo toàn evidence cần cho điều tra.

**Remediation tại nguồn:** trở lại event DTO allowlist được quản trị; thêm contract test từ chối field không được phép; gắn schema changes vào privacy review.

**Remediation downstream:** xác định các bản sao tại queue, DLQ, warehouse, report, backup và vendor; xử lý theo quy trình giữ/xóa và nghĩa vụ; rà IAM, retention và quyền export.

**Privacy/legal/governance:** đánh giá nghĩa vụ thông báo/điều tra, người chịu trách nhiệm xử lý, risk decision và giới hạn bằng chứng. **Không tự khẳng định “không có data breach” chỉ vì không có attacker bên ngoài**.

### 21.5. Retest và kết luận có giới hạn

| Test | Expected outcome |
| --- | --- |
| Producer thêm field canary nhạy cảm vào entity. | Event analytics không tự thêm field. |
| Lấy sample event sau fix trong môi trường được phép. | Không chứa email, phone, address hoặc trường cấm. |
| Query warehouse dataset sau thay đổi. | Dữ liệu đầu ra phù hợp schema/mục đích được duyệt. |
| User không thuộc nhóm analytics thử export. | Bị từ chối, có audit thích hợp. |
| Data retention/deletion workflow trên bản sao thuộc scope. | Các hành động được thực thi và có evidence; phần chưa xác minh được ghi rõ. |
| CI/CD schema diff cho release tiếp theo. | Kích hoạt owner review và negative tests. |

Kết luận nên nêu **release, phạm vi luồng, nơi nhận, thời gian và các phần chưa xác minh**. Việc sửa event mới không tự chứng minh mọi bản sao lịch sử đã được xử lý.

## 22. Privacy assurance: Claim – Argument – Evidence

### Hai loại claim

**Design claim:** “Ứng dụng có cơ chế bảo vệ dữ liệu cá nhân theo mục đích, bao gồm field allowlist, tenant authorization, retention và workflow yêu cầu của cá nhân.”

**Operating claim:** “Trong phạm vi các luồng, bản sao và thời kỳ được kiểm tra, các controls đó đã hoạt động theo tiêu chí: dữ liệu không vượt field contract, quyền sai bị từ chối, các yêu cầu hợp lệ được xử lý và evidence được bảo vệ.”

Một tài liệu kiến trúc chỉ hỗ trợ thiết kế, không chứng minh mọi quyết định xử lý thật đã diễn ra đúng. Một test PASS ở staging chưa chứng minh cấu hình production hoặc vendor trong kỳ tương ứng.

### CAE minh họa

**Claim:** “Trong release 2.8, luồng Analytics của Invoice SaaS chỉ xử lý trường được phê duyệt cho mục đích tổng hợp doanh thu; các bản sao thuộc inventory được quản trị quyền và retention.”

**Argument:** “Data inventory và processing register xác định nguồn/đích; producer dùng DTO allowlist, schema tests ngăn mở rộng, consumers có quyền được duyệt; retention và deletion checks theo lịch; drift làm phát sinh finding.”

**Evidence:** processing register/owner approval, data lineage, data contract, integration tests, actual payload sampling có kiểm soát, IAM policies, retention jobs, kết quả downstream verification, findings và retest.

### Ma trận controls và bằng chứng

| Control requirement | Test thiết kế/vận hành | Evidence phù hợp |
| --- | --- | --- |
| **PII-INV-01:** data assets và hoạt động xử lý được nhận diện. | So inventory với schema, logs, pipeline và bản sao. | Catalog, scanner kết hợp manual review, coverage report. |
| **PII-PUR-02:** xử lý có purpose và điều kiện được đánh giá. | Truy vết activity, data fields, recipients tới quyết định đã duyệt. | Processing register, assessment, approval và phiên bản. |
| **PII-MIN-03:** dữ liệu chuyển đúng mục đích, đủ tối thiểu. | Schema contract, canary fields, sample nguồn/đích. | CI logs, event DTO, warehouse scan, exceptions. |
| **PII-AUTHZ-04:** chỉ chủ thể được phép tiếp cận dữ liệu. | Negative cross-tenant/object/support/export tests. | Test report, IAM config, audit events và role review. |
| **PII-TRANS-05:** thông tin/notice và lựa chọn phản ánh hoạt động xử lý. | UI/API test, đối chiếu notice phiên bản với data flows. | Notice history, choice records, mapping activity. |
| **PII-REQ-06:** yêu cầu cá nhân được xử lý theo quy trình áp dụng. | Test xác minh danh tính, routing, response, downstream verification. | Request register đã bảo vệ, decision and action traces. |
| **PII-RET-07:** dữ liệu được giữ/xóa đúng quy tắc. | Job/lifecycle test trên nguồn, cache, warehouse, backup kế hoạch. | Retention schedule, execution logs, deletion evidence. |
| **PII-THIRD-08:** chuyển dữ liệu cho bên thứ ba có kiểm soát. | So actual payload với contract và allowed recipient. | Contract, transfer register, vendor review và config. |
| **PII-LOG-09:** logs không sao chép thừa dữ liệu cá nhân. | Canary tests, field scans, quyền log, kiểm tra collector. | Event schema, redaction tests, log access review. |
| **PII-CHANGE-10:** thay đổi schema/mục đích kích hoạt review. | Test gate thêm consumer/field và kiểm tra approval. | Release diff, pipeline gates, review/PIA records. |

### Bằng chứng có thể chống lại claim

Một dataset thực có email dù contract ghi “không có email” là evidence **không đạt**. Không được xóa mẫu khỏi bộ đánh giá, đổi nhãn hiện vật thành “không liên quan” mà không giải thích hoặc chỉ gửi những screenshot đạt để che finding.

## 23. Kế hoạch kiểm thử privacy controls

Privacy testing cần bao gồm cả **hành vi hợp lệ và tình huống phải bị từ chối**. Các ca dưới đây dành cho môi trường được phép, ưu tiên synthetic data và không cố tạo tiết lộ dữ liệu thật.

| Test ID | Tình huống | Kết quả cần chứng minh |
| --- | --- | --- |
| **PRIV-01** | Thu thập dữ liệu ở một form không yêu cầu trường tùy chọn ngoài mục đích. | Trường không cần không bị gửi/lưu mặc định; lý do trường bắt buộc rõ. |
| **PRIV-02** | Một event analytics thay đổi schema có thêm trường email. | CI/contract ngăn hoặc yêu cầu review; đích không tự nhận email ngoài allowlist. |
| **PRIV-03** | User tenant A truy vấn dữ liệu người thuộc tenant B. | Không trả dữ liệu B qua API, search, batch hoặc export trong scope. |
| **PRIV-04** | Nhân viên support không có ticket/approval đọc hồ sơ. | Bị từ chối hoặc cần điều kiện JIT phù hợp; audit không lộ payload. |
| **PRIV-05** | Tạo file export và đưa URL cho user không có quyền. | Không tải được; kiểm tra object storage/CDN và link TTL. |
| **PRIV-06** | Consent/choice được rút lại khi luồng phụ thuộc lựa chọn này. | Các consumers trong scope cập nhật hành vi theo chính sách và trong giới hạn đã xác định. |
| **PRIV-07** | Chưa có consent hợp lệ với purpose thật sự yêu cầu consent. | Không xử lý theo purpose đó, không tự bật cờ mặc định. |
| **PRIV-08** | Dữ liệu ở profile được sửa hợp lệ. | Nguồn và downstream có cơ chế đồng bộ/giải quyết mâu thuẫn theo scope. |
| **PRIV-09** | Privacy request từ người chưa được xác minh. | Không tiết lộ dữ liệu; xác minh phù hợp, không thu thêm dữ liệu quá mức. |
| **PRIV-10** | Yêu cầu xóa hợp lệ đến hệ thống nhiều bản sao. | Source, cache, index, warehouse và nơi nhận trong scope được xử lý/ghi giới hạn. |
| **PRIV-11** | Restore backup chứa bản ghi đã có quyết định xóa. | Có cơ chế không đưa dữ liệu bị hạn chế trở lại trái quy tắc, hoặc xử lý theo kế hoạch. |
| **PRIV-12** | Ứng dụng phát exception chứa email/secret canary giả. | Log/traces không ghi trường cấm trong pipeline thuộc scope. |
| **PRIV-13** | Vendor nhận payload với trường không có trong contract. | Gateway/contract test phát hiện và ngăn hoặc ghi finding. |
| **PRIV-14** | Tài khoản đặc quyền tải hàng loạt dữ liệu. | Quyền, mục đích, approval, audit và controls hạn chế đủ theo risk. |
| **PRIV-15** | Thêm consumer warehouse hoặc model AI nhận dữ liệu mới. | Kích hoạt data-flow/purpose/PIA review trước khi chia sẻ. |
| **PRIV-16** | Consent choice thay đổi đồng thời với job đã xếp hàng. | Có quy tắc rõ về thời điểm hiệu lực, không tự dùng trạng thái cũ vô hạn. |
| **PRIV-17** | Scanner phân loại không nhận diện được dữ liệu suy luận. | Phát hiện khoảng trống coverage; manual review và correction. |
| **PRIV-18** | Một nguồn logging/collector im lặng hai ngày. | Monitoring nhận diện thiếu evidence; không báo “zero privacy incident” như kết luận đầy đủ. |
| **PRIV-19** | Quyền role tại SaaS bị thu hồi. | Các sessions/cache/download links mất quyền theo requirement có thời gian rõ. |
| **PRIV-20** | Yêu cầu chưa có căn cứ hoặc chịu ngoại lệ giữ dữ liệu. | Quyết định có lý do và thẩm quyền, trả lời đúng quy trình, không xóa trái nghĩa vụ. |

### Không biến công cụ quét thành lời bảo đảm tuyệt đối

Scanner DLP có thể phát hiện một số định dạng như email hoặc số định danh, nhưng có **false positive/false negative**, có thể không phát hiện quan hệ gián tiếp, nội dung phi cấu trúc, hoặc dữ liệu suy luận. Kết hợp tự động hóa với **sample review, data owner validation và negative tests** đúng use case.

## 24. Evidence quality, provenance và bảo vệ hiện vật

Một privacy evidence repository có thể chứa chính những dữ liệu cần bảo vệ. Phải tránh “chứng minh privacy bằng cách sao chép dữ liệu nhạy cảm ra kho audit không kiểm soát”.

| Tiêu chí | Câu hỏi cần kiểm tra |
| --- | --- |
| **Relevance** | Artifact có hỗ trợ đúng purpose/requirement hoặc chỉ là policy chung? |
| **Completeness** | Đã bao gồm tất cả data assets, flow, recipients, copies và thời kỳ thuộc claim? |
| **Accuracy** | Phương pháp scan/test và observed result có đúng và được đối chiếu? |
| **Freshness** | Evidence có phù hợp schema, release, hợp đồng vendor và trạng thái hiện hành? |
| **Provenance** | Nguồn, người/công cụ thu, query, timestamp và biến đổi có rõ? |
| **Integrity** | Bản gốc, version, quyền sửa/xóa và chuỗi chuyển giao được quản trị phù hợp? |
| **Confidentiality** | Có lọc email, token, tài liệu cá nhân và dữ liệu khách không cần thiết? |
| **Repeatability** | Có test method, data synthetic, input, expected và observed để kiểm tra lại? |
| **Independence** | Reviewer có mức độ độc lập tương xứng với mức rủi ro? |
| **Limitations** | Những nguồn thiếu log, vendor không có dữ liệu hoặc tập mẫu chưa đầy đủ được ghi rõ? |

### Status có nghĩa khác nhau

- **PASS:** đạt tiêu chí trong phạm vi, thời kỳ, phương pháp đã mô tả.
- **FAIL:** có bằng chứng điều kiện sai so với tiêu chí.
- **PARTIAL:** chỉ một phần claim được hỗ trợ, một phần chưa đạt/kiểm tra.
- **NOT TESTED / EVIDENCE MISSING:** không đủ cơ sở, **không phải PASS**.
- **NOT APPLICABLE:** có căn cứ phạm vi hợp lệ cho việc không áp dụng.
- **EXCEPTION / RISK ACCEPTED:** có quyết định có thẩm quyền, giới hạn và thời hạn; **không phải chứng minh control đã đạt**.

### Chia sẻ evidence với auditor/đối tác

Nên có bản **redacted theo nhu cầu kiểm tra**, bảo vệ bản gốc nếu cần, quản trị truy cập và retention. Việc hash một file chỉ giúp hỗ trợ kiểm tra tính toàn vẹn khi có tham chiếu tin cậy; **không tự chứng minh nguồn gốc, độ đầy đủ hay tính chính xác của thông tin**.

## 25. Privacy governance, ownership và RACI

| Vai trò | Trách nhiệm |
| --- | --- |
| **Business/purpose owner** | Giải trình mục đích, nhu cầu dữ liệu, yêu cầu người nhận và tác động nghiệp vụ. |
| **Data owner/steward** | Duy trì inventory, classification, lineage, data quality và thay đổi trường. |
| **Privacy/legal/compliance** | Phân tích nghĩa vụ áp dụng, notice/rights, agreements, đánh giá tác động và ranh giới ngoại lệ. |
| **Security architect/control owner** | Định nghĩa và vận hành controls về quyền, mã hóa, logging, minimization và lifecycle. |
| **Application/service owner** | Thiết kế API, event DTO, xác thực/phân quyền, triển khai và regression tests. |
| **Platform/data engineering** | Quản lý warehouse, ETL, backups, storage, data contracts, deletion workflows. |
| **Vendor/third-party owner** | Quản lý nhà cung cấp, data transfer record, điều kiện sử dụng và bằng chứng của đối tác. |
| **Assurance/assessor** | Đánh giá design/operating effectiveness, evidence quality và findings có phạm vi. |
| **Risk owner** | Quyết định xử lý/chấp nhận phần rủi ro còn lại trong thẩm quyền. |
| **Incident response** | Điều phối containment, điều tra, evidence và khôi phục khi xảy ra sự cố. |

### RACI minh họa cho luồng analytics

**R** = thực hiện; **A** = trách nhiệm giải trình cuối cùng; **C** = được tham vấn; **I** = được thông báo.

| Hoạt động | Purpose owner | Data engineer | Privacy/legal | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Xác định mục đích và dữ liệu tối thiểu | **A/R** | C | C | C | I |
| Thiết kế/triển khai event contract và ETL | C | **A/R** | C | C | I |
| Đánh giá nghĩa vụ và điều kiện xử lý áp dụng | C | I | **A/R** | C | I |
| Kiểm tra độc lập control/evidence | C | C | C | **A/R** | I |
| Phê duyệt residual risk theo thẩm quyền | C | I | C | C | **A/R** |

RACI cần điều chỉnh theo cấu trúc và nghĩa vụ thực tế. Người được giao **Data owner không tự có quyền miễn trừ mọi nghĩa vụ pháp lý**, và assessor không mặc nhiên có thẩm quyền chấp nhận rủi ro kinh doanh.

## 26. Incident response và sự cố dữ liệu cá nhân

Sự cố privacy có thể liên quan **truy cập trái phép, rò rỉ, mất/sửa dữ liệu, chia sẻ nhầm, xử lý ngoài mục đích hoặc không đáp ứng yêu cầu cá nhân**. Cách phân loại pháp lý và nghĩa vụ xử lý/thông báo cần xem theo phạm vi thực tế.

### Quy trình phối hợp

1. **Phát hiện và bảo toàn:** ghi mốc, nguồn, dữ liệu, systems, các hành động đã thực hiện; bảo vệ log phù hợp.
2. **Containment:** chặn luồng sai, giới hạn quyền và xử lý tạm để ngăn tiếp tục tác động; tránh phá hủy evidence.
3. **Tìm phạm vi:** loại dữ liệu, chủ thể, tenant, thời gian, bản sao, recipients và các đường xuất.
4. **Đánh giá tác động:** confidentiality/integrity, nguy cơ lạm dụng, hậu quả đối với cá nhân, mức nghiêm trọng và các giả định chưa kiểm chứng.
5. **Xác định nghĩa vụ:** privacy/legal xác định điều kiện/thời hạn/cơ quan/người cần thông báo nếu thực sự áp dụng; không tự bịa số giờ thông báo chung.
6. **Remediation:** sửa source, quyền, data flow; xử lý bản sao và root cause, làm lại tests.
7. **Hậu kiểm và residual risk:** ghi conclusion, phần còn thiếu, owner, deadline và biện pháp ngăn tái diễn.

### Phân biệt “có khả năng lộ” với “đã bị đọc”

Bucket public là **trạng thái cho phép truy cập ngoài ý muốn**; log xác nhận download là evidence về hành động truy cập theo giới hạn có thể quan sát. Không có access log **không chứng minh không ai tải**, đặc biệt nếu logging bị tắt. Kết luận phải phù hợp evidence và đánh giá tác động, không được suy diễn để giảm mức nghiêm trọng.

## 27. Privacy assurance liên tục trong SDLC và vận hành

Một hoạt động xử lý được duyệt hôm nay có thể trở nên không phù hợp khi có field, consumer, purpose hoặc vendor mới. Privacy assurance cần **continuous reassessment**.

~~~mermaid
flowchart TD
    A["Data inventory + purposes + legal applicability"] --> B["PIA / risk scenarios + requirements"]
    B --> C["Controls by data flow and lifecycle"]
    C --> D["Design review + CI tests"]
    D --> E["Production monitoring + evidence"]
    E --> F{"Claim được hỗ trợ trong scope?"}
    F -- "Không" --> G["Finding / containment / remediation"]
    G --> H["Retest + residual risk decision"]
    H --> C
    F -- "Có" --> I["Kết luận có thời kỳ và giới hạn"]
    I --> J["New field / purpose / vendor / recipient / regulation"]
    J --> A
~~~

### Các trigger nên kích hoạt đánh giá

- Thêm dữ liệu cá nhân, thuộc tính suy luận, định danh mới hoặc đối tượng chủ thể mới.
- Dùng lại dữ liệu cho marketing, analytics, AI/ML hoặc mục đích khác.
- Thêm SDK theo dõi, event consumer, data export, vendor/subprocessor hoặc khu vực xử lý.
- Thay data classification, thời hạn lưu, logic xóa, quyền role, cloud storage hoặc key management.
- Thay privacy notice, lựa chọn của cá nhân hoặc cơ chế xử lý yêu cầu.
- Data breach, incident, findings từ audit, thiếu evidence hoặc dữ liệu sai ở downstream.
- Nghĩa vụ/phạm vi hợp đồng thay đổi và có xác nhận của chức năng chuyên trách.

### Mục tiêu của change gate

Khi PR thêm trường customer_email vào một event, pipeline nên phát hiện schema diff, xác định processing purpose và consumers, đánh giá field có thật sự cần, gọi owner review và chạy contract tests. Nếu không có mục đích đã duyệt, **không đưa trường vào event chỉ vì có sẵn trong entity**.

**CI PASS không thay thế kiểm tra production hoặc dữ liệu đã chuyển tới vendor trước khi sửa.**

## 28. Chỉ số đánh giá chương trình Personal Data Assurance

| Metric | Giúp trả lời | Giới hạn |
| --- | --- | --- |
| **Personal data inventory completeness** | Bao nhiêu data assets/flows có owner và mapping? | Mẫu số có thể thiếu dữ liệu phi cấu trúc, logs và bản sao. |
| **Processing-purpose coverage** | Bao nhiêu luồng có purpose/điều kiện được đánh giá? | Có record không chứng minh xử lý thực tế đúng. |
| **Unapproved fields/consumers** | Những schema changes nào vượt data contract? | Detector có thể bỏ sót dữ liệu suy luận và side channels. |
| **Privacy control test coverage** | Các hành động, tenant, datasets và quyền nào đã được thử? | Nhiều tests nhưng scope hẹp không tạo assurance toàn diện. |
| **Data subject request completion** | Quy trình tiếp nhận/xử lý có hiệu lực theo luật áp dụng? | Ticket closed chưa chắc bản sao downstream đã xử lý. |
| **Deletion verification latency** | Từ trigger đến kiểm chứng ở các đích thuộc scope mất bao lâu? | Phải phân biệt retention, hold và bản backup. |
| **Privacy evidence freshness** | Evidence còn phù hợp với schema, release, vendor và kỳ đánh giá? | File vừa tải lên có thể phản ánh hệ thống cũ. |
| **Findings and overdue remediation** | Những rủi ro/ngoại lệ nào chưa xử lý? | Chỉ đếm số ticket không phản ánh mức tác động tới người. |
| **Vendor processing review coverage** | Đối tác và các luồng nhận có bằng chứng còn hạn? | Chứng nhận vendor không thay phần cấu hình của tổ chức. |
| **Log/collector health** | Có nguồn im lặng làm mất khả năng kiểm chứng không? | Không có alert không chứng minh không có sự cố. |

### Tránh “điểm privacy” tổng hợp vô nghĩa

Không thể kết luận “85% compliant” chỉ vì 85% checkbox xanh khi 15% còn lại có thể liên quan dữ liệu đặc biệt nhạy cảm, hàng triệu bản ghi hoặc quyền bị thiếu. Cần ưu tiên theo **rủi ro, tác động cá nhân, scope, nghĩa vụ và chất lượng evidence**, không tối ưu số lượng tài liệu.

## 29. Hồ sơ YAML cho một privacy control và evidence plan

Ví dụ sau nhằm minh họa cách liên kết **purpose → data flow → control → test → evidence**, không phải cấu hình có thể dùng trực tiếp trong công cụ:

~~~yaml
privacy_control_id: PRIV-MIN-ANALYTICS-01
title: "Minimize personal data in invoice analytics"
business_purpose_id: PURPOSE-MONTHLY-REVENUE
environment: production
data_asset: invoice-records
data_subject_categories:
  - invoice-contact
  - customer-user
processing_owner_role: "Analytics Product Owner"
data_owner_role: "Invoice Data Owner"
privacy_review_role: "Privacy/Legal"
control_owner_role: "Analytics Platform Owner"
assurance_role: "Security & Privacy Assurance"
data_flows:
  source: "invoice-service"
  channel: "invoice-paid-events"
  destination: "analytics-warehouse"
data_contract:
  allowed_fields:
    - tenant_id
    - invoice_id
    - amount_minor
    - currency
    - occurred_at
  forbidden_fields:
    - customer_email
    - customer_phone
    - shipping_address
    - access_token
    - payment_secret
privacy_requirements:
  - "No fields outside approved purpose and schema"
  - "Approved consumer permissions and retention"
  - "Schema changes trigger data owner and privacy review"
tests:
  - add_sensitive_canary_field_to_source_entity
  - verify_event_field_allowlist
  - verify_warehouse_schema_and_actual_sample
  - verify_unauthorized_consumer_cannot_read
  - verify_retention_and_deletion_in_scope
evidence:
  sources:
    - "approved-purpose-register"
    - "versioned-event-contract"
    - "restricted-automated-test-results"
    - "warehouse-access-review"
  period: "example-release-period"
  status: "ILLUSTRATIVE_NOT_ASSESSED"
known_limitations:
  - "Historical vendor exports require separate review"
review_triggers:
  - new_field
  - new_consumer_or_vendor
  - new_processing_purpose
  - retention_or_applicable_obligation_change
~~~

Các ID, role, tên và status chỉ là **giả định học tập**. Không dùng hồ sơ mẫu làm bằng chứng đã tuân thủ. Khi triển khai, cần gắn **observed result, collector/test version, thời gian, người review, artifact có thật, giới hạn và findings**.

## 30. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Chỉ tên và số định danh là dữ liệu cá nhân.” | Định danh gián tiếp, online IDs và dữ liệu suy luận có thể liên quan đến cá nhân trong ngữ cảnh. |
| “Dữ liệu B2B không thuộc privacy.” | Thông tin người đại diện, nhân viên và người mua có thể là dữ liệu cá nhân. |
| “Database có encryption thì privacy đã đạt.” | Cần mục đích, giảm thiểu, transparency, rights, retention, bên nhận và controls vận hành. |
| “Có consent cho một mục đích thì dùng được mọi mục đích.” | Phạm vi và điều kiện phải được xét riêng theo hoạt động và luật áp dụng. |
| “Mọi xử lý đều phải dựa vào consent.” | Điều kiện/căn cứ hợp lệ có thể khác theo chế độ pháp lý; phải xác định đúng. |
| “Bỏ email khỏi dữ liệu nghĩa là đã ẩn danh.” | Khả năng liên kết qua ID, thuộc tính khác hoặc bảng ánh xạ có thể còn. |
| “User được quyền đọc nên có thể export toàn bộ.” | Authorization và purpose theo action, dữ liệu và phạm vi cụ thể. |
| “Log càng nhiều càng bảo đảm accountability.” | Logs có thể tạo bản sao dữ liệu cá nhân, secret và tăng hậu quả khi lộ. |
| “Xóa database là đáp ứng mọi yêu cầu xóa.” | Cần xét downstream, retention, backup, đối tác, ngoại lệ và bằng chứng. |
| “Đã ký hợp đồng vendor nghĩa là không còn trách nhiệm.” | Shared responsibility và data minimization/config nội bộ vẫn cần kiểm chứng. |
| “Công cụ quét không thấy PII nghĩa là không có PII.” | Dữ liệu phi cấu trúc, suy luận và khả năng nhận diện gián tiếp có thể bị bỏ sót. |
| “Thông báo privacy đăng trên web là đủ.” | Notice phải phản ánh hoạt động thực và đi kèm controls, evidence phù hợp. |
| “Có một dashboard xanh là đã privacy compliant.” | Kết luận phải theo claim, nghĩa vụ, scope, kỳ đánh giá và chất lượng evidence. |
| “Không có log truy cập dữ liệu trái phép chứng minh không ai truy cập.” | Có thể mất logs, retention quá ngắn hoặc đường truy cập chưa được quan sát. |
| “Được chấp nhận ngoại lệ là control đã PASS.” | Risk acceptance là quyết định có giới hạn, không thay thế hiệu quả control. |
| “PR sửa schema đã merge là đã loại dữ liệu cũ khỏi warehouse.” | Cần triển khai, đối chiếu nơi nhận, xử lý lịch sử và retest. |

## 31. Checklist cho một đợt Personal Data Assurance

1. **Data scope:** cá nhân/nhóm người nào, những trường và dữ liệu suy luận nào, gồm cả ID gián tiếp?
2. **Purpose:** mục đích xử lý có cụ thể, được duyệt và có điều kiện hợp lệ được xác minh?
3. **Roles:** ai quyết định, xử lý, sở hữu dữ liệu và trách nhiệm với đối tác?
4. **Inventory:** database, logs, event bus, search, cache, analytics, export, backup, staging và vendor được kiểm kê?
5. **Lineage:** dữ liệu có đường từ nguồn→biến đổi→nơi nhận, với trust boundaries?
6. **Classification and impact:** có xét rủi ro đối với người, dữ liệu nhạy cảm và khả năng liên kết?
7. **Transparency:** thông tin/notice và choices có phản ánh thực tế, phiên bản và quyền theo phạm vi?
8. **Minimization:** fields, volume, precision, recipients và retention đã được giới hạn theo purpose?
9. **Authorization:** object/tenant access, privileged access, export và dịch vụ nền có negative tests?
10. **Protection:** encryption, KMS, secure transfer, logs và evidence được bảo vệ?
11. **Subject requests:** quy trình xác minh, phân loại, xử lý quyền và downstream có test?
12. **Retention/deletion:** có lịch lưu, exceptions/holds, backup và restore handling?
13. **Third parties:** danh sách recipients, hợp đồng, khu vực, vai trò và evidence nhà cung cấp đúng scope?
14. **Risk assessment:** PIA/DPIA hoặc phương pháp phù hợp có xem necessity, impacts, alternatives và controls?
15. **Evidence:** design/operating evidence có provenance, completeness, timestamp, release và limits?
16. **Findings:** điều chưa đạt/thiếu bằng chứng có owner, hành động, deadline, retest và residual risk?
17. **Continuous review:** thay schema, purpose, SDK, vendor, AI use hoặc policy có trigger đánh giá lại?

## 32. Bài tập thực hành và gợi ý

### Bài tập A — Email công việc có phải dữ liệu cá nhân?

Một nhóm cho rằng địa chỉ email nhân viên của khách hàng doanh nghiệp không cần đưa vào inventory vì “chỉ là email công ty”.

**Gợi ý:** Xem email có liên quan hoặc giúp nhận diện một người cụ thể trong bối cảnh xử lý hay không; B2B không tự loại trừ dữ liệu của con người. Cần kiểm tra phạm vi và định nghĩa pháp lý áp dụng, mục đích/recipient/retention.

### Bài tập B — Có encryption nhưng chia sẻ ngoài mục đích

Warehouse mã hóa đầy đủ, nhưng ETL gửi email người mua tới đội phân tích chỉ cần tổng doanh thu. Security dashboard báo PASS vì encryption và IAM không lỗi.

**Gợi ý:** Đây có thể là privacy control failure về **data minimization/purpose limitation**. Cần kiểm tra data contract và field lineage ở đích, mục đích, bên nhận, quyền và bản sao lịch sử; encryption không giải quyết câu hỏi “có cần gửi dữ liệu đó không?”.

### Bài tập C — Consent chung cho mọi hoạt động

Một checkbox “Tôi đồng ý mọi điều khoản” được dùng để biện minh cho việc gửi hóa đơn, quảng cáo, phân tích và chia sẻ với đối tác.

**Gợi ý:** Phải phân loại từng hoạt động, tìm điều kiện xử lý phù hợp theo luật áp dụng; nếu cần consent, xem yêu cầu về phạm vi, lựa chọn, thông tin, version và withdrawal. Không tự biến một checkbox tổng quát thành bằng chứng đủ cho mọi purpose.

### Bài tập D — Pseudonymous ID và khả năng liên kết

Đội analytics thay email bằng customer_id, nhưng vẫn giữ bảng ánh xạ ở một dịch vụ khác và quyền truy cập cả hai dataset cho cùng nhóm.

**Gợi ý:** Không thể khẳng định đã ẩn danh. Phải xem khả năng liên kết, quyền bảng ánh xạ, dữ liệu bổ sung và tác động cá nhân; giảm quyền, purpose và retention ở cả hai nguồn rồi đánh giá theo tiêu chí pháp lý/threat model.

### Bài tập E — Yêu cầu xóa và bản backup

Ứng dụng xóa profile trong database và gửi email “tất cả dữ liệu đã được xóa”, nhưng backup vẫn giữ nhiều tháng và warehouse chưa được kiểm tra.

**Gợi ý:** Kết luận quá rộng so với evidence. Cần phân biệt request/action/verification, xử lý downstream và backup theo nghĩa vụ, hạn giữ và cơ chế restore; thông tin phản hồi phải phù hợp với những gì thực sự đã được thực hiện.

### Bài tập F — Support xem hồ sơ ngoài ticket

Nhân viên support có role hợp lệ và dùng quyền đó để xem dữ liệu của khách hàng không liên quan vụ việc mình đang xử lý.

**Gợi ý:** Không chỉ xét authentication/IAM; cần **need-to-know, purpose, ticket-scoped access**, JIT/approval nếu phù hợp, audit, negative tests và điều tra tác động. Role hợp lệ không tự bảo đảm hành vi xử lý đúng mục đích.

### Bài tập G — Data subject request từ email lạ

Một người gửi yêu cầu trích xuất toàn bộ hồ sơ theo tên và số điện thoại qua email không liên kết account. Đội vận hành định gửi ngay tệp CSV chứa dữ liệu.

**Gợi ý:** Cần xác minh danh tính và thẩm quyền bằng cơ chế tương xứng, tránh thu thêm dữ liệu nhạy cảm không cần; đối chiếu phạm vi và điều kiện của yêu cầu theo luật áp dụng. Không tiết lộ dữ liệu chỉ dựa vào thông tin dễ biết.

### Bài tập H — AI vendor mới

Đội sản phẩm gửi nội dung ticket hỗ trợ vào một công cụ AI bên ngoài mà không cập nhật processing register, notice hoặc hợp đồng xử lý.

**Gợi ý:** Đây là **data flow và mục đích/recipient mới**; cần inventory dữ liệu trong prompt, kiểm tra quyền sử dụng/retention của vendor, nghĩa vụ, giảm dữ liệu, điều kiện hợp lệ, privacy review và bằng chứng ở cả nguồn/đích.

### Bài tập I — Scanner báo zero PII

Một công cụ DLP quét bảng analytics và không thấy tên/email. Tuy nhiên, bảng có device_id, vị trí và chuỗi thời gian rất chi tiết, có thể liên kết với tài khoản ở hệ thống khác.

**Gợi ý:** Quét tên/email không đủ. Cần đánh giá định danh gián tiếp, joinability, disclosure theo nhóm nhỏ và các nguồn bổ sung. Kết luận nên giới hạn vào rule set scanner và dữ liệu đã kiểm tra.

### Bài tập J — Đã sửa code nhưng dữ liệu cũ còn tồn tại

PR sửa event để không gửi email đã được merge. Trong warehouse vẫn có email lịch sử và một vendor đã export dữ liệu trước đó.

**Gợi ý:** Tách **future-flow prevention** khỏi **historical remediation**. Cần triển khai và kiểm chứng release thật, điều tra nơi nhận/bản sao, đánh giá nghĩa vụ xử lý, xóa/hạn chế phù hợp và ghi phần chưa xác minh cùng residual risk.

## Kết luận

**Personal data** không chỉ là tên hoặc số định danh: các dấu vết kỹ thuật, dữ liệu giao dịch, thông tin suy ra và các tổ hợp dữ liệu đều có thể liên quan đến một cá nhân trong ngữ cảnh. **Privacy assurance** vì vậy vượt khỏi câu hỏi “hệ thống có bị hack không?” để xem hoạt động xử lý có **mục đích rõ, điều kiện hợp lệ, minh bạch, tối thiểu cần thiết, quyền truy cập phù hợp, giới hạn chia sẻ và lưu giữ, quy trình xử lý yêu cầu và bằng chứng vận hành** hay không. Trong **SECURITY_SECURITY_ASSURANCE**, từ một data asset cần truy vết tới purpose, data flow, control, test, evidence, finding, remediation và residual risk. **Chỉ kết luận hoạt động xử lý dữ liệu cá nhân được bảo đảm trong phạm vi, thời kỳ và những điều kiện mà bằng chứng thực tế hỗ trợ**; mọi giới hạn chưa kiểm tra phải được nêu rõ và tiếp tục theo dõi khi hệ thống thay đổi.

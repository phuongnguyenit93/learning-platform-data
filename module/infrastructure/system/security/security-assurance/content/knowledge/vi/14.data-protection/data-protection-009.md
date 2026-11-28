# Data Loss Prevention (DLP): Phòng ngừa thất thoát dữ liệu

## 1. Data Loss Prevention là gì?

**Data Loss Prevention (DLP)** là tập hợp **chính sách, quy trình và security controls** nhằm **nhận diện dữ liệu cần bảo vệ, giám sát cách dữ liệu được sử dụng hoặc di chuyển, và phát hiện/ngăn các hành động làm dữ liệu rời khỏi phạm vi được phép**. DLP thường tập trung vào các tình huống dữ liệu nhạy cảm bị **tiết lộ, chia sẻ sai người, sao chép ra kênh không được phép hoặc xuất ra ngoài môi trường được kiểm soát**.

Ví dụ: nhân viên có quyền xem danh sách khách hàng trên hệ thống CRM nhưng không có quyền gửi toàn bộ danh sách qua email cá nhân. DLP có thể phát hiện nội dung nhạy cảm trong email hoặc tệp đính kèm, so khớp với chính sách xuất dữ liệu và **cảnh báo, yêu cầu giải trình, cách ly hoặc chặn gửi** theo mức rủi ro.

DLP không chỉ là phần mềm quét biểu thức chính quy. Một chương trình DLP có thể gồm:

- **Data discovery và classification:** biết dữ liệu nhạy cảm nằm ở đâu, mức bảo vệ nào cần áp dụng.
- **Chính sách xử lý và chia sẻ:** loại dữ liệu nào được truyền cho ai, bằng kênh nào, trong điều kiện gì.
- **Điểm thực thi (enforcement points):** ứng dụng, API, email, endpoint, mạng, lưu trữ cloud, SaaS, công cụ cộng tác, CI/CD.
- **Detection/decision engine:** phân tích nội dung, metadata, danh tính, kênh, quyền, ngữ cảnh nghiệp vụ và dấu hiệu bất thường.
- **Response:** cho phép, cảnh báo, ghi nhận, cách ly, chặn, yêu cầu phê duyệt hoặc kích hoạt điều tra.
- **Operations và assurance:** điều chỉnh rule, xử lý false positive/negative, review incident, kiểm thử và lưu bằng chứng hiệu quả.

Trong module **SECURITY_SECURITY_ASSURANCE**, DLP phải được đánh giá như **security control có thể kiểm chứng**: rủi ro thất thoát dữ liệu nào cần giảm, đường dữ liệu nào thuộc phạm vi, quyết định có đúng policy không, bằng chứng cho thấy control đang hoạt động ở đâu và sai lệch được khắc phục như thế nào.

> **Lưu ý thuật ngữ:** Trong một số môi trường, DLP được mở rộng thành *Data Leakage Prevention*. Cả hai cách dùng đều thường nói đến bảo vệ dữ liệu trước sự tiết lộ ngoài ý muốn hoặc trái phép. DLP không đồng nghĩa với *backup* hay toàn bộ hoạt động bảo đảm dữ liệu không bị mất do hỏng đĩa, dù từ “loss” trong tên có thể gây nhầm lẫn.

### 1.1. Vì sao dữ liệu có thể “thất thoát” dù người dùng đăng nhập hợp lệ?

Phân quyền có thể cho phép người dùng **đọc** một hồ sơ vì cần làm việc. Nhưng người dùng có thể:

- Tải xuống hàng nghìn bản ghi thay vì một tập nhỏ phục vụ nhiệm vụ.
- Gửi tệp qua email cá nhân hoặc đăng lên dịch vụ lưu trữ chưa được phê duyệt.
- Sao chép thông tin vào hệ thống AI/chat/cộng tác không được phép theo chính sách.
- Đưa secret hoặc dữ liệu khách hàng vào repository, issue tracker và log.
- Cấu hình một bucket public hoặc gửi file tới đối tác sai địa chỉ.
- Dùng quyền export hợp lệ nhưng chọn tập dữ liệu rộng hơn mục đích được cấp quyền.
- Vô tình đồng bộ dữ liệu công việc sang thiết bị cá nhân.

**Authentication và authorization** kiểm soát người có thể thực hiện hành động; **DLP** bổ sung kiểm soát **nội dung, đích đến, kênh và bối cảnh sử dụng dữ liệu**. Hai cơ chế hỗ trợ nhau và đều cần ràng buộc chính sách cụ thể.

### 1.2. DLP và mục tiêu bảo mật

| Mục tiêu | DLP đóng góp gì? | Giới hạn |
| --- | --- | --- |
| **Confidentiality** | Giảm khả năng dữ liệu nhạy cảm rời phạm vi được phép | Không thể ngăn mọi hình thức ghi nhớ, chụp ảnh hoặc truyền thông ngoài kênh kiểm soát |
| **Integrity** | Phát hiện một số thao tác sao chép/sửa/chuyển nhầm | Không thay thế validation, kiểm soát thay đổi hay bảo vệ integrity |
| **Privacy** | Giới hạn chia sẻ dữ liệu cá nhân theo mục đích và người nhận | Cần cơ sở xử lý, quản lý dữ liệu và nghĩa vụ riêng tư khác ngoài DLP |
| **Accountability** | Lưu hành động, rule, decision và actor cho kiểm tra | Phải bảo vệ log và không thu thập quá mức nội dung nhạy cảm |
| **Risk reduction** | Giảm xác suất hoặc phạm vi tiết lộ qua những kênh đã bảo vệ | Không phải chứng nhận hệ thống miễn nhiễm với exfiltration |

## 2. DLP khác các kiểm soát dữ liệu khác thế nào?

| Biện pháp | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Data classification** | Dữ liệu thuộc loại/mức nhạy cảm nào? | Gắn nhãn “Restricted – dữ liệu định danh khách hàng” |
| **Access control** | Ai có quyền đọc, sửa, xuất dữ liệu nào? | Chỉ role phụ trách khách hàng A được xem hồ sơ A |
| **Encryption** | Dữ liệu có được bảo vệ khi lưu/truyền trước người không có khóa? | TLS và mã hóa lưu trữ |
| **DLP** | Dữ liệu có bị dùng/chia sẻ qua kênh hoặc đích trái policy không? | Chặn gửi danh sách khách hàng ra email cá nhân |
| **Data minimization** | Có cần thu thập hoặc truyền toàn bộ dữ liệu này không? | Trả 4 chữ số cuối thay vì toàn bộ định danh |
| **Tokenization/masking** | Có thể giảm khả năng lộ giá trị gốc bằng thay thế/che không? | Token hóa số định danh khi xử lý phân tích |
| **Backup và recovery** | Có khôi phục dữ liệu sau lỗi/xóa/ransomware được không? | Restore và diễn tập RTO/RPO |
| **CASB/SSE/SaaS security** | Ai sử dụng ứng dụng cloud, chia sẻ dữ liệu thế nào? | Kiểm tra public sharing link và nội dung tải lên |
| **Audit/monitoring** | Có nhận biết, truy vết và phản ứng sự kiện không? | Ghi actor, loại dữ liệu, rule hit và kết quả |
| **Data governance** | Ai sở hữu, dữ liệu được phép dùng trong mục đích nào? | Data owner phê duyệt các kênh chia sẻ và thời hạn lưu |

**Mã hóa không thay thế DLP:** người dùng có quyền giải mã vẫn có thể gửi bản rõ tới nơi không được phép. **DLP không thay thế mã hóa:** DLP có thể bỏ sót hoặc không quan sát được một kênh, trong khi TLS và mã hóa lưu trữ vẫn bảo vệ trước các threat khác.

## 3. Mô hình dữ liệu và ranh giới bảo vệ

### 3.1. Ba trạng thái dữ liệu

| Trạng thái | Dữ liệu ở đâu, đang làm gì? | Vị trí control thường gặp |
| --- | --- | --- |
| **Data at rest** | Đang lưu tại database, object storage, file server, cloud drive, repository hoặc backup | Discovery scanner, classification, access/configuration review, cloud storage policy |
| **Data in motion** | Đang truyền qua email, HTTP/API, upload, webhook, đồng bộ hoặc kênh mạng | Email gateway, proxy, API/egress gateway, upload/download policy, network DLP |
| **Data in use** | Đang mở, copy/paste, in, chuyển vào USB hoặc thao tác trong ứng dụng/thiết bị | Endpoint DLP, application control, managed browser, clipboard/print/USB restrictions |

Một tài liệu có thể đi qua **cả ba trạng thái** trong một hành động: nằm trong database, được tạo thành file trên server, xuất qua API, tải về laptop, rồi đính kèm email. Vì thế phải thiết kế control theo **data flow và trust boundary**, không chỉ chọn một công cụ cho một loại lưu trữ.

### 3.2. Các kênh thất thoát thường gặp

- Email ra ngoài tổ chức và email chuyển tiếp tự động.
- Tải lên dịch vụ cloud hoặc SaaS không được phê duyệt.
- Public link hoặc phân quyền sai trên object storage và công cụ cộng tác.
- API export, báo cáo, batch job, webhook, đối tác và dịch vụ thứ ba.
- Copy/paste vào chat, ticket, tài liệu, biểu mẫu hoặc công cụ AI ngoài phạm vi cho phép.
- Repository, CI/CD logs, artifacts và container image chứa credential.
- Thiết bị USB, bản in, screenshot và đồng bộ tài khoản cá nhân.
- Truy vấn database và sao lưu được sao chép qua đường quản trị.
- Kênh mạng hoặc protocol không nằm dưới điểm giám sát.
- Tài khoản service có quyền đọc nhiều dữ liệu và đích egress rộng.

**Không phải kênh nào cũng có khả năng quan sát giống nhau.** Ví dụ, kiểm tra mail gateway không quan sát mọi dữ liệu người dùng tải qua HTTPS, còn endpoint DLP có thể không thấy dữ liệu một server job tự chuyển trực tiếp giữa hai hệ thống cloud.

### 3.3. Luồng dữ liệu minh họa

~~~mermaid
flowchart LR
    A[("Customer DB")] --> B["Orders API"]
    B --> C["Report / export service"]
    C --> D["DLP policy decision"]
    D -->|"Được phép"| E["Approved destination"]
    D -->|"Rủi ro / không hợp lệ"| F["Block, hold hoặc review"]
    C --> G[("Controlled staging storage")]
    G --> H["Download gateway"]
    H --> D
    D --> I[("Protected audit events")]
    J["Endpoint / email / SaaS"] --> D
~~~

Sơ đồ mô tả các **điểm kiểm soát logic**, không có nghĩa một DLP engine duy nhất có thể chặn mọi kênh. Hệ thống thực tế có thể dùng nhiều control tại API, email, endpoint, storage và cloud.

## 4. Phân loại dữ liệu: nền tảng của DLP

### 4.1. Data discovery trước khi viết rule

Tổ chức cần biết:

1. **Dữ liệu nào** đang được xử lý: định danh cá nhân, hồ sơ tài chính, thông tin khách hàng, khóa bí mật, mã nguồn, bí mật kinh doanh.
2. **Ai sở hữu dữ liệu** và có quyền quyết định việc sử dụng/chia sẻ.
3. **Dữ liệu nằm ở đâu:** hệ thống gốc, bản sao, cache, export, backup, data lake, công cụ cộng tác.
4. **Luồng đi đâu:** user, dịch vụ, đối tác, nhà cung cấp, vùng/lãnh thổ, thiết bị.
5. **Ai cần truy cập và vì mục đích nào.**
6. **Dữ liệu có thời hạn lưu, giới hạn chia sẻ hoặc nghĩa vụ cụ thể nào.**
7. **Dữ liệu nào có thể tối thiểu hóa, masking hoặc loại bỏ** trước khi chuyển.

Nếu không có bản đồ dữ liệu, DLP rule dễ bảo vệ nhầm chỗ hoặc bỏ sót một đường nguy hiểm.

### 4.2. Nhãn dữ liệu minh họa

Một tổ chức có thể dùng bốn mức, nhưng tên và định nghĩa phải do tổ chức phê duyệt:

| Mức giả định | Nội dung ví dụ | Cách xử lý tham khảo |
| --- | --- | --- |
| **Public** | Thông tin đã được phép công bố | Có thể chia sẻ công khai theo chính sách |
| **Internal** | Tài liệu công việc, quy trình vận hành không công khai | Chia sẻ nội bộ hoặc bên được phê duyệt |
| **Confidential** | Hồ sơ khách hàng, dữ liệu thương mại, báo cáo nhạy cảm | Giới hạn người nhận và kênh, giám sát export |
| **Restricted** | Secret, khóa ký, thông tin cực nhạy cảm hoặc dữ liệu đặc biệt cần bảo vệ | Quy tắc nghiêm, có thể chặn/chuyển phê duyệt, hạn chế sao chép |

**Không có quy tắc phổ quát** rằng mọi dữ liệu cá nhân đều nằm cùng một mức; cần phân loại theo khả năng ảnh hưởng và nghĩa vụ thực tế. Dữ liệu được ghép từ nhiều nguồn ít nhạy cảm cũng có thể trở nên nhạy cảm hơn.

### 4.3. Metadata và lineage

Nhãn nên có:

- **Data set / asset ID** và data owner.
- Mức classification, phạm vi, phiên bản quy tắc gắn nhãn.
- Nguồn dữ liệu và lineage (truy xuất từ đâu, biến đổi ra sao).
- Mục đích và nhóm người nhận/kênh được phép.
- Thời hạn lưu, điều kiện xóa/ẩn danh nếu có.
- Confidence của hệ thống phân loại tự động.
- Thời điểm cập nhật và lịch review.

**Nhãn chỉ đáng tin nếu có quy trình bảo vệ.** Nếu client có thể tùy ý đổi tệp “Restricted” thành “Public”, một control DLP dựa riêng vào nhãn sẽ dễ bị bypass.

## 5. Cách DLP nhận diện nội dung nhạy cảm

### 5.1. Rule dựa trên mẫu (pattern matching)

Ví dụ: biểu thức chính quy nhận diện chuỗi có định dạng giống số định danh hoặc credential. Ưu điểm là dễ triển khai với dữ liệu có format rõ.

Giới hạn:

- **False positive:** chuỗi trông giống dữ liệu nhạy cảm nhưng thực ra chỉ là dữ liệu thử.
- **False negative:** dữ liệu nhạy cảm bị tách, biến đổi, mã hóa hoặc có định dạng không dự kiến.
- Một regex khớp định dạng **không chứng minh** giá trị hợp lệ hay thuộc loại dữ liệu cần chặn.
- Có thể ảnh hưởng hiệu năng nếu rule quá rộng hoặc được dùng cho tệp lớn.

Nên kết hợp **context, độ dài, vị trí, loại tệp, checksum/validation phù hợp và ngữ cảnh sử dụng**, thay vì coi regex là bằng chứng duy nhất.

### 5.2. Dictionary, exact data matching và fingerprint

- **Dictionary/keyword:** danh sách cụm từ hoặc thuật ngữ; dễ triển khai nhưng có thể nhiều nhiễu.
- **Exact data matching (EDM):** so khớp với những giá trị hoặc chỉ dấu cụ thể từ tập dữ liệu được phép dùng để nhận diện; cần quản lý bảo mật dữ liệu tham chiếu.
- **Document fingerprinting:** dùng đặc trưng của tài liệu để nhận diện bản sao hoặc đoạn tương tự; độ tin cậy phụ thuộc cách biến đổi, định dạng và cấu hình.
- **Metadata/label matching:** kiểm tra nhãn classification hoặc dấu provenance đáng tin.

**Lưu ý riêng về dữ liệu tham chiếu:** hash thuần của dữ liệu có ít khả năng biến thiên có thể bị dò bằng từ điển; không mặc định một danh sách hash là vô hại. Tổ chức cần bảo vệ index, secret, quyền truy cập, logging và vòng đời dữ liệu tham chiếu.

### 5.3. OCR, phân tích ngữ nghĩa và ML

Tài liệu có thể là PDF scan, ảnh hoặc văn bản không cấu trúc. Một hệ thống DLP có thể dùng **OCR** hoặc mô hình phân loại để phát hiện nội dung. Đây là **phương pháp phát hiện**, không phải bằng chứng chắc chắn.

- OCR có thể bỏ sót nội dung ảnh mờ hoặc bị biến dạng.
- Model có thể nhận định sai loại thông tin.
- Có thể phải xét chi phí, độ trễ, riêng tư và độ tin cậy của kết quả.
- Mô hình mới hoặc rule mới cần kiểm thử hồi quy trên tập dữ liệu được phép sử dụng.

**Không nhất thiết phải lưu nguyên văn dữ liệu nhạy cảm để kiểm chứng detection.** Có thể dùng dữ liệu giả lập, nhãn kết quả, reference ID hoặc mẫu đã che theo chính sách.

### 5.4. Tín hiệu ngữ cảnh

Quyết định DLP thường cần kết hợp:

- **Who:** actor/role, service identity, trạng thái account, mức độ tin cậy của phiên.
- **What:** loại dữ liệu, nhãn, mức nhạy cảm, khối lượng.
- **Where:** đích nhận, domain, tenant, ứng dụng, vùng triển khai.
- **How:** email, API export, public share, USB, copy/paste, webhook.
- **Why:** mục đích và approval đã được phê duyệt; case hoặc change ID nếu liên quan.
- **When:** thời điểm, tần suất, tốc độ, sự thay đổi bất thường.
- **Confidence:** mức tin cậy detection và nguồn metadata.

Một nội dung có nhãn Confidential có thể được phép gửi tới đối tác được phê duyệt qua kênh bảo vệ, nhưng không được phép gửi cùng nội dung đến email cá nhân. **Chỉ nhìn content mà bỏ context sẽ làm tăng chặn nhầm.**

## 6. Chính sách DLP và các dạng enforcement

### 6.1. Các mức phản ứng

| Hành động | Khi nào hữu ích? | Cần kiểm chứng gì? |
| --- | --- | --- |
| **Observe / audit** | Giai đoạn khảo sát, kiểm soát chưa đủ tin cậy để tự động chặn | Có log, scope, retention và đánh giá phát hiện |
| **Warn / coach** | Vi phạm rủi ro thấp, có thể sửa bởi người dùng | Cảnh báo rõ lý do, không tiết lộ dữ liệu nhạy cảm |
| **Require justification** | Cho phép ngoại lệ có kiểm soát theo điều kiện | Lý do, owner, audit, giới hạn và policy duyệt |
| **Require approval** | Chia sẻ rủi ro cao nhưng có nhu cầu kinh doanh hợp lệ | Phê duyệt đúng quyền, dữ liệu và đích được kiểm tra |
| **Quarantine / hold** | Tạm giữ file/email chờ đánh giá | Dữ liệu cách ly được bảo vệ, có hạn xử lý |
| **Redact / mask** | Chỉ một phần dữ liệu cần thiết để phục vụ mục đích | Không làm lộ trường còn lại, kết quả vẫn đúng nghiệp vụ |
| **Block** | Đích/kênh không được phép hoặc dữ liệu nhạy cảm không thể truyền | Không có đường bypass, thông báo và audit phù hợp |
| **Encrypt / route to approved channel** | Có cơ sở chia sẻ nhưng cần kênh bảo vệ | Người nhận, quyền truy cập, khóa và đường mở tệp đúng |

**Không phải rule nào cũng nên chặn ngay.** Nếu nhận diện còn nhiều false positive, tự động chặn email nghiệp vụ có thể gây gián đoạn. Có thể triển khai theo giai đoạn **observe → tune → enforce**, kèm tiêu chí chấp nhận rủi ro và thời hạn cho việc điều chỉnh.

Tuy nhiên, **observe-only không thể được báo cáo là đã ngăn thất thoát**. Cần nêu rõ đây là control phát hiện, chưa phải control phòng ngừa ở kênh đó.

### 6.2. Fail-open và fail-closed theo rủi ro

Một câu hỏi quan trọng: **DLP engine hoặc policy service không phản hồi thì ứng dụng làm gì?**

- Với export dữ liệu nhạy cảm và đích chưa được phê duyệt, policy có thể yêu cầu **hold/deny** khi không xác định được quyết định.
- Với nội dung ít rủi ro hoặc hoạt động phục vụ thiết yếu, tổ chức có thể quy định phương án giảm thiểu khác, nhưng phải ghi rõ vì sao và bằng chứng.
- Trong chế độ khẩn cấp, cần cơ chế phê duyệt và truy vết phù hợp, không âm thầm bỏ kiểm tra.

**Fail-closed cho mọi thứ** có thể tạo outage; **fail-open cho mọi thứ** có thể làm mất giá trị DLP. Quyết định cần dựa trên **data class, action, destination và risk appetite**, không chỉ một cấu hình mặc định.

### 6.3. Không để client tự quyết định classification

Ví dụ nguy hiểm:

~~~http
POST /api/reports/export
Content-Type: application/json

{
  "classification": "PUBLIC",
  "includeSensitiveFields": true,
  "destination": "external"
}
~~~

Nếu server tin trường classification do client gửi, người dùng có thể tự hạ nhãn. Chính sách đúng phải lấy **classification từ nguồn dữ liệu tin cậy hoặc policy service** và kiểm tra mức nhạy cảm của kết quả thực tế.

Client có thể gợi ý nhu cầu nghiệp vụ hoặc đích nhận; **không được tự cấp quyền vượt policy**.

## 7. DLP theo từng lớp kiến trúc

### 7.1. Endpoint DLP

Có thể giám sát hoặc hạn chế copy/paste, USB, in, upload, đồng bộ và tệp cục bộ trên **managed endpoints**.

**Điểm cần kiểm chứng:**

- Những hệ điều hành, phiên bản, user và thiết bị nào trong scope.
- Agent có hoạt động không, có chống tampering và báo lỗi không.
- Có đường bỏ qua qua browser, ứng dụng khác, clipboard, screenshot hoặc thiết bị không quản lý không.
- Kết quả báo cáo có gắn đúng máy và policy revision không.
- Tác động quyền riêng tư và hiệu năng đã được đánh giá chưa.

Không nên tuyên bố endpoint DLP có thể chặn mọi ảnh chụp màn hình hoặc hành vi bên ngoài thiết bị.

### 7.2. Email DLP

Kiểm tra nội dung thư, file đính kèm, domain người nhận và policy chia sẻ. Rủi ro gồm gửi sai địa chỉ, gửi mail cá nhân, forward tự động, mã hóa file đính kèm làm mất khả năng kiểm tra hoặc tài khoản mail bị chiếm.

**Điểm cần kiểm chứng:** mail nội bộ và external, alias, group, forward, encrypted attachment, file lớn, ngoại lệ và đường gửi không đi qua gateway.

### 7.3. Network / Secure Web Gateway

DLP trên kênh mạng có thể kiểm tra upload và lưu lượng qua proxy/egress phù hợp. Tuy nhiên:

- **TLS và mã hóa đầu cuối** có thể hạn chế nội dung quan sát được.
- Việc kiểm tra TLS có tác động bảo mật, quyền riêng tư, chứng chỉ và nghĩa vụ pháp lý; phải có thiết kế được phê duyệt.
- Không phải mọi protocol, thiết bị và đường kết nối đều đi qua cùng một điểm kiểm tra.
- Metadata lưu lượng và content inspection có độ bảo đảm khác nhau.

Một báo cáo “network DLP enabled” phải có **scope của các đường thực sự được kiểm tra**.

### 7.4. Cloud/SaaS DLP

Có thể phát hiện hoặc thay quyền khi dữ liệu bị lưu trong bucket/cloud drive, tài liệu dùng public link hoặc dữ liệu chia sẻ sang tenant khác.

Cần phân biệt:

- **API-based scan:** quét sau khi dữ liệu đã có trên dịch vụ; có thể phát hiện **sau thời điểm phơi nhiễm**.
- **Inline control:** ngăn tại thời điểm upload/share nếu tích hợp và kênh phù hợp.
- **Configuration posture:** kiểm tra quyền bucket/public link; có thể bổ trợ DLP nhưng không phải phân tích nội dung.

Phải biết **độ trễ phát hiện** và dữ liệu có thể đã bị truy cập trước khi bị cách ly hay không.

### 7.5. Application/API DLP

Ứng dụng thường có **ngữ cảnh nghiệp vụ tốt hơn** agent mạng: chủ dữ liệu, tenant, mục đích export, role, nhãn và quyền đối tác. Vì vậy, DLP tại tầng ứng dụng có thể quyết định dựa trên **data classification + authorization + destination + approval**.

Kiểm soát có thể nằm:

- Trước khi truy vấn hoặc xuất toàn bộ tập dữ liệu.
- Trước khi sinh file hoặc trước khi phát download link.
- Trước khi webhook gửi payload tới bên thứ ba.
- Trước khi worker chuyển báo cáo tới object storage/đích nhận.
- Ở cổng tải tệp đã được xử lý/an toàn.
- Trong hệ thống workflow cho phê duyệt export hoặc chia sẻ nhạy cảm.

**Application DLP không thay thế object-level authorization.** Nếu user A không có quyền xem dữ liệu B, engine DLP không được dùng để hợp thức hóa việc xuất dữ liệu của B rồi chỉ “cảnh báo”.

### 7.6. DLP cho secrets và CI/CD

Secret có thể lộ qua source code, artifact, build logs, container layer, issue và tài liệu. Các control liên quan có thể gồm:

- Secret detection trước commit và trong CI.
- Hạn chế ghi log env vars và token.
- Vault/workload identity thay credential dài hạn.
- Quét artifact/repository theo phạm vi.
- Revocation/rotation khi có secret leak.

**Quét secret không thay thế quản lý khóa.** Nếu secret đã xuất hiện trên repository được người khác truy cập, chỉ xóa dòng ở commit mới có thể chưa đủ; cần xem khả năng truy cập lịch sử, thu hồi secret và điều tra.

## 8. Threat modeling một luồng export có nguy cơ thất thoát dữ liệu

### 8.1. Bối cảnh giả định

Một nền tảng thương mại điện tử có **Orders API** viết bằng **Java/Spring Boot**. Nhân viên chăm sóc khách hàng có quyền xem dữ liệu những khách hàng được giao. Ứng dụng cho phép tạo báo cáo CSV để làm việc với bộ phận hỗ trợ được phê duyệt.

**Tài sản:** mã khách hàng, email, số điện thoại, địa chỉ giao hàng, tổng giá trị đơn hàng và các trường khác.

**Threat scenario:** nhân viên dùng chức năng export lấy quá nhiều dữ liệu rồi gửi file đến địa chỉ email cá nhân hoặc một webhook không được phê duyệt. Một kịch bản khác là attacker chiếm tài khoản nhân viên và lợi dụng quyền export hợp lệ.

### 8.2. Sơ đồ DFD và trust boundaries

~~~mermaid
flowchart LR
    U["Support agent"] -->|"Request export + destination"| API["Orders API"]
    API --> AUTHZ["Object/tenant authorization"]
    AUTHZ --> DB[("Orders Database")]
    DB --> BUILD["Report Builder"]
    BUILD --> CLASS["Trusted classification + DLP policy"]
    CLASS --> DEC{"Decision"}
    DEC -- "Approved" --> STAGE[("Private staging storage")]
    STAGE --> OUT["Controlled delivery/download"]
    OUT --> R["Approved recipient"]
    DEC -- "Block/hold" --> HOLD["Quarantine / Review"]
    CLASS --> AUDIT[("Protected audit log")]
    DEC --> AUDIT
    A["Risk/approval metadata"] --> CLASS
~~~

Đường **người dùng → API** không đáng tin chỉ vì có token hợp lệ. Đường **report builder → external recipient** là ranh giới tiết lộ dữ liệu quan trọng. Tệp ở **staging** cũng phải được phân quyền, mã hóa và có thời hạn; tên file khó đoán không thay thế quyền truy cập.

### 8.3. Control objectives

| ID | Mục tiêu bảo mật | Control cần có |
| --- | --- | --- |
| **DLP-OBJ-01** | Chỉ export các bản ghi mà user có quyền | Authorization lọc theo subject, role, tenant và phạm vi được giao |
| **DLP-OBJ-02** | Classification không được tự hạ bởi client | Metadata tin cậy hoặc phân loại từ nội dung/kết quả |
| **DLP-OBJ-03** | Dữ liệu Confidential chỉ đến đích được phê duyệt | Destination allowlist có governance, DLP policy |
| **DLP-OBJ-04** | Tập dữ liệu Restricted không đi qua đường export thông thường | Block hoặc review theo risk policy |
| **DLP-OBJ-05** | Không phát file trước khi có quyết định | Kiểm soát staging và delivery, chống race |
| **DLP-OBJ-06** | Mọi export được truy vết và có thể kiểm chứng | Audit actor, dữ liệu phân loại, đích, quyết định, build |
| **DLP-OBJ-07** | Khi engine lỗi, không tự cấp quyền xuất nhạy cảm | Failure behavior theo classification và risk |
| **DLP-OBJ-08** | Có xử lý false positive và ngoại lệ hợp lệ | Workflow review, hạn, approver, retest |

**Không chỉ dựa vào đếm số bản ghi.** Một bản ghi chứa khóa riêng hoặc dữ liệu cực nhạy cảm có thể gây hậu quả lớn hơn cả nghìn bản ghi thông thường.

## 9. Ví dụ Java/Spring Boot: quyết định DLP trước khi gửi báo cáo

### 9.1. Cách thiết kế responsibility

Ứng dụng cần tách rõ:

1. **Authorization:** người dùng có quyền tạo báo cáo chứa **tập dữ liệu này** không.
2. **Data minimization:** có thể loại bỏ trường không cần thiết không.
3. **Classification:** xác định mức nhạy cảm từ dữ liệu/metadata tin cậy.
4. **DLP decision:** dữ liệu ở mức đó có được gửi tới **đích cụ thể** qua **kênh cụ thể** không.
5. **Delivery:** chỉ khi có quyết định cho phép và file không bị thay đổi sau scan/decision.
6. **Audit:** lưu thông tin quyết định, không lưu nguyên toàn bộ báo cáo/PII vào log.
7. **Exception workflow:** nếu policy yêu cầu approval, phải chờ approval thật trước khi gửi.

### 9.2. Java example – pseudocode có cấu trúc

Đoạn code minh họa ý tưởng control, **không phải ứng dụng Spring Boot đầy đủ để biên dịch độc lập**. Các interface và domain type cần triển khai, cùng authentication, validation, giới hạn kích thước và audit.

~~~java
@Service
public class CustomerExportService {
    private final CurrentPrincipal principal;
    private final AuthorizedOrderQuery orders;
    private final ReportRenderer renderer;
    private final DataClassifier classifier;
    private final DlpPolicyEngine dlp;
    private final ControlledDelivery delivery;
    private final ExportAudit audit;

    public CustomerExportService(
            CurrentPrincipal principal,
            AuthorizedOrderQuery orders,
            ReportRenderer renderer,
            DataClassifier classifier,
            DlpPolicyEngine dlp,
            ControlledDelivery delivery,
            ExportAudit audit) {
        this.principal = principal;
        this.orders = orders;
        this.renderer = renderer;
        this.classifier = classifier;
        this.dlp = dlp;
        this.delivery = delivery;
        this.audit = audit;
    }

    public ExportReceipt export(ExportRequest request) {
        VerifiedSubject subject = principal.requireVerified();

        // Scope cua du lieu phai do server xac dinh tu quyen tin cay.
        AuthorizedDataset data = orders.findWithinAuthorizedScope(
                subject, request.reportFilter());

        // Thuc hien data minimization theo muc dich da duoc phe duyet.
        AuthorizedDataset minimized = data.minimizeFor(
                request.purpose());

        DataClassification classification =
                classifier.classifyTrusted(minimized);

        ExportContext context = new ExportContext(
                subject.id(),
                classification,
                request.destination(),
                "CUSTOMER_REPORT",
                request.purpose());

        DlpDecision decision = dlp.evaluate(context, minimized);

        if (decision.type() != DlpDecisionType.ALLOW) {
            // Khong dua raw report, token hoac PII vao audit log.
            audit.recordDeniedOrHeld(subject.id(),
                    decision.ruleId(), decision.type());
            throw new ExportNotPermittedException();
        }

        // Delivery phai dam bao output dung voi dataset da duoc duyet.
        // Khong de actor khac thay noi dung hoac destination sau decision.
        byte[] bytes = renderer.renderCsv(minimized);
        ExportReceipt receipt = delivery.deliverApproved(
                bytes, request.destination(), decision);

        audit.recordAllowed(subject.id(), decision.ruleId(),
                receipt.id(), classification);
        return receipt;
    }
}
~~~

**Những điều mã trên chưa giải quyết hết:**

- **Race/TOCTOU:** dataset, quyền, destination và nội dung file không được tự ý đổi giữa lúc policy quyết định và lúc chuyển. Hệ thống thực nên tạo artifact bất biến/định danh digest, áp dụng policy trên artifact cần gửi và ràng buộc delivery với quyết định đó.
- **Dữ liệu lớn:** gom toàn bộ báo cáo vào memory là ví dụ đơn giản. Trong sản xuất nên có luồng staging có kiểm soát, giới hạn dung lượng và kiểm tra hoàn tất trước khi tạo link phát file; không stream dữ liệu nhạy cảm trực tiếp cho client khi quyết định chặn chưa hoàn tất.
- **Classification:** một giá trị “CONFIDENTIAL” do frontend gửi **không đáng tin**; phải dựa vào source metadata và/hoặc chính nội dung được xử lý.
- **Đích nhận:** request.destination() phải được xác thực theo policy và ràng buộc với delivery, tránh thay đích sau approval hoặc qua redirect.
- **Failure mode:** lỗi policy engine, timeout hoặc parse error phải được xử lý theo chính sách an toàn. Exception không tự mở đường gửi.
- **Authorization:** AuthorizedOrderQuery là tầng nghiệp vụ có nhiệm vụ lọc theo quyền; DLP không thay nhiệm vụ đó.
- **CSV security:** nếu export có dữ liệu người dùng, phải xem rủi ro công thức spreadsheet khi mở CSV và encoding; đó là một control riêng, không phải chứng minh DLP.
- **Audit consistency:** cần mô hình ghi event phù hợp với giao dịch/bất đồng bộ, có trạng thái giao hàng thật và retry/idempotency, không chỉ log “allowed” trước khi gửi thành công.
- **Approvals:** quyết định HOLD/REVIEW không được chuyển thành ALLOW chỉ vì người dùng bấm xác nhận.
- **Download URL:** phải giới hạn phạm vi, TTL, identity hoặc cơ chế được phê duyệt; object staging không được public.

Một phiên bản sản xuất có thể dùng **asynchronous export job**: tạo tập kết quả đúng quyền → xuất vào vùng lưu trữ riêng → classify/scan → policy decision → approval nếu cần → tạo link phân phối có kiểm soát. Cần đảm bảo **không giao file ra ngoài trước khi có quyết định**.

### 9.3. Rule DLP ví dụ (YAML minh họa)

~~~yaml
policy_id: "DLP-CUSTOMER-EXPORT-DEMO"
version: "1.0"
owner: "Data Protection Team"
status: "DRAFT"
scope:
  application: "orders-api"
  channels:
    - "report-export"
    - "approved-partner-delivery"
requirements:
  - id: "DLP-REQ-01"
    description: "Restricted data must not be exported by standard workflow"
    match:
      classification: "RESTRICTED"
    decision: "BLOCK"
  - id: "DLP-REQ-02"
    description: "Confidential data only to approved destinations"
    match:
      classification: "CONFIDENTIAL"
      destination_approved: false
    decision: "HOLD_FOR_REVIEW"
  - id: "DLP-REQ-03"
    description: "Confidential data to approved partner"
    match:
      classification: "CONFIDENTIAL"
      destination_approved: true
      valid_business_purpose: true
      authorization_verified: true
    decision: "ALLOW"
defaults:
  unknown_classification: "HOLD_FOR_REVIEW"
  policy_engine_unavailable: "BLOCK_OR_HOLD_BY_RISK"
evidence_plan:
  - "Negative tests for unauthorized destination"
  - "Classification and rule matching tests"
  - "Delivery binding and TOCTOU tests"
  - "Runtime audit and policy version review"
~~~

Mẫu YAML **không phải policy đã được phê duyệt** và không thể dùng trực tiếp cho một engine cụ thể. Phần defaults chỉ là **ý định chính sách**: hệ thống thật phải định nghĩa chính xác điều gì được block/hold theo dữ liệu và yêu cầu khả dụng. Chưa có bằng chứng rule đã chạy.

### 9.4. Test matrix cho DLP export

| Kịch bản | Kết quả mong đợi | Evidence cần lưu |
| --- | --- | --- |
| User A xuất dữ liệu trong phạm vi được phép tới đích được duyệt | Cho phép nếu classification/purpose phù hợp | Positive test, decision ID, receipt |
| User A thử xuất dữ liệu của user B | Bị từ chối **ở authorization**, trước khi xét DLP | Cross-account negative test |
| User sửa nhãn classification thành Public | Server không tin nhãn tự khai; policy vẫn áp đúng | Tamper test |
| Có dữ liệu Restricted trong tập kết quả | Block/hold theo policy | Classification + enforcement test |
| Dữ liệu Confidential gửi tới email cá nhân | Chặn hoặc hold theo policy | Destination negative test |
| Dữ liệu Confidential gửi tới đối tác được phép | Chỉ cho phép khi đủ điều kiện nghiệp vụ, quyền, kênh | Approved path test |
| File chứa mẫu regex giống PII nhưng là dữ liệu giả | Hệ thống có hành vi phù hợp chính sách và review | False positive test |
| Dữ liệu nhạy cảm được biến đổi định dạng | Kết quả detection/giới hạn được ghi rõ | False negative/robustness test |
| Policy service timeout hoặc unavailable | Không tự phát file nhạy cảm ngoài quyền | Failure-mode test |
| Artifact bị sửa sau khi scan | Không thể gửi bản khác với bản đã duyệt | TOCTOU/integrity test |
| Export file quá lớn/không đọc được | Không đi qua đường gửi tự do; có quyết định lỗi rõ | Size/parser limit test |
| Approval bị giả mạo/hết hạn/sai recipient | Không vượt rule | Workflow negative test |
| Link tải xuống bị chuyển cho người khác | Bị từ chối theo ràng buộc identity/scope | Delivery authorization test |
| API export mới hoặc worker nội bộ | Cùng quy tắc bao phủ, không có bypass | Integration/architecture test |
| Log DLP chứa thông tin khách hàng | Không ghi raw PII/secret trái yêu cầu | Audit privacy test |
| Rule được cập nhật phiên bản mới | Test hồi quy theo rule mới trên build mục tiêu | Versioned test report |

Một suite “100% PASS” vẫn không hỗ trợ kết luận nếu thiếu kịch bản **đích không được phép, file lớn, xuất ngoài phạm vi hoặc bypass qua worker**.

## 10. Từ DLP event đến incident và khắc phục

### 10.1. DLP event không mặc định là incident

Một rule hit có thể là:

- Hành vi trái policy đã được ngăn.
- Hoạt động hợp lệ nhưng policy quá rộng.
- Thử nghiệm được phép hoặc dữ liệu giả.
- Hành vi sai quy trình cần huấn luyện.
- Tín hiệu nghi exfiltration hoặc compromise thực tế.
- Sự kiện chưa xác định cần điều tra.

**Alert ≠ confirmed breach.** Phải phân loại bằng ngữ cảnh, bằng chứng và mức rủi ro.

### 10.2. Quy trình điều tra

1. **Tiếp nhận và lưu metadata:** time, actor, destination, channel, rule ID/version, event ID, action taken.
2. **Kiểm tra chất lượng detection:** đúng loại dữ liệu không? Có false positive?
3. **Xác minh exposure:** dữ liệu có thực sự rời phạm vi được phép, hoặc chỉ bị block trước khi gửi?
4. **Ước lượng phạm vi:** loại dữ liệu, khối lượng, người nhận, quyền và thời gian.
5. **Đánh giá nguy cơ tiếp diễn:** có session bị chiếm, automation lỗi hoặc kênh bypass không?
6. **Cô lập/giảm thiểu nếu cần:** thu hồi link, khóa token, dừng export, hạn chế chia sẻ theo thẩm quyền.
7. **Phối hợp điều tra và nghĩa vụ thông báo** nếu có dấu hiệu sự cố thật; không tự suy mọi sự kiện là vi phạm pháp lý.
8. **Ghi phát hiện và nguyên nhân gốc**: rule sai, thiếu coverage, nhãn sai, authorization sai, approval thiếu, v.v.
9. **Khắc phục và retest:** kiểm chứng đường thất bại trên bản triển khai phù hợp.
10. **Cập nhật policy/risk/control register:** xem có cần thay rule, scope, giáo dục người dùng hoặc thiết kế data flow.

Không nên lưu toàn bộ tệp nhạy cảm vào ticket chỉ để chứng minh rule đã phát hiện. Dùng **reference ID, digest, metadata tối thiểu hoặc bằng chứng được bảo vệ** theo quy trình.

### 10.3. Phân loại finding đúng nguyên nhân

| Loại gap | Ví dụ | Hành động chính |
| --- | --- | --- |
| **Classification gap** | Dữ liệu bị gắn nhãn Public sai | Sửa quy tắc/phương pháp phân loại, review lineage |
| **Policy gap** | Chưa có quy định export đối với đối tác mới | Data owner và policy owner làm rõ điều kiện |
| **Detection gap** | Rule không nhận ra dữ liệu nhạy cảm trong định dạng mới | Tune detector và test hồi quy |
| **Enforcement gap** | Có alert nhưng file vẫn gửi dù policy yêu cầu block | Sửa integration/decision/điểm thực thi |
| **Coverage gap** | DLP chỉ kiểm tra HTTP download, bỏ qua webhook/job | Mở rộng điểm kiểm soát và test |
| **Authorization gap** | Export chứa bản ghi mà user không có quyền | Sửa quyền ở tầng nghiệp vụ/data |
| **Evidence gap** | Có tool nhưng không có test, log version hoặc cấu hình production | Thu thập bằng chứng phù hợp |
| **Operating gap** | Agent hoặc rule bị tắt/không nhận dữ liệu | Sửa vận hành, health monitoring và audit |
| **Ownership gap** | Không rõ ai duyệt đích nhận, xử lý false positive | Giao trách nhiệm, workflow, RACI |

Không dùng việc **tăng số lượng rule** làm phương án mặc định cho mọi gap. Nhiều khi đúng giải pháp là **giảm thu thập dữ liệu, sửa authorization hoặc thay luồng nghiệp vụ**.

## 11. False positive, false negative và hiệu quả DLP

### 11.1. Hai loại sai số

- **False positive (FP):** detector đánh dấu nội dung/hoạt động là vi phạm khi thực tế không thuộc trường hợp cần ngăn.
- **False negative (FN):** detector không phát hiện nội dung/hoạt động nhạy cảm mà policy cần xử lý.

Ví dụ: regex nhận diện số dạng thẻ thanh toán có thể chặn dữ liệu giả **FP**; một file ảnh chứa dữ liệu nhạy cảm không được OCR hoặc một file nén không đọc được có thể **FN**.

Một số hệ thống chỉ biết **alerts đã phát sinh**, không biết bao nhiêu nội dung nhạy cảm bị bỏ qua; vì vậy không thể suy ra FN rate thật từ số lượng alert thấp.

### 11.2. Đo detector bằng tập dữ liệu đã gán nhãn

Với tập kiểm thử có ground truth phù hợp:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| **TP** | Sự kiện nhạy cảm/vi phạm được phát hiện đúng |
| **FP** | Sự kiện không thuộc trường hợp mục tiêu nhưng bị phát hiện sai |
| **FN** | Sự kiện mục tiêu mà detector bỏ sót |
| **TN** | Sự kiện không thuộc mục tiêu và không bị phát hiện |

Có thể tính:

- **Precision = TP / (TP + FP):** trong các cảnh báo, bao nhiêu là đúng.
- **Recall = TP / (TP + FN):** trong các trường hợp mục tiêu, bao nhiêu được phát hiện.
- **False positive rate = FP / (FP + TN):** trong các trường hợp thực sự âm tính, bao nhiêu bị cảnh báo sai.

Những tỷ lệ này **chỉ có ý nghĩa với tập kiểm thử và cách gán nhãn đã nêu rõ**. Nếu đánh giá 20 file cố tình chọn đều dễ nhận diện, không thể tuyên bố detector đạt recall như vậy trên mọi dạng dữ liệu thật.

### 11.3. Control effectiveness khác detection accuracy

Ngay cả detector có precision/recall cao, **control DLP end-to-end** vẫn có thể thất bại vì:

- Kênh nguy hiểm không đi qua detector.
- Chính sách chọn **monitor** thay vì block cho tình huống cần chặn.
- Destination được đánh giá sai hoặc bị thay sau approval.
- Alert không được xử lý kịp và dữ liệu đã bị gửi.
- DLP agent ngừng chạy nhưng không có health alert.
- Policy rule chỉ được triển khai ở staging hoặc không đúng phiên bản.
- Người dùng có đường export khác không bị kiểm soát.
- Thông báo/quy trình manual review gây trì hoãn và bypass.

Do đó, phải kiểm tra **detection → decision → enforcement → operational response**, không chỉ bộ nhận diện nội dung.

## 12. Security assurance: chứng minh DLP có hiệu quả như thế nào?

### 12.1. Ba lớp đánh giá

| Lớp | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Design effectiveness** | Control có giải quyết đúng data flow, threat và policy? | Data map, classification rules, DFD, threat model, design review |
| **Implementation effectiveness** | Rule, agent, gateway, IAM, API hook và policy version đã triển khai đúng scope? | Config snapshot, code review, IaC, deployment inventory, integration test |
| **Operating effectiveness** | DLP có phát hiện/chặn theo tiêu chí, hoạt động ổn định và xử lý alert trong kỳ? | Test run, event/audit log, health metrics, incident/ticket/retest, review ngoại lệ |

Kết luận hiệu quả phải gắn với **security claim**:

> “Trong phạm vi Orders API export, dữ liệu Restricted không thể được chuyển qua kênh report-export thông thường; dữ liệu Confidential chỉ được chuyển tới đích có phê duyệt và hành động được audit.”

Chính sách trên có thể kiểm thử được bằng **kịch bản dương/âm**, cấu hình và tình huống thất bại. Nếu chỉ biết engine có rule nhưng chưa thử đường export, chưa đủ bằng chứng.

### 12.2. Bằng chứng cần metadata gì?

- **Control ID, policy/rule ID và version.**
- **Asset/data class**, môi trường, channel, service và build.
- **Test scenario, input class** (không cần lưu dữ liệu nhạy cảm nguyên bản), expected và actual result.
- **Decision type**, rule hit và enforcement outcome.
- **Actor và destination loại định danh phù hợp**, có giảm thiểu PII.
- **Thời điểm**, test run, công cụ/người chạy và reviewer.
- **Phạm vi**, đường không được kiểm tra, độ tin cậy và giả định.
- **Findings, ngoại lệ, approval, remediation và retest.**
- **Cơ chế bảo vệ tính toàn vẹn và thời hạn lưu evidence.**

**Đúng phiên bản là quan trọng:** một test chạy khi rule v1 ở staging không chứng minh rule v2 đã block trên production, đặc biệt khi dữ liệu hoặc đường egress thay đổi.

### 12.3. Trạng thái kết luận tham khảo

| Trạng thái | Ý nghĩa |
| --- | --- |
| **Effective within assessed scope** | Có bằng chứng đủ cho control đạt mục tiêu trong scope và kỳ đánh giá |
| **Partially effective** | Một phần đạt, còn gap về luồng hoặc thời gian |
| **Ineffective** | Có bằng chứng rule/điểm thực thi không đáp ứng claim |
| **Insufficient evidence** | Chưa có căn cứ kết luận, cần test/review thêm |
| **Exception approved** | Không đáp ứng đầy đủ nhưng có quyết định ngoại lệ hợp lệ, rủi ro còn lại được quản lý |
| **Not applicable** | Có lý do và thẩm quyền xác nhận yêu cầu không áp dụng |

**Exception approved không đồng nghĩa control đạt.** Một tài liệu “DLP policy đã ban hành” cũng không tự chứng minh toàn bộ các đường xuất dữ liệu đã được bảo vệ.

### 12.4. Lấy mẫu và độ bao phủ

Khi không thể kiểm tra tất cả kênh, cần:

1. Xác định population: số endpoint, service, bucket, user group, egress route hoặc kiểu tệp.
2. Chọn mẫu theo rủi ro, mức thay đổi và phân loại dữ liệu; nếu cần suy luận thống kê, phải thiết kế lấy mẫu phù hợp.
3. Nêu số mẫu, tiêu chí chọn và các trường hợp loại trừ.
4. Không suy từ **5/5 file test PASS** rằng mọi loại file và mọi kênh đều được chặn.
5. Đặc biệt ưu tiên kiểm tra **Restricted data, external destinations, service credentials và luồng mới**.
6. Thêm kiểm tra định kỳ/trigger theo thay đổi.

Kết quả kiểm tra cần phân biệt **coverage** với **mức an toàn**. Bao phủ 80% kênh không có nghĩa 80% dữ liệu được bảo vệ.

## 13. DLP metrics và chương trình vận hành

| Chỉ số | Hỗ trợ quyết định | Giới hạn |
| --- | --- | --- |
| **Data discovery coverage** | Bao nhiêu kho dữ liệu/kênh thuộc scope đã được phân loại | Không chứng minh classification chính xác |
| **Enforcement coverage** | Tỷ lệ đường truyền rủi ro cao có điểm chặn/kiểm tra | Cần mẫu số và kiểm chứng bypass |
| **Rule detection precision/recall trên tập test** | Chất lượng bộ nhận diện theo mẫu đánh giá | Không tự đại diện production |
| **Confirmed exfiltration incidents** | Sự kiện dữ liệu thực sự rời phạm vi trái policy | Phụ thuộc điều tra và khả năng phát hiện |
| **Blocked high-risk attempts** | Các hành động bị block trước khi tiết lộ | Số nhiều có thể do tấn công tăng hoặc rule sai |
| **Policy decision latency** | Độ trễ trước khi gửi/cho phép | Cần cân bằng availability và rủi ro |
| **False positive burden** | Ảnh hưởng tới hoạt động hợp lệ và đội review | Cần phân loại đúng dữ liệu thử/hoạt động hợp lệ |
| **Time to triage/respond** | Khả năng xử lý alert và giảm thiệt hại | Ghi mốc thời gian nhất quán |
| **Exception age / expiry** | Ngoại lệ còn hiệu lực, quá hạn và rủi ro | Không tính ngoại lệ là control đạt |
| **Health coverage** | Agent, connector, scanner và queue hoạt động trong kỳ | Agent sống không chứng minh rule đúng |
| **Verified remediation time** | Từ finding đến retest đạt | Không dừng ở PR merge |
| **Evidence freshness** | Bằng chứng đúng build, rule version và scope | Không dùng report cũ để kết luận môi trường mới |

**Ví dụ giả định:** trong 25 đường export/upload quan trọng, 18 đường đã được kiểm chứng chặn dữ liệu Restricted đúng policy, 3 đường mới ở monitor-only, 2 đường chưa kiểm tra và 2 đường bị phát hiện bypass. **Verified enforcement coverage = 18/25 = 72%** trong phạm vi đo, không phải “tổ chức an toàn 72%”. Hai đường bypass có thể liên quan dữ liệu nhạy cảm nhất và cần được ưu tiên theo rủi ro.

### 13.1. Điều chỉnh rule mà không làm mất khả năng kiểm chứng

Một vòng tune rule có thể gồm:

- Thu thập FP/FN từ tập test và vụ việc đã xác minh.
- Phân loại nguyên nhân: pattern quá rộng, thiếu định dạng, thiếu context, metadata sai, parser lỗi.
- Đề xuất thay đổi **version** của rule, nêu tác động.
- Chạy **regression test** cả các trường hợp phải chặn và phải cho phép.
- Phê duyệt theo thẩm quyền; rollout theo giai đoạn với quan sát phù hợp.
- So sánh metrics sau rollout, xác minh policy thực sự có hiệu lực.
- Lưu phiên bản trước, lý do đổi, approval, test run và kế hoạch rollback.

**Chỉnh rule để giảm alert không được làm biến mất hành vi exfiltration thật** nếu chưa có đánh giá rủi ro.

## 14. DLP exception và quản lý dữ liệu khi điều tra

### 14.1. Ngoại lệ có kiểm soát

Một nhu cầu kinh doanh hợp lệ có thể cần chia sẻ một tập dữ liệu nhạy cảm với đối tác. Nếu policy bình thường chặn, ngoại lệ nên có:

1. **Data owner** và mục đích cụ thể.
2. **Loại dữ liệu, classification và tập dữ liệu** tối thiểu cần chuyển.
3. **Đích nhận**, identity, hợp đồng/kênh và phạm vi sử dụng.
4. **Risk assessment**, nghĩa vụ pháp lý/hợp đồng thực tế áp dụng.
5. **Control bù trừ**: masking, encryption, hạn download, giới hạn người nhận.
6. **Người phê duyệt đúng thẩm quyền**, hạn và điều kiện thu hồi.
7. **Audit và bằng chứng gửi** đúng tập dữ liệu/đích đã duyệt.
8. **Review/expiry** và kế hoạch loại bỏ ngoại lệ khi không còn cần thiết.

Ngoại lệ không thể tự miễn trừ nghĩa vụ bắt buộc hoặc biến hành vi rủi ro thành “control effective”.

### 14.2. Bảo vệ dữ liệu trong DLP logs và quarantine

DLP tự nó có thể **thu thập nội dung cực kỳ nhạy cảm**, tạo thêm bề mặt tấn công. Cần:

- **Data minimization:** chỉ lưu trường cần để điều tra; ưu tiên metadata và reference.
- **RBAC/ABAC:** chỉ người có trách nhiệm được xem evidence, file cách ly, thông tin người dùng.
- **Encryption và key management:** bảo vệ kho evidence và đường truyền.
- **Retention:** giữ theo thời hạn phù hợp, xóa an toàn khi hết hạn.
- **Tamper resistance:** hạn chế sửa/xóa audit và có dấu vết truy cập.
- **Redaction:** che nội dung khi gửi sang SIEM/ticket/chat.
- **Data subject/privacy handling:** tuân thủ nghĩa vụ thực tế và quy trình nội bộ về xử lý dữ liệu.

Một hệ thống DLP chuyển nguyên file Restricted tới một log tập trung không được bảo vệ có thể **tạo sự cố mới trong lúc cố ngăn sự cố cũ**.

## 15. Trách nhiệm trong chương trình DLP

| Vai trò | Trách nhiệm | Giới hạn |
| --- | --- | --- |
| **Data owner** | Quyết định classification, mục đích và người nhận được phép theo thẩm quyền | Không tự bỏ qua nghĩa vụ bắt buộc |
| **Security/DLP owner** | Thiết kế rule, giám sát policy, đánh giá coverage và hiệu quả | Không mặc định hiểu mọi nhu cầu nghiệp vụ |
| **Application/control owner** | Tích hợp DLP với authorization, export, delivery, audit | Không phó mặc dữ liệu nghiệp vụ cho proxy |
| **Platform/SRE** | Vận hành agent, gateway, cloud connectors, policy services | Health check không thay test hiệu quả nghiệp vụ |
| **Engineering** | Implement, viết test, sửa gaps và cung cấp evidence | PR merge không đồng nghĩa production đã được bảo vệ |
| **Risk owner** | Quyết định xử lý residual risk trong quyền được giao | Không thay thế assessment về nội dung và công nghệ |
| **Privacy/legal/compliance** | Đánh giá nghĩa vụ và cách xử lý dữ liệu cá nhân | Không tự xác định control kỹ thuật đã hoạt động |
| **Assurance/audit reviewer** | Đánh giá bằng chứng, kết luận và giới hạn độc lập phù hợp | Không tự động có quyền chấp nhận rủi ro hoặc cấp ngoại lệ |

### 15.1. RACI minh họa

*R = Responsible; A = Accountable; C = Consulted; I = Informed.*

| Hoạt động | Data owner | DLP owner | App/Platform owner | Risk owner | Assurance |
| --- | --- | --- | --- | --- | --- |
| Phân loại và yêu cầu chia sẻ dữ liệu | **A/R** | C | C | C | I |
| Thiết kế DLP policy/rules | C | **A/R** | C | C | C |
| Triển khai enforcement trong API | C | C | **A/R** | I | C |
| Vận hành detection và triage | C | **A/R** | R | I | C |
| Xác minh effectiveness độc lập (khi cần) | C | C | C | I | **A/R** |
| Khắc phục gap tích hợp | C | C | **A/R** | C | C |
| Phê duyệt residual risk theo thẩm quyền | C | C | C | **A/R** | I |

Đây là **ma trận minh họa**, cần thay bằng phân quyền của tổ chức. Với DLP dùng chung, phải xác định rõ trách nhiệm giữa nền tảng và từng service.

## 16. Mẫu hồ sơ assurance đánh giá DLP

Mẫu YAML sau **chỉ minh họa trạng thái chưa có bằng chứng**, không phải kết quả kiểm thử thực:

~~~yaml
assessment_id: "DLP-ASSURANCE-DEMO-009"
control_id: "CTRL-DLP-EXPORT-01"
control_owner: "Orders API Technical Owner"
data_owner: "Customer Data Owner"
risk_owner: "Orders Product Owner"
policy:
  id: "DLP-CUSTOMER-EXPORT-DEMO"
  version: "1.0"
  status: "DRAFT"
security_claims:
  - "Restricted exports are blocked or held before delivery"
  - "Confidential reports go only to approved destinations"
  - "Export actions are authorized and audited"
scope:
  service: "orders-api"
  environment: "integration"
  build: "demo-build-not-verified"
  channels:
    - "report-export"
    - "approved-partner-delivery"
requirements:
  - id: "DLP-REQ-01"
    proof: "Negative export test for restricted data"
  - id: "DLP-REQ-02"
    proof: "Destination and approval tests"
  - id: "DLP-REQ-03"
    proof: "Authorization and audit review"
tests:
  - "Cross-account authorization"
  - "Mislabelled input and classification"
  - "Disallowed destination and bypass route"
  - "Policy engine timeout"
  - "Artifact mutation after decision"
  - "Large file and unparseable content"
  - "False positive/false negative regression"
design_review: "PENDING"
implementation_review: "NOT_VERIFIED"
operating_review: "NOT_VERIFIED"
evidence_refs: []
assurance_conclusion: "INSUFFICIENT_EVIDENCE"
confidence: "LOW"
findings: []
next_action: "Execute security tests and validate runtime policy"
exception:
  approved: false
  approver: null
~~~

Hồ sơ thật cần thêm thời gian, người đánh giá, kết quả test cụ thể, rule engine version, phạm vi population, bằng chứng bảo vệ, tình trạng triển khai production và quyết định rủi ro. **DRAFT / INSUFFICIENT_EVIDENCE** trong ví dụ có ý nghĩa: chưa có căn cứ xác nhận control đạt.

## 17. Các sai lầm phổ biến

### 17.1. Coi DLP là một sản phẩm thay vì một chương trình

**Sai:** “Đã mua DLP nên dữ liệu không thể thất thoát.”

**Đúng:** xác định data flow, classification, owner, policy, kênh, cách chặn, cách điều tra và evidence.

### 17.2. Dựa vào regex đơn giản rồi nói phát hiện mọi dữ liệu nhạy cảm

Regex có thể sai trên dữ liệu giả, định dạng mới, tệp ảnh hoặc dữ liệu đã biến đổi. **Cần:** tập test có ground truth, kết hợp context, đo FP/FN và xác định giới hạn.

### 17.3. Không xác định đích được phép

Cùng một file có thể được phép gửi cho đối tác X nhưng không phải email cá nhân Y. **Cần:** policy xét destination, purpose, approval, subject và data class.

### 17.4. Nhầm cảnh báo với ngăn chặn

DLP ở chế độ monitor-only có thể phát alert sau khi dữ liệu đã gửi. **Cần:** kiểm tra enforcement outcome và thời điểm phơi nhiễm.

### 17.5. Đánh đồng DLP và authorization

User A không được xuất bản ghi B ngay cả khi DLP cho phép chia sẻ báo cáo Confidential tới một đích được duyệt. **Cần:** authorization trước và DLP tại ranh giới chia sẻ.

### 17.6. Tin nhãn do client gửi

Client tự gắn Public để vượt policy. **Cần:** classification tin cậy và kiểm tra nội dung hoặc metadata server.

### 17.7. Quét file sau khi đã cấp public link

DLP phát hiện lúc đó có thể quá muộn. **Cần:** phân biệt inline và at-rest scan, bảo vệ staging và ngăn public access trước phê duyệt.

### 17.8. Không kiểm tra bypass qua worker, API và service identity

Mail gateway tốt không bảo vệ webhook trực tiếp từ backend. **Cần:** đánh giá mọi data flow quan trọng và shared responsibility.

### 17.9. Chặn quá nhiều làm người dùng tìm đường vòng

False positive cao và quy trình review chậm có thể khuyến khích shadow IT. **Cần:** tuning, giáo dục, kênh chia sẻ hợp lệ và hành động tương xứng.

### 17.10. Lưu toàn bộ tệp nhạy cảm vào DLP log

DLP evidence tự thành nguồn rủi ro. **Cần:** minimization, che nội dung, RBAC, encryption, retention và audit truy cập.

### 17.11. Dùng test cũ sau khi rule hoặc môi trường đổi

Policy rule mới có thể thay detection và enforcement. **Cần:** versioned regression tests và verification trên build/môi trường mục tiêu.

### 17.12. Đóng finding khi có ticket “fixed”

Một file vẫn có thể gửi qua kênh khác. **Cần:** retest kịch bản gốc và các biến thể bypass, kiểm tra deployment và bằng chứng vận hành.

## 18. Checklist thiết kế và đánh giá DLP

- [ ] Đã xác định tài sản, loại dữ liệu, data owner và mức classification.
- [ ] Có data flow/inventory cho data at rest, in motion và in use trong phạm vi.
- [ ] Biết các kênh rủi ro: email, endpoint, cloud/SaaS, API, export, webhook, CI/CD.
- [ ] Chính sách nêu ai được gửi **dữ liệu gì, tới đâu, qua kênh nào, vì mục đích nào**.
- [ ] Classification và approval được lấy từ nguồn tin cậy, không dựa vào client tùy ý.
- [ ] Các yêu cầu DLP được ánh xạ tới control owner và enforcement point.
- [ ] Có kiểm tra authorization trước khi xuất dữ liệu hoặc cấp download.
- [ ] Rule detection có test dương/âm, ví dụ FP/FN và giới hạn định dạng.
- [ ] Có tiêu chí phân biệt monitor, warn, hold, approve, redact và block.
- [ ] Fail-open/fail-closed được quyết định theo rủi ro và kiểm thử khi dependency lỗi.
- [ ] Không có đường phát file trước decision; staging và delivery được phân quyền.
- [ ] Có test destination sai, classification tampering, race/TOCTOU, large file và unparseable content.
- [ ] Đã kiểm tra worker, service-to-service, public link và các đường bypass.
- [ ] Có health monitoring cho agent/scanner/rule và bảo đảm runtime policy đúng phiên bản.
- [ ] Audit log không lưu secret hoặc PII nguyên văn không cần thiết.
- [ ] Quarantine/evidence được bảo vệ bằng quyền, encryption, retention và review.
- [ ] Alert có triage, owner, escalation, điều tra và phản ứng theo mức rủi ro.
- [ ] Ngoại lệ có data owner/risk owner, thẩm quyền, đích, thời hạn và control bù trừ.
- [ ] Findings có phân loại gap, action owner, milestone và **retest** trước khi đóng.
- [ ] Bằng chứng gắn policy/rule version, build, environment, thời gian và reviewer.
- [ ] Mức coverage và confidence được ghi, không suy thành tỷ lệ an toàn của tổ chức.
- [ ] Có trigger đánh giá lại khi data class, luồng chia sẻ, API hoặc nhà cung cấp đổi.

Checklist hỗ trợ quản trị và kiểm thử; đánh dấu đủ mục **không thay thế** bằng chứng rằng DLP đang hoạt động hiệu quả trong thực tế.

## 19. Câu hỏi tự kiểm tra

1. DLP khác access control, encryption và backup như thế nào?
2. Vì sao người dùng đăng nhập hợp lệ và có quyền đọc vẫn có thể tạo rủi ro data leakage?
3. Hãy nêu ba trạng thái data at rest, in motion và in use cùng ví dụ điểm kiểm soát.
4. Tại sao data discovery và classification phải đi trước việc chọn rule DLP?
5. Một rule chỉ dùng regex có những false positive/negative điển hình nào?
6. Vì sao phải kết hợp data class với destination, purpose và actor?
7. Chế độ monitor-only có được kết luận là đã ngăn exfiltration không?
8. Nếu DLP engine unavailable, nên quyết định fail-open hay fail-closed dựa trên thông tin nào?
9. Phân biệt inline DLP với API-based scan sau khi file đã lưu trong cloud.
10. User A được quyền tạo báo cáo của A nhưng yêu cầu chứa dữ liệu B. Control nào phải từ chối trước?
11. Nếu client gửi classification=PUBLIC, vì sao server không được tin?
12. Một báo cáo được scan rồi bị thay nội dung trước khi gửi. Rủi ro gì xảy ra, cần kiểm tra điều gì?
13. Precision, recall và false positive rate tính từ TP/FP/FN/TN như thế nào?
14. Vì sao detector có recall cao vẫn không chứng minh DLP toàn hệ thống hiệu quả?
15. Có thể dùng log DLP chứa toàn bộ PII để điều tra không? Những rủi ro và control nào cần xem?
16. Khi một rule chặn nhầm báo cáo hợp lệ, có nên tắt rule vĩnh viễn không? Hãy mô tả cách tune có bằng chứng.
17. Một webhook trong backend đi trực tiếp ra đối tác có thể bỏ qua email DLP ra sao?
18. Phân biệt detection gap, enforcement gap và evidence gap qua một kịch bản export.
19. Nếu 18/25 đường export có bằng chứng được bảo vệ, con số 72% nói lên điều gì và không nói lên điều gì?
20. Sau khi sửa rule và triển khai, cần bằng chứng nào để đóng finding DLP?

## 20. Tổng kết

**Data Loss Prevention (DLP)** là phương pháp **nhận diện, giám sát và kiểm soát việc dữ liệu nhạy cảm rời hoặc được sử dụng ngoài phạm vi cho phép**. Hiệu quả của DLP phụ thuộc vào **data discovery/classification, chính sách rõ người–dữ liệu–kênh–đích, khả năng phát hiện nội dung, điểm thực thi, ứng xử khi lỗi, xử lý false positive/negative và quản trị ngoại lệ**. Một công cụ quét hoặc một cảnh báo đơn lẻ không chứng minh dữ liệu đã được ngăn thất thoát. Trong **SECURITY_SECURITY_ASSURANCE**, phải truy vết từng rủi ro tới **security requirement → control → test/audit/evidence → finding → remediation và retest**, gắn kết luận với đúng phạm vi, phiên bản, kênh và thời điểm. Khi các luồng dữ liệu, ứng dụng và đối tác thay đổi, chương trình DLP cũng phải được đánh giá và cải tiến liên tục.

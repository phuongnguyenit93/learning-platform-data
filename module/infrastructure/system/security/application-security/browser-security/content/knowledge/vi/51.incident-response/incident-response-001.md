# XSS incident: điều tra và ứng phó sự cố thực thi script ngoài ý muốn trong browser

## 1. Mục tiêu của bài học

Cross-Site Scripting (XSS) xảy ra khi dữ liệu do người dùng hoặc nguồn không đáng tin kiểm soát được đưa vào trang theo cách khiến browser diễn giải dữ liệu đó thành mã có thể thực thi. Khi XSS xuất hiện trong một ứng dụng đang vận hành, nhóm kỹ thuật cần xử lý như một sự cố bảo mật: xác minh tín hiệu, xác định phạm vi, hạn chế tác động, sửa nguyên nhân và kiểm tra toàn bộ đường đi của dữ liệu.

Ứng phó sự cố XSS cần hiểu ranh giới giữa browser, origin và ứng dụng web. Script chạy trong origin của ứng dụng có thể tương tác với DOM, đọc dữ liệu mà JavaScript được phép truy cập và gửi request cùng origin dưới quyền của người đang mở trang. Cookie có thuộc tính **HttpOnly** không thể bị đọc qua **document.cookie**, nhưng XSS vẫn có thể thực hiện hành động bằng session của người dùng thông qua request mà browser tự đính kèm cookie. Vì vậy, chỉ bật HttpOnly hoặc chặn một chuỗi payload chưa đủ để kết luận sự cố đã được xử lý.

Sau bài học, bạn có thể:

- Phân biệt cảnh báo XSS, lỗ hổng có thể khai thác và sự cố đã bị khai thác.
- Phân loại reflected XSS, stored XSS và DOM-based XSS để chọn hướng điều tra.
- Thu thập bằng chứng browser và server mà không làm lộ session, token hoặc dữ liệu cá nhân.
- Đánh giá người dùng, route, dữ liệu và hành động có thể bị ảnh hưởng.
- Cô lập điểm phát sinh XSS, thu hồi credential khi cần và phối hợp khắc phục.
- Sửa nguyên nhân bằng output encoding theo ngữ cảnh, sanitization có kiểm soát, Trusted Types và Content Security Policy (CSP).
- Kiểm chứng bản sửa trên các browser và luồng nghiệp vụ liên quan trước khi khôi phục đầy đủ dịch vụ.

## 2. Khi nào một cảnh báo trở thành XSS incident?

Không phải mọi CSP violation hay chuỗi đáng ngờ trong query string đều chứng minh XSS đã thực thi. Một incident cần được phân loại dựa trên bằng chứng và tác động.

| Mức bằng chứng | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Tín hiệu cần điều tra | CSP report, WAF alert, chuỗi HTML bất thường, phản ánh giao diện lạ | Tạo case, lưu thời điểm và route, kiểm tra nguồn phát sinh |
| Lỗ hổng được xác nhận | Dữ liệu không tin cậy đi tới một execution sink mà không được xử lý phù hợp; test có kiểm soát chứng minh script có thể chạy | Đánh giá mức độ nghiêm trọng và lập kế hoạch khắc phục khẩn cấp |
| Khai thác có khả năng đã xảy ra | Có request, DOM hoặc telemetry phù hợp với hành vi thực thi; nhiều người dùng hoặc tài khoản bị ảnh hưởng | Kích hoạt quy trình incident response, bảo toàn bằng chứng và containment |
| Khai thác được xác nhận | Bằng chứng đáng tin cho thấy script ngoài ý muốn đã chạy hoặc dữ liệu/hành động đã bị truy cập trái phép | Xử lý như sự cố bảo mật; đánh giá credential, dữ liệu và nghĩa vụ thông báo |

Một CSP report có thể xuất hiện do script hợp lệ bị chặn, extension của browser, lỗi cấu hình hoặc nội dung do ứng dụng tạo ra. Report thường thiếu ngữ cảnh để xác định người dùng có bị tấn công hay không. Ngược lại, không có CSP report cũng không chứng minh ứng dụng không có XSS: policy có thể chưa được bật, report endpoint có thể lỗi hoặc browser không gửi báo cáo.

Trong suốt quá trình, hãy ghi rõ mức tin cậy của từng kết luận: **confirmed**, **likely**, **possible** hoặc **not observed**. Không biến một giả thuyết thành sự thật chỉ vì nó phù hợp với một log riêng lẻ.

## 3. Các dạng XSS và ý nghĩa khi điều tra

### 3.1 Reflected XSS

Reflected XSS thường xuất hiện khi dữ liệu từ request như query parameter, path, header hoặc form được đưa trở lại response mà không được encode theo đúng ngữ cảnh. Sự cố có thể chỉ ảnh hưởng người mở một URL được chuẩn bị đặc biệt, nhưng vẫn có thể lan rộng qua email, tin nhắn, quảng cáo hoặc trang bên ngoài dẫn người dùng tới URL đó.

Điểm cần truy vết:

- Parameter hoặc trường request nào chứa dữ liệu đầu vào.
- Route và template nào đưa dữ liệu đó vào response.
- Dữ liệu được đặt trong text node, HTML attribute, JavaScript, URL hay CSS context.
- Có redirect, cache hoặc link rút gọn làm thay đổi đường đi hay không.
- Những người dùng nào đã truy cập URL hoặc route trong khoảng thời gian liên quan.

### 3.2 Stored XSS

Stored XSS xảy ra khi dữ liệu không tin cậy được lưu lại, sau đó được render trong trang của một hoặc nhiều người dùng. Nguồn dữ liệu thường là bình luận, hồ sơ, tên hiển thị, nội dung hỗ trợ, mô tả sản phẩm, nội dung rich text hoặc dữ liệu đồng bộ từ hệ thống khác.

Stored XSS có thể ảnh hưởng người xem khác với người gửi dữ liệu ban đầu. Một bản ghi có thể được render ở nhiều vị trí như trang chi tiết, kết quả tìm kiếm, dashboard quản trị, email preview hoặc màn hình moderation. Vì vậy, sửa một template đang hiển thị chưa chắc đã loại bỏ mọi đường khai thác.

Điểm cần truy vết:

- Bản ghi, bảng dữ liệu, object storage hoặc nguồn đồng bộ chứa nội dung.
- Tài khoản và thời điểm tạo hoặc sửa dữ liệu.
- Tất cả màn hình, API và tác vụ nền có thể render lại nội dung đó.
- Cache CDN, cache ứng dụng, search index và bản export có thể giữ bản sao.
- Người dùng hoặc nhóm quyền nào đã xem nội dung bị ảnh hưởng.

### 3.3 DOM-based XSS

DOM-based XSS xảy ra khi JavaScript phía client đọc dữ liệu không tin cậy rồi đưa dữ liệu đó vào một DOM sink nguy hiểm. Dữ liệu có thể đến từ **location**, **postMessage**, fragment URL, storage, dữ liệu API hoặc một component khác.

Điểm cần truy vết:

- Source phía client, chẳng hạn **location.search**, **location.hash** hoặc **event.data**.
- Sink như **innerHTML**, **outerHTML**, **insertAdjacentHTML**, **document.write**, **eval** hoặc API có thể diễn giải chuỗi thành mã.
- Các hàm trung gian có decode, nối chuỗi hoặc chuyển đổi dữ liệu.
- Bundle JavaScript, source map và phiên bản asset thực tế mà browser tải.
- Service worker hoặc cache có thể tiếp tục phân phối bundle cũ sau khi deploy.

### 3.4 XSS qua nội dung rich text và template

Ứng dụng có thể chủ động hỗ trợ HTML trong nội dung do người dùng nhập. Khi đó, bài toán là xác định một tập con HTML an toàn và bảo đảm mọi nơi render đều tuân theo cùng policy. Sanitization chỉ ở một màn hình không đủ nếu nội dung còn được render ở email, admin console hoặc ứng dụng khác.

Hãy phân biệt dữ liệu cần hiển thị như văn bản với dữ liệu cần hỗ trợ markup. Nếu nghiệp vụ chỉ cần văn bản thuần, hãy giữ dữ liệu ở dạng text và dùng API như **textContent**. Chỉ dùng sanitizer khi thực sự cần cho phép HTML.

## 4. Nguyên tắc ứng phó

1. **Ưu tiên giảm tác động:** nếu có đường khai thác đang hoạt động, cô lập chức năng bị ảnh hưởng càng sớm càng tốt.
2. **Giữ bằng chứng:** ghi nhận log, request ID, phiên bản ứng dụng và cấu hình policy trước khi thay đổi làm mất dấu vết.
3. **Không phát tán payload:** không mở URL đáng ngờ trong browser đang đăng nhập tài khoản thật; không sao chép payload vào ticket, chat hoặc hệ thống có thể tự render HTML.
4. **Giới hạn quyền truy cập:** chỉ người tham gia điều tra cần thiết được xem bằng chứng có dữ liệu nhạy cảm.
5. **Đánh giá theo tác động thực tế:** xem xét quyền của người dùng, dữ liệu họ truy cập và hành động mà script có thể thực hiện.
6. **Sửa nguyên nhân:** xác định source, transformation và sink; không chỉ chặn một chuỗi đã quan sát.
7. **Kiểm chứng trước khi đóng incident:** chạy regression trên các đường render và browser liên quan, đồng thời theo dõi tín hiệu sau phục hồi.

Không dùng tài khoản production hoặc dữ liệu khách hàng để thử lại payload. Việc xác minh khả năng thực thi nên diễn ra trong staging hoặc môi trường cô lập với dữ liệu giả, tài khoản ít quyền và một marker vô hại có thể quan sát được.

## 5. Vòng đời xử lý XSS incident

~~~mermaid
flowchart TD
    A["Nhận tín hiệu"] --> B["Ghi nhận và bảo toàn bằng chứng"]
    B --> C["Xác minh an toàn"]
    C --> D{"Có XSS hoặc nguy cơ khai thác?"}
    D -->|Chưa đủ bằng chứng| E["Tiếp tục điều tra và theo dõi"]
    D -->|Có| F["Phân loại và đánh giá tác động"]
    F --> G["Containment"]
    G --> H["Tìm source, đường đi và sink"]
    H --> I["Sửa nguyên nhân và xử lý dữ liệu bị ảnh hưởng"]
    I --> J["Kiểm thử bảo mật và regression"]
    J --> K{"Đạt tiêu chí phục hồi?"}
    K -->|Chưa| I
    K -->|Đạt| L["Khôi phục có giám sát"]
    L --> M["Theo dõi, tổng kết và cải tiến"]
~~~

Các bước có thể diễn ra song song khi có nhiều nhóm tham gia. Tuy nhiên, mọi thay đổi khẩn cấp cần có người chịu trách nhiệm, thời điểm thực hiện và bằng chứng xác nhận hiệu quả.

## 6. Nhận tín hiệu và tạo hồ sơ incident

Nguồn phát hiện thường gặp:

- CSP violation report hoặc cảnh báo từ Reporting API.
- WAF, reverse proxy hoặc hệ thống phát hiện request bất thường.
- Báo cáo của người dùng về popup, nội dung lạ, redirect hoặc thao tác không mong muốn.
- Telemetry client ghi nhận lỗi JavaScript, thay đổi DOM hoặc route bất thường.
- Hệ thống hỗ trợ khách hàng nhận phản ánh nhiều tài khoản có cùng biểu hiện.
- Kiểm thử bảo mật, bug bounty hoặc rà soát code phát hiện source-to-sink flow nguy hiểm.
- Dấu hiệu account takeover, thao tác trái phép hoặc request cùng origin bất thường sau khi người dùng xem một trang cụ thể.

Khi tạo hồ sơ, ghi tối thiểu:

| Trường | Nội dung |
| --- | --- |
| Incident ID | Mã theo quy trình nội bộ |
| First observed / last observed | Thời điểm đầu và cuối theo UTC |
| Detection source | CSP, WAF, user report, monitoring hoặc security test |
| Affected service and route | Tên ứng dụng, host và route liên quan |
| Environment | Production, staging, browser/version nếu biết |
| Build and asset version | Release ID, commit hoặc hash bundle |
| Request correlation | Request ID, trace ID, edge log ID |
| Initial classification | Reflected, stored, DOM-based hoặc chưa rõ |
| Evidence confidence | Confirmed, likely, possible hoặc not observed |
| Incident owner | Người điều phối và nhóm xử lý |

Không đưa raw cookie, Authorization header, access token, mật khẩu, nội dung cá nhân hoặc toàn bộ URL có query nhạy cảm vào hồ sơ chung. Thay bằng giá trị đã redact, hash hoặc ID tham chiếu tới kho bằng chứng có kiểm soát.

## 7. Xác minh an toàn và tái hiện

Mục tiêu của bước xác minh là trả lời ba câu hỏi: dữ liệu nào bị kiểm soát, dữ liệu đi tới đâu và browser có diễn giải dữ liệu thành hành vi thực thi hay không.

### 7.1 Chuẩn bị môi trường

- Dùng staging hoặc bản sao cô lập có cấu hình gần production.
- Dùng tài khoản test ít quyền, dữ liệu giả và browser profile sạch.
- Ghi lại browser/version, URL, release ID, feature flag và CSP hiện hành.
- Tắt extension không cần thiết để giảm nhiễu; ghi nhận nếu extension là một phần của kịch bản.
- Không mở liên kết đáng ngờ trong session production.
- Dùng request ID và marker thử nghiệm riêng để liên kết log browser với log server.

### 7.2 Tái hiện có kiểm soát

1. Bắt đầu từ route hoặc dữ liệu được báo cáo; không thử hàng loạt payload không liên quan.
2. Xác định nguồn dữ liệu: query, form, record lưu trữ, message event, URL fragment hoặc API response.
3. Theo dõi dữ liệu qua các bước decode, template, component và helper.
4. Xác định sink cuối cùng và ngữ cảnh HTML/attribute/JavaScript/URL/CSS.
5. Trong lab, dùng một marker vô hại để chứng minh browser đã xử lý dữ liệu ngoài ý muốn. Marker chỉ nên ghi một giá trị cố định vào DOM hoặc console, không gửi dữ liệu ra ngoài, không đọc storage và không thực hiện hành động tài khoản.
6. Lưu video, screenshot hoặc trace đã loại bỏ credential; ghi rõ điều kiện để tái hiện.
7. Lặp lại trên route hoặc browser khác chỉ khi có giả thuyết cụ thể về phạm vi.

Ví dụ marker trong một trang lab do nhóm kiểm soát:

~~~javascript
document.documentElement.dataset.xssProbe = "confirmed";
~~~

Marker này chỉ phù hợp để chứng minh JavaScript đã thực thi trong môi trường thử nghiệm. Nó không phải payload để thử trên người dùng hoặc hệ thống bên ngoài.

### 7.3 Phân biệt lỗi hiển thị với thực thi script

Một chuỗi như **&lt;script&gt;** xuất hiện trên trang có thể chỉ là văn bản đã được encode đúng. Ngược lại, XSS có thể xảy ra qua event handler, URL scheme, SVG, template hoặc DOM API mà không có thẻ script rõ ràng. Vì vậy:

- Kiểm tra DOM cuối cùng trong browser, không chỉ response HTML.
- Xác định node và thuộc tính mà dữ liệu đã đi vào.
- Quan sát CSP console/report nhưng không xem report là bằng chứng duy nhất.
- Kiểm tra cả navigation ban đầu lẫn thao tác client sau khi trang tải.
- Xác minh bằng marker vô hại trong lab thay vì đánh giá qua hình thức chuỗi.

## 8. Phân loại mức độ nghiêm trọng

Mức độ phải phản ánh khả năng khai thác và hậu quả. Một XSS chỉ xuất hiện trong trang nội bộ vẫn có thể nghiêm trọng nếu người dùng có quyền quản trị truy cập trang đó.

| Mức | Tiêu chí tham khảo | Hành động |
| --- | --- | --- |
| Critical | Có khai thác đang diễn ra; ảnh hưởng tài khoản quản trị hoặc dữ liệu nhạy cảm diện rộng; có bằng chứng thao tác trái phép hoặc chiếm quyền | Kích hoạt incident khẩn cấp, containment ngay, xem xét thu hồi session/token theo phạm vi |
| High | XSS stored hoặc reflected có thể tiếp cận nhiều người dùng; ảnh hưởng luồng xác thực, thanh toán, quản trị hoặc dữ liệu quan trọng | Ưu tiên hotfix, hạn chế chức năng và theo dõi sát |
| Medium | Cần điều kiện truy cập hoặc tương tác đáng kể; phạm vi hẹp nhưng có thể ảnh hưởng dữ liệu hoặc hành động của người dùng | Lập kế hoạch sửa ưu tiên, kiểm soát đường truy cập và xác minh phạm vi |
| Low | Đường render có rủi ro nhưng chưa chứng minh được thực thi hoặc tác động thấp trong điều kiện hiện tại | Ghi nhận, khắc phục theo quy trình và tăng kiểm thử |

Khi đánh giá, cân nhắc:

- **Khả năng tiếp cận:** route public hay nội bộ; cần đăng nhập hay không; có yêu cầu quyền đặc biệt không.
- **Mức tương tác:** nạn nhân phải mở link, xem record hay chỉ cần tải trang.
- **Phạm vi người dùng:** một tài khoản, một nhóm, toàn bộ khách hàng hay người quản trị.
- **Quyền của origin:** dữ liệu JavaScript có thể đọc, API có thể gọi và hành động có thể thực hiện.
- **Loại dữ liệu:** thông tin cá nhân, dữ liệu tài chính, nội dung riêng tư hoặc dữ liệu quản trị.
- **Khả năng duy trì:** stored content, cache, bundle cũ hoặc service worker có thể tiếp tục phát tán.
- **Bằng chứng khai thác:** request, telemetry, báo cáo người dùng và dấu hiệu hành động bất thường có liên quan.

Không hạ mức độ chỉ vì cookie session có **HttpOnly**. Thuộc tính này giảm khả năng đọc trực tiếp cookie, nhưng script cùng origin vẫn có thể gọi endpoint bằng session của browser và đọc response mà ứng dụng cho phép.

## 9. Xác định phạm vi ảnh hưởng

Phạm vi cần bao gồm cả đường dữ liệu và nhóm người dùng.

### 9.1 Phạm vi kỹ thuật

- Route, template, component và API có liên quan.
- Source đầu vào và sink thực thi.
- Phiên bản frontend/backend bị ảnh hưởng.
- Subdomain, origin hoặc ứng dụng nhúng cùng xử lý dữ liệu.
- Các bản sao dữ liệu trong cache, search index, export, email preview và hệ thống đồng bộ.
- Browser/version và cấu hình CSP/Trusted Types.
- Thời gian lỗ hổng bắt đầu tồn tại và thời điểm bản sửa có hiệu lực thực tế.

### 9.2 Phạm vi người dùng và dữ liệu

- Ai có thể tạo nội dung gây lỗi và ai có thể xem nội dung đó.
- Tài khoản nào truy cập route hoặc record trong khoảng thời gian liên quan.
- Nhóm quyền nào có thể thực hiện hành động nhạy cảm trên cùng origin.
- Dữ liệu nào được hiển thị trong DOM hoặc trả về qua API.
- Có dấu hiệu đọc dữ liệu, thay đổi cấu hình, tạo giao dịch hoặc thao tác trái phép hay không.

Đối chiếu access log với thời gian, route, request ID và tài khoản đã pseudonymize. Một log cho thấy người dùng mở trang không chứng minh họ đã bị khai thác; cần kết hợp với dữ liệu browser, CSP, hành vi API và bằng chứng khác.

### 9.3 Lập bảng phạm vi

| Thành phần | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| Entry point | Dữ liệu đi vào qua đâu? | Request, form, record ID, event source |
| Transformation | Có decode, nối chuỗi hoặc template nào? | Code path, build/source map |
| Sink | Dữ liệu được diễn giải ở đâu? | DOM snapshot đã sanitize, trace, code location |
| Audience | Ai có thể kích hoạt hoặc xem? | ACL, role, access log |
| Persistence | Dữ liệu còn ở đâu sau deploy? | Database, cache, search index, object store |
| Exposure | Dữ liệu/hành động nào có thể bị truy cập? | API inventory, permission map, audit log |

## 10. Bảo toàn bằng chứng

Bằng chứng có thể biến mất khi cache bị purge, record bị xóa, bundle được deploy lại hoặc log hết retention. Trước khi containment làm thay đổi trạng thái hệ thống, hãy lưu những dữ liệu cần thiết theo quy trình incident response.

### 10.1 Bằng chứng nên thu thập

- Request/response metadata: timestamp UTC, method, route, status, request ID và header đã redact.
- CSP report: directive bị vi phạm, blocked URI đã làm sạch, document URI đã bỏ query nhạy cảm, source file và line/column nếu có.
- Browser evidence: screenshot, console output, DOM snapshot đã loại bỏ dữ liệu cá nhân, browser/version và profile state.
- Server evidence: application log, access log, audit event, release ID và feature flag.
- Code evidence: commit, source file, dependency version, bundle hash và cấu hình build.
- Data evidence: record ID, thời điểm tạo/sửa, nguồn đồng bộ và các bản sao cần xử lý.
- Timeline: thời điểm phát hiện, xác minh, containment, deploy, revoke credential và phục hồi.

### 10.2 Xử lý dữ liệu nhạy cảm

- Không lưu raw **Cookie**, **Set-Cookie**, **Authorization**, access token, refresh token hoặc password.
- Không gửi HAR/trace chưa kiểm tra qua ticket hoặc chat thông thường; các file này có thể chứa header và response nhạy cảm.
- Redact query parameter, form value và nội dung DOM có thông tin cá nhân.
- Giữ bản gốc trong kho bằng chứng có phân quyền, audit access và thời hạn lưu rõ ràng nếu quy trình yêu cầu.
- Ghi hash hoặc ID tham chiếu để xác minh tính toàn vẹn mà không nhân bản dữ liệu nhạy cảm.
- Không chạy lại request đã ghi nhận nếu request có thể tạo giao dịch hoặc thay đổi trạng thái.

### 10.3 Mẫu timeline

| Thời điểm UTC | Sự kiện | Người thực hiện | Bằng chứng/ID | Kết quả |
| --- | --- | --- | --- | --- |
| 09:10 | Nhận CSP alert | On-call | Alert ID | Mở incident |
| 09:18 | Xác nhận route liên quan | Security | Request ID đã redact | Cần containment |
| 09:25 | Tắt chức năng render rich text | Application team | Change ID | Giảm bề mặt ảnh hưởng |
| 10:05 | Deploy bản sửa | Release owner | Build ID | Chờ regression |
| 10:40 | Hoàn tất kiểm thử | QA/Security | Test run ID | Đủ điều kiện phục hồi |

Các thời điểm trên chỉ minh họa cách ghi timeline, không phải SLA hoặc thời gian chuẩn cho mọi tổ chức.

## 11. Containment: hạn chế tác động trước khi sửa triệt để

Containment phải phù hợp với đường khai thác và tác động kinh doanh. Chọn thay đổi nhỏ nhất có thể chặn đường khai thác đã xác nhận, sau đó kiểm tra ngay hiệu quả và side effect.

Các biện pháp có thể áp dụng:

1. Tạm tắt chức năng rich text, preview, widget hoặc route đang render dữ liệu không tin cậy.
2. Chuyển nội dung đáng ngờ sang chế độ text-only hoặc tạm ẩn record bị ảnh hưởng.
3. Chặn quyền truy cập vào route hoặc record bằng authorization ở server.
4. Tắt endpoint hoặc integration đang đưa dữ liệu không tin cậy vào sink nguy hiểm.
5. Áp dụng CSP khẩn cấp nếu policy đã được kiểm thử và có thể triển khai an toàn; theo dõi violation và lỗi chức năng sau thay đổi.
6. Purge cache hoặc search index sau khi đã bảo toàn bằng chứng và có danh sách đối tượng cần làm mới.
7. Thu hồi session/token hoặc yêu cầu xác thực lại với nhóm tài khoản có khả năng bị ảnh hưởng.

### 11.1 Khi nào cần thu hồi session hoặc token?

Đánh giá việc revoke dựa trên dữ liệu và quyền mà XSS có thể truy cập:

- Nếu script có thể chạy trong trang xác thực hoặc khu vực có dữ liệu nhạy cảm, xem xét session của người đã truy cập route trong khoảng thời gian bị ảnh hưởng.
- Nếu ứng dụng lưu access token trong **localStorage** hoặc **sessionStorage**, đánh giá khả năng token đã bị đọc và thu hồi token liên quan.
- Nếu session dùng cookie **HttpOnly**, vẫn đánh giá hành động trái phép qua request cùng origin; không mặc định rằng cookie đã bị đánh cắp.
- Nếu có bằng chứng truy cập tài khoản quản trị, xem xét rotate credential, revoke session và kiểm tra audit log của tài khoản đó.
- Tránh reset credential diện rộng khi chưa có phạm vi hoặc căn cứ; phối hợp với owner xác thực để chọn nhóm bị ảnh hưởng và thông báo phù hợp.

### 11.2 Vì sao WAF hoặc blocklist không phải bản sửa cuối?

WAF có thể giảm lưu lượng khai thác đã biết trong lúc nhóm triển khai containment. Tuy nhiên, XSS phụ thuộc vào ngữ cảnh. Cùng một ký tự có thể an toàn trong text node nhưng nguy hiểm trong JavaScript hoặc URL context. Kẻ tấn công cũng có thể thay đổi encoding, cấu trúc hoặc đường đi dữ liệu. Hãy xem rule WAF là lớp giảm thiểu tạm thời; bản sửa phải xử lý đúng source-to-sink flow trong ứng dụng.

## 12. Điều tra nguyên nhân gốc

Một XSS incident thường có nhiều lớp nguyên nhân. Điều tra cần trả lời vì sao dữ liệu không tin cậy được chấp nhận, vì sao nó đến sink, vì sao kiểm soát hiện tại không ngăn được và vì sao hệ thống không phát hiện sớm hơn.

### 12.1 Truy vết source-to-sink

1. Xác định input đầu tiên và ranh giới tin cậy.
2. Theo dõi mọi bước parse, decode, normalize, concatenate và serialize.
3. Ghi lại ngữ cảnh cuối cùng mà browser diễn giải dữ liệu.
4. Xác định encoding hoặc sanitizer đã chạy ở đâu và có đúng ngữ cảnh hay không.
5. Kiểm tra đường render phụ như admin view, mobile webview, email preview và export.
6. Đối chiếu code đang chạy với commit và asset mà người dùng thực sự tải.

### 12.2 Các nguyên nhân thường gặp

| Nguyên nhân | Dấu hiệu | Hướng khắc phục |
| --- | --- | --- |
| Output không được encode | Template chèn trực tiếp input vào HTML | Dùng auto-escaping và encoding đúng context |
| Encode sai context | HTML escaping được dùng trong JavaScript hoặc URL context | Chuyển dữ liệu qua API an toàn; encode theo đúng context |
| Dùng DOM sink nguy hiểm | **innerHTML**, **document.write**, **eval** nhận dữ liệu không tin cậy | Dùng **textContent**, DOM API an toàn hoặc sanitizer có policy |
| Sanitizer cấu hình rộng | Cho phép event handler, URL scheme hoặc tag không cần thiết | Dùng allowlist tối thiểu và cập nhật sanitizer |
| Nhiều nơi render cùng dữ liệu | Trang người dùng đã sửa nhưng admin view vẫn lỗi | Kiểm kê tất cả consumer và tái kiểm thử |
| Decode hoặc double-encode không nhất quán | Một layer decode sau khi layer khác đã sanitize | Chuẩn hóa data flow và chỉ xử lý tại ranh giới phù hợp |
| Thư viện hoặc component cũ | Component tự tạo HTML hoặc dùng API deprecated | Nâng cấp, thay thế và thêm regression |
| CSP yếu hoặc không có | Script inline hoặc eval vẫn được phép | Triển khai CSP nonce/hash và loại bỏ unsafe directive |
| Thiếu kiểm soát khi tích hợp | Dữ liệu từ hệ thống ngoài được coi là đáng tin | Đặt lại trust boundary và validate/encode tại nơi sử dụng |

### 12.3 Xác định phạm vi sửa

Không dừng ở dòng code được báo cáo. Tìm các call site dùng chung helper, component, template hoặc sanitizer. Một helper unsafe có thể tạo ra nhiều lỗ hổng cùng lúc; ngược lại, một lỗi riêng lẻ có thể có nhiều consumer. Mỗi finding cần gắn với source, sink, context và test case tương ứng.

## 13. Khắc phục XSS đúng cách

### 13.1 Ưu tiên hiển thị text bằng API an toàn

Khi nghiệp vụ chỉ cần hiển thị văn bản, không parse dữ liệu thành HTML.

~~~javascript
// Không an toàn: browser phân tích chuỗi thành markup.
messageContainer.innerHTML = userSuppliedMessage;

// An toàn hơn cho nội dung text thuần.
messageContainer.textContent = userSuppliedMessage;
~~~

**textContent** khiến browser hiển thị ký tự như văn bản. Cách này đơn giản hơn việc cố gắng loại bỏ các chuỗi có vẻ nguy hiểm.

### 13.2 Encode theo đúng output context

HTML text, HTML attribute, JavaScript, URL và CSS có quy tắc diễn giải khác nhau. Một hàm escape tổng quát không thể thay thế mọi loại encoding.

- Trong HTML text node, dùng template engine có auto-escaping hoặc HTML text encoding.
- Trong HTML attribute, đặt giá trị vào attribute được quote và dùng cơ chế encoding phù hợp.
- Trong JavaScript, tránh nối input vào source code; truyền dữ liệu qua JSON serialization hoặc DOM API.
- Trong URL, parse URL và allowlist scheme/host cần thiết; không chỉ encode chuỗi rồi tin rằng URL an toàn.
- Trong CSS, tránh chèn input vào stylesheet hoặc style expression; dùng class và giá trị enum đã kiểm soát.

Không dùng output encoding để biến HTML rich text thành an toàn. Nếu phải hỗ trợ markup, dùng sanitizer có allowlist được review.

### 13.3 Sanitize HTML khi nghiệp vụ thật sự cần rich text

Chỉ cho phép các tag, attribute và URL scheme mà sản phẩm cần. Ví dụ dưới đây minh họa cách dùng DOMPurify với profile HTML cơ bản:

~~~javascript
import DOMPurify from "dompurify";

function renderRichText(container, untrustedHtml) {
  const cleanHtml = DOMPurify.sanitize(untrustedHtml, {
    USE_PROFILES: { html: true }
  });

  container.innerHTML = cleanHtml;
}
~~~

Đây là ví dụ nền tảng, không phải cấu hình dùng được cho mọi sản phẩm. Trước khi áp dụng, hãy:

- Xác định tag, attribute và protocol thật sự cần.
- Không bật SVG, MathML hoặc custom element nếu không có nhu cầu đã đánh giá.
- Kiểm tra URL trong **href** và **src**, đặc biệt scheme và destination.
- Cập nhật sanitizer khi có bản vá bảo mật.
- Kiểm thử HTML malformed, nested element và mutation XSS trên browser mục tiêu.
- Dùng cùng một policy cho mọi nơi render nội dung đó.

Không sanitize bằng regex hoặc danh sách chuỗi thủ công. HTML là một ngôn ngữ có parser và quy tắc phục hồi markup phức tạp; regex đơn giản không mô hình hóa đầy đủ cách browser tạo DOM.

### 13.4 Dùng Trusted Types để kiểm soát DOM sink

Trusted Types giúp browser áp dụng policy cho một số sink nhận chuỗi có thể dẫn tới XSS. Nó không tự sanitize dữ liệu. Ứng dụng cần tạo policy có logic an toàn và giới hạn nơi được phép tạo **TrustedHTML**, **TrustedScript** hoặc **TrustedScriptURL**.

Ví dụ policy chỉ dành cho rich text đã qua sanitizer:

~~~javascript
const richTextPolicy = trustedTypes.createPolicy("app-rich-text", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      USE_PROFILES: { html: true }
    });
  }
});

container.innerHTML = richTextPolicy.createHTML(untrustedHtml);
~~~

Policy phải có tên được cho phép trong CSP **trusted-types**. Tránh tạo policy tổng quát trả nguyên input hoặc cấp quyền tạo Trusted Type cho mọi module. Nên bắt đầu bằng chế độ kiểm kê sink, sửa dần call site và sau đó enforce.

Ví dụ header khi ứng dụng đã sẵn sàng:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-rich-text
~~~

Kiểm tra browser support và hành vi fallback trước khi bật trên toàn bộ người dùng. Nếu policy không được hỗ trợ ở một browser mục tiêu, ứng dụng vẫn phải có output handling an toàn độc lập.

### 13.5 Tăng cường CSP

CSP là lớp phòng thủ bổ sung giúp giới hạn nguồn script và giảm khả năng thực thi khi có lỗi injection. Một policy mẫu có nonce:

~~~http
Content-Security-Policy: default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; script-src 'nonce-{RANDOM_PER_RESPONSE}' 'strict-dynamic'; require-trusted-types-for 'script'; trusted-types app-rich-text
~~~

Giá trị **{RANDOM_PER_RESPONSE}** phải được tạo ngẫu nhiên đủ mạnh cho từng response HTML và phải khớp với nonce trên script hợp lệ. Ví dụ trên cần được điều chỉnh theo kiến trúc, browser support, script loader và các nguồn tài nguyên thực tế của ứng dụng.

Khi triển khai:

- Loại bỏ **unsafe-inline** và **unsafe-eval** khi có thể.
- Dùng nonce hoặc hash cho script hợp lệ.
- Đặt **object-src 'none'** và **base-uri 'none'** nếu tương thích.
- Dùng **frame-ancestors** để kiểm soát embedding theo threat model.
- Bắt đầu bằng **Content-Security-Policy-Report-Only** khi cần đo compatibility, sau đó chuyển sang enforce theo kế hoạch.
- Cấu hình endpoint report có kiểm soát origin, rate limit và chống spam phù hợp; tránh log dữ liệu nhạy cảm.
- Theo dõi lỗi chức năng sau khi enforce, không chỉ đếm số violation.

CSP không thay thế output encoding, sanitization hoặc authorization. Nếu attacker có thể thực thi script qua một nguồn được allowlist, policy rộng hoặc nonce bị lộ, XSS vẫn có thể xảy ra.

### 13.6 Kiểm tra URL và dữ liệu từ message

Với URL do người dùng cung cấp, parse bằng URL API và kiểm tra scheme/host theo allowlist:

~~~javascript
function getAllowedLink(rawValue) {
  let parsed;
  try {
    parsed = new URL(rawValue, window.location.origin);
  } catch {
    return null;
  }

  if (parsed.protocol !== "https:") {
    return null;
  }

  if (parsed.port !== "" && parsed.port !== "443") {
    return null;
  }

  if (!["docs.example.test", "support.example.test"].includes(parsed.hostname)) {
    return null;
  }

  return parsed.href;
}
~~~

Danh sách host trong ví dụ là dữ liệu minh họa; sản phẩm cần định nghĩa allowlist của chính mình. Nếu chỉ cho phép link nội bộ, hãy giới hạn thêm origin và tránh redirect endpoint có thể chuyển sang host không tin cậy.

Với **postMessage**, luôn kiểm tra **event.origin**, định dạng và schema của **event.data**; chỉ gửi tới target origin cụ thể thay vì wildcard khi có thể. Không đưa message data trực tiếp vào **innerHTML**, **eval** hoặc navigation mà chưa kiểm tra.

## 14. Xử lý dữ liệu đã bị lưu hoặc phân phối

Với stored XSS, sửa code không tự động làm sạch nội dung đã lưu. Lập danh sách record bị ảnh hưởng và mọi bản sao của chúng.

Quy trình đề xuất:

1. Xác định record ID, owner, thời điểm tạo/sửa và nguồn nhập.
2. Bảo toàn bản gốc trong kho bằng chứng có kiểm soát nếu cần điều tra.
3. Xác định policy xử lý: sanitize lại, chuyển thành text, ẩn hoặc xóa theo quy trình dữ liệu.
4. Kiểm tra mọi consumer của record, bao gồm admin, search, export, email preview và API.
5. Làm mới cache, search index, CDN và nội dung đã render sau khi xử lý dữ liệu.
6. Ghi lại record đã xử lý, phiên bản sanitizer/policy và kết quả xác minh.

Không tự động sửa hàng loạt bằng một regex chung. Với nội dung rich text, dùng sanitizer đã review; với dữ liệu không cần markup, chuyển sang text thuần. Kiểm tra thủ công mẫu đại diện và chạy regression trước khi xử lý toàn bộ tập dữ liệu.

## 15. Kiểm thử sau khi sửa

Bản sửa chỉ đạt khi source-to-sink flow đã được xử lý và các luồng hợp lệ vẫn hoạt động. Dùng test case tái hiện incident làm regression bắt buộc.

| Nhóm kiểm thử | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| Reflected | Input xuất hiện trong HTML response | Hiển thị như text hoặc được xử lý đúng context; không thực thi |
| Stored | Nội dung đã lưu được xem bởi user khác | Không thực thi ở mọi màn hình render |
| DOM-based | URL fragment/query đi vào DOM | Không đến unsafe sink; marker không chạy |
| Attribute | Input chứa dấu quote hoặc ký tự điều khiển | Không thoát khỏi attribute context |
| URL | Link có scheme hoặc host ngoài allowlist | Bị từ chối hoặc hiển thị như text |
| Rich text | HTML hợp lệ theo allowlist | Markup cần thiết vẫn hiển thị |
| Rich text | Event handler, script hoặc URL nguy hiểm | Bị loại bỏ theo policy |
| Trusted Types | Code ghi chuỗi trực tiếp vào protected sink | Bị browser chặn trong chế độ enforce |
| CSP | Script ngoài policy | Bị chặn và report theo cấu hình |
| Session | Trang có XSS đã sửa được mở bằng tài khoản test | Không có hành vi trái phép; session flow hợp lệ vẫn hoạt động |
| Admin | Admin view, moderation và preview | Không còn đường render dễ bị khai thác |
| Cache | Trang/asset sau deploy và purge | Browser nhận đúng bản đã sửa |
| Browser | Các browser/version nằm trong support matrix | Kết quả nhất quán theo policy hỗ trợ |

### 15.1 Kiểm thử negative và positive

- Negative test chứng minh dữ liệu độc hại không được diễn giải thành script.
- Positive test chứng minh nội dung hợp lệ vẫn hiển thị và chức năng không bị phá vỡ.
- Test encoding nhiều lần để phát hiện decode không nhất quán.
- Test nội dung malformed và nested markup để đánh giá parser/sanitizer.
- Test đường render phụ và quyền khác nhau, không chỉ route đầu tiên được báo cáo.

Không chỉ assert rằng một chuỗi không xuất hiện trong HTML. Hãy kiểm tra DOM cuối cùng, browser console, request thực tế và hành vi marker trong lab.

### 15.2 Kiểm tra deploy và cache

Sau khi deploy:

- Xác minh release ID và bundle hash được phục vụ ở edge.
- Kiểm tra CDN, reverse proxy và application cache.
- Kiểm tra service worker có giữ bundle cũ hay không; xác minh quy trình update và client đang hoạt động.
- Mở trang trong profile sạch và một profile đã dùng trước đó để phát hiện cache cũ.
- Kiểm tra CSP header trên response thực tế của từng route, kể cả error page và redirect.

## 16. Phục hồi dịch vụ có giám sát

Chỉ khôi phục chức năng đã bị tắt khi đáp ứng tiêu chí đã thống nhất:

- Nguyên nhân gốc đã được xác định và bản sửa đã được review.
- Regression tái hiện incident đã PASS.
- Các đường render dùng chung đã được kiểm tra.
- Dữ liệu stored bị ảnh hưởng đã được xử lý hoặc có biện pháp kiểm soát rõ ràng.
- Cache và asset cũ đã được xử lý.
- CSP/Trusted Types policy có hiệu lực đúng trên response thực tế.
- Credential/session đã được revoke hoặc rotate khi đánh giá tác động yêu cầu.
- Monitoring và người chịu trách nhiệm theo dõi sau deploy đã sẵn sàng.

Khôi phục theo giai đoạn nếu thay đổi ảnh hưởng nhiều người dùng. Theo dõi error rate, CSP violation, JavaScript exception, tỷ lệ đăng nhập, luồng nghiệp vụ và báo cáo hỗ trợ. Nếu xuất hiện regression hoặc dấu hiệu khai thác mới, quay lại containment và cập nhật incident timeline.

## 17. Giám sát sau incident

Theo dõi cả tín hiệu bảo mật và sức khỏe ứng dụng:

| Tín hiệu | Cách diễn giải |
| --- | --- |
| CSP violation theo route/directive | Phát hiện script hoặc resource ngoài policy; cần phân loại false positive và nguồn hợp lệ |
| Request bất thường sau khi xem route | Có thể là dấu hiệu hành động cùng origin; cần correlation và kiểm tra nghiệp vụ |
| Tỷ lệ lỗi JavaScript tăng | Có thể policy hoặc bản sửa làm hỏng chức năng |
| Nhiều tài khoản xem cùng record đáng ngờ | Hữu ích để đánh giá phạm vi stored XSS |
| Bundle version không đồng nhất | Có thể còn client đang chạy asset cũ |
| Session revoke hoặc re-auth bất thường | Theo dõi tác động của containment và dấu hiệu account compromise |
| User report tiếp diễn | Có thể còn cache, consumer hoặc dữ liệu chưa được xử lý |

### 17.1 Mẫu event bảo mật đã giảm dữ liệu

~~~json
{
  "event": "xss_signal",
  "timestamp": "2026-11-22T03:10:00Z",
  "service": "web-app",
  "route_template": "/content/:contentId",
  "release_id": "release-2026.11.22.3",
  "signal_type": "csp_violation",
  "directive": "script-src",
  "source_file": "/assets/app.js",
  "request_id": "req-redacted-123",
  "user_ref": "pseudonymous-user-ref",
  "confidence": "possible"
}
~~~

Schema trên chỉ là ví dụ. Không đưa raw URL query, cookie, token, nội dung form hoặc DOM chứa dữ liệu người dùng vào telemetry. Dùng route template, pseudonymous identifier và request ID đã được kiểm soát để liên kết sự kiện.

### 17.2 Tương quan sự kiện

Khi điều tra, ghép CSP report với request log, release ID, route, browser và audit event theo timestamp/request ID. Xác định sai lệch clock giữa browser, edge và server. Tránh kết luận dựa trên IP đơn lẻ vì IP có thể dùng chung hoặc thay đổi.

## 18. Giao tiếp và điều phối

Incident owner chịu trách nhiệm giữ timeline và quyết định mức độ. Các nhóm thường tham gia:

- **Security:** phân loại, threat model, phạm vi, bằng chứng và tiêu chí đóng incident.
- **Application/frontend:** truy vết source-to-sink, sửa component/template và cung cấp build.
- **Platform/operations:** containment ở edge, cache, deploy, CSP header và log retention.
- **QA:** regression, browser matrix và kiểm tra chức năng.
- **Identity/support:** revoke session/token, đánh giá tài khoản và hỗ trợ người dùng bị ảnh hưởng.
- **Product/legal/privacy:** đánh giá tác động khách hàng, thông báo và nghĩa vụ theo quy trình tổ chức.

Mỗi cập nhật nên nêu sự kiện đã xác minh, điều chưa biết, phạm vi hiện tại, hành động đang thực hiện và người phụ trách tiếp theo. Không chia sẻ payload có thể thực thi hoặc credential trong kênh giao tiếp rộng.

## 19. Báo cáo sau sự cố

Post-incident review tập trung vào cách hệ thống và quy trình đã hoạt động. Báo cáo nên có:

1. Tóm tắt sự cố và tác động đã xác nhận.
2. Timeline từ tín hiệu đầu tiên đến khi phục hồi.
3. Root cause: source, transformation, sink và kiểm soát bị thiếu.
4. Phạm vi người dùng, dữ liệu, route, browser và phiên bản bị ảnh hưởng.
5. Biện pháp containment, remediation và credential action.
6. Kết quả regression và bằng chứng phục hồi.
7. Các điểm phát hiện chậm, log thiếu hoặc quy trình gây khó khăn.
8. Action item có owner, deadline và tiêu chí hoàn thành.

Tránh báo cáo chỉ ghi “đã escape input” hoặc “đã bật CSP”. Hãy chỉ rõ context nào được sửa, call site nào được kiểm tra, test nào chứng minh bản sửa và dữ liệu nào đã được xử lý.

## 20. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách tránh |
| --- | --- | --- |
| Coi CSP report là bằng chứng khai thác | Phân loại sai mức độ | Correlate với browser, server và hành vi thực tế |
| Chỉ tìm chuỗi **&lt;script&gt;** | Bỏ sót event handler, URL, DOM sink và template | Truy vết source-to-sink theo context |
| Chỉ sửa một trang | Stored XSS vẫn tồn tại ở admin hoặc preview | Kiểm kê mọi consumer của dữ liệu |
| Dùng regex để sanitize HTML | Bỏ sót parser behavior và mutation XSS | Dùng sanitizer chuyên dụng với allowlist |
| Chỉ bật HttpOnly | XSS vẫn có thể thực hiện request bằng session | Sửa XSS và đánh giá hành động cùng origin |
| Chỉ dựa vào WAF | Payload biến thể có thể đi qua | Sửa code tại source/sink |
| Deploy nhưng không purge cache | Client tiếp tục tải nội dung hoặc bundle cũ | Kiểm tra CDN, cache và service worker |
| Gửi HAR/trace nguyên bản vào ticket | Làm lộ cookie hoặc dữ liệu cá nhân | Redact và lưu bằng chứng trong kho có kiểm soát |
| Đóng incident ngay sau hotfix | Có thể còn record, route hoặc credential bị ảnh hưởng | Chỉ đóng khi đạt tiêu chí phục hồi và theo dõi |

## 21. Checklist xử lý XSS incident

### Tiếp nhận và xác minh

- [ ] Có incident ID, owner và timestamp UTC.
- [ ] Đã ghi route, release ID, browser/version và nguồn phát hiện.
- [ ] Đã phân biệt cảnh báo với bằng chứng thực thi.
- [ ] Việc tái hiện dùng staging, dữ liệu giả và tài khoản test.
- [ ] Không mở payload đáng ngờ trong session production.

### Phạm vi và bằng chứng

- [ ] Đã xác định source, transformation, sink và output context.
- [ ] Đã phân loại reflected, stored, DOM-based hoặc dạng phù hợp.
- [ ] Đã kiểm tra route, component, admin view và consumer liên quan.
- [ ] Đã đánh giá người dùng, quyền, dữ liệu và hành động có thể bị ảnh hưởng.
- [ ] Log, screenshot, HAR/trace và DOM snapshot đã được redact.
- [ ] Timeline và thay đổi containment có request/change ID.

### Containment và remediation

- [ ] Đã giảm bề mặt khai thác bằng biện pháp phù hợp.
- [ ] Đã đánh giá session/token và quyết định revoke có căn cứ.
- [ ] Đã sửa nguyên nhân bằng API an toàn, encoding đúng context hoặc sanitizer phù hợp.
- [ ] Trusted Types/CSP được cấu hình và kiểm thử theo support matrix.
- [ ] Không dùng regex hoặc blocklist làm biện pháp sửa cuối.
- [ ] Stored content, cache, search index và asset cũ đã được xử lý.

### Phục hồi và theo dõi

- [ ] Regression tái hiện incident đã PASS.
- [ ] Positive test xác nhận nội dung hợp lệ vẫn hoạt động.
- [ ] Browser, route và quyền liên quan đã được kiểm tra.
- [ ] Response header và bundle thực tế sau deploy đã được xác minh.
- [ ] Monitoring và người trực theo dõi sau phục hồi đã được xác định.
- [ ] Báo cáo sau sự cố có action item, owner và deadline.

## 22. Câu hỏi tự kiểm tra

1. Vì sao một CSP violation chưa đủ để kết luận đã xảy ra XSS?
2. Reflected, stored và DOM-based XSS khác nhau ở nguồn dữ liệu và đường thực thi như thế nào?
3. Vì sao XSS có thể thực hiện hành động bằng session dù cookie có HttpOnly?
4. Khi điều tra stored XSS, vì sao cần kiểm tra admin view, search index và email preview?
5. Những bằng chứng nào có thể chứa credential dù chúng trông như file debug thông thường?
6. Vì sao nên xác minh trong staging bằng marker vô hại?
7. Khi nào cần revoke session hoặc token sau một XSS incident?
8. Vì sao WAF rule không thay thế việc sửa source-to-sink flow?
9. Khi nào dùng textContent, khi nào cần sanitizer?
10. Trusted Types kiểm soát điều gì và vì sao nó không tự sanitize dữ liệu?
11. CSP nonce cần được tạo và gắn vào response như thế nào?
12. Vì sao sửa code chưa đủ nếu dữ liệu stored hoặc bundle cũ vẫn được phân phối?
13. Những tiêu chí nào phải đạt trước khi khôi phục chức năng?
14. Làm thế nào để theo dõi sự cố sau deploy mà không ghi raw cookie hoặc token vào log?

## 23. Tổng kết

XSS incident là sự cố tại ranh giới giữa dữ liệu không tin cậy và cách browser diễn giải nội dung trong origin của ứng dụng. Quy trình xử lý cần đi từ tín hiệu đến xác minh, phân loại, đánh giá phạm vi, containment, sửa nguyên nhân và phục hồi có giám sát. Reflected, stored và DOM-based XSS có đường đi khác nhau nên cần điều tra source-to-sink cụ thể.

Trong quá trình xử lý, bảo toàn bằng chứng nhưng phải redact credential và dữ liệu cá nhân. Đánh giá cả khả năng đọc dữ liệu lẫn khả năng thực hiện hành động cùng origin; HttpOnly giảm khả năng đọc cookie nhưng không vô hiệu hóa XSS. Sửa lỗi bằng API DOM an toàn, output encoding đúng context hoặc sanitizer có allowlist; dùng Trusted Types và CSP như lớp phòng thủ bổ sung. Với stored XSS, xử lý cả record và bản sao trong cache, search index hoặc các consumer khác.

Chỉ phục hồi khi regression chứng minh đường khai thác đã bị chặn, chức năng hợp lệ vẫn hoạt động, dữ liệu bị ảnh hưởng đã được xử lý và monitoring đã sẵn sàng. Post-incident review cần chuyển nguyên nhân và khoảng trống phát hiện thành action item có người phụ trách.

## 24. Tài liệu tham khảo

- [OWASP: Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [OWASP: DOM Based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html)
- [OWASP: XSS Filter Evasion Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XSS_Filter_Evasion_Cheat_Sheet.html)
- [OWASP: Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [MDN: Cross-site scripting (XSS)](https://developer.mozilla.org/docs/Web/Security/Attacks/XSS)
- [MDN: Content Security Policy](https://developer.mozilla.org/docs/Web/HTTP/CSP)
- [MDN: Trusted Types API](https://developer.mozilla.org/docs/Web/API/Trusted_Types_API)
- [W3C: Trusted Types](https://www.w3.org/TR/trusted-types/)
- [W3C: Content Security Policy Level 3](https://www.w3.org/TR/CSP3/)
- [DOMPurify](https://github.com/cure53/DOMPurify)
- [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

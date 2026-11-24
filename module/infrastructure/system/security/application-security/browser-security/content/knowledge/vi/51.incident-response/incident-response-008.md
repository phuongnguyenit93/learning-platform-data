# Post-incident review

## Mục tiêu

Post-incident review là buổi đánh giá có cấu trúc sau khi sự cố bảo mật đã được kiểm soát. Nhóm liên quan cùng dựng lại diễn biến, xác định phạm vi ảnh hưởng, phân tích nguyên nhân và chuyển bài học thành thay đổi có thể kiểm chứng. Mục tiêu là cải thiện khả năng phòng vệ và ứng phó của hệ thống, không tìm người để quy trách nhiệm.

Trong bảo mật trình duyệt, một sự cố có thể bắt đầu từ XSS, CSRF, cấu hình CORS sai, lộ cookie hoặc token, clickjacking, cache dùng chung phân phối nhầm dữ liệu, Service Worker bị thay thế hoặc security header bị cấu hình thiếu. Mỗi trường hợp có thể đi qua nhiều thành phần: trình duyệt, origin, ứng dụng web, API, CDN, hệ thống xác thực và hạ tầng vận hành. Review cần nối được các dấu vết này thành một bức tranh thống nhất.

Sau bài này, bạn có thể:

- Chuẩn bị và điều phối buổi post-incident review dựa trên bằng chứng.
- Dựng timeline có mốc thời gian, nguồn và mức độ tin cậy.
- Đánh giá phạm vi ảnh hưởng đến tài khoản, phiên, dữ liệu và trình duyệt.
- Phân tích nguyên nhân gốc cùng các yếu tố góp phần mà không dừng ở lỗi trực tiếp.
- Đánh giá hiệu quả phát hiện, khoanh vùng, loại bỏ nguyên nhân và khôi phục.
- Chuyển phát hiện thành hành động khắc phục có người phụ trách, thời hạn và tiêu chí xác minh.

## 1. Vì sao cần post-incident review

Khi sự cố đã được xử lý, nhóm thường có áp lực quay lại hoạt động bình thường. Nếu chỉ đóng ticket sau khi dịch vụ phục hồi, những điều kiện đã khiến sự cố xảy ra có thể vẫn còn: kiểm tra quyền thiếu ở một endpoint, cookie chưa được xoay vòng, cache chưa được làm sạch, CSP chưa được enforce hoặc telemetry không đủ để phát hiện lần tái diễn.

Post-incident review tạo một vòng phản hồi từ sự cố về thiết kế và vận hành. Kết quả cần trả lời được:

1. Điều gì đã xảy ra và người dùng hoặc dữ liệu nào bị ảnh hưởng?
2. Sự cố bắt đầu từ đâu, diễn biến qua những thành phần nào?
3. Vì sao biện pháp phòng vệ hiện có không ngăn chặn hoặc phát hiện sớm hơn?
4. Nhóm đã phản ứng như thế nào, điều gì hiệu quả và điều gì gây chậm trễ?
5. Những thay đổi nào cần thực hiện để giảm khả năng tái diễn hoặc giảm tác động?
6. Làm thế nào để chứng minh các thay đổi đó hoạt động?

Review nên được tổ chức sau khi đã kiểm soát tình huống khẩn cấp và có đủ dữ liệu ban đầu. Nếu còn rủi ro đang diễn ra, ưu tiên tiếp tục ứng phó; có thể ghi lại câu hỏi cần xem xét sau. Không trì hoãn biện pháp bảo vệ chỉ để chờ buổi review.

## 2. Nguyên tắc thực hiện

### 2.1. Tập trung vào hệ thống và điều kiện làm việc

Một sự cố hiếm khi chỉ do một thao tác cá nhân. Hãy tìm các điều kiện trong thiết kế, quy trình, cấu hình, công cụ và luồng phối hợp đã cho phép lỗi đi đến production hoặc kéo dài ảnh hưởng.

Thay vì ghi “kỹ sư quên bật CSP”, hãy điều tra sâu hơn:

- Quy trình phát hành có kiểm tra security header không?
- CSP có được kiểm thử trên route mới và trên CDN response không?
- Có cơ chế phát hiện header bị mất sau reverse proxy không?
- Tài liệu triển khai có chỉ rõ ai phê duyệt thay đổi policy không?
- Dashboard có cảnh báo khi tỷ lệ vi phạm tăng hoặc header biến mất không?

Mô tả sự kiện cụ thể, tránh phán xét về tính cách hoặc động cơ của người tham gia. Nếu một quyết định đã góp phần tạo ra sự cố, ghi lại bối cảnh, thông tin sẵn có và áp lực vận hành tại thời điểm đó.

### 2.2. Phân biệt sự thật, giả thuyết và điều chưa biết

Mỗi kết luận quan trọng phải có bằng chứng hoặc được ghi rõ là giả thuyết. Ví dụ:

- **Đã xác nhận:** access log cho thấy endpoint hồ sơ trả dữ liệu của tài khoản A sau một request được phục vụ từ cache dùng chung.
- **Giả thuyết:** cache key không phân biệt một header ảnh hưởng đến nội dung.
- **Chưa xác định:** có bao nhiêu client khác nhận bản sao trước khi cache được làm sạch.

Không chuyển giả thuyết thành sự thật chỉ vì nó hợp lý. Ghi rõ nguồn dữ liệu, khoảng thời gian và giới hạn quan sát.

### 2.3. Bảo vệ dữ liệu trong quá trình review

Bằng chứng sự cố có thể chứa cookie, token, URL có mã định danh, thông tin cá nhân, payload hoặc nội dung trang. Chỉ thu thập dữ liệu cần thiết, hạn chế quyền truy cập, che bí mật trong bản báo cáo và tuân thủ thời hạn lưu trữ đã được phê duyệt. Bản HAR, ảnh chụp DevTools và log trình duyệt cần được xử lý như dữ liệu nhạy cảm vì chúng có thể chứa header xác thực hoặc nội dung response.

## 3. Chuẩn bị buổi review

### 3.1. Xác định phạm vi

Bắt đầu bằng mã sự cố, thời gian xảy ra, hệ thống bị ảnh hưởng và trạng thái hiện tại. Xác định rõ review bao gồm frontend, API, CDN, hệ thống xác thực, Service Worker, quy trình phát hành hay tất cả các thành phần liên quan.

Chọn người tham gia theo vai trò cần thiết: incident commander, kỹ sư ứng dụng, nhóm bảo mật, vận hành hạ tầng/CDN, nhóm identity, hỗ trợ khách hàng và người phụ trách quyền riêng tư/pháp lý khi có dữ liệu người dùng bị ảnh hưởng. Không cần mời toàn bộ tổ chức nếu họ không đóng góp vào việc dựng sự kiện hoặc quyết định hành động.

### 3.2. Thu thập nguồn bằng chứng

Các nguồn thường hữu ích với sự cố bảo mật trình duyệt:

| Nguồn | Câu hỏi có thể trả lời | Giới hạn |
|---|---|---|
| Access log/API gateway | Request nào đến endpoint, thời điểm, status, route và request ID | Có thể không lưu đầy đủ body hoặc header; cần biết cấu hình masking |
| Identity provider và auth log | Đăng nhập, refresh, revoke, đổi mật khẩu, MFA và phiên bị thu hồi | Một thiết bị hoặc người dùng có thể có nhiều phiên |
| CDN/reverse proxy | Cache HIT/MISS, Age, cache key, header được chuyển tiếp và thay đổi cấu hình | Header cache có thể khác nhau giữa các tầng |
| WAF và hệ thống phát hiện | Request bị chặn, rule kích hoạt, địa chỉ nguồn và mẫu bất thường | Không phải mọi request độc hại đều bị nhận diện |
| CSP Reporting | Directive vi phạm, route/tài nguyên ở mức trình duyệt báo cáo | Báo cáo có thể bị giả mạo, thiếu hoặc bị trình duyệt gộp |
| Browser telemetry | Sự kiện runtime, lỗi tải tài nguyên, trạng thái phiên do ứng dụng ghi nhận | Client có thể sửa, bỏ hoặc gửi giả dữ liệu |
| Service Worker/Cache Storage | Phiên bản worker, lỗi cập nhật, cache do ứng dụng quản lý | Không phải lúc nào cũng có snapshot hoặc log lịch sử |
| Release/configuration history | Thay đổi code, CSP, cookie, CORS, CDN và feature flag | Cần đối chiếu thời gian triển khai thực tế |
| Ticket và trao đổi ứng phó | Quyết định, thời điểm phát hiện và hành động đã thực hiện | Ghi chú có thể được tạo muộn hoặc thiếu mốc thời gian |

Thu thập bản sao chỉ đọc khi có thể. Giữ nguyên dữ liệu gốc, ghi lại người thu thập, thời điểm, nguồn và thao tác chuyển đổi. Nếu cần trích xuất HAR hoặc log đã lọc, giữ bản gốc theo chính sách evidence handling và ghi rõ quy tắc lọc.

### 3.3. Đánh giá chất lượng dữ liệu

Trước khi dựng timeline, kiểm tra:

- Múi giờ của từng nguồn và sai lệch đồng hồ.
- Log có bị sampling, rotate, mất đoạn hoặc lọc bỏ header không.
- Request ID có được truyền xuyên qua CDN, gateway và API không.
- Thời gian client gửi có đáng tin không; ưu tiên timestamp tiếp nhận do máy chủ ghi nhận khi so sánh.
- Báo cáo CSP hoặc telemetry có thể là request giả mạo hay bị gửi lặp không.
- Có khoảng thời gian mà log không tồn tại hoặc hệ thống giám sát bị gián đoạn không.

Ghi lại khoảng trống dữ liệu thay vì tự nội suy các sự kiện chưa quan sát được.

## 4. Dựng timeline sự cố

Timeline là nền tảng để mọi người cùng hiểu diễn biến. Dùng thời gian chuẩn, thường là UTC trong báo cáo kỹ thuật, và ghi thêm múi giờ nếu cần phục vụ đội địa phương. Mỗi mốc nên có thời điểm, sự kiện, nguồn bằng chứng, mức độ tin cậy và tác động.

| Thời điểm UTC | Sự kiện | Nguồn | Độ tin cậy |
|---|---|---|---|
| 08:12 | Bản phát hành frontend bắt đầu triển khai | Release log | Cao |
| 08:19 | Báo cáo CSP `script-src` tăng trên route hồ sơ | CSP collector | Trung bình |
| 08:24 | Hỗ trợ khách hàng nhận phản ánh nội dung trang bất thường | Support ticket | Cao về thời điểm tiếp nhận |
| 08:31 | Nhóm ứng phó xác nhận một request bất thường trong access log | API gateway | Cao |
| 08:46 | Tắt luồng bị ảnh hưởng bằng feature flag | Change log | Cao |
| 09:05 | Thu hồi phiên nghi bị lộ và bắt đầu làm sạch cache | Identity/CDN log | Cao |
| 09:42 | Kiểm thử xác nhận luồng bị ảnh hưởng đã được chặn | Test record | Cao |

Bảng trên chỉ là ví dụ minh họa. Trong báo cáo thực tế, không điền thời điểm ước đoán như sự thật. Nếu chỉ biết sự kiện xảy ra trong khoảng 08:00–08:30, ghi thành khoảng và giải thích nguồn nào giới hạn được khoảng đó.

Timeline cần phân biệt:

- **Thời điểm bắt đầu kỹ thuật:** lần đầu hành vi sai hoặc truy cập trái phép xuất hiện trong dữ liệu có thể xác minh.
- **Thời điểm phát hiện:** hệ thống hoặc con người nhận ra dấu hiệu.
- **Thời điểm xác nhận:** nhóm có đủ bằng chứng để phân loại sự cố.
- **Thời điểm containment:** hành động đầu tiên làm giảm khả năng tiếp tục gây hại.
- **Thời điểm eradication:** nguyên nhân trực tiếp hoặc đường xâm nhập đã được loại bỏ.
- **Thời điểm recovery:** dịch vụ trở lại hoạt động an toàn.
- **Thời điểm closure:** các tiêu chí đóng sự cố được đáp ứng và phần việc còn lại đã được giao.

Không gộp “đã triển khai bản vá” với “đã khôi phục an toàn”. Sau khi sửa, vẫn cần xác minh cache, phiên, quyền, dữ liệu tồn dư và khả năng tái diễn.

## 5. Xác định phạm vi và tác động

Đánh giá tác động cần dựa trên những gì kẻ tấn công hoặc luồng lỗi có thể thực hiện, những gì log xác nhận đã xảy ra và phần nào chưa thể xác định.

### 5.1. Các chiều tác động

| Chiều đánh giá | Câu hỏi |
|---|---|
| Tính bí mật | Có dữ liệu nào bị đọc, tải xuống, hiển thị cho tài khoản khác hoặc gửi đến origin ngoài dự kiến? |
| Tính toàn vẹn | Có request thay đổi trạng thái, thao tác tài khoản hoặc nội dung nào bị thực hiện trái phép? |
| Tính sẵn sàng | Người dùng có bị chặn đăng nhập, tải trang, dùng API hoặc thực hiện giao dịch không? |
| Tài khoản và phiên | Có cookie, access token, refresh token hoặc session nào bị lộ, sao chép hay sử dụng lại? |
| Phạm vi người dùng | Bao nhiêu tài khoản, phiên, trình duyệt, route hoặc tenant có khả năng bị ảnh hưởng? |
| Phạm vi dữ liệu | Loại dữ liệu, khoảng thời gian, số bản ghi và hệ thống lưu trữ liên quan là gì? |
| Phạm vi hệ thống | Origin, subdomain, API, CDN, Service Worker, ứng dụng nhúng hoặc đối tác nào liên quan? |

Phân biệt rõ:

- **Confirmed impact:** bằng chứng trực tiếp cho thấy dữ liệu hoặc chức năng đã bị ảnh hưởng.
- **Potential exposure:** cấu hình hoặc điều kiện cho phép ảnh hưởng xảy ra, nhưng chưa có bằng chứng xác nhận đã bị khai thác.
- **Unknown:** dữ liệu không đủ để xác định. Nêu rõ vì sao không thể kết luận và hành động nào giảm rủi ro còn lại.

Không khẳng định “không có dữ liệu bị truy cập” chỉ vì không tìm thấy log nếu hệ thống trước đó không ghi nhận loại request cần thiết.

### 5.2. Kiểm tra theo từng nhóm sự cố trình duyệt

**XSS hoặc script không được phép**

- Xác định route, origin, nguồn dữ liệu đầu vào và DOM sink liên quan.
- Đối chiếu CSP violation, Trusted Types violation, access log và bản phát hành.
- Xác định script có thực thi trong origin ứng dụng hay không, dữ liệu nào có thể đọc và thao tác nào có thể được thực hiện.
- Kiểm tra khả năng truy cập DOM, API cùng origin, dữ liệu trang và token có thể đọc được bởi JavaScript. Cookie có cờ HttpOnly không đọc trực tiếp được bằng JavaScript, nhưng XSS vẫn có thể thực hiện request trong ngữ cảnh phiên của người dùng.
- Kiểm tra phạm vi tài khoản, thời gian tồn tại và khả năng payload còn nằm trong nội dung lưu trữ.

**CSRF**

- Xác định request thay đổi trạng thái, phương thức, endpoint và điều kiện cookie được gửi.
- Kiểm tra CSRF token, SameSite, Origin/Referer validation và yêu cầu xác thực lại nếu có.
- Phân biệt request bị gửi với hành động được máy chủ chấp nhận. Access log và audit log cần chứng minh kết quả thay đổi trạng thái.
- Kiểm tra các endpoint thay đổi dữ liệu qua GET hoặc endpoint có cơ chế xác thực thiếu nhất quán.

**Lộ cookie hoặc token**

- Xác định loại credential, thời hạn, phạm vi domain/path, thuộc tính Secure, HttpOnly, SameSite và nơi credential có thể đã xuất hiện.
- Kiểm tra request sử dụng credential trong access log, identity log và hệ thống phát hiện.
- Thu hồi phiên, refresh token hoặc credential bị ảnh hưởng; xác minh token cũ không còn được chấp nhận.
- Kiểm tra log, URL, analytics, error reporting, browser storage và hệ thống hỗ trợ có lưu credential hay không.

**CORS hoặc ranh giới origin sai**

- Xác định origin gửi request, endpoint nhận, header CORS trả về và dữ liệu mà JavaScript origin khác có thể đọc.
- Kiểm tra `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Vary: Origin` và preflight nếu có.
- Phân biệt việc trình duyệt cho phép gửi request với việc JavaScript được phép đọc response.
- Xác minh dữ liệu thực tế bị đọc và tài khoản/phiên nào có thể bị ảnh hưởng.

**Clickjacking**

- Xác định trang có thể bị nhúng trong frame, header `frame-ancestors` hoặc `X-Frame-Options`, và luồng thao tác nhạy cảm.
- Kiểm tra có hành động nào được xác nhận mà người dùng không chủ ý thực hiện không.
- Đánh giá các bước xác nhận, re-authentication và kiểm tra giao dịch ở máy chủ.

**Cache hoặc Service Worker**

- Kiểm tra cache HTTP riêng tư, shared cache, Cache API và bfcache như các cơ chế khác nhau.
- Đối chiếu `Cache-Control`, `Vary`, `ETag`, `Age`, trạng thái CDN và nội dung phản hồi.
- Kiểm tra việc đổi tài khoản, đăng xuất, thu hồi quyền, cập nhật Service Worker và xóa cache.
- Xác định dữ liệu nào có thể được tái sử dụng bởi người dùng khác hoặc phiên không còn hợp lệ.

## 6. Phân tích nguyên nhân

Một review tốt phân biệt nguyên nhân trực tiếp, yếu tố góp phần và điểm kiểm soát đã thất bại. Không dừng ở câu “đã có lỗ hổng XSS” hoặc “cookie bị đánh cắp”; đó là mô tả dạng sự cố, chưa giải thích vì sao hệ thống cho phép nó xảy ra và kéo dài.

Có thể dùng phương pháp 5 Whys như công cụ đặt câu hỏi, nhưng không ép mọi sự cố thành một chuỗi tuyến tính. Nhiều sự cố có nhiều nhánh nguyên nhân.

Ví dụ minh họa cho sự cố lộ dữ liệu do XSS:

| Lớp | Phát hiện |
|---|---|
| Sự kiện trực tiếp | Một chuỗi do người dùng kiểm soát được đưa vào DOM bằng sink diễn giải HTML |
| Vì sao dữ liệu đến được sink? | Route mới dùng cách render khác với các route cũ và thiếu bước xử lý đầu ra theo ngữ cảnh |
| Vì sao lỗi không bị phát hiện? | Kiểm thử chỉ bao phủ luồng nhập liệu chính, chưa có ca kiểm thử DOM XSS cho route mới |
| Vì sao CSP không giảm tác động? | Policy còn cho phép một nguồn script rộng và chưa enforce trên toàn bộ route |
| Vì sao phản ứng chậm? | CSP report và telemetry không được nhóm theo route/version; dashboard thiếu cảnh báo hồi quy |
| Yếu tố góp phần | Trang lỗi có một đường render nội dung do người dùng kiểm soát riêng, chưa được bao phủ bởi kiểm thử DOM XSS và rà soát CSP |

Từ ví dụ này, hành động khắc phục có thể bao gồm sửa sink và encode theo ngữ cảnh, bổ sung test hồi quy, thu hẹp CSP và triển khai enforce theo giai đoạn, thêm cảnh báo theo route/version, cùng kiểm tra cache sau deploy.

### 6.1. Phân biệt nguyên nhân gốc và yếu tố góp phần

- **Nguyên nhân gốc:** điều kiện hệ thống nếu được loại bỏ hoặc kiểm soát sẽ ngăn sự cố cụ thể xảy ra theo đường đã quan sát.
- **Yếu tố góp phần:** làm tăng xác suất, phạm vi hoặc thời gian tồn tại của sự cố.
- **Điểm kiểm soát thất bại:** biện pháp dự kiến phát hiện hoặc ngăn sự cố nhưng không hoạt động, không bao phủ hoặc không được giám sát.
- **Khoảng trống bằng chứng:** điều cần biết nhưng log hoặc telemetry hiện tại không đủ để trả lời.

Một sự cố có thể có nhiều nguyên nhân gốc. Ví dụ, lỗ hổng render dữ liệu là nguyên nhân cho XSS; policy CSP rộng và thiếu test hồi quy là các yếu tố góp phần; telemetry không đầy đủ là khoảng trống phát hiện.

### 6.2. Đánh giá cả cơ chế kỹ thuật và quy trình

Kiểm tra các lớp sau:

- **Thiết kế:** ranh giới origin, trust boundary, mô hình phiên, quyền truy cập và cách xử lý dữ liệu.
- **Triển khai:** output encoding, Trusted Types, CSRF protection, CORS allowlist, CSP và security headers.
- **Hạ tầng:** CDN cache key, reverse proxy, TLS, header forwarding, WAF và cấu hình subdomain.
- **Kiểm thử:** unit/integration/browser tests, test chuyển tài khoản, test thu hồi phiên và test cross-origin.
- **Phát hành:** review thay đổi policy, canary, feature flag, rollback và đồng bộ cache.
- **Giám sát:** CSP reports, auth events, client telemetry, access logs, alert và khả năng truy vết xuyên dịch vụ.
- **Ứng phó:** quyền truy cập công cụ, runbook, người quyết định, phối hợp giữa nhóm và khả năng thu hồi credential.

## 7. Đánh giá quá trình ứng phó

Post-incident review cần đánh giá quyết định và kết quả trong từng giai đoạn. Mục tiêu là nhận biết điểm nào giúp giảm tác động và điểm nào cần cải thiện.

| Giai đoạn | Câu hỏi đánh giá |
|---|---|
| Detection | Tín hiệu đầu tiên là gì? Mất bao lâu để nhận biết? Có cảnh báo nào bị bỏ qua hoặc quá nhiễu? |
| Triage | Nhóm phân loại mức độ nghiêm trọng và phạm vi như thế nào? Có giả định nào khiến điều tra đi sai hướng? |
| Containment | Biện pháp nào ngăn tác động tiếp tục? Có làm gián đoạn người dùng hợp lệ không? |
| Eradication | Nguyên nhân trực tiếp, credential, script, cấu hình hoặc cache bị ảnh hưởng đã được loại bỏ chưa? |
| Recovery | Hệ thống được khôi phục dựa trên tiêu chí nào? Có kiểm tra phiên, quyền, cache và security headers sau khôi phục không? |
| Communication | Người dùng, hỗ trợ, vận hành, quản lý và bên liên quan có nhận thông tin đúng lúc không? |
| Follow-up | Ai sở hữu các hành động còn lại? Có thời hạn và tiêu chí xác minh không? |

Đánh giá thời gian theo mốc thực tế:

- **Time to detect (TTD):** thời gian từ mốc bắt đầu có thể xác minh đến khi sự cố được phát hiện.
- **Time to acknowledge:** thời gian từ cảnh báo đến khi có người nhận xử lý.
- **Time to contain:** thời gian từ khi phát hiện đến khi giảm được tác động đang diễn ra.
- **Time to recover:** thời gian đến khi dịch vụ trở lại trạng thái vận hành an toàn.

Các chỉ số này chỉ hữu ích khi định nghĩa mốc bắt đầu nhất quán và dữ liệu có chất lượng. Nếu thời điểm bắt đầu chưa biết, hãy báo cáo giới hạn thay vì tạo ra con số chính xác giả tạo.

## 8. Chuyển bài học thành hành động khắc phục

Mỗi phát hiện cần dẫn đến hành động có thể thực hiện và xác minh. Tránh các mục chung chung như “tăng cường bảo mật”, “nâng cao nhận thức” hoặc “cải thiện monitoring” mà không có kết quả mong đợi.

Một action item tốt cần có:

| Trường | Nội dung |
|---|---|
| ID | Mã duy nhất của hành động |
| Finding | Phát hiện hoặc nguyên nhân liên quan |
| Action | Thay đổi cụ thể cần thực hiện |
| Owner | Một vai trò hoặc nhóm chịu trách nhiệm chính |
| Due date | Ngày hoàn thành dự kiến |
| Priority | Mức ưu tiên dựa trên rủi ro và phạm vi |
| Dependency | Hệ thống, nhóm hoặc quyết định cần có |
| Acceptance criteria | Điều kiện có thể kiểm chứng để đóng |
| Evidence | Test result, log, cấu hình hoặc link PR chứng minh hoàn thành |
| Status | Open, In progress, Blocked, Done hoặc Risk accepted |

Ví dụ:

| Phát hiện | Hành động | Tiêu chí nghiệm thu |
|---|---|---|
| Trang hồ sơ có nguy cơ bị lưu ở shared cache | Đặt chính sách cache phù hợp cho response cá nhân và cập nhật rule CDN | Kiểm thử hai tài khoản cùng URL; không có phản hồi của A được trả cho B; header và trạng thái CDN đúng |
| CSP chưa enforce trên một nhóm route | Thu hẹp allowlist, triển khai report-only rồi enforce theo giai đoạn | Test browser xác nhận script ngoài policy bị chặn; script hợp lệ hoạt động; báo cáo được nhận |
| Phiên cũ còn hiệu lực sau khi thu hồi | Cập nhật quy trình revoke session/refresh token và kiểm tra phía API | Credential đã thu hồi bị từ chối ở các endpoint được bảo vệ |
| Telemetry không phân biệt bản phát hành | Bổ sung app version và route ID đã chuẩn hóa | Dashboard phân nhóm đúng theo version/route và alert có thể tái hiện |
| Kiểm thử CSRF chưa bao phủ endpoint mới | Bổ sung browser integration test cho request thay đổi trạng thái | Test xác nhận request thiếu token hoặc sai origin bị từ chối theo thiết kế |

Ưu tiên dựa trên mức độ nghiêm trọng, khả năng tái diễn, số người dùng bị ảnh hưởng, độ khó khai thác và mức độ bất định còn lại. Hành động giảm thiểu ngay và hành động phòng ngừa dài hạn có thể khác nhau; ghi rõ quan hệ giữa chúng.

Không đóng action item chỉ vì đã merge code. Tiêu chí nghiệm thu cần chứng minh hành vi thực tế đã thay đổi trong môi trường phù hợp.

## 9. Xác minh sau khắc phục

Mỗi hành động cần có phương pháp kiểm chứng trước khi đóng. Với thay đổi bảo mật trình duyệt, kiểm tra cả cấu hình và hành vi của trình duyệt.

| Nhóm thay đổi | Cách xác minh |
|---|---|
| CSP và Trusted Types | Kiểm tra response header thực tế trên các route; thử hành vi hợp lệ và vi phạm trên trình duyệt hỗ trợ |
| Cookie/session | Kiểm tra thuộc tính cookie, rotation, logout, revoke và truy cập API bằng credential cũ |
| CSRF | Thử request hợp lệ, thiếu token, token sai và nguồn gửi không hợp lệ |
| CORS | Thử origin được phép và không được phép; xác nhận browser có thể đọc response chỉ trong trường hợp được thiết kế |
| Clickjacking | Thử nhúng route nhạy cảm trong frame từ origin khác và kiểm tra header bảo vệ |
| Cache | Thử cùng URL với hai tài khoản, sau đăng xuất, sau thu hồi quyền và sau cập nhật cache |
| Service Worker | Kiểm tra cập nhật worker, cache version, luồng offline và hành vi khi đổi tài khoản |
| Telemetry | Tạo sự kiện thử nghiệm, xác nhận collector nhận đúng schema và dashboard hiển thị đúng nhóm |

Cần có test hồi quy tự động cho hành vi có thể tái hiện ổn định và kiểm thử thủ công cho các điều kiện phụ thuộc trình duyệt hoặc hạ tầng. Ghi lại phiên bản trình duyệt, môi trường, thời gian và bằng chứng. Nếu chỉ kiểm thử trên staging, xác định bước kiểm soát khi triển khai production.

## 10. Báo cáo post-incident review

Báo cáo nên ngắn gọn ở phần điều hành nhưng có đủ chi tiết kỹ thuật để nhóm khác hiểu và kiểm chứng. Có thể dùng cấu trúc sau:

### 10.1. Thông tin chung

- Incident ID:
- Tiêu đề:
- Ngày xảy ra:
- Thời gian bắt đầu/kết thúc (UTC):
- Hệ thống và origin bị ảnh hưởng:
- Incident commander:
- Nhóm tham gia:
- Trạng thái hiện tại:

### 10.2. Tóm tắt điều hành

Mô tả ngắn sự cố, tác động đã xác nhận, biện pháp containment chính và trạng thái phục hồi. Nêu rõ phần nào còn chưa xác định.

### 10.3. Tác động

- Người dùng/tài khoản/tenant bị ảnh hưởng:
- Loại dữ liệu hoặc chức năng bị ảnh hưởng:
- Tác động đến tính bí mật, toàn vẹn và sẵn sàng:
- Khoảng thời gian phơi nhiễm:
- Confirmed impact:
- Potential exposure:
- Unknown và giới hạn dữ liệu:

### 10.4. Timeline

Liệt kê mốc thời gian UTC, sự kiện, nguồn bằng chứng và mức độ tin cậy. Đánh dấu rõ mốc ước lượng.

### 10.5. Nguyên nhân và yếu tố góp phần

Mô tả đường diễn biến kỹ thuật, nguyên nhân trực tiếp, nguyên nhân gốc, điểm kiểm soát thất bại và khoảng trống quan sát. Gắn từng kết luận với bằng chứng.

### 10.6. Đánh giá ứng phó

Ghi lại điều gì hoạt động tốt, điều gì làm chậm phản ứng, quyết định quan trọng, trade-off đã chọn và những cải tiến cần thiết trong runbook hoặc phối hợp.

### 10.7. Hành động

| ID | Action | Owner | Due date | Priority | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| SEC-001 |  |  |  |  |  | Open |
| SEC-002 |  |  |  |  |  | Open |

### 10.8. Phê duyệt và theo dõi

Ghi người xác nhận báo cáo, các quyết định chấp nhận rủi ro còn lại, ngày review lại và nơi lưu bằng chứng theo quyền truy cập được kiểm soát.

## 11. Ví dụ: sự cố lộ dữ liệu qua cache trình duyệt và CDN

Một ứng dụng hiển thị thông tin hồ sơ theo URL cố định. Sau một thay đổi cấu hình CDN, response của endpoint cá nhân được cache dùng chung. Người dùng A truy cập trang trước; một request sau đó từ người dùng B nhận lại response đã cache.

Trong ứng phó, nhóm tắt rule cache có vấn đề, làm sạch các object liên quan, kiểm tra access log và thông báo cho các nhóm phụ trách dữ liệu. Post-incident review cần làm rõ:

1. **Timeline:** thay đổi CDN được triển khai khi nào, cache bắt đầu HIT khi nào, request đầu tiên có khả năng phân phối chéo và thời điểm containment.
2. **Phạm vi:** URL/route nào bị ảnh hưởng, object còn trong cache bao lâu, có bao nhiêu request HIT, response có chứa dữ liệu cá nhân nào.
3. **Bằng chứng:** access log, cache status, Age, request ID, response metadata và test tái hiện bằng hai tài khoản.
4. **Nguyên nhân:** tại sao endpoint cá nhân được đưa vào rule cache dùng chung; vì sao cache key và response directive không ngăn được việc này.
5. **Phản ứng:** rule đã được tắt ở tất cả POP chưa, object đã được purge chưa, có cần thu hồi phiên hoặc thực hiện thông báo theo quy định không.
6. **Phòng ngừa:** chính sách `private, no-store` phù hợp cho endpoint, allowlist cache cho tài nguyên công khai, test hai tài khoản trong release pipeline và cảnh báo khi endpoint cá nhân có HIT.

Một lần tái hiện thành công trong staging chứng minh lỗi có thể xảy ra, nhưng không tự chứng minh có bao nhiêu người dùng production đã nhận dữ liệu. Phạm vi thực tế phải dựa vào log và thời gian lưu cache; nếu dữ liệu thiếu, báo cáo cần nêu rõ mức độ bất định.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ ghi lại triệu chứng | Nguyên nhân hệ thống vẫn tồn tại | Dựng đường diễn biến và tìm điểm kiểm soát thất bại |
| Đổ lỗi cho một cá nhân | Mất thông tin về điều kiện thiết kế và quy trình | Dùng ngôn ngữ trung lập, tập trung vào hệ thống |
| Xem CSP report là bằng chứng khai thác thành công | Đánh giá sai mức độ nghiêm trọng | Đối chiếu với log request, auth và tác động thực tế |
| Kết luận không có ảnh hưởng vì log không có dữ liệu | Bỏ sót phạm vi do logging thiếu | Ghi rõ khoảng trống quan sát và phân loại unknown |
| Chỉ sửa code mà không kiểm tra CDN/cache | Response cũ hoặc cấu hình cũ tiếp tục được phục vụ | Kiểm tra toàn bộ đường phân phối và purge có kiểm chứng |
| Đóng việc ngay sau khi deploy | Không biết biện pháp có hiệu quả hay không | Yêu cầu acceptance criteria và bằng chứng test |
| Action item không có owner hoặc hạn | Phát hiện không được xử lý đến cùng | Giao một owner chính, thời hạn và người theo dõi |
| Lưu nguyên HAR/log vào báo cáo phổ biến | Rò rỉ token, cookie hoặc dữ liệu người dùng | Giữ bản gốc có kiểm soát, tạo bản đã lọc cho người đọc |

## 13. Checklist hoàn tất

- [ ] Sự cố đã được containment và trạng thái rủi ro còn lại được ghi nhận.
- [ ] Phạm vi review, người tham gia và nguồn bằng chứng đã xác định.
- [ ] Timeline có múi giờ, nguồn và độ tin cậy cho từng mốc.
- [ ] Tác động đã được phân loại thành confirmed, potential exposure và unknown.
- [ ] Các cơ chế trình duyệt liên quan đã được xem xét: origin, cookie/session, CSP, CORS, CSRF, clickjacking, cache và Service Worker.
- [ ] Nguyên nhân gốc, yếu tố góp phần, điểm kiểm soát thất bại và khoảng trống telemetry đã được phân biệt.
- [ ] Quá trình detection, triage, containment, eradication và recovery đã được đánh giá.
- [ ] Mỗi hành động khắc phục có owner, due date, priority và acceptance criteria.
- [ ] Có test hoặc bằng chứng xác minh hành động đã thay đổi hành vi thực tế.
- [ ] Bằng chứng được bảo vệ, che bí mật và lưu theo chính sách.
- [ ] Rủi ro còn lại có quyết định chấp nhận hoặc kế hoạch xử lý.
- [ ] Có ngày theo dõi để kiểm tra action item và nguy cơ tái diễn.

Post-incident review hoàn tất khi nhóm có một mô tả sự cố dựa trên bằng chứng, hiểu được các điều kiện đã tạo ra và kéo dài tác động, đồng thời chuyển bài học thành những thay đổi có người chịu trách nhiệm và tiêu chí xác minh rõ ràng. Kết quả quan trọng nhất là hệ thống và quy trình ứng phó được cải thiện, để sự cố tương tự khó xảy ra hơn và nếu xảy ra thì được phát hiện, khoanh vùng và khôi phục nhanh hơn.

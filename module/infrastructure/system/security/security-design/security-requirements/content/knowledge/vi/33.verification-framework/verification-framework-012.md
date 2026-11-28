# Yêu cầu data protection

## 1. Bảo vệ dữ liệu là một hợp đồng xuyên suốt vòng đời

Trong chương **Verification framework**, yêu cầu data protection xác định hệ thống phải bảo vệ dữ liệu nào, trước tình huống nào, ở những nơi nào và bằng chứng nào đủ để xác nhận yêu cầu đã được đáp ứng.

Một database được mã hóa chưa chứng minh toàn bộ dữ liệu đã được bảo vệ. Cùng nội dung đó có thể xuất hiện trong cache, search index, queue, file tạm, bản xuất, log, trace, backup hoặc dữ liệu gửi cho một bên xử lý khác. Một bản sao nằm ngoài kiểm soát có thể làm mất giá trị của các kiểm soát tại kho chính.

Mục tiêu của đặc tả là chuyển câu “dữ liệu nhạy cảm phải được bảo vệ” thành chuỗi có thể kiểm chứng:

**Tài sản và mục đích xử lý → rủi ro → yêu cầu cụ thể → điểm thực thi → phép kiểm chứng → bằng chứng → kết luận có phạm vi.**

Sau bài học, người học có thể:

- Lập phạm vi dữ liệu, bản sao và luồng xử lý.
- Phân biệt quyền truy cập, mã hóa, tính toàn vẹn, che dữ liệu và khả năng phục hồi.
- Đặc tả thu thập tối thiểu, phản hồi API, lưu trữ, truyền, logging và export.
- Viết hợp đồng retention, xóa, backup và restore không làm sống lại dữ liệu đã bị loại.
- Thiết kế kiểm thử theo quyền, tenant, trạng thái lỗi và vòng đời dữ liệu.
- Phân biệt thiết kế đã được xem xét với kiểm soát đã được kiểm chứng trên bản triển khai.

Bài sử dụng dịch vụ tài liệu đa tenant làm ví dụ. Các thời hạn, schema, ID và trạng thái là lựa chọn minh họa của dự án, không phải thời hạn pháp lý hoặc baseline bắt buộc cho mọi hệ thống. Chính sách thực tế cần được xác nhận theo loại dữ liệu, cam kết nghiệp vụ, nghĩa vụ áp dụng và kiến trúc.

## 2. Bắt đầu bằng dữ liệu, mục đích và bản sao

### 2.1. Không chỉ phân loại theo tên bảng

Một hồ sơ dữ liệu cần nêu ít nhất:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Nội dung | Dữ liệu nghiệp vụ, định danh, credential, khóa hay metadata nào đang được xử lý? |
| Mục đích | Vì sao cần thu thập, biến đổi, truyền hoặc lưu dữ liệu này? |
| Chủ sở hữu | Role nào chịu trách nhiệm chính sách và vòng đời? |
| Mức nhạy cảm | Tác động nếu bị đọc, sửa, mất hoặc không truy cập được là gì? |
| Chủ thể được truy cập | Người dùng, tenant, workload, quản trị hoặc bên xử lý nào được phép? |
| Vị trí và bản sao | Dữ liệu nằm tại đâu, đi qua những interface nào? |
| Thời hạn | Mốc bắt đầu retention, điều kiện xóa và ngoại lệ được cấp là gì? |
| Kiểm soát | Quyền, profile truyền/lưu, logging, audit và cơ chế xóa nào áp dụng? |
| Bằng chứng | Dữ liệu nào xác nhận các kiểm soát đang có hiệu lực? |

Tên file, tiêu đề tài liệu, nội dung tìm kiếm, định danh tenant hoặc thông tin về ai đã đọc tài liệu cũng có thể nhạy cảm. Không tự coi metadata là công khai.

Dữ liệu dẫn xuất như thumbnail, OCR, chỉ mục tìm kiếm hoặc embedding có thể giữ thông tin từ tài liệu gốc. Cần phân loại theo nội dung và khả năng suy ra dữ liệu, thay vì miễn kiểm soát vì chúng không còn là file ban đầu.

### 2.2. Thu thập ít hơn giúp giảm phạm vi phải bảo vệ

Mỗi field được thu thập nên có mục đích và điều kiện sử dụng. Nếu một chức năng chỉ cần mã trạng thái, không mặc định lưu cả request body để “có thể hữu ích về sau”.

OWASP khuyến nghị xem xét mô hình đe dọa và giảm việc lưu dữ liệu nhạy cảm khi thiết kế bảo vệ dữ liệu lưu trữ. Lớp mã hóa cần được chọn theo loại truy cập mà hệ thống muốn chống lại. [OWASP: Cryptographic Storage](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)

Một yêu cầu tối thiểu hóa có thể kiểm chứng được: endpoint cập nhật thông tin chỉ nhận các field công bố trong hợp đồng, từ chối field ghi ngoài quyền và không lưu giá trị chưa có mục đích được chấp nhận.

Không dùng một mục đích rộng như “analytics” để tự cho phép sao chép mọi dữ liệu sang một kho khác. Luồng mới cần xác định scope, quyền đọc, thời hạn và bằng chứng riêng.

### 2.3. Danh mục bản sao của dịch vụ tài liệu

| Nơi dữ liệu xuất hiện | Ví dụ | Điều cần xác định |
|---|---|---|
| API và bộ nhớ tiến trình | Nội dung upload, object đã deserialize | Giới hạn xử lý, quyền và dữ liệu được xuất |
| Database | Metadata, ownership, trạng thái tài liệu | Quyền field/row, tính toàn vẹn, phiên bản và retention |
| Object storage | Nội dung gốc, phiên bản cũ, file xuất | Policy truy cập, vòng đời object và mọi version |
| Cache | Kết quả đọc, quyết định quyền | Scope tenant/chủ thể, độ mới và invalidation |
| Search index | Nội dung đã tách từ tài liệu | Quyền tìm kiếm, xóa và rebuild |
| Queue và dead-letter queue | Job, payload, thông tin lỗi | Giảm payload, quyền tiêu thụ, retention và replay |
| Tệp tạm | Upload dở, file render, archive | Quyền, bảo vệ volume và dọn khi crash |
| Log, trace và dump | Lỗi, query, telemetry | Danh sách dữ liệu được phép và đường fallback |
| Backup và snapshot | Bản sao phục vụ khôi phục | Quyền, mã hóa, thời hạn và đối soát sau restore |
| Thiết bị người dùng/đích nhận | Download hoặc export đã được cấp | Ranh giới kiểm soát và trách nhiệm bên nhận |

Sơ đồ hoặc inventory cần thể hiện cả các nơi trung gian. Bản sao ngoài phạm vi chưa được kiểm kê phải được ghi như khoảng trống, không được coi là không tồn tại.

## 3. Phân biệt các thuộc tính và cơ chế bảo vệ

### 3.1. Một cơ chế không thay cho mọi yêu cầu

| Cơ chế/thuộc tính | Giúp giải quyết | Không tự chứng minh |
|---|---|---|
| Xác thực | Danh tính caller hoặc workload | Caller được đọc mọi dữ liệu |
| Phân quyền | Quyền với tài nguyên, field, tenant và hành động | Bản sao ở kho khác cũng chịu cùng kiểm soát |
| Mã hóa khi truyền | Bảo vệ đường truyền theo profile và danh tính peer | Endpoint đích có quyền nhận hoặc dùng dữ liệu đúng mục đích |
| Mã hóa khi lưu | Bảo vệ nội dung đối với mô hình truy cập đã chọn | Ứng dụng bị chiếm hoặc người có quyền giải mã không đọc được |
| Kiểm soát toàn vẹn | Phát hiện hoặc ngăn sửa dữ liệu ngoài hợp đồng | Mọi bản cũ hợp lệ đều còn được phép dùng |
| Masking | Giảm dữ liệu được hiển thị cho một đối tượng | Giá trị gốc chưa được gửi trong response hoặc log |
| Pseudonymization/tokenization | Giảm lộ trực tiếp theo thiết kế cụ thể | Dữ liệu không còn có thể liên kết tới chủ thể |
| Retention và xóa | Giới hạn thời gian/cách tồn tại của dữ liệu | Dữ liệu đã được xóa ở mọi bản sao hoặc trên media |
| Backup và recovery | Khả năng phục hồi dữ liệu được phép | Quyền/xóa hiện hành còn đúng sau restore |

Mã hóa toàn volume có thể phù hợp để chống mất thiết bị, nhưng không nhất thiết chống tài khoản database có quyền đọc plaintext. Cần viết yêu cầu theo tác nhân và đường truy cập muốn chống.

Tương tự, checksum lưu cạnh dữ liệu không tự xác thực nguồn nếu bên sửa được dữ liệu cũng sửa được checksum. Yêu cầu toàn vẹn phải chỉ rõ nguồn xác thực, quyền sửa, cơ chế phát hiện và hành vi khi lỗi.

### 3.2. Rủi ro trong ví dụ

| Mã rủi ro | Tình huống | Hậu quả |
|---|---|---|
| R-DPT-01 | Sai tenant, sai field hoặc đường storage trực tiếp bỏ quyền | Dữ liệu bị đọc ngoài phạm vi |
| R-DPT-02 | Thu thập hoặc trả thêm dữ liệu không cần thiết | Tăng mức lộ và phạm vi xử lý |
| R-DPT-03 | Log, cache, queue, tệp tạm hoặc export giữ bản sao không được bảo vệ | Dữ liệu rò ngoài kho chính |
| R-DPT-04 | Khóa/peer lỗi dẫn tới plaintext hoặc nguồn khóa sai | Mất bí mật và tính toàn vẹn |
| R-DPT-05 | Dữ liệu bị sửa, tráo tài nguyên hoặc phát lại bản cũ | Quyết định nghiệp vụ sai |
| R-DPT-06 | Xóa hoặc hết hạn chỉ tác động một kho | Dữ liệu còn truy cập được hoặc tái tạo qua job |
| R-DPT-07 | Restore làm sống lại dữ liệu/quyền đã bị loại | Vi phạm trạng thái hiện hành |
| R-DPT-08 | Mất khóa hoặc xóa khóa chung quá sớm | Không khôi phục được dữ liệu còn phải giữ |
| R-DPT-09 | Evidence thiếu scope hoặc chứa chính dữ liệu nhạy cảm | Kết luận sai hoặc thêm điểm rò |

Mỗi rủi ro cần liên kết với yêu cầu và phép kiểm chứng. Không chỉ ghi tên một sản phẩm mã hóa rồi đánh dấu mọi rủi ro đã xử lý.

### 3.3. Chọn baseline có phiên bản

Khi dùng ASVS hoặc framework khác, cần ghi phiên bản, mục áp dụng, phần bổ sung theo dữ liệu và lý do không áp dụng. Cách đánh số có thể thay đổi giữa phiên bản, nên mapping phải được quản lý. [OWASP ASVS: Referencing requirements](https://github.com/OWASP/ASVS#how-to-reference-asvs-requirements)

Các mã DPT trong bài là ID nội bộ, không phải mã ASVS. Có một số kiểm soát tương tự framework không đủ để tuyên bố toàn sản phẩm đã đạt một mức kiểm chứng.

## 4. Đặc tả quyền truy cập, thu thập và đầu ra

### 4.1. Quyền cần tới đúng tài nguyên và field

Với một thao tác đọc, đặc tả nên xác định chủ thể, tenant, tài nguyên, hành động và tập field được trả. Tenant ID từ request không tự là tenant có thẩm quyền.

Một người có quyền xem trạng thái job chưa chắc có quyền xem toàn bộ tài liệu hoặc credential nội bộ của worker. API phải tạo response theo tập field được phép, thay vì serialize nguyên entity rồi chỉ ẩn trên UI.

Ví dụ hợp đồng đọc metadata:

```json
{
  "id": "doc-test-17",
  "title": "Báo cáo thử nghiệm",
  "state": "READY"
}
```

Response không tự kèm object storage key nội bộ, key reference, token tải, đường dẫn máy chủ hay dữ liệu của người khác. Nếu chức năng cần thêm field, phải có quyết định scope và quyền.

### 4.2. Các đường ngoài UI vẫn thuộc phạm vi

Phải kiểm tra API trực tiếp, export, search, download, preview, version cũ, bulk endpoint, interface hỗ trợ và job bất đồng bộ.

Một giao diện che số liệu không bảo vệ dữ liệu nếu response vẫn mang giá trị đầy đủ. Một URL khó đoán cũng không thay kiểm soát quyền, đặc biệt khi URL đi vào log hoặc bị chia sẻ.

Bulk operation cần kiểm tra từng tài nguyên hoặc một scope tập hợp được định nghĩa chính xác. Không chỉ kiểm tra tài nguyên đầu tiên rồi trả cả tập.

### 4.3. Cache và browser cần hợp đồng riêng

Trong ví dụ, phản hồi chứa nội dung tài liệu dùng chính sách HTTP no-store, và shared cache không được lưu các response đó. Service worker/Cache API hoặc cơ chế client lưu offline phải được cấu hình theo cùng hợp đồng; một header không tự kiểm soát mọi nơi ứng dụng chủ động lưu dữ liệu.

Nếu có cache nội bộ được phép, cần xác định dữ liệu được lưu, key phân tách tenant/chủ thể phù hợp, TTL, quyền đọc và hành vi khi dữ liệu/quyền hết hiệu lực. Kiểm tra quyền chỉ trước khi đưa dữ liệu vào cache có thể không đủ cho lần đọc sau.

Các rủi ro shared cache trả phản hồi cá nhân hóa cho sai người cần được kiểm tra như một đường rò độc lập. [OWASP: Web Cache Security](https://cheatsheetseries.owasp.org/cheatsheets/Web_Cache_Security_Cheat_Sheet.html)

Không thể dùng CORS, no-store hoặc logout để thu hồi dữ liệu người dùng đã tải và lưu ngoài quyền kiểm soát hệ thống. Cam kết phải nêu rõ ranh giới đó.

## 5. Truyền, lưu, toàn vẹn và quản lý khóa

### 5.1. Chỉ rõ profile và các hop được bảo vệ

Yêu cầu truyền dữ liệu cần liệt kê đường client/API, API/worker, datastore, queue, storage, audit và backup thuộc scope. Không chỉ bảo vệ hop từ Internet tới gateway.

Profile cần xác định giao thức và kiểm tra peer theo lựa chọn được phê duyệt, nguồn trust, quyền caller và hành vi khi không xác minh được. Không bỏ xác minh danh tính hoặc fallback sang plaintext để giữ tác vụ chạy.

Với egress hoặc bên xử lý ngoài, cần xác định dữ liệu được gửi, đích được cấp, mục đích, quyền và điều kiện giữ/xóa. Một kết nối TLS thành công chưa chứng minh đúng đối tượng nghiệp vụ được phép nhận.

### 5.2. Bảo vệ dữ liệu lưu theo mô hình đe dọa

Đặc tả cần biết lớp nào mã hóa, ai có thể đọc plaintext, khóa nằm ở đâu và những bản sao nào cùng chịu profile.

Nếu dùng mã hóa cấp ứng dụng, thiết kế cần xử lý version, metadata liên quan, quyền sử dụng khóa và lỗi xác thực nội dung theo cơ chế được chọn. Không tự cài một định dạng mật mã riêng để tránh đặc tả.

Đối với cơ chế xác thực ciphertext, dữ liệu hỏng hoặc ngữ cảnh sai phải bị từ chối trước khi cung cấp plaintext/tác dụng phụ ngoài hợp đồng. Nếu cần chống tráo ciphertext giữa tenant/tài nguyên, phải ràng buộc ngữ cảnh bằng thiết kế có thể kiểm chứng, không chỉ dựa tên file.

Một ciphertext cũ có thể vẫn hợp lệ về mật mã. Chống rollback hoặc phát lại còn cần kiểm tra version/trạng thái hiện hành từ nguồn có thẩm quyền.

### 5.3. Vòng đời khóa gắn với vòng đời dữ liệu

Cần phân biệt:

- Khóa được phép bảo vệ dữ liệu mới.
- Khóa cũ còn cần để đọc dữ liệu hợp lệ hoặc backup.
- Khóa nghi bị lộ cần ngừng cấp quyền và xử lý dữ liệu liên quan.
- Khóa đã đủ điều kiện hủy theo phạm vi và chính sách.
- Các bản sao khóa, bản bọc khóa, cache và dữ liệu plaintext còn tồn tại.

Rotation không tự làm dữ liệu cũ được mã hóa lại. Xóa khóa cũ cũng không tự tạo một migration an toàn. Quy trình phải xác định đọc phiên bản cũ, chuyển đổi nếu cần, bằng chứng hoàn tất và điều kiện hủy.

OWASP Key Management nhấn mạnh việc quản lý trạng thái khóa, khả năng phục hồi và các bản sao khi ngừng sử dụng hoặc hủy. [OWASP: Key Management](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)

Không hủy một khóa chung để xóa một tài liệu nếu việc đó làm mất dữ liệu khác còn được phép giữ. Muốn xóa bằng khóa ở cấp đối tượng, kiến trúc phải có độ hạt và quản lý bản sao phù hợp.

### 5.4. Giới hạn dữ liệu trong bộ nhớ

Ứng dụng thường phải xử lý plaintext trong bộ nhớ để thực hiện chức năng. Yêu cầu nên giới hạn quyền tiến trình, thời gian/cách giữ dữ liệu, dump, swap hoặc instrumentation theo nền tảng và mô hình đe dọa.

Không hứa một lệnh gán null sẽ xóa chắc mọi bản sao trong runtime có garbage collection. Các biện pháp zeroization cần được đánh giá theo API/runtime thực tế; những phần không chứng minh được phải được nêu đúng giới hạn.

Crash report, heap dump và công cụ hỗ trợ cần policy vì có thể chứa dữ liệu hoặc khóa đã được giải mã. Không cho phép tự động xuất chúng sang một đích ngoài phạm vi.

## 6. Logging, dữ liệu thử và export cũng cần bảo vệ

### 6.1. Log theo hợp đồng sự kiện

Trong ví dụ, một sự kiện audit có thể gồm loại thao tác, chủ thể, tài nguyên, tenant, kết quả và mã lý do đã được cho phép. Không cần body tài liệu hoặc access token để xác nhận một thao tác bị từ chối.

OWASP liệt kê credential, token, khóa và dữ liệu nhạy cảm trong những loại thông tin thường cần loại bỏ hoặc xử lý phù hợp trước khi ghi log. Log và các bản sao của nó cũng cần được bảo vệ. [OWASP: Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

Cần kiểm tra các đường:

- Startup và lỗi đọc cấu hình.
- Exception có dữ liệu từ database hoặc request.
- Middleware ghi header/body.
- Trace, metric label và correlation data.
- Collector, queue cục bộ, file tạm và fallback logger.
- Gói hỗ trợ, bản export log và công cụ quan sát.

Lọc trên giao diện xem log không ngăn giá trị gốc đi vào kho. Nên tạo sự kiện từ tập field được phép, đồng thời kiểm tra giới hạn độ dài và dữ liệu do caller kiểm soát.

Thông tin audit định danh người dùng vẫn có thể nhạy cảm. Cần purpose, quyền, retention và khả năng đối chiếu phù hợp, không coi audit là vùng được miễn mọi kiểm soát dữ liệu.

### 6.2. Môi trường test và bằng chứng kiểm chứng

Baseline của ví dụ dùng dữ liệu tổng hợp cho test. Nếu cần dữ liệu thực hoặc dữ liệu dẫn xuất, phải có quyết định scope, cách xử lý, quyền và thời hạn phù hợp.

Thay tên người nhưng giữ nội dung tài liệu hiếm gặp có thể vẫn để lộ chủ thể. Hash một định danh không tự làm dữ liệu vô danh hoặc loại bỏ khả năng liên kết.

Không đưa secret production vào fixture, screenshot, ticket hoặc báo cáo để chứng minh redaction. Dùng giá trị thử có dấu nhận dạng và theo dõi nó tại các đầu ra trong scope.

Evidence phải đủ để tái dựng kết quả nhưng tránh giữ nội dung nhạy cảm không cần thiết. Quyền đọc/export evidence có thể cần chặt hơn quyền xem trạng thái test.

### 6.3. Export là một lần tạo bản sao mới

Khi tạo export, cần xác định tài liệu/field được chọn, người nhận, phạm vi quyền, nơi lưu, điều kiện tải và vòng đời output.

Trong ví dụ:

- Worker chỉ lấy dữ liệu đúng scope đã được xác nhận.
- File chưa hoàn tất nằm trong staging riêng tư.
- Trước công bố, kiểm tra lại trạng thái dữ liệu và quyền áp dụng.
- Download đi qua điểm kiểm soát; không có đường object storage công khai ngoài hợp đồng.
- File export có thời hạn riêng và quy trình dọn.
- Việc người nhận đã tải file được coi là ranh giới khác, có trách nhiệm rõ.

Một grant tạo job không tự cho phép output tồn tại hoặc được tải vô hạn. Cũng không coi việc xóa tài liệu gốc sẽ tự xóa file export được đặt ở bucket khác.

## 7. Retention, xóa và backup: tách từng cam kết

### 7.1. Retention cần mốc bắt đầu và scope

“Giữ trong 30 ngày” chưa đủ nếu không nói 30 ngày từ upload, từ hoàn tất job hay từ lần sử dụng cuối. Việc đọc dữ liệu không nên âm thầm đặt lại retention nếu policy không quy định.

Một policy cần nêu:

| Thành phần | Nội dung cần chốt |
|---|---|
| Loại dữ liệu/bản sao | Gốc, index, cache, file tạm, export, audit hay backup |
| Sự kiện bắt đầu | Tạo, hoàn tất, hết hợp đồng hoặc một sự kiện có thẩm quyền |
| Điều kiện hết hiệu lực | Đến hạn, lệnh xóa, tài nguyên cha bị xóa hoặc trạng thái khác |
| Hành động | Ngừng truy cập, purge ở các kho, hủy khóa hoặc xử lý media theo scope |
| Cận thời gian | Khi nào hành động phải hoàn tất; cách đo |
| Ngoại lệ giữ | Ai cấp, phạm vi dữ liệu, lý do, thời hạn/xem xét lại |
| Bằng chứng | Trạng thái từng bản sao, lần chạy, lỗi và xác nhận hoàn tất |

Nếu có yêu cầu giữ để điều tra, tranh chấp hoặc nghĩa vụ khác, role có thẩm quyền phải xác nhận. Bản ghi giữ không tự khôi phục quyền đọc thông thường và không được mở rộng sang dữ liệu ngoài scope.

### 7.2. Phân biệt ngừng truy cập, xóa logic và sanitization

| Mốc | Kết luận có thể đưa ra |
|---|---|
| Chấp nhận yêu cầu xóa | Yêu cầu đã được xác thực và đăng ký; cần nêu còn bước nào |
| Commit xóa logic | Dữ liệu không còn được dùng qua các đường phục vụ đã xác định |
| Purge ở kho hoạt động | Đã xử lý các bản ghi/object/index/cache trong scope theo cơ chế của kho |
| Hết hiệu lực bản backup | Bản sao không còn được giữ hoặc khôi phục theo policy đã chọn |
| Sanitization media | Có quy trình và bằng chứng về việc làm dữ liệu trên media không còn truy cập được ở mức nỗ lực xác định |

Xóa record hoặc gọi delete object không tự chứng minh mọi byte trên thiết bị đã được ghi đè. Snapshot, versioning, replication và cơ chế lưu vật lý cần phạm vi riêng.

NIST SP 800-88 Rev. 2 mô tả media sanitization như việc làm truy cập dữ liệu mục tiêu không còn khả thi ở một mức nỗ lực xác định, với lựa chọn kỹ thuật và bảo đảm tương ứng. Không dùng nó như tên gọi cho mọi API delete. [NIST SP 800-88 Rev. 2](https://csrc.nist.gov/pubs/sp/800/88/r2/final)

### 7.3. Một hợp đồng thời gian minh họa

Trong tình huống này, dự án chọn:

- Lệnh xóa chỉ được báo ACCEPTED sau khi quyền yêu cầu xóa và trạng thái xóa logic bền vững đã được ghi.
- Mọi thao tác mới bắt đầu sau commit xóa logic không được đọc, công bố hoặc tải dữ liệu đã bị xóa qua các đường phục vụ trong scope.
- Bản sao ở các kho hoạt động thuộc scope phải được purge trong tối đa 24 giờ từ commit, trừ phần có hold được cấp đúng phạm vi.
- Export hết hạn một giờ sau công bố; không cấp download mới sau mốc đó và purge file trong hai giờ từ mốc hết hạn.
- Bản backup được giữ tối đa 35 ngày từ thời điểm snapshot hoàn tất; khi hết hạn phải xử lý theo policy của hệ thống backup.
- Backup còn hạn chỉ phục vụ recovery được cấp, không dùng làm đường đọc dữ liệu đã xóa cho người dùng thông thường.

Đây là các tham số thiết kế, không phải quy định pháp luật. Cần chứng minh bằng kiến trúc và phép đo, hoặc sửa hợp đồng trước khi công bố khả năng hệ thống.

Phạm vi “thao tác mới” phải có điểm xác định rõ ở từng đường vào. Hành vi đối với download hoặc tác vụ đã bắt đầu trước commit cần hợp đồng riêng; dữ liệu đã chuyển ra ngoài không thể bị kéo lại bằng xóa logic.

### 7.4. Ngăn cache và job làm sống lại dữ liệu

Một thiết kế khả thi có trạng thái/generation có thẩm quyền cho tài nguyên. Sau xóa logic:

- Điểm phục vụ xét trạng thái hiện hành trước khi cấp thao tác mới.
- Cache không tự là nguồn xác nhận tài nguyên còn được phục vụ.
- Worker kiểm tra tài nguyên trước đọc và trước công bố output.
- Replay message hoặc retry không được tạo lại tài nguyên từ payload cũ.
- Search/preview không trả dữ liệu trong thời gian chờ purge.
- Mọi version hoặc alias thuộc scope được liên kết tới cùng chính sách.

Để giữ cam kết không phục vụ sau commit, không thể chỉ invalidation cache theo cơ chế “sớm hay muộn”. Cần kiểm tra có thẩm quyền hoặc một cơ chế phối hợp bảo đảm cùng điều kiện; nếu không xác minh được, không cấp thao tác bị ảnh hưởng.

Check rồi ghi ở hai thời điểm không tự loại race condition. Việc publish output phải phối hợp với trạng thái xóa bằng điều kiện commit/version hoặc cơ chế tương đương đã được thiết kế và kiểm chứng.

### 7.5. Backup và restore không dùng dữ liệu lịch sử làm quyền hiện tại

Lệnh xóa xảy ra sau snapshot có thể không nằm trong backup đó. Quy trình recovery cần nguồn trạng thái xóa/hold/quyền hiện hành còn đáng tin, chẳng hạn journal được quản lý độc lập với snapshot đang khôi phục.

Journal cần có scope, thứ tự hoặc watermark đủ để đối chiếu, quyền sửa và tính toàn vẹn. Nếu có thể khôi phục backup 35 ngày, phải giữ đủ thông tin để xử lý mọi lệnh xóa liên quan tới các bản còn có thể khôi phục. Không xóa journal sớm đến mức bản sao cũ không còn đối soát được.

Một quy trình:

```text
Khôi phục vào vùng cách ly
    -> Xác minh nguồn backup, schema và khả năng dùng khóa cần thiết
    -> Lấy trạng thái xóa/hold/quyền còn có thẩm quyền
    -> Đối soát tới watermark hiện hành theo hợp đồng
    -> Loại hoặc cách ly dữ liệu không còn được phép phục vụ
    -> Rebuild index/cache từ tập dữ liệu còn được phép
    -> Kiểm tra quyền, logging và các đường download
    -> Chỉ mở phục vụ sau khi đủ bằng chứng
```

Nếu chưa biết journal có đầy đủ hay không, không tự mở phục vụ dữ liệu cũ rồi chờ đồng bộ sau. Hệ thống cần giữ cách ly phần chưa xác nhận theo hợp đồng recovery.

Mục tiêu phục hồi còn phải xét độ mới của journal và khóa, không chỉ RPO của database. Khôi phục đủ bản ghi không đồng nghĩa khôi phục đúng trạng thái bảo mật.

### 7.6. Xóa bằng khóa có điều kiện nghiêm ngặt

Cryptographic erasure chỉ có ý nghĩa trong scope mà mọi bản sao khóa cần thiết được xử lý và không còn bản plaintext có thể phục hồi ngoài giả định. Xóa một KEK không tự xóa plaintext DEK đang nằm ở nơi khác.

Phương án này cần biết độ hạt khóa, bản bọc, backup/escrow, key cache và dữ liệu dùng chung. Không mô tả thao tác disable một key reference là bằng chứng mọi bản dữ liệu đã bị hủy.

Nếu policy dùng cryptographic erasure, cần quy trình và evidence riêng về điều kiện áp dụng. Nó không thay việc ngăn truy cập logic trong khi đang chờ hoàn tất.

## 8. Bộ yêu cầu data protection có thể kiểm chứng

### 8.1. Một yêu cầu đầy đủ

**DPT-01 — Bảo vệ tài liệu theo chủ thể, tenant, tài nguyên và field**

- **Rủi ro:** R-DPT-01 và R-DPT-02.
- **Phạm vi:** API đọc, search, preview, download, bulk export và các đường trực tiếp được hỗ trợ.
- **Đầu vào có thẩm quyền:** danh tính đã xác minh, metadata sở hữu/phân loại và policy hiện hành.
- **Yêu cầu:** chỉ cấp dữ liệu và field trong quyền của chủ thể đối với đúng tài nguyên/tenant/hành động.
- **Khi lỗi:** thiếu hoặc không xác minh được điều kiện bắt buộc thì không trả nội dung hoặc tạo bản sao có thể truy cập trái phép.
- **Bằng chứng:** danh mục interface, ma trận quyền/field, code/config liên quan, kết quả test API và trạng thái dữ liệu.
- **Tiêu chí chấp nhận:** tài khoản tenant A đổi ID sang tài liệu/job của B vẫn không đọc được nội dung, metadata bị hạn chế hoặc file xuất.
- **Giới hạn:** endpoint công khai nếu có phải được liệt kê với phạm vi dữ liệu riêng, không miễn kiểm soát cả service.

Chỉ quan sát HTTP 403 chưa đủ nếu output vẫn được tạo tại một URL đọc được. Phải kiểm tra các đường đọc và tác dụng phụ thuộc phạm vi yêu cầu.

### 8.2. Yêu cầu bổ sung

| ID | Yêu cầu trong baseline minh họa | Bằng chứng chấp nhận chính |
|---|---|---|
| DPT-02 | Có inventory dữ liệu, mục đích, owner, phân loại và mọi bản sao thuộc scope; thu thập/response theo tập field được cấp. | Field không cần hoặc ghi ngoài quyền không bị lưu/đưa ra do serialize object rộng. |
| DPT-03 | Mọi hop truyền dữ liệu trong scope dùng profile bảo vệ và danh tính peer phù hợp. | Đối tác sai, trust sai hoặc lỗi thiết lập không tạo fallback plaintext/trust-all. |
| DPT-04 | Các kho hoạt động, tệp tạm, queue và backup áp dụng profile lưu tương ứng phân loại. | Kiểm tra quyền/lớp mã hóa thực tế; không chỉ một flag của database. |
| DPT-05 | Quyền dùng khóa, rotation, đọc phiên bản cũ và hủy có hợp đồng gắn với dữ liệu. | Thiếu khóa không ghi plaintext; rotation/restore không làm mất dữ liệu còn được phép giữ. |
| DPT-06 | Cơ chế toàn vẹn và ràng buộc ngữ cảnh phát hiện sửa/tráo dữ liệu; kiểm tra version riêng chống dùng bản cũ trái phép. | Ciphertext hỏng/sai ngữ cảnh và bản cũ không còn được chấp nhận không tạo output nghiệp vụ hợp lệ. |
| DPT-07 | Cache và client storage theo policy; cache không bỏ kiểm tra quyền/trạng thái dữ liệu. | Không rò giữa session/tenant, không phục vụ tài nguyên đã bị loại chỉ vì cache còn. |
| DPT-08 | Log, trace, dump, telemetry và evidence không chứa dữ liệu bị cấm; đầu ra có quyền và retention. | Dấu thử trong credential/body không xuất hiện trong các sink bị cấm, kể cả fallback. |
| DPT-09 | Export có scope dữ liệu, đích nhận, kiểm tra trước publish/download và thời hạn riêng. | Không dùng job hoặc URL cũ để công bố/tải dữ liệu hết quyền hoặc bị xóa. |
| DPT-10 | Retention có mốc bắt đầu, bản sao, hành động, deadline và owner; hold có thẩm quyền và scope riêng. | Không tự gia hạn khi đọc dữ liệu; không giữ cả tenant vì một đối tượng có hold. |
| DPT-11 | Xóa logic được ghi bền vững trước ACCEPTED; thao tác mới sau commit không phục vụ dữ liệu đã loại. | Test đồng thời, cache, search và job; không tái tạo từ payload cũ. |
| DPT-12 | Purge theo từng kho trong cận đã chọn, giữ trạng thái chưa hoàn tất và lỗi. | Chưa xóa version/index/export thì không báo mọi bản sao đã được xử lý. |
| DPT-13 | Backup có quyền/profile/thời hạn; restore đối soát trạng thái hiện hành trước phục vụ. | Backup trước lệnh xóa không làm dữ liệu đó xuất hiện lại; journal chưa đủ thì giữ cách ly. |
| DPT-14 | Test/support dùng dữ liệu phù hợp và quyền giới hạn; bản export hỗ trợ có vòng đời. | Không sao dữ liệu/secret production sang môi trường phụ mà thiếu quyết định áp dụng. |
| DPT-15 | Mỗi kết luận kiểm chứng gắn subject/config, scope, phương pháp và evidence đã lọc. | Thiếu bằng chứng hoặc report build khác không tự thành VERIFIED. |
| DPT-16 | Thay đổi luồng dữ liệu, bên nhận, policy, khóa hoặc topology kích hoạt đánh giá lại phần bị ảnh hưởng. | Luồng mới không kế thừa vô điều kiện kết quả của kho/đích cũ. |

Các ID DPT là mã nội bộ của bài học. Kết luận phải chỉ rõ yêu cầu nào đã kiểm chứng và phần nào còn mở.

Không cần mọi kiểm soát có cùng công cụ hoặc cùng tầng thực thi. Quan trọng là các điểm bảo vệ bao phủ đúng luồng dữ liệu và bằng chứng xác nhận được hành vi.

## 9. Hồ sơ bằng chứng và điều kiện qua gate

### 9.1. Bằng chứng cần đi theo đúng bản triển khai

Một record verification nên có:

| Nhóm | Nội dung |
|---|---|
| Yêu cầu | ID, revision, applicability và tiêu chí chấp nhận |
| Subject | Artifact/build, cấu hình, schema, policy và deployment liên quan |
| Phạm vi | Dữ liệu, kho, interface, bản sao và môi trường được kiểm tra |
| Phương pháp | Review thiết kế, code/config, test, kiểm tra trạng thái hoặc diễn tập recovery |
| Điều kiện test | Chủ thể, tenant, dữ liệu tổng hợp, trạng thái và lỗi được tạo |
| Kết quả | Hành vi quan sát, trạng thái dữ liệu và các deadline đã đo |
| Nguồn | Người/hệ thống tạo, thời điểm, công cụ và tham chiếu evidence |
| Giới hạn | Phần chưa biết, sample, giả định và điều kiện cần kiểm chứng thêm |

Sơ đồ mã hóa hoặc ADR cho biết thiết kế dự kiến. Cấu hình quyền và key service cho biết một phần implementation. Test và quan sát thực tế bổ sung bằng chứng hành vi.

Không suy ra production được bảo vệ giống staging nếu quyền, bucket, collector hoặc backup policy khác nhau.

### 9.2. Mẫu record cho yêu cầu restore

```yaml
requirementId: DPT-13
revision: 1
scope: documents-backup-and-restore
riskRefs: [R-DPT-06, R-DPT-07, R-DPT-08]

subject:
  buildRef: "documents-build-208"
  dataPolicyRevision: "data-protection-042"
  restorePlanRevision: "restore-plan-17"

checks:
  - id: snapshot-before-delete
    expected: deleted-document-not-served-after-restore
  - id: deletion-journal-incomplete
    expected: restored-scope-remains-isolated
  - id: required-key-version-unavailable
    expected: no-plaintext-fallback-and-no-false-success

evidenceRefs:
  - design-review-restore-17

verification:
  designReview: ADDRESSED
  implementationTests: NOT_RUN
  operationalExercise: NOT_RUN
  decision: NOT_VERIFIED

ownerRole: data-recovery-owner
verifierRole: data-protection-verification-owner
```

Schema và ID là dữ liệu minh họa. Record thể hiện thiết kế đã được xem xét nhưng chưa có test/diễn tập, nên không được đánh giá VERIFIED.

### 9.3. Trạng thái không được che mất khoảng trống

Có thể giữ các chiều độc lập:

- **Applicability:** áp dụng hay không, cùng lý do và phạm vi.
- **Design:** đã phân bổ cơ chế hay còn câu hỏi.
- **Verification:** đạt, không đạt hoặc chưa đủ bằng chứng.
- **Exception:** có quyết định ngoại lệ được phép hay không, còn hiệu lực ở đâu.
- **Operational status:** deployment hiện tại còn giữ điều kiện đã xác minh không.

Một ngoại lệ được chấp nhận không sửa kết quả FAILED thành VERIFIED. Một kiểm soát do provider thực hiện vẫn cần evidence phù hợp; không tự chuyển N/A vì đội phát triển không sở hữu nó.

Một ảnh chụp “encryption enabled” chỉ hỗ trợ thuộc tính tương ứng của kho tại thời điểm đó. Nó chưa chứng minh tệp tạm, query result, quyền giải mã hoặc backup cũng đáp ứng.

### 9.4. Gate phải xét điều kiện bắt buộc

Ví dụ, gate phát hành yêu cầu mọi kiểm soát bắt buộc trong scope đã được xác minh bằng evidence còn áp dụng, finding/khoảng trống được xử lý theo policy và ngoại lệ đúng quyền nếu được phép.

Một lần test không rò dữ liệu nhưng chỉ chạy tài khoản admin chưa đủ cho yêu cầu tenant isolation. Một báo cáo không có canary không đủ nếu chưa kiểm kê hết các sink bắt buộc.

Nếu 12/14 yêu cầu áp dụng đã VERIFIED, một yêu cầu còn FAILED và một yêu cầu NOT_VERIFIED, báo cáo phải giữ cả hai. Tỷ lệ 12/14 không tự cho phép bỏ yêu cầu bắt buộc.

Hồ sơ gate phải nêu quyết định cho đúng subject/config. Thay đổi storage policy sau gate có thể làm điều kiện không còn đúng dù artifact ứng dụng giữ nguyên.

## 10. Kế hoạch kiểm chứng theo vòng đời dữ liệu

### 10.1. Chuẩn bị dữ liệu đối chứng và quyền

Bộ dữ liệu thử nên có:

- Hai tenant A và B với tài liệu/metadata khác nhau.
- Chủ thể có quyền đọc, có quyền quản lý và không có quyền.
- Tài liệu đang hoạt động, bị thu hồi quyền, xóa logic, chờ purge và có hold được cấp.
- Bản gốc, version cũ, index, preview, tệp tạm và export có thể đối chiếu.
- Credential và nội dung tổng hợp có dấu nhận dạng.
- Backup trước/sau lệnh xóa cùng journal có thể kiểm tra.
- Trạng thái khóa/profile phù hợp, lỗi có kiểm soát và cách khôi phục môi trường.

Dữ liệu đối chứng giúp xác định hệ thống thực sự trả tài nguyên nào. Chỉ kiểm tra body không rỗng hoặc HTTP 200/403 không đủ để đánh giá bảo vệ dữ liệu.

### 10.2. Các ca kiểm thử chính

| Ca | Điều kiện hoặc tác động | Kết quả chấp nhận |
|---|---|---|
| T01 | Người có quyền đọc tài liệu trong tenant của mình | Chỉ trả dữ liệu/field đúng hợp đồng, không thêm thông tin nội bộ |
| T02 | Thay document, job hoặc version ID sang tenant khác | Không đọc được nội dung/metadata bị hạn chế và không tạo bản sao truy cập được |
| T03 | Bulk request gồm một tài nguyên đúng quyền và một tài nguyên ngoài quyền | Xử lý theo hợp đồng từng phần/toàn bộ đã chọn; không lộ tài nguyên ngoài quyền |
| T04 | Gửi field ngoài quyền hoặc chưa có mục đích được chấp nhận | Không tự lưu/ghi đè field đó; response không serialize thêm dữ liệu |
| T05 | Gọi storage, search, preview hoặc interface hỗ trợ theo các đường trong scope | Không có đường bỏ kiểm soát truy cập của dữ liệu |
| T06 | Warm cache bằng tenant/session A rồi đọc bằng B hoặc sau xóa logic | Không trả nhầm dữ liệu và không phục vụ dữ liệu đã loại qua cache |
| T07 | Peer hoặc trust của một hop sai, dịch vụ phụ trợ không đáp ứng profile | Thao tác liên quan không fallback sang kết nối kém bảo vệ |
| T08 | Thiếu quyền dùng khóa hoặc key service lỗi trong lúc ghi | Không ghi dữ liệu nhạy cảm dạng rõ, không tạo output dở dang có thể đọc |
| T09 | Sửa ciphertext, tráo ngữ cảnh tenant/resource hoặc phát lại version đã bị loại | Không cấp plaintext/kết quả nghiệp vụ hợp lệ ngoài hợp đồng |
| T10 | Rotation rồi đọc dữ liệu cũ và restore backup còn hạn | Dữ liệu được phép còn đọc/khôi phục được theo profile; không hủy khóa quá sớm |
| T11 | Dấu thử trong token, cookie, body và exception | Không có ở log/trace/export/evidence bị cấm, kể cả file tạm và fallback |
| T12 | Export được tạo, hết hạn hoặc tài liệu gốc đã bị loại trước publish | Không công bố/tải mới trái trạng thái; purge theo deadline áp dụng |
| T13 | Commit xóa logic khi cache/index/job vẫn giữ bản cũ | Thao tác mới không phục vụ dữ liệu; retry/replay không tái tạo quyền hoặc tài nguyên |
| T14 | Worker bị pause giữa kiểm tra quyền/trạng thái và commit output; xóa logic trong khoảng đó | Cơ chế phối hợp ngăn publish trái trạng thái, không chỉ check-then-use |
| T15 | Purge ở một kho thất bại hoặc còn version cũ/dead-letter copy | Giữ trạng thái chưa hoàn tất, có owner/retry; không báo mọi bản sao đã xong |
| T16 | Một tài liệu có hold được cấp, tài liệu khác không có | Chỉ scope được cấp được giữ; không trả lại quyền đọc thông thường hoặc giữ cả tenant vô điều kiện |
| T17 | Restore snapshot trước lệnh xóa với journal hiện hành đầy đủ | Dữ liệu đã xóa không được phục vụ lại, index/cache rebuild từ tập được phép |
| T18 | Restore thiếu journal, không xác minh được watermark hoặc khóa cần thiết | Phần chưa xác nhận giữ cách ly; không báo phục hồi an toàn thành công |
| T19 | Backup/export đến hạn theo policy | Không gia hạn do restore/copy ngoài hợp đồng; xử lý và giữ evidence đúng scope |
| T20 | Evidence thuộc build/config khác hoặc thiếu một kho bắt buộc | Không dùng để kết luận toàn phạm vi VERIFIED |
| T21 | Thêm analytics, đích nhận hoặc cache mới | Kích hoạt kiểm kê và đánh giá lại yêu cầu chịu ảnh hưởng |
| T22 | Dọn môi trường test sau lỗi/crash | Xử lý fixture, credential thử, file tạm và bản xuất theo scope; giữ evidence được phép |

T08/T09 cần quan sát dữ liệu lưu và tác dụng phụ, không chỉ thấy một thông báo lỗi. T11 cần nêu rõ sink nào đã kiểm tra, rule lọc nào có hiệu lực và điều gì còn chưa được quan sát.

T15 cần kiểm tra trạng thái từng bản sao. Một job purge trả thành công không thay bằng chứng rằng object version hoặc search index thực tế đã được xử lý.

T17/T18 phải chạy trong môi trường phục hồi cách ly. Không dùng dữ liệu thật hoặc mở dữ liệu khôi phục cho người dùng để thử xem có bị rò hay không.

### 10.3. Ví dụ Given–When–Then cho xóa và restore

```gherkin
Given snapshot S hoàn tất trước khi tài liệu D được xóa logic
And lệnh xóa D đã được commit vào journal có thẩm quyền
And D còn xuất hiện trong dữ liệu lịch sử của S
When hệ thống khôi phục S vào vùng cách ly
Then chưa mở đường đọc, search hoặc download cho người dùng
And đối soát journal tới watermark hiện hành theo hợp đồng
And D không thuộc tập dữ liệu được đưa trở lại phục vụ
And index và cache không tái tạo khả năng đọc D
And evidence ghi snapshot, policy, watermark, kết quả và phần chưa xác nhận
```

Ca âm tương ứng làm journal không đầy đủ hoặc không xác minh được. Kết quả bắt buộc là giữ cách ly phần chịu ảnh hưởng, không coi “database đã restore” như bằng chứng bảo vệ dữ liệu đã đạt.

### 10.4. Kiểm tra cận thời gian đúng mốc

Đối với xóa logic, đo từ commit đã được định nghĩa; đối với purge, đo từ cùng mốc hoặc sự kiện đã công bố cho bản sao đó. Đừng bắt đầu đồng hồ lúc worker purge nhận việc nếu hợp đồng bắt đầu từ lúc chấp nhận xóa.

Đối với export, phải phân biệt hạn cấp download mới, trạng thái tải đã bắt đầu và thời hạn purge byte ở storage.

Lịch quét mỗi 24 giờ không tự bảo đảm purge hoàn tất trong 24 giờ. Còn phải tính thời gian job chờ, retry, scan, giới hạn API và xử lý lỗi. Nếu chưa bảo đảm cận, giữ khoảng trống kiến trúc và điều chỉnh trước khi công bố cam kết.

## 11. Theo dõi vận hành và đánh giá lại

### 11.1. Quan sát hiệu lực, không chỉ sự tồn tại của cấu hình

Các tín hiệu có thể gồm:

- Mức hoàn tất inventory và khoảng trống luồng/bản sao.
- Số yêu cầu xóa/purge đang chờ theo tuổi, kho và owner.
- Export đã hết hạn nhưng chưa xử lý xong.
- Backup quá hạn hoặc không xác nhận được vòng đời.
- Lỗi dùng khóa, migration chưa hoàn tất và phiên bản cần cho recovery.
- Sai lệch quyền storage, cache, collector hoặc đường egress.
- Kết quả diễn tập restore và trạng thái đối soát journal.
- Chất lượng evidence và các điều kiện kiểm chứng không còn áp dụng.

Không ghi chính nội dung tài liệu hoặc token vào metric label. Số liệu vận hành phải dùng dữ liệu tối thiểu và tránh cardinality do caller điều khiển.

Nếu inventory chưa bao phủ hết kho, báo cáo không được tuyên bố purge toàn hệ thống. Mẫu số và giới hạn phải xuất hiện trong kết luận.

### 11.2. Khi nào phải xem lại yêu cầu?

Cần đánh giá tác động khi:

- Thu thập thêm field hoặc thay mục đích xử lý.
- Thêm đích nhận, analytics, search, OCR hoặc dữ liệu dẫn xuất.
- Đổi quyền, tenant model, cache hoặc đường download.
- Đổi crypto profile, key hierarchy hoặc cơ chế rotation.
- Đổi retention, hold, object versioning hoặc chính sách backup.
- Đổi quy trình restore, journal hoặc nơi giữ trạng thái xóa.
- Thêm debug/dump/support export.
- Có finding/sự cố cho thấy bản sao bị bỏ sót.

Phạm vi kiểm chứng lại dựa trên ảnh hưởng. Có thể giữ evidence còn phù hợp, nhưng phải chứng minh input và giả định liên quan không đổi.

### 11.3. Phản ứng khi phát hiện dữ liệu đã lộ

Đóng đường rò và giới hạn truy cập là bước quan trọng, nhưng không xóa được những bản đã bị đọc hoặc sao chép ra ngoài. Cần xác định dữ liệu, bên nhận, thời gian và phạm vi ảnh hưởng để xử lý theo quy trình có thẩm quyền.

Nếu credential xuất hiện trong log, chỉ sửa redaction không xử lý credential đã lộ. Cần xem xét thu hồi/xoay thông tin liên quan, phạm vi bản sao log và kiểm tra lại đường xuất dữ liệu.

Với khóa bị nghi lộ, re-encrypt hoặc thay khóa không làm dữ liệu ciphertext cũ đã bị lấy đi trở lại bí mật nếu bên khác có đủ khóa. Kết luận và thông tin sự cố phải phản ánh giới hạn này.

## 12. Bài tập: sửa yêu cầu “mã hóa database là đủ”

Một dịch vụ mô tả hiện trạng:

- Database được mã hóa, nhưng worker ghi file tạm vào volume dùng chung.
- API trả nguyên entity rồi UI che các field nội bộ.
- Cache dùng document ID làm key mà không có ràng buộc quyền rõ.
- Log lỗi ghi request body và URL tải.
- Xóa tài liệu chỉ đặt cờ trong database.
- Export, index và object version cũ không có owner purge.
- Restore backup đưa dịch vụ lên ngay, chưa đối soát các lệnh xóa xảy ra sau snapshot.

Hãy viết lại đặc tả:

1. Lập inventory dữ liệu và mọi bản sao có thể được tạo.
2. Xác định quyền tài nguyên/field và tập đầu ra được phép.
3. Chỉ rõ hop truyền, lớp lưu, key lifecycle và hành vi lỗi.
4. Thiết kế logging, export, cache và tệp tạm theo cùng phân loại dữ liệu.
5. Tách cam kết xóa logic, purge, backup và sanitization.
6. Thiết kế journal/đối soát để restore không làm sống lại dữ liệu đã loại.
7. Chọn phép kiểm chứng và điều kiện gate cho đúng scope.

Một chuỗi truy vết mẫu:

| Mắt xích | Nội dung |
|---|---|
| Tài sản | Nội dung và metadata tài liệu đã được yêu cầu xóa |
| Rủi ro | R-DPT-06 và R-DPT-07: bản sao còn phục vụ hoặc tái xuất hiện sau restore |
| Yêu cầu | DPT-10 đến DPT-13 |
| Phân bổ | Trạng thái tài nguyên, điểm đọc/publish, purge theo kho, backup và journal |
| Kiểm chứng | Review vòng đời, test đồng thời T13/T14, purge T15 và restore T17/T18 |
| Evidence | Mốc commit, phạm vi bản sao, kết quả từng kho, snapshot và watermark |
| Kết luận | Phân biệt ngừng phục vụ, purge chưa xong và backup còn giữ có kiểm soát |

Sản phẩm cần đạt là hợp đồng bảo vệ dữ liệu có phạm vi rõ: dữ liệu nào được xử lý, ai được dùng, bản sao nào tồn tại, khi nào phải ngừng phục vụ/xóa và bằng chứng nào xác nhận các điều kiện vẫn đúng khi lỗi hoặc phục hồi.

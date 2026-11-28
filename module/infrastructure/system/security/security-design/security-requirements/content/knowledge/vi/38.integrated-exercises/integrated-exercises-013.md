# Thực hiện security requirement review

## 1. Mục tiêu bài thực hành

Security requirement review là hoạt động đánh giá yêu cầu bảo mật trước khi chúng trở thành đầu vào chính thức cho thiết kế, triển khai và kiểm thử. Người review cần xác định yêu cầu có giải quyết đúng rủi ro, có diễn đạt rõ hành vi, có thực hiện được và có bằng chứng nghiệm thu hay không.

Một bộ yêu cầu có nhiều từ như “an toàn”, “mã hóa”, “phân quyền” vẫn có thể bỏ sót truy cập chéo tenant, rò rỉ qua log hoặc hành vi bỏ qua kiểm tra khi dịch vụ phụ thuộc gặp lỗi. Review có giá trị khi những khoảng trống đó được chuyển thành phát hiện có bằng chứng, yêu cầu sửa cụ thể và quyết định có người chịu trách nhiệm.

Sau bài thực hành tổng hợp này, bạn cần:

- Chuẩn bị được gói đầu vào và phạm vi review, gồm mục tiêu an toàn thông tin, mô hình đe dọa, luồng dữ liệu và tiêu chí nghiệp vụ.
- Phân biệt lỗi chất lượng đặc tả, thiếu kiểm soát rủi ro, quyết định kiến trúc chưa rõ và thiếu bằng chứng thực hiện.
- Phát hiện yêu cầu mơ hồ, thiếu điều kiện, mâu thuẫn, không kiểm chứng được hoặc quá phụ thuộc vào một giải pháp chưa được chứng minh.
- Viết nhận xét có thể hành động và sửa yêu cầu thành đặc tả đo được.
- Truy vết từ rủi ro đến yêu cầu, vị trí thực thi, ca kiểm thử và quyết định review.
- Xử lý ngoại lệ, chấp nhận rủi ro và mở lại review khi có thay đổi trong vòng đời phát triển.

Bài dùng một tình huống giả định tự chứa. Các ngưỡng và lựa chọn sản phẩm là giả định để luyện cách review, không phải tiêu chuẩn chung cho mọi ứng dụng.

## 2. Phân biệt các loại review và kết quả của chúng

| Hoạt động | Câu hỏi chính | Bằng chứng điển hình |
| --- | --- | --- |
| Review yêu cầu bảo mật | Hệ thống phải bảo vệ điều gì, trong điều kiện nào, kiểm chứng ra sao? | Đặc tả, mô hình đe dọa, tiêu chí chấp nhận, truy vết |
| Review thiết kế | Kiến trúc được đề xuất có thể thực hiện những yêu cầu đó không? | Luồng dữ liệu, ranh giới tin cậy, giao thức, quyết định kiến trúc |
| Review mã nguồn | Mã có thực hiện đúng thiết kế/yêu cầu và có lỗi triển khai không? | Diff, code, cấu hình, phân tích luồng |
| Kiểm thử bảo mật | Hệ thống đang chạy phản ứng thế nào với các ca đã xác định? | Request/response, kết quả kiểm thử, dấu vết và trạng thái dữ liệu |
| Quyết định phát hành | Những điều kiện của bản phát hành đã đạt hoặc được chấp nhận có thẩm quyền chưa? | Kết quả review, kiểm thử, vận hành, ngoại lệ và rủi ro tồn dư |

Một yêu cầu có thể được chấp thuận về nội dung khi chưa có mã. Điều đó chỉ nói rằng yêu cầu đủ rõ để tiếp tục công việc, không chứng minh sản phẩm đã đáp ứng yêu cầu. Ngược lại, một ca thử tình cờ thành công không sửa được đặc tả đang bỏ ngỏ hành vi quan trọng.

Đầu ra của buổi review gồm phiên bản yêu cầu đã xem xét, sổ phát hiện, quyết định trên từng điểm, người chịu trách nhiệm, hạn xử lý và điều kiện cần kiểm chứng ở bước sau. Không dùng một dấu “approved” chung cho mọi mức bảo đảm.

## 3. Tình huống: chức năng xuất dữ liệu hỗ trợ khách hàng

Một nền tảng hỗ trợ khách hàng phục vụ nhiều doanh nghiệp. Mỗi doanh nghiệp là một tenant. Người dùng có thể xem các ticket trong nhóm được cấp quyền. Nhóm sản phẩm muốn bổ sung chức năng xuất dữ liệu để người có quyền phân tích tải về một gói dữ liệu.

Các endpoint dự kiến:

```http
POST /v1/exports
GET /v1/exports/{export_id}
GET /v1/exports/{export_id}/download
```

Tác vụ xuất chạy bất đồng bộ. Worker đọc ticket, tạo artifact trong object storage và cập nhật trạng thái job. Client xem trạng thái rồi tải artifact. Artifact là sản phẩm có dữ liệu nhạy cảm, không phải một đường dẫn có thể công khai chỉ vì khó đoán.

### 3.1. Các quyết định nghiệp vụ đã được xác nhận

- Chỉ principal đã xác thực, còn hoạt động và có quyền `ticket:export` mới được tạo job.
- Tenant được lấy từ ngữ cảnh xác thực đã xác minh. Bộ lọc client không được mở rộng phạm vi tenant hoặc nhóm của người gọi.
- Mỗi job thuộc một tenant và một người tạo. Trong phiên bản này chỉ người tạo còn đủ quyền mới xem trạng thái hoặc tải kết quả; không có quyền quản trị tải thay mặc định.
- Phạm vi dòng dữ liệu là giao giữa bộ lọc nghiệp vụ và các ticket người gọi được phép xuất. Các trường nhạy cảm như email người yêu cầu chỉ được đưa vào khi có thêm quyền `ticket:export_sensitive`.
- Định dạng tải xuống của phiên bản này là JSON Lines: mỗi dòng là một JSON object được serialize đúng định dạng. Không tự bổ sung HTML, CSV hoặc một định dạng bảng tính khác.
- Artifact dùng được tối đa 24 giờ từ `ready_at`, không gia hạn khi tải lại. Dịch vụ phải xóa artifact khỏi storage hoạt động và các replica phục vụ trong vòng 1 giờ sau khi hết hạn.
- Mọi request và luồng tải dài phải phản ánh việc thu hồi quyền trong thời gian không quá 60 giây theo cơ chế được đặc tả; không cam kết lấy lại các byte người dùng đã tải trước đó.
- Giới hạn mỗi artifact là 100000 dòng và 100 MiB dữ liệu JSONL chưa nén. Không âm thầm cắt bớt kết quả rồi báo job thành công.

Những quyết định này là đầu vào của tình huống. Nếu học viên muốn thay đổi, phải ghi đề xuất và tác động để chủ sản phẩm quyết định, không tự sửa giả định chỉ để làm một yêu cầu dễ đạt hơn.

### 3.2. Dữ liệu và ranh giới tin cậy

| Thành phần | Dữ liệu hoặc quyết định nhạy cảm | Ranh giới cần review |
| --- | --- | --- |
| Client | Bộ lọc, ID job, request retry | Client không tự chứng minh tenant/quyền |
| API | Danh tính, quyền, metadata job | Xác thực khác với quyền trên đối tượng cụ thể |
| Worker | Phạm vi dòng/trường, trạng thái công việc | Message trong queue không thay thế kiểm tra quyền và hợp đồng |
| Object storage | Artifact nhiều ticket, có thể có dữ liệu cá nhân | Biết object key không đồng nghĩa có quyền đọc |
| Gateway tải xuống | Quyền hiện tại, TTL, phạm vi artifact | Truy cập phải đi qua kiểm soát, kể cả retry/range request |
| Log/audit | Ai xuất/tải gì, lỗi, lịch sử quyết định | Không đưa nguyên nội dung xuất hoặc token vào log |
| Backup/recovery | Job, quyền cũ và artifact lịch sử | Restore không làm sống lại quyền hoặc artifact đã hết hạn |

### 3.3. Mô hình đe dọa tóm tắt

| Mã | Hành vi đe dọa/sai sót | Hậu quả |
| --- | --- | --- |
| R-01 | Đổi `tenant_id`, bộ lọc hoặc ID job để trỏ sang tenant khác | Xuất hoặc đọc dữ liệu ngoài tenant |
| R-02 | Người dùng chỉ xem được nhóm A nhưng worker xuất cả tenant | Mở rộng phạm vi quyền khi xử lý nền |
| R-03 | Tải artifact sau khi người tạo mất quyền hoặc ticket đổi nhóm | Quyền cũ tiếp tục cấp dữ liệu |
| R-04 | Link tải là bearer token dài hạn, bucket hoặc fallback công khai | Người không được cấp quyền vẫn tải được |
| R-05 | Log nguyên payload, header hoặc artifact | Lộ dữ liệu qua hệ thống quan sát |
| R-06 | Export rất lớn hoặc gửi nhiều job | Cạn CPU, storage, queue và ảnh hưởng tenant khác |
| R-07 | Retry hoặc crash tạo nhiều job/artifact và trạng thái không nhất quán | Tác vụ lặp, file dở dang bị phát hành |
| R-08 | Backup/restore khôi phục credential, quyền và artifact đã hết hạn | Dữ liệu cũ bị phục vụ lại trái chính sách |
| R-09 | Mất dịch vụ phân quyền nhưng hệ thống bỏ kiểm tra để giữ khả dụng | Truy cập vượt quyền trong lúc sự cố |
| R-10 | Chính sách, worker và kiểm thử dùng các phiên bản phạm vi khác nhau | Kiểm soát không nhất quán, bằng chứng không còn phù hợp |

## 4. Gói yêu cầu ban đầu để học viên review

Đây là bản nháp `EXPORT-DRAFT-0.1`, cố ý chứa điểm thiếu và mâu thuẫn. Nó là dữ liệu của bài tập, không phải đặc tả được khuyến nghị.

| Mã nháp | Nội dung ban đầu |
| --- | --- |
| D-01 | Chức năng export phải an toàn và theo thông lệ tốt. |
| D-02 | Người dùng đăng nhập được xuất dữ liệu theo bộ lọc; request có thể gửi `tenant_id` để worker biết doanh nghiệp. |
| D-03 | Worker dùng tài khoản dịch vụ có quyền đọc toàn bộ ticket để xử lý nhanh. |
| D-04 | Người biết ID job có thể xem trạng thái; ID là UUID nên khó đoán. |
| D-05 | Link tải được ký và dùng được trong 7 ngày; khi dịch vụ phân quyền lỗi có thể dùng link trực tiếp tới storage. |
| D-06 | Artifact được mã hóa và tự xóa sau một thời gian phù hợp. |
| D-07 | Ghi toàn bộ request, response và header để điều tra khi có lỗi. |
| D-08 | Job phải chạy nhanh, retry tự động và không gây ảnh hưởng hệ thống. |
| D-09 | Backup hằng đêm; khi restore chỉ cần kiểm tra file còn mở được. |
| D-10 | QA xác nhận export thành công trước phát hành. |

Không sửa chỉ bằng cách thêm từ “server-side”, “zero trust” hoặc “mã hóa mạnh”. Cần chỉ ra điều kiện cụ thể bị thiếu, rủi ro xuất hiện và thay đổi nào khiến yêu cầu có thể được thực thi/kiểm chứng.

Ví dụ, “worker có quyền đọc toàn bộ ticket” có thể là mô tả quyền hạ tầng trong một thiết kế, nhưng không được trở thành quyền nghiệp vụ của người yêu cầu export. Reviewer phải hỏi đường dữ liệu nào giữ phạm vi người dùng, nó được xác minh ở đâu và lỗi quyền diễn ra thế nào.

## 5. Chuẩn bị và phương pháp review

### 5.1. Chốt phạm vi và baseline

Người điều phối ghi rõ tính năng, endpoint, loại dữ liệu, vai trò, môi trường, phiên bản yêu cầu và các giả định. Gói review cần có mô hình đe dọa, sơ đồ luồng dữ liệu, ma trận quyền, vòng đời artifact, mục tiêu logging/recovery và những quyết định còn mở.

Nếu một đầu vào còn thiếu, ghi mức ảnh hưởng. Thiếu toàn bộ mô hình quyền có thể ngăn kết luận về tính đầy đủ; thiếu một sơ đồ trình bày đẹp chưa chắc ngăn review nếu luồng và ranh giới đã rõ bằng văn bản. Tiếp tục phần có đủ căn cứ và đánh dấu phạm vi chưa thể kết luận.

Phân biệt ba loại câu:

- **Sự kiện đã được xác nhận:** sản phẩm chỉ cho người tạo tải artifact.
- **Giả định cần xác minh:** gateway có thể dừng stream khi quyền đổi.
- **Quyết định còn mở:** thành phần nào quản lý phiên bản phạm vi dữ liệu.

Không biến một giả định thành điều đã bảo đảm bằng cách viết lại nó ở dạng khẳng định.

### 5.2. Review theo hai chiều

**Chiều từ rủi ro xuống:** với từng rủi ro, tìm yêu cầu ngăn chặn/giới hạn, điểm thực thi và cách thử. Chiều này phát hiện lỗ hổng bao phủ.

**Chiều từ yêu cầu lên:** với từng yêu cầu, tìm mục tiêu nghiệp vụ/rủi ro mà nó phục vụ, điều kiện áp dụng, hành vi, vị trí và bằng chứng. Chiều này phát hiện câu thừa, mơ hồ, xung đột hoặc không khả thi.

Hai chiều cần đi cùng nhau. Một bộ câu đều viết rõ vẫn có thể bỏ sót quyền trên endpoint tải xuống; một danh sách rủi ro đầy đủ vẫn chưa đủ nếu các yêu cầu chỉ ghi “phải bảo mật”.

### 5.3. Các tiêu chí đánh giá một yêu cầu

| Tiêu chí | Câu hỏi review | Ví dụ lỗi |
| --- | --- | --- |
| Cần thiết và đúng phạm vi | Nó bảo vệ tài sản/rủi ro nào? | Bắt thêm công nghệ nhưng không liên hệ mục tiêu |
| Rõ chủ thể | Ai phải thực hiện: API, worker, gateway hay storage? | Chỉ viết “kiểm tra quyền” |
| Rõ điều kiện | Áp dụng cho thao tác, vai trò và trạng thái nào? | Chỉ xét tạo job, bỏ download/retry |
| Đơn nghĩa và có ngưỡng | Hai đội có hiểu cùng hành vi không? | “Xóa sớm”, “chạy nhanh”, “log đầy đủ” |
| Đủ hành vi lỗi | Nếu kiểm tra thất bại hoặc phụ thuộc hỏng thì sao? | Mất quyền thì trả link trực tiếp |
| Nhất quán | Có mâu thuẫn yêu cầu khác hoặc nghiệp vụ không? | TTL 7 ngày nhưng chính sách giữ 24 giờ |
| Khả thi | Có cơ chế, năng lực và phụ thuộc đáp ứng được không? | Thu hồi tức thì với link không qua kiểm soát |
| Kiểm chứng được | Có dữ liệu, thao tác và kỳ vọng PASS/FAIL không? | “QA thử export thành công” |
| Truy vết và quản lý đổi | Có mã, nguồn, chủ sở hữu và phiên bản không? | Không biết thay đổi quyền ảnh hưởng ca thử nào |

Một yêu cầu quá dài nên tách thành các mệnh đề có thể kiểm chứng riêng. Ngược lại, tách quá nhỏ nhưng bỏ mất quan hệ giữa chúng cũng có thể làm mất bất biến quan trọng, chẳng hạn “tenant từ server” phải đi cùng “mọi truy vấn và artifact giữ đúng tenant đó”.

## 6. Viết phát hiện review có thể hành động

### 6.1. Cấu trúc một phát hiện

Một nhận xét tốt chỉ đúng vị trí, dẫn căn cứ trong baseline, giải thích hậu quả, đề nghị thay đổi và nêu cách xác nhận đã xử lý. Tránh nhận xét chỉ có “cần bảo mật hơn” hoặc chỉ tên một công nghệ.

Ví dụ đầy đủ:

```text
Finding: F-03
Nguồn: EXPORT-DRAFT-0.1 / D-04
Loại: Thiếu yêu cầu phân quyền trên đối tượng
Quan sát: D-04 cho phép người biết ID job xem trạng thái,
          chưa yêu cầu so tenant và người tạo với principal hiện tại.
Rủi ro: Người dùng có ID của job khác có thể xem metadata hoặc lần tới artifact.
Căn cứ: Quyết định nghiệp vụ chỉ cho người tạo còn đủ quyền xem/tải;
        ID khó đoán không phải bằng chứng cấp quyền.
Đề nghị: Đặc tả kiểm tra tenant + owner trên cả endpoint trạng thái và download;
         thống nhất lỗi công khai cho ID không tồn tại và ID ngoài quyền.
Owner: Đội API
Xác nhận sửa đặc tả: Có mã yêu cầu, vị trí thực thi, hành vi lỗi và ca thử chéo owner/tenant.
Bằng chứng triển khai cần ở bước sau: Request/response và kiểm tra không phát byte artifact.
```

Phát hiện trên chỉ ra thiếu sót trong yêu cầu. Nó chưa khẳng định có lỗ hổng đã khai thác được trong mã đang chạy, vì tình huống chưa cung cấp bằng chứng triển khai.

### 6.2. Mức ảnh hưởng, độ tin cậy và ưu tiên

Không dùng một mức “High” để thay cho mọi lý do. Nên tách:

- **Ảnh hưởng rủi ro:** hậu quả nếu hệ thống thực hiện đúng phần đặc tả đang thiếu/sai, xét dữ liệu và phạm vi bị tác động.
- **Độ tin cậy:** đã thấy câu mâu thuẫn rõ trong yêu cầu, hay mới là giả định về thiết kế cần xác minh.
- **Ưu tiên xử lý/gate:** điểm này phải giải quyết trước chốt yêu cầu, trước thiết kế hay trước phát hành.

Ví dụ, D-05 cho phép fallback trực tiếp khi phân quyền lỗi là một mâu thuẫn rõ với mô hình quyền. Độ tin cậy về lỗi đặc tả cao. Mức khai thác thực tế vẫn phụ thuộc cách link/storage được triển khai. Một đánh giá có trách nhiệm ghi cả hai điều đó.

Lỗi văn phong có thể ưu tiên thấp nếu không đổi nghĩa. Thiếu toàn bộ giới hạn phạm vi tenant là điểm chặn baseline yêu cầu của tính năng này. Khi phân loại, giải thích điều kiện và tác động, không chỉ dựa vào số từ bị thiếu.

### 6.3. Sổ phát hiện mẫu

| Mã | Nguồn | Phát hiện và căn cứ | Rủi ro/loại lỗi | Điều kiện xử lý |
| --- | --- | --- | --- | --- |
| F-01 | D-01, D-10 | “An toàn”, “QA xác nhận thành công” không có điều kiện PASS/FAIL | Thiếu khả năng nghiệm thu, bao phủ R-10 chưa chứng minh | Viết yêu cầu có mã, ma trận truy vết và ca âm/biên |
| F-02 | D-02, D-03 | Tenant từ client và tài khoản worker toàn quyền chưa có hợp đồng giữ phạm vi người yêu cầu | Ảnh hưởng cao: R-01, R-02 | Tenant từ ngữ cảnh tin cậy; xác minh dòng/trường tại API và worker |
| F-03 | D-04 | UUID được dùng như lý do bỏ quyền trên job | Ảnh hưởng cao: R-01, R-04 | Kiểm tra tenant/owner cho trạng thái và tải; thống nhất lỗi |
| F-04 | D-05 | TTL 7 ngày mâu thuẫn 24 giờ; link trực tiếp không đáp ứng thu hồi và fallback bỏ kiểm tra | Ảnh hưởng cao: R-03, R-04, R-09 | Chốt đường tải có kiểm soát, TTL và giới hạn thu hồi 60 giây |
| F-05 | D-06 | Thiếu vị trí mã hóa, quyền khóa, mốc TTL, thời hạn xóa và phạm vi bản sao | R-04, R-08; chưa đủ đặc tả vòng đời | Tách mã hóa/quyền/lifecycle; định nghĩa storage hoạt động và backup |
| F-06 | D-07 | Log mọi header/body chứa token và dữ liệu xuất | Ảnh hưởng cao: R-05 | Danh sách metadata được phép, kiểm thử không có dữ liệu nhạy cảm |
| F-07 | D-08 | Không có quota, deadline, trạng thái retry và điều kiện artifact hoàn chỉnh | R-06, R-07 | Có ngưỡng, phép phân xử nguyên tử và kiểm thử crash/retry |
| F-08 | D-09 | File mở được chưa chứng minh quyền/TTL hiện hành sau restore | Ảnh hưởng cao: R-08 | Cách ly kết quả restore, nguồn quyết định hiện hành, kiểm thử không hồi sinh artifact |

Mỗi dòng trong sổ thật cần thêm owner, ngày mở, hạn xử lý, trạng thái, phiên bản sửa và liên kết bằng chứng. Bảng tóm tắt không thay thế hồ sơ của các phát hiện phức tạp như F-04 hoặc F-08.

## 7. Sửa yêu cầu thành đặc tả kiểm chứng được

Bộ `EXPORT-SEC-1.0-PROPOSED` dưới đây là phương án sửa để thảo luận trong buổi review. Chữ PROPOSED nhắc rằng câu được viết rõ chưa có nghĩa mọi người đã chấp thuận hoặc cơ chế thực hiện đã được chứng minh.

### SEC-01 — Xác thực và vòng đời quyền

API, worker và gateway phải gắn mỗi thao tác với principal/tenant từ nguồn danh tính đã được xác minh. Principal mất trạng thái hoạt động hoặc quyền export không được tiếp tục được cấp truy cập quá 60 giây từ khi quyết định thu hồi có hiệu lực tại nguồn có thẩm quyền.

Thời gian 60 giây bao gồm lan truyền, cache, chu kỳ kiểm tra và timeout. Với stream đang tải, mục tiêu là gateway ngừng phát byte mới trong giới hạn này; không thể thu hồi dữ liệu đã gửi tới client.

**Nghiệm thu:** thu hồi tài khoản/quyền trong khi tạo job, trước download và giữa stream; đo từ mốc quyết định tại nguồn đến lần cuối hệ thống còn cấp truy cập/phát byte. Không chỉ thử đăng xuất ở trình duyệt.

### SEC-02 — Phạm vi tenant, dòng và trường

API phải từ chối thuộc tính điều khiển tenant/owner do client tự thêm vào. Tenant và người tạo được gán từ ngữ cảnh xác thực. Worker phải áp dụng giao giữa bộ lọc hợp lệ và phạm vi được cấp cho principal; quyền hạ tầng của service account không mở rộng quyền nghiệp vụ.

Chỉ xuất các trường `ticket_id`, `title`, `status`, `created_at` trong phiên bản cơ sở. `requester_email` chỉ xuất khi có quyền `ticket:export_sensitive`. Không serialize toàn bộ entity rồi dựa vào UI để ẩn trường.

Bộ lọc chỉ nhận tập trường và toán tử được công bố trong schema; không nhận SQL, tên cột hoặc biểu thức tùy ý. Các giá trị phải đi qua truy vấn có tham số và kiểm tra kiểu/miền giá trị tương ứng.

**Nghiệm thu:** cố thêm tenant/owner, chọn nhóm ngoài quyền, dùng bộ lọc trộn nhóm được phép và không được phép, xuất khi thiếu quyền trường nhạy cảm. Kiểm tra nội dung artifact, không chỉ HTTP trả thành công.

### SEC-03 — Quyền trên job và tham chiếu artifact

Mọi lần xem trạng thái hoặc tải phải kiểm tra tenant và owner của job so với principal hiện tại, đồng thời kiểm tra quyền liên quan còn hiệu lực. UUID hoặc object key không được xem là yếu tố cấp quyền.

ID không tồn tại và ID nằm ngoài phạm vi người gọi đều trả `404 EXPORT_NOT_FOUND` với cấu trúc công khai thống nhất. Không trả tên tenant, owner, bộ lọc hoặc trạng thái thật của job ngoài quyền.

**Nghiệm thu:** dùng ID job của principal khác trong cùng tenant, ID tenant khác và ID không tồn tại cho cả hai endpoint. Không được có redirect hoặc byte artifact ngoài quyền.

### SEC-04 — Artifact chỉ hợp lệ trong phạm vi còn được cấp

Mọi lượt tải, kể cả retry/range request, phải đi qua gateway kiểm tra principal, tenant, owner, TTL và tính còn hiệu lực của phạm vi dữ liệu. Không cấp đường tải trực tiếp có thể bỏ những kiểm tra đó.

Bản thiết kế đề xuất dùng `export_scope_revision` tăng đơn điệu theo tenant khi quyền, thành viên nhóm, phạm vi nhìn thấy hoặc phân loại trường liên quan thay đổi. Job ghi revision của snapshot quyền/dữ liệu đã dùng. Trước cấp quyền tải, gateway so với revision hiện hành; khác revision thì từ chối artifact và yêu cầu tạo lại, không sửa bộ lọc trên một file đã tạo.

Thiết kế phải quy định việc tăng revision cùng thay đổi quyền/phạm vi, cách đọc nhất quán, cache, kiểm tra trong stream và trường hợp nguồn revision lỗi. Cơ chế không đạt tổng 60 giây của SEC-01 thì chưa đáp ứng yêu cầu, dù đã có một trường revision trong database.

**Nghiệm thu:** đổi nhóm của người dùng, chuyển ticket sang nhóm khác, thu hồi quyền trường nhạy cảm và thay đổi chính sách giữa lúc worker chạy/giữa stream. Artifact cũ không tiếp tục cấp dữ liệu ngoài cửa sổ đã chốt.

Revision theo tenant có thể làm hết hiệu lực cả những artifact không bị ảnh hưởng trực tiếp. Đây là đánh đổi để đơn giản hóa bảo đảm; chủ sản phẩm phải chấp nhận chi phí tạo lại. Cơ chế tinh hơn cần chứng minh tương đương, không tự bỏ kiểm tra vì chi phí cao.

### SEC-05 — Hợp đồng đầu ra và tối thiểu hóa dữ liệu

Artifact phải là JSONL với các trường được SEC-02 cho phép. Mỗi dòng được tạo bằng serializer phù hợp, không ghép chuỗi trực tiếp; ký tự xuống dòng trong giá trị được biểu diễn theo quy tắc JSON, không làm xuất hiện bản ghi giả.

Tầng tải phục vụ dưới dạng tệp đính kèm với tên do máy chủ tạo, không nhúng nội dung người dùng thành HTML hoặc đường dẫn. Không dùng tên ticket làm filesystem path/object key. Các định dạng mới cần review riêng về cách ứng dụng tiêu thụ diễn giải dữ liệu.

**Nghiệm thu:** dữ liệu chứa dấu nháy, ký tự xuống dòng, Unicode và chuỗi giống markup vẫn parse đúng thành số bản ghi mong đợi; không xuất cột ngoài allowlist hoặc nội dung từ tenant khác.

### SEC-06 — TTL và vòng đời bản sao

`expires_at = ready_at + 24 giờ`, với thời gian UTC từ máy chủ; tại `now >= expires_at` gateway từ chối tải, không chờ job dọn storage. Retry/tải nhiều lần không gia hạn cùng artifact.

Trong vòng 1 giờ từ `expires_at`, phải xóa object và các version/replica hoạt động do dịch vụ quản lý. Cache phục vụ không được tiếp tục cấp artifact hết hạn. Backup trong tình huống được giữ tối đa 30 ngày theo chính sách riêng, có mã hóa, giới hạn truy cập và quy tắc không đưa artifact cũ trở lại phục vụ.

**Nghiệm thu:** kiểm tra trước biên, đúng biên và sau biên TTL bằng đồng hồ kiểm soát; dừng tác vụ dọn để chứng minh gateway vẫn chặn; sau hạn dọn, kiểm tra các version/replica trong phạm vi quản lý. Không suy từ API xóa thành khẳng định mọi byte trên thiết bị vật lý đã biến mất tức thì.

### SEC-07 — Bảo vệ storage, khóa và đường truyền

Artifact phải được mã hóa khi truyền/lưu và chỉ đọc qua vai trò gateway/worker được cấp theo mục đích. Bucket không công khai. Client, principal thường và role vận hành không liên quan không được đọc trực tiếp artifact hoặc khóa giải mã.

Thiết kế phải chỉ ra khóa/phiên bản, quyền giải mã, rotation, retention và đường truy cập khi phục hồi. Không đặt bí mật trong URL ứng dụng, metadata job, log hoặc manifest công khai.

**Nghiệm thu:** thử truy cập storage bằng danh tính không được phép, cấu hình sai công khai, quyền giải mã sai và rotation; xác minh bản còn được phép dùng vẫn đọc được, người không có quyền không đọc được.

### SEC-08 — Lỗi và audit không rò dữ liệu

Phản hồi lỗi không chứa raw query, stack trace, token, bộ lọc nhạy cảm hoặc giá trị ticket. Audit ghi mã sự kiện, principal/tenant nội bộ, job ID, phiên bản chính sách, kết quả quyết định và mã lỗi; không ghi artifact, header xác thực hoặc URL chứa bí mật.

Log vận hành dùng metadata cố định, giới hạn độ dài; không dùng input tùy ý làm label metric. Bài tập chốt thời gian lưu audit export 90 ngày, giới hạn người đọc và ghi nhận việc truy cập; đây là quyết định nội bộ của tình huống.

**Nghiệm thu:** dùng dữ liệu nhạy cảm giả trong header/body/ticket và kích hoạt lỗi; đối chiếu response, log, audit và metric. Chuỗi có CR/LF không tạo bản ghi log giả, dữ liệu không xuất hiện ngoài danh sách cho phép.

### SEC-09 — Giới hạn tài nguyên và kết quả đầy đủ

Mỗi tenant có tối đa 2 job đang chạy và 20 job chờ; phân xử ngưỡng phải có hiệu lực trên toàn cụm, không tăng theo số replica. Hết chỗ nhận thêm trả `429 EXPORT_CAPACITY_EXCEEDED`.

Job chờ tối đa 15 phút từ khi được nhận; job đang chạy tối đa 5 phút từ lúc worker nhận quyền thực thi. Hết deadline chuyển sang trạng thái thất bại có mã riêng. Artifact tối đa 100000 dòng và `100 * 1024 * 1024` byte JSONL chưa nén, tính cả dấu phân tách dòng.

Vượt một ngưỡng phải dừng, không publish artifact dở dang và không báo thành công với dữ liệu bị cắt. Object tạm bị lỗi được xóa trong 1 giờ từ lúc job kết thúc/thất bại.

**Nghiệm thu:** thử đúng ngưỡng và vượt một đơn vị cho dòng/byte, cạnh tranh trên nhiều worker/instance, job chờ quá lâu và xử lý bị treo. Đối chiếu số job thực tế và số artifact có thể tải.

### SEC-10 — Retry, idempotency và công bố artifact nguyên tử

Tạo job phải yêu cầu idempotency key theo hợp đồng đã định. Khóa có phạm vi tenant–principal–endpoint, được giữ 24 giờ từ lần tạo được cam kết. Cùng khóa/cùng dữ liệu chuẩn hóa trả cùng job; khác dữ liệu trả `409 IDEMPOTENCY_CONFLICT`. Quyền hiện tại vẫn được kiểm tra khi trả kết quả cũ.

Worker dùng quyền sở hữu/lease để ngăn nhiều lần thực thi cùng publish một kết quả. Chỉ chuyển `READY` sau khi object hoàn chỉnh, manifest hợp lệ và snapshot phạm vi được chấp nhận. Job lỗi/crash không có artifact được tải chỉ vì object tạm đã tồn tại.

**Nghiệm thu:** gửi đồng thời cùng key, đổi nội dung cùng key, crash trước/sau khi ghi object và trước/sau commit trạng thái. Retry không tạo thêm job hay công bố kết quả chưa hoàn chỉnh.

Hợp đồng API chi tiết phải chốt định dạng key, cách chuẩn hóa bộ lọc, lỗi thiếu key và cách xử lý reservation đang chạy. Nếu các điểm đó còn mở, ghi action cụ thể thay vì mặc định framework đã giải quyết.

### SEC-11 — Phụ thuộc lỗi không được trở thành nhánh bỏ quyền

Khi không xác minh được danh tính, quyền hiện tại, scope revision hoặc khả năng giải mã bắt buộc, hệ thống không được cấp artifact hoặc public link để duy trì khả dụng.

Nếu đã xác minh người gọi không có quyền thì trả lỗi quyền theo hợp đồng. Nếu không thể xác minh do phụ thuộc lỗi thì trả lỗi khả dụng như `503 AUTHORIZATION_UNAVAILABLE` hoặc dừng stream theo cơ chế đã công bố; không gán mọi sự cố phụ thuộc thành input sai.

**Nghiệm thu:** ngắt phụ thuộc trước download và giữa stream, gây timeout/response lỗi/cached decision quá hạn. Không có redirect tới storage, không có byte mới được phát sau cửa sổ thu hồi cho phép.

### SEC-12 — Restore không hồi sinh quyền và artifact

Sau restore, job/artifact cũ phải ở trạng thái cách ly và không thể tải cho tới khi đã áp dụng nguồn danh tính/quyết định thu hồi hiện hành và chính sách lifecycle. Phiên bản revision lấy từ backup không tự được coi là trạng thái quyền mới nhất.

Trong phương án của bài, artifact được restore không phục vụ lại; trạng thái công khai cho owner hợp lệ là `410 EXPORT_REGENERATION_REQUIRED`. Người dùng muốn xuất lại phải tạo job mới theo quyền hiện tại. Không thay `ready_at` để gia hạn artifact cũ.

**Nghiệm thu:** restore điểm trước khi hết hạn/thu hồi quyền, giữ nguồn quyết định hiện hành ở mốc mới hơn; artifact cũ vẫn không tải được và không lộ job cho người ngoài quyền. Kiểm thử cả trường hợp chưa lấy được nguồn hiện hành: phạm vi đó vẫn bị chặn.

### SEC-13 — Phiên bản, quan sát và bằng chứng

Yêu cầu, schema bộ lọc, chính sách quyền, API, worker và bộ kiểm thử phải truy vết được đến phiên bản baseline. Theo dõi job lỗi theo mã, quota, artifact quá hạn dọn, lỗi quyền/phụ thuộc và độ trễ thu hồi.

Thay đổi role, trường xuất, đường tải, cache, storage, TTL, cách restore hoặc phạm vi worker phải kích hoạt đánh giá tác động và chạy lại ca liên quan trước kết luận phát hành.

**Nghiệm thu:** hồ sơ chỉ được phiên bản triển khai và ca đã chạy; mô phỏng một thay đổi quyền để thấy cảnh báo/metric phù hợp. Không coi báo cáo kiểm thử phiên bản cũ là bằng chứng cho hành vi đã thay đổi.


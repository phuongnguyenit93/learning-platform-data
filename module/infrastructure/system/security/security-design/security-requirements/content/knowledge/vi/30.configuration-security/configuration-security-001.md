# Secure default configuration

## 1. Cấu hình mặc định an toàn là một yêu cầu về hành vi

Trong chương **Configuration security**, secure default configuration là nguyên tắc hệ thống phải bắt đầu và vận hành với các lựa chọn hạn chế rủi ro khi người triển khai chưa cung cấp cấu hình tùy chọn. Tính an toàn không được phụ thuộc vào việc người vận hành nhớ bật đủ mọi công tắc bảo vệ.

Ví dụ, thiếu một biến môi trường không được làm API nhạy cảm chuyển sang không cần xác thực. Không cấu hình danh sách người được chia sẻ không được hiểu ngầm là mọi người đều được đọc. Không tìm thấy khóa mã hóa không được khiến dữ liệu mới được ghi dạng rõ để ứng dụng tiếp tục chạy.

Tuy nhiên, không phải mọi field đều có một giá trị mặc định hợp lệ. Khi thiếu thông tin bắt buộc như nguồn danh tính, khóa hoặc miền tin cậy, hành vi an toàn có thể là không kích hoạt chức năng liên quan cho tới khi điều kiện được đáp ứng.

Trong đặc tả yêu cầu bảo mật, câu “cấu hình phải secure by default” cần chuyển thành:

**Rủi ro cấu hình → giá trị mặc định hoặc điều kiện bắt buộc → nguồn có thẩm quyền → hành vi lỗi → tiêu chí kiểm chứng.**

Sau bài học, người học cần có khả năng:

- Phân biệt mặc định an toàn, cấu hình bắt buộc và bất biến bảo mật.
- Viết quy tắc cho giá trị thiếu, rỗng, sai kiểu, sai môi trường hoặc bị ghi đè.
- Đặc tả việc kiểm tra, kích hoạt, cập nhật và rollback cấu hình.
- Gắn yêu cầu với kiểm thử cài đặt mới, nâng cấp và trạng thái vận hành thực tế.

Các giá trị, thời hạn và mô hình trong bài là ví dụ thiết kế. Chúng cần được xác nhận theo tác động nghiệp vụ, mô hình đe dọa và kiến trúc của hệ thống thực tế.

## 2. Phân biệt các khái niệm liên quan

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| Secure defaults | Khi chưa cấu hình tùy chọn, hệ thống chọn hành vi nào? | Debug tắt; không tự mở chia sẻ công khai |
| Required configuration | Thiếu gì thì không có đủ điều kiện để hoạt động? | Nguồn xác thực và tham chiếu khóa bắt buộc |
| Security invariant | Điều kiện nào mọi cấu hình được chấp nhận đều phải giữ? | API được bảo vệ không được bỏ kiểm tra quyền |
| Baseline | Tập điều kiện và giá trị chuẩn cho một phạm vi triển khai | Baseline production có phiên bản |
| Hardening | Điều chỉnh bổ sung để giảm bề mặt tấn công trong bối cảnh cụ thể | Tắt module không dùng, thu hẹp quyền vận hành |
| Fail-secure behavior | Khi kiểm soát hoặc cấu hình lỗi, quyền được xử lý thế nào? | Không cấp quyền mới từ policy không xác định |
| Configuration drift | Hệ thống đang chạy lệch khỏi trạng thái được chấp nhận ra sao? | Một replica bật lại endpoint chẩn đoán |

### 2.1. Giá trị mặc định không thay thế bất biến

Một field có default `authentication.required = true` nhưng bất kỳ người gọi nào cũng đổi được thành `false` vẫn chưa tạo kiểm soát đầy đủ.

Với một API thuộc phạm vi bắt buộc xác thực, thiết kế có thể coi “luôn yêu cầu xác thực” là bất biến production. Khi đó cấu hình ghi đè trái điều kiện phải bị từ chối, thay vì chỉ cảnh báo rằng người dùng đã chọn khác default.

Ngược lại, một endpoint trạng thái tối thiểu được policy cho phép công khai có thể là ngoại lệ được thiết kế ngay từ đầu. Không cần đặt mọi endpoint vào cùng một quy tắc thiếu phạm vi.

### 2.2. Không phải cứ thiếu cấu hình là tắt toàn bộ hệ thống

Cần phân loại tác động:

- Thiếu cấu hình cho một tính năng tùy chọn: không kích hoạt tính năng đó.
- Thiếu điều kiện của một luồng nhạy cảm: không phục vụ luồng đó.
- Cấu hình nền tảng không hợp lệ: không chuyển sang trạng thái phục vụ chính.
- Thành phần phụ trợ lỗi nhưng snapshot tin cậy còn hiệu lực: có thể tiếp tục trong phạm vi đã đặc tả.

Quyết định phải bảo vệ an toàn và đáp ứng mục tiêu phục vụ đã thống nhất. Không dùng “fail closed” như một nhãn thay cho thiết kế hành vi lỗi của từng luồng.

## 3. Bắt đầu từ các tình huống cấu hình sai

| Tình huống | Rủi ro | Điều cần đặc tả |
|---|---|---|
| Cài đặt mới chưa có biến môi trường | API nhạy cảm hoạt động không có xác thực | Trạng thái chưa được cấp cấu hình và điều kiện kích hoạt |
| Copy cấu hình phát triển sang production | Debug, tài khoản mẫu hoặc kết nối không kiểm tra peer bị bật | Baseline theo môi trường và kiểm tra bất biến |
| Gõ sai tên thuộc tính | Một thiết lập quan trọng bị bỏ qua | Schema và quy tắc với field không biết |
| Giá trị rỗng hoặc sai kiểu | Chuyển sang một fallback quá rộng | Phân biệt thiếu, rỗng, null và giá trị không hợp lệ |
| Nguồn ưu tiên cao bị sửa | Ghi đè policy bằng một flag không có thẩm quyền | Provenance, phân quyền và thứ tự hợp nhất |
| Cập nhật một phần | Một instance dùng khóa mới với policy cũ hoặc ngược lại | Snapshot nhất quán và kích hoạt nguyên tử |
| Dùng bản cũ sau lỗi | Khôi phục lại quyền đã bị thu hồi | Hạn hiệu lực, trạng thái thu hồi và chống rollback |
| Nâng cấp phần mềm | Default mới làm thay đổi mức bảo vệ | Migration cấu hình và kiểm thử tương thích |
| Endpoint chẩn đoán lộ cấu hình | Secret và cấu trúc hệ thống bị đọc | Redaction, quyền truy cập và dữ liệu được công bố |

Mô hình đe dọa cần bao gồm người dùng không có quyền cấu hình, người vận hành có thể nhầm, tài khoản quản trị bị chiếm và các pipeline triển khai có khả năng đưa dữ liệu vào runtime.

Không chỉ tìm cấu hình sai trong một file. Kết quả thực tế có thể đến từ default trong code, biến môi trường, command line, secret reference, cấu hình từ xa và feature flag.

## 4. Những nhóm mặc định cần được định nghĩa

### 4.1. Xác thực, phân quyền và tài khoản khởi tạo

Các hành vi mặc định có thể gồm:

- Luồng nhạy cảm bắt buộc xác thực, từ chối khi chưa xác định được chủ thể.
- Quyền không được cấp rõ thì không được suy ra là cho phép.
- Tài khoản mẫu, credential dùng chung và chế độ tự tạo admin không có kiểm soát không tồn tại ở production.
- Tính năng chia sẻ công khai cần được kích hoạt có chủ đích theo policy.
- Thiếu nguồn danh tính không chuyển ứng dụng sang anonymous.

Khởi tạo quản trị viên cần một đường provisioning được bảo vệ và có vòng đời rõ ràng. Không đưa một mật khẩu mặc định giống nhau vào mọi bản cài hoặc in secret ra log rồi coi đó là giải pháp onboarding an toàn.

Nếu ứng dụng chưa được provision, có thể chỉ cung cấp trạng thái tối thiểu không tiết lộ dữ liệu và một cơ chế thiết lập có kiểm soát. Trạng thái đó không được có API quản trị nhạy cảm mở cho người đầu tiên trên mạng tự nhận quyền.

### 4.2. Giao tiếp và bảo vệ dữ liệu

Mặc định phải giữ kiểm tra đối tác theo profile đã chọn. Không tự fallback sang plaintext, “trust all” hoặc bỏ kiểm tra danh tính vì endpoint chưa được cấu hình đầy đủ.

Nếu luồng yêu cầu mã hóa dữ liệu, tham chiếu khóa và quyền dùng khóa là điều kiện bắt buộc. Không tự thay bằng một khóa cố định công khai hoặc phát sinh khóa tạm mới mỗi lần restart rồi làm dữ liệu cũ không đọc được.

Chính sách có thể yêu cầu nhiều kiểm soát khác nhau cho từng đường truyền và loại dữ liệu. Cần ghi rõ profile, nguồn khóa và phạm vi, không chỉ một field `encryption=true`.

### 4.3. Bề mặt tấn công và tài nguyên

Debug, endpoint quản trị, plugin và tính năng không cần thiết nên không tự hoạt động khi chưa được cho phép.

Network exposure phải có phạm vi rõ. Không coi một network nội bộ là bằng chứng mọi caller đáng tin; cũng không mặc định mở listener nhạy cảm trên mọi giao diện để đơn giản hóa khởi động.

Các cận tài nguyên phải có giá trị hữu hạn, đơn vị và miền hợp lệ. Ví dụ `0` không được ngầm nghĩa là không giới hạn nếu schema không cho phép hành vi đó.

### 4.4. Audit và dữ liệu cấu hình được hiển thị

Logging cần có mức bảo vệ và redaction phù hợp ngay từ đầu. Không mặc định dump toàn bộ cấu hình, token hoặc secret khi startup lỗi.

Đối với thao tác nhạy cảm cần bằng chứng bền vững, lỗi đường audit phải có chính sách. Có thể dùng lưu đệm bền vững có cận hoặc dừng thao tác liên quan theo thiết kế; không âm thầm tắt audit để tiếp tục cấp quyền.

## 5. Định nghĩa hợp đồng cấu hình trước khi chọn default

Mỗi thuộc tính ảnh hưởng đến bảo mật cần một hợp đồng đủ rõ để đội phát triển, vận hành và kiểm thử hiểu giống nhau. Không chỉ liệt kê tên và giá trị gợi ý.

| Thành phần hợp đồng | Nội dung cần xác định |
|---|---|
| Định danh và phạm vi | Tên field, luồng chịu ảnh hưởng, môi trường và phiên bản schema |
| Miền giá trị | Kiểu dữ liệu, đơn vị, giới hạn, quan hệ với các field khác |
| Trạng thái đầu vào | Phân biệt không có field, chuỗi rỗng, `null`, giá trị sai và giá trị hợp lệ |
| Mặc định hoặc bắt buộc | Giá trị được dùng khi thiếu, hoặc điều kiện khiến chức năng chưa được kích hoạt |
| Thẩm quyền | Nguồn nào được cấp hoặc ghi đè field; ai có quyền sửa nguồn đó |
| Bất biến | Điều kiện không thể bị cấu hình hợp lệ vô hiệu hóa trong phạm vi đã chọn |
| Thời điểm áp dụng | Startup, reload hay cần triển khai lại; cơ chế nhất quán giữa các field |
| Hành vi lỗi | Từ chối bản cập nhật, cô lập tính năng hay không sẵn sàng phục vụ |
| Bằng chứng | Mã lỗi, bản ghi audit, revision hiệu lực và phép kiểm thử |

### 5.1. Ví dụ hợp đồng cho một tính năng chia sẻ

Giả sử dịch vụ lưu tài liệu theo tenant có thuộc tính `sharing.publicEnabled`:

- Kiểu dữ liệu là boolean; khi không có field, giá trị là `false`.
- Chuỗi `"false"`, chuỗi rỗng và `null` không phải boolean hợp lệ; bản cấu hình chứa chúng bị từ chối.
- Chỉ policy đã được phê duyệt cho tenant mới có thể yêu cầu bật tính năng.
- `true` chỉ làm xuất hiện khả năng tạo chia sẻ công khai; từng tài liệu vẫn cần thao tác cấp chia sẻ của chủ thể có quyền.
- Trạng thái thiếu policy của tenant giữ tính năng tắt, không kế thừa một policy cho phép từ tenant khác.
- Bản cập nhật không hợp lệ không thay đổi revision đang hiệu lực.
- Kiểm thử phải quan sát truy cập tài liệu qua API, không chỉ kiểm tra giá trị trong bộ nhớ.

Như vậy, “mặc định tắt” không đồng nghĩa “mọi đối tượng đều trở thành công khai sau khi bật”. Yêu cầu phải mô tả cả cấu hình lẫn quyết định phân quyền tại thời điểm truy cập.

### 5.2. Thông số minh họa cần có cơ sở

Một baseline có thể chọn kích thước request tối đa là 1 MiB. Yêu cầu cần định nghĩa 1 MiB bằng 1.048.576 byte, lớp nào đo và hành vi khi vượt giới hạn. Với ví dụ trong bài, giới hạn này áp dụng cho API tài liệu dạng JSON không nhận nội dung nén; luồng upload lớn có hợp đồng riêng. Yêu cầu vượt giới hạn bị từ chối trước khi xử lý nghiệp vụ và không tạo tài liệu.

Con số này không phải mức an toàn chung cho mọi hệ thống. Nhóm thiết kế cần liên kết nó với kích thước dữ liệu hợp lệ, năng lực tài nguyên và kịch bản lạm dụng đã xác định. Nếu cho phép nội dung nén, còn phải đặc tả giới hạn sau giải nén và cận tài nguyên giải nén.

## 6. Bộ yêu cầu mẫu có thể truy vết

Xét dịch vụ lưu tài liệu nội bộ đa tenant. Tài liệu mặc định chỉ được truy cập theo quyền trong tenant. Hai endpoint trạng thái chỉ công bố thông tin tối thiểu; API tài liệu và API quản trị thuộc phạm vi bắt buộc bảo vệ.

Các rủi ro chính của ví dụ:

- **R-CFG-01:** thiếu hoặc sai cấu hình làm luồng được bảo vệ mở cho truy cập ẩn danh.
- **R-CFG-02:** ghi đè từ nguồn không có thẩm quyền làm suy yếu kiểm soát.
- **R-CFG-03:** cập nhật một phần, drift hoặc rollback làm dùng policy không được chấp nhận.
- **R-CFG-04:** secret hoặc dữ liệu nhạy cảm bị lộ qua cấu hình và chẩn đoán.
- **R-CFG-05:** thiếu giới hạn tài nguyên hoặc audit khiến khó ngăn chặn, điều tra lạm dụng.

Một tập yêu cầu minh họa có thể được viết như sau:

| ID và rủi ro | Yêu cầu quan sát được | Tiêu chí chấp nhận chính |
|---|---|---|
| CFG-01 · R-CFG-01 | Bản cài mới không có thông tin nguồn danh tính hợp lệ không được đưa API tài liệu và quản trị vào trạng thái phục vụ. | Không đọc, ghi hoặc quản trị tài liệu được; readiness báo chưa sẵn sàng với mã lý do ổn định; không xuất secret. |
| CFG-02 · R-CFG-01 | Ở production, mọi đường vào API tài liệu phải xác thực chủ thể và kiểm tra quyền đối với tenant, tài nguyên, hành động. | Thiếu danh tính bị từ chối; danh tính không có quyền cũng bị từ chối; không có tác dụng phụ nghiệp vụ. |
| CFG-03 · R-CFG-01, R-CFG-02 | Chia sẻ công khai mặc định tắt; cấu hình bật chỉ được chấp nhận từ policy tenant có thẩm quyền và vẫn yêu cầu cấp chia sẻ cho từng tài liệu. | Thiếu field giữ tính năng tắt; ghi đè trái thẩm quyền bị từ chối; bật tính năng không làm tài liệu hiện có tự công khai. |
| CFG-04 · R-CFG-02 | Cấu hình bảo mật phải được kiểm tra kiểu, tên field, phạm vi giá trị và quan hệ giữa các field trước khi kích hoạt. | Field không biết trong schema, khóa trùng, boolean dạng chuỗi, giá trị rỗng hoặc xung đột đều bị từ chối; không kích hoạt một phần. |
| CFG-05 · R-CFG-02 | Nguồn có ưu tiên cao chỉ được ghi đè các field nằm trong danh sách được phép của nguồn đó. | Thử dùng biến môi trường hay command line để tắt xác thực bị từ chối; có bằng chứng nguồn và mã lý do. |
| CFG-06 · R-CFG-01, R-CFG-02 | Production không chấp nhận debug và không bỏ kiểm tra danh tính đối tác trên các kết nối thuộc profile bảo vệ. | Bật debug hoặc yêu cầu bỏ xác minh đối tác làm cấu hình bị từ chối; không tự hạ xuống giao tiếp không được profile cho phép. |
| CFG-07 · R-CFG-01, R-CFG-04 | Ghi dữ liệu thuộc phạm vi mã hóa yêu cầu tham chiếu khóa hợp lệ và quyền sử dụng khóa. | Khi thiếu điều kiện này, không ghi dữ liệu mới dạng rõ và không tạo dữ liệu dở dang; không đưa vật liệu khóa vào log. |
| CFG-08 · R-CFG-03 | Một bản cập nhật chỉ được kích hoạt như một snapshot hoàn chỉnh đã qua kiểm tra; request dùng một revision nhất quán. | Không quan sát được request trộn policy mới với cấu hình cũ; cập nhật bị từ chối giữ nguyên revision trước đó nếu revision ấy còn được phép sử dụng. |
| CFG-09 · R-CFG-03 | Hết hạn hoặc bị thu hồi làm snapshot mất quyền sử dụng; rollback phải qua cùng cơ chế thẩm quyền và kiểm tra hiện hành. | Bản bị thu hồi không trở lại hiệu lực dù còn nằm trong cache hoặc được yêu cầu khôi phục. |
| CFG-10 · R-CFG-04 | Giao diện chẩn đoán cấu hình chỉ dành cho vai trò vận hành được cấp quyền và chỉ trả các field nằm trong danh sách công bố. | Token, mật khẩu, vật liệu khóa và thông tin tham chiếu bị phân loại nhạy cảm không xuất hiện trong phản hồi hay log. |
| CFG-11 · R-CFG-05 | API JSON trong phạm vi ví dụ có giới hạn request mặc định 1 MiB và miền cấu hình được chấp nhận từ 1 byte đến 1 MiB. | Giá trị ngoài miền bị từ chối; request 1.048.577 byte bị chặn trước xử lý nghiệp vụ và không tạo tài liệu. |
| CFG-12 · R-CFG-03, R-CFG-05 | Mọi lần đề nghị đổi cấu hình có kết quả audit; kích hoạt cần bản ghi ý định bền vững gắn revision và kết quả được đối soát. | Mất khả năng lưu bản ghi ý định làm bản cập nhật không được kích hoạt; sau sự cố xác định được revision nào thực sự đã hoạt động. |

Các mã CFG chỉ là định danh của bài học, không phải tuyên bố tuân thủ một tiêu chuẩn bên ngoài. Trong dự án, mỗi yêu cầu cần thêm chủ sở hữu, phiên bản, phạm vi ngoại lệ nếu có và liên kết đến kiến trúc, mã kiểm thử.

Đối với CFG-02, đặc tả giao thức có thể quy định HTTP `401` cho yêu cầu thiếu thông tin xác thực hợp lệ và `403` cho chủ thể đã xác thực nhưng thiếu quyền. Nếu dùng `404` để giảm lộ sự tồn tại của tài nguyên, quyết định đó phải được ghi rõ và kiểm thử nhất quán. Mục tiêu bắt buộc vẫn là không cho truy cập trái quyền và không tạo tác dụng phụ.

CFG-11 cũng không thể thay thế các yêu cầu về tần suất, số kết nối hoặc chi phí xử lý. Kích thước hữu hạn là một điều kiện của baseline; các cận còn lại cần xuất phát từ mô hình tài nguyên và tấn công của dịch vụ.

## 7. Ví dụ cấu hình cùng ý nghĩa bảo mật

Ví dụ dưới đây dùng schema tự định nghĩa để minh họa đặc tả, không phải cú pháp sẵn có của một framework. Các địa chỉ và tham chiếu đều là dữ liệu mẫu.

```yaml
schemaVersion: 1
revision: "cfg-2026-11-27-001"
targetEnvironment: production

authentication:
  required: true
  issuer: "https://identity.example.invalid"
  audience: "internal-document-service"

authorization:
  defaultDecision: deny
  tenantIsolationRequired: true

sharing:
  publicEnabled: false

transport:
  profile: verified-peer
  verifyPeerIdentity: true
  allowPlaintextFallback: false

dataProtection:
  encryptionRequired: true
  keyRef: "secret-ref:documents-data-key"

diagnostics:
  debugEnabled: false
  configView: operator-allowlist

apiLimits:
  jsonRequestMaxBytes: 1048576

audit:
  configurationChangesRequired: true
  activationRequiresDurableIntent: true
```

Hợp đồng của schema cần phân loại các field:

| Nhóm | Field minh họa | Khi không được cấp |
|---|---|---|
| Metadata bắt buộc | `schemaVersion`, `revision`, `targetEnvironment` | Từ chối snapshot vì không xác định được hợp đồng, danh tính phiên bản hoặc đích áp dụng |
| Điều kiện vận hành bắt buộc | `authentication.issuer`, `authentication.audience`, `dataProtection.keyRef` | Không phục vụ luồng cần các điều kiện đó cho tới khi có cấu hình và phụ thuộc hợp lệ |
| Giá trị mặc định | `sharing.publicEnabled=false`, `diagnostics.debugEnabled=false`, `apiLimits.jsonRequestMaxBytes=1048576` | Điền default đã công bố của phiên bản schema |
| Bất biến production | `authentication.required=true`, `authorization.defaultDecision=deny`, `authorization.tenantIsolationRequired=true` | Bổ sung giá trị bắt buộc nếu field bị thiếu; từ chối nếu giá trị cung cấp trái bất biến |
| Bất biến của profile bảo vệ | Các field transport, yêu cầu mã hóa, chế độ xem cấu hình và hai field audit trong ví dụ | Bổ sung giá trị được baseline ấn định; từ chối cấu hình trái profile áp dụng |

Trong baseline production này, `sharing.publicEnabled=true` cần thỏa điều kiện cấp quyền riêng đã mô tả ở CFG-03; `diagnostics.debugEnabled=true` luôn bị từ chối. Hai field cùng có default `false` nhưng khả năng ghi đè khác nhau.

Không dùng field `targetEnvironment` làm bằng chứng duy nhất về môi trường. Đích triển khai cần được đối chiếu với danh tính deployment từ một nguồn kiểm soát độc lập. Người sửa file không được ghi `development` để làm một workload production bỏ qua baseline.

Tương tự, sự tồn tại của `keyRef` chỉ xác nhận một tham chiếu về mặt cấu trúc. Hệ thống còn phải xác minh tham chiếu thuộc phạm vi được phép, phân giải đúng nguồn khóa và có quyền thực hiện thao tác cần thiết. Thông báo lỗi chỉ công bố mã lý do và thông tin đã được cho phép.

### 7.1. Thuật toán chuẩn hóa và kiểm tra

Một quy trình khái niệm có thể viết bằng mã giả:

```text
buildCandidate(sources, trustedDeploymentContext):
    raw = parseStrict(sources)               # từ chối khóa trùng
    verifySourcesAndAllowedOverrides(raw)
    requireSupportedSchemaAndMetadata(raw)
    rejectUnknownFieldsAndInvalidTypes(raw)
    candidate = applySchemaDefaults(raw)
    validateRangesAndCrossFieldConstraints(candidate)
    enforceDeploymentBaseline(candidate, trustedDeploymentContext)
    verifyRequiredDependencies(candidate)
    return immutableSnapshot(candidate)

activate(candidate):
    requireCurrentAuthorization(candidate)
    requireNotExpiredOrRevoked(candidate)
    persistDurableActivationIntent(candidate.revision)
    atomicallyPublish(candidate)
    persistOrReconcileActivationResult(candidate.revision)
```

Đây là trình tự trách nhiệm, không quy định một thư viện cụ thể. Bản triển khai phải bảo đảm không có đường kích hoạt khác bỏ qua các bước kiểm tra.

Kiểm tra nguồn diễn ra trước khi điền default để biết field nào thực sự do từng nguồn cung cấp. Bước kiểm tra kiểu cũng không được biến một giá trị rỗng hoặc sai kiểu thành “thiếu field” rồi áp dụng default. Default chỉ áp dụng cho trường hợp thiếu mà hợp đồng đã cho phép.

Một lần kiểm tra phụ thuộc tại startup không bảo đảm phụ thuộc sẽ luôn hoạt động. Mỗi thao tác runtime vẫn phải tuân thủ yêu cầu sử dụng danh tính, quyền, khóa và trạng thái thu hồi tương ứng.

## 8. Nguồn cấu hình, ghi đè và vòng đời kích hoạt

### 8.1. Ưu tiên không đồng nghĩa thẩm quyền

Có thể có chuỗi hợp nhất `default → file triển khai → cấu hình từ xa`. Nhưng “đứng sau thắng” chỉ giải quyết xung đột thứ tự, không trả lời nguồn đứng sau có quyền thay field đó hay không.

Đặc tả nên có ma trận như sau:

| Nguồn | Phạm vi được phép trong ví dụ | Điều kiện kiểm soát |
|---|---|---|
| Default gắn với bản phát hành | Giá trị khởi điểm theo schema | Có phiên bản, được kiểm thử cùng phần mềm |
| Cấu hình deployment được quản lý | Định danh dịch vụ, nguồn danh tính và tham chiếu khóa đúng phạm vi | Kiểm soát quyền sửa, kiểm tra đích triển khai và lưu lịch sử |
| Policy tenant có thẩm quyền | Cho phép tính năng chia sẻ trong tenant đã xác định | Xác minh nguồn, tenant, phạm vi field và hiệu lực |
| Biến môi trường hoặc command line | Chỉ các field có trong danh sách được phép | Không được hạ bất biến; ghi nhận nguồn trong kết quả chuẩn hóa |
| Giao diện vận hành | Đề nghị thay đổi theo vai trò | Xác thực, phân quyền, kiểm tra candidate và audit trước kích hoạt |

Nếu cùng một field được cấp nhiều lần trong một nguồn, cần từ chối thay vì phụ thuộc hành vi parser. Nếu nhiều nguồn hợp lệ được phép cấp cùng field, thứ tự phải được công bố và kiểm thử.

Với danh sách quyền, tập tenant hoặc mạng được phép, cần ghi rõ thao tác ghi đè là thay toàn bộ hay hợp nhất. Ví dụ, xóa một phần tử khỏi danh sách mới sẽ không thu hồi quyền nếu bộ hợp nhất vẫn giữ phần tử cũ. Trong ví dụ này, danh sách được cấp bởi nguồn có thẩm quyền thay toàn bộ danh sách trước đó, sau đó vẫn phải kiểm tra phạm vi.

### 8.2. Cài mới và reload có hành vi khác nhau

Khi cài mới, nếu chưa có snapshot hợp lệ thì không có bản tin cậy trước đó để tiếp tục dùng. API được bảo vệ phải giữ trạng thái chưa sẵn sàng. Endpoint liveness tối thiểu có thể vẫn phản hồi để phản ánh tiến trình còn hoạt động; readiness phải phản ánh điều kiện phục vụ. Các endpoint này không trả chi tiết cấu hình hoặc lý do chứa dữ liệu nhạy cảm.

Khi reload, một candidate không hợp lệ phải bị từ chối trước khi thay snapshot đang chạy. Chỉ được tiếp tục dùng snapshot cũ nếu nó còn được chính sách cho phép sử dụng, chưa hết hạn và chưa bị thu hồi. Không tự khôi phục default của từng field thất bại để tạo ra một snapshot pha trộn.

Tách các hành động sau trong thiết kế:

1. Thu nhận candidate và xác định nguồn.
2. Kiểm tra schema, thẩm quyền, baseline và phụ thuộc.
3. Ghi ý định kích hoạt bền vững.
4. Công bố snapshot mới như một đơn vị nhất quán.
5. Ghi kết quả, công bố revision đã hiệu lực và theo dõi sự hội tụ của các instance.

Mỗi request giữ một snapshot cấu hình nhất quán cho phần xử lý thuộc phạm vi đặc tả. Các kiểm tra động như thu hồi quyền khẩn cấp có thể cần đánh giá lại trong request; nếu có, phải quy định rõ điểm kiểm tra và tác dụng phụ được phép.

### 8.3. Nhiều instance, drift và thu hồi

Kích hoạt nguyên tử trong một process không bảo đảm cả cụm chuyển revision cùng lúc. Yêu cầu triển khai cần xác định cửa sổ cùng tồn tại của các revision và hành vi khi một instance không nhận được policy mới.

Ví dụ, một yêu cầu thu hồi khẩn cấp có thể đặt thời hạn áp dụng là 60 giây kể từ khi lệnh thu hồi được chấp nhận. Khi đó cần có:

- Revision mục tiêu và bằng chứng thời điểm lệnh được chấp nhận.
- Cơ chế xác định instance còn giữ revision đã thu hồi.
- Cách ngừng phục vụ luồng chịu ảnh hưởng ở instance không cập nhật kịp.
- Cận độ trễ phát hiện, truyền tin và loại instance khỏi đường phục vụ để tổng thời gian không vượt 60 giây.
- Kiểm thử khi instance mất kết nối, khởi động lại hoặc còn nhận request qua đường vào khác.

Instance bị cô lập không thể tự biết ngay mọi lệnh thu hồi mới. Nếu chọn cơ chế lease, cần giới hạn thời gian được dùng snapshot mà không tái xác nhận với nguồn có thẩm quyền, dùng cơ sở thời gian đáng tin cậy và tính cả độ trễ loại instance khỏi phục vụ. Không tự gia hạn lease khi mất kết nối, không đặt lại hạn khi restart và không coi cache còn tồn tại là bằng chứng còn hiệu lực. Một lựa chọn khác là chặn tại điểm thực thi độc lập vẫn nhận được lệnh thu hồi; mọi đường vào phải chịu kiểm soát tương ứng.

Đây là thời hạn minh họa cần thương lượng theo rủi ro và kiến trúc. Nếu kiến trúc chưa bảo đảm thời hạn đó, yêu cầu còn là một khoảng trống thiết kế; không thể chỉ thêm metric rồi coi đã đáp ứng.

Phát hiện drift cần so sánh trạng thái **thực sự có hiệu lực** với baseline và revision được phép, bao gồm từng instance. Có file đúng trong kho mã không chứng minh process đang dùng file đó.

### 8.4. Audit, khôi phục và nâng cấp

Audit thay đổi cấu hình nên ghi chủ thể, phạm vi, nguồn, revision trước/sau, kết quả, thời gian và mã lý do. Chỉ ghi tên field hay phần chênh lệch đã được lọc; không ghi toàn bộ giá trị bí mật.

Một cách đáp ứng CFG-12 là lưu ý định kích hoạt bền vững trước khi đổi snapshot, rồi ghi kết quả sau đó. Nếu tiến trình dừng giữa hai bước, cơ chế khôi phục phải đối soát revision thực sự hiệu lực với ý định chưa kết thúc. Một ý định không tự chứng minh kích hoạt thành công.

Nếu audit chưa ghi bền vững được ý định, candidate không được kích hoạt. Snapshot cũ chỉ tiếp tục phục vụ theo điều kiện hiệu lực của nó. Đường audit không được cho phép lưu đệm vô hạn; nếu dùng hàng đợi bền vững, phải có dung lượng, chính sách khi đầy và kiểm thử khôi phục.

Nâng cấp schema cần có bảng chuyển đổi rõ ràng. Khi default thay đổi, phải phân biệt field trước đây được cấp tường minh với field trước đây chỉ nhận default. Không được vô tình đưa một giá trị kém an toàn cũ thành ngoại lệ vĩnh viễn khi migration.

Rollback phần mềm cũng phải xét khả năng đọc schema mới, trạng thái thu hồi và dữ liệu được tạo bằng cấu hình mới. “Bản trước từng chạy được” không phải bằng chứng bản đó còn được phép sử dụng ở thời điểm khôi phục.

## 9. Chuyển yêu cầu thành kế hoạch kiểm thử

Bằng chứng kiểm thử cần gồm đầu vào, revision thực sự hiệu lực, hành vi API và kết quả audit đã lọc. Các trường hợp dưới đây dùng chung phạm vi dịch vụ tài liệu của ví dụ.

| Ca kiểm thử | Thiết lập hoặc thao tác | Kết quả bắt buộc |
|---|---|---|
| T01 · Cài mới thiếu cấu hình | Không cung cấp issuer, audience và key reference | API được bảo vệ không phục vụ; không sinh tài khoản mặc định; readiness chưa sẵn sàng |
| T02 · Bỏ field tùy chọn | Bỏ `sharing.publicEnabled` và `debugEnabled` khỏi cấu hình hợp lệ | Cả hai nhận `false`; revision hiệu lực được xác định |
| T03 · Không đúng kiểu | Lần lượt dùng chuỗi `"false"`, chuỗi rỗng và `null` cho field boolean | Mỗi candidate bị từ chối; không ép kiểu hoặc tự dùng default |
| T04 · Gõ sai và khóa trùng | Gửi field sai tên hoặc hai khóa trùng trong schema bảo mật | Từ chối với mã lỗi tương ứng; không phụ thuộc thứ tự parser |
| T05 · Nguồn vượt quyền | Dùng biến môi trường yêu cầu `authentication.required=false` | Không kích hoạt; chỉ rõ loại nguồn và mã lý do, không lộ giá trị bí mật |
| T06 · Giả môi trường | Đổi `targetEnvironment` thành development trên deployment production | Không giảm baseline; candidate không khớp đích bị từ chối |
| T07 · Xác thực và tenant | Gọi API thiếu danh tính, rồi dùng danh tính tenant A truy cập tài liệu tenant B | Từ chối theo hợp đồng API; không đọc được nội dung và không tạo tác dụng phụ |
| T08 · Đối tác và khóa | Dùng đối tác không hợp lệ hoặc làm mất quyền dùng khóa bắt buộc | Không hạ kiểm soát truyền tin; thao tác cần khóa thất bại an toàn, không ghi dạng rõ |
| T09 · Cận kích thước | Gửi request hợp lệ về nội dung ở 1.048.576 và 1.048.577 byte | Request ở cận đi qua kiểm tra kích thước; request vượt cận bị chặn trước nghiệp vụ |
| T10 · Reload lỗi | Gửi candidate không hợp lệ trong khi revision cũ còn được phép | Giữ nguyên revision cũ; có audit từ chối và không quan sát trạng thái pha trộn |
| T11 · Kích hoạt và restart | Dừng process trước/sau công bố snapshot, rồi khởi động lại | Khôi phục nhất quán; đối soát được audit và revision; không dùng ý định như bằng chứng thành công |
| T12 · Snapshot mất hiệu lực | Thu hồi snapshot, làm gián đoạn nguồn cấu hình và thử rollback về snapshot đó | Không tiếp tục hoặc phục hồi bản đã thu hồi; luồng bị ảnh hưởng ngừng phục vụ theo thời hạn đã đặc tả |
| T13 · Độ hội tụ của cụm | Cô lập một instance khi thu hồi, thử cả đường truy cập trực tiếp được hỗ trợ | Instance không giữ khả năng phục vụ trái policy sau thời hạn cho phép |
| T14 · Audit không ghi được | Làm kho audit hoặc hàng đợi bền vững không nhận ý định mới | Candidate chưa kích hoạt; bộ đệm có cận; không báo kích hoạt thành công |
| T15 · Redaction | Dùng secret thử nghiệm có dấu nhận dạng, kích hoạt lỗi và đọc chẩn đoán bằng từng vai trò | Không thấy secret trong phản hồi/log; vai trò thiếu quyền không được xem cấu hình |
| T16 · Migration | Nâng cấp rồi thử khôi phục với cấu hình có field thiếu và field đã cấp tường minh | Default và giá trị tường minh được xử lý theo hợp đồng migration; bất biến vẫn được giữ |

Không cần mọi ca đều là kiểm thử đầu cuối. Parser, hợp nhất và schema phù hợp với kiểm thử đơn vị; tương tác với nguồn danh tính, khóa, audit và reload cần kiểm thử tích hợp; rollout, mất kết nối và drift cần môi trường đại diện cho kiến trúc triển khai.

Tuy nhiên, chỉ kiểm tra bộ validator trả lỗi là chưa đủ cho các yêu cầu bảo vệ API. Ít nhất phải có bằng chứng luồng thật không phục vụ trái phép, không ghi dữ liệu ngoài chính sách và không bị một đường vào khác bỏ qua kiểm soát.

### 9.1. Một tiêu chí Given–When–Then hoàn chỉnh

```gherkin
Given deployment production đang phục vụ bằng revision r17 còn hiệu lực
And nguồn command line không được phép sửa authentication.required
When một candidate yêu cầu authentication.required=false qua command line
Then candidate bị từ chối với mã CONFIG_SOURCE_NOT_AUTHORIZED
And revision hiệu lực vẫn là r17
And yêu cầu không có danh tính tới API tài liệu bị từ chối
And không có tài liệu hoặc quyền mới được tạo
And audit ghi nguồn, kết quả và mã lý do mà không ghi secret
```

Ca này liên kết rủi ro R-CFG-02 với CFG-02, CFG-05, CFG-08 và CFG-12. Nó kiểm tra cả quyết định cấu hình lẫn hành vi của hệ thống sau quyết định đó.

## 10. Ngoại lệ và trách nhiệm trong vòng đời phát triển

Một nhu cầu tích hợp đặc biệt có thể đòi hỏi khác baseline. Cần xác định phần nào cho phép ngoại lệ và phần nào là bất biến không được vượt qua.

Với ngoại lệ được phép, hồ sơ tối thiểu nên gồm phạm vi tài nguyên hoặc tenant, rủi ro được chấp nhận, người có thẩm quyền, biện pháp bù, thời điểm hết hiệu lực và bằng chứng kiểm thử. Hệ thống phải có cơ chế thực thi phạm vi và thời hạn đó; một ghi chú trong ticket không tự tạo kiểm soát runtime.

Trong ví dụ, policy cho phép tenant A sử dụng tính năng chia sẻ không có nghĩa được tắt xác thực cho API quản trị. Môi trường phát triển cũng cần default phù hợp để tránh rò rỉ dữ liệu thử nghiệm và hình thành cấu hình được copy trực tiếp sang production.

Trách nhiệm có thể phân công như sau:

| Vai trò | Sản phẩm hoặc trách nhiệm |
|---|---|
| Chủ sở hữu rủi ro và nghiệp vụ | Quyết định phạm vi bảo vệ, tác động khi không phục vụ và quyền chấp thuận ngoại lệ |
| Kiến trúc và bảo mật | Xác định ranh giới tin cậy, bất biến, nguồn có thẩm quyền và hành vi suy giảm |
| Đội phát triển | Schema, validator, cơ chế snapshot, bảo vệ các đường vào và mã lỗi ổn định |
| Đội kiểm thử | Liên kết ID yêu cầu với ca kiểm thử dương, âm, migration và khôi phục |
| Đội nền tảng và vận hành | Phân phối cấu hình, quyền sửa, kiểm soát drift, bằng chứng revision và ứng phó thu hồi |

Trong thiết kế, yêu cầu liên kết tới thành phần thực thi: ví dụ CFG-05 thuộc bộ hợp nhất cấu hình, CFG-02 thuộc middleware và lớp quyết định quyền, CFG-08 thuộc cơ chế quản lý snapshot. Trong triển khai và vận hành, cần tiếp tục thu thập bằng chứng các thành phần ấy đang áp dụng đúng revision.

Việc giữ liên kết **rủi ro → yêu cầu → thành phần kiến trúc → ca kiểm thử → bằng chứng vận hành** giúp tìm phần cần đánh giá lại khi thay đổi default, thêm nguồn cấu hình hoặc mở một đường truy cập mới.

## 11. Những cách đặc tả dễ gây hiểu nhầm

| Cách viết | Vấn đề | Cách làm rõ |
|---|---|---|
| “Ứng dụng phải có cấu hình an toàn” | Không xác định được hành vi cần kiểm chứng | Chỉ ra phạm vi, field, default, bất biến và tiêu chí chấp nhận |
| “Thiếu cấu hình thì dùng giá trị chuẩn” | Có thể biến lỗi đầu vào thành cấu hình khác người triển khai dự định | Tách thiếu field được phép với rỗng, sai kiểu, sai nguồn và thiếu điều kiện bắt buộc |
| “Biến môi trường luôn được ưu tiên” | Ưu tiên bị dùng như quyền thay đổi mọi kiểm soát | Công bố danh sách field mỗi nguồn được cấp và kiểm tra bất biến sau hợp nhất |
| “Có file baseline trong repository là đủ” | Không biết trạng thái thực tế của từng instance | Đo revision hiệu lực và đối chiếu baseline được phép |
| “Lỗi thì rollback về bản gần nhất” | Bản gần nhất có thể hết hạn hoặc đã bị thu hồi | Kiểm tra lại thẩm quyền, hiệu lực và tương thích trước khôi phục |
| “Bật audit khi có sự cố” | Thiếu bằng chứng trước thời điểm phát hiện | Audit thay đổi cấu hình phải hoạt động từ đầu với dữ liệu được lọc |
| “Chỉ cần kiểm thử cài mới” | Bỏ sót drift, nâng cấp, reload và trạng thái suy giảm | Kiểm tra cả vòng đời và các đường phục hồi |

## 12. Bài tập vận dụng

Một API báo cáo có ba lỗi thiết kế:

1. Thiếu biến `AUTH_ISSUER` làm ứng dụng bật chế độ anonymous.
2. `PUBLIC_REPORTS` nhận chuỗi bất kỳ và coi mọi chuỗi không rỗng là `true`.
3. Khi dịch vụ cấu hình không phản hồi, mỗi instance tự dùng file cache gần nhất, kể cả file chứa policy đã thu hồi.

Hãy viết lại đặc tả cho từng lỗi, gồm rủi ro, điều kiện mặc định hoặc bắt buộc, nguồn có thẩm quyền, hành vi từ chối, kết quả API và bằng chứng kiểm thử. Thêm một trường hợp reload và một trường hợp restart.

Một hướng giải quyết:

- **Lỗi 1:** issuer là điều kiện bắt buộc cho API báo cáo được bảo vệ. Thiếu issuer giữ API chưa sẵn sàng, không chuyển sang anonymous. Kiểm thử phải gọi API sau startup thiếu cấu hình và xác nhận không có báo cáo được trả về.
- **Lỗi 2:** field chỉ nhận boolean đúng kiểu; khi thiếu nhận `false`. Các chuỗi `"false"`, `"0"`, chuỗi rỗng và `null` bị từ chối theo hợp đồng. Cho phép tính năng công khai vẫn cần policy có thẩm quyền và quyết định chia sẻ cho từng báo cáo.
- **Lỗi 3:** cache chỉ được dùng trong thời gian và phạm vi còn được cho phép; có cơ chế phát hiện thu hồi và chặn bản đã thu hồi sau restart. Reload thất bại giữ bản cũ chỉ khi bản đó còn hiệu lực. Khi không chứng minh được quyền tiếp tục sử dụng, luồng liên quan phải ngừng phục vụ theo hợp đồng đã xác định.

Sản phẩm của bài tập là một tập yêu cầu có thể giao cho đội phát triển và kiểm thử: mỗi yêu cầu xác định rõ đầu vào, quyết định, hành vi khi lỗi và bằng chứng cần thu thập. Đó là cách biến secure default configuration thành một phần cụ thể của đặc tả bảo mật.


# Data minimization — Tối thiểu hóa dữ liệu trong IAM

## 1. Thu thập và sử dụng dữ liệu vừa đủ cho một mục đích cụ thể

**Data minimization** là thiết kế để chỉ thu thập, sử dụng, chia sẻ và lưu giữ lượng dữ liệu cần thiết cho mục đích đã xác định. Trong quản lý danh tính và quyền truy cập, câu hỏi không chỉ là “có thể lấy được thuộc tính này không?” mà còn là “thành phần này cần biết thuộc tính đó để làm quyết định nào?”.

Một ứng dụng cần biết người dùng đã đăng nhập và có quyền xem báo cáo không nhất thiết cần ngày sinh, địa chỉ nhà, số điện thoại cá nhân hay toàn bộ nhóm mà người đó tham gia. Việc IdP có sẵn một thuộc tính không tạo ra lý do để gửi nó cho mọi ứng dụng tích hợp.

Tối thiểu hóa dữ liệu áp dụng cả với dữ liệu có vẻ bình thường. Khi kết hợp tên công ty, phòng ban, lịch sử đăng nhập và định danh thiết bị, hệ thống có thể suy ra nhiều thông tin hơn từng trường riêng lẻ. W3C Privacy Principles cũng đặt nguyên tắc tối thiểu hóa đối với dữ liệu cá nhân nói chung, không chỉ dữ liệu đã được biết là nhạy cảm hoặc có khả năng định danh trực tiếp. [W3C Privacy Principles — Data Minimization](https://www.w3.org/TR/privacy-principles/#data-minimization).

Mục tiêu không phải xóa tùy ý những dữ liệu hệ thống đang cần. IAM vẫn cần đủ bằng chứng để xác thực, đủ thuộc tính đáng tin cậy để quyết định quyền, đủ dữ liệu để khôi phục truy cập và đủ dấu vết để điều tra sự cố. Thiết kế tốt xác định rõ mức cần thiết của từng mục đích, thay vì sao chép toàn bộ hồ sơ để dự phòng cho mọi nhu cầu có thể xuất hiện.

## 2. Phân biệt tối thiểu hóa với các biện pháp bảo vệ khác

| Biện pháp | Câu hỏi chính | Điều biện pháp đó chưa tự giải quyết |
|---|---|---|
| Tối thiểu hóa dữ liệu | Có thực sự cần dữ liệu này tại thành phần này không? | Không thay thế kiểm soát truy cập và bảo mật dữ liệu còn cần dùng |
| Nguyên tắc ít quyền nhất | Chủ thể nào được thực hiện hành động nào? | Một ứng dụng có quyền hợp lệ vẫn có thể được cung cấp quá nhiều thuộc tính |
| Mã hóa | Ai có thể đọc dữ liệu nếu không có khóa? | Không làm dữ liệu dư thừa trở thành cần thiết |
| Che dữ liệu trên giao diện | Người xem màn hình thấy được phần nào? | Không ngăn dữ liệu đầy đủ bị gửi trong response, log hoặc export |
| Dùng định danh giả | Có thể thay định danh trực tiếp bằng một tham chiếu không? | Không bảo đảm không thể liên kết hoặc nhận diện lại |
| Giới hạn thời gian lưu | Dữ liệu còn cần được giữ đến khi nào? | Không biện minh cho việc thu thập quá mức ngay từ đầu |

Ví dụ, mã hóa toàn bộ hồ sơ nhân sự rồi sao chép sang 20 ứng dụng vẫn tạo ra 20 nơi lưu dữ liệu. Nếu chỉ hai ứng dụng cần địa chỉ cá nhân, thiết kế tối thiểu hóa sẽ xem xét việc không cung cấp trường đó cho 18 ứng dụng còn lại, đồng thời bảo vệ dữ liệu ở hai nơi thực sự cần dùng.

Một hash thông thường của email cũng không làm email trở thành dữ liệu vô danh. Không gian email có thể đoán được và cùng một giá trị hash có thể nối hoạt động giữa các hệ thống. Các tham chiếu giả hoặc cơ chế có khóa có thể giảm một số rủi ro, nhưng vẫn cần quản lý khả năng liên kết, quyền truy cập và thông tin bổ trợ.

## 3. Bắt đầu từ mục đích và quyết định cần thực hiện

### 3.1. Lập danh sách thuộc tính theo mục đích

Với mỗi trường, xác định mục đích, bên nhận, độ chi tiết và thời gian cần dùng. Bảng sau minh họa các câu hỏi thiết kế, không phải một schema bắt buộc:

| Mục đích | Dữ liệu có thể cần | Dữ liệu cần xem xét tránh cung cấp |
|---|---|---|
| Liên kết phiên đăng nhập với tài khoản ứng dụng | Định danh chủ thể trong phạm vi nhà cung cấp danh tính | Hồ sơ nhân sự đầy đủ |
| Gửi thông báo tài khoản | Địa chỉ liên hệ phù hợp đã được xác minh theo quy trình | Địa chỉ nhà hoặc nhiều số điện thoại không phục vụ thông báo |
| Quyết định truy cập báo cáo | Quyền phù hợp với tài nguyên, tenant và ngữ cảnh | Toàn bộ danh sách nhóm của tổ chức nếu chỉ cần một quyền cụ thể |
| Xác nhận điều kiện độ tuổi | Một kết quả xác minh điều kiện có nguồn đáng tin cậy | Ngày sinh đầy đủ hoặc bản chụp giấy tờ tại mọi ứng dụng nhận kết quả |
| Đồng bộ tài khoản sang SaaS | Các trường hệ thống đích thực sự yêu cầu | Mọi thuộc tính trong directory nguồn |
| Điều tra đăng nhập bất thường | Thời điểm, kết quả, mã sự kiện, tham chiếu chủ thể và ngữ cảnh cần thiết | Mật khẩu, OTP, token hoặc toàn bộ request body |

“Có thể hữu ích về sau” chưa phải mục đích đủ rõ để đưa một trường vào contract mặc định. Khi có nhu cầu mới, cần đánh giá thay đổi đó thay vì mở sẵn mọi thuộc tính cho tất cả bên nhận.

### 3.2. Giảm độ chi tiết khi kết quả là đủ

Nếu một dịch vụ chỉ cần biết người dùng đáp ứng một điều kiện, có thể cung cấp kết quả điều kiện thay vì dữ liệu gốc. Ví dụ, kết quả “đã được xác minh đáp ứng ngưỡng tuổi của dịch vụ” tiết lộ ít hơn ngày sinh đầy đủ.

Kết quả rút gọn vẫn cần ngữ nghĩa rõ: do ai xác minh, điều kiện nào được kiểm tra, kiểm tra lúc nào và còn phù hợp với quyết định hiện tại không. Một field `eligible: true` do trình duyệt tự gửi không thay thế bằng chứng đáng tin cậy. Tối thiểu hóa dữ liệu không cho phép bỏ qua việc kiểm tra nguồn, tính toàn vẹn hoặc độ mới của thuộc tính.

Trong ABAC, cách rút gọn còn phải giữ đúng chính sách. Chẳng hạn, thay thuộc tính bộ phận bằng một cờ quyền có thể giảm dữ liệu được chia sẻ, nhưng chỉ hợp lệ nếu bên phát hành thực sự tính cờ đó theo chính sách được chấp thuận và hệ thống nhận kiểm tra đúng phạm vi sử dụng.

## 4. Áp dụng vào hồ sơ, xác thực và khôi phục tài khoản

### 4.1. Hồ sơ danh tính không phải bản sao toàn bộ hồ sơ con người

Directory phục vụ IAM nên có mô hình thuộc tính gắn với chức năng của nó. Dữ liệu nhân sự, thanh toán hoặc chăm sóc khách hàng có thể cần tồn tại ở hệ thống chuyên trách mà không cần được sao chép nguyên vẹn vào directory đăng nhập.

Khi bổ sung trường hồ sơ, cần trả lời được ai sử dụng, quy trình nào sẽ hỏng nếu thiếu và nơi nào là nguồn chuẩn. Nếu một ứng dụng chỉ cần hiển thị tên, không nên vì sự tiện lợi của việc lấy dữ liệu mà cấp luôn quyền đọc toàn bộ hồ sơ.

Địa chỉ email có thể thay đổi hoặc được cấp lại theo vòng đời tổ chức. Thiết kế liên kết danh tính cần dùng định danh và quy tắc của nhà cung cấp tương ứng, thay vì mặc định email luôn là khóa ổn định duy nhất. Với OIDC, khi xử lý liên kết tài khoản, cần xem `sub` trong phạm vi issuer đã được xác minh, không dùng một `sub` trần để trộn danh tính từ các issuer khác nhau.

### 4.2. Xác thực và MFA

Lựa chọn phương thức xác thực ảnh hưởng loại dữ liệu cần xử lý. Nếu quy trình dùng phương thức không cần số điện thoại, việc yêu cầu số điện thoại của mọi người dùng cần có một mục đích riêng được xác định, chẳng hạn một kênh khôi phục đã được đánh giá. Không nên thêm thông tin liên hệ vào form chỉ vì các hệ thống trước đây thường làm như vậy.

Tuy nhiên, bỏ một trường mà không xem xét luồng dự phòng có thể làm người dùng mất khả năng khôi phục truy cập. Cần thiết kế đồng thời phương thức chính, phương thức dự phòng, xác minh thay đổi kênh liên hệ và kiểm soát chống chiếm tài khoản.

Thông tin xác thực cũng có yêu cầu bảo vệ riêng. Không ghi mật khẩu thô vào hồ sơ, log hoặc ticket. Việc vẫn cần duy trì dữ liệu xác minh mật khẩu không có nghĩa là được thay thế cơ chế lưu mật khẩu an toàn bằng một hash đơn giản để “giảm dữ liệu”.

### 4.3. Xác minh danh tính và tài liệu nguồn

Một số quy trình cần kiểm tra tài liệu hoặc thông tin định danh có độ nhạy cao. Cần tách nhu cầu thực hiện kiểm tra khỏi nhu cầu giữ lâu dài bản sao tài liệu. Ứng dụng nhận kết quả có thể chỉ cần một xác nhận phù hợp, thay vì tự lưu bản chụp giấy tờ từ quy trình xác minh.

Nếu hệ thống phải giữ dữ liệu nguồn cho một mục đích cụ thể, cần xác định nơi lưu, nhóm được truy cập và thời hạn tương ứng. Không nhân bản tài liệu sang log kỹ thuật, môi trường thử nghiệm hoặc hệ thống hỗ trợ chỉ để thuận tiện gỡ lỗi.

## 5. Tối thiểu hóa claims trong SSO và liên kết danh tính

### 5.1. Thiết kế contract riêng cho từng bên nhận

IdP có thể biết nhiều thuộc tính hơn mức một ứng dụng cần. Khi cấu hình SSO, nên xác định claims được phép phát hành cho từng client hoặc dịch vụ, thay vì cấu hình một bộ claims khổng lồ dùng chung.

Ví dụ, một cổng báo cáo có thể cần định danh ứng dụng, tenant và quyền xem báo cáo. Nó không nhất thiết cần số điện thoại, ngày sinh, lương hoặc danh sách mọi nhóm mà người dùng tham gia. Việc người dùng được xác thực thành công không đồng nghĩa ứng dụng cần nhận toàn bộ dữ liệu của người đó.

Trong OIDC, lựa chọn scope và cấu hình claims là một phần của contract chia sẻ dữ liệu. Không tự động yêu cầu thêm `profile`, `email`, `phone` hoặc `address` nếu chức năng không cần. Scope xin được cũng không nên bị hiểu là sự bảo đảm rằng mọi thuộc tính tương ứng luôn được trả về; ứng dụng phải xử lý đúng contract và chính sách của nhà cung cấp.

ID token phục vụ client xác minh kết quả xác thực; access token phục vụ truy cập tài nguyên theo contract tương ứng. Không dùng ID token như một vật chứa hồ sơ chung rồi chuyển tiếp cho mọi API. Khi giảm dữ liệu tùy chọn trong token, vẫn phải giữ và kiểm tra các trường bắt buộc của protocol hoặc profile đang dùng.

Ví dụ sau chỉ mô tả các phần dữ liệu nghiệp vụ dự kiến cho một bên nhận; đây không phải một token hoàn chỉnh:

```json
{
  "subject_ref": "subject-for-report-portal-27",
  "tenant_ref": "tenant-demo",
  "permissions": ["reports:read"]
}
```

Một token thực tế còn có cấu trúc và thông tin bảo mật theo protocol, như issuer, audience và thời hạn. Hệ thống nhận vẫn phải kiểm tra tính hợp lệ và quyền trên tài nguyên cụ thể. Chỉ có chuỗi `reports:read` không tự chứng minh người dùng được đọc mọi báo cáo của mọi tenant.

JWT chỉ được ký thường có payload đọc được bởi bên có token; chữ ký bảo vệ tính toàn vẹn, không đồng nghĩa mã hóa nội dung. Vì thế, không đưa dữ liệu riêng tư không cần thiết vào token với giả định rằng chuỗi token trông khó đọc là đủ bảo mật.

### 5.2. Giảm liên kết danh tính không cần thiết giữa ứng dụng

Một định danh dùng chung ở mọi ứng dụng tạo điều kiện nối hoạt động giữa các bên nhận. Khi phù hợp với yêu cầu tích hợp, có thể dùng định danh trong phạm vi riêng thay vì phát hành một định danh toàn cục có cùng giá trị cho mọi nơi.

OIDC hỗ trợ pairwise subject identifier: giá trị `sub` được phân biệt theo Sector Identifier. Vì nhiều client có thể cùng một sector, không nên diễn giải cơ chế này thành bảo đảm “mỗi client luôn có một giá trị khác nhau”. Cũng không nên hiểu pairwise `sub` là vô danh tuyệt đối: OpenID Provider vẫn có khả năng liên kết, và các claims khác như email có thể làm lộ mối liên hệ. [OpenID Connect Core 1.0 — Pairwise Identifier Algorithm](https://openid.net/specs/openid-connect-core-1_0.html#PairwiseAlg).

Nếu nghiệp vụ cần liên kết tài khoản giữa các ứng dụng, phải thực hiện theo cơ chế và quyền phù hợp. Không tự nối các hồ sơ chỉ vì đoán rằng hai email, tên hiển thị hoặc thuộc tính tương tự thuộc cùng một người.

## 6. Tối thiểu hóa trong API và provisioning

### 6.1. Lọc dữ liệu ở phía máy chủ

Một giao diện có thể chỉ hiển thị tên nhưng API vẫn trả về ngày sinh, địa chỉ và dữ liệu khôi phục. Đây là giảm hiển thị, chưa phải giảm chia sẻ. Người dùng hoặc thành phần có quyền đọc response vẫn có thể nhận các trường bị giấu khỏi màn hình.

Nên dùng mô hình response riêng cho từng chức năng và một danh sách trường được phép rõ ràng. Luồng xử lý khái niệm có thể như sau:

```text
Xác thực người gọi
    → kiểm tra quyền với tenant và đối tượng cụ thể
    → đọc các thuộc tính cần cho chức năng
    → ánh xạ sang response được phép
    → ghi audit event theo schema đã giới hạn
```

Không serialize trực tiếp toàn bộ entity directory hoặc object hồ sơ nội bộ ra API. Một trường mới được thêm vào entity không nên tự động xuất hiện trong mọi response hoặc export.

Danh sách trường được phép còn cần gắn với phân quyền. Quyền đọc tên hiển thị không kéo theo quyền đọc thông tin khôi phục tài khoản. Các API tìm kiếm, export hàng loạt và công cụ quản trị cũng phải tuân thủ giới hạn này, không chỉ API dùng cho màn hình người dùng.

### 6.2. Mapping thuộc tính theo hệ thống đích

Trong provisioning, tạo mapping theo nhu cầu của ứng dụng nhận. Một SaaS có thể cần định danh, tên hiển thị và trạng thái tài khoản; ứng dụng khác có thể cần thêm một thuộc tính tổ chức phục vụ phân quyền. Cần xác minh từng nhu cầu thay vì sao chép một mapping chung chứa toàn bộ directory.

Khi bỏ một trường khỏi mapping, không mặc định dữ liệu cũ ở đích sẽ tự biến mất. Một số cơ chế đồng bộ có thể giữ giá trị cũ nếu trường không còn được gửi. Cần kiểm tra ngữ nghĩa cập nhật hoặc xóa thuộc tính của connector và hệ thống đích, rồi xác minh trạng thái sau thay đổi.

Tối thiểu hóa còn áp dụng với danh tính workload. Một service account thường cần định danh dịch vụ, owner chịu trách nhiệm và quyền phù hợp; không nhất thiết cần bản sao hồ sơ cá nhân đầy đủ của người tạo. Thông tin owner vẫn cần đủ để kiểm toán và xử lý vòng đời của tài khoản dịch vụ.

## 7. Giữ khả năng kiểm toán với log vừa đủ

### 7.1. Chọn sự kiện và thuộc tính phục vụ điều tra

IAM cần quan sát đăng nhập, thay đổi phương thức MFA, cấp quyền, thu hồi quyền và hành động quản trị. Tối thiểu hóa không có nghĩa là ngừng ghi các sự kiện đó. Thay vào đó, chọn trường dữ liệu đủ để biết chuyện gì xảy ra, vào lúc nào, với đối tượng nào và kết quả ra sao.

Một sự kiện minh họa:

```json
{
  "event_id": "event-demo-934",
  "event_type": "authentication_failed",
  "occurred_at": "2026-10-12T02:10:00Z",
  "subject_ref": "audit-subject-61",
  "application_ref": "report-portal",
  "reason_class": "invalid_credential",
  "correlation_id": "flow-demo-82"
}
```

Đây là schema rút gọn cho ví dụ, không phải danh sách đầy đủ cho mọi hệ thống. Một hệ thống phòng chống lạm dụng có thể cần thêm thông tin nguồn mạng hoặc thiết bị, nhưng phải xác định mục đích, độ chi tiết, quyền truy cập và thời hạn sử dụng tương ứng.

Thông tin sự kiện nội bộ cũng không phải nội dung được phép trả nguyên văn cho người chưa xác thực. Chẳng hạn, phản hồi đăng nhập không nên tiết lộ một tài khoản có tồn tại chỉ vì log nội bộ ghi được nguyên nhân chi tiết.

Không ghi mật khẩu, OTP, access token, refresh token hoặc cookie phiên. OWASP Logging Cheat Sheet khuyến nghị loại bỏ hoặc xử lý phù hợp những dữ liệu như mật khẩu, token, bí mật và dữ liệu cá nhân nhạy cảm thay vì ghi trực tiếp vào log. [OWASP Logging Cheat Sheet — Data to Exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

### 7.2. Kiểm soát các bản sao khó nhìn thấy

Request tracing, error reporting, reverse proxy, hệ thống hỗ trợ và công cụ phân tích đều có thể vô tình tạo thêm bản sao dữ liệu danh tính. Giảm trường trong database chính không đủ nếu middleware vẫn ghi toàn bộ header hoặc request body.

Nên xây schema sự kiện rõ ràng và hạn chế dữ liệu ngay tại điểm phát sinh. Việc chỉ che dữ liệu khi hiển thị dashboard không loại bỏ bản gốc trong kho log. Các tính năng debug tạm thời cần phạm vi, thời hạn và kiểm soát phù hợp để không trở thành đường thu thập dữ liệu thường trực.

Định danh giả trong audit log vẫn có giá trị liên kết hành vi. Nếu cần ánh xạ về danh tính thật để xử lý sự cố, bảo vệ cơ chế ánh xạ riêng và giới hạn ai được sử dụng. Không coi việc đổi email thành một mã nội bộ là đã loại bỏ mọi nghĩa vụ bảo vệ dữ liệu.

## 8. Giảm dữ liệu trong toàn bộ vòng đời

### 8.1. Xác định thời gian cần dùng theo loại dữ liệu

Hồ sơ hiện hành, dữ liệu khôi phục, lịch sử cấp quyền và log kỹ thuật có thể có mục đích cùng thời hạn khác nhau. Cần xác định chính sách lưu giữ cho từng loại theo yêu cầu thực tế của tổ chức và bối cảnh áp dụng; không có một số ngày duy nhất phù hợp cho mọi dữ liệu IAM.

Vô hiệu hóa tài khoản không đồng nghĩa xóa toàn bộ dữ liệu ngay lập tức. Một số dấu vết có thể còn cần cho xử lý sự cố hoặc kiểm toán, nhưng điều đó cũng không biện minh cho việc giữ mọi bản sao hồ sơ vô thời hạn. Cần phân biệt dữ liệu vận hành còn cần, dữ liệu lịch sử có mục đích cụ thể và dữ liệu có thể loại bỏ.

Quy trình cần tính tới cache, chỉ mục tìm kiếm, kho phân tích, export, bản sao ở SaaS và backup. Với backup, chính sách phải làm rõ vòng đời, quyền khôi phục và cách xử lý dữ liệu đã hết hạn nếu một bản sao được phục hồi. Không hứa rằng xóa một hàng ở database chính đã xóa tức thời mọi bản sao.

### 8.2. Tránh để dữ liệu cũ tiếp tục được phát hành

Khi một thuộc tính không còn cần cho ứng dụng, cần ngừng phát hành trong claims, response và mapping tương ứng. Đồng thời kiểm tra dữ liệu đã được cache hoặc lưu lại ở bên nhận. Token đã phát hành có thể vẫn chứa giá trị cũ cho đến khi hết hiệu lực hoặc được xử lý bằng cơ chế của hệ thống; giảm claim ở lần phát hành sau không tự thu hồi mọi bản trước đó.

Dữ liệu thử nghiệm nên là dữ liệu tổng hợp phù hợp với tình huống cần kiểm tra, thay vì sao chép tùy tiện hồ sơ thật. Nếu một hoạt động hỗ trợ cần dữ liệu sản xuất, chỉ cung cấp phần cần thiết qua kênh và quyền đã được kiểm soát.

## 9. Ví dụ thiết kế một cổng báo cáo

Giả sử cổng báo cáo ban đầu nhận từ IdP tên, email, số điện thoại cá nhân, ngày sinh, địa chỉ nhà, mã nhân viên và toàn bộ nhóm directory. Ứng dụng lưu nguyên response vào bảng người dùng và ghi response đó vào log mỗi lần đăng nhập.

Sau khi phân tích chức năng, nhóm thiết kế xác định cổng chỉ cần liên kết tài khoản, hiển thị tên, xác định tenant và kiểm tra quyền đối với báo cáo. Một thiết kế phù hợp hơn có thể là:

| Thành phần | Dữ liệu giữ hoặc nhận | Lý do |
|---|---|---|
| IdP | Dữ liệu phục vụ xác thực và các mục đích đã được xác định | Không phát hành mọi trường cho cổng báo cáo |
| Liên kết tài khoản tại cổng | Định danh chủ thể trong phạm vi issuer cùng tenant khi cần | Nhận diện đúng tài khoản ứng dụng |
| Giao diện cổng | Tên hiển thị nếu chức năng cần | Hiển thị tài khoản đang dùng |
| Thành phần quyết định quyền | Các quyền hoặc thuộc tính đáng tin cậy liên quan tới báo cáo | Quyết định trên đúng tài nguyên và tenant |
| Audit log | Sự kiện, kết quả và tham chiếu đủ để điều tra | Truy vết mà không lưu nguyên hồ sơ hoặc token |

Trong thiết kế này, việc bỏ dữ liệu không cần không làm mất bước kiểm tra token, kiểm tra tenant hoặc kiểm tra quyền đối với từng báo cáo. Đồng thời, cần có kế hoạch xử lý dữ liệu dư đã được lưu từ trước; chỉ sửa payload mới chưa giải quyết các bản sao lịch sử.

Có thể theo dõi tiến bộ bằng số trường chưa có mục đích rõ ràng, số bên nhận dữ liệu, số mapping phát hành quá phạm vi và kết quả kiểm tra log có chứa bí mật. Không nên đặt mục tiêu giảm số claims bằng mọi giá: một claim cần cho kiểm tra bảo mật có thể quan trọng hơn việc giảm kích thước token.

## 10. Tự kiểm tra cách hiểu

**Ứng dụng chỉ hiển thị bốn số cuối điện thoại, nhưng API trả toàn bộ số điện thoại. Đã tối thiểu hóa việc chia sẻ chưa?**

Chưa. Người nhận response vẫn có dữ liệu đầy đủ. Cần xem chức năng có cần số đầy đủ hay không và giới hạn response ở phía máy chủ theo mục đích cùng quyền truy cập.

**Mã hóa hồ sơ và đặt quyền truy cập chặt chẽ có thay thế việc giảm dữ liệu dư không?**

Không. Các biện pháp đó bảo vệ dữ liệu đang có. Tối thiểu hóa quyết định dữ liệu nào thực sự cần được thu thập, chia sẻ hoặc lưu ở từng nơi ngay từ đầu.

**Có nên xóa log cấp quyền để giảm dữ liệu cá nhân không?**

Không nên xóa tùy ý dấu vết còn cần cho mục đích kiểm toán và điều tra đã xác định. Cần thiết kế trường log, quyền truy cập và vòng đời phù hợp, đồng thời tránh ghi hồ sơ đầy đủ hoặc bí mật không cần thiết.

**Dấu hiệu của một thiết kế IAM tối thiểu hóa dữ liệu là gì?**

Mỗi thuộc tính có mục đích và bên nhận rõ ràng; mỗi API, token và mapping chỉ cung cấp dữ liệu phù hợp; dữ liệu còn cần được bảo vệ và có vòng đời xác định. Hệ thống vẫn xác thực, phân quyền, khôi phục và kiểm toán được, trong khi giảm việc tiết lộ và nhân bản thông tin không cần thiết.

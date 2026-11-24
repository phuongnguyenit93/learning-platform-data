# Private knowledge risk

## 1. Thông tin riêng tư chưa chắc là bí mật xác thực

**Private knowledge** là những thông tin cá nhân hoặc thông tin về hoạt động của tài khoản mà hệ thống cho rằng chỉ người dùng thật biết. Ví dụ: địa chỉ từng sống, tên người thân, một đơn hàng cũ, thời điểm đăng ký hoặc số tiền của lần thanh toán gần đây.

Trong khôi phục tài khoản, giả định nguy hiểm nằm ở chữ “chỉ”. Một thông tin không xuất hiện trên hồ sơ công khai vẫn có thể được người thân, nhân viên hỗ trợ, đơn vị giao hàng hoặc người đã đọc được hộp thư biết đến. Việc người gửi biết thông tin đó không tự chứng minh họ có quyền đặt lại mật khẩu, gỡ MFA hay đăng ký passkey mới.

Ví dụ, một người mất điện thoại chứa ứng dụng MFA và yêu cầu được khôi phục bằng cách trả lời câu hỏi về lần mua hàng gần nhất. Hệ thống thấy câu trả lời đúng. Nhưng hóa đơn cũng có thể nằm trong email đã bị chiếm hoặc từng được chuyển tiếp cho người khác. Kết quả trả lời đúng chỉ chứng minh người gửi có thông tin về giao dịch, chưa chứng minh quyền kiểm soát tài khoản hợp lệ.

NIST SP 800-63A-4 không cho phép dùng KBV hoặc KBA cho bước xác minh danh tính trong phạm vi hướng dẫn của tài liệu. Đây là yêu cầu của tiêu chuẩn, không phải một kết luận rằng mọi dịch vụ ở mọi nơi đều chịu cùng nghĩa vụ pháp lý. [NIST SP 800-63A-4 — Identity Verification Methods](https://pages.nist.gov/800-63-4/sp800-63a/proofing/#identity-verification-methods)

Bài học này phân tích vì sao kiến thức riêng tư có thể mất giá trị bảo vệ và cách tránh biến nó thành đường vòng yếu khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực.

## 2. Phân biệt dữ kiện cá nhân với bí mật được tạo để xác thực

Không nên đánh đồng mọi thứ người dùng “biết” với câu hỏi về tiểu sử. Mật khẩu và mã khôi phục có mục đích, cách sinh và vòng đời khác với một dữ kiện đời sống.

| Loại thông tin | Đặc điểm | Giới hạn khi dùng trong recovery |
| --- | --- | --- |
| Dữ kiện tiểu sử | Có thể được nhiều người biết; khó thay đổi | Biết dữ kiện chưa chứng minh quyền truy cập |
| Lịch sử tài khoản | Có thể nằm trong email, hóa đơn, màn hình hoặc hệ thống đối tác | Có thể cùng bị lộ với một tài nguyên đã bị chiếm |
| Câu trả lời bảo mật tự chọn | Người dùng có thể chọn câu phổ biến hoặc dùng lại ở nơi khác | Tính bí mật và khả năng nhớ không được bảo đảm |
| Mật khẩu riêng cho dịch vụ | Được thiết lập như một bí mật xác thực có quản lý | Vẫn có thể bị đoán, lộ hoặc phishing; cần cơ chế xác thực phù hợp |
| Mã khôi phục được sinh ngẫu nhiên | Được cấp trước cho một mục đích khôi phục rõ ràng | Chỉ có giá trị khi sinh, lưu, gắn với tài khoản và tiêu thụ an toàn |
| Thử thách chứng minh giữ khóa | Chứng minh khả năng dùng khóa đã gắn với tài khoản | Cần kiểm tra giao thức, độ mới và ngữ cảnh của thử thách |

Một mã khôi phục không mạnh chỉ vì được gọi là “mã”. Nếu nó thực chất được tạo từ ngày sinh hoặc vài chữ số số điện thoại thì vấn đề dễ đoán vẫn còn.

Ngược lại, một câu trả lời hoàn toàn ngẫu nhiên, duy nhất và được lưu bằng công cụ quản lý bí mật có đặc tính gần với một mật khẩu bổ sung hơn là kiến thức cá nhân. Nhưng người dùng có thể mất chính công cụ đó cùng thiết bị. Đặt tên dữ liệu khác đi không giải quyết được sự phụ thuộc giữa các phương thức khôi phục.

Câu hỏi cần đặt ra là: dữ liệu này được tạo để chứng minh quyền gì, ai có thể có nó và nó có thể được thu hồi hoặc thay thế như thế nào?

## 3. Ai có thể biết thông tin được coi là “riêng tư”?

### 3.1. Đánh giá theo đối thủ cụ thể

Một người ngẫu nhiên có thể không biết địa chỉ cũ của người dùng. Điều đó không đủ để bảo vệ trước người từng sống chung, đồng nghiệp hoặc người đã có quyền truy cập tạm thời vào tài khoản.

| Nhóm đối thủ hoặc nguồn lộ | Kiến thức có thể có | Hệ quả đối với câu hỏi khôi phục |
| --- | --- | --- |
| Người thu thập thông tin công khai | Tên trường, quê quán, tên thú cưng từ bài đăng và ảnh | Dữ kiện tưởng kín có thể được suy ra |
| Người thân hoặc người từng sống chung | Địa chỉ cũ, ngày kỷ niệm, người liên hệ | Câu hỏi khó với người lạ có thể rất dễ với họ |
| Người có quyền đọc email | Hóa đơn, số đơn hàng, ngày đăng ký, thông báo thiết bị | Nhiều câu trả lời bị lộ từ cùng một nguồn |
| Người từng thấy session tài khoản | Lịch sử mua hàng, hồ sơ, câu hỏi đã thiết lập | Quyền truy cập tạm thời có thể để lại đường khôi phục |
| Nhân sự hoặc đối tác có quyền xem dữ liệu | Địa chỉ giao hàng, mã khách hàng, thông tin hỗ trợ | Không thể giả định mọi người biết dữ liệu đều là chủ tài khoản |
| Dữ liệu bị lộ từ dịch vụ khác | Câu trả lời dùng lại, địa chỉ, số điện thoại | Dữ liệu cũ có thể còn dùng được nhiều năm |

Bảng này dùng để xác định giới hạn của bằng chứng, không để mặc định người thân hay nhân viên là kẻ tấn công. Một cơ chế bảo vệ cần chịu được trường hợp người không được phép truy cập lại biết nhiều thông tin về người dùng.

### 3.2. Bí mật có thể suy giảm theo thời gian

Một câu trả lời có thể chưa lộ tại thời điểm đăng ký nhưng được chia sẻ hoặc xuất hiện trong một sự cố dữ liệu về sau.

```text
Thông tin từng ít người biết
        ↓
Được chia sẻ qua email, hóa đơn hoặc hồ sơ khác
        ↓
Có thêm người và hệ thống nắm giữ
        ↓
Vẫn được dùng như một “bí mật” khôi phục lâu dài
```

Họ tên thời đi học hoặc nơi sinh không thể được thay đổi thuận tiện như một khóa xác thực bị lộ. Việc thay câu hỏi sau sự cố cũng không thu hồi các dữ kiện đã bị phát tán.

Bởi vậy, “chưa tìm thấy trên Internet” là một nhận xét tại một thời điểm, không phải cam kết rằng chỉ chủ tài khoản biết câu trả lời.

## 4. Dễ nhớ không đồng nghĩa với khó đoán

### 4.1. Độ dài câu trả lời không cho biết sức chống đoán

Một tên trường dài có thể là câu trả lời phổ biến trong một nhóm người dùng. Một địa chỉ có nhiều ký tự nhưng đã có sẵn trên hóa đơn thì không tạo ra nhiều bất định cho người giữ hóa đơn.

Khi đánh giá nguy cơ đoán đúng, điều quan trọng là phân bố câu trả lời **sau khi xét những gì đối thủ biết**, không phải số ký tự hay tổng số câu trả lời có thể tưởng tượng.

Một câu hỏi trắc nghiệm cũng tự thu hẹp tập câu trả lời. Việc hiện bốn lựa chọn không tạo ra bốn bằng chứng; nó cung cấp cho người gửi một tập ứng viên nhỏ để chọn.

### 4.2. Nhiều câu hỏi có thể cùng phụ thuộc một nguồn

Giả sử hệ thống yêu cầu trả lời ba câu:

1. Địa chỉ giao hàng gần nhất là gì?
2. Số tiền của đơn hàng đó là bao nhiêu?
3. Đơn hàng được tạo trong tháng nào?

Ba câu này có thể được trả lời từ một email xác nhận duy nhất. Không thể coi chúng là ba lớp bảo vệ độc lập.

Về mặt xác suất, với `I` là thông tin đối thủ đã có:

```text
P(đúng cả ba | I)
  = P(đúng câu 1 | I)
  × P(đúng câu 2 | đúng câu 1, I)
  × P(đúng câu 3 | đúng câu 1, đúng câu 2, I)
```

Ví dụ số học giả định, không phải số liệu về hệ thống thực:

```text
Nếu ba câu độc lập và xác suất đúng mỗi câu là 10%:
    0,1 × 0,1 × 0,1 = 0,001 = 0,1%

Nếu dữ liệu giúp trả lời câu đầu cũng làm lộ hai câu sau:
    0,1 × 0,8 × 0,9 = 0,072 = 7,2%
```

Các con số chỉ minh họa rằng giả định độc lập có thể làm đánh giá rủi ro sai đáng kể. Trong thực tế, cần xem nguồn dữ liệu, mức tương quan và khả năng truy cập của đối thủ; không gán các xác suất minh họa này cho người dùng thật.

### 4.3. Nhớ sai là vấn đề của người dùng thật

Tên trường có thể được viết đầy đủ hoặc viết tắt. Một người có nhiều địa chỉ, nhiều số điện thoại hoặc không nhớ ngày đăng ký từ nhiều năm trước. Người dùng cũng có thể đã khai một câu trả lời không đúng sự thật rồi quên cách mình đã trả lời.

Nghiên cứu của Google về câu hỏi kiến thức cá nhân ghi nhận cả hạn chế bảo mật lẫn khó khăn ghi nhớ; hành vi tự làm câu trả lời “khó đoán hơn” cũng có thể mang tính dự đoán. [Google Research — Secrets, Lies, and Account Recovery](https://research.google/pubs/secrets-lies-and-account-recovery-lessons-from-the-use-of-personal-knowledge-questions-at-google/)

Một thiết kế khiến người dùng thật thường xuyên thất bại dễ tạo áp lực cho bộ phận hỗ trợ hạ tiêu chuẩn. Khi đó, độ yếu của cơ chế xuất hiện ở cả câu hỏi lẫn đường xử lý ngoại lệ.

## 5. Các biện pháp kỹ thuật có giới hạn rõ ràng

### 5.1. Băm câu trả lời bảo vệ lưu trữ, không làm dữ kiện trở nên bí mật

Với dữ liệu legacy còn lưu câu trả lời, lưu nguyên văn làm tăng hậu quả khi hệ thống bị đọc trái phép. Cơ chế bảo vệ bí mật phù hợp có thể giảm một phần nguy cơ từ dữ liệu lưu trữ.

Tuy nhiên, nếu đối thủ đã biết câu trả lời qua hóa đơn hoặc người quen, việc băm không ngăn họ gửi câu trả lời đúng qua giao diện recovery. Nếu không gian câu trả lời nhỏ, dữ liệu đã băm cũng không tự trở thành một bí mật có độ bất định cao.

Cần tách hai vấn đề:

- **Bảo vệ dữ liệu đang lưu:** hạn chế người có thể đọc hoặc suy ra câu trả lời từ kho dữ liệu.
- **Chứng minh quyền khôi phục:** xác định người đang tương tác có bằng chứng đủ mạnh cho hành động yêu cầu hay không.

Giải quyết vấn đề thứ nhất không tự hoàn thành vấn đề thứ hai.

### 5.2. Giới hạn thử lại giảm tốc độ, không thay chất lượng bằng chứng

Giới hạn số lần gửi, phát hiện tự động hóa và theo dõi yêu cầu liên quan có thể giảm việc đoán hàng loạt. Nhưng người đã có câu trả lời từ trước có thể thành công ngay lần đầu.

Chỉ giới hạn theo địa chỉ IP cũng không mô tả đầy đủ hành vi trên một tài khoản. Ngược lại, khóa đăng nhập của tài khoản sau vài câu trả lời sai có thể cho phép người ngoài gây từ chối dịch vụ.

Ngân sách thử lại nên gắn với yêu cầu recovery và các tín hiệu liên quan theo chính sách. Nó không phải lý do để chấp nhận một loại bằng chứng yếu.

### 5.3. So khớp mềm có thể mở rộng tập được chấp nhận

Để giảm lỗi ghi nhớ, hệ thống legacy có thể bỏ dấu, bỏ khoảng trắng, chấp nhận tên viết tắt hoặc cho phép sai một phần.

Quy tắc càng rộng, số câu trả lời được coi là đúng càng có thể tăng. Một câu trả lời gần giống không tạo ra bằng chứng mới về quyền sở hữu tài khoản.

Cần ghi rõ quy tắc đã dùng, bảo toàn phiên bản và hiểu tác động của nó. Không nới dần tiêu chí chỉ vì người gửi sắp hết lượt thử hoặc đã tạo nhiều ticket.

## 6. Câu hỏi và phản hồi có thể làm lộ thêm dữ liệu

Rủi ro không chỉ nằm ở đáp án. Bản thân câu hỏi, lựa chọn và gợi ý có thể tiết lộ thông tin tài khoản.

Ví dụ:

> Trong các địa chỉ sau, địa chỉ nào từng được bạn sử dụng?

Nếu một lựa chọn được lấy trực tiếp từ hồ sơ, câu hỏi đã đưa thông tin nhạy cảm vào một bề mặt chưa chắc được bảo vệ đủ. Một ngân hàng, người liên hệ hoặc tên cửa hàng xuất hiện trong lựa chọn cũng có thể tiết lộ quan hệ riêng tư.

Các dạng phản hồi khác cần tránh:

- Trả về chính xác câu nào đúng, câu nào sai sau mỗi lần gửi.
- Hiện một phần câu trả lời chuẩn để “nhắc nhớ”.
- Phân biệt rõ tài khoản có hay không có câu hỏi bảo mật ngay từ bước chưa xác minh.
- Hiện lịch sử giao dịch đầy đủ để người gửi chọn đáp án.
- Đưa câu trả lời vào đường dẫn URL, công cụ phân tích, log hoặc bản ghi hỗ trợ rộng quyền xem.

Thông báo trung tính có thể hạn chế việc dò dữ liệu, nhưng không làm private knowledge trở thành bằng chứng mạnh. Hệ thống vẫn cần một quy trình khôi phục phù hợp ngay cả khi không tiết lộ đáp án.

Một thông báo có thể dùng:

> Chúng tôi chưa có đủ bằng chứng để cho phép thay đổi bảo mật. Hãy tiếp tục bằng phương thức khôi phục đã được thiết lập hoặc quy trình hỗ trợ được cung cấp.

Thông báo không cần khẳng định người gửi là kẻ gian chỉ vì họ không nhớ một dữ kiện cũ.

## 7. Giữ ranh giới giữa thông tin hỗ trợ và quyền khôi phục

### 7.1. Thông tin đúng có thể giúp xử lý, không tự cấp quyền

Trong hỗ trợ khách hàng, số đơn hàng có thể giúp tìm đúng giao dịch. Ngày phát sinh sự cố có thể giúp thu hẹp khoảng thời gian cần xem xét.

Đó là giá trị phục vụ điều tra hoặc định tuyến, không đồng nghĩa chúng là phương thức xác thực. Nếu bất kỳ người nào tìm được một hóa đơn cũng có thể nhận token reset thì dữ liệu tra cứu đã bị nâng thành quyền truy cập.

OWASP cảnh báo câu hỏi bảo mật không còn được công nhận là yếu tố xác thực chấp nhận được; phần hướng dẫn về câu hỏi trong tài liệu của họ phục vụ bối cảnh legacy. [OWASP — Choosing and Using Security Questions](https://cheatsheetseries.owasp.org/cheatsheets/Choosing_and_Using_Security_Questions_Cheat_Sheet.html)

Một cách phân loại nội bộ có thể là:

| Nhãn | Mục đích | Tác động được phép trong thiết kế minh họa |
| --- | --- | --- |
| `CONTEXT_ONLY` | Tìm hồ sơ, hiểu tình huống | Hỗ trợ xử lý; không cấp quyền recovery |
| `RISK_SIGNAL` | Ghi nhận bất thường có nguồn gốc rõ | Đề nghị đánh giá thêm; không tự kết luận gian lận |
| `RECOVERY_PROOF` | Kết quả kiểm chứng một phương thức được chính sách chấp nhận | Được xem xét cho đúng hành động và ngữ cảnh |

Không phân loại dữ kiện tiểu sử thành `RECOVERY_PROOF` chỉ vì nhiều câu trả lời đều đúng.

### 7.2. Không cộng nhiều tín hiệu yếu để vượt điều kiện bắt buộc

Một mô hình chấm điểm dễ tạo lỗi nếu tổng điểm private knowledge có thể bù cho việc thiếu phương thức khôi phục hợp lệ.

```text
Biết tên trường cũ
+ biết địa chỉ giao hàng
+ biết số tiền hóa đơn
→ đủ điểm bỏ MFA
```

Cả ba thông tin có thể đến từ một nguồn đã bị lộ. Tổng điểm không tạo ra quyền kiểm soát yếu tố xác thực.

Thiết kế cần giữ điều kiện bắt buộc riêng: hành động này cần loại bằng chứng nào, bằng chứng có gắn với tài khoản không, đã được kiểm tra độ mới chưa và có phù hợp với tình huống mất yếu tố hiện tại không?

Thông tin sai cũng không nên tự động khóa vĩnh viễn người dùng. Khi dữ liệu gốc có thể cũ hoặc không chính xác, một mâu thuẫn cần được diễn giải trong ngữ cảnh.

## 8. Ví dụ ranh giới ở lớp quyết định

Mã giả dưới đây minh họa cách giữ dữ kiện hỗ trợ tách khỏi kết quả kiểm chứng phương thức khôi phục. Nó không cài đặt một giao thức xác thực cụ thể.

```text
function decideRecovery(case, requestedAction):
    if case.isClosed or case.isExpired:
        return DENY("CASE_NOT_ACTIVE")

    policy = loadPolicyFor(requestedAction)

    # Nạp kết quả đã kiểm chứng ở phía máy chủ.
    # Không nhận cờ passed hoặc proofType tự khai từ trình duyệt.
    proofs = loadVerifiedProofsFor(case.id, case.accountRef)

    eligible = proofs.filter(proof =>
        proof.isFresh
        and proof.isBoundTo(case.id, case.accountRef)
        and proof.covers(requestedAction)
        and policy.accepts(proof.method, case.threatContext)
    )

    # Private knowledge không được chuyển thành proof trong bước này.
    context = loadMinimizedSupportContext(case.id)

    if not policy.requiredRecoveryConditionsMet(eligible):
        return NEED_APPROVED_RECOVERY_PATH("INSUFFICIENT_PROOF")

    if policy.requiresAdditionalReview(case, eligible, context):
        return PENDING_REVIEW

    return READY_FOR_SCOPED_RECOVERY_GRANT
```

Các điều kiện `isFresh`, `isBoundTo` và `covers` cần có ý nghĩa cụ thể trong giao thức thực. Chẳng hạn, một mã dùng cho đặt lại mật khẩu không tự bao gồm quyền thay email hay bỏ MFA.

Đầu ra `READY_FOR_SCOPED_RECOVERY_GRANT` cũng chưa phải session đăng nhập. Khi cấp quyền, hệ thống còn phải kiểm tra lại trạng thái hiện hành, xử lý đồng thời và tiêu thụ bằng chứng dùng một lần theo thiết kế.

Dữ liệu ngữ cảnh chỉ được thu thập khi có mục đích rõ ràng. Đoạn mã không yêu cầu xây thêm kho dữ kiện cá nhân hoặc tiếp tục hỏi câu hỏi bảo mật trong hệ thống mới.

## 9. Chọn đường khôi phục theo bằng chứng và tình huống mất yếu tố

Một dịch vụ có thể thiết kế nhiều đường khôi phục, nhưng mỗi đường cần giải thích được nó chứng minh điều gì.

| Phương án | Điều có thể chứng minh | Điều cần xem xét |
| --- | --- | --- |
| Yếu tố xác thực dự phòng đã đăng ký | Khả năng sử dụng một yếu tố đã gắn với tài khoản | Yếu tố còn đáng tin cậy và được chính sách cho phép dùng cho hành động này không? |
| Mã khôi phục ngẫu nhiên được cấp trước | Có bí mật khôi phục đã gắn với tài khoản | Mã còn hiệu lực, chưa dùng và có thể đã bị lộ cùng thiết bị không? |
| Kênh khôi phục đã xác minh từ trước | Khả năng nhận và trả thử thách qua kênh đó | Kênh có đang bị chiếm hoặc cùng phụ thuộc tài nguyên bị mất không? |
| Chứng minh quyền giữ khóa từ thiết bị đã gắn | Có thể thực hiện thao tác bằng khóa liên quan | Đây có phải kiểm chứng mật mã, hay chỉ là nhận diện trình duyệt dễ sao chép? |
| Quy trình hỗ trợ hoặc xác minh lại có kiểm soát | Tập bằng chứng được đánh giá theo chính sách | Có chứng minh được liên kết với đúng tài khoản và đủ thẩm quyền cho hành động không? |

Bảng này không khẳng định các phương án tương đương nhau hay luôn phù hợp. Cách chọn phụ thuộc tài khoản, hành động, mô hình đe dọa và phương thức đã thiết lập.

Nếu tài khoản chưa từng gắn danh tính ngoài đời, việc người gửi biết nhiều dữ kiện hoặc có một giấy tờ thật không tự chứng minh quyền sở hữu tài khoản. Không tạo mối liên kết còn thiếu bằng chính lời khai đang cần kiểm tra.

Nếu tất cả phương thức có thể dùng đều không đáp ứng yêu cầu, hệ thống có thể cần giữ hoặc từ chối yêu cầu theo quy trình đã công bố. Không thay điều kiện đó bằng một bộ câu hỏi đời tư khó hơn.

Sau khi đủ điều kiện, quyền recovery nên giới hạn tài khoản, mục đích và thời gian. Với token dùng một lần, việc tiêu thụ cần chống sử dụng đồng thời. Việc thay yếu tố bị mất, xử lý session và gửi thông báo bảo mật phải theo chính sách của hành động thực sự được hoàn tất.

## 10. Ba tình huống cần nhận ra

### Tình huống A — Biết hóa đơn vì email đã bị chiếm

Người gửi trả lời đúng ngày mua, số tiền và địa chỉ giao hàng. Cả ba dữ kiện có trong một email hóa đơn.

**Phân tích:** các câu trả lời có tương quan mạnh và không độc lập với kênh email đang có nguy cơ bị chiếm. Thêm câu hỏi về một phần khác của cùng hóa đơn không tạo thêm bằng chứng đáng kể.

**Hướng xử lý:** giữ thông tin ở vai trò hỗ trợ nếu cần; không cho phép bỏ MFA từ kết quả trả lời đúng. Đường khôi phục phải đáp ứng chính sách cho tình huống kênh liên hệ có thể không còn đáng tin cậy.

### Tình huống B — Người quen biết rất nhiều tiểu sử

Người gửi biết trường cũ, tên người thân và địa chỉ thời thơ ấu. Chủ tài khoản không muốn người này có quyền truy cập.

**Phân tích:** một câu hỏi có vẻ riêng tư đối với người lạ vẫn có thể là kiến thức chung trong gia đình hoặc nhóm quen biết. Mức độ thân quen không tạo ra ủy quyền.

**Hướng xử lý:** yêu cầu phương thức chứng minh quyền khôi phục phù hợp. Người hỗ trợ không được bỏ qua điều kiện chỉ vì câu chuyện được kể chi tiết hoặc khớp nhiều dữ kiện.

### Tình huống C — Chủ tài khoản thật không nhớ đáp án cũ

Người dùng không nhớ mình từng nhập tên trường theo dạng viết tắt nào và đã mất thiết bị chứa passkey.

**Phân tích:** thất bại không tự chứng minh gian lận. Cơ chế dựa vào trí nhớ từ nhiều năm trước có thể loại nhầm người dùng thật.

**Hướng xử lý:** cung cấp đường khôi phục được chấp nhận khác nếu có, hoặc quy trình xem xét có giới hạn. Không công khai đáp án cũ, nới tiêu chí dần hoặc khuyến khích đoán cho đến khi vượt ngưỡng.

Ba tình huống cùng cho thấy hai sai lầm: người không có quyền có thể biết đáp án, còn người có quyền có thể không nhớ đáp án.

## 11. Bảo vệ dữ liệu và xử lý hệ thống legacy

### 11.1. Giảm dữ liệu cần giữ

Thu thập thêm thông tin đời tư để làm câu hỏi có thể tạo một kho dữ liệu nhạy cảm mà lợi ích bảo mật hạn chế. Dữ liệu đó còn có thể dùng để trả lời câu hỏi ở dịch vụ khác nếu bị lộ.

Chỉ giữ thông tin có mục đích và thời hạn rõ ràng. Hạn chế người được xem, bảo vệ đường truyền và dữ liệu lưu trữ, tránh sao chép vào công cụ hỗ trợ hoặc phân tích không cần thiết.

Bản ghi quyết định thường cần tham chiếu hồ sơ, phương thức đã kiểm chứng, thời điểm, phiên bản chính sách và lý do. Nó thường không cần lưu nguyên câu trả lời tiểu sử trong log.

### 11.2. Không thay cơ chế legacy bằng một cửa hậu hỗ trợ

Khi bỏ câu hỏi bảo mật khỏi quyền khôi phục, cần cung cấp phương thức phù hợp cho người dùng đang còn xác thực hợp lệ. Thêm hoặc thay phương thức recovery là hành động nhạy cảm và cần kiểm soát tương ứng.

Một quá trình chuyển đổi có thể bao gồm:

1. Xác định những hành động đang được cho phép chỉ nhờ private knowledge.
2. Ngừng tạo đường khôi phục mới dựa trên câu hỏi đó.
3. Cho người dùng đang ở phiên đủ tin cậy thiết lập phương thức recovery được chấp nhận.
4. Xử lý người không còn đăng nhập được bằng quy trình đã phê duyệt, không tự mở ngoại lệ bằng tiểu sử.
5. Loại dữ liệu câu trả lời khỏi mục đích cấp quyền và xóa theo chính sách lưu giữ khi đủ điều kiện.

Việc xác định thứ tự cần xét tác động thực tế để không vô tình làm mất mọi đường khôi phục của người dùng. Tuy nhiên, giữ khả năng hỗ trợ không có nghĩa tiếp tục cấp quyền bằng một bằng chứng không đáp ứng yêu cầu.

### 11.3. Đo đúng kết quả

Tỷ lệ trả lời đúng cao có thể phản ánh câu hỏi dễ đoán, không chỉ phản ánh trải nghiệm tốt. Tỷ lệ hoàn tất recovery cũng chưa cho biết bao nhiêu yêu cầu đến từ đúng chủ tài khoản.

Khi đánh giá hoạt động của quy trình, cần phân biệt khả năng người dùng thật khôi phục được, nguy cơ cấp nhầm quyền và mức độ tiếp xúc dữ liệu nhạy cảm. Dữ liệu theo dõi nên được tối thiểu hóa và kiểm soát truy cập; không xây lại hồ sơ đời tư chỉ để đo hiệu quả của việc bỏ câu hỏi đời tư.

## 12. Các nguyên tắc cần giữ

Kiến thức về một người và quyền truy cập tài khoản của người đó là hai điều khác nhau. Một câu trả lời đúng chỉ có ý nghĩa trong giới hạn của nguồn thông tin và những người có khả năng biết nó.

Nhiều câu trả lời không tạo ra nhiều yếu tố xác thực nếu cùng đến từ một hóa đơn, một hộp thư hoặc một mối quan hệ. Băm, giới hạn thử lại và thông báo trung tính giúp xử lý một số rủi ro kỹ thuật, nhưng không biến dữ kiện tiểu sử thành bằng chứng quyền sở hữu mạnh.

Trong luồng recovery, dữ kiện cá nhân chỉ nên có vai trò hỗ trợ được xác định rõ; chúng không được tự phát token, bỏ MFA, thay passkey hoặc bù cho điều kiện bằng chứng còn thiếu. Quyết định cấp quyền cần dựa trên phương thức được kiểm chứng, gắn với đúng tài khoản, đúng hành động và đúng ngữ cảnh mất yếu tố.

Người dùng thật cần đường khôi phục có thể sử dụng. Đường đó phải được thiết kế và kiểm soát từ trước, thay vì được hình thành tại thời điểm hỗ trợ bằng việc hỏi thêm những điều “chắc chỉ bạn mới biết”.

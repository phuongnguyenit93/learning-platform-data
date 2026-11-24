# Recovery objective

Trong hệ thống xác thực danh tính, **mục tiêu khôi phục (recovery objective)** mô tả mức dịch vụ và trạng thái dữ liệu mà tổ chức phải đưa trở lại sau một sự cố, trong khoảng thời gian đã cam kết. Mục tiêu này trả lời hai câu hỏi cốt lõi: người dùng cần có thể xác thực trở lại sau bao lâu, và hệ thống có thể chấp nhận mất tối đa bao nhiêu dữ liệu hoặc thay đổi đã được ghi nhận?

Đây là một phần của thiết kế tính sẵn sàng (availability) cho module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Phạm vi module bao gồm credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Vì vậy, khôi phục phải bảo đảm cả hai điều kiện: người dùng hợp lệ có thể tiếp tục truy cập, và hệ thống vẫn xác minh đúng danh tính, áp dụng đúng chính sách, từ chối credential đã bị thu hồi và giữ được bằng chứng cần thiết để điều tra.

Một dịch vụ đăng nhập trả về mã HTTP 200 chưa chắc đã được khôi phục. Nếu nó phát hành token bằng khóa không còn đáng tin cậy, chấp nhận mật khẩu cũ sau khi người dùng đã đổi mật khẩu, quên trạng thái thu hồi MFA, hoặc bỏ qua bước kiểm tra rủi ro thì dịch vụ có thể đang hoạt động về mặt kỹ thuật nhưng đã mất tính an toàn. Mục tiêu khôi phục vì thế phải xác định rõ **dịch vụ nào được khôi phục, dữ liệu nào phải nhất quán, hành trình nào phải hoạt động và những kiểm soát bảo mật nào không được hạ thấp**.

## 1. Vì sao xác thực cần mục tiêu khôi phục riêng?

Xác thực thường nằm ở đầu nhiều hành trình nghiệp vụ. Một người không đăng nhập được có thể không truy cập được email, mã nguồn, hệ thống nhân sự, dữ liệu khách hàng hoặc công cụ vận hành. Sự cố ở nhà cung cấp định danh (Identity Provider, IdP) có thể làm gián đoạn nhiều ứng dụng cùng lúc, dù bản thân các ứng dụng vẫn khỏe mạnh.

Ngược lại, khôi phục quá nhanh bằng một bản dữ liệu cũ có thể tạo ra sự cố bảo mật:

- Tài khoản đã bị khóa hoặc vô hiệu hóa lại xuất hiện ở trạng thái đang hoạt động.
- Mật khẩu hoặc chứng chỉ đã bị thu hồi được chấp nhận trở lại.
- Người dùng đã gỡ một thiết bị MFA nhưng thiết bị đó xuất hiện lại sau khi phục hồi.
- Token hoặc phiên đã bị thu hồi tiếp tục được chấp nhận.
- Chính sách yêu cầu MFA, xác minh thiết bị hoặc giới hạn quyền bị quay về cấu hình cũ.
- Sự kiện đăng nhập và thay đổi credential bị mất, khiến đội bảo mật không thể tái dựng diễn biến.
- Khóa ký token cũ được đưa trở lại sử dụng dù khóa đã bị nghi ngờ lộ.

Do đó, mục tiêu khôi phục của xác thực phải cân bằng ba yêu cầu:

1. **Tính sẵn sàng:** khôi phục các hành trình xác thực quan trọng trong thời gian chấp nhận được.
2. **Tính toàn vẹn:** không làm sống lại danh tính, credential, phiên hoặc quyền truy cập đã bị thu hồi.
3. **Khả năng kiểm chứng:** có đủ log, dấu thời gian, phiên bản chính sách và bằng chứng để xác nhận hệ thống sau phục hồi đang hoạt động đúng.

Tính sẵn sàng không đồng nghĩa với việc mọi yêu cầu đều phải được chấp nhận. Khi hệ thống không thể xác minh chữ ký, trạng thái thu hồi hoặc mức bảo đảm danh tính, từ chối có kiểm soát thường an toàn hơn việc cho phép truy cập không có căn cứ.

## 2. Các khái niệm cần phân biệt

### 2.1. Recovery Time Objective (RTO)

**RTO — mục tiêu thời gian khôi phục** là khoảng thời gian tối đa mà tổ chức đặt ra để đưa một dịch vụ hoặc năng lực nghiệp vụ trở lại mức hoạt động đã định sau sự cố.

Với hệ thống xác thực, RTO không nên chỉ đo thời gian máy chủ khởi động. Cần định nghĩa một điều kiện hoàn tất có thể kiểm chứng, chẳng hạn:

- Người dùng thông thường có thể hoàn thành đăng nhập bằng phương thức được phép.
- MFA được xác minh đúng và không bị bỏ qua.
- Token được ký bằng khóa hợp lệ, có issuer, audience và thời hạn đúng.
- Ứng dụng có thể xác minh token và kiểm tra trạng thái thu hồi theo thiết kế.
- Thay đổi credential và chính sách mới nhất vẫn được giữ nguyên.
- Các luồng quản trị đặc quyền và khôi phục tài khoản đáp ứng kiểm soát tương ứng.

Tổ chức phải thống nhất thời điểm bắt đầu tính RTO. Có thể bắt đầu từ lúc dịch vụ thực sự mất khả năng phục vụ, từ lúc hệ thống giám sát phát hiện hoặc từ lúc sự cố được tuyên bố. Dù chọn cách nào, định nghĩa phải được ghi lại để các lần đo có thể so sánh. Cần tách thời gian phát hiện, thời gian quyết định, thời gian phục hồi hạ tầng và thời gian xác nhận nghiệp vụ.

Ví dụ: RTO đăng nhập của nhân viên là 30 phút có nghĩa là trong vòng 30 phút kể từ mốc bắt đầu đã thống nhất, một tỷ lệ yêu cầu đăng nhập đạt điều kiện thành công đã định phải hoạt động trở lại. Nếu chỉ health check của cổng API chuyển sang xanh nhưng không thể hoàn thành MFA thì RTO nghiệp vụ chưa đạt.

### 2.2. Recovery Point Objective (RPO)

**RPO — mục tiêu điểm khôi phục** là lượng dữ liệu hoặc thay đổi tối đa có thể bị mất, thường được biểu diễn bằng khoảng thời gian giữa thời điểm dữ liệu gần nhất có thể khôi phục và thời điểm sự cố xảy ra.

RPO không chỉ là số phút của một bản sao lưu. Với xác thực, cần xác định loại sự kiện nào được phép mất và hậu quả của việc mất sự kiện đó.

Ví dụ:

- Nếu người dùng đổi mật khẩu thành công lúc 10:00 nhưng hệ thống khôi phục về bản dữ liệu 09:55, mật khẩu cũ có thể được chấp nhận lại.
- Nếu quản trị viên thu hồi một chứng chỉ lúc 10:00 nhưng bản phục hồi chỉ chứa trạng thái đến 09:55, chứng chỉ bị thu hồi có thể được tin cậy lại.
- Nếu một phiên bị thu hồi sau khi thiết bị thất lạc nhưng trạng thái thu hồi không được sao chép, phiên đó có thể tiếp tục dùng được.
- Nếu một mã khôi phục dùng một lần không ghi nhận trạng thái đã sử dụng, mã đó có nguy cơ được sử dụng lần thứ hai.

Vì vậy, RPO phải được định nghĩa theo **lớp dữ liệu và mức độ rủi ro**, không nên gán một con số duy nhất cho toàn bộ cơ sở dữ liệu.

RPO bằng 0 thường đòi hỏi cơ chế ghi nhận bền vững đồng bộ hoặc một thiết kế tương đương bảo đảm rằng thay đổi đã được xác nhận không biến mất khi một miền lỗi được giả định xảy ra. Nó không tự động có nghĩa là hệ thống chống được mọi thảm họa: hai bản sao đồng bộ trong cùng một miền lỗi vẫn có thể bị phá hủy cùng nhau, và một thao tác xóa độc hại có thể được nhân bản tức thì.

### 2.3. Maximum Tolerable Downtime và Work Recovery Time

**Maximum Tolerable Downtime (MTD)** hoặc **Maximum Allowable Outage (MAO)** mô tả khoảng gián đoạn tối đa mà nghiệp vụ có thể chịu trước khi hậu quả trở nên không thể chấp nhận. RTO cần thấp hơn giới hạn này và phải chừa thời gian cho các bước nghiệp vụ sau khi kỹ thuật được phục hồi.

**Work Recovery Time (WRT)** là thời gian để khôi phục các công việc tồn đọng sau khi dịch vụ đã hoạt động trở lại, ví dụ xử lý hàng đợi sự kiện, đối soát đăng nhập, hoàn tất yêu cầu hỗ trợ hoặc kiểm tra giao dịch bị treo. Trong thực tế, một hệ thống có thể đạt RTO nhưng vẫn chưa trở lại trạng thái vận hành bình thường nếu hàng đợi còn tồn đọng lớn.

### 2.4. RTO/RPO khác SLO/SLA như thế nào?

| Khái niệm | Câu hỏi chính | Ví dụ trong xác thực |
|---|---|---|
| SLI | Đo điều gì? | Tỷ lệ đăng nhập thành công, độ trễ xác minh MFA |
| SLO | Mức dịch vụ mong muốn trong một cửa sổ đo là bao nhiêu? | 99,9% yêu cầu đăng nhập hợp lệ thành công mỗi tháng |
| SLA | Cam kết dịch vụ với khách hàng hoặc bên liên quan là gì? | Cam kết hỗ trợ hoặc bồi hoàn theo hợp đồng |
| RTO | Sau sự cố, cần khôi phục trong bao lâu? | Khôi phục đăng nhập chính trong 30 phút |
| RPO | Có thể mất tối đa lượng dữ liệu nào? | Không mất sự kiện thu hồi credential đã được xác nhận |

SLO đo chất lượng vận hành trong một khoảng thời gian; RTO/RPO định hướng phục hồi sau sự cố. Một dịch vụ có SLO tốt trong điều kiện bình thường vẫn có thể có kế hoạch khôi phục yếu.

## 3. Xác định đúng phạm vi cần khôi phục

Không nên coi “dịch vụ xác thực” là một khối duy nhất. Hãy phân rã thành các năng lực và hành trình mà người dùng hoặc hệ thống phụ thuộc vào.

| Năng lực | Thành phần thường liên quan | Điều kiện khôi phục cần xác minh |
|---|---|---|
| Đăng nhập chính | Cổng xác thực, kho danh tính, bộ xác minh credential | Tài khoản hợp lệ đăng nhập được bằng phương thức đã đăng ký |
| Xác minh MFA | TOTP, push, phần cứng bảo mật, passkey | Thử thách được kiểm tra đúng; không có đường vòng yếu hơn ngoài chính sách |
| Xác minh chứng chỉ | PKI, CRL/OCSP, kho tin cậy | Chuỗi chứng chỉ và trạng thái thu hồi có thể kiểm tra |
| Phát hành token | Dịch vụ token, HSM/KMS, khóa ký | Token được ký bằng khóa được phép và chứa claim đúng |
| Kiểm tra phiên | Kho phiên, cookie, refresh token, danh sách thu hồi | Phiên bị thu hồi không được tiếp tục sử dụng |
| Liên kết danh tính | SAML, OIDC, OAuth, IdP bên ngoài | Issuer, audience, redirect URI và chữ ký được xác minh đúng |
| Khôi phục tài khoản | Kênh thông báo, xác minh bổ sung, hệ thống hỗ trợ | Chủ thể hợp lệ lấy lại quyền truy cập mà không hạ mức bảo đảm trái phép |
| Quản trị đặc quyền | Tài khoản khẩn cấp, phê duyệt, ghi log | Có thể vận hành khẩn cấp nhưng mọi hành động đều được kiểm soát và kiểm toán |
| Ghi nhận và điều tra | Log bảo mật, sự kiện thay đổi credential, dấu thời gian | Bằng chứng được giữ nguyên, có thể truy xuất và đối soát |

Với mỗi năng lực, cần ghi rõ:

- Người dùng hoặc hệ thống nào phụ thuộc vào năng lực đó.
- Hành trình nào bị dừng nếu năng lực mất.
- Mức quyền và mức bảo đảm danh tính cần thiết.
- Các phụ thuộc trực tiếp và gián tiếp.
- RTO, RPO, điều kiện hoàn tất và người chịu trách nhiệm xác nhận.
- Chế độ suy giảm được phép, nếu có.
- Những thao tác phải tạm khóa trong thời gian phục hồi.

Hãy mô hình hóa cả luồng đăng nhập và luồng thay đổi trạng thái bảo mật. Ví dụ, đăng nhập có thể vẫn chạy khi dịch vụ email gặp sự cố, nhưng khôi phục tài khoản bằng liên kết email có thể không hoạt động. Tương tự, token đã phát hành có thể còn được xác minh trong thời gian IdP ngừng hoạt động, nhưng không thể cấp token mới hoặc thu hồi phiên ngay lập tức. Hai hành trình này cần mục tiêu khác nhau.

## 4. Xây dựng mục tiêu từ tác động nghiệp vụ và rủi ro

Một con số RTO/RPO chỉ hữu ích khi gắn với hậu quả cụ thể. Có thể xác định mục tiêu theo quy trình sau.

### Bước 1: Liệt kê hành trình quan trọng

Bắt đầu từ hành trình người dùng và hệ thống thực sự cần thực hiện: đăng nhập nhân viên, đăng nhập khách hàng, truy cập quản trị, xác minh dịch vụ với dịch vụ, phát hành token, thu hồi phiên và khôi phục tài khoản.

Không mặc định mọi hành trình có cùng độ ưu tiên. Đăng nhập của quản trị viên hạ tầng có thể ảnh hưởng đến khả năng phục hồi các dịch vụ khác. Đăng nhập của người dùng cuối có thể ảnh hưởng trực tiếp đến hoạt động kinh doanh. Xác thực máy với máy có thể cần duy trì để các hệ thống tiếp tục trao đổi dữ liệu.

### Bước 2: Đánh giá tác động theo thời gian

Xác định điều gì xảy ra khi hành trình bị gián đoạn trong 5 phút, 30 phút, 4 giờ hoặc một ngày. Xem xét:

- Doanh thu, vận hành và trải nghiệm người dùng.
- Dịch vụ thiết yếu hoặc hoạt động có thời hạn.
- Khả năng xử lý sự cố của đội vận hành và bảo mật.
- Số lượng tài khoản, ứng dụng và khu vực bị ảnh hưởng.
- Nghĩa vụ pháp lý, hợp đồng và yêu cầu lưu giữ bằng chứng.
- Khả năng chuyển sang phương thức dự phòng an toàn.

Từ đánh giá này, xác định MTD/MAO rồi đặt RTO thấp hơn giới hạn đó. Cần tính thêm thời gian kiểm tra bảo mật và xử lý công việc tồn đọng.

### Bước 3: Phân loại dữ liệu và thao tác

Đối với từng loại dữ liệu, hãy hỏi: nếu mất thay đổi mới nhất thì điều gì có thể xảy ra? Mất dữ liệu hồ sơ hiển thị có thể gây phiền toái; mất trạng thái thu hồi có thể mở lại quyền truy cập. Hai loại dữ liệu này không thể dùng chung một RPO chỉ vì chúng nằm trong cùng cơ sở dữ liệu.

### Bước 4: Xác định điều kiện hoàn tất

Viết điều kiện có thể kiểm tra, không dùng mô tả mơ hồ như “dịch vụ đã lên”. Ví dụ:

- Tỷ lệ đăng nhập thành công của tài khoản thử nghiệm đạt ngưỡng trong một cửa sổ liên tục.
- MFA được thực thi theo chính sách hiện hành.
- Token mới được ký và xác minh đúng.
- Token hoặc phiên trong danh sách thu hồi bị từ chối.
- Không có credential bị thu hồi nào được chấp nhận trong bộ kiểm tra.
- Hàng đợi sự kiện quan trọng không còn vượt ngưỡng cho phép.
- Log bảo mật có dấu thời gian, nguồn và mã tương quan đầy đủ.

### Bước 5: Kiểm tra tính khả thi và chi phí

Mục tiêu RTO/RPO phải tương ứng với kiến trúc, nhân lực, nhà cung cấp và chi phí vận hành. RTO vài phút có thể yêu cầu dự phòng nóng, định tuyến tự động và nhân sự trực. RPO bằng 0 cho một loại dữ liệu có thể cần sao chép đồng bộ và xử lý độ trễ ghi. Nếu tổ chức chọn mục tiêu mà kiến trúc không đáp ứng, mục tiêu đó chỉ là kỳ vọng trên giấy.

### Bước 6: Phê duyệt và xem xét lại

Chủ sở hữu nghiệp vụ chấp nhận tác động gián đoạn; chủ sở hữu dịch vụ chịu trách nhiệm thiết kế kỹ thuật; đội bảo mật đánh giá rủi ro mất hoặc quay lui trạng thái bảo mật; đội vận hành xác nhận khả năng thực hiện runbook. Cập nhật mục tiêu khi thay đổi nhà cung cấp IdP, cách phát hành token, loại credential, vùng triển khai, quy mô người dùng hoặc yêu cầu pháp lý.

## 5. Chọn RPO theo loại dữ liệu xác thực

Các gợi ý dưới đây là nguyên tắc thiết kế, không phải giá trị mặc định áp dụng cho mọi hệ thống. Mục tiêu cụ thể phải được quyết định theo mô hình đe dọa, tác động nghiệp vụ và khả năng kỹ thuật.

| Loại dữ liệu hoặc trạng thái | Hậu quả nếu khôi phục thiếu dữ liệu mới | Hướng đặt RPO |
|---|---|---|
| Trạng thái khóa, vô hiệu hóa tài khoản | Tài khoản bị chặn có thể hoạt động trở lại | RPO bằng 0 hoặc cơ chế bảo đảm trạng thái mới nhất được áp dụng trước khi cấp quyền |
| Thay đổi mật khẩu, thu hồi mật khẩu | Mật khẩu cũ có thể được chấp nhận | RPO bằng 0 cho thay đổi đã xác nhận, hoặc buộc đặt lại credential bị ảnh hưởng trước khi mở truy cập |
| Đăng ký/gỡ bỏ MFA, passkey, thiết bị tin cậy | Thiết bị cũ hoặc yếu có thể được tin cậy lại | RPO rất thấp; trạng thái mới phải được đối soát trước khi xác thực |
| Thu hồi chứng chỉ và khóa | Chứng chỉ hoặc khóa bị thu hồi có thể được chấp nhận | Cần đồng bộ hoặc kiểm tra nguồn thu hồi độc lập, có tính nhất quán mạnh |
| Thu hồi phiên và refresh token | Phiên đã bị thu hồi có thể tiếp tục sống | RPO bằng 0 cho trạng thái thu hồi có tác động cao, hoặc áp dụng thời hạn token ngắn và cơ chế thu hồi đáng tin cậy |
| Chính sách xác thực và phân quyền | Yêu cầu MFA hoặc giới hạn quyền có thể bị quay lui | RPO bằng 0 hoặc quy trình khóa cấp quyền cho đến khi chính sách hiện hành được khôi phục |
| Mã khôi phục dùng một lần và trạng thái đã sử dụng | Mã có thể bị sử dụng lại | RPO bằng 0 đối với thao tác tiêu thụ mã |
| Bộ đếm, nonce và trạng thái chống replay | Thử thách hoặc thông điệp cũ có thể được chấp nhận lại | Không khôi phục nonce đã hết hạn thành trạng thái có thể dùng; phát sinh nonce mới và giữ trạng thái tiêu thụ phù hợp |
| Hồ sơ danh tính không nhạy cảm | Thông tin hiển thị hoặc thuộc tính phụ có thể cũ | Có thể chấp nhận RPO dài hơn nếu không ảnh hưởng quyết định xác thực |
| Log kiểm toán và sự kiện bảo mật | Mất bằng chứng điều tra, không thể đối soát | Mục tiêu gần bằng 0 cho sự kiện quan trọng; dùng kho log độc lập và chống sửa đổi |
| Telemetry và số liệu tổng hợp | Thiếu dữ liệu phân tích | Có thể chấp nhận RPO dài hơn tùy mục đích |

### 5.1. Trạng thái thu hồi phải được ưu tiên

Một quy tắc thiết kế quan trọng là: **khôi phục dữ liệu cũ không được làm sống lại quyền truy cập đã bị thu hồi**.

Có thể thực hiện bằng một hoặc nhiều cách:

- Lưu sự kiện thu hồi trong một kho độc lập với cơ sở dữ liệu chính.
- Ghi nhận thay đổi bảo mật vào log append-only hoặc kho chống sửa đổi.
- Dùng số phiên bản credential hoặc chính sách tăng đơn điệu để phát hiện dữ liệu bị quay lui.
- Sau phục hồi, đối soát danh sách tài khoản bị khóa, credential bị thu hồi, khóa bị vô hiệu hóa và phiên bị chấm dứt.
- Nếu không chứng minh được trạng thái thu hồi mới nhất, tạm từ chối cấp quyền có rủi ro cao cho đến khi đối soát xong.

Một chiến lược khác là ràng buộc token với thời điểm thay đổi bảo mật. Ví dụ, ứng dụng có thể từ chối token được phát hành trước mốc vô hiệu hóa tài khoản hoặc trước phiên bản credential hiện tại. Cách này chỉ hiệu quả nếu mốc thời gian và phiên bản được lưu đáng tin cậy, được phân phối đến các điểm xác minh và không bị quay lui cùng bản sao lưu.

### 5.2. Cẩn trọng với trạng thái chống replay

MFA dựa trên mã dùng một lần, challenge của passkey hoặc các giao thức xác thực có nonce cần xử lý trạng thái tiêu thụ. Một challenge đã được dùng phải không thể được chấp nhận lại chỉ vì hệ thống phục hồi về snapshot cũ.

Với TOTP, hệ thống thường cần kiểm soát việc chấp nhận lại cùng một mã trong cùng cửa sổ thời gian theo chính sách. Với WebAuthn/passkey, challenge phải được tạo mới, gắn với phiên giao dịch và chỉ dùng một lần. Bộ đếm chữ ký của authenticator có thể là tín hiệu phát hiện bất thường trong một số trường hợp, nhưng không nên xem nó là cơ chế chống replay duy nhất cho mọi passkey; một số authenticator đồng bộ có thể không cung cấp bộ đếm tăng đơn điệu hữu ích.

Sau khi phục hồi, không nên tái sử dụng challenge đang dở dang. Hãy hết hạn các giao dịch xác thực chưa hoàn tất và yêu cầu người dùng bắt đầu lại.

## 6. Thiết kế kiến trúc để đạt mục tiêu

### 6.1. Dự phòng theo miền lỗi

Dự phòng cần tách theo miền lỗi thực tế. Hai máy chủ trong cùng một rack không bảo vệ được lỗi rack; hai vùng dùng chung một tài khoản quản trị hoặc một khóa gốc không bảo vệ được sự cố quyền quản trị; hai bản sao trong cùng một vùng không bảo vệ được mất vùng.

Tùy mục tiêu, có thể dùng:

- **Active-active:** nhiều vùng cùng phục vụ lưu lượng. Có thể giảm thời gian chuyển đổi, nhưng cần giải quyết tính nhất quán, định tuyến và xung đột ghi.
- **Active-passive:** vùng dự phòng chờ tiếp quản. Cấu hình đơn giản hơn trong một số hệ thống, nhưng cần đo thời gian phát hiện, chuyển đổi và kiểm tra dữ liệu.
- **Warm standby:** vùng dự phòng đã chạy một phần năng lực, cần mở rộng hoặc hoàn tất đồng bộ trước khi phục vụ.
- **Backup và restore:** phục hồi từ bản sao lưu. Phù hợp với một số loại thảm họa hoặc dữ liệu ít thay đổi, nhưng thường có RTO dài hơn.

Không có mô hình nào tự động tốt nhất. Hãy chọn theo RTO/RPO, mức độ nhất quán cần thiết, chi phí, kỹ năng trực vận hành và khả năng kiểm thử.

### 6.2. Sao chép dữ liệu và nhất quán

Sao chép đồng bộ có thể hỗ trợ RPO rất thấp nhưng tăng độ trễ và phụ thuộc vào khả năng liên lạc giữa các miền. Sao chép bất đồng bộ thường có độ trễ thấp hơn cho giao dịch chính nhưng có thể mất những thay đổi gần nhất khi chuyển vùng.

Với trạng thái bảo mật quan trọng, hãy xem xét:

- Chỉ xác nhận thay đổi thu hồi hoặc thay đổi credential sau khi dữ liệu đã được ghi bền vững theo chính sách.
- Dùng phiên bản tăng đơn điệu hoặc nhật ký sự kiện để phát hiện dữ liệu cũ.
- Phân biệt lỗi không thể ghi nhận với lỗi không thể đọc; không tự động chấp nhận yêu cầu nhạy cảm khi không lưu được trạng thái chống replay.
- Đặt giới hạn độ trễ sao chép và cảnh báo trước khi vượt RPO.
- Có cơ chế giải quyết split-brain. Hai vùng cùng nhận ghi độc lập có thể tạo ra hai trạng thái danh tính khác nhau.
- Ghi lại nguồn dữ liệu và thời điểm đồng bộ cuối cùng để runbook có thể chọn điểm khôi phục có căn cứ.

### 6.3. Sao lưu có thể khôi phục và chống phá hoại

Bản sao lưu chỉ có giá trị khi có thể khôi phục. Với dữ liệu định danh và cấu hình xác thực, nên có:

- Bản sao lưu mã hóa, quyền truy cập tách biệt với quyền vận hành thường ngày.
- Bản sao lưu bất biến hoặc có cơ chế chống xóa/sửa trái phép.
- Bản sao ở miền lỗi hoặc tài khoản quản trị độc lập.
- Lịch sử phiên bản cấu hình và chính sách.
- Kiểm tra tính toàn vẹn, khả năng giải mã và khả năng đọc dữ liệu.
- Diễn tập khôi phục định kỳ trên môi trường cô lập.

Cần bảo vệ cả khóa dùng để mã hóa bản sao lưu. Một bản sao lưu hoàn chỉnh nhưng không thể giải mã khi KMS/HSM chính gặp sự cố không đáp ứng RTO.

### 6.4. Khóa ký, HSM và KMS

Khóa ký token là thành phần đặc biệt nhạy cảm. Khôi phục sai khóa có thể làm hệ thống phát hành token không được tin cậy hoặc khiến các ứng dụng không thể xác minh token hợp lệ.

Thiết kế cần xác định:

- Khóa nào đang hoạt động, khóa nào chỉ dùng để xác minh token cũ và khóa nào đã bị thu hồi.
- Ai có quyền kích hoạt, xuất, sao lưu hoặc phục hồi khóa.
- Quy trình khôi phục khóa trong HSM/KMS và yêu cầu phê duyệt nhiều bên nếu phù hợp.
- Cách phân phối JWKS hoặc chứng thư công khai đến các bên xác minh.
- Thời gian chồng lấn khi xoay vòng khóa.
- Cách xử lý token đã phát hành trước khi chuyển vùng.
- Quy trình ứng phó nếu nghi ngờ khóa riêng bị lộ.

Không nên đơn giản sao chép khóa riêng vào file cấu hình để “dễ khôi phục”. Khóa cần ở trong ranh giới bảo vệ phù hợp, có kiểm soát truy cập, kiểm toán và quy trình phục hồi đã diễn tập. Nếu khóa bị nghi ngờ lộ, ưu tiên thu hồi và xoay khóa theo kế hoạch ứng phó; không phục hồi khóa cũ chỉ để làm dịch vụ chạy nhanh hơn.

### 6.5. Token và phiên

Khôi phục token cần xem xét cả việc phát hành và xác minh:

- Issuer, audience, thuật toán ký và thời hạn token phải đúng.
- Bên xác minh phải có khóa công khai phù hợp và không chấp nhận thuật toán yếu hoặc không được phép.
- Token cũ không được trở nên hợp lệ trở lại sau khi phục hồi.
- Refresh token bị thu hồi phải tiếp tục bị từ chối.
- Cookie phiên cần có thuộc tính bảo mật và chính sách thời hạn đúng.
- Danh sách thu hồi hoặc phiên bản bảo mật phải được đồng bộ đến các dịch vụ xác minh.
- Nếu không thể xác minh trạng thái thu hồi, áp dụng chế độ hạn chế theo mức rủi ro thay vì giả định mọi token đều còn hợp lệ.

Token tự chứa (self-contained token) có thể được xác minh mà không cần truy vấn kho phiên ở mỗi yêu cầu, nhưng việc thu hồi tức thời sẽ khó hơn. Thiết kế có thể dùng thời hạn token ngắn, danh sách thu hồi, phiên bản tài khoản hoặc introspection tùy yêu cầu. Mục tiêu khôi phục cần tính đến độ trễ lan truyền trạng thái thu hồi, không chỉ thời gian khôi phục IdP.

### 6.6. Phụ thuộc bên ngoài

Một luồng xác thực có thể phụ thuộc vào DNS, cân bằng tải, đồng hồ hệ thống, mạng, HSM/KMS, nhà cung cấp MFA, email/SMS, IdP liên kết hoặc dịch vụ đánh giá rủi ro. Hãy ghi rõ phụ thuộc nào là bắt buộc và phụ thuộc nào có thể thay thế.

Đồng hồ hệ thống cần được đồng bộ vì token, chứng chỉ, TOTP và assertion có thời hạn. Sai lệch đồng hồ có thể làm người dùng hợp lệ bị từ chối hoặc mở rộng cửa sổ chấp nhận thông điệp cũ.

Nếu IdP bên ngoài ngừng hoạt động, hệ thống có thể cần chờ nhà cung cấp phục hồi, chuyển sang IdP dự phòng hoặc chỉ duy trì phiên hiện tại. Mỗi lựa chọn có rủi ro khác nhau. Không tự động chuyển sang nhà cung cấp thay thế nếu chưa xác minh issuer, khóa, chính sách, danh tính liên kết và cấu hình redirect.

## 7. Khôi phục tài khoản là một mục tiêu riêng

Trong ngữ cảnh xác thực, từ “recovery” còn chỉ việc một người lấy lại quyền truy cập sau khi mất mật khẩu, mất điện thoại, hỏng khóa bảo mật hoặc không còn yếu tố MFA. Đây là **khôi phục tài khoản (account recovery)**, khác với khôi phục dịch vụ sau thảm họa. Hai loại có thể cùng chịu ảnh hưởng bởi một sự cố nhưng cần mục tiêu và kiểm soát riêng.

Mục tiêu khôi phục tài khoản phải trả lời:

- Người dùng hợp lệ cần lấy lại quyền truy cập trong bao lâu?
- Bằng chứng nào đủ để chứng minh họ là chủ tài khoản?
- Mức bảo đảm sau khôi phục có tương đương trước sự cố không?
- Có cần chờ một khoảng thời gian hoặc phê duyệt bổ sung không?
- Những phiên, token và authenticator nào cần thu hồi?
- Người dùng và đội bảo mật được thông báo bằng kênh nào?
- Hành động khôi phục có được ghi log và có thể điều tra không?

### 7.1. Duy trì nhiều phương thức khôi phục an toàn

Một tài khoản có thể đăng ký nhiều passkey, khóa bảo mật hoặc phương thức MFA độc lập. Mã khôi phục dùng một lần có thể giúp người dùng lấy lại tài khoản khi mất thiết bị, nhưng cần có entropy đủ mạnh, lưu trữ an toàn, chỉ hiển thị khi tạo, chỉ dùng một lần và được bảo vệ bằng giới hạn thử.

Kênh email hoặc SMS có thể hữu ích trong một số bối cảnh nhưng không nên mặc định chúng có cùng mức bảo đảm với passkey hoặc khóa bảo mật. Email có thể bị chiếm quyền; số điện thoại có thể bị chuyển SIM hoặc tái cấp phát. Cần đánh giá rủi ro của từng phương thức và không tự động hạ cấp tài khoản đặc quyền xuống một kênh yếu hơn chỉ để đạt thời gian khôi phục.

### 7.2. Quy trình khôi phục có kiểm soát

Một quy trình mẫu có thể gồm:

1. Tiếp nhận yêu cầu và giới hạn tốc độ để giảm dò đoán hoặc spam.
2. Thu thập bằng chứng theo mức rủi ro, chẳng hạn một authenticator dự phòng, mã khôi phục, thiết bị đã tin cậy hoặc quy trình xác minh danh tính phù hợp.
3. Đánh giá dấu hiệu bất thường: thiết bị mới, vị trí bất thường, thay đổi thông tin liên hệ gần đây hoặc yêu cầu từ tài khoản có quyền cao.
4. Yêu cầu phê duyệt bổ sung hoặc thời gian chờ với thao tác rủi ro cao.
5. Thu hồi authenticator đã mất, phiên hiện có và refresh token khi cần.
6. Đăng ký phương thức xác thực mới bằng một luồng xác minh có ràng buộc.
7. Gửi thông báo qua kênh đã xác minh trước đó nếu có thể.
8. Ghi lại người yêu cầu, người phê duyệt, bằng chứng, thời điểm, thay đổi và kết quả.

Không nên dựa vào câu hỏi bí mật dễ đoán, thông tin công khai hoặc chỉ một cuộc gọi đến bộ phận hỗ trợ như bằng chứng duy nhất cho tài khoản nhạy cảm. Nhân viên hỗ trợ cũng là một phần của ranh giới tin cậy và cần quy trình chống giả mạo, phân quyền, ghi âm/ghi log theo chính sách và phê duyệt độc lập cho hành động đặc quyền.

### 7.3. Định nghĩa mức bảo đảm sau khôi phục

Sau khi tài khoản được khôi phục, không nhất thiết mọi hành động đều phải được mở ngay. Có thể đặt các giới hạn tạm thời cho thao tác thay đổi thông tin thanh toán, thêm authenticator, tạo API key hoặc nâng quyền. Thời gian chờ phải tương xứng với rủi ro và được giải thích rõ cho người dùng.

Điều quan trọng là khôi phục không được trở thành con đường bỏ qua MFA hoặc quy trình chứng minh danh tính. Nếu phương thức mới có mức bảo đảm thấp hơn, hệ thống phải áp dụng giới hạn tương ứng cho đến khi hoàn tất xác minh bổ sung.

## 8. Chế độ suy giảm an toàn khi chưa thể khôi phục đầy đủ

Không phải mọi thành phần đều có thể phục hồi cùng lúc. Có thể thiết kế chế độ suy giảm (degraded mode) để duy trì một phần dịch vụ trong khi bảo toàn ranh giới tin cậy.

Ví dụ:

- Cho phép ứng dụng tiếp tục xác minh token còn hiệu lực bằng khóa công khai đã được phân phối, trong khi IdP tạm thời không phát hành token mới.
- Cho phép người dùng tiếp tục phiên ít rủi ro trong một khoảng thời gian ngắn, nhưng yêu cầu xác thực lại trước hành động nhạy cảm.
- Cho phép đăng nhập người dùng thông thường nhưng tạm khóa thay đổi quyền, đăng ký authenticator mới hoặc thao tác quản trị.
- Chuyển xác thực dịch vụ sang credential dự phòng đã được cấp và kiểm soát từ trước.
- Tạm dừng khôi phục tài khoản nếu kênh chứng minh danh tính không còn đáng tin cậy.

Mỗi chế độ phải có điều kiện kích hoạt, phạm vi người dùng, quyền được phép, thời hạn, người phê duyệt và điều kiện thoát. Không nên bật chế độ suy giảm vô thời hạn.

Có thể dùng nguyên tắc sau:

- **Fail closed** khi không thể xác minh chữ ký, trạng thái thu hồi, danh tính hoặc chính sách cho một hành động nhạy cảm.
- **Degrade safely** khi có thể giới hạn quyền và thời gian mà vẫn giữ đủ căn cứ xác minh.
- **Fail open** chỉ trong trường hợp ngoại lệ đã được đánh giá, giới hạn chặt, có phê duyệt và có kiểm toán; không xem đây là cách mặc định để đạt availability.

### 8.1. Tài khoản khẩn cấp (break-glass)

Một số tổ chức cần tài khoản khẩn cấp để phục hồi IdP hoặc hệ thống quản trị khi cơ chế đăng nhập chính gặp sự cố. Tài khoản này phải được chuẩn bị trước, có phạm vi quyền tối thiểu cần thiết, lưu credential trong kho được kiểm soát độc lập và có cơ chế phê duyệt/giám sát phù hợp.

Sau mỗi lần sử dụng, cần:

- Xác minh lý do và người thực hiện.
- Đối chiếu log của tài khoản với thay đổi hệ thống.
- Xoay vòng credential nếu chính sách yêu cầu.
- Thu hồi phiên và credential tạm thời.
- Kiểm tra tài khoản đã trở về trạng thái bảo vệ bình thường.

Tài khoản break-glass không nên là tài khoản dùng chung không ghi nhận danh tính người thao tác. Nó cũng không nên phụ thuộc hoàn toàn vào chính IdP đang cần phục hồi.

## 9. Ví dụ xây dựng bộ mục tiêu

Giả sử một tổ chức có IdP phục vụ nhân viên, ứng dụng nội bộ và một số dịch vụ máy với máy. Bảng dưới đây chỉ minh họa cách ghi mục tiêu; con số thực tế phải được xác nhận qua phân tích tác động nghiệp vụ và diễn tập.

| Hành trình | RTO minh họa | RPO minh họa | Điều kiện hoàn tất |
|---|---:|---:|---|
| Đăng nhập nhân viên | 30 phút | 0 cho thay đổi credential và chính sách đã xác nhận | Đăng nhập và MFA hoạt động theo chính sách hiện hành |
| Đăng nhập quản trị đặc quyền | 15 phút | 0 cho trạng thái khóa, thu hồi và phân quyền | Đăng nhập bằng yếu tố mạnh; phê duyệt và kiểm toán hoạt động |
| Xác minh token hiện có | 10 phút | Không làm mất trạng thái khóa và thu hồi | Token hợp lệ được xác minh; token bị thu hồi bị từ chối |
| Phát hành token mới | 30 phút | 0 cho trạng thái khóa ký và chính sách phát hành | Khóa hợp lệ, claim đúng, khóa cũ bị xử lý theo kế hoạch |
| Thu hồi phiên | 5 phút | 0 cho sự kiện thu hồi quan trọng | Điểm xác minh nhận trạng thái thu hồi trong giới hạn đã định |
| Khôi phục tài khoản người dùng | 4 giờ | 0 cho trạng thái mã khôi phục đã sử dụng và authenticator bị thu hồi | Người dùng được xác minh và đăng ký yếu tố mới an toàn |
| Log bảo mật quan trọng | Theo mục tiêu điều tra | Gần 0 | Sự kiện quan trọng có thể truy xuất và đối soát |

Giả sử vùng chính gặp sự cố lúc 10:00. Vùng dự phòng có dữ liệu danh tính đồng bộ đến 09:59:58. Tuy nhiên, một sự kiện thu hồi tài khoản lúc 09:59:59 chưa đến vùng dự phòng. Nếu hệ thống chỉ dựa vào bản sao dữ liệu, tài khoản đó có thể được mở lại. Thiết kế an toàn phải có cơ chế nhận biết trạng thái thu hồi chưa đồng bộ, truy vấn nguồn thu hồi độc lập hoặc tạm khóa quyết định cấp quyền liên quan cho đến khi đối soát.

Trong ví dụ này, đạt RTO đăng nhập không có nghĩa là phải cho phép mọi tài khoản đăng nhập ngay. Điều kiện hoàn tất còn bao gồm việc bảo toàn trạng thái bảo mật mới nhất. Nếu chưa xác minh được danh sách thu hồi, hệ thống có thể phục hồi một phần, giới hạn một số hành trình và tiếp tục xử lý cho đến khi đủ bằng chứng.

### 9.1. Ví dụ biểu diễn mục tiêu dưới dạng cấu hình

Cấu hình dưới đây minh họa cách lưu mục tiêu cùng điều kiện nghiệm thu. Đây không phải cấu hình triển khai sẵn; tên trường, giá trị và ngưỡng cần được chuẩn hóa theo hệ thống thực tế.

~~~yaml
service: workforce-authentication
objectives:
  primary_login:
    rto: 30m
    rpo:
      credential_changes: 0s
      authentication_policy: 0s
    completion:
      - valid_user_can_complete_mfa
      - current_policy_is_enforced
      - revoked_credentials_are_rejected

  privileged_login:
    rto: 15m
    rpo:
      account_disable_state: 0s
      role_and_permission_changes: 0s
    completion:
      - strong_authentication_is_available
      - privileged_actions_are_audited

  session_revocation:
    rto: 5m
    rpo:
      revocation_events: 0s
    completion:
      - revoked_sessions_are_rejected_by_all_required_verifiers

  account_recovery:
    rto: 4h
    assurance:
      - identity_evidence_is_checked
      - lost_authenticators_are_revoked
      - new_authenticator_is_bound_to_verified_account
    completion:
      - user_is_not_downgraded_below_approved_assurance
      - recovery_event_is_auditable
~~~

Giá trị RPO bằng 0 trong ví dụ là yêu cầu thiết kế đối với thay đổi bảo mật quan trọng. Đội triển khai phải chứng minh cách đạt yêu cầu đó bằng cơ chế lưu bền vững, sao chép, đối soát hoặc kiểm soát chặn cấp quyền. Viết giá trị này vào YAML không tự tạo ra tính nhất quán.

## 10. Quy trình phục hồi trong một sự cố

Một runbook tốt giúp đội vận hành khôi phục có trật tự và không bỏ qua kiểm soát bảo mật. Có thể tổ chức quy trình theo các giai đoạn sau.

### Giai đoạn 1: Phát hiện và khoanh vùng

- Xác nhận phạm vi: một vùng, một thành phần, toàn bộ IdP hay một nhà cung cấp bên ngoài.
- Phân biệt lỗi availability với dấu hiệu xâm nhập hoặc phá hoại dữ liệu.
- Ghi lại mốc thời gian bắt đầu ảnh hưởng và mốc tuyên bố sự cố theo định nghĩa RTO.
- Ngăn các thao tác quản trị hoặc ghi dữ liệu không kiểm soát nếu có nguy cơ split-brain.
- Bảo toàn log, snapshot và bằng chứng liên quan.

Nếu nghi ngờ kẻ tấn công có quyền ghi vào hệ thống, không nên lập tức sao chép trạng thái hiện tại sang vùng sạch. Trước hết cần xác định điểm khôi phục đáng tin cậy và kiểm tra tính toàn vẹn.

### Giai đoạn 2: Chọn phương án và điểm khôi phục

- Xác định failover sang vùng dự phòng hay restore từ bản sao lưu.
- Kiểm tra thời điểm đồng bộ cuối cùng và độ trễ so với RPO.
- Kiểm tra nguồn trạng thái thu hồi độc lập, phiên bản chính sách và các thay đổi credential gần nhất.
- Xác định khóa ký nào còn được phép dùng, khóa nào phải thu hồi.
- Xác định các hành trình có thể mở lại và các hành trình phải tạm khóa.

Không chọn snapshot chỉ vì nó mới nhất. Snapshot mới nhất có thể chứa dữ liệu bị phá hoại hoặc cấu hình đã bị thay đổi trái phép.

### Giai đoạn 3: Phục hồi theo thứ tự phụ thuộc

Thứ tự thực tế tùy kiến trúc, nhưng thường cần xác nhận các nền tảng như DNS, mạng, thời gian hệ thống, HSM/KMS, kho dữ liệu, dịch vụ danh tính và các điểm xác minh token. Khôi phục khóa và chính sách phải được thực hiện theo quy trình có phê duyệt. Sau đó mới mở các luồng phát hành token, đăng nhập và thay đổi credential.

Các dịch vụ phụ thuộc cần nhận cấu hình issuer, khóa công khai, endpoint và trạng thái thu hồi chính xác. Tránh để một số vùng xác minh bằng JWKS cũ trong khi vùng khác đã chuyển sang khóa mới mà không có kế hoạch chuyển tiếp.

### Giai đoạn 4: Đối soát trạng thái bảo mật

Trước khi mở toàn bộ lưu lượng, kiểm tra:

- Tài khoản bị khóa hoặc vô hiệu hóa.
- Mật khẩu, chứng chỉ, passkey và authenticator bị thu hồi.
- Phiên, refresh token và API key bị thu hồi.
- Chính sách MFA, quyền và điều kiện truy cập.
- Khóa ký đang hoạt động và khóa đã bị thu hồi.
- Mã khôi phục đã sử dụng.
- Thử thách xác thực đang chờ; hết hạn các challenge không thể chứng minh trạng thái.
- Log sự kiện và chênh lệch giữa vùng chính với vùng dự phòng.

Nếu không thể đối soát một nhóm trạng thái quan trọng, giới hạn phạm vi mở dịch vụ tương ứng. Ví dụ, có thể mở xác minh token cho một nhóm ứng dụng trong khi giữ chức năng cấp quyền quản trị ở trạng thái khóa.

### Giai đoạn 5: Kiểm tra hành trình đầu cuối

Dùng tài khoản thử nghiệm đại diện cho các nhóm người dùng và mức quyền. Kiểm tra cả trường hợp thành công lẫn từ chối:

- Tài khoản hợp lệ đăng nhập bằng phương thức dự kiến.
- Người dùng phải hoàn tất MFA khi chính sách yêu cầu.
- Mật khẩu cũ bị từ chối sau khi đổi mật khẩu.
- Authenticator đã gỡ hoặc thu hồi bị từ chối.
- Token sai issuer, audience, chữ ký hoặc hết hạn bị từ chối.
- Phiên đã thu hồi không thể tiếp tục truy cập.
- Người dùng không có quyền không thể truy cập tài nguyên đặc quyền.
- Luồng khôi phục tài khoản yêu cầu đúng bằng chứng và ghi nhận đầy đủ.
- Sự kiện bảo mật được chuyển đến hệ thống log.

Health check hạ tầng chỉ là một phần của kiểm tra. Cần kiểm tra hành trình từ điểm vào của người dùng đến nơi ứng dụng quyết định cho phép hoặc từ chối.

### Giai đoạn 6: Mở lưu lượng có kiểm soát và theo dõi

Mở lưu lượng theo từng nhóm hoặc từng vùng nếu kiến trúc cho phép. Theo dõi tỷ lệ thành công, lỗi xác minh chữ ký, độ trễ MFA, độ trễ đồng bộ thu hồi, số lần đăng nhập bất thường và tải của hệ thống.

Giữ chế độ hạn chế cho các thao tác có rủi ro cao cho đến khi đội chịu trách nhiệm xác nhận trạng thái. Ghi lại thời điểm từng hành trình được phục hồi để tính RTO riêng, thay vì chỉ dùng một thời điểm chung cho toàn bộ hệ thống.

### Giai đoạn 7: Đối soát sau phục hồi

- Xử lý hàng đợi sự kiện và yêu cầu đang chờ theo quy tắc idempotency.
- Tìm các thay đổi có thể bị mất trong khoảng RPO.
- Kiểm tra token hoặc phiên có thể đã được chấp nhận trong thời gian gián đoạn.
- Thông báo cho người dùng bị ảnh hưởng và yêu cầu đăng ký lại yếu tố khi cần.
- Đối chiếu log giữa các vùng và hệ thống phụ thuộc.
- Ghi nhận RTO/RPO thực tế, các điều kiện chưa đạt và hành động khắc phục.

## 11. Đo lường và kiểm thử mục tiêu

Không thể khẳng định RTO/RPO đạt được chỉ dựa vào tài liệu kiến trúc. Phải đo trong diễn tập và sự cố thực tế.

### 11.1. Chỉ số nên theo dõi

| Nhóm | Chỉ số ví dụ | Mục đích |
|---|---|---|
| Đăng nhập | Tỷ lệ đăng nhập hợp lệ thành công, độ trễ p95/p99 | Phát hiện suy giảm hành trình chính |
| MFA | Tỷ lệ hoàn tất, lỗi nhà cung cấp, thời gian phản hồi | Phân biệt lỗi IdP và lỗi yếu tố thứ hai |
| Token | Tỷ lệ phát hành/xác minh, lỗi chữ ký, lỗi issuer/audience | Xác nhận đường phát hành và xác minh |
| Thu hồi | Độ trễ lan truyền sự kiện thu hồi, số điểm xác minh chưa cập nhật | Kiểm tra nguy cơ phiên cũ tiếp tục hoạt động |
| Sao chép | Replication lag, lỗi ghi, thời điểm đồng bộ cuối | Đánh giá RPO thực tế |
| Khôi phục | Thời gian từ ảnh hưởng đến hành trình đầu cuối hoạt động | Đánh giá RTO thực tế |
| Khóa | Trạng thái HSM/KMS, lỗi ký, lỗi truy cập khóa | Xác nhận khả năng sử dụng khóa hợp lệ |
| Kiểm toán | Độ trễ log, sự kiện thiếu, chênh lệch dấu thời gian | Bảo toàn khả năng điều tra |

Không chỉ đo trung bình. Các đuôi phân phối như p95/p99 và tỷ lệ lỗi theo vùng, nhà cung cấp, phương thức MFA hoặc nhóm người dùng thường bộc lộ vấn đề mà số trung bình che khuất.

### 11.2. Diễn tập theo tình huống

Nên kiểm thử ít nhất các tình huống:

- Mất một máy chủ xác thực.
- Mất một vùng hoặc kết nối liên vùng.
- Kho danh tính không khả dụng.
- HSM/KMS hoặc đường truy cập khóa gặp sự cố.
- Nhà cung cấp MFA hoặc email không phản hồi.
- DNS hoặc đồng hồ hệ thống sai lệch.
- Bản sao dữ liệu có độ trễ vượt RPO.
- Khôi phục từ bản sao lưu sau khi dữ liệu bị xóa hoặc sửa trái phép.
- Phát hiện khóa ký bị lộ và cần xoay khóa.
- Sự kiện thu hồi không được nhân bản đến vùng dự phòng.
- Người dùng mất thiết bị MFA trên diện rộng.

Trong mỗi lần diễn tập, hãy ghi lại mốc thời gian, quyết định, thao tác, lỗi, kết quả kiểm tra và thời gian khôi phục từng hành trình. Kiểm thử cả điều kiện từ chối để chắc chắn hệ thống không trở nên “dễ đăng nhập hơn” sau phục hồi.

### 11.3. Tiêu chí một cuộc diễn tập đạt

Một cuộc diễn tập chỉ đạt khi:

- Hành trình mục tiêu phục hồi trong RTO đã định.
- Dữ liệu quan trọng không vượt RPO.
- Trạng thái thu hồi và chính sách hiện hành được giữ nguyên.
- Khóa và token được xác minh theo đúng quy tắc.
- Không xuất hiện đường vòng MFA hoặc hạ mức bảo đảm ngoài phê duyệt.
- Log và bằng chứng cần thiết được lưu.
- Đội vận hành có thể thực hiện runbook bằng quyền và tài liệu đã chuẩn bị.
- Các phụ thuộc và giới hạn còn tồn tại được ghi thành hành động có chủ sở hữu.

## 12. Những sai lầm thường gặp

**Chỉ đặt RTO cho máy chủ.** Máy chủ chạy không chứng minh đăng nhập, MFA, phát hành token và thu hồi phiên đã hoạt động. Hãy đo hành trình nghiệp vụ đầu cuối.

**Dùng một RPO cho toàn bộ dữ liệu.** Hồ sơ hiển thị, log kiểm toán, trạng thái thu hồi và khóa ký có hậu quả khác nhau khi mất dữ liệu. Phân loại theo rủi ro.

**Chỉ kiểm tra bản sao lưu có tồn tại.** Bản sao lưu có thể bị hỏng, thiếu khóa giải mã hoặc không tương thích với phiên bản phần mềm. Phải thử phục hồi và kiểm tra kết quả.

**Cho rằng sao chép đồng bộ giải quyết mọi rủi ro.** Sao chép đồng bộ có thể nhân bản lỗi hoặc hành động độc hại. Cần bản sao bất biến, kiểm soát quyền và điểm khôi phục đáng tin cậy.

**Khôi phục snapshot cũ mà không đối soát thu hồi.** Điều này có thể mở lại tài khoản, credential hoặc phiên đã bị chặn. Trạng thái bảo mật mới nhất phải được đối soát trước khi cấp quyền.

**Bỏ qua khóa ký và HSM/KMS.** Có dữ liệu danh tính mà không có khóa hợp lệ thì chưa thể phát hành token an toàn. Khôi phục khóa cần được diễn tập riêng.

**Dùng fail-open để tăng availability.** Nếu không xác minh được chữ ký, danh tính hoặc chính sách, cho phép truy cập có thể biến sự cố availability thành sự cố xâm nhập.

**Đồng nhất account recovery với disaster recovery.** Khôi phục tài khoản cần xác minh chủ thể và giữ mức bảo đảm; khôi phục dịch vụ cần đưa hạ tầng và dữ liệu về trạng thái vận hành. Cần mục tiêu và quy trình riêng.

**Không tính phụ thuộc bên ngoài.** IdP có thể khỏe nhưng DNS, HSM, nhà cung cấp MFA hoặc đồng hồ hệ thống bị lỗi. Sơ đồ phụ thuộc phải phản ánh toàn bộ đường đi của yêu cầu.

**Không diễn tập theo tình huống tấn công.** Chỉ thử mất máy chủ sẽ bỏ sót rủi ro xóa dữ liệu, lộ khóa, sửa chính sách hoặc làm mất trạng thái thu hồi.

## 13. Checklist thiết kế

Trước khi phê duyệt mục tiêu khôi phục cho một hệ thống xác thực, hãy xác nhận:

- [ ] Đã liệt kê các hành trình đăng nhập, MFA, token, phiên, liên kết danh tính và khôi phục tài khoản.
- [ ] Mỗi hành trình có chủ sở hữu, mức độ quan trọng và điều kiện hoàn tất rõ ràng.
- [ ] RTO có mốc bắt đầu, mốc kết thúc và cách đo thống nhất.
- [ ] RPO được đặt theo lớp dữ liệu và thao tác bảo mật.
- [ ] Trạng thái khóa tài khoản, thu hồi credential, thu hồi phiên và chính sách không bị quay lui ngoài ý muốn.
- [ ] Khóa ký, HSM/KMS, JWKS và quy trình xoay khóa có phương án phục hồi.
- [ ] DNS, mạng, thời gian hệ thống, MFA và IdP bên ngoài nằm trong bản đồ phụ thuộc.
- [ ] Có bản sao lưu bất biến hoặc biện pháp tương đương, quyền truy cập độc lập và kiểm tra khả năng giải mã.
- [ ] Có chế độ suy giảm với phạm vi, thời hạn, quyền và điều kiện thoát được xác định.
- [ ] Tài khoản break-glass được kiểm soát và không phụ thuộc hoàn toàn vào dịch vụ đang phục hồi.
- [ ] Quy trình khôi phục tài khoản giữ mức bảo đảm danh tính và ghi nhận đầy đủ.
- [ ] Runbook bao gồm đối soát trạng thái thu hồi và kiểm tra cả trường hợp cho phép lẫn từ chối.
- [ ] Diễn tập đã đo RTO/RPO thực tế và tạo hành động khắc phục có chủ sở hữu.

## 14. Kết luận

Mục tiêu khôi phục cho xác thực phải mô tả thời gian phục hồi, điểm dữ liệu có thể chấp nhận và điều kiện an toàn để mở lại từng hành trình. RTO cho biết hệ thống cần hoạt động trở lại khi nào; RPO cho biết thay đổi nào có thể bị mất; các điều kiện nghiệm thu chứng minh việc phục hồi không làm suy yếu xác minh danh tính, chính sách, trạng thái thu hồi hoặc khả năng kiểm toán.

Một thiết kế tốt bắt đầu từ hành trình nghiệp vụ, phân loại dữ liệu theo hậu quả bảo mật, bảo vệ khóa và trạng thái thu hồi, rồi xác nhận bằng diễn tập. Khi chưa thể chứng minh một quyết định xác thực là đáng tin cậy, hệ thống cần giới hạn quyền hoặc tạm từ chối hành động nhạy cảm. Khôi phục chỉ hoàn tất khi người dùng hợp lệ có thể tiếp tục công việc và hệ thống vẫn nhận biết chính xác ai được phép truy cập, bằng credential nào và theo chính sách nào.


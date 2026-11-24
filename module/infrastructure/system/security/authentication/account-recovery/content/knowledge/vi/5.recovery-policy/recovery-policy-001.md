# Quyền sở hữu và rà soát chính sách khôi phục tài khoản

Một luồng khôi phục tài khoản không chỉ là chức năng gửi email đặt lại mật khẩu. Nó quyết định ai được cấp lại quyền truy cập khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Quyết định ấy có thể làm thay đổi chủ thể đang kiểm soát tài khoản, nên cần một chính sách có người chịu trách nhiệm rõ ràng và được rà soát trong suốt vòng đời sản phẩm.

Trong chương **Recovery Policy** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, bài học này tập trung vào **Policy ownership and review**: ai sở hữu chính sách, ai được thay đổi nó, bằng chứng nào dùng để đánh giá và điều gì phải xảy ra khi chính sách không còn phù hợp.

Các tình huống, vai trò và ngưỡng trong bài là ví dụ thiết kế. Tổ chức cần điều chỉnh theo tài sản, năng lực vận hành và mức rủi ro của mình; chúng không phải một bộ yêu cầu áp dụng giống nhau cho mọi dịch vụ.

Sau bài học, người học có thể:

- Phân biệt người chịu trách nhiệm về chính sách với người triển khai và người xử lý yêu cầu recovery.
- Lập phạm vi, ma trận trách nhiệm và quy trình thay đổi chính sách.
- Thiết kế lịch rà soát cùng các tác nhân kích hoạt rà soát ngoài lịch.
- Quản lý ngoại lệ có thời hạn mà không biến hỗ trợ khách hàng thành đường bỏ qua kiểm soát.
- Đối chiếu tài liệu, cấu hình và hành vi thực tế để phát hiện chính sách bị thực thi sai.

## 1. Vì sao chính sách recovery cần một chủ sở hữu?

Hãy xét một dịch vụ có ba thay đổi diễn ra độc lập:

1. Nhóm phát triển bổ sung passkey và coi đây là phương thức đăng nhập ưu tiên.
2. Nhóm hỗ trợ vẫn dùng hướng dẫn cũ: nhận email từ đúng địa chỉ là đủ để xóa mọi yếu tố xác thực.
3. Nhóm vận hành tăng thời hạn token recovery để giảm số yêu cầu gửi lại thư.

Mỗi nhóm có thể đang giải quyết một vấn đề có thật. Nhưng khi kết hợp, dịch vụ có thể cho phép người kiểm soát hộp thư bỏ qua passkey, đồng thời kéo dài khoảng sử dụng token. Không ai chủ động phê duyệt toàn bộ mức rủi ro mới.

Thiếu ownership thường biểu hiện ở những câu nói như:

- “Đó là quy tắc trong hệ thống cũ.”
- “Nhóm hỗ trợ vẫn xử lý như vậy từ trước.”
- “Chỉ thay cấu hình, không thay chính sách.”
- “Nhóm bảo mật đã góp ý rồi, chắc họ chịu trách nhiệm.”
- “Cần khôi phục tài khoản trước, hồ sơ ngoại lệ bổ sung sau.”

Một chủ sở hữu rõ ràng giúp biến các quyết định rời rạc thành một chính sách thống nhất. Tuy nhiên, có tên chủ sở hữu trong tài liệu chưa đủ; người đó phải có thẩm quyền quyết định, cơ chế phối hợp và trách nhiệm theo dõi việc thực thi.

### Ownership không có nghĩa là một người tự quyết mọi việc

Người sở hữu chính sách chịu trách nhiệm cuối cùng về việc chính sách đầy đủ, nhất quán, có người vận hành và được cập nhật đúng hạn. Họ vẫn cần các vai trò khác xác nhận những phần thuộc chuyên môn và thẩm quyền của mình.

Ví dụ, chủ sở hữu không thể đơn phương tuyên bố hệ thống đã thu hồi mọi refresh token nếu nhóm kỹ thuật chưa có khả năng thực hiện điều đó. Người chấp nhận rủi ro cũng phải nằm trong cấp thẩm quyền được tổ chức xác lập, thay vì được suy ra từ việc người đó viết tài liệu.

## 2. Phân biệt chính sách, tiêu chuẩn kỹ thuật và runbook

Ba loại tài liệu này liên quan nhưng không thay thế nhau.

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong recovery |
|---|---|---|
| Chính sách | Điều gì được phép, bị cấm, cần bằng chứng gì và ai có quyền quyết định? | Không xóa yếu tố xác thực mạnh chỉ dựa vào email khi phân khúc tài khoản đòi hỏi bằng chứng độc lập |
| Tiêu chuẩn hoặc thiết kế kỹ thuật | Hệ thống phải thực hiện quy tắc bằng cơ chế nào? | Token ràng buộc đúng mục đích, giới hạn thời gian, dùng một lần bằng thao tác nguyên tử |
| Runbook vận hành | Nhân viên hoặc trực vận hành xử lý một tình huống cụ thể như thế nào? | Các bước tiếp nhận người dùng mất MFA, thu thập bằng chứng được phép và chuyển cấp khi không đủ điều kiện |
| Cấu hình triển khai | Giá trị và nhánh hành vi nào đang có hiệu lực? | Ngưỡng giới hạn tần suất, loại bằng chứng chấp nhận, thời gian chờ theo từng nhóm tài khoản |

Chính sách nên đủ cụ thể để đưa ra quyết định, nhưng không cần chép toàn bộ mã nguồn hay hướng dẫn thao tác.

Ngược lại, một cấu hình có thể làm thay đổi chính sách trên thực tế. Giảm yêu cầu bằng chứng, cho phép bỏ MFA qua hỗ trợ hoặc mở rộng quyền của recovery session đều cần được đánh giá theo tác động, kể cả khi không sửa tài liệu có tên “policy”.

Một cấu trúc dễ duy trì là:

> Quy tắc chính sách → kiểm soát kỹ thuật hoặc vận hành → bằng chứng kiểm tra → người chịu trách nhiệm.

Ví dụ:

> Chỉ dùng token recovery một lần → kiểm tra và tiêu thụ nguyên tử → kiểm thử hai yêu cầu đồng thời và sự kiện sử dụng token → chủ sở hữu triển khai xác thực.

Liên kết này giúp người rà soát biết cần tìm bằng chứng ở đâu, thay vì chỉ đọc một tuyên bố chung rằng “recovery phải an toàn”.

## 3. Xác lập phạm vi trước khi phân trách nhiệm

Một chính sách chỉ nói “khôi phục tài khoản” dễ bỏ sót những đường vào khác nhau. Phạm vi cần liệt kê rõ:

- Đặt lại mật khẩu.
- Mất MFA hoặc mã dự phòng.
- Mất passkey, thiết bị chứa passkey hoặc quyền truy cập tài khoản đồng bộ liên quan.
- Mất hoặc thay email, số điện thoại và kênh recovery.
- Khôi phục qua hỗ trợ, quản trị viên hoặc một cổng tự phục vụ khác.
- Đăng ký yếu tố mới, xử lý yếu tố cũ và session sau recovery.
- Tranh chấp quyền sở hữu hoặc nghi ngờ tài khoản đã bị chiếm đoạt.

Cũng cần phân biệt loại tài khoản và hành động. Tài khoản quản trị, tài khoản khách hàng thông thường và tài khoản do tổ chức quản lý có thể có yêu cầu khác nhau.

Nếu xác thực do nhà cung cấp danh tính bên ngoài thực hiện, cần chỉ rõ trách nhiệm ở ranh giới liên kết: bên nào khôi phục danh tính, bên nào gán lại quyền trong ứng dụng, bên nào thông báo và thu hồi session cục bộ. Không mặc định việc nhà cung cấp đã recovery một tài khoản đồng nghĩa mọi quyết định cấp quyền của ứng dụng đều đã được xử lý.

### Đặt câu hỏi theo kết quả quyền hạn

Với từng nhánh, hãy ghi rõ:

1. Người yêu cầu cần chứng minh điều gì?
2. Bằng chứng nào được chấp nhận và chúng có độc lập với yếu tố đã mất không?
3. Sau khi đạt điều kiện, họ được thay đổi gì?
4. Khi nào được tạo session, session có quyền gì?
5. Yếu tố và quyền truy cập tồn tại trước đó được xử lý ra sao?
6. Ai có quyền xử lý trường hợp không đủ bằng chứng?
7. Dấu vết nào cần lưu để có thể giải thích quyết định?

Phạm vi kết thúc ở việc cấp lại quyền và xử lý hậu quả, không chỉ ở màn hình thông báo “đặt lại mật khẩu thành công”.

## 4. Các vai trò cần có và thẩm quyền tương ứng

Tên chức danh có thể khác nhau giữa tổ chức. Điều cần giữ là trách nhiệm và quyền quyết định không bị bỏ trống.

| Vai trò | Trách nhiệm chính | Giới hạn cần rõ |
|---|---|---|
| Chủ sở hữu chính sách | Duy trì phạm vi, tổ chức rà soát, điều phối thay đổi và theo dõi vấn đề chưa xử lý | Không tự xác nhận mọi kiểm soát kỹ thuật hoặc nhận thay mọi thẩm quyền chấp nhận rủi ro |
| Chủ sở hữu kỹ thuật | Chuyển quy tắc thành thiết kế, cấu hình, kiểm thử và cơ chế giám sát | Không âm thầm hạ yêu cầu bằng chứng để làm luồng chạy được |
| Đại diện an ninh | Đánh giá mô hình đe dọa, tính độc lập của bằng chứng và nguy cơ chiếm đoạt | Không thay thế trách nhiệm sản phẩm và vận hành chỉ bằng một lần góp ý |
| Chủ sở hữu vận hành hỗ trợ | Duy trì runbook, đào tạo, phân quyền và chất lượng xử lý thủ công | Không tự tạo một hình thức xác minh ngoài chính sách |
| Chủ sở hữu sản phẩm hoặc dịch vụ | Đánh giá tác động người dùng, khả năng tiếp cận và nhu cầu phục hồi | Không lấy tỷ lệ recovery thành công làm tiêu chí duy nhất |
| Người có thẩm quyền chấp nhận rủi ro | Quyết định chấp nhận rủi ro còn lại trong phạm vi được giao | Phải ghi rõ phạm vi, lý do và thời hạn khi cần |
| Đại diện dữ liệu, quyền riêng tư hoặc pháp chế khi liên quan | Đánh giá việc thu thập bằng chứng danh tính, truy cập và lưu giữ dữ liệu | Chỉ tham gia theo vấn đề thực tế; không biến mọi recovery thành thu thập tài liệu nhạy cảm |
| Vận hành hệ thống hoặc ứng phó sự cố | Theo dõi triển khai, xử lý lỗi và kích hoạt cơ chế khẩn cấp | Không mở một đường cấp quyền yếu hơn chỉ để khôi phục độ sẵn sàng |

Ở nhóm nhỏ, một người có thể kiêm nhiều vai trò. Cần ghi nhận việc kiêm nhiệm và bố trí người kiểm tra độc lập cho thay đổi nhạy cảm khi phù hợp, thay vì tạo cảm giác có nhiều lớp xét duyệt trong khi tất cả đều do một người thực hiện.

### Ví dụ ma trận RACI

Trong ma trận dưới đây:

- **A — Accountable:** vai trò chịu trách nhiệm cuối cùng cho kết quả của hoạt động.
- **R — Responsible:** vai trò trực tiếp thực hiện.
- **C — Consulted:** vai trò được tham vấn.
- **I — Informed:** vai trò được thông báo.

Mỗi hàng xác định một A để tránh trách nhiệm cuối cùng bị phân tán. Thẩm quyền của từng A phải phù hợp với cơ chế quản trị thực tế.

| Hoạt động | Chủ chính sách | Kỹ thuật | An ninh | Hỗ trợ | Sản phẩm | Thẩm quyền rủi ro |
|---|---|---|---|---|---|---|
| Duy trì phạm vi và lịch rà soát | A/R | C | C | C | C | I |
| Đánh giá nguy cơ của thay đổi | A | R | R | C | C | C |
| Xác nhận triển khai đáp ứng quy tắc | C | A/R | C | C | I | I |
| Cập nhật runbook và đào tạo | C | C | C | A/R | I | I |
| Phê duyệt chấp nhận rủi ro vượt giới hạn thông thường | R | C | C | C | C | A |
| Công bố phiên bản chính sách đã đủ phê duyệt | A/R | C | C | C | I | I |
| Thực hiện rà soát định kỳ | A/R | R | R | R | C | C |

Ma trận này không có nghĩa một dấu A tự thay thế mọi cổng phê duyệt. Ví dụ, chủ chính sách chịu trách nhiệm công bố nhưng vẫn phải có quyết định chấp nhận rủi ro bắt buộc trước khi công bố.

## 5. Hồ sơ tối thiểu của một chính sách recovery

Một hồ sơ hữu ích cần đủ thông tin để người khác tiếp quản mà không phải suy đoán ý định ban đầu.

| Trường | Nội dung cần ghi |
|---|---|
| Định danh và phiên bản | Mã ổn định của chính sách, phiên bản nội dung và trạng thái |
| Mục tiêu bảo vệ | Tài sản, hành động và rủi ro chiếm đoạt cần kiểm soát |
| Phạm vi | Dịch vụ, loại tài khoản, kênh và nhánh recovery |
| Chủ sở hữu và người thay thế | Vai trò có thẩm quyền, cách liên hệ và người tiếp nhận khi vắng mặt |
| Quy tắc quyết định | Bằng chứng, hạn chế, thời gian chờ nếu có và điều kiện từ chối |
| Quyền phê duyệt | Ai được phê duyệt thay đổi, ngoại lệ và rủi ro còn lại |
| Liên kết thực thi | Cấu hình, thiết kế, runbook và kiểm thử liên quan |
| Bằng chứng rà soát | Quyết định, phát hiện, hành động và kết quả kiểm tra |
| Hiệu lực | Thời điểm bắt đầu áp dụng và cách xử lý hồ sơ đang chạy |
| Lịch rà soát | Hạn tiếp theo, tác nhân kích hoạt và người tổ chức |
| Lịch sử thay đổi | Nội dung thay đổi, lý do, người phê duyệt và phạm vi ảnh hưởng |

### Ví dụ một hồ sơ rút gọn

~~~text
Policy ID: AR-POL-01
Tên: Khôi phục quyền truy cập khi mất yếu tố xác thực
Phạm vi: Tài khoản cá nhân; tự phục vụ và hỗ trợ
Chủ sở hữu: Vai trò phụ trách nền tảng danh tính
Chủ triển khai: Vai trò phụ trách dịch vụ Authentication
Chủ vận hành: Vai trò phụ trách hỗ trợ tài khoản
Trạng thái: Bản đề xuất, chưa có hiệu lực

Quy tắc:
- Email proof không tự cấp quyền xóa mọi MFA/passkey.
- Hành động nhạy cảm cần đúng tập bằng chứng được phê duyệt.
- Recovery context có quyền hạn thấp và gắn với đúng hồ sơ.
- Có quyết định cụ thể cho session và yếu tố cũ sau recovery.

Ngoại lệ:
- Chỉ theo phạm vi và cấp phê duyệt đã xác định.
- Có thời hạn, biện pháp bù và điều kiện kết thúc.

Rà soát:
- Theo lịch phù hợp với mức rủi ro.
- Ngoài lịch khi đổi yếu tố xác thực, có sự cố hoặc phát hiện bypass.
~~~

Đây là khung hồ sơ minh họa, không phải chính sách đủ để triển khai ngay. Những câu như “đúng tập bằng chứng được phê duyệt” phải được thay bằng quy tắc cụ thể hoặc liên kết tới ma trận quyết định đã có chủ sở hữu.

## 6. Biến chính sách thành các quyết định có thể kiểm chứng

Một chính sách viết “xác minh kỹ trước khi khôi phục” khó triển khai và cũng khó rà soát. Nên mô tả quy tắc theo tình huống, bằng chứng và quyền được cấp.

| Tình huống minh họa | Câu hỏi chính sách phải trả lời | Bằng chứng thực thi nên tìm |
|---|---|---|
| Mất mật khẩu nhưng còn passkey | Passkey được dùng để cho phép hành động nào? | Luồng đã triển khai, quyết định API và kiểm thử phạm vi quyền |
| Mất MFA, vẫn đọc email | Email có đủ không; nếu chưa đủ thì cần bằng chứng nào? | Ma trận quyết định và nhánh từ chối hoặc chuyển cấp |
| Hộp thư bị nghi xâm nhập | Có còn được gửi bí mật và xác minh qua kênh ấy không? | Nhánh đánh giá rủi ro, kênh độc lập và runbook hỗ trợ |
| Mất mọi yếu tố | Có đường xác minh phù hợp hay phải chưa cấp lại quyền? | Quy tắc chuyển cấp và hồ sơ quyết định |
| Token đã dùng hoặc hết hạn | Có trường hợp nào được bỏ kiểm tra không? | Kiểm tra phía máy chủ, xử lý cạnh tranh và cấu hình thực tế |
| Recovery đã hoàn tất | Session, mã dự phòng và quyền tồn tại được xử lý thế nào? | Cơ chế thu hồi, sự kiện xử lý và kiểm thử hiệu lực |
| Nhân viên muốn xóa MFA thủ công | Ai có thẩm quyền và bằng chứng nào là bắt buộc? | Quyền công cụ hỗ trợ, hồ sơ phê duyệt và nhật ký thao tác |

Cần chỉ ra các bất biến. Ví dụ:

- Một token email không được dùng sai mục đích để xóa yếu tố xác thực.
- Không cấp session đầy đủ chỉ vì một recovery context đã được tạo.
- Không dùng yếu tố mới do chính người yêu cầu vừa đăng ký để chứng minh họ có quyền thực hiện recovery trước đó.
- Không coi hai lần gửi mã vào cùng một hộp thư là hai nguồn bằng chứng độc lập.
- Không cho phép hỗ trợ vượt qua điều kiện bắt buộc bằng một nút thao tác không có kiểm soát.

Bất biến giúp đánh giá một thay đổi mà không phụ thuộc tên màn hình hay cách tổ chức mã nguồn. Nếu cùng một quyền có thể đạt qua API quản trị, quy tắc vẫn phải được áp dụng.

Cũng cần nhận diện giới hạn: khi dịch vụ chỉ có email và không có bằng chứng độc lập, chính sách không thể tuyên bố đã phân biệt chắc chắn người dùng thật với người kiểm soát hộp thư. Ownership bao gồm việc công khai mức bảo đảm thực tế và chuyển quyết định chấp nhận rủi ro đến đúng thẩm quyền.


## 7. Rà soát theo lịch và theo sự kiện

Rà soát định kỳ giúp phát hiện sự thay đổi tích lũy. Rà soát theo sự kiện giúp phản ứng trước những thay đổi không thể chờ đến kỳ tiếp theo.

### Chọn lịch theo mức rủi ro

Tần suất nên xét:

- Độ nhạy cảm của dữ liệu và quyền sau recovery.
- Quy mô và tốc độ thay đổi của dịch vụ.
- Tỷ lệ xử lý thủ công và mức phụ thuộc vào nhà cung cấp.
- Số ngoại lệ, vấn đề tồn đọng và mức độ quan sát được hành vi thực tế.
- Mức thiệt hại nếu chính sách sai hoặc người dùng không thể khôi phục.

Ví dụ, một tổ chức có thể chọn rà soát hàng quý cho luồng đang thay đổi nhanh và một chu kỳ dài hơn cho luồng ổn định. Đây là lựa chọn minh họa; không thể suy ra rằng hoàn thành đủ số cuộc họp trong năm đồng nghĩa chính sách đã an toàn.

Mỗi kỳ cần có ngày đến hạn, người tổ chức và bộ bằng chứng đầu vào. “Rà soát khi có thời gian” không phải một kế hoạch có thể theo dõi.

### Những sự kiện nên kích hoạt rà soát ngoài lịch

| Sự kiện | Điều cần xem lại |
|---|---|
| Bổ sung passkey hoặc thay mô hình MFA | Recovery có làm giảm bảo đảm của yếu tố mới không? |
| Sửa nhánh mất mọi thiết bị | Bằng chứng thay thế, quyền hỗ trợ và điều kiện từ chối |
| Có vụ chiếm đoạt hoặc trường hợp gần xảy ra | Quy tắc nào bị vượt qua, khoảng trống thực thi và phạm vi ảnh hưởng |
| Thay nhà cung cấp email, SMS hoặc danh tính | Ranh giới trách nhiệm, thời gian trễ, lỗi và phương án dự phòng |
| Tăng mạnh tỷ lệ từ chối hoặc bỏ dở | Chính sách có chặn nhầm người dùng thật, giao diện có gây nhầm lẫn không? |
| Nhiều yêu cầu ngoại lệ cùng loại | Có nhu cầu hợp lệ bị bỏ sót hay một đường bypass đang hình thành? |
| Thay đổi loại dữ liệu hoặc nhóm người dùng | Mức rủi ro, khả năng tiếp cận và bằng chứng có còn phù hợp không? |
| Thay công cụ hoặc quyền hỗ trợ | Có quyền mới cho phép đổi email, xóa yếu tố hoặc tạo session không? |
| Chủ sở hữu chuyển nhóm hoặc nghỉ việc | Ai nhận trách nhiệm, lịch rà soát và vấn đề tồn đọng? |
| Phát hiện cấu hình lệch tài liệu | Hành vi nào đang có hiệu lực và cần khống chế rủi ro ra sao? |

Tác nhân kích hoạt không nhất thiết buộc phải viết lại toàn bộ chính sách. Có thể rà soát đúng phạm vi bị ảnh hưởng, nhưng cần ghi rõ vì sao phần còn lại không cần thay đổi.

### Khi kỳ rà soát bị quá hạn

Không nên tự động vô hiệu mọi recovery chỉ vì quá hạn tài liệu; điều đó có thể gây khóa tài khoản hàng loạt mà không giảm đúng rủi ro.

Thay vào đó, cần chuyển cấp theo cơ chế đã định, đánh giá mức rủi ro hiện tại, giao người chịu trách nhiệm và đặt hạn xử lý. Nếu phải hạn chế một nhánh nguy hiểm, quyết định đó cần có phạm vi và phương án hỗ trợ cụ thể.

Chính sách quá hạn cũng không tự trở thành “đã được chấp nhận rủi ro”. Việc chấp nhận phải do đúng thẩm quyền quyết định và được ghi nhận.

## 8. Quy trình rà soát từ bằng chứng đến hành động

Một kỳ rà soát có thể thực hiện theo sáu bước.

### Bước 1: Xác nhận phạm vi và phiên bản đang áp dụng

Tập hợp phiên bản chính sách, cấu hình quan trọng, nhánh API, runbook và nhà cung cấp liên quan. Xác định có nhiều phiên bản cùng chạy theo vùng, nhóm tài khoản hoặc thời điểm triển khai hay không.

Nếu tài liệu ghi thời gian chờ là một giá trị nhưng cấu hình đang dùng giá trị khác, chưa thể kết luận luồng tuân thủ chỉ dựa trên tài liệu.

### Bước 2: Thu thập bằng chứng có giới hạn

Bằng chứng có thể gồm:

- Sơ đồ quyết định và mô hình đe dọa hiện hành.
- Kết quả kiểm thử các thuộc tính quan trọng của recovery.
- Dữ liệu sự kiện và số liệu đã tổng hợp.
- Mẫu hồ sơ hỗ trợ được lấy theo tiêu chí đã xác định.
- Danh sách quyền công cụ hỗ trợ và thao tác quản trị.
- Ngoại lệ còn hiệu lực, đã hết hạn và hành động chưa hoàn tất.
- Sự cố, phản hồi người dùng và vấn đề khả năng tiếp cận.

Không cần sao chép mọi token hoặc tài liệu danh tính vào gói rà soát. Dùng định danh hồ sơ, dữ liệu che bớt và quyền truy cập theo nhu cầu. Đánh giá chính sách không phải lý do để tạo thêm một kho bí mật recovery.

### Bước 3: Đối chiếu quy tắc với hành vi thực tế

Với mỗi quy tắc quan trọng, xác định:

1. Nó được thực thi tại đâu?
2. Ai có thể thay đổi hoặc bỏ qua?
3. Có đường tự phục vụ, hỗ trợ hay quản trị nào cho cùng kết quả nhưng dùng yêu cầu yếu hơn không?
4. Bằng chứng nào xác nhận kiểm soát đang có hiệu lực?
5. Khi một thành phần lỗi, hệ thống chuyển sang hành vi nào?

Không chỉ kiểm tra đường thành công. Cần xem token hết hạn, yêu cầu đồng thời, bằng chứng không đủ, timeout nhà cung cấp, thu hồi session lỗi và tranh chấp recovery.

### Bước 4: Đánh giá đồng thời an toàn và khả năng phục hồi

Một hệ thống từ chối mọi người dùng có thể giảm số vụ recovery bị lạm dụng nhưng không đạt mục đích phục hồi. Một hệ thống chấp nhận mọi yêu cầu có thể đạt tỷ lệ hoàn tất cao nhưng làm tăng chiếm đoạt.

Cần phân tích nhóm người dùng bị ảnh hưởng: người mất thiết bị, người không còn số điện thoại, người sử dụng công nghệ hỗ trợ và người có tài khoản bị xâm nhập. Khó khăn thực tế nên dẫn đến cải tiến phương án dự phòng, không tự động dẫn đến bỏ bằng chứng.

### Bước 5: Ghi quyết định và phân công hành động

Kết quả cần thuộc một trong các dạng rõ ràng:

- Tiếp tục chính sách hiện hành vì bằng chứng cho thấy vẫn phù hợp.
- Sửa chính sách hoặc cách thực thi, kèm người phụ trách và hạn hoàn thành.
- Chấp nhận một rủi ro còn lại trong phạm vi được phê duyệt.
- Hạn chế hoặc dừng một nhánh recovery, kèm phương án xử lý người dùng bị ảnh hưởng.
- Yêu cầu thêm bằng chứng trước khi kết luận.

“Đã thảo luận” chưa phải kết quả. Một phát hiện cũng chưa được đóng chỉ vì đã tạo yêu cầu công việc.

### Bước 6: Kiểm tra việc khắc phục và đóng kỳ rà soát

Người chịu trách nhiệm xác nhận thay đổi đã có hiệu lực, runbook đã được cập nhật và bằng chứng kiểm tra phù hợp đã tồn tại.

Ví dụ, phát hiện “nhân viên có thể xóa MFA không cần hồ sơ phê duyệt” chỉ được đóng khi quyền công cụ và quy trình thực tế đã thay đổi, không phải khi một đoạn hướng dẫn được bổ sung vào tài liệu.

Hồ sơ đóng kỳ cần ghi những vấn đề còn tồn đọng. Không được dùng việc kết thúc kỳ rà soát để làm biến mất rủi ro chưa xử lý.

## 9. Đọc số liệu mà không tạo động lực sai

Số liệu giúp tìm vấn đề nhưng không thay thế phân tích quyết định.

| Chỉ số | Cách dùng | Điều dễ hiểu sai |
|---|---|---|
| Tỷ lệ hoàn tất recovery | Theo dõi khả năng phục hồi theo nhánh và nhóm người dùng | Tăng tỷ lệ bằng cách bỏ yếu tố xác minh có thể làm chính sách yếu đi |
| Tỷ lệ bỏ dở hoặc bị từ chối | Tìm bước gây khó khăn và bằng chứng không phù hợp | Không phải mọi lần thất bại đều là người dùng thật bị chặn |
| Thời gian hoàn tất theo phân vị | Phát hiện chậm trễ, phân biệt thời gian chờ có chủ đích và lỗi | Một giá trị trung bình che khuất nhóm phải chờ rất lâu |
| Số vụ chiếm đoạt được xác nhận liên quan recovery | Đánh giá hậu quả và đường tấn công | Không có báo cáo không chứng minh không có sự cố; xác nhận thường có độ trễ |
| Tần suất và tuổi ngoại lệ | Nhận diện lối xử lý tạm trở thành thường trực | Đóng hồ sơ hành chính chưa chắc đã thu hồi quyền ngoại lệ |
| Tỷ lệ chuyển cấp và mở lại hồ sơ hỗ trợ | Tìm quy tắc không rõ hoặc quyết định thiếu nhất quán | Cần xem mẫu hồ sơ; con số riêng lẻ chưa giải thích nguyên nhân |
| Sai lệch cấu hình và kết quả thu hồi session | Kiểm tra độ tin cậy của thực thi | Một sự kiện “đã gửi lệnh thu hồi” chưa chứng minh token cũ hết quyền |

Khi báo cáo tỷ lệ, cần nêu mẫu số và đơn vị đếm. Một người có thể tạo nhiều yêu cầu; “100 lần gửi email” khác với “100 tài khoản cần recovery”. Cũng cần xác định khoảng đo, độ trễ ghi nhận sự cố và mức bao phủ của dữ liệu.

Nên phân tách theo nhánh, loại tài khoản và phiên bản chính sách khi có đủ dữ liệu. Nếu chỉ nhìn toàn bộ hệ thống, một nhánh hỗ trợ nhỏ nhưng nguy hiểm có thể bị che bởi lượng lớn yêu cầu đặt lại mật khẩu thông thường.

Các ngưỡng cảnh báo nên xuất phát từ rủi ro, năng lực vận hành và dữ liệu nền. Không đặt một con số tùy ý rồi dùng nó để tự động hạ bằng chứng hoặc gắn mọi người dùng vào diện gian lận.

## 10. Quản lý thay đổi và phiên bản chính sách

Một thay đổi cần được theo dõi từ đề xuất tới hành vi đang chạy.

~~~mermaid
flowchart LR
    A["Đề xuất và lý do"] --> B["Đánh giá tác động và rủi ro"]
    B --> C["Phê duyệt đúng thẩm quyền"]
    C --> D["Triển khai và kiểm chứng"]
    D --> E["Kích hoạt phiên bản"]
    E --> F["Theo dõi kết quả"]
    F --> G["Rà soát hoặc thay thế"]
    B --> H["Yêu cầu chỉnh sửa"]
    H --> A
~~~

### Nội dung một đề xuất thay đổi

Đề xuất nên có:

- Vấn đề cụ thể và nhóm người dùng hoặc tài sản bị ảnh hưởng.
- Quy tắc trước và sau thay đổi.
- Tác động tới bằng chứng, quyền hỗ trợ, session và kênh recovery.
- Nguy cơ mới, biện pháp giảm thiểu và rủi ro còn lại.
- Kế hoạch cập nhật cấu hình, API, runbook, đào tạo và thông báo khi cần.
- Điều kiện kích hoạt, tiêu chí theo dõi và cách quay lui an toàn.
- Cách xử lý những hồ sơ recovery đang chạy.

Không gộp thay đổi rủi ro cao vào một mô tả chung như “cải thiện trải nghiệm”. Ví dụ, giảm số bước là thay đổi giao diện; bỏ yêu cầu passkey là thay đổi mức bằng chứng, dù cả hai cùng làm biểu mẫu ngắn hơn.

### Phân loại theo tác động, không theo kích thước bản sửa

Sửa lỗi chính tả không cần cùng quy trình với việc cho hỗ trợ xóa MFA. Nhưng một dòng cấu hình chuyển điều kiện từ “email và bằng chứng độc lập” thành “email” có thể là thay đổi rất lớn.

Tổ chức nên xác lập trước loại thay đổi nào cần các phê duyệt nào. Mục tiêu là đặt kiểm soát đúng chỗ, không tạo một chuỗi xét duyệt giống nhau cho mọi thao tác.

### Gắn phiên bản với quyết định và cấu hình

Một hồ sơ recovery nên có khả năng truy ra:

- Phiên bản chính sách và tập quy tắc đã dùng.
- Phiên bản cấu hình hoặc quyết định triển khai liên quan.
- Bằng chứng và thời điểm đánh giá.
- Các thay đổi quyền đã được chấp nhận.

Chỉ ghi “policy v2” trong khi cấu hình thay đổi độc lập mà không có dấu vết sẽ không đủ để giải thích một quyết định quá khứ.

### Hồ sơ đang chạy cần quy tắc chuyển tiếp

Giả sử một phiên bản mới yêu cầu thêm bằng chứng do phát hiện bypass. Hồ sơ đang chờ không được mặc nhiên hoàn tất theo quy tắc yếu chỉ vì nó khởi tạo trước thời điểm phát hiện.

Mặt khác, áp dụng quy tắc mới cũng không nên âm thầm đặt lại mọi thời gian chờ hoặc tạo một chuỗi yêu cầu vô tận cho người dùng thật.

Cần quyết định rõ hồ sơ nào:

- Được tiếp tục theo quyết định cũ trong phạm vi chấp nhận được.
- Phải đánh giá lại hoặc bổ sung bằng chứng.
- Bị hủy vì điều kiện nền đã không còn an toàn.
- Cần hỗ trợ chuyển tiếp do sự khác biệt phiên bản.

Thay đổi ảnh hưởng người dùng cần được giải thích phù hợp mà không tiết lộ chi tiết có thể giúp lạm dụng.

### Quay lui không đồng nghĩa khôi phục lỗ hổng

Nếu phiên bản mới gây lỗi, khôi phục toàn bộ cấu hình cũ có thể mở lại đường recovery đã biết là không an toàn.

Phương án quay lui có thể là tạm hạn chế nhánh lỗi, dùng kênh dự phòng đã được phê duyệt hoặc giữ kiểm soát mới trong khi sửa trải nghiệm. Điều kiện quay lui cần được chuẩn bị trước khi kích hoạt thay đổi.

## 11. Ngoại lệ, tình huống khẩn cấp và ranh giới của hỗ trợ

Cần phân biệt hai trường hợp:

- **Xử lý thủ công trong chính sách:** nhân viên thực hiện một nhánh đã có điều kiện, bằng chứng và thẩm quyền rõ.
- **Ngoại lệ chính sách:** đề xuất lệch khỏi quy tắc hiện hành; cần quyết định riêng theo cơ chế ngoại lệ.

Nếu quy trình đã cho phép nhân viên xác minh bằng mã dự phòng hợp lệ, việc làm đó không tự là ngoại lệ. Ngược lại, bỏ yêu cầu bằng chứng độc lập vì người yêu cầu “rất gấp” là thay đổi đáng kể, không phải một thao tác hỗ trợ thông thường.

### Hồ sơ ngoại lệ cần có gì?

| Nội dung | Mục đích |
|---|---|
| Quy tắc muốn lệch và lý do | Biết chính xác điều gì bị bỏ hoặc thay |
| Phạm vi tài khoản, hành động và hệ thống | Tránh ngoại lệ lan sang trường hợp khác |
| Đánh giá nguy cơ và rủi ro còn lại | Thể hiện hậu quả có thể xảy ra |
| Người đề xuất và người phê duyệt | Bảo đảm đúng thẩm quyền và khả năng truy cứu |
| Biện pháp bù | Giảm rủi ro theo cơ chế có hiệu quả thực tế |
| Thời điểm bắt đầu và hết hạn | Ngăn giải pháp tạm tồn tại vô thời hạn |
| Cơ chế kết thúc hoặc thu hồi | Bảo đảm quyền ngoại lệ thực sự bị loại bỏ |
| Người kiểm tra kết quả | Xác nhận ngoại lệ đã được đóng đúng nghĩa |

Một cảnh báo email bổ sung không phải biện pháp bù đủ mạnh nếu rủi ro đang xét là đối thủ kiểm soát chính hộp thư đó. Thời gian chờ cũng không tự tạo bằng chứng danh tính mới.

Một số rủi ro có thể nằm ngoài mức cho phép ngoại lệ. Khi không đủ thẩm quyền hoặc không có biện pháp phù hợp, phải chưa cấp quyền thay vì mặc định mọi ngoại lệ đều có thể được duyệt.

### Ví dụ: nhà cung cấp MFA bị gián đoạn

Giả sử người dùng không thể nhận một loại OTP vì nhà cung cấp gặp lỗi. Một phản ứng nguy hiểm là tạm cho mọi tài khoản xóa MFA bằng email.

Cách xử lý cần bắt đầu từ phương án dự phòng đã phê duyệt: dùng yếu tố độc lập khác còn hợp lệ, giới hạn đúng nhóm bị ảnh hưởng hoặc chuyển sang hỗ trợ theo cùng yêu cầu bằng chứng. Nếu không có đường đủ an toàn, có thể phải trì hoãn recovery của một số tài khoản.

Quy trình khẩn cấp cần có người có thẩm quyền trực, phạm vi thay đổi, hạn hiệu lực, giám sát và rà soát sau sự kiện. “Khẩn cấp” không tự chứng minh người yêu cầu là chủ tài khoản.

Ngoại lệ lặp đi lặp lại là đầu vào của kỳ rà soát. Có thể chính sách chưa đáp ứng nhu cầu hợp lệ, hoặc có người đang dùng ngoại lệ để né kiểm soát. Cần tìm nguyên nhân trước khi biến cách làm tạm thành mặc định.

## 12. Bàn giao ownership và phát hiện chính sách lệch thực tế

Ownership phải gắn với một vai trò bền vững, đồng thời có người đang đảm nhiệm và người thay thế. Một địa chỉ nhóm không có người nhận trách nhiệm cụ thể chưa giải quyết được vấn đề.

Khi bàn giao, cần chuyển tối thiểu:

- Phạm vi, phiên bản có hiệu lực và các điểm tích hợp.
- Lịch rà soát, ngoại lệ và rủi ro còn lại.
- Phát hiện chưa đóng, hạn xử lý và người phụ trách.
- Thẩm quyền thay đổi, liên hệ kỹ thuật và đầu mối hỗ trợ.
- Cách truy cập bằng chứng và bảng giám sát theo quyền cần thiết.

Người mới cần xác nhận đã nhận trách nhiệm. Việc cập nhật tên trong tài liệu nhưng bỏ lại các ngoại lệ không ai theo dõi là một bàn giao chưa hoàn tất.

### Dấu hiệu policy drift

Policy drift là khoảng cách giữa quy tắc được công bố và hành vi có hiệu lực. Ví dụ:

- Tài liệu yêu cầu token dùng một lần nhưng hai yêu cầu đồng thời đều thành công.
- Chính sách yêu cầu bằng chứng độc lập nhưng công cụ hỗ trợ có nút bỏ qua.
- Runbook yêu cầu thu hồi session nhưng ứng dụng vẫn chấp nhận refresh token cũ.
- Tập quy tắc đã thay nhưng hồ sơ recovery không ghi được phiên bản quyết định.
- Một cờ cấu hình tạm cho sự cố chưa được trả về sau khi sự cố kết thúc.

Có thể phát hiện drift qua so sánh cấu hình, kiểm thử thuộc tính quan trọng, kiểm tra quyền quản trị và lấy mẫu hồ sơ. Biện pháp tự động cần bổ sung việc đọc quyết định thực tế, đặc biệt với recovery thủ công.

Khi phát hiện drift, phải xác định hành vi nào đang chạy, phạm vi ảnh hưởng và nhu cầu hạn chế khẩn cấp. Chỉ sửa tài liệu cho giống một hành vi yếu hơn không phải cách khắc phục đầy đủ.

## 13. Ví dụ xuyên suốt: triển khai passkey nhưng quên cập nhật recovery

Một dịch vụ bổ sung passkey để bảo vệ đăng nhập. Người dùng có thể mất thiết bị, nên nhóm hỗ trợ vẫn cần hỗ trợ recovery.

Trong kỳ rà soát, nhóm phát hiện:

- Đăng nhập tự phục vụ yêu cầu passkey theo chính sách mới.
- Công cụ hỗ trợ cũ cho phép xóa mọi passkey sau khi người yêu cầu trả lời email.
- Các tài khoản vừa recovery nhận session đầy đủ ngay lập tức.
- Hồ sơ hỗ trợ không ghi phiên bản chính sách hoặc bằng chứng đã dùng.

Đây không chỉ là lỗi đào tạo nhân viên. Quy tắc, quyền công cụ và cơ chế tạo session đang cho phép một đường yếu hơn.

Một kế hoạch xử lý có ownership rõ ràng có thể là:

| Việc cần làm | Vai trò phụ trách | Bằng chứng hoàn tất |
|---|---|---|
| Xác định chính sách cho mất passkey và mất mọi thiết bị | Chủ chính sách cùng an ninh, sản phẩm | Ma trận quyết định đã được phê duyệt |
| Hạn chế nhánh xóa passkey chỉ bằng email | Chủ kỹ thuật và chủ hỗ trợ | Quyền công cụ, kiểm tra API và runbook khớp nhau |
| Tách recovery context khỏi session tài khoản đầy đủ | Chủ kỹ thuật | Kiểm tra phạm vi quyền và điều kiện cấp session |
| Quyết định xử lý session, yếu tố cũ và hồ sơ đang chạy | Chủ chính sách cùng kỹ thuật | Quy tắc chuyển tiếp và kế hoạch thu hồi có hiệu lực |
| Xử lý nhu cầu của người mất hết yếu tố | Chủ hỗ trợ và sản phẩm | Đường chuyển cấp rõ; không hứa recovery khi chưa đủ bằng chứng |
| Kiểm tra tác động và đóng phát hiện | Chủ chính sách | Bằng chứng triển khai, kết quả theo dõi và vấn đề còn lại |

Nếu biện pháp tạm làm một nhóm người dùng chưa thể recovery, tác động đó cần được ghi nhận và theo dõi. Không nên báo cáo thành công chỉ vì số vụ lạm dụng giảm, trong khi vấn đề phục hồi bị chuyển hết sang hàng chờ hỗ trợ.

## 14. Câu hỏi dùng trong một buổi rà soát

Những câu hỏi sau giúp kiểm tra chất lượng quản trị mà không chỉ kiểm tra việc có tài liệu hay không:

1. Ai có trách nhiệm cuối cùng nếu chính sách cho phép chiếm đoạt tài khoản? Người đó có thẩm quyền sửa vấn đề không?
2. Những đường recovery nào tồn tại ngoài giao diện người dùng thông thường?
3. Bằng chứng nào vẫn có giá trị khi email hoặc thiết bị đã bị xâm nhập?
4. Mỗi hành động nhạy cảm có điều kiện rõ, hay một lần xác minh mở khóa mọi hành động?
5. Quyền hỗ trợ thực tế có thể làm nhiều hơn runbook cho phép không?
6. Một thay đổi cấu hình có thể hạ yêu cầu xác minh mà không qua quy trình phù hợp không?
7. Phiên bản chính sách nào được dùng cho một hồ sơ cụ thể, và có thể chứng minh điều đó không?
8. Khi nhà cung cấp lỗi, hệ thống dùng phương án dự phòng nào? Có tự hạ yêu cầu bằng chứng không?
9. Ngoại lệ nào đang có hiệu lực, ai theo dõi và điều gì bảo đảm chúng kết thúc?
10. Những người dùng thật nào đang khó recovery, và giải pháp có giữ được mức xác minh cần thiết không?
11. Phát hiện từ kỳ trước đã được sửa trong hệ thống hay mới được đóng trong công cụ quản lý công việc?
12. Nếu chủ sở hữu vắng mặt hoặc rời nhóm hôm nay, ai nhận lịch rà soát và các quyết định còn mở?

Một chính sách được quản lý tốt phải trả lời được cả hai mặt: **vì sao hệ thống cho phép cấp lại quyền**, và **ai chịu trách nhiệm chứng minh quy tắc đó vẫn phù hợp, đang được thực thi và sẽ được sửa khi điều kiện thay đổi**.

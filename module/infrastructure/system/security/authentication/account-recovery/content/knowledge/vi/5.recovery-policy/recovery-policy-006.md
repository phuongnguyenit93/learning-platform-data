# Ngoại lệ trong chính sách khôi phục tài khoản

Trong chương **Recovery Policy** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, ngoại lệ chính sách là một quyết định cho phép một trường hợp khôi phục tài khoản lệch khỏi quy tắc thông thường, trong phạm vi và thẩm quyền được xác định trước.

Recovery phải giúp người dùng lấy lại tài khoản khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Nhưng chính tình trạng thiếu yếu tố xác thực cũng khiến hệ thống khó phân biệt người dùng thật với đối thủ. Một ngoại lệ không được kiểm soát có thể trở thành cách đơn giản nhất để chiếm tài khoản: thay vì vượt qua MFA, đối thủ thuyết phục nhân viên bỏ MFA.

Bài học này trình bày cách tiếp nhận, đánh giá, phê duyệt, thực thi và kết thúc ngoại lệ mà vẫn giữ rõ ranh giới cấp quyền. Các vai trò, thời gian và tình huống trong bài là ví dụ thiết kế, không phải yêu cầu giống nhau cho mọi dịch vụ.

Sau bài học, người học có thể:

- Phân biệt recovery thủ công trong chính sách với ngoại lệ thực sự.
- Nhận diện yêu cầu ngoại lệ hợp lệ, yêu cầu không đủ bằng chứng và hành vi gây áp lực.
- Lập một quyết định có phạm vi hẹp, thời hạn, biện pháp bù và người chịu trách nhiệm.
- Ràng buộc phê duyệt với đúng tài khoản, hồ sơ, hành động và điều kiện bảo mật.
- Xử lý hết hạn, hủy, thu hồi và ảnh hưởng còn lại sau khi ngoại lệ đã được dùng.

## 1. Ngoại lệ là gì và không nên bị dùng thay cho điều gì?

Giả sử chính sách quy định rằng khi mất ứng dụng MFA, người dùng có thể cung cấp mã dự phòng đã tạo trước đó. Nhân viên hỗ trợ kiểm tra mã và hướng dẫn đăng ký lại MFA theo runbook.

Đây là **một nhánh được chính sách cho phép**, dù có nhân viên tham gia. Nó không tự trở thành ngoại lệ chỉ vì không hoàn toàn tự động.

Ngược lại, nếu chính sách yêu cầu thời gian chờ trước khi thay yếu tố và người yêu cầu muốn rút ngắn thời gian đó, đây có thể là ngoại lệ. Nếu người yêu cầu muốn bỏ hoàn toàn yêu cầu bằng chứng mà không có phương án thay thế phù hợp, đó là đề xuất thay đổi mức bảo đảm, không chỉ là hỗ trợ nhanh hơn.

| Tình huống | Cách phân loại |
|---|---|
| Dùng mã dự phòng theo đúng luồng đã công bố | Xử lý trong chính sách |
| Nhân viên chuyển hồ sơ lên nhóm xác minh theo runbook | Chuyển cấp trong chính sách |
| Token hết hạn, phát hành token mới theo cùng yêu cầu bằng chứng | Thực hiện lại bước hợp lệ |
| Token hợp lệ nhưng lỗi phần mềm khiến không dùng được | Sự cố triển khai; sửa lỗi hoặc dùng phương án dự phòng được phép |
| Rút ngắn thời gian chờ cho một hồ sơ cụ thể | Có thể là ngoại lệ nếu chính sách cho phép xét duyệt |
| Xóa passkey chỉ vì người gửi biết thông tin trong email | Yêu cầu bỏ bằng chứng; không tự đủ điều kiện để chấp thuận |
| Một quy trình tạm được dùng thường xuyên cho nhiều người | Dấu hiệu cần sửa chính sách hoặc sản phẩm, không nên duy trì bằng ngoại lệ vô hạn |

### Ba câu hỏi phân loại ban đầu

1. Quy tắc nào thực sự bị lệch?
2. Chính sách đã có đường xử lý phù hợp hay chưa?
3. Người xử lý có quyền xét loại lệch này hay phải từ chối hoặc chuyển cấp?

Nếu không chỉ ra được quy tắc bị lệch, nhân viên khó biết cần phê duyệt điều gì và cũng khó kiểm tra việc thực thi.

“Người dùng cần gấp” mô tả mức ưu tiên. Nó không xác định quy tắc được bỏ, không bổ sung bằng chứng và không tạo thẩm quyền cho người xử lý.

## 2. Vì sao ngoại lệ recovery có rủi ro đặc biệt?

Ngoại lệ thường xuất hiện khi người yêu cầu không đáp ứng điều kiện chuẩn. Điều này tạo ra sự mơ hồ có lợi cho đối thủ.

Một người dùng thật có thể mất điện thoại và không giữ mã dự phòng. Đối thủ cũng có thể nói chính xác điều đó. Sự xúc động, câu chuyện hợp lý hoặc áp lực thời gian không giúp hệ thống phân biệt chắc chắn hai trường hợp.

Các nguy cơ thường gặp gồm:

- **Lừa nhân viên:** dùng lịch sử giao dịch, thông tin cá nhân hoặc câu chuyện khẩn cấp để yêu cầu bỏ kiểm soát.
- **Tìm người dễ chấp thuận:** mở nhiều hồ sơ, chuyển kênh hoặc thử nhân viên khác sau khi bị từ chối.
- **Mượn uy tín nội bộ:** viện dẫn lãnh đạo, khách hàng lớn hoặc một phê duyệt không thể xác minh.
- **Mở rộng phạm vi:** từ cho phép tiếp tục xác minh thành đổi email, xóa MFA và cấp session đầy đủ.
- **Tạo chỗ đứng lâu dài:** dùng một ngoại lệ ngắn hạn để đăng ký passkey hoặc cấp quyền ứng dụng của đối thủ.
- **Giấu dấu vết:** xử lý ngoài công cụ được kiểm soát hoặc ghi thiếu bằng chứng và lý do.
- **Biến tạm thời thành thường trực:** để quyền hỗ trợ, cờ cấu hình hoặc phương án yếu tồn tại sau sự cố.

Một quyết định có chữ ký của người phê duyệt vẫn có thể sai nếu bằng chứng không chứng minh được quyền sở hữu hoặc người đó không có thẩm quyền với loại rủi ro đang xét.

### Phê duyệt không tạo ra bằng chứng còn thiếu

Nếu đối thủ kiểm soát hộp thư, thêm một quản lý xác nhận “email này có vẻ đúng” không làm email trở thành bằng chứng độc lập.

Tương tự, hai nhân viên cùng đọc một bộ thông tin lấy từ hộp thư chỉ tạo thêm người xem xét, không tạo thêm nguồn chứng minh danh tính.

Phân tách nhiệm vụ giúp giảm sai sót hoặc lạm quyền. Nó bổ sung cho việc xác minh, không thay thế việc xác minh.

## 3. Đặt ranh giới: điều gì có thể linh hoạt, điều gì phải được giữ?

Chính sách nên xác định trước những loại ngoại lệ được xét, giới hạn thẩm quyền và các điều kiện không được bỏ qua.

| Nhóm quy tắc | Ví dụ | Cách xử lý ngoại lệ |
|---|---|---|
| Quy trình hoặc thời gian | Hạn nộp hồ sơ, thứ tự xử lý, thời gian chờ trong một số trường hợp | Có thể linh hoạt nếu rủi ro được đánh giá và phạm vi được phê duyệt |
| Hình thức bằng chứng | Một phương thức thay thế có liên kết đáng tin cậy với tài khoản nhưng chưa nằm trong luồng tự phục vụ | Cần đánh giá mức bảo đảm, tính độc lập và thẩm quyền chấp nhận |
| Phạm vi quyền sau recovery | Cho phép thực hiện một hành động thay vì nhận toàn bộ quyền | Cần giới hạn thực tế ở phía máy chủ |
| Điều kiện nền của quyết định | Đúng tài khoản, đúng hồ sơ, bằng chứng có giá trị và người phê duyệt có thẩm quyền | Không được coi là tùy chọn chỉ vì có yêu cầu khẩn |
| Tính toàn vẹn và trách nhiệm | Token không bị phát lại, có dấu vết, quyết định không bị tự sửa | Cần giữ; không dùng ngoại lệ để bỏ kiểm soát nền |

Không nên cho phép “ngoại lệ mọi thứ” chỉ bằng một quyền quản trị cấp cao. Tổ chức cần định nghĩa ai được chấp nhận loại rủi ro nào và trường hợp nào không được phép recovery bằng đường ngoại lệ.

### Các bất biến thực tế

Một tập bất biến minh họa có thể gồm:

- Người yêu cầu chưa được xác minh không được tự chọn bằng chứng mới rồi dùng nó để chứng minh quyền với tài khoản cũ.
- Một phê duyệt không được chuyển sang tài khoản, hồ sơ hoặc hành động khác.
- Một token đã hết hạn hoặc đã dùng không được chấp nhận lại; nếu cần tiếp tục, tạo quyền mới sau khi kiểm tra điều kiện.
- Một ngoại lệ không được âm thầm cấp nhiều quyền hơn phạm vi được phê duyệt.
- Người tiếp nhận không tự phê duyệt trường hợp mà chính sách yêu cầu người kiểm tra độc lập.
- Quyết định phải có căn cứ và dấu vết; không chia sẻ token hoặc bí mật để “làm hộ” ngoài quy trình.

Nếu tổ chức cho phép thay đổi một quy tắc bảo mật cốt lõi ở cấp cao hơn, đó phải là quyết định quản trị được xác định riêng. Nhân viên hỗ trợ không được suy ra quyền ấy từ việc có nút thao tác trong công cụ.

## 4. Đánh giá bằng chứng trước khi đánh giá sự thuận tiện

Cần tách hai câu hỏi:

1. Có lý do hợp lệ để không đi theo luồng chuẩn không?
2. Có đủ căn cứ để cấp đúng quyền đang được yêu cầu không?

Ví dụ, điện thoại hỏng là lý do hợp lệ khiến người dùng không nhận được MFA. Nó chưa chứng minh người đang liên hệ là chủ tài khoản.

### Giá trị của các loại đầu vào

| Đầu vào | Có thể giúp gì? | Điều không được tự suy ra |
|---|---|---|
| Câu chuyện mất thiết bị | Hiểu nhu cầu và chọn nhánh hỗ trợ | Không tự chứng minh quyền sở hữu |
| Email từ địa chỉ đã đăng ký | Chứng minh một mức tiếp cận hộp thư nếu kênh được kiểm tra đúng | Không đủ chống người đã chiếm hộp thư |
| Hóa đơn, thông tin hồ sơ hoặc lịch sử liên hệ | Đối chiếu ngữ cảnh | Có thể đã lộ trong email hoặc từ nguồn khác |
| Yếu tố xác thực đã đăng ký từ trước | Có thể cung cấp bằng chứng mạnh theo cấu hình và chính sách | Không bảo đảm độc lập nếu cùng phụ thuộc vào một miền đã bị xâm nhập |
| Mã dự phòng giữ riêng, còn hợp lệ | Bằng chứng sở hữu có thể dùng theo chính sách | Không còn độc lập nếu mã nằm trong hộp thư bị lộ |
| Session có sẵn | Hỗ trợ đánh giá nếu đủ độ mới và mức xác thực | Cookie đơn thuần không đồng nghĩa chủ tài khoản đã được xác minh mạnh |
| Người quản trị tổ chức xác nhận | Có thể có giá trị nếu quyền ủy nhiệm đã được thiết lập trước | Một người tự nhận là quản lý không tự có quyền chuyển tài khoản |
| Tài liệu định danh | Có thể hỗ trợ trong mô hình danh tính phù hợp | Không tự liên kết với tài khoản cũ vốn không được xác lập danh tính |

Với passkey, cần xem xét cả yếu tố đã đăng ký và cách khôi phục tài khoản đồng bộ hoặc thiết bị liên quan. Tên phương thức không đủ để kết luận độc lập với sự cố.

### Không tăng độ tin cậy bằng số lượng thông tin yếu

Nhiều câu trả lời lấy từ cùng một hộp thư không tự trở thành nhiều nguồn độc lập. Điểm rủi ro hoặc số trường khớp hồ sơ cũng không nên được gọi là bằng chứng mật mã.

Nếu không còn bằng chứng đủ mạnh, có thể phải chưa cấp lại quyền. Đây là một kết quả cần được chính sách dự liệu, kèm hướng hỗ trợ rõ ràng, thay vì ép nhân viên chọn một cách xác minh không đáng tin.

## 5. Hồ sơ ngoại lệ: mô tả đúng quyết định cần phê duyệt

Một hồ sơ nên cho người khác hiểu vì sao ngoại lệ được đề xuất và chính xác điều gì sẽ xảy ra nếu chấp thuận.

| Trường | Nội dung cần có |
|---|---|
| Định danh | Mã ngoại lệ và mã hồ sơ recovery liên quan |
| Tài khoản đích | Định danh nội bộ ổn định; không chỉ là email có thể thay đổi |
| Quy tắc bị lệch | Mã hoặc nội dung quy tắc, phiên bản chính sách |
| Hành động đề xuất | Đổi gì, không kèm quyền ngầm nào khác |
| Lý do | Trở ngại thật sự của luồng chuẩn và nhu cầu người dùng |
| Bằng chứng | Loại bằng chứng, kết quả kiểm tra, thời điểm và giới hạn |
| Giả định đe dọa | Email, thiết bị, session hoặc kênh nào có thể đã bị xâm nhập |
| Rủi ro còn lại | Điều gì vẫn có thể xảy ra sau biện pháp bù |
| Biện pháp bù | Cơ chế cụ thể, người thực hiện và bằng chứng hiệu lực |
| Phê duyệt | Người đề xuất, người xác minh, người có thẩm quyền chấp nhận |
| Phạm vi và thời hạn | Tài khoản, hành động, thời điểm bắt đầu, hạn cuối và số lần sử dụng |
| Điều kiện vô hiệu | Thay đổi bảo mật, dấu hiệu gian lận, hết hạn hoặc hủy |
| Kế hoạch hậu kiểm | Kiểm tra quyền tồn tại, thông báo và đóng hồ sơ |

Mô tả “cho phép recovery theo ngoại lệ” quá rộng. Một mô tả tốt hơn là:

> Cho phép hồ sơ R-42 bổ sung một yếu tố MFA theo đúng kế hoạch đã phê duyệt, sau khi hoàn thành bằng chứng bắt buộc; áp dụng điều chỉnh thời gian chờ trong phạm vi quyết định E-17. Việc đổi email và tạo quyền ứng dụng cần quyết định riêng.

Mã R-42 và E-17 chỉ là ký hiệu minh họa. Nội dung phê duyệt thực tế phải đủ cụ thể để máy chủ và người vận hành xác định được hành động hợp lệ.

### Không đưa bí mật vào hồ sơ hành chính

Không chép OTP, token reset, mã dự phòng, cookie hoặc khóa riêng vào ticket. Ghi tham chiếu đến kết quả xác minh và lưu dữ liệu nhạy cảm ở đúng hệ thống có kiểm soát khi thật sự cần.

Hồ sơ cũng không nên thu thập thêm dữ liệu danh tính chỉ để tạo cảm giác chắc chắn. Bằng chứng phải có vai trò rõ trong việc liên kết người yêu cầu với tài khoản.

## 6. Biện pháp bù phải tác động vào đúng rủi ro

Biện pháp bù là kiểm soát bổ sung giúp giảm nguy cơ khi chấp nhận một độ lệch. Không phải hành động bổ sung nào cũng bù được rủi ro bị tăng.

| Rủi ro do ngoại lệ | Biện pháp có thể có ý nghĩa | Giới hạn |
|---|---|---|
| Rút ngắn khoảng phát hiện của người dùng | Bằng chứng độc lập mạnh hơn, thông báo qua kênh đã thiết lập và hạn chế hành động phù hợp | Không có phản đối không tự là đồng ý |
| Cho phép một hành động thủ công nhạy cảm | Phê duyệt độc lập, quyền thao tác một lần, ràng buộc tài khoản và kế hoạch | Nhiều người duyệt không sửa được bằng chứng giả |
| Nguy cơ duy trì quyền sau recovery | Kế hoạch xử lý session, refresh token và yếu tố cũ | Phải kiểm tra hiệu lực; chỉ gửi lệnh thu hồi chưa đủ |
| Nguy cơ sử dụng lại quyết định | Hạn hiệu lực ngắn, tiêu thụ nguyên tử và kiểm tra trạng thái hiện hành | Hết hạn phê duyệt không tự thu hồi quyền đã cấp |
| Nguy cơ mở rộng quyền | Recovery context có phạm vi hẹp, API chỉ chấp nhận hành động được duyệt | Ẩn nút giao diện không giới hạn được API |
| Khó điều tra quyết định thủ công | Dấu vết đầy đủ, tham chiếu bằng chứng và hậu kiểm | Nhật ký chỉ giúp truy vết, không trực tiếp ngăn mọi hành vi chiếm đoạt |

### Ví dụ các biện pháp bù không đủ

- Thêm một OTP vào cùng hộp thư đang bị nghi xâm nhập.
- Đợi lâu hơn nhưng không có bằng chứng nào mới.
- Chặn đổi email nhưng vẫn cho tải toàn bộ dữ liệu nhạy cảm.
- Cho người dùng mới đăng ký passkey rồi dùng passkey đó để chứng minh họ có quyền recovery trước khi đăng ký.
- Yêu cầu nhân viên viết ghi chú dài hơn trong khi công cụ vẫn cho cấp toàn quyền.

Một biện pháp bù cần trả lời được: nó giảm khả năng hoặc hậu quả của đường tấn công nào, bằng cơ chế gì, và làm sao biết nó đã có hiệu lực?


## 7. Vòng đời một ngoại lệ

Một ngoại lệ cần có trạng thái rõ ràng từ lúc tiếp nhận đến lúc kết thúc.

~~~mermaid
flowchart TD
    A["Tiếp nhận yêu cầu"] --> B["Phân loại quy tắc và thẩm quyền"]
    B --> C["Xác minh bằng chứng và đánh giá rủi ro"]
    C --> D{"Đủ điều kiện xét duyệt?"}
    D -->|Không| E["Từ chối hoặc yêu cầu thêm bằng chứng"]
    D -->|Có| F["Phê duyệt phạm vi và biện pháp bù"]
    F --> G["Chờ điều kiện thực thi"]
    G --> H{"Còn hiệu lực và điều kiện vẫn đúng?"}
    H -->|Có| I["Thực thi đúng một lần"]
    H -->|Không| J["Hủy, hết hạn hoặc đánh giá lại"]
    I --> K["Hậu kiểm quyền và đóng hồ sơ"]
~~~

### Bước 1: Tiếp nhận qua kênh được kiểm soát

Gắn yêu cầu với đúng hồ sơ recovery và tài khoản nội bộ. Kiểm tra các yêu cầu liên quan để tránh một quyết định từ chối bị bỏ qua chỉ bằng cách mở ticket mới.

Việc liên kết hồ sơ cần có kiểm soát truy cập và cách xử lý trùng hợp hợp lệ. Không tự gắn nhãn mọi người dùng mở lại yêu cầu là gian lận; có thể họ chưa nhận được giải thích hoặc hỗ trợ phù hợp.

### Bước 2: Phân loại và kiểm tra thẩm quyền

Xác định yêu cầu nằm trong chính sách hay thật sự cần ngoại lệ. Nếu không thuộc loại được phép xét, chuyển tới đúng cấp hoặc từ chối.

Không để công cụ mặc định rằng mọi nhân viên có quyền sửa tài khoản đều có quyền chấp nhận rủi ro ngoại lệ.

### Bước 3: Xác minh và đánh giá

Ghi rõ yếu tố đã mất, kênh có thể bị xâm nhập và hành động được đề xuất. Kiểm tra tính hợp lệ, độ mới và sự độc lập của bằng chứng.

Đánh giá phải xét cả rủi ro chiếm đoạt, mất dữ liệu và việc người dùng thật không thể recovery. Tuy nhiên, thiệt hại do chậm xử lý không tự chứng minh người yêu cầu có quyền truy cập.

### Bước 4: Phê duyệt quyết định cụ thể

Người phê duyệt xem đúng kế hoạch, bằng chứng và biện pháp bù. Nếu kế hoạch thay đổi sau phê duyệt, quyết định cũ không tự bao phủ phần mới.

Có thể yêu cầu một người khác thực hiện hoặc kiểm tra hành động nhạy cảm. Cơ chế này cần được hỗ trợ bằng quyền hệ thống, không chỉ bằng hướng dẫn rằng “nên nhờ đồng nghiệp xem”.

### Bước 5: Kiểm tra lại ngay trước thực thi

Một quyết định hợp lệ ở thời điểm duyệt có thể không còn phù hợp khi thực hiện. Ví dụ:

- Người dùng thật vừa thay yếu tố hoặc kênh recovery.
- Có cảnh báo chiếm đoạt mới.
- Bằng chứng đã hết độ mới.
- Một hồ sơ recovery khác đã hoàn tất.
- Phê duyệt đã bị hủy hoặc hết hạn.

Cần kiểm tra lại các điều kiện nền, thay vì chỉ kiểm tra rằng ticket có chữ “approved”.

### Bước 6: Thực thi và hậu kiểm

Áp dụng đúng hành động đã duyệt, đánh dấu quyền ngoại lệ đã dùng và xử lý session theo kế hoạch. Sau đó kiểm tra kết quả, thông báo phù hợp và đóng hồ sơ khi các công việc cần thiết đã hoàn tất.

Không đánh dấu thành công nếu hệ thống mới xếp hàng thu hồi session mà chưa biết việc thu hồi có hiệu lực hay không.

## 8. Biến phê duyệt thành quyền thực thi có giới hạn

Một lỗi thiết kế phổ biến là dùng cờ chung như `recoveryApproved = true`. Cờ đó không cho biết duyệt điều gì, cho tài khoản nào, còn hiệu lực bao lâu và đã dùng chưa.

Một bản ghi quyền ngoại lệ có thể chứa:

~~~text
exception_id
recovery_attempt_id
account_id
policy_version
approved_plan_digest
allowed_actions
evidence_reference
evidence_valid_until
approved_security_version
approved_by
approved_at
not_before
expires_at
state
consumed_at
revoked_at
~~~

Đây là mô hình minh họa, không phải danh sách trường bắt buộc cho mọi hệ thống.

### Các ràng buộc quan trọng

**Tài khoản và hồ sơ.** Quyền phải gắn với định danh nội bộ ổn định. Không chỉ dựa vào địa chỉ email người yêu cầu gửi lên, đặc biệt khi hành động đang xét là đổi email.

**Kế hoạch và hành động.** Nếu ngoại lệ cho phép điều chỉnh thời gian chờ để bổ sung MFA, nó không tự cho đổi email, xuất dữ liệu hoặc tạo token API. Kế hoạch nên lấy từ trạng thái đáng tin cậy phía máy chủ và có thể kiểm tra việc bị sửa.

**Bằng chứng và phiên bản bảo mật.** Kết quả xác minh phải còn giá trị. Thay đổi yếu tố, kênh recovery hoặc sự kiện quan trọng có thể yêu cầu đánh giá lại quyết định.

**Thời gian và trạng thái.** Quyền chưa đến thời điểm sử dụng, hết hạn, bị thu hồi hoặc đã tiêu thụ đều không được dùng tiếp.

**Ngữ cảnh thực thi.** Có mã ngoại lệ không tự là đủ. Người dùng hoặc nhân viên thực hiện còn phải thỏa yêu cầu xác thực, phân quyền và ràng buộc với hồ sơ tương ứng.

**Số lần áp dụng.** Việc kiểm tra và đánh dấu sử dụng phải nguyên tử đối với thay đổi bảo mật. Hai yêu cầu đồng thời không được cùng biến một phê duyệt thành hai lần cấp quyền.

Nếu cần token để truyền quyền giữa các thành phần, token phải khó đoán hoặc được bảo vệ toàn vẹn phù hợp, có mục đích và hạn riêng. Chữ ký đúng không chứng minh rằng quyền chưa bị thu hồi hoặc chưa dùng; thiết kế vẫn cần cách kiểm tra trạng thái hiện hành.

### Mã giả cho ranh giới thực thi

~~~text
function executeRecoveryException(exceptionId, context, submittedAction):
    require context is authenticated as required
    require validSubmissionContext(context)

    transaction:
        exception = lockException(exceptionId)
        attempt = lockRecoveryAttempt(exception.recoveryAttemptId)
        account = lockAccount(exception.accountId)

        require context is authorized for attempt
        require attempt.accountId == account.id
        require attempt is active
        require exception.state == "APPROVED"
        require exception.revokedAt is null
        require exception.consumedAt is null
        require exception.notBefore <= now
        require now < exception.expiresAt
        require now < exception.evidenceValidUntil

        require account.securityVersion ==
                exception.approvedSecurityVersion

        plan = loadApprovedPlan(exception)
        require digest(plan) == exception.approvedPlanDigest
        require submittedAction is permitted by plan
        require requiredEvidenceStillValid(attempt, plan)
        require compensatingControlsReady(plan)
        require approversRemainAuthorized(exception)

        applyApprovedAction(account, attempt, plan, submittedAction)
        applyRequiredSessionControls(account, plan)

        exception.consumedAt = now
        exception.state = "EXECUTED"
        account.securityVersion += 1

        recordDecisionAndOutcomeWithoutSecrets(exception, plan)
        enqueueRequiredNotification(exception, account)

    return nextStepWithOnlyApprovedPermissions()
~~~

Mã giả này diễn tả các bất biến, không bao quát toàn bộ triển khai. Với thao tác nhiều bước như đăng ký yếu tố mới, mỗi bước cần được ràng buộc với đúng challenge, hồ sơ và hành động; không chỉ tin dữ liệu do trình duyệt gửi lên.

Nếu nhiều dịch vụ cùng quản lý credential và session, cần cơ chế phối hợp, tính lặp lại an toàn và ranh giới thu hồi thực tế. Không thể tạo một transaction cơ sở dữ liệu cục bộ rồi giả định mọi quyền ở dịch vụ khác đã đổi nguyên tử theo nó.

Thứ tự khóa và xử lý retry cũng cần nhất quán. Sau một timeout, hệ thống nên tra kết quả của cùng thao tác để tránh áp dụng lại, thay vì cấp thêm một ngoại lệ mới mà không biết ngoại lệ trước đã thực thi hay chưa.

## 9. Hết hạn, hủy và thu hồi: ba việc khác nhau

Một quyền ngoại lệ chưa dùng có thể tự hết hạn. Một quyết định đã dùng có thể để lại thay đổi lâu dài. Đây là hai vòng đời cần quản lý riêng.

### Hết hạn trước khi sử dụng

Khi quá hạn, quyền không được thực thi. Nếu người dùng vẫn cần tiếp tục, kiểm tra lại điều kiện và phát hành quyết định phù hợp; không sửa trực tiếp thời hạn để biến một phê duyệt cũ thành quyền vô hạn.

Gia hạn cũng là một quyết định cần thẩm quyền và căn cứ. Một số bằng chứng có thể phải xác minh lại thay vì chỉ tăng `expires_at`.

### Hủy hoặc thu hồi trước khi sử dụng

Một phê duyệt cần bị vô hiệu khi người có thẩm quyền rút lại, xuất hiện sự kiện làm giả định ban đầu sai hoặc hồ sơ kết thúc theo nhánh khác.

Nếu lưu quyền trong token tự chứa, phải cân nhắc cách vô hiệu trước hạn. Việc ghi “revoked” trong ticket không có tác dụng nếu API chỉ kiểm tra chữ ký token và không biết trạng thái thu hồi.

### Sau khi đã sử dụng

Giả sử ngoại lệ chỉ có hiệu lực mười phút, nhưng trong mười phút đó đối thủ đăng ký được một passkey. Hết mười phút không làm passkey tự biến mất.

Kế hoạch hậu kiểm phải xem xét các hậu quả:

- Yếu tố mới nào được thêm và yếu tố cũ nào bị xóa?
- Session hoặc refresh token nào được cấp?
- Kênh recovery có thay đổi không?
- Quyền ứng dụng, token API hoặc dấu tin cậy thiết bị có phát sinh không?
- Dữ liệu nhạy cảm đã được truy cập hay xuất ra chưa?

Nếu phát hiện quyết định sai sau thực thi, cần xử lý như một sự kiện bảo mật phù hợp: hạn chế quyền, thu hồi yếu tố và session liên quan, xác minh lại quyền sở hữu và điều tra phạm vi ảnh hưởng.

Không phải mọi thay đổi đều đảo ngược được. Thu hồi session không thể lấy lại dữ liệu đã bị đọc. Vì vậy, kiểm soát trước thực thi và hạn chế quyền ngay sau recovery có vai trò khác với hậu kiểm.

### Đóng hồ sơ không đồng nghĩa xóa dấu vết

Có thể đóng hồ sơ sau khi công việc hoàn tất, nhưng phải giữ được lịch sử quyết định theo chính sách lưu giữ và quyền truy cập của dịch vụ. Không sửa lịch sử để làm một ngoại lệ bị thu hồi trông như chưa từng được phê duyệt.

## 10. Hai ví dụ ra quyết định

### Ví dụ A: đề nghị rút ngắn thời gian chờ

Một dịch vụ có quy tắc minh họa: bổ sung yếu tố MFA sau recovery phải chờ 24 giờ. Người dùng mất thiết bị chứa ứng dụng MFA nhưng vẫn có một khóa bảo mật đã đăng ký trước sự cố và còn đáp ứng yêu cầu xác thực độc lập của dịch vụ.

Người dùng đề nghị rút ngắn thời gian chờ vì cần tiếp tục công việc. Giả sử chính sách cho phép xét ngoại lệ thời gian chờ khi có đủ bằng chứng và được đúng cấp phê duyệt.

Phân tích cần tách rõ:

- **Quy tắc bị lệch:** thời gian chờ, không phải yêu cầu chứng minh quyền sở hữu.
- **Bằng chứng:** khóa bảo mật đã đăng ký, được kiểm tra theo yêu cầu của dịch vụ; không phải thiết bị mới do người yêu cầu vừa thêm.
- **Rủi ro tăng:** giảm khoảng thời gian phát hiện và phản ứng trước khi thay đổi.
- **Biện pháp bù:** kiểm tra nguy cơ xâm nhập, thông báo qua kênh đã thiết lập, giới hạn hành động và kế hoạch session phù hợp.
- **Phạm vi:** đúng hồ sơ, đúng hành động bổ sung MFA; các thay đổi khác vẫn theo chính sách.
- **Thực thi:** chỉ sau thời điểm mới được phê duyệt, còn hạn, dùng một lần và kiểm tra lại trạng thái tài khoản.

Ngay cả khi có bằng chứng mạnh, người xét duyệt vẫn có thể từ chối nếu xuất hiện dấu hiệu rủi ro khác. Con số 24 giờ chỉ nhằm minh họa loại quy tắc; không phải khuyến nghị thời gian chờ chung.

Nếu trường hợp này xuất hiện thường xuyên và có thể mô tả điều kiện an toàn ổn định, nên đưa thành nhánh chính sách được quản lý, thay vì phê duyệt ngoại lệ lặp lại.

### Ví dụ B: người yêu cầu chỉ còn hộp thư và lịch sử hóa đơn

Một người liên hệ cho biết đã mất mật khẩu, MFA và mọi thiết bị. Họ gửi email từ đúng địa chỉ, đọc được hóa đơn cũ và nói rằng việc chậm recovery gây thiệt hại lớn.

Những dữ liệu này phù hợp cả với người dùng thật lẫn một đối thủ đang kiểm soát hộp thư. Nếu tài khoản đòi hỏi bằng chứng độc lập và không có bằng chứng phù hợp, lý do khẩn cấp không đủ để xóa yếu tố.

Một quyết định thích hợp có thể là:

1. Chưa cấp quyền đổi yếu tố hoặc session đầy đủ.
2. Giải thích rằng các bằng chứng hiện có chưa đáp ứng điều kiện, không hướng dẫn cách né kiểm soát.
3. Kiểm tra các phương án dự phòng hoặc thẩm quyền ủy nhiệm đã thiết lập trước nếu thật sự có.
4. Chuyển cấp theo phạm vi được phép khi cần, không hứa kết quả recovery.
5. Ghi rõ giới hạn và hướng dẫn người dùng xử lý kênh email nếu nghi bị xâm nhập.

Thu thập thêm nhiều thông tin từ cùng hộp thư hoặc yêu cầu một đồng nghiệp bấm duyệt không khắc phục điểm thiếu căn bản.

Ở dịch vụ chỉ dùng email làm gốc tin cậy, quyết định có thể khác vì mức bảo đảm sản phẩm đã chấp nhận khác. Tuy nhiên, không được tuyên bố luồng ấy đã chống được đối thủ kiểm soát email.

## 11. Tình huống khẩn cấp và tài khoản nhạy cảm

### Khẩn cấp về vận hành không tự là quyền với tài khoản

Một nhà cung cấp OTP bị gián đoạn có thể khiến nhiều người không recovery được. Cần kích hoạt phương án dự phòng đã phê duyệt, giới hạn đúng nhóm bị ảnh hưởng và theo dõi tác động.

Tắt MFA hoặc đổi mọi tài khoản sang email-only là một thay đổi diện rộng về mức bảo đảm. Nó không nên bị ngụy trang thành hàng nghìn ngoại lệ nhỏ.

Một thay đổi khẩn cấp cần có:

- Người có thẩm quyền trực và phạm vi quyết định.
- Điều kiện kích hoạt, thời điểm hết hiệu lực và người theo dõi.
- Kiểm soát được giữ lại cùng rủi ro còn lại.
- Kế hoạch quay lui không mở lại đường đã biết là nguy hiểm.
- Rà soát sau sự kiện và xác nhận cấu hình tạm đã kết thúc.

### Tài khoản quản trị và quyền ủy nhiệm

Tài khoản nhạy cảm có thể cần ngưỡng thẩm quyền cao hơn, người kiểm tra độc lập hoặc không cho phép một số loại ngoại lệ.

Trong môi trường tổ chức, quyền của quản trị viên để cấp lại tài khoản phải được xác lập trước và xác minh qua kênh đáng tin cậy. Việc nhận một thư tự nhận là lãnh đạo không tạo quyền ủy nhiệm.

Cũng cần phân biệt:

- Xác minh một cá nhân là người dùng cũ.
- Thực hiện quyền quản trị hợp lệ của tổ chức để gán lại quyền.

Hai cơ sở cấp quyền này có thể dẫn tới quy trình khác nhau và cần được ghi đúng, không gọi mọi thao tác quản trị là đã chứng minh danh tính của người dùng trước đó.

Nếu có cơ chế truy cập khẩn cấp cho quản trị, cơ chế ấy cần phạm vi, người sở hữu và vòng đời riêng. Không dùng một tài khoản khẩn cấp dùng chung để tùy ý recovery tài khoản khách hàng.

## 12. Quan sát, chống lạm dụng và học từ ngoại lệ

Nhật ký ngoại lệ cần đủ để trả lời: ai đề xuất, ai kiểm tra, ai phê duyệt, dựa trên phiên bản và bằng chứng nào, hành động gì đã được thực hiện, kết quả ra sao.

Không ghi bí mật recovery vào log. Dữ liệu danh tính, mạng và thiết bị cần được hạn chế truy cập và lưu theo nhu cầu thực tế.

### Các mẫu nên điều tra

- Một người mở nhiều hồ sơ cho cùng tài khoản sau khi bị từ chối.
- Nhiều tài khoản dùng cùng một câu chuyện hoặc nguồn liên hệ.
- Một nhân viên có tỷ lệ phê duyệt cao bất thường ở một loại ngoại lệ.
- Phê duyệt diễn ra rất nhanh nhưng không có bằng chứng bắt buộc.
- Kế hoạch bị sửa sau khi đã duyệt.
- Quyền ngoại lệ được dùng sát hạn nhiều lần hoặc xuất hiện retry không có kết quả rõ.
- Một loại ngoại lệ liên tục được gia hạn hoặc không có bằng chứng thu hồi.

Các mẫu này là tín hiệu để kiểm tra, không phải kết luận tự động về người dùng hoặc nhân viên.

Giới hạn tần suất có thể áp dụng cho tạo yêu cầu, thử bằng chứng và liên hệ hỗ trợ. Cần tránh để đối thủ dễ khóa người dùng thật bằng cách tạo nhiều yêu cầu cho tài khoản của họ; luôn phải xem tác động từ chối dịch vụ và có đường xử lý phù hợp.

### Số liệu cần đọc theo ngữ cảnh

Có thể theo dõi số yêu cầu, tỷ lệ phê duyệt, lý do từ chối, thời gian xử lý, số quyền đã dùng, số hết hạn, số lần gia hạn và sự cố liên quan.

Khi tính tỷ lệ, nêu rõ đơn vị là yêu cầu, hồ sơ ngoại lệ hay tài khoản. Một tài khoản có thể tạo nhiều yêu cầu. Cũng cần xét độ trễ phát hiện chiếm đoạt; “chưa có khiếu nại” không chứng minh mọi quyết định đều đúng.

Không tối ưu riêng thời gian xử lý hoặc tỷ lệ chấp thuận. Các chỉ số này có thể tăng khi nhân viên bỏ kiểm soát. Cần đọc cùng chất lượng bằng chứng, hậu quả quyền hạn và việc người dùng thật bị chặn nhầm.

Nếu một ngoại lệ an toàn lặp lại thường xuyên, xem xét đưa thành luồng chuẩn với điều kiện rõ. Nếu ngoại lệ chủ yếu tồn tại để né một quy tắc bất tiện nhưng cần thiết, cần cải tiến phương án phục hồi thay vì âm thầm hạ bảo đảm.

## 13. Câu hỏi kiểm tra trước khi cho thực thi

Danh sách sau dùng để thiết kế và vận hành quy trình, không phải kết quả kiểm thử của một hệ thống cụ thể:

1. Đã chỉ ra đúng quy tắc bị lệch và phiên bản chính sách chưa?
2. Có đường chuẩn hoặc phương án dự phòng hợp lệ nào chưa được xem xét không?
3. Bằng chứng có thực sự liên kết với tài khoản cũ, còn mới và độc lập với sự cố không?
4. Người phê duyệt có thẩm quyền với loại tài khoản và mức rủi ro này không?
5. Biện pháp bù giảm đúng đường tấn công hay chỉ thêm thao tác hình thức?
6. Quyền đã gắn với đúng tài khoản, hồ sơ, kế hoạch và hành động chưa?
7. Kế hoạch có thay đổi sau phê duyệt không?
8. Hệ thống có kiểm tra lại trạng thái hiện hành ngay trước khi áp dụng không?
9. Thao tác có chống phát lại và xử lý cạnh tranh an toàn không?
10. Recovery context có bị dùng để nhận quyền ngoài phạm vi không?
11. Có cách hết hạn, hủy và thu hồi thực sự tại nơi kiểm tra quyền không?
12. Đã phân biệt hết hạn quyền ngoại lệ với thu hồi yếu tố hoặc session được tạo từ nó chưa?
13. Ai kiểm tra kết quả và chịu trách nhiệm đóng các việc còn lại?
14. Nếu bằng chứng không đủ, có thể chưa cấp quyền mà vẫn hướng dẫn người dùng rõ ràng không?

Ngoại lệ chỉ có giá trị khi giúp giải quyết một trường hợp cụ thể trong một ranh giới có thể giải thích và kiểm chứng. Một câu chuyện khẩn cấp, một ticket được duyệt hay một quyền quản trị rộng không được tự biến thành quyền khôi phục toàn bộ tài khoản.

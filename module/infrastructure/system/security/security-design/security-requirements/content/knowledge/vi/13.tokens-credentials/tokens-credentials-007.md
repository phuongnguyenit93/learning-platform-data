# Token revocation

## 1. Thu hồi token là một yêu cầu về hiệu lực truy cập

Token revocation là việc làm cho một token, một nhóm token hoặc một quan hệ cấp quyền không còn được chấp nhận trước khi chúng tự hết hạn theo chính sách ban đầu.

Tình huống thường gặp gồm người dùng đăng xuất, mất thiết bị, lộ credential, khóa tài khoản, gỡ quyền, chấm dứt tích hợp hoặc phát hiện khóa ký bị xâm phạm.

Trong thiết kế yêu cầu bảo mật, “có chức năng revoke” chưa đủ. Cần biết:

- Thứ gì bị thu hồi: một token, phiên, chuỗi refresh, grant, client hay toàn bộ tài khoản?
- Ai có quyền phát lệnh và trong điều kiện nào?
- Token đã phát hành còn dùng được ở đâu và trong bao lâu?
- Cache, replica và kết nối đang mở xử lý thế nào?
- Làm sao chứng minh việc thu hồi đã có hiệu lực tại nơi ra quyết định truy cập?

Một thông báo “thu hồi thành công” từ hệ thống quản trị không tự chứng minh mọi API đã ngừng chấp nhận token. Yêu cầu cần liên kết hành động quản trị với hiệu lực tại điểm thực thi.

## 2. Phân biệt thu hồi, hết hạn và những hành động liên quan

| Khái niệm | Điều nó thay đổi | Điều không được mặc định |
| --- | --- | --- |
| Token expiry | Token vượt thời hạn đã định | Không nhất thiết đáp ứng nhu cầu chặn sớm khi xảy ra sự cố |
| Token revocation | Hiệu lực token hoặc nhóm token trước hạn | Không tự đảo ngược hành động đã hoàn thành |
| Logout ở client | Trạng thái và credential client đang giữ | Bản sao credential ở nơi khác có thể vẫn dùng được |
| Ngừng refresh | Khả năng xin access token mới | Access token đã cấp có thể còn hiệu lực |
| Khóa tài khoản | Trạng thái chủ thể | API kiểm tra token offline có thể chưa biết thay đổi |
| Gỡ permission | Quyền thực hiện hành động | Token có chữ ký hợp lệ vẫn có thể chứa dữ kiện quyền cũ |
| Rotation credential | Credential mới thay credential cũ theo quy trình | Nếu credential cũ vẫn được chấp nhận thì chưa bị thu hồi |
| Rotation khóa ký | Khóa mới được dùng phát hành token | Khóa cũ có thể vẫn nằm trong tập khóa được tin cậy để kiểm tra |

Thu hồi là một điều kiện khiến yêu cầu truy cập bị từ chối. API vẫn cần kiểm tra chữ ký hoặc bằng chứng token, nhà phát hành, đối tượng nhận, thời hạn và quyền trên tài nguyên.

Một token chưa bị thu hồi không tự trở thành token hợp lệ. Ngược lại, token còn hạn và có chữ ký đúng vẫn có thể phải bị từ chối vì đã thu hồi.

### Bearer token và token có ràng buộc bên gửi

Với bearer token, việc giữ bản sao có thể đủ để sử dụng theo cơ chế được triển khai. Token có ràng buộc bằng chứng sở hữu hoặc bên gửi có thể giảm rủi ro khi chỉ token bị lấy cắp.

Nhưng ràng buộc bên gửi không thay thế thu hồi. Tài khoản có thể bị khóa hoặc thiết bị chứa cả token và khóa có thể bị chiếm. Hệ thống vẫn cần chính sách chấm dứt quyền phù hợp.

## 3. Xác định phạm vi thu hồi trước khi chọn cơ chế

| Phạm vi | Ví dụ | Những liên kết cần có |
| --- | --- | --- |
| Một token | Access token bị lộ | Mã nhận diện hoặc tham chiếu đáng tin cậy của token |
| Một chuỗi refresh | Refresh credential của một thiết bị bị lấy cắp | Quan hệ giữa các thế hệ refresh và phiên hoặc grant |
| Một phiên | Người dùng chọn đăng xuất thiết bị đang dùng | Token nào thuộc phiên đó, gồm credential đã cấp |
| Một grant hoặc quan hệ ủy quyền | Người dùng ngừng cho một ứng dụng truy cập | Token và client liên quan đến grant |
| Một client hoặc workload | Tích hợp đối tác bị chấm dứt | Principal, credential và token của tích hợp |
| Một chủ thể | Khóa mọi truy cập của tài khoản | Mọi phiên, client và miền trong phạm vi chính sách |
| Một miền khóa hoặc nhà phát hành | Khóa ký bị xâm phạm | Tập khóa được tin cậy và token bị ảnh hưởng |

Không nên dùng cụm “thu hồi người dùng” nếu ý định thực tế chỉ là thu hồi một refresh token trên một thiết bị.

Phạm vi quá hẹp không chặn được sự cố. Phạm vi quá rộng có thể làm gián đoạn người dùng hoặc hệ thống không liên quan. Yêu cầu phải chọn phạm vi theo loại sự kiện.

### Ví dụ logout một phiên

Giả sử phiên S có:

~~~text
Refresh token R1 -> R2 -> R3
Access token A1, A2, A3 đã được cấp
~~~

Thu hồi R3 có thể ngăn lần refresh tiếp theo. Nhưng A2 hoặc A3 còn hạn không tự mất hiệu lực nếu API chỉ kiểm tra chữ ký và thời gian.

Nếu yêu cầu là “logout phiên S chặn mọi yêu cầu mới của S trong 60 giây”, thiết kế phải xử lý cả credential truy cập đã phát hành, không chỉ credential refresh hiện tại.

### Quan hệ với phiên mới sau xác thực lại

Một người dùng có thể xác thực hợp lệ sau khi phiên cũ bị thu hồi và tạo phiên mới, nếu tài khoản vẫn được phép. Việc đó không đồng nghĩa token cũ được sống lại.

Cần phân biệt thu hồi một phiên với khóa toàn tài khoản; nếu khóa tài khoản đang có hiệu lực, đường cấp token mới cũng phải đáp ứng chính sách khóa.

## 4. Từ mô hình đe dọa đến yêu cầu cụ thể

| Sự kiện | Rủi ro | Hành vi cần đặc tả |
| --- | --- | --- |
| Người dùng logout nhưng token bị sao chép | Kẻ giữ bản sao tiếp tục truy cập | Phạm vi token bị chặn và thời gian có hiệu lực |
| Mất thiết bị chứa refresh credential | Duy trì khả năng xin token mới | Thu hồi chuỗi liên quan và xử lý access token đã cấp |
| Gỡ quyền quản trị | Dùng quyền cũ trong token | Đánh giá quyền hiện tại hoặc vô hiệu hóa dữ kiện cũ trong giới hạn đã định |
| Tài khoản bị khóa | Các phiên khác vẫn hoạt động | Ngừng cấp mới, refresh và chấp nhận token trong phạm vi khóa |
| Sự kiện thu hồi bị mất trên đường truyền | Một số node tiếp tục cho phép | Lưu bền, retry, đối soát và giới hạn độ trễ |
| Request cũ ghi đè trạng thái mới | Token bị thu hồi trở lại active | Cập nhật có thứ tự, phiên bản và ngữ nghĩa không hồi sinh |
| Khóa ký bị lấy cắp | Kẻ tấn công tự tạo token không có trong danh sách | Chấm dứt tin cậy khóa bị ảnh hưởng và xử lý lại miền token |
| Người không có quyền gọi revoke | Gây gián đoạn cho người khác | Xác thực, phân quyền và kiểm soát lạm dụng đường thu hồi |

Từ bảng rủi ro, mỗi yêu cầu còn cần owner, điểm thực thi, mốc đo, ngưỡng thời gian và bằng chứng chấp nhận.

Không chọn denylist chỉ vì có thể thêm một bảng dữ liệu; cần chứng minh danh sách đó được kiểm tra ở mọi nơi và có ngữ nghĩa lưu giữ đúng.

## 5. Các mô hình thực thi thu hồi

### 5.1. Token opaque và tra trạng thái

Với token opaque, API hoặc thành phần xác thực có thể dùng một dịch vụ kiểm tra trạng thái. Khi trạng thái bị vô hiệu hóa, đường kiểm tra phải trả về kết quả không chấp nhận theo chính sách.

Cơ chế này giúp tập trung trạng thái nhưng vẫn có các câu hỏi:

- Kết quả hợp lệ có được cache không?
- Cache giữ trong bao lâu?
- Có đường API nào không kiểm tra trạng thái không?
- Khi không gọi được dịch vụ trạng thái, request bị xử lý thế nào?
- Chủ thể hoặc grant bị khóa có được phản ánh vào kết quả không?

Kết quả kiểm tra cần được bảo vệ trên đường truyền và gắn với đúng token, bên gọi cùng ngữ cảnh được yêu cầu. API không được coi kết quả “đang hoạt động” là thay thế toàn bộ kiểm tra audience hoặc quyền nghiệp vụ.

### 5.2. Token tự chứa được xác minh offline

Một token đã ký có thể được API kiểm tra tại chỗ mà không liên hệ nhà phát hành. Nếu API chỉ biết chữ ký, thời hạn và các dữ kiện cố định trong token, nó không tự biết một sự kiện thu hồi vừa xảy ra.

Các hướng thiết kế có thể gồm:

- Tra danh sách token đã thu hồi.
- Kiểm tra trạng thái hoặc phiên bản của phiên, grant hay principal.
- Nhận sự kiện cập nhật trạng thái tới điểm thực thi.
- Dùng thời hạn ngắn trong phạm vi rủi ro được chấp thuận.
- Kết hợp các cách trên theo loại API.

Không bắt buộc mọi hệ thống dùng cùng một cách. Yêu cầu phải nêu kết quả cần đạt và thời gian chặn; kiến trúc phải chứng minh cách chọn đáp ứng được.

### 5.3. Denylist theo token

Denylist có thể lưu mã nhận diện đáng tin cậy hoặc fingerprint theo thiết kế để từ chối token cụ thể. Cần tránh va chạm giữa nhà phát hành, môi trường hoặc miền token.

Một giá trị định danh do client tự gửi không đủ để quyết định token tương ứng bị thu hồi hay chưa. Định danh cần được lấy hoặc kiểm chứng trong ngữ cảnh token đã được xác thực phù hợp.

Danh sách phải tồn tại đủ lâu để token không thể được chấp nhận trở lại. Nếu token có thể được chấp nhận đến thời hạn cộng dung sai, xóa entry trước mốc đó có thể làm token sống lại.

Nếu token không có giới hạn cuối cùng đáng tin cậy, không được tự chọn một TTL ngắn cho denylist rồi khẳng định thu hồi vĩnh viễn.

Denylist token đã biết không đủ để xử lý khóa ký bị xâm phạm: kẻ tấn công có thể tạo token mới chưa có trong danh sách.

### 5.4. Phiên bản hoặc thế hệ của phiên và grant

Token có thể được liên kết với một phiên hoặc grant có phiên bản. Khi thu hồi, hệ thống cập nhật phiên bản hoặc trạng thái; token thuộc trạng thái cũ bị từ chối.

Cách này có thể giảm nhu cầu liệt kê từng token, nhưng vẫn cần kiểm tra trạng thái hiện tại hoặc phân phối nó đến điểm thực thi.

Phải tránh việc bản sao cũ hoặc request cập nhật muộn ghi đè phiên bản mới hơn. Một lần rotation bình thường cũng không được vô tình đặt lại dấu thu hồi.

### 5.5. Token sống ngắn

Thời hạn ngắn giới hạn cửa sổ sử dụng khi không có cơ chế chặn sớm. Đây có thể là lựa chọn phù hợp cho một số tài nguyên, nhưng phải được mô tả đúng.

Nếu access token sống tối đa 10 phút và API chỉ xác minh offline, một token vừa cấp có thể còn dùng gần 10 phút, cộng ảnh hưởng của dung sai và ngữ nghĩa thời gian. Cơ chế đó không tự đáp ứng yêu cầu thu hồi trong 60 giây.

Có thể chọn chờ hết hạn theo mức rủi ro được phê duyệt, nhưng không nên gọi đó là “thu hồi tức thì”.

### 5.6. Ngừng tin cậy khóa ký

Trong sự cố khóa ký bị xâm phạm, cần xử lý tập khóa được tin cậy tại các điểm nhận. Chỉ ngừng ký token mới bằng khóa đó không ngăn token cũ hoặc token giả mới được xác minh bằng khóa còn được tin cậy.

Cần phân biệt rotation định kỳ, nơi khóa cũ có thể được giữ để xác minh token đang sống, với xử lý sự cố, nơi có thể phải chấm dứt tin cậy khóa bị ảnh hưởng sớm hơn.

Phạm vi ảnh hưởng có thể lớn; yêu cầu cần có quy trình kiểm soát, phân phối trạng thái tin cậy, xác thực lại và phục hồi. Không xem rotation khóa ký là nút thu hồi riêng cho một người dùng.

## 6. Đặc tả độ trễ thu hồi

### 6.1. Chọn mốc bắt đầu và kết thúc

Một phép đo rõ ràng có thể dùng:

- T0: hệ thống quản trị xác nhận đã ghi bền lệnh thu hồi hợp lệ.
- Ti: thời điểm điểm thực thi i bắt đầu từ chối mọi request mới thuộc phạm vi.
- D: thời gian tối đa được phép.

~~~text
Với mọi điểm thực thi i trong phạm vi:
Ti - T0 <= D
~~~

“Đã nhận request”, “đã ghi database”, “đã phát sự kiện” và “mọi API đã từ chối” là những mốc khác nhau.

Nếu giao diện chỉ xác nhận tiếp nhận lệnh, nên thể hiện trạng thái đó đúng nghĩa. Không gọi một thao tác đã hoàn tất trên toàn hệ thống nếu chưa có bằng chứng phù hợp.

### 6.2. Cache và đường truyền trạng thái

Độ trễ thực tế có thể chịu ảnh hưởng của xử lý lệnh, replication, sự kiện, cache, lịch retry và độ lệch thời gian. Cần đánh giá toàn bộ đường đi thay vì chỉ thời gian một truy vấn.

Ví dụ, yêu cầu chặn trong 60 giây không phù hợp với cache “token hợp lệ” sống 5 phút nếu không có cơ chế vô hiệu hóa cache hoặc kiểm tra bổ sung.

Thời hạn cache cũng không được vượt hạn cuối cùng của token theo chính sách. Một quyết định hợp lệ lấy trước khi token hết hạn không trở thành quyền hợp lệ sau hạn vì cache chưa dọn.

### 6.3. Request mới và công việc đang chạy

Yêu cầu chặn “request mới” không tự quyết định mọi request đang chạy phải bị hủy. Cần nêu điểm quyết định:

- Khi nhận request.
- Trước hành động nhạy cảm.
- Trước khi commit.
- Khi nhận từng thông điệp hoặc phát dữ liệu liên tục.

Kết nối WebSocket và stream đã mở cần yêu cầu riêng về tái đánh giá hoặc chấm dứt. Một token bị từ chối ở lần kết nối mới không chứng minh kết nối cũ đã ngừng quyền nhận dữ liệu.

Thu hồi cũng không tự hoàn tác giao dịch đã hoàn tất. Xử lý hậu quả và khả năng hủy tác vụ là các yêu cầu nghiệp vụ cần phối hợp.

## 7. Bảo vệ chính chức năng thu hồi

### 7.1. Xác thực và phân quyền

Đường thu hồi là một chức năng có thể gây gián đoạn quyền truy cập. Cần xác định actor nào được thu hồi đối tượng nào:

- Người dùng có thể thu hồi phiên của chính mình trong phạm vi ứng dụng.
- Client có thể thu hồi credential thuộc quan hệ được cấp cho nó theo chính sách.
- Nhân sự xử lý sự cố có thể thu hồi phạm vi rộng hơn bằng quyền được kiểm soát.
- Workload tự động chỉ được thao tác trong phạm vi đã cấp.

Không cho phép client tự nhập một user ID, session ID hoặc mã token bất kỳ để thu hồi đối tượng ngoài quyền.

Nếu đường thu hồi dùng cookie tự động gửi trong trình duyệt, cần đánh giá CSRF cho hành động đó. Các luồng quản trị nhạy cảm có thể cần xác thực lại hoặc phê duyệt theo mức rủi ro.

### 7.2. Idempotency và phản hồi

Gửi lại cùng một yêu cầu thu hồi không được làm token hoạt động trở lại. Retry hợp lệ phải dẫn tới trạng thái thu hồi tương đương thay vì sinh ra grant hoặc phiên mới.

Phản hồi không nên trở thành công cụ dò token tồn tại hoặc thuộc về ai. Một thiết kế có thể dùng phản hồi không tiết lộ sự khác biệt giữa đối tượng không tồn tại và đối tượng đã thu hồi, tùy giao thức và quyền của caller.

Vì vậy, một phản hồi thành công tổng quát không luôn là bằng chứng riêng rằng một token cụ thể đã từng tồn tại và đã bị vô hiệu hóa. Bằng chứng kiểm chứng cần lấy thêm trạng thái quản trị phù hợp và kết quả truy cập tại tài nguyên.

Khi client bị timeout, không được suy ra lệnh chắc chắn thất bại rồi khôi phục trạng thái active. Có thể cần tra kết quả theo mã tác vụ hoặc retry theo ngữ nghĩa idempotent đã định.

### 7.3. Giới hạn lạm dụng và quan sát

Cần kiểm soát khối lượng gọi, phạm vi tác vụ và quyền liệt kê. Một lệnh thu hồi diện rộng có thể cần quy trình khác với logout một phiên.

Audit nên ghi actor, đối tượng tham chiếu, phạm vi, lý do, thời điểm tiếp nhận, thời điểm ghi bền và trạng thái hiệu lực theo khả năng quan sát.

Không ghi nguyên token vào audit hoặc công cụ xử lý sự cố. Mã tác vụ và mã tham chiếu phục vụ điều tra không được trở thành credential sử dụng trực tiếp.

## 8. Thu hồi refresh token và xử lý phát hiện sử dụng lại

Refresh token thường có khả năng xin credential mới, nên việc bị lộ có thể kéo dài tác động vượt vòng đời một access token.

Nếu dùng rotation, mỗi lần sử dụng hợp lệ có thể thay refresh token hiện tại bằng token mới. Các thế hệ cần được liên kết với phạm vi thu hồi đã chọn, chẳng hạn phiên, thiết bị hoặc grant.

Một chuỗi khái niệm:

~~~text
Grant G / phiên S
  R1 -> R2 -> R3
              -> access token được cấp ở từng thời điểm
~~~

Khi phát hiện sử dụng lại token cũ, yêu cầu phải quyết định:

1. Đây là tín hiệu được xử lý theo cơ chế nào.
2. Có thu hồi token hiện tại hoặc toàn chuỗi không.
3. Access token đã cấp bị ảnh hưởng ra sao.
4. Có cần yêu cầu xác thực lại hay thông báo chủ thể không.
5. Hành vi với request đồng thời hoặc retry hợp lệ là gì.

Không phải mọi lần dùng lại đều chứng minh chắc chắn có kẻ tấn công. Hai tab hoặc một client retry sau mất phản hồi cũng có thể tạo tình huống tương tự. Thiết kế cần nêu rõ cách xử lý, không dựa vào một khẳng định tuyệt đối thiếu bằng chứng.

Ngược lại, chấp nhận dùng lại token cũ vô thời hạn để tránh lỗi giao diện làm mất ý nghĩa của rotation.

Nếu chính sách chọn một lần sử dụng nghiêm ngặt, cần bảo đảm chỉ một lần tiêu thụ thành công khi có request đồng thời. Các request còn lại được xử lý theo hợp đồng lỗi hoặc phục hồi đã định, không tạo thêm các chuỗi credential độc lập ngoài chính sách.

Nếu có khoảng xử lý retry, nó phải được giới hạn và phân tích rủi ro. Không dùng cụm “grace period” để che việc credential cũ tiếp tục cấp quyền không kiểm soát.

## 9. Phân tán, lỗi và phục hồi

### 9.1. Lệnh thu hồi phải bền vững và không bị đảo ngược ngoài chính sách

Một hệ thống phát sự kiện thu hồi nhưng không lưu được trạng thái chuẩn có thể mất hiệu lực sau restart. Cần xác định điểm ghi bền và cách đối soát.

Sự kiện có thể đến lặp, đến chậm hoặc không đúng thứ tự. Điểm nhận cần xử lý theo phiên bản hoặc ngữ nghĩa phù hợp để một sự kiện cũ không làm mất trạng thái mới hơn.

Ví dụ, cập nhật “đang hoạt động” được tạo trước lệnh thu hồi không được ghi đè kết quả thu hồi chỉ vì đến sau.

Nếu có quy trình khôi phục quyền, nên coi đó là hành động có quyền và điều kiện riêng. Không tự làm sống lại token đã thu hồi; có thể cần cấp một token mới sau khi thỏa điều kiện.

### 9.2. Không có trạng thái không đồng nghĩa còn hiệu lực

Denylist trống trên một node có thể có nghĩa token chưa bị thu hồi, nhưng cũng có thể là node chưa tải dữ liệu, mất kết nối hoặc khởi động lại.

Thiết kế phải phân biệt trạng thái “đã xác minh không bị thu hồi” với “không thể xác minh điều kiện bắt buộc”. Nếu không, mất dữ liệu sẽ trở thành đường cho phép truy cập.

Với API rủi ro cao, yêu cầu có thể là từ chối khi không xác minh được trạng thái cần thiết. Với một loại truy cập rủi ro thấp, có thể cho phép dùng kết quả cache trong khoảng giới hạn được phê duyệt.

Trong mọi trường hợp, không gia hạn token hoặc tạo phiên mới chỉ vì đường kiểm tra gặp lỗi.

### 9.3. Cache khóa và danh sách tin cậy

Khi sự cố liên quan khóa ký, các điểm nhận có thể vẫn giữ khóa cũ trong cache. Kế hoạch xử lý phải bao gồm cách cập nhật tập khóa được chấp nhận và độ trễ tại từng điểm.

Một thao tác xóa khóa ở máy chủ cấp không tự chứng minh mọi consumer đã dừng tin cậy. Cần kiểm tra cả consumer offline hoặc consumer có lịch cập nhật riêng trong phạm vi cam kết.

Nếu consumer không thể nhận thay đổi trong thời hạn yêu cầu, phải xác định giới hạn thực tế và chính sách rủi ro; không báo đã chặn toàn miền khi chưa có bằng chứng.

### 9.4. Backup và phục hồi trạng thái

Khôi phục một snapshot có thể mang lại trạng thái trước thu hồi. Hệ thống phải bảo đảm token đã hết hạn hoặc bị thu hồi không được chấp nhận trở lại chỉ vì dữ liệu quản trị được quay về bản cũ.

Có thể cần lưu lịch sử hoặc thế hệ thu hồi độc lập, đối soát với nguồn chuẩn, hoặc vô hiệu hóa những quan hệ không thể xác minh sau phục hồi.

Thời gian giữ trạng thái thu hồi phải tính đến mọi credential còn có khả năng được chấp nhận và các cache liên quan. Không xóa lịch sử cần cho bảo mật chỉ vì tác vụ quản trị đã báo hoàn tất.

### 9.5. Các đường chấp nhận ngoài API chính

Cần kiểm tra cả tải file bằng URL có credential, cổng đối tác, tác vụ nền, stream và các điểm thực thi khác trong phạm vi.

Một URL ký có thời hạn hoặc credential cấp cho tác vụ có thể có cơ chế thu hồi khác access token chính. Nếu nó nằm trong cam kết “đăng xuất chặn mọi truy cập”, cần thiết kế ràng buộc tương ứng hoặc ghi rõ phạm vi khác biệt.

Không coi việc API chính từ chối là bằng chứng mọi quyền truy cập dẫn xuất đã chấm dứt.

## 10. Bộ yêu cầu minh họa và tiêu chí chấp nhận

Giả sử một nền tảng quản trị chọn access token tối đa 10 phút, ngừng cấp mới trong tối đa 5 giây và chặn request mới của phạm vi bị thu hồi trong tối đa 60 giây. Các ngưỡng này chỉ là giả định cho bài học; hệ thống thực tế phải lựa chọn và phê duyệt theo rủi ro.

| ID | Yêu cầu | Tiêu chí chấp nhận |
| --- | --- | --- |
| RV-01 | Mỗi loại sự kiện có phạm vi thu hồi rõ: token, phiên, grant, client hoặc tài khoản | Từ lệnh quản trị xác định được đối tượng bị ảnh hưởng và những đối tượng không thuộc phạm vi |
| RV-02 | Actor chỉ được thu hồi đối tượng thuộc quyền đã cấp | Người dùng không thu hồi được phiên của người khác; client không tác động grant ngoài quyền |
| RV-03 | Sau khi ghi bền lệnh thu hồi, ngừng cấp và refresh credential thuộc phạm vi trong tối đa 5 giây | Gọi liên tục các đường cấp mới và refresh sau lệnh; mọi điểm cấp từ chối sau giới hạn |
| RV-04 | Mọi API trong phạm vi từ chối request mới bằng token đã thu hồi trong tối đa 60 giây, kể cả token còn hạn | Dùng token cấp ngay trước thu hồi trên mọi node và cache; không có điểm chấp nhận sau giới hạn |
| RV-05 | Thu hồi phiên bao gồm các thế hệ refresh cùng access token thuộc phiên theo chính sách | Token hiện tại và credential cũ còn hạn đều không tạo quyền ngoài cam kết |
| RV-06 | Cache không kéo dài quyết định hợp lệ qua hạn token hoặc thời hạn thu hồi | Làm nóng cache trước lệnh rồi kiểm tra lại tại ranh giới; TTL không tạo ngoại lệ ngầm |
| RV-07 | Retry cùng lệnh không đảo ngược thu hồi và không tạo quan hệ cấp quyền mới | Gửi lặp lệnh, timeout rồi retry; trạng thái cuối vẫn đúng và có thể liên kết audit |
| RV-08 | Sự kiện đến sai thứ tự hoặc cập nhật muộn không làm token bị thu hồi hoạt động trở lại | Áp dụng trạng thái cũ sau trạng thái mới; điểm thực thi vẫn từ chối |
| RV-09 | API quản trị từ chối khi không xác minh được trạng thái thu hồi bắt buộc | Gián đoạn dịch vụ trạng thái hoặc đường cập nhật không dẫn đến bỏ qua kiểm tra |
| RV-10 | Kết nối liên tục của phiên bị thu hồi ngừng cấp dữ liệu được bảo vệ trong ngưỡng riêng đã chốt | Kiểm tra stream đã mở trước lệnh, không chỉ bắt tay kết nối mới |
| RV-11 | Phục hồi trạng thái không làm token đã thu hồi hoặc hết hạn được chấp nhận lại | Khôi phục snapshot trước lệnh và kiểm tra token cũ ở điểm nhận |
| RV-12 | Audit liên kết được lệnh, phạm vi và bằng chứng hiệu lực mà không chứa credential nguyên giá trị | Điều tra được actor, mốc thời gian và điểm thực thi qua mã tham chiếu an toàn |

RV-10 cần một ngưỡng cụ thể trước khi dùng làm đặc tả cuối cùng, chẳng hạn 10 giây cho loại stream đang xét. Không để “ngưỡng riêng đã chốt” tồn tại mà chưa có con số, owner và phép đo.

RV-03 và RV-04 có hai phạm vi thời gian khác nhau. Trong cửa sổ chưa ngừng cấp hoàn toàn, nếu vẫn phát hành credential theo thiết kế được chấp thuận, các credential đó vẫn phải thuộc phạm vi bị chặn theo RV-04. Không để token được cấp trong cuộc đua thoát khỏi liên kết phiên hoặc grant.

### Ví dụ đặc tả một yêu cầu thu hồi

~~~yaml
requirement_id: RV-04
trigger: Lệnh thu hồi phiên được ghi bền và xác nhận
subject: Mọi token truy cập liên kết với phiên bị thu hồi
scope:
  - Mọi API trong miền ứng dụng được bảo vệ
  - Mọi node và cache quyết định chấp nhận token
maximum_effect_delay_seconds: 60
required_behavior: Từ chối request mới dùng token thuộc phiên bị thu hồi
includes:
  - Token đã phát hành và còn hạn
  - Credential được cấp trong cửa sổ xử lý lệnh nhưng vẫn thuộc phiên
verification:
  - Ghi nhận mốc xác nhận lệnh thu hồi
  - Gửi request liên tục bằng các token thử nghiệm tới từng điểm thực thi
  - Đối chiếu thời điểm từ chối và lý do trong audit
separate_requirements:
  - Ngừng cấp và refresh credential
  - Chấm dứt stream hoặc kết nối đang hoạt động
owner: Nhóm identity và các nhóm API trong phạm vi
~~~

Đây là ví dụ nội dung yêu cầu, không phải cấu hình triển khai. Cần bổ sung nguồn thời gian, độ chính xác phép đo và inventory điểm thực thi của hệ thống cụ thể.

## 11. Một dòng thời gian minh họa

~~~text
09:59:50  Access token A được cấp, thời hạn danh nghĩa 10 phút
10:00:00  Lệnh thu hồi phiên S được ghi bền và xác nhận
10:00:05  Chậm nhất từ mốc này, mọi đường cấp mới và refresh của S phải từ chối
10:01:00  Chậm nhất từ mốc này, mọi API trong phạm vi phải từ chối A
10:09:50  Thời điểm A tự hết hạn theo thời hạn danh nghĩa
~~~

Nếu A vẫn dùng được lúc 10:02 chỉ vì chưa đạt 10:09:50, thiết kế không đáp ứng giới hạn thu hồi 60 giây của ví dụ.

Đồng thời, kiểm tra chỉ A chưa đủ nếu phiên S còn token khác. Cần dùng tập credential đại diện cho các thế hệ và đường cấp có liên quan, đồng thời có bằng chứng cấu trúc rằng chúng đều bị ràng buộc với phạm vi S.

Sau một lần xác thực mới được phép, hệ thống có thể tạo phiên S2 độc lập. Việc S2 hoạt động không phải lý do để A của S được chấp nhận trở lại.

## 12. Thiết kế kiểm chứng theo rủi ro

### 12.1. Kiểm tra phân quyền của lệnh

Thử actor hợp lệ, actor chưa xác thực, actor thiếu quyền, client khác và phạm vi tenant khác. Đối chiếu cả kết quả thao tác lẫn audit.

Cần bảo đảm phản hồi không làm lộ dữ liệu ngoài quyền, nhưng cũng không vì phản hồi tổng quát mà bỏ qua việc kiểm tra hiệu lực thật sự.

### 12.2. Kiểm tra token còn hạn

Nếu chỉ dùng token đã hết hạn để kiểm tra revoke, ca từ chối không chứng minh cơ chế thu hồi hoạt động. Phải dùng token vẫn còn hạn và hợp lệ về các điều kiện khác.

Ca chuẩn gồm:

1. Gọi tài nguyên thành công bằng token thử nghiệm trước thu hồi.
2. Ghi nhận lệnh và mốc T0.
3. Tiếp tục gọi qua từng điểm thực thi.
4. Xác định thời điểm từ chối vì trạng thái thu hồi.
5. Đối chiếu với giới hạn đã cam kết.

Bằng chứng nguyên nhân hữu ích để tránh nhầm token hết hạn, lỗi mạng hoặc thiếu quyền với việc revoke đã thực thi.

### 12.3. Kiểm tra cache và sự kiện

Bao gồm cache nóng, cache lạnh, node mới khởi động, sự kiện lặp, đến chậm và sai thứ tự. Với gián đoạn cập nhật, xác định hệ thống thực hiện chính sách lỗi nào.

Một node nhận đúng sự kiện không chứng minh cả pool đã cập nhật. Cần inventory điểm thực thi và cách quan sát phạm vi kiểm chứng.

### 12.4. Kiểm tra chuỗi credential và cuộc đua

Kiểm tra nhiều access token từ cùng phiên, refresh token hiện tại, token trước rotation và request refresh đồng thời với lệnh thu hồi.

Nếu hệ thống cấp token mới trong lúc lệnh đang xử lý, token đó không được thoát khỏi phạm vi thu hồi đã định. Sự liên kết với phiên hoặc grant cần tồn tại ở các đường cấp liên quan.

Với phát hiện sử dụng lại refresh token, cần có cả tình huống tấn công theo mô hình và tình huống retry hợp lệ để kiểm chứng chính sách phản ứng, không chỉ ca “dùng lại thì lỗi”.

### 12.5. Kiểm tra sự cố khóa ký và phục hồi

Đây là phạm vi khác thu hồi một token. Cần kiểm tra các consumer ngừng tin cậy khóa bị ảnh hưởng theo cam kết, bao gồm cache khóa và đường cập nhật.

Trong môi trường kiểm chứng, không dùng khóa production hoặc tạo credential thực sự có quyền ngoài phạm vi. Bằng chứng nên dùng dữ liệu thử nghiệm và cơ chế được tách biệt.

Quy trình phục hồi cần kiểm tra token cũ, trạng thái thu hồi và các quyết định dùng cache. Khôi phục thành công dịch vụ chưa chứng minh không có quyền bị hồi sinh.

## 13. Audit và vận hành

Các trường hữu ích của sự kiện thu hồi gồm:

- Mã tác vụ và mã tham chiếu đối tượng.
- Actor phát lệnh, loại sự kiện và lý do.
- Phạm vi: token, phiên, grant, client hoặc chủ thể.
- Thời điểm nhận, ghi bền và xác nhận.
- Phiên bản trạng thái hoặc chính sách.
- Trạng thái phân phối và điểm thực thi nếu có.
- Lỗi, retry và kết quả đối soát.

Không ghi nguyên access token hoặc refresh token vào sự kiện. Công cụ hỗ trợ nên cung cấp thông tin liên kết đủ dùng mà không biến người đọc audit thành người có credential.

Cần phân biệt hai nhóm quan sát:

- Hệ thống điều khiển: lệnh đã được nhận, lưu và phân phối.
- Hệ thống thực thi: request thực sự bị chặn đúng phạm vi và thời hạn.

Chỉ đếm số lệnh revoke thành công không cho biết tỷ lệ điểm thực thi còn dùng trạng thái cũ.

Khi phát hiện độ trễ vượt ngưỡng, cần biết ảnh hưởng đến API, node, client và thời gian nào để xử lý. Không tự động báo “mọi token đã hết hiệu lực” chỉ vì tác vụ nền không còn trong hàng đợi.

## 14. Những cách viết yêu cầu dễ sai

| Cách viết | Vấn đề | Cách làm rõ |
| --- | --- | --- |
| JWT không thể revoke | Bỏ qua cơ chế kiểm tra trạng thái hoặc miền tin cậy | Nêu điều kiện của xác minh offline và cơ chế được chọn |
| Logout chỉ cần xóa token | Bỏ sót bản sao credential | Nêu thời hạn server từ chối token đã cấp |
| Revoke refresh là logout toàn bộ | Access token và phiên khác có thể còn hoạt động | Nêu phạm vi liên kết và hành vi của từng loại credential |
| Token sống ngắn nên revoke ngay | Nhầm hết hạn với chặn trước hạn | Nêu cửa sổ còn dùng được và ngưỡng chấp thuận |
| Đã cập nhật database nên hoàn tất | Điểm thực thi có cache hoặc bản sao cũ | Đo hiệu lực tại nơi quyết định truy cập |
| Đổi khóa ký là revoke một người dùng | Phạm vi có thể rộng hơn nhiều | Tách thu hồi token với xử lý tin cậy khóa |
| API trả thành công nên token đã bị vô hiệu hóa | Phản hồi có thể cố ý không tiết lộ trạng thái | Kiểm chứng bằng kết quả truy cập và bằng chứng quản trị phù hợp |
| Revoke phải hủy mọi giao dịch | Không xác định điểm quyết định và khả năng hoàn tác | Viết yêu cầu riêng cho request đang chạy, commit và stream |

Một thiết kế thu hồi hoàn chỉnh nối được sự kiện rủi ro với phạm vi credential, quyền phát lệnh, cách phân phối trạng thái và bằng chứng từ chối tại tài nguyên. Khi những yếu tố đó được đặc tả rõ, “token đã bị thu hồi” mới là một kết quả có thể kiểm chứng thay vì chỉ là nhãn trong hệ thống quản trị.

# Data correction

## 1. Sửa dữ liệu là một yêu cầu về tính chính xác và quyền riêng tư

Data correction là việc tiếp nhận, đánh giá và thực hiện điều chỉnh dữ liệu sai hoặc thiếu, đồng thời bảo đảm thay đổi được áp dụng đúng đối tượng, đúng phạm vi và không bị các bản sao cũ ghi đè trở lại.

Trong thiết kế yêu cầu bảo mật, mục tiêu không chỉ là “cho người dùng sửa hồ sơ”. Một thay đổi có thể tác động đến thông tin liên hệ, kết quả xử lý nghiệp vụ, dữ liệu đã chia sẻ, chỉ mục tìm kiếm và các quyết định đang dựa vào dữ liệu cũ.

Một yêu cầu sửa dữ liệu đầy đủ cần trả lời:

- Ai có thể yêu cầu sửa, ai được quyết định và ai được ghi thay đổi?
- Thông tin nào thực sự sai, thiếu hoặc chỉ không còn phù hợp ở thời điểm hiện tại?
- Nguồn nào có thẩm quyền đối với trường dữ liệu đó?
- Có được ghi đè, hay cần bổ sung một bản đính chính có ngữ cảnh?
- Những hệ thống nào đang sử dụng giá trị cũ?
- Khi nào có thể báo hoàn tất và dùng bằng chứng nào để chứng minh?
- Làm sao ngăn việc chỉnh sửa trở thành đường chiếm tài khoản, sửa dữ liệu người khác hoặc che dấu lịch sử?

Ví dụ, khách hàng báo địa chỉ liên hệ trong hồ sơ hiện tại sai. Dịch vụ hồ sơ sửa thành công nhưng hệ thống gửi thông báo vẫn dùng bản cache cũ. Kết quả tại cơ sở dữ liệu nguồn đúng, nhưng mục tiêu tránh tiếp tục gửi thông tin đến địa chỉ sai chưa đạt.

Bài học này tập trung chuyển nhu cầu điều chỉnh dữ liệu thành yêu cầu bảo mật cụ thể, có mốc đo, phạm vi thực thi và tiêu chí kiểm chứng.

## 2. Xác định điều cần sửa trước khi chọn thao tác cập nhật

### 2.1. Phân biệt dữ liệu hiện tại, dữ liệu lịch sử và nhận định

| Tình huống | Điều cần xác định | Hướng xử lý có thể phù hợp |
| --- | --- | --- |
| Gõ sai thông tin trong hồ sơ hiện tại | Giá trị đúng và nguồn xác minh | Sửa thuộc tính hiện tại theo quyền và bằng chứng cần thiết |
| Một thuộc tính thay đổi theo thời gian | Khi nào giá trị mới có hiệu lực | Cập nhật hiện tại, giữ lịch sử có mục đích và hạn lưu phù hợp |
| Bản ghi lịch sử phản ánh sự kiện đã xảy ra | Sai ở sự kiện hay sai ở cách diễn giải | Đính chính hoặc bổ sung có liên kết, không tạo lịch sử giả |
| Dữ liệu chưa đủ cho mục đích xử lý | Phần nào cần bổ sung | Thu thập phần tối thiểu cần thiết và ghi nguồn |
| Chủ thể phản đối một nhận định | Đó là sự kiện, ý kiến hay suy luận | Xem xét căn cứ, ghi nhận tranh chấp và áp dụng quy trình thích hợp |
| Dữ liệu của hai người bị gắn nhầm | Quan hệ định danh và ảnh hưởng liên quan | Xử lý liên kết sai theo quy trình có kiểm soát, không chỉ đổi tên hiển thị |

Tài liệu của ICO về quyền đính chính phân biệt sai sót dữ kiện với hồ sơ phản ánh một sai sót đã xảy ra và với ý kiến có ngữ cảnh. Điểm thiết kế cần rút ra là xác định bản ghi đang khẳng định điều gì trước khi chọn ghi đè hay bổ sung. Phạm vi nghĩa vụ cụ thể vẫn phụ thuộc quy định áp dụng và đánh giá của nhóm có thẩm quyền. [ICO, Right to rectification](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/individual-rights/right-to-rectification).

### 2.2. Không phải mọi cập nhật đều là sửa một sai sót

Một người chuyển nhà có thể cần cập nhật địa chỉ hiện tại. Địa chỉ được dùng trong một lần giao hàng đã hoàn tất có thể vẫn là bản ghi đúng về giao dịch lúc đó.

Ngược lại, nếu địa chỉ trong giao dịch đã bị nhập sai ngay từ đầu, chỉ nói “đây là lịch sử nên không sửa” không giải quyết được sai sót. Có thể cần bản đính chính, đánh dấu giá trị cũ không còn được dùng như dữ kiện đúng và xử lý hậu quả theo nghiệp vụ.

Yêu cầu phải chỉ ra:

- Ý nghĩa của trường dữ liệu.
- Khoảng thời gian mà giá trị mô tả.
- Cách trình bày giá trị hiện hành và bản đính chính.
- Quyền truy cập lịch sử.
- Những xử lý nào được phép tiếp tục dùng giá trị cũ.

### 2.3. Append-only không phải lý do bỏ qua đính chính

Một kho sự kiện không cho sửa bản ghi cũ vẫn có thể nhận sự kiện đính chính và xây lại các góc nhìn hiện hành.

Tuy nhiên, chỉ thêm sự kiện mà màn hình, báo cáo và hệ thống quyết định vẫn đọc giá trị sai là chưa đủ. Tiêu chí chấp nhận phải bao phủ kết quả sử dụng dữ liệu.

Không cần xóa mọi dấu vết để sửa một lỗi, cũng không cần giữ mọi bản sai mãi mãi. Quyền truy cập và retention của lịch sử là yêu cầu riêng cần phối hợp.

## 3. Từ mô hình đe dọa đến hành vi cần đặc tả

### 3.1. Tài sản và actor

Các tài sản liên quan gồm:

- Hồ sơ hiện hành và các quan hệ định danh.
- Giá trị đề xuất, bằng chứng và tài liệu đính kèm.
- Trạng thái xác minh, quyết định và lý do.
- Phiên bản dữ liệu, sự kiện đính chính và trạng thái truyền tới các nơi nhận.
- Lịch sử có kiểm soát, audit và dữ liệu phục hồi.
- Thông tin liên hệ dùng để xác thực, khôi phục hoặc nhận thông báo.

Actor có thể là chủ thể dữ liệu, người đại diện được xác minh theo chính sách, nhân viên xử lý, chủ sở hữu nguồn dữ liệu và các workload cập nhật bản sao.

Quyền gửi yêu cầu không đồng nghĩa quyền sửa trực tiếp. Một người có thể hợp lệ khi phản ánh sai sót nhưng vẫn cần quy trình đánh giá trước khi ghi vào nguồn có thẩm quyền.

### 3.2. Bảng rủi ro minh họa

| Đe dọa hoặc sai sót | Tác động | Kết quả yêu cầu cần hướng tới |
| --- | --- | --- |
| Caller đổi subject_id hoặc tenant_id | Sửa dữ liệu của người khác | Ràng buộc đối tượng và tenant bằng ngữ cảnh có thẩm quyền |
| Form cho sửa cả verified, role hoặc owner | Tăng quyền hoặc vượt quy trình | Chỉ cho phép tập trường và chuyển trạng thái đã cấp quyền |
| Dùng địa chỉ liên hệ mới làm bằng chứng sở hữu tài khoản cũ | Chiếm tài khoản | Tách xác minh yêu cầu khỏi xác minh kênh mới |
| Request dựa trên phiên bản cũ ghi đè thay đổi mới | Mất cập nhật đúng | Kiểm soát đồng thời và phát hiện xung đột |
| Một lần import sau đính chính đưa giá trị cũ trở lại | Sai sót tái diễn | Quy tắc nguồn và phiên bản ngăn hồi sinh giá trị đã thay thế |
| Kho chính đã sửa nhưng cache và tìm kiếm chưa sửa | Tiếp tục dùng dữ liệu sai | Phạm vi lan truyền, độ trễ và hành vi khi chưa đồng bộ |
| Nhân viên lấy danh nghĩa đính chính để sửa audit | Mất bằng chứng | Tách quyền xử lý dữ liệu khỏi quyền quản lý audit |
| Giá trị cũ và mới bị ghi vào log rộng quyền | Tăng dữ liệu nhạy cảm bị lộ | Audit tối thiểu; lịch sử chi tiết có quyền và hạn lưu riêng |
| Restore snapshot cũ rồi mở dịch vụ ngay | Dữ liệu sai xuất hiện lại | Đối soát và áp dụng đính chính trước khi sử dụng |
| Sửa hồ sơ nhưng không xem xét kết quả dẫn xuất | Quyết định vẫn dựa trên đầu vào sai | Xác định những dữ liệu hoặc quyết định phải tái đánh giá |

Từ bảng này, một yêu cầu cần có trigger, owner, đối tượng, điểm thực thi và bằng chứng. Cụm “đã hỗ trợ quyền sửa dữ liệu” chưa thể dùng làm tiêu chí kiểm thử.

## 4. Xác định phạm vi và nguồn có thẩm quyền

### 4.1. Kiểm kê nơi dữ liệu tồn tại và được sử dụng

Không chỉ tìm bảng hồ sơ. Cần xác định cả:

- Replica, cache và chỉ mục tìm kiếm.
- Hệ thống liên hệ, gửi thông báo và thực hiện nghiệp vụ.
- Kho phân tích, tệp xuất, sự kiện và hàng đợi.
- Dữ liệu dẫn xuất, báo cáo hoặc kết quả suy luận liên quan.
- Bên nhận dữ liệu ngoài ranh giới kiểm soát trực tiếp.
- Backup và môi trường phục hồi.

Inventory nên ghi trường dữ liệu, ý nghĩa, nguồn chuẩn, owner, consumer, cách cập nhật, cách xác nhận và khả năng hạn chế sử dụng giá trị cũ.

Một hệ thống không biết dữ liệu đã đi đâu khó chứng minh việc đính chính có hiệu lực đến đâu.

### 4.2. Quyền quyết định có thể khác nhau theo trường

Tên hiển thị có thể cho tự sửa theo chính sách. Một trạng thái đã xác minh hoặc quan hệ sở hữu có thể cần kiểm tra bổ sung. Dữ liệu do nguồn khác cung cấp có thể cần làm việc với owner của nguồn đó.

Không gọi một hệ thống là nguồn chuẩn cho toàn bộ hồ sơ nếu từng trường thực sự do các bên khác nhau quyết định.

Nếu hai nguồn mâu thuẫn, cần có quy tắc giải quyết hoặc trạng thái chờ đánh giá. Không chọn giá trị đến sau chỉ vì nó có timestamp lớn hơn.

### 4.3. Giữ định danh ổn định và xử lý liên kết sai cẩn thận

Một thuộc tính có thể thay đổi không nên tự trở thành căn cứ duy nhất để gộp hoặc tách người.

Sửa địa chỉ email không có nghĩa chuyển toàn bộ giao dịch sang một tài khoản khác đang dùng email đó. Sửa tên cũng không phải bằng chứng hai hồ sơ thuộc cùng người.

Nếu lỗi thực tế nằm ở quan hệ định danh, cần đánh giá phạm vi liên quan, phân quyền và khả năng ảnh hưởng chéo. Việc sửa một trường hiển thị không giải quyết được một liên kết chủ thể bị sai.

## 5. Tiếp nhận và xác minh yêu cầu mà không tạo rủi ro mới

### 5.1. Thông tin tối thiểu cần tiếp nhận

Một yêu cầu nên xác định được:

- Đối tượng hoặc hồ sơ đang được đề cập.
- Trường dữ liệu bị cho là sai hoặc thiếu.
- Nội dung điều chỉnh mong muốn và lý do.
- Bằng chứng cần thiết nếu loại dữ liệu yêu cầu.
- Phạm vi ảnh hưởng mà người yêu cầu biết.
- Kênh phản hồi phù hợp và mã theo dõi.

Không bắt người yêu cầu cung cấp lại toàn bộ hồ sơ nhạy cảm nếu chỉ cần sửa một thuộc tính nhỏ. Biểu mẫu và tài liệu đính kèm cũng là một tập dữ liệu cần phân quyền, bảo vệ khi truyền và có thời hạn lưu giữ.

Các trường tự khai như subject_id, tenant_id hay acting_as chỉ là đầu vào. Bên phục vụ vẫn phải xác minh quan hệ với đối tượng được yêu cầu.

### 5.2. Xác minh danh tính phải tương xứng với rủi ro

Cần xác định mức bảo đảm cho từng loại sửa đổi. Một phiên đăng nhập có thể đủ cho thay đổi rủi ro thấp nhưng chưa đủ cho thay đổi ảnh hưởng quyền sở hữu hoặc khôi phục tài khoản.

Nếu yêu cầu chứng minh bổ sung, chỉ thu thập dữ liệu cần thiết cho việc xác minh đó. Không mặc định mọi lần sửa tên hiển thị đều phải tải giấy tờ định danh.

Ngược lại, không coi việc biết thông tin đang có trong hồ sơ là bằng chứng chắc chắn về quyền sở hữu. Dữ liệu đó có thể đã bị lộ.

Nếu người dùng không truy cập được kênh cũ vì chính thông tin đó sai, cần một đường xác minh thay thế có kiểm soát. Không tạo vòng lặp trong đó chỉ có dữ liệu đang bị khiếu nại mới có thể chứng minh yêu cầu hợp lệ.

### 5.3. Tách xác minh người yêu cầu khỏi xác minh giá trị mới

Khi đổi email hoặc số điện thoại, có hai câu hỏi khác nhau:

1. Actor có quyền yêu cầu thay đổi thuộc tính của tài khoản này không?
2. Actor có kiểm soát kênh mới hoặc giá trị mới có đáp ứng điều kiện xác minh không?

Xác nhận một mã gửi đến email mới chỉ trả lời một phần câu hỏi thứ hai. Nó không tự chứng minh quyền sửa tài khoản cũ.

Đường kích hoạt kênh mới, gửi thông báo, khôi phục tài khoản và vô hiệu hóa liên kết cũ cần được thiết kế cùng nhau. Không để một giá trị chưa xác minh lập tức trở thành kênh khôi phục có thẩm quyền.

### 5.4. Tách quyền từng bước

| Hành động | Kiểm soát cần đặc tả |
| --- | --- |
| Gửi yêu cầu | Danh tính hoặc kênh tiếp nhận; chống lạm dụng; không tiết lộ hồ sơ ngoài quyền |
| Xem trạng thái | Kiểm tra quan hệ với yêu cầu và tenant |
| Đọc bằng chứng | Quyền theo vụ việc; không công khai qua URL đoán được |
| Đánh giá dữ kiện | Owner hoặc vai trò phù hợp với loại trường |
| Áp dụng thay đổi | Tập trường được phép, điều kiện xác minh và phiên bản |
| Lan truyền tới consumer | Danh tính workload, phạm vi dữ liệu và kiểm tra phiên bản |
| Đóng hoặc từ chối yêu cầu | Lý do, quyền quyết định, thông báo và audit |

Với thay đổi có tác động lớn, có thể cần phân tách người đánh giá và người thực hiện theo chính sách rủi ro. Đây phải là yêu cầu rõ ràng của loại thay đổi đang xét, không phải một phê duyệt thủ công cho mọi cập nhật nhỏ.

## 6. Quy trình xử lý và ngữ nghĩa trạng thái

### 6.1. Một vòng đời yêu cầu minh họa

~~~text
Đã tiếp nhận
    -> đang xác minh quyền và đối tượng
    -> đang đánh giá thông tin
    -> được chấp thuận hoặc có quyết định khác
    -> đã áp dụng vào nguồn chuẩn
    -> đang lan truyền và kiểm chứng
    -> hoàn tất trong phạm vi đã xác nhận
~~~

Có thể có trạng thái cần bổ sung thông tin, đang tranh chấp, xử lý một phần, lỗi hoặc từ chối. Phải chỉ rõ ai được chuyển trạng thái và điều kiện chuyển.

Một request được tiếp nhận chưa phải một thay đổi được chấp thuận. Một thay đổi được ghi ở nguồn cũng chưa phải tất cả nơi nhận đã dùng dữ liệu đúng.

### 6.2. Mốc thời gian không được trộn lẫn

Các mốc hữu ích:

- T_received: yêu cầu được hệ thống tiếp nhận và ghi nhận.
- T_verified: quyền yêu cầu và đối tượng đã được xác minh theo chính sách.
- T_decided: quyết định đánh giá được ghi nhận.
- T_applied: thay đổi được ghi bền tại nguồn có thẩm quyền.
- T_effective_i: điểm sử dụng i đã áp dụng phiên bản đúng hoặc ngừng dùng giá trị cũ theo yêu cầu.
- T_completed: đủ điều kiện đóng yêu cầu trong phạm vi được công bố.

Một SLA nội bộ về lan truyền có thể đo từ T_applied. Nó không thay thế thời hạn xử lý toàn yêu cầu nếu nguồn yêu cầu khác quy định mốc sớm hơn.

Không reset T_received mỗi lần chuyển nhóm, yêu cầu bổ sung hay retry để che thời gian chờ. Cách tính thời hạn, điều kiện tạm dừng hoặc gia hạn phải được xác định bởi chính sách áp dụng.

### 6.3. Dữ liệu đang bị tranh chấp được dùng thế nào?

Trong thời gian đánh giá, có thể cần đánh dấu trạng thái chưa xác minh, hạn chế một số sử dụng hoặc tạm ngừng xử lý có ảnh hưởng cao.

Cần nêu chính xác trường nào, nghiệp vụ nào và khoảng thời gian nào bị tác động. Một nhãn disputed mà mọi consumer bỏ qua không tạo ra hạn chế thực tế.

Ngược lại, chặn toàn bộ tài khoản vì một lỗi nhỏ ở tên hiển thị có thể không tương xứng. Hành vi phải theo rủi ro và chính sách có thẩm quyền, không chỉ theo một cờ toàn cục.

### 6.4. Từ chối hoặc chưa thể xác minh

Không phải mọi giá trị đề xuất đều được tự động coi là đúng. Có thể cần thêm thông tin, đính chính bằng cách bổ sung ngữ cảnh hoặc từ chối theo quy trình áp dụng.

Kết quả cần có lý do đủ dùng, đường phản hồi hoặc xem xét tiếp theo nếu chính sách yêu cầu, và trạng thái của dữ liệu trong thời gian chờ. Không được dùng thông báo chung để che việc yêu cầu đã bị bỏ quên.

Phản hồi cho người yêu cầu không nên lộ dữ liệu của người khác hoặc chi tiết kiểm soát có thể bị lạm dụng.

## 7. Áp dụng thay đổi an toàn tại nguồn có thẩm quyền

### 7.1. Kiểm soát trường và quy tắc nghiệp vụ

API cần giới hạn tập trường được sửa. Không ánh xạ mọi thuộc tính từ request vào bản ghi nội bộ.

Những trường như tenant, owner, role, verified, nguồn dữ liệu và phiên bản chính sách cần có quy trình riêng nếu được phép thay đổi. Caller không được tự đặt trạng thái “đã xác minh” bằng một trường trong JSON.

Kiểm tra dữ liệu mới phải phù hợp ý nghĩa trường: kiểu dữ liệu, độ dài, định dạng cần thiết, ký tự được hỗ trợ và quan hệ với trường khác.

Chuẩn hóa không được tự làm mất ý nghĩa. Không loại bỏ dấu trong tên, cắt giá trị hoặc đổi mọi ký tự sang chữ thường chỉ để dễ so sánh nếu quy tắc nghiệp vụ chưa cho phép.

### 7.2. Chống mất cập nhật khi có đồng thời

Giả sử hai request cùng đọc phiên bản 12:

~~~text
A: sửa địa chỉ liên hệ, dựa trên phiên bản 12
B: sửa địa chỉ liên hệ, cũng dựa trên phiên bản 12

A được ghi thành phiên bản 13
B đến sau không được âm thầm ghi đè phiên bản 13
~~~

Có thể dùng kiểm tra phiên bản, compare-and-set hoặc giao dịch phù hợp. Với API HTTP, If-Match cùng entity tag phù hợp là một cơ chế điều kiện để tránh ghi đè dữ liệu đã thay đổi. Theo RFC 9110, If-Match dùng so sánh mạnh; điều kiện không đạt phải được xử lý theo ngữ nghĩa tiền điều kiện, thường là phản hồi 412 khi không xác định được thao tác đã thành công trước đó. [RFC 9110, mục 13.1.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1).

Ví dụ khái niệm:

~~~http
PATCH /profiles/profile-demo-001
If-Match: "profile-v12"
Content-Type: application/json

{
  "display_name": "Tên hiển thị mẫu B"
}
~~~

Entity tag phải được bên phục vụ tạo và kiểm tra theo thiết kế. Header If-Match: * chỉ kiểm tra sự tồn tại của representation hiện tại; nó không thay thế việc so sánh một phiên bản cụ thể để phát hiện cập nhật cũ.

Kiểm soát đồng thời không thay thế xác thực, phân quyền và xác minh yêu cầu.

### 7.3. Quyết định và ghi dữ liệu phải nhất quán

Một request đã được chấp thuận trên dữ liệu cũ có thể không còn phù hợp sau một thay đổi khác. Trước khi commit, cần xác nhận các điều kiện bắt buộc vẫn đúng theo mô hình nhất quán được chọn.

Cần liên kết được:

- Yêu cầu và quyết định đã chấp thuận.
- Đối tượng, tenant và tập trường.
- Phiên bản trước và sau.
- Actor hoặc workload thực hiện.
- Công việc cần lan truyền và audit tương ứng.

Không báo thành công nếu giá trị đã ghi nhưng mất hoàn toàn khả năng xác định sự kiện đính chính cần phát. Kiến trúc phải xử lý cuộc đua giữa ghi dữ liệu và ghi nhận công việc lan truyền, chẳng hạn bằng cơ chế giao dịch phù hợp.

### 7.4. Retry phải giữ đúng ý nghĩa thao tác

Sau timeout, caller có thể không biết thay đổi đã được ghi hay chưa. Retry cùng thao tác cần có cách tra kết quả hoặc được xử lý idempotent theo hợp đồng.

Một khóa chống lặp không được cho phép caller khác hoặc tenant khác lấy kết quả của yêu cầu không thuộc quyền. Cũng không được tái sử dụng cùng khóa với nội dung khác rồi âm thầm coi là thao tác cũ.

Không dùng rollback tự động để đưa dữ liệu sai trở lại chỉ vì phản hồi mạng bị mất.

## 8. Lan truyền đính chính và ngăn dữ liệu cũ quay lại

### 8.1. Phạm vi phải dựa trên nơi sử dụng thực tế

Một luồng khái niệm:

~~~mermaid
flowchart LR
    A["Yêu cầu và quyền đã xác minh"] --> B["Đánh giá và quyết định"]
    B --> C["Nguồn dữ liệu có thẩm quyền"]
    C --> D["Công việc hoặc sự kiện đính chính"]
    D --> E["Cache, replica và tìm kiếm"]
    D --> F["Hệ thống thực hiện nghiệp vụ"]
    D --> G["Kho phân tích hoặc bên nhận liên quan"]
    E --> H["Đối soát phiên bản và hiệu lực"]
    F --> H
    G --> H
~~~

Mỗi mũi tên cần có danh tính được phép, bảo vệ dữ liệu trên đường truyền, ngữ nghĩa retry và cách phát hiện lỗi.

Không coi một thông báo trên event bus là bằng chứng consumer đã cập nhật. Cũng không coi một lần cập nhật consumer là đủ nếu đường đọc của nó vẫn giữ cache cũ.

### 8.2. Định danh, phiên bản và thứ tự sự kiện

Sự kiện cần đủ thông tin để bên nhận xác định đúng đối tượng, tenant, loại thay đổi và phiên bản. Không dùng thông tin liên hệ đang thay đổi làm khóa định danh duy nhất.

Phải xác định cách xử lý sự kiện lặp, đến chậm, sai thứ tự và thiếu khoảng giữa. Phiên bản phải có ngữ nghĩa trong phạm vi đối tượng hoặc trường dữ liệu, không chỉ là timestamp do caller cung cấp.

Một chi tiết quan trọng: nếu sự kiện chỉ chứa phần thay đổi, nhận phiên bản 14 trước phiên bản 13 không có nghĩa đã nhận mọi thay đổi của phiên bản 13.

~~~text
v13: sửa tên hiển thị
v14: sửa địa chỉ liên hệ

Consumer chỉ nhận patch v14:
    không được kết luận tên hiển thị cũng đã được cập nhật
~~~

Thiết kế có thể yêu cầu xử lý đúng thứ tự, tải lại snapshot hiện hành, hoặc quản lý phiên bản theo trường phù hợp. Chỉ bỏ mọi event có số nhỏ hơn số lớn nhất đã thấy có thể làm mất một phần đính chính.

Nếu sự kiện mang snapshot đầy đủ, phải biết snapshot bao phủ những trường và phiên bản nào. Không để sự kiện cũ ghi đè kết quả mới đã được xác nhận.

### 8.3. Sự kiện không cần mang toàn bộ dữ liệu nhạy cảm

Có thể phát mã tham chiếu và phiên bản, rồi để consumer có quyền tải phần cần thiết từ nguồn được bảo vệ.

Nếu payload phải có giá trị mới, cần giới hạn trường, bên nhận và retention của hàng đợi. Một sự kiện chứa cả toàn bộ hồ sơ cũ lẫn mới có thể mở rộng phạm vi lộ dữ liệu không cần thiết.

Bên nhận phải xác thực nguồn sự kiện hoặc đường lấy dữ liệu. Không cho một workload không có thẩm quyền tự phát sự kiện để sửa hồ sơ ở nơi khác.

### 8.4. Nguồn nhập định kỳ có thể làm đính chính mất hiệu lực

Một bản import cũ có thể chứa dữ liệu sai đã được sửa tại nguồn hiện hành.

Cần quy định quan hệ thẩm quyền:

- Đính chính tại đâu phải được phản hồi về nguồn upstream nào?
- Có cờ hoặc phiên bản đánh dấu dữ liệu cũ đã bị thay thế không?
- Khi nhận giá trị mâu thuẫn, hệ thống từ chối, đối soát hay chuyển đánh giá?
- Ai chịu trách nhiệm giải quyết nguồn thường xuyên tái đưa dữ liệu sai vào?

Không áp dụng last-write-wins cho mọi đầu vào nếu “ghi sau” chỉ có nghĩa một tệp cũ vừa được tải lên.

### 8.5. Cache và đường sử dụng có ảnh hưởng cao

Sau khi dữ liệu nguồn đã sửa, một tác vụ nhạy cảm có thể vẫn đọc cache cũ. Yêu cầu cần xác định giới hạn độ trễ và hành vi khi không xác minh được phiên bản hiện hành.

Các lựa chọn có thể gồm vô hiệu hóa cache, đọc nguồn có thẩm quyền cho hành động cụ thể, hoặc ngừng sử dụng trường đang tranh chấp khi quá hạn đồng bộ.

Cần phân biệt:

- Consumer đã nhận event.
- Kho của consumer đã ghi phiên bản mới.
- Mọi đường đọc liên quan không còn dùng giá trị cũ như dữ liệu hiện hành.

Một trong ba mốc không tự chứng minh hai mốc còn lại.

## 9. Đối tượng lịch sử, dữ liệu dẫn xuất và bên nhận khác

### 9.1. Hồ sơ lịch sử phải có ngữ nghĩa rõ ràng

Nếu giữ lịch sử, cần hiển thị hoặc xử lý sao cho người dùng được phép hiểu đâu là giá trị trước đây, đâu là lỗi đã được đính chính và đâu là giá trị có hiệu lực.

Không chỉ thêm một ghi chú ở nơi ít người đọc trong khi trường sai vẫn được dùng để tìm kiếm hoặc ra quyết định.

Quy trình sửa dữ liệu cũng không được dùng để sửa audit thành một lịch sử khác. Nếu audit có lỗi, có thể cần sự kiện bổ sung có liên kết và quyền xử lý riêng.

### 9.2. Dữ liệu dẫn xuất cần được đánh giá theo quan hệ phụ thuộc

Một báo cáo, phân nhóm hoặc kết quả tự động có thể đã được tính từ dữ liệu sai.

Yêu cầu cần phân biệt:

- Dữ liệu dẫn xuất có thể tính lại.
- Quyết định đã phát hành cần được đánh giá lại theo quy trình nghiệp vụ.
- Nội dung được giữ làm lịch sử có thể cần đính chính ngữ cảnh.
- Tập dữ liệu hoặc mô hình không thể được xử lý bằng một lệnh cập nhật bản ghi thông thường.

Sửa đầu vào không tự chứng minh báo cáo, kết luận hoặc tác động đã hoàn tất trước đó được sửa. Nếu có yêu cầu tái xử lý, phải có owner, phạm vi và bằng chứng riêng.

Không cam kết rằng sửa một bản ghi sẽ tự loại mọi ảnh hưởng của nó khỏi mô hình đã huấn luyện. Cần xác định các sản phẩm dữ liệu thực sự nằm trong phạm vi và phương pháp xử lý khả thi cho chúng.

### 9.3. Bên nhận bên ngoài cần trạng thái riêng

Nếu dữ liệu đã được chuyển tới bên khác, cần inventory bên nhận và quy trình thực hiện nghĩa vụ liên quan theo chính sách áp dụng.

Trạng thái nên phân biệt:

- Đã xác định bên nhận liên quan.
- Đã gửi thông báo hoặc yêu cầu đính chính.
- Bên nhận đã tiếp nhận.
- Bên nhận đã xác nhận áp dụng trong phạm vi cụ thể.
- Chưa xác minh, lỗi hoặc có ngoại lệ được ghi nhận.

Không báo “đã sửa ở mọi nơi” chỉ vì email thông báo đã được gửi. Nếu không kiểm soát trực tiếp hệ thống bên nhận, phải công bố giới hạn bằng chứng và cách chuyển xử lý.

Thông báo cũng phải hạn chế dữ liệu. Chỉ gửi phần cần thiết cho đúng bên có quyền, không phát tán lại toàn bộ hồ sơ sai để mô tả một thay đổi nhỏ.

## 10. Backup, restore và replay không được hồi sinh sai sót

### 10.1. Không cần nhầm backup với dữ liệu hiện hành

Một bản backup cũ có thể giữ giá trị trước đính chính. Cần quy định thời hạn tồn tại của bản sao, quyền tiếp cận và điều kiện sử dụng khi phục hồi.

Nếu không thể sửa từng bản ghi trong backup, kiến trúc phải có cách áp dụng trạng thái có thẩm quyền trước khi dữ liệu được đưa lại vào nghiệp vụ. Không để giới hạn kỹ thuật này trở thành lý do cho việc tiếp tục phục vụ dữ liệu sai.

### 10.2. Phục hồi vào vùng hạn chế rồi đối soát

Một quy trình minh họa:

1. Phục hồi bản sao vào vùng chưa mở cho nghiệp vụ.
2. Xác định mốc dữ liệu, phiên bản và những khoảng sự kiện còn thiếu.
3. Nạp các đính chính và trạng thái vòng đời phát sinh sau mốc đó.
4. Áp dụng theo đúng ngữ nghĩa thứ tự và thẩm quyền.
5. Tái tạo cache, chỉ mục và góc nhìn từ dữ liệu đã đối soát.
6. Xác minh các trường bị tác động và điều kiện sử dụng.
7. Chỉ mở lại phạm vi đã đủ bằng chứng.

Nếu không có nguồn đính chính đủ tin cậy, phải giữ trạng thái chưa xác minh và xử lý theo chính sách lỗi. Không mặc định bản snapshot là dữ liệu đúng nhất chỉ vì khôi phục thành công.

### 10.3. Phối hợp với xóa và retention

Một bản ghi đã bị xóa theo quyết định có hiệu lực không được tái tạo chỉ vì còn một sự kiện đính chính cũ chờ replay.

Cần định nghĩa thứ tự và ưu tiên giữa cập nhật, đính chính, hạn chế sử dụng và xóa. Khi thay phiên bản đối tượng hoặc tái sử dụng định danh, event cũ không được tác động nhầm đối tượng mới.

Danh mục đính chính hoặc dữ liệu chống hồi sinh phải giữ tối thiểu, được bảo vệ và có retention đủ cho phạm vi phục hồi được cam kết. Không giữ mọi giá trị cũ vĩnh viễn để thuận tiện replay.

Sửa một thuộc tính cũng không tự gia hạn retention của toàn hồ sơ. Nếu có quy tắc thay đổi mốc, phải được xác định riêng và có căn cứ.

## 11. Audit, quyền truy cập và bằng chứng

### 11.1. Audit quá trình khác với lưu mọi giá trị

Những thông tin hữu ích có thể gồm:

- Mã yêu cầu, mã đối tượng nội bộ và tenant trong phạm vi được phép.
- Actor, phương thức xác minh và vai trò xử lý.
- Tập trường đã đánh giá, phiên bản trước và sau.
- Quyết định, mã lý do và chính sách có hiệu lực.
- Thời điểm tiếp nhận, quyết định, commit và xác nhận từng nơi.
- Lỗi, retry, phần chưa xác minh và owner tiếp theo.

Không ghi toàn bộ giá trị cũ, giá trị mới hoặc tài liệu xác minh vào log phổ thông.

Nếu cần giữ lịch sử chi tiết để giải trình, đó là một kho có mục đích riêng, với quyền truy cập, mã hóa và retention phù hợp. Audit ứng dụng có thể chỉ cần tham chiếu đến kho đó.

### 11.2. Băm không tự làm bằng chứng hết nhạy cảm

Một fingerprint của giá trị thuộc miền dễ đoán có thể vẫn hỗ trợ đối chiếu hoặc dò ứng viên. Không mặc định băm số điện thoại hoặc một mã có cấu trúc sẽ loại mọi rủi ro nhận diện.

Định danh theo dõi và metadata của yêu cầu cũng có thể liên kết với một người. Chúng vẫn cần kiểm soát phạm vi và thời gian lưu.

### 11.3. Xác định thế nào là đủ bằng chứng hoàn tất

Bộ bằng chứng nên nối được:

~~~text
Yêu cầu hợp lệ
    -> quyết định có thẩm quyền
    -> thay đổi tại nguồn và phiên bản
    -> phạm vi cần lan truyền
    -> xác nhận tại các nơi sử dụng
    -> trạng thái và thông báo cuối cùng
~~~

Bằng chứng “hàng dữ liệu đã update” chỉ bao phủ một phần chuỗi.

Nếu một consumer bị gián đoạn, trạng thái phải phản ánh phần còn thiếu. Có thể đạt mục tiêu ngừng dùng giá trị sai bằng cách chặn tạm, nhưng chưa đủ để khẳng định consumer đã phục vụ giá trị đúng.

## 12. Bộ yêu cầu đo được cho một tình huống minh họa

### 12.1. Phạm vi và giả định

Giả sử nền tảng cho phép khách hàng yêu cầu sửa tên hiển thị và địa chỉ nhận thư trong hồ sơ hiện hành. Địa chỉ này được một dịch vụ dùng để gửi tài liệu; thông tin trong giao dịch đã hoàn tất được đánh giá riêng theo ý nghĩa lịch sử.

Phạm vi trực tiếp gồm dịch vụ hồ sơ, cache, tìm kiếm và dịch vụ gửi tài liệu. Các bên nhận khác được quản lý theo inventory riêng.

Các ngưỡng bên dưới là giả định của bài học:

- Thay đổi đã được xác minh và chấp thuận phải được ghi tại nguồn trong tối đa 5 phút từ T_decided.
- Trong tối đa 60 giây sau T_applied, quyết định gửi tài liệu mới không được tiếp tục dùng địa chỉ cũ như thông tin hiện hành.
- Trong tối đa 15 phút sau T_applied, các consumer trực tiếp phải áp dụng phiên bản mới theo hợp đồng.
- Nếu không đáp ứng, yêu cầu vẫn thể hiện lỗi hoặc xử lý một phần; không đổi nhãn hoàn tất để che vi phạm.

Những ngưỡng này không thay thời hạn xử lý yêu cầu quyền riêng tư do nguồn quy định áp dụng xác định. Cần theo dõi cả thời gian từ T_received và thời gian của từng giai đoạn.

### 12.2. Ma trận yêu cầu và tiêu chí chấp nhận

| ID | Yêu cầu bảo mật | Tiêu chí chấp nhận |
| --- | --- | --- |
| DC-01 | Actor chỉ được tác động hồ sơ, tenant và tập trường thuộc quyền hoặc quy trình đại diện đã được xác minh | Đổi subject, tenant hoặc thêm trường đặc quyền không sửa được dữ liệu; không lộ giá trị ngoài quyền |
| DC-02 | Xác minh quyền yêu cầu, tính hợp lệ và thẩm quyền nguồn trước khi ghi | Giá trị đề xuất chưa được chấp thuận không xuất hiện như dữ liệu đã xác minh |
| DC-03 | Mỗi yêu cầu có mã theo dõi, trạng thái và các mốc xử lý riêng | Phân biệt được tiếp nhận, quyết định, commit, lan truyền và hoàn tất; retry không reset thời gian nhận |
| DC-04 | Thay đổi đã chấp thuận trong phạm vi ví dụ được commit bền vững trong tối đa 5 phút từ T_decided | Đối chiếu quyết định, phiên bản và thời điểm nguồn ghi; quá hạn được ghi nhận là vi phạm |
| DC-05 | Cập nhật đồng thời không ghi đè âm thầm một thay đổi đã được ghi | Request dựa trên phiên bản cũ bị xử lý xung đột hoặc hợp nhất theo quy tắc rõ ràng; không mất trường đã sửa |
| DC-06 | Sau tối đa 60 giây từ T_applied, quyết định gửi tài liệu mới dùng dữ liệu đúng hoặc bị chặn nếu không xác minh được | Cache nóng, node chậm và tác vụ đã khởi tạo trước đó không tạo quyết định gửi mới bằng giá trị cũ sau giới hạn |
| DC-07 | Consumer trực tiếp áp dụng phiên bản mới trong tối đa 15 phút từ T_applied | Có bằng chứng tại kho và đường đọc liên quan; consumer chỉ bị chặn vì lỗi vẫn được ghi là chưa hoàn tất cập nhật |
| DC-08 | Sự kiện lặp, thiếu hoặc sai thứ tự không làm mất trường hoặc hồi sinh giá trị cũ | Kiểm tra patch khác trường, snapshot và replay; phiên bản không đủ phải được đối soát |
| DC-09 | Import từ nguồn cũ không tự ghi đè kết quả đã đính chính | Nhập lại dữ liệu cũ dẫn tới từ chối, đối soát hoặc quyết định có thẩm quyền, không tự phục hồi giá trị sai |
| DC-10 | Mỗi thay đổi có audit liên kết quyết định và phiên bản; log phổ thông không chứa toàn bộ dữ liệu cũ, mới hoặc bằng chứng | Truy vết được actor và kết quả mà không tạo bản sao hồ sơ nhạy cảm trong log rộng quyền |
| DC-11 | Restore và replay phải áp dụng đính chính và trạng thái vòng đời trước khi mở dữ liệu | Snapshot trước thay đổi không làm giá trị sai trở thành hiện hành; event cũ không tái tạo hồ sơ đã xóa |
| DC-12 | Trạng thái bên nhận và thông báo hoàn tất phải phản ánh đúng bằng chứng | Đã gửi thông báo không được trình bày là bên nhận đã sửa; phần chưa xác minh có owner và đường xử lý |

DC-06 đo hiệu lực ngăn sử dụng sai. DC-07 đo việc consumer thực sự nhận và phục vụ dữ liệu mới. Chặn đọc có thể giúp đáp ứng DC-06 trong một số lỗi, nhưng không tự đáp ứng DC-07.

### 12.3. Mốc đo cho một hành động có ảnh hưởng cao

~~~text
T_applied:
    nguồn hồ sơ đã ghi bền giá trị mới và phiên bản tương ứng

T_decision:
    dịch vụ gửi tài liệu quyết định địa chỉ sẽ được sử dụng

Nếu T_decision >= T_applied + 60 giây:
    dùng phiên bản đáp ứng yêu cầu hiện hành
    hoặc không thực hiện quyết định gửi khi không thể xác minh
~~~

Cần xác định nguồn đồng hồ, sai lệch được chấp thuận và độ chính xác của phép đo. Ngưỡng 60 giây phải bao gồm cache, hàng đợi, lịch cập nhật và đường retry liên quan.

Các tài liệu đã gửi trước điểm áp dụng không tự được thu hồi bởi việc sửa hồ sơ. Nếu cần xử lý tác động đã xảy ra, phải có yêu cầu nghiệp vụ riêng với owner và bằng chứng.

### 12.4. Ví dụ đặc tả có truy vết

~~~yaml
requirement_id: DC-06
risk_id: TH-CORRECTION-04
risk: Tài liệu tiếp tục được gửi đến địa chỉ sai sau khi hồ sơ đã được đính chính
data_scope: Địa chỉ nhận thư hiện hành của hồ sơ trong phạm vi
trigger: Giá trị mới được nguồn có thẩm quyền ghi bền
start_marker: T_applied
maximum_effect_delay_seconds: 60
enforcement_scope:
  - Mọi node dịch vụ quyết định gửi tài liệu
  - Cache và bản sao dữ liệu được các node này sử dụng
  - Tác vụ trong hàng đợi chưa thực hiện quyết định gửi
required_behavior:
  - Dùng dữ liệu đáp ứng phiên bản đính chính có hiệu lực
  - Không dùng giá trị cũ như thông tin hiện hành sau giới hạn
failure_behavior: Không quyết định gửi nếu không thể xác minh điều kiện bắt buộc
separate_requirements:
  - Cập nhật và xác nhận từng consumer
  - Xử lý tài liệu đã gửi
  - Nghĩa vụ thông báo bên nhận ngoài phạm vi trực tiếp
verification:
  - Làm nóng cache bằng phiên bản cũ trước khi sửa
  - Kiểm tra quyết định trên từng node sau mốc giới hạn
  - Gián đoạn cập nhật không dẫn tới bỏ qua kiểm tra
evidence:
  - Phiên bản nguồn và thời điểm commit
  - Phiên bản được dùng tại điểm quyết định
  - Kết quả, mã lý do và audit đã giảm dữ liệu nhạy cảm
owner: Nhóm hồ sơ, nhóm gửi tài liệu và nhóm nền tảng
~~~

Đây là nội dung đặc tả minh họa, không phải cấu hình triển khai. Khi áp dụng cần thay phạm vi khái niệm bằng inventory cụ thể và liên kết với kiến trúc, chính sách, kiểm thử tương ứng.

## 13. Thiết kế kiểm chứng theo rủi ro

### 13.1. Dữ liệu thử và kết quả trước thay đổi

Dùng dữ liệu tổng hợp và tenant thử phù hợp. Tạo hồ sơ với phiên bản và giá trị ban đầu xác định được.

Trước khi gửi yêu cầu, cần xác nhận đường đọc và consumer đang dùng giá trị ban đầu. Nếu một API đã không trả dữ liệu ngay từ đầu vì thiếu quyền, việc nó tiếp tục từ chối sau sửa không chứng minh đính chính đã hoạt động.

Một ca nền gồm:

1. Đọc giá trị ban đầu qua nguồn và các consumer trong phạm vi.
2. Gửi yêu cầu bằng actor có quyền.
3. Xác minh, quyết định và ghi nhận mốc xử lý.
4. Kiểm tra giá trị và phiên bản sau commit.
5. Quan sát consumer và đường sử dụng có ảnh hưởng cao.
6. Đối chiếu trạng thái cuối với bằng chứng từng nơi.

### 13.2. Phân quyền và xác minh

Thử chủ thể hợp lệ, người khác, tenant khác, người đại diện chưa đủ điều kiện và nhân viên không được phân công.

Cần thử cả endpoint trạng thái, tải bằng chứng và đường quản trị; không chỉ API sửa hồ sơ.

Thêm các trường ngoài allowlist như verified hoặc role vào request. Kết quả không được làm chúng thay đổi chỉ vì request còn có một trường hợp lệ.

Với thuộc tính liên quan đăng nhập hoặc khôi phục, kiểm tra riêng trường hợp actor chỉ kiểm soát kênh mới. Việc xác minh kênh mới không được tự cấp quyền chiếm hồ sơ cũ.

### 13.3. Đồng thời và idempotency

Thử hai thay đổi cùng trường và khác trường dựa trên cùng phiên bản.

Cần chứng minh không mất dữ liệu và kết quả hợp nhất, nếu có, tuân theo quy tắc. Không kết luận mọi cập nhật khác trường đều được tự hợp nhất; các trường có thể có quan hệ nghiệp vụ.

Mô phỏng timeout sau commit rồi retry cùng yêu cầu. Kết quả phải liên kết đúng thao tác ban đầu hoặc xử lý xung đột theo hợp đồng, không tạo hai quyết định mâu thuẫn.

### 13.4. Lan truyền và sự kiện sai thứ tự

Bao gồm:

- Consumer đã làm nóng cache trước thay đổi.
- Một event được gửi lặp.
- Hai patch khác trường đến sai thứ tự.
- Consumer bỏ lỡ một phiên bản.
- Snapshot cũ đến sau phiên bản mới.
- Import định kỳ chứa giá trị trước đính chính.
- Consumer khởi động lại hoặc xử lý bù sau gián đoạn.

Đối chiếu cả dữ liệu lưu và kết quả sử dụng. Một consumer ghi đúng bảng nhưng màn hình hoặc job vẫn đọc cache cũ chưa đáp ứng toàn bộ mục tiêu.

### 13.5. Lỗi, khôi phục và replay

Thử lỗi giữa commit nguồn và phát sự kiện, giữa consumer ghi dữ liệu và xác nhận, và trong lúc đối soát.

Trạng thái phải thể hiện phần chưa hoàn tất. Retry không được đổi mã đối tượng hoặc làm mất quan hệ với quyết định ban đầu.

Phục hồi snapshot trước đính chính vào môi trường kiểm chứng. Xác nhận dữ liệu chỉ được mở sau khi áp dụng các trạng thái mới có thẩm quyền.

Kết hợp với ca đã xóa hồ sơ hoặc đã đổi thế hệ định danh để chứng minh sự kiện đính chính cũ không tác động nhầm.

### 13.6. Dữ liệu lịch sử và hệ quả dẫn xuất

Tạo một bản ghi lịch sử có ý nghĩa cụ thể rồi kiểm tra cách hiển thị sau đính chính. Người đọc được phép phải phân biệt được lịch sử, lỗi và giá trị hiện hành.

Nếu phạm vi yêu cầu có báo cáo hoặc quyết định dẫn xuất, cần xác nhận tác vụ tái đánh giá thực sự chạy và kết quả được gắn với phiên bản đầu vào đúng.

Không dùng một lần update hồ sơ làm bằng chứng thay cho toàn bộ chuỗi tác động này.

### 13.7. Bằng chứng không được tạo thêm rò rỉ

Kiểm tra nội dung log, trace, thông báo và báo cáo thử nghiệm để tránh lưu toàn bộ dữ liệu cũ, mới hoặc tài liệu xác minh ngoài phạm vi cần thiết.

Dùng mã ca thử, phiên bản và kết quả đã lọc dữ liệu để đối soát. Quyền đọc bằng chứng kiểm thử và audit cũng cần phù hợp với độ nhạy cảm.

## 14. Vận hành và tiêu chí báo hoàn tất

Các số liệu nên phản ánh kết quả thay vì chỉ đếm số request:

| Số liệu | Ý nghĩa |
| --- | --- |
| Thời gian từ tiếp nhận đến quyết định | Phát hiện yêu cầu bị chờ hoặc chuyển nhóm nhiều lần |
| Thời gian từ quyết định đến commit | Kiểm tra khả năng thực thi tại nguồn |
| Độ trễ tại từng consumer | Nhận diện cache, replica hoặc hệ thống chậm |
| Số quyết định còn dùng giá trị cũ sau ngưỡng | Đo vi phạm hiệu lực tại nơi sử dụng |
| Số yêu cầu xử lý một phần và tuổi lớn nhất | Tránh trạng thái chờ vô hạn |
| Số xung đột, retry và sự kiện thiếu phiên bản | Phát hiện vấn đề nhất quán |
| Số lần import hoặc restore làm sai lệch | Theo dõi nguy cơ hồi sinh dữ liệu cũ |
| Bên nhận chưa xác nhận và phần chưa kiểm chứng | Thể hiện giới hạn phạm vi hoàn tất |

Nếu cam kết là giới hạn tối đa, p95 hoặc số trung bình không đủ chứng minh mọi yêu cầu đều đáp ứng. Cần theo dõi trường hợp vi phạm và phần không quan sát được.

Một thông báo hoàn tất nên phù hợp với phạm vi đã xác nhận: trường nào đã được sửa, nơi nào đã áp dụng, nơi nào có cách xử lý khác, và phần nào còn ngoài khả năng xác minh trực tiếp.

Không nói “đã cập nhật mọi nơi” khi inventory chưa bao phủ mọi bên nhận. Cũng không giữ yêu cầu mãi ở trạng thái không rõ nếu thực tế đã có quyết định từ chối hoặc ngoại lệ cần giải thích theo quy trình.

## 15. Những cách viết yêu cầu dễ sai

| Cách viết chưa đủ | Rủi ro | Cách làm rõ |
| --- | --- | --- |
| Người dùng được sửa mọi thông tin của mình | Có trường đặc quyền hoặc tác động bên khác | Xác định tập trường, mức xác minh và quy trình theo rủi ro |
| Biết email mới thì được đổi email tài khoản | Chiếm tài khoản | Tách quyền sửa tài khoản khỏi chứng minh kiểm soát kênh mới |
| Đã xác thực nên không cần kiểm tra subject | Sửa dữ liệu người khác | Kiểm tra đối tượng, tenant và quan hệ ủy quyền |
| PATCH thành công là hoàn tất đính chính | Bản sao và consumer còn sai | Tách commit, lan truyền, hiệu lực và trạng thái cuối |
| Bỏ event phiên bản cũ là đủ chống ghi đè | Có thể mất patch khác trường | Chốt ngữ nghĩa snapshot, patch, thứ tự và đối soát khoảng thiếu |
| Cập nhật mới nhất luôn đúng | Import cũ có thể đến muộn | Dùng thẩm quyền nguồn và phiên bản có ý nghĩa |
| Lịch sử bất biến thì không được đính chính | Dữ liệu sai tiếp tục bị dùng | Bổ sung có liên kết và sửa kết quả sử dụng hiện hành |
| Lưu cả trước và sau vào log để dễ kiểm tra | Tạo kho dữ liệu nhạy cảm phụ | Audit tối thiểu; lịch sử chi tiết có quyền và retention riêng |
| Sửa hồ sơ là sửa mọi quyết định đã phát sinh | Bỏ sót hệ quả dẫn xuất | Xác định tác vụ tái đánh giá và owner riêng |
| Restore thành công thì dữ liệu dùng được | Hồi sinh sai sót cũ | Áp dụng đính chính và trạng thái vòng đời trước khi mở |
| Gửi thông báo cho đối tác là đối tác đã sửa | Báo vượt bằng chứng | Theo dõi tiếp nhận, áp dụng và phần chưa xác minh |

Một yêu cầu sửa dữ liệu có thể kiểm chứng phải nối được quyền yêu cầu, căn cứ xác định giá trị đúng, thay đổi có kiểm soát, phạm vi lan truyền và bằng chứng hiệu lực. Khi những mắt xích này được đặc tả rõ, hệ thống mới có thể chứng minh rằng dữ liệu sai không còn tiếp tục được sử dụng như thông tin hiện hành trong phạm vi đã cam kết.

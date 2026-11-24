# Privacy request handling: xử lý yêu cầu quyền riêng tư khi khôi phục tài khoản

## 1. Yêu cầu quyền riêng tư có thể xuất hiện giữa một sự cố truy cập

Một người dùng mất mật khẩu, điện thoại hoặc passkey có thể đồng thời yêu cầu xem dữ liệu, sửa thông tin liên hệ hoặc xóa tài khoản. Hệ thống cần tiếp nhận các yêu cầu này mà không biến chúng thành đường vòng để lấy dữ liệu hay chiếm quyền truy cập.

**Privacy request handling** là quy trình nhận diện, xác minh, đánh giá, thực hiện và phản hồi một yêu cầu liên quan đến dữ liệu cá nhân. Trong khôi phục tài khoản, quy trình này phải giải quyết hai mục tiêu cùng lúc:

- Người dùng hợp lệ có đường thực hiện yêu cầu kể cả khi chưa đăng nhập được.
- Người không được phép không thể dùng yêu cầu xem, sửa hoặc xóa dữ liệu để gây hại cho chủ tài khoản.

Ví dụ, Mai mất điện thoại có ứng dụng MFA. Mai gửi từ một email mới: “Tôi không đăng nhập được, hãy gửi toàn bộ dữ liệu tài khoản và đổi email khôi phục sang địa chỉ này”. Đây là nhiều yêu cầu có tác động khác nhau. Việc tiếp nhận thư không đủ để phê duyệt tất cả.

Cũng cần phân biệt người yêu cầu thực hiện quyền với kẻ tấn công giả mạo. Hệ thống chưa biết bên nào đang liên hệ thì nên quản lý trạng thái chưa xác minh, thay vì mặc định mọi yêu cầu đều hợp lệ hoặc đều gian lận.

## 2. Phân loại hành động trước khi cấp quyền

Một nội dung tự do có thể chứa cả yêu cầu hỗ trợ truy cập và yêu cầu liên quan đến dữ liệu. Nhân viên hoặc bộ phân loại cần tách hành động để áp dụng đúng phạm vi.

| Nội dung yêu cầu | Công việc cần phân loại | Rủi ro nếu xử lý sai |
| --- | --- | --- |
| “Cho tôi bản sao dữ liệu” | Truy cập hoặc xuất dữ liệu cá nhân | Gửi dữ liệu cho người giả mạo |
| “Số điện thoại này không còn đúng” | Xem xét sửa dữ liệu và tác động lên kênh khôi phục | Chuyển quyền nhận mã sang số của kẻ tấn công |
| “Xóa tài khoản và dữ liệu của tôi” | Đánh giá phạm vi xóa và quyết định lưu giữ | Xóa dữ liệu của người khác hoặc báo xóa quá mức thực tế |
| “Tôi không muốn nhận email quảng cáo” | Quản lý tùy chọn liên lạc theo mục đích | Nhầm với yêu cầu xóa mọi thông báo bảo mật |
| “Tôi mất MFA, hãy mở lại tài khoản” | Khôi phục khả năng xác thực | Bỏ qua điều kiện phục hồi phương thức xác thực |
| “Tôi đại diện cho chủ tài khoản” | Xác minh người yêu cầu và thẩm quyền đại diện | Cấp quyền cho bên không được ủy quyền |

Các loại trên không mặc nhiên có cùng căn cứ xử lý, thời hạn hay điều kiện. Hệ thống cần một hồ sơ chính sách phù hợp với quyền áp dụng, khu vực và loại dữ liệu, thay vì dùng một nút “privacy approved” cho mọi hành động.

Trong thiết kế, có thể biểu diễn mỗi hành động bằng một mục riêng như ACCESS_DATA, RECTIFY_CONTACT, ERASE_DATA hoặc RECOVER_AUTHENTICATOR. Một hồ sơ yêu cầu có thể chứa nhiều mục, mỗi mục có quyết định và tiến độ riêng.

Yêu cầu sửa thông tin chính xác không nên tự trở thành quyền đăng ký phương thức xác thực mới. Nếu một trường vừa là thông tin liên hệ vừa là điểm nhận bí mật khôi phục, cần đánh giá cả hai tác động đó.

## 3. Tách tiếp nhận, nhận diện, xác minh và cho phép thực hiện

Bốn bước này trả lời những câu hỏi khác nhau:

1. **Tiếp nhận:** hệ thống đã ghi nhận người nào đó đang yêu cầu điều gì?
2. **Nhận diện dữ liệu:** dữ liệu nào có thể liên quan đến người được nêu trong yêu cầu?
3. **Xác minh:** có đủ cơ sở tin rằng người liên hệ là người đó hoặc đại diện hợp lệ không?
4. **Cho phép thực hiện:** hành động cụ thể nào được thực hiện, trên dữ liệu nào và bằng cách nào?

Biết một địa chỉ email từng gắn với tài khoản có thể hỗ trợ tìm dữ liệu. Điều đó chưa chứng minh người đang sử dụng địa chỉ hiện tại có quyền nhận bản sao dữ liệu lịch sử.

Tương tự, có đủ cơ sở xử lý một yêu cầu truy cập dữ liệu không tự cấp phiên đăng nhập đầy đủ. Quyền tải một gói dữ liệu không phải quyền gỡ MFA, đổi mật khẩu hoặc đăng ký passkey.

Hướng dẫn của EDPB về quyền truy cập trong bối cảnh GDPR phân biệt nhận diện dữ liệu với xác thực người yêu cầu và nhấn mạnh tính tương xứng khi cần thêm thông tin xác minh. Đây là cơ sở tham khảo cho cách tách các bước, đồng thời tránh thu thập thông tin thừa. [EDPB Guidelines 01/2022, mục 3.2–3.3](https://www.edpb.europa.eu/system/files/documents/2023-04/edpb_guidelines_202201_data_subject_rights_access_v2_en.pdf)

Một bản ghi trạng thái có thể dùng các trường độc lập:

~~~text
PrivacyRequest
  requestId
  receivedAt
  requestItems[]
  requesterIdentityState
  subjectMappingState
  representativeAuthorityState
  applicablePolicyProfile
  assignedOwner
  deadlineTracking
  deliveryPlan
  executionState
~~~

Không dùng một trường verified=true để thay cho tất cả những chiều trên.

## 4. Tiếp nhận khi người dùng không đăng nhập được

Cổng tự phục vụ sau đăng nhập là một đường thuận tiện, nhưng người mất phương thức xác thực cần đường thay thế. Ví dụ, hệ thống có thể có biểu mẫu liên hệ bảo mật hoặc một quy trình hỗ trợ được giao cho nhóm chuyên trách.

Trong hướng dẫn về quyền truy cập tại Anh, ICO nêu việc cung cấp thông tin cần có phương thức thay thế nếu người yêu cầu không thể hoặc không muốn dùng nền tảng trực tuyến an toàn. Khi áp dụng vào kiến trúc khôi phục, điều này gợi ý không đặt việc đăng nhập lại thành đường duy nhất để bắt đầu xử lý yêu cầu. [ICO, A guide to subject access — cung cấp thông tin](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/subject-access-requests/a-guide-to-subject-access/)

Ở bước tiếp nhận chưa xác minh, chỉ cần dữ liệu tối thiểu để hiểu yêu cầu và thiết lập liên lạc:

- Nội dung người dùng muốn thực hiện.
- Một định danh hoặc tham chiếu giúp tìm hồ sơ.
- Kênh liên lạc có thể sử dụng trong quá trình xử lý.
- Thông tin về việc có đang yêu cầu thay mặt người khác hay không.

Không mặc định yêu cầu tải giấy tờ tùy thân, ảnh khuôn mặt, toàn bộ sao kê hoặc lịch sử email. Dữ liệu xác minh cần được lựa chọn sau khi đánh giá điều gì thực sự còn thiếu.

Phản hồi ban đầu có thể là:

> Yêu cầu đã được tiếp nhận. Nhóm xử lý sẽ hướng dẫn các bước cần thiết trước khi cung cấp dữ liệu hoặc thực hiện thay đổi.

Thông báo này không cần xác nhận tài khoản tồn tại, liệt kê email dự phòng hoặc cho biết người dùng có bao nhiêu phương thức MFA.

requestId cần khó đoán, nhưng không nên là điều kiện duy nhất để xem nội dung hồ sơ. Quyền xem trạng thái chi tiết và tài liệu phải được kiểm tra riêng. Một mã hồ sơ xuất hiện trong email chuyển tiếp không được tự mở quyền tải toàn bộ dữ liệu.

## 5. Xác minh tương xứng với dữ liệu và hành động

Mức kiểm tra cần phản ánh hậu quả nếu xác minh sai, đồng thời tận dụng bằng chứng đã có để giảm gánh nặng cho người dùng.

Có thể xem xét:

- Phiên đã được xác thực phù hợp với tác vụ, nếu người dùng còn sử dụng được.
- Phương thức xác thực khác đã đăng ký, như khóa bảo mật còn giữ.
- Bằng chứng lịch sử phù hợp với mô hình dịch vụ và khó bị một người ngoài thu thập.
- Quy trình xác minh thay thế do nhóm có thẩm quyền thực hiện.
- Bằng chứng về quyền đại diện, khi yêu cầu được gửi thay người khác.

Không dùng các thông tin công khai như ngày sinh hoặc địa chỉ trên mạng làm bí mật đáng tin. Không coi việc cung cấp một email mới rồi nhận OTP ở đó là bằng chứng sở hữu tài khoản cũ.

Nếu hộp thư cũ có dấu hiệu bị xâm nhập, gửi xác nhận vào chính hộp thư đó có thể không giải quyết được vấn đề. Nếu không còn khả năng sử dụng kênh cũ, hệ thống cần xem xét phương án thay thế, không yêu cầu lặp vô hạn cùng một bước không thể hoàn thành.

Trong phạm vi hướng dẫn quyền truy cập tại Anh, ICO nhấn mạnh việc yêu cầu thông tin xác minh phải hợp lý, tương xứng và chỉ yêu cầu giấy tờ chính thức khi cần thiết. Không nên biến tải giấy tờ thành mặc định cho mọi người yêu cầu. [ICO, A guide to subject access — Can we ask for ID?](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/subject-access-requests/a-guide-to-subject-access/#can-we-ask-for-id)

Nếu cần thu thập tài liệu bổ sung, thiết kế nên xác định rõ:

1. Thuộc tính cần xác minh và lý do cần thuộc tính đó.
2. Các trường người dùng có thể che trước khi gửi.
3. Vị trí tải lên, người được truy cập và thời hạn lưu.
4. Kết quả được ghi nhận sau khi xem xét.
5. Cách loại bỏ bản sao không còn cần thiết theo quyết định lưu giữ.

Không gửi giấy tờ qua ticket công khai hoặc sao chép tài liệu sang nhiều nhóm chat nội bộ. Không dùng dữ liệu thu thập cho xác minh yêu cầu để tự mở rộng hồ sơ tiếp thị hay các mục đích không liên quan.

## 6. Theo dõi thời gian và trạng thái mà không tự đặt lại tiến độ

Một quy trình kỹ thuật có thể dùng chuỗi trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> TRIAGED
    TRIAGED --> VERIFICATION_NEEDED
    VERIFICATION_NEEDED --> IDENTITY_CONFIRMED
    TRIAGED --> IDENTITY_CONFIRMED
    IDENTITY_CONFIRMED --> SCOPE_REVIEW
    SCOPE_REVIEW --> EXECUTION_READY
    SCOPE_REVIEW --> DECISION_RESPONSE
    EXECUTION_READY --> EXECUTING
    EXECUTING --> RESPONSE_READY
    EXECUTING --> EXECUTION_ISSUE
    EXECUTION_ISSUE --> EXECUTING
    RESPONSE_READY --> DELIVERED
    DECISION_RESPONSE --> DELIVERED
    DELIVERED --> CLOSED
~~~

Đây là trạng thái nghiệp vụ minh họa, không phải cách tự xác định mọi mốc thời hạn pháp lý.

receivedAt cần được giữ nguyên khi đổi nhóm phụ trách, tách mục yêu cầu hoặc gửi lại hướng dẫn xác minh. Bộ theo dõi thời hạn phải dựa trên hồ sơ chính sách được người có thẩm quyền xác định, có sự kiện và lý do cho từng thay đổi mốc thời gian.

Không mặc định mọi lần chuyển sang VERIFICATION_NEEDED đều dừng toàn bộ đồng hồ. Không đặt một quy tắc chung “30 ngày kể từ lần người dùng trả lời gần nhất” cho mọi loại yêu cầu và khu vực.

Yêu cầu bổ sung thông tin cần được đưa ra sớm, giải thích rõ và tránh lặp lại dữ liệu đã đủ. Nếu người dùng phản hồi không giải quyết được điểm còn thiếu, nhóm xử lý cần chỉ ra điều gì cần làm rõ thay vì lặng lẽ đặt hồ sơ về đầu hàng đợi.

Một lỗi hệ thống hoặc tác vụ nền chậm phải được ghi nhận là vấn đề thực thi. Không đổi thành “đã phản hồi” chỉ vì email thông báo tiến độ đã được gửi.

## 7. Tìm và chuẩn bị dữ liệu đúng chủ thể

Sau khi đủ điều kiện xác minh, hệ thống cần ánh xạ yêu cầu tới dữ liệu đúng người. Một người có thể có nhiều định danh cũ, trong khi một địa chỉ email có thể được tái cấp cho người khác theo thời gian.

Không tìm chỉ bằng chuỗi email hiện tại rồi gộp mọi kết quả. Cần xét accountId, lịch sử ràng buộc, tenant, thời gian và quan hệ với các hệ thống liên quan.

Trong module khôi phục, dữ liệu liên quan có thể nằm ở:

- Hồ sơ liên hệ và lịch sử thay đổi phương thức khôi phục.
- Lịch sử yêu cầu đặt lại mật khẩu hoặc phục hồi MFA.
- Ticket hỗ trợ và thông tin xác minh đã được tiếp nhận.
- Sự kiện đăng nhập, session hoặc quyết định rủi ro liên quan đến người yêu cầu.
- Hệ thống gửi thông báo, kho tài liệu và các dịch vụ xử lý liên quan.

Không mặc định một bảng hồ sơ người dùng đại diện cho toàn bộ dữ liệu. Cũng không đưa mọi bản ghi cùng IP vào hồ sơ của một người, vì IP có thể dùng chung.

Gói dữ liệu cần được chuẩn bị để người nhận hiểu nội dung. Các mã trạng thái, mốc thời gian hoặc loại sự kiện cần có cách giải thích phù hợp. Việc cung cấp dữ liệu cần được xem xét cùng thông tin về xử lý thuộc phạm vi yêu cầu và chính sách áp dụng.

Đối với dữ liệu chứa thông tin của nhiều người hoặc thông tin cần bảo vệ, nhóm có thẩm quyền phải đánh giá cụ thể phần nào được cung cấp và cách trình bày. Không tự loại bỏ toàn bộ log chỉ vì nó nằm trong “hệ thống bảo mật”. Hướng dẫn EDPB về quyền truy cập đề cập cả dữ liệu nhật ký và việc cân nhắc quyền của người khác trong phạm vi phản hồi. [EDPB Guidelines 01/2022, phạm vi và giới hạn quyền truy cập](https://www.edpb.europa.eu/system/files/documents/2023-04/edpb_guidelines_202201_data_subject_rights_access_v2_en.pdf)

Gói phản hồi không nên trở thành nơi phát hành bí mật đang hoạt động như token khôi phục, khóa riêng hoặc mã dùng để chiếm quyền truy cập. Cần phân biệt dữ liệu mô tả một sự kiện với bí mật cho phép thực hiện hành động. Mọi quyết định che hoặc giữ lại phần dữ liệu cần có lý do và người chịu trách nhiệm.

Một manifest nội bộ có thể ghi phạm vi tìm kiếm và kết quả:

~~~text
DataScopeManifest
  requestId
  subjectReference
  scopeRevision
  systemsReviewed[]
  recordsIncluded[]
  transformationsApplied[]
  portionsRequiringDecision[]
  approvedBy
  preparedAt
~~~

Manifest cần được phân quyền vì bản thân nó cũng có thể mô tả dữ liệu nhạy cảm.

## 8. Sửa dữ liệu không đồng nghĩa bỏ qua bảo vệ tài khoản

Yêu cầu sửa email hoặc số điện thoại có thể tác động trực tiếp tới đường khôi phục. Vì vậy, nhóm xử lý phải hiểu trường đó đang được dùng cho mục đích nào trước khi thực hiện.

Ví dụ, số điện thoại sai có thể xuất hiện đồng thời trong hồ sơ liên hệ, hệ thống gửi thông báo và cơ chế phục hồi MFA. Sửa một bảng mà bỏ các bản sao khác có thể khiến thông báo vẫn gửi tới người cũ.

Một kế hoạch thay đổi có thể gồm:

1. Xác định chủ thể, trường dữ liệu và giá trị cần sửa.
2. Ghi nhận quyết định cho phép xử lý yêu cầu sửa.
3. Xác định tác động lên các phương thức xác thực và khôi phục.
4. Thực hiện thay đổi trong phạm vi đã được phê duyệt.
5. Xử lý grant, lựa chọn kênh hoặc tác vụ gửi đang tham chiếu phiên bản cũ.
6. Thông báo qua những đường phù hợp mà không tiết lộ thêm dữ liệu cho người không được phép.

Nếu việc sửa dữ liệu có thể tạo quyền nhận bí mật khôi phục, cần điều kiện kiểm soát cho tác động đó. Một nhân viên không nên dùng nút chỉnh hồ sơ để vô hiệu hóa toàn bộ chính sách phục hồi MFA.

Ngược lại, không nên tự động trả lời “hãy khôi phục đăng nhập trước” cho mọi yêu cầu sửa dữ liệu. Hệ thống cần đường quyết định thay thế sau khi đã xác minh phù hợp, với phạm vi hành động được ghi rõ.

Trong thiết kế grant, có thể tách quyền RECTIFY_PROFILE_CONTACT với BIND_RECOVERY_CHANNEL. Cách tách kỹ thuật phải phản ánh chính sách thực tế và không được dùng để bỏ quên những nơi vẫn lưu dữ liệu sai.

## 9. Xóa dữ liệu cần kế hoạch, không chỉ một câu lệnh

Một yêu cầu xóa cần được đánh giá về chủ thể, phạm vi, loại dữ liệu và quyết định lưu giữ áp dụng. Kết quả có thể khác nhau giữa hồ sơ tài khoản, bản sao chuyển phát, tài liệu xác minh và chứng cứ sự cố.

Không nên lập trình quy tắc “cứ có yêu cầu là xóa mọi log”. Cũng không nên giữ tất cả vô thời hạn chỉ vì nhãn “chống gian lận”. Nếu một phần dữ liệu cần tiếp tục được giữ theo quyết định hợp lệ, bản ghi quyết định cần có mục đích, phạm vi, người chịu trách nhiệm và mốc xem xét hoặc kết thúc.

Kế hoạch thực thi có thể phân loại:

| Nhóm dữ liệu | Câu hỏi cần giải quyết | Bằng chứng thực thi nên ghi |
| --- | --- | --- |
| Hồ sơ đang hoạt động | Xóa hoặc sửa trường nào, liên quan tới dịch vụ nào? | Kết quả theo phạm vi và phiên bản kế hoạch |
| Session và quyền khôi phục | Có quyền đang chờ có thể tái kích hoạt truy cập không? | Kết quả thu hồi theo phạm vi được phép |
| Gói dữ liệu đã chuẩn bị | Còn đường tải hoặc bản sao tạm nào không? | Trạng thái thu hồi quyền tải và xóa bản tạm |
| Tài liệu xác minh | Bản gốc và bản sao nằm ở đâu? | Kết quả xử lý theo chính sách lưu giữ |
| Bên xử lý liên quan | Cần yêu cầu xử lý nào và đã có xác nhận chưa? | Trạng thái yêu cầu và kết quả nhận được |
| Bản sao lưu | Có thể xử lý ngay hay cần cơ chế theo vòng đời backup? | Trạng thái thực tế và biện pháp khi khôi phục |
| Dữ liệu cần tiếp tục lưu | Phạm vi và lý do nào đã được phê duyệt? | Quyết định lưu giữ và quyền truy cập giới hạn |

Bản sao lưu cần có cách tránh làm dữ liệu đã xóa xuất hiện trở lại sau một lần phục hồi hệ thống. Một thiết kế có thể dùng danh sách yêu cầu xóa được bảo vệ và quy trình tái áp dụng khi phục hồi. Danh sách này cũng cần được giảm thiểu, phân quyền và quản lý vòng đời.

Không báo “đã xóa khỏi mọi nơi” khi chỉ xóa một bảng chính. Hệ thống nên phân biệt công việc đã hoàn tất, công việc còn chờ và phần dữ liệu tiếp tục được giữ theo quyết định áp dụng.

Nếu người dùng đồng thời yêu cầu bản sao rồi xóa, cần làm rõ thứ tự và phạm vi thực hiện. Không để tác vụ xóa tự chạy trước khi gói dữ liệu cần cung cấp được chuẩn bị hoặc trước khi giải quyết xung đột của hai mục yêu cầu.

## 10. Bàn giao kết quả tới đúng người

Một gói dữ liệu đã được chuẩn bị đúng vẫn có thể bị lộ ở bước gửi. Trong khôi phục tài khoản, kênh cũ có thể bị mất hoặc bị chiếm quyền, còn kênh mới chưa được ràng buộc với chủ tài khoản.

Cần tách hai khái niệm:

- **Kênh liên lạc về tiến độ:** dùng để trao đổi hướng dẫn không tiết lộ dữ liệu riêng khi chưa đủ điều kiện.
- **Kênh bàn giao dữ liệu:** được phê duyệt sau khi xác minh người nhận và xem xét mức nhạy cảm.

Một email mới có thể là kênh liên lạc hữu ích. Khả năng nhận thư tại địa chỉ đó chưa tự đủ để nhận toàn bộ bản sao dữ liệu hoặc trở thành email khôi phục mới.

Một thiết kế cổng bàn giao có thể dùng quyền tải riêng:

~~~text
PrivacyDeliveryGrant
  requestId
  requestItemId
  recipientReference
  artifactId
  artifactRevision
  allowedAction = DOWNLOAD_APPROVED_ARTIFACT
  expiresAt
  state
~~~

Quyền này không cấp VIEW_ALL_ACCOUNT_DATA, CHANGE_PASSWORD hoặc REMOVE_MFA. Mỗi lần truy cập cần kiểm tra grant, người nhận theo cơ chế bàn giao đã chọn, gói dữ liệu và trạng thái hiện tại.

Không coi một link khó đoán là câu trả lời duy nhất cho mọi mức nhạy cảm. Link có thể bị chuyển tiếp hoặc lộ qua hộp thư. Cơ chế bàn giao cần phù hợp với rủi ro, đồng thời có lựa chọn thay thế cho người không sử dụng được cổng trực tuyến.

Trước khi bàn giao, cần kiểm tra có báo cáo xâm nhập mới, yêu cầu thu hồi, thay đổi người đại diện hoặc điều chỉnh phạm vi làm gói dữ liệu cũ không còn phù hợp hay không. Khi thu hồi quyền tải, cũng cần xử lý các URL hoặc cơ chế truy cập đã phát hành theo khả năng thực tế của kiến trúc.

Nếu người nhận đã tải dữ liệu, thu hồi link không tự lấy lại bản sao đó. Hệ thống nên ghi nhận chính xác thời điểm và kết quả bàn giao thay vì tạo cảm giác có thể đảo ngược mọi tiết lộ.

## 11. Thực thi có giới hạn quyền và có thể tiếp tục sau lỗi

Nhóm hỗ trợ, nhóm quyền riêng tư và dịch vụ khôi phục có thể cùng tham gia nhưng cần trách nhiệm rõ ràng:

- Nhóm tiếp nhận nhận diện loại yêu cầu và hướng dẫn người dùng.
- Nhóm xác minh ghi nhận kết quả trong phạm vi được giao.
- Người có thẩm quyền xác định phạm vi xử lý và quyết định liên quan.
- Dịch vụ kỹ thuật thực hiện kế hoạch đã được cho phép.
- Cơ chế bàn giao kiểm tra người nhận và quyền truy cập kết quả.

Không cấp cho tài khoản hỗ trợ một quyền tổng hợp vừa xem giấy tờ, vừa xuất mọi dữ liệu, vừa gỡ MFA mà không có phạm vi hồ sơ.

Một lệnh thực thi có thể ràng buộc với mục yêu cầu và phiên bản kế hoạch:

~~~text
executeApprovedRequestItem(requestId, itemId, expectedRevision):
    request = loadRequestForAuthorizedOperator(requestId)
    item = request.findItem(itemId)

    require item.identityDecision is sufficient for this action
    require representative authority is sufficient when applicable
    require item.executionPlan.revision == expectedRevision
    require item.executionPlan is approved and current

    operationKey = deriveOperationKey(
        requestId,
        itemId,
        expectedRevision,
        item.action
    )

    if completedResultExists(operationKey):
        return recordedResult(operationKey)

    execute only the approved subject and data scope
    record per-system outcomes durably
    schedule retry for eligible incomplete work
    report actual completion and unresolved parts
~~~

Đây là mã giả về điều phối. Trong hệ thống phân tán, không thể chỉ dựa vào một phép kiểm tra “đã chạy chưa” ở đầu hàm để bảo đảm không chạy lặp khi có nhiều worker. Cần cơ chế idempotency hoặc điều phối phù hợp tại những nơi thực hiện thay đổi.

Định danh chủ thể và phạm vi dữ liệu phải lấy từ kế hoạch đã được duyệt, không lấy trực tiếp từ tham số tùy ý trong một yêu cầu HTTP của người dùng.

Khi tác vụ thất bại ở một dịch vụ, giữ kết quả các phần đã thực hiện và tiếp tục phần còn thiếu theo chính sách. Không thực thi lại mù quáng một thao tác phá hủy dữ liệu chỉ vì chưa nhận được phản hồi của lần đầu.

Nhật ký tối thiểu có thể ghi requestId, loại hành động, phạm vi tham chiếu, phiên bản quyết định, người hoặc dịch vụ thực hiện, thời gian và kết quả. Không sao chép toàn bộ giấy tờ, token hoặc gói dữ liệu vào log.

Quy trình xử lý yêu cầu cũng tạo dữ liệu mới. Ticket, ảnh xác minh, gói xuất, URL bàn giao và bản ghi quyết định cần vòng đời riêng. Đóng hồ sơ không có nghĩa mọi bản sao tạm đã được xử lý; kết quả dọn dẹp cần được theo dõi theo phạm vi đã xác định.

## 12. Tình huống thực hành

Mai mất quyền truy cập điện thoại và email cũ. Từ một email mới, Mai gửi ba yêu cầu:

1. Nhận bản sao dữ liệu cá nhân.
2. Xóa các tài liệu từng gửi để xác minh tài khoản.
3. Đổi email khôi phục và gỡ MFA để đăng nhập lại.

Nhóm hỗ trợ tìm thấy tên tài khoản tương ứng và một ticket cũ. Một nhân viên đề xuất gửi toàn bộ dữ liệu tới email mới, sau đó xóa log để “bảo vệ quyền riêng tư”.

Hãy phân tích:

- Việc tìm thấy tài khoản đã giải quyết bước nhận diện hay bước xác minh?
- Những hành động nào cần được tách thành mục yêu cầu riêng?
- Email mới có thể dùng cho việc liên lạc nào trước khi được phê duyệt làm kênh bàn giao?
- Tài liệu hoặc bằng chứng bổ sung nào thực sự cần thiết, và dữ liệu nào có thể tránh thu thập?
- Quyền nhận bản sao dữ liệu có cho phép đổi email khôi phục hoặc gỡ MFA không?
- Việc xóa tài liệu xác minh cần xét những bản sao và quyết định lưu giữ nào?
- Nếu một dịch vụ đã xóa thành công còn dịch vụ khác gặp lỗi, hệ thống phải phản hồi và tiếp tục thế nào?
- Bản ghi tối thiểu nào giúp chứng minh yêu cầu đã được xử lý mà không giữ lại toàn bộ dữ liệu nhạy cảm?
- Nếu email mới bị báo cáo xâm nhập ngay trước khi bàn giao, quyền tải đang chờ cần được đánh giá lại ra sao?

Một phương án phù hợp cần chỉ rõ người được xác minh, hành động được phép, dữ liệu thuộc phạm vi, cách bàn giao và kết quả thực tế. Xử lý yêu cầu quyền riêng tư thành công không tự đồng nghĩa tài khoản đã được khôi phục, và khôi phục đăng nhập thành công cũng không tự hoàn tất các yêu cầu về dữ liệu.

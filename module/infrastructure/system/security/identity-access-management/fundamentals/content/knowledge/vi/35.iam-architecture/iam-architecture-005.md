# Application plane: lớp ứng dụng thực thi truy cập trong kiến trúc IAM

## 1. Application plane nằm ở đâu?

Trong bài này, application plane là phần kiến trúc gồm các ứng dụng và dịch vụ sử dụng thông tin danh tính để phục vụ nghiệp vụ, đồng thời thực thi những giới hạn truy cập đối với tài nguyên của mình.

Nó có thể gồm giao diện web, ứng dụng di động, backend, API, dịch vụ xử lý nền và các điểm truy cập dữ liệu phục vụ nghiệp vụ. Không phải thành phần nào cũng có cùng trách nhiệm bảo mật: giao diện có thể điều chỉnh trải nghiệm, nhưng phía kiểm soát tài nguyên phải thực thi quyền.

Cách đặt tên và chia các plane có thể khác giữa các kiến trúc. Ở đây, plane là cách phân chia trách nhiệm logic, không phải yêu cầu phải triển khai thành một cụm máy hoặc một sản phẩm riêng.

Ví dụ, công ty An Bình dùng một nhà cung cấp danh tính để đăng nhập SSO. Người dùng sau đó gọi API quản lý hợp đồng. Nhà cung cấp danh tính có thể xác nhận người gọi là ai, nhưng API vẫn phải quyết định người đó được đọc, sửa hay phê duyệt hợp đồng nào.

Application plane là nơi quyết định truy cập cần gặp đúng tài nguyên và đúng nghiệp vụ. Một lần đăng nhập thành công không thể thay thế toàn bộ việc kiểm tra đó.

## 2. Phân biệt các nhóm trách nhiệm

Có thể nhìn kiến trúc IAM qua những nhóm trách nhiệm sau:

| Nhóm trách nhiệm | Ví dụ công việc |
| --- | --- |
| Quản trị danh tính và chính sách | Quản lý tài khoản, vai trò, phê duyệt quyền, cấu hình client và quy tắc |
| Cung cấp chức năng danh tính | Xác thực, quản lý phương tiện xác thực, phát hành hoặc kiểm tra bằng chứng danh tính |
| Application plane | Tiếp nhận ngữ cảnh danh tính, đánh giá hoặc yêu cầu đánh giá quyền, thực thi trên nghiệp vụ |
| Lưu trữ và cung cấp dữ liệu | Giữ tài nguyên, thuộc tính, quan hệ sở hữu và các dữ liệu cần cho quyết định |
| Quan sát và kiểm toán | Ghi nhận sự kiện, quyết định và kết quả để vận hành, điều tra |

Đây là một cách phân chia để thiết kế, không phải các lớp triển khai bắt buộc tách biệt. Một dịch vụ có thể đảm nhận nhiều vai trò, nhưng vẫn cần chỉ rõ nó đang có trách nhiệm gì tại từng điểm.

Việc đội IAM quản lý vai trò không có nghĩa đội IAM tự biết mọi điều kiện nghiệp vụ. Chẳng hạn, một người có vai trò phê duyệt nhưng vẫn có thể không được phê duyệt hợp đồng do chính mình tạo hoặc hợp đồng đã đóng.

Ngược lại, đội ứng dụng không nên tự tạo một cơ chế tin cậy danh tính khác ở từng API chỉ để thuận tiện. Những hợp đồng tích hợp chung giúp giữ nhất quán về nguồn danh tính, loại bằng chứng và ngữ nghĩa thuộc tính.

## 3. Luồng truy cập từ danh tính tới tài nguyên

Một luồng minh họa:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API hợp đồng
    participant V as Thành phần xác minh danh tính
    participant P as Thành phần quyết định quyền
    participant D as Dữ liệu nghiệp vụ
    C->>A: Yêu cầu đọc hợp đồng
    A->>V: Xác minh bằng chứng theo hợp đồng tích hợp
    V-->>A: Ngữ cảnh danh tính đáng tin cậy
    A->>D: Lấy ngữ cảnh tài nguyên tối thiểu cần thiết
    A->>P: Chủ thể, hành động, tài nguyên, bối cảnh
    P-->>A: Quyết định và giới hạn cần thực thi
    A->>D: Truy cập dữ liệu trong phạm vi được phép
    A-->>C: Kết quả đã áp dụng giới hạn
~~~

Sơ đồ không yêu cầu mỗi bước là một cuộc gọi mạng. Xác minh bằng chứng hoặc đánh giá quyền có thể nằm trong thư viện, middleware hoặc dịch vụ riêng.

Điểm quan trọng là ứng dụng không đi thẳng từ “đã đọc được một claim” tới “được trả tài nguyên”. Cần xác minh nguồn và ý nghĩa của thông tin, sau đó xét quyền cho yêu cầu cụ thể.

Việc lấy dữ liệu để đánh giá quyền cũng phải có giới hạn. API có thể cần tenant, chủ sở hữu và trạng thái của hợp đồng trước khi quyết định, nhưng không nên tải rồi phát tán toàn bộ nội dung nhạy cảm trước bước kiểm tra.

Khi không được phép, ứng dụng không trả nội dung rồi kỳ vọng client tự ẩn đi. Giới hạn phải được áp dụng trước khi dữ liệu rời khỏi điểm kiểm soát tương ứng.

## 4. Tiếp nhận danh tính qua một hợp đồng rõ ràng

Mỗi loại ứng dụng cần xác định bằng chứng nào được chấp nhận, ai phát hành và bằng chứng đó dùng cho việc gì.

Có thể có các mô hình như phiên phía server, token cho API hoặc danh tính workload. Không nên trộn chúng chỉ vì cùng chứa một định danh người dùng.

Một hợp đồng tích hợp cần làm rõ:

- Nguồn phát hành được tin cậy.
- Loại bằng chứng và luồng sử dụng.
- Bên nhận dự kiến.
- Thời gian hiệu lực và cách xử lý thời gian.
- Cách xác minh tính toàn vẹn hoặc trạng thái.
- Ý nghĩa của định danh chủ thể, tenant và các thuộc tính.
- Cách xử lý khi bằng chứng thiếu, sai hoặc không thể xác minh.

Với token, việc giải mã được nội dung không chứng minh token hợp lệ. Cần thực hiện các kiểm tra phù hợp với loại token và hợp đồng tin cậy đã chọn.

Một token dành cho client hoặc mục tiêu khác không tự trở thành bằng chứng hợp lệ để gọi API hiện tại. Chẳng hạn, không mặc định một ID token nhận ở bước đăng nhập là access token cho mọi API.

Các trường danh tính do client tự gửi, như userId, tenantId hoặc role trong body hay header, không nên được coi là sự thật chỉ vì tên trường có vẻ nội bộ. Nếu có thành phần trung gian cung cấp ngữ cảnh, cần bảo đảm chỉ nguồn được tin cậy mới có thể tạo hoặc sửa ngữ cảnh đó.

Không sử dụng email hoặc tên hiển thị như khóa chủ thể bất biến nếu vòng đời của chúng không đáp ứng yêu cầu định danh. Ứng dụng cần một cách ánh xạ ổn định, có phạm vi rõ và có xử lý cho thay đổi hoặc liên kết tài khoản.

## 5. Giao diện, gateway và backend có vai trò khác nhau

Ẩn nút “Phê duyệt” trên giao diện có thể giúp người dùng hiểu chức năng hiện có. Nó không ngăn một client khác gửi trực tiếp yêu cầu tới API.

Tương tự, gateway có thể xác minh token, hạn chế lưu lượng hoặc áp dụng kiểm tra chung. Nhưng nếu gateway không có ngữ cảnh sở hữu và trạng thái hợp đồng, nó không thể thay thế mọi quyết định nghiệp vụ.

| Thành phần | Vai trò có thể đảm nhận | Điều không nên mặc định |
| --- | --- | --- |
| Giao diện web hoặc mobile | Điều chỉnh trải nghiệm và gọi đúng luồng | Client có thể tự bảo vệ dữ liệu ở server |
| Gateway | Kiểm tra chung ở điểm vào, xác minh bằng chứng theo thiết kế | Mọi yêu cầu qua gateway đều có quyền với từng đối tượng |
| Backend nghiệp vụ | Kiểm tra quyền theo hành động và tài nguyên | Đăng nhập thành công là đủ |
| Dịch vụ dữ liệu | Áp dụng giới hạn truy vấn hoặc dữ liệu theo trách nhiệm | Tất cả client nội bộ đều đáng tin |
| Worker nền | Thực hiện tác vụ dưới danh tính và phạm vi được cấp | Chạy không có người dùng thì không cần kiểm tra quyền |

Nếu backend chỉ an toàn khi mọi request phải đi qua gateway, kiến trúc cần bảo đảm đường truy cập trực tiếp không bỏ qua kiểm soát. Một header chứa danh tính do gateway gắn phải được bảo vệ khỏi việc bên ngoài tự giả mạo.

Mô hình backend phục vụ riêng cho giao diện có thể giúp quản lý phiên hoặc giữ một số thông tin nhạy cảm ở phía server. Tuy nhiên, backend đó vẫn cần kiểm tra quyền trên các hành động mà nó thực hiện.

## 6. Điểm quyết định và điểm thực thi quyền

Có thể phân biệt hai vai trò:

- Policy Decision Point, viết tắt PDP: đánh giá chính sách và đưa ra quyết định.
- Policy Enforcement Point, viết tắt PEP: kiểm soát thao tác để quyết định đó thực sự có hiệu lực.

Trong application plane, API, middleware hoặc lớp truy cập dữ liệu có thể đảm nhận vai trò PEP. PDP có thể là logic trong ứng dụng hoặc một thành phần được gọi từ ứng dụng.

Các cách bố trí có đánh đổi khác nhau:

| Cách bố trí | Điểm thuận lợi | Điều cần quản lý |
| --- | --- | --- |
| Quyết định trong ứng dụng | Gần ngữ cảnh nghiệp vụ, ít phụ thuộc mạng cho bước quyết định | Trùng logic, lệch phiên bản và khác cách diễn giải |
| Dịch vụ quyết định dùng chung | Tập trung một phần policy và khả năng quan sát | Độ trễ, khả năng phục vụ và độ mới của dữ liệu đầu vào |
| Kết hợp | Dùng kiểm tra chung cùng điều kiện cục bộ | Ranh giới trách nhiệm và thứ tự kiểm tra |

Không có lựa chọn nào tự bảo đảm quyền được thực thi đúng. PDP trả “không cho phép” nhưng ứng dụng vẫn tiếp tục thao tác là lỗi ở điểm thực thi.

Quyết định cũng có thể kèm giới hạn như chỉ trả một số trường hoặc chỉ cho xem dữ liệu đã che. Nếu ứng dụng không thực hiện được giới hạn bắt buộc, không nên coi đó là một quyết định cho phép không điều kiện.

Các quy tắc xử lý kết quả không xác định, lỗi đánh giá hoặc policy không khớp cần được thiết kế rõ. Không biến lỗi kết nối tới thành phần quyết định thành quyền truy cập rộng hơn.

## 7. Kết hợp quyền với tài nguyên và trạng thái nghiệp vụ

Một mô hình đầu vào có thể gồm:

~~~text
Chủ thể:
    định danh đã được xác minh
    loại chủ thể
    các thuộc tính và quyền có nguồn phù hợp

Hành động:
    contract.read
    contract.edit
    contract.approve
    contract.export

Tài nguyên:
    hợp đồng cụ thể
    tenant sở hữu
    quan hệ với chủ thể
    trạng thái nghiệp vụ

Bối cảnh:
    phương thức truy cập
    ngữ cảnh xác thực cần thiết
    thời gian và các điều kiện chính sách liên quan
~~~

Đây là mô hình minh họa, không phải schema của một sản phẩm.

Ví dụ, để phê duyệt hợp đồng, có thể cần đồng thời:

~~~text
Danh tính hợp lệ
VÀ chủ thể thuộc tenant được phép
VÀ có quyền phê duyệt trong phạm vi tương ứng
VÀ hợp đồng đang chờ phê duyệt
VÀ không vi phạm điều kiện tách biệt trách nhiệm
VÀ đạt yêu cầu xác thực cho thao tác
~~~

Một role có tên “approver” không tự cung cấp toàn bộ các điều kiện này. Scope cho phép gọi API cũng có thể chỉ là kiểm tra ở mức rộng, chưa chứng minh quyền với từng hợp đồng.

Thông tin về tenant, sở hữu và trạng thái phải đến từ nguồn phù hợp. Nếu chỉ so tenantId trong body với tenantId do cùng client tự khai, phép so sánh chưa tạo ra một ranh giới bảo mật đáng tin cậy.

Kiểm tra quyền cũng cần theo hành động. Đọc một hợp đồng, xem trường nhạy cảm và xuất hàng loạt có thể có phạm vi khác nhau. Không mặc định quyền đọc bao gồm mọi cách sao chép hoặc phân phối dữ liệu.

## 8. Cô lập tenant và giới hạn dữ liệu trả về

Trong hệ thống nhiều tenant, một định danh tài nguyên hợp lệ chưa chứng minh người gọi được truy cập tài nguyên đó.

API cần kiểm tra mối liên hệ giữa chủ thể, tenant của yêu cầu và tenant của tài nguyên. Nếu cho phép truy cập liên tenant, quyền đó phải được mô tả riêng với phạm vi tương ứng.

Các đường cần xem xét gồm:

- Đọc, sửa hoặc xóa đối tượng theo ID.
- Danh sách, tìm kiếm và phân trang.
- Truy cập file đính kèm.
- Xuất báo cáo hoặc chạy tác vụ nền.
- Endpoint hỗ trợ và quản trị.
- Cache dữ liệu hoặc cache quyết định quyền.

Với danh sách, không chỉ kiểm tra quyền với endpoint rồi trả mọi bản ghi. Cần giới hạn tập dữ liệu theo policy và bảo đảm các trang tiếp theo vẫn áp dụng cùng phạm vi.

Nếu có masking hoặc giới hạn trường, cần thực hiện ở đường trả dữ liệu, không chỉ ở màn hình. Response không nên chứa trường mà client không được nhận dù giao diện đang ẩn trường đó.

Cache phải giữ được những yếu tố phân biệt có ảnh hưởng tới kết quả, chẳng hạn chủ thể, tenant, hành động, tài nguyên và trạng thái policy phù hợp. Một cache chỉ khóa theo resource ID có thể trả dữ liệu hoặc quyết định của chủ thể khác.

Không đưa mọi dữ liệu danh tính vào cache để giải quyết vấn đề này. Chọn khóa, giá trị và vòng đời theo đúng mục tiêu của cache, đồng thời bảo vệ những tham chiếu có thể liên kết tới người dùng.

## 9. Lời gọi giữa các dịch vụ và tác vụ nền

Khi API A gọi API B, B cần biết mình đang tin điều gì:

| Ngữ cảnh | Câu hỏi |
| --- | --- |
| Danh tính workload gọi tới | Dịch vụ nào đang kết nối và được phép làm gì? |
| Ngữ cảnh người dùng nếu có | Dịch vụ đang thay mặt ai và trong phạm vi nào? |
| Quyền của lời gọi | Hành động này có nằm trong phạm vi được giao không? |
| Đích nhận | Bằng chứng hoặc thông tin ủy quyền có dành cho dịch vụ này không? |

Không coi một lời gọi từ mạng nội bộ là đủ. Danh tính dịch vụ và quyền gọi cần được xác lập theo kiến trúc.

Cũng không tự động chuyển tiếp cùng một token người dùng tới mọi dịch vụ. Bên nhận, phạm vi và cơ chế ủy quyền phải phù hợp với từng đường gọi.

Nếu cần giữ ngữ cảnh thay mặt người dùng, ngữ cảnh đó phải được truyền qua cơ chế đáng tin cậy. Một header tự do mang userId không đủ để chứng minh quyền ủy quyền.

Với tác vụ nền, cần quyết định công việc chạy theo quyền của ai, quyền được kiểm tra khi tạo job và khi thực thi như thế nào. Quyền có thể đã thay đổi trong khoảng chờ.

Ví dụ, người dùng được phép yêu cầu xuất báo cáo lúc 10:00 nhưng bị thu hồi quyền trước khi job chạy. Kiến trúc cần quy tắc rõ cho việc tiếp tục, đánh giá lại hoặc hủy, thay vì để hành vi phụ thuộc ngẫu nhiên vào cache.

Tài khoản dịch vụ cũng cần quyền tối thiểu và chủ sở hữu. Không dùng một credential có toàn quyền cho mọi job chỉ vì các job thuộc cùng ứng dụng.

## 10. Phiên, token, cache và thời điểm thu hồi quyền

Application plane thường giữ những bản sao của trạng thái danh tính hoặc quyền:

- Phiên ứng dụng.
- Claim trong token.
- Membership đã tải.
- Cache quyết định truy cập.
- Quyền đã gắn với một job.
- Ngữ cảnh của kết nối tồn tại lâu.

Khi người dùng nghỉ việc hoặc bị giảm quyền, thay đổi tại nguồn không tự làm mọi bản sao đó mất hiệu lực ngay lập tức.

Cần xác định các mốc:

| Mốc | Câu hỏi cần trả lời |
| --- | --- |
| Ngừng cấp bằng chứng mới | Tài khoản còn tạo phiên hoặc nhận token mới được không? |
| Kết thúc phiên hiện tại | Ứng dụng có nhận và áp dụng tín hiệu kết thúc không? |
| Dữ liệu quyền được cập nhật | Cache hoặc membership cũ được xử lý khi nào? |
| Yêu cầu đang thực hiện | Thao tác đã bắt đầu được phép đi tới đâu? |
| Tác vụ chờ | Quyền có được đánh giá lại trước lúc thực thi không? |

Thời hạn token hoặc TTL cache là một phần của thiết kế, không phải bằng chứng độc lập rằng mọi quyền đã bị thu hồi theo cùng một thời hạn.

Với một thao tác có tác động lớn, có thể cần kiểm tra trạng thái mới hơn ở một mốc phù hợp. Cần xét cả thay đổi nghiệp vụ giữa lúc kiểm tra và lúc ghi dữ liệu.

Đưa kiểm tra quyền và cập nhật nghiệp vụ vào cùng một phạm vi xử lý phù hợp có thể giúp tránh một số sai lệch, nhưng không tạo ra tính nguyên tử toàn cục giữa mọi kho danh tính và ứng dụng. Kiến trúc vẫn cần công bố độ trễ, mốc hiệu lực và giới hạn còn lại.

## 11. Xử lý lỗi phụ thuộc mà vẫn giữ đúng chính sách

Lỗi nhà cung cấp danh tính, lỗi kho thuộc tính và lỗi dịch vụ quyết định có tác động khác nhau.

Một ứng dụng xác minh được loại token phù hợp bằng dữ liệu tin cậy cục bộ có thể tiếp tục một số hoạt động theo thiết kế khi một phụ thuộc không truy cập được. Điều đó không có nghĩa mọi loại token hoặc mọi thao tác đều không cần phụ thuộc trực tuyến.

Ngược lại, nếu luồng yêu cầu kiểm tra trạng thái trực tuyến mà thành phần kiểm tra không hoạt động, ứng dụng không nên tự chuyển sang chấp nhận một loại bằng chứng khác chỉ để tránh lỗi.

Những quy tắc cần làm rõ gồm:

- Timeout và giới hạn retry.
- Khi nào dữ liệu cache còn được chấp nhận.
- Thao tác nào cần thông tin mới.
- Cách xử lý khóa hoặc cấu hình tin cậy chưa biết.
- Phạm vi hành vi suy giảm đã được thiết kế.
- Cách ghi nhận lỗi đánh giá và quyết định từ chối.

Không nhận diện được nguồn phát hành hoặc không xác minh được bằng chứng không phải lý do để bỏ bước xác minh. Tương tự, thiếu thuộc tính bắt buộc không nên được hiểu thành “không có giới hạn”.

Có thể tách lỗi kỹ thuật khỏi từ chối theo policy trong quan sát nội bộ, để đội vận hành biết nên kiểm tra hạ tầng hay quy tắc. Response gửi ra ngoài vẫn cần tránh tiết lộ thông tin không cần thiết về tài khoản hoặc tài nguyên.

## 12. Quan sát quyết định và kết quả thực thi

Application plane cần giúp đối chiếu cả quyết định lẫn điều thực sự xảy ra.

Một bản ghi minh họa:

~~~json
{
  "event_type": "application_access_decision",
  "subject_reference": "subject-example-7",
  "workload_reference": "contracts-api",
  "tenant_reference": "tenant-example-3",
  "action": "contract.approve",
  "resource_reference": "contract-example-25",
  "decision": "deny",
  "reason_code": "separation_of_duties",
  "policy_version": "contracts-policy-v4",
  "correlation_reference": "request-example-81"
}
~~~

Các giá trị là dữ liệu giả. Những tham chiếu này không được là credential hoặc có khả năng cấp quyền.

Bản ghi quyết định không nhất thiết chứng minh thao tác đã thành công hay thất bại ở dữ liệu nghiệp vụ. Nếu được cho phép nhưng giao dịch ghi lỗi, cần phân biệt kết quả thực thi với kết quả authorization.

Các tín hiệu vận hành có thể gồm số quyết định theo kết quả, lỗi đánh giá, latency, độ mới của policy và độ trễ áp dụng thay đổi quyền. Không dùng một biểu đồ “tỷ lệ cho phép” làm chỉ số an toàn duy nhất.

Log không nên chứa mật khẩu, token, mã MFA hoặc toàn bộ hồ sơ danh tính. Dùng dữ liệu vừa đủ để đối chiếu, với quyền xem và vòng đời phù hợp.

Mã lý do cũng cần được kiểm soát. Có thể hữu ích ở log nội bộ nhưng không nhất thiết phù hợp để trả nguyên vẹn cho client chưa được biết tài nguyên có tồn tại hay không.

## 13. Phân chia trách nhiệm giữa đội IAM và đội ứng dụng

| Nội dung | Trách nhiệm cần được xác lập |
| --- | --- |
| Nguồn danh tính và hợp đồng token hoặc phiên | Đội IAM cùng đội tích hợp ứng dụng |
| Quyền nghiệp vụ trên tài nguyên | Đội sở hữu nghiệp vụ và ứng dụng |
| Mapping thuộc tính, scope và role | Các bên thống nhất ngữ nghĩa và phạm vi |
| Điểm thực thi quyền | Đội sở hữu API, dịch vụ hoặc tầng dữ liệu tương ứng |
| Vòng đời tài khoản và tín hiệu thu hồi | Nguồn có thẩm quyền, đội IAM và ứng dụng tiêu thụ |
| Quan sát và điều tra | Đội vận hành, bảo mật và ứng dụng theo quyền |
| Thay đổi policy | Chủ sở hữu policy với quy trình triển khai và xác nhận |

Một hợp đồng tốt cần nêu rõ điều gì xảy ra khi thêm role, đổi tên thuộc tính, thay issuer, đổi tenant hoặc thu hồi quyền.

Ứng dụng cũng cần biết phiên bản policy hoặc cấu hình đang dùng. Khi cập nhật, cần có cách xác nhận các instance và vùng phục vụ lưu lượng đã áp dụng đúng.

Không giải quyết mọi thay đổi bằng cách cấp thêm quyền rộng hơn cho ứng dụng. Quyền quản trị để sửa policy, quản lý client hoặc xuất dữ liệu phải được bảo vệ riêng với luồng sử dụng thông thường.

Các đường hỗ trợ và vận hành thuộc cùng bài toán kiến trúc. Một endpoint nội bộ bỏ qua kiểm tra tài nguyên có thể trở thành đường truy cập khác dù API chính đã được thiết kế cẩn thận.

## 14. Ví dụ tại An Bình

An Bình ban đầu chỉ kiểm tra người dùng có token hợp lệ và role “approver”. API phê duyệt nhận tenantId và contractId từ request rồi thực hiện cập nhật.

Thiết kế này còn thiếu những câu trả lời quan trọng: hợp đồng thuộc tenant nào, chủ thể có quyền trong tenant đó không, ai tạo hợp đồng và trạng thái hiện tại có cho phép phê duyệt không.

Nhóm ứng dụng xác lập lại đường xử lý:

1. Xác minh bằng chứng theo hợp đồng của API.
2. Xác định chủ thể và ngữ cảnh tenant từ nguồn đáng tin cậy.
3. Lấy metadata cần cho kiểm tra hợp đồng.
4. Đánh giá hành động phê duyệt theo phạm vi quyền và trạng thái nghiệp vụ.
5. Áp dụng quyết định cùng các giới hạn bắt buộc.
6. Thực hiện cập nhật với điều kiện trạng thái phù hợp.
7. Ghi nhận quyết định và kết quả thực thi riêng.

Gateway tiếp tục thực hiện kiểm tra chung. Giao diện tiếp tục ẩn hoặc hiện nút để hỗ trợ trải nghiệm. API giữ trách nhiệm kiểm tra đối tượng và hành động.

Khi người phê duyệt bị giảm quyền, nhóm không chỉ cập nhật role ở nguồn. Họ còn xác định cách phiên, token, cache và job phê duyệt đang chờ phản ánh thay đổi.

Với job xuất báo cáo, workload có danh tính riêng và chỉ được đọc phạm vi dữ liệu cần thiết. Nó không dùng credential quản trị chung để bỏ qua policy người dùng.

## 15. Những tình huống cần kiểm tra trong application plane

| Tình huống | Điều cần bảo đảm |
| --- | --- |
| Client sửa userId hoặc role trong request | Không thay đổi danh tính và quyền đáng tin cậy |
| Token không dành cho API | Không được chấp nhận như bằng chứng phù hợp |
| Người dùng có role đúng nhưng sai tenant | Không truy cập tài nguyên ngoài phạm vi |
| Người dùng đoán được resource ID | Vẫn phải qua kiểm tra đối tượng |
| UI ẩn nút nhưng client gọi trực tiếp API | Backend tiếp tục thực thi quyền |
| Request đi đường khác ngoài gateway | Không bỏ qua ranh giới kiểm soát đã xác định |
| Policy yêu cầu che trường | Dữ liệu thực tế trả về đã áp dụng giới hạn |
| Cache đã có quyết định cho người khác | Không dùng sai ngữ cảnh chủ thể hoặc tenant |
| Quyền bị thu hồi khi job đang chờ | Xử lý theo quy tắc vòng đời đã xác định |
| Dịch vụ A gọi B thay mặt người dùng | Có bằng chứng phù hợp cho workload và ngữ cảnh ủy quyền |
| PDP hoặc nguồn thuộc tính lỗi | Không tự mở rộng quyền |
| Trạng thái nghiệp vụ đổi sau kiểm tra | Thao tác ghi vẫn giữ các điều kiện cần thiết |
| Quyết định cho phép nhưng giao dịch lỗi | Phân biệt được authorization và kết quả nghiệp vụ |
| Kiểm tra log và telemetry | Không có credential hoặc dữ liệu danh tính dư thừa |

Application plane làm cho kiến trúc IAM có hiệu lực trên tài nguyên thực tế. Giá trị của nó nằm ở việc nối danh tính đáng tin cậy với hành động, đối tượng và trạng thái nghiệp vụ, rồi thực thi những giới hạn đó trên mọi đường truy cập cần được bảo vệ.

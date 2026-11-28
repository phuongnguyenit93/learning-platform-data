# Privilege elevation request trên endpoint

## 1. Yêu cầu nâng quyền giải quyết vấn đề gì?

Trong Endpoint Privileged Access Management (Endpoint PAM), **privilege elevation request** là yêu cầu cho phép một chủ thể thực hiện một công việc cần quyền cao hơn quyền hiện tại trên một thiết bị đầu cuối. Ví dụ, kỹ sư cần cài công cụ chẩn đoán đã được duyệt, nhân viên hỗ trợ cần sửa một dịch vụ, hoặc quản trị viên cần chạy một lệnh bảo trì trên máy trạm.

Một yêu cầu tốt không chỉ nói “cho tôi quyền admin”. Nó mô tả được **ai cần thực hiện hành động nào, bằng chương trình nào, trên thiết bị nào, trong khoảng thời gian nào và vì lý do gì**. Endpoint PAM sử dụng thông tin này để quyết định và cưỡng chế phạm vi cho phép.

Mục tiêu của bài là thiết kế được vòng đời yêu cầu nâng quyền có thể vận hành và kiểm toán: từ lúc người dùng bị chặn vì thiếu quyền, gửi yêu cầu, được xét duyệt, thực thi tác vụ, cho đến khi quyền hết hiệu lực và kết quả được đối soát.

Phạm vi là quản lý truy cập đặc quyền đối với endpoint trong chương trình PAM: kiểm kê quyền, least privilege, quyền đúng lúc và vừa đủ, giám sát, lưu bằng chứng và ứng phó sự cố. Bài không giả định một sản phẩm PAM cụ thể và không yêu cầu người dùng biết mật khẩu quản trị cục bộ.

### Một tình huống mở đầu

Lan là kỹ sư hỗ trợ. Tài khoản thường của Lan không thuộc nhóm quản trị cục bộ. Lan cần chạy công cụ sửa hàng đợi in trên máy được giao.

Yêu cầu “thêm Lan vào local Administrators trong ngày hôm nay” có phạm vi rất rộng: trong thời gian đó, nhiều chương trình khác có thể dùng quyền quản trị.

Yêu cầu có phạm vi hẹp hơn là:

> Cho Lan chạy đúng công cụ sửa hàng đợi in đã được kiểm tra, trên đúng máy cần hỗ trợ, một lần trong cửa sổ bảo trì 15 phút, với đầu vào đã xác định.

Đây là hướng áp dụng least privilege và Just Enough Administration (JEA). Thời điểm được cấp và thời hạn áp dụng thể hiện Just-in-Time (JIT). Tuy nhiên, “chỉ có hiệu lực 15 phút” chưa đủ để biến một yêu cầu admin rộng thành quyền vừa đủ.

## 2. Phân biệt yêu cầu, phê duyệt và nâng quyền thực tế

Ba khái niệm này cần được tách biệt khi thiết kế:

| Khái niệm | Ý nghĩa | Bằng chứng cần có |
|---|---|---|
| Yêu cầu | Người dùng mô tả nhu cầu thực hiện một tác vụ đặc quyền | Người yêu cầu, mục tiêu, phạm vi, lý do, thời điểm |
| Quyết định | Chính sách hoặc người có thẩm quyền cho phép hay từ chối phạm vi đó | Quyết định, người hoặc cơ chế quyết định, phiên bản chính sách, điều kiện |
| Thực thi | Thành phần tin cậy trên endpoint xác minh và chạy tác vụ được phép | Định danh endpoint, tiến trình, danh tính thực thi, kết quả, thời gian |

Một phê duyệt có thể không bao giờ được sử dụng. Một lần người dùng bấm chạy có thể bị chặn dù trước đó đã được duyệt, chẳng hạn file thực thi đã thay đổi hoặc thiết bị không còn đạt yêu cầu.

Do đó:

- `Approved` không chứng minh tác vụ đã chạy.
- `Executed` không chứng minh tác vụ đã thành công.
- Tác vụ thành công không chứng minh mọi thay đổi của nó đều đã được hoàn tác khi thời hạn kết thúc.

Một dấu nhắc nâng quyền của hệ điều hành cũng không mặc nhiên là quy trình phê duyệt nghiệp vụ. Việc người dùng xác nhận một cửa sổ hệ thống không thay thế cho kiểm tra phạm vi, vai trò người duyệt, thời hạn và bằng chứng của Endpoint PAM.

### Hai kiểu cấp quyền thường gặp

**Nâng quyền cho một tác vụ hoặc ứng dụng** cho phép một tiến trình thực hiện công việc nhất định. Mô hình này thường có thể giới hạn tốt hơn, nhưng vẫn phải kiểm tra tham số, tiến trình con, file cấu hình và các tài nguyên chương trình đọc hoặc thực thi.

**Cấp quyền cho tài khoản trong một thời gian** thay đổi khả năng của tài khoản, chẳng hạn tạm thêm vào nhóm đặc quyền. Phạm vi thường rộng hơn. Việc gỡ tài khoản khỏi nhóm không bảo đảm mọi tiến trình đã tạo lập tức mất khả năng đã nhận; hiệu lực còn phụ thuộc cơ chế token, phiên đăng nhập, bộ nhớ đệm và hệ điều hành.

Vì vậy, khi tác vụ cụ thể có thể được giới hạn đáng tin cậy, ưu tiên mô tả yêu cầu theo tác vụ. Nếu phải cấp quyền theo tài khoản, cần ghi rõ lý do, phạm vi rủi ro, cách kết thúc và cách xác minh thu hồi.

## 3. Các thành phần của một quy trình

Một quy trình tối thiểu có các vai trò sau:

| Thành phần | Trách nhiệm |
|---|---|
| Người yêu cầu | Khai báo mục đích và phạm vi công việc, cung cấp ticket hoặc bằng chứng cần thiết |
| Bộ máy chính sách | Phân loại tác vụ, đánh giá điều kiện, chọn đường tự động hoặc phê duyệt thủ công |
| Người phê duyệt | Kiểm tra tính cần thiết và thẩm quyền đối với phạm vi được yêu cầu |
| Dịch vụ cấp phép | Phát hành quyền thực thi có thời hạn, ràng buộc với yêu cầu đã được duyệt |
| Thành phần thực thi trên endpoint | Xác minh cấp phép, kiểm tra lại điều kiện và cưỡng chế tác vụ |
| Hệ thống ghi nhận và giám sát | Thu thập sự kiện, liên kết với ticket, hỗ trợ điều tra và rà soát |
| Chủ sở hữu kiểm soát | Duy trì chính sách, xử lý ngoại lệ và đánh giá xu hướng cấp quyền |

Việc xác định ai chịu trách nhiệm quan trọng không kém công nghệ. Nếu không có chủ sở hữu rõ ràng, hàng đợi yêu cầu dễ trở thành nơi mọi người bấm duyệt để giảm tồn đọng.

Người yêu cầu không tự phê duyệt yêu cầu của mình khi chính sách đòi hỏi phân tách nhiệm vụ. Với tác vụ rủi ro cao, người phê duyệt cần hiểu được phạm vi kỹ thuật hoặc có hỗ trợ từ nhóm đủ năng lực; chức danh quản lý trực tiếp không tự động tạo ra năng lực này.

## 4. Dữ liệu cần có trong yêu cầu

### 4.1. Xác định chủ thể và thiết bị

Không chỉ lưu tên hiển thị. Hệ thống cần định danh ổn định của người yêu cầu, tổ chức hoặc nhóm liên quan, và endpoint dự kiến thực thi.

Một yêu cầu được duyệt trên máy của Lan không được tự động dùng trên máy khác. Tên máy dễ đọc có ích cho vận hành, nhưng không nên là bằng chứng duy nhất để xác minh thiết bị.

Thông tin về trạng thái thiết bị có thể gồm trạng thái quản lý, tình trạng thành phần PAM, đồng bộ thời gian, khả năng gửi log và tín hiệu an ninh được tổ chức chấp nhận. Các điều kiện thực tế phải được định nghĩa trong chính sách, không suy ra từ một trường “compliant” không có nguồn gốc.

### 4.2. Xác định tác vụ và đối tượng thực thi

Tùy loại tác vụ, mô tả có thể cần:

- File thực thi, gói cài đặt hoặc script dự kiến.
- Dấu vân tay nội dung, nhà phát hành hoặc tiêu chí tin cậy được chính sách chấp nhận.
- Tham số được phép, thư mục làm việc và tài nguyên đích.
- Phạm vi file, thư mục, dịch vụ hoặc cấu hình được phép tác động.
- Quy tắc đối với tiến trình con.
- Danh tính đặc quyền sẽ được hệ thống sử dụng.
- Giới hạn số lần thực thi và cách xử lý chạy lại.

Đường dẫn không đủ để định danh chương trình nếu người dùng có thể thay file tại đường dẫn đó. Chữ ký số hợp lệ cũng không đồng nghĩa chương trình được phép thực hiện mọi tác vụ trong mọi ngữ cảnh. Cần xét tác vụ và khả năng chương trình diễn giải đầu vào.

### 4.3. Lý do và thời gian

Lý do nên gắn với công việc cụ thể: “khôi phục dịch vụ in cho ticket INC-DEMO-421”, thay vì “cần làm việc”.

Phần thời gian cần phân biệt:

| Mốc | Câu hỏi cần trả lời |
|---|---|
| Hạn chờ quyết định | Yêu cầu có còn giá trị nếu chưa ai xét sau thời gian này? |
| Cửa sổ được phép bắt đầu | Người dùng có thể khởi chạy tác vụ từ lúc nào đến lúc nào? |
| Số lần sử dụng | Được chạy một lần hay nhiều lần? |
| Giới hạn thời gian chạy | Nếu tiến trình vẫn chạy thì hệ thống xử lý thế nào? |
| Hạn của ngoại lệ | Nếu tồn tại ngoại lệ, khi nào phải rà soát hoặc loại bỏ? |

“Hết hạn phê duyệt” và “dừng tiến trình” là hai cơ chế khác nhau. Nếu hệ thống chỉ chặn khởi chạy mới khi hết hạn, bài toán quản trị vẫn cần quyết định cách xử lý các tiến trình đang chạy.

### 4.4. Ví dụ bản ghi yêu cầu

Ví dụ sau là mô hình dữ liệu minh họa, không phải cấu hình có thể nạp trực tiếp vào một sản phẩm:

~~~yaml
requestId: ELEV-DEMO-1042
requesterId: user-demo-lan
endpointId: endpoint-demo-017
task:
  type: approved-maintenance-tool
  artifactId: print-repair-package-v3
  artifactDigest: sha256:<DIGEST_CUA_GOI_DA_KIEM_TRA>
  argumentsProfile: repair-local-print-queue
  targetResource: local-print-service
  childProcessPolicy: deny-unless-explicitly-allowed
  executionIdentityProfile: endpoint-maintenance
businessContext:
  ticketId: INC-DEMO-421
  reason: Khoi phuc hang doi in tren endpoint duoc giao
requestedWindow:
  start: "2026-11-27T09:00:00+07:00"
  end: "2026-11-27T09:15:00+07:00"
constraints:
  maxExecutions: 1
  requireManagedEndpoint: true
  requireFreshAuthentication: true
  requireOnlineDecision: true
~~~

Một digest giả hoặc ký hiệu giữ chỗ không được đưa vào chính sách thật. Ví dụ chỉ thể hiện rằng quyền cần gắn với một gói đã được định danh và kiểm tra bằng một cơ chế cụ thể.

Không đặt mật khẩu, token phiên, khóa riêng hoặc dữ liệu người dùng không cần thiết vào phần lý do. Trường văn bản tự do thường được sao chép vào ticket, log và thông báo, khiến bí mật lan rộng ngoài dự kiến.

## 5. Vòng đời yêu cầu và các trạng thái

Một mô hình vòng đời có thể biểu diễn như sau:

~~~mermaid
stateDiagram-v2
    [*] --> Submitted
    Submitted --> PendingReview: Cần người duyệt
    Submitted --> Approved: Chính sách tự động cho phép
    Submitted --> Denied: Không đạt điều kiện
    PendingReview --> Approved: Duyệt phạm vi cụ thể
    PendingReview --> Denied: Từ chối
    PendingReview --> Cancelled: Người yêu cầu hủy
    PendingReview --> Expired: Quá hạn chờ
    Approved --> Executing: Endpoint xác minh và tiêu thụ quyền
    Approved --> Expired: Hết cửa sổ bắt đầu
    Approved --> Revoked: Thu hồi trước khi dùng
    Executing --> Completed: Có kết quả thực thi
    Executing --> Failed: Lỗi thực thi
    Executing --> TerminationRequested: Có yêu cầu dừng
    TerminationRequested --> Terminated: Xác minh đã dừng
    TerminationRequested --> TerminationFailed: Chưa dừng được
~~~

Tên trạng thái có thể khác giữa các hệ thống. Điều quan trọng là ngữ nghĩa không mơ hồ và các chuyển trạng thái được kiểm soát.

### 5.1. Gửi và chuẩn hóa

Thành phần tiếp nhận xác minh người dùng, chuẩn hóa tác vụ và kiểm tra dữ liệu bắt buộc. Thiếu định danh gói hoặc thiếu tài nguyên đích thì không nên biến thành một yêu cầu rộng hơn để “cho chạy được”.

Có thể gợi ý cho người dùng chọn tác vụ có sẵn thay vì bắt họ tự nhập lệnh. Việc này giảm lỗi và giúp đội phê duyệt so sánh các yêu cầu đồng nhất.

### 5.2. Đánh giá và quyết định

Quyết định cần gắn với một **ảnh chụp phạm vi yêu cầu** hoặc phiên bản bất biến của nó. Nếu người dùng thay file, thêm tham số hoặc chuyển endpoint sau khi duyệt, hệ thống phải đánh giá lại.

Nếu người phê duyệt cho phép phạm vi hẹp hơn, hệ thống tạo phạm vi hiệu lực rõ ràng và cho người yêu cầu biết. Không âm thầm diễn giải “duyệt” thành một phạm vi khác với nội dung người duyệt đã xem.

### 5.3. Cấp phép và sử dụng

Quyền thực thi cần được bảo vệ chống sửa và giả mạo, đồng thời ràng buộc với người dùng, endpoint, tác vụ, thời gian và số lần sử dụng.

Với quyền dùng một lần, việc tiêu thụ quyền phải ngăn được hai yêu cầu khởi chạy đồng thời cùng sử dụng thành công. Nếu không có sự phối hợp phù hợp giữa các thành phần, “maxExecutions: 1” chỉ là một nhãn trong dữ liệu.

Cần xác định khi nào tính một lần sử dụng: khi đặt chỗ, khi khởi chạy thành công hay khi tác vụ hoàn tất. Một thiết kế thường dùng cơ chế đặt chỗ, ghi nhận khởi chạy và đối soát lỗi để tránh cả chạy trùng lẫn mất quyền do sự cố truyền thông.

### 5.4. Đóng và đối soát

Khi tác vụ kết thúc, ghi nhận kết quả cùng mã tương quan. Nếu endpoint mất kết nối trước khi gửi kết quả, trạng thái hợp lý có thể là “chưa xác định kết quả”, thay vì tự kết luận thành công.

Quy trình đối soát cần tìm được:

- Quyền đã duyệt nhưng không dùng.
- Quyền đã sử dụng nhưng thiếu kết quả.
- Tiến trình chạy quá thời gian đã cho phép.
- Trường hợp đã thu hồi nhưng endpoint chưa xác nhận.
- Yêu cầu bị hủy hoặc hết hạn nhưng vẫn có nỗ lực sử dụng.

Đóng ticket nghiệp vụ và đóng vòng đời cấp quyền là hai sự kiện có liên quan nhưng không thay thế nhau.

## 6. Chọn đường phê duyệt theo rủi ro

Không phải mọi yêu cầu đều cần một người bấm duyệt, và không phải mọi tác vụ đều phù hợp với tự động hóa.

### 6.1. Tự động cho phép có điều kiện

Có thể áp dụng cho tác vụ lặp lại, có phạm vi rõ, đã kiểm thử và có người sở hữu. Ví dụ: chạy một gói chẩn đoán nội bộ chỉ thu thập trạng thái hệ thống trong phạm vi đã xác định.

Các điều kiện cần được thực thi bằng máy: đúng gói, đúng nhóm người dùng, đúng thiết bị, đúng tham số, đúng cửa sổ thời gian và đúng tình trạng endpoint.

Một chính sách tự động cũng là quyết định cấp quyền. Nó cần có phiên bản, người chịu trách nhiệm, lịch rà soát và khả năng thu hồi.

### 6.2. Phê duyệt thủ công

Phù hợp khi tác vụ mới, tác động lớn hoặc cần xem xét bối cảnh nghiệp vụ. Người duyệt cần xem được phạm vi thực tế, không chỉ lý do văn bản.

Ví dụ màn hình duyệt nên thể hiện rõ:

> Người dùng Lan đề nghị chạy gói sửa dịch vụ in phiên bản đã xác định trên endpoint-demo-017, một lần trước 09:15. Gói chạy dưới hồ sơ bảo trì cục bộ; tiến trình con bị giới hạn. Ticket liên quan: INC-DEMO-421.

Một nút “Approve admin” che giấu các giới hạn này và khó tạo ra bằng chứng về quyết định có hiểu biết.

### 6.3. Từ chối hoặc chuyển sang quy trình khác

Một số yêu cầu không nên được giải quyết bằng đường nâng quyền thông thường, chẳng hạn chạy công cụ chưa xác định nguồn gốc hoặc mở shell quản trị để thực hiện “bất kỳ thao tác nào cần thiết”.

Nếu nhu cầu hợp lệ nhưng phạm vi quá rộng, có thể đề nghị tách thành tác vụ xác định, dùng gói triển khai đã duyệt hoặc chuyển sang quy trình bảo trì có giám sát. Tình huống khẩn cấp cần đi theo cơ chế break-glass đã định nghĩa, thay vì biến mọi yêu cầu khẩn thành ngoại lệ không thời hạn.

### 6.4. Bảng định hướng quyết định

| Tình huống | Hướng xử lý minh họa | Điều kiện cần làm rõ |
|---|---|---|
| Công cụ chẩn đoán đã được quản lý | Có thể tự động cho phép | Phạm vi thu thập, đầu ra, tham số và phiên bản |
| Cài gói nội bộ đã kiểm tra | Chính sách hoặc người duyệt tùy tác động | Nguồn gói, thay đổi hệ thống, yêu cầu khởi động lại |
| Sửa cấu hình dịch vụ dùng chung | Phê duyệt thủ công theo thẩm quyền | Thiết bị đích, thay đổi dự kiến, phương án phục hồi |
| Chạy trình thông dịch hoặc shell quản trị | Đánh giá riêng với phạm vi rộng | Khả năng giới hạn thực tế và giám sát |
| Tắt kiểm soát bảo vệ endpoint | Quy trình ngoại lệ riêng hoặc từ chối | Thẩm quyền an ninh, thời hạn, biện pháp bù trừ |

Bảng này không phải một chính sách phổ quát. Tổ chức phải gắn mức rủi ro với tài sản, dữ liệu và tác động vận hành cụ thể.

## 7. Cưỡng chế phạm vi tại thời điểm chạy

Phê duyệt ở máy chủ chỉ có ý nghĩa nếu endpoint thực thi đúng phạm vi đó.

### 7.1. Xác minh lại đối tượng

Giữa lúc gửi yêu cầu và lúc chạy, file có thể bị thay, gói có thể được cập nhật hoặc tham số có thể đổi. Thành phần thực thi phải kiểm tra lại các thuộc tính đã được dùng để ra quyết định.

Một rủi ro điển hình là **time-of-check to time-of-use**: hệ thống kiểm tra một file, sau đó thực thi một file khác vì file hoặc đường dẫn đã thay đổi trong khoảng giữa hai bước. Việc xác minh và cách hệ điều hành mở, giữ và thực thi đối tượng cần được thiết kế đồng bộ để giảm khoảng trống này; chỉ tính hash ở bước gửi yêu cầu là chưa đủ.

Nếu thuộc tính khác với phạm vi đã duyệt, từ chối lần chạy đó và ghi lý do. Không tự mở rộng sang “cùng tên file” hoặc “phiên bản mới hơn” trừ khi chính sách có chủ đích cho phép và các điều kiện đã được xác định.

### 7.2. Kiểm soát đầu vào và môi trường

Một chương trình được tin cậy vẫn có thể nhận đầu vào khiến nó thực hiện hành vi quá rộng. Ví dụ:

- Tham số trỏ đến script khác do người dùng chỉnh sửa.
- Thư mục làm việc chứa thành phần được chương trình nạp.
- File cấu hình điều khiển đường dẫn đầu ra đặc quyền.
- Tính năng gọi tiện ích ngoài hoặc tạo tiến trình con.
- Đường dẫn hoặc tên tài nguyên được diễn giải khác với dự kiến.

Vì vậy, allowlist một file thực thi không đồng nghĩa đã giới hạn toàn bộ hành vi của nó. Nếu sản phẩm không cưỡng chế được giới hạn mong muốn, cần ghi nhận giới hạn đó và chọn tác vụ đóng gói hoặc đường xử lý phù hợp hơn.

### 7.3. Danh tính thực thi và bí mật

Người yêu cầu được phép thực hiện một tác vụ không có nghĩa họ cần nhận credential của tài khoản thực thi.

Nếu giải pháp sử dụng tài khoản quản trị do vault quản lý, thành phần tin cậy phải xử lý việc truy xuất, sử dụng và luân chuyển credential theo chính sách. Log không được ghi credential hoặc dữ liệu đủ để tái sử dụng quyền.

Cũng cần phân biệt người khởi tạo và danh tính chạy tiến trình. Khi tiến trình chạy dưới tài khoản dịch vụ hoặc tài khoản hệ thống, log vẫn phải truy ngược được về yêu cầu và người khởi tạo.

### 7.4. Kiểm tra điều kiện thay đổi

Trước khi bắt đầu, endpoint cần đánh giá lại những điều kiện mà chính sách yêu cầu còn hiệu lực: quyền chưa bị thu hồi, thiết bị vẫn đủ điều kiện, cửa sổ thời gian chưa đóng và tác vụ vẫn khớp.

Khi quyết định phụ thuộc tín hiệu trực tuyến mà không xác minh được, thiết kế cần có hành vi xác định. Không nên âm thầm bỏ qua điều kiện chỉ vì dịch vụ phê duyệt tạm thời không truy cập được.

## 8. Hết hạn, thu hồi và kết thúc tiến trình

Ba thao tác dưới đây giải quyết các vấn đề khác nhau:

| Thao tác | Hiệu lực dự kiến | Không được mặc định suy ra |
|---|---|---|
| Hết hạn quyền khởi chạy | Chặn khởi chạy mới sau mốc quy định | Tiến trình đang chạy tự động dừng |
| Thu hồi quyền cấp | Vô hiệu hóa khả năng sử dụng tiếp theo theo cơ chế hỗ trợ | Endpoint ngoại tuyến đã nhận được thu hồi |
| Kết thúc tác vụ | Dừng tiến trình hoặc phiên trong phạm vi kiểm soát | Mọi thay đổi hệ thống đã được hoàn tác |

Chính sách có thể yêu cầu dừng tác vụ khi quá giờ, nhưng phải kiểm tra sản phẩm và hệ điều hành hỗ trợ gì, có kiểm soát được tiến trình con hay không, và dừng như vậy có làm hỏng công việc đang thực hiện không.

Đối với tác vụ cài đặt, hết thời gian không làm ứng dụng tự biến mất. Đối với thay đổi cấu hình, thu hồi quyền không tự đưa cấu hình về trạng thái cũ. Phương án hoàn tác là một phần riêng của quản lý thay đổi.

Khi nghi ngờ lạm dụng đang xảy ra, hệ thống cần ghi nhận yêu cầu thu hồi hoặc kết thúc, trạng thái xác nhận từ endpoint và biện pháp tiếp theo nếu không cưỡng chế được. Không đánh dấu “đã xử lý” chỉ vì máy chủ đã phát thông điệp.

## 9. Thiết bị ngoại tuyến và tình huống lỗi

### 9.1. Endpoint không kết nối được dịch vụ cấp quyền

Có hai hướng thiết kế phổ biến:

**Yêu cầu trực tuyến:** không có quyết định hợp lệ thì không nâng quyền. Đây là cách đơn giản hơn để duy trì nhất quán về thu hồi và số lần sử dụng, nhưng có thể ảnh hưởng công việc khi mạng hoặc dịch vụ gián đoạn.

**Ủy quyền ngoại tuyến có giới hạn:** chỉ dành cho tác vụ được chính sách cho phép trước, có thời hạn và bằng chứng xác thực được kiểm tra tại thiết bị. Hướng này cần xử lý thêm chống phát lại, bảo vệ trạng thái cục bộ, đồng hồ, log tồn đọng và đối soát khi kết nối trở lại.

Ủy quyền ngoại tuyến không bảo đảm thu hồi tức thời nếu thiết bị không liên lạc được. Đây là giới hạn cần được chấp nhận có chủ đích, thay vì được che bởi nhãn “revoked” trên bảng điều khiển.

### 9.2. Thành phần thực thi lỗi

Nếu agent không xác minh được chính sách hoặc quyền cấp, không nên giải quyết bằng cách tự cấp admin rộng hơn.

Quy trình hỗ trợ cần cho phép chẩn đoán lỗi, ghi nhận ticket và dùng đường khôi phục đã được kiểm soát nếu thực sự cần thiết. Người dùng không phải tự tìm mật khẩu quản trị để vượt qua lỗi agent.

### 9.3. Lỗi ghi log

Cần xác định tác vụ nào bắt buộc có kênh ghi log hoạt động trước khi chạy, tác vụ nào được phép đệm sự kiện cục bộ, dung lượng đệm tối đa và hành vi khi đệm đầy.

Nếu có đệm, log phải được bảo vệ khỏi sửa đổi trái phép và được chuyển đi khi kết nối trở lại. Mất log hoặc khoảng trống chuỗi sự kiện cần tạo tín hiệu điều tra.

### 9.4. Gửi lặp, nhấn nhiều lần và lỗi phản hồi

Người dùng có thể bấm lại vì giao diện chậm. Dịch vụ cũng có thể gửi lại thông điệp khi không nhận được phản hồi.

Một mã yêu cầu hoặc khóa chống xử lý lặp giúp liên kết những lần thử đó. Tuy nhiên, chống trùng tại cổng API không thay thế cho kiểm soát một lần sử dụng ở nơi thực thi. Cần kiểm thử cả trường hợp gửi lại, đồng thời và mất phản hồi sau khi tiến trình đã khởi chạy.

## 10. Nhật ký và bằng chứng kiểm toán

Một chuỗi bằng chứng hữu ích nối được các sự kiện sau:

~~~text
request.submitted
  -> policy.evaluated
  -> decision.approved hoặc decision.denied
  -> grant.issued
  -> grant.consumed
  -> execution.started
  -> execution.completed hoặc execution.failed
  -> request.closed
~~~

Các nhánh hủy, hết hạn, thu hồi, từ chối tại endpoint và thất bại kết thúc cũng phải được ghi nhận.

Mỗi sự kiện nên có:

- Định danh sự kiện và mã tương quan yêu cầu.
- Thời gian xảy ra cùng thời gian hệ thống tiếp nhận nếu cần phân biệt.
- Người yêu cầu, người hoặc cơ chế quyết định và endpoint.
- Phiên bản chính sách, phạm vi được duyệt và thuộc tính đối tượng thực thi.
- Kết quả, mã nguyên nhân và nguồn phát sự kiện.
- Quan hệ với tiến trình hoặc phiên để hỗ trợ đối soát.

Ví dụ một sự kiện minh họa:

~~~json
{
  "eventType": "execution.started",
  "eventId": "evt-demo-8742",
  "requestId": "ELEV-DEMO-1042",
  "grantId": "grant-demo-337",
  "requesterId": "user-demo-lan",
  "endpointId": "endpoint-demo-017",
  "artifactId": "print-repair-package-v3",
  "policyVersion": "endpoint-maintenance-v12",
  "executionIdentityProfile": "endpoint-maintenance",
  "startedAt": "2026-11-27T09:03:12+07:00",
  "outcome": "started"
}
~~~

Không đưa dòng lệnh chứa bí mật, toàn bộ biến môi trường hoặc nội dung file người dùng vào log một cách mặc định. Cần cân bằng khả năng điều tra với tối thiểu hóa dữ liệu, phân quyền đọc, bảo vệ tính toàn vẹn và thời hạn lưu theo yêu cầu của tổ chức.

Ghi hình phiên, nếu có, là một loại bằng chứng bổ sung. Nó không thay thế log quyết định và không nên được mặc định khả dụng cho mọi kiểu tiến trình đặc quyền.

## 11. Ví dụ xuyên suốt: sửa dịch vụ in theo yêu cầu

### Bối cảnh

Máy endpoint-demo-017 bị lỗi hàng đợi in. Lan có ticket INC-DEMO-421 và được phép hỗ trợ thiết bị này. Tổ chức đã quản lý gói sửa dịch vụ in với tham số cố định, có lịch sử kiểm thử và phương án phục hồi.

### Bước 1: Gửi yêu cầu

Lan chọn tác vụ trong danh mục, chọn endpoint và liên kết ticket. Hệ thống xác nhận gói thực thi cùng các thuộc tính định danh được chính sách yêu cầu.

Lan đề nghị chạy một lần trong 15 phút. Cửa sổ này là thời gian bắt đầu được phép; giới hạn thời gian chạy và xử lý khi vượt giới hạn được khai báo riêng trong hồ sơ tác vụ.

### Bước 2: Đánh giá

Chính sách xác minh Lan thuộc nhóm hỗ trợ đúng phạm vi, endpoint đang được quản lý và tác vụ nằm trong danh mục.

Nếu chính sách chỉ cho phép tự động với nhóm máy thử nghiệm mà endpoint này thuộc máy nghiệp vụ quan trọng, hệ thống chuyển sang người duyệt có thẩm quyền. Không suy diễn quyền tự động từ việc cùng dùng một gói sửa lỗi.

### Bước 3: Phê duyệt

Người duyệt xem tác vụ, endpoint, ảnh hưởng có thể xảy ra, cửa sổ thời gian và ticket. Họ duyệt đúng phạm vi một lần, không cấp cho Lan quyền quản trị thường trực.

Quyết định được gắn với phiên bản bất biến của yêu cầu.

### Bước 4: Khởi chạy

Agent nhận quyền cấp, xác minh ràng buộc và kiểm tra lại gói. Nếu gói đã thay đổi từ lúc được duyệt, lần chạy bị chặn.

Nếu hợp lệ, agent tiêu thụ quyền theo cơ chế chống sử dụng lặp và khởi chạy tác vụ dưới danh tính thực thi đã định nghĩa. Lan không nhận mật khẩu quản trị.

### Bước 5: Kết thúc và đối soát

Hệ thống ghi thời điểm bắt đầu, kết quả tiến trình và kiểm tra vận hành tương ứng. Ticket ghi rõ sự cố in đã được xác nhận khôi phục hay vẫn còn lỗi; mã thoát thành công của công cụ không tự động chứng minh toàn bộ dịch vụ hoạt động đúng.

Lần chạy thứ hai bằng cùng quyền cấp bị từ chối. Nếu cần chạy lại, Lan gửi yêu cầu mới hoặc sử dụng cơ chế thử lại có kiểm soát được định nghĩa sẵn, kèm lý do và liên kết với lần trước.

## 12. Các lỗi thiết kế thường gặp

### “Duyệt một lần để chạy mọi thứ trong 30 phút”

Mô hình này có thể là cấp admin tạm thời, không phải nâng quyền theo tác vụ. Nếu tổ chức chấp nhận nó cho một trường hợp đặc biệt, phải nhận diện đây là phạm vi rộng và áp dụng kiểm soát tương ứng.

### “File nằm trong thư mục tin cậy nên an toàn”

Cần kiểm tra ai có thể ghi vào thư mục, thay file, chỉnh cấu hình hoặc ảnh hưởng đường dẫn. Tên thư mục không chứng minh tính toàn vẹn.

### “Cùng nhà phát hành thì chương trình nào cũng được”

Một nhà phát hành có thể cung cấp cả công cụ quản trị rất mạnh. Tin cậy danh tính nhà phát hành không đồng nghĩa cho phép mọi hành vi của mọi chương trình do họ ký.

### “Đã có ticket nên tự động duyệt”

Ticket chỉ là một phần của bối cảnh. Nó có thể sai thiết bị, đã đóng, không thuộc người yêu cầu hoặc không phê duyệt tác vụ cụ thể.

### “Người duyệt nhấn đồng ý là đủ bằng chứng”

Cần lưu phạm vi họ đã xem, phiên bản yêu cầu, thời điểm và thẩm quyền. Nếu yêu cầu bị thay đổi sau đó, một dòng log “approved” không còn giải thích được lần thực thi.

### “Gỡ nhóm admin là thu hồi toàn bộ quyền ngay”

Phải kiểm tra hiệu lực với token, phiên và tiến trình tồn tại. Có thể cần kết thúc phiên hoặc biện pháp bổ sung tùy cơ chế thực tế.

### “Hết hạn đồng nghĩa hoàn tác”

Hết hạn thường kiểm soát khả năng bắt đầu hoặc tiếp tục thực thi theo chính sách, không phải công cụ khôi phục trạng thái hệ thống.

### “Mọi yêu cầu bị từ chối đều là hành vi xấu”

Từ chối có thể do chọn nhầm tác vụ, gói mới chưa được đưa vào chính sách hoặc chính sách quá chặt. Cần phân biệt lỗi sử dụng, nhu cầu hợp lệ chưa được đáp ứng và tín hiệu lạm dụng.

## 13. Kiểm thử quy trình trước khi áp dụng rộng

Bài kiểm thử nên sử dụng endpoint và tác vụ thử nghiệm được quản lý, không dùng bí mật hoặc tài sản sản xuất.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Người hợp lệ, đúng thiết bị và đúng gói | Thực thi trong phạm vi được duyệt, đủ chuỗi bằng chứng |
| Người khác sử dụng cùng quyền cấp | Bị từ chối và có mã nguyên nhân |
| Dùng quyền cấp trên thiết bị khác | Bị từ chối tại nơi cưỡng chế |
| Thay gói sau khi được duyệt | Không thực thi đối tượng khác phạm vi |
| Thêm tham số hoặc thay tài nguyên đích | Yêu cầu đánh giá lại hoặc từ chối |
| Khởi chạy đồng thời hai lần với quyền một lần | Không có hai lần thực thi thành công trái phạm vi |
| Khởi chạy sau hạn bắt đầu | Bị từ chối, không tự nới thời hạn |
| Thu hồi trước khi thực thi | Lần thực thi bị chặn theo cơ chế đã công bố |
| Thu hồi khi endpoint ngoại tuyến | Thể hiện đúng giới hạn và trạng thái xác nhận |
| Tiến trình sinh tiến trình con | Cưỡng chế hoặc phát hiện theo hồ sơ tác vụ |
| Tác vụ chạy quá giới hạn | Hành vi khớp chính sách, có bằng chứng kết quả xử lý |
| Mất phản hồi sau khi tác vụ đã khởi chạy | Đối soát được, không tự động chạy trùng |
| Log không gửi được | Hành vi khớp chính sách ghi log và phục hồi |
| Yêu cầu bị sửa sau khi duyệt | Không dùng quyết định cũ cho phạm vi mới |

Không chỉ kiểm thử đường thành công trên giao diện. Cần kiểm tra nơi thực thi có thực sự từ chối và sự kiện có đủ để giải thích quyết định.

Với chức năng dừng tác vụ, thử cả tiến trình con và hậu quả vận hành. Một bài thử “đã gửi lệnh terminate” chưa xác minh được tác vụ đã dừng.

## 14. Đo lường để cải thiện chính sách

Theo dõi ít nhất ba mặt: trải nghiệm xử lý yêu cầu, mức thu hẹp quyền và độ đầy đủ của bằng chứng.

Các chỉ số có thể gồm:

- Thời gian chờ quyết định theo loại tác vụ, dùng các phân vị thay vì chỉ trung bình.
- Tỷ lệ yêu cầu bị từ chối kèm nhóm nguyên nhân.
- Tỷ lệ tác vụ nằm trong danh mục có thể tự động xử lý.
- Tỷ lệ cấp quyền rộng theo tài khoản so với cấp quyền theo tác vụ.
- Số quyền hết hạn không sử dụng và số quyền bị sử dụng ngoài phạm vi.
- Tỷ lệ chuỗi thực thi thiếu sự kiện bắt đầu, kết thúc hoặc quyết định.
- Số trường hợp thu hồi hoặc kết thúc chưa được endpoint xác nhận.
- Tần suất sử dụng ngoại lệ và số ngoại lệ quá hạn rà soát.

Phải định nghĩa mẫu số và phạm vi đo. Ví dụ:

~~~text
Tỷ lệ thiếu bằng chứng kết thúc
  = Số lần thực thi quá thời gian đối soát mà chưa có kết quả hợp lệ
    / Tổng số lần thực thi đã đến hạn phải có kết quả trong kỳ
~~~

Một lần chạy vừa bắt đầu chưa đến hạn báo kết quả không nên bị tính như mất bằng chứng.

Không tối ưu riêng tỷ lệ duyệt nhanh. Nếu mục tiêu này khiến người duyệt chấp nhận yêu cầu rộng hoặc bỏ qua kiểm tra, chỉ số đẹp nhưng kiểm soát yếu đi. Ngược lại, tỷ lệ từ chối cao có thể cho thấy danh mục tác vụ không đáp ứng công việc thực tế.

## 15. Bài tập thực hành thiết kế

### Đề bài

Một nhóm hỗ trợ 200 máy trạm đang dùng tài khoản quản trị cục bộ chung để cài công cụ và sửa dịch vụ. Tổ chức muốn thay bằng yêu cầu nâng quyền.

Chọn một tác vụ bảo trì cụ thể và xây dựng:

1. Bản ghi yêu cầu có chủ thể, endpoint, tác vụ, lý do, thời gian và phạm vi.
2. Quy tắc quyết định, người sở hữu và đường xử lý khi cần duyệt thủ công.
3. Ràng buộc quyền cấp và kiểm tra lại tại thời điểm thực thi.
4. Cách xử lý hết hạn, thu hồi, mất kết nối và tác vụ chạy quá lâu.
5. Chuỗi bằng chứng cùng ba bài kiểm thử từ chối quan trọng.

### Gợi ý triển khai

Chọn tác vụ càng rõ càng tốt, ví dụ sửa một dịch vụ đã biết bằng gói bảo trì được quản lý. Tránh bắt đầu với “mở shell để sửa mọi lỗi”.

Giữ phân biệt giữa quyền khởi chạy, thời gian chạy và trạng thái thay đổi sau tác vụ. Chỉ ghi khả năng thu hồi hoặc kết thúc mà cơ chế thực tế có thể cưỡng chế.

### Tiêu chí tự đánh giá

Thiết kế đạt yêu cầu khi người khác có thể trả lời từ dữ liệu và bằng chứng:

- Ai yêu cầu và ai hoặc chính sách nào cho phép?
- Phạm vi nào được duyệt và có bị thay đổi không?
- Đúng tác vụ đó đã chạy trên đúng endpoint chưa?
- Người dùng có nhận được quyền rộng hơn cần thiết không?
- Quyền có thể bị sử dụng lại hay chuyển sang người hoặc máy khác không?
- Hết hạn và thu hồi có hiệu lực thực tế đến đâu?
- Nếu thiếu kết quả, ai chịu trách nhiệm đối soát?
- Nếu tác vụ gây lỗi, có đường xử lý vận hành rõ ràng không?

## 16. Ghi nhớ

Một privilege elevation request có chất lượng là một mô tả quyền có thể kiểm tra và cưỡng chế, không chỉ là biểu mẫu xin admin.

Phê duyệt phải gắn với phạm vi bất biến; endpoint phải kiểm tra lại phạm vi đó trước khi chạy. JIT giới hạn thời điểm và thời hạn, còn quyền vừa đủ giới hạn hành vi. Cần cả hai để giảm quyền tồn tại và giảm khả năng lạm dụng.

Bằng chứng phải nối được người yêu cầu, quyết định, quyền cấp và thực thi. Hết hạn không tự dừng mọi tiến trình; thu hồi không tự hoàn tác thay đổi; một quyết định được duyệt cũng không chứng minh công việc đã hoàn tất.

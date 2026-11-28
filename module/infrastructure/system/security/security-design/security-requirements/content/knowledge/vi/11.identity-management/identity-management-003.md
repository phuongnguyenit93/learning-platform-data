# Deprovisioning account

## 1. Deprovisioning là kết quả thu hồi truy cập, không chỉ là một cờ trạng thái

**Deprovisioning account** là quá trình chấm dứt hoặc thu hẹp khả năng truy cập đã cấp cho một danh tính theo một phạm vi được xác định. Quá trình có thể được kích hoạt khi người dùng rời tổ chức, kết thúc hợp đồng, hết tư cách thành viên, chuyển nhiệm vụ hoặc có quyết định an toàn thông tin.

Một hệ thống không thể kết luận đã deprovision thành công chỉ vì bảng tài khoản có active = false. Người dùng có thể vẫn giữ phiên ứng dụng, access token, API key, chứng thư, quyền trong hệ thống khác hoặc liên kết tải dữ liệu còn hiệu lực.

Trong chương **Quản trị identity**, yêu cầu cần chuyển mục tiêu “người đã hết tư cách không còn truy cập được” thành những điều kiểm chứng được:

- Danh tính và phần quyền nào phải chấm dứt.
- Sự kiện nào có thẩm quyền và thời điểm nào bắt đầu nghĩa vụ thu hồi.
- Những nơi cấp hoặc sử dụng quyền cần được xử lý.
- Thời hạn đóng từng đường truy cập.
- Bằng chứng xác nhận, hành vi khi lỗi và người chịu trách nhiệm.
- Cách giữ, chuyển giao hoặc xử lý dữ liệu sau khi quyền đã bị đóng.

Các thuật ngữ sau có liên quan nhưng không đồng nghĩa:

| Thao tác | Mục đích | Điều chưa được bảo đảm |
| --- | --- | --- |
| Disable account | Không cho sử dụng tài khoản theo cổng kiểm tra trạng thái | Phiên, token hoặc quyền cục bộ có thể vẫn sống |
| Suspend | Tạm dừng trong một phạm vi, có thể chờ điều tra hoặc quyết định | Chưa nhất thiết kết thúc tư cách hoặc xử lý dữ liệu |
| Revoke | Vô hiệu một credential, phiên, grant hoặc quyền cụ thể | Các đường truy cập khác có thể còn |
| Deprovision | Đưa khả năng truy cập trong phạm vi về trạng thái đã yêu cầu và xác minh kết quả | Không tự có nghĩa dữ liệu đã bị xóa |
| Delete | Xóa một bản ghi hoặc dữ liệu theo quy tắc đã duyệt | Không tự thu hồi mọi bí mật hoặc token từng phát hành |
| Offboarding | Quy trình rời tổ chức gồm con người, thiết bị, dữ liệu và truy cập | Deprovisioning chỉ là một phần của quy trình rộng hơn |

Bài này tập trung vào đặc tả yêu cầu bảo mật của deprovisioning. Các thời hạn và mô hình trong ví dụ là quyết định minh họa để học cách viết yêu cầu, không phải quy tắc mặc định cho mọi tổ chức.

## 2. Bắt đầu từ tài sản và mô hình đe dọa

Xét một nền tảng học tập có nhiều tenant, tài khoản học viên, giảng viên, nhân viên hỗ trợ và tài khoản dịch vụ. Cùng một người có thể đồng thời là nhân viên của một tenant và học viên của một chương trình khác.

Nguồn quản lý tư cách gửi sự kiện thay đổi; dịch vụ identity phối hợp thu hồi ở hệ thống định danh, ứng dụng, phiên, quyền cục bộ và các credential được cấp thêm.

| Mã rủi ro | Tình huống | Tác động | Nhóm yêu cầu cần có |
| --- | --- | --- | --- |
| R-DP-01 | Tư cách đã chấm dứt nhưng đăng nhập vẫn được cấp | Phát sinh truy cập mới | Cổng cấp phiên và credential kiểm tra trạng thái hiệu lực |
| R-DP-02 | Tài khoản bị khóa nhưng phiên/token cũ còn dùng được | Tiếp tục đọc hoặc sửa dữ liệu | Thu hồi tại nơi sử dụng quyền |
| R-DP-03 | Có quyền cục bộ hoặc credential không nằm trong IdP | Đi vòng qua hệ thống định danh trung tâm | Kiểm kê và xử lý đầy đủ bề mặt truy cập |
| R-DP-04 | Gán nhầm người hoặc phạm vi tenant | Khóa người hợp lệ hoặc để sót quyền cần thu hồi | Định danh ổn định và phạm vi rõ ràng |
| R-DP-05 | Sự kiện cũ đến sau hoặc đồng bộ tạo lại tài khoản | Quyền đã đóng bị khôi phục | Phiên bản sự kiện, thứ tự hiệu lực và chặn phục hồi ngoài ý muốn |
| R-DP-06 | Connector lỗi nhưng quy trình báo hoàn tất | Mất bằng chứng và còn đường truy cập | Xác minh kết quả, retry và trạng thái không xác định |
| R-DP-07 | Người rời tổ chức biết secret dùng chung | Tiếp tục dùng danh tính khác | Đánh giá mức lộ, thay secret hoặc chặn đường sử dụng |
| R-DP-08 | Xóa tài khoản làm mất quyền sở hữu và audit | Mất dữ liệu hoặc đứt dấu vết trách nhiệm | Chuyển giao dữ liệu và giữ tham chiếu danh tính |
| R-DP-09 | Tác vụ, stream hoặc liên kết tiếp tục chạy | Truy cập kéo dài sau thời hạn | Điểm kiểm tra cho hoạt động đang diễn ra |

Deprovisioning không lấy lại được dữ liệu mà một người đã tải hợp lệ trước đó. Yêu cầu phải phân biệt ngăn truy cập mới, dừng hoạt động còn sống và xử lý các bản dữ liệu do hệ thống còn kiểm soát. Không hứa thu hồi mọi bản sao ngoài phạm vi kỹ thuật.

## 3. Xác định đúng danh tính và phạm vi phải thu hồi

### 3.1. Dùng định danh ổn định thay vì tên hoặc email

Một yêu cầu thu hồi cần gắn với ID chủ thể ổn định trong đúng identity realm, tức không gian danh tính được quản lý. Email, username, tên hiển thị và mã nhân sự có thể đổi hoặc được cấp lại; không được dùng so khớp gần đúng để tự chọn tài khoản cần khóa.

Hồ sơ ánh xạ tối thiểu nên xác định:

| Dữ kiện | Ý nghĩa |
| --- | --- |
| Subject ID và realm | Danh tính nội bộ cần xử lý |
| Source identity reference | Bản ghi của nguồn có thẩm quyền |
| Membership hoặc assignment ID | Tư cách hay nhiệm vụ cụ thể bị chấm dứt |
| Tenant và phạm vi tài nguyên | Đơn vị và tập quyền bị ảnh hưởng |
| Account references | Tài khoản tương ứng tại từng hệ thống đích |
| Lifecycle generation | Thế hệ vòng đời để phân biệt các lần cấp lại hợp lệ |
| Security holds | Các lệnh chặn đang có hiệu lực từ quy trình an toàn thông tin |

Nếu ánh xạ không rõ, quy trình phải báo lỗi điều tra hoặc áp dụng biện pháp bảo vệ được phê duyệt theo rủi ro; không tự chọn tài khoản có email gần giống rồi báo thành công.

### 3.2. Chấm dứt một membership không mặc nhiên xóa toàn bộ identity

Ví dụ, một giảng viên hết hợp đồng ở tenant A nhưng vẫn là học viên ở tenant B. Yêu cầu có thể là:

> Thu hồi các role, phân công, phiên mang phạm vi nhân sự và credential được cấp cho tư cách ở tenant A. Giữ phần truy cập học viên ở tenant B nếu tư cách đó còn hợp lệ và không có lệnh chặn toàn cục.

Việc thực thi cần xét token hoặc phiên chứa nhiều phạm vi. Có thể phải thu hồi phiên cũ rồi cho đăng nhập lại với quyền còn hợp lệ; không để token đa phạm vi giữ quyền A chỉ vì người dùng vẫn có quyền B.

Nếu quyết định yêu cầu đình chỉ toàn danh tính vì sự cố, phạm vi khác với chấm dứt một membership. Sự kiện phải biểu đạt được khác biệt này. Một nguồn quản lý nhân sự không được tự xóa quyền học viên độc lập chỉ vì hai tư cách cùng thuộc một người.

### 3.3. Quan hệ với tài khoản dịch vụ

Người tạo, người sở hữu và người biết credential của một tài khoản dịch vụ có thể là ba bên khác nhau. Không tự vô hiệu mọi tài khoản dịch vụ do người rời tổ chức từng tạo, vì có thể làm gián đoạn hệ thống không nằm trong phạm vi chấm dứt.

Thay vào đó, cần xác định chủ sở hữu còn hợp lệ, ai đã biết secret và các quyền cần chuyển giao. Đổi tên người sở hữu không làm secret cũ mất tác dụng. Nếu người đã hết quyền biết một bí mật còn dùng được, phải đánh giá và đóng đường đó bằng thay secret, giới hạn sử dụng hoặc biện pháp có hiệu lực tương ứng.

Credential cá nhân như API key do người dùng tạo cho mình vẫn thuộc phạm vi thu hồi cá nhân, trừ khi có quyết định chuyển đổi sang danh tính dịch vụ với quyền và chủ sở hữu được duyệt riêng.

## 4. Đặc tả sự kiện kích hoạt và thẩm quyền

Một sự kiện minh họa:

~~~json
{
  "eventId": "event-demo-1042",
  "source": "membership-registry-demo",
  "sourceRevision": 18,
  "subjectRef": "subject-demo-01",
  "realmRef": "realm-demo",
  "membershipRef": "membership-demo-a",
  "scope": {
    "tenantRef": "tenant-demo-a",
    "membershipOnly": true
  },
  "requestedState": "DISABLED",
  "effectiveAt": "2030-06-01T08:00:00Z",
  "occurredAt": "2030-05-31T09:00:00Z",
  "reasonCode": "MEMBERSHIP_ENDED"
}
~~~

Ngày và định danh chỉ là dữ liệu giả. Không có bí mật xác thực trong sự kiện. Hợp đồng cần quy định nguồn được phép thay đổi loại tư cách nào, cách xác minh nguồn, kiểm tra schema, phạm vi và chống sửa thông điệp.

Các trường quan trọng gồm thời điểm có hiệu lực, revision của nguồn, lý do, phạm vi và bằng chứng phê duyệt nếu quy trình yêu cầu. Một email tự do hoặc request do chính tài khoản bị xử lý tự gửi không thay thế sự kiện có thẩm quyền.

Với thay đổi theo lịch, hệ thống phải lưu kế hoạch bền vững và kích hoạt đúng mốc dù tiến trình khởi động lại. Nếu có quyết định hủy lịch hợp lệ trước mốc, phải ghi phiên bản mới và kiểm tra các lệnh chặn độc lập; không chỉ xóa một thông điệp trong hàng đợi.

### 4.1. Xác định mốc bắt đầu đo

Trong tình huống mẫu, t0 là thời điểm tư cách phải mất hiệu lực theo nguồn có thẩm quyền. Với quyết định khẩn cấp có hiệu lực ngay, t0 là thời điểm quyết định được commit tại nguồn đó.

Các mốc bổ sung:

~~~text
t0        = thời điểm nghĩa vụ thu hồi có hiệu lực
tReceive  = thời điểm hệ thống điều phối nhận sự kiện
tGate     = thời điểm cổng cấp quyền mới đã bị chặn
tClosed_i = thời điểm đường truy cập i được xác nhận đã đóng
tClosed   = thời điểm mọi đường trong phạm vi đạt trạng thái yêu cầu
~~~

Sự kiện đến muộn không được đặt lại t0 thành tReceive để làm số đo đẹp hơn. Độ trễ nhận sự kiện là một phần cần theo dõi của toàn chuỗi. Nếu nguồn gửi một thay đổi hồi tố, báo rõ độ trễ và trường hợp vi phạm; không che khoảng truy cập đã tồn tại.

Đồng hồ và timestamp phải có quy ước UTC và chất lượng đồng bộ phù hợp. Revision dùng cho thứ tự thay đổi của một nguồn; timestamp hiển thị không tự giải quyết xung đột giữa nhiều nguồn.

## 5. Chuyển mục tiêu thành thời hạn và tiêu chí hoàn tất

Hồ sơ thời hạn minh họa của nền tảng:

| Phạm vi | Mục tiêu từ t0 | Điều phải chứng minh |
| --- | --- | --- |
| Cấp phiên hoặc credential mới dựa trên tư cách đã hết | Không quá 60 giây | Đăng nhập, refresh và cấp credential không tạo quyền mới của tư cách đó |
| Truy cập thông thường đã tồn tại | Không quá 5 phút | Phiên, token và quyền cục bộ không còn cho thao tác thuộc phạm vi bị thu hồi |
| Truy cập đặc quyền hoặc quyết định khẩn cấp | Không quá 60 giây | Mọi đường đặc quyền trong phạm vi mất tác dụng trong thời hạn |
| Thông tin tiến độ | Khi từng bước đổi trạng thái | Có kết quả theo từng hệ thống, không chỉ một nhãn thành công chung |
| Chuyển giao dữ liệu | Theo hạn nghiệp vụ được duyệt riêng | Không dùng việc chờ chuyển giao làm lý do giữ quyền của người đã hết tư cách |

Đây là mục tiêu thiết kế cần được thẩm định, chưa phải kết quả đo. Nếu hệ thống đích không có khả năng đáp ứng, phải thay kiến trúc, bổ sung điểm cưỡng chế hoặc ghi nhận khoảng trống; không tự tuyên bố hoàn tất.

Các đường dùng secret chung cũng nằm trong thời hạn đóng truy cập tương ứng. Nếu việc thay secret mất lâu hơn nhưng không có biện pháp ngăn người đã hết quyền sử dụng, mục tiêu thu hồi chưa đạt. Một kế hoạch thay khóa trong tương lai không phải bằng chứng rằng đường truy cập đã đóng.

Hai loại bằng chứng cần phân biệt:

- **Lệnh đã được gửi hoặc nhận:** connector nhận request, hàng đợi đã có tác vụ hoặc API trả mã chấp nhận.
- **Trạng thái hiệu lực đã được xác nhận:** hệ thống đích đã thực thi điều kiện chặn và có bằng chứng phù hợp tại nơi quyết định hoặc sử dụng quyền.

Thời điểm đóng cuối cùng không phải thời điểm gửi lệnh cuối cùng. Chỉ đo các bước thành công sẽ bỏ sót chính những đường nguy hiểm đang lỗi; trạng thái chưa biết phải vẫn xuất hiện trong báo cáo.

Với mục tiêu tối đa 5 phút, trung bình hoặc p95 dưới 5 phút không chứng minh mọi trường hợp đã đạt. Cần báo số trường hợp quá hạn, thời gian của chúng và những trường hợp chưa xác định được thời điểm đóng.

## 6. Kiểm kê bề mặt truy cập cần deprovision

| Bề mặt | Hành động cần xét | Sai lầm dễ gặp |
| --- | --- | --- |
| Hệ thống định danh trung tâm | Đóng tư cách, ngăn cấp bằng chứng hoặc phiên mới trong phạm vi | Chỉ khóa IdP rồi coi mọi ứng dụng đã đăng xuất |
| Tài khoản cục bộ của ứng dụng | Vô hiệu đường đăng nhập và quyền nội bộ | Quên lối đăng nhập dự phòng |
| Phiên trình duyệt và di động | Vô hiệu phiên hoặc phiên bản quyền tại nơi sử dụng | Chỉ xóa cookie trên một thiết bị |
| Refresh token và grant | Chặn đổi token, thu hồi phạm vi được cấp | Chặn refresh nhưng bỏ access token đã phát hành |
| Access token | Dừng chấp nhận trước thời hạn bằng cơ chế phù hợp | Chỉ kiểm tra chữ ký và bỏ trạng thái thu hồi |
| API key, personal token | Vô hiệu tại bộ xác minh và mọi replica/cache liên quan | Xóa dòng quản lý nhưng cache vẫn nhận key |
| Khóa SSH hoặc chứng thư | Thu hồi hoặc chặn quyền sử dụng trong các đích tương ứng | Coi xóa public key ở một máy là đủ |
| Quyền cloud hoặc console quản trị | Thu hồi session và quyền ủy nhiệm còn hiệu lực | Chỉ bỏ một group ở nguồn |
| MFA và bằng chứng phục hồi | Ngăn dùng để tái kích hoạt hoặc lấy credential mới | Reset mật khẩu trở thành đường phục hồi tư cách đã đóng |
| Quyền chia sẻ và ủy quyền | Hủy grant, liên kết hoặc khả năng thực hiện thay trong phạm vi | Chỉ thu hồi role trực tiếp |
| Job, stream, kết nối dài | Hủy hoặc đánh giá lại tại điểm kiểm tra đã định nghĩa | Chỉ chặn request mới |
| File và đường tải do hệ thống kiểm soát | Chặn tải tiếp theo theo cam kết | Liên kết không kiểm tra lại vẫn dùng được |
| Secret mà người dùng biết | Thay, thu hẹp hoặc chặn sử dụng theo đánh giá | Chuyển owner nhưng giữ nguyên bí mật |

Không phải hệ thống nào cũng có mọi bề mặt trong bảng. Yêu cầu là có danh mục có chủ sở hữu và chứng minh đường nào tồn tại, đường nào không thuộc phạm vi. “Không thấy trong màn hình quản trị” không phải bằng chứng không tồn tại.

Đối với token tự chứa như JWT, chữ ký hợp lệ và thời hạn chưa hết có thể khiến bộ nhận vẫn chấp nhận sau khi tài khoản đã bị khóa. Muốn đáp ứng thời hạn thu hồi, cần cơ chế như kiểm tra trạng thái/phiên bản quyền, danh sách thu hồi hoặc thời hạn token đủ ngắn với các điều kiện kiểm tra thực tế.

Không mặc định logout đồng nghĩa thu hồi mọi credential. Logout trên thiết bị, logout tại hệ thống định danh và vô hiệu phiên ứng dụng là các tác động cần được xác định riêng.

## 7. Kiến trúc điều phối và trạng thái cần quan sát

Một kiến trúc minh họa:

~~~mermaid
flowchart LR
    S["Nguồn tư cách / quyết định an toàn thông tin"] --> O["Điều phối: kiểm tra phạm vi và revision"]
    O --> J["Kế hoạch và tác vụ bền vững"]
    J --> I["IdP và cổng cấp quyền"]
    J --> A["Ứng dụng và quyền cục bộ"]
    J --> T["Phiên, token, key và grant"]
    J --> D["Dữ liệu, job và chủ sở hữu"]
    I --> V["Xác minh kết quả theo đích"]
    A --> V
    T --> V
    D --> V
    V --> R["Tiến độ, cảnh báo và audit"]
~~~

Không bắt buộc dùng một sản phẩm điều phối cụ thể. Dù dùng workflow engine hay mã ứng dụng, trạng thái phải bền vững và đủ để khôi phục sau lỗi.

### 7.1. Tách trạng thái tài khoản khỏi trạng thái quy trình

Trạng thái tài khoản tại điểm cấp quyền trả lời có được sử dụng tư cách đó hay không. Trạng thái quy trình trả lời đã làm và xác minh đến đâu. Không cho phép quy trình còn “đang chuyển giao dữ liệu” giữ tài khoản hoạt động nếu thời hạn thu hồi đã đến.

Một luồng trạng thái mẫu:

~~~text
RECEIVED -> VALIDATED -> SCHEDULED hoặc REVOKING
REVOKING -> VERIFYING -> ACCESS_CLOSED
ACCESS_CLOSED -> DATA_PENDING -> COMPLETED
~~~

Lỗi hoặc thiếu bằng chứng có thể tạo trạng thái ESCALATED hoặc ACCESS_PARTIAL, kèm các bước đang chặn hoàn tất. Chúng không phải cách diễn đạt khác của thành công.

Mỗi hệ thống đích có trạng thái riêng như PENDING, RUNNING, RETRYABLE_ERROR, UNKNOWN, VERIFIED. Mã chấp nhận request không đủ để chuyển ngay sang VERIFIED.

ACCESS_CLOSED chỉ được dùng khi mọi đường truy cập trong phạm vi đã đạt điều kiện đóng. COMPLETED còn yêu cầu các nghĩa vụ dữ liệu và bàn giao thuộc quy trình đã hoàn tất. Nếu dự án chỉ theo dõi phần truy cập, tên và tiêu chí kết thúc phải nói rõ phạm vi đó.

### 7.2. Đừng gắn khôi phục quyền vào lỗi dọn dẹp

Nếu chuyển dữ liệu hoặc gửi thông báo thất bại, không tự bật lại quyền để “rollback toàn bộ quy trình”. Các bước thu hồi đã có hiệu lực cần được giữ. Khôi phục quyền là quyết định bảo mật riêng, không phải thao tác bù mặc định cho lỗi của một bước sau.

Tác vụ phải có giới hạn retry, backoff và cảnh báo trước khi hết hạn. Hàng đợi lỗi cần có chủ sở hữu xử lý và khả năng truy vết; đưa tác vụ vào đó không làm nghĩa vụ thu hồi biến mất.

## 8. Sự kiện trùng lặp, đến muộn và tái tạo tài khoản

### 8.1. Idempotency phải gắn với tác động

Thông điệp có thể được gửi lại sau timeout. Hệ thống cần nhận diện event ID và trạng thái tác vụ để một quyết định không tạo nhiều tác động ngoài ý muốn. Gửi lại lệnh disable đã đạt trạng thái mong muốn có thể được coi là thành công sau khi xác nhận đúng tài khoản và thế hệ vòng đời.

Tuy nhiên, idempotency không chỉ là bỏ qua mọi event ID từng thấy. Nếu tác vụ cũ chưa hoàn tất, lần xử lý lại phải tiếp tục hoặc kiểm tra kết quả, thay vì đánh dấu thành công vì sự kiện “đã nhận”.

Một khóa tác vụ có thể bao gồm quyết định, hệ thống đích, account reference và lifecycle generation. Không để retry của một lần rời tổ chức tác động nhầm tài khoản đã được cấp lại theo một quyết định mới.

### 8.2. Revision của từng nguồn và ưu tiên giữa các nguồn

Ví dụ, nguồn gửi revision 18 để đóng membership, rồi một revision 17 còn nằm trong hàng đợi đến sau với trạng thái ACTIVE. Revision cũ không được phục hồi quyền.

Revision chỉ so sánh được trong hợp đồng của cùng nguồn và cùng đối tượng. Số 20 từ sổ học viên không mặc nhiên có ưu tiên hơn số 19 từ quy trình an toàn thông tin. Các nguồn cần có phạm vi thẩm quyền và quy tắc kết hợp rõ ràng.

Một lệnh chặn toàn cục đang có hiệu lực không được gỡ chỉ vì nguồn nhân sự gửi bản cập nhật hồ sơ mới hơn. Chỉ quyết định đúng thẩm quyền mới được kết thúc lệnh chặn đó.

### 8.3. Chặn tạo lại từ đồng bộ cũ

Sau khi tài khoản bị xóa hoặc đóng, một tác vụ đồng bộ có thể nhìn thấy bản ghi nguồn cũ rồi tạo lại. Hệ thống cần giữ trạng thái mong muốn hoặc dấu vết vô hiệu hóa đủ để ngăn điều đó. Dấu vết tối thiểu có thể là một tombstone: bản ghi cho biết danh tính, thế hệ và quyết định đã chấm dứt.

Không tái sử dụng một định danh theo cách khiến credential hoặc liên kết của người cũ trỏ vào người mới. Khi một người được tiếp nhận lại hợp lệ, quy trình phải xác định rõ có dùng identity cũ hay không và tạo thế hệ quyền mới như thế nào.

Việc tái cấp hợp lệ không làm credential cũ sống lại. Các token, key và bằng chứng phục hồi thuộc thế hệ đã chấm dứt phải tiếp tục vô hiệu.

## 9. Đóng cửa sổ cạnh tranh ở phiên, token và hoạt động đang chạy

### 9.1. Cạnh tranh giữa đăng nhập và disable

Một tình huống cần kiểm thử:

~~~text
A: đọc tài khoản còn ACTIVE
B: commit quyết định disable và tăng phiên bản trạng thái
A: hoàn tất xác thực rồi tìm cách cấp phiên
~~~

Nếu A chỉ dựa vào lần đọc ban đầu, hệ thống có thể cấp thêm phiên sau khi đã ghi trạng thái đóng. Cổng cấp phiên cần kiểm tra trạng thái và phiên bản tại điểm ghi nhận cấp quyền, bằng giao dịch, điều kiện so sánh phiên bản hoặc cơ chế điều phối có tính nhất quán phù hợp.

Một mô hình có thể dùng authEpoch, tức phiên bản hiệu lực của trạng thái xác thực. Khi deprovision, tăng epoch và ghi trạng thái không được cấp quyền. Phiên hoặc token gắn với epoch cũ không còn được chấp nhận theo chính sách.

Mô hình epoch chỉ có tác dụng khi mọi bên liên quan kiểm tra đúng. Một dịch vụ chỉ kiểm tra chữ ký token mà không biết epoch mới vẫn có thể chấp nhận quyền cũ. Cache epoch và đường làm mới phải nằm trong thời hạn thu hồi đã cam kết.

Đối với thu hồi một membership, có thể cần phiên bản theo phạm vi hoặc cấp lại phiên với quyền còn hợp lệ. Tăng một epoch toàn cục là lựa chọn có tác động rộng, cần được quyết định rõ thay vì vô tình khóa mọi tư cách.

### 9.2. Thu hồi refresh không đồng nghĩa thu hồi access

Chặn refresh làm đối phương không lấy token mới qua grant đó, nhưng access token hiện tại vẫn có thể dùng đến khi bộ nhận dừng chấp nhận. Thời hạn thu hồi phải bao phủ cả hai.

Cơ chế xử lý token cần nêu:

- Những bên sử dụng token và phạm vi quyền tương ứng.
- Thời gian token sống và sai lệch đồng hồ được phép.
- Nơi kiểm tra trạng thái thu hồi hoặc version.
- Thời hạn cache và hành vi khi nguồn trạng thái lỗi.
- Bằng chứng token cũ không còn tạo tác động trước mốc cam kết.

Nếu dựa vào hết hạn tự nhiên, thời hạn lớn nhất và sai lệch kiểm tra phải thực sự nằm trong mục tiêu thu hồi. Không dùng thời hạn trung bình của token làm bằng chứng.

### 9.3. Request, kết nối dài và job đã bắt đầu

Một request đang ghi dữ liệu cần được liên kết với mô hình quyền tại thời điểm commit. Không thể bảo đảm dừng ngay mọi phép tính đang chạy chỉ bằng thay cờ tài khoản; yêu cầu phải xác định điểm kiểm tra, cách hủy và tác động đã hoàn tất.

Stream hoặc kết nối dài cần kiểm tra lại trạng thái hoặc có cơ chế đóng theo deadline. Chỉ chặn bước mở kết nối mới để lại một đường truy cập còn sống.

Job nền do người dùng yêu cầu cần được hủy, thu hẹp hoặc chuyển sang danh tính dịch vụ có phạm vi và người chịu trách nhiệm được duyệt. Không để job giữ vô hạn snapshot quyền của người đã hết tư cách.

Quyết định chuyển giao một tác vụ không được dùng như thủ thuật để bỏ qua thu hồi. Phải chứng minh ai còn được nhận kết quả và các quyền nào thật sự cần cho tác vụ tiếp tục.

## 10. Xử lý lỗi phụ thuộc và xác minh hiệu lực

Một hệ thống phân tán có thể gửi lệnh thành công nhưng chưa biết kết quả do mất kết nối. UNKNOWN là trạng thái cần giải quyết, không phải thành công và cũng không nhất thiết là chưa có tác động.

| Tình huống | Hành vi cần đặc tả | Bằng chứng cần có |
| --- | --- | --- |
| API đích timeout sau lệnh thu hồi | Tra cứu trạng thái hoặc retry an toàn theo khóa tác vụ | Xác định hiệu lực thực, không chỉ mã lỗi của lần gọi |
| Hệ thống đích không hoạt động | Giữ nghĩa vụ chưa hoàn tất, cảnh báo và thử lại | Có đường chặn thay thế nếu tuyên bố đã đóng truy cập |
| Kho trạng thái thu hồi không truy cập được | Bên sử dụng quyền áp dụng hành vi đã duyệt, không tự bỏ kiểm tra | Không vượt deadline bởi nhánh cho qua |
| Replica hoặc cache còn trạng thái cũ | Cập nhật hoặc hết hạn trong ngân sách | Đo qua từng điểm sử dụng, không chỉ nguồn |
| Tiến trình điều phối chết | Khôi phục kế hoạch bền vững và tiếp tục tác vụ | Không mất bước, không bật lại trạng thái ACTIVE |
| Connector lỗi credential quản trị | Báo lỗi có chủ sở hữu và xử lý trước hạn | Không giấu lỗi dưới nhãn đã gửi lệnh |
| Job dọn dữ liệu lỗi sau ACCESS_CLOSED | Tiếp tục khóa truy cập, xử lý nghĩa vụ dữ liệu riêng | Không khôi phục quyền để sửa lỗi dọn dẹp |

Với luồng đặc quyền của tình huống mẫu, khi không xác nhận được trạng thái hiệu lực trong giới hạn tin cậy, bên sử dụng không được tiếp tục cấp quyền dựa vào trạng thái cũ. Chi phí khả dụng của lựa chọn này phải được tính trong thiết kế và năng lực phụ thuộc.

Một hệ thống khác có thể có chế độ suy giảm được duyệt, nhưng cần giới hạn cụ thể và chứng minh nó không mâu thuẫn mục tiêu thu hồi. Câu “fail open để tránh gián đoạn” không cho biết rủi ro nào đã được chấp nhận và trong bao lâu.

### 10.1. Xác minh theo mức bảo đảm cần thiết

Bằng chứng có thể gồm trạng thái có thẩm quyền tại hệ thống đích, phiên bản thu hồi, xác nhận credential không còn được bộ nhận chấp nhận và phép kiểm tra có kiểm soát bằng tài khoản thử.

Không yêu cầu lưu mật khẩu hoặc thu thập token thật của người rời tổ chức để thử đăng nhập. Thiết kế cơ chế xác minh không làm phát sinh kho bí mật mới. Các ca kiểm thử đầu cuối dùng danh tính và credential tổng hợp trong môi trường được kiểm soát.

Nếu hệ thống đích không có phản hồi trạng thái đủ tin cậy, có thể cần điểm kiểm soát khác như cô lập đường truy cập. Muốn dùng biện pháp đó làm bằng chứng đóng, phải bao phủ các đường đi vòng có liên quan. Một máy chủ tạm offline chưa chứng minh credential đã bị thu hồi và sẽ không có hiệu lực khi máy khởi động lại.

## 11. Dữ liệu, quyền sở hữu và khôi phục do sai sót

### 11.1. Tách thu hồi truy cập khỏi xử lý dữ liệu

Dữ liệu có thể cần được giữ, chuyển giao, hạn chế tiếp cận hoặc xóa theo chính sách đã duyệt của chủ sở hữu dữ liệu. Không dùng deprovisioning như một lệnh xóa mọi nội dung mà tài khoản từng tạo.

Các nghĩa vụ nên chỉ rõ:

| Đối tượng | Câu hỏi cần quyết định |
| --- | --- |
| Hồ sơ học tập hoặc kết quả | Ai tiếp tục quản lý và ai được xem? |
| Tài liệu, báo cáo, dashboard | Chuyển chủ sở hữu cho ai, trong tenant nào? |
| Job định kỳ và cấu hình tích hợp | Dừng hay chuyển sang danh tính dịch vụ được quản lý? |
| Secret và khóa do tài khoản biết | Vô hiệu hoặc thay bằng cách nào? |
| Audit và tham chiếu tác giả | Giữ định danh nào để còn giải thích được hành vi? |
| Bản sao lưu | Khi phục hồi có giữ trạng thái thu hồi và áp lại quyết định mới hơn không? |

Xóa bản ghi danh tính không được làm mất khả năng xác định người đã thực hiện hành động trong audit. Có thể giữ tham chiếu tối thiểu hoặc bản ghi vô hiệu hóa theo chính sách dữ liệu, với quyền đọc và thời hạn tương ứng.

Khôi phục bản sao lưu có thể đưa trạng thái ACTIVE, group cũ hoặc key đã thu hồi trở lại. Quy trình phục hồi phải áp lại các quyết định và thế hệ hiện hành trước khi mở phục vụ. Kiểm thử deprovisioning cần bao gồm tình huống này.

### 11.2. Khôi phục tài khoản bị xử lý nhầm

Một yêu cầu khôi phục phải có thẩm quyền, phạm vi, lý do và bằng chứng độc lập với các credential đã bị thu hồi. Tài khoản bị chặn không được tự mở khóa thông qua một luồng reset mật khẩu thông thường.

Khôi phục không nên đồng nghĩa phát lại toàn bộ role, group, API key và token cũ từ lịch sử. Cần đánh giá quyền còn hợp lệ hiện tại, lệnh chặn độc lập, cấp credential mới khi cần và giữ vô hiệu các bí mật của thế hệ cũ.

Việc gỡ một quyết định đóng membership không tự gỡ lệnh chặn an toàn thông tin toàn cục. Quy trình cần lưu rõ quyết định nào được hủy và quyết định nào còn hiệu lực.

## 12. Audit và số đo phục vụ điều phối

Một sự kiện tiến độ minh họa:

~~~json
{
  "eventType": "DEPROVISION_TARGET_VERIFIED",
  "decisionRef": "decision-demo-01",
  "subjectRef": "subject-demo-01",
  "scopeRef": "membership-demo-a",
  "targetRef": "learning-api-demo",
  "lifecycleGeneration": 4,
  "requiredState": "ACCESS_DISABLED",
  "verificationType": "AUTHORITATIVE_STATE_AND_VERSION",
  "policyVersion": "deprovision-demo-v1",
  "result": "VERIFIED"
}
~~~

Thực tế cần thêm các mốc thời gian, ID tác vụ, nguồn sự kiện và tham chiếu bằng chứng. Không ghi password, token, API key, mã phục hồi hoặc body nguyên vẹn của phản hồi nhạy cảm vào audit.

Quyền đọc audit và bằng chứng phải có phạm vi. Audit nên đủ nối quyết định với từng tác động và người vận hành, nhưng không thu thập hồ sơ cá nhân vượt mục đích.

Các số đo cần bao phủ:

- Độ trễ nhận sự kiện so với t0, gồm cả sự kiện đến muộn.
- Thời gian ngăn cấp mới và thời gian đóng từng đường truy cập.
- Số đích chưa xác minh, lỗi retry, trạng thái UNKNOWN và quá hạn.
- Tỷ lệ tài khoản có đầy đủ ánh xạ và chủ sở hữu hệ thống đích.
- Số lần đồng bộ tìm cách tái tạo hoặc khôi phục quyền đã đóng.
- Số trường hợp khôi phục có phê duyệt và credential cũ vẫn bị từ chối.
- Chênh lệch giữa trạng thái mong muốn và trạng thái quan sát khi đối soát.

Đối soát định kỳ là lớp phát hiện bổ sung cho sự kiện, giúp tìm tác vụ thất lạc hoặc quyền cục bộ được cấp ngoài luồng. Chu kỳ đối soát không thay thế deadline nếu nó dài hơn thời hạn thu hồi.

Ngoại lệ cần có chủ sở hữu rủi ro, lý do, biện pháp bảo vệ, thời hạn và kế hoạch đóng. Chấp nhận một ngoại lệ không làm đường truy cập còn sống biến thành đã thu hồi; báo cáo phải giữ nguyên trạng thái và ảnh hưởng tới mục tiêu.

## 13. Đặc tả yêu cầu và truy vết tới kiến trúc

Ví dụ yêu cầu hoàn chỉnh cho quyền truy cập đã phát hành:

| Trường | Nội dung mẫu |
| --- | --- |
| ID | SR-DEPROV-04 |
| Mục tiêu | Chặn sử dụng quyền thuộc membership đã chấm dứt |
| Rủi ro | R-DP-02, R-DP-03, R-DP-09 |
| Phạm vi | Phiên, token, key, grant và kết nối còn sống của membership tại các đích được kiểm kê |
| Nghĩa vụ | Mọi đường thông thường mất hiệu lực trong 5 phút từ t0; đường đặc quyền hoặc khẩn cấp trong 60 giây |
| Điểm thực thi | Cổng sử dụng quyền tại ứng dụng, API và hệ thống đích, không chỉ IdP |
| Phụ thuộc | Trạng thái identity, mapping tài khoản, version/epoch, cache, connector |
| Hành vi lỗi | Không đánh dấu đóng khi thiếu bằng chứng; không bỏ kiểm tra trạng thái ngoài hợp đồng tin cậy |
| Chủ sở hữu | Nhóm identity điều phối; từng chủ hệ thống đích thực thi; vận hành xử lý lỗi; an toàn thông tin duyệt mức bảo đảm |
| Tiêu chí nghiệm thu | Credential và phiên thử cũ bị từ chối qua mọi đích trong thời hạn, gồm lỗi và cache nóng |
| Giới hạn | Không thu hồi dữ liệu đã được tải trước đó ngoài vùng kiểm soát |
| Ngoại lệ | Ghi nhận rõ truy cập còn tồn tại; không tự đổi nhãn thành VERIFIED |

Ma trận truy vết rút gọn:

| ID | Nghĩa vụ chính | Rủi ro và bằng chứng |
| --- | --- | --- |
| SR-DEPROV-01 | Ánh xạ đúng subject, realm, membership và generation | R-DP-04; tài khoản trùng tên, email đổi, nhiều tư cách |
| SR-DEPROV-02 | Chỉ nhận quyết định đúng thẩm quyền, phạm vi và revision | R-DP-04, R-DP-05; sự kiện giả, cũ, trùng và xung đột nguồn |
| SR-DEPROV-03 | Ngăn cấp mới trong 60 giây từ t0 | R-DP-01; đăng nhập, refresh, reset và cạnh tranh cấp phiên |
| SR-DEPROV-04 | Thu hồi quyền còn sống theo thời hạn | R-DP-02, R-DP-09; token cũ, phiên đa thiết bị, stream và job |
| SR-DEPROV-05 | Kiểm kê quyền cục bộ, credential và đường dự phòng | R-DP-03; kiểm tra đích ngoài IdP và credential cá nhân |
| SR-DEPROV-06 | Xử lý secret chung và danh tính dịch vụ có chủ sở hữu | R-DP-07; secret cũ không còn cấp quyền ngoài phạm vi |
| SR-DEPROV-07 | Điều phối bền vững, retry an toàn và xác minh từng đích | R-DP-06; timeout, crash, trạng thái UNKNOWN |
| SR-DEPROV-08 | Ngăn tạo lại hoặc hồi sinh quyền thế hệ cũ | R-DP-05; đồng bộ cũ, tiếp nhận lại và phục hồi backup |
| SR-DEPROV-09 | Tách dữ liệu, chuyển giao và thu hồi truy cập | R-DP-08; dữ liệu còn quản lý được, không bật lại quyền vì lỗi dọn dẹp |
| SR-DEPROV-10 | Audit và số đo giữ mốc từ nguồn, không loại lỗi khỏi báo cáo | R-DP-06; quá hạn, bằng chứng và độ bao phủ |
| SR-DEPROV-11 | Khôi phục sai sót có quyết định riêng và quyền hiện hành | R-DP-05; không hồi sinh token, group hoặc lệnh chặn đã mất điều kiện |
| SR-DEPROV-12 | Mọi hệ thống mới có hợp đồng deprovision trước khi nhận tài khoản | R-DP-03; mapping, owner, deadline và ca kiểm thử đầu cuối |

Mỗi ID cần gắn với cấu hình, điểm thực thi và bằng chứng của hệ thống cụ thể. Một connector có hỗ trợ thao tác xóa tài khoản chưa chứng minh toàn bộ yêu cầu thu hồi đã được thỏa mãn.

## 14. Kế hoạch nghiệm thu theo vòng đời và tình huống lỗi

Các ca dưới đây là kế hoạch kiểm thử của ví dụ, không phải kết quả đã chạy.

| Ca | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| AT-DP-01 | Chấm dứt membership theo lịch, khởi động lại bộ điều phối trước mốc | Kế hoạch vẫn kích hoạt đúng mốc, giữ t0 gốc |
| AT-DP-02 | Quyết định khẩn cấp trên tài khoản đặc quyền | Không còn đường đặc quyền trong 60 giây của hồ sơ mẫu |
| AT-DP-03 | Một người còn tư cách học viên nhưng hết tư cách nhân viên | Chỉ thu hồi đúng phạm vi; token đa phạm vi không giữ quyền cũ |
| AT-DP-04 | Tài khoản trùng tên hoặc email đã được cấp lại | Không tác động nhầm người; dùng ID và generation đúng |
| AT-DP-05 | Gửi lại cùng sự kiện nhiều lần | Không tạo tác động sai; các bước chưa xong được tiếp tục xác minh |
| AT-DP-06 | Sự kiện ACTIVE cũ đến sau DISABLED mới | Không khôi phục quyền |
| AT-DP-07 | Nguồn hồ sơ gửi cập nhật mới khi có security hold toàn cục | Không gỡ hold ngoài thẩm quyền |
| AT-DP-08 | Đăng nhập bắt đầu trước, cấp phiên hoàn tất sau khi disable commit | Không cấp phiên dựa trên trạng thái/version đã cũ |
| AT-DP-09 | Dùng refresh token, access token và cookie phiên cũ | Từng đường bị chặn trong deadline tương ứng |
| AT-DP-10 | Dùng key cá nhân, đăng nhập cục bộ và đường dự phòng | Không đi vòng qua việc khóa IdP |
| AT-DP-11 | Cache nóng và replica chậm tại bên sử dụng token | Không kéo dài quyền quá cam kết |
| AT-DP-12 | Connector timeout sau khi đích đã nhận lệnh | Xác minh hoặc retry an toàn; không coi timeout là chưa có tác động |
| AT-DP-13 | Một đích không truy cập được | Giữ trạng thái chưa xác minh, cảnh báo và không báo hoàn tất giả |
| AT-DP-14 | Bộ điều phối chết giữa hai đích | Khôi phục kế hoạch, giữ các bước đã thu hồi, không bật lại tài khoản |
| AT-DP-15 | Stream, kết nối dài và job đã chạy trước t0 | Dừng hoặc đổi phạm vi theo điểm kiểm tra và deadline |
| AT-DP-16 | Dùng liên kết tải hoặc grant thực hiện thay còn sống | Không tiếp tục nhận dữ liệu trong phạm vi đã thu hồi ngoài cam kết |
| AT-DP-17 | Reset mật khẩu, phục hồi hoặc dùng MFA cũ sau deprovision | Không tái kích hoạt tư cách hoặc cấp quyền mới |
| AT-DP-18 | Người rời tổ chức biết secret của tài khoản dịch vụ | Secret không tiếp tục tạo truy cập ngoài phạm vi; đổi owner đơn lẻ không được coi là đủ |
| AT-DP-19 | Bước chuyển giao dữ liệu thất bại sau ACCESS_CLOSED | Truy cập vẫn đóng, chỉ nghĩa vụ dữ liệu còn chờ xử lý |
| AT-DP-20 | Đồng bộ cố tạo lại tài khoản đã đóng | Bị chặn bằng trạng thái mong muốn/tombstone và revision |
| AT-DP-21 | Tiếp nhận lại hợp lệ cùng người | Quyền hiện tại được cấp rõ ràng; credential thế hệ cũ vẫn vô hiệu |
| AT-DP-22 | Khôi phục backup có tài khoản ACTIVE cũ | Áp lại quyết định hiện hành trước khi mở phục vụ |
| AT-DP-23 | Sự kiện đến muộn hơn deadline | Báo vi phạm từ t0, không đặt lại đồng hồ lúc nhận |
| AT-DP-24 | Một đích còn UNKNOWN khi các đích khác thành công | Không chuyển toàn quy trình sang ACCESS_CLOSED |
| AT-DP-25 | Khôi phục do xử lý nhầm trong khi một hold độc lập còn hiệu lực | Chỉ gỡ quyết định được phép; không phục hồi ngoài phạm vi |
| AT-DP-26 | Kiểm tra log, hàng đợi lỗi và bằng chứng với credential tổng hợp | Không lộ bí mật trong dữ liệu vận hành |

Bộ kiểm thử cần có cả ca bình thường và ca chỉ thu hồi một phần tư cách. Nếu mọi tài khoản đều bị khóa toàn cục, nhiều ca từ chối sẽ “đạt” nhưng yêu cầu phạm vi vẫn sai.

Đo thời hạn qua nơi thực sự cấp hoặc sử dụng quyền, không chỉ qua bảng trạng thái của bộ điều phối. Với cạnh tranh, điều khiển thứ tự các bước để chứng minh cửa sổ rủi ro được xử lý; với hệ thống phân tán, cần đo ở các đích và tầng cache liên quan.

Không có một phép thử duy nhất chứng minh mọi quyền đã được kiểm kê. Bằng chứng cần kết hợp danh mục đích, ánh xạ identity, cấu hình thu hồi, thử đầu cuối và đối soát quyền thực tế.

## 15. Duy trì yêu cầu trong vòng đời phát triển

Ở giai đoạn phân tích, xác định nguồn tư cách, phạm vi quyền và mức tác động khi để sót truy cập. Ở giai đoạn kiến trúc, quy định cổng cấp mới, cơ chế thu hồi tại bên sử dụng và trạng thái điều phối bền vững.

Khi tích hợp một ứng dụng mới, hợp đồng onboarding của ứng dụng cần bao gồm deprovisioning: account mapping, chủ sở hữu connector, các credential có thể phát hành, deadline, hành vi khi lỗi và bằng chứng xác minh. Một ứng dụng không có đường thu hồi là khoảng trống thiết kế cần được nhìn thấy trước khi cấp quyền rộng.

Thay đổi thời hạn token, thêm đăng nhập dự phòng, mở region, thêm cache, thay nguồn nhân sự hoặc bổ sung tài khoản dịch vụ đều có thể làm mất khả năng đáp ứng cam kết cũ. Các thay đổi đó cần được nối lại với yêu cầu và kế hoạch nghiệm thu.

Trong vận hành, đối soát trạng thái mong muốn với thực tế, xử lý đích chưa xác minh và theo dõi độ trễ từ nguồn. Định kỳ kiểm tra kịch bản khẩn cấp và khôi phục backup để tránh quyền cũ quay lại qua đường ít sử dụng.

Deprovisioning đạt yêu cầu khi phạm vi đúng, các đường truy cập thực sự mất hiệu lực trong thời hạn và kết quả có bằng chứng. Việc giữ dữ liệu, chuyển giao trách nhiệm hoặc sửa một quyết định nhầm phải tiếp tục được quản lý mà không làm sống lại quyền đã bị thu hồi ngoài ý muốn.

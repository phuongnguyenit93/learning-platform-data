# Fallback khi IAM unavailable

## 1. Fallback trong IAM cần đạt điều gì?

**Fallback khi IAM unavailable** là hành vi được thiết kế trước để xử lý request khi một hoặc nhiều thành phần IAM không thể cung cấp kết quả cần thiết. Mục tiêu là duy trì những chức năng có thể tiếp tục trong giới hạn đã được chấp nhận, đồng thời giữ ranh giới xác thực, cấp quyền và bảo vệ credential.

Fallback không phải quy tắc “không gọi được IAM thì cho qua”. Lỗi kết nối không tạo ra một danh tính mới, không làm token hết hạn trở nên hợp lệ và không cấp thêm quyền cho người gọi.

Ví dụ, một API có thể tiếp tục kiểm chứng một loại token tự chứa bằng khóa công khai đã được quản trị và còn được phép sử dụng. Nhưng một thao tác quản trị cần xác minh trạng thái quyền hiện tại có thể phải tạm ngừng khi không lấy được dữ liệu đó.

Một phương án fallback tốt trả lời được bốn câu hỏi: chức năng nào còn hoạt động, dựa trên bằng chứng nào, trong bao lâu và khi nào phải dừng. Hành vi sau khi IAM phục hồi cũng là một phần của thiết kế, không chỉ là bước kết thúc sự cố.

## 2. Xác định thành phần nào đang unavailable

IAM không phải một lời gọi duy nhất. Sự cố ở một thành phần không nhất thiết làm mọi chức năng danh tính cùng ngừng hoạt động.

| Thành phần bị ảnh hưởng | Hoạt động có thể bị ảnh hưởng | Điều không được suy ra tự động |
|---|---|---|
| IdP hoặc dịch vụ authentication | Login mới, tái xác thực, một số luồng SSO | Mọi phiên đã có đều phải được chấp nhận hoặc đều đã vô hiệu |
| Dịch vụ MFA | Hoàn thành bước xác thực bổ sung | Được bỏ MFA cho hành động vốn cần nó |
| Token endpoint | Cấp hoặc refresh token | Được tự kéo dài token cũ tại client |
| Nguồn khóa hoặc metadata | Cập nhật khóa và cấu hình kiểm chứng | Được tin khóa hoặc issuer do request tự cung cấp |
| Introspection | Kiểm tra trạng thái token theo hợp đồng | Opaque token được xem là active khi không tra cứu được |
| Dịch vụ quyết định quyền | Tính quyết định authorization mới | Mọi request đã xác thực đều đủ quyền |
| Nguồn thuộc tính | Lấy trạng thái, quan hệ hoặc entitlement cần thiết | Thuộc tính thiếu được thay bằng giá trị có lợi cho người gọi |
| Kênh thu hồi hoặc provisioning | Truyền và thực thi thay đổi vòng đời | Event đã gửi đồng nghĩa mọi đích đã thu hồi quyền |
| Audit hoặc telemetry | Ghi bằng chứng và quan sát | Có thể bỏ mọi yêu cầu audit để tiếp tục thao tác |

Trước khi kích hoạt fallback, cần khoanh vùng lỗi: một vùng triển khai, một issuer, một loại grant hay toàn bộ dịch vụ. Một phép kiểm tra sức khỏe chung có thể chưa phản ánh trạng thái của từng đường xử lý.

## 3. Phân biệt unavailable với một quyết định từ chối

Một timeout, một lỗi mạng và một phản hồi từ chối credential có ý nghĩa khác nhau.

```text
Credential sai hoặc không đáp ứng hợp đồng
    -> không xác thực thành công

Policy trả kết quả không đủ quyền
    -> không được thực hiện hành động

Không lấy được kết quả cần thiết từ phụ thuộc
    -> trạng thái xử lý lỗi hoặc chưa đủ bằng chứng
    -> chỉ xem xét fallback đã được định nghĩa cho trường hợp đó
```

Không dùng fallback để thử biến một kết quả từ chối rõ ràng thành cho phép. Nếu hệ thống đã biết tài khoản bị vô hiệu hóa hoặc credential bị thu hồi, bản cache “allowed” cũ không được ghi đè thông tin đó.

Ngược lại, một lỗi hạ tầng không nên được trình bày nội bộ như thể người dùng chắc chắn nhập sai mật khẩu. Phân loại đúng giúp vận hành xử lý sự cố mà không gây khóa tài khoản hàng loạt do một phụ thuộc hỏng.

Phản hồi ra ngoài có thể giới hạn chi tiết để tránh lộ cấu hình, nhưng log và metric được phân quyền cần phân biệt đủ nguyên nhân. Việc không thực hiện hành động vì thiếu bằng chứng khác với kết luận nghiệp vụ rằng chủ thể không có quyền.

## 4. Phân loại hành động trước khi chọn fallback

Không nên áp một chế độ fallback chung cho mọi endpoint. Quyết định phụ thuộc mức tác động, dữ liệu cần bảo vệ và yêu cầu về độ mới của bằng chứng.

| Nhóm hành động | Hướng thiết kế minh họa |
|---|---|
| Đọc nội dung vốn được phân loại công khai | Có thể tiếp tục theo chính sách công khai đã có; không đổi dữ liệu riêng thành công khai |
| Đọc dữ liệu ít nhạy cảm với credential hợp lệ và policy cục bộ còn hiệu lực | Có thể tiếp tục nếu phương án này đã được chấp nhận, có giới hạn và đủ bằng chứng |
| Login mới không thể hoàn tất kiểm chứng | Không tạo phiên chỉ dựa trên thông tin người dùng tự khai |
| Hành động đòi MFA hoặc tái xác thực mới | Không bỏ điều kiện chỉ vì thành phần xác thực bổ sung lỗi |
| Cấp đặc quyền hoặc thay đổi cấu hình tin cậy | Thường cần dừng nếu thiếu trạng thái hoặc phê duyệt bắt buộc |
| Thao tác nhạy cảm không thể kiểm tra quyền hiện tại | Không thực hiện bằng một mặc định cho phép |
| Công việc thu hồi quyền | Cần cơ chế thực thi, theo dõi và xử lý đích lỗi; không đánh dấu xong chỉ vì đã enqueue |
| Truy cập vận hành khẩn cấp | Đi theo quy trình riêng đã thiết lập, có phạm vi và bằng chứng |

Đây là các hướng thiết kế, không phải một bảng quyền có thể áp trực tiếp cho mọi hệ thống. Chủ sở hữu nghiệp vụ và an ninh cần xác định trường hợp cụ thể nào được tiếp tục và những điều kiện nào bắt buộc phải có.

Fail-closed nghĩa là không cấp quyền khi thiếu điều kiện cần thiết cho hành động. Nó không nhất thiết có nghĩa tắt mọi chức năng, bao gồm những chức năng không phụ thuộc thành phần đang hỏng.

## 5. Tách đường phục vụ request và đường quản trị

Đường phục vụ request sử dụng credential, policy và trạng thái để kiểm chứng và thực thi truy cập. Đường quản trị tạo hoặc thay đổi những dữ liệu đó, chẳng hạn đăng ký client, phân phối khóa, gán quyền hoặc sửa policy.

Nếu đường quản trị tạm thời lỗi nhưng điểm thực thi còn cấu hình hợp lệ tại chỗ, một số request có thể tiếp tục theo hợp đồng. Điều này khác với việc điểm thực thi bỏ qua kiểm tra.

```text
Đường quản trị và cập nhật
    -> cấu hình tin cậy, policy, trạng thái và sự kiện
    -> phân phối tới điểm thực thi

Đường request
    -> kiểm chứng credential theo cấu hình đang được phép
    -> đánh giá policy và trạng thái đủ mới
    -> thực thi hành động trong phạm vi
```

Cần biết dữ liệu cục bộ còn được dùng đến khi nào. Một bản policy tải thành công nhiều tháng trước không tự trở thành cơ sở cho phép truy cập vô hạn khi đường quản trị mất kết nối.

Tương tự, việc một API xác minh chữ ký tại chỗ không chứng minh nó có thể đáp ứng yêu cầu thu hồi ngay lập tức. Khả năng hoạt động khi mất kết nối và mục tiêu độ mới phải được thiết kế cùng nhau.

## 6. Kiểm chứng token tại chỗ khi nguồn IAM lỗi

### 6.1. Những điều kiện phải giữ

Với token tự chứa có cơ chế kiểm chứng phù hợp, điểm nhận có thể sử dụng cấu hình và khóa đã được quản trị theo thiết kế. Nó vẫn phải kiểm tra loại token, nguồn phát hành, bên nhận, thời hạn và các ràng buộc liên quan.

Những tình huống sau không được tự chuyển thành token hợp lệ:

- Token hết hạn hoặc chưa được phép sử dụng.
- Token dành cho một API khác.
- Nguồn phát hành chưa được chấp nhận.
- Không có khóa hợp lệ để kiểm chứng.
- Thiếu bằng chứng ràng buộc người trình nếu hợp đồng yêu cầu.
- Có thông tin đáng tin cậy cho biết credential hoặc nguồn khóa đã bị thu hồi.

Không tắt kiểm tra chữ ký, audience hoặc issuer để vượt qua sự cố. Không dùng nội dung chưa được kiểm chứng trong token để tìm một nguồn khóa tùy ý rồi tự mở rộng quan hệ tin cậy.

### 6.2. Cache khóa không phải cache quyền truy cập vô hạn

Cache khóa công khai có thể giúp tránh gọi nguồn khóa cho mọi request. Tuy nhiên, nó cần nguồn đáng tin, giới hạn độ cũ, cách xử lý xoay khóa và quy trình khi biết khóa bị lộ.

Một token mang key ID chưa có trong tập khóa được phép không thể được chấp nhận chỉ vì hệ thống đang outage. Cần xử lý thất bại hoặc lỗi phụ thuộc theo hợp đồng, đồng thời tránh việc hàng loạt request cùng kích hoạt tải khóa liên tục.

Không giữ một khóa đã biết bị thu hồi chỉ để duy trì tỷ lệ đăng nhập. Khả năng dùng cấu hình cục bộ chỉ có ý nghĩa khi cấu hình đó còn được phép sử dụng.

### 6.3. Opaque token và kiểm tra trạng thái

Nếu hợp đồng yêu cầu introspection hoặc tra cứu trạng thái, không thể thay bước đó bằng cách decode một token vốn không có bằng chứng tự kiểm chứng phù hợp.

Một kết quả introspection được cache, nếu được cho phép, vẫn phải có thời hạn và ràng buộc đúng token, nguồn, bên nhận và ngữ cảnh cần thiết. Chính sách phải xác định tác động lên độ trễ thu hồi; không coi trạng thái active từng được quan sát là active mãi mãi.

## 7. Cache quyết định quyền một cách có giới hạn

Một cache chỉ lưu `user -> allowed` thường không đủ. Quyết định có thể phụ thuộc issuer, subject, tenant, tài nguyên, hành động, policy, thuộc tính và các điều kiện của credential.

Ví dụ, quyền đọc khóa học A không thể được tái sử dụng để sửa khóa học B. Quyền có được trong một tenant cũng không chuyển sang tenant khác vì cùng tên người dùng.

Một cache dùng cho fallback cần xác định:

- Khóa cache đại diện cho quyết định nào và toàn bộ điều kiện quan trọng của nó.
- Phiên bản policy và những nguồn trạng thái được sử dụng.
- Thời điểm quyết định được tạo và thời điểm hết khả năng tái sử dụng.
- Cách invalidation khi nhận thay đổi hoặc thu hồi.
- Những hành động nào được phép dùng cache khi mất kết nối.
- Những tín hiệu nào buộc dừng dù TTL chưa hết.

Giới hạn sử dụng thực tế không được vượt điều kiện hết hạn sớm nhất trong các điều kiện cần thiết. Có thể gồm thời hạn token, thời hạn cache quyết định, độ mới thuộc tính và thời điểm kết thúc chế độ suy giảm đã được chấp nhận.

Ví dụ minh họa:

```text
Token còn hiệu lực:              4 phút
Quyết định cache còn được dùng:  2 phút
Chế độ suy giảm còn cho phép:    3 phút

Nếu mọi điều kiện khác vẫn đủ:
    giới hạn theo ba điều kiện trên không vượt 2 phút
```

Các con số chỉ minh họa cách lấy giới hạn, không phải ngưỡng khuyến nghị chung. Nếu xuất hiện một quyết định thu hồi đáng tin cậy trong phút đầu, không được tiếp tục chờ đủ 2 phút mới áp dụng nó.

Cache kết quả từ chối cũng có tác động: quyền hợp lệ mới có thể chưa được sử dụng cho đến khi cache được làm mới. Cần hiểu cả hai hướng thay đổi, không chỉ các trường hợp cho phép.

## 8. State machine cho chế độ suy giảm

Một chế độ fallback nên có trạng thái rõ ràng, thay vì nhiều khối xử lý exception tự cho qua rải rác trong mã.

```text
NORMAL
    -> phát hiện lỗi phụ thuộc đạt điều kiện
    -> DEGRADED_LIMITED nếu có phương án đã được phép và đủ bằng chứng
    -> BLOCKED cho hành động không đáp ứng điều kiện

DEGRADED_LIMITED
    -> hết thời hạn hoặc mất điều kiện cần thiết -> BLOCKED
    -> phụ thuộc phục hồi -> RECOVERY_CHECK

RECOVERY_CHECK
    -> đối soát trạng thái, policy, khóa và công việc còn dở
    -> đủ điều kiện -> NORMAL
    -> chưa đủ -> giữ giới hạn hoặc BLOCKED theo thiết kế
```

Trạng thái có thể khác nhau theo issuer, vùng, phụ thuộc hoặc nhóm hành động. Không cần chuyển cả hệ thống sang cùng một trạng thái chỉ vì một connector bị lỗi.

Một logic request minh họa có thể là:

```text
Nếu đã có bằng chứng đáng tin về vô hiệu hóa hoặc thu hồi:
    không thực hiện hành động

Nếu đường kiểm chứng và quyết định bình thường thành công:
    thực thi đúng kết quả authorization

Nếu nhận kết quả credential không hợp lệ hoặc không đủ quyền:
    không dùng fallback để đổi kết quả đó

Nếu phụ thuộc không cung cấp được kết quả:
    kiểm tra phương án fallback áp dụng cho hành động này
    kiểm tra đầy đủ credential và trạng thái cục bộ còn được phép
    nếu tất cả điều kiện được đáp ứng:
        thực hiện trong phạm vi suy giảm đã xác định
    nếu không:
        dừng mà không cấp quyền mới
```

Đây là pseudocode về trách nhiệm, không phải mã có thể thay thế thư viện kiểm chứng hoặc policy engine.

## 9. Timeout, retry và circuit breaker

Lời gọi IAM chậm có thể giữ thread, kết nối và request ở các dịch vụ phụ thuộc. Nếu mọi lớp đều retry nhiều lần, sự cố ban đầu có thể trở thành một đợt tăng tải lớn hơn.

Cần có timeout phù hợp, giới hạn tổng thời gian của thao tác, số lần retry và mức đồng thời. Backoff, phân tán thời điểm retry và circuit breaker có thể giúp giảm việc tiếp tục đẩy request vào phụ thuộc đang lỗi.

Circuit breaker mở không phải một kết quả authorization cho phép. Nó chỉ cho biết đường gọi phụ thuộc đang bị hạn chế theo cơ chế vận hành; hành vi truy cập vẫn đi qua quy tắc fallback hoặc từ chối tương ứng.

Retry còn phụ thuộc tính chất của thao tác. Một yêu cầu đổi authorization code hoặc xử lý refresh token có thể có ràng buộc sử dụng một lần và trạng thái đã thay đổi dù client chưa nhận phản hồi. Không retry mù tất cả thao tác cấp token như một request đọc không có tác động.

Khi kết quả thao tác chưa rõ, phải giữ trạng thái chưa xác định và xử lý theo giao thức hoặc hợp đồng thích hợp. Không mặc định “timeout nghĩa là server chưa làm gì” rồi tạo thêm quyền hoặc credential trùng lặp.

Không chuyển người dùng sang một IdP khác và nối tài khoản chỉ vì email giống nhau để vượt outage. Quan hệ tin cậy và liên kết danh tính của đường thay thế phải được thiết lập từ trước.

## 10. Phiên hiện có, workload và công việc bất đồng bộ

### 10.1. Phiên người dùng

Ứng dụng có thể có phiên riêng sau khi xác thực qua IdP. Việc IdP tạm thời unavailable không tự làm phiên đó biến mất, nhưng ứng dụng vẫn phải kiểm tra thời hạn, trạng thái và điều kiện của phiên theo thiết kế.

Nếu thao tác cần tái xác thực hoặc MFA mới, một phiên cũ chưa chắc đáp ứng yêu cầu. Không kéo dài phiên hoặc bỏ bước xác thực mới chỉ vì phụ thuộc đang hỏng.

Nếu session store không truy cập được, không biến một cookie bất kỳ thành danh tính đã xác thực. Khả năng kiểm chứng cục bộ phụ thuộc loại phiên và bằng chứng thực tế, không phải tên của cookie.

### 10.2. Workload identity

Workload cần credential còn hợp lệ và đúng phạm vi để tiếp tục gọi dịch vụ. Một chứng thư hoặc token đã hết hạn không được tự kéo dài chỉ vì dịch vụ cấp mới chưa phục hồi.

Cần thiết kế năng lực cấp và làm mới credential, cảnh báo thời hạn, đường bootstrap và phụ thuộc liên quan. Không fallback sang một secret quản trị dùng chung hoặc quyền của một người vận hành để duy trì mọi workload.

Một cơ chế dự phòng được chấp nhận phải có danh tính, phạm vi và audit riêng, thay vì che việc workload đang sử dụng quyền rộng hơn hợp đồng ban đầu.

### 10.3. Provisioning và thu hồi

Tác vụ bất đồng bộ có thể được lưu bền và xử lý sau nếu quy trình cho phép. Tuy nhiên, enqueue yêu cầu thu hồi không đồng nghĩa quyền ở hệ thống đích đã mất hiệu lực.

Cần hiển thị trạng thái từng đích, thực hiện biện pháp giới hạn cục bộ phù hợp, cảnh báo khi thu hồi chưa hoàn tất và đối soát sau phục hồi. Quyền còn tồn tại ở một SaaS lỗi không được che dưới trạng thái tổng “offboarding thành công”.

Với yêu cầu cấp thêm quyền, không coi việc lưu vào hàng đợi là quyền đã có hiệu lực trước khi các điều kiện và phê duyệt cần thiết được đáp ứng. Khi xử lý lại, cần kiểm tra thứ tự và trạng thái hiện tại để một lệnh cấp quyền cũ không khôi phục quyền vừa bị thu hồi.

## 11. Truy cập khẩn cấp là một quy trình riêng

Một tổ chức có thể chuẩn bị cơ chế break-glass để người được phép khôi phục hạ tầng khi đường IAM thông thường hỏng. Cơ chế này không nên là một tài khoản đặc quyền bí mật được dùng tự động cho mọi request thất bại.

Thiết kế cần xác định người được sử dụng, cách xác minh, giới hạn tài nguyên và thời gian, điều kiện kích hoạt, audit và cách kết thúc quyền khẩn cấp. Khi phù hợp, có thể yêu cầu phê duyệt hoặc kiểm soát nhiều người theo quy trình đã đặt.

Phải kiểm tra phụ thuộc của chính đường khẩn cấp. Nếu credential nằm trong một vault chỉ mở được bằng IdP đang lỗi, hoặc mọi yếu tố xác thực dự phòng cùng phụ thuộc một dịch vụ đã hỏng, phương án có thể không sử dụng được lúc cần.

Cơ chế dự phòng cần được bảo vệ theo mô hình đe dọa của nó, có kiểm kê và diễn tập. Việc tách phụ thuộc không phải lý do để lưu mật khẩu không bảo vệ hoặc bỏ bằng chứng về người đã sử dụng.

Sau sử dụng, cần kết thúc phiên và quyền tạm thời, xử lý credential theo quy trình, đối chiếu thao tác và lưu bằng chứng phù hợp. Không để chế độ khẩn cấp trở thành đường truy cập thường ngày lâu dài.

## 12. Audit và observability trong lúc outage

Một hệ thống đang chạy ở chế độ suy giảm cần cho người vận hành thấy chính xác giới hạn đó. Chỉ theo dõi tỷ lệ HTTP thành công có thể che việc request đang dùng policy cũ hoặc thu hồi bị trễ.

Các tín hiệu hữu ích gồm:

- Phụ thuộc nào lỗi, phạm vi nào bị ảnh hưởng và thời điểm bắt đầu.
- Số request được xử lý bình thường, bằng fallback hoặc bị chặn do thiếu điều kiện.
- Tuổi cache, thời gian còn lại của chế độ suy giảm và độ cũ của trạng thái.
- Lỗi cấp hoặc refresh token, tuổi credential workload và số retry.
- Độ trễ event thu hồi, số đích chưa thực thi và sai lệch đối soát.
- Tình trạng audit, bộ đệm và khả năng ghi nhận bằng chứng.

Nếu audit là điều kiện bắt buộc cho một hành động, cần giữ hợp đồng đó. Một phương án ghi đệm chỉ phù hợp khi đã được thiết kế với độ bền, bảo vệ, giới hạn dung lượng và cách xử lý khi đầy. Không âm thầm bỏ sự kiện để tiếp tục mọi thao tác.

Log có thể ghi chế độ xử lý, policy version, lý do dùng fallback và tham chiếu giao dịch phù hợp. Không ghi token, cookie, secret hoặc toàn bộ hồ sơ để debug outage.

Metric tổng hợp nên dùng chiều có giới hạn như vùng, phụ thuộc và nhóm hành động. Thông tin chi tiết về chủ thể hoặc credential cần nằm trong nơi được phân quyền, tránh tạo cardinality và rò rỉ dữ liệu qua label.

## 13. Phục hồi có kiểm soát

Khi một health check chuyển sang xanh, chưa chắc mọi thành phần IAM đã đồng bộ hoặc có đủ năng lực tiếp nhận lưu lượng dồn lại.

Quá trình phục hồi có thể gồm:

1. Xác nhận đường xử lý thực tế, không chỉ tiến trình còn chạy.
2. Mở lại lời gọi từng phần để tránh mọi instance đồng thời retry hoặc làm mới cache.
3. Kiểm tra khóa và cấu hình tin cậy, không khôi phục khóa đã bị thu hồi chỉ vì nó có trong snapshot cũ.
4. Đồng bộ policy, trạng thái chủ thể và các thay đổi quyền mới hơn.
5. Xử lý hàng đợi với kiểm soát thứ tự, idempotency và điều kiện hiện tại.
6. Đối soát phiên, credential, quyền và các tác vụ thu hồi còn dở.
7. Chỉ đưa từng nhóm hành động về bình thường khi đáp ứng điều kiện của nhóm đó.

Các quyền tạm thời hoặc trạng thái tạo ra trong quy trình khẩn cấp cần được xem xét và kết thúc phù hợp. Không tự nhập một quyết định fallback thành policy lâu dài.

Sau sự cố, cần xác định request nào dùng dữ liệu cũ, khoảng trễ thu hồi thực tế và những dữ liệu audit nào còn thiếu. Kết quả đó giúp điều chỉnh giới hạn, capacity hoặc kiến trúc phụ thuộc bằng bằng chứng thay vì chỉ tăng TTL cho mọi cache.

## 14. Ví dụ và tình huống kiểm chứng

Giả sử token endpoint bị gián đoạn nhưng API học tập vẫn có khả năng kiểm chứng một loại token đã phát hành, bằng khóa còn được phép và policy cục bộ đủ mới.

Một phương án đã được phê duyệt có thể cho phép đọc một số nội dung ít nhạy cảm theo phân loại, với credential còn hiệu lực và đầy đủ quan hệ truy cập cần thiết. Các thao tác cấp role, đổi cấu hình issuer hoặc truy cập đòi tái xác thực mới vẫn tạm dừng khi thiếu điều kiện.

Đây là tiếp tục thực thi một phạm vi đã xác định bằng bằng chứng còn được phép sử dụng. Nó không phải cho mọi người đọc dữ liệu và cũng không cho client tự tạo token thay thế.

Khi token của người dùng hết hạn mà chưa refresh được, request tiếp theo phải được xử lý theo trạng thái thiếu credential hợp lệ. Không kéo dài token tại API chỉ vì các request trước đó đã thành công.

Các tình huống kiểm chứng cần bao gồm:

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Login mới khi IdP không phản hồi | Không tạo phiên từ thông tin tự khai hoặc cache không đủ điều kiện |
| MFA lỗi ở thao tác cần MFA mới | Không tự bỏ điều kiện xác thực bổ sung |
| Token hợp lệ với khóa được tin còn dùng được | Hành vi theo hợp đồng và phạm vi fallback đã đặt |
| Token sai audience hoặc hết hạn trong lúc outage | Không mở rộng điều kiện chấp nhận |
| Token dùng khóa chưa biết | Không bỏ kiểm chứng hoặc tin nguồn khóa tùy ý |
| Đã biết tài khoản hoặc khóa bị thu hồi | Không để cache cho phép cũ ghi đè trạng thái đó |
| Opaque token không thể kiểm tra trạng thái | Không tự coi token là active |
| Cache đọc tài nguyên A được dùng cho yêu cầu ghi B | Không tái sử dụng quyết định ngoài ngữ cảnh |
| Một giới hạn thời gian fallback hết trước các giới hạn khác | Hệ thống dừng sử dụng theo mốc hết hạn sớm nhất liên quan |
| Circuit breaker mở | Không bị diễn giải thành kết quả authorization cho phép |
| Timeout sau một yêu cầu cấp token có trạng thái | Không retry mù hoặc giả định server chưa xử lý |
| Workload hết hạn credential | Không đổi sang secret quản trị hoặc kéo dài hiệu lực tùy ý |
| Thu hồi quyền bị lỗi ở một đích | Có trạng thái chưa hoàn tất, cảnh báo và đối soát |
| Audit buffer đầy | Hành vi theo yêu cầu bằng chứng đã xác định cho hành động |
| Break-glass được sử dụng | Đúng người, đúng phạm vi, có kết thúc và bằng chứng |
| IAM phục hồi sau nhiều thay đổi trạng thái | Không cấp lại quyền cũ hoặc mở lưu lượng trước khi đủ điều kiện |

Fallback IAM có giá trị khi hệ thống duy trì được những chức năng có đủ bằng chứng mà vẫn thể hiện rõ phần phải tạm ngừng. Điều kiện sử dụng trạng thái cục bộ, thời hạn suy giảm, cách xử lý thu hồi và quy trình phục hồi cần được kiểm chứng từ trước, để sự cố hạ tầng không biến thành một lần mở rộng quyền truy cập ngoài dự kiến.

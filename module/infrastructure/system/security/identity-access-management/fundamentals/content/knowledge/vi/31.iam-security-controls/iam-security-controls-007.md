# Credential rotation: thay thế thông tin xác thực có kiểm soát

## 1. Credential rotation giải quyết vấn đề gì?

**Credential rotation** là quá trình thay thế một thông tin xác thực đang sử dụng bằng một thông tin xác thực mới, chuyển các bên liên quan sang phiên bản mới và kết thúc khả năng sử dụng phiên bản cũ theo chính sách.

Thông tin xác thực có thể là mật khẩu, API key, client secret, cặp khóa của workload hoặc chứng thư gắn với khóa riêng. Trong hệ thống IAM, một số bí mật khác cũng cần vòng đời thay thế riêng, chẳng hạn khóa ký token hoặc bí mật đăng ký một phương thức MFA.

Mục tiêu của rotation là kiểm soát tuổi thọ, khả năng phân phối và việc thu hồi thông tin xác thực. Nếu một bí mật bị sao chép mà chưa bị phát hiện, việc kết thúc hiệu lực của bản cũ giúp giới hạn thời gian bản đó còn dùng được.

Tuy nhiên, rotation không tự bảo đảm rằng bí mật mới không bị đánh cắp. Nếu bí mật tiếp tục được ghi vào log, lưu trong mã nguồn hoặc phát cho một máy đã bị chiếm quyền, thay giá trị nhiều lần vẫn không xử lý được nguyên nhân.

Ví dụ xuyên suốt: dịch vụ `report-exporter` dùng một thông tin xác thực để đọc dữ liệu hợp đồng phục vụ báo cáo của An Bình. Thông tin đó đang được nhiều bản triển khai của dịch vụ sử dụng. Việc đổi giá trị ở kho bí mật chỉ là một bước; cần bảo đảm các bản triển khai nhận được giá trị mới và giá trị cũ thực sự bị từ chối.

## 2. Phân biệt rotation, renewal, revocation và rehash

| Khái niệm | Ý nghĩa | Điểm cần phân biệt |
| --- | --- | --- |
| Rotation | Chuyển sang thông tin xác thực hoặc phiên bản khóa mới | Phải có điểm kết thúc sử dụng phiên bản cũ |
| Renewal | Gia hạn hoặc cấp lại thời hạn sử dụng | Nếu vẫn dùng cùng bí mật hoặc khóa riêng thì chưa thay thế bí mật đó |
| Revocation | Thu hồi khả năng sử dụng | Có thể diễn ra ngay mà không chờ bản thay thế sẵn sàng |
| Rehash mật khẩu | Tính lại giá trị băm khi thay cấu hình lưu mật khẩu | Không có nghĩa người dùng đã có mật khẩu mới |
| Thay tên hoặc version | Đổi nhãn quản lý | Không tạo ra bí mật mới nếu vật liệu bí mật không đổi |

Ví dụ, cấp chứng thư mới với cùng khóa riêng có thể kéo dài hiệu lực danh tính được chứng nhận, nhưng không loại bỏ rủi ro do khóa riêng cũ đã bị lộ.

Tương tự, đặt một API key mới vào một biến cấu hình có tên mới không hoàn tất rotation nếu key cũ vẫn có thể gọi API vô thời hạn.

Rotation cũng không đồng nghĩa thu hồi mọi quyền. Chủ thể có thể giữ nguyên nhiệm vụ nhưng dùng thông tin xác thực mới. Ngược lại, khi chủ thể không còn được phép hoạt động, chỉ đổi bí mật mà vẫn giữ quyền cho bên không còn thẩm quyền là không đủ.

## 3. Nhận diện đúng loại thông tin cần thay thế

Không nên áp dụng một quy trình duy nhất cho mọi loại credential.

| Loại | Bên sử dụng hoặc xác minh | Điều cần chú ý khi thay thế |
| --- | --- | --- |
| Mật khẩu người dùng | Người dùng và hệ thống kiểm tra mật khẩu | Đổi mật khẩu không tự kết thúc mọi phiên hoặc token đã cấp |
| API key, client secret | Tích hợp hoặc workload và dịch vụ nhận | Cần cập nhật mọi consumer, giới hạn thời gian chấp nhận key cũ |
| Thông tin đăng nhập cơ sở dữ liệu | Ứng dụng, driver và máy chủ cơ sở dữ liệu | Kết nối đang mở có thể có vòng đời khác lần xác thực mới |
| Khóa riêng và chứng thư workload | Workload và bên xác minh danh tính | Phải xem cả cấp phát khóa, chứng thư và phân phối trust |
| Khóa ký token | Bên phát hành và các bên kiểm tra chữ ký | Token đã ký và cache khóa xác minh ảnh hưởng thời gian chuyển đổi |
| Refresh token | Client và hệ thống cấp token | Có thể thay theo từng lần sử dụng và phát hiện việc dùng lại theo thiết kế |
| Bí mật phương thức MFA | Người dùng, thiết bị và hệ thống xác thực | Cần quy trình đăng ký lại, xác minh người dùng và thu hồi phương thức cũ |

Thông tin xác thực ngắn hạn cũng cần quản lý vòng đời. Việc cấp credential mới tự động trước khi credential cũ hết hạn có thể là một phần của rotation, nhưng phải kiểm tra điều kiện cấp mới và việc hết hiệu lực của bản cũ.

Một thông tin xác thực được quản lý tự động không mặc nhiên có ít quyền. Giới hạn quyền và giới hạn thời gian là hai kiểm soát bổ sung cho nhau.

## 4. Bắt đầu bằng kiểm kê và xác định chủ sở hữu

Trước khi thay một bí mật, cần biết nó đang phục vụ ai và phụ thuộc vào đâu.

Một hồ sơ quản lý có thể gồm:

```text
credentialId: cred-report-exporter
principalId: workload-report-exporter
purpose: đọc dữ liệu cho tác vụ báo cáo
environment: production
scope: phạm vi tài nguyên đã được cấp
owner: nhóm vận hành báo cáo
currentVersion: version-12
consumers: các triển khai và job đã đăng ký
rotationState: STABLE
```

Các câu hỏi cần trả lời:

- Ai có quyền tạo, đọc, phân phối, kích hoạt và thu hồi?
- Credential được lưu ở đâu?
- Những dịch vụ, vùng triển khai hoặc job định kỳ nào dùng nó?
- Consumer có tải lại bí mật hay chỉ đọc lúc khởi động?
- Hệ thống xác minh có chấp nhận đồng thời hai phiên bản không?
- Có kết nối, phiên hoặc token nào tồn tại sau lần xác thực?
- Làm sao biết bản cũ không còn được sử dụng?
- Nếu chuyển đổi lỗi, có thể phục hồi an toàn đến đâu?

Một job chỉ chạy vào cuối tháng có thể không xuất hiện trong quan sát vài giờ gần nhất. Không nên suy ra rằng “không thấy sử dụng” luôn có nghĩa “không có consumer”.

Bí mật không có chủ sở hữu hoặc không rõ mục đích là một vấn đề quản trị cần xử lý, không phải lý do bỏ qua rotation mãi mãi.

## 5. Vòng đời thay thế có kiểm soát

Một vòng đời minh họa cho credential của workload:

```text
STABLE
  -> PREPARED
  -> DISTRIBUTED
  -> SWITCHED
  -> VERIFIED
  -> RETIRED
```

| Trạng thái | Bằng chứng cần có |
| --- | --- |
| `STABLE` | Phiên bản hiện tại đang phục vụ đúng mục đích |
| `PREPARED` | Bản mới được tạo, bảo vệ và gắn đúng danh tính, quyền |
| `DISTRIBUTED` | Consumer được phép đã có cách nhận bản mới |
| `SWITCHED` | Consumer bắt đầu sử dụng bản mới |
| `VERIFIED` | Các consumer bắt buộc đã hoạt động với bản mới theo tiêu chí |
| `RETIRED` | Bản cũ không còn được chấp nhận theo phạm vi đã định |

Đây là trạng thái quy trình minh họa, không phải schema bắt buộc của một sản phẩm.

Điểm kiểm soát quan trọng nhất là không nhầm `DISTRIBUTED` với `RETIRED`. Đã cập nhật kho bí mật không chứng minh rằng mọi tiến trình đã đọc giá trị mới hoặc rằng bên xác minh đã ngừng chấp nhận bản cũ.

Nếu phát hiện rủi ro trong quá trình chuyển đổi, cần chuyển sang xử lý sự cố hoặc trạng thái lỗi rõ ràng. Không để một lần rotation treo ở giai đoạn chấp nhận hai bản mà không có thời hạn và người chịu trách nhiệm.

## 6. Tạo và phân phối credential mới

### 6.1. Tạo bí mật độc lập

Credential mới cần được tạo bằng cơ chế sinh phù hợp với loại thông tin xác thực. Với bí mật ngẫu nhiên, cần dùng nguồn ngẫu nhiên phục vụ mật mã; không thay bí mật bằng cách tăng một số, thêm hậu tố thời gian hoặc sửa vài ký tự dự đoán được.

Khóa mới phải thực sự là khóa mới nếu mục tiêu là thay vật liệu khóa. Đổi chứng thư, tên key hoặc metadata trong khi giữ nguyên khóa riêng không đáp ứng mục tiêu đó.

### 6.2. Giữ đúng danh tính và phạm vi quyền

Bản mới phải được ràng buộc với đúng principal, tenant, môi trường và mục đích sử dụng.

Không cấp quyền rộng hơn chỉ để tránh lỗi trong lúc chuyển đổi. Ví dụ, thay thông tin đăng nhập của `report-exporter` không nên biến workload chỉ đọc thành tài khoản quản trị cơ sở dữ liệu.

Cần so sánh quyền thực tế, không chỉ tên vai trò. Quyền kế thừa, điều kiện và giới hạn trên tài nguyên có thể ảnh hưởng kết quả.

### 6.3. Phân phối qua đường được bảo vệ

Consumer chỉ nên nhận credential mà nó có quyền sử dụng, qua cơ chế được xác thực và kiểm soát truy cập.

Không gửi bí mật trong URL, log, bản ghi audit hoặc nội dung hỗ trợ không phù hợp. Việc sao chép bí mật vào nhiều file thủ công khiến quá trình thay thế khó kiểm soát và khó chứng minh đã loại bỏ bản cũ.

Nếu dùng kho bí mật, cần bảo vệ cả quyền đọc bí mật lẫn quyền cập nhật phiên bản. Người có thể thay phiên bản hiện hành có thể làm ứng dụng dùng credential do họ kiểm soát.

### 6.4. Giải quyết danh tính để lấy bí mật

Workload cần một cách xác thực ban đầu để lấy credential mới. Nếu cách đó là một bí mật tĩnh khác, bí mật này cũng cần được quản lý vòng đời.

Có thể sử dụng cơ chế danh tính workload của môi trường khi phù hợp, nhưng vẫn phải giới hạn principal nào được đọc bản nào. Chuyển bí mật vào kho quản lý không tự giải quyết mọi quyền truy cập vào kho.

## 7. Chuyển đổi và khoảng thời gian chấp nhận đồng thời

### 7.1. Khi hệ thống hỗ trợ hai phiên bản

Một mô hình thường gặp:

1. Tạo credential mới.
2. Cho phép bên xác minh nhận cả bản cũ và bản mới trong phạm vi chuyển đổi.
3. Chuyển consumer sang bản mới.
4. Kiểm tra hoạt động và việc sử dụng từng phiên bản.
5. Ngừng chấp nhận bản cũ trước hạn kết thúc đã định.
6. Xác minh lại rằng bản cũ bị từ chối.

Khoảng chấp nhận đồng thời giúp tránh gián đoạn, nhưng cũng là khoảng thời gian bản cũ còn có thể được sử dụng. Cần có thời hạn, tiêu chí kết thúc và cách xử lý consumer chưa chuyển.

Nếu bản cũ bị nghi ngờ đã lộ, việc tiếp tục chấp nhận nó để giữ hoạt động phải được đánh giá trong xử lý sự cố; không áp dụng quy trình chuyển đổi bình thường một cách máy móc.

### 7.2. Khi chỉ có một credential hoạt động

Một số hệ thống không hỗ trợ giữ hai bí mật cho cùng chủ thể. Khi đó, có thể cần phối hợp thời điểm thay đổi, tải lại cấu hình, làm mới kết nối hoặc một cửa sổ gián đoạn được kiểm soát.

Nếu tạo một principal thay thế, phải xác định đúng danh tính, phạm vi quyền, audit và cách thu hồi principal cũ. Không tạo tài khoản thứ hai có quyền rộng rồi bỏ quên tài khoản đầu tiên.

Không nên hứa “rotation không gián đoạn” khi bên xác minh và consumer không có cơ chế hỗ trợ điều đó.

### 7.3. Cache và kết nối có vòng đời riêng

Consumer có thể cache bí mật, giữ cấu hình trong bộ nhớ hoặc duy trì connection pool. Việc đổi giá trị ở kho bí mật có thể chỉ tác động đến lần tải tiếp theo.

Cần kiểm tra cả:

- Kết nối mới có xác thực bằng credential mới không?
- Kết nối hiện tại có cần kết thúc hoặc tái xác thực không?
- Một bản triển khai cũ có tự khởi động lại rồi đọc credential đã nghỉ không?
- Những job ít chạy có nhận được phiên bản mới không?
- Các vùng triển khai đã cập nhật trạng thái đến mức nào?

Thay mật khẩu cơ sở dữ liệu không nhất thiết làm mọi kết nối đang mở mất quyền ngay. Hành vi này phụ thuộc hệ thống và cấu hình, nên phải có bằng chứng về đường thu hồi thực tế.

## 8. Khóa ký token cần một luồng chuyển đổi khác

Với khóa ký, bên phát hành giữ khóa riêng để ký, còn các bên nhận dùng khóa xác minh thích hợp để kiểm tra token.

Một luồng thay khóa bình thường có thể gồm:

1. Chuẩn bị khóa mới và định danh phiên bản riêng.
2. Phân phối thông tin xác minh mới cho các bên nhận được phép.
3. Bảo đảm các bên nhận nhận diện được khóa mới.
4. Bắt đầu ký token mới bằng khóa mới.
5. Duy trì khả năng kiểm tra token cũ trong giới hạn chính sách.
6. Kết thúc chấp nhận khóa cũ khi đủ điều kiện.

Cần xét thời hạn token cũ, cache khóa, độ trễ phân phối và cơ chế cập nhật của từng bên nhận.

Định danh khóa giúp tìm đúng khóa trong tập khóa được chấp nhận; nó không tự là bằng chứng tin cậy. Bên nhận không nên chấp nhận một nguồn khóa tùy ý chỉ vì token chỉ đến nguồn đó.

Nếu khóa ký cũ bị lộ, kẻ nắm khóa có thể tạo token trông hợp lệ đối với bên vẫn chấp nhận khóa đó. Chỉ đổi sang ký token mới bằng khóa mới chưa làm token giả dưới khóa cũ bị từ chối. Cần một kế hoạch loại bỏ niềm tin vào khóa cũ và xử lý phiên hoặc token liên quan theo tình huống.

Khóa mã hóa dữ liệu có yêu cầu lưu giữ khác khóa xác thực. Dữ liệu cũ có thể còn cần khóa cũ để giải mã, dù không cho phép mã hóa dữ liệu mới bằng khóa đó. Không áp dụng quy tắc “xóa mọi khóa cũ ngay” cho mọi loại khóa mà chưa xét khả năng khôi phục dữ liệu và chính sách lưu giữ.

## 9. Mật khẩu, MFA và refresh token có đặc điểm riêng

### 9.1. Mật khẩu người dùng

Khi thay mật khẩu, hệ thống cần xác minh người được phép thay, bảo vệ luồng thay hoặc khôi phục và lưu giá trị kiểm chứng mật khẩu theo cơ chế phù hợp.

Đổi mật khẩu không phải thay thuật toán băm hoặc tạo salt mới cho cùng mật khẩu. Cũng không nên áp dụng mô hình chấp nhận hai mật khẩu trong một khoảng chuyển đổi chỉ vì mô hình đó thuận tiện cho API key của workload.

Khi xử lý nghi ngờ tài khoản bị chiếm đoạt, cần xem cả phiên đăng nhập, token, phương thức khôi phục và MFA. Nếu kẻ tấn công đã thêm một phương thức khôi phục khác, đổi mật khẩu đơn thuần có thể không chặn được việc quay lại tài khoản.

Việc xác định lúc nào yêu cầu đổi mật khẩu phải dựa trên chính sách phù hợp với loại tài khoản, dấu hiệu rủi ro và phương thức xác thực; không suy ra rằng mọi loại credential đều phải có cùng lịch thay định kỳ.

### 9.2. Bí mật phương thức MFA và mã khôi phục

Thay bí mật của một phương thức MFA có thể đòi hỏi đăng ký lại thiết bị hoặc phương thức. Luồng này cần bảo đảm đúng người dùng thực hiện và phương thức cũ được vô hiệu hóa khi cần.

Một mã khôi phục đã bị lộ không trở nên an toàn chỉ vì người dùng đổi mật khẩu. Nếu cấp bộ mã khôi phục mới, phải xác định khả năng sử dụng của bộ cũ và thông báo phù hợp.

### 9.3. Refresh token rotation

Trong một thiết kế refresh token rotation, mỗi lần đổi token có thể trả refresh token mới và kết thúc khả năng sử dụng lại token trước đó theo quy tắc của hệ thống.

Đây là cơ chế gắn với mỗi lần sử dụng, khác với việc một nhóm vận hành định kỳ thay API key.

Cần xử lý đúng các trường hợp request đồng thời, mất response, retry và phát hiện token cũ bị dùng lại. Nếu có cơ chế phát hiện dùng lại và thu hồi chuỗi token liên quan, phạm vi và hành vi đó phải được định nghĩa rõ; không chỉ xóa một bản ghi mà vẫn để đường cấp token khác hoạt động ngoài dự kiến.

## 10. Rotation theo kế hoạch và rotation khi có sự cố

| Khía cạnh | Theo kế hoạch | Khi nghi ngờ bị lộ |
| --- | --- | --- |
| Mục tiêu trực tiếp | Quản lý vòng đời và thay thế có kiểm soát | Chặn sử dụng trái phép và khôi phục quyền kiểm soát |
| Chấp nhận đồng thời | Có thể dùng nếu được hỗ trợ và có giới hạn | Cần đánh giá nguy cơ tiếp tục chấp nhận bản cũ |
| Thứ tự thực hiện | Có thể chuẩn bị và kiểm tra trước khi thu hồi | Có thể phải thu hồi sớm, chấp nhận gián đoạn |
| Khả năng quay lại bản cũ | Chỉ khi vẫn an toàn và được kiểm soát | Không khôi phục một credential đã bị coi là lộ |
| Việc cần làm thêm | Xác nhận consumer và thu hồi | Điều tra nguồn lộ, truy cập đã xảy ra và cơ chế duy trì hiện diện |

Trong sự cố, cần kiểm tra đường phân phối credential mới. Nếu máy nhận hoặc tài khoản quản trị kho bí mật đang bị kiểm soát, credential mới có thể bị lộ ngay sau khi tạo.

Cũng cần xác định các quyền hoặc thông tin xác thực phát sinh từ credential cũ: token đã cấp, tài khoản được tạo thêm, khóa tích hợp mới hoặc thay đổi chính sách. Thay credential ban đầu không tự hoàn tác những thay đổi đó.

Việc thu hồi một access token hoặc khóa không thể lấy lại dữ liệu đã được tải trước đó. Rotation là một phần của khống chế và phục hồi, không phải thao tác xóa dấu vết hậu quả.

## 11. Tự động hóa bằng trạng thái và tiêu chí rõ ràng

Mã giả sau minh họa quy trình thay một credential workload khi bên xác minh hỗ trợ chuyển đổi có kiểm soát:

```text
function rotateCredential(credentialId):
    plan = loadAuthorizedRotationPlan(credentialId)
    requireNoConflictingRotation(plan)

    newVersion = prepareIndependentCredential(
        principal = plan.principal,
        allowedScope = plan.approvedScope
    )

    storeProtectedVersion(newVersion)
    configureVerifierForControlledTransition(plan, newVersion)
    publishVersionToAuthorizedConsumers(plan, newVersion)

    observations = collectConsumerTransitionEvidence(plan, newVersion)

    if not requiredConsumersMeetTransitionCriteria(observations):
        recordIncompleteRotation(plan, observations)
        applyApprovedFailureProcedure(plan)
        return INCOMPLETE

    stopAcceptingOldVersion(plan.oldVersion)
    verifyOldVersionIsRejected(plan.oldVersion)
    verifyNewVersionStillWorksWithinScope(newVersion)

    recordRotationCompleted(plan, newVersion)
    return COMPLETED
```

Hàm `applyApprovedFailureProcedure` không được hiểu là luôn bật lại bản cũ. Nó phải xét bản cũ còn an toàn không, thời hạn chuyển đổi và các giới hạn đã được chấp nhận.

Quy trình tự động cần chịu được việc tiến trình bị ngắt giữa chừng:

- Ghi lại phiên bản đã tạo và những bước đã hoàn thành.
- Dùng định danh lần chạy hoặc cơ chế tương đương để tránh tạo credential mới vô hạn khi retry.
- Không cho hai lượt rotation cùng thay phiên bản hiện hành mà không phối hợp.
- Khi tiếp tục, kiểm tra trạng thái thật ở bên xác minh và consumer.
- Tách lỗi cấp phát, lỗi phân phối và lỗi thu hồi để xử lý đúng.

Nếu bước thu hồi thất bại, không báo hoàn tất chỉ vì consumer đã dùng được bản mới. Trạng thái cần cho thấy bản cũ còn được chấp nhận và ai phải xử lý tiếp.

## 12. Bằng chứng hoàn thành và audit

Một lần rotation nên có đủ bằng chứng cho cả chuyển đổi thành công lẫn kết thúc sử dụng bản cũ.

Ví dụ audit không chứa bí mật:

```json
{
  "eventType": "CREDENTIAL_ROTATION_COMPLETED",
  "credentialId": "cred-report-exporter",
  "principalId": "workload-report-exporter",
  "oldVersionId": "version-12",
  "newVersionId": "version-13",
  "environment": "production",
  "oldVersionAcceptance": "DISABLED",
  "rotationRunId": "rotation-88",
  "result": "SUCCESS"
}
```

Tùy hệ thống, bổ sung người hoặc workload khởi tạo, phê duyệt, thời điểm, consumer đã chuyển và kết quả kiểm tra thu hồi.

Không cần ghi giá trị credential để chứng minh đã rotation. Việc ghi bí mật mới vào audit sẽ tạo thêm một nơi phải bảo vệ và thu hồi.

Các tín hiệu vận hành có ích gồm:

- Credential sắp hết hạn nhưng chưa có kế hoạch thay.
- Lần chạy bị treo trong giai đoạn chuyển đổi.
- Consumer vẫn xác thực bằng phiên bản cũ.
- Bản cũ vẫn được chấp nhận sau thời hạn.
- Credential không có chủ sở hữu.
- Lỗi xác thực tăng sau khi chuyển phiên bản.
- Có request dùng lại credential đã thu hồi.

Quan sát cần phân biệt “không thấy sử dụng gần đây” với “đã bị từ chối tại mọi bên xác minh thuộc phạm vi”. Hai bằng chứng này không tương đương.

## 13. Kiểm thử trước và sau khi thay thế

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Credential mới gọi hành động hợp lệ | Xác thực thành công trong đúng phạm vi |
| Credential mới gọi hành động ngoài nhiệm vụ | Không được cấp quyền rộng hơn |
| Bản cũ được sử dụng sau khi kết thúc chuyển đổi | Bị từ chối ở các bên xác minh liên quan |
| Một consumer chưa tải lại cấu hình | Được phát hiện trước khi báo hoàn tất |
| Một job ít chạy đến kỳ thực hiện | Có cách nhận bản mới, không phụ thuộc bí mật đã nghỉ |
| Tiến trình rotation bị ngắt rồi chạy lại | Tiếp tục đúng trạng thái, không tạo phiên bản vô hạn |
| Hai lượt rotation chạy đồng thời | Không làm sai phiên bản hiện hành hoặc thu hồi nhầm |
| Kết nối hoặc phiên cũ còn tồn tại | Hành vi đúng với chính sách thu hồi đã định |
| Bước thu hồi gặp lỗi | Không báo thành công hoàn toàn |
| Khóa ký cũ bị loại khỏi tập chấp nhận | Token dùng khóa đó không tiếp tục được tin ngoài chính sách |
| Credential cũ bị coi là đã lộ | Quy trình lỗi không tự bật lại bản đó |
| Kho bí mật hoặc log bị kiểm tra | Không xuất hiện giá trị bí mật trong dữ liệu quan sát không cần thiết |
| Cập nhật nhầm tenant hoặc môi trường | Không được chuyển đổi hoặc cấp quyền ngoài kế hoạch |

Ngoài kiểm tra xác thực, cần kiểm tra dữ liệu và tác vụ thực tế. Một service có thể xác thực thành công bằng key mới nhưng đang chạy với quyền rộng hơn hoặc trỏ nhầm môi trường.

## 14. Áp dụng vào report-exporter của An Bình

Nhóm vận hành xác định tất cả bản triển khai và job dùng `version-12`, xác nhận workload chỉ cần đọc dữ liệu báo cáo trong phạm vi đã cấp và chuẩn bị `version-13` với quyền phù hợp.

Nếu dịch vụ nhận hỗ trợ hai phiên bản, nhóm mở một giai đoạn chuyển đổi có giới hạn, cho consumer tải bản mới rồi xác nhận từng nhóm consumer hoạt động. Những kết nối và job giữ trạng thái cũ được xử lý theo vòng đời của chúng.

Sau đó, nhóm ngừng chấp nhận `version-12`, thử lại để xác nhận bản cũ bị từ chối, kiểm tra bản mới vẫn thực hiện đúng nhiệm vụ và ghi audit bằng định danh phiên bản.

Nếu phát hiện `version-12` đã bị lộ giữa quá trình, nhóm chuyển sang phương án khống chế sự cố, kiểm tra nguồn lộ và không dùng việc quay lại bí mật cũ làm cách phục hồi thông thường.

Credential rotation hoàn tất khi bản mới được sử dụng đúng danh tính và quyền, bản cũ kết thúc hiệu lực theo chính sách, và các bằng chứng vận hành xác nhận được cả hai điều đó.

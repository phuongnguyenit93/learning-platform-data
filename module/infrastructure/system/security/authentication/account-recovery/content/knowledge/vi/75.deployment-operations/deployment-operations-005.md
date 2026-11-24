# Triển khai blue-green cho luồng khôi phục tài khoản

Trong chương **Deployment Operations**, “Blue green recovery deployment” là cách phát hành một phiên bản mới của luồng khôi phục tài khoản bằng hai môi trường ứng dụng song song: **blue** đang phục vụ và **green** chuẩn bị thay thế. Traffic được chuyển sang green sau khi các điều kiện triển khai đạt yêu cầu, đồng thời blue được giữ trong một khoảng thời gian để hỗ trợ xử lý sự cố.

Đối với `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, mục tiêu không chỉ là giữ endpoint hoạt động trong lúc triển khai. Hệ thống phải tiếp tục khôi phục tài khoản an toàn khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Một challenge phát trước thời điểm chuyển traffic vẫn cần được xử lý đúng sau đó; token đã dùng không được sống lại; bằng chứng khôi phục không được cấp quyền rộng hơn; session bị thu hồi không được hoạt động trở lại khi rollback.

Blue-green giúp tách bước chuẩn bị phiên bản khỏi bước chuyển traffic. Nó không tự giải quyết tính tương thích dữ liệu, đồng bộ policy, sử dụng token một lần hay cạnh tranh giữa các request. Những đặc tính đó phải được thiết kế riêng và trở thành điều kiện cho phép cutover.

## 1. Hai màu ứng dụng, một trạng thái bảo mật có thẩm quyền

Một cách tổ chức thường dùng là hai nhóm ứng dụng cùng làm việc với trạng thái recovery có thẩm quyền:

```text
                   Tên miền recovery ổn định
                              |
                      Bộ định tuyến traffic
                       /               \
                  Blue                  Green
              phiên bản N           phiên bản N+1
                       \               /
                    Các dịch vụ có thẩm quyền
                  /          |             \
          Challenge store  Credential    Session/revocation
                  \          |             /
                 Policy, khóa, quota và hàng đợi
```

Sơ đồ thể hiện quan hệ logic, không bắt buộc mọi thành phần phải nằm trong một cơ sở dữ liệu. Điểm quan trọng là blue và green không được có hai cách nhìn độc lập về việc một challenge đã dùng hay một session đã bị thu hồi.

Nếu sao chép database production cho green rồi cho cả hai màu xử lý recovery thật trên hai bản sao, cùng một token có thể được chấp nhận một lần ở mỗi nơi. Tương tự, rollback bằng cách khôi phục database cũ có thể phục hồi token đã dùng và trạng thái credential trước khi người dùng đổi mật khẩu.

Nếu kiến trúc buộc phải chuyển cả tầng dữ liệu, cần một kế hoạch chuyển quyền ghi và nhất quán riêng: xác định writer có thẩm quyền, ngăn writer cũ tiếp tục ghi, chuyển trạng thái đầy đủ và kiểm chứng trước khi mở phục vụ. Đổi màu ứng dụng đơn thuần không phải kế hoạch di chuyển dữ liệu.

### 1.1. Phân biệt chuyển ứng dụng và thay đổi policy

Nên tách ba hoạt động khi có thể:

- Phát hành mã ứng dụng mới.
- Thay đổi policy khôi phục và yêu cầu bằng chứng.
- Đổi khóa, định dạng token hoặc quyền ghi dữ liệu.

Thay đồng thời cả ba làm khó xác định nguyên nhân lỗi và thu hẹp khả năng rollback. Nếu phải kết hợp, release manifest cần ghi rõ quan hệ phụ thuộc, phiên bản tối thiểu được phép xử lý và những thay đổi không thể đảo ngược bằng cách chuyển traffic.

### 1.2. Blue-green khác với bảo đảm chỉ một tiến trình chạy

Trong thời gian chuyển traffic, request cũ có thể còn đang chạy ở blue trong khi request mới đã đến green. Scheduler, consumer và job nền cũng có thể tiếp tục hoạt động ở cả hai màu. Thiết kế phải chịu được sự chồng lấn đó, không dựa vào giả định “chỉ có một màu nhìn thấy token”.

## 2. Vì sao recovery khó triển khai hơn một API đọc dữ liệu?

Recovery có các giao dịch kéo dài qua nhiều phút hoặc nhiều ngày. Người dùng nhận email trước cutover nhưng mở link sau cutover; một yêu cầu gỡ MFA đang chờ review có thể đi qua nhiều bản phát hành.

Các đường đi cần xét gồm:

| Thời điểm bắt đầu | Thời điểm tiếp tục | Tình huống phải hỗ trợ hoặc từ chối có kiểm soát |
|---|---|---|
| Blue phát challenge | Green xác minh | Green hiểu và áp dụng đầy đủ ràng buộc của challenge cũ |
| Green phát challenge | Blue nhận request sau rollback | Blue xử lý được định dạng và ngữ nghĩa mới, hoặc bị ngăn nhận loại request đó |
| Blue bắt đầu review | Green phê duyệt | Quyết định vẫn gắn đúng chủ thể, hành động và policy |
| Green đã thay mật khẩu | Chuyển traffic lại blue | Credential mới vẫn có hiệu lực; trạng thái cũ không được phục hồi |
| Một màu đã dùng token | Màu còn lại nhận retry | Không thực hiện lần thứ hai; phản hồi theo contract idempotency |
| Một màu yêu cầu thu hồi session | Màu còn lại phục vụ đăng nhập | Cùng tôn trọng trạng thái thu hồi có thẩm quyền |

Với passkey, việc triển khai không được làm mất challenge đăng ký, ngữ cảnh tài khoản hoặc quyền được đăng ký credential mới. Với MFA, một bản cũ không được vô tình xem bằng chứng reset mật khẩu là quyền gỡ MFA. Sự tương thích phải bao gồm **ý nghĩa cấp quyền**, không chỉ khả năng parse JSON.

## 3. Đặt các bất biến bảo mật trước khi chọn công cụ triển khai

Một kế hoạch blue-green cho recovery nên nêu rõ những điều không được vi phạm ở bất kỳ màu nào:

1. Mỗi challenge chỉ cấp quyền cho đúng chủ thể, tenant và hành động đã ràng buộc.
2. Một challenge không được hoàn tất thành công nhiều lần vì đổi màu, retry hoặc mất phản hồi.
3. Thời hạn đã lưu không tự kéo dài và ngân sách thử không tự reset khi chuyển phiên bản.
4. Policy và quyết định thu hồi hiện hành vẫn có hiệu lực tại ranh giới hoàn tất.
5. Trạng thái credential mới, factor mới và session bị thu hồi không bị đảo ngược bằng rollback traffic.
6. Các giới hạn chống lạm dụng không được nhân đôi chỉ vì có hai pool ứng dụng.
7. Link recovery luôn đưa người dùng đến origin tin cậy và không lộ token vào log vận hành.
8. Lỗi phụ thuộc không trở thành quyền bỏ qua xác minh.

Mỗi bất biến cần gắn với cơ chế thực thi. Ví dụ, “token một lần” cần thao tác chuyển trạng thái có tính nguyên tử ở backend có thẩm quyền; một câu kiểm tra `if (!used)` trong bộ nhớ của từng node không đủ.

## 4. Lập release manifest và ma trận tương thích

Trước khi mở green, cần biết chính xác nó sẽ gặp dữ liệu nào và blue có thể gặp dữ liệu nào sau rollback.

Một release manifest có thể chứa:

```yaml
release:
  id: recovery-release-042
  blueArtifact: recovery-app-N
  greenArtifact: recovery-app-N-plus-1

  compatibility:
    challengeFormatsRead:
      - recovery-v1
    challengeFormatWrite: recovery-v1
    eventFormatsRead:
      - recovery-event-v1
    eventFormatWrite: recovery-event-v1
    requiresExpandedSchema: true
    minimumSecurityEpoch: 12

  routing:
    publicOrigin: https://accounts.example.invalid
    switchApiTraffic: true
    switchRecoveryCallbacks: true
    switchBackgroundOwnership: separately-controlled

  rollback:
    trafficRollbackAllowed: true
    blueMustReadGreenWrites: true
    databaseRestoreAllowed: false
```

Đây là schema minh họa do hệ thống triển khai tự định nghĩa. Các trường không tự tạo ra bảo đảm; controller triển khai và người vận hành phải kiểm chứng điều kiện tương ứng. `databaseRestoreAllowed: false` nhắc rằng rollback của release này không được khôi phục một snapshot cũ lên trạng thái recovery đang hoạt động.

Ma trận tối thiểu nên xem xét:

| Thành phần | Green đọc trạng thái blue tạo | Blue đọc trạng thái green tạo | Điều kiện cho rollback trực tiếp |
|---|---|---|---|
| Challenge | Hiểu định dạng, purpose, expiry và trạng thái | Không bỏ qua ràng buộc mới | Hai chiều tương thích về ngữ nghĩa |
| Credential | Đọc được kiểu và tham số cần thiết | Xác minh được credential mới | Không tạo credential mà blue xử lý sai |
| Policy | Hiểu điều kiện bắt buộc | Không bỏ qua điều kiện mới | Blue còn đáp ứng policy tối thiểu |
| Event | Consumer hiểu event cũ | Consumer cũ xử lý event mới đúng | Có contract rõ cho retry và phiên bản |
| Session | Tôn trọng revocation cũ | Tôn trọng revocation mới | Dùng cùng nguồn thu hồi có thẩm quyền |
| Review | Đọc được bằng chứng và quyết định | Không làm giảm yêu cầu phê duyệt | Mô hình trạng thái tương thích |

Nếu một ô không đạt, không nên ghi chung “rollback được”. Có thể giữ định dạng ghi cũ trong giai đoạn đầu, tách rollout capability hoặc loại blue khỏi đường hoàn tất nhạy cảm. Khi không thể quay lại blue an toàn, kế hoạch cần xác định phương án tiến lên bằng bản sửa và khả năng tạm hạn chế thao tác chịu ảnh hưởng.

## 5. Tiến hóa database theo expand–migrate–contract

Blue-green thường cần một khoảng thời gian cả phiên bản cũ và mới cùng hoạt động. Những thay đổi schema phá vỡ phiên bản cũ không phù hợp với khoảng chồng lấn này.

Một trình tự có thể áp dụng:

```text
EXPAND: thêm cấu trúc tương thích
    → triển khai ứng dụng đọc được cả trạng thái cũ và mới
    → MIGRATE: chuyển dữ liệu có kiểm soát
    → xác nhận không còn writer/reader cũ cần hỗ trợ
    → CONTRACT: bỏ cấu trúc cũ trong đợt riêng
```

Ví dụ, hệ thống muốn thêm `authorization_scope` cho recovery. Chỉ thêm một cột nullable không đủ để bảo đảm an toàn. Cần trả lời: challenge cũ không có trường này được hiểu là quyền gì? Blue có thể ghi thêm challenge thiếu scope không? Green có đang diễn giải giá trị thiếu thành quyền rộng hơn không?

Một cách chuyển tiếp là định nghĩa rõ định dạng cũ chỉ tương ứng một hành động hẹp đã biết, từ chối trường hợp không suy ra an toàn và giữ định dạng ghi có tương thích trong cửa sổ rollback. Nếu không thể diễn giải dữ liệu cũ mà không đoán quyền, cần yêu cầu bắt đầu lại cho nhóm challenge đó theo chính sách được phê duyệt.

### 5.1. Migration không được tạo lại quyền đã mất

Backfill phải giữ nguyên `consumedAt`, `revokedAt`, số lần thử và thời hạn. Không biến giá trị không đọc được thành trạng thái `PENDING` rồi cho phép xác minh lại. Mọi phép chuyển trạng thái cần có quy tắc và khả năng kiểm tra số lượng bản ghi bị ảnh hưởng.

Backfill cũng có thể cạnh tranh với request thật. Dùng điều kiện cập nhật phù hợp để không ghi đè trạng thái mới hơn; kiểm soát tải, lock và độ trễ trên backend recovery. Một migration đúng về kết quả cuối nhưng làm backend giới hạn thử quá tải vẫn có thể gây sự cố luồng xác thực.

### 5.2. Contract phải chờ tất cả bên tiêu thụ

Không chỉ API server mới cần schema. Consumer chậm, job hỗ trợ, công cụ review hoặc bản blue còn giữ để rollback cũng có thể phụ thuộc trường cũ. Chỉ loại bỏ cấu trúc sau khi đã xác nhận không còn bên cần nó và chính thức đóng cửa sổ tương thích tương ứng.

## 6. Giữ vòng đời token và challenge xuyên qua cutover

Link recovery nên dùng tên miền ổn định, chẳng hạn:

```text
https://accounts.example.invalid/recovery/continue?token=<opaque-token>
```

Không nhúng tên host của blue hoặc green vào link gửi cho người dùng. Nếu link cũ trỏ trực tiếp đến một màu, việc tắt màu đó sẽ làm recovery phụ thuộc vòng đời triển khai. Với nhiều origin hoặc domain theo tenant, ánh xạ phải được xác minh và kiểm soát ở tầng tin cậy.

### 6.1. Trạng thái cần nằm ngoài bộ nhớ của từng màu

Một challenge có thể cần lưu các thuộc tính như:

```text
challengeId, tokenDigest
subjectId, tenantId, purpose
formatVersion, policyRevisionAtIssue, securityEpochAtIssue
issuedAt, expiresAt, attemptCount, attemptBudget
evidenceState, reviewState
consumedAt, revokedAt, stateVersion
```

Lưu `expiresAt` do server quyết định, thay vì tính lại từ TTL của phiên bản đang xử lý. Việc thay bản ứng dụng không được cấp thêm thời gian hoặc lượt thử.

Nếu một bước tạm thời cần cookie hoặc session trước đăng nhập, hai màu phải hiểu được định dạng, cơ chế bảo vệ và chính sách của trạng thái đó trong cửa sổ tương thích. Sticky routing có thể cải thiện trải nghiệm nhưng không thay thế thiết kế trạng thái dùng chung hoặc khả năng đọc liên phiên bản.

### 6.2. Đường kiểm tra token không được tạo thêm khóa tin cậy tùy ý

Nếu token dựa vào chữ ký hoặc MAC, green cần kiểm tra được artifact còn hợp lệ theo tập khóa được phép. Thông tin chọn khóa trong token chỉ được ánh xạ vào keyring server tin cậy; không cho token chỉ định một URL hoặc đường dẫn secret tùy ý.

Không đổi khóa bắt buộc chỉ vì đổi màu. Tách vòng đời khóa khỏi vòng đời process giúp kiểm soát artifact đang tồn tại. Nếu đồng thời thu hồi khóa do sự cố, quyền chấp nhận artifact cũ phải tuân theo quyết định thu hồi, kể cả khi bản blue từng chấp nhận nó.

Với token opaque lưu trạng thái server, không cần giả định có khóa ký. Green phải dùng được cơ chế tra cứu và kiểm tra digest theo thiết kế. Dù dùng dạng nào, việc parse được token không thay thế kiểm tra trạng thái một lần, purpose, tenant và quyền hoàn tất.

### 6.3. Điểm hoàn tất phải có tính quyết định chung

Hai màu có thể cùng nhận một token gần như đồng thời. Cả hai đều có thể đọc thấy trạng thái chưa dùng nếu chỉ kiểm tra trước rồi cập nhật sau.

Thao tác nghiệp vụ cần một ranh giới có tính nguyên tử hoặc một state machine bền vững bảo đảm chỉ một bên giành được quyền hoàn tất. Ví dụ SQL giả mã sau chỉ minh họa việc giành quyền chuyển trạng thái; nó không phải toàn bộ giao dịch đổi credential:

```sql
UPDATE recovery_challenge
SET state = 'COMPLETING',
    state_version = state_version + 1,
    completion_operation_id = :operation_id
WHERE challenge_id = :challenge_id
  AND state = 'VERIFIED'
  AND state_version = :expected_version
  AND expires_at > :server_now
  AND revoked_at IS NULL;
```

Nếu không cập nhật được đúng một bản ghi, request không được tự thực hiện thay credential như thể đã thắng. Điều kiện xác minh bằng chứng, quyền hiện hành và thu hồi phải được kiểm tra trong thiết kế ranh giới cấp quyền tương ứng; câu SQL trên không bao gồm tất cả điều kiện đó.

Nếu challenge và credential cùng nằm trong một transaction phù hợp, có thể gắn chuyển trạng thái với thay đổi credential. Nếu phải gọi dịch vụ ngoài, cần trạng thái trung gian, operation ID bền vững, cơ chế tiếp tục hoặc đối soát và tính idempotent ở bên thực thi. Đánh dấu token đã dùng rồi gọi dịch vụ không có khả năng tiếp tục có thể khiến người dùng bị kẹt; gọi dịch vụ trước rồi mới đánh dấu có thể cho phép tác động lặp.

Một lỗi timeout không chứng minh giao dịch thất bại. Request retry phải kiểm tra operation cũ hoặc trạng thái có thẩm quyền, không cấp lại quyền vì chưa nhận được phản hồi.

## 7. Credential, MFA, passkey và session phải giữ cùng ngữ nghĩa

Thay đổi mật khẩu, gỡ MFA và cho phép đăng ký passkey mới là các hành động khác nhau. Blue và green phải thống nhất quyền nào đã được cấp và hậu điều kiện nào bắt buộc trước khi tuyên bố hoàn tất.

### 7.1. Không đổi ngầm mô hình quyền trong cửa sổ rollback

Giả sử green tạo một grant “chỉ được đăng ký lại passkey”, nhưng blue diễn giải cùng trường là “đã xác minh toàn bộ tài khoản”. Dù hai bản cùng đọc được dữ liệu, rollback sẽ mở rộng quyền. Đây là lỗi tương thích bảo mật.

Với định dạng grant mới, cần kiểm tra phiên bản cũ hiểu đúng hoặc bảo đảm nó không được xử lý loại grant đó. Trạng thái không hiểu phải bị từ chối có kiểm soát; không lấy giá trị mặc định để cấp quyền rộng hơn.

### 7.2. Trạng thái thu hồi không được chỉ nằm trong cache của một màu

Một kiến trúc có thể dùng `authVersion` hoặc mốc thu hồi theo tài khoản. Sau recovery, mốc có thẩm quyền tăng và đường xác thực phải áp dụng quy tắc tương ứng. Blue và green phải đọc hoặc kiểm tra trạng thái này theo contract về độ trễ và nhất quán đã được chọn.

Việc tăng một số trong database không tự làm access token tự chứa bị vô hiệu ngay lập tức. Nếu gateway hoặc dịch vụ xác thực không kiểm tra mốc đó, token có thể tiếp tục được chấp nhận theo thiết kế hiện tại. Kế hoạch release phải xác định nơi thực thi thu hồi, cửa sổ chậm trễ được phép và hành vi khi backend thu hồi không khả dụng.

Không đánh dấu recovery hoàn tất với lời hứa “session cũ đã bị thu hồi” nếu hệ thống mới chỉ enqueue một event. Nếu kiến trúc cần xử lý bất đồng bộ, dùng trạng thái và quyền truy cập phản ánh đúng hậu điều kiện chưa hoàn tất; quy định khi nào người dùng có thể đăng nhập hoặc thay đổi yếu tố tiếp theo.

### 7.3. Không mang quyền khôi phục sang session thông thường ngoài ý muốn

Nếu hệ thống dùng session giới hạn cho recovery, cookie và dữ liệu session cần biểu diễn đúng purpose, thời hạn và bước đã đạt. Khi green nhận cookie của blue hoặc ngược lại, không được diễn giải một phiên recovery thành phiên đăng nhập đầy đủ.

Nếu luồng yêu cầu đăng nhập lại sau recovery, cả hai màu phải tuân thủ. Một bản cũ tự đăng nhập sau reset mật khẩu có thể phá chính sách mới dù bước thay credential đã đúng.

## 8. Giới hạn chống lạm dụng phải hoạt động trên toàn bộ hai màu

Tăng gấp đôi số instance không được làm tăng gấp đôi ngân sách đoán mã hoặc phát link. Các giới hạn theo tài khoản, challenge và phạm vi liên quan cần dùng trạng thái hoặc dịch vụ thực thi chung có tính nhất quán phù hợp.

Ví dụ, nếu mỗi màu cho năm lần thử cùng một challenge bằng bộ đếm cục bộ, người tấn công có thể nhận thêm lượt khi đổi tuyến. Một cấu hình threshold giống nhau ở hai màu không đồng nghĩa có một ngân sách chung.

Cần kiểm tra:

- Cách chuẩn hóa chủ thể và xây khóa giới hạn có tương thích giữa hai bản không?
- Tenant và purpose có được đưa vào phạm vi đúng không?
- Counter có bị tạo lại dưới namespace mới sau release không?
- Blue có tự đặt lại số lần thử mà green đã ghi không?
- Khi backend giới hạn lỗi, cả hai màu có cùng hành vi hạn chế phù hợp không?

Giới hạn ở từng instance có thể bảo vệ tải cục bộ, nhưng không nên là cơ chế duy nhất bảo vệ ngân sách thử toàn tài khoản. Cũng cần tránh việc một yêu cầu độc hại gây khóa toàn bộ khả năng recovery của nạn nhân quá dễ dàng; lựa chọn phản ứng cần xét cả rủi ro chiếm đoạt và từ chối dịch vụ.

Nếu phải đổi thuật toán hoặc namespace limiter, cần kế hoạch chuyển trạng thái hoặc ràng buộc kết hợp trong giai đoạn chuyển tiếp. Không mặc định rằng bộ đếm mới rỗng là một thay đổi vô hại.

## 9. Consumer, scheduler và thông báo cũng có màu triển khai

Cutover ở load balancer thường chỉ thay đường HTTP. Nó không dừng scheduler trong blue hoặc đổi consumer đang đọc hàng đợi. Nếu khởi động green với toàn bộ job tự chạy, cả hai màu có thể cùng xử lý các tác vụ định kỳ hoặc cùng nhận một event sau redelivery.

### 9.1. Phân biệt có quyền chạy job và xử lý job không trùng tác động

Leader election hoặc lease giúp xác định bên được lên lịch, nhưng không bảo đảm một consumer cũ đã mất lease lập tức ngừng mọi tác động. Khi cần ngăn writer cũ, có thể dùng cơ chế fencing: cấp một thế hệ quyền tăng dần và yêu cầu nơi nhận ghi từ chối thế hệ cũ. Cơ chế này chỉ có tác dụng nếu backend thực sự kiểm tra token hoặc thế hệ tương ứng.

Dù đã phân quyền scheduler, từng tác động quan trọng vẫn cần idempotency bền vững. Queue có thể giao lại message sau timeout; process có thể chết sau khi đã gọi provider nhưng trước khi ack.

### 9.2. Dùng operation ID cho tác động nghiệp vụ

Một thông báo hoặc tác vụ thu hồi có thể mang định danh như:

```json
{
  "eventId": "evt-1042",
  "eventVersion": "recovery-event-v1",
  "operationId": "recovery-op-8421",
  "challengeId": "challenge-7319",
  "eventType": "RECOVERY_COMPLETION_NOTIFICATION_REQUESTED",
  "policyRevision": 184
}
```

Đây là ví dụ về metadata, không chứa token hay bằng chứng danh tính. Payload thật cần quyền truy cập và chính sách dữ liệu phù hợp. `operationId` phải gắn với tác động đã được cấp quyền, không chỉ là một request ID mới sinh mỗi lần retry.

Consumer nên tra cứu trạng thái cần thiết, kiểm tra tác vụ còn được phép và xử lý việc nhận trùng. Nếu provider hỗ trợ idempotency, ánh xạ định danh ổn định theo contract của provider. Nếu provider không hỗ trợ, cần thiết kế để giảm và xử lý gửi trùng; không tuyên bố bảo đảm gửi đúng một lần chỉ vì đã lưu một cờ ở phía ứng dụng.

### 9.3. Outbox không thay thế idempotency của bên nhận

Transactional outbox có thể giúp ghi thay đổi nghiệp vụ và ý định phát event trong cùng transaction ở nơi phù hợp. Relay vẫn có thể phát lại. Consumer và dịch vụ nhận cần chịu được lặp, đặc biệt với thu hồi session, thay credential hoặc cấp grant đăng ký factor.

Retry gửi email không được phát lại challenge mới ở mỗi lần chạy. Với event cũ sau cutover, consumer cũng không được bỏ qua lệnh thu hồi hiện hành chỉ vì event được tạo ở revision trước.

## 10. Readiness của green phải phản ánh khả năng phục vụ recovery

Một tiến trình trả HTTP 200 ở `/health` chưa chứng minh có thể tham gia recovery. Nên phân biệt:

| Loại kiểm tra | Mục đích | Ví dụ |
|---|---|---|
| Liveness | Tiến trình còn có khả năng hoạt động cơ bản | Event loop hoặc thành phần cốt lõi không bị kẹt |
| Readiness | Có được nhận một nhóm traffic cụ thể không? | Đúng policy, schema và quyền truy cập bắt buộc |
| Kiểm tra chức năng | Luồng thực tế có đúng contract không? | Token do blue phát được green xử lý đúng |
| Gate cutover | Toàn hệ thống đủ điều kiện đổi màu không? | API, worker, routing và rollback cùng đạt yêu cầu |

Tránh biến mọi lỗi provider tạm thời thành liveness failure khiến toàn bộ process liên tục restart. Cần quy định dependency nào ảnh hưởng readiness của thao tác nào, thao tác nào có thể hoãn và thao tác nào phải bị chặn.

### 10.1. Green cần được chuẩn bị mà chưa có quyền ghi ngoài ý muốn

Trong giai đoạn kiểm tra, giới hạn quyền chạy scheduler hoặc consumer theo kế hoạch. Làm rõ probe nào chỉ đọc và probe nào tạo dữ liệu. Một probe readiness không nên gửi link recovery thật hoặc thay mật khẩu mỗi lần được gọi.

Nếu dùng tài khoản kiểm thử trong production, tài khoản đó phải thuộc phạm vi kiểm soát và có cách làm sạch trạng thái đúng quy trình. Dữ liệu thử không được là tài khoản người dùng thật. Không cần sao chép secret hoặc bằng chứng cá nhân production sang môi trường phụ chỉ để có bài kiểm tra giống thật.

### 10.2. Health endpoint không phải nơi xuất secret

Có thể trả trạng thái policy revision, artifact ID và khả năng phục vụ, nhưng không trả token, keyring đầy đủ, credential provider hoặc cấu hình nhạy cảm. Trang vận hành chi tiết cần quyền riêng; endpoint dùng cho routing chỉ nên có thông tin tối thiểu cần thiết.

## 11. Quy trình cutover theo từng cổng quyết định

Một runbook có thể gồm các bước sau. Những bước thay đổi trạng thái cần có người hoặc hệ thống chịu trách nhiệm rõ ràng, cùng điều kiện dừng đã định trước.

### Bước 1 — Xác định phạm vi và cửa sổ tương thích

Chốt artifact, policy yêu cầu, định dạng challenge/event, schema và phụ thuộc. Xác định blue có được xử lý dữ liệu green tạo trong cửa sổ rollback không. Liệt kê thay đổi không thể đảo ngược bằng traffic.

### Bước 2 — Chuẩn bị hạ tầng và schema tương thích

Thực hiện phần expand cần thiết và xác minh blue vẫn hoạt động. Chuẩn bị green với quyền tối thiểu, config đúng môi trường và các tham chiếu secret hợp lệ. Không mở toàn bộ job nền một cách mặc định.

### Bước 3 — Kiểm tra liên phiên bản

Kiểm tra challenge từ blue sang green, retry liên màu, policy thu hồi, quota và các trạng thái review. Kiểm tra chiều green sang blue nếu tuyên bố hỗ trợ rollback trực tiếp. Bằng chứng phải bao gồm ngữ nghĩa quyền, không chỉ response thành công.

### Bước 4 — Chuẩn bị routing và tác vụ nền

Xác định toàn bộ lối vào: API phát challenge, trang tiếp tục, endpoint hoàn tất, callback provider, công cụ review và đường gọi nội bộ. Chuyển một route nhưng bỏ sót route hoàn tất có thể khiến request đi qua hai phiên bản không tương thích.

Quyền chạy consumer hoặc scheduler cần được chuyển hoặc cho chồng lấn theo cơ chế đã kiểm chứng. Không giả định cấu hình load balancer sẽ làm thay phần này.

### Bước 5 — Chuyển traffic

Kích hoạt route theo cơ chế triển khai đã chọn và quan sát màu thực tế đang xử lý request. Blue-green có thể có một bước kiểm tra giới hạn trước khi chuyển toàn bộ, nhưng nếu chia tỷ lệ traffic thì phải chịu được cùng lúc hai phiên bản ở đường nghiệp vụ.

Không dựa duy nhất vào việc sửa DNS để suy ra traffic đã chuyển hoàn toàn. Cache, resolver, kết nối tồn tại và đường gọi nội bộ có thể giữ đường cũ. Định nghĩa điểm kiểm soát traffic thực tế và cách chứng minh các backend nào còn nhận request.

### Bước 6 — Drain blue

Ngừng nhận request mới theo kế hoạch, cho request đang chạy kết thúc hoặc được xử lý lại theo contract. Theo dõi transaction, consumer, lease, callback và kết nối lâu. Bảo đảm retry sang green không lặp tác động đã commit ở blue.

### Bước 7 — Xác minh sau chuyển đổi

Kiểm tra outcome nghiệp vụ, lỗi theo phiên bản, thời gian xác minh, tác vụ thu hồi và độ trễ thông báo. Xác nhận không có node cũ tiếp tục cấp quyền trái policy hoặc ghi theo schema không còn được phép.

### Bước 8 — Đóng cửa sổ rollback và dọn phiên bản cũ

Chỉ tắt hẳn blue khi đã đạt điều kiện quan sát, xử lý request đang chạy và quyết định tương thích. Các bước contract schema hoặc bật định dạng ghi mới có thể được thực hiện ở đợt sau, khi không còn kỳ vọng quay lại blue.

## 12. Drain không đồng nghĩa chờ mọi link hết hạn

Cần phân biệt **request đang xử lý ở process** với **recovery đang chờ người dùng**.

Request đang chạy cần thời gian để kết thúc transaction hoặc đi vào trạng thái bền vững có thể tiếp tục. Một link đang nằm trong hộp thư không nên buộc process blue tồn tại suốt TTL nếu green đã hỗ trợ đúng trạng thái và định dạng đó.

Ngược lại, chỉ đợi một timeout HTTP rồi tắt blue cũng không đủ nếu job nền giữ trạng thái trong RAM hoặc callback của provider trỏ trực tiếp vào host blue.

Điều kiện drain hoàn tất nên xét:

- Blue không còn nhận request mới ngoài những đường được giữ có chủ đích.
- Không còn transaction quan trọng ở trạng thái chưa biết kết quả mà chưa có cách đối soát.
- Công việc nền đã xong, đã được giao lại an toàn hoặc còn quyền chạy theo kế hoạch rõ ràng.
- Quyền writer hoặc scheduler cũ đã bị thu hồi và backend thực thi được việc đó nếu có fencing.
- Callback và link công khai không phụ thuộc vào host blue sắp tắt.
- Trạng thái tạm cần tiếp tục đã được lưu ở nơi phiên bản còn hoạt động hiểu được.

Thời gian giữ blue để quan sát rollback là một quyết định vận hành khác thời gian drain. Đặt cửa sổ theo rủi ro, dạng lưu lượng và bằng chứng tương thích; không dùng một con số chung như thể mọi hệ thống recovery đều có cùng vòng đời.

## 13. Rollback sau khi có tác động bảo mật

Rollback traffic là đưa request tương lai về một phiên bản khác. Nó không hoàn tác những hành động hợp lệ đã xảy ra.

Xét chuỗi sự kiện:

```text
10:00  Blue phát challenge C theo policy hợp lệ.
10:05  Traffic chuyển sang green.
10:06  Green dùng C để hoàn tất reset mật khẩu qua operation O.
10:06  Credential mới được ghi; các hậu điều kiện được xử lý theo thiết kế.
10:07  Phát hiện lỗi giao diện ở green và chuyển traffic về blue.
10:08  Người dùng hoặc kẻ tấn công gửi lại C.
```

Blue phải thấy C đã được sử dụng hoặc đang thuộc operation O và không cấp một lần reset mới. Nó cũng phải dùng credential mới và tôn trọng trạng thái session đã thu hồi. Khôi phục database tại 10:00 để “đồng bộ với blue” sẽ phá các bảo đảm này.

### 13.1. Điều kiện cho rollback trực tiếp

Chỉ chọn quay traffic về blue khi có bằng chứng rằng:

1. Blue còn đáp ứng policy và mốc bảo mật tối thiểu đang có hiệu lực.
2. Blue đọc và xử lý đúng mọi trạng thái green đã ghi mà nó sẽ gặp.
3. Không có thay đổi schema hoặc định dạng credential khiến blue diễn giải sai.
4. Session, quota và trạng thái sử dụng token vẫn dùng nguồn có thẩm quyền.
5. Worker, callback và routing có kế hoạch chuyển tương ứng.

Nếu một điều kiện không đạt, giữ đường an toàn cho các thao tác còn khả dụng, hạn chế thao tác chịu ảnh hưởng và triển khai bản sửa phù hợp. Quay về một bản không hiểu yêu cầu bảo mật mới không phải rollback an toàn chỉ vì bản đó từng hoạt động ổn định.

### 13.2. Không nhầm rollback lỗi vận hành với thu hồi do xâm phạm

Nếu green bị nghi xâm phạm, cách xử lý có thể cần thu hồi secret, artifact, epoch hoặc challenge bị ảnh hưởng, đồng thời điều tra tác động. Chuyển traffic về blue không xóa quyền truy cập mà kẻ tấn công đã có.

Nếu một khóa hoặc kênh đã bị thu hồi, blue phải tuân theo quyết định mới. Không khôi phục config cũ để làm nó hoạt động lại. Policy rollback cần revision mới với những ràng buộc bắt buộc còn được giữ.

## 14. Kiểm tra những cuộc đua mà cutover tạo ra

Bộ kiểm tra nên tập trung vào hành vi đi qua ranh giới phiên bản và trạng thái, thay vì chỉ chạy happy path riêng ở green.

| Kịch bản | Điều cần chứng minh |
|---|---|
| Blue phát, green xác minh | Giữ đúng expiry, purpose, tenant và bằng chứng |
| Green phát, rollback về blue | Xử lý đúng hoặc định tuyến/từ chối theo contract đã công bố |
| Hai màu dùng cùng token đồng thời | Chỉ một operation được quyền hoàn tất |
| Commit thành công nhưng mất phản hồi | Retry không tạo thêm thay đổi credential |
| Token hết hạn đúng lúc chuyển màu | Không được sống lại do TTL hoặc clock khác nhau |
| Đổi revision khi đã thử gần hết ngân sách | Không cấp lại lượt thử ngoài policy migration |
| Thu hồi epoch trong lúc request đang chạy | Không hoàn tất bằng quyền vừa bị thu hồi |
| Redelivery event sau khi đổi consumer | Không tạo lại challenge hoặc cấp grant trùng |
| Session vừa bị thu hồi rồi rollback | Phiên cũ không được chấp nhận trái contract thu hồi |
| Blue giữ kết nối hoặc route cũ | Không tiếp tục thực thi policy đã bị cấm |
| Green không truy cập được limiter | Không biến lỗi dependency thành quyền thử không giới hạn |
| Review đang chờ qua nhiều phiên bản | Không mất bằng chứng và không bỏ điều kiện phê duyệt |

Kiểm tra thời gian bằng một nguồn thời gian có thể điều khiển ở môi trường thử nghiệm giúp tái hiện biên hết hạn. Trong production, cần contract về nguồn thời gian và xử lý lệch đồng hồ; không lấy thời gian client làm căn cứ cho quyền sử dụng token.

### 14.1. Shadow traffic phải tránh phát lại tác động

Không sao chép nguyên request hoàn tất recovery sang green đang kết nối trạng thái thật chỉ để so response. Bản shadow có thể tiêu thụ token, đổi credential hoặc gửi thông báo.

Nếu cần so quyết định, dùng dữ liệu tổng hợp hoặc chế độ đánh giá chỉ đọc đã được thiết kế rõ và giới hạn quyền ghi ở tầng phù hợp. Không đưa token thật hoặc bằng chứng danh tính vào hệ thống lưu traffic chỉ để tiện debug. Một flag `dryRun` ở ứng dụng chưa đủ nếu một nhánh vẫn gọi provider hoặc ghi qua thư viện ngoài.

## 15. Quan sát cutover mà không tiết lộ bí mật

Quan sát theo màu, artifact và giai đoạn nghiệp vụ giúp phân biệt lỗi rollout với thay đổi lưu lượng. Những chỉ số có ích gồm:

- Tỷ lệ phát challenge và lỗi provider.
- Tỷ lệ xác minh thành công, hết hạn, vượt ngân sách hoặc bị thu hồi.
- Thời gian hoàn tất và số operation ở trạng thái trung gian quá lâu.
- Xung đột khi giành quyền hoàn tất và số retry đã nhận diện là cùng operation.
- Độ trễ event, tác vụ thu hồi session và số lỗi chưa được đối soát.
- Revision đang áp dụng, node chưa đạt policy tối thiểu và tác vụ còn chạy ở blue.

Một mã lỗi tổng hợp như `RECOVERY_CHALLENGE_REJECTED` nên được phân loại nội bộ đủ để điều tra, nhưng phản hồi người dùng cần phù hợp với mục tiêu chống dò tài khoản và không lộ chi tiết factor.

Log có thể ghi challenge ID nội bộ hoặc operation ID đã được kiểm soát truy cập cùng phiên bản triển khai. Không ghi token, OTP, recovery code, URL đầy đủ chứa token, credential hoặc nội dung bằng chứng danh tính. Reverse proxy và hệ thống tracing cũng cần cấu hình giảm hoặc loại bỏ query nhạy cảm.

Ngưỡng tạm dừng rollout cần xuất phát từ baseline và mức rủi ro của hệ thống. Một tỷ lệ lỗi tổng thấp vẫn có thể che lỗi nghiêm trọng ở luồng gỡ MFA ít dùng. Quan sát theo hành động quan trọng, đồng thời tránh label chứa user ID hoặc tenant ID không giới hạn làm metric tăng kích thước không kiểm soát.

## 16. Các sai lầm làm blue-green trở thành đường hạ cấp bảo mật

### Chỉ đổi load balancer rồi coi như đã triển khai xong

API có thể đã ở green nhưng consumer, scheduler, công cụ review và callback vẫn đi theo blue. Cần bản đồ lối vào và quyền thực thi cho từng loại tác động.

### Dùng database riêng rồi đồng bộ sau

Với trạng thái token một lần và credential, việc “đồng bộ sau” có thể để cả hai bên cấp quyền từ cùng bằng chứng. Cần một authority và giao thức chuyển writer hoặc nhất quán phù hợp, không chỉ sao chép dữ liệu nền.

### Giữ blue nhưng cho nó bỏ qua yêu cầu mới

Một bản còn chạy để rollback vẫn cần đáp ứng policy hiện hành. Khả năng parse dữ liệu không cho phép bỏ qua purpose, review hoặc epoch chưa hiểu.

### Đổi TTL, token format và schema cùng một lần mà không có ma trận

Khi phát sinh lỗi, không biết artifact nào còn đọc được và bản nào được phép xử lý. Tách thay đổi hoặc ghi rõ quan hệ tương thích hai chiều trước cutover.

### Reset counter và cache cho sạch khi chuyển màu

Làm mới bộ đếm có thể tăng ngân sách tấn công; xóa cache thu hồi sai cách có thể làm session cũ được chấp nhận. Phân biệt cache có thể tái tạo an toàn với trạng thái bảo mật có thẩm quyền.

### Rollback bằng snapshot database

Snapshot cũ không chứa các token đã dùng, credential mới hoặc quyết định thu hồi phát sinh sau snapshot. Khôi phục dữ liệu là quy trình phục hồi sự cố riêng với kiểm soát nghiệp vụ và bảo mật, không phải thao tác thường quy để quay màu ứng dụng.

## 17. Câu hỏi tự kiểm tra

1. Nếu một link được blue phát trước cutover và được mở sau khi blue đã tắt, thành phần nào tiếp tục xử lý và lấy trạng thái ở đâu?
2. Bằng chứng nào cho thấy blue có thể xử lý đúng dữ liệu green đã ghi sau rollback?
3. Hai request ở hai màu cùng dùng một token bị phân xử bởi cơ chế nào?
4. Nếu người dùng đã đổi mật khẩu thành công ở green nhưng mất phản hồi, retry ở blue sẽ thấy trạng thái gì?
5. Counter giới hạn thử, quyết định thu hồi session và epoch có được duy trì xuyên phiên bản không?
6. Ai đang chạy scheduler và consumer trong từng giai đoạn; điều gì ngăn một worker cũ tiếp tục tác động sau khi mất quyền?
7. Có route, cookie, callback hoặc trạng thái trong RAM nào đang buộc recovery phụ thuộc vào một màu không?
8. Khi blue không còn đáp ứng policy tối thiểu, runbook sẽ xử lý sự cố green theo cách nào?

Triển khai blue-green cho recovery đạt mục tiêu khi traffic có thể chuyển giữa các phiên bản mà quyền đã cấp, quyền đã thu hồi và trạng thái của từng lần khôi phục vẫn được giữ đúng. Khả năng quay màu chỉ có giá trị khi phiên bản được quay về tiếp tục thực thi đầy đủ những điều kiện bảo mật đang có hiệu lực.

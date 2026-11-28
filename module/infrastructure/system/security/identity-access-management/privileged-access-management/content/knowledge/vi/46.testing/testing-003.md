# Test rotation

## 1. Mục tiêu của kiểm thử rotation trong PAM

**Rotation** là quá trình thay một credential đang được sử dụng bằng credential mới, đồng thời chuyển các bên sử dụng sang bản mới và xử lý hiệu lực của bản cũ theo chính sách. Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), credential có thể là mật khẩu tài khoản quản trị, mật khẩu tài khoản dịch vụ, khóa SSH hoặc thông tin xác thực dùng để kết nối hạ tầng nhạy cảm.

**Test rotation** không chỉ kiểm tra một job có trả về trạng thái thành công hay không. Bài kiểm thử phải chứng minh được các điều kiện:

- Credential mới xác thực được trên đúng hệ thống đích.
- Các ứng dụng, tác vụ và người dùng được phép đã sử dụng được credential mới.
- Credential cũ không còn tạo được truy cập mới sau thời điểm chính sách yêu cầu.
- Quyền của danh tính được giữ đúng phạm vi, không tăng lên vì thao tác thay credential.
- Các lỗi, lần thử lại và tác vụ cạnh tranh không làm PAM mất khả năng xác định credential nào đang có hiệu lực.
- Có bằng chứng truy vết kết quả mà không làm lộ secret.

Ví dụ, PAM thông báo đã đổi mật khẩu của tài khoản dịch vụ `svc-report-lab`. Một ứng dụng vẫn chạy bình thường nhờ connection pool mở từ trước. Nếu chỉ nhìn vào màn hình PAM và tình trạng ứng dụng, người kiểm thử có thể kết luận sai rằng rotation đã thành công. Chỉ khi ứng dụng mở kết nối mới bằng credential lấy từ đường cấp phát chuẩn mới có thể kiểm tra quá trình chuyển đổi thực tế.

Mục tiêu của bài này là xây dựng cách kiểm thử rotation có thể lặp lại, phân biệt thành công thật với thành công bề ngoài và xử lý được những trạng thái không chắc chắn.

## 2. Xác định chính xác loại rotation

Các loại credential không có cùng cơ chế thay thế. Test case phải bám vào cơ chế của hệ thống đích, không áp một tiêu chí duy nhất cho mọi loại secret.

| Loại credential | Thay đổi cần kiểm tra | Điểm dễ kết luận sai |
| --- | --- | --- |
| Mật khẩu tài khoản quản trị | Mật khẩu mới đăng nhập được; mật khẩu cũ bị từ chối trên mọi điểm xác thực thuộc phạm vi | Phiên quản trị cũ còn mở nên tưởng mật khẩu cũ vẫn đăng nhập được |
| Mật khẩu tài khoản dịch vụ | Đích chấp nhận bản mới; mọi consumer lấy được bản mới và mở kết nối mới | Chỉ cập nhật vault, chưa cập nhật hệ thống đích hoặc cấu hình consumer |
| Khóa SSH | Khóa mới được cấp đúng danh tính; khóa cũ bị loại khỏi mọi nguồn cấp quyền liên quan | Chỉ xóa một bản trong một file, còn bản khác hoặc cơ chế cấp quyền khác |
| API key | Key mới được chấp nhận đúng quyền; key cũ bị vô hiệu hóa theo chính sách overlap | Consumer vẫn dùng key cũ trong thời gian hai key cùng hợp lệ |
| Chứng thư | Chứng thư mới được cấp, triển khai và chấp nhận với trust chain phù hợp | Renewal thành công nhưng endpoint vẫn phục vụ chứng thư cũ |
| Credential ngắn hạn | Credential mới được cấp đúng lease/TTL; bản cũ hết hiệu lực hoặc bị thu hồi đúng cam kết | Cấp credential mới bị nhầm thành việc đã thu hồi bản cũ |

Với chứng thư, **renewal** và **key rotation** không mặc nhiên là cùng một việc: cấp chứng thư mới có thể sử dụng lại khóa tùy chính sách. Nếu bài kiểm thử yêu cầu thay cả khóa, phải có bằng chứng tương ứng.

Với token hoặc credential có thời hạn, thời điểm thu hồi hiệu lực phụ thuộc cơ chế xác thực. Một credential có thể chỉ mất hiệu lực khi hết hạn nếu hệ thống không có cơ chế thu hồi tức thời. Kết quả kiểm thử phải đối chiếu với cam kết thực tế, không giả định rằng thao tác “rotate” luôn làm mọi token cũ mất hiệu lực ngay lập tức.

### 2.1. Ba kiểu chuyển đổi thường gặp

**Thay thế một credential duy nhất:** hệ thống đích chỉ chấp nhận một mật khẩu tại một thời điểm. Sau khi đổi tại đích, consumer chưa cập nhật có thể bị lỗi xác thực. Bài kiểm thử cần đo khoảng gián đoạn và kiểm tra cơ chế cập nhật consumer.

**Cho phép overlap:** hệ thống có thể chấp nhận bản cũ và bản mới trong một cửa sổ giới hạn. Bài kiểm thử phải kiểm tra cả giai đoạn đồng tồn tại và thời điểm bản cũ thực sự bị vô hiệu hóa.

**Cấp credential ngắn hạn:** consumer nhận một credential mới thay vì dùng lâu dài một bản cố định. Cần kiểm thử vòng đời cấp phát, hết hạn, thu hồi nếu có và khả năng consumer làm mới thông tin xác thực.

Cửa sổ overlap, nếu được phép, phải có giới hạn và bằng chứng kết thúc. “Ứng dụng đã chạy bằng bản mới” chưa đủ nếu bản cũ vẫn còn quyền truy cập vô thời hạn.

## 3. Lập hợp đồng kiểm thử trước khi thực hiện

Mỗi bài kiểm thử cần có đối tượng, chính sách và tiêu chí chấp nhận cụ thể. Nếu thiếu những điều này, cùng một hiện tượng có thể bị đánh giá khác nhau giữa các lần chạy.

Một hợp đồng tối thiểu nên trả lời:

1. Danh tính và hệ thống đích nào được rotate?
2. Ai hoặc tiến trình nào khởi tạo rotation?
3. Những consumer nào thuộc phạm vi phải chuyển sang bản mới?
4. Có overlap không, và hạn cuối kết thúc overlap là khi nào?
5. Việc vô hiệu hóa áp dụng cho đăng nhập mới, phiên đang tồn tại hay cả hai?
6. Có được phép rollback credential không? Ai quyết định?
7. Khoảng gián đoạn và số lỗi xác thực được chấp nhận là bao nhiêu?
8. Những bằng chứng nào bắt buộc phải có để đóng bài kiểm thử?

Ví dụ sau là **đặc tả kiểm thử minh họa**, không phải schema cấu hình của một sản phẩm PAM:

```yaml
testId: ROT-LAB-003
environment: isolated-lab
accountRef: svc-report-lab
targetRefs:
  - report-db-lab
consumerRefs:
  - report-api-lab
  - report-worker-lab
rotationMode: single-active-password
policy:
  maxConsumerConvergenceSeconds: 60
  maxServiceInterruptionSeconds: 10
  maxUnexpectedAuthenticationFailures: 3
  oldCredentialNewLogin: denied-after-target-change
  existingSessions: expire-under-session-policy
  credentialRollback: prohibited
evidence:
  - rotation-operation-events
  - new-credential-fresh-authentication
  - each-consumer-fresh-connection
  - old-credential-denial
  - privilege-scope-check
  - sanitized-service-metrics
```

Các con số trong ví dụ là giả định cho môi trường lab. Chúng không phải ngưỡng chuẩn cho mọi hệ thống. Một dịch vụ phục vụ giao dịch liên tục và một tác vụ chạy theo ngày có yêu cầu chuyển đổi khác nhau.

Nếu danh sách consumer chưa đầy đủ, bài kiểm thử chỉ có thể kết luận trong phạm vi đã xác định. Không dùng kết quả của một consumer để đại diện cho toàn bộ tài khoản dịch vụ.

## 4. Chuẩn bị môi trường và dữ liệu kiểm thử

### 4.1. Dùng danh tính và đích thử nghiệm tách biệt

Rotation là một thay đổi có thể làm mất truy cập. Môi trường lab nên có:

- Tài khoản thử nghiệm có quyền tương đương phạm vi cần kiểm tra nhưng chỉ trên tài nguyên lab.
- Hệ thống đích và consumer thử nghiệm có thể khôi phục.
- Credential ban đầu được quản lý qua đúng luồng PAM, không đặt trong tài liệu hoặc mã nguồn.
- Kênh khôi phục độc lập đã được kiểm tra, có người chịu trách nhiệm.
- Điểm thu thập log, metric và sự kiện kiểm thử có đồng bộ thời gian.
- Chính sách lockout đã được biết để tránh biến một phép thử âm thành khóa tài khoản ngoài ý muốn.

Không dùng tài khoản break-glass làm đối tượng rotation thử nghiệm thông thường. Nếu cần kiểm thử cơ chế break-glass, đó phải là kịch bản riêng có phạm vi và quy trình khôi phục rõ ràng.

### 4.2. Ghi nhận baseline

Trước rotation, ghi lại trạng thái nền:

| Thành phần | Baseline cần có | Không nên lưu |
| --- | --- | --- |
| Danh tính | Account reference, trạng thái enabled/disabled, phạm vi quyền | Mật khẩu hoặc private key |
| Đích xác thực | Endpoint, realm/domain, node/replica liên quan | Chuỗi kết nối có secret |
| PAM/vault | Version reference hiện tại, chính sách rotation, operation reference | Nội dung secret |
| Consumer | Instance, cách lấy secret, cache TTL, chu kỳ reconnect | Biến môi trường chứa credential |
| Phiên | Session reference và cơ chế hết hạn/thu hồi | Cookie hoặc bearer token của phiên |
| Dịch vụ | Tỷ lệ lỗi, độ trễ, số kết nối mới trong thời gian baseline | Request/response chưa được lọc dữ liệu nhạy cảm |

Dùng **version reference hoặc định danh không bí mật** để phân biệt credential cũ và mới. Không ghi hash mật khẩu do người kiểm thử tự tạo vào log để “ẩn” mật khẩu; với secret có thể đoán, hash vẫn có thể tạo thêm rủi ro. Với chứng thư hoặc public key, fingerprint công khai có thể hữu ích nhưng vẫn phải tuân thủ chính sách log của tổ chức.

### 4.3. Chuẩn bị cách kiểm tra credential cũ

Để chứng minh bản cũ bị từ chối, test harness có thể cần sử dụng lại nó một lần. Harness phải giữ secret bằng cơ chế được phép, hạn chế thời gian tồn tại và không đưa secret vào:

- Tham số dòng lệnh có thể bị thu thập.
- Log debug, stack trace hoặc bản ghi phiên.
- File fixture, báo cáo CI hay ảnh chụp màn hình.
- Tên test case, URL, header được ghi lại nguyên văn.

Nếu chính sách không cho phép giữ lại bản cũ, cần thống nhất một cách kiểm chứng thay thế có đủ bằng chứng hoặc ghi rõ giới hạn của bài kiểm thử. Không tự ý tạo một kho lưu secret thứ hai để phục vụ test.

## 5. Mô hình trạng thái và các bất biến

Rotation thường liên quan nhiều hệ thống, nên không thể mặc định mọi bước cùng commit trong một transaction.

Một vòng đời khái niệm có thể là:

```text
BASELINED
   |
   v
CANDIDATE_PREPARED
   |
   v
TARGET_CHANGE_REQUESTED
   |
   +-- kết quả không xác định --> RECONCILIATION_REQUIRED
   |
   v
NEW_CREDENTIAL_CONFIRMED
   |
   v
CONSUMERS_CONVERGED
   |
   v
OLD_CREDENTIAL_CLOSED
   |
   v
EVIDENCE_COMPLETE
```

Đây là mô hình kiểm thử, không bắt buộc một sản phẩm phải dùng các tên trạng thái này. Với hệ thống chỉ có một mật khẩu hiệu lực, bản cũ có thể mất hiệu lực ngay khi đích nhận bản mới; bước `OLD_CREDENTIAL_CLOSED` lúc đó là bước xác minh, không phải một thao tác thu hồi riêng.

### 5.1. Các bất biến cần quan sát

**Không mất dấu credential có hiệu lực.** Khi đích đã đổi nhưng PAM chưa ghi nhận xong, quy trình phải có đủ trạng thái bền vững và quyền hạn để đối soát. Không được dựa hoàn toàn vào trí nhớ của một worker hoặc một phản hồi mạng.

**Không cấp secret chưa được xác nhận làm bản hiện hành.** Nếu thiết kế sử dụng vùng staging, consumer không được nhận candidate như bản đã sẵn sàng trước khi hoàn tất điều kiện kích hoạt. Nếu sản phẩm có trình tự khác, bài kiểm thử phải chứng minh cơ chế tương đương bảo vệ consumer và khả năng phục hồi.

**Không tăng quyền.** Rotation thay thông tin xác thực, không tự chuyển một tài khoản đọc dữ liệu thành quản trị viên.

**Không có hai writer xung đột.** Một lịch rotation định kỳ và một thao tác khẩn cấp không được làm consumer nhận những phiên bản đối nghịch nhau.

**Không kết luận hoàn tất khi chưa đủ bằng chứng.** Kết quả xác thực không xác định, consumer chưa chuyển đổi hoặc overlap chưa đóng đều phải được thể hiện trong trạng thái.

### 5.2. Tại sao “timeout” không đồng nghĩa “chưa đổi”?

PAM gửi yêu cầu đổi mật khẩu. Đích cập nhật thành công nhưng phản hồi bị mất trên đường về. PAM nhận timeout.

Trong trường hợp này, chạy lại một thao tác không có kiểm soát có thể tạo credential thứ ba hoặc ghi đè trạng thái mới. Bài kiểm thử phải xác minh hệ thống phân biệt được:

- Thất bại chắc chắn trước khi thay đổi.
- Thành công đã được đích xác nhận.
- Kết quả chưa xác định, cần reconciliation.

Timeout không được tự động diễn giải thành rollback an toàn.

## 6. Kịch bản chuẩn: chứng minh rotation thành công

### Bước 1 — Xác minh baseline bằng kết nối mới

Dùng credential hiện hành mở một kết nối mới tới đúng endpoint lab. Ghi nhận danh tính xác thực và thực hiện một thao tác tối thiểu được phép, chẳng hạn đọc một bản ghi thử nghiệm.

Đồng thời kiểm tra một thao tác ngoài quyền bị từ chối nếu thao tác đó an toàn và đã nằm trong thiết kế test. Đây là baseline để đối chiếu quyền sau rotation.

### Bước 2 — Khởi tạo một operation duy nhất

Khởi tạo rotation với một operation reference để nối các sự kiện của cùng một lần chạy. Ghi nhận:

- Tác nhân khởi tạo và lý do.
- Tài khoản, hệ thống đích, version reference trước thay đổi.
- Thời điểm bắt đầu và chính sách áp dụng.
- Cơ chế tránh chạy chồng cho cùng một đối tượng.

Không đưa giá trị credential vào operation reference hoặc tên sự kiện.

### Bước 3 — Xác minh credential mới tại đích

Sau khi hệ thống báo bản mới đã sẵn sàng, lấy credential qua đường được phép và thực hiện **xác thực mới**. Không tái sử dụng session, connection pool hay token đăng nhập được tạo trước rotation.

Kiểm tra:

- Đúng danh tính đích, không vô tình dùng một tài khoản fallback.
- Đúng endpoint và miền xác thực.
- Thao tác trong quyền thành công.
- Thao tác ngoài quyền vẫn bị từ chối.
- Bản mới thực sự khác bản cũ theo cơ chế kiểm chứng được phép.

Một thay đổi version reference trong vault chưa chứng minh secret ở đích đã thay đổi. Test harness có thể kiểm tra sự khác biệt trong bộ nhớ được bảo vệ, nhưng chỉ trả về kết quả boolean; không xuất secret hoặc dấu vết suy ra secret.

### Bước 4 — Xác minh từng consumer chuyển đổi

Với mỗi consumer, yêu cầu nó đi qua đúng đường lấy secret của ứng dụng rồi mở kết nối mới. Nếu chỉ gọi trực tiếp vào đích bằng test harness, mới kiểm chứng được credential mới hoạt động, chưa chứng minh ứng dụng lấy được nó.

Đối với ứng dụng có nhiều instance, cần kiểm tra các nhóm instance và cơ chế cache nằm trong phạm vi. Một instance vừa restart thành công không đại diện cho những instance còn giữ cache cũ.

### Bước 5 — Kiểm tra bản cũ theo thời hạn

Thực hiện số lần thử âm đã giới hạn trên một kết nối mới. Sau thời điểm bản cũ phải hết hiệu lực:

- Đích phải từ chối credential cũ.
- Không có đường fallback âm thầm chuyển sang credential khác.
- Phép thử phải phân biệt lỗi xác thực với mất mạng hoặc thiếu quyền thực thi thao tác.

Một request timeout không phải bằng chứng rằng credential cũ đã bị vô hiệu hóa.

### Bước 6 — Kiểm tra phiên và dịch vụ

Nếu chính sách cho phép phiên cũ tiếp tục tới khi hết hạn, kiểm tra đúng giới hạn đó. Nếu chính sách yêu cầu chấm dứt phiên cũ, kiểm tra cơ chế thu hồi phiên riêng.

Đo khoảng gián đoạn, lỗi xác thực và khả năng tạo kết nối mới. Không dùng duy nhất health check chỉ đọc cache hoặc trả về HTTP 200 mà không truy cập đích.

### Bước 7 — Chốt bằng chứng

Chỉ kết luận PASS khi các điều kiện bắt buộc đều có kết quả xác định. Ghi nhận những phần không áp dụng cùng lý do; không biến phần chưa kiểm tra thành PASS.

## 7. Ma trận kiểm thử rotation

Ma trận dưới đây có thể dùng làm bộ khung. Mỗi hàng cần được cụ thể hóa bằng đối tượng, dữ liệu, bước thực hiện và kết quả mong đợi của môi trường.

| Mã | Tình huống | Bằng chứng chính | Kết quả mong đợi |
| --- | --- | --- | --- |
| ROT-01 | Rotation bình thường | Fresh authentication, version reference, log operation | Bản mới hoạt động và đúng quyền |
| ROT-02 | Dùng lại credential cũ sau hạn | Kết quả xác thực mới từ đích | Bị từ chối vì credential không còn hợp lệ |
| ROT-03 | Consumer giữ cache cũ | Version được consumer sử dụng, lần reconnect | Consumer hội tụ trong giới hạn hoặc báo lỗi rõ |
| ROT-04 | Credential mới vi phạm chính sách đích | Lỗi validation đã lọc secret | Không đánh dấu hoàn tất; trạng thái hiện hành còn xác định |
| ROT-05 | Đích không truy cập được trước thay đổi | Sự kiện lỗi, kiểm chứng không có thay đổi | Retry có giới hạn, giữ trạng thái phù hợp |
| ROT-06 | Mất phản hồi sau khi đích đã đổi | Kết quả đối soát sau timeout | Không suy đoán thất bại; xác định lại trạng thái |
| ROT-07 | Lưu trạng thái PAM lỗi sau cập nhật đích | Recovery state và lần khôi phục | Không cấp bản cũ như thể còn đúng; có đường đối soát |
| ROT-08 | Hai yêu cầu rotation đồng thời | Operation ordering, lock/fencing evidence | Không để writer cũ ghi đè kết quả mới |
| ROT-09 | Khởi động lại bộ điều phối giữa chừng | Trạng thái trước/sau restart | Tiếp tục hoặc khôi phục có kiểm soát |
| ROT-10 | Consumer offline rồi hoạt động lại | Lần lấy secret và kết nối đầu tiên | Dùng bản hiện hành trước khi xử lý công việc |
| ROT-11 | Quyền tài khoản sau rotation | Thao tác được phép/bị cấm | Quyền giữ đúng baseline |
| ROT-12 | Kiểm tra mọi endpoint/replica liên quan | Auth probe theo topology | Không còn điểm trong phạm vi chấp nhận bản cũ sau hạn |
| ROT-13 | Mất khả năng gửi audit event | Durable queue hoặc trạng thái chặn theo thiết kế | Không bỏ qua yêu cầu bằng chứng bắt buộc |
| ROT-14 | Rotation khẩn cấp do nghi lộ secret | Revoke evidence và kiểm tra phiên | Không phục hồi lại credential bị nghi lộ |
| ROT-15 | Consumer dùng secret cố định trong cấu hình | Kết nối mới của consumer | Phát hiện cấu hình lỗi, không che bằng fallback |
| ROT-16 | Thử lại cùng operation | Số lần thay đổi thực tế tại đích | Không tạo tác dụng phụ ngoài cam kết idempotency |

Không cần chạy mọi hàng với mọi loại credential. Ví dụ, kiểm thử overlap hai API key khác với kiểm thử một mật khẩu hiệu lực duy nhất. Phải ghi rõ mục không áp dụng thay vì bỏ trống không giải thích.

## 8. Kiểm thử lỗi và khả năng phục hồi

### 8.1. Lỗi trước khi thay đổi tại đích

Ví dụ: endpoint quản trị đích không truy cập được hoặc yêu cầu bị từ chối trước khi cập nhật credential.

Điều cần kiểm tra:

- Bản hiện hành vẫn được nhận diện chính xác.
- Candidate chưa được phát hành như credential sẵn sàng.
- Retry có giới hạn, có backoff và không tạo quá nhiều lần đăng nhập lỗi.
- Cảnh báo chỉ tới đúng nhóm chịu trách nhiệm.
- Không có thông báo thành công chỉ vì secret đã được sinh trong vault.

Mô phỏng lỗi ở một điểm đã xác định trong lab, không dùng việc ngắt mạng ngẫu nhiên để rồi không biết thay đổi đã tới đích hay chưa.

### 8.2. Lỗi sau khi thay đổi tại đích

Đây là tình huống quan trọng hơn: đích đã nhận bản mới nhưng PAM chưa hoàn tất cập nhật trạng thái hoặc phát hành cho consumer.

Bài kiểm thử cần chứng minh hệ thống có thể:

1. Nhận biết operation đang dang dở.
2. Ngăn worker khác thực hiện thay đổi mâu thuẫn.
3. Xác định credential đang được đích chấp nhận bằng cơ chế được thiết kế.
4. Hoàn thiện trạng thái PAM hoặc chuyển sang quy trình khôi phục.
5. Giữ đủ bằng chứng để giải thích thời điểm và quyết định.

Không thử liên tục cả mật khẩu cũ lẫn mới trên môi trường có lockout mà không có giới hạn. Cơ chế đối soát phải tính đến giới hạn xác thực và phạm vi quyền của tài khoản quản trị rotation.

### 8.3. Consumer chuyển đổi một phần

Giả sử `report-api-lab` đã sử dụng bản mới, nhưng `report-worker-lab` vẫn giữ cache cũ.

Kiểm tra cả hai câu hỏi:

- Dịch vụ có tiếp tục đạt ngưỡng vận hành đã cam kết không?
- Hệ thống có nhìn thấy consumer chưa hội tụ không?

Nếu hết thời hạn mà consumer vẫn dùng bản cũ, bài kiểm thử không được PASS chỉ vì request trên API vẫn hoạt động. Cần kiểm tra cảnh báo, cơ chế làm mới cache, reconnect và trạng thái operation.

Đặc biệt với cron job, một vòng kiểm thử ngắn hơn chu kỳ chạy có thể bỏ sót lỗi. Có thể kích hoạt tác vụ thử nghiệm được phép hoặc thiết kế thêm điểm kiểm chứng để xác nhận lần chạy kế tiếp sẽ dùng bản hiện hành.

### 8.4. Phục hồi tiến lên và rollback

**Phục hồi tiến lên** là đưa hệ thống tới một trạng thái mới đã xác nhận: hoàn tất phát hành credential mới hoặc thay tiếp bằng một credential khác theo quy trình.

**Rollback credential** là đưa secret cũ trở lại hiệu lực. Cách này chỉ được sử dụng nếu chính sách cho phép và đã đánh giá các consumer, quyền, lịch sử thay đổi và lý do rotation.

Khi rotation được khởi tạo vì nghi secret bị lộ, phục hồi bản cũ có thể tái mở đường truy cập đã cần đóng. Kịch bản này phải kiểm tra rằng hệ thống không tự động rollback về secret bị nghi lộ để cải thiện availability.

Nếu chính sách cấm rollback như ví dụ ở phần 3, bài kiểm thử cần xác nhận cơ chế phục hồi tiến lên và đường quản trị khẩn cấp hoạt động.

## 9. Kiểm thử đồng thời, retry và scheduler

### 9.1. Hai operation cùng nhắm một tài khoản

Kích hoạt hai yêu cầu gần nhau trong lab: một từ scheduler và một từ người vận hành.

Các thiết kế hợp lệ có thể từ chối, xếp hàng hoặc hợp nhất yêu cầu thứ hai. Tiêu chí chung là:

- Có một trình tự thay đổi rõ ràng.
- Consumer không bị phát hành ngược từ bản mới hơn sang bản cũ hơn.
- Worker mất quyền sở hữu không tiếp tục commit kết quả.
- Không có operation báo hoàn tất cho credential đã bị operation khác thay thế mà không phản ánh trạng thái đó.

Chỉ thấy “có lock” chưa đủ. Nếu worker A mất lease và worker B nhận quyền, worker A bị chậm vẫn có thể quay lại ghi kết quả. Cần kiểm tra cơ chế như fencing/version check hoặc cơ chế tương đương thực sự chặn writer đã hết quyền ở những điểm ghi quan trọng.

Nếu hệ thống đích không hỗ trợ fencing, thiết kế phải có biện pháp điều phối và đối soát phù hợp; bài kiểm thử không được giả định target tự ngăn stale writer.

### 9.2. Retry cùng một operation

Gửi lại cùng operation reference sau một lỗi có thể khôi phục. Quan sát tác dụng thực tế tại đích và các sự kiện.

Nếu API cam kết idempotency, gọi lại không được tạo một vòng rotation độc lập ngoài ý muốn. Nếu API không có cam kết đó, bộ điều phối phải có cơ chế khác để nhận biết yêu cầu lặp.

Không mặc định một trường `operationId` trong JSON đã tạo ra idempotency. Phải kiểm chứng hành vi.

### 9.3. Thời gian và lịch chạy

Với rotation định kỳ, kiểm tra:

- Job được lên lịch theo thời gian nào và có xử lý sai lệch đồng hồ không.
- Sau downtime, job bỏ lỡ được xử lý theo chính sách nào.
- Retry có chồng lên lần chạy kế tiếp không.
- Nhiều tài khoản có đồng loạt rotate và gây quá tải hay không.
- Credential có bị hết hạn trước khi consumer hoàn tất chuyển đổi không.

Dùng khoảng thời gian đơn điệu để đo duration trong test harness nếu có thể. Timestamp từ nhiều hệ thống cần được đối chiếu với sai lệch đồng hồ; không dùng hai đồng hồ chưa đồng bộ để kết luận một SLA đã bị vi phạm vài mili giây.

## 10. Thiết kế test harness và oracle

**Oracle** là cơ sở để quyết định kết quả đúng hay sai. Trong test rotation, màn hình “Success” của PAM là một nguồn sự kiện, không phải oracle duy nhất.

Một harness nên kết hợp ít nhất ba góc nhìn:

| Góc nhìn | Câu hỏi được trả lời |
| --- | --- |
| Control plane của PAM | Operation đã đi qua những trạng thái nào, version nào được phát hành? |
| Xác thực thực tế tại đích | Credential mới/cũ có mở được kết nối mới không? |
| Consumer và dịch vụ | Ứng dụng thực sự lấy secret và xử lý công việc ra sao? |

Pseudocode sau mô tả cách tổ chức kiểm thử. Các hàm là adapter khái niệm, cần triển khai theo môi trường; đây không phải API có sẵn:

```text
baseline = captureSanitizedBaseline(accountRef, targets, consumers)
oldHandle = obtainRestrictedEphemeralHandle(currentVersionRef)

operation = startRotation(accountRef, uniqueOperationRef)

outcome = waitForKnownOutcome(operation, boundedDeadline)
if outcome == UNKNOWN:
    recordInconclusive("reconciliation required")
    invokeApprovedReconciliation(operation)
    stopWithoutPassing()

if outcome == FAILED:
    verifyFailureStateAgainstContract(operation, baseline)
    stopWithFailureEvidence()

newHandle = obtainRestrictedEphemeralHandle(publishedVersionRef)

assert protectedComparisonShowsChange(oldHandle, newHandle)

for each target in inScopeAuthenticationTargets:
    assert freshAuthentication(target, newHandle) == AUTHENTICATED
    assert authenticatedPrincipal(target) == expectedPrincipal
    assert allowedReadProbe(target) == ALLOWED
    assert safeForbiddenProbe(target) == DENIED

for each consumer in inScopeConsumers:
    result = consumerReconnectThroughNormalSecretPath(consumer)
    assert result.usedCurrentVersion
    assert result.expectedWorkSucceeded

waitUntilPolicyRequiresOldCredentialClosed(boundedDeadline)

for each target in inScopeAuthenticationTargets:
    assert freshAuthentication(target, oldHandle) == CREDENTIAL_REJECTED

assert sessionBehaviorMatchesPolicy()
assert operationalMetricsWithinContract()
assert mandatoryEvidenceIsComplete()

releaseHandlesAndRemovePermittedEphemeralArtifacts()
markPass()
```

Harness thực tế cần khối cleanup luôn chạy khi assertion thất bại hoặc timeout. Dừng bài kiểm thử không có nghĩa được bỏ quên secret handle, phiên thử nghiệm hay fault injection.

### 10.1. Chuẩn hóa kết quả xác thực

Không gộp mọi lỗi thành “bị từ chối”. Một adapter có thể trả về:

- `AUTHENTICATED`: xác thực thành công và có danh tính được kiểm chứng.
- `CREDENTIAL_REJECTED`: đích trả về tín hiệu xác thực không hợp lệ đủ rõ.
- `AUTHENTICATED_BUT_NOT_AUTHORIZED`: đã đăng nhập, nhưng thao tác không có quyền.
- `ACCOUNT_LOCKED_OR_DISABLED`: tài khoản bị khóa hoặc vô hiệu hóa.
- `UNREACHABLE`: không tới được đích.
- `UNKNOWN`: thiếu thông tin để phân loại.

Nếu bản cũ bị từ chối vì cả tài khoản đã bị disabled thì chưa chứng minh rotation bình thường đạt yêu cầu, bởi bản mới cũng có thể không dùng được. Cần kiểm chứng đồng thời khả năng sử dụng bản mới và nguyên nhân từ chối bản cũ.

### 10.2. Tránh phép thử tự chứng minh chính nó

Nếu một mock luôn trả về credential mới khi được yêu cầu, kiểm thử chỉ chứng minh harness đọc đúng mock. Nó không chứng minh đích đã nhận secret.

Có thể dùng test double để kiểm tra logic bộ điều phối, sau đó dùng integration test trong lab để xác minh hợp đồng với đích, cache, session và consumer thật. Không lấy kết quả unit test thay thế kết quả tích hợp của toàn đường đi.

## 11. Bằng chứng và tiêu chí PASS/FAIL

Một sự kiện kiểm thử đã lọc secret có thể có dạng:

```json
{
  "testId": "ROT-LAB-003",
  "operationRef": "rotation-lab-run-024",
  "accountRef": "svc-report-lab",
  "targetRef": "report-db-lab",
  "phase": "OLD_CREDENTIAL_NEW_AUTH",
  "credentialVersionRef": "version-before-run",
  "result": "CREDENTIAL_REJECTED",
  "reason": "TARGET_CONFIRMED_INVALID_CREDENTIAL",
  "evidenceRef": "restricted-evidence/run-024/probe-07"
}
```

Các giá trị trên là dữ liệu minh họa. Báo cáo không chứa mật khẩu, private key, token, raw authorization header hoặc bản dump request chưa được lọc.

### 11.1. Tiêu chí kết luận

**PASS** khi tất cả điều kiện bắt buộc trong hợp đồng đã được chứng minh: bản mới dùng được, consumer hội tụ, bản cũ mất hiệu lực theo thời hạn, phiên theo đúng chính sách, quyền không tăng và bằng chứng đủ.

**FAIL** khi có điều kiện bị vi phạm: bản cũ còn đăng nhập được sau hạn, consumer không reconnect được, operation lặp tạo thay đổi ngoài cam kết hoặc secret bị lộ trong output của quá trình test.

**INCONCLUSIVE/BLOCKED** khi chưa đủ cơ sở kết luận: mất kết nối tới đích, telemetry thiếu, topology chưa xác định hoặc kết quả thay đổi chưa được đối soát. Trạng thái này không được tính là PASS.

Trong kịch bản fault injection, việc operation rotation báo thất bại có thể là hành vi đúng. Test case chỉ PASS nếu hệ thống xử lý lỗi đúng hợp đồng, bảo toàn khả năng phục hồi và cung cấp đủ bằng chứng.

### 11.2. Các mốc thời gian nên đo

- Từ lúc khởi tạo tới lúc đích xác nhận credential mới.
- Từ lúc bản mới được phát hành tới lúc từng consumer hội tụ.
- Khoảng thời gian dịch vụ không tạo được công việc hoặc kết nối mới.
- Từ hạn đóng credential cũ tới thời điểm xác minh nó đã bị từ chối.
- Thời gian phát hiện và khôi phục một operation dang dở.

Nếu lấy mẫu định kỳ, thời điểm quan sát credential cũ bị từ chối chỉ cho biết giới hạn theo độ phân giải lấy mẫu. Không báo độ chính xác cao hơn bằng chứng thực tế.

## 12. Tình huống thực hành: tài khoản báo cáo trên hai consumer

### 12.1. Bối cảnh

Tài khoản `svc-report-lab` chỉ được đọc bộ dữ liệu báo cáo trong một cơ sở dữ liệu lab. Hai consumer sử dụng tài khoản này:

- `report-api-lab` giữ một connection pool.
- `report-worker-lab` lấy secret khi khởi động và chạy tác vụ theo lịch.

Đích chỉ chấp nhận một mật khẩu tại một thời điểm. Chính sách không cho khôi phục mật khẩu cũ. Phiên đã xác thực được xử lý theo session policy riêng.

### 12.2. Lần chạy thứ nhất

PAM đổi mật khẩu tại đích và cập nhật bản phát hành thành công. API vẫn trả về dữ liệu. Worker chưa tới giờ chạy nên không xuất hiện lỗi.

Nếu dừng ở đây, kết luận “rotation không làm gián đoạn dịch vụ” còn thiếu căn cứ.

Tiếp tục kiểm thử:

1. Buộc API tạo một kết nối lab mới qua luồng lấy secret của ứng dụng.
2. Kích hoạt một tác vụ thử nghiệm được phép trên worker.
3. Ghi nhận version reference mà mỗi consumer nhận qua telemetry đã lọc.
4. Kiểm tra đăng nhập mới bằng bản cũ.
5. Kiểm tra thao tác ghi ngoài quyền vẫn bị từ chối bằng bản mới.

Kết quả: API lấy bản mới và kết nối thành công. Worker tiếp tục dùng secret cache từ khi khởi động, nên kết nối mới thất bại. Bản cũ bị đích từ chối.

**Kết luận:** cập nhật tại đích đã có bằng chứng, nhưng kiểm thử rotation đầu cuối FAIL vì worker chưa hội tụ trong giới hạn. Một sự kiện PAM thành công không thay thế điều kiện consumer.

### 12.3. Lần chạy sau khi sửa consumer

Consumer được điều chỉnh để làm mới secret theo cơ chế thiết kế của ứng dụng. Trong lần kiểm thử tiếp theo, cả API và worker mở được kết nối mới bằng bản hiện hành; bản cũ bị từ chối; quyền đọc giữ nguyên.

Sau đó mới kiểm tra thêm:

- Worker offline trong lúc rotation rồi hoạt động trở lại.
- Đích đã đổi nhưng phản hồi tới PAM bị mất.
- Hai lệnh rotation gần như đồng thời.
- Bộ điều phối restart trước khi đóng operation.

Mỗi lần chạy phải có operation reference và baseline riêng. Không dùng credential hoặc kết quả lẫn giữa các lần để giải thích một kết quả PASS.

## 13. Những lỗi thường gặp khi test rotation

| Cách kiểm thử sai | Vì sao chưa đủ | Cách kiểm chứng phù hợp |
| --- | --- | --- |
| Chỉ kiểm tra secret version trong vault | Vault và đích có thể lệch nhau | Xác thực mới tại đích |
| Dùng lại connection pool cũ | Không đi qua bước xác thực bằng bản mới | Mở kết nối mới có kiểm soát |
| Chỉ thử credential mới | Không chứng minh bản cũ đã mất hiệu lực | Thử âm bản cũ sau thời hạn |
| Coi timeout là từ chối credential | Có thể lỗi mạng hoặc đích quá tải | Phân loại kết quả xác thực |
| Chỉ kiểm tra một endpoint | Replica hoặc đường xác thực khác có thể chưa cập nhật | Kiểm tra topology trong phạm vi |
| Chỉ restart một instance | Các instance còn lại có thể giữ cache cũ | Kiểm tra cơ chế hội tụ của các consumer |
| Không kiểm tra quyền | Credential mới có thể gắn sai danh tính hoặc quyền | Đối chiếu danh tính và thao tác được phép/bị cấm |
| Retry không có giới hạn | Có thể khóa tài khoản hoặc tạo thêm thay đổi | Retry theo operation và giới hạn rõ |
| Tự rollback secret cũ khi có lỗi | Có thể phục hồi credential đã bị nghi lộ | Áp dụng chính sách khôi phục đã định |
| Bật debug toàn bộ để lấy bằng chứng | Có thể phát tán credential qua log | Thu thập sự kiện đã lọc secret |

Một bài kiểm thử tốt phải làm lộ sự khác biệt giữa “đã đổi secret ở một nơi” và “đã hoàn tất vòng đời credential theo chính sách”.

## 14. Bài tập tự kiểm tra

### Bài tập 1 — PAM báo thành công, ứng dụng vẫn chạy

Ứng dụng có connection pool, chưa tạo kết nối mới từ trước rotation. Hãy xác định bằng chứng còn thiếu.

**Gợi ý:** cần kiểm tra xác thực mới bằng bản mới, consumer đi qua đúng đường lấy secret, bản cũ bị từ chối sau hạn và hành vi phiên theo chính sách. Tình trạng pool cũ chỉ chứng minh các phiên trước đó vẫn hoạt động.

### Bài tập 2 — Mất phản hồi sau yêu cầu thay đổi

PAM nhận timeout sau khi gửi yêu cầu đổi mật khẩu. Hãy quyết định có được chạy lại ngay một yêu cầu độc lập không.

**Gợi ý:** chưa có cơ sở kết luận đích chưa thay đổi. Cần đưa operation vào trạng thái cần đối soát, kiểm tra thiết kế idempotency và cơ chế khôi phục trước khi tạo thay đổi tiếp theo.

### Bài tập 3 — Overlap không kết thúc

Key mới hoạt động và mọi consumer đã chuyển đổi, nhưng key cũ vẫn gọi API được sau hạn overlap.

**Kết luận cần giải thích:** test FAIL vì điều kiện đóng credential cũ bị vi phạm, dù availability vẫn tốt.

### Bài tập 4 — Credential mới đăng nhập được nhưng có thêm quyền

Tài khoản trước rotation chỉ đọc được dữ liệu lab; sau rotation lại ghi được vào cùng tập dữ liệu.

**Kết luận cần giải thích:** khả năng xác thực mới không đủ. Bài kiểm thử phải FAIL do quyền tăng ngoài hợp đồng và cần điều tra việc cấp sai danh tính hoặc thay đổi cấu hình quyền.

### Bài tập 5 — Thiết kế một ca lỗi có thể lặp lại

Chọn một điểm lỗi sau khi đích đã đổi credential nhưng trước khi PAM chốt trạng thái. Viết:

1. Baseline và điều kiện an toàn của môi trường lab.
2. Cách tạo lỗi tại đúng điểm đã chọn.
3. Những trạng thái có thể quan sát.
4. Bằng chứng chứng minh cơ chế đối soát.
5. Điều kiện PASS của test case phục hồi.
6. Cleanup và xác nhận hệ thống trở lại trạng thái đã biết.

Bài làm cần mô tả cả điều hệ thống phải thực hiện và cách người kiểm thử nhận biết điều đó. Một dòng “retry thành công” không đủ để chứng minh hệ thống không bỏ mất credential có hiệu lực, phát hành sai bản hoặc khôi phục lại secret cần thu hồi.

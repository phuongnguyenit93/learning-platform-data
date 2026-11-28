# Break-glass deployment

## 1. Break-glass deployment giải quyết vấn đề nào?

Trong vận hành CI/CD, có những thời điểm quy trình triển khai bình thường không thể đáp ứng tình huống khẩn cấp: cổng phê duyệt bị lỗi, dịch vụ nhận diện danh tính không hoạt động, nền tảng CI bị xâm nhập hoặc phiên bản đang chạy gây gián đoạn nghiêm trọng. Doanh nghiệp vẫn phải khôi phục dịch vụ, nhưng một tài khoản quản trị dùng chung có thể biến sự cố vận hành thành sự cố an ninh lớn hơn.

**Break-glass deployment** là đường triển khai khẩn cấp được thiết kế và kiểm thử trước, cho phép một chủ thể xác định thực hiện một hành động đặc biệt trong phạm vi và thời gian giới hạn. Quyền được cấp gắn với sự cố, mục tiêu khôi phục, hiện vật triển khai và bằng chứng có thể kiểm tra lại.

Trong module quản lý truy cập đặc quyền (Privileged Access Management — PAM), trọng tâm không chỉ là đưa một phiên bản lên production. Trọng tâm là quản lý toàn bộ vòng đời quyền khẩn cấp:

1. Ai được yêu cầu và ai có thể chấp thuận?
2. Quyền đó thực sự cho phép làm gì trên tài nguyên nào?
3. Hệ thống xác minh người và workload như thế nào?
4. Khi nào quyền hết hiệu lực, và ai kiểm tra việc thu hồi?
5. Làm sao chứng minh hành động thực tế khớp với quyết định đã phê duyệt?

Một cơ chế break-glass tốt vẫn cần hoạt động khi một số thành phần bình thường bị hỏng. Tuy nhiên, nó không thể mặc định rằng cứ có sự cố là được bỏ mọi kiểm soát.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt triển khai khẩn cấp với quyền quản trị thường trực.
- Thiết kế yêu cầu quyền JIT/JEA cho một lần triển khai.
- Xác định ranh giới ngoại lệ và kiểm soát phải giữ.
- Phân tích phụ thuộc khi CI, IAM, PAM hoặc vault gặp sự cố.
- Xây dựng trình tự thực thi, thu hồi và lưu bằng chứng.
- Kiểm thử đường khẩn cấp mà không đưa credential production vào pipeline thông thường.

## 2. Phân biệt các đường triển khai

| Đường triển khai | Tình huống | Quyền và quy trình |
| --- | --- | --- |
| Deployment thông thường | Phát hành theo kế hoạch | Pipeline tiêu chuẩn, kiểm thử và phê duyệt theo chính sách thông thường |
| Emergency change | Thay đổi cần làm sớm để xử lý sự cố | Quy trình thay đổi được rút ngắn nhưng có thể vẫn dùng hoàn toàn đường triển khai chuẩn |
| Break-glass deployment | Đường chuẩn không khả dụng hoặc không thể đáp ứng mục tiêu khẩn cấp đã xác định | Đường đặc biệt có quyền hạn chế, điều kiện kích hoạt rõ, bằng chứng và thu hồi riêng |
| Quản trị đặc quyền tương tác | Chẩn đoán hoặc sửa hạ tầng bằng phiên quản trị | Phạm vi khác với triển khai; có thể cần assignment và phê duyệt riêng |

Không phải mọi emergency change đều cần break-glass. Nếu pipeline bình thường vẫn an toàn và đủ nhanh, hãy dùng pipeline đó theo cơ chế xử lý khẩn cấp đã được tổ chức phê duyệt.

Tương tự, quyền triển khai lại một ứng dụng không tự bao gồm quyền sửa firewall, mở tài khoản quản trị, đọc dữ liệu khách hàng hay tắt hệ thống giám sát. Mỗi hành động vượt phạm vi triển khai cần được đánh giá riêng.

### Ví dụ về mục tiêu đủ cụ thể

Một yêu cầu có thể là:

> Trong sự cố INC-EXAMPLE-042, triển khai lại bản đã được xác minh của dịch vụ checkout vào production để khôi phục khả năng thanh toán. Chỉ cho phép một lần khởi chạy trong cửa sổ 15 phút; theo dõi sức khỏe sau triển khai và đóng quyền khi hoàn tất.

Các giá trị thời gian trong bài chỉ là ví dụ thiết kế. Tổ chức phải chọn giới hạn phù hợp với độ rủi ro, thời gian thực thi và khả năng thu hồi của mình.

Yêu cầu “cho đội trực quyền admin đến khi hệ thống ổn định” không đủ xác định: không rõ thao tác, tài nguyên, thời điểm kết thúc hay điều kiện thành công.

## 3. Điều kiện kích hoạt và ranh giới ngoại lệ

Break-glass phải có tiêu chí kích hoạt để tránh trở thành đường tắt của công việc hằng ngày.

Một bộ tiêu chí có thể yêu cầu đồng thời:

- Có sự cố đang hoạt động với mức ảnh hưởng phù hợp chính sách.
- Có mục tiêu phục hồi hoặc ngăn thiệt hại cụ thể.
- Đường triển khai chuẩn không khả dụng, không đáng tin cậy hoặc không đáp ứng được thời gian xử lý.
- Có người chịu trách nhiệm ra quyết định.
- Có đường thực thi khẩn cấp đã chuẩn bị, cùng cách ghi nhận bằng chứng.
- Có cách kết thúc quyền và kiểm tra kết quả.

Độ nghiêm trọng cao không tự chứng minh rằng quyền yêu cầu là cần thiết. Một sự cố rất nghiêm trọng vẫn có thể chỉ cần quyền triển khai một dịch vụ, không cần quyền quản trị toàn bộ hạ tầng.

### Kiểm soát nào được thay đổi?

Cần ghi rõ ngoại lệ trước khi cấp quyền. Không dùng một cờ chung như `emergency=true` để làm mất hiệu lực mọi policy.

| Kiểm soát | Cách xử lý trong đường khẩn cấp |
| --- | --- |
| Lịch phát hành | Có thể cho phép ngoài lịch nếu sự cố đủ điều kiện |
| Số cấp phê duyệt của thay đổi chuẩn | Có thể thay bằng cơ chế phê duyệt khẩn cấp đã được định nghĩa |
| Một bài kiểm thử không liên quan trực tiếp đến bản rollback đã xác minh | Chỉ được miễn theo chính sách cụ thể, có lý do và đánh giá tác động |
| Nhận diện chủ thể thực thi | Phải duy trì hoặc dùng phương thức khẩn cấp đã được chuẩn bị và xác minh |
| Phạm vi đích triển khai | Phải giới hạn; không tự mở rộng sang mọi môi trường |
| Bảo vệ credential và dữ liệu nhạy cảm | Phải duy trì |
| Xác minh tính toàn vẹn, nguồn gốc hiện vật | Cần đường xác minh đáng tin; ngoại lệ riêng, nếu chính sách cho phép, phải có kiểm soát thay thế cụ thể |
| Ghi nhận quyết định và hành động | Phải có bằng chứng tin cậy, kể cả khi nơi tập trung log đang lỗi |
| Thu hồi hoặc vô hiệu hóa quyền | Phải có cơ chế và người kiểm tra |

Không có một danh sách ngoại lệ áp dụng giống nhau cho mọi tổ chức. Điều cần thiết là biết chính xác kiểm soát nào thay đổi, ai có thẩm quyền thay đổi và điều kiện bù đắp là gì.

Nếu không còn cách xác minh chủ thể hoặc không thể biết hiện vật nào sắp chạy, đường khẩn cấp đó chưa đủ điều kiện để thực thi an toàn. Người chỉ huy sự cố cần chọn phương án phục hồi khác hoặc kích hoạt phương án dự phòng đã được phê duyệt, thay vì tự tạo một đường admin mới ngay trong sự cố.

## 4. Mô hình quyền: kết hợp JIT, JEA và một lần thực thi

**Just-in-Time (JIT)** giới hạn thời điểm có quyền. **Just Enough Administration (JEA)** giới hạn những việc chủ thể được làm. Break-glass deployment cần cả hai.

Một quyền tồn tại 10 phút nhưng có thể tạo tài khoản quản trị vĩnh viễn vẫn có thể gây hậu quả lâu dài. Ngược lại, một quyền rất hẹp nhưng được giữ mãi vẫn tạo ra bề mặt truy cập thường trực không cần thiết.

### 4.1. Ràng buộc quyền vào giao dịch triển khai

Một assignment nên gắn với ít nhất:

- Mã sự cố và mã yêu cầu khẩn cấp.
- Người yêu cầu, người quyết định, người vận hành.
- Danh tính workload hoặc executor thực thi.
- Dịch vụ, môi trường và tập tài nguyên đích.
- Hành động được phép, chẳng hạn triển khai hoặc rollback một release xác định.
- Digest của hiện vật và, khi cần, digest của manifest/cấu hình triển khai.
- Thời điểm bắt đầu, hạn khởi chạy và giới hạn thực thi.
- Số lần được sử dụng.
- Điều kiện dừng, thu hồi và kết quả cần quan sát.

Cần phân biệt **hạn được phép khởi chạy** với **thời gian tiến trình còn được chạy**. Một job bắt đầu trước hạn có thể vẫn hoạt động sau khi token ban đầu hết hạn. Phải có policy riêng cho thời lượng job, gia hạn, dừng tiến trình và hành vi của hệ thống đích.

### 4.2. Phân tách các vai trò

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Người yêu cầu | Mô tả tác động, mục tiêu và phạm vi cần quyền |
| Người có thẩm quyền khẩn cấp | Chấp thuận rủi ro và ngoại lệ đúng phạm vi được ủy quyền |
| Người vận hành | Khởi chạy thao tác đã được phép và theo dõi kết quả |
| Executor | Thực hiện deployment bằng danh tính workload giới hạn |
| Người kiểm tra sau sự cố | Đối chiếu quyết định, hành động, thu hồi và bằng chứng |

Ở tình huống thiếu nhân sự, chính sách có thể cho phép một người đảm nhiệm nhiều vai trò. Điều này phải được định nghĩa và ghi nhận, không được che giấu bằng cách dùng chung tài khoản.

Một số tổ chức cho phép kích hoạt trước khi có người thứ hai trong trường hợp tối khẩn cấp. Khi đó cần điều kiện rất cụ thể, cảnh báo độc lập ngay khi sử dụng và hậu kiểm có thời hạn. Hậu kiểm không biến một hành vi tự cấp quyền ngoài chính sách thành hợp lệ.

### 4.3. Quyền logic phải được thực thi bằng cơ chế phù hợp

Một phiếu yêu cầu ghi “chỉ deploy checkout” không đủ nếu credential phía dưới vẫn là cluster-admin hoặc administrator của toàn tài khoản.

Các ràng buộc phải được ánh xạ vào nơi có thể thực thi chúng:

- Identity và policy engine xác minh người, workload, thời gian và phê duyệt.
- Deployment controller giới hạn hành động và số lần chạy.
- Hệ thống đích giới hạn tài nguyên và thao tác API.
- Cơ chế admission hoặc kiểm tra tương đương xác minh hiện vật và thuộc tính deployment.
- Audit ghi lại chủ thể, assignment và thay đổi thực tế.

Không phải hệ thống phân quyền nào cũng biểu diễn được giới hạn theo image digest hoặc số lần triển khai. Ví dụ, quyền sửa một deployment ở tầng API chưa tự bảo đảm rằng chỉ được dùng một image cụ thể. Khi nền tảng thiếu ràng buộc cần thiết, phải bổ sung một lớp thực thi phù hợp hoặc thu hẹp giao diện thao tác; không được mô tả quyền là “hẹp” chỉ vì phiếu yêu cầu viết như vậy.

## 5. Kiến trúc đường khẩn cấp

Một thiết kế có thể tách các thành phần sau:

```text
Người vận hành đã xác minh
          |
          v
Yêu cầu khẩn cấp + quyết định + phạm vi
          |
          v
Bộ cấp quyền PAM/JIT hoặc cơ chế dự phòng đã chuẩn bị
          |
          v
Executor khẩn cấp được kiểm soát
          |
          +----> Kho hiện vật và bằng chứng nguồn gốc
          |
          +----> Hệ thống đích: triển khai trong phạm vi đã cấp
          |
          +----> Audit độc lập / hàng đợi bằng chứng dự phòng
```

Sơ đồ thể hiện trách nhiệm logic. Các thành phần có thể nằm trong những sản phẩm khác nhau hoặc được kết hợp, nhưng các ranh giới tin cậy cần được giữ rõ.

### 5.1. Không phụ thuộc hoàn toàn vào thành phần đang hỏng

Nếu pipeline thường xuyên và pipeline khẩn cấp cùng phụ thuộc một runner, một danh tính quản trị, một vault và một kênh audit, chúng có thể hỏng cùng lúc.

Tuy nhiên, “độc lập” không đồng nghĩa sao chép mọi credential production sang một máy dự phòng. Việc thiết kế nên bắt đầu từ các kịch bản hỏng:

| Thành phần gặp sự cố | Câu hỏi cần trả lời |
| --- | --- |
| CI controller | Có executor khẩn cấp được chuẩn bị sẵn, không cần controller đó khởi tạo không? |
| Identity provider | Có cách xác thực khẩn cấp đã cấp phát và kiểm thử trước không? |
| Vault/PAM | Có cơ chế dự phòng được quản lý với phạm vi, người giữ và cách kiểm kê rõ không? |
| Artifact registry | Có bản hiện vật tin cậy ở vùng dự phòng và có thể kiểm tra lại tính toàn vẹn không? |
| Hệ thống audit tập trung | Có thể ghi bằng chứng cục bộ được bảo vệ hoặc sang nơi nhận độc lập không? |
| Mạng quản trị | Có đường truy cập thay thế được phê duyệt và hạn chế đích không? |
| Đồng hồ hoặc nguồn thời gian | Có thể đánh giá độ lệch và hiệu lực credential một cách đáng tin không? |

Một đường dự phòng vẫn có thể còn phụ thuộc chung. Phải xác định phụ thuộc đó và chấp nhận có ý thức, không giả định rằng đổi tên pipeline là đã có khả năng phục hồi.

### 5.2. Nếu CI bị xâm nhập

Đường khẩn cấp không nên lấy runner bị nghi xâm nhập làm nơi giữ credential đặc quyền hoặc kiểm tra bằng chứng duy nhất.

Một phương án được chuẩn bị trước có thể sử dụng:

- Máy quản trị hoặc runner khẩn cấp với baseline được xác minh.
- Danh tính executor riêng, không dùng credential của runner thường.
- Bản hiện vật lấy từ nguồn đã xác minh độc lập.
- Kênh phê duyệt và audit không do chính runner đó kiểm soát.
- Credential cũ được xem xét thu hồi theo phạm vi sự cố.

Một pipeline khác nhưng vẫn chạy trên cùng host bị xâm nhập chưa tạo ra ranh giới tin cậy mới.

### 5.3. Credential dự phòng cần quản lý riêng

Nếu tổ chức phải giữ credential khẩn cấp dài hạn do giới hạn nền tảng, credential đó cần được bảo quản, kiểm kê và kiểm thử theo chính sách break-glass riêng. Có thể áp dụng phân tách người giữ, thiết bị xác thực chuyên dụng, giám sát mọi lần sử dụng và rotation sau truy cập.

Không để credential này thành một biến bí mật luôn sẵn trong mọi job CI. Việc che giá trị trên giao diện không ngăn được một job có quyền sử dụng nó để gửi dữ liệu ra ngoài.

## 6. Hợp đồng triển khai khẩn cấp minh họa

Ví dụ dưới đây là **mô hình dữ liệu thiết kế**, không phải cấu hình chạy được của một sản phẩm cụ thể. Những tên trường như `maxStarts` chỉ có hiệu lực nếu hệ thống triển khai thực sự kiểm tra và cập nhật chúng an toàn.

```yaml
requestId: BG-EXAMPLE-017
incidentId: INC-EXAMPLE-042
purpose: Khoi phuc checkout sau release loi
requester: operator-a
decision:
  authority: incident-commander-b
  mode: emergency-approved
  exception:
    control: normal-release-window
    reason: Su co production dang dien ra
scope:
  environment: production
  service: checkout
  targets:
    - workload-checkout-primary
  action: deploy-approved-release
artifact:
  digest: "<DIGEST_CUA_HIEN_VAT_DA_XAC_MINH>"
  deploymentSpecDigest: "<DIGEST_CUA_MANIFEST_DA_DUYET>"
  provenanceReference: evidence/release-record
execution:
  executorIdentity: emergency-checkout-deployer
  maxStarts: 1
  launchWindowMinutes: 15
  maxExecutionMinutes: 20
  allowInteractiveShell: false
  allowPrivilegeDelegation: false
stopConditions:
  - error-rate-exceeds-incident-threshold
  - target-or-artifact-mismatch
  - identity-or-evidence-integrity-lost
evidence:
  sink: independent-emergency-audit
  fallback: protected-local-journal
closure:
  revokeAssignment: true
  verifyOutstandingExecutions: true
  credentialRotation: based-on-credential-type-and-exposure
```

Các placeholder phải được điền bằng dữ liệu đã xác minh trước khi chạy. Một mã sự cố hoặc một digest do người vận hành tự nhập không phải bằng chứng rằng nó đã được chấp thuận.

### 6.1. Chấp thuận phải gắn với nội dung

Quyết định chấp thuận cần ràng buộc vào các trường quan trọng của yêu cầu: môi trường, tài nguyên đích, hành động, hiện vật, manifest và ngoại lệ.

Nếu người vận hành đổi image digest sau khi phê duyệt mà quyết định vẫn được dùng lại, cơ chế phê duyệt đã mất ý nghĩa.

Một cách triển khai là chuẩn hóa nội dung yêu cầu, tính fingerprint của phần bất biến và đưa fingerprint vào quyết định hoặc token cấp quyền. Hệ thống thực thi kiểm tra fingerprint tại thời điểm khởi chạy. Cách chuẩn hóa, khóa xác minh và chống sửa đổi phải được thiết kế cụ thể theo nền tảng.

### 6.2. Một lần sử dụng cần cơ chế nguyên tử

Kiểm tra `maxStarts: 1` bằng cách đọc một biến rồi cập nhật sau khi job chạy có thể cho phép hai request đồng thời cùng vượt qua.

Bộ điều khiển cần chuyển trạng thái assignment một cách nguyên tử, chẳng hạn từ `AUTHORIZED` sang `STARTING`, trước khi tạo execution. Một idempotency key liên kết yêu cầu với execution giúp retry không tạo thêm lần triển khai.

Nếu nhận request lặp nhưng chưa rõ lần trước đã tạo job hay chưa, phải tra cứu trạng thái thực tế. Không tự tạo job mới chỉ vì client timeout.

## 7. Quy trình thực thi từ yêu cầu đến đóng quyền

### Bước 1: Xác nhận sự cố và lựa chọn hành động

Người chỉ huy và người vận hành thống nhất tác động hiện tại, kết quả mong muốn và vì sao cần đường khẩn cấp.

So sánh ít nhất các phương án phù hợp với tình huống:

- Triển khai lại phiên bản đã biết.
- Rollback.
- Vô hiệu hóa một tính năng bằng cơ chế đã quản lý.
- Chuyển lưu lượng sang vùng khỏe.
- Giữ trạng thái hiện tại và cô lập vùng lỗi.

Không mặc định rollback luôn an toàn. Schema dữ liệu, giao thức, cấu hình hoặc migration không tương thích có thể khiến rollback mã nguồn làm hệ thống lỗi nặng hơn.

### Bước 2: Xác định phạm vi và người có thẩm quyền

Lập yêu cầu với dịch vụ, môi trường, hiện vật, manifest, đích triển khai, thời gian và điều kiện dừng. Ghi rõ những quyền không cần cấp.

Người phê duyệt phải có thẩm quyền cho môi trường và loại ngoại lệ đó. Một người quản lý release thông thường chưa chắc có thẩm quyền phê duyệt bỏ qua một kiểm soát an ninh đặc biệt.

### Bước 3: Kiểm tra trạng thái đường khẩn cấp

Trước khi cấp quyền:

- Xác minh môi trường executor và danh tính thực thi.
- Kiểm tra nguồn hiện vật và cấu hình.
- Xác nhận nơi ghi bằng chứng chính hoặc dự phòng.
- Kiểm tra tài nguyên đích và trạng thái triển khai hiện tại.
- Xác nhận cơ chế thu hồi thực sự khả dụng.
- Kiểm tra hành động có phụ thuộc vào thành phần đang bị nghi xâm nhập không.

Nếu một điều kiện không đạt, cần xử lý điều kiện đó hoặc chọn đường dự phòng đã được phê duyệt. Không tự bỏ điều kiện chỉ để tiếp tục tiến trình.

### Bước 4: Cấp quyền JIT và tạo execution

PAM hoặc thành phần cấp quyền tạo assignment phù hợp phạm vi. Executor nhận credential theo cơ chế nền tảng hỗ trợ: danh tính workload, certificate ngắn hạn hoặc token có hạn.

Ưu tiên để credential được cấp trực tiếp cho executor đủ điều kiện. Người vận hành chỉ kích hoạt execution, không cần sao chép secret ra máy cá nhân.

Credential không được ghi vào tham số dòng lệnh, log debug, artifact, ticket hoặc chat. Nếu công cụ đích yêu cầu file credential, dùng vùng lưu tạm được hạn chế quyền truy cập và có cơ chế dọn phù hợp; phải tính đến tiến trình con, cache và crash dump.

### Bước 5: Thực thi với kiểm tra cuối cùng

Ngay trước thao tác thay đổi, executor kiểm tra lại:

- Assignment còn hiệu lực và chưa bị thu hồi.
- Người/workload/đích khớp yêu cầu.
- Digest hiện vật và deployment spec khớp nội dung đã được duyệt.
- Chính sách giới hạn quyền vẫn đang được áp dụng.
- Execution chưa tồn tại hoặc đang được tiếp tục theo cơ chế idempotency hợp lệ.
- Có thể ghi bằng chứng theo đường đã chọn.

Kiểm tra lúc submit không thay cho kiểm tra lúc chạy. Một job chờ hàng đợi quá lâu có thể bắt đầu sau hạn hoặc sau khi sự cố đã đóng.

### Bước 6: Quan sát và quyết định dừng

Theo dõi chỉ số phục hồi, thay đổi tài nguyên và dấu hiệu vượt phạm vi. Điều kiện thành công nên gắn với dịch vụ, không chỉ với exit code của công cụ deploy.

Ví dụ: công cụ trả mã thành công nhưng tỷ lệ thanh toán thành công vẫn không tăng, hoặc workload mới không đạt readiness, thì chưa thể coi sự cố đã được xử lý.

Nếu chạm điều kiện dừng, ngừng tạo thao tác mới, đánh giá trạng thái thực tế và thực hiện phương án phục hồi đã xác định. Một deployment bị dừng có thể để lại trạng thái một phần; cần đối chiếu hệ thống đích trước khi retry hoặc rollback.

### Bước 7: Thu hồi và đóng

Khi hoàn tất hoặc hủy:

1. Đóng khả năng khởi chạy mới.
2. Thu hồi assignment và credential có thể thu hồi.
3. Xác định job đang chạy, queued job, session và tiến trình con còn tồn tại.
4. Kiểm tra quyền phát sinh, tài khoản tạm hoặc thay đổi policy do execution tạo ra.
5. Rotate credential dài hạn đã được mở hoặc có nguy cơ lộ theo policy.
6. Đối chiếu trạng thái đích, kết quả phục hồi và hồ sơ audit.
7. Ghi nhận người đóng và người kiểm tra.

Chỉ “token đã hết hạn” chưa chứng minh rằng mọi hiệu ứng của quyền đã kết thúc.

## 8. Thu hồi quyền: hiểu đúng giới hạn của từng cơ chế

Các nền tảng khác nhau có hành vi thu hồi khác nhau. Cần kiểm thử thay vì suy luận rằng xóa assignment ở PAM sẽ lập tức hủy mọi truy cập.

| Thành phần | Rủi ro còn lại sau khi đóng assignment | Cách kiểm tra |
| --- | --- | --- |
| Token đã phát hành | Có thể còn được chấp nhận đến khi hết hạn hoặc cache cập nhật | Thử lời gọi phù hợp sau thu hồi và đo thời gian hiệu lực thực tế |
| Credential phiên liên kết | Phiên đích có thể sống lâu hơn phiên cấp quyền ban đầu | Kiểm tra TTL, session store và cơ chế terminate của đích |
| Queued job | Job có thể bắt đầu muộn bằng credential lưu sẵn | Hủy hàng đợi, kiểm tra lại quyền lúc khởi chạy |
| Job đang chạy | Tiến trình có thể tiếp tục thay đổi tài nguyên | Xác nhận trạng thái job và hành vi khi credential hết hạn |
| Credential dài hạn được lấy ra | Bản sao có thể tồn tại ngoài vault | Rotation, vô hiệu hóa bản cũ và điều tra nơi sử dụng |
| Quyền hoặc tài khoản được tạo trong phiên | Có thể tồn tại sau khi người cấp quyền đã mất truy cập | Đối chiếu thay đổi IAM/policy/tài khoản với baseline |
| Agent hoặc tiến trình con | Có thể có danh tính hoặc kết nối riêng | Kiểm tra danh sách thực thi, session và kết nối liên quan |

### Ví dụ về “đã thu hồi” nhưng chưa kết thúc

Một operator được phép khởi chạy deployment trong 15 phút. Ở phút thứ 14, job bắt đầu và lấy credential có TTL 30 phút. Đến phút thứ 15, PAM đóng assignment.

Nếu hệ thống đích vẫn tin credential đã cấp, job có thể tiếp tục gọi API. PAM đóng assignment đúng hạn nhưng quyền thực tế ở hệ thống đích chưa chấm dứt ngay.

Thiết kế cần xử lý sự khác biệt này bằng TTL phù hợp, kiểm tra trạng thái assignment trong executor, cơ chế terminate của đích hoặc giới hạn thời lượng execution. Phải báo đúng độ trễ thu hồi đo được; không hứa “thu hồi tức thời” nếu nền tảng không bảo đảm.

## 9. Hiện vật, cấu hình và thay đổi dữ liệu

### 9.1. Dùng hiện vật bất biến

Tên phiên bản hoặc image tag có thể trỏ đến nội dung khác theo thời gian nếu registry cho phép sửa. Quyết định khẩn cấp nên tham chiếu hiện vật bất biến bằng digest và xác minh nội dung thực tế khi lấy về.

Digest chứng minh nội dung khớp với giá trị đã biết; tự nó không chứng minh hiện vật an toàn. Cần biết giá trị được chấp thuận đến từ đâu, ai xây dựng, quá trình xác minh nào đã diễn ra và khóa hoặc nguồn bằng chứng nào đáng tin.

Nếu chính CI bị xâm nhập, một release mới do CI đó tạo có thể không đáng tin dù có digest rõ ràng. Phải đánh giá lại nguồn build, khóa ký và bằng chứng liên quan theo phạm vi sự cố.

### 9.2. Manifest cũng có thể mang đặc quyền

Một image hợp lệ vẫn có thể được triển khai với cấu hình nguy hiểm:

- Chạy bằng service account đặc quyền.
- Gắn secret hoặc volume không cần thiết.
- Mở kết nối mạng hoặc cổng quản trị ngoài phạm vi.
- Thay đổi cấu hình để gửi dữ liệu ra ngoài.
- Kích hoạt hook trước/sau deployment có quyền lớn.

Vì vậy, nếu scope phê duyệt phụ thuộc vào cấu hình, cần ràng buộc và kiểm tra deployment spec bên cạnh image digest. Kiểm soát nguồn image mà bỏ qua manifest chưa đủ kiểm soát hành động triển khai.

### 9.3. Rollback và migration

Trước rollback, cần biết bản cũ có đọc được dữ liệu hiện tại không, migration có đảo ngược được không và rollback có làm mất dữ liệu mới phát sinh không.

Một quyền triển khai ứng dụng không tự cho phép chạy migration phá hủy hoặc restore cơ sở dữ liệu. Các thao tác đó có thể cần quyền riêng, điểm khôi phục, người chấp thuận và kế hoạch xử lý dữ liệu.

Break-glass giảm thời gian chờ cấp quyền; nó không xóa tính không thể đảo ngược của một thay đổi dữ liệu.

## 10. Bằng chứng và giám sát phiên

Audit hữu ích phải giúp nối quyết định với hành động thực tế. Một dòng “operator-a dùng break-glass” chưa đủ để biết người đó đã làm gì.

### 10.1. Chuỗi bằng chứng tối thiểu

Một hồ sơ nên có:

- Request ID, incident ID và mục đích.
- Danh tính người yêu cầu, người quyết định, người vận hành và executor.
- Nội dung scope, ngoại lệ, thời gian và phiên bản policy áp dụng.
- Fingerprint hoặc phiên bản yêu cầu đã được chấp thuận.
- Artifact digest, deployment spec digest và tham chiếu bằng chứng nguồn gốc.
- Thời điểm cấp quyền, khởi chạy, dừng, thu hồi và xác minh thu hồi.
- Execution ID, tài nguyên đích và thay đổi đã quan sát.
- Kết quả theo dõi sức khỏe và quyết định tiếp theo.
- Bất thường, lỗi audit, gia hạn hoặc hành động ngoài dự kiến.

Không ghi raw token, secret, private key hoặc dữ liệu nhạy cảm của ứng dụng vào hồ sơ. Tham chiếu đến credential ID hoặc lease ID thường phù hợp hơn giá trị credential.

### 10.2. Audit dự phòng

Khi nơi tập trung log không khả dụng, có thể dùng journal dự phòng đã thiết kế trước:

- Ghi tuần tự với sequence number hoặc định danh sự kiện duy nhất.
- Hạn chế quyền sửa/xóa của executor.
- Bảo vệ bằng chữ ký, checksum có neo tin cậy hoặc kho ghi một lần theo khả năng nền tảng.
- Ghi nguồn thời gian và độ lệch nếu biết.
- Đồng bộ về nơi tập trung sau phục hồi, phát hiện trùng và thiếu sự kiện.

Checksum của một file log đặt cùng nơi mà kẻ tấn công có thể sửa cả log lẫn checksum không tạo ra bằng chứng độc lập. Tính chống sửa đổi phụ thuộc vào cách giữ khóa, phân quyền và neo bằng chứng.

Nếu cả audit chính lẫn dự phòng không hoạt động, cần áp dụng đúng quyết định đã định nghĩa cho tình huống này. Không được âm thầm chuyển sang chạy không có dấu vết.

### 10.3. Phiên tương tác và workload

Với phiên người dùng tương tác, có thể cần session recording, command audit và kiểm soát clipboard/file transfer theo nền tảng. Cần hạn chế hoặc che dữ liệu nhạy cảm phù hợp.

Với deployment tự động, bằng chứng quan trọng thường là quyết định authorization, API audit của đích, cấu hình execution, digest và kết quả thay đổi. Một video màn hình không thay thế được audit API và danh tính workload.

Mỗi lần kích hoạt break-glass nên tạo cảnh báo đến kênh giám sát phù hợp. Cảnh báo cần chứa thông tin điều tra đủ dùng nhưng không mang secret.

## 11. Tình huống thực hành: khôi phục checkout

Giả sử release mới làm phần lớn yêu cầu thanh toán thất bại. Pipeline thường bị kẹt vì dịch vụ phê duyệt đang lỗi. Hệ thống nhận diện danh tính, registry và audit độc lập vẫn hoạt động.

Bản trước đã có bằng chứng build và được xác minh tương thích dữ liệu hiện tại. Đội vận hành có executor khẩn cấp đã diễn tập.

| Thời điểm minh họa | Hành động | Bằng chứng và giới hạn |
| --- | --- | --- |
| 09:00 | Mở sự cố, xác nhận tác động | Incident ID và chỉ số lỗi |
| 09:03 | Chọn triển khai lại bản trước | Digest, deployment spec, đánh giá tương thích |
| 09:05 | Chấp thuận ngoại lệ cổng phê duyệt chuẩn | Người có thẩm quyền, fingerprint yêu cầu |
| 09:06 | Cấp quyền khởi chạy một lần | Scope checkout/production, hạn 09:21 |
| 09:08 | Executor kiểm tra và bắt đầu | Execution ID và trạng thái assignment nguyên tử |
| 09:12 | Workload ổn định, chỉ số cải thiện | Trạng thái rollout, tỷ lệ lỗi và lưu lượng |
| 09:16 | Đóng quyền và xác minh | Không còn job chờ, credential xử lý theo loại |
| 09:20 | Đối chiếu hồ sơ | Yêu cầu, quyết định, audit đích và kết quả khớp |

Không cần mở quyền đọc toàn bộ secret production hoặc tắt audit để làm việc này. Nếu trong khi triển khai xuất hiện nhu cầu sửa policy mạng, đó là thay đổi scope cần được xử lý rõ ràng.

### Nếu bản trước không tương thích dữ liệu

Đội vận hành không cố rollback chỉ vì quyền đã cấp. Họ dừng yêu cầu, ghi nhận lý do và chọn phương án khác: hotfix có bằng chứng tin cậy, thay đổi cấu hình hạn chế hoặc phục hồi dữ liệu theo quy trình riêng.

### Nếu job trả lỗi sau khi đã đổi một phần tài nguyên

Đầu tiên tra cứu execution và trạng thái đích. Chỉ retry khi biết hành động lặp là an toàn hoặc cơ chế idempotency bảo đảm tiếp tục đúng execution. Việc tạo assignment mới không tự làm một thao tác lặp trở nên an toàn.

## 12. Những lỗi thiết kế thường gặp

### “Tài khoản admin khẩn cấp dùng chung”

Không xác định chắc ai đã làm gì, khó thu hồi từng người và dễ trở thành quyền thường trực. Nếu nền tảng bắt buộc có tài khoản dự phòng chung, cần lớp checkout gắn người dùng, xác thực, giám sát, bảo quản và rotation phù hợp; không chia password trong chat nhóm.

### “Runner lúc nào cũng có secret để dùng khi cần”

Bất kỳ job hoặc mã chạy được trong runner có thể tìm cách sử dụng credential đó. Cần tách đường khẩn cấp và cấp quyền sau khi thỏa điều kiện, thay vì chỉ đặt tên biến là emergency.

### “TTL ngắn là đủ”

TTL không ngăn một credential tạo quyền tồn tại lâu hơn, không hủy mọi session đích và không xóa bản sao secret. Phải giới hạn cả hành động và kiểm tra quyền phát sinh.

### “Người đã được phê duyệt có thể đổi artifact”

Chấp thuận bị tách khỏi nội dung triển khai. Cần gắn quyết định với yêu cầu bất biến và kiểm tra lại ngay trước thay đổi.

### “Tắt admission hoặc audit để deployment chạy”

Một ngoại lệ quá rộng có thể cho phép nhiều chủ thể khác thực hiện hành động ngoài phạm vi cùng thời điểm. Cần ưu tiên ngoại lệ cục bộ có thể xác minh và có thời hạn; mọi thay đổi kiểm soát cấp hạ tầng phải có thẩm quyền, giám sát và cơ chế khôi phục riêng.

### “Chạy xong rồi quên đóng”

Assignment, queued job hoặc tài khoản tạm có thể tồn tại sau sự cố. Quy trình đóng phải có người chịu trách nhiệm và bằng chứng kiểm tra ở hệ thống đích.

### “Đường khẩn cấp chưa từng được diễn tập”

Credential có thể đã hết hiệu lực, người giữ khóa đã chuyển nhóm, runner không còn hoạt động hoặc registry dự phòng thiếu hiện vật. Chỉ có tài liệu hướng dẫn chưa chứng minh được khả năng sử dụng khi có sự cố.

## 13. Diễn tập và tiêu chí chấp nhận

Diễn tập nên bắt đầu trong môi trường phù hợp với rủi ro, dùng credential và hiện vật dành cho kiểm thử. Việc diễn tập trên production cần nằm trong kế hoạch đã được phê duyệt của tổ chức.

### 13.1. Các bài kiểm thử cần có

| Tình huống kiểm thử | Kết quả mong đợi |
| --- | --- |
| Yêu cầu hợp lệ, đúng đích và hiện vật | Tạo đúng một execution, có đủ bằng chứng |
| Đổi digest sau phê duyệt | Từ chối trước thao tác thay đổi |
| Đổi manifest để dùng danh tính đặc quyền hơn | Phát hiện sai nội dung/phạm vi và từ chối |
| Người không được chỉ định thử dùng assignment | Từ chối và ghi sự kiện |
| Submit hai request đồng thời | Không tạo hai execution ngoài policy |
| Job hết hạn khi đang chờ | Không khởi chạy bằng quyền cũ |
| Thu hồi trước khi job bắt đầu | Job không được thực thi |
| Thu hồi khi job đang chạy | Hành vi phù hợp policy và giới hạn thực tế đã đo |
| Mất audit tập trung | Đường dự phòng hoạt động và đối chiếu được sau phục hồi |
| Mất cả audit chính và dự phòng | Hành vi đúng chính sách đã định nghĩa |
| CI bị coi là không đáng tin | Không lấy credential hoặc bằng chứng duy nhất từ CI đó |
| Client timeout sau khi submit | Tra cứu lại execution, không tạo trùng |
| Đóng assignment | Không còn đường khởi chạy, quyền và execution còn lại được kiểm tra |

Kiểm thử âm tính rất quan trọng. Một đường chạy thành công chỉ chứng minh có thể triển khai; nó chưa chứng minh giới hạn quyền thực sự chặn được thao tác sai.

### 13.2. Kiểm tra việc khôi phục kiểm soát

Nếu bài diễn tập hoặc sự cố dùng ngoại lệ tạm thời, cần chứng minh rằng ngoại lệ đã được gỡ. So sánh cấu hình policy, tài khoản, quyền và trạng thái hàng đợi với kết quả mong đợi.

Không chỉ kiểm tra người vận hành đã đăng xuất. Một policy được sửa trong phiên có thể tiếp tục cho phép truy cập sau khi người đó rời hệ thống.

### 13.3. Chỉ số có ích

Có thể theo dõi:

- Thời gian từ yêu cầu đến khi quyền phù hợp sẵn sàng.
- Thời gian từ thực thi đến phục hồi mục tiêu dịch vụ.
- Độ trễ thu hồi thực tế ở hệ thống đích.
- Tỷ lệ assignment đóng có đủ chuỗi bằng chứng.
- Số lần gia hạn và lý do.
- Tỷ lệ lần sử dụng ngoài tiêu chí kích hoạt.
- Số credential hoặc quyền tồn dư được phát hiện.
- Tỷ lệ diễn tập đi qua được kịch bản mất phụ thuộc.

Không tối ưu riêng thời gian cấp quyền bằng cách mở rộng scope hoặc làm mất kiểm soát. Một deployment nhanh nhưng để lại quyền quản trị lâu dài là kết quả không đạt mục tiêu PAM.

## 14. Bài tập thiết kế

Hệ thống có hai dịch vụ checkout và reporting. CI controller bị lỗi, nhưng runner cũ vẫn hoạt động. Runner có credential có thể sửa mọi workload production. Vault còn hoạt động; hệ thống audit tập trung đang mất kết nối. Đội trực muốn rollback checkout.

Hãy mô tả:

1. Những điều kiện cần xác minh trước khi quyết định có thể rollback.
2. Đường executor nào đủ tin cậy và vì sao.
3. Scope JIT/JEA cho checkout, hiện vật và deployment spec.
4. Cách xử lý credential quá rộng của runner cũ.
5. Cách ghi audit dự phòng và đối chiếu sau phục hồi.
6. Cách ngăn job lặp khi client timeout.
7. Cách kết thúc quyền, session và queued job.

### Gợi ý tự đối chiếu

Một thiết kế phù hợp không lấy credential rộng của runner cũ làm mặc định chỉ vì runner còn chạy. Cần đánh giá độ tin cậy của runner, dùng cơ chế cấp quyền hạn chế hoặc executor khẩn cấp đã chuẩn bị.

Quyền cho checkout không mở sang reporting. Đích triển khai, hiện vật và manifest phải khớp quyết định. Audit dự phòng phải có tính toàn vẹn đủ tin cậy; “lưu vào thư mục bất kỳ rồi gửi sau” chưa đáp ứng nếu executor có thể tùy ý sửa hoặc xóa.

Cuối cùng, phải biết rollback có tương thích dữ liệu hiện tại hay không. Quyền được cấp chỉ trả lời ai được làm gì; nó không chứng minh phương án phục hồi là đúng.

## 15. Kết luận

Break-glass deployment là một năng lực phục hồi cần được quản lý như đường truy cập đặc quyền. Nó chỉ hữu ích khi đội vận hành có thể sử dụng trong sự cố thực, đồng thời vẫn chứng minh được chủ thể, phạm vi, hiện vật, thời gian và kết quả.

Thiết kế cần nối liền ba phần: cấp quyền JIT/JEA phù hợp, thực thi có kiểm soát và đóng quyền có xác minh. Một đường khẩn cấp hoàn chỉnh còn phải xử lý phụ thuộc bị hỏng, giới hạn thu hồi của nền tảng và bằng chứng khi audit tập trung không khả dụng.

Khi đã diễn tập những điều kiện này, break-glass giúp khôi phục dịch vụ mà không để quyền khẩn cấp trở thành đặc quyền thường trực.

# Review và loại bỏ quyền dư

## Mục tiêu bài học

Trong chương **Least privilege**, review quyền là quá trình xác nhận một danh tính còn cần những khả năng nào để hoàn thành công việc. Loại bỏ quyền dư là thực hiện và xác minh các thay đổi để quyền thực tế trở về phạm vi cần thiết.

Trong phạm vi **Privileged Access Management (PAM)**, đối tượng rà soát gồm tài khoản quản trị, tài khoản dịch vụ, workload và những đường nhận quyền trên hạ tầng nhạy cảm. Cần xem cả phạm vi tài nguyên, thời gian, credential, phiên và khả năng cấp quyền tiếp.

Sau bài học, bạn có thể:

- Phân biệt quyền dư, quyền chưa được sử dụng và quyền chưa đủ bằng chứng để quyết định.
- Đánh giá quyền hiệu lực thay vì chỉ xem danh sách role được cấp trực tiếp.
- Tổ chức review với chủ sở hữu, bằng chứng và quyết định có thể truy vết.
- Chọn biện pháp thu hồi, thu hẹp hoặc chuyển sang JIT/JEA.
- Xác minh rằng quyền đã giảm ở hệ thống đích và tác vụ hợp lệ vẫn hoạt động.

## 1. Quyền dư là gì?

**Quyền dư là khả năng vượt quá nhu cầu được chấp nhận của chủ thể về hành động, tài nguyên, thời gian hoặc điều kiện sử dụng.**

Một quyền có thể dư theo nhiều chiều:

| Chiều | Ví dụ |
| --- | --- |
| Hành động | Người chỉ chẩn đoán được cấp quyền sửa IAM |
| Tài nguyên | Job của ứng dụng A đọc được bí mật của cả ứng dụng B |
| Môi trường | Người chỉ làm thử nghiệm có quyền quản trị production |
| Thời gian | Quyền migration vẫn tồn tại nhiều tháng sau đợt phát hành |
| Chủ thể | Người đã chuyển đội vẫn nằm trong nhóm quản trị cũ |
| Điều kiện | Pipeline không được bảo vệ vẫn nhận được role phát hành |
| Cấp quyền tiếp | Role vận hành có thể tự gán quyền quản trị tổng quát |

Một tài khoản chỉ có một role vẫn có thể có nhiều quyền dư. Ngược lại, có nhiều role không tự chứng minh quyền quá rộng nếu từng role phục vụ nhu cầu hợp lệ và tổng quyền được kiểm soát.

Mục tiêu không phải làm số role nhỏ nhất. Mục tiêu là để khả năng thực tế phù hợp với nhiệm vụ và mức rủi ro được chấp nhận.

## 2. Phân biệt những trạng thái dễ bị gộp chung

| Trạng thái | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| Quyền đã xác nhận dư | Không còn nhu cầu hoặc vượt phạm vi cần thiết | Lập thay đổi để loại bỏ, thu hẹp hoặc giới hạn thời gian |
| Quyền chưa thấy sử dụng | Không có sự kiện sử dụng trong phạm vi quan sát | Kiểm tra nhu cầu và độ đầy đủ của dữ liệu trước khi kết luận |
| Quyền không rõ chủ sở hữu | Chưa xác định bên chịu trách nhiệm | Tìm chủ sở hữu, đánh giá rủi ro và áp dụng xử lý theo chính sách |
| Quyền có nhu cầu hiếm gặp | Dùng cho chu kỳ dài, phục hồi hoặc sự cố | Xem xét JIT, điều kiện kích hoạt và khả năng truy cập khẩn cấp |
| Quyền cần thiết nhưng quá rộng | Có nhu cầu hợp lệ nhưng role hoặc scope vượt mức | Thiết kế quyền hẹp hơn, không chỉ chọn giữ hoặc xóa toàn bộ |
| Quyền đang được miễn trừ tạm thời | Chưa thể thu hẹp ngay với lý do được chấp nhận | Có chủ sở hữu, giới hạn, biện pháp bù đắp và thời hạn xem xét |

Không có log sử dụng chưa đủ để kết luận quyền dư. Dữ liệu có thể thiếu vì:

- Chỉ thu thập một số giao thức hoặc hành động.
- Log bắt đầu sau thời điểm quyền được dùng.
- Công việc xảy ra theo chu kỳ dài hơn khoảng quan sát.
- Tài khoản có đường nhận role khác nên sự kiện xuất hiện dưới principal khác.
- Quyền phục hồi chỉ được dùng trong tình huống hiếm.
- Hệ thống không ghi đủ chi tiết để phân biệt từng khả năng.

Ngược lại, quyền đã từng được dùng không có nghĩa nó vẫn cần thiết. Việc sử dụng có thể thuộc nhiệm vụ cũ hoặc chính là hành vi ngoài nhu cầu.

## 3. Review phải dựa trên nhu cầu công việc

Một người được cấp quyền không nên chỉ trả lời “vẫn cần admin”. Cần làm rõ:

1. Chủ thể thực hiện nhiệm vụ gì?
2. Trên tài nguyên và môi trường nào?
3. Cần những hành động nào?
4. Tần suất và thời điểm sử dụng ra sao?
5. Có cần quyền thường trực hay có thể cấp theo nhiệm vụ?
6. Có phương án hẹp hơn nhưng vẫn hoàn thành công việc không?
7. Ai có trách nhiệm xác nhận nhu cầu và chấp nhận giới hạn còn lại?

Ví dụ:

> Tài khoản dịch vụ A cần ghi kết quả xử lý vào kho dữ liệu A, không cần đọc bí mật triển khai, quản lý tài khoản hoặc truy cập kho dữ liệu B.

Mô tả này tạo cơ sở để đánh giá quyền, thay vì giữ một role tổng quát vì ứng dụng “đã chạy như vậy từ trước”.

Với quyền khẩn cấp, nhu cầu không được đo chỉ bằng số lần đăng nhập. Cần xác nhận mục đích phục hồi, điều kiện sử dụng, người chịu trách nhiệm và khả năng dùng được khi cần.

## 4. Đánh giá quyền hiệu lực và các đường nhận quyền

Review danh sách cấp trực tiếp là cần thiết nhưng chưa đủ.

```text
Danh tính được rà soát
        |
        +--> Role hoặc quyền trực tiếp
        |
        +--> Nhóm, nhóm lồng nhau và kế thừa
        |
        +--> Role đủ điều kiện kích hoạt
        |
        +--> Chính sách tài nguyên và quan hệ tin cậy
        |
        +--> Quyền quản lý credential hoặc principal khác
        |
        +--> Khả năng sửa workload, mã hoặc chính sách mạnh hơn
                         |
                         v
              Tập khả năng thực tế cần đánh giá
```

Mỗi nền tảng có quy tắc đánh giá riêng. Không nên mặc định quyền hiệu lực chỉ là hợp đơn giản của mọi role.

Các câu hỏi quan trọng:

- Xóa một binding có làm mất khả năng hay role khác vẫn cho phép?
- Người dùng có thể nhận principal khác để làm cùng việc không?
- Có credential độc lập không đi qua hệ thống danh tính trung tâm không?
- Quyền đọc bí mật có mở đường đến credential mạnh hơn không?
- Quyền sửa pipeline hoặc workload có thể được dùng dưới danh tính đặc quyền không?
- Ai có thể tự sửa điều kiện cấp quyền?

### Thu hồi sai đối tượng có thể không đạt mục tiêu

Ví dụ, người A được cấp quyền qua nhóm và qua một role trực tiếp. Xóa role trực tiếp có thể không thay đổi khả năng của A.

Ngược lại, sửa định nghĩa role dùng chung để xử lý riêng người A có thể ảnh hưởng mọi chủ thể đang dùng role đó. Cần phân biệt:

- Xóa một quan hệ gán quyền.
- Thay scope của quan hệ gán.
- Đổi thành viên nhóm.
- Sửa định nghĩa role.
- Xóa principal hoặc credential.

Đây là các thay đổi có phạm vi tác động khác nhau.

## 5. Ai tham gia và chịu trách nhiệm?

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Chủ sở hữu công việc hoặc dịch vụ | Giải thích nhu cầu, phụ thuộc và tác động vận hành |
| Chủ sở hữu tài nguyên hoặc quyền | Xác nhận phạm vi truy cập phù hợp |
| Người quản lý hoặc người bảo trợ | Xác nhận quan hệ công việc, vị trí và thời hạn |
| Nhóm IAM/PAM hoặc nền tảng | Phân tích quyền hiệu lực, cơ chế cấp và thu hồi |
| Người thực hiện thay đổi | Áp dụng đúng thay đổi đã được chấp nhận |
| Người xác nhận kết quả | Kiểm tra quyền thực tế và tác vụ hợp lệ |
| Đội bảo mật hoặc ứng phó | Tham gia khi có dấu hiệu lạm dụng, credential bị lộ hoặc rủi ro cao |

Một người có thể đảm nhiệm nhiều vai trò theo quy mô tổ chức. Với quyền nhạy cảm, cần áp dụng mức xem xét độc lập phù hợp.

Không nên để một người chỉ dựa vào tên role rồi chấp nhận hàng loạt. Người xác nhận nhu cầu cần đủ ngữ cảnh, còn phân tích kỹ thuật phải giải thích được role thực sự cho phép những gì.

## 6. Chuẩn bị một đợt review có bằng chứng

### 6.1. Xác định phạm vi và mốc dữ liệu

Cần nêu:

- Những hệ thống, môi trường và loại danh tính được bao phủ.
- Thời điểm chụp trạng thái cấp quyền.
- Nguồn và khoảng thời gian quan sát sử dụng.
- Những hành động hoặc đường truy cập chưa có dữ liệu.
- Người chịu trách nhiệm và thời hạn của đợt review.

Trong môi trường thay đổi nhanh, kết quả có thể không còn đúng nếu role hoặc tài nguyên thay đổi giữa lúc phân tích và áp dụng. Cần nhận diện sai lệch và xác nhận lại thay đổi liên quan.

### 6.2. Thu thập thông tin tối thiểu cần thiết

| Nhóm bằng chứng | Nội dung |
| --- | --- |
| Danh tính | Loại chủ thể, trạng thái, chủ sở hữu, người bảo trợ |
| Cấp quyền | Role, nhóm, scope, điều kiện, thời hạn và nguồn cấp |
| Công việc | Nhiệm vụ, tài nguyên, lịch chạy, đợt thay đổi hoặc tình huống phục hồi |
| Sử dụng | Hành động, tài nguyên, phiên, kết quả, nguồn audit |
| Credential | Loại, vòng đời, đường phân phối, bên phụ thuộc |
| Thay đổi | Lịch sử chuyển vị trí, tạo role, mở rộng scope hoặc ngoại lệ |
| Thu hồi | Khả năng chặn cấp mới, xử lý credential và phiên đang tồn tại |

Không đưa mật khẩu, token hoặc khóa riêng vào hồ sơ review. Thông tin về credential nên dùng định danh tham chiếu và dữ liệu vòng đời phù hợp.

### 6.3. Đánh dấu độ tin cậy của kết luận

Có thể phân biệt:

- Đã có nhu cầu và bằng chứng đủ rõ.
- Có dấu hiệu dư nhưng cần xác nhận chủ sở hữu.
- Không đủ dữ liệu sử dụng.
- Có phụ thuộc chưa rõ.
- Có rủi ro cần xử lý khẩn cấp theo quy trình sự cố.

Cách phân loại này giúp tránh biến sự thiếu thông tin thành một kết luận chắc chắn.

## 7. Ưu tiên quyền nào trước?

Có thể ưu tiên theo kết hợp của khả năng gây tác động, đường bị lạm dụng và mức thiếu kiểm soát.

Những nhóm thường cần được xem xét sớm:

- Quyền quản lý IAM, cấp role hoặc thay quan hệ tin cậy.
- Quyền quản trị rộng trên production.
- Quyền đọc bí mật dùng chung hoặc quản lý credential của principal khác.
- Quyền thay audit, bản sao lưu hoặc cơ chế phục hồi.
- Tài khoản không có chủ sở hữu hoặc thuộc người đã hết quan hệ công việc.
- Credential dài hạn được dùng chung.
- Role phát hành mà workload không được tin cậy cũng có thể nhận.
- Quyền tạm thời đã quá điều kiện hoặc thời hạn được chấp nhận.

Đây là cách ưu tiên phân tích, không phải quy tắc xóa tự động mọi quyền trong các nhóm này.

Nếu có dấu hiệu đang bị lạm dụng, không nên chờ hết một đợt review định kỳ. Cần chuyển sang quy trình ứng phó, bảo toàn bằng chứng và hạn chế tác động theo mức khẩn cấp.

## 8. Chọn quyết định: không chỉ giữ hoặc xóa

| Quyết định | Khi phù hợp | Điều cần xác nhận |
| --- | --- | --- |
| Giữ có lý do | Quyền đúng nhu cầu và giới hạn phù hợp | Chủ sở hữu, phạm vi và lần xem xét tiếp |
| Thu hồi | Không còn nhu cầu hoặc chủ thể không còn được phép | Phụ thuộc, đường cấp khác và phiên còn hiệu lực |
| Thu hẹp hành động | Có nhiệm vụ nhưng role cho nhiều khả năng hơn cần thiết | Tác vụ hợp lệ vẫn thực hiện được |
| Thu hẹp tài nguyên | Quyền áp dụng quá nhiều môi trường hoặc đối tượng | Nguồn, đích và tài nguyên phụ thuộc đều được xét |
| Giảm thời gian | Chỉ cần trong một nhiệm vụ hoặc khoảng thời gian | Cơ chế cấp, hết hạn, thu hồi và phiên |
| Chuyển sang JIT/JEA | Nhu cầu có thể được đáp ứng bằng cấp theo tác vụ | Điều kiện kích hoạt và khả năng sửa chính ranh giới kiểm soát |
| Tách danh tính | Một principal phục vụ nhiều mục đích hoặc chủ thể | Chuyển đổi credential, audit và trách nhiệm |
| Ngoại lệ có thời hạn | Chưa thể thu hẹp ngay với lý do được chấp nhận | Biện pháp bù đắp, chủ sở hữu, hạn xử lý và quyết định gia hạn |

### JIT không xóa mọi rủi ro của quyền rộng

Nếu tài khoản luôn có thể tự nhận lại role quản trị rộng, việc role có thời hạn chưa chắc giới hạn đủ khả năng sử dụng.

Cần xem cả quyền đủ điều kiện kích hoạt, điều kiện phê duyệt và những quyền có thể tạo ra trong lúc role còn hiệu lực.

### JEA cần giới hạn thực chất

Một công cụ tác vụ hẹp nhưng cho sửa mã, đích hoặc tham số thực thi tùy ý có thể vẫn tạo quyền rộng. Chuyển quyền sang một công cụ như vậy chưa phải thu hẹp hiệu quả.

## 9. Ví dụ xuyên suốt: quyền dư của một pipeline

Một pipeline của ứng dụng A có role với các khả năng:

- Cập nhật dịch vụ A trên production.
- Sửa tài nguyên của các ứng dụng khác.
- Đọc nhiều bí mật không phục vụ triển khai A.
- Quản lý một số binding IAM.
- Thay cấu hình audit.

Chủ sở hữu xác nhận pipeline chỉ cần phát hành ứng dụng A. Dữ liệu sử dụng cho thấy các lần chạy gần đây tập trung vào triển khai A, nhưng không được dùng làm căn cứ duy nhất.

### Phân tích

| Khả năng | Nhu cầu đã xác nhận | Hướng xử lý |
| --- | --- | --- |
| Cập nhật dịch vụ A | Cần cho phát hành | Giữ với scope và điều kiện phù hợp |
| Sửa ứng dụng khác | Không thuộc nhiệm vụ | Loại khỏi quyền của pipeline A |
| Đọc bí mật không liên quan | Không thuộc nhiệm vụ | Thu hẹp đường lấy bí mật và quyền ở đích |
| Quản lý binding IAM | Không cần cho phát hành thông thường | Loại bỏ hoặc chuyển thành nhiệm vụ riêng nếu có nhu cầu hợp lệ |
| Thay audit | Không thuộc nhiệm vụ | Loại khỏi role phát hành |

Trước khi đổi, cần kiểm tra role có được workload khác dùng không. Nếu có, không nên sửa role dùng chung theo cách làm hỏng các nhiệm vụ hợp lệ của bên khác.

Một phương án là tạo hoặc sử dụng tập quyền hẹp cho pipeline A, chuyển đúng binding, xác nhận hoạt động rồi thu hồi binding rộng cũ.

### Hồ sơ quyết định minh họa

Đây là **mô tả hồ sơ review, không phải cấu hình của một công cụ**:

```yaml
review_item:
  id: review-example-028
  subject: application-a-release
  owner: application-a-operations
  target_scope: production/application-a

evidence:
  business_need: release-application-a
  entitlement_snapshot: snapshot-example-12
  usage_reference: audit-query-example-19
  coverage_gaps:
    - rare-recovery-workflow-requires-separate-confirmation

decision:
  outcome: reduce-scope-and-capabilities
  replacement: application-a-release-limited
  old_grant: shared-production-admin-binding
  accepted_by: resource-owner-example

completion:
  target_permission_check: required
  valid_release_check: required
  old_access_paths: reviewed
  session_and_credential_handling: required
```

Hồ sơ nên tham chiếu bằng chứng được bảo vệ thay vì sao chép credential hoặc toàn bộ dữ liệu nhạy cảm vào quyết định.

## 10. Thu hồi có kiểm soát

Một thay đổi quyền cần có mục tiêu cụ thể, ví dụ:

> Pipeline A không còn khả năng quản trị tài nguyên ngoài ứng dụng A, không còn quản lý IAM hoặc audit từ role phát hành.

Từ đó lập kế hoạch:

1. Xác định đúng binding, role, nhóm hoặc policy cần đổi.
2. Kiểm tra bên phụ thuộc và phạm vi ảnh hưởng.
3. Chuẩn bị quyền thay thế nếu vẫn có nhiệm vụ hợp lệ.
4. Xác định thời điểm, người thực hiện và cách xác nhận.
5. Áp dụng thay đổi qua luồng được kiểm soát.
6. Xử lý credential hoặc phiên còn mang quyền cũ theo cơ chế nền tảng.
7. Kiểm tra khả năng cần giữ và khả năng cần loại bỏ.
8. Ghi kết quả, ngoại lệ và công việc còn lại.

### Phương án khôi phục không nên mở lại quyền rộng vô thời hạn

Nếu có lỗi do thiếu quyền thực sự cần, cần xác định hành động và resource còn thiếu để bổ sung phù hợp.

Trong tình huống phải khôi phục quyền cũ để duy trì dịch vụ, nên ghi rõ lý do, phạm vi, thời hạn và hướng xử lý tiếp theo. Nếu mỗi lỗi đều dẫn tới cấp lại quản trị toàn hệ thống vĩnh viễn, review sẽ không tạo giảm quyền bền vững.

### Không thay đổi cấu hình dùng chung mà chưa hiểu tác động

Sửa một role, nhóm hoặc chính sách dùng chung có thể ảnh hưởng nhiều chủ thể. Cần kiểm tra ai đang dùng và liệu họ có cùng nhu cầu hay không.

Thu hẹp một binding cụ thể hoặc tách nhiệm vụ có thể phù hợp hơn việc thay định nghĩa chung cho tất cả.

## 11. Credential, phiên và quyền phát sinh sau thu hồi

Cần phân biệt bốn lớp:

```text
Quyền được cấp / điều kiện nhận quyền
                  |
                  v
Credential đã phát hành hoặc đã lấy
                  |
                  v
Phiên / kết nối đang hoạt động
                  |
                  v
Quyền, credential hoặc cấu hình mới đã tạo trước đó
```

Xử lý lớp đầu không tự bảo đảm mọi lớp sau đã hết hiệu lực.

Ví dụ:

- Xóa thành viên nhóm có thể không vô hiệu hóa ngay một token đã phát hành.
- Chặn lấy bí mật từ vault không thu hồi bản sao credential đã lấy.
- Đổi mật khẩu có thể không kết thúc phiên hiện tại.
- Thu hồi role ban đầu không xóa principal hoặc khóa đã được tạo bằng role đó.
- Vô hiệu hóa danh tính nguồn có thể không xử lý mọi phiên ở hệ thống đích.

Hành vi cụ thể phụ thuộc nền tảng và cơ chế xác thực. Kế hoạch cần xác định cách chặn cấp mới, xử lý quyền đã cấp và xác nhận kết quả.

Với credential bị nghi lộ, ngoài giảm quyền còn cần xử lý sự cố, luân chuyển hoặc thu hồi phù hợp. Không nên coi review là thay thế cho điều tra các tác động đã phát sinh.

## 12. Xác minh thế nào mới được coi là đã xử lý?

Một quyết định “thu hồi” trong hồ sơ chưa chứng minh quyền đã mất ở hệ thống đích.

Cần xác nhận ba nhóm:

| Nhóm xác nhận | Câu hỏi |
| --- | --- |
| Thay đổi được áp dụng | Đúng binding, role, nhóm hoặc policy đã được xử lý chưa? |
| Khả năng hiệu lực | Chủ thể còn đường khác để làm điều cần loại bỏ không? |
| Công việc hợp lệ | Nhiệm vụ cần giữ có hoạt động đúng với quyền mới không? |

Ví dụ cho pipeline A:

- Phát hành A qua luồng được chấp nhận vẫn hoạt động.
- Không còn quyền thay tài nguyên B theo mục tiêu thiết kế.
- Không còn quyền quản lý IAM hoặc audit từ danh tính phát hành.
- Không còn credential hoặc phiên cũ tiếp tục cho quyền rộng ngoài chính sách.
- Nguồn audit đủ để đối chiếu những kết luận này.

Cách xác nhận phải phù hợp với hệ thống và mức tác động. Không cần thực hiện một thao tác phá hủy trên production để chứng minh nó bị cấm; có thể dùng cơ chế đánh giá quyền hoặc môi trường xác nhận phù hợp nếu nền tảng hỗ trợ.

Nếu còn khoảng trống dữ liệu hoặc quyền đang chờ hết hạn theo cơ chế nền tảng, cần ghi trạng thái đó. Không nên đóng mục review chỉ vì lệnh cập nhật chính sách đã trả thành công.

## 13. Quản lý ngoại lệ và nhu cầu hiếm gặp

Một ngoại lệ nên có:

- Quyền và scope chưa thu hẹp được.
- Nhu cầu hoặc hạn chế kỹ thuật cụ thể.
- Chủ sở hữu chịu trách nhiệm.
- Rủi ro còn lại và quyết định chấp nhận theo thẩm quyền.
- Biện pháp bù đắp.
- Thời hạn và điều kiện xem xét lại.
- Công việc cần hoàn thành để kết thúc ngoại lệ.

Biện pháp bù đắp có thể gồm thời gian truy cập ngắn hơn, cảnh báo, hạn chế ngữ cảnh, giám sát hoặc quy trình tác vụ riêng. Chúng không nên được mô tả là đã loại bỏ quyền dư nếu quyền rộng vẫn tồn tại.

Đối với phục hồi và công việc hiếm gặp, có thể giữ một đường nhận quyền được kiểm soát thay vì giữ đặc quyền thường trực. Cần xác nhận đường đó khả dụng trong tình huống mà nó được thiết kế phục vụ.

Không đặt thời hạn lưu log hoặc ngưỡng “không dùng bao lâu thì xóa” như quy tắc chung cho mọi hệ thống. Các giá trị phải dựa trên công việc, chu kỳ, mức rủi ro và yêu cầu áp dụng.

## 14. Bằng chứng và chỉ số theo dõi

### Bằng chứng của một mục review

Nên liên kết được:

1. Trạng thái quyền trước thay đổi.
2. Nhu cầu được xác nhận và nguồn dữ liệu sử dụng.
3. Giới hạn quan sát hoặc phụ thuộc chưa rõ.
4. Người quyết định, lý do và thời điểm.
5. Thay đổi được áp dụng.
6. Kết quả xác minh ở đích.
7. Ngoại lệ hoặc việc còn lại.

Bằng chứng cần được bảo vệ khỏi sửa hoặc xóa trái phép, đồng thời giới hạn người xem vì có thể tiết lộ cấu trúc quyền và tài nguyên nhạy cảm.

### Chỉ số không nên chỉ đếm số nút “đã duyệt”

Các chỉ số hữu ích có thể gồm:

- Tỷ lệ chủ thể trong phạm vi đã được review với bằng chứng đủ.
- Số phát hiện đã có quyết định nhưng chưa áp dụng.
- Số phát hiện đã áp dụng nhưng chưa xác minh.
- Số ngoại lệ quá thời hạn.
- Thời gian từ khi xác nhận quyền dư đến khi xử lý và xác minh.
- Số đường quyền rộng tái xuất hiện sau khi đã xử lý.

Cần định nghĩa đơn vị đo nhất quán. Đếm role, binding, capability và danh tính lẫn nhau có thể tạo tỷ lệ gây hiểu nhầm.

Ví dụ, trong một đợt có **12 phát hiện đã xác nhận cần giảm quyền**:

- 5 phát hiện được thu hồi và xác minh.
- 4 phát hiện được thu hẹp hoặc chuyển sang cơ chế theo nhiệm vụ, đã xác minh.
- 3 phát hiện còn ngoại lệ hoặc chờ xử lý.

Tỷ lệ xử lý đã xác minh của tập phát hiện đó là **9/12 = 75%**. Không nên tính ba ngoại lệ thành đã loại bỏ quyền dư chỉ vì đã có người chấp nhận.

Tỷ lệ này không đo mức giảm rủi ro tổng thể: một phát hiện quản trị toàn tổ chức có thể quan trọng hơn nhiều phát hiện phạm vi nhỏ.

## 15. Duy trì kết quả sau đợt review

Quyền có thể tăng trở lại khi:

- Người dùng đổi vị trí nhưng giữ quyền cũ.
- Pipeline hoặc ứng dụng mới dùng role có sẵn quá rộng.
- Sự cố dẫn tới quyền tạm thời không được thu hồi.
- Nhãn, nhóm hoặc phạm vi cha thay đổi.
- Một role dùng chung được bổ sung khả năng mới.
- Tài nguyên mới tự nằm trong phạm vi wildcard hoặc kế thừa.

Vì vậy, ngoài review theo lịch còn cần xem xét theo sự kiện như chuyển vị trí, kết thúc dự án, đổi chủ sở hữu, thay role hoặc thay quan hệ tin cậy.

Có thể tự động hóa việc tập hợp dữ liệu, phát hiện thay đổi và nhắc xử lý. Quyết định tự động cần dựa trên quy tắc đủ rõ và được chấp nhận; không nên biến dữ liệu “last used” thiếu ngữ cảnh thành cơ chế xóa quyền hàng loạt.

## 16. Tình huống tự đánh giá

Một tổ chức định thu hồi mọi quyền không có log sử dụng trong một khoảng quan sát. Danh sách gồm:

- Quyền production cũ của người đã chuyển đội.
- Quyền phục hồi khẩn cấp chưa từng dùng trong khoảng đó.
- Role của job chạy theo chu kỳ dài hơn thời gian quan sát.
- Một role không thấy dùng trực tiếp nhưng chủ thể có thể nhận role khác.
- Credential lấy từ vault trước đây vẫn còn hiệu lực ở đích.

### Phân tích

**Người đã chuyển đội:** cần xác nhận nhu cầu hiện tại; quyền cũ có thể đã dư nhưng vẫn phải xử lý đúng binding, credential và phiên.

**Quyền phục hồi:** thiếu sử dụng không chứng minh không cần; cần đánh giá đường khẩn cấp, chủ sở hữu và điều kiện kích hoạt.

**Job theo chu kỳ dài:** khoảng quan sát chưa đủ đại diện; cần lịch công việc và bằng chứng bổ sung.

**Đường nhận role khác:** không thể chỉ dựa vào thống kê role trực tiếp; cần phân tích quan hệ tin cậy và principal đích.

**Credential đã lấy:** thu hồi quyền truy cập vault không tự thu hồi quyền sử dụng credential ở đích.

### Hướng xử lý

Phân nhóm theo mức chắc chắn và rủi ro, xác nhận nhu cầu với chủ sở hữu, chọn giữ, thu hẹp, chuyển sang quyền theo nhiệm vụ hoặc thu hồi. Mỗi thay đổi cần có kết quả xác minh và ngoại lệ rõ ràng.

Kết quả review có chất lượng phải giải thích được vì sao quyền được giữ hoặc thay đổi, thay vì chỉ dựa vào một trường dữ liệu.

## 17. Những điểm cần ghi nhớ

- Quyền dư là quyền vượt nhu cầu về hành động, tài nguyên, thời gian hoặc điều kiện; không đồng nghĩa mọi quyền chưa thấy dùng.
- Review cần kết hợp nhiệm vụ, quyền hiệu lực, bằng chứng sử dụng và giới hạn quan sát.
- Phải xem cả kế thừa, nhóm, điều kiện nhận role và đặc quyền gián tiếp.
- Biện pháp có thể là thu hồi, thu hẹp, tách danh tính hoặc chuyển sang JIT/JEA; không chỉ giữ hay xóa.
- Credential và phiên có vòng đời riêng. Quyết định thu hồi chưa đủ nếu quyền vẫn dùng được ở đích.
- Chỉ coi một phát hiện đã xử lý khi **thay đổi được áp dụng, quyền thực tế phù hợp và tác vụ hợp lệ được xác nhận**.
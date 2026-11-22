# Kích hoạt thủ công với đầu vào được kiểm tra

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt kích hoạt thủ công một quy trình với phê duyệt một bước trong quy trình đã chạy.
- Chọn trường hợp phù hợp để dùng manual trigger trong CI/CD.
- Thiết kế bộ đầu vào có kiểu dữ liệu, giá trị cho phép, mặc định và ràng buộc rõ ràng.
- Kiểm tra đầu vào ở phía thực thi, giới hạn quyền và bảo vệ bí mật.
- Thiết kế luồng xem trước, xác nhận, thực thi, xác minh và ghi dấu vết.
- Kiểm soát chạy lặp, chạy đồng thời và xử lý lỗi để thao tác thủ công có thể lặp lại an toàn.

## 1. Kích hoạt thủ công là gì?

Trong CI/CD, nhiều quy trình bắt đầu tự động khi có sự kiện Git như push, pull request, tạo tag hoặc hợp nhất vào nhánh chính. Tuy nhiên, có những hoạt động chỉ nên bắt đầu khi một người chủ động yêu cầu. Ví dụ: triển khai một artifact đã được kiểm thử lên môi trường cụ thể, chạy lại một tác vụ bảo trì, thực hiện migration có kiểm soát hoặc khôi phục một phiên bản đã biết.

**Kích hoạt thủ công (manual trigger)** là cơ chế cho phép người có quyền bắt đầu một workflow hoặc job bằng cách cung cấp một tập đầu vào được định nghĩa trước. Người khởi chạy chọn hành động, đối tượng và phạm vi thực hiện; pipeline kiểm tra các giá trị này trước khi tạo ra tác động.

Manual trigger không có nghĩa là con người phải thực hiện các bước kỹ thuật bằng tay. Con người đưa ra yêu cầu có chủ đích; pipeline vẫn kiểm tra, thực thi, xác minh và ghi nhận kết quả tự động.

Cần phân biệt hai khái niệm:

- **Manual trigger:** người dùng chủ động khởi chạy một workflow chưa chạy, chẳng hạn yêu cầu triển khai artifact digest lên staging.
- **Manual approval:** workflow đã chạy đến một điểm chờ và yêu cầu người có thẩm quyền cho phép đi tiếp, chẳng hạn phê duyệt rollout production sau khi staging đạt.

Hai cơ chế có thể xuất hiện trong cùng một luồng. Một người có thể khởi chạy workflow phát hành, sau đó một người khác phê duyệt bước production. Việc nhấn nút chạy workflow không tự động đồng nghĩa với việc mọi cổng kiểm soát đã được thông qua.

## 2. Khi nào nên dùng manual trigger?

Manual trigger hữu ích khi thời điểm thực hiện phụ thuộc vào quyết định vận hành hoặc khi cần chọn một đối tượng cụ thể.

| Trường hợp | Đầu vào thường cần | Lý do cần chủ động khởi chạy |
|---|---|---|
| Triển khai staging | Artifact digest, môi trường | Chọn phiên bản cần xác minh |
| Phát hành production | Artifact đã kiểm thử, lý do phát hành | Chủ động chọn thời điểm theo chính sách |
| Rollback | Phiên bản đích, lý do, mã sự cố | Chọn phiên bản đã biết để khôi phục |
| Chạy migration | Migration ID, môi trường, kế hoạch | Thực hiện thay đổi dữ liệu có tác động |
| Chạy tác vụ bảo trì | Loại tác vụ, phạm vi, chế độ dry-run | Tránh chạy định kỳ ngoài nhu cầu |
| Tạo dữ liệu kiểm thử | Dataset, tenant hoặc namespace | Chuẩn bị dữ liệu cho một hoạt động cụ thể |
| Chạy lại một bước | Pipeline run hoặc artifact liên quan | Điều tra và xử lý lỗi có kiểm soát |

Không nên dùng manual trigger cho mọi kiểm thử thông thường. Lint, unit test và các kiểm tra cần chạy trên mỗi pull request nên được tự động hóa theo sự kiện Git. Nếu người phát triển phải nhớ nhấn nút để kiểm tra chất lượng cơ bản, quy trình dễ bỏ sót và phản hồi chậm.

Một quy tắc hữu ích là: **tự động kích hoạt những việc cần xảy ra nhất quán theo sự kiện; dùng manual trigger cho hành động cần lựa chọn có chủ đích về thời điểm, đối tượng hoặc phạm vi.**

## 3. Đầu vào là một hợp đồng, không phải một dòng lệnh tùy ý

Khi thiết kế manual trigger, đừng bắt đầu bằng một ô văn bản tự do kiểu “nhập lệnh cần chạy”. Hãy mô hình hóa đầu vào thành một hợp đồng (input contract) có cấu trúc.

Một trường đầu vào nên xác định:

- **Tên:** tên ngắn, có ý nghĩa, nhất quán.
- **Kiểu dữ liệu:** chuỗi, số, boolean, lựa chọn có sẵn, môi trường hoặc mã định danh.
- **Bắt buộc hay tùy chọn:** có được bỏ trống không.
- **Giá trị mặc định:** nếu có, mặc định phải an toàn và dễ hiểu.
- **Miền giá trị:** danh sách cho phép, khoảng số, định dạng hoặc độ dài.
- **Ý nghĩa:** trường được dùng để quyết định điều gì.
- **Mức độ tin cậy:** dữ liệu có phải do người dùng cung cấp và cần kiểm tra lại không.

Ví dụ hợp đồng cho thao tác triển khai:

| Trường | Kiểu | Quy tắc |
|---|---|---|
| operation | Enum | Chỉ deploy hoặc rollback |
| target_environment | Enum / Environment | Chỉ môi trường được workflow hỗ trợ |
| artifact_digest | String | Bắt buộc, đúng định dạng digest và phải tồn tại trong kho tin cậy |
| reason | String | Bắt buộc, giới hạn độ dài, không chỉ chứa khoảng trắng |
| change_reference | String | Mã ticket hoặc change record theo định dạng quy định |
| dry_run | Boolean | Mặc định true nếu thao tác hỗ trợ xem trước |
| replica_count | Number | Chỉ dùng khi có nhu cầu; giới hạn trong khoảng được phép |

Không phải workflow nào cũng cần tất cả trường trên. Chỉ yêu cầu thông tin thực sự cần thiết để xác định hành động và kiểm soát rủi ro. Quá nhiều trường làm người dùng khó hiểu và khuyến khích nhập dữ liệu tùy tiện.

### 3.1. Ưu tiên kiểu dữ liệu và danh sách lựa chọn

Nếu chỉ có ba môi trường dev, staging, production, hãy dùng lựa chọn có sẵn thay vì yêu cầu người dùng tự gõ. Danh sách lựa chọn giảm lỗi chính tả và làm rõ phạm vi được phép.

Tương tự, nếu chỉ có các thao tác deploy, rollback và dry-run, hãy định nghĩa chúng thành enum hoặc lựa chọn riêng. Không nên dùng một chuỗi tự do rồi diễn giải chuỗi đó như tên lệnh shell.

Boolean phải thực sự là boolean. Không nên xử lý chuỗi "false" như một giá trị truthy chỉ vì ngôn ngữ script coi chuỗi không rỗng là đúng. Số cần được kiểm tra giới hạn và đơn vị; ví dụ replica_count là số nguyên dương, không phải một chuỗi bất kỳ.

### 3.2. Kiểm tra ràng buộc giữa các trường

Một giá trị riêng lẻ có thể hợp lệ nhưng tổ hợp của nhiều giá trị lại không hợp lệ.

Ví dụ:

- operation=rollback thì phải có phiên bản đích đã được lưu và còn khả năng triển khai.
- target_environment=production thì artifact phải vượt qua các gate bắt buộc cho production.
- dry_run=false với migration phá hủy dữ liệu có thể yêu cầu change record và phê duyệt bổ sung.
- operation=deploy không được nhận một digest chưa có trong artifact registry.
- replica_count chỉ được cung cấp cho loại dịch vụ có hỗ trợ thay đổi số replica.

Vì vậy, cần có bước kiểm tra tổ hợp đầu vào trước khi thực thi.

## 4. Kiểm tra đầu vào ở phía thực thi

Biểu mẫu của nền tảng có thể giúp người dùng nhập đúng kiểu dữ liệu, nhưng không phải ranh giới bảo mật. Đầu vào có thể đến từ API, CLI, một lần chạy được gọi lại hoặc một nguồn khác. Người dùng cũng có thể chọn nhánh mã chứa workflow khác với nhánh mặc định.

Do đó, pipeline phải xác minh lại các giá trị ở phía thực thi.

Có thể chia kiểm tra thành bốn lớp:

### 4.1. Kiểm tra cú pháp

Xác nhận giá trị có định dạng hợp lệ:

- Chuỗi không rỗng sau khi trim.
- Digest đúng định dạng mà registry sử dụng.
- Mã ticket đúng quy ước.
- Số nằm trong khoảng và có kiểu phù hợp.
- Giá trị enum thuộc danh sách đã khai báo.
- Chuỗi không vượt quá giới hạn độ dài.

### 4.2. Kiểm tra ngữ nghĩa

Xác nhận giá trị có ý nghĩa trong hệ thống:

- Artifact thực sự tồn tại trong registry.
- Artifact được tạo từ repository và commit được phép.
- Phiên bản không bị thu hồi hoặc đánh dấu cấm phát hành.
- Môi trường đích đã được cấu hình.
- Migration ID có trong danh mục migration được quản lý.
- Phiên bản rollback còn tương thích với schema và cấu hình hiện tại.

### 4.3. Kiểm tra chính sách

Xác nhận hành động được phép theo quy tắc vận hành:

- Người khởi chạy có quyền yêu cầu thao tác.
- Nhánh hoặc nguồn workflow được phép thực hiện hành động.
- Môi trường có cho phép triển khai ở thời điểm này không.
- Artifact đã vượt qua các cổng bắt buộc chưa.
- Thay đổi có cần phê duyệt hoặc change record không.
- Tài nguyên đích có đang bị khóa hoặc có rollout khác không.

### 4.4. Kiểm tra trạng thái ngay trước khi tác động

Một số điều kiện có thể thay đổi sau khi workflow bắt đầu. Ví dụ môi trường vừa được triển khai bởi pipeline khác, digest bị thu hồi hoặc cửa sổ phát hành đã đóng. Trước bước có tác động, cần xác minh lại những điều kiện này.

Nếu một kiểm tra quan trọng không thể thực hiện, pipeline nên dừng với trạng thái rõ ràng. Không nên tự bỏ qua chỉ vì dịch vụ kiểm tra tạm thời không truy cập được.

## 5. Quyền khởi chạy và quyền thực thi là hai lớp riêng

Một người có quyền mở workflow không nhất thiết có quyền triển khai đến mọi môi trường. Quyền khởi chạy xác định ai được gửi yêu cầu; quyền thực thi xác định pipeline được phép làm gì sau khi yêu cầu được xác thực.

Ví dụ:

| Vai trò | Có thể yêu cầu | Quyền thực thi tương ứng |
|---|---|---|
| Developer | Chạy test, triển khai preview hoặc staging | Không có credential production |
| Release manager | Yêu cầu phát hành artifact đã đạt gate | Có thể khởi tạo quy trình; production vẫn theo policy |
| Production approver | Phê duyệt rollout theo phạm vi được giao | Có quyền phê duyệt, không nhất thiết có quyền sửa artifact |
| Platform operator | Chạy một số tác vụ vận hành | Quyền giới hạn theo hệ thống và thời gian |

Cần lưu ý:

- Không tin trường requested_by do người dùng tự nhập để xác định danh tính. Lấy danh tính từ nền tảng.
- Không coi input approved=true là bằng chứng phê duyệt.
- Không để người có quyền chạy workflow tùy ý chọn môi trường rồi nhận luôn quyền quản trị môi trường đó.
- Dùng environment protection, role-based access hoặc cơ chế tương đương để bảo vệ bước nhạy cảm.
- Khi cần phân tách nhiệm vụ, người khởi chạy và người phê duyệt phải được kiểm tra theo chính sách.
- Cấp credential ở job cần sử dụng, không cấp toàn workflow nếu các bước khác không cần.

Manual trigger là điểm bắt đầu của một quy trình được kiểm soát. Nó không thay thế hệ thống phân quyền và không tự tạo ra quyền cho người yêu cầu.

## 6. Không truyền bí mật qua input

Không yêu cầu người dùng nhập password, access token, private key hoặc connection string vào biểu mẫu manual trigger. Các giá trị này có thể xuất hiện trong lịch sử chạy, log, API request, thông báo hoặc giao diện quản trị.

Thay vào đó:

- Lưu bí mật trong secret manager hoặc kho bí mật của nền tảng.
- Cấp secret theo môi trường và job.
- Dùng danh tính workload hoặc token ngắn hạn khi nền tảng hỗ trợ.
- Giới hạn quyền và thời gian tồn tại của credential.
- Không in giá trị bí mật ra log, kể cả trong thông báo lỗi.
- Thu hồi và luân chuyển bí mật nếu phát hiện bị lộ.

Input nên chứa **tham chiếu** đến tài nguyên được quản lý, không chứa bí mật của tài nguyên đó. Ví dụ người dùng chọn production-eu như một environment ID đã được cấu hình; workflow tự lấy credential được cấp cho environment này theo chính sách.

Việc che log không thay thế cho thiết kế không truyền bí mật. Secret masking có thể không nhận diện được giá trị đã biến đổi, mã hóa hoặc chia nhỏ trước khi ghi log.

## 7. Thiết kế luồng manual trigger an toàn

Một workflow thủ công tốt có thể chia thành sáu bước:

1. **Nhận yêu cầu:** lấy danh tính người khởi chạy, thời điểm, workflow ref và các input.
2. **Xác thực đầu vào:** kiểm tra kiểu, miền giá trị, định dạng và ràng buộc giữa các trường.
3. **Kiểm tra quyền và policy:** xác nhận người yêu cầu, artifact, môi trường và điều kiện phát hành.
4. **Xem trước:** hiển thị hành động dự kiến, đối tượng, phạm vi ảnh hưởng và những thay đổi sẽ xảy ra.
5. **Thực thi:** chỉ thực hiện khi tất cả gate bắt buộc đạt và có phê duyệt nếu cần.
6. **Xác minh và ghi nhận:** kiểm tra trạng thái sau thao tác, lưu kết quả và liên kết tới lần chạy.

~~~mermaid
flowchart TD
    A["Người có quyền gửi yêu cầu"] --> B["Nhận input + actor + workflow ref"]
    B --> C["Validate schema và giá trị"]
    C --> D{"Input hợp lệ?"}
    D -- "Không" --> X["Từ chối, chỉ rõ trường lỗi"]
    D -- "Có" --> E["Kiểm tra quyền và policy"]
    E --> F{"Được phép?"}
    F -- "Không" --> Y["Chặn và ghi audit"]
    F -- "Có" --> G["Resolve artifact và target"]
    G --> H["Dry-run / preview"]
    H --> I{"Gate và approval đạt?"}
    I -- "Không" --> Z["Dừng, giữ nguyên trạng thái"]
    I -- "Có" --> J["Thực thi có kiểm soát"]
    J --> K["Post-action verification"]
    K --> L{"Kết quả đạt?"}
    L -- "Không" --> M["Dừng rollout / recovery"]
    L -- "Có" --> N["Ghi audit và kết quả"]
~~~

Không phải mọi thao tác đều cần một bước dry-run riêng, nhưng với deploy production, migration hoặc thao tác có thể phá hủy dữ liệu, xem trước thường giúp người vận hành nhận ra sai môi trường hoặc sai phạm vi trước khi hành động.

## 8. Dry-run, xác nhận và hành động có tác động lớn

dry_run cho phép pipeline tính toán hoặc kiểm tra những gì sẽ xảy ra mà chưa thực hiện thay đổi. Một dry-run hữu ích cần trả về kết quả cụ thể:

- Môi trường và tài nguyên đích.
- Artifact hoặc phiên bản được chọn.
- Số lượng tài nguyên bị ảnh hưởng.
- Migration hoặc thao tác dự kiến.
- Điều kiện còn thiếu và gate chưa đạt.
- Các cảnh báo về khả năng tương thích hoặc phục hồi.

Không nên hiển thị “Dry run passed” nếu thực tế chỉ bỏ qua bước deploy. Dry-run cần chạy những kiểm tra có thể thực hiện mà không gây tác động và phải mô tả rõ những điều chưa thể xác minh.

Với thao tác phá hủy hoặc khó đảo ngược, có thể cần thêm bước xác nhận riêng. Ví dụ một tác vụ xóa dữ liệu yêu cầu chọn đúng environment, nhập mã xác nhận được tạo cho lần chạy hoặc được người có thẩm quyền phê duyệt. Không nên chỉ dựa vào một checkbox hoặc chuỗi confirm=yes do người yêu cầu tự nhập.

Cũng cần giới hạn phạm vi. Nếu tác vụ chỉ cần xử lý một tenant hoặc một nhóm tài nguyên, input nên biểu diễn đúng phạm vi đó và workflow cần xác minh phạm vi nằm trong allowlist.

## 9. Chọn artifact và phiên bản bằng định danh bất biến

Một lỗi thường gặp là cho phép người dùng nhập tên nhánh như main, latest hoặc release rồi triển khai trực tiếp. Các tham chiếu này có thể trỏ đến nội dung khác ở những thời điểm khác nhau.

Đối với hoạt động phát hành, nên chọn artifact đã được tạo và kiểm thử, định danh bằng digest hoặc ID bất biến. Pipeline có thể nhận một artifact_id, sau đó tra registry để lấy metadata và xác minh:

- Artifact thuộc đúng sản phẩm hoặc repository.
- Artifact được tạo từ commit được phép.
- Digest khớp với dữ liệu registry.
- Các kiểm tra bắt buộc đã đạt.
- Artifact chưa bị thu hồi.
- Artifact tương thích với môi trường và phiên bản dependency.

Nếu cần hỗ trợ rollback, hãy chọn một release ID hoặc digest đã tồn tại trong danh mục phát hành. Không nên yêu cầu người vận hành nhập URL tùy ý rồi tải gói từ nguồn không được tin cậy.

Tương tự, workflow ref hoặc branch được chọn để chạy manual trigger cũng cần được giới hạn. Một workflow có quyền production nhưng được chạy từ một nhánh chứa mã cấu hình chưa được review có thể tạo ra rủi ro. Hãy quy định nguồn workflow được phép, bảo vệ nhánh và giữ policy nhạy cảm ở vị trí được quản trị.

## 10. Chống chạy lặp và xung đột

Manual trigger dễ bị nhấn nhiều lần khi giao diện chậm hoặc người dùng không chắc lần chạy trước đã bắt đầu. Nếu workflow triển khai không được thiết kế để chạy lặp an toàn, hai lần chạy có thể cùng thay đổi môi trường hoặc thực hiện migration hai lần.

Một số cơ chế cần cân nhắc:

**Idempotency key:** mỗi yêu cầu có một mã duy nhất. Nếu cùng một yêu cầu được gửi lại, hệ thống nhận diện và trả về kết quả của lần xử lý trước hoặc tiếp tục theo trạng thái an toàn, thay vì thực hiện lại toàn bộ.

**Concurrency control:** giới hạn số workflow được phép tác động lên cùng một môi trường hoặc tài nguyên tại một thời điểm.

**State check:** trước khi thực thi, xác minh trạng thái hiện tại. Ví dụ nếu artifact đã được triển khai đúng lên staging, workflow có thể báo đã hoàn tất thay vì triển khai lại.

**Retry có giới hạn:** chỉ retry các lỗi tạm thời như timeout mạng hoặc lỗi dịch vụ phụ thuộc. Không retry mù quáng thao tác không idempotent.

**Timeout và cancellation:** xác định thời gian tối đa, cách dừng an toàn và cách xử lý nếu job bị hủy giữa chừng.

Không nên dùng một concurrency lock toàn cục nếu các môi trường hoặc dịch vụ không liên quan nhau. Khóa theo phạm vi thực sự có xung đột để giữ khả năng thực thi song song.

## 11. Ghi audit trail cho mỗi lần chạy

Một thao tác được khởi chạy thủ công cần truy vết được ai đã yêu cầu, yêu cầu điều gì, pipeline đã quyết định ra sao và hệ thống cuối cùng ở trạng thái nào.

Một bản ghi audit nên có tối thiểu:

| Trường | Ý nghĩa |
|---|---|
| Run ID | Định danh lần chạy |
| Actor | Danh tính thực của người khởi chạy từ nền tảng |
| Workflow ref | Phiên bản cấu hình workflow được thực thi |
| Requested action | Thao tác được yêu cầu |
| Inputs đã chuẩn hóa | Giá trị hợp lệ sau khi kiểm tra, loại bỏ dữ liệu nhạy cảm |
| Artifact identity | Commit, release ID hoặc digest |
| Target | Môi trường và phạm vi tài nguyên |
| Policy result | Các gate đạt, không đạt hoặc được miễn trừ |
| Approval | Người duyệt, thời điểm và phạm vi phê duyệt |
| Execution result | Bước đã thực hiện và trạng thái cuối |
| Verification | Bằng chứng sau thao tác |
| Correlation ID | Mã liên kết log, deployment và sự cố |

Không ghi bí mật hoặc giá trị nhạy cảm vào audit trail. Cần chuẩn hóa input trước khi lưu, giới hạn quyền đọc và giữ dữ liệu theo chính sách lưu trữ. Log của pipeline nên liên kết với bản ghi audit để người điều tra có thể đi từ yêu cầu đến kết quả.

Audit trail không chỉ phục vụ điều tra sau sự cố. Nó còn giúp đội ngũ nhận ra manual trigger nào thường bị nhập sai, hành động nào hay thất bại và có bước nào nên được tự động hóa theo sự kiện thay vì yêu cầu con người khởi chạy.

## 12. Ví dụ mô hình workflow manual trigger

YAML sau mô tả hợp đồng logic tổng quát, không phải cú pháp chạy trực tiếp trên một nền tảng CI/CD cụ thể:

~~~yaml
workflow:
  name: controlled-deployment
  trigger:
    type: manual
    inputs:
      operation:
        type: enum
        required: true
        allowed:
          - deploy
          - rollback

      target_environment:
        type: enum
        required: true
        allowed:
          - staging
          - production

      artifact_digest:
        type: string
        required: true
        format: sha256
        max_length: 71

      change_reference:
        type: string
        required: true
        pattern: "CHANGE-[0-9]+"

      reason:
        type: string
        required: true
        min_length: 10
        max_length: 300

      dry_run:
        type: boolean
        required: false
        default: true

  validate:
    - validate_input_schema
    - verify_actor_permission
    - verify_artifact_exists_and_is_trusted
    - verify_artifact_policy
    - verify_target_environment
    - verify_operation_constraints

  preview:
    enabled: true
    show:
      - actor
      - operation
      - target_environment
      - artifact_digest
      - change_reference
      - expected_impact

  execute:
    requires:
      - validation_passed
      - approval_if_required
      - environment_available
    controls:
      - idempotency_key
      - concurrency_lock
      - timeout
    steps:
      - perform_requested_operation
      - verify_actual_state
      - record_audit_event
~~~

Ví dụ cho thấy các input được khai báo trước, có kiểu và miền giá trị. Pipeline vẫn phải xác minh artifact, quyền và trạng thái môi trường ở phía thực thi. Không nên xem schema của biểu mẫu là bằng chứng duy nhất cho tính hợp lệ.

Các nền tảng như GitHub Actions, GitLab CI và Jenkins có cú pháp khai báo tham số thủ công khác nhau. Khi triển khai, cần ánh xạ hợp đồng logic này sang kiểu input, quyền, environment protection và secret scope của nền tảng đang dùng. Phần kiểm tra ở phía thực thi vẫn phải được giữ lại.

## 13. Những trạng thái nên trả về cho người khởi chạy

Một workflow manual trigger cần phân biệt được các kết quả để người dùng biết bước tiếp theo.

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| REJECTED | Input không hợp lệ hoặc không đáp ứng policy | Sửa trường được chỉ ra hoặc yêu cầu quyền phù hợp |
| BLOCKED | Thiếu điều kiện, môi trường hoặc phê duyệt | Bổ sung điều kiện hoặc chờ người có thẩm quyền |
| PREVIEWED | Đã kiểm tra và tạo kế hoạch, chưa thực thi | Xem lại phạm vi và xác nhận nếu được phép |
| RUNNING | Đang thực hiện | Theo dõi run ID |
| SUCCEEDED | Hành động và xác minh đều đạt | Dùng release/deployment ID để tra cứu |
| FAILED | Một bước thực thi thất bại | Xem log và trạng thái tài nguyên thực tế |
| CANCELLED | Đã hủy theo cách được hỗ trợ | Kiểm tra xem có tác động dở dang cần xử lý không |
| PARTIAL | Một phần thao tác đã xảy ra nhưng chưa hoàn tất | Chạy quy trình recovery hoặc tiếp tục có kiểm soát |

Đặc biệt, FAILED không luôn có nghĩa là hệ thống chưa thay đổi. Một deployment có thể cập nhật một phần tài nguyên rồi thất bại ở bước smoke test. Khi đó cần báo rõ trạng thái thực tế, không chỉ hiển thị dấu X màu đỏ.

## 14. Anti-pattern khi dùng manual trigger

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Một ô nhập lệnh tự do | Input có thể trở thành mã thực thi ngoài ý muốn | Dùng action enum và tham số có cấu trúc |
| Nhập môi trường bằng chuỗi tùy ý | Triển khai nhầm hoặc đến tài nguyên không được phép | Dùng allowlist và environment đã cấu hình |
| Dùng latest làm phiên bản phát hành | Nội dung có thể thay đổi giữa lúc kiểm tra và deploy | Dùng digest hoặc release ID bất biến |
| Chỉ kiểm tra ở giao diện | Có thể bị bỏ qua qua API hoặc lần chạy khác | Xác thực lại trong workflow và dịch vụ đích |
| Truyền token qua input | Lộ trong log, lịch sử hoặc metadata | Lấy từ secret manager hoặc workload identity |
| Coi người khởi chạy là người phê duyệt | Bỏ qua phân tách nhiệm vụ | Dùng approval gate và kiểm tra actor riêng |
| Không có dry-run cho thao tác lớn | Khó nhận ra sai phạm vi trước khi tác động | Hiển thị kế hoạch và yêu cầu xác nhận |
| Cho phép chạy đồng thời vô hạn | Ghi đè hoặc migration xung đột | Concurrency control theo môi trường |
| Retry toàn bộ workflow sau lỗi | Lặp thao tác không idempotent | Dùng idempotency key và retry theo loại lỗi |
| Không ghi lý do và audit | Không giải thích được vì sao hành động xảy ra | Ghi actor, input chuẩn hóa, policy và kết quả |

## 15. Checklist thiết kế manual trigger

Trước khi cho phép manual trigger tác động đến tài nguyên thật, hãy kiểm tra:

- [ ] Lý do cần manual trigger đã rõ và không phải công việc nên chạy tự động theo sự kiện.
- [ ] Input được định nghĩa bằng schema, kiểu dữ liệu và miền giá trị.
- [ ] Trường bắt buộc, mặc định và giới hạn độ dài được khai báo.
- [ ] Các ràng buộc giữa nhiều input được kiểm tra.
- [ ] Workflow xác thực lại input ở phía thực thi.
- [ ] Artifact được chọn bằng digest hoặc ID bất biến.
- [ ] Môi trường và tài nguyên đích nằm trong allowlist.
- [ ] Quyền khởi chạy và quyền thực thi được kiểm tra riêng.
- [ ] Phê duyệt được áp dụng khi policy yêu cầu.
- [ ] Không truyền bí mật qua input hoặc ghi vào log.
- [ ] Có dry-run/preview phù hợp với mức tác động.
- [ ] Có concurrency control, timeout và xử lý chạy lặp.
- [ ] Có xác minh trạng thái sau thao tác.
- [ ] Có audit trail gắn với actor, run ID, artifact và target.
- [ ] Trạng thái lỗi hoặc thực hiện một phần được giải thích rõ.

## 16. Bài tập tự đánh giá

Một nhóm vận hành có workflow triển khai production. Hiện tại, người dùng chỉ cần nhập tên nhánh, tên môi trường và một chuỗi lệnh tùy ý rồi nhấn nút chạy. Workflow dùng chung một token quản trị, không xác minh artifact trong registry và không ghi lại lý do phát hành. Có lần người vận hành chọn nhầm nhánh thử nghiệm và triển khai một bản chưa được kiểm thử.

Hãy thiết kế lại quy trình:

1. Trường nào nên là enum, boolean, số hoặc chuỗi có định dạng?
2. Có nên cho phép nhập tên nhánh tự do để chọn artifact production không? Vì sao?
3. Workflow cần xác minh những gì về artifact trước khi triển khai?
4. Làm thế nào phân biệt quyền khởi chạy với quyền phát hành production?
5. Bí mật nên được cấp cho job bằng cơ chế nào?
6. Có cần dry-run hoặc phê duyệt riêng không? Điều kiện nào quyết định?
7. Nếu người dùng nhấn nút hai lần, làm sao tránh triển khai trùng?
8. Những thông tin nào phải được lưu trong audit trail?
9. Nếu deploy thất bại sau khi đã cập nhật một phần tài nguyên, trạng thái nào và hướng recovery nào cần được hiển thị?

Một thiết kế tốt phải giới hạn lựa chọn, xác thực lại ở phía thực thi, gắn hành động với artifact bất biến, áp dụng đúng quyền và ghi lại kết quả. Manual trigger cần giúp con người đưa ra yêu cầu rõ ràng, còn pipeline chịu trách nhiệm thực thi yêu cầu đó một cách có kiểm soát.

## Kết luận

Manual trigger cho phép con người chủ động bắt đầu một hoạt động CI/CD cần lựa chọn về thời điểm, artifact, môi trường hoặc phạm vi. Để an toàn và dễ vận hành, đầu vào cần được định nghĩa như một hợp đồng có kiểu dữ liệu và ràng buộc rõ; pipeline phải xác thực lại ở phía thực thi, kiểm tra quyền, dùng artifact bất biến, bảo vệ bí mật và kiểm soát chạy lặp.

Một workflow tốt cho người khởi chạy biết mình đang yêu cầu điều gì, sẽ tác động đến đâu và kết quả được xác minh ra sao. Khi hành động có rủi ro cao, dry-run, phê duyệt và audit trail giúp giữ trách nhiệm rõ ràng. Nhờ vậy, thao tác thủ công trở thành một điểm điều khiển có kiểm soát trong quy trình tự động hóa.


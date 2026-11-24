# Data deletion after recovery — Xóa dữ liệu sau khôi phục tài khoản

## 1. Xóa đúng dữ liệu, đúng thời điểm

Quy trình khôi phục tài khoản có thể tạo ra nhiều dữ liệu tạm: challenge, token dùng một lần, bản chụp giấy tờ, kết quả xác minh, tác vụ thông báo và hồ sơ xử lý thủ công. Khi người dùng đã lấy lại quyền truy cập, giữ tất cả các dữ liệu đó vô thời hạn sẽ làm tăng bề mặt rò rỉ và nguy cơ lạm dụng.

**Data deletion after recovery** là quản lý việc xóa hoặc giảm thiểu dữ liệu không còn cần thiết sau một quy trình khôi phục. Phạm vi thường là dữ liệu phục vụ khôi phục, không phải tự động xóa hồ sơ, lịch sử sử dụng hoặc tài khoản của người dùng.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, việc xóa phải phối hợp với xác minh danh tính, đánh giá rủi ro, token dùng một lần, chống lạm dụng và kiểm soát phiên. Một lượt khôi phục hoàn tất khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực không được để lại các bí mật cũ còn dùng được.

Tuy nhiên, “không còn dùng được” và “đã bị xóa vật lý” là hai trạng thái khác nhau. Token phải bị vô hiệu hóa đúng lúc, ngay cả khi dữ liệu phục vụ chống phát lại hoặc audit còn cần giữ trong một thời gian có kiểm soát.

Ba câu hỏi nền tảng là:

1. Dữ liệu này thuộc lượt khôi phục nào và phục vụ mục đích gì?
2. Khi nào mục đích đó kết thúc, còn điều kiện giữ nào hợp lệ không?
3. Xóa nó có làm mất khả năng chống phát lại, xử lý sự cố hoặc bảo toàn dữ liệu khác không?

## 2. Phân biệt xóa dữ liệu khôi phục và xóa tài khoản

Đặt lại mật khẩu không đồng nghĩa với yêu cầu xóa tài khoản. Xóa ảnh giấy tờ tạm cũng không đồng nghĩa xóa mọi sự kiện audit liên quan. Cần tách các loại thao tác:

| Thao tác | Đối tượng chính | Điều kiện riêng |
| --- | --- | --- |
| Vô hiệu hóa quyền khôi phục | Token, challenge, phiên hạn chế | Quyền đã dùng, hết hạn, bị hủy hoặc bị thu hồi |
| Xóa dữ liệu tạm phục vụ khôi phục | Tệp tải lên, bản nháp, dữ liệu trung gian | Mục đích kết thúc và đạt điều kiện lưu giữ |
| Giảm thiểu hồ sơ xử lý | Chi tiết bằng chứng, thông tin liên lạc không cần giữ | Chính sách dữ liệu và nhu cầu truy vết |
| Lưu bản ghi audit tối thiểu | Ai làm gì, cho tài khoản nào, kết quả nào | Thời hạn, quyền truy cập và mục đích đã xác định |
| Xóa dữ liệu hoặc đóng tài khoản | Hồ sơ và dữ liệu nghiệp vụ | Yêu cầu và thẩm quyền riêng của vòng đời tài khoản |

Một cleanup job sau khôi phục không nên được cấp quyền xóa toàn bộ người dùng. Nó cũng không nên khôi phục dữ liệu từng bị xóa hợp lệ chỉ vì cần tái lập khả năng đăng nhập.

Đối với tài khoản bị chiếm, dữ liệu nghi vấn có thể cần được cách ly để điều tra thay vì tiếp tục xuất hiện trong giao diện bình thường. Cách ly và xóa là hai thao tác khác nhau, có mục đích, quyền truy cập và điều kiện kết thúc riêng.

## 3. Lập danh mục dữ liệu theo vòng đời

Trước khi đặt lịch xóa, cần biết dữ liệu thực sự nằm ở đâu. Một ảnh giấy tờ có thể tồn tại trong kho đối tượng, tệp tạm, ảnh thu nhỏ, kết quả OCR, công cụ quét tệp và hệ thống của nhà cung cấp xác minh. Xóa một hàng trong bảng `recovery_request` chưa chắc xóa được các bản sao đó.

Một danh mục tối thiểu có thể phân loại như sau:

| Nhóm | Ví dụ | Hướng xử lý sau khi hết mục đích |
| --- | --- | --- |
| Bí mật xác thực thô | OTP, token đầy đủ, mã dự phòng được xuất trình | Tránh lưu ngay từ đầu; loại bỏ khỏi bộ nhớ hoặc nơi tạm theo khả năng của môi trường |
| Trạng thái quyền dùng một lần | Grant ID, trạng thái tiêu thụ, thời hạn | Vô hiệu hóa trước; giữ phần cần chống phát lại rồi xóa theo policy |
| Bằng chứng danh tính | Ảnh giấy tờ, selfie, tài liệu hỗ trợ | Xóa hoặc giảm thiểu theo mục đích, thời hạn và điều kiện giữ đã xác định |
| Kết quả xác minh | Phán quyết, mức bảo đảm, tham chiếu nhà cung cấp | Có thể giữ ít hơn dữ liệu nguồn để phục vụ truy vết |
| Hồ sơ hỗ trợ | Ghi chú, hội thoại, tệp đính kèm | Lọc thông tin không cần thiết và áp dụng vòng đời riêng |
| Dữ liệu điều phối | Outbox, retry, tác vụ đang chờ | Hoàn tất hoặc hủy đúng tác vụ; giữ thông tin chống trùng trong thời gian cần thiết |
| Audit | Hành động, chủ thể, policy, kết quả | Giữ phạm vi tối thiểu, hạn chế truy cập và xóa khi hết thời hạn |
| Dữ liệu quan sát | Log, trace, bản ghi lỗi, bản sao payload | Thiết kế không mang bí mật; có lịch lưu và xóa độc lập |

Một tham chiếu hoặc hash không mặc nhiên là dữ liệu vô danh. Nếu nó vẫn có thể liên kết tới người dùng, hồ sơ hoặc một tài liệu cụ thể, cần bảo vệ theo mức phù hợp. Không thay tên người bằng account ID rồi kết luận rằng dữ liệu có thể giữ mãi.

Policy cần ghi rõ loại dữ liệu, nơi lưu, chủ thể chịu trách nhiệm, sự kiện bắt đầu tính thời hạn, cách xóa, cách kiểm chứng và cách xử lý ngoại lệ. Không nên chỉ có một tham số `deleteAfterDays` dùng cho tất cả.

## 4. Vô hiệu hóa bí mật trước khi dọn dữ liệu

Sau khi một quyền khôi phục được sử dụng thành công, hệ thống phải ngăn sử dụng lại theo contract. Không chờ đến khi job dọn dữ liệu chạy vào cuối ngày mới từ chối token cũ.

Ví dụ thứ tự hợp lý:

```text
Trong cổng thực thi khôi phục:
  kiểm tra quyền và điều kiện hiện tại
  tiêu thụ grant dùng một lần
  áp dụng đúng thay đổi xác thực
  xử lý trạng thái phiên theo policy
  ghi kết quả và sự kiện cần thiết

Sau đó theo vòng đời dữ liệu:
  xác định artifact nào đã hết mục đích
  xóa hoặc giảm thiểu theo policy
  xác nhận kết quả từng nơi lưu
```

Thao tác tiêu thụ và thay đổi xác thực phải dùng cơ chế nhất quán phù hợp. Nếu cùng cơ sở dữ liệu, có thể nằm trong một giao dịch; với nhiều hệ thống, cần thiết kế điều phối và chống lặp tương ứng. Một job xóa ở phía sau không sửa được lỗi cho phép thực thi lại ở phía trước.

### Vì sao không xóa ngay mọi dấu vết token?

Một token tự chứa có chữ ký vẫn có thể còn hợp lệ về mặt mật mã cho tới khi hết hạn. Nếu hệ thống dựa vào bản ghi đã tiêu thụ để từ chối phát lại, xóa bản ghi đó quá sớm có thể làm token được chấp nhận lại.

Tương tự, nếu thiếu hàng trong bảng grant được diễn giải thành “chưa dùng”, việc xóa hàng đã dùng là nguy hiểm. Thiết kế nên mặc định từ chối khi không có trạng thái ủy quyền cần thiết, đồng thời duy trì thông tin thu hồi hoặc tiêu thụ mà kiến trúc thật sự cần.

Thời điểm dọn bản ghi chống phát lại cần tính đến toàn bộ cửa sổ token còn có thể được chấp nhận, sai lệch thời gian được hệ thống cho phép, cache và các đường xác minh liên quan. Không dùng một thời hạn audit tùy ý để quyết định hiệu lực bảo mật của token.

Có thể giữ grant ID không mang quyền, trạng thái đã tiêu thụ và thời hạn thay vì giữ token thô. Bản ghi tối thiểu này vẫn phải được kiểm soát truy cập và có vòng đời rõ ràng.

## 5. Xác định sự kiện bắt đầu và điều kiện được xóa

Không phải dữ liệu nào cũng bắt đầu tính hạn từ `created_at`. Một hồ sơ chờ xác minh lâu, một hồ sơ bị từ chối và một lượt khôi phục thành công có thể có các mốc khác nhau.

Các trạng thái kết thúc có thể gồm:

- Khôi phục hoàn tất.
- Người dùng hủy yêu cầu.
- Yêu cầu hết hạn.
- Yêu cầu bị từ chối.
- Yêu cầu bị thu hồi vì dấu hiệu lạm dụng.

Một trạng thái kết thúc không luôn có nghĩa mọi artifact lập tức được xóa. Có thể còn tác vụ hậu xử lý hợp lệ, kiểm tra sự cố hoặc điều kiện giữ được xác lập. Tuy nhiên, không nên giữ toàn bộ dữ liệu mặc định chỉ vì “có thể cần sau này”.

Ví dụ một policy được mô tả bằng điều kiện thay vì con số chung:

```text
Tệp xác minh thô:
  xét xóa sau khi hồ sơ kết thúc và đạt thời hạn đã phê duyệt
  không xóa nếu đang thuộc một điều kiện giữ hợp lệ, đúng phạm vi
  không giữ token hoặc mật khẩu trong tệp vì mục đích audit

Bản ghi chống phát lại:
  giữ đến khi mọi đường chấp nhận quyền cũ đã đóng theo kiến trúc

Audit tối thiểu:
  giữ theo mục đích và thời hạn audit riêng
```

Các thời hạn cụ thể phải đến từ chính sách đã được áp dụng cho sản phẩm và loại dữ liệu. Không mặc định rằng mọi dịch vụ đều cần giữ giấy tờ một số ngày giống nhau hoặc rằng xóa càng sớm càng an toàn trong mọi trường hợp.

Nếu có điều kiện giữ phục vụ điều tra hoặc nghĩa vụ đã được xác định, ghi rõ phạm vi, người có thẩm quyền, lý do, thời điểm xem xét lại và cách kết thúc. Không dùng một cờ giữ vô hạn do bất kỳ nhân viên nào cũng có thể bật. Giữ bằng chứng theo một mục đích hợp lệ không làm token đã dùng được phép hoạt động trở lại.

## 6. Giới hạn cleanup theo request và artifact

Một tài khoản có thể có nhiều lượt khôi phục qua thời gian. Job dọn lượt cũ không được xóa yếu tố xác thực mới, hồ sơ mới hoặc tệp của lượt đang hoạt động.

Một lỗi thiết kế là:

```text
Xóa mọi dữ liệu có account_id = A17
vì recovery request R1 đã hoàn tất.
```

R1 có thể đã kết thúc, nhưng A17 vừa tạo R2. Cùng một account ID không chứng minh mọi dữ liệu đều thuộc R1.

Thay vào đó, tạo danh sách đích rõ ràng:

```text
CleanupPlan
  plan_id
  recovery_request_id
  request_lifecycle_version
  policy_version
  artifact_ids
  eligible_after
  state

RecoveryArtifact
  artifact_id
  recovery_request_id
  storage_reference
  storage_generation_or_version
  artifact_type
  retention_state
  deletion_state
```

Manifest cần được sinh từ dữ liệu nguồn đáng tin cậy. Không nhận đường dẫn tệp tùy ý từ client rồi xóa theo đường dẫn đó. Không dùng một prefix rộng trùng với thư mục hồ sơ, avatar hoặc dữ liệu xác thực hiện hành.

Nếu nhiều bản ghi tham chiếu chung một đối tượng vật lý, xóa một tham chiếu không tự cho phép xóa đối tượng. Cần quản lý quyền sở hữu, các tham chiếu còn hiệu lực và trạng thái thu gom phù hợp. Trong lúc đối tượng đã chuyển sang chờ xóa, không được tạo tham chiếu mới làm thay đổi giả định mà job vẫn tiếp tục dùng.

Đối với kho đối tượng có version, một delete marker có thể chỉ ẩn phiên bản hiện hành. Policy xóa cần tính đến các phiên bản và bản sao thực sự thuộc artifact, với định danh chính xác và quyền phù hợp. Không xóa toàn bucket hay toàn lịch sử của một người dùng để xử lý một tệp xác minh.

## 7. Điều phối xóa và xử lý thay đổi cạnh tranh

Quyết định đủ điều kiện xóa có thể thay đổi giữa lúc job lấy danh sách và lúc thực thi. Một điều kiện giữ có thể được thêm, policy có thể đổi hoặc artifact có thể vẫn được một tác vụ hợp lệ sử dụng.

Do đó, danh sách tìm được lúc quét chỉ là ứng viên. Trước khi chấp nhận lệnh xóa, cần kiểm tra lại trạng thái hiện tại và chuyển artifact sang trạng thái xóa theo cơ chế nhất quán.

```text
1. Lấy ứng viên đã đến hạn từ chỉ mục.
2. Nạp trạng thái request, artifact và các điều kiện giữ hiện tại.
3. Kiểm tra đúng request, phiên bản vòng đời, mục đích và phạm vi.
4. Chốt quyền xóa bằng giao dịch hoặc kiểm tra phiên bản phù hợp.
5. Ghi kế hoạch tác động ra nơi lưu bên ngoài bằng cơ chế giao bền vững.
6. Thực hiện từng đích; ghi nhận phản hồi và đối soát theo contract.
7. Hoàn tất artifact khi các đích bắt buộc đã đạt trạng thái quy định.
```

Các đường tạo điều kiện giữ, mở lại hồ sơ nếu được phép, thay đổi tham chiếu và lập lệnh xóa phải phối hợp cùng cơ chế. Khóa một hàng artifact không giúp ích nếu đường tạo điều kiện giữ hoàn toàn bỏ qua khóa hoặc phiên bản đó.

Policy cần quy định điểm mà quyết định xóa đã được chấp nhận và cách xử lý một yêu cầu giữ đến quá muộn. Không hứa rằng thêm cờ giữ sau khi đối tượng đã bị xóa sẽ phục hồi được dữ liệu. Những xung đột như vậy cần được ghi nhận và xử lý rõ ràng.

Đối với kho đối tượng hoặc nhà cung cấp bên ngoài, giao dịch cơ sở dữ liệu cục bộ không khóa được thao tác xóa vật lý ở hệ thống đó. Cần có contract cho trạng thái đã lên lịch, đã gửi lệnh, được nhà cung cấp chấp nhận và đã xác nhận kết quả. Một cờ `deleted=true` trong cơ sở dữ liệu không thay thế các bước này.

### Chạy lại phải an toàn

Job có thể dừng sau khi xóa đối tượng nhưng trước khi cập nhật bản ghi kết quả. Lần chạy lại cần dùng cùng artifact ID, thế hệ đối tượng và khóa tác vụ; không mở rộng thành xóa toàn thư mục để xử lý tình trạng không chắc chắn.

Phản hồi “không tìm thấy” có thể được coi là đích đã không còn tồn tại nếu định danh và phạm vi đúng, đồng thời contract của nơi lưu cho phép kết luận đó. Không diễn giải lỗi quyền truy cập hoặc timeout thành đã xóa.

Khi một đích lỗi, lưu trạng thái từng phần, retry có giới hạn và chuyển xử lý khi cần. Không xóa ngay mọi metadata liên hệ khiến hệ thống không còn biết phải dọn bản sao nào. Sau khi hoàn tất, giảm thiểu metadata đó theo policy thay vì giữ nguyên vô thời hạn.

## 8. Ví dụ Java: kiểm tra ứng viên trước bước chốt quyền xóa

Đoạn mã sau minh họa một phần cổng kiểm tra. Nó không thực hiện xóa và không thay thế giao dịch chốt quyền xóa. Các bản ghi được lấy từ nguồn phía máy chủ; không tin một đối tượng ứng viên do client gửi.

```java
import java.time.Instant;
import java.util.UUID;

enum RetentionState {
    REQUIRED_FOR_ACTIVE_PROCESS,
    REQUIRED_FOR_REPLAY_PROTECTION,
    ON_HOLD,
    ELIGIBLE_FOR_DELETION
}

record ClosedRecovery(
        UUID requestId,
        long lifecycleVersion,
        Instant terminalAt) {
}

record CleanupCandidate(
        UUID artifactId,
        UUID requestId,
        long requestLifecycleVersion,
        RetentionState retentionState,
        Instant eligibleAfter) {
}

final class CleanupEligibility {
    static boolean mayConsider(
            ClosedRecovery recovery,
            CleanupCandidate artifact,
            Instant trustedNow) {

        if (recovery == null || artifact == null || trustedNow == null
                || recovery.requestId() == null
                || recovery.terminalAt() == null
                || artifact.artifactId() == null
                || artifact.requestId() == null
                || artifact.eligibleAfter() == null) {
            return false;
        }

        return recovery.requestId().equals(artifact.requestId())
                && recovery.lifecycleVersion()
                    == artifact.requestLifecycleVersion()
                && !recovery.terminalAt().isAfter(trustedNow)
                && artifact.retentionState()
                    == RetentionState.ELIGIBLE_FOR_DELETION
                && !artifact.eligibleAfter().isAfter(trustedNow);
    }
}
```

`trustedNow` là thời gian phía máy chủ. `eligibleAfter` và `retentionState` phải được tính từ policy cùng trạng thái thật, không từ thời hạn do người yêu cầu tự chọn. Request ID và phiên bản giúp loại một kế hoạch cũ không còn khớp vòng đời đang xét.

Kết quả `true` chỉ cho phép xem xét bước tiếp theo. Trước khi phát lệnh xóa, hệ thống vẫn cần kiểm tra quyền, phiên bản policy, điều kiện giữ hiện tại, tham chiếu còn sống, định danh nơi lưu, trạng thái tác vụ và phạm vi tenant. Việc chốt phải ngăn thay đổi cạnh tranh phá vỡ những giả định đó theo contract của kiến trúc.

Không thể chứng minh chống phát lại đã hết nhu cầu chỉ bằng đoạn mã này. Việc đặt trạng thái `ELIGIBLE_FOR_DELETION` cho bản ghi bảo mật phải đến từ phân tích cửa sổ hiệu lực của quyền và các đường xác minh thực tế.

## 9. Các bản sao dễ bị bỏ sót

Một kế hoạch xóa cần bao phủ các nơi thực sự đã nhận dữ liệu, trong phạm vi kiến trúc và policy:

- Bản gốc và các phiên bản thuộc artifact trong kho đối tượng.
- Ảnh thu nhỏ, bản chuyển định dạng và dữ liệu OCR.
- Tệp tạm do xử lý ảnh, quét tệp hoặc tải xuống phục vụ xác minh.
- Chỉ mục tìm kiếm và cache nếu có lưu nội dung hoặc tham chiếu nhạy cảm.
- Tệp đính kèm trong công cụ hỗ trợ được phép sử dụng.
- Bản sao ở nhà cung cấp xác minh và các hệ thống phụ trợ theo contract.
- Queue, dead-letter queue hoặc bản ghi lỗi nếu thiết kế đã đưa payload vào đó.

Thiết kế tốt nên hạn chế việc sao chép ngay từ đầu. Sự kiện điều phối chỉ cần artifact ID và tham chiếu an toàn, không nên chứa toàn bộ ảnh giấy tờ hoặc token. Khi có nhiều bản sao, mỗi nơi có thể có thời hạn, cách xóa và cách xác nhận khác nhau.

Hết hạn URL ký không có nghĩa đối tượng đã bị xóa. Nó chỉ làm một khả năng truy cập theo URL đó hết hạn theo cơ chế tương ứng. Ngược lại, xóa đối tượng cũng không bảo đảm mọi bản sao từng được tải xuống đã biến mất.

Nếu dữ liệu đã đi qua cache hoặc hệ thống phân phối nội dung, cần tính đến khả năng lưu bản sao và cơ chế vô hiệu hóa được hỗ trợ. Không công khai tài liệu định danh chỉ để dễ hiển thị rồi trông chờ cleanup thu hồi mọi bản sao.

Không thể hứa thu hồi tuyệt đối dữ liệu đã bị chuyển tiếp hoặc sao chép ngoài sự kiểm soát của hệ thống. Việc giới hạn người được xem, ngăn tải không cần thiết và chọn kênh có kiểm soát giúp giảm rủi ro trước khi đến bước xóa.

## 10. Backup, lưu trữ bất biến và xóa bằng khóa

Backup có vòng đời riêng. Một bản sao bất biến có thể không hỗ trợ xóa chọn lọc ngay một artifact. Khi đó phải mô tả đúng: dữ liệu đã xóa khỏi nơi phục vụ chính, còn bản sao dự phòng được bảo vệ và sẽ hết vòng đời theo policy đã xác định. Không báo “đã xóa mọi bản sao” khi chưa có cơ sở.

Quy trình khôi phục backup cần biết các quyết định xóa đã có hiệu lực. Nếu phục hồi một snapshot cũ, phải áp dụng lại những quyết định liên quan trước khi dữ liệu được phục vụ hoặc đưa trở lại các luồng xử lý. Nếu không, một lần phục hồi sự cố có thể làm sống lại giấy tờ đã hết mục đích lưu giữ hoặc trạng thái grant đã bị thu hồi.

Bản ghi phục vụ việc áp dụng lại quyết định xóa cũng cần được tối thiểu hóa và có quyền truy cập phù hợp. Không giữ một bản sao nguyên dữ liệu đã xóa chỉ để nhớ rằng nó đã bị xóa.

Đối với lưu trữ có khóa chống xóa hoặc ràng buộc giữ, job phải nhận biết trạng thái bị chặn và báo đúng nguyên nhân. Không retry vô hạn, không sửa rộng quyền lưu trữ và không tắt cơ chế giữ ngoài thẩm quyền chỉ để có một báo cáo xanh.

### Khi nào xóa khóa có ý nghĩa?

Xóa khóa có thể làm dữ liệu mã hóa không còn giải mã được nếu mô hình quản lý khóa được thiết kế tương ứng. Điều kiện quan trọng gồm phạm vi khóa phù hợp, không còn bản sao khóa hoặc đường mở khóa hợp lệ khác, và không còn bản rõ ở các nơi ngoài phạm vi đó.

Không được xóa khóa dùng chung cho hồ sơ chính hoặc nhiều tài khoản chỉ để dọn một ảnh xác minh. Nếu dữ liệu khôi phục và dữ liệu nghiệp vụ dùng chung khóa, thao tác đó có thể làm mất khả năng đọc dữ liệu người dùng cần giữ.

Việc đặt lịch xóa khóa chưa đồng nghĩa khóa đã bị hủy, và xóa một bản bọc khóa chưa chắc loại mọi bản sao. Cần kiểm chứng theo khả năng thực tế của hệ thống quản lý khóa và bản sao dự phòng. Không dùng nhãn “crypto erase” để bỏ qua việc lập danh mục dữ liệu.

## 11. Audit, quyền vận hành và báo cáo kết quả

Một cleanup job cần quyền đủ để xóa đúng loại artifact, không cần quyền đọc mọi hồ sơ hay xóa mọi dữ liệu của tenant. Tách quyền lập policy, tạo điều kiện giữ và thực thi xóa theo mức rủi ro phù hợp.

Nhật ký xóa có thể gồm:

```text
cleanup_plan_id, artifact_reference, recovery_request_reference
policy_version, eligibility_reason
authorized_at, attempted_at, completed_at
storage_target_class, operation_reference
outcome, retry_state, failure_category
hold_reference_if_blocked
```

Không cần ghi nguyên token, nội dung giấy tờ hoặc đường dẫn chứa dữ liệu cá nhân vào log phổ thông. Tham chiếu cần đủ để đối soát nhưng không tự cấp quyền đọc artifact. Audit cũng phải có vòng đời riêng, không trở thành cách giữ lại toàn bộ dữ liệu đã chủ trương xóa.

Nên phân biệt các kết quả như:

| Kết quả | Ý nghĩa |
| --- | --- |
| Chưa đến hạn | Chưa đạt điều kiện thời gian hoặc vòng đời |
| Đang được giữ | Có điều kiện giữ hợp lệ, đúng phạm vi |
| Đã chấp nhận kế hoạch | Quyền xóa đã được chốt, chưa chắc mọi đích đã xong |
| Hoàn tất một phần | Một số đích đã xóa, một số còn chờ hoặc lỗi |
| Hoàn tất theo phạm vi | Các đích bắt buộc của kế hoạch đã đạt điều kiện xác nhận |
| Chờ hết vòng đời backup | Bản phục vụ chính đã xử lý, backup còn trong hạn đã quy định |
| Thất bại cần xử lý | Không thể tiếp tục an toàn bằng retry thông thường |

Theo dõi số artifact quá hạn chưa xóa, tuổi tác vụ lâu nhất, lỗi theo nơi lưu, bản sao chưa đối soát và điều kiện giữ không được xem xét lại. Số request đã đóng không cho biết dữ liệu tạm đã được dọn tới đâu.

Thông báo hoặc trả lời người dùng cần phản ánh đúng phạm vi. Có thể nói dữ liệu tạm nào đã được xử lý và phần nào còn chịu vòng đời đã định, nếu policy cho phép cung cấp thông tin đó. Không tuyên bố xóa toàn bộ audit hoặc backup khi hệ thống chỉ vừa xóa tệp trên kho chính.

## 12. Tình huống xuyên suốt

Mai mất thiết bị MFA và hoàn tất quy trình khôi phục thủ công R1. Hồ sơ xác minh gồm một tệp tải lên, kết quả kiểm tra và các quyết định đã được cho phép. Tài khoản chính, avatar và dữ liệu học tập không thuộc phạm vi cleanup của R1.

Tại thời điểm thực thi, quyền khôi phục được tiêu thụ một lần, yếu tố bị mất được xử lý và phiên cũ được kiểm soát theo policy. Trạng thái tiêu thụ có hiệu lực ngay; hệ thống không đợi job xóa tệp mới chặn token R1.

Sau khi đạt điều kiện lưu giữ, hệ thống lập manifest chỉ gồm artifact của R1. Tệp nguồn và bản OCR được xử lý theo chính sách của chúng; audit tối thiểu cùng bản ghi chống phát lại có vòng đời riêng. Nhân viên không tải ảnh về máy cá nhân để “giữ phòng khi cần” trước khi xóa.

Trong lúc job chạy, Mai tạo một yêu cầu R2. Job R1 không xóa theo account ID chung, nên tệp mới của R2 và yếu tố xác thực hiện hành không bị ảnh hưởng. Nếu xuất hiện điều kiện giữ hợp lệ trước khi quyền xóa R1 được chốt, artifact tương ứng được giữ theo quy trình và ghi nhận lý do.

Một kho đối tượng đã xóa thành công nhưng phản hồi bị timeout. Job tra cứu hoặc chạy lại theo cùng định danh đối tượng và thế hệ; nó không mở rộng phạm vi. Khi nhà cung cấp xác minh chưa xác nhận xử lý bản sao, kế hoạch được ghi hoàn tất một phần thay vì được đánh dấu xong toàn bộ.

Backup còn bản sao trong vòng đời đã quy định. Hệ thống giữ kiểm soát truy cập và quyết định xóa cần thiết để không đưa dữ liệu đó trở lại phục vụ nếu có lần phục hồi backup. Báo cáo thể hiện riêng phần đã hoàn tất và phần còn chờ hết vòng đời.

Xóa dữ liệu sau khôi phục là một phần của thiết kế bảo mật, không chỉ là câu lệnh dọn bảng. Cơ chế đúng phải loại dữ liệu không còn mục đích mà vẫn giữ hiệu lực chống phát lại, không xóa nhầm dữ liệu hiện hành và không đưa ra bảo đảm vượt quá khả năng kiểm chứng của hệ thống.

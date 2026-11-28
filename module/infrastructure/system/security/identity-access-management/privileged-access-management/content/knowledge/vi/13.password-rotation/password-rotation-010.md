# Rollback sau rotation thất bại

**Rollback sau rotation thất bại** là quá trình đưa những phần đã thay đổi về một trạng thái trước đó được xác định là còn an toàn và có thể vận hành. Trong Privileged Access Management (PAM), việc này có thể liên quan tới mật khẩu tại hệ thống đích, phiên bản hiện hành trong vault và cấu hình của những ứng dụng đang sử dụng credential.

Bài học thuộc chương **Password rotation**, trong phạm vi quản lý tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Nội dung kết hợp kiểm kê quyền, least privilege, JIT/JEA, vault, luân chuyển credential, giám sát phiên và bằng chứng phục vụ kiểm toán, ứng phó sự cố.

Một rotation thất bại không có nghĩa mọi thành phần vẫn giữ trạng thái cũ. Máy đích có thể đã đổi mật khẩu, vault chưa cập nhật bản hiện hành, còn ứng dụng vẫn giữ secret trước đó. Vì vậy, trước khi hoàn tác phải xác định điều gì đã thực sự xảy ra và lựa chọn cách phục hồi phù hợp.

Sau bài học, bạn có thể:

- Phân biệt rollback, đối soát trạng thái và phục hồi bằng một credential mới.
- Xây dựng ma trận trạng thái giữa đích, vault và bên sử dụng.
- Xác định điều kiện cho phép hoặc ngăn việc khôi phục credential cũ.
- Thiết kế xử lý lỗi từng phần, kết quả chưa chắc chắn và worker chạy lại.
- Đặt tiêu chí xác minh, bằng chứng và điều kiện kết thúc sự cố.

## 1. Vì sao không thể chỉ “đổi lại mật khẩu cũ”?

Một workflow rotation có thể gồm:

```text
Tạo candidate và bảo vệ dữ liệu cần phục hồi
  → Thay credential tại đích
  → Xác minh kết quả
  → Cập nhật phiên bản hiện hành trong vault
  → Cập nhật bên sử dụng
  → Xử lý credential cũ và công việc còn lại
```

Các bước này thường không thuộc cùng một giao dịch nguyên tử. Đích có thể không hỗ trợ giao dịch chung với vault; ứng dụng có thể nhận secret bất đồng bộ và giữ cache trong bộ nhớ.

Nếu bước cập nhật ứng dụng lỗi, mật khẩu mới ở đích vẫn có thể đúng. Đổi con trỏ vault về phiên bản cũ trong tình huống đó chỉ khiến vault tiếp tục cấp một credential không khớp. Ngược lại, khôi phục mật khẩu tại đích nhưng bỏ quên các ứng dụng đã nhận bản mới cũng tạo lỗi.

Một số nền tảng còn có lịch sử mật khẩu, điều kiện thay đổi hoặc cơ chế thu hồi không cho khôi phục giá trị cũ theo cách mong muốn. Credential cũ cũng có thể đã bị lộ, chính là lý do phải rotation khẩn cấp.

Rollback cần được hiểu là một workflow có điều kiện và bằng chứng, không phải một nút có thể đảo ngược mọi tác động.

## 2. Phân biệt ba hướng xử lý

| Hướng xử lý | Mục tiêu | Ví dụ |
|---|---|---|
| Reconciliation — đối soát | Xác định và đồng bộ trạng thái thực tế | Chứng minh đích đã chấp nhận bản mới sau khi phản hồi bị mất |
| Rollback — hoàn tác | Khôi phục một trạng thái trước đó còn được phép | Khôi phục cấu hình consumer và credential cũ khi mọi điều kiện an toàn đáp ứng |
| Forward recovery — phục hồi theo hướng tiến | Đi tới một trạng thái mới nhất quán, có thể dùng credential mới | Hoàn tất áp dụng bản mới, hoặc tạo một bản kế tiếp qua đường sửa chữa được kiểm soát |

Đối soát thường cần thực hiện trước khi chọn hai hướng còn lại. Nếu chưa biết đích đã đổi hay chưa, tự động gửi thêm lệnh thay mật khẩu có thể làm tình trạng khó xác định hơn.

Phục hồi theo hướng tiến có thể là lựa chọn phù hợp khi giá trị cũ không còn an toàn hoặc không thể đặt lại. Nó không tự động đồng nghĩa giảm gián đoạn: vẫn cần quyền thực thi, cập nhật bên dùng và kiểm chứng.

Một hệ thống cũng có thể tạm dùng một đường truy cập khẩn cấp được thiết kế trước để sửa chữa. Đường đó không nên bị ghi là rotation đã thành công nếu trạng thái chính vẫn chưa được xử lý.

## 3. Mô hình trạng thái cần giữ

### 3.1 Ba vị trí chính

- **Đích:** tài khoản hoặc dịch vụ xác thực đang chấp nhận credential nào theo điều kiện thực tế.
- **Vault:** những phiên bản nào đang được bảo vệ, bản nào là candidate, bản nào được cấp sử dụng.
- **Consumer:** proxy, ứng dụng, agent hoặc tác vụ đang giữ và dùng phiên bản nào.

Cần theo dõi thêm trạng thái quyền, phiên và credential cũ có còn được chấp nhận không. Không phải mọi đích đều chỉ có một credential hiệu lực.

### 3.2 “Phiên bản ở đích” là mô hình logic

Máy đích thường không cho đọc lại password để so sánh. Ký hiệu `v7` hoặc `v8` ở đích trong bài là cách mô tả phiên bản mà workflow có bằng chứng phù hợp rằng đích chấp nhận, không phải một yêu cầu truy xuất plaintext từ đích.

Bằng chứng có thể đến từ phản hồi thay đổi, xác thực có kiểm soát, metadata phiên bản hoặc cơ chế khác mà nền tảng hỗ trợ. Mỗi cách có phạm vi và độ mới riêng.

### Ma trận trạng thái minh họa

| Đích | Vault cấp sử dụng | Consumer | Ý nghĩa và hướng điều tra |
|---|---|---|---|
| `v7` | `v7`, có candidate `v8` | `v7` | Chưa có bằng chứng áp dụng bản mới; có thể dừng candidate nếu xác nhận không còn tác vụ sẽ thực hiện |
| `v8` | `v7`, có candidate `v8` | `v7` | Đích đã thay nhưng nguồn cấp chưa chuyển; cân nhắc hoàn tất bản mới |
| `v8` | `v8` | Một phần `v7`, một phần `v8` | Lỗi chuyển đổi consumer; cần kiểm soát triển khai và cache |
| Chưa xác định | Có `v7` và candidate `v8` | `v7` | Kết quả chưa chắc chắn; đối soát trước hành động tiếp |
| `v7` sau hoàn tác | `v8` | `v8` | Hoàn tác đích chưa đồng bộ các bên, dịch vụ có thể tiếp tục lỗi |
| Có thể chấp nhận nhiều credential | Bản được chỉ định | Các bản khác nhau | Phải biết credential nào còn hiệu lực, quyền tương ứng và thời hạn chấm dứt |

Không dùng ma trận này để suy ra mọi nền tảng hỗ trợ nhiều mật khẩu hoặc khôi phục bản cũ. Nó giúp nêu câu hỏi đúng trước khi chọn hành động.

## 4. Chuẩn bị khả năng phục hồi trước rotation

### 4.1 Kiểm kê phạm vi tác động

Ghi nhận tài nguyên, tài khoản, chủ sở hữu, quyền thực tế, mọi consumer đã biết và nguồn có thẩm quyền thay credential. Bao gồm cả tác vụ ít chạy, service account dùng chung và cấu hình trong môi trường dự phòng.

Nếu một tài khoản dùng cho nhiều ứng dụng, rollback có thể ảnh hưởng tất cả ứng dụng đó. Không chỉ kiểm tra consumer đầu tiên trả lỗi.

### 4.2 Lưu trạng thái và dữ liệu cần thiết bằng cơ chế được bảo vệ

Workflow cần có mã công việc, phiên bản trước, candidate, trạng thái bước, danh tính worker, kết quả quan sát và tham chiếu thay đổi cấu hình. Candidate phải được bảo vệ đủ sớm để có khả năng phục hồi nếu đích đã thay thành công rồi worker lỗi.

Giữ phiên bản trước theo chính sách không có nghĩa cấp quyền đọc cho mọi người xử lý sự cố. Bản cũ vẫn là secret và có thể còn giá trị ở những nơi khác hoặc trên một bản backup được phục hồi.

Không ghi password hoặc hash password vào log để hỗ trợ rollback. Dùng tham chiếu phiên bản do hệ thống quản lý và lưu giá trị qua cơ chế bảo vệ secret phù hợp.

### 4.3 Xác định khả năng của đích

Cần biết:

- Chỉ một hay nhiều credential có thể cùng hoạt động?
- Việc đặt lại giá trị cũ có được hỗ trợ và đáp ứng chính sách không?
- Độ trễ áp dụng hoặc replication ảnh hưởng xác thực thế nào?
- Có danh tính sửa chữa hoặc đường khẩn cấp được phép không?
- Thay credential có chấm dứt phiên hay chỉ ảnh hưởng xác thực mới?
- Có thể giới hạn tác động của validation và retry ra sao?

Nếu dùng hai tài khoản thay phiên thay vì hai credential của cùng tài khoản, cần xem chúng là hai danh tính khác nhau. Quyền, ownership dữ liệu và audit không tự tương đương chỉ vì tên role giống nhau.

### 4.4 Đặt tiêu chí dừng và hoàn tất

Chốt trước khi nào dừng mở rộng thay đổi: xác thực thất bại, sức khỏe dịch vụ không đạt, thiếu bằng chứng hoặc mất thẩm quyền worker. Xác định ai chọn hướng phục hồi, giới hạn thời gian và cách xử lý nếu phương án đầu tiên không đạt.

Tiêu chí cần dựa trên chức năng thực tế và quyền truy cập, không chỉ tiến trình còn chạy hay API điều khiển trả mã thành công.

## 5. Phản ứng đầu tiên khi rotation thất bại

Một quy trình tham chiếu:

1. **Giới hạn thay đổi tiếp:** dừng mở rộng batch, retry không kiểm soát và công việc mới có thể tác động cùng tài khoản.
2. **Giữ quyền xử lý rõ ràng:** xác định worker hoặc người có thẩm quyền tiếp tục, ngăn tác vụ cũ chạy muộn.
3. **Bảo toàn dữ liệu:** giữ candidate, phiên bản liên quan, trạng thái công việc và bằng chứng; không xóa dữ liệu chỉ để đưa job về trạng thái ban đầu.
4. **Thu thập quan sát:** đối chiếu phản hồi đích, vault, consumer và log theo quyền được phép.
5. **Phân loại:** lỗi trước áp dụng, sau áp dụng, chuyển đổi consumer hay kết quả chưa chắc chắn.
6. **Chọn phương án:** đối soát, hoàn tác có điều kiện hoặc phục hồi theo hướng tiến.
7. **Xác minh và đóng việc:** kiểm tra toàn luồng, xử lý quyền tạm, credential dư và ghi kết quả cuối.

Dừng scheduler không có nghĩa mọi request đã gửi đều dừng. Một lệnh đang thực thi ở đích hoặc một worker bị treo có thể tiếp tục. Cơ chế điều phối phải xét cả tác vụ đang chạy và yêu cầu đến muộn.

Không tự giảm kiểm soát bằng cách tắt xác minh đích, mở quyền toàn hệ thống hoặc đưa secret vào ticket để nhiều người thử thủ công.

## 6. Khi nào có thể rollback credential cũ?

Cần đồng thời xem xét các điều kiện sau:

- Có căn cứ rằng giá trị cũ vẫn được phép sử dụng; không bị coi là đã lộ hoặc phải thu hồi vì sự cố.
- Đích hỗ trợ khôi phục theo cơ chế và chính sách hiện hành.
- Có danh tính đủ quyền thực hiện nhưng phạm vi được kiểm soát.
- Có thể đồng bộ vault và các consumer đã thay đổi.
- Không có worker khác sẽ ghi đè sau khi hoàn tác.
- Có cách xác minh kết quả và xử lý việc còn tồn đọng.

Nếu thiếu điều kiện, không cố gọi hành động là rollback thành công. Cần chọn một hướng phục hồi khác hoặc chuyển người có trách nhiệm xử lý.

### Những trường hợp nên ngăn tự động khôi phục giá trị cũ

| Điều kiện | Vấn đề |
|---|---|
| Rotation do nghi ngờ lộ credential cũ | Khôi phục giá trị đó có thể khôi phục khả năng truy cập của kẻ tấn công |
| Chưa biết đích đã đổi chưa | Hành động mới có thể che mất trạng thái cần đối soát |
| Chính sách đích không chấp nhận bản cũ | Lặp lại không giải quyết được và có thể tạo thêm lỗi |
| Consumer không được kiểm kê đầy đủ | Có nguy cơ khôi phục một bên và làm hỏng các bên khác |
| Mất quorum hoặc có nhiều writer | Không có nguồn trạng thái có thẩm quyền để thực thi nhất quán |
| Danh tính đích không được xác minh | Có thể gửi credential tới sai tài nguyên |
| Máy đích đang bị xâm nhập | Credential phục hồi hoặc mới có thể tiếp tục bị lấy hoặc lạm dụng |

Ngăn rollback tự động không đồng nghĩa bỏ mặc dịch vụ. Nó là điểm chuyển sang reconciliation, phục hồi bằng bản mới hoặc quy trình ứng phó phù hợp.

## 7. Hoàn tác theo từng giai đoạn

### 7.1 Chưa gửi thay đổi tới đích

Nếu xác nhận chưa có yêu cầu nào có thể tiếp tục áp dụng, có thể hủy candidate và các thay đổi chuẩn bị theo chính sách. Giữ audit về lý do dừng và trạng thái cuối.

Nếu request đã được gửi nhưng chưa nhận phản hồi, không xếp vào trường hợp này chỉ vì phía client báo timeout.

### 7.2 Đích đã đổi, vault chưa chuyển bản hiện hành

Trước hết bảo vệ candidate và xác minh trạng thái đích. Nếu bản mới được chấp nhận và vẫn an toàn, hoàn tất cập nhật vault cùng consumer có thể phù hợp hơn việc thay lại đích.

Nếu quyết định rollback, cần áp dụng bản cũ tại đích bằng cơ chế được phép, xác minh rồi đồng bộ nguồn cấp và consumer theo kế hoạch. Không chỉ đổi con trỏ vault.

Thứ tự chi tiết phải dựa trên số credential có thể cùng hoạt động, khả năng khóa cấp sử dụng và tác động gián đoạn. Không có một thứ tự cố định bảo đảm không gián đoạn cho mọi nền tảng.

### 7.3 Vault và đích đã chuyển, consumer lỗi một phần

Dừng các thay đổi triển khai có thể tiếp tục phát phiên bản không mong muốn. Kiểm tra consumer nào giữ bản cũ, consumer nào nhận bản mới và consumer nào chỉ còn kết nối cũ đang hoạt động.

Có thể sửa đường delivery, reload hoặc triển khai lại consumer để dùng bản mới. Nếu quay về bản cũ, phải phối hợp cả credential đích và tất cả consumer trong phạm vi, bao gồm lịch sử cấu hình và cache.

Khôi phục một bản ứng dụng không mặc nhiên khôi phục mật khẩu. Bản ứng dụng cũ có thể vẫn lấy secret hiện hành từ vault hoặc mang cấu hình lạc hậu, tùy thiết kế.

### 7.4 Đích đã thu hồi bản cũ

Không giả định có thể bật lại giá trị cũ. Có thể cần một credential kế tiếp, một danh tính thay thế hoặc đường sửa chữa được hỗ trợ.

Nếu dùng một credential khác, kiểm tra quyền tối thiểu, phạm vi tài nguyên và audit. Một tài khoản khẩn cấp toàn quyền không nên trở thành tài khoản dịch vụ thường ngày sau khi sự cố kết thúc.

### 7.5 Không còn candidate đã áp dụng

Nếu dữ liệu cần thiết bị mất sau khi đích đổi, không cố suy ra password từ log hoặc dump nhạy cảm. Chuyển sang quy trình phục hồi bằng cơ chế quản trị được ủy quyền, đặt credential mới và cập nhật lại các bên theo chính sách.

Sự cố này cho thấy cần sửa khả năng bảo vệ candidate và trạng thái công việc trước những lần rotation tiếp theo.

## 8. Kết quả chưa chắc chắn và retry an toàn

### 8.1 Timeout không phải bằng chứng chưa thay đổi

Một request có thể được đích thực hiện thành công rồi phản hồi mới bị mất. Nếu worker tạo một password khác mỗi lần timeout, đích và vault có thể liên tục đi qua những phiên bản mà không bên nào biết chắc bản hiện hành.

Cần giữ mã công việc, trạng thái đã gửi và những phiên bản liên quan. Xác minh có giới hạn hoặc đọc metadata có thẩm quyền theo khả năng đích trước khi thực hiện thêm thay đổi.

### 8.2 Thao tác bù không mặc nhiên idempotent

Gửi lại cùng một lệnh đặt mật khẩu có thể bị lịch sử hoặc điều kiện đích từ chối. Gửi một mật khẩu khác lại tạo thêm tác động. “Thử lại” phải là quyết định ở mức workflow, không chỉ lặp kết nối mạng.

Mỗi thao tác bù cần xác định tiền điều kiện, tác động, hậu điều kiện và cách phát hiện đã thực hiện. Nếu không thể xác nhận an toàn, dừng tự động hóa và chuyển xử lý có trách nhiệm.

### 8.3 Ngăn kết quả cũ ghi đè quyết định mới

Một worker có thể trả kết quả thành công muộn sau khi người vận hành đã chọn phương án phục hồi khác. Nếu hệ thống chấp nhận kết quả đó mà không kiểm tra phiên bản công việc, con trỏ vault có thể quay về trạng thái không còn phù hợp.

Cần cơ chế kiểm tra trạng thái mong đợi khi cập nhật, định danh lần thực thi và thẩm quyền hiện tại. Việc fencing hoặc điều phối cũng phải xét tác động tại đích; một máy đích không hiểu token điều phối của PAM cần được bảo vệ bằng cơ chế phù hợp khác.

### 8.4 Tránh làm khóa tài khoản khi đối soát

Không thử lần lượt nhiều mật khẩu từ nhiều worker để tìm bản đúng mà không có giới hạn. Phối hợp ngân sách xác thực theo tài khoản, xét hoạt động consumer và chính sách khóa thực tế.

Lỗi mạng, trust hoặc rate limit phải được phân biệt với xác thực bị từ chối. Không dùng một phản hồi chung để kết luận chắc chắn về phiên bản credential.

## 9. Batch, cluster và nhiều consumer

### 9.1 Phục hồi theo tài khoản và phạm vi ảnh hưởng

Nếu rotation theo đợt trên nhiều máy có credential riêng, mỗi tài khoản có thể ở trạng thái khác nhau. Một lỗi trên máy thứ ba không tự là lý do khôi phục mật khẩu trên mọi máy đã hoàn tất an toàn.

Lập danh sách kết quả theo tài sản và tài khoản: chưa thay, đã xác nhận, chưa rõ, consumer chưa cập nhật và đã phục hồi. Sau đó quyết định theo từng phạm vi có quan hệ phụ thuộc.

### 9.2 Một tài khoản dùng chung cho nhiều consumer

Đây là một thay đổi credential với nhiều bên sử dụng, không phải nhiều rotation độc lập. Cần một nguồn có thẩm quyền và một kế hoạch cập nhật hoặc thu hẹp phạm vi lỗi.

Consumer offline vẫn có thể giữ bản cũ để dùng khi quay lại. Không đánh dấu mọi bên đã chuyển chỉ vì các instance đang online đều khỏe. Cần trạng thái xử lý cho tác vụ định kỳ, môi trường dự phòng và cấu hình chưa được dùng.

### 9.3 Dịch vụ xác thực có replication

Một hệ thống đích có nhiều node có thể có độ trễ áp dụng hoặc những điều kiện nhất quán riêng. Cần biết phép kiểm tra đang đi tới node nào và kết quả có đại diện cho đường sử dụng thực tế không.

Không đặt những password khác nhau lên các node của một danh tính dùng chung chỉ để làm từng phép thử riêng lẻ thành công. Thiết kế phải theo mô hình xác thực và replication thực tế của dịch vụ.

## 10. Mô hình kế hoạch phục hồi

Ví dụ sau chỉ biểu diễn yêu cầu thiết kế, không phải cấu hình triển khai trực tiếp của một sản phẩm PAM:

```yaml
rotation_recovery_model:
  account_reference: orders-production-service-account
  owner_reference: payments-platform-team
  workflow_controls:
    durable_execution_state: true
    protected_candidate_before_target_change: true
    single_authorized_executor: true
    late_results_checked_against_current_execution: true
  decisions:
    reconcile_uncertain_outcome_before_new_mutation: true
    old_credential_reuse_requires_safety_check: true
    compromised_old_credential_must_not_be_restored: true
    forward_recovery_supported_by_runbook: true
  coordination:
    vault_version_reference_required: true
    consumer_inventory_required: true
    deployment_jobs_coordinated: true
    bounded_authentication_attempts: true
  completion:
    target_state_confirmed: true
    vault_current_version_confirmed: true
    required_consumers_confirmed: true
    residual_credentials_and_access_tracked: true
    evidence_recorded_without_secret_values: true
```

Từng yêu cầu cần có thành phần chịu trách nhiệm, cơ chế thực thi và bằng chứng kiểm chứng. Giữ một bản cấu hình như trên không tự tạo giao dịch phân tán hay khả năng rollback của máy đích.

### Tiền điều kiện và hậu điều kiện

Với một hành động cụ thể, nên ghi rõ:

```text
Tiền điều kiện:
  Đúng tài khoản và tài nguyên; có thẩm quyền xử lý;
  biết hoặc đã phân loại trạng thái; phương án được phép;
  các tác vụ cạnh tranh được kiểm soát.

Hành động:
  Thực hiện thay đổi theo cơ chế được hỗ trợ,
  giữ dữ liệu cần phục hồi và ghi metadata công việc.

Hậu điều kiện:
  Xác nhận trạng thái đích, nguồn cấp và consumer;
  nêu rõ phần chưa chắc chắn và việc cần xử lý tiếp.
```

Nếu hậu điều kiện chưa đạt, hành động chưa thể được coi là kết thúc sự cố, ngay cả khi thao tác quản trị trả thành công.

## 11. Ví dụ: đích đổi thành công nhưng ứng dụng chưa cập nhật

Một dịch vụ có ba instance sử dụng tài khoản cơ sở dữ liệu. Trước thay đổi, vault, đích và cả ba instance dùng `v7`. Workflow đã bảo vệ candidate `v8`.

### Diễn biến

1. Đích chấp nhận thay đổi sang `v8`.
2. Worker mất phản hồi và chưa chuyển bản hiện hành của vault.
3. Một số kết nối cũ tiếp tục hoạt động, nhưng kết nối mới bằng `v7` thất bại.
4. Dashboard ứng dụng báo lỗi, còn job rotation báo timeout.

Lỗi dịch vụ không đủ cho biết đích chưa đổi. Đổi con trỏ hoặc cấu hình ứng dụng về `v7` không giải quyết được nếu đích chỉ còn chấp nhận `v8`.

### Đối soát

Nhóm xử lý dừng retry tự động, giữ quyền xử lý cho một bên và bảo toàn các phiên bản. Kiểm tra có kiểm soát xác nhận `v8` được đúng đích và tài khoản chấp nhận.

Nhóm chọn phục hồi theo hướng tiến: hoàn tất nguồn cấp `v8`, cập nhật các instance, kiểm tra xác thực mới và sức khỏe nghiệp vụ, đồng thời quản lý chuyển đổi pool kết nối theo khả năng ứng dụng. Việc tạo lại kết nối được giới hạn để tránh gây quá tải mới.

### Xác nhận kết quả

Bằng chứng cho thấy vault cấp đúng phiên bản, các consumer trong phạm vi đã nhận cấu hình và các kết nối mới hoạt động. Các kết nối hoặc tác vụ cũ được xử lý theo chính sách, không bị mặc định coi là đã kết thúc chỉ vì password đổi.

Nếu `v7` đã bị lộ, quyết định phục hồi vẫn không được đưa nó trở lại hiệu lực. Nếu `v8` cũng có nguy cơ lộ trong quá trình sự cố, cần một phiên bản kế tiếp và xử lý nguyên nhân thay vì dừng ở việc dịch vụ hoạt động lại.

### Trường hợp có thể chọn hoàn tác

Trong một kịch bản khác, credential cũ được xác nhận còn an toàn, đích hỗ trợ đặt lại và các consumer có thể được phối hợp đầy đủ. Nhóm có thể chọn hoàn tác credential cùng cấu hình liên quan theo kế hoạch đã kiểm soát.

Kết quả phải được xác minh tại cả đích, vault và consumer. Việc chỉ khôi phục một snapshot hoặc một file cấu hình rồi thấy tiến trình chạy chưa đủ chứng minh đã hoàn tác hoàn chỉnh.

## 12. Xác minh, bằng chứng và đóng sự cố

### 12.1 Xác minh theo toàn luồng

Cần kiểm tra những điều phù hợp phạm vi:

- Đúng tài nguyên và danh tính được xác nhận.
- Credential được chọn thực sự được đích chấp nhận trong ngữ cảnh sử dụng.
- Vault cấp đúng phiên bản theo quyết định mới nhất.
- Consumer thực hiện được xác thực mới và công việc cần thiết.
- Quyền tại đích vẫn đúng thiết kế, không còn quyền sửa chữa vượt hạn.
- Credential dư, candidate, bản cũ và các công việc retry được xử lý hoặc theo dõi rõ.
- Phiên, token và tác vụ còn tồn tại được đánh giá riêng.

Một kết nối cũ đang khỏe có thể che lỗi credential trên kết nối mới. Ngược lại, ép mọi kết nối ngắt ngay để thử có thể gây gián đoạn lớn. Chọn phép kiểm tra có giới hạn và tăng dần theo mức độ cần thiết.

### 12.2 Audit không chứa secret

Giữ mã sự cố, công việc rotation, tài nguyên, tài khoản, phiên bản tham chiếu, trạng thái quan sát, quyết định, người hoặc dịch vụ thực hiện, thời điểm và kết quả từng hành động. Nêu rõ lý do chọn rollback hay forward recovery và các giới hạn còn lại.

Bảo vệ log, bản ghi phiên và dữ liệu chẩn đoán. Không ghi môi trường tiến trình, chuỗi kết nối hoặc request đầy đủ nếu có thể chứa secret. Quyền đọc bằng chứng không mặc nhiên bao gồm quyền xem mọi credential được dùng để sửa chữa.

### 12.3 Thu hồi quyền tạm và rà soát nguyên nhân

Kết thúc phiên sửa chữa theo chính sách, thu hồi grant JIT và xử lý credential khẩn cấp đã dùng. Rotation không tự thực hiện các bước này.

Xác định nguyên nhân gốc: mất candidate, phản hồi timeout, consumer không reload, policy đích, quyền thiếu, nhiều writer hoặc trust sai. Cải thiện workflow và runbook dựa trên bằng chứng, thay vì chỉ tăng số lần retry hoặc giảm kiểm tra bảo mật.

## 13. Thực hành lỗi có kiểm soát

Trong môi trường lab được phép, dùng tài khoản thử, dữ liệu giả và giới hạn khóa tài khoản đã biết. Đây là các tình huống học tập đề xuất, không phải kết quả kiểm thử của một sản phẩm cụ thể.

| Tình huống | Điều cần quan sát |
|---|---|
| Lỗi trước khi gửi thay đổi | Không khôi phục đích không cần thiết; candidate được xử lý đúng |
| Mất phản hồi sau khi đích áp dụng | Kết quả chưa chắc chắn được đối soát trước thay đổi tiếp |
| Vault không cập nhật được bản hiện hành | Candidate được bảo vệ; không phát hành bản sai trạng thái |
| Consumer chỉ cập nhật một phần | Có kiểm kê theo consumer, không chỉ dựa vào instance đầu tiên |
| Đích từ chối khôi phục password cũ | Có đường phục hồi khác, không tự nới chính sách |
| Credential cũ bị coi là đã lộ | Không được đưa trở lại hiệu lực để giảm gián đoạn |
| Worker cũ trả kết quả muộn | Không ghi đè quyết định và phiên bản hiện hành mới hơn |
| Hai worker cùng xử lý | Chỉ bên có thẩm quyền được tác động tài khoản |
| Một máy lỗi trong batch nhiều tài khoản riêng | Quyết định phục hồi theo phạm vi, không hoàn tác toàn bộ một cách máy móc |
| Consumer offline quay lại | Không sử dụng credential lạc hậu ngoài kế hoạch |
| Phiên cũ tiếp tục sau thay đổi | Được xử lý riêng với mục tiêu thu hồi phiên và quyền |
| Sử dụng đường sửa chữa khẩn cấp | Có bằng chứng, giới hạn và bước dọn quyền sau sự cố |

Một runbook sẵn sàng vận hành cần mô tả rõ trạng thái, thẩm quyền, tiền điều kiện, tác động, hậu điều kiện và điểm chuyển sang xử lý thủ công. Khả năng phục hồi được chứng minh khi hệ thống đi tới trạng thái nhất quán, quyền được kiểm soát và bằng chứng giải thích được toàn bộ quá trình.

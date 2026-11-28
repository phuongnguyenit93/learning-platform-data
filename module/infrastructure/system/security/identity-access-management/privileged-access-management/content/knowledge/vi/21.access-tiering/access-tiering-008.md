# Tách audit admin trong mô hình phân tầng truy cập

## Mục tiêu bài học

Trong Privileged Access Management (PAM), người vận hành có thể thay đổi máy chủ, sử dụng tài khoản đặc quyền hoặc sửa cấu hình truy cập. Nếu cùng một quyền quản trị cũng cho phép xóa bằng chứng và tự xác nhận rằng hoạt động của mình phù hợp, giá trị kiểm tra độc lập sẽ suy giảm.

**Tách audit admin** trong bài này là phân tách quyền thực hiện và quản trị hoạt động đặc quyền với quyền xem xét, quản lý và bảo vệ bằng chứng của hoạt động đó. Việc tách cần xét cả con người, danh tính, vai trò, hệ thống và đường kiểm soát gián tiếp.

Sau bài học, bạn có thể:

- Phân biệt người vận hành, người rà soát audit và người quản trị nền tảng bằng chứng.
- Thiết kế quyền tối thiểu cho từng vai trò trong phạm vi tiering.
- Nhận diện đường sửa hoặc làm mất bằng chứng qua cấu hình, lưu trữ, IAM và khóa mã hóa.
- Bảo vệ chuỗi thu thập log và bản ghi phiên mà vẫn đáp ứng công việc vận hành.
- Xử lý ngoại lệ, sự cố ghi nhận và tình huống đội ngũ nhỏ có giới hạn độc lập.
- Lập bằng chứng để kiểm chứng việc phân tách đã có hiệu lực.

Các vai trò, cấu trúc dữ liệu và tình huống dưới đây là minh họa thiết kế. Cần ánh xạ sang khả năng của sản phẩm và chính sách thực tế.

## 1. Vấn đề không chỉ là một người có hai tên tài khoản

Giả sử một quản trị viên mở phiên PAM, thay đổi cấu hình máy chủ rồi có thể:

- Xóa bản ghi phiên.
- Giảm thời hạn lưu log.
- Tắt nguồn thu thập.
- Tự thêm mình vào nhóm audit.
- Sửa báo cáo để bỏ sự kiện liên quan.

Nếu việc kiểm tra chỉ dựa trên dữ liệu mà người đó tùy ý kiểm soát, tổ chức khó xác minh hoạt động đã diễn ra và cách quy trình được tuân thủ.

Tạo tài khoản `admin` và `auditor` riêng cho cùng người có thể giúp tách phiên, mục đích và dấu vết. Nó không tự tạo một người kiểm tra độc lập nếu người đó vẫn kiểm soát cả hai vai trò.

Một thiết kế cần trả lời riêng:

1. Ai có thể thực hiện thay đổi?
2. Ai có thể quyết định việc cấp quyền?
3. Ai có thể xem xét bằng chứng?
4. Ai có thể làm mất, sửa hoặc thay đổi cách tạo bằng chứng?
5. Ai có thể cấp lại các quyền trên cho chính mình?

Các câu trả lời giúp tìm ra xung đột thực tế, thay vì chỉ kiểm tra tên nhóm.

## 2. Phân biệt các loại vai trò audit và admin

### 2.1. Quản trị viên tài sản hoặc workload

Người này vận hành máy chủ, ứng dụng hoặc hạ tầng trong phạm vi được giao. Họ có thể cần xem log vận hành để chẩn đoán.

Không nên hiểu nguyên tắc tách là “admin không được đọc bất kỳ log nào”. Cần phân biệt log phục vụ công việc được phép với quyền quản trị toàn bộ hồ sơ bằng chứng và quyền xóa dấu vết.

### 2.2. Quản trị viên PAM

Vai trò này có thể quản lý tích hợp, cấu hình phiên, policy, tài khoản kỹ thuật hoặc đường truy cập.

Tùy sản phẩm, một tài khoản quản trị toàn cục có thể đồng thời kiểm soát audit. Cần đánh giá quyền đó thay vì mặc định PAM đã tách vai trò đầy đủ.

Nếu không thể tách một khả năng nhạy cảm trong sản phẩm, phải ghi giới hạn và bổ sung kiểm soát ở lớp khác khi phù hợp.

### 2.3. Người rà soát audit

Người rà soát kiểm tra quyết định phê duyệt, grant, phiên, thay đổi cấu hình và việc thu hồi. Vai trò này thường cần quyền đọc có phạm vi và khả năng lập kết luận.

Không mặc định người rà soát cần quyền sửa policy, lấy credential, mở phiên quản trị hoặc thay thời hạn lưu.

Quyền đọc bằng chứng cũng có thể rất nhạy cảm. Bản ghi phiên có thể chứa dữ liệu, bí mật hiển thị hoặc thông tin hạ tầng, nên không phải cứ “read-only” là ít rủi ro.

### 2.4. Người quản trị nền tảng bằng chứng

Vai trò này vận hành hệ thống thu nhận, lưu trữ, chỉ mục, sao lưu hoặc xuất bằng chứng.

Người đó không nhất thiết là người đưa ra kết luận audit. Họ cũng có thể nắm những khả năng ảnh hưởng tính toàn vẹn và khả dụng của dữ liệu.

Cần tách hoặc kiểm soát các hành động như thay retention, xóa kho, đổi tuyến thu thập và thay khóa liên quan. Không coi họ là người đọc thông thường chỉ vì hệ thống họ vận hành mang tên “audit”.

### 2.5. Người phê duyệt thay đổi nhạy cảm

Một số thay đổi cần người có thẩm quyền độc lập, chẳng hạn giảm thời hạn lưu hoặc cấp quyền rộng cho kho bằng chứng.

Vai trò này nên xem đúng phạm vi, tác động và điều kiện. Hai bước phê duyệt do cùng một cá nhân thực hiện không tự tạo kiểm soát hai người độc lập.

## 3. Tách trách nhiệm trong bối cảnh tiering

Tiering giới hạn nơi một danh tính được phép quản trị và những phạm vi nó có thể điều khiển. Tách audit/admin bổ sung một chiều khác: người có quyền thực hiện không đồng thời được tự kiểm soát toàn bộ bằng chứng về việc đó.

Hai chiều không thay thế nhau.

- Quản trị viên máy chủ Tier 1 có thể chỉ vận hành dịch vụ của mình.
- Người rà soát có thể đọc bằng chứng liên quan nhiều dịch vụ nhưng không quản trị chúng.
- Người vận hành kho bằng chứng có thể ảnh hưởng dữ liệu của nhiều tầng, nên cần được bảo vệ theo khả năng thực tế.

Tên tier trong tổ chức có thể khác nhau. Không mặc định một hệ thống log là Tier 0 chỉ vì nó quan trọng, cũng không mặc định nó là hệ thống thông thường chỉ vì không chạy ứng dụng kinh doanh.

Cần xét:

- Nó có quyền sửa policy hoặc danh tính ở phạm vi nào?
- Nó có thể điều khiển agent, broker hoặc máy nguồn không?
- Nó có thể đọc bí mật hoặc dữ liệu của những tầng nào?
- Ai có thể quản trị host, nền tảng ảo hóa, backup và khóa của nó?

Một công cụ audit chỉ đọc có phạm vi rủi ro khác một nền tảng vừa thu log vừa đẩy cấu hình đặc quyền. Phân loại cần phản ánh sự khác biệt đó.

### Đường kiểm soát cần đánh giá

```text
Người vận hành -> PAM -> Tài sản đích
                    |
                    v
             Sự kiện / bản ghi phiên
                    |
                    v
           Thu nhận và kho bằng chứng
                    |
                    v
              Người rà soát audit

Các đường gián tiếp:
IAM / nhóm quyền -> ai được sửa hoặc đọc
Lưu trữ / backup -> dữ liệu còn hay mất
Khóa mã hóa      -> dữ liệu còn đọc được hay không
Cấu hình nguồn   -> bằng chứng có được tạo và gửi hay không
```

Tách quyền ở giao diện audit nhưng để cùng admin toàn quyền trên host hoặc kho lưu có thể chưa đạt mục tiêu.

## 4. Xây ma trận quyền từ hành động cụ thể

Một ma trận minh họa:

| Hành động | Vận hành tài sản | Quản trị PAM | Rà soát audit | Vận hành kho bằng chứng |
|---|---|---|---|---|
| Mở phiên quản trị đích | Theo grant và phạm vi | Không mặc định có | Không mặc định có | Không |
| Sửa policy truy cập | Không theo quyền vận hành đích | Theo vai trò được giao | Không | Không |
| Xem log vận hành của tài sản | Theo nhu cầu và phạm vi | Theo nhiệm vụ hỗ trợ | Theo phạm vi rà soát | Theo nhiệm vụ được phép |
| Xem bản ghi phiên nhạy cảm | Quyền riêng khi cần | Không mặc định toàn bộ | Quyền đọc được giới hạn | Không mặc định xem nội dung |
| Xuất bộ bằng chứng | Quyền riêng khi có lý do | Không mặc định | Theo hồ sơ và kiểm soát xuất | Theo tác vụ được duyệt |
| Thay retention hoặc xóa dữ liệu được giữ | Không | Không mặc định | Không | Qua thẩm quyền và cơ chế riêng |
| Cấp vai trò audit hoặc quản trị kho | Không tự cấp | Không tự cấp ngoài phạm vi | Không | Không tự cấp ngoài phạm vi |

Ma trận là điểm khởi đầu. Những cụm “theo phạm vi” phải được cụ thể hóa thành resource, hành động, điều kiện và thời hạn.

### 4.1. Tách đọc, xuất và xóa

Quyền xem một bản ghi không nên tự bao gồm xuất toàn bộ dữ liệu. Quyền vận hành chỉ mục không nên tự bao gồm xóa dữ liệu gốc đang được giữ.

Cần xét cả bản gốc, bản sao, dữ liệu đã xử lý và báo cáo. Một bản sao bị chỉnh không nên được trình bày như bằng chứng gốc nguyên vẹn.

### 4.2. Bảo vệ quyền cấp quyền

Nếu người vận hành có thể tự thêm mình vào nhóm audit hoặc nhóm quản trị kho, việc tách trên giấy dễ bị vượt qua.

Quyền quản lý membership, role assignment và liên kết danh tính cần nằm trong mô hình phân tách. Cũng cần xét API, tài khoản dịch vụ và cơ chế khôi phục có thể làm điều tương tự.

## 5. Bảo vệ chuỗi tạo và lưu bằng chứng

Một kho lưu được bảo vệ tốt vẫn không giải quyết được việc nguồn không tạo sự kiện. Cần kiểm tra toàn chuỗi.

### 5.1. Tại nguồn phát sinh

Nguồn có thể là PAM, IdP, gateway, máy đích hoặc ứng dụng. Cần biết sự kiện nào được tạo, điều kiện nào làm mất sự kiện và ai có thể sửa cấu hình.

Quản trị viên có quyền rất cao trên máy nguồn có thể ảnh hưởng log cục bộ hoặc cơ chế gửi. Không nên tuyên bố đã ngăn được mọi sửa đổi tại nguồn nếu nền tảng không có khả năng đó.

Có thể giảm rủi ro bằng cách chuyển sự kiện sớm sang một miền quản trị khác, giới hạn quyền đổi cấu hình và theo dõi độ liên tục. Đây là biện pháp giảm tác động, không phải bằng chứng rằng nguồn luôn nói đúng.

### 5.2. Thu nhận và truyền

Tài khoản gửi log chỉ nên có những quyền cần để gửi dữ liệu. Không dùng cùng credential để vừa ghi sự kiện vừa xóa kho hoặc thay retention nếu không cần.

Cần xử lý:

- Xác thực đúng nguồn gửi.
- Bảo vệ dữ liệu khi truyền.
- Mất kết nối, hàng đợi và giới hạn dung lượng.
- Sự kiện trùng, xung đột mã sự kiện hoặc đến muộn.
- Theo dõi nguồn ngừng gửi và thay đổi cấu hình.

Một tín hiệu heartbeat giúp nhận biết nguồn có đang liên lạc, nhưng không tự chứng minh mọi sự kiện cần thiết đã được tạo. Cần đối soát với những nguồn và hoạt động liên quan.

Không có log không đồng nghĩa không có hoạt động.

### 5.3. Kho lưu và thời hạn giữ

Có thể sử dụng cơ chế ghi thêm, hạn chế sửa/xóa, kho độc lập hoặc chế độ lưu được bảo vệ nếu nền tảng hỗ trợ.

Cần kiểm tra quyền thực tế của:

- Quản trị viên ứng dụng.
- Quản trị viên hệ điều hành và nền tảng.
- Quản trị viên lưu trữ hoặc tài khoản đám mây.
- Tài khoản backup và phục hồi.
- Vai trò quản trị khóa.

Một log không có nút sửa trong giao diện chưa chắc bất biến ở lớp lưu bên dưới. Cấu hình giữ dữ liệu cũng cần được kiểm tra bằng khả năng thực thi, không chỉ tên tùy chọn.

Không mặc định một khoảng thời gian lưu phù hợp mọi tổ chức. Cần dựa trên mục đích, yêu cầu áp dụng, loại dữ liệu và quy trình xử lý hồ sơ cần bảo toàn.

### 5.4. Khóa mã hóa là một đường ảnh hưởng

Mã hóa bảo vệ nội dung, nhưng người có quyền vô hiệu hóa hoặc hủy khóa có thể làm dữ liệu mất khả năng sử dụng.

Cần đánh giá quyền đọc, sử dụng, thay đổi, vô hiệu hóa và xóa khóa theo khả năng nền tảng. Tách quyền quản lý khóa có thể hỗ trợ mục tiêu, nhưng phải xét cả các vai trò có thể tự cấp lại quyền đó.

Không giữ dữ liệu đủ lâu trên giấy trong khi vòng đời khóa khiến dữ liệu không còn đọc được. Kế hoạch phục hồi cũng cần tính đến khóa và quyền truy cập.

### 5.5. Chữ ký và mã băm có giới hạn

Mã băm giúp đối chiếu dữ liệu với một mốc đã biết. Chuỗi băm hoặc chữ ký có thể hỗ trợ phát hiện thay đổi theo mô hình được thiết kế.

Chúng không tự chứng minh dữ liệu đầy đủ, nội dung nguồn đúng hoặc người tạo sự kiện có thẩm quyền. Nếu cùng một người kiểm soát cả dữ liệu và mọi mốc kiểm chứng, mức độc lập có thể còn hạn chế.

Nên giữ mốc và bằng chứng liên quan ở nơi có quyền quản trị phù hợp với mục tiêu bảo vệ.

## 6. Tách quyền trong PAM mà vẫn làm được việc

### 6.1. Quyền hỗ trợ vận hành có phạm vi

Người quản trị có thể cần xem kết quả phiên của mình để điều tra lỗi kết nối. Có thể cung cấp thông tin hoặc một chế độ xem phù hợp mà không cấp toàn bộ quyền audit.

Ví dụ:

- Vận hành xem trạng thái và mã lỗi của phiên thuộc phạm vi công việc.
- Người rà soát xem hồ sơ phê duyệt, grant và hoạt động theo nhiệm vụ.
- Quyền xem nội dung bản ghi nhạy cảm được cấp riêng.
- Quyền xuất dữ liệu có lý do và dấu vết.

Không dùng một vai trò “support toàn cục” quá rộng để giải quyết mọi nhu cầu hỗ trợ.

### 6.2. JIT cho vai trò nhạy cảm

Một số thao tác quản trị hệ thống audit cần quyền nâng tạm thời. Có thể yêu cầu phê duyệt, giới hạn thời gian và đúng resource.

Ví dụ ý định chính sách:

```yaml
temporary_evidence_admin:
  request_type: repair_audit_index
  beneficiary: evidence-operator-07
  scope:
    service: evidence-platform
    operation: rebuild_index
    dataset_reference: evidence-dataset-21
  excluded:
    - change_retention
    - delete_original_records
    - disable_collection
    - grant_self_additional_roles
  controls:
    independent_approval_required: true
    limited_duration_required: true
    record_administrative_activity: true
    verify_original_data_preserved: true
```

Đây là mô hình mô tả, không phải cấu hình sản phẩm. Cần xác minh tác vụ “rebuild index” có thực sự tách khỏi xóa dữ liệu gốc hay không.

JIT giảm thời gian quyền tồn tại nhưng không biến một quyền phá hủy rộng thành an toàn. Nếu thao tác có thể xóa toàn bộ dữ liệu trong một phút, việc cấp trong năm phút vẫn có tác động lớn.

### 6.3. Tách người và tách danh tính

Nếu yêu cầu kiểm tra độc lập, cần người khác có trách nhiệm xem xét, không chỉ tài khoản khác của cùng người.

Hệ thống nên nhận biết mối liên hệ giữa các danh tính khi kiểm tra xung đột. Tên hiển thị hoặc email khác nhau không đủ chứng minh hai người khác nhau.

Người phê duyệt cũng cần thẩm quyền đúng phạm vi. Không chọn một người bất kỳ chỉ để đủ số bước.

### 6.4. Thay đổi policy audit là hoạt động cần được audit

Bản ghi cần bao phủ các hành động như bật/tắt thu thập, thay tuyến gửi, đổi retention, sửa quyền đọc/xuất và thay cấu hình che dữ liệu.

Nếu việc tắt audit cũng tắt luôn dấu vết của hành động tắt, cần lớp kiểm soát hoặc nguồn đối chiếu khác. Cần biết những giới hạn còn lại thay vì mặc định hệ thống tự bảo vệ hoàn toàn.

## 7. Quyền riêng tư, nội dung nhạy cảm và bản sao bằng chứng

Phân tách audit/admin không có nghĩa người rà soát được đọc mọi dữ liệu.

Bản ghi phiên có thể hiển thị thông tin khách hàng, token hoặc nội dung cấu hình nhạy cảm. Cần giới hạn người xem, phạm vi vụ việc và mục đích.

Có thể cung cấp bản đã giảm nhạy cảm cho một số nhiệm vụ. Khi đó:

- Phải biết bản nào là gốc và bản nào là dẫn xuất.
- Quy trình che dữ liệu cần được kiểm soát.
- Cần giữ liên kết và khả năng giải thích những phần đã loại bỏ.
- Không sửa bản gốc âm thầm để thay bằng một bản đã xử lý.
- Quyền xem bản gốc nhạy cảm phải được cấp riêng khi thực sự cần.

Quyền xuất cũng cần kiểm soát điểm đến và người nhận. Một bản tải xuống thiết bị không được quản lý có thể vượt khỏi mọi phân quyền ở cổng audit.

Việc đọc hoặc xuất bằng chứng nên để lại dấu vết thích hợp. Dấu vết đó cũng cần được bảo vệ, không nằm hoàn toàn dưới quyền người đang được theo dõi.

## 8. Ngoại lệ và giới hạn thực tế

### 8.1. Đội ngũ nhỏ

Một tổ chức nhỏ có thể chưa có đủ người để tách mọi vai trò thường trực. Cần ghi rõ xung đột thay vì mô tả là đã có kiểm tra độc lập hoàn toàn.

Có thể kết hợp các biện pháp phù hợp như:

- Quyền nâng tạm thời thay vì quyền luôn có.
- Phê duyệt hoặc rà soát bởi người có trách nhiệm khác.
- Lưu bản sao bằng chứng ở miền quản trị khác.
- Hạn chế khả năng xóa và giám sát thay đổi nhạy cảm.
- Rà soát định kỳ theo phạm vi và mức rủi ro.

Các biện pháp bù cần được đánh giá theo khả năng thực tế. Một người tự duyệt bằng tài khoản thứ hai không phải biện pháp bù tạo độc lập.

### 8.2. Hệ thống audit gặp sự cố

Nếu ghi phiên hoặc gửi log không hoạt động, hành vi với truy cập đặc quyền phải theo chính sách đã thiết kế.

Có thể chặn một loại phiên bắt buộc ghi nhận, hoặc áp dụng đường khẩn cấp được cho phép với trách nhiệm, thời hạn và bằng chứng thay thế cụ thể.

Không tự tắt yêu cầu ghi nhận rồi coi truy cập vẫn tương đương bình thường. Cũng không mặc định mọi sự cố log đều phải có cùng cách xử lý bất kể mức rủi ro và tác động vận hành.

### 8.3. Quản trị viên toàn cục

Một số nền tảng có vai trò quyền rất rộng hoặc một lớp quản trị bên dưới khó tách hoàn toàn. Cần giảm số người có quyền, giới hạn sử dụng, bảo vệ danh tính và giám sát từ nguồn đủ độc lập khi khả thi.

Nếu vẫn còn một đường toàn quyền có thể sửa bằng chứng, báo cáo cần nêu đúng giới hạn. Không đặt tên vai trò là “read-only audit” để che quyền quản trị khác của cùng người.

## 9. Tình huống thực hành: sửa lỗi kho audit trong lúc có sự cố sản xuất

### 9.1. Bối cảnh

Quân vận hành dịch vụ sản xuất qua PAM. Hạnh rà soát hoạt động đặc quyền. Dũng vận hành nền tảng bằng chứng.

Kho chỉ mục gặp lỗi, khiến giao diện tìm kiếm không trả đủ kết quả. Dữ liệu gốc vẫn được lưu ở kho riêng theo thiết kế.

Dũng yêu cầu quyền tạm để dựng lại chỉ mục. Cùng lúc, Quân cần tiếp tục một phiên khắc phục dịch vụ.

### 9.2. Phạm vi quyền mong muốn

| Người/vai trò | Quyền trong tình huống | Giới hạn |
|---|---|---|
| Quân, vận hành sản xuất | Thực hiện công việc theo grant và xem trạng thái cần thiết | Không thay retention hoặc xóa bằng chứng |
| Hạnh, rà soát audit | Đối chiếu quyết định, phiên và kết quả sửa kho | Không quản trị workload hoặc tự đổi dữ liệu gốc |
| Dũng, vận hành bằng chứng | Sửa chỉ mục trong phạm vi đã duyệt | Không mặc định xóa dữ liệu gốc hoặc tắt thu thập |
| Người phê duyệt được chỉ định | Đánh giá tác động và cho phép tác vụ sửa | Không dùng việc phê duyệt để sửa lịch sử |

### 9.3. Luồng xử lý

1. Xác định thành phần lỗi: giao diện, chỉ mục, thu nhận hay dữ liệu gốc.
2. Kiểm tra việc thu thập và giữ dữ liệu có tiếp tục hoạt động không.
3. Đánh giá tác động tới những phiên bắt buộc có bằng chứng.
4. Cấp quyền tạm cho đúng tác vụ sửa khi đủ điều kiện.
5. Ghi nhận người thực hiện, phạm vi, phiên bản cấu hình và kết quả.
6. Dựng lại chỉ mục mà giữ nguyên dữ liệu gốc theo thiết kế.
7. Đối soát số lượng, khoảng thời gian và mẫu sự kiện giữa nguồn và kết quả tìm kiếm.
8. Thu hồi quyền tạm rồi để người rà soát xác nhận theo nhiệm vụ.

Số lượng bằng nhau không tự chứng minh toàn bộ nội dung đúng. Cần kiểm tra quan hệ, nguồn và những mẫu có ý nghĩa.

### 9.4. Một yêu cầu không phù hợp

Dũng đề nghị cấp quyền xóa dữ liệu gốc “để làm sạch rồi nạp lại”.

Không nên coi đây là cùng phạm vi với sửa chỉ mục. Cần làm rõ vì sao cần xóa, dữ liệu nào liên quan, thời hạn giữ và thẩm quyền nào được phép quyết định.

Nếu không đáp ứng điều kiện, không cấp phần quyền đó. Nếu có quy trình thay đổi hợp lệ, nó phải có hồ sơ và biện pháp bảo vệ riêng; không được tự biến thành một bước phụ của tác vụ sửa.

### 9.5. Phát hiện xung đột gián tiếp

Hạnh có vai trò audit chỉ đọc trong ứng dụng, nhưng đồng thời thuộc nhóm quản trị toàn cục của tài khoản lưu trữ chứa bằng chứng.

Về quyền hiệu lực, Hạnh có thể có khả năng sửa hoặc làm mất dữ liệu dù giao diện audit ghi “read-only”. Cần xử lý xung đột theo mô hình quyền thực tế và kiểm tra các đường cấp lại quyền.

Việc chỉ gỡ nút xóa khỏi giao diện không giải quyết quyền ở lớp lưu trữ.

### 9.6. Nếu nguồn log đã bị tắt

Giả sử điều tra phát hiện nguồn thu thập của một máy bị tắt trong 20 phút.

Không thể tái tạo chắc chắn mọi hoạt động chỉ bằng cách bật lại. Cần đối chiếu nguồn khác như PAM, IdP, hệ thống đích hoặc sự kiện thay đổi, ghi khoảng trống và giới hạn kết luận.

Không ghi “không có hành vi bất thường” chỉ vì không có sự kiện trong khoảng nguồn ngừng gửi.

## 10. Quy trình cấp, rà soát và thu hồi vai trò

### 10.1. Cấp quyền

Hồ sơ cấp quyền cần nêu:

- Người hưởng quyền và mục đích.
- Vai trò cụ thể: vận hành, đọc audit, xuất bằng chứng hay quản trị nền tảng.
- Resource, dataset, tenant hoặc phạm vi tier.
- Những quyền xung đột đã được kiểm tra.
- Điều kiện xác thực, nguồn quản trị và thời hạn.
- Người phê duyệt có thẩm quyền.

Không cấp một nhóm “audit-admin” chung mà không biết nó thực sự bao gồm hành động nào.

### 10.2. Rà soát quyền hiệu lực

Cần xem cả quyền trực tiếp, nhóm, kế thừa, tài khoản thay thế và những vai trò có thể tự cấp thêm quyền.

Những câu hỏi hữu ích:

- Người vận hành có thể tự xóa dấu vết ở lớp nào?
- Người rà soát có thể thay chính sách hoặc grant mà họ đang kiểm tra không?
- Người quản trị kho có thể thay khóa hoặc retention mà không có dấu vết độc lập không?
- Một thay đổi membership có làm cùng người nắm các vai trò xung đột không?
- Quyền hỗ trợ tạm có trở thành thường trực không?

Một quyền không được dùng lâu không tự chứng minh nên xóa ngay, nhưng cần xác minh nhu cầu tồn tại và phạm vi.

### 10.3. Thu hồi

Khi hết nhiệm vụ hoặc nhân sự chuyển vai trò, cần xử lý eligibility, assignment, grant, phiên và token liên quan theo cơ chế nền tảng.

Bỏ vai trò trong ứng dụng không tự bảo đảm phiên cũ hoặc quyền lưu trữ đã bị gỡ. Cần đối soát cả lớp IAM, kho, khóa và tài khoản dịch vụ nếu thuộc phạm vi.

Không xóa hồ sơ audit chỉ vì người tạo hoặc người được ghi nhận đã nghỉ việc. Vòng đời bằng chứng phải theo mục đích và yêu cầu áp dụng riêng.

## 11. Kiểm chứng phân tách audit/admin

Thực hiện với tài khoản và dữ liệu kiểm thử trong phạm vi được phép. Không xóa bằng chứng thật để thử xem kiểm soát có hoạt động hay không.

| Phép thử | Kết quả mong đợi |
|---|---|
| Admin tài sản thử xóa bản ghi phiên trung tâm | Không có quyền ngoài phạm vi đã thiết kế |
| Admin PAM thử giảm retention | Bị chặn hoặc đi qua thẩm quyền thay đổi riêng |
| Người rà soát thử mở phiên quản trị workload | Không được phép chỉ nhờ vai trò audit |
| Người đọc audit thử xuất toàn bộ dataset | Kiểm tra quyền xuất và phạm vi riêng |
| Người vận hành kho thử đọc nội dung nhạy cảm | Không mặc định có quyền xem chỉ vì quản trị nền tảng |
| Người sửa chỉ mục thử xóa dữ liệu gốc | Không nằm trong quyền tác vụ hạn chế |
| Admin thử tự thêm vào nhóm audit đặc quyền | Không vượt phân tách qua quyền cấp quyền |
| Cùng một người dùng hai tài khoản duyệt và thực hiện | Kiểm tra độc lập theo chủ thể thực |
| Đổi retention, tuyến log hoặc cấu hình thu nhận | Có thẩm quyền và dấu vết thay đổi |
| Nguồn log ngừng gửi | Có phát hiện theo thiết kế và quy trình xử lý |
| Log đến muộn hoặc bị gửi trùng | Không mất hoặc nhân bản sai ý nghĩa sự kiện |
| Quyền lưu trữ/backup vượt vai trò ứng dụng | Được phát hiện trong quyền hiệu lực |
| Quyền vô hiệu hóa khóa làm dữ liệu khó sử dụng | Có kiểm soát và khả năng phát hiện phù hợp |
| Mất ghi phiên khi có yêu cầu truy cập | Thực thi đúng chính sách hoặc đường khẩn cấp |
| Quyền nâng tạm hết hạn | Không còn khả năng sử dụng ngoài cửa sổ |
| Xem hoặc xuất bằng chứng | Có dấu vết được bảo vệ và liên kết đúng người |
| Phục hồi dữ liệu | Bằng chứng và khóa liên quan phục hồi được theo thiết kế |

Cần thử cả luồng công việc hợp lệ: vận hành chẩn đoán được lỗi, người rà soát xem được phạm vi cần thiết và người quản trị nền tảng sửa được sự cố đã duyệt.

Nếu sản phẩm không hỗ trợ một mức tách, phải ghi giới hạn và kiểm chứng biện pháp khác. Không báo đạt chỉ vì các vai trò có tên khác nhau.

## 12. Bằng chứng để chứng minh việc phân tách

Một bộ hồ sơ có thể gồm:

- Định nghĩa vai trò và ma trận hành động.
- Assignment, membership và quan hệ giữa các danh tính cùng chủ thể.
- Quyền hiệu lực trên ứng dụng, host, lưu trữ, backup và khóa.
- Phê duyệt và thời hạn của quyền nâng tạm.
- Cấu hình nguồn log, thu nhận và lưu giữ theo phiên bản.
- Sự kiện thay đổi các cấu hình nhạy cảm.
- Kết quả các phép thử được thực hiện.
- Hoạt động đọc/xuất bằng chứng và người thực hiện.
- Sự cố thiếu log, ngoại lệ, điều kiện bù và kết quả khắc phục.

Khi kiểm tra quá khứ, cần biết cấu hình và vai trò có hiệu lực lúc đó. Ma trận quyền hiện tại không tự chứng minh một người không thể sửa dữ liệu vào tháng trước.

Hồ sơ phải phân biệt:

- Điều đã được chặn bằng kỹ thuật.
- Điều chỉ được phát hiện và rà soát.
- Điều dựa vào quy trình con người.
- Giới hạn chưa có biện pháp đáp ứng đầy đủ.

Cách mô tả này giúp người đọc hiểu mức bảo vệ thực tế và tránh coi mọi lớp là tương đương.

## 13. Những sai lầm thường gặp

**Tạo hai tài khoản rồi gọi là hai người độc lập.** Cần xem chủ thể thực và các quyền người đó kiểm soát.

**Tách trong ứng dụng nhưng bỏ quyền host hoặc storage.** Các lớp bên dưới có thể sửa hoặc làm mất bằng chứng.

**Gộp người đọc audit với người quản trị kho.** Quyền xem xét và quyền tác động nền tảng có mục đích khác nhau.

**Coi read-only là không nhạy cảm.** Bản ghi phiên và dữ liệu hạ tầng có thể tiết lộ thông tin quan trọng.

**Cấm admin xem mọi log.** Họ vẫn cần dữ liệu vận hành có phạm vi; mục tiêu là không tự kiểm soát toàn bộ dấu vết.

**Dựa hoàn toàn vào mã băm.** Cần nguồn, độ đầy đủ, mốc kiểm chứng và quyền quản trị đủ độc lập.

**Quên khóa mã hóa và backup.** Dữ liệu có thể mất khả dụng hoặc bị thay đổi qua các đường này.

**Tắt audit để xử lý sự cố mà không ghi nhận ngoại lệ.** Cần chính sách, thẩm quyền và giới hạn rõ.

**Cho rằng không có log nghĩa là không có hành động.** Phải kiểm tra độ liên tục và khoảng trống nguồn.

## 14. Tự kiểm tra

1. Tách tài khoản khác tách người kiểm tra độc lập như thế nào?
2. Vì sao một auditor chỉ đọc trong ứng dụng vẫn có thể có xung đột quyền?
3. Admin workload có được xem log chẩn đoán của mình không?
4. Cần phân biệt những quyền nào trên bằng chứng?
5. Vì sao quyền quản trị khóa mã hóa liên quan tới audit?
6. Một kho giữ dữ liệu tốt có bảo đảm nguồn luôn tạo đủ log không?
7. Sửa chỉ mục có tự cho phép xóa bản gốc không?
8. Nếu đội ngũ nhỏ không thể tách hết vai trò, nên mô tả và xử lý ra sao?

### Gợi ý trả lời

1. Tài khoản tách giúp phân biệt mục đích và phiên; độc lập cần chủ thể khác có trách nhiệm theo yêu cầu.
2. Họ có thể đồng thời quản trị host, storage, backup hoặc quyền cấp vai trò.
3. Có thể, theo nhu cầu và phạm vi; điều đó khác quyền sửa hoặc xóa hồ sơ bằng chứng trung tâm.
4. Đọc, tìm kiếm, xem nội dung nhạy cảm, xuất, sửa cấu hình, thay retention, xóa và cấp quyền.
5. Vô hiệu hóa hoặc hủy khóa có thể làm bằng chứng không còn đọc được.
6. Không. Cần kiểm tra nguồn, truyền, thu nhận và đối soát.
7. Không. Đó là những khả năng khác nhau cần thẩm quyền riêng.
8. Ghi rõ giới hạn, giảm quyền thường trực và dùng biện pháp bù có thể kiểm chứng; không giả định đã độc lập hoàn toàn.

## Kết luận

Tách audit/admin cần dựa trên khả năng thực tế: ai thực hiện hoạt động đặc quyền, ai kiểm tra và ai có thể thay đổi hoặc làm mất bằng chứng. Tên vai trò chỉ là bước đầu; ranh giới phải bao phủ IAM, PAM, nguồn log, lưu trữ, backup và khóa.

Khi kết hợp với tiering, least privilege, JIT, phê duyệt và bằng chứng được bảo vệ, việc phân tách giúp tổ chức kiểm tra hoạt động đặc quyền mà không đặt toàn bộ niềm tin vào chính người đang được kiểm tra. Những giới hạn còn lại phải được ghi rõ và xử lý theo trách nhiệm cụ thể.

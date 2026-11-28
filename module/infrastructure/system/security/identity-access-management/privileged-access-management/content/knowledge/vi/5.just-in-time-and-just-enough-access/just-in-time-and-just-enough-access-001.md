# Provision quyền ngay trước tác vụ

## 1. Provision quyền ngay trước tác vụ nghĩa là gì?

Trong PAM — Privileged Access Management, **provision quyền ngay trước tác vụ** là thiết lập hoặc kích hoạt đặc quyền khi chủ thể đã sẵn sàng thực hiện một công việc hợp lệ, thay vì duy trì quyền đó liên tục từ trước.

Đây là một cách thực hiện **JIT — just-in-time access**. Tài khoản của người dùng có thể đã tồn tại lâu dài, nhưng role quản trị, credential nhạy cảm hoặc khả năng mở phiên chỉ được cung cấp trong cửa sổ cần thiết.

Ví dụ, một kỹ sư thường chỉ có quyền theo dõi trạng thái ứng dụng. Khi cần khởi động lại một dịch vụ production theo yêu cầu xử lý sự cố, hệ thống đánh giá điều kiện, cấp khả năng thực hiện tác vụ trên đúng dịch vụ, xác nhận quyền đã có hiệu lực rồi mới cho bắt đầu. Đặc quyền được thu hồi sau khi hoàn thành hoặc khi đến hạn.

Mục tiêu là giảm **standing privilege — đặc quyền thường trực** và thu hẹp khoảng thời gian có thể lạm dụng quyền. Tuy nhiên, thời gian ngắn chưa đủ: quyền còn phải giới hạn theo tài nguyên, hành động, dữ liệu và khả năng cấp thêm quyền.

### Phân biệt JIT và JEA

- **JIT** trả lời: khi nào chủ thể được sử dụng đặc quyền, trong bao lâu và với điều kiện nào?
- **JEA — just-enough administration** trả lời: chủ thể được làm đúng những việc gì trên phạm vi nào?

Nếu cấp role quản trị toàn hệ thống trong năm phút cho một tác vụ chỉ cần xem trạng thái, thời gian có ngắn nhưng phạm vi quyền vẫn quá rộng. Provision đúng lúc nên đi cùng provision đúng mức.

## 2. Phê duyệt, provision và quyền có hiệu lực là những việc khác nhau

Một yêu cầu được duyệt chưa có nghĩa quyền đã được cấp; một API báo nhận yêu cầu cũng chưa chắc quyền đã sử dụng được tại đích.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Eligibility — đủ điều kiện yêu cầu | Chủ thể nằm trong phạm vi có thể đề nghị nhận quyền | Kỹ sư thuộc nhóm được phép yêu cầu vai trò vận hành ứng dụng |
| Yêu cầu truy cập | Mô tả nhiệm vụ, tài nguyên, hành động và thời gian cần quyền | Yêu cầu khởi động lại dịch vụ thanh toán |
| Phê duyệt hoặc quyết định policy | Chấp thuận yêu cầu trong các điều kiện xác định | Được thực hiện trong cửa sổ bảo trì đã thống nhất |
| Provision | Tạo hoặc thay đổi trạng thái cấp quyền | Tạo role assignment, thêm quyền tạm thời, cấp credential phù hợp |
| Quyền có hiệu lực | Điểm thực thi đã nhận biết và áp dụng quyền | Hệ thống đích chấp nhận tác vụ hợp lệ trong phạm vi đã cấp |
| Bắt đầu tác vụ | Người hoặc workload thực hiện công việc được giao | Gửi thao tác khởi động lại dịch vụ |
| Thu hồi | Loại bỏ hoặc chấm dứt các khả năng được cấp | Gỡ grant, dừng phiên hoặc xử lý token theo cơ chế của đích |

Có thể duyệt trước một nhiệm vụ diễn ra buổi chiều mà chưa cấp quyền ngay từ buổi sáng. Khi chủ thể chuẩn bị bắt đầu, hệ thống kiểm tra lại các điều kiện còn hiệu lực rồi mới provision.

Khoảng cách cần giảm là khoảng từ **quyền thực sự được cấp** đến **thời điểm cần sử dụng**, chứ không phải chỉ làm thao tác phê duyệt nhanh hơn.

### Một yêu cầu cũ không phải căn cứ vô hạn

Giữa lúc phê duyệt và lúc cấp quyền, người dùng có thể đổi nhiệm vụ, thiết bị mất điều kiện tin cậy hoặc tài nguyên thay đổi chủ sở hữu. Cần kiểm tra lại thông tin có thể thay đổi tại thời điểm cấp và thời điểm bắt đầu sử dụng theo mức rủi ro.

Nếu phạm vi tác vụ thay đổi, không nên dùng lại một quyết định phê duyệt cho yêu cầu khác mà không đánh giá tương ứng.

## 3. Xác định một đơn vị cấp quyền tạm thời

Một lần provision cần có đối tượng quản lý rõ ràng. Có thể gọi đó là **grant** hoặc **lease truy cập**: bản ghi liên kết một lần cấp quyền với chủ thể, tài nguyên, phạm vi và thời hạn cụ thể.

Tối thiểu cần biết:

- Chủ thể là người nào hoặc workload nào.
- Principal thực sự được nhận quyền.
- Tài nguyên đích và môi trường.
- Tác vụ hoặc role được chấp thuận.
- Điều kiện cấp và sử dụng.
- Thời điểm bắt đầu được phép cấp.
- Hạn kết thúc cố định cho lần cấp.
- Mã yêu cầu, quyết định phê duyệt và phiên liên quan.
- Những thay đổi đã tạo tại hệ thống đích.
- Cách thu hồi và cách kiểm chứng kết quả.

Không nên chỉ ghi “đã bật admin cho người A”. Mô tả đó không đủ để biết quyền nào phải gỡ, có ảnh hưởng đến yêu cầu khác hay không và còn bao nhiêu khả năng truy cập sau khi kết thúc.

Ví dụ bản ghi khái niệm:

```json
{
  "leaseRef": "lease-581",
  "requestRef": "incident-581",
  "subjectRef": "person-028",
  "principalRef": "idp:operator-028",
  "resourceRef": "payments-production-service-a",
  "allowedTasks": [
    "read-service-status",
    "restart-designated-service"
  ],
  "approvedWindowStart": "2026-12-02T14:00:00Z",
  "approvedWindowEnd": "2026-12-02T14:30:00Z",
  "expiresAt": "2026-12-02T14:18:00Z",
  "grantRef": "target-assignment-reference",
  "state": "PROVISIONING"
}
```

Đây là ví dụ dữ liệu minh họa, không phải schema hoặc cấu hình của một sản phẩm. Danh sách tác vụ phải được ánh xạ sang cơ chế cấp quyền thực tế; trường `expiresAt` trong hồ sơ không tự khiến quyền tại hệ thống đích hết hiệu lực.

Không ghi mật khẩu, token hoặc khóa riêng vào hồ sơ cấp quyền.

## 4. Một luồng provision ngay trước tác vụ

### Bước 1: Diễn đạt nhu cầu thành tác vụ có phạm vi

Yêu cầu cần mô tả đủ rõ để quyết định quyền tối thiểu:

- Làm gì: xem trạng thái, khởi động lại, thay một cấu hình hay thực hiện bảo trì?
- Ở đâu: tài nguyên cụ thể, nhóm tài nguyên, tenant hoặc môi trường nào?
- Khi nào: cửa sổ được phép và thời lượng cần thiết?
- Ai: danh tính cá nhân hoặc workload thực hiện?
- Vì sao: nhiệm vụ, yêu cầu thay đổi hoặc sự cố liên quan?
- Có thể hoàn tất bằng tác vụ hạn chế hay cần một ngữ cảnh rộng hơn?

“Cần quyền quản trị production” thường quá rộng. “Khởi động lại dịch vụ A thuộc ứng dụng thanh toán trong cửa sổ xử lý sự cố” giúp xây dựng grant rõ hơn.

Đối với JEA, tham số cũng là một phần của phạm vi. Quyền khởi động lại dịch vụ đã chỉ định khác với quyền chạy một lệnh tùy ý kèm đường dẫn hoặc script do người dùng cung cấp.

### Bước 2: Đánh giá điều kiện và quyết định cấp

Tùy rủi ro, hệ thống xem xét eligibility, nhiệm vụ, tài nguyên, thời hạn, nguồn truy cập, xác thực và phê duyệt độc lập.

Không phải tác vụ nào cũng cần người duyệt thủ công. Có thể tự động chấp thuận tác vụ đã được policy cho phép, miễn là điều kiện được thực thi và có bằng chứng. Với tác vụ nhạy cảm, cần tránh việc một người tự mở rộng phạm vi, tự phê duyệt rồi tự xóa dấu vết.

### Bước 3: Chờ chủ thể sẵn sàng, chưa kích hoạt sớm

Nếu yêu cầu được duyệt trước, giữ ở trạng thái chờ. Khi người hoặc workload chuẩn bị thực hiện, kiểm tra lại điều kiện và hạn phê duyệt.

Nếu nhiệm vụ bị hủy hoặc người dùng không bắt đầu, hệ thống không nên tự duy trì một đặc quyền đã cấp từ nhiều giờ trước chỉ vì yêu cầu từng được duyệt.

### Bước 4: Tạo hồ sơ cấp và cơ chế kết thúc

Trước hoặc trong quá trình cấp, cần ghi nhận bền vững lease, phạm vi, hạn kết thúc và cách tìm lại grant tại đích. Cơ chế theo dõi thu hồi không nên chỉ nằm trong bộ nhớ của một tiến trình đang chạy.

Nếu đích hỗ trợ hết hạn quyền tại chỗ, nên tận dụng theo thiết kế phù hợp. Nếu cần bộ điều phối gỡ quyền, phải có cơ chế bền vững và đối soát để không bỏ quên khi tiến trình lỗi.

Không nên giả định việc ghi hồ sơ và thay quyền ở một hệ thống khác luôn nằm trong cùng một giao dịch nguyên tử. Thiết kế cần xử lý trạng thái một phía đã thành công còn phía kia chưa xác nhận.

### Bước 5: Provision tại hệ thống thực thi

Hệ thống thực hiện thay đổi cần thiết, chẳng hạn tạo một role assignment có hạn hoặc cấp credential ngắn hạn đúng phạm vi.

Thành phần provision có đặc quyền nhạy cảm vì nó có thể cấp quyền cho người khác. Quyền của thành phần này cũng phải giới hạn theo miền tài nguyên và loại grant được quản lý; không tin trực tiếp mọi role hoặc đường dẫn do người yêu cầu gửi lên.

### Bước 6: Xác nhận quyền hiệu lực trước khi bắt đầu

Cần xác nhận grant đã được áp dụng trên đúng principal, tài nguyên và phạm vi. Với hệ thống có độ trễ lan truyền, có thể phải chờ trước khi cho phép tác vụ.

Việc xác nhận cần dùng phương thức phù hợp, chẳng hạn kiểm tra trạng thái grant hoặc một phép kiểm tra quyền không làm thay đổi dữ liệu. Không nên thực hiện thao tác phá hoại chỉ để thử xem quyền đã có hay chưa.

Nếu chưa xác minh được, không nên thông báo “đã sẵn sàng” hoặc cho chạy tác vụ bằng một quyền quản trị dự phòng rộng hơn.

### Bước 7: Thực hiện và theo dõi

Chủ thể sử dụng quyền qua đường đã xác định. Ghi nhận mã yêu cầu, lease, phiên, principal và sự kiện tại đích. Theo dõi các hành động ngoài phạm vi hoặc việc thay đổi điều kiện truy cập.

### Bước 8: Thu hồi sớm khi xong hoặc khi đến hạn

Tác vụ hoàn tất, bị hủy, có dấu hiệu sự cố hoặc hết hạn đều có thể là lý do kết thúc quyền. Không cần giữ quyền đến hết thời lượng tối đa khi công việc đã hoàn thành.

Thu hồi cần bao quát đúng grant, credential, token và phiên liên quan. Sau đó xác nhận trạng thái thực tế theo mục tiêu đã công bố.

## 5. Minh họa thời gian: duyệt trước, cấp sát lúc làm

Giả sử một công việc được duyệt buổi sáng nhưng chỉ được thực hiện trong cửa sổ buổi chiều. Các mốc dưới đây là ví dụ, không phải số liệu vận hành thực tế.

| Mốc | Sự kiện | Trạng thái quyền |
|---|---|---|
| 09:00 | Người vận hành gửi yêu cầu | Chưa có đặc quyền cho tác vụ |
| 09:02 | Yêu cầu được duyệt cho cửa sổ 14:00–14:30 | Được phép yêu cầu kích hoạt trong điều kiện đã duyệt |
| 14:03:00 | Người vận hành sẵn sàng; hệ thống đánh giá lại và đặt hạn 14:18:00 | Bắt đầu quy trình cấp, chưa thông báo sẵn sàng |
| 14:03:05 | Grant có hiệu lực tại đích trong ví dụ | Đặc quyền tồn tại đến hạn đã đặt |
| 14:03:10 | Xác minh grant đúng phạm vi | Có thể bắt đầu tác vụ |
| 14:03:12 | Tác vụ bắt đầu | Sử dụng đặc quyền đã cấp |
| 14:08:00 | Tác vụ hoàn thành | Khởi động thu hồi sớm và xác minh kết quả |
| 14:18:00 | Hạn tối đa của lần cấp nếu chưa kết thúc sớm | Cơ chế hết hạn hoặc thu hồi phải xử lý theo thiết kế |

Ví dụ này đặt hạn kết thúc trước khi provision, nên độ trễ cấp không làm hạn tự lùi về sau. Nếu lần cấp được thử lại, không tự tạo thêm một cửa sổ đầy đủ tính từ lần thử mới.

Một cách biểu diễn hạn của lần cấp là:

```text
Hạn kết thúc =
    thời điểm sớm nhất trong:
        - Hạn của lần kích hoạt theo policy
        - Kết thúc cửa sổ công việc đã được duyệt
        - Hạn hợp lệ của chủ thể hoặc nhiệm vụ
```

Đây là cách diễn đạt policy, không phải công thức bảo đảm mọi phiên đã ngừng ở thời điểm đó. Khả năng thực thi phụ thuộc role, token, phiên và cơ chế thu hồi tại đích.

Nếu đến sát hạn mà chưa xác minh quyền xong, có thể hủy lần cấp hoặc yêu cầu đánh giá lại. Không nên âm thầm kéo dài để bù độ trễ.

## 6. Những cách provision thường gặp và giới hạn của chúng

| Cơ chế | Quyền hoặc khả năng được tạo | Điều cần kiểm tra |
|---|---|---|
| Role assignment tạm thời | Quyền cho một principal trên tài nguyên | Phạm vi, thời điểm có hiệu lực, khả năng hết hạn và gỡ quyền |
| Thành viên nhóm tạm thời | Quyền được thừa hưởng từ nhóm | Nhóm lồng nhau, độ trễ và cách phiên hoặc token nhận quyền |
| Tài khoản hoặc credential cấp động | Danh tính hoặc phương tiện truy cập phục vụ nhiệm vụ | Quyền của tài khoản, hạn credential, phụ thuộc và cách dừng phiên |
| Token ngắn hạn | Khả năng gọi API trong phạm vi token | Audience, phạm vi, khả năng thu hồi và những quyền có thể cấp tiếp |
| Mở phiên qua PAM | Một phiên có quyền trên tài khoản đích | Role của tài khoản đích, đường truy cập khác và khả năng kết thúc phiên |
| Mở đường kết nối tạm thời | Khả năng tiếp cận giao diện quản trị | Đây là quyền kết nối; vẫn cần quản lý danh tính và đặc quyền tại đích |

Nếu PAM chỉ cho mở phiên đến một tài khoản quản trị luôn tồn tại, đặc quyền tại tài khoản đích vẫn thường trực. Cơ chế đó có thể làm quyền **sử dụng** đặc quyền của người vận hành trở nên tạm thời, nhưng không nên tuyên bố đã loại bỏ mọi đặc quyền thường trực của hệ thống.

Tương tự, mở cổng mạng trong 15 phút không tự giới hạn người dùng chỉ được khởi động lại một dịch vụ. Phân quyền tại đích và JEA vẫn cần được thiết kế.

## 7. Phạm vi cấp phải giữ nguyên từ phê duyệt đến thực thi

Một yêu cầu không nên được phê duyệt cho tài nguyên A rồi bị thay thành tài nguyên B trước lúc provision mà vẫn dùng quyết định cũ.

Cần liên kết quyết định với những thuộc tính quan trọng:

- Chủ thể và principal nhận quyền.
- Tài nguyên hoặc nhóm tài nguyên được định danh rõ.
- Role hoặc tác vụ, bao gồm các tham số có ý nghĩa bảo mật.
- Môi trường, tenant và miền quản trị.
- Cửa sổ công việc và hạn tối đa.
- Điều kiện truy cập và cơ chế gia hạn.

Các dữ liệu có thể thay đổi cần được đánh giá lại tại điểm phù hợp. Chẳng hạn, một nhóm tài nguyên có thêm máy nhạy cảm sau khi duyệt có thể làm phạm vi thực tế rộng hơn dự kiến.

Không nên để người dùng tự gửi một tên role tùy ý rồi hệ thống cấp bằng credential quản trị của bộ điều phối. Nhu cầu nghiệp vụ cần được ánh xạ qua danh mục quyền và policy đã kiểm soát.

### Tính đến quyền đã tồn tại

Nếu người dùng đã có role quản trị rộng từ trước, việc thêm một grant tạm thời hẹp không làm quyền hiệu lực trở nên hẹp. Quyền cuối cùng có thể là tổng hợp của nhiều nguồn cấp.

Trước khi tuyên bố một phiên chỉ có quyền theo tác vụ, cần xem xét quyền nền, nhóm, role khác và khả năng chuyển danh tính. Thu hồi grant của yêu cầu hiện tại cũng không tự xóa những nguồn quyền độc lập đó.

## 8. Độ trễ, thử lại và trạng thái chưa xác định

Provision đặc quyền là thao tác thay đổi trạng thái nhạy cảm. Nó có thể thất bại từng phần hoặc có kết quả chưa biết nếu kết nối bị ngắt.

### 8.1. API timeout không đồng nghĩa chưa cấp quyền

Bộ điều phối có thể không nhận được phản hồi dù hệ thống đích đã tạo grant. Nếu cứ tạo lại, có thể sinh nhiều grant, kéo dài quyền hoặc làm khó thu hồi.

Cần có cách liên kết một yêu cầu với kết quả tại đích, chẳng hạn định danh thao tác hoặc cơ chế chống tạo trùng khi nền tảng hỗ trợ. Khi chưa biết kết quả, phải đối soát trước khi coi lần cấp thất bại sạch sẽ hoặc thử tạo một quyền mới.

### 8.2. Thử lại không tự kéo dài quyền

Cùng một lần cấp cần giữ phạm vi và hạn kết thúc đã quyết định. Nếu cần thời gian mới, đó là một thay đổi phải được đánh giá theo policy, không phải hệ quả ngầm của thao tác thử lại.

### 8.3. Grant đã tạo nhưng chưa xác minh được

Đây là trạng thái có thể đã có đặc quyền ở đích dù giao diện chưa báo sẵn sàng. Cần tiếp tục đối soát hoặc thu hồi theo thời hạn, thay vì bỏ qua vì người dùng chưa bắt đầu tác vụ.

### 8.4. Thu hồi thất bại phải được theo dõi đến kết quả

Không nên chuyển trạng thái sang “đã thu hồi” chỉ vì đã gửi yêu cầu gỡ role. Cần ghi nhận phản hồi và xác minh theo khả năng hệ thống.

Một trạng thái tham khảo:

```text
APPROVED_WAITING
    -> PROVISIONING
    -> VERIFYING
    -> ACTIVE
    -> REVOKING
    -> REVOKED

Nếu kết quả cấp chưa biết:
    PROVISIONING / VERIFYING -> RECONCILING
        -> Xác nhận grant và tiếp tục nếu còn hợp lệ
        -> Hoặc xử lý thu hồi theo policy

Nếu thu hồi chưa hoàn tất:
    REVOKING -> REVOKE_PENDING
        -> Đối soát, thử lại có kiểm soát và xử lý theo mức rủi ro
```

Các trạng thái này là mô hình minh họa. Trạng thái cuối phải có nghĩa rõ ràng về grant, phiên và token đã được xử lý đến đâu.

## 9. Thiết kế thu hồi cùng lúc với thiết kế cấp quyền

Không nên đợi đến cuối mới hỏi “gỡ quyền bằng cách nào”. Trước khi provision, cần biết:

- Grant nào thuộc lần cấp này.
- Khi nào phải kết thúc.
- Hệ thống đích có cơ chế hết hạn tại chỗ không.
- Ai hoặc thành phần nào thực hiện thu hồi.
- Cách xử lý nếu bộ điều phối dừng hoạt động.
- Cách xử lý phiên, token và credential phát sinh.
- Cách xác nhận kết quả.
- Cách bảo toàn khả năng phục hồi khi có lỗi.

Nếu nhiều yêu cầu cùng liên quan một principal và role, phải biết lần cấp nào sở hữu thay đổi nào. Không nên gỡ toàn bộ thành viên của một nhóm hoặc xóa quyền hợp lệ của nhiệm vụ khác chỉ để kết thúc một lease.

Nếu đích không hỗ trợ grant độc lập cho từng lần cấp, cần có cơ chế quản lý quyền chồng lấn được thiết kế rõ. Không nên dùng một cờ “đang bật” rồi coi như có thể phân biệt đầy đủ mọi nhiệm vụ và thời hạn.

### Phân biệt kết thúc quyền và kết thúc mọi hoạt động

Một số hệ thống chỉ kiểm tra quyền khi tạo phiên; hệ thống khác kiểm tra ở từng yêu cầu. Token cũng có thể có thời hạn và cơ chế xác nhận riêng.

Vì vậy:

- Gỡ role có thể ngăn yêu cầu mới nhưng chưa chắc chấm dứt phiên đang chạy.
- Mật khẩu hết hiệu lực chưa chắc vô hiệu hóa token đã phát hành.
- Dừng phiên tương tác chưa chắc dừng tác vụ nền đã được khởi chạy.
- Thu hồi không đảo ngược dữ liệu đã bị đọc, xuất hoặc thay đổi.

Mục tiêu phải được mô tả theo cơ chế thực tế. Nếu hệ thống không thể dừng ngay một loại phiên hoặc token, cần ghi nhận phần quyền còn tồn tại và giới hạn tương ứng.

## 10. Áp dụng cho con người và workload

### 10.1. Con người thực hiện công việc quản trị

Cần liên kết yêu cầu với danh tính cá nhân, nhiệm vụ, điều kiện xác thực và phiên. Thời điểm sẵn sàng có thể là khi người dùng chọn bắt đầu công việc và đáp ứng điều kiện.

Môi trường quản trị cũng quan trọng. Cấp quyền ngắn hạn không bảo vệ được credential hoặc phiên nếu chúng được đưa vào một máy đã bị chiếm dụng.

### 10.2. Workload hoặc pipeline tự động hóa

Workload không có người nhập MFA cho từng lần chạy. Cần dùng cơ chế xác thực danh tính workload và điều kiện thực thi phù hợp thay vì sao chép luồng của con người.

Một pipeline có thể nhận credential hoặc role đúng phạm vi ngay trước bước triển khai. Cần liên kết grant với lần chạy, môi trường, tài nguyên và nhiệm vụ; hạn chế việc một workload có thể tự xin mọi quyền.

Sự kiện kết thúc pipeline là một tín hiệu để thu hồi, nhưng không nên là cơ chế duy nhất. Nếu tiến trình bị hủy hoặc hệ thống chạy pipeline lỗi, quyền vẫn cần có hạn và cơ chế đối soát.

### 10.3. Tránh dùng token cá nhân làm quyền tự động hóa lâu dài

Nếu một tác vụ chạy nền dùng token của nhân viên, việc cấp và thu hồi quyền có thể bị gắn sai với vòng đời con người. Nên xem xét danh tính riêng cho workload và cấp quyền theo từng lần chạy khi nền tảng hỗ trợ.

Không tự động cấp lại quyền chỉ vì lần chạy trước từng có quyền. Mỗi lần cần quyền phải đáp ứng điều kiện tương ứng.

## 11. Các tình huống thay đổi trong lúc chờ hoặc đang chạy

| Tình huống | Cách xử lý cần thiết kế |
|---|---|
| Người dùng không bắt đầu sau khi được duyệt | Giữ quyền chưa provision hoặc kết thúc lần cấp chưa dùng theo policy |
| Nhiệm vụ bị hủy trước lúc cấp | Không tạo grant; nếu đã bắt đầu cấp thì đối soát và xử lý phần đã tạo |
| Người dùng đổi nhóm hoặc hết hợp đồng | Đánh giá lại eligibility, ngăn kích hoạt mới và xử lý quyền đang tồn tại |
| Tài nguyên hoặc phạm vi thay đổi | Đánh giá lại quyết định và giới hạn đã duyệt |
| Tác vụ hoàn thành sớm | Thu hồi sớm, không chờ hết thời lượng tối đa |
| Tác vụ cần thêm thời gian | Yêu cầu gia hạn hoặc lần cấp mới theo policy; không tự gia hạn vô hạn |
| Phát hiện hành vi nghi vấn | Khoanh vùng và thu hồi theo mức rủi ro, đồng thời bảo toàn bằng chứng |
| PAM hoặc bộ điều phối gặp lỗi | Không tự mở đặc quyền rộng; áp dụng cơ chế hết hạn, đối soát và phục hồi đã thiết kế |

Truy cập khẩn cấp có thể cần luồng riêng để bảo đảm khả năng phục hồi. Luồng đó vẫn cần danh tính, phạm vi, điều kiện sử dụng, thời hạn và xem xét sau sử dụng. Không nên biến mọi lỗi của cơ chế JIT thành lý do cấp quản trị thường trực không được theo dõi.

## 12. Bằng chứng cần giữ cho một lần provision

Một chuỗi bằng chứng hữu ích phải trả lời được cả quyền **được yêu cầu**, quyền **được quyết định** và quyền **thực sự tồn tại**.

| Mốc | Thông tin nên liên kết |
|---|---|
| Gửi yêu cầu | Chủ thể, principal, tác vụ, tài nguyên, thời gian và lý do |
| Quyết định | Policy hoặc người phê duyệt, phạm vi được chấp thuận |
| Sẵn sàng bắt đầu | Điều kiện được kiểm tra lại và thời điểm |
| Provision | Lease, grant tại đích, loại thay đổi, hạn kết thúc |
| Xác minh | Kết quả quyền có hiệu lực, độ trễ hoặc lỗi chưa giải quyết |
| Sử dụng | Phiên hoặc lần chạy, thao tác, tài nguyên và kết quả |
| Kết thúc | Lý do thu hồi, trạng thái grant, credential, token và phiên |
| Đối soát | Các trạng thái lệch, thao tác thử lại và kết quả cuối |

Không ghi giá trị bí mật vào log. Bản ghi phiên hoặc kết quả thao tác có thể chứa dữ liệu nhạy cảm nên cũng cần giới hạn người xem và bảo vệ khỏi sửa, xóa trái phép.

Các chỉ số hữu ích gồm thời gian từ lúc sẵn sàng đến lúc quyền có hiệu lực, thời gian quyền tồn tại trước tác vụ, số grant chưa thu hồi được, số lần cấp không dùng và mức độ quyền vượt nhiệm vụ. Không nên chỉ đo tốc độ cấp quyền mà bỏ qua thời gian quyền còn tồn tại sau khi công việc kết thúc.

## 13. Ví dụ tổng hợp: khởi động lại dịch vụ production

Một kỹ sư cần khởi động lại dịch vụ thanh toán A để xử lý lỗi đã xác định.

### Phạm vi mong muốn

- Chỉ dịch vụ A trong môi trường production được giao.
- Chỉ xem trạng thái và khởi động lại theo cơ chế tác vụ phù hợp.
- Không cấp shell quản trị tùy ý, quyền đọc mọi secret hoặc quyền sửa hệ thống nhận dạng.
- Quyền được cấp khi kỹ sư sẵn sàng bắt đầu và đáp ứng điều kiện.
- Hạn kết thúc cố định; hoàn thành sớm thì thu hồi sớm.
- Có liên kết giữa yêu cầu, danh tính, grant, phiên và sự kiện tại dịch vụ.

### Một luồng xử lý có thể diễn đạt bằng mã giả

```text
nhan_yeu_cau(nguoi, tac_vu, tai_nguyen):
    xac_dinh_pham_vi_theo_policy()
    danh_gia_va_luu_quyet_dinh()
    giu_trang_thai_cho_neu_chua_bat_dau()

khi_chu_the_san_sang(yeu_cau):
    kiem_tra_lai_dieu_kien_va_pham_vi()
    an_dinh_han_ket_thuc_khong_tu_keo_dai_khi_thu_lai()
    luu_lease_va_thong_tin_doi_soat_ben_vung()
    provision_dung_quyen_tai_dich()
    xac_minh_quyen_da_co_hieu_luc()
    chi_thong_bao_san_sang_khi_xac_minh_dat()

khi_hoan_thanh_het_han_hoac_bi_huy(lease):
    thu_hoi_dung_nhung_thay_doi_thuoc_lease()
    xu_ly_phien_token_credential_theo_co_che_cua_dich()
    xac_minh_hoac_giu_trang_thai_cho_xu_ly()
    luu_ket_qua_khong_chua_bi_mat()
```

Đây là mã giả giải thích trách nhiệm, không phải chương trình có thể chạy hoặc thiết kế giao dịch đầy đủ.

### Các giới hạn cần ghi nhận

Ngay cả quyền khởi động lại đúng dịch vụ cũng có thể gây gián đoạn. Cần có điều kiện vận hành, khả năng chịu lỗi và phương án phục hồi của ứng dụng.

Nếu cơ chế tác vụ thực chất cho phép chạy script tùy ý với quyền cao, phạm vi mong muốn chưa được thực thi. Nếu phiên tiếp tục sống sau khi grant hết hạn, mục tiêu kết thúc truy cập cần được điều chỉnh hoặc bổ sung kiểm soát.

## 14. Kiểm chứng trước khi coi luồng đã đáp ứng mục tiêu

Trong môi trường hoặc đợt diễn tập được cho phép, có thể đánh giá:

| Tình huống | Kết quả mong đợi |
|---|---|
| Yêu cầu đã duyệt nhưng chủ thể chưa sẵn sàng | Chưa có đặc quyền sử dụng cho tác vụ |
| Chủ thể bắt đầu với đúng điều kiện | Grant đúng phạm vi được tạo và xác minh trước tác vụ |
| Thay tài nguyên hoặc role sau khi duyệt | Không được dùng quyết định cũ để mở rộng quyền |
| Provision có độ trễ | Không báo sẵn sàng trước khi xác nhận quyền hiệu lực |
| API timeout sau khi đã có thể tạo grant | Có đối soát, không tạo trùng hoặc tự kéo dài hạn |
| Tác vụ hoàn thành sớm | Quy trình thu hồi được kích hoạt và theo dõi |
| Bộ điều phối khởi động lại | Lease và nghĩa vụ thu hồi không bị mất |
| Gỡ role nhưng phiên hoặc token còn hoạt động | Phát hiện phần còn tồn tại và xử lý theo mục tiêu đã công bố |
| Có hai yêu cầu chồng lấn | Thu hồi một lease không xóa quyền hợp lệ không thuộc lease đó |
| Người dùng có quyền quản trị từ nguồn khác | Không tuyên bố quyền hiệu lực chỉ còn phạm vi JIT khi chưa xử lý nguồn đó |

Đây là gợi ý kiểm chứng cho người học, không phải tuyên bố đã thực hiện kiểm thử trên một hệ thống thực tế.

## 15. Những lỗi thường gặp

- Cấp quyền ngay khi phê duyệt dù công việc còn nhiều giờ mới bắt đầu.
- Chỉ giới hạn thời gian mà vẫn cấp role quá rộng.
- Coi thông báo nhận yêu cầu provision là bằng chứng quyền đã có hiệu lực.
- Chỉ lưu hạn kết thúc trong giao diện mà không có cơ chế thực thi hoặc thu hồi.
- Đặt lịch gỡ quyền trong bộ nhớ của một tiến trình duy nhất.
- Tạo grant mới mỗi lần timeout mà không đối soát trạng thái cũ.
- Đặt lại toàn bộ thời hạn sau mỗi lần thử lại.
- Gỡ role rồi kết luận mọi phiên và token đã mất hiệu lực.
- Quên xử lý quyền nền hoặc role được cấp từ nguồn khác.
- Tự gia hạn khi tác vụ chưa xong mà không đánh giá lại.
- Cho bộ điều phối cấp mọi role theo dữ liệu người dùng gửi lên.
- Xử lý lỗi JIT bằng cách mở quyền quản trị thường trực không có giới hạn.

## 16. Tình huống tự luyện

Một nhóm đã xây dựng cổng yêu cầu JIT. Sau khi được duyệt, người dùng được thêm vào nhóm quản trị trong 30 phút. Thực tế:

- Quyền được thêm ngay lúc duyệt, dù người dùng bắt đầu sau đó 20 phút.
- Giao diện báo thành công khi gửi yêu cầu, chưa kiểm tra nhóm có hiệu lực.
- Mỗi lần thử lại đều đặt lại bộ đếm 30 phút.
- Lịch gỡ nhóm chỉ nằm trong bộ nhớ của máy chạy cổng.
- Phiên quản trị có thể tiếp tục sau khi gỡ nhóm.
- Một số người vẫn có quyền tương đương qua nhóm khác.

Hãy phân tích:

1. Khoảng nào là thời gian đặc quyền tồn tại nhưng chưa cần dùng?
2. Vì sao đây chưa phải luồng provision sát lúc thực hiện tác vụ?
3. Cần phân biệt những trạng thái nào giữa duyệt, cấp, xác minh và sử dụng?
4. Làm sao giữ hạn kết thúc không bị kéo dài do thử lại?
5. Những thông tin nào phải lưu bền vững để có thể thu hồi sau khi hệ thống lỗi?
6. Cần xử lý quyền nền và phiên còn hoạt động như thế nào?
7. Bằng chứng nào đủ cho thấy một lần cấp đã kết thúc theo mục tiêu?

Gợi ý: thiết kế lại từ một lease có phạm vi và hạn rõ ràng, chỉ kích hoạt khi sẵn sàng, xác minh ở điểm thực thi và theo dõi nghĩa vụ thu hồi đến kết quả.

## 17. Ghi nhớ

Provision quyền ngay trước tác vụ là cấp đặc quyền khi có nhu cầu thực tế và chủ thể đã đáp ứng điều kiện, với phạm vi đủ dùng và hạn kết thúc rõ ràng. Phê duyệt trước không buộc phải cấp quyền trước.

Một luồng đáng tin cậy phải liên kết được yêu cầu, quyết định, grant tại đích, quyền hiệu lực, phiên sử dụng và kết quả thu hồi. JIT giảm thời gian có quyền; JEA và least privilege giảm khả năng tác động; đối soát, bằng chứng và cơ chế kết thúc giúp các giới hạn đó được duy trì cả khi có lỗi.

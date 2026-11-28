# Identity retention

## 1. Identity retention là gì?

**Identity retention** là việc xác định và thực thi thời gian lưu giữ dữ liệu liên quan đến danh tính: dữ liệu nào cần giữ, cho mục đích nào, tính thời hạn từ đâu, ai được sử dụng và điều gì phải xảy ra khi thời hạn kết thúc.

Trong IAM, dữ liệu danh tính không chỉ nằm trong bảng tài khoản. Nó còn có ở thuộc tính hồ sơ, liên kết danh tính bên ngoài, membership, quyền được cấp, credential, phiên, thiết bị, log kiểm toán, bản sao đồng bộ và bản sao lưu.

Một chính sách tốt phải đáp ứng đồng thời hai nhu cầu: giữ dữ liệu cần thiết cho hoạt động và truy vết đã được xác định, đồng thời không tích lũy hồ sơ danh tính vô hạn chỉ vì hệ thống có khả năng lưu trữ.

Ví dụ, khi một nhân viên rời tổ chức, hệ thống cần ngăn truy cập theo quy trình offboarding. Một số bằng chứng về hoạt động quản trị trước đó có thể vẫn cần được lưu theo chính sách riêng. Điều này không có nghĩa tài khoản phải tiếp tục đăng nhập được hoặc toàn bộ hồ sơ cá nhân phải được giữ cùng thời gian với log.

Retain một dữ liệu, cho phép sử dụng nó và giữ quyền truy cập của chủ thể là ba quyết định khác nhau.

## 2. Phân biệt retention với những thời hạn và trạng thái khác

| Khái niệm | Ý nghĩa | Không nên suy diễn thành |
|---|---|---|
| Account disabled | Tài khoản bị ngăn thực hiện một số hoạt động theo cơ chế hệ thống | Mọi bản sao dữ liệu và mọi credential đã biến mất |
| Deprovisioning | Gỡ hoặc vô hiệu hóa tài khoản, quyền và tài nguyên liên quan ở hệ thống đích | Toàn bộ log và backup đã được xóa |
| Token lifetime | Khoảng thời gian token có thể được chấp nhận theo hợp đồng và điều kiện kiểm tra | Thời gian cần giữ toàn bộ hồ sơ người dùng |
| Session timeout | Thời gian hoặc điều kiện kết thúc phiên | Chính sách xóa log xác thực |
| Data freshness | Dữ liệu còn đủ mới cho quyết định cần thực hiện không | Dữ liệu đã hết nhu cầu lưu giữ hay chưa |
| Retention period | Khoảng thời gian giữ một loại dữ liệu theo mục đích đã xác định | Quyền tự do sử dụng dữ liệu cho mọi mục đích |
| Deletion hoặc anonymization | Xóa hoặc biến đổi dữ liệu theo một phương pháp và phạm vi cụ thể | Đã xử lý mọi bản sao chỉ vì bảng chính không còn một dòng |

Một claim quyền hạn có thể quá cũ để dùng cho authorization dù bản ghi audit về claim đó vẫn còn trong thời gian cần lưu. Ngược lại, một tài khoản đang hoạt động không có nghĩa mọi thuộc tính từng thu thập đều phải được giữ mãi.

Không chờ hết thời hạn lưu hồ sơ mới thu hồi quyền. Thu hồi quyền phải đi theo trạng thái và sự kiện bảo mật tương ứng, còn retention xử lý vòng đời dữ liệu theo từng loại.

## 3. Kiểm kê toàn bộ dữ liệu liên quan đến danh tính

Trước khi đặt thời hạn, cần biết dữ liệu ở đâu và quan hệ giữa các bản sao.

| Nhóm dữ liệu | Ví dụ | Câu hỏi về retention |
|---|---|---|
| Định danh và hồ sơ | Subject ID, tên hiển thị, email, đơn vị | Thuộc tính nào còn cần khi quan hệ sử dụng đã kết thúc? |
| Liên kết tài khoản | Mapping tới IdP khác hoặc tài khoản SaaS | Khi nào mapping không còn cần và làm sao tránh nối nhầm về sau? |
| Credential và yếu tố xác thực | Password hash, dữ liệu đăng ký MFA, khóa truy cập | Khi vô hiệu hóa hoặc xóa danh tính, loại nào phải được thu hồi hay loại bỏ? |
| Phiên và grant | Session, refresh token record, quyền ủy quyền | Cơ chế thực thi mất hiệu lực và dọn trạng thái là gì? |
| Quyền và quan hệ | Role, group, entitlement, phê duyệt | Cần giữ trạng thái hiện hành hay bằng chứng lịch sử nào? |
| Thiết bị và tín hiệu rủi ro | Đăng ký thiết bị, đánh giá đăng nhập | Mục đích, độ mới và phạm vi lưu giữ có còn hợp lý không? |
| Audit và telemetry | Sự kiện xác thực, cấp quyền, hoạt động đặc quyền | Cần mức chi tiết nào để truy vết mà không nhân bản hồ sơ? |
| Bản sao dẫn xuất | Search index, cache, kho phân tích, file xuất | Ai cập nhật hoặc xóa chúng khi nguồn thay đổi? |
| Backup và snapshot | Bản sao phục hồi, bản sao bất biến | Khi nào hết vòng đời và khôi phục có làm dữ liệu cũ xuất hiện lại không? |

Không coi dữ liệu đã băm hoặc thay tên là đã ra ngoài phạm vi quản trị. Password hash vẫn là dữ liệu cần bảo vệ. Một ID giả danh vẫn có thể liên kết với người thật qua bảng mapping hoặc các dữ liệu khác.

Kiểm kê cũng phải bao gồm tài khoản dịch vụ, workload và người chịu trách nhiệm quản lý chúng. Một workload đã ngừng sử dụng có thể để lại credential hoặc quyền vượt quá nhu cầu nếu chỉ theo dõi tài khoản con người.

## 4. Gắn thời hạn với mục đích và loại dữ liệu

Không nên dùng một thời hạn chung như “giữ mọi thứ 5 năm” cho toàn bộ IAM. Các loại dữ liệu có mục đích, độ nhạy cảm và yêu cầu vận hành khác nhau.

Với mỗi loại dữ liệu, cần xác định:

- Mục đích lưu giữ và người chịu trách nhiệm cho mục đích đó.
- Phạm vi hệ thống, tenant, chủ thể và bản sao liên quan.
- Sự kiện bắt đầu tính thời hạn.
- Khoảng lưu giữ được phê duyệt và hành động khi hết hạn.
- Những ngoại lệ có thẩm quyền, điều kiện xem xét và giới hạn của chúng.
- Cách xác minh đã thực thi, kể cả khi một hệ thống đích đang lỗi.

Các thời hạn phải được lựa chọn từ yêu cầu thực tế đã được xác định cho hệ thống. Bài học không đặt ra một mốc bắt buộc chung cho mọi tổ chức hoặc mọi loại dữ liệu.

Ví dụ, mục đích vận hành tài khoản có thể kết thúc khi quan hệ sử dụng kết thúc. Mục đích điều tra hoặc audit đối với một số sự kiện có thể còn tồn tại lâu hơn. Khi đó chỉ giữ dữ liệu cần cho mục đích còn hiệu lực, với quyền truy cập phù hợp.

Nếu không xác định được mục đích hay chủ sở hữu, trạng thái đó cần được giải quyết trong quản trị dữ liệu. Không biến “chưa quyết định” thành chính sách giữ vô hạn.

## 5. Xác định đúng điểm bắt đầu tính thời hạn

Một khoảng thời gian không đủ để triển khai nếu thiếu mốc bắt đầu.

| Loại mốc | Có thể phù hợp với | Rủi ro cần tránh |
|---|---|---|
| Thời gian sự kiện xảy ra | Log hoặc bằng chứng lịch sử | Dùng thời gian nhập lại log làm mới toàn bộ thời hạn |
| Thời gian tạo bản sao | Snapshot hoặc file xuất | Không quản lý các bản sao được sao chép tiếp |
| Kết thúc quan hệ sử dụng | Một phần hồ sơ sau offboarding | Chờ một trường trạng thái không bao giờ được cập nhật |
| Credential hết hạn hoặc bị thu hồi | Dọn trạng thái credential theo thiết kế | Nhầm hết hạn credential với hết nhu cầu audit |
| Sự kiện đóng mục đích cụ thể | Hồ sơ phê duyệt hoặc tác vụ quản trị | Không có sự kiện kết thúc rõ ràng |

Trường `updatedAt` chung không nhất thiết là mốc retention phù hợp. Một tác vụ đồng bộ chạy hằng ngày có thể cập nhật nó và khiến dữ liệu không bao giờ đến hạn xóa.

Tương tự, không nên để một lần đăng nhập thất bại từ bên ngoài tự làm mới vô hạn thời gian giữ hồ sơ của tài khoản đã ngừng hoạt động. Nếu dùng hoạt động làm căn cứ, phải định nghĩa hoạt động nào có ý nghĩa và nguồn nào được tin cậy.

Sự kiện đến muộn hoặc bị sửa cần được xử lý theo quy tắc rõ ràng. Không âm thầm tính lại mọi thời hạn từ lúc pipeline nhận dữ liệu nếu điều đó làm lệch hợp đồng lưu giữ.

## 6. Vòng đời tài khoản và vòng đời dữ liệu chạy song song

Một quy trình minh họa có thể gồm hai nhánh phối hợp:

```text
Nhận sự kiện kết thúc quan hệ sử dụng đã được xác minh
    |
    +-> Nhánh quyền truy cập
    |     vô hiệu hóa đăng nhập theo thiết kế
    |     thu hồi phiên, grant, credential và quyền liên quan
    |     deprovision hệ thống đích và theo dõi kết quả
    |
    +-> Nhánh dữ liệu
          phân loại dữ liệu còn cần giữ
          xác định mốc retention và ngoại lệ hợp lệ
          giảm thuộc tính không còn cần thiết
          xóa hoặc biến đổi khi đến hạn
          xử lý bản sao và xác minh hoàn tất
```

Một ngoại lệ giữ dữ liệu phục vụ điều tra không phải ngoại lệ cho phép tài khoản tiếp tục truy cập. Hai nhánh phải có trạng thái và bằng chứng riêng.

Nếu offboarding ở một SaaS thất bại, hệ thống cần thể hiện còn tác vụ thu hồi quyền chưa hoàn tất. Nếu tài khoản đã bị khóa thành công nhưng backup vẫn còn trong vòng đời đã được phê duyệt, cần thể hiện trạng thái dữ liệu tương ứng, không gộp tất cả thành một cờ `deleted=true` thiếu ý nghĩa.

Trong khi tài khoản còn hoạt động, vẫn nên đánh giá các thuộc tính không còn dùng, dữ liệu đăng ký yếu tố xác thực cũ và bản sao đã hết mục đích. Retention không chỉ bắt đầu sau khi tài khoản bị xóa.

## 7. Xóa, giả danh hóa và giữ tham chiếu tối thiểu

### 7.1. Các phương án có ý nghĩa khác nhau

| Phương án | Điều thay đổi | Giới hạn |
|---|---|---|
| Xóa bản ghi | Loại bỏ dữ liệu khỏi một nơi lưu trữ cụ thể | Không tự xử lý replica, log, backup hoặc bản xuất |
| Xóa một số thuộc tính | Giữ bản ghi tối thiểu nhưng bỏ dữ liệu không còn cần | Phần còn lại vẫn có thể xác định hoặc liên kết chủ thể |
| Giả danh hóa | Thay định danh trực tiếp bằng mã tham chiếu có kiểm soát | Có thể nối lại qua mapping hoặc dữ liệu phụ trợ |
| Tổng hợp | Giữ thống kê thay vì từng hồ sơ | Nhóm quá nhỏ hoặc nhiều chiều vẫn có thể làm lộ thông tin |
| Ẩn danh hóa theo đánh giá phù hợp | Loại khả năng gắn dữ liệu với cá nhân ở mức yêu cầu | Không thể khẳng định chỉ dựa trên việc bỏ tên hoặc băm email |

Lựa chọn phải dựa trên mục đích và khả năng thực tế của hệ thống. Không đổi nhãn thành “anonymous” để thay thế việc đánh giá dữ liệu còn có thể liên kết ra sao.

### 7.2. Tombstone và định danh đã nghỉ sử dụng

Một số hệ thống cần giữ một tham chiếu tối thiểu để biết danh tính đã bị xóa, tránh khôi phục lại hoặc nối nhầm tài khoản. Bản ghi này thường được gọi là tombstone.

Tombstone không cần chứa toàn bộ hồ sơ cũ. Nó cần phạm vi, mục đích, quyền truy cập và thời hạn riêng, tương xứng với các bản sao hoặc đường khôi phục phải kiểm soát.

Việc tái sử dụng một email hoặc username cho người khác có thể gây nhầm nếu ứng dụng dùng chúng làm khóa liên kết duy nhất. Dữ liệu lịch sử và tài khoản mới phải được phân biệt bằng định danh đúng ngữ cảnh, tránh cấp lại quyền hoặc hiển thị lịch sử của người cũ cho người mới.

Định danh kỹ thuật ổn định cũng không phải lý do để giữ mọi dữ liệu cá nhân đi kèm mã đó vô hạn. Cần tách nhu cầu bảo toàn tham chiếu khỏi nhu cầu giữ hồ sơ chi tiết.

## 8. Thực thi retention qua nhiều hệ thống

Xóa một dòng trong kho IAM chính thường chưa hoàn thành toàn bộ công việc. Cần điều phối các nơi lưu trữ thuộc phạm vi được xác định.

Một tác vụ thực thi có thể trải qua các trạng thái:

```text
đến hạn -> kiểm tra điều kiện và ngoại lệ -> lập tác vụ
        -> xử lý từng đích -> xác minh từng đích
        -> hoàn tất / còn đích lỗi / đang được giữ theo ngoại lệ
```

Đầu vào tác vụ cần định danh chủ thể rõ ràng, nguồn hoặc issuer, tenant và loại dữ liệu. Không dùng email hiện tại làm khóa duy nhất cho thao tác xóa trên nhiều hệ thống vì email có thể thay đổi hoặc được tái sử dụng.

Những thuộc tính kỹ thuật cần có gồm:

- **Đúng phạm vi:** chỉ xử lý dữ liệu của chủ thể, tenant và mục đích đã xác định.
- **Idempotent:** chạy lại không làm mất dữ liệu của danh tính mới hoặc gây trạng thái sai.
- **Theo dõi từng đích:** phân biệt đã gửi yêu cầu, đã được xác nhận và đã kiểm chứng kết quả.
- **Retry có kiểm soát:** lỗi một đích không làm che mất tác vụ còn dở hoặc phát lệnh vô hạn.
- **Kiểm tra xung đột:** phát hiện hold, thay đổi trạng thái hoặc quan hệ dữ liệu cần xử lý riêng.
- **Bằng chứng tối thiểu:** ghi kết quả cần thiết mà không lưu lại toàn bộ dữ liệu vừa xóa.

Quan hệ tham chiếu phải được xem xét trước khi xóa. Một đơn hàng hoặc bản ghi audit có thể còn nhu cầu lưu riêng; xử lý quan hệ bằng cách tách tham chiếu hoặc giảm dữ liệu theo thiết kế, thay vì xóa dây chuyền không có phạm vi rõ ràng.

Nếu một đối tác hoặc SaaS chỉ trả xác nhận đã nhận yêu cầu, đó chưa nhất thiết là bằng chứng mọi bản sao đã được xử lý. Trạng thái hoàn tất phải dựa trên hợp đồng và khả năng xác minh thực tế của từng đích.

## 9. Credential, phiên và token cần cách xử lý riêng

Retention của hồ sơ không được thay thế quy trình thu hồi credential.

Khi kết thúc quyền sử dụng, cần xem xét session, refresh token, API key, chứng thư, yếu tố MFA và các grant ủy quyền còn có thể được dùng. Credential của workload có thể nằm ở các hệ thống khác với tài khoản con người sở hữu nó.

Một access token tự chứa có thể vẫn được resource server chấp nhận tới khi hết hạn hoặc tới khi một cơ chế kiểm tra trạng thái thích hợp ngăn được nó. Xóa tài khoản ở IdP không tự chứng minh mọi token đã phát hành lập tức mất hiệu lực ở tất cả nơi dùng.

Password hash, seed MFA hoặc vật liệu credential không nên được giữ trong hồ sơ lưu trữ thông thường chỉ vì muốn giữ bằng chứng tài khoản từng tồn tại. Bằng chứng cần thiết thường có thể được thiết kế tách khỏi bí mật xác thực; nếu có yêu cầu đặc biệt, nó cần phạm vi và kiểm soát riêng.

Khóa ký dùng chung cho nhiều chủ thể cũng khác credential của một chủ thể. Không xóa khóa ký chung như một bước “xóa người dùng” vì có thể ảnh hưởng mọi token và dịch vụ liên quan. Tương tự, một biện pháp xóa bằng cách hủy khóa mã hóa chỉ có ý nghĩa khi thiết kế khóa, phạm vi dữ liệu và các bản sao của khóa thực sự hỗ trợ mục tiêu đó.

Thao tác xóa logic trong một database không tự bảo đảm từng byte đã được ghi đè trên mọi thiết bị lưu trữ. Cần hiểu khả năng của nơi lưu trữ, replication, bản sao lưu và phương pháp hủy dữ liệu đang áp dụng, tránh khẳng định mạnh hơn bằng chứng.

## 10. Audit và log: giữ khả năng truy vết với dữ liệu tối thiểu

Một tổ chức có thể cần biết ai đã cấp quyền quản trị, cho đối tượng nào, khi nào và theo phê duyệt nào. Điều đó không có nghĩa log phải chứa toàn bộ hồ sơ, token hoặc credential của các bên.

Có thể tách:

- Bằng chứng sự kiện với định danh tham chiếu và loại hành động.
- Thông tin cần để phân giải tham chiếu khi điều tra được cho phép.
- Hồ sơ vận hành thông thường của tài khoản.

Mỗi phần có thể có thời hạn, quyền truy cập và cơ chế bảo vệ khác nhau. Khi cần giữ mapping để giải thích lịch sử, phải quản trị mapping đó; giả danh hóa không tự biến dữ liệu thành vô danh.

Không sửa hoặc xóa chọn lọc bằng chứng để che giấu một hoạt động. Xử lý retention của audit phải theo chính sách được xác định, với kiểm soát thay đổi và bằng chứng thực thi phù hợp.

Các bản ghi về chính tác vụ xóa cũng cần tối thiểu hóa. Có thể lưu policy version, mã tác vụ, nhóm dữ liệu, đích xử lý, thời gian và kết quả. Nếu chúng chứa subject ID hoặc dữ liệu liên kết, chúng vẫn thuộc phạm vi quản trị retention.

## 11. Backup, snapshot và nguy cơ tái xuất hiện dữ liệu

### 11.1. Bản sao lưu có vòng đời riêng

Một backup bất biến có thể không cho phép sửa từng bản ghi. Khi đó phải hiểu rõ chu kỳ hết hạn, quyền phục hồi, các bản sao tiếp theo và cách hạn chế sử dụng dữ liệu trong backup.

Nếu dữ liệu đã được xóa khỏi hệ thống đang chạy nhưng còn trong backup chưa hết vòng đời, báo cáo phải phản ánh đúng thực tế đó. Không tuyên bố mọi bản sao đã biến mất chỉ dựa trên kết quả của kho chính.

Thiết kế cần xác định backup nào còn chứa dữ liệu, chúng sẽ được loại bỏ theo mốc nào và có ngoại lệ được phê duyệt nào không. File export cá nhân hoặc snapshot không được quản lý có thể phá vỡ mọi thời hạn đã đặt cho backup chính thức.

### 11.2. Khôi phục phải áp dụng lại các quyết định đã có

Một backup cũ có thể chứa tài khoản đã bị vô hiệu hóa hoặc hồ sơ đã được xóa sau thời điểm tạo backup. Khôi phục nguyên trạng rồi mở hệ thống cho truy cập có thể đưa cả quyền cũ lẫn dữ liệu đã xử lý trở lại.

Quy trình phục hồi cần có cách đối chiếu những quyết định phát sinh sau mốc backup, chẳng hạn:

```text
Khôi phục vào môi trường kiểm soát
    -> đối chiếu trạng thái danh tính và quyết định xóa/thu hồi mới hơn
    -> áp dụng lại xử lý cần thiết và kiểm tra hệ thống đích
    -> xác minh không tái kích hoạt quyền hoặc dữ liệu ngoài chính sách
    -> mới mở phục vụ theo quy trình phục hồi
```

Nguồn đối chiếu phải sống sót qua tình huống phục hồi tương ứng và được bảo vệ phù hợp. Một deletion journal chỉ nằm trong chính backup cũ có thể thiếu các quyết định cần áp dụng lại.

Journal hoặc tombstone dùng cho phục hồi cần thời hạn đủ cho các bản sao còn có thể được khôi phục và quy trình liên quan, đồng thời vẫn phải giới hạn nội dung và mục đích. Không mặc định cần giữ toàn bộ hồ sơ cũ để thực hiện đối chiếu.

## 12. Ngoại lệ lưu giữ và quản lý hold

Một số dữ liệu có thể phải được giữ theo một ngoại lệ đã được người có thẩm quyền xác định, chẳng hạn để bảo toàn bằng chứng cho một cuộc điều tra cụ thể. Ngoại lệ cần được quản trị như một quyết định có phạm vi, không phải một cờ giữ vô hạn cho mọi dữ liệu của chủ thể.

Một hold nên có người chịu trách nhiệm, lý do, nhóm dữ liệu, phạm vi thời gian hoặc sự kiện, điều kiện xem xét lại và tiêu chí kết thúc. Quyền tạo hoặc gỡ hold cần được kiểm soát và audit.

Giữ bằng chứng về một hành động đặc quyền không mặc nhiên đòi giữ toàn bộ địa chỉ, số điện thoại và các credential của tài khoản. Dữ liệu không nằm trong phạm vi ngoại lệ vẫn phải được xử lý theo chính sách tương ứng.

Khi hold kết thúc, cần tính lại tác vụ còn phải làm theo thời hạn đã xác định. Không tự bắt đầu một khoảng retention mới đầy đủ chỉ vì vừa gỡ hold, trừ khi chính sách có căn cứ rõ ràng cho cách tính đó.

Tài khoản đang được giữ dữ liệu cho điều tra vẫn phải chịu trạng thái vô hiệu hóa và các biện pháp thu hồi quyền phù hợp. Không dùng hold như lý do khôi phục khả năng đăng nhập.

## 13. Ví dụ mô hình chính sách và diễn biến thực thi

Ví dụ sau dùng schema tự đặt và những thời hạn giả định để giải thích thiết kế. Các con số không phải thời hạn phù hợp chung hoặc yêu cầu bắt buộc cho hệ thống thực tế.

```yaml
policyId: identity-retention-example
version: example-v1
rules:
  inactiveProfile:
    clock: verified_relationship_end
    retainFor: P30D
    action: remove_nonrequired_profile_attributes
  authenticationEvents:
    clock: event_occurred_at
    retainFor: P90D
    action: delete_from_event_store_and_managed_copies
  privilegedAudit:
    clock: event_occurred_at
    retainFor: P180D
    action: apply_approved_audit_disposition
  managedBackups:
    clock: backup_created_at
    retainFor: P35D
    action: expire_backup
accessLifecycle:
  onRelationshipEnd: execute_offboarding_controls
exceptions:
  requireAuthorizedHold: true
  holdScopeMustBeExplicit: true
restoration:
  reconcileLaterDeletionAndRevocationDecisions: true
```

Các tên hành động trong ví dụ là yêu cầu thiết kế cần triển khai và kiểm chứng, không phải bằng chứng hệ thống tự thực hiện được. `remove_nonrequired_profile_attributes` cũng không đồng nghĩa đã xóa mọi danh tính ở mọi nơi.

Một diễn biến minh họa:

1. Khi nhận sự kiện kết thúc quan hệ đã được xác minh, hệ thống thực thi offboarding và ghi trạng thái từng đích.
2. Bộ quản lý dữ liệu phân loại hồ sơ, log, mapping và những bản sao liên quan theo các rule khác nhau.
3. Khi hồ sơ đến hạn, những thuộc tính không còn nhu cầu được xử lý ở kho chính và các bản sao đang chạy thuộc phạm vi; đích lỗi được theo dõi riêng.
4. Audit còn trong thời gian lưu được bảo vệ theo hợp đồng riêng, với dữ liệu tối thiểu cần thiết.
5. Backup cũ hết hạn theo thời điểm tạo của từng bản; trước khi hết hạn, mọi lần phục hồi phải đối chiếu quyết định xóa và thu hồi mới hơn.
6. Khi không còn công việc hoặc bản sao phải theo dõi cho mục đích tương ứng, dữ liệu điều phối cũng được xử lý theo thời hạn của nó.

Nếu xuất hiện hold hợp lệ, chỉ phần dữ liệu trong phạm vi hold được điều chỉnh theo quyết định đó. Các công việc thu hồi quyền và xử lý dữ liệu ngoài phạm vi vẫn tiếp tục.

## 14. Theo dõi và kiểm chứng chính sách retention

Một scheduler chạy thành công không đủ chứng minh retention đã được thực thi. Cần quan sát kết quả và những trường hợp chưa hoàn tất.

Các tín hiệu hữu ích gồm số tác vụ đến hạn, quá hạn, đích lỗi, hold cần xem xét, bản sao chưa được xử lý và lần kiểm chứng khôi phục gần nhất. Metric tổng hợp nên tránh dùng email hoặc subject ID làm label có cardinality cao; chi tiết điều tra nằm trong nơi được phân quyền.

Phân biệt dữ liệu đang được giữ theo ngoại lệ hợp lệ với dữ liệu quá hạn do lỗi vận hành. Cả hai cần được thấy rõ nhưng không có cùng ý nghĩa.

| Tình huống kiểm chứng | Kết quả cần xác nhận |
|---|---|
| Kết thúc quan hệ sử dụng | Quyền được xử lý theo offboarding, không chờ hết thời hạn hồ sơ |
| Thuộc tính hết nhu cầu khi tài khoản còn hoạt động | Có thể xử lý riêng mà không chờ xóa tài khoản |
| Đồng bộ cập nhật `updatedAt` hằng ngày | Không vô tình làm mới đồng hồ retention đã xác định |
| Tài khoản đã nghỉ nhận request đăng nhập thất bại | Request đó không tự kéo dài lưu hồ sơ ngoài chính sách |
| Một đích provisioning hoặc kho phân tích đang lỗi | Có tác vụ còn dở, retry và chủ sở hữu xử lý |
| Chạy lại tác vụ đã hoàn tất | Không xóa nhầm dữ liệu mới hoặc danh tính khác |
| Email cũ được cấp cho người khác | Không nối tài khoản hoặc lịch sử của hai chủ thể |
| Token cũ còn được resource server chấp nhận | Phạm vi và giới hạn thu hồi được nhận diện, không suy ra từ việc xóa hồ sơ |
| Audit còn mục đích lưu sau khi hồ sơ được giảm dữ liệu | Vẫn truy vết được trong phạm vi được phép, không giữ dư credential |
| Hold chỉ áp dụng một nhóm sự kiện | Không giữ toàn bộ dữ liệu chủ thể theo mặc định |
| Hold kết thúc | Tác vụ retention được đánh giá lại theo mốc và policy đúng |
| Khôi phục từ backup trước thời điểm xóa | Quyết định xóa và thu hồi mới hơn được áp dụng trước khi mở phục vụ |
| Backup hoặc bản export hết hạn | Có bằng chứng xử lý theo khả năng và hợp đồng lưu trữ |
| Báo cáo tác vụ xóa được tạo | Không nhân bản lại hồ sơ hoặc bí mật vừa được loại bỏ |

Identity retention có hiệu quả khi quyền truy cập, mục đích lưu dữ liệu và trạng thái thực thi được quản lý riêng nhưng phối hợp với nhau. Cần giữ đúng phần dữ liệu còn cần, xử lý phần đã hết mục đích và kiểm chứng mọi đường sao chép hoặc phục hồi có thể làm danh tính cũ xuất hiện trở lại.

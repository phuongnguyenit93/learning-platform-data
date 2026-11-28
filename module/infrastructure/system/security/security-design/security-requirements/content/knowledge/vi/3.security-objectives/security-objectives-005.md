# Accountability

## 1. Accountability là gì?

**Accountability** là khả năng gắn hành động và kết quả trong hệ thống với các chủ thể chịu trách nhiệm, đồng thời có đủ căn cứ để giải thích, kiểm tra và xử lý những hành động đó. Trong an toàn thông tin, thuật ngữ này thường được diễn đạt là **khả năng quy trách nhiệm** hoặc **trách nhiệm giải trình**.

Ví dụ, khi quyền đọc một tài liệu bị mở rộng, tổ chức cần biết ai khởi tạo thay đổi, danh tính nào thực thi, tài liệu và người nhận quyền nào bị tác động, chính sách nào được áp dụng, thay đổi có thành công không và ai chịu trách nhiệm xem xét nếu có bất thường.

Có một dòng log “đã cập nhật quyền” chưa trả lời được các câu hỏi đó. Ngược lại, thu thập thật nhiều thông tin nhưng không ai có quyền kiểm tra, không xác định được nguồn tin cậy hoặc không có quy trình xử lý cũng chưa tạo ra accountability đầy đủ.

Một mục tiêu accountability có thể diễn đạt như sau:

> Với các hành động nhạy cảm thuộc phạm vi đã xác định, hệ thống và quy trình vận hành phải cung cấp được bằng chứng đủ tin cậy để liên kết chủ thể khởi tạo, danh tính thực thi, đối tượng, điều kiện quyết định và kết quả; đồng thời xác định người có trách nhiệm xem xét, giải thích và xử lý khi cần.

Mục tiêu này cần được chuyển thành yêu cầu cụ thể về danh tính, phân quyền, sự kiện kiểm toán, bảo vệ bằng chứng, khả năng truy xuất và trách nhiệm vận hành. Accountability là thuộc tính của cả luồng xử lý và cách quản lý hệ thống, không phải tính năng riêng của kho log.

### 1.1. Quy trách nhiệm không đồng nghĩa kết luận một người cố ý làm sai

Bằng chứng hệ thống thường cho biết một hành động được thực hiện dưới danh tính nào và qua đường nào. Nếu tài khoản bị chiếm quyền, thông tin xác thực bị dùng chung hoặc thiết bị bị điều khiển, không thể chỉ từ tên tài khoản mà kết luận người sở hữu đã trực tiếp thao tác hay có ý định gì.

Vì vậy, cần phân biệt **gắn hành động với danh tính đã được xác minh** với **kết luận về con người thực sự điều khiển hành động**. Điều tra có thể cần thêm bối cảnh và bằng chứng. Yêu cầu tốt ghi rõ mức độ tin cậy cùng các giới hạn, thay vì hứa rằng hệ thống luôn chứng minh được mọi ý định của người dùng.

## 2. Phân biệt accountability với các khái niệm liên quan

| Khái niệm | Câu hỏi chính | Quan hệ với accountability |
|---|---|---|
| Identification — định danh | Chủ thể khai báo hoặc được nhận diện bằng mã nào? | Cung cấp điểm tham chiếu, nhưng một mã tự khai chưa đáng tin. |
| Authentication — xác thực | Căn cứ nào chứng minh danh tính theo cơ chế đã chọn? | Tạo cơ sở liên kết sự kiện với danh tính, có giới hạn theo độ tin cậy của cơ chế. |
| Authorization — phân quyền | Chủ thể có được thực hiện hành động này không? | Xác định điều kiện cho phép; cần phân biệt quyết định quyền với kết quả thực hiện. |
| Logging — ghi nhật ký | Sự kiện nào đã được ghi lại? | Là phương tiện tạo dấu vết; log có thể thiếu trường, sai nghĩa hoặc bị sửa. |
| Auditability — khả năng kiểm toán | Có thể xem xét và kiểm tra lại hoạt động bằng bằng chứng không? | Hỗ trợ giải trình và phát hiện sai lệch, nhưng vẫn cần người và quy trình xử lý. |
| Integrity — tính toàn vẹn | Dữ liệu và bằng chứng có bị thay đổi trái phép không? | Giúp giữ độ tin cậy của hồ sơ dùng để quy trách nhiệm. |
| Non-repudiation — chống chối bỏ | Có bằng chứng phù hợp để một bên không dễ phủ nhận một hành động đã gắn với họ không? | Là mục tiêu liên quan, thường đòi hỏi mô hình bằng chứng và tin cậy chặt hơn việc có log thông thường. |

Một tài khoản có quyền vẫn có thể dùng quyền sai mục đích; accountability giúp xem xét việc sử dụng đó. Một tài khoản không có quyền cũng có thể tạo nhiều lần thử đáng chú ý; các lần bị từ chối có thể thuộc phạm vi cần ghi nhận.

Chữ ký số hoặc cơ chế xác thực nguồn có thể hỗ trợ kiểm tra nguồn và phát hiện thay đổi nếu quản lý khóa cùng điểm xác minh đáng tin. Chúng không tự chứng minh người sở hữu khóa trực tiếp thao tác, nội dung đúng nghiệp vụ hay mọi sự kiện liên quan đều đã được ghi. Không nên gọi một hệ thống là chống chối bỏ chỉ vì log có hash hoặc chữ ký.

## 3. Xác định phạm vi accountability từ rủi ro

Không phải mọi sự kiện đều cần cùng mức chi tiết và cùng thời hạn lưu. Cần bắt đầu từ tài sản, tác động và câu hỏi điều tra thực sự phải trả lời.

Giả sử một dịch vụ quản lý tài liệu phục vụ nhiều tổ chức. Mỗi tổ chức là một **tenant**, có thành viên và dữ liệu riêng. Chủ tài liệu có thể giao quyền theo chính sách; nhân viên hỗ trợ chỉ có quyền có thời hạn; tác vụ nền chạy bằng danh tính dịch vụ.

Những hành động có thể cần hồ sơ kiểm toán chuyên biệt gồm:

- Cấp, đổi, thu hồi quyền hoặc thay đổi thành viên nhóm có ảnh hưởng đến quyền.
- Đọc hoặc xuất dữ liệu nhạy cảm trong các tình huống được xác định theo rủi ro.
- Xóa tài liệu, thay đổi cấu hình bảo vệ hoặc thực hiện phục hồi.
- Kích hoạt, sử dụng và kết thúc quyền hỗ trợ hoặc truy cập khẩn cấp.
- Thay đổi chính sách, cấu hình logging, khóa và danh tính có đặc quyền.
- Các lần từ chối hoặc lỗi quan trọng có thể báo hiệu lạm dụng hay mất dấu vết.

Một phân tích ban đầu có thể dùng bảng:

| Rủi ro | Câu hỏi cần trả lời bằng bằng chứng | Phạm vi cần ghi nhận |
|---|---|---|
| R-01: mở rộng quyền tài liệu trái phép | Ai yêu cầu, ai phê duyệt nếu có, ai thực thi và quyền đã đổi ra sao? | Vòng đời thay đổi quyền và kết quả ghi dữ liệu. |
| R-02: dùng danh tính máy để che người khởi tạo | Tác vụ được ai tạo, chạy lần nào và bằng danh tính nào? | Tạo tác vụ, lần chạy, ủy nhiệm và thao tác lên tài nguyên. |
| R-03: xóa hoặc sửa dấu vết sau lạm dụng | Nguồn nào phát sự kiện, ai có thể sửa/xóa và có phát hiện mất dữ liệu không? | Cấu hình nguồn phát, đường thu thập, quyền quản trị và kiểm tra toàn vẹn. |
| R-04: không điều tra được trong thời gian cần thiết | Sự kiện đã đến nơi truy vấn chưa, ai được truy vấn và mất bao lâu? | Độ trễ thu thập, lưu giữ, khả năng tìm kiếm và quy trình điều tra. |
| R-05: kho log trở thành nguồn rò rỉ dữ liệu | Đã ghi những trường gì, ai đọc được và tồn tại bao lâu? | Chính sách dữ liệu log, quyền theo tenant và xóa/lưu giữ. |

Nếu tổ chức yêu cầu quy trách nhiệm cho hoạt động quản trị hạ tầng nhưng chỉ thu log ứng dụng, phạm vi bằng chứng còn thiếu. Nếu chỉ cần điều tra thay đổi quyền mà ghi toàn bộ nội dung tài liệu, phạm vi dữ liệu có thể rộng hơn mục đích.

## 4. Xây dựng chuỗi danh tính và trách nhiệm

### 4.1. Danh tính cá nhân và tài khoản dùng chung

Với con người thực hiện thao tác nhạy cảm, cần có danh tính cá nhân hoặc cơ chế tương đương cho phép liên kết phiên đặc quyền với người sử dụng đã được xác minh. Tài khoản dùng chung mà nhiều người biết cùng một mật khẩu làm suy yếu khả năng quy trách nhiệm.

Nếu một cơ chế vận hành bắt buộc dùng tài khoản đích dùng chung, cần làm rõ lớp kiểm soát phía trước: ai được cấp phiên, phiên nào gắn với ai, thông tin xác thực được bảo vệ ra sao và làm thế nào nối thao tác với phiên đó. Đổi tên tài khoản đích hoặc thêm một dòng ghi chú thủ công chưa tự giải quyết được vấn đề.

Không ghi mật khẩu, khóa, token hay cookie phiên vào log để “chứng minh ai đăng nhập”. Nên dùng mã tham chiếu sự kiện xác thực hoặc phiên kiểm toán không có giá trị dùng để đăng nhập thay người dùng.

### 4.2. Chủ thể khởi tạo và danh tính thực thi

Một hành động có thể đi qua nhiều tầng:

```text
Người dùng đã xác thực
        |
        v
API nhận yêu cầu và tạo tác vụ
        |
        v
Worker chạy bằng danh tính dịch vụ
        |
        v
Kho dữ liệu ghi nhận thao tác
```

Nếu chỉ lưu danh tính worker, sẽ khó biết người nào khởi tạo nghiệp vụ. Nếu chỉ lưu người dùng, sẽ thiếu thành phần thực thi và đường điều khiển có thể bị lạm dụng.

Hồ sơ cần phân biệt:

- **Chủ thể khởi tạo:** người hoặc hệ thống yêu cầu hành động.
- **Danh tính thực thi:** principal mà component dùng khi gọi tài nguyên hoặc ghi dữ liệu.
- **Chủ thể được đại diện:** nếu có ủy nhiệm hoặc hành động thay, cần ghi rõ đối tượng được đại diện và căn cứ.
- **Người phê duyệt:** nếu chính sách yêu cầu, phải liên kết với quyết định phê duyệt cụ thể.
- **Chủ sở hữu quy trình:** vai trò chịu trách nhiệm giải thích và xử lý khi hành động hoặc dấu vết bất thường.

Thông tin về người khởi tạo phải đến từ ngữ cảnh đã xác minh hoặc hồ sơ tác vụ được bảo vệ. Một trường `initiatorId` do client tự gửi không phải bằng chứng đủ tin cậy. Tương tự, mã tương quan chỉ giúp nối các sự kiện; nó không tự chứng minh danh tính hay quyền.

### 4.3. Ủy nhiệm và hỗ trợ phải có dấu vết riêng

Khi nhân viên hỗ trợ thao tác trong phạm vi dữ liệu của khách hàng, không nên chỉ ghi khách hàng là người thực hiện. Cần giữ danh tính người hỗ trợ, ngữ cảnh được đại diện nếu có, phạm vi quyền được kích hoạt, người cho phép và thời hạn.

Với tác vụ do lịch chạy tự động tạo, có thể không tồn tại người khởi tạo tại mỗi lần chạy. Khi đó, ghi lịch hoặc cấu hình kích hoạt, danh tính workload, phiên bản cấu hình và chủ sở hữu chịu trách nhiệm. Không tự gán một người dùng làm người thao tác chỉ vì họ là người tạo lịch từ trước.

## 5. Thiết kế sự kiện kiểm toán có ý nghĩa

### 5.1. Ghi điều gì để giải thích được hành động?

Một hợp đồng sự kiện thường cần các nhóm trường sau:

| Nhóm trường | Nội dung | Chú ý |
|---|---|---|
| Định danh sự kiện | Mã sự kiện, loại, phiên bản schema và nguồn phát. | Hỗ trợ phân biệt sự kiện và diễn giải đúng theo phiên bản. |
| Chủ thể | Chủ thể khởi tạo, danh tính thực thi, ủy nhiệm hoặc phê duyệt khi có. | Dùng định danh ổn định theo nguồn có thẩm quyền; không suy từ dữ liệu tự khai. |
| Đối tượng | Tenant, loại và mã tài nguyên, đối tượng nhận quyền nếu liên quan. | Không coi metadata là công khai; giới hạn dữ liệu theo mục đích. |
| Hành động và kết quả | Hành động nghiệp vụ, quyết định quyền, kết quả thực hiện và mã lý do. | “Được cho phép” khác “đã ghi thay đổi thành công”. |
| Ngữ cảnh liên kết | Mã tương tác, thao tác, tác vụ, lần chạy, lần thử và tham chiếu phiên phù hợp. | Không dùng token truy cập làm khóa tương quan. |
| Thời gian | Thời điểm xảy ra, ghi nhận và tiếp nhận theo hợp đồng. | Ghi rõ ý nghĩa, múi giờ và giới hạn độ chính xác. |
| Thay đổi | Chênh lệch trước/sau hoặc tham chiếu bằng chứng cần thiết. | Chỉ áp dụng cho dữ liệu đã được cho phép ghi vào hồ sơ kiểm toán. |
| Căn cứ | Tham chiếu quyết định quyền, chính sách hoặc yêu cầu phê duyệt. | Phải có đường tra cứu phù hợp nếu muốn giải thích lại quyết định. |

Các trường bắt buộc thay đổi theo loại sự kiện. Một lần đọc tài liệu không nhất thiết cần giá trị trước/sau; một lần đổi quyền thường cần biết quyền nào đã thay đổi. Hợp đồng phải nêu rõ trường nào bắt buộc, tùy chọn hoặc bị cấm, thay vì yêu cầu chung “ghi đầy đủ thông tin”.

### 5.2. Ví dụ một sự kiện thay đổi quyền

Giả sử chủ tài liệu U-17 đổi quyền của U-27 từ đọc sang biên tập trên tài liệu D-123 thuộc tenant T-A. API thực thi bằng danh tính dịch vụ `document-api`.

```json
{
  "schemaVersion": 1,
  "eventId": "EVT-2048",
  "eventType": "document.permission.changed",
  "source": "document-api",
  "environment": "production",
  "occurredAt": "2026-01-10T08:15:30Z",
  "recordedAt": "2026-01-10T08:15:30.040Z",
  "tenantRef": "T-A",
  "initiatingActor": {
    "type": "user",
    "subjectRef": "U-17"
  },
  "executingPrincipal": {
    "type": "service",
    "subjectRef": "document-api"
  },
  "resource": {
    "type": "document",
    "resourceRef": "D-123"
  },
  "targetSubjectRef": "U-27",
  "action": "document.permission.change",
  "authorizationDecisionRef": "DEC-812",
  "policyVersion": "POL-7",
  "outcome": "succeeded",
  "change": {
    "from": "reader",
    "to": "editor"
  },
  "operationRef": "OP-915",
  "interactionRef": "INT-621"
}
```

Đây là schema minh họa, không phải tiêu chuẩn bắt buộc. Dữ liệu thay đổi quyền được phép xuất hiện trong kho kiểm toán được kiểm soát riêng của ví dụ; điều đó không có nghĩa được đưa mọi giá trị trước/sau vào log ứng dụng chung.

Trường `outcome=succeeded` chỉ được phát theo ngữ nghĩa đã cam kết về thay đổi thành công. Một quyết định cho phép trước giao dịch không được ghi nhầm thành thay đổi đã hoàn tất. Nếu thao tác thất bại hoặc chỉ thành công một phần, loại sự kiện và kết quả phải phản ánh trạng thái đó.

### 5.3. Thời gian và thứ tự sự kiện

Thời điểm xảy ra hành động, thời điểm ứng dụng ghi sự kiện và thời điểm kho tập trung tiếp nhận có thể khác nhau. Chênh lệch đó quan trọng khi điều tra và khi đo độ trễ.

Các component cần quy ước thời gian thống nhất, theo dõi sai lệch đồng hồ phù hợp và lưu đủ căn cứ để hiểu các mốc. Trong hệ thống phân tán, chỉ sắp xếp timestamp không luôn chứng minh được thứ tự nhân quả vì đồng hồ có thể lệch và sự kiện có thể đến muộn.

Để nối quan hệ, nên dùng mã thao tác, tác vụ, phiên bản dữ liệu hoặc số thứ tự theo nguồn khi phù hợp. Đo khoảng thời gian trong một tiến trình có thể cần cơ chế thời gian đơn điệu; timestamp theo đồng hồ lịch phục vụ một mục đích khác. Không trộn hai loại để tạo cảm giác chính xác hơn thực tế.

## 6. Bảo đảm dấu vết tồn tại và đáng tin

### 6.1. Không tách rời thay đổi nghiệp vụ với nghĩa vụ ghi nhận

Một lỗi quan trọng là cập nhật quyền thành công rồi mới cố gửi log bằng một lời gọi có thể thất bại mà không được xử lý. Khi đó, dữ liệu đã đổi nhưng bằng chứng có thể mất.

Với thao tác tác động cao, yêu cầu có thể quy định chỉ xác nhận thành công sau khi thay đổi và sự kiện kiểm toán tương ứng được ghi bền vững theo một cơ chế nhất quán. Một cách triển khai là lưu thay đổi nghiệp vụ và sự kiện trong cùng giao dịch, sau đó chuyển sự kiện sang kho kiểm toán bằng tiến trình riêng. Cách này thường được gọi là transactional outbox.

Đây là một lựa chọn kiến trúc, không phải công thức áp dụng bắt buộc. Điều cần chứng minh là không có đường đã nhận thành công nhưng bỏ mất sự kiện bắt buộc; nếu chưa biết giao dịch có thành công vì mất kết nối, hệ thống phải hỗ trợ xác định lại kết quả theo mã thao tác và chính sách gửi lại.

Sự kiện trong outbox chưa đồng nghĩa đã được bảo vệ khỏi mọi người quản trị kho nguồn. Cần đánh giá cả khoảng thời gian trước khi chuyển sang miền lưu trữ có cơ chế bảo vệ độc lập và khả năng phát hiện việc can thiệp nguồn phát.

### 6.2. Phân biệt phát sinh sự kiện, chuyển sự kiện và truy vấn được

Một sự kiện có thể đã được ứng dụng ghi nhưng chưa đến nơi điều tra. Vì vậy, nên có các cam kết riêng:

| Giai đoạn | Điều cần bảo đảm | Ví dụ bằng chứng |
|---|---|---|
| Phát sinh tại nguồn | Đúng loại, đúng thời điểm, đủ trường theo hợp đồng. | Đối chiếu hành động và sự kiện trong kiểm thử tích hợp. |
| Ghi bền vững | Không mất dấu vết đã cam kết khi xảy ra loại lỗi thuộc phạm vi. | Dừng tiến trình ở các điểm kiểm soát, kiểm tra trạng thái và sự kiện sau khởi động lại. |
| Chuyển và tiếp nhận | Có phản hồi lỗi, retry, kiểm soát trùng và phát hiện tồn đọng. | Mô phỏng gián đoạn đường chuyển, đối chiếu số sự kiện và trạng thái hàng đợi. |
| Lập chỉ mục và truy vấn | Sự kiện tìm được theo các khóa và thời hạn cần thiết. | Truy vấn từ nơi phục vụ điều tra, không chỉ kiểm tra tệp cục bộ. |
| Lưu giữ và kết thúc vòng đời | Bằng chứng tồn tại đúng thời hạn và được xóa theo chính sách. | Kiểm tra quyền, cấu hình lưu giữ và kết quả xử lý hết hạn. |

Nếu kho tập trung tạm thời lỗi, hệ thống có thể tiếp tục một số thao tác nhờ vùng lưu bền vững tại nguồn, trong giới hạn đã thiết kế. Cần nêu dung lượng, cảnh báo, thời gian chịu lỗi và hành vi khi không còn khả năng bảo đảm ghi nhận.

Không mặc định mọi thao tác đều phải dừng khi logging lỗi. Ví dụ thu hồi quyền trong tình huống khẩn cấp có nhu cầu vận hành khác với cấp thêm đặc quyền. Chính sách phải quy định hành vi theo loại hành động, cơ chế lưu bằng chứng và ngoại lệ được chấp nhận; không để mã xử lý lỗi tự bỏ qua nghĩa vụ ghi nhận.

### 6.3. Retry và sự kiện trùng không được làm sai câu chuyện

Một thao tác có thể được thử nhiều lần; một sự kiện có thể được chuyển nhiều lần. Đây là hai hiện tượng khác nhau.

- Mã thao tác liên kết một ý định hoặc giao dịch nghiệp vụ theo hợp đồng.
- Mã lần thử phân biệt các lần xử lý hoặc gửi lại khi cần điều tra.
- Mã sự kiện cho phép nhận biết một sự kiện đã được nhận trước đó.
- Mã tác vụ và lần chạy nối các bước bất đồng bộ.

Kho kiểm toán có thể loại bản sao chuyển trùng dựa trên mã sự kiện theo hợp đồng. Không được vì cùng mã thao tác mà xóa các lần thử có ý nghĩa bảo mật, chẳng hạn nhiều lần bị từ chối rồi một lần thành công. Cách xử lý trùng phải giữ được các thông tin mà mục tiêu accountability yêu cầu.

### 6.4. Bảo vệ tính toàn vẹn và phát hiện can thiệp

Các biện pháp thường cần phối hợp gồm giới hạn quyền đọc/ghi/xóa, tách quyền ứng dụng với quyền quản trị bằng chứng, bảo vệ kênh chuyển, lưu giữ theo chính sách, giám sát cấu hình và lưu bản sao trong miền quản trị thích hợp.

Cần phân biệt **ngăn sửa** và **phát hiện đã sửa**. Một cơ chế lưu chỉ ghi thêm có thể hạn chế sửa theo mô hình quyền cụ thể. Chuỗi hash hoặc chữ ký có thể hỗ trợ phát hiện thay đổi nếu có điểm neo, khóa và bộ xác minh đáng tin. Nếu người tấn công sửa được cả dữ liệu, bản tham chiếu, khóa và kết quả xác minh, cam kết còn lại sẽ khác.

Cũng phải xét việc ngừng phát sự kiện hoặc bỏ sót trước khi ghi. Hash của các sự kiện hiện có không tự chứng minh mọi hành động đáng ra phải được ghi đều đã có mặt. Có thể cần đối chiếu trạng thái nghiệp vụ, theo dõi sức khỏe nguồn phát, số thứ tự theo nguồn hoặc cơ chế kiểm tra tính đầy đủ phù hợp.

Những giới hạn này phải được nêu trong mô hình đe dọa. Không nên ghi “log không thể bị sửa trong mọi trường hợp” khi kiến trúc chỉ bảo vệ được trước một tập danh tính và loại can thiệp cụ thể.

## 7. Giữ bằng chứng hữu ích mà không tạo nguồn rò rỉ mới

### 7.1. Tối thiểu hóa dữ liệu theo câu hỏi điều tra

Kho kiểm toán có thể chứa mã người dùng, tài nguyên nhạy cảm, lịch sử quyền và chi tiết hoạt động. Bản thân nó là tài sản cần bảo vệ. Ghi toàn bộ request, response hoặc nội dung tài liệu thường làm tăng dữ liệu nhạy cảm mà chưa chắc giúp trả lời câu hỏi cần điều tra.

Nên xác định trường được phép, trường phải che và trường bị cấm. Ví dụ log thay đổi quyền có thể cần mã người nhận cùng quyền trước/sau, nhưng không cần mật khẩu, token, khóa mã hóa hoặc nội dung tài liệu. Địa chỉ mạng và thông tin thiết bị chỉ nên được thu khi có mục đích, phạm vi và chính sách phù hợp.

Định danh nội bộ hoặc giả danh vẫn có thể liên kết lại với con người hoặc hoạt động. Không được mặc định rằng dùng mã thay tên làm dữ liệu trở nên vô hại. Bảng ánh xạ danh tính, nếu cần cho điều tra, cũng phải có quyền đọc và thời hạn lưu được quản lý.

### 7.2. Kiểm soát đọc, xuất và quản trị bằng chứng

Quyền điều tra không nhất thiết bao gồm quyền quản trị kho log. Người quản trị tenant chỉ nên thấy bằng chứng trong phạm vi được giao; nhân viên hỗ trợ không tự có quyền tìm kiếm hoạt động của mọi khách hàng.

Cần đặc tả ai được truy vấn, ai được xuất, ai được đổi thời hạn lưu và ai được xóa hoặc vô hiệu hóa nguồn phát. Các hành động này cũng có thể cần dấu vết kiểm toán riêng. Tránh phụ thuộc hoàn toàn vào chính kho đang được quản trị để chứng minh rằng quản trị viên chưa can thiệp kho đó.

Thời hạn lưu phải gắn với mục đích và nhu cầu đã được xác định. Nó cần bao phủ nơi truy vấn, lưu trữ lạnh, tệp xuất điều tra và bản sao lưu theo chính sách. Không hứa xóa dữ liệu khỏi mọi bản sao ngay một thời điểm nếu thiết kế thực tế xử lý theo vòng đời khác.

### 7.3. Bảo vệ trước nội dung log gây hiểu nhầm

Các trường như lý do người dùng nhập hoặc tên tài nguyên có thể chứa nội dung không đáng tin. Nếu ghép trực tiếp vào văn bản, ký tự xuống dòng hoặc ký tự điều khiển có thể khiến người đọc và công cụ hiểu sai ranh giới sự kiện.

Hợp đồng nên dùng cấu trúc rõ, giới hạn kích thước, mã hóa đầu ra phù hợp và tách dữ liệu do người dùng cung cấp khỏi trường do hệ thống xác lập. Mã lý do được kiểm soát và tham chiếu đến hồ sơ yêu cầu thường dễ kiểm tra hơn việc dựa duy nhất vào một câu tự khai.

## 8. Biến mục tiêu accountability thành yêu cầu cụ thể

Các yêu cầu sau tiếp tục dùng ví dụ quản lý tài liệu. Những ngưỡng 60 giây và 90 ngày là **giá trị giả định cho bài học**, cần được lựa chọn lại dựa trên rủi ro và khả năng vận hành của dự án.

### ACC-01 — Liên kết được chủ thể và đường thực thi

> Với thay đổi quyền tài liệu, sử dụng quyền hỗ trợ và phục hồi thuộc phạm vi, hồ sơ kiểm toán phải phân biệt chủ thể khởi tạo, danh tính thực thi và chủ thể được đại diện khi có. Các định danh phải lấy từ nguồn đã xác minh, có không gian định danh phù hợp và liên kết được với phiên, tác vụ hoặc cấu hình kích hoạt tương ứng. Không coi trường danh tính tự khai từ client là căn cứ quy trách nhiệm.

**Tiêu chí chấp nhận:** kiểm thử người dùng trực tiếp, người hỗ trợ thao tác thay và tác vụ nền. Mỗi trường hợp phải truy được đúng đường danh tính; giả trường khởi tạo từ request không làm bằng chứng ghi nhận sai chủ thể đã xác thực.

### ACC-02 — Không xác nhận thay đổi quyền thành công khi thiếu bằng chứng bắt buộc

> Với mỗi thay đổi quyền được chấp nhận, hệ thống phải ghi bền vững thay đổi nghiệp vụ cùng sự kiện kiểm toán tương ứng bằng cơ chế nhất quán trước khi xác nhận thành công. Sự kiện phải nêu tài nguyên, tenant, người nhận quyền, quyền trước/sau, chủ thể, căn cứ quyết định và kết quả. Hành vi khi không bảo đảm ghi nhận phải được quy định cho từng loại thao tác, bao gồm ngoại lệ khẩn cấp nếu có.

**Tiêu chí chấp nhận:** mô phỏng lỗi ở các điểm trước/sau ghi dữ liệu và chuyển sự kiện; không có trạng thái đã xác nhận thành công nhưng không có bằng chứng bền vững bắt buộc. Khi phản hồi bị mất, truy vấn theo mã thao tác và gửi lại phải giữ kết quả nhất quán, không tạo lịch sử sai.

### ACC-03 — Bằng chứng truy xuất được trong thời hạn

> Trong điều kiện tối đa 500 sự kiện mỗi giây, mỗi sự kiện không vượt 4 KiB và cửa sổ đo 30 phút của môi trường kiểm thử đã thống nhất, mọi sự kiện thuộc phạm vi đã được ghi bền vững tại nguồn phải truy xuất được tại nơi điều tra trong tối đa 60 giây. Điểm bắt đầu đo là thời điểm ghi bền vững, điểm kết thúc là thời điểm truy vấn theo mã sự kiện trả được nội dung đúng và đủ trường.

**Tiêu chí chấp nhận:** đối chiếu tập mã sự kiện tại nguồn với tập truy xuất được, đo độ trễ và kiểm tra nội dung. Không tính một bản ghi trùng là bằng chứng cho một mã còn thiếu. Kịch bản gián đoạn đường chuyển phải có cam kết riêng về lưu đệm, cảnh báo và thời gian hoàn tất sau phục hồi, thay vì ngầm coi vẫn đạt ngưỡng bình thường.

Yêu cầu này đo sự kiện đã ghi tại nguồn. Để kiểm tra việc bỏ sót trước khi ghi, vẫn cần ACC-02, đối chiếu hành động nghiệp vụ và các kiểm tra tính đầy đủ theo mô hình đe dọa.

### ACC-04 — Bảo vệ bằng chứng trong thời hạn lưu

> Sự kiện kiểm toán thay đổi quyền phải được lưu 90 ngày theo chính sách của ví dụ. Danh tính thực hiện nghiệp vụ không được sửa hoặc xóa sự kiện đã tiếp nhận tại kho kiểm toán được bảo vệ. Quyền truy vấn, xuất, thay cấu hình lưu giữ và quản trị phải được phân tách theo vai trò đã định. Truy cập trái phép, thay cấu hình hoặc mất nguồn phát phải được phát hiện theo hợp đồng giám sát.

**Tiêu chí chấp nhận:** thử bằng danh tính nghiệp vụ, điều tra và quản trị theo mô hình quyền; kiểm tra giới hạn tenant, quyền xóa, quyền đổi cấu hình và dấu vết quản trị. Đối chiếu cơ chế toàn vẹn với tập chủ thể tấn công được đặt trong phạm vi, bao gồm giới hạn bảo vệ ở nguồn trước khi tiếp nhận.

Việc chọn 90 ngày ở đây không hàm ý đó là thời hạn phù hợp với mọi tổ chức. Trong dự án thực tế, cần xác định thời hạn, ngoại lệ giữ lại, nơi áp dụng và quy trình kết thúc vòng đời theo các ràng buộc thực sự của hệ thống.

### ACC-05 — Không ghi dữ liệu bị cấm vào hồ sơ kiểm toán

> Các sự kiện trong phạm vi phải tuân theo schema và danh sách trường được phép. Không ghi mật khẩu, token, cookie phiên, khóa bí mật hoặc nội dung tài liệu. Dữ liệu do người dùng nhập phải được giới hạn và biểu diễn an toàn, không làm thay đổi cấu trúc hay danh tính được hệ thống xác lập.

**Tiêu chí chấp nhận:** dùng dữ liệu đánh dấu trong kiểm thử để kiểm tra các đường thành công, từ chối, lỗi và retry; xác minh dấu đánh dấu thuộc nhóm bị cấm không xuất hiện trong log, bản xuất điều tra hoặc hàng đợi lỗi thuộc phạm vi.

### ACC-06 — Có trách nhiệm xem xét và phản hồi

> Mỗi loại cảnh báo về mất nguồn phát, thiếu sự kiện hoặc sử dụng đặc quyền bất thường phải có đầu mối tiếp nhận, mức ưu tiên, thời hạn xử lý và điều kiện chuyển cấp được chỉ định. Việc xem xét phải để lại kết quả, người chịu trách nhiệm và hành động tiếp theo theo quy trình đã được phê duyệt.

**Tiêu chí chấp nhận:** diễn tập một cảnh báo từ lúc phát hiện đến khi có người tiếp nhận, tra cứu bằng chứng và ghi kết quả xử lý trong thời hạn của loại cảnh báo đó. Nếu chưa chốt thời hạn hoặc chưa có người nhận, yêu cầu vận hành chưa đủ để nghiệm thu.

## 9. Truy vết yêu cầu với kiến trúc và rủi ro

| Rủi ro | Yêu cầu liên quan | Điểm thực hiện | Bằng chứng cần thu |
|---|---|---|---|
| R-01: không giải thích được thay đổi quyền | ACC-01, ACC-02 | API nghiệp vụ, nguồn danh tính và cơ chế ghi sự kiện nhất quán. | Đối chiếu thay đổi, danh tính, quyết định quyền và sự kiện. |
| R-02: tác vụ máy che mất người khởi tạo | ACC-01 | Hồ sơ tác vụ, worker, quan hệ ủy nhiệm. | Luồng từ yêu cầu đến lần chạy và tài nguyên bị tác động. |
| R-03: dấu vết bị sửa hoặc bị ngừng phát | ACC-02, ACC-04, ACC-06 | Nguồn phát, đường thu thập, kho bảo vệ và giám sát. | Kiểm thử quyền, kiểm tra tính toàn vẹn, đối chiếu tính đầy đủ và diễn tập cảnh báo. |
| R-04: bằng chứng không tìm được khi cần | ACC-03, ACC-06 | Thu thập, lập chỉ mục, truy vấn và vận hành điều tra. | Độ trễ, tập mã sự kiện, quyền truy vấn và kết quả diễn tập. |
| R-05: kho bằng chứng làm lộ dữ liệu | ACC-04, ACC-05 | Schema sự kiện, quyền truy vấn, xuất và lưu giữ. | Kiểm thử dữ liệu bị cấm, cách ly tenant và vòng đời bản sao. |

Ma trận thể hiện một rủi ro có thể cần nhiều yêu cầu và một yêu cầu có thể hỗ trợ nhiều rủi ro. Không nên tìm một thành phần duy nhất rồi giao toàn bộ accountability cho thành phần đó.

Nhóm sở hữu nghiệp vụ phải xác định sự kiện nào có ý nghĩa và thời điểm nào là thành công. Nhóm nền tảng logging chịu trách nhiệm về đường thu thập và bảo vệ theo hợp đồng. Nhóm định danh bảo đảm nguồn danh tính và vòng đời. Vai trò điều tra hoặc kiểm soát được giao trách nhiệm truy vấn, xem xét và phản hồi. Người chịu trách nhiệm yêu cầu xuyên suốt cần kiểm tra các phần này thực sự nối được với nhau.

## 10. Kịch bản chấp nhận xuyên suốt

Một kịch bản hữu ích là thay đổi quyền bằng tác vụ nền, đồng thời gây lỗi đường chuyển sự kiện:

```text
Cho trước:
  U-17 có quyền yêu cầu thay đổi quyền trên D-123 thuộc T-A.
  Tác vụ J-42 được tạo từ yêu cầu đã xác thực của U-17.
  Worker chạy bằng danh tính W-DOC.
  Đường chuyển sự kiện đến kho tập trung tạm thời không hoạt động.

Khi:
  J-42 thay quyền của U-27 theo chính sách cho phép.

Thì:
  Quyền chỉ được đổi trong phạm vi tài nguyên và tenant đã kiểm tra.
  Nếu thao tác được xác nhận thành công, thay đổi và sự kiện bắt buộc
  đã được lưu bền vững theo cam kết của hệ thống.
  Bằng chứng phân biệt U-17 là người khởi tạo và W-DOC là danh tính thực thi.
  Hệ thống phát hiện tồn đọng theo hợp đồng giám sát.
  Sau khi đường chuyển phục hồi, truy được sự kiện đúng nội dung,
  không mất sự kiện và xử lý được bản sao chuyển trùng.
```

Cần có thêm ca request giả chủ thể khởi tạo, người không đủ quyền, thao tác thất bại sau khi được cho phép, truy vấn log sai tenant và người quản trị cố thay cấu hình ghi nhận. Mỗi ca phải quan sát dữ liệu nghiệp vụ, nội dung bằng chứng và quyền truy cập tương ứng.

Kiểm tra rằng một hàm logging được gọi chưa đủ. Bằng chứng cần gắn với phiên bản phần mềm, cấu hình, mô hình tải, loại lỗi và phạm vi danh tính đã thử. Tập kiểm thử hữu hạn cũng không chứng minh mọi hành động đều sẽ được giải thích hoàn hảo trong mọi tình huống.

## 11. Duy trì accountability trong vòng đời phát triển

Schema sự kiện và ngữ nghĩa nghiệp vụ có thể thay đổi. Khi đổi tên sự kiện, thêm trường hoặc thay đổi cách xác định thành công, cần quản lý phiên bản để công cụ truy vấn và người điều tra vẫn hiểu đúng dữ liệu cũ. Không nên đổi ý nghĩa một trường mà giữ nguyên cách diễn giải ở toàn bộ hệ thống.

Thay đổi danh tính cũng cần được xử lý. Đổi tên tài khoản không nên làm mất liên kết lịch sử; tái sử dụng một mã cho người khác có thể gây quy trách nhiệm sai. Xóa hoặc kết thúc tài khoản phải tuân theo chính sách vòng đời dữ liệu, đồng thời làm rõ việc giữ tham chiếu và ánh xạ cần thiết cho bằng chứng còn trong thời hạn lưu.

Khi thêm API, tác vụ nền, đường hỗ trợ hoặc tích hợp, cần xem lại phạm vi hành động phải ghi và chuỗi chủ thể. Khi đổi kho logging, khóa hoặc sao lưu, cần kiểm tra lại độ trễ, truy vấn, toàn vẹn, quyền và phục hồi. Khôi phục được dữ liệu ứng dụng nhưng mất liên kết sự kiện hoặc danh tính vẫn có thể làm mục tiêu accountability không được đáp ứng.

Các ngoại lệ như dùng tài khoản chung trong sự cố hoặc tạm thời mất đường thu thập cần có phạm vi, thời hạn, người chấp nhận, biện pháp bù và kế hoạch kết thúc. Không dùng ngoại lệ cũ làm mặc định cho mọi hoạt động về sau.

## 12. Những nhầm lẫn thường gặp

| Nhận định | Vấn đề | Hướng đặc tả rõ hơn |
|---|---|---|
| “Có log là có accountability.” | Chưa có danh tính đáng tin, nghĩa sự kiện, bảo vệ hoặc người xử lý. | Đặc tả chuỗi chủ thể, hành động, kết quả, bằng chứng và trách nhiệm xem xét. |
| “Tài khoản X xuất hiện nên chắc chắn người X trực tiếp làm.” | Tài khoản có thể bị chia sẻ, chiếm quyền hoặc dùng qua ủy nhiệm. | Ghi mức độ xác thực, phiên và đường thực thi; nêu giới hạn kết luận. |
| “Được cho phép nghĩa là đã thực hiện thành công.” | Giao dịch có thể thất bại sau quyết định quyền. | Tách quyết định quyền với kết quả nghiệp vụ. |
| “Hash hoặc chữ ký làm log không thể bị chối bỏ.” | Còn phụ thuộc nguồn, khóa, tính đầy đủ và mô hình tin cậy. | Nêu chính xác thuộc tính được bảo vệ cùng các điều kiện kiểm chứng. |
| “Càng ghi nhiều càng dễ giải trình.” | Tăng rò rỉ, nhiễu và chi phí mà chưa chắc tăng bằng chứng. | Chọn trường theo câu hỏi điều tra và chính sách dữ liệu. |
| “Kho log tập trung không nhận được thì chỉ cần bỏ qua lỗi.” | Có thể mất sự kiện bắt buộc hoặc tạo khoảng mù không ai biết. | Đặt cam kết lưu bền vững, đệm, cảnh báo và hành vi theo loại thao tác. |
| “Timestamp sớm hơn luôn chứng minh hành động xảy ra trước.” | Đồng hồ lệch và xử lý bất đồng bộ có thể làm sai suy luận. | Kết hợp quan hệ tác vụ, mã thao tác, phiên bản và thông tin thời gian. |

## 13. Bài tập áp dụng

Một hệ thống cho phép nhà cung cấp hỗ trợ kỹ thuật chạy tác vụ sửa metadata tài liệu trong một tenant. Quyền hỗ trợ được cấp có thời hạn; tác vụ có thể gửi lại và chạy bằng service account. Việc sửa không được làm lộ nội dung tài liệu.

Hãy thực hiện các bước sau:

1. Liệt kê người yêu cầu, người phê duyệt nếu có, chủ thể được đại diện, danh tính thực thi và chủ sở hữu quy trình.
2. Viết mục tiêu accountability cho cấp quyền hỗ trợ, sử dụng quyền và kết quả sửa metadata.
3. Đề xuất hợp đồng sự kiện, phân biệt trường bắt buộc, tùy chọn và bị cấm. Nêu cách giữ nguồn danh tính đáng tin.
4. Xác định thời điểm được ghi thành công, cơ chế không mất bằng chứng và cách xử lý khi đường chuyển log lỗi.
5. Đặt yêu cầu truy xuất, lưu giữ, quyền đọc/xuất và phát hiện can thiệp với ngưỡng được giải thích theo rủi ro.
6. Viết ca kiểm chứng thành công, bị từ chối, gửi lại, hết quyền, sai tenant và sự cố ghi nhận; nêu giới hạn của bằng chứng thu được.

Một kết quả tốt cho phép trả lời ai đã khởi tạo, hệ thống nào thực thi, quyền nào được sử dụng, dữ liệu nào bị tác động, điều gì thực sự hoàn tất và ai sẽ xử lý khi bằng chứng cho thấy sai lệch. Đó là cách biến accountability thành nghĩa vụ bảo mật có thể triển khai và kiểm chứng trong vòng đời phát triển.

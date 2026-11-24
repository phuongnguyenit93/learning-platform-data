# Audit retention — Chính sách lưu giữ dữ liệu kiểm toán

## 1. Audit retention bảo vệ điều gì?

**Audit retention** là việc xác định dữ liệu kiểm toán nào cần được giữ, giữ đến khi nào, ở đâu, ai được truy cập và khi nào được phép hủy. Nó bao gồm cả thời gian lưu, khả năng đọc lại bằng chứng và quá trình xóa có kiểm soát.

Trong bảo mật logic nghiệp vụ, audit giúp giải thích một hành động đã diễn ra như thế nào: ai sửa giá, ai phê duyệt, đối tượng đang ở trạng thái gì, chính sách quyền nào đã được áp dụng, giao dịch nào thực sự commit và yêu cầu nào chỉ là lần gửi lại.

Những bằng chứng đó có thể không được sử dụng ngay. Một tranh chấp hoàn tiền, dấu hiệu lạm dụng quyền hoặc lỗi xử lý trùng có thể chỉ được phát hiện sau nhiều tuần. Nếu dữ liệu đã bị xóa, nhóm vận hành có thể không còn khả năng nối chuỗi quyết định. Ngược lại, lưu vô hạn làm tăng chi phí, lượng dữ liệu nhạy cảm có thể bị lộ và phạm vi truy cập cần kiểm soát.

Một chính sách retention cần đáp ứng đồng thời ba mục tiêu:

1. Giữ đủ bằng chứng để giải thích hành động trong phạm vi thời gian đã xác định.
2. Bảo đảm bằng chứng còn nguyên vẹn, có thể tìm thấy và diễn giải được.
3. Hủy dữ liệu đúng điều kiện, có thể kiểm chứng, trên các bản sao thuộc phạm vi quản lý.

Audit retention không sửa được một quy tắc nghiệp vụ đã bị bỏ qua. Nó hỗ trợ phát hiện, điều tra và đối chiếu việc thực thi các quy tắc đó.

## 2. Tình huống xuyên suốt: lịch sử phê duyệt hoàn tiền

Giả sử hoàn tiền R-420 có chuỗi sự kiện:

~~~text
REFUND_REQUESTED
    -> REFUND_APPROVAL_DENIED
    -> REFUND_APPROVED
    -> PAYMENT_SUBMITTED
    -> PAYMENT_CONFIRMED
~~~

Yêu cầu đầu tiên bị từ chối vì người tạo tự phê duyệt. Sau đó một người có thẩm quyền độc lập phê duyệt. Worker gửi lệnh thanh toán, nhận timeout rồi gửi lại với cùng mã nghiệp vụ. Cuối cùng hệ thống xác nhận một lần thanh toán có hiệu lực.

Hai tháng sau, khách hàng báo bị hoàn tiền sai số tiền. Để điều tra, hệ thống có thể cần:

- Số tiền và tiền tệ tại thời điểm yêu cầu và phê duyệt.
- Người tạo, người thao tác thực tế và chủ thể được đại diện, nếu có.
- Trạng thái và phiên bản đối tượng khi đưa ra từng quyết định.
- Quyền theo tenant, đối tượng và phiên bản chính sách đã sử dụng.
- Liên kết giữa quyết định phê duyệt, lệnh thanh toán, các lần retry và kết quả commit.
- Dữ kiện giải thích vì sao lần bị từ chối và lần được chấp nhận khác nhau.

Nếu chỉ giữ sự kiện PAYMENT_CONFIRMED, hệ thống biết tiền đã được chuyển nhưng khó giải thích ai đã cho phép số tiền đó. Nếu chỉ giữ log HTTP, phản hồi thành công cũng chưa đủ chứng minh giao dịch đã commit. Nếu bản ghi còn tồn tại nhưng khóa giải mã đã mất, khả năng điều tra vẫn bị phá vỡ.

Đối tượng cần được lưu giữ vì vậy không chỉ là các dòng log độc lập. Nó còn gồm những liên kết và thông tin cần thiết để hiểu chuỗi quyết định nghiệp vụ.

## 3. Phân biệt retention với các cơ chế liên quan

| Khái niệm | Mục đích | Quan hệ với audit retention |
|---|---|---|
| Application log | Chẩn đoán hoạt động và lỗi kỹ thuật | Có thể có thời hạn riêng; không mặc nhiên là bằng chứng nghiệp vụ đầy đủ |
| Audit record | Ghi nhận hành động, quyết định và kết quả | Là dữ liệu chính cần phân loại và quản lý vòng đời |
| Archive | Chuyển dữ liệu sang tầng lưu ít được truy cập hơn | Dữ liệu vẫn được giữ và vẫn cần quyền đọc, tính toàn vẹn, khả năng phục hồi |
| Backup | Khôi phục hệ thống sau sự cố | Không thay thế khả năng tra cứu audit; cũng có thể chứa dữ liệu cần hết hạn |
| Outbox | Giữ sự kiện để chuyển tiếp nhất quán sau commit | Là thành phần giao nhận; thời hạn dọn outbox khác thời hạn giữ bằng chứng cuối cùng |
| Idempotency store | Ngăn hoặc nhận diện việc xử lý lại cùng lệnh | Thời hạn có thể khác audit; xóa audit không được làm mất invariant chống xử lý trùng |
| Business ledger | Lưu trạng thái hoặc bút toán có thẩm quyền | Có thể có yêu cầu lưu riêng, không được coi là log tạm |
| Event store | Nguồn để dựng lại trạng thái trong mô hình event sourcing | Không được xóa như audit phụ nếu ứng dụng còn phụ thuộc vào lịch sử đó |
| Hold | Tạm ngăn hủy một phạm vi dữ liệu vì một lý do được xác định | Có thể chặn xóa dù thời hạn thông thường đã hết |

**Retention** trả lời “cần giữ đến khi nào”. **Archive** trả lời “giữ ở tầng nào”. **Backup** trả lời “khôi phục ra sao”. Ba câu hỏi liên quan nhưng không thay thế nhau.

Một file archive không đủ nếu không biết cách giải mã hoặc không còn schema để đọc. Một backup đầy đủ cũng chưa chắc cho phép tìm ra lịch sử của một hoàn tiền trong thời gian điều tra yêu cầu.

## 4. Xây dựng chính sách theo loại bằng chứng

Không nên đặt một TTL duy nhất cho mọi bảng và mọi loại sự kiện.

Một bản ghi phê duyệt có hiệu lực, một lần thử sai quyền và một log debug có giá trị điều tra, mức nhạy cảm và quan hệ phụ thuộc khác nhau. Chính sách cần xuất phát từ yêu cầu nghiệp vụ, thời gian có thể phát hiện sai phạm, nhu cầu xử lý tranh chấp, yêu cầu áp dụng với dữ liệu và khả năng vận hành.

### 4.1. Ma trận phân loại

| Nhóm dữ liệu | Câu hỏi quyết định thời hạn | Dữ liệu cần giữ cùng hoặc tham chiếu được |
|---|---|---|
| Từ chối quyền hoặc vi phạm invariant | Trong bao lâu cần phát hiện chuỗi thử lạm dụng? | Actor đã xác minh, hành động, phạm vi, lý do và liên kết yêu cầu |
| Phê duyệt và thay đổi trạng thái | Trong bao lâu quyết định còn phải được giải thích hoặc đối chiếu? | Trạng thái, phiên bản, dữ kiện quyết định và actor context |
| Thay đổi giá hoặc hạn mức | Khi nào có thể phát hiện hoặc xử lý hậu quả của thay đổi? | Giá trị trước/sau cần thiết, đơn vị, chính sách và lý do |
| Lệnh thanh toán và xử lý trùng | Trong bao lâu cần đối chiếu tác động thực tế và retry? | Business reference, command ID, liên kết kết quả gốc |
| Thay đổi quyền hoặc quan hệ đại diện | Có cần giải thích thẩm quyền của các hành động phát sinh sau đó không? | Phạm vi grant, phiên bản, thời điểm hiệu lực và thu hồi |
| Dữ liệu chẩn đoán | Cần bao lâu để xử lý lỗi kỹ thuật? | Chỉ các trường cần thiết cho mục tiêu chẩn đoán |
| Bản ghi hủy dữ liệu | Trong bao lâu cần chứng minh việc thực hiện chính sách retention? | Phiên bản chính sách, phạm vi, kết quả và người hoặc dịch vụ thực hiện |

Ma trận không yêu cầu giữ mọi trường mãi mãi. Có thể giảm chi tiết hoặc tách thông tin nhạy cảm thành phần có chính sách riêng, miễn là phần còn lại vẫn đáp ứng mục đích đã xác định.

### 4.2. Một chính sách phải có nhiều hơn số ngày

Ví dụ chính sách cho nhóm REFUND_DECISION cần xác định:

- Chủ sở hữu chính sách và phạm vi sự kiện áp dụng.
- Phiên bản chính sách, thời điểm có hiệu lực và cách áp dụng cho dữ liệu cũ.
- Mốc thời gian bắt đầu tính và đơn vị thời gian.
- Thời hạn giữ tối thiểu theo yêu cầu của nhóm dữ liệu.
- Các điều kiện phụ thuộc nghiệp vụ có thể ngăn xóa.
- Điều kiện và phạm vi hold.
- Thời gian tra cứu trực tuyến, thời gian ở archive và mục tiêu phục hồi.
- Điều kiện hủy, độ trễ dọn dữ liệu cho phép và cách xác nhận hoàn tất.
- Cách xử lý bản sao, index, cache, backup và dữ liệu xuất ra.
- Cách bảo vệ quyền đọc, khóa mã hóa và thông tin giải thích schema.

Nếu chưa phân loại được dữ liệu hoặc metadata retention không hợp lệ, không được coi đó là “đã hết hạn”. Cần đưa vào luồng xử lý ngoại lệ có theo dõi để xác định chính sách, đồng thời tránh để dữ liệu bị giữ vô thời hạn mà không ai xử lý.

## 5. Chọn đúng mốc thời gian bắt đầu tính

Một sự kiện thường có nhiều loại thời gian:

| Thời gian | Ý nghĩa |
|---|---|
| occurredAt | Thời điểm hành động hoặc sự kiện được cho là đã xảy ra |
| acceptedAt | Thời điểm thành phần lưu audit có thẩm quyền tiếp nhận sự kiện |
| recordedAt | Thời điểm bản ghi được lưu ở một tầng hoặc kho cụ thể |
| caseClosedAt | Thời điểm một hồ sơ nghiệp vụ liên quan kết thúc |
| archivedAt | Thời điểm chuyển sang archive |
| purgedAt | Thời điểm hoàn tất hủy trong phạm vi được ghi nhận |

Không có một mốc đúng cho mọi chính sách. Điểm bắt đầu phải được định nghĩa rõ và nguồn của nó phải đáng tin cậy.

### 5.1. Không để client quyết định thời hạn

Nếu retention được tính bằng occurredAt do client tự gửi, kẻ tấn công có thể gửi một mốc rất cũ để bản ghi lập tức đủ điều kiện xóa. Mốc quá xa trong tương lai cũng có thể gây tích lũy dữ liệu ngoài dự kiến.

Có thể chọn acceptedAt do hệ thống kiểm soát làm mốc cơ sở cho một nhóm sự kiện. Nếu chính sách cần dùng thời điểm nghiệp vụ, cần xác minh nguồn, kiểm tra sai lệch và định nghĩa cách xử lý sự kiện đến muộn.

Giữ nguyên thông tin sự kiện đến muộn khi cần điều tra, nhưng không đánh đồng thời gian tự khai với thời gian đã xác minh. Việc nhập lại archive hoặc chuyển storage không được tự ý làm thay đổi mốc retention.

### 5.2. Ví dụ tính thời hạn

Giả sử một bài toán minh họa chọn:

~~~text
Mốc cơ sở: acceptedAt do dịch vụ audit xác định
Tổng thời gian giữ: 90 ngày, mỗi ngày là 24 giờ
Tra cứu trực tuyến: 14 ngày đầu
Archive: phần thời gian còn lại
~~~

Với acceptedAt bằng 2026-01-01T00:00:00Z:

~~~text
Chuyển tầng dự kiến: 2026-01-15T00:00:00Z
Không được xóa trước: 2026-04-01T00:00:00Z
~~~

Các con số này chỉ phục vụ ví dụ tính toán. Thời hạn thực tế phải được suy ra từ yêu cầu của loại bằng chứng và hệ thống cụ thể.

“90 ngày” và “3 tháng lịch” là hai quy tắc khác nhau. Nếu chính sách dùng tháng lịch, cần định nghĩa lịch, múi giờ và cách xử lý ngày cuối tháng. Không thay tháng bằng một số giây cố định rồi cho rằng kết quả luôn tương đương.

### 5.3. Thời điểm hết hạn không phải lệnh xóa ngay

Tại 2026-04-01T00:00:00Z, bản ghi trong ví dụ mới vượt qua điều kiện thời gian. Nó vẫn có thể chưa được phép xóa nếu đang có hold, còn phụ thuộc nghiệp vụ hoặc chưa hoàn thành nghĩa vụ chuyển tiếp bằng chứng.

Chính sách cũng cần quy định độ trễ dọn dữ liệu. Ví dụ, job chạy theo lô có thể thực hiện sau mốc đủ điều kiện; cần đo độ trễ đó thay vì khẳng định dữ liệu biến mất đúng một giây cụ thể mà kiến trúc không bảo đảm.

## 6. Các invariant của vòng đời retention

Có thể mô hình hóa điều kiện lập kế hoạch xóa như sau:

~~~text
timeEligible =
    now >= effectiveDeleteNotBefore

purgeCandidate =
    timeEligible
    AND noActiveHold
    AND requiredEvidenceDependenciesResolved
    AND requiredDeliveryObligationsCompleted
    AND effectivePolicyIsKnown
~~~

Đây là điều kiện tạo ứng viên. Nó chưa thay thế kiểm tra quyền, kiểm tra lại trạng thái hiện tại và kiểm soát cạnh tranh tại bước thực sự cho phép hủy.

### 6.1. Deadline hiệu lực phải xét các phụ thuộc

Nếu chính sách có cả thời hạn cơ sở và thời hạn tính từ lúc hồ sơ đóng, một mô hình có thể là:

~~~text
baseDeadline = trustedAcceptedAt + baseWindow
caseDeadline = trustedCaseClosedAt + windowAfterClosure

effectiveDeleteNotBefore = max(baseDeadline, caseDeadline)
~~~

Công thức chỉ có ý nghĩa khi các mốc đã được xác định và chính sách thực sự dùng hai điều kiện này. Nếu hồ sơ còn mở, không bịa caseClosedAt hoặc thay bằng thời gian hiện tại. Biểu diễn rõ phụ thuộc chưa được giải quyết.

Một hold vô thời hạn cũng không nên bị thay bằng một ngày xa tùy ý. Nó là một điều kiện chặn riêng có định danh, phạm vi, lý do và vòng đời quản lý.

### 6.2. Những invariant cần giữ

1. Không hủy dữ liệu trước deadline hiệu lực.
2. Không hủy phạm vi có hold đang có hiệu lực.
3. Không xóa bằng chứng đầu vào trong khi chính sách còn yêu cầu giải thích một quyết định phụ thuộc vào nó.
4. Không dọn bản outbox chưa đáp ứng nghĩa vụ chuyển tiếp chỉ vì nó đã cũ.
5. Không báo hoàn tất hủy nếu mới xóa một bản sao trong phạm vi cần xử lý.
6. Không để job retention có quyền sửa quyết định hoặc tạo lại tác động nghiệp vụ.
7. Không để việc restore đưa dữ liệu đã hủy theo chính sách trở lại phục vụ người dùng mà không xử lý trạng thái hủy.
8. Không thay đổi chính sách hoặc metadata retention một cách âm thầm để che dấu vết.

Các invariant phải được thực thi bằng trạng thái và quyền của hệ thống, không chỉ ghi trong tài liệu vận hành.

## 7. Hold và thay đổi chính sách

### 7.1. Hold phải có phạm vi xác định

Một hold có thể được đặt cho một hồ sơ tranh chấp, nhóm giao dịch hoặc phạm vi điều tra theo yêu cầu của tổ chức. Khi có yêu cầu pháp lý áp dụng, hold cần tuân theo yêu cầu đó; bài này không ấn định thời hạn pháp lý cho một ngành hay địa phương.

Thông tin quản lý hold nên gồm:

- Hold ID và phạm vi dữ liệu được bảo vệ.
- Lý do, tham chiếu hồ sơ và người hoặc hệ thống có thẩm quyền đặt.
- Thời điểm có hiệu lực và phiên bản trạng thái.
- Chủ sở hữu chịu trách nhiệm theo dõi.
- Điều kiện xem xét lại và thông tin gỡ hold khi được phép.

Quyền đặt, thay đổi và gỡ hold phải được kiểm tra theo phạm vi đối tượng. Một nhân viên vận hành tenant t-a không được gỡ hold của tenant t-b bằng cách đổi ID trong API.

Không mặc nhiên cho phép người bị điều tra tự gỡ hold. Các thao tác nhạy cảm có thể cần tách biệt nhiệm vụ hoặc phê duyệt theo mô hình quản trị của hệ thống.

### 7.2. Gỡ hold không tự đặt lại mọi đồng hồ

Trong ví dụ 90 ngày, giả sử một hold được đặt ngày 25/03 và gỡ ngày 10/04. Dữ liệu không được xóa ngày 01/04 trong khi hold còn hiệu lực.

Sau khi gỡ hold, hệ thống phải tính lại các điều kiện hiện hành. Nếu deadline đã qua và không còn phụ thuộc nào khác, dữ liệu có thể trở thành ứng viên xóa. Không tự động “giữ thêm 90 ngày kể từ lúc gỡ hold” nếu chính sách không quy định điều đó.

Ngược lại, việc gỡ một hold không bảo đảm mọi hold khác đã hết. Cần xét tất cả hold đang có hiệu lực trên cùng phạm vi.

### 7.3. Thay đổi chính sách phải có cách chuyển tiếp

Nếu chính sách được kéo dài, cần chặn việc xóa theo deadline cũ trong giai đoạn cập nhật, rồi tính lại dữ liệu chịu ảnh hưởng. Đổi cấu hình cho sự kiện mới không tự bảo vệ được các bản ghi cũ đã nằm trong danh sách chờ xóa.

Nếu chính sách được rút ngắn, cần xác định rõ nhóm dữ liệu nào được áp dụng, kiểm tra hold và phụ thuộc, sau đó thực hiện qua luồng hủy có theo dõi. Một thay đổi cấu hình không nên lập tức làm job xóa hàng loạt dữ liệu mà không có khả năng đánh giá phạm vi.

Bản ghi audit có thể giữ phiên bản chính sách retention lúc tiếp nhận. Deadline hiệu lực hiện tại có thể nằm trong metadata quản lý riêng, được kiểm soát phiên bản và lưu lịch sử thay đổi. Không cần sửa nội dung sự kiện nghiệp vụ đã được niêm phong để áp dụng một chính sách mới.

Cần phân biệt:

- **Decision policy version:** chính sách đã quyết định cho phép hoặc từ chối hành động nghiệp vụ.
- **Retention policy version:** chính sách quản lý thời gian giữ bằng chứng của hành động đó.

Hai phiên bản trả lời hai câu hỏi khác nhau.

## 8. Từ ghi nhận đến archive và hủy

~~~mermaid
flowchart TD
    A["Ghi audit bền vững và phân loại"] --> B["Lưu ở tầng phục vụ tra cứu"]
    B --> C{"Đến thời điểm chuyển tầng?"}
    C -- "Có" --> D["Archive và xác minh khả năng đọc lại"]
    C -- "Chưa" --> E["Theo dõi deadline và phụ thuộc"]
    D --> E
    E --> F{"Đủ điều kiện lập kế hoạch xóa?"}
    F -- "Chưa" --> E
    F -- "Có" --> G["Tạo ứng viên với phiên bản policy và hold"]
    G --> H{"Kiểm tra lại và cho phép hủy"}
    H -- "Điều kiện đã đổi" --> E
    H -- "Hợp lệ" --> I["Hủy theo phạm vi và theo dõi từng bản sao"]
    I --> J{"Đã xác minh đủ phạm vi?"}
    J -- "Chưa" --> K["Retry có kiểm soát hoặc xử lý ngoại lệ"]
    K --> J
    J -- "Đủ" --> L["Ghi biên nhận hủy và hoàn tất"]
~~~

### 8.1. Archive vẫn phải là bằng chứng dùng được

Trước khi xóa bản trực tuyến sau khi archive, cần xác minh theo yêu cầu của hệ thống:

- Dữ liệu đã được ghi đầy đủ ở đích.
- Nội dung hoặc manifest có thể kiểm tra tính toàn vẹn.
- Có thể tìm ra dữ liệu theo các định danh cần cho điều tra.
- Khóa giải mã và thông tin schema còn được quản lý.
- Quyền truy cập ở archive không mở rộng hơn phạm vi được phép.
- Quy trình phục hồi thực sự đọc được dữ liệu trong thời gian yêu cầu.

Một phản hồi “upload thành công” chưa tự chứng minh toàn bộ chuỗi này. Checksum giúp phát hiện thay đổi nội dung nhưng không thay thế việc kiểm tra nguồn phát, khóa bảo vệ hoặc khả năng đọc lại.

Nếu tra cứu trực tuyến phải trả lời trong vài giây nhưng archive mất nhiều giờ để phục hồi, giao diện và quy trình điều tra cần phản ánh đúng khả năng đó. Không nên đánh đồng “dữ liệu còn tồn tại” với “có thể dùng ngay”.

### 8.2. Giữ đủ ngữ nghĩa để đọc dữ liệu cũ

Các ID và phiên bản chỉ hữu ích khi còn cách giải thích:

- SchemaVersion cần có bộ đọc hoặc tài liệu định dạng tương ứng.
- PolicyVersion cần trỏ tới quy tắc được giữ lại, nếu việc điều tra phụ thuộc vào quy tắc đó.
- Định danh actor cần có cách phân giải được kiểm soát, hoặc snapshot tối thiểu đủ cho mục đích điều tra.
- Đơn vị tiền tệ, trạng thái và mã lý do cần có ý nghĩa ổn định.

Không nhất thiết giữ nguyên toàn bộ hồ sơ cá nhân hoặc toàn bộ cấu hình hệ thống. Cần chọn tập bằng chứng tối thiểu đủ để giải thích quyết định, đồng thời bảo vệ việc truy cập vào dữ liệu tham chiếu.

### 8.3. Append-only không có nghĩa phải giữ vô hạn

Trong thời gian được giữ, dữ liệu audit có thể được thiết kế chỉ cho phép thêm, hạn chế sửa hoặc phát hiện sửa đổi. Khi hết điều kiện lưu giữ, một luồng hủy có thẩm quyền vẫn có thể loại bỏ dữ liệu theo chính sách.

Nếu dùng chuỗi hash, việc xóa một đoạn lịch sử có thể làm mất khả năng kiểm chứng các đoạn còn lại. Cần thiết kế ranh giới niêm phong, manifest hoặc checkpoint phù hợp và giữ thông tin kiểm chứng cần thiết.

Không tự nối lại chuỗi rồi tuyên bố rằng lịch sử chưa từng bị thay đổi. Phải phân biệt rõ việc hủy theo chính sách với việc chỉnh sửa trái phép.

## 9. Thiết kế tác vụ xóa không phá invariant

### 9.1. Điều kiện Java minh họa chỉ dùng để lập kế hoạch

Mã dưới đây là ví dụ theo phong cách Java, không phải một job xóa hoàn chỉnh:

~~~java
record RetentionSnapshot(
    String eventId,
    Instant effectiveDeleteNotBefore,
    boolean activeHold,
    boolean unresolvedEvidenceDependency,
    boolean requiredDeliveryCompleted,
    boolean effectivePolicyKnown,
    long policyRevision,
    long holdRevision
) {}

boolean canPlanPurge(RetentionSnapshot snapshot, Instant now) {
    return snapshot.effectivePolicyKnown()
        && snapshot.effectiveDeleteNotBefore() != null
        && !now.isBefore(snapshot.effectiveDeleteNotBefore())
        && !snapshot.activeHold()
        && !snapshot.unresolvedEvidenceDependency()
        && snapshot.requiredDeliveryCompleted();
}
~~~

Tên hàm **canPlanPurge** thể hiện giới hạn: kết quả đúng chỉ có nghĩa là có thể đưa bản ghi vào danh sách ứng viên tại thời điểm chụp snapshot.

Không được giữ kết quả boolean này nhiều giờ rồi coi đó là quyền xóa vĩnh viễn. Policy, hold và phụ thuộc có thể đã thay đổi.

### 9.2. Luồng thực thi cần kiểm soát cạnh tranh

Một quy trình hủy có thể tổ chức theo các bước:

1. Chọn ứng viên, ghi rõ phạm vi và các phiên bản trạng thái đã quan sát.
2. Tại bước cho phép hủy, đọc lại chính sách, hold, phụ thuộc và deadline từ nguồn có thẩm quyền.
3. Dùng cơ chế đồng bộ phù hợp để quyết định hủy và việc đăng ký hold không bỏ qua nhau.
4. Ghi trạng thái cho phép hủy bền vững trước khi thực hiện tác động không thể đảo ngược.
5. Thực hiện hủy theo mã tác vụ ổn định và theo dõi từng đích lưu.
6. Xác minh kết quả, ghi biên nhận hoặc trạng thái chưa hoàn tất.
7. Retry theo cách không xóa nhầm phạm vi mới và không báo hoàn tất nhiều lần với ngữ nghĩa sai.

Cần định nghĩa điểm bắt đầu hủy không thể đảo ngược trong hợp đồng hệ thống. Một hold đã được đăng ký thành công trước điểm đó phải ngăn được hủy. Nếu phạm vi đã vượt điểm đó, API đặt hold phải trả trạng thái phù hợp, không được hứa rằng dữ liệu đã được bảo vệ.

Một phép kiểm tra hold ở database rồi xóa object ở storage ngoài database không tạo thành transaction nguyên tử. Cơ chế điều phối phải giải quyết khoảng trống này, chẳng hạn bằng một state machine quản lý quyền bắt đầu hủy và thứ tự các lệnh có thẩm quyền. Chỉ thêm bước “check lại một lần” vẫn có thể còn race condition.

Không giữ transaction database kéo dài nhiều giờ chỉ để chờ archive hoặc storage phản hồi. Thiết kế cần có trạng thái bền vững, phiên bản hoặc cơ chế khóa phù hợp với ranh giới thực tế.

### 9.3. Quyền của dịch vụ retention phải có giới hạn

Dịch vụ retention có thể cần quyền xóa dữ liệu thuộc phạm vi chính sách, nhưng không vì vậy mà được:

- Sửa số tiền hoặc trạng thái hoàn tiền.
- Tạo quyết định phê duyệt mới.
- Gỡ mọi hold.
- Rút ngắn deadline bằng cách sửa metadata tùy ý.
- Truy xuất và xuất toàn bộ dữ liệu nhạy cảm ngoài nhu cầu công việc.

Tách quyền quản lý chính sách, đặt hold, thi hành hủy và xem dữ liệu theo mô hình trách nhiệm của hệ thống. Mỗi lệnh quản trị cũng cần actor context và audit tương ứng.

### 9.4. Xóa theo partition phải xét mọi bản ghi bên trong

Giả sử một partition chứa audit của nhiều tenant trong cùng ngày. Một tenant có dữ liệu hết hạn, tenant khác còn hold. Xóa cả partition theo ngày có thể làm mất bằng chứng đang được bảo vệ.

Chỉ được hủy cả partition hoặc object gộp khi mọi phần dữ liệu bên trong đều đủ điều kiện. Chỉ dùng deadline nhỏ nhất của các bản ghi là sai; ngay cả deadline lớn nhất cũng chưa thay thế việc kiểm tra hold và phụ thuộc.

Có thể thiết kế cách phân vùng theo lớp retention hoặc phạm vi quản trị để giảm xung đột. Nếu phải tách dữ liệu đang được giữ khỏi một khối, cần một quy trình bảo toàn được xác minh trước khi hủy khối gốc, không chỉ một thao tác sao chép chưa kiểm tra.

## 10. Outbox, transaction và idempotency có vòng đời riêng

### 10.1. Không dọn outbox chỉ bằng tuổi bản ghi

Outbox thường cùng commit với thay đổi nghiệp vụ. Nếu job xóa các bản ghi quá cũ trong khi publisher chưa chuyển tiếp thành công, thay đổi nghiệp vụ còn tồn tại nhưng audit ở kho đích bị thiếu.

Dọn outbox cần dựa trên trạng thái giao nhận và nghĩa vụ đã định nghĩa, không chỉ dựa vào createdAt. Việc đã gửi tới broker cũng chưa mặc nhiên bằng việc kho audit cuối cùng đã ghi bền vững nếu hợp đồng hệ thống yêu cầu mức bảo đảm đó.

Nếu outbox chỉ là tầng giao nhận, có thể dọn sau khi hoàn tất hợp đồng chuyển tiếp và thời gian hỗ trợ vận hành cần thiết. Nếu nó đồng thời là bản bằng chứng có thẩm quyền duy nhất, phải quản lý retention như bằng chứng, không coi nó là hàng đợi tạm.

### 10.2. Audit TTL không phải idempotency TTL

Giả sử bản ghi chống trùng của lệnh thanh toán hết hạn sớm hơn audit. Kẻ tấn công gửi lại một lệnh cũ. Việc audit vẫn ghi rằng lệnh từng được xử lý không tự ngăn hệ thống thực hiện lại, trừ khi có cơ chế kiểm tra có thẩm quyền được thiết kế cho mục đích đó.

Ngược lại, xóa một phần audit không được làm mất ràng buộc nghiệp vụ như “mỗi hoàn tiền chỉ thanh toán một lần”.

Cần xác định riêng:

- Cửa sổ nhận retry và thời hạn lưu kết quả idempotency.
- Phạm vi khóa chống trùng theo tenant, hành động và chủ thể phù hợp.
- Ràng buộc bền vững trên business reference hoặc trạng thái nghiệp vụ.
- Thời hạn giữ bằng chứng về các lần thử và kết quả có hiệu lực.

Hết hạn key không đồng nghĩa một yêu cầu cũ được phép tạo thêm tác động. State machine, unique constraint hoặc ledger phải tiếp tục giữ invariant theo mô hình nghiệp vụ.

### 10.3. Giữ liên kết thay vì giữ mọi lần thử giống nhau

Có thể có nhiều sự kiện kỹ thuật cho một command. Chính sách có thể phân biệt bằng chứng về tác động đã commit với các lần giao nhận lặp, miễn là vẫn giải thích được quan hệ giữa chúng.

Nếu rút gọn dữ liệu, cần nêu rõ thông tin nào được giữ và thông tin nào không còn. Không sửa lịch sử actor của sự kiện gốc thành actor của lần gọi gần nhất, cũng không tổng hợp theo cách làm mất dấu những lần bị từ chối do khác quyền hoặc khác tenant.

## 11. Bản sao, backup và khóa mã hóa

### 11.1. Phạm vi hủy phải được liệt kê

Dữ liệu audit có thể xuất hiện ở:

- Bảng chính và các replica.
- Search index hoặc hệ thống phân tích.
- Object archive và phiên bản object cũ.
- Cache, file tạm và gói export.
- Kho dữ liệu phục vụ điều tra.
- Backup và các môi trường khôi phục.

Một thao tác DELETE ở bảng chính không chứng minh tất cả bản sao đã biến mất. Chính sách cần chỉ rõ hệ thống nào phải xóa ngay, hệ thống nào hết hạn theo vòng đời backup và cách kiểm soát việc phục hồi.

Với cơ chế xóa bất đồng bộ hoặc nhất quán cuối cùng, cần có trạng thái tiến độ và giới hạn độ trễ. Không báo “đã hủy toàn bộ” khi mới gửi yêu cầu xóa.

### 11.2. Backup không được làm dữ liệu bị hủy xuất hiện trở lại

Không phải mọi kiến trúc đều có thể xóa chọn lọc một sự kiện trong một backup bất biến. Có thể quản lý thời hạn của backup và hạn chế phục hồi, nhưng phải mô tả đúng giới hạn đó.

Khi restore một snapshot cũ, dữ liệu từng được hủy theo chính sách có thể xuất hiện trở lại. Quy trình khôi phục cần đối chiếu trạng thái hủy hoặc áp dụng lại các quyết định hủy trước khi đưa dữ liệu vào phục vụ.

Thông tin đối chiếu này cũng là dữ liệu phải được quản lý: nó cần đủ để ngăn tái xuất hiện, nhưng không nên chứa nguyên bản dữ liệu đã hủy. Có thể dùng định danh và thông tin phạm vi tối thiểu theo thiết kế.

Nếu dữ liệu đang bị hold, kế hoạch backup và restore phải bảo đảm vẫn còn bản bằng chứng cần giữ. Không được để mọi bản có thể đọc đều hết hạn trong khi dashboard vẫn hiển thị hold còn hiệu lực.

### 11.3. Vòng đời khóa phải khớp vòng đời dữ liệu

Archive mã hóa có thể mất giá trị nếu khóa giải mã bị hủy quá sớm. Cần giữ khả năng giải mã cho dữ liệu còn phải lưu và kiểm tra việc phục hồi khóa theo yêu cầu.

Hủy khóa có thể là một phần của cơ chế hủy dữ liệu, nhưng chỉ phù hợp khi:

- Phạm vi khóa đủ hẹp để không làm mất dữ liệu khác còn phải giữ.
- Các bản sao khóa và đường khôi phục khóa được quản lý.
- Không còn bản plaintext hoặc bản được mã hóa bằng khóa khác ngoài phạm vi xử lý.
- Hold và các điều kiện phụ thuộc đã được giải quyết.

Một khóa dùng chung cho nhiều tenant không thể bị hủy để xóa một tenant mà không ảnh hưởng tenant khác.

Khóa giải mã và khóa dùng để kiểm tra chữ ký có vai trò khác nhau. Nếu bằng chứng được ký, hệ thống có thể cần giữ public key, thông tin phiên bản thuật toán và manifest để xác minh dữ liệu còn được giữ. Không coi “đã xoay khóa” là đồng nghĩa “dữ liệu cũ đã được hủy” hoặc “bằng chứng cũ không còn cần kiểm tra”.

## 12. Biên nhận hủy và giám sát retention

### 12.1. Biên nhận phải phản ánh đúng kết quả

Một biên nhận hủy có thể gồm:

~~~json
{
  "dispositionId": "disp-2048",
  "policyId": "refund-audit-retention",
  "policyRevision": 6,
  "scopeReference": "retention-batch-351",
  "authorizedAt": "2026-04-02T01:00:00Z",
  "completedAt": "2026-04-02T01:03:12Z",
  "executorServiceId": "audit-retention-worker",
  "deletedRecordCount": 1840,
  "targets": [
    {
      "name": "primary-audit-store",
      "status": "VERIFIED"
    },
    {
      "name": "audit-search-index",
      "status": "VERIFIED"
    }
  ],
  "outcome": "COMPLETED_FOR_DECLARED_SCOPE"
}
~~~

Ví dụ chỉ tuyên bố hoàn tất cho phạm vi đã khai báo. Nếu còn backup chờ hết hạn theo chính sách, trạng thái và báo cáo phải thể hiện điều đó theo hợp đồng quản lý dữ liệu.

Không chép toàn bộ actor context, payload và dữ liệu cá nhân đã bị hủy vào biên nhận. Nếu làm vậy, hệ thống chỉ chuyển dữ liệu sang một kho mới rồi gọi là “đã xóa”.

Bản ghi hủy có chính sách retention riêng. Cần tránh chuỗi ghi nhận vô hạn khi cứ hủy một biên nhận lại tạo một bản sao đầy đủ của nó.

Nếu tiến trình crash sau khi storage đã xóa nhưng trước khi ghi COMPLETED, lần chạy sau phải đối chiếu trạng thái và hoàn tất cùng dispositionId. Không xóa sang phạm vi mới hoặc ghi nhận một lần hủy khác chỉ vì tác vụ được retry.

### 12.2. Chỉ số vận hành cần trả lời câu hỏi cụ thể

| Chỉ số | Điều cần phát hiện |
|---|---|
| Số bản ghi đủ điều kiện nhưng chưa xử lý | Job dọn dữ liệu bị chậm hoặc ngừng |
| Tuổi của ứng viên quá hạn lâu nhất | Có lớp dữ liệu bị bỏ sót khỏi vòng đời |
| Số bản ghi chưa xác định chính sách | Lỗi phân loại hoặc thay đổi schema |
| Số ứng viên bị chặn bởi hold hoặc phụ thuộc | Khối lượng bằng chứng cần tiếp tục giữ |
| Lỗi chuyển archive và lỗi đọc lại | Dữ liệu tồn tại nhưng có nguy cơ không dùng được |
| Số bản sao chưa xác minh hủy | Việc hoàn tất giữa các kho chưa đồng đều |
| Outbox tồn đọng | Nghĩa vụ chuyển tiếp có thể chưa hoàn thành |
| Kết quả restore có áp dụng trạng thái hủy | Nguy cơ dữ liệu tái xuất hiện |
| Thao tác thay đổi policy hoặc hold bất thường | Lạm dụng quyền quản trị vòng đời |

Theo dõi hold lâu ngày để chủ sở hữu xem xét không đồng nghĩa tự gỡ hold theo tuổi. Chỉ được gỡ khi điều kiện và thẩm quyền tương ứng được đáp ứng.

## 13. Tình huống kiểm thử khi triển khai

Các tình huống sau dùng để thiết kế kiểm thử cho một hệ thống thực tế; mã minh họa trong bài chưa phải triển khai đã được chạy.

| Tình huống | Kết quả cần xác minh |
|---|---|
| now đứng ngay trước deadline | Không tạo quyền hủy trước thời điểm được phép |
| now đúng tại deadline | Chỉ vượt điều kiện thời gian; vẫn xét hold và phụ thuộc |
| Client gửi occurredAt rất cũ | Không làm bản ghi bị xóa ngay bằng một mốc tự khai |
| Sự kiện đến muộn hoặc nhập lại archive | Mốc retention theo chính sách, không vô tình rút ngắn hoặc kéo dài |
| Job đã lấy ứng viên rồi xuất hiện hold | Hold được chấp nhận trước điểm hủy không thể đảo ngược phải ngăn hủy |
| Gỡ một trong nhiều hold | Các hold còn hiệu lực vẫn bảo vệ dữ liệu |
| Policy kéo dài khi job đang chạy | Không xóa theo snapshot deadline cũ |
| Partition có bản ghi đang bị giữ | Không xóa toàn bộ partition chỉ vì phần lớn dữ liệu hết hạn |
| Archive ghi thiếu hoặc không giải mã được | Không xóa bản còn đọc được trước khi đáp ứng điều kiện chuyển tầng |
| Xóa bản ghi được quyết định khác tham chiếu | Không phá khả năng giải thích khi phụ thuộc vẫn cần giữ |
| Outbox cũ nhưng chưa hoàn tất giao nhận | Không mất sự kiện cần chuyển tiếp |
| Idempotency key hết hạn rồi nhận lệnh cũ | Không tạo lại tác động trái invariant nghiệp vụ |
| Worker crash sau khi đã xóa một đích | Retry đúng disposition, theo dõi phần chưa hoàn tất |
| Search index còn dữ liệu sau khi bảng đã xóa | Không báo hoàn tất ngoài phạm vi đã xác minh |
| Restore backup chứa dữ liệu đã bị hủy | Áp dụng trạng thái hủy trước khi phục vụ dữ liệu |
| Khóa mã hóa dùng chung nhiều phạm vi | Không hủy khóa làm mất dữ liệu còn phải giữ |
| Tenant t-a đổi ID để gỡ hold của t-b | Bị chặn bởi quyền theo đối tượng |
| Payload chứa credential hoặc dữ liệu dư thừa | Không đưa chúng vào audit hoặc biên nhận hủy |

Đối chiếu cả trạng thái nghiệp vụ, kho bằng chứng và trạng thái tác vụ retention. Kiểm tra “job đã chạy thành công” không đủ nếu archive không đọc được, hold bị bỏ qua hoặc backup làm dữ liệu xuất hiện trở lại.

## 14. Checklist thiết kế một chính sách audit retention

Trước khi triển khai cho hành động sửa giá, phê duyệt, thanh toán hoặc thay đổi quyền, hãy xác định:

1. Những loại bằng chứng nào cần giữ để giải thích quyết định và tác động đã commit?
2. Mỗi loại bắt đầu tính thời gian từ mốc nào, mốc đó do ai xác nhận?
3. Deadline, đơn vị thời gian và độ trễ hủy cho phép đã được định nghĩa rõ chưa?
4. Có giữ được actor context, schema, chính sách và các liên kết cần thiết trong thời gian điều tra không?
5. Hold được đặt, gỡ và kiểm tra theo quyền nào; cạnh tranh với việc hủy được giải quyết ra sao?
6. Khi policy thay đổi, dữ liệu cũ và ứng viên đang chờ xóa được xử lý thế nào?
7. Archive có thể tìm, đọc và xác minh được với quyền và khóa phù hợp không?
8. Outbox, idempotency store và ledger có vòng đời riêng mà vẫn giữ invariant nghiệp vụ không?
9. Mọi bản sao, backup, index và export thuộc phạm vi quản lý đã có cách hết hạn hoặc xử lý chưa?
10. Biên nhận có phản ánh đúng phạm vi hoàn tất mà không sao chép lại dữ liệu cần hủy không?

Một chính sách audit retention có giá trị khi hệ thống vừa giữ được bằng chứng cần thiết, vừa giải thích được vì sao một dữ liệu còn tồn tại hoặc đã được hủy. Điều đó đòi hỏi thời gian, quyền theo đối tượng, state machine, transaction và cơ chế xử lý trùng cùng tuân theo các điều kiện nghiệp vụ đã xác định.

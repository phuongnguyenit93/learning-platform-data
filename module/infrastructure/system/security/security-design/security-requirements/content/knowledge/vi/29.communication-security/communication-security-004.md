# Secure message transport — Đặc tả yêu cầu truyền thông điệp an toàn

## 1. Mục tiêu bảo mật của đường truyền thông điệp

Secure message transport là việc bảo vệ các kênh truyền thông điệp để đúng chủ thể gửi, nhận và xử lý dữ liệu qua những ranh giới tin cậy đã xác định. Mục tiêu bao gồm tính bí mật trên đường truyền, tính toàn vẹn, xác thực đầu kết nối và kiểm soát quyền sử dụng kênh.

Trong hệ thống bất đồng bộ, một thông điệp có thể đi qua producer, proxy, broker, hàng đợi, consumer, kênh retry và dead-letter queue. Mỗi chặng có danh tính, quyền, cơ chế mã hóa và điểm kết thúc bảo vệ riêng.

Trong module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, yêu cầu không dừng ở câu “bật TLS cho message broker”. Cần chuyển mô hình đe dọa thành những điều kiểm chứng được:

- Những chặng và điểm vào nào thuộc phạm vi bảo vệ?
- Mỗi đầu kết nối xác minh danh tính bên kia bằng cách nào?
- Danh tính nào được publish, consume hoặc quản trị những tài nguyên nào?
- Khi chứng thư, credential hoặc quyền bị thu hồi, kết nối đang tồn tại bị xử lý ra sao?
- Failover, retry và DLQ có giữ cùng mức bảo vệ không?
- TLS bảo vệ tới đâu, và cần cơ chế nào cho nội dung sau điểm kết thúc TLS?
- Bằng chứng nào chứng minh không có đường plaintext hoặc đường truy cập ngoài quyền?

Bài học lấy ví dụ một cổng hồ sơ gửi yêu cầu tạo bản xuất tới worker qua broker. Các ngưỡng số là giả định minh họa cho việc viết yêu cầu, không phải cấu hình bắt buộc của một sản phẩm cụ thể.

## 2. Xác định kiến trúc và ranh giới tin cậy

### 2.1. Luồng thông điệp minh họa

```text
Ứng dụng producer
        |
        | Kênh đã xác thực và bảo vệ
        v
Proxy / gateway nếu có
        |
        | Kênh tiếp theo được đặc tả riêng
        v
Broker / topic / queue
        |
        +--> Retry hoặc DLQ theo policy
        |
        | Kênh đã xác thực và bảo vệ
        v
Worker consumer
        |
        v
Kiểm tra thông điệp, quyền nghiệp vụ và thực hiện tác vụ
```

Một đường TLS từ producer tới proxy không tự bảo vệ chặng proxy tới broker. Tương tự, mã hóa chặng producer–broker không nói lên consumer đang dùng kênh gì.

Cần liệt kê các chặng thực tế, gồm kết nối giữa node broker nếu dữ liệu đi qua đó, replication liên vùng, client discovery, endpoint quản trị và đường chuyển tiếp sang hệ thống khác.

### 2.2. Điểm kết thúc TLS xác định phạm vi bảo vệ

Tại điểm kết thúc TLS, dữ liệu thường được giải mã để thành phần nhận sử dụng. Broker, proxy hoặc ứng dụng có quyền ở điểm đó có thể tiếp cận nội dung theo thiết kế.

Nếu mô hình đe dọa yêu cầu broker không được đọc payload, cần xem xét bảo vệ nội dung tới consumer, cùng quản lý khóa và quyền tương ứng. TLS từng chặng vẫn cần thiết cho phần kênh của nó.

Sidecar hoặc service mesh cũng cần được mô tả theo điểm kết thúc thực tế. Mã hóa giữa hai proxy không tự chứng minh dữ liệu đã được bảo vệ khỏi mọi chủ thể trên host hoặc khỏi một endpoint bị xâm nhập.

### 2.3. Đường phụ phải được kiểm kê

| Đường | Vì sao cần xét |
| --- | --- |
| Publish và consume chính | Mang dữ liệu và lệnh nghiệp vụ |
| Discovery, bootstrap, redirect/failover | Có thể đưa client tới endpoint khác cấu hình ban đầu |
| Kết nối giữa broker | Có thể mang bản sao hoặc chuyển tiếp thông điệp |
| Quản trị, tạo queue và đổi ACL | Có thể thay đổi toàn bộ ranh giới quyền |
| Retry, DLQ và công cụ redrive | Có thể chứa cùng dữ liệu nhạy cảm và tạo tác dụng lặp |
| Metrics, trace và hỗ trợ vận hành | Có thể vô tình ghi payload hoặc credential |
| Backup, export hoặc mirror dữ liệu broker | Đưa nội dung ra ngoài kênh truyền ban đầu |

Phạm vi phải dựa trên kiến trúc đang chạy. Một danh sách endpoint trong tài liệu chưa đủ nếu broker quảng bá thêm địa chỉ hoặc client tự phát hiện node khác.

## 3. Phân biệt các lớp bảo vệ

| Lớp | Mục tiêu chính | Bảo đảm cần bổ sung |
| --- | --- | --- |
| Mã hóa kênh | Bảo vệ dữ liệu trên chặng truyền được xác định | Danh tính đầu kết nối, quyền sử dụng và bảo vệ sau giải mã |
| Xác thực đầu kết nối | Biết bên kết nối là danh tính nào theo mô hình tin cậy | Danh tính đó được làm gì trên queue/topic nào |
| Phân quyền broker | Giới hạn publish, consume, tạo tài nguyên hoặc quản trị | Kiểm tra nội dung và quyền nghiệp vụ tại consumer |
| Mã hóa lưu trữ | Bảo vệ dữ liệu lưu theo cơ chế đã chọn | Quyền người vận hành, đường export và khả năng giải mã |
| Chữ ký hoặc xác thực nội dung khi được yêu cầu | Kiểm chứng nguồn và phần nội dung được bảo vệ | Quyền hiện hành, replay, thời hạn và tác dụng nghiệp vụ |
| Mã hóa payload tới nơi nhận | Giới hạn thành phần có thể đọc payload | Metadata còn lộ, quản lý khóa và quyền consumer |
| Idempotency/kiểm soát replay | Tránh tạo tác dụng không được phép từ thông điệp lặp | Xác thực, phân quyền và tính đúng của dữ liệu |
| Cơ chế giao nhận tin cậy | Giảm mất việc và hỗ trợ retry | Retry không vượt quyền hoặc làm lộ dữ liệu |

Một checksum thông thường không chứng minh người gửi hợp lệ nếu kẻ gửi có thể tính lại checksum. Một thông điệp được ký hợp lệ cũng có thể chứa yêu cầu mà người gửi không có quyền thực hiện.

Bảo vệ đường truyền, nội dung và thao tác nghiệp vụ phải được liên kết, nhưng mỗi lớp cần tiêu chí nghiệm thu riêng.

## 4. Mô hình đe dọa cho message transport

| Kịch bản | Tác động | Hướng yêu cầu |
| --- | --- | --- |
| Nghe lén trên một chặng không được bảo vệ | Lộ dữ liệu, token hoặc nội dung nghiệp vụ | Bảo vệ mọi chặng trong phạm vi, không chỉ endpoint đầu tiên |
| Client chấp nhận sai danh tính máy chủ | Gửi dữ liệu cho endpoint không đúng | Kiểm tra trust và danh tính đích dự kiến |
| Tắt kiểm tra chứng thư để xử lý lỗi | Mất xác thực đầu kết nối | Không có chế độ bỏ xác minh ngoài policy; lỗi phải được xử lý có kiểm soát |
| Producer dùng credential chung | Khó truy vết, quyền quá rộng | Danh tính dịch vụ riêng và quyền tối thiểu |
| Producer publish sang tenant/topic khác | Lộ dữ liệu hoặc tạo lệnh ngoài phạm vi | ACL và kiểm tra routing gắn với danh tính đã xác thực |
| Consumer đọc mọi queue | Nhận nội dung không thuộc nhiệm vụ | Tách quyền theo tài nguyên và vai trò |
| Dữ liệu nhạy cảm vào DLQ rộng quyền | Lộ nội dung qua kênh vận hành | DLQ giữ phân loại, quyền và retention phù hợp |
| Failover tới listener plaintext | Hạ mức bảo vệ khi sự cố | Chính sách kết nối nhất quán, không fallback thiếu bảo vệ |
| Credential bị thu hồi nhưng phiên còn chạy | Tiếp tục publish/consume ngoài thời hạn cho phép | Đặc tả hiệu lực thu hồi đối với cả kết nối hiện hữu |
| Thông điệp bị giao lại hoặc redrive | Tác dụng nghiệp vụ lặp | Định danh, trạng thái và chống lặp ở consumer |
| Payload giả trường producer/tenant | Consumer tin dữ kiện tự khai báo | Ràng buộc dữ kiện với nguồn được xác minh và quyền nghiệp vụ |
| Log hoặc trace ghi toàn bộ message | Rò rỉ ngoài kênh được bảo vệ | Giới hạn nội dung log và quyền công cụ quan sát |

Mô hình đe dọa cần xác định có tin broker/operator hay không, có chia sẻ broker giữa tenant hay không và có kết nối tới bên ngoài tổ chức hay không. Những giả định này quyết định có cần bảo vệ nội dung đầu cuối hoặc phân tách sâu hơn.

## 5. Xác thực kết nối và chống hạ cấp

### 5.1. Xác minh đúng máy chủ

Với mô hình chứng thư được chọn, client phải kiểm tra trust policy, hiệu lực và danh tính đích dự kiến. Danh tính đó có thể là tên máy chủ hoặc định danh dịch vụ theo cơ chế nền tảng.

Một chứng thư có chữ ký được tin nhưng thuộc đích khác không đủ để gửi dữ liệu. Tương tự, kết nối có mã hóa nhưng bỏ xác minh đầu bên kia không đáp ứng mục tiêu xác thực dịch vụ.

Không dùng cờ bỏ kiểm tra chứng thư hoặc chấp nhận mọi danh tính như cách xử lý vận hành bình thường. Nếu có trust đặc thù, pinning hoặc mô hình danh tính khác, phải đặc tả chính sách, vòng đời và kiểm thử tương ứng.

### 5.2. Xác thực client hoặc workload

Broker cần xác thực producer và consumer bằng cơ chế được phê duyệt, chẳng hạn chứng thư client hoặc credential/token của workload theo kiến trúc.

Khi dùng xác thực hai chiều, phải ánh xạ danh tính chứng thư tới principal và quyền. Việc bắt tay thành công không tự tạo ACL đúng.

Không dùng cùng một danh tính quyền rộng cho producer, consumer và công cụ quản trị nếu trách nhiệm có thể tách. Mỗi ứng dụng cần quyền phù hợp nhiệm vụ, khả năng luân chuyển và dấu vết truy vết.

### 5.3. Hồ sơ bảo vệ kênh

Yêu cầu nên tham chiếu hồ sơ mật mã được phê duyệt của dự án, trong đó xác định giao thức, thuật toán, cấu hình và điều kiện tương thích được phép.

Cần kiểm chứng cấu hình hiệu lực trên cả client và server, không chỉ một phía. Endpoint cấu hình đúng nhưng client còn được phép chuyển sang listener không bảo vệ vẫn tạo khoảng trống.

Không tự ghim một cấu hình sản phẩm chưa được kiểm tra vào yêu cầu chung. Điều cần nghiệm thu là các kết nối trong phạm vi chỉ dùng cấu hình được phê duyệt và từ chối cấu hình bị cấm.

### 5.4. Failover không được giảm bảo vệ

Nếu endpoint chính lỗi, client chỉ được chuyển sang đích dự phòng có cùng yêu cầu xác thực và bảo vệ. Không chuyển sang plaintext hoặc bỏ xác minh để “giữ hoạt động”.

Địa chỉ discovery, metadata node và DNS đều phải được xử lý theo mô hình tin cậy. Client cần kiểm tra danh tính thực tế ở từng kết nối mới, không chỉ tin rằng endpoint đó đến từ danh sách bootstrap.

## 6. Phân quyền publish, consume và quản trị

### 6.1. Quyền kỹ thuật cần tách theo thao tác

Một ma trận minh họa cho luồng xuất hồ sơ:

| Principal | Publish | Consume | Retry/DLQ | Quản trị |
| --- | --- | --- | --- | --- |
| export-api | Chỉ tài nguyên yêu cầu xuất được giao | Không nếu không cần | Không mặc nhiên đọc DLQ | Không |
| export-worker | Chỉ tài nguyên kết quả theo nhiệm vụ | Chỉ yêu cầu xuất thuộc phạm vi | Theo quyền xử lý được giao | Không |
| dlq-reviewer | Không tự publish vào luồng chính | Đọc tập DLQ được giao | Xem xét theo phạm vi và audit | Không |
| redrive-service | Publish lại theo quy trình đã duyệt | Chỉ nguồn redrive được phép | Đúng nguồn/đích và điều kiện | Không sửa ACL |
| broker-admin | Theo nhiệm vụ vận hành được duyệt | Không mặc nhiên có nhu cầu đọc payload | Theo chính sách | Có quyền quản trị được kiểm soát |

Quyền thực tế phụ thuộc nền tảng. Nếu quyền admin kỹ thuật cho phép đọc dữ liệu hoặc tự cấp quyền, phải ghi nhận trong mô hình đe dọa và bổ sung kiểm soát phù hợp; bảng phân vai không tự loại khả năng đó.

### 6.2. Routing phải gắn với principal có thẩm quyền

Producer không được tự chọn tenant hoặc đích ngoài phạm vi rồi trông chờ consumer sửa lại. Broker cần thực thi quyền trên tài nguyên mà nền tảng hỗ trợ; ứng dụng cần kiểm tra các thuộc tính chi tiết ngoài khả năng ACL của broker.

Ví dụ, broker có thể giới hạn topic/queue, còn điều kiện về event type hoặc quyền với từng hồ sơ cần thực thi ở lớp ứng dụng. Không tuyên bố broker kiểm soát một trường payload nếu nó không thực sự làm việc đó.

Tên topic chứa tenant không tự tạo phân tách. Cần chứng minh danh tính nào được publish/consume và có wildcard hoặc quyền tạo tài nguyên làm mở rộng phạm vi không.

### 6.3. Payload không tự chứng minh nguồn

Trường `producer_service` hoặc `tenant_id` trong JSON là dữ liệu do bên gửi cung cấp cho tới khi được kiểm chứng theo thiết kế.

Consumer cần biết nguồn tin nào được chấp nhận: danh tính được broker xác thực và chuyển giao đáng tin, envelope được bảo vệ, hoặc một cơ chế khác được phê duyệt. Không tin một header tự khai báo chỉ vì message đã đi qua mạng nội bộ.

Nếu broker cho nhiều producer cùng publish vào một queue, consumer phải có cách phân biệt và đánh giá nguồn theo yêu cầu. Không suy ra mọi nội dung trong queue đều có cùng mức quyền nghiệp vụ.

### 6.4. Danh tính dịch vụ khác quyền người dùng

Một message yêu cầu xuất hồ sơ có thể được tạo bởi service thay người dùng. Quyền publish của service không có nghĩa người dùng đó được xuất mọi hồ sơ.

Phải lưu và xác minh ngữ cảnh đại diện cần thiết, kiểm tra phạm vi tài nguyên và chính sách thời điểm thực thi. Một field actor ID tùy ý không tự cấp quyền đại diện.

Tác vụ hệ thống độc lập có thể có quyền riêng, nhưng quyền đó phải được mô hình hóa rõ, thay vì xuất hiện như fallback khi không còn ngữ cảnh người dùng.

## 7. Vòng đời chứng thư, credential và quyền

### 7.1. Luân chuyển không cần mở đường không bảo vệ

Kế hoạch rotation cần xác định:

- Chủ sở hữu và nguồn cấp danh tính/credential.
- Nơi giữ khóa riêng hoặc bí mật, cùng quyền đọc.
- Thời điểm thay mới, triển khai và xác minh.
- Nếu có giai đoạn chấp nhận cũ/mới, phạm vi và thời hạn chồng lấn.
- Cách loại credential cũ và kiểm tra kết nối sau chuyển đổi.
- Hành vi nếu cập nhật không hoàn tất trước hết hạn.

Một giai đoạn chuyển tiếp không được trở thành việc tin mọi chứng thư hoặc giữ credential cũ vô thời hạn. Rotation phải được kiểm thử với tải và kết nối dài hạn đại diện.

Không đưa bí mật vào mã nguồn, command log, cấu hình được phát công khai hoặc payload thông điệp để tiện debug.

### 7.2. Thu hồi phải xét kết nối đang mở

Thu hồi quyền tại broker hoặc hệ thống danh tính không luôn đồng nghĩa các kết nối đã xác thực bị ngắt ngay. Cần xác định điểm thực thi kiểm tra lại quyền, thời hạn phiên và cơ chế chấm dứt/refresh theo khả năng nền tảng.

Yêu cầu minh họa:

> Trong tối đa 5 phút từ lúc thu hồi principal được commit tại nguồn có thẩm quyền, principal đó không còn được tạo publish, subscription hoặc nhận delivery mới ngoài chính sách trên các đường thuộc phạm vi, gồm kết nối đã tồn tại.

Mốc 5 phút là giả định của ví dụ. Để đáp ứng, triển khai có thể cần kiểm tra quyền ở thao tác, làm mới xác thực, chủ động đóng phiên hoặc cơ chế khác. Chỉ kiểm tra chứng thư khi mở kết nối có thể chưa đủ.

Thông điệp đã được giao tới bộ nhớ consumer trước thu hồi không tự biến mất. Cần quy định riêng việc có được tiếp tục xử lý hay không, dựa trên quyền và chính sách nghiệp vụ.

### 7.3. Kết nối mới và phiên cũ là hai bài thử

Khi kiểm tra credential hết hạn hoặc bị thu hồi, phải thử ít nhất:

- Mở kết nối mới.
- Publish qua kết nối cũ.
- Tạo subscription mới trên phiên cũ.
- Nhận delivery theo subscription đã tồn tại.
- Reconnect sau failover.
- Xử lý message đã được nhận trước đó theo chính sách riêng.

Không kết luận đạt chỉ vì kết nối mới bị chặn trong khi phiên cũ vẫn đọc được dữ liệu vô thời hạn.

### 7.4. Phụ thuộc vào thời gian và nguồn tin cậy

Kiểm tra hiệu lực credential, grant hoặc message có thể phụ thuộc đồng hồ. Cần có yêu cầu đồng bộ và hành vi khi không đủ tin cậy về thời gian.

Việc message có trường thời điểm không chứng minh thời điểm đó đúng. Nếu cần sử dụng thời gian cho quyết định nhạy cảm, phải đặc tả nguồn và mức tin cậy, thay vì chấp nhận mọi timestamp do producer gửi.

## 8. Envelope, tính toàn vẹn nội dung và dữ liệu nhạy cảm

### 8.1. Envelope có cấu trúc rõ ràng

Một thông điệp minh họa:

```json
{
  "message_id": "msg-7f61",
  "business_operation_id": "export-804",
  "event_type": "DocumentExportRequested",
  "schema_version": 2,
  "producer_service": "export-api",
  "intended_consumer": "export-worker",
  "tenant_id": "tenant-07",
  "requested_by": "user-37",
  "issued_at": "2026-11-27T08:15:00Z",
  "payload": {
    "record_ids": ["case-915"],
    "requested_format": "pdf"
  },
  "correlation_id": "trace-381"
}
```

Đây là cấu trúc minh họa, không phải định dạng bắt buộc. Consumer phải xác minh nguồn và quyền trước khi tin các trường có ý nghĩa quyết định.

Thông điệp nên chỉ mang dữ liệu cần thiết. Dùng tham chiếu tài nguyên có thể giảm sao chép dữ liệu nhạy cảm, nhưng consumer vẫn cần quyền đọc tài nguyên đó và cơ chế truy cập an toàn.

### 8.2. Bảo vệ nội dung sau điểm kết thúc kênh

Nếu yêu cầu chỉ bảo vệ khỏi nghe lén mạng, TLS từng chặng có thể là một phần phù hợp của thiết kế. Nếu cần phát hiện sửa nội dung sau khi broker nhận, hoặc hạn chế broker đọc payload, phải có yêu cầu nội dung tương ứng.

Khi dùng cơ chế xác thực nội dung, cần xác định:

- Chủ thể nào được cấp quyền tạo thông điệp hợp lệ.
- Những field và ngữ nghĩa routing/audience nào nằm trong phần được bảo vệ.
- Cách biểu diễn và chuẩn hóa dữ liệu được kiểm chứng.
- Cách chọn khóa và xử lý phiên bản khóa.
- Quy tắc chấp nhận thông điệp cũ, lưu lâu hoặc được giao lại.
- Khả năng thay đổi metadata vận chuyển mà không làm nhập nhằng nội dung gốc.

Không tự ghép chuỗi tùy ý rồi gọi là chữ ký an toàn. Chọn cơ chế và thư viện được phê duyệt, cùng test tương thích giữa producer và consumer.

### 8.3. Mã hóa payload cần kế hoạch khóa

Nếu payload được mã hóa tới consumer, phải chỉ rõ ai có thể giải mã, cách rotation, retention và xử lý message còn trong queue khi khóa đổi.

Không xóa khóa cũ khi vẫn cần giải mã thông điệp được giữ hợp lệ. Cũng không đặt khóa giải mã ngay trong message rồi xem như đã đạt mục tiêu giới hạn người đọc.

Metadata như topic, kích thước, thời điểm, event type hoặc một phần envelope có thể vẫn quan sát được. Yêu cầu bí mật cần nói rõ phần nào thuộc phạm vi, thay vì coi mọi thông tin đều đã được che.

### 8.4. Schema và giới hạn tài nguyên

Consumer cần kiểm tra schema, kiểu, kích thước, event type và các giới hạn trước khi xử lý tốn tài nguyên hoặc thực hiện tác dụng.

Nếu có nén hoặc encoding, phải quy định giới hạn ở các giai đoạn phù hợp, gồm kích thước sau giải mã/giải nén khi áp dụng. Một giới hạn trên số byte truyền không tự bảo vệ mọi bước parse.

Schema validation giúp kiểm soát cấu trúc, nhưng không xác minh quyền hoặc tính đúng nghiệp vụ của các giá trị.

## 9. Replay, retry, thứ tự và request–reply

### 9.1. TLS không quyết định một message được xử lý mấy lần

Một broker có thể giao lại message khi consumer lỗi hoặc mất ACK. Một operator cũng có thể redrive từ DLQ.

Consumer phải có quy tắc chống tác dụng lặp dựa trên định danh lệnh và bất biến nghiệp vụ. Message ID giúp nhận diện đơn vị giao nhận, còn business operation ID cần cho những trường hợp nhiều message ID cùng đại diện một ý định.

Nếu marker chống lặp và tác dụng cục bộ phải cùng có hiệu lực, cần đặt chúng trong ranh giới nhất quán phù hợp. Một map trong bộ nhớ không đủ cho bảo đảm qua restart nếu chưa có cơ chế khác.

### 9.2. Tuổi thông điệp khác thời hạn nghiệp vụ

Một message giao chậm không tự là tấn công replay, nhưng có thể không còn hợp lệ để thực hiện. Cần phân biệt:

- Thời gian lưu ở broker.
- Thời hạn cho phép bắt đầu tác vụ.
- Thời hạn hoặc trạng thái của đối tượng nghiệp vụ.
- Cửa sổ chống replay và thời gian giữ marker.
- Thời điểm quyền cần được đánh giá lại.

Không áp cửa sổ vài phút cho mọi queue rồi làm mất công việc hợp lệ khi có sự cố kéo dài. Ngược lại, không cho lệnh nhạy cảm còn hiệu lực vô hạn chỉ vì message được lưu bền.

### 9.3. Thứ tự phải được kiểm tra theo nghiệp vụ

Một thông điệp đến sau có thể chứa revision cũ. Consumer cần guard hoặc version phù hợp để sự kiện cũ không làm lùi trạng thái đã hoàn tất.

Không giả định mọi message trên toàn hệ thống có một thứ tự duy nhất. Phạm vi thứ tự được broker hoặc partition cung cấp phải được đối chiếu với bất biến cần bảo vệ.

### 9.4. Request–reply không cho client chọn đích tùy ý

Nếu producer gửi yêu cầu kèm địa chỉ trả kết quả, consumer phải kiểm tra đích reply theo chính sách. Không gửi dữ liệu nhạy cảm tới bất kỳ queue, URL hoặc tên tài nguyên nào do payload tự chỉ định.

Phản hồi cần liên kết với request/operation đúng, được bảo vệ trên kênh tương ứng và chỉ được principal được phép nhận.

Một correlation ID không tự là bằng chứng nguồn hoặc quyền đọc phản hồi.

## 10. Retry, DLQ, quan sát và phục hồi

### 10.1. Retry giữ nguyên ranh giới bảo mật

Retry phải dùng endpoint, danh tính và quyền được phép. Không đổi sang credential quản trị hoặc listener thiếu bảo vệ khi gặp lỗi xác thực.

Cần giới hạn số lần, tốc độ, thời gian và dung lượng chờ theo thiết kế. Bão retry có thể làm cạn tài nguyên broker, consumer hoặc hệ thống danh tính.

Retry phải giữ liên kết operation và nội dung được phép; không tạo ý định nghiệp vụ mới chỉ vì lần gửi trước chưa có kết quả.

### 10.2. DLQ vẫn là nơi chứa dữ liệu nhạy cảm

DLQ có thể chứa payload, metadata và thông báo lỗi. Quyền đọc, mã hóa lưu trữ, retention và khả năng export cần phù hợp phân loại.

Không cấp quyền DLQ cho mọi người vận hành chỉ để xem lỗi. Có thể cung cấp thông tin lỗi đã giảm nhạy cảm, đồng thời giới hạn việc đọc nội dung đầy đủ.

Redrive là một thao tác tạo lại delivery, không mặc nhiên được quyền thực hiện lại nghiệp vụ. Phải kiểm tra nguồn/đích, trạng thái, quyền và chống lặp theo chính sách.

### 10.3. Log và audit không trở thành đường rò rỉ

Dấu vết nên liên kết principal kết nối, tài nguyên broker, quyết định quyền, message/operation ID và kết quả xử lý theo nhu cầu.

Không ghi credential, khóa, token hoặc toàn bộ payload nhạy cảm vào log thông thường. Cần kiểm soát cardinality của metric và quyền đọc trace.

Phân biệt các mốc: kết nối thành công, broker chấp nhận publish, message được giao, consumer commit nghiệp vụ và tác dụng ngoài được xác nhận. Một publish ACK không tự chứng minh nghiệp vụ cuối đã hoàn tất.

### 10.4. Backup và restore giữ ACL cùng ý nghĩa thông điệp

Sau restore hoặc migrate, cần kiểm tra trust, principal, ACL, endpoint, dữ liệu queue và marker chống lặp trước khi mở xử lý.

Không phục hồi quyền rộng cũ hoặc replay mọi message mà bỏ qua trạng thái hiện hành. Với tác dụng ngoài đã xảy ra, phải đối soát để tránh tạo lại.

Nếu broker mất khả dụng hoặc đầy dung lượng, chính sách tiếp nhận/lưu đệm/từ chối phải được đặc tả. Duy trì bảo mật của đường truyền không thay thế kế hoạch phục hồi dữ liệu và dịch vụ.

## 11. Bộ yêu cầu bảo mật minh họa

Các yêu cầu dưới đây áp dụng cho luồng yêu cầu xuất hồ sơ qua broker. Cơ chế cụ thể phải được chọn theo nền tảng và mô hình tin cậy, không suy ra rằng mọi broker hỗ trợ cùng một tính năng.

| ID | Yêu cầu có thể kiểm chứng | Chủ sở hữu | Bằng chứng đạt |
| --- | --- | --- | --- |
| SMT-01 | Phải có danh mục chặng truyền, endpoint, principal, loại dữ liệu và điểm kết thúc bảo vệ, gồm discovery, broker nội bộ, retry, DLQ và quản trị trong phạm vi. | Kiến trúc/nền tảng | Đối chiếu cấu hình đang chạy và kết nối thực tế; không có chặng mang dữ liệu chưa được phân loại. |
| SMT-02 | Mọi chặng thuộc phạm vi phải dùng hồ sơ bảo vệ kênh được phê duyệt; client không được fallback sang plaintext hoặc bỏ xác minh khi lỗi/failover. | Nền tảng/ứng dụng | Test listener không bảo vệ, endpoint dự phòng và lỗi cấu hình; kết nối bị cấm không mang dữ liệu ứng dụng. |
| SMT-03 | Client phải xác minh trust, hiệu lực và danh tính máy chủ dự kiến theo mô hình được duyệt; cấu hình chấp nhận mọi chứng thư/danh tính không được dùng. | Ứng dụng/nền tảng | Chứng thư không được tin, hết hiệu lực hoặc sai đích bị từ chối; đúng đích và cấu hình hợp lệ kết nối được. |
| SMT-04 | Producer, consumer và công cụ quản trị phải có principal và quyền theo nhiệm vụ; publish/consume/routing phải bị giới hạn theo tài nguyên và tenant thực sự được hỗ trợ. | Bảo mật/nền tảng | Thử từng vai trò với tài nguyên đúng/sai; các điều kiện ngoài khả năng ACL được kiểm tra ở lớp ứng dụng. |
| SMT-05 | Trong ví dụ, sau thu hồi principal tối đa 5 phút, principal không còn publish, tạo subscription hoặc nhận delivery mới trái chính sách, gồm phiên đã tồn tại. | Bảo mật/nền tảng | Timeline thu hồi và thử thao tác qua phiên mới/cũ trên các endpoint; không chỉ kiểm tra handshake mới. |
| SMT-06 | Rotation credential/khóa phải có thời điểm chuyển tiếp, loại bỏ bản cũ và kiểm thử; không mở quyền, bỏ xác minh hoặc kéo dài credential cũ vô hạn để tránh gián đoạn. | Quản lý danh tính/nền tảng | Diễn tập rotation, reconnect và failover; credential cũ bị xử lý theo hạn và policy đã duyệt. |
| SMT-07 | Nguồn và phần nội dung cần tin phải được xác minh bằng cơ chế được chọn; nếu mô hình yêu cầu broker không đọc/sửa được payload, phải có bảo vệ nội dung phù hợp và kế hoạch khóa. | Bảo mật/ứng dụng | Sửa envelope/payload/nguồn và kiểm tra phạm vi bảo vệ; phần không được bảo vệ được ghi rõ, không tuyên bố quá mức. |
| SMT-08 | Consumer phải kiểm tra schema, audience/event type, tenant, trạng thái và quyền nghiệp vụ; kích thước/độ phức tạp đầu vào phải trong ngân sách được duyệt. | Ứng dụng | Message đúng cấu trúc nhưng sai quyền hoặc sai phạm vi vẫn bị chặn; đầu vào vượt ngưỡng không làm xử lý vô hạn. |
| SMT-09 | Message lặp, cũ hoặc sai thứ tự không được tạo tác dụng nghiệp vụ trái chính sách; thời hạn lưu, cửa sổ chấp nhận và marker chống lặp phải được đặc tả riêng. | Ứng dụng/dữ liệu | Redelivery, revision cũ, restart và replay theo operation ID không phá bất biến; không chỉ dựa vào message ID. |
| SMT-10 | Retry, DLQ và redrive phải giữ phân loại, danh tính, quyền, retention và giới hạn tài nguyên; redrive không cấp quyền nghiệp vụ mới. | Vận hành/ứng dụng | Đọc DLQ trái quyền bị chặn; redrive sai nguồn/đích hoặc lệnh không còn hợp lệ không tạo tác dụng ngoài phạm vi. |
| SMT-11 | Đích request–reply hoặc chuyển tiếp phải thuộc tập được phê duyệt và khớp quyền nhận; client không tự chọn đích ngoài phạm vi để nhận dữ liệu. | Tích hợp/ứng dụng | Thay reply destination hoặc correlation reference không chuyển nội dung sang chủ thể/đích không được phép. |
| SMT-12 | Audit phải liên kết principal, tài nguyên broker, message/operation ID và các mốc kết quả; log/trace không ghi credential hoặc payload nhạy cảm ngoài chính sách. | Vận hành/bảo mật | Đối chiếu publish, delivery, commit và tác dụng ngoài; kiểm tra dữ liệu quan sát không trở thành đường rò rỉ. |
| SMT-13 | Lỗi xác thực, độ trễ thu hồi, kết nối bị cấm, message bị từ chối và backlog phải có chủ xử lý, ngưỡng và thời hạn cảnh báo; quá tải không làm giảm bảo vệ. | Vận hành/nền tảng | Tiêm lỗi và tải tới giới hạn; cảnh báo có bằng chứng thời gian, retry hữu hạn và không đổi sang đường thiếu bảo vệ. |
| SMT-14 | Thay trust/ACL, thêm endpoint, mirror/migrate hoặc restore phải kiểm tra lại ma trận kênh, quyền và trạng thái chống lặp trước khi mở xử lý. | Chủ dịch vụ | Test cấu hình hiệu lực sau thay đổi, principal đã thu hồi, message cũ và quyền DLQ; không dùng lại quyền rộng cũ ngoài policy. |

Ví dụ cho SMT-13: kiểm tra tình trạng kênh và điều khiển truy cập mỗi phút; thông báo lỗi bảo vệ kênh kéo dài phải tới nơi nhận trong 2 phút từ lúc được phát hiện. Mốc này là mục tiêu cảnh báo minh họa, không thay thế yêu cầu chặn kết nối không hợp lệ ngay tại điểm thực thi.

Giám sát mất tín hiệu cũng cần có thiết kế phù hợp. Nếu chính pipeline cảnh báo ngừng hoạt động, không được giữ dashboard xanh chỉ vì không còn lỗi mới được ghi nhận.

### 11.1. Mẫu đặc tả chi tiết cho thu hồi principal

```text
ID: SMT-05
Mục tiêu: principal bị thu hồi không tiếp tục dùng kênh quá thời hạn
Rủi ro: R-MSG-05 — phiên cũ tồn tại sau khi credential/quyền bị thu hồi
Phạm vi:
  - Producer và consumer của luồng xuất hồ sơ
  - Endpoint chính, dự phòng và đường discovery trong danh mục
Bắt đầu tính:
  - Thu hồi được commit tại nguồn danh tính/quyền có thẩm quyền
Điều kiện đạt:
  - Sau tối đa 5 phút, không có publish/subscription/delivery mới trái policy
  - Áp dụng cho phiên đang mở và phiên mới
  - Thiếu bằng chứng quyền đủ mới không được tự coi là còn quyền
Ngoài phạm vi tự suy ra:
  - Message đã được giao trước thu hồi không tự bị xóa
  - Quyền tiếp tục thực hiện nghiệp vụ được đặc tả riêng tại consumer
Chủ sở hữu: đội bảo mật và nền tảng
Kiểm thử: T-SMT-05, T-SMT-06, T-SMT-07
Bằng chứng: timeline thu hồi, principal, phiên, thao tác và kết quả broker
```

Nếu nền tảng chỉ áp dụng quyền khi mở kết nối, thiết kế phải bổ sung cơ chế để đạt thời hạn hoặc ghi nhận chưa đáp ứng. Không đánh dấu đạt chỉ bằng việc xóa credential trong nơi quản lý bí mật.

### 11.2. Điều kiện áp dụng của bảo vệ nội dung

Yêu cầu bảo vệ payload khỏi broker chỉ áp dụng khi mô hình đe dọa chọn broker ngoài phạm vi được phép đọc. Khi không áp dụng, phải nêu rõ broker và các principal liên quan có thể đọc nội dung theo quyền kỹ thuật nào.

Không đánh dấu “đã mã hóa đầu cuối” vì các chặng đều có TLS. Bằng chứng phải chỉ rõ nơi giải mã và chủ thể nắm khóa.

## 12. Ma trận kiểm thử nghiệm thu

Thử trong môi trường được kiểm soát bằng thông điệp tổng hợp có marker, principal riêng và endpoint đúng/sai được thiết kế cho bài thử. Không dùng dữ liệu khách hàng hoặc credential thật để quan sát plaintext hay kiểm tra log.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-SMT-01 | Quan sát từng chặng producer–proxy–broker–consumer và các đường nội bộ trong danh mục. | Kết nối và điểm kết thúc bảo vệ khớp thiết kế; không bỏ sót chặng mang dữ liệu. | SMT-01, 02 |
| T-SMT-02 | Cung cấp endpoint không bảo vệ, làm endpoint chính lỗi, thay danh sách discovery sang đích không đáp ứng policy. | Không gửi dữ liệu qua đường bị cấm; failover không bỏ xác minh hoặc giảm mức bảo vệ. | SMT-02, 03 |
| T-SMT-03 | Thử chứng thư không được tin, hết hiệu lực, sai danh tính đích và cấu hình client chấp nhận quá rộng. | Đích không hợp lệ bị từ chối; đích đúng kết nối được; không chỉ kiểm tra trạng thái “có TLS”. | SMT-03 |
| T-SMT-04 | Producer thử consume, consumer thử quản trị, principal tenant A thử tài nguyên tenant B và wildcard ngoài quyền. | Broker/lớp ứng dụng chặn đúng theo phân chia trách nhiệm; không phát/nhận dữ liệu ngoài phạm vi. | SMT-04, 08 |
| T-SMT-05 | Thu hồi principal rồi tiếp tục publish và nhận delivery qua phiên đã mở; đồng thời thử phiên mới. | Không quá 5 phút trong ví dụ còn thao tác mới trái policy; báo được lần chấp nhận cuối ở từng đường. | SMT-05 |
| T-SMT-06 | Rotation credential và trust theo kế hoạch; giữ một client cũ, reconnect và failover sau thời hạn chuyển tiếp. | Credential/trust được thay theo chính sách; không mở fallback không bảo vệ để duy trì kết nối. | SMT-05, 06 |
| T-SMT-07 | Ngắt nguồn quyền hoặc cập nhật thu hồi trong điều kiện mà triển khai phụ thuộc; kiểm tra phiên cũ và quyền tiếp tục xử lý message đã giao. | Hành vi đúng độ mới và policy; không dùng dữ kiện thiếu tin cậy để giữ quyền vô hạn. | SMT-05, 08 |
| T-SMT-08 | Sửa producer/tenant/audience, payload hoặc phần nội dung thuộc phạm vi được bảo vệ; gửi message có schema đúng nhưng sai quyền. | Phát hiện sửa đổi theo cơ chế áp dụng; consumer không tin trường tự khai báo hoặc bỏ kiểm tra nghiệp vụ. | SMT-07, 08 |
| T-SMT-09 | Gửi message lặp, operation lặp với message ID mới, revision cũ và delivery sai thứ tự; restart consumer. | Không tạo tác dụng bị cấm; marker và trạng thái giữ đúng qua restart; sự kiện cũ không làm lùi trạng thái. | SMT-09 |
| T-SMT-10 | Đưa thông điệp lỗi vào DLQ; dùng principal không có quyền đọc; redrive sang đích khác hoặc sau khi quyền nghiệp vụ đổi. | DLQ vẫn bảo vệ dữ liệu; redrive đúng quyền và không làm sống lại thao tác ngoài policy. | SMT-10 |
| T-SMT-11 | Thay đích reply, queue/URL trả kết quả hoặc reference của request. | Không gửi dữ liệu tới đích ngoài phạm vi; response đúng request và người nhận được phép. | SMT-11 |
| T-SMT-12 | Làm broker đầy hoặc phụ thuộc chậm, tạo retry vượt mức và đầu vào vượt ngân sách. | Từ chối/lưu đệm/giảm tải theo policy; không retry vô hạn hoặc chuyển credential/endpoint thiếu bảo vệ. | SMT-08, 10, 13 |
| T-SMT-13 | Tiêm lỗi publish, delivery, commit và mất ACK; kiểm tra log, trace và cảnh báo. | Phân biệt đúng mốc kết quả; không lộ bí mật/payload ngoài policy; cảnh báo đúng hạn. | SMT-12, 13 |
| T-SMT-14 | Restore/migrate trust, ACL, queue và marker; thử principal đã thu hồi và message cũ trước mở xử lý. | Không phục hồi quyền trái policy hoặc replay mù tác dụng; mọi đường bảo vệ vẫn đúng. | SMT-14 |
| T-SMT-15 | Nếu có bảo vệ nội dung đầu cuối, thử đọc/sửa payload tại broker, đổi khóa và xử lý message còn lưu. | Phạm vi bí mật/toàn vẹn đúng mô hình; consumer hợp lệ xử lý được bản còn trong hạn; giới hạn metadata được ghi rõ. | SMT-06, 07 |

Với tính năng không tồn tại trong kiến trúc, ghi rõ không áp dụng cùng bằng chứng phạm vi, thay vì đánh dấu đạt theo suy đoán. Ví dụ, không có proxy hoặc không có mã hóa payload đầu cuối thì bài thử tương ứng cần được giải thích.

### 12.1. Bằng chứng đủ để kết luận

Báo cáo cần có cấu hình hiệu lực, phiên bản ứng dụng/nền tảng, hồ sơ bảo vệ được duyệt, principal, tài nguyên, thời điểm, hành vi và kết quả thực tế.

Quan sát lưu lượng thử có thể hỗ trợ kiểm tra đường truyền, nhưng việc không nhìn thấy một marker trong một mẫu capture không tự chứng minh toàn bộ hệ thống được mã hóa và xác thực đúng. Cần kết hợp cấu hình, kết quả handshake, test âm và phạm vi chặng.

Tương tự, một publish bị từ chối không chứng minh principal không còn consume qua phiên khác. Ma trận phải bao phủ đúng những thao tác yêu cầu cam kết.

### 12.2. Đo thời hạn thu hồi

Mốc bắt đầu là commit thu hồi tại nguồn có thẩm quyền, không phải lúc node cuối đã cập nhật.

Cần giữ phiên cũ, tạo phiên mới và gửi thao tác trong khoảng quan sát. Nếu có nhiều node hoặc đường failover, phải thử các đường thuộc phạm vi và ghi độ không chắc chắn của phép đo.

Không cộng thời gian cảnh báo vào để biến việc tiếp tục nhận dữ liệu quá hạn thành đạt. Cảnh báo đúng hạn và thực thi thu hồi đúng hạn là hai yêu cầu khác nhau.

## 13. Truy vết từ rủi ro đến vận hành

Chuỗi truy vết tối thiểu:

```text
Mục tiêu bí mật, toàn vẹn và đúng chủ thể
    → Kịch bản nghe lén, giả danh, vượt quyền hoặc replay
    → Yêu cầu SMT-xx
    → Chặng truyền, danh tính, ACL và cơ chế nội dung
    → Test T-SMT-xx
    → Audit, cảnh báo, rotation và quy trình phục hồi
```

| Mục tiêu | Rủi ro | Yêu cầu | Thiết kế/kiểm chứng |
| --- | --- | --- | --- |
| Không lộ dữ liệu trên chặng truyền | Một hop hoặc failover plaintext | SMT-01, 02 | Danh mục và policy kênh; T-SMT-01, 02 |
| Kết nối đúng dịch vụ | Chấp nhận sai đích hoặc trust quá rộng | SMT-03 | Xác minh danh tính và trust; T-SMT-03 |
| Giữ ranh giới tenant và nhiệm vụ | Publish/consume ngoài phạm vi | SMT-04, 08 | ACL cộng guard ứng dụng; T-SMT-04, 08 |
| Ngăn principal đã thu hồi tiếp tục truy cập | Phiên cũ còn quyền | SMT-05, 06 | Hiệu lực quyền và vòng đời kết nối; T-SMT-05, 06, 07 |
| Không lặp hoặc mở lại nghiệp vụ qua redrive | Retry và DLQ bỏ guard | SMT-09, 10 | Operation ID, trạng thái và quyền redrive; T-SMT-09, 10 |
| Giữ bảo đảm sau phục hồi | Trust/ACL/marker cũ sống lại | SMT-14 | Kiểm tra trước mở xử lý; T-SMT-14 |

Thay endpoint, service mesh, cơ chế danh tính, broker, queue, retention hoặc công cụ hỗ trợ vận hành có thể thay đổi ranh giới tin cậy. Cần đánh giá lại yêu cầu và test liên quan.

Ngoại lệ phải có phạm vi dữ liệu/chặng, thời hạn, rủi ro còn lại, biện pháp bù và người phê duyệt. Không giảm xác minh cho toàn hệ thống chỉ để một client chưa được cập nhật tiếp tục chạy.

## 14. Những lỗi đặc tả thường gặp

| Cách viết hoặc triển khai | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Broker đã bật TLS.” | Chưa biết client, hop nội bộ và failover có tuân thủ không | Kiểm kê và test từng chặng |
| “Kết nối mã hóa nên đúng máy chủ.” | Có thể bỏ kiểm tra trust hoặc danh tính đích | Kiểm tra và test âm theo mô hình danh tính |
| “mTLS nghĩa là có quyền publish mọi nơi.” | Xác thực không thay ACL | Ánh xạ principal và quyền tối thiểu |
| “Tenant nằm trong topic name là đã tách.” | Wildcard hoặc quyền tạo tài nguyên có thể phá phạm vi | Kiểm chứng quyền thực tế và guard routing |
| “Nội bộ nên tin producer_id trong payload.” | Dữ kiện có thể do người gửi tự khai báo | Dựa vào nguồn được xác minh và ràng buộc rõ |
| “Thu hồi secret là phiên cũ tự mất quyền.” | Phiên có thể không kiểm tra lại | Đặc tả và test hiệu lực trên kết nối đang mở |
| “TLS bảo vệ cả message đã lưu.” | Kênh kết thúc trước nơi lưu hoặc xử lý | Có yêu cầu lưu trữ và nội dung tương ứng |
| “Message ký đúng thì được thực hiện.” | Chữ ký không cấp quyền với mọi đối tượng | Kiểm tra audience, trạng thái và nghiệp vụ |
| “DLQ chỉ là dữ liệu lỗi.” | Vẫn có thể chứa toàn bộ payload nhạy cảm | Giữ phân loại, quyền và retention |
| “Publish ACK là tác vụ đã xong.” | Có thể mới chỉ được broker chấp nhận | Phân biệt các mốc kết quả |
| “Retry sẽ tự an toàn vì dùng TLS.” | Redelivery có thể tạo tác dụng lặp | Chống lặp và guard tại consumer |
| “Restore queue rồi chạy lại mọi message.” | Quyền và tác dụng thực tế có thể đã đổi | Đối soát trước khi mở xử lý |

## 15. Bài tập áp dụng

Một hệ thống có producer gửi yêu cầu xử lý tài liệu, broker dùng chung cho nhiều tenant và worker nhận message. Endpoint chính có bảo vệ kênh nhưng endpoint dự phòng chưa được kiểm tra. Producer và worker dùng chung credential. DLQ cho mọi người vận hành đọc, còn consumer tin tenant ID và reply destination trong payload.

Hãy thực hiện:

1. Lập danh mục chặng truyền, principal, endpoint và điểm kết thúc bảo vệ.
2. Nêu ít nhất sáu kịch bản rủi ro, gồm nghe lén, giả danh, vượt quyền, replay và rò rỉ qua vận hành.
3. Thiết kế ma trận quyền publish, consume, DLQ/redrive và quản trị.
4. Viết sáu yêu cầu có ID, phạm vi, điều kiện đạt, chủ sở hữu và bằng chứng nghiệm thu.
5. Đặc tả rotation và thời hạn thu hồi với kết nối đang mở.
6. Thiết kế test sai danh tính máy chủ, failover, principal tenant khác và message lặp.
7. Giải thích khi nào cần bảo vệ payload ngoài TLS từng chặng.
8. Đề xuất cách kiểm soát reply destination và quyền nghiệp vụ tại consumer.
9. Nêu các bước kiểm tra trước khi xử lý lại message sau restore.

Đáp án tốt phải chứng minh mỗi chặng và mỗi chủ thể có đúng mức bảo vệ, đồng thời không nhầm bảo đảm giao nhận với quyền thực hiện nghiệp vụ.

## 16. Checklist chấp nhận yêu cầu

- Đã có danh mục chặng, endpoint, discovery và điểm kết thúc bảo vệ chưa?
- Mọi chặng trong phạm vi có dùng hồ sơ bảo vệ được duyệt không?
- Client có xác minh đúng trust, hiệu lực và danh tính đích không?
- Failover có tránh plaintext hoặc bỏ xác minh không?
- Producer, consumer và admin có principal và quyền theo nhiệm vụ không?
- Tenant/routing có được kiểm chứng ngoài dữ kiện tự khai báo không?
- Thu hồi có thời hạn và bao phủ phiên đang tồn tại không?
- Rotation có kiểm thử chuyển tiếp và loại bỏ credential cũ không?
- Phạm vi bảo vệ nội dung sau điểm kết thúc TLS có được nêu rõ không?
- Consumer có kiểm tra schema, audience, trạng thái và quyền nghiệp vụ không?
- Replay, retry, revision và marker có giữ bất biến qua restart không?
- DLQ, redrive và request–reply có giữ đúng phân loại và quyền không?
- Audit có phân biệt kết nối, publish, delivery và commit nghiệp vụ không?
- Log/trace có tránh lộ bí mật và payload ngoài chính sách không?
- Restore/migrate có kiểm tra lại trust, ACL và tác dụng trước khi mở xử lý không?

Truyền thông điệp an toàn đáp ứng mục tiêu bảo mật khi mọi chặng có đầu kết nối được xác minh, mọi principal chỉ sử dụng đúng tài nguyên được cấp, và nội dung cùng tác dụng nghiệp vụ vẫn được kiểm chứng qua retry, vận hành và phục hồi.

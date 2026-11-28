# Security acceptance criteria

## 1. Mục tiêu và vai trò

Security acceptance criteria là các tiêu chí nghiệm thu xác định hành vi và bằng chứng cần có để một thay đổi đáp ứng yêu cầu bảo mật trong phạm vi đã chọn.

Một mục tiêu như “bảo vệ dữ liệu khách hàng” chưa đủ để người phát triển biết phải làm gì hoặc người kiểm thử biết khi nào được kết luận đạt. Tiêu chí cần nêu rõ chủ thể, tài nguyên, điều kiện, hành vi được phép hoặc bị cấm và cách quan sát kết quả.

Ví dụ:

> Khi người dùng thuộc tenant A yêu cầu tải kết quả xuất dữ liệu của tenant B, hệ thống từ chối theo hợp đồng API, không trả nội dung file và không cung cấp đường tải thay thế có thể sử dụng.

Tiêu chí này gắn trực tiếp với một rủi ro: truy cập dữ liệu giữa các tenant. Nó cũng tạo được ca kiểm thử và điểm kiểm tra trong kiến trúc.

Trong chương Secure development, mục tiêu là đưa các tiêu chí vào công việc phát triển từ sớm, liên kết với thiết kế và duy trì bằng chứng đến lúc phát hành. Tiêu chí nghiệm thu bảo mật cần bao phủ cả hành vi thành công, hành vi bị từ chối, lỗi phụ thuộc và các thay đổi trạng thái quan trọng.

Các dịch vụ, định danh, ngưỡng và thời hạn trong bài là ví dụ thiết kế. Chúng cần được lựa chọn theo mô hình đe dọa và khả năng của sản phẩm thực tế.

## 2. Phân biệt mục tiêu, yêu cầu, thiết kế và tiêu chí nghiệm thu

| Lớp thông tin | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Mục tiêu bảo mật | Cần bảo vệ điều gì? | Dữ liệu không bị truy cập chéo tenant |
| Rủi ro | Điều gì có thể làm mục tiêu thất bại? | Người dùng đổi job ID để tải file của tenant khác |
| Yêu cầu bảo mật | Thuộc tính nào hệ thống phải duy trì? | Mọi lần truy cập kết quả export phải được phân quyền theo tenant và principal |
| Thiết kế kiểm soát | Thành phần nào cưỡng chế yêu cầu? | Service tải file lấy tenant từ ngữ cảnh đã xác minh và kiểm tra quyền trước khi mở object |
| Tiêu chí nghiệm thu | Quan sát nào chứng minh hành vi đáp ứng yêu cầu trong phạm vi kiểm tra? | Đổi job ID sang tenant khác không trả dữ liệu hoặc URL tải có hiệu lực |
| Ca kiểm thử | Dùng dữ liệu và thao tác cụ thể nào để kiểm tra? | Principal P-A gọi API tải job J-B, kiểm tra phản hồi và side effect |
| Definition of Done | Công việc cần hoàn tất những hoạt động nào? | Review, kiểm thử, tài liệu và bằng chứng theo quy trình |

“Đã chạy SAST” là một điều kiện quy trình. Nó chưa chứng minh một luồng tải file đã kiểm tra quyền đúng tenant.

“Phải dùng một thư viện cụ thể” là ràng buộc triển khai nếu kiến trúc đã chọn như vậy. Tiêu chí nghiệm thu vẫn cần chỉ ra thuộc tính được kiểm tra và kết quả mong đợi.

Một tiêu chí tốt duy trì được ý nghĩa khi thay đổi cách hiện thực, miễn là yêu cầu không bắt buộc một cơ chế cụ thể. Nếu cơ chế là một ràng buộc bắt buộc, cần ghi rõ căn cứ và cách kiểm tra chính cơ chế đó.

## 3. Bắt đầu từ mô hình đe dọa và phạm vi thay đổi

Trước khi viết tiêu chí, xác định:

1. Tài sản và dữ liệu nhạy cảm.
2. Chủ thể, quyền và phạm vi tenant.
3. Các điểm vào và ranh giới tin cậy.
4. Hành vi có thể tạo tác động hoặc làm lộ dữ liệu.
5. Các phụ thuộc và trạng thái có thể thay đổi.
6. Những rủi ro mà thay đổi mới tạo ra hoặc làm tăng.

Ví dụ thay đổi: bổ sung tính năng xuất dữ liệu đơn hàng thành file.

| Rủi ro | Yêu cầu cần đặc tả | Điểm cưỡng chế dự kiến |
| --- | --- | --- |
| R-EXP-01: tạo hoặc tải export của tenant khác | Cô lập tenant ở mọi bước | API, worker, nơi lưu file và đường tải |
| R-EXP-02: quyền bị thu hồi nhưng job chờ vẫn chạy | Kiểm tra quyền ở các điểm sử dụng đã xác định | Worker trước đọc dữ liệu, trước công bố và service tải |
| R-EXP-03: lỗi audit nhưng export vẫn phát hành | Sự kiện bắt buộc phải được ghi bền vững theo hợp đồng | Cổng tạo job và bước công bố |
| R-EXP-04: retry hoặc request đồng thời tạo nhiều job ngoài dự kiến | Có hợp đồng idempotency và giới hạn tài nguyên | API tạo job và quản lý trạng thái |
| R-EXP-05: file hết hạn vẫn được tải qua đường khác | Cưỡng chế thời hạn tại mọi đường mở lượt tải mới | Service tải, storage policy và cache liên quan |
| R-EXP-06: log lỗi chứa token hoặc dữ liệu xuất | Bảo vệ dữ liệu trong mọi đầu ra chẩn đoán | Logger, error handler và audit schema |

Một thay đổi ở giao diện có thể tác động tới API hoặc luồng bất đồng bộ cũ. Phạm vi tiêu chí cần theo luồng dữ liệu và quyền, không chỉ theo file source vừa sửa.

Nếu tính năng có nhiều đường truy cập như UI, API, batch hoặc công cụ quản trị, cần chỉ rõ các đường thuộc phạm vi. Chỉ kiểm tra UI không chứng minh API trực tiếp đã được bảo vệ.

## 4. Cấu trúc của một tiêu chí có thể kiểm chứng

Một mẫu tham khảo:

```text
ID:
Rủi ro và yêu cầu liên quan:
Phạm vi và phiên bản hợp đồng:

Given:
  Trạng thái ban đầu, chủ thể, quyền và dữ liệu.

When:
  Hành động hoặc sự kiện được kiểm tra.

Then:
  Kết quả phải quan sát được.
  Tác động bị cấm hoặc bắt buộc.
  Hành vi khi phụ thuộc không đáp ứng điều kiện.

Cách đo và điều kiện biên:
Bằng chứng cần lưu:
Chủ sở hữu xác nhận:
```

Không phải tiêu chí nào cũng cần một biểu mẫu dài. Những thông tin cần thiết có thể được trình bày bằng bảng hoặc gắn vào đặc tả, miễn là người triển khai và người kiểm thử hiểu cùng một nghĩa.

### 4.1. Given phải đủ để kết quả có nghĩa

“Người dùng không có quyền” cần được cụ thể hóa:

- Chưa xác thực, hết phiên hay đã xác thực nhưng thiếu role?
- Có cùng tenant không?
- Quyền được thu hồi trước hay sau khi tạo job?
- Tài nguyên có tồn tại không?
- Cấu hình và dependency nào đang được sử dụng?

Nếu không nêu rõ, hai phép thử có thể đều mang tên “không có quyền” nhưng kiểm tra hai thuộc tính khác nhau.

### 4.2. Then phải mô tả cả tác động

Một phản hồi lỗi chưa chứng minh thao tác không xảy ra.

Với export, có thể cần kiểm tra:

- Không có job mới được chấp nhận.
- Không có file được công bố.
- Không có nội dung dữ liệu hoặc URL tải có hiệu lực được trả.
- Không có sự kiện nghiệp vụ báo thành công.
- Có audit từ chối theo chính sách.

Không dùng câu “không có ghi database nào” nếu hệ thống vẫn phải ghi audit hoặc trạng thái từ chối. Cần chỉ rõ những tác động nghiệp vụ nào bị cấm và những dấu vết vận hành nào vẫn bắt buộc.

### 4.3. Tiêu chí phải nhận diện được kết quả chưa đủ bằng chứng

Nếu request timeout, không thể mặc định rằng yêu cầu đã bị từ chối an toàn. Tác vụ có thể đã được chấp nhận ở server.

Tiêu chí cần chỉ ra điểm quan sát bổ sung như trạng thái job, object được công bố, event hoặc audit. Nếu chưa kiểm tra được, kết quả là chưa kết luận được, không phải đạt.

## 5. Tình huống xuyên suốt: xuất dữ liệu theo tenant

Giả sử dịch vụ cung cấp:

```text
POST /tenants/{tenantId}/exports
GET  /tenants/{tenantId}/exports/{jobId}
GET  /tenants/{tenantId}/exports/{jobId}/download
```

Hợp đồng minh họa:

- Người tạo cần được xác thực, có quyền export và thuộc tenant được phép.
- Tenant trong đường dẫn phải được đối chiếu với ngữ cảnh quyền đã xác minh.
- Job chỉ xử lý dữ liệu thuộc phạm vi được phép.
- Worker kiểm tra quyền trước khi đọc dữ liệu và trước khi công bố kết quả.
- Service tải kiểm tra quyền tại mỗi quyết định mở lượt tải mới.
- File chỉ được tải qua đường đáp ứng kiểm soát truy cập, không công khai trực tiếp.
- Kết quả có thời hạn mở lượt tải mới là 15 phút tính từ lúc READY.
- Có audit bắt buộc cho các hành động đã đặc tả.
- Retry có hợp đồng idempotency rõ ràng.

Tên role, thời hạn và hình thức API là lựa chọn của ví dụ. Hệ thống thực tế có thể dùng mô hình khác, nhưng cần giữ các bất biến liên quan.

### 5.1. Ma trận hành vi cơ bản

| Chủ thể và điều kiện | Hành động | Kết quả mong đợi trong ví dụ |
| --- | --- | --- |
| Chưa xác thực hoặc credential không hợp lệ | Gọi API được bảo vệ | 401; không tạo job và không trả dữ liệu |
| Đã xác thực, đúng tenant nhưng thiếu quyền tạo export | Tạo export | 403; không tạo job mới |
| Đã xác thực, không được phép truy cập tenant hoặc job đích | Tra cứu hoặc tải job | 404 với thông báo chung theo hợp đồng, không trả dữ liệu |
| Có đủ quyền, dữ liệu hợp lệ | Tạo export | 202 với job ID thuộc đúng phạm vi |
| Job READY, còn hạn, người tải có quyền hiện tại | Mở lượt tải mới | Trả đúng dữ liệu được phép |
| Job hết hạn | Mở lượt tải mới | Từ chối theo hợp đồng; không mở file cho lượt tải đó |
| Quyền hiện tại không đáp ứng | Worker hoặc service tải kiểm tra | Từ chối tại điểm cưỡng chế tương ứng |

Việc chọn 404 trong trường hợp không được phép xem tài nguyên nhằm giữ hợp đồng phản hồi chung về sự tồn tại trong phạm vi đó. Cần kiểm tra nội dung phản hồi và các trường metadata, không chỉ status code.

Nếu có yêu cầu hạn chế rò rỉ qua thời gian phản hồi hoặc kích thước, phải viết tiêu chí đo riêng. Cùng status code không tự chứng minh mọi kênh suy luận đã được loại bỏ.

## 6. Viết tiêu chí cho các ranh giới quan trọng

### 6.1. AC-EXP-01: từ chối truy cập chéo tenant

```text
Given:
  Principal P-A chỉ được phép truy cập tenant A.
  Job J-B thuộc tenant B và đang READY.
  P-A biết hoặc đoán được ID của J-B.

When:
  P-A gọi API tra cứu hoặc tải J-B qua các đường thuộc phạm vi.

Then:
  Phản hồi tuân theo hợp đồng từ chối chung.
  Không trả nội dung file, vị trí object hoặc URL tải có hiệu lực.
  Không mở một lượt tải được chấp nhận cho J-B.
  Có audit từ chối với metadata được phép ghi.
```

Bộ kiểm thử cần cả trường hợp job tồn tại và job không tồn tại để đối chiếu hợp đồng phản hồi. Cần kiểm tra các đường thay thế đã được xác định, chẳng hạn truy cập object trực tiếp nếu kiến trúc có đường đó.

### 6.2. AC-EXP-02: chỉ xuất đúng tập dữ liệu

```text
Given:
  Có dữ liệu kiểm thử được gắn nhãn thuộc tenant A và tenant B.
  P-A có quyền export một tập dữ liệu xác định trong tenant A.

When:
  Job của P-A hoàn tất và P-A tải kết quả hợp lệ.

Then:
  Kết quả chỉ chứa các bản ghi và trường thuộc phạm vi P-A được phép.
  Không chứa bản ghi của tenant B.
  Không chứa trường bị loại theo chính sách phân loại dữ liệu.
  Số lượng và định danh dữ liệu được đối chiếu với tập kỳ vọng.
```

Một ca từ chối chéo tenant chưa chứng minh đường đi thành công không trộn dữ liệu. Vì vậy cần tiêu chí kiểm tra nội dung của kết quả hợp lệ.

### 6.3. AC-EXP-03: quyền bị thu hồi trong luồng bất đồng bộ

Giả sử chính sách yêu cầu cập nhật quyền ảnh hưởng tới các quyết định mới trong tối đa 60 giây.

```text
Given:
  P-A đã tạo job khi còn quyền.
  Job đang chờ xử lý.
  Việc thu hồi quyền được commit tại nguồn quyền có thẩm quyền ở t0.

When:
  Worker bắt đầu kiểm tra để đọc dữ liệu tại thời điểm t >= t0 + 60 giây.

Then:
  Worker không chấp nhận quyền cũ.
  Không bắt đầu đọc dữ liệu phục vụ export đó.
  Job chuyển sang trạng thái từ chối theo hợp đồng.
  Không có kết quả READY có thể tải từ job đó.
```

Phạm vi đo là quyết định của worker trước khi đọc dữ liệu, không phải thời điểm client nhận thông báo.

Với job đã chạy trước khi thu hồi, ví dụ chọn thêm yêu cầu kiểm tra quyền trước khi công bố kết quả. Service tải cũng kiểm tra quyền hiện tại khi mở lượt tải mới. Nếu chính sách đòi hủy ngay cả xử lý đang chạy, cần tiêu chí riêng cho tín hiệu hủy và giới hạn thời gian thực thi.

Nếu dùng cache quyền, lỗi kết nối nguồn quyền và tuổi cache phải có hành vi xác định. Khi không bảo đảm độ mới theo hợp đồng, worker không tự dùng dữ liệu quá hạn để cho phép.

### 6.4. AC-EXP-04: audit không thể được bảo đảm

```text
Given:
  Một hành động yêu cầu audit bền vững trước khi được chấp nhận.
  Cơ chế ghi audit bắt buộc không thể xác nhận ghi bền vững.
  Không còn cơ chế đệm được phê duyệt đáp ứng hợp đồng.

When:
  Hệ thống xử lý hành động đó.

Then:
  Không chấp nhận tạo job hoặc công bố kết quả tại điểm được bảo vệ.
  Trả lỗi vận hành theo hợp đồng.
  Không báo thành công rồi bỏ mất audit.
  Có tín hiệu vận hành qua kênh còn khả dụng theo thiết kế.
```

Nếu thiết kế cho phép bộ đệm bền vững, tiêu chí cần nêu dung lượng, giới hạn tồn đọng và hành vi khi đầy. Một lệnh gửi log không lỗi chưa đủ chứng minh đã đáp ứng yêu cầu bền vững.

### 6.5. AC-EXP-05: không lộ bí mật qua log và lỗi

```text
Given:
  Request thử nghiệm chứa canary không có quyền thực,
  đại diện cho token hoặc dữ liệu cần bảo vệ.
  Các nhánh lỗi xác thực, validation, worker và storage được kích hoạt.

When:
  Hệ thống xử lý các request và job thử nghiệm.

Then:
  Đầu ra lỗi và log thuộc phạm vi không chứa giá trị canary thô.
  Không ghi toàn bộ request hoặc nội dung file export ngoài chính sách.
  Audit vẫn có các trường cần thiết đã được phép,
  như action, kết quả, định danh liên quan và correlation ID.
```

Bằng chứng cần kiểm tra nhiều kênh: log ứng dụng, log proxy nếu thuộc phạm vi, telemetry, báo cáo lỗi và artifact chẩn đoán. Không dùng token hoặc dữ liệu khách hàng thật để tạo phép thử rò rỉ.

## 7. Viết tiêu chí đo được cho thời gian, retry và giới hạn

### 7.1. Thời hạn cần có mốc bắt đầu và điểm cưỡng chế

Tiêu chí “file hết hạn sau 15 phút” còn mơ hồ. Cần xác định:

- Tính từ lúc tạo job, lúc READY hay lần tải đầu tiên?
- Đo bằng đồng hồ nào?
- Thời điểm bị kiểm tra là lúc mở lượt tải hay trong suốt stream?
- Các đường cache hoặc storage trực tiếp có nằm trong phạm vi không?

Ví dụ hợp đồng:

```text
readyAt là thời điểm server chuyển job sang READY.
expiresAt = readyAt + 15 phút.

Mọi quyết định mở lượt tải mới tại t >= expiresAt phải bị từ chối.
Request bắt đầu ngay trước mốc và tại đúng mốc được kiểm thử riêng.
```

Tiêu chí này nói về việc mở lượt tải mới. Nếu cần giới hạn stream đã mở, phải xác định hành vi và điểm kiểm soát tương ứng; không suy ra điều đó từ TTL của job.

Quyền truy cập hết hạn và xóa vật lý là hai yêu cầu cần đo riêng. Thời hạn dọn object, bản sao hoặc backup phải có phạm vi và chính sách của từng lớp lưu trữ.

### 7.2. Idempotency phải gắn với ngữ cảnh

Ví dụ hợp đồng tạo job:

- Key được ràng buộc với tenant, principal và loại thao tác.
- Trong 24 giờ, cùng key và cùng nội dung yêu cầu theo quy tắc chuẩn hóa trả cùng job ID.
- Cùng key nhưng nội dung khác trả 409 và không tạo job thứ hai.
- Các request đồng thời cùng key chỉ tạo một job nghiệp vụ được chấp nhận.
- Retry sau khi client timeout phải tra lại kết quả hoặc dùng cùng key theo hợp đồng.

Không yêu cầu “worker chỉ chạy đúng một lần” nếu hệ thống queue có thể giao lại message. Tiêu chí cần tập trung vào tác động nghiệp vụ: không công bố nhiều kết quả ngoài hợp đồng hoặc tạo thêm job do retry.

Nếu key hết hạn sau 24 giờ và có thể được dùng lại, hành vi đó phải được ghi rõ. Không mặc định nó bảo đảm chống lặp vô thời hạn.

### 7.3. Giới hạn tốc độ phải có đơn vị và quy tắc đếm

Ví dụ:

> Với mỗi cặp tenant–principal, không chấp nhận quá 5 job mới trong bất kỳ cửa sổ trượt 60 giây nào. Retry hợp lệ trả lại cùng job không được tính là một job mới.

Tiêu chí kiểm thử cần có:

- Request ngay dưới và tại ngưỡng.
- Request vượt ngưỡng.
- Request đồng thời.
- Sự kiện ngay trước và sau biên cửa sổ.
- Hành vi khi kho bộ đếm không khả dụng.
- Kết quả từ chối, ví dụ 429 theo hợp đồng API, và việc không tạo thêm job.

Nếu thuật toán thực tế dùng cửa sổ cố định hoặc token bucket, phải đặc tả đúng ngữ nghĩa đó. Không dùng một câu mô tả cửa sổ trượt để nghiệm thu một thuật toán có hành vi khác mà chưa đánh giá.

### 7.4. Ngưỡng thống kê và bất biến cứng

“P95 thời gian phản hồi đạt ngưỡng” là điều kiện thống kê trong một mô hình tải. “Không trả bản ghi của tenant khác” là bất biến bảo mật.

Không dùng một tỷ lệ thành công tổng để che vi phạm cô lập dữ liệu. Tương tự, việc mọi mẫu đo đều đạt giới hạn thời gian chỉ cung cấp bằng chứng cho phạm vi quan sát; cần thiết kế và giám sát tương ứng để duy trì cam kết khi vận hành.

## 8. Từ tiêu chí tới kế hoạch kiểm thử

Một tiêu chí có thể cần nhiều phép thử ở các tầng khác nhau:

| Tầng kiểm tra | Điều có thể chứng minh | Ví dụ |
| --- | --- | --- |
| Kiểm tra rule hoặc policy thuần | Quyết định với các tổ hợp điều kiện cụ thể | Role, tenant, trạng thái job và thời hạn |
| Kiểm thử service | Điểm cưỡng chế và tác động trong nghiệp vụ | Không tạo job khi thiếu quyền |
| Kiểm thử tích hợp | Liên kết API, worker, storage, audit và cache | Thu hồi quyền khi job đang chờ |
| Kiểm thử qua API | Hợp đồng quan sát từ bên gọi | Status, body, dữ liệu và URL |
| Kiểm thử lỗi, thời gian và cạnh tranh | Hành vi khi phụ thuộc lỗi hoặc nhiều thao tác cùng lúc | Audit gián đoạn, retry và expiry |
| Review thiết kế và cấu hình | Các đường đi không thể hiện đầy đủ trong một ca chạy | Storage không có đường công khai ngoài service |

Mỗi tầng nên có mục đích rõ ràng. Không cần nhân bản cùng một kiểm tra ở mọi tầng chỉ để tăng số lượng test.

### 8.1. Thiết kế ma trận chủ thể–tài nguyên–hành động

Đối với phân quyền, có thể kết hợp:

- Chưa xác thực, hợp lệ, hết hạn, bị thu hồi.
- Cùng tenant, tenant khác, không có membership.
- Có role, thiếu role, role bị thay.
- Tài nguyên tồn tại, không tồn tại, đã xóa, hết hạn.
- Thao tác tạo, xem trạng thái, tải, hủy.
- API trực tiếp, worker, đường storage liên quan.

Chọn các lớp tương đương và trường hợp biên dựa trên rủi ro. Không tuyên bố kiểm tra toàn bộ không gian trạng thái chỉ vì mỗi role có một ca thử.

### 8.2. Dữ liệu thử phải tạo được phân biệt

Dữ liệu nên có các bản ghi và trường được gắn nhãn theo tenant, quyền và độ nhạy. Nếu cả hai tenant đều có dữ liệu giống nhau, một phép thử có thể không phát hiện trộn dữ liệu.

Với audit, cần kiểm tra cả sự kiện bắt buộc có mặt và dữ liệu bị cấm không xuất hiện. Với job bất đồng bộ, cần quan sát trạng thái, nội dung object và các event liên quan.

### 8.3. Kiểm tra sức mạnh của phép thử

Trong môi trường thử được kiểm soát, có thể dùng một cấu hình hoặc biến thể cố ý vi phạm tiêu chí để xác nhận phép thử thật sự thất bại.

Ví dụ, nếu kiểm thử cô lập tenant vẫn đạt khi điểm kiểm soát bị vô hiệu hóa trong fixture thử nghiệm, bằng chứng chưa đủ mạnh.

Mục tiêu là kiểm tra khả năng phát hiện vi phạm, không tạo một phép thử chỉ lặp lại điều kiện nội bộ của implementation.

## 9. Quản lý bằng chứng và trạng thái nghiệm thu

### 9.1. Bằng chứng phải gắn với đối tượng được xét

Cần lưu các định danh phù hợp:

- Tiêu chí và phiên bản đặc tả.
- Candidate source và artifact được kiểm tra.
- Phiên bản policy, cấu hình và các phụ thuộc có ảnh hưởng.
- Môi trường, dữ liệu thử, cách chạy và thời điểm.
- Kết quả, log hoặc artifact quan sát cần thiết.
- Người hoặc cơ chế đưa ra kết luận.

Một báo cáo của candidate A không tự chứng minh candidate B đã đáp ứng tiêu chí. Thay đổi source, cấu hình, quyền hoặc đường triển khai có thể làm bằng chứng cũ mất liên quan.

### 9.2. Tách kết quả test khỏi quyết định

Một mô hình minh họa:

```text
testExecution:
  PASSED | FAILED | INCONCLUSIVE | NOT_RUN

criterionAssessment:
  VERIFIED | VIOLATED | INCONCLUSIVE | NOT_APPLICABLE

releaseDecision:
  READY | NOT_READY | NEEDS_EVIDENCE | READY_WITH_EXCEPTION
```

Một test PASSED không tự làm tiêu chí VERIFIED nếu còn đường bắt buộc chưa kiểm tra.

NOT_APPLICABLE cần có căn cứ về phạm vi, không phải cách thay thế cho việc chưa làm test. INCONCLUSIVE không được đổi thành VERIFIED chỉ vì chưa có bằng chứng thất bại.

Ngoại lệ rủi ro là một quyết định riêng. Nếu tiêu chí đang VIOLATED nhưng ngoại lệ hợp lệ cho phép phát hành, phải giữ rõ kết luận thực tế và ghi READY_WITH_EXCEPTION theo policy.

### 9.3. Đo độ bao phủ theo tiêu chí

Có thể theo dõi:

```text
Độ bao phủ xác minh =
  Số tiêu chí áp dụng đã VERIFIED
  / Tổng số tiêu chí áp dụng trong phạm vi
```

Cần báo kèm:

- Tiêu chí chưa kiểm tra hoặc chưa đủ bằng chứng.
- Tiêu chí vi phạm.
- Tiêu chí có ngoại lệ.
- Tiêu chí không áp dụng cùng lý do.
- Các khoảng trống về môi trường hoặc đường truy cập.

Không chỉ báo tỷ lệ test đạt. Một nghìn test chức năng đạt không bù được việc thiếu một tiêu chí cô lập tenant bắt buộc.

## 10. Điều kiện chặn phát hành và ngoại lệ

Một policy minh họa:

| Tình trạng | Quyết định |
| --- | --- |
| Mọi tiêu chí bắt buộc áp dụng đều VERIFIED, bằng chứng còn phù hợp | READY |
| Có vi phạm tiêu chí thuộc nhóm không được miễn | NOT_READY |
| Có tiêu chí bắt buộc chưa đủ bằng chứng | NEEDS_EVIDENCE |
| Có ngoại lệ hợp lệ cho điều kiện được phép miễn | READY_WITH_EXCEPTION |
| Ngoại lệ hết hạn, sai candidate hoặc sai môi trường | Không áp dụng ngoại lệ; đánh giá theo trạng thái thực tế |

Nhóm tiêu chí không được miễn cần được xác định theo chính sách của tổ chức và rủi ro sản phẩm. Không để công cụ tự suy ra thẩm quyền chấp nhận rủi ro chỉ từ một nhãn ticket.

Hồ sơ ngoại lệ tối thiểu cần nêu:

- Tiêu chí và yêu cầu liên quan.
- Vi phạm hoặc phần bằng chứng còn thiếu.
- Candidate, môi trường và thời hạn áp dụng.
- Rủi ro còn lại và biện pháp bù.
- Chủ sở hữu khắc phục và người có thẩm quyền chấp nhận.
- Điều kiện đánh giá lại và kế hoạch kết thúc.

Không sửa tiêu chí sau khi test thất bại chỉ để biến kết quả thành đạt. Nếu yêu cầu ban đầu không phù hợp, cần quyết định thay đổi có căn cứ, cập nhật mô hình rủi ro và lưu lịch sử.

Việc thắt chặt hoặc điều chỉnh tiêu chí là một phần của quản lý yêu cầu. Nó phải thể hiện rõ tác động tới thiết kế, kiểm thử và các bản phát hành liên quan.

## 11. Bộ tiêu chí rút gọn và chuỗi truy vết

Ví dụ bảng theo dõi cho tính năng export:

| ID | Tiêu chí | Rủi ro | Điểm cưỡng chế | Bằng chứng chính |
| --- | --- | --- | --- | --- |
| AC-EXP-01 | Không truy cập kết quả chéo tenant | R-EXP-01 | API và service tải | Matrix quyền, phản hồi và không có dữ liệu/URL sử dụng được |
| AC-EXP-02 | Kết quả chỉ chứa tập dữ liệu được phép | R-EXP-01 | Query và bộ tạo export | Đối chiếu nội dung với dataset phân loại |
| AC-EXP-03 | Quyền bị thu hồi có hiệu lực ở các điểm đã đặc tả | R-EXP-02 | Worker, bước công bố và tải | Test cache, thời gian và job chờ |
| AC-EXP-04 | Không chấp nhận hành động cần audit khi không bảo đảm audit | R-EXP-03 | Cổng tạo job và công bố | Fault injection và trạng thái nghiệp vụ |
| AC-EXP-05 | Không lộ bí mật qua đầu ra chẩn đoán | R-EXP-06 | Logger và error handler | Canary, log và schema đầu ra |
| AC-EXP-06 | Retry cùng ngữ cảnh không tạo thêm job | R-EXP-04 | API và quản lý idempotency | Test đồng thời, timeout và xung đột payload |
| AC-EXP-07 | Giới hạn tạo job áp dụng đúng hợp đồng | R-EXP-04 | Bộ đếm và quyết định nhận job | Test biên cửa sổ, cạnh tranh và lỗi bộ đếm |
| AC-EXP-08 | Không mở lượt tải mới sau expiresAt | R-EXP-05 | Service tải và đường storage | Test trước, tại và sau mốc, gồm đường thay thế |

Chuỗi truy vết tham khảo:

```mermaid
flowchart LR
    R[Rủi ro] --> Q[Yêu cầu bảo mật]
    Q --> A[Tiêu chí nghiệm thu]
    A --> T[Ca kiểm thử và review]
    T --> E[Bằng chứng theo candidate]
    E --> D[Quyết định phát hành]
    D --> O[Giám sát và tái đánh giá]
```

Nếu một tiêu chí chưa có điểm cưỡng chế trong thiết kế, cần xử lý khoảng trống đó trước khi coi việc bổ sung test là đủ.

Nếu một test không liên kết được với tiêu chí, nó vẫn có thể có giá trị khác, nhưng không nên dùng số lượng test đó để chứng minh một yêu cầu bảo mật đã hoàn tất.

## 12. Ma trận kiểm tra chất lượng đặc tả

| Tình huống | Điều cần quan sát | Kết luận kỳ vọng |
| --- | --- | --- |
| Thiếu hoặc sai credential | API, job và dữ liệu trả về | Không chấp nhận hành động được bảo vệ |
| Principal đúng tenant nhưng thiếu quyền | Quyết định và tác động | Từ chối theo hợp đồng, không tạo job |
| Đổi tenant hoặc job ID | Body, object, URL và audit | Không có dữ liệu chéo tenant |
| Export hợp lệ với dữ liệu nhiều tenant | Nội dung file | Chỉ có bản ghi và trường được phép |
| Quyền bị thu hồi khi job chờ | Thời điểm kiểm tra và dữ liệu đọc | Áp dụng mốc hiệu lực đã chọn |
| Cache quyền quá hạn hoặc nguồn quyền lỗi | Quyết định tại worker/tải | Không cho phép bằng dữ liệu ngoài hợp đồng |
| Audit không xác nhận được ghi bền vững | Trạng thái tạo/công bố và lỗi | Không báo thành công trái yêu cầu |
| Hai request cùng key chạy đồng thời | Job ID và tác động nghiệp vụ | Một job được chấp nhận theo hợp đồng |
| Cùng key nhưng payload khác | Phản hồi và số job | Xung đột, không tạo thêm job |
| Client timeout sau khi gửi request | Tra cứu trạng thái và retry | Không suy ra chưa có tác động chỉ từ timeout |
| Vượt ngưỡng tạo job | Quyết định và bộ đếm | Từ chối đúng phạm vi, không tạo job vượt hợp đồng |
| Tải ngay trước và tại expiresAt | Đồng hồ và điểm mở lượt tải | Đúng điều kiện biên |
| Dùng đường storage hoặc cache thay thế | Quyền và dữ liệu | Không vượt thời hạn hoặc phân quyền |
| Gây lỗi ở các tầng | Log, telemetry và output lỗi | Không phát tán canary đại diện bí mật |
| Một test bị skip hoặc môi trường lỗi | Báo cáo nghiệm thu | Không tự kết luận VERIFIED |
| Candidate đổi sau khi có bằng chứng | Revision, artifact và cấu hình | Đánh giá lại phần liên quan |
| Ngoại lệ hết hạn | Gate và lý do quyết định | Không dùng lại ngoại lệ để vượt policy |
| Khôi phục hoặc rollback bản cũ | Policy, quyền và kiểm soát hiện tại | Không dùng quyết định lịch sử vô điều kiện |

Ma trận giúp phát hiện các nhánh bị bỏ sót trước khi viết test chi tiết. Nó cũng chỉ ra những quan sát ngoài status code cần được chuẩn bị.

Đối với tiêu chí vận hành như phục hồi hoặc thay khóa, cần có diễn tập phù hợp với môi trường và phạm vi được phép. Một mô tả quy trình chưa chứng minh đội ngũ có thể đáp ứng thời hạn khi thực hiện.

## 13. Lỗi thường gặp khi viết tiêu chí

| Cách viết hoặc cách dùng còn yếu | Cách hoàn thiện |
| --- | --- |
| “Tính năng phải an toàn” | Nêu tài sản, rủi ro, hành động và kết quả quan sát |
| “Chỉ người có quyền được truy cập” | Xác định chủ thể, tài nguyên, tenant, hành động và trạng thái quyền |
| Chỉ có happy path | Thêm từ chối, lỗi phụ thuộc, thay đổi quyền và điều kiện biên |
| Chỉ kiểm tra status code | Kiểm tra dữ liệu, job, object, event và audit liên quan |
| “Có log đầy đủ” | Xác định sự kiện, trường bắt buộc, dữ liệu bị cấm và độ bền vững |
| “Thu hồi ngay lập tức” | Chọn mốc thời gian, nguồn sự kiện và điểm cưỡng chế có thể đo |
| “Retry không được lặp” | Nêu đơn vị tác động, ngữ cảnh key, thời hạn và hành vi đồng thời |
| “Xóa sau 15 phút” | Phân biệt hết quyền tải, dọn object và phạm vi bản sao/backup |
| “Đã chạy công cụ bảo mật” | Nối kết quả công cụ với yêu cầu cụ thể và kiểm tra khoảng trống |
| Test skip được tính đạt | Giữ NOT_RUN hoặc INCONCLUSIVE và áp gate tương ứng |
| Ngoại lệ được ghi như đã đạt | Giữ kết luận thực tế và hiển thị quyết định có ngoại lệ |
| Sửa câu chữ sau khi thất bại mà không có căn cứ | Quản lý thay đổi yêu cầu, rủi ro và lịch sử quyết định |
| Dùng báo cáo của candidate cũ | Ràng buộc bằng chứng với đúng revision, artifact và cấu hình |

Không phải mọi tiêu chí đều cần một con số. Với một bất biến như không trả dữ liệu chéo tenant, điều cần chính xác là phạm vi và kết quả bị cấm. Với thời gian hoặc giới hạn tài nguyên, con số chỉ có ý nghĩa khi đơn vị, mốc và cách đo được xác định.

## 14. Duy trì tiêu chí trong vòng đời phát triển

Khi phân tích yêu cầu, đội sản phẩm và bảo mật chuyển rủi ro thành thuộc tính bắt buộc. Trong thiết kế, đội kỹ thuật xác định các điểm cưỡng chế và hành vi lỗi. Khi triển khai, người phát triển và kiểm thử dùng cùng hợp đồng để tạo mã và bằng chứng. Trước phát hành, người có trách nhiệm đánh giá kết quả, phần chưa đủ và ngoại lệ.

Sau phát hành, một thay đổi về quyền, cache, worker, storage hoặc mô hình triển khai có thể làm tiêu chí cũ chưa còn đủ. Sự cố và phát hiện mới cần được chuyển thành tiêu chí hoặc phép thử hồi quy có phạm vi rõ.

Các nhóm yêu cầu khác cũng áp dụng cùng phương pháp:

- Xác thực: khi nào credential được chấp nhận, từ chối hoặc thu hồi.
- Phân quyền: ai được tác động tới tài nguyên nào và tại điểm nào.
- Dữ liệu: dữ liệu nào được trả, lưu, chuyển hoặc xóa trong phạm vi nào.
- Logging: sự kiện nào phải có và dữ liệu nào không được ghi.
- Phục hồi: trạng thái bảo mật nào phải được duy trì sau restore hoặc rollback.

Một bộ security acceptance criteria đủ rõ tạo được thỏa thuận chung giữa phát triển, kiểm thử, bảo mật và vận hành. Mỗi quyết định nghiệm thu phải nối được mục tiêu bảo vệ với điều kiện quan sát, bằng chứng cụ thể và rủi ro còn lại của đúng candidate được xét.

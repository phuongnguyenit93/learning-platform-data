# Bulkhead — Đặc tả yêu cầu cô lập tài nguyên để ngăn lỗi lan truyền

## 1. Bulkhead giải quyết vấn đề bảo mật nào?

Bulkhead là cơ chế chia tài nguyên hoặc khả năng xử lý thành các phần có giới hạn để sự cố ở một phần không chiếm hết năng lực của phần khác. Tên gọi gợi đến các khoang kín trên tàu: một khoang gặp sự cố thì phạm vi ảnh hưởng cần được giới hạn.

Trong hệ thống phần mềm, tài nguyên cần cô lập có thể là luồng xử lý, tác vụ đang chạy, kết nối cơ sở dữ liệu, bộ nhớ đệm, hàng đợi hoặc worker. Ranh giới cô lập có thể dựa trên loại chức năng, dịch vụ phụ thuộc, tenant hoặc mức độ quan trọng của tác vụ.

Ví dụ, một cổng quản trị cung cấp tra cứu hồ sơ và xuất báo cáo. Dịch vụ lưu trữ báo cáo bị chậm, làm các yêu cầu xuất giữ luồng và kết nối lâu hơn. Nếu cả hai chức năng dùng chung tài nguyên không có giới hạn riêng, người dùng không xuất báo cáo cũng có thể không tra cứu được hồ sơ.

Trong phạm vi module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, bài học xem bulkhead như một cách chuyển rủi ro cạn kiệt tài nguyên và lỗi lan truyền thành yêu cầu bảo mật cụ thể:

- Chức năng hoặc chủ thể nào phải được cô lập với nhau?
- Tài nguyên nào có giới hạn và giới hạn được áp dụng ở đâu?
- Khi đầy, hệ thống từ chối, chờ có giới hạn hay chuyển sang xử lý bất đồng bộ?
- Những chức năng nào phải tiếp tục đáp ứng khi một khoang bị bão hòa?
- Dữ liệu, phân quyền và audit phải được giữ đúng như thế nào trong chế độ suy giảm?
- Bằng chứng nào chứng minh ranh giới cô lập thực sự có hiệu lực?

Bulkhead không bảo đảm hệ thống chịu được mọi mức tải. Nó giới hạn mức chiếm dụng theo thiết kế và thu hẹp phạm vi ảnh hưởng trong các giả định đã nêu.

## 2. Từ sự cố vận hành đến mô hình đe dọa

Một người dùng hợp lệ có thể tạo nhiều tác vụ tốn tài nguyên. Một tenant có dữ liệu lớn có thể vô tình gây hiện tượng noisy neighbor. Dịch vụ phụ thuộc bị chậm cũng có thể giữ tài nguyên của hệ thống lâu đến mức tạo ra tác động giống tấn công từ chối dịch vụ.

Không cần giả định mọi sự cố đều có chủ đích. Yêu cầu bảo mật nên xét cả hành vi lạm dụng, lỗi triển khai và suy giảm của dịch vụ phụ thuộc.

| Kịch bản | Tài sản hoặc mục tiêu bị ảnh hưởng | Hướng yêu cầu |
| --- | --- | --- |
| Chức năng xuất dữ liệu giữ hết worker | Khả năng tra cứu và quản trị | Ngân sách worker riêng cho chức năng xuất |
| Một tenant chiếm toàn bộ năng lực chung | Tính sẵn sàng cho tenant còn lại | Giới hạn theo tenant, kèm giới hạn tổng |
| Dịch vụ phụ thuộc chậm | Luồng, socket và bộ nhớ bị giữ lâu | Giới hạn đồng thời, timeout và chấm dứt công việc thực tế |
| Hàng đợi tăng không giới hạn | Bộ nhớ, độ trễ và khả năng phục hồi | Dung lượng hàng đợi và thời gian chờ hữu hạn |
| Mỗi lần lỗi sinh nhiều retry | Tải phục hồi vượt khả năng xử lý | Ngân sách retry nằm trong cùng giới hạn tài nguyên |
| Client tự khai báo ưu tiên cao | Năng lực dành cho chức năng quan trọng bị chiếm | Phân loại phía máy chủ, dựa trên danh tính được xác minh |
| Khi quá tải, hệ thống bỏ kiểm tra quyền | Tính bí mật và toàn vẹn dữ liệu | Chế độ suy giảm không làm yếu xác thực, phân quyền hoặc audit |
| Nhiều khoang vẫn dùng chung một nút cổ chai | Cô lập bề ngoài nhưng lỗi vẫn lan | Kiểm tra toàn bộ đường đi tài nguyên |

Mục tiêu cần diễn đạt theo kết quả, chẳng hạn:

> Khi chức năng xuất báo cáo bị bão hòa trong phạm vi tải thử đã xác định, chức năng tra cứu được cấp tài nguyên riêng phải tiếp tục đạt chỉ tiêu đáp ứng đã phê duyệt; yêu cầu vượt giới hạn phải bị từ chối có kiểm soát và không gây tăng tài nguyên không giới hạn.

Câu này vẫn cần được bổ sung phạm vi, số đo và tiêu chí nghiệm thu trước khi trở thành yêu cầu đầy đủ.

## 3. Bulkhead khác các cơ chế lân cận như thế nào?

| Cơ chế | Kiểm soát chính | Điều nó không tự bảo đảm |
| --- | --- | --- |
| Bulkhead | Số lượng công việc và tài nguyên được giữ trong từng khoang | Không tự giới hạn mọi loại tài nguyên hoặc mọi nút cổ chai dùng chung |
| Rate limiter | Tốc độ tiếp nhận trong một khoảng thời gian | Request chậm vẫn có thể tích lũy nhiều công việc đồng thời |
| Timeout/deadline | Thời gian cho phép của thao tác hoặc toàn bộ yêu cầu | Client hết chờ không có nghĩa tác vụ phía dưới đã dừng |
| Circuit breaker | Hạn chế gọi một phụ thuộc đang có dấu hiệu lỗi | Không chia sẵn tài nguyên giữa mọi nhóm công việc |
| Backpressure | Truyền tín hiệu giảm tốc khi phía nhận không đủ khả năng | Không tạo thêm tài nguyên và cần phía gửi tuân thủ |
| Quota | Hạn mức sử dụng theo chủ thể hoặc chu kỳ | Hạn mức theo ngày không thay thế giới hạn đồng thời |

Các cơ chế thường phối hợp với nhau. Một phụ thuộc có circuit breaker vẫn có thể làm đầy pool trước khi bộ ngắt mở. Một API có rate limit vẫn có thể cạn luồng nếu thời gian xử lý tăng mạnh. Bulkhead giúp giới hạn số công việc được giữ trong những tình huống đó.

## 4. Chọn ranh giới cô lập đúng với rủi ro

### 4.1. Theo chức năng

Tách tra cứu tương tác khỏi xuất dữ liệu hoặc xử lý theo lô giúp công việc dài không chiếm hết năng lực của thao tác ngắn. Ranh giới cần dựa trên đặc điểm tài nguyên và mức độ quan trọng, không chỉ dựa vào tên endpoint.

Nếu hai endpoint gọi cùng một pool kết nối không có hạn mức riêng, việc đặt hai semaphore ở lớp HTTP có thể chưa đủ để bảo vệ cơ sở dữ liệu.

### 4.2. Theo phụ thuộc

Mỗi phụ thuộc có thể có giới hạn số lời gọi đang thực hiện. Khi một dịch vụ chậm, nó chỉ được giữ tối đa phần tài nguyên đã được cấp.

Cần kiểm tra cả chuỗi gọi. Nếu một yêu cầu fan-out thành nhiều lời gọi, giới hạn ở yêu cầu đầu vào không trực tiếp bằng giới hạn số kết nối phía dưới.

### 4.3. Theo tenant hoặc chủ thể

Giới hạn theo tenant giúp giảm nguy cơ một khách hàng chiếm hết khoang chung. Nó thường cần kết hợp với giới hạn tổng:

```text
số_tác_vụ_của_tenant ≤ hạn_mức_tenant
tổng_tác_vụ_trong_khoang ≤ hạn_mức_khoang
```

Chỉ có hạn mức tenant không ngăn tổng số tenant làm cạn tài nguyên. Chỉ có hạn mức tổng cũng không bảo đảm một tenant khác còn cơ hội được phục vụ.

Khoá phân vùng phải được tạo từ danh tính và tenant đã được xác minh. Không dùng trực tiếp header do client tự khai báo để quyết định hưởng ngân sách ưu tiên hoặc tạo khoang mới.

### 4.4. Theo mức độ quan trọng

Có thể dành năng lực riêng cho chức năng quản trị sự cố hoặc kiểm soát bảo mật. Tuy nhiên, một người có vai trò quản trị không mặc nhiên được đưa mọi tác vụ của họ vào khoang ưu tiên.

Quy tắc cần gắn với loại thao tác được duyệt. Xuất báo cáo lớn vẫn là công việc xuất báo cáo, kể cả khi người thực hiện có quyền cao.

### 4.5. Theo mức cô lập kỹ thuật

| Cách triển khai | Phạm vi tác động có thể giới hạn | Phần vẫn cần đánh giá |
| --- | --- | --- |
| Semaphore/giới hạn đồng thời | Số công việc đang giữ permit | Luồng chạy thực tế, CPU, bộ nhớ, kết nối dùng chung |
| Pool luồng hoặc worker riêng | Năng lực thực thi của nhóm công việc | Bộ nhớ tiến trình, scheduler, I/O và tài nguyên chung |
| Pool kết nối riêng hoặc quota kết nối có bảo đảm | Mức chiếm dụng kết nối theo nhóm | Năng lực CPU/I/O, lock và số kết nối của máy chủ DB |
| Tiến trình hoặc deployment riêng | Một phần miền lỗi runtime và khả năng cấp tài nguyên | Hạ tầng, network, DB và dịch vụ nền dùng chung |
| Phân tách hạ tầng sâu hơn | Nhiều lớp tài nguyên và miền lỗi hơn | Chi phí vận hành và các phụ thuộc chưa được tách |

Không có một kỹ thuật duy nhất đủ cho mọi rủi ro. Cần mô tả rõ bulkhead bảo vệ tài nguyên nào và những tài nguyên nào còn chia sẻ.

## 5. Lập ngân sách tài nguyên

### 5.1. Xác định đơn vị của giới hạn

Các câu “tối đa 10” hoặc “pool nhỏ” không thể nghiệm thu nếu không biết đơn vị:

- Mười yêu cầu HTTP đang xử lý hay mười tác vụ nền?
- Mười lời gọi đến một phụ thuộc hay mười giao dịch cơ sở dữ liệu?
- Giới hạn trên mỗi instance, mỗi tenant hay toàn cụm?
- Hàng đợi tính theo số phần tử, tổng byte hay cả hai?
- Hạn mức có bao gồm retry, fan-out và công việc còn chạy sau timeout không?

Một yêu cầu tốt phải trả lời được các câu này.

### 5.2. Liên hệ tốc độ đến với công việc đồng thời

Trong điều kiện tương đối ổn định, có thể dùng quan hệ ước lượng:

```text
số_công_việc_đồng_thời_trung_bình
    ≈ tốc_độ_đến × thời_gian_lưu_trong_hệ_thống_trung_bình
```

Ví dụ, 20 yêu cầu/giây với thời gian xử lý trung bình 0,1 giây tương ứng khoảng 2 yêu cầu đồng thời trung bình. Nếu thời gian xử lý tăng thành 5 giây, nhu cầu trung bình có thể thành khoảng 100 yêu cầu đồng thời.

Đây là công cụ lập ngân sách trong điều kiện phù hợp, không phải công thức chứng minh an toàn khi tải đột biến hoặc hệ thống mất ổn định. Cần xét phân bố thời gian xử lý, đuôi độ trễ, kích thước dữ liệu và tải kiểm thử đại diện.

### 5.3. Ví dụ ngân sách trên một instance

Giả sử cổng quản trị có hai khoang:

| Thuộc tính | Tra cứu tương tác | Xuất báo cáo |
| --- | --- | --- |
| Công việc đang thực thi tối đa | 24 | 4 |
| Số yêu cầu chờ tối đa | 8 | 0 |
| Thời gian chờ admission tối đa | 100 mili giây | Không chờ |
| Deadline đầu cuối của yêu cầu | 2 giây | 8 giây |
| Kết nối DB được dành tối đa | 32 | 8 |
| Hành vi khi đầy khoang | Từ chối có kiểm soát | Từ chối ngay, không chuyển sang khoang tra cứu |

Trong ví dụ, tổng ngân sách kết nối DB của một instance là 60, gồm 32 cho tra cứu, 8 cho xuất, 8 cho audit và 12 cho tác vụ vận hành. Các phần dành riêng phải được thực thi bằng cơ chế phù hợp; bốn con số cấu hình không tự tạo ra sự bảo đảm nếu thực tế mọi nhóm vẫn giành cùng pool.

Số kết nối tối đa cần được đối chiếu với hành vi thật. Nếu một tác vụ xuất mở nhiều kết nối hoặc tạo fan-out, phải chứng minh bốn tác vụ không thể vượt ngân sách tám kết nối dành cho khoang này.

Các giá trị trên chỉ minh họa. Dành 32 kết nối không có nghĩa DB chịu được 32 truy vấn nặng đồng thời mà không ảnh hưởng nhóm khác. CPU, I/O, lock và truy vấn vẫn có thể là nút cổ chai chung.

### 5.4. Từ instance lên toàn cụm

Nếu có N instance và mỗi instance cho phép 4 tác vụ xuất, giới hạn thực thi toàn cụm có thể lên đến 4 × N. Autoscaling không được vô tình nhân mức chiếm dụng DB vượt năng lực được duyệt.

Một yêu cầu cấp cụm cần chỉ rõ:

- Số instance tối đa và tổng ngân sách tài nguyên tại mức đó.
- Hạn mức tenant được áp dụng cục bộ hay toàn cụm.
- Cơ chế cấp quyền thực thi có bảo đảm tính nguyên tử phù hợp không.
- Hành vi khi bộ điều phối hoặc kho trạng thái hạn mức mất kết nối.
- Điều kiện thu hồi, hết hạn hoặc đối soát permit mà không cho phép công việc cũ và mới chạy chồng vượt giới hạn.

Không được coi giới hạn cục bộ là hạn mức tenant toàn cụm. Nếu lựa chọn cho phép sai số tạm thời, phải đặc tả biên sai số, thời gian tồn tại và rủi ro được chấp nhận.

## 6. Hàng đợi, timeout và vòng đời permit

### 6.1. Hàng đợi cũng là tài nguyên cần giới hạn

Giới hạn worker nhưng cho phép hàng đợi vô hạn có thể chuyển sự cố từ cạn luồng sang cạn bộ nhớ. Một phần tử hàng đợi có thể giữ payload, tham chiếu ngữ cảnh và thông tin kết nối, không chỉ một mã công việc nhỏ.

Yêu cầu nên quy định:

- Số phần tử tối đa và kích thước dữ liệu được giữ.
- Thời gian chờ tối đa trước khi bắt đầu thực thi.
- Cách loại bỏ công việc hết hạn hoặc bị hủy.
- Hành vi khi đầy và cách trả thông tin cho bên gửi.
- Với hàng đợi bền vững: dung lượng lưu trữ, tuổi công việc, retention và tốc độ xả sau phục hồi.

Nếu dùng xuất báo cáo bất đồng bộ, phải tách rõ API tiếp nhận, hàng đợi công việc và worker. Mỗi lớp cần ngân sách riêng; một API trả mã công việc nhanh không chứng minh pipeline phía sau đã được cô lập.

### 6.2. Timeout không đồng nghĩa tài nguyên đã được trả

Khi client hết chờ, truy vấn DB hoặc lời gọi mạng có thể vẫn chạy. Nếu hệ thống trả permit ngay tại thời điểm timeout trong khi công việc cũ còn giữ tài nguyên, nó có thể nhận thêm công việc và vượt giới hạn thực tế.

Nguyên tắc cần đặc tả:

> Permit đại diện cho công việc đang giữ tài nguyên chỉ được trả khi công việc và phần tài nguyên được tính vào giới hạn đã thực sự kết thúc hoặc được xác nhận giải phóng.

Có thể trả phản hồi timeout cho client trước, nhưng phải tiếp tục tính công việc còn chạy vào ngân sách. Nếu công việc không thể hủy, khoang có thể duy trì trạng thái đầy; thiết kế cần cơ chế xử lý tác vụ treo hoặc cô lập worker phù hợp.

Không dùng lease hết hạn như bằng chứng công việc đã dừng. Với giới hạn phân tán, cần xử lý trường hợp chủ cũ mất kết nối nhưng vẫn thực thi khi chủ mới được cấp permit.

### 6.3. Ví dụ luồng xử lý ở mức khái niệm

```text
handle(request):
    context = verify_identity_and_authorization(request)
    lane = classify_operation_on_server(request.operation, context)
    tenant_key = context.verified_tenant_id

    reservation = try_reserve_tenant_and_lane(tenant_key, lane)

    if reservation is denied:
        record_bounded_rejection_metric()
        return documented_overload_response()

    try:
        task = start_actual_work_with_deadline(request, lane)
    catch start_error:
        reservation.release_once()
        return mapped_failure(start_error)

    on_actual_completion(task):
        release_task_resources()
        reservation.release_once()

    return response_or_timeout_to_client(task)
```

Đây là mã giả, không phải API của một thư viện. `Try_reserve_tenant_and_lane` cần có ngữ nghĩa cấp phép rõ ràng: nếu không giữ được cả hai điều kiện, không để rò permit đã lấy một phần. Lỗi khởi tạo phải phân biệt trường hợp chưa tạo tác vụ với trường hợp tác vụ đã được gửi và còn chạy.

Các đường thành công, lỗi, hủy và timeout phải giải phóng đúng một lần. Việc ngắt chờ của client không được bỏ qua callback thu hồi hoặc trả permit sớm.

Xác thực cũng có thể tốn tài nguyên. Bulkhead ở tầng nghiệp vụ không tự bảo vệ bước xử lý trước admission. Cần có giới hạn kích thước request, bảo vệ điểm vào và ngân sách phù hợp cho các bước tiền xử lý; không thể chờ đến khi đọc toàn bộ payload lớn rồi mới nghĩ đến giới hạn.

## 7. Hành vi khi quá tải phải giữ nguyên kiểm soát bảo mật

### 7.1. Từ chối có kiểm soát

Khi khoang đầy, hệ thống phải phản hồi theo hợp đồng đã công bố. Ví dụ, vượt hạn mức tenant có thể dùng HTTP 429; thiếu năng lực của một nhóm dịch vụ có thể dùng HTTP 503, tùy ngữ nghĩa API được duyệt.

Yêu cầu cần chỉ rõ mã phản hồi, cấu trúc lỗi, thời hạn trả về và chính sách retry. Không đưa topology nội bộ, thông tin tenant khác hoặc dữ liệu nhạy cảm vào thông báo.

Nếu cung cấp hướng dẫn thử lại, phía gửi vẫn cần backoff có độ ngẫu nhiên và giới hạn retry. Một phản hồi từ chối không được tự động sinh nhiều lời gọi nội bộ vượt ngân sách.

### 7.2. Không mượn khoang theo cách phá ranh giới

Khi khoang xuất đầy, chuyển công việc sang pool tra cứu có thể xóa mục tiêu cô lập. Nếu có cơ chế dùng chung phần dư, phải đặc tả giới hạn, điều kiện thu hồi và năng lực tối thiểu được bảo vệ.

Với yêu cầu bảo mật cần phần năng lực dành riêng, phương án đơn giản hơn để kiểm chứng là không cho khoang ít quan trọng mượn phần đó.

### 7.3. Chế độ suy giảm không bỏ qua quyền và audit

Một số ví dụ cần bị cấm trong đặc tả:

- Bỏ kiểm tra quyền vì dịch vụ phân quyền đang bận.
- Đổi sang cache không có ranh giới tenant phù hợp.
- Tạm tắt audit của thao tác nhạy cảm để tăng throughput.
- Trả dữ liệu cũ mà không xét yêu cầu quyền truy cập và độ mới.
- Gắn nhãn ưu tiên cao theo header chưa xác minh.

Nếu thao tác bắt buộc phải có audit bền vững nhưng đường audit không còn đáp ứng, chính sách phải nêu rõ chặn, xếp hàng an toàn hoặc dùng cơ chế thay thế nào đã được phê duyệt. Dành riêng một pool audit không giải quyết toàn bộ bài toán lưu bền và mất dữ liệu.

### 7.4. Công bằng giữa tenant không tự xuất hiện

Một khoang chung có giới hạn tổng vẫn có thể bị một tenant chiếm hết. Hạn mức tenant giúp chặn điều đó nhưng chưa tự bảo đảm không bị starvation khi nhiều tenant cùng tranh phần còn lại.

Nếu cần bảo đảm công bằng, đặc tả thêm lịch phục vụ, năng lực tối thiểu hoặc điều kiện không bị chờ vô hạn. Đồng thời giới hạn số khoang/counter được tạo; kẻ gửi không được tạo vô hạn khóa phân vùng để gây cạn bộ nhớ.

Cơ chế dọn khóa phải tránh xóa bộ đếm của công việc đang chạy rồi tạo mới để vượt hạn mức. Metric và nhãn tenant cũng cần kiểm soát cardinality; không đưa định danh tùy ý vào nhãn giám sát không giới hạn.

## 8. Bộ yêu cầu bảo mật minh họa

### 8.1. Giả định kiểm thử

Ví dụ dưới đây sử dụng cổng quản trị và ngân sách tại mục 5.3. Phép thử có một instance, dữ liệu tổng hợp cố định, một tập người dùng hợp lệ và cấu hình hạ tầng được ghi lại.

Sau 60 giây làm nóng, duy trì 20 yêu cầu tra cứu/giây trong 5 phút quan sát, đồng thời làm chậm phụ thuộc của chức năng xuất và tạo đủ yêu cầu để khoang xuất liên tục đầy. Chỉ tiêu bảo vệ tra cứu là:

- p95 độ trễ phản hồi thành công không quá 300 mili giây.
- Tỷ lệ lỗi tra cứu không quá 1% trên toàn bộ yêu cầu tra cứu đã gửi.
- Timeout, lỗi kết nối và phản hồi từ chối tra cứu được tính là lỗi, không bị loại khỏi mẫu số.
- Phải báo cả số phản hồi thành công và số thất bại; không dùng riêng p95 của số ít phản hồi thành công để kết luận đạt.

Đây là tiêu chí cho kịch bản nghiệm thu đã giới hạn, không phải cam kết với mọi dữ liệu, số instance hoặc mức tấn công.

### 8.2. Ma trận yêu cầu

| ID | Yêu cầu có thể kiểm chứng | Chủ sở hữu | Bằng chứng đạt |
| --- | --- | --- | --- |
| BULK-01 | Mỗi thao tác phải được ánh xạ phía máy chủ vào khoang được duyệt; tenant và ưu tiên dựa trên ngữ cảnh đã xác minh. | Ứng dụng | Danh mục thao tác; thử giả mạo header không đổi được tenant hoặc khoang ưu tiên. |
| BULK-02 | Trên một instance, tối đa 24 tác vụ tra cứu và 4 tác vụ xuất được thực thi; công việc còn chạy sau timeout vẫn phải được tính. | Ứng dụng | Metric và quan sát worker/phụ thuộc chứng minh giới hạn trong cả lỗi, hủy và timeout. |
| BULK-03 | Hàng chờ tra cứu tối đa 8 yêu cầu, thời gian chờ tối đa 100 mili giây; khoang xuất không có hàng chờ trong bộ nhớ. | Ứng dụng | Khi đầy, số chờ không vượt giới hạn; request hết chờ không được bắt đầu thực thi sau đó. |
| BULK-04 | Mỗi tenant được chạy tối đa 2 tác vụ xuất trên một instance trong ví dụ này, đồng thời vẫn tuân theo giới hạn tổng 4. | Ứng dụng | Một tenant không chiếm cả bốn vị trí; các tác vụ còn chạy không bị mất khỏi bộ đếm. |
| BULK-05 | Các ngân sách DB 32/8/8/12 phải được thực thi; tổng cấu hình không vượt 60 kết nối trên một instance. | Nền tảng/DB | Cấu hình hiệu lực và đo kết nối theo nhóm; xuất không lấy phần dành cho tra cứu hoặc audit. |
| BULK-06 | Khi đầy khoang xuất, p95 thời gian phản hồi từ chối không quá 100 mili giây trong kịch bản thử; không chuyển tác vụ sang khoang tra cứu. | Ứng dụng | Phản hồi đúng hợp đồng và đo đầu cuối; không xuất hiện thực thi ở pool khác. |
| BULK-07 | Trong kịch bản mục 8.1, tra cứu phải đạt p95 ≤ 300 mili giây và tỷ lệ lỗi ≤ 1% khi xuất bị bão hòa. | Chủ dịch vụ | Báo cáo tải hợp lệ, phân bố độ trễ, mẫu số lỗi và cấu hình môi trường. |
| BULK-08 | Deadline tra cứu 2 giây và xuất 8 giây phải được truyền theo thiết kế; timeout không được trả permit trước khi công việc thực tế dừng và tài nguyên được tính đã được giải phóng. | Ứng dụng | Dấu vết timeout, thời điểm dừng thực tế, kết nối và số permit cho từng đường kết thúc. |
| BULK-09 | Retry và fan-out phải tính vào ngân sách tài nguyên tương ứng; không có đường thực thi bỏ qua admission. | Ứng dụng | Thử lỗi phụ thuộc; tổng lời gọi thực tế không vượt các giới hạn đã duyệt. |
| BULK-10 | Khi suy giảm, xác thực, phân quyền, ranh giới tenant và chính sách audit bắt buộc vẫn có hiệu lực. | Bảo mật/ứng dụng | Test lỗi dịch vụ kiểm soát và khoang audit; không phát sinh thao tác nhạy cảm ngoài chính sách. |
| BULK-11 | Tình trạng sử dụng, chờ, từ chối, timeout và tác vụ chưa dừng phải quan sát được theo khoang; bão từ chối không gây log hoặc metric tăng không giới hạn. | Vận hành | Dashboard, metric tổng hợp, chính sách ghi log và thử tải từ chối. |
| BULK-12 | Thay đổi số instance, hạn mức hoặc chính sách dùng chung tài nguyên phải đánh giá lại ngân sách toàn cụm và được kiểm thử trước khi áp dụng. | Nền tảng | Cấu hình triển khai tối đa, ngân sách phụ thuộc và kết quả thử mở rộng. |

Mỗi dòng là một yêu cầu hoặc nhóm điều kiện liên quan để minh họa. Trong dự án thật, có thể tách nhỏ nếu cần giao quyền sở hữu hoặc tiêu chí kiểm thử độc lập.

BULK-04 là giới hạn cục bộ, không phải cam kết “mỗi tenant tối đa hai tác vụ trên toàn hệ thống”. Nếu nghiệp vụ cần hạn mức toàn cụm, phải bổ sung cơ chế và tiêu chí riêng.

### 8.3. Mẫu đặc tả một yêu cầu đầy đủ

```text
ID: BULK-02
Mục tiêu: giới hạn ảnh hưởng của xuất báo cáo tới tra cứu
Rủi ro: R-AVAIL-03 — tác vụ xuất giữ tài nguyên khi phụ thuộc chậm
Phạm vi: một instance API trong cấu hình đã phê duyệt
Giới hạn:
  - Tra cứu: tối đa 24 tác vụ thực tế đang thực thi
  - Xuất: tối đa 4 tác vụ thực tế đang thực thi
  - Retry và công việc chưa dừng sau timeout vẫn được tính
Khi không còn chỗ:
  - Tuân theo hàng chờ và hợp đồng từ chối của từng khoang
  - Không chuyển xuất sang pool tra cứu
Điều kiện thu hồi permit:
  - Tài nguyên mà permit đại diện đã được giải phóng
  - Thu hồi đúng một lần trên mọi đường kết thúc
Chủ sở hữu: đội ứng dụng
Kiểm thử: T-BULK-01, T-BULK-03, T-BULK-04
Bằng chứng: metric, trace và quan sát worker/kết nối thực tế
```

Mẫu số và phạm vi phải được giữ nhất quán giữa cấu hình, dashboard và bài kiểm thử.

## 9. Quan sát, cảnh báo và phản ứng sự cố

### 9.1. Các tín hiệu tối thiểu

| Tín hiệu | Câu hỏi hỗ trợ trả lời |
| --- | --- |
| Giới hạn cấu hình và số công việc đang chạy | Khoang có đạt hoặc vượt ngân sách không? |
| Độ dài và tuổi phần tử hàng chờ | Có tích tụ công việc quá cũ không? |
| Số từ chối theo lý do | Hết hạn mức tenant, đầy khoang hay lỗi điều phối? |
| Độ trễ admission và xử lý | Thời gian bị tiêu ở khâu chờ hay phụ thuộc? |
| Timeout, hủy và tác vụ còn chạy | Client đã hết chờ nhưng tài nguyên còn bị giữ không? |
| Kết nối, worker, bộ nhớ và I/O | Có nút cổ chai chung làm mất hiệu lực cô lập không? |
| Thông lượng và lỗi của khoang được bảo vệ | Tính sẵn sàng cần bảo vệ có thực sự được giữ không? |

Không chỉ giám sát khoang đang đầy. Mục tiêu quan trọng là chứng minh khoang còn lại vẫn phục vụ được.

### 9.2. Ví dụ điều kiện cảnh báo

Trong hệ thống minh họa, có thể đặt cảnh báo khi khoang xuất ở mức sử dụng tối đa liên tục 60 giây, hoặc khi tra cứu vi phạm chỉ tiêu trong lúc xuất bão hòa. Điều kiện vận hành chính thức phải nêu cửa sổ tính toán, số mẫu tối thiểu, thời hạn gửi cảnh báo và điều kiện hết cảnh báo.

Một khoang đầy nhưng đang từ chối đúng thiết kế có thể là tín hiệu tải cần xử lý. Khoang đầy kèm tài nguyên thực tế vượt ngân sách lại có thể là lỗi thực thi giới hạn. Hai tình huống cần mức ưu tiên và hướng xử lý khác nhau.

Cần giới hạn hoặc tổng hợp log từ chối để tránh tạo một đường cạn tài nguyên mới. Chính sách này phải giữ đủ số đếm và bằng chứng cần thiết; không được vô tình làm mất audit bắt buộc của thao tác nhạy cảm.

### 9.3. Phục hồi có kiểm soát

Khi phụ thuộc trở lại, hàng đợi và retry có thể tạo đợt tải lớn. Quy trình phục hồi cần kiểm soát tốc độ nhận việc, hủy công việc hết hạn, giữ nguyên giới hạn khoang và theo dõi chức năng được bảo vệ.

Không tự tăng hạn mức cho đến khi hết cảnh báo. Thay đổi cần dựa trên năng lực phụ thuộc và ngân sách toàn cụm; nếu chỉ tăng pool, vấn đề có thể chuyển từ API sang DB.

Với tác vụ có tác dụng phụ, retry hoặc phục hồi phải xét tính idempotent, quyền tại thời điểm thực thi và trạng thái công việc. Bulkhead không tự ngăn cập nhật trùng hoặc tác vụ đã bị hủy vẫn tiếp tục ghi dữ liệu.

## 10. Ma trận kiểm thử nghiệm thu

Các phép thử thực hiện trong môi trường được kiểm soát, dùng dữ liệu tổng hợp và ghi lại giới hạn tải. Không cần một cuộc tấn công thực tế để chứng minh yêu cầu; có thể tiêm độ trễ, giới hạn phụ thuộc và tạo tải đại diện.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-BULK-01 | Giữ tác vụ xuất ở phụ thuộc chậm, gửi thêm yêu cầu vượt bốn vị trí. | Chỉ bốn tác vụ xuất thực thi; phần vượt bị từ chối đúng hạn; không dùng pool tra cứu. | BULK-02, 03, 06 |
| T-BULK-02 | Chạy tải tra cứu và xuất theo mục 8.1; quan sát cả DB và bộ nhớ. | Tra cứu đạt p95 và tỷ lệ lỗi; tài nguyên dùng chung không làm mất mục tiêu cô lập. | BULK-05, 07, 11 |
| T-BULK-03 | Làm client timeout hoặc ngắt kết nối trong khi phụ thuộc chưa dừng. | Công việc còn chạy vẫn tính vào ngân sách; không nhận thêm vượt giới hạn; permit thu hồi đúng khi hoàn tất. | BULK-02, 08 |
| T-BULK-04 | Tiêm lỗi trước khi khởi chạy, lỗi lúc chạy, hủy và lỗi lúc trả kết quả. | Không rò permit hoặc thu hồi hai lần; số đang chạy cuối thử trở về mức đúng. | BULK-02, 08 |
| T-BULK-05 | Tenant A gửi nhiều tác vụ xuất; tenant B đồng thời có nhu cầu hợp lệ. | A không vượt hai tác vụ trên instance; B có thể sử dụng phần còn lại theo chính sách lịch phục vụ. | BULK-01, 04 |
| T-BULK-06 | Làm đầy hàng chờ tra cứu và cho một số request hết 100 mili giây chờ. | Không quá tám phần tử; phần tử hết chờ không được thực thi muộn; bộ nhớ giữ trong ngân sách. | BULK-03, 11 |
| T-BULK-07 | Thay header tenant/ưu tiên, gọi đường retry và fan-out. | Không đổi được khoang trái phép; không có lời gọi bỏ qua admission; hạn mức tổng vẫn đúng. | BULK-01, 09, 10 |
| T-BULK-08 | Làm dịch vụ phân quyền hoặc lưu audit không đáp ứng. | Thao tác nhạy cảm theo đúng chính sách đã duyệt; không tự bỏ kiểm tra hoặc mất ranh giới tenant. | BULK-10 |
| T-BULK-09 | Tăng số instance tới mức tối đa được phép, đồng thời tạo tải xuất. | Tổng kết nối và tác vụ nằm trong ngân sách cấp cụm; giới hạn cục bộ không bị báo nhầm là toàn cụm. | BULK-05, 12 |
| T-BULK-10 | Phục hồi phụ thuộc sau thời gian chậm; có công việc chờ/retry. | Không có đợt xả vượt ngân sách; công việc hết hạn được xử lý đúng; tra cứu tiếp tục đạt tiêu chí. | BULK-07, 08, 09 |
| T-BULK-11 | Tạo nhiều yêu cầu bị từ chối và nhiều khóa phân vùng không hợp lệ. | Cardinality được kiểm soát, không tạo pool tùy ý; log/metric không thành nút cạn tài nguyên. | BULK-01, 11 |

Kết quả cần có số lượng thực tế, không chỉ ảnh chụp cấu hình. Một semaphore báo bốn permit đã dùng chưa chứng minh chỉ có bốn truy vấn đang chạy nếu permit bị trả sớm hoặc có đường gọi khác bỏ qua nó.

Mỗi lượt thử nên lưu phiên bản ứng dụng, cấu hình pool, dữ liệu đầu vào, phiên bản chính sách, số instance, timeline tiêm lỗi và báo cáo đo. So sánh với tải nền trong cùng điều kiện giúp phát hiện nút cổ chai chung.

## 11. Truy vết yêu cầu với rủi ro và kiến trúc

Chuỗi truy vết phù hợp với vòng đời phát triển:

```text
Mục tiêu an toàn thông tin
    → Kịch bản cạn tài nguyên hoặc lỗi lan truyền
    → Yêu cầu BULK-xx
    → Ranh giới và ngân sách kiến trúc
    → Cấu hình / triển khai admission và thu hồi
    → Test T-BULK-xx
    → Bằng chứng nghiệm thu và metric vận hành
```

| Mục tiêu | Rủi ro | Yêu cầu | Quyết định kiến trúc | Kiểm chứng |
| --- | --- | --- | --- | --- |
| Duy trì tra cứu khi xuất chậm | Xuất giữ hết tài nguyên | BULK-02, 05, 07 | Khoang thực thi và ngân sách DB riêng | T-BULK-01, 02 |
| Giảm noisy neighbor | Một tenant chiếm hết khoang xuất | BULK-01, 04 | Khóa tenant đã xác minh; giới hạn tenant và tổng | T-BULK-05, 07 |
| Giữ đúng giới hạn khi lỗi | Timeout trả permit nhưng công việc chưa dừng | BULK-02, 08 | Theo dõi vòng đời tài nguyên thực tế | T-BULK-03, 04 |
| Giữ phân quyền khi suy giảm | Fallback bỏ kiểm soát để tiếp tục phục vụ | BULK-10 | Chính sách suy giảm và audit được phê duyệt | T-BULK-08 |
| Tránh quá tải sau mở rộng | Hạn mức mỗi instance nhân theo số instance | BULK-12 | Ngân sách và giới hạn cấp cụm | T-BULK-09 |

Khi thêm endpoint, đổi truy vấn, tăng fan-out, thay chính sách retry hoặc thay số replica tối đa, cần đánh giá lại ngân sách và test liên quan. Việc giữ nguyên tên pool không chứng minh rủi ro không đổi.

Ngoại lệ phải có phạm vi, lý do, biện pháp bù, người phê duyệt và thời hạn. Không bỏ một đường gọi khỏi danh mục chỉ để kết quả đo trông đạt.

## 12. Các lỗi đặc tả thường gặp

| Cách viết hoặc triển khai | Vì sao chưa đủ | Cách cải thiện |
| --- | --- | --- |
| “Hệ thống phải có bulkhead.” | Không nêu tài nguyên, ranh giới và kết quả | Ghi nhóm cần cô lập, ngân sách và test khi bão hòa |
| “Mỗi API có pool riêng.” | Vẫn có thể tranh DB, CPU hoặc bộ nhớ | Lập bản đồ đường đi tài nguyên và kiểm thử nút dùng chung |
| “Giới hạn bốn yêu cầu.” | Không rõ instance, tenant, retry và công việc còn chạy | Định nghĩa đơn vị, phạm vi và vòng đời phép đếm |
| “Hết worker thì đưa vào queue.” | Queue có thể tăng vô hạn | Giới hạn số lượng, byte, thời gian chờ và hành vi khi đầy |
| “Timeout thì trả permit ngay.” | Công việc thực tế có thể chưa dừng | Chỉ thu hồi khi tài nguyên tương ứng được giải phóng |
| “Đầy khoang thấp thì mượn khoang cao.” | Có thể phá phần năng lực được bảo vệ | Cấm hoặc đặc tả cơ chế dùng chung có giới hạn và bảo đảm |
| “Có quota tenant là công bằng.” | Chưa ngăn starvation hoặc vượt tổng | Thêm hạn mức tổng và chính sách lịch phục vụ nếu cần |
| “Autoscaling sẽ xử lý quá tải.” | Có thể nhân mức chiếm dụng phụ thuộc | Kiểm soát ngân sách cấp cụm và sức chịu của phụ thuộc |
| “Quá tải thì tắt audit.” | Tính sẵn sàng làm suy yếu trách nhiệm giải trình | Đặc tả audit và hành vi từ chối an toàn theo tác vụ |
| “Đo p95 thành công là đủ.” | Có thể che giấu phần lớn yêu cầu thất bại | Đo đồng thời số gửi, số thành công, lỗi, timeout và từ chối |

## 13. Bài tập áp dụng

Một nền tảng có ba chức năng: tra cứu hồ sơ, nhập dữ liệu theo lô và xuất báo cáo. Cả ba dùng chung worker và DB. Khi một tenant nhập dữ liệu lớn, chức năng tra cứu của tenant khác bị timeout. Hệ thống dự kiến tăng tối đa từ hai lên sáu instance.

Hãy thực hiện:

1. Viết ba kịch bản rủi ro, gồm lạm dụng bởi người dùng hợp lệ và lỗi phụ thuộc.
2. Chọn ranh giới bulkhead theo chức năng và tenant; xác định phần tài nguyên còn dùng chung.
3. Lập ngân sách worker, hàng đợi, kết nối DB và deadline trên một instance.
4. Tính tổng giới hạn ở sáu instance; chỉ ra rủi ro nếu giữ nguyên hạn mức cục bộ.
5. Viết ít nhất năm yêu cầu có ID, phạm vi, ngưỡng, hành vi khi đầy, chủ sở hữu và bằng chứng.
6. Thiết kế test timeout nhưng công việc chưa dừng, request bị hủy và phục hồi sau bão hòa.
7. Chỉ rõ cách giữ xác thực, phân quyền, tenant và audit khi một khoang không đáp ứng.

Đáp án tốt phải chứng minh chức năng nào được bảo vệ trong điều kiện nào, thay vì chỉ vẽ thêm pool. Nếu bảo đảm phụ thuộc vào DB hoặc cơ chế hủy tác vụ, cần nêu cách kiểm chứng giả định đó.

## 14. Checklist chấp nhận yêu cầu

- Đã xác định khoang theo rủi ro và mục tiêu bảo mật chưa?
- Mọi tài nguyên quan trọng, kể cả hàng đợi và DB, đã được đưa vào ngân sách chưa?
- Giới hạn có đơn vị và phạm vi instance/tenant/toàn cụm rõ ràng không?
- Retry, fan-out và công việc còn chạy sau timeout có được tính không?
- Phân loại khoang có do máy chủ quyết định từ ngữ cảnh đáng tin không?
- Khi đầy có hành vi hữu hạn và hợp đồng phản hồi rõ ràng không?
- Có bảo vệ phần năng lực dành riêng khỏi cơ chế fallback hoặc mượn tài nguyên không?
- Thu hồi permit có đúng một lần và gắn với tài nguyên thực tế không?
- Chế độ suy giảm có giữ phân quyền, ranh giới tenant và audit không?
- Có đo được chức năng cần bảo vệ, mẫu số lỗi và tài nguyên dùng chung không?
- Phép thử có chứng minh ngăn lỗi lan truyền và phục hồi trong phạm vi đã định không?
- Thay đổi cấu hình và autoscaling có được kiểm tra lại ngân sách cấp cụm không?

Bulkhead trở thành yêu cầu bảo mật có thể kiểm chứng khi ranh giới, ngân sách, hành vi quá tải và kết quả cần bảo vệ đều được đặc tả rõ, rồi được chứng minh bằng quan sát tài nguyên thực tế trong các kịch bản lỗi.

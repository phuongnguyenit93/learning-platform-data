# Conflict metric: Đo lường xung đột trong logic nghiệp vụ

## 1. Mục tiêu và phạm vi

**Conflict metric** là chỉ số đo các lần xử lý gặp xung đột theo hợp đồng nghiệp vụ, chẳng hạn sửa dựa trên revision đã cũ, chuyển trạng thái không còn hợp lệ hoặc dùng lại khóa idempotency với payload khác. Chỉ số này giúp nhận biết nơi các command đang cạnh tranh, client đang dùng dữ liệu cũ hoặc có hành vi cố vượt qua quy tắc của hệ thống.

Trong chương **Observability** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, việc quan sát xung đột phải gắn với business invariants, state machine, quyền theo đối tượng, transaction và idempotency. Mục tiêu là hiểu điều gì bị chặn và tác động nào thực sự đã xảy ra, không chỉ đếm một mã HTTP.

Một conflict có thể là bằng chứng kiểm soát đang hoạt động đúng. Nhiều conflict cũng có thể đến từ lỗi giao diện, tác vụ nền cạnh tranh hoặc retry không phù hợp. Không suy từ “conflict tăng” thành “đã bị khai thác”, và cũng không suy từ “conflict bằng không” thành “hệ thống an toàn”.

Sau bài học, bạn cần có khả năng:

- Định nghĩa một conflict và đơn vị đếm ở đúng ranh giới xử lý.
- Tách xung đột nghiệp vụ, xung đột nội bộ của transaction và lỗi kỹ thuật.
- Xây dựng counter, tỷ lệ và ngưỡng quan sát có mẫu số rõ ràng.
- Tránh đếm trùng do retry và tránh cardinality không giới hạn.
- Kết nối metric với log, trace và audit để xác minh nguyên nhân.
- Kiểm thử rằng telemetry phản ánh đúng kết quả, không làm thay đổi quyết định nghiệp vụ.

## 2. Định nghĩa conflict theo hợp đồng của thao tác

### 2.1. Conflict phải có ý nghĩa cụ thể

Một command thường có các điều kiện về trạng thái, phiên bản hoặc tính duy nhất. Conflict xuất hiện khi command không thể được áp dụng theo hợp đồng đó trong ngữ cảnh hiện tại.

| Nhóm xung đột minh họa | Ví dụ | Điều hệ thống cần bảo vệ |
| --- | --- | --- |
| `version_mismatch` | Sửa đơn bằng revision 41 trong khi đơn đã ở revision 42 | Không ghi đè lựa chọn mới bằng dữ liệu cũ |
| `invalid_transition` | Duyệt một yêu cầu hoàn tiền đã hủy | Chỉ đi qua các cạnh hợp lệ của state machine |
| `idempotency_payload_mismatch` | Cùng khóa command nhưng số tiền hoặc đối tượng đã khác | Không dùng một kết quả cũ cho một ý định khác |
| `operation_in_progress` | Một thao tác trùng đang xử lý và hợp đồng từ chối lần gọi cạnh tranh | Không tạo hai tác động ngoài ý muốn |
| `duplicate_operation` | Command mới cố tạo một nghiệp vụ đã tồn tại theo khóa duy nhất nghiệp vụ | Giữ invariant về tính duy nhất |
| `other_conflict` | Xung đột đã được nhận diện nhưng chưa có nhóm chuẩn tương ứng | Giữ nhóm dự phòng hữu hạn và phát hiện thiếu phân loại |

Các tên reason trong bài là quy ước minh họa. Dự án cần định nghĩa chúng từ các kết quả của miền nghiệp vụ, không lấy nguyên thông báo exception làm nhãn metric.

### 2.2. Không phải mọi lần không thành công đều là conflict

Một số trường hợp nên được phân biệt:

- Request thiếu số lượng hoặc có số lượng âm: lỗi dữ liệu đầu vào theo hợp đồng.
- Caller không được quản lý đơn hàng: từ chối quyền, không phải version conflict để tiết lộ trạng thái đơn.
- Không kết nối được cơ sở dữ liệu: lỗi kỹ thuật hoặc kết quả chưa rõ, tùy ranh giới quan sát.
- Gặp optimistic conflict nội bộ nhưng retry an toàn đã thành công: có sự kiện cạnh tranh nội bộ, nhưng kết quả attempt bên ngoài có thể là applied.
- Cùng command hợp lệ được gọi lại và trả kết quả đã lưu: replay theo idempotency, không mặc định là conflict.
- Command mới được ghi nhận để xử lý bất đồng bộ: pending, chưa có nghĩa tác động nghiệp vụ đã hoàn tất.

Nếu gom các trường hợp này vào cùng một số đếm, chỉ số sẽ không trả lời được câu hỏi hệ thống đang chặn điều gì.

### 2.3. Mã HTTP chỉ là một lớp biểu diễn

Một sản phẩm có thể dùng HTTP 409 cho nhiều loại conflict. Điều kiện phiên bản qua giao thức khác có thể được biểu diễn bằng mã khác. Một API trả 200 hoặc 202 cũng có thể đang trả kết quả replay hoặc trạng thái chờ.

Không định nghĩa conflict metric bằng cách đếm tất cả response 409 trên gateway rồi coi đó là toàn bộ xung đột nghiệp vụ. Gateway có thể không biết transaction đã commit, request bị chặn ở tầng nào hoặc response đang đại diện cho một command cũ.

Ngược lại, nếu gateway và metric nghiệp vụ khác nhau, cần giải thích bằng ranh giới đo trước khi kết luận có lỗi. Hai chỉ số có thể đang đo hai tập sự kiện khác nhau.

### 2.4. Đang xử lý không tự động là xung đột

Với cùng khóa và cùng payload, một hợp đồng idempotency có thể trả trạng thái pending hoặc chờ kết quả của thao tác đang chạy. Khi đó, không tự gắn reason `operation_in_progress` chỉ vì tìm thấy bản ghi chưa hoàn tất.

Chỉ dùng reason này nếu hợp đồng thực sự trả một kết quả conflict cho lần gọi đó. Nếu trả lại kết quả pending đã có, phân loại theo replay và giữ trạng thái command trong log hoặc dữ liệu kết quả phù hợp.

## 3. Chọn đơn vị đếm trước khi đặt tên metric

### 3.1. Một attempt khác một command

Trong bài này, **attempt được đánh giá** là một lần gọi vào ranh giới xử lý command đã qua kiểm tra đầu vào và quyền cần thiết để đánh giá nghiệp vụ cho đối tượng. Mỗi lần gọi lại từ client là một attempt mới, dù cùng thuộc một command.

**Command** là một ý định nghiệp vụ có định danh và hợp đồng idempotency. **Lần thử nội bộ** là một vòng thực hiện bên trong attempt, chẳng hạn retry transaction được thiết kế cho thao tác phù hợp.

```text
Command A
    Attempt 1 từ client
        Lần thử transaction 1: cạnh tranh nội bộ
        Lần thử transaction 2: commit thành công
    Attempt 2 từ client vì mất phản hồi
        Trả kết quả A đã lưu
```

Với hợp đồng trong ví dụ:

- Có hai attempt được đánh giá: một applied và một replayed.
- Có một command nghiệp vụ được áp dụng.
- Có một sự kiện cạnh tranh nội bộ.
- Không có conflict ở kết quả cuối của hai attempt, nếu cả hai được xử lý như trên.

Không chia số lần cạnh tranh nội bộ cho số command rồi gọi đó là tỷ lệ attempt bị conflict. Tử số và mẫu số đang dùng các đơn vị khác nhau.

### 3.2. Xác định những request nằm ngoài tập đo

Counter chính trong bài không chứa request chưa qua được ranh giới đánh giá đã định nghĩa, như request sai cấu trúc hoặc bị từ chối quyền theo đối tượng. Các request đó cần được quan sát ở chỉ số request hoặc security rejection riêng với taxonomy hữu hạn.

Ranh giới này phải được mô tả và giữ ổn định giữa các phiên bản. Nếu đổi từ “mọi HTTP request” sang “attempt đã qua quyền” mà giữ nguyên dashboard, tỷ lệ trước/sau sẽ không còn so sánh trực tiếp được.

Không đọc đối tượng ngoài quyền chỉ để phân loại chi tiết conflict. Telemetry không được mở một đường truy cập mà luồng nghiệp vụ đã cấm.

### 3.3. Một nguồn phân loại kết quả cuối

Ở ranh giới đã chọn, một attempt nhận một kết quả cuối để ghi nhận:

| `result` minh họa | Ý nghĩa |
| --- | --- |
| `applied` | Thay đổi đã được commit tại nguồn theo hợp đồng |
| `no_change` | Command được xử lý nhưng không tạo thay đổi theo ngữ nghĩa đã định nghĩa |
| `replayed` | Trả kết quả của command đã được ghi nhận, không áp dụng lại |
| `pending` | Đã chấp nhận để xử lý tiếp theo hợp đồng, chưa khẳng định tác động cuối |
| `conflict` | Không áp dụng được vì xung đột đã phân loại |
| `rejected` | Từ chối bởi điều kiện nghiệp vụ khác sau ranh giới đánh giá |
| `error` | Lỗi mà kết quả không áp dụng đã được xác định trong phạm vi quan sát |
| `unknown` | Chưa xác định được kết quả cuối; cần đối chiếu |

Nếu đã biết transaction commit, mất kết nối khi trả response không biến kết quả nghiệp vụ thành rollback. Nếu chính thành phần quan sát không biết commit có xảy ra không, không được tự gán applied hoặc conflict.

Một command pending có thể hoàn tất sau đó. Sự kiện hoàn tất được đo ở ranh giới xử lý nền riêng; không sửa một mẫu counter quá khứ của attempt tiếp nhận như thể nó luôn đồng nghĩa với hoàn tất.

## 4. Thiết kế counter và labels

### 4.1. Một họ metric với kết quả và lý do hữu hạn

Một thiết kế minh họa:

```text
business_command_attempts_total{
    operation,
    result,
    conflict_reason
}
```

Đây là counter tích lũy tại tiến trình/nguồn đo, không phải số lượng của riêng cửa sổ năm phút. Quy ước:

- `operation`: mã thao tác chuẩn như `change_order_quantity` hoặc `approve_refund`.
- `result`: một trong các giá trị hữu hạn ở bảng trên.
- `conflict_reason`: nhóm chuẩn ở mục 2 khi result là conflict; các result khác dùng `none`.

Ví dụ một tập series:

```text
business_command_attempts_total{operation="approve_refund",result="conflict",conflict_reason="invalid_transition"}
business_command_attempts_total{operation="approve_refund",result="applied",conflict_reason="none"}
business_command_attempts_total{operation="approve_refund",result="replayed",conflict_reason="none"}
```

Các dòng này mô tả nhãn, không phải cú pháp bắt buộc của một thư viện. Môi trường có thể thêm service hoặc môi trường triển khai theo quy ước quan sát chung, nhưng phải kiểm soát số tổ hợp.

Dùng cùng một họ counter giúp chia tỷ lệ theo kết quả trên cùng tập attempt. Không cần cộng thêm counter conflict ở repository và middleware cho cùng một lần từ chối.

### 4.2. Không dùng định danh đối tượng làm metric label

Không đưa các giá trị sau vào labels của counter này:

- User ID, tenant ID riêng lẻ nếu số lượng không được giới hạn và thiết kế riêng.
- Order ID, refund ID, command ID, trace ID hoặc khóa idempotency.
- URL nguyên bản chứa ID, raw payload hoặc thông báo exception tự do.
- Policy version hoặc mã bản dựng sinh liên tục nếu không có kế hoạch quản lý số series.

Mỗi tổ hợp nhãn có thể tạo một chuỗi thời gian khác. Một caller gửi nhiều ID hoặc chuỗi lỗi khác nhau có thể làm số series tăng mạnh nếu hệ thống dùng trực tiếp dữ liệu đó làm label.

Giữ các ID cần điều tra trong log/audit được phân quyền. Metric thể hiện nhóm thao tác; log hoặc trace giải thích một trường hợp cụ thể. Một số môi trường có liên kết exemplar tới trace, nhưng việc có liên kết không bảo đảm trace đã được giữ đầy đủ.

### 4.3. Chuẩn hóa reason từ phía máy chủ

Mapper phải chuyển mã kết quả miền nghiệp vụ sang taxonomy hữu hạn. Không cho request gửi `conflict_reason=version_mismatch` rồi dùng nguyên trường đó để tăng metric.

`other_conflict` là nhóm phát hiện thiếu phân loại, không phải nơi che mọi lỗi. Nếu nhóm này tăng sau một bản phát hành, cần kiểm tra mapper và hợp đồng; không tự động diễn giải thành một loại tấn công mới.

### 4.4. Cạnh tranh nội bộ dùng metric riêng

Nếu cần quan sát retry transaction, có thể dùng:

```text
business_concurrency_events_total{
    operation,
    kind,
    resolution
}
```

`kind` và `resolution` phải là tập hữu hạn do dự án định nghĩa, chẳng hạn optimistic retry đã giải quyết hoặc lần xử lý dừng sau giới hạn retry.

Một attempt có thể tạo nhiều sự kiện nội bộ. Số đếm này không phải số attempt bị conflict ở kết quả cuối. Lock timeout, deadlock hoặc lỗi kết nối cần được phân loại theo điều hệ thống thực sự biết, không tự coi là xung đột do caller gửi revision cũ.

## 5. Tính số lượng, tỷ lệ và phân bố

### 5.1. Tử số và mẫu số phải cùng tập đo

Với thao tác `o` và cửa sổ `W`, đặt:

```text
C(o, W) = số tăng của counter có result=conflict trong W
N(o, W) = tổng số tăng của counter cho mọi result trong W

Conflict rate(o, W) = C(o, W) / N(o, W), khi N(o, W) > 0
```

Mẫu số gồm mọi attempt đã đi qua ranh giới đánh giá và có kết quả được quan sát, kể cả replayed, pending, error và unknown. Đây là tỷ lệ theo attempt tại ranh giới đó, không phải tỷ lệ command duy nhất bị ảnh hưởng hoặc tỷ lệ toàn bộ HTTP traffic.

Nếu cần một tỷ lệ chỉ trên các quyết định đã xác định, có thể xây dựng chỉ số khác với mẫu số loại unknown hoặc error phù hợp. Phải đặt tên và giải thích riêng; không âm thầm đổi tập kết quả trong mẫu số của dashboard cũ.

Ví dụ trong năm phút, `approve_refund` có 1000 attempt được ghi nhận, trong đó 160 conflict. Tỷ lệ theo định nghĩa trên là 16%. Nếu 120 trong số conflict là version mismatch, tỷ trọng version mismatch trong nhóm conflict là 75%, còn tỷ lệ version mismatch trên mọi attempt là 12%.

Ba con số trả lời ba câu hỏi khác nhau. Không trình bày “75% request lỗi phiên bản” khi mẫu số thực tế chỉ là các conflict.

### 5.2. Không lấy tổng counter làm số của một cửa sổ

Counter có thể reset khi tiến trình khởi động lại hoặc thay nguồn đo. Hệ thống truy vấn phải dùng phép tính tăng/rate có xử lý reset theo backend, tổng hợp các instance trong cùng phạm vi và hiểu cách backend xử lý khoảng trống.

Không trừ hai giá trị bất kỳ rồi biến kết quả âm thành “số conflict âm”. Cũng không cộng cả series đã tổng hợp với các series nguồn của chính nó.

Số tăng do hệ thống truy vấn ước lượng từ các lần thu thập có thể không là số nguyên chính xác. Metric vận hành không mặc nhiên là sổ đối soát đầy đủ cho từng command.

### 5.3. Không có traffic khác với không có conflict

- `N > 0`, `C = 0`: có attempt được quan sát nhưng không có conflict trong tập đó.
- `N = 0`: tỷ lệ không xác định vì không có mẫu số.
- Không có dữ liệu thu thập: chưa biết tình hình, không được đổi thành 0% thành công.

Dashboard cần phân biệt no traffic và no data theo khả năng của hệ thống. Một metric biến mất sau khi instrumentation bị lỗi không phải tín hiệu hệ thống an toàn hơn.

### 5.4. Xem cả phân bố và số lượng tuyệt đối

Một client retry liên tục có thể làm tỷ lệ tăng; nhiều replay hợp lệ cũng có thể làm mẫu số tăng và khiến tỷ lệ giảm. Vì vậy, cần xem đồng thời số conflict, tổng attempt và phân bố các result.

Số command hoặc đối tượng duy nhất bị ảnh hưởng là câu hỏi khác. Có thể điều tra từ log/audit hoặc một pipeline tổng hợp được thiết kế riêng, với giới hạn lưu và độ đầy đủ rõ ràng. Không giải quyết bằng cách thêm command ID làm label của counter.

## 6. Đặt instrumentation tại ranh giới có kết quả đáng tin

### 6.1. Không tăng conflict ngay khi thấy một exception nội bộ

Một exception cạnh tranh có thể được xử lý bên trong transaction retry. Nếu repository tăng conflict counter và handler cũng tăng lần nữa khi trả kết quả, cùng một attempt có thể bị đếm hai lần hoặc vừa applied vừa conflict.

Counter kết quả attempt phải có một nơi chịu trách nhiệm phân loại và ghi nhận. Các tầng thấp có thể phát metric cạnh tranh nội bộ riêng, nhưng không tự gán kết quả cuối của attempt bên ngoài.

Một luồng minh họa:

```text
operation = mã thao tác chuẩn do máy chủ xác định
context = xác thực, kiểm tra request và quyền theo đối tượng

observed_result = unknown
conflict_reason = none

TRY
    result = thực thi command theo transaction và idempotency
    observed_result = phân loại từ kết quả đã biết của nguồn
    conflict_reason = reason chuẩn nếu result là conflict
    chuẩn bị phản hồi theo hợp đồng
CATCH xung đột nghiệp vụ đã xác định
    observed_result = conflict
    conflict_reason = ánh xạ mã miền nghiệp vụ sang nhóm hữu hạn
    chuẩn bị phản hồi conflict theo hợp đồng
CATCH lỗi đã xác định không áp dụng thay đổi
    observed_result = error
    xử lý lỗi theo hợp đồng
CATCH kết quả commit chưa xác định
    observed_result = unknown
    đối chiếu command theo quy trình, không tự áp dụng lại
FINALLY
    cố gắng tăng counter một lần tại ranh giới này
    dùng operation, observed_result và conflict_reason đã chuẩn hóa
```

Giả mã thể hiện trách nhiệm, không phải khuôn catch exception cho mọi framework. Kết quả rejected, no change, replayed và pending phải được phân loại khi hợp đồng có những trường hợp đó.

### 6.2. Một nơi ghi nhận không tạo bảo đảm exactly once bền vững

Trong đường chạy hoàn tất bình thường, cấu trúc trên tránh tăng counter ở nhiều tầng cho cùng một kết quả. Nó không bảo đảm mọi attempt trong thực tế luôn có đúng một mẫu metric bền vững.

Tiến trình có thể dừng sau commit nhưng trước khi tăng counter; metric có thể mất trước lần thu thập tiếp theo. Một attempt bị hủy giữa chừng cũng có thể chưa đi tới bước phân loại cuối. Không dùng tổng counter để thay thế audit hoặc command store có bảo đảm lưu phù hợp.

Nếu cần thống kê bền vững theo sự kiện đã commit, có thể xây pipeline từ nguồn durable được thiết kế cho mục tiêu đó. Pipeline vẫn phải xử lý giao trùng và định nghĩa rõ đang đếm command hay attempt. Không tự coi một consumer nhận message nhiều lần là nhiều thay đổi nghiệp vụ.

### 6.3. Phân loại từ điều đã kiểm chứng

Một update ảnh hưởng không dòng nào chưa tự chứng minh version mismatch. Đối tượng có thể không còn tồn tại, không ở đúng phạm vi hoặc không đáp ứng một điều kiện khác trong câu lệnh.

Mapper cần dựa vào hợp đồng, kết quả kiểm tra và ngữ cảnh được phép quan sát. Không thực hiện một truy vấn bỏ kiểm tra tenant chỉ để giải thích chi tiết cho metric. Không đổi lỗi lạ thành conflict nhằm làm biểu đồ error đẹp hơn.

Tương tự, việc middleware thấy client ngắt kết nối không tự chứng minh command đã thất bại. Phải phân biệt kết quả nghiệp vụ tại nguồn với kết quả giao phản hồi ở tầng vận chuyển.

### 6.4. Lỗi telemetry không được thay đổi quyết định nghiệp vụ

Bước tăng metric không nên làm transaction đã commit bị báo như chưa commit, làm mất response đúng hoặc gây retry tác động nghiệp vụ. Không thực thi lại command chỉ vì exporter metric không sẵn sàng.

Nếu hệ thống có yêu cầu audit bền vững bắt buộc trước khi chấp nhận thao tác, đó là hợp đồng lưu bằng chứng riêng. Không nhập nhằng giữa yêu cầu đó với một counter vận hành được phát theo cơ chế best effort.

## 7. Đọc dashboard theo thao tác và bối cảnh

### 7.1. Bộ góc nhìn tối thiểu

Một dashboard cho conflict nên thể hiện đồng thời:

| Góc nhìn | Câu hỏi được hỗ trợ |
| --- | --- |
| Conflict count theo operation và reason | Loại xung đột nào đang tăng ở thao tác nào? |
| Conflict rate cùng số attempt | Mức tăng tương ứng với traffic hay tỷ lệ đã thay đổi? |
| Phân bố applied, replayed, pending, error, unknown | Conflict tăng cùng retry, lỗi nguồn hay thay đổi cách tiếp nhận? |
| Cạnh tranh nội bộ và độ trễ | Có dấu hiệu contention hoặc vòng retry nội bộ tăng không? |
| Security rejection liên quan | Có nhiều request sai quyền nằm ngoài tập conflict chính không? |
| Độ đầy đủ của telemetry | Có nguồn đo hoặc luồng thu thập nào đang mất dữ liệu không? |

Các tín hiệu đi cùng nhau hỗ trợ đặt giả thuyết, không tự chứng minh quan hệ nhân quả. Latency tăng và conflict tăng có thể có chung một nguyên nhân, hoặc là hai vấn đề độc lập.

### 7.2. Tỷ lệ tổng có thể tăng chỉ vì cơ cấu traffic đổi

Xét hai thao tác có tỷ lệ riêng không thay đổi:

| Giai đoạn | Thao tác A | Thao tác B | Tỷ lệ tổng |
| --- | --- | --- | --- |
| Ban đầu | 100 attempt, 20 conflict | 900 attempt, 0 conflict | 20/1000 = 2% |
| Sau đó | 100 attempt, 20 conflict | 100 attempt, 0 conflict | 20/200 = 10% |

Tỷ lệ tổng tăng từ 2% lên 10%, nhưng A vẫn có 20 conflict trên 100 attempt, B vẫn không có conflict. Sự thay đổi là tỷ trọng traffic, không phải bằng chứng một thao tác đã trở nên dễ bị xung đột hơn.

Vì vậy, xem theo operation và reason trước khi dùng một tỷ lệ toàn service để điều tra. Khi so sánh các cửa sổ, cũng cần biết có thay đổi instrumentation, luồng client hoặc chế độ xử lý đồng bộ/bất đồng bộ không.

### 7.3. Baseline phải tương ứng với luồng sử dụng

Một màn hình nhiều người cùng sửa có thể thường gặp version mismatch. Một thao tác duyệt một lần hiếm khi có invalid transition có baseline khác.

So sánh với lịch sử của chính thao tác, trong điều kiện traffic và triển khai có ý nghĩa. Không áp một ngưỡng chung chỉ vì tất cả cùng được gọi là conflict.

Giữ thông tin về thay đổi giao diện, chính sách và triển khai ở nơi có thể đối chiếu với cửa sổ quan sát. Không cần biến mọi phiên bản đó thành label tồn tại vô hạn trên counter.

## 8. Thiết kế cảnh báo có thể hành động

### 8.1. Kết hợp tỷ lệ, số lượng và thời gian

Một quy tắc minh họa cho thao tác có đủ traffic:

```text
Cửa sổ: 5 phút
Điều kiện cùng thỏa:
    conflict rate > 10%
    conflict count >= 30
    evaluated attempts >= 200
Duy trì theo hai cửa sổ đánh giá liên tiếp đã định nghĩa
```

Các con số chỉ để minh họa cách kết hợp điều kiện, không phải ngưỡng khuyến nghị cho mọi hệ thống. Cần chọn từ baseline, mức độ quan trọng của thao tác, thời gian phản ứng và chi phí nhiễu của sản phẩm.

Nếu dùng cửa sổ chồng lấn, hai lần đánh giá không phải hai bộ quan sát độc lập. Hãy mô tả cách tính và thời gian duy trì để người vận hành hiểu cảnh báo thực sự khẳng định điều gì.

### 8.2. Traffic thấp cần cách đánh giá riêng

Bốn conflict trong mười attempt tạo tỷ lệ 40%, nhưng có ý nghĩa vận hành khác với bốn nghìn conflict trong mười nghìn attempt. Cần xem số tuyệt đối và bối cảnh, không chỉ phần trăm.

Ngược lại, không dùng điều kiện traffic tối thiểu để bỏ qua mọi bất thường ở thao tác hiếm nhưng quan trọng. Có thể cần quy tắc riêng dựa trên một số lần xung đột liên tiếp, một mẫu hành vi hoặc bằng chứng vi phạm invariant từ nguồn đáng tin cậy.

Một tác động trái phép được xác nhận có thể nghiêm trọng dù conflict counter bằng không. Cảnh báo về invariant bị phá không được phụ thuộc vào việc số conflict đã đủ lớn hay chưa.

### 8.3. Nội dung cảnh báo phải nói rõ phạm vi đo

Thông báo nên có:

- Operation, reason chính, môi trường và nguồn đo.
- Cửa sổ, số conflict, số attempt và tỷ lệ tương ứng.
- Phân bố kết quả đáng chú ý, chẳng hạn replayed hoặc unknown tăng.
- Độ tin cậy dữ liệu: có thiếu nguồn thu thập hay thay đổi schema không.
- Liên kết tới dashboard và nơi tra log/audit theo quyền.
- Hướng điều tra ban đầu, không kết luận tự động rằng đã có tấn công thành công.

Không đưa payload, thông tin cá nhân hoặc khóa idempotency vào nội dung cảnh báo chỉ để tiện tra cứu.

### 8.4. Không giảm conflict bằng cách bỏ kiểm soát

Những cách sau có thể làm metric đẹp hơn nhưng làm bảo mật logic tệ đi:

- Bỏ kiểm tra revision hoặc tự ghi đè theo kiểu lần ghi sau thắng.
- Tự cập nhật expected revision rồi lặp lại một quyết định mà người dùng chưa xác nhận trên dữ liệu mới.
- Đổi idempotency key khi payload bị báo không khớp để thử áp dụng lại.
- Bỏ điều kiện trạng thái hoặc phê duyệt vì chúng làm nhiều request bị chặn.
- Đổi tên conflict thành applied hoặc rejected mà không thay hợp đồng và dashboard.

Xử lý đúng là giải quyết nguyên nhân, như refresh dữ liệu và xin lựa chọn mới khi cần, sửa luồng client hoặc điều chỉnh retry an toàn theo invariant. Không mọi command đều có thể retry tự động sau khi đọc trạng thái mới.

## 9. Phân biệt dấu hiệu lạm dụng với cạnh tranh hợp lệ

### 9.1. Các giả thuyết cần kiểm tra

| Dấu hiệu | Giả thuyết có thể có | Bằng chứng cần bổ sung |
| --- | --- | --- |
| Version mismatch tăng sau một bản giao diện mới | Client giữ revision cũ hoặc có nhiều người cùng sửa | Phiên bản client, command flow và audit revision |
| Invalid transition lặp lại trên thao tác duyệt | Worker cũ, client stale hoặc cố bỏ qua state machine | Trạng thái có thẩm quyền, actor và chuỗi command |
| Idempotency payload mismatch tăng | Client tái sử dụng key sai hoặc cố thay ý định dưới cùng key | Fingerprint/reference được bảo vệ và hợp đồng của client |
| Operation in progress tăng cùng latency | Backend chậm hoặc caller retry quá nhanh | Thời gian xử lý, trạng thái command và vòng retry |
| Duplicate operation tăng | Giao trùng, thiếu đối soát hoặc tạo nhiều command cho cùng nghiệp vụ | Khóa duy nhất nghiệp vụ và tác động thực tế |
| Conflict giảm đột ngột trong khi applied bất thường | Thay đổi traffic, mất instrumentation hoặc kiểm soát bị bỏ qua | Sức khỏe telemetry và kiểm chứng invariant từ nguồn |

Mỗi hàng là một tập giả thuyết. Metric tổng hợp không đủ để quy kết một người dùng hoặc xác nhận có khai thác thành công.

### 9.2. Hành vi bị chặn khác với tác động đã xảy ra

Nếu một actor liên tục duyệt yêu cầu đã hủy và hệ thống từ chối đúng, đó có thể là dấu hiệu lạm dụng bị chặn. Cần điều tra theo quyền và bối cảnh; không ghi rằng tiền đã được hoàn trái phép chỉ vì conflict tăng.

Nếu audit hoặc đối soát chứng minh một yêu cầu đã hủy vẫn tạo tác động hoàn tiền, đó là bằng chứng khác về invariant bị phá. Mức phản ứng phải dựa trên tác động đã xác minh, không chỉ tỷ lệ conflict.

Một attacker cũng có thể tạo nhiều request được chấp nhận hoặc replay để làm mẫu số tăng. Vì vậy, số tuyệt đối, phân bố kết quả và phân tích có phạm vi từ log/audit vẫn quan trọng.

### 9.3. Cần kiểm tra cả những request ngoài tập metric chính

Caller sai quyền có thể bị chặn trước khi tới bước kiểm tra revision hoặc state machine. Conflict metric có thể không đổi, trong khi security rejection tăng rõ rệt.

Cần giữ sự phân biệt này trong dashboard và runbook. Không chuyển request sai quyền vào nhóm conflict chỉ để quan sát chúng ở cùng một biểu đồ, nhất là khi điều đó làm lộ trạng thái đối tượng.

## 10. Kết nối metric với log, trace và audit

### 10.1. Mỗi loại dữ liệu trả lời một câu hỏi

| Loại dữ liệu | Vai trò |
| --- | --- |
| Metric | Nhận biết quy mô, tỷ lệ, xu hướng và thời điểm bất thường |
| Log có cấu trúc | Giải thích kết quả một attempt và mã lý do chuẩn |
| Trace | Theo dõi đường xử lý, độ trễ và các lần gọi thành phần |
| Audit/command store | Đối chiếu quyết định, revision và kết quả được lưu theo hợp đồng |

Một trace có thể bị sampling hoặc không được giữ. Không tìm thấy trace không chứng minh request không tồn tại. Tương tự, log nói “đang xử lý” không chứng minh transaction đã commit.

Counter cho mọi attempt ở ranh giới này không nên bị suy ra đơn giản từ một tập trace đã sampling. Nếu chỉ có số liệu ước lượng từ sampling, phải trình bày giới hạn và phương pháp, không gọi nó là tổng attempt chính xác.

### 10.2. Ví dụ log cho một conflict đã xác định

```json
{
  "event_type": "BUSINESS_COMMAND_ATTEMPT_FINISHED",
  "operation": "approve_refund",
  "result": "conflict",
  "conflict_reason": "invalid_transition",
  "tenant_ref": "tenant-demo",
  "object_ref": "refund-318",
  "actor_ref": "staff-12",
  "command_ref": "command-772",
  "attempt_ref": "attempt-905",
  "trace_ref": "trace-218",
  "observed_revision": 12,
  "observed_state": "CANCELLED",
  "effect_applied": false,
  "policy_ref": "refund-approval-policy@3"
}
```

Đây là dữ liệu minh họa cho trường hợp caller đã có quyền được đánh giá thao tác, và hệ thống đã xác định không có thay đổi bởi attempt này. Không gán `effect_applied=false` nếu kết quả commit thực sự chưa rõ.

Các reference và trạng thái này nằm trong log được phân quyền, không trở thành labels của metric. Không cần log số tiền, thông tin tài khoản nhận hoặc raw key để giải thích mọi invalid transition.

### 10.3. Đối chiếu đúng đơn vị

Khi điều tra một cửa sổ, chọn các attempt có cùng operation, phạm vi nguồn và quy tắc phân loại. Có thể thấy một command applied, nhiều replay và nhiều conflict của những command khác trên cùng đối tượng.

Không yêu cầu số audit event applied bằng tổng attempt. Không yêu cầu mọi trace sampled phải giải thích được toàn bộ counter. Khi đối chiếu sai lệch, kiểm tra đơn vị, ranh giới, retention, giao trùng và độ đầy đủ của từng nguồn trước.

## 11. Ca minh họa: conflict ở thao tác duyệt hoàn tiền tăng

### 11.1. Tín hiệu ban đầu

Giả sử `approve_refund` thường có khoảng 3% conflict ở điều kiện sử dụng tương ứng. Trong một cửa sổ năm phút mới, nguồn đo ghi nhận:

```text
Tổng attempt được đánh giá: 1000
Conflict: 160
    version_mismatch: 120
    invalid_transition: 25
    idempotency_payload_mismatch: 10
    operation_in_progress: 5

Conflict rate: 16%
```

Tín hiệu đủ để mở điều tra theo quy tắc của sản phẩm, nhưng chưa chỉ ra một nguyên nhân duy nhất. Không gộp 160 conflict thành 160 giao dịch hoàn tiền bị gian lận.

### 11.2. Trình tự điều tra

1. Kiểm tra nguồn metric, lần reset counter và thay đổi ranh giới instrumentation.
2. Xác nhận traffic và tập operation có thể so sánh với baseline.
3. Tách reason; ưu tiên version mismatch vì đây là phần lớn mức tăng trong ví dụ.
4. Tra log/trace được phép để tìm mẫu client, revision và command flow.
5. Đối chiếu audit hoặc command store để xác định thay đổi nào đã commit.
6. Với các reason khác, lập giả thuyết và kiểm chứng riêng thay vì dùng kết luận của nhóm lớn nhất.

Giả sử bằng chứng cho thấy một màn hình mới giữ revision từ lúc mở trang, trong khi tác vụ nền đã cập nhật trạng thái hiển thị của đối tượng. Điều này có thể giải thích một phần version mismatch; cần kiểm tra chính revision và hợp đồng của đối tượng, không chỉ dựa vào thời điểm phát hành.

Mười payload mismatch có thể là lỗi tái sử dụng key khác, chưa được giải thích bởi vấn đề revision. Hai nhóm có thể cùng tăng trong một cửa sổ nhưng cần hai cách sửa khác nhau.

### 11.3. Cách khắc phục và xác minh

Sửa client để xử lý conflict theo hợp đồng: tải lại dữ liệu cần thiết, cho người dùng xem thay đổi và yêu cầu quyết định mới nếu nội dung phê duyệt đã khác. Giữ kiểm tra revision và ràng buộc phê duyệt theo đúng đối tượng/nội dung.

Với idempotency, sửa cách định danh command và kiểm tra fingerprint. Không đổi key một cách máy móc mỗi khi nhận conflict, vì có thể tạo tác động mới thay cho việc nhận lại kết quả cũ.

Sau sửa, quan sát lại conflict count/rate, phân bố replay/error/unknown và kết quả audit. Tỷ lệ giảm chỉ có ý nghĩa tích cực khi kiểm soát và invariant vẫn được giữ, không phải vì request bị chuyển sang một lỗi khác hoặc metric ngừng ghi.

## 12. Bảo vệ telemetry và quản lý thay đổi

### 12.1. Không tin dữ liệu điều khiển metric từ caller

Operation, result và reason phải được chọn từ mã phía máy chủ. Header, path động, exception message và payload không được tự tạo tên series.

Nếu nhận trace reference từ bên ngoài, xử lý theo chính sách tracing và xác thực định dạng; reference đó không trở thành bằng chứng actor hoặc quyền. Các định danh dùng điều tra phải có nguồn và giới hạn rõ ràng.

### 12.2. Giới hạn dữ liệu và quyền truy cập

Metric có thể tiết lộ quy mô hoạt động hoặc thời điểm lỗi. Endpoint thu thập, dashboard và dữ liệu chi tiết cần có quyền truy cập phù hợp.

Không ghi raw token, cookie, thông tin nhận tiền hoặc toàn bộ request vào log khi conflict tăng. Nếu cần hạn chế log để bảo vệ khả năng vận hành, phải hiểu dữ liệu nào có thể được sampling và dữ liệu audit nào có hợp đồng lưu bắt buộc riêng.

Chính sách giảm tải telemetry không được biến thành cách âm thầm bỏ bằng chứng nghiệp vụ quan trọng. Đồng thời, không để mỗi lần bị chặn sinh một payload log quá lớn khiến chính luồng quan sát bị lạm dụng.

### 12.3. Giữ được khả năng so sánh qua phiên bản

Khi thêm reason, đổi tên operation hoặc đổi ranh giới đánh giá, cần cập nhật hợp đồng metric, dashboard và cảnh báo. Đánh dấu khoảng thay đổi để lịch sử trước/sau không bị diễn giải như một thay đổi hành vi thuần túy.

Giám sát nhóm `other_conflict`, label không hợp lệ và nguồn đo mất dữ liệu. Một hệ thống phân loại không còn bắt được mã lỗi mới có thể tạo biểu đồ conflict giảm giả.

## 13. Kiểm thử instrumentation và tình huống lạm dụng

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Command hợp lệ commit | Một kết quả applied tại ranh giới attempt; reason là none |
| Expected revision cũ | Conflict có reason đúng, không có thay đổi trái phép |
| Chuyển trạng thái bị cấm | Invalid transition được ghi, state machine không bị vượt qua |
| Cùng key và cùng payload đã hoàn tất | Replayed theo hợp đồng, không tạo tác động hoặc conflict giả |
| Cùng key nhưng đổi payload quan trọng | Payload mismatch được nhận diện và không áp dụng ý định mới |
| Command còn pending | Kết quả phản ánh đúng hợp đồng, không mặc định coi là conflict hoặc applied |
| Cạnh tranh nội bộ rồi retry thành công | Metric nội bộ tăng phù hợp; kết quả attempt không bị đếm thêm conflict |
| Hết retry hoặc gặp lock timeout | Không tự phân loại thành version mismatch của caller |
| Middleware và handler cùng tham gia | Không tăng counter kết quả hai lần cho một attempt |
| Rollback trước commit | Không ghi applied cho dữ liệu chưa được lưu |
| Commit xong nhưng mất phản hồi | Kết quả nguồn được phân biệt với lỗi truyền response; retry không áp dụng lại |
| Kết quả commit chưa rõ | Unknown theo hợp đồng, không đoán rollback hay applied |
| Caller sai quyền hoặc sai tenant | Bị chặn đúng; không lộ trạng thái và không bị nhập sai vào mẫu số chính |
| Caller gửi reason hoặc operation tùy ý | Không tạo label tùy ý hoặc làm sai phân loại |
| Nhiều ID/payload/exception message khác nhau | Số tổ hợp metric label vẫn theo tập đã kiểm soát |
| Không có traffic hoặc mất dữ liệu | Dashboard phân biệt tỷ lệ không xác định với 0% conflict |
| Tiến trình restart và nhiều instance | Truy vấn xử lý reset và tổng hợp đúng, không cộng trùng nguồn |
| Telemetry exporter lỗi | Không đổi kết quả nghiệp vụ và không thực thi lại command |
| Trace bị sampling hoặc log bị giới hạn | Không tuyên bố tập chi tiết là đầy đủ nếu thực tế không đầy đủ |
| Bỏ nhầm một kiểm tra nghiệp vụ | Kiểm chứng invariant phát hiện dù conflict counter có thể giảm |

Các kiểm thử phải kiểm tra cả dữ liệu/side effect và telemetry. Chỉ xác nhận hàm tăng metric đã được gọi không chứng minh transaction, quyền đối tượng hoặc idempotency hoạt động đúng.

Với cạnh tranh, dùng điểm đồng bộ để tạo thứ tự đọc/ghi cần kiểm chứng. Với retry, tách rõ lần thử nội bộ, attempt từ client và command duy nhất. Với cảnh báo, dùng dữ liệu mô phỏng có cả tử số, mẫu số, reset và khoảng thiếu dữ liệu; không chỉ thử một đường vượt ngưỡng.

## 14. Câu hỏi tự kiểm tra

**Conflict tăng có chứng minh hệ thống bị khai thác không?**

Không. Nó cho thấy nhiều attempt bị phân loại xung đột hơn trong tập đo. Cần kiểm tra reason, baseline, dữ liệu chi tiết và tác động thực tế.

**Có thể dùng số response 409 làm toàn bộ conflict metric không?**

Không mặc định như vậy. Mã vận chuyển có thể không trùng với phân loại và ranh giới kết quả nghiệp vụ. Có thể dùng nó như một góc nhìn bổ sung với định nghĩa riêng.

**Một attempt retry transaction hai lần rồi thành công có bao nhiêu conflict?**

Trong metric kết quả attempt của bài, kết quả là applied. Các sự kiện cạnh tranh nội bộ được đếm riêng theo định nghĩa của chúng, không tự biến thành nhiều attempt conflict.

**Vì sao phải xem cả conflict count và conflict rate?**

Vì tỷ lệ phụ thuộc mẫu số và cơ cấu traffic. Số lượng tuyệt đối, phân bố result và baseline của từng operation giúp tránh kết luận sai từ phần trăm đơn lẻ.

**Có nên thêm order ID và command ID vào labels để tìm nguồn gây lỗi không?**

Không cho counter tổng hợp này. Giữ các ID trong dữ liệu chi tiết được phân quyền và dùng liên kết điều tra phù hợp, tránh tạo số series không giới hạn.

**Metric không phát được thì có nên rollback hoặc chạy lại command không?**

Không vì riêng lỗi phát counter vận hành. Quyết định nghiệp vụ và hợp đồng audit bền vững có ranh giới riêng; không để lỗi telemetry gây tác động trùng.

**Conflict bằng không có chứng minh không có vi phạm invariant không?**

Không. Có thể không có traffic, mất dữ liệu, phân loại sai hoặc kiểm soát đã bị bỏ qua. Cần quan sát sức khỏe telemetry và xác minh kết quả nghiệp vụ từ nguồn phù hợp.


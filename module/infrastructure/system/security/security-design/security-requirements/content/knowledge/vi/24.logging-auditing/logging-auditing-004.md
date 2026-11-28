# Authorization failure

## 1. Từ chối quyền là một sự kiện cần giải thích được

Authorization failure là tình huống một hoạt động không được thực hiện vì không đáp ứng điều kiện phân quyền, hoặc quá trình xác định quyền không thể hoàn tất. Trong logging và audit, hai nguyên nhân này cần được phân loại rõ thay vì cùng ghi một dòng “access denied”.

Ví dụ, người đã đăng nhập gọi API đọc tài liệu của người khác. Hệ thống từ chối là hành vi đúng. Nhưng tổ chức còn cần biết:

- Actor nào yêu cầu hành động nào?
- Quyết định được thực hiện tại đâu và dựa trên phiên bản chính sách nào?
- Đó là thiếu quyền, sai tenant hay không lấy được quyết định?
- Hành động đã thực sự bị chặn chưa?
- Có chuỗi thử nhiều tài nguyên hoặc quyền cao hơn không?
- Sự kiện có tới nơi điều tra được và có đáng tin không?

OWASP liệt kê các thất bại kiểm soát truy cập trong nhóm sự kiện cần ghi nhận, đồng thời yêu cầu xác định logging theo rủi ro từ giai đoạn thiết kế. Điều đó không đồng nghĩa mọi lần từ chối đều là một cuộc tấn công. [OWASP Logging Cheat Sheet, Which events to log](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#which-events-to-log).

Mục tiêu của bài là chuyển nhu cầu quan sát các lần thất bại phân quyền thành yêu cầu cụ thể về nội dung, phạm vi, độ đầy đủ, thời gian, bảo vệ và kiểm chứng.

**Audit không thay thế enforcement.** Một bản ghi nói DENY không chứng minh dữ liệu đã được giữ kín nếu ứng dụng vẫn gửi nội dung hoặc thực hiện tác động sau đó.

## 2. Phân loại đúng trước khi ghi sự kiện

### 2.1. Tách danh tính, quyết định quyền và lỗi phụ thuộc

| Tình huống | Phân loại cần có | Điều không được suy ra |
| --- | --- | --- |
| Không xác minh được credential | Authentication failure hoặc trạng thái tương ứng | Không tự gán một principal đã được xác thực |
| Principal hợp lệ nhưng thiếu quyền hành động | Authorization denied | Không mặc định principal có ý đồ tấn công |
| Quan hệ tenant hoặc tài nguyên không phù hợp | Authorization denied theo chính sách | Không tiết lộ thông tin của tenant hoặc chủ sở hữu khác |
| Dịch vụ quyết định chính sách không sẵn sàng | Authorization evaluation unavailable hoặc indeterminate | Không khẳng định đã xác minh người dùng thiếu quyền |
| Phản hồi chính sách sai nguồn hoặc sai cấu trúc | Lỗi tính hợp lệ của quyết định | Không chuyển thành ALLOW |
| Dữ liệu đầu vào không hợp lệ | Validation failure | Không tự gọi là thất bại phân quyền |
| Tài nguyên không tìm thấy | Kết quả theo hợp đồng tài nguyên và chính sách che giấu | Không suy mọi 404 là authorization failure |
| Giới hạn tốc độ từ chối trước khi đánh giá quyền | Rate-limit event | Không giả rằng đã có quyết định phân quyền |

Trong phạm vi bài, nhóm sự kiện bao gồm các quyết định từ chối quyền và lỗi đánh giá quyền liên quan. Mỗi nhóm phải có loại sự kiện và mã lý do riêng.

Nếu chính sách là từ chối khi không thể xác minh quyền, có thể ghi đồng thời nguyên nhân UNAVAILABLE và kết quả thực thi NOT_EXECUTED. Không nên đổi nguyên nhân thành MISSING_PERMISSION chỉ vì phản hồi cho caller giống nhau.

### 2.2. Mã HTTP không phải nguồn sự thật duy nhất

403 thường biểu đạt việc máy chủ từ chối thực hiện request. Tuy nhiên, HTTP cho phép dùng 404 để không tiết lộ sự tồn tại của tài nguyên bị cấm. [RFC 9110, mục 15.5.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.4).

Do đó, bộ thu log chỉ đếm 403 có thể bỏ sót các quyết định từ chối được che bằng 404. Ngược lại, một proxy hoặc kiểm soát khác có thể trả 403 mà chưa có đánh giá quyền nghiệp vụ.

API có batch hoặc lỗi nằm trong nội dung phản hồi cũng cần ngữ nghĩa sự kiện riêng. Không suy kết quả phân quyền chỉ từ mã vận chuyển của cả request.

### 2.3. Reason nội bộ khác thông báo công khai

Audit được bảo vệ có thể cần mã như MISSING_ACTION_PERMISSION hoặc TENANT_SCOPE_MISMATCH.

Caller có thể chỉ nhận thông báo chung và mã theo dõi an toàn. Không đưa tên người sở hữu, danh sách role còn thiếu hoặc nội dung tài nguyên vào phản hồi ngoài quyền.

Ngay cả audit nội bộ cũng không được khẳng định tài nguyên tồn tại nếu hệ thống chưa kiểm tra điều đó. Cần phân biệt thông tin đã xác minh và giá trị mà caller chỉ mới yêu cầu.

## 3. Từ mô hình đe dọa đến yêu cầu logging

| Đe dọa hoặc sai sót | Hậu quả | Kết quả cần đặc tả |
| --- | --- | --- |
| Thử nhiều mã tài nguyên ngoài quyền | Dò hoặc khai thác kiểm soát đối tượng | Có actor, hành động, tham chiếu mục tiêu và liên kết chuỗi |
| Workload dùng quyền vượt nhiệm vụ | Lạm dụng credential hoặc cấu hình sai | Ghi đúng danh tính dịch vụ và ngữ cảnh ủy quyền |
| Chỉ log ở giao diện | Bỏ sót gọi trực tiếp API | Phát sinh từ điểm thực thi phía tin cậy |
| Caller giả actor hoặc request ID | Audit quy sai người hoặc bỏ trùng sai | Trường có thẩm quyền lấy từ ngữ cảnh đã xác minh |
| Lý do quá chi tiết | Lộ cấu trúc quyền và tài nguyên | Phân tách dữ liệu công khai và audit có quyền |
| Chuỗi đầu vào tạo dòng log giả | Làm sai bằng chứng hoặc đánh lừa người điều tra | Schema, encoding, giới hạn và hiển thị an toàn |
| Pipeline mất sự kiện | Không phát hiện chuỗi thử quyền | Độ bền, đối soát và cảnh báo khoảng trống |
| Retry tạo nhiều bản sao | Báo động giả hoặc sai số đếm | Event ID ổn định theo cùng sự kiện và xử lý lặp |
| Mọi DENY đều báo động mức cao | Quá tải cảnh báo | Phân tích theo ngữ cảnh, mức nhạy cảm và chuỗi |
| Tắt logger để giảm tải | Mất quan sát đúng lúc bị khai thác | Hành vi lỗi rõ, không âm thầm bỏ audit bắt buộc |
| Người vận hành sửa hoặc xóa log | Mất tính tin cậy điều tra | Quyền tách biệt và bảo vệ tính toàn vẹn |
| DENY được log nhưng hành động vẫn chạy | Cảm giác an toàn sai | Kiểm chứng cả sự kiện và kết quả nghiệp vụ |

Một yêu cầu logging phải nối được rủi ro với nơi phát sự kiện, nội dung cần có, owner và bằng chứng. Tên logger hoặc một dòng cấu hình log level chưa đủ.

## 4. Phạm vi và đơn vị sự kiện

### 4.1. Ghi tại điểm có thẩm quyền thực thi

Điểm kiểm tra có thể ở gateway, ứng dụng, dịch vụ tài nguyên, worker hoặc consumer thông điệp. Cần inventory những nơi thực sự quyết định hành động được thực hiện hay không.

Frontend có thể ghi thông tin hỗ trợ trải nghiệm, nhưng việc nút bị ẩn không phải bằng chứng từ chối một lời gọi trực tiếp.

Dịch vụ ra quyết định và điểm thực thi có thể tách nhau. Khi đó cần biết ai tạo quyết định, ai áp dụng, và quan hệ giữa hai bản ghi.

### 4.2. Một request có thể có nhiều quyết định

Một request batch có thể gồm đối tượng được phép và bị từ chối. Cần mô tả kết quả ở mức phần tử hoặc nhóm có cùng ngữ nghĩa, không dùng một dòng “request thành công” để che phần thất bại.

Nếu chính sách cấm cả batch khi một phần bị từ chối, audit phải thể hiện quy tắc đó và kết quả thực thi.

Với stream hoặc kết nối dài, một quyết định từ chối ở thông điệp sau có thể khác quyết định cho phép khi bắt tay. Inventory cần bao phủ điểm tái đánh giá thực tế.

### 4.3. Không đếm mọi lời gọi hàm thành một lần thử riêng

Một quyết định có thể đi qua nhiều hàm hoặc đọc cache nhiều lần. Nếu tất cả phát cùng loại audit không có phân biệt, số liệu thử quyền sẽ bị thổi phồng.

Cần định nghĩa:

- Request hoặc interaction ở mức nghiệp vụ.
- Một lần đánh giá quyền logic.
- Một lần thực thi quyết định.
- Bản sao vận chuyển hoặc bản ghi chẩn đoán.

Cache hit vẫn có thể là nơi tạo quyết định từ chối cho request mới. Không bỏ sự kiện chỉ vì không gọi dịch vụ chính sách ở lần này.

## 5. Nội dung sự kiện phải đủ để giải trình

### 5.1. Schema theo câu hỏi điều tra

| Nhóm trường | Nội dung cần xác định | Điều cần tránh |
| --- | --- | --- |
| Định danh sự kiện | Event ID, loại và phiên bản schema | Caller tự quyết định ID dùng để bỏ trùng |
| Thời gian | Mốc quyết định, mốc ghi và mốc tiếp nhận | Dùng một timestamp cho mọi giai đoạn |
| Nguồn phát | Dịch vụ, instance và điểm thực thi | Chỉ biết tên file log |
| Actor | Loại danh tính và tham chiếu đã xác minh | Lấy username từ request như danh tính thật |
| Ủy quyền | Người khởi tạo, workload và principal hiệu lực nếu có | Gộp tất cả thành một user mơ hồ |
| Tenant | Phạm vi đáng tin cậy của actor và quyết định | Dùng tenant do caller tự khai làm bằng chứng quyền |
| Hành động | Tên hành động nghiệp vụ đã chuẩn hóa | Chỉ HTTP method hoặc tên màn hình |
| Tài nguyên | Loại và tham chiếu cần thiết | Nội dung tài nguyên hoặc thông tin chủ sở hữu ngoài quyền |
| Quyết định | DENY, INDETERMINATE hoặc trạng thái đã định nghĩa | Gọi mọi lỗi là thiếu permission |
| Lý do | Mã có tập giá trị được quản lý | Ghép câu chứa secret hoặc dữ liệu tùy ý |
| Chính sách | Phiên bản và nguồn quyết định | Chỉ ghi tên role không biết lúc nào có hiệu lực |
| Thực thi | Hành động có bị chặn và kết quả phản hồi | Đồng nhất quyết định với tác động thực tế |
| Liên kết | Interaction, decision và trace tham chiếu | Dùng một ID cho mọi mục đích |
| Ngữ cảnh phân tích | Phân loại actor, mức nhạy cảm và độ tin cậy phù hợp | Thu thập mọi header vì có thể cần |

Không phải mọi trường đều có giá trị trong mọi tình huống. Schema cần quy định trường bắt buộc, điều kiện xuất hiện, trạng thái không biết và lý do thiếu.

Không điền dữ liệu giả như actor=admin chỉ để vượt kiểm tra schema.

### 5.2. Actor khởi tạo và principal hiệu lực

Một người có thể yêu cầu tác vụ qua workload, hoặc một dịch vụ thực hiện thay mặt principal khác.

Audit cần giữ được quan hệ này khi nó tồn tại. Nếu chỉ ghi danh tính dịch vụ, có thể mất khả năng giải trình ai khởi tạo. Nếu chỉ ghi người dùng, có thể bỏ mất workload bị chiếm.

Chỉ ghi thông tin ủy quyền đã được hệ thống xác minh. Header tự nhận “on behalf of” không phải bằng chứng.

### 5.3. Tenant và mục tiêu chưa được xác minh

Caller có thể yêu cầu một mã tài nguyên không tồn tại hoặc không thuộc tenant của họ.

Có thể ghi requested_resource_ref được xử lý an toàn để điều tra chuỗi thử, nhưng không tự thêm owner_tenant nếu hệ thống chưa có căn cứ hoặc không cần biết.

Nếu điểm thực thi từ chối trước bước đọc tài nguyên, dùng trạng thái như NOT_EVALUATED cho sự tồn tại. Không suy ra EXISTS từ việc có mã ID trong URL.

Thông tin chi tiết liên tenant, nếu thật sự cần cho điều tra, phải có quyền đọc và mục đích riêng. Nó không nên xuất hiện trong mọi bản sao dashboard.

### 5.4. Mã lý do và phiên bản

Ví dụ một tập mã nội bộ:

~~~text
MISSING_ACTION_PERMISSION
RESOURCE_SCOPE_MISMATCH
TENANT_SCOPE_MISMATCH
POLICY_EXPLICIT_DENY
AUTHORIZATION_DEPENDENCY_UNAVAILABLE
POLICY_RESPONSE_INVALID
~~~

Cần quy tắc ánh xạ nguyên nhân sang mã, cách thay phiên bản và cách xử lý mã chưa biết.

Lý do là kết quả tại thời điểm đánh giá, không phải mô tả vĩnh viễn về người dùng. Một người thiếu quyền hôm nay có thể được cấp quyền hợp lệ sau đó.

## 6. Ví dụ sự kiện có cấu trúc

Ví dụ dưới đây dùng dữ liệu tổng hợp. Điểm thực thi đã xác minh principal nhưng từ chối vì thiếu quyền hành động trước khi đọc đối tượng cụ thể.

~~~json
{
  "schema_version": "1",
  "event_type": "authorization.denied",
  "event_id": "evt-demo-0001",
  "occurred_at": "2026-11-27T02:00:00.125Z",
  "recorded_at": "2026-11-27T02:00:00.126Z",
  "producer": {
    "service": "document-service-demo",
    "instance": "instance-demo-01",
    "enforcement_point": "document-read-gate"
  },
  "actor": {
    "type": "human",
    "subject_ref": "subject-demo-01",
    "authentication_state": "VERIFIED"
  },
  "tenant_ref": "tenant-demo-a",
  "action": "document.read",
  "resource": {
    "type": "document",
    "requested_ref": "resource-demo-09",
    "existence": "NOT_EVALUATED"
  },
  "decision": {
    "outcome": "DENY",
    "reason_code": "MISSING_ACTION_PERMISSION",
    "policy_version": "policy-demo-v7",
    "source": "LOCAL_EVALUATION"
  },
  "enforcement": {
    "effect": "NOT_EXECUTED",
    "public_response_status": 404
  },
  "correlation": {
    "interaction_id": "interaction-demo-01",
    "decision_id": "decision-demo-01",
    "trace_ref": "trace-demo-01"
  }
}
~~~

Mã 404 là lựa chọn phản hồi minh họa theo chính sách che giấu tài nguyên, không phải yêu cầu mọi hệ thống đều dùng 404.

Các ID có tiền tố demo không mô tả thuật toán sinh ID production. Hệ thống thực tế phải đáp ứng phạm vi duy nhất, kích thước, tính hợp lệ và khả năng liên kết đã chọn.

### 6.1. Những gì ví dụ không chứa

Không có Authorization header, cookie, mật khẩu, nguyên JWT, request body hoặc nội dung tài liệu.

Mã tham chiếu giúp nối sự kiện nhưng vẫn có thể liên quan đến một người. Nó không tự biến audit thành dữ liệu công khai hoặc ẩn danh.

Nếu cần phân tích địa chỉ nguồn, phải xác định nguồn đáng tin cậy, quyền truy cập và thời gian lưu. Không mặc định mọi X-Forwarded-For do caller gửi là địa chỉ thật.

### 6.2. Các biến thể cần được đặc tả

Nếu lỗi ở dịch vụ chính sách, loại sự kiện và reason phải phản ánh việc không thể đánh giá. Không sao chép nguyên ví dụ rồi để outcome DENY che nguyên nhân hạ tầng.

Nếu chính sách từ cache, cần nguồn và phiên bản liên quan. Nếu có nhiều điểm thực thi, cần quan hệ giữa các quyết định thay vì ghi các sự kiện trông giống nhau mà không phân biệt.

Với batch, có thể cần nhóm kết quả có số lượng và tham chiếu chi tiết được bảo vệ. Không tạo một payload không giới hạn chứa toàn bộ danh sách tài nguyên.

## 7. Đầu vào không đáng tin và giới hạn dữ liệu

### 7.1. Structured logging vẫn cần xử lý an toàn

Dữ liệu do caller kiểm soát có thể chứa ký tự xuống dòng, dấu phân cách, chuỗi giống JSON hoặc nội dung giống một sự kiện hệ thống.

Cần serialize theo schema bằng cơ chế phù hợp, không nối chuỗi thành dòng log tự do. Bộ thu và màn hình điều tra cũng phải xử lý nội dung như dữ liệu, không thực thi hoặc diễn giải như định dạng điều khiển.

Một chuỗi đã được escape khi ghi chưa chắc an toàn nếu công cụ xem log giải mã rồi chèn trực tiếp vào HTML.

### 7.2. Giới hạn chiều dài theo trường

Cần độ dài, kiểu và quy tắc cho từng trường, cùng giới hạn toàn sự kiện.

Không cắt nguyên chuỗi JSON sau serialize để khớp kích thước, vì có thể làm hỏng cấu trúc hoặc mất trường bắt buộc.

Cũng không cắt định danh quan trọng một cách tạo va chạm mà vẫn dùng như ID chính xác. Có thể dùng tham chiếu an toàn, trạng thái giá trị quá dài hoặc đường xử lý riêng được bảo vệ.

Giới hạn byte và giới hạn ký tự cần được phân biệt khi thiết kế dung lượng. Tiếng Việt hoặc dữ liệu Unicode có thể chiếm nhiều byte hơn số ký tự nhìn thấy.

### 7.3. Không tăng quyền chỉ để làm giàu log

Một request không có quyền đọc tài nguyên không nên khiến logger đọc toàn bộ tài nguyên để ghi lý do chi tiết.

Logging phải dùng ngữ cảnh được phép và phần metadata cần thiết. Làm giàu log bằng dịch vụ khác cũng cần kiểm soát quyền, mục đích và giới hạn lỗi.

Audit không được trở thành đường truy cập thay thế cho người không có quyền ở API chính.

### 7.4. Dữ liệu nhận diện và fingerprint

Băm một ID có miền giá trị nhỏ không tự ngăn dò hoặc liên kết. Nếu dùng cơ chế tham chiếu có khóa, cần thiết kế quyền dùng khóa, phạm vi, phiên bản và khả năng điều tra qua thời gian.

Không chọn một kỹ thuật chỉ để gọi log là “đã ẩn danh”. Cần đánh giá dữ liệu còn lại, cách kết hợp và ai được đọc.

## 8. Liên kết sự kiện, retry và thứ tự

### 8.1. Event ID khác interaction ID

Một interaction có thể tạo nhiều quyết định. Mỗi sự kiện logic cần định danh riêng; các bản sao do gửi lại giữ cùng event ID theo hợp đồng.

Request ID do caller cung cấp có thể hữu ích như dữ liệu liên kết đã kiểm tra, nhưng không nên làm khóa duy nhất để loại sự kiện. Kẻ tấn công có thể cố tình tái sử dụng nó.

Hai lần thử quyền độc lập không được bị gộp thành một chỉ vì cùng URL hoặc cùng request ID ngoài quyền kiểm soát.

### 8.2. Bỏ trùng không được làm mất ý nghĩa

Pipeline có thể vận chuyển lặp. Kho phân tích cần quy tắc bỏ trùng đúng phạm vi producer và event ID.

Không cần hứa “exactly once” nếu kiến trúc chỉ có retry và bỏ trùng trong một cửa sổ. Phải nêu cửa sổ, phần còn lại và cách báo cáo.

Không đếm bản sao vận chuyển như nhiều hành vi của actor. Đồng thời, không bỏ mất các lần thử riêng biệt mà một actor lặp lại.

### 8.3. Nhiều mốc thời gian

occurred_at là thời điểm quyết định tại producer; recorded_at là lúc ghi theo định nghĩa của producer; ingested_at nên do phía tiếp nhận xác lập.

Các mốc khác nhau giúp nhận biết event đến muộn và pipeline tồn đọng. Không cho producer tự khai timestamp tiếp nhận của kho trung tâm.

Thứ tự theo timestamp không luôn là thứ tự nhân quả. Muốn biết lần DENY có xảy ra trước hay sau một thay đổi quyền, cần thêm phiên bản chính sách, nguồn và giới hạn sai lệch thời gian.

## 9. Pipeline, độ bền và hành vi khi logging lỗi

### 9.1. Xác định từng mức thành công

~~~mermaid
flowchart LR
    A["Điểm thực thi từ chối hành động"] --> B["Tạo sự kiện theo schema"]
    B --> C["Ghi bền hoặc đệm bền theo hợp đồng"]
    C --> D["Vận chuyển có kiểm soát"]
    D --> E["Kho audit có thể truy vấn"]
    E --> F["Phân tích và cảnh báo"]
    G["Theo dõi sức khỏe và đối soát"] --> C
    G --> D
    G --> E
~~~

“Tạo object log”, “gọi logger”, “đã vào queue”, “ghi bền”, “tới kho” và “truy vấn được” là những mốc khác nhau.

Cần nói rõ mốc nào API hoặc thư viện xác nhận, mô hình sự cố nào được chịu và ai giám sát khoảng cách giữa các mốc.

Không mặc định ghi stdout là đã ghi bền. Kết quả phụ thuộc runtime, collector, bộ đệm và hợp đồng vận hành.

### 9.2. Logging lỗi không được biến DENY thành ALLOW

Nếu ứng dụng không ghi được sự kiện từ chối, hành động bị cấm vẫn không được thực hiện. Không trả thành công hoặc gửi dữ liệu như một cách né lỗi logger.

Cũng không được chặn vô hạn trên đường ghi log rồi làm tài nguyên ứng dụng cạn kiệt. Cần timeout, hàng đợi có giới hạn và chính sách lỗi rõ.

Đối với một thao tác vốn bị từ chối, logging không có quyền tự sửa trạng thái nghiệp vụ hoặc thử lại bằng danh tính mạnh hơn.

### 9.3. Bộ đệm bền có giới hạn

Nếu kho trung tâm lỗi, có thể tiếp tục ghi vào vùng đệm được bảo vệ theo thiết kế.

Cần xác định:

- Độ bền qua restart và loại lỗi lưu trữ được cam kết.
- Dung lượng, kích thước event và tốc độ phát sinh.
- Chính sách quyền đọc, mã hóa và retention của bộ đệm.
- Retry, chống gửi trùng và kiểm tra thứ tự cần thiết.
- Cảnh báo khi tồn đọng hoặc gần đầy.
- Hành vi khi không còn khả năng ghi.

Bộ đệm RAM không chứng minh sự kiện còn sau restart. Đĩa cục bộ cũng không tự chịu được mất toàn bộ node nếu mô hình sự cố yêu cầu điều đó.

### 9.4. Không hứa độ đầy đủ vô hạn

Muốn ghi mọi quyết định trong một phạm vi tải, phải định nghĩa phạm vi đó.

Ví dụ, nếu cụm cần chịu tốc độ 1.000 event mỗi giây trong 900 giây khi kho trung tâm gián đoạn:

~~~text
Số event tối thiểu cần hấp thụ = 1.000 × 900 = 900.000

Dung lượng payload tối thiểu =
    số event × kích thước event tối đa

Dung lượng thực còn phải tính:
    metadata, journal, chỉ mục, dự phòng và mô hình sao chép
~~~

Các con số chỉ là giả định học tập, không phải cấu hình chung cho mọi hệ thống.

Nếu vượt mô hình, cần giảm tải hoặc kiểm soát tiếp nhận theo kế hoạch, phát cảnh báo và báo đúng khoảng trống bằng chứng. Không âm thầm bỏ log mà vẫn công bố độ đầy đủ 100%.

Giới hạn tốc độ trước bước đánh giá quyền có loại sự kiện riêng. Không được đổi tên các quyết định DENY đã có thành “rate limit” chỉ để tránh nghĩa vụ ghi nhận.

### 9.5. Sampling và gộp sự kiện

Sampling có thể phù hợp với một số dữ liệu quan sát, nhưng không tự phù hợp với audit bắt buộc.

Nếu yêu cầu phải có từng quyết định từ chối trong phạm vi, dashboard có thể hiển thị tổng hợp nhưng bản gốc cần được xử lý theo hợp đồng đó.

Một bản gộp phải có ngữ nghĩa: phạm vi, cửa sổ, số lượng và giới hạn. Nó không thay thế được chi tiết từng lần nếu yêu cầu điều tra cần chi tiết đó.

Cơ chế bảo vệ khỏi log flooding không được trở thành nút tắt toàn bộ logging khi có nhiều hành vi đáng ngờ.

### 9.6. Đối soát và phát hiện khoảng trống

Có thể đối chiếu số quyết định tại điểm thực thi, số event ghi bền, số đã tiếp nhận và số sau bỏ trùng.

Cần cùng định nghĩa đơn vị và khoảng thời gian. Nếu một bên đếm request còn bên khác đếm phần tử batch, chênh lệch không tự là mất log.

Counter, sequence hoặc watermark có thể giúp phát hiện bất thường. Tuy nhiên, nếu cả counter và log đều do cùng tiến trình đã bị chiếm kiểm soát tạo ra, sự phù hợp giữa chúng không chứng minh tuyệt đối tính đầy đủ.

Nguồn kiểm chứng độc lập và mô hình tin cậy phải được nêu khi cần mức bảo đảm cao hơn.

## 10. Phát hiện hành vi cần dựa trên ngữ cảnh

### 10.1. Một DENY không đồng nghĩa một sự cố

Người dùng có thể mở liên kết cũ sau khi đổi vai trò. Giao diện có thể còn nút cũ trong lúc chính sách đã thay đổi. Workload cũng có thể bị cấu hình sai.

Các tình huống đó vẫn cần ghi nhận và xử lý, nhưng không nên mặc định mọi event đều là mức nguy cấp cao nhất.

Nên phân biệt mức sự kiện, mức nhạy cảm của hành động, độ tin cậy của dữ liệu và mức cảnh báo sau tương quan.

### 10.2. Những mẫu có thể cần phát hiện

| Mẫu | Giả thuyết cần xem xét | Dữ liệu phụ thuộc |
| --- | --- | --- |
| Nhiều tham chiếu mục tiêu trong thời gian ngắn | Dò tài nguyên hoặc lỗi client | Principal, action, tenant và tham chiếu an toàn |
| Gọi hành động quản trị ngoài nhiệm vụ | Thử tăng quyền hoặc nhầm cấu hình | Loại actor và phân loại hành động |
| Nhiều lỗi tenant | Tích hợp sai hoặc truy cập chéo | Ngữ cảnh tenant đáng tin cậy |
| Từ chối tăng mạnh sau deploy | Lỗi chính sách hoặc thay route | Phiên bản ứng dụng và chính sách |
| Nhiều workload cùng lỗi đánh giá | Sự cố phụ thuộc chung | Mã lỗi hạ tầng và điểm thực thi |
| Chuỗi từ chối rồi cho phép đáng ngờ | Thay quyền, bypass hoặc thay đổi hợp lệ | Event liên quan và lịch sử thay chính sách |

Bảng này là các giả thuyết phân tích, không phải kết luận tự động về actor.

### 10.3. Ví dụ quy tắc có thể đo

Giả sử chọn quy tắc minh họa:

~~~text
Trong cửa sổ trượt 60 giây:
    cùng principal đáng tin cậy
    cùng tenant và nhóm hành động
    có ít nhất 20 quyết định authorization.denied riêng biệt
    nhắm ít nhất 10 tham chiếu mục tiêu khác nhau

=> tạo cảnh báo trong tối đa 60 giây
   từ lúc kho phân tích có đủ sự kiện hợp lệ đáp ứng điều kiện
~~~

Phải loại bản sao vận chuyển trước khi đếm. Tham chiếu mục tiêu khác nhau không chứng minh những tài nguyên đó thực sự tồn tại.

Cơ chế tham chiếu cần giữ tính liên kết đủ cho cửa sổ phân tích mà vẫn đáp ứng giới hạn quyền riêng tư.

Thời gian nhận cảnh báo không giống thời gian xảy ra hành vi. Nếu pipeline chậm, cần tính cả độ trễ vận chuyển khi đánh giá khả năng phát hiện đầu cuối.

### 10.4. Tránh phản ứng tự động gây gián đoạn sai

Một quy tắc cảnh báo không tự cho phép khóa mọi tài khoản hoặc chặn cả tenant.

Biện pháp phản ứng cần chính sách riêng, độ tin cậy phù hợp và cách xử lý nhầm. Không dùng IP làm định danh chắc chắn cho một người nếu có proxy, NAT hoặc nguồn không được xác minh.

Nếu muốn phát hiện chuỗi DENY rồi ALLOW, phải có nguồn sự kiện cho phép và thay đổi quyền tương ứng. Không hứa một detector khi dữ liệu đầu vào cần thiết chưa được thu thập.

Cần kiểm thử cả mẫu tấn công tổng hợp và hoạt động bình thường có nhiều lần từ chối, chẳng hạn sau một thay đổi vai trò hợp lệ.

## 11. Bảo vệ audit và giới hạn việc sử dụng

### 11.1. Phân quyền đọc khác quyền ghi

Ứng dụng có thể cần gửi event nhưng không cần quyền sửa hoặc xóa lịch sử trong kho audit.

Người hỗ trợ một tenant không tự được xem tất cả actor và tài nguyên của tenant khác. Người vận hành collector cũng không mặc nhiên có quyền export toàn bộ log.

Cần phạm vi quyền, mục đích sử dụng, thời hạn quyền và audit việc truy cập hoặc thay cấu hình quan trọng.

### 11.2. Tính toàn vẹn có giới hạn cần hiểu đúng

Kho hạn chế sửa, chuỗi kiểm chứng, chữ ký hoặc các cơ chế tương tự có thể giúp phát hiện một số thay đổi.

Không coi một checksum thông thường là bằng chứng chống người có quyền sửa cả nội dung lẫn checksum. Cũng không coi một event có chữ ký là bằng chứng producer đã khai đúng sự thật nếu producer bị chiếm.

Cần phân biệt phát hiện sửa sau ghi, xác minh nguồn gửi và chứng minh độ đầy đủ. Ba mục tiêu đó không tự được đáp ứng bởi cùng một cơ chế.

### 11.3. Log là dữ liệu có vòng đời

Tham chiếu actor, IP, lịch sử truy cập và mục tiêu có thể là thông tin nhạy cảm trong ngữ cảnh sử dụng.

Cần mục đích, owner, hạn lưu, quy tắc export và xử lý bản sao. Bộ đệm, bản backup và tệp phân tích tải xuống cũng nằm trong phạm vi cần quản lý.

Không giữ log mãi vì có thể cần điều tra trong tương lai. Ngược lại, không xóa sớm khi có yêu cầu lưu giữ hoặc bảo toàn có hiệu lực.

Nếu ghi lại việc truy cập kho audit, cần kiến trúc tránh vòng lặp logging không giới hạn. Cơ chế kiểm toán hoạt động quản trị phải có phạm vi và đường ghi được kiểm soát.

## 12. Bộ yêu cầu đo được cho một hệ thống minh họa

### 12.1. Phạm vi và giả định

Giả sử nền tảng nhiều tenant có API tài liệu, worker xử lý lệnh và cổng quản trị. Inventory xác định những điểm thực thi phân quyền thuộc phạm vi bắt buộc.

Ví dụ chọn:

- Mỗi quyết định từ chối logic có event tương ứng, không sampling audit bắt buộc.
- Khi pipeline khỏe, event truy vấn được tại kho audit trong tối đa 30 giây từ mốc quyết định.
- Thiết kế chịu kho trung tâm gián đoạn 15 phút ở tổng tải tối đa 1.000 event mỗi giây theo mô hình phân bổ đã xác định.
- Kích thước event tối đa là 2 KiB; trường cần thiết phải nằm trong giới hạn bằng schema và quy tắc xử lý.
- Quy tắc mẫu ở mục 10 phát cảnh báo trong tối đa 60 giây từ khi có đủ event hợp lệ tại kho phân tích.

Đây là giả định kỹ thuật để minh họa, không phải ngưỡng bắt buộc chung. Mô hình sự cố, tải từng node, dự phòng, độ bền và giới hạn sai lệch thời gian cần được xác định trong đặc tả triển khai.

### 12.2. Ma trận yêu cầu và tiêu chí chấp nhận

| ID | Yêu cầu bảo mật | Tiêu chí chấp nhận |
| --- | --- | --- |
| AF-01 | Hành động bị từ chối không được thực hiện dù logging lỗi | Không trả nội dung ngoài quyền, không ghi thay đổi nghiệp vụ hoặc phát lệnh thực hiện tác động bị cấm trong ca DENY và ca logger lỗi |
| AF-02 | Tách authentication failure, authorization denied, lỗi đánh giá và lỗi nghiệp vụ | Event type và reason phản ánh nguyên nhân; UNAVAILABLE không bị gán thành thiếu permission đã xác minh |
| AF-03 | Mỗi quyết định từ chối logic tại điểm trong inventory có event hợp lệ theo phạm vi tải và sự cố đã cam kết | Đối soát decision ID trong bộ thử; không bỏ event theo actor “đáng tin” hoặc do cache hit |
| AF-04 | Event có schema, trường bắt buộc và nguồn dữ liệu đáng tin cậy | Kiểm tra actor, tenant, action, reason, policy, điểm thực thi và trạng thái chưa biết; input không tự ghi đè trường có thẩm quyền |
| AF-05 | Không đưa credential, toàn bộ hồ sơ hoặc nội dung tài nguyên vào event phổ thông | Ca có secret trong header, query và body không làm dữ liệu đó đi vào log; trường tự do được xử lý theo schema |
| AF-06 | Retry vận chuyển không làm tăng số quyết định hoặc mất lần thử riêng biệt | Cùng event ID được xử lý theo hợp đồng bỏ trùng; các quyết định khác nhau không bị gộp bằng request ID của caller |
| AF-07 | Khi pipeline khỏe, event truy vấn được trong tối đa 30 giây từ quyết định | Đo từ occurred_at đáng tin cậy tới khả năng truy vấn tại kho, có tính giới hạn đồng hồ; không chỉ đo queue ACK |
| AF-08 | Trong gián đoạn 15 phút và tải đã định, không mất event bắt buộc theo mô hình độ bền đã chọn | Restart thành phần nằm trong mô hình không mất dữ liệu; backlog được chuyển tiếp và đối soát sau phục hồi |
| AF-09 | Quy tắc mẫu đếm quyết định riêng biệt và cảnh báo trong tối đa 60 giây từ khi đủ dữ liệu hợp lệ | Bản sao không tạo đủ ngưỡng giả; cảnh báo có phạm vi, mốc và liên kết bằng chứng phù hợp |
| AF-10 | Audit chống truy cập và thay đổi ngoài quyền | Writer không sửa lịch sử theo quyền được cấp; người đọc bị giới hạn tenant và mục đích; thay cấu hình quan trọng có dấu vết |
| AF-11 | Event, bộ đệm, export và backup có owner, mục đích và retention được xác định | Không có bản sao trong inventory thiếu quy tắc; kiểm tra hết hạn và bảo toàn không làm sai nghĩa vụ áp dụng |
| AF-12 | Mất khả năng ghi, backlog vượt giới hạn hoặc phần chưa đối soát phải được quan sát | Có chỉ báo riêng và đường chuyển xử lý; không công bố đầy đủ 100% khi đã có khoảng trống chưa giải thích |

AF-03 và AF-08 chỉ được xác nhận trong mô hình đã nêu. Khi vượt tải hoặc sự cố nằm ngoài phạm vi bảo đảm, hệ thống vẫn phải giữ AF-01 và báo đúng phần thiếu; không tự coi đó là kết quả audit đầy đủ.

AF-07 đo pipeline. AF-09 đo xử lý quy tắc sau khi đủ dữ liệu. Muốn đưa ra cam kết phát hiện đầu cuối phải ghép cả các mốc, thay vì chỉ công bố thời gian chạy detector.

### 12.3. Ví dụ đặc tả có truy vết

~~~yaml
requirement_id: AF-03
risk_id: TH-AUDIT-02
risk: Chuỗi thử quyền không được điều tra vì thiếu hoặc gộp sai sự kiện
scope:
  - Điểm thực thi API tài liệu trong inventory
  - Worker xử lý lệnh có quyết định quyền
  - Điểm kiểm soát hành động quản trị trong phạm vi
trigger: Một quyết định từ chối quyền logic được tạo tại điểm thực thi
required_behavior:
  - Ghi một sự kiện logic với event_id và decision_id
  - Giữ liên kết interaction phù hợp
  - Phản ánh actor, tenant và mục tiêu theo nguồn tin cậy
  - Không khẳng định thông tin chưa được đánh giá
  - Không bỏ qua vì actor nội bộ hoặc quyết định từ cache
delivery_behavior:
  - Cho phép retry vận chuyển theo hợp đồng
  - Bỏ trùng không làm mất quyết định độc lập
failure_behavior:
  - Không đổi DENY thành ALLOW khi logging lỗi
  - Đệm bền trong phạm vi mô hình sự cố
  - Báo lỗi hoặc khoảng trống khi không còn bảo đảm ghi nhận
verification:
  - Đối soát tập decision_id dự kiến với event hợp lệ
  - Thử nhiều lớp actor, điểm thực thi và đường cache
  - Gửi lặp event và lặp request độc lập
evidence:
  - Inventory và schema có phiên bản
  - Kết quả kiểm chứng từng điểm
  - Mốc ghi bền, tiếp nhận và truy vấn
owner: Nhóm ứng dụng, nhóm nền tảng logging và nhóm giám sát bảo mật
~~~

Đây là đặc tả minh họa, không phải cấu hình triển khai. Mỗi điểm thực thi cần được gắn với thành phần cụ thể và người chịu trách nhiệm.

## 13. Đo độ đầy đủ mà không bị số lượng đánh lừa

### 13.1. Đối soát theo tập quyết định

Một cách đo trong bộ kiểm chứng có tập quyết định biết trước:

~~~text
D = tập decision_id phải có audit trong phạm vi thử
V = các decision_id trong D có ít nhất một event hợp lệ, đúng ngữ cảnh

coverage = |V| / |D|
~~~

Một nghìn bản sao của cùng event không bù được một quyết định khác bị thiếu.

Event chỉ được tính hợp lệ khi đúng actor, tenant, action, reason và quan hệ với quyết định theo yêu cầu. Có một dòng log sai ngữ cảnh không có nghĩa quyết định đã được giải trình.

Nếu D rỗng, cần quy tắc báo “không có quyết định để đo” thay vì tự đưa ra bằng chứng đã phủ mọi điểm.

### 13.2. Số liệu production có giới hạn

Trong vận hành, không phải lúc nào cũng có tập D độc lập hoàn hảo. Có thể dùng counter, sequence, watermark, trạng thái buffer và đối soát theo nguồn.

Phải phân biệt số liệu kiểm chứng, ước lượng vận hành và phần chưa quan sát được. Một dashboard không nhận event có thể do không có hành vi, do pipeline lỗi hoặc do điểm phát chưa được triển khai.

Không diễn giải “không có log từ chối” thành “không có truy cập bị từ chối” khi chưa kiểm tra sức khỏe và mức phủ.

### 13.3. Event không chứng minh không có bypass

Một đường code quên kiểm tra quyền có thể không tạo DENY nào. Log từ các đường kiểm tra đúng không tự phát hiện mọi đường bị bỏ sót.

Cần kiểm chứng access control và inventory điểm thực thi bên cạnh yêu cầu logging. Hai loại kiểm chứng bổ sung cho nhau.

Tương tự, nếu audit ghi NOT_EXECUTED nhưng job vẫn nhận lệnh, event không làm trạng thái nghiệp vụ trở nên an toàn. Phải kiểm tra tác động thực tế.

## 14. Thiết kế kiểm chứng theo rủi ro

### 14.1. Kiểm thử phân loại và enforcement

Dùng dữ liệu tổng hợp, tenant thử và actor phù hợp phạm vi.

Các ca cần có:

- Principal hợp lệ nhưng thiếu quyền hành động.
- Có quyền hành động nhưng sai phạm vi tài nguyên.
- Sai tenant.
- Credential không hợp lệ hoặc hết hạn.
- Dịch vụ chính sách không sẵn sàng.
- Phản hồi chính sách không hợp lệ.
- Tài nguyên chưa được đánh giá tồn tại.
- Đường cho phép hợp lệ để đối chiếu.

Với từng ca, xác minh nội dung phản hồi, trạng thái nghiệp vụ và event. Ca từ chối cần chứng minh dữ liệu không bị trả hoặc tác động không xảy ra, không chỉ thấy chữ DENY trong log.

### 14.2. Kiểm thử ngữ cảnh và input không đáng tin

Thử giả actor, tenant, event ID, request ID và header nguồn. Trường có thẩm quyền phải giữ đúng giá trị do hệ thống xác lập.

Đưa ký tự xuống dòng, dấu phân cách, chuỗi giống JSON và dữ liệu Unicode vào trường do caller kiểm soát. Kết quả không tạo thêm event giả, không phá schema và không thực thi nội dung trong công cụ xem.

Thử input quá dài. Trường bắt buộc phải còn đúng nghĩa; không cắt định danh rồi coi nó là ID chính xác.

### 14.3. Kiểm thử dữ liệu nhạy cảm

Đặt secret tổng hợp dễ nhận biết trong những vị trí có nguy cơ bị ghi như header, query và body.

Kiểm tra cả log ứng dụng, collector, dead-letter queue, báo lỗi serialize và export. Bộ lọc ở kho cuối không giúp bảo vệ bản sao đã bị ghi trước đó.

Nếu event lỗi schema được đưa vào vùng cách ly, cần đảm bảo nó không trở thành nơi lưu nguyên payload chứa secret với quyền rộng.

Không dùng dữ liệu hoặc credential thật để tạo mẫu thử.

### 14.4. Kiểm thử retry, cache và batch

Gửi cùng event nhiều lần để kiểm tra bỏ trùng. Gửi request độc lập cùng URL hoặc cùng client request ID để chứng minh không gộp nhầm.

Làm nóng cache từ chối rồi gọi lại. Mỗi quyết định logic trong phạm vi vẫn cần được ghi theo hợp đồng.

Với batch, kiểm tra cả chế độ từ chối toàn bộ và xử lý từng phần nếu hệ thống hỗ trợ. Event phải khớp quy tắc và kết quả thực thi, không chỉ mã HTTP của toàn request.

### 14.5. Kiểm thử pipeline và tải

Mô phỏng kho trung tâm lỗi, collector dừng, queue chậm, disk gần đầy, restart và phục hồi trong mô hình đã xác định.

Đo tải và kích thước thực của event, không chỉ số request. Một request batch có thể phát nhiều sự kiện.

Đối soát tập event sau phục hồi, bản sao, thứ tự và thời điểm truy vấn. Cần kiểm tra cả việc phát hiện khoảng trống khi chủ động tạo lỗi ngoài khả năng bảo đảm, thay vì yêu cầu hệ thống báo thành công trong mọi tình huống.

Enforcement phải tiếp tục giữ từ chối khi pipeline gặp lỗi. Không thử tải bằng cách gây sự cố ngoài phạm vi được phép.

### 14.6. Kiểm thử detector và cảnh báo

Tạo chuỗi tổng hợp đáp ứng đúng ngưỡng 20 quyết định và 10 tham chiếu trong cửa sổ mẫu. Kiểm tra cảnh báo và các mốc đo.

Thêm bản sao event, event đến muộn và các quyết định thuộc principal hoặc tenant khác. Chúng không được làm sai nhóm đếm.

Tạo hoạt động bình thường như mở liên kết cũ sau đổi role để kiểm tra mức cảnh báo và cách phân tích. Mục tiêu là tín hiệu có ích, không chỉ sinh thật nhiều cảnh báo.

Nếu detector cần event cho phép hoặc lịch sử đổi quyền, bộ thử phải có các nguồn đó với ngữ nghĩa đúng.

### 14.7. Kiểm thử quyền đọc và vòng đời audit

Thử danh tính writer, người điều tra được cấp quyền, người hỗ trợ tenant khác và actor không có quyền export.

Kiểm tra thay cấu hình, xử lý retention, bảo toàn và truy cập backup trong phạm vi. Không suy từ việc API tìm kiếm có phân quyền rằng mọi đường tải file log cũng đã được bảo vệ.

Bằng chứng kiểm thử cần được lọc và lưu theo chính sách, không tạo một kho dữ liệu nhạy cảm phụ.

## 15. Vận hành và những cách đặc tả dễ sai

### 15.1. Số liệu cần gắn với phạm vi

Nên theo dõi mức phủ điểm thực thi, số quyết định theo loại, độ trễ truy vấn, backlog, event lỗi schema, bản sao, khoảng trống, tình trạng buffer và cảnh báo.

Tách DENY do chính sách khỏi lỗi đánh giá quyền. Nếu gộp chúng, tổ chức có thể nhầm sự cố hạ tầng với tấn công tăng quyền hoặc bỏ sót một lỗi triển khai.

Số event tăng sau deploy có thể do chính sách đúng hơn, bug mới hoặc thay schema. Cần liên kết phiên bản và bối cảnh trước khi kết luận.

Nếu cam kết là giới hạn tối đa, p95 hay trung bình không chứng minh mọi event đáp ứng. Báo cáo cần có vi phạm và phần chưa xác minh.

### 15.2. Những câu yêu cầu cần viết lại

| Cách viết chưa đủ | Vấn đề | Cách làm rõ |
| --- | --- | --- |
| Log mọi 403 | Bỏ sót 404 che giấu và các kênh không phải HTTP | Phát sự kiện từ quyết định có thẩm quyền |
| Access denied là đủ | Không rõ nguyên nhân, đối tượng và chính sách | Schema có phân loại, ngữ cảnh và phiên bản |
| Log toàn request để điều tra | Lộ credential và dữ liệu cá nhân | Allowlist trường và tham chiếu tối thiểu |
| Request ID là khóa bỏ trùng | Caller có thể tái sử dụng hoặc giả mạo | Event ID và decision ID do phía tin cậy quản lý |
| Actor nội bộ không cần ghi | Bỏ sót lạm dụng workload | Phạm vi theo quyết định, có phân loại actor |
| Có JSON là chống injection | Công cụ xem vẫn có thể diễn giải sai | Serialize, giới hạn và hiển thị an toàn đầu cuối |
| Mọi DENY đều là sự cố nghiêm trọng | Tạo quá tải cảnh báo | Tương quan theo hành động, chuỗi và ngữ cảnh |
| Logger lỗi thì cho qua | Biến lỗi quan sát thành bypass | Giữ từ chối, đệm hoặc báo lỗi theo hợp đồng |
| Gọi logger thành công là đã có audit | Chưa biết độ bền và khả năng truy vấn | Định nghĩa mốc và mô hình sự cố |
| Số event bằng số request là đầy đủ | Batch, bản sao và nhiều điểm có đơn vị khác | Đối soát tập quyết định và event hợp lệ |
| Không thấy log nghĩa là không có hành vi | Có thể mất pipeline hoặc thiếu điểm phát | Kết hợp mức phủ và tín hiệu sức khỏe |
| Có chữ ký là mọi nội dung đúng | Producer vẫn có thể sai hoặc bị chiếm | Tách nguồn, toàn vẹn và độ đầy đủ |

Một đặc tả audit cho authorization failure cần chứng minh cả việc hành động bị cấm đã không xảy ra và việc quyết định đó được ghi nhận đúng ngữ cảnh. Khi nội dung, phạm vi, pipeline và bằng chứng được liên kết rõ, sự kiện từ chối mới trở thành dữ liệu có ích để điều tra và cải thiện kiểm soát.

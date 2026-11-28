# Alert theo authorization failure

## 1. Từ sự kiện từ chối đến một tín hiệu có thể xử lý

Alert theo authorization failure là cảnh báo được tạo từ các quyết định từ chối quyền hoặc một mẫu tương quan của chúng, nhằm phát hiện hoạt động cần được xem xét.

Một request bị từ chối có thể là dấu hiệu dò tài nguyên, thử vượt phạm vi hoặc lạm dụng credential. Nó cũng có thể xuất phát từ liên kết cũ, thay đổi vai trò hợp lệ, lỗi giao diện hoặc cấu hình workload sai.

Vì vậy, yêu cầu “cảnh báo khi có lỗi phân quyền” chưa đủ. Cần xác định:

- Sự kiện nào là đầu vào hợp lệ?
- Đơn vị đếm là request, quyết định hay bản sao log?
- Gom nhóm theo actor, tenant, tài nguyên và hành động thế nào?
- Trong cửa sổ nào, bao nhiêu sự kiện tạo điều kiện cảnh báo?
- Cảnh báo được tạo và tới đúng nơi trong bao lâu?
- Ai tiếp nhận, cách giảm nhiễu và cách kiểm chứng phần bỏ sót?
- Khi dữ liệu đầu vào lỗi hoặc thiếu, hệ thống báo tình trạng nào?

OWASP yêu cầu thiết kế logging, giám sát và cảnh báo theo rủi ro, đồng thời lưu ý rằng áp dụng máy móc có thể tạo quá nhiều cảnh báo khiến tín hiệu thật bị bỏ qua. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#which-events-to-log).

Mục tiêu của bài là chuyển một giả thuyết phát hiện thành yêu cầu bảo mật có thể đo và kiểm chứng, từ nguồn sự kiện đến nơi xử lý cảnh báo.

## 2. Phân biệt event, detection, alert và incident

| Khái niệm | Ý nghĩa | Điều không được suy ra |
| --- | --- | --- |
| Event | Bản ghi về một quyết định hoặc hoạt động | Một event không tự là tấn công |
| Detection condition | Điều kiện hoặc mẫu cần phát hiện | Điều kiện đúng chưa chứng minh ý đồ |
| Detection candidate | Kết quả máy xác định mẫu đã khớp | Chưa chắc đã được gửi tới người xử lý |
| Alert | Tín hiệu có ngữ cảnh và vòng đời để xử lý | Đã tạo alert không có nghĩa đã có người đọc |
| Incident | Sự cố được xác định theo quy trình có thẩm quyền | Không phải mọi alert đều trở thành incident |
| Response | Hành động ứng phó | Alert không tự cấp quyền khóa hoặc thay dữ liệu |

### 2.1. Authorization denied khác authentication failure

Principal đã được xác thực nhưng không có quyền đọc đối tượng là một loại sự kiện. Không xác minh được credential là loại khác.

Lỗi dịch vụ đánh giá quyền cũng cần phân biệt với việc chính sách đã xác định thiếu quyền. Nếu hạ tầng không trả quyết định, không nên tăng bộ đếm “người dùng thử quyền sai” như thể đã có bằng chứng đó.

Trong bài, quy tắc chính sử dụng quyết định DENY hợp lệ từ điểm thực thi có thẩm quyền. Các lỗi đầu vào hoặc đánh giá được theo dõi bằng nhóm tín hiệu riêng.

### 2.2. HTTP status không thay thế ngữ nghĩa sự kiện

Đếm 403 ở proxy có thể gồm nhiều nguyên nhân không phải phân quyền nghiệp vụ. Một API cũng có thể che tài nguyên bị cấm bằng phản hồi khác hoặc trả lỗi từng phần trong batch.

Detector cần sự kiện có loại, nguồn và kết quả quyết định rõ. Mã phản hồi có thể hỗ trợ ngữ cảnh nhưng không phải căn cứ duy nhất.

### 2.3. Không có DENY không chứng minh an toàn

Một đường bypass có thể cho phép truy cập mà không tạo lần từ chối nào. Một credential có quyền rộng bị chiếm cũng có thể chỉ tạo hành động được cho phép.

Cảnh báo từ DENY có phạm vi phát hiện riêng. Không nên dùng nó làm bằng chứng đã phát hiện mọi hành vi vượt quyền.

## 3. Xây dựng giả thuyết phát hiện theo rủi ro

### 3.1. Nêu hành vi cần tìm

Ví dụ một giả thuyết:

> Một principal đã xác thực liên tục thử đọc nhiều tham chiếu tài nguyên ngoài phạm vi trong thời gian ngắn; hệ thống cần tạo tín hiệu để kiểm tra khả năng dò tài nguyên hoặc lỗi tích hợp.

Giả thuyết nói rõ actor, hành động, mức đa dạng mục tiêu và thời gian. Nó không kết luận rằng mọi principal đáp ứng mẫu đều là kẻ tấn công.

Một giả thuyết khác có thể là workload vốn không cần chức năng quản trị lại liên tục gọi hành động đó. Không nhất thiết dùng cùng ngưỡng với hành vi đọc tài nguyên thông thường.

### 3.2. Từ đe dọa đến đặc tính quy tắc

| Tình huống | Điều muốn phát hiện | Điều kiện cần xem xét |
| --- | --- | --- |
| Thử nhiều mã đối tượng | Dò phạm vi tài nguyên | Số quyết định và số tham chiếu mục tiêu khác nhau |
| Gọi chức năng quản trị ngoài nhiệm vụ | Thử tăng quyền hoặc cấu hình sai | Nhóm hành động và loại actor |
| Nhiều lỗi tenant | Truy cập chéo hoặc sai ánh xạ | Ngữ cảnh tenant đáng tin cậy |
| Từ chối tăng ngay sau deploy | Lỗi chính sách hoặc client | Phiên bản ứng dụng và lịch thay đổi |
| Nhiều principal cùng lỗi đánh giá | Sự cố phụ thuộc chung | Event hạ tầng riêng, không gộp vào DENY |
| Một actor thử chậm trong thời gian dài | Né quy tắc ngắn hạn | Quy tắc hoặc phân tích có cửa sổ khác |
| Nhiều actor phối hợp | Phân tán hành vi | Tín hiệu liên kết được phép, không chỉ IP |

Một quy tắc không cần giải quyết mọi hàng của bảng. Nhưng phạm vi và điểm mù phải được ghi rõ.

### 3.3. Mức ưu tiên và độ tin cậy là hai chiều

Một hành động nhạy cảm có thể có tác động cao, dù bằng chứng tấn công còn yếu. Một mẫu đếm có thể khớp chắc chắn, nhưng nguyên nhân vẫn có thể là hoạt động hợp lệ.

Nên phân biệt mức tác động, độ tin cậy của đầu vào, độ chắc chắn rằng mẫu khớp và đánh giá nguyên nhân sau điều tra.

Không gán “tấn công đã xác nhận” chỉ vì một ngưỡng số học đã đạt.

## 4. Hợp đồng dữ liệu đầu vào

### 4.1. Trường cần cho quy tắc

| Nhóm | Dữ liệu cần có |
| --- | --- |
| Nguồn | Dịch vụ, điểm thực thi và phạm vi producer tin cậy |
| Quyết định | Loại event, outcome, reason và decision reference |
| Actor | Principal, miền phát hành và trạng thái xác minh |
| Tenant | Phạm vi được nguồn tin cậy xác lập |
| Hành động | Action hoặc action group theo ánh xạ có phiên bản |
| Mục tiêu | Loại và tham chiếu được xử lý an toàn |
| Thời gian | Mốc sự kiện và mốc đầu vào tiếp nhận |
| Liên kết | Event ID, interaction hoặc request reference phù hợp |
| Ngữ cảnh | Phiên bản chính sách, ứng dụng và thông tin cần cho phân tích |

Không cần đưa password, token, toàn request body hoặc nội dung tài nguyên vào alert.

### 4.2. Trường có thẩm quyền và giá trị tự khai

Principal và tenant dùng để gom nhóm phải đến từ ngữ cảnh đã xác minh, không phải header hoặc JSON mà caller tự đặt.

Nếu không có principal đủ tin cậy, không gộp mọi event thành một người tên UNKNOWN rồi tạo cảnh báo sai. Cần trạng thái dữ liệu chưa đủ, nhóm xử lý riêng và chỉ báo mức phủ.

Tham chiếu tài nguyên được yêu cầu không chứng minh tài nguyên tồn tại. Detector có thể đếm những tham chiếu khác nhau mà không đọc nội dung hoặc truy vấn chủ sở hữu ngoài nhu cầu.

### 4.3. Đơn vị đếm phải được định nghĩa

Trong ví dụ, đơn vị là quyết định từ chối logic cuối cùng tại điểm thực thi được quy tắc chọn.

Bản mô tả cùng quyết định từ nhiều lớp hoặc bản sao vận chuyển không tăng số đếm. Một batch có nhiều quyết định độc lập cần hợp đồng rõ về mức phần tử.

Một request mới bị từ chối từ cache vẫn có thể là quyết định logic mới. Không bỏ nó chỉ vì không gọi dịch vụ chính sách.

Event ID và decision reference cần phạm vi duy nhất phù hợp. Request ID do caller tái sử dụng không phải khóa an toàn để xóa các lần thử độc lập.

## 5. Đặc tả một quy tắc minh họa

### 5.1. Phạm vi và giả định

Giả sử hệ thống nhiều tenant có hành động đọc tài liệu. Quy tắc mẫu tìm một principal thử nhiều tham chiếu mục tiêu và bị từ chối trong thời gian ngắn.

Các con số sau chỉ là giả định học tập, không phải ngưỡng chuẩn cho mọi hệ thống:

- Cửa sổ trượt 60 giây theo thời gian sự kiện.
- Ít nhất 20 quyết định từ chối logic riêng biệt.
- Ít nhất 10 tham chiếu mục tiêu khác nhau.
- Gom nhóm theo miền danh tính, principal, tenant đáng tin cậy và nhóm hành động.
- Chỉ dùng nguồn và loại quyết định đã được chọn.

Tập lý do được phép gồm thiếu quyền hành động và không phù hợp phạm vi tài nguyên. Lỗi hạ tầng đánh giá quyền không nằm trong số đếm này.

### 5.2. Điều kiện hình thức

Gọi G là một nhóm:

~~~text
G = (identity_issuer, principal_ref, actor_tenant_ref, action_group)

E_G(t) = các quyết định hợp lệ, riêng biệt thuộc G
         có occurred_at trong khoảng (t - 60 giây, t]

Quy tắc khớp khi:
    số phần tử E_G(t) >= 20
và số tham chiếu mục tiêu khác nhau trong E_G(t) >= 10
~~~

Mốc đúng t - 60 giây bị loại; mốc t được tính. Cần chọn và giữ nhất quán quy tắc ranh giới, không để bộ kiểm thử và engine hiểu khác nhau.

Cửa sổ trượt không đồng nghĩa bucket theo phút lịch. Một chuỗi qua ranh giới phút vẫn có thể nằm trong 60 giây và phải được đánh giá.

t có thể là thời gian của một sự kiện làm tập quyết định đủ điều kiện. Khi dữ liệu đến sai thứ tự, engine phải đánh giá lại các cửa sổ liên quan theo hợp đồng.

### 5.3. Chỉ đếm bằng chứng có ngữ nghĩa đúng

Một event transport gửi lại không tăng số quyết định. Nhiều bản mô tả cùng decision cũng không tăng số đếm.

Nếu cùng principal_ref có thể tồn tại ở hai miền phát hành, phải có identity_issuer trong khóa. Nếu dùng cùng ID giữa tenant, khóa tenant không được bỏ.

Tham chiếu mục tiêu cần kiểu và namespace phù hợp. Không coi hai cách encoding của cùng tham chiếu là hai mục tiêu nếu hợp đồng chuẩn hóa xác định chúng tương đương.

Đồng thời, không chuẩn hóa tùy tiện làm gộp những ID thực sự khác nhau.

### 5.4. Mẫu khớp không chứng minh tài nguyên đã bị đọc

Quy tắc đếm những yêu cầu bị từ chối và các tham chiếu được thử. Nó không chứng minh các tài nguyên tồn tại, dữ liệu đã bị lộ hoặc actor có ý đồ xấu.

Nếu một chương trình hợp lệ thử 20 lần trên 12 tham chiếu và tất cả bị từ chối, mẫu vẫn khớp theo đặc tả. Việc đánh giá đó là cảnh báo hữu ích hay nhiễu thuộc phân tích mục đích, ngữ cảnh và hiệu chỉnh có phiên bản.

Không tùy ý bỏ kết quả chỉ vì người kiểm thử biết chương trình là hợp lệ mà quy tắc chưa có điều kiện ngoại lệ tương ứng.

## 6. Thời gian sự kiện, dữ liệu đến muộn và độ trễ

### 6.1. Các mốc phải khác nhau

Một mô hình có thể dùng:

- T_qualify: thời gian sự kiện tại cửa sổ đủ điều kiện.
- T_ready: mốc đầu vào đã tiếp nhận đủ tập event cần để chứng minh điều kiện.
- T_candidate: candidate và thông tin liên kết đã được ghi bền.
- T_destination_ack: đích đã xác nhận tiếp nhận theo hợp đồng.
- T_human_ack: người có trách nhiệm xác nhận xử lý.

T_ready phải dựa trên timestamp do thành phần đầu vào đáng tin cậy xác lập. Không dùng thời điểm engine bắt đầu chạy để reset độ trễ khi nó đã tồn đọng nhiều phút.

Việc phân biệt thời gian xảy ra với thời gian quan sát cũng xuất hiện trong mô hình log của OpenTelemetry qua Timestamp và ObservedTimestamp. Các tên trường của bài là ví dụ thiết kế, không phải ánh xạ mặc định sang mọi hệ thống. [OpenTelemetry, Logs](https://opentelemetry.io/docs/concepts/signals/logs/).

### 6.2. Đặc tả latency theo từng đoạn

Ví dụ chọn:

~~~text
T_candidate - T_ready <= 30 giây

T_destination_ack - T_candidate <= 30 giây
~~~

Đây là thời hạn tạo candidate và giao đến đích, không phải cam kết người trực đã đọc trong 30 giây.

Nếu nguồn có thể mất nhiều phút mới tới đầu vào, hai giới hạn này không chứng minh phát hiện đầu cuối nhanh. Cần yêu cầu riêng về vận chuyển, độ mới, sai lệch đồng hồ và mô hình sự cố.

Nếu mục tiêu là một deadline đầu cuối, ngân sách phải bao phủ mọi đoạn, việc ghi bền và độ chính xác phép đo. Không chỉ công bố thời gian xử lý của truy vấn.

### 6.3. Sự kiện đến muộn

Giả sử đường xử lý thời gian thực chấp nhận độ trễ đầu vào tối đa 30 giây theo cách đo đã chọn.

State phải được giữ đủ cho cửa sổ, độ muộn và nhu cầu phục hồi. Không xóa ngay dữ liệu cửa sổ chỉ vì đồng hồ xử lý đã đi qua thời gian sự kiện.

Event trong giới hạn được cập nhật vào cửa sổ liên quan và có thể tạo candidate sau khi chuỗi đã xảy ra. Alert phải phản ánh đúng khoảng thời gian hành vi.

Nếu chỉ cần chứng minh ngưỡng bằng những event đã có và điều kiện không cần chờ dữ liệu khác, không nên vô cớ chờ hết watermark mới tạo candidate.

### 6.4. Event ngoài giới hạn và replay lịch sử

Event quá muộn không được âm thầm biến mất khỏi mọi báo cáo. Cần chính sách backfill, phân tích lịch sử hoặc đánh dấu không thuộc bảo đảm thời gian thực.

Alert từ replay phải có nhãn phù hợp. Không mô tả một chuỗi diễn ra hôm qua như một cuộc tấn công đang xảy ra chỉ vì nó được nạp hôm nay.

Timestamp tương lai bất thường hoặc thiếu phải có xử lý chất lượng dữ liệu. Không tự thay toàn bộ bằng thời điểm nhận mà vẫn báo quy tắc event-time nguyên vẹn.

## 7. Vòng đời alert, chống trùng và giao đúng nơi

### 7.1. Từ rule match đến người xử lý

~~~mermaid
flowchart LR
    A["Sự kiện tin cậy"] --> B["Chuẩn hóa và loại bản sao"]
    B --> C["Tính cửa sổ và điều kiện"]
    C --> D["Candidate được ghi bền"]
    D --> E["Gom nhóm, ưu tiên và định tuyến"]
    E --> F["Đích xác nhận tiếp nhận"]
    F --> G["Người xử lý xác nhận và phân tích"]
    G --> H["Kết luận hoặc chuyển quy trình sự cố"]
~~~

Một dashboard có candidate không chứng minh hàng đợi xử lý đã nhận. Một đích ACK cũng không chứng minh người trực đã xem.

Mỗi trạng thái cần mốc và nguồn xác nhận. Lỗi định tuyến phải có retry, giới hạn và cơ chế phát hiện riêng.

### 7.2. Một chuỗi không cần tạo alert mới cho mỗi event

Trong ví dụ, sau lần kích hoạt đầu tiên, các match tiếp theo cùng nhóm có thể cập nhật cùng episode cảnh báo.

Cooldown minh họa là 300 giây tính từ mốc thông báo đã ghi nhận. Trong thời gian này vẫn cập nhật số lượng, mục tiêu và bằng chứng; chỉ giảm việc gửi lặp theo quy tắc.

Không reset cooldown mỗi lần có event mới, vì cách đó có thể làm thông báo tiếp theo bị trì hoãn vô hạn.

Nếu có điều kiện tăng mức nghiêm trọng, chính sách có thể yêu cầu thông báo bổ sung mà không chờ cooldown. Điều kiện này phải được đặc tả và kiểm thử.

### 7.3. Bỏ trùng giao nhận khác với giảm nhiễu

Candidate hoặc alert cần ID ổn định để retry cùng thông báo không tạo nhiều case khi đích có hỗ trợ idempotency.

Không hứa giao đúng một lần nếu đích không có khả năng tương ứng. Cần biết hệ thống xử lý ACK mất hoặc thông báo trùng thế nào.

Bỏ trùng không được gộp tenant, principal hoặc rule version khác nhau chỉ vì cùng một tiêu đề cảnh báo.

### 7.4. Restart và kết thúc episode

Checkpoint cửa sổ, offset đầu vào và sổ alert cần có mô hình phục hồi nhất quán. Sau restart, không nên quên một nửa chuỗi hoặc phát lại hàng loạt cảnh báo đã gửi.

Một episode có thể được đóng theo thời gian yên lặng hoặc quyết định xử lý đã định. Nhưng không có event mới trong lúc pipeline mất dữ liệu không chứng minh hành vi đã dừng.

Trạng thái cảnh báo và sức khỏe dữ liệu phải được xem cùng nhau. Phục hồi hoặc replay không được tự đóng case chưa được giải quyết.

## 8. Nội dung alert phải đủ dùng và có giới hạn

### 8.1. Những thông tin cần có

Một alert nên có rule ID và version, giả thuyết, nhóm actor, tenant được phép xem, cửa sổ, số quyết định, số mục tiêu và tham chiếu bằng chứng.

Cần phân biệt mức tác động, kết quả khớp mẫu và kết luận điều tra. Không đưa nhãn “đã xâm nhập” chỉ từ các lần bị từ chối.

Đường dẫn bằng chứng phải kiểm tra quyền khi truy cập. Biết alert ID không tự cho phép tải log của tenant khác.

### 8.2. Ví dụ alert tổng hợp

~~~json
{
  "alert_id": "alert-demo-31",
  "rule_id": "AUTHZ-DENY-ENUM",
  "rule_version": "demo-v1",
  "hypothesis": "Repeated denied access to diverse requested references",
  "group": {
    "identity_issuer": "issuer-demo-a",
    "principal_ref": "principal-demo-01",
    "actor_tenant_ref": "tenant-demo-a",
    "action_group": "document.read"
  },
  "window": {
    "start_exclusive": "2026-11-27T02:00:00Z",
    "end_inclusive": "2026-11-27T02:01:00Z"
  },
  "evidence_summary": {
    "distinct_denial_decisions": 20,
    "distinct_requested_refs": 12,
    "evidence_set_ref": "evidence-set-demo-31"
  },
  "severity": "MEDIUM",
  "pattern_state": "MATCHED",
  "incident_assessment": "UNCONFIRMED",
  "created_at": "2026-11-27T02:01:20Z",
  "destination_ack_at": "2026-11-27T02:01:35Z",
  "human_ack_at": null
}
~~~

Ví dụ dùng dữ liệu tổng hợp. Đích đã nhận không có nghĩa người xử lý đã xác nhận.

Không cần kèm toàn bộ 20 event, nguyên credential hoặc nội dung tài liệu trong thông báo. Chi tiết có thể nằm ở kho bằng chứng với quyền riêng.

Tham chiếu principal và tenant vẫn là dữ liệu cần bảo vệ, không tự trở thành thông tin công khai vì đã dùng mã.

## 9. Giảm nhiễu mà không làm mất phạm vi phát hiện

### 9.1. Hiểu hoạt động bình thường

Các nguyên nhân hợp lệ có thể tạo nhiều DENY:

- Người dùng mở liên kết cũ sau khi bị thu hồi một quyền.
- Client còn hiển thị chức năng đã bị bỏ khỏi vai trò.
- Job gọi nhầm API hoặc ánh xạ tenant sai.
- Một lần triển khai thay phiên bản chính sách.
- Tác vụ kiểm chứng được phép tạo dữ liệu thử theo kế hoạch.

Những tình huống này vẫn có giá trị vận hành. Cần phân loại hoặc định tuyến phù hợp, không mặc định bỏ toàn bộ.

Một workload nội bộ hoặc principal có role cao cũng có thể bị chiếm. Không dùng loại actor đó làm ngoại lệ chung cho mọi quy tắc.

### 9.2. Count, diversity và ratio trả lời các câu hỏi khác nhau

Số quyết định cho biết khối lượng. Số tham chiếu khác nhau cho biết mức đa dạng mục tiêu. Tỷ lệ từ chối có thể giúp so với tổng hoạt động.

Nếu dùng tỷ lệ, phải có mẫu số đúng phạm vi: cùng actor, tenant, hành động, cửa sổ và loại request. Không chia DENY nghiệp vụ cho tổng mọi request bao gồm health check rồi coi đó là tỷ lệ lỗi quyền.

Một principal có một lần bị từ chối trên một request có tỷ lệ 100% nhưng ít bằng chứng về một chuỗi. Có thể cần số lượng tối thiểu cùng ngữ cảnh.

Ngược lại, actor có lưu lượng lớn vẫn có thể tạo nhiều lần thử ngoài quyền dù tỷ lệ thấp. Không chỉ nhìn một phần trăm.

### 9.3. Ngoại lệ cần owner và hết hạn

Một suppression hợp lệ cần:

- Phạm vi actor, tenant, hành động và quy tắc.
- Lý do và nguồn quyết định.
- Người chịu trách nhiệm.
- Thời điểm bắt đầu và hết hiệu lực.
- Điều kiện xem xét hoặc thu hồi.
- Dấu vết thay đổi.

Không tự gia hạn suppression vì event tiếp tục xuất hiện. Không dùng danh sách tên “trusted” không có vòng đời.

Suppression có thể giảm thông báo hoặc thay ưu tiên theo chính sách, nhưng không tự cho phép xóa sự kiện gốc hoặc che số lượng đã bị suppression.

Sau hết hạn, quy tắc phải trở lại hành vi đã định. Việc này cần kiểm thử, không chỉ có một trường expires_at.

### 9.4. Hiệu chỉnh có phiên bản

Thay ngưỡng, ánh xạ action, danh sách reason hoặc khóa gom nhóm có thể làm thay phạm vi phát hiện.

Cần ghi version, lý do, dữ liệu đánh giá và thời điểm hiệu lực. Backtest theo cùng một version phải có kết quả tái tạo được trong các giả định đã công bố.

Không tăng ngưỡng chỉ để giảm số alert mà không xem các mẫu có thể bị bỏ sót. Nếu chủ động chấp nhận điểm mù, phải ghi rõ và xác định kiểm soát hoặc detector bổ sung khi cần.

Cold start hoặc thiếu dữ liệu nền cũng cần trạng thái riêng. Một baseline chưa có lịch sử không tự trở thành căn cứ mạnh để gắn nhãn bất thường.

### 9.5. Giới hạn của quy tắc ngắn hạn

Quy tắc 20 quyết định trong 60 giây có thể bỏ qua actor thử chậm hơn, dùng nhiều principal hoặc chỉ thực hiện một hành động có tác động cao.

Có thể cần quy tắc cửa sổ dài, quy tắc theo hành động nhạy cảm hoặc tương quan nhiều nguồn. Chúng cần yêu cầu riêng, không được ngầm tuyên bố đã được quy tắc mẫu bao phủ.

Không gộp mọi principal cùng IP thành một actor chắc chắn. Proxy, NAT và nguồn IP không được xác minh có thể tạo tương quan sai.

## 10. Sức khỏe dữ liệu và sức khỏe detector

### 10.1. Không có alert có nhiều nguyên nhân

Có thể thực sự không có mẫu khớp. Cũng có thể nguồn ngừng phát, collector dừng, schema đổi, rule bị tắt hoặc đích cảnh báo không nhận.

Cần một lớp quan sát riêng cho:

- Mức phủ nguồn và điểm thực thi.
- Event đầu vào, hợp lệ, không đủ trường hoặc bị loại theo lý do.
- Độ trễ đầu vào và số event quá muộn.
- Checkpoint, queue, lỗi xử lý và tình trạng state.
- Rule đang bật và phiên bản thực tế.
- Candidate đã ghi, thông báo đã ACK và lỗi giao.
- Suppression còn hiệu lực và số match chịu tác động.

Heartbeat chứng minh một mức kết nối, không chứng minh mọi quyết định đã được ghi đủ. Cần đối soát phù hợp nếu yêu cầu độ đầy đủ cao hơn.

### 10.2. Không giấu mất dữ liệu trong bộ lọc

Một lần đổi schema có thể làm tất cả event không còn đạt điều kiện actor hoặc reason. Nếu chỉ nhìn số alert bằng không, hệ thống có thể trông khỏe hơn trong khi thực tế bị mù.

Bộ lọc cần số liệu theo lý do loại và cảnh báo chất lượng. Event không đủ điều kiện không được gán bừa vào nhóm UNKNOWN để duy trì số đếm.

Cần phân biệt bị loại đúng chính sách với không thể xử lý do lỗi hợp đồng dữ liệu.

### 10.3. Khả năng chịu tải và state có giới hạn

Yêu cầu tải phải gồm tốc độ event, số nhóm đồng thời, mức đa dạng mục tiêu, cửa sổ, độ muộn và nhu cầu replay.

Một hệ thống chịu được nhiều event cho một principal chưa chắc chịu được cùng lượng event phân tán trên hàng nghìn principal.

Nếu state bị loại vì cạn tài nguyên, cần thể hiện phần bảo đảm không còn đạt. Không âm thầm quên các nhóm rồi báo không có hành vi đáng ngờ.

Backpressure, buffer và phục hồi đều có giới hạn. Phạm vi tải và mô hình sự cố phải được lựa chọn trước khi khẳng định SLA.

### 10.4. Detector lỗi không được làm yếu phân quyền

Hệ thống quan sát có thể không sẵn sàng nhưng điểm thực thi vẫn phải giữ chính sách truy cập bắt buộc.

Không có alert không trở thành bằng chứng request được phép. Lỗi detector cũng không được biến DENY thành ALLOW.

Nếu thiết kế cần một quyết định chặn trực tuyến từ hệ thống rủi ro, đó là một kiểm soát khác với cảnh báo bất đồng bộ và cần yêu cầu lỗi riêng.

### 10.5. Phát hiện lỗi giao cảnh báo

Nếu đích không ACK, cần retry có giới hạn và trạng thái chờ hoặc thất bại rõ.

Cần cách phát hiện việc giao bị lỗi không chỉ phụ thuộc vào chính kênh đã hỏng. Có thể là kênh dự phòng được xác định, dashboard có người giám sát hoặc cơ chế sức khỏe riêng.

Không ghi DELIVERED chỉ vì hàm gửi đã trả về trước khi đích thực sự tiếp nhận theo hợp đồng.

## 11. Chủ sở hữu, quyền riêng tư và phản ứng sau cảnh báo

### 11.1. Một alert cần nơi tiếp nhận cụ thể

Cần xác định đội hoặc vai trò phụ trách theo dịch vụ, tenant, mức tác động và thời gian trực.

Các mốc nên phân biệt:

- Đích tiếp nhận.
- Người xử lý xác nhận.
- Bắt đầu phân tích.
- Chuyển nhóm hoặc nâng cấp.
- Có kết luận hoặc chuyển thành incident.

Ví dụ, nếu sau 5 phút từ ACK của đích chưa có người xác nhận trong phạm vi trực đã cam kết, hệ thống phải chuyển cấp theo quy trình mẫu. Đây là yêu cầu phát hiện và chuyển tiếp khi quá hạn, không phải cam kết máy có thể buộc con người đọc.

Lịch trực, múi giờ và phạm vi ngoài giờ phải được xác định. Không mặc định mọi nhóm đều trực liên tục.

### 11.2. Runbook cần bắt đầu từ xác minh

Các bước xem xét có thể gồm:

1. Kiểm tra nguồn và độ đầy đủ dữ liệu.
2. Xác nhận group, cửa sổ và quy tắc đúng version.
3. Loại bản sao, lỗi client hoặc thay chính sách đã biết.
4. Xem hành động, mức nhạy cảm và quan hệ quyền phù hợp.
5. Đối chiếu thay đổi quyền hoặc hành động liên quan nếu có nguồn.
6. Đánh giá cần chuyển sự cố, sửa tích hợp hay tiếp tục theo dõi.
7. Ghi kết luận và bằng chứng tối thiểu.

Không cần mở dữ liệu tài nguyên bị cấm để chứng minh actor đã thử truy cập nó.

### 11.3. Không phản ứng tự động chỉ từ một nhãn

Nếu alert có thể kích hoạt khóa tài khoản, thu hồi credential hoặc chặn tenant, cơ chế phản ứng cần quyền, điều kiện và audit riêng.

Actor không được đưa lệnh tùy ý vào một trường alert rồi khiến hệ thống ứng phó thực thi nó. Runbook và hành động tự động phải dựa trên cấu hình có thẩm quyền.

Cần xét khả năng kẻ tấn công tạo tín hiệu để gây khóa nhầm người khác. Cảnh báo về một IP hoặc ID chưa được xác minh không đủ để quy trách nhiệm chắc chắn.

Biện pháp phản ứng có thể cần kiểm tra lại ngữ cảnh hiện tại, tính idempotent và đường xử lý nhầm.

### 11.4. Bằng chứng và thông báo có quyền riêng

Alert có thể chứa principal, tenant, địa chỉ nguồn và lịch sử hoạt động. Cần giới hạn người nhận và dữ liệu trong nội dung gửi.

Không đưa nguyên token hoặc nội dung tài liệu vào tin nhắn. Không dùng URL chứa credential để chia sẻ bằng chứng.

Người nhận alert không tự có quyền xem mọi tenant. Kho bằng chứng cần kiểm tra quyền khi truy cập, không chỉ lúc tạo liên kết.

Candidate, case, notification, export và dữ liệu kiểm thử đều có retention phù hợp. Đóng case không tự có nghĩa xóa ngay mọi bằng chứng, cũng không phải lý do giữ vô hạn.

## 12. Bộ yêu cầu đo được cho quy tắc mẫu

### 12.1. Phạm vi bảo đảm

Quy tắc mẫu áp dụng cho nguồn từ chối đọc tài liệu đã được kiểm kê, có actor và tenant đáng tin cậy, event có hợp đồng định danh và thời gian phù hợp.

Các ngưỡng của bài gồm cửa sổ 60 giây, 20 quyết định, 10 tham chiếu, độ muộn đầu vào 30 giây, thời gian tạo candidate 30 giây, ACK đích 30 giây và cooldown 300 giây.

Đối với sức khỏe nguồn trong ví dụ, chọn heartbeat mỗi 10 giây. Nguồn được đánh dấu STALE khi quá 20 giây không có heartbeat hợp lệ theo mốc quan sát đáng tin cậy. Đây chỉ là một tín hiệu kết nối; vẫn cần các kiểm tra độ đầy đủ khác.

Phạm vi tải, số nhóm, khả năng phục hồi và giới hạn đồng hồ phải được chốt trước khi kiểm chứng. Không dùng một thử nghiệm ít dữ liệu để cam kết cùng latency cho tải không giới hạn.

### 12.2. Ma trận yêu cầu và tiêu chí chấp nhận

| ID | Yêu cầu | Tiêu chí chấp nhận |
| --- | --- | --- |
| DA-01 | Chỉ quyết định DENY có loại, nguồn và ngữ cảnh hợp lệ được đếm | Authentication failure, lỗi đánh giá hoặc event giả không tăng số đếm; lỗi dữ liệu được quan sát riêng |
| DA-02 | Gom nhóm theo issuer, principal, tenant đáng tin cậy và action group có phiên bản | Principal cùng tên ở miền khác hoặc event tenant khác không bị cộng chung ngoài chính sách |
| DA-03 | Tạo candidate khi có ít nhất 20 quyết định và 10 tham chiếu riêng trong (t - 60 giây, t] | Kiểm tra đủ ngưỡng, thiếu một điều kiện và đúng ranh giới; không thay bằng bucket phút |
| DA-04 | Bản sao vận chuyển không tăng đếm, quyết định độc lập không bị gộp sai | Gửi lại event không tạo ngưỡng giả; lặp request độc lập và cache DENY được tính đúng |
| DA-05 | Event đến muộn trong 30 giây được xử lý theo event-time, ngoài giới hạn có chính sách riêng | Có thể tái đánh giá cửa sổ liên quan; backfill không giả là phát hiện thời gian thực |
| DA-06 | Candidate được ghi bền trong tối đa 30 giây từ T_ready | Đo theo mốc tiếp nhận đủ input, không reset về thời điểm engine bắt đầu tính |
| DA-07 | Đích ACK trong tối đa 30 giây từ candidate theo hợp đồng giao | Mất ACK dẫn tới retry hoặc trạng thái lỗi; không ghi người đã đọc từ ACK máy |
| DA-08 | Cooldown 300 giây không bị kéo dài chỉ vì event mới; match vẫn được cập nhật | Không gửi một alert mới cho mọi event; không làm mất bằng chứng hoặc chặn escalation được quy định |
| DA-09 | Nguồn STALE và các lỗi chất lượng dữ liệu không bị diễn giải là không có hành vi | Điều kiện STALE mẫu có cảnh báo sức khỏe trong tối đa 60 giây từ khi đạt; nguồn thiếu trường có chỉ báo và owner |
| DA-10 | Restart, replay và thay phiên bản không âm thầm làm mất cửa sổ hoặc nhân đôi case | Checkpoint và ledger được đối soát; phần không phục hồi được được báo chưa đủ bảo đảm |
| DA-11 | Alert được định tuyến theo phạm vi, có owner và quyền đọc bằng chứng | Người ngoài tenant không xem được chi tiết; sau 5 phút chưa có xác nhận trong phạm vi trực thì chuyển cấp theo kế hoạch |
| DA-12 | Thay rule và suppression có thẩm quyền, version, audit và thời hạn | Caller không tắt rule hoặc tự thêm ngoại lệ; suppression hết hạn khôi phục hành vi đã định và vẫn có số liệu tác động |

DA-09 không hứa heartbeat chứng minh mọi event đã tới. Nó yêu cầu không nhầm một nguồn không còn quan sát được với một nguồn không có từ chối.

DA-10 không khẳng định mọi sự cố đều không ảnh hưởng SLA. Nếu phục hồi vượt giới hạn, phải báo vi phạm và xử lý bù, không thay mốc đo để biến thành đạt.

### 12.3. Ví dụ đặc tả có truy vết

~~~yaml
requirement_id: DA-03
risk_id: TH-DETECTION-02
hypothesis: Một principal thử đọc nhiều tham chiếu ngoài quyền trong thời gian ngắn
rule_id: AUTHZ-DENY-ENUM
rule_version: demo-v1
input_contract:
  event_type: authorization.denied
  outcome: DENY
  actor_state: VERIFIED
  source: Điểm thực thi đọc tài liệu thuộc inventory
  allowed_reasons:
    - MISSING_ACTION_PERMISSION
    - RESOURCE_SCOPE_MISMATCH
group_by:
  - identity_issuer
  - principal_ref
  - actor_tenant_ref
  - action_group
window:
  type: SLIDING
  time_basis: occurred_at
  span_seconds: 60
  left_boundary: EXCLUSIVE
  right_boundary: INCLUSIVE
thresholds:
  minimum_distinct_logical_denials: 20
  minimum_distinct_requested_refs: 10
late_input:
  maximum_realtime_delay_seconds: 30
  outside_limit: Đánh dấu và xử lý theo chính sách backfill
alert_behavior:
  candidate_deadline_from_ready_seconds: 30
  destination_ack_deadline_seconds: 30
  cooldown_seconds: 300
  keep_evidence_during_cooldown: true
failure_behavior:
  - Không nới phân quyền vì detector lỗi
  - Không gộp dữ liệu thiếu principal thành một actor giả
  - Báo trạng thái không đủ bảo đảm và chuyển owner
verification:
  - Kiểm tra ngưỡng và ranh giới
  - Kiểm tra tenant, issuer và bản sao
  - Kiểm tra đến muộn, restart và suppression
owner: Nhóm dịch vụ tài liệu và nhóm giám sát bảo mật
~~~

Đây là đặc tả minh họa, không phải cấu hình của một sản phẩm. Khi áp dụng cần gắn với inventory, schema, mô hình tải và cơ chế giao nhận cụ thể.

## 13. Đánh giá chất lượng mà không nhầm số liệu

### 13.1. Tách tính đúng của engine và ích lợi phát hiện

Tính đúng của engine trả lời: dữ liệu đáp ứng quy tắc thì có candidate đúng không, không đáp ứng thì có bị đếm sai không?

Ích lợi phát hiện trả lời: candidate đó giúp tìm tình huống rủi ro đến đâu, gây bao nhiêu công việc không cần thiết và bỏ sót những hành vi nào?

Một batch hợp lệ đáp ứng đúng ngưỡng có thể tạo candidate đúng đặc tả nhưng vẫn là tín hiệu ít giá trị cho mục tiêu phát hiện tấn công. Đó là vấn đề hiệu chỉnh giả thuyết hoặc ngữ cảnh, không nhất thiết là bug của bộ đếm.

### 13.2. Precision và recall cần tập nhãn rõ

Nếu đánh giá theo các episode đã có ground truth:

~~~text
TP: episode mục tiêu được phát hiện
FP: episode không thuộc mục tiêu nhưng bị cảnh báo như thuộc mục tiêu
FN: episode mục tiêu bị bỏ sót
TN: episode không thuộc mục tiêu và không bị cảnh báo

precision = TP / (TP + FP)
recall    = TP / (TP + FN)
~~~

Cần thống nhất đơn vị là episode, case hoặc đơn vị đã chọn, không trộn số event với số incident.

Nếu mẫu số bằng không, phải báo không xác định hoặc không đủ dữ liệu theo quy tắc đo, không tự ghi 100%.

Tỷ lệ cảnh báo bị kết luận không phải sự cố không tự là false-positive rate. FPR dùng mẫu số FP + TN trong một tập có nhãn phù hợp; mẫu số này thường không đầy đủ trong vận hành thực tế.

### 13.3. Không đo recall chỉ bằng alert đã có

Danh sách alert đã điều tra không cho biết mọi hành vi đã bị bỏ sót. Cần tập kiểm chứng có nhãn, ca mô phỏng hoặc nguồn đánh giá khác.

Số liệu production cũng có thể lệch do chỉ một phần alert được điều tra. Case còn chưa rõ không nên tự được gán là false positive.

Các kết quả cần có phạm vi dữ liệu, thời kỳ, version quy tắc, đơn vị đo và phần chưa biết.

### 13.4. Đo thời gian theo từng mốc

Nên tách độ trễ nguồn, thời gian xử lý candidate, giao tới đích, người xác nhận và thời gian phân tích.

Nếu cam kết là giới hạn tối đa, trung bình hoặc p95 không đủ chứng minh mọi trường hợp đạt. Cần xem vi phạm, event quá muộn và đoạn không quan sát được.

Một detector nhanh trên input đến muộn vẫn có thể không đáp ứng mục tiêu ứng phó. Ngược lại, một alert giao nhanh nhưng không có owner vẫn chưa thành khả năng xử lý hữu ích.

## 14. Thiết kế kiểm chứng theo rủi ro

### 14.1. Bộ dữ liệu và kỳ vọng trước khi chạy

Dùng event tổng hợp hoặc môi trường thử được phép. Mỗi ca cần input, group, thời gian, nhãn nguồn, rule version và kết quả mong đợi.

Định nghĩa oracle kiểm thử từ đặc tả, không chỉ sao chép cùng một truy vấn của engine rồi dùng nó làm đáp án.

Không cần gọi trái quyền vào dữ liệu thật để tạo mẫu. Nếu kiểm chứng nguồn phát, dùng tenant và tài nguyên tổng hợp trong phạm vi được phép.

### 14.2. Ma trận ca thử cơ bản

| Ca | Dữ liệu hoặc điều kiện | Kỳ vọng |
| --- | --- | --- |
| Đủ hai ngưỡng | 20 quyết định, 10 tham chiếu cùng group trong cửa sổ | Candidate đúng phạm vi |
| Thiếu số quyết định | 19 quyết định và đủ tham chiếu | Chưa khớp quy tắc mẫu |
| Thiếu độ đa dạng | 20 quyết định nhưng 9 tham chiếu | Chưa khớp quy tắc mẫu |
| Bản sao đẩy số lượng | 19 quyết định và một bản gửi lại | Không biến thành 20 |
| Trùng tên khác issuer | Mỗi issuer có phần chưa đủ ngưỡng | Không cộng sai |
| Khác tenant | Mỗi tenant có phần chưa đủ ngưỡng | Không tạo cảnh báo do cộng chéo |
| Khác action group | Hai nhóm riêng chưa đủ điều kiện | Không trộn ngoài ánh xạ đã định |
| Đúng ranh giới trái | Một event tại đúng t - 60 giây | Event đó không được tính |
| Qua phút lịch | Chuỗi đủ điều kiện trong 60 giây nhưng qua ranh giới phút | Vẫn khớp |
| Lỗi đánh giá quyền | Event UNAVAILABLE hoặc INVALID | Không tăng DENY; theo dõi tín hiệu riêng |
| Principal chưa rõ | Không có actor đáng tin cậy | Không gán vào principal UNKNOWN chung |
| Hoạt động hợp lệ khớp mẫu | Batch hợp lệ vẫn đủ 20 và 10 | Candidate đúng đặc tả; đánh giá nhiễu theo mục tiêu |

Các ca đủ ngưỡng phải có nguồn và trường hợp lệ. Không dùng event sai schema làm ca dương rồi kết luận engine bỏ sót hành vi.

### 14.3. Thời gian, đến muộn và cửa sổ

Tạo các event có thứ tự sự kiện khác thứ tự tiếp nhận. Event đến muộn trong giới hạn phải cập nhật được cửa sổ đúng.

Thử timestamp tương lai, thiếu timestamp và vượt độ muộn. Kết quả phải theo chính sách chất lượng hoặc backfill, không tự đổi thành thời gian hiện tại để đếm.

Đo T_ready từ mốc đầu vào, T_candidate từ bản ghi bền và ACK từ đích. Khi tạm dừng engine, thời gian chờ vẫn phải xuất hiện trong số đo.

Kiểm thử cửa sổ trượt với chuỗi gần biên. Không chỉ dùng event nằm gọn trong một phút vì ca đó không phát hiện lỗi bucket cố định.

### 14.4. Cooldown, suppression và version

Cho chuỗi tiếp tục sau khi alert đầu tiên được tạo. Xác nhận cập nhật cùng episode, giữ bằng chứng và không gửi lại cho mọi event.

Tạo match gần cuối cooldown để chứng minh nó không kéo dài thời hạn do event mới. Kiểm tra điều kiện escalation không bị suppression thông báo lặp che mất.

Thử suppression sai phạm vi, hết hạn và bị thu hồi. Event gốc và số liệu match không được biến mất.

Thay rule version và ánh xạ action theo kế hoạch. Kết quả phải truy được version áp dụng; không dùng rule mới để viết lại lời giải thích của alert cũ.

### 14.5. Restart, replay và tải

Restart sau khi đã có một phần chuỗi, sau khi tạo candidate và sau khi gửi nhưng chưa ghi ACK.

Đối soát state, offset, alert ID và case tại đích. Không bỏ sót phần trước restart hoặc tạo case mới do mất sổ giao nhận.

Replay lịch sử cần nhãn và quy tắc gửi riêng, tránh phát tán lại hàng loạt cảnh báo cũ như sự kiện hiện tại.

Thử tải theo profile đã chọn, gồm nhiều group và nhiều tham chiếu. Nếu vượt khả năng giữ state, cần quan sát được suy giảm và phần bảo đảm không đạt, không trả dashboard xanh sai.

### 14.6. Dữ liệu, định tuyến và phản ứng

Thử caller giả tenant, principal, event ID và reason. Những giá trị đó không được ghi đè trường có thẩm quyền.

Đưa secret tổng hợp hoặc chuỗi điều khiển vào các trường dễ lọt vào thông báo. Kiểm tra candidate, notification, đường lỗi và export theo giới hạn dữ liệu.

Thử người nhận ngoài quyền mở bằng chứng. Alert ID hoặc link không được tự cấp quyền.

Mô phỏng đích không ACK, người không xác nhận và kênh chính lỗi. Trạng thái, retry và chuyển cấp phải đúng, không tự đánh dấu đã xử lý.

Nếu có phản ứng tự động, kiểm thử riêng quyền, phạm vi, idempotency và khả năng cảnh báo giả gây tác động sai. Việc detector khớp mẫu không thay các điều kiện này.

## 15. Vận hành và những cách đặc tả cần sửa

Nên theo dõi độ đầy đủ nguồn, chất lượng trường, event quá muộn, độ trễ từng đoạn, số candidate, alert được gửi, suppression, case chưa có người nhận và kết quả điều tra.

Số alert giảm có thể do ít hành vi, hiệu chỉnh tốt hơn, nguồn bị mất hoặc rule bị tắt. Không kết luận từ một con số.

Các thay đổi cần owner và audit. Người có quyền điều tra không tự có quyền sửa ngưỡng hoặc suppression toàn hệ thống.

| Cách viết chưa đủ | Rủi ro | Cách làm rõ |
| --- | --- | --- |
| Có 403 thì báo tấn công | Sai nguyên nhân và tạo nhiễu | Dùng event DENY có ngữ nghĩa, nguồn và ngữ cảnh |
| 20 lỗi trong một phút | Không rõ đơn vị, group và cửa sổ | Quyết định logic, khóa group và ranh giới trượt |
| Cùng IP là cùng người | Tương quan sai | Dùng danh tính đáng tin, IP chỉ là ngữ cảnh phù hợp |
| Log trùng cũng là lần thử mới | Ngưỡng giả | Bỏ bản sao theo định danh có thẩm quyền |
| Actor chưa biết thì gộp chung | Một group giả có khối lượng rất lớn | Đường chất lượng dữ liệu riêng |
| Event đến hôm nay là hành vi hôm nay | Báo sai replay hoặc tồn đọng | Tách event-time, receive-time và mode backfill |
| Tạo alert là xong | Không ai nhận hoặc xử lý | ACK đích, owner, xác nhận và chuyển cấp |
| Mỗi match reset cooldown | Im lặng vô hạn | Mốc cooldown gắn với thông báo, không với mọi event |
| Tắt alert cho bot nội bộ | Bỏ sót credential bị chiếm | Ngoại lệ có phạm vi, owner và thời hạn |
| Precision cao nghĩa không bỏ sót | Nhầm precision và recall | Tập nhãn, đơn vị và chỉ số riêng |
| Không có alert là hệ thống an toàn | Có thể mất nguồn hoặc thiếu phạm vi | Quan sát sức khỏe và điểm mù |
| Alert tự cho phép khóa tài khoản | Có thể gây gián đoạn từ cảnh báo giả | Chính sách phản ứng và quyền độc lập |

Một đặc tả alert theo authorization failure cần nối được giả thuyết rủi ro, dữ liệu đáng tin, logic cửa sổ, vòng đời giao nhận và người xử lý. Khi các mốc và giới hạn được ghi rõ, hệ thống mới có thể chứng minh cảnh báo vừa được tạo đúng vừa có khả năng dẫn tới hành động phù hợp.

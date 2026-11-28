# False positive và false negative trong IDS/IPS: Đo lường, phân tích và tinh chỉnh phát hiện xâm nhập

## 1. Vì sao IDS/IPS có thể cảnh báo sai hoặc bỏ sót?

**Intrusion Detection System (IDS)** phân tích dữ liệu từ mạng hoặc hệ thống để phát hiện dấu hiệu tấn công, hành vi bất thường hay vi phạm chính sách và phát cảnh báo. **Intrusion Prevention System (IPS)** có thể thực thi hành động ngăn chặn trực tiếp, chẳng hạn loại bỏ gói hoặc chặn kết nối, khi chính sách và vị trí triển khai cho phép. Cả hai đều phải ra quyết định từ tín hiệu không hoàn hảo: gói tin, luồng mạng, bản ghi, dấu hiệu giao thức, chữ ký hoặc mô hình thống kê.

Trong chương **IDS và IPS** của học phần **SECURITY_NETWORK_SECURITY**, hai loại sai số quan trọng nhất là:

- **False positive (FP, dương tính giả):** hệ thống kết luận có hành vi cần cảnh báo/chặn, trong khi thực tế đó là hoạt động hợp lệ hoặc không thuộc hành vi nguy hiểm được định nghĩa.
- **False negative (FN, âm tính giả):** thực tế xảy ra hành vi thuộc phạm vi cần phát hiện, nhưng hệ thống không tạo cảnh báo/chặn phù hợp trong thời gian cần thiết.

Đây là bài học nền tảng cho việc **phân tích lưu lượng, mô hình hóa mối đe dọa, giám sát xâm nhập, xây dựng firewall/IPS policy và thiết kế kiến trúc mạng an toàn**. FP có thể khiến SOC quá tải hoặc IPS làm gián đoạn dịch vụ. FN khiến hành vi nguy hiểm không được nhận biết kịp thời, tạo cơ hội cho tấn công kéo dài hoặc di chuyển ngang.

**Kết quả học tập:** sau bài này, bạn có thể đọc confusion matrix, tính precision/recall/FPR/FNR, giải thích ảnh hưởng của tỷ lệ tấn công thực tế, tìm nguyên nhân FP/FN, đề xuất phương án tuning có kiểm soát và tổ chức đo lường chất lượng phát hiện theo môi trường vận hành.

## 2. Phân biệt thực tế, kết luận của hệ thống và hành động IPS

Trước khi gọi một sự kiện là “sai”, phải xác định **điều gì được coi là hành vi cần phát hiện**. Một tổ chức có thể chọn phát hiện mọi lần quét cổng ngoài lịch; tổ chức khác chỉ cảnh báo quét có dấu hiệu xâm nhập. Cùng một traffic có thể là hoạt động bảo mật được cấp phép hoặc hành động không được phép, tùy bối cảnh.

| Trạng thái thực tế | IDS/IPS kết luận | Phân loại |
| --- | --- | --- |
| Có hành vi nguy hiểm thuộc định nghĩa | Có phát hiện đúng | **True positive (TP)** |
| Không có hành vi nguy hiểm thuộc định nghĩa | Có phát hiện nhầm | **False positive (FP)** |
| Có hành vi nguy hiểm thuộc định nghĩa | Không phát hiện | **False negative (FN)** |
| Không có hành vi nguy hiểm thuộc định nghĩa | Không phát hiện | **True negative (TN)** |

Lưu ý hai tầng kết quả:

1. **Phát hiện:** công cụ tạo alert hoặc kết luận một luồng đáng ngờ. Đây là kết quả phân loại.
2. **Ngăn chặn:** IPS quyết định drop, reject, reset hoặc áp dụng hành động khác. Đây là kết quả thực thi.

Một **TP alert** không có nghĩa tấn công đã bị chặn. Một gói bị IPS drop chưa chứng minh toàn bộ chiến dịch tấn công đã thất bại. Một rule chặn traffic hợp lệ là **false positive ở chính sách chặn**, ngay cả khi hệ thống chỉ ghi log “blocked” mà không có alert riêng. Khi đo chất lượng, phải ghi rõ đang đánh giá **alert, session, event, packet hay kết quả ngăn chặn**.

### 2.1. Ví dụ trực quan

**FP:** hệ thống giám sát phát alert “quét cổng” khi phần mềm kiểm kê nội bộ chạy theo lịch đã phê duyệt. Nếu policy coi kiểm kê được phép là bình thường, đó là FP của rule phát hiện.

**FN:** một ứng dụng đã bị khai thác qua kết nối HTTPS hợp lệ, nhưng sensor IDS đặt trước điểm kết thúc TLS chỉ thấy dữ liệu mã hóa; không có nguồn log ứng dụng hoặc khả năng phát hiện phù hợp nên không tạo alert.

**TP:** IDS xác định đúng chuỗi kết nối có dấu hiệu khai thác trên một máy lab, dựa trên lưu lượng và dấu vết được xác nhận trong kiểm thử.

**TN:** một phiên truy cập web bình thường không phát cảnh báo; để kết luận thực sự là TN, cần có dữ liệu xác minh rằng phiên đó không chứa hành vi được xem là dương tính.

## 3. Confusion matrix: Khung đo lường FP/FN

Confusion matrix (ma trận nhầm lẫn) đặt **nhãn thực tế** ở một trục và **kết luận của bộ phát hiện** ở trục kia:

| | Thực tế có tấn công | Thực tế không có tấn công |
| --- | ---: | ---: |
| **Phát hiện/cảnh báo** | TP | FP |
| **Không phát hiện/cảnh báo** | FN | TN |

Một bộ dữ liệu gồm **10.000 luồng mạng đã có nhãn kiểm chứng**, trong đó 100 luồng có hành vi cần phát hiện và 9.900 luồng bình thường. Giả sử IDS phát hiện 80 luồng tấn công, bỏ sót 20 luồng, cảnh báo nhầm 198 luồng bình thường.

| | Tấn công thật (100) | Bình thường (9.900) | Tổng |
| --- | ---: | ---: | ---: |
| Cảnh báo | **TP = 80** | **FP = 198** | 278 |
| Không cảnh báo | **FN = 20** | **TN = 9.702** | 9.722 |
| Tổng | 100 | 9.900 | **10.000** |

Ví dụ số học này chỉ nhằm học cách tính, không phải benchmark cho một sản phẩm IDS/IPS thực tế.

### 3.1. Các công thức quan trọng

| Chỉ số | Công thức | Ý nghĩa |
| --- | --- | --- |
| **Recall / TPR / Sensitivity** | TP / (TP + FN) | Trong các trường hợp nguy hiểm thật, phát hiện được bao nhiêu? |
| **FNR / Miss rate** | FN / (TP + FN) | Trong các trường hợp nguy hiểm thật, bỏ sót bao nhiêu? |
| **Precision / PPV** | TP / (TP + FP) | Trong các cảnh báo, bao nhiêu là nguy hiểm thật? |
| **FPR / False alarm rate** | FP / (FP + TN) | Trong các trường hợp bình thường, bao nhiêu bị cảnh báo nhầm? |
| **Specificity / TNR** | TN / (TN + FP) | Trong các trường hợp bình thường, bao nhiêu được nhận diện đúng? |
| **Accuracy** | (TP + TN) / (TP + FP + FN + TN) | Tỷ lệ kết luận đúng trên toàn bộ mẫu |
| **F1-score** | 2 × Precision × Recall / (Precision + Recall) | Trung bình điều hòa giữa precision và recall |

Các chỉ số có mẫu số bằng 0 cần được ghi là **không xác định/không áp dụng**, thay vì tùy ý báo 0% hoặc 100%. Với bộ dữ liệu có nhiều loại đe dọa, nên tính riêng theo lớp hoặc chiến thuật thay vì chỉ một con số tổng hợp.

Từ ví dụ trên:

~~~text
Recall = 80 / (80 + 20)              = 80%
FNR = 20 / (80 + 20)                 = 20%
Precision = 80 / (80 + 198)          ≈ 28,78%
FPR = 198 / (198 + 9702)             = 2%
Specificity = 9702 / (198 + 9702)    = 98%
Accuracy = (80 + 9702) / 10000       = 97,82%
F1 = 2 × 80 / (2 × 80 + 198 + 20)    ≈ 42,33%
~~~

**Điều đáng chú ý:** accuracy đạt **97,82%**, nhưng chỉ khoảng **29% số alert** phản ánh sự kiện dương tính thật. Chỉ số accuracy cao có thể che giấu chất lượng cảnh báo kém khi phần lớn lưu lượng là bình thường.

### 3.2. Precision và recall không thể thay thế nhau

- **Recall cao** giúp bỏ sót ít tấn công thật, nhưng bộ phát hiện có thể tạo nhiều FP.
- **Precision cao** giúp analyst ít phải xử lý alert sai, nhưng nếu hệ thống chỉ cảnh báo các dấu hiệu rõ rệt nhất thì có thể bỏ qua nhiều tấn công.
- **FPR thấp** vẫn có thể gây lượng alert lớn khi số sự kiện bình thường quá nhiều.

Không nên nói một rule “tốt” chỉ vì recall hoặc precision cao. Cần xét thêm mức độ nghiêm trọng của đe dọa, số lượng sự kiện thực tế, khả năng xử lý alert, độ trễ phát hiện và mức tác động khi IPS chặn nhầm.

## 4. Base rate: Vì sao FPR nhỏ vẫn làm SOC quá tải?

Trong mạng doanh nghiệp, tỷ lệ phiên hợp lệ thường vượt xa tỷ lệ phiên có hành vi tấn công xác nhận được. Điều này tạo ra **base-rate effect**: dù bộ phát hiện khá chính xác trên dữ liệu cân bằng, số lượng cảnh báo nhầm có thể lớn khi áp dụng trong môi trường hiếm có tấn công.

Giả sử mỗi ngày sensor quan sát **1.000.000** luồng, trong đó chỉ **100** có hành vi nguy hiểm theo định nghĩa. Nếu **TPR = 90%** và **FPR = 0,1%**:

~~~text
Positive thật:       100
Negative thật:   999.900
True positive:        90  (90% của 100)
False negative:       10
False positive:    ≈ 1.000  (0,1% của 999.900; làm tròn)
Tổng alert:        ≈ 1.090
Precision:         ≈ 8,3%
~~~

**Kết quả:** trên 1.000 cảnh báo có thể chỉ một phần nhỏ là tấn công thật, dù tỷ lệ FP trên luồng bình thường rất thấp. Trong vận hành, điều này dẫn tới mệt mỏi cảnh báo (*alert fatigue*), quá tải triage và nguy cơ bỏ sót một TP nằm giữa nhiều FP.

Khi dự báo tải SOC, hãy xét **số alert tuyệt đối theo giờ/ngày**, lượng alert trùng lặp, mức độ ưu tiên và thời gian xử lý trung bình, thay vì chỉ dùng FPR phần trăm.

## 5. Nguồn gây false positive

### 5.1. Chữ ký quá rộng

Signature phát hiện dựa trên mẫu byte, header, chuỗi giao thức hoặc chuỗi hành vi. Một mẫu quá chung như “nhiều kết nối tới các cổng khác nhau” có thể trùng với quét bảo mật hợp lệ, monitoring, service discovery hoặc ứng dụng hoạt động bất thường nhưng không độc hại.

**Hướng xử lý:** bổ sung điều kiện ngữ cảnh như hướng luồng, vai trò nguồn/đích, protocol state, tập cổng liên quan, tần suất và cửa sổ thời gian. Không thêm ngoại lệ dựa trên một IP duy nhất khi chưa hiểu nguyên nhân.

### 5.2. Không có baseline theo môi trường

Một hệ thống giám sát xem lượng truy vấn DNS cao là đáng ngờ, trong khi DNS resolver hoặc ứng dụng có kiến trúc microservices thường gửi nhiều truy vấn hợp lệ. Ngược lại, cùng ngưỡng có thể quá lỏng với một máy trạm bình thường.

**Hướng xử lý:** xây baseline theo nhóm tài sản (workstation/server/resolver), thời gian, môi trường và chức năng. Ghi nhận thay đổi hạ tầng hoặc sản phẩm để tránh coi mọi đợt triển khai mới là tấn công.

### 5.3. Thiếu thông tin sở hữu và lịch vận hành

Scanner kiểm kê, kiểm thử xâm nhập được cấp phép, sao lưu, nâng cấp và tác vụ batch có thể tạo pattern giống hành vi xâm nhập.

**Hướng xử lý:** đối chiếu với lịch change, allowlist có phê duyệt và thời hạn, tài khoản quản trị cũng như danh mục công cụ. Vẫn cần theo dõi hoạt động bất thường vượt ngoài phạm vi nhiệm vụ được phê duyệt.

### 5.4. Giải mã/phân tích giao thức khác thực tế

NAT, reverse proxy, load balancer, encapsulation, các biến thể protocol và dữ liệu lỗi có thể làm parser hiểu sai nguồn, đích hoặc nội dung. Một alert gắn với HTTP header có thể do WAF/proxy chèn vào, không phải do client gửi nguyên bản.

**Hướng xử lý:** ghi vị trí sensor, TLS termination, IP trước/sau NAT, protocol version và log tương ứng ở application/firewall.

### 5.5. Phát hiện bất thường thiếu dữ liệu bối cảnh

Anomaly detection có thể coi spike lưu lượng là bất thường mặc dù đó là campaign marketing, tải báo cáo cuối tháng hoặc quá trình khởi động lại hệ thống.

**Hướng xử lý:** kết hợp lịch hoạt động, nhật ký triển khai, loại dịch vụ, danh tính nguồn và mức tác động. Alert bất thường là **tín hiệu điều tra**, không tự động chứng minh có tấn công.

## 6. Nguồn gây false negative

### 6.1. Sensor không nhìn thấy luồng

IDS gắn ở cổng mirror của switch có thể bỏ sót traffic do sai cấu hình SPAN/TAP, quá tải mirror, packet loss, thay đổi route, lưu lượng nội bộ không qua sensor hoặc ứng dụng chạy trên mạng ảo/cloud khác.

**Hướng xử lý:** kiểm tra topology và đường đi hai chiều, counters mất gói, hiệu lực SPAN/TAP, luồng east-west, các interface tunnel và đường bypass.

### 6.2. Nội dung bị mã hóa

Khi traffic HTTPS đi qua sensor trước TLS termination, sensor thường không thể đọc URL, body hoặc truy vấn ứng dụng được mã hóa. Một số metadata như địa chỉ IP, port, thời gian, đặc điểm bắt tay TLS có thể vẫn quan sát được tùy giao thức và cấu hình, nhưng không đủ phát hiện mọi loại khai thác.

**Hướng xử lý:** đặt nguồn phát hiện tại điểm có thể nhìn nội dung hợp pháp (WAF, reverse proxy, ứng dụng), kết hợp log và telemetry endpoint. Nếu cân nhắc TLS inspection, cần đánh giá hiệu năng, quyền truy cập dữ liệu và quản trị khóa/chứng chỉ.

### 6.3. Kỹ thuật tấn công nằm ngoài chữ ký hoặc phạm vi rule

Một rule chỉ nhận dạng một biến thể đã biết có thể bỏ qua biến thể khác, kỹ thuật mới, payload được mã hóa trong ứng dụng hoặc một hành động lạm dụng nghiệp vụ không giống khai thác kỹ thuật.

**Hướng xử lý:** kết hợp phát hiện theo chữ ký, hành vi, log ứng dụng, danh tính và threat intelligence đã xác minh; định kỳ kiểm tra độ bao phủ đối với các kịch bản rủi ro thực tế.

### 6.4. Rule bị tắt, suppress quá rộng hoặc threshold không phù hợp

Để giảm FP, nhóm vận hành có thể tắt hoàn toàn một signature hoặc bỏ qua toàn bộ subnet nội bộ. Điều này có thể tạo **điểm mù FN** khi hành vi xấu xuất hiện ngay trong nguồn hoặc traffic được miễn.

**Hướng xử lý:** giới hạn ngoại lệ theo **nguồn, đích, chức năng, điều kiện, lịch và thời hạn**, có chủ sở hữu và kiểm tra lại khả năng phát hiện. Một rule có độ nhạy thấp hơn vẫn có thể giữ telemetry phụ trợ để phục vụ truy vết.

### 6.5. Giới hạn tài nguyên và thời gian

Sensor quá tải có thể drop packet; queue xử lý alert đầy; rule engine bị giới hạn số luồng hoặc không tái lắp ghép nội dung đầy đủ; log bị mất do pipeline. Mặc dù phát hiện đúng trên tập thử nhỏ, triển khai thực tế vẫn có thể sinh FN.

**Hướng xử lý:** kiểm thử ở mức tải đại diện, giám sát packet drops, queue depth, stream reassembly, CPU/RAM và độ trễ alert; theo dõi cả **sensor health**.

### 6.6. Quyết định phụ thuộc định nghĩa sự kiện

Nếu detection use case chỉ định “phát hiện khai thác thành công”, một alert về **nỗ lực** khai thác chưa chắc là TP theo nhãn đó; nó có thể là TP cho use case “phát hiện thử khai thác”. Phải định nghĩa *đối tượng và thời điểm cần phát hiện* trước khi đánh giá FN.

## 7. IDS và IPS chịu chi phí FP/FN khác nhau như thế nào?

| Khía cạnh | IDS (giám sát/cảnh báo) | IPS (can thiệp/chặn) |
| --- | --- | --- |
| FP thường gây | Alert noise, thời gian triage, báo cáo sai, mất tin cậy vào cảnh báo | Chặn giao dịch hợp lệ, mất kết nối, gián đoạn ứng dụng |
| FN thường gây | Bỏ lỡ tín hiệu điều tra hoặc phát hiện quá trễ | Không chặn được traffic nguy hiểm cần chặn |
| Mức thận trọng khi bật rule | Có thể thử alert-only và đánh giá trong SOC | Cần đánh giá tác động trước khi chuyển sang drop/reject |
| Chế độ đo cần xem | Chất lượng alert và khả năng phát hiện thực tế | Chất lượng phát hiện **và** hậu quả của quyết định chặn |
| Khả năng khắc phục | Tuning, enrichment, correlation, triage | Tuning cộng rollback, bypass/fail mode, exception có kiểm soát |

**Ví dụ:** rule IPS nhận nhầm mẫu byte trong một API call hợp lệ là khai thác và reset phiên. Đây không chỉ là một alert giả: người dùng có thể mất giao dịch. Ngược lại, nếu IPS không chặn một kết nối nguy hiểm do được đặt sai chiều luồng, kết quả là FN ở mục tiêu ngăn chặn dù một sensor khác vẫn ghi log.

### 7.1. Fail-open và fail-closed không phải FP/FN

Khi thiết bị inline gặp sự cố, **fail-open** thường ưu tiên duy trì đường truyền bằng cách cho qua lưu lượng khi cơ chế bảo vệ không sẵn sàng; **fail-closed** có thể cắt đường truyền để duy trì ranh giới kiểm soát. Hai lựa chọn thuộc bài toán **tính sẵn sàng và mức chấp nhận rủi ro**, không phải trực tiếp là nhãn FP/FN của từng rule.

Tuy vậy, trạng thái bypass/fail-open có thể làm tăng **bỏ sót thực thi**; fail-closed có thể gây gián đoạn ngay cả khi lưu lượng hợp lệ. Cần theo dõi trạng thái thiết bị, HA, session synchronization, health checks và đường dự phòng trong vận hành.

### 7.2. Khi nào dùng alert-only trước block?

Với rule mới hoặc vừa thay đổi ngưỡng, nếu sản phẩm hỗ trợ, thường có thể:

1. Chạy trong **detection/alert-only mode** trên đúng phân đoạn có log.
2. Xác nhận mẫu phát hiện bằng PCAP hoặc log đã được phép lưu.
3. Đánh giá FP theo môi trường, dịch vụ và thời điểm.
4. Đánh giá thử nghiệm âm tính/dương tính theo kịch bản.
5. Chuyển sang IPS block có kiểm soát trên phạm vi nhỏ; có rollback và owner.

Không nên coi một thời gian “không có FP alert” là bằng chứng tuyệt đối an toàn để bật chặn: có thể chưa có lưu lượng đủ đa dạng hoặc use case ít xuất hiện.

## 8. Precision–recall trade-off và ngưỡng cảnh báo

Nhiều hệ thống anomaly detection hoặc risk scoring có **điểm tin cậy**. Chọn threshold thấp có thể thu được nhiều tình huống nguy hiểm nhưng cũng có thể làm tăng alert từ traffic bình thường. Chọn threshold cao có thể giảm FP nhưng tăng FN.

~~~mermaid
flowchart LR
    Traffic[Dữ liệu mạng / log] --> Score[Signature, heuristic hoặc risk score]
    Score --> Gate{Vượt ngưỡng phát hiện?}
    Gate -->|Có| Alert[Alert / triage]
    Gate -->|Không| Silent[Không có alert từ rule này]
    Alert --> Decide{Chính sách IPS đủ điều kiện chặn?}
    Decide -->|Có| Block[Chặn có log và rollback]
    Decide -->|Không| Observe[Quan sát / điều tra]
~~~

Đây là **mô hình khái niệm**: signature cố định không nhất thiết có điểm số liên tục, và một số IPS áp dụng hành động trực tiếp mà không đi qua mô hình chấm điểm trên.

| Thay đổi | FP có thể | FN có thể | Rủi ro khi triển khai |
| --- | --- | --- | --- |
| Hạ ngưỡng cảnh báo | Tăng | Giảm | SOC quá tải; IPS có nguy cơ chặn nhầm |
| Nâng ngưỡng cảnh báo | Giảm | Tăng | Bỏ qua hành vi nguy hiểm tinh vi |
| Thêm xác minh giao thức/ngữ cảnh | Giảm nếu điều kiện đúng | Có thể tăng nếu điều kiện quá hẹp | Bỏ sót biến thể thật |
| Thêm dữ liệu xác thực/asset context | Có thể giảm | Có thể giảm | Phụ thuộc độ chính xác của dữ liệu bổ sung |
| Tắt toàn bộ signature gây nhiễu | Giảm mạnh | Có thể tăng mạnh | Tạo khoảng trống phát hiện |

Sự thay đổi FP/FN thực tế **không phải lúc nào cũng đơn điệu** nếu dữ liệu hoặc pipeline thay đổi cùng lúc. Hãy đo cùng một bộ thử có nhãn và kiểm tra traffic production đại diện, thay vì suy luận chỉ từ hướng thay đổi tham số.

### 8.1. ROC và Precision–Recall

- Đường **ROC** biểu diễn TPR so với FPR ở nhiều ngưỡng.
- Đường **Precision–Recall** biểu diễn độ chính xác của alert so với khả năng tìm ra dương tính thật.
- Khi tấn công thật hiếm và tập bình thường rất lớn, **Precision–Recall** thường trực quan hơn cho tải xử lý alert, vì thể hiện hậu quả của base rate.

Một mô hình có điểm ROC tốt vẫn có thể tạo precision thấp trong điều kiện production có rất ít positive. Do vậy nên báo cáo kết quả trên dữ liệu sát tỷ lệ xuất hiện thực tế và theo từng nhóm đe dọa.

## 9. Ground truth: Làm sao biết một cảnh báo đúng hay sai?

**Ground truth** là nhãn thực tế dùng để so sánh với kết luận của detector. Trong môi trường bảo mật, nhãn có thể khó xác định: nhiều nỗ lực xâm nhập không dẫn đến compromise; có traffic lành tính nhưng bất thường; và có hoạt động nguy hiểm không để lại dấu vết đầy đủ.

### 9.1. Các nguồn xác minh

| Nguồn | Hỗ trợ xác minh gì? | Giới hạn |
| --- | --- | --- |
| PCAP hoặc flow record đã thu hợp lệ | Địa chỉ, port, thời gian, đặc điểm giao thức, chuỗi kết nối | Có thể không thấy nội dung mã hóa, bị mất gói hoặc sai điểm nhìn |
| Log WAF/reverse proxy/ứng dụng | HTTP path, status, session, request ID, kết quả xử lý | Chỉ phản ánh tầng và phạm vi log; có thể thiếu hoặc chứa dữ liệu nhạy cảm |
| EDR/host telemetry | Tiến trình, file, kết nối, hành vi sau khai thác | Tùy độ bao phủ endpoint và độ tin cậy sensor |
| Log VPN/Identity | Người dùng/thiết bị đăng nhập, nguồn truy cập | Đăng nhập thành công không chứng minh hành động về sau là hợp lệ |
| Change ticket / lịch quét được duyệt | Bối cảnh hoạt động kiểm thử, bảo trì | Không tự chứng minh mọi hành vi phát ra đều nằm trong phạm vi |
| Báo cáo điều tra và lab có kịch bản | Xác thực chuỗi hành vi và nhãn kiểm thử | Có thể chưa đại diện độ phức tạp production |

Một alert chưa đủ chứng cứ nên được ghi **chưa xác định (undetermined)**, không ép vào FP. Việc phân loại bừa mọi alert chưa được xác minh là FP làm sai kết quả precision; ngược lại coi mọi alert mức cao là TP cũng làm méo thống kê.

### 9.2. Đơn vị đo và phạm vi đánh giá

Trước khi lập confusion matrix, phải nêu:

1. **Đơn vị:** packet, flow, session, alert, source IP, user, host hay incident.
2. **Cửa sổ thời gian:** mỗi phút, ngày, chiến dịch, hoặc khoảng sau sự kiện.
3. **Phạm vi phát hiện:** tấn công nào, ở lớp mạng nào, theo tài sản nào.
4. **Nhãn thực tế:** ai xác minh, từ nguồn nào và mức tin cậy bao nhiêu.
5. **Quy tắc gộp:** một cuộc quét có 200 alert là 200 event hay một incident?
6. **Thời điểm kết luận:** phát hiện trong bao lâu mới được coi đạt yêu cầu?

Nếu mẫu thử có 100 tấn công nhưng hệ thống tạo 2.000 alert trùng cho 80 tấn công, không thể đưa trực tiếp 2.000 alert vào TP của một confusion matrix **theo tấn công**. Đơn vị đo phải được giữ nhất quán từ đầu đến cuối.

### 9.3. Vì sao TN và FN khó đo trong production?

Trong traffic production khổng lồ, không thể xác minh thủ công từng gói **không cảnh báo** đều bình thường. Vì vậy không thể tính chính xác FPR/FNR toàn mạng chỉ bằng cách đếm alert và số lần analyst gắn nhãn.

Một chiến lược thực tế là kết hợp:

- Bộ thử nghiệm có nhãn và các lần replay/kiểm thử được cấp phép.
- Lấy mẫu **traffic không alert** để điều tra chọn lọc.
- Kiểm tra từ endpoint/log ứng dụng hoặc threat hunting để tìm sự kiện đã bị bỏ sót.
- Phân tích incident được xác nhận để truy ngược sensor lẽ ra phải phát hiện.
- Báo cáo **phạm vi và độ bất định** của chỉ số thay vì tuyên bố con số tuyệt đối.

Các kết quả lab nên được ghi rõ là **lab detection rate**, không tự quảng bá thành tỷ lệ phát hiện mọi hành vi trên môi trường thật.

## 10. Quy trình xử lý false positive trong SOC

Một workflow triage nên có thể kiểm tra lại được:

1. **Xác định alert:** rule ID, phiên bản rule, signature, sensor, timestamp, source/destination, action và risk score nếu có.
2. **Kiểm tra điểm nhìn:** lưu lượng có qua NAT, proxy, TLS termination, VPN hoặc tunnel làm biến đổi tín hiệu không?
3. **Đối chiếu bối cảnh:** asset owner, môi trường, lịch quét được cấp phép, service dependency, tài khoản và change record.
4. **Xác minh evidence:** PCAP/log/endpoint được phép sử dụng, loại bỏ hoặc che bí mật khi chia sẻ.
5. **Gắn trạng thái:** TP, FP, chưa xác định hoặc rule không còn phù hợp use case; ghi lý do và bằng chứng.
6. **Đề xuất tuning hẹp:** ràng buộc thêm protocol state, vùng tin cậy, loại tài sản hoặc ngoại lệ có điều kiện và thời hạn.
7. **Thử hồi quy:** hoạt động hợp lệ không còn tạo FP, nhưng mẫu tấn công đại diện vẫn được phát hiện.
8. **Triển khai có kiểm soát:** kiểm tra trên test/staging hoặc alert-only, theo dõi sau thay đổi, có khả năng rollback.

### 10.1. Ví dụ: Rule phát hiện quét cổng báo nhầm inventory scanner

Giả sử một sensor ghi:

~~~text
timestamp=2026-11-28T09:20:00Z
sensor=ids-internal-lab
rule_id=LAB-PORTSCAN-01
src=192.0.2.15 dst=198.51.100.20
category=possible-port-scan
action=alert
~~~

Đây là **log giả lập**, các IP thuộc dải tài liệu. Sau khi xác minh, nhóm SOC xác định nguồn là công cụ inventory được phép, đúng lịch và đúng danh sách máy/cổng. Nếu use case chỉ cảnh báo **quét trái phép**, sự kiện có thể được gắn FP.

**Tuning có kiểm soát:** cấu hình ngoại lệ chỉ cho nguồn scanner đã quản trị, mạng đích và cửa sổ kiểm tra được phép, đồng thời giữ giám sát lưu lượng ngoài lịch hoặc vượt phạm vi. Nếu miễn toàn bộ nguồn IP bất kể hành vi, một máy scanner bị chiếm quyền có thể trở thành điểm mù nguy hiểm.

### 10.2. Không dùng allowlist như cách chữa mọi FP

Allowlist theo IP thường thuận tiện nhưng có các giới hạn: địa chỉ thay đổi theo DHCP/NAT, máy có thể bị chiếm, nhiều ứng dụng dùng chung proxy. Khi có thể, kết hợp **danh tính thiết bị, chủ sở hữu, điều kiện giao thức, nguồn thực thi và thời hạn ngoại lệ**.

Ngoại lệ phải có **owner**, lý do, phạm vi, ngày hết hạn, kênh audit và phương án quay lại rule gốc. Nếu sản phẩm chỉ cho phép suppress alert nhưng không suppress IPS drop (hoặc ngược lại), cần kiểm tra semantics trước khi áp dụng.

## 11. Quy trình tìm và giảm false negative

FN khó quan sát trực tiếp vì **không có cảnh báo**. Cần chủ động kiểm tra các kịch bản có nhãn và sự kiện đã xác minh theo threat model.

### 11.1. Đối chiếu khả năng phát hiện với kịch bản tấn công

Lập ma trận gồm nguồn, loại kỹ thuật, dữ liệu mà sensor nhìn thấy, rule/analytic kỳ vọng và mức độ ưu tiên. Có thể tham khảo **MITRE ATT&CK** để tổ chức kỹ thuật và **MITRE D3FEND** để gợi ý cơ chế phòng thủ; đây là khung kiến thức, không phải bằng chứng sản phẩm tự động phát hiện được mọi kỹ thuật đã được ánh xạ.

| Kịch bản có quyền kiểm thử | Dữ liệu cần có | Dấu hiệu kiểm chứng | Rủi ro FN |
| --- | --- | --- | --- |
| Quét cổng trong lab | NetFlow/packet metadata | Số cổng/máy đích theo cửa sổ | Sensor sai vị trí, threshold quá cao |
| Truy cập API bất thường | WAF/app log, HTTP metadata | Request, status, auth context | HTTPS mã hóa trước sensor, thiếu log ứng dụng |
| Kết nối quản trị ngoài chính sách | Firewall/VPN/identity log | Nguồn, đích, port, principal | Không có log đường VPN hoặc rule lọc sai |
| Truy vấn DNS bất thường | DNS resolver log, flow metadata | Tên miền, tần suất, client | Client dùng resolver khác hoặc DNS mã hóa |
| Di chuyển ngang giữa subnet | East-west flow/EDR, ISFW log | Kết nối mới giữa vùng tin cậy | Traffic nội bộ không qua sensor |
| Tải dữ liệu lớn bất thường | Flow metrics và quyền ứng dụng | Byte, thời gian, tài khoản | Chỉ dựa vào chữ ký payload mà không đo hành vi |

### 11.2. Kiểm chứng có kiểm soát

1. Xác định **detection objective**: ví dụ phải phát hiện một chuỗi kết nối quét lab trong 2 phút.
2. Chuẩn bị nguồn/đích lab, lịch và người phê duyệt; sử dụng dữ liệu giả hoặc bài thử đã kiểm soát.
3. Thu thập ground truth độc lập từ máy thử và endpoint, không dựa riêng vào alert.
4. Chạy bài thử, đánh dấu mốc thời gian và lượng lưu lượng dự kiến.
5. Kiểm tra sensor đã nhìn đủ dữ liệu, rule có bật và có hoạt động đúng hướng.
6. Đối chiếu alert, drop action nếu là IPS, latency và thông báo đến SOC.
7. Nếu không có alert, lần theo từng lớp: **traffic capture → parser → rule engine → alert queue → log collector → SOC**.
8. Ghi FN, nguyên nhân, đề xuất điều chỉnh và bài hồi quy sau sửa.

**Không thực hiện kiểm thử tấn công trên hệ thống ngoài phạm vi được cho phép.** Với các bài về nội dung độc hại, dùng mẫu/simulator được kiểm soát và phù hợp chính sách phòng lab thay vì phát tán mã khai thác thật.

### 11.3. Chỉ số phát hiện cần đi kèm thời gian

Ngoài recall/FNR, các tổ chức có thể theo dõi:

- **Detection latency:** thời gian từ sự kiện thực đến lúc detector tạo alert có thể sử dụng.
- **MTTD (Mean Time To Detect):** thời gian phát hiện trung bình theo phạm vi và định nghĩa nhất quán.
- **Time to triage:** thời gian từ alert đến lúc analyst bắt đầu/xác minh.
- **Coverage:** tỷ lệ tài sản, giao thức, phân đoạn và kịch bản nằm trong điểm quan sát.
- **Sensor health:** packet drops, log delivery, queue delay, rule update status.

Không gộp **mất khả năng thu thập**, **thiếu rule** và **analyst xử lý trễ** thành cùng một nguyên nhân. Mỗi mắt xích có cách khắc phục khác nhau.

## 12. Thực hành: Phân tích alert với số liệu giả lập

Trong một buổi lab được phép, nhóm vận hành đã tạo bộ dữ liệu **có nhãn** gồm 500 sự kiện: 50 sự kiện nguy hiểm và 450 sự kiện lành tính. Detector đưa ra 70 alert, gồm 40 TP và 30 FP.

### 12.1. Lập confusion matrix

Từ dữ liệu:

~~~text
TP = 40
FP = 30
Positive thật = 50  => FN = 50 - 40 = 10
Negative thật = 450 => TN = 450 - 30 = 420

Recall = 40 / 50 = 80%
FNR = 10 / 50 = 20%
Precision = 40 / 70 ≈ 57,14%
FPR = 30 / 450 ≈ 6,67%
Specificity = 420 / 450 ≈ 93,33%
Accuracy = (40 + 420) / 500 = 92%
F1 = 80 / (80 + 30 + 10) ≈ 66,67%
~~~

**Câu hỏi phân tích:** detector có tạo được tất cả alert cần thiết không? Không: bỏ sót 10/50 sự kiện nguy hiểm. Nhưng cũng không thể giảm FP bằng cách tắt toàn bộ rule nếu điều đó khiến những 40 TP hiện tại bị bỏ lỡ.

### 12.2. Đọc một log JSON minh họa

~~~json
{
  "timestamp": "2026-11-28T09:20:00Z",
  "sensor": "ids-internal-lab",
  "event_type": "alert",
  "src_ip": "192.0.2.15",
  "dest_ip": "198.51.100.20",
  "proto": "TCP",
  "dest_port": 443,
  "alert": {
    "signature_id": 1000001,
    "signature": "LAB: repeated connections to service",
    "severity": 3
  }
}
~~~

Log trên là **ví dụ do bài học tạo ra**, không khẳng định một cảm biến cụ thể xuất chính xác mọi field như thế. Bản ghi cho biết alert xuất hiện ở đâu và cho luồng nào; **không chứa nhãn ground truth**. Để xác định TP/FP, hãy đối chiếu lịch vận hành, ứng dụng, lưu lượng và dấu vết endpoint.

Một số câu lệnh đọc log phù hợp trên **máy lab có quyền truy cập**:

~~~bash
# Hiển thị các event có loại alert từ tệp JSON Lines giả định.
# jq sẽ không có kết quả nếu file hoặc field không đúng định dạng.
jq 'select(.event_type == "alert") | {timestamp, src_ip, dest_ip, alert}' lab-eve.json

# Đếm số alert theo signature_id; đây chưa phải đếm TP/FP.
jq -r 'select(.event_type == "alert") | .alert.signature_id' lab-eve.json |
  sort | uniq -c | sort -nr
~~~

Tệp **lab-eve.json** là dữ liệu do nhóm thực hành chuẩn bị, không phải một file log chắc chắn tồn tại trên hệ thống. Nếu dùng Suricata/Zeek hoặc SIEM, tên trường và câu lệnh phân tích cần điều chỉnh cho đúng schema. Lưu lượng và log có thể chứa thông tin nhạy cảm, nên chỉ chia sẻ trong phạm vi được phép và làm sạch trước khi gửi.

### 12.3. So sánh hai phiên bản rule

Giả sử cùng một bộ 500 sự kiện có nhãn được đánh giá lại:

| Chỉ số | Rule A | Rule B |
| --- | ---: | ---: |
| TP | 40 | 35 |
| FN | 10 | 15 |
| FP | 30 | 8 |
| TN | 420 | 442 |
| Precision | 57,14% | 81,40% |
| Recall | 80,00% | 70,00% |
| FPR | 6,67% | 1,78% |

**Diễn giải:** Rule B giảm nhiều FP và tăng precision, nhưng bỏ sót thêm 5 trường hợp tấn công. Việc chọn A hay B phụ thuộc **mức nghiêm trọng của 5 trường hợp bị bỏ sót**, mục đích detector, tải SOC và hậu quả chặn nhầm nếu chạy ở chế độ IPS. Một chiến lược khác có thể giữ rule nhạy ở chế độ alert và chỉ chuyển các trường hợp có thêm ngữ cảnh đáng tin sang block.

## 13. Kiến trúc phòng vệ nhiều lớp giảm tác động của FP/FN

Một IDS/IPS đơn lẻ không nhìn thấy hết traffic hoặc mọi dạng khai thác. Học phần **SECURITY_NETWORK_SECURITY** kết hợp nhiều lớp phòng vệ giúp giảm tác động khi một detector nhầm lẫn:

~~~mermaid
flowchart LR
    Endpoint[Endpoint/Workload] --> Seg[Segmentation + Host firewall]
    Seg --> ISFW[Internal firewall + IDS/IPS]
    ISFW --> Proxy[WAF / Reverse proxy / DNS security]
    Proxy --> App[Ứng dụng + Xác thực]
    Endpoint -. Telemetry .-> SOC[SOC / SIEM / Detection engineering]
    ISFW -. Flow & alert logs .-> SOC
    Proxy -. HTTP/DNS logs .-> SOC
    App -. Auth/app logs .-> SOC
    SOC --> Review[Investigation + Tuning + Regression tests]
~~~

Sơ đồ minh họa **các lớp chức năng**; kết nối thực tế có thể khác tùy hướng luồng. Ý nghĩa của defense in depth:

- **Segmentation và firewall:** hạn chế nơi attacker có thể giao tiếp, kể cả khi IDS bỏ sót.
- **WAF và xác thực:** nhìn ngữ cảnh HTTP/người dùng mà network IDS có thể không đọc được khi traffic mã hóa.
- **VPN và kiểm soát truy cập:** xác định đường truy cập hợp lệ; chỉ có VPN không tự chứng minh hoạt động sau kết nối an toàn.
- **DNS security:** bổ sung tín hiệu về truy vấn và tên miền bất thường; cần xét DNS mã hóa và resolver được sử dụng.
- **EDR và host telemetry:** phát hiện hành vi tiến trình sau khi kết nối mạng vượt qua một lớp phát hiện.
- **SOC và quản trị rule:** đưa bằng chứng xác minh trở lại vòng đời tuning để giảm cả FP lẫn FN.

Không phải cứ bổ sung nhiều hệ thống là chất lượng tự động tốt hơn. Nhiều sensor có thể báo trùng một sự kiện; thiếu correlation làm tăng **số alert**, không tăng số incident được xác minh.

## 14. Quy trình quản lý chất lượng IDS/IPS theo thời gian

### 14.1. Trước triển khai

1. Viết detection use case rõ ràng, gắn với threat model và tài sản cần bảo vệ.
2. Xác nhận sensor nhìn thấy luồng liên quan và log được chuyển đầy đủ.
3. Xác định tiêu chí TP/FP/FN, đơn vị đo, độ trễ cho phép và bộ dữ liệu kiểm thử.
4. Đánh giá rule trên traffic hợp lệ đa dạng lẫn kịch bản nguy hiểm được phép thử.
5. Chọn hành động alert, drop hay reject theo mức tin cậy và chi phí ảnh hưởng nghiệp vụ.
6. Thiết kế rollback, chế độ hoạt động khi thiết bị lỗi và owner chịu trách nhiệm.

### 14.2. Sau triển khai

1. Theo dõi số alert tuyệt đối, tỷ lệ xác minh TP/FP và trạng thái chưa xác định.
2. Đo sensor health, mất gói, log delivery và độ trễ đến hệ thống điều tra.
3. Điều tra incident đã được xác nhận để phát hiện những FN trước đó.
4. Tinh chỉnh rule dựa trên bằng chứng, tránh ngoại lệ quá rộng hoặc vĩnh viễn.
5. Chạy lại bộ thử hồi quy khi thay phiên bản rule, parser, traffic policy hoặc topology.
6. Theo dõi ảnh hưởng tới ứng dụng khi IPS chặn và kiểm tra false blocking.
7. Rà soát định kỳ rule không có hit, rule quá nhiễu và vùng tài sản chưa có coverage.

### 14.3. Báo cáo chỉ số kèm phạm vi và độ tin cậy

Một báo cáo nên có:

| Thành phần | Ví dụ cách ghi |
| --- | --- |
| Phạm vi | IDS tại mạng ứng dụng; traffic IPv4/IPv6 của các subnet được chọn |
| Thời gian đo | 7 ngày production + bộ thử lab có nhãn |
| Quy mô | Số luồng, alert, incident, quy tắc được đánh giá |
| Nhãn | TP/FP/undetermined; phương pháp đối chiếu |
| Chỉ số | Precision trên alert đã xác minh; recall trên bộ thử có nhãn |
| Rủi ro và điểm mù | TLS chưa giải mã, SPAN packet loss, mạng bypass, log thiếu |
| Thay đổi | Rule ID, phiên bản, người duyệt, kết quả hồi quy, ngày áp dụng |

Không trình bày **precision từ các alert đã được triage** như thể đó là precision của mọi traffic. Nếu chỉ điều tra alert mức cao, số liệu có **selection bias**. Không báo FNR production chính xác khi chưa có cơ sở ước lượng số sự kiện bị bỏ sót.

## 15. Những hiểu lầm cần tránh

| Nhận định sai | Điều cần hiểu |
| --- | --- |
| “IDS có accuracy 99% nên cảnh báo rất đáng tin.” | Khi tấn công hiếm, precision vẫn có thể rất thấp. |
| “FPR 1% là chỉ 1% số alert bị nhầm.” | FPR tính trên **tất cả negative thật**, khác với tỷ lệ FP trong tổng alert. |
| “Không có alert nghĩa là không có tấn công.” | Có thể là FN, thiếu sensor coverage, encryption hoặc rule bị tắt. |
| “Alert mức critical là TP.” | Severity/priority không thay thế bằng chứng ground truth. |
| “Thấy nhiều alert nghĩa là phát hiện tốt.” | Có thể là duplicate hoặc FP, cần incident correlation và nhãn. |
| “Tắt rule nhiều FP sẽ luôn giúp hệ thống tốt hơn.” | Có thể làm tăng FN và bỏ mất detection use case quan trọng. |
| “Có TP alert nghĩa là IPS đã chặn được tấn công.” | Phát hiện và thực thi ngăn chặn là hai kết quả riêng. |
| “Bật IPS block ngay khi rule tạo alert.” | FP trong chế độ inline có thể gây gián đoạn nghiệp vụ. |
| “Có alert log thì chắc chắn sensor không mất gói.” | Phải theo dõi capture drops, queue và pipeline telemetry. |
| “Mọi traffic không được cảnh báo là TN.” | Không thể gán TN nếu chưa có cách xác minh nhãn thực tế. |
| “Traffic mã hóa đồng nghĩa hoàn toàn không thể phát hiện.” | Có thể còn metadata và log tại điểm kết thúc TLS, nhưng không phải nội dung nào cũng quan sát được. |

## 16. Câu hỏi tự kiểm tra

**Tình huống 1.** Một sensor tạo 300 alert. SOC xác minh 90 alert là TP, 160 là FP, 50 chưa đủ bằng chứng. Có được nói precision bằng 90/300 không? 

**Gợi ý:** Không nên kết luận precision của toàn bộ 300 alert như vậy. Với **250 alert đã xác minh**, tỷ lệ TP xác minh được là 90/250 = 36%. Phải báo riêng **50 alert chưa xác định**, và không coi 90/300 là một phép đo precision đầy đủ.

**Tình huống 2.** Một detector có FPR chỉ 0,1%, vì sao vẫn có thể phát hàng nghìn alert sai mỗi ngày?

**Gợi ý:** Lượng lưu lượng bình thường quá lớn; nhân FPR với số negative thật có thể cho số FP tuyệt đối cao.

**Tình huống 3.** IDS nhận traffic từ một VLAN người dùng nhưng không thấy kết nối giữa hai pod ở cùng node Kubernetes. Đó là vấn đề độ nhạy signature hay coverage?

**Gợi ý:** Có thể là **coverage**: luồng không đi qua điểm quan sát; cần kiểm tra CNI/overlay/host và vị trí sensor trước khi tuning rule.

**Tình huống 4.** Một rule phát alert về việc kiểm kê host hợp lệ. Điều chỉnh nào ít rủi ro hơn: tắt rule toàn mạng hay ngoại lệ cụ thể có thời hạn?

**Gợi ý:** Ngoại lệ giới hạn đúng công cụ, phạm vi, lịch được phép và được giám sát sẽ ít tạo điểm mù hơn.

**Tình huống 5.** Rule B có precision cao hơn A nhưng recall thấp hơn. Nên chọn rule nào để chặn tự động tại IPS?

**Gợi ý:** Cần đánh giá **hậu quả của FP block**, mức nghiêm trọng của FN, loại dịch vụ và thử nghiệm trên traffic đại diện; không thể quyết định chỉ từ một chỉ số.

**Tình huống 6.** Một API bị khai thác qua HTTPS nhưng network IDS không cảnh báo. Từng bước điều tra nguyên nhân gì?

**Gợi ý:** Kiểm tra sensor thấy luồng không, TLS termination, nguồn dữ liệu cần để phát hiện, parser, rule coverage, tình trạng sensor, log pipeline và alert delivery; sau đó cập nhật detection ở WAF/app/EDR nếu phù hợp.

## 17. Tổng kết

**False positive** là phát hiện/chặn nhầm hoạt động bình thường; **false negative** là bỏ sót hành vi phải phát hiện. Hai lỗi này tác động khác nhau lên IDS và IPS, đặc biệt khi IPS chạy inline và có thể ngắt dịch vụ hợp lệ.

Muốn đo lường có ý nghĩa, cần **định nghĩa rõ nhãn, đơn vị, cửa sổ thời gian và điểm quan sát**, sau đó dùng confusion matrix với precision, recall, FPR và FNR. Hãy nhớ rằng **base rate và coverage** có thể khiến một rule trông tốt trong lab nhưng tạo nhiều alert sai hoặc bỏ sót khi vận hành thật.

Trong **SECURITY_NETWORK_SECURITY**, chất lượng phát hiện được nâng lên bằng sự phối hợp giữa **sensor đúng vị trí, phân đoạn, firewall, VPN, WAF, DNS/ứng dụng, host telemetry, SOC và quy trình tuning có hồi quy**. Đích đến là phát hiện những nguy cơ có ý nghĩa đủ sớm, giảm tác động của cảnh báo sai và chứng minh chất lượng bằng dữ liệu có nhãn phù hợp, thay vì bằng số lượng alert đơn thuần.

### Tài liệu tra cứu thêm

- **NIST SP 800-94 — Guide to Intrusion Detection and Prevention Systems (IDPS):** khái niệm, triển khai, tuning và vận hành IDS/IPS.
- **NIST SP 800-61 — Computer Security Incident Handling Guide:** quy trình xử lý sự cố và đối chiếu bằng chứng điều tra.
- **MITRE ATT&CK:** phân loại hành vi đối thủ và xác định kịch bản phát hiện; cần xác minh coverage riêng cho từng môi trường.
- **MITRE D3FEND:** hệ thống kiến thức về kỹ thuật phòng thủ mạng và endpoint.
- **Suricata Documentation — Rules, Alerts, EVE JSON:** ví dụ về signature, log và trạng thái sensor.
- **Zeek Documentation:** phân tích lưu lượng dựa trên giao thức và dữ liệu log.
- **OWASP Detection and Response:** ngữ cảnh ứng dụng và phương pháp theo dõi sự kiện an ninh.

# Chọn tín hiệu và điều kiện dừng triển khai

## 1. Vì sao cần tín hiệu và điều kiện dừng?

Một lần triển khai thành công về mặt kỹ thuật chưa chắc đã tạo ra một lần phát hành an toàn. Container có thể khởi động, Pod có thể Ready và pipeline có thể báo xanh, nhưng người dùng vẫn gặp lỗi thanh toán, độ trễ tăng hoặc một luồng nghiệp vụ quan trọng bị gián đoạn.

Triển khai có kiểm soát cần trả lời hai câu hỏi:

- **Tín hiệu nào cho biết phiên bản mới đang hoạt động tốt?**
- **Khi nào phải dừng tăng lưu lượng, hủy rollout hoặc quay lui?**

Nếu không xác định trước, nhóm thường quyết định dựa trên vài log gần nhất hoặc cảm giác của người trực. Điều đó dễ bỏ sót lỗi xuất hiện chậm, phản ứng quá mức với nhiễu ngắn hạn hoặc tiếp tục rollout khi chỉ số quan trọng đã xấu đi.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, chiến lược phát hành cần có truy vết từ commit và artifact đến môi trường, cổng chất lượng, xác minh sau triển khai và rollback. Tín hiệu triển khai là bằng chứng cho quyết định tiếp tục hay dừng. Điều kiện dừng là chính sách được xác định trước để bảo vệ người dùng và hệ thống khi bằng chứng cho thấy phiên bản mới có rủi ro.

Một quy trình tốt không chỉ hỏi "deploy có xong không?" mà còn hỏi "dịch vụ có tiếp tục đáp ứng SLO và nghiệp vụ có còn đúng không?".

## 2. Triển khai tiến dần là một quá trình ra quyết định

Với rolling deployment, canary hoặc blue-green, phiên bản mới thường được đưa vào một phần hệ thống trước khi thay thế hoàn toàn phiên bản cũ. Mỗi bước tạo ra cơ hội quan sát và quyết định.

~~~mermaid
flowchart TD
    A["Xác định baseline và tiêu chí"] --> B["Preflight: kiểm tra telemetry"]
    B --> C{"Đủ dữ liệu quan sát?"}
    C -- "Không" --> H["HOLD: chưa tăng lưu lượng"]
    C -- "Có" --> D["Triển khai phạm vi nhỏ"]
    D --> E["Thu thập tín hiệu theo cửa sổ"]
    E --> F{"Đánh giá policy"}
    F -- "Đạt" --> G["Tăng dần phạm vi"]
    F -- "Cần điều tra" --> H
    F -- "Vi phạm nghiêm trọng" --> I["ABORT / ROLLBACK"]
    G --> J{"Đã đạt toàn bộ phạm vi?"}
    J -- "Chưa" --> E
    J -- "Rồi" --> K["Hoàn tất và tiếp tục theo dõi"]
    H --> E
~~~

Có thể áp dụng mô hình này cho canary, rolling update, blue-green hoặc phát hành theo feature flag. Điểm chung là mỗi lần tăng phạm vi cần có bằng chứng từ phiên bản đang được triển khai.

Các bước tăng lưu lượng như 1%, 5%, 20%, 50% rồi 100% chỉ là ví dụ. Tỷ lệ phù hợp phụ thuộc lưu lượng, mức độ rủi ro, năng lực hạ tầng, thời gian xử lý request và khả năng cô lập phiên bản. Một dịch vụ có lưu lượng thấp có thể cần thời gian quan sát dài hơn hoặc một môi trường kiểm thử đại diện trước khi mở rộng.

## 3. Phân loại tín hiệu triển khai

Không nên dựa vào một metric duy nhất. Tín hiệu cần bao phủ nhiều khía cạnh của hệ thống.

| Nhóm tín hiệu | Điều cần biết | Ví dụ |
|---|---|---|
| Trạng thái triển khai | Phiên bản mới có được khởi chạy đúng không? | Pod Ready, rollout progress, restart count, image digest |
| Sức khỏe kỹ thuật | Dịch vụ có đáp ứng và xử lý request ổn định không? | Availability, error rate, latency, throughput |
| Tài nguyên và phụ thuộc | Hệ thống có quá tải hoặc bị nghẽn ở thành phần khác không? | CPU, memory, queue lag, database connection, timeout |
| Nghiệp vụ | Người dùng có hoàn thành tác vụ quan trọng không? | Thanh toán thành công, đăng nhập, tạo đơn, tỷ lệ checkout |
| Bảo mật và dữ liệu | Có hành vi nguy hiểm hoặc sai lệch dữ liệu không? | Access denied bất thường, lỗi phân quyền, integrity check |
| Chất lượng telemetry | Có đủ dữ liệu để đưa ra quyết định không? | Metrics đến đúng, trace/log có version, sample count |

Trạng thái Pod Ready chỉ cho biết một số điều kiện sẵn sàng theo probe. Nó không chứng minh mọi API hoặc luồng nghiệp vụ đều hoạt động đúng. Tương tự, CPU thấp không đồng nghĩa dịch vụ khỏe nếu database đang từ chối kết nối.

## 4. Chọn SLI và SLO làm căn cứ

SLI (Service Level Indicator) là chỉ số đo một thuộc tính dịch vụ mà người dùng quan tâm. SLO (Service Level Objective) là mục tiêu đặt ra cho SLI trong một khoảng thời gian.

Một số SLI phổ biến:

- **Availability:** tỷ lệ request hợp lệ được xử lý thành công.
- **Latency:** thời gian xử lý request, thường xem p50, p95 và p99.
- **Correctness:** tỷ lệ kết quả hoặc dữ liệu trả về đúng.
- **Durability:** mức độ dữ liệu được lưu giữ an toàn, phù hợp với dịch vụ lưu trữ.
- **Freshness:** độ mới của dữ liệu, phù hợp với hệ thống xử lý luồng hoặc đồng bộ.

Ví dụ, một API có SLO availability 99,9% trong cửa sổ 30 ngày. Trong quá trình canary, nhóm cần theo dõi error rate của phiên bản mới và mức tiêu thụ error budget. Nếu phiên bản mới làm tốc độ tiêu thụ budget tăng nhanh, rollout cần dừng theo chính sách.

Không nên lấy SLO dài hạn rồi áp dụng máy móc thành một ngưỡng ngắn hạn. SLO giúp xác định mức dịch vụ cần bảo vệ; quyết định rollout cần thêm cửa sổ quan sát, baseline và lượng request đủ lớn.

### 4.1. Các chỉ số kỹ thuật thường dùng

- **Error rate:** số request lỗi chia cho tổng số request đủ điều kiện.
- **Latency percentile:** p95 hoặc p99 giúp phát hiện nhóm request chậm mà trung bình có thể che giấu.
- **Throughput:** số request hoặc tác vụ xử lý trong một đơn vị thời gian.
- **Availability:** tỷ lệ request được phục vụ theo định nghĩa SLI.
- **Saturation:** mức sử dụng hoặc hàng đợi của tài nguyên có giới hạn như CPU, memory, connection pool, worker hoặc queue.
- **Restart/crash rate:** số lần tiến trình hoặc container khởi động lại.
- **Queue lag:** độ trễ xử lý message hoặc công việc đang chờ.

Cần định nghĩa rõ request nào nằm trong mẫu số. Ví dụ, lỗi 4xx do người dùng nhập dữ liệu không hợp lệ có thể không được tính giống lỗi 5xx do server. Nếu mỗi nhóm dịch vụ định nghĩa error rate khác nhau, so sánh giữa phiên bản sẽ gây hiểu nhầm.

### 4.2. Error budget và burn rate

Error budget là phần lỗi dịch vụ được phép có trong mục tiêu SLO. Burn rate mô tả tốc độ tiêu thụ ngân sách lỗi so với tốc độ cho phép.

Nếu burn rate tăng cao trong khi canary đang nhận traffic, đó là tín hiệu mạnh để giữ hoặc dừng rollout. Nhiều tổ chức dùng nhiều cửa sổ thời gian để kết hợp phát hiện nhanh với xác nhận rằng vấn đề kéo dài. Cách đặt cửa sổ và ngưỡng cần dựa trên SLO, lưu lượng và độ biến động của dịch vụ.

Không nên sao chép một ngưỡng burn rate từ dịch vụ khác mà không xem xét chu kỳ request, mức độ quan trọng và khả năng chịu lỗi của chính dịch vụ.

## 5. Theo dõi golden signals và tài nguyên

Bốn golden signals thường được dùng để quan sát dịch vụ:

1. **Latency:** request mất bao lâu để hoàn tất.
2. **Traffic:** lượng request hoặc công việc hệ thống nhận.
3. **Errors:** tỷ lệ request thất bại.
4. **Saturation:** tài nguyên hoặc thành phần nào đang gần giới hạn.

Trong rollout, nên phân biệt tín hiệu của phiên bản mới với toàn dịch vụ. Nếu dashboard chỉ hiển thị tổng thể, một canary nhận 5% traffic có thể gây lỗi nhưng bị 95% traffic của phiên bản cũ che khuất.

Telemetry nên có nhãn hoặc thuộc tính để lọc theo:

- Service và môi trường.
- Version, image digest hoặc deployment revision.
- Canary/control cohort.
- Region, zone hoặc cluster.
- Endpoint hoặc nhóm nghiệp vụ.
- Release ID và thời điểm bắt đầu triển khai.

Không đưa user ID, request ID hoặc dữ liệu có cardinality rất cao vào label metric nếu không có lý do rõ ràng. Có thể dùng trace hoặc log để điều tra chi tiết.

### 5.1. Tín hiệu tài nguyên cần gắn với triệu chứng

CPU tăng có thể là bình thường khi traffic tăng. Memory tăng liên tục có thể báo hiệu leak. Queue lag tăng trong khi throughput giảm có thể cho thấy consumer không theo kịp. Database connection pool cạn có thể làm latency tăng dù CPU ứng dụng vẫn thấp.

Vì vậy, nên xem quan hệ giữa các tín hiệu thay vì dừng rollout chỉ vì một metric tài nguyên dao động ngắn hạn. Một tín hiệu tài nguyên trở thành điều kiện dừng mạnh khi nó đi kèm triệu chứng ảnh hưởng dịch vụ hoặc tiến gần giới hạn gây mất ổn định.

## 6. Chọn tín hiệu nghiệp vụ

Chỉ số kỹ thuật cho biết hệ thống hoạt động như thế nào; chỉ số nghiệp vụ cho biết người dùng có hoàn thành việc họ cần làm hay không.

Ví dụ:

| Loại dịch vụ | Tín hiệu nghiệp vụ |
|---|---|
| Thương mại điện tử | Tỷ lệ thêm giỏ, checkout thành công, đơn hàng được tạo |
| Thanh toán | Tỷ lệ authorize/capture thành công, giao dịch trùng hoặc bị từ chối bất thường |
| Đăng nhập | Tỷ lệ đăng nhập thành công, MFA completion, lỗi tạo session |
| Giao hàng | Tỷ lệ tạo vận đơn, thời gian xác nhận, sự kiện bị xử lý trùng |
| Nền tảng dữ liệu | Số bản ghi hợp lệ, độ trễ dữ liệu, tỷ lệ bản ghi bị loại |
| API nội bộ | Tỷ lệ tác vụ hoàn thành, retry, timeout giữa các dịch vụ |

Một phiên bản mới có thể trả HTTP 200 nhưng ghi dữ liệu sai, tính sai phí hoặc tạo giao dịch hai lần. Vì vậy, với luồng quan trọng cần có invariant hoặc kiểm tra tính đúng đắn của kết quả, không chỉ health endpoint.

Tín hiệu nghiệp vụ phải được định nghĩa đủ chính xác để tránh nhầm thay đổi về hành vi người dùng với lỗi triển khai. Ví dụ, tỷ lệ checkout thành công có thể giảm vì chiến dịch marketing mang về traffic khác thường; nên đối chiếu theo cohort, loại giao dịch hoặc nhóm người dùng phù hợp.

## 7. Thiết lập baseline và nhóm đối chứng

Một chỉ số chỉ có ý nghĩa khi biết mức bình thường của nó. Baseline có thể lấy từ:

- Cửa sổ ngay trước triển khai.
- Cùng khung giờ hoặc ngày trong tuần của các giai đoạn trước.
- Phiên bản ổn định đang phục vụ cùng thời điểm.
- Nhóm control không nhận phiên bản mới.
- SLO và ngưỡng vận hành đã được thống nhất.

Trong canary, so sánh phiên bản mới với control giúp giảm ảnh hưởng từ biến động traffic toàn hệ thống. Ví dụ, nếu cả hai nhóm cùng tăng latency do database bên ngoài chậm, nguyên nhân có thể không đến từ bản phát hành. Nếu chỉ canary có latency tăng, khả năng thay đổi mới gây vấn đề cao hơn.

Tuy nhiên, nhóm control cần tương đồng về loại request, region, dữ liệu và điều kiện xử lý. Nếu canary nhận request nặng hơn hoặc một nhóm người dùng khác, phép so sánh có thể sai lệch.

### 7.1. So sánh tương đối và tuyệt đối

Nên kết hợp hai loại điều kiện:

- **Ngưỡng tuyệt đối:** dịch vụ phải nằm trong giới hạn tối đa hoặc tối thiểu đã định.
- **Mức thay đổi tương đối:** phiên bản mới không được suy giảm quá mức so với baseline hoặc control.

Ví dụ, latency p95 có thể vẫn nằm dưới ngưỡng SLO nhưng tăng gấp đôi so với phiên bản ổn định. Ngược lại, một mức tăng nhỏ có thể không đáng kể khi metric vốn dao động lớn. Kết hợp cả hai giúp tránh quyết định chỉ dựa trên một con số.

## 8. Cửa sổ quan sát và lượng dữ liệu tối thiểu

Không nên quyết định tiếp tục rollout chỉ sau vài request đầu tiên. Cần đủ thời gian và số mẫu để phân biệt tín hiệu thật với nhiễu.

Cửa sổ quan sát phụ thuộc vào:

- Lưu lượng trung bình và tỷ lệ traffic canary.
- Độ trễ tối đa của request.
- Chu kỳ xử lý batch hoặc message.
- Thời gian phản ánh của metric và alert.
- Mức độ biến động theo giờ hoặc ngày.
- Độ trễ của tác động, ví dụ job chạy theo lịch hoặc báo cáo cuối ngày.

Với API có lưu lượng lớn, vài phút có thể tạo đủ mẫu cho một số tín hiệu. Với hệ thống xử lý batch hoặc giao dịch hiếm, cần thời gian dài hơn hoặc kiểm tra bổ sung trên dữ liệu thử nghiệm.

### 8.1. Minimum sample size

Nếu canary chỉ nhận rất ít request, một lỗi đơn lẻ có thể khiến error rate tăng mạnh. Nếu traffic quá thấp, không có lỗi cũng chưa chứng minh phiên bản an toàn.

Policy nên quy định lượng mẫu tối thiểu hoặc điều kiện đủ dữ liệu cho từng loại tín hiệu. Khi chưa đạt, trạng thái phải là INSUFFICIENT_DATA và rollout cần giữ nguyên phạm vi thay vì tự động tăng traffic.

### 8.2. Nhiễu và nhiều cửa sổ

Metric có thể dao động vì retry, batch, autoscaling, deploy của dependency hoặc traffic bất thường. Có thể sử dụng:

- Cửa sổ ngắn để phát hiện sự cố nghiêm trọng nhanh.
- Cửa sổ dài hơn để xác nhận xu hướng.
- Ngưỡng liên tục trong nhiều lần đánh giá.
- So sánh canary với control.
- Phân tích theo endpoint hoặc cohort.

Không nên làm trễ phản ứng với lỗi nghiêm trọng chỉ để chờ nhiều cửa sổ. Với lỗi mất dữ liệu, sai phân quyền hoặc crash diện rộng, điều kiện dừng có thể kích hoạt ngay khi có bằng chứng đáng tin cậy.

## 9. Xác định điều kiện dừng trước khi triển khai

Điều kiện dừng cần được viết thành policy trước khi bắt đầu rollout. Không nên đợi thấy dashboard đỏ rồi mới thương lượng xem có nên dừng hay không.

Một policy có thể chia thành các nhóm:

### 9.1. Điều kiện dừng cứng (hard stop)

Thường kích hoạt abort hoặc rollback theo runbook:

- Phiên bản mới không thể khởi động hoặc liên tục crash.
- Readiness hoặc health check bắt buộc thất bại trên phạm vi vượt ngưỡng.
- Error rate hoặc latency vi phạm SLO nghiêm trọng và có liên hệ với canary.
- Có bằng chứng dữ liệu sai, mất dữ liệu hoặc giao dịch trùng.
- Phát hiện lỗi phân quyền, rò rỉ dữ liệu hoặc hành vi bảo mật nghiêm trọng.
- Dependency quan trọng bị mất kết nối do thay đổi mới.
- Tài nguyên tiến gần ngưỡng gây sập dịch vụ và không có khả năng tự phục hồi.

Với lỗi dữ liệu hoặc bảo mật, không nhất thiết phải chờ metric thống kê đạt một ngưỡng. Một bằng chứng xác thực về sai lệch nghiêm trọng có thể đủ để dừng ngay.

### 9.2. Điều kiện giữ (hold) hoặc điều tra

Không nhất thiết phải rollback ngay, nhưng không được tăng phạm vi:

- Metric suy giảm nhẹ nhưng chưa đủ mẫu.
- Telemetry của phiên bản mới thiếu hoặc đến chậm.
- Một cảnh báo tài nguyên tăng nhưng chưa có tác động người dùng.
- Chỉ số nghiệp vụ thay đổi nhưng chưa xác định được nguyên nhân.
- Control và canary đều gặp lỗi, có thể do dependency chung.
- Một kiểm tra bắt buộc trả về trạng thái không xác định.

Giữ rollout cho phép nhóm điều tra trong khi hạn chế số người dùng bị ảnh hưởng.

### 9.3. Điều kiện tiếp tục

Chỉ tăng traffic khi:

- Các tín hiệu bắt buộc đã có dữ liệu hợp lệ.
- Health và readiness ổn định.
- Error rate, latency và SLI nằm trong policy.
- Không có finding nghiêm trọng mới.
- Chỉ số nghiệp vụ quan trọng không suy giảm ngoài mức cho phép.
- Cửa sổ quan sát và minimum sample size đã đạt.
- Không có điều kiện hold hoặc hard stop đang mở.

## 10. Phân biệt pause, abort và rollback

Ba hành động này có mục đích khác nhau.

| Hành động | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Pause / Hold | Giữ rollout ở phạm vi hiện tại, không tăng traffic | Cần thêm dữ liệu hoặc điều tra một tín hiệu chưa rõ |
| Abort | Dừng kế hoạch rollout và loại phiên bản mới khỏi phần chưa chuyển đổi | Canary có lỗi hoặc điều kiện phát hành không còn đạt |
| Rollback | Đưa traffic hoặc workload về phiên bản trước đã biết là ổn định | Phiên bản mới đang gây tác động và phiên bản cũ còn an toàn, tương thích |

Trong blue-green, abort có thể đơn giản là không chuyển traffic sang green. Trong canary, có thể đưa traffic canary về 0%. Trong rolling update, một phần instance mới đã thay thế instance cũ nên cần rollback hoặc roll-forward.

Không phải mọi hold đều cần rollback. Ngược lại, khi có lỗi nghiêm trọng đang ảnh hưởng người dùng, chỉ pause rollout có thể không đủ; cần giảm hoặc chuyển traffic khỏi phiên bản lỗi.

## 11. Quy tắc quyết định khi tín hiệu xung đột

Các tín hiệu có thể đưa ra kết quả khác nhau:

- Pod Ready nhưng error rate tăng.
- CPU bình thường nhưng checkout thành công giảm.
- SAST/SCA đạt nhưng ứng dụng ghi sai dữ liệu.
- Canary có latency tăng trong khi control cũng tăng.
- Metric kỹ thuật tốt nhưng telemetry nghiệp vụ không có dữ liệu.

Nên đặt thứ tự ưu tiên:

1. **An toàn dữ liệu và bảo mật:** sai dữ liệu, rò rỉ hoặc vượt quyền là lý do dừng mạnh.
2. **Tác động người dùng và SLO:** availability, error rate, latency và nghiệp vụ trọng yếu.
3. **Khả năng vận hành:** crash, saturation, queue lag, dependency health.
4. **Chất lượng bằng chứng:** dữ liệu có đầy đủ, đúng phiên bản và đủ mẫu không.

Một tín hiệu PASS không thể bù cho một hard stop ở nhóm khác. Ví dụ, CPU thấp không thể làm cho một lỗi ghi trùng giao dịch trở nên chấp nhận được.

Khi không thể kết luận do thiếu dữ liệu, kết quả nên là UNKNOWN hoặc INSUFFICIENT_DATA, không phải PASS.

## 12. Gắn tín hiệu với phiên bản và phạm vi triển khai

Để biết phiên bản mới gây ra thay đổi nào, telemetry cần có dấu mốc phát hành.

Nên ghi nhận:

- Release ID hoặc deployment ID.
- Git commit SHA.
- Artifact digest.
- Phiên bản ứng dụng.
- Môi trường và region.
- Thời điểm bắt đầu/kết thúc từng giai đoạn rollout.
- Tỷ lệ traffic canary và control.
- Các lần pause, abort, rollback và người phê duyệt.

Dashboard cần lọc được theo version và cohort. Nếu chỉ xem tổng thể, lỗi của một canary nhỏ có thể bị che bởi phiên bản cũ.

Cũng cần bảo đảm metric label không chứa thông tin cá nhân hoặc cardinality không kiểm soát. Các chi tiết request nên được tra cứu qua trace hoặc log với quyền truy cập phù hợp.

## 13. Ví dụ policy cho canary

Ví dụ dưới đây là cấu trúc minh họa trung lập nền tảng. Tên trường và ngưỡng thực tế cần được điều chỉnh theo hệ thống giám sát, SLO và lưu lượng của dịch vụ.

~~~yaml
deployment_policy:
  strategy: canary

  stages:
    - traffic: small
      observe_for: service_defined_window
    - traffic: medium
      observe_for: service_defined_window
    - traffic: full
      observe_for: post_rollout_window

  data_requirements:
    require_telemetry: true
    minimum_sample_size: service_defined_minimum
    insufficient_data_action: HOLD

  hard_stop:
    - signal: confirmed_data_integrity_failure
      action: ABORT_AND_ESCALATE
    - signal: confirmed_security_regression
      action: ABORT_AND_ESCALATE
    - signal: severe_slo_breach_attributable_to_canary
      action: ROLLBACK

  hold:
    - signal: latency_regression_needs_more_samples
      action: PAUSE
    - signal: telemetry_missing_or_delayed
      action: HOLD
    - signal: shared_dependency_degradation
      action: HOLD_AND_INVESTIGATE

  promote_requires:
    - health_checks_passed
    - slo_policy_passed
    - business_guardrails_passed
    - minimum_sample_size_reached
    - no_open_hard_stop
~~~

Policy trên không cung cấp ngưỡng latency hoặc error rate cụ thể vì mỗi dịch vụ có SLO, traffic và đặc điểm khác nhau. Ngưỡng cần được xác định bằng dữ liệu vận hành và được version hóa cùng cấu hình rollout.

## 14. Ví dụ: triển khai canary cho dịch vụ thanh toán

Giả sử dịch vụ thanh toán phát hành phiên bản mới có thay đổi cách gọi payment provider.

Trước triển khai, nhóm xác định:

- SLI availability và latency của API.
- Tỷ lệ authorize/capture thành công.
- Tỷ lệ giao dịch trùng hoặc bị từ chối bất thường.
- Error rate theo loại response.
- Timeout và connection pool tới payment provider.
- Baseline và nhóm control đang chạy phiên bản ổn định.

Khi bắt đầu canary:

1. Chuyển một phần nhỏ traffic đủ đại diện sang phiên bản mới.
2. Xác minh Pod Ready và image digest đúng release record.
3. Chờ đủ số giao dịch và cửa sổ quan sát.
4. So sánh error rate, p95 latency và tỷ lệ thanh toán thành công giữa canary và control.
5. Kiểm tra các invariant như mỗi yêu cầu thanh toán chỉ tạo một giao dịch hợp lệ.
6. Chỉ tăng traffic nếu tất cả điều kiện bắt buộc đạt.

Nếu tỷ lệ thanh toán thành công giảm rõ rệt chỉ ở canary, dừng tăng traffic và chuyển traffic về phiên bản ổn định theo runbook. Nếu phát hiện giao dịch trùng, kích hoạt hard stop, bảo toàn bằng chứng và xử lý dữ liệu theo quy trình sự cố.

Nếu cả canary và control đều giảm do payment provider gặp sự cố, giữ rollout và điều tra dependency chung. Không nên kết luận phiên bản mới là nguyên nhân chỉ từ một dashboard tổng.

## 15. Tự động hóa quyết định nhưng giữ khả năng kiểm soát

Có thể tự động hóa việc đánh giá tín hiệu và hành động rollout. Tuy nhiên, policy phải giải thích được và có giới hạn quyền rõ ràng.

Một bộ điều khiển rollout cần:

- Đọc metric theo đúng release, version và cohort.
- Kiểm tra minimum sample size và độ mới của dữ liệu.
- Đánh giá các hard stop trước điều kiện promote.
- Không tăng traffic nếu bất kỳ điều kiện bắt buộc nào chưa rõ.
- Ghi quyết định, dữ liệu đầu vào và thời điểm.
- Giới hạn số lần tự động retry hoặc đánh giá lại.
- Ngăn nhiều rollout cùng sửa traffic hoặc workload của một dịch vụ.
- Hỗ trợ pause thủ công và escalation đến người trực.
- Không tự động rollback các thay đổi dữ liệu không thể đảo ngược nếu chưa có runbook.

Tự động hóa nên thực hiện đúng hành động đã được phê duyệt. Ví dụ, một policy có thể tự động đưa traffic canary về 0% khi có lỗi nghiêm trọng, nhưng cần tạo incident và giữ lại thông tin để nhóm điều tra.

### 15.1. Ai có quyền ghi đè quyết định?

Cần quy định ai có thể:

- Pause rollout.
- Tiếp tục sau khi điều tra.
- Abort release.
- Kích hoạt rollback.
- Phê duyệt ngoại lệ.
- Thay đổi ngưỡng hoặc thời gian quan sát.

Mọi thao tác override cần ghi người thực hiện, lý do, thời điểm, phạm vi và thời hạn. Không nên để một lần bấm "continue" vô hiệu hóa toàn bộ hard stop mà không có audit trail.

## 16. Rollback phải xét đến dữ liệu và khả năng tương thích

Rollback ứng dụng không phải lúc nào cũng an toàn. Phiên bản mới có thể đã:

- Thay đổi schema database.
- Ghi dữ liệu theo định dạng mới.
- Phát message mà phiên bản cũ không hiểu.
- Thực hiện giao dịch ngoài hệ thống không thể hoàn tác.
- Thay đổi API contract giữa các dịch vụ.

Vì vậy, trước release cần xác định:

- Phiên bản cũ có tương thích với schema hiện tại không?
- Migration có hỗ trợ expand-contract không?
- Có thể dừng consumer hoặc chuyển traffic mà không mất message không?
- Giao dịch đã phát sinh có cần bù trừ (compensation) không?
- Có phương án roll-forward nếu rollback không an toàn không?

Với database, chiến lược expand-contract thường giảm rủi ro: thêm cấu trúc tương thích trước, triển khai ứng dụng có thể làm việc với cả schema cũ và mới, chuyển dữ liệu nếu cần, rồi mới loại bỏ cấu trúc cũ ở một release sau.

Rollback nên triển khai lại artifact đã lưu và xác minh, không build lại commit cũ tùy ý. Cùng với artifact digest, cần giữ release record, cấu hình môi trường và runbook tương ứng.

## 17. Kiểm thử điều kiện dừng trước khi dùng production

Một policy có thể đúng trên giấy nhưng sai khi kết nối với metric hoặc bộ điều khiển rollout. Cần kiểm thử các trường hợp:

- Healthy: tín hiệu tốt và đủ mẫu thì rollout được promote.
- Hard stop: lỗi nghiêm trọng khiến rollout abort hoặc rollback đúng hành động.
- Hold: metric chưa đủ mẫu thì không tăng traffic.
- Telemetry failure: dữ liệu cũ, thiếu hoặc sai version phải trả UNKNOWN.
- Shared dependency: control và canary cùng lỗi thì kích hoạt điều tra phù hợp.
- Recovery: sau khi sửa lỗi, quy trình tiếp tục hoặc khởi chạy lại có truy vết.
- Override: thao tác thủ công cần quyền và audit trail.
- Rollback failure: hệ thống phát cảnh báo và chuyển sang runbook dự phòng.

Nên dùng dữ liệu giả lập, staging hoặc môi trường thử nghiệm để kiểm tra policy trước khi bật tự động dừng production. Cần bảo đảm điều kiện dừng không bị vô hiệu hóa do lỗi truy vấn, thiếu label hoặc thay đổi tên metric.

## 18. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ dựa vào Pod Ready | Bỏ sót lỗi API và nghiệp vụ | Kết hợp health, SLI và business metrics |
| Chỉ xem metric toàn dịch vụ | Canary nhỏ bị phiên bản cũ che khuất | Phân tách theo version và cohort |
| Dừng theo một spike đơn lẻ | Rollback do nhiễu | Dùng cửa sổ, baseline và điều kiện xác nhận phù hợp |
| Chờ đủ mẫu với mọi loại lỗi | Có thể tiếp tục khi đã có lỗi nghiêm trọng | Hard stop cho dữ liệu, bảo mật và sự cố rõ ràng |
| Không có minimum sample size | Kết luận từ vài request | Dùng trạng thái INSUFFICIENT_DATA |
| Ngưỡng giống nhau cho mọi dịch vụ | Không phản ánh SLO và lưu lượng | Xác định policy theo dịch vụ |
| Metric thiếu release/version label | Không quy nguyên nhân được cho phiên bản | Gắn deployment marker và version |
| Coi thiếu telemetry là khỏe | Promote khi không có bằng chứng | UNKNOWN phải giữ rollout |
| Tự động rollback mọi cảnh báo | Có thể làm gián đoạn hoặc hỏng dữ liệu | Phân biệt hold, abort và rollback |
| Không kiểm tra khả năng tương thích dữ liệu | Phiên bản cũ không chạy được sau rollback | Chuẩn bị migration và roll-forward plan |
| Không ghi nhận override | Quyết định không thể kiểm toán | Lưu actor, lý do, thời gian và phạm vi |

## 19. Checklist chọn tín hiệu và điều kiện dừng

**Tín hiệu**

- [ ] Có SLI/SLO phù hợp với dịch vụ.
- [ ] Theo dõi latency, traffic, errors và saturation.
- [ ] Có health/readiness và tín hiệu phụ thuộc.
- [ ] Có metric nghiệp vụ cho luồng quan trọng.
- [ ] Telemetry phân biệt version, release và cohort.
- [ ] Có baseline và control phù hợp.

**Ngưỡng và dữ liệu**

- [ ] Ngưỡng dựa trên SLO và dữ liệu thực tế.
- [ ] Kết hợp điều kiện tuyệt đối và thay đổi so với baseline.
- [ ] Có minimum sample size.
- [ ] Có cửa sổ quan sát theo đặc điểm traffic.
- [ ] Phân biệt PASS, FAIL, UNKNOWN và INSUFFICIENT_DATA.
- [ ] Có cách xử lý metric đến chậm hoặc thiếu.

**Điều kiện và hành động**

- [ ] Hard stop và hold được định nghĩa trước rollout.
- [ ] Có tiêu chí tiếp tục hoặc promote rõ ràng.
- [ ] Phân biệt pause, abort và rollback.
- [ ] Có quy tắc xử lý khi control và canary cùng gặp lỗi.
- [ ] Có người chịu trách nhiệm và quy trình override.
- [ ] Các quyết định được ghi audit trail.

**Khả năng khôi phục**

- [ ] Artifact trước đó còn được lưu và xác minh.
- [ ] Rollback dùng đúng digest đã biết là ổn định.
- [ ] Database và message compatibility đã được đánh giá.
- [ ] Có roll-forward hoặc compensation plan khi rollback không an toàn.
- [ ] Có post-deploy verification sau promote hoặc rollback.
- [ ] Policy đã được thử với tình huống healthy, hard stop và telemetry failure.

## 20. Kết luận

Tín hiệu triển khai cần phản ánh cả trạng thái kỹ thuật, trải nghiệm người dùng, kết quả nghiệp vụ và chất lượng dữ liệu quan sát. SLI/SLO, golden signals, baseline và nhóm control giúp đánh giá phiên bản mới trong đúng bối cảnh. Cửa sổ quan sát và lượng mẫu tối thiểu giúp tránh quyết định từ dữ liệu nhiễu hoặc quá ít.

Điều kiện dừng cần được xác định trước, phân biệt hard stop với hold và gắn mỗi trạng thái với hành động phù hợp: tiếp tục, pause, abort hoặc rollback. Khi telemetry thiếu, hệ thống phải thể hiện trạng thái chưa biết thay vì coi là đạt. Kết hợp policy có thể giải thích, artifact bất biến, kiểm tra tương thích dữ liệu và audit trail giúp rollout có thể tự động hóa mà vẫn bảo vệ dịch vụ và người dùng.

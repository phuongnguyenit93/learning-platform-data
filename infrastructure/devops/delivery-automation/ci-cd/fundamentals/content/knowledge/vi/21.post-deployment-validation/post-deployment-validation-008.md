# Dừng mở rộng hoặc chuyển sang phục hồi khi có tín hiệu xấu

Một lần triển khai hoàn tất không có nghĩa phiên bản mới đã hoạt động tốt trong điều kiện thực tế. Sau khi traffic bắt đầu đi vào phiên bản mới, lỗi có thể chỉ xuất hiện ở một nhóm người dùng, một vùng, một loại request hoặc khi tải tăng. Nếu pipeline tiếp tục mở rộng rollout theo lịch mà không đọc các tín hiệu vận hành, một lỗi nhỏ ở canary có thể trở thành sự cố diện rộng.

Vì vậy, rollout cần có **điều kiện tiếp tục, điều kiện tạm dừng và điều kiện phục hồi** được xác định trước. Khi tín hiệu xấu xuất hiện, hệ thống phải dừng việc tăng phạm vi thay đổi, giữ đủ bằng chứng để điều tra và chọn hành động phù hợp: chờ thêm dữ liệu, tắt tính năng, chuyển traffic, rollback artifact hoặc roll forward bằng bản sửa lỗi. Quyết định cần dựa trên mức độ ảnh hưởng và khả năng đảo ngược, không chỉ dựa vào một trạng thái deploy thành công.

## 1. Deployment thành công chưa đồng nghĩa dịch vụ khỏe mạnh

Deployment controller thường xác nhận tài nguyên đã được cập nhật: pod đã được tạo, process đã khởi động hoặc load balancer đã nhận instance mới. Những kiểm tra đó cần thiết nhưng chưa đủ để kết luận phiên bản mới an toàn.

Một ứng dụng có thể:

- Khởi động thành công nhưng trả lỗi ở một endpoint nghiệp vụ.
- Vượt qua readiness probe nhưng kết nối database chậm hoặc cạn pool khi có tải.
- Trả HTTP 200 nhưng ghi dữ liệu sai hoặc tạo giao dịch trùng.
- Hoạt động tốt ở một vùng nhưng lỗi ở một region khác.
- Có error rate thấp khi canary nhận ít traffic, nhưng suy giảm khi tỷ lệ tăng.
- Không có lỗi kỹ thuật rõ ràng nhưng conversion hoặc tỷ lệ hoàn tất giao dịch giảm.

Cần phân biệt ba mốc:

| Mốc | Điều được xác nhận | Điều chưa được chứng minh |
|---|---|---|
| Deployment complete | Phiên bản đã được cài đặt hoặc rollout controller báo hoàn tất | Hành vi thực tế dưới traffic |
| Smoke/health check pass | Một số đường đi cơ bản phản hồi đúng | Tất cả luồng nghiệp vụ và tải thực tế |
| Post-deployment validation pass | Các guardrail và chỉ số trong cửa sổ quan sát đạt | Không có lỗi nào có thể xuất hiện trong tương lai |

Post-deployment validation là bước quyết định có tiếp tục mở rộng hay không. Nó cần liên kết kết quả kiểm tra với đúng artifact digest, deployment revision, môi trường và khoảng thời gian quan sát.

## 2. Xác định tín hiệu cần theo dõi trước khi triển khai

Không nên đợi đến khi có lỗi mới chọn metric. Trước rollout, nhóm cần xác định tín hiệu phản ánh sức khỏe kỹ thuật, trải nghiệm người dùng và tính đúng đắn của nghiệp vụ.

| Nhóm tín hiệu | Ví dụ | Có thể phát hiện |
|---|---|---|
| Availability | Tỷ lệ request thành công, health check, số instance sẵn sàng | Dịch vụ không phục vụ được request |
| Errors | HTTP 5xx, exception, failed job, timeout | Regression chức năng hoặc lỗi phụ thuộc |
| Latency | p50, p95, p99, thời gian xử lý theo endpoint | Suy giảm hiệu năng |
| Saturation | CPU, memory, thread, connection pool, queue depth | Cạn tài nguyên hoặc nghẽn |
| Dependency | Database errors, cache miss, provider 429/5xx, message lag | Tác động lan truyền từ hệ thống phụ thuộc |
| Business | Payment success, checkout completion, order creation | Lỗi ảnh hưởng kết quả nghiệp vụ |
| Data correctness | Bản ghi sai, duplicate, reconciliation mismatch | Ứng dụng chạy nhưng dữ liệu không đúng |
| Deployment | Restart, crash loop, failed probe, rollout stalled | Phiên bản mới không ổn định |

Không cần theo dõi hàng trăm metric trong mỗi lần phát hành. Chọn một tập nhỏ gồm các chỉ số có thể thay đổi do release và các guardrail bảo vệ dịch vụ. Mỗi metric cần có định nghĩa, nguồn dữ liệu, phạm vi đo và người chịu trách nhiệm.

Một endpoint health trả 200 chỉ cho biết một đường kiểm tra đã phản hồi. Nó không chứng minh thanh toán, tạo đơn hoặc luồng nghiệp vụ quan trọng hoạt động đúng. Hãy kết hợp health check với synthetic transaction hoặc kiểm tra nghiệp vụ có dữ liệu thử nghiệm an toàn.

## 3. So sánh với baseline và SLO

Một con số riêng lẻ thường khó diễn giải. Error rate 1% có thể là bình thường với một dịch vụ nội bộ nhưng là suy giảm nghiêm trọng với một luồng thanh toán vốn ổn định ở mức 0,05%.

Baseline là mức hoạt động tham chiếu trước khi triển khai. Có thể lấy từ:

- Cùng service, endpoint và vùng trong khoảng thời gian trước release.
- Nhóm instance đang chạy phiên bản ổn định.
- Cohort đối chứng không nhận tính năng mới.
- SLO/SLI và error budget đã được thống nhất.
- Một mốc tải tương đương trong các lần phát hành trước.

Khi so sánh, cần giữ phạm vi tương đương. So sánh p95 của endpoint thanh toán ở canary với p95 toàn hệ thống có thể che khuất vấn đề nếu cơ cấu request khác nhau.

SLO giúp xác định mức dịch vụ cần đạt. Error budget thể hiện lượng suy giảm được chấp nhận trong một khoảng thời gian theo chính sách. Một release làm burn rate tăng nhanh có thể cần dừng rollout ngay cả khi tổng error budget chưa cạn.

Ví dụ về cách diễn giải:

- Availability giảm so với baseline và tiến gần ngưỡng SLO.
- Error rate của canary cao hơn nhóm stable trong cùng thời gian.
- p95 latency tăng liên tục sau khi tăng traffic.
- Error budget burn rate vượt ngưỡng cảnh báo đã định.

Không nên dùng baseline như một giá trị cố định mãi mãi. Lưu lượng, mùa vụ, loại người dùng và cấu trúc hệ thống thay đổi; baseline cần được chọn theo khoảng thời gian và điều kiện phù hợp.

## 4. Đặt guardrail có ngưỡng, thời gian và phạm vi

Guardrail là điều kiện giới hạn để quyết định rollout có được tiếp tục hay không. Một guardrail có thể dựa trên ngưỡng tuyệt đối, mức thay đổi so với baseline hoặc kết hợp cả hai.

Ví dụ:

| Guardrail | Điều kiện minh họa | Hành động |
|---|---|---|
| HTTP 5xx | Cao hơn baseline đáng kể trong 10 phút và đủ số request | Dừng tăng traffic, điều tra |
| p95 latency | Vượt 1,5 lần baseline trong cửa sổ liên tục | Giữ rollout hoặc giảm traffic |
| Pod restart | Có crash loop hoặc restart tăng bất thường | Dừng rollout, kiểm tra runtime |
| Payment success | Cohort mới giảm vượt ngưỡng đã thống nhất | Tắt flag hoặc chuyển traffic về phiên bản ổn định |
| Database pool | Connection wait và timeout tăng liên tục | Dừng mở rộng, kiểm tra tải database |
| Data integrity | Phát hiện duplicate hoặc reconciliation mismatch | Chặn rollout và kích hoạt quy trình xử lý dữ liệu |

Các ngưỡng và thời gian trên chỉ minh họa. Nhóm cần xác định chúng từ SLO, baseline, mức rủi ro và đặc tính traffic. Không sao chép một con số chung cho mọi dịch vụ.

Một guardrail nên mô tả đủ:

- Metric và cách tính.
- Phạm vi: service, endpoint, region, tenant hoặc cohort.
- Ngưỡng cảnh báo và ngưỡng dừng.
- Cửa sổ đánh giá và thời gian duy trì vi phạm.
- Số mẫu tối thiểu để kết luận.
- Hành động khi vượt ngưỡng.
- Người hoặc hệ thống có quyền quyết định.

Nếu metric không có dữ liệu, không được tự coi là pass. Trạng thái cần được phân biệt giữa đạt, vi phạm và không đủ dữ liệu.

## 5. Cửa sổ quan sát và số lượng mẫu

Một metric có thể dao động tự nhiên. Một lỗi đơn lẻ hoặc một spike vài giây chưa chắc là regression, nhưng chờ quá lâu cũng có thể làm tăng phạm vi ảnh hưởng.

Cửa sổ quan sát cần phù hợp với:

- Lưu lượng thực tế của service.
- Chu kỳ nghiệp vụ, ví dụ thời gian hoàn tất thanh toán hoặc xử lý batch.
- Thời gian khởi động và warm-up của ứng dụng.
- Độ trễ của hệ thống telemetry.
- Mức độ nghiêm trọng nếu lỗi xảy ra.
- Số request hoặc giao dịch đủ để so sánh.

Với traffic cao, có thể phát hiện thay đổi trong vài phút. Với dịch vụ ít traffic, cần kéo dài cửa sổ, dùng synthetic test hoặc kiểm tra chủ động để không kết luận từ vài request.

Một quy tắc đánh giá có thể yêu cầu đồng thời:

1. Metric vượt ngưỡng.
2. Vi phạm kéo dài qua một khoảng thời gian tối thiểu.
3. Có đủ số request hoặc giao dịch.
4. Tín hiệu đến từ đúng revision hoặc cohort.

Ví dụ, p95 tăng cao trong 30 giây với 8 request không có cùng độ tin cậy với p95 tăng liên tục trong 10 phút trên hàng nghìn request. Ngược lại, một sự kiện data corruption hoặc giao dịch sai có thể cần dừng ngay mà không chờ đủ mẫu.

## 6. Phân biệt tín hiệu xấu với cảnh báo nhiễu

Không phải mọi alert đều yêu cầu rollback. Một cảnh báo có thể đến từ hệ thống monitoring, dependency hoặc tải nền thay đổi mà không liên quan đến release.

Khi tín hiệu xấu xuất hiện, cần đối chiếu:

- Thời điểm bắt đầu lỗi với thời điểm deploy và tăng traffic.
- Cohort canary với cohort stable.
- Endpoint bị ảnh hưởng với endpoint không liên quan.
- Region có phiên bản mới với region chưa rollout.
- Metric của ứng dụng với metric của database, cache và provider.
- Log, trace và deployment event cùng revision.

Nếu cả canary và stable cùng suy giảm do database đang quá tải, rollback artifact có thể không giải quyết nguyên nhân. Tuy nhiên, nếu canary suy giảm rõ rệt còn stable bình thường, khả năng regression từ release cao hơn.

Cần phân biệt **correlation** và **causation**. Việc lỗi xuất hiện sau deploy là tín hiệu cần điều tra, chưa tự chứng minh code mới là nguyên nhân. Với lỗi nghiêm trọng, ưu tiên giới hạn ảnh hưởng trước rồi tiếp tục phân tích khi dịch vụ ổn định.

## 7. Các quyết định khi tín hiệu xấu xuất hiện

Không phải mọi tình huống đều cần rollback ngay. Quy trình cần có các hành động với mức can thiệp khác nhau.

| Quyết định | Khi phù hợp | Kết quả |
|---|---|---|
| Continue | Guardrail đạt và dữ liệu đủ tin cậy | Tiếp tục giai đoạn rollout |
| Hold/pause | Metric chưa ổn định hoặc chưa đủ mẫu | Giữ nguyên tỷ lệ, chờ thêm dữ liệu |
| Stop expansion | Có tín hiệu xấu nhưng chưa xác định cần rollback | Không tăng thêm audience hoặc traffic |
| Reduce exposure | Vấn đề chỉ ảnh hưởng cohort hoặc tỷ lệ nhất định | Giảm tỷ lệ hoặc thu hẹp đối tượng |
| Disable feature | Lỗi nằm ở tính năng được điều khiển bằng flag và fallback an toàn | Chuyển về code path cũ |
| Rollback deployment | Binary mới gây lỗi và phiên bản cũ còn tương thích | Khôi phục artifact trước |
| Roll forward | Rollback không an toàn hoặc cần sửa lỗi nhanh | Triển khai bản sửa có kiểm thử |
| Emergency mitigation | Có nguy cơ mất dữ liệu, bảo mật hoặc gián đoạn lớn | Kích hoạt runbook sự cố |

Điểm quan trọng là **dừng mở rộng** và **phục hồi** là hai quyết định riêng. Dừng rollout giúp ngăn thêm người dùng bị ảnh hưởng trong khi nhóm xác định nguyên nhân. Phục hồi đưa hệ thống về trạng thái ổn định bằng hành động phù hợp.

## 8. Thiết kế trạng thái rollout rõ ràng

Một rollout có kiểm soát nên có trạng thái và chuyển tiếp được định nghĩa trước.

~~~mermaid
stateDiagram-v2
    [*] --> Preparing
    Preparing --> Validating: Deploy hoàn tất
    Validating --> Expanding: Guardrail đạt
    Validating --> Paused: Thiếu dữ liệu hoặc tín hiệu chưa rõ
    Validating --> Recovery: Vi phạm nghiêm trọng
    Expanding --> Observing: Tăng một bước traffic
    Observing --> Expanding: Guardrail đạt
    Observing --> Paused: Cảnh báo cần điều tra
    Observing --> Recovery: Ngưỡng dừng bị vượt
    Paused --> Observing: Có đủ dữ liệu và được cho phép tiếp tục
    Paused --> Recovery: Xác nhận cần phục hồi
    Recovery --> Verifying: Hành động phục hồi hoàn tất
    Verifying --> Stable: Kiểm tra sau phục hồi đạt
    Verifying --> Incident: Dịch vụ chưa ổn định
    Stable --> [*]
~~~

Các trạng thái cần có ý nghĩa vận hành:

- **Preparing:** xác nhận artifact, target, policy và kế hoạch rollout.
- **Validating:** triển khai xong, chạy smoke test và quan sát ban đầu.
- **Expanding:** tăng exposure theo từng bước đã định.
- **Observing:** giữ tỷ lệ hiện tại trong cửa sổ đánh giá.
- **Paused:** đóng băng thay đổi để điều tra.
- **Recovery:** tắt flag, giảm traffic, rollback hoặc roll forward.
- **Verifying:** xác nhận hệ thống đã phục hồi.
- **Stable:** hoàn tất rollout và lưu bằng chứng.
- **Incident:** cần xử lý sự cố theo quy trình vận hành.

Không để một job timeout hoặc monitoring mất kết nối tự động chuyển trạng thái sang Stable. Nếu không thể lấy tín hiệu bắt buộc, rollout cần giữ trạng thái paused hoặc failed theo policy.

## 9. Progressive rollout cần tăng theo bước và có điểm dừng

Ví dụ một rollout theo tỷ lệ traffic:

| Giai đoạn | Tỷ lệ traffic | Điều kiện |
|---|---:|---|
| Internal | Nội bộ | Smoke test và luồng chính đạt |
| Canary | 1% | Metric có đủ mẫu, không có lỗi nghiêm trọng |
| Small | 5% | Error rate và latency trong guardrail |
| Medium | 25% | Business metric và dependency ổn định |
| Large | 50% | Không có xu hướng suy giảm |
| Full | 100% | Được phép hoàn tất theo policy |

Các tỷ lệ cần được điều chỉnh theo quy mô traffic, khả năng cô lập và mức độ rủi ro. Một dịch vụ có thể cần bước 1%, 2%, 5%, 10%; dịch vụ khác có thể dùng 10%, 25%, 50%, 100%.

Sau mỗi lần tăng, phải có cửa sổ quan sát mới. Không tăng liên tục chỉ vì lần kiểm tra trước pass ngay sau khi deploy. Một số vấn đề xuất hiện trễ do cache warm-up, batch job, thời điểm cao tải hoặc dữ liệu mới.

Khi guardrail bị vi phạm, controller phải giữ hoặc giảm exposure theo chính sách. Không để một lịch rollout định thời tiếp tục chạy độc lập với kết quả validation.

## 10. Ví dụ canary: dừng tăng traffic khi error rate tăng

Giả sử phiên bản mới của API đơn hàng nhận 5% traffic. Nhóm đặt guardrail minh họa:

- Error rate 5xx của canary không được cao hơn nhóm stable quá mức đã định.
- p95 latency không được vượt ngưỡng SLO.
- Số request tối thiểu phải đạt trước khi so sánh.
- Vi phạm kéo dài qua hai cửa sổ liên tiếp thì dừng tăng traffic.
- Có bất kỳ dấu hiệu ghi sai hoặc mất dữ liệu nào thì dừng ngay.

Kết quả quan sát:

| Chỉ số | Stable | Canary | Đánh giá |
|---|---:|---:|---|
| 5xx rate | 0,2% | 1,8% | Xấu rõ rệt |
| p95 latency | 180 ms | 310 ms | Suy giảm |
| Request count | 18.000 | 950 | Đủ mẫu theo ví dụ |
| Database connection wait | Bình thường | Tăng | Có thể liên quan đến code mới |

Quyết định phù hợp là dừng tăng traffic, giữ lại log/trace và điều tra. Nếu lỗi được xác nhận liên quan đến code mới và code path cũ vẫn an toàn, có thể chuyển traffic về stable hoặc rollback. Không tiếp tục lên 25% chỉ vì deployment controller vẫn báo tất cả pod healthy.

## 11. Khi nào nên dừng rollout, khi nào cần phục hồi ngay?

Có thể dùng mức độ ảnh hưởng để xác định hành động ban đầu:

| Mức độ | Dấu hiệu | Hành động ban đầu |
|---|---|---|
| Thấp | Một cảnh báo đơn lẻ, không có tác động người dùng, chưa đủ mẫu | Giữ tỷ lệ và quan sát |
| Trung bình | Error rate hoặc latency xấu hơn baseline, chưa có mất dữ liệu | Dừng mở rộng, điều tra |
| Cao | Nhiều request quan trọng thất bại, SLO bị ảnh hưởng rõ | Dừng rollout và giảm exposure hoặc rollback theo runbook |
| Nghiêm trọng | Mất dữ liệu, giao dịch sai, lộ dữ liệu hoặc ảnh hưởng bảo mật | Dừng ngay, kích hoạt incident response và biện pháp cô lập |

Mức độ cần được định nghĩa theo dịch vụ và tác động nghiệp vụ. Một lỗi ở chức năng phụ có thể chấp nhận tạm thời; một lỗi ghi nhầm số tiền hoặc lộ dữ liệu cần phản ứng ngay dù tỷ lệ request lỗi thấp.

Khi chưa chắc nguyên nhân, dừng mở rộng thường là bước an toàn đầu tiên. Với tín hiệu nghiêm trọng, không chờ điều tra hoàn tất mới giảm ảnh hưởng.

## 12. Chọn giữa tắt feature flag, chuyển traffic và rollback artifact

Hành động phục hồi phụ thuộc cách release được thiết kế.

| Tình huống | Hành động có thể phù hợp | Điều cần xác minh |
|---|---|---|
| Tính năng mới lỗi, code cũ còn trong artifact | Tắt feature flag | Fallback path còn hoạt động và dữ liệu tương thích |
| Canary instance lỗi, stable instance khỏe | Chuyển traffic về stable | Load balancer/service routing và capacity |
| Binary mới lỗi trên mọi request | Rollback artifact hoặc roll forward | Phiên bản cũ tương thích với schema và config hiện tại |
| Config mới gây lỗi | Khôi phục config version trước | Config cũ còn tương thích với binary đang chạy |
| Dependency quá tải do tải tăng | Giảm exposure, rate limit hoặc fallback | Không làm backlog và retry storm tăng thêm |
| Migration đã thay đổi dữ liệu | Dùng runbook dữ liệu, có thể roll forward hoặc restore | Tác động giao dịch phát sinh sau migration |

Tắt flag không giúp ích nếu code mới đã thay đổi phần dùng chung trước khi đánh giá flag. Rollback image cũng không đủ nếu database đã bị migration phá vỡ tương thích. Vì vậy, chiến lược release và migration cần được thiết kế cùng nhau.

## 13. Tự động phục hồi cần có giới hạn an toàn

Tự động rollback có thể giảm thời gian phản ứng, nhưng hành động sai cũng có thể gây thêm sự cố. Chỉ tự động hóa khi điều kiện, phạm vi và hành động đã được kiểm thử.

Có thể tự động:

- Dừng tăng tỷ lệ rollout khi guardrail vi phạm.
- Chuyển traffic khỏi canary nếu stable capacity còn đủ.
- Tắt một feature flag có fallback đã được xác minh.
- Khôi phục config version trước nếu thay đổi có thể đảo ngược.
- Tạo incident hoặc gửi cảnh báo đến kênh vận hành theo policy.

Cần thận trọng hoặc yêu cầu người vận hành:

- Rollback khi schema đã thay đổi không tương thích.
- Hủy migration đang chạy.
- Restore database hoặc dữ liệu.
- Xóa resource hoặc thay đổi có tác dụng phụ khó đảo ngược.
- Thay đổi quyền, secret hoặc cấu hình bảo mật.
- Rollback khi phiên bản trước cũng đang có vấn đề.

Một automation cần có idempotency, timeout, retry giới hạn, audit và điều kiện dừng. Không để một controller lặp đi lặp lại rollback/deploy khi metric dao động quanh ngưỡng.

## 14. Tránh rollout dao động và phản ứng quá mức

Nếu metric liên tục vượt rồi quay về dưới ngưỡng, hệ thống có thể bật/tắt flag hoặc chuyển traffic qua lại. Hiện tượng này gây khó điều tra và có thể làm hệ thống bất ổn hơn.

Các kỹ thuật giảm dao động:

- **Hysteresis:** dùng ngưỡng dừng và ngưỡng cho phép tiếp tục khác nhau.
- **Consecutive windows:** yêu cầu vi phạm liên tiếp trong nhiều cửa sổ trước khi hành động, trừ lỗi nghiêm trọng.
- **Cooldown:** chờ một khoảng thời gian sau khi thay đổi traffic hoặc flag trước khi đánh giá lại.
- **Minimum sample size:** không ra quyết định từ quá ít request.
- **Maximum pause duration:** nếu không đủ dữ liệu sau thời hạn, yêu cầu người vận hành quyết định.
- **One action at a time:** không đồng thời thay traffic, flag và config khi chưa biết tác động của từng thay đổi.

Ví dụ, dừng rollout khi error rate vượt 2% trong hai cửa sổ 5 phút, nhưng chỉ cho phép tiếp tục khi error rate dưới 0,8% trong ba cửa sổ liên tiếp. Các ngưỡng chỉ là ví dụ; khoảng cách giữa hai ngưỡng giúp tránh chuyển trạng thái liên tục.

Không áp dụng cooldown để trì hoãn phản ứng với lỗi nghiêm trọng như data corruption hoặc security incident. Các điều kiện khẩn cấp phải có đường dừng ngay.

## 15. Quy trình phục hồi khi đã xác nhận tín hiệu xấu

Khi guardrail xác nhận release gây ảnh hưởng, nhóm cần thực hiện theo runbook rõ ràng:

1. **Freeze rollout:** khóa mọi bước tăng traffic hoặc promotion tiếp theo.
2. **Giới hạn ảnh hưởng:** dừng canary, giảm tỷ lệ, tắt flag hoặc chuyển traffic theo phương án an toàn.
3. **Xác định revision:** ghi lại artifact digest, config version, deployment revision và thời điểm bắt đầu.
4. **Thu thập bằng chứng:** log, trace, metric, event, request ID và trạng thái dependency.
5. **Chọn phương án:** disable flag, rollback artifact, restore config hoặc roll forward.
6. **Kiểm tra tương thích:** xác minh schema, dữ liệu, message và các consumer trước khi đổi phiên bản.
7. **Thực hiện phục hồi:** chạy hành động theo thứ tự đã định, có người chịu trách nhiệm.
8. **Xác minh lại:** smoke test, synthetic transaction, SLI và business metric.
9. **Giữ rollout ở trạng thái paused:** chỉ tiếp tục khi có quyết định và bằng chứng mới.
10. **Ghi nhận sự cố:** nguyên nhân, phạm vi ảnh hưởng, thời gian phục hồi và hành động phòng ngừa.

Không xóa pod, log hoặc artifact của phiên bản lỗi trước khi đã thu thập bằng chứng cần thiết, trừ khi cần cô lập khẩn cấp để bảo vệ hệ thống. Bằng chứng giúp xác định nguyên nhân và tránh lặp lại lỗi ở lần phát hành tiếp theo.

## 16. Xác minh sau khi phục hồi

Rollback hoặc tắt flag hoàn tất về mặt thao tác chưa có nghĩa dịch vụ đã phục hồi. Cần chạy lại các kiểm tra sau hành động.

Các bước xác minh nên gồm:

- Phiên bản đang phục vụ traffic đúng với deployment record.
- Tỷ lệ instance sẵn sàng và không có crash loop.
- Health check và smoke test đạt.
- Synthetic transaction hoàn tất và dữ liệu được ghi đúng.
- Error rate và latency trở lại trong guardrail.
- Database connection, queue depth và dependency ổn định.
- Không còn traffic đi vào phiên bản hoặc tính năng đã bị cô lập.
- Không có backlog hoặc retry storm do giai đoạn lỗi để lại.
- Metric nghiệp vụ được đối chiếu để phát hiện giao dịch thiếu hoặc trùng.

Cần giữ cửa sổ quan sát sau phục hồi. Nếu chỉ kiểm tra một request thành công rồi đóng incident, lỗi có thể quay lại khi tải tăng hoặc khi cache hết hiệu lực.

Với sự cố dữ liệu, phải có bước reconciliation riêng. Tắt flag hoặc rollback code không tự sửa các bản ghi đã bị ghi sai.

## 17. Thiết kế pipeline có bước đánh giá guardrail

Pipeline có thể mô hình hóa post-deployment validation thành một bước bắt buộc giữa deploy và promote.

Ví dụ pseudocode:

~~~text
deploy(candidate_revision, target)

if not smoke_test(candidate_revision):
    pause_rollout()
    recover_using_runbook()
    stop

start_observation_window()

while observation_window_active:
    signals = collect_signals(candidate_revision, stable_revision)

    if critical_data_or_security_signal(signals):
        freeze_rollout()
        execute_emergency_runbook()
        stop

    if required_signal_missing(signals):
        pause_rollout()
        request_operator_decision()
        stop

    if guardrail_breached(signals):
        freeze_rollout()
        reduce_exposure_or_recover()
        verify_recovery()
        stop

if all_guardrails_passed_with_enough_samples():
    promote_to_next_stage()
else:
    keep_rollout_paused()
~~~

Ví dụ này thể hiện luồng quyết định, không phải một chương trình có thể chạy nguyên trạng. Hàm thu thập tín hiệu phải gắn metric với đúng revision/cohort; điều kiện guardrail phải có ngưỡng và thời gian cụ thể; hành động recovery phải dùng runbook phù hợp với ứng dụng và dữ liệu.

Pipeline không nên chỉ chờ một lệnh smoke test trả mã 0 rồi tự promote. Cần kiểm tra đủ thời gian, số mẫu và các chỉ số bắt buộc. Nếu monitoring không truy cập được, kết quả là chưa xác minh, không phải thành công.

## 18. Lưu bằng chứng và truy vết quyết định rollout

Mỗi lần dừng hoặc phục hồi cần có bản ghi để nhóm biết điều gì đã xảy ra và vì sao.

Thông tin nên lưu:

- Release ID, artifact digest và source commit.
- Deployment revision, target environment và rollout stage.
- Tỷ lệ traffic hoặc audience tại từng thời điểm.
- Metric baseline, metric quan sát và cửa sổ đánh giá.
- Guardrail bị vi phạm, ngưỡng và số mẫu.
- Quyết định: continue, pause, stop, disable, rollback hoặc roll forward.
- Người hoặc automation khởi tạo hành động.
- Thời điểm và kết quả phục hồi.
- Smoke test, synthetic check và business verification sau phục hồi.
- Incident/ticket liên quan và kết luận.

Không đưa secret hoặc dữ liệu cá nhân thô vào log và report. Dùng request ID, trace ID hoặc định danh đã được giảm thiểu để nối bằng chứng.

Các bản ghi này giúp đánh giá lại ngưỡng rollout, xác định tín hiệu phát hiện chậm và chứng minh vì sao một release được tiếp tục hoặc bị dừng.

## 19. Ví dụ xuyên suốt: rollout API thanh toán gặp lỗi

Một phiên bản mới của API thanh toán được triển khai lên production. Ban đầu, 1% traffic được chuyển đến canary. Smoke test đạt, nhưng sau vài phút payment success rate giảm và timeout tới payment provider tăng.

Quy trình xử lý:

1. Controller giữ tỷ lệ ở 1%, không tăng lên 5%.
2. Nhóm so sánh canary với stable và xác nhận lỗi tập trung ở revision mới.
3. Trace cho thấy request mới gọi provider hai lần khi retry, làm tăng timeout và nguy cơ giao dịch trùng.
4. Nhóm tắt flag của luồng retry mới vì code path cũ vẫn còn và đã được kiểm thử.
5. Synthetic transaction xác nhận thanh toán mới hoạt động theo luồng cũ.
6. Nhóm đối chiếu giao dịch trong cửa sổ ảnh hưởng để tìm request có trạng thái không rõ.
7. Error rate và payment success trở lại guardrail trong cửa sổ quan sát sau phục hồi.
8. Rollout giữ paused; bản sửa được kiểm thử trước khi mở lại canary.

Nếu lỗi đã gây ghi dữ liệu sai, chỉ tắt flag chưa đủ. Nhóm cần reconciliation và xử lý giao dịch theo runbook nghiệp vụ trước khi tiếp tục release.

## 20. Checklist dừng rollout và phục hồi an toàn

Trước khi mở rộng hoặc kết thúc một lần triển khai, hãy kiểm tra:

- [ ] Artifact digest, revision và target được xác định rõ.
- [ ] Có baseline phù hợp cho service, endpoint và cohort.
- [ ] Guardrail bao gồm availability, error, latency, saturation và metric nghiệp vụ quan trọng.
- [ ] Mỗi guardrail có ngưỡng, cửa sổ, số mẫu tối thiểu và hành động.
- [ ] Metric thiếu hoặc monitoring lỗi không bị coi là pass.
- [ ] Có cửa sổ quan sát sau mỗi bước tăng traffic.
- [ ] Canary được so sánh với stable trong cùng điều kiện.
- [ ] Có trạng thái pause/stop để đóng băng rollout.
- [ ] Có phân biệt dừng mở rộng với rollback hoặc phục hồi.
- [ ] Đã xác định khi nào tắt flag, chuyển traffic, rollback hay roll forward.
- [ ] Hành động tự động chỉ áp dụng cho tình huống có thể đảo ngược và đã kiểm thử.
- [ ] Có hysteresis, cooldown và giới hạn retry để tránh dao động.
- [ ] Có runbook cho lỗi nghiêm trọng, mất dữ liệu và security incident.
- [ ] Sau phục hồi có smoke test, synthetic check và business verification.
- [ ] Bằng chứng và quyết định được lưu cùng release ID và revision.

Một rollout an toàn không phải là rollout luôn đi đến 100%. Nó là rollout có thể dừng đúng lúc, giới hạn phạm vi ảnh hưởng và phục hồi dựa trên bằng chứng. Khi guardrail được xác định trước, pipeline có quyền tạm dừng và nhóm có runbook phù hợp, tín hiệu xấu sau triển khai trở thành đầu vào cho một quyết định có kiểm soát thay vì một cảnh báo bị bỏ qua.


# Runbooks, trực vận hành và quy trình quản lý sự cố

Dịch vụ trên Google Cloud cần có người chịu trách nhiệm khi cảnh báo xuất hiện, hướng dẫn xử lý có thể làm theo và quy trình phối hợp khi nhiều thành phần cùng gặp lỗi. Nếu kiến thức vận hành chỉ nằm trong trí nhớ của một vài kỹ sư, sự cố ngoài giờ có thể kéo dài vì người trực phải tự tìm dashboard, xác định quyền truy cập, hỏi lại chủ hệ thống và thử các thao tác chưa được kiểm chứng.

Runbook, trực vận hành (on-call) và incident management tạo thành một hệ thống vận hành có thể lặp lại. Runbook hướng dẫn cách kiểm tra và khôi phục một tình huống cụ thể; on-call bảo đảm có người nhận và điều phối phản ứng; incident management giúp nhóm kiểm soát ảnh hưởng, giao tiếp, ra quyết định và học từ sự cố. Trên GCP, các hoạt động này kết hợp với Cloud Monitoring, Cloud Logging, Cloud Trace, Error Reporting, Cloud Audit Logs và công cụ triển khai của từng workload.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt runbook, playbook, incident và problem record.
- Viết runbook có điều kiện kích hoạt, bước chẩn đoán, hành động an toàn, rollback và tiêu chí xác nhận phục hồi.
- Thiết kế lịch trực, handoff, escalation và quyền truy cập cho người trực vận hành.
- Phân loại mức độ nghiêm trọng và tổ chức incident command.
- Sử dụng Cloud Monitoring, Logging, Trace, Error Reporting và audit logs để điều tra sự cố.
- Điều phối giảm thiểu ảnh hưởng, khôi phục dịch vụ và cập nhật trạng thái cho các bên liên quan.
- Viết postmortem theo hướng không quy lỗi cá nhân và theo dõi action items đến khi hoàn tất.

## 1. Runbook, playbook và incident management

Các khái niệm này có liên quan nhưng phục vụ những mục đích khác nhau.

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Runbook | Hướng dẫn thao tác cho một tình huống kỹ thuật đã biết | Xử lý Cloud Run tăng HTTP 5xx |
| Playbook | Điều phối nhiều bước hoặc nhiều nhóm cho một tình huống rộng hơn | Ứng phó sự cố rò rỉ credential |
| Incident | Sự kiện đang gây hoặc có nguy cơ gây ảnh hưởng đáng kể đến dịch vụ/người dùng | API checkout không tạo được đơn hàng |
| Problem record | Theo dõi nguyên nhân hệ thống và công việc ngăn tái diễn | Connection pool thường xuyên cạn khi tải tăng |
| Postmortem | Tài liệu học tập sau incident | Timeline, tác động, yếu tố góp phần và action items |

Runbook thường trả lời câu hỏi: “Khi cảnh báo X xuất hiện, người trực cần kiểm tra gì, làm gì và xác nhận kết quả ra sao?” Playbook bao quát hơn, có thể kết hợp runbook, vai trò, kênh giao tiếp, yêu cầu pháp lý và quy trình phê duyệt.

Một runbook tốt giúp người chưa từng xử lý tình huống vẫn có thể bắt đầu từ các bước an toàn. Nội dung cần đủ cụ thể để thực hiện, nhưng phải nêu rõ điều kiện dừng và escalation khi tình huống vượt khỏi phạm vi đã kiểm chứng.

## 2. Cấu trúc của một runbook có thể sử dụng khi trực ca

Runbook cần được viết cho người trực đang chịu áp lực thời gian. Đặt thông tin khẩn cấp ở đầu tài liệu và trình bày các bước theo thứ tự.

Một cấu trúc khuyến nghị:

| Thành phần | Nội dung cần có |
|---|---|
| Tên và metadata | Service, môi trường, owner, version, ngày review |
| Trigger | Alert name, triệu chứng, ngưỡng và điều kiện kích hoạt |
| Impact | Chức năng, người dùng, region và dependency có thể bị ảnh hưởng |
| Severity | Mức độ ban đầu và điều kiện nâng/hạ mức |
| Preconditions | Quyền, project, region, công cụ và xác nhận cần thiết |
| Dashboards và logs | Link dashboard, log query, trace và metric liên quan |
| Diagnosis | Các bước kiểm tra theo thứ tự, kèm kết quả mong đợi |
| Mitigation | Hành động giảm thiểu đã được kiểm chứng |
| Rollback/recovery | Cách quay lại trạng thái ổn định hoặc khôi phục |
| Verification | SLI/SLO, business check và thời gian theo dõi sau khôi phục |
| Escalation | Nhóm, vai trò, điều kiện và cách liên hệ |
| References | Architecture, dependency map, change history và tài liệu liên quan |

### Viết bước thao tác rõ ràng

Mỗi bước nên có bốn phần:

1. **Mục đích:** bước này giúp xác nhận giả thuyết hoặc giảm ảnh hưởng nào?
2. **Thao tác:** lệnh, dashboard hoặc truy vấn cần dùng.
3. **Kết quả mong đợi:** điều gì cho thấy hệ thống bình thường hoặc bất thường?
4. **Nhánh tiếp theo:** nếu kết quả A thì làm gì; nếu B thì dừng hoặc escalation ở đâu?

Ví dụ:

- Mục đích: kiểm tra revision Cloud Run đang nhận traffic.
- Thao tác: xem traffic allocation và trạng thái revision.
- Kết quả mong đợi: revision đang nhận traffic là revision đã được phát hành và có trạng thái ready.
- Nhánh tiếp theo: nếu traffic trỏ vào revision mới vừa phát hành và 5xx tăng sau thời điểm đó, so sánh log và metrics theo revision; nếu không xác định được revision liên quan, escalation cho service owner.

Tránh các chỉ dẫn mơ hồ như “kiểm tra server”, “restart nếu cần” hoặc “liên hệ team platform”. Hãy ghi rõ tài nguyên, dấu hiệu, tiêu chí và nhóm chịu trách nhiệm.

### Runbook phải nêu rõ giới hạn

Một tài liệu vận hành cần cho biết thao tác nào chỉ đọc, thao tác nào thay đổi production và thao tác nào có thể gây mất dữ liệu. Với hành động rủi ro cao, ghi rõ:

- Điều kiện tiên quyết và người phê duyệt.
- Phạm vi ảnh hưởng dự kiến.
- Cách sao lưu hoặc ghi nhận trạng thái trước khi thay đổi.
- Cách rollback.
- Tiêu chí dừng khi kết quả khác dự kiến.

Không để người trực tự suy đoán project, region, cluster hoặc tên service. Dùng placeholder rõ ràng và yêu cầu xác minh context trước khi chạy lệnh.

## 3. Xây dựng thư viện runbook cho workload GCP

Mỗi dịch vụ nên có runbook cho các triệu chứng phổ biến và những thao tác khôi phục có rủi ro cao. Có thể bắt đầu từ alert hiện có, incident lịch sử và dependency map.

| Workload | Runbook nên có |
|---|---|
| Cloud Run | HTTP 5xx tăng, latency cao, revision không ready, max instances đạt giới hạn |
| GKE | Pod CrashLoopBackOff, node NotReady, rollout thất bại, HPA không scale |
| Compute Engine | VM không khỏe, Managed Instance Group thiếu instance, disk gần đầy |
| Cloud SQL | Connection exhaustion, CPU cao, storage gần đầy, replication lag |
| Pub/Sub | Message backlog tăng, subscription không ack, dead-letter tăng |
| Load Balancing | Backend unhealthy, health check thất bại, traffic phân phối sai |
| Data pipeline | Job trễ, dữ liệu không mới, số bản ghi lỗi tăng |
| IAM và bảo mật | Credential bị lộ, thay đổi quyền bất thường, truy cập trái phép |

Nên có một runbook tổng quan cho từng service, chỉ đến các runbook chuyên biệt. Người trực phải biết service owner, dependency quan trọng, dashboard chính và cách mở incident ngay cả khi chưa xác định nguyên nhân.

### Quản lý nguồn sự thật

Runbook cần được lưu trong nơi có version history, review và quyền truy cập phù hợp. Mỗi tài liệu phải có owner và ngày review tiếp theo. Khi deploy thay đổi kiến trúc, metric, tên resource hoặc quyền IAM, thay đổi runbook liên quan trong cùng quy trình phát hành.

Một runbook không được cập nhật sẽ tạo rủi ro vận hành. Nếu lệnh hoặc dashboard đã thay đổi, hãy sửa tài liệu và kiểm tra lại theo môi trường staging hoặc quy trình kiểm thử an toàn.

## 4. Trực vận hành (on-call)

On-call là cơ chế phân công người chịu trách nhiệm nhận cảnh báo và bắt đầu phản ứng trong một khoảng thời gian xác định. Mục tiêu là có người tiếp nhận sự cố liên tục, không phụ thuộc vào việc một kỹ sư cụ thể có mặt trong văn phòng.

### Thiết kế lịch trực

Một lịch trực cần quy định:

- Primary on-call: người nhận cảnh báo đầu tiên.
- Secondary on-call: người hỗ trợ khi primary không phản hồi hoặc cần thêm chuyên môn.
- Service owner hoặc subject matter expert: người hiểu sâu service và có quyền quyết định kỹ thuật.
- Incident commander: người điều phối khi incident được tuyên bố.
- Escalation manager: người chịu trách nhiệm gọi cấp quản lý hoặc nhóm liên quan khi vượt ngưỡng.

Lịch trực nên có thời gian bàn giao rõ ràng, thời gian phản hồi mục tiêu và quy tắc thay ca. Không để một cá nhân trực liên tục quá lâu; bảo đảm có backup khi nghỉ phép, ốm hoặc mất kết nối.

### Handoff giữa các ca trực

Một handoff tốt ghi lại:

- Incident đang mở và mức độ nghiêm trọng.
- Alert đang firing hoặc có xu hướng bất thường.
- Thay đổi production gần đây.
- Công việc điều tra đang dở và giả thuyết đã loại trừ.
- Tác vụ có thời hạn hoặc cửa sổ bảo trì sắp tới.
- Người đang sở hữu từng action item.

Handoff cần được xác nhận bởi người nhận. Chỉ gửi một tin nhắn “không có gì mới” mà không kiểm tra dashboard, incident queue và cảnh báo đang mở sẽ tạo khoảng trống trách nhiệm.

### Phản hồi cảnh báo

Mỗi alert page nên có:

- Tên service và môi trường.
- Triệu chứng và mức độ ảnh hưởng dự kiến.
- Dashboard và runbook liên quan.
- Thời gian bắt đầu và điều kiện kích hoạt.
- Hướng dẫn xác nhận alert có thực sự ảnh hưởng người dùng hay không.

Người trực cần xác nhận đã nhận page trong thời gian quy định. Nếu không phản hồi, hệ thống escalation chuyển đến secondary hoặc nhóm quản lý. Nếu alert không actionable hoặc liên tục báo giả, hãy ghi nhận và tạo công việc cải thiện alert thay vì âm thầm bỏ qua.

### Bảo vệ sức khỏe người trực

On-call fatigue làm tăng nguy cơ bỏ sót cảnh báo và thao tác sai. Đội ngũ nên:

- Giảm alert noise và gom cảnh báo có cùng nguyên nhân.
- Dùng page cho tình huống cần hành động ngay; gửi ticket cho việc không khẩn cấp.
- Bảo đảm thời gian nghỉ bù sau incident lớn theo chính sách tổ chức.
- Luân phiên hợp lý và có backup chuyên môn.
- Theo dõi số page, thời gian trực, thời gian xử lý và công việc lặp lại.
- Tự động hóa các thao tác có quy tắc rõ ràng, sau khi đánh giá rủi ro.

## 5. Phân loại severity và điều kiện escalation

Severity giúp mọi người hiểu mức độ ưu tiên và tốc độ phản ứng. Tổ chức nên định nghĩa severity theo tác động đến người dùng, phạm vi, dữ liệu và thời gian kéo dài.

Một thang tham khảo:

| Mức | Tác động | Phản ứng |
|---|---|---|
| SEV-1 / Critical | Dịch vụ cốt lõi ngừng hoạt động diện rộng, mất dữ liệu hoặc rủi ro bảo mật nghiêm trọng đang diễn ra | Page ngay, lập incident command, cập nhật liên tục |
| SEV-2 / High | Chức năng quan trọng suy giảm đáng kể, nhiều người dùng bị ảnh hưởng hoặc workaround hạn chế | Kích hoạt nhóm service và dependency, theo dõi sát |
| SEV-3 / Medium | Ảnh hưởng có giới hạn, có workaround và chưa đe dọa SLO diện rộng | Tạo incident/ticket, xử lý trong khung ưu tiên |
| SEV-4 / Low | Lỗi nhỏ, cảnh báo đơn lẻ hoặc vấn đề chưa có tác động người dùng rõ ràng | Theo dõi và đưa vào backlog phù hợp |

Severity ban đầu có thể được nâng khi phạm vi ảnh hưởng mở rộng hoặc xuất hiện bằng chứng về mất dữ liệu, lộ thông tin hay vi phạm nghĩa vụ. Hạ severity chỉ sau khi có bằng chứng tác động đã giảm và người chịu trách nhiệm đồng ý.

### Escalation theo thời gian và chuyên môn

Escalation không chỉ là gọi quản lý. Nó có thể chuyển incident đến người có quyền truy cập, kiến thức hoặc trách nhiệm phù hợp.

Ví dụ:

- Primary on-call không xác nhận page trong thời gian phản hồi: chuyển secondary.
- Lỗi nằm ở Cloud SQL hoặc network: gọi owner của dependency.
- Incident vượt ngưỡng SEV-1: chỉ định incident commander và communications lead.
- Có dấu hiệu credential bị lộ hoặc truy cập trái phép: kích hoạt security incident process và nhóm bảo mật.
- Có khả năng ảnh hưởng hợp đồng hoặc dữ liệu khách hàng: thông báo các đầu mối pháp lý, privacy hoặc customer support theo quy trình nội bộ.

Không đưa bí mật, token hoặc dữ liệu cá nhân vào kênh escalation công khai. Chỉ chia sẻ thông tin tối thiểu cần thiết để nhóm xử lý.

## 6. Incident command: tổ chức phản ứng có điều phối

Khi incident lớn có nhiều người cùng điều tra, cần một người chịu trách nhiệm điều phối thay vì để mọi người tự thay đổi hệ thống song song.

### Các vai trò chính

| Vai trò | Trách nhiệm |
|---|---|
| Incident Commander (IC) | Xác định mục tiêu, ưu tiên, phân công, quyết định escalation và kết thúc incident |
| Operations Lead | Điều tra kỹ thuật, đề xuất và thực hiện mitigation/recovery |
| Communications Lead | Cập nhật trạng thái cho người dùng, quản lý và nhóm liên quan |
| Scribe | Ghi timeline, quyết định, giả thuyết, thay đổi và tác động |
| Subject Matter Expert | Cung cấp kiến thức về service hoặc dependency cụ thể |

Với incident nhỏ, một người có thể kiêm nhiều vai trò. Với incident lớn, nên tách vai trò để IC tập trung vào điều phối và không bị cuốn vào từng lệnh kỹ thuật.

### Nhịp điều phối

IC có thể duy trì một nhịp làm việc ngắn:

1. Nêu tình trạng hiện tại và mức severity.
2. Xác định mục tiêu giảm thiểu tiếp theo.
3. Giao một người chịu trách nhiệm cho mỗi nhánh điều tra.
4. Chỉ định thời điểm cập nhật tiếp theo.
5. Ghi quyết định và điều kiện chuyển bước.

Mọi thay đổi production cần có người thực hiện, mục tiêu và kết quả dự kiến. Tránh nhiều người cùng chạy lệnh thay đổi cấu hình mà không biết trạng thái hiện tại.

### Tuyên bố và đóng incident

Incident nên có một kênh hoặc record chính thức chứa severity, IC, service bị ảnh hưởng, thời điểm bắt đầu và liên kết tài liệu điều phối. Chỉ đóng incident khi:

- Tác động tới người dùng đã dừng hoặc trở về mức chấp nhận được.
- SLI/SLO và business checks được xác nhận ổn định trong khoảng quan sát phù hợp.
- Mitigation tạm thời đã có owner và kế hoạch xử lý lâu dài.
- Các nhóm liên quan đã nhận cập nhật cuối.
- Timeline và dữ liệu cần cho postmortem được lưu lại.

Nếu dịch vụ đã hoạt động trở lại nhưng vẫn còn rủi ro tái phát, incident có thể được chuyển sang trạng thái monitoring hoặc follow-up theo quy trình tổ chức.

## 7. Điều tra sự cố bằng công cụ GCP

Cloud Monitoring, Cloud Logging, Cloud Trace và Error Reporting cung cấp các góc nhìn bổ sung. Người trực nên bắt đầu từ alert và triệu chứng, sau đó mở rộng điều tra theo thời gian và dependency.

### Cloud Monitoring

Dùng Monitoring để:

- Xác nhận alert đang firing và resource liên quan.
- Xem metrics trước, trong và sau thời điểm incident.
- So sánh revision, zone, region hoặc service khi có label phù hợp.
- Kiểm tra SLO compliance và burn rate.
- Xác định saturation như CPU, memory, concurrency, connection pool hoặc backlog.

Dashboard nên có một trang tổng quan service và các dashboard chuyên sâu cho dependency. Đặt link trực tiếp từ alert đến dashboard hoặc runbook để giảm thời gian tìm kiếm.

### Cloud Logging

Logs giúp xác định sự kiện và ngữ cảnh. Một truy vấn Logs Explorer minh họa cho Cloud Run:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="checkout"
severity>=ERROR
timestamp >= "2026-11-19T00:00:00Z"
~~~

Thay tên service và thời gian bằng thông tin incident thực tế. Có thể bổ sung revision, region, trace hoặc các trường JSON có cấu trúc để thu hẹp kết quả.

Với GKE, có thể lọc theo resource type Kubernetes container và các label như cluster name, namespace name, pod name. Với Compute Engine, dùng resource type tương ứng và đối chiếu instance, zone, log name.

Không sao chép nguyên payload nhạy cảm vào incident channel. Khi cần lưu bằng chứng, hãy dùng log access có kiểm soát và tuân thủ retention policy.

### Cloud Trace và Error Reporting

Trace giúp theo dõi một request qua các service. Nếu checkout chậm, trace có thể cho thấy phần thời gian nằm ở Cloud Run, Cloud SQL hoặc lời gọi API bên ngoài. Error Reporting nhóm stack trace và lỗi ứng dụng để xác định lỗi mới hoặc lỗi đang tăng.

### Cloud Audit Logs

Audit Logs hữu ích khi nghi ngờ sự cố bắt nguồn từ thay đổi cấu hình hoặc quyền. Kiểm tra:

- Ai đã thay đổi IAM policy, service configuration hoặc firewall rule?
- Thao tác nào xảy ra ngay trước thời điểm sự cố?
- Principal nào thực hiện hành động?
- Thay đổi có nằm trong change record được phê duyệt không?

Admin Activity audit logs được ghi cho nhiều thao tác quản trị; Data Access logs có thể cần được bật cho những loại truy cập cụ thể và có thể ảnh hưởng đến chi phí. Xác minh loại log và retention đang áp dụng cho resource trước khi incident xảy ra.

## 8. Runbook mẫu: Cloud Run tăng HTTP 5xx

Tình huống: Cloud Monitoring page vì tỷ lệ HTTP 5xx của service checkout tăng cao sau một lần phát hành.

### Trigger và impact

- Alert: tỷ lệ 5xx vượt ngưỡng hoặc SLO burn rate cao.
- Service: Cloud Run **checkout**.
- Impact cần xác minh: người dùng không hoàn tất checkout, retry tăng, đơn hàng có thể được tạo một phần.
- Severity ban đầu: SEV-2; nâng lên SEV-1 nếu giao dịch cốt lõi ngừng hoạt động trên diện rộng hoặc có nguy cơ sai lệch dữ liệu.

### Chẩn đoán

1. Xác nhận project, region và service trong alert.
2. Mở dashboard checkout, xem request count, 5xx, latency và instance count.
3. So sánh thời điểm bắt đầu lỗi với lịch deploy hoặc thay đổi cấu hình.
4. Xem revision nào đang nhận traffic.
5. Lọc Cloud Logging theo service, revision và severity.
6. Kiểm tra trace để tìm dependency có lỗi hoặc latency cao.
7. Kiểm tra Cloud SQL connection count, quota và trạng thái dependency.

Lệnh đọc trạng thái service:

~~~bash
gcloud run services describe checkout \
  --region REGION \
  --project PROJECT_ID
~~~

Liệt kê revision:

~~~bash
gcloud run revisions list \
  --service checkout \
  --region REGION \
  --project PROJECT_ID
~~~

Các lệnh trên chỉ đọc metadata. Xác minh đúng project và region trước khi sử dụng.

### Mitigation

Nếu có bằng chứng revision mới gây lỗi và revision trước vẫn hoạt động ổn định, IC có thể yêu cầu rollback traffic về revision đã biết là tốt. Trước khi thay đổi, xác minh revision đích, traffic hiện tại và khả năng tương thích với schema/database/config hiện tại.

Ví dụ lệnh chuyển 100% traffic về revision đã xác minh:

~~~bash
gcloud run services update-traffic checkout \
  --to-revisions REVISION_NAME=100 \
  --region REGION \
  --project PROJECT_ID
~~~

Đây là thao tác thay đổi production. Chỉ thực hiện theo quy trình phê duyệt và xác nhận của incident commander hoặc người có quyền. Nếu lỗi do Cloud SQL, rollback ứng dụng có thể không giải quyết được; cần escalation cho database owner.

### Verification

- 5xx trở lại mức bình thường.
- Request latency và throughput ổn định.
- Tỷ lệ checkout thành công và business transaction được xác nhận.
- Không có tăng bất thường của đơn hàng trùng hoặc trạng thái giao dịch dở dang.
- Theo dõi qua ít nhất một khoảng thời gian đủ đại diện cho traffic.

Ghi lại revision trước/sau, thời điểm thay đổi, người thực hiện và kết quả. Tạo follow-up để tìm nguyên nhân và bổ sung kiểm thử/canary nếu cần.

## 9. Runbook mẫu: GKE Pod CrashLoopBackOff

Tình huống: alert cho thấy một deployment có pod liên tục restart, làm giảm số replica sẵn sàng.

### Chẩn đoán

1. Xác định project, cluster, namespace và deployment từ alert.
2. Kiểm tra pod readiness, restart count và events.
3. Xem logs của container hiện tại và previous container.
4. Kiểm tra image, config map, secret reference và resource requests/limits.
5. Xem node pressure, quota và trạng thái node.
6. Đối chiếu deployment history với thời điểm bắt đầu lỗi.

Lấy credentials của cluster:

~~~bash
gcloud container clusters get-credentials CLUSTER_NAME \
  --region REGION \
  --project PROJECT_ID
~~~

Kiểm tra pod và events:

~~~bash
kubectl get pods -n NAMESPACE
kubectl get events -n NAMESPACE --sort-by=.lastTimestamp
kubectl describe pod POD_NAME -n NAMESPACE
~~~

Đọc logs của container trước đó:

~~~bash
kubectl logs POD_NAME -n NAMESPACE --previous
~~~

### Mitigation và escalation

Nếu lỗi bắt đầu sau một rollout và image/config mới là yếu tố đã xác minh, phối hợp với owner để rollback deployment theo release process. Nếu nguyên nhân là secret không truy cập được, node pressure hoặc dependency bên ngoài, escalation đến nhóm quản lý tương ứng.

Không xóa pod hàng loạt hoặc restart node khi chưa xác định nguyên nhân. Việc xóa pod có thể làm mất bằng chứng và không giải quyết được lỗi cấu hình khiến pod tiếp tục crash.

### Verification

- Replica desired và ready trở lại mức yêu cầu.
- Restart rate giảm về bình thường.
- Không còn event lỗi lặp lại.
- Request error rate và latency của service ổn định.
- Theo dõi HPA, node capacity và dependency trong khoảng quan sát đã định.

## 10. Runbook mẫu: Cloud SQL connection exhaustion

Tình huống: Cloud Run hoặc GKE báo lỗi không lấy được database connection; checkout timeout hoặc trả lỗi.

### Chẩn đoán

- Kiểm tra Cloud SQL connections, CPU, memory, query latency và database logs.
- Đối chiếu số instance ứng dụng, concurrency và connection pool.
- Kiểm tra deploy mới có làm tăng số kết nối trên mỗi instance không.
- Tìm connection không được trả về pool hoặc query chạy lâu.
- Kiểm tra quota, maintenance event và tình trạng failover nếu có.

### Mitigation

- Giảm concurrency hoặc traffic theo quy trình đã kiểm chứng nếu ứng dụng tạo quá nhiều kết nối.
- Tạm dừng rollout mới nếu thay đổi vừa phát hành làm tăng connection.
- Giảm số connection từ workload theo cấu hình có kiểm soát.
- Escalate cho database owner trước thao tác terminate connection hoặc thay đổi instance tier.
- Nếu database đã quá tải, tránh tăng retry từ ứng dụng vì điều đó có thể làm tải tăng thêm.

### Verification

- Connection count nằm dưới giới hạn vận hành đã đặt.
- Query latency và lỗi kết nối giảm.
- Ứng dụng hoàn tất giao dịch bình thường.
- Không có backlog tăng kéo dài ở các consumer phụ thuộc database.
- Xác định action item về connection pooling, concurrency và capacity.

## 11. Giao tiếp trong incident

Giao tiếp tốt giúp các bên biết điều gì đang xảy ra, ai đang xử lý và khi nào có cập nhật tiếp theo. Không nên chờ có nguyên nhân gốc mới gửi thông báo đầu tiên.

Một thông báo trạng thái nên có:

- Incident ID và severity.
- Dịch vụ/chức năng bị ảnh hưởng.
- Thời điểm bắt đầu và phạm vi ảnh hưởng đã xác nhận.
- Biện pháp đang thực hiện.
- Workaround nếu có.
- Thời điểm cập nhật tiếp theo.

Ví dụ:

~~~text
INC-2026-042 | SEV-2 | Checkout API

Trạng thái: Đang điều tra.
Ảnh hưởng: Một phần request checkout tại region đang trả lỗi 5xx.
Bắt đầu: 10:15 UTC.
Đã xác nhận: Tỷ lệ lỗi tăng sau thay đổi revision gần nhất.
Đang thực hiện: Nhóm vận hành so sánh revision và kiểm tra dependency Cloud SQL.
Workaround: Chưa có workaround được xác nhận.
Cập nhật tiếp theo: 10:30 UTC.
~~~

Chỉ thông báo những gì đã xác minh. Nếu nguyên nhân chưa rõ, nói rõ đang điều tra. Không suy đoán lỗi do nhà cung cấp, khách hàng hoặc một cá nhân khi chưa có bằng chứng.

### Kênh và nhịp cập nhật

Tổ chức nên xác định trước:

- Kênh nội bộ để điều phối kỹ thuật.
- Kênh cập nhật cho quản lý, customer support và các nhóm sản phẩm.
- Kênh status page hoặc thông báo khách hàng nếu incident đủ nghiêm trọng.
- Người duyệt nội dung khi có ảnh hưởng pháp lý, bảo mật hoặc dữ liệu cá nhân.
- Chu kỳ cập nhật theo severity và cam kết dịch vụ.

Cloud Monitoring có thể gửi notification qua các notification channel được hỗ trợ như email, SMS, mobile app hoặc tích hợp webhook/Pub/Sub tùy cấu hình và khả năng hiện hành. Alert notification là tín hiệu để kích hoạt quy trình; incident coordination và customer communication vẫn cần một quy trình có owner rõ ràng.

## 12. Kết thúc sự cố và viết postmortem

Kết thúc incident là bước chuyển từ phản ứng khẩn cấp sang cải thiện hệ thống. Postmortem nên được viết khi sự cố đủ đáng kể, có ảnh hưởng đến SLO, người dùng, dữ liệu hoặc cần phối hợp nhiều nhóm.

### Cấu trúc postmortem

1. **Summary:** mô tả ngắn gọn điều gì đã xảy ra.
2. **Impact:** người dùng, khu vực, chức năng, thời gian và dữ liệu bị ảnh hưởng.
3. **Detection:** alert hoặc báo cáo nào phát hiện sự cố; thời gian phát hiện.
4. **Timeline:** các sự kiện, quyết định, mitigation và khôi phục.
5. **Root cause và contributing factors:** nguyên nhân chính cùng các điều kiện làm sự cố xảy ra hoặc khó phát hiện.
6. **Response review:** điều gì hoạt động tốt, điều gì gây chậm trễ.
7. **Action items:** công việc ngăn tái diễn, cải thiện phát hiện và giảm thời gian khôi phục.
8. **Owners và due dates:** người chịu trách nhiệm và hạn hoàn thành.

Postmortem theo hướng blameless tập trung vào hệ thống, thiết kế, thông tin và điều kiện làm việc. Mục tiêu là hiểu vì sao các guardrail không ngăn được lỗi và cải thiện chúng. Điều này vẫn yêu cầu owner và deadline cụ thể cho các hành động khắc phục.

### Viết action item có thể kiểm chứng

Action item tốt nêu hành động, owner, deadline, ưu tiên và tiêu chí hoàn tất.

Ví dụ:

| Action item | Owner | Tiêu chí hoàn tất |
|---|---|---|
| Thêm alert theo burn rate cho checkout latency SLO | SRE | Alert được kiểm thử trên dữ liệu mô phỏng và có runbook |
| Bổ sung test tải cho connection pool | Backend | Test chứng minh concurrency mục tiêu không vượt connection budget |
| Thêm canary analysis cho revision Cloud Run | Platform | Rollout tự dừng khi SLI vượt ngưỡng đã định |
| Cập nhật runbook Cloud SQL | Database team | Một người trực khác thực hiện diễn tập thành công |

Không đóng action item chỉ vì đã tạo ticket hoặc cập nhật tài liệu. Cần kiểm tra thay đổi đã được triển khai và tạo ra kết quả mong muốn.

## 13. Đo lường hiệu quả của vận hành

Không nên đánh giá chất lượng trực ca chỉ bằng số incident đã đóng. Các chỉ số có thể giúp tổ chức tìm điểm nghẽn:

| Chỉ số | Ý nghĩa |
|---|---|
| MTTD (Mean Time to Detect) | Thời gian trung bình từ lúc sự cố bắt đầu đến khi được phát hiện |
| MTTA (Mean Time to Acknowledge) | Thời gian trung bình từ page đến khi có người xác nhận |
| MTTR (Mean Time to Restore/Resolve) | Thời gian trung bình để khôi phục hoặc giải quyết, cần định nghĩa rõ mốc kết thúc |
| Reopen/recur rate | Tỷ lệ incident tái mở hoặc lặp lại |
| Alert actionability | Tỷ lệ page thực sự cần hành động |
| Runbook success rate | Tỷ lệ lần xử lý mà runbook giúp người trực hoàn thành đúng quy trình |
| Toil hours | Thời gian dành cho công việc vận hành lặp lại |
| Postmortem action completion | Tỷ lệ action item hoàn thành đúng hạn và được xác minh |

MTTR có nhiều cách định nghĩa. Hãy thống nhất đo đến thời điểm mitigation, service restored hay resolution hoàn toàn. Khi so sánh giữa các service, dùng cùng định nghĩa và phân loại severity để tránh kết luận sai.

Các chỉ số vận hành dùng để cải thiện quy trình và hệ thống, không nên biến thành bảng xếp hạng cá nhân. Một nhóm có nhiều incident được báo cáo có thể đang minh bạch hơn, trong khi nhóm có ít incident có thể đang thiếu telemetry hoặc không ghi nhận đầy đủ.

## 14. Quy trình incident management mẫu trên GCP

Một quy trình có thể áp dụng cho dịch vụ Cloud Run, GKE và Cloud SQL:

| Giai đoạn | Người chịu trách nhiệm | Hoạt động | Kết quả |
|---|---|---|---|
| Detect | Monitoring/on-call | Nhận page, xác nhận alert | Incident được ghi nhận |
| Triage | Primary on-call | Xác định service, impact, severity | Severity và owner ban đầu |
| Command | Incident commander | Chỉ định vai trò, mục tiêu và nhịp cập nhật | Kênh điều phối và incident record |
| Investigate | Operations/SME | Dùng metrics, logs, traces và audit logs | Giả thuyết có bằng chứng |
| Mitigate | Operations lead | Rollback, giảm traffic hoặc chuyển degraded mode | Ảnh hưởng giảm |
| Verify | Service owner | Kiểm tra SLI, business checks và dependency | Xác nhận phục hồi |
| Communicate | Communications lead | Gửi cập nhật và thông báo kết thúc | Các bên được thông tin |
| Learn | Service owner/SRE | Postmortem và action items | Cải tiến được theo dõi |

### Ví dụ: checkout lỗi sau release

1. Cloud Monitoring page vì burn rate của checkout tăng.
2. Primary on-call xác nhận page, mở runbook Cloud Run 5xx và tạo incident record.
3. Người trực thấy lỗi tập trung ở revision mới; IC chỉ định backend kiểm tra log và platform chuẩn bị rollback.
4. Trace cho thấy request lỗi trước khi ghi đơn hàng; Cloud SQL vẫn hoạt động bình thường.
5. IC phê duyệt rollback traffic về revision ổn định sau khi xác nhận tương thích schema.
6. Operations lead thực hiện thay đổi, service owner kiểm tra error rate, latency và giao dịch.
7. Communications lead cập nhật incident đã được giảm thiểu; nhóm tiếp tục theo dõi.
8. Sau khi ổn định, nhóm viết postmortem và bổ sung canary check cho business success metric.

Quy trình này giúp người trực biết khi nào cần gọi thêm người, ai ra quyết định và bằng chứng nào xác nhận dịch vụ đã phục hồi.

## 15. Checklist cho runbook và on-call readiness

- [ ] Mỗi service quan trọng có owner, primary/secondary on-call và escalation path.
- [ ] Alert page liên kết trực tiếp tới dashboard, runbook và incident channel.
- [ ] Runbook có trigger, impact, preconditions, diagnosis, mitigation, rollback và verification.
- [ ] Các lệnh production được đánh dấu rõ mức độ rủi ro và điều kiện phê duyệt.
- [ ] Project, region, cluster, namespace và service được xác minh trước thao tác.
- [ ] On-call schedule có handoff được xác nhận và backup khi người trực không phản hồi.
- [ ] Severity có tiêu chí tác động và điều kiện escalation.
- [ ] Incident commander, operations lead, communications lead và scribe có trách nhiệm rõ ràng.
- [ ] Có mẫu status update, incident record và quy tắc giao tiếp.
- [ ] Cloud Monitoring, Logging, Trace, Error Reporting và Audit Logs đủ dữ liệu cho điều tra.
- [ ] Findings/logs không làm lộ secret, token hoặc dữ liệu cá nhân.
- [ ] Incident lớn có postmortem và action items có owner, deadline, tiêu chí xác minh.
- [ ] Runbook được review định kỳ và diễn tập bởi người không phải tác giả.
- [ ] Alert noise, on-call load, MTTD, MTTA, MTTR và toil được xem xét để cải tiến.

## Kết luận

Runbook cung cấp hướng dẫn thao tác có thể kiểm chứng; on-call bảo đảm có người nhận và chịu trách nhiệm; incident management giúp nhóm phối hợp để giảm ảnh hưởng, khôi phục dịch vụ và giao tiếp rõ ràng. Trên GCP, Cloud Monitoring, Logging, Trace, Error Reporting và Audit Logs cung cấp bằng chứng để điều tra. Khi runbook được cập nhật, lịch trực có backup, escalation minh bạch và postmortem dẫn đến action items thực tế, tổ chức có thể giảm thời gian xử lý và cải thiện độ tin cậy qua từng sự cố.

## Tài liệu tham khảo

- [Google Cloud Architecture Framework: Operational excellence](https://docs.cloud.google.com/architecture/framework/operational-excellence)
- [Google Cloud: Site Reliability Engineering](https://sre.google/)
- [Google SRE Workbook: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [Google SRE Workbook: Incident response](https://sre.google/workbook/incident-response/)
- [Google SRE: Managing incidents](https://sre.google/sre-book/managing-incidents/)
- [Cloud Monitoring: Alerting overview](https://docs.cloud.google.com/monitoring/alerts)
- [Cloud Monitoring: Notification channels](https://docs.cloud.google.com/monitoring/support/notification-options)
- [Cloud Logging: Logs Explorer](https://docs.cloud.google.com/logging/docs/view/logs-explorer-interface)
- [Cloud Trace documentation](https://docs.cloud.google.com/trace/docs)
- [Error Reporting documentation](https://docs.cloud.google.com/error-reporting/docs)
- [Cloud Audit Logs overview](https://docs.cloud.google.com/logging/docs/audit)
- [Cloud Run documentation](https://docs.cloud.google.com/run/docs)
- [Google Kubernetes Engine documentation](https://docs.cloud.google.com/kubernetes-engine/docs)


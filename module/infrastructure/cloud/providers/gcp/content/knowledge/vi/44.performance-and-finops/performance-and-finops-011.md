# Recommender và đánh giá đề xuất tối ưu

Khi một tổ chức sử dụng nhiều dịch vụ Google Cloud, chi phí và cấu hình hạ tầng thay đổi liên tục: máy ảo bị cấp dư CPU, đĩa không còn gắn với VM, cụm GKE có workload chưa tối ưu, bảng BigQuery quét nhiều dữ liệu hoặc một service account sở hữu quyền không cần thiết. Rà soát thủ công tất cả tài nguyên rất tốn công, nhưng **áp dụng mọi gợi ý tự động** cũng có thể gây gián đoạn, mất dữ liệu hoặc vi phạm yêu cầu bảo mật.

**Google Cloud Recommender** cung cấp các insight và recommendation dựa trên đặc điểm sử dụng tài nguyên, dữ liệu quan sát và các quy tắc của từng dịch vụ. Các gợi ý này có thể xuất hiện trong Active Assist, FinOps hub, các trang tối ưu hóa hoặc ngay trong giao diện dịch vụ. Nhóm vận hành cần biến chúng thành quyết định có kiểm chứng: đánh giá lợi ích, hiểu tác động đến SLO, xem xét ràng buộc tài chính, triển khai bằng quy trình thay đổi và đo kết quả thực tế.

Bài học này tập trung vào **cách đọc và đánh giá đề xuất tối ưu** cho hạ tầng GCP, từ Compute Engine, Cloud SQL, GKE, Cloud Run, Cloud Storage đến BigQuery và IAM. Mục tiêu không phải chạy lệnh xóa tài nguyên nhanh nhất, mà là xây dựng một vòng lặp FinOps và SRE có thể truy vết, an toàn và đo được giá trị.

## 1. Recommender là gì và không phải là gì?

Recommender là dịch vụ tạo ra những gợi ý tối ưu cho một số loại tài nguyên hoặc hành vi sử dụng trên Google Cloud. Mỗi loại recommender có mã định danh riêng, phạm vi hỗ trợ và dữ liệu đầu vào phù hợp với dịch vụ đang phân tích.

Một recommendation có thể đề nghị:

- Đổi machine type của Compute Engine VM theo xu hướng sử dụng.
- Xem xét ngừng hoặc xóa tài nguyên được nhận diện là không hoạt động.
- Điều chỉnh cấu hình Cloud SQL nếu mức cấp phát không tương xứng tải.
- Cải thiện khả năng phân bổ tài nguyên của GKE workload.
- Xem xét partitioning hoặc clustering đối với BigQuery table.
- Điều chỉnh một chính sách IAM để giảm quyền không cần thiết.
- Cân nhắc mô hình chiết khấu cam kết khi có nhu cầu tiêu thụ ổn định.

**Recommendation không phải mệnh lệnh bắt buộc.** Một VM có mức CPU thấp có thể là standby DR, một disk không gắn VM có thể là bản phục hồi đang được giữ, và một IAM role ít được dùng có thể cần cho sự cố hiếm gặp. Mọi đề xuất phải được đặt trong bối cảnh nghiệp vụ và kiến trúc.

| Thuật ngữ | Ý nghĩa |
|---|---|
| Recommender | Loại dịch vụ hoặc bộ quy tắc sinh gợi ý cho một nhóm tài nguyên |
| Insight | Thông tin quan sát giúp giải thích trạng thái hoặc xu hướng sử dụng |
| Recommendation | Hành động tối ưu được đề xuất dựa trên dữ liệu/insight |
| Resource | Tài nguyên bị ảnh hưởng như VM, disk, table, service hoặc IAM policy |
| Impact | Tác động dự kiến về cost, performance, security hoặc mục tiêu khác |
| Operation group | Nhóm thao tác mà gợi ý mô tả để thực hiện thay đổi |
| State | Trạng thái theo dõi việc nhóm đã xử lý đề xuất đến đâu |
| Etag | Giá trị phục vụ kiểm tra phiên bản khi cập nhật trạng thái đề xuất |

Recommender không thay thế Cloud Monitoring, Cloud Billing, cấu hình quota, kiểm tra tải, backup hay change approval. Nó tạo đầu vào cho quyết định; các hệ thống và quy trình khác xác minh quyết định đó.

## 2. Các nơi xem đề xuất trên Google Cloud

Dữ liệu recommendation có thể được đưa ra qua nhiều bề mặt khác nhau.

| Bề mặt | Người dùng điển hình | Mục đích |
|---|---|---|
| Recommender API và gcloud | Platform/SRE/automation | Lấy đề xuất có cấu trúc, lọc và theo dõi trạng thái |
| Active Assist trong Google Cloud console | Người quản trị project | Duyệt các đề xuất và xem thông tin tác động |
| FinOps hub trong Cloud Billing | FinOps/billing owners | Tổng hợp cơ hội chi phí và tiến độ tối ưu |
| Trang tối ưu hóa trong Cloud Hub | Developer và platform team | Khám phá đề xuất có liên quan đến workload |
| Trang cấu hình của một sản phẩm | Chủ sở hữu dịch vụ | Xem gợi ý ngay trong bối cảnh tài nguyên |

Không nên mặc định mọi recommender xuất hiện ở tất cả các giao diện. Một số loại gợi ý có phạm vi project, billing account, folder hoặc organization; một số được công bố ở location cấp vùng, zone hoặc `global`.

### Phân biệt FinOps hub và Recommender API

FinOps hub ưu tiên góc nhìn tối ưu chi phí trên phạm vi tài khoản thanh toán và có thể xử lý các cơ hội trùng lặp để tổng hợp. Recommender API trả về các recommendation của từng recommender cụ thể. Vì vậy, **không nên cộng máy móc tổng tiền tiết kiệm từ mọi dòng API và coi đó là tổng cơ hội chi phí duy nhất**.

Cùng một VM có thể vừa được đề nghị rightsizing, vừa nằm trong một phương án cam kết sử dụng. Hai lợi ích này có thể giao thoa và không nhất thiết cộng được với nhau.

## 3. Insight và recommendation liên quan như thế nào?

**Insight** mô tả dữ kiện được quan sát, ví dụ mức sử dụng tài nguyên thấp, hoạt động ít hoặc cấu hình hiện tại có dấu hiệu rủi ro. **Recommendation** chuyển các tín hiệu đó thành một gợi ý thay đổi cụ thể.

~~~mermaid
flowchart LR
    A[Usage and configuration signals] --> B[Recommender analysis]
    B --> C[Insight]
    B --> D[Recommendation]
    C --> E[Human impact review]
    D --> E
    E --> F{Safe and valuable?}
    F -->|Yes| G[Plan change and approval]
    F -->|Not yet| H[Defer or dismiss with reason]
    G --> I[Apply in controlled window]
    I --> J[Measure outcome and close loop]
~~~

Ví dụ:

- Insight: một instance thường sử dụng ít CPU trong khoảng quan sát.
- Recommendation: xem xét máy có cấu hình nhỏ hơn.
- Context do nhóm bổ sung: đây là máy xử lý batch có đỉnh tải cuối tháng.
- Quyết định: chưa rightsizing ngay; chạy load test và đối chiếu lịch batch trước.

Những kết luận về dữ liệu hay độ phù hợp của cấu hình phải được kiểm chứng. Không được suy ra rằng **idle** đồng nghĩa với **không có chủ sở hữu** hoặc **có thể xóa an toàn**.

## 4. Dữ liệu và cấu trúc của một recommendation

Một recommendation trong API có những trường thường gặp:

| Trường | Mục đích |
|---|---|
| `name` | Tên tài nguyên recommendation gồm project, location, recommender ID và recommendation ID |
| `description` | Mô tả hành động được đề xuất |
| `recommenderSubtype` | Phân loại cụ thể trong một recommender |
| `primaryImpact` | Tác động chính, ví dụ cost hoặc performance |
| `additionalImpact` | Các tác động phụ nếu loại recommender cung cấp |
| `content.operationGroups` | Các thao tác được mô tả đối với tài nguyên |
| `stateInfo.state` | Trạng thái xử lý |
| `etag` | Giá trị chống cập nhật trên phiên bản cũ |
| `priority` | Độ ưu tiên do recommender cung cấp, khi có |
| `lastRefreshTime` | Mốc dữ liệu recommendation được làm mới |
| `insightReference` | Tham chiếu đến insight liên quan, khi có |

Tên resource có dạng khái niệm:

~~~text
projects/PROJECT_ID/locations/LOCATION/
  recommenders/RECOMMENDER_ID/recommendations/RECOMMENDATION_ID
~~~

Chuỗi trên được tách dòng để dễ đọc. Resource name thực tế là một chuỗi đầy đủ, không có xuống dòng.

### Operation group là đề xuất thay đổi, không phải script đáng tin cậy tuyệt đối

Một operation có thể biểu diễn `test`, `add`, `replace`, `remove` hoặc thao tác khác đối với tài nguyên/cấu hình. Operations mô tả trạng thái mà hệ thống gợi ý, nhưng nhóm cần kiểm tra:

- Resource chính xác và environment đang bị tác động.
- Thuộc tính trước/sau thay đổi.
- Các thao tác phụ thuộc hoặc điều kiện `test`.
- Những cấu hình do Terraform hoặc công cụ IaC quản lý.
- Mức độ cập nhật của dữ liệu recommendation.

Không copy operation và thực hiện vô điều kiện trên production. Một operation đúng lúc đề xuất được tạo có thể trở nên không phù hợp sau khi workload thay đổi.

## 5. Vòng đời trạng thái của recommendation

Recommender hỗ trợ các trạng thái dùng để ghi nhận tiến trình xử lý:

| Trạng thái | Ý nghĩa vận hành |
|---|---|
| `ACTIVE` | Gợi ý còn hiệu lực trong hệ thống và chưa được nhóm xử lý |
| `CLAIMED` | Có người hoặc workflow nhận xử lý gợi ý |
| `SUCCEEDED` | Ghi nhận đề xuất đã được thực hiện thành công |
| `FAILED` | Ghi nhận lần áp dụng đề xuất không thành công |
| `DISMISSED` | Nhóm chọn không thực hiện gợi ý tại thời điểm đó |

Recommendation ở trạng thái ACTIVE có thể được Google cập nhật khi điều kiện tài nguyên thay đổi. Trạng thái CLAIMED thường giữ nội dung recommendation ổn định cho quy trình đang thực hiện. Sau khi đã triển khai, cần ghi rõ kết quả thay vì để trạng thái CLAIMED kéo dài mãi.

~~~mermaid
flowchart TD
    A[ACTIVE] --> B[CLAIMED]
    A --> C[DISMISSED]
    B --> D[SUCCEEDED]
    B --> E[FAILED]
    C --> F[Re-evaluate if conditions change]
    F --> A
    E --> G[Analyze and retry under change control]
~~~

Sơ đồ là luồng vận hành tham khảo, không thể hiện mọi chuyển trạng thái hợp lệ của Recommender API.

### Etag và thay đổi đồng thời

Khi cập nhật state qua CLI/API, cần dùng `etag` của recommendation được đọc gần nhất. Nếu một người khác đã thay đổi recommendation hoặc nội dung được cập nhật, request dựa trên etag cũ có thể bị từ chối.

Không sửa etag thủ công để "ép" trạng thái. Hãy tải recommendation mới, review lại, rồi thực hiện thao tác đúng quyền.

**Đánh dấu SUCCEEDED không tự động chứng minh tài nguyên đã được tối ưu.** Đây là trạng thái quản lý recommendation; nhóm vẫn phải xác minh trạng thái thực của tài nguyên và chi phí sau thay đổi.

## 6. Những nhóm đề xuất thường gặp trong FinOps và SRE

| Nhóm | Ví dụ | Rủi ro cần cân nhắc |
|---|---|---|
| Compute Engine | Machine type rightsizing, idle VM | Gián đoạn, peak load, standby/DR |
| Disk, IP và reservation | Đĩa rời, IP không dùng, reservation dư | Mất dữ liệu hoặc phá phụ thuộc |
| Cloud SQL | Idle, overprovisioned, underprovisioned, reliability | Capacity, failover, backup, connection |
| GKE | Workload/cluster diagnosis, under/overprovision | Requests/limits, autoscaling, scheduling |
| Cloud Run | Gợi ý về CPU allocation hoặc security | Billing model, request latency, background tasks |
| BigQuery | Partition/clustering, slot/capacity | Workload thay đổi, SQL scan, slot commitments |
| Cloud Storage | Soft delete và tối ưu cấu hình lưu trữ | Khả năng phục hồi object, retention, chi phí |
| IAM | Bớt quyền dư thừa | Quyền khẩn cấp, job chạy hiếm, service identity |
| CUD | Cam kết sử dụng tài nguyên | Ràng buộc thời hạn và nguy cơ underutilization |
| Reliability/quota | HA, dung lượng đĩa, service limits | Độ tin cậy và chi phí có thể tăng |

Một số recommendation tập trung giảm chi phí; một số khác tăng bảo mật hoặc hiệu năng, thậm chí **có thể làm tăng hóa đơn**. Vì vậy, ưu tiên dựa trên mục tiêu của hệ thống chứ không chỉ dựa trên số tiền tiết kiệm.

Danh sách recommender và phạm vi hỗ trợ có thể thay đổi. Luôn xác nhận recommender ID trong tài liệu Google Cloud cho dịch vụ đang kiểm tra.

## 7. Quyền truy cập và chuẩn bị Recommender API

Trước khi sử dụng gcloud hoặc API, cần:

1. Chọn project hoặc phạm vi tài nguyên cần rà soát.
2. Xác nhận Recommender API đã được bật tại project thích hợp.
3. Cấp quyền IAM cho người xem gợi ý.
4. Xác định đúng recommender ID và location.
5. Kiểm tra quota project nếu API client yêu cầu.

Bật API tại một project thử nghiệm hoặc project được phép:

~~~bash
gcloud services enable recommender.googleapis.com \
  --project="PROJECT_ID"
~~~

Mỗi recommender có permission và role được hỗ trợ riêng, ví dụ các permission `recommender.*.list`, `recommender.*.get` và `recommender.*.update` tương ứng với loại đề xuất. Không cấp quyền quản trị rộng chỉ để đọc đề xuất.

### Nguyên tắc phân vai

| Vai trò quy trình | Quyền đề xuất |
|---|---|
| FinOps analyst | Xem chi phí và recommendations, không sửa tài nguyên |
| Resource owner/SRE | Review hiệu năng, độ tin cậy và tác động |
| Approver | Phê duyệt theo quy định thay đổi |
| Deployment identity | Chỉ thay đổi đúng resource sau approval |
| Auditor | Đọc lịch sử review, change request và kết quả |

Nên tách **quyền sửa state recommendation** khỏi **quyền sửa resource GCP**. Gắn trạng thái SUCCEEDED không tương đương có quyền resize VM hay thay IAM policy.

## 8. Xem recommendation bằng gcloud

Ví dụ liệt kê đề xuất chọn machine type cho Compute Engine VM ở một zone:

~~~bash
gcloud recommender recommendations list \
  --project="PROJECT_ID" \
  --location="asia-southeast1-a" \
  --recommender="google.compute.instance.MachineTypeRecommender" \
  --format="json"
~~~

Lệnh trên chỉ đọc recommendation, không thay đổi VM. Thay project, zone và recommender ID bằng giá trị đúng môi trường. Có thể một project không có recommendation ở thời điểm kiểm tra; kết quả rỗng không chứng minh rằng toàn bộ hạ tầng đã tối ưu.

Xem loại idle VM trong cùng zone:

~~~bash
gcloud recommender recommendations list \
  --project="PROJECT_ID" \
  --location="asia-southeast1-a" \
  --recommender="google.compute.instance.IdleResourceRecommender" \
  --format="table(name,description,stateInfo.state)"
~~~

Lọc một recommendation cụ thể và xem chi tiết:

~~~bash
gcloud recommender recommendations describe "RECOMMENDATION_ID" \
  --project="PROJECT_ID" \
  --location="asia-southeast1-a" \
  --recommender="google.compute.instance.MachineTypeRecommender" \
  --format="json"
~~~

Tên `RECOMMENDATION_ID` lấy từ kết quả list, không tự đặt. Một số loại recommendation dùng location `global` hoặc region thay cho zone; dùng location mà loại recommender yêu cầu.

### Xem insight

Có thể truy cập insight bằng Recommender API hoặc Google Cloud console, với insight type ID đúng loại. Không giả định một insight type ID tương đương recommender ID. Khi cần tự động hóa, truy vấn theo cấu trúc `projects/PROJECT_ID/locations/LOCATION/insightTypes/INSIGHT_TYPE_ID/insights` của API tương ứng.

### Thận trọng khi xuất JSON

Dữ liệu recommendation có thể chứa project ID, tên tài nguyên, cấu hình hạ tầng hoặc thông tin về chính sách IAM. Không đăng toàn bộ JSON lên kho công khai. Dùng quyền truy cập, retention và redaction thích hợp cho báo cáo.

## 9. Cách đọc impact và ước tính lợi ích

Recommendation có thể mang primary impact thuộc các nhóm như:

- **COST:** chi phí dự kiến tăng hoặc giảm.
- **PERFORMANCE:** thay đổi năng lực hoặc hiệu năng.
- **SECURITY:** cải thiện tư thế bảo mật.
- **MANAGEABILITY:** giảm công việc vận hành thủ công.
- **SUSTAINABILITY:** tác động đến phát thải theo mô hình ước tính được hỗ trợ.

Không phải mọi recommendation đều có đủ các tác động này. Một security recommendation quan trọng không thể bị gạt bỏ chỉ vì không có trường estimated savings.

### Đọc cost projection

Khi thấy con số tiết kiệm, cần hỏi:

1. Ước tính theo kỳ nào: tháng, năm hay khoảng duration khác?
2. Giá dùng là list price hay custom contract price?
3. Ước tính dựa vào khoảng sử dụng lịch sử nào?
4. Đã tính chi phí snapshot, backup, migration và downtime chưa?
5. Có CUD, credit hoặc discount khác ảnh hưởng lợi ích thực không?
6. Sau thay đổi có phát sinh chi phí egress, network hoặc support không?

Tài liệu Google Cloud nêu rằng phép tính savings trong recommendations được dùng để **so sánh và ưu tiên**; kết quả có thể dựa trên list/custom pricing tùy quyền xem billing, và không nhất thiết phản ánh credits hoặc mọi khoản giảm giá hiện có.

### Không cộng trùng các recommendation

Nếu một VM có khả năng tiết kiệm 60 USD/tháng nhờ rightsizing và có thêm đề xuất chiết khấu cam kết sử dụng dựa trên cùng phần compute, tổng tiết kiệm sau khi áp dụng cả hai không mặc định là 120 USD/tháng. Phải mô hình hóa thứ tự thay đổi và phần usage còn được áp dụng discount.

## 10. Mô hình đánh giá lợi ích tài chính

Một cách đơn giản để tính hiệu quả cho một đề xuất:

\[
\text{Net Monthly Benefit}
= \text{Avoided Cost}
- \text{Additional Ongoing Cost}
\]

Nếu có chi phí triển khai một lần:

\[
\text{Simple Payback (months)}
= \frac{\text{One-time Implementation Cost}}
       {\text{Net Monthly Benefit}}
\]

Các công thức trên mang tính quản trị cơ bản, không tính time value of money, taxes, biến động workload hay chiết khấu hợp đồng. Nếu net monthly benefit không dương, chỉ số payback không có ý nghĩa theo cách tính này.

Ví dụ minh họa:

- Một VM được đề nghị rightsizing giúp giảm chi phí danh nghĩa khoảng 140 USD/tháng.
- Backup/snapshot và giám sát bổ sung làm tăng 15 USD/tháng.
- Công triển khai, kiểm thử và cập nhật runbook quy đổi thành 200 USD một lần.
- Net benefit giả định: 125 USD/tháng; simple payback khoảng 1,6 tháng.

Nhưng nếu VM phải được nâng cấp lại vào cuối tháng do batch workload, chi phí rollback và gián đoạn có thể làm lợi ích giảm mạnh. Không kết luận chỉ từ phép tính trên.

### Phân biệt tiết kiệm dự kiến và đã ghi nhận

| Khái niệm | Cách hiểu |
|---|---|
| Potential saving | Ước tính trước khi áp dụng |
| Approved opportunity | Đề xuất đã qua review và được phép triển khai |
| Implemented change | Hạ tầng đã thực sự thay đổi |
| Realized saving | Chi phí sau thay đổi giảm so với baseline được chuẩn hóa |
| Avoided future cost | Chi phí đáng lẽ tăng theo kế hoạch nhưng đã tránh được |

Trong báo cáo FinOps, không cộng cả potential savings lẫn realized savings như thể chúng là hai khoản tiết kiệm độc lập.

## 11. Rủi ro kỹ thuật: hiệu năng, độ tin cậy và dữ liệu

Một optimization có thể trông hấp dẫn về giá nhưng làm vi phạm SLO hoặc RPO/RTO. Cần đánh giá trên workload thực.

### Câu hỏi về hiệu năng

- p95/p99 latency hiện tại còn bao nhiêu headroom?
- CPU trung bình thấp nhưng mức cao nhất vào cuối kỳ là bao nhiêu?
- Memory thường dùng và working set có phù hợp cấu hình nhỏ hơn?
- Network throughput, IOPS, disk latency hoặc concurrency có phải nút thắt?
- Autoscaling có đủ khả năng hấp thụ peak nếu giảm resource requests?
- Có tác vụ batch hoặc cron chỉ chạy hàng tuần/hàng tháng không?

### Câu hỏi về độ tin cậy

- Tài nguyên là primary, standby, DR, backup hay node điều phối?
- Nếu xóa/resize, đường failover và recovery có còn hoạt động?
- Có ràng buộc HA, placement, quota hoặc capacity reservation không?
- Mức downtime dự kiến và điều kiện rollback là gì?
- Ảnh hưởng đến replication, cluster scheduling và connection pool ra sao?

### Câu hỏi về dữ liệu

- Một disk "idle" có chứa snapshot logic hoặc dữ liệu cần khôi phục?
- Object lifecycle hoặc soft delete có đáp ứng retention và pháp lý?
- Database có backup/PITR được kiểm chứng?
- Tài nguyên có phụ thuộc được quản lý bên ngoài Terraform hay không?

Nếu thiếu dữ liệu quan sát hoặc owner không xác nhận, chọn `DEFER` thay vì áp dụng vội.

## 12. Lập ma trận ưu tiên có thể giải thích

Nhóm nên dùng bộ tiêu chí nhất quán cho mọi recommendation, đồng thời có **hard stop** đối với thay đổi có thể mất dữ liệu, thiếu backup hoặc chưa rõ chủ sở hữu.

Một cách đánh giá:

| Trục | Câu hỏi | Thang gợi ý |
|---|---|---|
| Lợi ích | Tiết kiệm/giảm rủi ro có đáng kể? | 1–5 |
| Độ tin cậy dữ liệu | Đề xuất dựa trên số liệu đủ đại diện? | 1–5 |
| Rủi ro thấp | Có dễ giữ SLO, data safety và rollback? | 1–5, điểm cao nghĩa là ít rủi ro |
| Công thực hiện thấp | Có ít bước và ít phụ thuộc? | 1–5, điểm cao nghĩa là dễ thực hiện |
| Tính cấp thiết | Có deadline bảo mật hoặc quota? | 1–5 |

Ví dụ tính điểm nội bộ:

\[
\text{Priority Score}
= 0.30B + 0.20C + 0.25R + 0.15E + 0.10U
\]

Trong đó `B` là benefit, `C` là confidence, `R` là độ an toàn (risk đảo chiều), `E` là ease và `U` là urgency. Trọng số chỉ minh họa; tổ chức cần thống nhất theo mục tiêu quản trị.

**Không cho điểm tổng thay thế điều kiện bắt buộc.** Một đề xuất xóa disk có điểm tiết kiệm cao nhưng chưa xác minh dữ liệu phải bị chặn, không được xếp lên triển khai chỉ vì điểm trung bình lớn.

### Ví dụ ma trận quyết định

| Đề xuất | Savings minh họa/tháng | Rủi ro | Confidence | Quyết định ban đầu |
|---|---:|---|---|---|
| Xóa IP không gắn tài nguyên | 15 USD | Thấp sau xác minh phụ thuộc | Cao | Candidate |
| Rightsize VM chạy batch cuối tháng | 140 USD | Trung bình/cao | Thấp nếu thiếu dữ liệu peak | Defer |
| Giảm Cloud SQL instance tier | 250 USD | Cao với DB production | Trung bình | Review sâu và load test |
| Bỏ IAM role rộng không dùng thường xuyên | Không có savings trực tiếp | Có thể ảnh hưởng incident access | Trung bình | Security review |

Con số là dữ liệu học tập, không phải giá hoặc recommendation thực của GCP.

## 13. Đánh giá VM rightsizing

VM machine type recommender thường là ví dụ dễ hiểu về tối ưu nhưng cũng dễ dẫn đến kết luận sai nếu chỉ đọc CPU trung bình.

### Checklist kỹ thuật

1. Xác định VM, zone, machine type, attached disks, labels và owner.
2. Xem utilization CPU/memory theo nhiều ngày và cửa sổ peak.
3. Kiểm tra workload định kỳ: batch cuối tháng, backup, báo cáo hoặc incident drill.
4. Xem loại VM: stateless, stateful, singleton, MIG hay standby.
5. Kiểm tra quyền, capacity/quota, reservation và CUD.
6. Ước tính downtime hoặc restart cần thiết khi thay đổi machine type.
7. Thử trên staging hoặc canary VM có hành vi đại diện.
8. Đo latency, throughput, error rate, CPU/memory và rollback.

Không áp dụng rightsizing chỉ vì average CPU thấp. Một ứng dụng Java có thể cần memory để tránh garbage collection quá mức hoặc cần burst CPU trong vài phút.

### Trường hợp có thể ưu tiên

- VM dev không phục vụ liên tục và có lịch bật/tắt rõ.
- VM stateless dùng nhiều replica, có khả năng canary.
- Workload có metric ổn định, headroom lớn và ít phụ thuộc phần cứng.
- Điều chỉnh không ảnh hưởng reserved capacity hoặc cam kết hợp đồng.

Nếu VM được quản lý bằng Terraform, phải sửa cấu hình IaC để tránh lần apply tiếp theo khôi phục cấu hình cũ.

## 14. Đánh giá idle VM, disk, IP và reservation

Một tài nguyên "không được sử dụng" theo điều kiện của recommender vẫn có thể có giá trị dự phòng hoặc dữ liệu cần giữ.

### Idle VM

- Kiểm tra instance có trong standby/DR runbook không.
- Xem access logs, job schedules, network traffic và trách nhiệm owner.
- Chứng minh không còn dependency, DNS, static IP hoặc cron bên ngoài.
- Cân nhắc stop trước khi delete nếu quy trình và chi phí cho phép.
- Lưu cấu hình, kiểm tra disk, snapshot và kế hoạch phục hồi trước khi xóa.

### Persistent Disk

Một disk rời có thể chứa dữ liệu để restore. Trước khi xóa:

1. Xác nhận không được gắn VM/GKE workload hoặc dịch vụ khác.
2. Kiểm tra labels, owner và lý do giữ disk.
3. Xác minh dữ liệu có cần retention hay bằng chứng pháp lý không.
4. Nếu backup được chấp thuận, tạo snapshot và **thử phục hồi** trong phạm vi thích hợp.
5. Tính chi phí snapshot và retention; không mặc định snapshot luôn rẻ hơn disk.
6. Chỉ xóa sau phê duyệt với resource ID chính xác.

### Static IP và reservation

- IP không gắn tài nguyên vẫn có thể được đặt trước cho cutover, allowlist hoặc DR.
- Reservation chưa dùng có thể bảo đảm capacity cho batch hoặc sự kiện cao điểm.
- Phải xem runbook, lịch triển khai và các hợp đồng phụ thuộc trước khi hủy.

Idle recommendations có thể dựa trên cửa sổ quan sát hữu hạn. Một workload chỉ chạy mỗi quý có thể không xuất hiện trong cửa sổ đó.

## 15. Cloud SQL: tối ưu phải ưu tiên dữ liệu và SLO

Cloud SQL có các nhóm gợi ý liên quan idle, overprovisioned, underprovisioned, reliability hoặc cấu hình bảo mật. Quyết định cho database cần thận trọng hơn so với stateless VM.

### Overprovisioned instance

Khi được đề nghị giảm tier, kiểm tra:

- CPU, memory và working set theo cả kỳ cao điểm.
- Số lượng kết nối, pool size của ứng dụng và database connection limits.
- Query latency, lock wait và long-running transactions.
- Disk I/O, storage auto-increase và replication lag.
- Cấu hình HA/standby, backup/PITR và maintenance.
- Khả năng resize gây gián đoạn/restart.

Nên chạy load test có tỷ lệ đọc/ghi và dataset đại diện, không chỉ dựa trên CPU trung bình.

### Idle instance

Một database không có traffic có thể là môi trường phục hồi, staging sắp dùng hoặc nguồn dữ liệu audit. Không xóa instance khi chưa xác minh backup và retention. Nếu kết thúc vòng đời, cần có quy trình archive/restore và xác nhận downstream đã chuyển sang nơi khác.

### Underprovisioned và reliability

Một recommendation khuyên **tăng** tài nguyên hoặc bật HA có thể làm tăng hóa đơn nhưng cải thiện reliability. Đối với hệ thống có SLO chặt, tăng chi phí này có thể mang lại giá trị lớn hơn một thay đổi tiết kiệm nhỏ khác.

## 16. GKE và Cloud Run: hiểu autoscaling trước khi tối ưu

### GKE

GKE workload hoặc cluster diagnosis có thể phản ánh phân bổ requests/limits và mức sử dụng chưa hợp lý.

Khi giảm CPU/memory requests:

- Kiểm tra sử dụng theo percentile và peak, không chỉ average.
- Xem throttling, OOMKilled, restart và Pod readiness.
- Đối chiếu HPA targets, replica count, PodDisruptionBudget và topology.
- Kiểm tra cluster autoscaler có đủ node capacity khi cần.
- Đánh giá cost giảm ở đâu: node count, reservation, waste hay chỉ thay đổi biểu đồ utilization.

Một thay đổi làm CPU requests thấp hơn không nhất thiết giảm hóa đơn nếu số node không thay đổi. Ngược lại, requests quá thấp có thể làm metric HPA và scheduling phản ứng bất thường. Phải so sánh ở cấp **cluster + workload**, không chỉ một Pod.

### Cloud Run

Các gợi ý về CPU allocation hoặc cấu hình runtime phải được xem trong ngữ cảnh:

- Workload chủ yếu phục vụ request hay có background activity?
- Concurrency và min/max instances được cấu hình thế nào?
- Instance startup time và p95/p99 latency dưới tải?
- Billing model nào đang được dùng, chi phí theo usage thật ra sao?
- Có job hoặc service khác sử dụng chung dependency?

Không giả định CPU luôn-allocated luôn tốn hơn hoặc luôn rẻ hơn. Chi phí phụ thuộc pattern request, idle time và cấu hình; cần lập thử nghiệm nhỏ để so sánh.

## 17. BigQuery và Cloud Storage: tối ưu cả truy vấn lẫn dữ liệu

### BigQuery partitioning và clustering

Khi có recommendation partition/cluster table:

1. Xem query patterns thực: WHERE, JOIN, GROUP BY và cột được lọc.
2. Xem table size, bytes processed, slot usage và query latency.
3. Kiểm tra data freshness, write patterns và late-arriving events.
4. Đánh giá thay đổi schema/table có ảnh hưởng BI contract không.
5. Thử trên bản sao hoặc bảng staging có dataset đại diện.
6. So sánh query cost và latency trước/sau.

Partition pruning giúp khi query thực sự lọc đúng partition key. Tạo partition nhưng mọi report vẫn `SELECT *` không lọc cột/ngày thì lợi ích có thể thấp.

### Cloud Storage soft delete và retention

Một gợi ý thay đổi cấu hình soft delete có thể ảnh hưởng cân bằng giữa chi phí và khả năng phục hồi object. Trước khi áp dụng cần kiểm tra:

- Yêu cầu khôi phục object đã xóa nhầm.
- Retention policy, Object Versioning và quy định tuân thủ.
- Lượng dữ liệu bị xóa/sửa mỗi tháng và chi phí lưu giữ.
- Workload backup hoặc pipeline tạo object tạm.
- RPO/RTO và quy trình restore drill.

Không tắt soft delete hoặc retention chỉ để giảm hóa đơn khi chính sách dữ liệu yêu cầu khả năng phục hồi. Ngược lại, bật tính năng bảo vệ quá rộng không phân loại bucket có thể tăng chi phí.

### Chọn phương án lưu trữ và truy vấn

Recommender là một đầu vào. Bài toán tổng thể còn có storage classes, lifecycle, BigQuery query design, materialized views và reservation strategy. Cần phối hợp tối ưu từ dữ liệu nguồn đến công cụ tiêu thụ, không chỉ một resource đơn lẻ.

## 18. IAM recommendation: tiết kiệm rủi ro, không chỉ tiền

IAM recommender có thể gợi ý bỏ role hoặc thay role quá rộng bằng quyền hẹp hơn. Đây thường là cơ hội cải thiện security posture mà không có savings tài chính trực tiếp.

### Quy trình review

1. Xác định principal, role, scope, tài nguyên và owner.
2. Xem quyền đã thực sự được sử dụng và loại insight hỗ trợ gợi ý.
3. Kiểm tra tác vụ hiếm: incident response, quarterly job, DR, deployment/migration.
4. Đọc các điều kiện IAM, inheritance và service account impersonation.
5. Nếu cần, tạo custom role hoặc role cụ thể đáp ứng đủ use case.
6. Thử trong sandbox/staging và chạy integration tests.
7. Triển khai theo change control, theo dõi `PERMISSION_DENIED`.
8. Có quy trình hoàn tác nhanh nếu workflow quan trọng bị ảnh hưởng.

Một role không được dùng trong cửa sổ theo dõi vẫn có thể cần thiết cho một tác vụ ít chạy. Không biến gợi ý bớt quyền thành thao tác xóa IAM hàng loạt mà chưa xác minh.

### Nguyên tắc least privilege

Mục tiêu không phải cấp quyền tối thiểu về số lượng role bất kể hậu quả, mà là cấp **đủ quyền cần thiết, trong phạm vi nhỏ nhất và thời gian phù hợp**.

Các API không phải lúc nào cũng cung cấp đầy đủ tín hiệu sử dụng quyền. Kết hợp recommender với audit logs, runbook và danh sách dependency.

## 19. Committed use discounts và xung đột lợi ích

Commitment recommendations có thể giúp giảm giá sử dụng tương lai nhưng thường gắn với thời hạn và điều kiện hợp đồng. Đối với CUD, cần mô hình hóa:

- Nhu cầu sử dụng ổn định trong suốt kỳ cam kết.
- Phần workload dự kiến chuyển sang Cloud Run, GKE hay region khác.
- Thay đổi machine type và rightsizing dự kiến.
- Loại resource và usage đủ điều kiện áp dụng.
- Các commitment đang có và cách phân bổ sử dụng.
- Những kịch bản tăng/giảm tải trong thời hạn cam kết.

Không mua cam kết chỉ vì lịch sử vài tuần trông ổn định. Một chiến dịch tối ưu khác có thể giảm nhu cầu tiêu thụ và khiến CUD không còn được tận dụng hết.

### Chọn thứ tự

Thông thường:

1. Xóa lãng phí đã xác minh và rightsizing an toàn.
2. Đánh giá nhu cầu compute còn lại sau tối ưu.
3. Dự báo usage có độ tin cậy đủ cao.
4. Mới đánh giá mức commitment phù hợp với rủi ro hợp đồng.

Đây là nguyên tắc ra quyết định, không thay thế điều khoản hoặc công cụ billing chính thức.

## 20. Quy trình triển khai đề xuất an toàn

Một vòng lặp chuẩn:

~~~mermaid
flowchart TD
    A[Collect recommendations] --> B[Assign owner and classify]
    B --> C[Check freshness and context]
    C --> D[Estimate benefit and risk]
    D --> E{Guardrails satisfied?}
    E -->|No| F[Defer or dismiss with evidence]
    E -->|Yes| G[Design change and rollback]
    G --> H[Change approval]
    H --> I[Canary or controlled rollout]
    I --> J[Validate service and cost]
    J --> K{Outcome verified?}
    K -->|Yes| L[Record SUCCEEDED and realized effect]
    K -->|No| M[Rollback and investigate]
    M --> N[Record FAILED or next action]
~~~

### Trước áp dụng

- Chụp trạng thái resource và configuration hiện tại.
- Xác minh recommendation còn mới và các `test` operations vẫn phù hợp.
- Có owner và phê duyệt theo rủi ro.
- Có backup/snapshot hoặc phương án restore khi liên quan dữ liệu.
- Xác định SLO, RTO, rollback trigger và monitoring.
- Nếu IaC quản lý resource, sửa Terraform/manifest và xem diff/plan trước.
- Tránh áp dụng nhiều thay đổi cùng lúc trên một dependency chung.

### Khi áp dụng

- Ưu tiên canary hoặc một nhóm resource nhỏ.
- Ghi change ID, commit SHA, người phê duyệt và thời điểm.
- Quan sát CPU, memory, throughput, request latency, error rate và dependency.
- Dừng hoặc rollback theo ngưỡng định trước.

### Sau áp dụng

- Xác minh resource thực sự ở trạng thái dự kiến.
- So sánh SLI/SLO trước và sau trong điều kiện workload tương đương.
- Đo chi phí trên billing data sau khi đủ dữ liệu đối soát.
- Ghi kết quả và cập nhật recommendation state.
- Tạo follow-up khi lợi ích thực thấp hoặc có regression.

Gắn trạng thái recommendation với ticket/change request để tránh nhiều người cùng thực hiện một đề xuất.

## 21. Quản lý trạng thái bằng gcloud và audit trail

Sau khi đã review và có quyết định, có thể sử dụng nhóm lệnh:

~~~bash
gcloud recommender recommendations mark-claimed --help
gcloud recommender recommendations mark-dismissed --help
gcloud recommender recommendations mark-succeeded --help
gcloud recommender recommendations mark-failed --help
~~~

Những lệnh trên chỉ hiển thị hướng dẫn; không thay đổi trạng thái.

Khi thực sự chuyển trạng thái, lệnh cần recommendation ID, `--project`, `--location`, `--recommender`, `--etag` và có thể thêm `--state-metadata`. Ví dụ dưới đây là **mẫu cú pháp**, chỉ dùng sau khi đã được phê duyệt:

~~~bash
gcloud recommender recommendations mark-claimed "RECOMMENDATION_ID" \
  --project="PROJECT_ID" \
  --location="ZONE_OR_REGION" \
  --recommender="RECOMMENDER_ID" \
  --etag="ETAG_FROM_LAST_READ" \
  --state-metadata="ticket=CHANGE_1234"
~~~

`ETAG_FROM_LAST_READ` cần thay bằng giá trị thực đúng định dạng mà CLI nhận; không copy nguyên placeholder vào môi trường thật. Sau khi claim, đọc lại recommendation và lấy etag mới trước bước cập nhật state tiếp theo.

**Mark-claimed không áp dụng cấu hình cho VM/disk/IAM.** Thay đổi resource thực tế được thực hiện bằng công cụ của dịch vụ hoặc IaC qua quy trình riêng.

### Dismiss không phải xóa bằng chứng

Nếu quyết định không áp dụng vì đó là standby DR, có thể dismiss theo quy trình và ghi lý do. Recommendation có thể được tạo hoặc cập nhật trở lại khi điều kiện thay đổi. Cần lưu record trong hệ thống ticket để giải thích quyết định về sau.

## 22. Đo realized savings và phát hiện regression

Chi phí sau áp dụng chỉ có ý nghĩa khi so với baseline hợp lý.

### Quy trình measurement

1. Lưu baseline: chi phí, usage, cấu hình, SLO và kỳ quan sát.
2. Ghi timestamp thay đổi và các sự kiện khác cùng thời điểm.
3. Chờ đủ thời gian cho billing data và lưu lượng ổn định.
4. So sánh theo đơn vị sử dụng hoặc transaction, không chỉ tổng tiền.
5. Điều chỉnh các yếu tố làm sai lệch so sánh: tăng traffic, thay region, thay giá, CUD và credits.
6. Theo dõi regression trong ít nhất một chu kỳ sử dụng đại diện.
7. Tổng hợp savings realized được chứng minh và chi phí triển khai.

Ví dụ một service tiết kiệm 20% hóa đơn VM nhưng throughput giảm 25% và p99 tăng gấp đôi. Đây không phải một optimization thành công nếu SLO bị phá vỡ.

### KPI cho chương trình Recommender

| KPI | Ý nghĩa |
|---|---|
| Recommendations reviewed | Số đề xuất được xem xét theo kỳ |
| Acceptance rate | Tỷ lệ đề xuất được duyệt áp dụng |
| Time to review | Thời gian từ xuất hiện đến quyết định |
| Realized net savings | Tiền tiết kiệm ròng đã được kiểm chứng |
| SLO regressions | Số thay đổi tối ưu làm vi phạm SLO |
| Reverted changes | Số thay đổi bị rollback |
| Stale recommendations | Gợi ý quá cũ chưa có quyết định |
| Coverage by owner | Tỷ lệ đề xuất có người chịu trách nhiệm |

Đừng tối ưu KPI acceptance rate bằng cách chấp nhận quá nhiều gợi ý không phù hợp. Giá trị thực đến từ savings, giảm rủi ro hoặc tăng hiệu quả mà vẫn giữ chất lượng dịch vụ.

## 23. Tự động hóa ở quy mô nhiều project

Khi tổ chức có hàng chục hoặc hàng trăm project, đọc thủ công từng loại recommender rất tốn thời gian. Có thể tạo một workflow định kỳ:

1. Thu thập recommendations với API theo các recommender ID và location được hỗ trợ.
2. Chuẩn hóa resource, project, owner, labels, impact, state và last refresh time.
3. Lưu snapshot có thời hạn vào kho dữ liệu được bảo vệ.
4. Phân loại thành nhóm cost/performance/security/reliability.
5. Khử trùng lặp các cơ hội trên cùng resource.
6. Tạo ticket cho owner theo mức ưu tiên.
7. Kéo kết quả thay đổi, trạng thái approval và realized savings về dashboard.

### BigQuery export

Google Cloud hỗ trợ xuất một số insights và recommendations sang BigQuery để phân tích ở quy mô lớn. **Không phải mọi recommender đều nằm trong cùng phạm vi export**, vì vậy cần kiểm tra danh sách hỗ trợ trước khi thiết kế báo cáo tổng hợp.

Khi dùng BigQuery, có thể xây dashboard về số lượng đề xuất theo project, loại, tuổi đề xuất, mức độ ưu tiên và owner. Tránh công khai bảng export nếu nó chứa tên resource, thông tin IAM hoặc thông tin chi phí nhạy cảm.

### Automation cần phân cấp rủi ro

| Loại gợi ý | Chính sách automation tham khảo |
|---|---|
| Chỉ đọc và tạo báo cáo | Tự động hóa thường xuyên |
| Label hoặc metadata ít rủi ro | Có thể auto-apply với guardrails nếu được duyệt |
| Rightsize VM/Cloud SQL production | Review người, change window và rollback |
| Xóa disk, bucket, database hoặc project | Phê duyệt độc lập, backup/retention checks |
| Thay IAM policy | Security owner review và thử nghiệm |
| CUD/cam kết tài chính | FinOps/billing approval có đánh giá dự báo |

Không cho job có quyền Owner toàn organization tự động thực hiện mọi operation group được API trả về. Phân quyền theo project và loại thay đổi, với rate limit, audit logs và kill switch.

## 24. Tình huống thực hành: tối ưu hệ thống orders trên GCP

Giả sử một nền tảng có:

- `orders-api` chạy trên Cloud Run.
- Worker VM xử lý báo cáo định kỳ.
- Cloud SQL lưu đơn hàng.
- GKE chạy các consumer xử lý sự kiện.
- BigQuery lưu dữ liệu phân tích.
- Cloud Storage giữ file báo cáo và backup.

Một vòng rà soát đưa ra bốn đề xuất minh họa:

| Mã | Đề xuất | Savings ước tính/tháng | Tín hiệu |
|---|---|---:|---|
| REC-01 | Rightsize VM worker | 140 USD | CPU trung bình thấp |
| REC-02 | Xem xét xóa disk không gắn | 35 USD | Disk rời trong thời gian dài |
| REC-03 | Giảm Cloud SQL tier | 250 USD | Utilization tương đối thấp |
| REC-04 | Thay IAM role rộng | Không quy đổi trực tiếp | Quyền ít được dùng |

### Bước 1 — Thu thập và xác minh

Dùng gcloud Recommender API ở đúng project/location, lưu ID, recommender, resource, timestamp, etag và impact. Đối chiếu Cloud Monitoring, Billing, Asset Inventory và Terraform state theo quyền được giao.

### Bước 2 — Liên hệ owner

- Worker VM có job lớn chạy vào ngày cuối tháng không?
- Disk rời có phải bản khôi phục đang giữ không?
- Cloud SQL có peak transaction và yêu cầu HA nào?
- IAM role có cần cho quy trình incident hoặc migration không?

### Bước 3 — Lập phương án

- REC-01: defer cho đến khi có telemetry của kỳ batch cao điểm; sau đó thử cấu hình nhỏ hơn trong staging.
- REC-02: xác minh data owner, tạo backup/snapshot được kiểm tra, chỉ xóa khi thực sự không còn ràng buộc.
- REC-03: đo connection, query latency và CPU trong load test; chuẩn bị rollback và maintenance window.
- REC-04: thay role bằng role phù hợp sau khi kiểm tra job hiếm và có approval bảo mật.

### Bước 4 — Đo và kết luận

Ví dụ REC-01 được triển khai sau khi thử nghiệm đạt SLO: lưu baseline chi phí và p95 job duration trước/sau; chỉ đánh dấu thành công khi thay đổi thật đã được áp dụng và theo dõi đủ một chu kỳ batch. REC-03 vẫn ở trạng thái review nếu thiếu dữ liệu peak, dù savings estimate cao hơn.

### Bước 5 — Cập nhật backlog

Mỗi recommendation có:

~~~text
recommendation_id: REC-01
resource_owner: data-platform-team
decision: approved-after-validation
risk: medium
change_id: CHG-2026-0119
baseline_window: previous representative batch cycle
expected_savings_monthly: 140 USD (illustrative)
actual_savings_monthly: pending verification
rollback: restore previous machine type through IaC
status: awaiting post-change measurement
~~~

Đây là biểu mẫu vận hành nội bộ minh họa, không phải JSON schema của Recommender API.

## 25. Những lỗi đánh giá phổ biến

| Anti-pattern | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| Xem savings estimate là tiền chắc chắn tiết kiệm | Không phản ánh mọi discount, credits và biến động usage | Đo realized net savings |
| Áp dụng mọi gợi ý `ACTIVE` tự động | Có thể làm gián đoạn service hoặc mất dữ liệu | Phân loại rủi ro và approval |
| Chỉ xem CPU trung bình | Bỏ sót peak hoặc memory pressure | Dùng percentiles, batch window và load test |
| Xóa disk/IP "idle" không hỏi owner | Có thể phá recovery hoặc dependency | Kiểm tra inventory, backup và runbook |
| Rightsize VM nhưng không sửa Terraform | IaC apply sau có thể khôi phục cấu hình cũ | Sửa source-of-truth và review plan |
| Xóa IAM role dựa trên cửa sổ ngắn | Job định kỳ/DR mất quyền | Kiểm tra use cases hiếm |
| Cộng savings từ các phương án trùng nhau | Thổi phồng opportunity | Deduplicate theo resource và mô hình tài chính |
| Dùng CLI `mark-succeeded` như bằng chứng thành công | Không xác minh resource/cost | Đối soát post-change |
| Không kiểm tra `etag` và refresh time | Hành động trên recommendation cũ | Re-fetch và review |
| Không theo dõi SLO sau tối ưu | Tiết kiệm nhưng giảm chất lượng | Guardrails và rollback |
| Bỏ qua IAM/organization policy | Thay đổi có thể vi phạm bảo mật | Security review và compliance gates |
| Dùng một danh tính toàn quyền cho automation | Blast radius quá rộng | Least privilege và scope limits |

## 26. Checklist đánh giá và triển khai

### Khi đọc đề xuất

- [ ] Đúng project, resource, recommender ID và location.
- [ ] Đã đọc description, subtype, impact và operation groups.
- [ ] `lastRefreshTime` và `etag` còn phù hợp.
- [ ] Đã đối chiếu resource owner, labels và kiến trúc.
- [ ] Không nhầm insight với quyết định triển khai.
- [ ] Có data source hỗ trợ kết luận (Monitoring/Billing/Logs).

### Khi đánh giá tài chính

- [ ] Biết price basis (list/custom), duration và currency.
- [ ] Đã xem CUD/credit/discount và overlap với gợi ý khác.
- [ ] Đã tính công triển khai, backup, monitoring và egress.
- [ ] Xác định baseline đo realized savings sau thay đổi.
- [ ] Không cộng trùng expected với realized savings.

### Khi đánh giá kỹ thuật

- [ ] Kiểm tra p95/p99, peak CPU/memory và dependency.
- [ ] Kiểm tra SLO, HA, DR, RPO/RTO và quota.
- [ ] Có backup/restore drill nếu động đến dữ liệu.
- [ ] Có kế hoạch test/canary, rollback và change window.
- [ ] IAM/security owner xác nhận nếu thay đổi quyền.
- [ ] Cấu hình IaC được cập nhật trước hoặc đồng thời triển khai.

### Sau thay đổi

- [ ] Resource ở trạng thái dự kiến, API và workload hoạt động.
- [ ] SLI/SLO không xấu hơn ngưỡng đã đặt.
- [ ] Billing data đủ thời gian để đối chiếu.
- [ ] Recommendation state và ticket được cập nhật chính xác.
- [ ] Báo cáo realized savings và chi phí phát sinh.
- [ ] Các bài học được đưa vào backlog FinOps/SRE.

## 27. Tài liệu tham khảo và học tiếp

Các nguồn tài liệu chính thức để kiểm tra recommender ID, lệnh và hành vi dịch vụ tại thời điểm triển khai:

- [Google Cloud Recommender overview](https://docs.cloud.google.com/recommender/docs)
- [Recommender key concepts](https://docs.cloud.google.com/recommender/docs/key-concepts)
- [Use the Recommender API](https://docs.cloud.google.com/recommender/docs/use-api)
- [Supported recommenders](https://docs.cloud.google.com/recommender/docs/recommenders)
- [Understanding cost-saving estimates](https://docs.cloud.google.com/recommender/docs/understand-cost-recs)
- [FinOps hub](https://docs.cloud.google.com/billing/docs/how-to/finops-hub)

Các trang có thể cập nhật theo dịch vụ và phiên bản công cụ. Trước khi tự động hóa, hãy xác minh tính khả dụng của recommender tại project/location, IAM permissions và điều kiện quản trị dữ liệu của tổ chức.

**Kết luận:** Recommender giúp nhóm nhìn thấy các cơ hội tối ưu khó phát hiện khi quản lý hạ tầng thủ công. Nhưng giá trị thực chỉ đến khi mỗi gợi ý được nối với dữ liệu đo, owner, SLO, rủi ro, chi phí triển khai và quy trình kiểm chứng sau thay đổi. Khi kết hợp Recommender với Active Assist, FinOps hub, Cloud Monitoring, Billing, IAM và Infrastructure as Code, tổ chức có thể tối ưu hạ tầng GCP có kiểm soát thay vì chỉ chạy theo con số savings ước tính.


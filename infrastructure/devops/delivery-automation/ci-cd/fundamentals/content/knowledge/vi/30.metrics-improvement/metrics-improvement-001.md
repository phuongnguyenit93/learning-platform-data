# Đo thời gian từ thay đổi đến khi sử dụng được trên môi trường đích

Một thay đổi code chỉ tạo ra giá trị khi người dùng hoặc hệ thống đích có thể sử dụng nó. Commit đã được merge, pipeline đã xanh hay lệnh deploy trả về thành công đều chưa đủ để chứng minh điều đó. Artifact có thể còn đang rollout, Pod chưa Ready, traffic vẫn đi vào phiên bản cũ, feature flag chưa bật hoặc luồng nghiệp vụ sau deploy chưa hoạt động.

Vì vậy, khi đo tốc độ phân phối phần mềm, cần xác định thời gian từ lúc một thay đổi được đưa vào luồng phát triển đến lúc thay đổi đó thực sự khả dụng trên môi trường mục tiêu. Chỉ số này thường được gọi là **lead time for changes** hoặc lead time từ change đến usable. Để số đo có ý nghĩa, nhóm phải định nghĩa chính xác mốc bắt đầu, mốc kết thúc, cách liên kết commit với deployment và cách xử lý các lần phát hành thất bại.

Trong CI/CD, mục tiêu không phải làm một con số nhỏ bằng mọi giá. Mục tiêu là tìm ra thời gian chờ và bước xử lý nào đang làm thay đổi đến người dùng chậm, rồi cải thiện luồng mà vẫn giữ chất lượng, bảo mật và khả năng phục hồi.

## 1. Lead time đo điều gì?

Lead time for changes đo khoảng thời gian từ khi thay đổi được commit vào version control đến khi thay đổi đó được triển khai thành công và có thể sử dụng trên môi trường đích. Đây là một chỉ số về tốc độ dòng chảy từ code đến production.

Với một service có quy trình phát hành rõ ràng, có thể định nghĩa:

~~~text
LeadTime = T_usable - T_change
~~~

Trong đó:

- **T_change:** thời điểm thay đổi được ghi nhận vào nhánh tích hợp hoặc revision được chọn làm đầu vào phát hành.
- **T_usable:** thời điểm thay đổi đã được triển khai, kiểm tra và thực sự khả dụng theo tiêu chí của môi trường đích.

Ví dụ: một commit được merge vào main lúc 09:00. Build, test và review đã hoàn tất lúc 09:18; artifact được publish lúc 09:22; production rollout bắt đầu lúc 09:30; toàn bộ instance Ready, traffic đã chuyển và smoke test đạt lúc 09:42. Lead time là 42 phút, không phải 18 phút của pipeline build/test hay 12 phút của lệnh deploy.

### 1.1. Vì sao cần mốc “usable”?

Một thay đổi có thể đã được đưa lên production nhưng chưa thể sử dụng:

- Deployment controller đã nhận manifest nhưng rollout vẫn đang tiến hành.
- Container đang chạy nhưng readiness probe chưa đạt.
- Instance mới Ready nhưng load balancer chưa route traffic đến.
- API mới đã deploy nhưng feature flag vẫn tắt.
- Schema đã cập nhật nhưng background worker chưa xử lý dữ liệu cần thiết.
- Endpoint trả 200 nhưng giao dịch nghiệp vụ quan trọng vẫn thất bại.
- Tính năng chỉ được bật cho cohort nhỏ, trong khi metric được báo cáo như thể đã mở cho toàn bộ người dùng.

Mốc kết thúc phải phản ánh mục tiêu đo. Nếu nhóm muốn đo “code đã chạy trong production”, có thể dùng thời điểm runtime xác nhận đúng artifact. Nếu muốn đo “khách hàng có thể sử dụng tính năng”, cần thêm điều kiện traffic, feature flag, quyền truy cập và smoke/synthetic transaction. Hai cách đo đều hữu ích, nhưng phải đặt tên và báo cáo riêng.

## 2. Chọn mốc bắt đầu nhất quán

Mốc bắt đầu quyết định nhóm đang đo đoạn nào của quy trình.

Một lựa chọn phổ biến cho DORA Lead Time for Changes là thời điểm commit được đưa vào version control. Với luồng CI/CD có nhánh tích hợp, nhóm có thể dùng thời điểm commit được merge vào nhánh chính hoặc thời điểm revision trở thành đầu vào chính thức của pipeline phát hành.

Các mốc có thể dùng:

| Mốc bắt đầu | Đang đo điều gì? | Hạn chế |
|---|---|---|
| Thời điểm developer bắt đầu code | Thời gian từ lúc bắt đầu làm việc đến khi dùng được | Khó đo chính xác, dễ bị lệch bởi việc chuyển task |
| Pull request được mở | PR cycle time từ review đến production | Bỏ qua thời gian viết code trước PR |
| Commit đầu tiên của change | Gần với thời điểm code được ghi nhận | Có thể gồm commit nháp hoặc commit chưa được chọn phát hành |
| Commit được merge vào nhánh tích hợp | Thời gian từ thay đổi đã được chấp nhận vào luồng chính đến khi usable | Phù hợp với flow trunk-based; cần map merge commit/squash |
| Commit/revision được chọn cho release | Thời gian từ revision được xác định đến khi usable | Phù hợp release train; có thể bỏ qua thời gian chờ trước khi chọn release |

Không nên trộn nhiều định nghĩa trong cùng một dashboard. Nếu nhóm dùng merge time cho một service và PR-open time cho service khác, phép so sánh sẽ không công bằng.

### 2.1. Đề xuất định nghĩa thực tế

Với module CI/CD, một định nghĩa dễ triển khai là:

- Bắt đầu tại thời điểm commit chứa change được tích hợp vào protected/default branch hoặc revision được chấp nhận làm release input.
- Kết thúc tại thời điểm deployment của revision đó đạt điều kiện usable trên environment mục tiêu.
- Dùng UTC timestamp do hệ thống quản lý source, pipeline và deployment ghi nhận.
- Gắn mọi mốc với change ID, commit SHA, artifact digest, deployment ID và environment.
- Báo cáo riêng lead time đến staging và lead time đến production nếu cả hai đều có giá trị.

Nếu tổ chức release theo batch, cần quy tắc xác định commit nào thuộc deployment đó. Không được tự chọn commit timestamp thuận lợi sau khi đã biết kết quả.

## 3. Định nghĩa mốc kết thúc: deploy thành công hay usable?

Mốc kết thúc không nên chỉ là lúc lệnh deploy trả exit code 0. Lệnh có thể chỉ gửi yêu cầu cho control plane, còn rollout tiếp tục ở phía sau.

Một deployment có thể được coi là usable khi các điều kiện phù hợp với service đã đạt:

1. Đúng artifact digest/revision đang chạy trên environment mục tiêu.
2. Rollout đã đạt trạng thái hoàn tất hoặc đạt phạm vi cohort được định nghĩa.
3. Instance cần thiết đã Ready và được đưa vào endpoint/traffic routing.
4. Health check và smoke/synthetic checks bắt buộc đạt.
5. Feature flag, entitlement hoặc routing đã mở đúng phạm vi người dùng mục tiêu.
6. Luồng nghiệp vụ đại diện có thể thực hiện thành công.
7. Không có guardrail bắt buộc nào đang chặn release, ví dụ error rate hoặc latency vượt ngưỡng.

### 3.1. Các mức “usable” khác nhau

| Mức kết thúc | Điều kiện | Chỉ số phù hợp |
|---|---|---|
| Deployed | Control plane đã áp dụng revision | Deploy request/operation duration |
| Runtime active | Instance chạy đúng artifact | Commit-to-runtime lead time |
| Ready for traffic | Instance Ready và có trong routing | Commit-to-ready lead time |
| Verified | Smoke/synthetic và guardrails đạt | Commit-to-verified lead time |
| Available to cohort | Flag/permission/routing mở cho cohort đã duyệt | Change-to-cohort-usable lead time |
| General availability | Tính năng mở rộng theo kế hoạch đến toàn bộ audience mục tiêu | Change-to-GA lead time |

Nên chọn một mốc chính cho báo cáo lead time và có thể giữ các mốc trung gian để phân tích. Ví dụ với service backend, Verified có thể là mốc chính. Với tính năng cần bật feature flag, Available to cohort hoặc General availability có thể phản ánh giá trị tốt hơn.

## 4. Phân biệt lead time với các chỉ số thời gian khác

Các chỉ số thời gian trong delivery thường bị gọi chung là “build time” hoặc “deployment time”, nhưng chúng đo các đoạn khác nhau.

| Chỉ số | Bắt đầu | Kết thúc | Câu hỏi |
|---|---|---|---|
| Lead time for changes | Commit/change được tích hợp | Change usable trên production | Bao lâu từ code đến giá trị sử dụng? |
| PR cycle time | PR được mở | PR được merge | Review và tích hợp mất bao lâu? |
| CI duration | Pipeline/job bắt đầu | Pipeline/job kết thúc | Máy chạy kiểm tra mất bao lâu? |
| Queue time | Job được tạo | Runner bắt đầu thực thi | Bao lâu công việc phải chờ worker? |
| Build duration | Build task bắt đầu | Artifact build xong | Compile/package mất bao lâu? |
| Deployment duration | Bắt đầu deploy | Rollout/deploy operation kết thúc | Deploy mất bao lâu? |
| Time to usable | Deploy bắt đầu hoặc commit tùy định nghĩa | Điều kiện usable đạt | Mất bao lâu để phiên bản thực sự phục vụ? |
| Time to restore service | Incident bắt đầu | Dịch vụ phục hồi | Mất bao lâu để khôi phục sau lỗi? |

Lead time tổng hợp nhiều đoạn. CI duration ngắn không đảm bảo lead time ngắn nếu change phải chờ review, release window, approval, runner capacity hoặc environment.

## 5. Mô hình sự kiện để tính lead time

Để tính đáng tin cậy, cần thu thập sự kiện thay vì chỉ lấy trạng thái cuối của pipeline.

Một change có thể đi qua chuỗi:

~~~mermaid
flowchart LR
    A[Change integrated] --> B[CI queued]
    B --> C[CI started]
    C --> D[Checks passed]
    D --> E[Artifact published]
    E --> F[Deploy requested]
    F --> G[Rollout complete]
    G --> H[Runtime verified]
    H --> I[Traffic / feature enabled]
    I --> J[Usable]
~~~

Mỗi sự kiện nên có:

- **event_id:** định danh sự kiện duy nhất.
- **event_type:** loại sự kiện như change_integrated, build_started, artifact_published, deployment_usable.
- **occurred_at:** thời điểm sự kiện thực sự xảy ra.
- **recorded_at:** thời điểm hệ thống thu thập/ghi sự kiện.
- **change_id** hoặc danh sách commit SHA liên quan.
- **repository**, **service**, **environment**.
- **pipeline_run_id**, **build_id**, **release_id**, **deployment_id** khi có.
- **artifact_digest** để định danh artifact.
- **result** hoặc **status**.
- **actor** hoặc workload identity nếu cần audit.

### 5.1. Ví dụ event record

~~~json
{
  "event_id": "evt-9f21",
  "event_type": "deployment_usable",
  "occurred_at": "2026-11-18T09:42:00Z",
  "recorded_at": "2026-11-18T09:42:02Z",
  "change_id": "chg-1842",
  "commit_sha": "a1b2c3d4",
  "service": "orders",
  "environment": "production",
  "release_id": "rel-2026-11-18-07",
  "deployment_id": "dep-7731",
  "artifact_digest": "sha256:abc123...",
  "result": "verified"
}
~~~

Ví dụ chỉ minh họa schema. Trong hệ thống thực tế, dùng định danh ổn định của SCM, build system và deployment platform; không tự tạo các ID không có liên kết đến nguồn gốc.

### 5.2. Dùng event time và processing time đúng cách

occurred_at biểu diễn lúc sự kiện xảy ra; recorded_at biểu diễn lúc telemetry đến hệ thống thu thập. Nếu event được gửi chậm, dùng recorded_at để tính lead time có thể làm kết quả tăng giả tạo.

Nên tính theo event time, đồng thời theo dõi ingestion lag:

~~~text
IngestionLag = T_recorded - T_occurred
~~~

Nếu ingestion lag lớn hoặc timestamp không đáng tin, đánh dấu dữ liệu thiếu chất lượng thay vì âm thầm dùng thời điểm nhận sự kiện.

## 6. Liên kết change với artifact và deployment

Đây là phần khó nhất khi đo lead time trên hệ thống thật. Một deployment thường chứa nhiều commit; một commit có thể được deploy nhiều lần; artifact có thể được promote qua staging rồi production; hotfix có thể cherry-pick; monorepo có nhiều service và một release chỉ chứa thay đổi của một phần.

Cần có chuỗi liên kết:

**Change → Commit(s) → Build → Artifact digest → Release → Deployment → Environment → Usable event**

Một release record nên lưu:

- Repository và service.
- Commit SHA hoặc danh sách commit được bao gồm.
- Build/pipeline run ID.
- Artifact coordinates/version/digest.
- Release ID và deployment ID.
- Environment/region/cohort.
- Thời điểm deploy và thời điểm usable.
- Kết quả validation và approval.

### 6.1. Một deployment chứa nhiều commit

Nếu deployment production chứa 8 commit, mỗi commit có thể nhận cùng T_usable của deployment đó khi tính commit-to-production lead time theo change. Khi tính thống kê, cần giữ quy tắc này nhất quán và tránh đếm trùng deployment như nhiều deployment event.

Ví dụ:

| Commit | Integrated at | Deployment usable at | Lead time |
|---|---|---|---:|
| C101 | 08:10 | 09:00 | 50 phút |
| C102 | 08:25 | 09:00 | 35 phút |
| C103 | 08:40 | 09:00 | 20 phút |

Deployment chỉ có một lần usable lúc 09:00, nhưng ba change có ba lead time khác nhau.

### 6.2. Một commit được deploy nhiều lần

Nếu cùng commit được deploy lên staging rồi production, mỗi environment là một phép đo khác nhau:

- Commit-to-staging-usable.
- Commit-to-production-usable.

Không cộng hoặc lấy trung bình hai mốc để gọi là một lead time. Dashboard cần ghi rõ environment mục tiêu.

### 6.3. Squash, cherry-pick và merge commit

Nếu SCM tạo squash commit hoặc cherry-pick SHA mới, cần lưu quan hệ giữa change/PR gốc và commit thực tế trong release. Có thể dùng PR/MR ID hoặc change ID làm khóa nghiệp vụ, nhưng vẫn lưu commit SHA thực sự được build.

## 7. Phân rã lead time để tìm nơi chờ

Lead time tổng hợp không nói trực tiếp nên cải thiện ở đâu. Hãy chia thành các khoảng thời gian giữa các event:

~~~text
T_total =
  T_integration_to_CI +
  T_CI +
  T_artifact_to_deploy +
  T_deployment +
  T_verification
~~~

Tùy quy trình, có thể bổ sung thời gian review trước merge, chờ release train, chờ approval, chờ capacity hoặc thời gian feature flag chưa được bật.

Ví dụ phân rã một change mất 6 giờ:

| Giai đoạn | Thời gian | Tỷ trọng |
|---|---:|---:|
| Chờ merge/review | 2 giờ | 33,3% |
| Chờ runner | 20 phút | 5,6% |
| CI build/test | 25 phút | 6,9% |
| Chờ release approval/window | 2 giờ | 33,3% |
| Publish và deploy | 35 phút | 9,7% |
| Verification và mở traffic | 40 phút | 11,1% |
| Tổng | 6 giờ | 100% |

Trong ví dụ này, tối ưu compiler thêm 5 phút không tác động nhiều bằng việc rút ngắn thời gian chờ review hoặc approval. Phân rã giúp chọn đúng điểm nghẽn.

### 7.1. Phân biệt processing time và waiting time

- **Processing time:** thời gian công việc thực sự được thực hiện, như build, test, scan hoặc rollout.
- **Waiting time:** thời gian change chờ người review, runner, approval, release window hoặc dependency.
- **Rework time:** thời gian sửa lỗi, chạy lại pipeline hoặc xử lý failed deployment.

Một pipeline có thời gian xử lý 15 phút nhưng chờ runner 90 phút vẫn có lead time dài. Không nên chỉ tối ưu thời gian CPU nếu phần lớn độ trễ đến từ queue hoặc handoff.

## 8. Tính lead time bằng dữ liệu có cấu trúc

Giả sử bảng change_deployments có các trường:

- change_id
- service
- environment
- integrated_at
- usable_at
- deployment_id
- artifact_digest
- usable_status

Một truy vấn SQL khái niệm:

~~~sql
SELECT
    service,
    environment,
    change_id,
    deployment_id,
    EXTRACT(EPOCH FROM (usable_at - integrated_at)) AS lead_time_seconds
FROM change_deployments
WHERE usable_status = 'verified'
  AND integrated_at IS NOT NULL
  AND usable_at IS NOT NULL
  AND usable_at >= integrated_at;
~~~

Truy vấn này chỉ là ví dụ, cú pháp tính thời gian có thể khác theo database. Cần bảo đảm một dòng tương ứng với đúng change/environment/deployment mapping và không nhân bản do join nhiều commit hoặc nhiều event.

### 8.1. Kiểm tra dữ liệu bất thường

Trước khi đưa metric lên dashboard, kiểm tra:

- usable_at có trước integrated_at không?
- Có change chưa được deploy nên chưa có usable_at không?
- Một change có nhiều deployment hoặc rollback không?
- Một deployment có nhiều change?
- Timestamp có timezone không?
- Có event bị gửi trùng không?
- Artifact digest có khớp giữa build và deployment?
- Environment có được chuẩn hóa tên không?
- Có change bị hủy hoặc superseded không?

Không loại bỏ mọi giá trị bất thường mà không lưu nguyên nhân. Một lead time âm có thể chỉ ra lỗi clock hoặc mapping; một change chờ 30 ngày có thể là thay đổi thật bị giữ lại chứ không phải dữ liệu rác.

## 9. Dùng median và percentile thay vì chỉ dùng average

Lead time thường có phân phối lệch: nhiều change được phát hành nhanh, một số change phải chờ nhiều ngày. Average có thể bị kéo lên bởi một số trường hợp dài; median cho biết trải nghiệm điển hình nhưng không phản ánh tail.

Nên theo dõi:

- **p50/median:** một nửa change có lead time thấp hơn mức này.
- **p75:** 75% change hoàn tất trong thời gian này.
- **p90/p95:** thể hiện nhóm change chậm và độ dài tail.
- **Average:** hữu ích cho tổng chi phí thời gian nhưng nhạy với outlier.
- **Count/sample size:** số change trong kỳ để biết mức tin cậy của phân phối.

Ví dụ:

| Thống kê | Lead time |
|---|---:|
| p50 | 42 phút |
| p75 | 1 giờ 20 phút |
| p90 | 5 giờ |
| p95 | 1,4 ngày |
| Average | 4,2 giờ |
| Changes | 180 |

Median 42 phút cho thấy phần lớn change đi nhanh, nhưng p95 1,4 ngày cho thấy có nhóm bị mắc ở release window hoặc approval. Cần phân tích nhóm tail thay vì chỉ công bố median.

### 9.1. So sánh cùng điều kiện

Khi so sánh theo tuần hoặc giữa service, giữ các điều kiện tương đồng:

- Cùng định nghĩa start/end.
- Cùng environment.
- Cùng cách map commit vào deployment.
- Cùng loại change hoặc phân tầng theo loại.
- Cùng đơn vị thời gian và timezone.
- Đủ sample size.
- Ghi nhận thay đổi trong quy trình đo.

Không so p50 của staging với p95 của production hoặc so service deploy liên tục với service phát hành theo tháng mà không giải thích khác biệt.

## 10. Các change chưa usable và dữ liệu bị kiểm duyệt

Nếu chỉ tính các change đã deploy thành công, dashboard có thể bỏ qua những change đang chờ nhiều ngày. Đây là thiên lệch sống sót: các trường hợp nhanh đã hoàn tất được tính, còn trường hợp chậm chưa có end time biến mất khỏi báo cáo.

Cần theo dõi thêm:

- Số change đã tích hợp nhưng chưa usable.
- Tuổi của change chưa hoàn tất (change age).
- Số change đang chờ review, approval, release window hoặc fix.
- Số change failed/canceled/superseded.
- Số change đang rollout nhưng chưa qua verification.

Đối với change chưa có end time, không thể tính lead time hoàn chỉnh. Có thể báo cáo tuổi hiện tại như một chỉ số riêng và sử dụng phân tích survival/censored data nếu nhóm có nhu cầu thống kê chuyên sâu. Ít nhất, dashboard không nên âm thầm bỏ chúng.

### 10.1. Phân biệt failed attempt và change cuối cùng

Một change có thể trải qua deploy thất bại rồi deploy lại thành công. Lead time đến usable nên tính từ mốc change ban đầu đến lần đầu đạt tiêu chí usable cuối cùng, đồng thời giữ riêng failed attempt và recovery duration. Không reset start time mỗi lần retry để làm lead time ngắn giả tạo.

Nếu release bị rollback trước khi người dùng có thể sử dụng, không đánh dấu change là usable. Nếu đã usable rồi mới phát sinh incident và rollback, giữ lại sự kiện usable lịch sử nhưng liên kết change failure/recovery metrics; không xóa mốc thành công ban đầu.

## 11. Đồng bộ thời gian và chất lượng timestamp

Lead time là phép trừ hai timestamp từ nhiều hệ thống: SCM, CI server, artifact registry, deployment platform và telemetry. Nếu clock không đồng bộ, kết quả có thể âm hoặc sai đáng kể.

Các nguyên tắc:

- Lưu timestamp ở UTC và có timezone rõ ràng.
- Đồng bộ clock trên runner, controller và hệ thống tự quản lý bằng NTP hoặc cơ chế tương đương.
- Ưu tiên timestamp do server/control plane ghi nhận thay vì thời gian do client tùy ý gửi.
- Giữ cả event time và ingestion time.
- Trong một tiến trình, dùng monotonic clock để đo duration nội bộ; dùng wall-clock UTC để liên kết sự kiện giữa hệ thống.
- Theo dõi clock skew và ingestion lag.
- Không sửa timestamp lịch sử để làm đẹp báo cáo.

Nếu SCM và deployment platform có clock lệch vài phút, phép đo change-to-usable ngắn vài phút có thể không đáng tin. Cần cảnh báo chất lượng dữ liệu hoặc loại kỳ đo bị lỗi theo policy minh bạch.

## 12. DORA Lead Time for Changes và các chỉ số liên quan

Lead time for changes là một trong các chỉ số DORA về hiệu suất phân phối phần mềm. Nó nên được xem cùng các chỉ số khác, thay vì trở thành mục tiêu độc lập.

Các chỉ số thường được dùng trong mô hình DORA hiện đại gồm:

- **Deployment frequency:** tần suất deploy đến production.
- **Lead time for changes:** thời gian từ commit đến khi change chạy trong production.
- **Change failure rate:** tỷ lệ deployment gây suy giảm dịch vụ hoặc cần remediation.
- **Failed deployment recovery time:** thời gian phục hồi sau deployment thất bại.
- **Deployment rework rate:** tỷ lệ deployment được thực hiện để sửa lỗi hoặc phục hồi từ thay đổi trước đó.

Tên gọi và cách operationalize có thể khác theo phiên bản mô hình và công cụ. Điều quan trọng là công bố định nghĩa đang dùng. Lead time thấp nhưng change failure rate cao không phải kết quả tốt; deployment frequency cao nhưng rework tăng có thể cho thấy pipeline đang đẩy thay đổi thiếu chất lượng.

### 12.1. Không đồng nhất lead time với throughput

Lead time đo thời gian của từng change; throughput đo số change hoàn tất trong một khoảng thời gian. Một nhóm có thể có lead time ngắn nhưng throughput thấp nếu change rất nhỏ hoặc ít người làm. Một nhóm có throughput cao nhưng lead time dài nếu nhiều change cùng nằm trong batch hoặc chờ release window.

Nên theo dõi cả hai để hiểu dòng chảy.

## 13. Đo theo service và environment

Một tổ chức có nhiều service không nên chỉ báo cáo một con số tổng hợp. Mỗi service có đặc điểm phát hành khác nhau:

- API stateless có thể deploy nhiều lần mỗi ngày.
- Database service có migration và maintenance window.
- Mobile/backend feature có thể phụ thuộc app store hoặc rollout client.
- Batch processing có thể chỉ usable sau khi job kế tiếp chạy.
- Feature flag có thể mở theo tenant hoặc cohort.

Nên phân đoạn theo:

- Service/component.
- Environment: staging, production, region hoặc cluster.
- Change type: feature, bugfix, security patch, config, migration.
- Release strategy: rolling, canary, blue/green, feature flag.
- Repository/team nếu cần ownership.
- Mức độ rủi ro hoặc phạm vi thay đổi.

Không gộp tất cả service vào một ranking đơn giản. Dùng metric để tìm vấn đề trong flow của từng service, không tạo cuộc thi giữa các nhóm có kiến trúc và nghĩa vụ khác nhau.

## 14. Xây dashboard lead time hữu ích

Một dashboard tốt cần trả lời ba lớp câu hỏi.

### 14.1. Kết quả tổng thể

- p50/p75/p90/p95 lead time.
- Số change usable trong kỳ.
- Số change đang chờ và tuổi của chúng.
- Tỷ lệ change chưa có deployment mapping.
- Tỷ lệ event thiếu timestamp hoặc artifact digest.
- Deployment frequency và change failure rate để có bối cảnh.

### 14.2. Phân rã bottleneck

Hiển thị thời gian ở từng đoạn:

- Change integrated → CI queued.
- CI queued → CI started.
- CI started → checks passed.
- Checks passed → artifact published.
- Artifact published → deploy requested.
- Deploy requested → rollout complete.
- Rollout complete → verification passed.
- Verification passed → feature available to target cohort.

Có thể dùng stacked bar cho từng change hoặc percentile theo từng phase. Khi một phase chiếm tỷ trọng lớn, mở drill-down đến pipeline run, approval record hoặc deployment event.

### 14.3. Chất lượng và rủi ro

Đặt cạnh lead time:

- Failed pipeline và retry count.
- Failed deployment và rollback.
- Change failure rate.
- Incident/recovery time.
- Error rate, latency, saturation sau deploy.
- Test/quality gate skipped hoặc bypass.
- Tỷ lệ artifact không truy được provenance.
- Số change được mở rộng cohort sau thời gian quan sát.

Không dùng dashboard chỉ để xếp hạng nhóm. Dùng nó để tìm chỗ chờ, loại bỏ handoff thừa và phát hiện khi tốc độ tăng nhưng chất lượng suy giảm.

## 15. Cải thiện lead time theo bottleneck

Sau khi phân rã, chọn cải tiến đúng nguyên nhân. Một số hướng thường gặp:

| Bottleneck | Dấu hiệu | Cải tiến có thể thử |
|---|---|---|
| Review chậm | Change chờ PR review lâu | PR nhỏ hơn, reviewer ownership rõ, review rotation, tự động kiểm tra style |
| Runner queue | Job chờ lâu trước khi chạy | Điều chỉnh capacity, autoscaling, runner labels và concurrency |
| CI quá dài | Build/test chiếm phần lớn thời gian | Cache đúng, incremental build, parallel tests, test pyramid |
| Test flaky | Retry nhiều, kết quả không ổn định | Sửa nguyên nhân flaky, cô lập test, giữ retry có giới hạn và quan sát |
| Approval chậm | Chờ người phê duyệt hoặc release window | Risk-based approval, owner/on-call rõ, approval theo release candidate |
| Artifact publish chậm | Upload lớn hoặc registry chậm | Layering, registry gần runner, compression và artifact size control |
| Rollout chậm | Readiness hoặc capacity kéo dài | Tối ưu startup, capacity planning, rollout strategy và probe |
| Verification chậm | Smoke/synthetic test lâu hoặc thủ công | Test ngắn, đại diện, tự động hóa và chia lớp verification |
| Feature chưa được mở | Deploy xong nhưng flag/cohort chờ | Tích hợp release decision và flag operation vào flow có owner |
| Batch release | Change phải chờ cửa sổ phát hành | Release nhỏ hơn, deploy thường xuyên hơn nếu risk controls cho phép |

### 15.1. Tối ưu queue trước khi tối ưu compute

Nếu CI duration chỉ 10 phút nhưng runner queue là 60 phút, thêm cache hoặc CPU mạnh hơn không giải quyết nguyên nhân chính. Hãy đo queue time riêng và xem runner capacity, concurrency limit, quota, label mismatch và job scheduling.

### 15.2. Tối ưu test có chọn lọc nhưng giữ required coverage

Có thể chạy unit tests song song, dùng affected tests hoặc tách fast checks và full suite. Tuy nhiên, selective testing phải có cơ chế fallback khi không xác định được impact; không bỏ test bắt buộc chỉ để giảm lead time.

### 15.3. Giảm batch size và handoff

Change nhỏ, review được nhanh và có thể deploy độc lập thường giảm thời gian chờ. Nhưng chia nhỏ không có nghĩa bỏ kiểm thử compatibility hoặc phát hành liên tục khi hệ thống chưa sẵn sàng. Cần giữ contract, migration và rollout controls.

## 16. Ví dụ tính lead time cho một change

Một change CHG-1842 thêm trường deliveryWindow vào service orders:

| Event | Timestamp UTC |
|---|---|
| Commit được merge vào main | 09:00 |
| CI bắt đầu | 09:04 |
| Test và quality gate đạt | 09:19 |
| Artifact digest được publish | 09:23 |
| Deploy production bắt đầu | 09:31 |
| Rollout hoàn tất, Pod Ready | 09:37 |
| Smoke test và business check đạt | 09:41 |
| Feature flag bật cho pilot cohort | 09:45 |

Nếu định nghĩa usable là “pilot cohort có thể dùng tính năng”, thì:

~~~text
LeadTime = 09:45 - 09:00 = 45 phút
~~~

Các đoạn thời gian:

- Chờ CI: 4 phút.
- CI: 15 phút.
- Publish và handoff: 12 phút.
- Rollout: 6 phút.
- Verification: 4 phút.
- Chờ/mở feature flag: 4 phút.

Nếu chỉ lấy thời điểm rollout hoàn tất, lead time sẽ là 37 phút. Nếu chỉ lấy pipeline duration, có thể báo cáo 15 phút. Cả hai có thể là metric hợp lệ cho câu hỏi riêng, nhưng không đại diện cho 45 phút đến khi pilot cohort sử dụng được.

## 17. Đặt mục tiêu và cải tiến theo xu hướng

Không nên đặt một con số lead time giống nhau cho mọi service. Mục tiêu cần dựa trên baseline, risk profile, release model và kỳ vọng sản phẩm.

Một cách triển khai:

1. Định nghĩa start/end và event schema.
2. Thu thập dữ liệu trong vài chu kỳ release để có baseline.
3. Phân tích median, p90/p95 và change age.
4. Tìm phase chiếm nhiều thời gian chờ nhất.
5. Chọn một cải tiến có thể kiểm chứng.
6. Theo dõi lead time cùng change failure rate và recovery.
7. Đánh giá sau một khoảng thời gian đủ mẫu.
8. Điều chỉnh mục tiêu nếu mix change/service thay đổi.

Có thể đặt SLO nội bộ như “90% change thuộc service X usable trong vòng 4 giờ”, nhưng cần định nghĩa rõ cohort, environment, loại change và trường hợp loại trừ. SLO nên hướng đến cải thiện flow, không phải khuyến khích bỏ gate.

### 17.1. Tránh biến metric thành mục tiêu gây hành vi sai

Khi lead time trở thành KPI thưởng/phạt, nhóm có thể:

- Gộp nhiều thay đổi thành một commit hoặc release để giảm số mẫu.
- Chọn timestamp bắt đầu muộn hơn.
- Đánh dấu usable ngay khi deploy command trả thành công.
- Bỏ qua failed attempt hoặc rollback.
- Giảm test/approval cần thiết.
- Chỉ đo change nhỏ và bỏ change khó.
- Đẩy lỗi sang giai đoạn sau release.

Để giảm rủi ro, giữ định nghĩa minh bạch, kết hợp quality/reliability metrics và xem xét các outlier. Metric là công cụ học hỏi về hệ thống, không phải thước đo giá trị cá nhân.

## 18. Checklist triển khai đo lead time

### Định nghĩa

- [ ] Mốc bắt đầu được định nghĩa rõ: commit integrated hoặc release input.
- [ ] Mốc kết thúc phản ánh usable, không chỉ deploy request thành công.
- [ ] Environment và phạm vi cohort được ghi rõ.
- [ ] Lead time được phân biệt với PR cycle, CI duration và deployment duration.
- [ ] Quy tắc map change/commit vào deployment được công bố.

### Dữ liệu và liên kết

- [ ] Có event ID, change ID, commit SHA, pipeline run, artifact digest và deployment ID.
- [ ] Timestamp có UTC/timezone, event time và recorded time.
- [ ] Có thể liên kết artifact đã test với artifact runtime.
- [ ] Deployment chứa nhiều commit được xử lý nhất quán.
- [ ] Có quy tắc cho squash, cherry-pick, batch release và nhiều environment.
- [ ] Event trùng, thiếu hoặc sai thứ tự được phát hiện.

### Phân tích

- [ ] Báo p50, p75, p90/p95 và sample size.
- [ ] Theo dõi change chưa usable và change age.
- [ ] Phân rã waiting time, processing time và rework time.
- [ ] Phân đoạn theo service, environment và change type.
- [ ] Không loại failed/long-running change một cách âm thầm.
- [ ] Theo dõi clock skew và ingestion lag.

### Cải tiến

- [ ] Chọn bottleneck dựa trên dữ liệu.
- [ ] Theo dõi deployment frequency, change failure và recovery cùng lead time.
- [ ] Cải tiến không làm yếu security, quality gate hoặc rollback readiness.
- [ ] Định nghĩa SLO và phạm vi đo có thể kiểm tra.
- [ ] Dashboard dùng để cải thiện flow, không xếp hạng cá nhân/đội theo một con số.

Đo thời gian từ thay đổi đến khi sử dụng được cần một định nghĩa rõ ràng về change và usable, cùng chuỗi sự kiện có thể truy vết từ commit đến runtime. Khi tách lead time thành thời gian chờ, xử lý, rollout và verification; theo dõi phân phối cùng các change chưa hoàn tất; và đặt cạnh chỉ số chất lượng, nhóm có thể xác định bottleneck thật. Cải tiến tốt là đưa change đến người dùng nhanh hơn trong khi vẫn giữ được tính đúng, an toàn và khả năng phục hồi của hệ thống.

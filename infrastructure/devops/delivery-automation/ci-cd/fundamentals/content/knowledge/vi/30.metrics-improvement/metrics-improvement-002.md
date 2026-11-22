# Phân biệt tần suất triển khai với số lần chạy pipeline

Một nhóm có thể chạy pipeline hàng trăm lần trong tuần nhưng chỉ triển khai production vài lần. Điều đó không mâu thuẫn: pipeline là quy trình tự động kiểm tra, build, đóng gói hoặc triển khai; còn deployment là một thay đổi thực sự được áp dụng vào một môi trường đích. Một pull request có thể kích hoạt nhiều pipeline run mà không tạo deployment nào. Ngược lại, một pipeline run có thể triển khai nhiều dịch vụ hoặc nhiều môi trường.

Vì vậy, **tần suất triển khai (deployment frequency)** và **số lần chạy pipeline (pipeline run count)** là hai chỉ số đo hai hoạt động khác nhau. Deployment frequency phản ánh nhịp đưa thay đổi vào môi trường, thường tập trung vào production. Pipeline run count phản ánh mức độ sử dụng và hoạt động của hệ thống CI. Dùng số lần pipeline chạy để thay thế số lần triển khai sẽ làm sai lệch bức tranh về tốc độ phát hành.

Trong CI/CD, cần định nghĩa rõ sự kiện nào được tính, service nào là đơn vị đo, môi trường nào thuộc phạm vi, và cách xử lý retry, rollback, canary hoặc GitOps. Khi định nghĩa nhất quán, hai chỉ số có thể được dùng cùng nhau để hiểu cả throughput phát hành lẫn hiệu quả của quy trình tự động hóa.

## 1. Hai chỉ số trả lời hai câu hỏi khác nhau

**Deployment frequency** trả lời: một service được triển khai thành công vào môi trường mục tiêu bao nhiêu lần trong một khoảng thời gian?

**Pipeline run count** trả lời: hệ thống CI đã khởi chạy bao nhiêu lần thực thi pipeline trong cùng khoảng thời gian?

| Khía cạnh | Deployment frequency | Pipeline run count |
|---|---|---|
| Đơn vị đo | Deployment event thành công | Pipeline execution/run |
| Câu hỏi | Thay đổi được đưa vào môi trường bao thường xuyên? | Pipeline được kích hoạt/chạy bao nhiêu lần? |
| Phạm vi thường dùng | Một service và một môi trường, đặc biệt production | Repository, workflow, branch, team hoặc CI platform |
| Bao gồm | Thay đổi thực sự được áp dụng và xác minh theo định nghĩa | PR checks, push builds, scheduled jobs, manual runs, deploy jobs |
| Không tự động bao gồm | Job deploy thất bại, no-op không thay đổi trạng thái | Deployment event; một run có thể không deploy |
| Mục đích | Đo throughput phát hành | Đo hoạt động và tải của hệ thống CI |

Ví dụ: một commit mở pull request kích hoạt lint, unit test, security scan và build preview. Bốn pipeline run có thể được ghi nhận, nhưng nếu chưa có thay đổi nào được triển khai vào production thì deployment frequency vẫn không tăng.

Một pipeline release sau đó có thể triển khai cùng artifact lên staging rồi production. Pipeline run count tăng một; deployment frequency của production tăng một lần cho service tương ứng. Nếu pipeline đó triển khai ba service độc lập, số deployment event ở cấp service có thể là ba dù chỉ có một pipeline run.

## 2. Định nghĩa deployment event trước khi đếm

Không thể đo deployment frequency chính xác nếu mỗi nhóm hiểu “một lần triển khai” theo cách khác nhau. Nên viết một định nghĩa vận hành có thể kiểm tra tự động.

Một định nghĩa thường dùng ở cấp service:

> Một deployment event được tính khi một phiên bản artifact hoặc cấu hình mới của một service được áp dụng thành công vào môi trường mục tiêu, đạt trạng thái hoàn tất theo deployment controller và được ghi nhận bằng một deployment ID duy nhất.

Định nghĩa cần trả lời:

- **Service:** đơn vị nào được đo? Một microservice, ứng dụng, workload hay toàn bộ sản phẩm?
- **Environment:** production, staging hay tất cả? Nếu đo DORA deployment frequency, cần tách production khỏi môi trường thử nghiệm.
- **Success:** lệnh deploy trả về thành công, rollout hoàn tất, hay post-deployment validation cũng phải đạt?
- **Change:** có cần observed version/config thay đổi không, hay một lần reconcile không thay đổi gì cũng tính?
- **Identity:** deployment ID nào xác định một lần triển khai logic?
- **Time:** dùng thời điểm bắt đầu, hoàn tất hay thời điểm được xác minh?

Với metric phát hành, thường dùng thời điểm deployment thành công/được xác minh làm timestamp. Cách này tránh tính một lần triển khai chưa hoàn tất vào kỳ đo. Cần lưu cả started_at và completed_at để phân tích lead time và thời gian rollout.

Định nghĩa phải nhất quán qua các service và thời gian. Nếu thay đổi quy tắc đếm, hãy version hóa định nghĩa metric và ghi chú khi so sánh dữ liệu lịch sử.

## 3. Pipeline run là gì?

Pipeline run là một lần workflow hoặc pipeline được hệ thống CI khởi chạy. Run có thể được kích hoạt bởi:

- Push commit lên branch.
- Mở, cập nhật hoặc đồng bộ pull request.
- Merge vào branch chính.
- Tạo tag hoặc release.
- Lịch chạy định kỳ như nightly build.
- Người dùng chạy thủ công.
- Sự kiện từ registry, dependency bot hoặc hệ thống ngoài.
- Retry/re-run sau khi job thất bại hoặc bị hủy.

Một pipeline run có thể chỉ chạy test, có thể tạo artifact, hoặc có thể triển khai. Không phải run nào cũng có deployment. Cũng cần phân biệt workflow run, job attempt và step retry: một workflow có thể có nhiều job; một job có thể được thử lại; một workflow run có thể bị re-run toàn bộ.

Khi đếm pipeline run, hãy xác định phạm vi: đếm mỗi workflow execution hay mỗi attempt? Thông thường, số workflow run được tạo là một chỉ số; số job attempt và retry là các chỉ số phụ để hiểu tải và độ ổn định. Không cộng lẫn chúng thành một con số không có đơn vị rõ ràng.

## 4. Công thức và đơn vị đo

### Deployment frequency

Ở cấp một service và một môi trường:

```text
Deployment frequency =
  số deployment event thành công trong khoảng thời gian
  / độ dài khoảng thời gian
```

Ví dụ, service A có 8 deployment production thành công trong 7 ngày:

```text
DF(A, production, 7 days) = 8 deployments / 7 days
                            ≈ 1.14 deployments per day
```

Có thể báo cáo dưới dạng “8 deployments/tuần” thay vì quy đổi trung bình theo ngày để người đọc dễ hiểu. Với tần suất thấp, nên báo cả số sự kiện và khoảng thời gian quan sát; một con số trung bình đơn lẻ có thể che giấu các khoảng im lặng dài.

### Pipeline run count

```text
Pipeline run count =
  số workflow run được tạo trong khoảng thời gian
  theo phạm vi repository/workflow/branch đã chọn
```

Đây là số đếm, không phải tốc độ triển khai. Có thể bổ sung pipeline runs per day, per repository hoặc per workflow để theo dõi tải CI.

Không so sánh trực tiếp “8 deployments/tuần” với “120 pipeline runs/tuần” như hai đại lượng cùng ý nghĩa. Chúng có thể được đặt cạnh nhau, nhưng cần giữ tên, đơn vị và phạm vi riêng.

## 5. Ví dụ: nhiều pipeline run nhưng ít deployment

Giả sử một nhóm có dữ liệu trong một tuần:

| Hoạt động | Số lượng |
|---|---:|
| Pull request checks | 52 pipeline runs |
| Push/branch builds | 28 pipeline runs |
| Nightly/security scans | 14 pipeline runs |
| Manual/re-run jobs | 11 pipeline runs |
| Release workflows | 15 pipeline runs |
| **Tổng pipeline runs** | **120** |
| Deployment production thành công của service A | 4 |
| Deployment production thành công của service B | 1 |
| Deployment production thành công của service C | 0 |

Tổng pipeline run count là 120. Tổng deployment event production ở cấp service là 5. Nếu một release workflow triển khai service A và B trong cùng lần chạy, run đó vẫn là một pipeline run nhưng tạo hai deployment event ở cấp service.

Không nên kết luận rằng nhóm “triển khai 120 lần” hoặc pipeline đang triển khai quá thường xuyên. Phần lớn run chỉ kiểm tra thay đổi trước khi merge. Để hiểu năng suất phát hành, hãy xem deployment frequency theo từng service; để hiểu tải CI, hãy xem pipeline run count theo loại trigger và workflow.

## 6. Ví dụ: một deployment có thể tạo nhiều pipeline run

Một lần phát hành có thể gồm:

1. Pull request pipeline chạy khi mở PR.
2. Pull request pipeline chạy lại khi cập nhật commit.
3. Required checks được re-run sau khi runner gặp lỗi.
4. Merge vào main kích hoạt build pipeline.
5. Release pipeline tạo artifact và deploy staging.
6. Một job thủ công phê duyệt rồi deploy production.

Tùy cách nền tảng ghi nhận, đây có thể là 5–6 pipeline runs nhưng chỉ có một deployment event production cho service đó. Nếu release pipeline thất bại trước khi áp dụng thay đổi, deployment frequency không tăng. Nếu deploy production đã hoàn tất nhưng job bị timeout khi chờ response, phải reconcile trạng thái đích trước khi quyết định có deployment event hay cần retry.

## 7. Retry, re-run và job attempt được tính thế nào?

Đây là nguồn gây sai lệch phổ biến. Cần phân biệt:

- **Pipeline rerun:** chạy lại workflow hoặc toàn bộ pipeline.
- **Job retry:** chạy lại một job trong cùng workflow.
- **Step retry:** một bước tự thử lại request hoặc command.
- **Deployment retry:** gửi lại yêu cầu triển khai hoặc tiếp tục operation đã được nhận.

Với pipeline run count, một workflow re-run mới thường là một run mới theo định nghĩa của CI platform. Job/step attempt nên được đo riêng. Với deployment frequency, không tính mỗi attempt là một deployment. Chỉ đếm deployment event logic đã thành công theo định nghĩa.

Ví dụ: lần deploy đầu timeout ở phía CI nhưng controller đã cập nhật production thành công. Runner truy vấn trạng thái và xác nhận deployment ID cũ đã hoàn tất. Đây vẫn là một deployment event, dù client có thể đã thực hiện nhiều request hoặc job attempt.

Nếu lần đầu thất bại trước khi thay đổi production, lần retry sau thành công thì chỉ có một deployment event thành công. Số attempt là hai và nên được lưu để đo độ ổn định.

## 8. Rollback, hotfix và thay đổi cấu hình

Rollback cũng là một thay đổi thực sự ở production nếu nó triển khai lại artifact cũ hoặc áp dụng cấu hình phục hồi. Không nên âm thầm loại bỏ rollback khỏi lịch sử deployment.

Nên lưu riêng loại sự kiện:

- Normal release: phát hành phiên bản theo kế hoạch.
- Hotfix: thay đổi khẩn cấp để sửa lỗi.
- Rollback: đưa service về artifact/config trước đó.
- Roll-forward: triển khai bản sửa mới để khắc phục.
- Config-only change: thay đổi cấu hình runtime mà không đổi binary.

Với báo cáo deployment frequency tổng thể, tổ chức có thể tính mọi deployment event thành công làm thay đổi trạng thái production, bao gồm rollback. Đồng thời, phân loại theo change_type để người đọc thấy tỷ lệ rollback/hotfix. Nếu metric được dùng cho DORA hoặc benchmark, phải công bố quy tắc tính và giữ nhất quán; không loại các deployment gây sự cố chỉ để làm đẹp số liệu.

Config-only change có được tính hay không phụ thuộc định nghĩa deployment của tổ chức. Nếu thay đổi cấu hình được phát hành như một thay đổi production có kiểm soát, nên ghi thành event riêng. Thay đổi một dashboard hoặc metadata không ảnh hưởng runtime thì không nên tính như deployment service.

## 9. Canary, blue-green và rollout nhiều bước

Một deployment logic có thể đi qua nhiều giai đoạn:

- Bắt đầu canary với 5% traffic.
- Tăng lên 25%, 50%, rồi 100%.
- Chuyển traffic blue-green từ pool cũ sang pool mới.
- Cập nhật nhiều replica hoặc nhiều availability zone.

Không nên tính mỗi bước tăng traffic, mỗi pod restart hoặc mỗi region wave thành một deployment mới nếu chúng là các phase của cùng một rollout và cùng deployment ID. Hãy ghi rollout phase riêng để phân tích thời gian, health và quyết định promote/abort.

Nếu rollout bị abort và rollback về version trước, ghi một event rollback liên kết với deployment ban đầu. Nếu sau đó phát hành một digest khác, đó là deployment event mới.

Với multi-region, cần chọn một đơn vị báo cáo:

- **Logical service deployment:** một lần phát hành cùng release cho service trên toàn bộ target region; phù hợp để đo nhịp release ở cấp service.
- **Per-region deployment:** mỗi region được cập nhật là một event; hữu ích cho vận hành và phân tích rollout.

Không cộng hai cách đếm vào cùng một metric. Có thể lưu cả hai dimension nhưng dashboard phải nói rõ đang hiển thị logical deployment hay region-level operation.

## 10. GitOps và reconcile không có thay đổi

Trong GitOps, controller có thể reconcile desired state liên tục. Một lần sync hoặc reconcile không nhất thiết là một deployment event.

Phân biệt:

- Reconcile loop kiểm tra trạng thái nhưng không có thay đổi: không tính deployment.
- Apply manifest mới làm thay đổi runtime state: có thể tạo deployment event.
- Retry reconcile do controller lỗi nhưng vẫn cùng desired revision: không tính nhiều deployment event.
- Drift correction đưa runtime về desired revision: ghi change/reconciliation event; chỉ tính deployment nếu có thay đổi runtime thực sự theo định nghĩa.
- Một commit cấu hình được apply thành công và thay đổi service: tính một event cho service/target đã chọn.

Nên lấy dữ liệu từ controller event hoặc deployment record có revision/digest và observed state, thay vì đếm số lần GitOps sync. Nếu controller phát nhiều event cho cùng một revision, cần deduplicate theo deployment ID hoặc change identity.

## 11. Một pipeline triển khai nhiều service

Monorepo hoặc release train có thể dùng một pipeline để triển khai nhiều service. Đếm deployment ở cấp pipeline sẽ làm mất độ phân giải:

Ví dụ một workflow triển khai:

- orders-service digest A lên production.
- payments-service digest B lên production.
- notifications-service không đổi nên bị skip.

Pipeline run count tăng một. Deployment frequency tăng một cho orders-service và một cho payments-service; notifications-service không tăng. Nếu tổ chức chỉ đo release train như một sản phẩm duy nhất, có thể ghi thêm release event cấp sản phẩm, nhưng không thay thế metric service-level khi đánh giá từng service.

Event model nên hỗ trợ quan hệ một-nhiều giữa pipeline run và deployment event. Mỗi deployment event có service, environment, target và digest riêng, cùng pipeline_run_id tham chiếu về run đã tạo nó.

## 12. Thiết kế dữ liệu sự kiện để đếm nhất quán

Một deployment event có thể lưu các trường:

| Trường | Ý nghĩa |
|---|---|
| deployment_id | ID duy nhất của lần triển khai logic |
| service_id | Service được triển khai |
| environment | Môi trường đích |
| target_scope | Cluster, namespace, region hoặc nhóm target |
| release_id | Release hoặc change request liên quan |
| pipeline_run_id | Pipeline run khởi tạo thao tác |
| artifact_digest | Nội dung artifact đã triển khai |
| config_revision | Revision cấu hình được áp dụng |
| change_type | normal, hotfix, rollback, roll-forward, config-only |
| status | accepted, running, succeeded, failed, cancelled |
| started_at | Thời điểm bắt đầu |
| completed_at | Thời điểm hoàn tất |
| verified_at | Thời điểm post-deployment validation đạt |
| source_commit | Commit nguồn |

Pipeline run record nên có run_id, workflow, repository, trigger, branch/ref, commit SHA, attempt, started_at, completed_at và conclusion. Hai record liên kết qua pipeline_run_id; không suy ra deployment count từ run count.

Ví dụ event:

```json
{
  "deployment_id": "dep-2026-004281",
  "service_id": "orders-service",
  "environment": "production",
  "target_scope": "ap-southeast-1/prod-orders",
  "release_id": "orders-2.7.1",
  "pipeline_run_id": "ci-18452",
  "artifact_digest": "sha256:abc123...",
  "config_revision": "7c91e2...",
  "change_type": "normal",
  "status": "succeeded",
  "started_at": "2026-11-18T09:24:00Z",
  "completed_at": "2026-11-18T09:28:42Z",
  "verified_at": "2026-11-18T09:30:00Z",
  "source_commit": "4f2a9c1..."
}
```

Schema trên là ví dụ. Cần có unique constraint cho deployment_id trong phạm vi phù hợp, lưu event history và không ghi đè các lần thử. Với rollout nhiều target, có thể có deployment parent và child target records.

## 13. Deduplication và nguồn dữ liệu đáng tin cậy

Deployment frequency sẽ bị đếm thừa nếu cùng một deployment được ghi từ nhiều nguồn: CI job, deployment controller, webhook và observability collector. Cần xác định nguồn nào là source of truth và cơ chế deduplication.

Các nguyên tắc:

- Sinh deployment ID ổn định khi tạo operation.
- Mọi event phase của cùng rollout dùng chung deployment ID.
- Retry dùng lại operation/idempotency identity khi tiếp tục cùng một ý định.
- Chỉ chuyển sang trạng thái succeeded khi điều kiện thành công đã đạt.
- Không tính event chỉ vì API nhận request hoặc job bắt đầu.
- Deduplicate webhook/event delivery theo event ID hoặc deployment ID + sequence.
- Lưu nguồn xác minh và timestamp để audit.

Nếu không có deployment controller record, có thể tạo event từ CI sau khi xác minh observed digest/config revision. Tránh lấy duy nhất kết quả exit code của lệnh deploy làm bằng chứng.

## 14. Dashboard nên hiển thị hai metric riêng

Một dashboard hữu ích có thể đặt hai chỉ số cạnh nhau nhưng giữ đúng đơn vị:

| Dashboard panel | Metric | Phân nhóm |
|---|---|---|
| Production deployment frequency | Successful deployment events / service / week | Service, environment, change type |
| Pipeline run volume | Workflow runs / week | Repository, workflow, trigger |
| Pipeline success rate | Successful runs / total completed runs | Workflow, branch |
| Deployment success rate | Successful deployment events / attempted deployments | Service, environment |
| Deployment duration | Started to completed/verified | Strategy, service |
| Retry/re-run rate | Runs or attempts retried / initial runs | Workflow, failure reason |
| Rollback rate | Rollback events / deployment events | Service, release |

Không gộp “pipeline success rate” với “deployment success rate”. Một pipeline có thể thành công khi chạy test nhưng không deploy; một pipeline có thể kết thúc lỗi sau khi deployment đã thành công nhưng bước report bị lỗi. Cần có trạng thái riêng cho operation triển khai và workflow run.

## 15. Dùng hai metric để tìm vấn đề

Hai chỉ số có ý nghĩa hơn khi được phân tích cùng nhau:

| Quan sát | Cách diễn giải có thể | Câu hỏi tiếp theo |
|---|---|---|
| Pipeline runs tăng, deployment frequency ổn định | Nhiều PR/build hơn, nhiều test hoặc nhiều retry | Run tăng do hoạt động phát triển, lịch scan hay flaky test? |
| Pipeline runs thấp, deployment frequency thấp | Ít thay đổi hoặc quy trình phát hành chậm | Có bottleneck review, approval, test hay release window? |
| Pipeline runs ổn định, deployment frequency tăng | Release nhỏ và thường xuyên hơn | Change failure/rollback có tăng không? |
| Pipeline runs tăng mạnh, success rate giảm | CI không ổn định hoặc dependency/runner lỗi | Queue, flaky test, quota hay thay đổi toolchain? |
| Deployment frequency tăng, rollback tăng | Phát hành nhanh nhưng chất lượng có thể giảm | Kiểm tra change failure rate và post-deploy signals |
| Một pipeline run tạo nhiều deployment event | Một release train triển khai nhiều service | Có cần báo cáo thêm theo service và product release? |

Đừng kết luận nguyên nhân chỉ từ hai con số. Kết hợp lead time for changes, change failure rate, failed deployment, rollback, MTTR và các chỉ số pipeline để hiểu toàn bộ luồng delivery.

## 16. Tránh metric gaming

Khi deployment frequency trở thành mục tiêu, nhóm có thể vô tình tối ưu con số thay vì khả năng phát hành an toàn:

- Chia một thay đổi không cần thiết thành nhiều deployment nhỏ chỉ để tăng count.
- Tính mỗi pod, region wave hoặc canary step thành deployment riêng.
- Đếm deploy request dù rollout thất bại.
- Bỏ rollback khỏi dữ liệu để giảm tỷ lệ sự cố.
- Tăng pipeline run bằng cách chạy lại workflow không tạo thêm giá trị.
- Gộp nhiều service vào một đơn vị đo để che giấu service triển khai chậm.

Biện pháp:

- Định nghĩa event và đơn vị đo trước khi đặt mục tiêu.
- Đo ở cấp service và production environment khi phù hợp.
- Lưu cả success, failure, rollback và attempt để không mất ngữ cảnh.
- Theo dõi change failure rate, recovery time và chất lượng cùng deployment frequency.
- Không dùng pipeline run count làm proxy cho deployment frequency.
- Không thưởng chỉ dựa trên một metric đơn lẻ.
- Audit các thay đổi trong quy tắc đếm và dashboard.

Mục tiêu là tăng khả năng đưa thay đổi có giá trị đến người dùng một cách an toàn, không phải làm cho biểu đồ deployment count tăng bằng mọi giá.

## 17. Ví dụ truy vấn dữ liệu

Giả sử bảng deployment_events có một dòng cho mỗi deployment logic và trạng thái cuối cùng đã được chuẩn hóa. Truy vấn deployment frequency của từng service trong một tuần:

```sql
SELECT
    service_id,
    COUNT(*) AS successful_production_deployments
FROM deployment_events
WHERE environment = 'production'
  AND status = 'succeeded'
  AND completed_at >= TIMESTAMP '2026-11-11 00:00:00'
  AND completed_at <  TIMESTAMP '2026-11-18 00:00:00'
GROUP BY service_id
ORDER BY service_id;
```

Truy vấn pipeline run count theo trigger:

```sql
SELECT
    trigger_type,
    COUNT(*) AS pipeline_runs
FROM pipeline_runs
WHERE started_at >= TIMESTAMP '2026-11-11 00:00:00'
  AND started_at <  TIMESTAMP '2026-11-18 00:00:00'
GROUP BY trigger_type
ORDER BY pipeline_runs DESC;
```

Các truy vấn là ví dụ và cần điều chỉnh theo schema thực tế. Nếu bảng deployment_events có nhiều dòng cho từng phase hoặc region, cần truy vấn logical deployment parent hoặc deduplicate theo deployment_id trước khi COUNT. Nếu metric dùng verified_at làm thời điểm ghi nhận, thay completed_at bằng verified_at và ghi rõ trong định nghĩa.

## 18. Quy trình triển khai đo lường

Có thể xây dựng metric theo các bước:

1. Chọn service và môi trường cần đo; ưu tiên production.
2. Viết định nghĩa deployment event và pipeline run.
3. Xác định source of truth: CI platform, deployment controller hoặc event collector.
4. Tạo deployment ID và liên kết pipeline_run_id.
5. Chuẩn hóa trạng thái, change type và timestamp.
6. Xử lý retry, rerun, multi-region, canary và GitOps deduplication.
7. Backfill dữ liệu lịch sử nếu nguồn đủ tin cậy; ghi rõ giới hạn dữ liệu.
8. Xây dashboard riêng cho deployment frequency và pipeline run count.
9. Đối chiếu một số lần release thực tế với record được đếm.
10. Review định nghĩa định kỳ khi kiến trúc hoặc quy trình thay đổi.

Trong giai đoạn đầu, nên chạy metric ở chế độ quan sát và đối chiếu thủ công trước khi dùng để đặt mục tiêu. Nếu dữ liệu chưa đủ, báo rõ mức độ tin cậy thay vì đưa ra con số chính xác giả tạo.

## 19. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng pipeline run count làm deployment frequency | Đánh giá sai nhịp phát hành | Đếm deployment event thực tế theo service/environment |
| Tính cả PR checks và nightly scan vào deployment | Tăng số giả tạo | Tách workflow activity khỏi deployment |
| Đếm mỗi retry là deployment mới | Đếm trùng cùng một thay đổi | Dùng deployment ID và deduplication |
| Đếm mỗi canary step hoặc pod update | Một rollout bị tính nhiều lần | Dùng logical deployment ID, lưu phase riêng |
| Bỏ rollback khỏi lịch sử | Mất dữ liệu về recovery và chất lượng | Phân loại rollback riêng, công bố quy tắc |
| Đếm run thành công dù deploy bị skip | Báo cáo có deployment không tồn tại | Kiểm tra observed state và deployment record |
| Gộp nhiều service thành một đơn vị | Không thấy service phát hành chậm | Báo cáo service-level và product-level riêng |
| Không định nghĩa production/target | Số liệu giữa nhóm không so sánh được | Chuẩn hóa environment taxonomy |
| Dùng timestamp không nhất quán | Sự kiện rơi sai kỳ báo cáo | Chọn completed/verified time và chuẩn UTC |

## 20. Checklist phân biệt và đo hai chỉ số

- [ ] Có định nghĩa riêng cho pipeline run và deployment event.
- [ ] Deployment frequency được đo theo service và environment rõ ràng.
- [ ] Chỉ tính deployment đã thành công theo điều kiện được công bố.
- [ ] Pipeline run count có phạm vi workflow/repository/trigger rõ ràng.
- [ ] Job attempt, step retry và workflow rerun được đo riêng khi cần.
- [ ] Retry của cùng deployment không tạo deployment event trùng.
- [ ] Rollback, hotfix, roll-forward và config-only change được phân loại.
- [ ] Canary phase, region wave và GitOps no-op reconcile không bị đếm sai.
- [ ] Pipeline một-nhiều deployment event được hỗ trợ trong event model.
- [ ] Có deployment ID, pipeline_run_id, artifact digest và source commit.
- [ ] Event được deduplicate và đối chiếu với observed state.
- [ ] Dashboard giữ đơn vị, phạm vi và time window riêng cho từng metric.
- [ ] Phân tích hai metric cùng success rate, rollback, change failure và recovery time.
- [ ] Có review định nghĩa và kiểm tra metric gaming định kỳ.

Deployment frequency cho biết service đưa thay đổi vào môi trường mục tiêu thường xuyên đến đâu; pipeline run count cho biết hệ thống CI thực thi workflow bao nhiêu lần. Khi tách đúng hai đơn vị đo, ghi deployment event theo service/environment và xử lý nhất quán retry, rollback, canary cùng GitOps, nhóm có thể đánh giá throughput phát hành và tải tự động hóa mà không nhầm lẫn hai hoạt động.

# Đo thời gian phục hồi và duy trì runbook DR

## 1. Mục tiêu và phạm vi

Trong chương **Sao lưu và khôi phục thảm họa** của module Oracle Cloud Infrastructure (OCI), bài này giải quyết hai câu hỏi vận hành: **dịch vụ thực sự phục hồi sau bao lâu** và **làm thế nào để đội trực dùng được runbook DR khi có sự cố**.

Sau bài học, bạn có thể:

- Chọn mốc bắt đầu, mốc kết thúc và nguồn bằng chứng cho phép đo phục hồi.
- Đối chiếu thời gian phục hồi thực tế với RTO, đồng thời kiểm chứng điểm dữ liệu phục hồi theo RPO.
- Phân biệt thời gian thao tác hạ tầng, thời gian chạy DR plan và thời gian người dùng chịu gián đoạn.
- Thiết kế diễn tập có phạm vi rõ ràng trên OCI và giải thích giới hạn của kết quả.
- Xây dựng runbook có người chịu trách nhiệm, điều kiện thực hiện, tiêu chí xác nhận và quy trình duy trì.

Bạn cần biết cơ bản về tenancy, compartment, IAM, VCN, Compute, lưu trữ, sao lưu và phương án phục hồi cơ sở dữ liệu Oracle. Bài học tập trung vào đo lường và điều hành quy trình; cách cấu hình từng cơ chế sao lưu hoặc nhân bản thuộc phạm vi thiết kế hạ tầng tương ứng.

Các con số, tên ứng dụng và ngưỡng kiểm thử trong bài là **ví dụ học tập**, không phải cam kết thời gian phục hồi của Oracle.

## 2. Xác định thế nào là “đã phục hồi”

### 2.1. Tách mục tiêu khỏi kết quả đo

**Recovery Time Objective (RTO)** là thời gian gián đoạn tối đa mà nghiệp vụ chấp nhận. **Recovery Point Objective (RPO)** là mức mất dữ liệu tối đa có thể chấp nhận, thường được biểu diễn bằng một khoảng thời gian. Đây là các mục tiêu cần thống nhất trước khi chọn phương án DR. [Oracle: Plan Your Disaster Recovery Strategy](https://docs.oracle.com/en/solutions/oci-best-practices/plan-your-disaster-recovery-strategy.html).

Trong báo cáo, nên dùng các tên riêng cho mục tiêu và kết quả:

| Đại lượng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| RTO mục tiêu | Giới hạn gián đoạn đã được nghiệp vụ chấp thuận | 45 phút |
| Thời gian phục hồi thực tế | Khoảng thời gian đo từ lúc dịch vụ bị gián đoạn đến lúc đạt tiêu chí phục hồi | 37 phút |
| RPO mục tiêu | Giới hạn khoảng dữ liệu có thể không phục hồi được | 120 giây |
| Khoảng lùi điểm phục hồi quan sát được | Khoảng cách từ thời điểm gián đoạn đến điểm dữ liệu nhất quán đã được kiểm chứng | 80 giây |
| Thời gian chạy DR plan | Thời gian riêng của lần thực thi quy trình điều phối | 15 phút |

Không ghi “RTO = 15 phút” chỉ vì công cụ điều phối hoàn thành trong 15 phút. Cần nói rõ đó là mục tiêu, kết quả đầu cuối hay thời gian của một thành phần.

### 2.2. Viết tiêu chí kết thúc trước khi chạy

Một máy Compute ở trạng thái chạy hoặc cơ sở dữ liệu mở thành công chưa đủ để xác nhận hệ thống đặt hàng đã phục hồi. Tiêu chí cần gắn với chức năng và mức phục vụ mà nghiệp vụ yêu cầu.

Ví dụ, đội vận hành thống nhất dịch vụ đặt hàng được xem là phục hồi khi:

1. Người dùng thử nghiệm đăng nhập qua đường truy cập được bảo vệ như đã thiết kế.
2. Tạo đơn thử có mã chống trùng, đọc lại được đơn và kiểm tra được trạng thái ghi nhận.
3. Đơn có tệp đính kèm đọc được tệp tương ứng từ nơi lưu trữ tại đích.
4. Các tác vụ cần thiết đã chạy; tác vụ có tác động bên ngoài được bật theo đúng giai đoạn.
5. Tại tải kiểm thử đã thống nhất, tỷ lệ lỗi nhỏ hơn 1% và độ trễ p95 nhỏ hơn 1 giây trong 5 phút liên tục.
6. Kết quả đối soát dữ liệu đáp ứng RPO và không phát hiện bất nhất chặn nghiệp vụ.
7. Người phụ trách nghiệp vụ xác nhận kết quả theo thẩm quyền trong runbook.

Ngưỡng tải phải có ý nghĩa: 100 yêu cầu/phút không chứng minh khả năng phục vụ 10.000 yêu cầu/phút. Nếu DR chỉ phục hồi chế độ tối thiểu, chẳng hạn cho phép tra cứu nhưng tạm khóa tạo đơn, cần đặt tên và mục tiêu riêng cho chế độ này.

Trong ví dụ trên, cửa sổ ổn định 5 phút được tính vào thời gian phục hồi. Nếu nhóm chọn quy ước khác, phải ghi rõ mốc bắt đầu ổn định và mốc hoàn tất xác minh; không đổi quy ước sau khi đã thấy kết quả.

### 2.3. Quy định mốc bắt đầu

Với sự cố thật, chọn thời điểm sớm nhất có bằng chứng đáng tin cậy rằng dịch vụ không còn đáp ứng tiêu chí phục vụ. Nguồn có thể là kiểm thử từ phía người dùng, số liệu lỗi hoặc nhật ký giao dịch.

Với diễn tập, ghi ít nhất hai mốc nếu chúng khác nhau:

- **Thời điểm phát lệnh gây lỗi:** bộ điều khiển bắt đầu kịch bản.
- **Thời điểm dịch vụ bị ảnh hưởng:** kiểm thử đầu cuối xác nhận gián đoạn.

Một diễn tập dựng bản sao ở đích nhưng không gây gián đoạn nguồn không có thời gian ngừng dịch vụ sản xuất để đo. Báo cáo của nó phải ghi “thời gian dựng và xác nhận bản sao DR”, kèm phạm vi đã kiểm tra.

Nếu hệ thống thăm dò mỗi 60 giây, thời điểm gián đoạn có thể nằm giữa lần thành công cuối và lần thất bại đầu. Hãy lưu khoảng bất định này. Không báo cáo độ chính xác đến từng giây khi nguồn quan sát chỉ có độ phân giải một phút.

## 3. Dựng timeline phục hồi

### 3.1. Các mốc tối thiểu

Một bộ mốc dùng được cho nhiều quy trình DR:

| Mốc | Sự kiện | Bằng chứng phù hợp |
| --- | --- | --- |
| `t_outage` | Dịch vụ bắt đầu gián đoạn | Kết quả thăm dò, giao dịch thất bại |
| `t_detected` | Hệ thống hoặc người trực phát hiện | Alarm, sự kiện tiếp nhận của đội trực |
| `t_declared` | Người có thẩm quyền quyết định kích hoạt DR | Nhật ký quyết định trong hồ sơ sự cố |
| `t_execution_start` | Bắt đầu thực thi quy trình đã chọn | Execution ID, nhật ký bộ điều phối |
| `t_execution_end` | Quy trình điều phối hoàn tất | Kết quả thực thi và log bước |
| `t_route_verified` | Xác nhận truy cập qua đường phục vụ đích | Kiểm thử từ các vị trí đại diện |
| `t_service_restored` | Đủ tiêu chí phục hồi đầu cuối | Báo cáo kiểm thử và xác nhận nghiệp vụ |

Nếu precheck chạy ngay trước quy trình, ghi thời gian của nó và xác định có nằm trong `t_execution_start → t_execution_end` hay không. Dù nằm ở đâu trong cách tổ chức log, khoảng thời gian này vẫn thuộc thời gian gián đoạn nếu dịch vụ đang ngừng.

Các bước xác nhận an toàn, chờ phê duyệt, thử lại và xử lý lỗi đều phải xuất hiện trên timeline. Không dừng đồng hồ khi nhóm chuyển từ công cụ tự động sang thao tác thủ công.

### 3.2. Ví dụ có số liệu

Giả sử ứng dụng đặt hàng dùng Compute, Load Balancer và cơ sở dữ liệu Oracle. Có một vùng dự phòng với kết nối và phương án phục hồi dữ liệu đã được chuẩn bị. Nhóm đặt RTO 45 phút và RPO 120 giây.

Tất cả thời điểm sau dùng UTC:

| Sự kiện | Thời điểm ngày 2026-11-21 | Thời gian từ sự kiện trước |
| --- | --- | --- |
| Dịch vụ gián đoạn | 03:00:00 | — |
| Phát hiện và tiếp nhận | 03:02:00 | 2 phút |
| Quyết định kích hoạt DR | 03:07:00 | 5 phút |
| Bắt đầu quy trình điều phối | 03:09:00 | 2 phút |
| Quy trình điều phối hoàn tất | 03:24:00 | 15 phút |
| Xác nhận tuyến truy cập đích | 03:29:00 | 5 phút |
| Hoàn tất kiểm chứng đầu cuối và cửa sổ ổn định | 03:37:00 | 8 phút |

Kết quả:

```text
Thời gian phục hồi thực tế
  = t_service_restored - t_outage
  = 03:37:00 - 03:00:00
  = 37 phút

Thời gian chạy quy trình điều phối
  = t_execution_end - t_execution_start
  = 03:24:00 - 03:09:00
  = 15 phút

Khoảng còn lại so với RTO
  = 45 - 37
  = 8 phút
```

Trong 8 phút kiểm chứng cuối, có thể mất 3 phút để các phép kiểm tra đều đạt, rồi thêm 5 phút theo dõi ổn định. Cần ghi lại các mốc nhỏ này để người đọc hiểu điều kiện kết thúc.

Giả sử điểm dữ liệu nhất quán đã xác minh là `02:58:40Z`:

```text
Khoảng lùi điểm phục hồi
  = 03:00:00 - 02:58:40
  = 80 giây

Đối chiếu RPO mục tiêu
  = 80 giây <= 120 giây
```

Kết luận phù hợp là: **lần kiểm tra này phục hồi dịch vụ sau 37 phút và xác minh được điểm dữ liệu cách thời điểm gián đoạn 80 giây**. Đây là bằng chứng cho kịch bản, cấu hình và tải đã thử. Nó chưa chứng minh mọi sự cố tương lai đều đạt cùng kết quả.

### 3.3. Chia ngân sách thời gian

Phân bổ RTO thành ngân sách giúp nhận ra chỗ cần cải thiện:

| Giai đoạn | Ngân sách ví dụ | Thực tế | Nhận xét |
| --- | --- | --- | --- |
| Phát hiện | 3 phút | 2 phút | Còn 1 phút |
| Quyết định | 5 phút | 5 phút | Hết ngân sách giai đoạn |
| Chuẩn bị và kiểm tra trước thực thi | 2 phút | 2 phút | Cần theo dõi nếu xuất hiện lỗi quyền |
| Điều phối phục hồi | 20 phút | 15 phút | Cần phân tích bước chậm nhất |
| Kiểm chứng đường truy cập | 5 phút | 5 phút | Chưa có khoảng dự phòng |
| Kiểm chứng ứng dụng và ổn định | 10 phút | 8 phút | Còn 2 phút |
| **Tổng** | **45 phút** | **37 phút** | **Còn 8 phút** |

Các giá trị là cách phân bổ nội bộ, không phải giới hạn kỹ thuật của OCI. Chỉ cộng các khoảng nối tiếp không chồng lấn. Nếu kiểm chứng dữ liệu chạy cùng lúc với khởi động ứng dụng, phải biểu diễn quan hệ song song thay vì tính hai lần.

## 4. Thu thập bằng chứng đáng tin cậy trên OCI

### 4.1. Tách ba lớp quan sát

| Lớp | Cần biết | Nguồn bằng chứng |
| --- | --- | --- |
| Điều hành | Ai phát hiện, ai quyết định, vì sao phải chờ | Hồ sơ sự cố hoặc diễn tập |
| Hạ tầng và điều phối | Lệnh nào được gọi, bước nào thành công hoặc lỗi | OCI Audit, DR plan execution, log tự động hóa |
| Dịch vụ và dữ liệu | Người dùng thực hiện được gì, dữ liệu nào còn đầy đủ | Synthetic test, log ứng dụng, truy vấn đối soát |

OCI Audit ghi nhận hoạt động gọi các API công khai được hỗ trợ, gồm thời điểm, nguồn, tài nguyên đích và phản hồi. Nó giúp đối chiếu thao tác điều khiển hạ tầng; một phản hồi API thành công chưa chứng minh ứng dụng đã sẵn sàng. [Oracle: Overview of Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm).

OCI Logging cung cấp service logs và custom logs. Các loại log cần dùng phải được bật hoặc cấu hình thu thập trước, có IAM phù hợp để đội trực tra cứu. Không mặc định mọi nhật ký ứng dụng đã tự xuất hiện trong tenancy. [Oracle: Logging Overview](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm).

Với Full Stack DR, lưu execution ID, trạng thái và log của từng bước. Giao diện xem log có thể chỉ hiện phần cuối; cần tải bản log đầy đủ khi phân tích nguyên nhân và lưu bằng chứng. [Oracle: View Logs for Disaster Recovery Plan Executions](https://docs.oracle.com/en-us/iaas/disaster-recovery/doc/view-logs-dr-plan-executions.html).

### 4.2. Chuẩn hóa thời gian và định danh

Mỗi sự kiện nên có:

- ID sự cố hoặc diễn tập để liên kết nhiều nguồn.
- Thời điểm sự kiện theo ISO 8601 có múi giờ; ưu tiên UTC.
- Thời điểm hệ thống thu thập nhận được sự kiện, nếu khác đáng kể.
- Region, compartment, tài nguyên hoặc execution ID liên quan.
- Phiên bản runbook, phiên bản tự động hóa và nhánh kịch bản.
- Nguồn bằng chứng, người hoặc hệ thống ghi nhận.
- Kết quả, lần thử và lỗi nếu có.

Đồng bộ đồng hồ các máy sinh log và ghi nhận sai lệch đã biết. Trong cùng một tiến trình đo thời lượng, đồng hồ đơn điệu giúp tránh ảnh hưởng của việc chỉnh đồng hồ hệ thống. Khi ghép log giữa nhiều máy, vẫn cần timestamp chuẩn và thông tin sai số.

Mẫu JSON sau là **schema do nhóm vận hành tự thiết kế**, không phải trường mặc định trong API OCI:

```json
{
  "exercise_id": "orders-dr-20261121-01",
  "scenario": "primary-unreachable",
  "event": "service_restored",
  "event_time": "2026-11-21T03:37:00Z",
  "observed_time": "2026-11-21T03:37:02Z",
  "runbook_version": "2.4",
  "automation_revision": "git:<commit-id>",
  "region": "<dr-region>",
  "compartment_id": "<dr-compartment-ocid>",
  "plan_execution_id": "<execution-ocid-if-used>",
  "attempt": 1,
  "result": "passed",
  "evidence_ref": "<restricted-evidence-location>"
}
```

Không đưa mật khẩu, token, private key hoặc thông tin khách hàng vào sự kiện. Runbook ghi vị trí và cách lấy bí mật theo quyền được cấp, thay vì chứa trực tiếp giá trị bí mật.

### 4.3. Đặt nơi quan sát ngoài phạm vi lỗi

Nếu hệ thống giám sát và bản runbook duy nhất cùng phụ thuộc region bị mất, nhóm có thể không biết khi nào sự cố bắt đầu hoặc phải làm gì tiếp theo.

Cần kiểm tra khả năng truy cập trong chính tình huống diễn tập:

- Đội trực đọc được runbook và danh bạ từ một vị trí còn hoạt động.
- Kết quả probe đầu cuối và nhật ký quyết định vẫn được lưu.
- Tài khoản vận hành đăng nhập được, kể cả nhánh truy cập khẩn cấp đã được tổ chức phê duyệt.
- Kho bằng chứng có quyền đọc/ghi phù hợp tại đích và chính sách lưu giữ rõ ràng.
- Log chưa chuyển tới kho trung tâm được giữ tại nguồn và có thể bổ sung sau.

Mục tiêu là tránh mất cả hệ thống phục hồi lẫn cách chứng minh quá trình phục hồi.

## 5. Kiểm chứng RPO cùng với thời gian phục hồi

### 5.1. Xác định điểm dữ liệu có thể sử dụng

Gọi:

- `t_outage` là thời điểm gián đoạn đã chọn.
- `t_recovery_point` là thời điểm mới nhất mà dữ liệu phục hồi được chứng minh đầy đủ, nhất quán và dùng được theo phạm vi nghiệp vụ.

Khi `t_recovery_point <= t_outage`:

```text
recovery_point_gap = t_outage - t_recovery_point
```

Khoảng này biểu diễn độ lùi của điểm phục hồi. Để biết giao dịch thực tế nào mất, vẫn phải đối soát tập giao dịch đã được nguồn chấp nhận với tập giao dịch có tại đích.

Không lấy thời điểm tạo file backup hoặc bản ghi có timestamp lớn nhất làm bằng chứng duy nhất. Một bản ghi mới có thể tồn tại trong khi giao dịch trước đó bị thiếu, tệp đính kèm chưa tới hoặc hàng đợi đang chứa tác vụ chưa xử lý.

### 5.2. Quy trình đối soát cho ứng dụng đặt hàng

Trong môi trường diễn tập, chuẩn bị các giao dịch tổng hợp có ID duy nhất và mã chống trùng. Ghi nhận giao dịch nào thực sự được ứng dụng nguồn xác nhận thành công theo ngữ nghĩa bền vững của ứng dụng.

Một nguồn đối chứng độc lập có thể giữ ID và thời điểm xác nhận mà không chứa nội dung nhạy cảm. Nếu không có nguồn đối chứng còn truy cập được, phải ghi rõ giới hạn kết luận.

Sau phục hồi:

1. Xác định điểm khôi phục của cơ sở dữ liệu theo cơ chế đang dùng.
2. So sánh danh sách ID đã được xác nhận ở nguồn với danh sách đọc được tại đích.
3. Xác minh một mốc liên tục mà mọi giao dịch thuộc phạm vi kiểm tra trước mốc đó đều đầy đủ.
4. Kiểm tra quan hệ đơn hàng, chi tiết đơn và tệp đính kèm.
5. Kiểm tra tác vụ nền, outbox hoặc hàng đợi theo thiết kế ứng dụng.
6. Ghi số giao dịch thiếu, giao dịch trùng, trường hợp không xác định và khoảng lùi điểm phục hồi.

Nếu có nhiều luồng ghi, nhiều partition hoặc giao dịch hoàn tất không theo thứ tự, một số thứ tự lớn nhất không chứng minh toàn bộ dữ liệu trước nó đã đầy đủ. Cần watermark cho từng luồng hoặc bộ đối chứng bao phủ toàn bộ phạm vi.

Một chỉ số độ trễ nhân bản là đầu vào hữu ích cho quyết định, nhưng không thay thế việc kiểm tra dữ liệu đã phục hồi. Với Oracle Data Guard hoặc cơ chế khôi phục từ backup, runbook phải dẫn đúng quy trình và bằng chứng của loại cơ sở dữ liệu đang sử dụng; không dùng một lệnh promote chung cho mọi dịch vụ.

Full Stack DR điều phối quy trình và không tự quyết định RPO của ứng dụng. RPO còn phụ thuộc dịch vụ lưu trữ, cơ sở dữ liệu và cấu hình nhân bản bên dưới. [Oracle: Full Stack Disaster Recovery FAQ, mục RTO và RPO](https://www.oracle.com/cloud/full-stack-disaster-recovery/faq/).

### 5.3. Không kết luận “đạt” khi thiếu bằng chứng

Ví dụ, DR plan chạy xong sau 15 phút và ứng dụng đọc được dữ liệu mới nhất nhìn thấy tại `02:59:50Z`. Nếu không có bằng chứng giao dịch trước đó đã đầy đủ, chưa thể kết luận khoảng mất dữ liệu chỉ là 10 giây.

Báo cáo nên phân biệt:

| Trạng thái | Cách hiểu |
| --- | --- |
| Đạt | Có phép đo và bằng chứng đáp ứng mục tiêu trong phạm vi đã công bố |
| Không đạt | Có bằng chứng vượt mục tiêu hoặc vi phạm tiêu chí bắt buộc |
| Chưa xác minh | Thiếu bằng chứng cần thiết để kết luận |
| Ngoài phạm vi | Hạng mục được loại trừ từ thiết kế diễn tập và được ghi rõ |

Một diễn tập có thể đạt thời gian phục hồi nhưng chưa xác minh RPO. Hai kết quả này cần được báo cáo độc lập.

## 6. Phân tích thời gian của Full Stack DR

Full Stack DR tổ chức plan thành các nhóm và bước. Các nhóm chạy theo thứ tự, còn các bước trong cùng một nhóm chạy song song. Precheck kiểm tra tính phù hợp của plan và cấu hình liên quan; bản thân precheck không thay đổi topology. [Oracle: Overview of Disaster Recovery Plan Executions](https://docs.oracle.com/en-us/iaas/disaster-recovery/doc/overview-dr-plan-executions.html).

Do đó, nếu một nhóm có ba bước độc lập mất 4, 7 và 5 phút, thời gian nhóm xấp xỉ 7 phút cộng chi phí điều phối, thay vì 16 phút. Phải dùng timestamp thực tế vì còn có thời gian chờ, thử lại hoặc xử lý lỗi.

Ví dụ:

```text
Nhóm A: Kiểm tra điều kiện       2 phút
Nhóm B: Phục hồi dữ liệu        7 phút
Nhóm C: Bật các thành phần app  4 phút
Nhóm D: Kiểm tra trong plan     2 phút
                               --------
Thời gian điều phối             15 phút
```

Đường quyết định tổng thời gian là chuỗi phụ thuộc dài nhất, thường gọi là **đường găng**. Giảm một bước song song từ 4 xuống 2 phút sẽ không làm nhóm nhanh hơn nếu bước 7 phút vẫn quyết định thời gian hoàn tất.

Khi tìm nguyên nhân chậm, hỏi theo thứ tự:

1. Nhóm nào chiếm thời gian nhiều nhất?
2. Bước nào quyết định thời điểm nhóm kết thúc?
3. Bước đó đang thực sự xử lý, chờ tài nguyên, chờ quyền hay chờ thao tác con người?
4. Có thể chuẩn bị trước, tự động hóa hoặc song song hóa mà vẫn giữ đúng phụ thuộc không?
5. Sau thay đổi, có còn kiểm chứng dữ liệu và bảo đảm một nơi ghi chủ động không?

Precheck thành công không chứng minh dịch vụ đã phục hồi, dữ liệu đã đạt RPO hoặc tài nguyên sẽ luôn được cấp đủ khi xảy ra sự cố. Cần thực thi và kiểm tra đầu cuối để có bằng chứng cho các yêu cầu đó.

Không bỏ qua một bước lỗi chỉ để làm tổng thời gian đẹp hơn. Nếu chấp nhận tiếp tục trong trạng thái suy giảm, runbook phải định nghĩa trước điều kiện, thẩm quyền và tác động.

## 7. Chọn diễn tập phù hợp với điều cần chứng minh

### 7.1. Các hình thức và giới hạn

| Hình thức | Điều kiểm tra được | Giới hạn cần ghi |
| --- | --- | --- |
| Tabletop: đi qua kịch bản trên bàn | Quyết định, liên lạc, trình tự và trách nhiệm | Không đo được thời gian phục hồi hạ tầng thực |
| Khôi phục bản sao cô lập | Khả năng dùng backup, cấu hình và kiểm chứng dữ liệu | Có thể chưa kiểm tra tuyến người dùng hoặc lỗi nguồn |
| DR drill có điều phối | Khả năng dựng và kiểm tra stack tại đích | Phụ thuộc thành phần được hỗ trợ và cấu hình cô lập |
| Switchover có kế hoạch | Quy trình chuyển vai trò khi nguồn còn hoạt động | Có thể thuận lợi hơn tình huống nguồn không truy cập được |
| Failover trong môi trường thử với nguồn bị cô lập | Nhánh phục hồi khi không dựa được vào nguồn | Chỉ đại diện cho lỗi và quy mô đã mô phỏng |
| Chuyển trở lại có kiểm soát | Đồng bộ ngược, chuyển vai trò và kiểm chứng lần nữa | Cần kế hoạch và phép đo riêng |

Theo thuật ngữ Full Stack DR, Start DR Drill dựng bản sao stack ở standby và Stop DR Drill kết thúc bản sao phục vụ diễn tập. Switchover và failover là các loại chuyển đổi khác nhau. [Oracle: Full Stack Disaster Recovery Terminology and Concepts](https://docs.oracle.com/en-us/iaas/disaster-recovery/doc/disaster-recovery-terminology.html).

Khả năng dựng bản sao không đồng nghĩa mọi tác động của ứng dụng đã được cô lập. Runbook cần xử lý endpoint thanh toán, email, webhook, lịch chạy và đường ghi dữ liệu. Kiểm tra loại tài nguyên và plan được hỗ trợ trong cấu hình thực tế; không giả định mọi thành phần đều có cùng khả năng drill.

### 7.2. Làm phép đo đủ đại diện

Trước diễn tập, ghi rõ:

- Dữ liệu có quy mô bao nhiêu, tốc độ tăng và thời điểm bản backup được chọn.
- Tài nguyên nào đã dựng sẵn; tài nguyên nào chỉ tạo khi kích hoạt.
- Nhân sự đã được báo trước đến mức nào và người thao tác có quen hệ thống không.
- Mức tải, số vị trí thăm dò và các tích hợp bên ngoài được kiểm tra.
- Có tính thời gian phát hiện, ra quyết định và chuẩn bị vào kết quả hay không.
- Giả lập mất nguồn ở đâu: máy, mạng, dịch vụ hay cả đường quản trị.
- Khả năng truy cập IAM, kho bí mật, mã tự động hóa và kho bằng chứng khi nguồn lỗi.
- Điều kiện dừng, giới hạn chi phí và cách kết thúc diễn tập.

Nếu đã tải sẵn dữ liệu, mở sẵn quyền hoặc tạo sẵn toàn bộ Compute trước khi bấm giờ, các điều kiện này phải xuất hiện trong báo cáo.

Khi kiểm chứng tuyến truy cập, kiểm tra từ các mạng và resolver đại diện. Việc đổi bản ghi DNS hoặc nhận phản hồi thành công từ API chỉ xác nhận thao tác điều khiển. Thời điểm người dùng thực sự tới đích còn phụ thuộc cache, kết nối đang tồn tại và cách ứng dụng phân giải tên.

## 8. Thiết kế runbook để người trực thực thi được

### 8.1. Thông tin đầu tài liệu

Runbook cần là tài liệu thực thi, có định danh phiên bản và trạng thái kiểm chứng. Mẫu dưới đây chỉ là nội dung mẫu cho tài liệu vận hành:

```yaml
runbook_id: orders-oci-dr
version: "2.4"
owner_role: platform-operations
backup_owner_role: database-operations
service: orders
scenario: primary-unreachable
source_region: "<source-region>"
target_region: "<dr-region>"
source_compartment_ocid: "<source-compartment-ocid>"
target_compartment_ocid: "<target-compartment-ocid>"
rto_target_minutes: 45
rpo_target_seconds: 120
plan_reference: "<dr-plan-ocid-or-approved-workflow>"
automation_revision: "<commit-id>"
last_exercise_id: orders-dr-20261121-01
last_validated_at: "2026-11-21T03:37:00Z"
next_review_due: "<date-by-team-policy>"
evidence_location: "<restricted-location>"
```

Các placeholder phải được thay bằng giá trị chính xác trước khi đưa runbook vào sử dụng. Tên hiển thị giúp con người nhận biết, còn OCID và region giúp xác định đúng đích thao tác.

Ngoài thông tin trên, runbook cần có sơ đồ phụ thuộc, địa chỉ dịch vụ, cách xác thực, người có thẩm quyền quyết định và danh bạ dự phòng. Một runbook không ghi nhánh sự cố đang xử lý dễ khiến người trực dùng nhầm switchover khi nguồn đã không còn truy cập được.

### 8.2. Phân vai rõ ràng

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Người chỉ huy sự cố | Quyết định kích hoạt, thay đổi phạm vi, chấp nhận trạng thái suy giảm |
| Người thực thi hạ tầng | Chạy workflow được duyệt, xác nhận region, compartment và tài nguyên |
| Người phụ trách cơ sở dữ liệu | Xác minh dữ liệu, điều kiện chuyển vai trò và nguy cơ mất dữ liệu |
| Người phụ trách mạng và bảo mật | Kiểm tra tuyến, quyền, bí mật và cách cô lập nơi ghi cũ |
| Người phụ trách ứng dụng/nghiệp vụ | Thực hiện giao dịch kiểm chứng và xác nhận tiêu chí phục hồi |
| Người ghi nhận | Lưu timeline, quyết định, lần thử và liên kết bằng chứng |

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ, nhưng trách nhiệm vẫn phải được ghi rõ. Cần có người thay thế và đường liên lạc khi công cụ thường dùng không hoạt động.

Trong sự cố, dùng thẩm quyền đã được tổ chức giao trước để tránh phải tìm người phê duyệt từ đầu. Những quyết định ngoài phạm vi đó, như chấp nhận mất dữ liệu vượt ngưỡng, phải được đưa đúng người có thẩm quyền.

### 8.3. Trình tự phục hồi tham khảo

Bảng sau là cấu trúc runbook cho ví dụ đặt hàng. Nó cần được cụ thể hóa theo thiết kế và dịch vụ OCI thực tế trước khi vận hành.

| Bước | Thực hiện | Điều kiện để sang bước tiếp |
| --- | --- | --- |
| 1. Xác nhận sự cố | Xác định dịch vụ ảnh hưởng, phạm vi lỗi, mốc gián đoạn và độ tin cậy của bằng chứng | Có mã sự cố, người chỉ huy và kịch bản phù hợp |
| 2. Xác nhận quyền và đích | Kiểm tra danh tính thực thi, tenancy, region, compartment, plan và bản runbook | Đúng đích, đủ quyền và còn truy cập được công cụ cần thiết |
| 3. Đánh giá dữ liệu | Kiểm tra backup/replica, điểm dữ liệu dự kiến, khả năng giải mã và ngưỡng RPO | Có quyết định rõ về nguồn dữ liệu phục hồi |
| 4. Bảo đảm một nơi ghi chủ động | Thực hiện cơ chế cô lập hoặc fencing đã thiết kế; kiểm tra bằng chứng | Đủ điều kiện an toàn để đích trở thành nơi ghi |
| 5. Thực thi workflow | Chạy đúng plan hoặc nhánh khôi phục đã duyệt, lưu ID và log | Các bước bắt buộc hoàn tất, trạng thái lỗi được xử lý |
| 6. Kiểm tra nội bộ đích | Xác minh DB, cấu hình ứng dụng, kết nối, secret và tệp cần thiết | Đạt điều kiện để mở phục vụ theo từng giai đoạn |
| 7. Chuyển và kiểm chứng truy cập | Cập nhật tuyến theo thiết kế, kiểm tra từ bên ngoài và quản lý tác vụ nền | Lưu lượng đến đúng đích, không có nơi ghi ngoài kiểm soát |
| 8. Kiểm chứng nghiệp vụ | Đối soát dữ liệu, chạy giao dịch tổng hợp, theo dõi cửa sổ ổn định | Đạt các tiêu chí đã định nghĩa ở đầu runbook |
| 9. Công bố phục hồi và tiếp tục bảo vệ | Ghi mốc phục hồi, xác nhận người chịu trách nhiệm, kiểm tra cơ chế bảo vệ mới | Có bằng chứng, theo dõi tiếp và kế hoạch các bước còn lại |

Các bước trong bảng biểu diễn phụ thuộc logic. Nếu workflow tự động đã bao gồm fencing hoặc kiểm chứng, cần dẫn tới đúng bước đó và dùng bằng chứng của nó, tránh lặp một thao tác có tác dụng phụ.

### 8.4. Mỗi bước phải có cấu trúc đủ dùng

Một bước thực thi nên trả lời được:

- **Đầu vào:** tài nguyên nào, trạng thái hiện tại nào, quyền nào.
- **Hành động:** lệnh, đường dẫn trong Console hoặc workflow chính xác, kèm phiên bản.
- **Kết quả mong đợi:** trạng thái quan sát được và bằng chứng cần lưu.
- **Giới hạn chờ:** chờ bao lâu, truy vấn trạng thái ở đâu.
- **Khi lỗi:** ai xử lý, nhánh tiếp theo, có được thử lại không.
- **Điều kiện dừng:** trường hợp nào phải dừng để tránh mất dữ liệu hoặc ghi hai nơi.

Ví dụ mô tả bước kiểm chứng ứng dụng:

```text
ID: APP-VERIFY-01
Người chịu trách nhiệm: application-on-call

Đầu vào:
- Endpoint đích đã được xác định và xác thực.
- Tài khoản test có quyền tối thiểu.
- Mã giao dịch test gắn với exercise_id.
- Tác động email/thanh toán đã được cô lập trong diễn tập.

Thực hiện:
1. Đăng nhập qua đường truy cập được chỉ định.
2. Gửi một đơn tổng hợp với idempotency key đã ghi nhận.
3. Đọc lại đơn, trạng thái và tệp đính kèm.
4. Nếu yêu cầu bị timeout, tra cứu bằng cùng key trước khi quyết định gửi lại.
5. Đối chiếu dữ liệu và theo dõi ngưỡng phục vụ trong 5 phút.

Thành công:
- Giao dịch đúng một lần theo ngữ nghĩa ứng dụng.
- Đọc lại được dữ liệu liên quan.
- Đạt tải, tỷ lệ lỗi và độ trễ đã thống nhất.

Dừng:
- Không xác định được nơi ghi chủ động.
- Xuất hiện đơn trùng, thiếu dữ liệu bắt buộc hoặc truy cập nhầm môi trường.

Bằng chứng:
- Timestamp, request ID, transaction ID, kết quả đọc lại và biểu đồ cửa sổ kiểm tra.
```

Trong runbook thật, phần “thực hiện” phải dẫn tới bộ lệnh hoặc bộ kiểm thử đã kiểm chứng. Một dòng “kiểm tra ứng dụng” không đủ để người trực khác tái hiện cùng phép đo.

## 9. Xử lý lỗi, thử lại và chuyển trở lại

### 9.1. Dừng đúng lúc

Runbook cần nêu rõ các tình huống không được tự đi tiếp:

- Không xác định được dữ liệu nào có thể dùng và phạm vi mất dữ liệu.
- Quyền truy cập hoặc OCID cho thấy đang thao tác nhầm môi trường.
- Không chứng minh được điều kiện ngăn hai nơi cùng ghi theo thiết kế.
- Bước chuyển vai trò có kết quả chưa xác định sau timeout.
- Kiểm tra phát hiện dữ liệu lệch, thiếu khóa giải mã hoặc phụ thuộc bắt buộc chưa phục hồi.

Việc nguồn không trả lời không tự chứng minh nguồn đã ngừng xử lý. Chỉ đổi DNS cũng không bảo đảm các client cũ hoặc tác vụ nền đã ngừng ghi. Cơ chế fencing phải phù hợp kiến trúc và được kiểm chứng.

Khi tiến độ chậm hơn ngân sách, người chỉ huy cần biết thời gian còn lại và các lựa chọn đã định nghĩa. Không bỏ xác minh dữ liệu hoặc mở hai nơi ghi để “đạt RTO”.

### 9.2. Thử lại theo trạng thái thực tế

Sau timeout, thao tác phía dịch vụ có thể vẫn đang chạy hoặc đã thành công. Trước khi thử lại:

1. Tra cứu execution/work request hoặc trạng thái tài nguyên bằng ID đã lưu.
2. Xác định kết quả thật và các tác dụng phụ đã xảy ra.
3. Chỉ retry bước có điều kiện cho phép; dùng cơ chế chống trùng nếu công cụ hỗ trợ.
4. Lưu cả lần thử cũ, lần mới và khoảng thời gian chờ.

Không khởi chạy lặp thao tác promote, tạo tài nguyên hoặc gửi giao dịch chỉ vì không nhận được phản hồi đầu tiên. Runbook cần phân biệt rõ “thất bại”, “đang chạy” và “chưa xác định”.

### 9.3. Chuyển trở lại là một kế hoạch riêng

Sau failover, vùng DR có thể trở thành nơi tiếp nhận dữ liệu mới. Chuyển về vị trí cũ cần:

- Xác định bên nào đang giữ dữ liệu có thẩm quyền.
- Sửa và kiểm chứng hạ tầng tại nơi dự kiến chuyển về.
- Đồng bộ dữ liệu theo đúng cơ chế của dịch vụ.
- Xác minh điều kiện chuyển vai trò, ngăn ghi hai nơi và kiểm tra ứng dụng lần nữa.
- Ghi phép đo riêng cho khoảng gián đoạn khi chuyển trở lại.
- Thiết lập lại bảo vệ dữ liệu và giám sát sau chuyển đổi.

Không bật nguồn cũ rồi đổi DNS về một cách mặc định. Với bản sao phục vụ drill, thực hiện quy trình kết thúc diễn tập và dọn đúng tài nguyên được tạo; quy trình đó khác với chuyển trở lại sau failover thực.

## 10. Duy trì runbook theo thay đổi của hệ thống

### 10.1. Có phiên bản và chủ sở hữu

Runbook nên được quản lý trong hệ thống có lịch sử thay đổi. Mỗi bản dùng để thực thi cần liên kết được với:

- Người sở hữu và người thay thế.
- Cấu hình hạ tầng hoặc commit Infrastructure as Code liên quan.
- Phiên bản script, bộ kiểm thử và công cụ cần dùng.
- Plan/DR protection group nếu dùng Full Stack DR.
- Snapshot hoặc bản xuất cấu hình plan ở thời điểm diễn tập.
- Kết quả lần xác minh gần nhất, các giới hạn đã biết và ngày cần xem lại.

OCID của plan định danh tài nguyên, nhưng một mình nó chưa mô tả toàn bộ cấu hình tại thời điểm chạy. Nếu plan được sửa tại chỗ, cần lưu thêm bản chụp cấu hình hoặc cơ chế truy vết thay đổi tương đương.

Phân biệt trạng thái **đã sửa tài liệu** và **đã thực thi xác minh bản sửa**. Ngày cập nhật mới không tự làm runbook trở thành bản đã được kiểm chứng.

### 10.2. Cập nhật theo sự kiện

| Thay đổi | Nội dung cần xem lại |
| --- | --- |
| Thêm Compute, đổi image hoặc cấu hình khởi động | Thành phần được phục hồi, thời gian dựng và kiểm tra sẵn sàng |
| Thay đổi VCN, subnet, NSG hoặc kết nối liên vùng | Đường quản trị, đường ứng dụng, probe và fencing |
| Thay IAM, dynamic group hoặc compartment | Quyền người thực thi, quyền workflow và đọc bằng chứng |
| Luân chuyển secret, wallet, chứng thư hoặc khóa mã hóa | Cách truy cập ở đích và khả năng dùng dữ liệu phục hồi |
| Thay loại DB, cấu hình standby hoặc cơ chế backup | Nhánh phục hồi, RPO, bước chuyển vai trò và failback |
| Thay schema, outbox hoặc nơi lưu tệp | Phép kiểm chứng dữ liệu và tính nhất quán giữa thành phần |
| Thay DNS, endpoint hoặc tích hợp bên ngoài | Chuyển lưu lượng, bộ kiểm tra và cô lập tác động diễn tập |
| Thay nhân sự, thẩm quyền hoặc mục tiêu nghiệp vụ | Danh bạ, người quyết định, RTO/RPO và tiêu chí phục hồi |

Khi topology hoặc thành viên DR protection group thay đổi, đối chiếu lại plan và cập nhật theo quy trình được hỗ trợ; chạy lại precheck và diễn tập các nhánh bị ảnh hưởng. Không mặc định plan cũ đã bao phủ tài nguyên mới.

### 10.3. Chọn nhịp kiểm tra theo mức độ quan trọng

Một nhịp tham khảo do nhóm tự điều chỉnh:

- **Sau thay đổi ảnh hưởng DR:** xem lại runbook, quyền, cấu hình và phép kiểm tra tương ứng.
- **Hàng tháng:** xác minh danh bạ, truy cập tài liệu, quyền tại đích và điều kiện tiên quyết.
- **Hàng quý:** diễn tập nhánh ưu tiên với người thực thi khác người viết runbook.
- **Định kỳ theo rủi ro và sau thay đổi lớn:** kiểm tra quy mô dữ liệu, lỗi nguồn và chuyển trở lại.

Đây là lịch gợi ý cho vận hành, không phải yêu cầu mặc định của OCI. Cơ sở lựa chọn phải là mức quan trọng của dịch vụ, tốc độ thay đổi và nghĩa vụ của tổ chức.

Một phép thử có giá trị là giao runbook cho người trực dự phòng và quan sát chỗ họ phải hỏi tác giả. Mỗi câu hỏi cần thiết cho việc thực thi là dấu hiệu tài liệu còn thiếu đầu vào, tiêu chí hoặc ngữ cảnh.

### 10.4. Khép vòng sau diễn tập

Sau mỗi lần chạy:

1. Giữ nguyên dữ liệu đo và log gốc.
2. Lập timeline hợp nhất; đánh dấu mốc chưa chắc chắn.
3. Đối chiếu từng tiêu chí phục hồi và mục tiêu thời gian, dữ liệu.
4. Ghi các điểm chờ, thao tác ngoài tài liệu và bước phải thử lại.
5. Tạo việc khắc phục có người chịu trách nhiệm, hạn và tiêu chí xác nhận.
6. Sửa runbook và tự động hóa tương ứng.
7. Thực thi lại phạm vi cần thiết để xác nhận hiệu quả sửa đổi.

Ví dụ, “cải thiện IAM” là một việc quá mơ hồ. Một việc có thể kiểm chứng là: “tài khoản trực dự phòng chạy được precheck tại compartment DR bằng quyền đã duyệt; lưu kết quả và cập nhật mục truy cập trong runbook”.

Nếu thay đổi cơ chế phục hồi, dữ liệu hoặc phụ thuộc chính, cần đo lại đầu cuối. Một lần kiểm tra cú pháp script không chứng minh được RTO mới.

## 11. Báo cáo kết quả mà không che mất rủi ro

### 11.1. Mẫu báo cáo tối thiểu

| Trường | Giá trị ví dụ |
| --- | --- |
| Mã lần chạy | `orders-dr-20261121-01` |
| Kịch bản | Nguồn không truy cập được trong môi trường thử |
| Runbook và tự động hóa | Bản 2.4, commit được ghi trong hồ sơ |
| Phạm vi | DB, Compute, tệp đính kèm, tuyến truy cập và giao dịch tổng hợp |
| Điều kiện đầu vào | Warm standby; quy mô dữ liệu và mức tải được ghi riêng |
| RTO mục tiêu / thực tế | 45 phút / 37 phút |
| RPO mục tiêu / khoảng lùi xác minh | 120 giây / 80 giây |
| Thời gian chạy workflow | 15 phút |
| Số lần thử | 1 |
| Ngoại lệ | Thanh toán thật được thay bằng endpoint thử nghiệm |
| Hạng mục chưa kiểm tra | Phục hồi toàn bộ region thật, tải đỉnh sản xuất |
| Dọn tài nguyên và bảo vệ sau chạy | Ghi trạng thái hoàn tất hoặc việc còn mở |
| Bằng chứng | Timeline, execution ID, log đầy đủ, kết quả đối soát |
| Người xác nhận | Vai trò và thời điểm xác nhận |

Mục ngoại lệ và ngoài phạm vi giúp người đọc hiểu chính xác bằng chứng đang có. Không đổi “chưa kiểm tra” thành “đạt” chỉ vì không phát hiện lỗi.

### 11.2. Theo dõi nhiều lần chạy

Nên theo dõi:

- Tỷ lệ đạt trên tổng số lần chạy theo cùng kịch bản.
- Thời gian phục hồi đầu cuối và từng giai đoạn.
- Số lần phải thao tác ngoài runbook hoặc cần quyền bổ sung.
- Số lần chưa xác minh được RPO.
- Tuổi của bản runbook đã kiểm chứng và số thay đổi chưa kiểm tra lại.
- Chi phí diễn tập, tài nguyên còn tồn đọng và việc khắc phục quá hạn.

Không loại những lần thất bại khỏi báo cáo thời gian. Nếu đã chạy 50 phút mà chưa phục hồi, ghi “chưa phục hồi sau 50 phút”, cùng trạng thái lần chạy; không nhập thành 0 hoặc bỏ mẫu.

Chỉ tính trung vị hay phân vị khi có đủ dữ liệu và nhóm mẫu có ý nghĩa. Ba lần diễn tập với ba kịch bản khác nhau không đủ để công bố p95 đáng tin cậy. So sánh cần giữ được điều kiện tương đồng về dữ liệu, tải, tài nguyên chuẩn bị sẵn và tiêu chí kết thúc.

Khi tối ưu, đặt lợi ích đo được cạnh chi phí: chuẩn bị thêm capacity, giữ Compute sẵn hoặc tăng tần suất bảo vệ dữ liệu có thể rút ngắn một số giai đoạn nhưng làm tăng chi phí thường xuyên. Không suy ra phương án tối ưu từ một số đo duy nhất.

## 12. Thực hành phép tính và hoàn thiện runbook

### 12.1. Tính lại ví dụ bằng PowerShell

Đoạn sau chỉ tính thời lượng từ dữ liệu mẫu trong bộ nhớ, không thao tác tài nguyên OCI:

```powershell
$timeline = @{
    Outage         = [DateTimeOffset]::Parse('2026-11-21T03:00:00Z')
    ExecutionStart = [DateTimeOffset]::Parse('2026-11-21T03:09:00Z')
    ExecutionEnd   = [DateTimeOffset]::Parse('2026-11-21T03:24:00Z')
    Restored       = [DateTimeOffset]::Parse('2026-11-21T03:37:00Z')
    RecoveryPoint  = [DateTimeOffset]::Parse('2026-11-21T02:58:40Z')
}

$rtoTargetMinutes = 45
$rpoTargetSeconds = 120

if ($timeline.ExecutionStart -lt $timeline.Outage -or
    $timeline.ExecutionEnd -lt $timeline.ExecutionStart -or
    $timeline.Restored -lt $timeline.ExecutionEnd -or
    $timeline.RecoveryPoint -gt $timeline.Outage) {
    throw 'Timeline khong phu hop voi kich ban mau.'
}

$recoveryMinutes = ($timeline.Restored - $timeline.Outage).TotalMinutes
$executionMinutes = ($timeline.ExecutionEnd - $timeline.ExecutionStart).TotalMinutes
$recoveryPointGapSeconds = ($timeline.Outage - $timeline.RecoveryPoint).TotalSeconds

[pscustomobject]@{
    RecoveryActualMinutes   = $recoveryMinutes
    ExecutionMinutes        = $executionMinutes
    RtoHeadroomMinutes      = $rtoTargetMinutes - $recoveryMinutes
    RecoveryPointGapSeconds = $recoveryPointGapSeconds
    RtoTimeCheck            = $recoveryMinutes -le $rtoTargetMinutes
    RpoTimeCheck            = $recoveryPointGapSeconds -le $rpoTargetSeconds
}
```

Kết quả mong đợi lần lượt là `37`, `15`, `8`, `80`, `True` và `True`. Hai giá trị Boolean chỉ so sánh khoảng thời gian mẫu với mục tiêu; chúng không tự kiểm chứng tính đầy đủ của dữ liệu hoặc chất lượng phục vụ.

### 12.2. Thực hành trong môi trường OCI dành riêng cho học tập

1. Chọn một ứng dụng có giao dịch kiểm chứng được và xác định phạm vi dữ liệu.
2. Điền thông tin đầu runbook, mục tiêu và tiêu chí kết thúc trước khi chạy.
3. Xác minh truy cập đích, quyền tối thiểu, backup/replica, log và cách dừng diễn tập.
4. Chọn diễn tập dựng bản sao hoặc kịch bản lỗi được môi trường cho phép; ghi rõ điều không thử.
5. Ghi toàn bộ mốc, lần thử, quyết định và execution ID nếu có.
6. Chạy bộ kiểm tra nghiệp vụ, đối soát dữ liệu và theo dõi cửa sổ ổn định.
7. Tính thời gian đầu cuối, thời gian điều phối và khoảng lùi điểm phục hồi.
8. Nhờ người khác dùng runbook đã sửa để tái hiện quy trình.
9. Kết thúc diễn tập, kiểm tra cơ chế bảo vệ dữ liệu và đối chiếu tài nguyên còn tính phí.

Tài nguyên diễn tập nên có định danh rõ, giới hạn thời gian và người dọn dẹp. Theo dõi Compute, bản sao dữ liệu, lưu trữ, log và lưu lượng phát sinh; không coi việc tắt ứng dụng là đã dọn hết chi phí.

## 13. Những lỗi làm phép đo và runbook mất giá trị

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Bấm giờ từ khi chạy plan | Bỏ thời gian phát hiện và quyết định | Ghi timeline từ mốc gián đoạn đã định nghĩa |
| Dừng giờ khi DB mở được | Bỏ kiểm tra ứng dụng và tuyến người dùng | Dùng tiêu chí đầu cuối, có tải và cửa sổ ổn định |
| Cộng tất cả bước song song | Tính sai thời gian đường găng | Dùng thời điểm bắt đầu/kết thúc nhóm và bước |
| Chỉ nhìn bản ghi mới nhất | Bỏ sót dữ liệu thiếu trước đó | Đối soát ID, watermark và quan hệ giữa kho dữ liệu |
| Chỉ lưu log ở nguồn | Mất bằng chứng khi nguồn lỗi | Bố trí quan sát và lưu trữ ngoài phạm vi lỗi |
| Dùng quyền quản trị trong mọi lần thử | Che mất lỗi quyền của người trực thực tế | Kiểm tra bằng đúng danh tính vận hành đã thiết kế |
| Retry sau timeout mà không đọc trạng thái | Có thể tạo thao tác trùng hoặc chuyển vai trò sai | Tra cứu ID và trạng thái trước khi retry |
| Sửa tài liệu nhưng không xác minh | Runbook mới chưa có bằng chứng dùng được | Gắn trạng thái kiểm chứng với từng phiên bản |
| Chỉ diễn tập có nguồn khỏe | Chưa kiểm tra nhánh nguồn không truy cập được | Bổ sung kịch bản có phạm vi và điều kiện dừng rõ |
| Không ghi lần thất bại | Báo cáo thời gian quá lạc quan | Giữ mọi lần chạy, trạng thái và thời gian quan sát |
| Không dọn bản sao diễn tập | Phát sinh chi phí và tài nguyên không có chủ | Có bước kết thúc, kiểm kê và xác nhận người chịu trách nhiệm |

Một runbook sẵn sàng cần có phiên bản cụ thể, đầu vào đúng hệ thống, người thực thi và người quyết định rõ ràng, điều kiện an toàn, cách xác minh kết quả cùng bằng chứng từ lần chạy đại diện. Thước đo cuối cùng là đội trực có phục hồi được chức năng đã cam kết, trong giới hạn thời gian và dữ liệu đã chấp thuận, bằng quy trình có thể thực hiện lại hay không.

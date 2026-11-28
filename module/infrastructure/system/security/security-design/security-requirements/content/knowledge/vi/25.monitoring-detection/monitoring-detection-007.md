# Alert theo configuration drift

## 1. Configuration drift là tín hiệu cần được đặt trong bối cảnh bảo mật

Configuration drift là sự lệch giữa cấu hình quan sát được và trạng thái hoặc baseline tham chiếu theo quy tắc so sánh đã xác định. Drift có thể phát sinh từ thao tác thủ công, công cụ khác, rollout chưa hội tụ, thay đổi do dịch vụ quản lý hoặc hành vi ngoài quy trình.

Ví dụ, một kho dữ liệu đang được yêu cầu không cho đọc công khai, nhưng cấu hình thực tế được đổi sang cho phép. Dịch vụ vẫn hoạt động bình thường nên metric về uptime hoặc latency có thể không báo vấn đề.

Một yêu cầu còn mơ hồ:

> Cảnh báo khi cấu hình thay đổi.

Một cách đặc tả có thể kiểm chứng hơn:

> Với các thuộc tính bảo mật thuộc danh mục, hệ thống phải so sánh quan sát đủ mới với baseline được phê duyệt áp dụng cho đúng tài nguyên. Khi có sai lệch không nằm trong biến thiên hoặc ngoại lệ hợp lệ, phải tạo cảnh báo đúng mức ưu tiên, có bằng chứng, owner và giới hạn thời gian.

NIST SP 800-128 đặt quản lý và theo dõi cấu hình trong mục tiêu duy trì bảo mật và giảm rủi ro của hệ thống. Xem [NIST SP 800-128 — Guide for Security-Focused Configuration Management](https://csrc.nist.gov/pubs/sp/800/128/upd1/final).

Trong module yêu cầu bảo mật, chuỗi cần thiết là:

> Rủi ro → baseline và policy → phạm vi thuộc tính → nguồn quan sát → logic đánh giá → cảnh báo → triage hoặc khắc phục → kiểm chứng.

Một alert drift không tự chứng minh đã có xâm nhập. Nó cũng không tự cấp quyền ghi lại cấu hình hoặc cập nhật baseline.

## 2. Phân biệt các trạng thái tham chiếu

### 2.1. Không có một “nguồn sự thật” dùng thay cho mọi mục đích

| Thành phần | Vai trò | Giới hạn |
|---|---|---|
| Policy bảo mật | Xác định điều kiện hoặc giới hạn phải giữ | Có thể bao phủ ít thuộc tính hơn toàn cấu hình |
| Baseline được phê duyệt | Trạng thái tham chiếu cho tài nguyên và thời điểm cụ thể | Cần quản lý phiên bản, phạm vi và căn cứ chấp nhận |
| Cấu hình mong muốn trong mã | Mô tả trạng thái công cụ triển khai cần hướng tới | Có thể chưa được phê duyệt hoặc chưa được áp dụng |
| State hoặc inventory của công cụ | Ghi nhận tài nguyên và thuộc tính mà công cụ biết | Có thể cũ, chưa đủ hoặc đã được cập nhật theo trạng thái không được phép |
| Cấu hình quan sát qua API | Snapshot tại nguồn và mốc thời gian xác định | Có thể trễ, thiếu trường hoặc chưa phản ánh hành vi runtime |
| Hành vi hiệu lực | Quyền truy cập hoặc tác động thực tế sau các lớp cấu hình | Cần nguồn hoặc phép kiểm tra phù hợp nếu mục tiêu yêu cầu |

Cần chỉ ra phép so sánh đang dùng những thành phần nào. “Không có diff trong state” không tự chứng minh tài nguyên tuân thủ policy bảo mật.

### 2.2. Drift và vi phạm policy là hai câu hỏi khác nhau

Một cấu hình có thể khác baseline nhưng vẫn đáp ứng policy. Ví dụ, thay đổi số replica trong khoảng được phép có thể là biến thiên vận hành đã được chấp nhận.

Ngược lại, baseline hoặc mã triển khai có thể đã bị cập nhật sang một trạng thái không an toàn. Cấu hình thực tế khớp baseline đó vẫn có thể vi phạm policy.

Vì vậy, đặc tả nên giữ được hai phép đánh giá khi cần:

```text
So sánh với baseline:
    actual có lệch trạng thái tham chiếu được áp dụng không?

Đánh giá policy:
    actual và baseline có thỏa các điều kiện bảo mật bắt buộc không?
```

Nếu baseline có ngoại lệ hợp lệ, phạm vi và thời hạn của ngoại lệ phải được quản lý riêng. Không tự mở rộng một ngoại lệ cho mọi tài nguyên tương tự.

### 2.3. Terraform state là một ví dụ cần diễn giải đúng

Tài liệu HashiCorp mô tả refresh-only để xem hoặc ghi nhận chênh lệch giữa state và hạ tầng thực tế; thao tác này không tự thay hạ tầng về cấu hình mong muốn. Xem [HashiCorp — Manage resource drift](https://developer.hashicorp.com/terraform/tutorials/state/resource-drift).

Một suy luận cho yêu cầu bảo mật là việc cập nhật state theo actual không tự phê duyệt thay đổi đó. Không dùng sự biến mất của một diff trong công cụ như bằng chứng duy nhất rằng rủi ro đã được xử lý.

## 3. Xác định rủi ro và thuộc tính cần theo dõi

### 3.1. Ưu tiên các thay đổi ảnh hưởng kiểm soát

| Rủi ro minh họa | Thuộc tính hoặc trạng thái cần cân nhắc |
|---|---|
| R1: mở rộng tiếp cận dữ liệu | Public access, phạm vi principal, nhóm mạng hoặc điều kiện chia sẻ |
| R2: giảm bảo vệ dữ liệu | Chính sách mã hóa, cấu hình TLS hoặc quyền sử dụng khóa |
| R3: mất khả năng quan sát | Tắt audit, đổi đích log, giảm mức thu thập hoặc bỏ sensor |
| R4: nâng quyền | Role binding, policy, service identity và quyền quản trị |
| R5: hợp thức hóa sai lệch | Thay baseline, đổi selector hoặc thêm ngoại lệ ngoài quyền |
| R6: điểm mù quan sát | Không đọc được cấu hình, inventory thiếu hoặc nguồn ngừng cập nhật |
| R7: alert hoặc diff làm lộ dữ liệu | Secret, thông tin kết nối hoặc payload cấu hình bị gửi vào kênh rộng |
| R8: khắc phục gây tác động ngoài phạm vi | Tự apply hoặc rollback khi trạng thái đã đổi và chưa đánh giá hệ quả |

Bảng chỉ là điểm khởi đầu. Dự án cần gắn mỗi nhóm với tài sản, loại dữ liệu, tác động và chủ sở hữu.

### 3.2. Thuộc tính được theo dõi phải có ngữ nghĩa

Không phải mọi thay đổi metadata đều cần page. Timestamp do hệ thống tự cập nhật có thể không phục vụ mục tiêu bảo mật, còn một nhãn quyết định phân loại dữ liệu hoặc phạm vi policy lại có thể rất quan trọng.

Cần danh sách thuộc tính, kiểu, quy tắc chuẩn hóa và mức rủi ro. Không dùng một quy tắc bỏ qua toàn bộ tags, annotations hoặc metadata nếu trong đó có trường ảnh hưởng kiểm soát.

Nếu yêu cầu bảo vệ quyền truy cập thực tế, một cờ đơn lẻ có thể chưa đủ. Cần xem các lớp policy, quan hệ tài nguyên và nguồn đánh giá hiệu lực tương ứng với kiến trúc.

### 3.3. Phạm vi tài nguyên không được dễ dàng né tránh

Một selector dựa vào tag do chính người thay cấu hình có thể sửa tạo nguy cơ tài nguyên biến mất khỏi giám sát.

Cần inventory hoặc cơ chế đối soát phát hiện tài nguyên mới, bị chuyển phạm vi, đổi owner, xóa hoặc tạo lại. Danh tính tài nguyên nên bao gồm ngữ cảnh và thế hệ khi cần để tránh nhầm một tài nguyên mới với bản cũ dùng lại tên.

Nếu một tài nguyên không có baseline phù hợp, trạng thái nên là chưa được đánh giá hoặc cần review theo policy. Không tự coi là compliant chỉ vì không tìm thấy bản tham chiếu.

## 4. Baseline, phiên bản và ngoại lệ

### 4.1. Hồ sơ baseline cần gì?

Một baseline có thể cần:

- ID và phiên bản bất biến hoặc cách truy xuất lịch sử.
- Loại tài nguyên, môi trường và phạm vi được áp dụng.
- Thuộc tính mong muốn, khoảng cho phép và quy tắc chuẩn hóa.
- Thời điểm có hiệu lực, owner và reference phê duyệt.
- Liên kết với policy bắt buộc và phiên bản công cụ đánh giá.
- Ngoại lệ được phép, điều kiện hết hạn và người có thẩm quyền.

Quyền sửa baseline cần tách phù hợp với quyền thay tài nguyên và quyền thay rule. Nếu cùng một thao tác tự cập nhật actual rồi lấy actual làm baseline mới, hệ thống có thể che chính sai lệch cần phát hiện.

Một chữ ký hoặc lịch sử Git hỗ trợ kiểm tra nguồn và thay đổi trong phạm vi thiết kế. Nó không tự chứng minh nội dung baseline là đúng về bảo mật.

### 4.2. Quy tắc lựa chọn baseline phải xác định được

Một tài nguyên có thể chịu baseline cấp tổ chức, dịch vụ và môi trường. Cần cách áp dụng và xử lý xung đột rõ, không phụ thuộc thứ tự đọc file ngẫu nhiên hoặc baseline được client tự chọn.

Với đánh giá trạng thái hiện tại, cần biết baseline nào có hiệu lực tại thời điểm snapshot được đánh giá. Với điều tra thay đổi lịch sử, có thể cần baseline áp dụng tại thời điểm thay đổi.

Hai mục tiêu đó khác nhau. Event cần ghi phiên bản và thời gian dùng cho kết luận, không ghép một snapshot cũ với baseline mới rồi diễn giải như cùng một thời điểm.

### 4.3. Ngoại lệ và cửa sổ triển khai

Một thay đổi được phê duyệt có thể cần thời gian hội tụ. Đặc tả cần giới hạn tài nguyên, thuộc tính, giá trị hoặc khoảng được phép, thời gian và điều kiện kết thúc.

Không dùng “đang maintenance” để tắt mọi kiểm tra bảo mật. Với thuộc tính rủi ro cao, policy có thể yêu cầu cảnh báo ngay hoặc một ngoại lệ riêng, thay vì tự động hưởng cửa sổ chung.

Khi ngoại lệ hết hạn, phải đánh giá lại cấu hình. Nếu dữ liệu không đủ mới, hệ thống cần thể hiện khoảng không xác minh được và yêu cầu xử lý; không tự tuyên bố vẫn tuân thủ.

## 5. Nguồn quan sát và cách phát hiện

### 5.1. Kết hợp thay đổi được ghi nhận với snapshot

| Cơ chế | Điểm mạnh | Điểm cần kiểm chứng |
|---|---|---|
| Event thay đổi | Có thể phản ứng sớm và giữ dấu vết ai gọi thao tác | Event có thể chỉ mô tả request, bị trễ hoặc không đầy đủ |
| Quét định kỳ | Đối soát trạng thái hiện tại, phát hiện thay đổi không có event | Có khoảng mù giữa các lần quét |
| So sánh qua IaC hoặc controller | Có ngữ cảnh trạng thái mong muốn | Phạm vi thuộc tính và tài nguyên phụ thuộc công cụ |
| Probe hoặc đánh giá hiệu lực | Kiểm tra hành vi hoặc quyền thực tế theo mục tiêu | Cần an toàn, quyền, giới hạn và cách diễn giải kết quả |

AWS Config là một ví dụ có trigger theo thay đổi, theo chu kỳ hoặc kết hợp, với scope xác định tài nguyên được đánh giá. Xem [AWS Config — Components of a Rule](https://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_components.html).

Việc một sản phẩm hỗ trợ cơ chế này không tự bảo đảm độ trễ hoặc bao phủ cho ứng dụng cụ thể. Cần xác nhận loại tài nguyên, trường, vùng và cấu hình nguồn thực tế.

### 5.2. Audit thay đổi và actual không thay thế nhau

Một request sửa cấu hình được ghi nhận thành công có thể cần được đối chiếu lại với actual sau đó. Việc một controller gửi desired state cũng chưa chứng minh runtime đã dùng trạng thái đó.

Audit giúp tìm principal, operation, thời gian và reference. Danh tính trong audit có thể là workload hoặc tài khoản tự động, chưa chắc xác định được một cá nhân nếu không có liên kết ủy quyền phù hợp.

Kubernetes phân biệt các mức audit như Metadata, Request và RequestResponse, trong đó mức chi tiết khác nhau về body. Xem [Kubernetes — Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/). Khi chọn nguồn, cần đủ metadata cho điều tra mà không mặc định sao chép toàn bộ nội dung có thể chứa secret.

### 5.3. Không đọc được khác với không có drift

Timeout, thiếu quyền, resource type chưa hỗ trợ, field bị ẩn và snapshot quá cũ cần có trạng thái phù hợp.

Có thể dùng các trạng thái nội bộ như `MATCH`, `DRIFT`, `POLICY_VIOLATION`, `UNKNOWN`, `STALE` hoặc `PENDING_TRANSITION`. Đây là lựa chọn minh họa; tên trạng thái của từng nhà cung cấp có thể khác.

Không tìm thấy resource cũng cần được diễn giải: đã xóa hợp lệ, bị xóa ngoài quy trình, sai account, sai vùng hay collector thiếu quyền. Một kết quả rỗng không tự là bằng chứng tuân thủ.

## 6. Chuẩn hóa, so sánh và ví dụ baseline

### 6.1. So sánh theo ngữ nghĩa

Một diff văn bản có thể bị nhiễu bởi thứ tự field, format hoặc giá trị mặc định. Cần chuẩn hóa theo loại dữ liệu và ngữ nghĩa đã định.

Ví dụ:

- Có thể sắp xếp một tập không có thứ tự khi contract thật sự coi nó là tập.
- Không tự sắp xếp danh sách rule firewall nếu thứ tự ảnh hưởng quyết định.
- Giá trị thiếu, null, mặc định và giá trị chưa quan sát được phải được phân biệt.
- Phiên bản hoặc mức giao thức cần so sánh theo kiểu đã xác định, không theo chuỗi tùy ý.
- Trường do provider tính toán chỉ được bỏ qua khi đã đánh giá tác động.

Chuẩn hóa không được làm mất thông tin bảo mật để giảm số diff. Cần có version và kiểm thử riêng cho logic so sánh.

### 6.2. Baseline giả lập

```yaml
baselineId: restricted-export-store
baselineVersion: 3
resourceClass: export-storage
environment: production
effectivePolicyRef: export-data-policy-example-4
properties:
  permitPublicRead: false
  auditEnabled: true
  requireEncryptedStorage: true
allowedVariance:
  capacityClass:
    - standard
    - expanded
```

Đây là mô hình chuẩn hóa phục vụ bài học, không phải tên property dùng trực tiếp cho một dịch vụ cloud cụ thể.

Giả sử snapshot đủ mới cho thấy `permitPublicRead: true`. Detector cần xác định baseline đúng phạm vi, khả năng quan sát thuộc tính và ngoại lệ còn hiệu lực, rồi tạo kết quả cho property đó.

Nếu `capacityClass` đổi từ standard sang expanded trong tập được cho phép, không nhất thiết có security drift theo contract này. Nhưng thay đổi `auditEnabled` không được bỏ qua cùng nhóm chỉ vì nó nằm trong một rollout.

### 6.3. Luồng đánh giá minh họa

```text
Xác định tài nguyên và thế hệ
    → lấy baseline và policy đúng phạm vi, phiên bản, thời điểm
    → xác minh snapshot đủ mới và đủ trường
    → chuẩn hóa theo schema được kiểm soát
    → so sánh thuộc tính và kiểm tra policy
    → đối chiếu biến thiên, phê duyệt và ngoại lệ
    → ghi kết quả, bằng chứng và mức chắc chắn
    → cập nhật trạng thái finding và alert theo policy
```

Nếu baseline đổi trong lúc đánh giá, cần giữ quan hệ phiên bản hoặc chạy lại theo contract. Không trộn kết quả giữa hai baseline mà không thể hiện điều đó.

## 7. Thiết kế finding và alert để operator hiểu được sai lệch

### 7.1. Bằng chứng tối thiểu

Một finding nên xác định:

- Tài nguyên, thế hệ, môi trường và phạm vi tổ chức.
- Baseline, policy và rule version dùng để đánh giá.
- Thuộc tính lệch, điều kiện kỳ vọng và quan sát được trong mức dữ liệu được phép.
- Nguồn, snapshot version và thời gian quan sát.
- Ngoại lệ hoặc phê duyệt đã được đối chiếu, cùng trạng thái kết quả.
- Mức tác động, độ chắc chắn và những phần chưa biết.
- Owner, runbook và reference tới bằng chứng hạn chế quyền.

Không tự gán người gây thay đổi nếu nguồn chỉ có snapshot. Có thể biết actual đã lệch nhưng chưa biết actor; đó là kết quả cần diễn giải đúng.

### 7.2. Ví dụ finding giả lập

```json
{
  "schemaVersion": 1,
  "findingId": "finding-example-207",
  "observationId": "observation-example-31",
  "ruleId": "EXPORT_STORE_PUBLIC_READ",
  "ruleVersion": 2,
  "resourceRef": "resource-example-17",
  "resourceGeneration": "generation-example-2",
  "environment": "production",
  "tenantRef": "tenant-example-a",
  "baselineId": "restricted-export-store",
  "baselineVersion": 3,
  "policyRef": "export-data-policy-example-4",
  "observedAt": "2026-11-27T08:00:00Z",
  "observedConfigVersion": "config-example-9",
  "fieldRef": "/permitPublicRead",
  "expected": false,
  "observed": true,
  "evaluation": "DRIFT",
  "exceptionStatus": "NO_VALID_EXCEPTION",
  "severity": "HIGH",
  "changeActorRef": null,
  "attributionStatus": "UNKNOWN",
  "ownerRef": "team-example-data-platform",
  "runbookRef": "DRIFT-EXPORT-01"
}
```

Các giá trị đều giả lập. Hai giá trị boolean được coi là được phép hiển thị trong ví dụ; không áp dụng cách ghi before/after này cho secret hoặc dữ liệu nhạy cảm.

Finding mô tả một sai lệch cấu hình. Nó chưa khẳng định ai đã thực hiện hoặc có dữ liệu đã bị tải trái phép. Những kết luận đó cần bằng chứng riêng.

### 7.3. Vòng đời và cách đóng

Có thể có các trạng thái như phát hiện mới, đang triage, lệch được chấp nhận có hạn, đang khắc phục, đã xác minh khôi phục hoặc chưa đủ dữ liệu.

Acknowledgement hoặc mute chỉ thay đổi quá trình thông báo, không làm actual trở nên đúng. Một operator đã nhận việc cũng không có nghĩa finding đã được xử lý.

Chỉ đóng theo “đã khôi phục” khi có quan sát đủ mới xác minh đúng trạng thái theo baseline và policy áp dụng. Nếu đóng vì baseline được thay hợp lệ hoặc quyết định chấp nhận rủi ro, cần lý do và reference tương ứng, không ghi như actual đã tự quay về giá trị cũ.

### 7.4. Dedupe, flapping và cảnh báo mới

Khóa liên kết có thể dựa trên tài nguyên, thế hệ, rule, baseline version và loại sai lệch. Mỗi lần quan sát vẫn cần ID hoặc mốc riêng để giữ bằng chứng tiến triển.

Gom nhiều diff vào một incident có thể giảm nhiễu nhưng không được che một thuộc tính bảo mật mới bị lệch. Cần cập nhật phạm vi, thời điểm và mức ưu tiên theo rule.

Debounce hoặc yêu cầu nhiều lần đọc phù hợp cho một số thuộc tính có thay đổi thoáng qua. Với thuộc tính rủi ro cao, chính sách có thể yêu cầu phản ứng ngay từ quan sát đáng tin; không áp điều kiện hai lần quét cho mọi loại drift.

Một sai lệch đã được tự khôi phục vẫn có thể cần điều tra khoảng thời gian và nguyên nhân. Không xóa dấu vết chỉ vì trạng thái hiện tại đã khớp.

## 8. Độ trễ, tính mới và giới hạn của phép quan sát

### 8.1. Đo theo nguồn và điểm nhận cảnh báo

Cần tách các mốc:

```text
Thay đổi được ghi nhận tại nguồn
    → tín hiệu thay đổi được thu thập
    → actual đủ mới được lấy
    → đánh giá hoàn tất
    → finding hoặc alert được tạo
    → kênh trực xác nhận nhận
```

Nếu chỉ đo từ lúc detector có đủ snapshot, kết quả bỏ qua chậm giao event và chậm lấy cấu hình. Yêu cầu toàn luồng phải chọn mốc bắt đầu có bằng chứng.

Khi không biết thời điểm thay đổi thật, có thể chỉ biết lần cuối còn khớp và lần đầu quan sát lệch. Báo cáo cần giữ khoảng không chắc chắn đó, thay vì đặt thời điểm phát sinh drift bằng timestamp chạy scan.

### 8.2. Quét định kỳ có khoảng mù

Ví dụ dự án đặt:

- Khoảng cách tối đa giữa hai lần bắt đầu chu kỳ quét là 5 phút, gồm jitter được chấp nhận.
- Lấy cấu hình của từng tài nguyên trong phạm vi hoàn tất trong tối đa 2 phút của chu kỳ.
- Đánh giá và chuyển cảnh báo mất tối đa 1 phút sau khi có dữ liệu hợp lệ.

Trong điều kiện đó, một drift tồn tại liên tục và quan sát được có thể có giới hạn tới cảnh báo là 8 phút nếu xảy ra ngay sau lần đọc trước. Đây là giới hạn của ví dụ và cần kiểm thử với inventory, quota và tải cụ thể.

Một thay đổi xảy ra rồi bị đảo lại hoàn toàn giữa hai lần đọc có thể không xuất hiện trong snapshot. Muốn bao phủ tình huống đó cần nguồn thay đổi hoặc bằng chứng khác phù hợp; không thể hứa bằng riêng polling.

### 8.3. Event không tự loại bỏ độ trễ actual

Nguồn có thể giao event trước khi API đọc phản ánh trạng thái mới. Ngược lại, actual có thể đổi mà event chưa tới.

Cần thời hạn chờ hội tụ, số lần đọc lại và cách kết luận. Một event yêu cầu đổi cấu hình chưa thành công không nên bị diễn giải như actual chắc chắn đã lệch.

Nếu các tài nguyên được đọc ở các thời điểm khác nhau, không gọi kết quả toàn inventory là một snapshot nguyên tử khi hệ thống không bảo đảm điều đó.

### 8.4. Dữ liệu cũ không được dùng để tự đóng cảnh báo

Mỗi quan sát cần thông tin tính mới theo contract nguồn. Timestamp của collector nhận response không tự chứng minh mọi dữ liệu bên trong đều vừa được cập nhật.

Nếu nguồn không còn đọc được, giữ lịch sử quan sát cuối cùng nhưng đánh dấu trạng thái hiện tại không xác định hoặc stale. Không dùng “không có diff mới” như bằng chứng đã khôi phục.

Ngoại lệ hết hạn cũng cần dữ liệu đủ mới để đánh giá lại. Nếu chưa có, tạo việc cần xử lý về hết ngoại lệ và khả năng xác minh, không tự khẳng định trạng thái hiện tại tốt hoặc xấu hơn bằng chứng có sẵn.

## 9. Triage và khắc phục không làm mất kiểm soát

### 9.1. Các câu hỏi operator cần trả lời

Trước khi thay tài nguyên, cần xác minh:

- Baseline và policy có đúng tài nguyên, thời điểm và môi trường không?
- Snapshot có đủ mới, đủ trường và đúng nguồn không?
- Diff có ngữ nghĩa bảo mật hay chỉ là khác biểu diễn?
- Có thay đổi hoặc ngoại lệ hợp lệ còn hiệu lực không?
- Có dấu hiệu thay baseline, scope hoặc nguồn thu thập để che drift không?
- Chủ thể gây thay đổi được biết ở mức nào?
- Khắc phục có ảnh hưởng dữ liệu, kết nối hoặc tác vụ đang chạy không?

Runbook cần có điều kiện dừng và escalation khi không đủ bằng chứng. Không hướng operator apply một kế hoạch rộng chỉ để làm mất cảnh báo.

### 9.2. Thay baseline và khôi phục actual là các quyết định khác nhau

Nếu actual ngoài quyền, có thể cần khôi phục bằng thay đổi được phê duyệt. Nếu baseline cũ không còn phù hợp, có thể cần thay baseline theo quy trình quản trị. Cả hai trường hợp cần đánh giá policy và tác động.

Không tự chấp nhận actual mới vì công cụ đề xuất cập nhật state. Cũng không mặc định mọi drift đều phải rollback ngay; một thay đổi khẩn cấp hợp lệ có thể cần nhánh riêng trong runbook.

Lịch sử finding phải giữ lý do, người quyết định và reference. Việc đổi baseline không được viết lại bằng chứng cũ thành “chưa từng có sai lệch”.

### 9.3. Tự động khắc phục cần contract riêng

Auto-remediation cần quyền tối thiểu, danh sách tài nguyên và thuộc tính được phép, điều kiện trước thao tác, giới hạn tốc độ và cách dừng vòng lặp.

Trước khi ghi, cần xác minh actual hoặc version vẫn phù hợp với kế hoạch. Nếu tài nguyên đã đổi tiếp, phải dừng hoặc đánh giá lại theo policy, tránh ghi đè một thay đổi hợp lệ mới.

Có thể dùng cơ chế kiểm tra version hoặc điều kiện tương đương nếu nền tảng hỗ trợ. Thao tác gửi thành công chưa đủ; cần quan sát sau khắc phục để xác minh hiệu lực.

Hành động xóa hoặc tạo lại tài nguyên có tác động khác với sửa một thuộc tính. Alert drift không tự là ủy quyền thực hiện những hành động đó.

## 10. Bảo vệ detector và dữ liệu cấu hình

### 10.1. Không biến diff thành nơi chứa secret

Snapshot hoặc plan có thể chứa mật khẩu, token, dữ liệu kết nối và giá trị cấu hình nhạy cảm. Không gửi toàn bộ diff tới pager, chat hoặc ticket dùng chung.

Với field nhạy cảm, có thể chỉ ghi đã thay đổi, loại kiểm soát, version hoặc reference được phép. Không coi hash của một secret có miền nhỏ là dữ liệu mặc nhiên an toàn hoặc ẩn danh.

Cần làm sạch trước khi ghi log hoặc chuyển sang collector. Chỉ che ở giao diện không xử lý bản thô đã vào buffer, index hoặc bên cung cấp dịch vụ.

Tên tài nguyên, tag và annotation do người dùng điều khiển cũng cần giới hạn và encode, tránh chèn dòng giả hoặc markup vào công cụ điều tra.

### 10.2. Giới hạn quyền của nguồn và công cụ

Collector chỉ nên có quyền đọc cấu hình cần thiết. Nếu có thành phần khắc phục, nên phân biệt quyền đánh giá với quyền thay đổi theo thiết kế.

Baseline store, rule engine, exception store và selector cũng là tài sản cần bảo vệ. Thay những phần này có thể làm mất khả năng phát hiện mà actual vẫn chưa được sửa.

Quyền xem chi tiết cần giới hạn theo tổ chức, tài sản và trách nhiệm. Reference hoặc finding ID không thay thế authorization.

### 10.3. Giám sát khả năng quan sát drift

Cần theo dõi lần quét cuối, số tài nguyên dự kiến và đã đọc, lỗi quyền, quota, lỗi schema, backlog và baseline không tải được.

Một collector sống không chứng minh nó đọc đủ account, vùng hoặc namespace. Inventory và việc tài nguyên ra khỏi phạm vi cần được đối soát.

Đường thông báo sức khỏe nên được đánh giá để tránh mất cùng điểm lỗi đang được giám sát. Nếu mọi thông báo đều phụ thuộc chính nguồn đã tắt, việc mất nguồn có thể bị che.

Khi năng lực quan sát suy giảm, dashboard phải thể hiện phạm vi đó. Không giữ nhãn “compliant” từ lần đọc cũ vô thời hạn.

## 11. Ví dụ yêu cầu đo được và ma trận nghiệm thu

### 11.1. Bối cảnh và các ngưỡng minh họa

Giả sử dịch vụ giám sát các thuộc tính bảo mật của kho export trong production. Dự án chọn:

- Mỗi tài nguyên bắt buộc có owner, baseline và policy đúng phiên bản.
- Event thay đổi được dùng cùng quét định kỳ theo các điều kiện nguồn đã được kiểm tra.
- Với thay đổi có event và actual được nguồn cung cấp trong điều kiện đã định, tạo và chuyển cảnh báo rủi ro cao trong 180 giây từ mốc thay đổi được xác minh.
- Đường quét định kỳ có chu kỳ, thời gian đọc và xử lý như mục 8.2, giới hạn tới cảnh báo là 8 phút cho drift tồn tại liên tục, quan sát được.
- Snapshot cũ quá 10 phút không được dùng làm bằng chứng tuân thủ hiện tại.
- Khi mất khả năng xác minh hoặc quá giới hạn tính mới, tạo tín hiệu sức khỏe trong tối đa 2 phút từ lúc điều kiện đó được xác định.
- Ngoại lệ của ví dụ có thời hạn tối đa 24 giờ, chỉ được áp dụng cho phần được phép; bắt đầu đánh giá lại trong 5 phút từ khi hết hạn.
- Metadata finding giữ 90 ngày; snapshot hoặc bằng chứng bổ sung có schema, quyền và retention riêng.
- Không tự động khắc phục ngoài những hành động đã có policy và quyền cụ thể.

**Các con số là giả định minh họa, không phải thời hạn mặc định từ NIST, Terraform, AWS Config hoặc Kubernetes.** Nếu nguồn hoặc quota không đáp ứng, phải điều chỉnh kiến trúc hoặc contract thay vì giữ một cam kết không thể kiểm chứng.

Mục tiêu 180 giây không áp dụng cho mọi loại tài nguyên chỉ vì dùng cơ chế event. Giới hạn polling cũng không bao phủ thay đổi ngắn hoàn toàn giữa hai lần quan sát.

### 11.2. Ma trận rủi ro, yêu cầu và bằng chứng

| Mã | Rủi ro | Yêu cầu cụ thể | Bằng chứng nghiệm thu |
|---|---|---|---|
| CD-01 | R1–R6 | Inventory xác định đúng tài nguyên, thế hệ, scope, owner và baseline | Tạo mới, đổi tag phạm vi, chuyển owner và tạo lại cùng tên không làm tài nguyên bị bỏ qua âm thầm |
| CD-02 | R5 | Baseline có phiên bản, phê duyệt và cách áp dụng; thay đổi được bảo vệ | Người chỉ được thay actual không tự phê duyệt baseline; lịch sử quyết định và hiệu lực có thể tra cứu |
| CD-03 | R1, R2, R4 | So sánh drift và đánh giá policy theo mục tiêu đã chọn | Actual khớp một baseline không đạt policy vẫn bị phát hiện theo rule policy |
| CD-04 | R1–R4 | Chuẩn hóa đúng ngữ nghĩa, chỉ bỏ qua thuộc tính được duyệt | Đổi thứ tự tập tương đương không tạo nhiễu; đổi thứ tự rule có ý nghĩa không bị chuẩn hóa mất |
| CD-05 | R6 | Event và polling có phạm vi, độ trễ và đối soát riêng | Bỏ một event có kiểm soát nhưng giữ drift liên tục: đường quét phát hiện trong giới hạn đã định |
| CD-06 | R1–R4 | Drift rủi ro cao từ nguồn đủ điều kiện được cảnh báo trong 180 giây | Đo từ mốc thay đổi được xác minh đến receipt kênh, gồm thu thập và lấy actual |
| CD-07 | R6 | Không đọc được hoặc snapshot quá 10 phút không được kết luận MATCH | Mất quyền đọc, timeout và trường thiếu tạo UNKNOWN hoặc STALE; finding cũ không tự được đóng |
| CD-08 | R5 | Ngoại lệ đúng tài nguyên, thuộc tính, giá trị và thời hạn; hết hạn được đánh giá lại | Ngoại lệ sai scope không được áp dụng; quá hạn 24 giờ không tiếp tục mute theo cờ cũ |
| CD-09 | R1–R4 | Dedupe và vòng đời finding giữ được thay đổi quan trọng | Event trùng không tạo bão; thuộc tính mới lệch hoặc tái phát sau đóng vẫn được xử lý theo policy |
| CD-10 | R7 | Diff và alert không chứa secret; quyền xem bằng chứng theo phạm vi | Secret giả lập không xuất hiện raw ở các đích ngoài quyền; tenant khác không mở được finding |
| CD-11 | R8 | Khắc phục kiểm tra trạng thái trước và xác minh sau; có giới hạn quyền | Actual đổi version trước remediation làm thao tác dừng hoặc đánh giá lại; API thành công nhưng actual chưa khớp chưa đóng finding |
| CD-12 | R5, R6 | Rule, baseline, exception và sức khỏe nguồn có audit và chủ sở hữu | Tắt source hoặc đổi selector có dấu vết và tín hiệu; dashboard không giữ trạng thái tốt từ dữ liệu cũ ngoài hạn |

Các phép kiểm tra cần quan sát cả actual, baseline, kết quả đánh giá và kênh nhận. Một dòng log “đã phát hiện” chưa chứng minh alert tới đúng người hoặc phép so sánh đúng phạm vi.

### 11.3. Tiêu chí chấp nhận cho drift bảo mật

```gherkin
Given tai nguyen P thuoc baseline B phien ban 3
And permitPublicRead duoc yeu cau la false
And khong co ngoai le hop le cho thuoc tinh nay
When nguon dang tin xac minh actual co permitPublicRead bang true
Then he thong tao finding gan P, the he tai nguyen, B va rule version
And alert neu ro thuoc tinh lech va pham vi quan sat
And khong tu gan actor neu khong co bang chung danh tinh
And khong tu cap quyen khac phuc ngoai policy
```

### 11.4. Tiêu chí chấp nhận cho mất dữ liệu quan sát

```gherkin
Given finding drift dang mo va lan quan sat cuoi van lech
When collector mat quyen doc actual
Then trang thai hien tai the hien UNKNOWN hoac STALE theo contract
And finding khong duoc dong theo ly do da khoi phuc
And co tin hieu suc khoe cho pham vi bi anh huong
And khong coi ket qua rong la compliant
```

### 11.5. Tiêu chí chấp nhận cho ngoại lệ hết hạn

```gherkin
Given mot ngoai le duoc phe duyet cho dung tai nguyen va thuoc tinh
When ngoai le het han
Then he thong bat dau danh gia lai trong 5 phut theo vi du
And chi ap dung ket luan dua tren du lieu du moi
And neu actual van lech va khong con ngoai le thi tao hoac cap nhat alert
And neu khong the xac minh thi bao trang thai chua du bang chung
```

Các đoạn trên là tiêu chí để xây dựng kiểm thử dự án, không phải thông báo rằng một hệ thống thực tế đã vượt qua các kiểm tra.

## 12. Kiểm chứng và cải tiến trong vòng đời

### 12.1. Bộ thử phải kiểm tra cả đúng và sai ngữ cảnh

Cần ca thay đổi ngoài quy trình, rollout hợp lệ, biến thiên được phép, ngoại lệ sai scope, ngoại lệ hết hạn, baseline sai phiên bản và tài nguyên chưa có baseline.

Các ca ngữ nghĩa gồm thứ tự field, tập tương đương, danh sách có thứ tự, null, default, field chưa quan sát được và thay đổi giá trị nhạy cảm.

Các ca pipeline gồm event trùng, đến trễ, đảo thứ tự, bỏ event, API thiếu quyền, snapshot cũ, quét bị chậm, quota và tài nguyên ra khỏi selector.

Một lần tạo diff thành công trong công cụ phát triển chưa xác minh toàn luồng. Cần kiểm thử từ actual hoặc nguồn thay đổi tới kênh trực và bước triage, trong môi trường an toàn theo kế hoạch.

### 12.2. Theo dõi nhiễu, bỏ sót và khả năng khôi phục

Cần xem lại finding nhiễu do chuẩn hóa, baseline không đúng hoặc cửa sổ triển khai thiếu điều kiện. Không chỉ tăng debounce để làm mất những alert khó xử lý.

Khi phát hiện một thay đổi bị bỏ sót, cần xác định nó nằm ngoài scope, không có nguồn, rule sai hay dữ liệu tới quá trễ. Kết quả phải cập nhật coverage và yêu cầu liên quan.

Tự khôi phục nhiều lần có thể là dấu hiệu controller và thao tác thủ công đang xung đột. Cần giữ bằng chứng của chu kỳ lệch và khôi phục, thay vì chỉ thống kê trạng thái cuối.

### 12.3. Baseline và detector cần đi theo thay đổi sản phẩm

Đổi provider, API, schema hoặc cách triển khai có thể thay ý nghĩa field và default. Thay phân loại dữ liệu hoặc phạm vi tenant cũng có thể thay mức ưu tiên.

Cần kiểm soát phiên bản rule, normalization, baseline và exception; regression test trước khi mở rộng. Việc chuyển công cụ không được tự xóa lịch sử finding hoặc mất quan hệ với quyết định cũ.

### 12.4. Những câu đặc tả cần viết rõ hơn

| Câu còn mơ hồ | Điều cần bổ sung |
|---|---|
| “Cảnh báo khi config đổi” | Thuộc tính, baseline, policy, nguồn và tác động bảo mật |
| “Git là nguồn sự thật” | Trạng thái phê duyệt, hiệu lực, actual và kiểm tra policy |
| “State đã sync nên hết drift” | Phép so sánh nào đã đạt và actual có được khắc phục không |
| “Bỏ qua metadata” | Các trường cụ thể được phép bỏ, ảnh hưởng selector và kiểm soát |
| “Scan mỗi 5 phút” | Lịch bắt đầu, thời gian đọc, tải, quota, tính mới và điểm nhận alert |
| “Không có diff là compliant” | Dữ liệu đủ mới, đủ trường, nguồn đọc thành công và baseline đúng |
| “Maintenance thì mute” | Phạm vi, thuộc tính, thời hạn và chính sách rủi ro cao |
| “Auto-fix mọi drift” | Quyền, điều kiện trước, tác động, giới hạn và xác minh sau |

Một đặc tả alert theo configuration drift cần nối được **baseline được phê duyệt → actual đủ tin cậy → so sánh có ngữ nghĩa → ngoại lệ có giới hạn → cảnh báo đúng phạm vi → xử lý có quyền → xác minh và lịch sử**. Chuỗi này giúp phát hiện sự lệch có ý nghĩa bảo mật mà không hợp thức hóa cấu hình sai hoặc làm mất kiểm soát trong lúc khắc phục.

# Đánh giá kết quả và loại bỏ false positive trong kiểm thử bảo mật mạng

Trong chương **Kiểm thử và xác minh bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**, việc chạy một công cụ kiểm thử chỉ mới tạo ra **quan sát và giả thuyết**. Giá trị của một đợt kiểm thử đến từ khả năng trả lời: **cơ chế bảo vệ có hoạt động như kỳ vọng không, kết quả nào đã được xác minh, kết quả nào là false positive, trường hợp nào bị bỏ sót và thay đổi nào cải thiện an toàn mà không gây gián đoạn?**

Một IDS có thể cảnh báo khi nhân viên quản trị chạy một công cụ kiểm thử được duyệt. Một scanner có thể báo lỗ hổng dựa trên banner phiên bản nhưng bản vá đã được backport. Một kết nối thử tới subnet bị timeout có thể bị firewall chặn, nhưng cũng có thể do máy đích ngừng hoạt động. Một rule WAF tưởng như gây false positive có thể thực sự ngăn một request nguy hiểm được ngụy trang trong traffic hợp lệ.

Vì vậy, **loại bỏ false positive không có nghĩa xóa cảnh báo khỏi dashboard, tắt rule hoặc hợp thức hóa mọi hoạt động lành tính**. Đó là quy trình **xác minh ground truth, phân loại bằng chứng, tìm nguyên nhân, điều chỉnh chính xác phạm vi và kiểm thử lại cả trường hợp hợp lệ lẫn không hợp lệ**, có quyền phê duyệt và khả năng rollback.

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt **true positive (TP), false positive (FP), false negative (FN), true negative (TN)** và trạng thái **chưa xác minh** theo đúng câu hỏi kiểm thử.
- Tính, diễn giải và không lạm dụng **precision, recall, false positive rate, false discovery rate, specificity, F1 và coverage**.
- Thiết kế **test oracle/ground truth** và bộ **positive–negative controls** cho firewall, segmentation, IDS/IPS, WAF, VPN/ZTNA, DNS, cloud networking và scanner.
- Thu thập bằng chứng tại các lớp **packet, flow, policy decision, identity, application response và business outcome**.
- Phân biệt **tool false positive** với **môi trường không đúng, sensor thiếu coverage, dữ liệu đã cũ, cấu hình kiểm thử sai hoặc thay đổi chặn traffic thật**.
- Xây quy trình **triage → reproduce → corroborate → adjudicate → scoped tuning → regression → rollout → monitor → close**.
- Ghi nhận **exceptions có chủ sở hữu, căn cứ, TTL, phạm vi, kiểm thử lại và audit trail**, tránh làm giảm detection recall.
- Thực hành với dữ liệu **giả trên localhost/offline lab**, không tấn công hạ tầng hoặc bên thứ ba.

Các tên miền có hậu tố **.example**, địa chỉ IP trong dải dành cho tài liệu và kết quả thống kê ở bài đều là dữ liệu **minh họa**, không phải kết quả của hệ thống đang vận hành. Mọi hoạt động thử packet, kết nối, xác thực hoặc chính sách phải nằm trong **phạm vi được ủy quyền**.

## 1. Phạm vi kiểm thử và điều kiện an toàn

### 1.1. “Kiểm thử được phép” là một yêu cầu kỹ thuật

Trước khi đánh giá một false positive, phải xác minh phép thử đó đúng **resource, thời gian, identity và phương pháp** đã được phê duyệt.

| Thành phần scope | Câu hỏi cần trả lời |
| --- | --- |
| **Resource owner** | Ai quản lý hệ thống, ai có quyền chấp thuận? |
| **Assets / IP / FQDN** | Cụ thể những subnet, host, service, tenant nào được phép thử? |
| **Source test identity** | Tài khoản, endpoint, VPN tunnel hoặc workload thử là gì? |
| **Methods** | Chỉ đọc log, health check, synthetic request, scan có giới hạn hay phép thử khác? |
| **Traffic budget** | Tần suất, timeout, connection count, body size, bandwidth và load trần? |
| **Time window** | Thời điểm bắt đầu, kết thúc, timezone và change freeze? |
| **Guardrails** | Có cấm brute force, stress, fuzzing, exploit thật, truy cập dữ liệu production? |
| **Rollback / stop criteria** | Khi có lỗi dịch vụ, ai dừng thử và khôi phục? |
| **Evidence handling** | Ai được đọc PCAP, logs, WAF request fragments, user metadata? |
| **Escalation** | Khi phát hiện vấn đề thật hoặc tác động ngoài dự kiến, báo ai? |

Phép thử cho phép **GET /health trên lab** không tự cho phép thử credential stuffing, quét toàn bộ LAN hay thay firewall policy thật. Nếu scope mơ hồ, **không mở rộng phép thử** chỉ vì công cụ có thể chạy.

### 1.2. Nguyên tắc an toàn

- Ưu tiên **offline analysis, synthetic traffic, localhost, staging và test identities**.
- Với production, ưu tiên **read-only evidence**, replay ở lab và thay đổi có phê duyệt.
- Bảo vệ **credential, Cookie, Authorization, TLS session secrets, PCAP và dữ liệu người dùng**.
- Không “chứng minh false positive” bằng cách tắt IDS/IPS/WAF trên toàn hệ thống.
- Không thử khai thác lỗ hổng trên hệ thống ngoài scope; sử dụng **authenticated configuration/version evidence** khi đủ để xác minh.
- Có **positive control** để tránh nhầm “đường không truy cập được vì app chết” thành “firewall chặn đúng”.
- Ghi **tác động ngoài dự kiến** là một finding của test, không giấu để số liệu đẹp.

## 2. Phải đặt đúng câu hỏi trước khi gắn nhãn TP/FP/FN/TN

Trong kiểm thử bảo mật mạng, một kết quả “positive” có thể mang **ngữ nghĩa khác nhau**:

1. **Detector:** “Có hoạt động đáng nghi/lỗ hổng/vi phạm policy”.
2. **Preventive control:** “Một kết nối thuộc loại phải chặn đã bị chặn”.
3. **Availability test:** “Một kết nối hợp lệ được phép đi qua và dịch vụ trả phản hồi”.
4. **Compliance test:** “Cấu hình triển khai đúng yêu cầu”.

Ví dụ một firewall **deny** có thể là **thành công của security control** đối với đường trái quyền nhưng là **lỗi tính khả dụng** đối với đường hợp lệ. Không gọi deny là “true positive” hay “false positive” trước khi xác định **test objective**.

### 2.1. Chuẩn hóa bài toán phân loại

Trong bài, khi tính confusion matrix của **detector/cảnh báo**:

- **Positive prediction:** detector phát cảnh báo hoặc đánh dấu rủi ro.
- **Actual positive:** một trường hợp thuộc **loại sự kiện mục tiêu** đã được ground truth xác nhận.
- **Actual negative:** trường hợp không thuộc loại mục tiêu theo oracle/bộ test có đủ bằng chứng.

Đối với firewall hoặc ZTNA **enforcement**, dùng thêm ma trận **expected access decision vs observed enforcement outcome**; không lẫn hai loại bảng.

### 2.2. Sơ đồ hai cấp xác minh

~~~mermaid
flowchart TD
    A["Test scenario + expected behavior"] --> B["Observed alert / allow / deny / response"]
    B --> C{"Evidence đủ để phân loại?"}
    C -->|Không| D["UNVERIFIED / telemetry gap / needs retest"]
    C -->|Có| E["Compare against ground truth / oracle"]
    E --> F["Classify TP / FP / FN / TN (for detector)"]
    E --> G["Classify allowed / blocked correct or incorrect (for policy)"]
    F --> H["Root-cause + safe tuning"]
    G --> H
    H --> I["Positive + negative regression"]
    I --> J["Approval, rollout, monitoring and review"]
~~~

## 3. Định nghĩa TP, FP, FN, TN và trạng thái không xác định

| Ground truth | Detector cảnh báo | Detector không cảnh báo |
| --- | --- | --- |
| **Có sự kiện mục tiêu** | **TP** — phát hiện đúng | **FN** — bỏ sót |
| **Không có sự kiện mục tiêu** | **FP** — cảnh báo sai | **TN** — bỏ qua đúng |

### 3.1. True Positive (TP)

Một phép thử giả lập đã được gắn nhãn là lưu lượng cần phát hiện, sensor nằm đúng capture path, rule hoạt động và phát alert đúng với tín hiệu được định nghĩa. **TP không tự chứng minh đã có tấn công thành công**: có thể chỉ là request bị phát hiện/chặn.

### 3.2. False Positive (FP)

Detector cảnh báo cho hành vi **không thuộc sự kiện mục tiêu đã định nghĩa**, trong bối cảnh đã được kiểm chứng. Ví dụ một synthetic request hợp lệ trên staging kích hoạt chữ ký WAF vì pattern tương tự cú pháp tấn công nhưng payload được ứng dụng xử lý như dữ liệu thông thường và không vượt trust boundary. Cần đủ evidence để kết luận; **“người dùng nói hợp lệ” chỉ là thông tin ban đầu**, không phải ground truth cuối.

### 3.3. False Negative (FN)

Một trường hợp thuộc **positive ground truth** đã thực sự đi qua sensor/enforcement point có kỳ vọng phát hiện, nhưng detector không báo hoặc control không chặn theo test objective. Nếu traffic **không đi qua sensor**, đó có thể là **coverage failure** thay vì rule-level FN; phải ghi rõ nguyên nhân và tiêu chí đo.

### 3.4. True Negative (TN)

Một benign/allowed trường hợp đã được test và không bị detector cảnh báo. Không lấy toàn bộ lưu lượng không có alert trong production làm TN nếu không có **nhãn ground truth**; phần lớn benign cases chưa hề được xác minh.

### 3.5. Unverified và inconclusive không phải TN

Một sample có IDS alert nhưng:

- PCAP thiếu đầu connection.
- TLS/QUIC không có app content.
- Endpoint owner chưa xác minh.
- Rule phiên bản khác với test.
- Time/NAT mapping không rõ.

Nên đánh nhãn **UNVERIFIED/INCONCLUSIVE** hoặc **NEEDS_MORE_EVIDENCE**, không tự đổi thành FP/TN chỉ vì chưa tìm thấy tác động.

### 3.6. Khái niệm “false positive” có thể phụ thuộc policy

Một scanner báo “TCP 22 exposed” là đúng về **reachability** nếu SSH đang nghe và reachable từ test zone; nhưng SSH có thể được cho phép bởi policy. Đây là **observed fact đúng, policy risk có thể accepted**, không nhất thiết là false positive của scanner. Nếu scanner tuyên bố “SSH có thể khai thác CVE X” chỉ do banner sai, đây là hypothesis khác cần xác minh.

## 4. Ground truth và test oracle: không có nhãn chuẩn thì không có FP chắc chắn

**Ground truth** là bằng chứng đủ mạnh để xác định trạng thái thực của test case; **test oracle** là quy tắc quyết định PASS/FAIL hoặc target label trước/độc lập với kết quả công cụ đang kiểm tra.

### 4.1. Các nguồn oracle có thể dùng

| Test objective | Ground truth/expected result phù hợp |
| --- | --- |
| **Firewall segmentation** | Approved connectivity matrix, policy intention, actual dataplane test |
| **IDS rule detection** | Lab packet fixture/test event được dựng có nhãn, sensor path/alert expected |
| **WAF false positive** | App route contract, sanitized request/response, WAF rule decision, server behavior |
| **VPN/ZTNA access** | IAM entitlement, posture/device state, authenticated PEP decision, session logs |
| **Vulnerability finding** | Authenticated version/config, patch/backport evidence, vendor advisory, safe validation |
| **DNS protective policy** | Approved domain category/policy, resolver answer/log, direct bypass checks |
| **Cloud/Kubernetes policy** | Deployed security group/NACL/NetworkPolicy attachment và live reachability test |
| **NAC/802.1X** | Device identity, expected VLAN/ACL, RADIUS result, effective port/session state |

### 4.2. Oracle không được lấy nguyên từ tool cần đánh giá

Nếu dùng “scanner báo vulnerable” làm nhãn actual positive, rồi tính scanner precision từ chính các alert đó, phép đo **circular** và không cho biết FP. Cần ít nhất một **nguồn xác minh độc lập** hoặc lab condition có thể kiểm soát được.

Ví dụ: banner scanner báo version A, nhưng OS package manager và bản tin bảo mật của nhà cung cấp cho biết **bản vá được backport**. Ground truth về tính dễ bị khai thác phải dựa trên **điều kiện cụ thể của lỗ hổng**, không chỉ banner.

### 4.3. Hai nguồn đồng ý vẫn có thể cùng sai

Một IDS và dashboard SIEM có thể đều dùng cùng rule output; đó là **hai giao diện của cùng nguồn**, không phải corroboration độc lập. Tìm nguồn khác lớp như **app log, endpoint/process, firewall dataplane, authorized lab replay**.

### 4.4. Ground truth có phạm vi

Một TCP test chứng minh cổng reachable từ **Zone A** không chứng minh mọi Zone đều reachable. Một negative test từ một identity không chứng minh **mọi account** bị deny. Gắn oracle với **source zone, identity, resource, service, time, policy version và network path**.

### 4.5. Dữ liệu giả lập và production khác nhau

Lab fixtures có nhãn rõ giúp đo recall nhưng không tái hiện hết **CDN, proxy, IPv6, encrypted traffic, packet loss, user behavior, burstiness hoặc phiên bản client**. Báo hiệu quả trên **test population**; không chuyển kết quả đó thành production detection rate nếu chưa có phương pháp đo tương ứng.

## 5. Confusion matrix và các chỉ số định lượng

### 5.1. Các công thức

Với TP, FP, FN, TN:

\[
\mathrm{Precision}=\frac{TP}{TP+FP}
\]

\[
\mathrm{Recall\ (TPR)}=\frac{TP}{TP+FN}
\]

\[
\mathrm{Specificity\ (TNR)}=\frac{TN}{TN+FP}
\]

\[
\mathrm{False\ Positive\ Rate\ (FPR)}=\frac{FP}{FP+TN}
\]

\[
\mathrm{False\ Discovery\ Rate\ (FDR)}=\frac{FP}{TP+FP}=1-\mathrm{Precision}
\]

\[
\mathrm{False\ Negative\ Rate\ (FNR)}=\frac{FN}{FN+TP}=1-\mathrm{Recall}
\]

\[
F_1=\frac{2TP}{2TP+FP+FN}
\]

Các công thức trên chỉ có nghĩa khi **ground truth/denominator** xác định được. Nếu denominator bằng 0, metric không xác định; không tự báo 100%.

### 5.2. Ví dụ test set mất cân bằng

Giả định có **1.000 tình huống kiểm thử có nhãn**: 40 tình huống positive cần phát hiện, 960 benign.

| Kết quả | Số lượng |
| --- | ---: |
| TP | 32 |
| FN | 8 |
| FP | 48 |
| TN | 912 |
| **Tổng** | **1.000** |

Suy ra:

- **Precision = 32/(32+48) = 40%**: chỉ 40% alerts của bộ test là positive thực.
- **Recall = 32/(32+8) = 80%**: 20% positive cases bị bỏ sót.
- **Specificity = 912/(912+48) = 95%**.
- **FPR = 48/(48+912) = 5%**.
- **FDR = 48/(32+48) = 60%**.
- **F1 = 64/(64+48+8) ≈ 53,3%**.
- **Accuracy = (32+912)/1000 = 94,4%**, dù precision chỉ 40%.

Đây là minh họa cho **base-rate effect**: nếu benign traffic áp đảo, ngay một FPR tưởng thấp cũng có thể sinh nhiều alerts sai hơn alerts đúng.

### 5.3. Accuracy có thể gây hiểu lầm

Một detector không cảnh báo gì trong tập 1.000 mẫu với 990 benign và 10 positive sẽ đạt **99% accuracy**, nhưng **recall=0%**. Vì vậy không chọn rule chỉ dựa trên accuracy; cần precision, recall, coverage, severity và chi phí sai sót.

### 5.4. Phân biệt FPR và “% alerts sai”

- **FPR** có denominator là **all actual negatives**.
- **FDR** hoặc **1 - precision** có denominator là **all predicted positives (alerts)**.

Nếu SOC nói “60% cảnh báo là sai”, đó là một tỷ lệ tương tự **FDR** trên các alerts đã được gắn nhãn đầy đủ, **không phải FPR=60%**.

### 5.5. Nhiều cấp độ TP/FP

Cần nêu metric đo ở cấp:

- **Packet/flow**: một flow có thể kích hoạt nhiều signatures.
- **Alert**: một incident có thể sinh hàng trăm alerts.
- **Detection rule invocation**: dùng khi đánh giá phiên bản rule.
- **Incident/case**: alerts được correlation thành một vụ điều tra.
- **Business operation**: request/transaction sau proxy và application.

Không lấy **số alerts FP** chia cho **số incidents**; numerator/denominator phải cùng đơn vị.

## 6. Độ bao phủ và chất lượng dữ liệu là điều kiện của mọi kết luận

Một kết quả không thấy alert có thể do **rule không match**, **sensor không thấy traffic**, hoặc **pipeline không ghi nhận alert**.

### 6.1. Những câu hỏi cần trả lời

1. **Test traffic đã đi qua đúng sensor hoặc PEP chưa?**
2. Sensor có đầy đủ **cả hai chiều** khi detector cần request/response không?
3. Có **packet drop, span oversubscription, sampling, capture truncation, NAT/overlay** làm mất dữ liệu không?
4. App có dùng **TLS/QUIC/ECH**, parser có thể đọc trường detector yêu cầu không?
5. Alert được tạo nhưng **SIEM ingestion/dedup/suppression** làm biến mất?
6. Rule đang **enabled/monitor-only/block**, deployed version và priority nào?
7. Có **clock skew, log ingestion delay hoặc time-window mismatch**?
8. Test request có tới **đúng host/path, service port, subnet và workload revision**?

### 6.2. Các trạng thái quan sát

~~~text
TEST_EXECUTED_AND_OBSERVED
TEST_EXECUTED_BUT_SENSOR_MISSED
TEST_NOT_REACHING_ENFORCEMENT_POINT
CONTROL_DECISION_OBSERVED
CONTROL_DECISION_NOT_LOGGED
APPLICATION_OUTCOME_CONFIRMED
PARTIAL_CAPTURE
ENCRYPTED_CONTENT_NOT_OBSERVABLE
UNKNOWN
~~~

Đừng gộp mọi trạng thái thành “false negative” hoặc “no vulnerability”. Cần tách **coverage quality** với **detection accuracy**.

### 6.3. Positive control chống nhầm lẫn availability

Ví dụ kiểm thử segmentation kỳ vọng **Source A không được SSH tới DB**. Test timeout không đủ chứng minh firewall deny. Hãy xác minh:

- Destination **đang hoạt động** và có listener phù hợp.
- Từ **allowed source** có authorized positive test kết nối được.
- Tại PEP có **deny event/connection decision** phù hợp.
- Route/DNS/source IP/IPv4 vs IPv6 khớp scope.
- Không có **host-local firewall hoặc service crash** tạo kết quả giống deny.

Đối với trường hợp kỳ vọng **allow**, cũng cần app response có ý nghĩa, không chỉ TCP SYN-ACK nếu mối quan tâm là API có thể phục vụ.

## 7. Thu thập bằng chứng với provenance và mức tin cậy

Một finding được đánh dấu false positive cần có **evidence truy nguyên được**, không chỉ comment “known benign”.

### 7.1. Evidence schema mẫu

~~~json
{
  "finding_id": "FIND-LAB-014",
  "test_id": "TEST-ZONE-A-DB-014",
  "objective": "verify_denied_path",
  "scope": {
    "source_zone": "test-zone-a",
    "destination": "db.lab.example",
    "service": "tcp/5432",
    "identity": "synthetic-lab-identity"
  },
  "expected_policy_result": "DENY",
  "observed": {
    "client_result": "connection_timeout",
    "firewall_event": "deny_rule_21",
    "app_result": "not_received",
    "sensor_health": "verified_for_test_window"
  },
  "time_utc": "2026-11-28T09:20:00Z",
  "policy_version": "lab-policy-v3",
  "evidence_refs": [
    "EVID-LAB-FW-21",
    "EVID-LAB-CLIENT-06"
  ],
  "adjudication": "EXPECTED_DENY_CONFIRMED_IN_SCOPE",
  "limitations": "One source, one destination, one time window"
}
~~~

Đây là **schema giả định**. Không điền field **sensor_health=verified** hoặc **app_result=not_received** nếu thiếu logs/test chứng minh.

### 7.2. Bằng chứng theo lớp

| Lớp | Nguồn | Có thể chứng minh | Không tự chứng minh |
| --- | --- | --- | --- |
| **Client/test driver** | curl, synthetic client, command output | Request/connection attempt và client error | PEP nào chặn; server đã xử lý |
| **Network path** | PCAP, NetFlow, router/firewall flow | Packet/flow observable, TCP state nếu đủ | User intent, app authorization |
| **Policy decision** | NGFW, WAF, PEP, cloud audit | Rule/action tại một enforcement point | Toàn bộ policy paths khác được bảo vệ |
| **Identity** | IdP/VPN/ZTNA/IAM | Authn/posture/role/session state | Tất cả app operations đã diễn ra |
| **Endpoint** | EDR/process audit | Process/network association theo agent | Ground truth hoàn toàn khi agent bị mất |
| **Application** | Access/transaction logs | Route, status, app actor/outcome trong scope | Mọi network packets |
| **Scanner** | Scan report | Tool quan sát/banner/test response | Lỗ hổng exploitability chắc chắn |

### 7.3. Mức khẳng định

| Nhãn | Ý nghĩa |
| --- | --- |
| **OBSERVED** | Nguồn quan sát trực tiếp một event/field đã mô tả |
| **CORROBORATED** | Có nhiều nguồn độc lập hỗ trợ cùng claim |
| **INFERRED** | Giả thuyết có căn cứ nhưng không xác nhận trực tiếp |
| **UNVERIFIED** | Thiếu dữ liệu/điều kiện test để kết luận |
| **CONFIRMED_FP** | Có oracle và evidence xác nhận detector cảnh báo sai cho mục tiêu đã định |
| **CONFIRMED_TP** | Có oracle và evidence xác nhận detector cảnh báo đúng |
| **SCOPE_EXCEPTION** | Finding hợp lệ nhưng được chấp nhận có điều kiện theo policy |
| **DISPUTED** | Bằng chứng mâu thuẫn cần giải quyết |

**SCOPE_EXCEPTION không đồng nghĩa CONFIRMED_FP**: một nguy cơ thật có thể được business chấp nhận trong phạm vi và thời hạn nhất định.

## 8. Kiểm tra dữ liệu gốc, đồng hồ và trạng thái công cụ

### 8.1. Những nguyên nhân tạo FP mà không cần rule sai

| Tình huống | Biểu hiện | Cần kiểm tra |
| --- | --- | --- |
| **Log delay / out-of-order** | Alert dường như tới trước request | Event time, ingest time, NTP offset |
| **Duplicate ingestion** | Một test bị đếm thành nhiều alerts | Source event ID, collector retries |
| **Sampling/truncation** | Một phần payload bị parser diễn giải sai | Captured/original length, packet drops |
| **Asymmetric routing** | Chỉ nhìn một chiều TCP | Sensor placement và return path |
| **NAT / proxy rewriting** | Source IP/Host/path khác kỳ vọng | Original vs translated tuple, trusted proxy logs |
| **Clock skew** | Correlation nhầm phiên/user | Original timestamp, corrected UTC, uncertainty |
| **Schema version drift** | Trường action biến từ blocked sang detected | Parser/schema release, raw record |
| **IP/workload reuse** | Finding gắn sai asset | DHCP lease, Pod UID, VM lifecycle |
| **Cache/CDN** | Scanner thấy banner/response của edge | Target authority, upstream origin, test method |
| **Stale asset inventory** | Scanner báo trên host đã decommission | Asset lifecycle, discovery timestamp |
| **Rule deployment mismatch** | Lab pass, production false alarm | Applied config/version, zone/PEP |

### 8.2. Event time và ingestion time

Một alert SIEM được index lúc 09:08 có thể bắt nguồn từ firewall flow 09:01. Nếu ghép theo ingest time, dễ gán nhầm nó cho một deployment 09:07. Cần giữ **raw timestamp, timezone, UTC normalized event time, clock quality và ingestion delay**; khi uncertainty intervals giao nhau, không khẳng định thứ tự chính xác.

### 8.3. Không sửa raw evidence cho vừa giả thuyết

Nếu parser sai, tạo **derived normalized event** với version và correction note; giữ raw packet/log và checksum/record reference. Một finding có thể được reclassified từ suspected TP sang FP sau khi sửa mapping, nhưng phải giữ **adjudication history** và người review.

### 8.4. Kiểm tra tool trước khi chê rule

Khi scanner báo lỗi không ổn định, xác minh **DNS resolution, proxy mode, TLS verification, timeout, retries, authenticated scan credentials, plugin/database version, rate limits và target redirect**. Nếu scanner không đăng nhập được, nó có thể cho **unsupported/inconclusive finding** chứ không phải FP chắc chắn.

## 9. Correlation qua network paths và nhận dạng đối tượng

Trong mạng có NAT, proxy, VPN, service mesh hoặc cloud load balancer, **5-tuple tại cảm biến A có thể không giống 5-tuple tại B**. Một cảnh báo không thuộc đúng workload sẽ bị đánh nhầm FP dù pattern phát hiện là đúng ở nơi khác.

~~~mermaid
flowchart LR
    C["Test identity + endpoint"] --> V["VPN / ZTNA"]
    V --> N["NAT / FW"]
    N --> P["WAF / proxy"]
    P --> A["Application / workload"]
    C -. "EDR/test driver ID" .-> X["Correlation ledger"]
    V -. "VPN session ID" .-> X
    N -. "NAT 5-tuple/time" .-> X
    P -. "Gateway request/trace ID" .-> X
    A -. "App actor/outcome" .-> X
~~~

### 9.1. Quy tắc ghép evidence

1. Xác định **capture point/hop** của từng nguồn.
2. So sánh **time intervals**, không chỉ timestamp cùng phút.
3. Dùng **NAT translation mapping** với source/dest ports và protocol.
4. Dùng **authenticated VPN/IdP session mapping** để xác định client/workload.
5. Trên HTTP/2/HTTP/3, xác định **request/stream IDs** thay vì đếm connections.
6. Xem **retry, redirect, health check** trước khi gộp events.
7. Khi không khớp, đánh dấu **INFERRED/UNKNOWN**, không tự chọn một user.

### 9.2. X-Forwarded-For không phải bằng chứng user

Header **X-Forwarded-For/Forwarded** có thể do client tự khai. Chỉ tin chain khi trusted proxy **validate/overwrite** theo chính sách. Kết luận “request từ nhân viên A” phải dựa trên **peer connection, NAT/VPN mapping, authenticated application identity**; không chỉ IP in trong header.

### 9.3. DNS và SNI không chứng minh URL hoặc payload

DNS query có thể đến từ cache/prefetch, SNI có thể vắng do ECH, và CDN IP có nhiều tenants. Nếu scanner/WAF/IDS gắn “malicious download” từ DNS + TCP 443, cần **app/DLP/endpoint evidence** trước khi xác nhận. Không thấy HTTP path trong HTTPS là **not observable by design**, không phải một FP hay FN được phân loại tùy ý.

## 10. Kiểm thử enforcement khác kiểm thử detection

### 10.1. Enforcement matrix riêng

| Policy expectation | Observed access allowed | Observed access denied |
| --- | --- | --- |
| **ALLOW** | Đúng mong đợi | **False block / availability regression** |
| **DENY** | **Policy bypass / false allow** | Đúng mong đợi |

“False block” ở bảng này đôi khi được gọi không chính thức là false positive của firewall policy (chặn traffic hợp lệ). Nhưng đừng đưa trực tiếp vào confusion matrix IDS nếu định nghĩa **positive** của IDS là phát hiện tấn công.

### 10.2. Application response khác network allow

TCP connect thành công có thể vẫn nhận **HTTP 401/403** do application auth. Một firewall **allow** cũng không chứng minh server nhận toàn bộ data. Khi kiểm thử segmentation, chọn **network reachability oracle**; khi kiểm thử API authorization, chọn **application authorization oracle**.

### 10.3. Ba mốc khi thay đổi control

- **Requested:** đã gửi lệnh/chấp thuận thay đổi.
- **Applied:** control-plane/config xác nhận thay đổi được triển khai.
- **Effective:** test/dataplane evidence chứng minh control làm việc theo kỳ vọng.

Không đo hiệu quả rule chỉ từ status “deployment succeeded”. Trong distributed/cloud network, propagation delay hoặc config mismatch có thể khiến mỗi path có kết quả khác.

### 10.4. Cần cả hai loại test

Nếu chỉ thử **allowed path**, có thể không biết firewall đang **fail-open** với forbidden path. Nếu chỉ thử **denied path**, firewall có thể “bảo mật” bằng cách chặn mọi thứ. **Positive legitimate-traffic control + negative forbidden-traffic control** phải cùng có trong acceptance criteria.

## 11. Firewall/NGFW: xác định rule false block hay false allow

### 11.1. Thiết kế connectivity policy matrix

Ví dụ mô hình giả:

| Nguồn | Đích | Service | Kỳ vọng | Bằng chứng |
| --- | --- | --- | --- | --- |
| Web tier | App tier | TCP/8443 | ALLOW | TCP/TLS success + app health |
| Web tier | DB tier | TCP/5432 | DENY | Firewall deny + listener positive control |
| Admin VPN role | Jump host | TCP/22 | ALLOW có điều kiện | Entitlement + session + SSH handshake test |
| Guest Wi-Fi | Internal admin | TCP/443 | DENY | Source zone + PEP deny |
| Backup workload | Approved storage | TCP/443 | ALLOW | Authenticated backup/synthetic path |
| Untrusted source | Backup control API | TCP/443 | DENY | Role/path based policy evidence |

### 11.2. Khi TCP timeout gây false confidence

Một test cổng 5432 timeout có thể do:

- Firewall deny theo policy.
- Không có route hoặc route sai.
- DB server stopped, không listen.
- Host firewall chặn.
- DNS dẫn sai IP.
- Security group/NACL chặn ở layer khác.
- TCP SYN đi được nhưng return path bị mất.

Do đó kết luận “segmentation PASS” cần **rule/PEP event** kết hợp **allowed-source positive control**. Nếu không có logs, ghi **INCONCLUSIVE** và chỉ rõ evidence cần bổ sung.

### 11.3. Rule shadowing, priority và NAT

NGFW có thể áp **rule ordering, implicit deny, pre-NAT/post-NAT addresses, zones, object groups, identity matching**. Một cảnh báo “wrong rule hit” có thể do dashboard hiển thị địa chỉ sau NAT nhưng policy được đánh giá trước NAT hoặc ngược lại tùy sản phẩm. Xác minh **vendor semantics và effective policy**, không chỉ text config.

### 11.4. Stateful inspection và chiều traffic

Return traffic có thể được chấp nhận bởi **stateful established-flow handling** dù không có inbound allow rule riêng. Một tester thấy response đi qua chưa chứng minh firewall cho phép **new inbound sessions** từ untrusted zone. Dùng test case **new connection đúng chiều**, ghi session state và source zone.

### 11.5. Một false block không đồng nghĩa nên mở cổng rộng

Nếu legitimate job bị chặn, fix có thể là **service identity mapping, đúng destination FQDN/IP, source group, schedule hoặc service port**, không phải mở **ANY/ANY**. Kiểm thử lại đường **đáng lẽ phải deny** sau mỗi thay đổi.

## 12. Kiểm thử segmentation và microsegmentation

### 12.1. Phạm vi phân đoạn

Một thiết kế phân đoạn có thể ở nhiều lớp:

- **VLAN/VRF, route table và ACL**.
- **Perimeter/internal firewall**.
- **Cloud security group, NACL, subnet routing**.
- **Kubernetes NetworkPolicy + CNI enforcement**.
- **Service mesh authorization/mTLS**.
- **Identity-aware ZTNA/PEP**.
- **Host firewall và workload identity**.

**Sơ đồ kiến trúc không chứng minh policy đã được thực thi**. Cần kiểm tra từng đường đi thực tế với source/destination identities thuộc scope.

### 12.2. False positive thường gặp

Scanner nói “workload A truy cập DB bị chặn” nhưng test pod không có label đúng, sidecar chưa được inject, hoặc traffic đi qua **egress gateway** khác. Đây là **test setup mismatch**, chưa chắc control false positive.

### 12.3. Positive test và bypass test

Trên lab:

1. Allowed workload với đúng **namespace, labels, service account** có thể gọi API.
2. Denied workload không thể tạo connection/application request như policy.
3. Các **alternate paths** (IPv6, node IP, public LB, sidecar bypass, secondary NIC) được liệt kê và chỉ thử nếu scope cho phép.
4. Có **PEP/dataplane evidence** đúng nguồn và giờ.
5. Thử lại sau rollout, policy propagation hoặc failover.

Không mở thêm đường bypass chỉ để “tạo FN”; test cần giới hạn ở **mạng thử nghiệm hoặc đường đã được chủ hệ thống cho phép**.

### 12.4. Gắn policy objective vào outcome

Nếu NetworkPolicy của Kubernetes chỉ được thiết kế bảo vệ traffic **pod-to-pod**, kết quả từ **hostNetwork**, traffic node-local hoặc external LB có thể nằm ngoài phạm vi kiểm soát thực tế tùy CNI/kiến trúc. Đó có thể là **coverage/design gap**, không nên chỉ “suppress false positive” mà bỏ qua đường truy cập không được bảo vệ.

## 13. IDS/IPS và NDR: false positive trong signature/anomaly detection

### 13.1. Vì sao benign traffic kích hoạt IDS?

- Rule dùng **generic byte pattern** trùng payload hợp lệ.
- Protocol parser hiểu nhầm **fragmentation/reassembly/encoding**.
- Network scan được **ủy quyền** nhìn giống discovery không hợp lệ.
- App library/SDK update tạo **TLS fingerprint** mới.
- Backup/monitoring jobs tạo **periodic flow/large transfer**.
- Signature không đủ ràng buộc với **source zone, destination service, protocol state**.
- SIEM **duplicate/correlation** khiến một event thành nhiều alerts.
- Một IOC/domain/IP được **chia sẻ qua CDN hoặc cloud multi-tenancy**.

### 13.2. Chữ ký khớp không chứng minh tấn công thành công

Một Suricata/IDS signature match có thể phản ánh **attempt**, **benign packet bytes**, **test fixture**, hoặc lưu lượng đã bị IPS block. Muốn biết server có bị khai thác, cần **endpoint/app/business outcome** khi phép thử yêu cầu.

### 13.3. Phân tích theo rule và cohort

Thay vì tắt mọi alert cùng signature:

| Thuộc tính | Cách phân nhóm |
| --- | --- |
| Rule ID/version | Quy tắc nào thật sự tạo alert? |
| Transport/protocol state | TCP handshake/HTTP/TLS/QUIC |
| Source cohort | Scanner lab, workstation, service account |
| Destination service | Admin portal, API, DNS, backup |
| Environment | Lab, staging, production, partner |
| App/client version | Trước/sau SDK/browser release |
| Time pattern | Scheduled job, burst, unexplained deviation |
| Outcome | Blocked, allowed, unknown, app action |

Một FP chỉ có thể được chứng minh trong **cohort/test condition** cụ thể. Không suy rằng tất cả alerts tương tự trên mạng đều FP.

### 13.4. Đo packet loss và blind spots

Nếu detector không thấy bài test đã gắn nhãn positive, cần kiểm tra **SPAN/TAP mirror, packet drops, decoder version, TLS content visibility, capture direction, filter, rule enabled state và EVE/SIEM delivery**. Khi sensor không instrumented path, báo **coverage gap**, không báo rule precision/recall từ một bộ test không hợp lệ.

### 13.5. IPS block là một hành động có rủi ro

Tuning IPS không chỉ giảm alerts mà còn ảnh hưởng kết nối thật. Có thể dùng **detect-only/canary mode** theo phê duyệt, test permitted/forbidden fixtures rồi mới promote. Cần theo dõi **latency, packet drops, session resets, error rates và security detections** sau rollout.

### 13.6. Tín hiệu nào thường cần điều tra tiếp?

Ví dụ một source benign được cấp phép quét có thể kích hoạt signature port scan; nhưng nếu cùng source còn có **privilege escalation, account abuse hoặc unauthorized data access**, không được whitelisting toàn bộ source. Đánh giá **mỗi phát hiện theo rule/behavior và time window**.

## 14. WAF và API gateway: lỗi phát hiện so với lỗi ứng dụng

### 14.1. Vì sao WAF dễ tạo false block?

Một ứng dụng nhận JSON, Markdown, SQL examples hoặc source code do user hợp lệ tải lên. Các chuỗi này có thể trùng **rule pattern** cho SQL injection, XSS hoặc path traversal dù ứng dụng xử lý chúng như dữ liệu không thể thực thi. Tuy nhiên, một input “trông như ví dụ” cũng có thể khai thác nếu app **đưa nó vào câu lệnh/cấu trúc không an toàn**. Kết luận phải dựa trên **route contract, parse behavior, context và output encoding**, không chỉ content nhìn có vẻ vô hại.

### 14.2. Trường cần có trong triage WAF

| Trường | Ý nghĩa |
| --- | --- |
| **WAF transaction/request ID** | Ghép đúng một quyết định |
| **Rule ID/version/message** | Quy tắc kích hoạt, không chỉ score |
| **Engine/action mode** | Detect, block, challenge, rate limit |
| **Normalized route/method/content type** | Hiểu ngữ cảnh application |
| **Matched variable/location** | Header/query/body; không cần lưu secret |
| **Source identity/zone** | Authenticated principal thay IP alone |
| **App/gateway outcome** | Request có bị chặn trước app không? |
| **Deployment/feature revision** | Có release làm traffic thay đổi không? |
| **Test fixture version** | Khả năng tái hiện không dùng dữ liệu thật |

### 14.3. Không dùng 403 đơn độc làm bằng chứng

Một **403** có thể từ WAF, reverse proxy, authorization layer hoặc application; **429** có thể từ rate limiting; **502** có thể upstream error. Xác định **response source** và điểm xử lý thật trước khi gọi WAF false positive.

### 14.4. Kiến trúc sửa đúng phạm vi

Ưu tiên theo thứ tự, tùy bằng chứng:

1. Xác minh **application contract và expected request**; nếu client gửi sai, sửa client.
2. Sửa **canonicalization/decoder/parser** nếu hiểu sai HTTP framing.
3. Nâng/cập nhật **rule set** có correction đã thử.
4. Điều chỉnh **chính xác rule ID, parameter/route, content type, caller identity** khi phù hợp.
5. Giới hạn exception theo **owner, TTL, environment** và lưu lý do.
6. Kiểm thử **benign fixture** cùng **known malicious synthetic fixture**, bảo đảm không làm bypass rule khác.

Tránh **disable toàn bộ SQLi/XSS detection trên một domain** chỉ vì một endpoint có body chứa source code.

### 14.5. An toàn khi xem request evidence

WAF logs có thể chứa **Authorization, Cookie, query token hoặc một đoạn body riêng tư**. Dùng **masked matched location, rule ID, route template, test payload giả**, phân quyền nghiêm ngặt; không gửi raw request của khách hàng vào chat hay công cụ thử nghiệm không được phép.

## 15. Vulnerability scanning: finding sai, không đủ bằng chứng và rủi ro đã được xử lý

### 15.1. Scanner đưa ra giả thuyết theo nhiều cơ chế

- **Banner/version inference**: software tự khai phiên bản.
- **Authenticated inventory**: đọc package/version/config trên host với quyền.
- **Remote behavior checks**: quan sát response theo một test có giới hạn.
- **Configuration assessment**: so baseline/policy.
- **Authenticated dependency inventory/SBOM**: xác định component và metadata.

Độ tin cậy khác nhau. Scanner đưa ra kết quả **potential vulnerability** không phải lúc nào cũng xác nhận **điều kiện khai thác**.

### 15.2. Backport và thông tin phiên bản

Một Linux distribution có thể **backport security fix** mà giữ upstream version string. Scanner dựa trên banner sẽ báo CVE, trong khi gói đã được vá theo **vendor advisory và installed package release**. Cách xác minh:

1. Xác nhận **asset chính xác** và scanner plugin ID.
2. Thu **package metadata, distribution release, vendor security advisory** có hiệu lực.
3. So sánh **CVE affected configuration/feature, patch status và runtime binary**.
4. Nếu cần kiểm thử kỹ thuật, dùng **staging và phương pháp không phá hoại có quyền**.
5. Lưu evidence và phân loại: **confirmed FP**, **patched/mitigated**, **affected** hoặc **inconclusive**.

Không gọi “false positive” chỉ vì admin nói “đã patch” nếu không có bằng chứng package/deployment đang chạy.

### 15.3. Service fingerprint nhầm đích

Load balancer, WAF, CDN hoặc transparent proxy có thể trả banner **khác origin**. Một scanner thấy TLS certificate hết hạn của test host nhưng thực ra kết nối vào **stale IP từ asset inventory**. Xác minh:

- **DNS A/AAAA/CNAME** tại thời điểm test.
- **SNI/Host** thực scanner gửi.
- Proxy/LB routing rules, listener/target groups.
- **Certificate chain** ở điểm test và app server.
- Actual **asset owner** theo cloud/resource inventory.

### 15.4. Risk acceptance không phải FP

Nếu lỗ hổng còn thực nhưng đã có **compensating controls và exception được phê duyệt**, phân loại **confirmed vulnerability — risk accepted/mitigated**, không đổi sang FP. Điều này giữ tính trung thực của vulnerability posture và giúp rà soát khi exception hết hạn.

### 15.5. “Không scan được” không phải “không có lỗ hổng”

Scanner credential thất bại, target down hoặc firewall block scanner có thể làm coverage giảm. Kết quả nên là **scan failed/partial coverage**, không phải TN. Kiểm thử scanner reachability và credentials bằng **đường được phép**; không tìm đường bypass tự phát.

### 15.6. Lưu bằng chứng tính không thể khai thác theo scope

Một component có CVE nhưng **feature bị tắt** hoặc **code path không reachable** có thể giảm exploitability; song code vẫn có thể tồn tại. Kết luận nên phân biệt:

- **Component/version affected**.
- **Feature/configuration affected**.
- **Reachable attack surface**.
- **Exploitability evidence trong scope**.
- **Compensating control và residual risk**.

Không gắn “scanner false positive” khi thực ra **risk reduced by policy**.

## 16. VPN, ZTNA và identity-aware access

### 16.1. Các nhầm lẫn phổ biến

- Một tài khoản vừa **MFA success** nhưng bị ZTNA policy từ chối vì **device posture** không đạt.
- VPN gateway cho phép tunnel nhưng firewall/app vẫn deny resource.
- **Account disabled** nhưng existing VPN/application session chưa bị terminate.
- App test qua **proxy hoặc secondary interface** khác path đã thiết kế.
- RADIUS/IdP logs đến SIEM muộn, khiến access decision bị ghép nhầm.

Một kết quả “user không truy cập được” có thể là **control hoạt động đúng** chứ không phải false block, nếu user đang **không đạt điều kiện**.

### 16.2. Bảng test theo identity, device và resource

| Identity | Posture | Resource | Expected | Verification |
| --- | --- | --- | --- | --- |
| Employee test role | Compliant | App nhân sự test | ALLOW | IdP + PEP + app success |
| Employee test role | Non-compliant | App nhân sự test | DENY | Posture reason + PEP deny |
| Contractor test role | Compliant | Admin-only app | DENY | Role/entitlement + PEP |
| Admin test role | Compliant | Authorized jump host | ALLOW có điều kiện | MFA/session + service health |
| Revoked test principal | Bất kỳ | Privileged resource | DENY | Token/session invalidation evidence |

### 16.3. Verify effective revoke

Disable account tại IdP có thể chặn **new login** nhưng không tự xóa **existing VPN tunnel, long-lived application cookie, OAuth token hoặc mTLS session**. Khi một bài test được báo FP vì “disabled mà vẫn có flow”:

1. Xác định **policy mục tiêu** là revoke new auth, current tunnels hay toàn bộ sessions.
2. Thu IdP change event, PEP session IDs, token/app logs.
3. Dùng **test identity có quyền** và negative/positive controls.
4. Đánh dấu **genuine control gap** nếu policy yêu cầu immediate full revocation nhưng còn đường hợp lệ cũ.
5. Không suppress alert chỉ vì IdP đã báo success.

### 16.4. Time-bound access exceptions

Một vendor được phép truy cập tạm thời có thể sinh alerts “unusual remote access”. Nếu có **approved identity, timeframe, resource scope và source posture**, có thể tuning theo **session/identity/role/time** thay vì whitelist toàn bộ VPN IP range. Thời điểm hết hạn và review owner phải được theo dõi.

## 17. DNS security: malicious domain, shared infrastructure và resolver scope

### 17.1. Những false positives thường gặp

- **Domain reputation** cũ hoặc sai khi IP/CDN được tái sử dụng.
- Domain dùng **shared hosting** với nhiều khách hàng độc lập.
- **Sinkhole/test domain** thuộc exercise được duyệt.
- Resolver trả **NXDOMAIN** do cấu hình/typo thay vì block malicious domain.
- DNS query là **prefetch/cache warmup**, không dẫn tới connection.
- **DoH/DoT/DoQ** khiến passive sensor không thấy query, dẫn tới attribution sai.
- TLS SNI/outer ECH hostname không cho biết **request hostname thật**.

### 17.2. Bằng chứng cần ghép

| Câu hỏi | Evidence |
| --- | --- |
| Query có thật từ client nào? | Authorized resolver log + NAT/endpoint mapping |
| Resolver áp policy gì? | Policy ID/category/decision, source scope |
| Domain lúc đó resolve IP nào? | Time-bounded DNS answer/TTL |
| Client có kết nối tiếp không? | Firewall/flow logs cùng time window |
| Hành động ứng dụng là gì? | Proxy/app/endpoint logs nếu cần |
| Reputation có đáng tin không? | Nguồn, timestamp, threat intel confidence |

### 17.3. Domain exception cần đúng độ chi tiết

Nếu một FQDN bị gắn nhãn sai, không mở cả **registrable parent domain/wildcard** nếu không có reason. Giới hạn **exact FQDN, destination/service, resolver policy, identity cohort và TTL**, kiểm thử lại threat-domain controls khác.

### 17.4. Không khẳng định “no DNS events” nghĩa sạch

Client có thể dùng local cache, alternate resolvers hoặc encrypted DNS được cấp phép. Một detector không thấy request có thể là **coverage issue**. Kiểm thử **resolver enforcement path và direct egress policy** trong lab.

## 18. Wireless, NAC và 802.1X: xác minh đúng trạng thái kết nối

### 18.1. Một kết nối Wi-Fi hợp lệ có thể bị chặn đúng

Thiết bị có SSID đúng nhưng chưa hoàn tất 802.1X/EAP, RADIUS trả deny do certificate không tin cậy, posture không đạt hoặc device identity chưa registered. Alert “unauthorized device” không chắc là FP chỉ vì người dùng thuộc công ty.

### 18.2. Nguồn cần kiểm tra

- **Association/authentication events** từ AP/controller.
- **RADIUS/AAA authentication & authorization results**, session/accounting IDs.
- **EAP-TLS certificate identity**, validity, issuer/trust chain phù hợp.
- **Assigned VLAN/dynamic ACL/role** và switch enforcement.
- **DHCP lease, MAC randomization và endpoint identity**.
- Packet capture/test client tại **điểm được phép**.

### 18.3. MAC address không tự chứng minh user/device

Modern clients có thể dùng **randomized MAC**, và MAC có thể bị thay đổi. Attribution cần **authenticated device/user identity và session IDs**, không whitelist MAC hàng loạt để bỏ cảnh báo.

### 18.4. Kiểm thử positive/negative

Trong lab được cấp phép:

1. Test device certificate hợp lệ, đúng role → expected VLAN/ACL.
2. Test identity không được cấp → deny rõ ở RADIUS/PEP.
3. Test expired/revoked certificate → kết quả theo policy.
4. Sau reauthentication/roaming → assigned policy vẫn đúng.
5. Guest network → không truy cập internal admin zone.

Nếu một thiết bị chỉ gặp lỗi DHCP sau authentication thành công, không tự gọi đó là **802.1X false block**; vấn đề có thể ở VLAN/DHCP/gateway routing.

## 19. Cloud network, Kubernetes và service mesh: validation đa lớp

### 19.1. Cloud security group/NACL

Một scanner thấy kết nối bị chặn nhưng cloud firewall đã “allow”. Có thể do **NACL stateless, route table, subnet association, host firewall, LB listener, security group attachment hoặc ephemeral return ports**. Cần phân biệt **control-plane declared state** và **dataplane effective decision**.

### 19.2. Kubernetes NetworkPolicy

Các policy có tính phụ thuộc vào **CNI thực thi, namespace/pod selectors, NetworkPolicy ingress/egress direction, multi-homed pods, hostNetwork và DNS egress**. Một test pod gắn label sai có thể tạo false conclusion về policy.

Kiểm thử nên ghi **cluster/namespace/Pod UID/service account/pod labels, node, NetworkPolicy version, ingress/egress path và CNI implementation**. Đừng chỉ dùng Pod IP vì nó có thể tái sử dụng.

### 19.3. Service mesh mTLS

Một flow bị từ chối có thể do **peer authentication mode, certificate identity, authorization policy, trust domain, sidecar/ambient dataplane hoặc routing**, không phải firewall. Xác định **control owner và reject reason**; tránh sửa network ACL để giải quyết lỗi identity gây mất kiểm soát.

### 19.4. False positive trong cloud asset mapping

Một public IP từng thuộc VM A nhưng được reassigned cho VM B. Scanner report chưa cập nhật có thể gắn lỗ hổng cho tài sản sai. Correlate bằng **cloud resource ID, instance lifecycle, interface ID, IP assignment time, load balancer target**.

### 19.5. Các phép thử chéo bắt buộc

| Đường | Allowed test | Denied test |
| --- | --- | --- |
| Same namespace | Service-to-service theo policy | Workload không có label/identity phù hợp |
| Cross namespace | Approved API call | Default-deny hoặc isolation policy |
| Pod → DNS | Resolver được phép | Bypass resolver ngoài policy |
| Internet → LB | Public endpoint hợp lệ | Admin/internal-only endpoint |
| Egress gateway | Approved destination | Unapproved destination/port |
| Mesh identities | Caller principal hợp lệ | Principal không được authorize |

Thử **chỉ những paths có scope**, không tạo traffic bypass tới production destinations để chứng minh coverage.

## 20. TLS, QUIC và các nguyên nhân nhầm lẫn do giới hạn quan sát

### 20.1. Vì sao detector “không thấy” không đồng nghĩa false negative?

Passive network sensor thường thấy **IP/ports, timing, packet lengths, một số handshake metadata**, không đọc được **HTTP request body/path** qua TLS/HTTP2/HTTP3 được mã hóa đúng. Nếu rule yêu cầu HTTP content nhưng sensor nằm **trước TLS termination**, đó là **visibility/design limitation**. Không tính vào recall trên cùng population với plaintext nếu detector không có khả năng quan sát đã được khai báo.

### 20.2. Các trường TLS dễ bị diễn giải sai

- **SNI** do client cung cấp, không phải hostname đã được cert validation xác nhận.
- **ECH** có thể che hostname nội bộ, outer SNI không nhất thiết là app hostname.
- **TLS 1.3 Certificate** thường được mã hóa sau ServerHello, không như TLS 1.2 full handshake.
- **ALPN offered** khác **ALPN selected**; trong TLS 1.3 selected ALPN được bảo vệ.
- **JA3/JA4-style fingerprints** là đặc trưng client/network stack, không xác nhận duy nhất malware.
- **QUIC Initial** có thể chứa metadata TLS parser quan sát được trong QUIC v1 nhưng không đọc HTTP/3 application data.

### 20.3. Tuning TLS fingerprint

Khi SDK/browser cập nhật làm fingerprint đổi:

1. So release/change record và **endpoint/process identity**.
2. Correlate destination/service, protocol version, TLS success/failure.
3. Xem liệu watchlist feature có còn khả năng phân biệt benign/malicious.
4. Đánh giá lại **cohort baseline** và false discovery rate.
5. Không whitelist một JA3 fingerprint trên toàn môi trường chỉ vì vài clients benign.
6. Giữ ability phát hiện independent indicators như **unauthorized process, destination, volume hoặc behavior**.

### 20.4. TLS interception không phải giải pháp phổ quát

Giải mã qua proxy có thể làm thay đổi trust boundary, phá **mTLS/certificate pinning**, tăng latency và tạo risk đối với data. Nếu mục tiêu là xác minh method/path/status cho ứng dụng do tổ chức sở hữu, thường nên dùng **authorized app/proxy logs** với redaction, không bật TLS inspection rộng để giảm “visibility false positive”.

## 21. Phương pháp đánh giá kết quả kiểm thử từng bước

### Bước 1 — Xác nhận finding và test objective

Tạo record gồm **test ID, expected behavior, actual observation, scope, source identity, target asset, policy/rule version, time window và người phụ trách**. Phân loại sơ bộ: possible TP, possible FP, possible FN, policy bypass, inconclusive.

### Bước 2 — Kiểm tra test setup

Đảm bảo **asset tồn tại, đúng DNS/IP/port, identity, protocol, TLS mode, proxy settings, routing, test driver version, scanner plugin và time sync**. Nếu setup sai, sửa fixture và chạy lại; không tuning security control theo kết quả nhiễu.

### Bước 3 — Đối chiếu với oracle độc lập

Tìm **approved access matrix/entitlement, source code/test contract, authenticated package/patch inventory, known test fixtures hoặc application audit**. Nếu oracle chỉ là công cụ đang xét, finding chưa đủ điều kiện kết luận FP.

### Bước 4 — Thu network + control + app evidence

Nối **flow/PCAP → firewall/NAT/PEP decision → identity/session → app result** đúng source/target/time. Đánh dấu chứng cứ thiếu và độ tin cậy, không suy user từ IP chia sẻ.

### Bước 5 — Tái hiện bằng thử nghiệm an toàn

Ưu tiên **localhost/staging/synthetic transaction**, giống protocol/route/config đang nghi. Có **benign control** và **positive malicious-labeled test fixture** đủ an toàn. Không đưa payload khai thác thật lên production nếu không có scope/approval đặc thù.

### Bước 6 — Quyết định trạng thái

Có thể là:

- **CONFIRMED_FP** khi ground truth benign và alert sai theo objective.
- **CONFIRMED_TP** khi target condition có thật và detector báo đúng.
- **CONFIRMED_FN** khi positive fixture thuộc coverage nhưng detector bỏ sót.
- **POLICY_FALSE_BLOCK / POLICY_FALSE_ALLOW** cho enforcement.
- **COVERAGE_GAP / TEST_SETUP_ERROR / INCONCLUSIVE** khi chưa đủ điều kiện.
- **RISK_ACCEPTED / COMPENSATING_CONTROL** khi finding thật nhưng risk được xử lý.

### Bước 7 — Root cause và đề xuất remediation nhỏ nhất

Tìm lỗi ở **test fixture, data mapping, asset inventory, parser, normalization, rule logic, threshold, identity grouping, policy scope hoặc app behavior**. Ưu tiên sửa **nguồn gốc** trước khi suppression.

### Bước 8 — Regression và phê duyệt

Kiểm thử lại **original benign reproducer, known-positive security fixture, adjacent rules, alternate paths và impact metrics**. Có rollback plan và owner.

### Bước 9 — Rollout theo canary nếu phù hợp

Áp dụng vào một **scope hẹp**, quan sát **FP giảm nhưng FN/recall không tăng xấu**, đồng thời theo dõi latency/availability. Đối với WAF/IPS, cần cân nhắc **detect-only/shadow** khi đổi rule nhạy cảm.

### Bước 10 — Đóng finding có bằng chứng

Ghi **classification, independent oracle, evidence refs, change ID, rule/policy before–after, test outcomes, reviewer, exception expiry và residual risks**. Không để finding biến mất khỏi ticket chỉ vì rule bị disable.

## 22. Root-cause taxonomy: vì sao một finding bị đánh sai?

### 22.1. Phân loại nguyên nhân gốc

| Nhóm | Root cause | Sửa ở đâu? |
| --- | --- | --- |
| **Test design** | Test wrong identity/path/version hoặc không có oracle | Test plan/fixture |
| **Environment** | Service down, DNS cache, route khác, proxy auto-config | Lab/staging/environment setup |
| **Sensor placement** | Missed path, asymmetric routing, SPAN packet drop | Network telemetry architecture |
| **Protocol parsing** | Unsupported HTTP2/QUIC, TLS opacity, fragmented TCP | Parser/capture configuration |
| **Log pipeline** | Duplicate, ingest lag, action field mis-map | Collector/SIEM schema |
| **Asset attribution** | NAT/Pod IP reuse, stale CMDB, shared CDN | Inventory/correlation |
| **Rule scope** | Thiếu source zone, role, method, resource class | Detection/enforcement condition |
| **Threshold/baseline** | Static threshold không xét seasonal/scheduled patterns | Rule/analytics calibration |
| **Threat intelligence** | Stale IOC, shared IP, reputation không còn đúng | IOC source/TTL/validation |
| **Application contract** | Client gửi sai content type, response normalization mismatch | Client/server API |
| **Documentation** | Policy matrix/exception chưa cập nhật | Governance/intent |
| **Actual vulnerability** | Risk thực nhưng business cho phép tạm | Risk treatment, không phải FP |

### 22.2. “Không tìm thấy hành vi độc hại” không đủ để xác nhận FP

Một IDS alert có thể xuất hiện khi endpoint logs bị xóa hoặc EDR mất kết nối. **Absence of evidence** không phải **evidence of absence**, nhất là với sensor coverage không đầy đủ. Đánh dấu **UNVERIFIED** và tạo backlog thu thập thông tin nếu chưa có oracle.

### 22.3. Nguyên nhân nhiều lớp

Một false block có thể xuất phát từ hai yếu tố kết hợp: WAF signature overly broad và ứng dụng release mới khiến field JSON chứa câu lệnh SQL mẫu. Sửa rule chỉ giải quyết một phía; cần cân nhắc **application contract, data format và WAF parsing scope** để tránh lỗi tái diễn.

### 22.4. Khi finding đã được mitigating control xử lý

Nếu scanner báo port SSH mở, nhưng truy cập chỉ qua **approved jump host + MFA + network ACL**, đây có thể là **true exposure with controls**, chứ không phải false positive. Ghi **residual risk/compensating controls** và tính hiệu lực của chúng bằng test.

## 23. Chiến lược giảm false positive nhưng không tăng false negative

### 23.1. Thứ tự ưu tiên tuning

1. **Sửa dữ liệu/fixture:** timezone, log duplication, parser và test identities.
2. **Sửa asset inventory:** decommissioned IP, owner, installed patch/version.
3. **Sửa correlation:** NAT mappings, proxy hops, session IDs, cloud resource IDs.
4. **Dùng context:** source zone, workload identity, application route, change window.
5. **Tăng specificity rule:** ràng buộc protocol state, destination resource, event sequence.
6. **Điều chỉnh threshold** dựa trên labeled baseline theo cohort và risk.
7. **Time-bound exception/suppression** cho trường hợp benign đã xác minh.
8. **Disable rule toàn bộ** chỉ khi có quyết định rủi ro chính thức và control thay thế đủ bằng chứng.

### 23.2. Tuning không đồng nghĩa im lặng

Ba cách xử lý khác nhau:

- **Detector rule correction:** rule không còn match benign nhưng vẫn match positive fixture.
- **Alert correlation/deduplication:** giảm duplicate notifications nhưng raw detections còn được lưu/truy xuất theo chính sách.
- **Scoped suppression:** một subset có bằng chứng benign được giảm mức ưu tiên hoặc không gửi paging, thường vẫn giữ telemetry/audit.

Không đánh đồng **giảm paged alerts** với **giảm số false positives thực**; đôi khi chỉ có thay đổi presentation.

### 23.3. Scoped exception có nhiều chiều

~~~yaml
exception_id: "EXC-LAB-014"
purpose: "approved synthetic backup test"
control: "lab-ids-rule-100"
source_identity: "backup-test-service-account"
source_zone: "lab-backup"
destination: "archive.lab.example"
service: "tcp/443"
time_window_utc:
  start: "2026-11-28T10:00:00Z"
  end: "2026-11-28T10:15:00Z"
action: "reduce_page_noise_not_drop_raw_telemetry"
evidence_ref: "FIND-LAB-014"
owner: "lab-security-owner"
approval: "LAB-APPROVAL-ONLY"
review_at: "2026-11-28T10:15:00Z"
rollback: "remove_scoped_exception"
~~~

Đây là **cấu trúc giả**, không phải policy engine syntax và không thay thế phê duyệt thực. Ngoại lệ cần **scope nhỏ nhất và thời hạn**, đồng thời kiểm tra có làm mù rule quan trọng cho các source/destination khác không.

### 23.4. Suppression phải còn khả năng phát hiện ngữ cảnh thay đổi

Nếu một scanner được duyệt chạy trong 10 phút, chỉ nên giảm paging cho **scan signature phù hợp với test ID/time/source**. Không whitelist mọi hoạt động security alerts từ scanner host, vì chính host đó vẫn có thể bị compromise.

### 23.5. Threshold tuning dựa trên dữ liệu có nhãn

Một hệ thống cảnh báo khi >100 requests/phút. Job backup/lab hợp lệ tạo 120/phút; tấn công giả lập có thể tạo 200/phút. Tăng threshold lên 250 sẽ triệt FP nhưng tạo FN. Thay vào đó cân nhắc:

- **Identity/service specific baselines**.
- **Rate per authenticated principal/resource**.
- **Known maintenance window with validation**.
- **Multiple independent signals** (error rate, privilege changes, unusual destinations).
- **Multi-window thresholds** và hysteresis khi phù hợp.

Chọn threshold dựa trên **precision–recall tradeoff** và khả năng ứng phó, không chỉ mục tiêu giảm alert count.

### 23.6. Dữ liệu train/tuning không được rò vào test set

Nếu chỉnh rule trên 50 examples rồi dùng lại đúng 50 examples để tuyên bố precision cải thiện trong production, đó chỉ là **fit trên known fixtures**. Dùng **separate validation/holdout cases**, cohorts/periods khác nhau và regression cho những positive attack-like fixtures mà trước đây detector thấy.

## 24. Quản lý thay đổi rule, approval, canary và rollback

### 24.1. Hồ sơ thay đổi tối thiểu

~~~text
Change ID / finding reference:
Control type: IDS / IPS / WAF / FW / PEP / scanner rule
Affected rule/policy ID and version:
Problem: observed FP / false block / mapping issue:
Independent oracle and evidence:
Root cause and proposed smallest change:
Expected benign behavior after change:
Expected malicious/forbidden behavior after change:
Coverage/risk/availability impact:
Owner and approver:
Canary scope + duration:
Positive and negative regression tests:
Rollback plan and threshold:
After-release monitoring and expiry review:
~~~

### 24.2. Change phases

~~~mermaid
flowchart LR
    A["Finding triaged"] --> B["Root cause + evidence"]
    B --> C["Scoped candidate change"]
    C --> D["Offline/staging regression"]
    D --> E{"Tests + approvals PASS?"}
    E -->|Không| F["Reject/revise; keep existing protection"]
    E -->|Có| G["Canary/shadow or staged deploy"]
    G --> H{"Recall/availability/coverage acceptable?"}
    H -->|Không| I["Rollback + investigate"]
    H -->|Có| J["Promote + observe + document"]
~~~

### 24.3. Test cases trước và sau rule change

| Nhóm | Trước | Sau kỳ vọng |
| --- | --- | --- |
| **Benign reproducer** | Gây alert false block | Không bị chặn/cảnh báo sai |
| **Known positive fixture** | Đúng rule phát hiện | **Vẫn phát hiện/chặn** |
| **Adjacent attack-like fixtures** | Không thuộc exception | Không vô tình bypass |
| **Legitimate control flow** | App healthy | Không tăng 4xx/5xx/reset/latency |
| **Alternate zone/identity** | Theo policy gốc | Không vô tình allow rộng |
| **Parser/telemetry pipeline** | Events đủ source/fields | Còn provenance/detection visibility |
| **Rollback** | Old config khôi phục được | Có procedure/test proof |

### 24.4. Canary metrics

Theo dõi:

- **FP rate/FDR** trong tập alerts có nhãn, không chỉ số cảnh báo.
- **Recall** trên positive fixtures/known indicators.
- **Block/allow decision correctness** theo access matrix.
- **Response codes, TLS failures, connection resets, p95 latency, packet drops**.
- **Sensor/parser coverage** và delivery lag.
- **Unexpected flows** hoặc policy bypass do change.

### 24.5. Đóng exception và review date

Một exception tạm thời cần có **time-to-live, owner, ticket, reason, scope, compensating control và review trigger**. Khi hết hạn, tự động thông báo/review theo workflow; **không tự kéo dài ngoại lệ vô hạn**. Nếu hệ thống dùng tự động hóa rollback, phải đảm bảo rollback không làm outage do thay đổi app contract; phê duyệt theo môi trường.

## 25. Lab localhost: đối chiếu quan sát của client với log server

Mục đích lab là **trình diễn kỹ thuật đo và giảm ngộ nhận**, không khai thác lỗ hổng. Chỉ chạy trên máy hoặc VM thuộc quyền người học, không sử dụng token thật, không đụng endpoint ngoài scope.

### 25.1. Thiết lập server thử nghiệm

Một HTTP server đơn giản có thể dùng để xác nhận **đường được phép, status 200/404 và log time**. Ví dụ dưới đây là bài tập Linux/macOS có Python đã cài trong **môi trường học của người dùng**, không phải lệnh worker chạy trong repository:

~~~bash
# Chỉ chạy trong thư mục lab riêng và máy thuộc quyền quản trị.
# Python demo server bind localhost để không mở dịch vụ ra LAN.
python3 -m http.server 18080 --bind 127.0.0.1
~~~

**Không dùng server demo này cho production.** Tùy Python/runtime, server có thể hỗ trợ HTTP/1.0 hoặc cách xử lý requests khác app thật; lab chỉ kiểm tra basic reachability.

### 25.2. Synthetic client và oracle

~~~bash
# Positive allowed request: chỉ localhost, không proxy.
curl --noproxy '*' --max-time 5 -sS -o /dev/null -w \
  'http_status=%{http_code} remote_ip=%{remote_ip}\n' \
  'http://127.0.0.1:18080/'

# Negative app-level resource case: đường dẫn không tồn tại.
curl --noproxy '*' --max-time 5 -sS -o /dev/null -w \
  'http_status=%{http_code} remote_ip=%{remote_ip}\n' \
  'http://127.0.0.1:18080/does-not-exist-lab'
~~~

Kỳ vọng: root thông thường trả **200** nếu directory phục vụ đúng; đường không tồn tại trả **404**. **404 là response ứng dụng**, không phải firewall deny. Nếu server chưa chạy, cả hai có thể fail; điều đó không chứng minh segmentation.

### 25.3. Capture tối thiểu nếu có quyền

~~~bash
# Linux loopback lab only; dừng bằng Ctrl+C khi đủ dữ liệu.
sudo tcpdump -i lo -nn -s 0 -w lab-security-test.pcap \
  'tcp port 18080 and host 127.0.0.1'
~~~

PCAP có thể chứa full URL/content; trong lab dùng dữ liệu giả. Không thu traffic của users khác. macOS dùng **lo0**; Windows cần adapter capture tương ứng. Nếu không có quyền capture, dùng **curl output và server logs** là đủ cho phần đánh giá này.

### 25.4. Đọc bằng TShark (nếu đã có PCAP)

~~~bash
tshark -r lab-security-test.pcap -Y 'http.request' -T fields \
  -e frame.time_epoch \
  -e tcp.stream \
  -e http.request.method \
  -e http.request.uri
~~~

Nếu HTTP dissector không tự nhận port 18080, cần **Decode As** phù hợp trong Wireshark/TShark. Không nhìn thấy \`http.request\` **chưa chứng minh request không tồn tại**; có thể cần TCP reassembly hoặc parser configuration. Lab không được dùng để đo recall của một IDS production khác sensor/capture point.

### 25.5. Chấm kết quả đúng

| Observation | Kết luận được phép |
| --- | --- |
| Curl root 200, server log có GET | Application endpoint có trả response cho test trong scope |
| Curl missing path 404 | HTTP request tới app, resource không tồn tại theo server |
| Curl connection refused, server stopped | Không có listener; **không chứng minh FW deny** |
| Curl timeout, không có sensor data | **Inconclusive**, cần route/PEP/app status |
| PCAP có TCP retransmission | Không tự là hai application attempts |
| Server log 200 nhưng SIEM không thấy | Kiểm tra parser/log collection/coverage, không kết luận alert FP |

### 25.6. Dọn môi trường

Dừng server và capture. Xử lý PCAP/test logs theo chính sách lab; không để capture chạy rộng, không đăng payload chứa cookie/token lên ticket. **Bài không chạy mã trong workspace của dự án**.

## 26. Case study 1 — Firewall timeout bị coi nhầm là segmentation PASS

### 26.1. Bối cảnh giả định

Đội QA cần chứng minh **Guest Wi-Fi không được truy cập DB subnet**. Một test client gửi TCP connection tới DB port 5432 và nhận timeout. Bảng test được đánh dấu **PASS: firewall blocked** mà không có evidence bổ sung.

### 26.2. Điều tra

| Câu hỏi | Bằng chứng cần |
| --- | --- |
| DB server có chạy không? | Service health từ allowed zone |
| Route có tồn tại không? | Authorized routing/PEP observation |
| DNS có trỏ đúng DB không? | Time-bounded resolver answer |
| Guest source có nằm đúng VLAN/SSID không? | NAC/WLC/endpoint address evidence |
| Firewall có thực sự deny? | Rule hit/flow deny trong đúng time/5-tuple |
| Host firewall có chặn không? | OS audit/config trên host được phép |
| Có IPv6 hoặc đường public LB khác không? | Network path inventory/scope test |

### 26.3. Ground truth

Trong bài lab, team nhận ra DB service **đang dừng**, nên mọi source đều timeout. Kết quả ban đầu **không đủ điều kiện để kết luận segmentation PASS**. Sau khi DB lab được khởi động, source thuộc app tier kết nối thành công; guest source bị PEP deny có log.

### 26.4. Phân loại

- Bản thử thứ nhất: **INCONCLUSIVE / TEST_SETUP_ERROR**.
- Bản thử thứ hai: **EXPECTED_DENY_CONFIRMED_IN_SCOPE**.
- Không ghi bản thử đầu là **TP** vì detector ground truth chưa được xác định.

**Bài học:** đối với firewall/segmentation, positive control về service health là bắt buộc để không nhầm một sự cố availability thành security enforcement.

## 27. Case study 2 — IDS cảnh báo job backup được phép

### 27.1. Tình huống

IDS phát cảnh báo nghi exfiltration do **large outbound bytes + periodic pattern** từ một host trong lab. App owner xác nhận cùng khoảng thời gian có backup job mới được duyệt, truyền dữ liệu test tới approved archive.

### 27.2. Không kết luận FP chỉ từ lời giải thích

Thu:

1. **Approved change/job record** cùng time window.
2. Authenticated **service account** và process identity.
3. Destination IP/FQDN/port đúng service backup.
4. Flow byte counts với packet drop/sampling caveat.
5. Job log chứng minh content là **synthetic/test data**.
6. IDS rule ID/version và matched features.
7. Egress policy/credential access không có anomalies khác.

### 27.3. Kết quả

Nếu evidence xác nhận benign condition của test, alert có thể là **CONFIRMED_FP** theo mục tiêu rule “unauthorized transfer”. Nhưng quy tắc phát hiện **unexpected outbound volume** có thể vẫn đúng về việc có traffic lớn; chỉ phần **risk classification** bị sai. Phải ghi đúng objective.

### 27.4. Tuning an toàn

- Giữ **flow telemetry** và detect volume bất thường bên ngoài backup job.
- Scoped exception theo **service identity, destination, schedule, task ID**.
- Rule vẫn kích hoạt đối với **unknown process/destination/source zone**.
- Negative regression với synthetic unauthorized-transfer pattern trong lab.
- Có **TTL và owner** cho exception khi backup architecture thay đổi.

### 27.5. Không nên làm

Không whitelist toàn bộ host hoặc tắt rule exfiltration ở mạng production vì host chạy backup hợp lệ. Nếu chính backup host bị xâm nhập, suppression rộng sẽ tạo blind spot.

**Bài học:** một alert FP theo use case cụ thể không khiến tất cả tín hiệu volume/network behavior trở nên vô nghĩa.

## 28. Case study 3 — Scanner báo CVE từ banner phiên bản đã backport

### 28.1. Bối cảnh

Scanner phát **HIGH severity** cho web service với phiên bản upstream có CVE. System administrator nói phiên bản không đổi vì distribution đã backport patch.

### 28.2. Evidence review

| Nguồn | Điều cần xác minh |
| --- | --- |
| Scan plugin | CVE ID, detection method, banner/version assumptions |
| Authenticated package inventory | Exact package release/build + architecture |
| Vendor security advisory | Bản vá đã được backport trong release nào |
| Deployed runtime/service | Binary thật đang phục vụ, không chỉ package installed |
| Configuration | Feature/affected code path bật hay tắt |
| Reverse proxy/CDN | Banner thuộc origin hay edge |
| Safe staging verification | Kết quả không phá hoại nếu cần |

### 28.3. Ba kết luận khác nhau

- **CONFIRMED_FP:** plugin đưa ra claim affected nhưng installed/deployed package theo vendor chính xác không thuộc affected build/condition.
- **CONFIRMED_VULNERABILITY_MITIGATED:** thành phần còn affected nhưng firewall/application control làm giảm khả năng khai thác.
- **INCONCLUSIVE:** không xác minh được binary/patch/runtime hoặc scanner unauthenticated thiếu quyền.

### 28.4. Khắc phục

Gửi **vendor package/build evidence và plugin reference** để scanner sửa mapping nếu hợp lệ; cập nhật **exception chính xác theo asset + CVE + expiry** trong khi chờ plugin update nếu policy cho phép. Không suppress mọi findings cho cùng host, và không tắt authenticated scan chỉ để giảm báo cáo.

**Bài học:** phân biệt **độ chính xác detection** và **risk treatment**; banner không phải ground truth duy nhất.

## 29. Case study 4 — WAF chặn nội dung hỗ trợ lập trình

### 29.1. Bối cảnh

Một ứng dụng knowledge-base cho phép người dùng được xác thực gửi ví dụ SQL như **“SELECT …”** trong bài học. WAF phát một signature SQLi và trả 403. Người dùng gọi đây là FP.

### 29.2. Các câu hỏi trước khi kết luận

- Request có nằm trong **endpoint/content-type/role** được cho phép nhập nội dung mã không?
- WAF parser có chọn **matched parameter** đúng không?
- Ứng dụng lưu/render nội dung đó như dữ liệu hay có nguy cơ nội suy vào câu lệnh SQL?
- Có **backend authorization** trước khi tạo content không?
- Có thể tạo **benign synthetic fixture** có cùng cấu trúc nhưng không chứa dữ liệu thật không?
- Rule cũng bảo vệ **API endpoints khác** không?

### 29.3. Thực hành đúng

1. Dùng ticket/test identity có quyền.
2. Tái hiện trong **staging** với synthetic SQL text không thực thi.
3. Ghép **WAF transaction ID, app route, response và rule metadata**.
4. Xác nhận request là benign theo ứng dụng và WAF block ngoài kỳ vọng.
5. Tạo điều chỉnh **chỉ đối với matched variable/route và rule ID** theo policy.
6. Kiểm thử lại **benign fixture** phải pass và **malicious-labeled synthetic fixture** vẫn bị phát hiện trong môi trường thử.
7. Monitor sau rollout, không log full body của người dùng.

### 29.4. Anti-pattern

Tắt mọi nhóm SQL injection rules cho **api.example** hoặc bypass WAF toàn bộ **/api/**. Một exception quá rộng có thể biến **FP fix** thành **FN risk** trên các endpoints khác.

**Bài học:** chính xác hóa rule theo **ngữ cảnh ứng dụng**, không loại bỏ lớp kiểm soát chung.

## 30. Case study 5 — ZTNA false block hay posture deny đúng?

### 30.1. Bối cảnh

Một nhân viên test role có entitlement truy cập app nhưng bị ZTNA deny. Helpdesk đánh dấu false positive vì user “đúng phòng ban”.

### 30.2. Evidence

ZTA policy đòi **role + device posture + MFA + application resource tag**. Kiểm tra:

- Authenticated user/role tại IdP.
- Actual **device certificate, compliance, EDR state**.
- ZTNA session/PEP policy decision.
- Current app entitlement/resource owner.
- Thời điểm **certificate expiry, posture refresh hoặc SSO token**.
- App response nếu PEP cho request đi qua.

### 30.3. Phân loại

Nếu device **không đạt posture**, deny là **expected control**, không phải FP. Nếu posture đã đạt nhưng PEP cache stale khiến deny sai, đó có thể là **policy false block** hoặc **sync error** cần fix.

### 30.4. Tuning an toàn

Không bỏ toàn bộ posture requirement cho cả nhóm người dùng. Sửa **device enrollment, posture synchronization, cache/refresh logic** hoặc cấp exception hẹp được phê duyệt với TTL và compensating controls nếu cần phục vụ kinh doanh.

### 30.5. Regression

- Compliant test device + authorized role → ALLOW.
- Non-compliant test device + same role → DENY.
- Wrong role + compliant device → DENY.
- Revoked account/token → DENY theo chính sách.
- Alternate path không đi qua PEP → bị kiểm soát hoặc được báo coverage gap.

**Bài học:** phải kiểm thử **toàn bộ điều kiện của policy**, không chỉ tên user.

## 31. Case study 6 — Giảm FP bằng ngưỡng cao tạo false negative

### 31.1. Bối cảnh

NDR có rule phát cảnh báo khi một test workload tạo hơn **100 kết nối thất bại mỗi phút**. Một monitoring job hợp lệ gây 120 kết nối thất bại/phút do API thử health endpoint, dẫn tới alerts sai. Team tăng threshold lên 300 để “hết noise”.

### 31.2. Kết quả thử nghiệm giả định

| Scenario | Connections thất bại/phút | Trước (ngưỡng 100) | Sau (ngưỡng 300) |
| --- | ---: | --- | --- |
| Scheduled health check benign | 120 | FP alert | Không alert |
| Lab suspicious scan fixture | 180 | TP alert | **FN** |
| Other aggressive fixture | 350 | TP alert | TP alert |

**Lưu ý:** các con số là tình huống giả, không đại diện cho ngưỡng an toàn chung. Ngưỡng chỉ minh họa tradeoff.

### 31.3. Phân tích

Thay đổi rule giảm FP cho monitoring job nhưng mất một positive detection case, do đó **không đạt acceptance** nếu scanner fixture 180/phút là threat scenario bắt buộc phát hiện.

### 31.4. Cách cải thiện

1. Phân nhóm theo **authenticated workload/process, destination và maintenance window**.
2. Phân biệt **known monitored endpoint** với nhiều unauthenticated destinations.
3. Dùng **multi-signal detector**: số destinations, error ratio, process lineage, identity changes.
4. Tạo **exception hẹp/short TTL**, không globally increase threshold vô căn cứ.
5. Chạy lại **labeled regression set và production shadow monitoring**.
6. Theo dõi **FN risk** cùng với noise reduction trước khi release.

### 31.5. Bài học

Một biện pháp “giảm số alert FP” chỉ thành công nếu **mức phát hiện thật và khả năng kiểm soát rủi ro vẫn nằm trong ngưỡng chấp nhận**.

## 32. Bài thực hành offline: đánh giá một tập kết quả có nhãn

Bài thực hành không kết nối mạng, không quét và không đổi firewall/WAF/IDS. Người học dùng bảng **synthetic labeled fixtures** để xác định confusion matrix, đề xuất tuning và xem tuning có làm tăng FN hay không.

### 32.1. Định nghĩa test objective

Giả định detector D có nhiệm vụ phát hiện **một nhóm hành vi mạng không được cho phép** trên các **test flows có nhãn rõ**. “Actual positive” nghĩa mẫu nằm trong bộ **approved positive security fixtures** do lab tạo; “actual negative” nghĩa mẫu thuộc **benign fixtures** do lab kiểm soát. Không suy diễn các nhãn này sang traffic người dùng thực.

### 32.2. Dữ liệu giả lập

| Test ID | Nhãn ground truth | Detector có alert? | Kết quả |
| --- | --- | --- | --- |
| LAB-01 | Positive | Có | TP |
| LAB-02 | Positive | Có | TP |
| LAB-03 | Positive | Có | TP |
| LAB-04 | Positive | Có | TP |
| LAB-05 | Positive | Có | TP |
| LAB-06 | Positive | Có | TP |
| LAB-07 | Positive | Không | FN |
| LAB-08 | Positive | Không | FN |
| LAB-09 | Negative | Có | FP |
| LAB-10 | Negative | Có | FP |
| LAB-11 | Negative | Có | FP |
| LAB-12 | Negative | Không | TN |
| LAB-13 | Negative | Không | TN |
| LAB-14 | Negative | Không | TN |
| LAB-15 | Negative | Không | TN |
| LAB-16 | Negative | Không | TN |
| LAB-17 | Negative | Không | TN |
| LAB-18 | Negative | Không | TN |
| LAB-19 | Negative | Không | TN |
| LAB-20 | Negative | Không | TN |

Giả sử **20 mẫu đều đã thực sự đi qua sensor, có parser hỗ trợ và event delivery được kiểm tra**. Nếu thiếu điều kiện này, phải phân loại coverage/inconclusive trước khi tính metric.

### 32.3. Tính toán

~~~text
TP = 6
FP = 3
FN = 2
TN = 9

Precision   = 6 / (6 + 3)   = 66.7%
Recall      = 6 / (6 + 2)   = 75.0%
Specificity = 9 / (9 + 3)   = 75.0%
FPR         = 3 / (9 + 3)   = 25.0%
FDR         = 3 / (6 + 3)   = 33.3%
F1          = 12 / (12+3+2) = 70.6%
Accuracy    = (6 + 9) / 20  = 75.0%
~~~

### 32.4. Đánh giá một đề xuất tuning

Một kỹ sư đề xuất thay đổi threshold:

- LAB-09, LAB-10, LAB-11 hết alert (giảm 3 FP).
- Nhưng LAB-04, LAB-05 cũng hết alert (tạo thêm 2 FN).

Kết quả sau tuning:

~~~text
TP = 4
FP = 0
FN = 4
TN = 12

Precision = 4/(4+0) = 100%
Recall    = 4/(4+4) = 50%
FPR       = 0/(0+12) = 0%
F1        = 8/(8+0+4) = 66.7%
~~~

**Precision tăng nhưng recall giảm từ 75% xuống 50%.** Nếu mục tiêu detection yêu cầu duy trì phát hiện các positive fixtures LAB-04/LAB-05, change **không đạt**. Số FP bằng 0 không tự chứng minh cải thiện an toàn.

### 32.5. Tuning an toàn hơn

Giả định LAB-09–11 cùng một **approved test service account** chạy vào cửa sổ bảo trì. Có thể tạo **rule context** cho test account/destination/time đã được xác minh, thay vì tăng threshold toàn bộ. Sau đó:

1. Chạy lại cả 20 fixtures.
2. Thêm **holdout fixtures** với benign clients khác và positive scenarios tương tự.
3. Kiểm tra **rule vẫn match positive clients** ngoài exception.
4. Kiểm tra bản ghi vẫn giữ **raw telemetry** cho audit.
5. Đặt **exception expiry và review owner**.

### 32.6. Thêm các samples chưa xác minh

Giả sử có 5 production alerts không có ground truth vì EDR offline. Chúng **không được thêm vào FP**. Ghi:

~~~json
{
  "dataset": "synthetic-detector-lab-014",
  "labeled_cases": 20,
  "unverified_cases": 5,
  "tp": 6,
  "fp": 3,
  "fn": 2,
  "tn": 9,
  "ground_truth_source": "approved_synthetic_test_fixtures",
  "production_claim": "not_supported",
  "classification_version": "v1"
}
~~~

Nếu cần báo số liệu ngoài lab, phải nêu rõ **population, sampling strategy, time window, labeling coverage và confidence interval** nếu thích hợp, không trộn test fixtures với unverified production alerts.

## 33. Ma trận kiểm thử positive, negative và kiểm tra false positive

Các test dưới đây được thiết kế cho **staging/lab hoặc production window đã có ủy quyền**, không tự tạo traffic trái scope.

| Test | Setup có kiểm soát | Expected outcome |
| --- | --- | --- |
| **T01 – Firewall allow path** | Approved source → app service | ALLOW + app health |
| **T02 – Firewall deny path** | Guest lab → internal DB | PEP DENY, app listener positive control |
| **T03 – Server down** | Stop local lab server | INCONCLUSIVE cho segmentation, không ghi FW deny |
| **T04 – Wrong DNS target** | Synthetic stale DNS mapping | Test setup error phát hiện |
| **T05 – Pre-NAT/post-NAT** | Known translation và 5-tuple | Không gán nhầm source |
| **T06 – IPv4/IPv6 paths** | Approved dual-stack lab | Policy đúng từng address family |
| **T07 – Stateful return traffic** | Allowed established flow | Không suy inbound new session allowed |
| **T08 – IDS positive fixture** | Labeled benign-safe signature test | TP/detection expected |
| **T09 – IDS benign fixture** | Allowed backup/monitoring traffic | Không tạo FP theo objective |
| **T10 – IDS packet loss** | Controlled sensor gap | Đánh dấu coverage, không gán TN |
| **T11 – SIEM duplicate events** | Collector replay cùng source ID | Dedup analytics, raw refs retained |
| **T12 – Time skew** | Source clock offset giả | UTC normalize và correlation đúng |
| **T13 – TLS opacity** | HTTPS lab no decryption | Không tuyên bố passive sensor thấy HTTP body |
| **T14 – TLS fingerprint drift** | SDK/browser release fixture | FP review theo cohort/version |
| **T15 – ECH hostname visibility** | Lab ECH-capable | Outer/inner provenance đúng |
| **T16 – WAF benign code example** | Approved content endpoint fixture | Benign request không bị block sai |
| **T17 – WAF positive fixture** | Safe labeled malicious-like fixture | Rule vẫn phát hiện sau tuning |
| **T18 – WAF scope change** | Adjacent endpoint | Không vô tình bypass toàn domain |
| **T19 – Rate limit by identity** | Synthetic accounts ở threshold khác | Per-principal policy đúng |
| **T20 – Vulnerability backport** | Authenticated package + advisory | Không gắn CVE sai từ banner |
| **T21 – Scanner auth failure** | Test credentials không hợp lệ | Coverage/inconclusive, không gán TN |
| **T22 – CDN shared IP** | Two lab hostnames same IP | Không suy IOC chỉ từ IP |
| **T23 – Asset decommission** | Old IP assigned new asset | Report owner và target đúng |
| **T24 – VPN new login deny** | Revoked test user | IdP/PEP deny đúng |
| **T25 – VPN existing session** | Authorized lab active session | Revoke semantics kiểm chứng |
| **T26 – ZTNA compliant role** | Approved identity/posture | ALLOW test application |
| **T27 – ZTNA non-compliant** | Same role, failing posture | DENY |
| **T28 – ZTNA wrong role** | Compliant device but denied entitlement | DENY |
| **T29 – DNS protective block** | Synthetic test-domain policy | Resolver policy outcome đúng |
| **T30 – DNS cache behavior** | Cache hit/no new query | Không kết luận “no traffic” |
| **T31 – NAC/802.1X compliant** | Test cert và device identity | Correct VLAN/ACL |
| **T32 – NAC failed cert** | Expired lab test cert | Reject có reason đúng |
| **T33 – Kubernetes labels** | Correct vs wrong pod labels | NetworkPolicy đúng workload |
| **T34 – Kubernetes egress** | Approved vs nonapproved lab target | Correct allow/deny ở CNI |
| **T35 – Service mesh principal** | Known workload identity | AuthZ policy đúng, không nhầm IP |
| **T36 – Cloud SG effective policy** | SG/NACL/route attachment | Dataplane outcome phù hợp |
| **T37 – Suppression scope** | Exception chỉ test service | Other cohorts vẫn được phát hiện |
| **T38 – Suppression expiry** | Simulation sau TTL | Rule/alert behavior được khôi phục |
| **T39 – Canary regression** | Before/after labeled fixtures | FP giảm, FN không vượt acceptance |
| **T40 – Rollback** | Simulated policy rollback | Original protections và app health trở lại |
| **T41 – Pipeline outage** | Controlled collector stop | Coverage alert, không báo 0 risk |
| **T42 – Disputed evidence** | App/proxy logs không khớp | UNVERIFIED, mở review |
| **T43 – Risk accepted ≠ FP** | True exposure có exception | Risk accepted với owner/expiry |
| **T44 – Privacy** | Synthetic token trong WAF log | Redaction, limited access, retention |
| **T45 – Negative and positive controls** | PEP deny test + allowed service test | Cả security và availability đều PASS |

### 33.1. Mẫu chấm test

~~~text
Test ID / objective / expected decision:
Authorized scope / environment / source identity:
Fixture version and owner:
Target resource/port/protocol/route:
Applied rule/policy/scanner version:
Execution time UTC / clock quality:
Client observation:
Network/PEP/IDS/WAF/IdP/app evidence:
Ground truth source independent from detector:
Coverage and sensor health:
Classification: TP/FP/FN/TN or policy outcome/INCONCLUSIVE:
Before/after change:
Risk/availability impact:
Reviewer/approval:
Rollback/exception and next revalidation:
~~~

### 33.2. Mỗi regression cần giữ cả trường hợp đúng và sai

Nếu thay đổi để giảm 10 FP, phải có **tập positive fixtures mà trước đây detector phát hiện**, và ít nhất một số trường hợp gần ranh giới của exception. Chỉ test lại benign cases sẽ **không nhìn thấy FN mới**.

### 33.3. “Không có alert” chỉ có nghĩa sau khi xác minh đường dữ liệu

Khi detector không báo, phải xác nhận **test traffic đã đi qua PEP/sensor, parser hiểu protocol, rule enabled và alert pipeline hoạt động**. Nếu sensor outage, test nên **FAIL/INCONCLUSIVE về coverage**, không chấm TN.

## 34. Runbook triage và adjudication false positive

### Giai đoạn 1 — Tiếp nhận và bảo toàn finding

1. Ghi **finding ID, tool/rule/plugin version, asset, affected source zone, risk label và thời gian UTC**.
2. Xác nhận **test authorization và scope**.
3. Lưu **raw event reference**, parser version, sensor/vantage, evidence retention.
4. Thu **description của user/app owner** như hypothesis, không coi là oracle cuối.
5. Phân loại sơ bộ **TP candidate, FP candidate, FN candidate, policy outcome mismatch hoặc inconclusive**.

### Giai đoạn 2 — Điều tra nguồn và đường đi

1. Kiểm tra **identity, target hostname/IP, protocol, service port, time window**.
2. Xem **NAT/proxy/VPN/mesh/LB** có đổi 5-tuple hoặc actor attribution không.
3. Kiểm tra **sensor capture health, TLS visibility, packet loss, sample rate, parser mapping và ingest latency**.
4. Tìm **applied policy/rule decision** ở đúng enforcement point.
5. Đối chiếu **app/business outcome** nếu finding claim successful operation.

### Giai đoạn 3 — Ground truth và tái hiện

1. Xác định **test oracle độc lập**.
2. Tạo/reuse **synthetic fixture** tương đương tại lab/staging.
3. Có positive/negative controls, không dùng traffic production nhạy cảm.
4. Nếu phép thử không thể tái hiện, ghi **inconclusive hoặc environment-dependent**, không ép FP.
5. Gắn nhãn có **reviewer**, evidence refs, confidence và severity.

### Giai đoạn 4 — Quyết định remediation

1. Sửa **test configuration, asset mapping, parser hoặc rule root cause**, nếu có.
2. Nếu cần exception, giới hạn **identity, zone, resource, rule, time, data type**.
3. Đánh giá **FP giảm thế nào, FN tăng không, control bypass risk ra sao**.
4. Lập **change ID, approval, canary và rollback**.
5. Không dùng “suppress all” hoặc global allow để chốt ticket nhanh.

### Giai đoạn 5 — Kiểm thử lại và triển khai

1. Replay **original benign fixture**.
2. Replay **positive security fixtures/adjacent scenarios**.
3. Test **allowed legitimate flows và denied forbidden paths**.
4. Kiểm tra **availability/latency/resets** của ứng dụng.
5. Kiểm tra **telemetry, parser và audit trail** vẫn còn.
6. Rollback khi **unexpected allow/FN/critical outage** hoặc không đạt acceptance.

### Giai đoạn 6 — Kết luận và theo dõi

1. Cập nhật finding trạng thái **confirmed FP/TP/FN/policy failure/risk accepted/inconclusive**.
2. Ghi **before/after metrics** có population/labeling rõ.
3. Liên kết **rule change, approval, regression test IDs, rollback plan và exception TTL**.
4. Đưa detector/watchlist vào **revalidation cadence**.
5. Nếu phát hiện FN hoặc coverage gap, mở **finding riêng** thay vì giấu trong FP closure.
6. Bảo vệ raw PCAP, credentials và user data theo data-handling policy.

## 35. Những nhầm lẫn thường gặp khi loại bỏ false positive

1. **“Có alert là có tấn công thành công.”** Alert có thể chỉ là rule match, attempt hoặc benign fixture.
2. **“Không có alert nghĩa an toàn.”** Có thể là FN, coverage gap hoặc pipeline loss.
3. **“User nói hợp lệ nên chắc là FP.”** Cần oracle và evidence độc lập.
4. **“Scanner báo CVE là chắc chắn exploit được.”** Detection method và affected conditions cần xác minh.
5. **“Admin nói đã patch nên scanner sai.”** Phải kiểm tra deployed binary/vendor backport/config.
6. **“Risk accepted nghĩa false positive.”** Finding thật với exception không phải FP.
7. **“Firewall deny luôn tốt.”** Có thể false block traffic hợp lệ.
8. **“Firewall allow luôn xấu.”** Allowed path có thể đúng access matrix.
9. **“TCP timeout chứng minh firewall deny.”** Service down, DNS, route/return path cũng gây timeout.
10. **“Được TCP SYN-ACK nghĩa app authorization thành công.”** Network reachability khác app auth.
11. **“Một positive control đủ chứng minh segmentation.”** Cần kiểm tra forbidden paths.
12. **“Một negative control đủ chứng minh an toàn.”** Có thể app ngừng hoạt động toàn bộ.
13. **“Cùng IP nghĩa cùng user.”** NAT, VPN, proxy và Pod IP reuse có thể gây nhầm.
14. **“X-Forwarded-For là bằng chứng identity.”** Header client-controlled khi không có trusted chain.
15. **“DNS query chứng minh người dùng tải file.”** Query không chứng minh app request/content.
16. **“TLS SNI chứng minh URL/path.”** SNI không phải HTTP request target.
17. **“SNI vắng nghĩa client cố ý ẩn tấn công.”** Có ECH, no-SNI, missing packets, midstream.
18. **“JA3/JA4 fingerprint là tên malware.”** Nhiều software chia sẻ và thay đổi fingerprints.
19. **“Tất cả UDP/443 là HTTP/3.”** Có thể là giao thức khác, cần protocol evidence.
20. **“HTTP/3/QUIC request path đọc được từ passive PCAP.”** Encrypted content không quan sát được thông thường.
21. **“Không thấy TLS 1.3 certificate nghĩa cert sai.”** TLS 1.3 mã hóa Certificate message.
22. **“Bật TLS interception luôn giải quyết false positive.”** Thêm trust/privacy/compatibility risk.
23. **“Rule match hai lần nghĩa hai tấn công.”** Duplicate, retransmission và retries phải phân biệt.
24. **“SIEM alert time là event time.”** Ingest delay và time skew có thể đảo thứ tự.
25. **“Một scanner report luôn đúng asset owner.”** IP/CDN/VM/container ownership có thể đổi.
26. **“Scanner không scan được nghĩa không có CVE.”** Đây là coverage gap/inconclusive.
27. **“Rule bị false positive một lần thì mọi alert cùng rule sai.”** Phải đánh giá cohort/context.
28. **“Giảm 90% alerts chứng minh precision tăng.”** Có thể chỉ suppress, không đổi ground truth.
29. **“FPR là tỷ lệ alerts sai.”** Tỷ lệ alerts sai là FDR khi đã có nhãn đầy đủ.
30. **“Accuracy cao đồng nghĩa detector tốt.”** Base-rate imbalance có thể che recall thấp.
31. **“Precision 100% nên detector tối ưu.”** Detector có thể bỏ sót phần lớn actual positives.
32. **“Không đo được TN thì cứ coi mọi no-alert flow là TN.”** Cần labeled negative population.
33. **“UNKNOWN có thể tính là FP để đóng ticket.”** Không đủ evidence thì phải để inconclusive.
34. **“Coverage gap chính là FN của rule.”** Phải tách sensor path với rule-level detection.
35. **“Mọi false block chỉ cần mở firewall.”** Cần tìm đúng control: app/IdP/PEP/route/posture.
36. **“Mở ANY/ANY giải quyết false block an toàn.”** Có thể tạo policy bypass nghiêm trọng.
37. **“Có thể whitelist toàn bộ IP scanner sau một test hợp lệ.”** Scanner host có thể bị dùng sai mục đích.
38. **“Ngưỡng càng cao càng ít false positives mà không hại detection.”** Có thể tăng FN.
39. **“Tuning trên tập test rồi báo cùng tập đó là hiệu năng production.”** Overfitting/selection bias.
40. **“Rule update áp trên control plane nghĩa dataplane đổi ngay.”** Cần effectiveness test.
41. **“Không cần canary hoặc rollback cho IPS/WAF.”** False block có thể gây outage.
42. **“Một WAF 403 nghĩa backend bị lỗi quyền.”** WAF/proxy có thể chặn trước app.
43. **“Code SQL trong nội dung là SQL injection chắc chắn.”** Context và xử lý ứng dụng quyết định.
44. **“CORS success nghĩa backend auth đúng.”** CORS không thay server-side authorization.
45. **“Đổi tên rule thành benign là đủ.”** Phải có evidence và root-cause record.
46. **“Chỉ giữ alert count, không cần raw event IDs.”** Không truy nguyên được khi audit.
47. **“Rule suppression làm event không còn quan trọng.”** Raw telemetry vẫn hữu ích khi có incident mới.
48. **“Thiết bị có Wi-Fi SSID đúng là được phép vào LAN.”** 802.1X, posture và VLAN enforcement khác nhau.
49. **“Một Pod IP đủ xác định workload.”** Pod UID/service account và lifecycle mới đáng tin.
50. **“Cloud security group allow đủ chứng minh kết nối success.”** Route/NACL/host firewall/LB có thể block.
51. **“Test fail do app down là policy deny PASS.”** Cần service positive control.
52. **“Phát hiện sai một lần có thể đóng mọi duplicate findings về sau.”** Cần xem thời gian, asset và rule version.
53. **“Bỏ FP là xóa lịch sử alert.”** Cần audit trail/adjudication history.
54. **“Một exception không cần ngày hết hạn.”** Long-lived suppression tạo blind spot.
55. **“Số lượng false positive càng thấp càng tốt với bất kỳ giá nào.”** Phải cân đối FN, risk, availability.
56. **“Chỉ cần test đường IPv4.”** IPv6/alternate route có thể nằm ngoài coverage.
57. **“Một proxy log tự chứng minh toàn traffic đều đi qua proxy.”** Direct bypass phải được kiểm tra.
58. **“Có port scan authorized nghĩa scanner alerts vô hại toàn bộ.”** Phân loại đúng test window/identity.
59. **“Một log source đủ cho ground truth mọi tầng.”** Network, identity và application có mục tiêu khác nhau.
60. **“Có thể đưa full PCAP hoặc token thật vào báo cáo FP.”** Cần data minimization/redaction.

## 36. Bài tập vận dụng và gợi ý đáp án

### Bài 1 — Phân loại FP/TP/FN/TN

Detector phát alert cho 4 positive lab fixtures và 2 benign fixtures; bỏ sót 1 positive và im lặng với 7 benign. Tính confusion matrix.

**Gợi ý:** TP=4, FP=2, FN=1, TN=7. Precision=4/6≈66,7%; recall=4/5=80%; FPR=2/9≈22,2%.

### Bài 2 — FPR hay tỷ lệ alerts sai?

Trong tập có nhãn, 100 benign test flows, 5 được alert. Tổng alerts có 20, trong đó 5 benign. FPR và FDR là bao nhiêu?

**Gợi ý:** FPR=5/100=5%; FDR=5/20=25%; precision=75% nếu 15 còn lại đúng là actual positives.

### Bài 3 — Điều gì chưa đủ để gọi false positive?

Một IDS alert trùng với giờ backup; analyst không có job log hoặc authenticated process evidence. Có nên đóng FP ngay?

**Gợi ý:** không. Backup là giả thuyết; cần **job approval, process identity, destination, time và rule outcome**. Nếu thiếu, ghi UNVERIFIED.

### Bài 4 — Firewall DENY nhưng ứng dụng chết

Guest network test không connect DB; allowed app tier cũng không connect. Cần ghi kết quả nào?

**Gợi ý:** **INCONCLUSIVE**, kiểm tra DB listener/app health và PEP event trước khi nói segmentation pass.

### Bài 5 — Authenticated scan và banner

Scanner báo CVE do phiên bản header, OS vendor advisory nói bản vá đã backport. Cần thêm gì?

**Gợi ý:** installed/deployed package release + binary/config + affected conditions + plugin method. Không dựa vào lời khẳng định chung.

### Bài 6 — False positive hay risk accepted?

SSH mở với jump host được phép, scanner xác nhận port reachable. Chủ hệ thống đã phê duyệt access và MFA.

**Gợi ý:** kết quả **reachability là đúng**. Risk có thể accepted/mitigated theo policy; không tự gọi scanner FP.

### Bài 7 — Tuning threshold

Một rule phát hiện 10/10 lab attack fixtures và báo sai 4 benign jobs. Sau khi tăng threshold, chỉ còn 1 FP nhưng mất 3 TP. Có đủ gọi thành công?

**Gợi ý:** chưa. Recall giảm 100% xuống 70%; cần risk/acceptance review và context-based tuning để tránh FN.

### Bài 8 — WAF 403

Một POST hợp lệ bị trả 403. App không ghi request. Cần tìm nguồn response nào?

**Gợi ý:** WAF/reverse proxy/gateway transaction ID và policy action. Không tự đổ lỗi app authorization.

### Bài 9 — VPN user với device không compliant

Tài khoản đúng role nhưng EDR posture không đạt, ZTNA deny. Helpdesk gọi FP.

**Gợi ý:** deny có thể là **expected**. Kiểm tra entitlement **và** posture policy; so với compliant-device test.

### Bài 10 — NAT attribution

Một public IP trùng với egress của công ty; threat alert nói nhân viên A đã gửi dữ liệu ra ngoài.

**Gợi ý:** cần NAT 5-tuple/time, VPN/device identity, app/EDR evidence; public IP không chứng minh user hoặc file content.

### Bài 11 — TLS fingerprint mới

80% microservices xuất hiện JA3 mới sau rollout SDK. Cách phân loại?

**Gợi ý:** xem release/process IDs, destinations, trust, change record, independent threat signals; **cohort baseline và rule validation**, không global whitelist.

### Bài 12 — Kubernetes policy mismatch

NetworkPolicy lab deny không hoạt động như kỳ vọng, nhưng test pod không có labels thuộc selector.

**Gợi ý:** test setup/policy selection sai; xác minh **namespace, Pod UID, labels, CNI policy enforcement và traffic path** trước khi gọi FP/FN.

### Bài 13 — App 404 và firewall

Client curl tới localhost trả HTTP 404. Có thể nói firewall chặn không?

**Gợi ý:** không; 404 là application response, chứng minh HTTP request đã tới một server trả response trong scope.

### Bài 14 — SIEM không thấy rule match

IDS sensor có raw alert, nhưng SIEM không hiển thị. Đây là detector FN?

**Gợi ý:** detector có phát alert, nên đây là **pipeline/ingestion/visibility issue**, không phải rule-level FN. Ghi cả hai metrics.

### Bài 15 — Chứng minh exception an toàn

Một rule gây FP trên backup service account. Thiết kế ít nhất bốn acceptance tests.

**Gợi ý:** benign backup fixture không page; suspicious fixture từ **other process/identity** vẫn alert; destination ngoài approved scope vẫn alert; TTL expiry khôi phục behavior; logs vẫn được giữ.

### Bài 16 — Kết quả không có ground truth

Có 12 alerts đã review, 4 confirmed FP, 3 confirmed TP, 5 unverified. Có thể báo precision=3/12 không?

**Gợi ý:** không nên coi 5 unverified là FP. Trong **7 đã được adjudicate**, observed precision=3/(3+4)≈42,9%, nhưng cần nêu **label coverage=7/12**, selection bias và không suy production precision đầy đủ.

### Bài 17 — False positive trong DNS

Một endpoint hỏi DNS cho domain có reputation xấu nhưng không mở kết nối. Có chắc C2 traffic xảy ra?

**Gợi ý:** không. Query có thể là cache/prefetch/block check; cần endpoint/process/flow/app evidence và nguồn reputation/timestamp.

### Bài 18 — Wi-Fi/802.1X

Một laptop bị deny VLAN nội bộ sau khi nhập đúng mật khẩu corporate, nhưng RADIUS trả certificate expired.

**Gợi ý:** authentication/authorization policy có thể deny đúng; đánh giá EAP-TLS certificate, enrollment và time sync, không whitelist MAC.

### Bài 19 — Đo detector sau tuning

Trước tuning TP=32, FP=48, FN=8, TN=912. Sau tuning TP=28, FP=12, FN=12, TN=948. Kết quả thế nào?

**Gợi ý:** trước precision=40%, recall=80%. Sau precision=28/40=70%, recall=28/40=70%. Precision tăng nhưng recall giảm 10 điểm phần trăm; cần business/risk acceptance và labeled scenario coverage.

### Bài 20 — Xây chương trình validation nhiều vùng

Một tổ chức có on-prem firewall, cloud SG/NACL, WAF, VPN, IDS/IPS, guest Wi-Fi, Kubernetes và ZTNA. Thiết kế chương trình:

1. Lập **in-scope access matrix** và threat/detection objectives.
2. Dùng **test identities + authorized windows**.
3. Xây **independent ground truth/oracles** cho từng control.
4. Tách **detection alert** khỏi **policy allow/deny**.
5. Thu **sensor/PEP/app/identity evidence** có provenance.
6. Đo **TP/FP/FN/TN** trên labeled population và **coverage** riêng.
7. Có **benign + positive fixtures**, multi-zone/IPv6/alternate path cases.
8. Tuning **narrowest scope** với change approval/TTL/rollback.
9. Theo dõi **security recall và availability** sau canary.
10. Ghi **adjudication history, residual risk và revalidation cadence**.

**Gợi ý:** định nghĩa câu hỏi trước, chọn công cụ sau. Không dùng alert count làm chỉ số thành công duy nhất.

## 37. Checklist đánh giá kết quả và loại false positive

| Kiểm tra | Bằng chứng hoặc điều kiện đạt |
| --- | --- |
| Đã có **test authorization và scope** rõ? | Owner, assets, methods, time window |
| Có expected policy behavior/test objective? | Access matrix hoặc detector specification |
| Có phân biệt detection và enforcement outcomes? | Hai loại result labels riêng |
| Có **ground truth độc lập** với scanner/detector? | Authenticated inventory, test fixture, app/PEP evidence |
| Có lưu test case ID và fixture version? | Test manifest |
| Timezone/UTC/clock skew có rõ? | Original/event/ingest time |
| Network source zone/identity đúng? | Session/NAT/role mapping |
| Target asset hiện tồn tại và đúng owner? | Asset/cloud/Pod UID inventory |
| DNS/SNI/proxy routing được xác minh? | Resolver/PEP/trace evidence |
| Sensor/PEP nằm trên đúng traffic path? | Route/capture point evidence |
| Packet loss/sampling/asymmetry đã kiểm tra? | Sensor health/counters |
| TLS/QUIC visibility limitations đã tính? | Protocol/termination context |
| Rule/plugin/version/config có đúng bản đang áp? | Deployment state và audit |
| Tool có scan/auth permission và parser support? | Tool execution/coverage logs |
| Có endpoint/app/business evidence khi claim outcome? | Request/transaction/EDR audit |
| Raw evidence và normalized events có provenance? | Evidence refs/hash nếu phù hợp |
| Có giữ FP/TP/FN/TN và UNVERIFIED tách biệt? | Adjudication status |
| Metrics có population/denominator thống nhất? | Labeling/test sample definition |
| Precision/FPR/FDR có bị nhầm? | Metric formulas, review |
| Accuracy có bị base-rate bias che FN? | Recall/FNR và class distribution |
| Có positive legitimate path control? | Allowed traffic app health |
| Có negative forbidden path control? | PEP deny + attempted flow evidence |
| Test không thành công do app down có bị loại kết luận? | Availability check |
| Có xác định root cause ở data/parser/asset/rule? | Finding RCA |
| Cảnh báo đã được confirm benign thật hay chỉ “known owner”? | Independent oracle |
| Rule tuning scoped theo identity/route/service/time? | Before/after conditions |
| Có tránh global whitelist/ANY allow/tắt IDS nhóm lớn? | Risk/control review |
| Còn giữ raw telemetry khi chỉ suppress paging? | Log/pipeline configuration |
| Có threat-positive regression fixtures sau tuning? | Recall/coverage test |
| Có kiểm tra adjacent rules/alternate paths? | Regression matrix |
| Có kiểm tra availability/latency/reject metrics? | Canary/SLO evidence |
| Có change ID/approval/rollback plan? | Change record |
| Exception có owner, TTL, reason và review date? | Exception registry |
| Risk acceptance có phân biệt với FP? | Residual risk sign-off |
| Có đánh giá false negatives do tuning gây ra? | Before/after FN set |
| Có theo dõi rule/asset changes cần revalidate? | Maintenance process |
| Evidence/report có redaction, access và retention? | Data-handling controls |
| Incident/test status có reviewer, hạn chế rõ? | Final report |

### 37.1. Điều kiện được phép đóng một FP finding

Một finding chỉ nên ghi **CONFIRMED_FP / RESOLVED** nếu:

1. **Target condition và test objective** được xác định.
2. Có **benign ground truth đáng tin** cho đúng sample/cohort.
3. Nguyên nhân được ghi hoặc phạm vi uncertainty đã nêu.
4. Có **remediation/tuning** phù hợp hoặc exception được phê duyệt.
5. **Original benign reproducer** được kiểm thử lại.
6. **Positive/security regression fixtures** vẫn đạt yêu cầu.
7. Control coverage và khả dụng không bị giảm ngoài ngưỡng.
8. Có **owner, reviewer, evidence refs, change/expiry**.

Nếu chưa đủ, dùng **UNVERIFIED, RISK_ACCEPTED, POLICY_MISMATCH hoặc OPEN** thích hợp, không ép nhãn FP để đóng số liệu.

## 38. Tổng kết

**Đánh giá kết quả và loại bỏ false positive** là kỹ năng cốt lõi của **kiểm thử và xác minh bảo mật mạng**. Nó yêu cầu phân biệt **tín hiệu phát hiện, trạng thái policy, hành vi thực của mạng và kết quả ứng dụng**. Với detector, cần nhãn đúng **TP/FP/FN/TN**, ground truth độc lập và các metric **precision, recall, FPR, FDR, F1** có denominator rõ. Với firewall, segmentation, ZTNA và các preventive controls, phải so **expected allow/deny** với **effective network/application behavior**, có cả positive và negative controls.

Một false positive không được xác nhận chỉ vì user khẳng định hợp lệ hoặc scanner/IDS báo lặp; cũng không được loại bỏ bằng cách **tắt rule, mở cổng toàn mạng, whitelist cả host/subnet hoặc nâng ngưỡng không kiểm tra recall**. Các nguyên nhân thường nằm ở **test fixture, asset mapping, NAT/identity correlation, clock/data quality, protocol parsing, TLS visibility, rule specificity, threat intelligence hoặc policy intent**. Để tránh nhầm lẫn, phải xác minh từ **network flows, PEP decisions, endpoint/IdP, application logs và authorized test oracle** theo đúng trust boundary.

Trong module **SECURITY_NETWORK_SECURITY**, cách tiếp cận bền vững là **scope rõ → ground truth → evidence có provenance → adjudication → root-cause → scoped tuning → positive/negative regression → canary/rollback → monitoring và revalidation**. Một kết quả được xem là tốt khi **giảm cảnh báo sai mà vẫn giữ năng lực phát hiện đúng, không tạo false negatives nghiêm trọng, không phá availability hoặc chính sách phân đoạn, và không làm lộ dữ liệu nhạy cảm**. Mọi kết luận phải có **người review, thời gian, control version, giới hạn đo và evidence có thể kiểm tra lại**.

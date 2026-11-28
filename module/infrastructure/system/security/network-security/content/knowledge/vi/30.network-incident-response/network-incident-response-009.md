# Ghi nhận timeline của sự cố mạng: từ dấu thời gian đến chuỗi bằng chứng có thể kiểm chứng

Trong chương **Ứng phó sự cố mạng** của module **SECURITY_NETWORK_SECURITY**, timeline là một trong những sản phẩm quan trọng nhất của quá trình điều tra. Khi phát hiện kết nối bất thường, mất khả dụng mạng, nghi vấn xâm nhập VPN, tấn công DDoS, thay đổi firewall trái phép hoặc truyền dữ liệu ra ngoài, đội ứng phó cần trả lời: **điều gì đã xảy ra, lúc nào, bằng chứng đến từ đâu, hệ thống nào bị ảnh hưởng, hành động xử lý bắt đầu và có hiệu lực khi nào?**

Một bản timeline tốt không chỉ là danh sách log sắp xếp theo timestamp. Nó phải phản ánh **nguồn, loại thời gian, sai lệch đồng hồ, độ tin cậy, ngữ cảnh, quan hệ giữa sự kiện, khoảng thời gian chưa quan sát được và quyết định của người ứng phó**. Nếu hệ thống firewall chạy chậm 90 giây, VPN gateway ghi log theo giờ địa phương, cloud audit phát sinh trễ 5 phút và EDR mất mạng, việc nối các log theo thứ tự văn bản có thể dẫn tới kết luận sai về nguyên nhân, phạm vi và thời điểm containment.

**Mục tiêu học tập**

- Phân biệt **event time, observation time, log time, ingestion time, alert time, analyst confirmation time và effective remediation time**.
- Chuẩn hóa timestamp về **UTC/ISO 8601**, giữ nguyên timestamp gốc, offset, timezone và precision; nhận diện **NTP drift, clock skew, time jumps, delayed delivery**.
- Thiết kế **timeline schema** gắn mỗi mốc với source, event ID, tài sản, identity, correlation key, confidence và evidence reference.
- Hợp nhất **firewall, VPN, DNS, DHCP, NAT, IDS/IPS, NetFlow/IPFIX, packet capture, EDR, IAM, cloud control plane và application logs** mà không gán sai danh tính.
- Xây dựng **mốc trước sự cố, phát hiện, phân tích, containment, eradication, recovery và post-incident review**, đồng thời ghi decision log riêng.
- Ghi rõ **observed fact, hypothesis, inference, contradiction, unknown và scope limitation**; không tuyên bố “không có tấn công” chỉ vì không thấy log.
- Lập timeline với **bằng chứng bảo toàn, giới hạn chia sẻ dữ liệu và khả năng tái lập**; thực hành trên bộ dữ liệu giả an toàn.

Trong bài, mọi tên miền có hậu tố **.example**, địa chỉ IP thuộc dải tài liệu, tài khoản test và timestamps trong tình huống đều là **dữ liệu giả định**. Các ví dụ lệnh chỉ áp dụng với **log của hệ thống được phép quản trị**. Không chủ động quét, truy cập hay thu thập dữ liệu trên mạng bên thứ ba.

## 1. Timeline sự cố mạng là gì?

**Incident timeline** là biểu diễn có cấu trúc của các mốc thời gian và sự kiện liên quan tới một sự cố, kèm bằng chứng, mức độ chắc chắn và tác động. Nó giúp cả đội SOC, Network, IAM, Platform, pháp chế và business owner làm việc trên **cùng một chuỗi sự kiện được kiểm chứng**, thay vì mỗi nhóm suy luận từ vài dòng log riêng.

### 1.1. Các câu hỏi timeline phải trả lời

1. **Trước dấu hiệu đầu tiên:** có thay đổi route, firewall, quyền IAM/VPN, cấu hình DNS hoặc triển khai nào?
2. **Dấu hiệu đầu tiên quan sát được:** event nào xuất hiện, sensor nào thấy, có bắt đầu trước alert không?
3. **Đối tượng:** source/destination IP, port, user, device, workload, service account và ứng dụng nào?
4. **Đường đi:** request/flow có qua proxy, VPN, NAT, WAF, load balancer, service mesh hoặc direct route nào?
5. **Tác động:** có bằng chứng kết nối thành công, phiên được tạo, dữ liệu được xử lý hoặc dịch vụ bị gián đoạn không?
6. **Phát hiện và xử lý:** alert tạo lúc nào, analyst xác minh lúc nào, isolation/block/revoke được thực thi và xác minh hiệu lực khi nào?
7. **Khoảng trống:** log nào thiếu, đồng hồ nào lệch, nơi nào không có cảm biến, sự kiện nào chỉ mang tính giả thuyết?
8. **Kết thúc:** tài nguyên đã phục hồi/được kiểm thử khi nào, residual risk và corrective actions là gì?

### 1.2. Timeline khác danh sách log

| Thuộc tính | Raw logs | Timeline có cấu trúc |
| --- | --- | --- |
| **Đơn vị** | Log record do hệ thống tạo | Incident-relevant fact/observation/decision |
| **Sắp thứ tự** | Theo timestamp nguồn hoặc ingest mặc định | Theo event-time đã chuẩn hóa, có uncertainty |
| **Nguồn** | Một hoặc vài hệ thống | Đa nguồn với provenance |
| **Trùng lặp** | Nhiều retries, alerts, packets | Gộp có kiểm soát, vẫn liên kết toàn bộ evidence |
| **Độ tin cậy** | Không luôn phân biệt | Observed/inferred/confirmed/contradicted |
| **Tác động** | Không nhất thiết có | Nêu được business/network significance |
| **Hành động người ứng phó** | Có thể rời rạc trong ticket | Mốc decision, containment và hiệu lực |
| **Khoảng trống** | Dễ vô hình | Unknown intervals, missing sensors, skew |

Một timeline **có thể có nhiều cách nhìn**: bản đầy đủ dành cho investigator; bản executive chỉ có mốc lớn, tác động và trạng thái; bản technical có correlation/evidence IDs. Các bản phải cùng dựa trên **nguồn sự thật được quản trị**, không sửa nội dung để phù hợp một câu chuyện có sẵn.

### 1.3. Timeline là công cụ điều tra, không tự chứng minh quan hệ nhân quả

Nếu log A xuất hiện trước log B, điều đó **không đủ** kết luận A gây ra B. Ví dụ một deployment xảy ra lúc 09:00 và một VPN alert xuất hiện lúc 09:05; có thể liên quan, có thể không. Cần **cơ chế kỹ thuật, correlation và kiểm chứng** trước khi ghi “deployment gây mất VPN”.

## 2. Các loại thời điểm phải phân biệt

### 2.1. Không có một “thời điểm sự kiện” chung cho mọi nguồn

| Trường thời gian | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Event time** | Khi hành vi mà bản ghi mô tả xảy ra theo đồng hồ nguồn | Firewall ghi packet bị deny lúc 09:03:10 |
| **Observation time** | Khi sensor thực sự quan sát/đo được tín hiệu | SPAN sensor timestamp packet khi capture |
| **Log generation time** | Khi tiến trình tạo bản ghi log | Log flush trễ vài giây sau flow kết thúc |
| **Collection time** | Khi collector đọc/nhận log | Agent đọc file theo batch |
| **Ingestion time** | Khi pipeline/SIEM nhận và index event | SIEM index lúc 09:09 một event lúc 09:03 |
| **Alert time** | Khi rule/correlation engine tạo alert | Rule tạo alert sau khi đủ ngưỡng |
| **Triage confirmation time** | Khi analyst xác nhận incident cần xử lý | On-call xác minh evidence |
| **Action issued time** | Khi đội phản ứng yêu cầu block/revoke/isolate | Gửi thay đổi firewall lúc 09:12 |
| **Action effective time** | Khi control thật sự có hiệu lực | Negative test xác minh block lúc 09:14 |
| **Recovery confirmed time** | Khi service/control được thử và đạt điều kiện phục hồi | Synthetic test pass lúc 09:32 |

**Không dùng ingestion time thay event time** để tuyên bố thứ tự tấn công nếu pipeline có queue/retry. Cũng không dùng thời điểm một người gửi tin nhắn “đã khóa account” để thay cho thời điểm **active sessions thật sự bị vô hiệu hóa**.

### 2.2. Ví dụ log đến SIEM trễ

~~~text
09:00:00Z  VPN login succeeded (event time trên gateway)
09:00:03Z  Firewall ghi connection đầu tiên
09:05:20Z  SIEM mới nhận VPN log vì pipeline tắc
09:06:00Z  SIEM correlation alert được tạo
09:07:10Z  Analyst bắt đầu điều tra

Sai:  "Firewall flow xảy ra trước VPN login."
Đúng: "Firewall flow được quan sát sau VPN login theo
       timestamp đã đối chiếu; VPN log được ingest muộn."
~~~

### 2.3. Mốc “lần đầu được thấy” không phải “thời điểm xâm nhập đầu tiên”

Các thuật ngữ nên tách:

- **First seen in available telemetry**: mốc sớm nhất có bằng chứng trong dữ liệu hiện có.
- **Earliest confirmed malicious action**: mốc sớm nhất được kiểm chứng là hoạt động độc hại.
- **Estimated initial access window**: khoảng nghi ngờ xâm nhập ban đầu, thường không chính xác tới giây.
- **Incident declaration time**: thời điểm tổ chức công bố incident theo quy trình.

**First seen** bị giới hạn bởi log retention, sensor coverage, capture start và độ tin cậy timestamp. Không viết “attacker bắt đầu lúc 09:00” chỉ vì log sớm nhất bạn tìm được là 09:00.

## 3. UTC, offset, timezone, daylight saving và precision

Một timeline điều tra nên sử dụng **UTC làm trục chính**, lưu timestamp theo ISO 8601/RFC 3339 khi phù hợp, đồng thời giữ **giá trị gốc** và timezone/offset từ hệ nguồn.

### 3.1. Cách biểu diễn

~~~text
2026-11-28T09:10:30Z         UTC; Z biểu thị offset +00:00
2026-11-28T16:10:30+07:00    Cùng thời điểm theo UTC+07
2026-11-28 16:10:30          Chưa có offset/timezone: mơ hồ
2026-11-28T09:10:30.123Z     Precision tới millisecond
2026-11-28T09:10Z            Chỉ precision tới phút
~~~

**Tất cả các timestamp chỉ để minh họa.** Trong sản xuất, timezone với daylight saving phải được hiểu theo thời điểm lịch sử, không áp offset hiện tại cho log từ những tháng trước.

### 3.2. Khác biệt giữa offset và timezone

**+07:00** là UTC offset; **Asia/Ho_Chi_Minh** là tên timezone có quy tắc lịch sử. Một hệ ở **America/New_York** có thể thay UTC offset theo daylight saving trong năm. Ghi cả **timezone identifier** khi có thể, vì chỉ dùng tên viết tắt như **CST** rất dễ mơ hồ.

### 3.3. Giữ hai dạng

Ví dụ normalize một log:

~~~json
{
  "raw_timestamp": "2026-11-28 16:10:30",
  "source_timezone": "Asia/Ho_Chi_Minh",
  "normalized_event_time_utc": "2026-11-28T09:10:30Z",
  "timestamp_precision": "seconds",
  "conversion_rule": "timezone mapping as of event date"
}
~~~

Không ghi **normalized_event_time_utc** nếu timezone nguồn chưa xác định. Khi chưa rõ, lưu **candidate interval** và nhãn **timestamp_unknown_zone**, không đoán theo timezone của máy analyst.

### 3.4. Precision khác accuracy

Timestamp ghi đến microsecond **không tự chính xác đến microsecond**. Nếu clock bị lệch 90 giây, việc hiển thị 6 chữ số sau dấu thập phân chỉ là **độ phân giải cao của một đồng hồ sai**. Phải tách:

- **Resolution/precision**: số bước thời gian công cụ có thể ghi.
- **Accuracy**: mức gần với thời gian thực có tham chiếu.
- **Clock synchronization confidence**: mức tin cậy vào NTP/PTP/GPS/time source.
- **Event attribution confidence**: mức tin rằng event thuộc đúng host/user/session.

### 3.5. Sắp xếp hai event trong cùng một giây

Nếu logs chỉ có precision tới giây, hai sự kiện cùng timestamp **không có thứ tự chắc chắn**. Không tự cho sự kiện ở dòng đầu file xảy ra trước dòng sau nếu hệ thống ghi bất đồng bộ; sử dụng **sequence counter, monotonic ordering, causal identifiers hoặc khoảng thời gian không chắc chắn** khi có.

## 4. Clock skew, NTP và thời gian được hiệu chỉnh

Trong điều tra mạng, **clock skew** có thể làm hành vi nguồn xảy ra “sau” hậu quả của nó trên dashboard. Do đó cần đánh giá đồng hồ trước khi nối sự kiện đa nguồn.

### 4.1. Các nguyên nhân lệch giờ

- Thiết bị mạng không đồng bộ NTP/PTP hoặc cấu hình time server sai.
- Firewall, switch, router hoặc thiết bị OT mất nguồn đồng bộ.
- VM/container host clock bị jump sau suspend/resume/migration.
- Collector đánh timestamp **lúc nhận log**, không lúc event phát sinh.
- Timestamp được ghi bằng giờ địa phương nhưng parser giả UTC.
- Chuyển daylight saving hoặc cấu hình timezone sai.
- Log flushing/batching, network outage hoặc delay ở SIEM pipeline.
- Một số nguồn chỉ có relative uptime/monotonic timestamps.

### 4.2. Không sửa raw evidence

Giữ nguyên timestamp gốc. Tạo **derived normalized time** kèm cách tính, độ tin cậy và nguồn reference:

~~~text
Raw VPN log event time:     2026-11-28 09:05:00Z
Reference observation:     gateway clock ~90 seconds fast
Estimated corrected time:  2026-11-28 09:03:30Z
Correction method:         approved clock-offset evidence
Uncertainty:               +/- 5 seconds in this example

Do not replace raw timestamp in the evidence artifact.
~~~

Ví dụ trên mô tả đồng hồ **nhanh hơn thời gian tham chiếu** nên thời gian thực ước lượng sớm hơn bản ghi. Không áp “-90 giây” cho toàn bộ ngày nếu clock offset có thể thay theo thời gian; đo **offset theo khoảng thời gian**.

### 4.3. Mô hình offset có sai số

Gọi:

- \(t_r\): timestamp gốc của nguồn.
- \(\Delta(t)\): offset nguồn so với reference time tại thời điểm đó.
- \(\epsilon\): biên sai số ước lượng.

\[
t_{\mathrm{corrected}} \approx t_r - \Delta(t)
\]

\[
t_{\mathrm{actual}} \in
[t_{\mathrm{corrected}}-\epsilon,\,
 t_{\mathrm{corrected}}+\epsilon]
\]

Nếu hai khoảng **overlap**, không khẳng định sự kiện A chắc chắn trước B chỉ vì hai corrected timestamps lệch nhau vài mili giây.

### 4.4. Tương quan clock độc lập

Khi được phép và có nguồn tham chiếu:

- Kiểm tra trạng thái **NTP/PTP** của thiết bị với lệnh read-only do vendor hỗ trợ.
- Xem **time synchronization logs** và thời điểm clock jump.
- So sánh các **shared events** giữa hai hệ: cùng VPN session start, cùng NAT/flow record, cùng request ID tại gateway và app.
- Kiểm tra **timezone/UTC conversion** trong collector và SIEM parser.
- Ghi **time confidence**: synchronized, estimated, unsynchronized, unknown.

Đừng đồng bộ/sửa giờ trên router hoặc domain controller giữa lúc điều tra chỉ để log “khớp đẹp” mà chưa có change/incident approval: thay đổi clock có thể ảnh hưởng auth, certificate validation và ứng dụng.

### 4.5. Monotonic time và wall time

**Monotonic clock** hữu ích đo khoảng thời gian trong một tiến trình/hệ thống, ít bị ảnh hưởng bởi thay đổi đồng hồ hiển thị; **wall clock** dùng để gắn mốc UTC. Cần biết nguồn log dùng clock nào. Monotonic value không trực tiếp so với UTC của thiết bị khác nếu chưa có một ánh xạ phù hợp.

## 5. Bằng chứng và provenance: timeline phải truy nguyên được

Mỗi dòng timeline nên dẫn về **source evidence ID**, không chỉ ghi câu kể lại. Ví dụ:

~~~text
Time UTC: 09:03:30Z +/- 5s
Event: VPN authentication accepted
Actor: contractor-test-17
Source: VPN gateway authentication log
Source event ID: vpn-evt-012
Original timestamp: 09:05:00Z (clock fast ~90s)
Confidence: observed event, estimated normalized time
Evidence: EVID-0001
Related sessions: vpn-session-71
Limitations: client device identity not yet confirmed
~~~

### 5.1. Mỗi sự kiện có ít nhất các trường

| Nhóm | Trường | Vì sao cần |
| --- | --- | --- |
| **Identity** | incident_id, event_id, source_event_id | Tránh trùng/sai sự cố |
| **Time** | original, UTC normalized, precision, uncertainty, ingest_time | Xây trục thời gian có độ tin cậy |
| **Source** | product/service, hostname, collector, sensor/vantage | Biết ai đã quan sát |
| **Subject** | device/identity/workload/source IP | Liên kết đúng đối tượng |
| **Action** | login, connection, deny, alert, config_change, revoke | Nêu việc được ghi nhận |
| **Target** | destination, resource, network zone, port/protocol | Hiểu scope mạng |
| **Result** | accepted, denied, timed out, policy applied | Không nhầm attempt và success |
| **Evidence** | file ID/log pointer/hash, ticket ID, trace ID | Có thể kiểm chứng lại |
| **Confidence** | observed, corroborated, inferred, hypothesis, disputed | Chặn kết luận quá mức |
| **Owner** | analyst, reviewer, incident lead | Trách nhiệm rà soát |

### 5.2. Tách observed và inferred

**Observed:** firewall log ghi accepted connection từ IP A sang IP B. **Inferred:** nhiều dấu hiệu cho thấy kết nối đó thuộc cùng user vừa VPN login. **Confirmed:** có NAT mapping + VPN session + EDR/process/app logs đáng tin nối đúng phiên. Mức độ chắc chắn phải thay đổi khi evidence xuất hiện.

### 5.3. Một timeline record có thể có nhiều chứng cứ

Không cần copy tất cả raw logs vào bảng chính. Dùng **evidence references** tới artifacts lưu an toàn. Một dòng “PEP blocked access” có thể dẫn tới **firewall policy change event + dataplane deny log + negative test**, trong khi bản timeline hiển thị ngắn gọn.

### 5.4. Cần ghi cả nguồn mâu thuẫn

Nếu server log cho biết request lúc 09:00 nhưng proxy log ghi 08:58, không xóa một trong hai:

1. Kiểm tra timezone/clock.
2. Xác định có hai requests khác nhau không.
3. So request ID/connection ID/NAT context.
4. Ghi **contradiction status** và người chịu trách nhiệm xác minh.

Xóa “outliers” chỉ vì chúng phá vỡ câu chuyện điều tra có thể khiến timeline sai.

## 6. Chuỗi bằng chứng (chain of custody) và tính nguyên vẹn

Nếu timeline sẽ dùng trong postmortem, audit, bảo hiểm hoặc quá trình pháp lý, **nguồn bằng chứng và lịch sử xử lý** phải có thể truy lại.

### 6.1. Thu thập không phá nguồn

- Ưu tiên **read-only exports** từ firewall/SIEM/EDR/IdP/cloud khi có quyền.
- Ghi **collector account, query/filter, snapshot time, timezone, tool version**.
- Bảo quản **file gốc ở nơi hạn chế quyền**, tạo bản làm việc riêng nếu cần normalize.
- Tính **cryptographic hash** của artifacts khi thu theo quy trình, ghi lại hash và phương pháp.
- Ghi ai **tạo, truy cập, chuyển giao, xuất bản hoặc chỉnh sửa** bản sao.
- Không làm biến dạng raw timestamp, source fields hoặc record ordering trong bản gốc.

### 6.2. Hash dùng để làm gì?

Hash như SHA-256 giúp kiểm tra **artifact bytes có đổi** giữa các lần xử lý. Nhưng hash không tự chứng minh log ban đầu là trung thực, clock đúng hoặc sensor không bị compromise; phải kết hợp **nguồn tin cậy, quyền hệ thống, immutability controls và corroboration**.

### 6.3. Phân loại dữ liệu

PCAP, DNS logs, VPN identities, IAM changes và application logs có thể chứa **PII, session identifiers, client IP, partner topology, secrets**. Không dán raw token/cookie/password vào timeline. Sử dụng **pseudonymized identity hoặc reference IDs**, chỉ cho người có quyền mở evidence chi tiết.

### 6.4. Bản timeline phát hành và bản nội bộ

| Phiên bản | Nội dung | Người đọc |
| --- | --- | --- |
| **Working timeline** | Sự kiện chi tiết, giả thuyết, mâu thuẫn, evidence pointers | SOC/IR, các owner liên quan |
| **Verified technical timeline** | Các mốc đã kiểm chứng, uncertainty và sources | Incident commander, security/platform leads |
| **Executive timeline** | Phát hiện, tác động, containment, recovery, hành động tiếp theo | Lãnh đạo/business owner |
| **External disclosure timeline** | Thông tin được phép chia sẻ, đã rà soát pháp lý/privacy | Khách hàng, đối tác, cơ quan theo quy định |

Không gửi bản working chứa thông tin nhạy cảm cho mọi người chỉ vì bảng chính nhìn giống bản báo cáo.

## 7. Timeline của quy trình ứng phó sự cố

Timeline không chỉ ghi hoạt động của đối tượng nghi ngờ mà còn ghi **hành động của đội ứng phó** theo các mốc điều tra.

~~~mermaid
flowchart LR
    A["Potential precursor"] --> B["First seen / alert"]
    B --> C["Triage / declaration"]
    C --> D["Investigation / scoping"]
    D --> E["Containment issued"]
    E --> F["Containment verified"]
    F --> G["Eradication"]
    G --> H["Recovery verified"]
    H --> I["Post-incident review"]
~~~

Các giai đoạn có thể **chồng lấp và lặp lại**; incident response thực không luôn đi theo một đường tuyến tính. Ví dụ vừa containment vừa tiếp tục điều tra phạm vi; recovery một dịch vụ có thể bắt đầu trước khi mọi hệ thống hoàn tất eradication.

### 7.1. Mốc bắt buộc trong response timeline

| Mốc | Bằng chứng khuyến nghị | Câu hỏi |
| --- | --- | --- |
| **First observed indicator** | Alert/raw event và sensor | Được thấy lần đầu ở đâu? |
| **Incident declared** | IR ticket/incident commander log | Khi nào quyết định mức độ? |
| **Scope established** | Asset/identity/path evidence | Ảnh hưởng tới ai/cái gì? |
| **Containment requested** | Change ticket/command audit | Ai phê duyệt hành động gì? |
| **Containment implemented** | Device/firewall/IAM config event | Control đã được cập nhật chưa? |
| **Containment effective** | Deny/revoke/session test | Đường trái quyền thực đã bị chặn chưa? |
| **Eradication verified** | Removed persistence/credential rotation evidence | Nguyên nhân kỹ thuật đã xử lý chưa? |
| **Recovery verified** | SLO/synthetic/business checks | Dịch vụ có hoạt động bình thường? |
| **Incident resolved/closed** | Approval, residual risk | Điều kiện đóng có đạt? |
| **Lessons assigned** | CAPA/action owners/dates | Phòng ngừa tái diễn như thế nào? |

### 7.2. Issued khác effective

Ví dụ team thay firewall rule lúc 11:05 nhưng rule propagation tới dataplane hoàn tất 11:07. **Mốc containment có hiệu lực** là khi traffic trái quyền thực bị chặn theo bằng chứng, không chỉ khi thao tác gửi lệnh hoặc commit cấu hình.

Với revoke VPN, cần phân biệt **disable new login**, **terminate existing tunnels** và **app/token sessions** còn dùng được qua đường khác.

### 7.3. Thời điểm phát hiện không phải lúc bắt đầu ảnh hưởng

Một sự cố có thể bắt đầu 08:00, được phát hiện 10:00, được declare 10:15 và mới containment 11:00. Tính metrics như **detection latency** và **containment time** phải công khai cách xác định **mốc bắt đầu**, tránh lấy alert time làm initial compromise nếu có evidence sớm hơn.

## 8. Các nguồn log/network telemetry đưa vào timeline

Một sự cố mạng có thể cần nhiều nguồn, nhưng mỗi nguồn chỉ nhìn thấy **một lát cắt của hệ thống**.

| Nguồn | Sự kiện hữu ích | Giới hạn/bẫy |
| --- | --- | --- |
| **Firewall/NGFW** | Allow/deny, NAT, policy hit, config change | Stateful flows, aggregated logs, offset |
| **VPN/ZTNA** | Auth success/fail, session start/end, tunnel IP, revocation | Login success không chứng minh mọi app access |
| **DNS resolver** | Qname/query/response và client mapping | Cache/DoH/DoT, resolver forwarding, shared IP |
| **DHCP/IPAM** | IP lease, device MAC/identity, renewal | Lease không xác minh ai đang dùng máy |
| **NAT gateway** | Private↔public IP/port mappings | Port reuse, logging granularity |
| **IDS/IPS/NDR** | Alert/signature/anomaly, flow evidence | False positives, sensor placement |
| **NetFlow/IPFIX** | 5-tuple, packets/bytes, duration | Sampling/aggregation, không đọc app payload |
| **Packet capture** | Packet timing, TCP/TLS/QUIC structures | Capture loss, asymmetric routing, encryption |
| **Router/switch** | Interface up/down, routing changes, BGP/OSPF events | Syslog có thể thiếu timezone hoặc queue trễ |
| **Load balancer/WAF/proxy** | Request/connection, TLS termination, policy action | Một request qua nhiều proxy hops |
| **EDR/endpoint** | Process/network association, device posture, containment | Agent offline/tampered, clock skew |
| **IdP/IAM/PAM** | MFA, grants, disable/revoke, admin activity | Token/sessions có thể tồn tại sau disable |
| **Cloud audit/VPC flow** | Control-plane changes, VPC traffic summaries | Delivery lag, aggregation, provider-specific semantics |
| **Kubernetes/service mesh** | Pod/service account, sidecar auth, network policy | Pod IP reuse, rolling deployment, mTLS hops |
| **Application/API/DB** | Authenticated action, request ID, transaction | Có thể sampling, không thể hiện path ngoài app |
| **Ticket/chat/on-call** | Decisions, approvals, human action times | Tin nhắn có thể đến muộn hoặc ước lượng |

### 8.1. Ưu tiên theo câu hỏi

Để xác định **đường kết nối**, ưu tiên firewall/NAT/flow/PCAP. Để xác định **user hoặc workload**, ưu tiên IdP/VPN/endpoint/service identity. Để xác định **thao tác lên dữ liệu**, ưu tiên application/API/business audit. Để xác định **lúc quyết định containment**, cần change/audit log và xác minh đường dữ liệu sau thay đổi.

### 8.2. Một nguồn có thể thiếu sự kiện do thiết kế

- TLS/QUIC mã hóa payload nên passive NDR không thấy HTTP path/body.
- Flow log có thể ghi **record ở cuối interval**, không phải lúc flow bắt đầu.
- VPN audit có thể ghi **reconnect** khác new authentication.
- DNS query có thể bị cache, không có log mới.
- EDR có thể **store-and-forward** sau khi máy online lại.
- Cloud audit đôi khi có **event time và delivery time** khác biệt lớn.

Vì vậy, **không thấy log** phải được diễn giải cùng độ bao phủ/retention và thiết kế của sensor.

## 9. Chuẩn hóa log thành mô hình timeline thống nhất

Mỗi hệ thống có schema riêng. Một firewall ghi **srcip/dstip/action**, một IdP ghi **principalId/authResult**, một cloud service ghi **eventTime/requestID**, trong khi PCAP chỉ có **packet timestamps và 5-tuple**. Muốn hợp nhất, cần định nghĩa data contract trước khi import.

### 9.1. Canonical event mẫu

~~~json
{
  "incident_id": "INC-LAB-2026-009",
  "timeline_event_id": "TL-0007",
  "category": "network_connection",
  "event_name": "vpn_assigned_ip_connected_to_admin_service",
  "event_time_original": "2026-11-28T09:07:05+07:00",
  "source_timezone": "Asia/Ho_Chi_Minh",
  "event_time_utc": "2026-11-28T02:07:05Z",
  "event_time_uncertainty_ms": 5000,
  "ingest_time_utc": "2026-11-28T02:09:15Z",
  "time_quality": "estimated_offset",
  "source_system": "firewall-lab-01",
  "source_record_id": "fw-demo-913",
  "evidence_id": "EVID-0003",
  "src_ip": "192.0.2.17",
  "src_port": 51320,
  "dest_ip": "198.51.100.25",
  "dest_port": 443,
  "network_protocol": "TCP",
  "action": "allow",
  "identity_ref": "vpn-user-test-17",
  "identity_attribution": "inferred_from_vpn_and_nat",
  "related_ids": ["vpn-session-71", "nat-demo-112"],
  "confidence": "medium",
  "status": "under_review",
  "analyst_note": "Application action not established from firewall flow"
}
~~~

Đây là **schema minh họa**, không phải log thô từ một sản phẩm. Dải IP được dùng cho tài liệu. Đặc biệt, **identity_ref** được đánh dấu **inferred**, không được đổi thành “confirmed” chỉ vì có một user login gần thời điểm đó.

### 9.2. Trường nào không nên mất trong quá trình normalize?

| Original detail | Vì sao giữ |
| --- | --- |
| **Raw timestamp string** | Cho phép kiểm tra conversion/timezone |
| **Original field names** | Giữ ngữ nghĩa và khắc phục parser errors |
| **Source record ID** | Tìm lại bản gốc trong hệ nguồn |
| **Sensor/interface/zone** | Xác định vị trí quan sát và trust boundary |
| **Source timezone, offset, precision** | Không tạo thứ tự thời gian giả |
| **Event vs ingest time** | Phát hiện delayed delivery |
| **Action/decision fields** | Allow không đồng nghĩa thành công tầng ứng dụng |
| **Subject identifiers** | User/device/workload có thể khác IP |
| **Raw evidence hash/location** | Giữ tính tái lập |
| **Parser/normalizer version** | Khi logic mapping đổi, biết event bị ảnh hưởng |

### 9.3. Tách record và sự kiện logic

Một lần kết nối có thể tạo:

~~~text
DNS lookup event
VPN authenticated session
Firewall SYN/allow
NAT translation
IDS inspection event
Proxy transaction
Application request
Application response
Firewall flow-close record
~~~

Đây có thể là **các quan sát khác nhau của một hành trình truy cập**, nhưng không được gộp thành một event “user đã tải dữ liệu” nếu không có app evidence. Timeline có thể dùng **parent_event_id, related_ids hoặc correlation_group** để nhóm mà vẫn giữ từng chứng cứ.

### 9.4. Trạng thái record trong quá trình điều tra

Nên có trạng thái rõ ràng:

- **Raw/imported:** đã thu thập, chưa kiểm tra.
- **Parsed:** đã chuẩn hóa schema/time format.
- **Correlated:** liên hệ nhiều nguồn theo khóa và time window.
- **Verified:** đã kiểm chứng với nguồn bằng chứng thích hợp.
- **Inferred:** có giả thuyết hợp lý nhưng chưa xác nhận.
- **Disputed:** có nguồn mâu thuẫn hoặc clock attribution chưa giải quyết.
- **Superseded:** một cách giải thích cũ được thay bởi evidence mới, vẫn lưu lịch sử.

Không xóa giả thuyết cũ mà không lưu lý do thay đổi; postmortem cần hiểu **quyết định được đưa ra dựa trên thông tin có tại thời điểm đó**.

## 10. Ghép sự kiện giữa nhiều nguồn mà không nối nhầm

Correlation là một trong các khâu khó nhất: cùng một hành vi có thể để lại nhiều log, nhưng **giống IP/port/time chưa chắc cùng phiên**.

### 10.1. Độ tin cậy của correlation keys

| Key | Mức hữu ích | Điểm yếu |
| --- | --- | --- |
| **App request ID / trace ID** | Mạnh trong chuỗi dịch vụ đã instrumented | Có thể được client tự gửi, cần trusted normalization |
| **VPN session ID** | Mạnh để nối auth và tunnel lifecycle trong một hệ | Không trực tiếp biết app operations |
| **Firewall/NAT connection/session ID** | Hữu ích để map địa chỉ qua NAT | Có thể bị tái sử dụng/thay theo vendor |
| **TCP 5-tuple + time window** | Hữu ích khi capture ở cùng hop | NAT, port reuse, proxy pooling làm thay tuple |
| **Authenticated principal ID** | Mạnh trong IdP/app audit khi được xác thực | Một principal có thể có nhiều devices/sessions |
| **Device/EDR process ID + time** | Hữu ích để xác định tiến trình | PID reuse, EDR loss hoặc tampering |
| **Destination hostname/DNS qname** | Hỗ trợ group theo service | Shared CDN IP, cache, DoH, host spoofing |
| **Timestamp gần nhau** | Hỗ trợ tìm ứng viên | Không đủ để xác nhận nhân quả hay identity |

### 10.2. Một correlation chain

~~~mermaid
flowchart LR
    A["IdP/VPN principal + session"] --> B["Assigned tunnel IP/lease"]
    B --> C["Firewall/NAT session mapping"]
    C --> D["Proxy/PEP transaction"]
    D --> E["App request/actor"]
    E --> F["Business operation audit"]
    C --> G["IDS/NetFlow/PCAP"]
~~~

Không phải mọi incident đều có đủ sáu chặng. Khi một chặng không có log hoặc chỉ có sampled data, ghi rõ **gap** thay vì tự nối trực tiếp.

### 10.3. Candidate matching cần cửa sổ thời gian hợp lý

Nếu firewall clock nhanh 90 giây và VPN clock chuẩn, matching theo ±3 giây sẽ bỏ sót session đúng. Nếu mở cửa sổ ±30 phút trong hệ nhiều người dùng, lại dễ ghép nhầm. Chọn time window theo:

- Precision và uncertainty của từng nguồn.
- NTP skew đã đo.
- NAT/port reuse frequency.
- Log delivery granularity.
- Session duration.
- Volume của các flows đồng thời.

**Thời gian gần nhau là điều kiện gợi ý, không phải bằng chứng duy nhất**.

### 10.4. Sự kiện dựa trên log không tương đương đối tượng tồn tại vĩnh viễn

Một Kubernetes Pod IP hoặc ephemeral VM IP có thể được cấp cho workload khác sau vài phút. Một VPN tunnel IP cũng có thể được cấp lại. Muốn gắn IP vào user/workload, phải kiểm tra **lease/session start/end bao phủ đúng thời điểm flow**, không chỉ nhìn bảng mapping mới nhất.

## 11. NAT, DHCP, VPN và source IP attribution

### 11.1. Trường hợp không có NAT mapping

Firewall thấy:

~~~text
2026-11-28T09:05:10Z  src=203.0.113.40:53010
                      dst=198.51.100.25:443
                      action=allow
~~~

Nhưng **203.0.113.40** là public NAT IP của một văn phòng. Không thể khẳng định user nào truy cập bằng log đó. Cần mapping:

~~~text
Public 203.0.113.40:53010
  <- Private 192.0.2.17:51320
  <- VPN/host/device identity in same time interval
~~~

Toàn bộ IP và ports chỉ là ví dụ. NAT records phải khớp **giao thức, addresses, ports, effective interval**, không chỉ public IP.

### 11.2. DHCP leases

DHCP có thể gán IP cho một thiết bị trong một khoảng thời gian. Khi phân tích:

- Ghi **lease start, renew, expiry** và timezone của DHCP server.
- Xác minh lease còn hiệu lực tại thời điểm event.
- Kết hợp device identity/802.1X/switch logs nếu cần.
- Chú ý **MAC spoofing, randomized MAC, VM/container networking**, không xem MAC là bằng chứng user tuyệt đối.

### 11.3. VPN logs

Một VPN log có thể có:

- **Auth attempt/result**.
- **MFA result** hoặc IdP correlation.
- **Session start/end**.
- **Assigned tunnel IP**.
- **Device posture/client version**.
- **Gateway location** và reconnect reason.

**VPN login thành công ≠ mọi kết nối từ NAT IP đó thuộc user ấy**. Cần xác nhận assigned IP, session interval, gateway routing và other concurrent sessions.

### 11.4. Session overlap và port reuse

Trong thời điểm nhiều VPN clients dùng chung gateway, NAT ports có thể đổi và được tái sử dụng sau khi flow đóng. Nếu một log flow-close được ghi sau khi session mới bắt đầu, **dùng mỗi record timestamp** có thể ghép sai. Phải sử dụng **flow start/end hoặc connection tracking state** khi có.

### 11.5. IPv6 và alternate paths

IPv6 có thể bỏ qua một số mô hình IPv4 NAT và dùng **privacy addresses** thay đổi. Không dựa vào một IP IPv4 để khẳng định không có kết nối từ client qua IPv6. Timeline nên ghi **address family, interface, route và sensor coverage** riêng khi cần.

## 12. DNS và HTTP/TLS metadata: diễn giải đúng chuỗi sự kiện

DNS logs có thể giúp xác định domain một client đã hỏi, nhưng **không chứng minh client đã kết nối hay gửi HTTP request** tới domain.

### 12.1. Ví dụ cùng ngày

~~~text
09:00:00Z  DNS resolver log:
            client asks for api.partner.example
09:00:01Z  DNS response:
            address 198.51.100.25
09:00:04Z  Firewall:
            TCP flow to 198.51.100.25:443 accepted
09:00:05Z  TLS sensor:
            ClientHello observed with SNI api.partner.example
09:00:06Z  Application log:
            POST /v1/orders, authenticated test principal, 200
~~~

Nếu chỉ có ba sự kiện đầu, có thể nói **domain query và network flow được quan sát và tương quan**; chưa đủ khẳng định HTTP operation. **Application log** cung cấp mức bằng chứng khác, nhưng vẫn phải kiểm tra log/ID tương ứng đúng flow.

### 12.2. Những khoảng trống thường gặp

- **DNS cache/prefetch**: DNS query có nhưng không có connection, hoặc ngược lại.
- **Shared CDN IP**: nhiều hostname cùng trỏ về một IP.
- **DoH/DoT/DoQ**: passive observer có thể không thấy nội dung DNS query.
- **TLS 1.3/ECH**: một số hostname/handshake metadata bị che.
- **HTTP/2/3 multiplexing**: một connection chứa nhiều requests.
- **Proxy resolution**: proxy có thể tự resolve đích, client-side DNS log không phản ánh toàn bộ.

Do đó, **DNS event**, **TLS handshake** và **application request** là những loại sự kiện khác nhau, không được gộp thành một “user đã tải dữ liệu” nếu chưa có app audit.

### 12.3. Khi một domain xuất hiện trước event

Đặt DNS record vào timeline có thể giúp analyst tìm mốc chuẩn bị, nhưng phải tránh gọi một DNS lookup là **initial compromise**. Một ứng dụng có thể resolve domain để prefetch, health check hoặc kiểm tra cập nhật mà không truyền dữ liệu nhạy cảm.

## 13. Flow logs, packet capture và IDS: phân biệt “seen” với “succeeded”

### 13.1. Firewall allow là gì?

Firewall **allow** thường cho biết policy cho phép xử lý một traffic unit/flow theo góc nhìn của firewall. Nó không tự khẳng định:

- TCP three-way handshake đã hoàn tất.
- TLS handshake đã xác thực peer thành công.
- HTTP request đã gửi và được ứng dụng xử lý.
- User đã được cấp quyền dữ liệu.
- File đã được truyền hoặc ghi nhận đầy đủ.

Muốn kết luận phải kiểm tra **session state, bytes, response, application logs** tùy câu hỏi.

### 13.2. IDS alert là tín hiệu, không tự là incident xác nhận

IDS/IPS alerts có thể là:

- **Signature match** đúng nhưng benign test traffic.
- False positive do protocol parser hoặc rule overly broad.
- Traffic do scanner được ủy quyền.
- Tín hiệu thật của tấn công bị chặn trước khi tới ứng dụng.
- Event từ **sampled/asymmetric capture** thiếu context.

Trong timeline, ghi **Alert observed** với rule ID, severity, sensor, action và confidence; chỉ nâng thành **Confirmed malicious action** khi có evidence hỗ trợ.

### 13.3. NetFlow/IPFIX time semantics

Một flow exporter có thể gửi record khi flow **kết thúc**, **hết active timeout** hoặc theo batch. Timeline cần ghi **flow_start/flow_end**, không lấy thời điểm SIEM nhận export làm thời điểm connection đầu tiên. Với sampling, byte/packet counters có thể là **ước lượng hoặc sampled values**.

### 13.4. Packet capture có timestamps và packet loss

Một packet capture giúp thấy **TCP SYN/FIN/RST, packet sizes/timing, TLS handshake metadata** trong phạm vi capture. Nhưng:

- Timestamp do capture host/driver tạo và có sai số.
- Packet loss/snaplen/asymmetric routing có thể thiếu packets.
- Một TCP retransmission không tự tạo HTTP retry mới.
- HTTPS/QUIC mã hóa application content.
- Các PCAP ở hai hop qua NAT/proxy không có cùng 5-tuple.

Đọc PCAP cần ghi **capture point, direction, time correction và scope** trước khi dùng làm trục thời gian.

### 13.5. Một flow chứa nhiều application events

HTTP/2 multiplexing, HTTP keep-alive, WebSocket và gRPC streams có thể giữ network connection dài. Một record firewall flow có **start 09:00, end 11:00** không đồng nghĩa một transaction kéo dài hai giờ; phải dùng **application-level events** để biết các request/operation bên trong.

## 14. Identity, endpoint, workload và cloud audit

### 14.1. Human identity

IdP có thể ghi user authentication, MFA challenge, token issuance, risk signal và disable event. Nhưng:

- MFA được yêu cầu không đồng nghĩa đã thành công.
- Session/token có thể tồn tại sau account disable.
- Một user có nhiều devices, browsers, VPN sessions.
- Một shared account/service token có thể được nhiều tiến trình dùng.

Timeline nên dùng **immutable subject/user ID khi có**, không chỉ display name hoặc email có thể đổi.

### 14.2. Endpoint identity

EDR có thể cung cấp **process started, network connection opened, file modified, device isolated**. Khi ghép với firewall flow, xem:

- Agent health và offline buffering.
- Process start/end time, PID reuse.
- Hostname/device ID/IP assignment tại thời điểm event.
- Timestamps event vs agent upload.
- Sensor privilege và khả năng bị xâm nhập.

Không kết luận process gây flow chỉ vì cùng machine IP nếu có nhiều processes/containers hoặc thiếu process-level evidence.

### 14.3. Cloud control plane và dataplane

Ví dụ cloud audit ghi một security group thay đổi lúc 09:00, VPC flow log ghi connection lúc 09:01. Có thể liên quan, nhưng muốn kết luận **thay đổi security group khiến connection được cho phép**, cần:

- Đúng resource/security group attachment và version.
- Thời gian rule thực có hiệu lực, không chỉ API response.
- Các security layers khác (NACL, route, load balancer, host firewall).
- Positive/negative test hoặc dataplane evidence.

Audit event time có thể khác thời điểm **network policy convergence**.

### 14.4. Kubernetes và container workloads

Pod IP có thể được **tái sử dụng**. Timeline cho traffic từ Pod phải có:

- Namespace, Pod UID, ServiceAccount, node và cluster.
- Pod creation/termination time, image/deployment revision.
- CNI/NetworkPolicy decision và service mesh identity nếu có.
- Lưu ý NAT qua node/egress gateway và sidecar proxy.

Không map IP của Pod đã bị xóa sang Pod hiện tại cùng IP rồi kết luận sai đối tượng.

### 14.5. OT/IoT và thiết bị ít telemetry

Nhiều thiết bị OT/IoT có **clock không đồng bộ, logs ngắn, không có EDR và không thể restart để lấy bằng chứng**. Cần ưu tiên **passive network sensor, asset inventory, switch port và historian/SCADA event source** theo yêu cầu an toàn vận hành. Tránh scan/chạm thiết bị thật ngoài scope trong lúc incident; phải đánh dấu uncertainty nếu nguồn thiếu.

## 15. Chọn sự kiện cho timeline: đủ sâu nhưng không ngập noise

Một sự cố có thể phát sinh hàng triệu log lines. Timeline không cần chứa tất cả flow packets; nó cần giữ **mốc tạo nên hiểu biết và quyết định** với references cho raw evidence.

### 15.1. Những event nên đưa vào

- Mốc **first seen** và những precursor đáng tin trước đó.
- **Authentication changes**, privileged grants, VPN/session starts.
- Những connections/flows đại diện cho **đường tấn công hoặc tác động**.
- Sự kiện **policy/config/route change** có liên quan.
- Mốc **alert fired, triage, incident declaration**, escalation.
- **Containment requested, deployed và verified**.
- **Credential rotation, isolation, patch, recovery tests**.
- **Data-access/business effects** có bằng chứng.
- Các **log gaps, false-positive corrections, uncertainty changes** quan trọng.

### 15.2. Những record thường chỉ cần aggregate

- Hàng nghìn repeated IDS alerts của cùng rule/source trong cùng một burst.
- TCP retransmissions hoặc NetFlow records nối tiếp của một session dài.
- Phần lớn health checks bình thường trong cùng khoảng.
- Duplicate SIEM events do ingestion retries.
- Nhiều status updates không thay đổi quyết định.

Nên tổng hợp thành **event group** có count, first/last seen, representative evidence IDs và query/snapshot reference; giữ quyền mở raw records khi điều tra.

### 15.3. Không xóa sự kiện phản bác giả thuyết

Ví dụ IDS alert gợi ý dữ liệu được chuyển ra ngoài, nhưng app log cho biết proxy đã block request trước backend. Cả hai phải được đưa vào để diễn giải: **attempt observed**, **request blocked**, **no confirmed app transfer in observed scope**. Không xóa IDS alert cũng không khẳng định transfer thành công.

### 15.4. Timeline sống có version

Khi incident đang diễn ra, timeline phải được cập nhật có lịch sử:

~~~text
v0.1 — initial triage, partial logs, event times uncorrected
v0.2 — NAT mapping and VPN sessions correlated
v0.3 — clock skew measured; ordering corrected
v0.4 — containment verified by dataplane evidence
v1.0 — post-incident reviewed, open uncertainties retained
~~~

**Versioning** giúp phân biệt “chúng ta biết điều gì vào lúc quyết định containment” với “sau này điều tra tìm thêm gì”, tránh đánh giá quyết định quá khứ bằng thông tin không có lúc đó.

## 16. Tình huống xuyên suốt: nghi vấn tài khoản VPN bị sử dụng trái phép

### 16.1. Mô tả tình huống giả định

Một tổ chức vận hành VPN cho nhà thầu và một ứng dụng quản trị nội bộ ở **198.51.100.25:443**. Vào buổi sáng, SIEM phát cảnh báo phiên VPN của một test contractor có dấu hiệu bất thường. Đội SOC cần xác định:

- Phiên VPN nào được tạo?
- Địa chỉ tunnel nào được cấp và flow nào thuộc phiên đó?
- Firewall thấy traffic gì và nó có tới ứng dụng thành công không?
- Alert phát sinh **sau sự kiện thực** bao lâu?
- Khi vô hiệu hóa tài khoản, **đường truy cập cũ thật sự hết hiệu lực lúc nào**?

Mọi thông tin dưới đây là **bài tập minh họa**, không khẳng định tài khoản thật bị xâm nhập. Một quyết định “suspicious” phải được nâng thành incident xác nhận dựa trên bằng chứng thực, không chỉ location khác thường.

### 16.2. Chú ý clock skew trước khi sắp thứ tự

Nguồn **firewall-lab-01** có bằng chứng đồng hồ **nhanh khoảng 90 ± 5 giây** trong khoảng sự cố. **VPN, IdP và app lab** dùng UTC theo reference đã kiểm tra. SIEM có queue delay. Vì vậy:

~~~text
Firewall raw event timestamp:  2026-11-28T08:56:52Z
Estimated firewall offset:     +90 seconds (+/- 5s)
Corrected event timestamp:     2026-11-28T08:55:22Z +/- 5s

SIEM ingest time:              2026-11-28T09:01:30Z
These are different timestamps for the same firewall record.
~~~

### 16.3. Timeline đã normalize

| UTC đã chuẩn hóa | Event/bằng chứng | Source/evidence | Độ tin cậy và diễn giải |
| --- | --- | --- | --- |
| **08:55:12Z** | IdP chấp nhận login test principal sau MFA theo rule hiện hành | IdP auth, EVID-01 | **Observed**; chưa chứng minh device/ý định user |
| **08:55:17Z** | VPN mở session 71, cấp tunnel IP 192.0.2.17 | VPN auth/session, EVID-02 | **Observed**; ánh xạ trong session interval |
| **08:55:20Z** | NAT record map private 192.0.2.17:51320 sang 203.0.113.40:53010 | NAT log, EVID-03 | **Observed** theo đúng 5-tuple/time |
| **08:55:22Z ±5s** | Firewall allow TCP connection tới 198.51.100.25:443 | FW raw 08:56:52Z, EVID-04 | **Observed flow**, thời gian corrected; không xác nhận app action |
| **08:55:23Z** | IDS ghi rule match về bất thường tại egress | IDS, EVID-05 | **Alert evidence**; không tự là compromise |
| **08:55:27Z** | Reverse proxy trả 401 cho request tới admin portal | Proxy/app, EVID-06 | **Observed rejection**; không chứng minh truy cập thành công |
| **09:02:15Z** | SIEM correlation phát alert sau khi nhận đủ các log | SIEM rule, EVID-07 | **Alert created**, không phải first network event |
| **09:03:00Z** | On-call nhận và bắt đầu xác minh scope | Incident ticket, EVID-08 | **Human action**, chưa containment |
| **09:05:15Z** | Incident lead phê duyệt disable account và terminate VPN session | Approval/ticket, EVID-09 | **Decision/authorization** |
| **09:05:45Z** | IdP account disabled | IdP audit, EVID-10 | **New login control**, không bảo đảm existing tunnel bị ngắt |
| **09:06:00Z** | VPN gateway ghi session 71 terminated | VPN session log, EVID-11 | **Gateway action**, cần xác minh network effect |
| **09:06:25Z** | Controlled negative test không còn tới được resource qua tunnel | Firewall/PEP/test, EVID-12 | **Verified containment** trong phạm vi kiểm thử |
| **09:10:00Z** | Điều tra không thấy phiên VPN khác trong các logs có coverage đã xác định | VPN/IdP query, EVID-13 | **Scoped negative finding**, không khẳng định toàn bộ hệ thống |
| **09:25:00Z** | Authorized user kiểm tra ứng dụng admin hoạt động bình thường | Synthetic/app test, EVID-14 | **Service recovery/availability validated** |

### 16.4. Những điều chưa thể kết luận từ timeline

Không thể tự khẳng định:

- MFA thành công đồng nghĩa test contractor là người trực tiếp thực hiện.
- Firewall allow nghĩa một request có quyền đã được chấp nhận.
- IDS alert là cuộc tấn công được xác nhận.
- Proxy 401 nghĩa không có đường truy cập thứ hai tới app.
- Các log không thấy data transfer chứng minh tuyệt đối **không có exfiltration**.
- Account disabled lúc 09:05:45Z đã vô hiệu hóa mọi app/API tokens.

Nếu có app cookie/token riêng, cần **application session revocation evidence** và kiểm tra alternate paths trong đúng scope. Timeline phải ghi **residual unknowns**.

### 16.5. Mốc và độ trễ có thể đo

Với ví dụ:

- **First observed relevant network/identity event:** 08:55:12Z.
- **Alert created:** 09:02:15Z.
- **Triage started:** 09:03:00Z.
- **Containment approved:** 09:05:15Z.
- **Account disabled:** 09:05:45Z.
- **VPN session termination logged:** 09:06:00Z.
- **Containment effect verified by bounded test:** 09:06:25Z.

Nếu đo từ first observed event tới alert, độ trễ khoảng **7 phút 3 giây**; từ alert tới negative test xác minh containment là **4 phút 10 giây**. Các chỉ số này **không phải dwell time của attacker**, vì chúng ta chưa xác định initial compromise. Mốc firewall corrected có uncertainty ±5 giây cũng không được diễn giải chính xác tới millisecond.

### 16.6. Executive summary ngắn

Một bản tóm tắt an toàn có thể nói:

> Trong ngày 28/11/2026 (UTC), hệ thống ghi nhận phiên VPN test bất thường và một kết nối tới ứng dụng quản trị. Proxy đã trả 401 với request được quan sát. SOC tạo alert lúc 09:02:15Z, vô hiệu hóa account và chấm dứt phiên; kiểm thử xác minh đường VPN mục tiêu không còn khả dụng lúc 09:06:25Z. Chưa có bằng chứng trong các nguồn được kiểm tra rằng thao tác quản trị thành công, nhưng việc đánh giá các đường truy cập khác và app tokens là mục tồn đọng cần xử lý.

Đây là **narrative dựa trên bằng chứng**, không phải ghi “tấn công đã thất bại hoàn toàn” khi vẫn còn những vùng chưa quan sát.

## 17. Evidence ledger và timeline table: hai bảng bổ sung cho nhau

**Evidence ledger** trả lời “dữ liệu gốc nằm ở đâu, do ai thu thập, có nguyên vẹn không?”. **Timeline table** trả lời “bằng chứng này cho thấy điều gì trong chuỗi sự kiện?”. Nên sử dụng hai artifacts có liên kết.

### 17.1. Evidence ledger mẫu

| Evidence ID | Nguồn | Khoảng dữ liệu | Thu thập | Integrity/handling |
| --- | --- | --- | --- | --- |
| EVID-01 | IdP auth audit export | 08:40–09:15 UTC | IAM responder | File raw, hash, restricted |
| EVID-02 | VPN session audit | 08:40–09:15 UTC | VPN owner | Read-only export |
| EVID-03 | NAT translation logs | 08:50–09:15 UTC | Network analyst | Bảo vệ port mapping |
| EVID-04 | Firewall flow log | 08:50–09:15 UTC | Network analyst | Clock offset evidence liên kết |
| EVID-05 | IDS alert log | 08:50–09:15 UTC | SOC | Rule/parser version lưu |
| EVID-06 | Reverse proxy access log | 08:50–09:15 UTC | App owner | URI/token redacted |
| EVID-07 | SIEM correlation result | 09:00–09:10 UTC | SOC | Rule definition và ingest timestamps |
| EVID-09 | Incident approval | 09:05 UTC | Incident commander | Người phê duyệt và policy |
| EVID-12 | Containment negative test | 09:06 UTC | Network + IAM | Test scope, source và result |

**Hash và tên file thật** chỉ được điền sau khi artifact được thu theo quy trình; không bịa hash để trang trí. Với log có PII, ledger có thể dùng **opaque evidence ID** thay đường dẫn lưu trữ nhạy cảm.

### 17.2. Timeline change log

~~~text
TL-0004
  09:03 first imported: event_time 08:56:52Z (raw firewall)
  09:08 quality review: firewall offset +90s +/-5s established
  09:09 corrected event time 08:55:22Z +/-5s
  Raw event and previous display preserved
  Reviewer: network-analyst / source EVID-CLOCK-01
~~~

Ví dụ cho thấy **kết luận có thể thay đổi**, nhưng bản evidence gốc không được chỉnh sửa.

### 17.3. Event ID và reference policy

Mỗi timeline row nên có **stable ID** như TL-0004. Khi một điều tra viên viết “evidence TL-0004 contradicted by TL-0011”, cả nhóm biết đúng mốc được nhắc tới, dù timeline được sắp lại sau hiệu chỉnh.

## 18. Chuẩn hóa, deduplication và tổng hợp không làm mất chứng cứ

### 18.1. Vấn đề log trùng lặp

Một SIEM có thể nhận cùng event hai lần do collector retry, một firewall có **flow open/flow close**, một IDS tạo nhiều alerts cho một stream, và một app ghi **retry** thành nhiều request attempts. Các loại trùng này không giống nhau.

| Hiện tượng | Có nên gộp? | Cách giữ evidence |
| --- | --- | --- |
| **Collector duplicate của cùng source_event_id** | Có thể dedupe ở analytics | Giữ raw copies hoặc ingest references |
| **Flow start và flow end** | Không xóa một chiều | Gộp thành lifecycle summary có start/end |
| **Nhiều IDS alerts một TCP session** | Có thể aggregate thành alert burst | Count, first/last, rule IDs |
| **TCP retransmission** | Không coi request mới | Keep TCP metrics, không nhân đôi app operations |
| **HTTP client retry** | Không gộp thành một attempt | Link retry group/transaction ID |
| **Cùng user login hai VPN gateways** | Không gộp | Hai sessions riêng cần điều tra |
| **Hai events có cùng timestamp precision một giây** | Không gộp tự động | Sắp thứ tự chưa chắc, lưu sequence if available |

### 18.2. Định danh nguồn và version

Một hệ có thể tạo **event ID không duy nhất toàn cầu**. Khi dedupe, nên dùng **source ID + source_event_id + version/time range**, kết hợp parser-specific constraints. Một regex theo text message có thể làm mất hai event thật chỉ vì cùng nội dung.

### 18.3. Log suppression và summary

Nếu một source gửi hàng trăm nghìn events, timeline có thể ghi:

~~~text
09:00–09:03Z
  IDS rule R-1000 matched 1,824 times for a specific source/dest tuple.
  Source: IDS sensor S-1, alert IDs preserved in EVID-15 export.
  No single alert is treated as confirmed successful exploitation.
~~~

**Không đổi sự kiện tổng hợp thành fact “1,824 cuộc tấn công thành công”**. Chỉ có 1.824 rule matches theo điều kiện log.

### 18.4. Data freshness và late arrivals

Khi source gửi log trễ, một event mới có thể được chèn vào **giữa timeline cũ**, không phải cuối cùng. Dashboard cần **event-time ordering** và chỉ ra time của lần cập nhật/sửa. Incident report có thể **freeze tại cutoff** kèm ghi chú nguồn nào chưa đồng bộ.

## 19. Nguồn thời gian không đáng tin, thiếu log và mốc bất định

### 19.1. Khoảng thời gian thay vì một giây giả

Nếu chỉ biết thiết bị OT xảy ra lỗi **trong khoảng 10:00–10:05**, viết:

~~~text
Event time range: 2026-11-28T10:00:00Z .. 10:05:00Z
Reason: source logs only interval-based aggregate
Confidence: time window, not point timestamp
~~~

Không chọn 10:02:30Z rồi hiển thị như timestamp đo được. Có thể dùng **estimated midpoint** cho visualization nhưng bắt buộc gắn uncertainty/range và không dùng nó để chứng minh thứ tự nhân quả với sự kiện ở 10:03.

### 19.2. Unknown intervals

Trong timeline, nên ghi rõ:

- Sensor S2 mất packets 09:10–09:13.
- EDR trên endpoint E5 offline 09:00–09:25.
- Cloud flow logs có sampling và delayed delivery.
- Firewall rotated logs trước thời điểm cần tra.
- Proxy log có thiếu region hoặc request IDs.

Một khoảng **không có bằng chứng** có thể mang **rủi ro chưa biết**, không mặc định chứng minh không có hoạt động.

### 19.3. Tách “không thấy”, “bị chặn” và “không xảy ra”

| Kết luận | Yêu cầu bằng chứng |
| --- | --- |
| **Không thấy event trong nguồn S** | Query/scope/retention của S rõ, đã chạy và được ghi |
| **Control đã chặn action X** | Policy deny + dataplane/app negative outcome trong test/sự kiện |
| **Không có action X trong toàn bộ sự cố** | Cần coverage và khả năng loại trừ rất mạnh; thường khó khẳng định tuyệt đối |
| **Chưa xác định action X** | Chính xác khi chưa có đủ evidence |

### 19.4. Thứ tự mâu thuẫn khi clock có sai số

Giả sử:

~~~text
Event A corrected: 09:01:10Z +/- 20s
Event B corrected: 09:01:15Z +/-  2s
~~~

Khoảng của A là **09:00:50–09:01:30**, B là **09:01:13–09:01:17**. Chúng **overlap**; không thể chứng minh A trước B dựa trên timestamps alone. Muốn xác định thứ tự cần **causal link, sequence ID, synchronized source hoặc evidence khác**.

### 19.5. Không ép dữ liệu khớp narrative

Một đội có thể tìm evidence ban đầu phù hợp giả thuyết “credential abuse”, nhưng log sau đó cho thấy test scanner được phê duyệt. Timeline phải cho phép **downgrade hypothesis** và ghi việc false positive được xác nhận. Độ tin cậy của báo cáo phụ thuộc khả năng **sửa kết luận công khai**, không giữ mọi alert là attack.

## 20. Decision log và response timeline phải được nối nhưng không trộn

Một **decision log** lưu **ai quyết định điều gì, dựa trên evidence nào, rủi ro gì được chấp nhận và mốc thi hành nào được yêu cầu**. Một **timeline** cho biết events và hiệu lực theo thời gian.

### 20.1. Decision record mẫu

~~~yaml
decision_id: DEC-LAB-009
incident_id: INC-LAB-2026-009
decision_time_utc: "2026-11-28T09:05:15Z"
approved_by: "incident-commander"
action: "disable_test_account_and_terminate_vpn_session"
evidence_refs:
  - EVID-02
  - EVID-04
  - EVID-05
scope: "contractor-test-17 / vpn-session-71"
business_impact_review: "approved lab scope"
implementation_ref: EVID-11
effectiveness_ref: EVID-12
status: "verified_in_scope"
~~~

Đây là **cấu trúc ví dụ**, không phải một thay đổi thực tế. Một quyết định real-world cần **approval theo playbook/độ nghiêm trọng**, đặc biệt khi có thể làm gián đoạn khách hàng hoặc nhiều services.

### 20.2. Ba loại mốc hành động

- **Decision/approval:** người có thẩm quyền chọn một hành động.
- **Implementation/configuration:** hệ thống nhận/apply thay đổi.
- **Effectiveness verification:** negative/positive control cho thấy tác dụng mong muốn.

Với firewall, **API success** không nhất thiết đồng nghĩa rule được áp trên mọi dataplane nodes. Với IAM, **account disabled** không đảm bảo app session cookie hoặc API token cũ bị vô hiệu ngay.

### 20.3. Mốc undo/rollback

Nếu thay đổi được rollback, phải ghi:

- Ai ra quyết định và tại sao rollback.
- Thời gian rollback request, deploy, effective.
- Kết quả kiểm thử sau rollback.
- Rủi ro bảo mật có quay trở lại không và compensating control.

Một timeline không ghi rollback dễ khiến hậu kiểm nhầm rằng một rule vẫn đang áp dụng suốt incident.

### 20.4. Giao tiếp với business owner

Thông báo như “dịch vụ đã phục hồi” nên gắn với **application/business SLO checks**, không chỉ firewall rule đã rollback. Timeline giúp tách **network restored**, **app healthy**, **business transaction confirmed** và **incident closed**.

## 21. Runbook lập timeline từ lúc mở incident đến khi chốt báo cáo

### Giai đoạn A — Xác định mục đích và phạm vi

1. Ghi **incident ID, severity, incident commander, network/service owners** và thời điểm bắt đầu điều tra.
2. Viết câu hỏi điều tra: **initial access? unauthorized connectivity? outage? data exposure? containment effective?**
3. Xác định **assets, identities, VLAN/VPC, gateways, VPN, ports/protocols** liên quan.
4. Đặt **working time window** đủ bao phủ precursor và hậu quả; không chỉ vài phút quanh alert.
5. Chỉ rõ **quyền truy cập log/PCAP**, retention, PII handling và những hệ thống không được phép chủ động kiểm tra.
6. Mở **evidence ledger** và **decision log** ngay từ đầu.

### Giai đoạn B — Thu evidence theo thứ tự ưu tiên

1. Xác định logs **dễ bị ghi đè/rotation**: firewall buffers, volatile devices, endpoint memory/connection state nếu playbook cho phép.
2. Export read-only **IdP/VPN/NAT/firewall/IDS/cloud/app logs** trong cửa sổ đã xác định.
3. Thu **clock sync status/timezone** cho từng nguồn, không chỉ raw timestamps.
4. Lưu **event IDs, parser versions, original query, collector time**, tạo hashes theo quy trình.
5. Xem **sensor coverage, packet loss, sampling và ingest delays**; không tạo khoảng trống âm thầm.
6. Tách **raw evidence** khỏi bản đã normalize hoặc redacted.

### Giai đoạn C — Normalize và xây timeline sơ bộ

1. Convert timestamps về **UTC** nhưng giữ raw timestamp, timezone và precision.
2. Gắn clock offset và **uncertainty interval** khi có evidence.
3. Phân loại event types: auth, network, detection, configuration, user action, containment, recovery.
4. Đặt **stable timeline event IDs** và evidence refs.
5. Sắp theo **corrected event time**; nếu các khoảng chồng lấp, không ép thứ tự.
6. Gộp duplicate collector records có kiểm soát, không xóa application retries.

### Giai đoạn D — Correlate và xác minh

1. Nối **identity ↔ VPN session ↔ assigned IP ↔ NAT mapping ↔ firewall flow ↔ app** bằng khóa đáng tin.
2. Kiểm tra **network hop changes** qua proxy/load balancer/mesh.
3. Tìm **negative evidence/counterexamples** phản bác giả thuyết.
4. Đánh dấu mọi attribution là **observed/corroborated/inferred/unknown**.
5. Thu **app/business audit** khi cần chứng minh thao tác dữ liệu, không suy từ TLS bytes.
6. Đưa mọi mâu thuẫn thời gian/source vào danh sách review, không tự bỏ qua.

### Giai đoạn E — Ghi và xác minh các biện pháp xử lý

1. Ghi **decision maker, approval, planned action và expected impact**.
2. Ghi **command/config request time và applied time** từ audit.
3. Có thể dùng **authorized negative test, session termination check và positive service test** để biết control thực có hiệu lực.
4. Theo dõi **credential revocation, session invalidation, rule propagation, device isolation** theo đúng loại control.
5. Ghi **rollback/failover/recovery timeline** và các mốc dịch vụ được người dùng xác nhận.
6. Tách **temporary containment** khỏi **permanent remediation**, có owner/expiry khi dùng exception.

### Giai đoạn F — Chốt timeline, review và truyền thông

1. Hoàn thiện bản **technical verified timeline** cùng uncertainty/unknowns.
2. Lập **executive summary** không phóng đại kết quả.
3. Bảo đảm **evidence refs mở được bởi người có quyền**, raw file hashes và access logs được giữ.
4. Rà **PII/credential redaction**, external disclosure process nếu liên quan.
5. Review **MTTD/MTTC/recovery metrics** với định nghĩa rõ.
6. Giao **corrective actions, owners, priorities, review dates**.
7. Đóng incident chỉ theo tiêu chí đã thống nhất, không vì timeline “đẹp” hoặc alert tự hết.

## 22. Công cụ và lệnh chỉ đọc phục vụ xây timeline

Các ví dụ ở mục này **được trình bày để người học thực hành trên file log thử thuộc quyền sở hữu**, không chạy trên dự án hiện tại. Không dùng lệnh bên dưới để đọc toàn ổ đĩa, log của người khác hoặc nơi chứa secrets không được cấp quyền.

### 22.1. Linux: xem dải timestamp trong log văn bản

~~~bash
# Ví dụ chỉ đọc local lab log; phải biết timezone/format thực của file.
# Không dùng grep output làm kết luận khi timestamp thiếu timezone.
grep '2026-11-28T09:' incident-lab.log
~~~

**Giới hạn:** grep là text search, không chuẩn hóa time. Nếu log có **UTC+07, epoch milliseconds hoặc multiline events**, một grep theo chuỗi giờ có thể bỏ sót hoặc nhầm record.

### 22.2. Linux: xác minh trạng thái đồng bộ giờ

~~~bash
# Chỉ kiểm tra trên host lab có quyền, không thay đổi cấu hình.
timedatectl status
timedatectl timesync-status
~~~

Tùy distro/systemd và công cụ NTP đang chạy, một lệnh có thể không hỗ trợ hoặc không phản ánh toàn bộ chất lượng clock. Nếu dùng chrony trong môi trường có quyền:

~~~bash
chronyc tracking
chronyc sources -v
~~~

Các lệnh này phục vụ **quan sát time synchronization**. Đừng tự kết luận mọi log trước đó đều đúng giờ chỉ vì NTP **đang synchronized ở thời điểm điều tra**.

### 22.3. PowerShell: xem timezone trên máy được phép quản trị

~~~powershell
# Read-only, trên Windows lab do bạn sở hữu.
Get-Date -Format o
Get-TimeZone
w32tm /query /status
~~~

**Get-Date** là giờ máy ở thời điểm chạy, không thay thế bằng chứng lịch sử về clock offset. W32Time status chỉ hỗ trợ đánh giá; khi thiết bị đã bị drift trong quá khứ, cần **time service event logs** hoặc nguồn tham chiếu khác.

### 22.4. PowerShell: normalize ISO timestamp có offset

~~~powershell
# Chỉ dùng dữ liệu giả, không mở file dự án khác.
$raw = '2026-11-28T16:10:30+07:00'
$time = [DateTimeOffset]::Parse(
    $raw,
    [System.Globalization.CultureInfo]::InvariantCulture
)
$time.ToUniversalTime().ToString('o')
# Kỳ vọng: 2026-11-28T09:10:30.0000000+00:00
~~~

Với timestamp **không có timezone**, không nên parse và ngầm giả local system zone rồi coi kết quả là UTC đúng. Phải có **source timezone** đáng tin hoặc giữ giá trị chưa chuẩn hóa.

### 22.5. PowerShell: kiểm tra hash của artifact

~~~powershell
# Read-only với artifact thuộc phạm vi được cấp quyền.
Get-FileHash -Algorithm SHA256 -LiteralPath '.\incident-lab.jsonl'
~~~

Hash chỉ kiểm tra **bytes tại thời điểm tính**; không xác thực bản ghi đã được sinh từ thiết bị đáng tin hoặc đủ log.

### 22.6. jq: xem event time mà không thay raw file

~~~bash
# Input: JSON Lines test events đã sanitize.
# jq -r chỉ in ba field từ các record, không chỉnh nguồn.
jq -r '[.event_time_utc, .source_system, .event_name] | @tsv' \
  incident-lab.jsonl
~~~

Lệnh này không tự sắp thứ tự đúng nếu timestamps có chất lượng không đồng nhất. Chỉ nên sort sau khi **normalize UTC và đánh dấu uncertainty**.

### 22.7. TShark: packet timestamps và TCP flows trong lab

~~~bash
# PCAP do bạn tự capture trong lab, giới hạn field xuất.
tshark -r incident-lab.pcapng \
  -T fields \
  -e frame.time_epoch \
  -e ip.src -e tcp.srcport \
  -e ip.dst -e tcp.dstport \
  -e tcp.flags
~~~

TShark đọc packet timestamps của capture, không tự biết **clock skew tại máy capture**, NAT mapping hoặc user identity. Trường TCP sẽ trống đối với UDP/QUIC; phải phân loại transport trước khi diễn giải.

### 22.8. Giữ truy vấn và output reference

Khi một analyst dùng SIEM/EDR console, ghi **query string/filter, UTC range, source index, role, execution time, result count và export hash/reference**. Nếu sau này data retention xóa log, tổ chức vẫn có thể biết **bộ bằng chứng nào được xem lúc quyết định**.

## 23. Ví dụ truy vấn chỉ đọc và những lỗi khi lọc dữ liệu

### 23.1. SQL minh họa sau khi đã normalize

~~~sql
-- PSEUDO-SQL chỉ để diễn giải; không chạy lên production.
-- Giả định event_time_utc đã được chuẩn hóa và kiểm tra quality.
SELECT
    incident_id,
    timeline_event_id,
    event_time_utc,
    time_uncertainty_ms,
    source_system,
    event_name,
    evidence_id,
    confidence
FROM normalized_timeline_events
WHERE incident_id = 'INC-LAB-2026-009'
ORDER BY event_time_utc, timeline_event_id;
~~~

**ORDER BY** chỉ sắp các point values hiển thị; nếu các time intervals overlap hoặc precision khác nhau, cần **hiển thị uncertainty và không tuyên bố thứ tự chắc chắn**.

### 23.2. Tìm ingest delay lớn

~~~sql
-- PSEUDO-SQL: cú pháp interval/difference tùy SQL engine.
SELECT event_id, source_system, event_time_utc, ingest_time_utc,
       ingestion_delay_seconds
FROM normalized_telemetry
WHERE ingestion_delay_seconds > 60
ORDER BY ingestion_delay_seconds DESC;
~~~

Ingestion delay lớn có thể do **queue/network retries/agent offline**. Nếu source clock sai, phép đo delay cũng có thể sai. Kiểm tra **clock quality** trước khi giải thích.

### 23.3. Tìm duplicate source IDs một cách cẩn thận

~~~sql
SELECT source_system, source_record_id, COUNT(*) AS copy_count
FROM normalized_telemetry
WHERE incident_id = 'INC-LAB-2026-009'
GROUP BY source_system, source_record_id
HAVING COUNT(*) > 1;
~~~

Kết quả cho thấy candidate duplicates, **chưa chứng minh** tất cả record trùng đều là collector retries nếu source ID có thể được tái sử dụng hoặc event lifecycle có phiên bản.

### 23.4. Không sort string timestamp đa định dạng

Một phép sort từ điển trên:

~~~text
2026-11-28 16:10:30
2026-11-28T09:12:00Z
2026-11-28T16:09:00+07:00
173278... (epoch-like representation)
~~~

không thể đảm bảo thứ tự thời gian thực. Cần **parse theo source format** và chuẩn hóa timestamps có offset/timezone. Những giá trị thiếu timezone phải được **flag**, không âm thầm đưa vào cùng trục.

### 23.5. Bắt lỗi đơn vị epoch

Unix time có thể được xuất dưới dạng **seconds, milliseconds, microseconds hoặc nanoseconds**. Nhầm milliseconds thành seconds khiến timestamp thành ngày vô lý. Cần dựa vào **schema** và có sanity checks với incident window; không đoán đơn vị chỉ bằng số chữ số trong mọi trường hợp.

### 23.6. Log parsing multiline

Một stack trace hay một application audit record có thể gồm nhiều dòng. Nếu import mỗi dòng thành event riêng, timeline sẽ xuất hiện timestamp thiếu ngữ cảnh hoặc body text bị coi là event. Parser phải **nhận đúng record boundary**, có source ID và test fixtures.

## 24. Các metric IR lấy từ timeline và điều kiện đo

### 24.1. Time-to-detect và time-to-contain

Định nghĩa minh họa:

\[
T_{\mathrm{detect}} = t_{\mathrm{alert/confirmation}} -
                      t_{\mathrm{earliest\ observed\ relevant\ action}}
\]

\[
T_{\mathrm{contain}} = t_{\mathrm{containment\ effective}} -
                       t_{\mathrm{detection/declared}}
\]

Các mốc phải **được định nghĩa thống nhất**. Một tổ chức có thể chọn **alert created** hay **analyst confirmed** làm điểm kết thúc detection latency; không trộn hai định nghĩa giữa các kỳ báo cáo.

### 24.2. Dwell time

**Dwell time** thường đề cập khoảng thời gian đối thủ có mặt/hoạt động trong hệ thống trước khi được phát hiện hoặc loại bỏ, tùy định nghĩa tổ chức. Nó **không thể được xác định chính xác** chỉ từ first observed alert nếu initial compromise còn unknown. Nên dùng **estimated interval + confidence**, không đưa một con số chính xác giả.

### 24.3. Recovery time và business impact

Recovery có nhiều lớp:

- **Network connectivity restored**: route/firewall/TLS/gateway hoạt động.
- **Application SLO restored**: synthetic/real-user tests đạt mục tiêu.
- **Business operation confirmed**: transaction workflow quan trọng chạy được.
- **Security controls restored**: những protections tạm bypass đã được khôi phục/compensated.

Không kết luận sự cố khắc phục hoàn toàn chỉ vì ping/traceroute thành công nếu app vẫn trả lỗi hoặc access policy còn fail-open.

### 24.4. Metric của bài học, không chỉ kết quả IR

Đội IR có thể theo dõi chất lượng ghi timeline:

| Metric | Ý nghĩa |
| --- | --- |
| **Evidence-linked event percentage** | Tỷ lệ dòng timeline có source evidence reference |
| **Time normalized with known zone** | Tỷ lệ timestamp xác định được timezone/offset |
| **Clock-quality coverage** | Số hệ log quan trọng có bằng chứng NTP/clock status |
| **Unknown/contradicted events** | Các mốc còn nghi ngờ cần review |
| **Timeline update lag** | Thời gian từ source event ingest tới lần cập nhật timeline |
| **Containment effect verification rate** | Tỷ lệ hành động có dataplane/session-level confirmation |
| **Preserved raw artifacts** | Tỷ lệ evidence có provenance/integrity controls |
| **Source coverage** | Số vùng mạng/identity/app bắt buộc có telemetry phù hợp |

**Chất lượng timeline tốt không đồng nghĩa incident rủi ro thấp**, nhưng giúp điều tra và quyết định ít sai hơn.

## 25. Tổ chức phối hợp và trách nhiệm review

### 25.1. Vai trò

| Vai trò | Trách nhiệm trên timeline |
| --- | --- |
| **Incident commander** | Xác định severity, mục tiêu, quyết định containment và status updates |
| **Timeline owner / scribe** | Giữ một timeline chính, stable IDs, change history, evidence links |
| **SOC analyst** | Thu IDS/SIEM/EDR/identity events, phân loại alerts |
| **Network engineer** | Xác minh routing, NAT, firewall, VPN, IP ownership và clock skew |
| **IAM/Endpoint owner** | Auth/session/revocation/device identity evidence |
| **Cloud/Platform owner** | Control-plane changes, cloud flow data, Kubernetes/network policy |
| **Application owner** | Request/transaction outcomes, business impact, SLO |
| **Privacy/Legal/Compliance** | Data handling, notifications và external disclosure theo quy định |
| **Reviewer** | Thách thức giả định, kiểm tra uncertainty, phản biện root-cause claims |

### 25.2. Một đầu mối timeline, nhiều người cung cấp evidence

Nên có **một canonical timeline** (versioned/owned) và phân quyền cho nhóm bổ sung facts. Nếu mỗi đội duy trì file riêng không đồng bộ, các mốc như “block request” có thể bị lẫn với “block effective”, làm báo cáo sau sự cố mâu thuẫn.

### 25.3. Handoff giữa ca

~~~text
Incident ID, severity, current owners:
Last verified timestamp / timeline version:
Current impact and containment status:
New evidence added in this shift:
Clock skew corrections and provenance:
Disputed/unknown events:
Critical gaps to collect before log rotation:
Pending decisions and approvals:
Expected next checks and time:
Data-handling restrictions:
~~~

Handoff không nên chỉ nói “đã xử lý hết”, mà phải có **action outstanding, những điều chưa kiểm chứng và người chịu trách nhiệm**.

### 25.4. Khi mốc thời gian có thể ảnh hưởng thông báo pháp lý

Một số nghĩa vụ thông báo phụ thuộc **thời điểm tổ chức biết/đánh giá một sự kiện**, không nhất thiết timestamp attacker bắt đầu. Các yêu cầu này thay đổi theo khu vực/loại dữ liệu/hợp đồng. Timeline cần giữ riêng **first observed, analyst confirmed, incident declared, impact assessment approved**, để bộ phận có thẩm quyền áp dụng quy định phù hợp, không suy tự động từ một log.

## 26. Kiểm soát phát tán timeline và bảo vệ riêng tư

### 26.1. Tách các loại thông tin

| Nội dung | Rủi ro khi chia sẻ | Giải pháp |
| --- | --- | --- |
| **Usernames và VPN identities** | Lộ thông tin nhân sự/đối tác | Token hóa/pseudonymize trong bản rộng |
| **Source/destination IP và internal topology** | Tiết lộ kiến trúc mạng | Restricted technical appendix |
| **Auth tokens/API keys/cookies** | Có thể bị tái sử dụng | Không lưu raw trong timeline; rotate nếu lộ |
| **DNS queries và URLs** | Có thể phản ánh hành vi cá nhân | Minimize/sanitize và RBAC |
| **PCAP** | Chứa payload hoặc sensitive metadata | Encrypted evidence store/TTL |
| **Business operations** | Dữ liệu tài chính/khách hàng | Chỉ chia sẻ transaction IDs và kết luận đủ thẩm quyền |
| **Attack path chưa khắc phục** | Tăng nguy cơ bị khai thác | Chỉ chia sẻ theo need-to-know |

### 26.2. Bản tóm tắt phải đúng nhưng không làm lộ điều không cần

Ví dụ bản kỹ thuật có thể ghi private tunnel IP cụ thể, trong khi executive report chỉ cần “một phiên contractor VPN chưa được ủy quyền đã truy cập tới vùng quản trị; connection bị chặn tại ứng dụng”. **Bỏ bớt chi tiết nhạy cảm không được phép biến “attempt” thành “successful compromise”**.

### 26.3. Quyền truy cập và kiểm toán thay đổi

Timeline và evidence store nên có:

- **Role-based access**.
- Quy tắc **append/change audit** cho các bản sửa.
- Mốc **who viewed/exported** artifacts nhạy cảm.
- **Retention/destruction** theo incident severity và nghĩa vụ.
- Review trước khi chia sẻ bên ngoài.

### 26.4. Không dùng timeline để gán lỗi cá nhân thiếu căn cứ

Một public NAT IP hoặc một IdP login không đủ chứng minh một cá nhân đã thực hiện malicious action. Nếu cần attribution, phải có **authenticated identity, device/process, session mapping và corroboration**. Giữ **privacy, fairness và confidence labels** khi phân tích hành vi nhân viên.

## 27. Case study 1 — Firewall clock nhanh làm đảo thứ tự sự kiện

### 27.1. Tình huống giả định

Một VPN gateway ghi phiên bắt đầu lúc **10:01:00Z**, firewall log ghi một traffic flow liên quan lúc **10:02:35Z**, trong khi application audit cho thấy request lúc **10:01:10Z**. Analyst kết luận firewall traffic xuất hiện **sau khi ứng dụng xử lý request**, nên cho rằng request không đi qua firewall.

### 27.2. Điều tra time source

Đội Network xác minh **firewall clock nhanh 90 giây ±5 giây** trong khoảng đó. Khi hiệu chỉnh:

~~~text
VPN session started:       10:01:00Z
Firewall raw flow time:    10:02:35Z
Firewall corrected time:  10:01:05Z +/-5s
Application request:       10:01:10Z
~~~

Timeline sau hiệu chỉnh **không còn mâu thuẫn rõ như ban đầu**, nhưng vì firewall time có uncertainty, không nên tuyên bố flow chắc chắn trước application request đến từng giây nếu các khoảng overlap.

### 27.3. Các bước cần làm

1. Lưu nguyên **raw firewall record** và event ID.
2. Thu **NTP/clock correction evidence** với đúng time window.
3. Tính **corrected time + uncertainty**, có reviewer.
4. Correlate **5-tuple/NAT/proxy connection ID** nếu cần xác nhận đó là cùng flow.
5. Ghi bản **timeline revision** và lý do sửa thứ tự.
6. Nếu log source có clock jumps, chia correction theo từng đoạn thời gian.

**Bài học:** so sánh timestamps khác nguồn trước khi kiểm tra clock có thể dựng nên một **false causal story**.

## 28. Case study 2 — Route change và network outage

### 28.1. Tình huống giả định

Người dùng báo mất kết nối ứng dụng từ 14:03 đến 14:18. Trước đó, một hệ thống automation thay route trong VPC lúc 14:02. Đội vận hành nghi route change làm mất ứng dụng.

| UTC | Quan sát | Nguồn | Chưa thể kết luận |
| --- | --- | --- | --- |
| 14:02:00 | API cập nhật route table accepted | Cloud control-plane audit | Route có hiệu lực toàn mạng ngay lúc này? |
| 14:02:20 | Routing policy distributed tới một zone | Cloud/network telemetry | Tất cả nodes đã converge? |
| 14:03:10 | Synthetic test từ Zone A thất bại | SRE test | Do route hay app DNS/TLS? |
| 14:04:00 | Packet drop counters tăng tại gateway | Network metrics | Cần xác định đích và route selection |
| 14:08:00 | Incident declared, rollback approved | Decision log | Rollback đã triển khai chưa? |
| 14:10:00 | Route rollback API accepted | Cloud audit | Dataplane đã quay lại chưa? |
| 14:12:30 | Network path test qua Zone A thành công | Authorized test | Đường này đã hồi phục |
| 14:18:00 | App synthetic+business check qua nhiều zone đạt | App/SRE | Service phục hồi theo phạm vi test |

### 28.2. Phân tích

Để gắn **route change là nguyên nhân**, cần chứng cứ:

- Đúng route table gắn với subnet/gateway bị ảnh hưởng.
- Route ưu tiên/chọn next hop thay đổi như giả thuyết.
- Traceroute/flow logs/packet drops và app synthetic tests ở nguồn hợp lệ.
- Không có DNS, application deploy hoặc upstream outage độc lập cùng thời điểm.
- Recovery correlation với route rollback và dataplane convergence.

**API cập nhật route thành công không đủ** chứng minh route đã có hiệu lực tại đúng thời điểm mất gói.

### 28.3. Kết luận có giới hạn

Nếu evidence đủ, có thể ghi “route update liên quan tới mất kết nối ở Zone A, dịch vụ phục hồi sau khi dataplane revert”. Nếu còn source gaps, ghi **probable contributing factor** với confidence, không gắn “root cause confirmed” chỉ vì hai mốc gần nhau.

## 29. Case study 3 — IDS alert nhiều lần bị gọi nhầm là nhiều cuộc tấn công

### 29.1. Bối cảnh giả định

IDS phát **1.200 alerts trong 3 phút** cho cùng source/destination và rule. Dashboard tạm thời nói “1.200 lần khai thác”. App owner xác nhận endpoint không có request hợp lệ nào tới backend.

### 29.2. Những thứ cần tách

- Số **IDS rule matches**.
- Số **distinct network connections**.
- Số **HTTP/2 streams/requests** nếu protocol phù hợp.
- Số **attempts được nhận ở gateway/WAF**.
- Số **application operations**.
- Số **confirmed malicious actions**.

1.200 rule matches có thể do retransmissions, repeated probes, retry loops, packet-level signature semantics hoặc một campaign, **không đồng nghĩa 1.200 khai thác thành công**.

### 29.3. Timeline chuẩn hóa

~~~text
15:00:00Z - 15:03:00Z  IDS alert burst:
                          rule R-1000, count 1,200
                          first/last event references retained
15:00:10Z                 Firewall blocks related flow (policy evidence)
15:00:12Z                 Proxy receives no corresponding app request
15:04:00Z                 SOC triage opens investigation
15:07:00Z                 Evidence reviewed: maliciousness still unconfirmed
~~~

Kết luận phù hợp là **“1.200 signature matches được quan sát trong ba phút”**, kèm điều tra status, không đổi chúng thành số **confirmed intrusions**.

### 29.4. Khi nào được xác nhận tấn công?

Cần ground truth hoặc evidence đủ tin cậy từ **packet/protocol details, endpoint/app logs, authorized test records, threat intelligence và incident scoping**. Một rule match có thể mang ý nghĩa nguy cơ cao, nhưng mức khẳng định phải đúng nguồn.

**Bài học:** timeline phải giữ **count, first/last timestamps và representative evidence**, đồng thời phân biệt alert, attempt và outcome.

## 30. Case study 4 — Cloud audit log đến sau nhưng mô tả hành động sớm hơn

### 30.1. Tình huống giả định

Một security group bị nới rules lúc **07:50:00Z**, VPC flow log thấy connection lúc **07:51:30Z**, nhưng audit của cloud control plane được index vào SIEM tận **08:05:00Z**. Một analyst xem SIEM theo ingest order thấy flow trước config change nên bỏ qua giả thuyết policy change.

### 30.2. Cách ghi timeline

| Trường | Giá trị giả định |
| --- | --- |
| Cloud API event_time | 07:50:00Z |
| Cloud API ingest_time | 08:05:00Z |
| VPC flow_start | 07:51:30Z |
| VPC flow ingest_time | 07:55:00Z |
| API change result | API accepted; chưa xác nhận full dataplane convergence |
| Investigation note | Time ordering nên dựa trên event_time và clock quality |

### 30.3. Biện pháp

1. Dùng **event-time view** thay SIEM arrival-time view.
2. Lưu **eventTime, receivedTime và ingestion lag**.
3. Xác minh **resource IDs, security group attachments, effective policies**.
4. Ghép **flow start/end, source/destination, port và route**.
5. Test direct path trong phạm vi được phép để xác định rule hiện có hiệu lực hay không.
6. Ghi rõ mốc **policy applied** nếu có audit/dataplane evidence riêng.

**Bài học:** thứ tự ingest logs không phải thứ tự thay đổi hạ tầng, và audit control-plane không tự chứng minh flow được phép chỉ vì nằm gần nhau.

## 31. Case study 5 — IdP disable thành công nhưng phiên ứng dụng vẫn sống

### 31.1. Tình huống giả định

Đội phản ứng nghi một tài khoản vendor bị chiếm. IdP disable account lúc **11:20:00Z**, VPN gateway dừng phiên lúc **11:20:40Z**, nhưng ứng dụng có **browser session cookie** được cấp trước đó, vẫn chấp nhận một thao tác tới **11:34:00Z** thông qua một proxy route khác.

### 31.2. Ba ranh giới khác nhau

~~~text
11:20:00Z  Identity account disabled
11:20:40Z  Existing VPN tunnel terminated
11:21:00Z  New VPN login denied (tested)
11:34:00Z  Existing application session finally invalidated

Identity disable:
  stops or restricts new identity operations under IdP policy.

VPN termination:
  stops a specific network access tunnel.

Application session invalidation:
  ends the app's acceptance of an already issued session.
~~~

Không một mốc đơn lẻ nào thay thế được hai mốc còn lại. Với một user có **API token/service credential** hoặc đường ZTNA khác, còn cần kiểm tra thêm identity/session scopes liên quan.

### 31.3. Timeline phải ghi cả hai loại kiểm thử

- **Negative control:** token/session đã revoke không còn được dùng để thực hiện hành động có quyền.
- **Positive control:** ứng dụng vẫn khỏe và user hợp lệ còn được phép truy cập.

Nếu negative request timeout vì toàn bộ app đang down, chưa thể chứng minh policy revoke hoạt động.

### 31.4. Bài học

**Effective containment time** cho một sự cố credential abuse phải tính đến **active sessions, alternate paths và downstream credentials** theo scope, chứ không dừng tại thời điểm nhấn nút Disable trong IdP.

## 32. Case study 6 — Khoảng trống log do packet sensor outage

### 32.1. Tình huống giả định

NDR sensor ghi logs từ **13:00 đến 13:11**, sau đó không có traffic trong 9 phút; sensor bắt đầu ghi lại lúc **13:20**. Firewall cùng lúc vẫn thấy flows từ các hosts bình thường.

### 32.2. Hai giả thuyết

- Có thể toàn bộ network traffic ngừng thật.
- Có thể **sensor/collector bị lỗi hoặc một đường mới đi ngoài vantage**.

Không được dùng **NDR event_count=0** làm bằng chứng “network đã sạch” trước khi kiểm tra sensor health, interface counters, firewall flow logs và routes.

### 32.3. Dòng timeline phù hợp

~~~text
13:11:00Z  Last NDR event observed on sensor S2
13:11:15Z  Collector heartbeat missing
13:12:00Z  Firewall continues to log allowed connections
13:20:00Z  NDR sensor S2 resumes event delivery

Unknown interval:
  13:11-13:20Z network traffic details unavailable from S2.
  Do not infer absence of suspicious traffic in this interval.
~~~

### 32.4. Khắc phục

1. Ghi **sensor outage start/end**, source health, backlog và packet drops.
2. Dùng **alternate authorized sources** như firewall/NAT/EDR/app logs để điều tra khoảng thiếu.
3. Không tự dựng packet-level events chưa tồn tại.
4. Xem log backlog có **original event_time** hay chỉ ingest time.
5. Bổ sung HA/coverage alert để lần sau phát hiện sensor outage sớm.

**Bài học:** trong điều tra, **một khoảng trống bằng chứng cũng là sự kiện quan trọng cần đưa vào timeline**.

## 33. Những sai lầm phổ biến khi ghi timeline sự cố mạng

1. **“Log nào xuất hiện trong SIEM trước thì event xảy ra trước.”** Ingest order không phải event-time order.
2. **“Tất cả timestamps đều đã ở UTC.”** Thiết bị có thể ghi local time, offset hoặc epoch.
3. **“CST là timezone đủ rõ.”** Abbreviation có thể mơ hồ; cần identifier và historical rules.
4. **“Có .123456 là timestamp chính xác tới microsecond.”** Precision khác clock accuracy.
5. **“NTP hiện đang OK thì log hai giờ trước chắc chắn đúng.”** Clock có thể jump/drift theo giai đoạn.
6. **“Sửa raw timestamps trực tiếp sẽ dễ đọc hơn.”** Cần giữ original evidence, thêm derived corrected time.
7. **“Hai sự kiện cách nhau 1 giây chắc chắn có thứ tự.”** Time uncertainty intervals có thể overlap.
8. **“Một DNS query chứng minh client đã vào website.”** Cache/prefetch/shared CDN làm attribution có điều kiện.
9. **“Firewall allow đồng nghĩa app chấp nhận thao tác.”** Network policy khác application result.
10. **“IDS alert đồng nghĩa exploit thành công.”** Alert là tín hiệu, cần kiểm chứng.
11. **“Một NAT public IP xác định được một người.”** Nhiều clients có thể dùng cùng IP.
12. **“X-Forwarded-For luôn là source IP thật.”** Header có thể bị client tự khai.
13. **“DHCP lease hiện tại chứng minh IP thuộc thiết bị đó trong quá khứ.”** Kiểm tra lease interval và reuse.
14. **“Pod IP là định danh workload lâu dài.”** Pod IP có thể tái sử dụng; cần Pod UID và lifecycle.
15. **“HTTP 200 nghĩa tiền đã chuyển.”** Business operation cần transaction audit.
16. **“VPN login thành công nghĩa user đã đọc được DB.”** Cần đường đi, quyền và app access evidence.
17. **“Account disabled nghĩa mọi phiên chết ngay.”** Existing sessions/tokens có thể vẫn sống.
18. **“Firewall rule updated nghĩa containment đã hiệu lực.”** Cần dataplane/session verification.
19. **“Ping thành công nghĩa ứng dụng phục hồi.”** Kiểm tra app SLO và business workflow.
20. **“Không thấy log là không có hoạt động.”** Có thể do sensor coverage/retention/outage.
21. **“NetFlow record created time là flow start time.”** Export có thể được gửi khi flow end/timeout.
22. **“Một TCP retransmission là retry ứng dụng.”** Transport repeat không tự thêm business operation.
23. **“Một TLS connection là một HTTP request.”** HTTP/2/3 multiplex có nhiều requests.
24. **“SNI cho biết URL/body và hành vi người dùng.”** SNI là TLS handshake hint, ECH còn có thể che.
25. **“PCAP luôn là ground truth về user và dữ liệu.”** Capture có clock skew, loss, encryption và NAT gaps.
26. **“Một service account luôn thuộc một người dùng.”** Machine identities có thể được dùng bởi nhiều workloads.
27. **“Hai events gần giờ nhau chứng minh A gây B.”** Temporal correlation không tự là causation.
28. **“Mỗi alert phải là một hàng riêng.”** Có thể aggregate bursts có lưu count/first/last/evidence.
29. **“Cứ dedupe mọi log giống nhau.”** Có thể xóa requests/attempts riêng thật.
30. **“Chỉ giữ các record phù hợp giả thuyết.”** Bỏ evidence phản bác làm báo cáo thiếu khách quan.
31. **“Sửa timeline là xóa dòng cũ.”** Nên giữ revision history và lý do.
32. **“Một timestamp thiếu timezone có thể mặc định theo máy analyst.”** Đây là suy đoán có thể sai.
33. **“Epoch 13 chữ số luôn là seconds.”** Cần schema/units, kiểm tra millisecond vs seconds.
34. **“Mọi logs có độ tin cậy như nhau.”** Sensor có thể bị tampered/offline, source clock không đồng bộ.
35. **“Hash file chứng minh event thực sự xảy ra.”** Hash chứng minh integrity của bytes, không xác minh nội dung.
36. **“Alert time là first compromise time.”** Initial access có thể sớm hơn nhiều.
37. **“Incident declared time là first detected time.”** Analyst có thể xác minh trước hoặc sau declaration.
38. **“Containment issued time là containment effective time.”** Đó là các mốc khác.
39. **“Recovery khi route hồi phục là incident closed.”** Cần security controls và business validation.
40. **“Lưu toàn bộ token/PII vào timeline để tiện điều tra.”** Không phù hợp data minimization.
41. **“Đưa raw PCAP vào executive report là cần thiết.”** Có thể chia sẻ tóm tắt/redacted references.
42. **“Không cần log mốc rollback.”** Bỏ qua rollback gây hiểu sai trạng thái chính sách.
43. **“Chỉ cần thuật lại sự cố một lần sau khi kết thúc.”** Timeline nên sống, có version và ghi quyết định kịp thời.
44. **“Nếu clock skew chưa rõ cứ chọn thời gian trung bình và coi là chính xác.”** Phải dùng uncertainty interval.
45. **“Một metric MTTD có thể so sánh mọi tổ chức.”** Cần cùng định nghĩa và population.
46. **“Nếu chưa chứng minh exfiltration thì có thể ghi không có exfiltration.”** Chỉ ghi không thấy trong sources đã kiểm tra.
47. **“Không cần lưu parser/query version.”** Thay parser làm thay nghĩa field/trend.
48. **“Một SIEM dashboard đẹp hơn điều tra chi tiết.”** Presentation không thay provenance và review.

## 34. Bài thực hành offline: dựng timeline từ log giả

Bài thực hành này **không cần mạng hoặc truy cập hệ thống thật**. Người học nhận một tập records giả, chuẩn hóa timestamps và quyết định những gì có thể kết luận. Không mở thêm log ngoài lab.

### 34.1. Input giả định

~~~json
[
  {
    "source": "vpn",
    "raw_time": "2026-11-28T16:00:10+07:00",
    "event": "vpn_login_accepted",
    "session": "vpn-test-1"
  },
  {
    "source": "firewall",
    "raw_time": "2026-11-28T09:02:15Z",
    "event": "outbound_flow_allowed",
    "session": "fw-test-1"
  },
  {
    "source": "siem",
    "raw_time": "2026-11-28T09:03:40Z",
    "event": "alert_created",
    "related": "vpn-test-1"
  },
  {
    "source": "idp",
    "raw_time": "2026-11-28T09:04:20Z",
    "event": "account_disabled",
    "principal": "test-user-1"
  }
]
~~~

Thông tin bổ sung do bài tập cung cấp:

- VPN log có timezone rõ ràng **+07:00**.
- Firewall clock **nhanh 120 giây ±10 giây** trong khoảng điều tra.
- SIEM và IdP timestamps UTC được kiểm tra trong giới hạn ±2 giây.
- Firewall record chỉ cho biết **flow allow**, chưa có app/transaction evidence.
- Không có VPN session termination log trong input này.

### 34.2. Các bước thực hiện

1. Chuyển VPN time **16:00:10+07:00** thành **09:00:10Z**.
2. Hiệu chỉnh firewall raw **09:02:15Z** trừ **120 giây**, thành **09:00:15Z ±10 giây**.
3. Sắp timeline theo normalized time nhưng giữ uncertainty.
4. Ghi mốc alert và account disabled riêng, không coi disable là effective containment.
5. Nêu **những gì chưa biết**: app access, user/device attribution, VPN active session sau disable.
6. Đề xuất hai nguồn evidence tiếp theo: **VPN termination/session logs** và **app/PEP negative test result**.

### 34.3. Kết quả kỳ vọng

| UTC đã chuẩn hóa | Event | Evidence level |
| --- | --- | --- |
| 09:00:10Z | VPN test login accepted | Observed auth event |
| 09:00:15Z ±10s | Firewall flow allowed | Observed flow, corrected time |
| 09:03:40Z | SIEM alert created | Observed alert |
| 09:04:20Z | IdP account disabled | Observed control change |

Không thể chắc chắn **VPN login trước firewall flow** vì firewall uncertainty interval là **09:00:05–09:00:25**, bao trùm 09:00:10. Trong bản kết quả, có thể hiển thị theo corrected point time nhưng phải đánh dấu **relative order uncertain**.

### 34.4. Tiêu chí đạt

- Không xóa **raw_time**.
- Ghi **UTC timezone, precision và offset**.
- Không kết luận **app operation succeeded** từ firewall allow.
- Không kết luận **active VPN session terminated** từ IdP disabled.
- Đề xuất evidence có thể **xác minh giả thuyết**, không phải chỉ thêm alert count.

## 35. Ma trận kiểm thử chất lượng timeline và bằng chứng

Các tests dùng **mock logs, lab hệ thống thuộc quyền quản trị hoặc tabletop exercise**. Không thay firewall/account thật khi chưa được incident commander/chủ hệ thống phê duyệt.

| Test | Điều kiện kiểm thử | Expected result |
| --- | --- | --- |
| **T1 – Offset đúng** | 16:10:30+07:00 | Convert thành 09:10:30Z |
| **T2 – Timezone missing** | 16:10:30 không có zone | Mark unknown zone, không tự coi UTC |
| **T3 – DST historical conversion** | Log từ vùng DST theo ngày lịch sử | Dùng IANA zone/time rules thích hợp |
| **T4 – Epoch units** | seconds vs milliseconds | Parser dựa schema, không nhầm ngày |
| **T5 – Clock skew** | Firewall fast +90s | Giữ raw; corrected time và uncertainty |
| **T6 – Time overlaps** | Hai events có intersecting intervals | Không ép thứ tự chắc chắn |
| **T7 – Late SIEM delivery** | Event đến sau vài phút | Event order theo event_time, ingestion lag riêng |
| **T8 – Duplicate collector log** | Một source_event_id được gửi lại | Analytics dedupe có provenance |
| **T9 – True repeated action** | Hai VPN logins khác session IDs | Không gộp thành một event |
| **T10 – NAT attribution** | Nhiều private clients chung public IP | Match 5-tuple/time interval, không gán theo IP alone |
| **T11 – DHCP reuse** | IP đổi lease owner | Dùng lease tại đúng event time |
| **T12 – Pod IP reuse** | Pod A bị xóa, Pod B dùng lại IP | Dùng Pod UID và lifecycle |
| **T13 – TLS opacity** | HTTPS/QUIC encrypted traffic | Không suy URL/body từ flow metadata |
| **T14 – IDS burst** | 1.000 duplicate-looking alerts | Aggregate count mà không gọi 1.000 exploits |
| **T15 – Sensor outage** | NDR không gửi logs 10 phút | Hiện unknown interval và coverage gap |
| **T16 – Control-plane action** | Cloud SG API accepted | Không ghi dataplane effective nếu chưa kiểm chứng |
| **T17 – VPN revoke** | Account disabled, tunnel còn open | Mốc containment vẫn partial |
| **T18 – App cookie lifetime** | Session cũ còn usable | Effective revoke đo đến app |
| **T19 – Firewall allow** | Connection allowed, app 403 | Không ghi app success |
| **T20 – Route outage** | Cloud route change + app errors | Causal claim cần network evidence |
| **T21 – PCAP clock** | Capture host offset | Timestamp correction và source reference |
| **T22 – Contradictory logs** | Proxy/app disagree | Disputed state, review queue |
| **T23 – Raw integrity** | Artifact bytes bị thay | Hash mismatch surfaced, không âm thầm dùng |
| **T24 – Sensitive log data** | Synthetic token xuất hiện | Redacted output, raw restricted |
| **T25 – Incident handoff** | Đổi analyst giữa ca | Timeline version, pending evidence và decisions được chuyển |
| **T26 – Effective containment** | Rule issued nhưng deny test chưa đạt | Không đánh dấu verified |
| **T27 – Positive control** | Negative test fail do app down | Không chấm policy PASS thiếu app health |
| **T28 – Rollback** | Rule rollback sau outage | Timeline ghi issued/applied/effective và reversal |
| **T29 – Unknown timeframe** | OT log chỉ có 5-minute bucket | Ghi interval, không bịa timestamp |
| **T30 – External disclosure** | Executive timeline cần chia sẻ | Redaction và legal/privacy review |

### 35.1. Test pass phải có evidence

Một phép kiểm thử **đạt** khi kết quả đúng điều kiện và có:

- **Fixture/test ID**.
- Source systems và timezone.
- Raw event + normalized event.
- Expected ordering/uncertainty.
- Negative/positive controls nếu đo containment.
- Reviewer, result và known limitations.

Một bảng test có **30/30 PASS** chỉ chứng minh các tình huống đã thử; không cho phép tuyên bố mọi incident future sẽ có timeline chính xác tuyệt đối.

### 35.2. Regression khi parser và sources đổi

Khi nâng SIEM parser, đổi firewall vendor, chuyển cloud region hoặc thay IdP, chạy lại tests cho **time zone, source event ID, NAT mapping, session lifecycle và evidence references**. Một thay đổi schema có thể khiến dashboard vẫn chạy nhưng âm thầm sai thứ tự.

## 36. Bài tập vận dụng và gợi ý đáp án

### Bài 1 — Chuẩn hóa giờ

Một router ghi **2026-11-28 16:30:00** theo timezone Asia/Ho_Chi_Minh. IdP ghi **2026-11-28T09:30:01Z**. Hai record gần thời gian nhau không?

**Gợi ý:** router event là **09:30:00Z**, cách IdP một giây theo display timestamps. Tuy nhiên, chưa biết NTP skew/precision và correlation nên không khẳng định thứ tự causal nếu cần độ chính xác cao.

### Bài 2 — Sửa clock skew mà không sửa evidence

Firewall raw timestamp **10:05:40Z**, đồng hồ nhanh **120 ±10 giây** trong cửa sổ sự cố. Tính corrected time và range.

**Gợi ý:** corrected **10:03:40Z**, uncertainty interval **10:03:30Z–10:03:50Z**. Giữ raw time và evidence về nguồn offset.

### Bài 3 — So sánh time intervals

Event A có corrected time **10:00:00Z ±30 giây**; event B **10:00:20Z ±5 giây**. Có thể chứng minh A trước B không?

**Gợi ý:** A interval 09:59:30–10:00:30, B 10:00:15–10:00:25. Hai khoảng overlap; **thứ tự chưa chắc**.

### Bài 4 — SIEM ingest delay

Một cloud IAM change xảy ra 08:30, đến SIEM 08:47. Một VPC flow xảy ra 08:31 và đến SIEM 08:32. Vì record VPC xuất hiện trên dashboard trước, có thể nói flow dẫn tới IAM change không?

**Gợi ý:** không. **Event time** của IAM sớm hơn flow; ingestion order đảo do delay. Việc IAM change gây flow vẫn là giả thuyết cần kiểm tra attachments và policy effect.

### Bài 5 — VPN, NAT và user

Firewall thấy **public NAT IP 203.0.113.40:53010** kết nối admin service. Một VPN user login cùng phút đó. Có thể xác định user là thủ phạm không?

**Gợi ý:** không. Cần **NAT translation mapping gồm port và time**, tunnel IP/session interval và identity/endpoint evidence. Một public IP không phải unique user identity.

### Bài 6 — DNS và application operation

DNS log ghi query cho **api.partner.example** lúc 12:00, firewall log thấy TLS connection tới IP cùng phút. Incident note viết “user đã upload dữ liệu tới partner lúc 12:00”.

**Gợi ý:** kết luận vượt evidence. DNS query và TLS flow không cho biết **HTTP method/body, user hoặc successful upload**. Cần proxy/app/SaaS audit/DLP/endpoint evidence có quyền.

### Bài 7 — Đánh giá MTTD

First observed relevant event lúc **08:00**, alert created **08:12**, analyst confirmed **08:15**. Nếu SLO phát hiện dùng **alert time**, độ trễ bao lâu? Nếu dùng analyst confirmation?

**Gợi ý:** lần lượt **12 phút và 15 phút**. Báo rõ định nghĩa thay vì gộp thành “MTTD 12 phút” mà không nêu mốc.

### Bài 8 — Containment hiệu lực

Incident commander phê duyệt firewall deny lúc **13:00**, commit xong **13:01**, nhưng flow tới target vẫn được allow trên một gateway cho tới **13:04**. Negative test mới xác minh denied lúc **13:05**.

**Gợi ý:** 13:00 là approval, 13:01 là config commit, **13:05** là mốc kiểm chứng containment với test được nêu. Không tự tuyên bố rule effective lúc 13:01.

### Bài 9 — Negative evidence

EDR agent trên laptop offline 09:00–10:00. Không có alerts liên quan máy đó trong giờ này. Có thể ghi “laptop không bị tấn công” không?

**Gợi ý:** không. Ghi **EDR coverage gap**, dùng firewall/DNS/IdP/app evidence khác, đánh dấu **unknown** trong khoảng thiếu.

### Bài 10 — IDS alert burst

IDS ghi 500 rule matches trong 2 phút từ cùng một network flow. Backend log không có request nào. Nêu event timeline phù hợp.

**Gợi ý:** ghi **500 signature matches, first/last time, rule/source/flow IDs**, kiểm tra firewall/WAF logs. Không biến thành “500 successful exploits”.

### Bài 11 — Account disable và existing session

IdP disable user lúc 10:00, VPN session dừng lúc 10:03, app session cũ còn chấp nhận API tới 10:17. Effective access revocation của app là bao lâu tính từ t0?

**Gợi ý:** **17 phút** theo evidence bài toán, trong khi new VPN access và tunnel termination có các mốc khác. Kiểm tra alternate access/token scope.

### Bài 12 — Dùng timeline để phản biện root cause

Route thay lúc 14:02, outage bắt đầu 14:03, rollback lúc 14:10 và service phục hồi 14:18. Chỉ chuỗi mốc này có đủ kết luận route là root cause không?

**Gợi ý:** là giả thuyết mạnh nhưng cần **route attachment, dataplane convergence, flow/drops và exclusion of co-occurring app/DNS issues**, cùng tests để củng cố nhân quả.

### Bài 13 — Bảo quản bằng chứng

Một analyst export log, chỉnh timezone ngay trong file gốc, xóa những rows trùng và chỉ lưu CSV đã “làm sạch”. Điều gì chưa đúng?

**Gợi ý:** mất **raw provenance, timestamp gốc và duplicate semantics**. Nên giữ raw artifact có hash/metadata, tạo bản normalized riêng và log transformations.

### Bài 14 — Xây timeline cho sự cố mất DNS

Một ứng dụng không resolve được domain từ 09:15 đến 09:27. Nguồn có: resolver logs, DNS query metrics, DHCP, firewall rules, deployment records, app error rates. Hãy thiết kế các mốc bắt buộc.

**Gợi ý:** first failed resolution, resolver health, config/deploy change, network path/port 53/DoT availability, retry/cache effects, containment/rollback, negative/positive DNS tests, app recovery và unknown intervals.

### Bài 15 — Bản executive và bản kỹ thuật

Timeline kỹ thuật gồm client IP, VPN username, partner hostname, raw URI có PII và packet capture. Lãnh đạo chỉ cần biết tác động, thời gian phát hiện và containment.

**Gợi ý:** executive view nên dùng **resource class, affected cohort, major UTC milestones, confirmed impact, current residual risk và next actions**, tránh raw credentials/PII/topology; vẫn giữ liên kết tới bản kỹ thuật được kiểm soát.

### Bài 16 — Thiết kế một pipeline có thể tái lập

Đề xuất cách hợp nhất **IdP, VPN, NAT, NGFW, IDS, cloud flow và app logs** cho sự cố nghi exfiltration. Trong bài nêu:

1. Canonical event schema và raw artifact references.
2. Timezone/offset/precision/clock quality.
3. Identity/session/NAT correlation keys.
4. Alert/flow/app evidence được phân loại theo confidence.
5. First-seen vs first-confirmed timeline.
6. Containment action/implemented/effective milestones.
7. Missing sensors và uncertainty intervals.
8. Privacy/redaction và evidence chain.
9. Detection/containment/recovery metrics có định nghĩa.
10. Decision ownership và post-incident revisions.

**Gợi ý:** trình bày trước **network path và trust boundaries**, sau đó mới normalize logs. Không coi một source duy nhất là ground truth toàn bộ incident.

## 37. Checklist hoàn tất timeline sự cố mạng

| Câu hỏi | Bằng chứng/kết quả mong đợi |
| --- | --- |
| Có incident ID, scope, severity và owner? | Incident record, commander |
| Có time window bao phủ precursor và recovery? | Scope notes, source retention |
| Phân biệt alert time và first observed event time? | Event IDs, time definitions |
| Mỗi event có raw timestamp và source timezone? | Raw evidence |
| Các timestamps đã normalize UTC đúng quy tắc? | Parser/zone conversion notes |
| Đã kiểm tra precision, clock skew và NTP/PTP khi cần? | Time source evidence |
| Uncertainty intervals có được hiển thị? | Corrected time, confidence ranges |
| Không ép thứ tự hai events có overlapping intervals? | Timeline reviewer check |
| Có giữ event time và ingestion time riêng? | Schema/data contract |
| Source logs đã được export read-only đúng scope? | Collection manifest |
| Evidence có source record IDs và references? | Evidence ledger |
| Raw artifacts có integrity/chain-of-custody controls? | Hash/collection/access logs |
| Parser/normalizer phiên bản nào đã dùng? | Config/release metadata |
| Dedupe có phân biệt collector retry và action thật? | Dedupe policy/test |
| Firewall/VPN/NAT mappings đúng session interval? | NAT/session references |
| DHCP/IPv6/Pod IP reuse đã được xét? | Lease/workload lifecycle |
| Có xem xét proxy/gateway/service mesh hops? | Path diagram và transaction IDs |
| DNS/TLS metadata có bị diễn giải thành app action không? | Evidence confidence review |
| Flow allow có bị gọi nhầm là successful business access? | Response/app audit |
| IDS alerts có được phân biệt với confirmed intrusion? | Triage/false-positive findings |
| Packet loss, sampling, sensor outage có được ghi? | Telemetry quality/unknown intervals |
| Có evidence phản bác giả thuyết được giữ lại? | Disputed/contradictory events |
| Timeline có stable row IDs và version history? | Review/change log |
| Mỗi decision có approver và evidence tại thời điểm quyết định? | Decision log |
| Phân biệt containment requested/applied/effective? | Config audit và negative tests |
| Existing sessions/tokens đã được kiểm tra khi revoke? | IdP/VPN/app evidence |
| Có ghi rollback/failover/emergency exceptions? | Change/approval log |
| Recovery có app/business validation và security controls? | Positive/SLO tests |
| Metrics MTTD/MTTC/MTTR có định nghĩa thống nhất? | Metric definitions |
| Có còn unresolved hypotheses/unknowns ghi rõ? | Open issues/risk register |
| Lộ PII, token, PCAP nhạy cảm đã được hạn chế? | Redaction/access review |
| Executive report không thay đổi mức khẳng định evidence? | Reviewed summary |
| Có owners và follow-up actions sau sự cố? | Corrective action register |
| Team sau ca có thể tái lập timeline từ artifacts? | Handoff/evidence links |

### 37.1. Điều kiện chốt timeline

Một timeline có thể được **chốt để báo cáo** khi:

- Các mốc quan trọng có **nguồn và time quality** rõ.
- Những bằng chứng mâu thuẫn đã được **giải quyết hoặc nêu là chưa giải quyết**.
- Impact, containment và recovery claims có bằng chứng tại **đúng lớp**.
- Hạn chế logging/coverage được **công khai**, không thay bằng giả định.
- Dữ liệu nhạy cảm được xử lý theo chính sách.
- Người chịu trách nhiệm phê duyệt **version và residual risks**.

“Chốt” không nhất thiết có nghĩa **mọi câu hỏi đã được trả lời**; nếu có bằng chứng mới hợp lệ, cần **phát hành revision có audit trail**.

## 38. Tổng kết

**Ghi nhận timeline của sự cố** là quá trình chuyển các log rời rạc thành một chuỗi sự kiện có thể kiểm chứng để phục vụ **ứng phó sự cố mạng, bảo toàn bằng chứng, đánh giá tác động, containment và cải tiến phòng vệ**. Một timeline đáng tin cần nhiều hơn thao tác sort timestamps: phải giữ **giờ gốc, UTC normalized time, timezone/precision, NTP clock skew, ingest delay, source event IDs, evidence provenance, uncertainty và trạng thái xác nhận**.

Trong module **SECURITY_NETWORK_SECURITY**, các nguồn như **firewall, NAT, VPN, DNS, IDS/IPS, NetFlow/IPFIX, packet capture, cloud audit, EDR, IAM, proxy, service mesh và application logs** cung cấp các mảnh thông tin khác nhau. Kết hợp chúng cần **correlation keys đáng tin, session/lease intervals và hiểu network paths**; không được coi **firewall allow, DNS query, TLS handshake hay IDS alert** là bằng chứng chắc chắn một người đã truy cập hoặc đánh cắp dữ liệu.

Timeline cũng phải ghi hoạt động của người ứng phó theo từng giai đoạn: **first seen, alert, triage, declaration, decision, control implementation, containment effectiveness, eradication, recovery verification và post-incident review**. Một biện pháp chỉ được coi là hiệu lực khi có **bằng chứng tại dataplane/session/application và kiểm thử thích hợp**, không chỉ dựa trên lệnh đã gửi.

Phương pháp bền vững là xây **evidence ledger + canonical timeline + decision log**, cập nhật có version, ghi cả **unknown/missing sensor intervals**, giữ những bằng chứng phản bác và thực hiện **quyền riêng tư, redaction, integrity/chain of custody**. Nhờ đó đội ứng phó có thể giải thích **điều gì đã thực sự quan sát được, điều gì còn là giả thuyết, tại sao chọn hành động xử lý và khi nào rủi ro được kiểm soát**, thay vì dựng một câu chuyện có vẻ liền mạch nhưng không đủ bằng chứng.

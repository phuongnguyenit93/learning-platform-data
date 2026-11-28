# Post-incident review và action item trong ứng phó sự cố mạng

## 1. Tổng quan: xử lý xong sự cố chưa phải là kết thúc

Một nhóm vận hành có thể khôi phục VPN, sửa rule firewall hoặc chặn một nguồn tấn công trong vài phút. Tuy nhiên, nếu chỉ ghi “dịch vụ đã hoạt động” rồi đóng ticket, tổ chức sẽ không biết vì sao cảnh báo bị bỏ lỡ, quy trình phối hợp nào thất bại, cách khắc phục có tạo rủi ro mới hay không và điều gì phải thay đổi để sự cố không lặp lại.

**Post-incident review (PIR)** là hoạt động đánh giá có cấu trúc **sau khi một sự cố đã được kiểm soát**, dựa trên bằng chứng và trải nghiệm của các bên tham gia. PIR giúp chuyển những gì đã học thành quyết định cải tiến có thể kiểm chứng. **Action item** là một đầu việc cụ thể phát sinh từ PIR, có người chịu trách nhiệm, thời hạn, tiêu chí hoàn thành và phương pháp xác minh hiệu quả.

Trong module **SECURITY_NETWORK_SECURITY**, PIR áp dụng cho các sự cố liên quan phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, mạng không dây, hạ tầng cloud, phát hiện xâm nhập và phân tích lưu lượng. Cùng một quy trình có thể dùng cho mất kết nối, sai cấu hình gây gián đoạn, lưu lượng tấn công, DNS hijacking, đường truyền bất thường hoặc vi phạm chính sách truy cập.

Sau bài này, người học có thể:

- Giải thích mục tiêu, thời điểm và đầu ra của một PIR.
- Chuẩn bị bằng chứng, dựng timeline và phân biệt sự kiện đã xác minh với giả thuyết.
- Phân tích nguyên nhân trực tiếp, nguyên nhân góp phần và điểm yếu hệ thống.
- Tổ chức buổi review tập trung vào học hỏi, trách nhiệm hệ thống và quyết định cải tiến.
- Viết action item rõ ràng, có owner, hạn chót, mức ưu tiên, bằng chứng kiểm thử và tiêu chí đóng.
- Đánh giá hiệu quả thay đổi bằng dữ liệu: phạm vi ảnh hưởng, phát hiện, khắc phục, tái diễn và tác động phụ.
- Xử lý các yêu cầu bảo vệ dữ liệu, pháp lý và tính toàn vẹn của chứng cứ trong suốt quá trình review.

> **Phân biệt:** *Incident response* nhằm giảm thiểu tác động và khôi phục an toàn; *post-incident review* nhằm hiểu sự cố, tìm lỗ hổng trong cơ chế phòng vệ và cải thiện hệ thống. PIR không thay thế điều tra pháp chứng, đánh giá pháp lý hay quy trình kỷ luật khi những quy trình đó được yêu cầu.

## 2. Khi nào nên tổ chức PIR?

Không phải mọi cảnh báo đều cần họp dài. Nên có **ngưỡng kích hoạt** theo mức độ nghiêm trọng, tác động và khả năng học được điều quan trọng.

| Tình huống | Gợi ý mức review | Lý do |
|---|---|---|
| Sự cố an ninh xác nhận có ảnh hưởng dữ liệu, quyền truy cập hoặc tính toàn vẹn | PIR đầy đủ, phối hợp đội an ninh và chủ dữ liệu | Phạm vi hệ quả, điểm yếu kiểm soát và yêu cầu thông báo |
| Mất kết nối dịch vụ trọng yếu, vượt error budget hoặc SLO đã xác định | PIR đầy đủ | Cải thiện kiến trúc, khả năng phát hiện và phục hồi |
| Thay đổi firewall/IDS/IPS khiến traffic hợp lệ bị chặn diện rộng | PIR đầy đủ hoặc rút gọn tùy tác động | Kiểm soát thay đổi, kiểm thử, rollback, giám sát |
| Sự cố DNS, VPN hoặc cloud routing gây gián đoạn cục bộ | PIR rút gọn hoặc đầy đủ tùy phạm vi | Bài học về phụ thuộc và phân tách trách nhiệm |
| Cảnh báo nhiễu, near miss hoặc sự cố được ngăn chặn trước khi ảnh hưởng người dùng | Review ngắn, ghi các phát hiện hữu ích | Sửa lỗ hổng trước khi gây tác động thật |
| Lỗi đã biết, tác động thấp và không phát hiện điều mới | Cập nhật sự cố và xu hướng | Giảm họp lặp lại; vẫn theo dõi số lần tái diễn |

Chính sách nội bộ quyết định ngưỡng bắt buộc. Một phương án thực tế là mở PIR khi sự cố có **mức nghiêm trọng cao**, **tác động kinh doanh đáng kể**, **đòi hỏi phối hợp nhiều nhóm**, **có khả năng tái diễn** hoặc **phát hiện một lỗ hổng quan trọng**; dùng template nhẹ hơn cho những vụ việc còn lại.

**Thời điểm tổ chức:** khi đã kiểm soát nguy cơ tức thời và có đủ dữ kiện ban đầu, nhưng trước khi ký ức người tham gia bị phai mờ. Có thể tổ chức phiên tổng kết sớm và cập nhật báo cáo sau nếu còn chờ kết quả pháp chứng, nhà cung cấp hoặc phân tích bổ sung. Việc thiếu bằng chứng phải được ghi **chưa xác minh**, không lấp khoảng trống bằng suy đoán.

### 2.1. Điều kiện tối thiểu trước khi mở buổi review

- Sự cố có **incident ID**, phân loại và người điều phối rõ ràng.
- Biết trạng thái hiện tại: đã khôi phục, đang theo dõi hay vẫn còn rủi ro.
- Đã thu thập bản ghi cần thiết trước khi hết thời gian lưu: firewall, DNS, VPN, proxy, NetFlow/IPFIX, IDS/IPS, cloud audit, SIEM, PCAP theo phạm vi cho phép.
- Có timeline tạm thời và các câu hỏi cần giải quyết.
- Các bên liên quan có cơ hội cung cấp thông tin về quyết định, hành động và tác động.
- Đã áp dụng quyền truy cập phù hợp đối với bằng chứng chứa dữ liệu nhạy cảm.

Không trì hoãn khôi phục chỉ để bắt đủ bằng chứng cho PIR; ưu tiên an toàn, kiểm soát và giảm tác động của sự cố. Khi phải thay đổi hiện trường, ghi lại mốc thời gian và lý do.

## 3. Đầu ra cần có của một PIR hữu ích

Một báo cáo PIR nên đủ ngắn để người quản lý hiểu rủi ro nhưng đủ cụ thể để kỹ sư tái kiểm chứng. Các đầu ra tối thiểu:

1. **Tóm tắt điều hành:** chuyện gì xảy ra, ai bị ảnh hưởng, trạng thái cuối cùng, mức độ chắc chắn của kết luận.
2. **Phạm vi tác động:** tính bảo mật, toàn vẹn, sẵn sàng; dịch vụ, người dùng, khu vực, thời lượng và dữ liệu liên quan.
3. **Timeline UTC:** các mốc diễn biến, cách phát hiện, điều phối, cô lập, khôi phục, theo dõi; nguồn bằng chứng.
4. **Phân tích nguyên nhân:** sự kiện kích hoạt, cơ chế lỗi, điều kiện góp phần, kiểm soát nào không hoạt động như kỳ vọng.
5. **Đánh giá ứng phó:** điều gì giúp xử lý nhanh, điều gì làm chậm, quyết định nào dựa trên thông tin thiếu.
6. **Danh sách action item:** owner, mức ưu tiên, deadline, tiêu chí hoàn thành, xác minh độc lập và trạng thái.
7. **Rủi ro tồn đọng và phần chưa biết:** giả thuyết chưa được xác minh, phụ thuộc bên ngoài, lý do chấp nhận rủi ro nếu có.
8. **Theo dõi sau PIR:** người kiểm tra tiến độ, thời điểm đo lại và điều kiện đóng PIR.

Một PIR “đã tổ chức họp” nhưng chưa có đầu việc được giao và cách kiểm tra kết quả thường chỉ là ghi chép, chưa hoàn tất vòng học hỏi.

## 4. Thu thập và bảo vệ chứng cứ

Sự cố mạng có thể phân tán dấu vết ở nhiều tầng và hệ thống. Những gì không được ghi nhận đúng lúc có thể biến mất do log rotation, retention ngắn, auto-scaling, thiết bị reboot hoặc cache DNS hết TTL.

### 4.1. Bằng chứng theo thành phần

| Thành phần | Bằng chứng hữu ích | Câu hỏi điển hình |
|---|---|---|
| Firewall, ACL, security group | Config diff, rule version, policy hit/drop, change record | Rule nào chặn/cho phép lưu lượng? Ai duyệt, triển khai và rollback? |
| Router, switch, SD-WAN | Routing events, BGP/OSPF changes, interface errors, queue drops | Đường đi thay đổi khi nào? Mất kết nối xảy ra ở hop nào? |
| VPN/ZTNA, IAM | Auth success/failure, policy decisions, tunnel health, session logs | Ai mất quyền truy cập, lỗi chứng thực hay transport? |
| DNS | Query/response logs, SERVFAIL/NXDOMAIN, TTL, resolver health | Có phân giải sai, quá tải resolver hay DNS poisoning? |
| IDS/IPS/NDR/SIEM | Alert, signature ID, rule deployment, blocked sessions, triage notes | Cảnh báo có đúng không, có false positive hoặc miss detection? |
| Reverse proxy, LB, WAF | Request IDs, status, upstream latency, backend health, WAF decisions | Lỗi từ client, proxy, backend hay chính sách WAF? |
| PCAP/flow telemetry | Timestamp, 5-tuple, RTT, retransmission, RST, NetFlow/IPFIX | Packet nào quan sát được, ở sensor nào, có mất gói? |
| Cloud/kubernetes | Audit trail, route table, network policy, workload event, control-plane logs | Có thay đổi tài nguyên, policy hoặc vùng hoạt động? |
| Host/application | Kernel/network counters, app traces, error logs, resource metrics | Backend có nhận request, đọc socket và phản hồi không? |
| Quy trình và giao tiếp | Incident channel, ticket, approval, quyết định, handover | Hành động nào diễn ra dựa trên thông tin nào? |

**Ghi mức tin cậy của từng nguồn:** đồng hồ đồng bộ chưa; sensor đặt trước hay sau NAT; PCAP có thiếu packet không; log đã bị sampling hay redact không; cấu hình trích xuất tại thời điểm sự cố có được lưu không.

### 4.2. Bảo toàn và quyền truy cập

- Liên kết chứng cứ với **incident ID**, nguồn, thời điểm thu thập, người thu, mức phân loại, phạm vi, định danh lưu trữ và checksum khi thích hợp.
- Dùng kho bảo vệ, mã hóa khi truyền và lưu, IAM ít quyền nhất và nhật ký truy cập. Tránh dán nguyên PCAP, credential, cookie, bearer token, dữ liệu khách hàng hay thông tin máy chủ nhạy cảm vào biên bản họp hoặc ticket công khai.
- Nếu cần chain of custody, lưu hash của file gốc, thời gian, công cụ, người bàn giao và lịch sử truy cập/chuyển giao. Hash giúp kiểm tra toàn vẹn so với giá trị đã tin cậy, không tự chứng minh nguồn gốc.
- Giữ **bản gốc** được kiểm soát; dùng **bản trích xuất đã giảm dữ liệu** để thảo luận. Thời hạn lưu, legal hold và yêu cầu xóa phải theo chính sách áp dụng; PIR không mặc nhiên cho phép giữ chứng cứ vô thời hạn.
- Phân biệt bản báo cáo rộng rãi với phụ lục hạn chế. Nếu vụ việc có điều tra hoặc nghĩa vụ thông báo đang xử lý, phối hợp nhóm phụ trách trước khi phổ biến thông tin.

Các cuộc thảo luận nên ghi được **hành vi hệ thống** mà không để lộ bí mật hoặc dữ liệu cá nhân không cần thiết. Có thể dùng mã tham chiếu tới chứng cứ gốc trong kho, thay vì chép nội dung nhạy cảm vào báo cáo.

## 5. Dựng timeline dựa trên bằng chứng

Timeline giúp biến lời kể “mạng bắt đầu lỗi vào khoảng chiều” thành chuỗi sự kiện có thể kiểm tra.

### 5.1. Các mốc nên tách riêng

| Ký hiệu | Ý nghĩa | Ví dụ cách xác định |
|---|---|---|
| `T_start` | Thời điểm dấu hiệu/tác động đầu tiên đã xác nhận | Synthetic probe lỗi hoặc request đầu tiên bị drop |
| `T_detect` | Thời điểm hệ thống hoặc người vận hành phát hiện | Alert được tạo hoặc ticket của người dùng đầu tiên |
| `T_ack` | Thời điểm có người nhận điều phối | Incident commander nhận case |
| `T_contain` | Thời điểm ngăn lan rộng hoặc giới hạn tác động | Cô lập segment, rollback rule, chặn IOC được xác minh |
| `T_recover` | Thời điểm dịch vụ/kiểm soát được khôi phục theo tiêu chí | Health check và traffic kiểm thử đạt tiêu chí |
| `T_close` | Thời điểm kết thúc xử lý khẩn cấp theo quy trình | Đóng phase ứng cứu, tiếp tục theo dõi hậu sự cố |

**Không coi các mốc trên là tương đương.** Cô lập một máy có thể làm giảm rủi ro trước khi dịch vụ khôi phục; khôi phục dịch vụ có thể xảy ra trước khi xác định nguyên nhân. `T_start` thường chỉ là “thời điểm sớm nhất có bằng chứng”, không nhất thiết là thời điểm nguyên nhân ban đầu xuất hiện.

Các metric có thể tính từ những định nghĩa đã thống nhất:

~~~text
Time to detect          = T_detect  - T_start
Time to acknowledge     = T_ack     - T_detect
Time to contain         = T_contain - T_start
Time to recover         = T_recover - T_start
Post-recovery follow-up = T_close   - T_recover
~~~

Không cộng trừ tùy tiện khi timestamp từ các nguồn chưa đồng bộ. Cần thống nhất độ chính xác, timezone (ưu tiên UTC), đoạn dữ liệu bị thiếu và quy tắc xử lý sự cố có nhiều đợt ảnh hưởng. Nếu đo MTTD/MTTR cho nhiều vụ việc, phải nêu rõ MTTR đang là **mean time to recover**, **mean time to resolve** hay định nghĩa khác.

### 5.2. Ví dụ timeline

Tình huống giả định: sau thay đổi policy IDS/IPS, traffic API hợp lệ từ vùng VPN bị drop. Toàn bộ thời điểm dưới đây là **dữ liệu minh họa**, không phải sự cố thật.

| UTC | Sự kiện | Bằng chứng | Trạng thái kết luận |
|---|---|---|---|
| 09:00 | Rule IDS/IPS mới được áp dụng cho VPN ingress | Change ticket và policy version | Xác nhận |
| 09:03 | Lượt gọi API đầu tiên từ dải VPN có session bị drop | Policy hit/drop log | Xác nhận |
| 09:07 | Synthetic test VPN cảnh báo tăng lỗi | Monitoring alert | Xác nhận |
| 09:10 | On-call nhận incident, phân loại mức độ | On-call ack/ticket | Xác nhận |
| 09:16 | Nhóm so sánh policy trước/sau triển khai | Config diff | Xác nhận |
| 09:21 | Quyết định rollback thay đổi với người có thẩm quyền | Incident channel/change log | Xác nhận |
| 09:24 | Rollback hoàn tất; log drop theo rule mới dừng | Config audit và IDS/IPS metrics | Xác nhận |
| 09:28 | Synthetic test, tỷ lệ lỗi và lưu lượng người dùng trở lại baseline | Dashboard và test từ VPN | Xác nhận |
| 10:00 | Kết thúc giai đoạn ứng cứu, mở PIR | Incident record | Xác nhận |

Với định nghĩa trên: phát hiện mất 4 phút từ lần drop đầu tiên (09:03→09:07), nhận xử lý sau 3 phút (09:07→09:10), containment tại 09:24 sau 21 phút, recovery tại 09:28 sau 25 phút. **Những con số này chỉ hợp lệ theo mốc được nêu**, không thể suy ra thời lượng tác động của từng người dùng.

~~~mermaid
flowchart LR
    A["09:00 Đổi policy"] --> B["09:03 Drop API"]
    B --> C["09:07 Alert"]
    C --> D["09:10 On-call ACK"]
    D --> E["09:21 Duyệt rollback"]
    E --> F["09:24 Rollback"]
    F --> G["09:28 Kiểm tra phục hồi"]
    G --> H["PIR và action items"]
~~~

Ghi rõ “điều gì được xác minh” khác với “điều gì chỉ được suy đoán”. Ví dụ nếu thiếu PCAP phía client, không được tuyên bố mọi request của người dùng đều bị drop; có thể chỉ xác nhận các session được ghi trong log.

## 6. Phân tích nguyên nhân: nhiều lớp thay vì một cá nhân

Một PIR tốt phân biệt ít nhất bốn lớp:

1. **Triệu chứng/tác động:** người dùng VPN nhận timeout đến API.
2. **Cơ chế lỗi trực tiếp:** IDS/IPS drop session theo signature/rule cụ thể.
3. **Sự kiện kích hoạt:** triển khai policy mới tại 09:00.
4. **Điều kiện hệ thống góp phần:** phạm vi rule quá rộng, thiếu test với traffic VPN hợp lệ, rollout đồng loạt và cảnh báo chưa phân tách theo nhóm người dùng.

Chỉ ghi “kỹ sư cấu hình sai” không giải thích tại sao một thay đổi như vậy có thể vượt qua quá trình kiểm tra, hay hệ thống cần phát hiện/giới hạn hậu quả thế nào. Cách tiếp cận **blameless** tập trung vào thông tin, công cụ, quy trình và điều kiện làm việc tại thời điểm người tham gia đưa ra quyết định. Nó không có nghĩa là bỏ qua nghĩa vụ bảo mật hoặc trách nhiệm đã được quy định.

### 6.1. Dùng Five Whys có kiểm chứng

Ví dụ giả định:

| Câu hỏi | Câu trả lời dựa trên dữ liệu |
|---|---|
| Vì sao người dùng VPN không gọi được API? | IPS drop các phiên theo rule X, thấy trong policy hit logs |
| Vì sao rule X drop traffic hợp lệ? | Điều kiện match bao phủ mẫu request bình thường, tái hiện được ở môi trường kiểm thử |
| Vì sao điều kiện match được triển khai rộng? | Rollout áp dụng trực tiếp cho toàn bộ VPN ingress, không có canary |
| Vì sao thiếu canary? | Pipeline policy không hỗ trợ nhóm áp dụng thử hoặc bước kiểm tra này chưa được đặt bắt buộc |
| Vì sao không phát hiện trước ảnh hưởng người dùng? | Regression suite thiếu kịch bản từ VPN và alert chỉ tổng hợp theo API, không phân tách nguồn VPN |

**Five Whys không phải máy tìm “một root cause tuyệt đối”.** Có thể có nhiều chuỗi nguyên nhân song song: policy sai, rollout không an toàn, monitoring thiếu chiều dữ liệu, rollback chậm, training chưa đầy đủ. Nếu một câu trả lời không có bằng chứng, gắn `hypothesis` và tạo nhiệm vụ xác minh.

### 6.2. Phân tích theo cây sự kiện và lớp phòng thủ

~~~mermaid
flowchart TD
    U["Tác động: API timeout qua VPN"]
    U --> M["IPS drop phiên hợp lệ"]
    M --> R["Signature/policy match quá rộng"]
    M --> L["Rollout không phân đợt"]
    U --> D["Phát hiện chậm"]
    D --> T["Chưa có synthetic test từ VPN trước triển khai"]
    D --> O["Dashboard không tách chiều VPN"]
    U --> C["Phục hồi kéo dài"]
    C --> P["Rollback cần phê duyệt thủ công nhiều bước"]
~~~

Các câu hỏi cần xét riêng cho sự cố **an ninh**:

- Lớp phòng vệ nào đáng ra phải ngăn sự cố hoặc giảm tác động? Ví dụ segmentation, MFA, DNS filtering, IDS/IPS, egress control, cloud security group.
- Điểm phát hiện nào đáng ra phải thấy sớm hơn? Log/alert nào bị bỏ sót do retention, query, threshold hay thiếu owner?
- Nếu đã phát hiện, điều gì ngăn containment? Thiếu quyền, playbook chưa rõ, phụ thuộc nhà cung cấp hay thông tin asset chưa đầy đủ?
- Trong recovery, có tái mở đường cho attacker hoặc bỏ qua kiểm soát quan trọng không? Có cần phương án thay thế tạm thời, thời hạn và owner theo dõi không?
- Có bằng chứng về truy cập trái phép/dữ liệu bị ảnh hưởng không? Nếu chưa có, phải ghi “chưa xác minh”, không đồng nhất thiếu alert với “không xảy ra xâm nhập”.

### 6.3. Đánh giá ranh giới trách nhiệm

Thành phần tạo ra thông báo lỗi không nhất thiết là nơi phát sinh nguyên nhân. Ví dụ `504` từ reverse proxy có thể do app chờ DB, mất gói giữa proxy và backend, pool connection cạn hoặc DNS của upstream. PIR cần đối chiếu PCAP, server logs, proxy timings, firewall decisions và traces để phân biệt.

Tương tự, một bản vá cấu hình mạng có thể khôi phục connectivity nhưng bỏ lại rủi ro kiểm soát. Chỉ tuyên bố “đã sửa” khi **chức năng** và **yêu cầu an ninh liên quan** đều được kiểm chứng.

## 7. Đánh giá chất lượng quá trình ứng cứu

Đừng giới hạn PIR ở nguyên nhân kỹ thuật. Diễn tiến sự cố còn phụ thuộc quan sát, thông tin và quyết định của nhóm vận hành.

| Giai đoạn | Câu hỏi review | Cơ hội cải tiến |
|---|---|---|
| Chuẩn bị | Có sơ đồ đường đi, inventory, owner, backup config, playbook và test? | Chuẩn hóa inventory, diễn tập, baseline |
| Phát hiện | Người trực nhận alert có thể hành động? Có false positive/false negative? | Giảm nhiễu, điều chỉnh rule, tăng phân loại |
| Triage | Có nhận diện đúng phạm vi, mức độ và bảo vệ chứng cứ? | Checklist triage, correlating logs, severity guide |
| Điều phối | Ai là incident commander? Có giao nhiệm vụ và cập nhật stakeholder? | Phân vai, escalation, kênh liên lạc dự phòng |
| Containment | Đã giới hạn hậu quả mà không phá hủy chứng cứ hay làm gián đoạn ngoài ý muốn? | Phương án chặn an toàn, runbook, phê duyệt rút gọn |
| Eradication | Đã loại nguyên nhân/xâm nhập còn tồn tại, revoke credential khi phù hợp? | Kiểm tra persistence, rules, IOC, hygiene |
| Recovery | Có tiêu chí kiểm tra lại cả connectivity, an ninh và nghiệp vụ? | Synthetic test, canary, rollback và rollback verification |
| Hậu sự cố | Bằng chứng có đủ? Action item có owner/đo hiệu quả? | Đo MTTD/MTTR, lịch rà soát, tracking tập trung |

Ghi cả **điều đã hoạt động tốt**: dashboard giúp khoanh vùng nhanh, on-call có quyền truy cập đúng mức, đội app và network phối hợp qua một incident commander, hoặc canary đã hạn chế blast radius. Những điểm tốt nên được duy trì và nhân rộng nếu có bằng chứng.

Khi có vấn đề giao tiếp, mô tả hành vi quan sát được và điều kiện góp phần, ví dụ “trong 12 phút đầu không có owner xác nhận việc kiểm tra VPN ingress” thay cho phán xét cá nhân. Mục tiêu là cải thiện thời gian và độ chính xác của quyết định.

## 8. Viết action item có thể thực hiện và kiểm chứng

“Cần cải thiện giám sát” không phải một action item tốt. Một action item cần là thay đổi có thể được giao việc, review và kiểm chứng theo điều kiện kết thúc.

### 8.1. Mẫu action item

| Trường | Nội dung yêu cầu |
|---|---|
| ID và liên kết | `AI-INC-042-01`, liên kết incident/PIR và bằng chứng |
| Vấn đề và bằng chứng | Cơ chế lỗi hoặc lỗ hổng đã quan sát; log/trace/config cụ thể |
| Kết quả mong muốn | Điều gì cần thay đổi để ngăn, phát hiện hoặc giảm tác động |
| Biện pháp cụ thể | Đổi policy, bổ sung kiểm thử, cảnh báo, runbook, kiểm soát phân quyền... |
| Owner | **Một** người chịu trách nhiệm theo dõi đến đóng; có thể có contributor |
| Ưu tiên | Theo rủi ro, tác động, xác suất tái diễn và tốc độ triển khai |
| Due date | Ngày cam kết; nếu phụ thuộc, ghi dependency và mốc review |
| Acceptance criteria | Điều kiện có thể kiểm tra độc lập trước khi đánh dấu Done |
| Validation/rollout | Test, môi trường, giám sát trước/sau, phương án rollback |
| Trạng thái và bằng chứng đóng | Open/In progress/Blocked/Done/Verified/Risk accepted; liên kết kết quả |

**Một owner chịu trách nhiệm** không có nghĩa người đó tự thực hiện mọi phần. Với thay đổi liên nhóm, giao người phối hợp và quyết định ưu tiên; phân rã thành các action item nhỏ, có phụ thuộc rõ ràng.

### 8.2. Từ lời hứa mơ hồ đến hành động có thể đóng

| Mơ hồ | Action item tốt hơn |
|---|---|
| “Sửa rule IPS” | “Thu hẹp rule X để không match request API hợp lệ từ VPN theo mẫu traffic đã xác nhận; thêm test replay; triển khai canary; đối chiếu policy hits trước/sau” |
| “Thêm giám sát” | “Thêm synthetic API probe từ VPN A/B mỗi 1 phút; cảnh báo sau N lần lỗi liên tục; kiểm tra cảnh báo và escalation đến on-call” |
| “Có rollback nhanh” | “Tạo playbook rollback IDS/IPS theo version trong 5 phút khi trigger đạt ngưỡng; diễn tập với on-call, ghi audit và kiểm tra traffic sau rollback” |
| “Cập nhật tài liệu” | “Viết sơ đồ request path client VPN→firewall→IPS→LB→app và bảng owner; xác minh tính đúng với đại diện network/app; gắn vào runbook incident” |
| “Không tái diễn nữa” | “Thêm policy test gate bắt buộc trước triển khai; ghi tỷ lệ test pass và phát hiện regression trong ba đợt rollout tiếp theo” |

**Acceptance criteria** tập trung vào kết quả xác thực, không chỉ “PR merged” hay “document published”. Ví dụ một cảnh báo chỉ thực sự hoàn thành khi phát tín hiệu đúng trên dữ liệu thử, đi tới người trực và tạo phản hồi trong điều kiện được định nghĩa.

### 8.3. Ví dụ action backlog sau sự cố IPS

Các owner và deadline dưới đây là dữ liệu ví dụ; không gán cho nhân sự thực.

| ID | Action item | Owner vai trò | Ưu tiên ví dụ | Done khi |
|---|---|---|---|---|
| AI-01 | Thu hẹp rule IPS X, thêm regression test cho VPN→API | Network Security | P0 | Replay traffic hợp lệ pass; mẫu tấn công thử nghiệm vẫn bị chặn; canary thành công |
| AI-02 | Triển khai canary policy 5% trước mở rộng | Network Platform | P1 | Quy trình chạy được, rollout dừng khi metrics vượt ngưỡng, rollback xác nhận |
| AI-03 | Thêm synthetic monitor từ VPN và alert theo khu vực | SRE/Monitoring | P1 | Test gây lỗi có kiểm soát tạo alert đúng on-call, khôi phục không báo giả |
| AI-04 | Rút ngắn quy trình rollback đã được phê duyệt | Incident Management | P1 | Diễn tập có log/audit và người trực thực hiện trong mục tiêu được thống nhất |
| AI-05 | Rà soát policy exceptions tạm thời sau rollback | Security Governance | P2 | Không còn ngoại lệ quá hạn hoặc đã có risk owner/phê duyệt hợp lệ |
| AI-06 | Bổ sung sơ đồ lưu lượng và runbook kiểm tra hai đầu | Network + App | P2 | Runbook được dùng thành công trong diễn tập và được hai nhóm duyệt |

*P0/P1/P2 chỉ là ví dụ phân cấp nội bộ*, phải tuân theo hệ thống ưu tiên thực tế của tổ chức. Action “P0” ở một tổ chức có thể yêu cầu xử lý tức thời; nếu không có thang chuẩn, định nghĩa thang trước khi gán mức.

## 9. Ưu tiên theo rủi ro và khả năng giảm tác động

Không nên ưu tiên chỉ theo mức độ nổi bật trong cuộc họp. Đánh giá theo:

- **Mức độ tác động nếu tái diễn:** số người dùng, dịch vụ trọng yếu, phạm vi dữ liệu, quyền truy cập và tính sẵn sàng.
- **Khả năng tái diễn/phơi nhiễm:** cấu hình tương tự đã tồn tại ở đâu, có bao nhiêu route/segment dùng cùng policy, kiểm soát hiện có hiệu quả không.
- **Khả năng phát hiện trước khi gây hại:** alert, canary, logs, dự phòng và khả năng cô lập.
- **Hiệu quả giảm rủi ro:** action ngăn nguyên nhân, giảm blast radius, phát hiện sớm hay chỉ làm xử lý nhanh hơn.
- **Chi phí, phụ thuộc và rủi ro triển khai:** rollback, điều kiện kiểm thử, vận hành và độ tin cậy của biện pháp mới.

Có thể dùng ma trận **impact × likelihood** theo chuẩn tổ chức. Điểm số dùng để hỗ trợ thảo luận, **không thay thế đánh giá an ninh**: một lỗ hổng xác thực có tác động nghiêm trọng dù chưa có thống kê tái diễn.

### 9.1. Nhóm action theo lớp phòng vệ

Để tránh PIR chỉ dừng ở vá lỗi hiện tại, tạo hành động ở các cấp:

| Lớp | Mục tiêu | Ví dụ |
|---|---|---|
| Prevent | Giảm xác suất phát sinh | CI policy tests, review firewall diff, kiểm soát quyền thay đổi |
| Limit blast radius | Giới hạn phạm vi ảnh hưởng | Segmentation, canary, rate limit, rollout theo vùng |
| Detect | Phát hiện sớm đúng đối tượng | Synthetic probe từ VPN, cảnh báo drop rate theo policy |
| Respond | Giảm thời gian cô lập và phục hồi | Playbook, quyền khẩn cấp có audit, rollback diễn tập |
| Learn | Cải thiện khả năng phân tích lần sau | Chuẩn hóa log, đồng bộ timestamp, mapping NAT và request IDs |

Một PIR không nhất thiết phải tạo hành động trong tất cả nhóm. Nhưng nếu chỉ có hành động “tăng timeout” hoặc “restart thiết bị”, nên kiểm tra có đang bỏ qua điểm yếu về prevention/detection hay không.

## 10. Quản lý vòng đời của action item

~~~mermaid
flowchart LR
    A["Phát hiện từ PIR"] --> B["Viết action có tiêu chí đo"]
    B --> C["Ưu tiên, gán owner và hạn"]
    C --> D["Thực hiện, review thay đổi"]
    D --> E["Test và rollout an toàn"]
    E --> F{"Đạt acceptance criteria?"}
    F -->|"Chưa"| G["Bổ sung/sửa và kiểm tra lại"]
    G --> D
    F -->|"Đạt"| H["Verified và ghi bằng chứng"]
    H --> I["Theo dõi hiệu quả, xu hướng tái diễn"]
~~~

Quy trình cần rõ nghĩa các trạng thái:

- **Open:** có đủ thông tin, owner và tiêu chí; chưa bắt đầu.
- **In progress:** đang triển khai theo kế hoạch, có cập nhật tiến độ.
- **Blocked:** chưa thể thực hiện vì phụ thuộc/phê duyệt/thiếu dữ liệu; nêu người gỡ vướng và ngày xem lại.
- **Done:** người thực hiện xác nhận đã triển khai.
- **Verified/Closed:** reviewer kiểm tra acceptance criteria, kết quả test và bằng chứng hiệu quả theo yêu cầu.
- **Risk accepted / Won't do:** quyết định có thẩm quyền về việc không triển khai, kèm phân tích rủi ro, thời hạn đánh giá lại; không dùng để âm thầm bỏ qua việc quá hạn.

Tùy công cụ có thể có các trạng thái khác, nhưng **“Done” và “Verified” không nên bị đánh đồng** trong hạng mục ảnh hưởng an ninh hoặc tính sẵn sàng.

### 10.1. Ví dụ biểu diễn một action item bằng YAML

~~~yaml
id: AI-INC-042-01
incident_id: INC-042
title: "Thêm regression test cho policy IPS trên luồng VPN đến API"
problem: "Policy X chặn request hợp lệ được ghi nhận trong phiên điều tra"
owner_role: "network-security"
reviewer_role: "sre-security-review"
priority: P1
created_at_utc: "2026-11-28T10:00:00Z"
due_at_utc: "2026-12-05T10:00:00Z"
status: in_progress
dependencies:
  - "Bộ mẫu lưu lượng đã làm sạch và được phê duyệt cho kiểm thử"
acceptance_criteria:
  - "Traffic hợp lệ từ VPN qua policy mới không bị drop"
  - "Mẫu phát hiện giả lập vẫn kích hoạt kiểm soát dự kiến"
  - "Test được chạy bắt buộc trước khi deploy policy"
validation:
  environment: "staging-and-limited-canary"
  evidence_ref: "evidence/INC-042/AI-01"
  independent_review_required: true
monitoring:
  metric: "ips_policy_drop_rate_for_allowlisted_vpn_test"
  review_window: "3 deployment cycles"
fallback: "Rollback policy về version đã xác nhận"
~~~

Đây là **mẫu minh họa**, không phải file cấu hình có thể chạy trực tiếp. Địa chỉ chứng cứ và thông tin nhạy cảm cần được truy cập qua kho an toàn; không nhúng credential, file PCAP gốc hoặc tên người dùng vào bản action công khai.

### 10.2. Quy trình xử lý action item quá hạn

1. Owner cập nhật tiến độ, bằng chứng và blocker trước ngày đến hạn.
2. Người điều phối PIR rà soát các mục P0/P1 theo chu kỳ đã thống nhất; thông báo sớm khi deadline có nguy cơ trễ.
3. Nếu thay đổi scope hoặc hạn, cần ghi **lý do**, rủi ro còn tồn đọng và người phê duyệt, không âm thầm sửa lịch sử.
4. Nếu phải hoãn, có thể yêu cầu **biện pháp tạm**: giám sát tăng cường, canary, hạn chế rollout, access review hoặc phương án rollback.
5. Nếu action đã triển khai nhưng không đạt tiêu chí, mở lại hoặc tạo issue sửa lỗi có liên kết, không đóng PIR chỉ vì đã merge code.

Action item có phụ thuộc nên được theo dõi bằng thứ tự rõ ràng. Ví dụ “triển khai test gate” phụ thuộc có bộ traffic mẫu được rà soát; có thể tách việc tạo dataset an toàn thành action riêng.

## 11. Đo hiệu quả: action item có thật sự giảm rủi ro?

Khi action ở trạng thái Verified, cần có kế hoạch xác minh **hiệu quả thực tế**, không chỉ kiểm tra công việc đã hoàn tất.

| Mục tiêu | Chỉ số ví dụ | Cách diễn giải |
|---|---|---|
| Phát hiện sớm | `time_to_detect`, tỷ lệ alert có action, alert precision | So cùng loại sự cố/vùng; giảm thời gian mà không tăng nhiễu quá mức |
| Khoanh vùng nhanh | `time_to_contain`, số segment/user bị ảnh hưởng | Cần xem mức độ nghiêm trọng và blast radius khác nhau |
| Phục hồi an toàn | `time_to_recover`, rollback success, SLO burn rate | Thời gian phục hồi không được đánh đổi bằng bỏ kiểm soát an ninh |
| Ngăn tái diễn | Regression test pass, policy diff violations, sự cố cùng cơ chế | Không tái diễn trong vài tuần chưa chứng minh rủi ro đã bằng 0 |
| Nâng chất lượng review | Tỷ lệ action có owner/criteria, % được Verified đúng hạn | Cần xem **chất lượng** test/việc đóng, tránh chạy theo tỷ lệ |
| Bảo vệ dữ liệu | Tỷ lệ evidence đúng retention/ACL, audit truy cập | Đừng lưu nhiều dữ liệu hơn chỉ để nâng khả năng debug |

Ví dụ: sau khi thêm canary và regression test, **ba đợt triển khai** tiếp theo đều chạy bài test VPN→API, không phát sinh drop bất thường ở canary, alert được kích hoạt trong diễn tập, và rollback đạt điều kiện về thời gian. Đây là bằng chứng tích cực về hiệu quả của action, nhưng vẫn cần theo dõi dài hơn và đánh giá coverage của bài test.

Tránh dùng một con số trung bình để kết luận toàn hệ thống đã tốt. Có thể kiểm tra theo site, ISP, VPN concentrator, policy version, thiết bị và nhóm user; một subset nhỏ vẫn có thể chịu ảnh hưởng nặng.

### 11.1. Leading và lagging indicators

- **Leading indicators:** tỷ lệ change được kiểm thử, canary coverage, phát hiện config drift, số action P1 quá hạn, chất lượng playbook, độ đầy đủ log.
- **Lagging indicators:** số sự cố tái diễn, thời gian gián đoạn, dữ liệu bị ảnh hưởng, số ca phải rollback khẩn cấp, MTTD/MTTR của các sự cố đã xảy ra.

Cần cả hai. Số sự cố giảm có thể do ít thay đổi hoặc ít ghi nhận hơn; số cảnh báo tăng có thể vì phát hiện tốt hơn hoặc vì rule gây nhiễu. Dùng thêm bối cảnh để hiểu xu hướng.

## 12. Tổ chức buổi PIR hiệu quả

Một buổi review nên có facilitator, incident commander/người điều phối, đại diện network/security, app/SRE và chủ dịch vụ. Privacy/legal/forensics tham gia khi vụ việc có dữ liệu nhạy cảm, tấn công hoặc nghĩa vụ báo cáo. Chỉ mời những vai trò có đóng góp hoặc quyết định cần thiết; không biến buổi họp thành phiên đánh giá cá nhân.

Gợi ý agenda khoảng 60 phút cho sự cố có mức tác động vừa; điều chỉnh theo độ phức tạp:

| Thời lượng ví dụ | Hoạt động | Đầu ra |
|---|---|---|
| 5 phút | Mục tiêu, quy tắc thảo luận và phạm vi | Đồng thuận về cách dùng bằng chứng |
| 10 phút | Tóm tắt tác động, dịch vụ và khách hàng | Impact statement được xác minh |
| 15 phút | Duyệt timeline và các điểm chưa rõ | Timeline và câu hỏi cần tiếp tục điều tra |
| 15 phút | Phân tích cơ chế, điều kiện góp phần, lớp bảo vệ | Danh sách nhận định kèm mức tin cậy |
| 10 phút | Đề xuất và ưu tiên action items | Owner, deadline, acceptance criteria |
| 5 phút | Kiểm tra risk owner, người theo dõi và lịch review | Quyết định và trách nhiệm sau họp |

**Facilitator** nên hỏi:

- Trước sự cố, chúng ta kỳ vọng hệ thống và cảnh báo hoạt động thế nào?
- Thực tế đã diễn ra gì, chứng cứ nào xác nhận?
- Ở thời điểm quyết định, mỗi người **biết gì**, **chưa biết gì**, **có quyền/công cụ nào**?
- Kiểm soát nào thất bại? Kiểm soát nào đã giảm tác động?
- Nếu sự cố tương tự diễn ra đêm nay, điều gì sẽ khiến phát hiện và containment nhanh hơn?
- Đầu việc nào làm giảm rủi ro lớn nhất và có thể được xác minh khi hoàn thành?

Tránh câu hỏi dẫn dắt “Ai gây ra?” hoặc “Tại sao không đơn giản làm X?”, vốn bỏ qua những gì nhóm thực sự quan sát được trong thời điểm áp lực.

## 13. Case study: PIR sau lỗi rule IPS ảnh hưởng VPN

### 13.1. Bối cảnh và dữ liệu ban đầu

Một tổ chức phân tách mạng người dùng qua VPN, IDS/IPS, firewall và load balancer đến API nội bộ. Sau một lần cập nhật IPS signature, người dùng VPN gặp timeout; phần lớn người dùng ngoài VPN vẫn truy cập bình thường.

**Giả định có bằng chứng:**

- Config audit xác nhận version policy mới được áp dụng lúc 09:00 UTC.
- IPS logs ghi tăng phiên bị drop, cùng rule X và nguồn thuộc một số dải VPN.
- Số lỗi ở synthetic probe VPN tăng từ 09:07; synthetic ngoài VPN ổn định.
- Rollback hoàn tất 09:24; dashboard và kiểm thử xác nhận phục hồi 09:28.
- Không có chứng cứ trong phạm vi điều tra cho thấy dữ liệu bị truy cập trái phép. Điều này **không đồng nghĩa** khẳng định không có rủi ro ở các vùng chưa thu thập dữ liệu.

### 13.2. Phân tích nhân quả

**Trigger:** thay đổi policy tại 09:00.

**Cơ chế trực tiếp:** IPS chặn luồng API hợp lệ do điều kiện match của rule X rộng hơn dự kiến, được xác nhận bằng policy hit logs và kiểm thử traffic được phép.

**Điều kiện góp phần:** không có canary cho VPN ingress; regression test chưa bao phủ hành vi request của nhóm VPN; alert tổng hợp khó thấy lỗi theo nhóm truy cập; rollback đòi hỏi nhiều bước phê duyệt.

**Điều giúp xử lý:** có lưu lịch sử policy version và audit trail, nên so sánh được cấu hình; đội ứng cứu có synthetic test cho VPN để xác minh phục hồi.

**Các điểm cần điều tra thêm:** vì sao bộ mẫu test ban đầu không phản ánh traffic thật, tỷ lệ người dùng VPN bị ảnh hưởng, có policy tương tự ở các segment khác không, hoặc có quy trình change khác đã có kiểm soát tốt hơn để áp dụng.

### 13.3. Hành động và xác minh

Các action AI-01 đến AI-06 ở mục 8 là backlog ví dụ cho case này. Sau khi thực hiện:

1. Chạy regression test với mẫu request hợp lệ và mẫu bị chặn theo thiết kế; gắn kết quả với policy version.
2. Deploy canary trên phạm vi giới hạn, kiểm tra drop rate, synthetic probe, alert latency và tác động tới user hợp lệ.
3. Mở rộng theo đợt chỉ khi tiêu chí được đáp ứng; rollback nếu chạm điều kiện đã thống nhất.
4. Diễn tập incident mới từ phát hiện → xác định policy → phê duyệt rollback → phục hồi; xem log có đầy đủ không.
5. Ghi owner và bằng chứng kiểm tra từng action; đánh giá lại sau một số rollout tiếp theo.

**Điểm học được:** Một “root cause” dạng “rule match sai” là chưa đủ nếu pipeline vẫn cho phép deploy phạm vi rộng mà không có kiểm thử, canary hoặc khả năng phát hiện nhanh. Cải tiến cần kết hợp policy correctness, rollout safety, observability và incident response.

## 14. Mẫu báo cáo PIR có thể điền

~~~markdown
# PIR — <incident_id> — <short_title>

## A. Metadata
- Incident ID:
- Severity và phạm vi:
- Trạng thái: recovered / monitoring / open
- Incident commander:
- PIR facilitator:
- Thời điểm review (UTC):
- Phân loại báo cáo và nhóm được phép xem:

## B. Tóm tắt và impact
- Triệu chứng và hành vi hệ thống quan sát được:
- Dịch vụ, phân đoạn/vùng/nhóm user bị ảnh hưởng:
- Ảnh hưởng confidentiality/integrity/availability:
- Thời lượng, độ tin cậy số đo và phạm vi chưa xác minh:
- Cách khôi phục và tiêu chí đã đạt:

## C. Timeline
| UTC | Sự kiện | Nguồn bằng chứng | Xác nhận/giả thuyết |
|---|---|---|---|
| ... | ... | ... | ... |

## D. Phân tích
- Trigger:
- Cơ chế trực tiếp:
- Điều kiện góp phần:
- Kiểm soát phát hiện/containment/recovery:
- Điều hoạt động tốt:
- Điều cần làm rõ, giới hạn của bằng chứng:
- Rủi ro còn tồn đọng:

## E. Action backlog
| ID | Action | Owner | Priority | Due | Acceptance criteria | Evidence | Status |
|---|---|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... | ... | ... |

## F. Follow-up
- Người theo dõi backlog:
- Ngày review hành động và hiệu quả:
- Người phê duyệt risk acceptance (nếu có):
- Phụ lục chứng cứ có kiểm soát truy cập:
~~~

Mẫu này dùng cho nội dung đã được rà soát để chia sẻ theo phân loại. Nếu incident chứa IOC nhạy cảm, khóa, PII hay file PCAP đầy đủ, chỉ gắn đường dẫn tham chiếu từ kho chứng cứ phù hợp; thông tin mật giữ trong phụ lục có quyền hạn chế.

## 15. Các lỗi thường gặp khi làm PIR

1. **Chỉ tổng kết “đã khôi phục”.** Không có giả thuyết nguyên nhân, bài học hoặc cách giảm tái diễn.
2. **Kết luận do thiếu người cẩn thận.** Bỏ qua thiếu test, thiếu quyền, áp lực thời gian, công cụ khó dùng và blast radius.
3. **Đặt “root cause” trước khi có chứng cứ.** Sau đó chỉ chọn log ủng hộ nhận định; cần ghi mức tin cậy và dữ liệu phản biện.
4. **Đổ lỗi hệ thống mạng từ một HTTP status hoặc RST.** Thành phần quan sát được lỗi không nhất thiết phát sinh nguyên nhân.
5. **Dùng timeline không nhất quán.** Log server, cloud và chat khác timezone, NTP lệch, sự kiện tương đối không được ghi rõ.
6. **Đưa dữ liệu nhạy cảm vào tài liệu quá rộng quyền.** PIR phục vụ học hỏi, không cấp phép nhân bản PCAP hay token.
7. **Tạo action “cải thiện giám sát”.** Không có owner, acceptance criteria và ngày kiểm tra, khó đóng hoặc đo hiệu quả.
8. **Đóng khi PR đã merge.** Thay đổi có thể chưa triển khai, chưa được thử tại đúng đường traffic hoặc tạo false positive.
9. **Không ghi rủi ro tồn đọng.** Tạm tắt IPS hoặc mở firewall để khôi phục nhưng không có owner/lịch thu hẹp policy.
10. **Không theo dõi action sau họp.** Backlog lỗi thời khiến cùng sự cố lặp lại và nhóm mất niềm tin vào PIR.
11. **Chạy theo MTTR thấp bằng mọi giá.** Giảm thời gian xử lý nhưng bỏ qua containment, an ninh hoặc độ bền phục hồi.
12. **Xóa chứng cứ quá sớm hoặc giữ vô thời hạn.** Cần retention, legal hold và quyền truy cập theo chính sách đã xác định.

## 16. Checklist thực hiện từ đầu đến cuối

### Trước buổi review

- [ ] Đã quyết định mức PIR tương xứng với severity, tác động và khả năng học hỏi.
- [ ] Đã ghi incident ID, owner, trạng thái ứng cứu, người điều phối PIR.
- [ ] Đã xác định nguồn log/metric/PCAP cần thiết và tính chính xác timestamp UTC.
- [ ] Đã bảo vệ chứng cứ, phân loại thông tin, giữ bản gốc và kiểm soát chia sẻ.
- [ ] Đã dựng timeline sơ bộ, tách fact, hypothesis và phần chưa biết.
- [ ] Đã mời đúng các vai trò tham gia và chuẩn bị impact statement.

### Trong buổi review

- [ ] Đã thống nhất phạm vi tác động và cách xác định thời điểm phát hiện/khôi phục.
- [ ] Đã kiểm tra evidence cho các mốc quan trọng và ghi các khoảng trống.
- [ ] Đã phân biệt trigger, cơ chế trực tiếp, điều kiện hệ thống và lỗi kiểm soát.
- [ ] Đã ghi điều hoạt động tốt, điểm yếu trong detection, triage, containment, recovery.
- [ ] Đã tạo action item có owner, mức ưu tiên, due date, acceptance criteria và test.
- [ ] Đã quyết định owner cho các rủi ro tồn đọng và câu hỏi chưa xác minh.

### Sau buổi review

- [ ] Đã công bố bản PIR theo phân loại; giới hạn phụ lục nhạy cảm.
- [ ] Đã đưa action vào hệ thống theo dõi và liên kết tới incident.
- [ ] Đã review blockers và thay đổi deadline có ghi lý do/phê duyệt.
- [ ] Đã kiểm tra triển khai, hiệu quả, tác động phụ và phương án rollback.
- [ ] Đã có người xác nhận trạng thái Verified và bằng chứng đóng.
- [ ] Đã có ngày xem lại chỉ số, lessons learned và khả năng tái diễn.
- [ ] Đã tuân thủ lịch lưu/xóa chứng cứ và yêu cầu legal hold (nếu có).

## 17. Câu hỏi tự kiểm tra

**1. Sau khi khôi phục dịch vụ, đội vận hành ghi “nguyên nhân do cấu hình sai”, không có action item. PIR thiếu gì?**

Thiếu phân tích điều kiện cho phép sai cấu hình đến production, các kiểm soát đã thất bại, owner, deadline, acceptance criteria và cách kiểm tra giảm khả năng tái diễn.

**2. Tại sao một action “tạo cảnh báo DNS” chưa đủ tốt?**

Nó chưa mô tả tiêu chí phát hiện, ngưỡng, phạm vi resolver, nơi gửi cảnh báo, ai nhận, false positive và cách test end-to-end. Cần biết tín hiệu nào chứng minh cảnh báo thực sự hữu ích.

**3. Trong timeline, thời điểm có alert là 09:07 nhưng request đầu tiên lỗi 09:03. Có thể gọi 09:07 là sự cố bắt đầu không?**

Không. Theo bằng chứng hiện có, 09:03 là mốc tác động sớm nhất được xác nhận; 09:07 là mốc phát hiện. Phải ghi rõ cách đo và khả năng có tác động trước 09:03 chưa được quan sát.

**4. Nếu action đã triển khai và PR merged nhưng chưa có test chứng minh canary/rollback hoạt động, nên đóng Verified chưa?**

Chưa. Cần đáp ứng acceptance criteria, xác nhận triển khai đúng môi trường và ghi bằng chứng kiểm thử, trừ khi có quyết định chấp nhận rủi ro rõ ràng theo quy trình.

**5. Nếu điều tra không thấy IOC trong log, có thể khẳng định không bị xâm nhập không?**

Không. Kết luận phải giới hạn theo phạm vi, thời gian lưu và chất lượng nguồn đã kiểm tra. Có thể ghi “chưa tìm thấy bằng chứng trong dữ liệu hiện có” và xác định bước điều tra bổ sung nếu rủi ro đáng kể.

**6. Vì sao buổi PIR nên có đại diện Network, Security và Application khi API timeout sau thay đổi IPS?**

Để đối chiếu hành vi tại client/VPN/IPS/LB/app, xác định thành phần gây drop và tác động tới nghiệp vụ, đồng thời tạo action đúng owner: policy, kiểm thử, monitoring, rollback và xác minh phục hồi.

---

**Ghi nhớ:** PIR có giá trị khi nối liền **bằng chứng → diễn biến → cơ chế và điều kiện góp phần → action item có trách nhiệm → kiểm tra hiệu quả**. Mục đích không phải chứng minh ai đã sai, mà là làm cho kiến trúc mạng, vận hành an ninh và quy trình ứng cứu ngày càng ít có cơ hội lặp lại cùng một kiểu sự cố.

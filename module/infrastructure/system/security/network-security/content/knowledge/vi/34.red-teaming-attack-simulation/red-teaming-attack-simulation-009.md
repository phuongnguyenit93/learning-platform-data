# Phân biệt red team, penetration test và purple team

## 1. Ba cách kiểm thử có cùng mục tiêu bảo mật nhưng câu hỏi khác nhau

Một tổ chức có firewall, VPN, phân đoạn mạng, IDS/IPS và hệ thống giám sát đầy đủ vẫn có thể chưa biết các lớp phòng vệ có **hoạt động cùng nhau khi xảy ra một chuỗi hành vi tấn công** hay không. Để đánh giá có hệ thống, người làm an toàn thông tin thường sử dụng **penetration test (kiểm thử xâm nhập)**, **red team (đội mô phỏng đối thủ)** và **purple team (hoạt động phối hợp kiểm thử–phòng thủ)**.

Ba thuật ngữ này có liên quan, nhưng **không đồng nghĩa**:

- **Penetration test:** *Trong phạm vi được phép, có những điểm yếu nào có thể khai thác, ảnh hưởng cụ thể ra sao và phải sửa gì?*
- **Red team:** *Một đối thủ với năng lực và mục tiêu đã mô hình hóa có thể tiến đến mục tiêu nào qua nhiều lớp phòng vệ, và tổ chức có phát hiện, ngăn chặn, phản ứng kịp không?*
- **Purple team:** *Khi chủ động cho bên mô phỏng và bên phòng thủ phối hợp, tín hiệu nào cần được phát hiện, quy tắc nào thiếu và cải tiến nào đã được chứng minh hoạt động?*

Bài thuộc chương **Red team và mô phỏng tấn công mạng** trong module **SECURITY_NETWORK_SECURITY**. Các ví dụ liên hệ trực tiếp tới phân đoạn mạng, firewall, VPN, kiểm soát định danh, IDS/IPS, DNS, Wi-Fi và hạ tầng đám mây. Phạm vi thảo luận là **hoạt động được ủy quyền**, với mục tiêu học tập, kiểm tra phòng thủ và cải thiện khả năng chống chịu.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích được mục tiêu, phạm vi, phương pháp, bằng chứng và đầu ra của từng hình thức.
2. Phân biệt **kiểm thử lỗ hổng riêng lẻ** với **kiểm chứng chuỗi tấn công và năng lực phản ứng**.
3. Thiết kế một tình huống thử nghiệm trên môi trường mạng theo cả ba góc nhìn.
4. Lập **Rules of Engagement (ROE)** và tiêu chí dừng để thử nghiệm không gây ảnh hưởng ngoài ý muốn.
5. Đọc các chỉ số kết quả như mức độ ảnh hưởng, tỷ lệ phát hiện, độ trễ phát hiện và độ hiệu quả sau cải tiến.
6. Quyết định nên chọn penetration test, red team, purple team hoặc kết hợp dựa trên câu hỏi cần trả lời.

## 2. Bảng so sánh tổng quan

| Khía cạnh | Penetration test | Red team | Purple team |
| --- | --- | --- | --- |
| **Câu hỏi chính** | Điểm yếu có thể bị khai thác ở đâu? | Đối thủ có thể đạt mục tiêu nào qua nhiều lớp bảo vệ? | Phòng thủ đang nhìn thấy gì, thiếu gì, sửa và xác minh thế nào? |
| **Đơn vị đánh giá** | Ứng dụng, host, thiết bị, dịch vụ, segment hoặc bề mặt được giao | Chuỗi hành vi theo mục tiêu và giả thuyết đối thủ | Từng hành vi kiểm thử, telemetry, detection, triage và phản ứng |
| **Phạm vi** | Thường xác định chặt theo danh sách tài sản và phương pháp | Có thể trải qua nhiều hệ thống/người/quy trình, nhưng vẫn bị giới hạn bởi ROE | Theo tập hành vi, use case phòng thủ hoặc chuỗi sự kiện cần cải thiện |
| **Thông tin ban đầu** | Có thể black-box, gray-box hoặc white-box | Dựa trên threat scenario, mức thông tin được quy định | Hai bên trao đổi thông tin đủ để kiểm thử và tinh chỉnh |
| **Phối hợp với blue team** | Thường báo trước và điều phối theo phạm vi | Có thể hạn chế tiết lộ chi tiết cho SOC nếu ROE cho phép; có white cell quản lý an toàn | Hợp tác chủ động, kiểm tra và phản hồi nhanh |
| **Ưu tiên** | Khám phá và xác nhận lỗ hổng, mức tác động, khắc phục | Đánh giá khả năng bảo vệ một mục tiêu, phát hiện và ứng phó | Tăng độ phủ và chất lượng phát hiện/phản ứng |
| **Thời gian** | Thường tương đối ngắn, phụ thuộc phạm vi | Có thể kéo dài hơn để kiểm tra nhiều giai đoạn | Có thể chạy theo buổi, sprint hoặc chương trình lặp lại |
| **Công cụ** | Kiểm tra thủ công, scanner, đánh giá cấu hình, kiểm thử theo kịch bản | Kỹ thuật mô phỏng đối thủ, đánh giá liên kết kiểm soát, công cụ điều phối | Tác vụ mô phỏng có kiểm soát, SIEM/EDR/NDR, detection engineering |
| **Chỉ số quan trọng** | Điểm yếu đã xác nhận, mức độ ảnh hưởng, tỷ lệ khắc phục qua retest | Mục tiêu đạt/không đạt, thời gian phát hiện, phản ứng và điểm đứt của chuỗi phòng vệ | Tỷ lệ test có tín hiệu, phát hiện đúng, điều tra đúng và cải tiến đã qua retest |
| **Sản phẩm cuối** | Báo cáo lỗ hổng có bằng chứng và hướng sửa | Narrative/timeline, phát hiện về con người–quy trình–công nghệ, đánh giá mục tiêu | Detection gap register, rule/playbook cải tiến, evidence trước–sau |
| **Điểm hạn chế** | Có thể bỏ qua kết hợp nhiều điểm yếu và khả năng SOC ứng phó | Không chứng minh mọi bề mặt đều sạch; kết quả phụ thuộc kịch bản | Không tự thay thế việc tìm lỗ hổng trên diện rộng hoặc kiểm tra độc lập |

**Độ sâu khai thác không phải tiêu chí duy nhất để phân loại.** Một penetration test có thể rất sâu về kỹ thuật; một red team engagement có thể dùng phương thức mô phỏng ít xâm nhập để kiểm chứng phát hiện và phản ứng. Purple team cũng không nhất thiết là một phòng ban độc lập: đây thường là **cách tổ chức phối hợp** giữa người mô phỏng và người phòng thủ.

## 3. Penetration test: tìm và chứng minh điểm yếu

### 3.1. Mục tiêu và cách tư duy

**Penetration testing** là hoạt động được ủy quyền nhằm xác định và xác thực điểm yếu bảo mật có thể bị lợi dụng trong **phạm vi tài sản đã thỏa thuận**. Kiểm thử viên đánh giá lỗ hổng, cấu hình sai, xác thực/phân quyền yếu, phân đoạn mạng không đúng, lỗi logic ứng dụng hoặc thành phần lỗi thời; khi cần, họ chứng minh ảnh hưởng bằng cách an toàn và có kiểm soát.

Ví dụ câu hỏi trong phạm vi network security:

- Firewall có cho phép máy trạm truy cập trực tiếp VLAN cơ sở dữ liệu ngoài ma trận chính sách không?
- Cổng quản trị trên VPN gateway có bị lộ tới vùng không được phép không?
- Wi-Fi guest có truy cập được hệ thống nội bộ đáng lẽ phải tách biệt không?
- Thiết bị mạng có còn dùng firmware có lỗ hổng áp dụng theo advisory của nhà sản xuất không?
- Một tài khoản người dùng thử nghiệm có được cấp quyền quá rộng trong giao diện cấu hình cloud firewall không?

### 3.2. Quy trình điển hình

~~~mermaid
flowchart LR
    A["Thỏa thuận phạm vi và ROE"] --> B["Lập danh mục bề mặt"]
    B --> C["Đánh giá cấu hình và điểm yếu"]
    C --> D["Xác thực ảnh hưởng an toàn"]
    D --> E["Đánh giá rủi ro và nguyên nhân"]
    E --> F["Báo cáo, khắc phục, retest"]
~~~

Một chu trình có thể gồm:

1. **Scoping:** xác định IP/FQDN, vùng mạng, ứng dụng, tài khoản thử, loại test được phép, thời gian và hệ thống không được chạm tới.
2. **Reconnaissance có giới hạn:** thu thập thông tin phục vụ kiểm thử, ưu tiên danh mục được cung cấp và nguồn đã được phê duyệt.
3. **Đánh giá:** rà soát cấu hình, giao thức, bản vá, xác thực và luồng kết nối theo từng hạng mục.
4. **Validation:** xác nhận lỗ hổng bằng bằng chứng tác động tối thiểu. Không cần trích xuất dữ liệu thật hay giành quyền quản trị toàn hệ thống để chứng minh một phân quyền sai.
5. **Risk analysis:** mô tả điều kiện khai thác, ảnh hưởng tới CIA (confidentiality, integrity, availability), độ khó và các biện pháp giảm thiểu hiện hữu.
6. **Remediation và retest:** đề xuất cách sửa, kiểm tra đã sửa đúng và không ảnh hưởng chức năng cần thiết.

Đầu ra quan trọng là **danh sách phát hiện có thể hành động**: tài sản, lỗ hổng, điều kiện, bằng chứng, mức ảnh hưởng, cách khắc phục, owner và kết quả retest.

### 3.3. Điều penetration test chưa tự chứng minh

Ngay cả khi tìm thấy lỗi nghiêm trọng, penetration test **không mặc nhiên cho biết** SOC có phát hiện được chuỗi tấn công thực tế, nhóm ứng phó có phối hợp tốt hay một đối thủ cụ thể có thể đạt mục tiêu trong điều kiện doanh nghiệp đang vận hành. Ngược lại, một pentest không tìm ra lỗi không phải bảo đảm tuyệt đối rằng hạ tầng không thể bị xâm nhập: kết quả phụ thuộc thời gian, phạm vi, kỹ thuật được phép và những phần không thể quan sát.

**Black-box, gray-box, white-box** mô tả mức thông tin/khả năng truy cập người kiểm thử được cấp, **không phải ba hình thức đồng nghĩa với pentest, red team và purple team**. Ví dụ, cả pentest và red team đều có thể bắt đầu với thông tin hạn chế.

## 4. Red team: kiểm chứng chuỗi bảo vệ trước đối thủ mô phỏng

### 4.1. Red team khác gì?

**Red teaming** là hoạt động mô phỏng hành vi đối thủ với **mục tiêu và giả thuyết đe dọa được lựa chọn**. Thay vì hỏi “có bao nhiêu lỗ hổng?”, một engagement có thể hỏi:

> Nếu một tài khoản VPN có quyền hạn giới hạn bị chiếm quyền trong giả định thử nghiệm, tổ chức có phát hiện và ngăn được chuỗi truy cập tới vùng tài chính đã phân đoạn hay không?

Những yếu tố red team quan tâm gồm:

- **Mục tiêu nghiệp vụ đã thỏa thuận:** ví dụ kiểm chứng khả năng tiếp cận một tài sản quan trọng, không cần thực hiện hành vi gây hại thật.
- **Mô hình đối thủ:** động cơ, điều kiện ban đầu, khả năng, TTP (tactics, techniques and procedures) phù hợp với threat intelligence.
- **Đường liên kết nhiều lớp:** định danh/VPN → truy cập mạng → phân đoạn/firewall → dịch vụ → giám sát → ứng phó.
- **Khả năng phát hiện và phản ứng:** SOC có thấy hành vi? Ai tiếp nhận? Có điều tra đúng? Có ngăn chuỗi mục tiêu kịp lúc?
- **Điều kiện an toàn:** mô phỏng bằng tài khoản và hệ thống được duyệt, dữ liệu giả, marker hoặc bằng chứng không gây gián đoạn.

Red team không bắt buộc phải khai thác một lỗ hổng hoàn toàn mới. Có thể bắt đầu từ **assumed breach**: giả định đối thủ đã có một quyền truy cập ban đầu do người điều phối cấp, nhằm tập trung đánh giá kiểm soát nội bộ và khả năng phát hiện thay vì dành thời gian vượt qua một cửa vào không nằm trong mục tiêu.

### 4.2. Quy trình red team điển hình

1. **Chọn mục tiêu và đối thủ:** dựa trên rủi ro kinh doanh, thiết bị/dịch vụ trọng yếu và threat model.
2. **Thiết kế scenario:** nêu giả định ban đầu, đường tiến triển có thể xảy ra, TTP dự kiến, bằng chứng cần có và điều kiện đạt.
3. **Ban hành ROE:** thống nhất hệ thống được phép, kỹ thuật cấm, thời điểm, mức lưu lượng, dữ liệu giả, white cell, kênh dừng khẩn cấp và quy tắc phối hợp với SOC.
4. **Thực hiện theo kịch bản được duyệt:** mô phỏng từng hành vi với giới hạn tác động; giữ nhật ký thời gian và bằng chứng.
5. **Ghi nhận blue team:** cảnh báo có tạo ra không, có được phân loại đúng không, phản ứng có diễn ra trong giới hạn chấp nhận không.
6. **Đối chiếu (debrief):** hợp nhất timeline hai phía để tìm điểm mất tín hiệu hoặc điểm nghẽn điều phối; tạo kế hoạch cải tiến và retest.

Không phải engagement nào cũng thử kỹ thuật con người (phishing, gọi điện giả mạo, truy cập vật lý). Những hoạt động này cần **quyền riêng, giới hạn đối tượng và biện pháp bảo vệ** nếu có trong ROE; không tự thêm chỉ vì gọi là red team.

### 4.3. Điều kiện thành công và giới hạn diễn giải

Một kịch bản có thể được ghi nhận là **mục tiêu mô phỏng đã đạt**, nhưng đồng thời blue team phát hiện rất sớm và xử lý đúng, hoặc ngược lại red team không đạt mục tiêu vì giới hạn thời gian trong khi một thiếu sót phát hiện vẫn còn. Vì vậy cần báo cáo **mục tiêu, đường thử, phần nào được mô phỏng, phần nào không, sự kiện đã thấy và phản ứng của tổ chức**. Không dùng chỉ số “red thắng/blue thua” làm kết luận duy nhất.

Mỗi cuộc diễn tập chỉ quan sát **một tập giả thuyết, tài sản và thời điểm cụ thể**; nó không thay thế danh mục lỗ hổng toàn tổ chức hoặc kiểm thử tuân thủ thường kỳ.

## 5. Purple team: biến hành vi kiểm thử thành cải tiến đã xác minh

### 5.1. Purple team là phương pháp phối hợp

Trong một hoạt động **purple teaming**, người mô phỏng hành vi đối thủ và người vận hành phòng thủ **chia sẻ kịch bản, tín hiệu và kết quả**, thường theo vòng lặp ngắn. Mục tiêu chính là nâng chất lượng **telemetry, detection logic, triage, điều tra, containment và playbook**.

Ví dụ, đội mô phỏng tạo một chuỗi đăng nhập bằng **tài khoản test** vào VPN từ môi trường được ủy quyền rồi thử kết nối tới một đích kiểm thử trong vùng khác. Blue team kiểm tra VPN logs, IdP, firewall flow logs và SIEM:

- Có sự kiện đăng nhập và thay đổi vị trí/thiết bị như dự kiến không?
- Một luồng bị firewall từ chối có đến được pipeline SIEM không?
- Cảnh báo có gắn đúng user, IP, thiết bị, zone và thời điểm không?
- Điều tra viên có đủ bằng chứng để phân biệt thử nghiệm với sự cố thực không?
- Sau khi chỉnh log/rule/playbook, **chạy lại cùng phép thử** có cho kết quả tốt hơn không?

### 5.2. Vòng lặp kiểm chứng

~~~mermaid
flowchart TD
    A["Chọn TTP/use case và tiêu chí phát hiện"] --> B["Xác nhận telemetry cần có"]
    B --> C["Mô phỏng hành vi đã được duyệt"]
    C --> D["Blue team quan sát, điều tra, phản ứng"]
    D --> E{"Đạt tiêu chí?"}
    E -->|"Chưa"| F["Sửa thu thập log, detection, playbook"]
    F --> C
    E -->|"Đạt"| G["Lưu evidence và đóng test case"]
    G --> H["Đưa vào kiểm thử hồi quy"]
~~~

Purple team **không nhất thiết phải tồn tại như một nhóm riêng**. Một chương trình có thể tổ chức các buổi hợp tác giữa red team, SOC, network security, IAM, cloud security và đội phát triển. Điểm khác biệt là **truyền kiến thức và kiểm chứng cải tiến ngay trong quy trình**, thay vì chỉ có một báo cáo bàn giao sau khi kết thúc.

### 5.3. Đầu ra hữu ích

- Ma trận test case/TTP → nguồn telemetry → detection rule → playbook → kết quả.
- Danh sách **gaps**: không có log, field thiếu, rule quá nhiễu, thiếu enrichment, khó xác nhận owner hoặc phản ứng chậm.
- Phân tích **before/after** sau thay đổi, bao gồm tỷ lệ test pass và tác dụng phụ đối với hoạt động hợp lệ.
- Những điều kiện cần đưa vào **kiểm thử hồi quy** mỗi khi đổi firmware, firewall rule, VPN, SIEM hoặc hệ thống định danh.

Purple team cũng có thể phát hiện lỗ hổng, nhưng kết quả quan trọng nhất là **phòng thủ được cải thiện bằng bằng chứng thực nghiệm**.

## 6. Nhìn ba hình thức trên cùng một tình huống mạng

### 6.1. Bài toán chung

Một doanh nghiệp có người dùng truy cập ứng dụng nội bộ qua VPN/ZTNA. Vùng **USER/VPN** được phép dùng HTTPS tới ứng dụng; vùng **DATABASE** chỉ chấp nhận kết nối từ backend đã được phê duyệt. SOC nhận log từ VPN, IdP, firewall, IDS/IPS và EDR.

~~~mermaid
flowchart LR
    U["Tài khoản/thiết bị thử nghiệm"] --> V["VPN / ZTNA"]
    V --> F["Firewall phân đoạn"]
    F --> A["Ứng dụng nội bộ HTTPS"]
    A --> D["Database"]
    F -.->|"Default deny"| D
    V --> L["VPN + IdP logs"]
    F --> N["Firewall / IDS logs"]
    L --> S["SIEM / SOC"]
    N --> S
~~~

### 6.2. Ba phương án tiếp cận

| Hình thức | Câu hỏi trong cùng tình huống | Hoạt động đã được duyệt | Bằng chứng cuối |
| --- | --- | --- | --- |
| **Penetration test** | Có lỗi ACL/segmentation hoặc phân quyền cho user VPN truy cập thẳng database? | Kiểm thử cặp nguồn–đích–cổng được phê duyệt, rà soát rule và cấu hình, xác nhận tác động ở mức tối thiểu | Rule sai/đúng, tuyến thực tế, bằng chứng test âm/dương, mức ảnh hưởng, khuyến nghị sửa |
| **Red team** | Một đối thủ bắt đầu từ quyền VPN thử nghiệm có thể tiến gần mục tiêu đã định, và SOC có phát hiện/đáp ứng? | Mô phỏng chuỗi hành vi trong phạm vi, dùng host và dữ liệu giả, ghi timeline; blue team xử lý theo ROE | Timeline red–blue, checkpoint đạt/chưa đạt, thời gian phát hiện/phản ứng, điểm yếu liên kết |
| **Purple team** | SOC có quan sát và cảnh báo chính xác các hành vi VPN bất thường, chặn phân đoạn, truy cập ứng dụng không? | Chạy từng test case, xem log cùng blue team, chỉnh rule/playbook, chạy lại | Ma trận detection, field/log còn thiếu, kết quả trước–sau, test hồi quy |

**Cùng một firewall default deny** có thể là đối tượng của cả ba: pentest kiểm tra **đường truy cập bị cấm**, red team đánh giá **đường tấn công và phản ứng tổng thể**, purple team kiểm chứng **log/cảnh báo và quy trình xử lý** khi hành vi bị ngăn chặn hoặc xảy ra bất thường.

### 6.3. Ví dụ bản ghi kết quả khác nhau

**Penetration test:** “Từ tài khoản kiểm thử thuộc nhóm VPN-USER, kết nối TCP tới database bị chặn trên firewall F-01 theo policy P-12. Khi thay bằng địa chỉ nguồn khác được cấp phép kiểm tra, phát hiện một ngoại lệ cũ cho phép dải rộng hơn yêu cầu; đã xác nhận rule hit bằng log và đề nghị thu hẹp ngoại lệ.”

**Red team:** “Trong kịch bản assumed breach, chuỗi liên lạc thử qua VLAN đã bị chặn ở bước truy cập DATABASE. Firewall ghi nhận sự kiện, nhưng SOC không tạo case vì thiếu ánh xạ rule và asset criticality. Mục tiêu cuối không đạt; yêu cầu cải thiện khả năng phát hiện/ưu tiên sự kiện vẫn tồn tại.”

**Purple team:** “Sau khi bổ sung enrichment tài sản, sửa correlation rule và điều chỉnh playbook, lần chạy lại cùng test case tạo alert có đủ tài khoản, IP nguồn, zone, policy ID và asset owner. Điều tra viên xác định đúng nguyên nhân trong giới hạn thời gian mục tiêu; lưu evidence và test hồi quy.”

Các kết quả trên là **tình huống giả lập** nhằm minh họa cách viết báo cáo, không phải phát hiện thực tế trên một hệ thống cụ thể.

## 7. Lập phạm vi, ROE và kiểm soát an toàn

Red teaming và penetration testing đều là các hoạt động kỹ thuật **có thể ảnh hưởng tới hệ thống**, vì vậy phải được **ủy quyền rõ ràng**. Purple team cũng cần giới hạn phạm vi vì một phép mô phỏng có kiểm soát vẫn có thể làm tăng log, thay đổi trạng thái endpoint hoặc gây cảnh báo vận hành.

### 7.1. Những nội dung ROE phải làm rõ

| Thành phần | Câu hỏi phải trả lời |
| --- | --- |
| **Quyền thực hiện** | Ai sở hữu tài sản, ai phê duyệt, khi nào hiệu lực bắt đầu/kết thúc? Có bên thứ ba cần đồng ý riêng? |
| **Mục tiêu và phạm vi** | IP, FQDN, tenant, VLAN, tài khoản, thiết bị và hệ thống nào được phép; hệ thống nào **ngoài phạm vi**? |
| **Mức độ kỹ thuật** | Chỉ quan sát, test cấu hình, mô phỏng hành vi, kiểm chứng tác động ở mức nào? Những kỹ thuật nào bị cấm? |
| **Tài khoản/dữ liệu** | Có tài khoản lab và dữ liệu canary/giả không? Làm sao bảo vệ dữ liệu thật nếu vô tình nhìn thấy? |
| **Giới hạn an toàn** | Lưu lượng tối đa, lịch chạy, hệ thống nhạy cảm, sao lưu, tính sẵn sàng, thời điểm ngắt thử nghiệm? |
| **Thông báo** | Ai biết đầy đủ, ai chỉ biết mục tiêu chung, blue team có biết trước từng test không? |
| **White cell** | Nhóm điều phối trung lập giữ ROE, theo dõi rủi ro và có quyền dừng là ai? |
| **Kênh liên lạc** | Cách báo khẩn cấp khi có sự cố thật, alert bất ngờ hoặc rủi ro ảnh hưởng người dùng? |
| **Bảo toàn chứng cứ** | Đồng bộ thời gian, nhật ký nguồn, cách lưu bằng chứng, phân quyền và quy định bảo mật? |
| **Cleanup** | Thu hồi user/token test, xóa rule/tài sản tạm, phục hồi config, xác minh không còn hiệu ứng? |
| **Điều kiện dừng** | Khi nào dừng ngay: mất dịch vụ, không còn giám sát, vượt phạm vi, xuất hiện dữ liệu nhạy cảm? |
| **Phê duyệt thay đổi** | Nếu cần thay đổi scope hoặc kỹ thuật, ai quyết định và bằng cách nào? |

**Đối với red team:** bí mật kịch bản đối với một bộ phận SOC **không đồng nghĩa** không ai được biết. White cell và người có thẩm quyền phải có thông tin, kênh cứu hộ và quyền dừng. Nếu SOC phản ứng như với sự cố thật, tình huống an toàn phải được kiểm soát để không gây gián đoạn ngoài kịch bản.

### 7.2. Mẫu ROE rút gọn

~~~yaml
exercise_id: NT-EXERCISE-009
exercise_type: purple_team
objective: "Kiểm chứng phát hiện đăng nhập VPN và truy cập trái phép giữa hai zone"
owner: network-security
approval_status: approved
scope:
  test_sources:
    - "10.10.10.21"    # Host test do tổ chức sở hữu
  test_destinations:
    - "10.20.20.10"    # Endpoint giả lập
  test_accounts:
    - "exercise-user"
  excluded:
    - "production-database"
    - "third-party-systems"
allowed_actions:
  - "controlled test login"
  - "limited benign connection attempts to approved endpoints"
  - "read-only review of approved firewall and VPN logs"
prohibited_actions:
  - "service disruption or load testing"
  - "real credential harvesting"
  - "modification or extraction of real business data"
  - "persistence outside approved test infrastructure"
control:
  white_cell: "exercise-coordinator"
  stop_condition: "production impact, unexpected scope, loss of monitoring"
  evidence_storage: "approved-evidence-repository"
  cleanup_required: true
  retest_after_improvement: true
~~~

Đây là **schema minh họa**, chưa đủ để tự động cho phép triển khai. Một ROE chính thức còn cần tên người phê duyệt, lịch thực hiện, kênh liên lạc khẩn cấp và quy trình ứng phó. IP dùng trong ví dụ là địa chỉ riêng, chỉ biểu diễn mạng thực hành.

### 7.3. Thực hành an toàn khi mô phỏng

**Ưu tiên mô phỏng tác động thay vì tạo tác động thật:** ví dụ dùng canary/test record để chứng minh khả năng truy cập vùng được bảo vệ, thay vì sao chép dữ liệu thật; sử dụng hành vi kiểm thử lành tính để tạo tín hiệu điều tra thay vì thực hiện mã phá hoại hoặc làm gián đoạn. Cách mô phỏng cần giữ đủ fidelity để kiểm tra kiểm soát mục tiêu và được ghi rõ trong báo cáo.

Khi bất ngờ phát hiện dấu hiệu xâm nhập thật, dữ liệu nhạy cảm ngoài phạm vi hoặc hệ thống sản xuất suy giảm, người thực hiện phải **dừng theo ROE, bảo toàn chứng cứ và thông báo kênh đã quy định**. Không tự mở rộng nhiệm vụ để tiếp tục điều tra các hệ thống chưa được cho phép.

## 8. Thiết kế phép thử và bản đồ ATT&CK

**MITRE ATT&CK** là hệ thống tri thức công khai về các chiến thuật và kỹ thuật đối thủ được quan sát trong thực tế. Có thể dùng để mô tả **hành vi mục tiêu, điều kiện tiên quyết và nguồn telemetry cần thiết** cho red/purple team. ATT&CK là một **ngôn ngữ chung**, không phải danh sách kiểm thử bắt buộc hay chứng nhận rằng đã mô phỏng đầy đủ mọi đối thủ.

### 8.1. Ma trận quan sát mẫu

| Hành vi/kịch bản đã duyệt | Nguồn tín hiệu kỳ vọng | Blue team phải làm gì? | Cách xác minh |
| --- | --- | --- | --- |
| Đăng nhập thử nghiệm vào VPN từ thiết bị mới | VPN gateway, IdP, device posture, MFA logs | Gắn được user, thiết bị, trạng thái xác thực và mức rủi ro | So thời điểm test với log và case |
| Kết nối từ VLAN USER sang vùng DATABASE bị chặn | Firewall allow/deny, flow logs, NDR | Xác định đúng source, destination, zone, policy và mức ưu tiên | Đối chiếu packet path và rule ID |
| Truy vấn DNS tới domain test do tổ chức quản lý | DNS resolver, proxy, EDR/DNS telemetry | Xác định host phát sinh, domain và chính sách | Xem DNS log và enrichment |
| Truy cập một endpoint HTTPS canary | Proxy/WAF, flow logs, server access log | Phân biệt giao dịch kiểm thử với truy cập trái phép | Gắn request ID, tài khoản test và log |
| API quản trị từ service account test ngoài lịch | API audit, IAM, SIEM | Phát hiện lệch lịch/quyền, điều tra nguồn và xác thực | So token identity và audit trail |
| Thay đổi rule firewall **trong lab** qua quy trình đã duyệt | Config audit, controller, change management | Có cảnh báo thay đổi không có ticket hợp lệ | So bản chạy trước–sau, ticket và alert |

Trong red team, ma trận có thể giữ bí mật với một phần blue team để kiểm tra khả năng ứng phó tự nhiên. Trong purple team, ma trận thường là **đầu vào chung** để hai phía điều chỉnh telemetry và test lại. Với pentest, ma trận này có thể bổ trợ các phát hiện cấu hình nhưng không thay thế kiểm tra lỗ hổng.

### 8.2. Định nghĩa test case có thể lặp lại

Một test case tốt nên có:

- **ID và mục tiêu:** ví dụ PT-SEG-004: phát hiện luồng thử từ VPN USER tới vùng DATA.
- **Điều kiện ban đầu:** tài khoản thử, tuyến mạng, phiên bản policy và môi trường đã phê duyệt.
- **Hành vi kích hoạt:** thao tác mô phỏng tối thiểu, có thể lặp lại và an toàn.
- **Tín hiệu phải có:** log nguồn, field quan trọng, timestamp, ID correlating và nơi lưu.
- **Kết quả chấp nhận:** alert tạo ra, đối tượng được gắn nhãn đúng, triage và hành động đúng theo runbook.
- **Điều kiện không đạt:** không có log, mất field, báo sai tài sản hoặc trễ quá ngưỡng đã thống nhất.
- **Cleanup và retest:** cách trở về baseline, thời điểm kiểm tra lại.

Không nên đánh đồng **event generated**, **event ingested**, **alert fired**, **triaged correctly** và **response executed**. Chúng là các chặng khác nhau; purple team thường đo và cải thiện từng chặng.

## 9. Đo lường kết quả đúng với mục tiêu

### 9.1. Penetration test

Các chỉ số hữu ích:

- **Số phát hiện đã xác nhận**, có mức ảnh hưởng và bằng chứng đầy đủ.
- **Tài sản/bề mặt đã được kiểm tra** so với phạm vi được ủy quyền.
- **Tỷ lệ khắc phục và retest pass**: phần trăm phát hiện được sửa và xác nhận đã sửa, tính trên tập có thể retest.
- **Thời gian tới khi khắc phục** theo mức độ rủi ro và owner.

Không chỉ xếp hạng người kiểm thử theo “số CVE tìm được”. Một lỗi phân đoạn cho phép truy cập dữ liệu nhạy cảm có thể có giá trị cải thiện bảo mật cao hơn hàng chục phát hiện cấu hình mức thấp. Mặt khác, một báo cáo “0 finding” phải nêu rõ phạm vi và phương pháp, tránh gây hiểu nhầm là hệ thống đã an toàn tuyệt đối.

### 9.2. Red team

Tập trung vào:

- **Objective attainment:** mục tiêu mô phỏng đã đạt, bị chặn, chưa thử hoặc không thể kết luận.
- **Time to detect:** từ sự kiện đánh dấu tới thời điểm phát hiện đủ chất lượng theo định nghĩa ROE.
- **Time to triage / time to contain:** thời gian phân loại, xác minh và đưa ra biện pháp ngăn chặn phù hợp.
- **Detection/response gaps:** chặng nào bị mất tín hiệu hoặc quy trình phối hợp không hiệu quả.
- **Control effectiveness:** điểm nào trong chuỗi bị chặn, ngăn chặn đúng hay vô tình làm gián đoạn.

Ví dụ, chỉ số **time to detect** có thể tính:

\[
TTD = t_{\mathrm{detection}} - t_{\mathrm{emulation\ event}}
\]

Chỉ số này chỉ có ý nghĩa khi có đồng hồ thống nhất, xác định rõ thế nào là “phát hiện” (sinh alert hay con người xác nhận), và gắn đúng sự kiện test. Nếu có nhiều vòng thử, nên báo trung vị, phân bố và các trường hợp không phát hiện thay vì che giấu bằng trung bình đơn giản.

### 9.3. Purple team

Nhìn vào **kết quả cải tiến có thể kiểm chứng**:

| Chỉ số | Cách đo gợi ý | Cần tránh |
| --- | --- | --- |
| Telemetry coverage | Test case có đủ log và các field cần thiết / test case đủ điều kiện | Coi có log bất kỳ là đủ tín hiệu phân tích |
| Detection coverage | Test case tạo ra alert đúng / test case có tiêu chí cảnh báo đã định | Đếm alert nhiễu hoặc cảnh báo nhầm là pass |
| Triage correctness | Case được phân loại đúng và gắn đúng tài sản/ngữ cảnh / case đã kiểm tra | Chỉ đo rule fired mà bỏ điều tra |
| Detection latency | Phân bố độ trễ từ sự kiện đến alert/triage theo định nghĩa | So số liệu khi timestamp/collector bị lệch |
| Retest pass rate | Use case sau cải tiến đạt lại tiêu chí / use case đã retest | Chỉ ghi “đã sửa” trên ticket |
| Operational cost | Tác động tới false positive, tải log, thời gian analyst, độ ổn định dịch vụ | Tăng số alert bằng mọi giá |

Một detection rule phát hiện 100% test case nhưng sinh hàng nghìn false positive mỗi ngày có thể làm giảm hiệu quả phòng thủ. Kết quả cần xem cả **độ nhạy, tính chính xác, mức nhiễu và khả năng vận hành**.

## 10. Chọn phương pháp theo mức trưởng thành và mục đích

| Tình huống | Ưu tiên | Lý do |
| --- | --- | --- |
| Một firewall/VPN vừa nâng cấp cần tìm lỗi cấu hình và phân quyền | **Penetration test** có phạm vi rõ | Xác minh vấn đề kỹ thuật và tác động trước/sau khắc phục |
| Phải trả lời liệu SOC có phát hiện hành vi định danh/mạng bất thường không | **Purple team** | Có thể lặp test, kiểm tra pipeline log, detection và runbook |
| Ban lãnh đạo cần đánh giá năng lực đối phó một đối thủ cụ thể nhắm vào dữ liệu nhạy cảm | **Red team** theo threat scenario | Kiểm chứng chuỗi công nghệ–con người–quy trình và phản ứng |
| Tổ chức chưa có inventory hoặc logging ổn định | **Làm nền tảng và pentest trọng điểm trước** | Thiếu phạm vi và telemetry khiến red team khó diễn giải, rủi ro vận hành tăng |
| Nhiều pentest đã xác nhận lỗ hổng nhưng detection vẫn yếu | **Purple team**, sau đó red team khi đủ điều kiện | Chuyển findings thành tín hiệu và phản ứng có thể kiểm chứng |
| Muốn đánh giá toàn diện trên chu kỳ dài | **Kết hợp theo giai đoạn** | Pentest tìm điểm yếu, purple cải thiện phòng thủ, red kiểm tra hiệu quả tổng thể |

Một chuỗi triển khai thực tế có thể là: **inventory/threat model → penetration test những bề mặt trọng yếu → khắc phục → purple team kiểm chứng telemetry → red team theo mục tiêu → debrief → cải tiến → retest**. Đây là một mô hình tham khảo, không phải thứ tự bắt buộc. Một tổ chức có SOC trưởng thành có thể chạy purple liên tục và red team định kỳ, trong khi pentest vẫn triển khai khi hệ thống thay đổi đáng kể.

**Không sử dụng ba tên gọi như cấp bậc tuyệt đối.** Mỗi phương pháp có giả định, ngân sách, điều kiện thành công và giới hạn riêng. Chọn theo **quyết định cần đưa ra sau kiểm thử**, thay vì theo mức độ hấp dẫn của thuật ngữ.

## 11. Cách phối hợp red, blue và white cell

| Vai trò | Trách nhiệm | Bằng chứng cần giữ |
| --- | --- | --- |
| **Red / người mô phỏng** | Thực thi hành vi được phép, ghi timestamp, test ID, kết quả và thay đổi trạng thái | Nhật ký thử, nguồn/đích, dữ liệu mẫu, mức độ mô phỏng |
| **Blue / SOC/IR/operations** | Thu log, phát hiện, phân loại, điều tra, phản ứng và ghi quyết định | Alert ID, case, truy vấn, incident timeline và hành động |
| **Purple facilitator** | Kết nối hai phía, giải thích chênh lệch, dẫn dắt retest và đo trước–sau | Ma trận detection gaps, kết quả kiểm thử lại |
| **White cell / control team** | Bảo đảm ROE, giám sát rủi ro, xử lý ngoại lệ, ra lệnh dừng | Phê duyệt, scope, thay đổi, dừng khẩn và thông báo |
| **Chủ dịch vụ/tài sản** | Xác nhận giá trị nghiệp vụ, giờ kiểm thử và mức tác động chấp nhận được | Bản đồ phụ thuộc, quyền sở hữu, biên bản nghiệm thu |

Trong thực tế, một người có thể đảm nhiệm nhiều vai trò, nhưng **quyền phê duyệt và quyền dừng** cần được xác định rõ. Nếu red team cần hạn chế lộ kịch bản cho SOC, white cell vẫn phải có kênh điều phối để tránh việc phản ứng thật gây ảnh hưởng hoặc nhầm lẫn với sự cố ngoài thử nghiệm.

### 11.1. Timeline phải đồng bộ

Ví dụ bảng đối chiếu:

| Thời điểm minh họa | Red ghi nhận | Blue ghi nhận | Nhận xét |
| --- | --- | --- | --- |
| 09:00 | Bắt đầu ca kiểm thử VPN bằng tài khoản test | IdP nhận sự kiện login | Sự kiện đã được ghi nhận |
| 09:03 | Thử kết nối TCP tới endpoint không được phép | Firewall deny, flow log có policy ID | Kiểm soát phân đoạn hoạt động |
| 09:05 | Thử request đến HTTPS canary | WAF/proxy nhận request | Có telemetry L7 |
| 09:10 | Kết thúc chuỗi đã được duyệt | SOC có event nhưng chưa tạo case | Gap ở correlation hoặc ngưỡng ưu tiên |
| 10:20 | Chạy lại phép thử sau điều chỉnh trong buổi purple | SOC nhận case có asset context | Cải tiến đã có bằng chứng; cần tiếp tục theo dõi nhiễu |

Mọi mốc trong bảng là **giả lập**. Khi báo cáo chính thức phải dùng timestamp có timezone, giải thích clock skew và dẫn chứng được truy vết về nguồn. Nếu log bị thu thập trễ, **thời điểm sự kiện**, **thời điểm SIEM ingest** và **thời điểm analyst nhận diện** cần tách riêng.

## 12. Những hiểu nhầm thường gặp

1. **“Red team chỉ là pentest khó hơn.”** Pentest ưu tiên xác thực điểm yếu trong phạm vi; red team ưu tiên mục tiêu đối thủ và chuỗi phòng vệ, có thể dùng kỹ thuật đơn giản để kiểm chứng phản ứng.
2. **“Purple team là nhóm tấn công thứ ba.”** Purple thường là mô hình phối hợp giữa mô phỏng và phòng thủ; kết quả quan trọng là telemetry, detection và playbook cải thiện.
3. **“Red team phải bí mật với tất cả mọi người.”** Hoạt động vẫn cần chủ sở hữu, white cell, ROE, kiểm soát an toàn và quyền dừng.
4. **“Một chiến dịch red team không đạt mục tiêu nghĩa là mọi kiểm soát đã tốt.”** Kết quả chỉ bao phủ kịch bản, thời gian, dữ liệu và giới hạn đã chọn; có thể còn gaps nghiêm trọng chưa được thử.
5. **“Penetration test không khai thác được thì không có rủi ro.”** Có thể chưa chạm đúng điều kiện, thời gian không đủ, scope giới hạn hoặc kiểm soát khác đã chặn đường thử.
6. **“Có alert là phát hiện thành công.”** Một event chưa được ingest, một alert bị bỏ qua hoặc gắn sai tài sản chưa đủ để khẳng định tổ chức có khả năng phát hiện/phản ứng.
7. **“Phát hiện càng nhiều alert càng tốt.”** Rule nhiều false positive có thể làm SOC quá tải; cần đo độ chính xác, chi phí vận hành và chất lượng triage.
8. **“Purple team cần diễn tập hành vi nguy hiểm cho giống thật.”** Mô phỏng lành tính và bằng chứng có kiểm soát có thể đủ để kiểm tra telemetry; mức fidelity phải ghi rõ.
9. **“Tìm thấy một CVE quan trọng là đủ để đánh giá toàn bộ năng lực SOC.”** CVE ảnh hưởng đến quản lý lỗ hổng; năng lực SOC còn gồm log, correlation, playbook, phối hợp và containment.
10. **“Chỉ cần test ở firewall biên.”** VPN, east–west, Wi-Fi guest, DNS, mạng quản trị và cloud có thể tạo đường đi khác; chọn scope theo threat model.

## 13. Mẫu đầu ra cho từng engagement

### 13.1. Penetration test finding

~~~text
Finding ID: PT-NET-014
Tên: Ngoại lệ firewall giữa VPN-USER và DATA quá rộng
Phạm vi: Firewall F-01, rule P-120, subnet và host được phép kiểm thử
Mô tả: Kết nối từ host thử ngoài danh sách hợp lệ đi qua policy
Bằng chứng: timestamp, source/destination, rule hit, log và test ID
Điều kiện và ảnh hưởng: quyền truy cập không đúng baseline
Giới hạn: chưa đánh giá dữ liệu thật hoặc các subnet ngoài scope
Khuyến nghị: thu hẹp rule, xác minh owner và expiry
Chủ khắc phục: Network Security
Retest: pending / pass / fail, kèm bằng chứng
~~~

### 13.2. Red team objective report

~~~text
Scenario ID: RT-NET-006
Mục tiêu: kiểm chứng phân đoạn và phát hiện trên đường VPN -> DATA
Giả định ban đầu: quyền VPN thử nghiệm được white cell cấp
Phạm vi: tài khoản, host, IP và time window theo ROE
TTP/phương thức: chuỗi hành vi lành tính được phê duyệt
Timeline: hành vi mô phỏng, dấu vết log, sự kiện SOC và phản ứng
Objective: blocked / achieved in simulation / not attempted
Control findings: policy enforcement, detection, triage, response
Hạn chế: bước nào được mô phỏng; dữ liệu nào không dùng
Khuyến nghị: cải tiến policy, giám sát và playbook
Revalidation owner và deadline: [...]
~~~

### 13.3. Purple team detection report

~~~text
Test case: PUR-NET-022
Hành vi: nguồn VPN test gửi kết nối tới zone không được phép
Expected telemetry: VPN log + firewall deny + asset context
Expected detection: case SOC với user/host/zone/policy chính xác
Before: event có nhưng thiếu asset mapping; không có alert
Change: bổ sung enrichment và correlation rule đã review
After: alert đúng; analyst xác minh trong ngưỡng đã phê duyệt
Side effects: kiểm tra false positive và hiệu năng pipeline
Regression schedule: sau thay đổi firewall/VPN/SIEM liên quan
Evidence: test ID, log query, rule version, case ID
~~~

Ba mẫu đều cần **bảo mật dữ liệu, giới hạn phân phối, xác nhận của chủ tài sản và người chịu trách nhiệm tiếp theo**. Bằng chứng thử nghiệm không nên chứa mật khẩu thật, token còn hiệu lực hoặc dữ liệu khách hàng vượt phạm vi được phép.

## 14. Câu hỏi tự kiểm tra và bài tập ứng dụng

### 14.1. Câu hỏi

1. Điểm khác biệt cốt lõi giữa mục tiêu của penetration test và red team là gì?
2. Vì sao red team có thể dùng một **assumed breach** mà vẫn kiểm chứng được giá trị phòng thủ?
3. Một firewall chặn kết nối trái phép nhưng SOC không tạo alert. Pentest, red team và purple team sẽ nhìn nhận kết quả này thế nào?
4. Trường hợp nào **purple team** phù hợp hơn một engagement bí mật kéo dài?
5. Tại sao kết quả “không có alert” không thể tự chứng minh red team đã vượt qua mọi lớp phòng vệ?
6. ROE cần nêu những giới hạn nào khi mô phỏng lưu lượng qua VPN, firewall và cloud gateway?
7. Nêu ít nhất ba chỉ số có ý nghĩa cho purple team và cách tránh báo cáo kết quả sai.
8. Một tổ chức thiếu inventory và mất nhiều firewall logs nên chuẩn bị những gì trước khi chạy red team quy mô lớn?

### 14.2. Bài tập nhỏ

Giả sử bạn phụ trách môi trường gồm VLAN USER, VLAN APP, VLAN DATA; VPN chỉ dành cho nhân viên; IDS/IPS giám sát traffic giữa USER và APP; log tập trung về SIEM. Hãy tạo:

1. **Hai test case pentest** kiểm chứng ACL/firewall và quyền quản trị thiết bị.
2. **Một mục tiêu red team** gắn với một tài sản nghiệp vụ và kịch bản giả lập an toàn.
3. **Một vòng purple team** gồm sự kiện kích hoạt, nguồn log phải xuất hiện, điều kiện tạo alert và tiêu chí retest.
4. **Một ROE ngắn** xác định host thử, tài khoản, giờ chạy, hệ thống cấm chạm, dữ liệu giả và phương án dừng.

Đáp án mẫu ở mức định hướng: pentest kiểm tra USER không thể tới DATA trên cổng ngoài chính sách và management interface không reachable từ USER; red team kiểm chứng SOC có phát hiện khi tài khoản VPN test thực hiện chuỗi truy cập không đúng phân đoạn; purple team mô phỏng kết nối bị chặn → xác minh firewall log được ingest → tạo case có nguồn/đích/zone → điều chỉnh nếu thiếu → chạy lại; ROE giới hạn vào host/cổng thử, chỉ dùng tài khoản và dữ liệu giả, có white cell và lệnh dừng khẩn.

**Ghi nhớ:** **Penetration test** giúp xác nhận *điểm yếu cụ thể*; **red team** đánh giá *khả năng bảo vệ, phát hiện và phản ứng trước một mục tiêu đối thủ mô phỏng*; **purple team** giúp *biến các hành vi mô phỏng thành cải tiến phòng thủ đã kiểm chứng*. Ba phương pháp bổ trợ cho nhau; giá trị thực nằm ở phạm vi rõ, thử nghiệm có kiểm soát, bằng chứng truy vết và thay đổi được kiểm tra lại.

# RTO (Recovery Time Objective): mục tiêu thời gian khôi phục dịch vụ

**RTO (Recovery Time Objective)** là khoảng thời gian gián đoạn tối đa mà tổ chức **đặt mục tiêu** để khôi phục một dịch vụ, quy trình nghiệp vụ hoặc năng lực vận hành về **mức hoạt động tối thiểu đã được chấp nhận** sau sự cố. RTO là mục tiêu phục hồi có chủ sở hữu và điều kiện nghiệm thu; nó không phải cam kết rằng mọi sự cố đều được khôi phục đúng hạn.

Trong **Business Continuity** (duy trì hoạt động kinh doanh), RTO trả lời câu hỏi: *“Nếu chức năng này ngừng phục vụ, chúng ta cần phục hồi đủ để kinh doanh tiếp tục trong bao lâu?”* Với **Security Assurance**, câu trả lời còn phải được chứng minh: mục tiêu có nguồn gốc từ đánh giá tác động, phương án phục hồi có khả năng đáp ứng, kết quả diễn tập được đo bằng bằng chứng có thể kiểm tra, và dịch vụ chỉ được bàn giao khi đáp ứng các điều kiện an toàn.

Sau bài học, người học có thể:

- Phân biệt RTO với RPO, MTPD/MAO, WRT, MTTR và SLA/SLO.
- Xây dựng RTO từ Business Impact Analysis (BIA), yêu cầu nghiệp vụ và phụ thuộc kỹ thuật.
- Phân bổ ngân sách thời gian phục hồi, thiết kế quy trình khôi phục có kiểm soát bảo mật.
- Đo RTO thực tế bằng mốc thời gian và điều kiện nghiệm thu, tổ chức diễn tập và lưu bằng chứng assurance.

## 1. Định nghĩa RTO có thể đo lường

Một cách diễn đạt thực dụng:

> **RTO = thời gian tối đa cho phép từ lúc phát sinh gián đoạn nghiệp vụ đến lúc năng lực phục vụ tối thiểu được khôi phục và chấp nhận theo tiêu chí đã phê duyệt.**

Ví dụ, một hệ thống đặt hàng có RTO **4 giờ**. Dịch vụ bị gián đoạn lúc **09:00** thì mốc khôi phục mục tiêu là **13:00**. Nếu kỹ sư khởi động được máy chủ lúc 11:30 nhưng khách hàng chưa thể tạo đơn, hệ thống **chưa đạt trạng thái phục hồi**. Nếu lúc 12:40 các luồng đặt hàng, thanh toán, kiểm soát truy cập và kiểm tra tính toàn vẹn đều đạt tiêu chí đã định, thời gian phục hồi đo được là **3 giờ 40 phút**.

Cần xác lập hai mốc trước khi sự cố xảy ra:

| Mốc | Cách xác định | Sai lầm thường gặp |
|---|---|---|
| **Bắt đầu** (T0) | Thời điểm gián đoạn bắt đầu gây tác động lên chức năng nghiệp vụ thuộc phạm vi RTO | Lấy lúc đội vận hành nhận cảnh báo hoặc tuyên bố sự cố; có thể bỏ sót thời gian phát hiện |
| **Kết thúc** (T1) | Thời điểm chức năng đạt **toàn bộ tiêu chí phục hồi tối thiểu**, được xác nhận theo quy trình | Lấy lúc VM/pod “Running”, database trả lời ping hoặc DNS vừa được đổi |
| **Thời gian quan sát** | T1 − T0 | Trừ bớt thời gian chờ quyết định, điều tra hoặc xác nhận bảo mật |
| **Đạt mục tiêu** | T1 − T0 ≤ RTO đã phê duyệt **và** các điều kiện nghiệm thu đạt | Chỉ kiểm tra thời gian, bỏ qua khả năng xử lý nghiệp vụ và rủi ro dữ liệu |

Cách định nghĩa trên phải được thống nhất bằng văn bản cho từng phạm vi dịch vụ. Một hệ thống có thể được coi là khôi phục ở chế độ giảm công suất, chẳng hạn **60% lưu lượng với các nghiệp vụ cốt lõi**, nếu mức đó được bộ phận nghiệp vụ phê duyệt **trước** khi sự cố diễn ra. Việc tự hạ tiêu chuẩn sau sự cố không tự động biến kết quả thành “đạt RTO”.

RTO có thể áp dụng ở nhiều lớp: quy trình kinh doanh (*tiếp nhận đơn hàng*), sản phẩm (*checkout*), dịch vụ kỹ thuật (*payment API*), hoặc thành phần hạ tầng. Khi các lớp có mục tiêu riêng, phải xác định rõ **đối tượng**, **ranh giới phụ thuộc**, **điểm bắt đầu/kết thúc**, **người nghiệm thu** để tránh nhầm lẫn.

## 2. Phân biệt RTO với các chỉ tiêu liên quan

| Khái niệm | Câu hỏi mà chỉ tiêu trả lời | Ví dụ minh họa |
|---|---|---|
| **RTO — Recovery Time Objective** | Cần phục hồi chức năng trong bao lâu? | Checkout: 4 giờ |
| **RPO — Recovery Point Objective** | Chấp nhận mất tối đa bao nhiêu dữ liệu theo chiều thời gian? | Checkout: 15 phút dữ liệu |
| **MTPD — Maximum Tolerable Period of Disruption** / **MAO — Maximum Acceptable Outage** | Gián đoạn tối đa mà nghiệp vụ còn có thể chịu đựng trước khi tác động trở nên không thể chấp nhận? | Quy trình xử lý đơn: 6 giờ |
| **WRT — Work Recovery Time** | Sau khi hệ thống kỹ thuật được phục hồi, cần thêm bao lâu để nghiệp vụ đối soát, xử lý tồn đọng và hoạt động ổn định? | 1 giờ để xử lý hàng đợi |
| **MTTR — Mean Time to Repair/Recover** | Thời gian khắc phục/khôi phục **trung bình đo được** trong một tập sự cố theo định nghĩa của đội vận hành là bao nhiêu? | Trung bình 2 giờ qua 12 sự cố |
| **SLA/SLO về availability** | Dịch vụ cần duy trì mức sẵn sàng nào trong kỳ đo và theo hợp đồng/mục tiêu vận hành? | SLO 99,9% theo tháng |

**RTO và RPO độc lập về ý nghĩa.** Phục hồi sau 2 giờ có thể đạt RTO 4 giờ, nhưng nếu chỉ khôi phục được dữ liệu cũ hơn 1 giờ thì không đạt RPO 15 phút. Ngược lại, giữ nguyên dữ liệu nhờ replication không bảo đảm hệ thống sẽ sẵn sàng trong 4 giờ.

**MTPD/MAO là giới hạn chịu đựng của nghiệp vụ; RTO là mục tiêu để tránh chạm giới hạn đó.** Tùy phương pháp BIA và phạm vi đo, doanh nghiệp còn cần dự trù thời gian xác minh, xử lý công việc tồn đọng (WRT), sai số và tình huống bất lợi. Không nên tự động đặt RTO bằng MTPD.

**MTTR là chỉ số mô tả lịch sử, còn RTO là yêu cầu thiết kế.** Trung bình 2 giờ không chứng minh mỗi sự cố đều đạt RTO 4 giờ: một số lần có thể vượt xa giới hạn. Cần xem thời gian ở các kịch bản xấu, độ phân tán, phân vị và những lần không đạt.

**SLA/SLO không thay thế RTO.** Một cam kết uptime theo tháng không tự chỉ ra tổ chức phải phục hồi một đợt gián đoạn cụ thể trong bao lâu. RTO cần được liên kết với mục tiêu availability nhưng có cách đo riêng.

## 3. Xác định “phục hồi” theo nghiệp vụ và bảo mật

Để RTO có thể kiểm chứng, hãy viết **định nghĩa trạng thái phục hồi tối thiểu** (minimum acceptable operating level, MAOL) cho dịch vụ. Với hệ thống giao dịch, ví dụ minh họa:

1. Người dùng hợp lệ có thể đăng nhập, xem giỏ hàng và tạo đơn qua tuyến truy cập phục hồi.
2. Các yêu cầu mua hàng tạo ra kết quả đúng; không sinh trùng đơn hoặc mất trạng thái giao dịch.
3. Chế độ xử lý đạt ít nhất 60% công suất giờ cao điểm đã định; các kiểm tra sức khỏe và độ trễ thỏa tiêu chí theo cửa sổ đo.
4. Các control tối thiểu như xác thực, phân quyền, mã hóa kết nối, quản lý khóa/bí mật và ghi log bảo mật vẫn hoạt động.
5. Nguồn dữ liệu được xác minh **tính toàn vẹn**, độ mới theo RPO và trạng thái đồng bộ/đối soát; không sử dụng điểm khôi phục còn dấu hiệu bị xâm nhập.
6. Người có thẩm quyền nghiệp vụ và kỹ thuật xác nhận bằng chứng, ghi mốc T1 và công bố trạng thái đã phục hồi.

Ví dụ tiêu chí đo có thể là “tỷ lệ thành công của giao dịch thử ≥ 99% và độ trễ p95 ≤ 800 ms trong 15 phút liên tục”, nhưng các con số này **chỉ là giả định để học**, phải xác định lại theo đặc điểm tải và quy trình thực tế. Nếu cần 15 phút quan sát để nghiệm thu, **T1 nằm ở cuối khoảng quan sát thành công**, không phải đầu khoảng đó.

Trạng thái **degraded but usable** chỉ được tính là phục hồi nếu đã có tiêu chuẩn, phạm vi chức năng và người phê duyệt rõ ràng. Một API trả HTTP 200 nhưng ghi sai dữ liệu hoặc bỏ qua xác thực không thể coi là dịch vụ đã được khôi phục an toàn.

## 4. Xây dựng RTO từ Business Impact Analysis (BIA)

Không nên khởi đầu bằng việc hỏi “đội kỹ thuật có thể dựng lại server nhanh đến đâu?”. RTO xuất phát từ **mức tổn thất mà nghiệp vụ có thể chấp nhận**, sau đó đội kỹ thuật phải đánh giá khoảng cách giữa mục tiêu và năng lực phục hồi thực tế.

Quy trình xây dựng:

1. **Khoanh vùng chức năng quan trọng.** Liệt kê hành trình người dùng, quy trình nghiệp vụ, dữ liệu trọng yếu, thời gian cao điểm, phạm vi khách hàng và các nghĩa vụ phải duy trì.
2. **Phân tích tác động theo thời gian.** Với từng chức năng, đánh giá tổn thất doanh thu, hợp đồng, uy tín, vận hành, an toàn, tuân thủ và khả năng xử lý tồn đọng ở các mốc như 15 phút, 1 giờ, 4 giờ, 24 giờ.
3. **Xác định mức gián đoạn chịu được.** BIA nêu giới hạn MTPD/MAO và lý do có thể kiểm toán; có thể phải phân biệt mùa cao điểm với giai đoạn thông thường.
4. **Chọn RTO có khoảng đệm.** Tính đến thời gian khôi phục nghiệp vụ, chấp nhận rủi ro, khả năng huy động nhân sự và điều kiện an toàn.
5. **Lập bản đồ phụ thuộc.** Kiểm tra identity provider, DNS, mạng, cơ sở dữ liệu, backup, KMS/HSM, chứng chỉ, secret store, nhà cung cấp, observability, con người và quyền truy cập khẩn cấp.
6. **Đánh giá tính khả thi và chi phí.** So sánh RTO mong muốn với năng lực thực tế của cold/warm/hot standby, phương án thủ công, failover và rollback; nếu không đạt cần đầu tư, giảm yêu cầu có phê duyệt hoặc chấp nhận rủi ro chính thức.
7. **Phê duyệt, lưu phiên bản và đánh giá lại.** Business owner chịu trách nhiệm về mức chịu đựng; technology/security owner cam kết phương án và bằng chứng. RTO cần được rà soát sau thay đổi kiến trúc hoặc nghiệp vụ.

Ví dụ phân loại **giả định**, không phải khuyến nghị chung:

| Chức năng nghiệp vụ | RTO mục tiêu | RPO mục tiêu | Lý do cần xem xét |
|---|---:|---:|---|
| Xác nhận đơn hàng trực tuyến | 4 giờ | 15 phút | Dừng doanh thu, phát sinh đơn chưa hoàn tất |
| Đối soát thanh toán cuối ngày | 24 giờ | 1 giờ | Có thể hoãn trong thời gian ngắn nhưng không được sai số liệu |
| Phân tích hành vi nội bộ | 72 giờ | 24 giờ | Tác động tức thời thấp hơn, có thể tái xử lý dữ liệu |

Một RTO quá ngắn có thể đòi hỏi nhiều vùng triển khai, duy trì công suất dự phòng, đường khôi phục độc lập và đội phản ứng trực 24/7. Một RTO quá dài có thể khiến thiệt hại vượt ngưỡng chấp nhận. Vì thế quyết định phải có **chủ sở hữu, lý do và bằng chứng thử nghiệm**, không đơn thuần lấy một con số “chuẩn ngành”.

## 5. Phân rã ngân sách RTO và đường găng khôi phục

RTO là ngân sách **end-to-end**, bao gồm cả thời gian chưa có hành động sửa chữa. Một cách phân tích:

```text
T_quan_sát =
  T_phát_hiện
+ T_đánh_giá_và_quyết_định
+ T_cô_lập_nếu_cần
+ T_phục_hồi_kỹ_thuật
+ T_xác_minh_an_toàn_và_nghiệp_vụ
+ T_bàn_giao
```

Các bước có thể chạy song song, vì vậy trên hệ thống thực tế **không luôn cộng cơ học mọi tác vụ**. Hãy dùng timeline và sơ đồ phụ thuộc để tính đường găng; tổng trên chỉ minh họa cho chuỗi công việc nối tiếp.

Ví dụ RTO 4 giờ (240 phút), ngân sách giả định:

| Hoạt động tuần tự | Ngân sách | Mốc tính từ 09:00 |
|---|---:|---:|
| Phát hiện và phân loại gián đoạn | 15 phút | 09:15 |
| Kích hoạt quy trình và quyết định phương án | 10 phút | 09:25 |
| Cô lập phạm vi và xác định đường phục hồi an toàn | 45 phút | 10:10 |
| Chuyển vùng/khôi phục hạ tầng, dữ liệu và dịch vụ | 85 phút | 11:35 |
| Kiểm tra an toàn, chức năng, dữ liệu và tải tối thiểu | 45 phút | 12:20 |
| Nghiệm thu, bàn giao và thông tin trạng thái | 20 phút | 12:40 |
| **Dự phòng biến động** | **20 phút** | **Hạn RTO: 13:00** |

20 phút dự phòng giúp hấp thụ bất định; đó **không phải** khoảng thời gian được phép bỏ qua nếu các bước trước chậm. Nếu failover mất thêm 30 phút, ngân sách đã vượt 10 phút, trừ khi các bước khác rút ngắn mà vẫn giữ nguyên chất lượng kiểm soát.

```mermaid
flowchart LR
    A["T0: Bắt đầu gián đoạn"] --> B["Phát hiện & phân loại"]
    B --> C["Quyết định kích hoạt BC/DR"]
    C --> D["Cô lập nguy cơ"]
    D --> E["Phục hồi dữ liệu & dịch vụ"]
    E --> F["Xác minh nghiệp vụ + bảo mật"]
    F --> G["Chấp nhận trạng thái khôi phục"]
    G --> H["T1: Ghi nhận thời gian thực tế"]
```

**Đường găng phụ thuộc:** Checkout chỉ phục hồi được khi dịch vụ nhận diện, kho khóa, database và cổng kết nối thanh toán đạt mức tối thiểu. Những thành phần nào có thể khôi phục song song thì lên lịch song song; thành phần nào cần kết quả của bước trước thì nằm trên đường găng. Nếu KMS chưa cấp khóa cho database, việc khởi động được ứng dụng cũng chưa giúp chức năng checkout hoạt động.

Có thể quản lý thêm **RTO nội bộ theo thành phần** (ví dụ IdP ≤ 60 phút, database ≤ 120 phút), nhưng các chỉ tiêu con phải được kiểm tra trong quan hệ phụ thuộc. Đạt từng RTO con một cách độc lập **không chứng minh** RTO của hành trình nghiệp vụ đầu cuối đã đạt.

## 6. Thiết kế phương án kỹ thuật phù hợp với RTO

| Phương án | Đặc điểm chính | Rủi ro/câu hỏi cần kiểm chứng |
|---|---|---|
| **Cold recovery** | Dựng lại tài nguyên và phục hồi backup sau sự cố | Thời gian cấp hạ tầng, restore, cấu hình, kiểm thử, khả năng truy cập backup |
| **Warm standby** | Có môi trường dự phòng chạy một phần, cần scale và chuyển lưu lượng | Dữ liệu cập nhật tới đâu, thiếu cấu hình/secrets nào, failover mất bao lâu |
| **Hot standby / active-passive** | Hạ tầng dự phòng gần sẵn sàng, dữ liệu được đồng bộ | Cơ chế chuyển vùng, lỗi chung, split-brain, tính toàn vẹn dữ liệu |
| **Active-active** | Nhiều vùng xử lý lưu lượng đồng thời | Tính nhất quán giao dịch, cơ chế phân vùng, lỗi đồng thời, phạm vi ảnh hưởng |
| **Vận hành thủ công tạm thời** | Duy trì nghiệp vụ thiết yếu bằng quy trình ngoài hệ thống | Khối lượng chịu tải, kiểm soát gian lận, dữ liệu nhập lại, phê duyệt và đối soát |

Không có phương án nào tự động bảo đảm một con số RTO. Thời gian thực tế phụ thuộc vào lượng dữ liệu, mức tự động hóa, nhân sự, trạng thái nhà cung cấp, điều kiện kiểm soát truy cập và diễn biến sự cố.

Đối với security assurance, cần kiểm tra cả **đường khôi phục**:

- Backup, khóa giải mã, bản cấu hình và container image có còn truy cập được khi tài khoản cloud hoặc identity chính bị khóa/chiếm quyền?
- Môi trường dự phòng có dùng cùng credential, pipeline, DNS, mạng quản trị hoặc vùng tin cậy với môi trường bị xâm nhập?
- Replication có đồng thời sao chép dữ liệu bị mã hóa, xóa hoặc sửa trái phép? Có điểm khôi phục sạch và cách xác minh không?
- Quyền *break-glass* có được kiểm soát, ghi nhận, kiểm tra định kỳ và thu hồi sau khi xử lý?
- Log, audit trail và bằng chứng pháp chứng có được bảo toàn khi phục hồi hay tự động cleanup sẽ phá hủy bằng chứng?
- Khóa mã hóa, chứng chỉ, secrets, chính sách IAM và các control về mạng có được khôi phục đúng phiên bản, không dùng lại yếu tố đã lộ?
- Phương án có xử lý được lỗi chung của một nhà cung cấp hoặc mất quyền vào control plane không?

Việc đáp ứng RTO bằng cách tắt xác thực, bỏ logging, dùng bản backup chưa xác minh hoặc mở mạng quá mức có thể tạo ra rủi ro nghiêm trọng hơn sự cố ban đầu. Các tình huống ngoại lệ phải đi qua cơ chế phê duyệt rủi ro được định trước.

## 7. RTO khi sự cố là tấn công mạng

Với lỗi hạ tầng thông thường, khởi động instance dự phòng có thể đủ để tiếp tục thử nghiệm. Với ransomware, phá hoại dữ liệu hoặc lạm dụng tài khoản đặc quyền, **“chạy lại được” chưa có nghĩa “an toàn để chạy lại”**.

Luồng khôi phục cần phối hợp **Incident Response (IR)** với **Business Continuity/Disaster Recovery (BC/DR)**:

1. **Xác nhận tác động và lưu T0.** Ghi hệ thống, chức năng, nhóm khách hàng, mức gián đoạn và độ tin cậy của mốc thời gian.
2. **Kích hoạt điều phối.** Chỉ định incident commander, người ra quyết định BC/DR, chủ sở hữu nghiệp vụ, phụ trách bảo mật và người nghiệm thu.
3. **Ngăn nguy cơ lan rộng.** Phân vùng, vô hiệu hóa thông tin xác thực nghi bị lộ, ngăn tác nhân tiếp tục truy cập khi phù hợp; gìn giữ log và chứng cứ.
4. **Lựa chọn nguồn phục hồi đáng tin cậy.** Xác minh image, cấu hình, khóa, backup, dấu hiệu xâm nhập, độ mới và tính toàn vẹn. Nếu điểm sạch cũ hơn RPO, ghi nhận xung đột mục tiêu và trình quyết định.
5. **Phục hồi có kiểm soát.** Dựng môi trường và dữ liệu qua đường quản trị tin cậy, kiểm tra quyền, mạng, chính sách và service-to-service authentication.
6. **Xác minh hoạt động và an toàn.** Chạy canary giao dịch, đối soát dữ liệu, kiểm tra telemetry và sự vắng mặt của tín hiệu tấn công còn hoạt động theo phạm vi kiểm tra đã xác định.
7. **Nghiệm thu, ghi T1 và giám sát tăng cường.** Người được ủy quyền ký nhận; tiếp tục điều tra, giám sát và xử lý công việc tồn đọng.

Nếu phục hồi an toàn khiến RTO không đạt, cần **ghi đúng kết quả không đạt** và quyết định ứng phó dựa trên rủi ro. Không làm sai mốc T0, chuyển T1 thành lúc máy chủ khởi động, hoặc coi dịch vụ an toàn khi chưa có bằng chứng chỉ để báo cáo “đạt RTO”.

Một trường hợp đáng chú ý là khôi phục từ backup: **RTO** tính thời gian lấy hệ thống trở lại hoạt động, **RPO** tính lượng dữ liệu cần tái tạo hoặc mất theo thời gian. Backup sạch cách thời điểm gián đoạn 90 phút có thể khôi phục nhanh trong RTO 4 giờ nhưng vẫn không thỏa RPO 15 phút. Đó là hai kết quả khác nhau cần báo cáo riêng.

## 8. Đo RTO bằng dữ liệu và bằng chứng kiểm toán được

Để so sánh kết quả giữa các sự cố và diễn tập, tổ chức cần một **quy tắc đo** có phiên bản, không phụ thuộc vào cảm nhận của người trực ca.

**Công thức cơ bản:**

```text
Recovery_Duration = T1_accepted - T0_impact

RTO_Time_Result =
    PASS nếu Recovery_Duration <= Approved_RTO
    FAIL nếu Recovery_Duration >  Approved_RTO

Recovery_Overall_Result =
    PASS chỉ khi RTO_Time_Result = PASS
    và tất cả tiêu chí phục hồi bắt buộc đều PASS.
```

Trước khi đo, cần chỉ ra timezone (tốt nhất thu thập timestamp UTC), đồng bộ thời gian, nguồn log và quy tắc xử lý khi có nhiều hệ thống cùng ảnh hưởng. Nếu **chỉ biết T0 nằm trong khoảng 09:00–09:05**, hãy ghi khoảng không chắc chắn; khi đánh giá bảo thủ có thể dùng mốc sớm nhất 09:00. Không lấy mốc phát hiện 09:05 làm mốc gián đoạn nếu biết tác động bắt đầu sớm hơn.

**Bộ bằng chứng tối thiểu:**

| Bằng chứng | Nguồn có thể dùng | Chứng minh |
|---|---|---|
| BIA và bản phê duyệt RTO | Tài liệu có owner, ngày, phiên bản | Vì sao mục tiêu được chọn, phạm vi phục hồi |
| T0 và phạm vi ảnh hưởng | Synthetic monitoring, error rate, giao dịch lỗi, sự kiện nghiệp vụ | Lúc nào nghiệp vụ thực sự bị ảnh hưởng |
| Các mốc quyết định | Incident timeline, ticket, chat log công việc, phê duyệt | Độ trễ phát hiện, huy động, chuyển phương án |
| Thao tác phục hồi | Log pipeline/automation, restore job, failover event, thay đổi DNS | Quy trình đã thực hiện và thời gian thực tế |
| Kiểm tra dữ liệu và bảo mật | Kết quả checksum/đối soát, kiểm tra IAM, audit log, vulnerability/IOC check phù hợp | Điều kiện an toàn và toàn vẹn của trạng thái phục hồi |
| Chứng cứ nghiệp vụ | Test giao dịch, dashboard mức phục vụ, canary, xác nhận business owner | Tiêu chí cuối cùng đã đạt tại T1 |
| RTO/RPO và sai lệch | Báo cáo diễn tập/sự cố, action items | Đã đạt hay chưa, nguyên nhân, người chịu trách nhiệm khắc phục |

Một bản ghi có cấu trúc có thể trông như sau (dữ liệu **minh họa**, mọi link bằng chứng phải trỏ tới hiện vật thật):

```yaml
exercise_id: BC-EXAMPLE-009
service: checkout
scenario: primary-region-unavailable
scope: place-order-and-payment
rto_target_minutes: 240
rpo_target_minutes: 15
impact_start_utc: "2026-09-15T02:00:00Z"
accepted_recovery_utc: "2026-09-15T05:40:00Z"
observed_recovery_minutes: 220
recovery_mode: approved-degraded-mode
acceptance:
  core_transactions: PASS
  data_integrity: PASS
  security_controls: PASS
  business_owner_signoff: PASS
rto_result: PASS
rpo_result: PASS # Phải có phép đo độ mới dữ liệu riêng
evidence:
  - "monitoring/impact-window"
  - "recovery/run-logs"
  - "validation/transaction-tests"
  - "validation/integrity-and-security"
  - "approvals/business-owner"
```

Cần bảo đảm các timestamp trong bằng chứng có thể đối chiếu và không bị sửa sau sự kiện mà không có dấu vết. Kho bằng chứng nên phân quyền, quản lý phiên bản, có chính sách lưu giữ và liên kết đến ticket/action item. **Việc có YAML hoặc báo cáo “PASS” tự nó không chứng minh đạt RTO**; bằng chứng gốc và cách đo phải kiểm tra lại được.

## 9. Kiểm thử khả năng đạt RTO

Một RTO chưa được thử là một **giả thuyết về năng lực phục hồi**. Lập kế hoạch diễn tập theo mức độ rủi ro, độ phức tạp, thay đổi kiến trúc và giá trị nghiệp vụ. Diễn tập cần mô phỏng đủ các nút thắt của đường phục hồi, trong đó có phụ thuộc, dữ liệu, con người và bước nghiệm thu.

| Kiểu kiểm thử | Giá trị | Giới hạn cần ghi rõ |
|---|---|---|
| **Tabletop** | Xác minh vai trò, quyền quyết định, danh sách phụ thuộc, quy trình truyền thông | Không đo được thời gian restore thật |
| **Restore drill** | Đo truy cập backup, khôi phục dữ liệu, checksum, cấu hình | Chưa chứng minh toàn bộ dịch vụ đã phục hồi |
| **Failover drill** | Đo chuyển vùng, routing, DNS, các dependency và kết nối | Có thể bỏ sót kiểm tra nghiệp vụ hoặc dữ liệu sau chuyển |
| **End-to-end recovery exercise** | Đo từ T0 tới T1 có tiêu chí nghiệp vụ và bảo mật | Độ tin cậy phụ thuộc độ giống production của tải, dữ liệu và kịch bản |
| **Cyber recovery exercise** | Thử khôi phục khi nguồn chính không đáng tin, credential bị thu hồi, backup cần kiểm tra sạch | Cần bảo vệ môi trường diễn tập và xác định rõ giới hạn mô phỏng |

Để bài kiểm thử có giá trị assurance:

- Chọn kịch bản cụ thể (mất vùng, hỏng database, ransomware, mất control plane), tập hợp dịch vụ liên quan và phạm vi tác động.
- Đặt **T0 giả lập** rõ ràng; ghi nhận đồng hồ bắt đầu, bao gồm cả thời gian phát hiện nếu mục tiêu đo từ lúc gián đoạn.
- Chạy runbook theo đúng quyền, trách nhiệm, phê duyệt và mức tự động hóa dự kiến ở production.
- Đo từng bước cùng đường găng. Tạo đủ tải và dữ liệu để phát hiện thời gian restore tăng theo dung lượng.
- Buộc diễn tập đi đến **nghiệm thu đầy đủ**, không dừng tại “environment healthy”.
- Lưu kết quả theo mục tiêu, riêng **PASS/FAIL của thời gian**, **PASS/FAIL của RPO**, **PASS/FAIL của tiêu chí bảo mật/nghiệp vụ**.
- Ghi các giả định, trở ngại, hành động khắc phục, hạn hoàn thành và lịch **retest** sau thay đổi.

Ví dụ, nếu restore database mẫu chỉ 2 GB trong khi production có 2 TB, phải ghi rằng phép thử **không chứng minh** thời gian restore thực tế ở quy mô sản xuất. Tương tự, một failover bằng tay có nhiều quản trị viên hiện diện trong diễn tập chưa chứng minh khả năng đạt RTO vào đêm nghỉ khi nhân sự ít hơn.

### Mẫu điều kiện chấp nhận một lần diễn tập

```text
Scenario: Mất vùng chính của checkout
Target: RTO <= 240 phút, RPO <= 15 phút
T0: giao dịch checkout đầu tiên thất bại do sự cố giả lập

PASS khi:
  [ ] Kịch bản, phạm vi và T0 được ghi với bằng chứng
  [ ] Các luồng nghiệp vụ bắt buộc đạt mức phục hồi đã phê duyệt
  [ ] AuthN/AuthZ, network policy, keys, TLS, audit logs hoạt động
  [ ] Dữ liệu giao dịch được đối soát và đo được RPO
  [ ] Business owner/incident commander xác nhận T1
  [ ] T1 - T0 <= 240 phút
  [ ] Báo cáo chứa raw evidence và action items

Bất kỳ mục bắt buộc nào không đạt -> ghi FAIL/NOT DEMONSTRATED
theo quy tắc báo cáo đã thống nhất.
```

Các checkbox là ví dụ về cổng nghiệm thu; đối với một đơn vị cụ thể cần bổ sung quy trình ký nhận, tiêu chí được áp dụng và mức bằng chứng tương ứng với rủi ro.

## 10. Tình huống hoàn chỉnh: khôi phục checkout sau mất vùng

**Giả định nghiệp vụ:** BIA phê duyệt RTO 4 giờ, RPO 15 phút cho chức năng tạo đơn và thanh toán; chế độ giảm công suất 60% được phép nếu vẫn giữ đủ control và ghi nhận giao dịch đúng. MTPD của chức năng là 6 giờ và tổ chức còn dự trù thời gian xử lý backlog ngoài mốc nghiệm thu kỹ thuật.

**Giả định kiến trúc:** Ứng dụng có warm standby ở vùng thứ hai; database có bản sao hoặc backup; hệ thống còn phụ thuộc vào IdP, DNS, key service và gateway thanh toán. Kịch bản thử: vùng chính mất khả dụng hoàn toàn, không có bằng chứng bị xâm nhập.

**Timeline diễn tập:**

| Thời điểm | Sự kiện | Ý nghĩa kiểm chứng |
|---|---|---|
| 09:00 | Giao dịch checkout bắt đầu lỗi diện rộng | **T0**, bắt đầu đo |
| 09:15 | Đội trực phát hiện, phân loại phạm vi | Kiểm tra độ trễ phát hiện |
| 09:25 | Incident commander kích hoạt kế hoạch | Quyết định và ủy quyền |
| 10:10 | Hoàn tất đánh giá an toàn, xác định trạng thái dự phòng | Điều kiện trước failover |
| 11:35 | Chuyển tuyến xong, ứng dụng và DB phản hồi | **Chưa phải T1**; cần kiểm tra nghiệp vụ |
| 12:20 | Kết quả kiểm tra chức năng, RPO, toàn vẹn và control đạt | Chuẩn bị nghiệm thu |
| 12:40 | Cửa sổ quan sát và phê duyệt kết thúc | **T1**, đủ điều kiện phục hồi |
| 13:00 | Hạn RTO đã phê duyệt | Mốc so sánh |

**Kết quả thời gian:** 12:40 − 09:00 = **220 phút**, nhỏ hơn 240 phút, có **20 phút dư địa**. Nếu các kiểm tra RPO và điều kiện bảo mật/nghiệp vụ đều PASS như giả định, cuộc diễn tập **đạt RTO** theo tiêu chí đã công bố.

Tuy vậy, giả sử kiểm tra đối soát phát hiện các đơn hàng từ 09:30–10:00 không có bản ghi nhất quán. Khi đó hệ thống dù đã đáp ứng latency lúc 12:40 **không được ghi kết quả overall PASS**. Cần bổ sung điều tra, khôi phục/đối soát dữ liệu và đo lại T1 theo trạng thái chấp nhận thực tế. Trong báo cáo phải thể hiện rõ mục nào chưa đạt cùng tác động tới RTO/RPO.

Sau diễn tập, nhóm assurance có thể truy vết từ **yêu cầu BIA → RTO phê duyệt → kiến trúc dự phòng/runbook → bản ghi các mốc → nghiệm thu nghiệp vụ/bảo mật → kết luận → việc khắc phục**. Chuỗi truy vết đó làm cho tuyên bố “chúng ta khôi phục trong 4 giờ” có cơ sở kiểm chứng.

## 11. Các lỗi thường gặp khi quản trị RTO

| Lỗi | Vì sao làm sai đánh giá | Cách khắc phục |
|---|---|---|
| Đặt RTO theo khả năng restore hiện có | Có thể bỏ qua ngưỡng chịu đựng thực của doanh nghiệp | Bắt đầu từ BIA; đo khoảng cách năng lực |
| Đồng nhất RTO với RPO | Khôi phục nhanh không có nghĩa dữ liệu đủ mới | Đo thời gian và mất mát dữ liệu riêng |
| Tính từ lúc tuyên bố incident | Loại bỏ thời gian phát hiện ra khỏi thiệt hại | Đặt T0 ở lúc tác động nghiệp vụ bắt đầu |
| Tính T1 lúc hạ tầng xanh | Bỏ qua chức năng, tải, toàn vẹn và bảo mật | Dùng bộ tiêu chí nghiệm thu end-to-end |
| Chỉ đo từng dịch vụ con | Không tính dependency hoặc đường găng | Diễn tập hành trình nghiệp vụ hoàn chỉnh |
| Chỉ có RTO trên giấy | Không có chứng cứ đáp ứng khi xảy ra sự cố thật | Diễn tập theo kịch bản, lưu raw evidence |
| Thử nghiệm trên tập dữ liệu quá nhỏ | Đánh giá thấp thời gian restore, reindex, replay | Dùng tải/dữ liệu đại diện hoặc chỉ rõ giới hạn |
| Bỏ qua thời gian chờ khóa, quyền, người phê duyệt | RTO “lý tưởng” không thực hiện được trong ca trực | Diễn tập quyền break-glass, on-call và phụ thuộc |
| Cắt bớt control để kịp hạn | Dịch vụ có thể bị tấn công tiếp hoặc dữ liệu không tin cậy | Thiết kế kiểm soát phục hồi từ trước; ghi ngoại lệ có phê duyệt |
| Có FAIL nhưng không đóng action item | Năng lực không cải thiện qua các lần diễn tập | Gán owner, hạn, điều kiện đóng và retest |

## 12. Vận hành chương trình RTO liên tục

RTO cần được quản lý như một **yêu cầu có vòng đời** trong chương trình security assurance, gắn với các thay đổi nghiệp vụ và kỹ thuật.

**Khi lập kế hoạch:** mỗi dịch vụ quan trọng có business owner, RTO/RPO được phê duyệt, BIA, bản đồ phụ thuộc, phương án restore và runbook. Định nghĩa T0/T1, cổng nghiệm thu và vai trò ra quyết định được cập nhật cùng phiên bản.

**Khi triển khai:** đánh giá mỗi thay đổi có ảnh hưởng đến khả năng phục hồi hay không: mở rộng dung lượng dữ liệu, thêm dependency, đổi dịch vụ identity, chỉnh key management, chuyển region, thay đổi backup retention hoặc quy trình release. Các thay đổi có rủi ro được đưa vào kiểm thử và cập nhật runbook.

**Khi giám sát:** theo dõi tín hiệu có thể phản ánh gián đoạn nghiệp vụ (synthetic transaction, error budget, queue backlog, độ trễ giao dịch), độ sẵn sàng của môi trường dự phòng, tình trạng backup/restore, tuổi bản sao và dấu hiệu suy giảm chất lượng. Cảnh báo sớm giúp giảm thời gian phát hiện nhưng **không thay thế** diễn tập end-to-end.

**Khi kiểm chứng:** tổ chức diễn tập theo rủi ro và sau thay đổi quan trọng, đo thời gian với bằng chứng gốc, so sánh RTO/RPO, phân tích các lần vượt hạn và đưa sai lệch vào backlog khắc phục. Chủ sở hữu nghiệp vụ xem xét lại mục tiêu khi nhu cầu và mức chịu đựng thay đổi.

Nhóm assurance nên có thể trả lời bằng chứng cụ thể: **RTO này ai phê duyệt? Căn cứ BIA nào? Runbook nào được dùng? Lần thử gần nhất đo T0/T1 ra sao? Mọi phụ thuộc và control có được kiểm tra? Sai lệch đã được khắc phục và thử lại chưa?**

## 13. Tự kiểm tra kiến thức

1. Dịch vụ có RTO 2 giờ, RPO 10 phút. Hệ thống phục hồi sau 90 phút nhưng dùng bản backup cũ 45 phút. Hãy kết luận riêng về RTO, RPO và trạng thái nghiệm thu.
2. Theo timeline, nghiệp vụ gián đoạn lúc 08:00, alert lúc 08:12, incident được tuyên bố lúc 08:30, VM chạy lại lúc 09:00, giao dịch cốt lõi và kiểm tra bảo mật đạt lúc 09:40. Mốc nào là T0, T1 và thời gian phục hồi?
3. Một nhóm chỉ diễn tập failover API và đạt 30 phút; database, IdP và kiểm tra đơn hàng không nằm trong phạm vi. Bằng chứng đó có đủ kết luận RTO nghiệp vụ 1 giờ không? Vì sao?
4. Vì sao một phương án active-active vẫn có thể không đáp ứng RTO khi cả hai vùng cùng sử dụng một hệ thống cấp khóa hoặc một nhà cung cấp identity?
5. Trong tình huống ransomware, khôi phục từ backup gần nhất có thể làm lan mã độc, còn backup sạch quá cũ so với RPO. Những ai cần tham gia quyết định và phải ghi nhận những loại kết quả nào?

**Điểm cần ghi nhớ:** RTO chỉ có ý nghĩa khi chỉ rõ **phạm vi nghiệp vụ**, **định nghĩa phục hồi an toàn**, **mốc đo**, **người phê duyệt** và **bằng chứng thử nghiệm**. Một con số mục tiêu chưa được kiểm tra qua toàn bộ chuỗi phụ thuộc chưa đủ để khẳng định hệ thống có khả năng duy trì hoạt động kinh doanh khi xảy ra sự cố.

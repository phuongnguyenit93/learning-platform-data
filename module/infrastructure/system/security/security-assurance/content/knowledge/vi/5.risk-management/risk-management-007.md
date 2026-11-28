# Risk score – Chấm điểm rủi ro bảo mật có căn cứ

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **risk score** là gì, vì sao cần lượng hóa/chuẩn hóa mức ưu tiên xử lý rủi ro và giới hạn của một con số đơn lẻ.
- Nhận diện các yếu tố làm thay đổi đánh giá rủi ro: tài sản, sự kiện đe dọa, điểm yếu, khả năng xảy ra, mức tác động, phạm vi, thời gian và độ tin cậy của dữ liệu.
- Xây dựng thang **likelihood × impact** minh bạch, tính và diễn giải điểm trên ma trận 5×5 mà không coi thứ bậc 1–5 là xác suất hay tiền tệ chính xác.
- Phân biệt **rủi ro ban đầu (inherent risk)**, **rủi ro còn lại (residual risk)** và mức rủi ro mà tổ chức có thẩm quyền chấp nhận.
- Liên kết điểm rủi ro với yêu cầu, security controls, kiểm thử, audit, bằng chứng vận hành, phát hiện và khắc phục trong chương trình **security assurance liên tục**.
- Thực hiện một ví dụ thực tế về API Java/Spring Boot và trình bày bản ghi đánh giá rủi ro có thể kiểm tra lại.

## 1. Risk score là gì và phục vụ quyết định nào?

**Risk score** là giá trị được gán theo một **phương pháp đánh giá đã xác định** để biểu diễn mức rủi ro của một tình huống trong bối cảnh cụ thể. Điểm giúp các bên so sánh, sắp xếp ưu tiên, chọn biện pháp xử lý, theo dõi biến động và chuyển cấp những tình huống vượt mức chấp nhận.

Trong quản lý rủi ro bảo mật, một **risk scenario** nên nêu tối thiểu:

> **Ai/cái gì có thể gây sự kiện nào, khai thác điều kiện hoặc điểm yếu nào, tác động tới tài sản/mục tiêu nào, trong phạm vi và khoảng thời gian nào?**

Ví dụ: “Người dùng đã đăng nhập có thể thay `documentId` trong API xuất báo cáo để tải tài liệu của tenant khác, dẫn đến lộ dữ liệu khách hàng trên production.” Câu này hữu ích hơn “API có lỗ hổng IDOR”, vì nêu được **đường tấn công, điều kiện, tài sản và hậu quả**.

Trong module **SECURITY_SECURITY_ASSURANCE**, điểm rủi ro là một đầu vào quan trọng để xác định **mức assurance cần đạt**: rủi ro cao có thể cần nhiều lớp control, độ bao phủ test lớn hơn, review độc lập và bằng chứng hiệu quả vận hành mạnh hơn. Điểm cũng giúp giải thích vì sao một finding được ưu tiên sửa trước các finding khác.

Nhưng **điểm số không phải bằng chứng hệ thống an toàn**. “Risk score giảm từ 20 xuống 10” chỉ là một kết luận đánh giá; muốn đáng tin phải có bằng chứng rằng control được triển khai và thực sự hoạt động trong đúng phạm vi.

### Phân biệt thuật ngữ

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Asset / tài sản** | Thông tin, hệ thống hoặc năng lực có giá trị cần bảo vệ | Cơ sở dữ liệu đơn hàng, dịch vụ thanh toán |
| **Threat / đe dọa** | Nguồn hoặc tình huống có khả năng gây hại | Kẻ tấn công đánh cắp token, nhân sự thao tác sai |
| **Vulnerability / điểm yếu** | Điều kiện có thể bị khai thác hoặc dẫn đến thiệt hại | API thiếu kiểm tra quyền cấp đối tượng |
| **Risk scenario** | Cách đe dọa và điểm yếu tạo hậu quả cụ thể | Người dùng A đọc hồ sơ B qua ID |
| **Likelihood** | Đánh giá khả năng/khuynh hướng sự kiện gây hại xảy ra trong phạm vi và kỳ đánh giá | “Khá cao” vì endpoint công khai, dễ lạm dụng |
| **Impact** | Mức hậu quả nếu kịch bản xảy ra | Lộ thông tin khách hàng và ảnh hưởng pháp lý |
| **Risk score** | Điểm theo thang/phương pháp đã thống nhất | `4 × 5 = 20` |
| **Risk level** | Nhóm ưu tiên được suy ra theo ngưỡng có định nghĩa | Critical theo ma trận nội bộ minh họa |
| **Risk treatment** | Quyết định giảm thiểu, tránh, chuyển/chia sẻ hoặc chấp nhận rủi ro | Sửa phân quyền, ngừng endpoint, mua bảo hiểm hoặc chấp nhận có điều kiện |
| **Risk owner** | Người có trách nhiệm và thẩm quyền đối với quyết định về rủi ro | Chủ sở hữu dịch vụ/đơn vị nghiệp vụ được ủy quyền |

**Không đồng nhất severity của một lỗ hổng với điểm rủi ro của cả hệ thống.** Một CVSS base score mô tả mức nghiêm trọng kỹ thuật của lỗ hổng theo mô hình CVSS tương ứng; điểm rủi ro của tổ chức còn cần xét khai thác thực tế, tài sản, độ phơi lộ, control và tác động nghiệp vụ. Mức CVSS cao có thể không phải rủi ro ưu tiên nhất ở mọi môi trường, còn lỗi logic nghiệp vụ nghiêm trọng có thể không có mã CVE.

## 2. Chấm điểm phải bắt đầu từ ngữ cảnh và phạm vi

Trước khi gán một số, assessor cần xác định:

1. **Hệ thống/tài sản:** dịch vụ, dataset, workflow, hạ tầng, tenant, vùng địa lý và chủ sở hữu.
2. **Mục tiêu bảo mật:** tính bí mật, toàn vẹn, sẵn sàng, xác thực/ủy quyền, truy vết và các nghĩa vụ khác phù hợp.
3. **Kịch bản:** tác nhân, điều kiện, đường khai thác, sự kiện bất lợi và hậu quả.
4. **Trạng thái được đánh giá:** kiến trúc dự kiến, test environment hay production thực tế, revision ứng dụng, policy và phiên bản hạ tầng.
5. **Khoảng thời gian:** ví dụ đánh giá rủi ro trong 12 tháng tiếp theo; kỳ này phải được ghi rõ và nhất quán giữa các kịch bản được so sánh.
6. **Giả định và mức độ chắc chắn:** dữ liệu nào đã được kiểm chứng, điều gì chưa biết hoặc chưa quan sát được.
7. **Hệ quy chiếu/tolerance:** tiêu chí đánh giá tác động, ngưỡng chấp nhận và cơ quan phê duyệt của tổ chức.

Cùng một lỗ hổng không nhất thiết có cùng risk score tại môi trường staging với dữ liệu giả và production với dữ liệu thật. Tương tự, thay đổi từ API chỉ truy cập nội bộ sang Internet công khai có thể làm điểm rủi ro tăng dù không có dòng code nào đổi.

### Ví dụ về cách mô tả kịch bản

| Mô tả mơ hồ | Mô tả giúp chấm điểm |
| --- | --- |
| “Chưa có MFA.” | “Tài khoản quản trị cloud có thể đăng nhập bằng mật khẩu bị lộ mà không có xác thực bổ sung; nguy cơ thay đổi IAM và truy xuất dữ liệu production.” |
| “Có lỗi SQL injection.” | “Endpoint tra cứu đơn hàng nhận input không tham số hóa; người dùng không xác thực có thể gửi payload để đọc dữ liệu đơn hàng trong database có kết nối production.” |
| “Logging chưa đủ.” | “Trong 30 ngày gần đây, sự kiện cấp quyền đặc biệt từ tài khoản B không được chuyển về hệ thống giám sát; hoạt động trái phép có thể không bị phát hiện kịp thời.” |

**Một risk score chỉ có ý nghĩa khi các phương án so sánh dùng cùng tiêu chí và phạm vi tương đương.** Nếu hai nhóm dùng hai thang likelihood khác nhau, phép so điểm số giữa nhóm có thể gây hiểu lầm.

## 3. Những phương pháp chấm điểm thường gặp

Không có một công thức duy nhất bắt buộc cho tất cả tổ chức. Một số lựa chọn:

| Cách đánh giá | Cách biểu diễn | Khi hữu ích | Giới hạn |
| --- | --- | --- | --- |
| **Định tính** | Thấp / trung bình / cao / rất cao | Thiếu dữ liệu định lượng nhưng có chuyên gia và tiêu chí rõ | Dễ phụ thuộc nhận định, cần chuẩn hóa và phản biện |
| **Bán định lượng** | Likelihood 1–5 × impact 1–5 và ma trận | Ưu tiên nhiều rủi ro theo quy trình thống nhất | Điểm thứ bậc không phải phép đo xác suất/tổn thất tuyệt đối |
| **Định lượng** | Xác suất/tần suất, phân phối tổn thất hoặc kỳ vọng thiệt hại theo mô hình phù hợp | Có dữ liệu đủ tốt để phân tích kinh tế và lựa chọn đầu tư | Dữ liệu, giả định và bất định của mô hình có thể lớn |
| **Kết hợp** | Ma trận cho triage; định lượng sâu cho rủi ro trọng yếu | Cân bằng chi phí đánh giá và nhu cầu ra quyết định | Cần giải thích rõ khi đổi phương pháp hoặc đơn vị |

Bài học sử dụng **ma trận 5×5** như một **ví dụ phương pháp nội bộ** để dễ thực hành. Các điểm, ngưỡng và chính sách phía dưới là số minh họa, không phải chuẩn phổ quát hay ngưỡng do NIST/ISO áp đặt. Tổ chức cần chọn phương pháp phù hợp với risk appetite, điều kiện đánh giá và yêu cầu áp dụng.

## 4. Xây dựng thang Likelihood 1–5

**Likelihood** trả lời: kịch bản gây hại có khả năng xảy ra đến mức nào trong phạm vi và kỳ đánh giá đang xét? Không nên đánh đồng một **mức độ dễ khai thác** kỹ thuật với tần suất/khả năng sự kiện có hậu quả thực tế: còn phải xét sự hiện diện của tác nhân, đường truy cập, điều kiện tiên quyết và control đang có hiệu lực.

Một rubric tham khảo:

| Điểm | Nhãn | Định nghĩa định tính minh họa |
| ---: | --- | --- |
| **1** | Rất thấp | Cần nhiều điều kiện hiếm gặp; ít hoặc không có đường truy cập thực tế quan sát được trong phạm vi đánh giá |
| **2** | Thấp | Có thể xảy ra nhưng có điều kiện khó đáp ứng; biện pháp kiểm soát đã được kiểm chứng đang hạn chế đáng kể |
| **3** | Trung bình | Có kịch bản khả thi và một số điều kiện thuận lợi; bằng chứng chưa đủ để coi là thường gặp hoặc hiếm |
| **4** | Cao | Đường khai thác tương đối dễ tiếp cận, điều kiện sẵn có, điểm yếu/hiện trạng tạo cơ hội rõ |
| **5** | Rất cao | Đường gây hại đang hiện hữu hoặc có bằng chứng hoạt động/tái diễn phù hợp, ít trở ngại đáng kể trong phạm vi đánh giá |

Rubric trên **không quy đổi điểm 4 thành “80%”**. Nếu tổ chức muốn dùng ngưỡng xác suất chính xác, cần dữ liệu và mô hình hiệu chuẩn độc lập. Với cách định tính, nên kèm phần giải thích và nguồn bằng chứng cho mỗi điểm.

Các yếu tố thường xem xét:

- **Mức phơi lộ:** Internet công khai, chỉ mạng nội bộ, đặc quyền cần có, số endpoint hoặc tenant bị ảnh hưởng.
- **Khả năng khai thác:** độ phức tạp, nhu cầu tương tác người dùng, tính tự động hóa, đường khai thác khả thi.
- **Tình hình đe dọa:** dấu hiệu tấn công vào tổ chức, lỗ hổng bị khai thác rộng rãi, intel có nguồn gốc và ngày hiệu lực.
- **Trạng thái control:** kiểm tra phân quyền có thật sự được áp dụng không, có cơ chế giới hạn và giám sát hiệu quả không.
- **Sự kiện quá khứ:** incident, near miss, exploit attempt, cảnh báo và dữ liệu giám sát; phải cân nhắc độ phủ của telemetry.
- **Độ tin cậy của quan sát:** “không thấy bị tấn công” không chứng minh rất ít khả năng nếu log thiếu hoặc quy tắc phát hiện chưa có.

Với các kịch bản vô tình như cấu hình nhầm hoặc xóa dữ liệu, likelihood cũng cần xét tần suất thay đổi, mức tự động hóa, phê duyệt, rollback và sự cố tương tự; không chỉ tập trung tác nhân độc hại.

## 5. Xây dựng thang Impact 1–5

**Impact** là hậu quả lên mục tiêu nghiệp vụ và bảo mật nếu tình huống gây hại xảy ra. Có thể liên quan đến thất thoát dữ liệu, gián đoạn, gian lận, tài chính, pháp lý, quyền riêng tư, uy tín, an toàn con người và nghĩa vụ với khách hàng. Không nên lấy riêng trị số CVSS hoặc số lượng request làm mức tác động.

| Điểm | Nhãn | Định nghĩa minh họa theo tác động nghiệp vụ |
| ---: | --- | --- |
| **1** | Không đáng kể | Gián đoạn hoặc ảnh hưởng rất nhỏ, dễ khôi phục, không có dữ liệu nhạy cảm bị ảnh hưởng đáng kể |
| **2** | Nhỏ | Ảnh hưởng có giới hạn, khắc phục nhanh, phạm vi người dùng/tài sản nhỏ |
| **3** | Đáng kể | Chức năng hoặc dữ liệu quan trọng bị ảnh hưởng cục bộ; cần xử lý phối hợp và nguồn lực đáng kể |
| **4** | Nghiêm trọng | Ảnh hưởng lớn tới khách hàng, dịch vụ trọng yếu hoặc dữ liệu nhạy cảm; có khả năng phát sinh nghĩa vụ và chi phí cao |
| **5** | Đặc biệt nghiêm trọng | Có thể gây hậu quả quy mô lớn hoặc khó phục hồi, ảnh hưởng nghiêm trọng tới kinh doanh, quyền riêng tư, nghĩa vụ pháp lý hoặc an toàn |

Để tránh đánh giá tùy hứng, mỗi tổ chức nên định nghĩa **anchor riêng** cho từng tiêu chí: số khách hàng, giới hạn mất dữ liệu, thời gian gián đoạn, chi phí, mức nhạy cảm, nghĩa vụ pháp lý và mức ảnh hưởng đến con người. Ví dụ, ngừng dịch vụ 30 phút có thể thấp đối với một trang thông tin nội bộ nhưng rất cao đối với một hệ thống điều phối cấp cứu.

### Khi có nhiều loại tác động

| Chiều tác động | Câu hỏi thực hành |
| --- | --- |
| Bí mật dữ liệu | Dữ liệu loại nào có thể bị lộ, số lượng và tính nhạy cảm ra sao? |
| Toàn vẹn | Dữ liệu/giao dịch có thể bị sửa tới đâu, có phát hiện và phục hồi được không? |
| Sẵn sàng | Dịch vụ nào dừng, trong bao lâu, ảnh hưởng tới ai và cam kết RTO/RPO nào? |
| Tài chính/nghiệp vụ | Thiệt hại trực tiếp, gián tiếp hoặc ngừng nghiệp vụ ở mức nào? |
| Pháp lý/quyền riêng tư | Có nghĩa vụ thông báo, điều tra, phạt hoặc trách nhiệm hợp đồng nào theo bối cảnh áp dụng? |
| An toàn và uy tín | Hệ quả với con người hoặc niềm tin có đáng kể không? |

Có tổ chức lấy **mức tác động lớn nhất** trong các chiều trọng yếu, có tổ chức dùng quy tắc tổng hợp đã hiệu chuẩn. Không được tự động lấy trung bình các chiều để làm mờ tác động rất lớn đến an toàn hoặc quyền riêng tư. **Phương pháp tổng hợp phải được ban hành trước** và ghi rõ trong hồ sơ đánh giá.

## 6. Tính risk score bằng ma trận 5×5

Với mô hình bán định lượng minh họa:

\[
\text{Risk score} = L \times I
\]

Trong đó **L** là likelihood (1–5), **I** là impact (1–5). Điểm nằm từ **1 đến 25**.

| Likelihood \ Impact | **1** | **2** | **3** | **4** | **5** |
| :--- | ---: | ---: | ---: | ---: | ---: |
| **5** | 5 | 10 | 15 | 20 | 25 |
| **4** | 4 | 8 | 12 | 16 | 20 |
| **3** | 3 | 6 | 9 | 12 | 15 |
| **2** | 2 | 4 | 6 | 8 | 10 |
| **1** | 1 | 2 | 3 | 4 | 5 |

Ví dụ quy định nhóm ưu tiên cho bài học:

| Điểm | Risk level minh họa | Cách phản ứng tham khảo |
| ---: | --- | --- |
| **1–4** | Low | Theo dõi và duy trì control; xem xét theo lịch phù hợp |
| **5–9** | Medium | Có kế hoạch giảm thiểu/giám sát theo chủ sở hữu và chính sách |
| **10–16** | High | Ưu tiên xử lý, có đánh giá và phê duyệt phù hợp trước quyết định liên quan |
| **17–25** | Critical | Chuyển cấp ngay theo chính sách, xem xét giảm thiểu khẩn cấp hoặc tạm dừng hoạt động gây rủi ro |

**Đây là ngưỡng ví dụ.** Trong môi trường thật, tốc độ xử lý, ngưỡng release gate và quyền phê duyệt phải dựa trên chính sách của tổ chức; một score tự nó không ra lệnh “phải đóng production”.

### Hai lưu ý quan trọng khi đọc điểm

**Thứ nhất:** thang 1–5 thường là *ordinal* (thứ bậc), không bảo đảm chênh lệch 4→5 bằng 2→3 về xác suất hoặc chi phí. Vì vậy, `L×I` là **quy ước xếp ưu tiên**, không phải tính toán tổn thất kỳ vọng tuyệt đối. Điểm 20 không có nghĩa rủi ro “nguy hiểm gấp đôi” điểm 10.

**Thứ hai:** phép nhân có thể cho cùng một số từ những tình huống rất khác nhau. `L=5, I=2` và `L=2, I=5` đều đạt 10 nhưng một trường hợp xảy ra thường xuyên với tác động nhỏ, trường hợp còn lại hiếm hơn nhưng hậu quả lớn. Các chính sách cần cho phép **chuyển cấp riêng với tác động thảm họa** hoặc nghĩa vụ pháp lý, ngay cả khi điểm tích thấp.

## 7. Risk score ban đầu và sau khi áp dụng control

Cần phân biệt:

- **Inherent risk / rủi ro ban đầu:** mức rủi ro của kịch bản **trước các control đang đánh giá** theo giả định/baseline cụ thể; cách tính phải ghi rõ và nhất quán.
- **Residual risk / rủi ro còn lại:** mức rủi ro sau khi xét các control đã được triển khai và **có cơ sở đánh giá hiệu lực**, cùng các giới hạn còn tồn tại.
- **Target risk / mức mục tiêu:** mức tổ chức muốn đạt sau các hành động dự kiến; **chưa phải trạng thái hiện tại**.
- **Risk acceptance:** quyết định có thẩm quyền về việc chịu rủi ro tồn dư theo phạm vi/điều kiện xác định; không biến một control thất bại thành đạt.

Một sơ đồ quyết định cơ bản:

~~~mermaid
flowchart TD
    A["Mô tả risk scenario và phạm vi"] --> B["Đánh giá L/I ban đầu với giả định rõ"]
    B --> C["Định nghĩa control và tiêu chí chấp nhận"]
    C --> D["Triển khai control, test và thu bằng chứng"]
    D --> E{"Control có hiệu lực được xác minh?"}
    E -- "Có" --> F["Đánh giá lại L/I và residual score"]
    E -- "Không hoặc chưa đủ bằng chứng" --> G["Không ghi giảm điểm theo giả định"]
    G --> H["Finding, sửa, retest hoặc xử lý rủi ro theo thẩm quyền"]
    H --> D
    F --> I{"Mức còn lại trong giới hạn quyết định?"}
    I -- "Có" --> J["Ghi quyết định, owner, điều kiện đánh giá lại"]
    I -- "Không" --> H
~~~

**Không nên trừ một số phần trăm máy móc** mỗi khi thêm control. Một control chỉ làm thay đổi likelihood/impact nếu nó thực sự tác động đến điều kiện gây hại và mức thay đổi có căn cứ. Ví dụ, thêm logging không trực tiếp ngăn unauthorized access; nó có thể hỗ trợ phát hiện và giới hạn tác động trong một số điều kiện, nhưng cần bằng chứng detection và thời gian phản ứng.

## 8. Ví dụ hoàn chỉnh: Risk score cho API xuất tài liệu giữa các tenant

**Bối cảnh:** một ứng dụng Java/Spring Boot có endpoint `GET /api/reports/{id}/export` trả CSV. API yêu cầu đăng nhập nhưng không kiểm tra người dùng có quyền trên báo cáo thuộc tenant khác không. Báo cáo chứa dữ liệu nhạy cảm của khách hàng; endpoint ở production và có thể được gọi bởi nhiều tài khoản.

### Bước 1 — Xác định rủi ro và mục tiêu

| Thành phần | Mô tả |
| --- | --- |
| **Risk ID** | RISK-DATA-007 |
| **Asset** | Báo cáo nhạy cảm của khách hàng trong dịch vụ report-service |
| **Threat scenario** | Người dùng tenant A thay ID và tải CSV của tenant B |
| **Điểm yếu** | Endpoint chỉ kiểm tra “đã đăng nhập”, bỏ qua quyền theo đối tượng/tenant |
| **Mục tiêu** | Bảo vệ bí mật dữ liệu và ranh giới tenant |
| **Phạm vi** | Production, endpoint export và các luồng tải báo cáo tương tự |
| **Kỳ đánh giá** | Ví dụ 12 tháng tiếp theo, cần điều chỉnh theo quy định của tổ chức |

### Bước 2 — Chấm điểm ban đầu có lý do

**Likelihood = 4 (cao):** nhiều tài khoản có thể gọi API; biết ID hoặc đoán ID trong điều kiện phù hợp; kiểm tra cấp đối tượng thiếu. Tuy nhiên cần kiểm chứng phương thức tìm ID, phạm vi API và khả năng khai thác thực tế; đây là **đánh giá minh họa theo giả định**.

**Impact = 5 (đặc biệt nghiêm trọng):** nếu hàng loạt báo cáo nhạy cảm bị tải trái phép, tác động có thể lớn đến quyền riêng tư, khách hàng và trách nhiệm nghiệp vụ. Điểm thực tế phụ thuộc quy mô dữ liệu, phân loại tài sản và nghĩa vụ áp dụng.

\[
L = 4,\qquad I = 5,\qquad R_{\text{inherent}} = 4\times 5 = 20
\]

Theo ngưỡng mẫu ở phần 6: **Critical (20/25)**.

### Bước 3 — Chọn control và tiêu chí nghiệm thu

| ID | Control hoặc hoạt động | Kết quả cần kiểm tra |
| --- | --- | --- |
| CTRL-AUTHZ-01 | Kiểm tra quyền trên từng báo cáo, ràng buộc actor, tenant và action | Tenant A không đọc/xuất được báo cáo B; user hợp lệ vẫn hoạt động |
| CTRL-AUTHZ-02 | Dùng chung đường authorization cho xem, download, export và batch | Không có đường bypass trên mọi route thuộc phạm vi |
| CTRL-TEST-01 | Test negative/positive tự động trong CI và kiểm tra route thực | Test với fixture thực và security filters đúng; test lỗi cũ |
| CTRL-OPS-01 | Kiểm soát release và kiểm chứng image digest trên môi trường triển khai | Bản đã kiểm thử đúng là bản đang chạy |
| CTRL-LOG-01 | Ghi nhận truy cập bị từ chối và phát hiện bất thường phù hợp | Event tới nơi giám sát và có người xử lý khi test |

### Bước 4 — Thu bằng chứng trước khi chấm lại

Ví dụ bằng chứng cần được thu thực tế:

- Pull request được review có thay đổi logic phân quyền và giải thích phạm vi.
- Bộ integration tests gồm user hợp lệ, tenant khác, không đăng nhập, role không đủ và endpoint export.
- CI run gắn với commit và artifact digest, có cả kết quả thất bại trước sửa và thành công sau sửa.
- Đối chiếu artifact digest với deployment thực tế; kiểm tra policy và cấu hình liên quan trên môi trường đích.
- Test end-to-end có kiểm soát với dữ liệu thử, cùng log và cảnh báo nếu nằm trong phạm vi.
- Kết quả rà soát các endpoint tương tự, finding, người đánh giá và giới hạn còn lại.

Một test mock trả HTTP 403 không tự chứng minh toàn bộ API đã được bảo vệ. Bằng chứng phải khớp với **đường xử lý thật** và mọi đường truy cập thuộc claim.

### Bước 5 — Tính residual risk và quyết định

Giả sử control phân quyền cấp đối tượng đã được kiểm chứng trên các tuyến liên quan, chính sách quyền và bản triển khai đã được đối chiếu. Nhóm đánh giá có cơ sở hạ **likelihood từ 4 xuống 2**, trong khi **impact vẫn 5** vì nếu control bị bypass và báo cáo lộ, hậu quả tiềm năng không tự giảm:

\[
L_{\text{residual}}=2,\quad I_{\text{residual}}=5,\quad
R_{\text{residual}}=2\times 5=10
\]

Theo thang minh họa, **10 = High**. Hạ điểm từ 20 xuống 10 chỉ đúng **nếu giả định được bảo vệ bởi bằng chứng và assessor đã review**; đây không phải số liệu đo được của hệ thống cụ thể. Rủi ro High vẫn có thể vượt risk tolerance và cần thêm biện pháp, đánh giá độc lập hoặc quyết định rủi ro của người có thẩm quyền.

**Sai lầm thường gặp:** team đặt điểm residual = 4 ngay khi merge PR sửa lỗi, trước khi test hoặc triển khai, rồi dùng đó làm bằng chứng rủi ro “đã xử lý”. Đó mới là **dự kiến sau khắc phục**, không phải residual đã được kiểm chứng.

## 9. Điểm số và bằng chứng trong hồ sơ security assurance

Risk score chỉ giúp ra quyết định khi có thể truy ngược **lý do, nguồn dữ liệu, phương pháp và người chịu trách nhiệm**.

### Chuỗi truy vết

~~~text
RISK-DATA-007: Tải báo cáo trái phép giữa các tenant
    -> OBJ-CONF-01: Bảo vệ tính bí mật
    -> REQ-AUTHZ-01: Phân quyền theo báo cáo và tenant
    -> CTRL-AUTHZ-01: Kiểm tra quyền trên mỗi route đọc/xuất
    -> TEST-AUTHZ-01: Negative/positive integration và end-to-end tests
    -> EV-AUTHZ-01: Test result + commit + image digest + deployment
    -> FIND-AUTHZ-01: Route thiếu kiểm tra quyền (nếu còn)
    -> RISK-REVIEW-01: Residual score, giới hạn và quyết định xử lý
~~~

### Mẫu bản ghi risk register

Mẫu dưới đây dùng placeholder `<...>`, **không mô tả kết quả đánh giá thật** và không dùng làm xác nhận hệ thống đạt control:

~~~yaml
risk_id: RISK-DATA-007
title: "Đọc trái phép báo cáo giữa các tenant"
scenario: "User tenant A xuất báo cáo thuộc tenant B"
asset: "report-service/customer-reports"
environment: production
assessment_period: "<START_END_OR_TIME_HORIZON>"
assessment_date: "<ISO_8601_DATE>"
assessment_method: "likelihood-impact-matrix-5x5-v1"
risk_owner: "<AUTHORIZED_RISK_OWNER>"
assessor: "<PERSON_OR_TEAM>"
initial_assessment:
  likelihood: 4
  impact: 5
  score: 20
  level: critical
  rationale: "<EVIDENCE_BASED_REASONING>"
controls:
  - id: CTRL-AUTHZ-01
    implementation_ref: "<REVIEWED_COMMIT>"
    evaluation_ref: "<TEST_RUN_OR_ASSESSMENT>"
  - id: CTRL-OPS-01
    implementation_ref: "<DEPLOYMENT_ID>"
    evaluation_ref: "<RUNTIME_CHECK>"
residual_assessment:
  likelihood: 2
  impact: 5
  score: 10
  level: high
  valid_only_if: "All listed controls have verified effectiveness"
confidence: "<HIGH_MEDIUM_LOW_AND_RATIONALE>"
limitations: "<MISSING_EVIDENCE_AND_UNTESTED_SCOPE>"
decision:
  treatment: "<MITIGATE_AVOID_SHARE_ACCEPT>"
  approving_authority: "<APPROVER>"
  decision_ref: "<APPROVAL_OR_TICKET_ID>"
  due_date: "<REVIEW_OR_REMEDIATION_DATE>"
review_triggers:
  - "Thay đổi luồng authorization hoặc tenant"
  - "Thay đổi quyền/môi trường production"
  - "Phát hiện bị khai thác hoặc control không hoạt động"
evidence_refs:
  - "<SOURCE_CONTROL_AND_REVIEW>"
  - "<TEST_RESULT>"
  - "<DEPLOYMENT_AND_RUNTIME_VERIFICATION>"
~~~

Từng trường score phải có một **rationale** giải thích tại sao chọn đúng mức đó. Nếu dữ liệu chưa đủ, assessor phải ghi độ tin cậy và khoảng bất định hoặc trạng thái “chưa đủ dữ liệu”, thay vì lấy một con số như thể đã đo chính xác.

### Trạng thái đánh giá control khác trạng thái risk score

| Trạng thái control | Điều có thể kết luận | Ảnh hưởng tới residual score |
| --- | --- | --- |
| **Đã kiểm chứng đạt** | Control đáp ứng yêu cầu trong phạm vi, thời điểm đã thử | Có cơ sở xem xét giảm điểm nếu control thực sự làm giảm khả năng/tác động |
| **Chưa đủ bằng chứng** | Chưa thể kết luận hiệu lực control | Không được tự suy ra điểm giảm từ một thiết kế hoặc lời hứa |
| **Không đạt** | Bằng chứng cho thấy thiếu hụt | Cần khắc phục, đánh giá lại và có thể tăng điểm theo thực trạng |
| **Ngoại lệ được chấp nhận** | Người có thẩm quyền chịu rủi ro tồn dư theo điều kiện cụ thể | Không tự thay đổi sự thật kỹ thuật hoặc điểm đánh giá |

## 10. Công cụ và dữ liệu hỗ trợ chấm điểm

Đánh giá nên dựa trên nguồn dữ liệu có ngữ cảnh rõ:

| Nguồn dữ liệu | Hỗ trợ đánh giá | Cần tránh suy luận gì? |
| --- | --- | --- |
| Inventory tài sản và phân loại dữ liệu | Xác định scope, độ nhạy cảm và hậu quả | Asset “low” trên CMDB chưa chắc phản ánh dữ liệu hiện tại |
| Threat model, attack path, kiểm thử xâm nhập | Xác định kịch bản, tính khả thi và điều kiện khai thác | Một đường thử thất bại không chứng minh không có đường khác |
| CVSS và advisory | Tham khảo tính nghiêm trọng của lỗ hổng kỹ thuật | CVSS không thay cho tác động nghiệp vụ và bối cảnh tổ chức |
| Dữ liệu khai thác thực tế, threat intelligence | Bổ sung tín hiệu về hành vi đe dọa và mức ưu tiên | Tín hiệu bên ngoài không tự chứng minh hệ thống cụ thể đã bị khai thác |
| Test, review, scan và cấu hình triển khai | Đánh giá control có được triển khai, kiểm tra hay không | CI pass không chứng minh production đang chạy đúng |
| Log, incident, near miss và detection test | Quan sát sự kiện và khả năng phát hiện | Không có alert không có nghĩa sự kiện không xảy ra |
| Dữ liệu kinh doanh, RTO/RPO và yêu cầu pháp lý | Hiệu chuẩn tiêu chí impact | Không dùng số liệu bối cảnh khác mà không kiểm tra khả năng áp dụng |

Một hệ thống scoring tự động có thể tổng hợp data, tính điểm theo rule và nhắc review; **không nên tự động tạo quyết định chấp nhận rủi ro** từ một công thức đơn giản khi ngữ cảnh nghiệp vụ hoặc chứng cứ còn thiếu.

## 11. Ví dụ Java: tính điểm nhất quán theo rubric

Đoạn Java 17+ sau chỉ **tự động hóa công thức và ngưỡng minh họa**. Nó không xác định likelihood và impact từ sự thật bên ngoài, không thay thế review của assessor, không đánh giá hiệu lực control.

~~~java
public final class RiskScoreExample {
    public enum Level {
        LOW, MEDIUM, HIGH, CRITICAL
    }

    public record RiskScore(int likelihood, int impact) {
        public RiskScore {
            if (likelihood < 1 || likelihood > 5) {
                throw new IllegalArgumentException("likelihood phải từ 1 đến 5");
            }
            if (impact < 1 || impact > 5) {
                throw new IllegalArgumentException("impact phải từ 1 đến 5");
            }
        }

        public int value() {
            return likelihood * impact;
        }

        public Level level() {
            int score = value();
            if (score >= 17) return Level.CRITICAL;
            if (score >= 10) return Level.HIGH;
            if (score >= 5) return Level.MEDIUM;
            return Level.LOW;
        }
    }

    public static void main(String[] args) {
        RiskScore before = new RiskScore(4, 5);
        RiskScore after = new RiskScore(2, 5);

        System.out.println(before.value() + " / " + before.level());
        System.out.println(after.value() + " / " + after.level());
        // 20 / CRITICAL
        // 10 / HIGH
    }
}
~~~

Để đưa logic vào ứng dụng thật, cần thêm **version của ma trận**, chính sách chặn/chuyển cấp rủi ro đặc biệt, lịch sử thay đổi, giải trình và phê duyệt. Không nên cho một developer tự chỉnh ngưỡng nhằm “làm xanh” pipeline mà không có quản trị và review. Các ca biên (1, 4, 5, 9, 10, 16, 17, 25) nên được xác minh nếu dùng kết quả code cho quyết định thực tế.

## 12. Chuyển risk score thành ưu tiên và kế hoạch xử lý

Điểm rủi ro phục vụ quyết định **xử lý gì trước, ai chịu trách nhiệm, deadline nào và cần bằng chứng mức nào**. Các phương án phổ biến:

| Lựa chọn xử lý | Khi nào có thể cân nhắc | Ví dụ | Trách nhiệm cần xác định |
| --- | --- | --- | --- |
| **Giảm thiểu (mitigate)** | Có control khả thi làm giảm likelihood hoặc impact | Bổ sung authorization, phân tách mạng, tăng khả năng phục hồi | Control owner, người triển khai, người kiểm chứng, risk owner |
| **Tránh (avoid)** | Hoạt động gây rủi ro không cần thiết hoặc vượt khả năng kiểm soát | Tắt endpoint export công khai khi chưa có quyền truy cập an toàn | Chủ sở hữu nghiệp vụ và người phê duyệt thay đổi |
| **Chia sẻ/chuyển một phần (share/transfer)** | Có cơ chế hợp đồng/bảo hiểm/chia sẻ nghĩa vụ thích hợp | Hợp đồng với nhà cung cấp, cơ chế bảo hiểm | Chủ sở hữu hợp đồng/rủi ro; xác nhận phần rủi ro vẫn còn |
| **Chấp nhận (accept)** | Rủi ro trong ngưỡng và được người có thẩm quyền chấp thuận | Ngoại lệ có thời hạn, control bù trừ và lịch review | Risk owner/authority, không phải mặc nhiên người tạo finding |

**Chia sẻ rủi ro không làm mất toàn bộ trách nhiệm**, đặc biệt với dữ liệu, nghĩa vụ pháp lý và quyền của khách hàng. Chấp nhận rủi ro là một quyết định quản trị có hồ sơ; nó không phải bằng chứng control đã được sửa.

Một **risk treatment plan** cần có: risk ID, score/rationale hiện tại, mức mục tiêu, biện pháp cụ thể, control owner, risk owner, người kiểm chứng, hạn xử lý, tiêu chí thành công, bằng chứng dự kiến, chi phí/tác động nghiệp vụ, đường escalation và ngày tái đánh giá.

### Khi hai rủi ro cùng số điểm

Giả sử RISK-A = `5 × 2 = 10` (nhiều lần gián đoạn nhỏ) và RISK-B = `2 × 5 = 10` (ít gặp nhưng gây hậu quả pháp lý nghiêm trọng). Để sắp ưu tiên, còn xét:

- Quy định hoặc nghĩa vụ bắt buộc không thể bỏ qua.
- Mức phơi lộ, số người bị ảnh hưởng và thời gian phát hiện/khắc phục.
- Khả năng một sự kiện làm suy giảm nhiều control hoặc lan rộng giữa các hệ thống.
- Độ tin cậy của dữ liệu và mức bất định.
- Hiệu quả, chi phí và thời gian triển khai biện pháp giảm thiểu.
- Quy tắc ưu tiên rủi ro tác động cực lớn theo risk appetite.

Vì vậy, dashboard nên giữ **cả L và I**, rationale và thời điểm, không chỉ cột “score”.

## 13. Risk score trong quy trình phát triển và vận hành liên tục

Điểm rủi ro có thể thay đổi **khi môi trường hoặc bằng chứng thay đổi**. Nên xây dựng cơ chế đánh giá lại theo sự kiện và định kỳ.

| Điểm kích hoạt | Cần kiểm tra lại | Bằng chứng được cập nhật |
| --- | --- | --- |
| Thêm API, trust boundary hoặc luồng dữ liệu mới | Kịch bản đe dọa, L/I và phạm vi control | Threat model, yêu cầu, review, test |
| Thay đổi xác thực/phân quyền | Khả năng khai thác, quyền thực tế và nguy cơ bypass | Test authorization, IAM policy, commit/build |
| Cập nhật dependency hoặc advisory mới | Độ phơi lộ, tính khai thác, asset liên quan | SBOM/inventory, SCA, triage và bản vá |
| Đưa bản mới lên production | Control đã được triển khai đúng chưa, cấu hình có drift không | Artifact digest, deployment record, runtime validation |
| Phát hiện khai thác hoặc sự cố | Likelihood, mức tác động, phạm vi ảnh hưởng và độ tin cậy của điểm cũ | Incident timeline, log, evidence và đánh giá lại |
| Control monitoring hoặc backup bị lỗi | Mức mất khả năng phát hiện/khôi phục; tác động và rủi ro tồn dư | Alert, detection test, restore drill |
| Hoàn tất remediation | Kết quả retest, status control và residual score | Regression test, review, deployment, retest |
| Đến kỳ audit/review | Điểm còn hiệu lực không, ngoại lệ có hết hạn không | Risk register, sign-off, control evidence, finding |

Các tiêu chí đo lường hữu ích: tỷ lệ rủi ro cao có owner, tỷ lệ đánh giá có căn cứ đầy đủ, tỷ lệ score còn hiệu lực trong kỳ, số ngoại lệ quá hạn, tỷ lệ finding được retest trên đúng môi trường và thời gian chênh giữa thay đổi control với lần đánh giá lại.

Không dùng KPI “giảm điểm trung bình bằng mọi giá”. Nó có thể khuyến khích hạ điểm chủ quan hoặc ẩn các tình huống nghiêm trọng. Cần theo dõi cả **chất lượng bằng chứng, thay đổi thực của exposure/control, độ bao phủ và độ tin cậy**.

## 14. Các sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm? | Cách khắc phục |
| --- | --- | --- |
| “Mọi CVSS 9.8 đều là risk score 9.8 của công ty.” | CVSS severity không đại diện toàn bộ rủi ro nghiệp vụ | Dùng CVSS như một đầu vào, đánh giá tài sản, exposure, control và tác động |
| “Likelihood 4 nghĩa là có 80% xác suất bị tấn công.” | Thang ordinal 1–5 không tự có ý nghĩa xác suất | Nêu rubric định tính; chỉ dùng xác suất khi có mô hình được hiệu chuẩn |
| “Có firewall/monitoring thì tự trừ 50% điểm.” | Chưa chứng minh control ngăn sự kiện hoặc giảm hậu quả | Liên kết control, test, deployment và hiệu quả vận hành |
| “Không có alert nghĩa là rủi ro thấp.” | Thiếu log hoặc detection có thể làm quan sát không đầy đủ | Kiểm tra độ phủ telemetry và detection test |
| “Score được tính ở staging nên dùng luôn cho production.” | Dữ liệu, cấu hình, người dùng và exposure có thể khác | Ghi môi trường/phạm vi và tái đánh giá khi triển khai |
| “Cùng điểm thì ưu tiên như nhau.” | L/I, nghĩa vụ và hậu quả có thể rất khác | Giữ nguyên L/I, dùng tiêu chí escalation và risk appetite |
| “Tự đóng finding đồng nghĩa residual risk thấp.” | Chưa chứng minh control hoạt động trên bản sửa đã deploy | Có retest, review và runtime evidence |
| “Risk owner có thể sửa điểm để release nhanh.” | Thiếu traceability và có thể che thiếu hụt kỹ thuật | Version rubric, ghi rationale, lịch sử, người review và quyền phê duyệt |
| “Chấp nhận rủi ro nghĩa là control đã đạt.” | Quyết định quản trị không đổi sự thật kỹ thuật | Giữ finding/control status riêng với acceptance record |

## 15. Bài tập thực hành

**Tình huống:** hệ thống đăng ký tài khoản có endpoint reset mật khẩu. Tính năng cho phép gửi email reset nhưng không giới hạn tần suất theo danh tính hoặc nguồn request. Có dấu hiệu lượng request tăng bất thường. Nhóm phát triển đề nghị tăng risk score từ Medium lên High và thêm rate limit; nhóm vận hành cho rằng “đã có WAF nên rủi ro chắc chắn thấp”.

Hãy thực hiện:

1. Viết **risk scenario** nêu rõ tác nhân, điểm yếu, sự kiện và hậu quả; phân biệt email flooding, lạm dụng tài nguyên và khả năng chiếm tài khoản.
2. Đặt giả định về môi trường, phạm vi, kỳ đánh giá; chọn L và I trên thang 1–5 và giải thích.
3. Xác định dữ liệu nào có thể hỗ trợ likelihood: access logs, telemetry, WAF coverage, khả năng bypass, hiệu lực quota, số event quan sát và các giới hạn.
4. Đề xuất security controls và test cho rate limit, hành vi khác biệt giữa IP/tài khoản, bảo vệ user enumeration và luồng reset hợp lệ.
5. Lập bộ evidence cần có trước khi hạ residual score; xác định ai review và ai được phê duyệt chấp nhận rủi ro tồn dư.
6. Đưa ra trigger đánh giá lại khi WAF rule thay đổi, xuất hiện tấn công, logic reset được triển khai lại hoặc có finding mới.

### Một lời giải minh họa

**Kịch bản:** tác nhân ngoài Internet có thể gửi lượng lớn request reset cho cùng tài khoản hoặc nhiều tài khoản; việc thiếu rate limit hiệu quả dẫn tới gửi email hàng loạt, tiêu thụ tài nguyên và làm giảm chất lượng dịch vụ. Tình huống chiếm tài khoản cần **kịch bản riêng**: thiếu rate limit của request reset **không tự chứng minh** token reset bị đoán được hoặc tài khoản có thể bị chiếm; muốn đánh giá account takeover phải có thêm điều kiện và chứng cứ.

Giả sử endpoint công khai, request bị lặp nhiều và chưa có bằng chứng hiệu lực của WAF trên đường truy cập thực, assessor có thể **minh họa** likelihood = 4, impact = 3 cho kịch bản email flooding, score = `4 × 3 = 12` (High theo thang bài học). Kết luận thật cần căn cứ số liệu, tác động nghiệp vụ và chính sách tổ chức.

Các control có thể gồm rate limit nhiều chiều theo tài khoản/nguồn, chống lạm dụng ở lớp ứng dụng và edge, giới hạn tài nguyên/queue, thông báo lỗi không tiết lộ tài khoản, và monitoring độ phủ. Kiểm thử cả request bình thường và request vượt ngưỡng, nhiều nguồn, proxy, retry, khoảng thời gian và tác động tới người dùng hợp lệ. Chỉ sau khi đối chiếu chính sách, test, phiên bản triển khai và tín hiệu vận hành, nhóm mới có cơ sở đánh giá lại likelihood.

Nếu vẫn còn điểm High hoặc bằng chứng không đủ, risk owner được trao thẩm quyền cần quyết định kế hoạch xử lý hoặc ngoại lệ có thời hạn. **Không giảm residual score chỉ dựa vào việc WAF đang bật.**

## Ghi nhớ

- **Risk score là công cụ hỗ trợ quyết định**, được tính trong một bối cảnh, phạm vi, khoảng thời gian và phương pháp xác định; điểm số không phải bằng chứng hệ thống an toàn.
- Với ma trận 5×5, `likelihood × impact` cho ra một chỉ số **bán định lượng mang tính thứ bậc**, không phải xác suất hay thiệt hại tuyệt đối.
- Cần tách **inherent risk, target risk và residual risk**, đồng thời ghi rõ điều kiện và bằng chứng cho mọi lần giảm điểm.
- **Control được viết ra hoặc merge chưa chứng minh đã vận hành hiệu quả**: phải có test, review, version/deployment, phạm vi và khả năng tái kiểm tra.
- Bản ghi risk score tốt liên kết được **risk → objective → requirement → control → evidence → finding → retest → decision**, cùng owner và thời điểm đánh giá lại.
- Security assurance liên tục đòi hỏi **cập nhật risk score khi có phát hiện, thay đổi, sự cố hoặc bằng chứng mới**, với sự phối hợp giữa phát triển, vận hành, bảo mật, audit và người có thẩm quyền chấp nhận rủi ro.

# Rủi ro còn lại (Residual Risk) trong đánh giá rủi ro bảo mật

## 1. Vì sao đã triển khai kiểm soát vẫn còn rủi ro?

Một nhóm phát triển đã bật MFA cho tài khoản quản trị, phân quyền theo tenant, mã hóa dữ liệu, kiểm tra bảo mật trong CI/CD và sao lưu thường xuyên. Nhóm có thể kết luận hệ thống đã an toàn tuyệt đối không?

**Không.** Những biện pháp trên có thể giảm khả năng sự cố xảy ra, hạn chế phạm vi ảnh hưởng hoặc giúp khôi phục nhanh hơn. Nhưng tài khoản vẫn có thể bị chiếm qua phiên đăng nhập, phân quyền vẫn có thể lỗi ở endpoint mới, khóa mã hóa có thể bị lộ và bản sao lưu có thể không phục hồi được. Một số nguyên nhân hoặc điều kiện còn nằm ngoài phạm vi kiểm soát.

**Rủi ro còn lại (residual risk)** là **mức rủi ro vẫn tồn tại sau khi tính đến các biện pháp xử lý và security controls có hiệu lực trong phạm vi đánh giá**. Đây là cơ sở để tổ chức trả lời:

- Controls đã giảm được **khả năng xảy ra**, **mức độ hậu quả**, hay cả hai?
- Phần rủi ro chưa giảm đang nằm ở kịch bản, tài sản, người dùng hoặc phụ thuộc nào?
- Có **bằng chứng kiểm chứng** rằng các controls đã hoạt động đúng và đủ phạm vi không?
- Mức rủi ro còn lại có phù hợp **risk appetite** và tiêu chí chấp nhận đã được phê duyệt không?
- Nếu chưa phù hợp, ai phải bổ sung biện pháp, theo dõi phát hiện hoặc quyết định xử lý?

Trong chương **Đánh giá rủi ro** của module **SECURITY_SECURITY_ASSURANCE**, residual risk nối phân tích rủi ro với **yêu cầu bảo mật, security controls, kiểm thử, audit, khắc phục phát hiện và đánh giá lại liên tục**. Tuyên bố “rủi ro đã giảm” phải được hỗ trợ bởi lập luận và bằng chứng, thay vì chỉ dựa vào việc mua công cụ, hoàn thành ticket hay có một lần kiểm thử đạt.

> Rủi ro còn lại **không đồng nghĩa với rủi ro được chấp nhận**. Tổ chức phải đánh giá phần rủi ro tồn tại rồi mới ra quyết định xử lý hoặc chấp nhận theo đúng thẩm quyền.

## 2. Phân biệt các khái niệm dễ nhầm

Các phương pháp quản trị có thể đặt tên trạng thái rủi ro khác nhau. Khi thiết lập chương trình đánh giá, phải ghi rõ đang dùng định nghĩa nào.

| Khái niệm | Ý nghĩa trong bài | Ví dụ |
| --- | --- | --- |
| **Inherent risk – Rủi ro vốn có** | Mức rủi ro của kịch bản trong giả định **chưa tính tác dụng của các controls được lựa chọn**, theo mô hình được tổ chức xác định. | Rủi ro truy cập chéo tenant nếu không có cơ chế phân quyền đối tượng. |
| **Current residual risk – Rủi ro còn lại hiện tại** | Mức rủi ro **ngay tại thời điểm đánh giá**, sau khi xét các controls đã thực sự triển khai và được kiểm chứng ở phạm vi liên quan. | Đã có phân quyền tập trung, nhưng endpoint export chưa được kiểm tra. |
| **Target residual risk – Rủi ro còn lại mục tiêu** | Mức dự kiến sau khi hoàn thành các biện pháp đang lên kế hoạch; là **mục tiêu/ước tính**, chưa phải kết quả hiện tại. | Dự kiến giảm sau khi bổ sung kiểm tra quyền và kiểm thử export. |
| **Risk appetite – Khẩu vị rủi ro** | Loại và lượng rủi ro tổ chức sẵn sàng theo đuổi hoặc duy trì để đạt mục tiêu. | Không chấp nhận rủi ro lộ rộng dữ liệu nhạy cảm ngoài giới hạn chính sách. |
| **Risk tolerance / acceptance criteria – Ngưỡng/tiêu chí chịu đựng và chấp nhận** | Giới hạn thực hành dùng để xem xét mức rủi ro được phép ở một hoạt động, dịch vụ hoặc thời gian nhất định. | Rủi ro cấp cao phải được trình hội đồng hoặc cấp quản trị được ủy quyền. |
| **Accepted residual risk – Rủi ro còn lại đã được chấp nhận** | Phần rủi ro được người có thẩm quyền **chủ động phê duyệt** theo phạm vi, điều kiện và thời hạn phù hợp. | Chấp nhận tạm thời một ngoại lệ có biện pháp bù đắp và ngày hết hạn. |
| **Realized loss / incident impact – Tổn thất đã xảy ra** | Hậu quả thực tế của một sự cố được xác nhận; khác với rủi ro dự kiến trước sự cố. | Dịch vụ đã ngừng 18 phút và 250 giao dịch đã thất bại. |

Một số tổ chức định nghĩa **residual risk** là rủi ro sau **mọi phương án xử lý đã hoàn tất**, và dùng **current risk** cho trạng thái trước khi xử lý bổ sung. Khi đó phải ghi rõ mốc thời gian, controls nào đã tính và loại đánh giá nào đang được trình bày. Bài này sử dụng thuật ngữ **current residual risk** để chỉ trạng thái **đang có và đã được kiểm chứng**, giúp tránh nhập nhằng với target residual risk.

### Rủi ro không về 0 chỉ vì có security control

Mỗi control đều có **điều kiện hoạt động, phạm vi, phụ thuộc và giới hạn**:

- MFA có thể bảo vệ đăng nhập thông thường nhưng không bao trùm một đường xác thực cũ.
- Rate limiting giảm lạm dụng nhưng có thể chặn nhầm người dùng hợp lệ hoặc không đủ khi lưu lượng vượt năng lực thiết kế.
- Backup giúp khôi phục nhưng có thể không tồn tại ngoài miền lỗi chung hoặc chưa được thử restore.
- WAF phát hiện được một số dạng tấn công nhưng không bảo đảm nhận diện mọi lỗi logic nghiệp vụ.
- Review quyền truy cập thực hiện theo quý có thể bỏ sót thay đổi xảy ra giữa hai kỳ review.

Những giới hạn đó là một phần của **rủi ro còn lại** và cần được mô tả công khai trong kết luận assurance.

## 3. Rủi ro còn lại luôn gắn với một kịch bản cụ thể

Không nên viết “hệ thống còn rủi ro mức 3” mà thiếu kịch bản. Để đánh giá được, cần xác định:

1. **Tài sản và mục tiêu:** dịch vụ, dữ liệu, hoạt động kinh doanh hoặc con người cần bảo vệ.
2. **Sự kiện bất lợi:** tác nhân hoặc nguyên nhân, điểm yếu, điều kiện xảy ra và đường dẫn tới hậu quả.
3. **Phạm vi và thời gian:** phiên bản, môi trường, nhóm người dùng, tenant, vùng địa lý và giai đoạn đánh giá.
4. **Impact:** hậu quả với tính bí mật, toàn vẹn, sẵn sàng và các ảnh hưởng nghiệp vụ liên quan nếu kịch bản xảy ra.
5. **Likelihood:** khả năng/tần suất kịch bản trong khoảng thời gian đã định, cùng độ không chắc chắn.
6. **Các controls hiện hành:** cách controls phòng ngừa, phát hiện, giới hạn hoặc phục hồi; ai sở hữu và phần nào được bao phủ.
7. **Bằng chứng:** test, review, cấu hình, log, audit hoặc diễn tập chứng minh hiệu lực và giới hạn của từng control.

**Ví dụ kịch bản:** “Trong bản phát hành đang chạy của dịch vụ hóa đơn đa tenant, một người dùng đã xác thực có thể yêu cầu ID hóa đơn không thuộc tenant của họ; nếu API bỏ qua object-level authorization, thông tin kinh doanh của tenant khác có thể bị đọc.”

Với kịch bản này, không thể đánh giá residual risk đúng nếu chỉ biết “JWT đang hoạt động”. Cần chứng minh mỗi đường truy cập liên quan thực hiện **authorization theo đối tượng và tenant**, không chỉ xác thực danh tính ban đầu.

~~~mermaid
flowchart LR
    A["Tài sản + kịch bản rủi ro"] --> B["Inherent risk theo giả định"]
    B --> C["Controls hiện có và phạm vi áp dụng"]
    C --> D["Bằng chứng thiết kế + vận hành"]
    D --> E["Current residual risk"]
    E --> F{"Đáp ứng tiêu chí chấp nhận?"}
    F -- "Chưa" --> G["Xử lý bổ sung + kiểm chứng lại"]
    F -- "Có thể" --> H["Quyết định của risk owner có thẩm quyền"]
    G --> E
    H --> I["Giám sát và đánh giá lại"]
    I --> C
~~~

Biểu đồ minh họa chu trình ra quyết định; **đạt ngưỡng** không tự động tạo một phê duyệt và **không đạt ngưỡng** không cho phép bỏ qua nghĩa vụ bắt buộc.

## 4. Controls thực sự làm giảm phần nào của rủi ro?

Rủi ro có thể biểu diễn định tính theo **likelihood × impact**, hoặc định lượng bằng mô hình có dữ liệu phù hợp. Trước khi giảm điểm, cần giải thích **cơ chế tác động** của control.

### 4.1. Controls giảm likelihood

Các biện pháp như xác thực mạnh, kiểm tra quyền truy cập, vá lỗ hổng, phân tách mạng và xác thực đầu vào có thể làm kịch bản tấn công khó xảy ra hoặc khó thành công hơn. Nhưng tác dụng phụ thuộc vào **phạm vi, cấu hình và khả năng bị bỏ qua**.

**Ví dụ:** bật MFA đúng trên các tài khoản quản trị tương tác có thể giảm khả năng chiếm quyền từ mật khẩu bị đánh cắp. Nếu kẻ tấn công **vẫn chiếm được** tài khoản có quyền xóa toàn bộ dữ liệu, hậu quả của sự kiện đó có thể chưa giảm đáng kể. Không được tự động giảm impact chỉ vì đã bật MFA.

### 4.2. Controls giảm impact

Phân vùng dữ liệu theo tenant, hạn chế quyền theo đối tượng, giới hạn tốc độ xuất dữ liệu, sao lưu độc lập và khôi phục đã diễn tập có thể giới hạn **số lượng dữ liệu bị ảnh hưởng**, **thời gian gián đoạn** hoặc **khả năng mất dữ liệu** khi sự kiện xảy ra.

**Ví dụ:** backup được kiểm thử với RPO/RTO phù hợp có thể giảm tổn thất do gián đoạn và mất dữ liệu trong kịch bản ransomware đã mô tả. Tuy nhiên, nó không tự động giảm nguy cơ lộ dữ liệu trước khi bị mã hóa và chưa bảo đảm phục hồi trong mọi thảm họa.

### 4.3. Controls chủ yếu giúp phát hiện hoặc phản ứng

SIEM, cảnh báo, trực ứng cứu, playbook và cơ chế cô lập có thể giúp phát hiện sớm và giảm thời gian tác động. **Một cảnh báo không được xử lý** khó được coi là bằng chứng kiểm soát làm giảm hậu quả. Đánh giá cần xem cả khâu phát hiện, tới đúng người, phản ứng và kết quả.

| Control minh họa | Phần rủi ro có thể tác động | Bằng chứng tối thiểu có ích | Giới hạn cần lưu ý |
| --- | --- | --- | --- |
| MFA quản trị | Giảm likelihood của một số kịch bản chiếm tài khoản. | Danh sách tài khoản thuộc phạm vi, policy trên môi trường đích, test đường đăng nhập/ngoại lệ. | Session hijacking, tài khoản máy và đường bypass có thể cần control riêng. |
| Object-level authorization | Giảm likelihood truy cập trái phép; có thể giảm phạm vi dữ liệu khi có sự cố khác. | Test theo vai trò và tenant trên endpoint/phiên bản thực tế; đối chiếu inventory. | Endpoint export và luồng batch có thể chưa được bao phủ. |
| Phân đoạn mạng | Có thể giảm khả năng lan truyền và blast radius. | Cấu hình kết nối, kiểm thử phân đoạn và đường phụ thuộc. | Credential chung hoặc control plane có thể vượt ranh giới. |
| Rate limit và quota | Giảm khả năng tài nguyên bị chiếm dụng; giới hạn ảnh hưởng từ một nguồn. | Stress test, thông số thực tế, tỷ lệ chặn nhầm và giám sát. | DDoS phân tán, tải nền cao hoặc quá tải phụ thuộc sâu hơn. |
| Backup tách miền lỗi | Có thể giảm impact mất dữ liệu/gián đoạn sau sự cố. | Restore drill, đo RTO/RPO, kiểm tra toàn vẹn và quyền khôi phục. | Sao lưu có thể nhiễm lỗi logic, thiếu dữ liệu hoặc cùng bị xóa. |
| Log, alert và on-call | Phát hiện sớm và hỗ trợ giảm thời gian hậu quả. | Kiểm thử alert, timeline sự cố, kết quả diễn tập phản ứng. | Cảnh báo nhiều nhưng không ai phản hồi thì tác dụng thực tế thấp. |

**Nguyên tắc:** phân biệt một control **đã được thiết kế**, **đã triển khai**, **đang hoạt động** và **có bằng chứng hiệu quả**. Bốn mức này không tương đương nhau.

## 5. Quy trình đánh giá current residual risk theo bằng chứng

Một quy trình làm việc có thể áp dụng cho từng dòng trong risk register:

### Bước 1 — Xác định kịch bản và tiêu chí đánh giá

Viết rõ sự kiện, hệ quả CIA/nghiệp vụ, phạm vi, thời kỳ và điều kiện. Chọn phương pháp đánh giá đã được tổ chức phê duyệt; ví dụ thang likelihood/impact 1–5 với tiêu chí riêng cho từng cấp.

Nếu không có tiêu chí chung, hai nhóm có thể đưa ra “cao” và “thấp” cho cùng một tình huống mà không thể đối chiếu.

### Bước 2 — Ước lượng inherent risk có ghi giả định

Xác định hậu quả nếu sự kiện xảy ra và khả năng xảy ra **trong mô hình chưa tính các controls được lựa chọn**. Inherent risk giúp nhìn rõ nhu cầu bảo vệ ban đầu và mức độ phơi lộ, nhưng đây là **giả định phân tích**, không phải một trạng thái thực nghiệm có thể quan sát trực tiếp.

Không nhất thiết phải gỡ control khỏi môi trường để đo inherent risk. Có thể dùng threat model, BIA, lịch sử sự cố, sơ đồ kiến trúc và chuyên gia để ước lượng theo giả định đã nêu.

### Bước 3 — Liệt kê và kiểm tra controls hiện có

Với từng control, ghi rõ:

- **Control ID, owner, operator, phạm vi áp dụng** và mục tiêu xử lý kịch bản.
- **Hiệu lực thiết kế (design effectiveness):** nếu vận hành như thiết kế, có xử lý đúng nguyên nhân/hậu quả không?
- **Hiệu lực vận hành (operating effectiveness):** có hoạt động đúng trên phiên bản/môi trường và trong khoảng thời gian đang đánh giá không?
- **Tình trạng phát hiện, ngoại lệ, lỗi công cụ và mức bao phủ** thực tế.
- **Bằng chứng** còn hiệu lực và các giả định chưa được xác minh.

Một control “đã mua”, “đang cấu hình” hoặc “dự kiến triển khai” không được tự động tính như đã vận hành thành công.

### Bước 4 — Ước lượng likelihood và impact còn lại

Dựa trên cơ chế thực tế và evidence, xem xét kịch bản còn có thể xảy ra ra sao và hậu quả nếu xảy ra đã được giới hạn đến mức nào. Ghi **lý do từng mức** thay đổi hoặc không thay đổi.

Khi bằng chứng thiếu, có thể đưa ra khoảng, kết luận tạm thời, hoặc giữ mức đánh giá thận trọng theo chính sách. **Không coi việc chưa thấy sự cố là chứng cứ rủi ro bằng 0**.

### Bước 5 — So sánh với tiêu chí và quyết định xử lý

Đối chiếu residual risk với risk appetite, tolerance và nghĩa vụ áp dụng. Nếu vượt ngưỡng, xác định phương án xử lý bổ sung, người chịu trách nhiệm, hạn hoàn tất và cách kiểm chứng. Nếu trong ngưỡng, người có thẩm quyền có thể đưa ra quyết định chấp nhận hoặc tiếp tục giám sát theo chính sách.

### Bước 6 — Lưu kết luận và lịch đánh giá lại

Kết quả phải chỉ rõ **đang đánh giá thời điểm nào, phiên bản nào, bằng chứng nào, điều gì chưa kiểm chứng, ai có quyền quyết định và lúc nào phải đánh giá lại**. Mọi thay đổi đáng kể về tài sản, lỗ hổng, dữ liệu, controls hoặc sự cố thực tế có thể làm kết luận cũ mất hiệu lực.

## 6. Ví dụ chấm điểm định tính trước và sau kiểm soát

Giả sử tổ chức dùng thang **Likelihood (L) 1–5** và **Impact (I) 1–5** đã định nghĩa, cùng ma trận risk rating được phê duyệt. Ví dụ dưới đây **chỉ minh họa việc ghi nhận lập luận**; nhãn rủi ro cuối cùng phải theo đúng ma trận của tổ chức.

| Trạng thái | Likelihood | Impact | Lập luận | Mức risk minh họa |
| --- | :---: | :---: | --- | --- |
| **Inherent** | 4 | 5 | Nếu không có phân quyền theo đối tượng, người dùng có thể đọc dữ liệu tenant khác; hậu quả lộ dữ liệu nhạy cảm rộng. | Rất cao |
| **Current residual** | 2 | 5 | Đã có authorization tập trung, test đa vai trò trên API chính; còn tuyến export chưa kiểm tra, nên khả năng giảm nhưng hậu quả khi lộ dữ liệu quy mô lớn chưa được chứng minh là thấp hơn. | Cao |
| **Target residual** | 1 (mục tiêu) | 4 (mục tiêu có điều kiện) | Dự kiến kiểm tra toàn bộ tuyến export, hạn chế bulk export và chứng minh phạm vi dữ liệu bị giới hạn; chưa được tính là đã đạt. | Trung bình theo mục tiêu |

Các mức L/I và nhãn trong bảng là **giá trị giả lập cho giảng dạy**, không phải kết quả đo từ một hệ thống thật. Không được quy đổi “4 × 5 = 20” thành xác suất 20% hay tổn thất 20 đơn vị tiền. Điểm số thứ bậc chỉ có ý nghĩa **trong phương pháp chấm điểm và các ngưỡng đã duyệt**; việc nhân hai nhãn thứ bậc không tự biến chúng thành phép đo định lượng.

### Trường hợp không nên hạ Impact

Nếu chỉ bổ sung **MFA** cho tài khoản quản trị nhưng người có quyền sau khi đăng nhập vẫn có thể xóa toàn bộ dữ liệu, MFA có thể giảm khả năng kẻ tấn công chiếm tài khoản; hậu quả *khi việc chiếm tài khoản vẫn xảy ra* có thể vẫn cấp 5. Chỉ giảm Impact khi control mới **chứng minh có thể giới hạn hậu quả**, chẳng hạn quyền xóa được tách, có xác nhận độc lập, và dữ liệu phục hồi được trong kịch bản liên quan.

### Tại sao không “trừ điểm” máy móc?

Nếu có 5 controls, không thể mặc định giảm 5 điểm rủi ro: nhiều controls có thể **phụ thuộc cùng cơ chế**, thiếu bao phủ hoặc bị vô hiệu đồng thời. Một API gateway và một WAF cùng đặt trước ứng dụng có thể cùng bị bỏ qua qua một endpoint trực tiếp; hai báo cáo “PASS” có thể cùng kiểm tra một đường đi mà bỏ sót đường khác.

## 7. Một cách định lượng residual risk khi đủ dữ liệu

Đối với một kịch bản được định nghĩa rõ, tổ chức có thể mô hình hóa **tổn thất kỳ vọng** từ xác suất/tần suất và hậu quả có điều kiện. Trong mô hình cực kỳ đơn giản với **tối đa một sự kiện trong một năm**:

\[
\mathbb{E}[L_{\mathrm{năm}}]
=P(\text{sự kiện trong năm})\times\mathbb{E}[\text{tổn thất}\mid\text{sự kiện}]
\]

Ví dụ minh họa, giả sử:

| Thành phần | Trước khi tính control | Sau khi tính control có bằng chứng |
| --- | ---: | ---: |
| Xác suất sự kiện xảy ra trong năm (giả định) | 20% | 5% |
| Tổn thất trung bình *nếu* xảy ra (giả định) | 400 triệu đồng | 150 triệu đồng |
| Giá trị tổn thất kỳ vọng đơn giản | 80 triệu đồng/năm | 7,5 triệu đồng/năm |

Theo các giả định đó, mô hình cho thấy mức kỳ vọng giảm **72,5 triệu đồng/năm**. Tuy nhiên:

- Các xác suất và tổn thất trong ví dụ **được đặt ra để minh họa**, không phải số liệu khảo sát hay bảo đảm.
- Nếu có thể xảy ra **nhiều lần/năm**, mô hình cần tần suất và phân phối mức tổn thất phù hợp.
- Sự cố có hậu quả rất lớn nhưng hiếm gặp có thể không được phản ánh đầy đủ bằng **giá trị kỳ vọng trung bình**.
- Các ước lượng phụ thuộc nhau, độ lệch thu thập dữ liệu và giả định khả năng kiểm soát cần được đánh giá.
- Risk appetite có thể không cho phép hậu quả nhất định **dù tổn thất kỳ vọng thấp**.

Nên trình bày **khoảng ước tính hoặc kịch bản**, đơn vị, thời hạn, giả định và độ tin cậy khi dữ liệu không đủ vững. Một con số “7,5 triệu” được tính đúng từ đầu vào tự đoán vẫn không trở thành bằng chứng mạnh về residual risk.

## 8. Đánh giá chất lượng bằng chứng để xác nhận residual risk

Security assurance đòi hỏi phân biệt lời khẳng định, lập luận và bằng chứng:

**Claim:** “Với bản phát hành 2.8 của Invoice API và các endpoint được đánh giá, rủi ro truy cập hóa đơn xuyên tenant còn ở cấp X theo tiêu chí của tổ chức.”

**Argument:** “Kiểm tra quyền theo đối tượng áp dụng tại tầng service; quyền được gắn với tenant của principal từ nguồn tin cậy; những đường truy cập liên quan được kiểm thử; phát hiện chưa xử lý và giới hạn đều được liệt kê.”

**Evidence:** API inventory, chính sách authorization, kết quả test chéo tenant, code review, cấu hình bản triển khai, log, hồ sơ ngoại lệ và retest các phát hiện.

### Một bằng chứng có giá trị cần đáp ứng điều gì?

| Thuộc tính | Câu hỏi cần đặt | Ví dụ bằng chứng chưa đủ |
| --- | --- | --- |
| **Liên quan** | Test có thật sự kiểm tra điều kiện của claim/rủi ro không? | Unit test parser được dùng để chứng minh authorization. |
| **Bao phủ** | Bao nhiêu endpoint, tài khoản, tenant, vùng và đường dữ liệu đã được xét? | Chỉ kiểm tra API đọc, bỏ qua export/batch. |
| **Nguồn gốc** | Ai tạo, công cụ nào chạy, kết quả gốc ở đâu? | Ảnh chụp “green” không có test report. |
| **Tính mới** | Bằng chứng gắn với phiên bản, cấu hình, thời điểm nào? | Test cũ trước khi thay thư viện IAM. |
| **Tính tái hiện** | Có dữ liệu đầu vào, bước chạy và tiêu chí thành công không? | Nhận định chủ quan “đã thử và ổn”. |
| **Độ độc lập** | Người đánh giá có đủ năng lực và phù hợp với mức rủi ro không? | Người sửa lỗi tự duyệt kết luận cho rủi ro cao mà không review. |
| **Tính toàn vẹn** | Hiện vật được lưu, bảo vệ khỏi sửa đổi và xử lý bí mật phù hợp không? | File log bị ghi đè, mất mốc thời gian hoặc lộ thông tin nhạy cảm. |
| **Giới hạn** | Có ghi lại điều chưa kiểm tra, giả định và ngoại lệ không? | Dashboard báo PASS mà không đề cập luồng chưa có coverage. |

**Đánh giá thiết kế** trả lời control có khả năng xử lý rủi ro nếu hoạt động như dự định; **đánh giá vận hành** trả lời nó có thật sự hoạt động trong khoảng thời gian và phạm vi cần chứng minh không. Cả hai có thể cần thiết cho một kết luận residual risk đáng tin.

### Phân loại khoảng trống bằng chứng

- **Control chưa được triển khai:** không được tính như hiện hành.
- **Đã triển khai nhưng chưa kiểm tra:** hiệu lực còn chưa chắc chắn; ghi evidence gap.
- **Đã kiểm tra một phần:** chỉ có thể suy luận trong phạm vi đó, không suy rộng.
- **Có test không đạt hoặc có phát hiện mở:** đưa kết quả trái chiều vào đánh giá, gắn owner và hạn xử lý.
- **Có bằng chứng cũ sau thay đổi lớn:** xem xét lại tính hợp lệ; nếu mất hiệu lực thì phải kiểm chứng mới.

Kết quả bảo mật không được làm đẹp bằng cách **bỏ những bằng chứng bất lợi** khỏi hồ sơ đánh giá.

## 9. Tình huống thực hành: phân quyền đa tenant

Một dịch vụ SaaS quản lý hóa đơn cho hàng trăm doanh nghiệp. API có các luồng xem, sửa và xuất báo cáo hóa đơn. Nguy cơ là người dùng tenant A tìm cách đọc hóa đơn tenant B do thiếu kiểm tra quyền đối tượng.

### Bước 1 — Xác định rủi ro trước xử lý

**Tài sản:** hóa đơn chứa thông tin giao dịch thương mại và dữ liệu liên hệ.

**Sự kiện:** một người dùng đã xác thực gửi ID hóa đơn không thuộc tenant và nhận về dữ liệu của doanh nghiệp khác.

**Giả định ban đầu:** không có object-level authorization đáng tin ở service, nên hậu quả có thể lan trên nhiều đối tượng. Chấm điểm inherent risk theo tiêu chí tổ chức với ranh giới và mức không chắc chắn được ghi rõ.

### Bước 2 — Xác minh controls hiện có

Nhóm đã triển khai:

1. Xác thực người dùng qua hệ thống danh tính.
2. Authorization theo tenant và đối tượng tại tầng xử lý nghiệp vụ.
3. Integration tests cho truy cập đúng quyền và truy cập chéo tenant ở API đọc/sửa.
4. Log và phát hiện mẫu truy cập bất thường; giới hạn số yêu cầu theo chính sách.

**Bằng chứng:** code review, kết quả integration tests gắn với commit, cấu hình production và đối chiếu API inventory. Tuy nhiên, API xuất báo cáo vừa bổ sung chưa được test với dữ liệu tenant khác. Như vậy, trạng thái hiện tại có **coverage gap**; không thể tuyên bố rủi ro của *mọi* đường đọc hóa đơn đã được giảm như nhau.

### Bước 3 — Đánh giá current residual risk

Theo ví dụ thang mức ở mục 6, kịch bản tổng hợp có thể có **likelihood thấp hơn inherent** do các controls đã kiểm chứng trên API chính. Impact vẫn **cao** nếu một đường đọc diện rộng bị khai thác. Nếu tuyến export chưa kiểm tra có phạm vi rất rộng, mức rủi ro còn lại có thể vẫn vượt ngưỡng của tổ chức.

Không được tự coi API export có phân quyền đúng chỉ vì API xem đã qua test. Cũng không được kết luận đã xảy ra lộ dữ liệu chỉ từ sự tồn tại của khoảng trống kiểm thử; đánh giá rủi ro tiềm năng và điều tra sự cố thực tế là hai nhiệm vụ khác nhau.

### Bước 4 — Đề xuất và chứng minh xử lý bổ sung

Nhóm phát triển đưa authorization cho luồng export về cùng điểm kiểm soát tin cậy; thêm negative tests cho các vai trò và tenant, kiểm tra bulk download, giới hạn bản ghi cho phép và cập nhật inventory. Nhóm assurance kiểm tra test report cùng cấu hình trên phiên bản triển khai. Nếu phát hiện lỗi đã được sửa, cần **retest** và lưu dấu kết quả.

Sau khi có bằng chứng, risk assessor có thể **đánh giá lại likelihood**, và chỉ giảm impact nếu chứng minh phạm vi dữ liệu hoặc hậu quả bị giới hạn. Risk owner xem lại residual risk dựa trên kết quả mới. Một PR đã merge hoặc ticket chuyển “Done” không tự làm thay đổi mức residual risk được xác nhận.

### Bước 5 — Ghi nhận giới hạn và kích hoạt đánh giá lại

Ví dụ giới hạn: các batch job do hệ thống nội bộ chạy được đánh giá theo kịch bản riêng; API mới phát hành phải đi qua inventory và regression tests; đổi mô hình tenant hoặc cơ chế identity là trigger đánh giá lại.

## 10. Tình huống thứ hai: ransomware và khôi phục dữ liệu

Giả sử một tổ chức lưu hồ sơ nghiệp vụ quan trọng trên máy chủ và object storage. Kịch bản là mã độc chiếm quyền quản trị, mã hóa dữ liệu đang dùng và xóa được một số bản sao.

| Thành phần | Trước cải thiện | Sau kiểm soát được kiểm chứng |
| --- | --- | --- |
| **Khả năng xâm nhập/lan truyền** | Quyền quản trị rộng, mạng ít phân đoạn. | Quyền tối thiểu, MFA phù hợp, phân đoạn và kiểm tra đường di chuyển ngang. |
| **Khả năng phá hủy backup** | Bản sao dùng chung credential với hệ thống chính. | Bản sao tách miền lỗi, quyền xóa hạn chế, bảo vệ tính bất biến khi thích hợp. |
| **Thời gian gián đoạn** | Chưa có runbook hoặc diễn tập. | Runbook và diễn tập phục hồi đầu cuối có đo RTO. |
| **Mức mất dữ liệu** | Chưa xác định điểm phục hồi thực tế. | Restore drill chứng minh RPO trong kịch bản đã xét. |
| **Bằng chứng** | Chỉ có ảnh cấu hình “backup enabled”. | Log backup, thử khôi phục, đối soát dữ liệu, thời gian thực hiện và phát hiện còn lại. |

Khi controls hoạt động, **likelihood của một số đường tấn công có thể giảm**, và **impact của mất dữ liệu/gián đoạn có thể giảm**. Nhưng kịch bản **đánh cắp dữ liệu trước khi mã hóa** có thể vẫn giữ impact cao. Do đó cần tách hoặc cập nhật **nhiều kịch bản**, tránh một điểm residual risk duy nhất che mất hậu quả riêng.

**RTO (Recovery Time Objective)** là mục tiêu thời gian phục hồi quy trình trong kịch bản xác định; **RPO (Recovery Point Objective)** là mức mất dữ liệu/độ lùi điểm phục hồi có thể chấp nhận. Backup chạy thành công không chứng minh hai mục tiêu này đạt; phải có bằng chứng từ khôi phục được thử nghiệm và đánh giá được dữ liệu sau restore.

## 11. Quyết định xử lý hoặc chấp nhận rủi ro còn lại

Sau khi có kết luận, risk owner hoặc cấp được ủy quyền chọn hành động theo chính sách. Những phương án thường gặp:

| Phương án | Áp dụng khi nào? | Lưu ý assurance |
| --- | --- | --- |
| **Giảm rủi ro (mitigate)** | Bổ sung/sửa controls để giảm likelihood hoặc impact. | Yêu cầu bằng chứng triển khai và retest trước khi xác nhận residual risk mới. |
| **Tránh rủi ro (avoid)** | Dừng hoặc thay đổi hoạt động gây rủi ro không thể chấp nhận. | Xác minh đường xử lý rủi ro đã thực sự được loại bỏ trong phạm vi xác định. |
| **Chia sẻ/chuyển giao một phần hậu quả (share/transfer)** | Dùng hợp đồng, bảo hiểm hoặc cơ chế phân chia nghĩa vụ theo chính sách. | Không tự loại bỏ trách nhiệm, hậu quả phi tài chính hay rủi ro kỹ thuật. |
| **Chấp nhận rủi ro (accept)** | Phần rủi ro nằm trong tiêu chí và được cấp có thẩm quyền phê duyệt, hoặc có ngoại lệ được phê duyệt theo quy trình. | Ghi lý do, phạm vi, mức rủi ro, điều kiện giám sát và thời điểm đánh giá lại. |

**Không phải rủi ro nào cũng có thể được chấp nhận bằng văn bản.** Có những nghĩa vụ pháp lý, hợp đồng, yêu cầu bảo vệ con người hoặc chính sách bắt buộc không cho phép miễn trừ theo cách đó. Quy trình chấp nhận phải kiểm tra các ràng buộc áp dụng và quyền hạn người phê duyệt.

### Một hồ sơ risk acceptance có trách nhiệm

Tối thiểu nên có:

- **Risk ID, kịch bản, tài sản, phạm vi, phiên bản và thời gian** đánh giá.
- **Current residual risk** và tiêu chí/giới hạn liên quan; lý do tại sao chưa thể loại bỏ hết.
- **Controls đang hiệu lực**, evidence, phát hiện và các giới hạn chưa được kiểm chứng.
- **Lý do quyết định** và lựa chọn thay thế đã xem xét, bao gồm tác động tới người liên quan.
- **Biện pháp giảm thiểu tạm thời**, người thực hiện, hành động tiếp theo và deadline khi phù hợp.
- **Người có thẩm quyền phê duyệt**, ngày quyết định, thời hạn hiệu lực, điều kiện tái thẩm định.
- **Sự kiện kích hoạt đánh giá lại:** xuất hiện exploit, sự cố, dữ liệu mới, thay đổi hệ thống hoặc control mất hiệu lực.

Không nên coi một email “đồng ý triển khai” hoặc ticket quá hạn là bằng chứng phê duyệt chấp nhận residual risk, trừ khi tài liệu đó thực sự đáp ứng quy trình và quyền hạn đã được tổ chức xác định.

### Phân biệt Risk owner và Control owner

**Control owner** chịu trách nhiệm bảo đảm một biện pháp bảo vệ có thiết kế, vận hành, bằng chứng và hành động khắc phục đúng phạm vi. **Risk owner** chịu trách nhiệm quản lý và quyết định về rủi ro trong thẩm quyền, bao gồm việc có chấp nhận rủi ro còn lại hay cần xử lý thêm. **Risk assessor/security assurance** cung cấp đánh giá và kiểm chứng bằng chứng; không tự động có quyền chấp nhận rủi ro.

## 12. Ghi nhận residual risk trong risk register

Risk register cần cho phép truy vết từ kết luận đến các điều kiện đã kiểm chứng, thay vì chỉ một ô “Risk = Medium”. Ví dụ YAML **minh họa cách tổ chức hồ sơ**:

~~~yaml
risk_id: RISK-INVOICE-TENANT-014
title: "Cross-tenant invoice disclosure"
assessment_date: "2026-11-28"
scope:
  service: "invoice-api"
  release: "2.8"
  paths:
    - "GET /invoices/{id}"
    - "PATCH /invoices/{id}"
    - "POST /invoices/export"
scenario: "Authenticated principal reads another tenant's invoice"
assessment_method: "Approved 1-5 likelihood-impact rubric"
inherent_risk:
  likelihood: 4
  impact: 5
  rating: "Very High (illustrative)"
current_residual_risk:
  likelihood: 2
  impact: 5
  rating: "High (illustrative)"
  rationale: "Core API controls tested; export path has coverage gap"
control_assessment:
  - id: "AUTHZ-INVOICE-01"
    owner_role: "Invoice Service Owner"
    operating_evidence: "authz-tests/invoice-api-2.8"
    coverage: "Core read and update paths"
    limitation: "Export path pending negative tests"
evidence_gaps:
  - "Object-level authorization for export not independently verified"
planned_treatments:
  - action: "Enforce export authorization and regression tests"
    treatment_owner_role: "Invoice Engineering Lead"
    due: "To be agreed"
target_residual_risk:
  rating: "Pending test and reassessment"
decision:
  status: "Pending authorized risk owner decision"
  risk_owner_role: "Customer Data Risk Owner"
reassessment_triggers:
  - "Export authorization fix released and retested"
  - "New tenant data access path"
  - "New evidence or security incident"
~~~

Các ID, đường dẫn, phiên bản, ngày và số liệu trong ví dụ là **giả định học tập**, không phải báo cáo audit có thật. Khi triển khai, thay bằng hiện vật thực, người được giao quyền và ngày đánh giá chính xác. Nếu hồ sơ chứa chi tiết lỗ hổng, phải bảo vệ quyền truy cập phù hợp.

### Đường truy vết cần nhìn thấy được

~~~mermaid
flowchart TD
    A["Risk scenario + Risk owner"] --> B["Impact / Likelihood theo tiêu chí"]
    B --> C["Security requirements và Controls"]
    C --> D["Control owner + Operator"]
    D --> E["Test / Audit / Evidence + giới hạn"]
    E --> F["Current residual risk có lập luận"]
    F --> G["Quyết định: giảm / tránh / chia sẻ / chấp nhận"]
    G --> H["Phát hiện, hành động, retest, theo dõi"]
    H --> F
~~~

Đây là mối liên kết căn bản để hoạt động **SECURITY_SECURITY_ASSURANCE** có thể giải trình qua phát triển, vận hành và kiểm toán.

## 13. Assurance liên tục: khi nào đánh giá lại rủi ro còn lại?

Residual risk là một **nhận định tại thời điểm và trong phạm vi xác định**. Sau thay đổi, số liệu cũ có thể không còn phản ánh hệ thống.

| Thay đổi hoặc tín hiệu | Vì sao phải xem lại? | Bằng chứng/hành động |
| --- | --- | --- |
| **Thêm endpoint hoặc luồng chia sẻ dữ liệu** | Có thể xuất hiện đường bypass, tài sản mới hoặc tăng blast radius. | Cập nhật inventory, threat model và integration/security tests. |
| **Thêm loại dữ liệu nhạy cảm hoặc tenant mới** | Impact tiềm năng và nghĩa vụ có thể thay đổi. | Data classification, phân tích phạm vi, đánh giá Impact mới. |
| **Phát hành IAM/library hoặc thay cấu hình** | Hiệu lực control cũ có thể bị thay đổi. | Change review, regression test, đối chiếu production. |
| **Phát hiện lỗ hổng/exploit mới** | Likelihood và giả định về cách tấn công có thể thay đổi. | Threat intelligence phù hợp, kiểm tra mức phơi lộ và kiểm soát. |
| **Sự cố thật hoặc diễn tập thất bại** | Cho thấy control/giả định trước đây chưa đúng hoặc chưa đủ. | Incident timeline, root-cause analysis, retest và re-rating. |
| **Thay nhà cung cấp, kiến trúc hoặc vùng triển khai** | Xuất hiện điểm lỗi chung, nghĩa vụ và phụ thuộc mới. | Sơ đồ cập nhật, review shared responsibility, thử failover. |
| **Ngoại lệ hết hạn hoặc phát hiện quá hạn** | Mức phơi lộ tăng hoặc biện pháp tạm không còn hợp lệ. | Escalation, quyết định rủi ro mới, yêu cầu khắc phục. |
| **Bằng chứng hết hạn hoặc mất tính toàn vẹn** | Không còn cơ sở chắc chắn để dùng mức residual risk trước. | Thu lại evidence, điều chỉnh trạng thái đánh giá. |

### Tích hợp vào phát triển và vận hành

Ở giai đoạn thiết kế, xác định risk scenario và mục tiêu xử lý. Trong phát triển, liên kết security requirements với controls và regression tests. Trước phát hành, đánh giá các thay đổi có ảnh hưởng risk và ghi quyết định. Trong production, dùng telemetry, cảnh báo, kết quả kiểm tra cấu hình và sự cố để xác nhận controls còn hiệu lực. Sau audit hoặc phát hiện, cập nhật risk register cùng retest và quyết định rủi ro.

Không phải mọi commit đều cần đánh giá lại toàn bộ danh mục rủi ro. Điều quan trọng là có **cơ chế xác định phạm vi ảnh hưởng**, chủ sở hữu và kiểm chứng lại các claim bị thay đổi.

### Theo dõi mức rủi ro thay vì chỉ đếm controls

Các chỉ số hữu ích có thể là:

- Tỷ lệ các risk scenario trọng yếu có **owner, đánh giá hiện hành và evidence còn hiệu lực**.
- Số residual risk vượt ngưỡng, mức độ nghiêm trọng và tuổi tồn đọng của chúng.
- Tỷ lệ **planned treatments** được kiểm chứng và có điều chỉnh mức residual risk sau retest.
- Số **risk acceptance** hết hạn, thiếu phê duyệt hoặc thiếu điều kiện theo dõi.
- Số control có bằng chứng vận hành không đạt, coverage gap hoặc cấu hình drift.
- Số thay đổi có tác động đáng kể nhưng chưa cập nhật risk assessment.

Không nên tối ưu “100% risks accepted” hoặc “100% controls green” như thành tích tự thân. Mục tiêu là **nhận diện và xử lý rủi ro dựa trên bằng chứng thực tế**.

## 14. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Đã có control nên residual risk bằng 0.” | Control chỉ làm giảm một số đường rủi ro trong phạm vi và điều kiện có bằng chứng. |
| “Rủi ro còn lại chính là rủi ro đã được chấp nhận.” | Phải **đánh giá trước**, rồi cấp có thẩm quyền mới quyết định chấp nhận hay xử lý. |
| “Mua scanner/backup/WAF đồng nghĩa đã giảm điểm risk.” | Chỉ tính hiệu lực khi đã triển khai, vận hành và có bằng chứng phù hợp. |
| “Kế hoạch triển khai giảm được current residual risk.” | Kế hoạch chỉ hỗ trợ **target residual risk**; chưa phải trạng thái hiện tại. |
| “Đã bật MFA nên likelihood và impact đều giảm.” | MFA thường chủ yếu ảnh hưởng một số kịch bản likelihood; impact cần lập luận riêng. |
| “Càng nhiều controls thì càng an toàn.” | Controls có thể trùng, phụ thuộc cùng điểm lỗi hoặc bỏ sót phạm vi. |
| “Không tìm thấy sự cố trong log nghĩa là không còn rủi ro.” | Log có giới hạn quan sát, thời gian lưu và khả năng phát hiện. |
| “Điểm CVSS hoặc scanner là residual risk của doanh nghiệp.” | Cần kết hợp phơi lộ thực tế, tài sản, hậu quả, kiểm soát và tiêu chí nghiệp vụ. |
| “Rủi ro Medium thì ai cũng được duyệt.” | Quyền phê duyệt theo governance, nghĩa vụ và risk appetite của tổ chức. |
| “Đóng ticket sửa lỗi nghĩa là risk giảm.” | Cần xác minh bản sửa, retest và cập nhật đánh giá có căn cứ. |
| “Risk register chỉ cần một con số.” | Phải có kịch bản, thời điểm, bằng chứng, giả định, owner và quyết định. |
| “Đã chấp nhận một lần thì không cần đánh giá lại.” | Acceptance có phạm vi, điều kiện, thời hạn và trigger xem lại theo chính sách. |

## 15. Checklist đánh giá residual risk cho một thay đổi

Khi một nhóm đề nghị phát hành thay đổi có liên quan bảo mật, có thể kiểm tra lần lượt:

1. **Risk scenario:** sự kiện bất lợi, tài sản và phạm vi phiên bản/môi trường đã được mô tả đủ rõ chưa?
2. **Impact/Likelihood:** phương pháp và tiêu chí nào đang dùng, có ghi giả định và độ không chắc chắn không?
3. **Controls:** từng biện pháp xử lý kịch bản gì, owner là ai, phạm vi tới đâu?
4. **Evidence:** controls có được kiểm tra trên bản phát hành và đường nghiệp vụ cần chứng minh không?
5. **Phát hiện:** có test không đạt, ngoại lệ, API chưa bao phủ hoặc bằng chứng hết hạn không?
6. **Current residual risk:** mức hiện tại được suy ra từ evidence thế nào, có phân biệt target sau kế hoạch không?
7. **Quyết định:** mức rủi ro trong tiêu chí hay cần thêm xử lý; ai có thẩm quyền phê duyệt?
8. **Theo dõi:** ai chịu trách nhiệm khắc phục, hạn và kết quả retest; điều kiện nào bắt buộc đánh giá lại?

Checklist này giúp một buổi release review hoặc cuộc audit đi từ **tuyên bố → bằng chứng → nhận định → quyết định**, không dừng ở danh sách controls đã có.

## 16. Bài tập và gợi ý giải

### Bài tập A — Đã bật MFA nhưng chưa kiểm tra đường dự phòng

Hệ thống quản trị cloud có MFA cho người dùng qua SSO. Một tài khoản quản trị khẩn cấp đăng nhập bằng cơ chế riêng chưa có evidence kiểm tra. Nhóm yêu cầu hạ residual risk của mọi kịch bản chiếm quyền quản trị xuống “Low”.

**Gợi ý:** Chưa đủ cơ sở cho toàn bộ phạm vi. Cần kiểm tra quyền và cơ chế bảo vệ tài khoản khẩn cấp, xác nhận chính sách giám sát và hậu kiểm, đánh giá các đường đăng nhập bị bỏ qua. Có thể kết luận riêng cho SSO nếu evidence phù hợp, còn kịch bản tài khoản khẩn cấp cần đánh giá độc lập.

### Bài tập B — Backup đã chạy nhưng restore thất bại

Rủi ro mất dữ liệu được chấm Inherent High. Nhóm vận hành báo backup tự động thành công mỗi ngày và đề xuất Current Residual Low. Trong diễn tập, không thể khôi phục dữ liệu do thiếu khóa giải mã.

**Gợi ý:** Báo cáo backup chưa đủ; diễn tập thất bại là bằng chứng **chống lại** claim về khả năng phục hồi. Phải đánh giá lại impact còn lại với điều kiện restore hiện tại, ghi phát hiện và thực hiện sửa quản lý khóa/khôi phục, sau đó diễn tập lại trước khi giảm rating.

### Bài tập C — Kế hoạch sửa lỗi có thời hạn

Một endpoint export cho phép truy cập vượt quyền ở production. Đội kỹ thuật sẽ phát hành bản sửa sau 10 ngày. Product owner muốn ghi “residual risk Medium” ngay vì đã có kế hoạch.

**Gợi ý:** Kế hoạch không làm giảm **current residual risk**; phải xem mức phơi lộ hiện tại, cân nhắc biện pháp giảm thiểu tạm (chặn endpoint, giới hạn truy cập), ghi người xử lý và hạn. Chỉ cập nhật mức sau khi biện pháp được triển khai và kiểm chứng. Nếu cần hoạt động khi rủi ro vượt tiêu chí, phải theo quy trình quyết định có thẩm quyền và kiểm tra nghĩa vụ bắt buộc.

### Bài tập D — Chấm điểm rủi ro bằng số

Một nhóm giả định xác suất xảy ra sự cố trong năm là 10%, tổn thất có điều kiện trung bình 200 triệu đồng. Sau cải tiến, nhóm ước lượng xác suất còn 5%, tổn thất còn 120 triệu đồng. Hãy so sánh tổn thất kỳ vọng trong mô hình tối đa một sự kiện/năm.

**Gợi ý:** Trước: 0,10 × 200 triệu = **20 triệu đồng/năm**. Sau: 0,05 × 120 triệu = **6 triệu đồng/năm**. Chênh lệch kỳ vọng **14 triệu đồng/năm** theo **các giả định đặt ra**. Để dùng ra quyết định thật, cần nguồn dữ liệu về xác suất/hậu quả, đánh giá tổn thất nghiêm trọng hiếm gặp và quy tắc risk appetite; kết quả không có nghĩa sự cố thật chỉ gây thiệt hại 6 triệu.

### Bài tập E — Rủi ro đã chấp nhận nhưng hệ thống thay đổi

Một ngoại lệ được phê duyệt cho dữ liệu nội bộ trong một môi trường staging. Sáu tháng sau môi trường đó chứa bản sao dữ liệu khách hàng production, nhưng quyết định acceptance cũ vẫn đang được dùng.

**Gợi ý:** **Phạm vi và impact đã thay đổi**. Quyết định cũ không mặc nhiên áp dụng; phải cập nhật data classification, threat scenario, controls và current residual risk, rồi trình cấp có thẩm quyền đánh giá lại trước khi dựa vào ngoại lệ đó.

## Kết luận

**Rủi ro còn lại** là mức rủi ro vẫn tồn tại **sau khi xét hiệu quả có bằng chứng của các biện pháp bảo vệ hiện hành trong phạm vi đánh giá**. Đánh giá đúng cần mô tả kịch bản, phân biệt likelihood và impact, kiểm tra thiết kế và hoạt động của controls, công khai bằng chứng thiếu hoặc trái chiều, so sánh với tiêu chí chấp nhận và ghi quyết định của người có thẩm quyền. Trong chương trình **SECURITY_SECURITY_ASSURANCE**, residual risk là kết quả phải được **chứng minh, theo dõi và cập nhật** qua các lần phát triển, kiểm thử, audit, khắc phục và thay đổi vận hành. Một bản sửa hoặc một chứng nhận không tự xóa rủi ro; chỉ lập luận gắn với evidence còn hiệu lực mới tạo cơ sở để tin vào mức rủi ro được công bố.

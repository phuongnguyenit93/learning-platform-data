# Impact (Mức độ tác động) trong quản lý rủi ro bảo mật

## 1. Impact trả lời câu hỏi gì?

Giả sử một dịch vụ thương mại điện tử có ba phát hiện:

- Một endpoint quản trị bị lỗi phân quyền, có thể cho phép đọc hồ sơ của khách hàng thuộc tenant khác.
- Một dịch vụ tạo đơn hàng có thể ngừng phục vụ trong giờ cao điểm do quá tải cơ sở dữ liệu.
- Một giao diện phụ hiển thị sai một biểu tượng khi người dùng không đăng nhập.

Cả ba đều là vấn đề cần xem xét, nhưng hậu quả nếu chúng thực sự xảy ra rất khác nhau. Không thể ưu tiên khắc phục hợp lý nếu chỉ dựa vào số lượng lỗi, nhãn mức độ của công cụ hoặc cảm nhận của người báo cáo.

**Impact (mức độ tác động)** là mức độ hậu quả đối với tổ chức và các bên liên quan **nếu một kịch bản rủi ro thực sự xảy ra**. Trong quản lý rủi ro bảo mật, impact giúp trả lời:

> Nếu sự kiện bất lợi diễn ra trong phạm vi đã xác định, những tài sản, hoạt động, con người và nghĩa vụ nào bị ảnh hưởng; hậu quả nghiêm trọng tới đâu, kéo dài bao lâu và bằng chứng nào hỗ trợ nhận định đó?

Ở chương **Quản lý rủi ro** của module **SECURITY_SECURITY_ASSURANCE**, đánh giá impact là bước nối **mục tiêu bảo mật** với **quyết định ưu tiên security controls, kiểm thử, audit và khắc phục phát hiện**. Mô tả module nhấn mạnh việc đánh giá có bằng chứng rằng hệ thống đáp ứng yêu cầu bảo mật; vì vậy, kết luận “impact cao” hay “impact thấp” cần có **kịch bản, giả định, tiêu chí và bằng chứng** thay vì chỉ có một con số.

**Phân biệt ngay từ đầu:**

- **Impact:** hậu quả lớn đến đâu *nếu sự kiện xảy ra*.
- **Likelihood:** khả năng hoặc tần suất sự kiện xảy ra trong khoảng thời gian và điều kiện đã xét.
- **Risk:** sự kết hợp giữa hậu quả và sự không chắc chắn về việc xảy ra sự kiện, theo phương pháp quản lý rủi ro được tổ chức áp dụng.

Một sự kiện có thể **rất hiếm nhưng impact rất lớn**, hoặc xảy ra thường xuyên với impact nhỏ. Không nên gọi impact là “khả năng xảy ra”, cũng không kết luận risk bằng cách nhìn impact đơn lẻ.

## 2. Bắt đầu từ kịch bản sự cố, không từ tên lỗ hổng

Nhãn “SQL injection”, “DDoS”, “mất backup” hoặc “truy cập trái phép” chưa đủ để đánh giá tác động. Cần mô tả chuỗi nguyên nhân và hậu quả trong ngữ cảnh cụ thể.

Một kịch bản có ích nên nêu:

1. **Tài sản hoặc quy trình bị ảnh hưởng:** dữ liệu, chức năng, dịch vụ, con người hay chuỗi cung ứng nào?
2. **Nguồn gây hại và sự kiện:** kẻ tấn công, lỗi người vận hành, sự cố hạ tầng, thay đổi phần mềm hoặc thảm họa nào?
3. **Điều kiện khai thác/thất bại:** quyền cần có, bề mặt tiếp cận, phụ thuộc, kiểm soát hiện hữu và phạm vi ảnh hưởng.
4. **Kết quả trực tiếp:** dữ liệu bị lộ/sửa/mất, chức năng ngừng hoạt động hoặc giao dịch không hoàn tất ra sao?
5. **Hậu quả nghiệp vụ:** thiệt hại tài chính, gián đoạn phục vụ, tác động tới khách hàng, nghĩa vụ pháp lý, uy tín và an toàn.
6. **Mốc thời gian và điều kiện phục hồi:** mất bao lâu để phát hiện, cô lập, khôi phục và xử lý hậu quả?

Ví dụ:

**Kịch bản mơ hồ:** “Có lỗi IDOR trong Invoice API, impact nghiêm trọng.”

**Kịch bản kiểm chứng được:** “Trong bản triển khai đang xét, một người dùng tenant A có thể thay đổi mã hóa đơn trong yêu cầu API để đọc hóa đơn của tenant B nếu thiếu kiểm tra quyền theo đối tượng. Phạm vi API có thể truy cập, số hồ sơ có nguy cơ, mức nhạy cảm của thông tin hóa đơn và khả năng phát hiện/thu hồi phải được kiểm chứng trước khi đánh giá hậu quả.”

Cách mô tả thứ hai tránh **tự suy diễn** rằng toàn bộ dữ liệu đã bị lộ, đồng thời chỉ ra thông tin còn thiếu. Impact có thể được ước lượng theo kịch bản có điều kiện và cần cập nhật khi bằng chứng thay đổi.

### Chuỗi nguyên nhân – sự kiện – hậu quả

~~~mermaid
flowchart LR
    A["Bối cảnh và tài sản cần bảo vệ"] --> B["Sự kiện rủi ro"]
    C["Điểm yếu / điều kiện"] --> B
    B --> D["Ảnh hưởng trực tiếp lên C / I / A"]
    D --> E["Gián đoạn và tổn thất nghiệp vụ"]
    E --> F["Hậu quả cho khách hàng / nghĩa vụ / uy tín"]
    G["Security controls"] -. "Ngăn ngừa, giới hạn, phát hiện, phục hồi" .-> B
    G -.-> D
    G -.-> E
~~~

**Lưu ý:** tác động có thể gồm nhiều tầng, nhưng cần tránh **đếm trùng cùng một tổn thất** ở nhiều tầng khi lượng hóa bằng tiền.

## 3. Các chiều tác động cần đánh giá

Không phải mọi hậu quả đều quy đổi được thành tiền. Một tổ chức nên xác định trước các **impact dimensions** phù hợp với nghiệp vụ, nghĩa vụ và mức chịu đựng rủi ro.

| Chiều tác động | Câu hỏi đánh giá | Ví dụ |
| --- | --- | --- |
| **Bí mật dữ liệu (Confidentiality)** | Dữ liệu nào có thể bị tiết lộ? Bao nhiêu bản ghi, chủ thể và đối tác bị ảnh hưởng? | Lộ hồ sơ khách hàng hoặc bí mật kinh doanh. |
| **Toàn vẹn dữ liệu/quy trình (Integrity)** | Thông tin hay kết quả nghiệp vụ có bị thay đổi trái phép? Có thể phát hiện và khôi phục dữ liệu đúng không? | Sửa số tiền thanh toán, đổi tài khoản nhận tiền. |
| **Sẵn sàng và tính liên tục (Availability)** | Dịch vụ nào bị gián đoạn, trong bao lâu, với bao nhiêu người dùng? | Không nhận đơn hoặc không đăng nhập được vào hệ thống. |
| **Tài chính** | Tổn thất trực tiếp, doanh thu/lợi nhuận bị ảnh hưởng, chi phí phục hồi, hợp đồng? | Chi phí ứng cứu, mất đơn hàng, chi phí xử lý yêu cầu. |
| **Khách hàng và đối tác** | Ai bị ảnh hưởng; họ mất dịch vụ, quyền riêng tư, tài sản hay cơ hội nào? | Khách hàng bị lừa đảo từ dữ liệu rò rỉ. |
| **Pháp lý, hợp đồng và tuân thủ** | Có nghĩa vụ báo cáo/khắc phục hoặc nguy cơ xử phạt theo quy định áp dụng? | Phải điều tra và thông báo sự cố theo nghĩa vụ liên quan. |
| **Uy tín và niềm tin** | Quan hệ với khách hàng, nhà đầu tư và đối tác bị ảnh hưởng đến mức nào? | Đối tác ngừng tích hợp; khách hàng chấm dứt hợp đồng. |
| **An toàn, sức khỏe, môi trường** | Hệ thống số có thể gây tổn hại thực tế tới con người hoặc môi trường? | Mất tính toàn vẹn dữ liệu điều khiển thiết bị. |
| **Chiến lược và vận hành dài hạn** | Sự cố gây chậm triển khai, mất năng lực cạnh tranh hoặc gián đoạn quy trình thiết yếu? | Dừng phát hành sản phẩm hoặc mất dữ liệu nghiên cứu quan trọng. |

Không phải kịch bản nào cũng có đủ mọi chiều trên. Hãy ghi **không áp dụng**, **chưa xác định** hoặc **có bằng chứng thấp** khi thích hợp, thay vì tự thêm hậu quả không có căn cứ.

### 3.1. Tác động trực tiếp và gián tiếp

**Trực tiếp** thường xảy ra ngay khi sự kiện tác động tới hệ thống: dừng API, bản ghi bị sửa, dữ liệu bị tải ra. **Gián tiếp** hình thành từ phản ứng và hệ quả: chi phí điều tra, khôi phục, bồi thường theo hợp đồng, khách hàng rời bỏ hoặc hoãn dự án.

Phân biệt này có ích khi thu thập bằng chứng và xác định thời gian của tổn thất. Chẳng hạn, một API ngừng 90 phút là diễn biến trực tiếp; giao dịch bị bỏ dở và công sức hỗ trợ sau đó là hậu quả có thể phát sinh. Tổ chức phải chỉ rõ mức tổn thất nào **đã xảy ra**, mức nào **ước tính nếu kịch bản xảy ra**, và mức nào **phụ thuộc các giả định bổ sung**.

### 3.2. Tác động tức thời và kéo dài

Việc khôi phục dịch vụ chưa chắc kết thúc hậu quả. Dữ liệu bị lộ có thể bị sao chép và sử dụng lâu dài; giao dịch sai cần đối soát; dữ liệu thiếu dấu vết kiểm toán có thể khiến điều tra kéo dài. Định nghĩa impact cần có **time horizon** phù hợp, ví dụ gián đoạn trong ngày, chi phí xử lý trong quý và tác động dài hạn lên quan hệ khách hàng.

Không nên dùng mặc định cùng một khoảng thời gian cho mọi kịch bản. Khoảng đánh giá và lý do chọn phải được ghi trong hồ sơ.

## 4. Tổ chức chọn thang Impact như thế nào?

Đánh giá định tính thường dùng 3, 4 hoặc 5 cấp. Quan trọng nhất là **các ngưỡng phải được mô tả trước và nhất quán trong tổ chức**, được người có thẩm quyền duyệt và phù hợp bối cảnh nghiệp vụ.

Ví dụ thang 5 cấp **minh họa**:

| Cấp | Nhãn | Hướng diễn giải hậu quả | Dấu hiệu có thể xem xét |
| :---: | --- | --- | --- |
| **1** | Không đáng kể | Hậu quả nhỏ, dễ khắc phục trong hoạt động bình thường. | Ảnh hưởng rất hẹp, không gián đoạn nghiệp vụ quan trọng; chi phí nằm trong vận hành thông thường. |
| **2** | Thấp | Suy giảm cục bộ; có thêm công xử lý nhưng ít ảnh hưởng tới mục tiêu chính. | Một nhóm nhỏ bị gián đoạn ngắn, phục hồi đơn giản, không có hệ quả đáng kể khác. |
| **3** | Trung bình | Hậu quả đáng kể ở một dịch vụ/đơn vị, cần điều phối khắc phục. | Gián đoạn nghiệp vụ hoặc ảnh hưởng dữ liệu trong phạm vi hạn chế; có chi phí và báo cáo nội bộ rõ rệt. |
| **4** | Cao | Đe dọa mục tiêu nghiệp vụ quan trọng hoặc nhiều bên liên quan. | Dịch vụ trọng yếu ngừng đáng kể, lộ dữ liệu nhạy cảm trên phạm vi lớn, chi phí phục hồi cao. |
| **5** | Nghiêm trọng | Hậu quả vượt mức chịu đựng thông thường, có thể làm gián đoạn hoạt động thiết yếu hoặc gây hại nghiêm trọng. | Tổn hại an toàn, mất năng lực phục vụ trọng yếu dài ngày, mất mát dữ liệu không thể phục hồi hoặc nghĩa vụ nghiêm trọng. |

Bảng trên là **mẫu phương pháp**, không phải tiêu chuẩn bắt buộc. Một ngân hàng, bệnh viện và ứng dụng thử nghiệm nội bộ sẽ có ngưỡng khác nhau. Tổ chức có thể gắn các mốc định lượng đã được phê duyệt cho từng chiều, như:

- Giá trị tổn thất tài chính theo ngưỡng tiền và thời kỳ.
- Thời gian gián đoạn của từng chức năng thiết yếu.
- Số lượng và mức nhạy cảm của hồ sơ hoặc người bị ảnh hưởng.
- Mức độ ảnh hưởng đến an toàn, nghĩa vụ hoặc cam kết hợp đồng.
- Khả năng khôi phục dữ liệu và thời gian tác động tồn lưu.

### 4.1. Chọn mức chung khi có nhiều chiều

Không nên cộng các nhãn 1–5 thành một con số như thể chúng là đơn vị đo vật lý. Cũng không nên tính trung bình khiến một hậu quả rất nghiêm trọng bị che bởi nhiều chiều có tác động thấp.

Một quy tắc dễ giải trình là **lấy cấp cao nhất trong các chiều có khả năng bị tác động, nếu chính sách đã chọn quy tắc đó**, rồi ghi rõ chiều quyết định mức cuối cùng. Tuy nhiên, với tổ chức có mô hình tổng hợp khác (chẳng hạn đánh trọng số), cần tuân thủ mô hình đã phê duyệt và giải thích tại sao phù hợp; trọng số không được che khuất hậu quả về an toàn hoặc nghĩa vụ không thể bù trừ.

Ví dụ kịch bản rò rỉ dữ liệu có tác động vận hành cấp 2, tài chính cấp 3 và bí mật dữ liệu cấp 4. Nếu dùng quy tắc cao nhất, **impact chung là 4**. Đây là đánh giá có điều kiện theo những chiều thực sự liên quan, không phải phép cộng 2 + 3 + 4.

### 4.2. Tính nhất quán và hiệu chuẩn

Để giảm sai lệch giữa người đánh giá:

1. Dùng **tiêu chí đã được duyệt trước** khi chấm từng kịch bản.
2. Ghi lại ví dụ tham chiếu cho mỗi cấp và mỗi loại quy trình.
3. Tham vấn các chức năng liên quan như business owner, finance, vận hành, privacy và an toàn khi cần.
4. Tổ chức hiệu chuẩn các ca điển hình giữa nhiều nhóm.
5. Lưu lý do chọn cấp và bằng chứng của giả định quan trọng.

Hai nhóm đánh giá cùng một loại sự cố với mức chênh lệch lớn cần giải thích khác biệt **phạm vi, khách hàng, thời gian, khả năng phục hồi hoặc dữ liệu liên quan**, thay vì chỉ chọn mức lớn hơn cho “an toàn”.

## 5. Các yếu tố làm Impact thay đổi

Ngay cả khi cùng một lỗ hổng, hậu quả có thể thay đổi theo ngữ cảnh:

| Yếu tố | Vì sao quan trọng? | Câu hỏi chứng cứ |
| --- | --- | --- |
| **Mức nhạy cảm và giá trị dữ liệu** | Tiết lộ thông tin công khai khác với lộ dữ liệu định danh hoặc bí mật kinh doanh. | Data classification, data inventory, chủ sở hữu dữ liệu đã phê duyệt. |
| **Số lượng và phạm vi đối tượng bị ảnh hưởng** | Một tenant bị tác động khác với truy cập xuyên toàn bộ tenant. | Access paths, giới hạn phân quyền, thống kê bản ghi/người dùng. |
| **Tính trọng yếu của quy trình** | Mất chức năng thanh toán có thể nghiêm trọng hơn mất chức năng báo cáo phụ. | Business Impact Analysis (BIA), SLA/SLO, thời điểm cao điểm. |
| **Thời gian diễn ra và phát hiện** | Gián đoạn càng lâu, hậu quả có thể càng tăng; dữ liệu bị sửa lâu ngày càng khó khôi phục. | Telemetry, log, thời gian phát hiện và cô lập. |
| **Phụ thuộc và lan truyền** | Sự cố một thành phần có thể ảnh hưởng nhiều sản phẩm hoặc đối tác. | Sơ đồ kiến trúc, dependency map, data lineage. |
| **Khả năng phục hồi** | Backup được kiểm thử khác với bản sao chưa từng restore hoặc không độc lập. | Restore drill, RTO/RPO, kết quả đối soát dữ liệu. |
| **Kiểm soát giới hạn phạm vi** | Phân đoạn mạng, quyền theo tenant, quota hoặc giới hạn giao dịch có thể giảm blast radius. | Cấu hình thực tế, test, giám sát và phạm vi bao phủ. |
| **Nghĩa vụ và điều kiện hợp đồng** | Hậu quả có thể khác theo khu vực, loại dữ liệu và cam kết. | Ý kiến pháp chế/compliance, tài liệu hợp đồng áp dụng. |
| **Bối cảnh thời gian** | Mất dịch vụ 30 phút ngày thường khác với 30 phút trong cao điểm có nhiều giao dịch. | Lịch kinh doanh, dữ liệu lưu lượng, lịch sử giao dịch. |

Một đánh giá impact có chất lượng cần cho phép người đọc thấy **vì sao các yếu tố trên dẫn tới kết luận**, thay vì chỉ ghi “High”.

### “Blast radius” – phạm vi lan truyền

Blast radius là mức độ sự cố có thể lan ra qua các tài sản, tenant, khu vực hoặc tổ chức. Thiết kế nhiều tenant, phụ thuộc chung, dùng chung credential hay chính sách truy cập quá rộng có thể tăng phạm vi. Một control cách ly dữ liệu theo tenant có thể làm giảm **impact của kịch bản bị khai thác** nếu bằng chứng cho thấy phạm vi bị giới hạn, dù nó không nhất thiết loại trừ khả năng xảy ra sự kiện ban đầu.

## 6. Đánh giá định lượng khi có đủ dữ liệu

Với một số kịch bản, tổ chức có thể ước lượng impact bằng tiền, số giao dịch, giờ ngừng hoạt động, số hồ sơ hay tỷ lệ khách hàng bị ảnh hưởng. Phép lượng hóa phải có **đơn vị, khoảng thời gian và nguồn dữ liệu** rõ ràng.

### 6.1. Mô hình chi phí đơn giản

Đối với sự cố gián đoạn, một cách phân tách minh họa:

\[
\text{Tổn thất ước tính}
= \text{Giá trị biên bị mất}
+ \text{Chi phí ứng cứu/phục hồi}
+ \text{Chi phí phát sinh khác}
\]

Trong đó **giá trị biên bị mất** là phần đóng góp kinh tế thực sự bị mất do giao dịch không thể phục hồi về sau, chứ không mặc định bằng tổng doanh thu bị trì hoãn. Nếu khách hàng đặt lại đơn vào ngày hôm sau, không nên coi toàn bộ doanh thu trong thời gian gián đoạn là tổn thất vĩnh viễn.

**Ví dụ minh họa:** một hệ thống đặt hàng ngừng hoạt động trong giờ cao điểm. Từ dữ liệu lịch sử, đội nghiệp vụ ước tính có **3.000 đơn** có nguy cơ không hoàn thành; **1.000 đơn** trong số đó được đặt lại sau khi phục hồi. Mỗi đơn không quay lại đóng góp khoảng **50.000 đồng** sau các chi phí biến đổi đã định nghĩa.

\[
\text{Giá trị biên mất} = (3.000 - 1.000) \times 50.000
= 100.000.000\text{ đồng}
\]

Nếu chi phí tăng thêm để ứng cứu/phục hồi là **20 triệu đồng**, chi phí hỗ trợ khách hàng tăng thêm là **10 triệu đồng**, và các hạng mục không bị đếm trùng, thì impact tài chính minh họa của kịch bản này khoảng **130 triệu đồng**.

Con số đó **chưa bao gồm** các ảnh hưởng khó lượng hóa như khách hàng mất niềm tin, nghĩa vụ hợp đồng hoặc sự cố lan sang hệ thống khác. Những phần chưa đo phải được ghi riêng, không được ngầm cho rằng bằng 0.

### 6.2. Phân biệt tổn thất có điều kiện với tổn thất kỳ vọng

**Impact** trong ví dụ là **mức tổn thất nếu kịch bản gián đoạn xảy ra theo giả định đã chọn**. Nếu xác suất kịch bản xảy ra trong một năm là 10%, một phép tính giá trị kỳ vọng đơn giản có thể là:

\[
130.000.000 \times 10\% = 13.000.000\text{ đồng/năm}
\]

Nhưng **13 triệu đồng/năm là giá trị tổn thất kỳ vọng trong mô hình đơn giản**, không phải mức impact của một lần xảy ra. Phép tính chỉ có ý nghĩa nếu xác suất, tần suất sự kiện, tổn thất có điều kiện và khoảng thời gian được xác định nhất quán; các sự kiện phụ thuộc và hậu quả đuôi dài có thể khiến mô hình đơn giản không phù hợp.

Không nên gán tùy tiện xác suất 10% chỉ để tạo một kết quả “có vẻ định lượng”. Khi thiếu dữ liệu, thang định tính có lập luận rõ ràng thường đáng tin hơn con số chính xác giả.

### 6.3. Phân tích khoảng và giả định

Một ước tính điểm duy nhất che giấu độ không chắc chắn. Khi cần, có thể xây dựng **kịch bản thấp – cơ sở – cao nhưng hợp lý**:

| Kịch bản | Giả định điển hình | Cách dùng |
| --- | --- | --- |
| **Thấp** | Phạm vi được cô lập sớm, phần lớn giao dịch phục hồi. | Hiểu hậu quả khi biện pháp giới hạn hoạt động tốt. |
| **Cơ sở** | Diễn biến phù hợp dữ liệu lịch sử hoặc tình huống đại diện. | Hỗ trợ quyết định và so sánh phương án. |
| **Cao có cơ sở** | Gián đoạn xảy ra đúng cao điểm, phụ thuộc chung bị ảnh hưởng, khó phục hồi hơn. | Kiểm tra sức chịu đựng và mức ưu tiên khắc phục. |

“Cao có cơ sở” không đồng nghĩa tưởng tượng mọi điều xấu nhất cùng xảy ra. Phải nêu **căn cứ thực tế và điều kiện cần để kịch bản mở rộng**. Nếu không thể xác định được khoảng, ghi rõ mức tin cậy thấp và nhu cầu thu thập thêm bằng chứng.

## 7. Impact với tính bí mật, toàn vẹn và sẵn sàng

Cùng một tài sản có thể có mức tác động khác nhau với từng thuộc tính trong bộ ba **CIA**.

### 7.1. Bí mật (Confidentiality)

Câu hỏi chính: *nếu dữ liệu bị đọc hoặc tiết lộ ngoài quyền, hậu quả là gì?* Cần xem xét độ nhạy, khả năng liên kết với các nguồn khác, số đối tượng, thời gian tiếp cận và khả năng thu hồi. Một file đã bị sao chép ra ngoài có thể **không thể thu hồi toàn bộ**, ngay cả khi quyền truy cập đã được khóa.

**Ví dụ:** API cung cấp lịch sử hóa đơn của một tenant. Nếu lỗi chỉ ảnh hưởng một bản ghi thử nghiệm đã vô danh hóa, hậu quả khác với lỗi cho phép tải dữ liệu định danh của nhiều khách hàng. **Mức impact phải phản ánh bằng chứng về phạm vi và tính chất dữ liệu**, không chỉ nhãn “IDOR”.

### 7.2. Toàn vẹn (Integrity)

Câu hỏi chính: *nếu dữ liệu hoặc quá trình xử lý bị sửa sai, điều gì sẽ xảy ra trước khi được phát hiện và sửa đúng?* Cần xét cơ chế đối soát, khả năng truy nguồn thay đổi, giao dịch không thể đảo ngược và sự lan truyền sang hệ thống khác.

**Ví dụ:** sửa sai địa chỉ giao hàng có thể gây giao hàng nhầm, trong khi sửa sai số tài khoản nhận tiền có thể dẫn tới chuyển tiền nhầm và hậu quả khó đảo ngược. Có bản sao backup chưa chắc đủ để khôi phục nếu không biết dữ liệu đúng tại thời điểm nào.

### 7.3. Sẵn sàng (Availability)

Câu hỏi chính: *nếu một chức năng hoặc dữ liệu không sử dụng được, hoạt động nào bị dừng, trong bao lâu và mức độ phục hồi ra sao?* Cần gắn impact với **BIA**, SLI/SLO, RTO/RPO khi phù hợp và đặc biệt với **giao dịch nghiệp vụ đầu cuối**, thay vì chỉ với tình trạng CPU hay máy chủ.

**Ví dụ:** mất API nhận đơn 20 phút giữa đêm có thể không tạo nhiều tổn thất ở một dịch vụ theo giờ; nhưng cùng 20 phút trong đợt bán hàng giới hạn số lượng có thể gây hậu quả đáng kể.

### 7.4. Không bỏ sót ảnh hưởng phối hợp

Một cuộc tấn công mã hóa dữ liệu có thể đồng thời gây **mất sẵn sàng** và **nghi ngờ mất toàn vẹn**. Một vụ chiếm tài khoản có thể vừa lộ dữ liệu, vừa sửa dữ liệu và làm gián đoạn dịch vụ. Khi đánh giá, tách các chiều để hiểu nguyên nhân và biện pháp xử lý, sau đó tổng hợp theo quy tắc đã thống nhất; tránh đếm trùng cùng một tổn thất.

## 8. Từ inherent impact đến residual impact

Đánh giá impact có thể xét hai trạng thái:

- **Inherent impact:** hậu quả có thể xảy ra theo kịch bản khi chưa tính các biện pháp kiểm soát được lựa chọn để làm giảm rủi ro, theo định nghĩa *inherent* của phương pháp tổ chức. Đây là mô hình giả định; cần nói rõ điều kiện nào đang được bỏ qua.
- **Residual impact:** hậu quả còn lại theo kịch bản sau khi tính đến **các controls đã được triển khai và có bằng chứng hiệu quả** trong phạm vi đánh giá.

Không phải mọi control đều giảm impact. Có control chủ yếu làm giảm **likelihood**, ví dụ một số biện pháp ngăn khai thác ban đầu. Control khác giảm **phạm vi hoặc thời gian hậu quả**, ví dụ phân đoạn tenant, giới hạn quyền, giảm thời gian phát hiện và khả năng khôi phục.

| Control | Có thể tác động phần nào? | Cần kiểm chứng gì? |
| --- | --- | --- |
| Xác thực mạnh và chặn hành vi đăng nhập không hợp lệ | Chủ yếu giảm khả năng chiếm tài khoản trong kịch bản phù hợp. | Phạm vi MFA, đường bypass, kết quả thử và tài khoản ngoại lệ. |
| Giới hạn quyền theo từng đối tượng/tenant | Có thể giảm phạm vi dữ liệu bị ảnh hưởng khi một quyền bị lạm dụng; đồng thời giảm khả năng thành công của hành vi vượt quyền. | Test truy cập chéo tenant, code path và cấu hình thực tế. |
| Phân đoạn mạng và giới hạn blast radius | Giảm khả năng lan truyền và phạm vi hậu quả trong một số kịch bản. | Sơ đồ phụ thuộc, chính sách thực tế, kiểm thử phân đoạn. |
| Phát hiện và phản ứng nhanh | Có thể giảm thời gian sự cố và hậu quả tiếp diễn nếu có quy trình ứng cứu hiệu quả. | Kết quả diễn tập, MTTD/MTTR được định nghĩa, timeline thực tế. |
| Backup và khôi phục được diễn tập | Có thể giảm mất dữ liệu và thời gian ngừng dịch vụ ở kịch bản phục hồi. | Kết quả restore, RTO/RPO, khả năng dùng dữ liệu sau phục hồi. |
| Công cụ chỉ báo cáo phát hiện nhưng không ai xử lý | Chưa đủ cơ sở để mặc định impact giảm. | Có owner, alert đến người trực, hành động và thời gian khắc phục đã được chứng minh không? |

### Không giảm điểm chỉ dựa vào kế hoạch

Những phát biểu như “sẽ bật MFA”, “đã mua dịch vụ chống DDoS”, “đang bổ sung backup” **không chứng minh residual impact đã giảm**. Phải phân biệt:

1. **Existing control:** đang triển khai, có bằng chứng còn hiệu lực.
2. **Planned control:** đã đề xuất hoặc đang thực hiện, chưa được tính như đã có hiệu quả.
3. **Assumed control:** được giả định trong kịch bản nhưng chưa kiểm chứng; cần làm rõ và giảm mức tin cậy của kết luận.

Sau khi sửa hoặc thay đổi control, cần chạy lại các phép kiểm tra liên quan và **đánh giá lại impact hoặc likelihood tùy cơ chế tác động thực tế**, không tự động giảm cả hai.

## 9. Tình huống thực hành: lộ hóa đơn giữa các tenant

Một nền tảng SaaS quản lý hóa đơn cho nhiều doanh nghiệp. API đọc hóa đơn sử dụng ID trong đường dẫn. Kiểm thử phát hiện một nhánh xử lý có thể bỏ qua bước kiểm tra tenant của principal.

### Bước 1 — Xác định phạm vi và bằng chứng hiện có

Nhóm thu thập:

- Kiểu dữ liệu trong hóa đơn: tên doanh nghiệp, mã số hóa đơn, hàng hóa/dịch vụ, giá trị giao dịch, thông tin liên hệ.
- Số tenant và hóa đơn thuộc nhánh API có vấn đề; có giới hạn phân trang, quyền hoặc rate limit hay không.
- Endpoint nào dùng chung đường xử lý; tài khoản và quyền gì là điều kiện để khai thác.
- Logging nào có thể cho biết yêu cầu truy cập trái phép đã xảy ra; có dấu hiệu exfiltration không.
- Nghĩa vụ hợp đồng hoặc xử lý dữ liệu liên quan, cần ý kiến của pháp chế/privacy khi áp dụng.

Không nên nhầm **“có thể đọc”** với **“đã có bằng chứng dữ liệu bị đọc”**. Khả năng hậu quả của kịch bản có thể vẫn nghiêm trọng, song hồ sơ phải tách **impact tiềm năng** khỏi **tổn thất thực tế đã xác nhận**.

### Bước 2 — Viết các chiều Impact

Ví dụ một bảng làm việc theo thang 1–5 **minh họa**, với điều kiện đánh giá đã nêu và có thể thay đổi theo bằng chứng:

| Chiều | Nhận định và căn cứ | Cấp sơ bộ |
| --- | --- | :---: |
| Bí mật dữ liệu | Hóa đơn chứa thông tin kinh doanh nhạy cảm; có khả năng truy cập giữa tenant. Chưa xác định hết phạm vi nhánh API. | **4** |
| Toàn vẹn | Phát hiện hiện tại chỉ ở luồng đọc; chưa có bằng chứng cho đường sửa hóa đơn. | **Chưa kết luận cho kịch bản sửa** |
| Sẵn sàng | Lỗi đọc hóa đơn không tự gây gián đoạn dịch vụ trong kịch bản đang xét. | **1** |
| Tài chính và hợp đồng | Có thể phát sinh chi phí điều tra và xử lý khách hàng; chưa đủ dữ liệu lượng hóa chính xác. | **3, sơ bộ** |
| Uy tín/khách hàng | Khách doanh nghiệp có thể mất niềm tin nếu dữ liệu giao dịch bị tiết lộ. | **3–4, cần hiệu chuẩn** |

Nếu chính sách dùng cấp **cao nhất có căn cứ**, impact sơ bộ là **4** do khả năng ảnh hưởng bí mật dữ liệu. Đây là **giá trị giả định của bài học**, không phải kết luận đối với một hệ thống thật. Cần mở các công việc xác minh phạm vi, kiểm tra các endpoint cùng cơ chế và xem lại ảnh hưởng pháp lý/hợp đồng.

### Bước 3 — Liên kết impact với hành động

Trong thời gian đánh giá, nhóm triển khai biện pháp giảm thiểu phù hợp như giới hạn tạm đường truy cập có rủi ro, sửa kiểm tra phân quyền và bổ sung kiểm thử chéo tenant. Security assurance phải xác định:

1. Có kết quả test **được phép và không được phép** trên toàn bộ endpoint thuộc phạm vi không?
2. Có bằng chứng phiên bản đã sửa **thực sự được triển khai** không?
3. Những đường truy cập phụ hoặc dữ liệu trong cache/export có được xem xét không?
4. Có bằng chứng nào cho thấy phạm vi bị giới hạn đủ để giảm mức impact giả định không?
5. Phần chưa biết và rủi ro còn lại có owner và người quyết định có thẩm quyền không?

Nếu sửa authorization làm hành vi vượt tenant không còn xảy ra theo phạm vi test, **likelihood của kịch bản khai thác có thể giảm**; chưa đủ lý do để khẳng định **impact nếu một vụ lộ dữ liệu vẫn xảy ra** đã giảm. Chỉ khi phạm vi dữ liệu bị ảnh hưởng có bằng chứng giới hạn hơn hoặc cách giảm hậu quả thực tế đã được chứng minh mới nên xem xét giảm impact có điều kiện.

### Bước 4 — Kết luận có giới hạn

Ví dụ một kết luận assurance phù hợp:

> “Impact tiềm năng của kịch bản đọc hóa đơn xuyên tenant được xếp cấp 4 theo tiêu chí bí mật dữ liệu đã chọn. Căn cứ là tính nhạy cảm của thông tin hóa đơn và khả năng truy cập qua nhánh API được xác nhận bằng kiểm thử. Quy mô bản ghi có thể tiếp cận và dấu hiệu truy cập thực tế vẫn đang xác minh; việc sửa phân quyền phải được retest trên phiên bản triển khai. Kết luận sẽ được cập nhật khi có bằng chứng mới.”

Kết luận này nêu được **điều biết, điều giả định, điều chưa biết và hành động tiếp theo**.

## 10. Tình huống đối chiếu: gián đoạn dịch vụ nhận đơn

Giả sử một dịch vụ nhận đơn hàng có kịch bản **database connection pool bị cạn**. Sự kiện có thể làm API tạo đơn timeout trong giờ cao điểm.

**Bằng chứng cần có:** thống kê lượng đơn theo giờ, tỉ lệ đơn được đặt lại sau gián đoạn, giá trị đóng góp kinh tế theo đơn, hợp đồng dịch vụ, hệ thống thanh toán và phụ thuộc, kết quả load test, lịch sử sự cố, năng lực failover và kết quả diễn tập restore.

Một cách đánh giá:

1. **Phạm vi:** chỉ API tạo đơn hay toàn bộ chức năng mua hàng? Có ảnh hưởng mọi vùng không?
2. **Thời gian:** gián đoạn 15 phút, 2 giờ hay cả ngày? Các phương án phục hồi đã được kiểm chứng chưa?
3. **Người dùng:** tỉ lệ giao dịch lỗi bao nhiêu, khách có thể đặt lại không?
4. **Hệ quả dữ liệu:** đơn thất bại có ghi nửa chừng và tạo sai lệch tồn kho/thanh toán không?
5. **Hậu quả tài chính:** phần giá trị biên không thể thu hồi, công ứng cứu, nghĩa vụ hợp đồng và các tác động khác.

Ví dụ cùng kịch bản mất database nhưng một hệ thống có **chế độ nhận đơn dự phòng đã được thử nghiệm** sẽ có hậu quả khác với hệ thống chỉ có backup chưa từng restore. Để lập luận residual impact giảm, phải chứng minh chế độ dự phòng có thể xử lý đủ luồng thiết yếu và dữ liệu nhất quán theo tiêu chí nghiệp vụ.

Không dùng trực tiếp nhãn mức độ CPU cao, số lỗi 500 hoặc thời gian downtime dự kiến để suy ra impact cấp 5 nếu không có **liên kết tới hậu quả nghiệp vụ**.

## 11. Hồ sơ Impact có thể kiểm toán và truy vết

Impact là một đầu vào quan trọng cho lựa chọn controls và ưu tiên kiểm chứng. Một đánh giá tốt cần được lưu cùng **risk scenario** và các quyết định liên quan. Mẫu YAML sau **chỉ minh họa cách ghi hồ sơ phân tích**, không phải cấu trúc metadata của bài học hay mẫu bắt buộc của tổ chức:

~~~yaml
risk_id: RISK-INVOICE-ACCESS-014
asset: "Invoice records across customer tenants"
scenario: "Authenticated user accesses another tenant's invoice"
scope:
  service: "invoice-api"
  release: "2.8"
  endpoints: ["GET /invoices/{id}"]
impact_method: "Qualitative 1-5; approved business rubric"
impact_time_horizon: "Incident and reasonable follow-up period"
impact_dimensions:
  confidentiality:
    level: 4
    rationale: "Commercially sensitive invoice content"
  integrity:
    level: null
    rationale: "Write paths are assessed separately"
  availability:
    level: 1
    rationale: "Read-only access flaw has no identified outage effect"
overall_impact:
  level: 4
  aggregation_rule: "Highest credible applicable dimension"
assumptions:
  - "A cross-tenant read path is reachable"
  - "The exposure scope is not yet fully bounded"
uncertainties:
  - "Maximum number of affected records"
  - "Evidence of actual unauthorized access"
evidence:
  - "authz-test/invoice-api-2.8"
  - "data-catalog/invoice-fields"
assessment_owner: "Invoice risk assessment lead"
business_reviewer: "Invoice data owner"
risk_decision_owner: "Authorized business risk owner"
review_triggers:
  - "Authorization fix is deployed and retested"
  - "New evidence changes affected scope"
  - "New API or sensitive invoice fields are added"
assessment_status: "Preliminary; evidence gaps open"
~~~

Trong thực tế, cần bổ sung **ngày đánh giá, phiên bản tiêu chí, người phê duyệt, liên kết hiện vật thật, trạng thái kiểm tra và lịch sử thay đổi**. Chỉ có đường dẫn hoặc tên báo cáo không chứng minh hiện vật tồn tại hay kết quả hợp lệ.

### Liên kết Impact vào Claim – Argument – Evidence

Trong security assurance, có thể ghi:

- **Claim (tuyên bố):** “Tác động tối đa có cơ sở của sự cố đọc hóa đơn xuyên tenant trong phạm vi đã phân tích là cấp 4 theo tiêu chí bí mật dữ liệu của tổ chức.”
- **Argument (lập luận):** “Hóa đơn chứa dữ liệu kinh doanh nhạy cảm; khả năng truy cập chéo tenant và phạm vi endpoint tạo ra hậu quả tương ứng; các giới hạn chưa được chứng minh vẫn được ghi rõ.”
- **Evidence (bằng chứng):** danh mục dữ liệu, thông tin số lượng tenant/bản ghi, kết quả kiểm thử đường truy cập, kiến trúc, log, chính sách phân loại và biên bản tham vấn Data owner.

Để một claim đáng tin, người đánh giá phải kiểm tra **evidence có hỗ trợ đúng lập luận không**, bằng chứng có đúng phiên bản/môi trường không, những gì đang được *giả định* và những lỗ hổng bằng chứng nào có thể làm thay đổi kết luận.

### Bảng bằng chứng: cái gì chứng minh được, cái gì chưa

| Bằng chứng | Hỗ trợ kết luận gì? | Không tự chứng minh điều gì? |
| --- | --- | --- |
| Data catalog, phân loại được duyệt | Độ nhạy, loại dữ liệu và yêu cầu bảo vệ trong phạm vi catalog. | Toàn bộ bản sao dữ liệu hoặc mọi đường truy cập đã được liệt kê. |
| Log truy cập có đủ độ tin cậy | Yêu cầu cụ thể đã được ghi nhận trong khoảng lưu trữ. | Không có truy cập trái phép ngoài phạm vi log hoặc trước thời điểm bật log. |
| Integration test truy cập chéo tenant | Hành vi của endpoint trong phiên bản, môi trường và case đã kiểm tra. | Mọi endpoint khác hoặc sản xuất với cấu hình khác đều an toàn. |
| BIA và thống kê giao dịch | Mức quan trọng nghiệp vụ, tải điển hình, hậu quả gián đoạn có cơ sở. | Tổn thất sẽ luôn đúng bằng ước tính trong mọi sự cố tương lai. |
| Kết quả restore/failover drill | Khả năng phục hồi trong kịch bản, phiên bản và cấu hình đã thử. | Khả năng phục hồi trong mọi loại thảm họa hay ở mọi thời điểm. |
| Phân tích pháp chế/compliance | Các nghĩa vụ và rủi ro pháp lý liên quan trong phạm vi xem xét. | Một mức phạt cụ thể chắc chắn sẽ xảy ra trong tương lai. |

## 12. Ai tham gia đánh giá và phê duyệt Impact?

Impact có cả yếu tố kỹ thuật và kinh doanh. Nếu chỉ giao cho công cụ quét lỗ hổng hoặc một kỹ sư tự quyết, dễ đánh giá sai hậu quả.

| Vai trò | Đóng góp vào Impact |
| --- | --- |
| **Business/process owner** | Chỉ rõ chức năng trọng yếu, ảnh hưởng khách hàng, thời điểm quan trọng và mức gián đoạn chấp nhận được. |
| **Data owner** | Xác nhận loại dữ liệu, độ nhạy, mục đích, số lượng/nhóm dữ liệu có thể bị ảnh hưởng. |
| **System/service owner** | Cung cấp kiến trúc, phụ thuộc, phiên bản, log, khả năng cô lập và phục hồi. |
| **Security/control owner** | Giải thích kịch bản, điều kiện khai thác, control, giới hạn bảo vệ và phát hiện. |
| **Finance, legal/privacy/compliance** | Hỗ trợ lượng hóa hậu quả hoặc nghĩa vụ khi phù hợp và đúng thẩm quyền. |
| **Risk owner** | Chịu trách nhiệm quản lý rủi ro và quyết định xử lý/chấp nhận trong quyền hạn tổ chức giao. |
| **Security assurance/assessor** | Kiểm tra cách áp tiêu chí, chất lượng bằng chứng, tính nhất quán và khoảng trống lập luận. |

**Người ghi đánh giá Impact không mặc nhiên là người được quyền chấp nhận rủi ro.** Rủi ro có tác động cao hoặc ảnh hưởng nhiều đơn vị có thể phải được trình cấp có thẩm quyền theo chính sách. Tổ chức nên xác định quyền phê duyệt, trách nhiệm tham vấn, thời hạn xem lại và đường leo thang trước khi phát sinh phát hiện.

### Khi có bất đồng về mức Impact

Ví dụ đội kỹ thuật cho rằng gián đoạn database là cấp 2 vì có thể khởi động lại trong 30 phút; bộ phận nghiệp vụ cho rằng cấp 4 do 30 phút đó nằm trong kỳ chốt thanh toán không thể lùi. Cách xử lý là:

1. Xác định cùng một **kịch bản, thời gian và phạm vi**.
2. Đối chiếu **BIA, giao dịch thực tế, điều kiện cam kết và khả năng phục hồi**.
3. Kiểm tra có nhầm giữa tác động trên máy chủ và hậu quả đối với quy trình nghiệp vụ không.
4. Áp dụng **rubric đã duyệt**; ghi mọi giả định khác nhau hoặc phân tích nhiều kịch bản nếu cần.
5. Chuyển tới người có thẩm quyền khi các yếu tố chưa thể được giải quyết bằng bằng chứng hiện có.

Mục tiêu của hiệu chuẩn là một đánh giá **có thể giải thích và tái kiểm tra**, không phải ép các nhóm đồng ý với một con số thiếu cơ sở.

## 13. Từ Impact đến quyết định xử lý rủi ro

Impact hỗ trợ ưu tiên, nhưng **không tự quyết định** có sửa ngay, chấp nhận hay chuyển giao rủi ro. Quyết định còn phụ thuộc likelihood, thời gian phơi lộ, mức rủi ro chấp nhận được, nghĩa vụ bắt buộc, hiệu quả controls, chi phí và các phương án xử lý.

Một quy trình ra quyết định nên:

1. **Xác định kịch bản và hậu quả** với các chiều Impact phù hợp.
2. **Đánh giá likelihood** theo phương pháp đã chọn và nêu độ không chắc chắn.
3. **Tổng hợp mức risk** theo tiêu chí/tolerance đã phê duyệt, tránh gắn nhãn severity của scanner trực tiếp làm Impact.
4. **Chọn phương án xử lý**: tránh hoạt động gây rủi ro, giảm bằng controls, chuyển giao một phần hậu quả tài chính nếu phù hợp, hoặc chấp nhận rủi ro còn lại trong thẩm quyền.
5. **Lập bằng chứng sau xử lý**: kiểm thử, quan sát, review thiết kế, xác nhận triển khai, retest và cập nhật phạm vi.
6. **Đánh giá lại** Impact/likelihood/residual risk khi có thay đổi hoặc bằng chứng mới.

Trong một số tình huống impact rất lớn, tổ chức có thể áp chính sách không cho phép chấp nhận rủi ro dù likelihood thấp. Việc này phụ thuộc **risk appetite, obligations và các ngưỡng bắt buộc** được phê duyệt; không tự suy ra từ phép nhân điểm trong ma trận.

### Phân biệt Impact, risk rating và vulnerability severity

| Khái niệm | Dùng để đánh giá | Sai lầm thường gặp |
| --- | --- | --- |
| **Impact** | Hậu quả có điều kiện nếu một sự kiện xảy ra trong bối cảnh xác định. | Coi mọi lỗi cùng loại đều có hậu quả như nhau. |
| **Likelihood** | Khả năng/tần suất sự kiện xảy ra trong thời kỳ đã xét. | Nhầm hậu quả cao với khả năng xảy ra cao. |
| **Risk rating** | Mức rủi ro từ phương pháp tổng hợp hậu quả và khả năng hoặc bất định. | Nhân điểm 1–5 rồi hiểu kết quả như xác suất hay tiền thực tế. |
| **Vulnerability severity (ví dụ CVSS)** | Mức nghiêm trọng kỹ thuật của lỗ hổng theo hệ thống chấm điểm tương ứng. | Dùng điểm kỹ thuật làm bằng chứng duy nhất cho tác động nghiệp vụ. |
| **Incident impact thực tế** | Hậu quả đã xác nhận khi sự cố thật xảy ra. | Dùng mức tiềm năng như thể tổn thất thực tế đã xảy ra. |

Điểm số kỹ thuật có thể là **đầu vào** cho kịch bản, nhưng Impact cuối cùng cần bổ sung tài sản, dữ liệu, khách hàng, phụ thuộc và bối cảnh vận hành.

## 14. Duy trì đánh giá Impact liên tục

Impact thay đổi theo dữ liệu, sản phẩm, cách sử dụng và môi trường. Một đánh giá lập ở giai đoạn thiết kế chưa chắc còn đúng sau khi có khách hàng mới hoặc chuyển dữ liệu sang hệ thống phân tích.

~~~mermaid
flowchart TD
    A["Xác định tài sản và kịch bản"] --> B["Thu thập hậu quả, bằng chứng, giả định"]
    B --> C["Chấm từng chiều Impact theo rubric"]
    C --> D["Tổng hợp và review với owner"]
    D --> E["Liên kết với Likelihood và quyết định Risk"]
    E --> F["Triển khai kiểm soát / khắc phục"]
    F --> G["Kiểm thử, audit, thu evidence"]
    G --> H{"Bằng chứng hoặc bối cảnh thay đổi?"}
    H -- "Có" --> B
    H -- "Chưa" --> I["Giám sát và tái đánh giá theo lịch"]
    I --> H
~~~

Các sự kiện nên kích hoạt xem lại gồm:

- Bổ sung dữ liệu nhạy cảm, thay đổi phân loại hoặc số lượng đối tượng liên quan.
- Mở API, tenant, vùng triển khai, bên nhận dữ liệu hoặc tích hợp đối tác mới.
- Thay đổi RTO/RPO, phụ thuộc quan trọng, mô hình hoạt động hoặc khối lượng giao dịch.
- Xuất hiện exploit, threat hoặc sự cố làm thay đổi cách hiểu kịch bản.
- Security control bị vô hiệu, thay đổi, mở rộng phạm vi hoặc được triển khai lại.
- Kết quả test, pentest, audit, BIA hoặc diễn tập cho thấy giả định không còn đúng.
- Chính sách, hợp đồng hoặc nghĩa vụ được áp dụng thay đổi.

**Impact review phải gắn với phiên bản bằng chứng.** Khi thay đổi làm mất hiệu lực kết luận cũ, cần đánh dấu đánh giá đang chờ cập nhật và giao người sở hữu xử lý, thay vì để dashboard tiếp tục hiển thị điểm cũ như còn được xác nhận.

### Từ phát hiện đến bằng chứng đã khắc phục

Một chu trình assurance hữu ích:

**Phát hiện → xác định kịch bản → đánh giá Impact có bằng chứng → giao owner → khắc phục/giảm thiểu → kiểm tra lại → đánh giá residual risk → quyết định và giám sát.**

Đóng một ticket vì “đã merge code” không tự chứng minh impact được giảm. Cần kiểm tra phần thay đổi có đúng phiên bản triển khai, còn đường đi nào chưa bao phủ và hậu quả còn lại trong kịch bản có khác hay không.

## 15. Các sai lầm cần tránh

| Ngộ nhận | Cách xử lý đúng |
| --- | --- |
| “Impact và likelihood đều là khả năng sự cố xảy ra.” | Impact đo hậu quả có điều kiện; likelihood đo khả năng hoặc tần suất. |
| “Điểm CVSS Critical thì business impact luôn Critical.” | Phải phân tích dữ liệu, quy trình, phạm vi và controls của hệ thống cụ thể. |
| “Chưa có bằng chứng khai thác nghĩa là impact bằng 0.” | Tách impact **tiềm năng** nếu kịch bản xảy ra với thiệt hại **đã xác nhận**. |
| “Dùng một mức Impact cho cả ứng dụng.” | Xem xét từng kịch bản và quy trình; một dịch vụ có nhiều mức hậu quả khác nhau. |
| “Lấy trung bình tất cả chiều để tránh điểm quá cao.” | Tuân thủ quy tắc tổng hợp đã duyệt; không che khuất hậu quả nghiêm trọng. |
| “Impact bằng tổng doanh thu đi qua hệ thống khi outage.” | Phân biệt doanh thu trì hoãn, giao dịch mất thực sự và chi phí tăng thêm; tránh đếm trùng. |
| “Mọi giá trị tiền đều biết chính xác.” | Dùng khoảng, giả định và mức độ tin cậy khi thông tin không đủ. |
| “Thêm control nghĩa là impact giảm.” | Kiểm tra control tác động đến likelihood, phạm vi hoặc hậu quả; đòi hỏi bằng chứng hiệu quả. |
| “Backup thành công nghĩa là hậu quả mất dữ liệu thấp.” | Cần thử restore, kiểm tra dữ liệu và đo RTO/RPO cho kịch bản phù hợp. |
| “Điểm Impact đã chấm thì dùng mãi.” | Đánh giá lại khi dữ liệu, khách hàng, phụ thuộc, nghĩa vụ hoặc controls thay đổi. |
| “Người báo lỗi tự quyết định chấp nhận rủi ro.” | Quyền quyết định thuộc risk owner/cấp có thẩm quyền theo governance. |

## 16. Bài tập áp dụng

### Bài tập A — Phân biệt hậu quả và xác suất

Một lỗ hổng hiếm có thể làm sai số dư tiền của nhiều khách hàng; một lỗi thường xuyên làm báo cáo nội bộ chậm 20 giây. Sự kiện nào có Impact cao hơn?

**Hướng phân tích:** tác động đến toàn vẹn dữ liệu tài chính và khách hàng có thể lớn hơn đáng kể so với độ trễ báo cáo, **dù lỗ hổng đầu tiên ít có khả năng xảy ra hơn**. Cần xác định phạm vi dữ liệu, hậu quả đối soát, khả năng khôi phục và rubric của tổ chức trước khi chấm cấp.

### Bài tập B — Lượng hóa gián đoạn

Một dịch vụ bị gián đoạn, có 800 đơn dự kiến trong khoảng đó. Sau phục hồi, 600 đơn được khách đặt lại; mỗi đơn không quay lại đóng góp 40.000 đồng. Chi phí ứng cứu phát sinh là 6 triệu đồng; giả sử không có đếm trùng và chưa tính các hậu quả khác.

**Hướng tính:** (800 − 600) × 40.000 + 6.000.000 = **14.000.000 đồng**. Đây là **một phần impact tài chính có điều kiện**, chưa phản ánh tổn thất hợp đồng, uy tín hay hậu quả khác nếu có; cũng chưa tính likelihood của gián đoạn.

### Bài tập C — Có nên giảm Impact sau khi bật MFA?

Một rủi ro được đánh giá là “nếu tài khoản quản trị bị chiếm, kẻ tấn công có thể xóa nhiều bản ghi khách hàng”. Đội IAM triển khai MFA toàn bộ tài khoản quản trị. Có thể tự động giảm điểm Impact từ 5 xuống 2 không?

**Hướng phân tích:** MFA có thể giảm likelihood chiếm tài khoản theo cơ chế phù hợp, nhưng **nếu tài khoản vẫn bị chiếm** thì khả năng xóa dữ liệu và hậu quả có thể chưa đổi. Chỉ thay đổi impact khi có bằng chứng control làm giảm phạm vi/khả năng xóa hoặc giảm hậu quả sau sự kiện (ví dụ quyền tối thiểu, phục hồi đã kiểm chứng). Ghi riêng các giả định và kiểm tra MFA có bao phủ mọi đường đăng nhập không.

### Bài tập D — Đánh giá không chắc chắn

Khi phát hiện API đọc chéo tenant, log chỉ được giữ 24 giờ; không biết có bị khai thác trước đó hay không. Đội kỹ thuật kết luận “impact thấp vì không tìm thấy log truy cập”.

**Hướng phân tích:** thiếu log ngoài 24 giờ **không chứng minh không có truy cập**; cần xác định impact tiềm năng dựa trên độ nhạy và phạm vi dữ liệu có thể tiếp cận, tách biệt với tổn thất thực tế đã xác nhận, ghi mức tin cậy/giới hạn bằng chứng và đề xuất điều tra hoặc cải thiện telemetry.

## Kết luận

**Impact** là mức độ hậu quả của một kịch bản rủi ro bảo mật khi sự kiện xảy ra, xét theo **tài sản, dữ liệu, quy trình, khách hàng, thời gian và nghĩa vụ thực tế**. Đánh giá đáng tin cần kịch bản có phạm vi rõ, tiêu chí đã được hiệu chuẩn, bằng chứng cho từng chiều, giả định và độ không chắc chắn được ghi nhận, cùng người có thẩm quyền xem xét. Trong chương trình **SECURITY_SECURITY_ASSURANCE**, kết quả Impact không đứng một mình: nó dẫn dắt lựa chọn controls, kiểm thử, audit, ưu tiên khắc phục, đánh giá residual risk và quyết định có thể giải trình. Khi hệ thống thay đổi hoặc bằng chứng mới xuất hiện, Impact phải được xem lại để kết luận bảo mật luôn phản ánh tình trạng hiện tại.

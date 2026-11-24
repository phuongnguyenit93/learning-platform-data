# Xử lý công việc khẩn cấp bằng chính sách dịch vụ rõ ràng

## 1. Vì sao Kanban cần chính sách riêng cho công việc khẩn cấp?

Một nhóm phát triển phần mềm có thể đang hoàn thiện tính năng tìm kiếm, sửa lỗi giao diện và cải tiến kiểm thử thì nhận được thông tin: hệ thống thanh toán vừa ghi nhận hai giao dịch cho cùng một đơn hàng. Đây là sự cố có thể ảnh hưởng trực tiếp đến tiền của khách hàng và uy tín sản phẩm; nhóm cần phản ứng nhanh.

Nhưng nếu mọi bên liên quan đều có thể gắn nhãn **“khẩn cấp”** cho yêu cầu của mình, bảng Kanban dễ biến thành một hàng dài việc phải làm “ngay lập tức”. Khi đó:

- Công việc đang làm bị ngắt liên tục, chi phí chuyển ngữ cảnh tăng.
- Nhiều hạng mục bị bỏ dở và mất thời gian hoàn thành.
- Một yêu cầu được ưu tiên không phải vì tác động thực tế mà vì người đề xuất nói lớn hơn.
- Lỗi nghiêm trọng thực sự phải chờ sau những việc chỉ “gấp” về mặt cảm nhận.
- Người dùng và các bên liên quan không thể dự đoán khi nào công việc thường được xử lý.

**Kanban** giúp quản lý dòng công việc bằng cách trực quan hóa việc đang đi qua hệ thống, quản lý lượng việc dở dang (**Work in Progress — WIP**), quy định chính sách rõ ràng và cải tiến dựa trên quan sát. Với công việc khẩn cấp, điều quan trọng không phải tạo một cột đỏ bắt mắt, mà là thống nhất **khi nào được xử lý ngoại lệ, ai có quyền quyết định, công việc nào bị ảnh hưởng và cách đưa hệ thống trở lại nhịp bình thường**.

Trong bài này, **“chính sách dịch vụ”** là những quy tắc được công khai và thống nhất về cách tiếp nhận, phân loại, chọn, xử lý, chuyển trạng thái và hoàn thành các loại công việc. Một cách phổ biến là sử dụng **classes of service (các lớp dịch vụ)** để phân biệt nhu cầu xử lý khác nhau, chẳng hạn việc khẩn cấp, việc có hạn cố định hoặc việc thông thường.

Đây là chủ đề thuộc module **AGILE_DEVELOPMENT**: hiểu và thực hành Agile để phản hồi sớm, bàn giao tăng dần, cải tiến liên tục, đồng thời biết kết hợp user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Xử lý khẩn cấp tốt là một khả năng thích ứng quan trọng, nhưng **không được đánh đổi sự an toàn hoặc làm mất tính minh bạch của toàn bộ dòng công việc**.

### Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt **mức độ nghiêm trọng**, **tính khẩn cấp**, **chi phí trì hoãn** và **hạn chót** của công việc.
2. Giải thích cách sử dụng lớp dịch vụ trong Kanban và vì sao **Expedite** phải là ngoại lệ có quy tắc rõ.
3. Thiết kế chính sách tiếp nhận, phân loại, giới hạn WIP, quyền quyết định, thông báo và kết thúc xử lý việc khẩn.
4. Tổ chức một luồng ứng phó nhanh mà vẫn tôn trọng yêu cầu chất lượng, an toàn và công việc đang thực hiện.
5. Quan sát ảnh hưởng của việc chen ngang đến **cycle time, throughput, work item age, blocked time** và dự báo dịch vụ.
6. Áp dụng chính sách vào tình huống sự cố thanh toán, yêu cầu có hạn pháp lý và backlog thông thường.

## 2. Hiểu đúng “khẩn cấp”: không phải yêu cầu nào có chữ “ASAP” cũng giống nhau

**Urgency (tính khẩn cấp)** là mức độ cần hành động sớm do thời gian chờ tạo ra hậu quả hoặc làm mất cơ hội. **Severity/impact (mức độ nghiêm trọng/tác động)** nói về hậu quả đối với người dùng, sản phẩm hoặc tổ chức. Hai yếu tố này liên quan nhưng không đồng nhất.

| Khái niệm | Câu hỏi cần hỏi | Ví dụ |
|---|---|---|
| **Tác động / severity** | Bao nhiêu người bị ảnh hưởng, thiệt hại và rủi ro lớn đến đâu? | Khách hàng có thể bị tính tiền hai lần khi thanh toán. |
| **Khẩn cấp / urgency** | Điều gì xấu đi nếu nhóm đợi thêm? Cần phản ứng trong thời gian nào? | Mỗi giao dịch mới có thể tiếp tục tạo thiệt hại, cần ngăn nhanh. |
| **Chi phí trì hoãn / cost of delay** | Giá trị mất đi hoặc rủi ro tăng theo thời gian ra sao? | Chờ khắc phục khiến số giao dịch sai và công sức đối soát tăng. |
| **Hạn chót / deadline** | Có ngày hoặc thời điểm cụ thể cần đáp ứng không? | Chính sách xác thực mới phải có hiệu lực trước ngày đã công bố. |
| **Độ bất định** | Thông tin nào chưa rõ và phải xác minh ngay? | Chưa biết lỗi chỉ xảy ra với một cổng thanh toán hay tất cả phương thức. |

Một lỗi có tác động rất lớn nhưng chưa rõ nguyên nhân vẫn có thể cần **hành động giảm thiểu ngay**, trong khi điều tra nguyên nhân gốc sẽ tiếp tục sau. Ngược lại, yêu cầu thêm một biểu tượng cho buổi giới thiệu nội bộ “vào sáng mai” có hạn gần nhưng không đương nhiên được phép chen ngang một sự cố bảo mật đang diễn ra.

### 2.1. Khẩn cấp không đồng nghĩa quan trọng nhất về lâu dài

Một cải tiến hệ thống sao lưu có thể rất quan trọng nhưng chưa có sự cố xảy ra và có thể được lên kế hoạch. Một sự cố đang khiến dữ liệu người dùng bị lộ vừa **nghiêm trọng** vừa **khẩn cấp**. Một cơ hội thương mại chỉ còn vài ngày có thể có **hạn chót cố định**, nhưng cần đánh giá tác động và mức độ chắc chắn, không tự mặc định cao hơn toàn bộ công việc khác.

Phân biệt này giúp nhóm lựa chọn **chính sách dịch vụ thích hợp**, thay vì chỉ xếp công việc thành hai loại “có ưu tiên” và “không ưu tiên”.

### 2.2. Phân biệt “cần phản ứng ngay” với “cần hoàn tất ngay”

Trong sự cố production, có ít nhất ba loại thời điểm:

1. **Phát hiện và xác nhận:** có ai tiếp nhận, đánh giá tình huống và bắt đầu ứng phó chưa?
2. **Giảm thiểu tác động:** có thể vô hiệu hóa luồng lỗi, chuyển sang phương án an toàn hoặc ngăn thiệt hại phát sinh thêm không?
3. **Khắc phục đầy đủ:** sửa nguyên nhân, kiểm tra hồi quy, phục hồi và cải tiến phòng ngừa.

Một nhóm có thể phản ứng rất nhanh nhưng cần thêm thời gian để sửa triệt để. Vì vậy, không nên dùng **một con số thời gian xử lý** để thay cho cả chính sách ứng phó sự cố, đặc biệt khi tiền, an toàn và dữ liệu cá nhân bị ảnh hưởng.

## 3. Các lớp dịch vụ (classes of service) trong Kanban

Một cách phổ biến trong thực hành Kanban là phân biệt công việc theo **chi phí trì hoãn** và kỳ vọng dịch vụ. Các lớp dưới đây là **mẫu minh họa thường gặp**, không phải danh sách bắt buộc hay mức ưu tiên phổ quát cho mọi nhóm.

| Lớp dịch vụ | Khi nào phù hợp? | Cách xử lý thường gặp | Cần cảnh giác |
|---|---|---|---|
| **Expedite — xử lý khẩn** | Chờ đợi có thể làm tăng thiệt hại lớn hoặc rủi ro không chấp nhận được. | Ưu tiên xử lý ngay theo chính sách, có người điều phối, thường giới hạn rất ít việc đồng thời. | Dùng thường xuyên sẽ làm mọi việc khác chậm và mất tính dự báo. |
| **Fixed Date — ngày cố định** | Có thời hạn mang ý nghĩa thực tế, chi phí trì hoãn tăng mạnh sau mốc đó. | Lên kế hoạch và bắt đầu đủ sớm theo rủi ro và thời gian thực hiện. | Đợi đến sát hạn rồi mới gọi là Expedite. |
| **Standard — thông thường** | Giá trị và chi phí trì hoãn không đòi hỏi chen ngang ngay. | Xử lý theo thứ tự ưu tiên và chính sách kéo việc của nhóm. | Công việc dễ bị đói nếu expedite xuất hiện liên tục. |
| **Intangible — lợi ích/rủi ro dài hạn khó thấy ngay** | Công việc cải thiện độ tin cậy, nợ kỹ thuật hoặc rủi ro tương lai chưa tạo hậu quả tức thời. | Bố trí năng lực và xem xét định kỳ; đo ảnh hưởng dài hạn. | Để hoãn vô thời hạn cho tới khi trở thành sự cố thật. |

**Điểm mấu chốt:** lớp dịch vụ là **thỏa thuận về cách phục vụ công việc**, không chỉ là nhãn màu hoặc tên trạng thái.

### 3.1. Expedite không phải “mọi thứ từ cấp quản lý”

Một yêu cầu do người có chức vụ cao gửi đến vẫn phải được xem xét theo **tác động, độ khẩn, bằng chứng và chính sách đã thống nhất**, trừ khi tổ chức có thẩm quyền ứng phó khẩn cấp hoặc nghĩa vụ bắt buộc riêng.

Ví dụ có thể đáng cân nhắc Expedite:

- Lỗi đang khiến giao dịch thanh toán bị tính tiền lặp.
- Rò rỉ dữ liệu hoặc lỗ hổng đang bị khai thác, cần ngăn thiệt hại.
- Dịch vụ thiết yếu ngừng hoạt động diện rộng.
- Một sự cố đang tạo ảnh hưởng nghiêm trọng đến an toàn, quyền truy cập hoặc nghĩa vụ vận hành.

Ví dụ thường **không tự động** là Expedite:

- “Làm nút mới trước chiều nay vì có buổi demo”.
- “Lãnh đạo muốn xem một báo cáo mới ngay”.
- “Story này tồn tại trong backlog lâu nên phải xong lập tức”.

Những yêu cầu sau vẫn có thể quan trọng, nhưng nên được đánh giá bằng ưu tiên chung hoặc **Fixed Date** khi có thời hạn thực sự.

### 3.2. Fixed Date cần bắt đầu sớm, không phải chờ tới khi cháy nhà

Nếu một thay đổi đáp ứng quy định phải hoàn tất trước mốc có hiệu lực, nhóm nên **làm rõ từ trước**, đánh giá phụ thuộc, năng lực, mức bất định và thời gian kiểm chứng.

Đẩy công việc có hạn cố định tới sát ngày rồi nâng thành Expedite thường là dấu hiệu **lập kế hoạch chưa tốt**. Chính sách Fixed Date giúp tránh biến ngày đến hạn thành lý do hợp thức hóa việc chen ngang.

### 3.3. Intangible không phải “có thể bỏ qua”

Việc bổ sung kiểm thử hồi quy, cải thiện khả năng quan sát, cập nhật thư viện đang cũ hoặc giảm điểm nghẽn chuyên môn có thể chưa tạo doanh thu ngay. Nhưng nếu hoãn lâu, rủi ro và chi phí thay đổi có thể tích tụ.

Nhóm nên có cách xem xét định kỳ và phân bổ năng lực cho công việc này khi phù hợp. Nếu xuất hiện bằng chứng về lỗ hổng đang bị khai thác hoặc lỗi nghiêm trọng, một hạng mục có thể được **phân loại lại** theo tình huống thực, thay vì giữ nhãn cũ.

## 4. Chính sách dịch vụ rõ ràng phải chứa những gì?

Trong Kanban, **explicit policies (chính sách được diễn đạt rõ)** giúp những người sử dụng hệ thống làm việc hiểu **khi nào một hạng mục có thể vào luồng, được chọn, được chuyển trạng thái, được ưu tiên và hoàn thành**.

Một chính sách xử lý việc khẩn cấp hữu ích tối thiểu phải trả lời:

| Thành phần | Câu hỏi chính | Ví dụ minh họa |
|---|---|---|
| **Điều kiện kích hoạt** | Tình huống nào đủ để dùng Expedite? | Sự cố đang tạo hoặc có nguy cơ tức thời gây mất tiền, mất dữ liệu, ngừng dịch vụ quan trọng. |
| **Bằng chứng tối thiểu** | Cần biết gì trước khi phân loại? | Dấu hiệu, người bị ảnh hưởng, nguồn phát hiện, mức độ tin cậy, diễn biến theo thời gian. |
| **Quyền quyết định** | Ai xác nhận lớp dịch vụ và điều phối? | Người trực sự cố hoặc người phụ trách dịch vụ theo chính sách; Product Owner tham gia khi cần đổi ưu tiên sản phẩm. |
| **Quy tắc chen ngang** | Việc nào bị dừng hoặc tạm hoãn; ngoại lệ WIP ra sao? | Tập trung một sự cố Expedite chủ đạo, chọn người phối hợp, đánh dấu việc bị gián đoạn. |
| **Giới hạn đồng thời** | Có thể xử lý bao nhiêu việc Expedite cùng lúc? | Mục tiêu chỉ một luồng khẩn chủ đạo; nếu nhiều sự cố nghiêm trọng phải kích hoạt quy trình điều phối riêng. |
| **Mức dịch vụ kỳ vọng** | Phản ứng và thông báo theo nhịp nào? | Có nhịp cập nhật sự cố, kênh liên lạc và mốc kiểm tra tiếp theo. |
| **Điều kiện hoàn tất** | Khi nào ngừng chế độ khẩn cấp? | Tác động đã được ngăn/giảm đến mức chấp nhận, có bằng chứng kiểm chứng, bàn giao xử lý tiếp rõ ràng. |
| **Hậu kiểm** | Làm sao cải tiến chính sách? | Xem nguyên nhân, tổng thời gian gián đoạn, tác động đến công việc thường và hành động phòng ngừa. |

Chính sách có thể ngắn nhưng phải **dễ tìm, được dùng thống nhất và được cải tiến theo bằng chứng**, không chỉ lưu trong một tài liệu chưa ai đọc.

### 4.1. Ví dụ văn bản chính sách nhóm

~~~text
CHÍNH SÁCH LỚP DỊCH VỤ - BẢN MINH HỌA

1. Tiếp nhận:
   - Mọi yêu cầu ghi rõ vấn đề, tác động, mức khẩn và người liên hệ.
   - Khi có sự cố đang gây thiệt hại lớn, dùng ngay kênh ứng phó sự cố;
     không chờ cuộc họp chọn backlog thường kỳ.

2. Phân loại:
   - Expedite: có tác động lớn đang diễn ra hoặc nguy cơ nghiêm trọng cận kề.
   - Fixed Date: có mốc bắt buộc thực, có thể lập kế hoạch trước.
   - Standard: xử lý theo thứ tự và chính sách kéo việc thông thường.
   - Intangible: lợi ích hoặc phòng ngừa rủi ro dài hạn, xem xét định kỳ.

3. Quyền quyết định:
   - Người điều phối được chỉ định xác nhận Expedite và thông báo lý do.
   - Product Owner/người phụ trách ưu tiên cập nhật tác động tới backlog.
   - Quy định ứng phó an toàn/bảo mật của tổ chức có thể được kích hoạt ngay.

4. Điều phối:
   - Mục tiêu tối đa một hạng mục Expedite đang xử lý chủ đạo.
   - Những người cần thiết phối hợp xử lý; hạng mục bị ngắt phải được ghi rõ.
   - Nếu có nhiều sự cố nghiêm trọng, người điều phối kích hoạt cơ chế xử lý
     sự cố đồng thời thay vì ngầm bỏ qua một sự cố hoặc giấu WIP.

5. Thông tin:
   - Có người phụ trách cập nhật tình trạng và mốc thông báo kế tiếp.
   - Nêu điều đã biết, điều chưa chắc, tác động và hành động giảm thiểu.

6. Thoát chế độ khẩn:
   - Xác nhận tác động đang diễn ra đã được kiểm soát theo tiêu chí phù hợp.
   - Công việc còn lại được phân loại, ưu tiên và theo dõi rõ ràng.
   - Xem lại nguyên nhân, thời gian chờ và ảnh hưởng tới các hạng mục khác.
~~~

Các giới hạn và thẩm quyền trong mẫu là **ví dụ để nhóm điều chỉnh**, không phải luật chung của Kanban. Khi có sự cố an toàn hoặc bảo mật nghiêm trọng, quy trình ứng phó và nghĩa vụ bắt buộc của tổ chức luôn cần được áp dụng phù hợp.

## 5. Thiết kế luồng xử lý Expedite trên bảng Kanban

Một bảng Kanban hữu ích thể hiện **dòng công việc thật** từ lúc được chấp nhận vào hệ thống cho tới khi đáp ứng điều kiện hoàn thành.

Ví dụ, nhóm đang dùng các trạng thái:

~~~text
Tồn đọng -> Đã chọn -> Đang thực hiện -> Đang xác minh -> Hoàn thành
                      (WIP 3)           (WIP 2)
~~~

Các số WIP ở trên **chỉ để minh họa**. Nhóm có thể bổ sung nhãn, thẻ hoặc một **swimlane Expedite** chạy ngang qua các trạng thái khi cần. Tuy nhiên, không nên tạo một cột “Khẩn cấp” mơ hồ rồi để công việc nằm ở đó mà không ai biết đang ở bước nào.

### 5.1. Swimlane Expedite làm gì?

Swimlane phân biệt lớp dịch vụ của thẻ công việc trong khi vẫn giữ các bước xử lý và điều kiện hoàn thành.

| Lớp / Trạng thái | Đã chọn | Đang xử lý | Đang xác minh | Hoàn thành |
|---|---|---|---|---|
| **Expedite** | Chỉ việc đủ điều kiện và được điều phối. | Sự cố đang được giảm thiểu hoặc sửa. | Kiểm tra hiệu quả khắc phục, hồi quy và rủi ro liên quan. | Xác nhận thoát chế độ khẩn, công việc tiếp theo rõ. |
| **Fixed Date** | Được chọn đủ sớm theo hạn và độ bất định. | Triển khai theo mốc và phụ thuộc đã biết. | Kiểm tra với thời gian dự phòng phù hợp. | Đạt chất lượng trước thời hạn áp dụng. |
| **Standard/Intangible** | Được chọn theo chính sách chung. | Hạn chế WIP, hỗ trợ hoàn thành. | Kiểm tra liên tục, tránh dồn cuối. | Hoàn thành theo định nghĩa thống nhất. |

**Swimlane không tự tạo năng lực thực hiện.** Nếu toàn nhóm chỉ có ba người xử lý được lỗi thanh toán, kéo thêm mười thẻ vào làn Expedite sẽ không làm cả mười việc được giải quyết nhanh hơn.

### 5.2. Minh họa luồng quyết định

~~~mermaid
flowchart TD
    A["Yêu cầu hoặc sự cố mới"] --> B["Xác nhận tác động, mức khẩn, bằng chứng"]
    B --> C{"Đang gây nguy cơ lớn cần hành động tức thời?"}
    C -->|Có| D["Kích hoạt quy trình ứng phó và xem xét Expedite"]
    C -->|Không| E{"Có hạn cố định thật sự?"}
    E -->|Có| F["Fixed Date: lập kế hoạch đủ sớm"]
    E -->|Không| G["Standard hoặc Intangible theo chính sách"]
    D --> H["Điều phối, giới hạn WIP, ghi việc bị gián đoạn"]
    H --> I["Giảm tác động, sửa và xác minh"]
    I --> J{"Rủi ro tức thời đã được kiểm soát?"}
    J -->|Chưa| H
    J -->|Rồi| K["Bàn giao việc còn lại, hậu kiểm, phục hồi flow"]
    F --> L["Kéo việc và kiểm tra theo luồng"]
    G --> L
~~~

Sơ đồ hỗ trợ thảo luận, **không thay thế playbook ứng phó sự cố**. Những hành động ngăn rủi ro đang diễn ra có thể phải bắt đầu trước khi mọi thông tin phân loại đã đầy đủ.

## 6. Tiếp nhận và triage: quyết định khẩn cấp dựa trên bằng chứng

**Triage** là hoạt động đánh giá nhanh tình huống để quyết định mức phản ứng phù hợp. Với công việc khẩn, mục tiêu là **ra quyết định ban đầu đủ tốt và có thể điều chỉnh**, không đợi một báo cáo dài hoàn hảo.

### 6.1. Thông tin đầu vào tối thiểu

| Câu hỏi | Lý do |
|---|---|
| Điều gì đang xảy ra? | Phân biệt sự cố thực với đề xuất hoặc cảm nhận. |
| Ai và bao nhiêu người bị ảnh hưởng? | Ước lượng tác động và mức độ lan rộng. |
| Hậu quả gì nếu chờ thêm? | Xem có cần hành động ngay không. |
| Có đang tiếp tục phát sinh thiệt hại? | Quyết định có cần ngăn luồng lỗi, rollback hay giảm phạm vi dịch vụ. |
| Đã có bằng chứng gì và điều gì chưa chắc? | Tránh coi giả định là kết luận. |
| Ai có quyền quyết định giảm thiểu, thông báo hoặc bật/tắt tính năng? | Tránh chậm hoặc hành động vượt thẩm quyền. |
| Ai sẽ cập nhật và khi nào kiểm tra lại? | Giữ thông tin nhất quán, tránh công việc bị bỏ quên. |

Nếu sự cố liên quan tiền, dữ liệu cá nhân hoặc an toàn, nhóm phải tuân thủ quy trình ứng phó chuyên trách và các nghĩa vụ liên quan. **Chính sách Kanban quản lý dòng công việc, không thay thế yêu cầu bảo mật, pháp lý hay trách nhiệm xử lý sự cố.**

### 6.2. Phân biệt tình huống thật với “độ ồn”

Ví dụ:

| Yêu cầu mới | Tín hiệu | Phân loại ban đầu có thể phù hợp |
|---|---|---|
| Nhiều khách bị trừ tiền hai lần cho cùng đơn. | Giao dịch lỗi đang diễn ra, thiệt hại tài chính tăng. | Expedite hoặc trực tiếp kích hoạt ứng phó sự cố nghiêm trọng. |
| Thay đổi biểu mẫu vì quy định có hiệu lực sau sáu tuần. | Hạn có thật, vẫn đủ thời gian lên kế hoạch. | Fixed Date. |
| Lãnh đạo muốn đổi màu nút trước buổi họp ngày mai. | Hạn gần do kế hoạch nội bộ, tác động chưa rõ. | Đánh giá trong Standard/Fixed Date tùy giá trị và thỏa thuận, không tự động Expedite. |
| Thư viện cũ không còn được hỗ trợ nhưng chưa có lỗ hổng được biết. | Rủi ro dài hạn cần đánh giá. | Intangible hoặc Standard; có thể tăng ưu tiên khi bằng chứng đổi. |
| Lỗ hổng bảo mật đang bị khai thác công khai trong dịch vụ đang sử dụng. | Nguy cơ thiệt hại hiện hữu/cận kề lớn. | Kích hoạt ứng phó bảo mật; Expedite cho công việc cần thực hiện trong luồng. |
| Một tính năng không đạt kỳ vọng kinh doanh nhưng vẫn hoạt động an toàn. | Cần điều chỉnh giá trị, chưa chắc là sự cố tức thời. | Product Backlog ưu tiên cao nếu phù hợp, không nhất thiết Expedite. |

**Phân loại là một quyết định có thể xem lại.** Khi thông tin mới cho thấy tác động lớn hơn hoặc nhỏ hơn ban đầu, người có thẩm quyền nên điều chỉnh lớp dịch vụ và giải thích lý do.

## 7. Ai được quyết định chen ngang và phải công khai điều gì?

Chính sách chỉ có tác dụng khi **quyền quyết định và trách nhiệm thông tin** đủ rõ. Nếu ai cũng có thể tự dán “Expedite”, lớp dịch vụ mất ý nghĩa. Nếu chỉ một người có quyền quyết định nhưng không có người thay thế khi vắng mặt, sự cố có thể bị chậm vì chính chính sách.

Một cơ chế minh họa:

1. **Người phát hiện** báo dấu hiệu, tác động, bằng chứng và kênh liên hệ; khi có nguy cơ cao dùng ngay kênh ứng phó.
2. **Người điều phối được ủy quyền** đánh giá và xác nhận hoặc điều chỉnh lớp dịch vụ; có người thay thế được xác định trước.
3. **Những người xử lý** cùng làm rõ việc cần làm ngay, chia trách nhiệm và xác minh kết quả.
4. **Người chịu trách nhiệm ưu tiên sản phẩm** như Product Owner (nếu nhóm dùng Scrum) giúp làm rõ tác động tới Product Backlog, Sprint Goal hoặc cam kết kinh doanh.
5. **Người phụ trách giao tiếp** cập nhật trạng thái cho bên liên quan theo nhịp thống nhất, không để kỹ sư đang ứng phó bị gián đoạn bởi nhiều yêu cầu báo cáo riêng.

Trong một tổ chức, các vai trò có thể có tên khác, ví dụ incident commander, service owner, người trực on-call. **Kanban không bắt buộc các chức danh này**; điều cần thiết là chính sách thể hiện rõ ai chịu trách nhiệm ở từng quyết định và đường liên lạc khi khẩn.

### 7.1. Minh bạch chi phí chen ngang

Khi kích hoạt Expedite, nên ghi rõ:

- Công việc thường nào bị tạm dừng hoặc mất năng lực xử lý?
- Ai đang chuyển sang xử lý sự cố?
- Có hạng mục Fixed Date nào bị đe dọa?
- Thay đổi dự báo, phạm vi hoặc cam kết cần được thông báo cho ai?
- Khi nào sẽ xem xét lại mức khẩn và cách phục hồi công việc?

Không cần lập tức tính chính xác mọi chi phí, nhưng **chi phí chen ngang phải được nhìn thấy**. Nếu không, tổ chức dễ coi Expedite là “làm miễn phí” và liên tục đẩy việc ngoài kế hoạch vào hệ thống.

## 8. WIP và công việc khẩn: ưu tiên ngay nhưng không vô hạn

Một nguyên tắc quan trọng của Kanban là **quản lý lượng công việc dở dang**. Với Expedite, nhiều nhóm đặt mục tiêu **chỉ một hạng mục khẩn chủ đạo đang thực hiện** để tập trung năng lực và giảm chuyển ngữ cảnh. Đây là **chính sách thiết kế theo năng lực thực tế**, không phải giới hạn bắt buộc cho mọi Kanban system.

### 8.1. Expedite có thể là ngoại lệ của quy tắc kéo việc bình thường

Trong luồng Standard, nhóm thường kéo hạng mục mới khi còn năng lực theo WIP limit. Expedite có thể cho phép **ưu tiên chen ngang theo một ngoại lệ được ghi rõ**, chẳng hạn ngừng một số công việc hiện tại và dồn người phù hợp xử lý.

Tuy vậy, **ngoại lệ có điều kiện khác với bỏ qua WIP hoàn toàn**. Nhóm cần nêu:

1. Khi nào được phép vượt WIP limit hoặc thay đổi ưu tiên?
2. Ai xác nhận ngoại lệ?
3. Việc nào được tạm dừng và đánh dấu thế nào?
4. Phải kiểm tra lại tình trạng vào thời điểm nào?
5. Khi nào ngừng Expedite và quay về chính sách kéo việc bình thường?

### 8.2. Nếu có hai sự cố nghiêm trọng cùng lúc?

Chính sách “tối đa một Expedite” **không có nghĩa bỏ mặc sự cố thứ hai**. Khi hai sự cố nghiêm trọng xảy ra đồng thời, tổ chức cần xử lý theo mức ảnh hưởng và năng lực thực:

- Xác định sự cố nào đang gây thiệt hại lớn hơn hoặc lan nhanh hơn.
- Kích hoạt cơ chế điều phối sự cố đồng thời hoặc bổ sung năng lực có quyền hạn phù hợp.
- Nếu có thể, phân chia nhóm ứng phó theo dịch vụ và chuyên môn thay vì để một người chuyển qua lại liên tục.
- Thông báo rõ giới hạn năng lực và rủi ro còn lại.
- Ghi nhận ngoại lệ WIP và lý do để hậu kiểm.

**Giới hạn WIP là cơ chế giúp quyết định minh bạch**, không phải lý do trì hoãn những nghĩa vụ ứng phó bắt buộc.

### 8.3. Đừng biến Expedite thành kho chứa việc dang dở

Một lỗi được giảm tác động trong vài giờ nhưng còn công việc điều tra, phòng ngừa và nâng cấp hệ thống có thể kéo dài nhiều ngày. Sau khi tác động tức thời đã được kiểm soát:

1. Xác nhận điều kiện kết thúc giai đoạn khẩn cấp.
2. Tách các công việc tiếp theo: sửa triệt để, xử lý dữ liệu bị ảnh hưởng, cải thiện giám sát, tài liệu và phòng ngừa.
3. Ưu tiên chúng bằng lớp dịch vụ phù hợp với **rủi ro còn lại**, không tự động đẩy tất cả thành Expedite vô hạn.
4. Khôi phục công việc bị gián đoạn với trạng thái và dự báo cập nhật.

Nếu rủi ro cao chưa được kiểm soát, việc hạ cấp Expedite chỉ để “giải phóng làn” là không phù hợp.

## 9. Service Level Expectation và kỳ vọng xử lý

Kanban có thể sử dụng **Service Level Expectation (SLE)** để diễn đạt **kỳ vọng về thời gian một hạng mục đi qua hệ thống**, thường dựa trên dữ liệu cycle time lịch sử và một mức độ tin cậy/percentile.

Ví dụ giả định:

> Trong 12 tuần gần đây, khoảng 85% hạng mục Standard hoàn thành trong 8 ngày hoặc ít hơn, tính từ lúc bắt đầu xử lý đến khi đáp ứng điều kiện Done của nhóm.

Thông tin này có thể giúp nói rõ kỳ vọng với các bên liên quan và phát hiện hạng mục đang có nguy cơ vượt thời gian thường thấy. Đây **không phải lời bảo đảm** một hạng mục cụ thể sẽ xong trong 8 ngày; thống kê phụ thuộc dữ liệu mẫu, loại công việc và cách nhóm định nghĩa điểm bắt đầu/kết thúc.

### 9.1. Không dùng SLE Standard để hứa thời gian Expedite

Hạng mục Expedite có cơ chế chen ngang và thường khác hẳn về loại việc, độ bất định, rủi ro. Nếu trộn tất cả vào một tập số liệu rồi dùng percentile chung, dự báo dễ gây hiểu nhầm.

Nên cân nhắc **phân tích theo lớp dịch vụ** khi số lượng quan sát đủ có ý nghĩa, và phân biệt:

- **Response time:** thời gian từ phát hiện/báo cáo tới khi có người tiếp nhận hoặc phản ứng đầu tiên.
- **Mitigation time:** thời gian từ phát hiện tới khi tác động đang diễn ra được kiểm soát theo tiêu chí rõ.
- **Cycle time:** thời gian từ lúc công việc bắt đầu xử lý tới lúc hoàn thành theo định nghĩa của luồng.
- **Resolution time:** thời gian đến khi nguyên nhân hoặc hành vi lỗi được khắc phục theo mức yêu cầu.

Một incident có thể được giảm thiệt hại sớm nhưng cần thời gian đối soát và sửa bền vững. Chính sách nên nói rõ **mốc nào đang được đo và vì sao**.

### 9.2. SLE không thay thế SLO/SLA hoặc nghĩa vụ ứng phó sự cố

**Service Level Objective (SLO)** là mục tiêu dịch vụ, ví dụ độ sẵn sàng; **Service Level Agreement (SLA)** có thể là cam kết với khách hàng kèm điều kiện cụ thể. **SLE trong Kanban** là kỳ vọng về thời gian luồng công việc, thường hỗ trợ dự báo và điều phối.

Chúng có thể liên quan nhưng **không đồng nghĩa**. Khi sản phẩm có SLA, yêu cầu tuân thủ hoặc kịch bản sự cố cần phản ứng ngay, đội phải đáp ứng cơ chế bắt buộc đó, không viện một SLE thống kê của backlog để trì hoãn.

## 10. Case study: lỗi thanh toán bị tính tiền hai lần

**Toàn bộ tình huống, thời điểm và chính sách sau đây chỉ là ví dụ giả định để học cách áp dụng**, không phải hướng dẫn vận hành hay quy trình thanh toán áp dụng cho mọi tổ chức.

### 10.1. Bối cảnh

Một nhóm vận hành và phát triển ứng dụng thương mại điện tử dùng Kanban để xử lý:

- Tính năng Standard: cải thiện tìm kiếm và trang theo dõi đơn.
- Công việc Fixed Date: bổ sung một bước xác thực theo quy định mới.
- Công việc Intangible: nâng chất lượng cảnh báo thanh toán và dọn mã xử lý giao dịch cũ.

Sáng thứ Ba, bộ phận hỗ trợ ghi nhận nhiều trường hợp khách bị tính tiền hai lần khi nhấn “Thanh toán” sau khi ứng dụng bị gián đoạn kết nối.

Ban đầu chưa rõ lỗi nằm ở giao diện, hệ thống backend, cổng thanh toán hay việc xử lý webhook lặp. Điều đã biết là có **thiệt hại tài chính tiềm ẩn đang tiếp tục phát sinh**.

### 10.2. Triage và quyết định kích hoạt

| Câu hỏi | Thông tin giả định | Hành động |
|---|---|---|
| Có sự cố đang xảy ra không? | Nhiều giao dịch có dấu hiệu trừ tiền lặp, có đối chiếu ban đầu. | Kích hoạt kênh ứng phó phù hợp ngay. |
| Tác động tiếp diễn không? | Các lần thanh toán mới có thể mắc lỗi tương tự. | Ưu tiên ngăn giao dịch sai tiếp tục phát sinh theo phương án an toàn. |
| Có đủ điều kiện Expedite không? | Nguy cơ thiệt hại tài chính trực tiếp, không thể chờ hàng đợi thông thường. | Người có thẩm quyền xác nhận Expedite và ghi lý do. |
| Ai điều phối? | Đại diện trực sự cố được chỉ định, cùng kỹ sư thanh toán và người phụ trách nghiệp vụ. | Một đầu mối trạng thái và quyết định. |
| Công việc nào bị ảnh hưởng? | Tính năng tìm kiếm tạm dừng, một phần năng lực đội dành cho sự cố. | Đánh dấu việc bị gián đoạn, xem lại dự báo. |
| Có nghĩa vụ riêng không? | Có thể cần quy trình an toàn, đối soát và thông báo khách hàng. | Thực hiện theo chính sách và thẩm quyền áp dụng. |

**Điều quan trọng:** người xử lý cần bắt đầu các bước bảo vệ an toàn theo quy trình sự cố ngay, không đợi một cuộc họp Kanban chính thức mới được kiểm tra hoặc giảm thiệt hại.

### 10.3. Luồng ứng phó minh họa

**Bước 1 — Ngăn tác động đang diễn ra.** Nhóm xác minh phạm vi, cân nhắc tạm ngừng một luồng thanh toán có nguy cơ, chuyển về phương án an toàn hoặc rollback theo quy trình được phép. Quyết định phải xét tác động tới giao dịch hợp lệ và dữ liệu, không đơn giản tắt toàn bộ hệ thống theo cảm tính.

**Bước 2 — Tạo sự thật chung.** Ghi thời điểm, ảnh hưởng, phiên bản triển khai, dấu hiệu log/trace không chứa thông tin nhạy cảm, số lượng trường hợp xác định và điểm chưa chắc. Người điều phối cập nhật cho bên liên quan theo nhịp thống nhất.

**Bước 3 — Tìm và sửa nguyên nhân.** Giả sử nhóm phát hiện hệ thống tạo hai lệnh thu tiền khi retry sau timeout, do thiếu cơ chế xử lý yêu cầu lặp an toàn. Giải pháp kỹ thuật cụ thể cần được xác định qua bằng chứng; có thể liên quan tới idempotency key, trạng thái giao dịch, đối soát với cổng thanh toán và xử lý webhook.

**Bước 4 — Xác minh trước khi mở lại.** Kiểm tra trường hợp thanh toán thành công, timeout, retry, callback đến lặp hoặc sai thứ tự, giao dịch có trạng thái chưa rõ và quyền truy cập. Kiểm tra cả việc hiển thị trạng thái cho khách và quy trình xử lý những giao dịch đã ảnh hưởng.

**Bước 5 — Phục hồi và hậu kiểm.** Khi tác động đã được kiểm soát theo tiêu chí đã thỏa thuận, nhóm đưa các cải tiến không còn khẩn tức thời vào backlog theo rủi ro còn lại, khôi phục việc bị gián đoạn, cập nhật dự báo Fixed Date và cải tiến chính sách hoặc giám sát.

### 10.4. Bảng Kanban trong tình huống

| Hạng mục | Lớp dịch vụ | Trước sự cố | Khi ứng phó | Sau khi giảm tác động |
|---|---|---|---|---|
| Sửa giao dịch thanh toán lặp | Expedite | Chưa tồn tại trên bảng. | Ưu tiên người và kiểm tra cần thiết; cập nhật tình trạng liên tục. | Hoàn tất khi đạt điều kiện ứng phó/DoD; việc tiếp theo được ghi riêng. |
| Cải thiện trang tìm kiếm | Standard | Đang phát triển. | Tạm dừng có ghi nhận, không đánh dấu hoàn thành giả. | Đánh giá lại mức ưu tiên và thời gian hoàn thành. |
| Bổ sung xác thực theo quy định | Fixed Date | Đang được chuẩn bị trước hạn. | Theo dõi tác động tới deadline, có thể bảo vệ năng lực tối thiểu. | Điều chỉnh kế hoạch hoặc báo rủi ro trước khi trễ. |
| Nâng chất lượng giám sát thanh toán | Intangible | Được xếp xử lý định kỳ. | Một phần có thể cần làm ngay để phục vụ chẩn đoán. | Ưu tiên thêm cảnh báo và phòng ngừa theo hậu kiểm. |

Điều cần học không chỉ là “sự cố đã được sửa nhanh hay không” mà còn là **toàn bộ chi phí và tác động lên hệ thống giao giá trị** đã được nhìn thấy và xử lý thế nào.

### 10.5. Đánh giá sau sự cố

Một cuộc hậu kiểm hướng học hỏi có thể đặt những câu hỏi:

1. Tín hiệu nào đã giúp phát hiện sự cố, tín hiệu nào bị thiếu?
2. Thời gian từ phát hiện đến tiếp nhận và giảm tác động có phù hợp rủi ro không?
3. Quyết định Expedite có rõ ràng và đủ nhanh không?
4. Có những công việc nào bị gián đoạn; bao nhiêu WIP tồn lại sau sự cố?
5. Tiêu chuẩn chất lượng và kiểm thử trước phát hành cần cải thiện ở đâu?
6. Thông tin tới khách hàng và bên liên quan có nhất quán, chính xác không?
7. Công việc phòng ngừa nào cần ưu tiên, ai có trách nhiệm và khi nào xem lại?

Hậu kiểm nên tập trung vào **nguyên nhân hệ thống và điều kiện làm việc**, không chỉ truy tìm một cá nhân để đổ lỗi.

## 11. Xử lý việc có hạn cố định mà không tạo khẩn cấp giả

Một sản phẩm có thể nhận yêu cầu thay đổi hợp đồng API, quy định dữ liệu hoặc tính năng phục vụ sự kiện ra mắt với thời hạn cụ thể. Cần phân biệt **Fixed Date** với **Expedite** để tránh lập kế hoạch phản ứng.

### 11.1. Tính ngược từ hạn chót cùng mức bất định

Một chính sách Fixed Date hữu ích có thể yêu cầu:

- Có bằng chứng về hạn chót và hậu quả nếu trễ.
- Đánh giá thời gian xử lý dựa trên dữ liệu, độ phức tạp và phụ thuộc.
- Đưa thời gian kiểm tra, tích hợp, phê duyệt bắt buộc vào kế hoạch.
- Theo dõi **work item age** và tín hiệu nguy cơ trước hạn.
- Có điểm quyết định giảm phạm vi hoặc tăng điều phối hợp lệ trước khi hết thời gian.

Thay vì đợi đến một ngày trước hạn, nhóm nên làm rõ **lúc nào phải bắt đầu để đạt mức tin cậy chấp nhận được**.

### 11.2. Ví dụ thời hạn tuân thủ

Một yêu cầu xác thực mới có hiệu lực vào cuối tháng sau. Nhóm ghi vào lớp Fixed Date, kiểm tra phụ thuộc với đối tác và bố trí việc tích hợp sớm. Nếu thử nghiệm cho thấy đối tác chưa cung cấp hỗ trợ cần thiết, nhóm báo rủi ro và tìm phương án đáp ứng đúng quy định trước khi sát hạn.

Nếu cuối cùng xuất hiện nguy cơ không tuân thủ cận kề, nhóm cần kích hoạt cơ chế ứng phó phù hợp; việc nâng cấp thành Expedite nên gắn với **mức rủi ro thực và quyết định có thẩm quyền**, không nhằm che giấu sự chậm trễ trong kế hoạch.

## 12. Xây dựng chính sách kéo việc Standard và bảo vệ công việc dài hạn

Một luồng Kanban ổn định không chỉ biết xử lý khẩn mà còn phải giúp công việc thường **được hoàn thành đều đặn và có thể dự báo**.

### 12.1. Quy tắc kéo việc rõ ràng

Ví dụ khi còn chỗ WIP, người thực hiện có thể kéo một hạng mục từ hàng chờ đã sắp theo chính sách. Nếu không có Expedite đang hoạt động, nhóm tiếp tục ưu tiên việc gần hoàn thành và việc phục vụ mục tiêu sản phẩm quan trọng.

Quy tắc cần làm rõ:

- Ai được bổ sung hoặc sắp thứ tự công việc?
- Khi nào hạng mục đủ thông tin để vào luồng?
- Trường hợp nào được bỏ qua thứ tự thông thường?
- Khi WIP đã đầy, nhóm ưu tiên gỡ chặn hay chấp nhận ngoại lệ như thế nào?
- Nếu công việc đang mở quá lâu, ai xem xét và đưa ra hành động?

**Việc kéo công việc vào hệ thống phải dựa trên năng lực thực và các chính sách đã thống nhất**, không chỉ vì có người đang tạm rảnh trong vài phút.

### 12.2. Tránh bỏ đói Standard và Intangible

Nếu Expedite diễn ra liên tục, công việc thông thường bị trì hoãn và các cải tiến phòng ngừa rủi ro không bao giờ được thực hiện. Nhóm nên quan sát:

- Tỷ lệ thời gian dành cho xử lý sự cố khẩn.
- Số hạng mục Standard/Intangible bị tạm dừng và tuổi của chúng.
- Công việc Fixed Date bị đe dọa.
- Số vấn đề lặp lại có thể giảm nếu đầu tư vào phòng ngừa.

Một giải pháp có thể là bố trí năng lực cho công việc bảo trì, giảm WIP, tăng quan sát sớm hoặc làm lại chính sách tiếp nhận. Nếu sự cố thường xuyên đến mức không còn là “ngoại lệ”, phải **cải tiến hệ thống và năng lực vận hành**, không chỉ tạo thêm nhãn Expedite.

## 13. Đo lường hiệu quả chính sách dịch vụ

Không thể kết luận một nhóm xử lý khẩn tốt chỉ vì “Expedite xong nhanh”. Cần xem **toàn bộ flow, mức độ phục hồi, chất lượng và kết quả với người dùng**.

| Chỉ số/tín hiệu | Ý nghĩa | Câu hỏi cải tiến |
|---|---|---|
| **WIP** | Số hạng mục đang thực hiện theo định nghĩa nhóm. | Khi có Expedite, WIP có bị mở rộng mất kiểm soát không? |
| **Cycle time** | Thời gian từ lúc bắt đầu tới lúc hoàn thành hạng mục. | Expedite và Standard có đang có thời gian hoàn thành phù hợp từng chính sách không? |
| **Throughput** | Số hạng mục hoàn thành trong một khoảng thời gian. | Khẩn cấp nhiều có làm giảm tổng khả năng hoàn thành không? |
| **Work item age** | Hạng mục chưa Done đã nằm trong luồng bao lâu. | Có việc thường bị bỏ quên hoặc nguy cơ vượt SLE không? |
| **Blocked time** | Thời gian thực tế không thể tiến do phụ thuộc. | Expedite có bị chờ phê duyệt, môi trường hoặc quyết định không? |
| **Số lượt Expedite** | Tần suất công việc được dùng lớp khẩn. | Có quá nhiều việc bị phân loại khẩn hoặc sự cố lặp lại không? |
| **Gián đoạn do Expedite** | Số việc tạm dừng, thời gian phục hồi, thay đổi dự báo. | Chi phí chen ngang có được nhìn thấy không? |
| **Thời gian phản ứng/giảm tác động** | Mốc ứng phó sự cố theo định nghĩa rõ. | Nhóm có ngăn thiệt hại đủ sớm không? |
| **Lỗi lặp / sự cố sau khắc phục** | Sự cố tương tự có quay lại không? | Có chỉ chữa triệu chứng mà chưa giải quyết nguyên nhân không? |
| **Outcome và guardrail** | Tác động tới người dùng, an toàn, bảo mật và chất lượng. | Xử lý nhanh có thực sự bảo vệ người dùng và giá trị sản phẩm không? |

### 13.1. Ví dụ dữ liệu giả định

| Quan sát | Tháng A | Tháng B | Tháng C |
|---|---:|---:|---:|
| Số hạng mục được phân loại Expedite | 2 | 6 | 11 |
| Throughput Standard (hạng mục/tháng) | 22 | 18 | 13 |
| Cycle time trung vị Standard (ngày) | 5 | 7 | 10 |
| Hạng mục Standard bị tạm dừng do chen ngang | 2 | 5 | 9 |

**Đây là dữ liệu minh họa, không phải ngưỡng chuẩn.** Xu hướng gợi ý rằng số Expedite tăng có thể làm giảm khả năng dự báo của việc thường. Nhưng trước khi kết luận, nhóm phải xem kích thước hạng mục, biến động năng lực, thay đổi tiêu chí phân loại, mức độ nghiêm trọng và số lượng yêu cầu mới.

Hành động hợp lý có thể là xem **nguyên nhân nhiều Expedite**, cải thiện giám sát và phòng ngừa, giới hạn chen ngang không chính đáng hoặc điều chỉnh năng lực ứng phó. Không nên chỉ đặt mục tiêu “giảm số nhãn Expedite” vì nó có thể khiến người ta **giấu sự cố thật**.

### 13.2. Dùng dữ liệu theo lớp dịch vụ

Một hạng mục Expedite có thể được hoàn thành nhanh do tập trung nhiều người; hạng mục Standard khác có thể phải chờ lâu vì bị ngắt. Báo cáo chỉ đưa ra cycle time trung bình chung có nguy cơ che khuất sự đánh đổi này.

Khi mẫu đủ phù hợp, nhóm nên xem phân phối cycle time, work item age và throughput **theo lớp dịch vụ**, cùng số vụ chen ngang và chi phí gián đoạn. Với những nhóm có ít Expedite, báo cáo định tính từng sự cố có thể hữu ích hơn những percentile thiếu độ tin cậy.

### 13.3. Kiểm tra tính ổn định của dự báo

Nếu nhóm đã công bố SLE cho Standard, hãy xem:

1. Hạng mục còn mở nào đang tiến gần hoặc vượt mức thời gian kỳ vọng?
2. Expedite xuất hiện có làm thay đổi phân phối cycle time Standard không?
3. Cần cải thiện chính sách kéo việc, WIP hoặc năng lực phục vụ không?
4. Có cần công bố lại SLE dựa trên dữ liệu mới, kèm giải thích phạm vi và độ tin cậy không?

Đừng tùy tiện đổi định nghĩa thời điểm bắt đầu/kết thúc chỉ để tỷ lệ “đúng hạn” đẹp hơn.

## 14. Cải tiến chính sách bằng các vòng phản hồi ngắn

Kanban khuyến khích **bắt đầu từ hệ thống hiện tại, làm minh bạch cách làm và cải tiến dần dựa trên dữ liệu**, thay vì buộc cả tổ chức đổi mọi vai trò ngay lập tức.

Một vòng cải tiến minh họa:

~~~mermaid
flowchart LR
    A["Đặt chính sách dịch vụ rõ"] --> B["Quan sát việc khẩn và flow thường"]
    B --> C["Xem tác động, blocker và dữ liệu"]
    C --> D["Chọn một thay đổi nhỏ"]
    D --> E["Thử trong một giai đoạn"]
    E --> F["Đánh giá chất lượng và khả năng dự báo"]
    F --> A
~~~

### 14.1. Ví dụ thay đổi có thể kiểm chứng

**Vấn đề:** Trong một tháng, nhiều yêu cầu “khẩn” được đưa vào ngay bởi bất kỳ bên liên quan nào; WIP tăng, nhiều story thường bỏ dở.

**Giả thuyết cải tiến:** Nếu yêu cầu Expedite phải có tác động và người quyết định rõ, đồng thời giới hạn số việc khẩn đang xử lý, nhóm sẽ giảm chen ngang không cần thiết mà vẫn phản ứng nhanh với sự cố thật.

**Thử nghiệm:** Dùng chính sách triage minh bạch, phân quyền và một luồng Expedite chủ đạo trong giai đoạn thử, cùng cơ chế ngoại lệ cho nhiều sự cố nghiêm trọng.

**Quan sát:** Số trường hợp được phân loại lại, thời gian phản ứng với sự cố thật, số việc Standard bị gián đoạn, work item age, chất lượng và phản hồi stakeholder.

**Quyết định:** Giữ, điều chỉnh hoặc bỏ một phần chính sách dựa trên bằng chứng. Nếu các sự cố nghiêm trọng bị chậm do quy trình phê duyệt, nhóm cần sửa quy trình ngay.

### 14.2. Duy trì nhịp xem lại không quá nặng

Nhóm có thể dùng buổi replenishment, service delivery review, cuộc xem xét rủi ro hoặc retrospective phù hợp để điều chỉnh chính sách. Tên cuộc họp không quan trọng bằng việc **thực sự xem dữ liệu và thay đổi cách làm**.

Với sự cố đang diễn ra, trao đổi trực tiếp hoặc kênh ứng phó được ưu tiên; không chờ một buổi họp định kỳ chỉ để có quyền xử lý.

## 15. Kết hợp chính sách Kanban với Scrum và XP

**Kanban và Scrum không phải hai lựa chọn loại trừ nhau.** Nhóm Scrum có thể sử dụng thực hành Kanban để nhìn thấy flow, giới hạn WIP và xử lý blocker, trong khi vẫn giữ các accountability, artifact, commitment và sự kiện của Scrum.

### 15.1. Khi dùng Scrum

Nếu một sự cố nghiêm trọng xuất hiện trong Sprint:

- Developers chủ động xác minh và phối hợp xử lý theo thẩm quyền.
- Product Owner được thông tin về tác động tới thứ tự ưu tiên và có thể cùng Developers làm rõ/thương lượng phạm vi Sprint khi cần.
- Scrum Master giúp team và tổ chức tháo trở ngại, duy trì minh bạch và hiệu quả Scrum.
- Team xem tác động tới **Sprint Goal** và **Definition of Done**, không tự động bỏ qua chất lượng để giữ mọi hạng mục đã chọn.
- Tại Sprint Review và Retrospective, team học từ kết quả sản phẩm và cách phản ứng với thay đổi.

Một lỗi production nghiêm trọng cần được xử lý theo cơ chế ứng phó ngay cả khi chưa đến sự kiện Scrum tiếp theo. Sprint có độ dài cố định không có nghĩa **mọi điều kiện thực tế đều phải chờ đến Sprint sau**.

### 15.2. Khi dùng XP

Các thực hành **Extreme Programming (XP)** như tích hợp liên tục, kiểm thử tự động, TDD, lập trình cặp và refactoring có thể giúp giảm thời gian phát hiện và sửa lỗi, cũng như giữ sản phẩm an toàn sau khi khắc phục.

Ví dụ, một bộ kiểm thử kiểm tra idempotency của lệnh thanh toán có thể giúp tránh tái diễn lỗi tính tiền lặp. Tuy vậy, **kiểm thử xanh chưa tự chứng minh sự cố thực tế đã chấm dứt**; cần xác minh hiệu quả khắc phục và theo dõi vận hành phù hợp.

### 15.3. Lựa chọn cách phối hợp theo loại công việc

| Loại công việc | Thực hành hữu ích | Điều không nên nhầm |
|---|---|---|
| Sự cố cần giảm tác động ngay | Quy trình ứng phó + Expedite rõ thẩm quyền + thông tin thống nhất. | Kanban board thay thế quy trình bảo mật, pháp lý hoặc an toàn. |
| Tính năng thông thường | Product Backlog, chính sách kéo việc, WIP, phản hồi người dùng. | Càng nhiều ticket mở thì càng nhanh tạo giá trị. |
| Hạng mục hạn cố định | Lập kế hoạch sớm, SLE/dữ liệu dự báo, chuẩn bị phụ thuộc. | Chờ đến sát deadline rồi mới gọi là khẩn. |
| Công việc cải tiến chất lượng | Giữ năng lực phù hợp, retrospection, kiểm thử và refactoring. | Không thấy giá trị ngay nghĩa là không cần làm. |

## 16. Những phản mẫu thường gặp

| Phản mẫu | Hệ quả | Thay đổi nên thử |
|---|---|---|
| **Mọi yêu cầu đều là P0/Expedite.** | Lớp dịch vụ mất ý nghĩa, công việc thường luôn bị ngắt. | Yêu cầu tiêu chí tác động và quyền phân loại minh bạch. |
| **Ai có chức vụ cao hơn tự động chen lên trước.** | Ưu tiên không phản ánh chi phí trì hoãn hoặc rủi ro thực. | Áp dụng chính sách chung và cơ chế ngoại lệ có trách nhiệm. |
| **Không giới hạn việc khẩn đang làm.** | Nhiều sự cố cạnh tranh cùng năng lực, phản ứng chậm và hỗn loạn. | Giới hạn đồng thời phù hợp; có quy trình cho nhiều sự cố nghiêm trọng. |
| **Chỉ tạo cột “Khẩn cấp” nhưng không có trạng thái xử lý.** | Việc có nhãn nhưng thiếu người điều phối và điều kiện Done. | Giữ trạng thái luồng; dùng swimlane/nhãn lớp dịch vụ đúng nghĩa. |
| **Gọi Fixed Date thành Expedite vào phút chót.** | Trễ hạn có thể lặp đi lặp lại. | Lập kế hoạch và theo dõi rủi ro trước hạn. |
| **Dừng việc thường nhưng không đánh dấu.** | Dự báo sai, stakeholder không biết chi phí gián đoạn. | Ghi việc bị ngắt, cập nhật trạng thái và ước lượng lại. |
| **Chỉ đo thời gian sửa lỗi, không đo thời gian tiếp nhận.** | Có thể che giấu khoảng chờ trước khi phản ứng. | Phân biệt response, mitigation, cycle và resolution time. |
| **Khắc phục tạm xong rồi đóng hết việc.** | Nguyên nhân và phòng ngừa không được theo dõi. | Hậu kiểm, tách công việc tiếp theo và ưu tiên theo rủi ro còn lại. |
| **Dùng mock hoặc demo để tuyên bố sự cố đã được sửa.** | Lỗi tích hợp thật có thể còn tồn tại. | Kiểm chứng trong môi trường phù hợp, giám sát tác động sau sửa. |
| **Bỏ qua kiểm thử và bảo mật vì “việc khẩn”.** | Tạo sự cố mới hoặc làm thiệt hại lớn hơn. | Giảm phạm vi, phối hợp xử lý nhanh nhưng giữ kiểm soát bắt buộc. |
| **Tăng overtime như biện pháp thường trực.** | Mất khả năng phát triển bền vững, tăng lỗi và cạn năng lực. | Đánh giá năng lực trực, phòng ngừa, WIP và phân bổ công việc. |
| **Dùng SLA làm SLE hoặc dùng SLE làm cam kết chắc chắn.** | Hiểu sai độ tin cậy và nghĩa vụ dịch vụ. | Định nghĩa rõ chỉ số, phạm vi, mức tin cậy và cam kết pháp lý riêng. |
| **Tối ưu số việc Expedite giảm bằng cách không ghi nhận.** | Sự cố thật bị che giấu, dữ liệu mất giá trị. | Tập trung vào an toàn, chất lượng, nguyên nhân và khả năng dự báo. |

## 17. Bài tập thực hành: phân loại và thiết kế chính sách

Giả sử một nhóm phát triển nền tảng học trực tuyến đang có các hạng mục:

| Mã | Tình huống |
|---|---|
| A | Lỗi mới làm học viên A xem được dữ liệu tiến độ riêng tư của học viên B. |
| B | Bộ phận kinh doanh muốn đổi banner trước buổi giới thiệu vào sáng mai. |
| C | Một quy định mới yêu cầu thay đổi quy trình lưu dữ liệu sau năm tuần. |
| D | Bộ kiểm thử tự động lâu không được bảo trì, làm nhóm chậm phát hiện lỗi. |
| E | Nhiều học viên mới không hiểu cách tiếp tục bài cũ; tính năng vẫn hoạt động an toàn. |
| F | Toàn bộ học viên đang không đăng nhập được do dịch vụ xác thực ngừng hoạt động. |

### Câu hỏi 1 — Phân loại nào có cơ sở?

**Gợi ý phân tích:**

- **A:** có thể cần kích hoạt ứng phó bảo mật và Expedite vì nguy cơ lộ dữ liệu đang diễn ra.
- **B:** chưa đủ bằng chứng là Expedite; nên đánh giá giá trị/hạn thật theo chính sách Standard hoặc Fixed Date.
- **C:** phù hợp Fixed Date nếu mốc áp dụng có thật; cần lập kế hoạch, không đợi sát hạn.
- **D:** công việc Intangible/Standard về chất lượng; nếu xuất hiện nguy cơ nghiêm trọng cụ thể có thể đổi lớp.
- **E:** có thể ưu tiên trong Product Backlog dựa trên outcome; không tự động chen ngang như incident.
- **F:** có thể cần ứng phó sự cố nghiêm trọng ngay và Expedite vì dịch vụ thiết yếu đang ngừng.

Đây là **phân loại ban đầu**, phải được kiểm tra bằng tác động, phạm vi, dữ liệu và chính sách thật của tổ chức.

### Câu hỏi 2 — A và F xảy ra đồng thời thì sao?

**Gợi ý phân tích:** không bỏ qua A hoặc F chỉ vì chính sách mục tiêu một Expedite. Kích hoạt cơ chế điều phối sự cố đồng thời, đánh giá phạm vi và thiệt hại, huy động năng lực phù hợp và phân công đầu mối. Có thể cần quyết định ưu tiên bảo vệ dữ liệu và khôi phục truy cập theo cách giảm rủi ro tổng thể. Ghi minh bạch giới hạn năng lực, quyết định và thông tin tới bên liên quan.

### Câu hỏi 3 — Khi sự cố kết thúc, phần việc nào quay lại Standard?

**Gợi ý phân tích:** chỉ hạ cấp khi điều kiện thoát chế độ khẩn đã được đáp ứng. Các cải tiến phòng ngừa, nâng cấp test hoặc làm lại kiến trúc có thể trở về Standard/Intangible nếu không còn rủi ro tức thời; những nghĩa vụ xử lý dữ liệu, khách hàng hoặc tuân thủ còn cấp bách phải giữ mức ưu tiên phù hợp.

### Câu hỏi 4 — Đo chính sách có hiệu quả hay không bằng gì?

**Gợi ý phân tích:** xem response/mitigation time cho sự cố thật, số việc bị gián đoạn, WIP, cycle time Standard, SLE theo lớp, số sự cố lặp lại, chất lượng sau sửa và phản hồi stakeholder. Không chỉ đếm số ticket màu đỏ đã đóng.

## 18. Checklist áp dụng trong nhóm

Trước khi đưa hạng mục vào lớp khẩn cấp:

- [ ] Có mô tả rõ **tác động, tính khẩn và hậu quả nếu chờ** không?
- [ ] Đã phân biệt sự cố đang xảy ra với yêu cầu có hạn hoặc đề xuất thông thường chưa?
- [ ] Có bằng chứng ban đầu và ghi rõ điều còn chưa chắc không?
- [ ] Người có quyền xác nhận Expedite và người điều phối đã rõ chưa?
- [ ] Có kênh ứng phó riêng cho sự cố an toàn, bảo mật và nghĩa vụ bắt buộc chưa?
- [ ] Đã biết năng lực ứng phó và giới hạn số việc khẩn đang xử lý chưa?
- [ ] Những hạng mục bị gián đoạn và rủi ro Fixed Date có được minh bạch không?
- [ ] Có người phụ trách thông báo và mốc cập nhật tiếp theo không?
- [ ] Có tiêu chí xác nhận đã giảm tác động và kết thúc chế độ khẩn không?

Sau khi xử lý:

- [ ] Kết quả khắc phục đã được kiểm chứng với rủi ro phù hợp chưa?
- [ ] Những vấn đề còn lại đã được ghi và ưu tiên rõ ràng chưa?
- [ ] Công việc Standard/Intangible bị ngắt đã có kế hoạch phục hồi chưa?
- [ ] Dự báo hoặc SLE cần xem xét lại có được thông báo không?
- [ ] Nhóm có đánh giá nguyên nhân, thời gian chờ, lỗi lặp và biện pháp phòng ngừa không?
- [ ] Có thay đổi chính sách nào cần thử và đo kết quả ở chu kỳ tiếp theo không?

Checklist là **công cụ hỗ trợ thảo luận và phản ứng nhanh**, không phải cổng phê duyệt bắt buộc khiến sự cố nghiêm trọng phải chờ đợi. Nhóm cần thiết kế quy trình đủ nhanh khi thực sự khẩn và đủ chặt để không lạm dụng ưu tiên.

## 19. Kết luận

**Xử lý công việc khẩn cấp bằng chính sách dịch vụ rõ ràng** là cách Kanban kết hợp khả năng phản ứng nhanh với sự minh bạch và tính ổn định của dòng công việc. Thay vì để mọi yêu cầu tự tuyên bố là khẩn, nhóm dựa trên **tác động, chi phí trì hoãn, hạn thật, rủi ro và bằng chứng** để chọn cách phục vụ.

Lớp **Expedite** dành cho những tình huống cần ưu tiên ngoại lệ và phải có cơ chế điều phối, giới hạn WIP phù hợp, thông tin thống nhất, tiêu chí kết thúc và hậu kiểm. **Fixed Date** giúp chuẩn bị việc có hạn trước khi thành sự cố; **Standard** giữ nhịp bàn giao thông thường; **Intangible** bảo vệ các đầu tư có ích cho khả năng phát triển và phòng ngừa rủi ro dài hạn. Những lớp này là thực hành tùy chỉnh theo bối cảnh, không phải một bộ luật cứng của mọi hệ thống Kanban.

Việc theo dõi **WIP, cycle time, throughput, work item age, blocker và mức dịch vụ kỳ vọng** giúp nhóm hiểu chi phí chen ngang và cải tiến chính sách. Khi kết hợp với Scrum và kỹ thuật XP, quản lý việc khẩn không chỉ là **chữa cháy nhanh**, mà còn là **giảm sự cố lặp lại, giữ chất lượng, học từ thực tế và bảo toàn khả năng giao giá trị bền vững**.

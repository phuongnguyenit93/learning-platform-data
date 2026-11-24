# Tránh biến ước lượng thành hạn chót bắt buộc hoặc công cụ so sánh cá nhân

“Story này khoảng 8 điểm, vậy cuối thứ Sáu phải xong nhé.” Một quản lý nói như vậy sau buổi ước lượng. Lập trình viên không đồng ý vì yêu cầu còn phụ thuộc vào dịch vụ của nhóm khác, nhưng ngại nêu rủi ro. Sang tuần sau, công việc trễ; bảng thống kê ghi người đó “hoàn thành ít điểm hơn đồng nghiệp”, dù họ đã dành thời gian sửa lỗi tích hợp và hỗ trợ cả nhóm.

Vấn đề không nằm ở việc nhóm **có ước lượng**. Vấn đề nằm ở việc một nhận định có bất định đã bị biến thành **lời hứa về ngày hoàn tất** và sau đó thành **thước đo đánh giá cá nhân**. Cách dùng này làm mất chức năng quan trọng nhất của ước lượng: hỗ trợ trao đổi, nhận diện rủi ro và đưa ra quyết định trong điều kiện chưa biết hết tương lai.

Trong Agile, nhóm cần có khả năng **dự báo đủ tốt để phối hợp** và đồng thời **thay đổi kế hoạch khi dữ liệu mới xuất hiện**. Kỷ luật về chất lượng, minh bạch và trách nhiệm vẫn cần thiết. Điều cần tránh là tạo ra “độ chắc chắn giả” khiến mọi người giấu trở ngại, giảm tiêu chuẩn hoàn tất hoặc làm đẹp số liệu.

Bài học thuộc chương **Ước lượng và dự báo** của module **AGILE_DEVELOPMENT**. Theo mục tiêu của module, phần mềm được phát triển thích ứng nhờ phản hồi sớm, giao từng phần tăng trưởng và cải tiến liên tục. Những thực hành như user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc chỉ thực sự có ích khi các con số được dùng để **học hỏi và chọn hành động**, không để trừng phạt người nêu bất định.

Sau bài này, bạn có thể:

- Phân biệt **ước lượng, dự báo, mục tiêu, deadline và cam kết** trong trao đổi sản phẩm.
- Giải thích vì sao story points, velocity và số ticket hoàn thành không phải chỉ số năng suất cá nhân.
- Trình bày một dự báo bằng **giả định, khoảng kết quả, mức độ tin cậy, rủi ro và thời điểm cập nhật**.
- Thương lượng phạm vi khi có ngày phát hành cố định mà không âm thầm cắt kiểm thử hoặc tăng giờ làm.
- Dùng throughput, cycle time, WIP và lịch sử giao hàng để hỗ trợ quyết định trong Scrum hoặc Kanban.
- Nhận diện tín hiệu chỉ số bị sử dụng sai và đề xuất cách đánh giá, cải tiến công bằng hơn.
- Thực hành một cuộc trao đổi với người liên quan khi dự báo và deadline đang mâu thuẫn.

## 1. Phân biệt các khái niệm trước khi bàn ngày hoàn tất

Nhiều tranh cãi bắt đầu vì cùng một con số đang được hiểu theo nhiều nghĩa.

| Khái niệm | Câu hỏi nó trả lời | Ví dụ | Điều không được suy ra |
| --- | --- | --- | --- |
| **Ước lượng (estimate)** | Với hiểu biết hiện tại, công việc có quy mô hoặc mức nỗ lực tương đối thế nào? | Story A được nhóm xem là khoảng 5 điểm tương đối. | Chắc chắn mất 5 ngày, hoặc người nhận story phải xong trong 5 ngày. |
| **Dự báo (forecast)** | Dựa trên dữ liệu và giả định, kết quả nào có thể đạt vào khoảng thời gian nào? | Với các điều kiện hiện tại, nhiều khả năng hoàn tất phạm vi nhỏ trong vài tuần. | Ngày dự báo là bảo đảm, bất kể sự cố hay thay đổi. |
| **Mục tiêu (goal/target)** | Tổ chức hoặc nhóm mong muốn đạt kết quả nào? | Giúp người học quay lại bài dễ dàng trước đợt thử nghiệm. | Mục tiêu tự chứng minh năng lực hoặc khả năng hoàn tất. |
| **Hạn chót (deadline)** | Thời điểm nào có ràng buộc bên ngoài hay quyết định quản lý? | Cổng thanh toán cũ ngừng hỗ trợ vào ngày được nhà cung cấp thông báo. | Mọi phạm vi dự kiến đều phải hoàn thành mà không cần đánh đổi. |
| **Cam kết (commitment)** | Ai nhận trách nhiệm cho mục tiêu, hành động và tiêu chuẩn nào? | Nhóm cùng theo đuổi Sprint Goal và minh bạch về rủi ro; Increment đáp ứng DoD. | Mọi ước lượng ban đầu trở thành cam kết không thể điều chỉnh. |
| **Thực tế (actual)** | Điều gì đã xảy ra? | Một lát công việc hoàn tất sau 7 ngày kể từ khi bắt đầu. | Ước lượng trước đó “sai” là bằng chứng có người làm việc kém. |

**Ước lượng là thông tin để ra quyết định, không phải nghĩa vụ tự phát sinh.** Nếu tổ chức cần một cam kết chính thức về ngày, phạm vi hoặc chất lượng, các bên phải **trao đổi và chấp nhận cam kết ấy một cách minh bạch** trên cơ sở rủi ro và quyền quyết định phù hợp. Không được biến một con số được phát biểu trong thảo luận thành lời hứa mà người phát biểu chưa hề đưa ra.

### 1.1. Quy mô công việc, nỗ lực và thời gian lịch là ba đại lượng khác nhau

Một yêu cầu có thể cần ít giờ viết code nhưng phải chờ nhiều ngày để có tài khoản truy cập hệ thống đối tác. Một thay đổi lớn lại có thể được cả nhóm hoàn tất sớm nhờ chia nhỏ và phối hợp tốt.

- **Quy mô tương đối:** mức phức tạp, khối lượng và bất định so với các mục khác trong cùng cách ước lượng của nhóm.
- **Nỗ lực (effort):** mức công sức được bỏ ra; có thể diễn đạt bằng giờ hoặc ngày công trong một số ngữ cảnh.
- **Thời gian lịch/elapsed time:** khoảng thời gian từ lúc bắt đầu đến lúc hoàn tất, bao gồm cả chờ đợi, bàn giao, review và xử lý sự cố.

Trong hệ thống có hàng chờ, **thời gian lịch thường không bằng tổng giờ lao động trực tiếp**. Nhầm lẫn hai đại lượng này tạo ra deadline thiếu cơ sở.

### 1.2. Ngày cố định có thể là thật; suy đoán “mọi tính năng phải xong” có thể là giả

Nếu có ngày hết hiệu lực chứng chỉ, ngày thay đổi quy định hoặc một sự kiện đã cam kết với khách hàng, nhóm cần tôn trọng ràng buộc thực. Nhưng một ngày cố định **không tự làm phạm vi công việc trở nên nhỏ hơn**.

Khi dự báo không phù hợp ngày cần đạt, lựa chọn hợp lệ có thể gồm giảm phạm vi phụ, tìm phương án thay thế, thay đổi cách triển khai, huy động nguồn lực với đánh giá tác động hoặc đàm phán lại cam kết. **Không nên lấy việc bỏ kiểm thử, bỏ bảo mật hoặc làm ngoài giờ kéo dài làm giả định mặc định**.

## 2. Vì sao ước lượng vốn có bất định?

Phát triển phần mềm là công việc khám phá. Ngay cả khi nhóm hiểu người dùng và công nghệ, một số chi tiết vẫn chỉ xuất hiện khi thử tích hợp, chạy kiểm thử hoặc quan sát sử dụng thật.

Các nguồn bất định thường gặp:

| Nguồn | Ví dụ | Cách giảm bất định |
| --- | --- | --- |
| **Yêu cầu** | Chưa rõ khi nào một video được coi là “hoàn thành”. | Trao đổi ví dụ, user story và acceptance criteria với người hiểu nghiệp vụ. |
| **Kỹ thuật** | Chưa chắc API của đối tác hỗ trợ lưu trạng thái theo cách dự kiến. | Spike/PoC ngắn với câu hỏi, tiêu chí kết thúc rõ. |
| **Phụ thuộc** | Chờ nhóm khác cung cấp quyền truy cập hay thay đổi hợp đồng API. | Làm rõ đầu mối, thời điểm và phương án dự phòng. |
| **Chất lượng** | Có thể phát hiện lỗi dữ liệu hoặc vấn đề hiệu năng trong kiểm thử. | Tích hợp thường xuyên, kiểm thử tự động phù hợp, quan sát sớm. |
| **Năng lực và luồng** | Thành viên phải hỗ trợ sự cố; công việc chờ review kéo dài. | Giới hạn WIP, nhìn hàng đợi và dữ liệu dòng công việc. |
| **Thị trường/người dùng** | Người dùng thử không cần tính năng như nhóm tưởng. | Giao lát nhỏ, thu phản hồi và điều chỉnh backlog. |

Ước lượng thường dựa vào **thông tin tại thời điểm ước lượng**. Nếu giả định thay đổi đáng kể, việc cập nhật dự báo là hành vi có trách nhiệm. Giữ nguyên con số chỉ để tránh “mất uy tín” khiến người liên quan đưa quyết định bằng thông tin đã lỗi thời.

### Chi phí của độ chính xác giả

Hãy so hai cách trình bày:

> “Chính xác 9 ngày nữa xong toàn bộ, không có gì phải lo.”

và:

> “Với phạm vi hiện tại, chúng tôi dự kiến khoảng 2–3 tuần để hoàn tất các lát cốt lõi. Rủi ro chính là tích hợp đối tác; sẽ cập nhật sau khi thử tích hợp vào thứ Tư.”

Thông điệp thứ hai có thể kém “đẹp” hơn, nhưng cho người liên quan **thông tin dùng được**: khoảng dự báo, giả định, nguồn rủi ro và mốc cập nhật.

Không phải lúc nào cũng cần mô hình xác suất phức tạp. Điều tối thiểu là **không ngụy tạo mức chắc chắn vượt quá bằng chứng sẵn có**.

## 3. Vì sao biến ước lượng thành deadline gây hại?

Khi người ước lượng hiểu rằng con số sẽ trở thành cam kết cứng, cách họ ước lượng và hợp tác có thể thay đổi.

~~~mermaid
flowchart TD
    A["Ước lượng ban đầu còn bất định"] --> B["Bị chuyển thành deadline cố định"]
    B --> C["Rủi ro bị che giấu hoặc ước lượng bị thổi phồng"]
    C --> D["Chậm phản hồi, tích lũy WIP, giảm minh bạch"]
    D --> E["Áp lực tăng khi phát hiện lệch kế hoạch"]
    E --> F["Có nguy cơ cắt kiểm thử, làm ngoài giờ hoặc 'đóng ticket' sớm"]
    F --> G["Chất lượng và dữ liệu dự báo trở nên kém tin cậy"]
    G --> H["Nhóm khó học từ thực tế; dự báo tiếp tục sai"]
    H --> B
~~~

Sơ đồ mô tả **một vòng phản hồi có thể xảy ra**, không khẳng định mọi nhóm đều hành xử như vậy. Một tổ chức có thể có deadline cần thiết và vẫn giữ hiệu quả nếu công khai phạm vi, rủi ro, năng lực và cách điều chỉnh.

### Những biểu hiện đáng chú ý

1. **Ước lượng phòng thủ:** mọi người cộng nhiều “đệm” vào từng story vì sợ bị phạt nếu trễ.
2. **Trì hoãn thông báo:** thành viên phát hiện phụ thuộc trễ nhưng chờ đến gần hạn mới nói, vì nói sớm từng bị xem là viện cớ.
3. **Giảm chất lượng âm thầm:** kiểm thử tích hợp hoặc xử lý trường hợp lỗi bị đẩy sang “sau phát hành” dù cần thiết.
4. **Trộn Done với code complete:** bảng công việc ghi hoàn tất khi chưa đáp ứng Definition of Done.
5. **Chọn việc dễ để có điểm:** nhóm ưu tiên ticket ít rủi ro nhưng ít giá trị, né các lỗi phức tạp hoặc công việc cần phối hợp.
6. **Nợ kỹ thuật và quá tải:** làm ngoài giờ thường xuyên khiến tốc độ trước mắt có vẻ tăng nhưng năng lực bền vững và khả năng dự báo suy giảm.

Những tín hiệu này không chứng minh một cá nhân thiếu trách nhiệm; chúng có thể cho thấy **cơ chế quản lý đang khuyến khích hành vi trái mục tiêu**.

## 4. Story points và velocity không phải đồng hồ hay bảng xếp hạng

**Story points** là cách một số nhóm biểu diễn **quy mô tương đối** của Product Backlog Items, thường cân nhắc nỗ lực, độ phức tạp và bất định. Scrum không bắt buộc dùng story points, Fibonacci, Planning Poker hoặc velocity.

Ví dụ, cùng một nhóm ước lượng:

- Story A: 3 điểm — thay đổi đã quen, ít phụ thuộc.
- Story B: 8 điểm — luồng mới có rủi ro tích hợp.
- Story C: 13 điểm — nhiều trường hợp chưa rõ, có thể cần chia nhỏ.

Điều này **không** có nghĩa B chắc chắn mất \(8/3\) lần thời gian A. Điểm chỉ có ý nghĩa theo quy ước và trải nghiệm của **nhóm đã tạo ra thang điểm**.

### 4.1. Vì sao không nên so velocity giữa các nhóm?

Giả sử:

| Nhóm | Quy ước ước lượng | Hoàn tất trong Sprint |
| --- | --- | ---: |
| **Nhóm A** | Story đăng nhập cơ bản được xem là 3 điểm. | 24 điểm |
| **Nhóm B** | Cùng loại story được xem là 8 điểm. | 48 điểm |

Không thể từ đó kết luận Nhóm B làm việc hiệu quả gấp đôi. Hai nhóm có **hệ quy chiếu khác nhau**, sản phẩm và mức phụ thuộc có thể khác nhau, thậm chí cách chia story và Definition of Done cũng khác.

Velocity có thể hỗ trợ **lập kế hoạch nội bộ của một nhóm ổn định**, nhưng không phải thước đo chuẩn để xếp hạng liên nhóm, cá nhân hoặc xác định thưởng phạt.

### 4.2. Vì sao không thể quy story points cho từng cá nhân?

Một story hoàn tất thường có đóng góp của nhiều người: làm rõ yêu cầu, lập trình, review, thiết kế, kiểm thử, vận hành và hỗ trợ xử lý phụ thuộc. Người được gắn tên vào ticket **không phải lúc nào cũng là người tạo ra toàn bộ kết quả**.

Khi cộng điểm theo cá nhân, hệ thống có thể phạt người:

- Review code nhiều, giúp người khác hoàn tất story.
- Giải quyết lỗi sản xuất hoặc sự cố khó ước lượng.
- Hỗ trợ người mới, lập trình cặp hoặc chia sẻ kiến thức.
- Phát hiện rủi ro bảo mật làm nhóm phải sửa thiết kế.
- Làm công việc nền tảng giảm lỗi dài hạn nhưng không có nhiều story points.

Ngược lại, một người có thể tăng “điểm cá nhân” bằng cách nhận nhiều story nhỏ và tránh việc khó. Tổng điểm cao **không tự nói lên đóng góp vào kết quả sản phẩm**.

### 4.3. Tránh “mục tiêu điểm” tự làm sai dữ liệu

Nếu người quản lý yêu cầu “Sprint sau phải tăng từ 30 lên 40 điểm”, nhóm có thể:

- Tăng điểm ước lượng từng story.
- Tách một yêu cầu thành nhiều mục nhỏ chỉ để đếm nhiều hơn.
- Giảm tiêu chuẩn Done để đóng nhiều ticket.
- Đưa các việc khó, ít được chấm điểm ra ngoài thống kê.

Khi chỉ số trở thành mục tiêu bị thưởng phạt, **nó có thể mất giá trị như tín hiệu quan sát**. Đây là lý do phải hỏi: con số có phản ánh kết quả người dùng, chất lượng và năng lực giao hàng thật hay chỉ phản ánh cách ghi dữ liệu?

## 5. Ước lượng có ích khi nào và nên thực hiện thế nào?

Không phải mọi công việc đều cần ước lượng bằng điểm. Nhu cầu ước lượng có thể là chọn mức đầu tư, đánh giá tính khả thi của một phương án, lập kế hoạch phát hành hoặc nhận diện công việc quá lớn.

### 5.1. Xác định quyết định cần hỗ trợ trước khi ước lượng

Thay vì hỏi “story này bao nhiêu điểm?”, hãy hỏi:

- **Con số này dùng để quyết định gì?** So sánh lựa chọn, phát hiện story quá lớn hay dự báo khoảng thời gian?
- **Mức độ chính xác cần tới đâu?** Quyết định đầu tư lớn cần dữ liệu khác với việc chọn một story nhỏ cho Sprint.
- **Còn điều gì chưa biết đáng kể?** Có thể thu hẹp bằng hỏi đáp, ví dụ hoặc spike?
- **Ai đủ hiểu để ước lượng?** Người làm công việc và người hiểu rủi ro liên quan cần tham gia.
- **Khi nào nên ngừng phân tích?** Tránh tốn nhiều ngày để ước lượng một công việc nhỏ hơn chi phí ước lượng.

### 5.2. Làm rõ user story trước, chứ không dựa trên tiêu đề

Một story “Thêm báo cáo học tập” có thể là danh sách ba chỉ số hoặc hệ thống phân tích đa chiều. Nếu nhóm ước lượng khi chưa rõ đối tượng, trường hợp sử dụng, dữ liệu và điều kiện hoàn tất, độ phân tán của các con số là tín hiệu cần **làm rõ phạm vi**.

Ví dụ story:

> **Là** giảng viên phụ trách một lớp, **tôi muốn** xem danh sách học viên có bài quá hạn, **để** chủ động hỗ trợ người học cần giúp đỡ.

Tiêu chí chấp nhận được thảo luận cùng người hiểu nghiệp vụ:

~~~gherkin
Feature: Xem học viên có bài quá hạn trong lớp phụ trách

Scenario: Có học viên quá hạn
  Given giảng viên đã đăng nhập và có quyền xem lớp "Java nhập môn"
  And lớp có học viên chưa hoàn thành bài đã tới hạn
  When giảng viên mở danh sách học viên quá hạn
  Then hệ thống hiển thị đúng học viên và bài quá hạn thuộc lớp đó

Scenario: Không có học viên quá hạn
  Given giảng viên có quyền xem lớp "Java nhập môn"
  And không có học viên quá hạn trong lớp
  When giảng viên mở danh sách
  Then hệ thống hiển thị trạng thái không có học viên quá hạn

Scenario: Không có quyền xem lớp
  Given giảng viên không có quyền xem lớp "Lớp B"
  When giảng viên yêu cầu danh sách học viên quá hạn của "Lớp B"
  Then hệ thống từ chối truy cập theo chính sách
  And không tiết lộ dữ liệu lớp đó
~~~

Giờ nhóm có thể trao đổi về một **lát dọc có kết quả kiểm chứng được**. Task UI, API, truy vấn dữ liệu và kiểm thử là các thành phần hỗ trợ story; không nên tự động chia thành những story ngang được cộng điểm riêng nhưng chưa tạo hành vi dùng được.

### 5.3. Planning Poker và ý kiến khác nhau

Một nhóm sử dụng ước lượng tương đối có thể dùng Planning Poker: mỗi người suy nghĩ độc lập, cùng lộ điểm, rồi thảo luận lý do chênh lệch.

Ví dụ:

- Người A: **3 điểm**, vì cho rằng có sẵn API phù hợp.
- Người B: **8 điểm**, vì biết dữ liệu hiện tại thiếu quyền truy cập theo lớp.
- Người C: **13 điểm**, vì chưa rõ yêu cầu xử lý học viên chuyển lớp.

Mục đích không phải lấy trung bình \((3+8+13)/3 = 8\) rồi coi 8 là đáp án khoa học. **Chênh lệch là thông tin cần điều tra.** Nhóm có thể làm rõ quyền truy cập, chia lát hoặc thử một trường hợp dữ liệu trước khi quyết định.

### 5.4. Có thể không ước lượng từng story

Nếu nhóm có luồng ổn định, phần lớn mục được chia đủ nhỏ và có dữ liệu cycle time/throughput đáng tin, họ có thể dùng **dự báo theo dòng công việc** thay cho cộng story points. Điều đó không nghĩa là “khỏi lập kế hoạch”; nhóm vẫn cần làm rõ giá trị, phân chia phạm vi và quản lý rủi ro.

Chọn cách ít tốn kém nhất mà **vẫn hỗ trợ quyết định tốt**. Không nên biến việc ước lượng thành một nghi thức phải hoàn tất trước mọi công việc.

## 6. Dự báo là một phân bố khả năng, không phải một ngày chắc chắn

**Forecast** nên giúp người liên quan hiểu điều gì có thể hoàn tất, vào khoảng thời gian nào, với độ chắc chắn ra sao và dựa trên những giả định nào.

Ví dụ cách nói thiếu thông tin:

> “Chắc chắn ngày 15 sẽ hoàn thành.”

Cách nói dùng được hơn:

> “Nếu phạm vi không đổi và phụ thuộc đối tác được giải quyết trong tuần này, dự báo hiện tại cho bản lõi là khoảng cuối tuần thứ ba đến tuần thứ tư. Chúng tôi sẽ cập nhật sau khi kiểm tra tích hợp. Các mục phân tích nâng cao chưa nằm trong dự báo này.”

Một forecast tốt có thể bao gồm:

1. **Phạm vi:** hạng mục hoặc kết quả nào được tính vào.
2. **Điểm bắt đầu và điểm Done:** định nghĩa nhất quán; DoD không bị thay đổi lén.
3. **Dữ liệu:** từ nhóm và loại công việc nào, trong khoảng thời gian nào.
4. **Giả định:** năng lực, WIP, phụ thuộc, môi trường, việc khẩn.
5. **Khoảng kết quả hoặc xác suất:** nêu mức tin cậy khi dữ liệu cho phép, không dùng phần trăm tự chế.
6. **Rủi ro chính:** yếu tố có thể làm forecast dịch chuyển.
7. **Mốc cập nhật:** khi dữ liệu mới xuất hiện hoặc theo chu kỳ thích hợp.
8. **Người chịu trách nhiệm về quyết định:** ai chọn phạm vi/phát hành khi forecast thay đổi.

### Không nên nhầm ba loại phát biểu

| Phát biểu | Ý nghĩa |
| --- | --- |
| “**Chúng ta muốn** ra bản thử trước hội nghị.” | Mục tiêu hoặc mong muốn thời điểm. |
| “**Dựa trên dữ liệu**, khoảng ngày X–Y có vẻ khả thi nếu điều kiện A/B giữ nguyên.” | Dự báo có điều kiện. |
| “**Chúng ta đồng ý cam kết** giao phạm vi S trước ngày D theo các điều kiện và cơ chế xử lý rủi ro đã nêu.” | Cam kết được thương lượng rõ ràng. |

Cả ba phát biểu đều có thể có giá trị, miễn là **không đánh tráo ý nghĩa**.

## 7. Ví dụ dự báo bằng throughput: tính được gì và chưa tính được gì?

Giả sử một nhóm dùng Kanban, hoặc một Scrum Team đang theo dõi luồng công việc, có số mục **đạt Done theo cùng tiêu chuẩn** trong sáu tuần gần đây:

| Tuần | Mục Done |
| --- | ---: |
| 1 | 3 |
| 2 | 4 |
| 3 | 5 |
| 4 | 3 |
| 5 | 6 |
| 6 | 4 |
| **Tổng** | **25** |

Throughput trung bình minh họa:

\[
\text{Throughput trung bình}=\frac{3+4+5+3+6+4}{6}=\frac{25}{6}\approx4{,}17\ \text{mục/tuần}
\]

Giả sử nhóm đã làm rõ và chia một phạm vi phát hành còn **12 mục tương đối giống với các mục lịch sử**. Phép tính cơ học:

\[
\frac{12\ \text{mục}}{4{,}17\ \text{mục/tuần}}\approx2{,}9\ \text{tuần}
\]

Con số 2,9 tuần **không phải lời hứa**, cũng **không phải mốc có xác suất thành công đã được tính**. Nếu xem mức throughput trong sáu tuần là 3–6 mục/tuần, phép chia đơn giản gợi ra khoảng **2–4 tuần trong những điều kiện thuận lợi tương tự**, nhưng không tạo ra cận chắc chắn: một phụ thuộc lớn hoặc sự cố có thể làm thời gian vượt xa bốn tuần.

### 7.1. Những câu hỏi phải hỏi trước khi dùng forecast

- **12 mục có giống lịch sử không?** Nếu có hai tích hợp lớn hơn hẳn những công việc trước, throughput theo số mục có thể gây hiểu nhầm.
- **Các mục được chia thế nào?** Nhóm vừa chuyển từ story lớn sang những task rất nhỏ thì dữ liệu đếm cũ và mới không còn so trực tiếp.
- **DoD có nhất quán không?** Nếu tuần gần đây bỏ bước kiểm thử để đóng ticket, throughput tăng không có nghĩa năng lực giao hàng cải thiện.
- **Còn công việc phát hành ngoài danh sách không?** Ví dụ kiểm thử bảo mật, di chuyển dữ liệu, hỗ trợ, kiểm tra vận hành.
- **Các mục có phụ thuộc nối tiếp không?** Phép chia trung bình không mô hình hóa chính xác giới hạn chuỗi phụ thuộc.
- **Có ngày nghỉ hoặc sự kiện khẩn dự kiến không?** Năng lực trong sáu tuần tới có thể khác lịch sử.

### 7.2. Dữ liệu đủ tốt có thể dùng mô phỏng xác suất

Với lịch sử ổn định, nhóm có thể mô phỏng nhiều khả năng hoàn tất bằng cách lấy mẫu từ phân bố throughput/cycle time đã quan sát, thường gọi là **mô phỏng Monte Carlo**.

Các bước tư duy:

1. Xác định số mục còn lại, phạm vi và cách hiểu Done.
2. Kiểm tra dữ liệu lịch sử có phù hợp với loại công việc đang dự báo không.
3. Mô phỏng nhiều chuỗi hoàn thành có điều kiện theo dữ liệu đó.
4. Xem phân bố thời điểm hoàn tất, chẳng hạn mốc đạt một mức xác suất mong muốn.
5. Công bố **phương pháp, cỡ mẫu, giới hạn và giả định**, cập nhật khi điều kiện thay đổi.

Mô phỏng không biến công việc mới thành chắc chắn. Nếu dữ liệu quá ít, thay đổi quy trình lớn hoặc có một phụ thuộc chưa từng xuất hiện, cần nói rõ **forecast không được hiệu chỉnh tốt**. Không nên báo “độ tin cậy 90%” chỉ vì một biểu đồ đẹp.

### 7.3. Ví dụ công bố thay vì che bất định

> “Phạm vi lõi còn 12 mục đã được làm rõ. Dữ liệu sáu tuần của nhóm cho thấy trung bình khoảng 4 mục Done mỗi tuần, nhưng kích thước vài mục mới lớn hơn bình thường. Ước lượng sơ bộ là khoảng ba tuần, với rủi ro vượt bốn tuần nếu tích hợp đối tác không đúng giả định. Chúng tôi sẽ chia lại hai mục lớn, đo thêm một tuần và cập nhật forecast trước khi chốt kế hoạch phát hành.”

Thông điệp này tạo cơ sở **để chọn hành động**, không chỉ để so ngày.

## 8. Sử dụng cycle time và Service Level Expectation đúng cách

Không phải lúc nào nhóm cũng cần dự báo **bao giờ xong toàn bộ 12 mục**. Nhiều khi câu hỏi thực tế là **một mục đã bắt đầu thường mất bao lâu để đạt Done?**

**Cycle time** là thời gian từ khi mục bắt đầu thực hiện đến khi hoàn tất, theo các mốc được nhóm xác định và sử dụng nhất quán. **Work item age** là tuổi hiện tại của một mục vẫn đang mở.

Trong Kanban, **Service Level Expectation (SLE)** có thể diễn đạt kỳ vọng thời gian hoàn thành một mục bằng **khoảng thời gian và xác suất**, được dựa trên dữ liệu lịch sử khi có dữ liệu phù hợp.

Ví dụ minh họa, không phải số liệu thực:

> “Theo dữ liệu gần đây của loại công việc này, khoảng 85% mục đã bắt đầu được hoàn tất trong 8 ngày làm việc hoặc ít hơn.”

Điều đó **không có nghĩa** mỗi mục buộc phải hoàn tất trước ngày thứ tám, cũng không có nghĩa một mục đến ngày thứ chín là do cá nhân làm kém. SLE là tín hiệu để hỏi: mục này có vướng phụ thuộc, rủi ro hoặc giới hạn WIP nào cần hỗ trợ không?

### Những việc có thể làm khi một mục già đi

- Chủ động phối hợp với người đang bị chặn.
- Chia lại phạm vi nếu có thể tạo lát có giá trị mà không bỏ chất lượng.
- Hoàn tất review/kiểm thử cho mục đang dở trước khi kéo thêm việc.
- Làm rõ phụ thuộc, đầu mối quyết định và thời hạn phản hồi.
- Cập nhật forecast của những mục liên quan.

### Little's Law: dùng để hiểu hệ thống, không áp deadline cá nhân

Trong một hệ thống luồng ổn định với các điều kiện áp dụng phù hợp, quan hệ trung bình có thể viết:

\[
\text{WIP trung bình}=\text{Throughput trung bình}\times\text{Cycle time trung bình}
\]

Nếu throughput và các điều kiện tương đương được giữ, WIP quá cao thường đi cùng thời gian hoàn tất dài hơn. Tuy nhiên, đây là **quan hệ thống kê ở cấp hệ thống**, không phải công thức để kết luận một người phải xong story trong số ngày cụ thể. Hệ thống thay đổi, hàng đợi, kích cỡ công việc và cách đo có thể làm cách áp dụng đơn giản không phù hợp.

## 9. Khi deadline thực sự cố định: thương lượng điều gì?

Một tình huống phổ biến: **ngày ra mắt không đổi, nhưng phạm vi và mức bất định còn lớn**. Khi đó, điều phối tốt cần làm rõ các biến số có thể điều chỉnh.

### 9.1. Phân biệt “bất biến” với “có thể thương lượng”

| Thành phần | Ví dụ có thể cố định | Ví dụ có thể thay đổi |
| --- | --- | --- |
| **Ngày** | Hệ thống cũ bị ngừng hỗ trợ vào ngày đã xác nhận. | Ngày ra bản mở rộng hoặc ngày thêm tính năng phụ. |
| **Phạm vi** | Luồng đặt lịch cốt lõi theo cam kết/hợp đồng. | Báo cáo tùy biến, bộ lọc nâng cao, cá nhân hóa. |
| **Chất lượng/an toàn** | Không để lộ dữ liệu, không tạo giao dịch sai, đạt kiểm soát bắt buộc. | Có thể chọn giải pháp đơn giản hơn nhưng vẫn đáp ứng tiêu chuẩn. |
| **Đối tượng** | Một số khách hàng hoặc quy định bắt buộc. | Thử với nhóm giới hạn trước khi mở rộng toàn bộ. |
| **Nguồn lực** | Nhân sự hiện có trong giai đoạn ngắn. | Bổ sung hỗ trợ với đánh giá chi phí phối hợp, không mặc định người mới làm tăng năng suất tức thì. |
| **Cách triển khai** | Phải giữ hệ thống hoạt động an toàn. | Triển khai theo giai đoạn, có feature flag, phương án khôi phục hoặc chuyển đổi tuần tự. |

**Cắt phạm vi phụ** khác với **cắt chất lượng cần thiết**. Một sản phẩm khả dụng tối thiểu hoặc Increment có thể sử dụng vẫn phải đúng chức năng cốt lõi và đáp ứng những yêu cầu bảo mật, riêng tư, vận hành cần thiết.

### 9.2. Một cách trình bày lựa chọn thay cho lời hứa rỗng

Giả sử người liên quan muốn bản thử dùng tính năng “Học tiếp” trước sự kiện ba tuần nữa, trong khi forecast sơ bộ cho toàn bộ yêu cầu là bốn đến sáu tuần.

Nhóm có thể trình bày:

- **Phương án A — Giữ ngày, giảm phạm vi:** giao lưu/khôi phục tiến độ trên một thiết bị và đường quay lại học; chưa làm đồng bộ offline hoặc gợi ý AI.
- **Phương án B — Giữ phạm vi rộng:** dời cửa sổ phát hành theo forecast có điều kiện, nếu cam kết bên ngoài cho phép.
- **Phương án C — Giao theo giai đoạn:** thử một nhóm nhỏ với chức năng cốt lõi đã đạt chất lượng, sau đó mở rộng khi phụ thuộc và phản hồi cho phép.
- **Phương án D — Đổi giải pháp:** nếu mục tiêu là hỗ trợ người học tìm bài đang dở, có thể dùng giao diện và logic đơn giản hơn thay vì thiết kế đồng bộ phức tạp ngay.

Các phương án có thể kết hợp. Điều không nên chọn là **tuyên bố vẫn giao toàn bộ đúng ngày** mà không thay bất kỳ điều kiện nào, rồi bí mật đẩy lỗi và kiểm thử sang sau.

### 9.3. Quản lý cam kết bên ngoài

Nếu đã cam kết với khách hàng, nhóm có trách nhiệm báo sớm khi forecast rủi ro, không đợi quá hạn. Người có thẩm quyền cần xem:

1. Cam kết cụ thể về **kết quả, phạm vi và ngày** là gì?
2. Phần nào là nghĩa vụ không thể bỏ; phần nào do nhóm tự suy diễn?
3. Hậu quả và phương án xử lý nếu thay đổi cam kết là gì?
4. Ai phải tham gia đàm phán và thông báo?
5. Tiêu chuẩn nào vẫn phải đạt để tránh gây hại hoặc vi phạm nghĩa vụ?

Thích ứng không đồng nghĩa phá cam kết tùy tiện. Nó là **trung thực về khả năng thực hiện và lựa chọn phương án ít rủi ro hơn**.

## 10. Scrum: trách nhiệm với mục tiêu khác với “cam kết từng điểm”

Trong Scrum, một số khái niệm giúp ngăn ước lượng trở thành cơ chế giao deadline máy móc:

| Khái niệm | Ý nghĩa phù hợp |
| --- | --- |
| **Product Goal** | Đích dài hạn của sản phẩm, là cam kết liên quan tới Product Backlog. |
| **Product Backlog** | Danh sách được sắp thứ tự, thay đổi khi hiểu biết mới xuất hiện; không phải danh sách lời hứa từng ticket. |
| **Sprint Goal** | Mục tiêu thống nhất cho Sprint, là cam kết của Sprint Backlog. |
| **Sprint Backlog** | Sprint Goal, các mục được chọn và kế hoạch để Developers đưa chúng thành Increment. |
| **Definition of Done** | Cam kết về chất lượng của Increment. |
| **Increment** | Phần tiến bộ tích hợp, có thể sử dụng và đạt DoD; không đồng nghĩa mọi tính năng đã được release. |

### 10.1. Sprint Planning là lập kế hoạch trong điều kiện thực tế

Trong Sprint Planning, Scrum Team thảo luận vì sao Sprint có giá trị và tạo Sprint Goal; **Developers lựa chọn** phần công việc họ dự kiến có thể hoàn tất và lập kế hoạch thực hiện, dựa trên năng lực, hiệu suất đã quan sát, DoD và hiểu biết về Product Backlog Items.

Điểm quan trọng: đây là **sự dự báo và lập kế hoạch của những người thực hiện**, không phải quyền của người ngoài áp một tổng story points cố định rồi yêu cầu “ký cam kết”.

### 10.2. Trong Sprint, kế hoạch có thể được thích ứng

Developers kiểm tra tiến độ tới Sprint Goal và điều chỉnh Sprint Backlog khi học được điều mới. Phạm vi có thể được làm rõ và thương lượng với Product Owner khi phù hợp, nhưng Sprint Goal vẫn là định hướng. **Chất lượng không bị giảm**, DoD vẫn áp dụng và các thay đổi phải minh bạch.

Không nên tuyên bố mọi Product Backlog Item được chọn phải hoàn tất bằng mọi giá; cũng không nên xem việc điều chỉnh phạm vi hợp lý là bằng chứng cá nhân thất bại.

### 10.3. Daily Scrum để phối hợp, không phải giám sát từng người

Daily Scrum giúp Developers kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch cho ngày tiếp theo. Một buổi Daily Scrum mà mỗi người đọc “hôm qua làm bao nhiêu điểm, hôm nay phải xong mấy điểm” có thể bỏ lỡ các điểm chặn thực sự.

Những câu hỏi tốt hơn:

- Lát dọc nào gần đạt DoD nhất, cần ai cùng hoàn tất?
- Phụ thuộc nào đe dọa Sprint Goal?
- Có thay đổi nào cần thảo luận với Product Owner?
- Có cần giảm WIP hoặc xử lý review đang tắc?
- Bằng chứng mới nào khiến forecast của Sprint thay đổi?

### 10.4. Sprint Review và Retrospective để học, không để xét tội

Sprint Review xem kết quả và điều chỉnh hướng sản phẩm; Retrospective cải tiến cách phối hợp, chất lượng và hiệu quả. Chênh lệch giữa forecast và thực tế là **dữ liệu để hiểu hệ thống và giả định**, không phải lý do mặc định để bêu tên một người.

Scrum Master có thể giúp nhóm và tổ chức dùng đúng các sự kiện và minh bạch về trở ngại; Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog; Developers chịu trách nhiệm cách thực hiện và chất lượng Increment. **Không vai trò nào có thể biến một ước lượng thành sự thật bằng mệnh lệnh.**

## 11. Kanban và XP: cải thiện năng lực giao hàng thay vì tăng áp lực điểm số

### 11.1. Kanban nhìn luồng thay vì bảng xếp hạng người

Kanban khuyến khích trực quan hóa luồng, quản lý WIP, làm rõ chính sách và dùng dữ liệu thực tế. Khi forecast thay đổi, câu hỏi nên là **hệ thống bị nghẽn ở đâu?**

Ví dụ một bảng:

~~~text
Ready -> Development (WIP <= 3) -> Review (WIP <= 2) -> Verify -> Done
                                 ^                   ^
                                 |                   |
                          Hàng đợi review     Chờ môi trường test
~~~

Giới hạn WIP trên chỉ là minh họa. Nếu cột Review luôn đầy, yêu cầu mỗi lập trình viên “làm nhiều điểm hơn” có thể làm hàng đợi tệ hơn. Cách có ích là **giúp hoàn tất công việc đang chờ**, cải thiện thời gian phản hồi review hoặc giảm kích thước thay đổi.

Trong Kanban, số đo dòng công việc là dữ liệu để quản lý **hệ thống chuyển việc thành giá trị**, không phải để trừng phạt người đang xử lý những mục khó.

### 11.2. XP giúp giảm bất định và chi phí sửa lỗi

Các thực hành như **test-driven development (TDD)**, continuous integration, refactoring, lập trình cặp và thiết kế đơn giản có thể khiến việc triển khai các lát nhỏ đáng tin cậy hơn:

- Kiểm thử tạo phản hồi kỹ thuật sớm.
- Tích hợp thường xuyên phát hiện xung đột trước khi đến gần hạn.
- Refactoring giảm độ phức tạp kéo dài chu kỳ thay đổi.
- Lập trình cặp hoặc làm việc chung chia sẻ kiến thức, giảm phụ thuộc vào một cá nhân.
- Thiết kế đủ cho nhu cầu hiện tại tránh xây trước các khả năng chưa cần.

Cần đánh giá chúng theo tác động lên **chất lượng và khả năng giao sản phẩm bền vững**, không phải số giờ hoặc điểm cá nhân “tiết kiệm” ngay tuần đầu.

### 11.3. Có thể kết hợp cách làm

Một Scrum Team có thể dùng dữ liệu Kanban để cải thiện dự báo của Sprint, đồng thời sử dụng XP để giữ chất lượng. Không nên ép mọi phương pháp vào một thang điểm thống nhất giữa nhóm. **Mục tiêu là phản hồi sớm và năng lực thích ứng**, không phải thắng cuộc thi velocity.

## 12. Đánh giá con người công bằng hơn: không dùng story points cá nhân

Người quản lý vẫn cần hỗ trợ phát triển năng lực, phản hồi hiệu suất và làm rõ trách nhiệm. Việc không dùng story points làm bảng xếp hạng **không có nghĩa không thể đánh giá công việc**; nó có nghĩa chọn tín hiệu phù hợp hơn và tránh quy chụp từ một con số.

### 12.1. Phân biệt hiệu quả của hệ thống với đóng góp của con người

| Câu hỏi | Dữ liệu nên xem | Điều cần tránh |
| --- | --- | --- |
| Nhóm có giao giá trị đều đặn không? | Kết quả người dùng, chất lượng, throughput, cycle time, WIP, độ tin cậy dự báo. | Gán tất cả biến động cho một cá nhân. |
| Một người có đóng góp chuyên môn ra sao? | Chất lượng quyết định, kết quả đầu cuối, khả năng giải quyết vấn đề, ví dụ công việc cụ thể. | Lấy tổng điểm ticket được gắn tên làm năng suất. |
| Người đó có giúp cả nhóm tốt hơn không? | Review hữu ích, hỗ trợ người khác, chia sẻ kiến thức, chủ động nêu rủi ro, hợp tác liên chuyên môn. | Coi thời gian giúp đồng nghiệp là “không tạo điểm”. |
| Còn khả năng phát triển nào? | Phản hồi đa chiều có bối cảnh, kỹ năng cần rèn, kết quả học tập và mức hỗ trợ phù hợp. | Dán nhãn “kém” chỉ từ một Sprint có sự cố. |
| Có trở ngại hệ thống nào? | Phụ thuộc, quyền quyết định, môi trường, hàng chờ, sự gián đoạn. | Đòi cá nhân tự bù bằng làm ngoài giờ kéo dài. |

Các dữ liệu này cần được diễn giải **có bối cảnh, tôn trọng quyền riêng tư và minh bạch mục đích**. Không nên sử dụng log hoạt động, số commit, số dòng code hay thời gian online như bằng chứng độc lập về giá trị cá nhân.

### 12.2. Cách phản hồi cụ thể và có trách nhiệm

Thay vì:

> “Bạn Sprint này chỉ xong 5 điểm, còn đồng nghiệp xong 13 điểm.”

Có thể trao đổi:

> “Trong hai lần review API gần đây, bạn phát hiện lỗi quyền truy cập trước khi phát hành. Việc đó giúp nhóm tránh rủi ro. Tôi cũng thấy một thay đổi bị chặn lâu vì phụ thuộc hệ thống khác; hãy cùng xác định cách báo sớm và nguồn hỗ trợ. Với mục tiêu phát triển nghề nghiệp của bạn, mình muốn bàn thêm về việc chia nhỏ thay đổi để nhận phản hồi nhanh hơn.”

Đây là phản hồi dựa trên **hành vi, tác động và cơ hội cải tiến**, không tô hồng mọi vấn đề. Khi có thiếu sót thực sự về chất lượng hoặc trách nhiệm, vẫn cần trao đổi dựa trên bằng chứng cụ thể và điều kiện làm việc.

### 12.3. An toàn khi nêu bất định

Nhóm cần có khả năng nói:

- “Ước lượng này chưa đáng tin vì chưa kiểm tra API.”
- “Tôi dự đoán lát này không đạt DoD trong Sprint nếu điểm nghẽn review chưa được giải quyết.”
- “Tôi phát hiện một rủi ro bảo mật; không thể gọi phần này Done ngay.”
- “Bằng chứng mới cho thấy tính năng này không còn đáng ưu tiên.”

Nếu phát biểu trung thực bị trừng phạt, những người làm việc sẽ học cách **che giấu thông tin làm dự báo kém lạc quan**. Khi đó ngay cả người quản lý cũng mất dữ liệu để ra quyết định.

## 13. Tình huống xuyên suốt: một bản phát hành gặp deadline

Một nhóm xây tính năng **“Học tiếp”** cho nền tảng học trực tuyến. Đơn vị kinh doanh mong muốn trình diễn bản thử cho nhóm đối tác trong **ba tuần**, và yêu cầu ban đầu có bốn phần:

1. Lưu/khôi phục vị trí video.
2. Lối vào “Học tiếp” rõ ràng trên trang chủ.
3. Đồng bộ nhiều thiết bị, kể cả tình huống xung đột.
4. Bộ gợi ý bài tiếp theo bằng AI.

Nhóm có lịch sử throughput khoảng ba đến sáu mục đã Done mỗi tuần, nhưng các phần 3 và 4 chưa được chia đủ rõ, có rủi ro tích hợp và dữ liệu.

### 13.1. Cách xử lý sai

Người quản lý chuyển mọi mục thành story points rồi yêu cầu: “Tổng 40 điểm, ba tuần thì phải làm được. Ai không đủ điểm sẽ bị đánh giá cuối kỳ.”

Phản ứng có thể là:

- Nhóm tránh đề cập phụ thuộc hoặc đổi quy ước points.
- Developers chia việc để có nhiều điểm hơn.
- Kiểm thử đa thiết bị và xử lý lỗi được làm qua loa.
- Báo cáo Sprint xanh hơn nhưng bản dùng thử không đáng tin.
- Nhóm mất cơ hội thử sớm phần người học thực sự cần.

### 13.2. Cách xử lý thích ứng

**Bước 1 — xác định kết quả sự kiện:** Người học của nhóm thử có thể mở lại video đúng vị trí đã lưu; đội ngũ có thể trình diễn luồng thật, không gây sai lệch hoặc lộ dữ liệu.

**Bước 2 — chia phạm vi:** Hai lát đầu có thể hoàn tất đầu cuối với các điều kiện bảo mật và kiểm thử cần thiết. Đồng bộ đa thiết bị và AI cần nghiên cứu hoặc thử riêng.

**Bước 3 — tạo forecast:** Developers cùng người hiểu phụ thuộc đánh giá năng lực thực tế, ưu tiên công việc cốt lõi, dùng throughput/cycle time nếu dữ liệu tương thích và nêu rủi ro.

**Bước 4 — nêu phương án:** Nếu ngày thử nghiệm cố định, tập trung hai lát cốt lõi, chưa cam kết hai phần nâng cao; có phương án demo an toàn và giới hạn người thử.

**Bước 5 — chọn tín hiệu:** Tỷ lệ khôi phục vị trí thành công, thời gian người học tìm lại bài, lỗi dữ liệu, thời gian các lát đi qua Review/Verify.

**Bước 6 — cập nhật:** Sau một tuần, nếu phụ thuộc lưu dữ liệu gây chậm, thông báo ngay và đánh giá lại phạm vi/cửa sổ phát hành. Không đợi tới ngày demo rồi mới nói không kịp.

### 13.3. Minh họa trao đổi giữa các vai trò

**Người liên quan:** “Ngày ra mắt ba tuần nữa có giữ được không?”

**Product Owner:** “Mục tiêu chính của bản thử là người học có thể tiếp tục video đáng tin cậy. Đồng bộ đa thiết bị và AI có thể chưa cần cho đợt này. Chúng ta nên chốt phạm vi lõi trước.”

**Developers:** “Với dữ liệu hiện tại, phạm vi lõi có khả năng phù hợp cửa sổ đó nếu việc tích hợp được làm rõ trong tuần đầu. Tuy nhiên, chúng tôi chưa có cơ sở để cam kết cả bốn phần. Chúng tôi sẽ nêu rủi ro, kiểm tra luồng đầu cuối và cập nhật forecast vào cuối tuần.”

**Người kiểm thử hoặc người phụ trách chất lượng:** “Phát hành thử vẫn cần đạt tiêu chí quyền truy cập, lưu tiến độ chính xác và xử lý lỗi. Không thể bỏ các trường hợp đó để giữ ngày.”

**Người liên quan:** “Vậy hãy thống nhất bản lõi cho nhóm thử, còn hai phần nâng cao xem lại sau khi nhận dữ liệu.”

Đây là cuộc đàm phán có trách nhiệm: **ngày có thể giữ, nhưng phạm vi và giả định được công khai; chất lượng cần thiết không bị hy sinh**.

### 13.4. Không đánh giá thành công chỉ bằng “đúng ngày”

Một bản phát hành đúng ngày nhưng không hoạt động hoặc người dùng không có giá trị là thất bại theo nhiều cách. Ngược lại, một dự báo được cập nhật sớm, giúp tổ chức thu hẹp phạm vi và giao phần thiết yếu an toàn, có thể là một thành công của **khả năng thích ứng và quản trị rủi ro**.

Cần đánh giá kết hợp: **kết quả người dùng, chất lượng, sự minh bạch và khả năng phối hợp**, không chỉ độ chênh lệch giữa ước lượng đầu tiên và ngày hoàn tất thực tế.

## 14. Mẫu truyền đạt một forecast cho người liên quan

Một bản dự báo thường không cần báo cáo dài. Mẫu sau có thể ghi trong tài liệu phát hành, bản cập nhật hoặc comment của epic:

~~~text
MỤC TIÊU/KẾT QUẢ:
  Ai cần đạt kết quả gì? Tại sao quan trọng?

PHẠM VI ĐƯỢC DỰ BÁO:
  Những lát hoặc Product Backlog Items nào nằm trong phạm vi?
  Điều gì chưa được tính?

THỜI ĐIỂM / KHOẢNG DỰ BÁO:
  Khoảng dự kiến hoặc mốc theo mức xác suất có cơ sở.
  Đây là forecast, target hay cam kết chính thức?

CƠ SỞ:
  Dữ liệu lịch sử, cách đo Done, cỡ mẫu và giới hạn dữ liệu.
  Mức thay đổi so với các công việc đã hoàn tất.

GIẢ ĐỊNH:
  Năng lực, phụ thuộc, môi trường, ngày nghỉ, WIP và chất lượng.

RỦI RO CHÍNH:
  Điều gì có thể khiến dự báo đổi? Có phương án giảm rủi ro nào?

LỰA CHỌN / ĐÁNH ĐỔI:
  Giảm phạm vi, đổi giải pháp, theo giai đoạn hay điều chỉnh lịch?

MỐC CẬP NHẬT VÀ NGƯỜI CHỊU TRÁCH NHIỆM:
  Khi nào có bằng chứng mới? Ai chọn bước tiếp theo?
~~~

Đừng dùng mẫu này để tạo thủ tục phê duyệt nặng nề cho mọi task. Nó phù hợp nhất với **quyết định có rủi ro, phụ thuộc hoặc ảnh hưởng đến nhiều bên**.

### Ví dụ cập nhật ngắn

> “Bản thử ‘Học tiếp’ dự kiến gồm hai lát lõi, không gồm AI và đồng bộ offline. Lịch sử giao hàng giúp chúng tôi kỳ vọng hoàn tất trong cửa sổ khoảng ba tuần, nhưng phụ thuộc xác thực tiến độ chưa được kiểm tra xong. Tuần này chúng tôi sẽ chạy thử tích hợp, cập nhật forecast sau khi có kết quả và điều chỉnh phạm vi nếu rủi ro tăng. Điều kiện về quyền truy cập và DoD được giữ nguyên.”

Thông báo này mang lại thông tin mà một ngày cố định trống bối cảnh không cung cấp được.

## 15. Cơ chế vận hành để bảo vệ tính trung thực của ước lượng

Một bài hướng dẫn sẽ ít có hiệu quả nếu cơ chế đánh giá vẫn thưởng phạt theo “đúng điểm/đúng ngày”. Nhóm và tổ chức có thể thống nhất những thực hành cụ thể.

### 15.1. Chính sách sử dụng số liệu

| Số liệu | Dùng để làm gì | Không dùng để làm gì |
| --- | --- | --- |
| **Story points/velocity** | Thảo luận quy mô tương đối và lập kế hoạch của cùng nhóm khi phù hợp. | Xếp hạng cá nhân, so năng suất giữa nhóm, áp hạn chót mỗi story. |
| **Throughput** | Dự báo hoàn tất các mục tương đối đồng nhất; theo dõi khả năng giao hàng của hệ thống. | Ép tăng số ticket bằng cách chia vụn hoặc hạ chất lượng. |
| **Cycle time** | Phát hiện chờ đợi và cải thiện dòng công việc. | Kết luận người có story lâu hơn là kém năng lực. |
| **WIP/work item age** | Nhìn điểm nghẽn, tập trung hoàn tất việc đang mở. | Giám sát vi mô hoặc phạt người nêu trở ngại. |
| **Lỗi sau phát hành** | Học về rủi ro và chất lượng sản phẩm. | Gán trách nhiệm đơn giản cho người commit cuối cùng mà không điều tra hệ thống. |
| **Kết quả sản phẩm** | Đánh giá các giả thuyết giá trị và lựa chọn backlog. | Quy mọi thay đổi hành vi người dùng cho một cá nhân duy nhất. |

### 15.2. Kiểm soát chất lượng số liệu

- Dùng **Definition of Done** nhất quán khi đếm công việc hoàn tất.
- Chỉ so throughput của những loại mục có cách phân chia tương đối tương thích.
- Tránh bỏ những mục khó hoặc việc hỗ trợ sản xuất ra ngoài thước đo vì làm forecast đẹp hơn.
- Ghi khi thay đổi quy trình, năng lực, loại việc hoặc điểm đo.
- Giữ quyền riêng tư và dùng dữ liệu theo mục đích đã công bố.
- Cho phép thành viên **giải thích ngữ cảnh** mà không phải tự vệ trước một bảng xếp hạng.

### 15.3. Nhịp cập nhật forecast

Không cần tái ước lượng mọi ticket mỗi ngày. Nhóm nên cập nhật forecast khi:

- Phạm vi tăng/giảm đáng kể.
- Phát hiện rủi ro hoặc phụ thuộc mới.
- Có dữ liệu throughput/cycle time đáng kể so với giả định cũ.
- Một thay đổi chất lượng hoặc sự cố ảnh hưởng năng lực.
- Cần quyết định phát hành hoặc thông báo cam kết.
- Có phản hồi người dùng làm thay đổi mức ưu tiên của các lát.

Cập nhật đều đặn theo nhịp phù hợp với Sprint hoặc luồng Kanban giúp giảm bất ngờ, nhưng **sự kiện nghiêm trọng không nên chờ lịch họp**.

## 16. Các ngộ nhận và phản ứng cần tránh

| Ngộ nhận | Vấn đề | Cách hiểu hoặc hành động phù hợp |
| --- | --- | --- |
| “Ước lượng 5 điểm tức 5 ngày.” | Điểm tương đối không phải ngày lịch. | Xác định đơn vị, quy ước và mục đích sử dụng. |
| “Ước lượng sai thì người làm phải chịu trách nhiệm cá nhân.” | Ước lượng chứa bất định và ảnh hưởng hệ thống. | Xem giả định, dữ liệu, rào cản và cách cập nhật; đánh giá hành vi cụ thể nếu cần. |
| “Team B có velocity gấp đôi Team A nên giỏi gấp đôi.” | Quy ước, loại công việc và DoD khác nhau. | Xem kết quả sản phẩm, chất lượng và năng lực cải tiến trong bối cảnh từng nhóm. |
| “Ai nhận story nhiều điểm là người đóng góp nhất.” | Story thường có nhiều người đóng góp. | Ghi nhận kết quả chung, hỗ trợ, chất lượng quyết định và tác động thực tế. |
| “Deadline đã chốt, không được nêu rủi ro.” | Che thông tin khiến tổ chức mất cơ hội ứng phó. | Báo sớm, đưa lựa chọn phạm vi và rủi ro minh bạch. |
| “Muốn dự báo tốt thì cần ước lượng mọi thứ thật chính xác.” | Nỗ lực ước lượng có thể lớn hơn lợi ích; tương lai vẫn biến động. | Làm rõ lát, dùng dữ liệu phù hợp và tập trung vào những quyết định quan trọng. |
| “Cứ làm thêm giờ là bù được mọi độ trễ.” | Có giới hạn nhận thức, phụ thuộc và chi phí lỗi; thiếu bền vững. | Giảm WIP, cải thiện phối hợp, thương lượng phạm vi/lịch thay vì phụ thuộc vào quá tải. |
| “Cứ tăng số Done là thành công.” | Đếm mục không đo giá trị hoặc chất lượng. | Kết hợp flow metrics, DoD, lỗi và kết quả người dùng. |
| “Một forecast 90% nghĩa là chắc chắn xong.” | Xác suất không bằng bảo đảm; mô hình có giả định. | Nêu điều kiện, dữ liệu, phương án nếu kết quả nằm ngoài khoảng dự báo. |
| “Không dùng points là khỏi lập kế hoạch.” | Vẫn cần ra quyết định về phạm vi, năng lực, rủi ro và phát hành. | Dùng dự báo theo dòng, chia lát và kiểm tra giả thuyết khi phù hợp. |

## 17. Bài tập ứng dụng: khi dự báo xung đột với ngày ra mắt

Bạn thuộc nhóm phát triển hệ thống đặt lịch tư vấn trực tuyến. Doanh nghiệp đã thông báo ngày giới thiệu bản thử sau **ba tuần**. Backlog hiện có:

- **A:** Người dùng xem các khung giờ còn trống và đặt một lịch hợp lệ.
- **B:** Xác nhận không tạo lịch trùng nếu hai người cùng chọn một khung giờ.
- **C:** Gửi email xác nhận và hiển thị trạng thái rõ khi gửi thất bại.
- **D:** Tạo lịch lặp nhiều tháng với quy tắc tùy chỉnh.
- **E:** Gợi ý giờ phù hợp dựa trên mô hình AI.
- **F:** Kiểm soát quyền truy cập và dữ liệu cá nhân theo chính sách áp dụng.
- **G:** Theo dõi sự cố và có phương án hỗ trợ/khôi phục phù hợp.
- **H:** Xuất báo cáo tùy biến cho nhiều phòng ban.

Một số thành viên dự đoán phạm vi A–H mất **năm đến bảy tuần**, nhưng người quản lý nói: “Ba tuần đã hứa rồi, ai không hoàn tất số điểm được giao sẽ bị đánh giá thấp.” Nhóm có throughput trung bình lịch sử khoảng bốn mục đã Done mỗi tuần, nhưng D và E lớn hơn các công việc thông thường.

### Nhiệm vụ

1. **Phân biệt:** Trong lời quản lý, đâu là deadline, đâu là forecast, đâu là sự đánh tráo thành cam kết hoặc chỉ số cá nhân?
2. **Giá trị cốt lõi:** Chọn phạm vi thử tối thiểu giúp người dùng đặt lịch đúng, đủ chất lượng và an toàn. Giải thích những mục có thể hoãn và những điều không thể cắt.
3. **Dự báo:** Dùng throughput trung bình làm phép tính tham khảo cho các mục có kích thước phù hợp; nêu ít nhất ba lý do chưa thể cam kết ngày.
4. **Thương lượng:** Đề xuất hai phương án để người liên quan quyết định nếu ngày ba tuần không thay đổi.
5. **Đo lường:** Chọn hai flow metrics, một số đo chất lượng và một số đo giá trị sản phẩm cho bản thử.
6. **Văn hóa nhóm:** Viết lại câu “ai không đủ điểm bị đánh giá thấp” thành một quy tắc quản lý bảo vệ sự minh bạch nhưng vẫn có trách nhiệm.
7. **Báo cáo:** Viết một thông điệp cập nhật dài khoảng năm câu: phạm vi, dự báo, rủi ro, điều kiện phát hành và mốc cập nhật.

### Gợi ý hướng giải

**Phân biệt:** Ba tuần là mốc kinh doanh đã công bố. Năm đến bảy tuần là forecast sơ bộ của nhóm cho phạm vi A–H. Không thể chuyển forecast đó thành trách nhiệm cá nhân theo story points, và ngày ba tuần không tự chứng minh toàn bộ phạm vi sẽ hoàn tất.

**Phạm vi lõi:** A, B, F và những điều kiện vận hành G cần thiết để thử an toàn; C có thể cần ở mức tối thiểu phù hợp cách xác nhận đã thống nhất. **D, E, H** nên được đánh giá lại theo giá trị và chưa nhất thiết nằm trong bản thử. Nếu email chưa sẵn sàng, phải bảo đảm người dùng vẫn nhận trạng thái đặt lịch đúng, không đánh tráo bằng thông báo thành công giả.

**Dự báo:** Không thể lấy đơn giản tám mục chia bốn mục/tuần rồi kết luận chắc chắn hai tuần, vì kích thước D/E khác biệt, phụ thuộc và chuẩn Done của bản thử có thể khác dữ liệu lịch sử, còn công việc vận hành/phát hành có thể chưa được đếm. Cần chia lát, làm rõ và dự báo lại.

**Thương lượng:** (1) Giữ ngày ba tuần, giới hạn bản thử vào luồng đặt lịch an toàn và minh bạch giới hạn; hoặc (2) giữ phạm vi lớn hơn nhưng thương lượng lịch/phân kỳ phát hành có điều kiện. Có thể dùng thử nghiệm kỹ thuật sớm cho việc đặt lịch đồng thời để giảm rủi ro.

**Đo lường:** Cycle time và WIP; số sự cố đặt trùng/vi phạm dữ liệu; tỷ lệ người dùng đặt lịch hợp lệ thành công. Chỉ số cần có định nghĩa nhất quán và được diễn giải theo mẫu người dùng thử.

**Quản lý:** “Chúng ta dùng ước lượng và dữ liệu luồng để dự báo, công khai rủi ro và hỗ trợ hoàn tất công việc theo DoD. Phản hồi cá nhân dựa trên hành vi, chất lượng, hợp tác và kết quả có bối cảnh, không dựa vào tổng story points.”

## 18. Tự kiểm tra kiến thức

**Câu 1.** Một story 8 điểm bắt đầu thứ Hai. Người quản lý yêu cầu xong thứ Ba vì “8 điểm không khó”. Có cơ sở không?

**Đáp án:** Không đủ. Story points là quy mô tương đối trong quy ước của nhóm, không phải giờ hay ngày. Cần xem phạm vi, phụ thuộc, dữ liệu thực tế, DoD và khả năng hoàn tất.

**Câu 2.** Nhóm A đạt velocity 45, nhóm B đạt 25. Có thể xếp hạng năng suất không?

**Đáp án:** Không thể dựa vào hai con số ấy. Quy ước points, công việc, phạm vi và DoD có thể khác nhau; velocity không phải thước đo chuẩn so giữa nhóm.

**Câu 3.** Không dùng story points để đánh giá cá nhân thì người quản lý có mất khả năng phản hồi hiệu suất không?

**Đáp án:** Không. Có thể xem hành vi và kết quả có bối cảnh, chất lượng quyết định, hợp tác, hỗ trợ, học hỏi và trách nhiệm thực tế. Không nên suy năng lực từ số ticket hay số điểm.

**Câu 4.** Deadline thật sự cố định có nghĩa nhóm buộc phải hoàn tất toàn bộ phạm vi dự kiến dù dự báo không đáp ứng?

**Đáp án:** Không. Cần xác định nghĩa vụ thực sự, thương lượng phạm vi, cách triển khai hoặc nguồn lực, công khai rủi ro và giữ các yêu cầu an toàn/chất lượng bắt buộc.

**Câu 5.** Một dự báo nói “85% công việc loại này xong trong tám ngày”. Nếu mục đang ở ngày thứ chín, ai đã vi phạm?

**Đáp án:** Chưa thể kết luận ai vi phạm. SLE mô tả kỳ vọng thống kê cho loại công việc, không phải deadline cá nhân. Hãy kiểm tra điểm nghẽn và hỗ trợ mục đang chờ.

**Câu 6.** Nhóm tăng throughput bằng cách chia một story thành năm ticket, nhưng hành vi người dùng chưa hoàn tất. Có phải tốc độ tạo giá trị đã tăng?

**Đáp án:** Chưa thể kết luận. Thay đổi cách chia làm dữ liệu đếm không còn so trực tiếp; cần xem Increment đạt DoD, chất lượng và kết quả người dùng.

**Câu 7.** Khi một rủi ro mới xuất hiện giữa Sprint, Developers có nên giữ im lặng để tránh bị xem là ước lượng sai không?

**Đáp án:** Không. Cần nêu rủi ro sớm, điều chỉnh kế hoạch hướng Sprint Goal, trao đổi với Product Owner khi ảnh hưởng phạm vi hoặc ưu tiên và giữ DoD.

**Câu 8.** Có thể dùng dữ liệu throughput mà không làm Planning Poker cho mọi mục không?

**Đáp án:** Có thể khi luồng đủ ổn định và cách chia mục tương đối phù hợp. Tuy nhiên vẫn cần xác định phạm vi, làm rõ rủi ro và đọc dữ liệu trong bối cảnh thực tế.

**Câu 9.** Mô phỏng Monte Carlo cho kết quả với xác suất cao có nghĩa forecast chắc chắn đúng không?

**Đáp án:** Không. Mô phỏng phản ánh giả định và dữ liệu đầu vào. Phân bố công việc, phụ thuộc hoặc hệ thống thay đổi có thể làm dự báo lệch.

**Câu 10.** Đánh giá Sprint chỉ dựa vào số story points có thể bỏ sót những điều gì?

**Đáp án:** Giá trị người dùng, chất lượng, bảo mật, review, hỗ trợ người khác, khắc phục sự cố, giảm nợ kỹ thuật và các phụ thuộc hệ thống.

## 19. Ghi nhớ trọng tâm

- **Ước lượng là giả thuyết về công việc trong điều kiện thông tin chưa đầy đủ; dự báo là nhận định có điều kiện về khả năng hoàn tất.** Cả hai khác với mục tiêu, deadline và cam kết đã được thương lượng.
- **Đừng tự đổi story points thành ngày lịch.** Quy mô tương đối, công sức và thời gian chờ có bản chất khác nhau.
- **Story points/velocity không phải thước đo năng suất cá nhân hay thang chuẩn so các nhóm.** Cộng điểm theo người có thể bóp méo hành vi và bỏ sót đóng góp quan trọng.
- **Dự báo nên nêu phạm vi, dữ liệu, giả định, rủi ro, khoảng hoặc mức tin cậy có cơ sở và mốc cập nhật.** Số chính xác không đồng nghĩa đáng tin.
- **Có deadline thật vẫn có quyền và trách nhiệm thương lượng phạm vi/giải pháp.** Không hy sinh DoD, bảo mật hoặc tính đúng đắn để bảo vệ một con số.
- **Scrum giữ cam kết với Product Goal, Sprint Goal và Definition of Done**, trong khi Sprint Backlog có thể thích ứng theo thông tin mới. Kanban giúp nhìn luồng và dự báo dựa trên thực tế.
- **Throughput, cycle time, WIP và SLE đo tính chất của luồng công việc**, hỗ trợ phát hiện trở ngại, không phải bảng xếp hạng con người.
- **XP và những thực hành kỹ thuật chất lượng** giúp giảm bất định, tích hợp sớm và giao những phần tăng trưởng đáng tin cậy.
- **Đánh giá con người dựa trên đóng góp có bối cảnh, chất lượng, hợp tác và khả năng cải tiến**, không chỉ số ticket hoặc điểm được gắn tên.
- **Nêu rủi ro sớm là hành vi có trách nhiệm.** Độ tin cậy của kế hoạch tăng khi nhóm có thể nói thật, học từ sai lệch và thay đổi quyết định theo phản hồi.

Một nhóm Agile trưởng thành không chứng minh giá trị bằng việc **luôn dự đoán đúng một ngày chính xác** hoặc **mỗi cá nhân tạo ra nhiều điểm hơn**. Nhóm tạo ra các dự báo có ích, đưa ra đánh đổi minh bạch, giao phần mềm đạt chất lượng và học từ thực tế để phục vụ người dùng tốt hơn. Khi ước lượng được dùng như công cụ đối thoại thay vì hình phạt, khả năng thích ứng và cải tiến liên tục mới có chỗ phát triển.

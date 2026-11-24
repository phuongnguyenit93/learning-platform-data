# Các giá trị giao tiếp, đơn giản, phản hồi, can đảm và tôn trọng

Một nhóm phát triển có thể sử dụng test-driven development (TDD), pair programming và tích hợp liên tục nhưng vẫn khó giao phần mềm có giá trị. Nếu mọi người không trao đổi về nhu cầu thực, xây giải pháp quá phức tạp, bỏ qua kết quả kiểm thử, sợ thừa nhận sai lầm hoặc đối xử thiếu tôn trọng khi review mã, các kỹ thuật ấy dễ trở thành nghi thức. **Extreme Programming (XP) không chỉ là tập hợp kỹ thuật lập trình; đó còn là một hệ thống giá trị hướng dẫn cách nhóm lựa chọn và phối hợp.**

Năm giá trị thường được trình bày trong XP là **Communication (Giao tiếp), Simplicity (Đơn giản), Feedback (Phản hồi), Courage (Can đảm) và Respect (Tôn trọng)**. Chúng giúp nhóm phát triển phần mềm trong môi trường thay đổi bằng cách **làm rõ vấn đề sớm, chọn giải pháp vừa đủ, kiểm chứng liên tục, dám sửa hướng đi và duy trì quan hệ hợp tác lành mạnh**.

Bài học thuộc chương **Extreme Programming** trong module **AGILE_DEVELOPMENT**. Bên cạnh user story, backlog, Scrum và Kanban, XP cung cấp các thực hành kỹ thuật và cộng tác giúp nhóm **giao phần mềm tăng dần mà vẫn giữ khả năng thay đổi an toàn**. Nội dung tập trung vào ý nghĩa thực hành của năm giá trị XP, mối quan hệ giữa chúng và cách vận dụng qua ví dụ phát triển nền tảng học tập.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của **năm giá trị XP** và phân biệt giá trị với thực hành hoặc công cụ.
2. Nhận ra dấu hiệu giao tiếp thiếu hiệu quả dù nhóm tổ chức nhiều cuộc họp.
3. Áp dụng nguyên tắc đơn giản để tạo **lát cắt giá trị nhỏ** mà không đánh đổi chất lượng.
4. Thiết kế các **vòng phản hồi nhanh** từ kiểm thử, tích hợp, người dùng và vận hành.
5. Thực hành can đảm bằng cách nói rõ rủi ro, refactor khi thích hợp và đổi quyết định dựa trên bằng chứng.
6. Xây dựng tôn trọng thông qua review, pair programming, phối hợp liên chức năng và nhịp làm việc bền vững.
7. Phân tích trường hợp các giá trị có vẻ xung đột để chọn hành động cân bằng.
8. Liên hệ các giá trị với TDD, CI, refactoring, small releases và cách phối hợp với Scrum/Kanban.

## 2. Vì sao XP cần giá trị, không chỉ quy trình?

Trong phát triển phần mềm phức tạp, nhóm không thể viết sẵn một thủ tục cho mọi tình huống. Hằng ngày có những lựa chọn như:

- Người dùng yêu cầu thêm một trường dữ liệu nhưng chưa rõ mục đích; nên xây ngay hay hỏi thêm?
- Thiết kế hiện tại có một đoạn lặp nhỏ; nên refactor hay tạo thêm tầng trừu tượng?
- Một bài kiểm thử hồi quy mới thất bại sát ngày phát hành; nên bỏ qua hay nêu rủi ro?
- Hai lập trình viên bất đồng về cách giải quyết; nên tranh luận bằng cấp bậc hay kiểm chứng?
- Một đồng đội gặp khó với công nghệ mới; nên giao việc riêng để “nhanh hơn” hay cùng chia sẻ kiến thức?

Các quy trình có thể gợi ý câu trả lời, nhưng **giá trị quyết định cách nhóm cân nhắc**. XP hướng về phát triển thích ứng: học nhanh từ phần mềm thật, giữ thiết kế có thể thay đổi và làm việc cùng nhau thay vì tối ưu từng cá nhân.

### 2.1. Giá trị, nguyên tắc và thực hành không giống nhau

| Mức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Giá trị** | Điều nhóm coi trọng khi lựa chọn, nhất là khi có đánh đổi | Giao tiếp, đơn giản, phản hồi, can đảm, tôn trọng |
| **Nguyên tắc/hướng dẫn** | Cách suy luận từ giá trị thành hành động | Phản hồi sớm, thay đổi theo từng bước nhỏ, giảm rủi ro, hướng tới lợi ích chung |
| **Thực hành** | Hoạt động cụ thể nhóm có thể triển khai và kiểm chứng | Pair programming, TDD, CI, refactoring, small releases |
| **Công cụ** | Phương tiện hỗ trợ thực hành | Công cụ kiểm thử, Git, pipeline CI, bảng công việc, môi trường staging |

Không nên coi **“có pipeline CI”** là bằng chứng nhóm đã có văn hóa phản hồi: nếu pipeline báo lỗi liên tục nhưng mọi người bỏ qua, giá trị Feedback chưa thực sự được thực hành. Tương tự, dùng một công cụ chat chung không tự bảo đảm giao tiếp rõ ràng.

### 2.2. Năm giá trị tạo thành một hệ thống

| Giá trị | Câu hỏi ra quyết định | Rủi ro khi thiếu |
| --- | --- | --- |
| **Giao tiếp** | Chúng ta đã hiểu cùng một vấn đề và những ràng buộc quan trọng chưa? | Hiểu sai yêu cầu, phụ thuộc ẩn, làm lại |
| **Đơn giản** | Cách nhỏ nhất, rõ nhất để đáp ứng nhu cầu hiện tại là gì? | Thiết kế quá mức, chậm phản hồi, khó thay đổi |
| **Phản hồi** | Chúng ta có thể biết sớm quyết định này đúng hay sai bằng cách nào? | Lỗi và giả định sai được phát hiện muộn |
| **Can đảm** | Có sự thật hoặc thay đổi cần thiết nào ta đang tránh né? | Che rủi ro, giữ giải pháp lỗi thời, tích tụ nợ kỹ thuật |
| **Tôn trọng** | Quyết định này ảnh hưởng tới người dùng và đồng đội như thế nào? | Thiếu an toàn để phản ánh vấn đề, mất hợp tác, kiệt sức |

**Một giá trị đơn lẻ chưa đủ.** Can đảm không có tôn trọng có thể thành áp đặt; đơn giản không có phản hồi có thể thành làm sơ sài; giao tiếp không đi kèm hành động và kiểm chứng có thể biến thành họp liên tục.

## 3. Giá trị 1 — Giao tiếp (Communication)

**Giao tiếp trong XP** là làm cho thông tin cần thiết đến đúng người, đúng lúc, đủ rõ để cùng xây giải pháp đúng. Nó không được đo bằng số tin nhắn, số cuộc họp hay độ dài tài liệu.

Trong phần mềm, hiểu lầm thường xuất hiện giữa nhiều góc nhìn: người dùng nói bằng vấn đề nghiệp vụ; Product Owner nói bằng ưu tiên và kết quả; Developers quan tâm hành vi, dữ liệu, tích hợp; kiểm thử chú ý ngoại lệ; vận hành cần quan sát và khôi phục hệ thống. **Giao tiếp tốt biến những góc nhìn ấy thành hiểu biết chung có thể kiểm chứng.**

### 3.1. Giao tiếp là đối thoại, không chỉ chuyển giao đặc tả

Ví dụ Product Owner đưa user story:

> **Là** học viên, **tôi muốn** đăng ký workshop, **để** giữ được một chỗ phù hợp với lịch học.

Story này là **lời mời trao đổi**, chưa phải bản đặc tả đủ cho mọi trường hợp. Nhóm cần hỏi:

1. Điều kiện nào khiến một học viên được đăng ký?
2. Workshop hết chỗ có cho vào danh sách chờ không?
3. Nếu hai học viên đăng ký chỗ cuối cùng cùng lúc thì sao?
4. Học viên có được đăng ký hai lần không?
5. Khi gửi thông báo thất bại, trạng thái đăng ký có thay đổi không?
6. Ai có quyền xem, sửa hoặc hủy đăng ký?
7. Thế nào là kết quả có thể chấp nhận đối với người dùng?

Chỉ khi các bên trao đổi và thống nhất **ví dụ hành vi**, nhóm mới có nền tảng để viết kiểm thử và chia lát cắt phù hợp.

### 3.2. Ba cách làm cho giao tiếp đáng tin cậy hơn

**Thứ nhất: dùng ví dụ cụ thể.** Thay vì “hệ thống xử lý đăng ký chính xác”, hãy mô tả trường hợp còn chỗ, hết chỗ, gửi yêu cầu trùng và hai người tranh chỗ cuối cùng.

**Thứ hai: đưa phản hồi lại thành vòng kín.** Người nhận thông tin diễn đạt lại quyết định, giới hạn và bước tiếp theo. Nếu Product Owner nói “chưa làm thanh toán”, Developers cần xác nhận phạm vi đầu chỉ có workshop miễn phí hoặc đã có một cơ chế thanh toán độc lập nào khác.

**Thứ ba: kiểm tra bằng phần mềm và dữ liệu.** Sự hiểu biết chung cần được kiểm chứng bằng test, bản mẫu, Increment hoặc quan sát người dùng, không dừng ở câu “mọi người đã đồng ý”.

### 3.3. Kênh giao tiếp nên phù hợp với loại vấn đề

| Tình huống | Cách giao tiếp phù hợp | Vì sao |
| --- | --- | --- |
| Quy tắc nghiệp vụ chưa rõ | Trao đổi trực tiếp giữa người hiểu nghiệp vụ, Developers và kiểm thử; kèm ví dụ | Giảm vòng lặp hỏi-đáp qua nhiều tầng |
| Bất đồng giải pháp kỹ thuật | Whiteboard ngắn, pair programming, spike hoặc thử nghiệm | Kiểm chứng thay vì tranh luận ý kiến trừu tượng |
| Thay đổi API ảnh hưởng nhiều nhóm | Hợp đồng tích hợp rõ, ví dụ dữ liệu, thông tin phiên bản và đầu mối quyết định | Giữ các nhóm cùng hiểu ranh giới |
| Phát hiện lỗi bảo mật hoặc mất dữ liệu | Kênh phản ứng sự cố đúng thẩm quyền, thông tin tác động rõ | Không để rủi ro khẩn bị chìm trong backlog hoặc buổi họp định kỳ |
| Quyết định khó đảo ngược | Ghi lại ngắn gọn bối cảnh, lựa chọn, rủi ro và người chốt | Người đến sau hiểu lý do quyết định |
| Phản hồi về cách hợp tác | Trao đổi tôn trọng, tập trung hành vi và tác động | Giảm phòng thủ cá nhân, giữ khả năng cải tiến |

XP thường ưu tiên **giao tiếp gần và thường xuyên**, nhưng không có nghĩa mọi thông tin đều phải truyền miệng. Tài liệu, test, bản thiết kế và quyết định được ghi lại giúp giao tiếp **bền vững**, đặc biệt trong nhóm phân tán hoặc hệ thống cần truy vết.

### 3.4. Dấu hiệu thiếu Communication

- Story được đánh dấu “Ready” nhưng Developers và Product Owner hiểu khác về Done.
- Một phụ thuộc được biết từ đầu nhưng chỉ xuất hiện vào ngày tích hợp.
- Người kiểm thử nhận phần mềm cuối Sprint mà chưa từng thấy kịch bản nghiệp vụ.
- Reviewer chỉ nói “code không tốt” mà không chỉ ra rủi ro hoặc ví dụ cụ thể.
- Một thành viên liên tục phải đoán ai có quyền quyết định.

**Hành động nhỏ có thể thử:** Với các PBI gần được chọn, tổ chức cuộc trao đổi ba góc nhìn *nghiệp vụ – kỹ thuật – kiểm thử* để cùng viết hai hoặc ba ví dụ chấp nhận quan trọng trước khi code.

## 4. Giá trị 2 — Đơn giản (Simplicity)

**Simplicity** trong XP hướng nhóm tới **giải pháp đơn giản nhất có thể đáp ứng nhu cầu hiện tại một cách đúng đắn và có chất lượng**. Đơn giản không đồng nghĩa ít dòng code bằng mọi giá, bỏ kiểm thử, bỏ thiết kế hoặc lờ đi những ràng buộc đã biết.

Một giải pháp đơn giản giúp:

- Người mới hiểu mã và hành vi nhanh hơn.
- Phần mềm có ít nhánh không cần thiết để kiểm thử.
- Nhóm điều chỉnh hướng đi khi có phản hồi mới mà ít phải phá thiết kế cũ.
- Phản hồi xuất hiện sớm vì thời gian xây dựng lát cắt đầu ngắn hơn.
- Tránh chi tiền và công sức cho những nhu cầu chưa được xác thực.

### 4.1. YAGNI và thiết kế vừa đủ

**YAGNI — You Aren't Gonna Need It** nhắc nhóm không xây chức năng hoặc cơ chế phức tạp chỉ vì *có thể một ngày nào đó sẽ cần*. Ví dụ, nền tảng workshop mới chỉ có một loại đặt chỗ không nhất thiết phải xây ngay bộ quy tắc giảm giá nhiều cấp, đặt chỗ liên tổ chức và nền tảng plugin cho mọi loại sự kiện.

Nhưng YAGNI **không biện minh cho việc bỏ những yêu cầu đã biết** như phân quyền, tính nhất quán chỗ, sao lưu dữ liệu quan trọng hoặc khả năng kiểm chứng. Nếu yêu cầu hiện tại đòi hỏi chống đăng ký trùng khi nhiều người thao tác, việc xây kiểm soát đồng thời là thiết kế vừa đủ, không phải “tối ưu quá sớm”.

### 4.2. So sánh hai lựa chọn thiết kế

**Tình huống:** Hệ thống cần gửi thông báo khi học viên đăng ký workshop thành công.

| Lựa chọn | Lợi ích | Rủi ro/chi phí cần xét |
| --- | --- | --- |
| **A. Thực hiện một luồng xác nhận đáng tin, tách ranh giới thông báo rõ ràng** | Đáp ứng nhu cầu hiện tại, dễ thử và thay đổi | Cần xử lý thất bại của dịch vụ thông báo đúng theo chính sách |
| **B. Xây ngay nền tảng workflow tổng quát với hàng chục loại trigger và rule** | Có thể mở rộng nhiều trường hợp tương lai | Tăng chi phí, kiểm thử và phức tạp trước khi biết nhu cầu thật |

Nếu tổ chức chưa có bằng chứng cần một workflow engine tổng quát, **A thường là lựa chọn đáng thử trước**. Nhưng nếu sản phẩm đã có nhiều luồng tương đồng và yêu cầu vận hành chung được xác thực, giải pháp B có thể hợp lý. Đơn giản là **đơn giản trong bối cảnh**, không phải luôn chọn phương án ít cấu trúc nhất.

### 4.3. Đơn giản thông qua lát cắt dọc

Thay vì một PBI “hoàn thiện toàn bộ chức năng workshop”, nhóm có thể lần lượt giao:

1. Học viên xem danh sách workshop còn chỗ.
2. Học viên đủ điều kiện đăng ký một chỗ và nhận trạng thái đúng.
3. Học viên xem đăng ký của chính mình.
4. Học viên hủy theo chính sách; chỗ trống cập nhật chính xác.
5. Học viên nhận nhắc lịch qua một kênh đã được kiểm chứng.

Mỗi lát cắt đi qua phần giao diện, nghiệp vụ, dữ liệu và kiểm thử cần thiết. **Không nên chia theo từng tầng kỹ thuật rồi gọi mỗi tầng là giá trị người dùng đã được giao**, nếu chưa có hành vi đầu cuối hoạt động được.

### 4.4. Khi “đơn giản” bị hiểu sai

| Hiểu sai | Hệ quả | Cách hiểu phù hợp XP |
| --- | --- | --- |
| “Code nhanh, test sau” | Lỗi hồi quy và làm lại tích tụ | Giữ kiểm thử cần thiết ngay trong lát cắt |
| “Không cần nói với người dùng” | Xây sai thứ cần đơn giản hóa | Chỉ đơn giản hóa sau khi hiểu mục tiêu |
| “Viết mọi thứ vào một hàm cho ít file” | Phụ thuộc cao, khó thay đổi | Tối ưu khả năng hiểu, thay đổi và kiểm chứng, không chỉ số dòng |
| “Không cần xử lý dữ liệu cạnh tranh vì hiếm xảy ra” | Tính đúng đắn bị phá khi tăng sử dụng | Giữ các ràng buộc đã biết dù giải pháp nhỏ |
| “Cứ tạo abstraction tổng quát để sau dùng” | Thiết kế thừa và chi phí bảo trì tăng | Trì hoãn khả năng chưa được chứng minh, refactor khi nhu cầu xuất hiện |

**Đơn giản không phải thiếu trách nhiệm**; đó là sự chủ động loại bỏ những gì chưa cần, trong khi làm đúng những gì đã cần.

## 5. Giá trị 3 — Phản hồi (Feedback)

**Feedback** trong XP là khả năng nhận thông tin đáng tin cậy về **hành vi phần mềm, tính đúng đắn, thiết kế, nhu cầu người dùng và cách nhóm đang làm việc**, rồi dùng thông tin ấy để thay đổi quyết định kịp thời.

Phản hồi sớm giúp giảm chi phí sửa sai. Nếu nhóm phát hiện lỗi đăng ký trùng ngay khi viết hàm nghiệp vụ, phạm vi điều tra nhỏ hơn nhiều so với khi lỗi xuất hiện sau một tháng, dữ liệu đã phát tán tới email, báo cáo và hệ thống thanh toán.

### 5.1. Những vòng phản hồi bổ trợ nhau

| Vòng phản hồi | Phương tiện ví dụ | Câu hỏi được trả lời | Độ trễ mong muốn |
| --- | --- | --- | --- |
| **Ngay khi viết code** | Unit test, TDD, chạy kiểm tra cục bộ | Hàm hoặc quy tắc có hành xử đúng? | Rất ngắn, phù hợp việc đang làm |
| **Khi tích hợp thay đổi** | CI, kiểm thử tích hợp, kiểm tra chất lượng tự động | Thay đổi có phá hệ thống chung? | Sớm sau mỗi lần tích hợp |
| **Khi kiểm chứng nghiệp vụ** | Acceptance criteria, ví dụ hành vi, kiểm thử đầu cuối | Lát cắt có đáp ứng nhu cầu đã thống nhất? | Trong vòng triển khai lát cắt |
| **Khi dùng thử hoặc phát hành** | Demo Increment, thử với người dùng, quan sát hành vi | Giải pháp có giải quyết vấn đề thật? | Càng sớm càng tốt nhưng đủ bằng chứng |
| **Khi vận hành thật** | Logs, metrics, traces, cảnh báo, báo lỗi và hỗ trợ | Hệ thống có đáng tin, an toàn và dễ vận hành? | Theo mức rủi ro và dịch vụ |
| **Khi cải tiến cách làm** | Retrospective, phân tích luồng, ý kiến thành viên | Nhóm đang bị cản trở ở đâu? | Định kỳ và khi có dấu hiệu cần thiết |

Không phải mọi vòng đều có thể có phản hồi tức thì. Đo tỷ lệ người dùng quay lại học tuần sau cần thời gian quan sát; điều quan trọng là **không trì hoãn những phản hồi có thể có sớm**, và không giả định một test xanh đã xác nhận toàn bộ giá trị sản phẩm.

### 5.2. Feedback thực sự cần đi tới hành động

Giả sử pipeline CI thường xuyên báo lỗi kiểm thử phân quyền. Nhóm biết nhưng vẫn merge vì “bài kiểm thử này hay chập chờn”. Họ đang **thu tín hiệu nhưng không dùng phản hồi**.

Một cách xử lý tốt hơn:

1. Xác định bài kiểm thử thất bại do lỗi sản phẩm, hạ tầng kiểm thử hay dữ liệu giả lập.
2. Phân loại rủi ro; nếu có nguy cơ lộ dữ liệu, ngăn phát hành cho tới khi được kiểm chứng an toàn.
3. Sửa lỗi thực hoặc sửa bài kiểm thử không đáng tin, thay vì đơn giản xóa test cho xanh.
4. Theo dõi số lần tái diễn; cải thiện độ tin cậy của pipeline.
5. Cập nhật quy tắc làm việc nếu phản hồi liên tục bị bỏ qua.

Vòng phản hồi chỉ khép kín khi **có quyết định hoặc học hỏi từ tín hiệu nhận được**.

### 5.3. Minh họa phản hồi ở các tầng

~~~mermaid
flowchart LR
    A["Giả thuyết giá trị và user story"] --> B["Viết tiêu chí + test"]
    B --> C["Xây lát cắt nhỏ"]
    C --> D["Unit/integration tests + CI"]
    D --> E["Increment đạt chất lượng"]
    E --> F["Người dùng và vận hành quan sát"]
    F --> G["Học hỏi: giữ, sửa, bỏ, mở rộng"]
    G --> A
    D -->|"Test thất bại"| C
~~~

Đây là vòng học hỏi tổng quát, không phải một công thức quy định mọi nhóm phải dùng cùng công cụ hoặc thứ tự chính xác.

### 5.4. Phản hồi về output khác phản hồi về outcome

**Output:** nhóm đã giao nút “Đăng ký workshop” và kiểm thử hoạt động.

**Outcome:** người học có thể đăng ký thành công mà không cần bộ phận hỗ trợ; trạng thái xác nhận đáng tin và tỷ lệ lỗi giảm.

Kiểm thử tự động chủ yếu giúp kiểm chứng **hành vi và chất lượng đã mô tả**. Quan sát người dùng giúp biết hành vi đó **có tạo giá trị thật hay không**. Cả hai loại phản hồi đều cần thiết trong phát triển thích ứng.

## 6. Giá trị 4 — Can đảm (Courage)

**Can đảm trong XP** là dám hành động dựa trên sự thật và lợi ích dài hạn của sản phẩm, ngay cả khi lựa chọn đó khó chịu: thừa nhận giả định sai, nêu rủi ro, thay đổi thiết kế, bỏ chức năng không còn giá trị hoặc từ chối đánh dấu Done khi chưa đạt chất lượng.

Can đảm không phải **liều lĩnh, coi thường quy định, phá mã đang chạy mà không kiểm thử**, hay tranh luận áp đảo người khác. Can đảm đi cùng **phản hồi, tôn trọng, giao tiếp và bước thay đổi nhỏ để kiểm soát rủi ro**.

### 6.1. Can đảm nói sự thật về trạng thái công việc

Ví dụ nhóm đang gần ngày phát hành, nhưng kiểm thử cho thấy hai học viên có thể cùng chiếm chỗ cuối của một workshop. Người chịu trách nhiệm có thể ngại nói ra vì sợ gây chậm trễ.

Thực hành Courage:

- Nêu vấn đề và bằng chứng cụ thể, không che lỗi trong báo cáo.
- Giải thích tác động: xác nhận sai, bộ phận hỗ trợ phải xử lý, người dùng mất niềm tin.
- Đề xuất phương án an toàn: sửa và kiểm thử cạnh tranh, thu hẹp phạm vi phát hành, hoặc dời tính năng chưa sẵn sàng.
- Phối hợp với Product Owner và người có thẩm quyền để quyết định theo giá trị và rủi ro.
- Không gắn trách nhiệm sai sót với một cá nhân trước khi tìm nguyên nhân hệ thống.

Một hành động như vậy có thể khiến kế hoạch thay đổi, nhưng **giữ lòng tin và khả năng phát triển lâu dài**.

### 6.2. Can đảm refactor khi có tín hiệu phù hợp

Refactoring là **thay đổi cấu trúc bên trong mà không cố ý thay đổi hành vi quan sát được**. Nếu mã trùng lặp gây lỗi và làm việc thêm quy tắc khó khăn, nhóm có thể refactor thành cấu trúc đơn giản hơn, có kiểm thử bảo vệ.

Can đảm thể hiện qua:

1. Thừa nhận thiết kế từng hợp lý nay không còn phù hợp.
2. Có kiểm thử đủ để nhận biết hành vi bị phá.
3. Refactor từng bước nhỏ, chạy test thường xuyên, tích hợp sớm.
4. Tránh “đập đi xây lại” toàn bộ nếu không có bằng chứng và phương án rủi ro phù hợp.
5. Kiểm tra thiết kế mới có giúp nhóm thay đổi an toàn hơn không.

**Can đảm sửa thiết kế** không có nghĩa thay đổi mọi thứ cho đẹp. Đôi khi can đảm là **không làm một refactor lớn** vì nhu cầu hiện tại chưa chứng minh lợi ích hoặc rủi ro quá cao.

### 6.3. Can đảm nhận phản hồi trái ý

Một Product Owner có thể rất thích giao diện lịch tháng, nhưng người dùng thử lại ưu tiên danh sách khung giờ. XP khuyến khích nhóm nhìn phản hồi một cách cởi mở, **không bảo vệ phương án chỉ vì đã đầu tư công sức**.

Nếu đã có 70% mã lịch tháng, đó là chi phí đã phát sinh, **không tự chứng minh hoàn thiện nốt là lựa chọn tốt hơn**. Nhóm cần cân nhắc giá trị tương lai, khả năng tái sử dụng, chi phí chuyển hướng và mục tiêu sản phẩm.

### 6.4. Các dấu hiệu nhầm Courage với liều lĩnh

| Hành vi | Can đảm có trách nhiệm? | Vì sao |
| --- | --- | --- |
| Công khai một lỗ hổng và phối hợp sửa trước phát hành | Có | Minh bạch để bảo vệ người dùng |
| Xóa kiểm thử bảo mật cho pipeline xanh | Không | Né phản hồi và tăng rủi ro |
| Dám đề xuất bỏ tính năng ít giá trị dựa trên thử nghiệm | Có | Điều chỉnh quyết định theo bằng chứng |
| Thay kiến trúc toàn hệ thống trong một đêm không có kế hoạch khôi phục | Không | Thay đổi lớn, khó đảo ngược, thiếu kiểm chứng |
| Đặt câu hỏi phản biện yêu cầu của cấp quản lý một cách tôn trọng | Có | Làm rõ mục tiêu và hậu quả |
| Chê trách người mới ngay trước cả nhóm vì viết code chưa tốt | Không | Làm giảm tôn trọng và khả năng học hỏi |

## 7. Giá trị 5 — Tôn trọng (Respect)

**Respect** nghĩa là nhìn nhận mỗi người có giá trị, năng lực và những giới hạn thực tế; lắng nghe góc nhìn của họ; không lạm dụng quyền lực hay chỉ tiêu để ép quyết định làm hại người dùng hoặc đồng đội. Trong XP, tôn trọng còn thể hiện ở **trách nhiệm với mã nguồn, sản phẩm, khách hàng và thế hệ người bảo trì sau này**.

Respect thường được nhắc như giá trị thứ năm trong những trình bày XP về sau. Khi đọc nguồn lịch sử, có thể gặp danh sách bốn giá trị ban đầu: **giao tiếp, đơn giản, phản hồi, can đảm**. Điều này không nên được hiểu rằng tôn trọng chỉ là “phụ kiện”; trong cách trình bày năm giá trị hiện nay, nó là nền tảng cho sự hợp tác bền vững.

### 7.1. Respect trong trao đổi kỹ thuật

Một code review có thể cùng nội dung kỹ thuật nhưng hiệu quả khác hẳn tùy cách nói:

| Cách phản hồi làm giảm tôn trọng | Cách phản hồi hỗ trợ hợp tác |
| --- | --- |
| “Ai lại viết code kiểu này?” | “Đoạn này có thể tạo dữ liệu trùng khi hai yêu cầu đến đồng thời; ta cùng xem trường hợp kiểm thử này nhé.” |
| “Cách của tôi là chuẩn, sửa theo đi.” | “Tôi nghiêng về phương án A vì dễ kiểm thử hơn. Có ràng buộc nào khiến B phù hợp hơn không?” |
| “Bạn phải biết cái này rồi chứ.” | “Quy tắc nghiệp vụ này chưa được giải thích rõ; tôi sẽ chia sẻ ví dụ và cùng kiểm chứng.” |
| “Cứ làm thêm giờ đi, Sprint đã hứa.” | “Với năng lực hiện tại, phần nào có thể dời mà vẫn giữ chất lượng và mục tiêu?” |

Respect **không đồng nghĩa né mọi bất đồng**. Một lỗi nghiêm trọng vẫn phải được chỉ ra rõ; khác biệt là **phê bình bằng chứng và hành vi, không hạ thấp con người**.

### 7.2. Respect với người dùng

Nhóm thể hiện tôn trọng bằng cách:

- Không phát hành tính năng có nguy cơ lộ thông tin chỉ để đạt mốc.
- Không đưa người dùng vào một thử nghiệm rủi ro mà thiếu bảo vệ hoặc sự đồng ý phù hợp.
- Thông báo trạng thái đăng ký rõ, không hiển thị thành công khi giao dịch thực tế thất bại.
- Lắng nghe khó khăn của những người có khả năng tiếp cận, thiết bị và bối cảnh khác nhau.
- Quan tâm đến khả năng vận hành và khôi phục khi sự cố xảy ra.

**Tôn trọng không chỉ hướng vào người cùng nhóm; nó gắn với những người chịu ảnh hưởng bởi phần mềm.**

### 7.3. Respect với năng lực bền vững

XP coi trọng nhịp làm việc có thể duy trì. Nếu nhóm liên tục yêu cầu làm thêm giờ để bù dự báo sai, chất lượng và khả năng học hỏi có thể suy giảm. Tôn trọng thể hiện ở việc **lập kế hoạch với năng lực thực tế, nhận diện dấu hiệu quá tải và sửa nguyên nhân hệ thống**, không mặc định rằng sự hy sinh cá nhân là giải pháp quản trị lâu dài.

Điều này không có nghĩa mọi tình huống đều tránh được áp lực hay sự cố; các ca khẩn có thể cần nỗ lực đặc biệt theo thỏa thuận và quy định. Vấn đề là **không biến trạng thái khẩn cấp thành chế độ làm việc bình thường**.

### 7.4. Tôn trọng và an toàn tâm lý

Một nhóm có thể tạo điều kiện để thành viên:

- Nêu “tôi chưa hiểu yêu cầu này” mà không bị đánh giá yếu kém.
- Báo test thất bại hoặc ước lượng ban đầu sai sớm.
- Phản biện thiết kế của người có kinh nghiệm mà không bị trả đũa.
- Đề nghị hỗ trợ khi công việc bị chặn.
- Cùng rút kinh nghiệm từ sự cố bằng chứng thay vì tìm người để đổ lỗi.

Đây là **điều kiện giúp Communication, Feedback và Courage vận hành**, chứ không phải lời hứa rằng mọi cuộc trao đổi luôn dễ chịu.

## 8. Năm giá trị bổ trợ nhau trong một quyết định

Hãy xem tình huống: “Học viên hủy workshop nhưng số chỗ trống không được cập nhật đúng trong một số trường hợp hiếm.”

| Giá trị | Nhìn tình huống từ góc độ nào? | Hành động minh họa |
| --- | --- | --- |
| **Giao tiếp** | Ai hiểu quy tắc hủy, khôi phục chỗ và ngoại lệ? | Product Owner, Developers và kiểm thử cùng làm rõ ví dụ |
| **Đơn giản** | Cách sửa nhỏ nhất, an toàn nhất đáp ứng đúng quy tắc là gì? | Sửa luồng cập nhật trạng thái, tránh dựng lại toàn bộ nền tảng |
| **Phản hồi** | Làm sao biết lỗi đã được sửa và không tái phát? | Test trường hợp hủy trùng, đồng thời, lỗi giao dịch; CI và log |
| **Can đảm** | Có cần công khai lỗi và hoãn phát hành phần không an toàn? | Báo rủi ro, bảo vệ chất lượng, điều chỉnh kế hoạch nếu cần |
| **Tôn trọng** | Người dùng và đồng đội chịu ảnh hưởng thế nào? | Giữ dữ liệu đúng, hỗ trợ người đã gặp lỗi, review không đổ lỗi |

Đây là lý do XP thường coi các thực hành có tính **bổ trợ lẫn nhau**: test giúp dám refactor; giao tiếp giúp test đúng quy tắc; thiết kế đơn giản giúp vòng phản hồi nhanh; tôn trọng giúp mọi người dám nêu dữ liệu không thuận lợi.

### 8.1. Khi các giá trị có vẻ xung đột

| Căng thẳng thường gặp | Cách cân bằng |
| --- | --- |
| **Đơn giản vs chất lượng** | Không xây tính năng chưa cần, nhưng giữ các điều kiện an toàn và kiểm thử thuộc nhu cầu hiện tại |
| **Giao tiếp vs tập trung** | Trao đổi đúng người, đúng thời điểm và lưu quyết định ngắn; không mở họp không có mục đích |
| **Phản hồi nhanh vs chi phí thử nghiệm** | Chọn phép thử nhỏ, có điều kiện dừng và đủ bằng chứng; không thử rủi ro cao trực tiếp trên người dùng nếu thiếu bảo vệ |
| **Can đảm vs tôn trọng** | Nêu bất đồng thẳng thắn nhưng dựa trên bằng chứng, không công kích cá nhân |
| **Đơn giản vs nhu cầu tương lai** | Tách thiết kế dễ thay đổi, không xây sẵn mọi giả định chưa được xác minh |
| **Tôn trọng nhịp làm việc vs yêu cầu khẩn** | Xử lý sự cố theo mức độ và thẩm quyền, sau đó cải thiện hệ thống để không lặp lại khẩn cấp |

**Không nên dùng một giá trị làm lý do bỏ các giá trị còn lại.**

## 9. Từ giá trị XP tới các thực hành quen thuộc

Nhiều thực hành gắn với XP có thể được hiểu như **cơ chế cụ thể giúp nhóm duy trì giá trị**. Một thực hành thường hỗ trợ nhiều giá trị cùng lúc.

| Thực hành | Giá trị được hỗ trợ nổi bật | Cách tạo tác dụng |
| --- | --- | --- |
| **Pair programming** | Giao tiếp, phản hồi, tôn trọng, can đảm | Hai người cùng suy nghĩ, xem mã và nhận phản hồi tức thì |
| **Test-driven development (TDD)** | Phản hồi, đơn giản, can đảm | Viết kỳ vọng có thể kiểm tra; phát triển đủ để test đạt; refactor có bảo vệ |
| **Continuous Integration (CI)** | Phản hồi, giao tiếp, can đảm | Tích hợp thường xuyên, phát hiện xung đột và hồi quy sớm |
| **Refactoring** | Đơn giản, can đảm, phản hồi | Cải thiện thiết kế từng bước mà giữ hành vi đã kiểm chứng |
| **Small releases** | Phản hồi, đơn giản, giao tiếp | Đưa phần giá trị nhỏ tới người dùng sớm để học |
| **Simple design** | Đơn giản, can đảm | Giữ cấu trúc vừa đủ, giảm phức tạp suy đoán |
| **Collective code ownership** | Giao tiếp, tôn trọng, can đảm | Tránh vùng mã “chỉ một người được sửa”, cùng giữ trách nhiệm chất lượng |
| **Coding standards** | Giao tiếp, tôn trọng, đơn giản | Giảm chi phí hiểu mã và review, tránh tranh luận vụn vặt |
| **Customer collaboration / real customer involvement** | Giao tiếp, phản hồi, tôn trọng | Làm rõ giá trị và kiểm tra giả định nghiệp vụ |
| **Sustainable pace** | Tôn trọng, can đảm, phản hồi | Giữ chất lượng, sức khỏe hợp tác và khả năng dự báo |
| **Planning bằng những lát cắt nhỏ** | Giao tiếp, đơn giản, phản hồi | Ra quyết định gần thời điểm cần, giao và kiểm tra thường xuyên |

Đây là **bản đồ liên hệ học tập**, không phải tuyên bố mỗi thực hành chỉ thuộc một giá trị hoặc mọi nhóm phải đồng loạt áp dụng tất cả. Cần hiểu mục đích và giới hạn của từng thực hành trong bối cảnh nhóm.

## 10. Ví dụ TDD: phản hồi nhanh để giữ thiết kế đơn giản

**TDD** thường được diễn đạt qua chu trình **Red – Green – Refactor**:

1. **Red:** Viết một kiểm thử nhỏ mô tả hành vi cần có và thấy nó thất bại đúng lý do.
2. **Green:** Viết lượng mã tối thiểu hợp lý để kiểm thử đạt.
3. **Refactor:** Cải thiện cấu trúc mã trong khi kiểm thử tiếp tục đạt.

Giả sử hệ thống cần kiểm tra liệu học viên có thể đăng ký workshop còn chỗ hay không. Nhóm làm rõ trước các quy tắc, sau đó viết những ví dụ kiểm thử:

~~~gherkin
Feature: Kiem soat dang ky workshop

  Scenario: Hoc vien du dieu kien dang ky khi con cho
    Given hoc vien A du dieu kien tham gia workshop W
    And W con mot cho trong
    When A gui yeu cau dang ky hop le
    Then A nhan trang thai dang ky duoc xac nhan
    And so dang ky xac nhan khong vuot suc chua

  Scenario: Khong cho xac nhan vuot suc chua
    Given W chi con mot cho trong
    When hai hoc vien du dieu kien gui yeu cau gan nhu dong thoi
    Then so dang ky duoc xac nhan toi da la mot
    And yeu cau khong thanh cong co trang thai ro rang

  Scenario: Khong cho xem dang ky cua nguoi khac
    Given hoc vien B khong co quyen xem dang ky cua A
    When B yeu cau xem dang ky cua A
    Then he thong tu choi truy cap
~~~

Những kịch bản này thể hiện **kỳ vọng cần kiểm chứng**; chúng không tự quy định chi tiết kiến trúc hoặc đảm bảo rằng một unit test đơn lẻ có thể kiểm tra hành vi cạnh tranh thực tế. Hạng mục liên quan đến đồng thời và quyền truy cập cần **kết hợp kiểm thử phù hợp ở nhiều mức**, ví dụ kiểm thử giao dịch hoặc tích hợp.

### 10.1. Năm giá trị xuất hiện thế nào trong TDD?

- **Communication:** Ví dụ kiểm thử giúp Product Owner, Developers và kiểm thử nói về cùng một hành vi.
- **Simplicity:** Viết đủ mã để đáp ứng kỳ vọng, không tạo sẵn hàng loạt chức năng chưa cần.
- **Feedback:** Test thất bại sớm khi hành vi không đúng.
- **Courage:** Dám sửa cấu trúc mã sau khi có mạng lưới kiểm thử đáng tin.
- **Respect:** Tôn trọng người bảo trì bằng những kiểm thử dễ hiểu và mã có khả năng thay đổi an toàn.

### 10.2. TDD không tự giải quyết mọi loại chất lượng

Unit test xanh không tự chứng minh:

- Trạng thái giao dịch đúng khi hai yêu cầu thực hiện đồng thời.
- Truy cập trái phép bị chặn ở mọi API.
- Hệ thống chịu tải phù hợp hoặc vận hành tốt.
- Chức năng tạo giá trị người dùng trong đời sống thật.

Vì vậy, TDD cần đi cùng **kiểm thử tích hợp, bảo mật, hiệu năng, nghiệm thu và quan sát vận hành** theo rủi ro của sản phẩm. XP đề cao phản hồi liên tục, không đồng nhất toàn bộ phản hồi với unit test.

## 11. Pair programming: giao tiếp và phản hồi ngay khi làm việc

**Pair programming** là thực hành hai người cùng giải quyết một vấn đề lập trình tại một thời điểm, thường luân phiên vai trò người điều khiển thao tác (*driver*) và người cùng suy nghĩ, quan sát, đặt câu hỏi (*navigator*). Trọng tâm không phải người này code còn người kia “canh lỗi”, mà là **cùng chịu trách nhiệm suy nghĩ về thiết kế, hành vi và chất lượng**.

### 11.1. Tình huống phù hợp để thử

- Luồng nghiệp vụ rủi ro cao như đăng ký chỗ cuối hoặc phân quyền.
- Một thành viên mới cần hiểu hệ thống và tiêu chuẩn kiểm thử.
- Công việc đang bị tắc vì hai cách hiểu kiến trúc khác nhau.
- Cần giảm phụ thuộc vào một chuyên gia duy nhất.
- Refactor một phần mã khó, cần phản hồi thiết kế liên tục.

### 11.2. Nguyên tắc phối hợp có tôn trọng

| Điều nên làm | Điều cần tránh |
| --- | --- |
| Thống nhất mục tiêu và tiêu chí hoàn thành của phiên làm việc | Ghép đôi không có mục tiêu rồi gọi đó là collaboration |
| Luân phiên vai trò để cả hai cùng học | Một người làm tất cả, người còn lại chỉ quan sát bị động |
| Hỏi và giải thích bằng ví dụ, không chỉ ra lệnh | Người nhiều kinh nghiệm áp đảo hoặc chế giễu |
| Dừng ngắn để thống nhất khi cách hiểu khác nhau | Tăng tốc gõ mã để né trao đổi khó |
| Nghỉ phù hợp, chú ý khả năng tập trung | Ép pairing liên tục không xét sức khỏe và loại việc |
| Kết hợp review, test và CI phù hợp | Cho rằng pairing thay thế mọi kiểm thử hoặc quy định bảo mật |

Pair programming **không phải giải pháp tối ưu cho mọi giờ làm hoặc mọi loại nhiệm vụ**. Nhóm cần thử theo nhu cầu, quan sát kết quả về kiến thức chia sẻ, lỗi, thời gian hoàn tất và trải nghiệm thành viên.

## 12. CI và phát hành nhỏ: biến Feedback thành nhịp công việc

**Continuous Integration** không chỉ là có một pipeline được chạy khi gần release. Ý tưởng cốt lõi là **tích hợp thay đổi thường xuyên với hệ thống chung và kiểm chứng sớm** để tránh những bất ngờ lớn khi ghép nhiều phần việc.

### 12.1. Một vòng tích hợp có phản hồi tốt

~~~mermaid
flowchart TD
    A["Chọn lát cắt có giá trị"] --> B["Viết test và triển khai thay đổi nhỏ"]
    B --> C["Tích hợp với nhánh/code chung"]
    C --> D["Pipeline kiểm thử và kiểm tra"]
    D --> E{"Đạt tiêu chí?"}
    E -->|"Chưa"| F["Điều tra, sửa mã hoặc test, chạy lại"]
    F --> B
    E -->|"Đạt"| G["Increment đủ chất lượng theo DoD"]
    G --> H["Phát hành hoặc thử với người dùng khi phù hợp"]
    H --> I["Thu phản hồi và cập nhật backlog"]
    I --> A
~~~

Một nhóm có thể triển khai **continuous delivery/deployment** theo mức kiểm soát phù hợp, nhưng **CI không tự đồng nghĩa tự động phát hành ra production**. Điều kiện phát hành phải tính tới an toàn, dữ liệu, phê duyệt và vận hành thực tế.

### 12.2. Khi pipeline báo lỗi

Nhóm cần làm rõ chính sách:

- Ai nhận thông tin và có thể bắt đầu điều tra?
- Thay đổi tiếp theo có được tích hợp nếu nhánh chung đang lỗi không?
- Làm sao phân biệt test flaky với lỗi sản phẩm và giữ khả năng tái hiện?
- Lỗi bảo mật hoặc dữ liệu có cần chặn phát hành ngay?
- Khi sửa, cần kiểm chứng môi trường nào và thông báo ai?

**Feedback nhanh chỉ có giá trị khi cả nhóm phản ứng kịp thời và có trách nhiệm.**

### 12.3. Small releases không đồng nghĩa tung tính năng chưa an toàn

Một phát hành nhỏ có thể là cho một nhóm người dùng giới hạn sử dụng **lát cắt đã đạt DoD**, kèm khả năng theo dõi và phục hồi phù hợp. Việc giảm phạm vi hoặc dùng feature flag không cho phép bỏ các kiểm soát bắt buộc; feature flag cũng cần được quản lý để tránh rủi ro cấu hình và nợ kỹ thuật.

## 13. Can đảm thay đổi thiết kế nhờ phản hồi kỹ thuật

Thiết kế phần mềm rất dễ trở nên cứng nhắc khi nhóm cố dự đoán mọi trường hợp tương lai. XP khuyến khích **simple design**, **refactoring thường xuyên** và kiểm thử để có thể thay đổi khi nhu cầu được chứng minh.

### Ví dụ

Ban đầu workshop chỉ có một quy tắc đăng ký: đủ điều kiện và còn chỗ. Nhóm viết một thành phần xử lý rõ ràng, có test. Sau vài Increment, sản phẩm phát sinh quy tắc ưu tiên cho nhóm học viên đặc biệt.

Một hướng thích ứng:

1. Viết ví dụ hành vi mới và làm rõ ngoại lệ với người hiểu nghiệp vụ.
2. Kiểm tra thiết kế hiện tại, xác định phần thật sự cần thay đổi.
3. Refactor nhỏ để tách quy tắc đủ điều kiện nếu việc đó làm mã dễ hiểu và dễ thử hơn.
4. Tạo thêm hành vi và kiểm thử tương ứng, không bỏ các test cũ.
5. Tích hợp, đánh giá Increment và tiếp tục quan sát phản hồi.

Nhóm **không cần** xây hệ thống plugin quy tắc từ ngày đầu để thể hiện “kiến trúc tốt”. Đồng thời **không nên** giữ mọi quy tắc chồng chất trong một hàm lớn khi nhu cầu mới đã chứng minh cần cấu trúc rõ hơn.

### Dấu hiệu refactoring đáng cân nhắc

| Dấu hiệu | Câu hỏi cần hỏi | Phản ứng có trách nhiệm |
| --- | --- | --- |
| Lặp cùng quy tắc ở nhiều nơi, thường gây lỗi | Có một khái niệm nghiệp vụ chung đã đủ rõ? | Refactor với test, tránh tổng quát hóa quá mức |
| Thay một trường kéo theo sửa nhiều tầng không liên quan | Có phụ thuộc không cần thiết? | Cải thiện ranh giới phụ thuộc theo từng bước |
| Code khó viết test | Thiết kế đang gắn chặt vào môi trường hoặc trạng thái? | Tách phần có thể kiểm chứng, làm rõ tác động |
| Một thay đổi rất nhỏ đòi di trú lớn | Có thiết kế tương thích chuyển tiếp an toàn? | Thử phương án theo giai đoạn, kiểm tra khôi phục |
| Đề xuất “viết lại từ đầu vì mã xấu” | Bằng chứng giá trị có lớn hơn rủi ro? | Đánh giá chi phí, cơ hội cải tiến từng phần và phương án rollback |

## 14. Tình huống xuyên suốt: đội phát triển đăng ký workshop

**Bối cảnh:** Một nhóm gồm Product Owner, Developers đa kỹ năng, người phụ trách kiểm thử và các bên vận hành đang phát triển chức năng đăng ký workshop cho nền tảng học tập. Mục tiêu là **học viên tự đăng ký được chỗ phù hợp, nhận trạng thái đáng tin và giảm xử lý thủ công**.

Backlog ban đầu gồm:

| Hạng mục | Giá trị dự kiến | Điều chưa biết |
| --- | --- | --- |
| Xem workshop còn chỗ | Người học tìm được buổi phù hợp | Lịch tháng hay danh sách giờ được ưa thích? |
| Đăng ký chỗ | Người học tự giữ chỗ | Xử lý yêu cầu đồng thời và đăng ký trùng |
| Xem đăng ký của mình | Biết chính xác trạng thái | Quyền truy cập và hiển thị lỗi |
| Tự hủy | Giảm công việc hỗ trợ | Giới hạn thời gian hủy và cách trả chỗ |
| Gửi nhắc lịch | Giảm bỏ lỡ | Kênh và tần suất phù hợp |

### 14.1. Giao tiếp trước khi code

Thay vì Developers nhận một mô tả “Làm trang đăng ký” rồi tự đoán, nhóm tổ chức trao đổi ngắn:

- Product Owner nêu người dùng và kết quả mong muốn.
- Developers hỏi về số chỗ, trạng thái và tình huống đồng thời.
- Người phụ trách kiểm thử đề nghị kịch bản lỗi, quyền truy cập, gửi lặp.
- Vận hành hỏi cách phát hiện trường hợp số chỗ không nhất quán.

Nhóm thống nhất tiêu chí chấp nhận và **một lát cắt nhỏ có thể thử**: một học viên đủ điều kiện đăng ký một workshop còn chỗ và xem trạng thái.

### 14.2. Đơn giản hóa phạm vi mà không bỏ điều cốt lõi

Nhóm chưa làm lịch tháng kéo thả, hệ thống điểm thưởng hoặc nhắc lịch đa kênh. Thay vào đó, họ chọn danh sách khung giờ đơn giản để giao sớm.

Nhưng phần đầu vẫn phải:

- Kiểm tra quyền của học viên.
- Không xác nhận vượt sức chứa khi nhiều yêu cầu đồng thời.
- Phản hồi trạng thái thất bại/thành công rõ ràng.
- Có kiểm thử và tín hiệu vận hành tối thiểu cần thiết.

**Nhóm bỏ tính năng tùy chọn chưa được kiểm chứng, không bỏ tính đúng đắn.**

### 14.3. Thiết lập phản hồi ở nhiều tầng

- Viết test cho quy tắc nghiệp vụ và hành vi cạnh tranh thích hợp.
- Tích hợp sớm với cơ sở dữ liệu và giao diện thật.
- Chạy pipeline khi có thay đổi.
- Dùng môi trường phù hợp để người dùng đánh giá luồng đăng ký.
- Quan sát các lỗi từ hệ thống và phản hồi của bộ phận hỗ trợ.

Một cuộc thử nghiệm cho thấy người học ít quan tâm lịch tháng và muốn biết **chắc chắn còn chỗ** hơn là giao diện phong phú. Product Owner có thể điều chỉnh thứ tự backlog dựa trên bằng chứng ấy.

### 14.4. Can đảm trước lỗi ở chỗ cuối cùng

Trong kiểm thử, nhóm thấy hai yêu cầu đồng thời có thể xác nhận một chỗ. Dù gần mốc demo, Developers nêu rủi ro và yêu cầu không đánh dấu Done khi chưa đáp ứng tiêu chí. Nhóm xem lại thiết kế xử lý cạnh tranh, sửa có kiểm chứng và đề xuất dời tính năng nhắc lịch nếu cần.

Đây là **can đảm được hỗ trợ bởi phản hồi**, không phải từ chối hợp tác hoặc bảo vệ một quan điểm cá nhân.

### 14.5. Tôn trọng trong phối hợp

Kỹ sư mới phát hiện lỗi nhưng chưa biết cách xử lý. Thành viên giàu kinh nghiệm chọn pairing để cùng hiểu vấn đề, tách test tái hiện và điều tra nguyên nhân. Trong review, nhóm tập trung vào dữ liệu và quy tắc, không đánh giá năng lực người đã viết đoạn mã.

Khi nhóm phải làm thêm giờ nhiều ngày, mọi người nêu giới hạn thực tế và thương lượng phạm vi với Product Owner thay vì mặc định “thêm giờ là cam kết Agile”.

### 14.6. Kết quả mong muốn

Một vòng XP thành công trong tình huống này không được đo bằng **bao nhiêu giờ pairing** hoặc **bao nhiêu test được viết**, mà bằng việc:

- Increment thực sự đáp ứng hành vi đã thống nhất và chất lượng cần thiết.
- Người học đăng ký thành công, trạng thái rõ, ít cần hỗ trợ.
- Nhóm phát hiện lỗi sớm và sửa mà không phá những chức năng cũ.
- Mỗi thành viên hiểu hệ thống tốt hơn, phụ thuộc cá nhân giảm.
- Backlog thay đổi theo phản hồi và mục tiêu sản phẩm.

## 15. XP trong nhóm áp dụng Scrum hoặc Kanban

XP, Scrum và Kanban giải quyết những góc nhìn bổ sung nhau, nhưng **không phải các thuật ngữ đồng nghĩa**.

| Cách tiếp cận | Trọng tâm | Cách liên hệ với giá trị XP |
| --- | --- | --- |
| **Scrum** | Khung thực nghiệm với Product Goal, Sprint Goal, các artifact, event và accountability | XP giúp Developers tạo Increment đạt DoD qua test, tích hợp, cải thiện thiết kế và cộng tác |
| **Kanban** | Hiển thị và quản lý dòng công việc, WIP, cycle time, throughput, chính sách kéo việc | XP giúp giảm lỗi/làm lại, chia lát cắt nhỏ và giao tiếp khi hạng mục bị tắc |
| **XP** | Các giá trị và thực hành cộng tác/kỹ thuật để phát triển phần mềm thích ứng | Giao tiếp, đơn giản, phản hồi, can đảm và tôn trọng định hướng cách làm hằng ngày |
| **Product discovery** | Hiểu vấn đề, thử giả thuyết, chọn giá trị | Phản hồi và giao tiếp XP giúp không xây giải pháp thiếu bằng chứng |

### 15.1. Khi Scrum Team sử dụng XP

Ví dụ Sprint Goal là **“Học viên đăng ký được workshop còn chỗ một cách đáng tin cậy”**. Product Owner làm rõ giá trị và thứ tự Product Backlog. Developers tự quản kế hoạch tạo Increment; Scrum Master giúp vận dụng Scrum hiệu quả và tháo gỡ trở ngại.

XP có thể bổ trợ bằng:

1. Cùng Product Owner làm rõ ví dụ chấp nhận.
2. TDD và kiểm thử tích hợp cho quy tắc đăng ký.
3. Pair programming khi xử lý logic cạnh tranh phức tạp.
4. Tích hợp liên tục và refactoring nhỏ.
5. Giữ phần mềm đạt DoD thay vì hoãn kiểm thử sang Sprint sau.

**Áp dụng XP không làm thay đổi thẩm quyền Product Owner đối với Product Backlog hay quyền tự quản của Developers trong Sprint.** Nó giúp nhóm thực thi mục tiêu một cách đáng tin cậy hơn.

### 15.2. Khi nhóm theo Kanban sử dụng XP

Một bảng Kanban cho thấy “Chờ kiểm thử” ngày càng phình ra. Nhóm có thể dùng:

- Phản hồi XP để đưa kiểm thử đến sớm hơn trong lát cắt.
- TDD hoặc kiểm thử tự động để giảm vòng làm lại.
- Pairing và chia sẻ kiến thức khi chỉ một người có thể giải quyết lỗi.
- Thiết kế đơn giản để hạn chế khối lượng thay đổi cần kiểm chứng.
- Nhịp phát hành nhỏ để quan sát người dùng sớm.

Nhưng **Kanban không tự làm mọi vấn đề kỹ thuật biến mất**; XP giúp cải thiện năng lực tạo phần mềm đúng đắn bên trong dòng chảy.

## 16. Các hiểu lầm thường gặp về năm giá trị XP

| Hiểu lầm | Vì sao gây hại | Điều cần hiểu |
| --- | --- | --- |
| “Communication nghĩa là họp càng nhiều càng tốt” | Tăng thời gian chờ, giảm tập trung | Giao tiếp đúng người, đúng mục đích, tạo hiểu biết và quyết định |
| “XP không cần viết tài liệu” | Mất khả năng truy vết, người mới khó hiểu | Tài liệu vừa đủ là công cụ giao tiếp khi thực sự hữu ích |
| “Simplicity nghĩa là ít code và ít test” | Tăng lỗi và khó thay đổi | Đơn giản là đáp ứng đúng nhu cầu hiện tại với chất lượng |
| “YAGNI nghĩa là bỏ mọi kiểm soát bảo mật” | Rủi ro người dùng nghiêm trọng | Điều kiện an toàn đã biết là một phần nhu cầu hiện tại |
| “Feedback chỉ là chạy unit test” | Không biết giải pháp có giá trị người dùng | Cần phản hồi nghiệp vụ, tích hợp, vận hành và người dùng |
| “Pipeline xanh thì tính năng chắc chắn đúng” | Test có thể thiếu tình huống, môi trường khác nhau | Test là bằng chứng trong phạm vi kiểm chứng, không phải bảo đảm tuyệt đối |
| “Courage nghĩa là thích gì sửa nấy” | Thay đổi lớn, thiếu kiểm soát, dễ gây sự cố | Can đảm đi cùng kiểm thử, phương án và trách nhiệm |
| “Dám tranh luận nghĩa là công kích mạnh” | Người khác ngại nêu rủi ro | Thẳng thắn về sự thật, tôn trọng con người |
| “Respect nghĩa là không được phản biện” | Giữ quyết định sai vì ngại mất lòng | Phản biện bằng chứng và trao đổi trực tiếp vẫn là tôn trọng |
| “Pair programming là hai người làm việc của một người nên luôn lãng phí” | Bỏ qua lợi ích giảm lỗi, học chung và phản hồi | Đánh giá tổng chi phí làm lại/chuyển giao và loại công việc |
| “Pair programming phải áp 100% thời gian” | Có thể tạo quá tải hoặc không phù hợp từng nhiệm vụ | Chọn cách dùng dựa trên mục tiêu và bằng chứng |
| “TDD viết test xong thì khỏi test hệ thống” | Bỏ sót tích hợp, bảo mật, hiệu năng | Cần kết hợp kiểm thử theo rủi ro |
| “CI nghĩa là tự động deploy production ngay” | Hiểu sai ranh giới kiểm soát phát hành | Tích hợp và xác minh liên tục khác với chính sách phát hành |
| “Refactoring là viết lại mọi thứ cho đẹp” | Đầu tư lớn, khó kiểm chứng | Cải thiện cấu trúc từng bước với test bảo vệ hành vi |
| “Sustainable pace nghĩa là không có trách nhiệm với deadline” | Tạo xung đột giả giữa chất lượng và cam kết | Lập kế hoạch thực tế, nêu rủi ro sớm và xử lý việc khẩn có trách nhiệm |
| “Cứ áp dụng đủ tên thực hành là đã có giá trị XP” | Nghi thức không tạo cải thiện | Kiểm tra kết quả, phản hồi, chất lượng và hợp tác |

## 17. Đo xem các giá trị XP có thực sự được vận dụng không

Giá trị không thể đo trực tiếp bằng một KPI đơn giản. Nên kết hợp quan sát định tính với các tín hiệu chất lượng và dòng công việc, **tránh biến thước đo thành chỉ tiêu gây hành vi sai**.

| Góc nhìn | Tín hiệu có thể dùng | Cách đọc cẩn trọng |
| --- | --- | --- |
| **Giao tiếp** | Số vòng làm rõ muộn, hiểu lầm yêu cầu, phụ thuộc phát hiện trễ, chất lượng trao đổi qua ví dụ | Ít họp chưa chắc giao tiếp tốt; nhiều câu hỏi có thể là dấu hiệu học hỏi tích cực |
| **Đơn giản** | Độ dễ hiểu của lát cắt, chi phí thay đổi, lượng chức năng bỏ vì thiếu giá trị, sự cố do cấu trúc phức tạp | Không dùng số dòng code thấp làm mục tiêu tuyệt đối |
| **Phản hồi** | Thời gian nhận tín hiệu từ CI, vòng phát hiện lỗi, phản hồi người dùng được đưa vào backlog | Test chạy nhanh nhưng thường bị bỏ qua thì chưa có hiệu quả |
| **Can đảm** | Rủi ro được báo sớm, quyết định dừng việc sai, refactor có kiểm chứng | Không đo bằng số lần tranh cãi hoặc số lần “phá quy trình” |
| **Tôn trọng** | Khả năng trao đổi an toàn, mức chia sẻ kiến thức, chất lượng code review, mức quá tải | Khảo sát cần bảo mật phù hợp; không ép mọi người công khai cảm xúc |
| **Kết quả chung** | Lead/cycle time, lỗi sau phát hành, làm lại, độ tin cậy, kết quả người dùng | Không quy mọi biến động cho một thực hành XP; xem bối cảnh và chất lượng dữ liệu |

### 17.1. Một trường hợp chỉ số tăng nhưng XP vận dụng kém

Giả sử nhóm tăng số story Done mỗi Sprint, nhưng lỗi sau phát hành cũng tăng và thành viên thường phải làm thêm giờ. Không thể kết luận XP được cải thiện vì throughput cao hơn. Có thể nhóm **đang bỏ chất lượng và phá nhịp làm việc bền vững**, dẫn tới làm lại trong tương lai.

Ngược lại, nhóm hoàn tất ít story hơn trong một giai đoạn nhưng loại bỏ được lỗi dữ liệu nghiêm trọng, giảm chờ tích hợp và có thử nghiệm xác nhận giá trị người dùng có thể đã tạo ra **kết quả tích cực hơn**.

### 17.2. Quan sát hệ thống thay vì chấm điểm cá nhân

Đếm **số test mỗi lập trình viên**, **số giờ pairing**, **số commit** hoặc **số lần góp ý PR** để xếp hạng cá nhân dễ làm biến dạng hành vi. XP hướng tới năng lực **cả nhóm** tạo phần mềm có chất lượng, phản hồi nhanh và hợp tác bền vững.

## 18. Thử nghiệm nhỏ để đưa năm giá trị vào công việc hằng ngày

Nếu nhóm muốn áp dụng XP, không nhất thiết triển khai một cuộc “chuyển đổi văn hóa” lớn bằng khẩu hiệu. Hãy chọn **một vấn đề thực tế**, đưa ra giả thuyết và thử hành động nhỏ có thể quan sát.

### Ví dụ thử nghiệm hai Sprint

**Vấn đề:** Code review của nhóm thường phát hiện sai quy tắc nghiệp vụ rất muộn, làm các PBI phải sửa nhiều vòng.

**Giả thuyết:** Nếu nhóm dùng cuộc trao đổi ba góc nhìn trước khi code, viết ví dụ kiểm thử chính và pairing ngắn ở các luồng rủi ro, số lần làm lại sẽ giảm và cycle time ổn định hơn.

| Thời điểm | Hoạt động | Giá trị được thực hành |
| --- | --- | --- |
| Trước Sprint | Chọn một hoặc hai PBI có rủi ro vừa phải; xác định baseline về vòng review, thời gian chờ, lỗi | Giao tiếp và phản hồi |
| Đầu Sprint 1 | Product Owner, Developers và kiểm thử cùng viết vài ví dụ chấp nhận | Giao tiếp, tôn trọng |
| Trong Sprint 1 | Viết test cho quy tắc, phát triển lát cắt nhỏ, tích hợp liên tục | Đơn giản, phản hồi |
| Khi gặp phần khó | Pair ngắn, nêu giả định và giới hạn; phản biện giải pháp bằng test | Can đảm, tôn trọng |
| Cuối Sprint 1 | Xem Increment, lỗi, thời gian chờ, phản hồi của người dùng | Phản hồi |
| Sprint 2 | Giữ/điều chỉnh cách làm theo dữ liệu, mở rộng có chọn lọc | Cả năm giá trị |

### 18.1. Tiêu chí kiểm tra thử nghiệm

1. Người tham gia có hiểu cùng hành vi và rủi ro trước khi triển khai hơn không?
2. Số vòng review do hiểu sai nghiệp vụ có thay đổi?
3. Thời gian từ bắt đầu làm tới Increment đạt DoD có ổn định hơn?
4. Lỗi hồi quy hoặc lỗi vận hành có tăng không?
5. Thành viên có thể nêu bất đồng và yêu cầu hỗ trợ một cách tôn trọng?
6. Người dùng có nhận được phần mềm đúng nhu cầu sớm hơn?

**Không nên kết luận từ hai Sprint rằng một thực hành “luôn hiệu quả”.** Quan sát đủ bối cảnh, ghi hạn chế của dữ liệu và tiếp tục thử khi cần.

## 19. Khi nhóm không thể áp dụng tất cả thực hành XP ngay

Một số nhóm có hệ thống cũ, kiểm thử thiếu, môi trường tích hợp chậm, nhóm phân tán hoặc chịu ràng buộc kiểm soát thay đổi. Năm giá trị XP vẫn giúp **chọn thứ tự cải tiến**, ngay cả khi chưa thể áp dụng đầy đủ.

| Ràng buộc | Hành động nhỏ phù hợp | Điều phải tránh |
| --- | --- | --- |
| Không có mạng lưới unit test đáng tin | Bắt đầu với test cho phần thay đổi có rủi ro, cải thiện khả năng chạy tự động | Refactor lớn mà không có cách kiểm chứng hành vi |
| CI chạy rất lâu và không ổn định | Phân tích nguyên nhân, cải thiện bài test và dữ liệu thử, ưu tiên bước kiểm tra nhanh có ý nghĩa | Xóa test quan trọng chỉ để pipeline xanh |
| Product Owner khó tiếp cận | Chuẩn bị câu hỏi và ví dụ rõ, tạo nhịp trao đổi ngắn với người có thẩm quyền nghiệp vụ | Developers tự đoán toàn bộ hành vi rồi gọi đó là linh hoạt |
| Nhóm ở nhiều múi giờ | Viết quyết định, test và ví dụ dễ truy vết, hẹn giờ trao đổi trực tiếp cho điểm khó | Họp ngoài giờ thường xuyên với một nhóm thành viên |
| Hệ thống có nhiều quy định bảo mật | Cùng chuyên gia xác định ranh giới, đưa kiểm soát vào lát cắt từ sớm | Bỏ phê duyệt hoặc kiểm tra bắt buộc nhân danh “small release” |
| Một chuyên gia giữ phần lớn kiến thức | Pairing/mentoring có kế hoạch, luân chuyển review hợp lý | Ép người thiếu kỹ năng duyệt thay đổi rủi ro cao |
| Nhóm luôn bị ngắt bởi sự cố | Làm rõ chính sách xử lý khẩn, cải thiện quan sát hệ thống và chất lượng hồi quy | Lấy làm thêm giờ liên tục làm cách tăng năng lực |

**Một cải tiến XP cần phù hợp cả kỹ thuật và con người.** Áp dụng ngay hàng loạt thực hành mà không hiểu vấn đề, không đủ công cụ hoặc không có khả năng quan sát có thể tạo thêm gánh nặng.

## 20. Checklist tự đánh giá năm giá trị trong một hạng mục

Mẫu sau có thể dùng trong refinement, review cách làm hoặc retrospective. Đây là **công cụ học tập**, không phải yêu cầu chính thức của XP hay một cổng phê duyệt bổ sung.

~~~text
HẠNG MỤC:
KẾT QUẢ NGƯỜI DÙNG MONG MUỐN:
RỦI RO CHÍNH:

GIAO TIẾP
[ ] Người hiểu nghiệp vụ và người triển khai có cùng ví dụ hành vi
[ ] Quyết định/phụ thuộc quan trọng có người chịu trách nhiệm rõ
[ ] Khi có thay đổi, người liên quan biết tác động và quyết định mới

ĐƠN GIẢN
[ ] Lát cắt đủ nhỏ để giao và kiểm chứng sớm
[ ] Không xây tính năng hoặc abstraction chưa có nhu cầu rõ
[ ] Các yêu cầu chất lượng, bảo mật, dữ liệu đã biết vẫn được đáp ứng

PHẢN HỒI
[ ] Có test phù hợp cho hành vi/rủi ro chính
[ ] Tích hợp và kiểm chứng sớm, pipeline có người xử lý tín hiệu
[ ] Có cách thu phản hồi người dùng/vận hành sau khi giao

CAN ĐẢM
[ ] Rủi ro hoặc giả định sai được nêu công khai, không che tiến độ
[ ] Có phương án sửa hướng đi/refactor được kiểm chứng
[ ] Không đánh dấu Done khi chưa đạt tiêu chuẩn hoàn thành

TÔN TRỌNG
[ ] Bất đồng được trao đổi bằng bằng chứng, không công kích cá nhân
[ ] Có chia sẻ kiến thức và phối hợp phù hợp năng lực
[ ] Phạm vi và nhịp làm việc được lựa chọn có trách nhiệm

SAU KHI GIAO
- Điều thực tế khác giả định:
- Bằng chứng nhận được:
- Quyết định giữ / sửa / bỏ:
- Cải tiến nhỏ cần thử lần tới:
~~~

Nếu checklist quá dài so với một hạng mục nhỏ, chỉ chọn những câu hỏi **có tác dụng quyết định thực tế**. Mục tiêu là sống theo giá trị, không phải tăng số trường bắt buộc trên công cụ.

## 21. Bài tập tình huống: năm giá trị XP được thử thách

**Bối cảnh:** Một nhóm phát triển nền tảng học tập cần giao tính năng “Học viên đăng ký và hủy workshop”. Nhóm đang trong Sprint thứ hai của sản phẩm mới.

Các sự kiện xảy ra:

1. Product Owner đề nghị làm một bộ quy tắc đăng ký tổng quát để “sau này tất cả loại sự kiện đều dùng được”, dù hiện tại chỉ hỗ trợ workshop miễn phí.
2. Một Developer nói rằng quy tắc hủy chưa rõ nhưng ngại hỏi vì sợ “làm chậm cả nhóm”.
3. Test tích hợp phát hiện trường hợp hai người đăng ký chỗ cuối bị xác nhận trùng.
4. Một reviewer để lại bình luận: “Code của bạn quá tệ, viết lại từ đầu đi”.
5. Quản lý muốn bỏ kiểm thử cạnh tranh để kịp buổi trình diễn.
6. Hai thành viên liên tục làm thêm giờ; một người mới chưa hiểu khu vực xử lý đăng ký.
7. Sau khi phát hành lát cắt nhỏ trên môi trường được phép thử, học viên cho biết họ cần xem trạng thái rõ ràng hơn là lịch tháng.

### Câu hỏi thực hành

1. Hãy chỉ ra **giá trị XP nào đang bị thử thách** ở từng sự kiện. Có tình huống liên quan nhiều hơn một giá trị không?
2. Với đề xuất bộ quy tắc tổng quát, bạn sẽ xác minh nhu cầu và lựa chọn thiết kế vừa đủ ra sao?
3. Với Developer ngại hỏi, nhóm cần cải thiện cách giao tiếp và tôn trọng bằng hành động gì?
4. Test tích hợp thất bại là loại phản hồi nào? Vì sao cần phản ứng trước khi coi PBI đạt Done?
5. Làm sao phản biện bình luận review vừa **can đảm** vừa **tôn trọng**?
6. Có thể thương lượng phạm vi hoặc mốc nào để giữ chất lượng thay vì bỏ kiểm thử?
7. Bạn sẽ thử pairing và chia sẻ tri thức thế nào để giảm phụ thuộc nhưng không làm người mới quá tải?
8. Phản hồi thích trạng thái rõ hơn lịch tháng sẽ tác động ra sao tới Product Backlog và kế hoạch Increment tiếp theo?
9. Đề xuất **hai chỉ báo** cho thấy thử nghiệm cải tiến XP có tác dụng, và **một chỉ báo** có thể phản ánh tác dụng phụ.

### Gợi ý hướng giải

**Sự kiện 1:** Giá trị Simplicity khuyên không xây khả năng tổng quát chưa có bằng chứng; Communication và Feedback giúp kiểm tra nhu cầu tương lai. Cần giữ khả năng thay đổi an toàn, không nhất thiết dự đoán trước mọi trường hợp.

**Sự kiện 2:** Communication, Courage và Respect cùng xuất hiện. Nhóm cần khuyến khích hỏi sớm, làm rõ bằng ví dụ, không đánh giá người đặt câu hỏi là kém năng lực.

**Sự kiện 3:** Feedback cho thấy hành vi quan trọng chưa đúng. Courage yêu cầu công khai rủi ro; Simplicity thúc đẩy giải pháp phù hợp, kiểm thử đủ mức; Respect bảo vệ dữ liệu và niềm tin người dùng.

**Sự kiện 4:** Người review nên chỉ ra hành vi có rủi ro, lý do, ví dụ và phương án; không tấn công người viết mã. Có thể phản biện mạnh mẽ về kỹ thuật mà vẫn tôn trọng cá nhân.

**Sự kiện 5:** Không bỏ điều kiện tính đúng đắn đã biết. Product Owner và Developers có thể chọn lát cắt giá trị nhỏ hơn hoặc thay đổi mốc minh bạch, tùy cam kết và thẩm quyền.

**Sự kiện 6:** Pairing ngắn ở phần khó, chuyển giao kiến thức và cải tiến cách phân bổ công việc có thể tốt hơn yêu cầu làm thêm giờ kéo dài. Hỗ trợ người mới theo mức phù hợp.

**Sự kiện 7:** Nhóm đưa bằng chứng vào ưu tiên backlog, xem xét trạng thái rõ ràng trước lịch tháng; không giữ giải pháp cũ chỉ vì đã làm nhiều.

**Chỉ báo:** Có thể xem số vòng làm lại do hiểu sai yêu cầu, thời gian từ test thất bại tới sửa, lỗi sau phát hành, cycle time của lát cắt và phản hồi người dùng. Tác dụng phụ có thể là quá nhiều cuộc họp hoặc áp lực pairing gây giảm tập trung; cần đo trong bối cảnh, không đặt chỉ tiêu số lượng phi thực tế.

## 22. Ghi nhớ và tự kiểm tra

**Năm giá trị XP không tồn tại tách biệt.** Communication tạo hiểu biết chung; Simplicity giúp xây điều cần thiết mà vẫn có khả năng thay đổi; Feedback giúp phát hiện sớm điều đúng/sai; Courage giúp nhóm dám phản ứng với sự thật và đổi hướng; Respect tạo môi trường để mọi người cùng học hỏi, bảo vệ người dùng và duy trì chất lượng.

Những giá trị ấy được thể hiện qua thực hành như **TDD, pair programming, refactoring, CI, small releases, customer collaboration, collective code ownership và sustainable pace**. Mục tiêu cuối không phải “áp dụng đủ kỹ thuật XP”, mà là **giao Increment có giá trị, đáng tin cậy và dễ thay đổi qua phản hồi sớm**.

Tự kiểm tra:

1. Vì sao XP cần các giá trị nếu đã có TDD và CI?
2. Giao tiếp hiệu quả khác với tổ chức nhiều cuộc họp như thế nào?
3. Vì sao một user story thường cần ví dụ hành vi và đối thoại để được hiểu đầy đủ?
4. YAGNI và thiết kế đơn giản khác với bỏ kiểm thử hoặc bỏ yêu cầu bảo mật ở đâu?
5. Hãy nêu ba nguồn phản hồi khác nhau và giới hạn của mỗi nguồn.
6. TDD Red – Green – Refactor hỗ trợ Feedback, Simplicity và Courage như thế nào?
7. Một unit test xanh có đủ để chứng minh tính năng tạo giá trị người dùng không? Vì sao?
8. Phân biệt can đảm thay đổi thiết kế với hành vi liều lĩnh khi refactor.
9. Tôn trọng thể hiện thế nào khi một reviewer phát hiện lỗi nghiêm trọng?
10. Vì sao làm thêm giờ liên tục có thể xung đột với Respect và khả năng giao hàng bền vững?
11. Hãy mô tả một tình huống các giá trị Simplicity và Feedback phải cân bằng với chất lượng.
12. XP có thể bổ trợ Scrum và Kanban như thế nào mà không thay thế trách nhiệm của Product Owner và Developers?

Khi đối diện một lựa chọn khó, hãy hỏi: **“Chúng ta đã hiểu nhau chưa, giải pháp này có thực sự cần thiết và đủ đơn giản không, bằng chứng nào sẽ cho biết đúng hay sai, có sự thật nào cần can đảm nói ra, và quyết định này có tôn trọng người dùng cùng đồng đội không?”** Năm câu hỏi đó biến những giá trị XP từ khẩu hiệu thành cách phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục.

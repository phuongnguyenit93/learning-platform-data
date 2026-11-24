# Phân biệt nguyên mẫu, sản phẩm khả dụng tối thiểu và phần tăng trưởng có thể sử dụng

Một nhóm đang xây nền tảng học trực tuyến và muốn kiểm tra xem người học có cần tính năng “tiếp tục bài học đang xem” hay không. Ba đề xuất được đưa ra:

- Người thiết kế tạo màn hình có thể bấm thử để quan sát người học có tìm thấy nút “Học tiếp” không.
- Người quản lý sản phẩm đề xuất mở một khóa học thật cho một nhóm nhỏ, đủ để kiểm tra người học có quay lại và hoàn tất bài không.
- Nhóm phát triển hoàn thiện chức năng lưu tiến độ, tích hợp với hệ thống hiện có và đáp ứng tiêu chuẩn chất lượng trước khi có thể đưa vào sử dụng.

Ba đề xuất có liên hệ chặt chẽ nhưng **không có cùng mục đích**. Đề xuất đầu nghiêng về **nguyên mẫu (prototype)**, đề xuất thứ hai mô tả một phương án **sản phẩm khả dụng tối thiểu (minimum viable product – MVP)**, còn đề xuất thứ ba mô tả một **phần tăng trưởng có thể sử dụng (usable increment)**.

Hiểu đúng khác biệt giúp nhóm tránh hai sai lầm phổ biến: đầu tư quá nhiều trước khi biết người dùng có cần giải pháp, hoặc đưa một bản thử nghiệm chưa đạt chất lượng ra sử dụng chỉ để gọi nó là “MVP”.

Bài học nằm trong chương **Sản phẩm và giá trị** của module **AGILE_DEVELOPMENT**. Agile nhấn mạnh phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. Vì thế, nguyên mẫu, MVP và phần tăng trưởng là những cách nhìn bổ sung để nhóm quyết định **cần học gì, cần chứng minh giá trị gì và có thể giao phần mềm nào**. Các thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc đều có thể hỗ trợ quyết định đó.

Sau bài này, bạn có thể:

1. Giải thích mục đích, đối tượng, mức độ hoàn thiện và bằng chứng mà prototype, MVP và increment tạo ra.
2. Phân biệt **khả năng thử ý tưởng**, **khả năng kiểm chứng giá trị** và **khả năng đưa phần mềm vào sử dụng**.
3. Chọn hình thức phù hợp dựa trên rủi ro chưa được giải đáp và chi phí kiểm chứng.
4. Viết một user story, tiêu chí chấp nhận và kế hoạch thu phản hồi cho một phần gia tăng nhỏ.
5. Nhận diện các ngộ nhận như “MVP là sản phẩm nhiều lỗi”, “prototype luôn phải viết code” hoặc “increment chỉ tồn tại khi đã phát hành”.

## 1. Ba câu hỏi dẫn đến ba khái niệm

Một cách nhanh để phân biệt là bắt đầu từ **câu hỏi cần trả lời**:

| Khái niệm | Câu hỏi chính | Kết quả mong muốn |
| --- | --- | --- |
| **Nguyên mẫu (prototype)** | “Ý tưởng hoặc cách tương tác này có dễ hiểu, có khả thi hoặc có giải quyết đúng vấn đề như dự đoán không?” | Phát hiện sai giả định sớm, học về giải pháp trước khi đầu tư đầy đủ. |
| **MVP (minimum viable product)** | “Một phiên bản nhỏ nhất đủ hữu ích và đáng tin cậy có tạo ra hành vi hoặc kết quả giá trị với người dùng mục tiêu không?” | Bằng chứng về giá trị, nhu cầu, hành vi hoặc tính khả thi của hướng sản phẩm trong bối cảnh thực. |
| **Phần tăng trưởng có thể sử dụng (usable increment)** | “Phần chức năng mới đã được tích hợp, đáp ứng tiêu chuẩn hoàn tất và có thể sử dụng cùng sản phẩm hiện tại chưa?” | Một bước tiến sản phẩm đạt chất lượng, có thể kiểm tra hoặc phát hành tùy quyết định. |

Không nên xếp ba khái niệm thành ba “cấp độ chất lượng” cứng nhắc. Một prototype có thể được thiết kế rất chỉn chu nhưng không xử lý dữ liệu thật. Một MVP có thể phục vụ số người dùng nhỏ nhưng phải đủ an toàn cho mục đích thử nghiệm. Một increment có thể được xây hoàn chỉnh về kỹ thuật nhưng chưa chứng minh giả thuyết kinh doanh nào.

**Điểm mấu chốt:** Prototype và MVP thường nói về **mục đích học hỏi và kiểm chứng**, còn increment trong Scrum nhấn mạnh **trạng thái phần mềm đã hoàn tất, tích hợp và sẵn sàng sử dụng**.

### Một bảng so sánh toàn diện

| Tiêu chí | Prototype | MVP | Usable increment |
| --- | --- | --- | --- |
| Mục đích ưu tiên | Khám phá ý tưởng, thiết kế, thao tác hoặc tính khả thi. | Kiểm tra giả thuyết giá trị với người dùng thật, qua một sản phẩm hay hình thức cung cấp có thể sử dụng thực tế. | Tạo bước tiến sản phẩm đạt tiêu chuẩn hoàn tất. |
| Câu hỏi trọng tâm | “Có nên và có thể làm như thế này không?” | “Người dùng có nhận giá trị đủ để dùng hoặc tiếp tục dùng không?” | “Phần này có hoàn thành đúng tiêu chuẩn và tích hợp được không?” |
| Đối tượng thử | Người dùng đại diện, chuyên gia, thành viên nhóm; tùy giả thuyết. | Người dùng mục tiêu trong điều kiện đủ thực để quan sát hành vi có ý nghĩa. | Nhóm phát triển, bên liên quan và có thể cả người dùng khi được đưa vào sử dụng. |
| Mức hoàn thiện | Biến thiên từ bản phác thảo đến mô hình chạy được. | Tối thiểu về **phạm vi**, đủ khả dụng và đáng tin cậy cho tình huống thử nghiệm. | Đáp ứng Definition of Done hay tiêu chuẩn hoàn tất tương ứng. |
| Hệ thống và dữ liệu thật | Có thể mô phỏng; phải nói rõ giới hạn. | Thường cần trải nghiệm thật hoặc cơ chế cung cấp giá trị thật; có thể kèm thao tác thủ công có kiểm soát. | Phần thay đổi đã tích hợp và được kiểm tra theo chuẩn chất lượng sản phẩm. |
| Cách lấy phản hồi | Quan sát tác vụ, phỏng vấn, thử tương tác, thử kỹ thuật. | Quan sát sử dụng, duy trì sử dụng, kết quả người dùng và tín hiệu nhu cầu. | Kiểm thử, kiểm tra khả dụng, vận hành; phản hồi thực tế nếu phát hành. |
| Kết quả có thể là | Sửa thiết kế, đổi giả thuyết, bỏ ý tưởng, làm thử nghiệm khác. | Tiếp tục đầu tư, điều chỉnh định hướng, thay nhóm khách hàng mục tiêu hoặc dừng. | Tích lũy thành sản phẩm hoàn chỉnh hơn; có thể quyết định phát hành. |
| Phát hành rộng | Không phải mục tiêu mặc định. | Không bắt buộc phát hành rộng; thường giới hạn để học. | Có thể phát hành, nhưng **không phải cứ Done là đã phát hành**. |
| Sai lầm thường gặp | Hiểu bản minh họa là cam kết kỹ thuật đã sẵn sàng. | Gọi một tính năng lỗi hoặc chưa an toàn là “tối thiểu”. | Coi “code xong” là Increment khi chưa tích hợp hoặc chưa đạt DoD. |

Các cột trên mô tả **mục đích thường gặp**, không phải quy tắc cấm kết hợp. Một thử nghiệm MVP có thể bắt đầu bằng nguyên mẫu, hoặc được hiện thực hóa bằng một hay nhiều increment đáp ứng tiêu chuẩn hoàn tất.

## 2. Nguyên mẫu (prototype): làm rõ ý tưởng trước khi xây đầy đủ

**Nguyên mẫu** là một hiện vật giúp những người liên quan hình dung, tương tác hoặc kiểm tra một giả thuyết về giải pháp. Nó có thể là tranh phác tay, wireframe, màn hình tương tác, mô phỏng luồng nghiệp vụ, mô hình kỹ thuật hoặc bản code thí nghiệm.

Nguyên mẫu có hai lợi thế:

1. **Chi phí thay đổi thấp:** một bố cục có thể sửa sau vài phút thay vì phải cập nhật giao diện, API, cơ sở dữ liệu và bài kiểm thử production.
2. **Làm rõ điều khó nói bằng lời:** người dùng có thể thử thao tác, chỉ ra họ kỳ vọng gì và nhóm có thể quan sát chỗ họ nhầm lẫn.

### 2.1. Mức độ chi tiết của nguyên mẫu

| Hình thức | Ví dụ | Nên dùng khi |
| --- | --- | --- |
| **Độ trung thực thấp (low fidelity)** | Sơ đồ luồng, bản vẽ giấy, wireframe đen trắng. | Chưa rõ luồng thao tác, khái niệm, nhãn hoặc thứ tự bước. |
| **Độ trung thực trung bình** | Bộ màn hình liên kết có thể bấm; dữ liệu ví dụ rõ ràng. | Muốn kiểm tra điều hướng, nội dung thông báo và quy trình. |
| **Độ trung thực cao (high fidelity)** | Bản mô phỏng gần giống sản phẩm, có chuyển trạng thái và nội dung thực tế hơn. | Muốn quan sát trải nghiệm cụ thể trước khi cam kết triển khai. |
| **Nguyên mẫu kỹ thuật** | Một đoạn code thử tích hợp API, mô hình đồng bộ hoặc xử lý thuật toán. | Chưa biết giải pháp kỹ thuật có khả thi, đủ nhanh hoặc tương thích không. |

*Độ trung thực* mô tả mức độ giống sản phẩm kỳ vọng, **không** nói trực tiếp về chất lượng sản xuất. Một bản mẫu nhìn rất thật vẫn có thể không có lưu trữ, xác thực, phân quyền, giám sát hoặc xử lý lỗi.

### 2.2. Cách tổ chức thử nguyên mẫu

Giả sử nhóm muốn thiết kế chức năng “tiếp tục học”. Họ có hai thiết kế: nút “Học tiếp” ở đầu trang chủ và mục “Tiếp tục” nằm trong danh sách khóa học.

Nhóm mời một số người phù hợp với nhóm người học mục tiêu và giao nhiệm vụ:

> “Bạn đã xem dở một video hôm qua. Hãy mở lại đúng bài để học tiếp.”

Người quan sát ghi nhận:

- Người học có tìm ra cách bắt đầu tác vụ không?
- Họ chọn mục nào trước, có bị hiểu nhầm nội dung nhãn không?
- Họ có hiểu điều gì sẽ xảy ra khi bấm “Học tiếp” không?
- Có điểm nào khiến họ cần hỗ trợ hoặc dừng lại?

Sau đó nhóm hỏi vì sao người học chọn như vậy, cải tiến bản mẫu rồi kiểm tra lại. Không nên ngay lập tức suy từ “ba trong năm người thích A” thành kết luận chắc chắn cho toàn bộ người dùng. Mẫu nhỏ rất hữu ích để **phát hiện vấn đề khả dụng**, nhưng thường không đủ để ước lượng chính xác mức độ phổ biến.

### 2.3. Nguyên mẫu không nhất thiết phải phát hành và không phải một Increment

Prototype không cần đáp ứng mọi điều kiện để trở thành sản phẩm vận hành. Điều cần làm rõ là **những gì nó có và chưa có**. Nếu dữ liệu chỉ là giả lập, hãy nói rõ. Nếu bấm “Thanh toán” chỉ chuyển màn hình mà không thực hiện giao dịch, không trình bày nó như giao dịch thật.

Nguyên mẫu có thể được bỏ sau khi đã học xong. Cũng có trường hợp một phần ý tưởng hoặc mã được tái sử dụng, nhưng chỉ nên đưa vào sản phẩm khi được đánh giá, tích hợp, kiểm thử và đáp ứng các yêu cầu chất lượng tương ứng.

**Phân biệt thêm:** *Proof of Concept (PoC)* thường tập trung vào câu hỏi **“một hướng kỹ thuật có làm được không?”**. PoC có thể là một dạng thử nghiệm hoặc nguyên mẫu kỹ thuật; trong khi nguyên mẫu giao diện tập trung vào cách người dùng hiểu và tương tác với giải pháp. Hai thuật ngữ có thể được các tổ chức dùng linh hoạt, nên cần xác định cụ thể giả thuyết đang thử.

## 3. MVP: phiên bản tối thiểu đủ để học về giá trị thật

**MVP – Minimum Viable Product**, thường dịch là **sản phẩm khả dụng tối thiểu**, là một cách tiếp cận tạo ra phiên bản hoặc trải nghiệm nhỏ nhất **đủ để kiểm tra giả thuyết quan trọng về giá trị sản phẩm bằng hành vi hoặc phản hồi có ý nghĩa của người dùng mục tiêu**.

MVP là thuật ngữ phổ biến trong phát triển sản phẩm và Lean Startup, không phải một loại hiện vật bắt buộc được Scrum định nghĩa. Cách diễn đạt khác nhau giữa tổ chức, nhưng mục tiêu chung là **học đủ sớm để giảm nguy cơ xây sản phẩm không ai cần**.

### 3.1. “Tối thiểu” là tối thiểu về phạm vi đầu tư

Một MVP tốt thường loại bỏ các chức năng chưa phục vụ giả thuyết cần kiểm tra. Nó không nhất thiết phải có giao diện hoàn hảo, hàng chục tùy chỉnh hay giải quyết mọi trường hợp ngoại lệ của sản phẩm tương lai.

Tuy nhiên, “tối thiểu” không đồng nghĩa:

- Bỏ qua bảo mật dữ liệu và quyền truy cập.
- Chấp nhận mất dữ liệu hoặc thu tiền sai mà không kiểm soát.
- Không nói rõ giới hạn của bản thử nghiệm.
- Công bố số liệu thành công không thể kiểm chứng.
- Đưa thử nghiệm gây rủi ro cho người dùng mà không cân nhắc biện pháp an toàn cần thiết.

**Viable** nên được hiểu trong **bối cảnh và đối tượng thử nghiệm**: sản phẩm đủ đáng tin cậy, đúng chức năng cốt lõi và an toàn để người dùng mục tiêu nhận giá trị thực trong phạm vi đã xác định.

### 3.2. Một MVP cần giả thuyết có thể bác bỏ

Ví dụ về giả thuyết chưa tốt:

> “Nếu làm nền tảng học trực tuyến, người dùng sẽ thích.”

Không rõ “thích” được quan sát thế nào, dành cho ai và trong điều kiện nào.

Ví dụ tốt hơn:

> “Trong nhóm người mới học Java, khi được cung cấp một lộ trình gồm ba bài nhỏ với bài tập và chức năng tiếp tục học, một tỷ lệ người học đủ lớn sẽ hoàn tất bài thứ hai trong tuần đầu để nhóm có cơ sở tiếp tục đầu tư.”

Cần đặt trước tiêu chí quyết định dựa trên bối cảnh thực tế, ví dụ:

- **Nhóm người dùng mục tiêu**: người mới học Java đã đăng ký thử chương trình.
- **Giá trị tối thiểu**: có thể bắt đầu, học, làm bài tập và tiếp tục tiến độ.
- **Tín hiệu**: số người kích hoạt học tập, số người hoàn thành bài hai, phản hồi về khó khăn.
- **Ngưỡng và thời gian**: do nhóm thống nhất dựa trên sản phẩm, mẫu dự kiến và chi phí thử nghiệm; không có một ngưỡng phần trăm “chuẩn MVP” cho mọi dự án.
- **Quyết định**: mở rộng, điều chỉnh giải pháp hoặc dừng nếu giả thuyết không được ủng hộ.

MVP không tự trả lời mọi câu hỏi về thị trường. Nó giảm bất định **đối với giả thuyết đã chọn**.

### 3.3. Những hình thức MVP thường gặp

| Hình thức | Cách hoạt động | Loại giả thuyết có thể học |
| --- | --- | --- |
| **Một luồng sản phẩm thật giới hạn** | Mở một chức năng hoàn chỉnh cho một nhóm người dùng nhỏ. | Người dùng có sử dụng, hoàn tất tác vụ và quay lại không? |
| **Concierge MVP** | Người trong nhóm thực hiện thủ công một phần dịch vụ, minh bạch với người dùng. | Nhu cầu có thật không; cách hỗ trợ nào đem lại giá trị? |
| **Wizard of Oz MVP** | Trải nghiệm mặt trước trông như được tự động hóa nhưng xử lý phía sau có người thực hiện, với kiểm soát phù hợp. | Người dùng có cần kết quả của dịch vụ trước khi đầu tư tự động hóa không? |
| **Thử nghiệm luồng đăng ký hoặc quan tâm** | Trình bày đề xuất giá trị và quan sát hành động quan tâm có thật; sản phẩm có thể chưa cung cấp đầy đủ. | Có tín hiệu ban đầu về nhu cầu hoặc thông điệp không? |

Một trang đăng ký quan tâm thường chỉ cho **tín hiệu nhu cầu ban đầu**; nó chưa chứng minh người dùng sẽ hài lòng, sẵn sàng trả tiền hay sử dụng lâu dài. Vì vậy, có nhóm gọi đây là *thử nghiệm khói (smoke test)* hoặc thử nghiệm tiền MVP. Khi dùng nhãn “MVP”, cần mô tả rõ sản phẩm hay trải nghiệm nào đã thực sự được cung cấp.

Với Concierge hoặc Wizard of Oz, nhóm không nên tạo kỳ vọng sai về khả năng, quy mô, an toàn hoặc cách dữ liệu được xử lý. Phần thủ công phải có năng lực thực hiện, giới hạn số lượng và các biện pháp bảo vệ phù hợp.

### 3.4. MVP có thể thay đổi hình dạng theo câu hỏi cần học

Để kiểm tra xem người học có muốn nhận nhắc nhở theo lịch hay không, nhóm có thể gửi nhắc nhở thủ công theo lịch đã được người học đồng ý. Để kiểm tra liệu người học có hoàn tất bài khi có video và bài tập ngắn, nhóm cần một luồng học thật có nội dung và theo dõi tiến độ. Hai giả thuyết khác nhau dẫn tới hai MVP rất khác nhau.

MVP tốt được xác định **bởi điều cần học**, không phải bởi một danh sách cố định gồm “đăng nhập + hai màn hình + một API”.

## 4. Phần tăng trưởng có thể sử dụng (usable increment): một bước tiến sản phẩm đạt chất lượng

**Increment** trong Scrum là một bước tiến cụ thể hướng tới **Product Goal**, bổ sung vào những increment trước đó, được kiểm tra để bảo đảm chúng phối hợp hoạt động. Increment phải **có thể sử dụng** (*usable*) và đáp ứng **Definition of Done (DoD)**.

Nếu một hạng mục chưa đáp ứng Definition of Done, nó chưa thể được coi là một phần của Increment theo nghĩa Scrum. **Nói “đã viết code xong” không đồng nghĩa với “đã hoàn tất một Increment”.**

### 4.1. Khả dụng và hoàn tất là điều kiện quan trọng

“Có thể sử dụng” không chỉ nói rằng giao diện mở được. Nó còn hàm ý phần gia tăng đã đáp ứng tiêu chuẩn chất lượng cần thiết và tương thích với sản phẩm hiện tại. Đối với một chức năng lưu tiến độ học, nhóm có thể cần:

- Lưu và đọc tiến độ đúng trong phạm vi hỗ trợ.
- Kiểm tra quyền truy cập: người học không xem hoặc sửa trái phép tiến độ người khác.
- Xử lý trường hợp chưa có tiến độ hoặc kết nối bị gián đoạn theo thỏa thuận.
- Kiểm thử hành vi quan trọng; có mức độ kiểm thử tự động phù hợp.
- Tích hợp với tính năng hiện có và kiểm tra không làm hỏng hành vi trước.
- Có thông tin cấu hình, theo dõi và xử lý lỗi phục vụ vận hành nếu cần.
- Đáp ứng các điều kiện khác đã được tổ chức và Scrum Team đưa vào DoD.

**Definition of Done** là cam kết về chất lượng của Increment, không nên nhầm với **acceptance criteria** của một user story. Tiêu chí chấp nhận nói về hành vi cụ thể của story; DoD mô tả trạng thái chất lượng cần đạt của công việc khi được coi là hoàn tất.

### 4.2. Increment có thể được tạo ra nhiều lần trong một Sprint

Scrum không yêu cầu nhóm chỉ có đúng một Increment vào cuối Sprint. Có thể tạo nhiều Increment trong một Sprint; mỗi Increment đã Done có thể được xem là một bước tiến có thể sử dụng. **Sprint Review không phải cổng bắt buộc để phát hành**: nhóm có thể phát hành sớm nếu đáp ứng điều kiện phát hành, hoặc giữ một Increment đã hoàn tất mà chưa phát hành vì quyết định kinh doanh hay vận hành.

Vì vậy, phân biệt ba trạng thái:

| Trạng thái | Có thể kết luận gì? | Chưa thể kết luận gì? |
| --- | --- | --- |
| **Code được viết xong** | Có hiện thực kỹ thuật ban đầu. | Chưa đủ để nói đạt DoD hoặc có thể sử dụng. |
| **Increment đáp ứng DoD** | Phần gia tăng đã tích hợp, đạt chuẩn hoàn tất và có thể sử dụng. | Chưa chắc đã được phát hành tới mọi người dùng. |
| **Đã phát hành cho người dùng** | Có khả năng nhận phản hồi thực tế tùy phạm vi triển khai. | Chưa chắc tạo giá trị hoặc đạt mục tiêu kinh doanh. |

Một bản build có thể đã hoàn tất nhưng chưa bật tính năng cho khách hàng. Việc sử dụng *feature flag* hoặc phát hành theo nhóm có thể giúp kiểm soát phân phối; các bước đó vẫn cần quy trình vận hành phù hợp.

### 4.3. Increment không nhất thiết là một “tính năng lớn”

Một Increment có thể nhỏ: bổ sung khả năng lọc một trường hợp có giá trị, cải thiện một thao tác, sửa lỗi ảnh hưởng người dùng hoặc nâng cấp hệ thống để đáp ứng mục tiêu sản phẩm. Điều quan trọng là **bước tiến sản phẩm được tích hợp và đáp ứng DoD**, không phải số màn hình được thêm.

Trong những phương pháp khác Scrum, nhóm có thể dùng cách gọi “phần tăng trưởng dùng được” theo nghĩa rộng. Khi thảo luận về **Increment của Scrum**, hãy giữ đúng ràng buộc về tính tích hợp, khả dụng và DoD.

## 5. Ba khái niệm liên hệ với nhau ra sao?

Chúng có thể xuất hiện trong cùng một hành trình phát triển, nhưng **không phải một quy trình ba bước bắt buộc**. Đôi khi nhóm không cần prototype vì vấn đề đã rõ. Đôi khi có nhiều nguyên mẫu trước khi thử MVP. Một MVP phần mềm có thể được giao thông qua nhiều Increment; cũng có Increment chỉ phục vụ cải tiến chất lượng, chưa nhằm kiểm tra một giả thuyết thị trường riêng.

~~~mermaid
flowchart TD
    A["Nhu cầu hoặc giả thuyết chưa chắc chắn"] --> B{"Điều gì rủi ro nhất?"}
    B -->|"Khả dụng, cách tương tác, giải pháp kỹ thuật"| C["Thử prototype hoặc PoC"]
    B -->|"Nhu cầu, giá trị, hành vi sử dụng"| D["Thiết kế thử nghiệm MVP"]
    B -->|"Làm phần sản phẩm đã hiểu rõ"| E["Xây Increment nhỏ theo DoD"]
    C --> F["Học từ thử nghiệm"]
    D --> G["Quan sát người dùng mục tiêu"]
    E --> H["Kiểm tra Increment đã tích hợp và có thể sử dụng"]
    F --> I{"Cần điều chỉnh?"}
    G --> I
    H --> J["Quyết định có phát hành và thu phản hồi không"]
    J --> I
    I -->|"Có"| A
    I -->|"Chưa"| K["Tiếp tục theo hướng tạo giá trị"]
~~~

Trong sơ đồ, các nhánh có thể kết hợp. Ví dụ, đội ngũ thử prototype để chọn giao diện, sau đó phát triển MVP bằng hai Increment đã Done rồi mở cho một nhóm người học.

### Quan hệ chồng lấp cần nhớ

1. **Prototype có thể dẫn tới MVP:** prototype làm rõ giao diện/giải pháp; MVP kiểm chứng giá trị với người dùng trong tình huống đủ thực.
2. **MVP có thể bao gồm một hoặc nhiều Increment:** khi MVP là phần mềm vận hành, các phần được giao phải đạt chuẩn hoàn tất phù hợp; trong Scrum, đó là DoD.
3. **Không phải mọi Increment đều là MVP:** sửa lỗi, tăng bảo mật hoặc bổ sung một phần của sản phẩm đã có vẫn là Increment, dù không phải lần thử nghiệm giá trị của một MVP mới.
4. **Không phải mọi prototype đều trở thành mã sản phẩm:** đôi khi bản thử nghiệm chỉ phục vụ khám phá rồi được bỏ.
5. **Cùng một phiên bản có thể phục vụ nhiều mục đích:** một phần sản phẩm đã Done được đưa cho nhóm người dùng đầu tiên vừa là Increment vừa là hiện thực của MVP, nếu nó được thiết kế để kiểm chứng giả thuyết giá trị cụ thể.

Do đó, câu hỏi đúng không phải “sản phẩm của chúng ta đang ở cấp 1, 2 hay 3?” mà là “chúng ta đang giảm bất định nào, và hiện vật đã đáp ứng tiêu chuẩn nào?”.

## 6. Ví dụ xuyên suốt: tính năng “Học tiếp” trên nền tảng học trực tuyến

Một nhóm thấy nhiều người bắt đầu bài học rồi dừng giữa video. Nhóm muốn tăng khả năng người học quay lại và hoàn thành bài.

### 6.1. Bước 1 — tìm hiểu vấn đề và giả thuyết

Tín hiệu ban đầu: người học dừng giữa chừng và tỷ lệ quay lại thấp. Từ dữ liệu đó **chưa thể khẳng định** nguyên nhân là họ khó tìm lại video; còn có thể do nội dung quá dài, lịch cá nhân hoặc chất lượng video.

Giả thuyết giải pháp:

> “Nếu người học tìm và mở lại đúng đoạn đã xem dễ dàng, nhiều người sẽ quay lại tiếp tục học hơn.”

Nhóm có thể phỏng vấn, xem hành trình sử dụng có sự đồng ý và thử một nguyên mẫu để biết giả thuyết về giao diện có hợp lý hay không.

### 6.2. Bước 2 — prototype để kiểm tra tương tác

Người thiết kế tạo hai giao diện có thể bấm thử:

- **A:** trang chủ hiển thị thẻ “Tiếp tục học” cùng ảnh bài và nút.
- **B:** người học vào danh sách khóa học, mở bài rồi tìm nút “Tiếp tục từ 12:35”.

Người tham gia thử thực hiện tác vụ: “Hôm qua bạn học dở. Hãy mở đúng chỗ để học tiếp.” Nhóm quan sát nơi người dùng tìm trước, số lần lạc hướng và cách họ hiểu nhãn.

**Đầu ra:** quyết định chọn cách trình bày phù hợp và những điều cần kiểm tra thêm. Prototype không chứng minh rằng dữ liệu tiến độ sẽ được lưu chính xác trên hệ thống thật hoặc tính năng sẽ làm tăng tỷ lệ hoàn thành.

### 6.3. Bước 3 — xác định MVP để kiểm chứng giá trị

Nhóm chọn một nhóm nhỏ người học mới, với phạm vi:

- Một khóa học có video và bài tập thật.
- Người học đăng nhập được, mở bài và lưu vị trí xem gần nhất trên cùng tài khoản trong phạm vi thiết bị hỗ trợ.
- Trang chủ thể hiện rõ thao tác “Học tiếp”.
- Các lỗi phổ biến và quyền truy cập được xử lý phù hợp.
- Có cách thu dữ liệu hành vi, phản hồi và hỗ trợ người dùng.

Chưa triển khai bảng xếp hạng, thuật toán gợi ý học bằng AI, gamification nhiều cấp hay tùy chỉnh giao diện sâu. Những phần đó không trực tiếp cần để kiểm chứng giả thuyết “tiếp tục học dễ dàng giúp người học quay lại”.

**Giả thuyết MVP:** Trong nhóm người học mục tiêu, một tỷ lệ đủ lớn sử dụng “Học tiếp” và tiếp tục học ở tuần kế tiếp để nhóm cân nhắc đầu tư mở rộng.

Nhóm cần thống nhất trước cách tính chỉ số, mốc thời gian, số lượng người thử và tiêu chí quyết định phù hợp; không dùng một tỷ lệ tùy ý như chuẩn chung cho mọi MVP.

### 6.4. Bước 4 — xây các Increment có thể sử dụng

Thay vì mở một backlog gồm toàn bộ tính năng nền tảng, nhóm có thể chia việc thành các phần gia tăng đáp ứng DoD:

| Increment dự kiến | Hành vi dùng được sau khi hoàn tất | Kiểm tra cần thực hiện |
| --- | --- | --- |
| **I1 – Lưu và khôi phục vị trí** | Người học đăng nhập, xem video, quay lại và tiếp tục từ vị trí đã lưu. | Kiểm thử lưu/đọc tiến độ, phân quyền, lỗi và tương thích với luồng học hiện có. |
| **I2 – Lối vào “Học tiếp”** | Người học thấy bài đang xem dở và mở lại trực tiếp từ trang chủ. | Kiểm thử điều hướng, hiển thị trạng thái và các trường hợp không có tiến độ. |
| **I3 – Phản hồi và theo dõi** | Nhóm có tín hiệu sử dụng phù hợp, người học nhận thông báo lỗi rõ ràng. | Kiểm tra dữ liệu đo không làm lộ thông tin nhạy cảm; tín hiệu đủ đáng tin cậy. |

Mỗi Increment phải thực sự tích hợp với các phần đã hoàn tất và đạt DoD tương ứng; bảng trên chỉ minh họa một cách chia phạm vi, không bảo đảm từng phần đều tự động đạt điều kiện hoàn tất.

Một MVP được thử với người dùng có thể được hình thành từ I1, I2, I3 cùng nội dung khóa học và điều kiện vận hành cần thiết. Nhóm cũng có thể cần kết hợp các phần thành một lần thử nghiệm nếu từng increment riêng chưa trả lời được giả thuyết giá trị.

### 6.5. Bước 5 — học từ bằng chứng

Giả sử sau giai đoạn thử, nhóm thấy nhiều người bấm “Học tiếp”, nhưng chỉ ít người hoàn thành bài thứ hai. Phản hồi phỏng vấn cho thấy nội dung bài quá dài. Kết luận có cơ sở là **đường quay lại học có thể đang được sử dụng**, nhưng mục tiêu hoàn thành học tập chưa đạt. Nhóm nên kiểm tra giả thuyết về độ dài nội dung trước khi đầu tư lớn vào các tính năng cá nhân hóa.

Nếu chỉ đo số lần bấm “Học tiếp”, nhóm có thể nhầm **mức độ sử dụng tính năng** với **giá trị sản phẩm**. Cần kết hợp chỉ số hành vi và kết quả học tập.

### 6.6. Sơ đồ tóm tắt hành trình

| Câu hỏi | Hiện vật phù hợp | Quyết định rút ra |
| --- | --- | --- |
| Người học có nhận ra nút “Học tiếp” không? | Prototype tương tác. | Chọn luồng và nhãn dễ hiểu hơn. |
| Người học có quay lại học nhờ tính năng đó không? | MVP có trải nghiệm thật cho nhóm mục tiêu. | Tiếp tục đầu tư, đổi hướng hoặc dừng. |
| Chức năng lưu tiến độ đã tích hợp và đạt DoD chưa? | Increment phần mềm. | Đủ điều kiện được coi là Done và cân nhắc phát hành. |

## 7. Chuyển giả thuyết thành user story và tiêu chí chấp nhận

**User story** là công cụ trao đổi về giá trị cho một nhóm người dùng. Nó không tự động là prototype, MVP hay Increment; nhóm cần xác định story thuộc thử nghiệm hoặc phạm vi nào.

Ví dụ:

> **Là** người học đang theo một khóa video, **tôi muốn** tiếp tục tại vị trí gần nhất đã xem, **để** không phải dò lại nội dung mỗi lần quay lại.

Cần làm rõ trước khi phát triển: “gần nhất” theo mốc nào, tình huống không có tiến độ, quyền truy cập, mất mạng và có nhiều thiết bị. Phạm vi MVP có thể giới hạn một số trường hợp; giới hạn đó phải minh bạch với người tham gia thử.

Một số **tiêu chí chấp nhận** minh họa:

~~~gherkin
Feature: Tiếp tục xem video đang học

Scenario: Mở lại video có tiến độ đã lưu
  Given người học đã đăng nhập và có quyền xem bài
  And vị trí xem gần nhất đã được lưu thành công
  When người học chọn "Học tiếp"
  Then hệ thống mở đúng bài đang học
  And video có thể tiếp tục tại vị trí đã lưu theo sai số được thỏa thuận

Scenario: Chưa từng xem bài
  Given người học có quyền xem bài nhưng chưa có tiến độ
  When người học mở bài
  Then video bắt đầu từ đầu
  And không có thông báo sai rằng tiến độ đã được khôi phục

Scenario: Không có quyền truy cập
  Given người học không có quyền xem bài
  When người học cố mở đường dẫn tiếp tục bài đó
  Then hệ thống từ chối truy cập theo chính sách
  And không tiết lộ tiến độ của người học khác
~~~

Những tiêu chí trên mô tả hành vi; để trở thành Increment trong Scrum, phần triển khai còn phải đáp ứng **DoD** như tiêu chuẩn kiểm thử, tích hợp, khả năng vận hành và những điều kiện chất lượng đã thống nhất.

### Một bảng kết nối ba lớp quyết định

| Lớp | Nhóm cần ghi lại | Ví dụ |
| --- | --- | --- |
| **Giả thuyết sản phẩm/MVP** | Ai cần giá trị gì; tín hiệu nào cho thấy có giá trị. | Người học có quay lại và tiếp tục học trong tuần. |
| **Story và acceptance criteria** | Hành vi cụ thể, trường hợp bình thường và lỗi. | Khôi phục đúng bài, đúng vị trí, đúng quyền truy cập. |
| **Definition of Done/Increment** | Tiêu chuẩn chất lượng, tích hợp, bằng chứng hoàn tất. | Kiểm thử đạt, phần thay đổi tích hợp, vận hành và bảo vệ dữ liệu theo DoD. |

Ba lớp này bổ sung nhau; đo hành vi người dùng không thay thế việc bảo đảm phần mềm hoạt động đúng, và vượt qua kiểm thử không chứng minh sản phẩm có nhu cầu trên thị trường.

## 8. Chọn hình thức theo rủi ro cần giảm

Trước mỗi quyết định đầu tư, nhóm nên xác định **điều chưa biết có ảnh hưởng lớn nhất**.

| Tình huống | Câu hỏi đang mở | Bước thử phù hợp trước tiên |
| --- | --- | --- |
| Người dùng không hiểu cách đặt lịch trong bản thiết kế. | Luồng tương tác có rõ không? | Prototype có thể bấm và thử tác vụ. |
| Chưa biết kết nối với hệ thống thanh toán có đáp ứng yêu cầu kỹ thuật. | Tích hợp có khả thi không? | PoC/nguyên mẫu kỹ thuật với dữ liệu và ranh giới kiểm soát phù hợp. |
| Chưa biết cửa hàng nhỏ có muốn trả tiền cho chức năng quản lý tồn kho. | Nhu cầu và giá trị trả tiền có đủ không? | MVP/dịch vụ giới hạn để kiểm tra hành vi, cam kết hoặc sử dụng thật. |
| Người dùng đã cần tính năng lọc đơn hàng rõ ràng; nhóm đang bổ sung vào hệ thống. | Phần mới đã hoàn tất đúng chuẩn chưa? | Increment nhỏ, tích hợp và đạt DoD. |
| Sản phẩm đã phát hành nhưng tỷ lệ hoàn thành tác vụ thấp. | Nguyên nhân thuộc thao tác, chất lượng hay giá trị? | Phân tích phản hồi trước, rồi chọn prototype/MVP experiment/increment cải tiến tương ứng. |

### Quy tắc thực hành theo bốn bước

1. **Ghi một giả định duy nhất hoặc một nhóm giả định liên quan.** Ví dụ: “Người học không quay lại vì khó tìm vị trí cũ.”
2. **Ước lượng hệ quả nếu sai.** Nếu sai, nhóm có lãng phí nhiều tuần hoặc gây rủi ro cho người dùng không?
3. **Chọn thử nghiệm rẻ nhất đủ đáng tin cậy.** Prototype nếu chỉ cần quan sát điều hướng; phần mềm thật nếu phải kiểm chứng hành vi quay lại.
4. **Đặt điều kiện chuyển bước.** Bằng chứng nào khiến nhóm đầu tư tiếp, thay đổi hoặc dừng?

“Rẻ nhất” ở đây nghĩa là **chi phí kiểm chứng hợp lý so với độ tin cậy và rủi ro**, không phải luôn chọn phương án ít tiền nhất. Với thay đổi liên quan thanh toán, dữ liệu sức khỏe hay bảo mật, thử nghiệm không được bỏ các kiểm soát an toàn cần thiết.

## 9. Phản hồi và chỉ số: mỗi hình thức đo điều khác nhau

Một thử nghiệm chỉ tạo ra giá trị học hỏi khi nhóm biết **mình đang đo gì** và **dùng kết quả cho quyết định nào**.

### 9.1. Chỉ số phù hợp với prototype

Có thể quan sát:

- Tỷ lệ người tham gia **hoàn tất đúng tác vụ được giao**.
- Thời gian cần để tìm nút hoặc đi hết luồng, nếu nhiệm vụ và phương pháp đo nhất quán.
- Số lần đi nhầm, cần nhờ người hướng dẫn hoặc hiểu sai thông báo.
- Mô tả bằng lời về điều người dùng kỳ vọng và điều khiến họ bối rối.
- Với PoC: tính khả thi kỹ thuật trong điều kiện thử được xác định.

**Không nên kết luận:** “80% người thử hoàn tất tác vụ nên MVP chắc chắn thành công.” Thử nghiệm khả dụng ở quy mô nhỏ không chứng minh người dùng có động lực quay lại, trả tiền hay thay đổi thói quen.

### 9.2. Chỉ số phù hợp với MVP

Chọn chỉ số gắn với giả thuyết sản phẩm:

- **Activation:** tỷ lệ người dùng thực hiện hành động cốt lõi đầu tiên.
- **Retention:** tỷ lệ người tiếp tục quay lại và nhận giá trị sau một khoảng thời gian phù hợp.
- **Task success:** tỷ lệ hoàn thành tác vụ trọng tâm trong môi trường sử dụng.
- **Tín hiệu nhu cầu:** đăng ký thử, sử dụng lặp lại, giới thiệu hoặc cam kết trả phí khi phù hợp.
- **Chất lượng trải nghiệm:** lỗi làm gián đoạn tác vụ, phản hồi hỗ trợ, khiếu nại.

Không có một chỉ số duy nhất dùng cho mọi MVP. Nếu giả thuyết là người dùng sẵn sàng trả phí, số lượt truy cập trang giới thiệu chưa đủ. Nếu giả thuyết là học viên học được kiến thức, lượt mở bài cũng chưa đủ thay cho kết quả học tập.

### 9.3. Chỉ số phù hợp với Increment và luồng phát triển

Có thể theo dõi:

- Tỷ lệ các mục **đạt DoD**, không chỉ code được đánh dấu xong.
- Lỗi nghiêm trọng xuất hiện sau triển khai và thời gian khôi phục.
- **Lead time** từ yêu cầu đến hoàn tất theo mốc nhóm quy ước.
- **Cycle time** từ lúc bắt đầu xử lý đến khi Done.
- **Throughput**: số mục hoàn tất theo đơn vị thời gian.
- **WIP**: số mục đang làm dở và điểm nghẽn gây chờ đợi.

Các chỉ số luồng giúp nhóm phát hiện trở ngại giao hàng, nhưng **throughput tăng không chứng minh sản phẩm có ích**. Cần đọc cùng chất lượng và kết quả người dùng.

### 9.4. Cẩn thận với bằng chứng yếu

Ví dụ, sau khi ra bản MVP, 30 trong 100 người học thử quay lại trong tuần. Con số 30% cần được đặt trong bối cảnh: người tham gia được chọn thế nào, hành vi quay lại được định nghĩa ra sao, tỷ lệ nền trước đó là bao nhiêu, mẫu đủ lớn cho quyết định nào, có nhóm so sánh hay không?

Phỏng vấn giúp hiểu *vì sao* người dùng hành động; dữ liệu hành vi giúp ước lượng *điều gì và bao nhiêu* đang xảy ra. Kết hợp hai nguồn thường đáng tin hơn khi chỉ nhìn một trong hai.

Đừng dùng prototype đẹp làm bằng chứng sản phẩm có người mua, hoặc dùng một MVP nhiều người quan tâm làm bằng chứng phần mềm đã đạt DoD.

## 10. Kết nối với Scrum, Kanban và XP

### 10.1. Scrum: Increment là khái niệm có định nghĩa chính thức

Trong Scrum, **Product Backlog** sắp thứ tự công việc dựa trên giá trị, rủi ro và thông tin mới. **Sprint Goal** tạo mục tiêu ngắn hạn để nhóm tập trung, còn **Increment** là kết quả sản phẩm đạt DoD và có thể sử dụng. **Sprint Review** giúp kiểm tra kết quả và thảo luận điều chỉnh Product Backlog.

Prototype và MVP có thể là kỹ thuật nghiên cứu sản phẩm hỗ trợ Product Owner và Scrum Team, nhưng **không phải sự kiện hay hiện vật Scrum bắt buộc**. Một nhóm không cần hoàn tất “một prototype, rồi một MVP” trước mỗi Sprint.

Ví dụ, trong Sprint Planning, nhóm chọn một phần chức năng đã rõ và có thể giao. Trong Sprint, họ tạo Increment đạt DoD. Song song, Product Owner và các thành viên liên quan có thể tổ chức thử nghiệm nguyên mẫu cho một nhu cầu tương lai; kết quả giúp sắp xếp Product Backlog, nhưng prototype chưa Done theo chuẩn sản phẩm không nên tự động được tuyên bố là Increment.

### 10.2. Kanban: quan sát dòng công việc từ giả thuyết tới giá trị

Kanban giúp nhóm trực quan hóa công việc, giới hạn WIP và quản lý luồng. Một nhóm có thể theo dõi các loại công việc như nghiên cứu, prototype, xây dựng, kiểm thử, phát hành và đánh giá phản hồi.

Điều này giúp nhận diện vấn đề:

- Rất nhiều prototype được tạo nhưng không ai tổng kết việc đã học.
- MVP nằm chờ phê duyệt quá lâu nên giả thuyết thị trường đã thay đổi.
- Nhiều story “đang làm” nhưng ít phần chức năng thực sự hoàn tất.
- Phát hành nhiều nhưng phản hồi người dùng chưa quay lại backlog.

**Giới hạn WIP** và chính sách chuyển bước rõ giúp giảm tắc nghẽn. Không nên ép mọi loại thử nghiệm có cùng Definition of Done: bản prototype cần tiêu chí kết thúc thử nghiệm, trong khi Increment của sản phẩm cần DoD kỹ thuật tương ứng.

### 10.3. XP: chất lượng kỹ thuật giúp phần mềm nhỏ vẫn đáng tin

XP nhấn mạnh phản hồi nhanh từ **test-driven development (TDD)**, tích hợp liên tục (CI), refactoring, lập trình cặp và thiết kế đơn giản trong bối cảnh phù hợp.

Khi nhóm triển khai MVP thành phần mềm thật, các kỹ thuật này giúp mỗi thay đổi nhỏ không làm hỏng hệ thống hiện có. Nếu prototype có mục đích khám phá nhanh và sẽ bỏ, nhóm có thể chọn cách hiện thực nhẹ hơn; nhưng mã mang sang sản phẩm cần được rà soát lại, thử nghiệm và đưa về tiêu chuẩn chất lượng chung.

**Thông điệp:** Nhóm có thể *học nhanh* ở prototype/MVP và *giao an toàn* qua các Increment. Hai mục tiêu hỗ trợ nhau khi kế hoạch và tiêu chuẩn được diễn đạt rõ.

## 11. Những nhầm lẫn thường gặp và cách sửa

| Phát biểu dễ gây hiểu sai | Vì sao chưa đúng | Cách nói/điều chỉnh phù hợp |
| --- | --- | --- |
| “MVP càng ít tính năng càng tốt, lỗi cũng được.” | Số tính năng thấp không đủ tạo giá trị; lỗi hoặc rủi ro có thể làm dữ liệu thử nghiệm vô nghĩa. | MVP có **phạm vi tối thiểu đủ để kiểm tra giả thuyết**, đồng thời đáp ứng yêu cầu an toàn và khả dụng của tình huống sử dụng. |
| “Prototype đã giống giao diện thật nên cho khách hàng dùng ngay.” | Bản mô phỏng có thể thiếu logic, dữ liệu, phân quyền hoặc xử lý lỗi. | Kiểm tra kỹ năng lực thực tế và hoàn thiện trước khi cung cấp như sản phẩm. |
| “Một story đã code xong tức là có Increment.” | Có thể chưa tích hợp, kiểm thử hoặc đáp ứng DoD. | Chỉ coi là Increment khi nó hoàn tất theo DoD và dùng được cùng phần sản phẩm hiện có. |
| “Increment chỉ được tạo ở cuối Sprint.” | Scrum cho phép nhiều Increment trong một Sprint. | Tạo các phần gia tăng Done thường xuyên; thời điểm phát hành là quyết định riêng. |
| “MVP bắt buộc phải viết toàn bộ hệ thống tự động.” | Một phần giá trị có thể được cung cấp thủ công để học trước khi đầu tư tự động hóa. | Chọn cách thử phù hợp với giả thuyết, minh bạch và kiểm soát rủi ro. |
| “Người dùng khen prototype nghĩa là MVP sẽ thành công.” | Ý kiến về bản mẫu không giống hành vi sử dụng trong thực tế. | Kiểm tra hành vi thật bằng MVP hoặc thử nghiệm giá trị phù hợp. |
| “Tính năng đã Done thì chắc chắn có giá trị.” | Chất lượng kỹ thuật và nhu cầu thị trường là hai câu hỏi khác nhau. | Kết hợp DoD/Increment với phản hồi người dùng và chỉ số kết quả. |
| “Mỗi sản phẩm chỉ có đúng một MVP từ lúc ra đời.” | Các giả thuyết mới xuất hiện khi sản phẩm và thị trường thay đổi. | Có thể dùng tư duy MVP cho thử nghiệm giá trị mới, nhưng phải đặt tên rõ để tránh nhầm với lần ra mắt đầu tiên. |

## 12. Đánh đổi, ranh giới và yêu cầu an toàn

### Chất lượng không phải thứ nên bỏ vì “đang thử”

Một prototype nội bộ không đụng dữ liệu thật có thể được làm rất nhanh. Nhưng nếu thử nghiệm đụng dữ liệu cá nhân, thanh toán, sức khỏe hoặc thao tác không thể hoàn tác, nhóm phải áp dụng các biện pháp bảo vệ và yêu cầu liên quan. “Chỉ là MVP” không làm giảm nghĩa vụ đó.

Độ tin cậy của dữ liệu cũng quan trọng: nếu phần mềm thường xuyên lỗi trong quá trình thử, nhóm khó biết người dùng rời đi vì **không cần giá trị** hay vì **trải nghiệm hỏng**.

### Không nhầm phản hồi về khả dụng với phản hồi về giá trị

Một prototype giúp biết người dùng có **tìm thấy** nút “Học tiếp” không. MVP giúp kiểm tra họ có **thực sự quay lại học** không. Increment giúp nhóm biết chức năng “Học tiếp” đã **được xây và tích hợp đúng chuẩn** không. Các câu hỏi có thể liên quan, nhưng không thay thế nhau.

### Không kéo dài nghiên cứu vô tận

Prototype rất rẻ so với xây phần mềm đầy đủ, nhưng cũng có chi phí. Nếu nhóm liên tục vẽ bản mẫu mà không xác định giả thuyết hoặc bước tiếp theo, họ chỉ chuyển lãng phí sang giai đoạn khám phá.

Tương tự, nhóm không nên liên tục phát hành các phiên bản “MVP” nhỏ nhưng không thu dữ liệu hoặc không dùng dữ liệu để điều chỉnh. Mỗi thử nghiệm cần một câu hỏi và tiêu chí kết thúc rõ.

### Không khóa cứng thứ tự phát triển

Đối với tính năng bắt buộc, đã được làm rõ và có rủi ro thấp, nhóm có thể xây trực tiếp một Increment mà không cần nguyên mẫu hoặc MVP riêng. Với sản phẩm mới, nhóm có thể phải làm nhiều prototype và thử MVP trước khi đầu tư lớn. Hãy chọn **đường học hỏi đủ ngắn để giảm rủi ro đáng kể**.

## 13. Quy trình thực hành cho một ý tưởng mới

Dưới đây là một quy trình gợi ý. Đây không phải bộ nghi thức bắt buộc của Agile hay Scrum:

| Bước | Câu hỏi ra quyết định | Hiện vật hoặc kết quả |
| --- | --- | --- |
| **1. Xác định kết quả** | Người dùng cần giải quyết vấn đề gì, dấu hiệu thành công là gì? | Phát biểu vấn đề, nhóm người dùng, mục tiêu đo được. |
| **2. Xác định rủi ro lớn nhất** | Chưa rõ trải nghiệm, khả thi kỹ thuật, nhu cầu hay chất lượng triển khai? | Danh sách giả thuyết và mức bất định. |
| **3. Chọn thử nghiệm** | Prototype, PoC, MVP hoặc Increment nào cung cấp bằng chứng đáng tin cậy với chi phí hợp lý? | Kế hoạch thử có đối tượng, phạm vi, tiêu chí dừng. |
| **4. Chia nhỏ phạm vi** | Phần nào bắt buộc để kiểm chứng, phần nào có thể để sau? | User story, backlog đã sắp thứ tự. |
| **5. Thực hiện và bảo đảm chất lượng** | Những tiêu chuẩn nào phải đạt trước khi người dùng thật sử dụng? | Prototype được mô tả đúng giới hạn, hoặc Increment đạt DoD. |
| **6. Thu và đánh giá phản hồi** | Quan sát có xác nhận giả thuyết không; giới hạn dữ liệu là gì? | Dữ liệu định tính/định lượng, kết quả kiểm thử. |
| **7. Quyết định tiếp theo** | Tiếp tục, điều chỉnh, mở rộng hay dừng? | Quyết định có căn cứ và thay đổi backlog. |

Nếu bước thứ ba dẫn tới một MVP phần mềm, bước thứ năm có thể gồm **nhiều Increment**. Nếu bước thứ ba là thử nguyên mẫu giao diện, nhóm có thể bỏ mã hoặc bản mẫu sau khi hoàn tất việc học.

## 14. Bài tập tình huống

Một công ty muốn phát triển ứng dụng giúp cửa hàng nhỏ quản lý hàng tồn. Người đề xuất đưa ra danh sách:

- Quét mã vạch để nhập xuất hàng.
- Xem số lượng còn lại của từng mặt hàng.
- Báo hàng sắp hết.
- Dự báo nhu cầu bằng AI.
- Tùy chỉnh hàng chục loại báo cáo.
- Đồng bộ với năm hệ thống kế toán.
- Phân quyền và lưu lịch sử điều chỉnh tồn kho.
- Hỗ trợ dùng offline trên điện thoại.

Công ty chưa biết **chủ cửa hàng có sẵn sàng sử dụng ứng dụng hằng ngày hay không**. Một số người còn lo nhân viên sẽ thao tác nhập xuất nhầm.

Hãy thực hiện:

1. **Viết hai giả thuyết khác nhau:** một giả thuyết về cách nhân viên thao tác và một giả thuyết về giá trị kinh doanh.
2. **Chọn prototype:** mô tả bản mẫu ngắn nhất để kiểm tra quét mã và điều chỉnh số lượng; nêu người tham gia và tác vụ.
3. **Đề xuất MVP:** chọn một cửa hàng hoặc nhóm cửa hàng phù hợp, một luồng có thể dùng thật, dữ liệu cần đo và những tính năng có thể trì hoãn.
4. **Chia MVP thành Increment:** nêu hai hoặc ba phần có giá trị, kèm ví dụ DoD hoặc ràng buộc chất lượng.
5. **Thiết kế kết luận:** bằng chứng nào khiến nhóm tiếp tục đầu tư, thay đổi giải pháp hoặc dừng?
6. **Nhận diện rủi ro:** nếu dữ liệu tồn kho sai dẫn tới bán quá số lượng, nhóm cần kiểm soát gì trước khi thử với người dùng thật?

### Hướng giải gợi ý

**Giả thuyết tương tác:** nhân viên có thể quét mã và xác nhận thay đổi số lượng mà ít sai sót hơn cách ghi tay hiện tại. Nhóm có thể thử nguyên mẫu màn hình quét/nhập với dữ liệu mẫu và quan sát người tham gia hoàn tất tác vụ.

**Giả thuyết giá trị:** chủ cửa hàng có thể kiểm tra tồn kho nhanh đủ để ra quyết định nhập hàng và duy trì thói quen cập nhật mỗi ngày. MVP giới hạn ở danh mục hàng của một cửa hàng, nhập xuất cơ bản và màn hình xem tồn. Dự báo AI, báo cáo nâng cao và nhiều tích hợp kế toán có thể đợi bằng chứng.

**Increment minh họa:** (I1) danh mục hàng và xem tồn có phân quyền; (I2) ghi nhận nhập/xuất có xác nhận và lịch sử; (I3) cảnh báo hàng sắp hết. Mỗi phần phải đáp ứng DoD và kiểm thử dữ liệu, đặc biệt khi nhiều người thao tác cùng lúc. Tùy mục tiêu, nhóm có thể cần kết hợp các phần trước khi MVP đủ giá trị cho người dùng.

**Phản hồi cần thu:** tỷ lệ giao dịch được ghi đúng, thời gian kiểm tra tồn, mức sử dụng lặp lại và phản ánh lỗi. Kết quả của prototype về thao tác không thay cho bằng chứng MVP về giá trị; hoàn tất các Increment cũng chưa đủ kết luận người dùng sẽ tiếp tục sử dụng.

## 15. Tự kiểm tra nhanh

**Câu 1.** Nhóm dựng màn hình Figma có thể bấm thử, có dữ liệu mẫu nhưng không lưu thay đổi. Đây phù hợp nhất với khái niệm nào?

**Đáp án:** Prototype tương tác. Nó giúp kiểm tra luồng và cách hiểu, chưa phải bằng chứng một sản phẩm thật đã tích hợp hoặc đem lại giá trị sử dụng dài hạn.

**Câu 2.** Một nhóm đưa bản phần mềm giới hạn cho 20 người dùng mục tiêu nhằm kiểm tra họ có tiếp tục dùng dịch vụ sau tuần đầu. Đây có phải MVP không?

**Đáp án:** Có thể là MVP nếu bản thử đủ hữu ích, an toàn trong phạm vi thử và gắn với giả thuyết, chỉ số, quyết định rõ ràng. Chỉ “20 người dùng” không đủ để xác định.

**Câu 3.** Lập trình viên hoàn thành chức năng nhưng chưa tích hợp, chưa qua kiểm thử cần thiết và chưa đạt DoD. Có Increment theo Scrum chưa?

**Đáp án:** Chưa. Increment phải tích hợp, đáp ứng Definition of Done và có thể sử dụng.

**Câu 4.** Một Increment đã Done nhưng chưa phát hành rộng. Điều đó có mâu thuẫn với Scrum không?

**Đáp án:** Không. Increment đã có thể sử dụng; phát hành là quyết định riêng. Có thể tạo nhiều Increment trong Sprint.

**Câu 5.** Một MVP được thử nghiệm và người dùng quay lại sử dụng nhiều, nhưng phát hiện lỗi lộ dữ liệu cá nhân. Có được coi đó là thành công không?

**Đáp án:** Không thể chỉ dựa vào tín hiệu sử dụng. Nhóm phải xử lý rủi ro và yêu cầu bảo vệ dữ liệu; mức độ chấp nhận được của sản phẩm thử nghiệm bao gồm chất lượng và an toàn.

**Câu 6.** Một nhóm làm prototype, rồi MVP, rồi nhiều Increment. Đây có phải thứ tự bắt buộc cho mọi tính năng Agile không?

**Đáp án:** Không. Các hình thức được chọn dựa trên điều chưa biết và mục tiêu. MVP phần mềm thực tế còn có thể được tạo thành từ một hoặc nhiều Increment.

**Câu 7.** Vì sao số lượt nhấn nút trong MVP không đủ chứng minh tính năng giúp người học thành công?

**Đáp án:** Nó chỉ cho thấy một hành vi sử dụng. Cần xem người học có đạt mục tiêu như tiếp tục học, hiểu bài hoặc hoàn thành khóa học không.

## 16. Ghi nhớ trọng tâm

- **Prototype giúp khám phá giải pháp:** kiểm tra giao diện, trải nghiệm hoặc tính khả thi trước khi cam kết triển khai đầy đủ.
- **MVP giúp kiểm chứng giá trị:** phiên bản hay trải nghiệm nhỏ nhất đủ để học về nhu cầu, hành vi và lợi ích thực với người dùng mục tiêu.
- **Usable Increment giúp giao phần mềm đạt chuẩn:** phần tăng trưởng đã tích hợp, đáp ứng Definition of Done và có thể sử dụng; không bắt buộc đã phát hành.
- **Ba khái niệm không phải ba giai đoạn cứng nhắc.** Chúng có thể chồng lấp hoặc được dùng độc lập theo giả thuyết và bối cảnh.
- **Đo đúng loại bằng chứng:** prototype đo sự hiểu và khả dụng của ý tưởng; MVP đo giá trị trong tình huống dùng thật; Increment đo trạng thái hoàn tất, chất lượng và năng lực giao hàng.
- **Phạm vi nhỏ không được đánh đổi bằng rủi ro không kiểm soát.** MVP và Increment vẫn cần những điều kiện đúng đắn, an toàn và vận hành cần thiết.
- **User story, backlog, Scrum, Kanban và XP** giúp nhóm làm rõ giá trị, chọn phạm vi, đưa các phần tăng trưởng đạt chất lượng và học từ phản hồi.

Khi hiểu rõ sự khác nhau, nhóm có thể dùng **prototype để hỏi sớm**, **MVP để học bằng kết quả thực tế** và **Increment để giao phần mềm có thể sử dụng một cách đáng tin cậy**. Sự kết hợp linh hoạt này giúp phát triển sản phẩm theo đúng tinh thần Agile: giảm bất định, giao tăng dần và điều chỉnh liên tục dựa trên phản hồi.

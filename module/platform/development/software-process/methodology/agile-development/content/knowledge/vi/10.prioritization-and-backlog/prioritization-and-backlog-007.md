# Phân biệt tiêu chí sẵn sàng do nhóm thống nhất với yêu cầu bắt buộc của khung làm việc

## 1. Vì sao cần phân biệt?

Trong một nhóm phát triển sản phẩm theo Agile, các thành viên thường thảo luận xem một hạng mục trong **product backlog** đã “sẵn sàng” để bắt đầu hay chưa. Người này muốn có user story và tiêu chí chấp nhận, người khác muốn có bản thiết kế, người khác nữa yêu cầu ước lượng hoặc kiểm thử được chuẩn bị trước. Sau một thời gian, danh sách kiểm tra nội bộ có thể bị coi là **quy định bắt buộc của Scrum**, dù nhóm tự tạo ra để giải quyết những khó khăn trước đây.

Ví dụ, nhóm phát triển nền tảng học trực tuyến có câu quy ước:

> “Story phải được ước lượng, có bản thiết kế được phê duyệt và đầy đủ mọi tiêu chí chấp nhận trước khi được đưa vào Sprint.”

Quy ước này có thể hữu ích trong một hoàn cảnh nhất định, nhưng **không phải toàn bộ các điều kiện trên đều là yêu cầu bắt buộc của Scrum**. Nếu áp dụng cứng nhắc, nhóm có thể chờ đủ tài liệu mới bắt đầu học hỏi, trì hoãn xử lý một vấn đề giá trị cao hoặc biến Product Backlog thành hàng đợi phê duyệt.

Ngược lại, nếu viện lý do “Agile linh hoạt” để bỏ qua các yêu cầu cốt lõi của khung làm việc, nhóm có thể mất tính minh bạch, không còn mục tiêu chung, thiếu chuẩn chất lượng và không thực sự vận hành theo khung đã chọn.

Vì vậy cần phân biệt:

1. **Quy tắc hoặc yêu cầu của khung làm việc:** Thành phần cần có khi nhóm tuyên bố áp dụng một framework cụ thể.
2. **Tiêu chí hoặc thỏa thuận do nhóm tự chọn:** Cách nhóm thực hiện công việc để đạt mục tiêu, có thể điều chỉnh dựa trên kinh nghiệm và bằng chứng.
3. **Ràng buộc tổ chức hoặc bên ngoài:** Pháp luật, hợp đồng, bảo mật, an toàn và tiêu chuẩn tổ chức, có thể bắt buộc dù framework Agile không trực tiếp quy định.

Chủ đề thuộc chương **Ưu tiên và backlog** của module **AGILE_DEVELOPMENT**. Việc hiểu đúng giúp nhóm tạo các phần tăng dần có giá trị, cộng tác với khách hàng, duy trì phản hồi sớm và cải tiến cách làm, đồng thời phối hợp hợp lý các thực hành user story, Scrum, Kanban và XP.

## 2. Ba lớp quy định cần được đọc đúng

| Lớp | Ai đưa ra? | Ví dụ | Có thể thay đổi như thế nào? |
| --- | --- | --- | --- |
| **Khung làm việc đã chọn** | Định nghĩa của framework | Trong Scrum: các accountabilities, events, artifacts và commitments được mô tả trong Scrum Guide | Muốn nói đang áp dụng Scrum cần giữ các yếu tố thiết yếu; thay đổi tùy ý một yếu tố cốt lõi làm sai lệch việc áp dụng khung |
| **Thỏa thuận làm việc của nhóm** | Nhóm cùng thống nhất, thường có Product Owner và vai trò liên quan tham gia | “Hạng mục dự định kéo vào thực hiện nên có ví dụ luồng chính và người giải đáp câu hỏi nghiệp vụ” | Có thể thử, đánh giá và điều chỉnh khi không còn phục vụ dòng giá trị |
| **Ràng buộc tổ chức/bên ngoài** | Tổ chức, khách hàng, cơ quan quản lý hoặc hợp đồng | Yêu cầu bảo vệ dữ liệu cá nhân, tiêu chuẩn kiểm toán, phê duyệt bảo mật bắt buộc | Chỉ được thay đổi theo đúng thẩm quyền và quy trình liên quan |

**Không được đồng nhất “tự chọn” với “không cần thực hiện”.** Khi nhóm đã đồng thuận một quy tắc hữu ích, mọi người nên thực hiện nhất quán cho đến khi cùng điều chỉnh. Nhưng cần gọi đúng tên và hiểu nguồn gốc để không xem một thói quen nội bộ là luật phổ quát của Scrum hay Agile.

Tương tự, **không phải mọi yêu cầu bắt buộc của tổ chức đều được Scrum yêu cầu**. Chẳng hạn, một hệ thống ngân hàng có thể cần bằng chứng rà soát bảo mật trước triển khai. Đây là ràng buộc quan trọng, nhưng không có nghĩa Scrum Guide tự quy định một loại biểu mẫu phê duyệt bảo mật cố định cho mọi sản phẩm.

## 3. Scrum thực sự yêu cầu những gì?

Scrum là một **framework nhẹ** hướng đến giải quyết vấn đề phức tạp và tạo giá trị thông qua kiểm tra, thích ứng. Để phân biệt các “quy tắc bắt buộc”, cần hiểu những yếu tố chính của framework thay vì chỉ nhớ tên một buổi họp.

### 3.1. Những thành phần cốt lõi

| Nhóm thành phần Scrum | Những thành phần cần nhận diện | Ý nghĩa đối với backlog và lựa chọn công việc |
| --- | --- | --- |
| **Accountabilities** (trách nhiệm) | Product Owner, Scrum Master, Developers | Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog; Developers lập kế hoạch tạo Increment; Scrum Master chịu trách nhiệm thiết lập Scrum và hiệu quả Scrum Team |
| **Events** (sự kiện) | Sprint, Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective | Tạo các điểm kiểm tra, điều chỉnh mục tiêu, công việc, kết quả và cách làm |
| **Artifacts** (tạo tác) | Product Backlog, Sprint Backlog, Increment | Làm minh bạch công việc hướng đến giá trị, kế hoạch Sprint và phần sản phẩm đã hoàn thành |
| **Commitments** (cam kết tương ứng) | Product Goal, Sprint Goal, Definition of Done | Tạo đích đến, sự tập trung và chuẩn chất lượng minh bạch cho các artifact |

Một số điểm đặc biệt quan trọng:

- **Product Backlog** là danh sách có thứ tự, phát triển theo thời gian về những điều cần để cải thiện sản phẩm. Product Owner chịu trách nhiệm về việc quản lý hiệu quả Product Backlog, bao gồm sắp xếp thứ tự các Product Backlog Item (PBI).
- **Product Goal** là cam kết của Product Backlog, giúp nhóm có mục tiêu sản phẩm dài hạn thay vì chỉ tối ưu việc đóng nhiều task.
- **Sprint Planning** xác định vì sao Sprint có giá trị, có thể làm gì trong Sprint và cách thực hiện công việc đã chọn. Scrum Team cộng tác để xây dựng Sprint Goal; Developers lựa chọn PBI cho Sprint thông qua trao đổi với Product Owner.
- **Sprint Backlog** gồm Sprint Goal, các PBI được chọn và kế hoạch hành động của Developers.
- **Increment** phải đáp ứng **Definition of Done (DoD)**. Công việc chưa đáp ứng DoD không trở thành một phần của Increment.
- **Sprint Review** và **Sprint Retrospective** tạo cơ hội kiểm tra, thích ứng kết quả sản phẩm và cách làm việc. Backlog có thể điều chỉnh theo điều được học.

Các thành phần này gắn với nhau. Ví dụ, nếu Product Owner tự quyết toàn bộ chi tiết kỹ thuật cho Developers, nhóm có thể làm sai tinh thần tự quản của Scrum; nếu nhóm tuyên bố “Done” nhưng chưa đạt Definition of Done, tính minh bạch về Increment bị phá vỡ.

### 3.2. Những thứ Scrum không yêu cầu phải dùng như một mẫu duy nhất

Scrum không bắt buộc mọi Product Backlog Item phải:

- Được viết theo mẫu **“Là... tôi muốn... để...”** của user story.
- Có số **story point**, dùng **Planning Poker** hoặc một thang ước lượng cố định.
- Có một trường **Definition of Ready** chính thức hoặc được đánh dấu “READY” trước mọi Sprint.
- Được thẩm định bởi một ban phê duyệt “ready gate” riêng.
- Có tài liệu thiết kế chi tiết, wireframe hoặc bản đặc tả dài theo một mẫu chung.
- Có các vai trò “Business Analyst”, “QA” hoặc “Tech Lead” như các accountability riêng của Scrum.
- Được cố định toàn bộ yêu cầu từ đầu Sprint và không được làm rõ thêm trong quá trình làm.

Những thực hành trên **có thể hữu ích** tùy công việc. Ví dụ, ước lượng giúp nhóm trao đổi mức độ phức tạp, ví dụ kiểm thử giúp tránh hiểu sai, bản thiết kế giúp thống nhất trải nghiệm. Nhưng **hữu ích** khác với **Scrum bắt buộc**.

Trong Scrum, **Product Backlog refinement** là hoạt động liên tục nhằm chia nhỏ và làm rõ PBI; nó không được quy định là một event chính thức với thời lượng hay lịch họp cố định. Điều này cho phép nhóm chọn hình thức trao đổi phù hợp để PBI đủ minh bạch khi cần.

### 3.3. “Có thể Done trong một Sprint” không đồng nghĩa “đã biết hết mọi chi tiết”

Trong hướng dẫn Scrum, PBI có thể được chọn tại Sprint Planning khi Developers đánh giá rằng có thể hoàn thành chúng trong một Sprint. Hoạt động refinement thường giúp PBI đạt mức minh bạch này.

Điều đó **không đòi hỏi** mọi tình huống biên, chi tiết giao diện hoặc từng dòng kiểm thử phải được viết ra trước. Nhóm vẫn học hỏi và làm rõ trong Sprint. Tuy nhiên, nếu một quy tắc pháp lý quan trọng, khả năng truy cập dữ liệu hay một phụ thuộc then chốt chưa thể giải quyết, Developers cần đánh giá thận trọng khả năng đạt DoD và Sprint Goal.

**Sẵn sàng tương đối** nghĩa là đã có đủ hiểu biết và điều kiện để bắt đầu công việc có trách nhiệm. Nó khác với lời hứa rằng không còn bất kỳ điều chưa chắc chắn nào.

## 4. Definition of Ready là gì và vì sao là thỏa thuận tùy chọn?

**Definition of Ready (DoR)** thường được dùng như một tên gọi cho **thỏa thuận của nhóm về những dấu hiệu cho thấy một hạng mục đủ rõ và đủ khả thi để đưa vào công việc tiếp theo**. Tùy tổ chức, DoR có thể là vài câu hỏi ngắn, một checklist hoặc chính sách rõ ràng của một trạng thái trên bảng công việc.

Điểm quan trọng: **DoR không phải commitment chính thức của Scrum**. Scrum có **Definition of Done**, nhưng không đưa ra một Definition of Ready bắt buộc với danh sách điều kiện chung cho mọi đội.

DoR có thể giúp:

- Phát hiện hạng mục quá lớn hoặc thiếu mục đích người dùng.
- Làm rõ câu hỏi nghiệp vụ quan trọng trước khi tiêu tốn nhiều công sức.
- Nhận diện phụ thuộc, rủi ro, người ra quyết định và tài nguyên cần thiết.
- Hỗ trợ Developers và Product Owner trao đổi có trách nhiệm về công việc có thể chọn.
- Giảm chờ đợi, giảm làm lại và tăng khả năng giao Increment sớm.

Nhưng DoR sẽ gây hại nếu:

- Biến thành **cửa kiểm duyệt** ngăn công việc giá trị cao chỉ vì chưa điền đủ biểu mẫu.
- Yêu cầu **mọi chi tiết phải được xác định trước**, dù công việc cần khám phá và thử nghiệm.
- Tạo cảm giác Product Owner hoặc một nhóm chức năng có thể “ra lệnh cho Developers nhận việc” chỉ bằng cách đóng dấu READY.
- Được dùng để chứng minh trách nhiệm thuộc về người viết yêu cầu, thay vì thúc đẩy cộng tác.
- Luôn áp dụng một danh sách dài như nhau cho sửa lỗi khẩn, thăm dò rủi ro, nghiên cứu và tính năng người dùng.

**Tên gọi không quan trọng bằng hành vi.** Nhóm có thể không dùng thuật ngữ DoR mà vẫn có câu hỏi sàng lọc hữu ích: “Ai cần điều này?”, “Giá trị là gì?”, “Chúng ta có biết cách kiểm chứng?”, “Điều gì đang chặn khả năng hoàn thành?”.

## 5. Đừng nhầm DoR, acceptance criteria và DoD

Ba khái niệm thường cùng xuất hiện trong thảo luận user story nhưng phục vụ mục tiêu khác nhau.

| Khía cạnh | Definition of Ready (DoR) | Acceptance criteria (tiêu chí chấp nhận) | Definition of Done (DoD) |
| --- | --- | --- | --- |
| **Mục đích** | Giúp nhóm quyết định PBI có đủ minh bạch/khả thi để xem xét bắt đầu không | Mô tả hành vi và điều kiện một hạng mục cần đáp ứng | Xác định chuẩn chất lượng để công việc trở thành một phần Increment |
| **Trạng thái với Scrum** | Thực hành tùy chọn của nhóm, không phải commitment Scrum | Thực hành hữu ích, không có mẫu bắt buộc trong Scrum | Commitment chính thức gắn với Increment |
| **Áp dụng lúc nào?** | Chủ yếu khi chuẩn bị chọn hoặc kéo công việc | Khi làm rõ, triển khai và kiểm chứng hành vi riêng | Khi đánh giá công việc đã đủ điều kiện thành Increment hay chưa |
| **Phạm vi** | Mức sẵn sàng của công việc sắp làm | Yêu cầu đặc thù của story/PBI | Chuẩn chung theo phạm vi áp dụng của sản phẩm/Increment |
| **Ví dụ** | “Hiểu mục tiêu; biết người giải đáp; rủi ro quan trọng được nêu” | “Khi lưu khóa lần hai, danh sách không tạo mục trùng” | “Được tích hợp; kiểm thử bắt buộc đạt; tiêu chuẩn bảo mật và chất lượng áp dụng được đáp ứng” |
| **Nguy cơ khi dùng sai** | Quan liêu hóa và ngăn khám phá | Biến thành danh sách thiết kế bất biến hoặc quá mơ hồ | Gắn nhãn Done khi chất lượng chưa đủ, tạo tiến độ giả |

**Ví dụ cụ thể:** Nhóm chuẩn bị story “Lưu khóa học yêu thích”.

- **DoR đề xuất:** Đã rõ người hưởng lợi, lợi ích mong muốn và luồng chính; có người giải đáp câu hỏi về tài khoản; story được chia đủ nhỏ để cân nhắc thực hiện.
- **Acceptance criteria:** Một người học đã đăng nhập lưu được khóa; lưu lặp không tạo trùng; người khác không xem được danh sách riêng; lỗi lưu không bị báo thành công.
- **DoD:** Phần mềm và kiểm thử liên quan được tích hợp, đáp ứng các chuẩn chất lượng chung mà nhóm/tổ chức đã xác lập.

Nếu story **đủ rõ để bắt đầu nhưng chưa đạt các tiêu chí hành vi**, nó chưa được hoàn thành. Nếu story **đạt hành vi nghiệp vụ nhưng chưa đạt DoD**, cũng không thể coi là một phần Increment đã Done. Ba khái niệm mô tả ba câu hỏi khác nhau.

### DoD và chuẩn tối thiểu của tổ chức

Khi tổ chức có tiêu chuẩn Definition of Done cho sản phẩm hoặc nhiều nhóm cùng phát triển sản phẩm, nhóm phải tôn trọng các chuẩn áp dụng. Trong Scrum, nếu không có chuẩn tổ chức, Scrum Team cần tạo Definition of Done phù hợp với sản phẩm; nếu có chuẩn tổ chức, DoD của nhóm ít nhất phải đáp ứng chuẩn đó.

Ngược lại, **DoR không tự động có địa vị tương đương DoD** chỉ vì cùng chứa chữ “Definition”. Đặt hai tên cạnh nhau trong công cụ quản lý backlog không biến chúng thành hai commitment Scrum ngang nhau.

## 6. Thiết lập tiêu chí sẵn sàng hữu ích như thế nào?

Một DoR hoặc working agreement tốt bắt đầu từ **vấn đề thực tế của nhóm**, không phải từ một checklist sao chép nguyên mẫu.

### Bước 1: Nhận diện việc gì khiến nhóm thường bị chặn

Ví dụ, nhóm phát triển nền tảng học trực tuyến thấy nhiều hạng mục “đang làm” phải dừng vì chưa có người xác nhận chính sách hoàn tiền. Nhóm nên hỏi:

- Story nào bị chặn vì thiếu thông tin?
- Thiếu thông tin có thể được làm rõ sớm hơn không?
- Có kiểu công việc nào cần khám phá trước khi ước lượng khả năng hoàn thành không?
- Vấn đề có nằm ở khối lượng story quá lớn, phụ thuộc giữa nhóm hoặc chất lượng môi trường?

Nếu nút nghẽn thật là hệ thống kiểm thử không ổn định, thêm điều kiện “mọi story phải có bản thiết kế giao diện” sẽ không giải quyết nguyên nhân.

### Bước 2: Viết tiêu chí thành câu hỏi thực dụng

Một tập gợi ý ngắn:

| Nhóm câu hỏi | Tiêu chí gợi ý | Vì sao có ích? |
| --- | --- | --- |
| **Giá trị** | Người dùng/bên hưởng lợi và kết quả mong đợi đã đủ rõ chưa? | Tránh làm tính năng chỉ vì có yêu cầu giải pháp |
| **Phạm vi** | Story có đủ nhỏ để cân nhắc hoàn thành trong chu kỳ làm việc mục tiêu không? | Giảm dở dang và tích hợp muộn |
| **Kiểm chứng** | Nhóm có thể nêu một hoặc vài ví dụ chứng minh hành vi mong muốn không? | Giảm tranh luận khi kiểm thử |
| **Phụ thuộc** | Các phụ thuộc quyết định khả năng hoàn thành đã được nhận diện chưa? | Giúp đánh giá rủi ro lập kế hoạch |
| **Quyết định** | Có người có thể trả lời các câu hỏi nghiệp vụ quan trọng không? | Tránh bị chặn kéo dài |
| **Chất lượng/rủi ro** | Có yêu cầu bảo mật, dữ liệu, tuân thủ hoặc khả năng tiếp cận cần lưu ý không? | Không bỏ sót điều có thể gây hậu quả lớn |

Đây là **bộ câu hỏi tham khảo**, không phải danh mục “đúng chuẩn Scrum”. Nhóm nên chọn số ít tiêu chí giải quyết được vấn đề thật và để không gian cho việc học hỏi khi thực hiện.

### Bước 3: Phân biệt ba trạng thái của thông tin

Không phải điều chưa được biết đều có cùng mức độ rủi ro:

1. **Đã rõ:** Có quyết định và ví dụ đủ để thực hiện.
2. **Chưa rõ nhưng có thể học trong khi làm:** Ví dụ cách bố trí tốt nhất của bộ lọc có thể được thử bằng bản mẫu hoặc phản hồi sớm.
3. **Chưa rõ và có thể cản trở khả năng hoàn tất:** Ví dụ chưa được phép truy cập hệ thống thanh toán thử nghiệm, chưa biết luật hoàn tiền hoặc chưa có quyết định về quyền sử dụng dữ liệu.

Đối với trạng thái 2, có thể **chủ động bắt đầu một lát cắt học hỏi**. Đối với trạng thái 3, nhóm cần xử lý phụ thuộc, giảm phạm vi hoặc chọn một công việc khám phá phù hợp trước khi cam kết phần rủi ro cao.

### Bước 4: Thử thỏa thuận trong một khoảng thời gian

Ví dụ:

> “Trong hai Sprint tới, trước khi cân nhắc một Product Backlog Item cho Sprint, Product Owner và Developers cùng làm rõ giá trị, ví dụ luồng chính, người giải đáp câu hỏi nghiệp vụ và phụ thuộc có nguy cơ cản trở Done. Các câu hỏi còn mở được ghi lại cùng cách xử lý; không yêu cầu mọi chi tiết UI phải hoàn thành trước.”

Nhóm có thể xem lại sau vài Sprint: thời gian chờ làm rõ đã giảm chưa, có tiêu chí nào khiến việc chuẩn bị kéo dài mà không cải thiện kết quả không?

### Bước 5: Chỉnh sửa bằng bằng chứng

Giữ quy tắc hữu ích, bỏ quy tắc hình thức, bổ sung điều kiện cho những rủi ro thực tế. Người điều phối có thể ghi rõ **tại sao nhóm đặt ra quy tắc** để thành viên mới hiểu mục đích và có thể chất vấn khi điều kiện thay đổi.

## 7. Làm rõ Product Backlog Item mà không dựng “cửa khóa” cứng

Một cách vận dụng là đặt câu hỏi khi chuyển PBI từ ý tưởng sang công việc chuẩn bị thực hiện:

~~~mermaid
flowchart TD
    A["Ý tưởng / nhu cầu trong Product Backlog"] --> B["Làm rõ giá trị và bối cảnh"]
    B --> C{"Đủ minh bạch để Developers cân nhắc hoàn thành?"}
    C -->|"Có"| D["Cân nhắc chọn khi lập kế hoạch phù hợp"]
    C -->|"Còn điều quan trọng chưa rõ"| E["Trao đổi, chia nhỏ, giải quyết phụ thuộc hoặc khám phá"]
    E --> B
    D --> F["Triển khai, tiếp tục làm rõ và kiểm thử"]
    F --> G{"Đáp ứng tiêu chí liên quan và DoD?"}
    G -->|"Chưa"| F
    G -->|"Có"| H["Increment hoàn tất; kiểm tra giá trị"]
~~~

Sơ đồ này **minh họa quá trình tư duy**, không phải workflow bắt buộc của Scrum. Trong Sprint Planning, Scrum Team cần trao đổi Sprint Goal, giá trị và khả năng giao hàng; Developers chọn PBI cho Sprint. Trong Kanban, nhóm có thể có chính sách rõ ràng về thời điểm kéo hạng mục mới mà không dùng Sprint.

### Khi nào có thể tiến hành dù còn điều chưa rõ?

Có thể hợp lý khi:

- Chưa biết cách hiển thị bộ lọc tối ưu, nhưng có thể làm một phiên bản nhỏ và thử với người dùng.
- Cần đo xem một khả năng có đáng xây tiếp không; công việc hiện tại là **thử nghiệm hoặc khám phá**, có mục tiêu học hỏi và giới hạn rõ.
- Một tình huống biên ít rủi ro có thể được làm rõ trong lúc triển khai bởi người có thẩm quyền đang sẵn sàng trao đổi.

Nên tránh cam kết một hạng mục như thể có thể Done khi:

- Phụ thuộc bên ngoài chưa có phương án xử lý và ảnh hưởng trực tiếp tới luồng chính.
- Chưa có quy tắc quyền truy cập hoặc bảo mật thiết yếu.
- Mục tiêu sản phẩm chưa rõ đến mức không biết kết quả nào có giá trị.
- Phạm vi lớn hơn nhiều so với năng lực và thời gian có thể dành cho Sprint.

Quyết định phụ thuộc **mức bất định, mức rủi ro và khả năng học trong chu kỳ**, không phụ thuộc việc biểu mẫu có đủ dấu tích xanh hay chưa.

## 8. Ví dụ xuyên suốt: lựa chọn công việc cho nền tảng học trực tuyến

Giả sử nhóm có Product Goal: **giúp người mới học lập trình lựa chọn và bắt đầu khóa học phù hợp với ít trở ngại hơn**.

Product Backlog hiện có các hạng mục giả định:

| PBI | Nhu cầu | Hiện trạng hiểu biết | Rủi ro/điều cần trao đổi |
| --- | --- | --- | --- |
| **A — Hiển thị trình độ khóa học** | Người mới nhận ra khóa phù hợp | Biết nguồn dữ liệu và luồng hiển thị chính | Cần thống nhất cách xử lý khóa thiếu thông tin |
| **B — Đăng ký và thanh toán** | Người học mua được khóa trả phí | Luồng chính đã được mô tả | Chưa có môi trường thanh toán thử nghiệm; hoàn tiền chưa rõ |
| **C — Lưu khóa yêu thích** | Người học quay lại khóa đang cân nhắc | Có user story và ví dụ lưu/xóa cơ bản | Cần xác định dữ liệu có đồng bộ đa thiết bị không |
| **D — Gợi ý khóa bằng AI** | Người học nhận đề xuất phù hợp | Chưa biết nhóm người dùng cần và cách đánh giá | Nhiều giả thuyết; phù hợp nghiên cứu trước khi đầu tư lớn |

### 8.1. Vận dụng tiêu chí sẵn sàng do nhóm thống nhất

Nhóm có thể chọn:

- **A:** Cùng làm rõ quy tắc cho dữ liệu thiếu rồi chia phần tăng dần nhỏ; nếu Developers đánh giá khả thi, có thể cân nhắc đưa vào Sprint.
- **B:** Không tự đánh dấu “ready” chỉ vì câu user story đã đẹp. Cần giải quyết môi trường thử nghiệm, quyền hạn và quy tắc quan trọng, hoặc chia thành một PBI khám phá tích hợp thanh toán có mục tiêu rõ trước.
- **C:** Nếu đồng bộ đa thiết bị là giá trị cốt lõi, cần xác nhận phạm vi; nếu chưa cần, thỏa thuận một lát cắt nhỏ có thể dùng được và ghi rõ điều để sau.
- **D:** Không bắt buộc phải viết đặc tả AI đầy đủ trước khi học. Có thể ưu tiên thử bản mẫu khuyến nghị thủ công và quan sát nhu cầu trước khi đầu tư hạ tầng.

Như vậy, **mức sẵn sàng là thông tin cho quyết định ưu tiên và lập kế hoạch**; nó không thay thế đánh giá giá trị, chi phí, rủi ro và khả năng nhận phản hồi.

### 8.2. Minh họa một user story sau Conversation

**Card:**

> **Là** người học mới, **tôi muốn** thấy trình độ và điều kiện tiên quyết của khóa học ngay ở danh sách kết quả, **để** nhận biết khóa nào phù hợp trước khi mở chi tiết.

**Các câu hỏi cần trao đổi:**

- “Cơ bản” và “Nâng cao” do ai định nghĩa?
- Nếu khóa chưa có dữ liệu trình độ, hiển thị thế nào để tránh gây hiểu lầm?
- Người dùng điện thoại hoặc sử dụng bàn phím có đọc được thông tin?
- Chỉ hiển thị nhãn đã đủ, hay cần tóm tắt điều kiện tiên quyết?
- Nguồn dữ liệu có đảm bảo nhất quán giữa danh sách và trang chi tiết?

**Ví dụ tiêu chí chấp nhận sau khi trao đổi:**

~~~gherkin
Tính năng: Hiển thị thông tin trình độ khóa học

  Tình huống: Khóa có dữ liệu trình độ
    Cho trước khóa "Java nhập môn" được xác nhận thuộc mức "Cơ bản"
    Khi người học xem thẻ kết quả của khóa "Java nhập môn"
    Thì thẻ hiển thị nhãn trình độ "Cơ bản"
    Và thông tin này nhất quán với trang chi tiết của khóa

  Tình huống: Khóa chưa có dữ liệu trình độ
    Cho trước khóa "Java thực hành" chưa được xác định trình độ
    Khi người học xem thẻ kết quả của khóa "Java thực hành"
    Thì giao diện không tự gán mức "Cơ bản" hoặc "Nâng cao"
    Và hiển thị trạng thái thông tin theo quy tắc đã thống nhất
~~~

**DoR tùy chọn** có thể giúp cả nhóm xác nhận rằng nguồn dữ liệu, người quyết định nhãn và luồng chính đã rõ. Nhưng việc hiển thị đúng, tích hợp, kiểm thử và đáp ứng tiêu chuẩn chất lượng vẫn thuộc **việc hoàn tất**, được đánh giá qua acceptance criteria và DoD.

### 8.3. Tránh biến DoR thành phương tiện ép nhận việc

Giả sử Product Owner gắn nhãn “Ready” cho PBI B vì đã có mockup và ước lượng. Developers vẫn nhận thấy môi trường thanh toán chưa sẵn sàng, khiến không thể kiểm thử hành vi quan trọng. Khi đó:

1. Developers nêu rõ trở ngại và tác động tới Sprint Goal, Increment, DoD.
2. Product Owner cùng nhóm trao đổi ưu tiên, phương án chia nhỏ hoặc xử lý phụ thuộc.
3. Nhóm có thể chọn một PBI khám phá giao thức thanh toán hoặc ưu tiên PBI khác có giá trị, nếu phù hợp.
4. Nhãn “Ready” được cập nhật để phản ánh thực tế; không dùng nó làm lý do ép Developers cam kết khả năng chưa có.

Việc này không làm Scrum “kém kỷ luật”. Ngược lại, nó giúp **dự báo dựa trên năng lực và rủi ro thực**, giữ mục tiêu và chất lượng minh bạch.

## 9. Ai có quyền quyết định và ai nên tham gia?

Vấn đề “ready” thường trở nên căng thẳng khi các bên không hiểu quyền quyết định.

| Câu hỏi | Trách nhiệm và cách cộng tác phù hợp |
| --- | --- |
| Ai quyết định thứ tự Product Backlog? | **Product Owner** chịu trách nhiệm quản lý hiệu quả và sắp xếp Product Backlog trong Scrum; có thể nhận góp ý và ủy quyền công việc nhưng vẫn chịu trách nhiệm cuối cùng |
| Ai xác định PBI nào có thể hoàn tất trong Sprint? | **Developers** lựa chọn PBI trong Sprint Planning thông qua trao đổi với Product Owner và dựa trên năng lực, hiểu biết, DoD |
| Ai làm rõ nghiệp vụ? | Product Owner cùng người có hiểu biết và thẩm quyền phù hợp; Developers cần chủ động đặt câu hỏi và tham gia xác nhận ví dụ |
| Ai xác định cách triển khai kỹ thuật? | Developers tự quản cách tạo Increment, phối hợp với các vai trò liên quan theo tiêu chuẩn tổ chức |
| Ai hỗ trợ cải tiến cách làm và loại bỏ trở ngại Scrum? | Scrum Master phục vụ hiệu quả Scrum Team và tổ chức, hỗ trợ kiểm tra và thích ứng |
| Ai phê duyệt yêu cầu ngoài thẩm quyền nhóm? | Theo quy trình của tổ chức, hợp đồng và yêu cầu pháp lý; không tự suy từ nhãn DoR hoặc trách nhiệm Product Owner |

**Không nên tạo vai trò “người cấp phép Ready” có quyền phủ quyết mọi việc** nếu nhóm chưa có lý do rõ và cách kiểm soát tác động của cơ chế đó. Trong môi trường có yêu cầu an toàn hoặc tuân thủ, phê duyệt độc lập có thể thực sự cần thiết; khi đó hãy diễn đạt đúng nguồn ràng buộc thay vì gán nó thành quy định của Scrum.

## 10. Tiêu chí sẵn sàng trong Scrum, Kanban và XP

### Scrum

Trong Scrum, Product Backlog và refinement giúp chuẩn bị cho Sprint Planning. Một working agreement về mức minh bạch của PBI có thể hỗ trợ Developers dự báo khả năng Done và tạo Sprint Goal. **Scrum không yêu cầu DoR chính thức**; nhóm cũng không được dùng DoR tùy chọn để thay cho Product Goal, Sprint Goal hoặc Definition of Done.

### Kanban

Kanban thường khuyến khích nhóm **trực quan hóa công việc và làm rõ chính sách luồng**. Một chính sách cho cột “Ready to pull” có thể quy định loại công việc, thông tin tối thiểu, cách ưu tiên và điều kiện kéo việc. Chính sách này giúp dòng công việc được vận hành nhất quán, nhưng **không phải mẫu DoR giống hệt cho mọi hệ thống Kanban**.

Ví dụ, nhóm hỗ trợ vận hành có thể cho phép kéo ngay sự cố nghiêm trọng theo chính sách khẩn cấp, trong khi yêu cầu phát triển thông thường cần được làm rõ và xếp thứ tự trước. Nếu “Ready” trở thành một hàng đợi chờ phê duyệt quá lâu, nhóm nên xem lại chính sách bằng cycle time, work item age và công việc bị chặn.

### Extreme Programming (XP)

XP nhấn mạnh user story, trao đổi thường xuyên với đại diện khách hàng, kiểm thử, tích hợp liên tục, thiết kế có thể thay đổi và giao các phần nhỏ. Một nhóm XP có thể thống nhất rằng story nên đủ nhỏ, có ví dụ chấp nhận rõ và khách hàng có thể giải đáp trong quá trình làm.

Điểm nhấn là **conversation và feedback**, không phải hoàn tất một bản đặc tả bất biến trước khi lập trình. Thực hành kỹ thuật như TDD, CI hay refactoring hỗ trợ nhóm xử lý thay đổi khi học thêm.

| Vấn đề | Scrum | Kanban | XP |
| --- | --- | --- | --- |
| Chọn/lấy việc | Sprint Planning và Product Backlog được sắp thứ tự | Chính sách kéo việc và quản lý dòng chảy | Câu chuyện giá trị nhỏ, trao đổi với khách hàng, lựa chọn phù hợp |
| Tiêu chí “sẵn sàng” | DoR là thỏa thuận tùy chọn | Có thể là chính sách rõ ràng của luồng | Có thể là quy ước story đủ hiểu và kiểm chứng |
| Chuẩn hoàn tất | Definition of Done là commitment của Increment | Chính sách hoàn tất/tiêu chuẩn chất lượng theo hệ thống | Kiểm thử chấp nhận và thực hành kỹ thuật chất lượng |
| Phản hồi | Sprint Review và các trao đổi thường xuyên | Phản hồi và cải tiến luồng liên tục | Phát hành nhỏ, kiểm thử và phản hồi nhanh |

Đừng đánh đồng các cách tiếp cận này thành một bộ quy định bắt buộc duy nhất; nhóm có thể lựa chọn và phối hợp thực hành phù hợp, nhưng cần nói rõ mình đang áp dụng framework nào.

## 11. Đo xem thỏa thuận sẵn sàng có giúp ích không

Thêm checklist không đồng nghĩa với cải thiện. Nhóm nên kiểm tra **tác động của thỏa thuận** sau một khoảng thời gian.

| Tín hiệu | Cách đọc | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **Số PBI bị chặn vì thiếu quyết định nghiệp vụ** | Có giảm việc phải chờ khi đã bắt đầu không? | Cần phân biệt thiếu thông tin và thay đổi nhu cầu hợp lý |
| **Thời gian từ lúc đề xuất đến lúc bắt đầu thực hiện** | DoR có tạo hàng đợi chuẩn bị kéo dài không? | Tăng thời gian có thể do ưu tiên thấp, không chỉ do checklist |
| **Cycle time** | Hạng mục đã bắt đầu được hoàn tất nhanh và ổn định hơn không? | So sánh cùng loại, độ lớn hạng mục và định nghĩa luồng |
| **Số lần làm lại do hiểu sai** | Conversation và ví dụ chấp nhận có hữu ích không? | Phân biệt làm lại do hiểu sai với điều chỉnh vì phản hồi mới |
| **Tỷ lệ hạng mục đạt DoD** | Nhóm có giao phần sản phẩm hoàn chỉnh đúng chuẩn hơn không? | Không sử dụng để ép tăng sản lượng bằng cách hạ DoD |
| **Thời gian chờ phê duyệt/giải đáp** | Có người hoặc bước quy trình nào là nút nghẽn? | Không tự quy trách nhiệm cho cá nhân nếu quyền hạn thiếu rõ |
| **Phản hồi người dùng** | Hạng mục giao có tạo giá trị dự kiến không? | Hoàn tất theo checklist không chứng minh outcome |

**Một thỏa thuận tốt có thể bị bỏ hoặc sửa** khi tác dụng phụ lớn hơn lợi ích. Ví dụ, nếu “phải có wireframe được ký duyệt” khiến mọi story chờ ba tuần dù câu hỏi chủ yếu về dữ liệu, nhóm nên trao đổi bỏ điều kiện chung hoặc giới hạn nó cho những loại giao diện có rủi ro cụ thể.

Không nên biến “tỷ lệ story Ready” thành mục tiêu cá nhân hay áp dụng máy móc quy tắc “tất cả story phải Ready hai Sprint trước”. Điều đó dễ khuyến khích đánh dấu theo hình thức mà không cải thiện hiểu biết thực tế.

## 12. Những ngộ nhận phổ biến

**Ngộ nhận 1: “Scrum bắt buộc có Definition of Ready.”** Scrum có Definition of Done là commitment của Increment; DoR là thực hành tùy chọn được nhiều nhóm sử dụng.

**Ngộ nhận 2: “Không được bắt đầu bất cứ việc gì khi chưa đủ 100% acceptance criteria.”** Tùy rủi ro, nhóm có thể làm rõ dần khi triển khai. Một PBI chưa rõ mục tiêu hoặc có phụ thuộc chặn DoD cần được xử lý, nhưng không cần biết trước mọi chi tiết của mọi tác vụ.

**Ngộ nhận 3: “Story có story point thì đã Ready.”** Điểm ước lượng không chứng minh nhu cầu, quyền truy cập, phụ thuộc hoặc tiêu chí kiểm chứng đã được hiểu.

**Ngộ nhận 4: “Càng nhiều tiêu chí Ready thì chất lượng càng cao.”** Checklist dài có thể tăng chờ đợi, tạo chuyển giao và khiến nhóm ưu tiên thủ tục hơn kết quả. Chỉ giữ những câu hỏi giải quyết rủi ro thực.

**Ngộ nhận 5: “Product Owner đã đóng dấu Ready thì Developers phải nhận.”** Trong Scrum, Developers lựa chọn PBI cho Sprint khi lập kế hoạch, trao đổi với Product Owner về giá trị và khả năng Done.

**Ngộ nhận 6: “Ready đồng nghĩa Done.”** Ready nói về khả năng bắt đầu có trách nhiệm; Done nói về chất lượng của phần sản phẩm đã hoàn tất. Acceptance criteria kiểm tra hành vi đặc thù của story.

**Ngộ nhận 7: “Có DoR thì không cần trao đổi trong Sprint.”** Điều chưa biết vẫn xuất hiện khi làm việc. Agile đề cao phản hồi và cộng tác liên tục, không phải ký đóng băng một bộ yêu cầu từ đầu.

**Ngộ nhận 8: “Mọi quy định tổ chức đều là quy định Scrum.”** Bảo mật, tuân thủ và hợp đồng có thể bắt buộc theo nguồn riêng, cần thực hiện đúng nhưng phải được phân loại đúng.

**Ngộ nhận 9: “Bỏ DoR là bỏ kỷ luật.”** Nhóm không dùng thuật ngữ DoR vẫn có thể làm rõ backlog, đánh giá rủi ro, tạo Sprint Goal và đạt DoD một cách kỷ luật.

**Ngộ nhận 10: “Cần dùng cùng checklist cho tính năng, sự cố và nghiên cứu.”** Các loại công việc có mục tiêu, rủi ro và cách kiểm chứng khác nhau. Có thể chọn chính sách riêng phù hợp với từng loại.

## 13. Bài tập tình huống: “Ready gate” đang chặn backlog

Một Scrum Team phát triển nền tảng thanh toán học phí có working agreement như sau:

> “Mọi PBI phải có story point, bản thiết kế UI đã ký, đầy đủ acceptance criteria và chữ ký của hai bộ phận thì mới được đưa vào Sprint.”

Trong tuần này có ba hạng mục:

1. **A — Sửa lỗi hiển thị số tiền:** Một lỗi rõ ràng khiến người dùng hiểu nhầm phí; có thể mô tả ví dụ sai/đúng, ít phụ thuộc, nhưng không có thiết kế UI ký mới.
2. **B — Tích hợp thanh toán mới:** Có đủ user story, mockup và story point, nhưng chưa cấp quyền vào môi trường thử nghiệm và chưa quyết định quy tắc hoàn tiền.
3. **C — Tìm hiểu nguyên nhân đăng ký bỏ dở:** Chưa biết giải pháp, cần phân tích dữ liệu và quan sát người dùng trước khi tạo story chức năng.

### Câu hỏi

1. Trong working agreement trên, điều gì **không phải yêu cầu bắt buộc của Scrum**?
2. Vì sao chỉ dựa vào số dấu tích “Ready” có thể khiến nhóm chọn B thay vì A hoặc C?
3. Developers và Product Owner cần trao đổi gì tại Sprint Planning để hướng tới Sprint Goal?
4. Đề xuất một bộ **tối đa năm câu hỏi sẵn sàng**, đủ linh hoạt cho A, B và C.
5. Làm sao kiểm chứng thỏa thuận mới có cải thiện dòng công việc mà vẫn duy trì chất lượng?

### Gợi ý lời giải

**Câu 1:** Các yêu cầu về story point, chữ ký UI, đủ toàn bộ acceptance criteria và hai chữ ký trong *mọi trường hợp* không phải các điều kiện DoR bắt buộc được Scrum quy định. Nhưng nếu một yêu cầu ký duyệt đến từ quy định pháp lý hoặc tiêu chuẩn tổ chức áp dụng cho hạng mục cụ thể, nhóm vẫn phải tuân thủ nguồn ràng buộc đó.

**Câu 2:** B trông “đủ giấy tờ” nhưng có phụ thuộc có thể khiến nó không đạt DoD trong Sprint. A có thể mang giá trị và mức khẩn cao nhưng bị chặn bởi mẫu ký duyệt không phù hợp. C cần khám phá vì chưa thể dự đoán giải pháp; yêu cầu mockup đầy đủ cho C là không hợp lý. Cần ưu tiên dựa trên giá trị, rủi ro, khả năng hoàn tất và mục tiêu học hỏi, không phải vẻ hoàn chỉnh của biểu mẫu.

**Câu 3:** Product Owner trao đổi giá trị và thứ tự PBI; Developers đánh giá năng lực, phụ thuộc và khả năng Done, rồi cùng Scrum Team hình thành Sprint Goal. Nhóm có thể xem A là sửa lỗi ưu tiên, B là hạng mục cần gỡ phụ thuộc hoặc chia nhỏ, C là hoạt động khám phá với đầu ra học hỏi rõ nếu phù hợp Sprint Goal.

**Câu 4:** Bộ câu hỏi gợi ý:

- Mục tiêu của PBI là **tạo giá trị, khắc phục rủi ro hay học được điều gì**?
- Kết quả có thể **quan sát hoặc kiểm chứng** là gì?
- Công việc đã được chia đủ nhỏ để **cân nhắc hoàn thành** trong chu kỳ này chưa?
- Có phụ thuộc, quyền truy cập hoặc quy định nào có thể **chặn việc đạt DoD/kết quả nghiên cứu** không?
- Khi có câu hỏi quan trọng, **ai giúp giải đáp hoặc quyết định** và khi nào?

**Câu 5:** Thử thỏa thuận trong một vài Sprint, theo dõi việc bị chặn do thiếu thông tin, thời gian chờ phê duyệt, tỷ lệ đạt DoD, lỗi sau phát hành và phản hồi thành viên; sau đó giữ, sửa hoặc bỏ những điều kiện không có ích. Không hạ chuẩn bảo mật hoặc Definition of Done để có vẻ “giao nhanh hơn”.

## 14. Mẫu thỏa thuận và hướng dẫn áp dụng

Một nhóm có thể ghi quy ước đơn giản như sau:

> **Mục đích:** Giúp Developers và Product Owner đánh giá PBI có đủ rõ và khả thi để trao đổi khi chọn công việc, giảm tình trạng bị chặn sau khi bắt đầu.  
> **Phạm vi:** Hạng mục phát triển tính năng thông thường; sự cố khẩn, nghiên cứu và ràng buộc bắt buộc có chính sách phù hợp riêng.  
> **Câu hỏi kiểm tra:** Giá trị/mục tiêu đã rõ? Có ví dụ hoặc kết quả kiểm chứng? Hạng mục có đủ nhỏ? Phụ thuộc quan trọng đã biết và có phương án? Người quyết định có thể tiếp cận?  
> **Xử lý điều chưa rõ:** Ghi câu hỏi, mức rủi ro và phương án học hỏi; không bắt buộc mọi chi tiết được đóng băng.  
> **Ra quyết định:** Product Owner quản lý thứ tự Product Backlog; Developers đánh giá khả năng hoàn tất và lựa chọn công việc trong Sprint Planning.  
> **Không thay thế:** Definition of Done, yêu cầu pháp lý/tổ chức hoặc các thành phần thiết yếu của Scrum.  
> **Xem lại:** Tại Sprint Retrospective sau vài lần áp dụng, dựa trên việc bị chặn, dòng công việc và chất lượng.

Đây là **mẫu tham khảo để cùng chỉnh sửa**, không phải quy định áp dụng cho mọi nhóm. Thỏa thuận có thể tồn tại dưới dạng câu hỏi trong backlog refinement, chính sách của bảng công việc hoặc ghi chú nhóm. Điều quan trọng là mọi người **biết tại sao thỏa thuận tồn tại và có thể cải tiến nó**.

### Danh sách kiểm tra khi nghe ai đó nói “Scrum bắt buộc phải...”

1. **Nguồn nào quy định?** Scrum Guide, quy định tổ chức, hợp đồng hay một thói quen địa phương?
2. **Đang nói đến điều gì?** Một accountability/event/artifact/commitment, một tiêu chí hành vi, hay công cụ hỗ trợ?
3. **Nếu không làm, điều cốt lõi nào bị ảnh hưởng?** Scrum transparency, giá trị, khả năng giao Increment, tuân thủ hay chỉ thủ tục nội bộ?
4. **Có cách nhẹ hơn để đạt cùng mục đích không?** Cuộc trao đổi ngắn, ví dụ kiểm chứng hoặc chính sách luồng thay cho thêm tầng phê duyệt?
5. **Ai có quyền thay đổi?** Nhóm tự điều chỉnh được hay cần người có thẩm quyền tổ chức, pháp lý hoặc hợp đồng?
6. **Đo tác dụng thế nào?** Giảm bị chặn, giao giá trị sớm hơn, ít lỗi hơn hoặc làm rõ quyết định tốt hơn?

**Ghi nhớ:** **Definition of Ready** và các tiêu chí “sẵn sàng” có thể giúp nhóm chuẩn bị Product Backlog Item tốt hơn, nhưng **không phải yêu cầu bắt buộc của Scrum**. **Definition of Done** là commitment chính thức của Increment; Product Goal và Sprint Goal cũng là các commitment của Scrum với mục đích khác nhau. Nhóm Agile hiệu quả biết phân biệt quy tắc của framework, thỏa thuận tự chọn và ràng buộc bên ngoài; từ đó sử dụng kỷ luật phù hợp để giao phần mềm có giá trị, nhận phản hồi sớm và cải tiến liên tục.

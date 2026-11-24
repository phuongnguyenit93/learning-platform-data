# Giảm bất định bằng các vòng phản hồi ngắn

Trong phát triển phần mềm, đội ngũ hiếm khi biết chính xác ngay từ đầu người dùng cần gì, giải pháp nào khả thi nhất hoặc hệ thống sẽ vận hành ra sao trong điều kiện thực tế. **Agile giảm bất định bằng cách kiểm chứng các giả định sớm và thường xuyên**, thông qua những phần sản phẩm nhỏ có thể đánh giá được, rồi sử dụng điều học được để quyết định bước tiếp theo.

Đây là một nguyên tắc nền tảng của Agile: giao sản phẩm tăng dần, cộng tác với người liên quan và sẵn sàng điều chỉnh kế hoạch khi có hiểu biết mới. Vòng phản hồi ngắn không đồng nghĩa với việc làm gấp hay thay đổi liên tục theo mọi ý kiến. Mục tiêu là **rút ngắn khoảng thời gian từ lúc đưa ra một giả định đến lúc có bằng chứng đủ tin cậy để hành động**.

## 1. Bất định xuất hiện ở đâu?

Một yêu cầu có thể được mô tả rất chi tiết nhưng vẫn chứa nhiều điều chưa được kiểm chứng. Đội phát triển có thể hoàn thành đúng tài liệu ban đầu mà sản phẩm vẫn không đem lại giá trị như mong đợi.

| Loại bất định | Câu hỏi chưa có lời giải | Cách lấy phản hồi phù hợp |
| --- | --- | --- |
| **Nhu cầu và giá trị** | Vấn đề này có đủ quan trọng để người dùng thay đổi hành vi không? | Phỏng vấn theo tình huống thực tế, quan sát sử dụng, đo mức hoàn thành tác vụ |
| **Khả dụng và trải nghiệm** | Người dùng có hiểu và thực hiện được thao tác không? | Bản mẫu có thể thử, kiểm thử khả dụng, quan sát các điểm vướng |
| **Kỹ thuật** | Giải pháp có đáp ứng hiệu năng, bảo mật và khả năng tích hợp không? | Thử nghiệm kỹ thuật có phạm vi hẹp, kiểm thử tự động, đo hiệu năng |
| **Vận hành** | Hệ thống có ổn định và hỗ trợ được người dùng thực tế không? | Triển khai giới hạn, giám sát lỗi, nhật ký vận hành, phản hồi hỗ trợ |
| **Phối hợp và tiến độ** | Công việc đang tắc ở đâu, phụ thuộc nào làm chậm bàn giao? | Hiển thị dòng công việc, xem xét công việc đang làm, đo thời gian chờ |

**Bất định khác với công việc chưa làm.** Một tính năng chưa được lập trình nhưng có yêu cầu và kỹ thuật đã được kiểm chứng là công việc còn tồn đọng. Ngược lại, một tính năng đã lập trình xong nhưng chưa ai sử dụng có thể vẫn chứa bất định lớn về giá trị.

Những giả định có tác động lớn và chưa chắc chắn nên được kiểm chứng trước. Ví dụ, trước khi dành nhiều tuần xây hệ thống gợi ý sản phẩm, nhóm có thể thử gợi ý thủ công cho một nhóm người dùng nhỏ để xem họ có thực sự sử dụng gợi ý hay không.

## 2. Vòng phản hồi ngắn là gì?

**Vòng phản hồi (feedback loop)** là chu trình đưa ra một giả định, thực hiện một thay đổi có thể quan sát, thu thập bằng chứng và điều chỉnh quyết định. Một vòng chỉ thực sự khép kín khi kết quả quan sát **dẫn đến một quyết định**: tiếp tục, thay đổi, mở rộng, thu hẹp hoặc dừng.

~~~mermaid
flowchart LR
    A["Nêu vấn đề và giả định"] --> B["Chọn phép kiểm chứng nhỏ"]
    B --> C["Tạo và bàn giao phần có thể đánh giá"]
    C --> D["Quan sát, đo lường, hỏi người dùng"]
    D --> E{"Bằng chứng nói gì?"}
    E -->|Ủng hộ giả định| F["Tiếp tục hoặc mở rộng"]
    E -->|Bác bỏ giả định| G["Điều chỉnh hướng tiếp cận"]
    E -->|Chưa đủ rõ| H["Thiết kế phép kiểm chứng tiếp theo"]
    F --> A
    G --> A
    H --> A
~~~

Chu trình này thường được diễn đạt bằng các hoạt động **xây dựng – đo lường – học hỏi**. Trong thực hành Agile, “xây dựng” không nhất thiết là viết mã: nó có thể là bản mẫu giao diện, một thử nghiệm tích hợp, bài kiểm thử, bản trình diễn hoặc một phần chức năng đã sử dụng được.

### Vì sao nên rút ngắn vòng phản hồi?

1. **Phát hiện sai giả định khi chi phí thay đổi còn thấp.** Sửa một luồng trên bản mẫu thường dễ hơn sửa cùng luồng sau khi đã mở rộng sang nhiều dịch vụ.
2. **Giảm số quyết định nối tiếp dựa trên một giả định chưa đúng.** Nếu chờ đến cuối dự án mới xác nhận cách người dùng thanh toán, nhiều tính năng phụ thuộc có thể phải làm lại.
3. **Tạo cơ hội điều chỉnh ưu tiên.** Backlog được cập nhật bằng điều vừa học, thay vì chỉ hoàn thành tuần tự các hạng mục được viết từ nhiều tháng trước.
4. **Làm lộ sớm trở ngại kỹ thuật và phối hợp.** Tích hợp và kiểm thử thường xuyên giúp nhìn thấy lỗi, nút thắt và phụ thuộc khi phạm vi vẫn còn nhỏ.

Tuy nhiên, **phản hồi nhanh chưa chắc là phản hồi tốt**. Ý kiến từ một người không đại diện, số liệu quá ít hoặc tín hiệu được đo sai có thể dẫn đến kết luận sai nhanh hơn. Vì vậy, cần đồng thời quan tâm đến tốc độ, chất lượng và cách diễn giải bằng chứng.

## 3. Thiết kế một vòng phản hồi có giá trị

### Bước 1 — Diễn đạt điều cần học dưới dạng giả định có thể kiểm chứng

Thay vì bắt đầu bằng “phải xây màn hình X”, hãy xác định:

- **Vấn đề:** Ai đang gặp khó khăn, trong bối cảnh nào?
- **Giả định:** Nếu thay đổi điều gì thì hành vi hoặc kết quả nào sẽ cải thiện?
- **Bằng chứng:** Cần quan sát gì để biết giả định có được ủng hộ?
- **Giới hạn:** Phản hồi được lấy từ ai, trong bao lâu và khi nào cần xem xét lại?

Ví dụ: “Người mua mới thường bỏ quá trình thanh toán vì phí vận chuyển xuất hiện quá muộn. Nếu hiển thị phí ước tính sớm hơn, nhiều người sẽ hoàn thành thanh toán hơn.” Đây là **giả thuyết cần kiểm chứng**, chưa phải một sự thật đã được xác nhận.

### Bước 2 — Chọn phần bàn giao nhỏ nhất có thể trả lời câu hỏi

Chia công việc theo **lát cắt giá trị từ đầu đến cuối (vertical slice)**: người dùng có thể thực hiện một hành động có ý nghĩa trên phần mềm đang hoạt động. Tránh chỉ chia theo lớp kỹ thuật như “xong database”, “xong API”, “xong giao diện” nếu từng phần riêng lẻ không tạo ra phản hồi về hành vi thực tế.

Một lát cắt tốt thường có:

- Một nhóm người dùng và tình huống cụ thể.
- Một luồng sử dụng đủ hoàn chỉnh để quan sát.
- Tiêu chí chấp nhận rõ ràng, có thể kiểm thử.
- Cách thu thập phản hồi và một thời điểm xem xét kết quả.

“Nhỏ nhất” không có nghĩa là bỏ qua tính an toàn, bảo mật, khả năng truy cập hoặc chất lượng cần thiết. Phần bàn giao vẫn phải đáp ứng tiêu chuẩn hoàn thành (Definition of Done) phù hợp trước khi đến tay người dùng.

### Bước 3 — Đưa thay đổi tới đúng nơi có thể thu được bằng chứng

Tùy câu hỏi, nơi kiểm chứng có thể là:

| Điều muốn học | Hình thức kiểm chứng | Hạn chế cần nhớ |
| --- | --- | --- |
| Người dùng có hiểu bước thao tác không? | Cho người dùng thử bản mẫu và quan sát | Bản mẫu không chứng minh được độ ổn định khi vận hành |
| Giải pháp có tích hợp được không? | Thử nghiệm kỹ thuật, kiểm thử hợp đồng API | Tích hợp thành công chưa chứng minh nhu cầu thị trường |
| Luồng mới có cải thiện kết quả không? | Phát hành giới hạn, đo hành vi hoặc thử nghiệm đối chứng | Cần lưu lượng và thời gian quan sát đủ phù hợp |
| Nhóm có bàn giao đều đặn không? | Theo dõi bảng Kanban, thời gian chờ và thời gian hoàn tất | Dòng công việc tốt chưa đồng nghĩa với giá trị người dùng |

### Bước 4 — Thu thập cả tín hiệu định tính và định lượng

- **Định tính:** Người dùng giải thích mục đích, bộc lộ khó khăn ở bước nào, vì sao họ không tin tưởng hoặc không dùng tính năng.
- **Định lượng:** Tỷ lệ hoàn thành tác vụ, lỗi phát sinh, độ trễ, số người thực sự sử dụng, thời gian hoàn thành một luồng.
- **Tín hiệu kỹ thuật:** Kết quả kiểm thử, thời gian build, lỗi tích hợp, tỷ lệ thay đổi gây sự cố.
- **Tín hiệu dòng công việc:** Công việc tồn đọng, thời gian bị chặn, thời gian từ bắt đầu đến hoàn thành.

Số liệu giúp biết **điều gì đang xảy ra**; quan sát và trao đổi thường giúp hiểu **vì sao**. Cần đặt ngữ cảnh cho dữ liệu: số lượng mẫu, nhóm người dùng, khoảng thời gian, khác biệt theo thiết bị và các thay đổi diễn ra đồng thời.

### Bước 5 — Ra quyết định và cập nhật backlog

Sau khi xem xét bằng chứng, nhóm ghi rõ quyết định và lý do:

- **Tiếp tục** nếu kết quả ủng hộ giả định và rủi ro còn chấp nhận được.
- **Điều chỉnh** nếu phát hiện nhu cầu đúng nhưng cách giải quyết chưa hiệu quả.
- **Kiểm chứng thêm** nếu bằng chứng ít, nhiễu hoặc mâu thuẫn.
- **Dừng** nếu giả định quan trọng bị bác bỏ hoặc chi phí không tương xứng với giá trị.

Phản hồi chỉ tạo ra học hỏi có ích khi ảnh hưởng đến ưu tiên, thiết kế, tiêu chí chấp nhận hoặc cách làm việc ở vòng sau. Lưu một ghi chú ngắn về “giả định – bằng chứng – quyết định – việc tiếp theo” giúp tránh việc tranh luận lại từ đầu.

## 4. Ví dụ xuyên suốt: giảm bỏ dở thanh toán

Giả sử một nhóm phát triển ứng dụng thương mại điện tử phát hiện nhiều người rời đi khi vào trang thanh toán. Nhóm chưa biết nguyên nhân thực sự.

### 4.1. Từ triệu chứng đến user story

Nhóm quan sát dữ liệu hành trình và trò chuyện với một số người mua. Một khả năng được nêu ra: phí giao hàng chỉ được hiển thị tại bước cuối nên người dùng bất ngờ.

**User story:**

> Là người mua hàng lần đầu, tôi muốn nhìn thấy phí giao hàng ước tính trước khi xác nhận đơn, để có thể quyết định mua với tổng chi phí rõ ràng.

**Tiêu chí chấp nhận mẫu:**

1. Khi có địa chỉ giao hàng đủ thông tin, màn hình hiển thị chi phí giao hàng ước tính và tổng tiền dự kiến.
2. Nếu hệ thống chưa thể ước tính phí, giao diện thông báo rõ thay vì hiển thị số không chính xác.
3. Người mua được xem lại tổng tiền trước khi xác nhận đơn.
4. Luồng chính hoạt động trên màn hình di động và có kiểm thử cho các trường hợp hợp lệ, thiếu địa chỉ và lỗi dịch vụ tính phí.

Lưu ý: user story mô tả **nhu cầu**; tiêu chí chấp nhận mô tả **điều kiện để phần chức năng hoạt động đúng**. Cả hai chưa thay thế được việc đo xem tính năng có giải quyết vấn đề kinh doanh hay không.

### 4.2. Chọn thay đổi nhỏ và chỉ số quan sát

Nhóm không cần viết lại toàn bộ hệ thống thanh toán. Lát cắt đầu tiên có thể chỉ hiển thị phí ước tính từ dịch vụ hiện có tại thời điểm người dùng nhập địa chỉ. Nếu chức năng mới đủ an toàn để thử trên một phần lưu lượng, nhóm có thể triển khai có kiểm soát.

| Thành phần | Thiết kế vòng kiểm chứng đầu tiên |
| --- | --- |
| Giả định | Hiển thị phí sớm làm giảm việc bỏ dở do bất ngờ về chi phí |
| Thay đổi | Thêm thông tin phí ước tính và tổng dự kiến trong một bước hiện có |
| Người quan sát | Người mua mới hoàn tất bước nhập địa chỉ |
| Tín hiệu chính | Tỷ lệ hoàn thành thanh toán của nhóm được quan sát |
| Tín hiệu bổ sung | Số lỗi báo phí, phản hồi người dùng, thời gian thao tác, lượt liên hệ hỗ trợ |
| Quyết định tiếp theo | Giữ, sửa cách hiển thị, kiểm chứng nguyên nhân khác hoặc dừng |

Ví dụ, nếu tỷ lệ hoàn thành thanh toán tăng trong một đợt thử nghiệm nhỏ thì đó là **tín hiệu khích lệ**, chưa mặc nhiên chứng minh nguyên nhân. Giá khuyến mãi, nguồn truy cập, mùa mua sắm và quy mô mẫu đều có thể ảnh hưởng kết quả. Khi điều kiện phù hợp, dùng nhóm đối chứng hoặc cách so sánh đáng tin cậy để đánh giá tác động.

### 4.3. Diễn biến của các vòng tiếp theo

**Vòng 1 — Kiểm tra khả dụng:** Người mua thử bản mẫu. Nhiều người hiểu tổng tiền, nhưng một số nhầm “phí ước tính” với “phí cuối cùng”. Nhóm điều chỉnh nhãn và giải thích thời điểm xác định phí chính thức.

**Vòng 2 — Kiểm tra kỹ thuật:** Nhóm tích hợp với dịch vụ tính phí và chạy kiểm thử tự động. Dữ liệu cho thấy dịch vụ phản hồi chậm ở một số địa chỉ. Nhóm bổ sung trạng thái đang tính và phương án xử lý lỗi trước khi phát hành.

**Vòng 3 — Kiểm tra giá trị:** Nhóm phát hành giới hạn, quan sát kết quả hoàn thành thanh toán và phỏng vấn các trường hợp bỏ dở. Nếu bằng chứng chỉ ra phí vận chuyển cao mới là nguyên nhân chính, nhóm chuyển ưu tiên sang cách cung cấp lựa chọn giao hàng phù hợp, thay vì tiếp tục tối ưu màn hình.

Mỗi vòng trả lời một câu hỏi khác nhau. Thời gian hoàn thành một vòng chỉ hữu ích nếu câu hỏi được xác định rõ và cách thu nhận bằng chứng phù hợp.

## 5. Vòng phản hồi tồn tại ở nhiều cấp độ

Không có một độ dài vòng phản hồi đúng cho mọi tình huống. Một lỗi lập trình có thể được phát hiện trong vài phút, trong khi thay đổi về thói quen sử dụng có thể cần nhiều tuần để xuất hiện rõ.

| Cấp độ | Vòng phản hồi tiêu biểu | Điều có thể điều chỉnh |
| --- | --- | --- |
| **Cá nhân / kỹ thuật** | Viết kiểm thử, chạy kiểm thử, lập trình cặp, xem xét mã | Cách triển khai, lỗi logic, thiết kế mã |
| **Tích hợp / bàn giao** | Tích hợp liên tục (CI), kiểm thử tích hợp, triển khai thử | Lỗi tương thích, chất lượng bản build, khả năng phát hành |
| **Nhóm** | Họp phối hợp hằng ngày, quan sát luồng công việc, review phần đã hoàn thành | Phân công, công việc bị chặn, thứ tự ưu tiên ngắn hạn |
| **Sản phẩm** | Sprint Review, thử nghiệm khả dụng, phát hành tăng dần, quan sát chỉ số sử dụng | Backlog, thiết kế tính năng, giả định về giá trị |
| **Cách làm việc** | Retrospective, phân tích sự cố, cải tiến quy trình | Quy tắc phối hợp, chất lượng, tốc độ nhận phản hồi |

Một số thực hành Agile hỗ trợ các vòng trên theo những cách khác nhau:

- **Scrum:** Sprint tạo nhịp tạo Increment; Sprint Review là cơ hội xem sản phẩm cùng stakeholder và điều chỉnh Product Backlog; Sprint Retrospective tạo vòng phản hồi về cách nhóm làm việc. Sprint Review không nên chỉ là buổi báo cáo tiến độ.
- **Kanban:** Trực quan hóa công việc, giới hạn công việc đang làm (WIP), chủ động xử lý các mục bị chặn và theo dõi thời gian hoàn tất giúp phát hiện chậm trễ liên tục, không phải đợi hết Sprint.
- **Extreme Programming (XP):** Kiểm thử tự động, phát triển hướng kiểm thử (TDD), lập trình cặp, tái cấu trúc và tích hợp liên tục rút ngắn phản hồi kỹ thuật, giúp nhóm thay đổi sản phẩm với ít rủi ro hơn.

Các cách làm có thể kết hợp theo bối cảnh. Ví dụ, một nhóm dùng nhịp Sprint để trao đổi với stakeholder, bảng Kanban để quan sát dòng công việc và CI để nhận phản hồi kỹ thuật mỗi lần cập nhật mã. Việc tổ chức nghi thức không tự động tạo ra học hỏi; nhóm vẫn cần đưa bằng chứng vào quyết định.

## 6. Đo thời gian phản hồi và chất lượng học hỏi

Không nên chỉ đếm số buổi họp, số bản phát hành hay số user story hoàn thành. Đó là các chỉ dấu hoạt động, không trực tiếp chứng minh giá trị. Hãy kết hợp chỉ số về **tốc độ nhận phản hồi**, **khả năng bàn giao** và **kết quả sản phẩm**.

| Chỉ số | Hiểu và sử dụng như thế nào | Ngộ nhận thường gặp |
| --- | --- | --- |
| **Time to feedback** (thời gian tới phản hồi) | Khoảng thời gian từ khi nêu giả định hoặc đưa thay đổi ra kiểm chứng đến khi có bằng chứng sử dụng được | Có phản hồi nhanh nghĩa là đã có đủ dữ liệu để kết luận |
| **Lead time** | Thời gian từ khi yêu cầu được tiếp nhận theo quy ước của nhóm đến khi bàn giao; cần thống nhất mốc đầu/cuối | Mọi đội đều dùng cùng một cách tính |
| **Cycle time** | Thời gian từ lúc bắt đầu thực hiện một hạng mục đến khi hoàn tất theo quy ước | Giảm thời gian bằng cách bỏ qua kiểm thử là cải tiến |
| **WIP** (work in progress) | Số việc đang được thực hiện cùng lúc; WIP quá cao thường tăng chờ đợi và chuyển ngữ cảnh | Càng nhiều việc được mở thì nhóm càng hiệu quả |
| **Tỷ lệ lỗi lọt ra môi trường sử dụng** | Tín hiệu về chất lượng của các phần bàn giao và khả năng phát hiện lỗi sớm | Số lỗi ít luôn đồng nghĩa với chất lượng cao, bất kể quy mô người dùng |
| **Chỉ số kết quả** | Mức hoàn thành tác vụ, tỷ lệ sử dụng thực, thời gian người dùng đạt mục tiêu, mức hài lòng trong đúng bối cảnh | Số tính năng đã phát hành bằng giá trị sản phẩm |

Ví dụ, một story bắt đầu làm sáng thứ Hai và hoàn thành chiều thứ Năm có cycle time gần bốn ngày theo lịch làm việc của nhóm. Nhưng nếu phải chờ thêm hai tuần mới có phản hồi từ người dùng, **vòng học hỏi về giá trị** vẫn dài. Vì vậy, rút ngắn cycle time là hữu ích nhưng chưa đủ.

Khi diễn giải số liệu, nên quan sát **xu hướng qua nhiều hạng mục**, độ biến động và các điểm chờ lớn; tránh dùng một con số đơn lẻ để đánh giá cá nhân. Đội ngũ có thể giao đều mỗi tuần nhưng vẫn đang giải quyết sai vấn đề.

## 7. Cách làm vòng phản hồi ngắn mà vẫn bền vững

### Duy trì chất lượng ở mỗi phần bàn giao

Kiểm thử tự động, code review phù hợp, tích hợp thường xuyên và tiêu chí hoàn thành minh bạch giúp rút ngắn vòng phát hiện lỗi. Nếu mỗi lần thử nghiệm đều làm hỏng luồng cũ, nhóm sẽ dành thời gian khắc phục sự cố thay vì học hỏi về sản phẩm.

### Hạn chế công việc đang làm

Khi mọi người đồng thời xử lý quá nhiều story, thời gian chờ giữa các bước phân tích, phát triển, kiểm thử và phản hồi tăng lên. Giới hạn WIP, hỗ trợ hoàn tất công việc gần xong và tháo gỡ phụ thuộc giúp phần sản phẩm có thể đánh giá đến tay người dùng sớm hơn.

### Gắn vòng phản hồi với quyết định

Một buổi demo chỉ hữu ích khi có người phù hợp tham gia, có tiêu chí quan sát và có quyền hoặc đường dẫn rõ ràng để điều chỉnh backlog. Trước mỗi vòng, cần biết ai sẽ xem kết quả, khi nào xem và có thể thay đổi quyết định gì.

### Phân biệt phản hồi với yêu cầu mới

Người dùng có thể đề xuất một chức năng cụ thể, nhưng nhu cầu ẩn phía sau có thể được giải quyết đơn giản hơn. Hãy hỏi tình huống gặp vấn đề, tác động và cách họ đang xoay xở. Kiểm chứng vấn đề trước khi biến mọi đề xuất thành hạng mục phát triển.

### Chọn đúng cỡ thử nghiệm và thời gian quan sát

Vòng phản hồi kỹ thuật thường ngắn vì phép kiểm chứng rõ ràng. Với hành vi người dùng, cần đủ thời gian để họ tiếp cận tính năng và đủ dữ liệu để tránh nhiễu. Rút ngắn thời gian chờ không có nghĩa là ép mọi kết luận phải xuất hiện sau một ngày.

## 8. Những cách làm khiến vòng phản hồi mất tác dụng

| Dấu hiệu | Hệ quả | Điều chỉnh |
| --- | --- | --- |
| Chỉ nhận phản hồi khi toàn bộ dự án kết thúc | Sai lệch về nhu cầu được phát hiện muộn | Chia theo những khả năng người dùng có thể thử sớm |
| Demo màn hình nhưng chưa có luồng sử dụng hoàn chỉnh | Dễ nhận xét về giao diện, khó kiểm chứng giá trị | Đưa ra tác vụ cụ thể để người xem thực hiện |
| Stakeholder chỉ xem tiến độ và số việc hoàn tất | Không trả lời được người dùng có hưởng lợi không | Bổ sung dữ liệu hành vi và câu hỏi cần quyết định |
| Nhóm thu thập nhiều ý kiến nhưng không cập nhật backlog | Học hỏi bị ngắt trước bước hành động | Chốt quyết định, người phụ trách và vòng kiểm chứng kế tiếp |
| Thấy một phản hồi tiêu cực thì lập tức đảo hướng | Quyết định bị chi phối bởi mẫu nhỏ hoặc ý kiến mạnh | Kiểm tra tính đại diện, đối chiếu nhiều nguồn bằng chứng |
| Bàn giao nhanh bằng cách bỏ kiểm thử và tiêu chuẩn hoàn thành | Tích lũy lỗi và nợ kỹ thuật, vòng sau chậm đi | Giữ mức chất lượng cần thiết, tự động hóa kiểm tra lặp lại |
| Tối ưu velocity hoặc số story thay cho kết quả | Có nhiều đầu ra nhưng không chắc tạo giá trị | Theo dõi một số chỉ số kết quả gắn với vấn đề người dùng |

## 9. Thực hành áp dụng cho một nhóm Agile

Một nhóm có thể thử cách làm sau trong hai tuần, tùy quy mô công việc và thời gian tiếp cận người dùng:

1. **Đầu kỳ:** Chọn một bất định đáng kể trong Product Backlog, nêu rõ giả định, người dùng mục tiêu và tín hiệu cần quan sát. Ưu tiên giả định có tác động lớn hoặc có thể gây làm lại nhiều nếu sai.
2. **Trong kỳ:** Chia một hạng mục thành lát cắt đủ nhỏ, thống nhất tiêu chí chấp nhận và Definition of Done. Thực hiện kiểm thử và tích hợp liên tục để nhận phản hồi kỹ thuật.
3. **Khi có phần sử dụng được:** Đưa đến đúng nhóm người dùng hoặc stakeholder, quan sát thao tác thay vì chỉ hỏi “có thích không?”. Ghi lại dữ liệu, bối cảnh và ý kiến bất đồng.
4. **Cuối kỳ:** Đối chiếu kết quả với giả định ban đầu. Ghi quyết định và cập nhật thứ tự backlog. Nếu chưa đủ bằng chứng, xác định rõ câu hỏi cần học ở vòng tới.
5. **Retrospective:** Xem vòng nào mất thời gian nhất: chờ thiết kế, chờ kiểm thử, chờ triển khai hay chờ người phản hồi. Chọn một điều chỉnh quy trình nhỏ và theo dõi hiệu quả ở kỳ kế tiếp.

Nhóm có thể lưu một bản ghi học hỏi rất ngắn:

| Trường | Ví dụ |
| --- | --- |
| Giả định | Người dùng bỏ thanh toán vì không biết phí giao hàng từ sớm |
| Phép kiểm chứng | Thử màn hình hiển thị phí ước tính và phát hành giới hạn |
| Bằng chứng | Quan sát sử dụng, tỷ lệ hoàn thành thanh toán, lỗi tính phí |
| Giới hạn | Mẫu thử ít; hiệu ứng chương trình khuyến mãi chưa được tách riêng |
| Quyết định | Tiếp tục đo có đối chứng; sửa thông điệp về phí ước tính |
| Việc tiếp theo | Cập nhật backlog và xác định tiêu chí cho vòng kế tiếp |

### Câu hỏi tự kiểm tra

1. Hạng mục đang làm nhằm giải quyết vấn đề nào, và điều gì vẫn chỉ là giả định?
2. Phần nhỏ nhất có thể bàn giao để kiểm chứng giả định là gì?
3. Ai sẽ cung cấp phản hồi, qua kênh nào và vào thời điểm nào?
4. Nhóm cần bằng chứng kỹ thuật, bằng chứng từ hành vi người dùng hay cả hai?
5. Nếu bằng chứng trái dự đoán, quyết định nào sẽ thay đổi?
6. Điều gì đang khiến thời gian từ khi bắt đầu làm đến khi học được điều mới kéo dài?

**Ghi nhớ:** Giá trị của một vòng phản hồi nằm ở **quyết định tốt hơn sau mỗi lần học**. Agile trở nên thích ứng khi đội ngũ liên tục giao những phần sản phẩm đủ nhỏ để kiểm chứng, quan sát bằng chứng thực tế và điều chỉnh hướng đi — đồng thời bảo đảm chất lượng để các vòng tiếp theo vẫn diễn ra nhanh và an toàn.

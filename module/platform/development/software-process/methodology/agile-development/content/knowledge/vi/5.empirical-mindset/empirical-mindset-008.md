# Tránh biến nghi thức và chỉ số thành mục tiêu tự thân trong Agile

> **Thông điệp chính:** Scrum, Kanban, XP, các cuộc họp, bảng công việc và chỉ số đều là **phương tiện giúp nhóm tạo giá trị và học hỏi từ thực tế**. Khi nhóm chỉ cố “làm đúng nghi thức” hoặc “đạt con số đẹp”, phương tiện có thể thay thế mục tiêu. Tư duy thực nghiệm đưa sự chú ý trở lại câu hỏi: *Chúng ta đã học được gì, đã giao được giá trị nào, và cần điều chỉnh điều gì tiếp theo?*

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận biết sự khác biệt giữa **tuân thủ một hoạt động Agile** và **đạt mục đích mà hoạt động đó phục vụ**.
2. Giải thích vì sao **minh bạch, kiểm tra và thích ứng** là cốt lõi của cách làm thực nghiệm, còn nghi thức và chỉ số chỉ có ích khi hỗ trợ chu trình này.
3. Nhận diện các kiểu lệch hướng: họp chỉ để có họp, hoàn thành ticket để tăng số lượng, nâng story point để tăng velocity hoặc làm báo cáo đẹp nhưng sản phẩm không tốt lên.
4. Sử dụng các chỉ số của **dòng công việc, chất lượng và giá trị sản phẩm** để tìm vấn đề, kiểm chứng giả thuyết và đưa ra quyết định.
5. Thiết kế một thử nghiệm cải tiến nhỏ cho nhóm dùng Scrum, Kanban hoặc XP, có mục tiêu, tín hiệu quan sát và điều kiện đánh giá rõ ràng.

## 2. Vấn đề: khi phương tiện bị nhầm thành mục tiêu

Giả sử hai nhóm cùng phát triển phần mềm bán hàng.

**Nhóm A** duy trì Daily Scrum, Sprint Review, Sprint Retrospective, bảng công việc và biểu đồ velocity. Báo cáo tuần nào cũng có số story point “hoàn thành” tăng. Nhưng lỗi vẫn lọt sang môi trường thật, yêu cầu người dùng vẫn bị hiểu nhầm và những đề xuất cải tiến từ retrospective hiếm khi được thực hiện.

**Nhóm B** cũng làm việc theo một nhịp rõ ràng, nhưng luôn đặt câu hỏi: “Sprint Goal có tiến triển không?”, “Phần mềm vừa giao có giải quyết vấn đề khách hàng không?”, “Công việc bị chặn ở đâu?”, “Giả thuyết cải tiến tuần trước có tạo tác động không?”. Khi phát hiện cuộc họp chưa hiệu quả, nhóm thay đổi cách chuẩn bị và điều phối; khi thấy nhiều lỗi xuất hiện, nhóm điều chỉnh cách chia việc và kiểm thử.

Nhóm A có vẻ **tuân thủ nhiều dấu hiệu bên ngoài của Agile**; nhóm B thể hiện rõ hơn **tư duy kiểm tra thực tế và thích ứng**. Điều quan trọng không phải số cuộc họp, số cột trên bảng hay biểu đồ trông như thế nào, mà là những hoạt động đó giúp nhóm giao sản phẩm có ích, giảm rủi ro và cải tiến ra sao.

Đây cũng là bẫy thường gặp trong quản trị: khi một thước đo được dùng làm mục tiêu thưởng/phạt trực tiếp, mọi người có động cơ tối ưu điểm số, đôi khi làm mất ý nghĩa ban đầu của thước đo. Hiện tượng này thường được diễn đạt qua **định luật Goodhart**: một chỉ số có thể mất chất lượng như một phép đo khi bị biến thành mục tiêu cần tối đa hóa.

**Ví dụ:** nếu chỉ đánh giá nhóm bằng số ticket đã đóng, một số người có thể chia công việc thành nhiều ticket rất nhỏ để có số lượng cao hơn, trong khi trải nghiệm khách hàng không thay đổi. Việc chia nhỏ công việc vốn có thể rất tốt; vấn đề nằm ở **lý do và tác động** của nó.

## 3. Tư duy thực nghiệm là gì?

**Tư duy thực nghiệm (empirical mindset)** có nghĩa là giảm lệ thuộc vào giả định chưa kiểm chứng và dùng bằng chứng từ sản phẩm, người dùng và quy trình làm việc để ra quyết định. Không phải mọi quyết định đều cần một thí nghiệm thống kê; nhưng nhóm cần phân biệt điều **đã quan sát**, điều **đang giả định** và điều **chưa biết**.

Scrum dựa trên ba trụ cột thực nghiệm:

| Trụ cột | Câu hỏi cần trả lời | Hành vi minh họa |
|---|---|---|
| **Minh bạch (Transparency)** | “Mọi người có cùng nhìn đúng trạng thái và tiêu chuẩn công việc không?” | Một mục chỉ được coi là hoàn thành khi đáp ứng Definition of Done; rủi ro và việc bị chặn được hiển thị rõ |
| **Kiểm tra (Inspection)** | “Kết quả thực tế khác kỳ vọng ở đâu?” | Kiểm tra Increment với bên liên quan, xem xu hướng cycle time, phân tích lỗi tái diễn |
| **Thích ứng (Adaptation)** | “Từ những gì vừa học, ta sẽ thay đổi quyết định hoặc cách làm nào?” | Đổi thứ tự backlog, chia nhỏ user story, điều chỉnh chính sách WIP, bổ sung kiểm thử thiết yếu |

Ba phần phụ thuộc lẫn nhau:

- **Minh bạch thiếu kiểm tra:** dữ liệu được cập nhật đều nhưng không ai dùng để đặt câu hỏi.
- **Kiểm tra thiếu thích ứng:** cuộc họp nêu nhiều vấn đề nhưng mọi thứ vẫn diễn ra như cũ.
- **Thích ứng thiếu minh bạch:** nhóm thay đổi theo cảm giác, khó biết nguyên nhân và kết quả.

### Vòng lặp học hỏi ngắn

~~~mermaid
flowchart TD
    A["Nêu vấn đề và kết quả mong muốn"] --> B["Phát biểu giả thuyết"]
    B --> C["Chọn thay đổi nhỏ và cách đo"]
    C --> D["Thực hiện trong phạm vi kiểm soát"]
    D --> E["Quan sát kết quả và rủi ro"]
    E --> F{"Bằng chứng cho thấy gì?"}
    F -->|"Có tác dụng"| G["Duy trì hoặc mở rộng có kiểm soát"]
    F -->|"Chưa đủ dữ liệu"| H["Thu thập thêm / điều chỉnh phép đo"]
    F -->|"Không có tác dụng"| I["Đổi hoặc dừng cách làm"]
    G --> J["Đặt câu hỏi tiếp theo"]
    H --> J
    I --> J
    J --> A
~~~

Một hoạt động chỉ thật sự tạo giá trị khi nó giúp nhóm đi qua ít nhất một phần của chu trình này. Ví dụ, retrospective không kết thúc ở việc “mọi người đã chia sẻ”; giá trị nằm ở **một thay đổi có chủ đích** và việc kiểm tra thay đổi ấy ở vòng tiếp theo.

## 4. Phân biệt mục đích, cơ chế và chỉ số

Để tránh nhầm lẫn, hãy tách ba tầng:

| Tầng | Định nghĩa | Ví dụ |
|---|---|---|
| **Kết quả mong muốn (outcome)** | Điều có ý nghĩa với người dùng hoặc hệ thống sản phẩm | Tỷ lệ kích hoạt tài khoản tăng; lỗi thanh toán giảm; khách hàng hoàn tất đơn dễ hơn |
| **Cơ chế/thực hành (practice)** | Cách nhóm phối hợp và kiểm chứng để đạt outcome | Sprint Review, giới hạn WIP, TDD, kiểm thử tích hợp, phỏng vấn người dùng |
| **Tín hiệu/chỉ số (signal/metric)** | Thông tin giúp xem cơ chế có đang tạo kết quả và rủi ro nào không | Cycle time, lỗi lọt môi trường thật, số người kích hoạt thành công, tỷ lệ bỏ dở |

**Output** là lượng việc hoặc sản phẩm trung gian đã tạo ra, chẳng hạn “đã triển khai 7 màn hình”, “đã hoàn thành 18 ticket”, “đã viết 40 kiểm thử”. **Outcome** là tác động cần thiết, chẳng hạn “người dùng tìm được đơn nhanh hơn” hoặc “tỷ lệ thanh toán thành công cao hơn”. Output có thể là điều kiện để tạo outcome, nhưng hai khái niệm không đồng nhất.

Ví dụ: nhóm xây 5 bộ lọc tìm kiếm (output) nhưng người dùng không dùng chúng và thời gian tìm sản phẩm không giảm. Việc giao đủ 5 bộ lọc chưa chứng minh tính năng có giá trị. Cần xem kết quả thực tế, chất lượng và chi phí duy trì.

**Câu hỏi kiểm tra nhanh:** “Nếu nhóm đạt chỉ số này ở mức rất cao mà người dùng vẫn không hài lòng, chúng ta có xem đó là thành công không?” Nếu câu trả lời là *không*, chỉ số đó phải được xem như **tín hiệu hỗ trợ**, không phải đích cuối.

## 5. Khi nghi thức Agile trở thành hình thức

Trong Scrum, các sự kiện có mục đích rõ và được thiết kế để tạo cơ hội kiểm tra, thích ứng. **Sprint** là vùng chứa các sự kiện khác; Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective giúp nhóm thường xuyên điều chỉnh hướng đi.

Khi dùng Scrum, không nên tùy tiện bỏ các sự kiện cốt lõi rồi vẫn khẳng định đang áp dụng đầy đủ Scrum. Tuy nhiên, nhóm được và nên **cải tiến cách chuẩn bị, cách thảo luận và mức tập trung vào mục đích** trong khuôn khổ Scrum. Nếu không dùng Scrum đầy đủ, tổ chức có thể lựa chọn cách làm khác nhưng cần mô tả chính xác cách đang áp dụng.

| Sự kiện/thực hành | Mục đích thực sự | Dấu hiệu bị nghi thức hóa | Cách đưa về đúng mục đích |
|---|---|---|---|
| **Sprint Planning** | Thống nhất vì sao Sprint có giá trị, chọn việc và lập kế hoạch đạt Sprint Goal | Chỉ “nhét đủ điểm” theo capacity; không ai diễn đạt được Sprint Goal | Bắt đầu bằng outcome và rủi ro; xây kế hoạch khả thi và linh hoạt |
| **Daily Scrum** | Developers kiểm tra tiến độ tới Sprint Goal, điều chỉnh kế hoạch trong ngày | Lần lượt báo cáo cho quản lý; mỗi người đọc lại ticket | Tập trung việc cần phối hợp, nguy cơ không đạt mục tiêu và điều chỉnh kế hoạch |
| **Sprint Review** | Kiểm tra Increment cùng bên liên quan, học từ phản hồi và điều chỉnh hướng đi | Chỉ trình chiếu slide, đếm tính năng hoàn thành; không có thảo luận | Dùng sản phẩm hoạt động được, trao đổi về thay đổi của bối cảnh và Product Backlog |
| **Sprint Retrospective** | Cải tiến chất lượng và hiệu quả cách làm | Ghi hàng chục “action item” nhưng không theo dõi | Chọn một hoặc hai thay đổi khả thi, theo dõi tác động ở Sprint tiếp theo |
| **Backlog refinement** | Làm các mục backlog rõ và nhỏ vừa đủ để sẵn sàng lập kế hoạch | Chuẩn hóa mọi story thật chi tiết nhiều tháng trước | Làm rõ mục gần, kiểm chứng giả định và không tạo tài liệu quá sớm |
| **Kanban board** | Nhìn thấy dòng công việc và điểm bị chặn | Di chuyển thẻ cho đẹp cuối tuần; công việc thật không phản ánh | Cập nhật trạng thái sát thực tế; làm rõ chính sách kéo việc và giới hạn WIP |
| **Pair programming / code review** | Chia sẻ hiểu biết, phát hiện lỗi, cải thiện thiết kế | “Ngồi đôi” hoặc chấp thuận PR theo chỉ tiêu mà không trao đổi | Tập trung vào rủi ro, chất lượng phản hồi và phần mã cần được hiểu chung |

**Lưu ý:** backlog refinement là hoạt động diễn ra liên tục khi cần, không phải một trong các sự kiện Scrum được quy định như Sprint Review hay Daily Scrum.

### 5.1. Daily Scrum không phải bảng chấm công bằng lời

Một Daily Scrum trở nên kém hiệu quả khi từng người chỉ trả lời ba câu “hôm qua làm gì, hôm nay làm gì, có vướng gì không” như một báo cáo cho cấp trên. Mẫu ba câu hỏi có thể hữu ích trong một số nhóm, nhưng **không phải công thức bắt buộc của Scrum Guide**.

Ví dụ đối thoại tập trung vào mục tiêu:

> “Sprint Goal là người mua có thể tự đổi địa chỉ trước khi đơn bàn giao vận chuyển. Phần kiểm thử tích hợp đang bị chặn vì trạng thái đơn hàng từ hệ thống kho chưa thống nhất. Hôm nay cần Developer và người phụ trách tích hợp cùng kiểm tra luồng đó trước khi nhận thêm story khác.”

Sau buổi trao đổi, nhóm có việc cần làm cụ thể. Nếu cuộc họp kết thúc mà mọi người vẫn thiếu thông tin, cần xem lại cấu trúc thảo luận.

### 5.2. Sprint Review không phải buổi công bố thành tích

Review có giá trị khi một Increment được kiểm tra trong bối cảnh nhu cầu thay đổi. Ví dụ:

> Nhóm trình diễn tính năng đăng ký và phát hiện tỷ lệ người dùng bỏ dở vẫn cao ở bước xác thực email. Thay vì chỉ ghi nhận “đã xong giao diện đăng ký”, Product Owner và các bên liên quan cùng thảo luận việc nghiên cứu email thất lạc và ưu tiên lại backlog.

Một buổi demo suôn sẻ nhưng không có trao đổi về điều vừa học có thể thiếu phần quan trọng nhất của Sprint Review.

### 5.3. Retrospective cần hành động nhỏ và kiểm chứng

Nêu ra 15 vấn đề mà không thay đổi gì thường ít hữu ích hơn chọn một vấn đề có tác động rõ. Chẳng hạn:

**Quan sát:** nhiều story hoàn thành phần phát triển nhưng chờ kiểm thử nhiều ngày.

**Giả thuyết:** quá nhiều việc được bắt đầu cùng lúc làm công đoạn kiểm thử quá tải.

**Thử nghiệm:** trong Sprint kế tiếp, Developers ưu tiên hoàn tất việc đang mở và giữ WIP của cột “Đang phát triển” ở mức nhóm thống nhất.

**Kiểm tra:** xem tuổi các story đang mở, thời gian chờ kiểm thử, chất lượng và mức độ gián đoạn. Nếu kết quả không tốt hơn, xem xét lại WIP, cách chia story và năng lực kiểm thử.

Đây là ví dụ về **cải tiến dựa trên nguyên nhân giả định**, không phải lời cam kết rằng giảm WIP sẽ luôn giải quyết được mọi điểm tắc.

## 6. Khi chỉ số biến thành mục tiêu để “chơi theo điểm số”

Chỉ số thường là **đại diện gần đúng** cho thứ khó đo trực tiếp. Nó có thể rất hữu ích, nhưng dễ bị hiểu sai nếu tách khỏi bối cảnh.

| Chỉ số | Ý nghĩa hợp lý | Cách dùng sai phổ biến | Phép kiểm tra bổ sung |
|---|---|---|---|
| **Velocity (story points/Sprint)** | Hỗ trợ một Scrum Team dự báo năng lực tương đối nếu cách ước lượng đủ nhất quán | Xếp hạng nhóm, đặt KPI “Sprint sau phải nhiều điểm hơn” | Sprint Goal, chất lượng, độ ổn định dự báo và giá trị Increment |
| **Số ticket hoàn thành** | Theo dõi lượng hạng mục đi qua hệ thống | Chia nhỏ ticket chỉ để tăng số đếm; né việc khó | Kích thước và loại việc, outcome, công việc làm lại |
| **Throughput** | Số hạng mục hoàn thành trên đơn vị thời gian | Ép tăng bằng mọi giá, bỏ qua kích thước và mức rủi ro | WIP, cycle time, lỗi và loại công việc |
| **Cycle time** | Thời gian từ lúc bắt đầu thực hiện đến lúc hoàn thành theo định nghĩa của nhóm | Ép đóng việc sớm, giấu trạng thái chờ, tránh việc phức tạp | Phân phối thời gian, work item age, reopen rate và chất lượng |
| **Lead time** | Thời gian từ mốc yêu cầu/cam kết được định nghĩa đến mốc hoàn thành | Đổi mốc bắt đầu để số đẹp hơn | Nhất quán điểm đo; trải nghiệm chờ của khách hàng |
| **Số lỗi tìm thấy** | Cung cấp tín hiệu về chất lượng và năng lực phát hiện | Thưởng theo số bug, dẫn đến báo bug vụn hoặc bỏ qua lỗi khó | Mức độ nghiêm trọng, lỗi lọt ra sử dụng, thời gian khôi phục |
| **Độ phủ kiểm thử** | Cho biết phần mã được thực thi bởi kiểm thử theo cách đo cụ thể | Coi 100% coverage là bảo đảm không lỗi | Chất lượng assert, kiểm thử rủi ro quan trọng và lỗi thực tế |
| **Deployment frequency** | Tín hiệu về khả năng phát hành thường xuyên | Phát hành thay đổi vô nghĩa để tăng số lần | Giá trị được giao, lỗi triển khai và khả năng khôi phục |
| **Số giờ họp / tỷ lệ dự họp** | Có thể mô tả chi phí thời gian phối hợp | Coi tham gia đủ mọi cuộc họp là biểu hiện Agile tốt | Chất lượng quyết định, thời gian chờ làm rõ, mức gián đoạn |

### 6.1. Cái bẫy của velocity

Trong một nhóm, story point là **ước lượng tương đối**, không phải đơn vị công việc chuẩn giữa các nhóm.

Ví dụ:

| Sprint | Tổng story point hoàn thành | Số lỗi nghiêm trọng phát sinh sau phát hành | Tỷ lệ người dùng kích hoạt thành công |
|---|---:|---:|---:|
| 1 | 28 | 2 | 72% |
| 2 | 42 | 5 | 71% |

Nhìn riêng story point, Sprint 2 có vẻ “năng suất” hơn. Nhưng lỗi tăng và tỷ lệ kích hoạt không cải thiện. Ngoài ra, chưa biết độ phức tạp của story, cách ước lượng có thay đổi hay không, sản phẩm có thêm nhiều người dùng hay không. **Không thể kết luận chỉ từ bảng này** rằng nhóm làm việc tốt hơn hay kém hơn; có thể xác định những câu hỏi cần điều tra.

Nếu tổ chức đưa chỉ tiêu “mọi Sprint phải tăng 15% velocity”, thành viên có thể vô thức tăng điểm ước lượng, chỉ chọn story dễ hoặc bỏ việc cải thiện chất lượng. Khi đó chỉ số không còn giúp dự báo.

**Nguyên tắc sử dụng:** velocity, nếu được nhóm dùng, nên hỗ trợ lập kế hoạch và trao đổi trong chính ngữ cảnh của nhóm. Không dùng điểm để đánh giá cá nhân hoặc so sánh năng suất giữa các nhóm với thang ước lượng khác nhau.

### 6.2. Chỉ tối ưu tốc độ dòng công việc cũng có thể gây hại

Kanban giúp nhóm hiểu luồng bằng các phép đo như **WIP, throughput, work item age và cycle time**. Ví dụ, sau khi đặt giới hạn WIP, cycle time giảm là một tín hiệu tích cực. Nhưng nếu nhóm chỉ chọn những ticket dễ nhất để làm nhanh, các việc rủi ro cao hoặc ảnh hưởng lớn có thể nằm lại backlog quá lâu.

Cần kết hợp:

- **Luồng công việc:** bao nhiêu việc đang mở, việc nào già nhất, thời gian hoàn thành phân bố ra sao?
- **Chất lượng:** có lỗi nghiêm trọng, công việc phải làm lại hoặc tác động không mong muốn không?
- **Giá trị:** việc đang hoàn thành có giải quyết ưu tiên thực sự không?
- **Tính bền vững:** nhóm có đang đổi ngữ cảnh liên tục hoặc phải làm thêm giờ kéo dài không?

Không có mục tiêu “giảm cycle time vô hạn”. Nếu cố giảm bằng cách bỏ hoạt động kiểm thử cần thiết, số liệu luồng có thể đẹp lên ngắn hạn nhưng sản phẩm kém ổn định hơn.

### 6.3. “Không đo để tránh bị thao túng” cũng không phải giải pháp

Lo ngại về chỉ số bị sử dụng sai không có nghĩa nên dừng đo lường. Nếu không quan sát thời gian chờ, chất lượng hay kết quả, nhóm khó biết cải tiến có tác dụng không.

Giải pháp tốt hơn là **đo ít nhưng có mục đích**, định nghĩa rõ phép đo, xem nhiều tín hiệu cùng lúc, giải thích bối cảnh và dùng dữ liệu để tìm vấn đề của hệ thống thay vì tạo bảng xếp hạng cá nhân.

## 7. Xây bộ chỉ số gắn với câu hỏi ra quyết định

Trước khi thêm một biểu đồ lên dashboard, hãy hoàn thành câu:

> “Chúng ta đo **___** để biết **___**, từ đó quyết định **___**.”

Ví dụ: “Chúng ta đo *work item age* để biết story nào đã mở lâu bất thường, từ đó ưu tiên tháo điểm bị chặn trước khi kéo thêm việc mới.”

Một bộ chỉ số tốt thường có cả **tín hiệu chính** và **tín hiệu bảo vệ (guardrails)**:

| Mục tiêu/câu hỏi | Tín hiệu chính | Tín hiệu bảo vệ | Quyết định có thể đưa ra |
|---|---|---|---|
| Giảm thời gian chờ hoàn thành yêu cầu | Phân phối cycle time hoặc lead time theo loại việc | Lỗi nghiêm trọng, work item age | Giới hạn WIP, xử lý điểm tắc, chia nhỏ hạng mục |
| Giúp người mới đăng ký thành công | Tỷ lệ kích hoạt, tỷ lệ hoàn tất luồng | Lỗi đăng nhập, yêu cầu hỗ trợ, phản hồi tiêu cực | Điều chỉnh ưu tiên backlog và trải nghiệm |
| Phát hành tin cậy hơn | Lỗi triển khai, khả năng khôi phục, kết quả kiểm thử | Giá trị được giao, chi phí vận hành, tốc độ đáp ứng thay đổi | Cải thiện CI/CD, kiểm thử hồi quy, quy trình phát hành |
| Giảm làm lại vì hiểu sai yêu cầu | Số story phải mở lại do lệch acceptance criteria | Thời gian chuẩn bị, thời gian chờ quyết định | Tổ chức làm rõ ví dụ trước khi phát triển |
| Giảm quá tải và gián đoạn | WIP, công việc bị chặn, phản hồi của nhóm | Tốc độ giao giá trị và mức khẩn cấp được xử lý | Làm rõ chính sách ưu tiên, giảm nhận việc song song |

### Chọn chỉ số ở mức nào?

- **Cấp sản phẩm:** kết quả người dùng và doanh nghiệp, chẳng hạn hoàn tất giao dịch hoặc giảm yêu cầu hỗ trợ.
- **Cấp dòng công việc của nhóm:** lead time, cycle time, WIP, throughput, tuổi việc bị chặn.
- **Cấp kỹ thuật/chất lượng:** lỗi, kiểm thử thiết yếu, độ ổn định triển khai, khả năng khôi phục và chi phí bảo trì.

Mỗi cấp trả lời câu hỏi khác nhau. Một nhóm hoàn thành nhiều story có thể vẫn chưa tạo outcome mong muốn; một sản phẩm có outcome tốt trong thời gian ngắn vẫn có thể đang tích tụ nợ kỹ thuật.

### Định nghĩa phép đo trước khi diễn giải

Với cycle time, cần thống nhất thời điểm **bắt đầu** và **hoàn thành**. Nếu một Sprint tính từ lúc chuyển sang “Đang làm”, còn Sprint sau tính từ lúc “Đang kiểm thử”, so sánh trực tiếp sẽ gây sai lệch.

Với tỷ lệ phần trăm, cần biết **mẫu số** và thời gian đo. Ví dụ, “10/20 người hoàn tất” và “1.000/2.000 người hoàn tất” đều là 50%, nhưng độ tin cậy và mức độ biến động khác nhau. Cần cân nhắc mùa vụ, phân khúc người dùng, thay đổi lưu lượng và cỡ mẫu.

Với phân phối thời gian, các phân vị như **P85** (85% hạng mục có thời gian không vượt giá trị này, theo tập quan sát và định nghĩa tương ứng) đôi khi hữu ích hơn chỉ dùng trung bình. Tuy nhiên, phân vị với rất ít mẫu có thể dao động mạnh; không nên diễn giải như bảo đảm thời hạn giao hàng.

## 8. Thiết kế thử nghiệm cải tiến thay vì thêm quy định

Khi thấy một nghi thức hoặc chỉ số chưa tạo giá trị, đừng vội đặt ra thêm KPI hay buộc nhóm họp nhiều hơn. Có thể triển khai chu trình **thử nhỏ – quan sát – điều chỉnh**:

1. **Nêu vấn đề bằng dữ kiện:** “Trong ba Sprint gần đây, nhiều story bị chặn khi chờ làm rõ quy tắc nghiệp vụ.”
2. **Đặt mục tiêu có ý nghĩa:** “Giảm thời gian chờ giải đáp mà không tăng lỗi do yêu cầu chưa rõ.”
3. **Phát biểu giả thuyết:** “Làm rõ ví dụ với Product Owner, Developer và Tester trước khi bắt đầu những story mơ hồ sẽ giảm vòng hỏi đáp.”
4. **Chọn can thiệp nhỏ:** thử một buổi thảo luận ngắn dành cho các story rủi ro cao trong hai Sprint; không bắt mọi story phải tham gia.
5. **Chọn tín hiệu:** thời gian chờ làm rõ, số story phải mở lại, lỗi do hiểu sai, phản hồi của nhóm và chi phí thời gian họp.
6. **Quan sát và thảo luận:** so với dữ liệu trước đó khi có thể, xem điều gì khác biệt và yếu tố nào chưa kiểm soát.
7. **Quyết định tiếp:** tiếp tục, mở rộng, điều chỉnh hoặc dừng thí nghiệm; ghi lại điều học được.

### Mẫu giả thuyết thử nghiệm

~~~text
Vấn đề:
  Story thường bị tắc khi sang kiểm thử do tiêu chí chấp nhận mơ hồ.

Giả thuyết:
  Nếu làm rõ ví dụ trước khi nhận các story có rủi ro nghiệp vụ cao,
  số lần phải hỏi lại và thời gian chờ ở bước kiểm thử sẽ giảm.

Phạm vi:
  Chỉ các story được nhóm đánh giá là còn nhiều cách hiểu, trong 2 Sprint.

Thay đổi:
  PO + Developer + Tester thảo luận ví dụ cụ thể,
  ghi acceptance criteria vào story, không yêu cầu buổi họp cố định cho mọi việc.

Tín hiệu:
  Thời gian chờ làm rõ, tuổi story bị chặn, số lần mở lại story.

Tín hiệu bảo vệ:
  Lỗi nghiệp vụ và thời gian nhóm dành cho hoạt động làm rõ.

Điểm đánh giá:
  Cuối Sprint thứ hai, xem ví dụ thực tế và dữ liệu thu thập được.

Quyết định tiếp:
  Giữ / thay đổi / dừng cách làm; nêu lý do và phần còn chưa chắc chắn.
~~~

Thí nghiệm hai Sprint là **ví dụ minh họa**, không phải thời lượng chuẩn. Với thay đổi ảnh hưởng người dùng lớn hoặc rủi ro cao, cần điều chỉnh phạm vi thử nghiệm và kiểm soát thích hợp. Với số quan sát quá ít, hãy tránh kết luận mạnh về quan hệ nhân quả.

### Đừng nhầm biến động tự nhiên với hiệu quả của giải pháp

Nếu cycle time giảm một tuần, chưa chắc chính cuộc họp mới đã tạo ra thay đổi. Tuần đó có thể chỉ có công việc dễ hơn, ít sự cố hơn hoặc thành viên nhiều kinh nghiệm hơn. Để đánh giá đáng tin cậy:

- Giữ cách định nghĩa chỉ số ổn định.
- Phân loại công việc khi đặc tính quá khác nhau.
- Quan sát xu hướng trong khoảng thời gian phù hợp.
- Đối chiếu phản hồi định tính, ví dụ cụ thể và các tín hiệu bảo vệ.
- Ghi nhận các thay đổi khác xảy ra cùng thời gian.

Mục tiêu của thử nghiệm cải tiến nội bộ thường là **ra quyết định tốt hơn dưới sự bất định**, không phải chứng minh chắc chắn một quy luật phổ quát chỉ từ vài mẫu.

## 9. Tình huống xuyên suốt: đội Scrum bị ám ảnh bởi velocity

### Bối cảnh

Một nhóm phát triển ứng dụng đặt hàng dùng Sprint hai tuần. Quản lý yêu cầu velocity tăng qua từng Sprint và coi số điểm cao là bằng chứng hiệu quả. Nhóm bắt đầu:

- Tăng điểm ước lượng cho cùng mức phức tạp.
- Ưu tiên story dễ lấy điểm, trì hoãn lỗi khó.
- Đánh dấu “Done” cho tính năng chưa kiểm thử tích hợp đầy đủ.
- Dành Sprint Review để trình bày số story point, ít hỏi khách hàng về kết quả.

Sau vài Sprint, dashboard tăng đẹp nhưng khách hàng vẫn gặp lỗi giỏ hàng. Nhóm đã **tối ưu hóa một phép đo** trong khi chất lượng và giá trị sản phẩm không tăng tương ứng.

### Nhóm chuyển hướng như thế nào?

**Bước 1 – Tái khẳng định mục tiêu:** cùng Product Owner và bên liên quan xác định ưu tiên là giảm tỷ lệ đặt hàng thất bại và tăng khả năng hoàn tất giao dịch.

**Bước 2 – Minh bạch thực trạng:** đưa các mục chưa đáp ứng Definition of Done về đúng trạng thái, làm rõ lỗi nghiêm trọng và phân biệt story mới với công việc sửa lỗi/làm lại.

**Bước 3 – Điều chỉnh đo lường:** giữ velocity như một nguồn tham khảo nội bộ cho kế hoạch nếu nhóm còn thấy hữu ích; thêm tỷ lệ giao dịch thành công, lỗi nghiêm trọng và phân phối cycle time của các hạng mục liên quan.

**Bước 4 – Cải tiến nhỏ:** chọn một cách giảm lỗi hồi quy, chẳng hạn thêm kiểm thử tích hợp cho các luồng thanh toán trọng yếu và giảm số story bắt đầu song song.

**Bước 5 – Kiểm chứng:** quan sát hành vi khách hàng, lỗi và dòng công việc sau các Increment tiếp theo. Nếu tỷ lệ giao dịch cải thiện trong khi chất lượng và sức tải ổn định, nhóm có thêm bằng chứng để tiếp tục. Nếu chưa, nhóm nghiên cứu nguyên nhân khác.

### Bảng theo dõi minh họa

| Tín hiệu | Trước khi thay đổi | Sau khi thử nghiệm | Điều cần thận trọng |
|---|---:|---:|---|
| Velocity được báo cáo | 45 điểm/Sprint | 35 điểm/Sprint | Thang ước lượng thay đổi có thể khiến so sánh vô nghĩa |
| Giao dịch thành công | 93% | 96% | Cần kiểm tra lưu lượng, phân khúc và yếu tố khác |
| Lỗi nghiêm trọng sau phát hành | 6 | 2 | Số lỗi phụ thuộc phạm vi, cách phát hiện và thời gian theo dõi |
| WIP trung bình của nhóm | 12 | 7 | Giảm WIP không tự động chứng minh tăng giá trị |

Đây là **số giả định phục vụ bài học**. Nếu chỉ nhìn velocity, nhóm tưởng rằng hiệu quả đã đi xuống. Khi xét kết quả người dùng và độ ổn định, có thể thấy hướng thay đổi đáng tiếp tục kiểm chứng. **Không thể suy ra quan hệ nhân quả chắc chắn chỉ từ bốn con số.**

### Quyết định cuối cùng

Nhóm ngừng dùng velocity làm chỉ tiêu thưởng/phạt, tập trung vào Sprint Goal và chất lượng Increment. Sprint Review có thảo luận phản hồi người dùng, còn Retrospective chọn một cải tiến nhỏ và xem lại tác động ở Sprint sau.

**Bài học:** nhóm làm Agile tốt không nhất thiết có biểu đồ tăng đều. Nhóm cần khả năng **minh bạch về vấn đề, kiểm tra kết quả và thích ứng khi dữ liệu mâu thuẫn với kỳ vọng**.

## 10. Áp dụng nguyên tắc với Scrum, Kanban và XP

Các phương pháp/thực hành khác nhau đặt trọng tâm khác nhau, nhưng đều có thể bị nghi thức hóa.

### 10.1. Scrum: dùng các sự kiện để học và đạt mục tiêu

Scrum có mục tiêu và cam kết giúp việc kiểm tra có ý nghĩa: **Product Goal** gắn với Product Backlog, **Sprint Goal** gắn với Sprint Backlog, và **Definition of Done** gắn với Increment.

Nếu nhóm chỉ cố hoàn thành tất cả item đã đưa vào Sprint mà quên Sprint Goal, họ đã nhầm **phạm vi ban đầu** với **mục tiêu mang lại giá trị**. Khi thông tin thay đổi, Developers và Product Owner có thể làm rõ và thương lượng lại phạm vi trong Sprint mà không làm nguy hại Sprint Goal; chất lượng không được giảm.

**Dấu hiệu kiểm tra:** sau mỗi sự kiện Scrum, có một quyết định rõ ràng hơn, một sự hiểu biết mới hoặc một kế hoạch được cập nhật để đạt mục tiêu hay không?

### 10.2. Kanban: chính sách và phép đo nhằm cải thiện luồng

Kanban nhấn mạnh minh bạch hóa workflow, quản lý công việc đang thực hiện và cải tiến luồng. Một nhóm có thể đặt giới hạn WIP nhưng vẫn thất bại nếu ai cũng tạo việc “khẩn cấp” vượt giới hạn mà không cân nhắc tác động.

Giới hạn WIP không phải thành tích riêng; nó là **chính sách giúp nhóm phát hiện điểm tắc và phối hợp để hoàn tất việc**. Nếu giới hạn hiện tại không phù hợp, nhóm có thể điều chỉnh dựa trên bằng chứng và nhu cầu phục vụ khách hàng.

**Dấu hiệu kiểm tra:** có bao nhiêu việc phải chờ, việc nào già nhất, và nhóm đã thay đổi cách phối hợp như thế nào khi phát hiện điểm tắc?

### 10.3. XP: thực hành kỹ thuật vì khả năng đổi hướng an toàn

Các thực hành như **TDD, pair programming, continuous integration và refactoring** có mục tiêu tạo phản hồi sớm, giảm lỗi và giữ mã dễ thay đổi.

Đừng biến “tất cả đều phải pair programming mọi giờ” hoặc “phải đạt 100% code coverage” thành mục tiêu tự thân mà không xét bối cảnh. Ví dụ, TDD có ích khi kiểm thử diễn đạt rõ hành vi và thiết kế; nếu chỉ viết kiểm thử qua loa để đạt chỉ tiêu, nhóm có thể tăng chi phí bảo trì mà không giảm rủi ro.

**Dấu hiệu kiểm tra:** sau một thay đổi yêu cầu, nhóm có thể chỉnh hành vi an toàn hơn, phát hiện lỗi sớm hơn và triển khai tin cậy hơn hay không?

### 10.4. Phối hợp các cách tiếp cận mà không “sưu tầm nghi thức”

Nhóm có thể dùng Scrum để làm việc theo mục tiêu Sprint, dùng dữ liệu dòng công việc và chính sách WIP từ Kanban, đồng thời áp dụng các kỹ thuật XP để bảo vệ chất lượng. Nhưng thêm mỗi thực hành cũng có **chi phí chú ý, đào tạo và vận hành**.

Trước khi áp dụng một quy tắc mới, hãy hỏi:

1. Quy tắc này giải quyết vấn đề cụ thể nào?
2. Bằng chứng nào cho thấy vấn đề đang tồn tại?
3. Ai cần thực hiện và tốn bao nhiêu thời gian?
4. Tín hiệu nào cho biết nó hiệu quả hoặc gây tác dụng phụ?
5. Khi nào nhóm sẽ xem lại và thay đổi hoặc loại bỏ nó?

Những câu hỏi này giúp tránh việc áp dụng Scrum, Kanban, XP chỉ để chứng minh nhóm “đúng chuẩn Agile” trên bề mặt.

## 11. Checklist cho người điều phối và thành viên nhóm

Trước, trong và sau một hoạt động Agile, có thể tự hỏi:

### Trước khi họp hoặc đưa một chỉ số lên dashboard

- Vấn đề hay quyết định cụ thể nào cần giải quyết?
- Ai cần có mặt và thông tin nào có thể chuẩn bị bất đồng bộ?
- Nếu không có hoạt động này, nhóm sẽ mất cơ hội học hay kiểm soát rủi ro gì?
- Chỉ số này phục vụ câu hỏi nào? Ai có thể dùng nó để thay đổi quyết định?

### Trong khi trao đổi hoặc xem dữ liệu

- Chúng ta có phân biệt **sự thật quan sát được** với **giả định và giải thích** không?
- Có ai đang cố khiến biểu đồ đẹp lên bằng cách đổi quy tắc ghi nhận không?
- Có dấu hiệu khác mâu thuẫn với chỉ số chính không?
- Những người liên quan có thể đặt câu hỏi và nêu bằng chứng ngược không?

### Sau khi kết thúc

- Đã có hành động, quyết định hoặc điều mới học rõ ràng chưa?
- Ai theo dõi, ở đâu và lúc nào nhóm sẽ kiểm chứng kết quả?
- Có cần cập nhật backlog, DoD, chính sách dòng công việc hoặc kiểm thử không?
- Hoạt động này có cần điều chỉnh để bớt tốn thời gian mà vẫn đạt mục đích không?

**Cần giữ sự cân bằng:** không phải cuộc họp nào cũng phải tạo một “action item” mới. Đôi khi một quyết định giữ nguyên hướng đi **dựa trên thông tin mới được kiểm tra** cũng là kết quả có giá trị.

## 12. Những cách hiểu sai thường gặp

| Cách hiểu sai | Vì sao gây hại | Cách hiểu và làm phù hợp hơn |
|---|---|---|
| “Càng nhiều cuộc họp Agile, nhóm càng trưởng thành.” | Tăng gián đoạn nhưng chưa chắc tăng hiểu biết | Đánh giá cuộc họp theo mục đích và quyết định tạo ra |
| “Đi họp đủ nghĩa là giao tiếp tốt.” | Người dự vẫn có thể hiểu khác nhau hoặc không dám nêu ý kiến | Dùng ví dụ, xác nhận cách hiểu và lưu quyết định |
| “Velocity tăng nghĩa là sản phẩm đang thành công.” | Điểm ước lượng không đo giá trị hay chất lượng | Kết hợp Sprint Goal, kết quả người dùng và rủi ro |
| “Story point là giờ làm việc và dùng để so sánh các nhóm.” | Thang đo tương đối khác nhau; tạo áp lực làm đẹp số liệu | Dùng ước lượng để hỗ trợ kế hoạch trong bối cảnh phù hợp |
| “Đóng ticket càng nhanh càng tốt.” | Có thể khiến nhóm bỏ qua kiểm thử, làm lại hoặc vấn đề khó | Xem cycle time cùng chất lượng và giá trị |
| “Có dashboard là đã minh bạch.” | Dashboard sai định nghĩa hoặc che điểm tắc vẫn gây hiểu nhầm | Minh bạch chính sách, trạng thái thật và giới hạn của dữ liệu |
| “Retrospective thành công khi có thật nhiều ý tưởng.” | Ý tưởng không được thực hiện, quá tải cải tiến | Chọn ít việc khả thi và kiểm chứng tác động |
| “Không nên đo chỉ số vì dễ bị lạm dụng.” | Nhóm mất khả năng nhận biết xu hướng và điểm tắc | Định nghĩa phép đo, xem ngữ cảnh và dùng chỉ số để học |
| “Quy trình đã chuẩn hóa thì không nên thay đổi.” | Nhóm tiếp tục làm việc kém hiệu quả khi bối cảnh thay đổi | Cải tiến chính sách dựa trên bằng chứng trong khuôn khổ cần thiết |
| “Có dữ liệu là biết ngay nguyên nhân.” | Nhầm tương quan, biến động ngẫu nhiên với tác động thật | Xem nhiều tín hiệu, kiểm tra giả thuyết và ghi mức độ chắc chắn |

## 13. Bài tập thực hành

### Bài tập 1 – Phát hiện chỉ số bị tối ưu sai

Nhóm A tăng số ticket hoàn thành từ 30 lên 50 mỗi tuần. Đồng thời, số lỗi nghiêm trọng sau phát hành tăng, nhiều ticket bị mở lại và người dùng không thấy cải thiện ở chức năng chính.

Hãy trả lời:

1. Có thể kết luận năng suất của nhóm tăng không? Vì sao?
2. Nêu ít nhất **hai cách** chỉ số ticket có thể bị làm sai lệch.
3. Chọn **hai tín hiệu bổ sung** và giải thích quyết định mà chúng hỗ trợ.
4. Đề xuất một thử nghiệm cải tiến nhỏ, có thời điểm xem lại kết quả.

**Gợi ý:** số ticket là output, không tự nói lên outcome. Có thể xét lỗi phải làm lại, cycle time, tỷ lệ hoàn tất tác vụ người dùng và mức WIP. Cần kiểm tra cả cách chia ticket và mức độ phức tạp công việc.

### Bài tập 2 – Thiết kế lại Sprint Retrospective

Một nhóm luôn dành một giờ retrospective để liệt kê vấn đề. Mỗi lần có hơn 20 đề xuất cải tiến; Sprint sau không ai nhớ các đề xuất đó.

Thiết kế cách điều phối mới bằng cách ghi:

- Một tiêu chí chọn vấn đề ưu tiên.
- Một cải tiến nhỏ nhóm có thể thử trong Sprint sau.
- Người chịu trách nhiệm theo dõi và cách công khai tiến độ.
- Một chỉ số hoặc dấu hiệu định tính để nhận biết tác động.
- Thời điểm đưa kết quả trở lại cuộc thảo luận.

**Gợi ý:** có thể ưu tiên vấn đề lặp lại, gây ảnh hưởng tới Sprint Goal hoặc chất lượng. Đừng mở thêm một KPI chỉ để “chứng minh” retrospective có hiệu quả.

### Bài tập 3 – Xây câu hỏi đo lường có mục đích

Chọn một trong các chỉ số: **cycle time, WIP, velocity, số lỗi sau triển khai, tỷ lệ người dùng kích hoạt thành công**. Điền mẫu:

~~~text
Chúng ta đo: _______________________________
Để trả lời câu hỏi: _________________________
Định nghĩa phép đo và khoảng thời gian: _____
Quyết định có thể đưa ra: ___________________
Tín hiệu bảo vệ cần xem cùng: _______________
Trường hợp chỉ số bị hiểu sai: ______________
~~~

**Gợi ý:** nếu đo WIP, mục tiêu có thể là phát hiện quá nhiều việc đang mở. Không biến “WIP = 0” thành đích cuối vì khi đó nhóm không có công việc đang thực hiện.

### Bài tập 4 – Tranh luận về một “quy định Agile” mới

Quản lý đề xuất: “Để tăng hiệu quả Agile, tất cả thành viên phải dự thêm một cuộc họp cập nhật hai lần mỗi ngày, và mỗi người phải hoàn thành ít nhất năm ticket mỗi tuần.”

Hãy viết phản hồi với ba phần:

1. **Mục tiêu cần làm rõ:** cuộc họp và chỉ tiêu ticket dự kiến giải quyết vấn đề gì?
2. **Rủi ro:** hai quy định có thể dẫn đến hành vi lệch hướng nào?
3. **Phương án thử nhỏ:** có cách nào đo thời gian chờ, độ rõ công việc hoặc giá trị giao hàng trước khi mở rộng quy định không?

Đánh giá câu trả lời bằng cách tự hỏi: “Đề xuất của mình có bảo đảm việc ra quyết định dựa trên quan sát thực tế, và có thể thay đổi khi bằng chứng mới xuất hiện không?”

## 14. Tổng kết

Tư duy thực nghiệm là động lực giúp Agile thích ứng qua **phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục**. Nghi thức Scrum, bảng Kanban, thực hành XP, user story, backlog hay dashboard chỉ có giá trị khi hỗ trợ điều đó.

Hãy ghi nhớ năm nguyên tắc thực hành:

1. **Bắt đầu từ kết quả cần đạt:** người dùng hoặc hệ thống sẽ tốt hơn ở điểm nào?
2. **Dùng hoạt động đúng mục đích:** họp để làm rõ, quyết định hoặc cải tiến; quản lý luồng để giảm tắc nghẽn; kỹ thuật XP để tạo thay đổi an toàn.
3. **Dùng chỉ số như tín hiệu:** xem định nghĩa, xu hướng, bối cảnh và tác dụng phụ trước khi kết luận.
4. **Ưu tiên vòng học hỏi nhỏ:** nêu giả thuyết, thực hiện thay đổi có kiểm soát, quan sát và điều chỉnh.
5. **Không đánh đổi tính minh bạch lấy điểm số:** khi công việc chưa đạt Definition of Done hoặc còn rủi ro, cần thể hiện đúng trạng thái thực.

Một nhóm thành công không phải nhóm có dashboard luôn xanh hoặc lịch họp đầy đủ nhất, mà là nhóm **nhìn thấy thực tế, giao được phần mềm có giá trị, học từ kết quả và có khả năng điều chỉnh một cách có trách nhiệm**.

**Câu hỏi ghi nhớ:** “Nếu bỏ tên gọi Agile khỏi cuộc họp, bảng công việc và chỉ số này, chúng có còn giúp chúng ta đưa ra quyết định tốt hơn cho sản phẩm và người dùng không?”

### Tài liệu tham khảo

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — giá trị Agile, phản hồi sớm, phần mềm hoạt động được và cải tiến liên tục.
- [The Scrum Guide](https://scrumguides.org/scrum-guide.html) — ba trụ cột của tính thực nghiệm, mục tiêu Scrum, các sự kiện và Definition of Done.
- [The Kanban Guide](https://kanbanguides.org/) — quản lý luồng, chính sách workflow và các phép đo WIP, throughput, work item age, cycle time.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — các thực hành kỹ thuật và phản hồi nhanh trong XP.

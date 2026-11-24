# Thiết kế phần tăng trưởng đủ nhỏ để nhận phản hồi sớm

Một nhóm phát triển nền tảng học lập trình Java muốn nâng tỷ lệ người học hoàn thành bài luyện tập. Nhóm đề xuất một tính năng lớn: **“Hệ thống luyện tập thông minh”**, gồm ngân hàng câu hỏi, chấm điểm, giải thích đáp án, gợi ý ôn tập, thống kê giáo viên, xếp hạng và cá nhân hóa bằng AI. Theo bản kế hoạch ban đầu, toàn bộ tính năng cần tám tuần; chỉ khi đó nhóm mới mời người học sử dụng.

Sau bốn tuần, giao diện đã gần hoàn chỉnh, API đang tích hợp và nhiều phần được báo “90%”. Nhưng chưa có học viên nào tự làm được một câu hỏi đầu cuối. Nhóm chưa biết người học gặp khó vì **không hiểu đáp án**, vì **giao diện nộp bài** hay vì **thiếu động lực ôn tập**. Sự chậm trễ không chỉ là chậm viết code; đó là chậm **học điều gì thực sự tạo giá trị**.

Một cách khác là chọn **phần tăng trưởng nhỏ đầu tiên**: học viên được cấp quyền mở một câu trắc nghiệm Java, chọn đáp án, nộp và nhận phản hồi đúng/sai rõ ràng. Phần này được tích hợp, kiểm thử, đáp ứng tiêu chuẩn hoàn tất và có thể đưa cho một nhóm học viên thật dùng sớm. Sau đó, nhóm quan sát cách họ làm bài, hỏi thêm những điểm khó hiểu và quyết định liệu nên bổ sung **giải thích đáp án**, **gợi ý ôn tập** hay một nhu cầu khác.

Đó là trọng tâm của bài **“Thiết kế phần tăng trưởng đủ nhỏ để nhận phản hồi sớm”**, thuộc chương **Phản hồi và phát hành** của module **AGILE_DEVELOPMENT**. Bài kết nối các giá trị Agile – cộng tác, phần mềm hoạt động, đáp ứng thay đổi – với thực hành user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc, giúp nhóm **giao giá trị tăng dần và điều chỉnh dựa trên phản hồi đáng tin**, thay vì chỉ hoàn thành nhiều đầu việc kỹ thuật.

Sau bài học, bạn có thể:

1. Phân biệt **phần tăng trưởng có thể sử dụng (Increment)** với task, bản demo, prototype, MVP và một lần release.
2. Xác định thế nào là một lát công việc **đủ nhỏ nhưng vẫn có ý nghĩa và an toàn**.
3. Chia một yêu cầu lớn thành các **lát dọc đầu cuối (vertical slices)** có thể kiểm tra hành vi người dùng.
4. Kết nối mỗi lát với **giả thuyết, đối tượng, tín hiệu phản hồi và quyết định tiếp theo**.
5. Đặt acceptance criteria và Definition of Done để tránh “giao sớm” bằng cách hạ chất lượng.
6. Tổ chức phát hành có kiểm soát, thu phản hồi định tính/định lượng và tránh suy diễn từ dữ liệu yếu.
7. Xử lý phụ thuộc kỹ thuật, phát hành theo nhóm, quyền riêng tư và những rủi ro khi thử nghiệm trên người dùng.
8. Dùng Scrum, Kanban và XP để rút ngắn chu kỳ **xây dựng – kiểm chứng – học hỏi**.
9. Thực hành thiết kế chuỗi Increment cho một tình huống sản phẩm thực tế.

## 1. Vì sao kích thước phần tăng trưởng quyết định tốc độ học?

Trong Agile, nhóm không chỉ cần **tạo phần mềm**, mà còn cần kiểm tra những giả định về **nhu cầu, khả năng sử dụng và giá trị**. Một yêu cầu lớn thường chứa nhiều giả định chưa được xác nhận cùng lúc:

- Người dùng có thật sự cần khả năng này không?
- Họ có tìm thấy và hiểu cách sử dụng không?
- Luồng thao tác có đủ đơn giản không?
- Thông tin trả về có giúp họ ra quyết định không?
- Hệ thống có đúng, an toàn và đủ tin cậy không?
- Khả năng này có cải thiện kết quả mà sản phẩm hướng tới không?

Nếu triển khai mọi thành phần rồi mới quan sát, nhóm có thể phát hiện giả định sai **sau khi chi phí đã phát sinh lớn**. Khi phần tăng trưởng nhỏ, nhóm có thể học sớm và chọn đầu tư bước tiếp theo dựa trên bằng chứng.

### 1.1. Hai nhịp làm việc đối lập

| Cách làm | Điều nhóm làm đầu tiên | Khi nào có phản hồi giá trị? | Rủi ro |
| --- | --- | --- | --- |
| **Gói tính năng lớn** | Xây giao diện, API, báo cáo, AI, thống kê và nhiều luồng cùng lúc. | Sau khi gần như toàn bộ tích hợp hoàn tất. | Sai giả định được phát hiện muộn; chi phí sửa và tích hợp lớn. |
| **Các lát nhỏ có thể sử dụng** | Giao một hành vi người dùng trọn vẹn, rồi mở rộng theo phản hồi. | Ngay sau khi lát đầu đạt chất lượng và được thử bởi đối tượng phù hợp. | Cần kỷ luật chọn phạm vi, hợp đồng, chất lượng và đo lường. |

**Nhỏ hơn không tự động tốt hơn.** Nếu một lát quá nhỏ đến mức chỉ có “tạo bảng database” hoặc “vẽ nút Nộp” mà không có hành vi dùng được, nhóm không thể nhận phản hồi đáng tin về giá trị người dùng. Kích thước tốt là **nhỏ nhất để tạo một kết quả có ý nghĩa và có thể kiểm chứng**.

### 1.2. Học nhanh khác với làm ẩu

Giao sớm phải đi cùng **độ tin cậy**. Một tính năng sai quyền truy cập, tính sai điểm hoặc mất dữ liệu có thể khiến phản hồi méo mó và gây thiệt hại. Do đó, mục tiêu là **rút ngắn thời gian từ giả thuyết đến bằng chứng hữu ích với tiêu chuẩn chất lượng không bị hạ**, không phải rút ngắn bằng cách bỏ kiểm thử.

## 2. Phân biệt Increment, user story, prototype, MVP và release

Các khái niệm thường bị dùng lẫn nhau, dẫn đến định nghĩa “đã xong” không rõ.

| Khái niệm | Bản chất | Có nhất thiết được người dùng thật sử dụng ngay? | Điều cần lưu ý |
| --- | --- | --- | --- |
| **User story** | Cách diễn đạt một nhu cầu/hành vi từ góc nhìn người dùng. | Không. | Là kỹ thuật hỗ trợ trao đổi, không phải hiện vật bắt buộc của Scrum. |
| **Task kỹ thuật** | Một phần công việc cần thực hiện. | Không. | Hoàn thành task không có nghĩa người dùng đã có khả năng mới. |
| **Prototype** | Bản thử để khám phá hoặc kiểm tra giả định. | Không. | Có thể là màn hình mô phỏng hoặc thử nghiệm chưa đủ điều kiện vận hành. |
| **MVP (Minimum Viable Product)** | Phiên bản/giải pháp tối thiểu giúp kiểm tra giả thuyết quan trọng về sản phẩm trong bối cảnh cụ thể. | Tùy hình thức thí nghiệm và đối tượng. | Không đồng nghĩa “sản phẩm lỗi nhưng rẻ”; cần đúng mục đích học và an toàn. |
| **Increment trong Scrum** | Một bước tiến cụ thể hướng tới Product Goal, tích hợp với các Increment trước, đáp ứng Definition of Done và có thể sử dụng. | Không bắt buộc đã release rộng, nhưng phải có thể sử dụng. | Có thể có nhiều Increment trong một Sprint. |
| **Deployment** | Đưa phần mềm lên một môi trường chạy. | Không. | Có thể deploy với feature flag tắt hoặc chỉ phục vụ nội bộ. |
| **Release** | Mở khả năng sản phẩm cho đối tượng người dùng đã xác định. | Có, trong phạm vi đã mở. | Quyết định và điều kiện release khác với trạng thái Done. |
| **Experiment/thử nghiệm** | Một thiết kế để kiểm chứng giả thuyết bằng bằng chứng. | Tùy phương pháp. | Có thể dùng prototype, phỏng vấn hoặc Increment thật. |

**Ví dụ:** Một prototype giao diện đáp án giúp phỏng vấn người học về mức dễ hiểu, nhưng chưa chắc là Increment vì chưa tích hợp với logic chấm điểm. Một Increment đã đạt DoD có thể được triển khai với feature flag tắt, rồi release cho lớp thử khi điều kiện phù hợp. Một MVP có thể gồm **nhiều Increment nhỏ**, tùy câu hỏi cần kiểm chứng.

### 2.1. Đừng đánh đồng “đã Done” với “đã tạo outcome”

- **Output:** nhóm đã cung cấp khả năng trả lời trắc nghiệm.
- **Outcome:** người học hiểu lỗi sai và tiếp tục học hiệu quả hơn.
- **Impact:** sau một thời gian, tỷ lệ đạt mục tiêu học tập hoặc duy trì học được cải thiện.

Một Increment đạt DoD giúp bảo đảm phần mềm **có thể sử dụng và đúng chuẩn**, nhưng không tự chứng minh outcome. Phản hồi sau release hoặc thử nghiệm là đầu vào quan trọng để kiểm tra giá trị.

## 3. Tiêu chí của một phần tăng trưởng “nhỏ nhưng đúng nghĩa”

Để đánh giá một lát ứng viên, hãy dùng sáu câu hỏi:

| Tiêu chí | Câu hỏi | Dấu hiệu chưa đạt |
| --- | --- | --- |
| **Có hành vi người dùng hoặc năng lực tích hợp rõ** | Ai có thể làm được điều gì sau lát này? | Chỉ có bảng dữ liệu hoặc endpoint rời rạc không được sử dụng. |
| **Đầu cuối trong phạm vi chọn** | Có đi qua những lớp cần thiết để hành vi hoạt động thật không? | UI dùng dữ liệu giả, API chưa nối, dữ liệu chưa lưu đúng. |
| **Đủ nhỏ để hoàn tất và nhận phản hồi nhanh** | Có thể làm, kiểm tra và tích hợp trong một khoảng ngắn phù hợp năng lực nhóm không? | Nhiều vai trò, quy tắc và phụ thuộc chưa được cắt nghĩa. |
| **Đạt tiêu chuẩn chất lượng** | DoD, phân quyền, dữ liệu, kiểm thử và rủi ro liên quan có được bảo vệ không? | “Sẽ kiểm tra bảo mật ở Sprint sau.” |
| **Có đối tượng và cách quan sát** | Ai sẽ thử, phản hồi qua đâu, tín hiệu nào quan trọng? | “Ra mắt rồi sẽ biết”, nhưng không có người thử hay số đo. |
| **Có quyết định tiếp theo** | Phản hồi nào khiến nhóm tiếp tục, sửa, thu hẹp hay bỏ hướng này? | Dù phản hồi thế nào, roadmap vẫn cố định hoàn toàn. |

Một lát không nhất thiết phải có đầy đủ mọi tính năng của trải nghiệm hoàn chỉnh. Nó cần **hoàn chỉnh trong phạm vi được công bố**, không làm người dùng hiểu nhầm hoặc gặp rủi ro do “để phần thiết yếu làm sau”.

### 3.1. Kiểm tra bằng một câu diễn đạt

Hãy thử hoàn thành câu:

> “Sau khi Increment này đạt DoD và được đưa tới **[nhóm người dùng]**, họ có thể **[hành vi cụ thể]**, giúp chúng tôi quan sát **[tín hiệu]** để quyết định **[bước tiếp theo]**.”

Ví dụ:

> “Sau khi Increment đầu được mở cho 20 học viên trong lớp thử, họ có thể làm một câu Java và xem đúng/sai; chúng tôi quan sát việc hoàn tất, chỗ họ không hiểu và lỗi nộp bài, để quyết định có nên ưu tiên giải thích đáp án trước báo cáo điểm.”

Nếu không thể diễn đạt **ai làm gì và học được gì**, lát có thể đang là một tập task chứ chưa phải một phần tăng trưởng phục vụ phản hồi.

## 4. Vòng phản hồi: từ giả thuyết tới quyết định

Giao nhỏ chỉ có ý nghĩa khi nhóm **sẵn sàng thay đổi quyết định từ bằng chứng**. Một vòng học có thể mô tả bằng sáu bước:

1. Xác định **vấn đề người dùng** hoặc kết quả sản phẩm cần cải thiện.
2. Nêu **giả thuyết** về hành vi và giá trị.
3. Chọn **lát nhỏ** đủ kiểm tra một phần quan trọng của giả thuyết.
4. Xây, kiểm thử, tích hợp và cung cấp cho đối tượng phù hợp.
5. Thu **phản hồi định lượng/định tính** cùng tín hiệu chất lượng.
6. Quyết định **giữ, cải thiện, mở rộng, đổi hướng hoặc dừng**.

~~~mermaid
flowchart TD
    A["Vấn đề người dùng / Product Goal"] --> B["Giả thuyết cần kiểm chứng"]
    B --> C["Chọn lát dọc nhỏ, có giá trị"]
    C --> D["Phát triển + tích hợp + DoD"]
    D --> E{"Đủ điều kiện thử hoặc release?"}
    E -->|"Chưa"| F["Giải quyết chất lượng, vận hành hoặc thẩm quyền"]
    F --> E
    E -->|"Có"| G["Cho nhóm người dùng phù hợp trải nghiệm"]
    G --> H["Quan sát hành vi + hỏi nguyên nhân + theo dõi lỗi"]
    H --> I{"Bằng chứng hỗ trợ giả thuyết?"}
    I -->|"Có / đủ tự tin"| J["Mở rộng hoặc chọn lát kế tiếp"]
    I -->|"Chưa rõ"| K["Điều chỉnh cách đo hoặc thử thêm"]
    I -->|"Không"| L["Sửa giải pháp, đổi hướng hoặc dừng"]
    J --> B
    K --> B
    L --> B
~~~

Đây là **mô hình học hỏi**, không phải một quy trình công việc bắt buộc hay bảo đảm nhân quả. Trong thực tế, nhóm có thể phỏng vấn trước khi code, kiểm tra prototype, quan sát một nhóm nhỏ hoặc release theo giai đoạn. Chọn kênh phản hồi theo **rủi ro và điều chưa biết**.

### 4.1. Giả thuyết nên đủ cụ thể

**Mơ hồ:** “Tính năng AI sẽ làm học viên thích học hơn.”

**Có thể kiểm chứng hơn:**

> “Với học viên mới luyện Java, nếu sau khi chọn đáp án sai họ được xem lời giải ngắn gắn với khái niệm đang học, thì nhiều người sẽ hoàn tất câu ôn tập kế tiếp hơn so với trải nghiệm chỉ báo sai, trong khi thời gian phản hồi và lỗi hiển thị không vượt ngưỡng chấp nhận.”

Từ giả thuyết, nhóm có thể thử **lời giải ngắn do giảng viên biên soạn** trước, chưa cần hệ thống AI. Đây là cách giảm chi phí kiểm tra **giá trị của lời giải**, thay vì buộc phải kiểm chứng cả giá trị và một công nghệ phức tạp cùng lúc.

## 5. Xếp hạng giả định trước khi chia công việc

Một yêu cầu lớn chứa nhiều giả định khác loại. Không phải lúc nào lát có nhiều giao diện nhất cũng giúp học nhanh nhất.

### Các loại bất định

| Loại giả định | Câu hỏi | Cách thu bằng chứng phù hợp |
| --- | --- | --- |
| **Nhu cầu (desirability)** | Học viên có thật sự cần giải thích chi tiết sau câu sai? | Phỏng vấn, quan sát, thử bản đơn giản với người học. |
| **Dễ sử dụng (usability)** | Học viên có tìm thấy và hiểu nút xem lời giải? | Task-based usability test, quan sát lỗi/nhầm thao tác. |
| **Giá trị (value/outcome)** | Lời giải có giúp họ làm câu tiếp theo tốt hơn không? | Đo hành vi và chất lượng học tập, kết hợp định tính. |
| **Khả thi kỹ thuật (feasibility)** | Logic chấm và trả phản hồi có đúng dưới tải và tình huống lỗi? | Spike kỹ thuật, prototype, integration/performance tests. |
| **Khả năng vận hành (operability)** | Có giám sát, xử lý lỗi, hỗ trợ khi hệ thống chấm bị chậm không? | Thử nghiệm vận hành, diễn tập khôi phục phù hợp. |
| **An toàn/tuân thủ** | Có lộ đáp án cá nhân hoặc sử dụng dữ liệu trái quyền không? | Threat modeling và kiểm thử bảo mật với người có thẩm quyền. |
| **Khả năng kinh doanh (viability)** | Chi phí tạo nội dung lời giải có phù hợp nguồn lực không? | Thử với phạm vi nhỏ, đo thời gian biên soạn và vận hành. |

### 5.1. Bản đồ giả định

Đối với mỗi giả định, ghi:

- **Mức ảnh hưởng nếu sai:** nhỏ, trung bình, lớn.
- **Mức tự tin hiện tại:** có bằng chứng thực hay chỉ dự đoán?
- **Chi phí kiểm chứng:** phỏng vấn, prototype hay Increment thật?
- **Rủi ro thử nghiệm:** ảnh hưởng ai, có cần giới hạn đối tượng?
- **Lựa chọn sau thử:** kết quả nào khiến nhóm đổi kế hoạch?

Nên ưu tiên các giả định **tác động lớn, chưa chắc chắn và có thể kiểm chứng tương đối rẻ**, nhưng không được bỏ qua kiểm soát an toàn bắt buộc chỉ vì chúng khó thử.

### 5.2. Đừng dùng Increment để kiểm tra một câu hỏi có thể hỏi trước

Nếu chưa rõ người học muốn lời giải văn bản hay video, vài buổi phỏng vấn và một prototype có thể giúp nhóm hiểu cách họ diễn đạt nhu cầu. Điều đó không thay thế việc kiểm chứng sản phẩm chạy thật, nhưng giúp **tránh xây sai lát đầu tiên**.

Một prototype chưa đạt DoD **không nên bị báo thành Increment Done**. Cách làm hữu ích là phân biệt rõ **hoạt động khám phá** với **bước tiến của sản phẩm**.

## 6. Chia lát dọc: từ thao tác người dùng tới dữ liệu thật

Một lỗi phổ biến là chia yêu cầu theo lớp kỹ thuật:

> Database → Backend → Frontend → QA → Integration.

Mỗi bộ phận có thể xong phần mình nhưng đến cuối vẫn không có hành vi đầu cuối. Phản hồi người dùng phải chờ tích hợp toàn bộ.

**Vertical slicing** là chia theo **hành vi hoàn chỉnh đủ nhỏ**, đi qua những lớp cần thiết: giao diện, nghiệp vụ, dữ liệu, tích hợp, kiểm thử và điều kiện vận hành trong phạm vi lát đó.

~~~mermaid
flowchart LR
    subgraph H["Chia ngang theo lớp: phải đợi ghép"]
      D1["Toàn bộ DB"] --> D2["Toàn bộ API"] --> D3["Toàn bộ UI"] --> D4["QA cuối kỳ"]
    end
    subgraph V["Chia dọc theo giá trị: mỗi lát đủ dùng"]
      S1["Lát 1:\n1 câu + nộp + phản hồi"] --> S2["Lát 2:\ngiải thích câu sai"]
      S2 --> S3["Lát 3:\nđi tới bài ôn tập"]
    end
~~~

Sơ đồ đơn giản hóa cách làm; thực tế các nhóm có thể làm nhiều việc song song và vẫn cần tích hợp. Điều quan trọng là **đơn vị kiểm tra kết quả** được chọn theo hành vi người dùng, không phải theo ranh giới nghề nghiệp.

### 6.1. Đối chiếu một yêu cầu

**Yêu cầu lớn:** “Làm hệ thống kiểm tra kiến thức Java hoàn chỉnh.”

**Chia ngang yếu:**

- PBI 1: thiết kế toàn bộ cơ sở dữ liệu câu hỏi.
- PBI 2: xây tất cả API chấm điểm.
- PBI 3: xây tất cả màn hình câu hỏi.
- PBI 4: kiểm thử tích hợp sau khi ba PBI xong.

**Chia dọc có thể kiểm chứng:**

- PBI A: học viên có quyền trả lời **một câu trắc nghiệm** và xem phản hồi đúng/sai.
- PBI B: với câu trả lời sai, học viên xem **một lời giải ngắn đúng ngữ cảnh**.
- PBI C: từ lời giải, học viên mở **một nội dung ôn tập liên quan**.
- PBI D: người học xem lại **kết quả đã lưu** của một lượt làm bài.

Mỗi PBI phải đáp ứng **acceptance criteria và DoD** khi được coi là Done. Nếu các PBI này được triển khai như những Increment lần lượt tích hợp vào sản phẩm, nhóm có thể quan sát người học sau từng phần; không phải chờ tất cả D mới xin phản hồi.

### 6.2. Lát dọc không đồng nghĩa mỗi story tự đứng một mình hoàn toàn

Một lát mới có thể **bổ sung** hành vi lên sản phẩm và Increment trước đó. PBI B sử dụng khả năng nộp đáp án từ PBI A; điều cần giữ là **bản tích hợp sau B có thể sử dụng và đạt DoD**, chứ không bắt B tự triển khai lại toàn bộ A.

Cũng không nên bắt mỗi lát là một microservice, một repository hay một nhóm độc lập. **Ranh giới sản phẩm và hành vi** là trọng tâm của chia lát.

## 7. Mười kỹ thuật chia nhỏ yêu cầu lớn

Khi một epic quá lớn, hãy thử các hướng chia sau. Không kỹ thuật nào là quy tắc bắt buộc; lựa chọn phải giữ **giá trị và an toàn**.

| Kỹ thuật | Câu hỏi gợi ý | Ví dụ trên nền tảng học |
| --- | --- | --- |
| **Theo bước quy trình** | Người dùng cần bước đầu có ích nào? | Nộp một câu trước; sau đó mới làm bài nhiều câu và xem tổng kết. |
| **Theo biến thể dữ liệu** | Có thể bắt đầu với loại dữ liệu phổ biến nhất? | Câu nhiều lựa chọn một đáp án; sau đó câu nhiều đáp án hoặc điền code. |
| **Theo quy tắc nghiệp vụ** | Quy tắc nào đơn giản nhưng tạo hành vi thật? | Chấm một đáp án chính xác; sau đó thêm điểm từng phần hoặc quy tắc thi lại. |
| **Theo kênh/giao diện** | Một kênh có thể cung cấp giá trị trước? | Giao diện web đáp ứng thiết bị phổ biến; sau đó tối ưu trải nghiệm offline. |
| **Theo nhóm người dùng có quyền** | Đối tượng thử nào đại diện và an toàn? | Một lớp học thử được cấp quyền trước khi mở rộng. |
| **Theo phạm vi nội dung** | Có thể thử một loại bài hoặc một chủ đề? | Câu hỏi Java cơ bản, sau đó mở thêm chủ đề khác. |
| **Theo mức độ tự động hóa** | Có thể làm bước thủ công minh bạch để học giá trị? | Giảng viên biên soạn lời giải; chưa cần AI tự sinh lời giải. |
| **Theo độ phong phú trải nghiệm** | Hành vi cơ bản nào đủ hữu ích trước các tiện ích nâng cao? | Phản hồi đúng/sai trước dashboard thống kê chi tiết. |
| **Theo rủi ro/kiến thức cần học** | Lát nào kiểm chứng giả định quan trọng nhất? | Thử lời giải với nhóm nhỏ để xem có giúp người học tiếp tục không. |
| **Theo đường tích hợp bên ngoài** | Có thể bắt đầu với một đường gọi thật được kiểm soát? | Kết nối một bộ câu hỏi thật trước khi thêm nhiều nhà cung cấp nội dung. |

### 7.1. Chia theo trường hợp phổ biến trước ngoại lệ

Ví dụ, bản đầu hỗ trợ câu hỏi **một đáp án đúng**; bản sau hỗ trợ nhiều đáp án, điểm một phần và câu tự luận. Cách chia có thể hợp lý nếu bản đầu **thật sự hoàn chỉnh trong phạm vi một đáp án**, và không vô tình chấm sai hoặc mở ra những loại câu hỏi chưa hỗ trợ.

**Phạm vi được giới hạn phải hiển thị rõ** cho người dùng. Nếu hệ thống âm thầm nhận loại câu hỏi không hỗ trợ rồi trả điểm sai, đó không phải lát nhỏ an toàn.

### 7.2. Chia theo đối tượng không được phá quyền truy cập

Release cho một lớp thử là cách giới hạn quy mô, nhưng không được hiểu là **được bỏ xác thực, kiểm tra quyền hoặc bảo vệ dữ liệu** vì “chỉ có 20 người”. Các điều kiện an toàn thiết yếu phải đúng ngay với nhóm nhỏ.

### 7.3. Chia theo rủi ro không có nghĩa chỉ làm thử nghiệm nội bộ mãi

Một **spike** về thư viện chấm code có thể giải quyết câu hỏi kỹ thuật; nhưng nếu chỉ có spike mà không bao giờ tạo hành vi người dùng, nhóm vẫn chưa kiểm chứng giá trị. Sau spike, nên chọn một lát đủ nhỏ để tích hợp thật và nhận phản hồi phù hợp.

### 7.4. Chia theo thời gian không thay thế chia giá trị

“Làm epic này trong ba ngày đầu, ba ngày giữa, ba ngày cuối” chỉ chia lịch. Nếu sau mỗi chặng không có khả năng rõ để kiểm tra, đó chưa phải chia Increment có ích.

## 8. Cách xác định lát nhỏ nhất đủ học được điều quan trọng

Trong nhiều trường hợp có nhiều lát hợp lý. Hãy chọn bằng quy trình ngắn:

1. **Chọn câu hỏi cần học:** ví dụ “Người học có hiểu thông báo sai và biết làm gì tiếp không?”
2. **Xác định hành vi nhỏ nhất trả lời được:** học viên làm một câu, được báo sai và có lời giải ngắn.
3. **Loại tính năng không cần cho câu hỏi:** chưa cần xếp hạng, AI, phân tích toàn khóa.
4. **Giữ điều kiện đúng và an toàn:** xác thực/quyền, đáp án đúng, dữ liệu không lộ, lỗi được xử lý.
5. **Xác định nhóm thử và cách quan sát:** học viên mới ở một lớp Java, nhiệm vụ cụ thể và phản hồi.
6. **Chọn ngưỡng ra quyết định mang tính giả thuyết:** điều gì cho thấy nên tiếp tục/đổi hướng?
7. **Đánh giá khả năng hoàn tất:** nếu vẫn quá lớn, chia theo quy tắc, dữ liệu hoặc hành vi tiếp mà không làm mất tính hoàn chỉnh.

### Ma trận quyết định lát ứng viên

| Lát ứng viên | Giá trị có thể nhận ngay | Khả năng học | Chi phí/rủi ro | Nhận xét |
| --- | --- | --- | --- | --- |
| Tạo mọi bảng dữ liệu câu hỏi | Chưa có hành vi học viên | Thấp về giá trị người dùng | Có thể thấp cục bộ, cao khi tích hợp muộn | Là task kỹ thuật, không nên gọi Increment độc lập. |
| Một câu + nộp + đúng/sai | Có hành vi đầu cuối rõ | Biết mức dễ dùng và lỗi xử lý | Phù hợp nếu kiểm thử/DoD rõ | Ứng viên lát đầu tốt. |
| Toàn bộ bảng xếp hạng và huy hiệu | Có thể tạo hứng thú về sau | Chưa kiểm tra được vấn đề hiểu câu sai | Phạm vi lớn | Nên chờ bằng chứng ưu tiên. |
| Một câu sai + lời giải ngắn | Giúp người học hiểu sai ở đâu | Kiểm chứng trực tiếp giả thuyết lời giải | Cần nội dung đúng và cách đánh giá | Ứng viên lát tiếp theo có giá trị học cao. |
| Hệ thống AI tự sinh mọi lời giải | Nhiều khả năng nếu hoạt động tốt | Trộn giả định giá trị và tính khả thi AI | Rủi ro sai nội dung/chi phí cao | Nên kiểm chứng nhu cầu bằng lời giải biên soạn trước. |

**Đừng áp một công thức “càng ít ngày càng tốt” cứng nhắc.** Kích thước phù hợp phụ thuộc năng lực nhóm, độ rủi ro, phụ thuộc và cách thu phản hồi. Điều có ích là **phần đầu đủ nhỏ để được hoàn tất và quan sát trước khi quyết định đầu tư phần lớn kế hoạch**.

## 9. Ví dụ xuyên suốt: biến epic luyện tập thành chuỗi Increment

**Product Goal giả định:** “Giúp học viên mới học Java luyện tập đều đặn, hiểu lỗi sai và hoàn thành các bài ôn tập cốt lõi.”

**Vấn đề quan sát ban đầu:** nhiều học viên mở bài trắc nghiệm nhưng bỏ dở sau khi trả lời sai. Chưa rõ nguyên nhân chính.

**Epic đề xuất:** “Xây hệ thống luyện tập và gợi ý ôn tập cá nhân hóa.”

### 9.1. Chuỗi Increment ứng viên

| Phần | Người học có thể làm gì? | Giả thuyết/tín hiệu cần học | Chưa làm để giữ nhỏ |
| --- | --- | --- | --- |
| **I1 – Một câu trắc nghiệm hoạt động thật** | Mở một câu Java có quyền, chọn đáp án, nộp và nhận phản hồi đúng/sai. | Học viên có tìm và sử dụng được luồng nộp bài không? | Chưa có dashboard, AI, bài thi nhiều câu. |
| **I2 – Giải thích câu trả lời sai** | Sau khi nộp sai, xem lời giải ngắn, đúng nội dung và không lộ trước khi nộp. | Lời giải có giúp hiểu nguyên nhân và tiếp tục làm câu khác không? | Chưa tự tạo lời giải bằng AI, chưa cá nhân hóa. |
| **I3 – Đi tới nội dung ôn tập liên quan** | Từ lời giải mở một bài học phù hợp với kiến thức thiếu. | Học viên có đi ôn tập thay vì rời sản phẩm không? | Chưa tạo lộ trình học tự động toàn khóa. |
| **I4 – Nhớ trạng thái luyện tập** | Xem lại kết quả câu đã làm trong phạm vi đã hỗ trợ. | Việc lưu tiến độ có giúp người học quay lại dễ hơn không? | Chưa có thống kê giáo viên nâng cao. |
| **I5 – Mở rộng có điều kiện** | Thực hiện nhiều câu/biến thể đã được ưu tiên sau phản hồi. | Các cải tiến có giữ kết quả tốt khi mở rộng không? | Chưa xây mọi nhánh tương lai cùng lúc. |

Bảng là **lộ trình ứng viên**, không phải hợp đồng phải làm đủ năm phần. Nếu sau I1, học viên không thể hiểu thông báo kết quả hoặc trải nghiệm nộp bài lỗi, nhóm nên **sửa vấn đề trước khi vội làm I2**. Nếu dữ liệu cho thấy người học cần một dạng hỗ trợ khác lời giải, PO có thể đổi thứ tự Product Backlog.

### 9.2. Mỗi Increment phải tích hợp vào sản phẩm

Để gọi I1 là Increment Done, không chỉ có màn hình:

- Câu hỏi được lấy từ nguồn dữ liệu thực phù hợp.
- Việc nộp đáp án được xử lý đúng và có phản hồi rõ.
- Người dùng không thể thao tác hoặc xem dữ liệu trái quyền.
- Có kiểm tra các trường hợp lỗi cần thiết.
- Chức năng hoạt động với phần sản phẩm hiện có, đạt DoD.

I2 bổ sung lời giải **trên luồng đã dùng được** của I1. Nhóm không cần triển khai lại I1, nhưng phải bảo đảm sau khi thêm I2, sản phẩm tích hợp vẫn đạt tiêu chuẩn chất lượng.

### 9.3. Bản đồ học sau mỗi lần phát hành

| Sau phần | Nên hỏi người học | Nên quan sát | Quyết định có thể phát sinh |
| --- | --- | --- | --- |
| **I1** | “Bạn có biết bấm gì để nộp và hiểu kết quả không?” | Tỷ lệ nộp thành công, lỗi, nơi thoát, ghi chú quan sát. | Sửa luồng thao tác hoặc cải thiện phản hồi cơ bản. |
| **I2** | “Lời giải có chỉ ra đúng lý do bạn sai không?” | Số lần mở lời giải, khả năng giải thích lại, tiếp tục câu kế. | Sửa nội dung/độ dài lời giải hoặc ưu tiên nội dung ôn tập. |
| **I3** | “Bài ôn tập có giúp bạn giải quyết điểm chưa hiểu?” | Click qua bài học, hoàn tất bài ôn, quay lại luyện tập. | Giữ liên kết thủ công hay thử gợi ý phù hợp hơn. |
| **I4** | “Bạn có tìm lại câu đã làm một cách dễ dàng không?” | Lượt quay lại, truy cập lịch sử, lỗi dữ liệu. | Cải thiện khả năng quay lại hoặc ngừng mở rộng tính năng không cần. |

Không chỉ đếm lượt click. Một học viên mở lời giải nhiều lần **có thể vì lời giải hữu ích hoặc vì khó hiểu**. Cần kết hợp hành vi và câu hỏi định tính để diễn giải.

## 10. Thiết kế user story và acceptance criteria đủ hẹp

Một user story có thể theo mẫu:

> **Là** học viên đã được cấp quyền luyện tập Java, **tôi muốn** nộp một đáp án cho câu hỏi trắc nghiệm và nhận phản hồi rõ ràng, **để** biết mình trả lời đúng hay sai và có thể tiếp tục.

Đây là cách diễn đạt nhu cầu; không phải bản đặc tả đầy đủ. Các câu hỏi cần trao đổi thêm:

- Người học có được sửa lựa chọn sau khi nộp không?
- Có giới hạn thời gian hay số lần nộp không?
- Khi mạng lỗi, giao diện thông báo thế nào?
- Câu hỏi có một hay nhiều đáp án đúng?
- Ai được xem đáp án đúng và ở thời điểm nào?
- Có lưu lại đáp án không, hay đây là lượt thử không lưu?
- Người dùng khác có thể xem lịch sử của học viên này không?

**Không cần giải hết mọi biến thể để có I1.** Nhưng phải xác định rõ **phạm vi và hành vi của những trường hợp được hỗ trợ**, nhất là dữ liệu và quyền.

### 10.1. Gherkin cho Increment I1

~~~gherkin
Feature: Trả lời một câu hỏi trắc nghiệm Java

Scenario: Học viên nộp đáp án hợp lệ
  Given học viên đã đăng nhập và có quyền luyện tập "Java cơ bản"
  And câu hỏi đang mở cho phép chọn đúng một đáp án
  When học viên chọn một đáp án hợp lệ và bấm "Nộp"
  Then hệ thống đánh giá theo quy tắc chấm điểm đã cấu hình
  And hiển thị phản hồi đúng hoặc sai rõ ràng
  And không cung cấp dữ liệu riêng của học viên khác

Scenario: Chưa chọn đáp án
  Given học viên có quyền làm câu hỏi
  And chưa chọn đáp án nào
  When học viên bấm "Nộp"
  Then hệ thống không ghi nhận câu trả lời hợp lệ
  And hướng dẫn học viên chọn đáp án trước khi nộp

Scenario: Không có quyền vào bài luyện tập
  Given tài khoản không có quyền truy cập bài luyện tập
  When tài khoản đó gửi yêu cầu nộp đáp án
  Then hệ thống từ chối theo chính sách
  And không tiết lộ đáp án hoặc tiến độ riêng tư trái quyền

Scenario: Dịch vụ xử lý nộp bài gặp lỗi
  Given học viên có quyền và đã chọn một đáp án
  And hệ thống không thể xử lý yêu cầu nộp bài
  When học viên bấm "Nộp"
  Then giao diện không thông báo sai rằng bài đã được ghi nhận thành công
  And hiển thị cách xử lý hoặc thử lại phù hợp

Scenario: Câu hỏi thuộc loại chưa được hỗ trợ
  Given bản tăng trưởng hiện tại chỉ hỗ trợ câu hỏi một đáp án đúng
  When học viên mở một câu hỏi ngoài phạm vi hỗ trợ
  Then hệ thống không chấm sai theo quy tắc một đáp án
  And hiển thị trạng thái hoặc hành động phù hợp với phạm vi sản phẩm
~~~

Những tình huống trên là **mẫu để thảo luận**; sản phẩm thật cần xác định chính xác chính sách lưu đáp án, giới hạn nộp, khả năng thử lại và thông điệp lỗi.

### 10.2. Gherkin cho Increment I2

~~~gherkin
Feature: Hiển thị lời giải sau câu trả lời sai

Scenario: Học viên sai và có lời giải
  Given học viên có quyền làm câu hỏi "JAVA-01"
  And học viên đã nộp một đáp án sai
  And lời giải đã được biên soạn và kiểm chứng cho "JAVA-01"
  When học viên xem kết quả
  Then hệ thống hiển thị lời giải ngắn gắn với đáp án đúng
  And lời giải được trình bày dễ đọc trong phạm vi thiết bị hỗ trợ

Scenario: Học viên chưa nộp
  Given học viên có quyền mở câu hỏi "JAVA-01"
  And chưa hoàn tất lần nộp theo quy tắc bài luyện tập
  When học viên đang chọn đáp án
  Then hệ thống không tiết lộ lời giải trước thời điểm được phép

Scenario: Thiếu nội dung lời giải
  Given một câu hỏi chưa có lời giải được phê duyệt
  When học viên đã nộp sai và xem kết quả
  Then hệ thống không tạo nội dung lời giải sai sự thật
  And hiển thị phản hồi phù hợp với phạm vi hỗ trợ đã công bố
~~~

Ở I2, “lời giải ngắn” có thể được giảng viên biên soạn; nhóm không cần AI nếu giá trị cần kiểm chứng chỉ là **có lời giải hay không**. Kiểm soát tính đúng đắn nội dung vẫn là điều kiện quan trọng.

## 11. Definition of Done bảo vệ sự hoàn chỉnh của lát nhỏ

**Acceptance criteria** mô tả hành vi cụ thể của một PBI; **Definition of Done (DoD)** là tiêu chuẩn chất lượng chính thức để một phần tiến bộ được coi là Increment hoàn tất trong Scrum.

Trong Scrum Guide 2020:

- Increment là bước tiến cụ thể hướng tới Product Goal.
- Mỗi Increment bổ sung vào những Increment trước đó và được kiểm tra để chúng hoạt động cùng nhau.
- Increment phải **có thể sử dụng** và đáp ứng DoD.
- Một PBI **chưa đáp ứng DoD không thể coi là một phần Increment**; có thể được đưa lại Product Backlog để xem xét tiếp.
- **Có thể tạo nhiều Increment trong một Sprint.**

### DoD minh họa cho I1/I2

| Nhóm | Ví dụ điều kiện hoàn tất |
| --- | --- |
| **Tích hợp** | Giao diện, logic chấm và nguồn dữ liệu hoạt động cùng sản phẩm hiện có. |
| **Hành vi** | Acceptance criteria, nhánh lỗi và trường hợp biên thiết yếu được kiểm chứng. |
| **Dữ liệu** | Không ghi/trả dữ liệu sai hoặc lộ dữ liệu người học khác. |
| **Phân quyền** | Các đường vào bài học và xem kết quả phải kiểm tra quyền phù hợp. |
| **Kiểm thử** | Kiểm thử tự động/thủ công phù hợp chạy và có kết quả; hồi quy không bị phá. |
| **Quan sát** | Có khả năng nhận diện lỗi nộp bài hoặc sự cố quan trọng theo nhu cầu vận hành. |
| **Tài liệu hỗ trợ** | Phần hướng dẫn, nội dung lời giải, thay đổi cấu hình cần thiết được cập nhật theo tiêu chuẩn. |
| **Tương thích** | Không làm hỏng những hành vi của phiên bản/Increment trước. |

Đây là **ví dụ**, không phải DoD chính thức của mọi nhóm. Nếu tổ chức đã có tiêu chuẩn chất lượng áp dụng, chúng là mức tối thiểu cần tuân thủ; nếu không, Scrum Team xây DoD phù hợp.

### 11.1. “Chia nhỏ” không đồng nghĩa trì hoãn lỗi nghiêm trọng

Không nên dùng các lát sau để “hoàn thiện” những điều **bắt buộc có từ đầu**, chẳng hạn:

- I1 cho phép xem kết quả người khác, hứa I3 sẽ thêm kiểm tra quyền.
- I1 chấm sai khi hai lần nộp cạnh tranh, hứa I4 mới sửa đúng đắn.
- I1 luôn thông báo thành công dù dữ liệu không được ghi.
- I1 dùng dữ liệu thật trái quy định với lý do “chỉ bản thử”.

Các phần chưa có thể là **năng lực mở rộng**, không phải **việc che một phần chưa đạt DoD**.

### 11.2. Nếu chưa Done, phải làm gì?

Nếu luồng đang tích hợp nhưng phát hiện kiểm thử phân quyền thất bại, phần đó **chưa được gọi là Increment Done**. Nhóm cần hoàn thiện phù hợp, trao đổi tác động với Product Owner và điều chỉnh kế hoạch. Không đổi nhãn Done chỉ vì Sprint Review sắp diễn ra.

## 12. Từ Increment đến phản hồi: thử với ai, ở đâu và khi nào?

Increment đã Done **có thể được bàn giao trước khi Sprint kết thúc**. **Sprint Review không phải cổng phát hành bắt buộc**, nhưng release phải phù hợp điều kiện an toàn, vận hành, thẩm quyền và nhu cầu sản phẩm.

### 12.1. Một số cách đưa Increment tới phản hồi

| Cách | Mục đích | Ưu điểm | Điều cần kiểm tra |
| --- | --- | --- | --- |
| **Thử nội bộ theo nhiệm vụ** | Phát hiện lỗi sử dụng và vấn đề ban đầu. | Dễ tổ chức sớm. | Người nội bộ có thể không đại diện người học thật. |
| **Nhóm học viên thử có chủ đích** | Kiểm tra hành vi và giá trị thực ở phạm vi nhỏ. | Phản hồi gần thực tế, giới hạn ảnh hưởng. | Quyền, đồng ý tham gia khi cần, hỗ trợ, chọn mẫu. |
| **Canary/rollout dần** | Quan sát độ tin cậy và hành vi ở mức rủi ro kiểm soát. | Có thể dừng trước khi ảnh hưởng rộng. | Ngưỡng dừng, monitoring, khả năng rollback. |
| **Feature flag** | Bật/tắt chức năng cho đối tượng định sẵn. | Tách deploy và release; mở rộng dần. | Flag không tự sửa lỗi dữ liệu hoặc thay DoD. |
| **Phát hành rộng** | Cung cấp giá trị cho toàn bộ đối tượng mục tiêu phù hợp. | Nhận dữ liệu sử dụng lớn hơn. | Rủi ro và khả năng hỗ trợ cao hơn. |
| **Prototype/phỏng vấn** | Học về nhu cầu, hiểu biết hoặc mô hình tương tác. | Ít chi phí trước khi xây. | Phản hồi trên mô phỏng không thay bằng chứng từ sử dụng thật. |

**Không phải mọi phản hồi đều cần một release production rộng.** Nhưng nếu câu hỏi liên quan khả năng vận hành trong điều kiện thật, ý định sử dụng lặp lại hoặc hành vi thực, một prototype tĩnh có thể chưa đủ.

### 12.2. Điều kiện release nên công khai

Trước khi mở I1 cho lớp thử, hỏi:

- Phạm vi nào **thực sự đã đạt DoD**?
- Nhóm nào được cấp quyền và họ được thông báo những giới hạn gì?
- Có điều kiện bảo mật, riêng tư, dữ liệu, hợp đồng hoặc vận hành nào?
- Người nào có thẩm quyền quyết định release theo tổ chức?
- Có giám sát lỗi, hỗ trợ và cách dừng/khôi phục tương xứng không?
- Những chỉ số và phản hồi nào sẽ được xem sau release?

**Scrum không quy định một chức danh duy nhất phải phê duyệt mọi release**. Tổ chức cần làm rõ quyền đó, không dùng Sprint Review làm cửa ký mặc định nếu không có ràng buộc thực.

## 13. Thiết kế kênh phản hồi trước khi viết tính năng

Nếu nhóm xây xong mới hỏi “đo bằng cách nào?”, nhiều dữ liệu cần thiết có thể không được thu hoặc người dùng không biết kênh góp ý.

### 13.1. Phản hồi định tính

Một số cách phù hợp:

- **Quan sát người học làm nhiệm vụ thật:** họ có tìm đúng câu hỏi, hiểu phản hồi, biết bước tiếp theo không?
- **Phỏng vấn ngắn sau tác vụ:** hỏi điều gì họ nghĩ sẽ xảy ra và điều gì khiến họ khó hiểu.
- **Phản hồi từ giảng viên/hỗ trợ:** phát hiện lỗi nội dung, nhu cầu bối cảnh và rào cản không thấy trong số liệu.
- **Phiên dùng thử có kịch bản:** cho học viên mới giải một câu thay vì chỉ hỏi họ có thích ý tưởng không.

Câu hỏi hữu ích thường là:

- “Bạn vừa muốn làm gì khi nhấn nút đó?”
- “Tại sao bạn dừng ở bước này?”
- “Bạn hiểu thông báo này theo cách nào?”
- “Nếu không có lời giải, bạn thường xử lý câu sai ra sao?”

Nên hạn chế câu hỏi dẫn dắt như “Tính năng mới tiện hơn đúng không?”, vì người dùng có thể trả lời lịch sự thay vì mô tả trải nghiệm thật.

### 13.2. Phản hồi định lượng

Dùng các sự kiện hoặc chỉ số có ý nghĩa:

| Sự kiện/đại lượng | Câu hỏi hỗ trợ | Rủi ro diễn giải |
| --- | --- | --- |
| **QuestionViewed** | Bao nhiêu người thật sự thấy câu hỏi? | Có thể đếm mở lại/trùng nếu không định nghĩa phiên. |
| **AnswerSubmitted** | Người học đã nộp thành công hay chỉ bấm nút? | Cần phân biệt yêu cầu gửi và xử lý thành công. |
| **AnswerFeedbackViewed** | Người học có nhìn thấy phản hồi không? | Nhìn thấy không chứng minh hiểu. |
| **ExplanationOpened** | Có ai tìm lời giải không? | Click cao có thể do hữu ích hoặc do thiếu rõ ràng. |
| **NextQuestionStarted** | Học viên có tiếp tục luyện tập không? | Phải xét động cơ, độ khó và bối cảnh nhóm. |
| **ReviewLessonOpened** | Liên kết ôn tập có được dùng không? | Mở bài không đồng nghĩa đã học xong. |
| **SubmissionError** | Có lỗi nộp bài hoặc timeout không? | Logging thiếu có thể khiến số lỗi thấp giả. |

### 13.3. Event phải có ngữ nghĩa rõ

Đừng ghi cùng tên **AnswerSubmitted** cho cả “người dùng nhấn nút” và “hệ thống xác nhận đã lưu”. Hai sự kiện này hỗ trợ hai câu hỏi khác nhau. Nếu không phân biệt, tỷ lệ hoàn tất có thể bị thổi phồng.

Một định nghĩa tối thiểu:

~~~text
Event: AnswerSubmissionSucceeded
Đối tượng: người học có quyền trong bài luyện tập đã được hỗ trợ
Điều kiện phát: hệ thống xử lý và xác nhận kết quả hợp lệ
Đơn vị đếm: một lần nộp được chấp nhận, có cách xử lý trùng
Thuộc tính cần thiết: loại câu hỏi, phiên bản trải nghiệm, nhóm thử (nếu hợp lệ)
Không thu: nội dung cá nhân không cần thiết hoặc dữ liệu nhạy cảm trái mục đích
Phục vụ: tỷ lệ nộp thành công và phát hiện lỗi theo nhóm/phiên bản
~~~

Sự kiện là **công cụ quan sát**, không phải lý do thu mọi dữ liệu có thể thu. Cần tuân thủ quyền riêng tư, thời gian lưu trữ và cơ chế thông báo/đồng ý theo chính sách áp dụng.

## 14. Chọn chỉ số theo giả thuyết, có guardrails

Một nhóm nên tách **chỉ số chính để học**, **chỉ số chất lượng/an toàn không được đánh đổi** và **tín hiệu chẩn đoán**.

### Ví dụ cho I2 – lời giải câu sai

| Loại | Ví dụ | Mục đích |
| --- | --- | --- |
| **Outcome gần** | Tỷ lệ người nộp sai nhưng tiếp tục câu ôn tập tiếp theo trong khoảng thời gian được định nghĩa. | Kiểm tra liệu lời giải hỗ trợ tiếp tục học không. |
| **Tín hiệu hiểu bài** | Người học có thể tự giải thích lý do sai hoặc trả lời câu tương tự sau đó. | Tránh đồng nhất click với học tập. |
| **Tín hiệu sử dụng** | Tỷ lệ mở lời giải, thời gian đọc phù hợp, phản hồi định tính. | Chẩn đoán giao diện/nội dung. |
| **Guardrail kỹ thuật** | Tỷ lệ lỗi nộp, độ trễ phản hồi, sự cố phân quyền và dữ liệu. | Phát hiện hại do thay đổi. |
| **Guardrail trải nghiệm** | Người học không bị che đáp án quá sớm, không bị tăng thao tác gây nhầm. | Bảo vệ người dùng khỏi một cải tiến phản tác dụng. |
| **Chi phí duy trì** | Thời gian tạo/cập nhật lời giải và số lỗi nội dung. | Đánh giá tính khả thi khi mở rộng. |

### 14.1. Mẫu giả thuyết có điều kiện

> “Trong nhóm học viên mới đã đồng ý tham gia thử nghiệm phù hợp, hiển thị lời giải ngắn sau câu sai sẽ làm tăng tỷ lệ tiếp tục câu ôn tập kế tiếp so với trải nghiệm chỉ báo sai. Chúng ta theo dõi lỗi/độ trễ và đánh giá cả phản hồi định tính trước khi quyết định mở rộng.”

Không cần biến mọi giả thuyết thành một con số độ chính xác cao khi chưa có dữ liệu nền. Nếu chưa biết mức hiện tại, **đo baseline hoặc thử khám phá trước**, rồi đặt ngưỡng ra quyết định phù hợp.

### 14.2. “North Star Metric” không đủ thay cả hệ thống

Một chỉ số tổng như “tỷ lệ quay lại học” có thể giúp định hướng, nhưng thường thay đổi vì nhiều yếu tố: kỳ thi, chất lượng nội dung, thời khóa biểu, khuyến mãi. Một lát nhỏ cần **tín hiệu gần với hành vi nó tác động**, đồng thời kiểm tra chất lượng và kết quả dài hạn khi có đủ thời gian.

## 15. Đọc dữ liệu phản hồi mà không tự kết luận quá mức

Giả sử nhóm thử I2 trên hai lớp có số học viên như nhau:

| Nhóm quan sát | Người từng trả lời sai | Người tiếp tục câu ôn tập | Tỷ lệ quan sát |
| --- | ---: | ---: | ---: |
| **A – chỉ thông báo sai** | 100 | 38 | 38% |
| **B – có lời giải ngắn** | 100 | 54 | 54% |

Chênh lệch quan sát là:

\[
54\%-38\%=16\ \text{điểm phần trăm}
\]

Đây chỉ là **ví dụ dữ liệu minh họa**, không phải kết quả nghiên cứu và **chưa đủ chứng minh lời giải là nguyên nhân**. Hai lớp có thể khác về trình độ, độ khó câu hỏi, người dạy hoặc động lực. Số lượng mẫu và phương pháp phân nhóm có thể chưa đủ để rút kết luận chắc chắn.

### 15.1. Những câu hỏi phải xem trước khi ra quyết định

1. Hai nhóm được chọn thế nào? Có ngẫu nhiên hay có khác biệt biết trước?
2. Câu hỏi và thời điểm thực hiện có tương đương không?
3. Người học có bị đo trùng nhiều lần hoặc loại khỏi mẫu theo cách gây lệch không?
4. “Tiếp tục” được định nghĩa là nhấn nút hay thực sự bắt đầu câu kế tiếp?
5. Có lỗi chỉ xuất hiện ở một phiên bản không?
6. Lời giải có sai nội dung hoặc vô tình tiết lộ đáp án trước khi nộp không?
7. Có quan sát định tính để hiểu **vì sao** một số người vẫn rời bỏ không?
8. Có đủ thời gian và số mẫu để đánh giá ổn định khi mở rộng không?

Nếu cần đánh giá tác động nhân quả đáng tin hơn, có thể thiết kế **thử nghiệm có đối chứng và phân nhóm phù hợp**, kèm xem xét thống kê và đạo đức thử nghiệm. Trong nhiều tình huống, một **usability test nhỏ** đã đủ chỉ ra lỗi thiết kế cần sửa trước khi làm phép so sánh quy mô lớn.

### 15.2. Quyết định nên dựa trên bằng chứng và rủi ro

Một kết quả như trên có thể cho thấy **lời giải đáng tiếp tục khám phá**, chứ không tự động cho phép mở cho toàn bộ người dùng. Nếu lỗi nộp bài tăng hoặc nội dung lời giải thiếu chính xác, nhóm cần khắc phục trước.

**Đừng tối ưu chỉ số bằng cách gây hại trải nghiệm.** Ví dụ, buộc người học nhấn “Câu tiếp theo” mới đóng hộp thoại có thể làm số lần nhấn tăng mà không cải thiện hiểu bài.

## 16. Tối ưu thời gian đến phản hồi bằng số đo dòng công việc

Lát nhỏ có thể làm nhanh hơn, nhưng nếu nằm chờ review, kiểm thử hoặc release lâu, phản hồi người dùng vẫn đến muộn.

### 16.1. Bốn mốc cần phân biệt

- **Lead time:** thời gian từ điểm yêu cầu được ghi nhận/chấp nhận đến mốc hoàn tất theo chính sách đã định nghĩa.
- **Cycle time:** thời gian từ lúc công việc bắt đầu tới khi hoàn tất theo Definition of Workflow.
- **Time from Done to Released:** khoảng chờ sau khi Increment đạt DoD tới khi nhóm người dùng có thể sử dụng.
- **Time to feedback:** thời gian từ lúc đặt câu hỏi/ra quyết định thử đến khi có bằng chứng đủ để cân nhắc bước tiếp theo.

Nhóm cần **công bố ranh giới đo**. Một story có thể Done vào ngày 4, release ngày 6 và có phản hồi sau ngày 9; không nên báo “feedback lead time 4 ngày” chỉ vì cycle time tới Done là bốn ngày.

### 16.2. Ví dụ bản đồ luồng một lát nhỏ

~~~mermaid
flowchart LR
    A["Làm rõ và chia lát\n0,5 ngày"] --> B["Chờ quyết định nội dung\n1 ngày"]
    B --> C["Lập trình + test\n1,5 ngày"]
    C --> D["Chờ review\n1 ngày"]
    D --> E["Tích hợp, đạt DoD\n0,5 ngày"]
    E --> F["Chờ đủ điều kiện release\n0,5 ngày"]
    F --> G["Thử với học viên\n1 ngày"]
    G --> H["Phân tích phản hồi và quyết định"]
~~~

Tổng thời lượng minh họa từ bắt đầu làm rõ đến hoàn tất thử là:

\[
0{,}5+1+1{,}5+1+0{,}5+0{,}5+1=6\ \text{ngày làm việc}
\]

Trong ví dụ, phần **chờ** là 2,5 ngày (quyết định nội dung, review và release). Nếu rút thời gian lập trình từ 1,5 xuống 1 ngày nhưng giữ nguyên các hàng chờ, phản hồi chỉ tới sớm hơn 0,5 ngày. Nhóm nên xem các điểm nghẽn thực trước khi tăng tốc code.

Các số liệu trên là **giả định minh họa**, không phải chuẩn thời gian cho mọi story hoặc năng lực cá nhân.

### 16.3. Theo dõi thêm các tín hiệu

| Chỉ số | Dùng để hiểu | Lưu ý |
| --- | --- | --- |
| **WIP (work in progress)** | Có quá nhiều lát đang dở không? | WIP cao thường làm hàng chờ dài; ngưỡng theo bối cảnh. |
| **Work item age** | Lát nào đang mở quá lâu và vì sao? | Hỗ trợ xử lý blocker, không xếp hạng cá nhân. |
| **Throughput** | Hệ thống hoàn tất được bao nhiêu mục trong một khoảng? | Đếm nhiều ticket hơn không tự chứng minh giá trị. |
| **Blocked time** | Đang chờ quyền, nội dung, review hoặc môi trường bao lâu? | Ghi lý do rõ, tránh giấu điểm nghẽn. |
| **Lỗi sau release** | Giao sớm có làm chất lượng giảm không? | Đọc cùng mức nghiêm trọng, số người bị ảnh hưởng. |
| **Thời gian tới phản hồi hữu ích** | Nhóm học và thay đổi ưu tiên nhanh không? | Nhanh nhưng dữ liệu sai lệch có thể gây quyết định tệ. |

### 16.4. Đừng dùng kích thước story để chấm năng suất cá nhân

Nếu dùng story points, điểm chỉ hỗ trợ trao đổi/ước lượng theo bối cảnh nhóm. Không nên quy “người A làm 13 points” thành năng suất hơn “người B làm 8 points”. Nhiều công việc quan trọng như kiểm thử, hỗ trợ review, gỡ phụ thuộc và chăm sóc chất lượng là đóng góp tập thể.

## 17. Scrum: dùng Sprint Goal và Product Backlog để chọn lát có giá trị

Trong **Scrum**, người dùng và kết quả sản phẩm được kết nối với những cấu trúc có mục đích:

- **Product Owner:** chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog hiệu quả, bao gồm thứ tự các mục.
- **Developers:** chọn các Product Backlog Items cho Sprint trong Sprint Planning sau trao đổi và tự lập kế hoạch thực hiện để tạo Increment đạt DoD.
- **Scrum Master:** hỗ trợ Scrum được áp dụng đúng, Scrum Team hiệu quả, giúp trở ngại được tháo gỡ.
- **Product Goal:** định hướng dài hạn của sản phẩm.
- **Sprint Goal:** mục tiêu chung trong Sprint, giúp nhóm thích ứng kế hoạch mà vẫn tập trung.
- **Increment/DoD:** tiêu chuẩn có thể sử dụng, không chỉ “đã làm một phần”.
- **Sprint Review:** kiểm tra kết quả Sprint và cùng bên liên quan xác định điều chỉnh tiếp theo; **không phải cổng bắt buộc để release**.
- **Sprint Retrospective:** cải tiến cách phối hợp và chất lượng, gồm cả năng lực chia lát/thu phản hồi.

### 17.1. Một Sprint Goal tốt không phải danh sách ticket

**Danh sách yếu:** “Hoàn thành UI, API, database và ba báo cáo.”

**Mục tiêu có giá trị hơn:**

> “Học viên mới có thể làm một câu trắc nghiệm Java và nhận phản hồi đúng/sai đáng tin cậy để tiếp tục luyện tập.”

Một Sprint có thể tạo **nhiều Increment**, nhưng không nhất thiết mọi PBI phải phát hành riêng. Những lát nhỏ giúp nhóm có cơ hội giao/phản hồi trước Sprint Review khi thích hợp.

### 17.2. Khi phản hồi đến giữa Sprint

Nếu I1 được thử sớm và học viên hiểu nhầm phản hồi, Developers và PO trao đổi tác động tới Sprint Goal. Có thể điều chỉnh Sprint Backlog để giải quyết vấn đề quan trọng, giữ DoD và mục tiêu chung. **Không nên bắt nhóm làm tất cả ticket ban đầu bất chấp bằng chứng**.

Tuy nhiên, nhận phản hồi mới không có nghĩa bất kỳ ai cũng được giao task trực tiếp làm thay đổi kế hoạch ngầm. Trong Scrum, Product Owner chịu trách nhiệm thứ tự Product Backlog, Developers quản lý kế hoạch thực hiện, còn các bên phối hợp minh bạch.

## 18. Kanban và XP: giảm lãng phí trước khi tăng tốc release

### 18.1. Kanban: nhìn thấy nơi một lát đang chờ

Một bảng luồng minh họa:

~~~text
Ready -> Develop (WIP <= 3) -> Review (WIP <= 2) -> Verify -> Done
                                                |
                                               blocked

Done -> Release ready -> Released -> Feedback observed
~~~

Các cột và giới hạn WIP trên chỉ là **ví dụ thiết kế**, không phải cấu trúc Kanban bắt buộc. Nếu các lát nhỏ liên tục nằm chờ review ba ngày, hãy xử lý hàng chờ và khả năng review, không tiếp tục mở thêm việc mới để mọi người “có task”.

**Chính sách hữu ích:** khi cột Review đầy, Developers ưu tiên giúp các mục đang chờ hoàn tất hoặc làm rõ trở ngại; chỉ kéo việc mới khi phù hợp. Cần có đường riêng cho sự cố khẩn khi sản phẩm yêu cầu, với tiêu chí rõ để tránh mọi yêu cầu đều thành expedite.

### 18.2. XP: giữ chất lượng ở mỗi lát

Các thực hành **Extreme Programming (XP)** hỗ trợ giao tăng dần:

- **TDD:** viết kiểm thử cho hành vi mong đợi, triển khai đủ, rồi refactor.
- **Continuous Integration:** tích hợp thường xuyên, phát hiện lỗi sớm.
- **Refactoring:** giữ khả năng thay đổi khi các lát liên tục được bổ sung.
- **Pair Programming/review:** trao đổi hiểu biết nghiệp vụ và giảm thiếu sót.
- **Simple Design:** chưa xây AI, hàng chục cấu hình hoặc kiến trúc dự đoán nếu lát đầu không cần.
- **Small Releases:** tạo khả năng phản hồi với phạm vi phù hợp, không xem ngày cuối Sprint là cửa release mặc định.

Những thực hành này không loại bỏ nhu cầu hiểu người dùng. Nhóm có thể viết mã rất tốt cho một tính năng **không ai cần**. Vì vậy, kỹ thuật và phản hồi giá trị phải đi cùng nhau.

### 18.3. Lean: tối ưu toàn bộ vòng học hỏi

Một nhóm có thể phát hành hằng ngày nhưng **không quan sát người dùng**, hoặc thu hàng trăm ý kiến nhưng **không thay đổi backlog**. Lean nhắc nhóm xem toàn bộ luồng từ nhu cầu → Increment → sử dụng → học → quyết định, giảm **chờ, bàn giao, làm lại và WIP**.

## 19. Phụ thuộc liên nhóm không được trở thành lý do để trì hoãn mọi phản hồi

Một lát đầu cuối có thể đi qua **nhiều nhóm chuyên môn**: nội dung câu hỏi, ứng dụng web, dịch vụ chấm điểm, Identity và vận hành. Nếu mỗi nhóm chỉ hoàn tất phần mình rồi bàn giao tuần tự, nhóm sản phẩm có thể không nhận được Increment đúng hạn.

### 19.1. Phối hợp theo hành vi thay vì giao nguyên tầng

| Tình huống | Cách dễ gây chờ | Cách phối hợp có giá trị hơn |
| --- | --- | --- |
| API chấm điểm và UI | Backend hoàn thành toàn bộ API, sau đó frontend bắt đầu. | Thống nhất hợp đồng cho một câu hỏi, tích hợp lát đầu sớm. |
| Nội dung lời giải | Đợi giảng viên biên soạn mọi lời giải toàn khóa. | Chọn vài câu quan trọng có lời giải được kiểm chứng để thử giá trị. |
| Quyền truy cập | “Tính năng xong rồi mới nhờ Identity kiểm tra.” | Làm rõ quyền ngay khi chia lát, có negative tests từ đầu. |
| Môi trường test | Đợi cuối Sprint mới có môi trường tích hợp. | Thiết lập môi trường và test hợp đồng phù hợp sớm. |
| Quyết định release | Đợi cuộc họp định kỳ không có nghĩa vụ thực. | Công khai điều kiện release, đầu mối và phương án đưa vào thử khi đủ chuẩn. |

### 19.2. Một thay đổi hợp đồng cần có chủ sở hữu

Nếu dịch vụ chấm điểm thay cấu trúc phản hồi, UI và phần lưu tiến độ có thể bị ảnh hưởng. Cần xác định **ai sở hữu hợp đồng, consumer nào phụ thuộc, kiểm thử tương thích và thời điểm chuyển đổi**.

Không nên tạo một lát “đầu cuối” giả bằng cách bỏ tích hợp thật rồi tuyên bố Done. **Mock/prototype** có ích để khám phá, nhưng phải được gọi đúng trạng thái và rủi ro.

### 19.3. Chia theo giá trị có thể cần hợp tác liên chức năng

Một story nhỏ về người học có thể chứa nhiều task kỹ thuật. Điều đó không làm story “quá to” nếu nhóm có khả năng phối hợp, triển khai và kiểm chứng trong khoảng hợp lý. **Đừng biến mọi task thành story** chỉ để báo số lượng hoàn tất tăng.

## 20. Phản hồi sớm và quyền riêng tư: không thử nghiệm bằng mọi giá

Thử sản phẩm sớm trên người dùng thật đặt ra trách nhiệm rõ về an toàn và sự tin cậy.

### 20.1. Các nguyên tắc thực hành

- **Giới hạn thu thập dữ liệu** theo câu hỏi cần kiểm chứng; không ghi đáp án cá nhân hoặc thông tin nhận dạng không cần thiết.
- **Phân quyền đúng** cho người học, giảng viên và bộ phận hỗ trợ.
- **Thông báo mục đích và cơ chế tham gia** thử nghiệm theo chính sách/pháp luật áp dụng; tôn trọng lựa chọn của người dùng.
- **Không làm sai lệch trải nghiệm học quan trọng** hoặc cố ý gây bất lợi cho người học chỉ để tăng chỉ số.
- **Không giấu chức năng còn giới hạn:** phạm vi thử phải được mô tả trung thực.
- **Có phương án hỗ trợ khi xảy ra lỗi**, kể cả khi chỉ mở cho nhóm nhỏ.
- **Không sử dụng dữ liệu nhạy cảm trong log, ảnh chụp hoặc test** nếu không có cơ chế kiểm soát phù hợp.
- **Đảm bảo khả năng tiếp cận** ở mức cần thiết; người học sử dụng thiết bị/công nghệ hỗ trợ không nên bị loại khỏi thiết kế mặc định mà không được cân nhắc.

### 20.2. Canary không thay cho chất lượng

Một lỗi phân quyền nghiêm trọng ảnh hưởng 1% người dùng vẫn là lỗi nghiêm trọng. **Rollout nhỏ chỉ giới hạn phạm vi tiếp xúc**, không hợp thức hóa phần chưa đạt DoD.

### 20.3. Feature flag không chữa được lỗi dữ liệu

Tắt flag có thể ngăn người dùng truy cập giao diện, nhưng không tự hoàn tác dữ liệu đã ghi sai, sự kiện đã phát hoặc tác vụ nền đã chạy. Với lát liên quan tới lịch sử bài làm, cần đánh giá **tính nhất quán dữ liệu và phương án khôi phục**, không chỉ có nút bật/tắt.

## 21. Khi nào nên dừng, mở rộng hoặc đổi hướng?

Mục đích phản hồi không phải xác nhận trước quyết định của nhóm, mà là **giảm bất định và đưa ra quyết định tốt hơn**.

### Khung quyết định sau một lát

| Kết quả quan sát | Câu hỏi cần hỏi | Hành động phù hợp có thể chọn |
| --- | --- | --- |
| Người dùng hoàn tất tác vụ, chất lượng ổn, giá trị phù hợp. | Cần tăng phạm vi hay còn điều cần xác nhận? | Mở rộng theo giai đoạn hoặc chọn lát tiếp. |
| Người dùng tìm thấy nhưng không hiểu phản hồi. | Ngôn ngữ/giao diện có gây nhầm không? | Sửa tương tác cơ bản trước khi thêm tính năng. |
| Người dùng không mở tính năng. | Có vấn đề về nhu cầu, khả năng tìm thấy, phân quyền hay cách tuyển mẫu? | Phỏng vấn/quan sát thêm, có thể thay vị trí hoặc giả thuyết. |
| Nhiều người click lời giải nhưng vẫn không làm tiếp. | Nội dung có khó hiểu, sai hoặc không gắn ngữ cảnh? | Cải thiện nội dung, kiểm tra năng lực hiểu bài. |
| Lỗi nộp bài tăng. | Có vi phạm DoD, hạ tầng hoặc tải mới? | Hạn chế rollout, khắc phục, phân tích nguyên nhân. |
| Dữ liệu không đủ kết luận. | Mẫu, cách đo hoặc thời gian có phù hợp không? | Điều chỉnh thí nghiệm/đo, chưa tuyên bố thắng. |
| Giả định giá trị không được hỗ trợ. | Có giải pháp đơn giản khác đáng thử không? | Đổi hướng hoặc dừng đầu tư, cập nhật Product Backlog. |

Đừng áp ngưỡng máy móc cho mọi sản phẩm. Điều quan trọng là **nêu tiêu chí ra quyết định trước khi nhìn số liệu**, nhưng vẫn chấp nhận phát hiện bất ngờ và xem các rủi ro không dự báo được.

### 21.1. Một kết quả “thất bại” có thể tiết kiệm đầu tư

Nếu I2 cho thấy lời giải do giảng viên biên soạn không cải thiện việc người học tiếp tục, nhóm có thể **dừng kế hoạch xây AI giải thích hàng loạt** và tìm nguyên nhân. Đó là một kết quả học tập hữu ích, không nhất thiết là thất bại quản lý dự án.

Mục tiêu không phải mỗi giả thuyết đều đúng, mà là **kiểm tra giả định quan trọng trước khi đầu tư sâu**.

## 22. Những anti-patterns khi chia Increment

| Anti-pattern | Vì sao gây hại | Cách điều chỉnh |
| --- | --- | --- |
| **Chia theo database/API/UI** | Mỗi phần riêng lẻ không tạo hành vi người dùng; phản hồi chờ tích hợp. | Chia lát dọc có luồng đầu cuối và DoD. |
| **“MVP” là bản thiếu an toàn** | Gây lỗi dữ liệu, lộ quyền hoặc làm mất niềm tin. | Giảm phạm vi tính năng, không hạ điều kiện chất lượng. |
| **Mở mọi story cùng lúc** | WIP cao, nhiều việc gần xong, ít kết quả Done. | Giới hạn WIP, ưu tiên hoàn tất lát nhỏ. |
| **Tính năng đầu tiên chứa mọi biến thể** | Chi phí và bất định cao, học được muộn. | Bắt đầu với một luồng phổ biến có giá trị, giới hạn công khai. |
| **Chỉ làm prototype rồi báo Done** | Chưa có Increment tích hợp, không đủ bằng chứng hành vi thật. | Phân biệt prototype với phần sản phẩm đã đạt DoD. |
| **Không định nghĩa câu hỏi học tập** | Thu nhiều dữ liệu nhưng không biết quyết định gì. | Gắn từng lát với giả thuyết và tín hiệu cụ thể. |
| **Chỉ đếm click để suy ra hiểu bài** | Click có thể tăng vì khó hiểu hoặc thao tác bắt buộc. | Đo outcome gần hơn và hỏi người học. |
| **Chạy A/B không kiểm tra nhóm và mẫu** | Sai lệch do cohort, mùa vụ hoặc cách đo. | Công khai giới hạn, kiểm soát yếu tố quan trọng. |
| **Đợi cuối Sprint mới cho ai thử** | Feedback đến muộn dù Increment đã Done. | Bàn giao/release khi đủ điều kiện, Sprint Review không là cổng mặc định. |
| **Release liên tục mà không quan sát** | Output tăng, nhưng không biết giá trị hoặc lỗi. | Thiết kế telemetry và kênh feedback trước release. |
| **Hạ Definition of Done để báo nhiều Increment** | Chất lượng giảm, các lát sau chịu nợ lớn. | Giữ DoD, giảm phạm vi hoặc xử lý nút thắt. |
| **Chia chuyện kỹ thuật thành ticket nhỏ để tăng throughput** | Số ticket đẹp, người dùng vẫn chưa nhận giá trị. | Phân biệt task và PBI/Increment; dùng outcome. |
| **Nhồi nhiều giả thuyết vào một thí nghiệm** | Không biết phần nào tạo tác động. | Thử giả định quan trọng với thay đổi đủ đơn giản. |
| **Không xử lý phản hồi trái giả thuyết** | Roadmap không đổi dù dữ liệu cảnh báo. | Cập nhật Product Backlog, chọn tiếp tục/đổi/dừng. |
| **Canary làm lý do bỏ bảo mật** | Nhóm nhỏ vẫn có người dùng thật và dữ liệu thật. | Giữ chuẩn bắt buộc, chỉ giới hạn rollout khi đủ điều kiện. |
| **Coi story points là tốc độ cá nhân** | Khuyến khích ước lượng phình và chia ticket vụn. | Dùng số đo hệ thống, chất lượng và giá trị. |
| **Lát đầu không có ai dùng thử** | Không nhận được phản hồi dù code hoàn chỉnh. | Xác định cohort, điều kiện release và kênh phản hồi sớm. |
| **Chờ mọi tính năng mới có tài liệu/hỗ trợ** | Có thể trì hoãn giá trị không cần thiết. | Chuẩn bị tài liệu/hỗ trợ **đúng phạm vi lát được mở**, không làm trọn roadmap trước. |

## 23. Workshop nhanh: chia một epic thành lát nhận phản hồi

Một nhóm có thể thực hiện workshop với Product Owner, Developers và người hiểu nghiệp vụ/kiểm thử. Scrum Master hoặc người hỗ trợ luồng có thể giúp cuộc trao đổi hiệu quả.

### Bước 1 — Nêu outcome và người dùng

Viết một câu:

> “Chúng ta muốn **[nhóm người dùng]** đạt được **[kết quả]**, vì hiện họ gặp **[vấn đề quan sát]**.”

Ví dụ: “Học viên mới hiểu vì sao chọn sai và biết ôn tiếp, vì nhiều người rời bài sau khi xem thông báo sai”.

### Bước 2 — Liệt kê giả định chưa biết

Tách giả định về nhu cầu, cách dùng, khả thi kỹ thuật, chất lượng, bảo mật, dữ liệu và năng lực vận hành. Đánh dấu **tác động lớn và tự tin thấp**.

### Bước 3 — Vẽ hành trình người dùng

Ví dụ:

> Mở câu hỏi → chọn đáp án → nộp → xem phản hồi → hiểu lý do → chọn bước ôn tập → quay lại làm tiếp.

Nhóm tìm **đoạn nhỏ đầu tiên có thể hoàn tất đầu cuối**. Nếu đoạn vẫn lớn, giới hạn loại câu, nhóm người dùng, nội dung hoặc quy tắc, không bỏ tiêu chuẩn chất lượng.

### Bước 4 — Viết các lát ứng viên

Mỗi lát cần một tên hành vi, acceptance criteria cơ bản, phạm vi còn thiếu được công bố, phụ thuộc, điều kiện DoD và cách thử.

### Bước 5 — Chọn câu hỏi học tập và kênh feedback

Trả lời:

- Ai sẽ thử và trong hoàn cảnh nào?
- Quan sát điều gì để biết họ thực hiện được tác vụ?
- Cần hỏi gì để hiểu nguyên nhân?
- Số đo chất lượng/an toàn nào phải theo dõi?
- Khi nào và ai quyết định lát tiếp?

### Bước 6 — Kiểm tra năng lực hoàn tất

Developers đánh giá khả thi và rủi ro. Nếu chưa thể tích hợp một lát trong khoảng mong muốn, xem tiếp **quy tắc, dữ liệu, biến thể, phụ thuộc** có thể chia mà vẫn giữ hành vi dùng được.

### Bước 7 — Cam kết kiểm tra lại sau phản hồi

Không biến toàn bộ danh sách lát ứng viên thành kế hoạch bất biến. Chọn một bước đầu đủ rõ; phần tiếp theo được **ưu tiên lại theo dữ liệu thực tế và Product Goal**.

## 24. Bài tập tình huống: thiết kế Increment cho chức năng tìm khóa học

Một đội phát triển nền tảng học trực tuyến nhận yêu cầu từ Product Owner:

> “Người học cần nhanh chóng tìm thấy khóa Java phù hợp với trình độ.”

Đề xuất ban đầu từ các bên liên quan gồm:

- Tìm theo từ khóa.
- Lọc theo giá, ngôn ngữ, trình độ, chủ đề, giảng viên và đánh giá.
- Gợi ý cá nhân hóa bằng AI.
- Tìm bằng giọng nói.
- Xếp hạng theo lịch sử hành vi.
- Bộ lọc nâng cao và lưu bộ lọc.
- Giao diện mobile, tablet và desktop.
- Dashboard quản trị về hành vi tìm kiếm.

Nhóm chưa biết người học thường tìm theo **tên khóa**, **trình độ** hay **vấn đề họ muốn giải quyết**. Nếu triển khai toàn bộ mới thử, có thể mất nhiều tuần.

### Nhiệm vụ

1. Viết một **outcome** cụ thể hơn “xây tìm kiếm thông minh”.
2. Chỉ ra ít nhất **năm giả định** cần kiểm chứng.
3. Đề xuất **bốn lát dọc** theo thứ tự có thể thay đổi, mỗi lát có hành vi và đối tượng rõ.
4. Chọn **lát đầu nhỏ nhất có giá trị**, giải thích những gì chưa làm và những gì **không được bỏ**.
5. Viết ít nhất **ba acceptance scenarios**, gồm không có kết quả, quyền xem và lỗi.
6. Chọn hai **tín hiệu giá trị**, hai **guardrails chất lượng** và cách thu phản hồi định tính.
7. Đề xuất một cách phát hành có kiểm soát cho lát đầu.
8. Giả sử chỉ **5 trong 20** người thử tìm được khóa phù hợp trong một nhiệm vụ đã thống nhất. Có thể kết luận gì và chưa thể kết luận gì?
9. Sau phản hồi, người dùng cho biết “tôi không biết khóa nào dành cho người mới”, trong khi tìm theo tên khóa hoạt động tốt. Bạn sẽ ưu tiên lát nào tiếp?
10. Nếu kiểm thử phát hiện kết quả tìm kiếm hiển thị khóa học chưa được phép công khai, có thể phát hành để thu feedback rồi sửa sau không?

## 25. Hướng giải tham khảo cho bài tập

### 25.1. Outcome và giả định

**Outcome minh họa:**

> “Người mới học Java có thể tìm và mở đúng trang khóa học phù hợp với nhu cầu trong một nhiệm vụ thử rõ ràng, không bị dẫn tới nội dung không có quyền truy cập.”

Một số giả định:

- Người học biết tên khóa hoặc từ khóa phù hợp.
- Họ hiểu cách hệ thống biểu diễn trình độ.
- Kết quả tìm kiếm có thứ tự đủ hữu ích.
- Dữ liệu tiêu đề/mô tả khóa được cập nhật và tìm đúng.
- Người dùng phân biệt khóa công khai với khóa giới hạn.
- Chức năng tìm hoạt động đủ nhanh ở dữ liệu thật.
- Người học sẽ sử dụng lọc trình độ nếu được cung cấp.
- Việc tìm đúng khóa dẫn đến việc mở trang khóa và bắt đầu học.

### 25.2. Bốn lát dọc ứng viên

| Lát | Kết quả người học có được | Giả thuyết cần kiểm tra |
| --- | --- | --- |
| **S1 – Tìm theo tên/từ khóa cơ bản** | Người học nhập từ khóa và mở trang một khóa công khai phù hợp, có xử lý không có kết quả và lỗi. | Luồng tìm cơ bản có tìm và sử dụng được không? |
| **S2 – Thể hiện trình độ rõ trong kết quả** | Người học thấy nhãn trình độ được kiểm chứng, hiểu khóa dành cho ai. | Thiếu thông tin trình độ có là nguyên nhân chọn sai? |
| **S3 – Lọc theo trình độ được hỗ trợ** | Người học giới hạn kết quả theo mức nhập môn/trung cấp trong phạm vi đã định nghĩa. | Bộ lọc có giúp tìm khóa phù hợp nhanh hơn? |
| **S4 – Sắp thứ tự theo tiêu chí có nghĩa** | Người học thấy kết quả được sắp theo một tiêu chí minh bạch dựa trên nhu cầu. | Thứ tự có cải thiện việc tìm khóa phù hợp không? |

**Tìm bằng giọng nói và AI** chưa cần nếu giả định cốt lõi chưa được kiểm chứng. Các lát có thể đổi thứ tự: nếu S1 cho thấy vấn đề chính là thông tin trình độ chứ không phải từ khóa, S2 có thể được ưu tiên nhanh.

**Không được bỏ:** phân quyền và trạng thái xuất bản khóa, xử lý dữ liệu/đường dẫn an toàn, kết quả đúng trong phạm vi, lỗi và DoD.

### 25.3. Gherkin cho lát S1

~~~gherkin
Feature: Tìm khóa học công khai theo từ khóa

Scenario: Từ khóa có kết quả
  Given người học đang xem danh mục khóa học được phép hiển thị
  And tồn tại khóa học công khai "Java căn bản" khớp từ khóa "Java"
  When người học nhập "Java" và thực hiện tìm kiếm
  Then hệ thống hiển thị khóa "Java căn bản" theo quy tắc tìm kiếm đã định
  And người học có thể mở trang chi tiết được phép truy cập

Scenario: Không có khóa khớp
  Given không có khóa học được phép hiển thị nào khớp "QuantumJavaXYZ"
  When người học tìm "QuantumJavaXYZ"
  Then hệ thống thông báo không có kết quả rõ ràng
  And không hiển thị dữ liệu khóa học trái quyền

Scenario: Khóa học chưa được công khai
  Given tồn tại một khóa Java chưa được phép công khai
  When người học không có quyền tìm kiếm "Java"
  Then kết quả không tiết lộ thông tin riêng của khóa đó
  And đường dẫn trực tiếp tới khóa vẫn được kiểm tra quyền theo chính sách

Scenario: Dịch vụ tìm kiếm lỗi
  Given dịch vụ tìm kiếm tạm thời không thể trả kết quả
  When người học thực hiện tìm kiếm
  Then giao diện không báo sai rằng không có khóa nào tồn tại
  And hiển thị thông báo hoặc cách thử lại phù hợp
~~~

Lát S1 vẫn cần kiểm tra injection, phân quyền, tính đúng đắn truy vấn và thời gian phản hồi theo mức rủi ro; Gherkin là ví dụ hành vi, không thay bộ kiểm thử hoặc DoD.

### 25.4. Tín hiệu và phát hành

**Tín hiệu giá trị:**

- Tỷ lệ người tham gia hoàn tất nhiệm vụ tìm và mở đúng khóa trong bài thử được định nghĩa.
- Mức độ người học hiểu vì sao kết quả phù hợp, qua quan sát/phỏng vấn; có thể theo dõi tỷ lệ mở trang khóa phù hợp trong môi trường thực sau khi định nghĩa cách đo.

**Guardrails:**

- Không hiển thị nội dung khóa trái quyền hoặc chưa công khai.
- Tỷ lệ lỗi/độ trễ tìm kiếm không vượt tiêu chí sản phẩm đã thống nhất.

**Phản hồi:** tổ chức thử nhiệm vụ với nhóm học viên mới phù hợp, quan sát cách họ nhập từ khóa và hỏi điều họ trông đợi. Có thể mở S1 cho một nhóm dùng thử theo điều kiện release an toàn.

**Kết quả 5/20:** có thể nhận thấy **nhiều người tham gia mẫu chưa hoàn tất nhiệm vụ**, cần điều tra giao diện, từ khóa, dữ liệu và quy tắc khớp. Chưa đủ để kết luận toàn bộ người học đều thất bại hoặc nguyên nhân nằm ở thuật toán; mẫu nhỏ và cách chọn người có thể lệch.

**Ưu tiên tiếp theo:** Nếu vấn đề là hiểu khóa dành cho ai, thử **thông tin trình độ rõ (S2)** trước AI. Nếu kiểm thử lộ khóa chưa công khai, **không được release như một Increment Done** để “lấy feedback”; cần khắc phục quyền và chất lượng trước.

## 26. Tự kiểm tra kiến thức

**Câu 1.** Một API đã chạy nhưng chưa có luồng người dùng sử dụng. Có tự động là Increment Done không?

**Đáp án:** Không. Cần xét phần tiến bộ có thể sử dụng, đã tích hợp và đáp ứng DoD của sản phẩm. Một task API hoàn tất chưa chắc tạo Increment có ý nghĩa.

**Câu 2.** Vì sao chia ngang theo backend/frontend/QA thường khiến phản hồi người dùng đến muộn?

**Đáp án:** Các phần riêng rẽ chưa tạo hành vi đầu cuối; phải đợi ghép và kiểm thử tổng thể mới có phần mềm sử dụng được.

**Câu 3.** Lát nhỏ có được bỏ kiểm thử quyền truy cập để release cho 10 người dùng không?

**Đáp án:** Không. Giới hạn số người dùng không xóa nghĩa vụ bảo vệ dữ liệu, quyền và DoD.

**Câu 4.** MVP, prototype và Increment có phải một khái niệm không?

**Đáp án:** Không. Prototype phục vụ khám phá; MVP là cách tối thiểu kiểm chứng giả thuyết quan trọng; Increment trong Scrum là bước tiến tích hợp, có thể sử dụng, đạt DoD. Một MVP có thể có nhiều Increment.

**Câu 5.** Nếu học viên click lời giải rất nhiều, có thể kết luận họ học tốt hơn không?

**Đáp án:** Không. Cần đo tín hiệu học tập/hành vi gần outcome và phản hồi định tính; click có thể tăng vì nội dung khó hiểu.

**Câu 6.** Scrum có bắt buộc chờ Sprint Review mới release Increment không?

**Đáp án:** Không. Increment đạt DoD có thể được bàn giao trước khi Sprint kết thúc nếu các điều kiện release phù hợp. Sprint Review dùng để kiểm tra kết quả và thích ứng.

**Câu 7.** Nếu có một story rất lớn, nên chia nó bằng cách nào?

**Đáp án:** Chọn hành vi người dùng nhỏ, đi qua các lớp cần thiết; giới hạn biến thể, quy tắc hoặc đối tượng khi phù hợp, nhưng giữ khả năng sử dụng và chất lượng.

**Câu 8.** Điều gì khác giữa “đã phát hành” và “đã tạo giá trị”?

**Đáp án:** Phát hành là đưa khả năng tới người dùng; giá trị cần được kiểm chứng bằng hành vi, kết quả, phản hồi và bối cảnh phù hợp.

**Câu 9.** Một phiên bản có tỷ lệ tiếp tục luyện tập 54%, phiên bản khác 38%. Có thể khẳng định tính năng tạo tăng trưởng 16 điểm phần trăm do quan hệ nhân quả không?

**Đáp án:** Chưa đủ. Đây là chênh lệch quan sát; phải xét cách chọn mẫu, độ khó, thời điểm, đo lường và thiết kế thử nghiệm.

**Câu 10.** Vì sao cần phân biệt Done, Released và Feedback Observed trên bảng luồng?

**Đáp án:** Để thấy công việc đã đạt chất lượng nhưng còn chờ phát hành, hoặc đã phát hành nhưng chưa có bằng chứng giá trị. Mỗi khoảng trễ có nguyên nhân và hướng cải tiến khác nhau.

**Câu 11.** User story chia nhỏ có cần được viết theo một khuôn mẫu cố định để là Agile không?

**Đáp án:** Không. Mẫu user story là công cụ trao đổi; điều quan trọng là hiểu nhu cầu, hành vi, tiêu chí kiểm chứng và tạo giá trị.

**Câu 12.** Nếu phản hồi cho thấy giả định ban đầu sai, nhóm nên làm gì?

**Đáp án:** Đánh giá chất lượng bằng chứng, làm rõ nguyên nhân và điều chỉnh Product Backlog hoặc hướng giải pháp. Dừng một hướng không có giá trị có thể là kết quả học hỏi tốt.

## 27. Checklist trước khi chọn và phát hành một lát

### Giá trị và giả thuyết

- [ ] Có một vấn đề người dùng hoặc kết quả sản phẩm được mô tả rõ.
- [ ] Biết lát này kiểm tra giả định nào và vì sao cần học sớm.
- [ ] Có đối tượng sẽ dùng/thử và điều kiện tham gia phù hợp.
- [ ] Có cách thu phản hồi định tính hoặc định lượng đủ trả lời câu hỏi.
- [ ] Biết quyết định nào có thể thay đổi sau phản hồi.

### Kích thước và tính hoàn chỉnh

- [ ] Lát thể hiện hành vi **đầu cuối**, không chỉ một tầng kỹ thuật.
- [ ] Phạm vi biến thể, quy tắc và nhóm dùng thử được nêu rõ.
- [ ] Kích thước đủ nhỏ để nhóm hoàn tất và kiểm tra trong nhịp phù hợp.
- [ ] Các phụ thuộc và người chịu trách nhiệm được làm rõ sớm.
- [ ] Không trì hoãn yếu tố đúng đắn, phân quyền hoặc chất lượng bắt buộc.

### Kiểm chứng và release

- [ ] Acceptance criteria có cả trường hợp chính, lỗi và rủi ro quan trọng.
- [ ] Increment được tích hợp và đáp ứng Definition of Done.
- [ ] Đã phân biệt **Done**, **Deployed** và **Released**.
- [ ] Người có quyền release và chính sách vận hành/tuân thủ đã rõ.
- [ ] Có giám sát lỗi, hỗ trợ và cách ngừng/khôi phục phù hợp với rủi ro.
- [ ] Không thu dữ liệu người học quá mức hoặc trái mục đích.

### Học hỏi và điều chỉnh

- [ ] Số đo có định nghĩa rõ, không nhầm click với outcome.
- [ ] Có guardrails cho an toàn, chất lượng và trải nghiệm.
- [ ] Đã xem giới hạn mẫu, cách chọn người và khả năng suy diễn.
- [ ] Có thời điểm xem lại kết quả và người quyết định bước tiếp theo.
- [ ] Product Backlog/roadmap có thể được cập nhật từ bằng chứng.
- [ ] Nhóm cải thiện cả thời gian làm việc **và thời gian chờ phản hồi**.

Checklist phục vụ trao đổi, không phải một cổng phê duyệt hành chính mới. Với lát rất nhỏ, có thể sử dụng phiên bản rút gọn nhưng **không bỏ những điều kiện an toàn cần thiết**.

## 28. Ghi nhớ trọng tâm

- **Phần tăng trưởng tốt không chỉ nhỏ; nó phải có thể sử dụng, đúng phạm vi, đạt chất lượng và giúp học được điều quan trọng.**
- **Chia lát dọc theo hành vi người dùng**, không chỉ chia backend/frontend/database/QA thành các gói chưa tích hợp.
- **Kết nối lát với giả thuyết, đối tượng thử, số đo và quyết định tiếp theo.** Nếu không ai quan sát hoặc thay đổi quyết định, “giao nhỏ” chưa tạo vòng học hỏi.
- **Prototype, MVP, Increment, deploy và release khác nhau.** Gọi đúng trạng thái để không nhầm demo với sản phẩm Done hoặc output với outcome.
- **Chia bằng quy trình, biến thể, quy tắc, phạm vi dữ liệu, đối tượng, độ phong phú hoặc bất định**; không chia bằng cách trì hoãn chất lượng bắt buộc.
- **Definition of Done bảo vệ khả năng sử dụng.** Một phần chưa đạt DoD không được ghi là Increment chỉ để kịp ngày.
- **Sprint Review không phải cổng phát hành mặc định.** Increment có thể được bàn giao trước khi Sprint kết thúc khi đủ điều kiện.
- **Phản hồi phải được thiết kế trước:** phỏng vấn, quan sát, telemetry và guardrails cần trả lời câu hỏi cụ thể, có quyền riêng tư.
- **Dữ liệu từ một nhóm nhỏ là tín hiệu để học, không tự chứng minh quan hệ nhân quả.** Kết hợp định lượng, định tính và bối cảnh.
- **Kanban giúp thấy WIP/hàng chờ; Scrum giữ mục tiêu và nhịp kiểm tra; XP giữ kỹ thuật giúp mỗi lát đạt DoD; Lean tối ưu toàn bộ vòng phản hồi.**
- **Không phải mọi lát ứng viên đều phải xây.** Sau mỗi lần kiểm chứng, nhóm nên có quyền tiếp tục, mở rộng, cải thiện, đổi hướng hoặc dừng.
- **Mục tiêu cuối là thời gian từ một giả định quan trọng tới hiểu biết đáng tin cậy và giá trị thật**, không phải số lượng story đóng hoặc tần suất release bằng mọi giá.

Khi thiết kế phần tăng trưởng, hãy bắt đầu bằng câu hỏi **“Phần nhỏ nhất nào người dùng có thể thực sự trải nghiệm một cách an toàn, và trải nghiệm đó giúp chúng ta quyết định điều gì?”**. Trả lời được câu hỏi này, rồi hoàn thiện lát tới DoD, mở cho đúng đối tượng và chủ động học từ phản hồi, là cách biến Agile thành dòng phát triển **giao giá trị tăng dần, giảm làm lại và thích ứng liên tục**.

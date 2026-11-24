# Các khái niệm nền: giá trị, vòng lặp, phần tăng trưởng và luồng công việc

## 1. Bốn khái niệm tạo nên cách làm việc Agile

Trong phát triển phần mềm, kế hoạch ban đầu hiếm khi mô tả chính xác mọi nhu cầu, rủi ro kỹ thuật và hành vi của người dùng. Agile giúp nhóm tiến về mục tiêu trong điều kiện còn nhiều điều chưa biết: **giao một phần sản phẩm có ích, nhận phản hồi sớm, học từ kết quả và điều chỉnh bước tiếp theo**.

Để hiểu Agile, cần phân biệt bốn khái niệm thường xuất hiện cùng nhau:

| Khái niệm | Câu hỏi cốt lõi | Ý nghĩa trong công việc |
| --- | --- | --- |
| **Giá trị (value)** | Vì sao chúng ta làm việc này, và ai được lợi? | Dẫn dắt mục tiêu, thứ tự ưu tiên và cách đánh giá kết quả. |
| **Vòng lặp (iteration)** | Bao lâu thì chúng ta kiểm tra giả định và điều chỉnh? | Tạo nhịp làm việc, phản hồi và học hỏi thường xuyên. |
| **Phần tăng trưởng (increment)** | Sau mỗi bước, sản phẩm đã dùng được thêm điều gì? | Biến công sức thành một phần sản phẩm hoàn chỉnh, tích hợp được với phần trước. |
| **Luồng công việc (workflow/flow)** | Công việc đi từ nhu cầu đến hoàn tất như thế nào? | Giúp nhìn thấy tiến độ, giới hạn việc làm dở và cải thiện khả năng giao hàng. |

Bốn khái niệm có liên hệ nhưng **không đồng nghĩa**. Nhóm có thể làm việc theo vòng lặp hai tuần mà chưa giao được phần tăng trưởng dùng được. Nhóm cũng có thể giao các phần tăng trưởng liên tục bằng Kanban mà không chia thời gian thành Sprint. Trong cả hai trường hợp, phải nhìn vào **giá trị nhận được và chất lượng luồng công việc** để biết cách làm có hiệu quả không.

Một vòng học hỏi đơn giản:

~~~mermaid
flowchart LR
    A["Nhu cầu và giả định giá trị"] --> B["Chọn phần việc nhỏ có ích"]
    B --> C["Xây dựng và kiểm chứng"]
    C --> D["Phần tăng trưởng dùng được"]
    D --> E["Phản hồi và kết quả thực tế"]
    E --> F["Điều chỉnh ưu tiên và cách làm"]
    F --> A
~~~

Sơ đồ cho thấy mục tiêu của mỗi lần giao sản phẩm không chỉ là **hoàn thành đầu việc** mà còn là giảm sự không chắc chắn: điều gì có ích, điều gì chưa đúng và bước nào đáng làm tiếp.

## 2. Giá trị: điểm xuất phát của quyết định

### 2.1. Giá trị của sản phẩm là kết quả có ích

Một tính năng được viết xong là **đầu ra** (*output*). Điều người dùng hoặc tổ chức thực sự nhận được là **kết quả** (*outcome*). Chúng có thể liên quan, nhưng không tự động bằng nhau.

Ví dụ, nhóm xây dựng chức năng **đặt lịch tư vấn trực tuyến**:

- Đầu ra: màn hình chọn lịch, API tạo lịch hẹn và thông báo xác nhận.
- Kết quả mong muốn của khách hàng: đặt được cuộc hẹn mà không phải gọi điện, ít nhầm giờ hơn.
- Kết quả mong muốn của tổ chức: giảm thời gian nhân viên xử lý lịch thủ công, giảm lịch hẹn bị bỏ lỡ.
- Tín hiệu kiểm chứng: tỷ lệ khách hoàn tất đặt lịch, thời gian trung bình để đặt lịch, số lỗi đặt trùng, số cuộc hẹn không đến.

Nếu màn hình đã bàn giao nhưng khách không sử dụng được hoặc thường gặp lỗi, nhóm đã tạo ra đầu ra mà **chưa chứng minh được giá trị**.

Giá trị cũng không chỉ là tính năng mới. Sửa một lỗ hổng bảo mật, cải thiện khả năng tiếp cận, giảm thời gian phản hồi, giảm lỗi sản xuất hoặc làm hệ thống dễ thay đổi hơn đều có thể mang lại lợi ích trực tiếp hoặc bảo vệ giá trị lâu dài. Cần xem ai hưởng lợi, lợi ích nào được kỳ vọng và bằng chứng nào xác nhận điều đó.

Một cách diễn đạt mục tiêu hữu ích:

> Chúng ta tin rằng **[thay đổi]** sẽ giúp **[nhóm người dùng]** đạt **[kết quả]**; chúng ta sẽ kiểm tra bằng **[tín hiệu hoặc phản hồi]**.

Ví dụ:

> Chúng ta tin rằng hiển thị các khung giờ còn trống sẽ giúp khách tự đặt lịch nhanh hơn; chúng ta sẽ kiểm tra tỷ lệ hoàn tất đặt lịch và phản hồi từ những khách dùng thử.

Đây là một **giả thuyết giá trị**, không phải cam kết rằng giải pháp chắc chắn thành công. Agile khuyến khích kiểm chứng giả thuyết bằng những thay đổi vừa đủ nhỏ để học sớm.

### 2.2. Bốn giá trị trong Agile Manifesto

Tuyên ngôn Agile nêu bốn ưu tiên khi phát triển phần mềm. Mỗi hàng có hai vế **đều có giá trị**, nhưng trong tình huống cần lựa chọn, vế bên trái được coi trọng hơn:

| Giá trị Agile | Diễn giải qua hành động |
| --- | --- |
| **Cá nhân và tương tác** hơn quy trình và công cụ | Trao đổi trực tiếp khi có điểm mơ hồ; công cụ theo dõi hỗ trợ cộng tác thay vì thay thế đối thoại. |
| **Phần mềm hoạt động** hơn tài liệu toàn diện | Tạo bằng chứng bằng chức năng chạy được, được kiểm thử; vẫn viết tài liệu cần thiết cho vận hành, bảo trì và tuân thủ. |
| **Cộng tác với khách hàng** hơn đàm phán hợp đồng | Thường xuyên xác nhận nhu cầu và tiêu chí thành công với người liên quan; vẫn tôn trọng cam kết và ràng buộc đã thống nhất. |
| **Phản hồi với thay đổi** hơn bám sát kế hoạch | Cập nhật kế hoạch khi có thông tin mới; vẫn lập kế hoạch để phối hợp, quản lý phụ thuộc và rủi ro. |

Không nên hiểu Agile là không có quy trình, không có tài liệu hay không cần kế hoạch. Điểm chính là **những thứ đó phục vụ việc tạo giá trị và khả năng thích ứng**, thay vì trở thành mục đích tự thân.

### 2.3. Ưu tiên theo giá trị và mức độ chưa chắc chắn

Khi sắp xếp backlog, một nhóm có thể cân nhắc đồng thời:

1. **Lợi ích kỳ vọng:** vấn đề của ai được giải quyết, quan trọng đến đâu?
2. **Mức độ rủi ro hoặc chưa biết:** giả định nào cần kiểm chứng sớm?
3. **Chi phí và quy mô:** có thể chia nhỏ để nhận phản hồi nhanh hơn không?
4. **Phụ thuộc và tính cấp thiết:** có mốc tuân thủ, tích hợp hoặc giới hạn thời gian nào?

Ví dụ, trước khi xây dựng bộ lọc lịch nâng cao, nhóm nên xác minh người dùng có **tìm được khung giờ và đặt lịch thành công** hay không. Nếu hành vi cơ bản chưa hoạt động, thêm nhiều lựa chọn chưa chắc tạo thêm giá trị.

## 3. Vòng lặp: làm, kiểm tra, học và điều chỉnh

### 3.1. Vòng lặp là gì?

**Vòng lặp (iteration)** là một chu kỳ làm việc và học hỏi có chủ đích. Nhóm chọn mục tiêu gần, thực hiện một phần công việc, kiểm tra kết quả, nhận phản hồi rồi quyết định điều chỉnh giải pháp hoặc kế hoạch.

Một vòng lặp có thể gồm:

1. **Định hướng:** thống nhất mục tiêu và giả định cần kiểm chứng.
2. **Lựa chọn:** lấy một số hạng mục ưu tiên, có phạm vi đủ nhỏ.
3. **Thực hiện:** phân tích, thiết kế vừa đủ, lập trình, tích hợp và kiểm thử.
4. **Kiểm tra kết quả:** trình diễn sản phẩm hoạt động, đo lường và nghe phản hồi.
5. **Điều chỉnh:** cập nhật backlog, cách phối hợp và tiêu chí cho lần tiếp theo.

Điều cốt yếu là **thông tin từ vòng trước thay đổi quyết định ở vòng sau**. Nếu nhóm lặp lại cùng một quy trình nhưng không học từ kết quả, nhịp làm việc đó chưa phát huy lợi ích của Agile.

### 3.2. Vòng lặp có nhất thiết là Sprint?

Không. **Sprint** là một cơ chế cụ thể của Scrum: khoảng thời gian cố định, dài tối đa một tháng, hướng tới một Sprint Goal. Trong Sprint, nhóm tạo ra các Increment đáp ứng Definition of Done; tại Sprint Review, nhóm cùng các bên liên quan kiểm tra kết quả và điều chỉnh định hướng sản phẩm; tại Retrospective, nhóm cải tiến cách làm việc.

Các nhóm không dùng Scrum vẫn có thể lặp theo vòng học hỏi, ví dụ: thử nghiệm một giao diện trong vài ngày, thu thập phản hồi sau mỗi lần phát hành hoặc rà soát kết quả sản phẩm hằng tuần. **Kanban** thường tập trung vào luồng liên tục và các nhịp xem xét công việc thay vì bắt buộc timebox phát triển.

Vì vậy, cần tách hai ý:

- **Nhịp thời gian:** khi nào nhóm lập kế hoạch, đồng bộ và xem lại kết quả?
- **Nhịp phản hồi:** khi nào xuất hiện bằng chứng đủ tốt để thay đổi quyết định?

Phản hồi có thể đến ngay trong một vòng lặp; không cần đợi đến cuối Sprint mới nói chuyện với người dùng hay kiểm thử phần mềm.

### 3.3. Vòng lặp ngắn giúp gì?

Giả sử nhóm mất ba tháng mới giới thiệu chức năng đặt lịch với khách hàng. Nếu giả định về cách khách chọn thời gian sai, nhóm có thể phải sửa nhiều thiết kế và mã nguồn.

Thay vào đó, nhóm thử một **luồng đặt lịch tối thiểu** với một nhóm khách đại diện trong vòng đầu. Từ phản hồi “người dùng cần thấy giờ theo múi giờ của mình”, nhóm thay đổi ưu tiên ngay trước khi xây dựng các tùy chọn nâng cao.

Vòng lặp ngắn giúp giảm **thời gian phát hiện sai lệch**, nhưng không tự động bảo đảm chất lượng. Nếu không có kiểm thử, tích hợp thường xuyên hoặc người phản hồi phù hợp, nhóm có thể chỉ giao những phần dở dang nhanh hơn.

## 4. Phần tăng trưởng: sản phẩm hoàn chỉnh thêm từng bước

### 4.1. Increment là gì?

**Phần tăng trưởng (increment)** là phần giá trị sản phẩm được bổ sung vào những gì đã hoàn tất trước đó. Trong Scrum, một Increment phải **dùng được**, **được tích hợp với các Increment trước** và đáp ứng **Definition of Done** (định nghĩa hoàn tất) để bảo đảm tính minh bạch về chất lượng.

Increment không đơn giản là số lượng mã nguồn viết thêm hoặc một phần công việc đang dở. Một API mới chỉ chạy trên máy lập trình viên, chưa tích hợp và chưa được kiểm thử phù hợp, không đủ để gọi là Increment hoàn tất.

Ví dụ, với chức năng đặt lịch tư vấn:

| Lần giao | Phần sản phẩm được bổ sung | Giá trị có thể kiểm chứng |
| --- | --- | --- |
| **Increment 1** | Khách xem khung giờ còn trống, đặt một cuộc hẹn và nhận xác nhận cơ bản. | Khách có thể tự đặt lịch trong phạm vi thử nghiệm. |
| **Increment 2** | Khách có thể đổi hoặc hủy lịch theo quy tắc rõ ràng. | Giảm nhu cầu gọi nhân viên để sửa lịch. |
| **Increment 3** | Gửi nhắc lịch tự động cho cuộc hẹn đã đặt. | Có cơ hội giảm số cuộc hẹn bị quên; cần đo để xác nhận. |

Mỗi hàng minh họa một **lát cắt chức năng từ đầu đến cuối** (*vertical slice*): giao diện, nghiệp vụ, lưu trữ, xử lý lỗi và kiểm thử cần thiết để hành vi đó dùng được. Không nên chia một Increment thành “tuần 1 viết database, tuần 2 viết API, tuần 3 viết giao diện” nếu từng phần chưa tạo thành hành vi sản phẩm có thể kiểm chứng.

Increment 2 hoặc 3 phải giữ được hành vi đã hoàn tất trước đó; thêm khả năng mới mà phá vỡ chức năng cũ không phải tăng trưởng bền vững.

### 4.2. Hoàn tất, được chấp nhận và phát hành khác nhau thế nào?

Ba khái niệm dễ bị nhập làm một:

| Trạng thái/khái niệm | Câu hỏi kiểm tra |
| --- | --- |
| **Acceptance criteria** (tiêu chí chấp nhận của một hạng mục) | Hành vi cụ thể cần đáp ứng là gì để hạng mục giải quyết đúng nhu cầu? |
| **Definition of Done — DoD** (định nghĩa hoàn tất dùng chung) | Công việc đã thỏa chuẩn chất lượng cần thiết, được tích hợp và kiểm chứng chưa? |
| **Release/Deployment** (phát hành/triển khai) | Khi nào và tới môi trường hoặc nhóm người dùng nào phần sản phẩm được đưa vào sử dụng? |

Ví dụ, tiêu chí chấp nhận của “đặt lịch” có thể là “không cho hai khách xác nhận cùng một khung giờ đã hết chỗ”. DoD của nhóm còn bao gồm các kiểm tra phù hợp như kiểm thử tự động, review mã, tích hợp thành công và không có lỗi nghiêm trọng còn mở. Phần mềm **Done** có thể sẵn sàng để phát hành, nhưng quyết định phát hành thực tế còn tùy chính sách, vận hành và mục tiêu kinh doanh.

**Không cần đợi kết thúc Sprint mới có Increment**, và một Sprint cũng có thể tạo nhiều Increment. Ngược lại, Sprint kết thúc mà không có phần sản phẩm nào đáp ứng DoD là tín hiệu cần xem xét về cách chia nhỏ công việc, rủi ro, năng lực hoặc chất lượng.

### 4.3. Lặp và tăng trưởng liên hệ với nhau nhưng không trùng nhau

- **Lặp** mô tả cách khám phá và cải thiện: quay lại kiểm tra một giả định, giải pháp hoặc kết quả.
- **Tăng trưởng** mô tả trạng thái sản phẩm: phần khả năng sử dụng đã được bổ sung và tích hợp.

Một nhóm có thể **lặp qua nhiều bản phác thảo** để tìm đúng trải nghiệm trước khi tạo Increment. Một nhóm triển khai liên tục có thể **giao các Increment nhỏ mỗi ngày** mà không dùng Sprint cố định. Lý tưởng là kết hợp học hỏi lặp đi lặp lại với các Increment có chất lượng, nhưng không nên đánh đồng “đã hết vòng lặp” với “đã có giá trị”.

## 5. Luồng công việc: đưa ý tưởng đến trạng thái hoàn tất

### 5.1. Workflow mô tả hành trình của từng hạng mục

**Luồng công việc (workflow)** là các trạng thái và quy tắc chuyển trạng thái của một hạng mục, từ khi được xem xét đến khi đạt kết quả mong muốn. Một bảng công việc có thể bắt đầu đơn giản như sau:

~~~mermaid
flowchart LR
    A["Backlog"] --> B["Sẵn sàng"]
    B --> C["Đang thực hiện"]
    C --> D["Review / Kiểm thử"]
    D --> E["Done"]
    D --> C
    E --> F["Phát hành khi phù hợp"]
    F --> G["Thu phản hồi"]
    G -. "Ý tưởng hoặc điều chỉnh mới" .-> A
~~~

Các cột là **ví dụ**, không phải mẫu bắt buộc. Tùy nhóm có thể gộp, tách hoặc đổi tên cột. Điều quan trọng là mỗi trạng thái có ý nghĩa rõ ràng, ví dụ:

- **Sẵn sàng:** hạng mục đã đủ hiểu để bắt đầu; kết quả mong muốn và tiêu chí chấp nhận tương đối rõ.
- **Đang thực hiện:** nhóm đang làm, cần tính vào giới hạn công việc dở dang.
- **Review/Kiểm thử:** đang chờ hoặc tiến hành xác minh, vẫn là công việc **chưa xong**.
- **Done:** thỏa Definition of Done; riêng bước phát hành có thể được theo dõi nếu nhóm cần.

Nhìn vào luồng giúp nhóm phân biệt **đang bận** với **đang hoàn tất việc**. Nếu tám hạng mục đều đang viết mã nhưng không hạng mục nào qua được kiểm thử, lượng công việc dở dang tăng còn giá trị vẫn chưa được giao.

### 5.2. WIP, cơ chế kéo và nút thắt

**Work in Progress (WIP)** là số hạng mục đã bắt đầu nhưng chưa hoàn tất tại một thời điểm hoặc trong các trạng thái được xác định. **WIP limit** là mức giới hạn để tránh mở quá nhiều việc cùng lúc.

Giả sử nhóm đặt giới hạn **hai hạng mục** cho cột “Đang thực hiện”. Khi cả hai vị trí đã có việc, thành viên không tự động lấy hạng mục mới. Họ có thể phối hợp xử lý kiểm thử, tháo vướng mắc hoặc hoàn tất việc đang dang dở. Đây là tinh thần **pull**: nhận việc khi hệ thống có năng lực xử lý.

Lợi ích thường gặp:

- Giảm chuyển ngữ cảnh giữa nhiều việc chưa hoàn tất.
- Phát hiện sớm nút thắt, ví dụ review mã hoặc môi trường kiểm thử bị quá tải.
- Tạo động lực **hoàn tất trước khi bắt đầu thêm**, giúp phản hồi đến nhanh hơn.

Không có con số WIP limit đúng cho mọi nhóm. Cần thử nghiệm, theo dõi và điều chỉnh theo loại công việc, năng lực, phụ thuộc và mức độ biến động. **Một hạng mục bị chặn vẫn cần được thể hiện rõ**, không nên âm thầm bỏ khỏi thống kê để số liệu trông đẹp hơn.

### 5.3. Scrum, Kanban và XP nhìn từ bốn khái niệm

Các cách thực hành này có trọng tâm khác nhau nhưng có thể bổ trợ:

| Cách thực hành | Liên hệ với giá trị, vòng lặp, increment và flow |
| --- | --- |
| **Scrum** | Sử dụng Sprint, Sprint Goal, Product Backlog và các sự kiện kiểm tra–thích ứng để hướng đến Increment hoàn tất. |
| **Kanban** | Trực quan hóa workflow, quản lý WIP, theo dõi luồng và cải thiện khả năng dự báo, giao hàng liên tục. |
| **Extreme Programming (XP)** | Nhấn mạnh thực hành kỹ thuật như kiểm thử tự động, tích hợp liên tục, refactoring và cộng tác sát để các Increment nhỏ vẫn đáng tin cậy. |

Nhóm có thể dùng kỹ thuật XP khi làm Scrum hoặc áp dụng nguyên tắc Kanban để cải thiện cách công việc di chuyển trong Sprint. Tên phương pháp không thay thế được việc kiểm tra sản phẩm có tạo giá trị và có thực sự hoàn tất hay không.

## 6. Đặt bốn khái niệm vào một tình huống thực tế

Một nhóm phụ trách phần mềm đặt lịch tư vấn nhận được phản hồi rằng khách phải gọi điện nhiều lần mới tìm được lịch trống.

**Bước 1 — Xác định giá trị.** Nhóm đặt mục tiêu giúp khách tự đặt được lịch và giảm thao tác thủ công cho nhân viên. Họ ghi nhận số lần khách phải gọi điện, tỷ lệ hoàn tất đặt lịch và phản hồi của người dùng thử.

**Bước 2 — Chọn Increment nhỏ.** Thay vì thiết kế ngay toàn bộ hệ thống đặt lịch đa chi nhánh, nhóm ưu tiên luồng đầu tiên: xem một danh sách giờ trống, chọn giờ, xác nhận đặt lịch và nhận thông tin cuộc hẹn. Phạm vi thử nghiệm được công bố rõ để không gây hiểu nhầm về năng lực hệ thống.

**Bước 3 — Quản lý flow.** Hạng mục được tách thành các lát cắt có thể kiểm chứng. Trên bảng công việc, nhóm thấy một hạng mục đang chờ xác minh quy tắc trùng giờ. Họ cùng xử lý trở ngại này trước khi bắt đầu thêm chức năng lọc lịch.

**Bước 4 — Hoàn tất Increment.** Nhóm kiểm tra các tiêu chí chấp nhận, chạy kiểm thử phù hợp, tích hợp với hệ thống hiện có và xác nhận thỏa Definition of Done. Một phiên bản dùng thử được đưa tới nhóm khách được chọn.

**Bước 5 — Lặp và học.** Phản hồi cho thấy khách thường nhầm múi giờ khi đặt từ xa. Nhóm cập nhật backlog: ưu tiên hiển thị múi giờ rõ ràng trước chức năng gợi ý khung giờ nâng cao. Kết quả vòng đầu ảnh hưởng trực tiếp đến lựa chọn vòng sau.

~~~text
Giá trị cần đạt
   ↓ quyết định ưu tiên
Phần việc nhỏ, đủ rõ
   ↓ di chuyển qua workflow, giữ WIP hợp lý
Increment tích hợp và Done
   ↓ phát hành/thử nghiệm phù hợp, nhận phản hồi
Vòng lặp học hỏi và điều chỉnh backlog
   ↺ tiếp tục hướng đến giá trị
~~~

Trong tình huống này:

- **Giá trị** trả lời *tại sao làm* và *kết quả nào đáng theo đuổi*.
- **Vòng lặp** trả lời *khi nào và bằng cách nào học để đổi hướng*.
- **Increment** trả lời *đã có thêm khả năng sản phẩm hoàn tất nào*.
- **Workflow** trả lời *công việc đi qua các bước nào, đang tắc ở đâu*.

## 7. Đo lường để cải thiện mà không chạy theo chỉ số

Nhóm cần kết hợp **chỉ số kết quả sản phẩm** với **chỉ số luồng công việc**. Chỉ nhìn số hạng mục đã đóng có thể khiến nhóm tối ưu tốc độ hoàn thành việc ít giá trị.

| Chỉ số | Cách hiểu | Câu hỏi có ích |
| --- | --- | --- |
| **Outcome metric** (chỉ số kết quả) | Mức thay đổi ở hành vi hoặc lợi ích của người dùng/tổ chức, ví dụ tỷ lệ đặt lịch thành công. | Sản phẩm có giải quyết vấn đề không? |
| **Lead time** | Thời gian từ một điểm bắt đầu đã thống nhất (ví dụ yêu cầu được tiếp nhận) đến điểm giao/hoàn tất đã thống nhất. | Khách hàng phải chờ bao lâu? |
| **Cycle time** | Thời gian từ khi bắt đầu xử lý hạng mục đến khi hoàn tất. | Một hạng mục mất bao lâu sau khi thực sự bắt đầu? |
| **Throughput** | Số hạng mục hoàn tất trong một khoảng thời gian. | Năng lực giao hàng thực tế theo thời gian ra sao? |
| **WIP** | Số hạng mục đang làm dở tại một thời điểm. | Có quá nhiều việc mở cùng lúc không? |
| **Work item age** (tuổi hạng mục) | Thời gian một hạng mục đang làm đã tồn tại mà chưa hoàn tất. | Việc nào có dấu hiệu mắc kẹt? |
| **Quality signal** (tín hiệu chất lượng) | Lỗi sau phát hành, tỷ lệ thất bại kiểm thử, sự cố hoặc công sức sửa lỗi. | Tốc độ giao hàng có bền vững không? |

**Ví dụ minh họa:** hạng mục “cho phép đổi lịch” được yêu cầu ngày thứ Hai, nhóm bắt đầu xử lý ngày thứ Tư và hoàn tất ngày thứ Sáu. Nếu lấy điểm kết thúc là cuối thứ Sáu và quy ước tính theo ngày làm việc, lead time xấp xỉ **5 ngày làm việc** còn cycle time xấp xỉ **3 ngày làm việc**. Hai chỉ số khác nhau vì lead time tính cả thời gian chờ trước khi bắt đầu.

Các tổ chức có thể chọn mốc bắt đầu và kết thúc khác nhau cho “lead time”, vì vậy phải **công bố định nghĩa và dùng nhất quán** trước khi so sánh. Không nên đánh giá năng suất cá nhân bằng throughput, số dòng mã hoặc số story point: các chỉ số này phụ thuộc cách chia việc và dễ bị tối ưu sai mục đích.

Để cải thiện, nhóm có thể xem phân bố cycle time, các hạng mục tồn đọng lâu, nơi thường chờ duyệt hoặc chờ kiểm thử, rồi thử một thay đổi nhỏ như giảm WIP hoặc làm rõ điều kiện “Sẵn sàng”. Sau đó theo dõi xem thời gian chờ và chất lượng thực sự cải thiện hay không.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Agile là làm nhanh và bỏ kế hoạch.” | Agile hướng đến học nhanh, điều chỉnh có căn cứ; kế hoạch vẫn cần và được cập nhật khi có bằng chứng mới. |
| “Đã hoàn thành task nghĩa là tạo ra giá trị.” | Task hoàn tất chỉ là tín hiệu tiến độ. Giá trị phải gắn với kết quả sử dụng hoặc lợi ích được kiểm chứng. |
| “Một Sprint bằng một Increment.” | Sprint là timebox trong Scrum; trong Sprint có thể tạo nhiều Increment. Increment phải thỏa DoD và dùng được. |
| “Increment là một mảnh mã hoặc tài liệu đang làm.” | Increment là khả năng sản phẩm đã hoàn tất và tích hợp, không phải phần việc chưa kiểm chứng. |
| “Done đồng nghĩa với đã đưa lên production.” | Done thể hiện chuẩn hoàn tất; thời điểm phát hành là một quyết định riêng. |
| “Kanban chỉ cần treo bảng To do–Doing–Done.” | Cần định nghĩa workflow, chủ động quản lý WIP, quan sát luồng và cải thiện từ dữ liệu. |
| “Tất cả thành viên luôn bận nghĩa là hệ thống hiệu quả.” | Nhiều việc mở có thể làm tăng chờ đợi, chuyển ngữ cảnh và chậm giao giá trị. |
| “Càng nhiều story point/throughput càng tốt.” | Chỉ số có ý nghĩa khi đi cùng chất lượng, giá trị và cách đo nhất quán. |

## 9. Cách vận dụng khi bắt đầu một nhóm Agile

Không cần áp dụng ngay mọi nghi thức Scrum, Kanban hay XP. Có thể bắt đầu bằng những câu hỏi và hành động cụ thể:

1. **Làm rõ giá trị:** mỗi hạng mục ưu tiên có người hưởng lợi, vấn đề cần giải quyết và bằng chứng thành công dự kiến.
2. **Chia nhỏ sản phẩm:** tìm lát cắt chức năng có thể kiểm chứng từ đầu đến cuối; thống nhất tiêu chí chấp nhận và Definition of Done.
3. **Tạo nhịp phản hồi:** chọn thời điểm thường xuyên để xem phần mềm hoạt động, nghe người dùng và cập nhật backlog.
4. **Hiển thị workflow:** thống nhất trạng thái, quy tắc chuyển trạng thái, cách thể hiện công việc bị chặn và giới hạn WIP phù hợp.
5. **Đo điều cần cải thiện:** theo dõi thời gian chờ, việc dở dang, lỗi và một vài tín hiệu kết quả sản phẩm; dùng dữ liệu để thử thay đổi nhỏ trong quy trình.
6. **Kiểm tra tính thích ứng:** sau mỗi lần giao hoặc xem xét, chỉ ra một điều đã học và một quyết định đã thay đổi vì điều đó.

Một nhóm mới có thể bắt đầu với bảng công việc đơn giản, vòng phản hồi hằng tuần và các phần tăng trưởng nhỏ đáp ứng DoD. Khi có dữ liệu về rủi ro và nút thắt, nhóm điều chỉnh quy mô công việc, nhịp phối hợp hoặc phương pháp. Mục tiêu không phải giống một khuôn mẫu Agile nhất định mà là **duy trì khả năng tạo giá trị, nhận phản hồi sớm và cải tiến liên tục**.

## Ghi nhớ

**Giá trị** giúp chọn đúng vấn đề. **Vòng lặp** giúp học và thay đổi hướng đi. **Increment** bảo đảm mỗi lần tiến lên để lại phần sản phẩm dùng được. **Workflow** giúp công việc đi từ ý tưởng tới hoàn tất với ít chờ đợi và rủi ro hơn. Bốn yếu tố phối hợp để Agile trở thành cách phát triển phần mềm thích ứng dựa trên bằng chứng, thay vì chỉ là lịch họp hoặc tên một quy trình.

### Thuật ngữ chính

| Thuật ngữ | Nghĩa ngắn gọn |
| --- | --- |
| **Value** | Lợi ích/kết quả có ý nghĩa cho người dùng, tổ chức và các bên liên quan. |
| **Iteration** | Chu kỳ thực hiện–kiểm tra–học hỏi–điều chỉnh. |
| **Increment** | Phần sản phẩm tăng thêm, tích hợp và đáp ứng chuẩn hoàn tất. |
| **Feedback** | Thông tin từ kiểm chứng, sử dụng thực tế hoặc trao đổi giúp ra quyết định tiếp theo. |
| **Backlog** | Danh sách công việc/cơ hội có thứ tự ưu tiên và được cập nhật. |
| **Definition of Done** | Bộ tiêu chuẩn chất lượng để xác định một phần công việc sản phẩm đã hoàn tất. |
| **Workflow** | Các trạng thái và quy tắc đưa hạng mục qua quá trình làm việc. |
| **WIP** | Số hạng mục đã bắt đầu nhưng chưa hoàn tất. |


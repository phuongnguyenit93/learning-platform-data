# Áp dụng tiêu chí hoàn tất chung khi nhiều nhóm cùng phát triển sản phẩm

## 1. Một sản phẩm, nhiều nhóm: “xong phần tôi” chưa chắc là Done

Một nền tảng học trực tuyến có thể được phát triển bởi nhiều Scrum Team cùng làm trên **một sản phẩm**. Giả sử nhóm A phụ trách đăng nhập và phân quyền, nhóm B phụ trách bài học và tiến độ, nhóm C phụ trách trải nghiệm trang khóa. Mỗi nhóm đều báo phần việc của mình đã hoàn thành:

- Nhóm A đã cập nhật API xác thực và kiểm tra quyền học.
- Nhóm B đã thêm khả năng tìm bài học tiếp theo từ tiến độ.
- Nhóm C đã hiển thị nút “Tiếp tục học” trên giao diện.

Tuy nhiên, khi ghép các thay đổi, hệ thống lại cho phép mở bài học bằng đường dẫn trực tiếp mà không kiểm tra quyền hoặc giao diện gọi một phiên bản API khác với phiên bản được triển khai. **Các phần riêng lẻ có thể chạy, nhưng sản phẩm chung chưa sử dụng được một cách an toàn.**

Vấn đề này xuất hiện khi mỗi nhóm hiểu “Done” theo một cách: nhóm giao diện chỉ cần UI chạy ở máy mình, nhóm backend chỉ cần unit test xanh, nhóm tích hợp đợi đến cuối tháng mới ghép hệ thống. Trong Agile, cách làm đó đẩy lỗi và phản hồi về cuối, làm giảm khả năng giao sản phẩm tăng dần.

**Definition of Done (DoD)** giúp các thành viên và các nhóm có một tiêu chuẩn chung để biết khi nào một **Increment** thực sự đạt chất lượng cần thiết cho sản phẩm. Theo Scrum Guide 2020:

> Definition of Done là mô tả chính thức về trạng thái của Increment khi nó đáp ứng các thước đo chất lượng cần thiết cho sản phẩm.

Điểm quan trọng của bài này: **Khi nhiều Scrum Team cùng làm việc trên một sản phẩm, họ phải cùng xác định và tuân thủ cùng một Definition of Done.** Việc có nhiều nhóm, nhiều repository hoặc nhiều thành phần kỹ thuật không biến sản phẩm chung thành những chuẩn chất lượng độc lập.

## 2. DoD nằm ở đâu trong các tạo tác và cam kết của Scrum?

Scrum có ba tạo tác (artifacts) và ba cam kết gắn với chúng:

| Tạo tác Scrum | Cam kết | Vai trò |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Minh bạch công việc cần để cải thiện sản phẩm và mục tiêu dài hạn |
| **Sprint Backlog** | **Sprint Goal** | Minh bạch mục tiêu và kế hoạch thực hiện trong Sprint |
| **Increment** | **Definition of Done** | Minh bạch mức chất lượng bắt buộc để công việc được xem là hoàn tất |

Product Goal nói **hướng đến kết quả nào**, Sprint Goal nói **vì sao Sprint hiện tại có giá trị**, còn Definition of Done xác định **điều kiện chất lượng để một phần sản phẩm thực sự hoàn tất**. Ba cam kết bổ trợ nhau, không thay thế nhau.

Trong Scrum, một Increment là bước tiến cụ thể hướng tới Product Goal. Mỗi Increment phải được **cộng thêm vào các Increment trước** và được xác minh kỹ để tất cả hoạt động cùng nhau. Increment phải **sử dụng được** mới có thể mang lại giá trị. Khi một Product Backlog Item đáp ứng DoD, một Increment được tạo ra; trong cùng Sprint có thể có nhiều Increment.

Nếu PBI **chưa đạt DoD**, nó **không được xem là một phần Increment hoàn tất, không được phát hành như phần hoàn tất và không được trình bày tại Sprint Review như một Increment đã Done**. Nhóm vẫn có thể minh bạch về công việc dang dở hoặc rủi ro, nhưng không gắn nhãn Done để che phần chất lượng chưa đạt. Công việc chưa Done quay lại Product Backlog để xem xét tiếp theo.

### DoD không phải một mốc kiểm tra hình thức cuối Sprint

Một nhóm có thể đáp ứng DoD và tạo Increment **nhiều lần trong một Sprint**. Sprint Review không phải cổng bắt buộc để phát hành; Increment có thể được cung cấp cho stakeholder trước khi Sprint kết thúc khi các điều kiện liên quan đã đáp ứng. Vì vậy, DoD nên được thực hiện **trong quá trình phát triển và tích hợp**, không phải kiểm tra dồn vào buổi demo.

~~~mermaid
flowchart TD
    A["Product Goal chung"] --> B["Product Backlog chung"]
    B --> C["Các Scrum Team chọn và phát triển PBIs"]
    C --> D["Tích hợp và kiểm tra cùng một sản phẩm"]
    D --> E{"Đáp ứng DoD chung?"}
    E -->|"Chưa"| F["Sửa lỗi, hoàn thiện và kiểm tra lại"]
    F --> D
    E -->|"Đã đáp ứng"| G["Increment dùng được, cộng vào sản phẩm"]
    G --> H["Nhận phản hồi, kiểm tra kết quả"]
    H --> I["Điều chỉnh Product Backlog"]
    I --> C
~~~

## 3. Khi nào nhiều Scrum Team cần một DoD chung?

Scrum Guide nêu rõ: nếu nhiều Scrum Team cùng làm việc trên **một sản phẩm**, họ phải **cùng xác định và tuân thủ một Definition of Done**. Khi một Scrum Team quá lớn và được tổ chức lại thành nhiều Scrum Team cùng tập trung vào sản phẩm đó, các nhóm cũng chia sẻ **Product Goal, Product Backlog và Product Owner**.

Điểm phân biệt là **ranh giới sản phẩm**, không phải số lượng phòng ban, số repository hay sơ đồ tổ chức.

| Tình huống | Cách hiểu DoD |
| --- | --- |
| Hai Scrum Team phát triển các khả năng của cùng nền tảng học | Cùng một DoD phù hợp sản phẩm, không hạ tiêu chuẩn giữa các nhóm |
| Một nhóm làm giao diện, nhóm khác làm dịch vụ tiến độ cho cùng sản phẩm | Sự phân chia kỹ thuật không loại trừ yêu cầu tích hợp và DoD chung |
| Tổ chức có chuẩn bảo mật/kiểm thử chung | Mỗi Scrum Team phải tuân thủ chuẩn tổ chức như **mức tối thiểu**, bổ sung theo nhu cầu sản phẩm |
| Hai sản phẩm khác nhau với bối cảnh và rủi ro khác nhau | Có thể có DoD khác nhau phù hợp từng sản phẩm, vẫn tuân thủ chuẩn tổ chức |
| Một nhóm muốn thêm kiểm tra chuyên sâu cho thành phần của mình | Có thể thêm cách làm hoặc kiểm tra phù hợp, nhưng không được làm suy yếu DoD chung của sản phẩm |

### Chuẩn tổ chức và DoD sản phẩm

Nếu Definition of Done là một phần tiêu chuẩn của tổ chức, **tất cả Scrum Team phải tuân thủ ít nhất tiêu chuẩn đó**. Khi chưa có tiêu chuẩn tổ chức, Scrum Team tạo DoD phù hợp với sản phẩm. Với nhiều Scrum Team cùng phát triển một sản phẩm, các nhóm cùng xác định và tuân thủ cùng một DoD.

Ví dụ: tổ chức yêu cầu kiểm tra phân quyền và không đưa thông tin nhạy cảm vào log. Sản phẩm học trực tuyến còn cần kiểm tra tính toàn vẹn tiến độ học. DoD chung của sản phẩm phải phản ánh cả chuẩn tổ chức áp dụng lẫn yêu cầu chất lượng cần thiết này.

DoD chung **không cấm** một nhóm thực hiện kiểm thử chuyên biệt: nhóm thanh toán kiểm tra idempotency của callback, nhóm học tập kiểm tra trạng thái hoàn thành bài. Tuy nhiên, các kiểm tra quan trọng cho chất lượng Increment phải được phản ánh trong **tiêu chí chung theo điều kiện áp dụng rõ ràng**, thay vì để một nhóm tuyên bố Done dù phần rủi ro liên quan chưa được kiểm tra.

### DoD chung không có nghĩa một đội kiểm thử làm thay mọi nhóm

DoD là **tiêu chuẩn chất lượng chung**, không phải tên một bộ phận hay hàng đợi phê duyệt. Developers của các Scrum Team có trách nhiệm tạo Increment đáp ứng DoD; kỹ năng kiểm thử, bảo mật và vận hành có thể được phối hợp hoặc hỗ trợ chuyên sâu, nhưng không thể dùng một cổng QA ở cuối để thay cho chất lượng được xây dựng ngay từ đầu.

## 4. Phân biệt DoD, acceptance criteria, Definition of Ready và release

Đây là nguồn nhầm lẫn phổ biến nhất khi nhiều nhóm phối hợp.

| Khái niệm | Câu hỏi được trả lời | Phạm vi và ví dụ |
| --- | --- | --- |
| **Definition of Done (DoD)** | Khi nào Increment đủ chất lượng để được coi là hoàn tất? | Áp dụng thống nhất cho sản phẩm: tích hợp, kiểm thử, bảo mật, khả năng vận hành phù hợp |
| **Acceptance criteria** | Story/PBI cụ thể cần thể hiện hành vi nào? | Ghi danh khóa miễn phí phải tránh bản ghi trùng, kiểm tra quyền học và thông báo đúng trạng thái |
| **Definition of Ready (DoR)**, nếu nhóm sử dụng | Cần hiểu biết gì trước khi bắt đầu PBI? | Đủ rõ người dùng, quy tắc chính, phụ thuộc; **không phải thành phần bắt buộc của Scrum** |
| **Release checklist/điều kiện phát hành** | Có nên cung cấp phiên bản này cho người dùng ở thời điểm hiện tại? | Thời điểm kinh doanh, vận hành, kế hoạch rollout, pháp lý hoặc phê duyệt ngoài Scrum |
| **Task checklist** | Những bước cụ thể nào cần thực hiện? | Viết API, bổ sung UI, tạo dữ liệu test, cập nhật tài liệu |

**Acceptance criteria** bổ sung hành vi riêng cho từng PBI; chúng **không thay thế DoD**. Nếu story “Tiếp tục học” điều hướng đúng trong demo nhưng chưa kiểm thử quyền truy cập theo DoD, story chưa Done. Ngược lại, một thay đổi đã đáp ứng các tiêu chuẩn kỹ thuật chung nhưng không đáp ứng hành vi nghiệp vụ đã thống nhất cũng chưa hoàn tất.

**DoD và release là hai quyết định khác nhau.** Một Increment đạt DoD là sử dụng được, nhưng tổ chức có thể chọn thời điểm và đối tượng phát hành phù hợp; ví dụ dùng feature flag để mở dần cho học viên. Không nhất thiết phải phát hành vào cuối mỗi Sprint, và cũng không được coi “chưa có lịch phát hành” là lý do để giữ mã thiếu kiểm thử nhưng vẫn gắn Done.

Với thay đổi dữ liệu không thể đảo ngược đơn giản, việc tắt feature flag không tự khôi phục dữ liệu. Điều kiện phát hành, phương án chuyển đổi dữ liệu và khôi phục phải được đánh giá theo rủi ro thực tế.

## 5. Các nhóm cùng tạo DoD chung như thế nào?

Một DoD có ích phải **rõ ràng, kiểm tra được, phù hợp với sản phẩm và được mọi nhóm hiểu giống nhau**. Không nên bắt đầu bằng cách ghép toàn bộ checklist của mỗi phòng ban thành một danh sách dài mà không biết mục nào bảo vệ chất lượng gì.

### Bước 1 – Thống nhất ranh giới và luồng giá trị của sản phẩm

Xác định những thành phần nào tạo nên một trải nghiệm thống nhất. Chẳng hạn, người học bấm “Tiếp tục học” liên quan đồng thời đến:

- Danh tính, phiên đăng nhập và quyền truy cập.
- Dữ liệu tiến độ, quy tắc chọn bài tiếp theo.
- Giao diện, điều hướng và thông báo lỗi.
- Hệ thống theo dõi sự kiện và vận hành.

Nếu chỉ kiểm thử từng hệ thống riêng, chưa đủ chứng minh trải nghiệm dùng được. **Tích hợp các thay đổi vào cùng sản phẩm** là phần không thể bỏ qua.

### Bước 2 – Xác định tiêu chuẩn bắt buộc của tổ chức

Kiểm tra những quy tắc đã có về bảo mật, quyền riêng tư, quy trình dữ liệu, tính sẵn sàng, truy cập hoặc tuân thủ. Tổ chức có thể đã xác định mức tối thiểu chung; các nhóm không được tự bỏ một yêu cầu chỉ vì thấy nó làm story khó hoàn thành hơn.

### Bước 3 – Thu thập các rủi ro chất lượng đặc thù

Thảo luận với Developers, Product Owner và các chuyên gia cần thiết:

- Lỗi nào ảnh hưởng trực tiếp đến người dùng hoặc kết quả kinh doanh?
- API giữa các nhóm thường bị sai hợp đồng ở trường hợp nào?
- Dữ liệu học viên có nguy cơ bị truy cập trái phép hoặc mất tiến độ khi đồng bộ không?
- Việc thay đổi schema hoặc triển khai không đồng bộ có gây lỗi tương thích không?
- Increment có thể được xác minh trên môi trường tích hợp phù hợp hay chưa?

Chuyển rủi ro thành **điều kiện chất lượng có thể xác nhận**, không dừng ở khẩu hiệu “phải bảo đảm chất lượng cao”.

### Bước 4 – Viết tiêu chí và bằng chứng xác minh

Thay “đã test đầy đủ” bằng điều kiện cụ thể hơn: “các bài kiểm thử tự động bắt buộc liên quan chạy đạt trên phiên bản tích hợp, các kịch bản phân quyền rủi ro cao được xác nhận, không còn lỗi nghiêm trọng chưa xử lý theo chính sách chung”. Thước đo hiệu năng hoặc bảo mật cụ thể cần được thống nhất **theo yêu cầu sản phẩm**, không lấy một con số tùy ý áp cho mọi chức năng.

### Bước 5 – Thử DoD trên một vertical slice thật

Lấy một PBI đi từ giao diện qua backend và dữ liệu, kiểm tra:

- Có tiêu chí nào không xác minh được vì thiếu môi trường hoặc quyền truy cập?
- Có bước quan trọng nào bị hiểu khác nhau giữa nhóm A và B?
- Có việc kiểm tra trùng lặp không cần thiết hoặc điểm chờ khó tránh?
- Các tiêu chí có giúp tìm lỗi trước khi tích hợp cuối Sprint không?

Điều chỉnh cách tổ chức công việc và năng lực kỹ thuật để đáp ứng DoD. Không nên giải quyết mọi khó khăn bằng cách **hạ tiêu chuẩn**.

### Bước 6 – Công bố, duy trì và cải tiến có phối hợp

DoD nên được lưu ở nơi dễ tìm, giải thích được bằng ví dụ và gắn với công việc thực tế. Khi cần thay đổi DoD sản phẩm, các Scrum Team phải **phối hợp thống nhất** để tránh nhóm A dùng phiên bản cũ, nhóm B dùng phiên bản mới. Một thay đổi về chính sách dữ liệu hoặc loại lỗi phát hiện trong production có thể là tín hiệu để bổ sung tiêu chí mới.

PO cần hiểu hệ quả về giá trị, chất lượng và thứ tự công việc; Developers xác định cách đáp ứng các tiêu chí; Scrum Master hỗ trợ tăng hiệu quả Scrum và tháo gỡ trở ngại về cách phối hợp.

## 6. Ví dụ một Definition of Done chung cho nền tảng học

Bảng sau là **mẫu tham khảo**, không phải danh sách bắt buộc theo Scrum Guide. Một sản phẩm thực tế phải điều chỉnh theo mức rủi ro, chuẩn tổ chức và kiến trúc.

| Nhóm tiêu chí | Diễn đạt kiểm chứng được | Bằng chứng có thể dùng |
| --- | --- | --- |
| **Tích hợp** | Thay đổi được tích hợp vào phiên bản chung; các thành phần liên quan hoạt động cùng nhau | Build/pipeline tích hợp thành công, kết quả thử luồng |
| **Hành vi nghiệp vụ** | Các acceptance criteria liên quan được xác nhận; ngoại lệ quan trọng được xử lý | Test, ví dụ nghiệp vụ, kết quả kiểm tra với người hiểu nghiệp vụ |
| **Kiểm thử hồi quy** | Bộ kiểm thử bắt buộc ở mức phù hợp chạy đạt; không làm hỏng hành vi đã có | Kết quả CI, kiểm thử đơn vị/tích hợp/hợp đồng theo phạm vi |
| **Phân quyền và dữ liệu** | Quyền truy cập được kiểm soát tại nơi có thẩm quyền; dữ liệu nhạy cảm được bảo vệ | Kịch bản kiểm thử quyền, review thay đổi dữ liệu, kiểm tra bảo mật cần thiết |
| **Tương thích API** | Các bên tiêu thụ/gửi dữ liệu đáp ứng hợp đồng, xử lý phiên bản chuyển tiếp phù hợp | Contract test, kết quả thử tích hợp và thử tương thích |
| **Tính toàn vẹn dữ liệu** | Thay đổi schema, xử lý retry, lỗi và dữ liệu cũ không vi phạm quy tắc đã xác định | Test migration, tình huống gửi lặp, kiểm tra dữ liệu mẫu |
| **Hiệu năng/độ tin cậy** | Đáp ứng ngưỡng và kịch bản chất lượng đã thống nhất khi có liên quan | Kết quả kiểm tra tải, timeout, phục hồi phù hợp |
| **Khả năng tiếp cận** | Các hành trình UI mới đáp ứng tiêu chuẩn trợ năng áp dụng cho sản phẩm | Kiểm tra tương tác bàn phím, tên điều khiển, thử công cụ hỗ trợ khi cần |
| **Quan sát và vận hành** | Có cách phát hiện, chẩn đoán và ứng phó với lỗi quan trọng; không ghi log dữ liệu nhạy cảm | Dashboard/log/alert có kiểm soát, hướng dẫn xử lý, kịch bản thử |
| **Tài liệu và hiểu biết** | Thay đổi liên quan đến API, nghiệp vụ hoặc cách vận hành đã được cập nhật | Tài liệu ngắn, ghi quyết định, hướng dẫn cho người sử dụng liên quan |
| **Chất lượng mã** | Thay đổi được review theo chính sách, không còn lỗi chặn hoặc lỗi không thể chấp nhận theo chuẩn chung | Kết quả review, static analysis và danh sách lỗi đã giải quyết |
| **Sẵn sàng sử dụng** | Increment có thể được dùng trong điều kiện đã xác định; không phụ thuộc vào thành phần chưa được hoàn tất mà không có cách vận hành phù hợp | Luồng end-to-end, môi trường tích hợp, kế hoạch chuyển đổi khi cần |

Một số tiêu chí có phần **“khi áp dụng”**: giao diện chỉ cần kiểm tra trợ năng UI khi hạng mục có ảnh hưởng tương ứng, thay đổi không chạm dữ liệu có thể không cần migration. Nhưng điều kiện áp dụng phải minh bạch và nhất quán; không được lợi dụng “không áp dụng” để bỏ kiểm tra rủi ro thực tế.

### Viết tiêu chí rõ hơn thay vì dùng từ chung chung

| Diễn đạt khó kiểm chứng | Diễn đạt hữu ích hơn |
| --- | --- |
| “Chất lượng tốt.” | “Không còn lỗi blocker/critical chưa xử lý theo quy tắc chung và các bài kiểm thử bắt buộc đều đạt.” |
| “Đã kiểm thử.” | “Các kịch bản chấp nhận liên quan, phân quyền và kiểm thử hồi quy đã được xác minh trên bản tích hợp.” |
| “Backend xong.” | “Hợp đồng API phù hợp bên sử dụng, kiểm thử hợp đồng và luồng tích hợp liên quan đạt.” |
| “Triển khai được.” | “Bản tích hợp có thể triển khai theo quy trình đã xác định; thay đổi dữ liệu/tương thích có phương án xử lý phù hợp.” |
| “Bảo mật OK.” | “Các trường hợp truy cập trái quyền đã xác định được chặn và kiểm tra bảo mật theo chính sách áp dụng đạt.” |

DoD không cần liệt kê từng test case. Nó nêu **mức chất lượng chung**; trường hợp nghiệp vụ riêng được xác định bằng acceptance criteria, test case và tài liệu liên quan.

## 7. Ví dụ xuyên nhóm: một user story đi qua ba thành phần

### 7.1. Mục tiêu sản phẩm và user story

Giả sử Product Goal là giúp học viên duy trì tiến độ đầu khóa bằng trải nghiệm học đáng tin cậy. PO ưu tiên user story:

> “Là học viên đã có quyền học, tôi muốn tiếp tục từ bài tiếp theo khi quay lại trang khóa để không phải tìm lại vị trí đã học.”

Để tạo khả năng đó, cần ít nhất ba thành phần:

- **Nhóm A – quyền học:** xác thực, trạng thái ghi danh và kiểm tra quyền truy cập bài.
- **Nhóm B – tiến độ:** xác định bài hợp lệ tiếp theo theo quy tắc hoàn thành.
- **Nhóm C – trải nghiệm:** hiển thị hành động tiếp tục và xử lý trạng thái thành công/thất bại.

~~~mermaid
flowchart LR
    U["Học viên mở trang khóa"] --> UI["Nhóm C: giao diện Tiếp tục học"]
    UI --> AUTH["Nhóm A: kiểm tra quyền học"]
    AUTH --> PROG["Nhóm B: tra cứu tiến độ"]
    PROG --> NEXT["Xác định bài tiếp theo hợp lệ"]
    NEXT --> UI
    UI --> L["Học viên mở đúng bài được phép"]
    AUTH -. "Không có quyền" .-> DENY["Không cấp truy cập trái phép"]
    PROG -. "Không còn bài" .-> DONE["Hiển thị hoàn tất khóa"]
~~~

Nếu nhóm C hoàn thành giao diện mà nhóm B chưa cung cấp dữ liệu tin cậy, **user story của hành trình đầy đủ chưa đạt DoD**. Nếu API tiến độ hoàn tất nhưng chưa tích hợp với kiểm tra quyền, **Increment sản phẩm vẫn chưa được chứng minh là an toàn trong luồng cần dùng**.

### 7.2. Acceptance criteria của story

~~~gherkin
Feature: Tiếp tục học từ trang khóa

  Scenario: Học viên có quyền học và còn bài tiếp theo
    Given học viên đã đăng nhập và có quyền truy cập khóa
    And một bài đã được ghi nhận hoàn tất theo quy tắc
    When học viên mở trang khóa và chọn "Tiếp tục học"
    Then hệ thống mở đúng bài tiếp theo hợp lệ
    And không làm thay đổi sai trạng thái tiến độ hiện tại

  Scenario: Người không có quyền dùng đường dẫn trực tiếp
    Given người dùng không có quyền truy cập nội dung khóa
    When người dùng yêu cầu mở liên kết trực tiếp đến bài học
    Then hệ thống từ chối truy cập tại nơi có thẩm quyền
    And không tiết lộ thông tin học tập bị hạn chế

  Scenario: Học viên đã hoàn thành bài cuối
    Given học viên có quyền học và đã hoàn thành bài cuối
    When học viên mở trang khóa
    Then hệ thống hiển thị trạng thái hoàn thành phù hợp
    And không điều hướng đến bài không tồn tại
~~~

Các tình huống này minh họa cho chính sách giả định; người có thẩm quyền nghiệp vụ cần xác nhận ý nghĩa “hoàn tất” và “bài tiếp theo”, nhất là khi khóa cho phép học không theo thứ tự.

### 7.3. Đối chiếu DoD chung theo hành trình

| Điều kiện chung | Bằng chứng cần cho story này |
| --- | --- |
| Tích hợp Increment | Giao diện, quyền học và tiến độ hoạt động trên cùng bản tích hợp |
| Kiểm thử nghiệp vụ | Ba tình huống Gherkin được thực thi/xác minh, cùng trường hợp dữ liệu thiếu theo rủi ro |
| Kiểm soát quyền | Bài học bị chặn nếu thiếu quyền ngay cả khi gửi yêu cầu trực tiếp |
| Tương thích hợp đồng | Phản hồi API tiến độ tương thích với bên dùng, xử lý trạng thái không còn bài |
| Hồi quy | Không làm hỏng việc ghi danh, mở bài hoặc lưu tiến độ trước đây |
| Vận hành | Lỗi điều hướng/tiến độ có thể được phát hiện và kiểm tra bằng thông tin không nhạy cảm |
| Chất lượng chung | Review, pipeline và kiểm tra thích hợp đã đạt, không còn lỗi chặn |

Việc tạo ba task ở ba nhóm **không làm nên ba Increment độc lập của story này**. Nhóm phải đánh giá kết quả ở mức **sản phẩm chung**. Có thể tổ chức công việc theo nhiều PBI nhỏ hơn khi mỗi PBI thực sự tạo ra một Increment dùng được và đáp ứng DoD; không nên gọi một task triển khai dở là PBI Done chỉ để cộng điểm hoàn thành.

## 8. Tích hợp liên tục để không dồn “Done thật” về cuối

Khi nhiều nhóm phát triển cùng sản phẩm, việc chỉ ghép mã vào cuối Sprint tạo ra rủi ro:

- Hợp đồng API giữa nhóm A và B có thể đã thay đổi.
- Quy tắc dữ liệu tiến độ không còn khớp giao diện.
- Schema mới không tương thích phiên bản đang chạy.
- Bộ test của từng nhóm đều xanh nhưng luồng end-to-end bị hỏng.
- Lỗi phân quyền chỉ xuất hiện khi các thành phần được kết nối.

Một hệ thống kỹ thuật hỗ trợ DoD chung thường gồm **tích hợp liên tục (CI)**, kiểm thử tự động đa tầng, kiểm tra hợp đồng, review thay đổi và môi trường tích hợp đáng tin cậy. Các thực hành XP như kiểm thử tự động, refactoring và phát triển theo lát nhỏ giúp giữ sản phẩm ở trạng thái có thể thích ứng.

### Các tầng bằng chứng kiểm thử

| Cấp kiểm tra | Phát hiện loại vấn đề nào? | Điểm cần lưu ý |
| --- | --- | --- |
| **Unit test** | Quy tắc tính bài tiếp theo, kiểm tra điều kiện, xử lý biến thể | Nhanh, nhưng không chứng minh các dịch vụ phối hợp đúng |
| **Component/service test** | Hành vi một dịch vụ với dữ liệu và phụ thuộc được kiểm soát | Cần tránh phụ thuộc giả lập khác hẳn môi trường thật |
| **API/contract test** | Tương thích giữa bên cung cấp và bên tiêu thụ API | Cần có cơ chế kiểm tra khi hợp đồng thay đổi |
| **Integration test** | Kết nối các dịch vụ, cơ sở dữ liệu, sự kiện và quyền | Tốn công môi trường, nên chọn kịch bản giá trị/rủi ro cao |
| **End-to-end test** | Hành trình người dùng hoàn chỉnh qua nhiều thành phần | Không cần tự động hóa mọi biến thể qua UI; ưu tiên luồng trọng yếu |
| **Security/performance/operational checks** | Truy cập trái quyền, dữ liệu nhạy cảm, tải và khả năng quan sát | Mức kiểm tra và ngưỡng dựa trên rủi ro sản phẩm |

**Không có yêu cầu Scrum phải dùng một công cụ CI/CD cụ thể hoặc đạt một phần trăm coverage cố định.** Các nhóm quyết định cách hiện thực hóa tiêu chí chất lượng đã thỏa thuận, ưu tiên những kiểm tra cung cấp phản hồi sớm và đáng tin.

### Phối hợp thay đổi giữa các nhóm

Nếu nhóm B muốn đổi trường phản hồi API từ trạng thái số sang trạng thái chữ, họ cần:

1. Làm rõ tác động lên nhóm C và những bên tiêu thụ khác.
2. Thống nhất hợp đồng hoặc chiến lược tương thích ngược trong giai đoạn chuyển tiếp.
3. Bổ sung/điều chỉnh contract test và kiểm thử tích hợp.
4. Phối hợp thứ tự triển khai nếu các phiên bản có thể tồn tại đồng thời.
5. Kiểm tra bản tích hợp đạt DoD trước khi tuyên bố Increment Done.

Nếu thay đổi buộc tất cả hệ thống triển khai đồng thời, nhóm nên nhận diện rủi ro và cân nhắc chia thành các bước tương thích. Mục tiêu là giảm phụ thuộc dồn cuối, **không phải thêm một cuộc họp phê duyệt cho mỗi API**.

## 9. Ai chịu trách nhiệm đáp ứng DoD khi công việc trải nhiều nhóm?

Scrum định nghĩa Developers chịu trách nhiệm về chất lượng bằng cách tuân thủ Definition of Done. Khi có nhiều Scrum Team cho cùng sản phẩm, **các nhóm cùng tuân thủ một DoD**; không có lý do để chuyển toàn bộ trách nhiệm chất lượng sang nhóm được giao “kiểm thử cuối”.

| Câu hỏi phối hợp | Cách tiếp cận phù hợp |
| --- | --- |
| Ai làm rõ giá trị và ưu tiên PBI? | Product Owner chung chịu trách nhiệm Product Backlog hiệu quả |
| Ai tạo Increment và đáp ứng DoD? | Developers của các Scrum Team phối hợp để tạo phần mềm tích hợp đạt chất lượng |
| Ai giải quyết phụ thuộc thiết kế/API? | Các thành viên chuyên môn liên quan trao đổi trực tiếp, cập nhật hợp đồng và kiểm tra chung |
| Ai hỗ trợ cải thiện hiệu quả Scrum và trở ngại phối hợp? | Scrum Master(s) hỗ trợ Scrum Team và tổ chức phù hợp accountability của mình |
| Ai xác định quy tắc an toàn/nghiệp vụ đặc thù? | Người có thẩm quyền/kiến thức phù hợp cung cấp yêu cầu; nhóm biến thành tiêu chí có thể kiểm tra |
| Ai xác nhận PBI Done? | Dựa vào việc **đáp ứng DoD và tiêu chí liên quan**, không chỉ chữ ký của một quản lý hoặc QA cuối |

### Phụ thuộc phải được minh bạch ngay từ lập kế hoạch

Nếu nhóm C cần endpoint của nhóm B, đó là rủi ro cần làm rõ trong refinement và Sprint Planning, không đợi tới ngày demo. Có thể tổ chức một lát dọc xuyên nhóm, hoặc ưu tiên một khả năng hạ tầng thực sự có thể tích hợp và dùng được. Developers lựa chọn cách phối hợp trong thực tế; Product Owner cân nhắc giá trị và thứ tự của các PBIs.

### Tránh tạo thứ bậc điều phối không cần thiết

DoD chung không có nghĩa nhóm A luôn là “nhóm trưởng” phê duyệt việc của B, hay Scrum Master trở thành quản lý tiến độ liên nhóm. Khi cần quyết định kiến trúc, chất lượng và vận hành, nhóm có thể dùng tiêu chuẩn chung, trao đổi chuyên môn trực tiếp, automation và cơ chế xử lý bất đồng rõ ràng.

## 10. Thực hành DoD chung trong Sprint Planning, Daily Scrum và Sprint Review

### Refinement và Sprint Planning

Khi làm rõ PBI, các nhóm cần biết **toàn bộ công việc để đáp ứng DoD**: không chỉ viết mã mà cả tích hợp, kiểm thử, quyền truy cập, dữ liệu, khả năng vận hành và phụ thuộc giữa nhóm. Một story tưởng nhỏ có thể cần tách lát hoặc spike nếu chưa rõ hợp đồng bên ngoài.

Sprint Goal hướng dẫn lựa chọn công việc và cách phối hợp; DoD xác định chất lượng không thể bỏ qua. Khi nhiều nhóm phục vụ cùng sản phẩm, họ có thể có Sprint riêng trong cùng cấu trúc sản phẩm nhưng **không được dùng những DoD mâu thuẫn** khiến Increment không kết nối được.

### Trong Sprint và Daily Scrum

Daily Scrum giúp Developers kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog. Các nhóm có thể bổ sung cơ chế phối hợp liên nhóm khi cần: làm rõ phiên bản API, xử lý blocker, chia sẻ tín hiệu pipeline và thống nhất thời điểm tích hợp. Những cơ chế hỗ trợ này **không thay thế các sự kiện Scrum** và không cần biến thành lịch họp nặng nề.

### Trong Sprint Review

Scrum Team và stakeholder kiểm tra **Increment đã đạt DoD** và tiến triển Product Goal. Nếu luồng “Tiếp tục học” mới chạy trên mock nhưng không kiểm tra quyền thật, không được trình bày nó như Increment hoàn tất. Có thể giải thích minh bạch hạng mục chưa Done và tác động lên backlog, nhưng chất lượng không được hạ chỉ để có nhiều chức năng trong buổi Review.

Increment **có thể được phát hành trước Sprint Review**. Review là cơ hội kiểm tra kết quả và điều chỉnh hướng sản phẩm, không phải cổng bắt buộc phê duyệt release.

### Trong Sprint Retrospective

Khi phát hiện lỗi tích hợp lặp lại, các nhóm nên kiểm tra nguyên nhân về hợp đồng, môi trường, test hoặc tổ chức công việc và chọn cải tiến cụ thể. Ví dụ:

- Tạo contract test chạy khi API thay đổi.
- Đưa một kiểm thử quyền truy cập xuyên thành phần vào pipeline tích hợp.
- Giảm thời gian chờ môi trường kiểm thử.
- Chia story nhỏ hơn để tích hợp được hằng ngày.

**Cải tiến cách đáp ứng DoD** khác với **giảm tiêu chuẩn DoD**. Nếu không thể hoàn tất thường xuyên, nhóm cần tìm bottleneck và tăng năng lực kỹ thuật, không tự đánh dấu Done khi chất lượng chưa đạt.

## 11. Xử lý các trường hợp khó: Done cục bộ, ngoại lệ và phát hành

| Tình huống | Có được coi PBI/Increment chung là Done không? | Hướng xử lý |
| --- | --- | --- |
| UI chạy với mock, API thật chưa tích hợp | **Chưa**, nếu hành vi tích hợp là điều kiện của PBI | Hoàn tất kết nối và kiểm tra theo DoD |
| Unit test của từng nhóm xanh nhưng end-to-end thất bại | **Chưa** | Sửa lỗi phối hợp và kiểm tra hồi quy |
| Chức năng đáp ứng acceptance criteria nhưng lộ dữ liệu học viên khác | **Chưa** | Sửa phân quyền, đánh giá sự cố và kiểm thử bảo mật |
| Đã tích hợp, đạt DoD nhưng chưa bật feature flag cho mọi người | **Có thể Done**, nếu Increment sử dụng được và DoD được đáp ứng | Phân biệt quyết định release/rollout với trạng thái chất lượng |
| PBI được phát triển xong mã nhưng còn migration dữ liệu bắt buộc chưa thử | **Chưa** | Kiểm tra migration, tương thích và phương án vận hành |
| Một thành phần không có giao diện không cần test trợ năng UI | **Có thể không áp dụng tiêu chí UI**, nếu DoD nêu rõ điều kiện áp dụng | Kiểm tra các tiêu chí khác phù hợp phạm vi thành phần |
| Nhóm phụ trách API có thêm kiểm tra bảo mật chuyên sâu | **Không mâu thuẫn**, nếu vẫn đáp ứng DoD chung | Tiếp tục kiểm tra theo rủi ro chuyên biệt và chia sẻ bài học |
| Một quản lý chấp nhận bỏ qua kiểm tra bảo mật bắt buộc | **Không thể dùng chữ ký thay DoD** | Giải quyết rủi ro và cơ chế quản trị phù hợp trước khi gọi Done |

### Nếu thật sự có ngoại lệ thì sao?

Trong thực tế, có lúc tiêu chí bị chặn bởi môi trường ngoài hoặc công cụ không sẵn sàng. Nhóm cần **minh bạch về việc chưa đáp ứng DoD** và xem lại phạm vi/cách thực hiện. Một quyết định phát hành khẩn cấp theo quy trình sự cố của tổ chức không tự biến phần mềm thành Increment đã đạt DoD. Không nên tạo “ngoại lệ ngầm” cho từng Sprint để con số hoàn thành đẹp hơn.

Nếu một tiêu chí của DoD được viết quá chung, không phù hợp hoặc khó xác minh, các nhóm nên **cùng cải tiến định nghĩa và cách đo**, vẫn giữ các chuẩn tổ chức và mức chất lượng cần thiết của sản phẩm. Việc sửa DoD phải minh bạch, không hồi tố gắn Done cho hạng mục trước đó khi tiêu chuẩn thực tế chưa được đáp ứng.

## 12. Dùng số liệu để cải tiến khả năng đáp ứng DoD chung

Một DoD có thể được viết rất hay nhưng quy trình thực tế vẫn có hàng đợi tích hợp lớn hoặc lỗi thường xuyên xuất hiện sau phát hành. Cần kết hợp bằng chứng kỹ thuật với dữ liệu dòng công việc:

| Chỉ số/tín hiệu | Điều có thể quan sát | Cần tránh |
| --- | --- | --- |
| **Số lỗi tích hợp phát hiện muộn** | Hợp đồng giữa nhóm hoặc kiểm thử chung có vấn đề | Quy lỗi ngay cho một nhóm mà không xem hệ thống |
| **Thời gian chờ kiểm thử/tích hợp** | Môi trường, pipeline hoặc phụ thuộc trở thành bottleneck | Cắt kiểm thử quan trọng để giảm số liệu |
| **Cycle time** | Mất bao lâu để một PBI đi từ bắt đầu đến hoàn tất theo chính sách | Thay đổi định nghĩa Done để làm thời gian ngắn giả tạo |
| **Work item age** | PBI nào đang làm quá lâu và có nguy cơ bị chặn | Chỉ theo dõi việc đã Done, bỏ qua việc đang chờ |
| **WIP** | Có quá nhiều hạng mục mở đồng thời? | Đẩy nhiều việc sang trạng thái “xong cục bộ” để che WIP |
| **Throughput** | Số hạng mục hoàn thành trong khoảng thời gian | So sánh các nhóm có kích thước hạng mục khác nhau như đơn vị tương đương |
| **Lỗi sau phát hành** | Chất lượng thực tế có được bảo vệ hay không | Chỉ đo số lượng lỗi mà không xem mức độ ảnh hưởng |
| **Outcome sản phẩm** | Người học có đăng ký và tiếp tục học tốt hơn? | Đánh đồng tăng số ticket Done với tăng giá trị |

Một nhóm có thể dùng Kanban để trực quan hóa luồng “Đang làm → Kiểm thử → Tích hợp → Done”, giới hạn WIP và chú ý hạng mục chờ lâu. Tuy nhiên, **Done trên bảng** phải thống nhất với **DoD sản phẩm**, không được tạo cột Done riêng cho từng nhóm rồi cộng chúng như Increment đã hoàn tất.

**Velocity/story point** nếu có dùng để dự báo nội bộ không phải chỉ số so sánh năng suất giữa các Scrum Team. Các nhóm có thể ước lượng khác nhau; tăng tổng điểm không chứng minh sản phẩm tốt hơn.

## 13. Mô hình phối hợp đề xuất cho nhiều Scrum Team

Một cách vận hành gọn có thể gồm những vòng phối hợp sau:

1. **Trước khi thực hiện:** Product Owner giúp làm rõ Product Goal, Product Backlog và ưu tiên; Developers của các nhóm chia lát, nêu phụ thuộc, thống nhất acceptance criteria và điều kiện DoD.
2. **Trong phát triển:** tích hợp thay đổi nhỏ thường xuyên, chạy kiểm thử tự động phù hợp, kiểm tra hợp đồng giữa các bên và xử lý blocker trực tiếp.
3. **Khi một PBI đến gần Done:** kiểm tra hành trình dùng thật cùng tiêu chí chung, không chỉ tổng hợp trạng thái task từng nhóm.
4. **Khi có Increment:** bảo đảm DoD đã đạt, phát hành khi phù hợp và thu thập bằng chứng phản hồi.
5. **Sau khi quan sát:** Scrum Team cùng stakeholder kiểm tra kết quả tại Sprint Review, PO cập nhật thứ tự backlog; các nhóm cải tiến kỹ thuật/phối hợp trong Retrospective.
6. **Khi xuất hiện rủi ro mới:** cùng xem lại DoD và cách kiểm tra, không âm thầm tạo chuẩn riêng mâu thuẫn.

~~~mermaid
flowchart TD
    A["Một Product Owner + Product Goal + Product Backlog"] --> B["Các Scrum Team chọn lát có giá trị"]
    B --> C["Phát triển song song nhưng tích hợp liên tục"]
    C --> D["Kiểm tra DoD chung ở mức sản phẩm"]
    D --> E{"Tất cả tiêu chí áp dụng đã đạt?"}
    E -->|"Không"| F["Cùng sửa lỗi / tháo phụ thuộc"]
    F --> C
    E -->|"Có"| G["Increment dùng được"]
    G --> H["Phát hành phù hợp và kiểm tra phản hồi"]
    H --> I["Cải tiến backlog và cách phối hợp"]
    I --> B
~~~

Đây là **mô hình thực hành minh họa**, không phải quy trình Scrum có thêm sự kiện bắt buộc. Một tổ chức có thể chọn công cụ và nhịp phối hợp khác nếu vẫn bảo đảm tính minh bạch, tự quản, Increment sử dụng được và cùng DoD.

## 14. Các phản mẫu khi nhiều nhóm cùng một sản phẩm

| Phản mẫu | Hậu quả | Điều chỉnh |
| --- | --- | --- |
| **Mỗi nhóm có một định nghĩa Done không tương thích** | Không biết sản phẩm đã hoàn tất ở mức nào | Cùng xây và tuân thủ DoD chung phù hợp sản phẩm |
| **Done = code merged vào repository của nhóm** | Sai lệch API, phân quyền và dữ liệu chỉ phát hiện khi ghép | Kiểm thử trên bản tích hợp và hành trình xuyên thành phần |
| **Dồn mọi kiểm thử tích hợp tới cuối Sprint/quý** | Lỗi phát hiện muộn, không tạo Increment đều đặn | Tích hợp liên tục, kiểm thử hợp đồng và luồng trọng yếu sớm |
| **Có một đội QA làm cổng chất lượng thay cho Developers** | Chờ đợi, trách nhiệm chất lượng bị chuyển giao | Developers xây chất lượng trong khi làm, dùng chuyên gia hỗ trợ khi cần |
| **DoD là checklist dài nhưng không có bằng chứng** | Người ký xác nhận khác nhau, chất lượng không minh bạch | Viết tiêu chí kiểm chứng được, tự động hóa phù hợp |
| **Hạ DoD để kịp demo** | Tăng nợ kỹ thuật, tạo cảm giác Done giả | Giảm phạm vi chức năng hoặc làm rõ kế hoạch, không bỏ chất lượng |
| **Nhầm acceptance criteria với DoD** | Story chạy đúng một tình huống nhưng chưa an toàn/vận hành được | Kết hợp yêu cầu nghiệp vụ và chuẩn chất lượng chung |
| **Nhầm DoD với quyết định release** | Chậm giao giá trị hoặc tưởng đã phát hành là đã Done | Phân biệt chất lượng Increment và lịch rollout |
| **Hợp đồng API thay đổi không thông báo nhóm dùng** | Phá vỡ luồng tích hợp dù test cục bộ đạt | Thử tương thích, công bố thay đổi, phối hợp phiên bản |
| **Đếm ticket cục bộ để đo giá trị** | Ba task Done được báo thành ba Increment có giá trị | Đo khả năng sử dụng, DoD chung và outcome |
| **Đưa tiêu chuẩn quá chung như “test đầy đủ”** | Mỗi nhóm tự hiểu khác nhau | Định nghĩa mức kiểm tra và điều kiện áp dụng rõ |
| **Biến việc thay đổi DoD thành quyền của một nhóm** | Tiêu chuẩn không thống nhất, gây phụ thuộc và tranh chấp | Cùng thống nhất thay đổi và tôn trọng chuẩn tổ chức |

Mục đích của một DoD chung không phải bảo đảm không bao giờ có lỗi. Nó làm chất lượng **minh bạch và có thể kiểm tra**, giúp giảm rủi ro khi nhiều nhóm thay đổi cùng một sản phẩm, từ đó giao Increment đều đặn hơn.

## 15. Bài thực hành: thiết kế DoD chung cho ba Scrum Team

### 15.1. Bối cảnh

Ba Scrum Team cùng phát triển một nền tảng học trực tuyến:

- **Team Identity:** quản lý tài khoản, đăng nhập, quyền truy cập.
- **Team Learning:** quản lý bài học, tiến độ và trạng thái hoàn thành.
- **Team Experience:** quản lý trang khóa, điều hướng và tương tác người học.

Product Goal: giúp học viên có thể bắt đầu, quay lại và tiếp tục học an toàn với tiến độ chính xác.

Trong Sprint vừa qua:

1. Team Experience hoàn thành UI “Tiếp tục học” và unit test giao diện.
2. Team Learning hoàn thành API trả về bài tiếp theo, nhưng chưa kiểm tra hợp đồng với bản UI mới.
3. Team Identity thay đổi chính sách cấp quyền, nhưng chưa triển khai trên môi trường tích hợp.
4. Buổi demo cục bộ chạy được nhờ mock dữ liệu, nhưng thử liên kết trực tiếp thực tế có nguy cơ bỏ qua kiểm tra quyền.
5. Mỗi nhóm đang dùng một checklist Done khác nhau.

### 15.2. Nhiệm vụ

1. Giải thích **vì sao ba nhóm không thể gọi toàn bộ user story “Tiếp tục học” là Done** từ năm thông tin trên.
2. Viết **một DoD chung** gồm ít nhất sáu tiêu chí có thể kiểm chứng, bao gồm tích hợp, nghiệp vụ, phân quyền, hồi quy, dữ liệu và vận hành.
3. Tách **ba acceptance criteria của story** khỏi các tiêu chí chất lượng chung.
4. Nêu **bằng chứng** để kiểm tra từng điều kiện, không chỉ ghi “QA approved”.
5. Đề xuất **một thay đổi trong CI/integration** để phát hiện lỗi sớm hơn.
6. Giải thích tình huống nếu UI đã xong nhưng hợp đồng API vẫn sai: nên ghi trạng thái công việc và trao đổi tại Sprint Review thế nào?
7. Chọn một chỉ số luồng và một chỉ số sản phẩm để xem giải pháp phối hợp tốt hơn có tạo giá trị hay không.

### 15.3. Lời giải tham khảo

**Vì sao chưa Done?** Các phần mới hoạt động trong môi trường cục bộ, chưa chứng minh luồng có thể sử dụng cùng nhau và chưa đáp ứng an toàn truy cập; hơn nữa, ba nhóm chưa có một DoD thống nhất để đánh giá Increment.

**DoD chung ứng viên:**

| Điều kiện | Bằng chứng kỳ vọng |
| --- | --- |
| Bản tích hợp của các thay đổi liên quan chạy được | Pipeline build/integration đạt và thử luồng người dùng thật |
| Các kịch bản chấp nhận quan trọng được xác nhận | Kết quả test cho trường hợp còn bài, hết bài, không có quyền |
| Không bỏ qua kiểm soát truy cập phía máy chủ | Test liên kết trực tiếp trái quyền và dữ liệu học viên khác |
| API giữa các nhóm tương thích ở phiên bản tích hợp | Contract test giữa bên cung cấp và tiêu thụ đạt |
| Tiến độ không bị ghi hoặc đọc sai theo quy tắc đã thống nhất | Test dữ liệu cũ, retry, trạng thái thiếu dữ liệu khi áp dụng |
| Kiểm thử hồi quy và review chất lượng bắt buộc đạt | CI xanh, kết quả review và các lỗi chặn đã xử lý |
| Lỗi quan trọng có thể chẩn đoán mà không lộ dữ liệu cá nhân | Kiểm tra log/metric và hướng ứng phó phù hợp |

**Acceptance criteria riêng của story:** (1) học viên có quyền mở đúng bài tiếp theo; (2) học viên hoàn thành bài cuối không bị điều hướng sai; (3) người không có quyền bị chặn, kể cả đường dẫn trực tiếp. Các tiêu chí này mô tả **hành vi nghiệp vụ**, còn DoD chung quy định **mức chất lượng** cho mọi Increment liên quan.

**Cải tiến kỹ thuật:** chạy contract test khi Team Learning thay API và Team Experience cập nhật bên tiêu thụ; thử một hành trình end-to-end có kiểm tra quyền trong CI. Không cần tự động hóa mọi kịch bản UI, nhưng cần bảo vệ các luồng rủi ro cao.

**Cách báo trạng thái:** UI task có thể hoàn thành theo tiêu chí task, nhưng PBI/Increment chung **chưa Done**. Tại Sprint Review, nhóm nói rõ kết quả và trở ngại, không trình bày demo mock như Increment sẵn sàng sử dụng. Các PBI chưa đạt DoD được xem lại trong Product Backlog; PO và Developers phối hợp bước tiếp theo.

**Đo lường:** dùng **cycle time của PBI xuyên nhóm** để xem thời gian chờ tích hợp có giảm; đồng thời đo **tỷ lệ học viên đủ điều kiện mở được bài tiếp theo** và theo dõi lỗi phân quyền/mất tiến độ làm guardrail. Việc rút ngắn cycle time không có ý nghĩa nếu chất lượng hoặc outcome giảm.

Lời giải này chỉ là điểm khởi đầu. DoD thật cần các Scrum Team và người có trách nhiệm thống nhất dựa trên tiêu chuẩn tổ chức, rủi ro sản phẩm và khả năng kiểm chứng hiện có.

## 16. Checklist áp dụng DoD chung

- [ ] Đã xác định **ranh giới của một sản phẩm**, không nhầm với ranh giới repository hoặc phòng ban?
- [ ] Nếu nhiều Scrum Team cùng sản phẩm, các nhóm có **cùng Product Goal, Product Backlog, Product Owner** theo Scrum?
- [ ] Các nhóm đã **cùng xác định và tuân thủ một Definition of Done**?
- [ ] DoD tôn trọng **tiêu chuẩn tổ chức như mức tối thiểu** nếu có?
- [ ] Tiêu chí chất lượng được viết **có thể kiểm tra**, với điều kiện áp dụng rõ ràng?
- [ ] Đã phân biệt **DoD, acceptance criteria, DoR và quyết định release**?
- [ ] Công việc được đánh giá theo **Increment tích hợp và dùng được**, không chỉ task cục bộ?
- [ ] Hợp đồng API, thay đổi dữ liệu và phiên bản giữa các nhóm được kiểm tra thích hợp?
- [ ] Các rủi ro về **phân quyền, dữ liệu, hiệu năng và vận hành** được bảo vệ theo nhu cầu sản phẩm?
- [ ] Có cách tích hợp liên tục và phát hiện sai lệch sớm, thay vì đợi cuối Sprint?
- [ ] PBI chưa đạt DoD được **minh bạch là chưa hoàn tất**, không gắn Done để làm đẹp báo cáo?
- [ ] Các Scrum Team cùng chịu trách nhiệm chất lượng, không chuyển hết sang cổng QA cuối?
- [ ] Việc thay đổi DoD được **phối hợp và áp dụng nhất quán** giữa các nhóm?
- [ ] Số liệu về **WIP, cycle time, lỗi tích hợp và outcome** được dùng để cải tiến thay vì xếp hạng nhân viên?
- [ ] Increment đã đạt DoD có thể được xem xét phát hành phù hợp mà không chờ Review như cổng phê duyệt?

**Ghi nhớ:** Khi nhiều Scrum Team cùng phát triển một sản phẩm, **Definition of Done chung** bảo đảm mọi người có cùng cách hiểu về chất lượng của Increment. Hoàn thành giao diện, API hay database riêng lẻ chưa đủ; các thay đổi phải **tích hợp, được kiểm tra và dùng được cùng nhau** ở mức sản phẩm. Giữ tiêu chuẩn chung, phối hợp sớm và cải tiến luồng công việc giúp Agile giao giá trị tăng dần với phản hồi đáng tin cậy, thay vì tích lũy những phần việc “xong cục bộ” nhưng chưa tạo thành sản phẩm hoàn chỉnh.

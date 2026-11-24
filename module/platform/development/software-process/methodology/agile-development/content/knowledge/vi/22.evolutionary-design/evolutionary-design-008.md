# Điều phối kiến trúc giữa các nhóm bằng ràng buộc cùng quyết định rõ ràng

Một nền tảng học trực tuyến được phát triển bởi ba nhóm: **Identity** phụ trách tài khoản và quyền truy cập, **Learning** phụ trách nội dung và tiến độ học, **Assessment** phụ trách bài kiểm tra. Trong Sprint đầu, mỗi nhóm làm rất nhanh. Sang Sprint tiếp theo, Learning truy vấn thẳng bảng kết quả kiểm tra của Assessment, Assessment tự sao chép thông tin quyền truy cập từ Identity, còn Identity đổi cấu trúc dữ liệu mà không thông báo. Một thay đổi nhỏ ở quy tắc hoàn thành khóa học khiến cả ba nhóm phải sửa mã, đồng bộ triển khai và xử lý lỗi tích hợp.

Giải pháp không nhất thiết là một kiến trúc sư trung tâm **phê duyệt từng lớp, từng API và từng pull request**. Cách đó có thể làm tăng chờ đợi và giảm quyền tự chủ. Nhưng để các nhóm **tự quyết mọi thứ mà không có nguyên tắc chung** cũng có thể tạo dữ liệu không nhất quán, hợp đồng dễ gãy và khó giao Increment có thể sử dụng.

Trong **thiết kế tiến hóa (evolutionary design/architecture)**, nhóm giữ khả năng thay đổi theo phản hồi thực tế bằng cách xác định **một số ràng buộc chung có lý do**, trao quyền cho quyết định cục bộ và làm **những quyết định ảnh hưởng nhiều nhóm trở nên minh bạch, có người chịu trách nhiệm, có cơ chế kiểm chứng và có thể xem lại**.

Bài thuộc chương **Thiết kế tiến hóa** trong module **AGILE_DEVELOPMENT**. Mục tiêu của module là hiểu Agile và phát triển phần mềm thích ứng bằng phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Bài học kết nối những ý tưởng đó với **điều phối kiến trúc nhiều nhóm**: làm sao tránh thiết kế quá mức từ đầu mà vẫn không để mỗi nhóm vô tình phá khả năng thay đổi của cả sản phẩm.

Sau khi học, bạn có thể:

1. Giải thích sự khác nhau giữa **thiết kế tiến hóa**, thiết kế tự phát và kiến trúc cố định quá sớm.
2. Phân biệt **nguyên tắc kiến trúc, ràng buộc bắt buộc, quyết định cục bộ, quyết định liên nhóm** và ngoại lệ được kiểm soát.
3. Thiết kế cơ chế **quyền quyết định** để nhóm tự chủ mà không tạo hai nguồn thẩm quyền cạnh tranh.
4. Viết **Architecture Decision Record (ADR)** nêu bối cảnh, lựa chọn, đánh đổi, hệ quả, chủ sở hữu và điều kiện xem lại.
5. Xác định **ranh giới miền và quyền sở hữu dữ liệu**, quản lý API, sự kiện và thay đổi tương thích giữa nhiều nhóm.
6. Đưa ràng buộc thành **kiểm tra kiến trúc tự động (architectural fitness functions)** khi phù hợp.
7. Quản lý phụ thuộc, tích hợp và kiến trúc trong Scrum/Kanban/XP mà không biến thiết kế thành cổng duyệt chậm.
8. Sử dụng số liệu luồng, chất lượng, khả năng thay đổi và kết quả người dùng để biết cơ chế phối hợp có hiệu quả hay không.
9. Xử lý tình huống xung đột thực tế: thay đổi hợp đồng, dữ liệu riêng tư, phát hành độc lập và quyết định chưa có người chịu trách nhiệm.

## 1. Thiết kế tiến hóa khác gì “thiết kế xong rồi mới code”?

Kiến trúc phần mềm bao gồm những quyết định có ảnh hưởng lớn hoặc khó đảo ngược về **ranh giới trách nhiệm, dữ liệu, tương tác, phụ thuộc, triển khai, chất lượng và khả năng vận hành**.

Trong môi trường thay đổi, không thể biết trước chính xác mọi nhu cầu. Kiến trúc tiến hóa thừa nhận điều đó và hướng tới việc:

- **Ra quyết định đúng thời điểm**, khi đã có đủ thông tin cho quyết định cần thiết.
- **Giữ lựa chọn mở** ở nơi bất định cao, tránh khóa sản phẩm vào giả định chưa kiểm chứng.
- **Đặt ràng buộc chung vừa đủ** để các phần hoạt động cùng nhau.
- **Thử và kiểm chứng** bằng code, test, tích hợp, dữ liệu vận hành và phản hồi người dùng.
- **Refactor hoặc thay đổi kiến trúc từng bước**, thay vì tích lũy nợ rồi viết lại toàn hệ thống.
- **Ghi nhận đánh đổi**, để quyết định cũ có thể được xem lại khi bối cảnh thay đổi.

### 1.1. Ba cách làm cần phân biệt

| Cách tiếp cận | Mô tả | Rủi ro chính |
| --- | --- | --- |
| **Đóng băng thiết kế quá sớm** | Cố định mọi service, bảng dữ liệu, công nghệ và hợp đồng trước khi có phản hồi thực tế. | Đầu tư vào giả định sai, đổi hướng tốn kém. |
| **Thiết kế tự phát không ranh giới** | Mỗi nhóm tự tạo API/dữ liệu/phụ thuộc mà không có tiêu chuẩn và người quyết định rõ. | Tích hợp gãy, dữ liệu mâu thuẫn, thay đổi lan rộng. |
| **Thiết kế tiến hóa có điều phối** | Giữ ràng buộc ít nhưng quan trọng, trao quyền cục bộ, kiểm tra hợp đồng và xem lại quyết định dựa trên bằng chứng. | Vẫn có chi phí phối hợp; cần kỷ luật duy trì ranh giới và phản hồi. |

**Tiến hóa không có nghĩa kiến trúc ngẫu nhiên.** Nhóm vẫn chủ động thiết kế. Sự khác biệt là **thiết kế được kiểm chứng và điều chỉnh liên tục**, đồng thời những quyết định khó đảo ngược được xem xét cẩn thận hơn.

### 1.2. “Tối thiểu nhưng đủ” không phải “càng ít quy tắc càng tốt”

Một quy tắc chung về bảo mật hoặc tính tương thích API có thể giúp nhiều nhóm tránh sự cố. Ngược lại, quy tắc bắt tất cả nhóm dùng cùng một thư viện logging phiên bản cụ thể trong mọi hoàn cảnh có thể không đáng chi phí nếu nó không phục vụ mục tiêu kiểm soát thực sự.

Hãy hỏi: **Quy tắc này bảo vệ bất biến hoặc chất lượng nào? Nếu không có, nhóm khác hoặc người dùng có chịu rủi ro gì? Có cách ít ràng buộc hơn vẫn kiểm chứng được không?**

## 2. Vì sao kiến trúc trở thành vấn đề phối hợp nhiều nhóm?

Một nhóm có thể tự thay đổi nội bộ và biết ngay tác động. Khi có nhiều nhóm, một thay đổi cục bộ có thể ảnh hưởng những phần mà tác giả không trực tiếp sở hữu.

### Các nguồn ma sát thường gặp

| Nguồn ma sát | Ví dụ | Hệ quả |
| --- | --- | --- |
| **Dữ liệu dùng chung không có chủ sở hữu rõ** | Learning sửa trực tiếp bảng quiz_attempt do Assessment quản lý. | Thay schema làm gãy chức năng, khó xác định ai sửa lỗi. |
| **Hợp đồng API không được thống nhất** | Assessment đổi trường result thành outcome mà không có đường chuyển đổi. | Learning triển khai lỗi, cần release đồng thời. |
| **Quy tắc nghiệp vụ bị sao chép** | “Hoàn thành bài” được tính khác nhau trong hai service. | Người học thấy kết quả mâu thuẫn. |
| **Phụ thuộc đồng bộ chồng chéo** | Mỗi request trang chủ phải gọi tuần tự bốn service. | Độ trễ và rủi ro lan truyền sự cố tăng. |
| **Bảo mật không đồng nhất** | Một nhóm kiểm tra quyền theo lớp, nhóm khác chỉ dựa vào ID từ client. | Nguy cơ lộ tiến độ học hoặc kết quả cá nhân. |
| **Không có chuẩn quan sát vận hành** | Các service dùng cách ghi correlation ID khác nhau. | Sự cố liên nhóm khó truy vết. |
| **Thiếu quyết định chung** | Hai nhóm đều cho rằng nhóm kia chịu trách nhiệm đồng bộ dữ liệu. | Công việc bị chặn và tranh cãi kéo dài. |
| **Quá nhiều cổng phê duyệt** | Mọi thay đổi nhỏ phải chờ một hội đồng kiến trúc họp tháng một lần. | Lead time tăng và nhóm né cải tiến. |

Những vấn đề này không nhất thiết chứng minh nên dùng microservices hoặc một framework mới. Chúng cho thấy cần xác định **ranh giới quyết định và hợp đồng phối hợp** ngay cả khi sản phẩm là **modular monolith** hoặc các module trong cùng repository.

### “Tự chủ nhóm” và “tính nhất quán sản phẩm” là hai nhu cầu cùng tồn tại

Tự chủ có ích khi nhóm có thể nhanh chóng chọn cách thực hiện phù hợp. Tính nhất quán có ích khi các thay đổi cục bộ **không phá hợp đồng, dữ liệu, chất lượng và mục tiêu chung**. Kiến trúc tiến hóa tìm cách **tối đa hóa quyền quyết định cục bộ trong những ranh giới chung có thể kiểm chứng**.

## 3. Phân loại quyết định: cục bộ, liên nhóm và cấp tổ chức

Không phải mọi quyết định đều cần cùng số người tham gia. Một cơ chế quản trị hiệu quả phải tránh hai cực đoan: **mọi chuyện phải xin duyệt** hoặc **mọi chuyện ai thích thì làm**.

| Cấp quyết định | Ví dụ | Người tham gia phù hợp | Cần ghi lại gì? |
| --- | --- | --- | --- |
| **Cục bộ, dễ đảo ngược** | Đổi tên phương thức nội bộ, tách lớp, chọn cấu trúc thuật toán không đổi hợp đồng. | Developers sở hữu khu vực mã; review kỹ thuật khi phù hợp. | Commit/PR và kiểm thử thường đủ. |
| **Cục bộ nhưng có rủi ro chất lượng** | Đổi cách cache dữ liệu tiến độ trong module Learning. | Developers cùng người hiểu vận hành/bảo mật liên quan. | Giả định, ảnh hưởng, test và khả năng khôi phục. |
| **Liên nhóm hoặc thay hợp đồng** | Đổi sự kiện AssessmentAttemptCompleted; thay cơ chế gọi Identity. | Nhóm sở hữu, các nhóm tiêu thụ, người hiểu bảo mật/vận hành và PO khi ảnh hưởng giá trị. | ADR/RFC hoặc decision log, kế hoạch tương thích và kiểm chứng. |
| **Khó đảo ngược / phạm vi sản phẩm** | Chuyển phân quyền sang giải pháp dùng chung, thay mô hình sở hữu dữ liệu, tách một service mới. | Người chịu trách nhiệm kiến trúc liên quan, các nhóm bị ảnh hưởng và thẩm quyền tổ chức cần thiết. | Đánh đổi, rủi ro, thử nghiệm, điều kiện quay lại, chi phí vận hành. |
| **Nghĩa vụ cấp tổ chức** | Chính sách mã hóa, phân loại dữ liệu, quyền truy cập, kiểm toán hoặc hợp đồng. | Chức năng có thẩm quyền về bảo mật/tuân thủ/pháp lý và nhóm triển khai. | Tiêu chuẩn bắt buộc, bằng chứng và ngoại lệ hợp lệ. |

**Độ khó đảo ngược** thường quan trọng không kém **mức ảnh hưởng**. Đổi tên biến có thể đảo ngược dễ; chuyển dữ liệu hàng triệu học viên và đổi hợp đồng với đối tác có thể đòi hỏi phối hợp dài hơn.

### Phân loại bằng bốn câu hỏi

1. **Ai sẽ phải thay đổi mã hoặc cách làm** nếu quyết định này đổi?
2. **Có làm thay đổi hợp đồng** mà nhóm khác hoặc người dùng đang phụ thuộc?
3. **Có ảnh hưởng dữ liệu, bảo mật, độ tin cậy, pháp lý hoặc chi phí vận hành** không?
4. **Có thể đảo ngược nhanh và an toàn** nếu giả định sai không?

Nếu cả bốn câu trả lời cho thấy phạm vi nhỏ, không cần một hội đồng duyệt. Nếu tác động liên nhóm hoặc khó đảo ngược, cần tăng mức tham vấn và bằng chứng, **không nhất thiết tăng số cuộc họp**.

## 4. Ràng buộc kiến trúc: giữ bất biến, không khóa mọi lựa chọn

**Architectural constraints/guardrails** là những giới hạn hoặc nguyên tắc đủ rõ để các nhóm biết điều gì **bắt buộc giữ**, điều gì có thể tự chọn và dấu hiệu nào cho thấy kiến trúc đang lệch mục tiêu.

Không phải ràng buộc nào cũng có mức bắt buộc giống nhau. Nên tách:

- **Invariant/bất biến cần bảo vệ:** nếu vi phạm, sản phẩm sai hoặc không an toàn. Ví dụ: không cho người học đọc kết quả của người khác trái quyền.
- **Tiêu chuẩn tổ chức bắt buộc:** bảo mật, lưu vết, chính sách dữ liệu, chuẩn tương thích được phê duyệt.
- **Guardrail kỹ thuật:** quy tắc ranh giới, giao tiếp, quan sát hoặc quản lý phụ thuộc được chọn để giảm rủi ro.
- **Khuyến nghị mặc định (default):** hướng dẫn nên theo trong trường hợp thông thường, có đường ngoại lệ minh bạch.
- **Quyết định cục bộ:** chi tiết triển khai nhóm tự chọn trong những giới hạn trên.

### Bảng ví dụ guardrails cho nền tảng học

| Mã | Ràng buộc | Lý do | Cách kiểm chứng | Quyền ngoại lệ |
| --- | --- | --- | --- | --- |
| **G1** | Mỗi dữ liệu nghiệp vụ quan trọng có **nhóm chịu trách nhiệm ghi** và hợp đồng truy cập rõ. | Tránh sửa dữ liệu chéo và bất nhất. | Sơ đồ sở hữu, quyền DB, dependency tests. | Cần tham vấn các nhóm sở hữu/tiêu thụ và ghi quyết định. |
| **G2** | Không chấp nhận request chỉ dựa vào một ID do client gửi; phải kiểm tra **xác thực và quyền** ở ranh giới tin cậy. | Tránh truy cập dữ liệu trái phép. | Test phân quyền, rà soát bảo mật. | Không tự cấp ngoại lệ làm suy yếu bảo mật bắt buộc. |
| **G3** | Thay đổi hợp đồng API/event ảnh hưởng consumer phải có **đường tương thích hoặc kế hoạch chuyển đổi**. | Tránh buộc phát hành đồng thời và gãy tích hợp. | Contract tests, schema checks, môi trường thử. | Quyết định liên nhóm có kế hoạch và chủ sở hữu. |
| **G4** | Thay đổi quan trọng phát ra **correlation/trace context** theo quy ước dùng chung. | Điều tra sự cố liên nhóm. | Test tích hợp, quan sát log/trace. | Chỉ khi có phương án quan sát tương đương. |
| **G5** | Increment phải đạt **Definition of Done** và điều kiện an toàn áp dụng. | Không báo Done khi sản phẩm chưa dùng được. | CI, test, review, bằng chứng DoD. | Không coi hạ chuẩn DoD ngầm là ngoại lệ hợp lệ. |
| **G6** | Những quyết định thay đổi ranh giới sở hữu hoặc hợp đồng liên nhóm cần **ADR có người quyết định và mốc xem lại**. | Dễ tìm lý do và tránh hai nguồn sự thật. | Quy trình ADR nhẹ, liên kết PR/issue. | Có cơ chế xử lý khẩn, bổ sung ADR sau khi ổn định. |

Đây là **một bộ ví dụ**, không phải tiêu chuẩn bắt buộc cho mọi hệ thống. Tổ chức cần xác nhận ràng buộc dựa trên loại sản phẩm, quyền hạn và mức rủi ro.

### Mỗi guardrail nên có năm đặc điểm

1. **Có mục đích:** bảo vệ một chất lượng hoặc bất biến đã giải thích.
2. **Có phạm vi:** áp dụng cho hệ thống/nhóm/dữ liệu và trường hợp nào.
3. **Có cách kiểm chứng:** kiểm tra tự động, test, review hoặc bằng chứng phù hợp.
4. **Có chủ sở hữu và lối xử lý ngoại lệ:** ai làm rõ khi có xung đột.
5. **Có thời điểm xem lại:** khi mục tiêu hoặc bối cảnh thay đổi, kiểm tra quy tắc còn hữu ích không.

Một quy tắc không được giải thích và không thể kiểm chứng dễ trở thành “kiến trúc theo lời đồn” hoặc công cụ tranh luận chủ quan.

## 5. Ranh giới miền và dữ liệu: quyết định cần rõ từ đầu

Một điểm khó trong kiến trúc nhiều nhóm là phân chia **ranh giới nghiệp vụ (domain boundaries)**, chứ không chỉ chia repository hoặc cụm máy chủ.

Với nền tảng học, có thể cân nhắc ba **bounded contexts**:

- **Identity & Access:** xác thực, danh tính, quyền và dữ liệu truy cập theo chính sách.
- **Learning Progress:** nội dung học, vị trí video, trạng thái tiến độ theo người học.
- **Assessment:** câu hỏi, lần làm bài, kết quả chấm và các quy tắc đánh giá.

Ranh giới này chỉ là **ứng viên thiết kế**. Trong sản phẩm thực, nên xác nhận với người hiểu nghiệp vụ: “Hoàn thành bài học” và “Đạt bài kiểm tra” có cùng chủ sở hữu quyết định hay không?

### 5.1. Sơ đồ sở hữu và giao tiếp minh họa

~~~mermaid
flowchart LR
    U["Người học"] --> APP["Ứng dụng web/mobile"]
    APP --> LEARN["Learning Progress\nSở hữu tiến độ"]
    APP --> TEST["Assessment\nSở hữu kết quả kiểm tra"]
    APP --> ID["Identity & Access\nSở hữu danh tính/quyền"]
    LEARN -->|"Kiểm tra quyền theo hợp đồng"| ID
    TEST -->|"Kiểm tra quyền theo hợp đồng"| ID
    TEST -->|"AssessmentAttemptCompleted v1"| EVT["Event channel"]
    EVT -->|"Consumer idempotent"| LEARN
    LEARN --> LDB[("Progress data")]
    TEST --> TDB[("Assessment data")]
    ID --> IDB[("Identity data")]
~~~

Sơ đồ chỉ minh họa một khả năng tích hợp; **không khẳng định mọi hệ thống phải dùng ba microservices và message broker**. Với một **modular monolith**, cùng các nguyên tắc sở hữu và ranh giới có thể được thực hiện bằng module, interface và kiểm thử kiến trúc trong một tiến trình.

### 5.2. “Sở hữu dữ liệu” không phải “cấm người khác sử dụng”

Nếu Assessment sở hữu kết quả chấm, Learning vẫn có thể **đọc thông tin cần thiết thông qua hợp đồng phù hợp**. Nhưng Learning không nên tự ghi vào bảng kết quả của Assessment hoặc lệ thuộc vào cấu trúc lưu trữ nội bộ.

Một nguyên tắc thực hành:

> Nhóm sở hữu quy tắc và dữ liệu cung cấp hợp đồng được quản lý; nhóm tiêu thụ nêu nhu cầu và kiểm thử hợp đồng; cả hai làm rõ ý nghĩa dữ liệu và mức cập nhật cần thiết.

Không nên áp dụng “mỗi service một database vật lý” như luật tuyệt đối khi kiến trúc chưa cần microservices. Điều nên giữ là **ranh giới quyền ghi và trách nhiệm thay đổi được kiểm soát**.

### 5.3. Ai quyết định “đã hoàn thành bài học”?

Giả sử một bài được xem là hoàn thành nếu người học đã xem đủ nội dung và vượt bài kiểm tra:

- Assessment biết **kết quả lần làm bài**.
- Learning biết **tiến độ xem** và trạng thái khóa học.
- Product Owner/đơn vị nghiệp vụ cần làm rõ **quy tắc hoàn thành**.
- Nhóm sở hữu quy tắc hoàn thành phải được xác định để tránh **hai định nghĩa khác nhau** trong các service.

Nếu không có chủ sở hữu quy tắc, cả Learning và Assessment có thể tự tính trạng thái riêng. Đây là **xung đột kiến trúc và nghiệp vụ**, không chỉ là lỗi kỹ thuật.

## 6. Hợp đồng API và sự kiện: phối hợp bằng điều kiện kiểm chứng được

Các nhóm không cần thống nhất mọi chi tiết triển khai, nhưng phải thống nhất **cái được trao đổi và ý nghĩa của nó**.

Một hợp đồng tốt bao gồm không chỉ tên endpoint/trường dữ liệu mà còn:

- Ngữ nghĩa nghiệp vụ của dữ liệu và trạng thái.
- Yêu cầu xác thực, phân quyền và mức bảo mật.
- Điều kiện thành công, lỗi, timeout và retry.
- Kỳ vọng tương thích khi producer/consumer nâng phiên bản khác thời điểm.
- Tính nhất quán: dữ liệu có sẵn ngay hay chấp nhận độ trễ?
- Tính lặp lại (*idempotency*), thứ tự và cơ chế xử lý bản tin trùng.
- Ai sở hữu hợp đồng, ai là consumer và cách thông báo thay đổi.

### 6.1. Ví dụ hợp đồng sự kiện

Giả sử Assessment phát sự kiện khi một lần làm bài hoàn tất:

~~~json
{
  "eventId": "evt-2026-00123",
  "eventType": "AssessmentAttemptCompleted",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T09:30:00Z",
  "attemptId": "attempt-481",
  "learnerId": "learner-27",
  "courseId": "java-intro",
  "assessmentId": "quiz-05",
  "result": "PASSED"
}
~~~

Đây là **dữ liệu minh họa**. Các ID chỉ là giả định, không phải thông tin người dùng thật. Không nên đưa email, tên đầy đủ hoặc dữ liệu nhạy cảm vào sự kiện nếu không cần thiết; phải tuân thủ chính sách riêng tư và quản lý truy cập của hệ thống.

**Ý nghĩa cần chốt trước:** “PASSED” có phải trạng thái cuối cùng của một attempt? Nếu chấm lại sau phúc khảo, sự kiện nào biểu diễn điều chỉnh? Khi nào Learning có thể coi kết quả là hợp lệ để cập nhật tiến độ? Sự kiện được phát sau commit hay có thể xảy ra khi giao dịch còn thất bại?

Nếu các nhóm chỉ đồng ý tên trường mà chưa thống nhất **ngữ nghĩa và vòng đời**, contract test có thể Green nhưng trải nghiệm người học vẫn sai.

### 6.2. Thay đổi hợp đồng theo hướng tương thích

Ví dụ cần bổ sung trường **gradingPolicyVersion**. Có thể:

1. Giữ các trường cũ và bổ sung trường mới theo quy tắc tương thích đã thống nhất.
2. Làm rõ trường mới là **tùy chọn hay bắt buộc**, giá trị mặc định nào được chấp nhận.
3. Cập nhật producer/consumer theo thứ tự giúp các phiên bản cùng tồn tại.
4. Chạy schema/contract tests và thử với một consumer đại diện.
5. Quan sát lỗi parse, schema mismatch và trạng thái nghiệp vụ sau triển khai.
6. Chỉ loại bỏ hợp đồng cũ khi có bằng chứng consumer đã chuyển an toàn.

**Không nên mặc định thêm trường luôn tương thích.** Một consumer không chấp nhận trường lạ hoặc một thay đổi ý nghĩa trường cũ vẫn có thể bị gãy; chính sách tương thích phải dựa trên định dạng và cách consumer xử lý thực tế.

### 6.3. Consumer-driven contract tests

Khi một consumer dựa vào một subset API/sự kiện, **consumer-driven contract tests** có thể ghi rõ những kỳ vọng ấy và kiểm tra producer còn đáp ứng sau thay đổi. Nhưng loại kiểm thử này không thay thế:

- Kiểm thử nghiệp vụ xuyên nhiều thành phần.
- Kiểm thử phân quyền và dữ liệu nhạy cảm.
- Kiểm thử hiệu năng, độ tin cậy và vận hành.
- Thảo luận về ý nghĩa của các trạng thái nghiệp vụ.

**Hợp đồng là ranh giới phối hợp, không phải bằng chứng duy nhất rằng toàn bộ hành trình người dùng hoạt động.**

## 7. Đồng bộ hay bất đồng bộ? Quyết định theo đặc tính cần giữ

Một quyết định liên nhóm thường gặp: Learning lấy kết quả bài kiểm tra bằng **API đồng bộ** hay **nhận sự kiện bất đồng bộ**?

| Tiêu chí | Gọi đồng bộ | Giao tiếp qua sự kiện |
| --- | --- | --- |
| **Thời điểm có dữ liệu** | Có thể đọc kết quả ngay khi service đáp ứng. | Consumer có thể nhận sau một độ trễ. |
| **Phụ thuộc vận hành** | Phụ thuộc vào khả năng đáp ứng khi gọi. | Giảm phụ thuộc thời gian gọi nhưng thêm broker/consumer và backlog. |
| **Xử lý lỗi** | Timeout, retry, circuit breaker; phải tránh gọi dây chuyền vô hạn. | Retry, bản tin trùng, thứ tự, dead-letter, replay và giám sát độ trễ. |
| **Mô hình dữ liệu** | Consumer dùng response của producer. | Consumer có thể duy trì projection riêng từ sự kiện. |
| **Độ phức tạp** | Thường đơn giản hơn nếu nhu cầu đọc nhỏ và ít phụ thuộc. | Có thể phù hợp khi nhiều consumer hoặc cần tách nhịp, nhưng vận hành phức tạp hơn. |
| **Phù hợp khi** | Cần kết quả ngay theo nghĩa nghiệp vụ và dịch vụ đủ tin cậy. | Chấp nhận nhất quán cuối cùng và cần phản ứng nhiều nơi theo sự kiện. |

Không có lựa chọn đúng cho mọi trường hợp. Nếu người học vừa nộp bài và **cần thấy kết quả ngay**, Assessment có thể trả kết quả trực tiếp cho luồng nộp bài. Learning cập nhật trạng thái tổng hợp từ sự kiện sau đó, nếu sản phẩm **chấp nhận độ trễ** và giao diện diễn đạt trạng thái phù hợp.

### 7.1. Bất đồng bộ không cho phép “mất dữ liệu rồi tự sửa sau”

Với sự kiện quan trọng, cần làm rõ:

- Gửi sự kiện khi nào so với commit dữ liệu?
- Có thể gửi trùng không?
- Consumer có xử lý lặp an toàn không?
- Khi sự kiện đến sai thứ tự, trạng thái tổng hợp được xác định thế nào?
- Nếu consumer ngừng hoạt động, backlog và retry được quan sát ra sao?
- Khi xử lý thất bại nhiều lần, bản tin đi đâu và ai chịu trách nhiệm?
- Có cơ chế đối soát khi dữ liệu hai bên khác nhau không?

Ví dụ, trong hệ thống có giao nhận bản tin **at-least-once**, consumer nên thiết kế **idempotent**. Không nên hứa “đúng một lần trong mọi điều kiện” chỉ vì framework messaging có một tùy chọn tên gần giống.

### 7.2. Quy tắc ứng dụng minh họa

Learning chỉ ghi nhận một lần hoàn tất mới nếu **eventId** chưa được xử lý hoặc trạng thái mới hợp lệ theo phiên bản/kết quả nghiệp vụ. Nếu có sự kiện sửa kết quả, nhóm cần một **quy tắc rõ về phiên bản và thứ tự** thay vì đơn giản “bản tin tới sau thì luôn ghi đè”.

Tối thiểu, cần một **bộ kiểm thử hợp đồng và tích hợp** cho duplicate, out-of-order, retry và quyền xử lý sự kiện.

## 8. Dùng ADR để biến tranh luận thành quyết định có thể xem lại

**Architecture Decision Record (ADR)** là bản ghi ngắn cho một quyết định kiến trúc quan trọng. Nó giúp người đến sau biết **vì sao** chọn giải pháp, **đã cân nhắc những phương án nào**, **đánh đổi gì**, và **khi nào nên xem lại**.

ADR không phải tài liệu đặc tả toàn bộ hệ thống. Nó cũng không nhất thiết là biểu mẫu cần được một hội đồng phê duyệt trước mọi commit.

### 8.1. Những thành phần thiết yếu

| Thành phần | Nội dung |
| --- | --- |
| **Mã và tiêu đề** | Một quyết định cụ thể, ví dụ ADR-007: Tích hợp kết quả kiểm tra qua sự kiện. |
| **Trạng thái** | Proposed, Accepted, Deprecated/Superseded hoặc tương đương. |
| **Bối cảnh** | Vấn đề, yêu cầu, ràng buộc, dữ liệu hiện có và bất định. |
| **Yếu tố quyết định** | Bảo mật, coupling, latency, availability, năng lực vận hành, chi phí chuyển đổi. |
| **Lựa chọn đã xem** | Ít nhất những giải pháp hợp lý, gồm giữ hiện trạng nếu phù hợp. |
| **Quyết định** | Phương án và phạm vi áp dụng, điều không nằm trong quyết định. |
| **Hệ quả/đánh đổi** | Điểm lợi, chi phí, rủi ro và công việc tiếp theo. |
| **Người chịu trách nhiệm** | Người/chủ thể có thẩm quyền chốt, nhóm bị tác động và người cần tham vấn. |
| **Kiểm chứng/xem lại** | Fitness functions, thử nghiệm, chỉ số, mốc hoặc sự kiện kích hoạt xem lại. |

### 8.2. Phân biệt RFC với ADR

- **RFC/proposal:** tài liệu mời thảo luận, trình bày phương án, thu phản hồi trước khi ra quyết định.
- **ADR:** bản ghi quyết định đã được chốt trong phạm vi thẩm quyền, cùng lý do và hệ quả.

Không nhất thiết phải có hai tài liệu. Một ADR có thể đi qua trạng thái **Proposed → Accepted**, miễn là người đọc phân biệt rõ **đề xuất** với **quyết định có hiệu lực**.

### 8.3. Giữ lịch sử thay vì viết lại quá khứ

Nếu ADR-007 không còn phù hợp vì yêu cầu thay đổi, nên tạo ADR mới **supersedes ADR-007** hoặc ghi rõ thay thế. Điều này giữ được **lý do lịch sử** và giúp giải thích vì sao code cũ tồn tại.

Sửa một ADR cũ để nó có vẻ “luôn đúng” làm mất khả năng học từ quyết định và bối cảnh trước đó.

## 9. ADR ví dụ: hợp đồng kết quả bài kiểm tra

Dưới đây là một ADR học tập, không phải quyết định thật của tổ chức.

~~~text
ADR-007: Chuyển kết quả hoàn tất bài kiểm tra từ Assessment sang Learning

Trạng thái:
  ACCEPTED (minh họa)

Bối cảnh:
  Learning cần biết một lần làm bài đã hoàn tất để cập nhật tiến độ.
  Hiện tại Learning đang đọc trực tiếp dữ liệu nội bộ của Assessment.
  Mỗi lần Assessment thay schema, Learning có nguy cơ lỗi tích hợp.
  Nhu cầu: cập nhật tiến độ với độ trễ chấp nhận được; bảo vệ dữ liệu học viên.

Lựa chọn:
  A. Giữ truy vấn trực tiếp bảng Assessment.
  B. Learning gọi API Assessment đồng bộ mỗi khi cần kết quả.
  C. Assessment phát sự kiện AssessmentAttemptCompleted theo hợp đồng.

Quyết định:
  Chọn C cho cập nhật trạng thái tổng hợp tiến độ.
  Luồng nộp bài vẫn nhận kết quả trực tiếp từ Assessment khi cần phản hồi ngay.
  Learning không ghi hoặc truy vấn cấu trúc lưu trữ nội bộ của Assessment.

Lý do:
  Giảm phụ thuộc vào schema nội bộ và tách nhịp cập nhật tổng hợp.
  Có thể thêm consumer mới không đổi giao dịch nộp bài trực tiếp.

Hệ quả:
  Cần broker hoặc hạ tầng tương đương, retry, idempotency, tracing,
  theo dõi độ trễ và đối soát khi dữ liệu sai lệch.
  Giao diện phải diễn đạt trạng thái "đang cập nhật" nếu chưa có projection.

Bảo mật:
  Không gửi dữ liệu nhận dạng vượt nhu cầu; kiểm soát quyền publish/consume.
  Learning phải kiểm tra quyền người dùng khi hiển thị tiến độ.

Trách nhiệm:
  Assessment sở hữu hợp đồng publish và dữ liệu lần làm bài.
  Learning sở hữu projection tiến độ và idempotent consumer.
  Platform/Operations hỗ trợ độ tin cậy và quan sát sự kiện.
  Các nhóm bị ảnh hưởng đã tham vấn trước khi chốt.

Kiểm chứng:
  Contract tests v1; tests duplicate/out-of-order/retry;
  kiểm chứng luồng học viên; theo dõi độ trễ event và dữ liệu lệch.

Điều kiện xem lại:
  Độ trễ không đáp ứng trải nghiệm, chi phí vận hành vượt khả năng,
  hoặc nhiều use case mới cần nhất quán mạnh hơn.
~~~

### Vì sao không chọn A hoặc B?

**A – đọc database chéo:** có thể nhanh về ngắn hạn nhưng làm Learning phụ thuộc chi tiết lưu trữ Assessment và khó giữ quyền sở hữu dữ liệu. Nếu tổ chức có mô hình dữ liệu dùng chung có kiểm soát, cần đánh giá trên thực tế, không coi mọi shared database là sai tuyệt đối.

**B – API đồng bộ:** có thể đơn giản hơn và phù hợp khi cần dữ liệu mới nhất, nhưng làm Learning phụ thuộc vào availability/latency của Assessment tại thời điểm gọi. Trong ví dụ, trạng thái tiến độ tổng hợp **có thể cập nhật trễ** nên C được chọn.

**C – sự kiện:** giảm một loại coupling nhưng thêm độ phức tạp vận hành; quyết định phải thừa nhận và có người chịu trách nhiệm cho độ phức tạp đó.

**ADR tốt không chỉ mô tả phương án thắng.** Nó bảo vệ **lý do chọn, điều kiện đúng và dấu hiệu phương án không còn phù hợp**.

## 10. Quyền quyết định: tránh cả “kiến trúc sư ra lệnh” lẫn “không ai quyết”

Mô hình điều phối cần nêu **ai được tự quyết**, **ai phải được tham vấn** và **ai chịu trách nhiệm cuối cùng khi quyết định ảnh hưởng nhiều nhóm**.

### 10.1. Một mô hình phân quyền minh họa

| Quyết định | Đầu mối quyết định/giải trình | Cần tham vấn | Bằng chứng phù hợp |
| --- | --- | --- | --- |
| Refactor nội bộ không đổi hợp đồng | Developers của nhóm sở hữu | Reviewer/chuyên gia kỹ thuật nếu cần | Test, PR, diff. |
| Chọn cấu trúc module/implementation nội bộ | Developers của nhóm sở hữu | Những người vận hành hoặc người hiểu rủi ro | Kiểm thử, kiến trúc cục bộ. |
| Thay hợp đồng API có consumer | Nhóm sở hữu hợp đồng theo cơ chế đã thống nhất | Consumer, bảo mật, vận hành khi liên quan | ADR/contract tests/kế hoạch rollout. |
| Đổi ranh giới dữ liệu giữa hai nhóm | Đầu mối quyết định liên nhóm được xác định trước | Hai nhóm, người hiểu nghiệp vụ, bảo mật, vận hành | ADR, phương án migration, test. |
| Ban hành chuẩn bảo mật bắt buộc | Người/bộ phận có thẩm quyền của tổ chức | Các nhóm chịu tác động | Tiêu chuẩn, cơ chế kiểm chứng và ngoại lệ. |
| Đổi ưu tiên Product Backlog trong Scrum | **Product Owner** | Developers, các bên liên quan, người cung cấp ràng buộc kiến trúc | Giá trị, rủi ro, phụ thuộc, forecast. |
| Chọn công việc và kế hoạch Sprint trong Scrum | **Developers** trong khuôn khổ Sprint Planning và Sprint Goal | PO và các chuyên gia liên quan | Sprint Backlog, DoD, năng lực thực tế. |
| Cải tiến hiệu quả Scrum và trở ngại liên nhóm | **Scrum Master** hỗ trợ hiệu quả, làm cho trở ngại được tháo gỡ | Developers, PO, người có quyền xử lý phụ thuộc | Quan sát, hành động cải tiến, phản hồi. |

Bảng không phải RACI bắt buộc của Scrum. Các quyền về **hợp đồng, ngân sách, tuân thủ, kiến trúc liên tổ chức** do tổ chức phân định; không nên tự gán cho một chức danh Scrum nếu không có thẩm quyền.

### 10.2. Tham vấn không đồng nghĩa phải đạt đồng thuận tuyệt đối

Một cách phù hợp ở nhiều nhóm là **quy trình xin ý kiến (advice process)**:

1. Người đề xuất mô tả vấn đề, giải pháp và tác động.
2. Xin ý kiến **những người chịu ảnh hưởng** và **chuyên gia liên quan**.
3. Ghi ý kiến quan trọng, đặc biệt là rủi ro và lựa chọn thay thế.
4. Người có thẩm quyền ra quyết định theo phạm vi đã định.
5. Công bố quyết định, bằng chứng và mốc xem lại.

Như vậy, các nhóm có tiếng nói mà không phải chờ **mọi người đều thích** cùng một giải pháp. Những yêu cầu pháp lý hoặc bảo mật bắt buộc không được biến thành ý kiến tùy chọn.

### 10.3. Nếu bất đồng không được giải quyết?

Một cơ chế chuyển cấp nên rõ:

- Bất đồng **về nghiệp vụ/giá trị:** quay về người có trách nhiệm sản phẩm và các bên có thẩm quyền.
- Bất đồng **về hợp đồng tích hợp:** nhóm sở hữu và consumer đối chiếu yêu cầu kiểm chứng; nếu không đủ quyền, chuyển tới đầu mối kiến trúc liên nhóm.
- Bất đồng **về bảo mật/tuân thủ:** chuyên gia hoặc bộ phận có thẩm quyền xác định điều kiện áp dụng.
- Bất đồng **về chi phí/năng lực:** người chịu trách nhiệm nguồn lực và PO xem lựa chọn phạm vi.
- Bất đồng **về cách triển khai nội bộ:** Developers chịu trách nhiệm lựa chọn trong các ràng buộc chung.

Không nên sử dụng “kiến trúc sư có tiếng nói cuối” cho mọi trường hợp mà **không làm rõ loại quyết định và thẩm quyền**.

## 11. Architectural fitness functions: biến nguyên tắc thành phản hồi

**Architectural fitness function** là một phép kiểm tra hoặc số đo giúp đánh giá kiến trúc còn đáp ứng một đặc tính mong muốn khi hệ thống thay đổi hay không. Nó có thể được thực hiện bằng **test, phân tích tĩnh, kiểm tra contract, đo vận hành hoặc review có tiêu chí rõ**.

Mục tiêu không phải tự động hóa mọi quyết định kiến trúc, mà là **đưa phản hồi sớm vào đường thay đổi của nhóm**.

### 11.1. Từ nguyên tắc đến phép kiểm tra

| Mục tiêu kiến trúc | Tín hiệu/fitness function | Nhịp kiểm tra |
| --- | --- | --- |
| **Không phụ thuộc vào persistence của module khác** | Kiểm tra dependency package/module ở CI; test kiến trúc. | Mỗi PR/merge. |
| **Giữ hợp đồng API/event tương thích** | Schema compatibility, consumer-driven contract tests. | Khi producer/consumer thay hợp đồng. |
| **Không truy cập dữ liệu trái quyền** | Automated authorization tests, negative tests và rà soát bảo mật. | CI và kiểm thử tích hợp/phát hành. |
| **Người học có thể thực hiện hành trình đầu cuối** | End-to-end acceptance test trên lát giá trị. | Khi tích hợp các phần liên quan. |
| **Điều tra được sự cố xuyên nhóm** | Trace/correlation propagation tests và kiểm tra độ phủ telemetry. | CI và vận hành. |
| **Độ trễ và tỷ lệ lỗi đáp ứng mục tiêu** | SLI/SLO theo hành trình quan trọng, kiểm tra tải và quan sát. | Liên tục hoặc theo release. |
| **Các lần cập nhật bất đồng bộ không sai tiến độ** | Duplicate/out-of-order/replay tests và đối soát dữ liệu. | CI, test môi trường và vận hành. |
| **Triển khai độc lập không phá consumer** | Test ma trận phiên bản producer/consumer và rollout tương thích. | Trước và trong chuyển đổi. |

**Không nên chọn quá nhiều fitness functions từ đầu.** Bắt đầu ở những thuộc tính có rủi ro đáng kể và dễ bị thay đổi làm hỏng, sau đó mở rộng khi có bằng chứng.

### 11.2. Ví dụ Java với ArchUnit: bảo vệ ranh giới module

Giả sử một modular monolith có các package **learning** và **assessment**. Nhóm muốn module Learning không phụ thuộc trực tiếp vào lớp persistence nội bộ của Assessment.

Ví dụ với **ArchUnit JUnit 5** (cần cấu hình dependency phù hợp trong dự án):

~~~java
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

@AnalyzeClasses(packages = "com.example.learningplatform")
class ArchitectureBoundaryTest {

    @ArchTest
    static final ArchRule learningMustNotDependOnAssessmentPersistence =
            noClasses()
                    .that().resideInAPackage("..learning..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..assessment.persistence..");
}
~~~

Nếu Developers vô tình import một repository nội bộ của Assessment vào Learning, kiểm tra có thể báo lỗi trong CI. Nhóm không cần chờ cuộc họp kiến trúc cuối Sprint mới phát hiện lệch ranh giới.

**Giới hạn:** rule trên kiểm tra **phụ thuộc ở cấp class/package**, không tự phát hiện truy vấn SQL trực tiếp qua chuỗi, reflection, data access bên ngoài hoặc ý nghĩa nghiệp vụ sai. Cần bổ sung cách kiểm chứng phù hợp cho những rủi ro đó.

### 11.3. Fitness function phải đo thuộc tính, không chỉ tên công nghệ

Một quy tắc “tất cả team phải dùng công cụ X” chỉ hữu ích nếu X bảo vệ yêu cầu có thật. Thường tốt hơn là diễn đạt:

> “Dịch vụ cần phát được trace context theo định dạng thống nhất để truy vết request giữa các nhóm.”

Sau đó xác định test/telemetry, còn thư viện thực hiện có thể được lựa chọn trong phạm vi tương thích.

**Guardrail định hướng kết quả** thường dễ tiến hóa hơn **quy tắc khóa triển khai** mà không có lý do.

## 12. Quy trình hợp đồng và kiểm thử tích hợp nhiều nhóm

Để phối hợp kiến trúc mà không trở lại “big design up front”, nhóm có thể thiết lập một nhịp kỹ thuật ngắn:

1. **Trước khi xây sâu:** thống nhất phạm vi lát đầu cuối, chủ sở hữu dữ liệu và hợp đồng tối thiểu.
2. **Trong phát triển:** producer và consumer phát triển với schema/API contract được quản lý, có test hai phía.
3. **Tích hợp sớm:** ghép một luồng thực xuyên module/service, thử trường hợp thành công và thất bại.
4. **Trong CI:** chạy fitness functions, contract tests, kiểm thử chất lượng và bảo mật phù hợp.
5. **Trước release:** xác minh phiên bản tương thích, dữ liệu, quan sát và khả năng khôi phục.
6. **Sau release:** theo dõi error, latency, lag, hành vi người dùng; cập nhật quyết định nếu giả định không đúng.

### Các cấp kiểm tra bổ trợ nhau

| Cấp kiểm tra | Phát hiện tốt điều gì | Không thể thay thế điều gì |
| --- | --- | --- |
| **Unit tests** | Quy tắc và trường hợp biên ở một module. | Tích hợp thật và hành vi đa dịch vụ. |
| **Architecture/dependency tests** | Vi phạm ranh giới import/module. | Đúng đắn nghiệp vụ và bảo mật runtime. |
| **Contract/schema tests** | Producer/consumer thay đổi hợp đồng không tương thích. | Luồng end-to-end có đúng kết quả người dùng không. |
| **Integration tests** | Giao tiếp thật, dữ liệu, giao dịch, lỗi giữa thành phần. | Mọi tình huống production và giá trị người dùng. |
| **End-to-end acceptance tests** | Hành trình người dùng qua nhiều phần. | Kiểm tra hiệu năng sâu và mọi phân nhánh nội bộ. |
| **Security/resilience tests** | Truy cập trái quyền, timeout, retry, khả năng chịu lỗi. | Đánh giá giá trị sản phẩm với người dùng. |
| **Observability/SLIs** | Độ trễ, lỗi, backlog, hành vi vận hành. | Phán quyết mọi thiết kế tốt/xấu chỉ từ một chỉ số. |

Không nên cố chuyển mọi kiểm thử thành **end-to-end UI tests** vì chúng thường chậm và có thể không ổn định. Hãy chọn nhiều lớp kiểm tra hỗ trợ nhau để đạt **phản hồi sớm và đủ tin cậy**.

## 13. Thay đổi kiến trúc theo từng bước: giữ đường quay lại

Một ràng buộc hoặc quyết định kiến trúc có thể tiến hóa khi bối cảnh thay đổi. Vấn đề là **thay đổi mà không phá hợp đồng đang dùng**.

### 13.1. Expand–migrate–contract cho dữ liệu và API

Giả sử Learning hiện đọc trực tiếp bảng Assessment, cần chuyển sang sự kiện:

| Giai đoạn | Việc làm | Điều kiện an toàn |
| --- | --- | --- |
| **Expand** | Assessment cung cấp hợp đồng event mới, vẫn duy trì cách cũ trong giai đoạn chuyển đổi. | Consumer cũ không gãy, kiểm soát quyền. |
| **Migrate** | Learning xây consumer idempotent và projection; đối chiếu với dữ liệu hiện tại. | Đủ test duplicate/retry, giám sát lag, sai lệch. |
| **Observe** | Chạy thử có kiểm soát, so trạng thái giữa đường cũ và mới. | Không lộ dữ liệu, có ngưỡng dừng và đầu mối xử lý. |
| **Switch** | Chuyển luồng sử dụng sang projection mới theo điều kiện đã xác định. | Có kênh rollback/khôi phục và kiểm tra hành trình. |
| **Contract** | Bỏ quyền đọc trực tiếp bảng cũ sau khi xác nhận không còn phụ thuộc. | Consumer đã chuyển, không còn job/phiên bản cần đường cũ. |

Không nên đổi schema cũ, logic cập nhật và hạ tầng phát sự kiện **trong một lần phát hành khó hoàn tác** nếu có thể tách thành các bước tương thích nhỏ hơn.

### 13.2. Branch by abstraction

Với thay đổi nội bộ lớn, có thể tạo **một hợp đồng trừu tượng ổn định**, rồi chuyển từng đường gọi từ triển khai cũ sang mới:

~~~mermaid
flowchart LR
    APP["Luồng sản phẩm"] --> PORT["ProgressReadPort\nHợp đồng ổn định"]
    PORT --> OLD["OldProgressReader"]
    PORT --> NEW["EventProjectionReader"]
    OLD --> OLDDATA[("Dữ liệu cũ")]
    NEW --> NEWDATA[("Projection mới")]
~~~

Sơ đồ mô tả **giai đoạn song song**; trong triển khai thực tế, có thể có cơ chế chọn đường đọc, so kết quả hoặc tắt đường mới khi phát hiện lỗi. Đây không phải lý do tạo interface cho mọi class: chỉ thêm abstraction khi nó giải quyết **điểm chuyển đổi thực sự**.

### 13.3. Rollback không phải lúc nào cũng đơn giản

Tắt feature flag hoặc chuyển sang version cũ có thể giải quyết vấn đề mã thực thi nhưng **không hoàn tác dữ liệu đã ghi sai, sự kiện đã gửi hoặc hành động đã xảy ra bên ngoài**.

Với thay đổi dữ liệu hoặc tích hợp, cần cân nhắc:

- Tương thích ngược giữa version trước và sau.
- Khả năng phục hồi hoặc bù trừ nghiệp vụ.
- Quy trình migration một chiều có điểm không thể quay lại.
- Tính nhất quán giữa producer và consumer sau replay.
- Người có quyền kích hoạt dừng rollout hoặc phương án khôi phục.

**Kiến trúc tiến hóa không bảo đảm mọi quyết định đều đảo ngược hoàn toàn**. Nó yêu cầu làm rõ mức độ đảo ngược trước khi ra quyết định.

## 14. Chất lượng toàn sản phẩm: ràng buộc xuyên nhóm

Khi một hành trình người dùng đi qua nhiều nhóm, **chất lượng end-to-end không thể là trách nhiệm “phần mình đã chạy” của từng nhóm riêng lẻ**.

### 14.1. Những thuộc tính cần nhìn xuyên hệ thống

| Thuộc tính | Ví dụ rủi ro | Cách phối hợp |
| --- | --- | --- |
| **Bảo mật/phân quyền** | Assessment tin thông tin learnerId do client gửi; Learning hiển thị kết quả trái quyền. | Chuẩn xác thực/quyền, kiểm thử negative cases theo ranh giới. |
| **Độ tin cậy** | Assessment lỗi làm Learning không thể tải toàn bộ trang học. | Quyết định nơi cần đồng bộ, timeout, fallback theo giá trị người dùng. |
| **Hiệu năng** | Mỗi trang phải gọi tuần tự nhiều service, tổng độ trễ cao. | SLO theo hành trình, quan sát trace, giảm phụ thuộc không cần thiết. |
| **Nhất quán dữ liệu** | Điểm quiz đã thay nhưng tiến độ vẫn “chưa hoàn thành”. | Thống nhất mô hình nhất quán, độ trễ chấp nhận và đối soát. |
| **Khả năng vận hành** | Không biết request lỗi ở service nào. | Correlation IDs, tracing, log/metric đủ và chung ngữ nghĩa. |
| **Khả năng thay đổi** | Một yêu cầu cần sửa đồng thời bốn nhóm. | Ranh giới miền, contract versioning, giảm coupling và migration theo bước. |
| **Khả năng phục hồi** | Sự kiện tích tụ nhưng không ai theo dõi consumer lag. | SLI cho backlog/lag, retry policy, cảnh báo có người trực. |
| **Tuân thủ/quyền riêng tư** | Event chứa dữ liệu cá nhân không cần thiết, lưu quá lâu. | Phân loại dữ liệu, mục đích sử dụng, retention và quyền theo chính sách. |

### 14.2. Đặt SLO với phạm vi rõ

Một mục tiêu minh họa:

> “Trong điều kiện tải đã định nghĩa, **95% request mở trang tiến độ** từ người dùng hợp lệ hoàn thành trong **dưới 800 ms**, đo từ ranh giới API phục vụ ứng dụng; nhóm theo dõi tỷ lệ lỗi và độ trễ theo cửa sổ quan sát đã thống nhất.”

Đây là **ví dụ thiết kế**, không phải chuẩn SLO cho mọi nền tảng. Cần xác định rõ môi trường, percentile, đơn vị, phương pháp đo và ảnh hưởng của mạng/client nếu nằm ngoài ranh giới đo.

Khi có nhiều service, **không nên cộng trực tiếp các giá trị p95 của từng service rồi coi đó là p95 end-to-end**. Phân bố phụ thuộc và khả năng gọi song song/phân nhánh cần được đo hoặc mô hình hóa phù hợp.

### 14.3. Một nhóm không thể tự bảo đảm mọi thuộc tính xuyên nhóm

Nếu Learning đạt p95 tốt nội bộ nhưng page load vẫn chậm vì Identity và Assessment, cần làm việc trên **hành trình đầu cuối**. Tương tự, team Assessment không thể tuyên bố quyền riêng tư toàn hệ thống an toàn chỉ vì dữ liệu trong database của mình được mã hóa.

Sự phối hợp cần có **người chịu trách nhiệm cho kết quả chung** và các đầu mối từng ranh giới. Mục tiêu không phải tìm ai để phạt khi SLO lệch, mà là **phát hiện điểm nghẽn và quyết định cải tiến**.

## 15. Scrum, Kanban, XP và Lean hỗ trợ điều phối kiến trúc ra sao?

Kiến trúc tiến hóa không phải framework thay thế Scrum hay Kanban. Nó là cách tư duy và thực hành kỹ thuật có thể **đi cùng nhiều mô hình quản lý công việc**.

### 15.1. Scrum: sản phẩm, Increment và trách nhiệm tự quản

- **Product Owner:** tối đa hóa giá trị, chịu trách nhiệm thứ tự Product Backlog. PO cần hiểu đánh đổi kiến trúc ảnh hưởng thời gian, rủi ro và giá trị để quyết định ưu tiên.
- **Developers:** tạo Increment đáp ứng **Definition of Done**, tự quản kế hoạch triển khai và chịu trách nhiệm chất lượng. Họ cần phối hợp kỹ thuật liên nhóm để các Increment hoạt động cùng nhau.
- **Scrum Master:** hỗ trợ hiệu quả Scrum, làm cho trở ngại được tháo gỡ và hỗ trợ tổ chức giảm rào cản phối hợp.

Khi nhiều Scrum Teams cùng làm **một sản phẩm**, cần làm rõ **một Product Goal, một Product Backlog và một Product Owner** theo cấu trúc Scrum cho sản phẩm đó; các nhóm phải thống nhất **Definition of Done chung** và tích hợp những Increment.

Một cuộc họp kiến trúc **không được quyền tự sắp Product Backlog thay PO** chỉ vì muốn xây phần kỹ thuật thú vị. Nhưng PO cũng không thể dùng quyền ưu tiên để yêu cầu Developers **bỏ qua DoD, bảo mật hoặc hợp đồng đã thống nhất**.

### 15.2. Kanban: phơi bày phụ thuộc và chờ quyết định

Bảng Kanban có thể hiển thị:

~~~text
Ready -> Develop -> Cross-team Review -> Integration Verify -> Done
              WIP 4             WIP 2                WIP 2

Blocked:
  LEARN-42  - Waiting for Assessment event schema
  TEST-18   - Waiting for security review of result visibility
  ID-09     - Waiting for migration compatibility test
~~~

Các giới hạn WIP chỉ là **ví dụ**, không phải giá trị chuẩn. Tín hiệu quan trọng là **tuổi công việc, thời gian bị chặn, số lần bàn giao và số mục Done**, thay vì chỉ đếm đầu việc bắt đầu.

Nếu mọi thay đổi liên nhóm đều chờ một kiến trúc sư duy nhất, cách cải thiện có thể là **định nghĩa guardrails rõ và tự động hóa kiểm tra**, để ít quyết định hơn cần xin duyệt.

### 15.3. XP: tạo phản hồi kỹ thuật sớm

TDD, Continuous Integration, refactoring, pair programming và thiết kế đơn giản giúp:

- Giữ các phần mã dễ đổi theo yêu cầu mới.
- Phát hiện vi phạm hợp đồng và lỗi hồi quy sớm.
- Thảo luận trực tiếp khi hai nhóm chưa thống nhất một ranh giới.
- Tích hợp các lát nhỏ thay vì chờ “big bang”.
- Chia sẻ hiểu biết, giảm điểm nghẽn chỉ một người được phép sửa.

**Refactoring cục bộ và cải tiến kiến trúc liên nhóm không giống nhau về phạm vi rủi ro.** Cả hai cần kiểm thử, nhưng thay dữ liệu/hợp đồng xuyên nhóm đòi hỏi thảo luận và kế hoạch chuyển đổi tương xứng.

### 15.4. Lean: giảm hàng chờ và bàn giao vô ích

Lean giúp nhìn luồng giá trị:

> Nhu cầu người học → quyết định backlog → làm rõ hợp đồng → phát triển → tích hợp → đạt DoD → release → phản hồi.

Nếu một ADR phải chờ hai tuần nhưng phần code chỉ mất hai ngày, có thể **cơ chế ra quyết định** đang là nút thắt. Cần hỏi liệu quyết định có thực sự cần phê duyệt tập trung hay có thể chuyển thành guardrail/test rõ.

**Đừng tối ưu việc mỗi người luôn bận.** Tập trung hoàn tất một lát đầu cuối có thể tạo nhiều giá trị hơn mở đồng thời hàng chục thay đổi kiến trúc chưa tích hợp.

## 16. Lịch phối hợp vừa đủ: không biến thiết kế thành chuỗi cổng duyệt

Một mô hình phối hợp nhẹ có thể gồm những cuộc trao đổi có mục đích, **không áp mọi sự kiện như nghi thức bắt buộc**:

| Hoạt động | Khi nào có ích | Đầu ra cần thiết |
| --- | --- | --- |
| **Product/technical refinement chung** | Trước lát công việc ảnh hưởng nhiều nhóm. | Hành vi end-to-end, dữ liệu, ranh giới, rủi ro và PBI có thể làm. |
| **Architecture huddle ngắn** | Khi có lựa chọn kiến trúc ảnh hưởng hợp đồng hoặc chất lượng. | Các lựa chọn, người quyết định, điểm bất đồng và hành động tiếp. |
| **ADR/RFC bất đồng bộ** | Cần xin ý kiến nhiều nhóm khác múi giờ. | Quyết định/rủi ro có dấu vết, không cần mọi người dự họp cùng giờ. |
| **Contract/integration checkpoint** | Trước thay đổi tương thích hoặc rollout nhiều phiên bản. | Bằng chứng test, chủ sở hữu và điều kiện chuyển bước. |
| **Review kết quả sản phẩm** | Sau khi có Increment, dữ liệu hoặc phản hồi người dùng. | Điều học được và thay đổi backlog/ưu tiên. |
| **Architecture fitness review** | Theo nhịp thích hợp hoặc khi tín hiệu chất lượng lệch. | Guardrail cần giữ/sửa, nợ kỹ thuật cần ưu tiên, ngoại lệ hết hạn. |

**Một cuộc họp có giá trị khi nó tạo quyết định, tháo trở ngại hoặc giảm bất định.** Nếu mọi cuộc họp kiến trúc chỉ là status reporting, hãy thử dùng decision log, dashboard và làm việc trực tiếp giữa nhóm bị ảnh hưởng.

### Có nên lập Architecture Review Board?

Có thể cần một diễn đàn cấp tổ chức khi quyết định **rủi ro cao, khó đảo ngược hoặc có nghĩa vụ bắt buộc**. Nhưng không nên để hội đồng này duyệt mọi refactor nhỏ hoặc trở thành hàng chờ không có SLA phản hồi.

Một chính sách phân tầng:

- **Local change:** team tự quyết và chứng minh bằng test/CI.
- **Cross-team contract:** owner và consumers tham vấn, ADR khi cần.
- **High-risk/org-wide:** xem xét bởi người có thẩm quyền liên quan, có tiêu chí và thời hạn phản hồi rõ.

Đây là lựa chọn **mang tính tổ chức**, không phải thành phần bắt buộc của Scrum.

## 17. Tình huống xuyên suốt: nâng tính năng hoàn thành khóa học

Nhóm sản phẩm muốn người học nhìn thấy **tiến độ khóa học chính xác** sau khi hoàn tất video và bài kiểm tra.

Ba nhóm cùng tham gia:

1. **Identity:** cấp thông tin danh tính và chính sách quyền.
2. **Assessment:** chấm bài, xác định kết quả lần làm bài.
3. **Learning:** tổng hợp tiến độ video và điều kiện hoàn thành học phần.

### 17.1. Lát giá trị đầu tiên

> **Là** người học được cấp quyền, **tôi muốn** thấy một học phần được đánh dấu hoàn thành sau khi đáp ứng điều kiện video và bài kiểm tra, **để** biết phần nào cần học tiếp.

Đừng bắt đầu bằng dự án “thiết kế hệ thống sự kiện hoàn hảo cho mọi học phần trong ba năm tới”. Bắt đầu bằng **quy tắc nghiệp vụ và lát end-to-end cần kiểm chứng**.

### 17.2. Quyết định kiến trúc tối thiểu

| Câu hỏi | Quyết định ứng viên | Nhóm cần tham vấn |
| --- | --- | --- |
| Ai sở hữu điểm bài kiểm tra? | Assessment, không cho Learning ghi trực tiếp. | Assessment, Learning. |
| Ai tính trạng thái hoàn thành học phần? | Learning theo quy tắc sản phẩm đã thống nhất. | Learning, PO, Assessment. |
| Learning biết kết quả quiz bằng cách nào? | Event đã định nghĩa hoặc API phù hợp; thử luồng nhỏ. | Learning, Assessment, Platform. |
| Người học có quyền xem kết quả nào? | Kiểm tra quyền tại ranh giới phục vụ, không tin ID gửi từ client. | Identity, Learning, Assessment, Security. |
| Trạng thái cập nhật ngay hay có trễ? | Phạm vi cho phép nhất quán cuối cùng nếu UI diễn đạt trạng thái chờ rõ. | PO, Learning, Assessment, UX. |
| Trường hợp event trùng hoặc thất bại? | Consumer idempotent, retry/monitor/đối soát. | Learning, Platform/Operations. |

### 17.3. Sơ đồ luồng công việc minh họa

~~~mermaid
sequenceDiagram
    actor Learner as Người học
    participant App as Ứng dụng
    participant Assessment as Assessment
    participant Bus as Event channel
    participant Learning as Learning Progress
    participant Auth as Identity/Access

    Learner->>App: Nộp bài kiểm tra
    App->>Assessment: Submit attempt (auth context)
    Assessment->>Auth: Kiểm tra quyền theo hợp đồng
    Auth-->>Assessment: Quyết định quyền
    Assessment-->>App: Kết quả lần làm bài
    Assessment->>Bus: AttemptCompleted v1
    Bus-->>Learning: Deliver event (có thể lặp)
    Learning->>Learning: Validate, deduplicate, update projection
    Learner->>App: Xem tiến độ học phần
    App->>Learning: Get progress
    Learning->>Auth: Kiểm tra quyền người xem
    Auth-->>Learning: Quyết định quyền
    Learning-->>App: Trạng thái / đang đồng bộ
    App-->>Learner: Hiển thị tiến độ phù hợp
~~~

Sơ đồ có tính **sư phạm**: nó không đề cập toàn bộ cơ chế token, cache, event outbox hay kiểm soát lỗi. Trong hệ thống thực tế, các nhóm phải thiết kế những phần đó theo rủi ro và trách nhiệm. Những lần gọi kiểm tra quyền có thể là kiểm chứng token/claims được ủy quyền theo chính sách; không phải mọi request bắt buộc gọi đồng bộ Identity.

### 17.4. Acceptance criteria của luồng liên nhóm

~~~gherkin
Feature: Tiến độ học phần dựa trên video và kết quả bài kiểm tra

Scenario: Hoàn thành khi đã đạt cả hai điều kiện
  Given người học có quyền truy cập học phần "Java căn bản"
  And tiến độ video của người học đáp ứng điều kiện hoàn thành đã thống nhất
  And Assessment đã ghi nhận lần làm bài đạt yêu cầu
  When Learning xử lý kết quả đánh giá hợp lệ
  Then trạng thái học phần của người học trở thành "Hoàn thành"
  And trạng thái được hiển thị đúng cho người học có quyền

Scenario: Bản tin kết quả được gửi trùng
  Given Learning đã xử lý sự kiện kết quả với eventId "evt-01"
  When cùng sự kiện với eventId "evt-01" được gửi lại
  Then Learning không ghi nhận trùng một lần hoàn thành
  And trạng thái tiến độ vẫn nhất quán với quy tắc nghiệp vụ

Scenario: Kết quả bài kiểm tra chưa được đồng bộ
  Given người học vừa hoàn thành bài kiểm tra
  And trạng thái tổng hợp ở Learning chưa nhận được sự kiện
  When người học mở trang tiến độ
  Then hệ thống không hiển thị xác nhận hoàn thành sai sự thật
  And cung cấp trạng thái đang cập nhật phù hợp với trải nghiệm đã thống nhất

Scenario: Không có quyền xem tiến độ
  Given một tài khoản không được phép xem tiến độ của người học khác
  When tài khoản đó yêu cầu dữ liệu tiến độ của người học khác
  Then hệ thống từ chối theo chính sách
  And không tiết lộ dữ liệu tiến độ riêng tư
~~~

Các ví dụ này là **tiêu chí chấp nhận của một hành vi**, không thay Definition of Done hay các kiểm thử vận hành và bảo mật cần thiết.

### 17.5. Tích hợp sớm để giảm rủi ro

Một nhịp thực hiện khả thi:

- **Lát 1:** thống nhất và thử luồng một lần làm bài với dữ liệu giả lập đúng hợp đồng, kiểm tra quyền ở ranh giới.
- **Lát 2:** tích hợp producer/consumer thật, kiểm thử trùng và retry, quan sát độ trễ.
- **Lát 3:** nối với dữ liệu video và hiển thị trạng thái tổng hợp đúng.
- **Lát 4:** theo phản hồi, điều chỉnh trải nghiệm đang đồng bộ hoặc mở rộng quy tắc học phần khác.

Lát nào được gọi là **Increment Done** phải đáp ứng DoD và có thể sử dụng trong phạm vi thực sự đã giao. Không nên gọi “event mock đã chạy” là luồng sản phẩm hoàn tất khi tích hợp thật chưa đạt.

### 17.6. Khi thử nghiệm cho thấy quyết định sai

Giả sử việc cập nhật bất đồng bộ khiến 30% học viên phải chờ trạng thái lâu hơn mức chấp nhận được trong điều kiện đo đã thống nhất. Đây là **tín hiệu cần xem lại ADR**, không phải lý do giấu số liệu để bảo vệ lựa chọn kiến trúc.

Các phương án có thể gồm tối ưu consumer, giảm backlog, sửa chính sách retry, dùng API đồng bộ cho trường hợp cần kết quả tức thời, hoặc thay cách hiển thị. Chọn dựa trên **chi phí, giá trị, độ tin cậy và dữ liệu mới**, không dựa trên sự trung thành với “event-driven”.

## 18. Đo hiệu quả điều phối kiến trúc mà không biến thành KPI cá nhân

Một cơ chế kiến trúc tốt nên **giảm ma sát khi tạo Increment**, giữ chất lượng và hỗ trợ thay đổi. Không nên đo thành công bằng số ADR hoặc số kiến trúc sư duyệt PR.

| Mục tiêu | Tín hiệu hữu ích | Cách hiểu sai cần tránh |
| --- | --- | --- |
| **Ít chờ quyết định liên nhóm** | Blocked time chờ contract/owner, số lần chuyển cấp, tuổi quyết định chưa chốt. | Ép mọi quyết định phải duyệt trong một giờ dù có rủi ro nghiêm trọng. |
| **Thay đổi độc lập hơn** | Số thay đổi buộc đồng thời deploy nhiều nhóm, sự cố tương thích. | Coi mọi shared change là lỗi; có các thay đổi cần phối hợp thật. |
| **Phản hồi sớm** | Thời gian từ thử hợp đồng đến có test tích hợp; từ Increment Done đến phản hồi người dùng. | Chỉ đếm số buổi họp kiến trúc. |
| **Chất lượng kiến trúc** | Contract failures, vi phạm guardrails, lỗi dữ liệu/phân quyền, độ trễ và availability. | Chỉ đo số test Green mà bỏ hành vi thật. |
| **Năng lực giao hàng** | Cycle time, throughput, WIP, work item age theo loại công việc tương thích. | Xếp hạng nhóm/cá nhân bằng số ticket hoặc story points. |
| **Khả năng thích ứng** | Chi phí/độ lan rộng khi thêm quy tắc, số bước migration, độ ổn định CI. | Đếm số microservices hoặc số interface làm thước đo tốt. |
| **Giá trị sản phẩm** | Người học hoàn thành hành trình, thông tin tiến độ đúng và kịp, tỷ lệ lỗi/khó hiểu. | Tự coi output được release là outcome đã đạt. |
| **Chi phí vận hành** | Sự cố liên nhóm, tốc độ phục hồi, toil và thời gian điều tra. | Giảm chi phí trước mắt bằng cách bỏ quan sát hoặc dự phòng. |

### 18.1. Ví dụ số đo trước và sau guardrail mới

Giả sử trong hai giai đoạn có số thay đổi tương đối giống nhau:

| Chỉ số minh họa | Trước | Sau thử nghiệm |
| --- | ---: | ---: |
| Thời gian chờ median để chốt thay đổi hợp đồng | 4 ngày làm việc | 2 ngày làm việc |
| Tỷ lệ PR vi phạm ranh giới được phát hiện trước merge | 30% trong số vi phạm biết được | 90% trong số vi phạm biết được |
| Sự cố tích hợp sau phát hành | 5 | 2 |
| Trung vị cycle time của mục liên nhóm | 11 ngày | 8 ngày |
| Lỗi phân quyền nghiêm trọng | 0 được phát hiện | 0 được phát hiện |

**Đây chỉ là dữ liệu giả định**, không chứng minh guardrail tạo ra tất cả cải thiện. Nếu cách ghi nhận vi phạm hoặc loại công việc thay đổi, con số không so trực tiếp được. Số lỗi nghiêm trọng bằng 0 trong một mẫu nhỏ **không chứng minh hệ thống không có rủi ro**.

Hãy nhìn xu hướng, phân bố, bối cảnh và chất lượng kết quả. **Fitness functions để phát hiện sai sớm**, không phải công cụ chấm điểm đội nào “tuân thủ hơn” rồi thưởng phạt máy móc.

### 18.2. Một cải tiến kiến trúc tốt có thể làm chỉ số cục bộ xấu tạm thời

Trong giai đoạn migration, nhóm có thể cần duy trì song song hai đường dữ liệu, số thay đổi và số bước tích hợp tăng. Đó có thể là **chi phí chuyển đổi có chủ đích** để giảm coupling lâu dài.

Đánh giá cần cân bằng **chi phí hiện tại, rủi ro chuyển đổi và khả năng thay đổi trong tương lai**. Không nên yêu cầu mọi chỉ số đều cải thiện ngay trong tuần đầu.

## 19. Xử lý ngoại lệ với guardrails mà không làm vô hiệu ràng buộc

Không một bộ guardrails nào dự đoán được mọi tình huống. Nhưng “ngoại lệ” phải có cơ chế minh bạch, nhất là khi ảnh hưởng bảo mật hoặc dữ liệu.

### Các bước xử lý ngoại lệ

1. **Nêu lý do:** ràng buộc hiện tại ngăn mục tiêu nào, vì sao?
2. **Xác định phạm vi:** module, service, người dùng, dữ liệu, thời gian và các nhóm chịu tác động.
3. **Phân tích rủi ro:** điều gì có thể sai, có biện pháp bù trừ phù hợp không?
4. **Xác định thẩm quyền:** ai được quyền chấp nhận ngoại lệ theo chính sách tổ chức?
5. **Ghi quyết định:** ADR hoặc decision log, điều kiện áp dụng và dấu vết tham vấn.
6. **Đặt mốc xem lại/hết hạn:** ngoại lệ không trở thành luật mới ngầm định mãi mãi.
7. **Quan sát:** theo dõi tín hiệu rủi ro và phương án giảm/hoàn tác.

### Ví dụ ngoại lệ có thể cân nhắc

Một consumer cũ không hỗ trợ trường sự kiện mới nên nhóm cần duy trì **phiên bản cũ trong một giai đoạn chuyển đổi**. Ngoại lệ có điều kiện, thời hạn và test tương thích có thể hợp lý.

### Ví dụ không được tự cấp ngoại lệ

“Để phát hành kịp, endpoint tiến độ tạm thời **không kiểm tra quyền**, sau Sprint sẽ thêm lại.” Đây là nguy cơ truy cập dữ liệu trái phép, không thể hợp thức hóa bằng chữ “tạm”. Cần chọn phạm vi phát hành an toàn hơn, giải pháp đúng hoặc thương lượng lại mốc.

## 20. Các anti-patterns khi điều phối kiến trúc

| Anti-pattern | Biểu hiện | Cách điều chỉnh |
| --- | --- | --- |
| **Hội đồng duyệt mọi thay đổi** | Đổi tên hàm cũng phải chờ lịch họp kiến trúc. | Phân tầng quyết định; local tự quyết, chỉ đưa việc liên nhóm/rủi ro cao vào tham vấn phù hợp. |
| **“Mỗi team tự do tuyệt đối”** | Không có sở hữu dữ liệu, hợp đồng hoặc tiêu chuẩn tích hợp. | Ràng buộc chung ít nhưng rõ, có fitness functions. |
| **Kiến trúc sư thiết kế tất cả từ xa** | Không tham gia code/test, quyết định dựa trên giả định. | Cùng Developers thử lát end-to-end, review dữ liệu vận hành. |
| **ADR chỉ ghi phương án đã chọn** | Người sau không hiểu vì sao giải pháp hợp lý. | Ghi bối cảnh, lựa chọn khác, đánh đổi và điều kiện xem lại. |
| **ADR trở thành tài liệu không ai đọc** | Quyết định nằm ở chỗ khó tìm, code không liên kết. | Liên kết ADR từ backlog/PR/contract và chỉ viết quyết định quan trọng. |
| **Rule không ai kiểm tra** | “Không được truy cập DB chéo” nhưng vi phạm thường xuyên. | Test kiến trúc/quyền, reviewer chịu trách nhiệm phù hợp. |
| **Chỉ kiểm tra tự động, bỏ ngữ nghĩa nghiệp vụ** | Schema hợp lệ nhưng trạng thái COMPLETED mang nghĩa khác. | Thảo luận domain, acceptance/contract/integration tests. |
| **Chọn microservices như mục tiêu tự thân** | Nhiều service nhỏ nhưng coupling và vận hành tăng. | Chọn theo ranh giới miền, năng lực và nhu cầu đổi độc lập; monolith module hóa cũng hợp lệ. |
| **Một shared database không rõ chủ sở hữu** | Nhiều nhóm cùng ghi và thay schema tùy ý. | Chỉ rõ ownership/đường ghi, hợp đồng thay đổi và kiểm soát chuyển đổi. |
| **Thay đổi hợp đồng đột ngột** | Producer đổi trường rồi consumer gãy production. | Kiểm thử tương thích, versioning và expand–contract. |
| **Event-driven cho mọi thứ** | Nhu cầu cần kết quả ngay nhưng dùng projection chậm, không có trạng thái rõ. | Chọn giao tiếp theo tính nhất quán, latency và khả năng vận hành thực. |
| **Giao tiếp đồng bộ thành chuỗi dài** | Mỗi request phụ thuộc nhiều service và lan truyền lỗi. | Quan sát trace, xem lại coupling, giảm đường đồng bộ khi có giá trị. |
| **Quy tắc bảo mật khác nhau giữa các nhóm** | Một đường gọi bỏ kiểm tra quyền. | Guardrail an toàn, test negative cases và trách nhiệm rõ. |
| **Đòi đồng thuận tuyệt đối** | Mọi quyết định trì hoãn tới khi tất cả thích một giải pháp. | Tham vấn người bị ảnh hưởng, có đầu mối chốt và đường chuyển cấp. |
| **Che rủi ro để không làm chậm Sprint** | Không ghi blocked, không thông báo hợp đồng thiếu. | Minh bạch tác động Sprint Goal, PO/SM hỗ trợ phối hợp. |
| **Coi hết lỗi kỹ thuật là lỗi cá nhân** | Các nhóm ngại nêu nợ hoặc giới hạn của kiến trúc. | Cải tiến hệ thống bằng dữ liệu và trách nhiệm phối hợp. |
| **SLO/fitness chỉ đặt để trình bày** | Không có cách đo, owner hoặc phản ứng khi lệch. | Định nghĩa phép đo, cảnh báo/đầu mối và cách thích ứng. |
| **Không gỡ ngoại lệ cũ** | Ngoại lệ “tạm” tồn tại nhiều năm, phá ranh giới. | Có expiry/review và kế hoạch đưa về chuẩn hoặc sửa chuẩn. |

## 21. Mẫu làm việc: Architecture Coordination Agreement

Một thỏa thuận ngắn giúp các nhóm phối hợp mà không phải nhớ các quy tắc truyền miệng. Đây là **mẫu tùy chọn**, không phải hiện vật bắt buộc của Scrum.

~~~text
MỤC TIÊU SẢN PHẨM:
  Giá trị người dùng và kết quả nào cần đạt?

RANH GIỚI VÀ SỞ HỮU:
  Module/domain nào do nhóm nào chịu trách nhiệm?
  Quy tắc nghiệp vụ/dữ liệu nào là nguồn sự thật?

GUARDRAILS CHUNG:
  Bảo mật, tương thích, quan sát, DoD, dữ liệu và vận hành cần giữ.
  Quy tắc nào bắt buộc, quy tắc nào chỉ là khuyến nghị mặc định?

QUYỀN QUYẾT ĐỊNH:
  Local changes: team sở hữu tự quyết trong guardrails.
  Contract changes: owner tham vấn consumer.
  Org/safety decisions: người có thẩm quyền theo chính sách.
  Khi bất đồng, chuyển cấp theo phạm vi nào?

HỢP ĐỒNG:
  API/events/schema, versioning, error semantics, auth,
  tính nhất quán, idempotency và kế hoạch tương thích.

KIỂM CHỨNG:
  Contract tests, architecture tests, integration tests,
  SLIs/SLOs và những phép kiểm tra cần thiết khác.

TÀI LIỆU QUYẾT ĐỊNH:
  Khi nào cần ADR? Nơi lưu, người chốt, cách thay thế ADR cũ.

PHỐI HỢP:
  Kênh thảo luận; thời hạn phản hồi phù hợp với mức rủi ro;
  cách xử lý blocker và sự cố khẩn.

THAY ĐỔI VÀ PHÁT HÀNH:
  Kế hoạch migration, rollout, rollback/compensation và thông báo.

ĐÁNH GIÁ LẠI:
  Dữ liệu nào cho thấy guardrail hữu ích/hại?
  Khi nào xem lại ngoại lệ và quyết định kiến trúc?
~~~

Nếu nhóm chỉ có hai module nhỏ, thỏa thuận có thể rất ngắn. Không cần tạo bộ tài liệu hàng trăm trang trước khi bắt đầu. **Sự rõ ràng của quyền và hợp đồng** quan trọng hơn số lượng biểu mẫu.

## 22. Bài tập thực hành: xung đột kiến trúc giữa bốn nhóm

Một tổ chức phát triển nền tảng học Java có bốn nhóm:

- **Identity:** tài khoản, quyền truy cập và đăng ký vào khóa học.
- **Content:** bài học và video.
- **Assessment:** bài kiểm tra và điểm.
- **Learning:** tiến độ và trang tổng quan học tập.

Product Owner muốn ra bản thử trong **bốn tuần** để người học thấy được **“Khóa học đã hoàn thành”** khi đã xem đủ bài và đạt bài kiểm tra. Các điều kiện đã biết:

1. Assessment đang lưu kết quả trong một database riêng và có service API.
2. Learning đề xuất đọc trực tiếp bảng Assessment vì “nhanh hơn làm API”.
3. Identity muốn thay format ID học viên và dự định deploy vào giữa Sprint.
4. Content muốn thêm sự kiện “VideoCompleted” nhưng chưa thống nhất khi nào coi là hoàn tất.
5. Nhóm vận hành chỉ có một người hiểu message broker, trong khi một kiến trúc sư đề xuất dùng event-driven cho mọi giao tiếp.
6. Sản phẩm chứa thông tin tiến độ cá nhân; không được lộ kết quả cho tài khoản trái quyền.
7. Hiện mỗi nhóm có DoD riêng, khác nhau về kiểm thử tích hợp và bảo mật.
8. Ban quản lý muốn mọi ADR phải đợi cuộc họp duyệt kiến trúc hai tuần một lần.

### Nhiệm vụ

1. **Tìm ranh giới:** xác định nhóm sở hữu dữ liệu điểm, tiến độ, video và danh tính; nêu quy tắc nghiệp vụ nào còn thiếu chủ sở hữu.
2. **Phân loại quyết định:** đổi tên phương thức nội bộ, đổi ID học viên công khai, thêm sự kiện VideoCompleted, đổi công nghệ logging, thay cơ chế kiểm tra quyền — quyết định nào cục bộ, nào liên nhóm hoặc cần thẩm quyền tổ chức?
3. **Guardrails:** đề xuất tối thiểu năm ràng buộc chung, mỗi ràng buộc có lý do và một cách kiểm chứng.
4. **Đánh đổi:** so sánh ba cách Learning lấy kết quả quiz: đọc DB chéo, API đồng bộ và sự kiện; chọn một phương án có điều kiện, không chỉ nêu ưu điểm.
5. **ADR:** viết một ADR ngắn về hợp đồng thay đổi ID học viên hoặc giao tiếp kết quả quiz, có trạng thái, owner, phương án, hệ quả và thời điểm xem lại.
6. **Tính khả thi:** nếu message broker hiện có ít người vận hành, quyết định “mọi thứ event-driven” có nên mặc định được chấp nhận không?
7. **Thay đổi tương thích:** đề xuất cách đổi format ID mà không buộc mọi nhóm deploy cùng lúc trong một ngày.
8. **Definition of Done:** khi nhiều Scrum Teams cùng một sản phẩm, cần xử lý DoD khác nhau thế nào?
9. **Quản trị:** đề xuất một quy trình ra quyết định nhanh hơn họp hai tuần một lần nhưng vẫn xử lý những quyết định rủi ro cao.
10. **Phản hồi:** đề xuất hai số đo luồng, hai tín hiệu chất lượng/kiến trúc và một chỉ số giá trị sản phẩm.
11. **Kiểm thử:** viết ít nhất ba acceptance scenarios cho hành vi hoàn thành khóa học, gồm bản tin trùng và quyền truy cập.
12. **Cập nhật kế hoạch:** nếu sau tuần đầu thử tích hợp cho thấy API hiện có đủ nhanh và đáng tin, bạn có sẵn sàng xem lại lựa chọn event-driven không? Vì sao?

## 23. Hướng giải tham khảo cho bài tập

### 23.1. Phân ranh giới và quyền quyết định

- **Assessment** chịu trách nhiệm kết quả đánh giá và hợp đồng cung cấp kết quả.
- **Content** chịu trách nhiệm trạng thái bài/video theo miền phù hợp.
- **Identity** chịu trách nhiệm danh tính và ràng buộc quyền liên quan.
- **Learning** chịu trách nhiệm tổng hợp tiến độ/hoàn thành khóa học nếu đó là phân định đã thống nhất.
- **Product Owner và chuyên gia nghiệp vụ** cần làm rõ ngưỡng “xem đủ” và “đạt bài kiểm tra”, điều kiện xử lý phúc khảo hoặc thay đổi kết quả.

Đổi tên phương thức nội bộ không đổi hợp đồng thường là **quyết định cục bộ**. Đổi format ID công khai và thêm event là **quyết định liên nhóm**. Thay quy tắc kiểm tra quyền có thể liên quan **chính sách bắt buộc cấp tổ chức**. Công nghệ logging có thể là lựa chọn cục bộ nếu vẫn đạt chuẩn quan sát chung; nếu ảnh hưởng tính tương thích telemetry toàn hệ thống thì cần phối hợp liên nhóm.

### 23.2. Guardrails mẫu

| Ràng buộc | Vì sao | Cách kiểm chứng |
| --- | --- | --- |
| **Dữ liệu có chủ sở hữu ghi rõ** | Tránh chỉnh sửa chéo và schema coupling. | Quyền DB, dependency tests, tài liệu sở hữu. |
| **Thay hợp đồng có đường tương thích** | Tránh deploy đồng thời và consumer lỗi. | Schema/contract tests, thử ma trận version. |
| **Kiểm tra quyền tại ranh giới phục vụ** | Không lộ tiến độ cá nhân. | Negative authorization tests. |
| **Dữ liệu hoàn thành chỉ phát sinh từ quy tắc thống nhất** | Không có hai trạng thái “Hoàn thành” mâu thuẫn. | Acceptance/integration tests và chủ sở hữu nghiệp vụ. |
| **Increment chung đạt DoD** | Tạo phần mềm có thể sử dụng toàn sản phẩm. | CI, integration/quality checks. |
| **Có telemetry cho luồng quan trọng** | Truy vết lỗi đa nhóm. | Trace/correlation verification và quan sát runtime. |

### 23.3. Chọn phương án giao tiếp

**Đọc DB chéo** dễ bắt đầu nhưng coupling và quyền sở hữu rủi ro cao. **API đồng bộ** có thể là lựa chọn đầu nếu yêu cầu cần kết quả ngay, hiện có API đủ tin cậy và đội ngũ vận hành còn hạn chế. **Event** có thể phù hợp hơn khi nhiều consumer cần dữ liệu cập nhật theo sự kiện và hệ thống chấp nhận độ trễ, với điều kiện đầu tư vào idempotency, replay, lag và khả năng vận hành.

Phương án đề xuất có điều kiện:

> “Trong bản thử bốn tuần, Learning dùng API Assessment đã có để lấy kết quả cần thiết theo hợp đồng versioned, tránh truy vấn DB nội bộ. Chỉ bổ sung event cho trường hợp cần tách nhịp hoặc nhiều consumer khi có bằng chứng nhu cầu và năng lực vận hành, ghi lại trong ADR.”

Đây chỉ là **một lựa chọn hợp lý theo dữ kiện bài tập**, không phải đáp án duy nhất. Nếu hệ thống đã có hạ tầng sự kiện đáng tin và mô hình dữ liệu cần nhất quán cuối cùng, có thể chọn cách khác với đánh đổi được ghi rõ.

### 23.4. Đổi ID học viên theo giai đoạn

1. Identity cung cấp **một hợp đồng ổn định** hoặc mapping hỗ trợ ID cũ/mới trong giai đoạn chuyển đổi.
2. Consumer được cập nhật để **đọc cả hai** hoặc sử dụng ID chuẩn hóa qua hợp đồng.
3. Kiểm tra phân quyền không dựa vào một ID do client tự đưa chưa xác thực.
4. Chạy contract tests và thử từng consumer.
5. Chỉ loại bỏ ID cũ khi đã xác nhận toàn bộ consumer được chuyển an toàn.
6. Theo dõi lỗi lookup, dữ liệu mồ côi và có kế hoạch đối soát.

Nếu ID là khóa ngoại trong nhiều hệ thống, cần xem kỹ **migration dữ liệu và tính toàn vẹn**; không chỉ đổi chuỗi trong JSON rồi coi hoàn tất.

### 23.5. DoD, governance và số đo

Với nhiều Scrum Teams cùng một sản phẩm, cần **một DoD chung** phù hợp tiêu chuẩn tổ chức và tích hợp Increment; không thể nhóm Learning gọi Done khi kiểm thử bảo mật đang là điều kiện của sản phẩm.

Quy trình kiến trúc có thể phân tầng: thay đổi cục bộ tự quyết, thay đổi hợp đồng tham vấn owner/consumer bằng ADR bất đồng bộ, thay đổi khó đảo ngược/rủi ro cao có review theo thẩm quyền và thời gian phản hồi rõ. Không để mọi đổi tên hoặc refactor nhỏ phải đợi cuộc họp hai tuần.

Số đo ví dụ: **blocked time** chờ contract và **cycle time** liên nhóm; **contract failures sau release** và **sự cố phân quyền/độ trễ**; **tỷ lệ người học nhận đúng trạng thái hoàn thành sau khi đáp ứng điều kiện** (với cửa sổ đo và độ trễ chấp nhận đã thống nhất).

### 23.6. Acceptance scenarios gợi ý

~~~gherkin
Feature: Trạng thái hoàn thành khóa học

Scenario: Hai điều kiện hoàn thành đều đạt
  Given người học có quyền truy cập khóa "Java cơ bản"
  And người học đã hoàn thành video theo quy tắc được thống nhất
  And Assessment đã ghi nhận bài kiểm tra đạt yêu cầu
  When Learning nhận dữ liệu đánh giá hợp lệ và cập nhật tiến độ
  Then trạng thái khóa học của người học trở thành "Hoàn thành"

Scenario: Xử lý sự kiện kết quả trùng
  Given Learning đã xử lý sự kiện kết quả có eventId "evt-42"
  When Learning nhận lại cùng eventId "evt-42"
  Then trạng thái hoàn thành không bị ghi nhận trùng
  And dữ liệu tiến độ vẫn nhất quán

Scenario: Không có quyền xem tiến độ người khác
  Given một tài khoản không có quyền xem tiến độ của người học khác
  When tài khoản đó yêu cầu trạng thái hoàn thành khóa học của người học khác
  Then hệ thống từ chối truy cập theo chính sách
  And không tiết lộ dữ liệu học tập riêng tư

Scenario: Kết quả đánh giá chưa đến nơi tổng hợp
  Given người học đã nộp bài kiểm tra thành công
  And Learning chưa nhận được dữ liệu kết quả hợp lệ
  When người học mở trang tiến độ
  Then giao diện không khẳng định sai rằng khóa học đã hoàn thành
  And thể hiện trạng thái chờ cập nhật phù hợp theo quy tắc sản phẩm
~~~

### 23.7. Vì sao phải sẵn sàng xem lại quyết định?

Kiến trúc tiến hóa đòi hỏi **quyết định có điều kiện**, không phải gắn danh dự với một công nghệ. Nếu dữ liệu thực tế cho thấy API đồng bộ hiện có giải quyết yêu cầu đủ tốt, ít chi phí vận hành và không gây coupling khó chấp nhận, việc hoãn event-driven có thể là lựa chọn tốt hơn. Nếu về sau xuất hiện nhiều consumer hoặc yêu cầu tính sẵn sàng khác, ADR được xem lại cùng bằng chứng mới.

## 24. Tự kiểm tra kiến thức

**Câu 1.** Kiến trúc tiến hóa có nghĩa mọi nhóm được tự quyết mọi thứ mà không cần ranh giới chung không?

**Đáp án:** Không. Cần giữ ràng buộc về dữ liệu, hợp đồng, an toàn và chất lượng chung; trao quyền cục bộ trong những ranh giới đó và kiểm chứng bằng phản hồi thực tế.

**Câu 2.** Mọi lần đổi tên phương thức nội bộ có cần ADR và hội đồng kiến trúc duyệt không?

**Đáp án:** Không. Nếu không thay hợp đồng và rủi ro nhỏ, commit/PR cùng kiểm thử thường đủ. ADR nên dành cho quyết định có tác động đáng kể hoặc khó đảo ngược.

**Câu 3.** Vì sao “schema của event không đổi” vẫn chưa đủ chứng minh hợp đồng an toàn?

**Đáp án:** Ý nghĩa nghiệp vụ, điều kiện thành công, quyền truy cập, thứ tự sự kiện, retry và xử lý lỗi vẫn có thể thay đổi. Cần kiểm tra ngữ nghĩa và hành trình end-to-end.

**Câu 4.** Nếu Learning đọc trực tiếp bảng Assessment và chạy nhanh, có thể kết luận đó luôn là kiến trúc tốt nhất không?

**Đáp án:** Không. Cần xem quyền sở hữu dữ liệu, coupling schema, khả năng thay đổi, kiểm soát quyền và chi phí tương thích lâu dài. Shared database có thể hợp lý trong một số bối cảnh, nhưng cần ranh giới rõ.

**Câu 5.** ADR cần ghi gì ngoài phương án được chọn?

**Đáp án:** Bối cảnh, lựa chọn khác, yếu tố quyết định, hệ quả, rủi ro, owner/thẩm quyền, cách kiểm chứng và điều kiện xem lại.

**Câu 6.** Event-driven có luôn tốt hơn API đồng bộ khi nhiều team tham gia không?

**Đáp án:** Không. Nó có thể giảm phụ thuộc thời gian thực nhưng thêm lag, duplicate, out-of-order và chi phí vận hành. Chọn theo yêu cầu nhất quán, latency, độ tin cậy và năng lực thực tế.

**Câu 7.** Một architecture fitness function có thể là gì?

**Đáp án:** Kiểm tra không có phụ thuộc tới persistence nội bộ của module khác, contract tests, kiểm thử quyền, hoặc SLI/SLO quan sát độ trễ. Nó cần gắn với thuộc tính kiến trúc có lý do.

**Câu 8.** Những phép kiểm tra tự động có thay thế hoàn toàn sự trao đổi miền nghiệp vụ không?

**Đáp án:** Không. Tests có thể Green trong khi các nhóm hiểu khác nghĩa của “Hoàn thành”. Cần thảo luận chủ sở hữu quy tắc và ví dụ hành vi.

**Câu 9.** Tại sao migration nhiều bước thường an toàn hơn đổi tất cả service cùng lúc?

**Đáp án:** Có thể giữ tương thích, kiểm chứng từng bước, giới hạn phạm vi lỗi và chuẩn bị đường quay lại. Tuy nhiên cần chú ý dữ liệu và tác dụng phụ có thể không rollback hoàn toàn.

**Câu 10.** Khi nhiều Scrum Teams cùng một sản phẩm, có thể mỗi nhóm dùng DoD khác nhau cho Increment của cùng sản phẩm không?

**Đáp án:** Theo Scrum, các nhóm cùng sản phẩm cần một **Definition of Done chung** và Increment tích hợp; tiêu chuẩn tổ chức áp dụng vẫn phải được tuân thủ.

**Câu 11.** Nếu cổng duyệt kiến trúc làm chờ hai tuần, nên bỏ tất cả review không?

**Đáp án:** Không. Nên phân tầng quyết định, tự động hóa guardrails và chỉ đưa thay đổi rủi ro cao hoặc liên nhóm vào tham vấn phù hợp, giữ thẩm quyền/kiểm soát bắt buộc.

**Câu 12.** Những chỉ số nào tốt hơn “số ADR đã viết” khi xem hiệu quả điều phối?

**Đáp án:** Blocked time, cycle time liên nhóm, lỗi hợp đồng sau phát hành, khả năng thay đổi độc lập, mức sự cố, chất lượng trải nghiệm và kết quả người dùng có bối cảnh.

## 25. Checklist điều phối kiến trúc giữa các nhóm

### Ranh giới và trách nhiệm

- [ ] Mục tiêu sản phẩm và hành trình người dùng xuyên nhóm đã rõ.
- [ ] Mỗi quy tắc nghiệp vụ quan trọng có chủ sở hữu quyết định.
- [ ] Dữ liệu quan trọng có quyền ghi và hợp đồng truy cập rõ.
- [ ] Nhóm biết quyết định nào tự chốt, quyết định nào cần tham vấn.
- [ ] Có kênh xử lý bất đồng và chuyển cấp theo đúng thẩm quyền.

### Ràng buộc và kiểm chứng

- [ ] Guardrails có mục đích, phạm vi và cách kiểm chứng.
- [ ] Không có đường truy cập trái quyền đến dữ liệu cá nhân.
- [ ] API/event có ngữ nghĩa, versioning và kế hoạch tương thích.
- [ ] Duplicate/retry/out-of-order được xử lý nơi cần.
- [ ] Tích hợp nhiều nhóm được kiểm tra sớm ở mức độ rủi ro phù hợp.
- [ ] Fitness functions quan trọng chạy theo nhịp thay đổi thực tế.
- [ ] DoD, chất lượng và nghĩa vụ tổ chức không bị hạ ngầm.

### Quyết định và thay đổi

- [ ] Các quyết định đáng kể có ADR/decision log dễ tìm.
- [ ] ADR ghi lựa chọn khác và lý do, không chỉ kết luận.
- [ ] Người tiêu thụ hợp đồng được tham vấn trước thay đổi ảnh hưởng họ.
- [ ] Thay đổi lớn được chia thành bước tương thích khi có thể.
- [ ] Có kế hoạch quan sát, khôi phục và đối soát dữ liệu theo rủi ro.
- [ ] Ngoại lệ có chủ sở hữu, thẩm quyền và mốc xem lại.
- [ ] Không phải mọi thay đổi nhỏ đều bị đẩy vào cổng phê duyệt tập trung.

### Phản hồi và cải tiến

- [ ] Nhóm xem blocked time, WIP và luồng công việc liên nhóm.
- [ ] Có tín hiệu chất lượng, độ tin cậy, bảo mật và giá trị người dùng.
- [ ] Mọi thay đổi kiến trúc có giả định hoặc điều kiện để xem lại.
- [ ] Các nhóm dùng dữ liệu để cải tiến, không xếp hạng cá nhân bằng số ticket/ADR.
- [ ] Có thể giải thích rõ vì sao kiến trúc hiện tại còn phù hợp hoặc cần đổi.

## 26. Ghi nhớ trọng tâm

- **Thiết kế tiến hóa không phải thiết kế tùy hứng.** Giữ những ràng buộc bảo vệ dữ liệu, hợp đồng, chất lượng và khả năng đổi, rồi học từ thực tế để điều chỉnh.
- **Phân tầng quyết định:** thay đổi cục bộ dễ đảo ngược nên được trao quyền; quyết định liên nhóm hoặc khó đảo ngược cần tham vấn và bằng chứng tương xứng.
- **Guardrails hữu ích khi có lý do, phạm vi, người chịu trách nhiệm và cách kiểm chứng.** Chúng không nên khóa mọi lựa chọn công nghệ không có nhu cầu thực.
- **Ranh giới miền và quyền sở hữu dữ liệu rõ** giảm phụ thuộc vào schema nội bộ và nguy cơ quy tắc nghiệp vụ bị sao chép.
- **Hợp đồng API/event cần cả cú pháp và ngữ nghĩa**, gồm quyền truy cập, lỗi, tương thích, idempotency, thứ tự và mức nhất quán.
- **Không có quy luật “microservices tốt hơn monolith” hoặc “event tốt hơn API”.** Chọn dựa trên sản phẩm, rủi ro, khả năng vận hành và bằng chứng.
- **ADR ghi lại lý do, lựa chọn, hệ quả, chủ sở hữu và điều kiện xem lại.** Đây là công cụ truyền thông và học hỏi, không phải thủ tục để hợp thức hóa mọi quyết định nhỏ.
- **Architectural fitness functions** đưa kiểm tra ranh giới, hợp đồng, bảo mật và chất lượng vào CI/vận hành; chúng bổ trợ chứ không thay trao đổi nghiệp vụ.
- **Migration tiến hóa theo các bước tương thích** có thể giảm rủi ro thay đổi lớn, nhưng cần xử lý dữ liệu, side effects và khả năng khôi phục thực tế.
- **Scrum giữ mục tiêu, trách nhiệm và DoD; Kanban giúp nhìn hàng chờ; XP giữ kỹ thuật phản hồi sớm; Lean tối ưu dòng giá trị.** Những thực hành này bổ trợ điều phối kiến trúc nhiều nhóm.
- **Đo hiệu quả bằng khả năng giao giá trị, độ tin cậy và chi phí thay đổi**, không bằng số buổi duyệt hay số ADR được viết.
- **Quyết định kiến trúc là lựa chọn có điều kiện.** Khi dữ liệu hoặc mục tiêu đổi, nhóm có trách nhiệm xem lại thay vì bảo vệ phương án cũ bằng mọi giá.

Một kiến trúc phát triển bền vững không đến từ việc **một người vẽ sơ đồ hoàn hảo cho tất cả nhóm** hoặc **mỗi nhóm tự xây một thế giới riêng**. Nó xuất hiện khi các nhóm hiểu rõ **điều gì phải nhất quán, ai được quyết điều gì, bằng chứng nào chứng minh hệ thống còn đáp ứng mục tiêu và khi nào cần thay đổi quyết định**. Với ràng buộc vừa đủ, hợp đồng rõ ràng và vòng phản hồi ngắn, sản phẩm có thể tiến hóa theo nhu cầu người dùng mà không mất khả năng tích hợp, chất lượng và thích ứng.

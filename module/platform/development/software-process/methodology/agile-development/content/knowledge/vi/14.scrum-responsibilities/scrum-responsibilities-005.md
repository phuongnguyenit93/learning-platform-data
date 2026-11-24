# Developers và trách nhiệm xây dựng phần tăng trưởng sử dụng được

## 1. Đích đến của Developers không phải là “viết xong mã”

Trong Scrum, việc một thành viên hoàn thành hàm, giao diện, API hay kịch bản kiểm thử là một bước tiến cần thiết, nhưng **không tự động có nghĩa sản phẩm đã có một phần tăng trưởng sử dụng được**. Nếu các phần việc chưa tích hợp, lỗi quan trọng chưa được xử lý hoặc chất lượng chưa đạt chuẩn, người dùng chưa nhận được kết quả đáng tin cậy.

Scrum Guide 2020 dùng thuật ngữ **Developers** cho những người thuộc Scrum Team **cam kết tạo ra bất kỳ khía cạnh nào của một Increment sử dụng được trong mỗi Sprint**. Trách nhiệm này không chỉ thuộc về người viết code. Tùy bối cảnh sản phẩm, Developers có thể đóng góp kỹ năng kiểm thử, thiết kế, kiến trúc, dữ liệu, vận hành, bảo mật, trải nghiệm người dùng và kỹ thuật phần mềm.

Ví dụ, với một nền tảng học trực tuyến, mục tiêu Sprint là giúp học viên đăng ký khóa học miễn phí còn chỗ. Một người hoàn tất form đăng ký, một người hoàn tất API, người khác viết test, nhưng luồng thực tế vẫn tạo hai đăng ký khi người dùng nhấn nút hai lần. **Mục tiêu xây dựng Increment đáng tin cậy chưa đạt**, dù từng cá nhân đã hoàn tất phần việc được phân.

Bài học này thuộc **AGILE_DEVELOPMENT**, tập trung vào phần trách nhiệm Developers trong khung Scrum: **tự quản lý kế hoạch, bảo vệ chất lượng, thường xuyên thích ứng và cùng nhau hoàn tất phần mềm có thể sử dụng**. Các thực hành như user story, backlog, Kanban, XP và chỉ số dòng công việc được dùng ở đây như công cụ hỗ trợ kết quả đó, không phải những điều Scrum bắt buộc áp dụng nguyên dạng.

> **Ý chính:** Developers cùng chịu trách nhiệm nghề nghiệp đối với việc tạo Increment có thể sử dụng và đạt Definition of Done, chứ không chỉ chịu trách nhiệm “làm xong phần việc của mình”.

## 2. Developers là ai và có những trách nhiệm chính thức nào?

### 2.1. “Developers” là accountability, không phải tên chức danh tuyển dụng

Theo Scrum Guide 2020, Scrum Team gồm **Product Owner, Scrum Master và Developers**. Đây là ba nhóm **trách nhiệm (accountabilities)** được xác định trong Scrum, không đồng nghĩa với ba phòng ban hoặc một sơ đồ phân cấp.

Một số cách hiểu thường gặp:

| Thành viên hoặc năng lực | Có thể là Developer trong Scrum Team không? | Điều kiện cần hiểu |
| --- | --- | --- |
| Kỹ sư backend/frontend/mobile | Có | Cùng đóng góp vào việc tạo Increment đáp ứng DoD. |
| Người chuyên kiểm thử hoặc tự động hóa test | Có | Chất lượng là trách nhiệm chung, không chỉ là “cửa kiểm tra” sau khi code. |
| Chuyên gia UI/UX tham gia tạo sản phẩm | Có | Đóng góp vào hành vi sử dụng được; vai trò thực tế tùy cách tổ chức đội. |
| Kỹ sư dữ liệu, hạ tầng, vận hành | Có | Khi là thành viên Scrum Team cùng làm để tạo Increment. |
| Chuyên gia bảo mật | Có thể | Nếu là thành viên Scrum Team; chuyên gia tư vấn bên ngoài vẫn có thể hỗ trợ mà không thuộc Team. |
| Product Owner hoặc Scrum Master | Có accountability riêng | Có thể đóng góp kỹ năng, nhưng không vì thế được xóa các trách nhiệm chính thức hoặc quyền tự quản lý của Developers. |

Không cần gọi mọi người là “lập trình viên”. Từ **Developers** nhấn mạnh năng lực tạo kết quả cho sản phẩm. Scrum Team mang tính **liên chức năng**, có hoặc có quyền tiếp cận những kỹ năng cần thiết để tạo giá trị, và **tự quản lý** ai làm gì, khi nào, bằng cách nào trong nhóm.

Điều này không có nghĩa một người phải thành thạo mọi chuyên môn. Nhóm cần **hợp tác và chia sẻ trách nhiệm** để không biến mỗi kỹ năng thành một hàng đợi chuyển giao không ai chịu trách nhiệm chung.

### 2.2. Bốn trách nhiệm của Developers theo Scrum Guide 2020

Scrum Guide nêu rõ Developers luôn chịu trách nhiệm:

1. **Tạo kế hoạch cho Sprint — Sprint Backlog.**
2. **Thấm nhuần chất lượng bằng cách tuân thủ Definition of Done.**
3. **Điều chỉnh kế hoạch hằng ngày để hướng tới Sprint Goal.**
4. **Giữ trách nhiệm lẫn nhau như những người làm nghề chuyên nghiệp.**

Diễn giải thực hành:

| Trách nhiệm | Câu hỏi Developers phải trả lời | Bằng chứng thực tế |
| --- | --- | --- |
| **Lập Sprint Backlog** | Cần chọn công việc và thực hiện thế nào để đạt mục tiêu Sprint? | Sprint Goal, PBIs được chọn và kế hoạch do Developers tạo, đủ minh bạch để phối hợp. |
| **Duy trì chất lượng theo DoD** | Phần được gọi là Done có thật sự đạt chuẩn chung không? | Code tích hợp, kiểm thử, các kiểm soát cần thiết và bằng chứng hoàn tất. |
| **Thích ứng mỗi ngày** | Với tiến độ và thông tin hôm nay, bước tiếp theo nào giúp đạt Sprint Goal? | Kế hoạch điều chỉnh sau Daily Scrum hoặc khi có phát hiện quan trọng. |
| **Trách nhiệm nghề nghiệp với nhau** | Các thành viên có cùng bảo vệ kết quả thay vì đẩy việc hoặc lỗi qua lại không? | Review, phối hợp gỡ trở ngại, minh bạch tiến độ và chia sẻ kiến thức. |

Đây là **trách nhiệm tập thể của Developers**. Nó không ngụ ý tất cả phải cùng sửa một dòng mã hoặc mọi quyết định đều cần bỏ phiếu. Thành viên có thể nhận trách nhiệm triển khai các phần khác nhau, nhưng khi chất lượng hoặc tích hợp của phần sản phẩm gặp vấn đề, nhóm cần chủ động phối hợp để tạo kết quả chung.

### 2.3. Developers không chịu trách nhiệm thay tất cả vai trò khác

**Scrum Team** chịu trách nhiệm tạo một Increment **có giá trị, hữu ích** mỗi Sprint. Trong nhóm:

- **Product Owner (PO)** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả, gồm Product Goal, mô tả hạng mục, thứ tự ưu tiên và minh bạch.
- **Developers** lập kế hoạch thực hiện, chọn cách giải quyết kỹ thuật, tuân thủ DoD và điều chỉnh hằng ngày để tạo Increment.
- **Scrum Master (SM)** chịu trách nhiệm thiết lập Scrum đúng khung và về hiệu quả của Scrum Team; phục vụ cả nhóm, Product Owner và tổ chức, đồng thời thúc đẩy tháo gỡ trở ngại.

PO không nên giao chi tiết từng task cho Developers; Developers cũng không tự quyết định thay PO về ưu tiên kinh doanh hoặc đổi chính sách nghiệp vụ khi chưa có thẩm quyền. Scrum Master giúp cải thiện điều kiện làm việc nhưng không phải người duy nhất chịu trách nhiệm cho chất lượng hoặc gỡ tất cả lỗi kỹ thuật.

## 3. “Phần tăng trưởng sử dụng được” nghĩa chính xác là gì?

### 3.1. Increment có những đặc tính nào?

**Increment** là một bước tăng cụ thể tiến tới **Product Goal**. Theo Scrum Guide 2020:

- Increment **bổ sung** vào các Increment đã có.
- Mỗi Increment được **xác minh kỹ** để các Increment hoạt động cùng nhau.
- Increment phải **sử dụng được (usable)** thì mới có thể cung cấp giá trị.
- Một Sprint có thể có **nhiều Increment**.
- Increment có thể được **giao cho stakeholder trước khi Sprint kết thúc**; Sprint Review không phải cổng bắt buộc để phát hành.
- Công việc **không đáp ứng Definition of Done không được coi là một phần của Increment**.

“Sử dụng được” ở đây không nhất thiết có nghĩa **đã mở cho toàn bộ khách hàng**. Tổ chức có thể lựa chọn phát hành đến một nhóm người dùng giới hạn hoặc chờ một thời điểm thích hợp, nhưng sản phẩm phải **thực sự có khả năng vận hành trong phạm vi dự định** và đạt chuẩn DoD.

### 3.2. Phân biệt task, prototype, Increment và release

| Kết quả | Ví dụ | Điều có thể khẳng định |
| --- | --- | --- |
| **Task hoàn thành** | Một kỹ sư viết xong API tạo đăng ký và unit test. | Một công việc kỹ thuật hoàn tất, chưa chứng minh luồng đầu cuối có thể dùng. |
| **Prototype / mock** | Giao diện bấm Đăng ký với dữ liệu mô phỏng. | Có thể kiểm tra ý tưởng và trải nghiệm, chưa chứng minh hệ thống thật lưu đúng. |
| **Increment đạt DoD** | Học viên đăng ký qua giao diện thật, dữ liệu chính xác, quyền truy cập và test bắt buộc đạt. | Có thêm phần sản phẩm có thể sử dụng, tích hợp với sản phẩm hiện tại. |
| **Release / triển khai sử dụng** | Bật khả năng đó cho nhóm học viên thử nghiệm. | Increment đã được phân phối hoặc kích hoạt cho đối tượng sử dụng. |
| **Outcome được kiểm chứng** | Học viên tự đăng ký thành công, giảm yêu cầu hỗ trợ. | Có bằng chứng về giá trị thực tế, trong giới hạn dữ liệu quan sát. |

Các mức này có thể liên quan nhưng không tương đương. Một demo đẹp không thay thế kiểm thử; triển khai phần mềm không tự chứng minh người dùng nhận được lợi ích; và một Increment đã Done không phải chờ đến Sprint Review mới có thể được phát hành.

### 3.3. Increment không bắt buộc là một tính năng lớn

Một Increment có thể rất nhỏ, miễn **tăng khả năng hữu ích của sản phẩm** và đạt DoD. Ví dụ:

- Học viên đã đăng nhập có thể đăng ký **một loại khóa học miễn phí** còn chỗ, chưa hỗ trợ thanh toán hoặc danh sách chờ.
- Nhân viên hỗ trợ có thể xem trạng thái đăng ký **đúng quyền** thay vì tra cơ sở dữ liệu thủ công.
- Hệ thống khắc phục lỗi đăng ký trùng đã gây thiệt hại và có kiểm thử hồi quy.

Phần nhỏ cần có **ranh giới sử dụng minh bạch**. Không được hoãn kiểm tra quyền hoặc dữ liệu nhất quán rồi nói “phiên bản tối thiểu” để biện minh cho sản phẩm chưa an toàn.

### 3.4. Sự khác biệt giữa Increment và Sprint Goal

**Sprint Goal** là mục tiêu chung của Sprint; nó giải thích **vì sao** công việc trong Sprint có giá trị. **Increment** là kết quả sản phẩm cụ thể đã được tạo và xác minh.

Trong một Sprint, Developers có thể hoàn thành vài Increment đóng góp cho cùng Sprint Goal, nhưng chưa chắc các Increment đó đã đủ để đạt mục tiêu chung. Ngược lại, việc đánh dấu nhiều Product Backlog Items Done không tự chứng minh Sprint Goal đạt nếu chúng không tạo được khả năng mà mục tiêu mô tả.

## 4. Definition of Done: chất lượng là trách nhiệm của Developers

### 4.1. Definition of Done là gì?

**Definition of Done (DoD)** là mô tả chính thức về trạng thái của Increment khi nó đáp ứng các tiêu chuẩn chất lượng cần thiết cho sản phẩm. DoD tạo sự minh bạch: mọi người cùng hiểu **“hoàn tất” nghĩa là gì**.

Nếu tổ chức có chuẩn DoD, mọi Scrum Team phải tuân thủ chuẩn đó **tối thiểu**. Nếu không có chuẩn tổ chức, Scrum Team tạo DoD phù hợp cho sản phẩm. Khi **nhiều Scrum Team cùng làm một sản phẩm**, họ phải cùng định nghĩa và tuân thủ **một DoD chung**.

Developers chịu trách nhiệm duy trì chất lượng bằng cách tuân thủ DoD. Họ không thể tự ý bỏ kiểm thử hoặc thay đổi định nghĩa Done để làm đẹp tiến độ. Nếu một Product Backlog Item chưa đáp ứng DoD, nó **không được đưa ra như một Increment hoàn tất** và cần được xem xét lại trong Product Backlog để tiếp tục xử lý.

### 4.2. DoD khác tiêu chí chấp nhận

| Khía cạnh | Acceptance criteria — Tiêu chí chấp nhận | Definition of Done |
| --- | --- | --- |
| **Phạm vi** | Hành vi, quy tắc hoặc giới hạn của một hạng mục cụ thể. | Chuẩn chất lượng chung của Increment/sản phẩm. |
| **Ví dụ** | “Một học viên không có hai đăng ký hiệu lực cho cùng khóa”. | “Mã tích hợp, test cần thiết đạt, kiểm soát quyền được xác minh”. |
| **Mục đích** | Làm rõ điều sản phẩm phải làm trong hạng mục. | Minh bạch tiêu chuẩn hoàn tất. |
| **Tạo/làm rõ** | Developers hợp tác với PO và người có chuyên môn nghiệp vụ. | Scrum Team định nghĩa trong giới hạn chuẩn tổ chức, Developers tuân thủ khi tạo Increment. |
| **Khi không đạt** | Hành vi mong đợi chưa đúng; không thể khẳng định hạng mục hoàn tất. | Công việc chưa được coi là Increment Done. |

Hai loại tiêu chuẩn **bổ sung cho nhau**. Một hạng mục có thể qua hết happy-path acceptance criteria nhưng vẫn chưa Done vì chưa tích hợp, kiểm thử bảo mật, cập nhật hợp đồng API hoặc yêu cầu chất lượng khác.

### 4.3. Mẫu DoD minh họa cho nền tảng học trực tuyến

Nhóm có thể thảo luận một DoD thích hợp với rủi ro dự án:

- [ ] Hành vi nghiệp vụ và trường hợp lỗi bắt buộc được làm rõ, kiểm chứng.
- [ ] Mã được tích hợp vào phiên bản sản phẩm hiện hành; build và kiểm tra CI đạt.
- [ ] Kiểm thử đơn vị, tích hợp, hồi quy và các mức test cần thiết theo rủi ro đã đạt.
- [ ] Các ràng buộc bảo mật, quyền truy cập và bảo vệ dữ liệu được xác minh.
- [ ] Những vấn đề chất lượng nghiêm trọng vi phạm chính sách hoàn tất đã được xử lý.
- [ ] Tác động đến cấu hình, tài liệu API, hướng dẫn vận hành, quan sát log/metric được cập nhật khi cần.
- [ ] Increment hoạt động được trong môi trường và phạm vi sử dụng đã thống nhất.
- [ ] Kết quả có bằng chứng để nhóm và stakeholder kiểm tra; không dựa riêng vào tuyên bố “máy tôi chạy được”.

Đây **không phải danh sách bắt buộc của Scrum Guide**, mà là ví dụ để áp dụng. DoD thực tế phải phù hợp đặc điểm sản phẩm, tiêu chuẩn của tổ chức và các rủi ro. Không nhất thiết mọi thay đổi đều yêu cầu cùng một bộ kiểm thử hiệu năng đầy đủ, nhưng các kiểm soát bắt buộc không thể bỏ qua.

### 4.4. Không chuyển trách nhiệm chất lượng về cuối quy trình

Phản mẫu thường gặp:

> “Developer viết xong mã rồi; QA chưa kiểm tra là việc của QA.”

Trong Scrum, Developers có thể gồm cả người chuyên kiểm thử, nhưng **trách nhiệm tạo Increment đạt DoD là trách nhiệm chung**. Nếu một bước kiểm chứng quan trọng chưa xong, hạng mục chưa Done, dù ai đang trực tiếp kiểm tra.

Nhóm nên xây chất lượng vào luồng làm việc: làm rõ ví dụ sớm, test theo rủi ro, review mã, tích hợp thường xuyên, quan sát kết quả và sửa lỗi khi thay đổi còn nhỏ.

## 5. Developers lập Sprint Backlog như thế nào?

### 5.1. Sprint Planning tạo mục tiêu và kế hoạch chung

Trong **Sprint Planning**, Scrum Team thảo luận ba chủ đề:

1. **Vì sao Sprint này có giá trị?** Tạo **Sprint Goal**.
2. **Có thể hoàn tất điều gì trong Sprint?** Developers lựa chọn các Product Backlog Items có thể thực hiện qua trao đổi với Product Owner.
3. **Làm thế nào để biến các hạng mục được chọn thành Increment?** Developers lập kế hoạch thực hiện, có thể chia nhỏ thành công việc cụ thể.

**Sprint Backlog** là artifact bao gồm **Sprint Goal**, các Product Backlog Items được chọn và kế hoạch bàn giao Increment. Đây là **kế hoạch do Developers tạo và dành cho Developers**, được cập nhật trong Sprint.

Product Owner cung cấp mục tiêu, bối cảnh, thứ tự Product Backlog và trả lời câu hỏi nghiệp vụ. Developers cung cấp đánh giá kỹ thuật, năng lực và cách thực hiện. Scrum Master hỗ trợ Scrum được áp dụng hiệu quả. **Không ai bên ngoài Developers nên áp đặt chi tiết họ phải làm bao nhiêu Product Backlog Items hoặc ai làm từng task**.

### 5.2. Dự báo theo năng lực và bằng chứng

Developers cần xét:

- Mục tiêu Sprint và giá trị của các mục được chọn.
- Kích thước, độ phức tạp và bất định kỹ thuật.
- Năng lực sẵn có, nghỉ phép, công việc hỗ trợ/vận hành cần thiết.
- Những phụ thuộc nghiệp vụ, môi trường và liên nhóm.
- Khả năng kiểm thử, tích hợp, review và đạt DoD.
- Dữ liệu hoàn tất trước đây nếu có và còn phù hợp.

Ví dụ minh họa: ba Sprint gần đây nhóm thường tạo được 2–3 lát cắt đăng ký có kích thước tương tự mỗi Sprint. Dữ liệu đó là **đầu vào dự báo**, không phải lời bảo đảm Sprint tới cũng đạt đúng ba lát cắt. Một rủi ro API chưa rõ hoặc thành viên nghỉ phép có thể khiến cần chọn ít hơn.

**Scrum không bắt buộc story points, velocity hay một cách ước lượng cụ thể.** Developers có thể dùng độ lớn tương đối, mô tả độ phức tạp, dữ liệu cycle time hoặc kỹ thuật phù hợp để ra quyết định. Không dùng điểm số như quota để ép mọi người “nhận đủ việc”.

### 5.3. Chọn công việc để đạt một mục tiêu, không phải lấp đầy lịch

**Ví dụ yếu:** Sprint Backlog có các mục không liên quan: đổi màu trang chủ, thêm SMS, sửa dashboard, thêm một API báo cáo và xây nút đăng ký. Nhóm không nêu được một kết quả chung.

**Ví dụ có trọng tâm:** Sprint Goal là “Học viên thử nghiệm tự đăng ký được khóa học miễn phí còn chỗ và nhận xác nhận đúng”. Developers chọn các hạng mục hỗ trợ luồng này và chuẩn bị kế hoạch tích hợp–kiểm thử.

Không phải mọi hạng mục trong Sprint đều phải cùng một tính năng, nhưng **Sprint Goal cần là mục tiêu chung tạo sự gắn kết và linh hoạt**. Khi phát hiện một hạng mục phụ không còn phù hợp, Developers có cơ sở trao đổi với Product Owner thay vì cố đóng bằng mọi giá.

### 5.4. Sprint Backlog là kế hoạch sống

Sau Sprint Planning, Developers có thể:

- Thêm hoặc làm rõ các bước cần thiết để hoàn tất hạng mục.
- Tách task, thay cách phối hợp và phân chia người thực hiện.
- Cập nhật ước lượng/phụ thuộc khi học thêm về hệ thống.
- Trao đổi với Product Owner để làm rõ hoặc thương lượng phạm vi khi cần.
- Tập trung năng lực xử lý trở ngại ảnh hưởng Sprint Goal.

Sprint Backlog **không phải một hợp đồng bất biến về từng dòng việc**. Tuy nhiên, thay đổi không được làm nguy hại Sprint Goal; chất lượng không được giảm. Scrum khuyến khích thích ứng có trách nhiệm, không phải liên tục nhận thêm việc theo người yêu cầu mới nhất.

## 6. Developers điều chỉnh kế hoạch mỗi ngày

### 6.1. Daily Scrum dành cho Developers

**Daily Scrum** là sự kiện **15 phút cho Developers**, diễn ra mỗi ngày làm việc trong Sprint nhằm kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog khi cần.

Developers được chọn cấu trúc phù hợp. **Scrum Guide không bắt buộc ba câu hỏi** “hôm qua làm gì, hôm nay làm gì, có blocker không?”. Điều quan trọng là sự kiện tạo ra **kế hoạch hành động phù hợp cho công việc tiếp theo**.

Ví dụ thảo luận:

> “Luồng đăng ký đã tích hợp giao diện và API, nhưng test hai học viên tranh chỗ cuối thất bại. Để bảo vệ Sprint Goal, hôm nay hai người sẽ điều tra transaction và một người bổ sung test; bộ lọc nâng cao chưa được bắt đầu.”

Cuộc trao đổi tập trung vào **điều cần thay đổi để đạt mục tiêu**, không phải báo cáo hoạt động cá nhân cho Scrum Master hoặc quản lý.

### 6.2. Không đợi Daily Scrum mới xử lý vấn đề

Nếu pipeline hỏng lúc 10 giờ hoặc test phát hiện rủi ro dữ liệu lúc 15 giờ, Developers nên phối hợp ngay khi cần. Daily Scrum không thay thế những trao đổi chi tiết trong ngày, code review, pairing, làm rõ với Product Owner hoặc xử lý sự cố.

Khi trở ngại vượt quyền hạn, nhóm cần đưa ra thông tin cụ thể để Scrum Master hỗ trợ kết nối người có quyền hoặc yêu cầu tổ chức thay đổi điều kiện gây chậm trễ.

### 6.3. Tự quản lý không có nghĩa ai thích việc nào thì làm việc đó

Một Scrum Team tự quản lý cho phép Developers chọn ai làm gì, khi nào và cách làm như thế nào. Nhưng quyền tự chủ được định hướng bằng **Sprint Goal, Product Goal, DoD và các giới hạn của tổ chức**.

Ví dụ, một kỹ sư có kinh nghiệm giao diện thấy phần backend bị chặn có thể giúp chuẩn bị contract test, ghép cặp hoặc làm rõ dữ liệu thay vì tự mở một tính năng giao diện mới chỉ để luôn bận.

Nhóm cần **tối ưu việc hoàn tất chung**, không tối ưu lượng task mỗi cá nhân đang giữ.

## 7. Trách nhiệm nghề nghiệp lẫn nhau và cộng tác liên chức năng

### 7.1. Từ “phần việc của tôi” sang “Increment của chúng ta”

Giả sử một user story đòi hỏi giao diện, API, dữ liệu, kiểm thử và cấu hình môi trường. Nếu các chuyên môn chỉ chuyển giao tuần tự, phát hiện lỗi tích hợp đến cuối Sprint là điều dễ xảy ra.

Một cách cộng tác tốt hơn:

1. Cùng hiểu hành vi và ví dụ chấp nhận trước khi triển khai.
2. Thống nhất hợp đồng giao diện giữa các thành phần sớm.
3. Ghép cặp hoặc review khi quyết định ảnh hưởng nhiều người.
4. Tích hợp các thay đổi nhỏ thường xuyên.
5. Dùng kiểm thử và quan sát để kiểm tra cả luồng, không chỉ từng module.
6. Cùng xử lý lỗi cho tới khi Increment đạt DoD.

Điều này không buộc mọi người phải trở thành chuyên gia toàn diện; nó khuyến khích **chia sẻ hiểu biết, giảm phụ thuộc vào một cá nhân** và đặt kết quả sản phẩm lên trước ranh giới chức danh.

### 7.2. “Giữ trách nhiệm với nhau” không phải giám sát hoặc đổ lỗi

Accountability nghề nghiệp gồm:

- Báo sớm trở ngại, tiến độ thực tế và những điều chưa biết.
- Nêu phản biện kỹ thuật khi thấy nguy cơ sai hành vi hoặc giảm chất lượng.
- Review thay đổi và giúp đồng nghiệp xử lý lỗi trong phạm vi phù hợp.
- Giữ những thỏa thuận chung về DoD, coding conventions, bảo mật và hợp đồng API.
- Chủ động xin hỗ trợ và chia sẻ tri thức thay vì giấu rủi ro.
- Phản hồi cụ thể dựa trên kết quả, không quy chụp cá nhân khi hệ thống gặp vấn đề.

Ví dụ, việc một thành viên nói “phần chống đăng ký trùng chưa đủ kiểm chứng, chưa nên gọi Done” là hành vi bảo vệ tiêu chuẩn nghề nghiệp, dù nó làm thay đổi dự báo Sprint.

### 7.3. Một số cách tổ chức phối hợp

| Thực hành | Tác dụng | Lưu ý |
| --- | --- | --- |
| **Pair programming / pairing** | Chia sẻ hiểu biết, giải quyết phần khó, phát hiện lỗi sớm. | Dùng có chủ đích, không áp đặt mọi việc đều phải hai người. |
| **Code review** | Kiểm tra tính đúng đắn, dễ bảo trì và tác động liên thành phần. | Không biến một người duyệt duy nhất thành điểm nghẽn không cần thiết. |
| **Three Amigos** | Góc nhìn nghiệp vụ, phát triển, kiểm thử cùng làm rõ hành vi. | Không bắt buộc đúng ba cá nhân hay chức danh. |
| **Swarming** | Nhiều thành viên tập trung hoàn tất một hạng mục bị chặn. | Cân nhắc năng lực, chuyên môn và nhu cầu thực tế. |
| **Collective code ownership** | Giảm lệ thuộc một cá nhân khi cải tiến mã. | Vẫn cần kiểm soát review, quyền truy cập và trách nhiệm rõ. |
| **Working agreements** | Minh bạch cách phối hợp, chất lượng, thời điểm phản hồi. | Cập nhật khi nhóm học thêm; không biến thành bộ thủ tục nặng. |

Các thực hành là lựa chọn của nhóm và tổ chức, không phải thành phần bắt buộc của Scrum Guide. Điều bắt buộc về mặt trách nhiệm là **cùng tạo Increment sử dụng được**.

## 8. Chia công việc thành lát cắt giá trị có thể hoàn tất

### 8.1. Tại sao không chỉ chia theo lớp kỹ thuật?

Một kế hoạch có thể phân thành:

- Tuần 1: tạo bảng cơ sở dữ liệu.
- Tuần 2: viết API.
- Tuần 3: làm giao diện.
- Tuần 4: kiểm thử.

Trong cách làm này, mỗi tuần có thể có nhiều task Done, nhưng người dùng chưa có hành vi dùng được cho đến rất muộn. Rủi ro của hệ thống chỉ lộ ra khi các thành phần gặp nhau.

**Vertical slice (lát cắt dọc)** là một phần khả năng sản phẩm đi qua các thành phần cần thiết để người dùng thực hiện một tác vụ có ý nghĩa. Ví dụ: học viên đăng ký một khóa miễn phí, hệ thống xác nhận và lưu đúng thông tin.

~~~mermaid
flowchart LR
    A["Học viên chọn khóa còn chỗ"] --> B["Giao diện gửi yêu cầu"]
    B --> C["API kiểm tra quyền & quy tắc"]
    C --> D["Cập nhật dữ liệu nhất quán"]
    D --> E["Trả kết quả xác nhận"]
    E --> F["Kiểm chứng Increment / nhận phản hồi"]
~~~

### 8.2. Những cách chia lát cắt an toàn

| Chiều chia | Lát cắt đầu tiên | Phần có thể ưu tiên sau |
| --- | --- | --- |
| **Nhóm người dùng** | Học viên cá nhân đã đăng nhập. | Nhân viên đăng ký hộ hoặc tổ chức đặt hàng loạt. |
| **Loại giao dịch** | Khóa học miễn phí. | Thanh toán, hoàn tiền và gói học phức tạp. |
| **Kịch bản sử dụng** | Một lượt đăng ký hợp lệ và lỗi cốt lõi. | Tìm kiếm nâng cao, danh sách chờ, đề xuất khóa học. |
| **Kênh** | Website với thiết bị được hỗ trợ. | Ứng dụng di động riêng, SMS đa kênh. |
| **Phạm vi thử nghiệm** | Nhóm học viên được chọn trong điều kiện an toàn. | Mở rộng sử dụng sau khi có bằng chứng phù hợp. |

**Không được chia lát cắt bằng cách bỏ qua điều kiện tối thiểu để đúng và an toàn.** Nếu không chống được đăng ký trùng hoặc không kiểm tra quyền truy cập, đó không phải một phiên bản “tối giản nhưng hoàn tất” của luồng đã cam kết.

### 8.3. Một Increment nhỏ tốt hơn nhiều task chưa tích hợp

Lát cắt dọc giúp nhóm nhận phản hồi về hành vi thật, giảm thời gian phát hiện lỗi tích hợp và dễ thay đổi ưu tiên. Nhưng chia quá nhỏ thành các bước không thể dùng cũng không giải quyết được vấn đề. Developers cần hỏi:

- Người dùng hoặc người kiểm chứng phù hợp có thể thực hiện hành vi nào sau lát cắt này?
- Các lớp kỹ thuật cần tích hợp đã đủ chưa?
- Tiêu chí chấp nhận và DoD có thể được đáp ứng trong phạm vi thời gian?
- Có phụ thuộc hoặc rủi ro cần thử sớm không?
- Nếu phải thu hẹp, phần nào **tùy chọn** có thể hoãn mà vẫn giữ tính đúng đắn?

## 9. Ví dụ thực hành: Developers xây Increment đăng ký khóa học

### 9.1. Bối cảnh và Sprint Goal

Một Scrum Team phát triển nền tảng học trực tuyến. Product Owner nhận phản hồi rằng học viên phải liên hệ nhân viên khi muốn đăng ký lớp. Sau khi cân nhắc giá trị và rủi ro, Product Backlog được sắp xếp để ưu tiên luồng tự đăng ký đầu tiên.

**Product Goal minh họa:** Học viên có thể tự hoàn tất các bước đăng ký khóa học phổ biến, giảm phụ thuộc vào xử lý thủ công.

**Sprint Goal hai tuần minh họa:**

> “Học viên thử nghiệm có thể tự đăng ký một khóa học miễn phí còn chỗ và nhận xác nhận đáng tin cậy.”

Các giới hạn cần làm rõ:

- Học viên đã đăng nhập, khóa học miễn phí có sức chứa giới hạn.
- Một học viên chỉ có tối đa một đăng ký hiệu lực cho cùng khóa.
- Không xác nhận vượt sức chứa dù nhiều người đăng ký đồng thời.
- Người dùng không được xem/sửa dữ liệu của người khác trái quyền.
- Đáp ứng DoD chung và các chính sách an toàn của sản phẩm.

Những khả năng **chưa cần trong lát cắt này**: thanh toán, danh sách chờ, đăng ký hộ, SMS nhắc học.

### 9.2. Một user story làm cơ sở trao đổi

> Là học viên đã đăng nhập, tôi muốn đăng ký một khóa học miễn phí còn chỗ để tham gia học mà không cần nhờ nhân viên hỗ trợ.

**User story không phải một artifact bắt buộc của Scrum**. Đây là một định dạng hữu ích để Product Owner và Developers trao đổi về nhu cầu; nhóm có thể mô tả Product Backlog Item bằng cách khác miễn minh bạch và đủ rõ.

Các ví dụ chấp nhận có thể viết gần cú pháp Gherkin:

~~~gherkin
Feature: Đăng ký một khóa học miễn phí

  Scenario: Đăng ký thành công
    Given học viên A đã đăng nhập và chưa đăng ký khóa X
    And khóa X còn ít nhất một chỗ
    When A xác nhận đăng ký khóa X
    Then hệ thống lưu đúng một đăng ký hiệu lực cho A
    And A nhận được trạng thái xác nhận thành công

  Scenario: Yêu cầu lặp không tạo bản ghi trùng
    Given A đã có đăng ký hiệu lực cho khóa X
    When A gửi lại yêu cầu đăng ký khóa X
    Then hệ thống không tạo thêm đăng ký hiệu lực
    And A nhận được trạng thái đăng ký hiện tại

  Scenario: Hai học viên tranh chỗ cuối
    Given khóa X chỉ còn một chỗ
    When A và B đủ điều kiện cùng xác nhận đăng ký X
    Then tối đa một đăng ký mới được xác nhận
    And tổng đăng ký hiệu lực không vượt sức chứa X

  Scenario: Từ chối truy cập trái quyền
    Given học viên A không có quyền sửa đăng ký của B
    When A yêu cầu sửa đăng ký của B
    Then hệ thống từ chối thay đổi
~~~

Kịch bản Gherkin mô tả **hành vi mong đợi**; nó chỉ thành kiểm thử tự động khi có mã kiểm thử và chạy trong môi trường phù hợp. Scrum không bắt buộc Gherkin, nhưng nhóm cần **bằng chứng đủ tin cậy** để chứng minh hành vi đã thống nhất.

### 9.3. Developers chủ động lập kế hoạch

Nhóm có kỹ sư frontend, backend, kiểm thử và thành viên hỗ trợ hạ tầng. Developers không cần chờ Scrum Master giao việc lần lượt, mà cùng xem Sprint Goal và thỏa thuận:

| Việc cần phối hợp | Vì sao cần | Cách xác minh |
| --- | --- | --- |
| Xác nhận quy tắc chỗ trống và đăng ký lặp | Tránh hiểu sai nghiệp vụ. | PO xác nhận ví dụ và giới hạn. |
| Xây một luồng giao diện–API–dữ liệu | Có khả năng đăng ký đầu cuối. | Thử một học viên đăng ký thành công qua phiên bản tích hợp. |
| Xử lý tranh chấp chỗ cuối | Bảo vệ tính nhất quán. | Kiểm thử cạnh tranh và ràng buộc dữ liệu. |
| Bảo vệ quyền truy cập và dữ liệu | Đáp ứng chất lượng và chính sách. | Kiểm thử truy cập trái quyền, kiểm tra cấu hình phù hợp. |
| Tích hợp CI và review mã | Giảm rủi ro thay đổi chồng lấn. | Pipeline và các kiểm tra bắt buộc đạt. |
| Quan sát hành vi với học viên đại diện | Kiểm chứng khả năng sử dụng và nhu cầu. | Phản hồi từ thử nghiệm trong phạm vi cho phép. |

Đây là **kế hoạch minh họa**, không phải phân công bắt buộc theo chức danh. Developers lựa chọn cách chia việc, đồng bộ với PO về phạm vi và nhờ Scrum Master hỗ trợ tháo gỡ phụ thuộc khi cần.

### 9.4. Một rủi ro kỹ thuật cần được giải quyết đúng

Khi hai người gửi yêu cầu gần đồng thời, cách thực hiện ngây thơ:

~~~text
Nếu còn chỗ:
    thêm bản ghi đăng ký
    giảm số chỗ trống
~~~

có thể làm sai dữ liệu nếu kiểm tra và cập nhật không được bảo vệ theo cơ chế nhất quán phù hợp.

Nhóm có thể thảo luận các lựa chọn như giao dịch cơ sở dữ liệu, ràng buộc tính duy nhất, cập nhật có điều kiện, khóa phù hợp hoặc một cơ chế xử lý tập trung. Ví dụ *pseudocode SQL*, chỉ để minh họa nguyên tắc cập nhật có điều kiện:

~~~sql
-- Minh họa một bước cập nhật sức chứa; chưa phải giải pháp đầy đủ.
UPDATE course
SET reserved_count = reserved_count + 1
WHERE id = :course_id
  AND reserved_count < capacity;

-- Chỉ xác nhận đặt chỗ nếu giao dịch hợp lệ và cập nhật
-- đúng 1 hàng; cần xử lý lưu đăng ký, uniqueness,
-- rollback, retry, isolation và idempotency cùng giao dịch.
~~~

**Lưu ý:** đoạn SQL riêng lẻ **không đủ chứng minh** rằng hệ thống không đăng ký trùng hay không vượt sức chứa. Cần thiết kế toàn bộ giao dịch và kiểm tra các trường hợp cạnh tranh, lỗi mạng, retry, dữ liệu hiện có, đặc tính cơ sở dữ liệu và ràng buộc nghiệp vụ. Ví dụ chỉ cho thấy Developers cần quan tâm **tính đúng đắn đầu cuối**, không thể chỉ chạy demo một người dùng rồi coi Done.

### 9.5. Trong Sprint: phát hiện lỗi, điều chỉnh và hỗ trợ nhau

Giả sử test đồng thời thất bại. Developers cùng điều tra và cập nhật Sprint Backlog:

1. Thu thập bằng chứng lỗi, xác định điều kiện tái hiện.
2. Thảo luận phương án sửa an toàn, có thể nhờ chuyên gia cơ sở dữ liệu hỗ trợ.
3. Cập nhật kiểm thử hồi quy và kiểm thử tích hợp phù hợp.
4. Minh bạch với PO nếu công sức mới ảnh hưởng dự báo hoặc phạm vi phụ.
5. Ưu tiên hoàn tất phần chống trùng trước khi mở tính năng lọc khóa học không cần cho Sprint Goal.
6. Chỉ đóng hạng mục khi Increment đáp ứng DoD.

Việc cùng giải quyết vấn đề có thể khiến một thành viên tạm ngừng task riêng. Đây không phải “năng suất thấp” nếu nó giúp cả nhóm hoàn tất Increment đáng tin cậy.

### 9.6. Kiểm chứng Increment và phản hồi

Trước khi tuyên bố Done, Developers cần có bằng chứng ở cả:

**Chất lượng kỹ thuật:**

- Luồng đầu cuối tích hợp và hoạt động trong phạm vi đã thống nhất.
- Các trường hợp thành công, lặp, tranh chấp chỗ cuối và trái quyền được kiểm chứng.
- Các kiểm soát quan trọng theo DoD đã đạt.
- Không còn lỗi nghiêm trọng vi phạm chuẩn hoàn tất.

**Khả năng sử dụng và giá trị:**

- Học viên có thể hiểu cách đăng ký và trạng thái nhận được.
- Người dùng thử cung cấp phản hồi cho PO và Scrum Team về phần còn khó hiểu.
- Các chỉ số sử dụng, nếu đủ dữ liệu, hỗ trợ quyết định bước tiếp theo.

Một Increment đạt DoD có thể **được phát hành trước Sprint Review** nếu phù hợp chính sách. Sprint Review vẫn là cơ hội để Scrum Team và stakeholder xem kết quả Sprint, bối cảnh và điều chỉnh Product Backlog.

Nếu sản phẩm mới có code, demo hoặc test với fake service nhưng chưa đạt kiểm chứng tích hợp bắt buộc, nhóm phải nói rõ **chưa Done**; không dùng phần trăm task để che đi rủi ro.

## 10. Các thực hành kỹ thuật giúp Developers giao Increment đáng tin cậy

Scrum quy định **khung trách nhiệm và kiểm tra–thích ứng**, không bắt buộc sử dụng TDD, một pipeline CI cụ thể hay một hệ thống quản lý ticket. Developers lựa chọn các thực hành phù hợp với đặc tính sản phẩm và chuẩn tổ chức.

### 10.1. Các thực hành thường gắn với XP

| Thực hành | Hỗ trợ trách nhiệm Developers như thế nào? | Ranh giới |
| --- | --- | --- |
| **Continuous integration (CI)** | Kiểm tra tích hợp và lỗi thay đổi sớm, giảm rủi ro dồn cuối Sprint. | Pipeline xanh không tự chứng minh đúng toàn bộ nghiệp vụ. |
| **Test-driven development (TDD)** | Làm rõ hành vi khi phát triển, tạo vòng test–code–refactor ngắn. | Không thay thế kiểm thử tích hợp, trải nghiệm hay đánh giá an toàn. |
| **Pair programming** | Chia sẻ hiểu biết, phản hồi ngay về quyết định thiết kế. | Dùng phù hợp bối cảnh, không buộc mọi task phải làm cặp. |
| **Refactoring** | Duy trì cấu trúc dễ thay đổi khi yêu cầu tiến hóa. | Cần kiểm thử bảo vệ và giữ hành vi đã cam kết. |
| **Collective code ownership** | Giảm phụ thuộc chuyên gia độc quyền trên một mô-đun. | Vẫn tuân thủ quyền truy cập, review và chính sách thay đổi. |
| **Small releases / small changes** | Giảm quy mô lỗi và tăng tốc độ nhận phản hồi. | Không chia nhỏ bằng cách bỏ chất lượng hay kiểm soát bắt buộc. |

Áp dụng những kỹ thuật này là cách **đưa chất lượng vào từng bước làm**, thay vì chỉ chạy một đợt test lớn cuối Sprint.

### 10.2. Tự động hóa và kiểm thử theo rủi ro

Một chiến lược kiểm thử hợp lý có thể kết hợp:

- **Unit tests:** kiểm tra quy tắc tính toán/biến đổi dữ liệu ở phạm vi nhỏ.
- **Integration tests:** kiểm tra thành phần phối hợp thật, ví dụ API và cơ sở dữ liệu.
- **Contract tests:** xác minh tương thích giữa các dịch vụ khi có phụ thuộc.
- **End-to-end tests:** xác minh một số luồng người dùng cốt lõi.
- **Security/access tests:** kiểm tra những quyền và rủi ro quan trọng.
- **Exploratory testing:** tìm vấn đề chưa được dự đoán trong kịch bản viết sẵn.
- **Nonfunctional checks:** hiệu năng, độ tin cậy, khả năng quan sát hoặc hỗ trợ tiếp cận khi cần thiết.

Không nên đòi mọi hạng mục có số lượng test giống hệt nhau. Chọn mức kiểm chứng dựa trên **rủi ro và DoD**. Nhưng không được biến “test đã viết” thành “test đã chạy” hoặc “test giả lập đã đạt” thành “tích hợp thực đã được xác minh”.

### 10.3. Chất lượng bao gồm vận hành và khả năng thay đổi

Increment có thể đáp ứng happy path nhưng vẫn khó dùng hoặc khó vận hành nếu thiếu:

- Xử lý lỗi có thông báo rõ và khả năng thử lại an toàn.
- Phân quyền và kiểm soát dữ liệu cá nhân.
- Theo dõi lỗi, log và metric đủ phục vụ điều tra.
- Tương thích với những thành phần, Increment trước đó.
- Cập nhật tài liệu hoặc hợp đồng API chịu ảnh hưởng.
- Kiểm tra migration, rollback hoặc phương án triển khai khi có thay đổi dữ liệu.

Những điều này cần được xem xét **tương xứng với sản phẩm**, không phải áp một checklist cố định khổng lồ. Developers nên cùng Scrum Team xây DoD phản ánh điều thực sự cần để gọi một Increment là hoàn tất.

## 11. Khi có phụ thuộc và trở ngại ngoài Scrum Team

### 11.1. Minh bạch tác động, không chỉ nêu tên nhóm đang chặn

Ví dụ, bài đăng ký cần môi trường thử của dịch vụ xác nhận học viên, nhưng tài khoản CI chưa được cấp. Developers không thể tự vượt quyền truy cập. Họ có thể:

1. Mô tả mục tiêu và kiểm thử bị ảnh hưởng.
2. Chỉ rõ những kiểm chứng nào đã làm được với test double và cái nào chưa.
3. Xác định đúng người hoặc nhóm có quyền cấp môi trường.
4. Nhờ Scrum Master hỗ trợ tháo gỡ và điều phối nếu cần.
5. Cập nhật Sprint Backlog, dự báo và trao đổi với PO về tác động.
6. Kiểm chứng bằng việc test tích hợp thực sự chạy đạt trước khi đóng trở ngại.

**Đã gửi yêu cầu cấp quyền** không có nghĩa trở ngại được gỡ. Đã chạy mock thành công cũng không tự chứng minh điều kiện DoD về tích hợp đã đạt.

### 11.2. Ranh giới tự quản lý và nghĩa vụ chung

Developers được tự quyết nhiều chi tiết về cách thực hiện; tuy nhiên những quyết định ảnh hưởng API dùng chung, chính sách dữ liệu, hệ thống thanh toán hoặc an toàn production có thể cần tham vấn/phê duyệt theo chính sách tổ chức.

Tự quản lý có nghĩa **chủ động nhận diện, đề xuất phương án và làm việc với người có thẩm quyền**, không phải tự ý bỏ qua giới hạn vì mục tiêu Sprint.

### 11.3. Khi Product Owner yêu cầu đổi phạm vi giữa Sprint

Nếu PO hoặc stakeholder đề nghị thêm SMS nhắc học:

- Developers cùng PO làm rõ giá trị và tác động đến Sprint Goal.
- Đề nghị mới có thể được sắp thứ tự trên Product Backlog.
- Nếu thật sự cần đưa vào Sprint, cần thương lượng phạm vi và kế hoạch sao cho không nguy hại Sprint Goal, không hạ chất lượng.
- Điều cần thiết để sửa lỗi trong phạm vi đã cam kết hoặc đạt DoD **không bị xem là chức năng tùy chọn** để loại bỏ cho kịp hạn.

**Sprint Backlog là kế hoạch của Developers**, nhưng không được tách rời sự chịu trách nhiệm của PO về giá trị và thứ tự Product Backlog.

## 12. Đo lường đúng trách nhiệm Developers

Không nên chỉ đánh giá Developers bằng số dòng mã, số task, số story point, phần trăm sử dụng thời gian hay số giờ họp. Những con số ấy dễ thúc đẩy làm nhiều việc dở thay vì tạo Increment đáng tin cậy.

| Tín hiệu | Câu hỏi cần trả lời | Cách diễn giải |
| --- | --- | --- |
| **Increment đạt DoD** | Nhóm thực sự có thêm khả năng sử dụng nào? | Cần minh bạch ranh giới và bằng chứng; đừng đếm prototype như Increment. |
| **Tiến độ Sprint Goal** | Hành vi nào đã đóng góp cho mục tiêu chung, còn trở ngại nào? | Không suy ra từ phần trăm ticket đã đóng. |
| **Defect escape / lỗi sau phát hành** | Những vấn đề nào lọt qua kiểm chứng? | Xem mức độ nghiêm trọng, hệ thống và nguyên nhân; không dùng để đổ lỗi cá nhân. |
| **Cycle time** | Từ lúc bắt đầu hạng mục đến Done mất bao lâu? | Định nghĩa mốc rõ, phân biệt loại công việc. |
| **Work item age** | Hạng mục đang làm đã chờ bao lâu, bị chặn ở đâu? | Dùng để hỗ trợ hoàn tất, không chấm điểm năng suất cá nhân. |
| **WIP / throughput** | Có quá nhiều việc dở hoặc luồng hoàn tất chậm không? | Số lượng không đồng nghĩa giá trị; kích thước item có thể khác nhau. |
| **Tỷ lệ tích hợp và hồi quy thành công** | Nhóm có nhận phản hồi kỹ thuật đủ sớm không? | Chú ý flakiness, độ bao phủ rủi ro và thời gian khôi phục pipeline. |
| **Outcome sản phẩm** | Increment có giúp người dùng đạt kết quả mong muốn không? | Cần phối hợp PO và stakeholder; nhiều yếu tố ngoài quyền kiểm soát Developers. |

### 12.1. Minh họa báo cáo đúng bản chất

**Báo cáo dễ gây hiểu nhầm:**

> “Đã hoàn tất 12/14 task, tương đương 86%; có thể coi Sprint gần như Done.”

**Báo cáo minh bạch hơn:**

> “Luồng đăng ký một học viên đã tích hợp, nhưng kiểm thử cạnh tranh cho chỗ cuối chưa đạt. Increment đăng ký chưa đáp ứng DoD. Developers đang tập trung khắc phục giao dịch và kiểm thử lại; chức năng lọc nâng cao được trao đổi hoãn để bảo vệ Sprint Goal.”

Thông tin thứ hai giúp Scrum Team và stakeholder hiểu **điều có thể dùng, điều chưa đạt chuẩn, rủi ro và hướng xử lý**.

### 12.2. Tránh biến chỉ số thành mục tiêu sai

- **Story points/velocity** có thể hỗ trợ dự báo nhưng không phải quy tắc bắt buộc của Scrum hay thước đo năng suất cá nhân.
- **Throughput** có thể tăng nhờ chia việc nhỏ giả tạo mà không tăng giá trị.
- **Báo ít bug hơn** không chắc chất lượng tốt nếu nhóm ngừng báo lỗi.
- **Đóng ticket sớm** không tạo Increment nếu tích hợp và kiểm chứng chưa hoàn thành.

Hãy dùng chỉ số để **đặt câu hỏi và cải tiến hệ thống làm việc**. Giá trị và chất lượng phải là mục tiêu, số liệu là phương tiện học hỏi.

## 13. Các phản mẫu khiến Developers khó tạo Increment dùng được

| Phản mẫu | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| **“Code complete” được gọi là Done** | Tích hợp, kiểm thử và lỗi bị dồn sang giai đoạn sau. | Dùng DoD chung và minh bạch bằng chứng hoàn tất. |
| **QA là cổng kiểm thử riêng sau Sprint** | Increment chưa thực sự hoàn tất trong Sprint. | Xây khả năng kiểm thử vào Developers/Scrum Team và luồng Sprint. |
| **Quản lý giao từng task và tự quyết cách làm** | Developers khó tự quản lý và không sở hữu Sprint Backlog. | Developers lập, cập nhật kế hoạch; người khác hỗ trợ mục tiêu và ranh giới. |
| **Daily Scrum là buổi điểm danh báo cáo** | Không kiểm tra Sprint Goal và điều chỉnh kế hoạch. | Tập trung vào tiến độ chung, trở ngại và bước tiếp theo. |
| **Mỗi chuyên môn chỉ làm phần của mình** | Chuyển giao dài, lỗi tích hợp muộn, khó tạo Increment. | Lát cắt dọc, pairing, review, hỗ trợ nhau khi bị chặn. |
| **Tách task theo tầng, không có hành vi dùng được** | Cuối Sprint nhiều task Done nhưng ít giá trị giao được. | Chia theo hành trình/nhu cầu người dùng và tích hợp sớm. |
| **Tự hạ DoD để kịp hạn** | Đánh dấu hoàn tất sai, tăng rủi ro bảo mật và vận hành. | Giữ DoD; thương lượng phạm vi tùy chọn hoặc cập nhật dự báo. |
| **Không nêu rủi ro vì sợ ảnh hưởng tiến độ** | Scrum thiếu minh bạch nên kiểm tra–thích ứng kém. | Khuyến khích báo sớm bằng bằng chứng và giải pháp. |
| **Cố bắt đầu thêm việc khi hạng mục đang chờ test** | WIP cao, cycle time tăng, ít kết quả Done. | Swarm xử lý tắc nghẽn, giới hạn WIP phù hợp. |
| **Phát hành = Scrum Review phải phê duyệt** | Trì hoãn giá trị không cần thiết. | Phân biệt Increment Done, release và Review; tuân thủ chính sách triển khai riêng. |
| **Tự quyết thay chính sách sản phẩm** | Giải pháp có thể sai quy tắc nghiệp vụ. | Làm rõ với PO/người có thẩm quyền, giữ quyền tự quyết triển khai. |
| **Tập trung velocity thay outcome và chất lượng** | Chia việc để lấy điểm, bỏ rủi ro khó đo. | Theo dõi Increment, DoD, giá trị và độ tin cậy. |

## 14. Bài tập vận dụng và đáp án gợi ý

### Bài tập 1 — Ai chịu trách nhiệm điều gì?

Một Scrum Team xây chức năng “Học viên đăng ký khóa học” gặp các câu hỏi:

1. Hạng mục thanh toán nên nằm trước hay sau đăng ký miễn phí trong Product Backlog?
2. Developers sẽ dùng giao dịch cơ sở dữ liệu nào để chống đăng ký trùng?
3. Ai tạo và cập nhật Sprint Backlog khi tìm ra thêm việc tích hợp?
4. Ai giúp nhóm xử lý trở ngại do quy trình cấp quyền sandbox quá lâu?
5. Ai chịu trách nhiệm tuân thủ DoD khi tạo Increment?

**Gợi ý:** (1) PO chịu trách nhiệm thứ tự Product Backlog; Developers cung cấp thông tin rủi ro và công sức. (2) Developers quyết định giải pháp trong giới hạn tiêu chuẩn chung. (3) Developers. (4) Scrum Master thúc đẩy tháo gỡ, phối hợp chủ sở hữu môi trường; nhóm vẫn có trách nhiệm chủ động. (5) Developers chịu trách nhiệm tuân thủ DoD; Scrum Team cùng chịu trách nhiệm về Increment có giá trị.

### Bài tập 2 — Điều gì đã Done?

Cuối Sprint, nhóm có:

- A: Form đăng ký hiển thị đúng với dữ liệu giả.
- B: API đăng ký có unit test nhưng chưa kiểm thử cùng giao diện.
- C: Luồng đăng ký từ đầu đến cuối chạy, kiểm thử trường hợp cạnh tranh đạt và đáp ứng DoD.
- D: Tính năng mới hoạt động nhưng còn lỗi phân quyền nghiêm trọng.

**Câu hỏi:** những hạng mục nào có thể thuộc Increment hoàn tất? Tại sao?

**Gợi ý:** trong giả định trên, **C** đáp ứng điều kiện của một Increment dùng được. A là prototype hoặc phần việc thành phần; B chưa chứng minh tích hợp; D vi phạm chất lượng/an toàn. Thực tế vẫn cần kiểm tra từng item với DoD chung và các bằng chứng tương ứng.

### Bài tập 3 — Viết Sprint Goal từ danh sách task

Backlog ứng viên:

- Tạo endpoint đăng ký.
- Thêm bảng đăng ký.
- Làm giao diện chọn khóa.
- Kiểm thử đăng ký lặp và sức chứa.
- Thêm SMS nhắc học.
- Tạo dashboard thống kê.

Hãy viết **một Sprint Goal** có ích cho học viên; chọn các công việc cần thiết để tạo Increment đầu tiên và giải thích những việc có thể hoãn.

**Ví dụ đáp án:**

> “Học viên thử nghiệm có thể tự đăng ký một khóa miễn phí còn chỗ, được xác nhận chính xác và dữ liệu không bị trùng.”

Luồng đầu cuối cùng các test bảo vệ tính đúng đắn cần thiết; SMS và dashboard có thể hoãn nếu không bắt buộc cho mục tiêu, chính sách hoặc nghĩa vụ liên quan.

### Bài tập 4 — Điều chỉnh kế hoạch khi test thất bại

Đến ngày thứ sáu của Sprint hai tuần, test phát hiện hai học viên đồng thời vẫn có thể giành chỗ vượt sức chứa. Một bên liên quan đề nghị bỏ test để demo đúng ngày, còn PO muốn thêm bộ lọc nâng cao.

Hãy đề xuất:

1. Developers nên làm gì ngay?
2. Những thông tin nào cần báo PO?
3. Scrum Master có thể hỗ trợ như thế nào?
4. Vì sao không được gọi Increment là Done khi test bắt buộc chưa đạt?
5. Cách thương lượng phạm vi nào bảo vệ được Sprint Goal?

**Gợi ý:** Developers ưu tiên tái hiện và sửa lỗi, cập nhật test, kế hoạch và dự báo; báo tác động rõ với PO. Scrum Master hỗ trợ gỡ trở ngại chuyên gia/môi trường; nhóm có thể hoãn bộ lọc nâng cao nhưng không hạ DoD. Increment chỉ Done sau khi kiểm chứng hành vi bắt buộc.

### Bài tập 5 — Từ chuyển giao theo phòng ban đến lát cắt dọc

Nhóm hiện tổ chức:

> Phân tích hoàn tất rồi giao backend → backend giao frontend → frontend giao QA → QA giao vận hành. Chỉ có một đợt kiểm thử tích hợp cuối Sprint.

Hãy thiết kế cách phối hợp mới tạo ít nhất **một lát cắt dùng được trong Sprint**:

- Ai cần tham gia làm rõ ví dụ và tiêu chí?
- Khi nào nhóm thống nhất hợp đồng API và chạy kiểm thử tích hợp?
- Các công việc có thể thực hiện song song an toàn là gì?
- Khi một kỹ năng bị nghẽn, thành viên khác hỗ trợ thế nào?
- Bằng chứng nào cho thấy phần tăng trưởng đã đáp ứng DoD?

**Gợi ý:** dùng trao đổi đa góc nhìn nghiệp vụ–phát triển–kiểm thử; thống nhất contract sớm, kiểm tra liên tục; chia hành vi đầu cuối nhỏ; hạn chế WIP; tạo bằng chứng tích hợp và kiểm thử trước khi đánh dấu Done.

### Bài tập 6 — Đọc các số đo mà không đánh lừa bản thân

Một nhóm tăng số ticket đóng từ 12 lên 25 mỗi Sprint, nhưng số lỗi sản xuất tăng và các hạng mục tích hợp thường chờ ở trạng thái “Testing” nhiều ngày.

**Câu hỏi:** có thể kết luận Developers đã tạo nhiều giá trị hơn không? Nhóm nên xem thêm những tín hiệu nào?

**Gợi ý:** không. Cần xem Increment đạt DoD, mức đạt Sprint Goal, kích thước các ticket, chất lượng, thời gian chờ/cycle time, WIP và outcome người dùng. Hành động có thể là giảm WIP, cải thiện CI/test, ghép cặp và chia lát cắt đúng nghĩa.

## 15. Checklist trước khi Developers tuyên bố hoàn tất một Increment

### Trước và trong Sprint

- [ ] Developers hiểu Sprint Goal và giá trị người dùng cần tạo.
- [ ] Những Product Backlog Items được chọn phục vụ mục tiêu và phù hợp năng lực dự báo.
- [ ] Sprint Backlog do Developers tạo, minh bạch và có thể điều chỉnh.
- [ ] Các quy tắc nghiệp vụ quan trọng đã được làm rõ với PO/người có thẩm quyền.
- [ ] Công việc được chia thành những lát cắt có thể sử dụng, không chỉ theo tầng kỹ thuật.
- [ ] Rủi ro về dữ liệu, bảo mật, tích hợp và phụ thuộc được nhận diện sớm.
- [ ] Team phối hợp mỗi ngày để hoàn tất việc đang làm và xử lý trở ngại.

### Khi kiểm chứng Done

- [ ] Hành vi người dùng cốt lõi và những trường hợp lỗi bắt buộc được kiểm chứng.
- [ ] Mã, dữ liệu, giao diện, hợp đồng tích hợp hoạt động cùng nhau.
- [ ] Các kiểm thử và kiểm soát chất lượng theo DoD được thực thi và đạt.
- [ ] Không còn lỗi nghiêm trọng vi phạm tiêu chuẩn hoàn tất.
- [ ] Tài liệu/hướng dẫn vận hành và các cấu hình chịu ảnh hưởng được cập nhật khi cần.
- [ ] Phần sản phẩm thực sự **có thể sử dụng** trong phạm vi đã công bố.
- [ ] Trạng thái Done có bằng chứng, không chỉ dựa trên demo hoặc lời xác nhận.
- [ ] Nếu chưa đạt DoD, thông tin được công khai và công việc không bị gọi là Increment hoàn tất.
- [ ] Phản hồi mới được trao đổi với PO để điều chỉnh Product Backlog và kế hoạch tiếp theo.

Checklist này minh họa cách suy nghĩ; không thay thế DoD thực tế của Scrum Team và chuẩn tổ chức. Điều quan trọng là **cùng hiểu, kiểm chứng và chịu trách nhiệm cho kết quả**, không thêm biểu mẫu chỉ để hoàn thành thủ tục.

## 16. Tổng kết

**Developers trong Scrum là những người chịu trách nhiệm tạo ra mọi khía cạnh cần thiết của một Increment có thể sử dụng trong mỗi Sprint.** Bốn trách nhiệm chính thức của họ gồm: **tạo Sprint Backlog; tuân thủ Definition of Done; điều chỉnh kế hoạch hằng ngày hướng tới Sprint Goal; và giữ trách nhiệm nghề nghiệp với nhau**.

Để thực hiện tốt, Developers cần tự quản lý trong một Scrum Team liên chức năng, làm rõ yêu cầu cùng PO, chia công việc thành các lát cắt giá trị, tích hợp và kiểm thử sớm, chủ động xử lý trở ngại, minh bạch khi chưa Done và cải thiện kỹ thuật liên tục. Scrum Master hỗ trợ nhóm và tổ chức; PO dẫn dắt giá trị và thứ tự Product Backlog; nhưng **Developers không thể chuyển trách nhiệm chất lượng và lập kế hoạch Sprint cho vai trò khác**.

Kết quả cần nhìn thấy không phải chỉ là mã đã viết hoặc số ticket đã đóng, mà là **Increment tích hợp, đáng tin cậy, đạt DoD và có khả năng mang giá trị cho người dùng**. Từ kết quả thực tế và phản hồi, Scrum Team tiếp tục kiểm tra, thích ứng và tiến gần hơn tới Product Goal.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Developers** | Những người trong Scrum Team cam kết tạo bất kỳ khía cạnh nào của một Increment sử dụng được mỗi Sprint. |
| **Accountability** | Trách nhiệm giải trình chính thức của một vai trò trong Scrum. |
| **Scrum Team** | Đơn vị tự quản lý, liên chức năng gồm Product Owner, Scrum Master và Developers. |
| **Product Owner** | Người chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog. |
| **Scrum Master** | Người chịu trách nhiệm thiết lập Scrum và hiệu quả Scrum Team, hỗ trợ cả nhóm và tổ chức. |
| **Product Goal** | Cam kết về trạng thái tương lai của sản phẩm trong Product Backlog. |
| **Sprint Goal** | Cam kết về mục tiêu chung của Sprint. |
| **Sprint Backlog** | Sprint Goal, các Product Backlog Items được chọn và kế hoạch do Developers tạo. |
| **Increment** | Phần sản phẩm tăng thêm, tích hợp, xác minh và có thể sử dụng, đáp ứng DoD. |
| **Definition of Done (DoD)** | Tiêu chuẩn chất lượng chung để xác định khi Increment hoàn tất. |
| **Acceptance criteria** | Tiêu chí cụ thể làm rõ hành vi mong đợi của một backlog item. |
| **Vertical slice** | Lát cắt hành vi đi qua các thành phần cần thiết để tạo khả năng sử dụng đầu cuối. |
| **Daily Scrum** | Sự kiện 15 phút của Developers để kiểm tra tiến độ Sprint Goal và điều chỉnh kế hoạch. |
| **Cross-functional** | Có/tiếp cận đủ kỹ năng cần thiết để tạo giá trị, giảm phụ thuộc chuyển giao. |
| **Self-managing** | Tự quyết ai làm gì, khi nào và bằng cách nào trong trách nhiệm của nhóm. |
| **WIP** | Các hạng mục đã bắt đầu nhưng chưa hoàn tất. |
| **Cycle time** | Thời gian từ khi bắt đầu đến khi hoàn tất theo quy ước đo của nhóm. |


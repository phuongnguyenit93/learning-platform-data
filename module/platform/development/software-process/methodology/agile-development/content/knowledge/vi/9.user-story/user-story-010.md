# Nhận diện câu chuyện giả, công việc thuần kỹ thuật và các giới hạn của khuôn mô tả

## 1. Khi một câu có đúng khuôn nhưng vẫn không phải user story tốt

Trong phát triển phần mềm theo **Agile**, user story giúp nhóm thảo luận về **nhu cầu của một người hoặc một nhóm người** và giá trị cần tạo ra. Khuôn diễn đạt phổ biến là:

> Với vai trò là **[ai]**, tôi muốn **[khả năng]**, để **[đạt lợi ích gì]**.

Khuôn này hữu ích vì nhắc nhóm hỏi ba điều: người nhận giá trị là ai, họ cần làm gì và vì sao điều đó quan trọng. Tuy nhiên, **viết đủ ba vế không chứng minh rằng nhóm đã hiểu đúng nhu cầu**.

Xem câu sau:

> Với vai trò là cơ sở dữ liệu, tôi muốn có một chỉ mục mới để truy vấn chạy nhanh hơn.

Câu này có đủ “vai trò – mong muốn – mục đích”, nhưng cơ sở dữ liệu không phải người dùng đang có nhu cầu. Tạo chỉ mục có thể là công việc kỹ thuật rất cần thiết, song ép nó vào lời kể của “cơ sở dữ liệu” chỉ che khuất vấn đề thật: truy vấn nào đang chậm, ai bị ảnh hưởng, mức cải thiện cần đạt và rủi ro khi thay đổi là gì.

Một câu khác:

> Với vai trò là khách hàng, tôi muốn hệ thống sử dụng Redis để xem đơn hàng nhanh hơn.

Khách hàng thực sự có thể muốn xem trạng thái đơn nhanh, nhưng họ thường không yêu cầu kiến trúc Redis. Việc chỉ định công nghệ trong câu chuyện có thể làm nhóm bỏ qua những cách khác đơn giản hơn hoặc phù hợp hơn.

Những trường hợp như vậy cho thấy ba chủ đề quan trọng của bài học:

1. **Câu chuyện giả (fake user story):** mang hình thức user story nhưng không diễn đạt được nhu cầu có ý nghĩa của một người dùng hoặc bên hưởng lợi xác định.
2. **Công việc thuần kỹ thuật:** hoạt động xây dựng, cải tiến, bảo mật, vận hành hoặc nghiên cứu kỹ thuật cần được quản lý minh bạch, nhưng không nhất thiết phải được viết dưới dạng user story.
3. **Giới hạn của khuôn mô tả:** mẫu “Với vai trò là…” không thay thế trao đổi, bằng chứng, quy tắc nghiệp vụ, kiểm thử và những hình thức mô tả thích hợp khác.

Đây là một phần của tư duy **AGILE_DEVELOPMENT**: ưu tiên giá trị, học từ phản hồi sớm, giao phần mềm tăng dần và liên tục cải tiến Product Backlog. Mục tiêu không phải làm cho mọi dòng trong backlog đều giống nhau, mà là giúp nhóm **chọn đúng việc, hiểu đúng kết quả và kiểm chứng được tiến bộ**.

### Kết quả học tập

Sau bài này, người học có thể:

- Nhận diện các dấu hiệu của user story giả, mơ hồ, bị khóa sẵn giải pháp hoặc không thể kiểm chứng.
- Phân biệt nhu cầu người dùng với công việc kỹ thuật, lỗi, nghiên cứu và ràng buộc chất lượng.
- Chọn định dạng mô tả phù hợp cho từng loại hạng mục backlog mà vẫn giữ liên hệ với giá trị sản phẩm.
- Sửa một câu chuyện có vấn đề thành nhu cầu rõ ràng, các tiêu chí chấp nhận hoặc hạng mục hỗ trợ kỹ thuật phù hợp.
- Tổ chức trao đổi giữa nghiệp vụ, phát triển và kiểm thử để tránh nhầm “đúng khuôn” với “đủ hiểu”.

## 2. Bản chất của user story: cuộc trao đổi được khơi gợi bằng một thẻ ngắn

Một user story tốt mô tả **nhu cầu hoặc mục tiêu từ một góc nhìn có ý nghĩa**, với kích thước đủ nhỏ để nhóm có thể làm rõ, triển khai và đánh giá theo từng phần. Nó không cần chứa toàn bộ thiết kế, cấu trúc dữ liệu hay kịch bản kiểm thử ngay trong một câu.

Có thể hiểu user story qua mô hình **3C**:

| Thành phần | Ý nghĩa | Ví dụ với tra cứu đơn hàng |
|---|---|---|
| **Card** | Mô tả ngắn, giúp nhớ điều cần trao đổi. | “Khách hàng xem được trạng thái đơn hiện tại”. |
| **Conversation** | Nghiệp vụ, phát triển, kiểm thử và các bên liên quan thảo luận bối cảnh, quy tắc, ngoại lệ, giá trị. | Trạng thái nào được hiển thị? Thông tin từ vận chuyển chậm thì sao? Người khác có xem được đơn không? |
| **Confirmation** | Cách xác nhận nhu cầu đã được đáp ứng, thường thông qua ví dụ và tiêu chí chấp nhận. | Chủ đơn xem được trạng thái hợp lệ; dữ liệu không thuộc quyền truy cập bị bảo vệ; trạng thái thiếu cập nhật được diễn đạt phù hợp. |

Khuôn “Với vai trò là…” chỉ là một cách viết phần **Card**. Nếu không có Conversation và Confirmation, nhóm vẫn có thể bất đồng về việc “hoàn thành” nghĩa là gì.

Ví dụ một user story có hướng giá trị:

> Với vai trò là khách hàng đã đặt hàng, tôi muốn xem trạng thái đơn gần nhất để biết khi nào cần chuẩn bị nhận hàng.

Câu trên **có tiềm năng** là một user story tốt vì người dùng và kết quả mong muốn rõ hơn. Tuy vậy, nhóm vẫn cần kiểm tra:

- Khách hàng thực sự có nhu cầu theo dõi trạng thái không? Họ đang tra cứu bằng cách nào?
- Trạng thái “gần nhất” nghĩa là gì nếu hệ thống vận chuyển cập nhật chậm?
- Ai được xem dữ liệu của đơn và thông tin nào được phép hiển thị?
- Phần nào có thể bàn giao trước để nhận phản hồi?
- Cách nào cho thấy khách hàng hiểu được trạng thái và giảm nhu cầu liên hệ hỗ trợ?

**Một câu chuyện có vẻ hợp lý chưa chắc là nhu cầu đã được xác minh.** User story là cách tổ chức thảo luận và học hỏi, không phải bằng chứng độc lập về giá trị.

## 3. “Câu chuyện giả” là gì và nhận diện bằng cách nào?

**Câu chuyện giả** là cách gọi thực hành cho những dòng công việc được ép vào hình thức user story, nhưng phần “vai trò”, “mong muốn” hoặc “lợi ích” không phản ánh đúng nhu cầu, khiến người đọc khó biết phải tạo ra giá trị gì. Đây không phải thuật ngữ phân loại bắt buộc của Scrum và cũng không hàm ý người viết cố tình gian dối.

Có một số dạng thường gặp.

### 3.1. Nhân vật giả: hệ thống hoặc thành phần kỹ thuật tự xưng là người dùng

> “Với vai trò là database, tôi muốn có index cho bảng orders để tốc độ tốt hơn.”

> “Với vai trò là microservice, tôi muốn retry request để hoạt động ổn định.”

Database và microservice không phải người sử dụng có mục tiêu riêng. Nhu cầu kỹ thuật có thể chính đáng, nhưng nên ghi thành **hạng mục kỹ thuật** với mục tiêu và tiêu chí rõ ràng, hoặc liên kết với nhu cầu thật:

- Nhu cầu thật: người mua xem lịch sử đơn trong thời gian hợp lý, không phải chờ quá lâu.
- Hạng mục hỗ trợ: đánh giá và tối ưu truy vấn lịch sử đơn, có số đo trước và sau.
- Ràng buộc chất lượng: xác định mục tiêu thời gian phản hồi, tải và điều kiện đo phù hợp.

**Ngoại lệ cần phân biệt:** “người sử dụng API” có thể là một lập trình viên đối tác hoặc một nhóm tích hợp thực sự. Khi họ có công việc rõ ràng (ví dụ cần tra cứu lỗi tích hợp để xử lý giao dịch), một câu chuyện từ góc nhìn người tích hợp vẫn có thể hợp lệ. Vấn đề nằm ở việc **vai trò và nhu cầu có thật hay chỉ được đặt tên để điền vào mẫu**.

### 3.2. Lợi ích rỗng hoặc tuần hoàn

> “Với vai trò là người dùng, tôi muốn đăng nhập để có thể đăng nhập.”

> “Với vai trò là admin, tôi muốn có trang quản trị để quản trị dễ hơn.”

Các vế “để” ở đây chỉ lặp lại thao tác, không giải thích kết quả cần đạt. Có thể hỏi tiếp:

- Đăng nhập để truy cập dữ liệu riêng tư nào, trong điều kiện nào?
- Người quản trị đang gặp trở ngại gì, cần ra quyết định hoặc hoàn tất công việc gì?
- Có điều gì sẽ được cải thiện nếu đáp ứng yêu cầu?

Ví dụ sửa theo mục tiêu:

> Với vai trò là nhân viên hỗ trợ, tôi muốn tra cứu những yêu cầu còn quá hạn để ưu tiên liên hệ khách hàng trước khi cam kết phục vụ bị vi phạm.

Sự khác biệt nằm ở **công việc và giá trị cụ thể**, chưa phải ở độ dài câu.

### 3.3. Giải pháp kỹ thuật bị giấu trong mong muốn của người dùng

> “Với vai trò là khách hàng, tôi muốn website dùng Redis và CQRS để tải nhanh.”

Nếu không có bằng chứng khách hàng quan tâm tới những công nghệ này, câu chuyện đã trộn **nhu cầu** với **quyết định thiết kế**.

Một cách tách:

- User story: “Là khách hàng quay lại, tôi muốn xem đơn gần đây nhanh để xác nhận trạng thái trước khi liên hệ hỗ trợ.”
- Tiêu chí chất lượng: “Trang lịch sử đơn đạt mục tiêu thời gian phản hồi đã thống nhất dưới tải đại diện.”
- Quyết định kỹ thuật: đo nguyên nhân chậm và lựa chọn phương án tối ưu; có thể dùng chỉ mục, cache, phân trang hoặc thay đổi truy vấn nếu có bằng chứng.

Đôi khi một giải pháp cụ thể là ràng buộc hợp lệ, chẳng hạn tổ chức đã có nền tảng bắt buộc. Khi đó hãy ghi rõ **ràng buộc thiết kế và lý do**, thay vì làm như đó là mong muốn của người dùng cuối.

### 3.4. Câu quá rộng hoặc không thể biết khi nào xong

> “Với vai trò là khách hàng, tôi muốn hệ thống thương mại điện tử hoàn chỉnh để mua sắm thuận tiện.”

> “Với vai trò là người dùng, tôi muốn trải nghiệm thật tốt để hài lòng.”

Các câu này có thể mô tả **hướng sản phẩm hoặc mục tiêu lớn**, nhưng chưa đủ để nhóm làm rõ một phần có thể hoàn thành và đánh giá. Chúng có thể được chuyển thành mục tiêu sản phẩm, một nhóm hạng mục lớn hoặc giả thuyết, rồi chia nhỏ thành những khả năng cụ thể.

Ví dụ, với mục tiêu “mua sắm thuận tiện”, nhóm có thể tìm vấn đề cụ thể: xem phí vận chuyển, thay đổi số lượng, lưu địa chỉ nhận hàng, thanh toán bằng phương thức phổ biến. Mỗi phần cần tiêu chí và phản hồi riêng.

### 3.5. Câu chỉ nêu hoạt động nội bộ mà không có kết quả

> “Với vai trò là lập trình viên, tôi muốn refactor lớp OrderService để mã sạch hơn.”

**Lập trình viên là người thật**, nhưng câu này chưa mô tả rõ nhu cầu sản phẩm hoặc công việc người dùng nào đang bị cản trở. Có thể có lý do kỹ thuật hoàn toàn chính đáng: lỗi thường xuyên, thời gian sửa đổi kéo dài, thiết kế chồng chéo hoặc nguy cơ mất dữ liệu. Khi đó nên ghi một **technical enabler/refactoring item** cùng phạm vi, bằng chứng và điều kiện hoàn thành.

Không cần dựng một lợi ích người dùng trực tiếp nếu công việc mang giá trị gián tiếp như giảm rủi ro và giữ khả năng thay đổi phần mềm.

### 3.6. Một vai trò quá chung che đi bối cảnh

> “Với vai trò là user, tôi muốn nhận notification để biết thông tin.”

“User” và “thông tin” không giúp nhóm thiết kế hoặc kiểm tra. Ai cần nhận? Khi nào? Thông báo về chuyện gì? Họ phải hành động gì? Loại thông tin nào không nên gửi vì riêng tư?

Có thể cải thiện:

> Với vai trò là người mua vừa đặt hàng, tôi muốn được thông báo khi đơn đã bàn giao cho đơn vị vận chuyển để chuẩn bị nhận hàng.

Ngay cả câu này vẫn cần làm rõ kênh gửi, nội dung tối thiểu, tính đúng lúc, trạng thái không thể gửi và lựa chọn của người dùng.

## 4. Bảng chẩn đoán nhanh các loại hạng mục

Không phải mọi dòng cần sửa thành một user story “đẹp”. Một số nên chuyển sang loại mô tả khác.

| Dòng công việc ban đầu | Nhận định | Cách mô tả phù hợp hơn |
|---|---|---|
| “Là database, tôi muốn index orders để nhanh hơn.” | Nhân vật giả; thực chất công việc kỹ thuật. | Technical enabler: đo và tối ưu truy vấn lịch sử đơn, có ngưỡng chất lượng và kiểm tra không làm sai kết quả. |
| “Là người dùng, tôi muốn đăng nhập để đăng nhập.” | Lợi ích tuần hoàn. | Làm rõ ai cần truy cập chức năng nào và vì sao cần xác thực. |
| “Là khách hàng, tôi muốn Redis để xem đơn nhanh.” | Trộn nhu cầu với giải pháp. | Story về tra cứu đơn; yêu cầu hiệu năng riêng; phương án kỹ thuật dựa trên đo đạc. |
| “Là nhân viên kho, tôi muốn lọc đơn cần giao trong hôm nay để sắp xếp ca làm.” | Có người dùng, mục tiêu và lợi ích cụ thể. | Giữ làm story tiềm năng; bổ sung ví dụ và tiêu chí chấp nhận. |
| “Nâng thư viện xử lý JWT từ bản cũ để vá lỗ hổng đã xác định.” | Công việc bảo mật kỹ thuật chính đáng. | Security/maintenance item với phạm vi, cách kiểm chứng và kiểm tra hồi quy. |
| “Là người dùng, tôi muốn không bao giờ có lỗi.” | Không thể kiểm chứng theo nghĩa tuyệt đối. | Đặt các tiêu chí chất lượng và mục tiêu độ tin cậy có phạm vi, đơn vị đo, điều kiện áp dụng. |
| “Sửa lỗi thanh toán bị trừ tiền hai lần khi retry.” | Báo cáo lỗi và rủi ro nghiêm trọng. | Defect với bước tái hiện, kết quả hiện tại/mong đợi, mức ảnh hưởng và kiểm thử hồi quy. |
| “Nghiên cứu liệu cổng thanh toán có hỗ trợ hoàn tiền từng phần.” | Cần giảm bất định. | Spike có câu hỏi nghiên cứu, giới hạn thời gian, minh chứng và quyết định tiếp theo. |
| “Là đối tác tích hợp, tôi muốn mã lỗi API rõ để xử lý yêu cầu thất bại.” | Có thể là user story hợp lệ cho người dùng API thật. | Xác minh vai trò đối tác, mô tả hợp đồng lỗi và các trường hợp kiểm thử. |
| “Đảm bảo người dùng chỉ thấy dữ liệu thuộc quyền truy cập.” | Ràng buộc bảo mật áp dụng rộng. | Security requirement/DoD/tiêu chí chấp nhận liên quan; thêm công việc kỹ thuật khi cần triển khai. |

Điểm quan trọng: **hạng mục kỹ thuật không phải hạng mục vô giá trị**. Nó chỉ không nhất thiết phù hợp với văn phong mô phỏng người dùng.

## 5. Công việc thuần kỹ thuật: có giá trị nhưng cần cách quản lý riêng

Trong một sản phẩm đang phát triển, nhóm phải làm nhiều công việc người dùng không nhìn thấy trực tiếp: nâng cấp thư viện, xử lý nợ kỹ thuật, giám sát, cải thiện hiệu năng, bảo mật, chuẩn hóa dữ liệu, kiểm thử tự động, xây đường triển khai, khắc phục lỗi, nghiên cứu công nghệ.

Những công việc này có thể là **điều kiện để cung cấp giá trị**, giúp phần mềm an toàn, ổn định và dễ thay đổi. Không cần cố đặt một “người dùng tưởng tượng” cho mỗi việc. Thay vào đó, nhóm cần nêu **vì sao phải làm, kết quả mong đợi và cách kiểm chứng**.

### 5.1. Các loại công việc thường gặp

| Loại | Ví dụ | Nên ghi rõ |
|---|---|---|
| **Technical enabler** | Thêm cơ chế xử lý sự kiện an toàn để hỗ trợ hoàn tiền bất đồng bộ. | Năng lực mới được mở ra, hạng mục sản phẩm liên quan, tiêu chí kỹ thuật và phụ thuộc. |
| **Refactoring** | Tách logic tính giá đang trùng lặp ở ba luồng thanh toán. | Vấn đề hiện tại, phạm vi thay đổi, hành vi phải giữ nguyên, kiểm thử hồi quy. |
| **Infrastructure/operations** | Cấu hình cảnh báo khi hàng đợi hoàn tiền tồn quá lâu. | Mức nguy cơ, tín hiệu giám sát, hành động khi cảnh báo và thử nghiệm vận hành. |
| **Security/compliance** | Ngăn dữ liệu thanh toán nhạy cảm xuất hiện trong log. | Ràng buộc bắt buộc, phạm vi dữ liệu, phương án xác minh, bằng chứng tuân thủ khi cần. |
| **Defect** | Retry tạo hai lệnh hoàn tiền cho cùng một giao dịch. | Cách tái hiện, kết quả hiện tại/mong đợi, mức nghiêm trọng, kiểm tra sau sửa. |
| **Spike/research** | Kiểm tra khả năng cổng thanh toán trả thông tin hoàn tiền từng phần. | Câu hỏi cần trả lời, giới hạn thời gian, hiện vật đầu ra, quyết định sau nghiên cứu. |
| **Test automation** | Bổ sung kiểm thử hồi quy cho chuyển trạng thái hủy đơn. | Những lỗi muốn ngăn, trường hợp phải bao phủ, độ ổn định và khả năng chạy trong quy trình. |

Một phần trong các việc trên có thể được thực hiện **bên trong một user story** nếu nhỏ và cần thiết để story đạt Definition of Done. Một phần có thể được quản lý như Product Backlog Item riêng, ví dụ nâng cấp thư viện bảo mật ảnh hưởng toàn hệ thống hoặc spike để đánh giá rủi ro tích hợp.

Scrum **không bắt buộc mọi Product Backlog Item là user story**. Backlog là tập hợp công việc cần thiết để cải thiện sản phẩm; cách mô tả cần giúp những người liên quan hiểu, sắp xếp thứ tự và điều chỉnh khi có thêm thông tin.

### 5.2. Mẫu ghi một technical enabler minh bạch

Ví dụ sau không giả làm câu chuyện của khách hàng:

~~~text
Loại: Technical enabler
Tiêu đề: Giảm thời gian tải lịch sử đơn khi số bản ghi tăng

Bối cảnh:
  Khi dữ liệu tăng, truy vấn lịch sử đơn chậm và ảnh hưởng khả năng tra cứu
  của khách hàng. Số đo ban đầu và tập dữ liệu đại diện cần được xác nhận.

Giá trị / rủi ro:
  Cải thiện khả năng sử dụng chức năng tra cứu, giảm nguy cơ quá tải
  và giữ chi phí thay đổi ở mức phù hợp.

Phạm vi:
  Đo truy vấn hiện tại; kiểm tra kế hoạch truy vấn; tối ưu khi có bằng chứng.
  Không tự động mặc định chọn cache hoặc một công nghệ cụ thể.

Điều kiện hoàn thành:
  - Có số đo trước/sau trong môi trường và tải đã thống nhất.
  - Đáp ứng mục tiêu thời gian phản hồi phù hợp.
  - Không làm sai thứ tự, phân trang và quyền truy cập dữ liệu.
  - Kiểm thử hồi quy và hướng dẫn vận hành cần thiết đã được cập nhật.

Liên kết:
  Năng lực tra cứu đơn hàng và mục tiêu chất lượng sản phẩm liên quan.
~~~

Ở đây, hạng mục kỹ thuật được liên kết với giá trị và tiêu chuẩn chất lượng **mà không gán sai nhu cầu cho “database”**.

### 5.3. Công việc kỹ thuật có thể trở thành user story khi người dùng kỹ thuật là thật

Không phải cứ có từ “developer” trong vai trò là story giả. Một người phát triển sử dụng **SDK, API, công cụ CI, portal nội bộ hoặc hệ thống quan sát** có thể là người dùng thật.

Ví dụ:

> Với vai trò là lập trình viên đối tác tích hợp API, tôi muốn nhận mã lỗi nhất quán và hướng dẫn xử lý để tự khắc phục yêu cầu thất bại mà không phải liên hệ hỗ trợ.

Nhu cầu này có người dùng thực, hành vi quan sát được và giá trị rõ ràng. Ngược lại:

> Với vai trò là lập trình viên, tôi muốn đổi tên hàm calculateTotal thành computeTotal để mã sạch hơn.

Câu thứ hai thường là tác vụ chỉnh sửa mã; không cần khoác vào một story. **Vai trò kỹ thuật có thể là người dùng thực; điều quan trọng là loại công việc và lợi ích có được mô tả đúng không.**

## 6. Những giới hạn của khuôn “Với vai trò là...”

Khuôn ba vế giúp khởi đầu cuộc trao đổi, nhưng không giải quyết được mọi nhu cầu mô tả phần mềm.

### 6.1. Khuôn có thể khóa giải pháp quá sớm

Khi câu chuyện ghi “Tôi muốn một nút xanh ở góc trên bên phải”, nhóm có thể bỏ qua việc người dùng đang cần tìm thao tác nào và tại sao họ khó hoàn thành công việc. Điều này không có nghĩa mọi quyết định giao diện đều sai; với thiết kế đã được xác minh hoặc ràng buộc thương hiệu, vị trí và hình thức có thể là yêu cầu hợp lệ. Chỉ cần phân biệt **nhu cầu** với **ràng buộc thiết kế đã được quyết định**.

Ví dụ:

- Nhu cầu: người mua muốn sửa số lượng trước thanh toán để tránh đặt sai.
- Giải pháp dự kiến: nút cộng/trừ cạnh từng mặt hàng.
- Điều cần kiểm tra: người mua có nhận ra cách sửa không; cập nhật tổng tiền và phí có đúng không.

### 6.2. Một câu ngắn không chứa hết quy tắc và ngoại lệ

> “Là khách hàng, tôi muốn hủy đơn trước khi giao để thay đổi quyết định.”

Câu này chưa cho biết cách xử lý đơn đang đóng gói, đơn đã thanh toán, hoàn tiền một phần, thao tác lặp, sự cố mạng hay quyền truy cập. Những điều đó cần được làm rõ bằng **Conversation**, ví dụ cụ thể, tiêu chí chấp nhận, quy tắc nghiệp vụ và kiểm thử.

Không nên nhồi mọi quy tắc vào một câu dài hàng trăm chữ. User story có thể là tiêu đề dễ nhớ, còn thông tin cần thiết được ghi gần hạng mục để cả nhóm tra cứu.

### 6.3. Nhu cầu chất lượng khó diễn đạt như một tính năng riêng lẻ

Hiệu năng, độ tin cậy, khả năng tiếp cận, bảo mật, tính toàn vẹn dữ liệu và khả năng vận hành thường **cắt ngang nhiều chức năng**. Câu “Là người dùng, tôi muốn ứng dụng an toàn” chưa đủ chỉ dẫn nhóm cần làm gì và kiểm chứng như thế nào.

Cần diễn đạt thành **quality attribute, constraint, policy, Definition of Done hoặc tiêu chí chấp nhận có phạm vi**. Ví dụ:

> Với thao tác xem lịch sử đơn, hệ thống phải kiểm soát quyền truy cập để chỉ tài khoản có quyền mới xem được dữ liệu; mọi luồng truy cập liên quan được kiểm tra ở mức API và giao diện.

Hoặc:

> Trong điều kiện tải đại diện và tập dữ liệu được xác định, thời gian phản hồi trang lịch sử đơn phải đạt mục tiêu được nhóm thống nhất trước triển khai.

Thời gian, ngưỡng tải, môi trường và percentile cụ thể cần dựa vào đặc điểm sản phẩm; không nên tự đặt con số rồi trình bày như tiêu chuẩn chung của Agile.

### 6.4. Lỗi, sự cố và nghĩa vụ bắt buộc có cách diễn đạt riêng

Một defect thường cần **các bước tái hiện, hành vi thực tế, hành vi mong đợi, tác động và kiểm thử hồi quy**. Không cần ép thành “Là người dùng, tôi muốn lỗi được sửa”.

Một yêu cầu tuân thủ có thể phải được đáp ứng dù người dùng không chủ động yêu cầu. Nhóm cần ghi rõ **nguồn nghĩa vụ, phạm vi áp dụng, hạn chót và bằng chứng đáp ứng**, thay vì bịa lợi ích riêng cho một nhân vật giả.

Tương tự, một yêu cầu vận hành có thể được mô tả bằng **mức dịch vụ, cách phát hiện sự cố, quy trình khôi phục và tiêu chí chấp nhận**, không nhất thiết là story của khách hàng cuối.

### 6.5. Công việc nghiên cứu cần mục tiêu học hỏi thay vì cam kết tính năng

Khi chưa biết một API có hỗ trợ hoàn tiền từng phần hay không, nhóm chưa nên hứa sẽ bàn giao tính năng hoàn tiền từng phần trong một hạng mục thiếu bằng chứng. Một **spike** phù hợp hơn:

~~~text
Loại: Spike kỹ thuật
Câu hỏi: Nhà cung cấp thanh toán có hỗ trợ hoàn tiền từng phần không?
Giới hạn: Một khoảng thời gian nghiên cứu được nhóm thống nhất.
Hoạt động: Đọc tài liệu tích hợp, gọi sandbox, ghi các trường hợp hỗ trợ và lỗi.
Kết quả: Bằng chứng kiểm tra, giới hạn đã biết, các lựa chọn và đề xuất.
Quyết định tiếp: Chia backlog thành các phần triển khai khả thi hoặc đổi hướng.
~~~

Spike có đầu ra là **kiến thức và giảm bất định**. Không nên đánh giá nó như một chức năng sản xuất đã có thể sử dụng.

### 6.6. “Người dùng” không phải lúc nào cũng là một vai trò đơn lẻ

Một quy trình có nhiều bên có thể được mô tả phù hợp hơn bằng **use case, journey map, quy trình nghiệp vụ hoặc bảng chuyển trạng thái**. Chẳng hạn, hủy đơn liên quan khách hàng, kho, kế toán và cổng thanh toán; mỗi bên có mục tiêu và quyền hạn khác nhau.

User story có thể chia một phần giá trị trong quy trình này, nhưng bản đồ quy trình và quy tắc chuyển trạng thái giúp nhóm hiểu tác động toàn cục. **Mỗi công cụ mô tả giải quyết một góc nhìn, không có công cụ nào thay thế hoàn toàn các công cụ khác.**

## 7. Chọn định dạng phù hợp thay vì ép mọi việc thành story

| Tình huống | Cách mô tả thường phù hợp | Thông tin không nên thiếu |
|---|---|---|
| Người dùng cần khả năng mới để đạt mục tiêu | **User story** hoặc **job story** | Ai/bối cảnh, mục tiêu, giá trị, ví dụ và tiêu chí chấp nhận. |
| Quy trình nhiều vai trò, nhiều nhánh | **Use case**, sơ đồ quy trình, bảng trạng thái | Vai trò, điều kiện, luồng chính, ngoại lệ, quyền hạn. |
| Lỗi hiện có | **Bug/defect report** | Cách tái hiện, thực tế so với mong đợi, tác động, bằng chứng và kiểm tra hồi quy. |
| Cải thiện nền tảng, cấu trúc, hiệu năng | **Technical enabler/task** | Vấn đề, động cơ, phạm vi, rủi ro, cách đo/kiểm chứng, liên kết giá trị. |
| Bất định kỹ thuật hoặc nghiệp vụ | **Spike/research item** | Câu hỏi cần trả lời, giới hạn, thử nghiệm, hiện vật học hỏi. |
| Quy định bảo mật, tuân thủ, chất lượng | **Constraint, policy, quality requirement** | Phạm vi, nguồn yêu cầu, tiêu chuẩn đo và cách xác minh. |
| Giả thuyết về giá trị hoặc nhu cầu | **Hypothesis/experiment** | Giả định, phương án thử, tín hiệu thành công, cách ra quyết định. |
| Công việc kỹ thuật nhỏ nằm trong một story | **Subtask/checklist** | Người phối hợp, điều cần làm, điều kiện hoàn tất, phụ thuộc nếu có. |

**Job story** thường được viết theo mẫu:

> Khi **[tình huống]**, tôi muốn **[động lực hoặc tiến bộ cần đạt]** để **[kết quả mong muốn]**.

Ví dụ: “Khi sắp rời nhà để nhận hàng, tôi muốn biết đơn đã đến điểm giao chưa để tránh chờ vô ích.” Mẫu này nhấn mạnh **hoàn cảnh và động lực**, hữu ích khi vai trò nhân khẩu học ít quyết định hành vi.

Các định dạng không loại trừ nhau. Một hạng mục lớn có thể có user story hướng giá trị, liên kết đến quyết định kiến trúc, yêu cầu chất lượng, một vài task kỹ thuật và những kiểm thử cần thiết. Nhóm nên giữ thông tin **gọn, liên kết được và dễ cập nhật**.

## 8. Dùng INVEST như gợi ý đánh giá, không phải bộ luật hình thức

**INVEST** là bộ tiêu chí gợi ý đánh giá chất lượng một user story:

| Chữ | Ý nghĩa | Câu hỏi hữu ích khi có story đáng ngờ |
|---|---|---|
| **I — Independent** | Có thể thực hiện với ít phụ thuộc không cần thiết. | Có thể chia hoặc sắp thứ tự để giao một phần giá trị sớm hơn không? |
| **N — Negotiable** | Còn chỗ trao đổi về cách giải quyết. | Story đang mô tả nhu cầu hay khóa sẵn công nghệ và thiết kế? |
| **V — Valuable** | Mang giá trị cho người dùng hoặc bên liên quan. | Có ai nhận được lợi ích rõ ràng? Nếu là kỹ thuật, giá trị gián tiếp đã được làm rõ chưa? |
| **E — Estimable** | Có đủ hiểu biết để đánh giá nỗ lực hoặc bất định. | Có câu hỏi hoặc thử nghiệm nào phải thực hiện trước khi cam kết? |
| **S — Small** | Đủ nhỏ để hoàn thành, kiểm tra và nhận phản hồi trong nhịp làm việc phù hợp. | Có thể tách thành các lát giá trị mà vẫn giữ hành vi hữu ích không? |
| **T — Testable** | Có thể xác nhận kết quả mong đợi. | Có ví dụ hoặc tín hiệu nào phân biệt “đúng” với “sai” không? |

INVEST là **heuristic**, không phải tiêu chuẩn bắt buộc của Scrum hoặc một bài chấm điểm cứng. Một hạng mục có phụ thuộc thực tế vẫn có thể quan trọng. Một spike có thể chưa “Estimable” như tính năng thông thường nhưng có **giới hạn thời gian và mục tiêu học hỏi** rõ.

Đặc biệt, **Valuable không có nghĩa mọi hạng mục đều phải tạo doanh thu tức thời**. Công việc phòng ngừa rủi ro, sửa lỗ hổng bảo mật, cải thiện khả năng vận hành hoặc giảm nợ kỹ thuật có thể mang giá trị đáng kể dù người dùng không thấy một nút mới.

Không nên dùng INVEST để ép một technical task thành user story chỉ nhằm đạt đủ sáu chữ.

## 9. Cách chuyển một câu chuyện giả thành hạng mục đúng bản chất

Một quy trình sửa có thể thực hiện theo năm bước:

1. **Hỏi “ai thực sự bị ảnh hưởng?”** Phân biệt người dùng trực tiếp, bên vận hành, khách hàng mua sản phẩm và thành phần kỹ thuật.
2. **Hỏi “họ muốn đạt kết quả gì?”** Chuyển từ màn hình, công nghệ hoặc hoạt động nội bộ sang công việc và giá trị mong muốn.
3. **Kiểm tra bằng chứng:** vấn đề đã được quan sát, đo đạc hay mới là giả thuyết?
4. **Phân loại công việc:** user story, bug, kỹ thuật, spike, ràng buộc chất lượng hay mục tiêu lớn?
5. **Viết cách xác minh và liên kết:** dùng ví dụ/tiêu chí chấp nhận, đo lường, kiểm thử hoặc đầu ra học hỏi phù hợp.

~~~mermaid
flowchart TD
    A[Hạng mục được đề xuất] --> B{Có nhu cầu của một người hoặc nhóm thật?}
    B -->|Có| C{Có hành vi hoặc outcome kiểm chứng được?}
    C -->|Có| D[User story hoặc job story]
    C -->|Chưa rõ| E[Khám phá và làm rõ nhu cầu]
    B -->|Không hoặc chỉ là kỹ thuật| F{Bản chất công việc là gì?}
    F -->|Lỗi hiện có| G[Bug với bước tái hiện]
    F -->|Cải thiện kỹ thuật| H[Technical enabler hoặc task]
    F -->|Chưa biết cách làm| I[Spike có mục tiêu học hỏi]
    F -->|Ràng buộc| J[Quality requirement hoặc policy]
    D --> K[Ví dụ, tiêu chí và phản hồi]
    E --> K
    G --> K
    H --> K
    I --> K
    J --> K
~~~

### 9.1. Ví dụ chuyển đổi từ câu “database muốn index”

**Câu ban đầu:** “Là database, tôi muốn index cột customer_id.”

**Hỏi thêm:** Truy vấn nào chậm? Người dùng nào bị ảnh hưởng? Có số đo không? Có chắc chỉ mục là phương án tốt? Có ảnh hưởng tốc độ ghi hoặc chi phí lưu trữ?

**Cách ghi hợp lý:**

- User story liên quan: “Là khách hàng quay lại, tôi muốn mở lịch sử đơn gần đây đủ nhanh để xác nhận đơn đã mua trước khi đặt lại.”
- Hạng mục kỹ thuật: “Đo và tối ưu truy vấn lịch sử đơn theo customer_id với dữ liệu và tải đại diện.”
- Tiêu chí: “Đạt mục tiêu thời gian phản hồi được thống nhất; dữ liệu đúng, phân trang đúng, quyền truy cập không đổi; xem cả chi phí ghi và lưu trữ.”

Nếu việc thêm chỉ mục là giải pháp đã được chứng minh, nhóm vẫn có thể ghi trực tiếp một task “Tạo chỉ mục…”, kèm cơ sở kỹ thuật và kiểm chứng. **Không phải lúc nào cũng cần tạo thêm user story mới** nếu nhu cầu đã được theo dõi trong hạng mục liên quan.

### 9.2. Ví dụ chuyển đổi từ “người dùng muốn Redis”

**Câu ban đầu:** “Là khách hàng, tôi muốn Redis cache để giảm thời gian tra cứu.”

**Viết lại theo giá trị:** “Là khách hàng, tôi muốn kiểm tra trạng thái giao hàng kịp thời để biết khi nào cần nhận hàng.”

**Ràng buộc chất lượng:** phản hồi trong điều kiện đã thỏa thuận phải đủ nhanh, nhưng **dữ liệu trạng thái không được hiển thị sai theo cách gây nhầm lẫn**. Nhóm đo hệ thống trước khi chọn cache, tối ưu truy vấn, giảm số lần gọi mạng hoặc thiết kế phân trang.

Một cache có thể giúp tăng tốc nhưng cũng tạo rủi ro dữ liệu cũ; quyết định kỹ thuật phải xét cả hai mặt, không coi công nghệ là mục tiêu sản phẩm.

### 9.3. Ví dụ chuyển đổi từ “mọi người muốn không có lỗi”

**Câu ban đầu:** “Là người dùng, tôi muốn ứng dụng không bao giờ lỗi.”

**Phân loại:** mong muốn chung về độ tin cậy, chưa phải story nhỏ có thể kiểm thử theo nghĩa tuyệt đối.

**Cách xử lý:** xác định những luồng quan trọng (đặt hàng, thanh toán, tra cứu đơn), mức độ lỗi chấp nhận được, cách đo trong môi trường đại diện, quy trình phục hồi và guardrail phù hợp. Những cải tiến cần thiết có thể trở thành hạng mục kỹ thuật hoặc lỗi với độ ưu tiên tương ứng.

### 9.4. Ví dụ người dùng kỹ thuật thực sự

**Câu ban đầu:** “Là developer, tôi muốn log đẹp hơn.”

Nếu đang nói tới log nội bộ để hỗ trợ sửa một lỗi, thường nên tạo task kỹ thuật kèm mục tiêu quan sát và bảo vệ dữ liệu.

Nếu sản phẩm là một nền tảng dành cho lập trình viên, câu chuyện sau có thể hợp lệ:

> Là người vận hành dịch vụ, tôi muốn tìm được request thất bại theo correlation ID để chẩn đoán nguyên nhân khi khách báo lỗi mà không phải dò thủ công qua nhiều hệ thống.

Ở đây người vận hành là **người dùng thật của công cụ quan sát**, công việc và kết quả xác minh được. Tuy vậy vẫn cần thảo luận truy cập log, thông tin nhạy cảm, thời gian lưu và hành vi khi không tìm thấy request.

## 10. Tình huống thực hành: làm rõ backlog cho luồng thanh toán

Giả sử một nhóm đang cải thiện thanh toán trực tuyến. Sau vài buổi trao đổi, Product Backlog có bảy dòng sau:

| Mã | Mô tả được đề xuất |
|---|---|
| A | “Là customer, tôi muốn nút màu xanh thật lớn để thanh toán dễ hơn.” |
| B | “Là database, tôi muốn tăng connection pool để nhanh hơn.” |
| C | “Là khách mua hàng, tôi muốn biết tổng tiền cần trả trước khi xác nhận để tránh chi phí bất ngờ.” |
| D | “Là hệ thống, tôi muốn retry thanh toán để ổn định.” |
| E | “Sửa lỗi khi khách bấm thanh toán hai lần dẫn đến hai giao dịch.” |
| F | “Nghiên cứu SDK mới có hỗ trợ xác thực bổ sung theo yêu cầu nhà cung cấp.” |
| G | “Không ghi thông tin thanh toán nhạy cảm vào log.” |

### 10.1. Phân loại sau khi trao đổi

| Mã | Loại phù hợp | Điều cần làm rõ |
|---|---|---|
| A | Giả thuyết thiết kế hoặc nhu cầu UX chưa rõ. | Có bằng chứng nút khó tìm không? Người dùng bỏ dở vì lý do gì? Thử nghiệm khả dụng trước khi khóa màu/kích thước. |
| B | Technical task/enabler. | Kết nối nào đang nghẽn? Có số đo chờ kết nối? Tăng pool có làm quá tải database không? |
| C | User story tiềm năng hợp lệ. | Tổng tiền gồm thuế, phí vận chuyển, khuyến mại khi nào? Nếu phí thay đổi thì sao? |
| D | Technical enabler hoặc reliability requirement. | Retry khi nào an toàn, idempotency thế nào, phân biệt lỗi mạng với giao dịch đã hoàn tất ra sao? |
| E | Defect có rủi ro cao. | Bước tái hiện, ảnh hưởng tài chính, trạng thái giao dịch, kiểm tra hồi quy và ưu tiên xử lý. |
| F | Spike kỹ thuật. | Câu hỏi, môi trường kiểm tra, giới hạn thời gian và quyết định tiếp theo. |
| G | Security constraint; có thể cần task riêng. | Loại dữ liệu bị cấm, các kênh log, cách kiểm tra và nghĩa vụ áp dụng. |

Kết luận không phải “chỉ giữ dòng C và xóa phần còn lại”. Tất cả có thể quan trọng, nhưng **phải được mô tả đúng bản chất, ưu tiên theo rủi ro và liên kết với mục tiêu sản phẩm**.

### 10.2. Làm rõ story C bằng ví dụ

Story:

> Là khách mua hàng, tôi muốn nhìn thấy tổng tiền phải trả trước khi xác nhận thanh toán để có thể quyết định mua mà không gặp chi phí bất ngờ.

Các góc nhìn cần trao đổi:

- **Nghiệp vụ:** tổng tiền bao gồm những thành phần nào, lúc nào phí vận chuyển hoặc khuyến mại được xác định?
- **Phát triển:** dữ liệu giá, thuế, phí và khuyến mại lấy từ đâu; xử lý thay đổi giá giữa lúc xem và lúc xác nhận thế nào?
- **Kiểm thử:** nếu mã giảm giá hết hạn, phí giao hàng thay đổi, mạng gián đoạn hoặc nhiều tab cùng thanh toán thì sao?

Ví dụ tiêu chí chấp nhận:

1. Trước bước xác nhận, khách nhìn thấy tổng tiền và các thành phần chi phí cần thiết theo chính sách đang áp dụng.
2. Nếu một thành phần ảnh hưởng tổng tiền thay đổi trước xác nhận, hệ thống không âm thầm thu số tiền khác với số đã được khách chấp thuận.
3. Khi không thể xác định tổng tiền hợp lệ, hệ thống nêu tình trạng cần xử lý và không cho xác nhận một giao dịch có số tiền chưa rõ.
4. Người dùng chỉ nhìn thấy thông tin liên quan đến giỏ và tài khoản mà mình có quyền truy cập.

Tùy nghiệp vụ, các quy tắc thuế, chuyển đổi tiền tệ, làm tròn và hoàn tiền còn phải được mô tả riêng. **Tiêu chí chấp nhận có thể kiểm tra không có nghĩa đã mô tả hết mọi ràng buộc của toàn bộ hệ thống thanh toán.**

### 10.3. Chia nhỏ để giao tăng dần

Nhóm có thể lập thứ tự giá trị và rủi ro như sau:

1. Làm rõ và xử lý lỗi thanh toán trùng có tác động tài chính nghiêm trọng, vì đây là rủi ro không nên để kéo dài.
2. Đưa phần hiển thị tổng tiền rõ ràng vào luồng thanh toán cơ bản, cùng các kiểm tra an toàn thiết yếu.
3. Dùng spike để kiểm tra yêu cầu xác thực của SDK mới trước khi cam kết phạm vi tích hợp.
4. Đo nguyên nhân chờ kết nối và xử lý những điểm nghẽn đã được chứng minh.
5. Thử nghiệm thiết kế nút thanh toán nếu dữ liệu cho thấy người dùng khó nhận ra hoặc sử dụng thao tác.

Đây là **thứ tự minh họa**, không phải thứ tự mặc định cho mọi sản phẩm. Quyết định thực tế phụ thuộc mức độ nghiêm trọng, nghĩa vụ pháp lý, tác động người dùng, phụ thuộc kỹ thuật và năng lực nhóm.

Scrum, Kanban hay XP có thể được dùng để phối hợp công việc đó: Scrum hỗ trợ nhịp mục tiêu và phản hồi; Kanban giúp quan sát các hàng chờ và giới hạn WIP; XP cung cấp thực hành kiểm thử và tích hợp liên tục để thay đổi an toàn. **Không khung nào đòi hỏi phải giả vờ rằng tăng connection pool là một mong muốn của khách hàng.**

## 11. Cộng tác để phát hiện câu chuyện giả trước khi phát triển

Một cuộc trao đổi ngắn giữa **nghiệp vụ, phát triển và kiểm thử** có thể làm lộ điểm yếu của một story trước khi nhóm đầu tư quá nhiều. Thực hành **Three Amigos** hoặc trao đổi với ví dụ cụ thể là những cách phổ biến; không cần cố định đúng ba người hay biến nó thành một nghi thức bắt buộc.

### 11.1. Những câu hỏi nên đặt

| Góc nhìn | Câu hỏi |
|---|---|
| Nghiệp vụ / sản phẩm | Ai đang gặp vấn đề? Giá trị kỳ vọng là gì? Đây là bằng chứng hay giả định? Tại sao phải làm ngay? |
| Phát triển | Yêu cầu có chỉ định giải pháp quá sớm không? Có phụ thuộc, vấn đề dữ liệu, ràng buộc hoặc nợ kỹ thuật cần ghi riêng không? |
| Kiểm thử / chất lượng | Khi nào xem là đạt? Có trường hợp biên, lỗi, quyền truy cập hoặc thay đổi trạng thái nào chưa rõ? |
| Cả nhóm | Nên giữ là story, chia nhỏ, tạo spike, ghi bug hay tạo technical enabler? Ai có quyền quyết định điểm chưa thống nhất? |

Mục tiêu là tạo **hiểu biết chung**, không phải tìm người đã viết “sai format”. Nếu một câu chuyện được làm rõ qua trao đổi và cho phép bàn giao giá trị, nó đạt mục đích của một thẻ nhắc việc ngay cả khi không viết theo câu mẫu.

### 11.2. Ghi quyết định gần hạng mục

Một backlog item hữu ích nên cho biết:

- **Loại công việc:** story, bug, enabler, spike, constraint hoặc loại khác phù hợp.
- **Lý do cần làm:** giá trị, mức rủi ro, bằng chứng hoặc nghĩa vụ bắt buộc.
- **Kết quả cần đạt:** hành vi, chất lượng, đầu ra học hỏi hoặc sửa lỗi.
- **Cách kiểm chứng:** tiêu chí chấp nhận, số đo, kiểm thử, minh chứng hoặc quyết định tiếp theo.
- **Liên kết và phụ thuộc:** mục tiêu sản phẩm, story, hệ thống hoặc rủi ro liên quan khi cần.

Không cần đòi mọi hạng mục có một trường “business value” giả tạo. Nếu công việc là khắc phục lỗ hổng bảo mật, giá trị có thể được mô tả bằng rủi ro cần giảm và tiêu chí bảo vệ, thay vì ước lượng doanh thu bịa đặt.

## 12. Sai lầm thường gặp khi áp dụng máy móc user story

| Thói quen | Tác hại | Điều chỉnh |
|---|---|---|
| Bắt buộc mọi backlog item đều bắt đầu bằng “Với vai trò là…”. | Tạo nhân vật giả, che lấp bản chất công việc kỹ thuật. | Chọn định dạng theo loại hạng mục, giữ liên kết với mục tiêu sản phẩm. |
| Coi câu có đủ ba vế là đã sẵn sàng phát triển. | Thiếu quy tắc, ví dụ, rủi ro và tiêu chí xác minh. | Dùng Conversation và Confirmation; hỏi ngay điểm chưa rõ. |
| Viết user story từ góc nhìn database, server, hàng đợi. | Công nghệ được nhân cách hóa, giá trị không rõ. | Viết task/enabler kỹ thuật với mục tiêu và kiểm chứng cụ thể. |
| Bỏ mọi việc kỹ thuật vì “không tạo giá trị người dùng”. | Nợ kỹ thuật, lỗi và rủi ro tích tụ, giảm khả năng thích ứng. | Đánh giá giá trị gián tiếp, nghĩa vụ bảo mật, chi phí trì hoãn và tác động dài hạn. |
| Cứ gắn tên “người dùng” vào giải pháp có sẵn. | Nhóm ít khám phá phương án thay thế. | Tách vấn đề, outcome và quyết định thiết kế; kiểm tra giả định. |
| Chia story theo lớp database → API → UI rồi gọi đó là giao tăng dần. | Không có phần sử dụng được để nhận phản hồi sớm. | Khi có thể, chia theo lát giá trị dọc từ đầu đến cuối. |
| Story quá lớn nhưng vẫn cố đưa vào một Sprint. | Khó hoàn thành, tích hợp và đánh giá. | Chia theo trường hợp, quy tắc hoặc nhóm người dùng, giữ tiêu chí chất lượng. |
| Lấy story point hoặc số story đã xong làm thước đo giá trị. | Tăng số thẻ có thể không cải thiện sản phẩm. | Xem phần mềm hoàn thành, outcome, chất lượng và phản hồi thực tế. |
| Đánh đồng tiêu chí chấp nhận với toàn bộ kiểm thử. | Bỏ sót rủi ro tích hợp, an toàn và hồi quy. | Thiết kế kiểm thử theo rủi ro cùng Definition of Done. |
| Đòi mọi việc đều có “người dùng cuối” mới được ưu tiên. | Bỏ qua bên vận hành, nhà tích hợp và trách nhiệm pháp lý. | Nhận diện người hưởng lợi thực hoặc rủi ro/điều kiện bắt buộc. |

## 13. Danh sách kiểm tra trước khi nhận một user story vào kế hoạch

Khi nhìn một dòng trong backlog, có thể tự hỏi:

- [ ] Có **người hoặc nhóm người thật** được xác định đủ cụ thể, hay chỉ là tên của một thành phần hệ thống?
- [ ] Họ đang cố đạt **kết quả nào** trong bối cảnh nào? Vế “để” có nêu lợi ích thực thay vì lặp lại vế “muốn” không?
- [ ] Vấn đề dựa trên **bằng chứng hay giả thuyết**? Những điều chưa biết đã được nhận diện chưa?
- [ ] Câu chuyện mô tả **nhu cầu** hay bắt buộc giải pháp công nghệ/giao diện mà chưa có lý do rõ?
- [ ] Có thể đưa ra **ví dụ, tiêu chí chấp nhận hoặc outcome** để đánh giá không?
- [ ] Công việc có đủ nhỏ để bàn giao một phần giá trị và nhận phản hồi trong nhịp phù hợp không?
- [ ] Nếu đây là bug, technical enabler, spike hoặc ràng buộc chất lượng, định dạng mô tả khác có **trung thực và hữu ích hơn** không?
- [ ] Công việc kỹ thuật có **mục đích, rủi ro, phụ thuộc và cách kiểm chứng** đủ rõ không?
- [ ] Những quy định, yêu cầu bảo mật hoặc chất lượng bắt buộc đã được nhận diện chưa?
- [ ] Nghiệp vụ, phát triển và kiểm thử đã có đường trao đổi để giải quyết câu hỏi phát sinh chưa?

Danh sách này là công cụ hỗ trợ quyết định, **không phải cổng phê duyệt cứng**. Một hạng mục nghiên cứu có thể được đưa vào thực hiện dù đáp án đang chưa rõ, miễn là mục tiêu học hỏi, phạm vi và đầu ra đã được thống nhất.

## 14. Kết luận

**User story là công cụ tạo sự hiểu biết chung về nhu cầu và giá trị, không phải mẫu câu phải áp lên mọi công việc.** Một câu đủ “vai trò – mong muốn – lợi ích” vẫn có thể là câu chuyện giả nếu người dùng được bịa ra, lợi ích rỗng, yêu cầu khóa sẵn công nghệ hoặc không thể kiểm chứng.

Công việc thuần kỹ thuật có thể hoàn toàn cần thiết để bảo vệ chất lượng, giảm rủi ro và giữ khả năng phát triển lâu dài. Nhóm nên mô tả nó đúng bản chất — task, technical enabler, bug, spike, constraint hoặc một định dạng phù hợp — với lý do, kết quả và cách xác minh rõ ràng. Những người dùng kỹ thuật thực sự, như lập trình viên tích hợp API hoặc kỹ sư vận hành, vẫn có thể là chủ thể của user story hợp lệ.

Trong **Agile Development**, câu chuyện, backlog, Scrum, Kanban và XP đều nhằm phục vụ phản hồi sớm và bàn giao giá trị tăng dần. Vì vậy, điều cần tối ưu là **đúng nhu cầu, đúng loại công việc, quyết định minh bạch và phần mềm có thể kiểm chứng**, chứ không phải sự đồng nhất hình thức giữa mọi thẻ công việc.

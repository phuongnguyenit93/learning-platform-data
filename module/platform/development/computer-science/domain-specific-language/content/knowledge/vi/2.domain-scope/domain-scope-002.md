# Xác định bên liên quan

Khi xác định phạm vi miền cho một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), cần làm rõ ai hiểu miền nghiệp vụ, ai sẽ diễn đạt quy tắc bằng DSL, ai chịu ảnh hưởng từ kết quả thực thi và ai chịu trách nhiệm duy trì giải pháp. Những cá nhân hoặc nhóm này được gọi chung là **bên liên quan** (*stakeholders*).

Xác định bên liên quan là bước tìm ra đúng người, đúng vai trò và đúng mối quan tâm để thiết kế DSL giải quyết được vấn đề thực tế. Nếu chỉ trao đổi với người đặt hàng hoặc nhóm phát triển, DSL có thể mô hình hóa sai quy tắc nghiệp vụ, khó sử dụng trong công việc hằng ngày hoặc không đáp ứng yêu cầu vận hành và kiểm soát. Ngược lại, khi hiểu đầy đủ các bên liên quan, nhóm thiết kế có cơ sở xác định thuật ngữ, khái niệm, quy tắc, cú pháp, ngữ nghĩa và công cụ cần có.

## 1. Bên liên quan trong một dự án DSL là ai?

Bên liên quan là một cá nhân, nhóm hoặc tổ chức có thể ảnh hưởng đến dự án DSL, có quyền quyết định đối với miền nghiệp vụ, hoặc chịu tác động từ cách DSL được thiết kế và sử dụng. Họ không nhất thiết trực tiếp viết mã hay sử dụng trình biên tập DSL.

Ví dụ, trong DSL mô tả quy trình xử lý đơn hàng, nhân viên kho có thể là người thực hiện một bước của quy trình; chuyên gia nghiệp vụ giải thích quy tắc phân bổ hàng; nhân viên kiểm soát xác định điều kiện phê duyệt; kỹ sư tích hợp kết nối hệ thống kho; còn nhóm vận hành chịu trách nhiệm triển khai và giám sát môi trường chạy DSL. Tất cả đều có mối quan tâm cần được xem xét.

Một số nhóm bên liên quan thường gặp:

| Nhóm | Vai trò và mối quan tâm thường gặp |
|---|---|
| Chuyên gia miền nghiệp vụ | Hiểu thuật ngữ, chính sách, quy trình, ngoại lệ và các quy tắc chuyên ngành. Họ giúp xác nhận mô hình DSL có phản ánh đúng thực tế hay không. |
| Người dùng nghiệp vụ | Dùng DSL để mô tả cấu hình, quy tắc hoặc quy trình. Họ quan tâm đến cách diễn đạt dễ hiểu, ít sai sót và phù hợp với công việc. |
| Chuyên viên phân tích nghiệp vụ hoặc chủ sản phẩm | Thu thập nhu cầu, xác định ưu tiên, kết nối mục tiêu kinh doanh với yêu cầu của DSL và điều phối quyết định về phạm vi. |
| Nhà thiết kế DSL và kỹ sư ngôn ngữ | Xây dựng mô hình miền, cú pháp, ngữ nghĩa, kiểm tra tính hợp lệ, trình phân tích cú pháp, trình thông dịch hoặc trình biên dịch. |
| Nhà phát triển ứng dụng và nhóm tích hợp | Tích hợp DSL với ứng dụng, API, cơ sở dữ liệu hoặc hệ thống hiện có; quan tâm đến hợp đồng dữ liệu, khả năng mở rộng và xử lý lỗi. |
| Nhóm vận hành và quản trị nền tảng | Triển khai, cấu hình, giám sát, sao lưu, phân quyền và xử lý sự cố cho môi trường thực thi DSL. |
| An toàn thông tin, kiểm toán và tuân thủ | Xác định yêu cầu về quyền truy cập, bảo vệ dữ liệu, truy vết, lưu giữ hồ sơ và tuân thủ chính sách hoặc quy định. |
| Người tài trợ và người ra quyết định | Cung cấp nguồn lực, xác định mục tiêu, chấp nhận rủi ro và phê duyệt các quyết định quan trọng về phạm vi. |
| Bộ phận hỗ trợ, đào tạo và người chịu ảnh hưởng | Hỗ trợ người dùng, xây dựng tài liệu, đào tạo hoặc tiếp nhận tác động khi quy trình và công cụ thay đổi. |

Các nhóm trên chỉ là gợi ý. Một người có thể đảm nhiệm nhiều vai trò; một vai trò cũng có thể do nhiều người cùng đảm nhiệm. Vì vậy, nên ghi nhận **vai trò và trách nhiệm** thay vì chỉ ghi tên cá nhân hoặc chức danh.

### Phân biệt bên liên quan, người dùng và tác nhân

Ba khái niệm này có liên hệ nhưng không đồng nghĩa:

- **Người dùng DSL** là người trực tiếp viết, chỉnh sửa, kiểm tra hoặc chạy nội dung DSL. Người dùng có thể là chuyên viên nghiệp vụ, nhà phát triển hoặc quản trị viên.
- **Tác nhân** (*actor*) là vai trò tương tác với hệ thống trong một tình huống hoặc ca sử dụng. Tác nhân thường xuất hiện trong mô hình quy trình và tương tác.
- **Bên liên quan** có phạm vi rộng hơn: họ có thể không trực tiếp tương tác với DSL nhưng vẫn có quyền quyết định hoặc chịu ảnh hưởng. Ví dụ, bộ phận kiểm toán có thể không viết DSL nhưng cần truy xuất lịch sử thay đổi và kết quả thực thi.

Một hệ thống bên ngoài cũng không tự động là một bên liên quan. Cần xác định chủ sở hữu hoặc nhóm chịu trách nhiệm cho hệ thống đó, vì chính họ mới có thể giải thích hợp đồng tích hợp, giới hạn kỹ thuật và trách nhiệm vận hành.

## 2. Vì sao phải xác định bên liên quan từ sớm?

DSL biểu diễn một miền nghiệp vụ bằng các khái niệm và quy tắc có cấu trúc. Mỗi nhóm bên liên quan nhìn miền đó từ một góc độ khác nhau. Việc xác định họ sớm giúp nhóm thiết kế:

1. **Giới hạn đúng phạm vi miền.** Chuyên gia nghiệp vụ làm rõ hoạt động nào thuộc miền, hoạt động nào nằm ngoài phạm vi và các miền lân cận cần tích hợp.
2. **Dùng đúng ngôn ngữ của miền.** Người trực tiếp làm việc với nghiệp vụ giúp phát hiện thuật ngữ, cách gọi đồng nghĩa và những từ có nghĩa khác nhau giữa các bộ phận.
3. **Mô hình hóa đúng quy tắc và ngoại lệ.** Người thực hiện, người phê duyệt và người kiểm soát có thể chỉ ra các điều kiện, trường hợp biên và bước xử lý khi quy trình thất bại.
4. **Thiết kế DSL phù hợp với người sử dụng.** Người viết DSL cần cú pháp dễ đọc, thông báo lỗi có ý nghĩa và cách kiểm tra trước khi áp dụng.
5. **Đáp ứng yêu cầu kỹ thuật và vận hành.** Nhóm tích hợp, bảo mật và vận hành làm rõ yêu cầu về dữ liệu, quyền hạn, hiệu năng, khả năng quan sát và khôi phục.
6. **Tạo sự đồng thuận và khả năng tiếp nhận.** Người bị ảnh hưởng được tham gia sớm sẽ giúp phát hiện thay đổi quy trình, nhu cầu đào tạo và trở ngại khi triển khai.

Nếu bỏ sót một nhóm, yêu cầu quan trọng có thể chỉ xuất hiện sau khi DSL đã được xây dựng. Khi đó, việc bổ sung có thể buộc nhóm thay đổi mô hình miền, ngữ nghĩa hoặc cấu trúc chương trình DSL.

## 3. Bắt đầu từ ranh giới miền và luồng công việc

Không nên lập danh sách bên liên quan chỉ bằng cách hỏi ai đang tham gia dự án. Hãy bắt đầu từ mục tiêu và ranh giới miền đã xác định, sau đó lần theo công việc thực tế để tìm ra những người có kiến thức, quyền quyết định hoặc chịu ảnh hưởng.

### 3.1. Làm rõ mục tiêu và ranh giới

Trước tiên, viết ngắn gọn:

- Vấn đề nghiệp vụ mà DSL cần giải quyết.
- Đối tượng, quy trình, quy tắc hoặc cấu hình mà DSL sẽ biểu diễn.
- Những nội dung được đưa vào phạm vi và những nội dung được loại khỏi phạm vi.
- Các hệ thống, bộ phận hoặc miền khác có trao đổi dữ liệu với miền đang xét.

Ranh giới càng rõ, việc tìm bên liên quan càng có định hướng. Chẳng hạn, nếu DSL chỉ mô tả quy tắc phân bổ hàng trong kho, nhóm cần tìm người chịu trách nhiệm về tồn kho, vị trí lưu trữ và chính sách ưu tiên. Nhóm cũng cần xác định ai cung cấp dữ liệu đơn hàng và ai nhận kết quả phân bổ.

### 3.2. Lập bản đồ quy trình và các điểm quyết định

Vẽ hoặc mô tả các bước chính của quy trình từ đầu đến cuối. Với mỗi bước, đặt câu hỏi:

- Ai khởi tạo công việc?
- Ai thực hiện hoặc phê duyệt?
- Ai cung cấp dữ liệu đầu vào?
- Ai nhận kết quả hoặc chịu tác động?
- Ai theo dõi, xử lý ngoại lệ và giải quyết tranh chấp?
- Ai thay đổi quy tắc khi chính sách hoặc điều kiện kinh doanh thay đổi?
- Ai vận hành hệ thống hỗ trợ bước này?

Đừng chỉ xem luồng thành công. Các tình huống như dữ liệu thiếu, giao dịch bị từ chối, hết hàng, hủy yêu cầu, quá thời hạn hoặc cần phê duyệt bổ sung thường làm lộ ra những bên liên quan chưa xuất hiện trong quy trình thông thường.

### 3.3. Tìm người sở hữu quy tắc, dữ liệu và quyết định

Mỗi khái niệm quan trọng trong miền nên có người hoặc nhóm có thể giải thích và xác nhận. Ví dụ:

- Ai định nghĩa một đơn hàng được xem là hợp lệ?
- Ai sở hữu quy tắc tính phí hoặc điều kiện hoàn tiền?
- Ai chịu trách nhiệm về chất lượng dữ liệu tồn kho?
- Ai có quyền thay đổi trạng thái của một yêu cầu?
- Ai phê duyệt ngoại lệ và ai kiểm tra quyết định đó?

Những câu hỏi này giúp phân biệt người biết cách thực hiện công việc với người có thẩm quyền xác nhận chính sách. Hai vai trò có thể thuộc cùng một người, nhưng không nên mặc định như vậy.

## 4. Kỹ thuật khám phá bên liên quan

Không có một kỹ thuật duy nhất phù hợp cho mọi miền. Nên kết hợp nhiều cách để kiểm tra thông tin từ các góc độ khác nhau.

| Kỹ thuật | Cách thực hiện | Thông tin có thể thu được |
|---|---|---|
| Phỏng vấn | Trao đổi với từng vai trò về mục tiêu, công việc, quyết định, dữ liệu, khó khăn và ngoại lệ. | Kiến thức chuyên sâu, trách nhiệm thực tế, quy tắc ít được tài liệu hóa. |
| Hội thảo nghiệp vụ | Mời các nhóm liên quan cùng mô tả quy trình, thống nhất thuật ngữ và thảo luận tình huống. | Khác biệt trong cách hiểu, điểm giao tiếp giữa bộ phận và các quyết định cần đồng thuận. |
| Quan sát công việc | Quan sát người dùng thực hiện nhiệm vụ trong môi trường làm việc. | Các bước thủ công, công cụ phụ trợ, ngoại lệ và nhu cầu không được nói ra trong phỏng vấn. |
| Phân tích tài liệu | Đọc quy trình, biểu mẫu, chính sách, báo cáo, hợp đồng dữ liệu và tài liệu hệ thống. | Thuật ngữ chính thức, quy tắc được phê duyệt, trách nhiệm và ràng buộc hiện có. |
| Đi theo một tình huống cụ thể | Chọn một trường hợp từ đầu đến cuối, hỏi ai tham gia ở từng bước và điều gì xảy ra khi có lỗi. | Chuỗi phụ thuộc, tác nhân gián tiếp, điểm bàn giao và cách xử lý ngoại lệ. |
| Giới thiệu theo mạng lưới | Hỏi người đã phỏng vấn xem còn vai trò nào cần tham gia hoặc xác nhận. | Những nhóm ít xuất hiện trong sơ đồ tổ chức nhưng nắm kiến thức hoặc chịu ảnh hưởng. |

Một số câu hỏi mở hữu ích khi phỏng vấn:

- Công việc nào anh/chị cần hoàn thành trong quy trình này?
- Anh/chị dựa vào thông tin hoặc quy tắc nào để đưa ra quyết định?
- Trường hợp nào thường khiến quy trình bị dừng hoặc phải xử lý thủ công?
- Ai có quyền thay đổi quy tắc? Ai cần được thông báo khi quy tắc thay đổi?
- Kết quả của bước này được chuyển cho ai hoặc hệ thống nào?
- Điều gì sẽ gây rủi ro nếu DSL diễn đạt sai hoặc thực thi sai quy tắc?
- Anh/chị cần xem thông tin gì để tin tưởng và kiểm tra kết quả?

Nên hỏi về công việc và tình huống cụ thể thay vì chỉ hỏi người tham gia muốn có tính năng nào. Người được phỏng vấn thường mô tả giải pháp quen thuộc; nhiệm vụ của nhóm thiết kế là tìm hiểu vấn đề và nhu cầu đằng sau đề xuất đó.

## 5. Lập sổ đăng ký bên liên quan

Sau khi khám phá, ghi nhận thông tin trong một **sổ đăng ký bên liên quan** (*stakeholder register*). Tài liệu này giúp nhóm biết cần tham vấn ai, vì sao cần tham vấn và quyết định nào cần họ xác nhận.

Các trường thông tin nên có:

| Trường | Nội dung cần ghi |
|---|---|
| Vai trò hoặc nhóm | Tên vai trò nghiệp vụ hoặc nhóm chịu trách nhiệm. |
| Phạm vi trách nhiệm | Công việc, quy tắc, dữ liệu hoặc hệ thống mà vai trò sở hữu. |
| Mục tiêu và mối quan tâm | Kết quả họ cần đạt được và điều họ muốn bảo đảm. |
| Kiến thức chuyên môn | Thuật ngữ, chính sách hoặc quy trình mà họ có thể giải thích. |
| Quyền quyết định | Nội dung họ có thể phê duyệt, từ chối hoặc thay đổi. |
| Tác động từ DSL | Cách DSL hoặc việc triển khai DSL ảnh hưởng đến công việc của họ. |
| Mức độ ảnh hưởng và quan tâm | Cơ sở để xác định cách thức và tần suất tham gia. |
| Cách tham gia | Phỏng vấn, hội thảo, duyệt mô hình, kiểm thử tình huống hoặc nhận thông tin. |
| Người đại diện và liên hệ | Đầu mối phù hợp để phối hợp, nếu đã xác định. |

Không phải mọi trường đều cần chi tiết ngay từ đầu. Có thể bắt đầu bằng vai trò, trách nhiệm, mối quan tâm và cách tham gia; sau đó bổ sung khi hiểu miền sâu hơn.

### Ví dụ: DSL cho quy trình xử lý đơn hàng

Giả sử một nhóm xây dựng DSL để mô tả quy trình xử lý đơn hàng từ lúc xác nhận thanh toán đến khi giao hàng hoặc hủy đơn. Danh sách ban đầu có thể như sau:

| Bên liên quan | Mối quan tâm cần xác nhận | Ảnh hưởng đến thiết kế DSL |
|---|---|---|
| Chuyên gia xử lý đơn hàng | Điều kiện đơn hợp lệ, trạng thái và các trường hợp hủy. | Định nghĩa kiểu dữ liệu, trạng thái hợp lệ và quy tắc chuyển trạng thái. |
| Nhân viên kho | Tồn kho thực tế, giữ hàng, chọn hàng và xử lý thiếu hàng. | Biểu diễn bước kiểm tra tồn kho, giữ hàng và nhánh xử lý khi không đủ hàng. |
| Bộ phận thanh toán | Xác nhận thanh toán, hoàn tiền và đối soát. | Mô hình hóa điều kiện thanh toán, quyền thực hiện và kết quả giao dịch. |
| Chăm sóc khách hàng | Thay đổi địa chỉ, yêu cầu hủy và thông báo cho khách. | Biểu diễn sự kiện, điều kiện cho phép thay đổi và hành động thông báo. |
| Nhóm tích hợp | Trao đổi dữ liệu với hệ thống đơn hàng, kho và vận chuyển. | Xác định kiểu dữ liệu trao đổi, ánh xạ trường và cách xử lý lỗi tích hợp. |
| Nhóm bảo mật và kiểm toán | Quyền phê duyệt, lịch sử thay đổi và khả năng truy vết. | Bổ sung quy tắc phân quyền, nhật ký và thông tin kiểm toán cần lưu. |
| Nhóm vận hành nền tảng | Triển khai quy trình, giám sát, xử lý lỗi và khôi phục. | Xác định cấu hình chạy, trạng thái thực thi, log và cơ chế xử lý thất bại. |

Đoạn DSL dưới đây chỉ minh họa cách các mối quan tâm có thể dẫn đến yêu cầu ngôn ngữ; đây không phải cú pháp chuẩn:

~~~text
workflow FulfillOrder {
    when order.paymentConfirmed
    reserve inventory

    if inventory.available {
        create shipment
        notify customer
    } else {
        request replenishment
        notify order team
    }
}
~~~

Chuyên gia đơn hàng cần xác nhận thời điểm quy trình được bắt đầu. Nhân viên kho cần xác nhận ý nghĩa của việc giữ hàng và cách xác định hàng có sẵn. Chăm sóc khách hàng cần xác nhận thông báo nào được gửi trong từng nhánh. Nhóm tích hợp cần xác định dữ liệu và hệ thống thực hiện các hành động. Nhóm kiểm toán có thể yêu cầu lưu lại kết quả của từng quyết định. Một cấu trúc DSL chỉ được xem là phù hợp sau khi các bên có trách nhiệm xác nhận những quy tắc liên quan.

## 6. Đánh giá mức độ ảnh hưởng và cách tham gia

Sau khi lập danh sách, nhóm cần xác định ai phải tham gia thường xuyên, ai cần được tham vấn ở các quyết định cụ thể và ai chỉ cần nhận thông tin. Có thể dùng ma trận **mức độ ảnh hưởng — mức độ quan tâm** (*power-interest matrix*) như một công cụ định hướng:

| | Quan tâm cao | Quan tâm thấp |
|---|---|---|
| Ảnh hưởng cao | Phối hợp chặt chẽ; tham gia các quyết định phạm vi, ưu tiên và phê duyệt. | Duy trì sự hài lòng; cung cấp thông tin đúng thời điểm và tham vấn khi quyết định ảnh hưởng đến trách nhiệm của họ. |
| Ảnh hưởng thấp | Cập nhật thường xuyên và tạo cơ hội phản hồi; họ có thể hiểu rõ tác động trong công việc thực tế. | Theo dõi mức độ ảnh hưởng; cung cấp thông tin phù hợp khi có thay đổi liên quan. |

Ma trận này không phải công cụ để bỏ qua nhóm có ít quyền lực. Một nhân viên trực tiếp thao tác có thể không có quyền phê duyệt nhưng lại hiểu rõ các ngoại lệ mà DSL phải hỗ trợ. Nhóm thiết kế cần cân nhắc cả mức độ bị ảnh hưởng, kiến thức chuyên môn và rủi ro nếu ý kiến của nhóm đó bị bỏ sót.

Có thể dùng thêm ma trận **ảnh hưởng — tác động** nếu muốn nhận diện người có ít quyền quyết định nhưng chịu tác động lớn. Với mỗi bên liên quan, hãy chọn hình thức tham gia phù hợp:

- **Chịu trách nhiệm thực hiện:** trực tiếp cung cấp thông tin hoặc tạo ra đầu ra công việc.
- **Chịu trách nhiệm cuối cùng:** có quyền xác nhận hoặc phê duyệt kết quả.
- **Được tham vấn:** cung cấp kiến thức hoặc phản biện trước khi quyết định.
- **Được thông báo:** nhận thông tin về quyết định và thay đổi có liên quan.

Ma trận RACI có thể hỗ trợ làm rõ trách nhiệm cho từng hoạt động. RACI thường phân biệt Responsible (người thực hiện), Accountable (người chịu trách nhiệm cuối cùng), Consulted (người được tham vấn) và Informed (người được thông báo). Nên lập RACI cho các hoạt động cụ thể như xác nhận thuật ngữ miền, phê duyệt quy tắc nghiệp vụ hoặc nghiệm thu tình huống; không nên gán một nhãn chung cho một cá nhân trong toàn bộ dự án.

## 7. Xử lý khác biệt và xung đột giữa các bên

Các bên liên quan có thể dùng cùng một từ với ý nghĩa khác nhau hoặc có mục tiêu mâu thuẫn. Ví dụ, bộ phận kinh doanh muốn linh hoạt thay đổi điều kiện ưu đãi; bộ phận tài chính muốn giới hạn chặt để kiểm soát chi phí; bộ phận vận hành muốn quy tắc ổn định và dễ giám sát.

Khi có khác biệt, nhóm thiết kế nên:

1. Ghi lại phát biểu, tình huống và vai trò đưa ra ý kiến; tránh biến một nhận xét cá nhân thành quy tắc chung.
2. Làm rõ loại yêu cầu: quy định bắt buộc, chính sách nội bộ, mục tiêu nghiệp vụ, sở thích sử dụng hay giới hạn kỹ thuật.
3. Yêu cầu các bên đưa ví dụ cụ thể, bao gồm trường hợp bình thường, trường hợp biên và trường hợp ngoại lệ.
4. Xác định người có thẩm quyền quyết định đối với từng loại quy tắc. Không để nhóm phát triển tự quyết định chính sách nghiệp vụ.
5. So sánh các phương án theo tác động, rủi ro, chi phí và khả năng thực hiện; ghi lại quyết định cùng lý do.
6. Chuyển quyết định đã thống nhất thành thuật ngữ, quy tắc hoặc ràng buộc có thể kiểm tra trong mô hình DSL.

Ví dụ, hai bộ phận có thể bất đồng về việc đơn hàng đã thanh toán có được hủy sau khi kho bắt đầu lấy hàng hay không. Nhóm cần xác định ai sở hữu chính sách hủy, trạng thái nào được xem là đã bắt đầu lấy hàng, và cần xử lý thanh toán hoặc tồn kho ra sao. Khi đã thống nhất, quy tắc phải được mô tả bằng ví dụ và kiểm thử để mọi bên hiểu cùng một nghĩa.

Không phải mọi mong muốn đều có thể đưa vào DSL. Một yêu cầu có thể nằm ngoài ranh giới miền, trái với chính sách bắt buộc hoặc không khả thi về kỹ thuật. Nhóm cần giải thích lý do, ghi nhận quyết định và chỉ ra nơi xử lý yêu cầu đó nếu nó thuộc phạm vi của một hệ thống hoặc quy trình khác.

## 8. Kiểm tra mức độ bao phủ của danh sách

Danh sách bên liên quan nên được kiểm tra bằng quy trình và các quyết định của miền, thay vì chỉ dựa vào số lượng người đã phỏng vấn. Có thể dùng các câu hỏi sau:

- Mỗi khái niệm và quy tắc cốt lõi có người đủ chuyên môn để giải thích và xác nhận không?
- Mỗi bước quan trọng có người thực hiện, người phê duyệt và người nhận kết quả đã được xác định chưa?
- Các ngoại lệ, trường hợp lỗi và tình huống cần xử lý thủ công có bên liên quan chịu trách nhiệm chưa?
- Chủ sở hữu của dữ liệu và hệ thống tích hợp đã được xác định chưa?
- Yêu cầu về bảo mật, kiểm toán, vận hành và hỗ trợ đã có đầu mối chưa?
- Người trực tiếp viết hoặc sử dụng DSL có cơ hội thử nghiệm cách diễn đạt và phản hồi chưa?
- Người chịu ảnh hưởng từ thay đổi quy trình có được tham gia hoặc được thông báo chưa?
- Với mỗi quyết định quan trọng, đã rõ ai quyết định cuối cùng và ai cần được tham vấn chưa?

Sau đó, tổ chức một buổi xác nhận danh sách với đại diện nghiệp vụ và nhóm kỹ thuật. Đề nghị họ chỉ ra vai trò còn thiếu, vai trò bị trùng, người không có quyền xác nhận hoặc những mối quan tâm chưa được đại diện. Danh sách cần được cập nhật khi phạm vi miền thay đổi hoặc khi nhóm phát hiện thêm quy trình và hệ thống liên quan.

## 9. Kết quả cần có sau bước xác định bên liên quan

Kết quả của bước này không chỉ là một danh sách tên. Một bộ đầu ra hữu ích thường gồm:

1. **Sổ đăng ký bên liên quan:** vai trò, trách nhiệm, mối quan tâm, quyền quyết định và cách tham gia.
2. **Bản đồ bên liên quan:** thể hiện quan hệ giữa các nhóm, luồng thông tin, điểm bàn giao và hệ thống liên quan.
3. **Danh sách mối quan tâm:** ghi nhận điều mỗi nhóm cần DSL bảo đảm, bao gồm các ràng buộc và rủi ro.
4. **Bảng thuật ngữ và chủ sở hữu khái niệm:** xác định ai giải thích hoặc xác nhận từng thuật ngữ quan trọng trong miền.
5. **Ma trận trách nhiệm và kế hoạch tham gia:** chỉ rõ ai thực hiện, ai phê duyệt, ai được tham vấn và ai được thông báo ở từng hoạt động.
6. **Danh sách vấn đề và quyết định còn mở:** ghi nhận khác biệt chưa giải quyết, người chịu trách nhiệm và bước tiếp theo.

Các đầu ra này là đầu vào cho việc mô hình hóa miền, xác định yêu cầu và thiết kế DSL. Chúng giúp nhóm chuyển mối quan tâm của từng bên thành những nội dung có thể xem xét, chẳng hạn kiểu dữ liệu, quy tắc, điều kiện, sự kiện, quyền hạn, thông báo lỗi, khả năng tích hợp hoặc yêu cầu vận hành.

## 10. Những sai lầm thường gặp

- **Chỉ hỏi người đặt hàng hoặc quản lý.** Họ có thể hiểu mục tiêu nhưng không nắm mọi thao tác, ngoại lệ và khó khăn trong công việc hằng ngày.
- **Đồng nhất bên liên quan với người dùng DSL.** Người kiểm toán, chủ sở hữu dữ liệu hoặc người chịu ảnh hưởng có thể không trực tiếp viết DSL nhưng vẫn có yêu cầu quan trọng.
- **Chỉ dựa vào sơ đồ tổ chức.** Vai trò thực tế và luồng quyết định có thể khác chức danh hoặc tuyến báo cáo.
- **Bỏ qua trường hợp ngoại lệ.** Danh sách thường thiếu người xử lý lỗi, tranh chấp, hủy bỏ, hoàn tác và tình huống bất thường.
- **Ghi nhận ý kiến mà không xác định thẩm quyền.** Người có kinh nghiệm không nhất thiết là người được quyền phê duyệt chính sách.
- **Để một nhóm áp đặt thuật ngữ cho toàn miền.** Cần đối chiếu cách dùng từ giữa các bộ phận và thống nhất định nghĩa rõ ràng.
- **Xem danh sách là cố định.** Khi ranh giới miền, quy trình hoặc hệ thống tích hợp thay đổi, bên liên quan cũng có thể thay đổi.
- **Mời nhiều người nhưng không có mục tiêu tham gia.** Mỗi cuộc trao đổi cần nêu rõ nội dung cần xác nhận và quyết định cần đạt được.

## 11. Quy trình thực hiện đề xuất

Có thể thực hiện bước xác định bên liên quan theo trình tự sau:

1. Viết mục tiêu và ranh giới miền của DSL.
2. Mô tả luồng công việc, quyết định, dữ liệu và các tình huống ngoại lệ trong phạm vi.
3. Liệt kê vai trò thực hiện, phê duyệt, cung cấp dữ liệu, nhận kết quả, vận hành và kiểm soát.
4. Phỏng vấn, quan sát và đối chiếu tài liệu để kiểm chứng danh sách ban đầu.
5. Ghi mối quan tâm, quyền quyết định, mức độ ảnh hưởng và cách tham gia vào sổ đăng ký.
6. Làm rõ xung đột, xác định người có thẩm quyền và lưu lại quyết định.
7. Xác nhận danh sách với đại diện các nhóm và cập nhật khi hiểu biết về miền thay đổi.

Chất lượng của bước này được thể hiện ở việc nhóm có thể trả lời rõ: **ai hiểu và sở hữu từng quy tắc của miền, ai sẽ diễn đạt hoặc sử dụng DSL, ai chịu ảnh hưởng từ kết quả, và ai có quyền xác nhận quyết định liên quan**. Khi những câu hỏi đó có câu trả lời và được ghi nhận, nhóm có nền tảng đáng tin cậy để tiếp tục xác định khái niệm, yêu cầu và phạm vi của ngôn ngữ miền đặc thù.

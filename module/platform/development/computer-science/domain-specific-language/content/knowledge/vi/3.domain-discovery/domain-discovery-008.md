# Kiểm chứng với chuyên gia

## Vì sao cần kiểm chứng miền với chuyên gia?

Khi xây dựng ngôn ngữ chuyên miền (domain-specific language, DSL), nhóm phát triển phải chuyển cách hiểu về một lĩnh vực thành khái niệm, quy tắc, cú pháp và ngữ nghĩa có thể được công cụ xử lý. Tài liệu hiện có, mô hình dữ liệu và trao đổi nội bộ cung cấp nhiều thông tin, nhưng chúng không phải lúc nào cũng phản ánh đầy đủ cách công việc thực sự diễn ra.

Chuyên gia miền (domain expert) là người có kiến thức và kinh nghiệm sâu về lĩnh vực mà DSL hỗ trợ. Họ có thể là nhân viên nghiệp vụ, chuyên viên vận hành, kế toán, kỹ sư, nhà phân tích, chuyên gia tuân thủ hoặc người thường xuyên ra quyết định trong quy trình. Kiểm chứng với chuyên gia là quá trình đưa cách hiểu, mô hình và ví dụ của nhóm phát triển trở lại cho những người am hiểu lĩnh vực xem xét, xác nhận và điều chỉnh.

Hoạt động này giúp trả lời những câu hỏi cốt lõi:

- Nhóm đã hiểu đúng các khái niệm và thuật ngữ mà người trong miền sử dụng chưa?
- Các đối tượng, vai trò, trạng thái và quan hệ trong mô hình có phản ánh công việc thực tế không?
- Quy tắc nghiệp vụ có điều kiện, ngoại lệ và giới hạn nào chưa được ghi nhận?
- Các ví dụ DSL có thể diễn đạt đúng những tình huống mà chuyên gia gặp trong thực tế không?
- Cách diễn giải của công cụ có khớp với ý định của người viết DSL không?

Nếu không kiểm chứng, nhóm có thể tạo ra một ngôn ngữ có cú pháp hợp lệ và chương trình thực thi ổn định nhưng lại mô hình hóa sai nghiệp vụ. Sai lệch này thường khó phát hiện khi chỉ kiểm tra mã nguồn hoặc kiểm thử kỹ thuật, bởi hệ thống có thể làm đúng theo một quy tắc đã được hiểu sai ngay từ đầu.

## Ai nên tham gia kiểm chứng?

Không phải lúc nào một người cũng hiểu toàn bộ miền. Trong nhiều tổ chức, kiến thức được phân bố giữa các bộ phận và vai trò khác nhau. Vì vậy, cần xác định đúng người tham gia theo từng phần của mô hình và quy trình.

Các nhóm người thường cần xem xét gồm:

- **Người trực tiếp thực hiện công việc:** mô tả các bước thực tế, công cụ đang dùng, tình huống thường gặp và thao tác ngoại lệ.
- **Người chịu trách nhiệm nghiệp vụ:** giải thích mục tiêu, chính sách, tiêu chí quyết định và kết quả mà tổ chức mong muốn.
- **Người phê duyệt hoặc quản lý:** xác nhận thẩm quyền, giới hạn, trách nhiệm và những trường hợp cần phê duyệt.
- **Chuyên gia tuân thủ, pháp lý hoặc kiểm soát:** làm rõ quy định bắt buộc, dấu vết kiểm toán, phân quyền và điều kiện không được vi phạm.
- **Người vận hành hoặc hỗ trợ:** cung cấp thông tin về lỗi thực tế, quy trình khôi phục, xử lý ngoại lệ và yêu cầu giám sát.
- **Người sử dụng DSL dự kiến:** đánh giá cách diễn đạt có dễ hiểu, đủ rõ và phù hợp với trình độ của người viết hay không.

Nhóm phát triển cũng cần có người điều phối buổi làm việc, người ghi nhận quyết định và người hiểu kiến trúc DSL để chuyển phản hồi thành thay đổi cụ thể. Những vai trò này có thể do một số thành viên kiêm nhiệm, nhưng trách nhiệm cần được xác định rõ.

### Lập bản đồ chuyên gia theo chủ đề

Trước khi tổ chức phiên kiểm chứng, hãy lập bảng thể hiện chủ đề nào cần xác nhận và ai có kiến thức phù hợp:

| Chủ đề cần xác nhận | Người phù hợp | Nội dung cần làm rõ |
|---|---|---|
| Thuật ngữ và khái niệm | Chuyên viên nghiệp vụ, người dùng thường xuyên | Cách gọi, định nghĩa, từ đồng nghĩa và phạm vi sử dụng |
| Luồng công việc | Người trực tiếp thực hiện, quản lý quy trình | Trình tự, điều kiện bắt đầu, kết quả và ngoại lệ |
| Chính sách và giới hạn | Chủ sở hữu nghiệp vụ, bộ phận kiểm soát | Điều kiện hợp lệ, quyền hạn, ngưỡng và trường hợp bị cấm |
| Dữ liệu và đơn vị | Chuyên gia dữ liệu, kế toán hoặc kỹ sư lĩnh vực | Ý nghĩa trường dữ liệu, đơn vị đo, độ chính xác và nguồn dữ liệu |
| Vận hành và phục hồi | Người vận hành, hỗ trợ | Lỗi thường gặp, xử lý thủ công, thử lại và khôi phục |
| Cách dùng DSL | Người dùng dự kiến, lập trình viên miền | Khả năng đọc, cách viết, thông báo lỗi và hỗ trợ công cụ |

Việc lập bản đồ này tránh tình trạng chỉ hỏi một người có chức danh cao rồi xem ý kiến đó là đại diện cho mọi hoạt động. Người có thẩm quyền phê duyệt chính sách có thể không nắm hết các thao tác hàng ngày; ngược lại, người thực hiện quy trình có thể không biết những giới hạn pháp lý hoặc chính sách cấp tổ chức.

## Chuẩn bị nội dung trước phiên kiểm chứng

Một phiên làm việc hiệu quả cần có mục tiêu và tài liệu đủ cụ thể để chuyên gia có thể phản hồi. Không nên chỉ trình bày một sơ đồ lớn hoặc một danh sách thuật ngữ rồi hỏi chung rằng mô hình có đúng không.

Nhóm phát triển nên chuẩn bị:

1. **Phạm vi miền:** mô tả phần công việc DSL sẽ hỗ trợ và những phần nằm ngoài phạm vi.
2. **Bảng thuật ngữ:** liệt kê từ ngữ chuẩn, định nghĩa tạm thời, thuật ngữ gần nghĩa và câu hỏi còn mở.
3. **Mô hình khái niệm:** thể hiện các đối tượng, vai trò, quan hệ, trạng thái và thuộc tính chính.
4. **Mô tả quy trình:** ghi lại các bước, điều kiện, nhánh quyết định và kết quả.
5. **Quy tắc nghiệp vụ:** nêu điều kiện, ngoại lệ, giới hạn, quyền hạn và hệ quả.
6. **Ví dụ thực tế đã ẩn dữ liệu nhạy cảm:** chọn các trường hợp điển hình, trường hợp biên và trường hợp thất bại.
7. **Biểu thức DSL thử nghiệm:** chuyển một số yêu cầu thành cú pháp dự kiến để chuyên gia có thể đọc và diễn giải.
8. **Danh sách câu hỏi chưa giải quyết:** nêu rõ điều gì chưa chắc chắn, giả định nào đang được dùng và quyết định nào cần chuyên gia xác nhận.

Tài liệu nên thể hiện trạng thái của từng nội dung, chẳng hạn *đã xác nhận*, *đang đề xuất*, *chưa rõ* hoặc *có ý kiến khác nhau*. Nhờ đó, người tham gia không nhầm một giả định của nhóm phát triển với quy tắc đã được tổ chức phê duyệt.

## Các phương pháp khai thác và kiểm chứng kiến thức

Không có một kỹ thuật duy nhất phù hợp cho mọi miền. Có thể kết hợp phỏng vấn, quan sát, hội thảo, rà soát tài liệu và diễn tập tình huống để có được bức tranh đầy đủ.

### Phỏng vấn chuyên gia

Phỏng vấn giúp tìm hiểu cách chuyên gia suy nghĩ, ra quyết định và giải quyết tình huống. Câu hỏi nên gắn với công việc cụ thể thay vì chỉ hỏi về định nghĩa trừu tượng.

Ví dụ, thay vì hỏi “Đơn hàng hợp lệ là gì?”, có thể hỏi:

- Hãy kể lại lần gần nhất anh/chị xử lý một đơn hàng.
- Anh/chị kiểm tra những thông tin nào trước khi xác nhận?
- Trường hợp nào khiến đơn hàng bị từ chối hoặc cần bổ sung dữ liệu?
- Khi khách hàng thay đổi yêu cầu sau khi thanh toán, quy trình xử lý ra sao?
- Có trường hợp nào quy tắc thông thường không được áp dụng không?

Các câu hỏi theo tình huống thường giúp chuyên gia nhớ đến điều kiện và ngoại lệ cụ thể. Người phỏng vấn nên hỏi tiếp về lý do, dữ liệu đầu vào, kết quả và người chịu trách nhiệm ở từng bước.

### Quan sát công việc thực tế

Quan sát cho phép nhóm thấy những thao tác và quyết định có thể không xuất hiện trong tài liệu. Người thực hiện đôi khi bỏ qua việc mô tả các bước đã trở thành thói quen, chẳng hạn kiểm tra một màn hình khác, hỏi đồng nghiệp hoặc xử lý thủ công khi hệ thống không đáp ứng.

Khi quan sát, cần ghi lại:

- Sự kiện hoặc yêu cầu khởi đầu công việc.
- Dữ liệu và công cụ mà người thực hiện sử dụng.
- Các bước chính và nhánh quyết định.
- Những thông tin được kiểm tra nhưng không thể hiện trên biểu mẫu.
- Trường hợp phải dừng, chuyển cấp hoặc xử lý ngoài hệ thống.
- Kết quả cuối cùng và cách xác nhận kết quả.

Việc quan sát cần tuân thủ quy định của tổ chức về quyền riêng tư, bảo mật và quyền truy cập dữ liệu. Ví dụ sử dụng trong tài liệu DSL nên được ẩn danh hoặc thay thế bằng dữ liệu giả khi có thông tin cá nhân hay bí mật kinh doanh.

### Hội thảo mô hình hóa chung

Hội thảo giúp nhiều vai trò cùng xây dựng hoặc xem xét một mô hình. Nhóm có thể dùng thẻ khái niệm, sơ đồ, bảng trạng thái hoặc các ví dụ trên màn hình để mọi người chỉ ra điểm chưa thống nhất.

Một cách làm hữu ích là yêu cầu mỗi người mô tả cùng một quy trình từ góc nhìn của mình, sau đó so sánh các mô tả. Khác biệt có thể cho thấy một quy tắc chưa rõ, một thuật ngữ đang được dùng theo nhiều nghĩa hoặc một ranh giới trách nhiệm chưa được xác định.

Người điều phối cần khuyến khích cả ý kiến trái chiều và ghi lại lý do. Mục tiêu không phải đạt đồng thuận thật nhanh mà là làm lộ ra những khác biệt có ảnh hưởng đến mô hình và cách DSL vận hành.

### Rà soát tài liệu và dữ liệu hiện có

Hợp đồng, biểu mẫu, quy trình vận hành, bảng tính, báo cáo, hướng dẫn nội bộ, nhật ký sự cố và cấu hình hệ thống cũ đều có thể cung cấp bằng chứng về thuật ngữ và quy tắc. Tuy nhiên, tài liệu có thể lỗi thời hoặc phản ánh cách triển khai cũ thay vì chính sách hiện hành.

Khi sử dụng tài liệu, cần hỏi ai tạo ra nó, khi nào được cập nhật, phạm vi áp dụng là gì và ai có thẩm quyền xác nhận. Đối chiếu tài liệu với cách làm thực tế giúp phát hiện chênh lệch giữa quy định trên giấy và hoạt động hàng ngày.

### Diễn tập tình huống và ví dụ cụ thể

Một mô hình thường dễ kiểm chứng hơn khi được đặt vào tình huống. Hãy chọn một trường hợp bình thường, một trường hợp có ngoại lệ và một trường hợp không hợp lệ. Đề nghị chuyên gia mô tả đầu vào, các quyết định, kết quả và lý do.

Ví dụ với quy trình hoàn tiền:

- Đơn hàng đã thanh toán và có một mặt hàng bị hỏng.
- Đơn hàng mới chỉ được tạo nhưng chưa thu tiền.
- Một phần tiền đã được hoàn trước đó và người dùng gửi thêm yêu cầu.
- Người yêu cầu không có quyền phê duyệt hoàn tiền.

Qua các tình huống này, nhóm có thể xác định liệu thuật ngữ “hoàn tiền” có bao gồm việc hủy giao dịch chưa thu tiền hay không, cách tính số tiền còn được hoàn và ai có quyền thực hiện.

## Kiểm chứng từ thuật ngữ đến quy tắc nghiệp vụ

Kiểm chứng nên diễn ra ở nhiều mức độ. Một thuật ngữ có thể nghe hợp lý nhưng vẫn chưa đủ rõ để trở thành thành phần của DSL. Cần đi từ định nghĩa, quan hệ, vòng đời đến điều kiện và hệ quả.

### Xác nhận định nghĩa và cách sử dụng thuật ngữ

Với mỗi thuật ngữ quan trọng, hãy yêu cầu chuyên gia:

- Diễn giải bằng lời của họ.
- Đưa ra ví dụ thuộc phạm vi thuật ngữ.
- Nêu một trường hợp gần giống nhưng không thuộc phạm vi.
- Xác định các từ khác đang được dùng thay thế.
- Nêu rõ thuật ngữ có ý nghĩa khác trong bộ phận hoặc ngữ cảnh khác hay không.

Ví dụ, nếu thuật ngữ là “khách hàng đang hoạt động”, cần hỏi tiêu chí cụ thể là có tài khoản chưa khóa, có đăng nhập gần đây hay có giao dịch trong một khoảng thời gian. Những cách hiểu này không thể tự động thay thế cho nhau.

### Xác nhận quan hệ giữa các khái niệm

Một mô hình miền thường chứa các quan hệ như một khách hàng có nhiều đơn hàng, một đơn hàng có nhiều dòng hàng, một khoản thanh toán gắn với một nghĩa vụ hoặc một chuyến giao hàng có nhiều điểm dừng.

Hãy xác nhận:

- Một đối tượng có thể liên kết với bao nhiêu đối tượng khác?
- Quan hệ có bắt buộc hay tùy chọn?
- Khi một đối tượng bị xóa, đối tượng liên quan được xử lý thế nào?
- Quan hệ có thay đổi theo trạng thái hoặc thời gian không?
- Có trường hợp ngoại lệ nào làm thay đổi quy tắc thông thường không?

Các câu trả lời ảnh hưởng đến kiểu dữ liệu, cấu trúc tham chiếu, thao tác và kiểm tra hợp lệ trong DSL.

### Xác nhận trạng thái và chuyển trạng thái

Tên trạng thái cần được gắn với điều kiện vào, điều kiện ra và hành động hợp lệ. Có thể sử dụng bảng chuyển trạng thái để chuyên gia xem xét:

| Trạng thái hiện tại | Sự kiện hoặc hành động | Trạng thái tiếp theo | Điều kiện cần xác nhận |
|---|---|---|---|
| `DRAFT` | Gửi đơn | `SUBMITTED` | Các trường bắt buộc đã đầy đủ |
| `SUBMITTED` | Chấp nhận đơn | `CONFIRMED` | Đơn đáp ứng chính sách bán hàng |
| `CONFIRMED` | Ghi nhận thanh toán | `PAID` | Thanh toán được xác nhận thành công |
| `CONFIRMED` | Hủy đơn | `CANCELLED` | Chưa phát sinh điều kiện ngăn hủy |
| `PAID` | Hoàn tất giao hàng | `DELIVERED` | Có xác nhận giao nhận phù hợp |

Bảng trên chỉ là ví dụ khởi đầu. Chuyên gia cần xác nhận trạng thái, sự kiện và điều kiện thực tế. Có thể có thêm trạng thái chờ, thất bại, hoàn một phần, giao một phần hoặc tranh chấp. Cần làm rõ những chuyển tiếp nào không được phép và cách xử lý khi sự kiện đến sai thứ tự.

### Xác nhận điều kiện, ngoại lệ và giới hạn

Một quy tắc nghiệp vụ cần có điều kiện áp dụng và hệ quả đủ rõ. Ví dụ “đơn hàng được miễn phí vận chuyển” phải được làm rõ theo khu vực, loại sản phẩm, giá trị đơn, hạng khách hàng, khối lượng hoặc chương trình đang áp dụng.

Đối với từng quy tắc, hãy hỏi:

- Điều kiện nào phải đúng đồng thời và điều kiện nào chỉ cần một trong số đó đúng?
- Giá trị biên có được chấp nhận không? Ví dụ tổng tiền bằng đúng ngưỡng tối thiểu.
- Nếu thiếu dữ liệu thì xử lý thế nào?
- Quy tắc có ngoại lệ theo vai trò, thời gian, khu vực hoặc loại giao dịch không?
- Nếu hai quy tắc cùng áp dụng nhưng cho kết quả khác nhau, quy tắc nào ưu tiên?
- Ai có quyền thay đổi hoặc ghi đè kết quả tự động?

Không nên biến một câu mô tả chung thành biểu thức DSL trước khi các điều kiện này được xác định.

## Kiểm chứng biểu thức DSL với chuyên gia

Sau khi có mô hình miền và quy tắc ban đầu, nhóm có thể tạo các biểu thức DSL thử nghiệm. Đây là cách kiểm chứng quan trọng vì chuyên gia sẽ thấy ngôn ngữ dự kiến được dùng như thế nào, thay vì chỉ xem sơ đồ khái niệm.

### Yêu cầu chuyên gia diễn giải biểu thức

Đưa một đoạn DSL cho chuyên gia đọc và hỏi họ hiểu hệ thống sẽ làm gì. Hãy so sánh cách diễn giải đó với ý định của người thiết kế. Nếu chuyên gia hiểu khác, cần xác định nguyên nhân nằm ở tên gọi, cấu trúc, toán tử, phạm vi áp dụng hay thiếu thông tin ngữ cảnh.

Ví dụ DSL giả định:

```text
RULE "Free shipping"
WHEN order.total >= 1000000
  AND customer.segment IS "VIP"
THEN shipment.fee = 0
```

Chuyên gia có thể đặt câu hỏi: `order.total` tính trước hay sau giảm giá? Có bao gồm thuế không? `VIP` được xác định tại thời điểm đặt hàng hay thời điểm giao? Đơn hàng có nhiều kiện thì tất cả đều miễn phí hay chỉ kiện đầu tiên? `shipment.fee` là phí của một lần giao hay tổng phí của đơn hàng?

Những câu hỏi này cho thấy biểu thức ngắn gọn vẫn có thể chứa nhiều giả định ngầm. Nhóm cần làm rõ ngữ nghĩa, thêm thuật ngữ hoặc điều kiện cần thiết, và ghi lại quyết định vào đặc tả.

### Yêu cầu chuyên gia viết hoặc sửa ví dụ

Cho chuyên gia mô tả một tình huống bằng ngôn ngữ của họ, sau đó cùng chuyển thành DSL. Cũng có thể đưa biểu thức hiện tại và yêu cầu họ chỉ ra phần khó hiểu hoặc không phản ánh cách làm thực tế.

Khi người dùng miền có thể tự đề xuất biểu thức mà không cần liên tục hỏi ý nghĩa từ khóa, đó là dấu hiệu từ vựng đang gần với tư duy của họ. Nếu họ thường xuyên phải giải thích lại bằng lời vì cú pháp gây hiểu nhầm, cần xem xét thiết kế biểu thức.

### Kiểm chứng cả trường hợp hợp lệ và không hợp lệ

Đừng chỉ trình bày ví dụ thành công. Chuyên gia cần xác nhận cách DSL phản ứng khi:

- Thiếu một trường bắt buộc.
- Giá trị nằm ngoài giới hạn.
- Một đối tượng không ở trạng thái cho phép thao tác.
- Người dùng không có quyền thực hiện hành động.
- Hai quy tắc mâu thuẫn cùng được kích hoạt.
- Dữ liệu đến trễ, trùng lặp hoặc sai thứ tự.

Thông báo lỗi cũng cần dùng thuật ngữ miền dễ hiểu. Ví dụ, “Không thể hoàn tiền vì số tiền yêu cầu vượt quá số tiền đã thu” thường hữu ích hơn một thông báo chỉ nói “Validation failed”.

## Một quy trình kiểm chứng theo vòng lặp

Kiểm chứng miền không nên là một buổi phê duyệt duy nhất ở cuối dự án. Khi mô hình và DSL phát triển, các giả định mới xuất hiện và phản hồi trước đó có thể cần được xem xét lại.

Một vòng lặp thực tế có thể gồm:

1. **Nêu giả thuyết:** ghi lại cách nhóm đang hiểu một thuật ngữ, quy trình hoặc quy tắc.
2. **Chuẩn bị bằng chứng:** tập hợp tài liệu, ví dụ, sơ đồ hoặc biểu thức DSL liên quan.
3. **Thảo luận với đúng chuyên gia:** đặt câu hỏi theo tình huống và yêu cầu họ giải thích lý do.
4. **Ghi nhận phản hồi:** phân biệt phần xác nhận, phần cần sửa, phần chưa rõ và ý kiến còn mâu thuẫn.
5. **Cập nhật mô hình và DSL:** sửa định nghĩa, quan hệ, quy tắc, cú pháp hoặc thông báo lỗi khi cần.
6. **Đưa ví dụ đã xác nhận vào bộ kiểm thử:** dùng các trường hợp thực tế đã ẩn dữ liệu nhạy cảm làm ví dụ chuẩn.
7. **Xác nhận lại thay đổi:** trình bày phiên bản đã cập nhật để chuyên gia xác nhận rằng ý nghĩa mong muốn được giữ đúng.

Chu trình này có thể lặp lại cho từng phần nhỏ của miền. Những khái niệm ổn định có thể được xác nhận sớm; các quy tắc phức tạp hoặc còn tranh luận cần được theo dõi đến khi có quyết định phù hợp.

## Ghi nhận quyết định và quản lý ý kiến khác nhau

Không phải mọi câu hỏi đều có một câu trả lời ngay lập tức. Các chuyên gia có thể đưa ra ý kiến khác nhau vì họ làm việc ở các bộ phận, khu vực, phiên bản quy trình hoặc ngữ cảnh khác nhau. Không nên tự chọn một ý kiến chỉ vì nó dễ triển khai.

Với mỗi vấn đề chưa thống nhất, hãy ghi lại:

- Câu hỏi hoặc khái niệm đang tranh luận.
- Các cách hiểu được đưa ra và người/nhóm đại diện.
- Bằng chứng hoặc ví dụ hỗ trợ từng cách hiểu.
- Phạm vi mà mỗi cách hiểu đang áp dụng.
- Người hoặc vai trò có thẩm quyền quyết định.
- Quyết định cuối cùng, lý do và ngày hiệu lực.
- Ảnh hưởng đến mô hình, biểu thức DSL, dữ liệu và kiểm thử.

Nếu các cách hiểu đều hợp lệ trong phạm vi riêng, giải pháp có thể là phân chia ngữ cảnh miền hoặc biểu diễn chúng thành các khái niệm khác nhau. Nếu tổ chức cần một quy tắc duy nhất, người có thẩm quyền nghiệp vụ phải quyết định và xác nhận chính sách. Nhóm phát triển không nên tự giải quyết tranh chấp nghiệp vụ bằng cách chọn cấu trúc dữ liệu thuận tiện nhất.

Một bản ghi quyết định ngắn có thể có dạng:

```text
Vấn đề: Thời điểm xác định hạng khách hàng cho ưu đãi
Các cách hiểu: Hạng tại lúc đặt hàng / hạng tại lúc thanh toán
Phạm vi: Chương trình ưu đãi trực tuyến
Quyết định: Dùng hạng tại thời điểm đơn hàng được xác nhận
Lý do: Giữ mức ưu đãi ổn định trong suốt quá trình xử lý đơn
Ảnh hưởng DSL: Quy tắc ưu đãi tham chiếu customer.segmentAtConfirmation
Người xác nhận: Chủ sở hữu nghiệp vụ chương trình
```

Đây là ví dụ minh họa về cách ghi quyết định; thông tin thực tế cần được tổ chức xác nhận.

## Chuyển phản hồi thành đặc tả và kiểm thử

Ý kiến của chuyên gia chỉ có giá trị lâu dài khi được chuyển thành thông tin mà nhóm phát triển và công cụ có thể sử dụng. Không nên để quyết định chỉ tồn tại trong ghi chú cuộc họp hoặc trí nhớ của một thành viên.

Tùy loại phản hồi, cần cập nhật một hoặc nhiều tài sản sau:

| Phản hồi từ chuyên gia | Nơi cần cập nhật |
|---|---|
| Tên gọi hoặc định nghĩa chưa chính xác | Bảng thuật ngữ miền |
| Thiếu đối tượng hoặc quan hệ | Mô hình khái niệm hoặc mô hình dữ liệu |
| Quy trình có nhánh hoặc trạng thái chưa được mô tả | Sơ đồ quy trình và mô hình trạng thái |
| Điều kiện hoặc giới hạn mới | Đặc tả quy tắc nghiệp vụ |
| Biểu thức gây hiểu nhầm | Cú pháp, ngữ nghĩa hoặc ví dụ DSL |
| Trường hợp hợp lệ hoặc không hợp lệ mới | Bộ ví dụ chuẩn và bộ kiểm thử |
| Quyền hạn hoặc yêu cầu kiểm toán | Mô hình vai trò, chính sách và đặc tả vận hành |

Mỗi quy tắc quan trọng nên có ví dụ minh họa đầu vào, kết quả mong đợi và lý do. Các ví dụ đã được chuyên gia xác nhận có thể trở thành kiểm thử chấp nhận (acceptance test) hoặc bộ kiểm thử đặc tả (specification test). Khi bộ thực thi DSL thay đổi, các kiểm thử này giúp phát hiện trường hợp hành vi kỹ thuật đã thay đổi so với quy tắc miền.

Ví dụ, một quy tắc hoàn tiền có thể được ghi thành các trường hợp:

| Trường hợp | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Hoàn một phần hợp lệ | Đã thu tiền, số tiền yêu cầu nhỏ hơn số tiền còn có thể hoàn | Chấp nhận yêu cầu |
| Vượt số tiền còn lại | Số tiền yêu cầu lớn hơn số tiền còn có thể hoàn | Từ chối và nêu lý do |
| Chưa thu tiền | Thanh toán chưa được ghi nhận thành công | Không tạo giao dịch hoàn tiền |
| Không đủ quyền | Người yêu cầu không có quyền tạo hoặc phê duyệt | Từ chối theo chính sách phân quyền |

Các kết quả cụ thể cần được chuyên gia xác nhận, đặc biệt là sự khác biệt giữa từ chối yêu cầu, đưa vào hàng chờ phê duyệt và cho phép xử lý thủ công.

## Đánh giá mức độ sẵn sàng của mô hình miền

Không cần đợi mọi chi tiết của miền đều được biết mới có thể tiếp tục thiết kế DSL. Tuy nhiên, cần phân biệt phần đã được xác nhận với phần còn giả định và hiểu rõ rủi ro của từng điểm chưa rõ.

Một chủ đề có thể được xem là đủ cơ sở để chuyển sang thiết kế chi tiết khi:

- Thuật ngữ chính có định nghĩa và ngữ cảnh sử dụng rõ ràng.
- Những người đại diện phù hợp đã xem xét mô hình và các ví dụ quan trọng.
- Quan hệ, trạng thái và quy tắc chính đã được xác nhận hoặc có người chịu trách nhiệm quyết định.
- Trường hợp ngoại lệ quan trọng đã được nêu và có cách xử lý dự kiến.
- Các biểu thức DSL mẫu được chuyên gia diễn giải đúng với ý định.
- Ý kiến khác nhau, giả định và vấn đề chưa giải quyết được ghi lại.
- Có ví dụ hoặc tiêu chí chấp nhận để kiểm chứng hành vi của bộ thực thi.

Đây không phải là danh sách để đánh dấu hình thức. Với miền có rủi ro cao, chẳng hạn thanh toán, y tế hoặc tuân thủ pháp luật, yêu cầu xác nhận và bằng chứng cần nghiêm ngặt hơn. Với một công cụ nội bộ có phạm vi hẹp, nhóm có thể chấp nhận một số giả định có kiểm soát và bổ sung dần trong quá trình sử dụng.

## Những sai lầm thường gặp khi kiểm chứng với chuyên gia

### Chỉ hỏi chuyên gia xác nhận mô hình đã có

Nếu chỉ trình bày một mô hình hoàn chỉnh rồi hỏi “Có đúng không?”, chuyên gia thường khó nhận ra những giả định ẩn hoặc có xu hướng đồng ý với cách diễn đạt của nhóm phát triển. Hãy để họ kể lại tình huống, tự mô tả quy trình và diễn giải ví dụ bằng cách hiểu của mình.

### Chỉ làm việc với một người đại diện

Một cá nhân có thể có kinh nghiệm sâu nhưng không đại diện cho tất cả vai trò và trường hợp. Hãy xác định các nhóm liên quan và kiểm chứng những phần giao nhau hoặc có tranh chấp với nhiều người phù hợp.

### Chỉ xem tài liệu mà không quan sát thực tế

Quy trình chính thức có thể khác với cách công việc đang được thực hiện. Kết hợp tài liệu với phỏng vấn, quan sát và ví dụ sự cố để phát hiện bước ngầm, ngoại lệ và giải pháp tạm thời.

### Chỉ kiểm chứng trường hợp thành công

Trường hợp bình thường thường không bộc lộ hết quy tắc. Hãy hỏi về dữ liệu thiếu, trạng thái sai, quyền hạn không đủ, giao dịch trùng lặp, sự kiện đến muộn và những tình huống cần xử lý thủ công.

### Dùng thuật ngữ kỹ thuật để dẫn dắt câu trả lời

Nếu nhóm hỏi chuyên gia “Đối tượng này có phải aggregate root không?”, người được hỏi có thể không hiểu hoặc trả lời theo cách họ nghĩ nhóm muốn nghe. Nên hỏi về trách nhiệm, vòng đời, danh tính và quy tắc trước, rồi nhóm phát triển mới ánh xạ sang khái niệm kỹ thuật.

### Không ghi lại lý do và nguồn xác nhận

Chỉ lưu kết quả cuối cùng sẽ khiến nhóm khó hiểu vì sao một quy tắc được chọn và liệu nó còn đúng khi chính sách thay đổi. Hãy lưu cả phạm vi, bằng chứng, người xác nhận và ảnh hưởng đến DSL.

### Xem mọi phản hồi là yêu cầu phải thêm cú pháp

Chuyên gia có thể đề xuất một cách diễn đạt tiện lợi cho một trường hợp đơn lẻ. Không phải đề xuất nào cũng cần trở thành từ khóa hoặc tính năng mới. Nhóm cần xác định nhu cầu có lặp lại, có thuộc phạm vi miền và có mang lại lợi ích cho người dùng DSL hay không.

## Ví dụ xuyên suốt: kiểm chứng DSL cho quy trình hoàn tiền

Giả sử nhóm đang xây dựng DSL cho hệ thống thương mại điện tử và muốn hỗ trợ mô tả quy tắc hoàn tiền. Nhóm bắt đầu với giả định rằng một đơn hàng đã thanh toán có thể được hoàn một phần hoặc toàn bộ.

### Bước 1: Xác định người cần hỏi

Nhóm mời nhân viên chăm sóc khách hàng, kế toán, người quản lý phê duyệt hoàn tiền và người vận hành cổng thanh toán. Mỗi người có góc nhìn khác nhau: lý do khách hàng yêu cầu, cách ghi nhận tiền, giới hạn thẩm quyền và trạng thái thực tế của giao dịch.

### Bước 2: Thu thập tình huống

Nhóm yêu cầu từng người kể về một yêu cầu hoàn tiền gần đây, gồm thời điểm nhận yêu cầu, dữ liệu cần kiểm tra, các bước phê duyệt và kết quả. Qua trao đổi, nhóm phát hiện rằng có trường hợp hoàn tiền do trả hàng, có trường hợp điều chỉnh giá và có trường hợp giao dịch thanh toán thất bại nhưng hệ thống đã ghi nhận nhầm.

### Bước 3: Làm rõ thuật ngữ

Nhóm hỏi liệu “hoàn tiền” có bao gồm việc hủy một khoản thanh toán chưa được thu hay không. Kế toán phân biệt hoàn tiền với hủy giao dịch; người vận hành cổng thanh toán giải thích rằng hai thao tác có trạng thái và thời điểm xử lý khác nhau. Nhóm quyết định cần hai thuật ngữ riêng trong mô hình.

### Bước 4: Làm rõ giới hạn

Nhóm đưa ra trường hợp khách hàng đã được hoàn một phần và tiếp tục yêu cầu hoàn thêm. Chuyên gia xác nhận số tiền có thể hoàn phải tính đến các khoản đã hoàn trước đó và những khoản phí không được hoàn theo chính sách. Nhóm ghi nhận quy tắc cùng nguồn xác nhận.

### Bước 5: Thử biểu thức DSL

Nhóm đưa ra biểu thức giả định:

```text
WHEN payment.status IS "CAPTURED"
  AND refund.remainingAmount >= request.amount
THEN refund.create(request)
```

Chuyên gia hỏi `remainingAmount` được tính tại thời điểm nào và điều gì xảy ra khi hai yêu cầu hoàn tiền được gửi gần như đồng thời. Nhóm bổ sung yêu cầu kiểm tra số tiền còn lại một cách nhất quán khi thực hiện giao dịch và xác định rõ trạng thái chờ xử lý.

### Bước 6: Chuyển thành ví dụ kiểm thử

Nhóm ghi lại các trường hợp đã được xác nhận: hoàn một phần, hoàn toàn bộ, yêu cầu vượt số tiền còn lại, thanh toán chưa được thu, giao dịch đang chờ và người dùng không đủ quyền. Những ví dụ này trở thành căn cứ để kiểm tra bộ thực thi DSL.

Qua ví dụ, có thể thấy kiểm chứng với chuyên gia không chỉ giúp sửa tên gọi. Nó làm rõ cả khái niệm, quy trình, quy tắc, thời điểm áp dụng và hành vi cần được bảo đảm trong hệ thống.

## Vai trò liên tục của chuyên gia sau khi DSL được đưa vào sử dụng

Kiểm chứng không kết thúc khi DSL có phiên bản đầu tiên. Người dùng thực tế có thể phát hiện tình huống mới, quy định có thể thay đổi và tổ chức có thể mở rộng phạm vi hoạt động. Nhóm nên duy trì kênh ghi nhận phản hồi và quy trình xem xét thay đổi.

Khi có yêu cầu mới, cần xác định đó là:

- Thuật ngữ mới hoặc cách hiểu mới của thuật ngữ hiện có.
- Quy tắc mới trong phạm vi miền hiện tại.
- Ngoại lệ chưa từng được mô hình hóa.
- Nhu cầu thuộc một ngữ cảnh miền khác.
- Vấn đề do cú pháp, tài liệu hoặc công cụ hỗ trợ DSL gây ra.
- Lỗi trong cách bộ thực thi diễn giải một quy tắc đã được xác nhận.

Mỗi thay đổi có ảnh hưởng đến ngữ nghĩa nên được chuyên gia phù hợp xem xét trước khi phát hành. Cần lưu phiên bản đặc tả, ví dụ đã xác nhận và kiểm thử liên quan để người dùng hiểu biểu thức cũ sẽ được diễn giải như thế nào.

## Kết luận

Kiểm chứng với chuyên gia là cầu nối giữa hiểu biết nghiệp vụ và thiết kế DSL. Nhóm phát triển cần đưa thuật ngữ, mô hình, quy trình, quy tắc và biểu thức mẫu đến đúng người có kiến thức để họ diễn giải, phản biện và xác nhận bằng tình huống thực tế.

Kết quả quan trọng của hoạt động này là một mô hình miền có căn cứ, các quyết định được ghi lại, những điểm chưa rõ được quản lý và các ví dụ có thể dùng để kiểm thử. Khi chuyên gia tham gia xuyên suốt quá trình, DSL có cơ hội phản ánh đúng cách lĩnh vực vận hành và giúp người dùng diễn đạt công việc bằng một ngôn ngữ nhất quán, dễ hiểu.

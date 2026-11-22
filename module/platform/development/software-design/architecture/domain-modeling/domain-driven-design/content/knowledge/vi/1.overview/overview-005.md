# Độ phức tạp nghiệp vụ so với độ phức tạp kỹ thuật

Khi xây dựng một hệ thống phần mềm, đội phát triển thường phải giải quyết hai nhóm khó khăn khác nhau. Nhóm thứ nhất đến từ chính bài toán mà tổ chức đang làm: chính sách, quy tắc, quyết định, ngoại lệ và cách các hoạt động nghiệp vụ liên hệ với nhau. Nhóm thứ hai đến từ việc biến giải pháp thành một hệ thống phần mềm có thể vận hành: lưu trữ dữ liệu, giao tiếp giữa các dịch vụ, bảo mật, hiệu năng, triển khai và giám sát.

Hai nhóm khó khăn này có liên quan, nhưng không đồng nhất. Một hệ thống có thể có nghiệp vụ rất phức tạp dù công nghệ triển khai đơn giản. Ngược lại, một chức năng nghiệp vụ đơn giản vẫn có thể đòi hỏi hạ tầng kỹ thuật phức tạp khi phải phục vụ hàng triệu người dùng hoặc hoạt động trên nhiều khu vực địa lý.

Domain-Driven Design (DDD) bắt đầu bằng việc hiểu đúng miền nghiệp vụ và mô hình hóa những quy tắc có ý nghĩa đối với tổ chức. Vì vậy, người học DDD cần phân biệt được độ phức tạp nghiệp vụ với độ phức tạp kỹ thuật, nhận ra phần nào cần được mô hình hóa trong domain và phần nào thuộc trách nhiệm của giải pháp kỹ thuật.

Sau bài học này, bạn có thể:

- Giải thích hai nguồn độ phức tạp và cách chúng tác động lẫn nhau.
- Nhận diện quy tắc nghiệp vụ, yêu cầu kỹ thuật và những yêu cầu có cả hai mặt.
- Phân tích một ví dụ thực tế để xác định phần nào cần được mô hình hóa bằng DDD.
- Biết khi nào nên đầu tư vào mô hình domain và khi nào một giải pháp đơn giản là đủ.

## 1. Độ phức tạp nghiệp vụ là gì?

Độ phức tạp nghiệp vụ (*business complexity*) xuất phát từ bản chất của miền nghiệp vụ mà phần mềm cần hỗ trợ. Nó nằm trong mục tiêu của tổ chức, cách con người ra quyết định, các chính sách, quy định, thuật ngữ, quy trình, trạng thái và những ngoại lệ có thể xảy ra.

Ví dụ, một hệ thống cho vay có thể phải trả lời nhiều câu hỏi:

- Khách hàng nào đủ điều kiện vay theo từng loại sản phẩm?
- Thu nhập, lịch sử tín dụng, tài sản bảo đảm và khoản nợ hiện tại ảnh hưởng đến quyết định như thế nào?
- Có trường hợp nào được miễn một điều kiện hoặc cần người có thẩm quyền phê duyệt không?
- Lãi suất và lịch trả nợ thay đổi ra sao khi khách hàng trả trước hạn hoặc chậm thanh toán?
- Nếu chính sách thay đổi, hợp đồng đang hoạt động được áp dụng chính sách cũ hay chính sách mới?

Đây là những câu hỏi về cách hoạt động cho vay thực sự diễn ra. Chúng vẫn tồn tại dù hệ thống được viết bằng Java, C#, Go hay một ngôn ngữ khác; dù dữ liệu được lưu trong PostgreSQL hay một cơ sở dữ liệu khác.

Độ phức tạp nghiệp vụ thường đến từ các yếu tố sau:

**Quy tắc và chính sách.** Một quyết định có thể phụ thuộc vào nhiều điều kiện. Điều kiện có thể kết hợp, loại trừ hoặc thay đổi theo loại sản phẩm, nhóm khách hàng, khu vực hay thời điểm.

**Ngoại lệ.** Quy trình thực tế hiếm khi chỉ có một đường đi chuẩn. Có thể có trường hợp cần phê duyệt thủ công, miễn trừ, xử lý tranh chấp hoặc áp dụng chính sách riêng.

**Vòng đời và trạng thái.** Một đối tượng nghiệp vụ thường trải qua nhiều giai đoạn. Đơn vay có thể được tạo, gửi duyệt, chấp thuận, giải ngân, tất toán hoặc quá hạn. Mỗi chuyển đổi có điều kiện và hệ quả riêng.

**Thời gian và lịch sử.** Một quy tắc có thể phụ thuộc vào ngày hiệu lực, thời hạn, thứ tự sự kiện hoặc chính sách tại thời điểm giao dịch được tạo. Dữ liệu hiện tại đôi khi chưa đủ để giải thích một quyết định trong quá khứ.

**Sự phụ thuộc giữa các quyết định.** Một thay đổi ở một phần nghiệp vụ có thể tác động đến phần khác. Ví dụ, thay đổi loại hợp đồng có thể ảnh hưởng đến cách tính phí, điều kiện hủy và cách ghi nhận doanh thu.

**Ngôn ngữ và cách hiểu của tổ chức.** Cùng một từ có thể mang nghĩa khác nhau giữa các phòng ban hoặc giữa các nhóm sản phẩm. Nếu không làm rõ, phần mềm dễ mã hóa những cách hiểu mâu thuẫn.

Độ phức tạp nghiệp vụ không được đo bằng số lượng màn hình, bảng dữ liệu hay dòng mã. Một quy tắc ngắn như “khách hàng được hoàn phí nếu hủy trước ngày hiệu lực” có thể ẩn chứa nhiều câu hỏi: ngày hiệu lực nào, múi giờ nào, hủy một phần có được không, phí nào được hoàn, và quy tắc áp dụng cho hợp đồng đã gia hạn ra sao?

## 2. Độ phức tạp kỹ thuật là gì?

Độ phức tạp kỹ thuật (*technical complexity*) phát sinh từ việc thiết kế, xây dựng, tích hợp và vận hành hệ thống phần mềm. Nó liên quan đến nền tảng công nghệ, kiến trúc, dữ liệu, giao tiếp, bảo mật, hiệu năng và độ tin cậy.

Ví dụ, một hệ thống cho vay phục vụ lượng lớn khách hàng có thể cần giải quyết:

- Phân tải yêu cầu và mở rộng năng lực xử lý khi lưu lượng tăng.
- Đảm bảo dữ liệu nhất quán khi nhiều dịch vụ cùng cập nhật thông tin khoản vay.
- Tích hợp với hệ thống định danh, chấm điểm tín dụng, ngân hàng và cổng thanh toán.
- Xử lý timeout, retry, thông điệp gửi trùng và dịch vụ bên ngoài tạm thời không khả dụng.
- Bảo vệ dữ liệu cá nhân, quản lý quyền truy cập, mã hóa và lưu dấu kiểm toán.
- Triển khai, giám sát, sao lưu và khôi phục khi có sự cố.

Những vấn đề này cần năng lực kỹ thuật và quyết định kiến trúc phù hợp. Chúng có thể ảnh hưởng trực tiếp đến trải nghiệm và kết quả kinh doanh, nhưng bản thân chúng không nhất thiết quyết định khách hàng nào đủ điều kiện vay hay mức lãi suất nào được áp dụng.

Một số nguồn phổ biến của độ phức tạp kỹ thuật:

- **Kiến trúc và phân tán:** ranh giới dịch vụ, giao tiếp đồng bộ hoặc bất đồng bộ, nhất quán dữ liệu, thứ tự xử lý và xử lý lỗi giữa các thành phần.
- **Dữ liệu:** mô hình lưu trữ, truy vấn, di chuyển dữ liệu, sao lưu, phục hồi và quản lý dữ liệu lịch sử.
- **Hiệu năng và quy mô:** độ trễ, thông lượng, tải đột biến, bộ nhớ đệm và khả năng mở rộng.
- **Bảo mật và vận hành:** xác thực, phân quyền, mã hóa, giám sát, cảnh báo, triển khai và khôi phục.
- **Tích hợp:** giao thức, định dạng dữ liệu, giới hạn API, phiên bản và hành vi của hệ thống bên ngoài.

Độ phức tạp kỹ thuật cũng có thể xuất hiện khi yêu cầu nghiệp vụ không phức tạp. Một trang hiển thị nội dung tĩnh có quy tắc nghiệp vụ rất ít, nhưng nếu phải phân phối nội dung toàn cầu với độ trễ thấp và khả năng chịu lỗi cao thì hạ tầng phục vụ nó vẫn phức tạp.

## 3. So sánh hai loại độ phức tạp

Có thể phân biệt hai loại độ phức tạp bằng câu hỏi mà chúng cần trả lời:

| Góc nhìn | Độ phức tạp nghiệp vụ | Độ phức tạp kỹ thuật |
|---|---|---|
| Câu hỏi chính | Tổ chức cần đưa ra quyết định gì và theo quy tắc nào? | Hệ thống thực hiện, lưu trữ và vận hành các quyết định đó ra sao? |
| Nguồn phát sinh | Chính sách, quy trình, con người, thị trường, quy định và ngoại lệ | Công nghệ, kiến trúc, dữ liệu, tích hợp, tải và môi trường vận hành |
| Ví dụ | Điều kiện hoàn tiền, cách tính lãi, quyền phê duyệt | Giao dịch cơ sở dữ liệu, retry API, phân tải, mã hóa |
| Người hiểu sâu | Chuyên gia nghiệp vụ cùng đội phát triển | Kiến trúc sư, kỹ sư và đội vận hành; vẫn cần trao đổi với chuyên gia nghiệp vụ |
| Cách tiếp cận | Khám phá domain, làm rõ thuật ngữ và mô hình hóa quy tắc | Chọn kiến trúc, công nghệ và cơ chế vận hành phù hợp |

Đây là cách phân biệt theo bản chất của vấn đề, không phải theo nơi đoạn mã đang nằm. Một quy tắc nghiệp vụ có thể bị viết trong controller hoặc câu lệnh SQL, nhưng vị trí đó không biến nó thành vấn đề kỹ thuật. Tương tự, một yêu cầu bảo mật có thể được nhắc đến trong quy trình nghiệp vụ, nhưng việc quản lý khóa mã hóa vẫn là trách nhiệm kỹ thuật.

Một yêu cầu cũng có thể có cả hai mặt. Chẳng hạn, “không được thu tiền khách hàng hai lần cho cùng một lần thanh toán” là một cam kết nghiệp vụ. Hệ thống có thể hiện thực cam kết đó bằng mã định danh idempotency, kiểm soát giao dịch, ràng buộc dữ liệu và cơ chế đối soát. Cam kết thuộc về nghiệp vụ; các cơ chế bảo đảm nó là lựa chọn kỹ thuật. Đội phát triển cần hiểu cả hai để giải pháp thực sự đáp ứng yêu cầu.

### Bốn tình huống thường gặp

| Độ phức tạp nghiệp vụ | Độ phức tạp kỹ thuật | Ví dụ minh họa |
|---|---|---|
| Thấp | Thấp | Công cụ nội bộ lưu danh bạ nhân viên với vài thao tác thêm, sửa, xem và xóa |
| Cao | Thấp | Công cụ tính thuế hoặc tính quyền lợi với nhiều chính sách và ngoại lệ, nhưng chỉ phục vụ một nhóm người dùng với hạ tầng đơn giản |
| Thấp | Cao | Dịch vụ phân phối nội dung tĩnh toàn cầu, ít quy tắc nghiệp vụ nhưng yêu cầu độ trễ thấp và khả năng sẵn sàng cao |
| Cao | Cao | Hệ thống giao dịch tài chính có nhiều quy tắc thanh toán, đối soát và yêu cầu xử lý phân tán với độ tin cậy cao |

Ma trận này giúp tránh một suy luận sai: công nghệ khó không đồng nghĩa domain phức tạp, và nghiệp vụ đơn giản không đồng nghĩa hệ thống luôn dễ xây dựng. Cần đánh giá từng trục riêng trước khi chọn cách tổ chức giải pháp.

## 4. Ví dụ: xử lý yêu cầu trả hàng và hoàn tiền

Hãy xét một hệ thống thương mại điện tử. Khách hàng gửi yêu cầu trả một sản phẩm đã mua và muốn nhận lại tiền.

Ở góc độ nghiệp vụ, câu hỏi không chỉ là “có thể gọi API hoàn tiền hay không”. Đội phát triển cần hiểu chính sách trả hàng của doanh nghiệp:

1. Sản phẩm nào được phép trả? Một số loại hàng có thể bị loại trừ vì lý do vệ sinh, cá nhân hóa hoặc quy định pháp lý.
2. Thời hạn trả hàng được tính từ lúc đặt hàng, thanh toán hay giao hàng thành công?
3. Khách hàng có thể trả một phần số lượng trong đơn hàng không?
4. Nếu đơn hàng đã dùng mã giảm giá, điểm thưởng hoặc ưu đãi theo số lượng, số tiền hoàn được tính như thế nào?
5. Phí vận chuyển, phí dịch vụ hoặc phí hoàn hàng có được hoàn không?
6. Sản phẩm bị hư hỏng, đã qua sử dụng hoặc thiếu phụ kiện được xử lý theo chính sách nào?
7. Khách hàng được hoàn về phương thức thanh toán ban đầu hay có thể chọn tín dụng cửa hàng?
8. Ai có quyền chấp thuận một trường hợp nằm ngoài chính sách thông thường?

Những câu hỏi trên thể hiện độ phức tạp nghiệp vụ. Chúng định nghĩa thế nào là một yêu cầu trả hàng hợp lệ và khách hàng được nhận khoản hoàn nào.

Một mô hình domain có thể diễn đạt quyết định này bằng một chính sách trả hàng. Ví dụ dưới đây là luồng xử lý khái niệm, không gắn với ngôn ngữ lập trình hay nhà cung cấp cụ thể:

```text
evaluateReturn(request, order, returnPolicy, currentTime)
  kiểm tra đơn hàng và dòng hàng được yêu cầu trả
  kiểm tra thời hạn và điều kiện của sản phẩm
  áp dụng chính sách theo loại hàng và khu vực
  tính số tiền hoàn cho số lượng được chấp thuận
  xác định ngoại lệ cần người có thẩm quyền duyệt
  trả về quyết định, số tiền và lý do
```

Kết quả của bước này là một quyết định nghiệp vụ có thể giải thích được: yêu cầu được chấp thuận hay từ chối, số tiền dự kiến được hoàn và căn cứ của quyết định. Các màn hình, API hay cổng thanh toán có thể thay đổi, nhưng ý nghĩa của chính sách cần được giữ nhất quán.

Ở góc độ kỹ thuật, hệ thống còn phải thực hiện quyết định đó một cách an toàn:

- Nhận yêu cầu qua API và xác thực người gửi.
- Lưu trạng thái yêu cầu trả hàng và kiểm soát việc cập nhật đồng thời.
- Gọi nhà cung cấp thanh toán để thực hiện hoàn tiền.
- Xử lý timeout hoặc phản hồi không rõ ràng mà không hoàn tiền hai lần.
- Gửi thông báo cho khách hàng và các bộ phận liên quan.
- Đối soát giao dịch khi kết quả từ nhà cung cấp đến chậm hoặc không đồng nhất.

Những cơ chế này thuộc về thiết kế ứng dụng và hạ tầng. Chúng cần phối hợp với domain nhưng không nên làm mờ chính sách trả hàng. Chẳng hạn, adapter thanh toán chịu trách nhiệm chuyển yêu cầu hoàn tiền sang giao thức của nhà cung cấp; chính sách domain chịu trách nhiệm xác định khách hàng được hoàn bao nhiêu theo quy định của cửa hàng.

| Vấn đề | Bản chất cần làm rõ |
|---|---|
| Sản phẩm nào được trả trong 30 ngày? | Quy tắc nghiệp vụ; cần xác định mốc thời gian và ngoại lệ |
| Số tiền hoàn khi đơn có mã giảm giá? | Quy tắc tính toán nghiệp vụ |
| API thanh toán bị timeout thì xử lý thế nào? | Vấn đề tích hợp và độ tin cậy kỹ thuật |
| Một yêu cầu hoàn tiền bị gửi lại nhiều lần? | Cam kết không hoàn trùng là yêu cầu nghiệp vụ; idempotency và kiểm soát giao dịch là cơ chế kỹ thuật |
| Ai được duyệt trường hợp đặc biệt? | Chính sách phân quyền nghiệp vụ; xác thực và kiểm soát quyền là phần hiện thực kỹ thuật |

Ví dụ này cho thấy không nên phân loại chỉ dựa trên tên tính năng. Cần hỏi vấn đề đang bảo vệ quyết định nào, hoặc đang bảo đảm hệ thống thực hiện quyết định đó ra sao.

## 5. Điều gì xảy ra khi nhầm lẫn hai loại độ phức tạp?

### Chỉ tập trung vào công nghệ

Đội phát triển có thể bắt đầu bằng việc chọn framework, chia microservice, thiết kế schema hoặc thêm message broker trước khi hiểu đầy đủ nghiệp vụ. Kết quả là hệ thống có hạ tầng hiện đại nhưng quy tắc quan trọng lại nằm rải rác trong controller, câu lệnh truy vấn, cấu hình hoặc các dịch vụ tích hợp.

Khi chính sách thay đổi, cùng một quy tắc có thể phải sửa ở nhiều nơi. Các nhóm có thể hiểu khác nhau về một thuật ngữ. Chuyên gia nghiệp vụ khó kiểm tra xem hệ thống có đang phản ánh đúng cách tổ chức hoạt động hay không. Chi phí bảo trì tăng lên dù công nghệ ban đầu được lựa chọn rất tốt.

### Chỉ tập trung vào nghiệp vụ

Chiều ngược lại cũng nguy hiểm. Một mô hình nghiệp vụ dễ hiểu không tự động giải quyết được giao dịch đồng thời, mất kết nối, dữ liệu gửi trùng, rò rỉ thông tin hay tải tăng đột biến. Nếu bỏ qua những vấn đề kỹ thuật này, hệ thống có thể đưa ra quyết định đúng nhưng thực hiện sai hoặc không đáng tin cậy.

DDD không có nghĩa là xem nhẹ kiến trúc, cơ sở dữ liệu, bảo mật hay vận hành. DDD giúp đội phát triển hiểu và bảo vệ logic domain; kỹ thuật phần mềm tốt giúp logic đó được thực thi an toàn, hiệu quả và có thể vận hành lâu dài.

### Nhầm độ dài mã nguồn với độ phức tạp của domain

Một hệ thống có nhiều lớp, nhiều bảng và nhiều dòng mã chưa chắc có domain phức tạp. Phần lớn độ dài có thể đến từ tích hợp, chuyển đổi dữ liệu hoặc mã khung. Ngược lại, một domain có nhiều chính sách và ngoại lệ có thể đang được triển khai bằng một lượng mã nhỏ nhưng rất khó hiểu vì quy tắc bị nén vào các điều kiện lồng nhau.

Vì vậy, khi đánh giá một hệ thống, hãy tìm những quyết định nghiệp vụ và quy tắc chi phối chúng. Đừng dùng số lượng thành phần kỹ thuật làm đại diện cho độ phức tạp domain.

## 6. Cách nhận diện phần phức tạp nằm ở đâu

Khi khảo sát một bài toán, hãy trao đổi với chuyên gia nghiệp vụ và đội kỹ thuật theo hai nhóm câu hỏi.

**Để khám phá độ phức tạp nghiệp vụ:**

- Những quyết định nào ảnh hưởng trực tiếp đến kết quả kinh doanh hoặc quyền lợi khách hàng?
- Quy tắc nào thường thay đổi? Ai có quyền thay đổi hoặc phê duyệt chúng?
- Có những trường hợp ngoại lệ nào? Điều kiện nào khiến quy trình chuyển sang một nhánh khác?
- Một đối tượng nghiệp vụ trải qua những trạng thái nào? Ai hoặc điều gì được phép chuyển trạng thái?
- Những thuật ngữ nào đang được các nhóm hiểu khác nhau?
- Có quyết định nào phải được giải thích hoặc tái dựng sau nhiều tháng, nhiều năm không?

**Để khám phá độ phức tạp kỹ thuật:**

- Hệ thống cần đáp ứng bao nhiêu yêu cầu mỗi giây và độ trễ tối đa là bao nhiêu?
- Dữ liệu cần nhất quán ở phạm vi nào? Có nhiều thành phần cùng cập nhật không?
- Hệ thống phụ thuộc vào dịch vụ bên ngoài nào và sẽ phản ứng ra sao khi chúng gặp sự cố?
- Yêu cầu về bảo mật, quyền riêng tư, kiểm toán và khôi phục là gì?
- Hệ thống cần mở rộng, triển khai và giám sát như thế nào?

Một kỹ thuật hữu ích là mô tả một tình huống nghiệp vụ cụ thể theo ba phần: điều kiện ban đầu, sự kiện xảy ra và kết quả mong đợi. Sau đó hỏi chuyên gia về các biến thể và ngoại lệ. Những khác biệt làm thay đổi quyết định thường giúp bộc lộ quy tắc domain. Tiếp theo, đội kỹ thuật xác định các yêu cầu về dữ liệu, giao tiếp và vận hành để hiện thực những quyết định đó.

Ví dụ, thay vì chỉ ghi “hỗ trợ hủy đơn”, hãy hỏi: đơn ở trạng thái nào được hủy, ai được hủy, khi nào không thể hủy, nếu hàng đã đóng gói thì sao, khoản thanh toán và điểm thưởng được xử lý thế nào? Sau khi hiểu các quy tắc này, đội phát triển mới có cơ sở thiết kế API, giao dịch dữ liệu và tích hợp kho vận phù hợp.

## 7. DDD tập trung giải quyết phần nào?

DDD là cách tiếp cận thiết kế phần mềm lấy domain làm trọng tâm. DDD đặc biệt hữu ích khi nghiệp vụ là nguồn tạo khác biệt cho tổ chức và có nhiều quy tắc, thuật ngữ, trạng thái hoặc ngoại lệ cần được hiểu chính xác.

Trong DDD, chuyên gia nghiệp vụ và đội phát triển cùng xây dựng một ngôn ngữ chung (*Ubiquitous Language*). Các khái niệm trong trao đổi, tài liệu, mô hình và mã nguồn cần thống nhất về ý nghĩa trong phạm vi đang xét. Khi một từ còn mơ hồ, đội phát triển cần làm rõ trước khi biến nó thành cấu trúc dữ liệu hoặc hành vi phần mềm.

DDD có hai nhóm thiết kế bổ trợ nhau:

- **Strategic Design** giúp xác định các phần khác nhau của domain, ranh giới ngữ cảnh (*Bounded Context*) và quan hệ giữa chúng qua *Context Map*. Cách tiếp cận này giúp tổ chức mô hình phù hợp với cách các nhóm và lĩnh vực nghiệp vụ thực sự hoạt động.
- **Tactical Design** cung cấp các công cụ mô hình hóa bên trong một ngữ cảnh, chẳng hạn *Entity*, *Value Object*, *Aggregate*, *Repository* và *Domain Event*. Chúng giúp biểu đạt danh tính, giá trị, quy tắc nhất quán, truy xuất và những sự kiện có ý nghĩa trong domain.

Những công cụ này không nhằm làm cho mọi phần của hệ thống trở nên phức tạp hơn. Chúng giúp đặt sự phức tạp đúng chỗ: quy tắc nghiệp vụ được diễn đạt trong mô hình domain; phần điều phối use case thuộc ứng dụng; lưu trữ, giao tiếp và tích hợp được xử lý qua các thành phần kỹ thuật phù hợp. Ranh giới cụ thể phụ thuộc vào bài toán và kiến trúc của hệ thống.

DDD thường đáng đầu tư khi:

- Quy tắc nghiệp vụ phức tạp và thường xuyên thay đổi.
- Những quyết định trong domain tạo ra lợi thế cạnh tranh hoặc ảnh hưởng lớn đến tổ chức và khách hàng.
- Nhiều nhóm cùng làm việc và cần thống nhất cách hiểu về các khái niệm nghiệp vụ.
- Các ngoại lệ, trạng thái và chính sách đang khó kiểm soát vì bị phân tán trong mã nguồn.
- Có chuyên gia nghiệp vụ sẵn sàng cùng đội phát triển khám phá và xác nhận mô hình.

Với một ứng dụng CRUD đơn giản, ít quy tắc và ít thay đổi, áp dụng đầy đủ các mẫu DDD có thể tạo thêm chi phí không cần thiết. Hãy chọn mức độ mô hình hóa tương xứng với độ phức tạp thực tế của domain.

## 8. Bài tập tự kiểm tra

Một doanh nghiệp giao hàng muốn xây dựng chức năng tính phí vận chuyển. Hãy phân loại các câu hỏi sau theo độ phức tạp nghiệp vụ, độ phức tạp kỹ thuật hoặc cả hai:

1. Phí được tính theo khu vực, khối lượng, kích thước hay loại dịch vụ?
2. Đơn hàng đủ điều kiện miễn phí vận chuyển khi nào?
3. Nếu dịch vụ định giá của đối tác không phản hồi trong hai giây, hệ thống xử lý ra sao?
4. Nếu khách hàng thay đổi địa chỉ sau khi đơn đã được lấy hàng, phí có được tính lại không?
5. Làm thế nào để tránh ghi nhận hai lần cùng một lần yêu cầu định giá?

Gợi ý trả lời:

- Câu 1, 2 và 4 chủ yếu là nghiệp vụ vì chúng xác định chính sách tính phí và cách xử lý thay đổi đơn hàng.
- Câu 3 chủ yếu là kỹ thuật vì liên quan đến timeout và khả năng phản hồi của tích hợp. Tuy nhiên, thời gian chờ tối đa có thể bắt nguồn từ cam kết dịch vụ với khách hàng.
- Câu 5 có cả hai mặt: hệ thống phải bảo đảm hành vi nghiệp vụ không bị tính hoặc ghi nhận trùng, còn mã yêu cầu duy nhất, idempotency và lưu trữ trạng thái là các cơ chế kỹ thuật.

Nếu các nhóm chưa thống nhất câu trả lời cho câu 1, 2 hoặc 4, vấn đề cần giải quyết trước tiên là hiểu domain. Nếu quy tắc đã rõ nhưng hệ thống không xử lý được timeout hoặc yêu cầu gửi trùng, trọng tâm nằm ở thiết kế kỹ thuật. Trong thực tế, hai nhóm thường phải phối hợp để tạo ra một giải pháp hoàn chỉnh.

## Kết luận

Độ phức tạp nghiệp vụ mô tả những điều khó khăn vốn có trong cách tổ chức hoạt động và ra quyết định. Độ phức tạp kỹ thuật mô tả những khó khăn khi xây dựng và vận hành phần mềm để hỗ trợ các hoạt động đó. Chúng tác động lẫn nhau nhưng cần được nhận diện riêng.

DDD giúp đội phát triển khám phá, diễn đạt và tổ chức phần logic nghiệp vụ quan trọng bằng một mô hình domain cùng ngôn ngữ chung. Khi hiểu rõ domain, đội phát triển có cơ sở tốt hơn để chọn kiến trúc và cơ chế kỹ thuật phù hợp. Mục tiêu là tạo ra phần mềm phản ánh đúng nghiệp vụ, đồng thời vận hành đáng tin cậy khi các quy tắc và nhu cầu thay đổi.

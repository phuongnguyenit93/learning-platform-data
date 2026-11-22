# Quy tắc nghiệp vụ

Quy tắc nghiệp vụ (business rule) là một phát biểu có ý nghĩa đối với hoạt động của tổ chức, mô tả điều kiện, giới hạn, chính sách hoặc cách đưa ra quyết định trong một miền. Quy tắc có thể xác định ai được phép thực hiện một hành động, khi nào một đơn hàng được chấp nhận, cách tính mức chiết khấu, hoặc dữ liệu nào phải có trước khi một quy trình tiếp tục. Trong ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL), quy tắc nghiệp vụ được biểu diễn bằng các khái niệm gần với cách chuyên gia miền diễn đạt công việc, để chương trình có thể đọc, kiểm tra và thực thi chúng một cách nhất quán.

Quy tắc nghiệp vụ tạo cầu nối giữa chính sách của tổ chức và hành vi của phần mềm. Chúng giúp phần mềm phản ánh cách miền hoạt động, đồng thời làm rõ giới hạn của DSL: ngôn ngữ chỉ nên mô hình hóa những chính sách và quyết định thuộc miền mà nó phục vụ. Chi tiết như cách mở kết nối mạng, lưu đối tượng vào bộ nhớ hay gửi một truy vấn SQL thường thuộc tầng triển khai, trừ khi chính chúng là khái niệm mà người dùng miền cần điều khiển.

## 1. Quy tắc nghiệp vụ là gì?

Một quy tắc nghiệp vụ diễn đạt điều mà tổ chức hoặc miền yêu cầu phải đúng, được phép, bị cấm hoặc được tính theo một chính sách. Nó thường có thể được diễn đạt bằng ngôn ngữ tự nhiên trước khi chuyển thành DSL.

Ví dụ trong miền bán hàng:

- Một đơn hàng chỉ được xác nhận khi có ít nhất một sản phẩm.
- Khách hàng hạng Gold được giảm giá 10% cho sản phẩm đủ điều kiện.
- Đơn hàng có tổng giá trị từ 2.000.000 đồng được miễn phí vận chuyển.
- Không chấp nhận thanh toán nếu phương thức thanh toán đã hết hiệu lực.

Các phát biểu này mô tả chính sách bán hàng. Chúng khác với yêu cầu kỹ thuật như “dùng HTTP/2”, “lưu cache trong 30 giây” hoặc “mã hóa dữ liệu bằng thuật toán cụ thể”. Một quy tắc nghiệp vụ có thể dẫn đến một lựa chọn kỹ thuật, nhưng bản thân nó được xác định bởi ý nghĩa và mục tiêu của miền.

Quy tắc thường có ba thành phần cơ bản:

1. **Điều kiện:** hoàn cảnh hoặc dữ liệu cần được xem xét.
2. **Kết luận hoặc kết quả:** điều được xác định khi điều kiện thỏa mãn.
3. **Phạm vi và ngoại lệ:** đối tượng, thời điểm, kênh hoặc trường hợp mà quy tắc áp dụng, cùng những tình huống được miễn trừ.

Chẳng hạn, “Nếu khách hàng thuộc hạng Gold và sản phẩm nằm trong danh sách khuyến mãi, áp dụng mức giảm 10% cho sản phẩm đó” có điều kiện là hạng khách hàng và trạng thái sản phẩm; kết quả là mức giảm; phạm vi là sản phẩm đủ điều kiện trong chương trình. Nếu chính sách có giới hạn thời gian, giới hạn số lượng hoặc ngoại lệ, những yếu tố đó cũng phải được mô tả.

## 2. Phân biệt quy tắc nghiệp vụ với logic kỹ thuật

Trong một hệ thống phần mềm, logic nghiệp vụ và logic kỹ thuật cùng tồn tại nhưng giải quyết những câu hỏi khác nhau.

| Loại logic | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Quy tắc nghiệp vụ | Tổ chức muốn quyết định hoặc yêu cầu điều gì? | Đơn hàng trên 2.000.000 đồng được miễn phí vận chuyển |
| Kiểm tra hợp lệ của miền | Dữ liệu có hợp lệ theo khái niệm của miền không? | Số lượng đặt hàng phải lớn hơn 0 |
| Logic ứng dụng | Khi nào và theo trình tự nào các chức năng được gọi? | Sau khi đơn hàng được xác nhận, tạo yêu cầu thanh toán |
| Chi tiết kỹ thuật | Hệ thống hiện thực chức năng bằng cách nào? | Gửi yêu cầu HTTP tới cổng thanh toán và ghi log |

Ranh giới giữa các nhóm có thể phụ thuộc vào hệ thống. Ví dụ, quy tắc “một tài khoản chỉ được có tối đa ba phiên đăng nhập đang hoạt động” có thể là chính sách bảo mật của tổ chức. Việc lưu bộ đếm phiên trong Redis là chi tiết kỹ thuật. DSL quản lý chính sách tài khoản có thể biểu diễn giới hạn ba phiên, nhưng không nhất thiết phải mô tả cách Redis hoạt động.

Một cách phân biệt hữu ích là hỏi liệu chuyên gia miền có thể xác nhận phát biểu đó là đúng hoặc sai dựa trên chính sách và hoạt động của tổ chức hay không. Nếu câu trả lời phụ thuộc chủ yếu vào thư viện, giao thức, cấu trúc dữ liệu hoặc nền tảng triển khai, nội dung đó thường thuộc tầng kỹ thuật.

## 3. Các dạng quy tắc thường gặp

Quy tắc nghiệp vụ có thể đảm nhiệm nhiều vai trò. Việc phân loại giúp chọn cách biểu diễn phù hợp trong DSL.

### 3.1. Quy tắc ràng buộc

Quy tắc ràng buộc (constraint rule) xác định điều kiện bắt buộc hoặc giới hạn không được vi phạm. Nó thường dùng để xác thực dữ liệu hoặc ngăn một trạng thái không hợp lệ.

Ví dụ:

- Số lượng của một dòng hàng phải là số nguyên dương.
- Ngày kết thúc hợp đồng không được trước ngày bắt đầu.
- Một tài khoản bị khóa không được tạo giao dịch mới.

Một ràng buộc có thể được kiểm tra khi nhập dữ liệu, khi lưu dữ liệu hoặc ngay trước khi thực hiện hành động. DSL cần xác định thời điểm kiểm tra và cách báo lỗi để người dùng biết dữ liệu nào vi phạm quy tắc.

### 3.2. Quy tắc suy diễn

Quy tắc suy diễn (derivation rule) tạo ra một giá trị hoặc kết luận từ những dữ kiện đã biết.

Ví dụ:

- Thành tiền của dòng hàng bằng đơn giá nhân số lượng.
- Khách hàng được xếp hạng Silver nếu tổng chi tiêu trong năm đạt ngưỡng quy định.
- Đơn hàng được đánh dấu là giao hàng ưu tiên nếu thỏa mãn điều kiện về loại dịch vụ và địa chỉ.

Quy tắc suy diễn nên nêu rõ dữ liệu đầu vào, công thức hoặc điều kiện, kiểu kết quả và cách xử lý trường hợp thiếu dữ liệu. Cần tránh để hai quy tắc cùng tính một giá trị theo các công thức khác nhau mà không có cơ chế xác định quy tắc có hiệu lực.

### 3.3. Quy tắc quyết định

Quy tắc quyết định (decision rule) ánh xạ một hoặc nhiều điều kiện sang một kết quả, chẳng hạn phê duyệt, từ chối, phân loại hoặc chọn mức phí.

Ví dụ, một chính sách xét duyệt có thể quyết định hạn mức theo điểm tín dụng và thu nhập. Khi có nhiều điều kiện kết hợp, bảng quyết định thường dễ đọc và dễ đối chiếu hơn một chuỗi điều kiện lồng nhau.

### 3.4. Quy tắc hành động và phản ứng sự kiện

Một số quy tắc xác định hành động cần thực hiện khi một sự kiện xảy ra, chẳng hạn tạo yêu cầu rà soát khi giao dịch vượt ngưỡng hoặc gửi hồ sơ sang bước kiểm tra thủ công. Đây là dạng quy tắc có thể gây ra hiệu ứng bên ngoài.

Cần phân biệt quyết định nghiệp vụ với hành động kỹ thuật thực thi quyết định. Quy tắc có thể phát biểu “yêu cầu kiểm tra thủ công”; ứng dụng hoặc bộ thực thi chịu trách nhiệm tạo tác vụ, gửi thông báo và ghi nhận kết quả. Cách tách này giúp quy tắc dễ kiểm thử và tránh để một lần đánh giá lặp lại vô tình gửi nhiều thông báo hoặc tạo nhiều giao dịch.

## 4. Biểu diễn quy tắc trong DSL

DSL có thể cung cấp nhiều hình thức biểu diễn. Lựa chọn phụ thuộc vào độ phức tạp của chính sách, người viết quy tắc và nhu cầu kiểm tra.

### 4.1. Biểu thức điều kiện

Với quy tắc đơn giản, biểu thức điều kiện thường đủ rõ ràng:

```text
rule "free-shipping" {
    when order.total >= 2000000
    then order.shippingFee = 0
}
```

Đoạn DSL trên mô tả rằng khi tổng giá trị đơn hàng đạt ngưỡng, phí vận chuyển được đặt bằng không. Các tên `order.total` và `order.shippingFee` là khái niệm của miền. DSL có thể kiểm tra kiểu dữ liệu, đơn vị tiền tệ, quyền cập nhật trường và ngưỡng hợp lệ.

Một DSL khác có thể dùng dạng gần với câu tự nhiên:

```text
when order.total is at least 2_000_000 VND
then shipping is free
```

Cú pháp cụ thể có thể khác nhau, nhưng ngữ nghĩa phải rõ: giá trị được so sánh là tổng trước hay sau chiết khấu, ngưỡng có bao gồm giá trị bằng ngưỡng hay không, và quy tắc áp dụng cho loại đơn hàng nào.

### 4.2. Bảng quyết định

Khi một quyết định phụ thuộc vào nhiều điều kiện, bảng quyết định giúp thể hiện các tổ hợp một cách có hệ thống.

Ví dụ minh họa chính sách phí giao hàng:

| Tổng đơn hàng | Khu vực giao | Thành viên ưu tiên | Kết quả |
|---|---|---|---|
| Từ 2.000.000 đồng | Bất kỳ | Bất kỳ | Miễn phí |
| Dưới 2.000.000 đồng | Nội thành | Có | Miễn phí |
| Dưới 2.000.000 đồng | Nội thành | Không | Phí tiêu chuẩn |
| Dưới 2.000.000 đồng | Ngoại thành | Bất kỳ | Phí theo khu vực |

Bảng giúp chuyên gia nghiệp vụ nhận ra trường hợp còn thiếu hoặc các điều kiện chồng lấn. Khi chuyển thành DSL, cần định nghĩa rõ “Bất kỳ”, thứ tự ưu tiên nếu nhiều dòng cùng khớp và hành vi khi không có dòng nào khớp.

### 4.3. Cây quyết định

Cây quyết định biểu diễn các câu hỏi theo từng bước. Nó hữu ích khi một quyết định có thứ tự kiểm tra rõ ràng, chẳng hạn xác định hồ sơ có cần rà soát bổ sung hay không. Mỗi nút là một điều kiện, mỗi nhánh là một kết quả có thể xảy ra và mỗi lá là quyết định cuối cùng.

Cây có thể trực quan với một số lượng nhánh vừa phải. Nếu số điều kiện tăng nhanh, bảng quyết định hoặc tập quy tắc có cấu trúc có thể dễ quản lý hơn. Dù dùng hình thức nào, thứ tự đánh giá và đường đi đến kết quả phải có thể giải thích.

### 4.4. Tập quy tắc có cấu trúc

Một DSL có thể cho phép khai báo nhiều quy tắc độc lập:

```text
rule "minimum-order-value" {
    when order.itemCount == 0
    then reject order with "Đơn hàng phải có ít nhất một sản phẩm"
}

rule "gold-member-discount" {
    when customer.tier == Gold and item.isEligibleForPromotion
    then apply discount 10 percent to item
}
```

Cấu trúc này giúp đặt tên, mô tả, phân nhóm và quản lý phiên bản cho từng quy tắc. Tên quy tắc nên phản ánh mục đích nghiệp vụ. Phần mô tả có thể ghi nguồn chính sách, người sở hữu, ngày hiệu lực và lý do thay đổi.

## 5. Dữ liệu và ngữ cảnh để đánh giá quy tắc

Một quy tắc chỉ có thể được đánh giá đúng khi dữ liệu đầu vào có ý nghĩa và thời điểm rõ ràng. DSL cần xác định những dữ kiện nào có sẵn, chúng đến từ đâu và có thể thay đổi trong quá trình đánh giá hay không.

Các câu hỏi cần giải quyết gồm:

- **Kiểu dữ liệu:** số tiền, số lượng, ngày tháng, tỷ lệ và trạng thái được biểu diễn bằng kiểu nào?
- **Đơn vị:** giá trị tiền tệ thuộc loại tiền nào; thời lượng tính bằng giây, phút hay ngày; tỷ lệ dùng phần trăm hay số thập phân?
- **Dữ liệu thiếu:** nếu không biết hạng khách hàng hoặc không có ngày sinh thì điều kiện được xem là sai, không xác định hay gây lỗi?
- **Thời điểm:** quy tắc dùng dữ liệu tại lúc tạo đơn, lúc thanh toán hay lúc xử lý?
- **Nguồn dữ liệu:** dữ kiện được lấy từ hồ sơ, giao dịch, cấu hình hay dịch vụ bên ngoài?
- **Tính nhất quán:** các dữ kiện được đọc từ cùng một trạng thái dữ liệu hay có thể thuộc những thời điểm khác nhau?

Ví dụ, quy tắc “khách hàng được giảm giá nếu là thành viên Gold” cần biết hạng thành viên tại thời điểm áp dụng ưu đãi. Nếu hạng thành viên thay đổi giữa lúc tạo đơn và lúc thanh toán, hệ thống phải có chính sách rõ ràng về thời điểm chốt hạng.

Giá trị chưa biết cần được xử lý tường minh. Nếu DSL âm thầm coi dữ liệu thiếu là `false`, một chính sách có thể từ chối hoặc chấp thuận sai. Một số DSL sử dụng logic ba giá trị (`true`, `false`, `unknown`) hoặc yêu cầu dữ liệu bắt buộc phải được xác thực trước khi đánh giá. Lựa chọn nào cũng cần được ghi rõ trong ngữ nghĩa của ngôn ngữ.

## 6. Ngữ nghĩa đánh giá và xung đột quy tắc

Khi có nhiều quy tắc cùng áp dụng, DSL phải xác định cách chúng được đánh giá và cách kết hợp kết quả. Nếu không, chương trình có thể cho kết quả khác nhau tùy thứ tự thực thi hoặc cách cài đặt runtime.

### 6.1. Thứ tự đánh giá

Có nhiều mô hình thường gặp:

- **Đánh giá theo thứ tự khai báo:** quy tắc được xử lý theo vị trí xuất hiện trong tài liệu.
- **Ưu tiên tường minh:** mỗi quy tắc có mức ưu tiên; quy tắc có ưu tiên cao hơn được xét trước hoặc có quyền quyết định trước.
- **Đánh giá đồng thời theo tập điều kiện:** hệ thống tìm tất cả quy tắc phù hợp rồi áp dụng chính sách kết hợp đã định nghĩa.
- **Suy diễn theo dữ kiện mới:** kết quả của quy tắc này có thể trở thành dữ kiện để kích hoạt quy tắc khác.

Mỗi mô hình có ưu điểm và rủi ro riêng. Thứ tự khai báo dễ hiểu nhưng có thể khiến việc sắp xếp lại tệp làm thay đổi kết quả. Ưu tiên tường minh dễ điều khiển hơn nhưng cần quy ước xử lý khi hai quy tắc có cùng mức ưu tiên. Suy diễn nhiều bước linh hoạt nhưng cần kiểm soát vòng lặp và điều kiện dừng.

### 6.2. Quy tắc xung đột

Xung đột xảy ra khi nhiều quy tắc cùng áp dụng nhưng đưa ra kết quả không tương thích. Ví dụ, một quy tắc đặt phí vận chuyển bằng không trong khi quy tắc khác yêu cầu tính phí theo khu vực. DSL cần xác định một chính sách giải quyết xung đột như ưu tiên, phạm vi cụ thể hơn, loại trừ lẫn nhau hoặc báo lỗi khi có cấu hình mâu thuẫn.

Không nên để runtime tự chọn một quy tắc tùy ý. Nếu một trường chỉ được có một giá trị cuối cùng, ngôn ngữ nên phát hiện trường hợp nhiều quy tắc cùng ghi trường đó mà không có cơ chế kết hợp. Nếu nhiều quy tắc được phép cộng dồn, chẳng hạn các khoản phụ phí độc lập, phép kết hợp cũng phải được quy định rõ.

### 6.3. Vòng lặp và chuỗi suy diễn

Trong mô hình suy diễn, quy tắc A có thể tạo dữ kiện kích hoạt quy tắc B, rồi quy tắc B lại làm thay đổi điều kiện của A. Nếu không có giới hạn, quá trình có thể lặp vô hạn hoặc tạo kết quả không ổn định.

DSL có thể ngăn chu trình phụ thuộc, giới hạn số bước đánh giá, chỉ cho phép một số loại kết quả được dùng làm dữ kiện mới, hoặc yêu cầu quy tắc phải có tính đơn điệu trong một số mô hình suy diễn. Thông báo lỗi cần chỉ ra chuỗi quy tắc gây ra vấn đề để người viết sửa được cấu hình.

## 7. Kiểm tra quy tắc và thông báo lỗi

Quy tắc nghiệp vụ nên được kiểm tra ở nhiều giai đoạn. Một số lỗi có thể phát hiện trước khi chạy; những lỗi khác chỉ xuất hiện khi có dữ liệu thực tế.

**Kiểm tra tĩnh** có thể phát hiện:

- Cú pháp không hợp lệ hoặc thiếu thành phần bắt buộc.
- Tham chiếu đến trường, kiểu hoặc đối tượng không tồn tại.
- So sánh các kiểu không tương thích.
- Dùng đơn vị không phù hợp, chẳng hạn so sánh tiền tệ khác loại mà không có chuyển đổi được quy định.
- Quy tắc trùng tên, điều kiện không thể thỏa mãn hoặc xung đột có thể xác định từ cấu hình.

**Kiểm tra khi chạy** có thể phát hiện:

- Dữ liệu đầu vào thiếu hoặc nằm ngoài phạm vi cho phép.
- Không lấy được dữ kiện bắt buộc từ nguồn bên ngoài.
- Không có quy tắc nào xử lý trường hợp hiện tại.
- Nhiều quy tắc tạo ra kết quả mâu thuẫn.
- Lỗi khi thực hiện hành động được yêu cầu sau quyết định.

Thông báo lỗi tốt nên nêu tên quy tắc, dữ liệu hoặc điều kiện liên quan, giá trị thực tế nếu an toàn để hiển thị, và cách khắc phục. Ví dụ: “Quy tắc `minimum-order-value` từ chối đơn hàng vì không có dòng sản phẩm” hữu ích hơn thông báo chung chung “Rule failed”.

Cần phân biệt lỗi cấu hình quy tắc với kết quả từ chối hợp lệ. Một đơn hàng không đủ điều kiện ưu đãi có thể là kết quả nghiệp vụ bình thường, trong khi biểu thức tham chiếu trường không tồn tại là lỗi của chương trình DSL. Việc phân loại rõ ràng giúp ứng dụng quyết định có thể tiếp tục, yêu cầu người dùng sửa dữ liệu hay cần quản trị viên sửa chính sách.

## 8. Kiểm thử và giải thích kết quả

Quy tắc thường chứa những chính sách quan trọng, vì vậy cần có cách kiểm thử độc lập với các thành phần kỹ thuật bên dưới.

Một bộ kiểm thử nên bao gồm:

- **Trường hợp điển hình:** dữ liệu phổ biến và kết quả mong đợi.
- **Biên của điều kiện:** ngay dưới, bằng và ngay trên ngưỡng.
- **Ngoại lệ:** đối tượng được miễn trừ hoặc thuộc phạm vi đặc biệt.
- **Dữ liệu thiếu và sai kiểu:** xác nhận hành vi khi không đủ thông tin.
- **Điều kiện chồng lấn:** nhiều quy tắc cùng khớp.
- **Không có quy tắc phù hợp:** xác nhận hành vi mặc định.
- **Thay đổi thời gian:** quy tắc bắt đầu hoặc hết hiệu lực tại thời điểm xác định.

Ví dụ cho ngưỡng miễn phí vận chuyển 2.000.000 đồng, nên thử các tổng đơn hàng 1.999.999, 2.000.000 và 2.000.001 đồng. Ba trường hợp này làm rõ điều kiện là “lớn hơn” hay “lớn hơn hoặc bằng”.

Ngoài kết quả cuối cùng, hệ thống có thể cung cấp dấu vết đánh giá (rule trace): dữ kiện đã sử dụng, quy tắc nào được xét, điều kiện nào đúng hoặc sai, quy tắc nào được kích hoạt và lý do kết quả được chọn. Dấu vết giúp chuyên gia nghiệp vụ xác minh chính sách và giúp kỹ sư tìm lỗi. Cần giới hạn dữ liệu nhạy cảm trong log và chỉ cho người có quyền xem những thông tin phù hợp.

## 9. Vòng đời và quản lý thay đổi quy tắc

Chính sách nghiệp vụ thường thay đổi theo thị trường, hợp đồng, quy định hoặc quyết định nội bộ. Nếu quy tắc được nhúng rải rác trong mã nguồn, việc tìm kiếm và cập nhật có thể tốn thời gian, đồng thời dễ tạo ra các phiên bản chính sách không nhất quán.

Một vòng đời quản lý quy tắc có thể gồm:

1. **Thu thập:** ghi nhận chính sách từ người có thẩm quyền và xác định mục tiêu.
2. **Làm rõ:** chuyển phát biểu tự nhiên thành điều kiện, kết quả, phạm vi và ngoại lệ không mơ hồ.
3. **Mô hình hóa:** chọn biểu thức, bảng quyết định hoặc cấu trúc quy tắc phù hợp trong DSL.
4. **Xác thực:** chuyên gia miền xác nhận ý nghĩa; công cụ kiểm tra cú pháp, kiểu và xung đột.
5. **Kiểm thử:** chạy các trường hợp điển hình, biên, ngoại lệ và hồi quy.
6. **Phê duyệt và phát hành:** ghi nhận người phê duyệt, phiên bản và thời điểm hiệu lực.
7. **Theo dõi:** xem kết quả thực tế, dấu vết đánh giá và phản hồi để phát hiện vấn đề.

Một quy tắc có thể cần các thuộc tính quản trị như mã định danh ổn định, tên dễ đọc, mô tả, chủ sở hữu, nguồn chính sách, phiên bản, trạng thái và khoảng thời gian hiệu lực. Không phải DSL nào cũng cần tất cả các trường này, nhưng những hệ thống có chính sách thay đổi thường xuyên nên xem xét chúng từ đầu.

Khi cập nhật quy tắc, cần xác định thay đổi áp dụng cho giao dịch mới hay cả giao dịch đang xử lý. Phiên bản quy tắc đã dùng để đưa ra một quyết định quan trọng có thể cần được lưu lại để giải thích hoặc kiểm toán sau này. Nếu một quy tắc có hiệu lực từ ngày cụ thể, hệ thống phải xác định múi giờ và cách xử lý thời điểm bắt đầu, kết thúc.

## 10. Ví dụ tổng hợp: DSL xét điều kiện đơn hàng

Giả sử một cửa hàng dùng DSL để mô tả các chính sách cơ bản khi xác nhận đơn hàng:

```text
rule "order-must-have-items" {
    when order.items.count == 0
    then reject order with "Đơn hàng phải có ít nhất một sản phẩm"
}

rule "positive-quantity" {
    when exists item in order.items where item.quantity <= 0
    then reject order with "Số lượng sản phẩm phải lớn hơn 0"
}

rule "gold-discount" {
    when customer.tier == Gold
         and order.createdAt is within promotion.activePeriod
    then apply 10 percent discount to eligible items
}

rule "free-shipping" {
    when order.totalAfterDiscount >= 2000000 VND
    then set order.shippingFee to 0 VND
}
```

Ví dụ này cho thấy nhiều dạng quy tắc cùng tồn tại: ràng buộc về sản phẩm, kiểm tra số lượng, áp dụng chính sách chiết khấu và suy ra phí vận chuyển. Các tên `order`, `customer`, `promotion` và `item` thuộc mô hình miền. DSL phải định nghĩa rõ `totalAfterDiscount` được tính ở bước nào, `activePeriod` bao gồm hai đầu mút hay không, và các quy tắc từ chối được ưu tiên so với quy tắc tính ưu đãi như thế nào.

Một quy trình đánh giá có thể thực hiện theo các giai đoạn:

1. Kiểm tra dữ liệu đơn hàng và các ràng buộc cơ bản.
2. Nếu dữ liệu hợp lệ, xác định các chương trình ưu đãi đang có hiệu lực.
3. Tính chiết khấu cho các sản phẩm đủ điều kiện.
4. Tính tổng sau chiết khấu.
5. Đánh giá quy tắc phí vận chuyển.
6. Trả về quyết định cùng lý do và dấu vết quy tắc đã áp dụng.

Thứ tự trên là một chính sách thực thi cần được đặc tả. Nếu DSL cho phép các quy tắc tự chạy theo thứ tự bất kỳ, nó phải có cơ chế phụ thuộc hoặc giai đoạn để bảo đảm `totalAfterDiscount` đã được tính trước khi đánh giá phí vận chuyển.

Ví dụ cũng cho thấy quy tắc nghiệp vụ không nên tự ý thực hiện mọi thao tác của ứng dụng. DSL có thể quyết định đơn hàng hợp lệ và xác định mức phí. Ứng dụng thương mại điện tử sau đó chịu trách nhiệm lưu đơn, gọi cổng thanh toán và gửi thông báo theo hợp đồng tích hợp.

## 11. Nguyên tắc thiết kế quy tắc trong DSL

Một DSL hỗ trợ quy tắc nghiệp vụ tốt nên hướng đến những nguyên tắc sau:

- **Dùng từ vựng của miền:** tên đối tượng, thuộc tính và hành động phải gần với cách người làm nghiệp vụ gọi chúng.
- **Một quy tắc có một mục đích rõ:** đặt tên theo quyết định hoặc chính sách mà quy tắc thể hiện.
- **Diễn đạt điều kiện tường minh:** tránh ngầm hiểu về đơn vị, thời điểm, phạm vi và dữ liệu thiếu.
- **Kết quả có thể dự đoán:** quy định thứ tự, ưu tiên, kết hợp và trường hợp không có quy tắc phù hợp.
- **Lỗi có thể giải thích:** chỉ ra quy tắc và điều kiện liên quan thay vì chỉ báo lỗi thực thi chung.
- **Có thể kiểm thử độc lập:** cho phép đưa dữ liệu đầu vào và xác nhận kết quả mong đợi mà không cần chạy toàn bộ hệ thống.
- **Thay đổi có kiểm soát:** lưu phiên bản, nguồn chính sách, thời điểm hiệu lực và thông tin phê duyệt khi cần.
- **Giới hạn hiệu ứng:** tách quyết định khỏi hành động kỹ thuật có tác động bên ngoài, đồng thời kiểm soát quyền và dữ liệu mà bộ thực thi có thể truy cập.

Quy tắc nghiệp vụ là cách đưa chính sách và tri thức của một miền vào chương trình có cấu trúc. Khi DSL biểu diễn được điều kiện, kết quả, ngoại lệ và thời điểm áp dụng một cách rõ ràng, chuyên gia miền có thể đọc và xác nhận chính sách, còn hệ thống có thể kiểm tra và thực thi chính sách nhất quán. Ranh giới tốt giữ cho quy tắc tập trung vào quyết định nghiệp vụ, trong khi ứng dụng và hạ tầng đảm nhiệm các chi tiết tích hợp và vận hành.

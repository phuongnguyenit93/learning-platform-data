# Xác định yêu cầu và phạm vi kiểm tra khả năng truy cập

Trong module `VALIDATION_TESTING_STRATEGY`, kiểm thử khả năng truy cập (accessibility testing, thường viết tắt là a11y testing) xác nhận rằng người dùng có thể nhận biết thông tin, điều hướng, hiểu và sử dụng sản phẩm trong những điều kiện và cách tương tác khác nhau, bao gồm cả khi họ sử dụng công nghệ hỗ trợ. Khả năng truy cập là một thuộc tính chất lượng của sản phẩm, đồng thời ảnh hưởng trực tiếp đến khả năng hoàn thành các công việc nghiệp vụ.

Không thể xác định phạm vi kiểm tra chỉ bằng cách chạy một công cụ quét trên trang web. Công cụ tự động có thể phát hiện một số lỗi về cấu trúc, nhãn, tương phản hoặc thuộc tính, nhưng khó đánh giá đầy đủ ý nghĩa nội dung, thứ tự đọc, khả năng thao tác bằng bàn phím, trải nghiệm với trình đọc màn hình và tính dễ hiểu của quy trình. Phạm vi kiểm tra cần được xây dựng từ yêu cầu, người dùng, hành trình quan trọng, nền tảng hỗ trợ, tiêu chuẩn áp dụng và mức rủi ro.

Bài học này trình bày cách xác định yêu cầu khả năng truy cập, lựa chọn tiêu chuẩn và mức phù hợp, xác định hành trình và thành phần cần kiểm tra, phân bổ kiểm thử tự động và thủ công, chọn công nghệ hỗ trợ, xác định bằng chứng và ghi nhận rủi ro còn lại. Mục tiêu là chuyển kỳ vọng về khả năng truy cập thành các điều kiện có thể xác minh và một phạm vi kiểm thử phù hợp với sản phẩm.

## 1. Hiểu khả năng truy cập và mục tiêu kiểm thử

### 1.1. Khả năng truy cập là gì?

Khả năng truy cập (accessibility) là mức độ một sản phẩm, dịch vụ hoặc nội dung có thể được nhận biết, hiểu và sử dụng bởi nhiều người, bao gồm người có khuyết tật hoặc có nhu cầu tiếp cận khác nhau. Nhu cầu đó có thể liên quan đến thị giác, thính giác, vận động, lời nói, nhận thức, học tập hoặc thần kinh; cũng có thể xuất hiện tạm thời hoặc theo bối cảnh.

Ví dụ:

- Người mù có thể dùng trình đọc màn hình để nghe tên, vai trò, trạng thái và nội dung của điều khiển.
- Người thị lực kém có thể phóng to văn bản hoặc tăng độ tương phản mà vẫn đọc và thao tác được.
- Người hạn chế vận động có thể sử dụng bàn phím hoặc công tắc thay cho chuột và thao tác chạm phức tạp.
- Người điếc hoặc nghe kém có thể tiếp cận nội dung video qua phụ đề và nội dung âm thanh qua bản chép lời phù hợp.
- Người có khó khăn về nhận thức có thể cần ngôn ngữ rõ ràng, bố cục nhất quán, hướng dẫn dễ hiểu và thông báo lỗi cụ thể.
- Người nhạy cảm với chuyển động có thể cần giảm hoạt ảnh hoặc tránh nội dung nhấp nháy gây khó chịu.

Khả năng truy cập không chỉ phục vụ một nhóm nhỏ. Tính năng như phụ đề có ích trong môi trường ồn; điều hướng bằng bàn phím có ích khi thiết bị trỏ không hoạt động; nội dung rõ ràng có ích khi người dùng đang căng thẳng hoặc sử dụng màn hình nhỏ.

### 1.2. Mục tiêu của kiểm thử khả năng truy cập

Kiểm thử cần trả lời những câu hỏi thực tế:

- Người dùng có thể tìm và nhận biết thông tin quan trọng không?
- Có thể điều hướng và hoàn thành tác vụ bằng phương thức tương tác được hỗ trợ không?
- Công nghệ hỗ trợ có thể hiểu tên, vai trò, giá trị, trạng thái và thứ tự nội dung không?
- Thông báo, lỗi và trạng thái thay đổi có được truyền đạt không?
- Nội dung có thể được đọc và hiểu ở kích thước, độ tương phản và bố cục phù hợp không?
- Người dùng có đủ thời gian và cách xử lý khi phiên hoặc nội dung tự thay đổi không?
- Các hành trình quan trọng có thể hoàn thành mà không bị chặn bởi một lỗi truy cập không?

Một trang có màu sắc đẹp hoặc vượt qua công cụ quét chưa chắc đã truy cập được. Cần kiểm tra khả năng hoàn thành công việc thực tế, ví dụ đăng ký, tìm kiếm, đặt hàng, thanh toán, gửi biểu mẫu hoặc xem báo cáo.

### 1.3. Khả năng truy cập là yêu cầu sản phẩm, không chỉ là công việc giao diện

Lỗi truy cập có thể nằm ở nhiều lớp:

| Lớp | Ví dụ vấn đề | Hướng kiểm tra |
|---|---|---|
| Nội dung | Hướng dẫn khó hiểu, hình ảnh thiếu mô tả thay thế | Rà soát nội dung và ngữ cảnh |
| Thiết kế | Tương phản thấp, thông tin chỉ dùng màu sắc | Kiểm tra thị giác và quy tắc thiết kế |
| Giao diện | Điều khiển không có tên truy cập, focus bị mất | Kiểm thử DOM/accessibility tree và công nghệ hỗ trợ |
| Tương tác | Không thể dùng bàn phím hoặc thao tác chạm | Kiểm thử bằng các phương thức nhập liệu |
| Logic nghiệp vụ | CAPTCHA không có cách thay thế, timeout không thể gia hạn | Rà soát quy trình và chính sách |
| Dữ liệu | Trạng thái hoặc lỗi không được thông báo cho công nghệ hỗ trợ | Kiểm tra cập nhật và thông báo trạng thái |
| Nền tảng | Ứng dụng không tương thích với trình đọc màn hình trên thiết bị hỗ trợ | Kiểm thử trên tổ hợp thiết bị và công nghệ hỗ trợ |

Vì vậy, yêu cầu khả năng truy cập cần được xem xét từ phân tích, thiết kế, nội dung, phát triển, kiểm thử và vận hành.

## 2. Xác định tiêu chuẩn và mức yêu cầu áp dụng

### 2.1. WCAG và bốn nguyên tắc nền tảng

Web Content Accessibility Guidelines (WCAG) của W3C là bộ hướng dẫn phổ biến để đánh giá khả năng truy cập nội dung web. WCAG tổ chức tiêu chí theo bốn nguyên tắc, thường được gọi là POUR:

- **Perceivable – Có thể nhận biết:** thông tin và thành phần giao diện phải được trình bày theo cách người dùng có thể nhận biết.
- **Operable – Có thể thao tác:** các thành phần và điều hướng phải có thể sử dụng được.
- **Understandable – Có thể hiểu:** thông tin và cách vận hành giao diện phải dễ hiểu, có thể dự đoán.
- **Robust – Tương thích bền vững:** nội dung phải được diễn giải đáng tin cậy bởi trình duyệt và công nghệ hỗ trợ hiện tại cũng như tương lai.

Bốn nguyên tắc này giúp nhóm phân loại yêu cầu và phát hiện khoảng trống. Chúng không thay thế việc đọc tiêu chí thành công cụ thể trong phiên bản WCAG được dự án lựa chọn.

### 2.2. Chọn phiên bản và mức phù hợp

WCAG có các phiên bản và mức phù hợp. Các mức A, AA và AAA biểu thị mức yêu cầu tăng dần. Trong nhiều dự án web, WCAG 2.2 mức AA được dùng làm mục tiêu phổ biến, nhưng mục tiêu thực tế phải được xác định theo luật, hợp đồng, chính sách tổ chức, thị trường và phạm vi sản phẩm.

- **Level A:** các tiêu chí nền tảng nhằm loại bỏ những rào cản nghiêm trọng.
- **Level AA:** bổ sung các tiêu chí thường được dùng làm mục tiêu phù hợp thực tế cho nhiều sản phẩm.
- **Level AAA:** mức cao hơn với yêu cầu chặt hơn; không phải lúc nào cũng khả thi hoặc áp dụng đồng đều cho toàn bộ nội dung.

Không nên tự tuyên bố sản phẩm “đạt WCAG” nếu chưa xác định phiên bản, mức, phạm vi trang hoặc luồng, cách đánh giá và các ngoại lệ được chấp nhận. Nếu sản phẩm chịu điều chỉnh bởi một quy định cụ thể, cần xác nhận chính xác tiêu chuẩn và phiên bản được viện dẫn với bộ phận pháp lý hoặc người có thẩm quyền.

WCAG được thiết kế cho nội dung web. Ứng dụng native, tài liệu PDF, kiosk, thiết bị nhúng hoặc nội dung bên thứ ba có thể cần tiêu chuẩn, hướng dẫn nền tảng và phương pháp đánh giá bổ sung.

### 2.3. Chuyển tiêu chuẩn thành yêu cầu dự án

Không nên đưa toàn bộ danh sách tiêu chí vào mọi tính năng mà không xét ngữ cảnh. Hãy xác định:

1. Phiên bản hướng dẫn được áp dụng.
2. Mức phù hợp mục tiêu.
3. Loại sản phẩm và nền tảng trong phạm vi.
4. Hành trình, trang, nội dung và thành phần được đánh giá.
5. Tiêu chí nào áp dụng, không áp dụng hoặc cần đánh giá riêng.
6. Bằng chứng cần có và người có thẩm quyền chấp nhận.
7. Cách xử lý nội dung bên thứ ba hoặc ngoại lệ.

Ví dụ yêu cầu dự án:

| Thành phần yêu cầu | Nội dung minh họa |
|---|---|
| Tiêu chuẩn | WCAG 2.2 |
| Mục tiêu | Level AA cho phạm vi ứng dụng web đã xác định |
| Nền tảng | Trình duyệt và thiết bị trong ma trận hỗ trợ |
| Hành trình ưu tiên | Đăng nhập, tìm kiếm, đặt hàng, thanh toán, quản lý tài khoản |
| Phương pháp | Quét tự động, rà soát thủ công, bàn phím, trình đọc màn hình và phóng to |
| Bằng chứng | Danh sách tiêu chí, kết quả từng hành trình, lỗi và ảnh/chứng cứ phù hợp |
| Ngoại lệ | Ghi rõ phạm vi, lý do, người phê duyệt và kế hoạch xử lý |

Bảng này là ví dụ cách ghi yêu cầu, không phải tuyên bố rằng một cấu hình cụ thể phù hợp với mọi tổ chức.

### 2.4. Phân biệt tuân thủ tiêu chuẩn và khả năng sử dụng thực tế

Đạt một tập tiêu chí kỹ thuật là cơ sở quan trọng nhưng không tự động bảo đảm trải nghiệm tốt cho mọi người. Một biểu mẫu có nhãn hợp lệ vẫn có thể dùng ngôn ngữ khó hiểu; một trang có thể điều hướng bằng bàn phím nhưng thứ tự focus gây nhầm lẫn; một biểu đồ có mô tả thay thế nhưng không cung cấp dữ liệu đủ ý nghĩa.

Vì vậy, nên kết hợp:

- Đánh giá theo tiêu chuẩn và tiêu chí thành công.
- Kiểm thử hành trình và công việc thực tế.
- Đánh giá bằng công nghệ hỗ trợ.
- Phản hồi từ người dùng có nhu cầu truy cập khác nhau khi phù hợp.

## 3. Xác định người dùng, tác vụ và hành trình ưu tiên

### 3.1. Bắt đầu từ công việc người dùng cần hoàn thành

Xác định các tác nhân, mục tiêu và tác vụ quan trọng thay vì chỉ lập danh sách màn hình. Ví dụ với nền tảng thương mại điện tử:

| Người dùng hoặc nhu cầu | Tác vụ | Rào cản cần tìm |
|---|---|---|
| Người dùng trình đọc màn hình | Tìm sản phẩm và đặt hàng | Thiếu tên điều khiển, thứ tự đọc sai, thông báo không được đọc |
| Người dùng chỉ dùng bàn phím | Đăng nhập, chọn sản phẩm, thanh toán | Focus không nhìn thấy, điều khiển không nhận phím |
| Người dùng phóng to nội dung | Đọc chi tiết và hoàn tất biểu mẫu | Nội dung tràn ngang, nút bị che hoặc chồng lấp |
| Người dùng nghe kém | Xem video giới thiệu sản phẩm | Thiếu phụ đề hoặc thông tin chỉ truyền qua âm thanh |
| Người dùng cần ngôn ngữ rõ ràng | Tạo tài khoản và xử lý lỗi | Hướng dẫn mơ hồ, thông báo không chỉ ra cách sửa |
| Người dùng thiết bị di động | Duyệt và đặt hàng bằng thao tác chạm hoặc công nghệ hỗ trợ | Vùng chạm nhỏ, cử chỉ phức tạp, nhãn không phù hợp |

Không nên giả định mọi người trong một nhóm có cùng cách sử dụng. Nhu cầu và công nghệ hỗ trợ rất đa dạng; ma trận kiểm thử cần tập trung vào các phương thức và rủi ro liên quan đến sản phẩm.

### 3.2. Chọn hành trình có hậu quả cao

Ưu tiên các tác vụ mà người dùng cần hoàn thành để tiếp cận dịch vụ hoặc quyền lợi:

- Đăng ký, đăng nhập và khôi phục tài khoản.
- Tìm kiếm, lọc và đọc thông tin.
- Đặt hàng, thanh toán và nhận xác nhận.
- Gửi yêu cầu, tải tài liệu hoặc hoàn thành biểu mẫu.
- Quản lý hồ sơ, quyền riêng tư và cài đặt.
- Đặt lịch, hủy hoặc thay đổi dịch vụ.
- Xem trạng thái, thông báo và báo cáo.
- Liên hệ hỗ trợ hoặc xử lý sự cố.

Một lỗi trên trang đăng nhập hoặc thanh toán có thể chặn toàn bộ hành trình. Vì vậy, ưu tiên theo mức độ ảnh hưởng đến khả năng hoàn thành công việc, tần suất sử dụng, mức nhạy cảm của dữ liệu và khả năng có phương án thay thế.

### 3.3. Xác định các trạng thái của mỗi hành trình

Với từng tác vụ, kiểm tra cả:

- Trạng thái ban đầu và điều kiện truy cập.
- Luồng thành công.
- Dữ liệu không hợp lệ và lỗi xác thực.
- Trạng thái tải, chờ hoặc xử lý bất đồng bộ.
- Kết quả rỗng hoặc không có dữ liệu.
- Cảnh báo, xác nhận và hộp thoại.
- Trạng thái lỗi và cách khôi phục.
- Phiên hết hạn hoặc nội dung tự cập nhật.
- Kết quả hoàn tất và bằng chứng xác nhận.

Ví dụ, biểu mẫu đăng ký không chỉ cần kiểm tra trường nhập. Cần xác nhận người dùng có thể tìm lỗi, hiểu cách sửa, giữ lại dữ liệu hợp lệ và biết khi nào đăng ký hoàn tất.

### 3.4. Xác định nội dung ngoài giao diện chính

Phạm vi khả năng truy cập có thể cần bao gồm:

- Email và thông báo giao dịch.
- Tệp PDF, hóa đơn, báo cáo và tài liệu tải xuống.
- Video, âm thanh, phụ đề và bản chép lời.
- Biểu đồ, bản đồ, canvas hoặc nội dung trực quan.
- CAPTCHA, widget và nội dung nhúng của bên thứ ba.
- Nội dung trợ giúp, hướng dẫn và trang lỗi.
- Thông báo hệ thống và nội dung được tạo động.

Không nên chỉ kiểm tra các trang HTML chính nếu người dùng cần tải và đọc tài liệu hoặc tương tác với thành phần nhúng để hoàn thành công việc.

## 4. Xác định các nhóm tiêu chí cần kiểm tra

Các tiêu chí cụ thể phụ thuộc phiên bản và mức WCAG được chọn. Những nhóm dưới đây giúp lập phạm vi ban đầu; khi đánh giá tuân thủ, cần đối chiếu tiêu chí thành công chính thức và điều kiện áp dụng.

### 4.1. Khả năng nhận biết nội dung

Kiểm tra xem thông tin có thể được nhận biết qua nhiều cách hay không:

- Hình ảnh mang thông tin có văn bản thay thế phù hợp với mục đích.
- Hình ảnh trang trí được công nghệ hỗ trợ bỏ qua khi thích hợp.
- Video có phụ đề cho lời thoại và âm thanh quan trọng.
- Nội dung âm thanh có bản chép lời phù hợp.
- Thông tin không chỉ được truyền bằng màu sắc, hình dạng, vị trí hoặc âm thanh.
- Màu chữ và nền đạt yêu cầu tương phản áp dụng.
- Nội dung vẫn đọc được khi phóng to hoặc thay đổi khoảng cách văn bản trong điều kiện được yêu cầu.
- Nội dung đa phương tiện có điều khiển phù hợp và không tự phát âm thanh gây cản trở.
- Biểu đồ và nội dung trực quan có cách trình bày tương đương để hiểu dữ liệu.

Ví dụ: trường bắt buộc không chỉ được đánh dấu bằng viền đỏ; cần có nhãn hoặc thông báo thể hiện rõ trường đó bắt buộc.

### 4.2. Khả năng thao tác

Kiểm tra người dùng có thể điều khiển và điều hướng:

- Mọi chức năng cần thiết có thể thực hiện bằng bàn phím nếu tiêu chuẩn yêu cầu.
- Không có bẫy bàn phím khiến focus không thể thoát.
- Thứ tự focus hợp lý và theo trình tự nội dung.
- Focus nhìn thấy rõ khi điều hướng.
- Thành phần không bị che khuất bởi header, dialog hoặc vùng cố định.
- Có đủ thời gian thao tác hoặc cơ chế gia hạn khi cần.
- Chuyển động, nhấp nháy hoặc cập nhật tự động có thể dừng, tạm dừng hoặc kiểm soát theo yêu cầu.
- Vùng thao tác có kích thước và khoảng cách phù hợp theo tiêu chí áp dụng.
- Cử chỉ phức tạp có phương thức thay thế khi cần.

Ví dụ: người dùng phải có thể mở menu, chọn sản phẩm, thay đổi số lượng, gửi biểu mẫu và đóng hộp thoại chỉ bằng bàn phím.

### 4.3. Khả năng hiểu

Kiểm tra nội dung và cách vận hành có nhất quán:

- Ngôn ngữ chính của trang hoặc phần nội dung được khai báo phù hợp.
- Ngôn ngữ của đoạn khác biệt được nhận biết khi cần.
- Nhãn, hướng dẫn và tên điều khiển rõ ràng.
- Điều hướng và cách đặt tên nhất quán.
- Khi nhập sai, lỗi được xác định và mô tả bằng văn bản.
- Có gợi ý sửa lỗi khi phù hợp.
- Thao tác có hậu quả quan trọng có thể được xem lại, xác nhận hoặc đảo ngược theo tiêu chí áp dụng.
- Thành phần có cách vận hành có thể dự đoán.

Ví dụ: thông báo “Không hợp lệ” chưa đủ nếu không chỉ ra trường nào sai và cách khắc phục.

### 4.4. Tương thích với công nghệ hỗ trợ

Kiểm tra cấu trúc và ngữ nghĩa mà trình duyệt hoặc nền tảng cung cấp cho công nghệ hỗ trợ:

- Thành phần có tên truy cập (accessible name) phù hợp.
- Vai trò (role) và trạng thái được công bố chính xác.
- Quan hệ giữa nhãn, mô tả, nhóm trường và lỗi được thể hiện.
- Thứ tự đọc có ý nghĩa.
- Tiêu đề và landmark giúp điều hướng.
- Thông báo trạng thái động được công bố khi cần.
- Nội dung tùy chỉnh có semantics phù hợp.
- Các thay đổi trong DOM hoặc accessibility tree không làm mất trạng thái focus hoặc thông tin quan trọng.

Không nên thêm ARIA chỉ để làm cho một công cụ quét hết cảnh báo. Ưu tiên phần tử HTML ngữ nghĩa sẵn có; dùng ARIA khi cần và kiểm tra bằng công nghệ hỗ trợ thực tế.

## 5. Xác định phạm vi theo thành phần giao diện

Một số thành phần có rủi ro truy cập cao vì chứa nhiều tương tác hoặc trạng thái.

### 5.1. Điều hướng, menu và liên kết

Kiểm tra:

- Liên kết có tên mô tả mục tiêu.
- Menu có thể mở, đóng và điều hướng bằng phương thức được hỗ trợ.
- Trạng thái mở/đóng được công bố.
- Focus đi vào và ra khỏi menu hợp lý.
- Liên kết bỏ qua nội dung lặp (skip link) hoạt động khi cần.
- Cấu trúc heading và landmark giúp điều hướng.
- Liên kết không chỉ được phân biệt bằng màu nếu không đáp ứng tiêu chí.

### 5.2. Biểu mẫu

Kiểm tra:

- Mỗi trường có nhãn được liên kết đúng.
- Hướng dẫn và định dạng kỳ vọng được công bố.
- Trường bắt buộc được nhận biết bằng văn bản hoặc semantics.
- Lỗi được gắn với trường và được công bố.
- Khi submit thất bại, focus hoặc thông báo giúp người dùng tìm vị trí cần sửa.
- Dữ liệu hợp lệ không bị mất không cần thiết.
- Nhóm trường có tên và quan hệ rõ ràng.
- Captcha hoặc xác minh có phương án tiếp cận phù hợp.
- Không yêu cầu nhập lại thông tin đã cung cấp nếu tiêu chí áp dụng hạn chế điều đó.

### 5.3. Dialog, modal và popover

Kiểm tra:

- Khi mở, tên và vai trò được công bố.
- Focus được chuyển vào vùng tương tác phù hợp.
- Người dùng có thể thao tác và đóng bằng phương thức được hỗ trợ.
- Focus được trả về vị trí hợp lý khi đóng.
- Nội dung nền được xử lý đúng khi dialog là modal.
- Không có focus ẩn phía sau hoặc bị giữ ngoài ý muốn.
- Nội dung không bị che khuất khi phóng to.

### 5.4. Bảng, danh sách và dữ liệu phức tạp

Kiểm tra:

- Heading và cấu trúc hàng/cột được công bố.
- Quan hệ giữa tiêu đề và ô dữ liệu rõ ràng.
- Bảng có thể điều hướng trên màn hình nhỏ.
- Không dùng khoảng trắng hoặc ký tự trang trí để giả lập cấu trúc.
- Có cách thay thế hoặc mô tả phù hợp cho dữ liệu phức tạp.
- Kết quả sắp xếp và lọc được thông báo khi thay đổi.

### 5.5. Thành phần tùy chỉnh

Với combobox, date picker, tab, tree, slider hoặc widget tùy chỉnh, kiểm tra:

- Role và tên truy cập.
- Trạng thái mở, đóng, chọn, vô hiệu hóa.
- Phím điều hướng theo mẫu tương tác phù hợp.
- Focus và thứ tự thao tác.
- Thông báo khi giá trị thay đổi.
- Hành vi trên trình đọc màn hình và thiết bị mục tiêu.

Thành phần tùy chỉnh thường có rủi ro cao hơn điều khiển HTML gốc vì nhóm phải tự triển khai nhiều hành vi mặc định của nền tảng. Khi có thể, ưu tiên thành phần native hoặc thư viện đã được kiểm chứng và vẫn cần kiểm thử trong ngữ cảnh sản phẩm.

## 6. Chọn phương pháp kiểm thử tự động và thủ công

### 6.1. Kiểm tra tự động

Công cụ tự động có thể hỗ trợ phát hiện:

- Thiếu thuộc tính hoặc tên truy cập trong một số trường hợp.
- Cấu trúc heading hoặc landmark bất thường.
- Một số lỗi tương phản có thể tính toán.
- Giá trị ARIA hoặc thuộc tính không hợp lệ.
- Một số vi phạm cấu trúc và semantics.
- Một số lỗi có thể xác định từ DOM hoặc accessibility tree.

Công cụ tự động phù hợp để chạy lặp lại trên pull request, CI hoặc các trang đại diện. Tuy nhiên, chúng không thể xác nhận đầy đủ:

- Văn bản thay thế có mô tả đúng mục đích hình ảnh không.
- Thứ tự đọc có hợp lý với ý nghĩa nghiệp vụ không.
- Focus có dễ theo dõi và không bị che trong mọi trạng thái không.
- Hành trình có thể hoàn thành bằng bàn phím không.
- Trình đọc màn hình có đọc thông tin đúng và theo thứ tự dễ hiểu không.
- Hướng dẫn, nội dung và thông báo có dễ hiểu không.
- Người dùng thực tế có thể hoàn thành công việc không.

Do đó, kết quả quét tự động không phải chứng nhận khả năng truy cập.

### 6.2. Kiểm tra thủ công

Các hoạt động thủ công thường bao gồm:

- Điều hướng toàn bộ hành trình bằng bàn phím.
- Kiểm tra focus, thứ tự focus và khả năng thoát khỏi thành phần.
- Dùng trình đọc màn hình để đọc cấu trúc, nhãn, trạng thái và thông báo.
- Phóng to nội dung và kiểm tra reflow.
- Kiểm tra tương phản và trạng thái focus.
- Tắt CSS hoặc xem nội dung theo cách khác khi phù hợp.
- Kiểm tra phụ đề, bản chép lời và điều khiển media.
- Rà soát nội dung, ngôn ngữ và hướng dẫn.
- Kiểm tra với người dùng có nhu cầu truy cập khác nhau khi có điều kiện.

Thủ công không có nghĩa là chỉ quan sát bằng mắt. Một số kiểm tra cần bàn phím, trình đọc màn hình, cài đặt hệ điều hành hoặc thiết bị thật.

### 6.3. Kết hợp theo tầng

| Tầng | Kiểm tra phù hợp |
|---|---|
| Component | Tên truy cập, role, trạng thái, nhãn và hành vi bàn phím của thành phần |
| Page / feature | Heading, landmark, focus order, lỗi biểu mẫu, thông báo động |
| Journey / E2E | Hoàn thành tác vụ bằng bàn phím hoặc công nghệ hỗ trợ |
| System / platform | Tương thích trình duyệt, thiết bị, hệ điều hành và công nghệ hỗ trợ |
| Content review | Ngôn ngữ, văn bản thay thế, phụ đề, hướng dẫn và tài liệu |

Không nên chỉ chọn một tầng. Lỗi ở component có thể được phát hiện sớm; lỗi trong hành trình cần kiểm tra trong ngữ cảnh; lỗi về nội dung cần người hiểu nội dung đánh giá.

## 7. Chọn công nghệ hỗ trợ và ma trận nền tảng

### 7.1. Xác định tổ hợp hỗ trợ cần kiểm tra

Không thể kiểm tra mọi trình duyệt, hệ điều hành, thiết bị và công nghệ hỗ trợ. Hãy chọn ma trận dựa trên người dùng mục tiêu, nền tảng được hỗ trợ và rủi ro.

Ví dụ với web:

| Nền tảng | Công nghệ hỗ trợ / phương thức | Mục tiêu |
|---|---|---|
| Windows + trình duyệt được hỗ trợ | NVDA hoặc JAWS theo ma trận sản phẩm | Kiểm tra đọc nội dung, điều hướng và biểu mẫu |
| macOS + trình duyệt được hỗ trợ | VoiceOver | Kiểm tra accessibility tree và tương tác |
| iOS | VoiceOver và điều khiển chạm | Kiểm tra ứng dụng hoặc web mobile |
| Android | TalkBack | Kiểm tra tên, vai trò, trạng thái và thao tác |
| Máy tính | Chỉ dùng bàn phím, không dùng chuột | Xác nhận điều hướng và thao tác |
| Trình duyệt phóng to | Zoom và reflow | Xác nhận nội dung vẫn đọc và sử dụng được |

Ma trận thực tế cần dựa trên tổ hợp trình duyệt, hệ điều hành và công nghệ hỗ trợ mà tổ chức cam kết hỗ trợ. Các phiên bản phần mềm thay đổi có thể tạo khác biệt; hãy ghi phiên bản khi báo cáo.

### 7.2. Kiểm tra bằng bàn phím

Một vòng kiểm tra cơ bản:

1. Dùng Tab và Shift+Tab để di chuyển qua các điều khiển.
2. Quan sát vị trí focus ở mỗi bước.
3. Dùng Enter hoặc Space để kích hoạt thành phần phù hợp.
4. Dùng phím mũi tên hoặc phím tắt theo mẫu tương tác của widget.
5. Mở và đóng menu, dialog, dropdown và các thành phần tùy chỉnh.
6. Xác nhận không có bẫy bàn phím.
7. Kiểm tra focus không bị che bởi header, footer hoặc overlay.
8. Hoàn thành một hành trình quan trọng mà không dùng chuột.

Không nên chỉ thử Tab trên trang đầu. Cần kiểm tra các trạng thái động và nhánh lỗi vì focus thường bị mất sau khi cập nhật giao diện.

### 7.3. Kiểm tra với trình đọc màn hình

Tập trung vào:

- Tên, vai trò và trạng thái của điều khiển.
- Heading, landmark và thứ tự đọc.
- Nhãn và mô tả của trường biểu mẫu.
- Thông báo lỗi và thông báo trạng thái.
- Nội dung được tải động.
- Dialog, menu và widget tùy chỉnh.
- Thông tin không được truyền chỉ bằng hình ảnh hoặc màu sắc.
- Khả năng hoàn thành tác vụ mà không nhìn màn hình.

Cần ghi rõ công nghệ hỗ trợ và phiên bản đã dùng. Một trang hoạt động với một trình đọc màn hình không tự động chứng minh tương thích với mọi tổ hợp khác.

### 7.4. Kiểm tra phóng to và reflow

Kiểm tra ở các mức phóng to và cỡ chữ phù hợp với tiêu chuẩn hoặc yêu cầu dự án. Quan sát:

- Văn bản không bị cắt hoặc chồng lấp.
- Không mất nội dung hoặc chức năng.
- Không cần cuộn ngang hai chiều cho nội dung thông thường ở điều kiện tiêu chí quy định, trừ nội dung cần bố cục hai chiều.
- Menu và dialog vẫn sử dụng được.
- Nút và trường nhập không bị che.
- Người dùng có thể hoàn thành tác vụ mà không cần khôi phục kích thước mặc định.

Cần phân biệt phóng to toàn trang với tăng riêng cỡ chữ hoặc thay đổi khoảng cách văn bản; chúng có thể làm lộ những lỗi khác nhau.

### 7.5. Kiểm tra trên thiết bị di động

Ngoài trình đọc màn hình, xem xét:

- Kích thước và khoảng cách vùng chạm.
- Cử chỉ kéo, vuốt hoặc đa điểm có phương thức thay thế phù hợp.
- Hướng màn hình và bố cục.
- Bàn phím ảo có che trường hoặc nút hành động không.
- Focus và vị trí cuộn khi mở dialog hoặc validation error.
- Voice control hoặc switch access nếu nằm trong phạm vi hỗ trợ.
- Thay đổi kích thước chữ và cài đặt trợ năng của hệ điều hành.

## 8. Chuyển yêu cầu khả năng truy cập thành tiêu chí kiểm thử

Một yêu cầu có thể kiểm thử cần mô tả điều kiện, hành động và kết quả quan sát được. Tránh chỉ ghi “giao diện phải thân thiện với người khuyết tật”.

### 8.1. Ví dụ tiêu chí chấp nhận

| Mục tiêu | Tiêu chí có thể xác minh | Bằng chứng |
|---|---|---|
| Nhận biết tên điều khiển | Mỗi trường và nút có tên truy cập phù hợp với mục đích | Accessibility tree và trình đọc màn hình |
| Dùng bàn phím | Người dùng hoàn thành luồng đăng ký chỉ bằng bàn phím | Video hoặc checklist thao tác, trạng thái cuối |
| Focus rõ ràng | Focus luôn có dấu hiệu nhìn thấy và không bị che trong các bước | Ảnh chụp các trạng thái focus |
| Lỗi biểu mẫu | Khi nhập sai, lỗi được xác định bằng văn bản và liên kết với trường | DOM, accessibility tree và thông báo đọc |
| Nội dung video | Lời thoại và âm thanh quan trọng có phụ đề đồng bộ | Rà soát phụ đề và phát lại |
| Phóng to | Nội dung và chức năng vẫn sử dụng được ở mức phóng to mục tiêu | Ảnh chụp và kết quả hành trình |
| Tương phản | Văn bản và thành phần giao diện đáp ứng ngưỡng áp dụng | Kết quả đo và trạng thái thực tế |
| Trạng thái động | Kết quả cập nhật được công nghệ hỗ trợ nhận biết khi cần | Quan sát bằng trình đọc màn hình |

Các ngưỡng số và tiêu chí cụ thể cần đối chiếu với phiên bản WCAG hoặc tiêu chuẩn được dự án áp dụng. Bảng trên là mẫu chuyển yêu cầu thành bằng chứng, không thay thế danh mục tiêu chí chính thức.

### 8.2. Ví dụ Given–When–Then

~~~gherkin
Feature: Đăng ký tài khoản có thể truy cập

  Scenario: Người dùng hoàn thành đăng ký chỉ bằng bàn phím
    Given trang đăng ký đã tải
      And người dùng chưa nhập dữ liệu
    When người dùng di chuyển bằng Tab và Shift+Tab
      And điền các trường bắt buộc
      And gửi biểu mẫu bằng bàn phím
    Then mọi điều khiển cần thiết đều có thể nhận focus
      And vị trí focus được nhìn thấy
      And lỗi được mô tả bằng văn bản nếu dữ liệu không hợp lệ
      And khi dữ liệu hợp lệ, tài khoản được tạo
      And kết quả hoàn tất được thông báo
~~~

Kịch bản này có thể cần nhiều trường hợp riêng: một trường hợp xác nhận luồng thành công, một trường hợp lỗi biểu mẫu và một trường hợp dùng trình đọc màn hình để xác minh thông báo. Tách trường hợp giúp chẩn đoán lỗi và ghi bằng chứng chính xác hơn.

### 8.3. Ghi rõ điều kiện môi trường

Với mỗi trường hợp, ghi:

- Phiên bản ứng dụng và trang.
- Trình duyệt, hệ điều hành và thiết bị.
- Công nghệ hỗ trợ và phiên bản.
- Cài đặt phóng to, tương phản hoặc giảm chuyển động nếu liên quan.
- Ngôn ngữ và dữ liệu.
- Trạng thái ban đầu.
- Các bước thao tác.
- Hành vi mong đợi và thực tế.
- Bằng chứng và giới hạn kiểm tra.

## 9. Phân tích rủi ro và ưu tiên phạm vi

Không phải mọi trang đều có mức rủi ro như nhau. Ưu tiên theo khả năng người dùng bị chặn khỏi công việc quan trọng, mức độ hậu quả và số lượng người bị ảnh hưởng.

### 9.1. Các yếu tố đánh giá

- **Mức quan trọng của tác vụ:** có liên quan đến đăng nhập, thanh toán, quyền lợi, dữ liệu cá nhân hoặc dịch vụ cốt lõi không?
- **Mức độ chặn:** người dùng có thể tiếp tục bằng cách khác không?
- **Phạm vi ảnh hưởng:** lỗi xuất hiện trên một trang, nhiều thành phần dùng chung hay toàn bộ hành trình?
- **Tần suất:** tác vụ hoặc thành phần được sử dụng thường xuyên đến đâu?
- **Khả năng phát hiện:** người dùng có nhận ra và tự khắc phục được không?
- **Khả năng thay thế:** có phương thức tiếp cận tương đương, thực tế và không tạo thêm gánh nặng không?
- **Yêu cầu tuân thủ:** có tiêu chí hoặc nghĩa vụ bắt buộc áp dụng không?

### 9.2. Ma trận ưu tiên gợi ý

| Mức | Ví dụ | Cách xử lý |
|---|---|---|
| Rất cao | Không thể đăng nhập, thanh toán hoặc gửi yêu cầu bằng công nghệ hỗ trợ; nội dung quan trọng không thể nhận biết | Chặn chấp nhận hành trình cho đến khi có giải pháp hoặc quyết định hợp lệ |
| Cao | Thành phần dùng chung làm nhiều trang không thể điều hướng hoặc đọc đúng | Ưu tiên sửa ở component dùng chung và hồi quy các trang phụ thuộc |
| Trung bình | Một số nội dung hoặc thao tác có phương thức thay thế nhưng gây khó khăn đáng kể | Lập kế hoạch sửa, xác định phạm vi và người chịu trách nhiệm |
| Thấp | Vấn đề ít ảnh hưởng đến tác vụ, dễ nhận biết và có cách sử dụng phù hợp | Xử lý theo kế hoạch cải tiến và theo dõi |

Một phương thức thay thế chỉ được xem là phù hợp nếu người dùng thực sự có thể tiếp cận, hoàn thành công việc và không bị yêu cầu tiết lộ thông tin hoặc chịu thêm rào cản không hợp lý.

### 9.3. Xác định phạm vi tối thiểu và phạm vi mở rộng

Phạm vi tối thiểu nên bao gồm:

- Hành trình cốt lõi và các trạng thái chính.
- Thành phần dùng chung như điều hướng, biểu mẫu, dialog và thông báo.
- Các phương thức nhập liệu được cam kết.
- Một ma trận công nghệ hỗ trợ đại diện.
- Các tiêu chí bắt buộc theo tiêu chuẩn và chính sách.

Phạm vi mở rộng có thể bao gồm:

- Các hành trình ít phổ biến nhưng hậu quả cao.
- Nhiều trình duyệt, thiết bị và công nghệ hỗ trợ.
- Nội dung PDF, video, biểu đồ và widget bên thứ ba.
- Kiểm thử với người dùng có nhu cầu truy cập khác nhau.
- Các tình huống đặc biệt về thời gian, chuyển động, xác thực và dữ liệu động.

## 10. Báo cáo lỗi và đánh giá bằng chứng

### 10.1. Nội dung báo cáo lỗi

Một báo cáo lỗi khả năng truy cập nên có:

- Mã lỗi và mức độ ưu tiên.
- Trang, thành phần và hành trình bị ảnh hưởng.
- Tiêu chí hoặc yêu cầu liên quan.
- Người dùng hoặc phương thức tương tác bị ảnh hưởng.
- Môi trường, trình duyệt, hệ điều hành và công nghệ hỗ trợ.
- Tiền điều kiện và các bước tái hiện.
- Kết quả mong đợi và kết quả thực tế.
- Bằng chứng như ảnh, video, cây accessibility, log hoặc mô tả thao tác.
- Tác động đến khả năng hoàn thành công việc.
- Gợi ý hướng khắc phục nếu đã xác định được nguyên nhân.

Tránh báo cáo chỉ bằng ảnh chụp nếu vấn đề liên quan đến trình đọc màn hình hoặc thứ tự focus. Cần mô tả chính xác điều công nghệ hỗ trợ công bố hoặc thao tác nào không thể thực hiện.

### 10.2. Phân biệt lỗi công cụ và lỗi sản phẩm

Một công cụ tự động có thể báo cảnh báo không phù hợp với ngữ cảnh, hoặc bỏ sót vấn đề mà người dùng gặp phải. Khi triage:

1. Xác định rule và tiêu chí mà công cụ kiểm tra.
2. Kiểm tra thành phần trong ngữ cảnh thực tế.
3. Xác minh bằng phương pháp thủ công hoặc công nghệ hỗ trợ.
4. Ghi kết luận: lỗi xác nhận, false positive có căn cứ, chưa đủ bằng chứng hoặc vấn đề ngoài phạm vi.
5. Nếu rule tạo nhiễu, điều chỉnh cấu hình có kiểm soát và giữ lại lý do.

Không được đóng một lỗi thực tế chỉ vì công cụ quét không phát hiện.

### 10.3. Đánh giá kết quả theo hành trình

Một hành trình chỉ nên được xem là đã xác nhận khi người dùng có thể hoàn thành mục tiêu và các tiêu chí áp dụng đã được kiểm tra. Báo cáo nên nêu:

- Hành trình và nền tảng đã kiểm tra.
- Công nghệ hỗ trợ và phương thức nhập liệu.
- Tiêu chí đạt, không đạt, bị chặn hoặc chưa kiểm tra.
- Các lỗi chặn người dùng hoàn thành công việc.
- Các giới hạn của công cụ và ma trận kiểm thử.
- Rủi ro còn lại và người có thẩm quyền chấp nhận.

Không nên dùng một tỷ lệ quét tự động làm kết luận duy nhất về khả năng truy cập của sản phẩm.

## 11. Tích hợp kiểm tra khả năng truy cập vào vòng đời phát triển

### 11.1. Trong phân tích và thiết kế

- Ghi yêu cầu khả năng truy cập cùng yêu cầu chức năng.
- Chọn tiêu chuẩn và mức áp dụng.
- Xem xét người dùng, tác vụ và phương thức tương tác.
- Thiết kế semantics, focus, thông báo và nội dung ngay từ đầu.
- Đánh giá component dùng chung và thư viện giao diện.
- Xác định tiêu chí chấp nhận và nguồn bằng chứng.

### 11.2. Trong phát triển

- Dùng HTML ngữ nghĩa và điều khiển native khi phù hợp.
- Duy trì nhãn, trạng thái và quan hệ của thành phần.
- Kiểm tra focus khi cập nhật nội dung động.
- Tránh chỉ truyền thông tin bằng màu hoặc hình ảnh.
- Chạy formatter, lint và accessibility checks phù hợp.
- Review nội dung thay thế, phụ đề và thông báo.

### 11.3. Trong CI và kiểm thử

- Chạy công cụ tự động trên trang hoặc component thay đổi.
- Dùng kiểm thử component để xác nhận semantics và trạng thái.
- Kiểm tra thủ công các hành trình ưu tiên bằng bàn phím.
- Dùng trình đọc màn hình trên ma trận được chọn.
- Kiểm tra phóng to, reflow và các trạng thái lỗi.
- Theo dõi lỗi mới và lỗi hồi quy ở component dùng chung.

### 11.4. Trước phát hành và sau phát hành

- Rà soát hành trình có rủi ro cao trên bản dựng ứng viên.
- Xác nhận các lỗi chặn đã được giải quyết hoặc có quyết định xử lý hợp lệ.
- Kiểm tra nội dung và thành phần bên thứ ba.
- Duy trì kênh nhận phản hồi và báo lỗi truy cập.
- Theo dõi thay đổi nền tảng, trình duyệt và công nghệ hỗ trợ.
- Đánh giá lại khi thêm hành trình, component hoặc nội dung mới.

## 12. Những sai lầm thường gặp

1. **Chỉ chạy công cụ quét tự động:** bỏ sót vấn đề về ý nghĩa nội dung, focus, bàn phím và trải nghiệm trình đọc màn hình.
2. **Chỉ kiểm tra trang chủ:** không kiểm tra các hành trình thiết yếu như đăng nhập, thanh toán hoặc gửi biểu mẫu.
3. **Chỉ tập trung vào thị giác:** bỏ qua vận động, thính giác, nhận thức và công nghệ hỗ trợ.
4. **Coi ARIA là giải pháp mặc định:** thêm thuộc tính không đúng ngữ nghĩa hoặc làm sai hành vi điều khiển.
5. **Chỉ kiểm tra trạng thái ban đầu:** bỏ qua dialog, lỗi, tải động, focus sau cập nhật và phiên hết hạn.
6. **Dùng một tổ hợp công nghệ hỗ trợ cho mọi kết luận:** không xem xét ma trận nền tảng mà sản phẩm cam kết hỗ trợ.
7. **Đồng nhất tuân thủ tiêu chí với trải nghiệm tốt:** bỏ qua khả năng hoàn thành công việc thực tế.
8. **Không kiểm tra nội dung ngoài HTML:** bỏ sót PDF, video, email, biểu đồ hoặc widget bên thứ ba.
9. **Không ghi phiên bản môi trường:** khiến lỗi khó tái hiện và kết quả không thể so sánh.
10. **Chấp nhận phương thức thay thế không tương đương:** người dùng phải nhờ người khác hoặc thực hiện quy trình phức tạp hơn để hoàn thành cùng tác vụ.
11. **Không ưu tiên lỗi chặn:** xử lý lỗi thẩm mỹ trước lỗi khiến người dùng không thể đăng nhập hoặc thanh toán.
12. **Không duy trì kiểm tra sau phát hành:** thành phần hoặc nội dung mới đưa rào cản trở lại.

## 13. Checklist xác định yêu cầu và phạm vi kiểm tra khả năng truy cập

- [ ] Đã xác định người dùng, nhu cầu truy cập và các tác vụ quan trọng.
- [ ] Đã chọn phiên bản tiêu chuẩn, mức phù hợp và căn cứ áp dụng.
- [ ] Đã xác định nền tảng, trình duyệt, thiết bị và công nghệ hỗ trợ trong phạm vi.
- [ ] Đã liệt kê hành trình, trạng thái, nhánh lỗi và nội dung liên quan.
- [ ] Đã xem xét bốn nguyên tắc có thể nhận biết, thao tác, hiểu và tương thích.
- [ ] Đã xác định yêu cầu về bàn phím, focus, semantics, nhãn và thông báo.
- [ ] Đã xem xét tương phản, phóng to, reflow, phụ đề và văn bản thay thế.
- [ ] Đã chọn thành phần và hành trình cần kiểm tra tự động và thủ công.
- [ ] Đã xác định các kiểm tra cần trình đọc màn hình hoặc công nghệ hỗ trợ thật.
- [ ] Đã viết tiêu chí chấp nhận có thể quan sát và nguồn bằng chứng.
- [ ] Đã ưu tiên lỗi theo mức độ chặn, hậu quả và phạm vi ảnh hưởng.
- [ ] Đã ghi rõ nội dung hoặc thành phần bên thứ ba và giới hạn kiểm tra.
- [ ] Đã xác định người phụ trách, trạng thái lỗi và cách chấp nhận rủi ro còn lại.
- [ ] Đã đưa kiểm tra khả năng truy cập vào review, CI, hồi quy và phát hành.
- [ ] Đã có cách tiếp nhận phản hồi và xem xét lại khi sản phẩm thay đổi.

Xác định đúng yêu cầu và phạm vi kiểm tra khả năng truy cập giúp nhóm chứng minh người dùng có thể hoàn thành công việc bằng những phương thức tương tác được hỗ trợ. Khi kết hợp tiêu chuẩn phù hợp, kiểm tra tự động, kiểm tra thủ công, công nghệ hỗ trợ và đánh giá hành trình, kết luận về khả năng truy cập sẽ có căn cứ rõ ràng hơn và phản ánh tốt hơn trải nghiệm thực tế.

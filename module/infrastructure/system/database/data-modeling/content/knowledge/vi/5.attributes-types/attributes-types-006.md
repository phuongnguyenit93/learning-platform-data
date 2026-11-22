# Văn bản, mã kỹ thuật, độ dài và quy tắc Unicode

Dữ liệu văn bản xuất hiện ở hầu hết mô hình dữ liệu: tên người, tên sản phẩm, địa chỉ, mô tả, ghi chú, mã nghiệp vụ và định danh kỹ thuật. Tuy cùng được lưu dưới dạng chuỗi, các giá trị này có mục đích khác nhau. Tên sản phẩm cần hỗ trợ ngôn ngữ tự nhiên; mã SKU cần tuân theo một quy tắc ký tự ổn định; khóa kỹ thuật cần nhận diện bản ghi mà không phụ thuộc vào cách viết tên hiển thị.

Nếu dùng chung một quy tắc cho mọi loại chuỗi, hệ thống có thể gặp lỗi tìm kiếm, so sánh và tính duy nhất. Văn bản tiếng Việt có dấu có thể bị biến dạng khi đi qua hệ thống không hỗ trợ Unicode đầy đủ. Một chuỗi nhìn giống nhau có thể được mã hóa bằng các chuỗi mã Unicode khác nhau. Giới hạn 50 ký tự cũng có thể bị hiểu sai nếu ứng dụng đếm ký tự hiển thị còn cơ sở dữ liệu giới hạn byte hoặc đơn vị mã.

Bài học này giúp xác định loại dữ liệu văn bản, phân biệt mã kỹ thuật với nội dung hiển thị, chọn giới hạn độ dài phù hợp và thiết kế quy tắc Unicode nhất quán từ ứng dụng đến cơ sở dữ liệu.

**Sau bài học, bạn có thể:**

- Phân biệt văn bản tự do, nhãn hiển thị, mã nghiệp vụ và định danh kỹ thuật.
- Giải thích sự khác nhau giữa byte, code unit, code point và grapheme cluster.
- Chọn quy tắc mã hóa, chuẩn hóa, so sánh và kiểm tra Unicode phù hợp.
- Xác định giới hạn độ dài theo yêu cầu nghiệp vụ và khả năng lưu trữ.
- Thiết kế quy tắc ký tự và tính duy nhất cho mã kỹ thuật.
- Tránh lỗi mojibake, cắt chuỗi sai, ký tự nhìn giống nhau và so sánh không nhất quán.

## 1. Phân loại dữ liệu văn bản trước khi chọn kiểu

Không phải mọi chuỗi đều có cùng ý nghĩa. Trước khi chọn kiểu dữ liệu và giới hạn, hãy xác định chuỗi được dùng để làm gì, ai tạo ra nó và hệ thống cần so sánh hoặc tìm kiếm như thế nào.

| Loại giá trị | Ví dụ | Đặc điểm thiết kế |
|---|---|---|
| Văn bản tự do | Mô tả sản phẩm, ghi chú đơn hàng | Hỗ trợ Unicode, độ dài có thể lớn, không nên áp dụng bảng ký tự quá hẹp |
| Tên hoặc nhãn hiển thị | Tên khách hàng, tên sản phẩm | Có thể có dấu, nhiều ngôn ngữ, cần quy tắc hiển thị và tìm kiếm |
| Mã nghiệp vụ | SKU, mã đơn, mã kho | Có định dạng và phạm vi duy nhất được xác định |
| Định danh kỹ thuật | UUID, mã nội bộ | Dùng để tham chiếu ổn định; không phụ thuộc tên hiển thị |
| Giá trị phân loại | Loại sản phẩm, trạng thái | Nên dùng miền giá trị hoặc danh mục được quản lý |
| Nội dung có cấu trúc | JSON, XML, nội dung đánh dấu | Cần quy tắc cú pháp, phiên bản và kiểm tra cấu trúc riêng |

Ví dụ, tên sản phẩm “Cà phê rang xay Đà Lạt” là văn bản hiển thị. SKU “CF-DL-250G” là mã kỹ thuật có quy tắc. Hai giá trị đều là chuỗi nhưng không nên dùng cùng chính sách kiểm tra.

Cần hỏi với mỗi thuộc tính:

- Người dùng nhập tự do hay hệ thống sinh ra?
- Giá trị có thể chứa nhiều ngôn ngữ hoặc ký tự ngoài ASCII không?
- Có cần tìm kiếm không dấu, không phân biệt hoa thường hoặc theo ngôn ngữ không?
- Có cần duy nhất không, và duy nhất trong phạm vi nào?
- Giá trị có được thay đổi sau khi tạo không?
- Có cần giữ nguyên cách viết ban đầu để hiển thị, kiểm toán hoặc đối chiếu không?

## 2. Unicode: một ký tự nhìn thấy có thể gồm nhiều đơn vị mã

Unicode là tiêu chuẩn gán mã cho các ký tự và ký hiệu của nhiều hệ chữ viết. Unicode không đồng nghĩa với UTF-8. Unicode xác định tập ký tự và code point; UTF-8, UTF-16 và UTF-32 là các cách mã hóa code point thành đơn vị lưu trữ.

Để thiết kế độ dài chính xác, cần phân biệt bốn khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| Byte | Đơn vị dữ liệu 8 bit | Đo dung lượng khi mã hóa UTF-8 |
| Code unit | Đơn vị cơ sở của một dạng mã hóa | UTF-16 dùng đơn vị 16 bit; một code point có thể cần hai code unit |
| Code point | Một giá trị mã Unicode | Ký hiệu Unicode như chữ, dấu hoặc emoji |
| Grapheme cluster | Một đơn vị gần với ký tự mà người dùng cảm nhận khi đọc | Một chữ có dấu tổ hợp hoặc emoji ghép có thể gồm nhiều code point |

### 2.1. Ví dụ với tiếng Việt

Chữ “ế” có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng một chữ cái kết hợp với các dấu phụ. Hai chuỗi có thể nhìn giống nhau nhưng có chuỗi code point khác nhau.

Vì vậy, so sánh hai chuỗi theo byte hoặc code point trực tiếp có thể cho kết quả khác nhau dù người dùng nhìn thấy cùng một chữ. Đây là lý do cần xác định chính sách chuẩn hóa Unicode trước khi so sánh hoặc áp dụng ràng buộc duy nhất.

### 2.2. Ví dụ với emoji và ký tự ghép

Một emoji hiển thị có thể được tạo từ nhiều code point, ví dụ một biểu tượng gia đình hoặc biểu tượng có màu da. Một ký tự có dấu trong một số hệ chữ viết cũng có thể gồm ký tự cơ sở và dấu kết hợp.

Do đó:

- Đếm byte không tương đương đếm ký tự.
- Đếm code point không luôn tương đương đếm ký tự người dùng nhìn thấy.
- Cắt chuỗi tại một byte tùy ý có thể làm hỏng chuỗi UTF-8.
- Cắt tại code point vẫn có thể tách một grapheme cluster thành các phần hiển thị không mong muốn.

Nếu giới hạn được mô tả cho người dùng là “tối đa 100 ký tự”, cần xác định ứng dụng đếm theo grapheme cluster hay theo quy tắc khác. Nếu giới hạn là dung lượng lưu trữ, phải tính byte theo encoding thực tế.

## 3. Mã hóa ký tự và lỗi hiển thị

Một chuỗi Unicode có thể đi qua nhiều thành phần:

1. Giao diện nhập liệu;
2. Ứng dụng và thư viện xử lý chuỗi;
3. Driver kết nối cơ sở dữ liệu;
4. Cấu hình encoding của kết nối;
5. Kiểu và character set của cột;
6. Công cụ xuất dữ liệu, báo cáo hoặc tích hợp.

Tất cả các thành phần cần hiểu cùng một cách mã hóa. Chỉ đặt cột hỗ trợ Unicode là chưa đủ nếu ứng dụng hoặc kết nối chuyển đổi sai dữ liệu.

### 3.1. UTF-8 và tính tương thích

UTF-8 là cách mã hóa Unicode phổ biến trên web và nhiều hệ thống hiện đại. Nó dùng từ một đến bốn byte cho mỗi code point. Ký tự ASCII có cách biểu diễn tương thích với ASCII, còn các ký tự khác có thể cần nhiều byte.

Khi thiết kế, cần kiểm tra:

- Cơ sở dữ liệu có character set hỗ trợ đầy đủ Unicode không?
- Driver có gửi và nhận chuỗi theo encoding đúng không?
- Kết nối có cấu hình encoding nhất quán không?
- Công cụ import/export có giữ nguyên dữ liệu không?
- Các hệ thống tích hợp có hỗ trợ tiếng Việt và các ký tự ngoài ASCII không?

Tên kiểu cột khác nhau giữa các hệ quản trị. Có hệ quản trị dùng một kiểu chuỗi Unicode riêng, có hệ quản trị dùng character set ở cấp cơ sở dữ liệu hoặc cột. Hãy xác minh hành vi của nền tảng cụ thể trước khi triển khai.

### 3.2. Mojibake là gì?

Mojibake là hiện tượng văn bản bị hiển thị thành ký tự sai do dữ liệu được giải mã bằng encoding không khớp với encoding ban đầu.

Ví dụ, một chuỗi tiếng Việt có thể hiển thị thành những ký tự lạ như “CÃ  phÃª” thay vì “Cà phê”. Khi đó, dữ liệu có thể đã bị chuyển đổi sai ở một bước trong luồng truyền hoặc lưu trữ.

Không nên sửa bằng cách thay thế thủ công các ký tự nhìn thấy trong giao diện. Cần xác định nơi encoding bị lệch, kiểm tra byte hoặc dữ liệu gốc, sau đó sửa đúng ở nguồn hoặc trong quy trình chuyển đổi. Nếu đã lưu sai, cần kế hoạch phục hồi có kiểm chứng và sao lưu trước khi cập nhật hàng loạt.

## 4. Chuẩn hóa Unicode trước khi so sánh

Unicode cung cấp các dạng chuẩn hóa để biểu diễn những chuỗi tương đương theo một dạng nhất quán.

Hai dạng thường được nhắc tới:

- **NFC:** chuẩn hóa theo dạng tổ hợp chuẩn, thường ghép các chuỗi có thể ghép thành dạng chuẩn dựng sẵn.
- **NFD:** chuẩn hóa theo dạng phân rã chuẩn, tách một số ký tự thành ký tự cơ sở và dấu kết hợp.

Ngoài ra còn có NFKC và NFKD, là các dạng chuẩn hóa tương thích. Chúng có thể gộp những khác biệt về hình thức mà Unicode xem là tương thích. Vì vậy, chúng có thể hữu ích cho một số quy tắc tìm kiếm hoặc xử lý định danh, nhưng không nên áp dụng máy móc lên văn bản gốc cần bảo toàn cách viết.

### 4.1. Chọn dạng chuẩn hóa

Đối với nhiều hệ thống nghiệp vụ, có thể chọn NFC làm dạng chuẩn lưu hoặc dạng chuẩn so sánh cho các trường văn bản thông thường. Tuy nhiên, đây là quyết định cần thống nhất với ứng dụng, hệ thống tích hợp và yêu cầu bảo toàn dữ liệu.

Một chiến lược phổ biến:

- Giữ nguyên văn bản người dùng gửi nếu cần bảo toàn nội dung gốc.
- Tạo dạng chuẩn hóa để so sánh hoặc tìm kiếm nếu có nhu cầu.
- Áp dụng cùng quy tắc ở mọi nơi ghi dữ liệu.
- Không chuẩn hóa tùy tiện những nội dung có ý nghĩa chính xác từng byte, chữ ký số hoặc dữ liệu được dùng làm payload nguyên gốc.

Không nên xem NFC là phép thay thế cho kiểm tra định dạng, xử lý khoảng trắng hoặc so sánh không phân biệt hoa thường. Đây là những chính sách khác nhau.

### 4.2. Chuẩn hóa không đồng nghĩa với bỏ dấu

Chuẩn hóa Unicode giữ ý nghĩa ký tự theo quy tắc Unicode; bỏ dấu là một phép biến đổi phục vụ tìm kiếm hoặc đối sánh gần đúng. Ví dụ, “Hòa” và “Hoa” có thể được coi là gần nhau trong một chức năng tìm kiếm, nhưng không nhất thiết là cùng một tên hoặc cùng một mã.

Nếu cần tìm kiếm không dấu, hãy tạo cơ chế tìm kiếm riêng. Không ghi đè tên gốc bằng chuỗi đã bỏ dấu vì sẽ làm mất thông tin hiển thị.

### 4.3. Hoa thường và quy tắc so sánh

Chuyển chữ thường (lowercase), case folding và so sánh không phân biệt hoa thường không phải lúc nào cũng giống nhau. Quy tắc phụ thuộc ngôn ngữ và collation. Một số chữ cái có cách chuyển hoa/thường đặc biệt theo locale.

Cần phân biệt:

- **Giá trị gốc:** chuỗi người dùng nhập hoặc hệ thống nhận.
- **Dạng chuẩn hóa:** chuỗi đã được chuẩn hóa theo một dạng Unicode.
- **Dạng so sánh:** chuỗi hoặc quy tắc dùng để tìm kiếm và xác định tương đương.
- **Dạng hiển thị:** chuỗi được trả cho người dùng.

Không nên tự viết một hàm lowercase đơn giản rồi giả định nó giải quyết mọi trường hợp Unicode.

## 5. Collation và phép so sánh chuỗi

Collation quy định cách so sánh và sắp xếp chuỗi theo một tập quy tắc. Nó có thể quyết định việc so sánh có phân biệt hoa thường, dấu, ngôn ngữ hoặc một số khác biệt ký tự hay không.

Ví dụ, hai chuỗi có thể được coi là tương đương trong một collation không phân biệt hoa thường, nhưng khác nhau trong collation phân biệt hoa thường. Một collation không phân biệt dấu có thể coi một số chữ có dấu và không dấu là tương đương khi tìm kiếm.

Không có một collation đúng cho mọi trường. Tên người, tên địa phương, mã sản phẩm và khóa kỹ thuật có nhu cầu khác nhau.

| Loại thuộc tính | Quy tắc so sánh thường cần xem xét |
|---|---|
| Tên hiển thị | Có thể cần tìm kiếm không phân biệt hoa thường; việc bỏ dấu tùy chức năng |
| Mô tả | Tìm kiếm ngôn ngữ tự nhiên, có thể dùng full-text search |
| Mã kỹ thuật | So sánh chính xác theo bảng ký tự và quy tắc chữ hoa/thường đã công bố |
| Định danh opaque | So sánh theo biểu diễn chuẩn của định danh |
| Trạng thái hoặc loại | So sánh theo tập giá trị chuẩn, tránh biến thể cách viết tự do |

Một cột có collation không phù hợp có thể khiến ràng buộc UNIQUE từ chối hai mã khác nhau hoặc chấp nhận hai giá trị mà nghiệp vụ coi là trùng. Cần kiểm tra hành vi collation cùng với ràng buộc duy nhất, chỉ mục và truy vấn thực tế.

## 6. Thiết kế mã kỹ thuật riêng với văn bản hiển thị

Mã kỹ thuật là giá trị dùng để định danh hoặc trao đổi giữa hệ thống. Nó cần ổn định, dễ kiểm tra và có quy tắc rõ ràng. Văn bản hiển thị phục vụ con người, có thể thay đổi ngôn ngữ hoặc cách viết.

Ví dụ:

| Thuộc tính | Giá trị minh họa | Mục đích |
|---|---|---|
| product_id | Một UUID hoặc mã nội bộ | Định danh kỹ thuật ổn định |
| sku | CF-DL-250G | Mã hàng theo quy tắc doanh nghiệp |
| product_name | Cà phê rang xay Đà Lạt 250 g | Tên hiển thị |
| product_description | Mô tả nguồn gốc, cách rang và hướng dẫn pha | Văn bản tự do |

Không nên dùng tên hiển thị làm khóa chính. Tên có thể đổi, trùng, dịch sang ngôn ngữ khác hoặc chứa dấu và khoảng trắng. Mã kỹ thuật cần có vòng đời và quy tắc riêng.

### 6.1. Quy tắc định dạng mã

Một mã kỹ thuật nên xác định rõ:

- Bộ ký tự cho phép;
- Độ dài tối thiểu và tối đa;
- Quy tắc hoa/thường;
- Ký tự phân cách được phép;
- Có cho phép khoảng trắng không;
- Có cho phép dấu tiếng Việt hoặc ký tự Unicode không;
- Phạm vi duy nhất;
- Có phân biệt số 0 đầu hay không;
- Mã có được đổi sau khi tạo không;
- Ai hoặc hệ thống nào có quyền cấp mã.

Với mã được trao đổi rộng rãi giữa nhiều hệ thống, một tập ký tự ASCII có giới hạn có thể giảm rủi ro khác biệt collation và công cụ tích hợp. Đây là lựa chọn thiết kế, không phải quy tắc bắt buộc cho mọi mã. Nếu nghiệp vụ yêu cầu mã có ký tự bản địa, cần xác định rõ encoding, normalization và so sánh.

Ví dụ định dạng SKU minh họa:

~~~text
CF-DL-250G
CF-HN-500G
TEA-GT-100G
~~~

Quy tắc có thể là chữ Latin in hoa, chữ số và dấu gạch ngang, độ dài từ 3 đến 24 ký tự, không có khoảng trắng. Hệ thống cần xác định SKU duy nhất toàn doanh nghiệp hay chỉ trong từng tổ chức hoặc nhà cung cấp.

### 6.2. Số 0 ở đầu và kiểu dữ liệu

Mã có thể chứa chữ số nhưng vẫn là chuỗi. Ví dụ mã vùng “0012” không phải số 12. Nếu lưu dưới kiểu số, số 0 đầu có thể bị mất và các phép toán số học không có ý nghĩa.

Hãy dùng kiểu chuỗi cho mã định danh có số 0 đầu, ký tự phân cách hoặc không dùng trong phép tính. Chỉ dùng kiểu số nếu giá trị thực sự là đại lượng số học.

### 6.3. Không tự động chuyển mã thành không dấu

Nếu mã kỹ thuật được quy định chỉ gồm ASCII, hãy kiểm tra và từ chối ký tự ngoài tập cho phép. Không tự động chuyển “ĐÀ NẴNG” thành “DA NANG” hoặc xóa ký tự không hợp lệ mà không có quy tắc rõ ràng. Hai mã khác nhau có thể bị biến thành cùng một chuỗi sau khi chuyển đổi.

Nếu cần tạo mã từ tên hiển thị, hãy coi đó là quy trình sinh mã có kiểm tra xung đột, có quy tắc xử lý trùng và có khả năng giữ mã ổn định sau khi tên thay đổi.

## 7. Độ dài: ký tự, code point hay byte?

Giới hạn độ dài phải phù hợp với cách người dùng hiểu và cách hệ thống lưu trữ. Cụm từ “tối đa 100 ký tự” cần được làm rõ trước khi chuyển thành giới hạn cột.

Có ít nhất ba cách đo thường gặp:

- **Số grapheme cluster:** gần với số ký tự người dùng nhìn thấy.
- **Số code point hoặc code unit:** số đơn vị mã theo cách triển khai.
- **Số byte:** dung lượng sau khi mã hóa.

Ví dụ một chuỗi tiếng Việt hoặc emoji có thể có số byte lớn hơn số ký tự hiển thị. Vì vậy, giới hạn 100 byte không tương đương 100 ký tự.

### 7.1. Độ dài nghiệp vụ và giới hạn lưu trữ

Nên ghi nhận hai giới hạn riêng:

1. **Giới hạn nghiệp vụ:** người dùng được phép nhập tối đa bao nhiêu ký tự hiển thị, hoặc mã có bao nhiêu ký tự theo định dạng.
2. **Giới hạn lưu trữ:** cột và hệ thống có thể lưu tối đa bao nhiêu đơn vị theo encoding và kiểu dữ liệu.

Ví dụ, tên sản phẩm có thể giới hạn 200 grapheme cluster theo yêu cầu giao diện, trong khi cột cần đủ dung lượng byte để lưu chuỗi UTF-8 tương ứng. Cần kiểm tra giới hạn trên toàn bộ đường đi, gồm API, driver, database, message queue và hệ thống tích hợp.

### 7.2. Chọn kiểu chuỗi

Các hệ quản trị có kiểu chuỗi và quy tắc độ dài khác nhau. Những kiểu thường gặp:

| Kiểu khái niệm | Đặc điểm | Khi cân nhắc |
|---|---|---|
| CHAR(n) | Độ dài cố định hoặc có quy tắc đệm khoảng trắng tùy hệ quản trị | Mã có độ dài cố định thật sự |
| VARCHAR(n) | Chuỗi có giới hạn độ dài | Tên, mã và trường văn bản ngắn đến trung bình |
| TEXT hoặc kiểu tương đương | Văn bản dài, giới hạn hoặc cách lưu phụ thuộc nền tảng | Mô tả, ghi chú và nội dung dài |

Không chọn CHAR chỉ vì muốn giới hạn độ dài. Cần hiểu cách hệ quản trị xử lý padding, trailing spaces, so sánh và index. Với mã có độ dài biến đổi, VARCHAR thường dễ diễn đạt hơn.

TEXT không có nghĩa là không giới hạn tuyệt đối. Hệ quản trị, giao thức, API và ứng dụng vẫn có giới hạn dung lượng, bộ nhớ, thời gian xử lý và kích thước payload.

### 7.3. Tránh cắt chuỗi sai

Khi cắt chuỗi theo byte, không được cắt giữa một chuỗi byte UTF-8 của code point. Khi cắt theo code point, cần xem có làm tách grapheme cluster không. Nếu người dùng nhập giới hạn theo số ký tự hiển thị, giao diện nên đếm theo quy tắc phù hợp và báo lỗi trước khi lưu.

Không nên dựa vào cơ sở dữ liệu tự cắt chuỗi vượt giới hạn. Một số hệ quản trị báo lỗi, một số chế độ hoặc thao tác có thể cắt và cảnh báo. Ứng dụng cần xác thực rõ ràng và không âm thầm làm mất dữ liệu.

## 8. Khoảng trắng, ký tự điều khiển và ký tự khó nhìn thấy

Chuỗi văn bản có thể chứa nhiều loại khoảng trắng và ký tự điều khiển. Hai chuỗi nhìn giống nhau có thể khác vì:

- Khoảng trắng ASCII và khoảng trắng không ngắt dòng;
- Tab hoặc xuống dòng;
- Khoảng trắng ở đầu hoặc cuối;
- Ký tự zero-width;
- Ký tự điều khiển định hướng văn bản;
- Ký tự thay thế hoặc ký tự không hợp lệ sau chuyển mã.

Không nên loại bỏ mọi ký tự khó nhìn thấy một cách tùy tiện. Trong văn bản tự do, xuống dòng có thể mang ý nghĩa. Trong mã kỹ thuật, tab, newline và khoảng trắng thường nên bị từ chối.

### 8.1. Chính sách trim

Cần xác định có loại bỏ khoảng trắng ở đầu và cuối hay không. Với tên hiển thị, có thể chuẩn hóa khoảng trắng đầu/cuối để tránh nhập nhầm. Nhưng với nội dung văn bản gốc, có thể cần bảo toàn nguyên văn.

Đối với mã kỹ thuật, chính sách thường nên nghiêm ngặt: từ chối khoảng trắng hoặc loại bỏ theo một quy tắc duy nhất trước khi kiểm tra định dạng. Không để ứng dụng và database áp dụng hai cách trim khác nhau.

### 8.2. Ký tự điều khiển và bidi

Một số ký tự điều khiển Unicode ảnh hưởng thứ tự hiển thị văn bản từ trái sang phải hoặc phải sang trái. Chúng có thể cần thiết trong nội dung đa ngôn ngữ, nhưng cũng có thể làm mã hoặc tên hiển thị gây nhầm lẫn khi kiểm tra bằng mắt.

Với mã kỹ thuật, nên từ chối ký tự điều khiển và ký tự định dạng không cần thiết. Với văn bản tự do, cần xử lý theo chính sách nội dung, hiển thị an toàn và ngữ cảnh ngôn ngữ. Không nên loại bỏ chúng bằng một bộ lọc chung cho mọi trường.

### 8.3. Ký tự đồng hình

Ký tự đồng hình (confusable) là các ký tự từ bảng chữ cái khác nhau nhưng có hình dáng gần giống nhau. Ví dụ một chữ Latin và một chữ Cyrillic có thể nhìn gần như giống nhau. Điều này có thể gây nhầm lẫn cho mã đăng nhập, mã sản phẩm, tên miền hoặc mã tham chiếu.

Đối với định danh và mã quan trọng:

- Hạn chế bảng ký tự theo nhu cầu nghiệp vụ;
- Áp dụng chuẩn hóa và quy tắc so sánh thống nhất;
- Cảnh báo hoặc từ chối ký tự đồng hình khi phù hợp;
- Không dựa vào mắt người để kiểm tra tính duy nhất;
- Dùng ID kỹ thuật ổn định để liên kết bản ghi.

Với tên người và nội dung tự do, không nên áp đặt giới hạn ASCII chỉ để tránh ký tự đồng hình. Cần tách chính sách của trường hiển thị khỏi chính sách của mã định danh.

## 9. Thiết kế quy tắc logic cho từng trường

Một đặc tả thuộc tính văn bản nên ghi rõ hơn tên và kiểu chuỗi. Có thể dùng mẫu sau:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Ý nghĩa | Chuỗi đại diện cho nội dung gì? |
| Nguồn | Người dùng nhập, hệ thống sinh hay nhận từ hệ thống ngoài? |
| Encoding | Hệ thống dùng Unicode và encoding nào? |
| Độ dài | Đo theo grapheme, code point, code unit hay byte? |
| Miền ký tự | Có giới hạn bảng ký tự không? |
| Normalization | Có chuẩn hóa NFC hoặc dạng khác không? |
| So sánh | Có phân biệt hoa thường, dấu hoặc locale không? |
| Khoảng trắng | Có trim, cấm hoặc giữ nguyên không? |
| Tính duy nhất | Duy nhất toàn cục hay theo phạm vi nào? |
| Bảo toàn | Có cần giữ nguyên chuỗi gốc không? |

Ví dụ đặc tả cho hai trường:

| Thuộc tính | product_name | sku |
|---|---|---|
| Mục đích | Tên hiển thị cho người dùng | Mã hàng để tham chiếu và trao đổi |
| Ký tự | Unicode | Chữ Latin in hoa, số và dấu gạch ngang theo quy tắc |
| Độ dài | Tối đa 200 grapheme cluster theo chính sách giao diện | 3–24 ký tự theo định dạng mã |
| Chuẩn hóa | NFC cho dạng so sánh; giữ giá trị gốc nếu cần | Chuẩn hóa theo định dạng mã đã công bố |
| Hoa/thường | Có thể tìm kiếm không phân biệt hoa thường | Quy định mã không phân biệt hoa thường hoặc chỉ chấp nhận chữ hoa |
| Khoảng trắng | Trim đầu/cuối theo chính sách; cho phép khoảng trắng bên trong | Không cho phép |
| Duy nhất | Thường không duy nhất | Duy nhất trong phạm vi doanh nghiệp hoặc tenant đã xác định |

Các giá trị trong bảng là ví dụ. Dự án phải xác nhận giới hạn, phạm vi và quy tắc thực tế trước khi áp dụng.

## 10. Ví dụ thiết kế: danh mục sản phẩm

Giả sử hệ thống cần lưu mã SKU, tên sản phẩm, tên tìm kiếm và mô tả.

### 10.1. Xác định ý nghĩa

- SKU là mã tham chiếu nghiệp vụ, không phải tên hiển thị.
- Tên sản phẩm có thể chứa dấu tiếng Việt và nhiều ngôn ngữ.
- Mô tả có thể dài và chứa dấu câu, xuống dòng.
- Tên tìm kiếm có thể là dữ liệu dẫn xuất để hỗ trợ tìm kiếm không dấu hoặc không phân biệt hoa thường.

Không nên lưu tên tìm kiếm đã bỏ dấu vào cột tên hiển thị. Cũng không nên dùng tên sản phẩm làm khóa duy nhất.

### 10.2. Mô hình logic minh họa

~~~sql
PRODUCT
-------
product_id          : Identifier, primary key
sku                 : Code, required, unique in agreed scope
product_name        : Unicode text, required, max 200 grapheme clusters
product_description : Unicode long text, optional
search_name         : Derived/search text, optional
created_at          : Timestamp
~~~

Đây là ký pháp logic minh họa, không phải DDL của một hệ quản trị cụ thể. Cần xác định cách tạo search_name, collation, index và giới hạn vật lý theo nền tảng triển khai.

### 10.3. Quy trình nhập SKU

1. Nhận giá trị người dùng nhập.
2. Kiểm tra ký tự được phép và độ dài.
3. Áp dụng quy tắc hoa/thường và khoảng trắng đã công bố.
4. Kiểm tra tính duy nhất trong đúng phạm vi.
5. Lưu mã chuẩn.
6. Trả lỗi rõ ràng nếu mã sai định dạng hoặc đã tồn tại.

Không tự động bỏ ký tự không hợp lệ rồi lưu vì người dùng có thể không nhận ra mã đã bị thay đổi. Nếu có thao tác tự động chuẩn hóa, cần hiển thị kết quả và bảo đảm không gây xung đột.

### 10.4. Quy trình nhập tên sản phẩm

1. Nhận văn bản Unicode.
2. Kiểm tra encoding và chuỗi hợp lệ.
3. Kiểm tra độ dài theo quy tắc giao diện và giới hạn lưu trữ.
4. Xử lý khoảng trắng đầu/cuối theo chính sách.
5. Lưu nội dung hiển thị.
6. Tạo dạng tìm kiếm riêng nếu cần.
7. Khi đọc, hiển thị chuỗi đúng encoding và không làm mất dấu.

## 11. Tính duy nhất khi có Unicode

Ràng buộc UNIQUE không chỉ là quyết định có hay không. Nó phụ thuộc vào cách hệ thống xem hai chuỗi có tương đương hay không.

Ví dụ, nghiệp vụ có thể coi hai SKU chỉ khác chữ hoa/thường là cùng một mã. Khi đó, nếu database so sánh phân biệt hoa thường, ràng buộc UNIQUE thông thường có thể cho phép cả hai. Ngược lại, một collation không phân biệt dấu có thể coi hai tên khác dấu là tương đương, dù doanh nghiệp muốn giữ cả hai.

Cần xác định quy tắc chuẩn hóa trước khi tạo unique index hoặc kiểm tra trùng.

Một cách thiết kế là lưu:

- Giá trị gốc để hiển thị;
- Giá trị chuẩn hóa dùng để so sánh;
- Ràng buộc duy nhất trên giá trị chuẩn hóa trong phạm vi phù hợp.

Ví dụ khái niệm:

~~~text
sku_original = "cf-dl-250g"
sku_canonical = "CF-DL-250G"
UNIQUE(tenant_id, sku_canonical)
~~~

Đây chỉ là ví dụ. Nếu mã có phân biệt hoa thường, không được chuyển tất cả thành chữ hoa. Nếu mã được cấp bởi nhà cung cấp và có quy tắc riêng, phải giữ quy tắc của nguồn đó.

Đối với tên hiển thị, thường không nên áp dụng unique toàn cục. Hai người hoặc hai sản phẩm có thể cùng tên. Nếu cần phát hiện trùng gần đúng, đó là chức năng tìm kiếm hoặc kiểm soát nghiệp vụ riêng, không đồng nhất với khóa duy nhất.

## 12. Tìm kiếm văn bản và dữ liệu gốc

Tìm kiếm cần quy tắc riêng với lưu trữ. Một trường tên có thể được tìm theo:

- Chuỗi chính xác;
- Không phân biệt hoa thường;
- Không phân biệt dấu;
- Tiền tố;
- Từ khóa toàn văn;
- Bí danh hoặc tên thay thế;
- Tên theo ngôn ngữ.

Không nên thay đổi dữ liệu gốc chỉ để làm tìm kiếm dễ hơn. Có thể tạo cột hoặc chỉ mục tìm kiếm đã chuẩn hóa, nhưng phải ghi rõ nó là dữ liệu dẫn xuất, có cách tạo và cập nhật.

Ví dụ, người dùng tìm “ca phe” có thể muốn thấy “cà phê”. Chức năng tìm kiếm có thể dùng khóa tìm kiếm không dấu. Nhưng nếu hai sản phẩm “Hoa” và “Hòa” khác nhau, việc bỏ dấu không được dùng làm định danh hoặc quy tắc duy nhất.

Nếu hệ thống hỗ trợ nhiều ngôn ngữ, cần xác định tên nào là tên chính, tên nào là bản dịch, ngôn ngữ nào được ưu tiên và việc đổi ngôn ngữ có ảnh hưởng tới định danh hay không. ID sản phẩm vẫn ổn định dù tên hiển thị thay đổi.

## 13. Thay đổi quy tắc văn bản theo thời gian

Quy tắc Unicode, collation, thư viện xử lý chuỗi và yêu cầu nghiệp vụ có thể thay đổi. Việc thay đổi quy tắc có thể làm phát sinh xung đột giữa những giá trị trước đây được coi là khác nhau.

Trước khi thay đổi:

1. Xác định trường nào chịu ảnh hưởng.
2. Kiểm tra dữ liệu hiện tại theo quy tắc mới.
3. Tìm các giá trị trở thành trùng sau chuẩn hóa hoặc đổi collation.
4. Xác định cách xử lý xung đột và người có thẩm quyền quyết định.
5. Lập kế hoạch cập nhật dữ liệu, index và ứng dụng.
6. Kiểm tra tích hợp và khả năng đọc dữ liệu cũ.
7. Triển khai theo phiên bản, có sao lưu và phương án khôi phục.

Không nên đổi collation hoặc chuẩn hóa dữ liệu hàng loạt mà chưa kiểm tra tác động tới unique index. Hai mã trước đây khác nhau có thể trở thành tương đương theo quy tắc mới, làm migration thất bại hoặc gây nhầm lẫn tham chiếu.

Nếu mã kỹ thuật đã được trao đổi với hệ thống ngoài, thay đổi quy tắc mã có thể là thay đổi hợp đồng tích hợp. Cần có phiên bản hoặc quy trình chuyển đổi tương thích thay vì âm thầm đổi giá trị.

## 14. Những lỗi thường gặp

1. **Dùng kiểu số cho mã:** làm mất số 0 đầu hoặc khiến hệ thống thực hiện phép tính không có ý nghĩa.
2. **Giới hạn độ dài theo byte nhưng mô tả là ký tự:** người dùng nhập ít ký tự vẫn bị từ chối khi dùng tiếng Việt hoặc emoji.
3. **Giả định một ký tự hiển thị bằng một code point:** gây cắt chuỗi hoặc đếm độ dài sai.
4. **Không thống nhất encoding:** dữ liệu tiếng Việt bị mojibake khi đi qua driver hoặc công cụ import/export.
5. **Bỏ qua Unicode normalization:** chuỗi nhìn giống nhau nhưng không khớp khi so sánh chính xác.
6. **Dùng NFKC hoặc bỏ dấu trên dữ liệu gốc mà không đánh giá:** làm thay đổi những khác biệt có thể mang ý nghĩa.
7. **Dùng collation chung cho mọi cột:** mã kỹ thuật và tên hiển thị có nhu cầu so sánh khác nhau.
8. **Tạo UNIQUE trên tên hiển thị:** ngăn các đối tượng hợp lệ có cùng tên.
9. **Tự động xóa ký tự lạ:** mã hoặc nội dung bị biến đổi mà người dùng không biết.
10. **Không kiểm tra khoảng trắng và ký tự điều khiển:** mã nhìn giống nhau nhưng không khớp.
11. **Coi TEXT là không giới hạn:** bỏ qua giới hạn API, giao thức, bộ nhớ và dung lượng lưu trữ.
12. **Không kiểm tra sau khi đổi collation hoặc chuẩn hóa:** unique index có thể phát sinh xung đột.

## 15. Checklist thiết kế thuộc tính văn bản

- [ ] Đã xác định chuỗi là văn bản tự do, tên hiển thị, mã nghiệp vụ hay định danh kỹ thuật.
- [ ] Đã xác định ai tạo giá trị và giá trị có thể thay đổi hay không.
- [ ] Hệ thống hỗ trợ Unicode xuyên suốt từ giao diện đến database và tích hợp.
- [ ] Đã chọn encoding phù hợp và kiểm tra import/export.
- [ ] Đã xác định có chuẩn hóa Unicode hay không, dùng dạng nào và ở bước nào.
- [ ] Đã phân biệt chuẩn hóa, lowercase, case folding và bỏ dấu.
- [ ] Đã xác định collation và quy tắc so sánh cho từng nhóm thuộc tính.
- [ ] Độ dài nghiệp vụ được đo theo đơn vị rõ ràng.
- [ ] Giới hạn lưu trữ đủ cho encoding và kiểu dữ liệu thực tế.
- [ ] Quy tắc cắt chuỗi không làm hỏng code point hoặc grapheme cluster.
- [ ] Mã kỹ thuật có bảng ký tự, độ dài, hoa/thường và phạm vi duy nhất rõ ràng.
- [ ] Mã có số 0 đầu được lưu như chuỗi.
- [ ] Khoảng trắng, ký tự điều khiển và ký tự định dạng được xử lý theo từng loại trường.
- [ ] Dữ liệu gốc được giữ khi cần bảo toàn nội dung hiển thị hoặc lịch sử.
- [ ] Tìm kiếm không dấu hoặc không phân biệt hoa thường được tách khỏi định danh.
- [ ] Thay đổi normalization hoặc collation có kiểm tra xung đột và kế hoạch migration.

## 16. Bài tập thực hành

Một hệ thống quản lý sản phẩm có các yêu cầu:

- Tên sản phẩm hỗ trợ tiếng Việt và tiếng Anh.
- SKU chỉ gồm chữ Latin, số và dấu gạch ngang.
- SKU không phân biệt chữ hoa và chữ thường.
- Tên sản phẩm được giới hạn theo số ký tự người dùng nhìn thấy.
- Người dùng có thể tìm sản phẩm bằng từ khóa không dấu.
- Mô tả sản phẩm có thể chứa xuống dòng.
- Mã sản phẩm phải duy nhất trong từng tổ chức.

Hãy đề xuất đặc tả logic cho các thuộc tính:

1. product_id;
2. sku;
3. product_name;
4. product_description;
5. search_name;
6. tenant_id.

Cần nêu rõ kiểu khái niệm, encoding, độ dài, normalization, collation, tính duy nhất và cách xử lý khoảng trắng.

**Gợi ý đáp án:**

| Thuộc tính | Đặc tả tham khảo |
|---|---|
| product_id | Định danh kỹ thuật ổn định, không phụ thuộc tên sản phẩm; khóa chính |
| sku | Chuỗi ASCII theo tập ký tự đã công bố; chuẩn hóa chữ hoa; không khoảng trắng; UNIQUE theo tenant_id |
| product_name | Văn bản Unicode; hỗ trợ tiếng Việt và tiếng Anh; NFC cho dạng chuẩn so sánh; giới hạn theo grapheme cluster |
| product_description | Văn bản Unicode dài; cho phép xuống dòng; không trim hoặc xóa ký tự nội dung một cách máy móc |
| search_name | Giá trị dẫn xuất phục vụ tìm kiếm; có thể lowercase và bỏ dấu theo quy tắc tìm kiếm; không dùng làm khóa |
| tenant_id | Định danh tổ chức; tham gia phạm vi duy nhất của SKU và tham chiếu tenant hợp lệ |

Một phương án triển khai có thể lưu tên gốc và tạo search_name riêng. Khi tìm kiếm không dấu, ứng dụng hoặc bộ máy tìm kiếm áp dụng cùng quy tắc biến đổi. SKU được chuẩn hóa trước khi kiểm tra trùng và lưu theo một biểu diễn duy nhất.

**Các câu hỏi cần xác nhận thêm:** giới hạn tên sản phẩm là bao nhiêu grapheme cluster; SKU có được đổi sau khi đã phát sinh giao dịch không; một SKU có thể được dùng lại sau khi sản phẩm ngừng kinh doanh không; và tổ chức có thể chia sẻ mã với tổ chức khác hay không.

Bài tập đạt yêu cầu khi đặc tả tách biệt rõ văn bản hiển thị và mã kỹ thuật, đo độ dài đúng đơn vị, giữ được tiếng Việt, tìm kiếm không dấu mà không làm mất tên gốc, và kiểm tra SKU duy nhất trong đúng phạm vi tổ chức.

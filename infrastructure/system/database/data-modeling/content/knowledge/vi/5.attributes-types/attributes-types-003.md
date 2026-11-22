# Miền giá trị và lựa chọn kiểu theo ý nghĩa nghiệp vụ

Khi thiết kế thuộc tính cho một mô hình dữ liệu, tên cột và kiểu lưu trữ mới chỉ mô tả được một phần ý nghĩa. Ta còn phải xác định thuộc tính đại diện cho điều gì, những giá trị nào được phép xuất hiện, đơn vị đo là gì, độ chính xác cần giữ đến đâu, giá trị có thể vắng mặt trong trường hợp nào và hệ thống sẽ kiểm tra quy tắc đó ở đâu.

**Miền giá trị (value domain)** mô tả tập hợp các giá trị hợp lệ mà một thuộc tính hoặc nhóm thuộc tính có thể nhận. Miền giá trị có thể được xác định bởi kiểu dữ liệu, giới hạn, đơn vị, danh mục mã, quy tắc định dạng, quan hệ với thuộc tính khác và điều kiện nghiệp vụ. Chọn kiểu dữ liệu đúng theo ý nghĩa nghiệp vụ giúp dữ liệu được lưu chính xác, truy vấn nhất quán, kiểm tra được và dễ trao đổi giữa các hệ thống.

Ví dụ, số lượng sản phẩm là một đại lượng đếm không âm; giá tiền là một đại lượng có đơn vị tiền tệ và quy tắc làm tròn; ngày sinh là một ngày lịch, không phải thời điểm có múi giờ; mã đơn hàng là một định danh, không phải số để cộng trừ. Dù các giá trị này có thể được biểu diễn bằng số hoặc chuỗi, chúng có ý nghĩa và quy tắc khác nhau.

Bài học này trình bày cách xác định miền giá trị từ yêu cầu nghiệp vụ, lựa chọn kiểu dữ liệu, biểu diễn các giới hạn và xử lý những trường hợp dễ gây lỗi khi chuyển mô hình logic thành lược đồ lưu trữ.

## 1. Miền giá trị là gì?

Miền giá trị là tập hợp các giá trị mà một thuộc tính được phép nhận theo định nghĩa nghiệp vụ. Một miền thường gồm nhiều thành phần:

- **Kiểu biểu diễn:** số nguyên, số thập phân, chuỗi, ngày giờ, Boolean, mã hoặc cấu trúc phức hợp.
- **Phạm vi:** giá trị nhỏ nhất, lớn nhất hoặc tập giá trị cho phép.
- **Đơn vị:** đồng tiền, kilogram, mét, phần trăm, số lượng sản phẩm hoặc đơn vị nghiệp vụ khác.
- **Độ chính xác:** số chữ số, số chữ số thập phân hoặc độ phân giải thời gian.
- **Quy tắc định dạng:** mẫu mã, độ dài, chữ hoa/thường, ký tự được phép.
- **Tính bắt buộc:** có được để trống hoặc chưa xác định không.
- **Quy tắc phụ thuộc:** giá trị có hợp lệ khi kết hợp với thuộc tính khác hay không.
- **Ngữ nghĩa thời gian:** giá trị mô tả ngày lịch, thời điểm tuyệt đối, thời gian địa phương hay khoảng thời lượng.

Ví dụ miền của số lượng dòng hàng có thể được mô tả như sau:

| Thành phần | Quy tắc |
|---|---|
| Ý nghĩa | Số đơn vị sản phẩm được đặt trong một dòng hàng |
| Kiểu khái niệm | Số lượng |
| Miền | Số nguyên lớn hơn 0 |
| Đơn vị | Cái |
| Độ chính xác | Số nguyên |
| Tính bắt buộc | Bắt buộc |
| Kiểm tra | Không nhận số âm, số 0 hoặc phần thập phân |

Miền của nhiệt độ bảo quản có thể khác: số thập phân, đơn vị độ C, giới hạn theo từng loại hàng và có thể cần độ chính xác một chữ số thập phân. Không thể chọn kiểu chỉ dựa vào việc cả hai đều là số.

### 1.1. Phân biệt kiểu dữ liệu và miền giá trị

Kiểu dữ liệu xác định cách giá trị được biểu diễn và những phép toán cơ bản mà hệ thống hỗ trợ. Miền giá trị bổ sung ý nghĩa nghiệp vụ và các giới hạn cụ thể.

Ví dụ, kiểu INTEGER có thể chứa nhiều số nguyên âm và dương. Nhưng thuộc tính quantity trong một đơn hàng chỉ cho phép số nguyên dương. Do đó:

- Kiểu dữ liệu: số nguyên.
- Miền giá trị: số nguyên lớn hơn 0.
- Quy tắc bổ sung: không vượt giới hạn số lượng được phép đặt cho một đơn hàng.

Một kiểu dữ liệu có thể được dùng cho nhiều miền khác nhau. Hai thuộc tính cùng dùng VARCHAR(50) không có nghĩa chúng có cùng ý nghĩa hoặc cùng quy tắc. Mã bưu chính, mã sản phẩm, tên hiển thị và số điện thoại đều có thể được lưu dưới dạng chuỗi nhưng cần quy tắc kiểm tra khác nhau.

### 1.2. Miền giá trị không chỉ là giới hạn min và max

Một thuộc tính có thể cần thỏa mãn nhiều điều kiện hơn một khoảng số học.

Ví dụ, tỷ lệ chiết khấu có thể nằm trong khoảng 0 đến 100%, nhưng còn phụ thuộc loại khuyến mại, thời điểm áp dụng và quyền phê duyệt. Mã quốc gia có thể có độ dài cố định nhưng phải thuộc danh mục mã được công nhận. Ngày kết thúc hợp đồng phải lớn hơn hoặc bằng ngày bắt đầu. Email có thể đúng cấu trúc cú pháp nhưng vẫn chưa được xác minh hoặc không còn được phép sử dụng.

Vì vậy, hãy xác định miền giá trị ở mức nghiệp vụ trước, sau đó phân bổ các quy tắc vào kiểu dữ liệu, ràng buộc cơ sở dữ liệu, kiểm tra ứng dụng hoặc quy trình xác minh bên ngoài.

## 2. Thu thập ý nghĩa nghiệp vụ trước khi chọn kiểu

### 2.1. Hỏi thuộc tính đại diện cho điều gì?

Tên thuộc tính đôi khi mơ hồ. Ví dụ:

- amount có thể là số tiền phải thu, đã thu, đã hoàn hoặc còn nợ.
- date có thể là ngày tạo, ngày hiệu lực, ngày giao hoặc ngày hệ thống ghi nhận.
- status có thể là trạng thái đơn hàng, thanh toán, giao hàng hoặc trạng thái xử lý nội bộ.
- count có thể là số lượng đơn hàng, số lượt thử hoặc số bản ghi đã xử lý.
- rate có thể là tỷ lệ phần trăm, tốc độ trên đơn vị thời gian hoặc lãi suất.

Trước khi chọn kiểu, hãy viết một câu định nghĩa rõ nghĩa của thuộc tính. Nếu hai thuộc tính có cùng tên nhưng ý nghĩa khác nhau, cần dùng tên cụ thể hơn hoặc ghi định nghĩa riêng trong từ điển dữ liệu.

### 2.2. Hỏi đơn vị và quy ước

Mọi đại lượng đo lường cần có đơn vị và quy ước. Ví dụ:

- Khối lượng lưu bằng gram hay kilogram?
- Khoảng cách lưu bằng mét hay kilomet?
- Nhiệt độ dùng độ C hay độ F?
- Số tiền dùng loại tiền tệ nào?
- Phần trăm được lưu theo thang 0–100 hay 0–1?
- Thời gian lưu bằng giây, mili giây hay phút?
- Kích thước lưu theo centimet hay millimet?

Không nên dựa vào tên cột để ngầm đoán đơn vị. Hai hệ thống cùng lưu weight = 5 nhưng một bên hiểu là kilogram, bên kia hiểu là gram có thể tạo ra sai lệch nghiêm trọng.

### 2.3. Hỏi giới hạn và trường hợp biên

Cần làm rõ:

- Giá trị nhỏ nhất và lớn nhất được phép.
- Có cho phép số âm không?
- Có cho phép số 0 không?
- Có cho phép phần thập phân không?
- Có thể vượt giới hạn trong một trạng thái đặc biệt không?
- Giá trị cực đại có thể tăng theo thời gian không?
- Giá trị ngoài miền được từ chối, làm tròn, chuyển đổi hay đưa vào hàng chờ xử lý?

Ví dụ, tồn kho khả dụng thường không được âm, nhưng số lượng điều chỉnh kho có thể âm vì nó mô tả lượng tăng hoặc giảm. Không nên áp dụng cùng một miền cho hai thuộc tính chỉ vì chúng cùng liên quan đến số lượng.

### 2.4. Hỏi dữ liệu có thể vắng mặt không?

Cần phân biệt:

- Không biết giá trị.
- Chưa thu thập.
- Không áp dụng cho trường hợp này.
- Người dùng từ chối cung cấp.
- Giá trị chưa được xác minh.
- Giá trị đã bị xóa theo chính sách.

Các trường hợp này có thể cần cách biểu diễn khác nhau. Một giá trị NULL thường chỉ cho biết không có giá trị được lưu, nhưng không tự giải thích lý do. Nếu nghiệp vụ cần phân biệt các trạng thái, có thể cần thêm thuộc tính trạng thái hoặc mô hình hóa quy trình thu thập.

## 3. Phân loại các miền giá trị phổ biến

### 3.1. Miền số nguyên

Dùng số nguyên cho các đại lượng đếm hoặc mã số học thực sự cần phép toán số học.

Ví dụ:

- Số lượng sản phẩm.
- Số lần thử.
- Số thứ tự dòng hàng.
- Số ngày trong một khoảng đếm.
- Phiên bản tăng dần.

Cần chọn phạm vi phù hợp với giá trị lớn nhất dự kiến. Số nguyên nhỏ tiết kiệm dung lượng hơn trong một số hệ quản trị, nhưng chọn quá nhỏ có thể gây tràn số khi dữ liệu tăng. Hãy dựa vào giới hạn nghiệp vụ, tốc độ tăng và vòng đời hệ thống.

Mã có các chữ số nhưng không mang ý nghĩa số học thường nên lưu dưới dạng chuỗi. Ví dụ mã bưu chính 01234 cần giữ số 0 ở đầu; mã nhân viên 000172 không nên bị chuyển thành 172 nếu định dạng là một phần của mã.

### 3.2. Miền số thập phân chính xác

Dùng kiểu số thập phân chính xác cho các đại lượng cần giữ giá trị theo quy tắc thập phân, đặc biệt là tiền tệ, tỷ lệ và phép tính kế toán.

Ví dụ:

- Đơn giá.
- Tổng tiền hóa đơn.
- Thuế.
- Tỷ lệ hoa hồng.
- Khối lượng có số lẻ.
- Số đo cần độ chính xác xác định.

Trong nhiều hệ quản trị quan hệ, kiểu DECIMAL hoặc NUMERIC cho phép khai báo precision và scale. Precision là tổng số chữ số được lưu; scale là số chữ số sau dấu thập phân.

Ví dụ NUMERIC(12, 2) cho phép tối đa 12 chữ số tổng cộng, trong đó có 2 chữ số thập phân. Giá trị tối đa dương là 9.999.999.999,99. Con số cụ thể phải phù hợp miền nghiệp vụ.

### 3.3. Miền số thực dấu phẩy động

FLOAT, REAL hoặc DOUBLE PRECISION thường biểu diễn số thực theo dạng dấu phẩy động nhị phân. Chúng phù hợp với tính toán khoa học, mô phỏng, đo lường hoặc thuật toán chấp nhận sai số làm tròn.

Không nên mặc định dùng FLOAT cho tiền tệ hoặc các phép tính cần đối chiếu chính xác từng đơn vị nhỏ nhất. Một số số thập phân không thể biểu diễn chính xác bằng dạng nhị phân, nên phép cộng và so sánh có thể tạo ra sai số nhỏ.

Nếu nghiệp vụ cần số tiền chính xác đến đồng hoặc cent, dùng số thập phân chính xác hoặc biểu diễn bằng số nguyên theo đơn vị nhỏ nhất đã thống nhất.

### 3.4. Miền chuỗi ký tự

Chuỗi dùng cho dữ liệu văn bản, mã, tên, mô tả và các giá trị định dạng.

Cần phân biệt:

- Độ dài tối đa theo ký tự hay byte.
- Có cho phép chuỗi rỗng không.
- Có phân biệt chữ hoa và chữ thường không.
- Có chuẩn hóa khoảng trắng hoặc Unicode không.
- Có quy tắc định dạng hoặc tập ký tự hợp lệ không.
- Có cần tìm kiếm toàn văn hoặc so sánh không phân biệt dấu không.

CHAR thường phù hợp với chuỗi có độ dài cố định theo cách triển khai của hệ quản trị; VARCHAR phù hợp với chuỗi có độ dài biến đổi; TEXT thường dùng cho văn bản dài. Chi tiết về lưu trữ và giới hạn khác nhau giữa các hệ quản trị, vì vậy cần xem tài liệu của nền tảng được chọn.

Không nên đặt độ dài tùy tiện. Tên người, địa chỉ, mã sản phẩm và ghi chú có phân bố độ dài khác nhau. Hãy khảo sát dữ liệu thực tế, tiêu chuẩn liên quan và khả năng mở rộng.

### 3.5. Miền Boolean

Boolean biểu diễn hai giá trị logic true và false. Tuy nhiên, nghiệp vụ đôi khi cần ba trạng thái: có, không và chưa biết. NULL có thể đại diện cho chưa biết, nhưng cần xác định rõ ý nghĩa của NULL và cách truy vấn.

Ví dụ, is_verified có thể có:
- TRUE: đã xác minh.
- FALSE: đã xác minh và kết quả không đạt hoặc chưa xác minh, tùy định nghĩa.
- NULL: chưa có kết quả.

Nếu “chưa gửi xác minh”, “đang chờ”, “thất bại” và “đã xác minh” là các trạng thái khác nhau, một Boolean không đủ; hãy dùng miền trạng thái rõ ràng.

### 3.6. Miền ngày và thời gian

Thời gian có nhiều ý nghĩa khác nhau:

- Ngày lịch, ví dụ ngày sinh hoặc ngày đáo hạn.
- Thời điểm tuyệt đối, ví dụ lúc thanh toán được xác nhận.
- Thời gian địa phương theo một múi giờ, ví dụ giờ mở cửa cửa hàng.
- Khoảng thời lượng, ví dụ thời gian xử lý.
- Khoảng hiệu lực, ví dụ một hợp đồng có hiệu lực từ ngày nào đến ngày nào.

Không dùng một kiểu timestamp cho mọi trường hợp. Ngày sinh thường nên lưu kiểu DATE vì không cần múi giờ. Thời điểm giao dịch thường cần một thời điểm tuyệt đối, được chuẩn hóa và hiển thị theo múi giờ phù hợp. Giờ mở cửa có thể cần cả thời gian địa phương lẫn múi giờ của địa điểm.

### 3.7. Miền mã và danh mục

Mã nghiệp vụ như trạng thái đơn hàng, loại sản phẩm, quốc gia, phương thức thanh toán hoặc đơn vị tính có thể được biểu diễn bằng enum, chuỗi có ràng buộc hoặc khóa tham chiếu tới bảng danh mục.

Chọn cách nào phụ thuộc vào:
- Danh sách giá trị có cố định hay thay đổi thường xuyên.
- Có cần metadata cho từng giá trị không.
- Có cần hiệu lực theo thời gian không.
- Có nhiều hệ thống cần dùng chung mã không.
- Có cần bản dịch hoặc nhãn hiển thị đa ngôn ngữ không.
- Việc thêm giá trị mới có cần triển khai lại ứng dụng không.

Enum có thể thuận tiện khi tập giá trị nhỏ và ổn định. Bảng tham chiếu phù hợp hơn khi danh mục cần được quản trị, có mô tả, trạng thái, thứ tự hiển thị hoặc người chịu trách nhiệm.

### 3.8. Miền nhị phân và dữ liệu lớn

Dữ liệu nhị phân có thể dùng để lưu nội dung tệp, ảnh hoặc dữ liệu mã hóa. Tuy nhiên, cần cân nhắc lưu trực tiếp trong cơ sở dữ liệu hay lưu ở object storage và giữ tham chiếu trong mô hình dữ liệu.

Cần xác định kích thước tối đa, loại nội dung, checksum, thời hạn lưu, quyền truy cập và cách xử lý khi tệp bị thay thế hoặc xóa. Không nên dùng trường BLOB cho mọi tệp mà không có nhu cầu truy vấn và vận hành rõ ràng.

### 3.9. Miền cấu trúc linh hoạt như JSON

JSON có thể phù hợp cho dữ liệu bán cấu trúc, thuộc tính mở rộng hoặc payload tích hợp mà schema thay đổi theo loại đối tượng. Tuy nhiên, dùng JSON không có nghĩa là không cần mô hình hóa.

Cần xác định:
- Những trường nào là bắt buộc.
- Kiểu dữ liệu và miền hợp lệ của từng trường.
- Cấu trúc nào được phép thay đổi.
- Trường nào cần truy vấn, lọc hoặc đánh chỉ mục.
- Cách quản lý phiên bản schema.
- Quy tắc xử lý trường không được nhận diện.

Nếu một thuộc tính được dùng thường xuyên trong lọc, nối, ràng buộc hoặc báo cáo, cân nhắc đưa nó thành cột có kiểu rõ ràng. JSON nên phục vụ phần linh hoạt có chủ đích, không thay thế toàn bộ mô hình dữ liệu.

## 4. Chọn kiểu theo ý nghĩa nghiệp vụ

Bảng sau minh họa cách chuyển từ khái niệm nghiệp vụ sang kiểu biểu diễn. Tên kiểu cụ thể có thể khác giữa PostgreSQL, MySQL, SQL Server, Oracle hoặc các hệ thống NoSQL.

| Ý nghĩa nghiệp vụ | Kiểu khái niệm | Lựa chọn thường gặp | Điều cần kiểm tra |
|---|---|---|---|
| Số lượng sản phẩm | Số nguyên đếm | INTEGER hoặc BIGINT | Có cho phép 0, âm hoặc phần lẻ không? |
| Tiền tệ | Số thập phân chính xác + currency | DECIMAL/NUMERIC hoặc số nguyên đơn vị nhỏ nhất | Precision, scale, loại tiền và làm tròn |
| Tỷ lệ phần trăm | Số thập phân hoặc số nguyên theo quy ước | NUMERIC/DECIMAL | Lưu 0–100 hay 0–1? |
| Mã đơn hàng | Định danh dạng chuỗi | VARCHAR hoặc UUID | Phạm vi duy nhất, khả năng đổi mã |
| Ngày sinh | Ngày lịch | DATE | Không cần múi giờ |
| Thời điểm thanh toán | Thời điểm tuyệt đối | Timestamp có quy ước múi giờ | UTC, độ chính xác và nguồn thời gian |
| Giờ mở cửa | Giờ địa phương + múi giờ | TIME và timezone identifier | Giờ mùa hè và địa điểm |
| Có được kích hoạt không | Boolean hoặc trạng thái | BOOLEAN hoặc mã trạng thái | Có trạng thái chưa biết/chờ không? |
| Email | Văn bản có quy tắc định dạng | VARCHAR/TEXT | Chuẩn hóa, xác minh, so sánh |
| Tọa độ địa lý | Số đo có đơn vị | Kiểu spatial hoặc số thập phân | Hệ tọa độ và độ chính xác |
| Nội dung tệp | Dữ liệu nhị phân hoặc tham chiếu | BLOB hoặc object key | Kích thước, quyền và vòng đời |
| Thuộc tính mở rộng | Dữ liệu có cấu trúc linh hoạt | JSON/JSONB hoặc document | Schema, kiểm tra và chỉ mục |

### 4.1. Không dùng kiểu số cho mọi chuỗi chỉ gồm chữ số

Một mã định danh có thể chỉ gồm các chữ số nhưng không có ý nghĩa cộng trừ. Ví dụ:
- Mã bưu chính.
- Mã khách hàng.
- Số điện thoại.
- Mã vận đơn.
- Số tài khoản được hiển thị.
- Mã sản phẩm có số 0 ở đầu.

Lưu các giá trị này bằng kiểu chuỗi giúp giữ nguyên định dạng và tránh phép toán không có ý nghĩa. Nếu cần kiểm tra chỉ gồm chữ số hoặc theo mẫu cụ thể, dùng validation hoặc constraint phù hợp.

### 4.2. Không dùng chuỗi cho đại lượng cần tính toán

Lưu tiền, số lượng hoặc thời gian dưới dạng chuỗi khiến việc so sánh, sắp xếp và tính toán khó chính xác. Ví dụ, sắp xếp chuỗi "100" và "20" theo thứ tự từ điển không giống sắp xếp số.

Nếu dữ liệu là đại lượng, chọn kiểu số hoặc kiểu thời gian phù hợp. Chỉ chuyển sang chuỗi ở lớp hiển thị hoặc tích hợp khi hợp đồng yêu cầu.

### 4.3. Chọn precision và scale từ nghiệp vụ

Với số thập phân, hãy xác định:
- Giá trị lớn nhất dự kiến.
- Số chữ số thập phân có ý nghĩa.
- Quy tắc làm tròn.
- Có cần giữ độ chính xác trung gian cao hơn độ chính xác hiển thị không.
- Đơn vị nhỏ nhất mà nghiệp vụ cho phép.

Ví dụ, một đơn giá có thể được lưu đến 4 chữ số thập phân để tính toán, trong khi tổng tiền thanh toán được làm tròn đến 2 chữ số theo quy tắc tiền tệ. Không nên làm tròn ở mỗi bước nếu nghiệp vụ yêu cầu giữ độ chính xác đến bước cuối.

### 4.4. Chọn kiểu theo giới hạn tăng trưởng

Không chọn INTEGER chỉ vì dữ liệu hiện tại nhỏ. Hãy dự báo:
- Số bản ghi tối đa trong vòng đời.
- Tốc độ tăng mỗi ngày hoặc mỗi năm.
- Giá trị có tăng đơn điệu không.
- Hệ thống có cần nhập dữ liệu lịch sử từ nguồn khác không.
- Có khả năng hợp nhất nhiều hệ thống không.

Chọn kiểu quá nhỏ có thể dẫn đến migration khó khăn. Chọn kiểu quá lớn cũng có thể ảnh hưởng dung lượng chỉ mục hoặc hiệu năng ở một số nền tảng. Hãy dựa vào yêu cầu và đặc tính hệ quản trị.

## 5. Đơn vị, độ chính xác và quy tắc làm tròn

### 5.1. Lưu đơn vị cùng ý nghĩa của đại lượng

Một số đo không có ý nghĩa đầy đủ nếu thiếu đơn vị. Có thể dùng tên cột rõ như weight_grams, distance_meters hoặc lưu giá trị cùng mã đơn vị.

Nếu nhiều đơn vị được phép, hãy chuẩn hóa về một đơn vị cơ sở để tính toán và lưu mã đơn vị khi cần giữ nguyên đơn vị nguồn. Ví dụ, cân nặng có thể nhập theo kilogram hoặc pound nhưng được quy đổi về gram hoặc kilogram theo quy tắc thống nhất.

Không tự ý quy đổi nếu nghiệp vụ cần giữ cả giá trị ban đầu, đơn vị gốc và kết quả quy đổi. Trong trường hợp kiểm toán, nguồn và hệ số quy đổi có thể quan trọng.

### 5.2. Tiền tệ cần đi cùng mã tiền tệ

Một giá trị 100.00 không đủ để biết đó là 100 USD, 100 EUR hay 100.000 VND. Mô hình tiền tệ thường cần cả amount và currency_code.

Số chữ số thập phân hợp lệ phụ thuộc loại tiền tệ và quy tắc nghiệp vụ. Một số loại tiền có đơn vị nhỏ nhất khác nhau; một số nghiệp vụ còn có quy tắc làm tròn riêng cho thuế, thanh toán hoặc kế toán.

Ví dụ cấu trúc khái niệm:

| Thuộc tính | Ý nghĩa |
|---|---|
| amount | Giá trị tiền theo quy ước precision/scale |
| currency_code | Mã loại tiền tệ |
| rounding_rule | Quy tắc làm tròn nếu cần lưu theo giao dịch |
| exchange_rate | Tỷ giá khi chuyển đổi, nếu có |
| rate_source | Nguồn tỷ giá |
| rate_time | Thời điểm áp dụng tỷ giá |

Không nhất thiết mọi bảng đều cần tất cả trường trên. Chỉ lưu những gì cần để tái lập giao dịch và đáp ứng yêu cầu nghiệp vụ.

### 5.3. Phần trăm và tỷ lệ

Cùng một tỷ lệ 5% có thể được biểu diễn bằng 5 hoặc 0.05. Cần thống nhất quy ước trong mô hình và hợp đồng dữ liệu.

Nếu lưu 0.05, trường có thể mang tên discount_rate và miền 0 đến 1. Nếu lưu 5, trường có thể mang tên discount_percent và miền 0 đến 100. Không dùng tên mơ hồ như rate mà không ghi định nghĩa.

### 5.4. Quy tắc làm tròn phải rõ

Các cách làm tròn khác nhau có thể tạo kết quả khác nhau, nhất là khi tính thuế, chiết khấu hoặc phân bổ tổng tiền cho nhiều dòng hàng.

Hãy xác định:
- Làm tròn ở từng dòng hay sau khi cộng tổng?
- Dùng half-up, half-even hay quy tắc khác?
- Số chữ số giữ trong phép tính trung gian?
- Xử lý sai lệch một đơn vị nhỏ nhất khi phân bổ tổng?
- Quy tắc theo từng loại tiền tệ hoặc khu vực?

Không nên để mỗi dịch vụ tự làm tròn theo thư viện mặc định. Quy tắc cần được ghi trong đặc tả nghiệp vụ và áp dụng nhất quán.

## 6. Kiểu ngày giờ và múi giờ

### 6.1. Ngày lịch không phải thời điểm

Ngày sinh, ngày phát hành giấy phép hoặc ngày đáo hạn thường là ngày lịch. Chúng không đại diện cho một thời điểm cụ thể trên dòng thời gian và không cần quy đổi theo múi giờ.

Thời điểm thanh toán, thời điểm nhận sự kiện hoặc thời điểm tạo bản ghi lại là một thời điểm. Nếu lưu như ngày lịch, hệ thống sẽ mất thông tin giờ, phút và thứ tự giữa các sự kiện trong ngày.

### 6.2. Thời điểm tuyệt đối và thời gian địa phương

Một sự kiện xảy ra tại một thời điểm có thể được chuẩn hóa về UTC để trao đổi và sắp xếp. Khi hiển thị, hệ thống chuyển sang múi giờ của người dùng hoặc địa điểm nghiệp vụ.

Giờ mở cửa cửa hàng lại là thời gian địa phương: 09:00 đến 18:00 tại một địa điểm. Nếu cửa hàng nằm ở khu vực có quy tắc giờ mùa hè, cần lưu timezone identifier phù hợp thay vì chỉ lưu độ lệch UTC cố định.

### 6.3. Chọn độ chính xác thời gian

Không phải trường hợp nào cũng cần microsecond. Hãy xác định độ phân giải theo nghiệp vụ:

- Ngày lịch: không cần phần thời gian.
- Thời điểm giao dịch: thường cần giây hoặc mili giây tùy thứ tự và đối soát.
- Dữ liệu cảm biến: có thể cần độ phân giải cao hơn.
- Lịch hẹn: cần thời gian địa phương, múi giờ và quy tắc lặp.

Độ chính xác cao hơn không tự động làm dữ liệu đúng hơn. Nguồn đồng hồ, đồng bộ thời gian và ý nghĩa của timestamp vẫn cần được xác định.

### 6.4. Thời gian hiệu lực và thời gian ghi nhận

Một thuộc tính có thể cần hai mốc:
- Thời điểm dữ kiện bắt đầu có hiệu lực trong nghiệp vụ.
- Thời điểm hệ thống nhận hoặc ghi nhận dữ kiện.

Ví dụ, một thay đổi địa chỉ được nhập ngày 10 nhưng có hiệu lực từ ngày 1. Nếu chỉ lưu một timestamp, không thể trả lời chính xác cả hai câu hỏi “địa chỉ có hiệu lực từ khi nào?” và “hệ thống biết điều đó từ khi nào?”.

## 7. NULL, giá trị mặc định và miền tùy chọn

### 7.1. NULL không phải số 0 hoặc chuỗi rỗng

NULL thường biểu thị không có giá trị được xác định. Nó khác:
- 0: giá trị số cụ thể.
- Chuỗi rỗng: chuỗi có độ dài bằng 0.
- FALSE: giá trị Boolean phủ định.
- Một mã “không áp dụng”: giá trị nghiệp vụ cụ thể.
- Một giá trị mặc định: giá trị được hệ thống điền theo quy tắc.

Dùng 0 thay NULL có thể làm sai phép tính và báo cáo. Dùng chuỗi rỗng thay NULL có thể khiến hệ thống không phân biệt dữ liệu chưa nhập với dữ liệu nhập là rỗng.

### 7.2. Xác định lý do thiếu dữ liệu

Nếu nghiệp vụ cần phân biệt các tình huống, có thể dùng một thuộc tính trạng thái hoặc mô hình dữ liệu riêng.

Ví dụ, ngày xác minh có thể:
- NULL vì chưa bắt đầu xác minh.
- Có giá trị khi đã xác minh.
- Trạng thái riêng là rejected khi xác minh thất bại.

Không nên suy ra mọi trạng thái từ việc ngày có NULL hay không nếu có nhiều bước trung gian.

### 7.3. Giá trị mặc định phải có ý nghĩa

DEFAULT chỉ nên dùng khi có một giá trị mặc định đúng theo nghiệp vụ. Ví dụ, số lần thử ban đầu có thể mặc định bằng 0. Nhưng country = VN chỉ hợp lệ nếu quy trình bảo đảm mọi bản ghi mới đều thuộc Việt Nam; không nên dùng làm mặc định chỉ vì phần lớn khách hàng hiện tại ở Việt Nam.

### 7.4. NOT NULL là một quyết định nghiệp vụ

Đặt NOT NULL nghĩa là mọi bản ghi hợp lệ đều phải có giá trị. Hãy xác định thời điểm bắt buộc:
- Ngay khi tạo bản ghi.
- Sau khi hoàn tất một bước.
- Khi chuyển sang trạng thái đã xác nhận.
- Chỉ bắt buộc với một loại đối tượng hoặc kênh cụ thể.

Một trường có thể tạm thời chưa có giá trị khi bản ghi đang ở trạng thái draft, nhưng bắt buộc trước khi submit. Nếu cơ sở dữ liệu không thể biểu diễn điều kiện theo trạng thái bằng constraint đơn giản, cần có kiểm tra ở transaction hoặc quy trình ứng dụng.

## 8. Mã hóa miền bằng kiểu và ràng buộc

### 8.1. Ràng buộc NOT NULL, CHECK và UNIQUE

Trong mô hình quan hệ, các ràng buộc giúp đảm bảo miền dữ liệu ngay tại nơi lưu trữ.

Ví dụ SQL minh họa:

~~~sql
CREATE TABLE order_item (
    order_item_id BIGINT PRIMARY KEY,
    order_id      BIGINT NOT NULL,
    line_number   INTEGER NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    currency_code VARCHAR(3) NOT NULL,
    sku           VARCHAR(40) NOT NULL,
    CONSTRAINT uq_order_item_order_line
        UNIQUE (order_id, line_number)
);
~~~

Ràng buộc trên chỉ là ví dụ về cú pháp. Quy tắc duy nhất cho dòng hàng cần được thiết kế theo nghiệp vụ thực tế; ví dụ này không khẳng định SKU phải duy nhất trong một đơn. Nếu cùng SKU có thể xuất hiện nhiều dòng, cần chọn khóa dòng phù hợp.

Các loại ràng buộc phổ biến:
- NOT NULL: không cho phép thiếu giá trị.
- CHECK: giới hạn miền giá trị hoặc quan hệ giữa các trường.
- UNIQUE: bảo đảm tính duy nhất trong phạm vi khai báo.
- PRIMARY KEY: định danh duy nhất và không NULL.
- FOREIGN KEY: bảo đảm tham chiếu đến bản ghi hợp lệ.

### 8.2. Dùng bảng tham chiếu cho miền có quản trị

Nếu danh sách mã thay đổi theo nghiệp vụ, có thể dùng bảng tham chiếu:

~~~sql
CREATE TABLE order_status (
    status_code VARCHAR(20) PRIMARY KEY,
    display_name VARCHAR(80) NOT NULL,
    is_terminal BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
~~~

Bảng đơn hàng tham chiếu mã trạng thái:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status_code VARCHAR(20) NOT NULL,
    CONSTRAINT fk_orders_status
        FOREIGN KEY (status_code)
        REFERENCES order_status(status_code)
);
~~~

Trong thực tế, nếu trạng thái có quy tắc chuyển đổi, không nên chỉ kiểm tra mã có tồn tại. Cần kiểm soát chuyển trạng thái theo quy trình nghiệp vụ, ví dụ không cho đơn đã hủy chuyển thẳng sang đã giao.

### 8.3. Dùng domain type khi hệ quản trị hỗ trợ

Một số hệ quản trị quan hệ cho phép tạo kiểu miền (domain type) dựa trên kiểu cơ sở và gắn ràng buộc dùng chung.

Ví dụ PostgreSQL:

~~~sql
CREATE DOMAIN positive_quantity AS INTEGER
    CHECK (VALUE > 0);

CREATE DOMAIN currency_code AS VARCHAR(3)
    CHECK (char_length(VALUE) = 3 AND VALUE ~ '^[A-Z]{3}$');

CREATE TABLE order_line (
    order_line_id BIGINT PRIMARY KEY,
    quantity positive_quantity NOT NULL,
    currency currency_code NOT NULL
);
~~~

Domain type giúp tái sử dụng quy tắc cơ bản cho nhiều cột. Tuy nhiên, regex ba chữ cái chỉ kiểm tra định dạng, không chứng minh mã tiền tệ là mã hợp lệ. Nếu cần danh mục chuẩn và metadata, dùng bảng tham chiếu hoặc cơ chế kiểm tra tương ứng.

Cú pháp và khả năng hỗ trợ domain khác nhau giữa các hệ quản trị. Không nên phụ thuộc vào domain type nếu ứng dụng cần chạy trên nhiều nền tảng mà chưa có chiến lược tương thích.

### 8.4. Phân bổ kiểm tra giữa cơ sở dữ liệu và ứng dụng

Không phải mọi quy tắc đều có thể hoặc nên đặt trong CHECK constraint. Hãy phân loại:

- Quy tắc đơn giản trên một cột: kiểu, NOT NULL, CHECK.
- Quy tắc duy nhất: UNIQUE hoặc chỉ mục duy nhất.
- Tham chiếu: FOREIGN KEY.
- Quy tắc nhiều bản ghi hoặc cạnh tranh: transaction, khóa hoặc cơ chế cập nhật có kiểm soát.
- Quy tắc phụ thuộc dịch vụ ngoài: xác minh qua API hoặc quy trình tích hợp.
- Quy tắc phụ thuộc trạng thái và quyền: logic nghiệp vụ trong ranh giới giao dịch, kết hợp constraint cần thiết.

Kiểm tra ở ứng dụng cải thiện thông báo lỗi cho người dùng nhưng không nên là lớp bảo vệ duy nhất cho những bất biến cần đúng với mọi đường ghi dữ liệu.

## 9. Miền giá trị trong các mô hình lưu trữ khác nhau

Ý nghĩa miền dữ liệu cần nhất quán dù cách biểu diễn vật lý thay đổi.

### 9.1. Cơ sở dữ liệu quan hệ

Mô hình quan hệ thường hỗ trợ kiểu cột, ràng buộc, khóa và bảng tham chiếu rõ ràng. Phù hợp khi cần tính nhất quán mạnh ở mức dữ liệu có cấu trúc, truy vấn kết hợp và kiểm soát miền ngay tại cơ sở dữ liệu.

Cần lưu ý:
- Kiểu và cú pháp khác nhau giữa hệ quản trị.
- Enum hoặc domain type có thể gây khó khi thay đổi schema.
- Ràng buộc phức tạp cần cân nhắc hiệu năng và khả năng bảo trì.

### 9.2. Document database

Document database có thể lưu các thuộc tính trong một tài liệu, với cấu trúc linh hoạt. Tuy nhiên, từng trường vẫn cần định nghĩa kiểu và miền hợp lệ.

Cần xác định:
- Schema validation có được bật không?
- Các document cũ có thể thiếu trường mới không?
- Giá trị null khác với trường không tồn tại thế nào?
- Cách quản lý phiên bản schema.
- Những trường nào phải có cùng kiểu qua mọi document.
- Cách xử lý document không hợp lệ.

Sự linh hoạt của document không loại bỏ nhu cầu về miền giá trị. Nếu mỗi document tùy tiện dùng kiểu khác nhau cho cùng một trường, consumer sẽ phải xử lý nhiều trường hợp và dễ phát sinh lỗi.

### 9.3. Graph database

Trong graph database, node và relationship có thể mang properties. Các property cũng cần kiểu, miền và quy tắc. Ví dụ, cạnh OWNS có thể có valid_from, valid_to và ownership_share. Cần kiểm tra tỷ lệ sở hữu trong miền hợp lệ và tổng tỷ lệ của các quan hệ có thỏa mãn quy tắc nghiệp vụ hay không.

### 9.4. Kho dữ liệu phân tích

Kho phân tích thường cần kiểu hỗ trợ tổng hợp, lọc theo thời gian và lưu lịch sử. Cần xác định:
- Kiểu số có đủ precision không?
- Ngày và thời điểm có quy ước nhất quán không?
- Mã phân loại có được chuẩn hóa không?
- Giá trị thiếu có được phân biệt với giá trị bằng 0 không?
- Dữ liệu đã được quy đổi đơn vị hoặc tiền tệ chưa?
- Có lưu nguồn, thời điểm trích xuất và phiên bản biến đổi không?

Không nên chuyển mọi dữ liệu nghiệp vụ thành kiểu floating point hoặc chuỗi trong kho phân tích chỉ để nhập liệu dễ hơn. Kiểu dữ liệu cần phục vụ cả độ chính xác và câu hỏi phân tích.

## 10. Ví dụ xuyên suốt: miền giá trị của đơn hàng

Giả sử hệ thống bán hàng cần lưu đơn hàng, dòng hàng, thanh toán và giao nhận.

### 10.1. Định nghĩa miền cho các thuộc tính

| Thuộc tính | Ý nghĩa | Miền giá trị đề xuất | Kiểu khái niệm |
|---|---|---|---|
| order_id | Định danh đơn hàng | Không rỗng, duy nhất trong hệ thống | Identifier |
| order_date | Ngày đơn được tạo theo lịch nghiệp vụ | Ngày hợp lệ | Date |
| created_at | Thời điểm hệ thống ghi nhận | Thời điểm tuyệt đối | Timestamp |
| status | Trạng thái đơn hàng | Tập mã được quản lý | Reference/enum |
| quantity | Số sản phẩm trong dòng hàng | Số nguyên lớn hơn 0 | Integer |
| unit_price | Đơn giá đã chốt | Không âm, precision/scale theo chính sách | Decimal |
| currency_code | Loại tiền tệ | Mã thuộc danh mục hợp lệ | Code |
| discount_rate | Tỷ lệ chiết khấu | Từ 0 đến 1 nếu dùng quy ước tỷ lệ | Decimal |
| tracking_code | Mã vận đơn | Chuỗi theo quy tắc của nhà vận chuyển | String |
| delivered_at | Thời điểm giao thành công | Có giá trị khi trạng thái giao là delivered | Timestamp tùy chọn |

### 10.2. Đưa quy tắc vào lược đồ

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE orders (
    order_id       UUID PRIMARY KEY,
    order_date     DATE NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL,
    status_code    VARCHAR(20) NOT NULL,
    currency_code  VARCHAR(3) NOT NULL,
    total_amount   NUMERIC(14, 2) NOT NULL
                   CHECK (total_amount >= 0),
    delivered_at   TIMESTAMPTZ NULL,
    CHECK (
        status_code <> 'delivered'
        OR delivered_at IS NOT NULL
    )
);

CREATE TABLE order_items (
    order_item_id UUID PRIMARY KEY,
    order_id      UUID NOT NULL REFERENCES orders(order_id),
    product_id    UUID NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(14, 4) NOT NULL
                  CHECK (unit_price >= 0),
    line_total    NUMERIC(14, 2) NOT NULL
                  CHECK (line_total >= 0)
);
~~~

Ví dụ này thể hiện một số lựa chọn, không phải schema hoàn chỉnh. Trường hợp status_code = delivered cần được ràng buộc với danh mục trạng thái hoặc logic chuyển trạng thái. Cột total_amount có thể cần đối chiếu với tổng dòng hàng, thuế và chiết khấu trong cùng quy trình. Độ chính xác của unit_price và line_total cần được xác nhận theo chính sách giá và làm tròn.

### 10.3. Phát hiện những điểm chưa rõ

Trước khi chốt kiểu và miền, cần hỏi:

- Đơn hàng có thể có giá trị âm do điều chỉnh hoặc hoàn tiền không?
- Một sản phẩm có thể bán theo khối lượng lẻ không?
- Có nhiều loại tiền tệ trong cùng một đơn không?
- Giá được lưu đến bao nhiêu chữ số thập phân?
- Tổng tiền được làm tròn theo từng dòng hay sau khi cộng?
- Thời điểm tạo đơn là thời điểm người dùng gửi yêu cầu hay lúc hệ thống xác nhận?
- Một đơn giao nhiều lần thì delivered_at biểu diễn lần giao đầu, lần cuối hay thời điểm giao đủ?
- Mã vận đơn có thể có nhiều mã cho một đơn không?
- Đơn hàng có thể ở trạng thái delivered nhưng vẫn còn một dòng chưa giao không?

Các câu hỏi này có thể khiến mô hình cần thêm thực thể giao hàng, bảng thanh toán, lịch sử trạng thái hoặc miền số lượng khác. Không nên ép mọi khái niệm vào một thuộc tính chỉ để schema đơn giản.

## 11. Quản lý miền khi dữ liệu thay đổi theo thời gian

### 11.1. Danh mục có thể mở rộng

Một danh sách trạng thái hoặc loại sản phẩm có thể thay đổi theo thời gian. Nếu tập giá trị được mã hóa cứng trong nhiều ứng dụng, thêm một giá trị mới có thể yêu cầu phát hành đồng loạt.

Cần quyết định:
- Danh mục do ai quản lý?
- Thêm mã mới có cần phê duyệt không?
- Mã cũ có được xóa hay chỉ ngừng sử dụng?
- Consumer cũ phải xử lý mã chưa biết như thế nào?
- Nhãn hiển thị có thay đổi hoặc dịch sang ngôn ngữ khác không?

Một consumer nên có cách xử lý giá trị mới theo hợp đồng, thay vì giả định danh mục sẽ không bao giờ thay đổi.

### 11.2. Miền có hiệu lực theo thời gian

Một giá trị có thể hợp lệ trong một khoảng thời gian. Ví dụ, mức thuế, bảng giá hoặc giới hạn tín dụng thay đổi theo ngày hiệu lực.

Cần lưu:
- Giá trị hoặc phiên bản.
- Thời điểm bắt đầu có hiệu lực.
- Thời điểm kết thúc, nếu có.
- Thời điểm hệ thống ghi nhận.
- Nguồn và người phê duyệt khi cần.

Không nên ghi đè một giá trị cũ nếu nghiệp vụ cần tái dựng giao dịch đã dùng quy tắc nào tại thời điểm phát sinh.

### 11.3. Thay đổi quy tắc miền

Nếu giới hạn số lượng tối đa thay đổi từ 100 lên 500, cần biết quy tắc mới áp dụng cho bản ghi cũ hay chỉ bản ghi tạo sau thời điểm thay đổi. Nếu thay đổi đơn vị hoặc precision, cần kế hoạch chuyển đổi và kiểm tra dữ liệu hiện có.

Một thay đổi miền có thể yêu cầu:
1. Xác định dữ liệu hiện tại có nằm trong miền mới không.
2. Xác định cách xử lý giá trị không còn hợp lệ.
3. Cập nhật constraint và schema.
4. Cập nhật producer/consumer.
5. Kiểm tra dữ liệu lịch sử.
6. Ghi nhận phiên bản quy tắc hoặc thời điểm hiệu lực nếu cần.

## 12. Lỗi thường gặp khi lựa chọn kiểu

- **Chọn kiểu theo hình dạng dữ liệu:** thấy toàn chữ số thì dùng INTEGER, dù giá trị là mã.
- **Dùng FLOAT cho tiền tệ:** có thể gây sai số khi tính toán và đối chiếu.
- **Không ghi đơn vị:** các hệ thống hiểu khác nhau về kg, gram, mét hoặc phần trăm.
- **Dùng timestamp cho ngày lịch:** phát sinh lệch ngày khi quy đổi múi giờ.
- **Lưu thời gian địa phương mà thiếu múi giờ:** không thể xác định chính xác thời điểm khi quy tắc múi giờ thay đổi.
- **Dùng BOOLEAN cho quy trình nhiều trạng thái:** mất thông tin về chờ, thất bại, chưa biết hoặc không áp dụng.
- **Dùng VARCHAR cho mọi dữ liệu:** mất khả năng kiểm tra kiểu, tính toán và ràng buộc ở tầng lưu trữ.
- **Đặt độ dài tùy tiện:** dữ liệu hợp lệ bị cắt hoặc phải migration sớm.
- **Để NULL mang nhiều ý nghĩa:** consumer không biết dữ liệu chưa nhập, không áp dụng hay chưa xác minh.
- **Dùng DEFAULT để che thiếu dữ liệu:** tạo ra giá trị có vẻ hợp lệ nhưng sai nghiệp vụ.
- **Chỉ kiểm tra ở giao diện:** dữ liệu ghi từ API, import hoặc tác vụ nền có thể vượt miền.
- **Dùng enum cứng cho danh mục thay đổi thường xuyên:** việc thêm giá trị trở nên khó triển khai.
- **Lưu JSON không có schema:** cùng một trường có thể mang kiểu và ý nghĩa khác nhau giữa các bản ghi.
- **Không tính đến tăng trưởng:** kiểu số hoặc độ dài mã không đủ cho vòng đời hệ thống.
- **Không kiểm tra chuyển đổi giữa hệ thống:** mất số 0 đầu, sai precision hoặc đổi múi giờ ngoài ý muốn.

## 13. Tiêu chí kiểm chứng miền giá trị

Một miền giá trị tốt cần có ví dụ hợp lệ, ví dụ không hợp lệ và hành vi hệ thống mong đợi.

**Kiểm tra số lượng**

- Given: một dòng hàng yêu cầu số lượng là số nguyên dương.
- When: người dùng nhập 0, -1 hoặc 1.5.
- Then: hệ thống từ chối và thông báo quy tắc phù hợp.

**Kiểm tra tiền tệ**

- Given: đơn hàng dùng một loại tiền tệ và precision đã quy định.
- When: hệ thống tính chiết khấu, thuế và tổng tiền.
- Then: phép tính tuân theo quy tắc làm tròn và có thể đối chiếu lại.

**Kiểm tra định danh dạng số**

- Given: mã bưu chính có số 0 ở đầu.
- When: dữ liệu được nhập, lưu và xuất.
- Then: mã vẫn giữ nguyên định dạng, không bị chuyển thành số.

**Kiểm tra ngày và thời điểm**

- Given: khách hàng có ngày sinh và một giao dịch thanh toán.
- When: dữ liệu được lưu và hiển thị ở múi giờ khác.
- Then: ngày sinh không bị đổi ngày; thời điểm giao dịch vẫn đại diện đúng một thời điểm.

**Kiểm tra miền trạng thái**

- Given: đơn hàng có danh mục trạng thái được quản lý.
- When: producer phát một trạng thái mới mà consumer chưa nhận diện.
- Then: consumer xử lý theo chính sách giá trị chưa biết, ghi nhận lỗi hoặc đưa vào luồng xử lý phù hợp, không âm thầm diễn giải sai.

**Kiểm tra NULL**

- Given: trường ngày xác minh có thể chưa có giá trị trước khi bắt đầu quy trình.
- When: bản ghi chưa xác minh được lưu.
- Then: hệ thống phân biệt được trạng thái chưa bắt đầu với trạng thái xác minh thất bại hoặc không áp dụng.

**Kiểm tra giới hạn tăng trưởng**

- Given: số lượng bản ghi tăng theo dự báo vòng đời.
- When: giá trị tiến gần giới hạn kiểu dữ liệu.
- Then: hệ thống vẫn lưu được dữ liệu hợp lệ hoặc có kế hoạch chuyển đổi trước khi chạm giới hạn.

## 14. Danh sách kiểm tra trước khi chốt kiểu dữ liệu

- [ ] Đã viết định nghĩa nghiệp vụ cho từng thuộc tính quan trọng.
- [ ] Đã xác định miền hợp lệ, giá trị biên và các trường hợp ngoại lệ.
- [ ] Đã xác định đơn vị và quy ước biểu diễn.
- [ ] Đã chọn kiểu phù hợp với phép toán và ý nghĩa dữ liệu.
- [ ] Đã xác định precision, scale và quy tắc làm tròn cho số thập phân.
- [ ] Đã xác định giới hạn tăng trưởng và phạm vi của kiểu số.
- [ ] Đã phân biệt mã định danh với đại lượng số học.
- [ ] Đã phân biệt ngày lịch, thời điểm tuyệt đối, giờ địa phương và khoảng thời lượng.
- [ ] Đã xác định múi giờ và độ chính xác thời gian khi cần.
- [ ] Đã làm rõ NULL, chuỗi rỗng, giá trị mặc định và trạng thái chưa biết.
- [ ] Đã xác định danh mục mã, chủ sở hữu và cách mở rộng miền.
- [ ] Đã đặt ràng buộc phù hợp ở cơ sở dữ liệu và ứng dụng.
- [ ] Đã kiểm tra chuyển đổi giữa các hệ thống và consumer.
- [ ] Đã có ví dụ hợp lệ, không hợp lệ và tiêu chí chấp nhận.
- [ ] Đã xem xét thay đổi miền theo thời gian và dữ liệu lịch sử.

Kết quả của bước này là định nghĩa miền giá trị cho các thuộc tính, kèm kiểu khái niệm, đơn vị, phạm vi, độ chính xác, tính bắt buộc và quy tắc kiểm tra. Từ đó, nhóm thiết kế có thể chọn kiểu vật lý và ràng buộc phù hợp với ý nghĩa nghiệp vụ, đồng thời bảo đảm dữ liệu được hiểu nhất quán ở mọi hệ thống sử dụng.


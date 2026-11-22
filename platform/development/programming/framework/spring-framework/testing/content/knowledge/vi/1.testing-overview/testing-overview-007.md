# Từ yêu cầu hành vi đến tình huống thành công và thất bại

Kiểm thử Spring Framework có giá trị khi mỗi bài kiểm thử chứng minh được một hành vi mà người dùng, hệ thống tích hợp hoặc thành phần khác có thể quan sát. Để làm được điều đó, người viết kiểm thử cần bắt đầu từ yêu cầu hành vi, xác định trạng thái ban đầu và dữ liệu đầu vào, rồi mô tả cả kết quả mong đợi lẫn những điều hệ thống phải từ chối hoặc giữ nguyên khi có lỗi.

Các annotation như **@SpringBootTest**, **@WebMvcTest** hay **@DataJpaTest** chỉ giúp chọn môi trường chạy kiểm thử. Chúng không tự tạo ra một bộ tình huống tốt. Một lớp kiểm thử có thể khởi động đầy đủ Spring context nhưng vẫn bỏ sót trường hợp quan trọng nếu yêu cầu chưa được chuyển thành các tình huống cụ thể. Ngược lại, một kiểm thử đơn vị nhỏ có thể chứng minh chính xác một quy tắc nghiệp vụ mà không cần khởi động Spring.

Quy trình trong bài học này gồm năm việc: đọc yêu cầu và xác định hành vi quan sát được; làm rõ tiền điều kiện, dữ liệu, quy tắc và kết quả; chia yêu cầu thành tình huống thành công, thay thế và thất bại; chọn tầng kiểm thử Spring phù hợp; viết assertion chứng minh cả kết quả đúng lẫn những tác động không được phép xảy ra.

## 1. Bắt đầu từ hành vi, không bắt đầu từ annotation

Một yêu cầu hành vi mô tả hệ thống cần phản ứng thế nào trước một tác nhân hoặc một sự kiện. Ví dụ:

> Khi khách hàng gửi yêu cầu tạo đơn hàng hợp lệ và sản phẩm còn đủ hàng, hệ thống tạo đơn hàng và trừ số lượng tồn kho tương ứng.

Câu này mô tả một luồng thành công, nhưng chưa đủ để xây dựng bộ kiểm thử. Ta vẫn cần biết thế nào là hợp lệ, tồn kho được kiểm tra ở thời điểm nào, kết quả trả về có thông tin gì, và hệ thống phải giữ trạng thái ra sao nếu không thể tạo đơn.

Một yêu cầu có thể được phân tích theo những thành phần sau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Tác nhân | Ai hoặc thành phần nào kích hoạt hành vi? | Khách hàng đã đăng nhập |
| Điểm kích hoạt | Hành động nào bắt đầu xử lý? | Gửi POST tạo đơn hàng |
| Tiền điều kiện | Trạng thái nào phải tồn tại trước đó? | Sản phẩm tồn tại và đang được bán |
| Đầu vào | Dữ liệu nào được gửi vào? | Mã sản phẩm, số lượng |
| Quy tắc | Điều kiện nào quyết định kết quả? | Số lượng từ 1 đến 10 và không vượt tồn kho |
| Kết quả thành công | Người gọi quan sát được điều gì? | Nhận phản hồi tạo đơn thành công |
| Thay đổi trạng thái | Dữ liệu nào được tạo, cập nhật hoặc xóa? | Tạo đơn và giảm tồn kho |
| Kết quả thất bại | Hệ thống phản hồi thế nào khi điều kiện không thỏa? | Từ chối yêu cầu với lỗi phù hợp |
| Tác động bị cấm | Điều gì tuyệt đối không được xảy ra? | Không tạo đơn dở dang, không trừ tồn kho khi bị từ chối |

Hai nhóm thông tin cuối rất quan trọng. Một kiểm thử chỉ xác nhận API trả về lỗi có thể vẫn bỏ sót lỗi nghiêm trọng nếu hệ thống đã ghi một phần dữ liệu trước khi trả lỗi. Với thao tác thay đổi trạng thái, cần kiểm tra cả điều đã xảy ra và điều không được xảy ra.

### 1.1. Viết lại yêu cầu thành phát biểu có thể kiểm chứng

Một phát biểu hành vi hữu ích thường có dạng:

**Khi** một tác nhân thực hiện hành động với dữ liệu và trạng thái ban đầu xác định, **thì** hệ thống tạo ra kết quả quan sát được và thực hiện những thay đổi trạng thái đã cam kết; nếu điều kiện không thỏa, hệ thống trả về kết quả từ chối phù hợp và không để lại tác động ngoài ý muốn.

Điều quan trọng là người viết kiểm thử có thể chỉ ra:

- Dữ liệu hoặc trạng thái nào làm cho tình huống khác với tình huống khác.
- Hành động nào được thực hiện.
- Kết quả nào có thể quan sát từ bên ngoài.
- Trạng thái nào phải thay đổi hoặc phải được giữ nguyên.
- Quy tắc nào quyết định tình huống được chấp nhận hay bị từ chối.

Nếu một từ trong yêu cầu có thể được hiểu theo nhiều cách, chẳng hạn “nhanh”, “hợp lệ”, “đủ quyền”, “không trùng lặp” hoặc “thử lại an toàn”, hãy ghi nhận điểm chưa rõ để người sở hữu yêu cầu xác nhận. Không tự chọn một cách hiểu rồi biến nó thành tiêu chí kiểm thử chính thức.

### 1.2. Phân biệt hành vi với cách triển khai

Yêu cầu thường nói hệ thống phải làm gì, còn mã nguồn quyết định hệ thống làm việc đó bằng cách nào. Kiểm thử hành vi nên ưu tiên hợp đồng quan sát được:

- API trả mã trạng thái và nội dung phản hồi nào.
- Một bản ghi có được tạo hay không.
- Số dư, số lượng hoặc trạng thái nghiệp vụ thay đổi ra sao.
- Sự kiện hoặc lời gọi tích hợp nào được phát ra.
- Người dùng không đủ quyền có bị từ chối hay không.

Không nên biến tên phương thức private, thứ tự gọi các hàm không thuộc hợp đồng, hoặc cấu trúc của một lớp triển khai thành mục tiêu chính của kiểm thử. Khi cấu trúc nội bộ thay đổi nhưng hành vi vẫn đúng, bộ kiểm thử hành vi nên tiếp tục có giá trị.

## 2. Chuyển yêu cầu thành tiêu chí chấp nhận

Tiêu chí chấp nhận là những điều kiện cụ thể để xác định một hành vi đã được đáp ứng. Chúng tạo cầu nối giữa câu mô tả nghiệp vụ và tình huống kiểm thử.

Ví dụ, câu “số lượng đặt hàng phải hợp lệ” còn quá mơ hồ. Cần làm rõ:

- Số lượng có bắt buộc không?
- Số lượng có phải là số nguyên dương không?
- Có giới hạn tối đa cho một đơn hàng không?
- Giới hạn tối đa là quy tắc đầu vào hay phụ thuộc vào tồn kho?
- Khi sai, API trả kết quả nào?
- Dữ liệu đơn hàng và tồn kho có được giữ nguyên không?

Sau khi các quy tắc được xác nhận, có thể viết tiêu chí:

1. Yêu cầu phải có mã sản phẩm và số lượng.
2. Số lượng phải là số nguyên từ 1 đến 10.
3. Sản phẩm phải tồn tại.
4. Tồn kho phải lớn hơn hoặc bằng số lượng được yêu cầu tại thời điểm hệ thống xác nhận đơn.
5. Khi tất cả điều kiện thỏa mãn, hệ thống tạo một đơn hàng và giảm tồn kho đúng bằng số lượng đặt.
6. Khi một điều kiện không thỏa mãn, hệ thống từ chối yêu cầu và không tạo thay đổi nghiệp vụ một phần.

Các tiêu chí trên đủ rõ để tạo những tình huống riêng. Chúng cũng giúp phát hiện điểm cần hỏi thêm, chẳng hạn cách xử lý hai yêu cầu đồng thời cùng mua sản phẩm cuối cùng.

### 2.1. Dùng Given – When – Then

Given – When – Then là cách diễn đạt một tình huống theo ba phần:

- **Given**: trạng thái ban đầu và các điều kiện đã chuẩn bị.
- **When**: hành động được kiểm thử.
- **Then**: kết quả có thể quan sát và trạng thái phải được bảo toàn hoặc thay đổi.

Ví dụ cho tình huống thành công:

**Given**

- Sản phẩm P đang tồn tại.
- Sản phẩm P còn 5 đơn vị.
- Chưa có đơn hàng nào được tạo bởi yêu cầu này.

**When**

- Khách hàng gửi yêu cầu đặt 2 đơn vị sản phẩm P.

**Then**

- Hệ thống trả kết quả tạo đơn thành công theo hợp đồng API.
- Đơn hàng mới chứa đúng sản phẩm P và số lượng 2.
- Tồn kho còn 3 đơn vị.
- Chỉ có một đơn hàng được tạo cho thao tác đó.

Với tình huống thất bại, phần Then phải nói rõ cả lỗi được trả về và trạng thái được giữ nguyên:

**Given**

- Sản phẩm P đang tồn tại nhưng chỉ còn 1 đơn vị.

**When**

- Khách hàng yêu cầu 2 đơn vị sản phẩm P.

**Then**

- Hệ thống từ chối yêu cầu theo hợp đồng lỗi đã thống nhất.
- Không có đơn hàng mới được tạo.
- Tồn kho vẫn là 1.

Given – When – Then không bắt buộc phải được viết thành file Gherkin hoặc chạy bằng một framework BDD. Đây trước hết là cách suy nghĩ và trình bày để người viết, người kiểm thử và người duyệt yêu cầu cùng hiểu một tình huống theo cùng một nghĩa.

### 2.2. Tách tiêu chí quan sát được

Một tiêu chí tốt phải có cách xác minh. Những từ như “đúng”, “hợp lệ”, “thành công” hoặc “an toàn” cần được chuyển thành bằng chứng:

| Cách viết chưa đủ rõ | Cách viết có thể kiểm chứng |
| --- | --- |
| Tạo đơn thành công | Có đúng một đơn mới với mã sản phẩm và số lượng đã gửi |
| Trừ kho chính xác | Tồn kho sau xử lý bằng tồn kho trước xử lý trừ số lượng được chấp nhận |
| Dữ liệu không bị ảnh hưởng khi lỗi | Số bản ghi đơn hàng và số lượng tồn kho giữ nguyên |
| Người không có quyền bị chặn | API trả kết quả từ chối theo hợp đồng bảo mật và không thực hiện thao tác nghiệp vụ |
| Không xử lý trùng | Xác định rõ khóa nhận diện yêu cầu trùng, kết quả phản hồi và số tác động được phép |

Nếu không thể chỉ ra dữ liệu nào chứng minh tiêu chí, có thể tiêu chí vẫn còn mơ hồ hoặc cần thêm khả năng quan sát trong hệ thống.

## 3. Tạo tập tình huống thành công và thất bại

Một yêu cầu thường tạo ra nhiều tình huống. Không nên chỉ viết một kiểm thử cho luồng thuận lợi rồi xem đó là mức bao phủ đầy đủ.

### 3.1. Tình huống thành công chính

Đây là luồng thường gặp nhất khi tất cả tiền điều kiện và quy tắc đều thỏa mãn. Hãy chọn dữ liệu đơn giản, rõ ràng để chứng minh hành vi cốt lõi:

- Sản phẩm tồn tại.
- Số lượng nằm trong giới hạn.
- Tồn kho đủ.
- Người gọi có quyền.
- Hệ thống tạo đơn và cập nhật tồn kho.

Tình huống thành công nên kiểm tra các kết quả quan trọng, không chỉ kiểm tra rằng không có exception. Với thao tác ghi dữ liệu, hãy xác nhận trạng thái sau xử lý.

### 3.2. Tình huống thành công thay thế

Luồng thành công có thể có nhiều dạng đầu vào hoặc trạng thái ban đầu:

- Người dùng đặt số lượng tối thiểu.
- Người dùng đặt đúng số lượng tối đa cho phép.
- Người dùng chọn một phương thức giao hàng khác đã được hỗ trợ.
- Một trường tùy chọn bị bỏ trống và hệ thống áp dụng giá trị mặc định đã được quy định.

Chỉ tạo tình huống riêng khi khác biệt đó có ý nghĩa đối với hợp đồng hoặc quy tắc. Không cần nhân bản kiểm thử cho những dữ liệu khác nhau nhưng cùng một lớp hành vi nếu không làm tăng bằng chứng.

### 3.3. Tình huống dữ liệu không hợp lệ

Đây là các trường hợp đầu vào không đáp ứng định dạng hoặc giới hạn:

- Thiếu trường bắt buộc.
- Giá trị null khi không được phép.
- Chuỗi không thể chuyển thành kiểu dữ liệu yêu cầu.
- Số lượng bằng 0 hoặc âm.
- Giá trị vượt giới hạn đã công bố.
- Mã định danh sai định dạng.

Ở tầng web, các tình huống này thường liên quan đến binding, validation và cách ánh xạ lỗi HTTP. Cần xác nhận cả nội dung lỗi nếu API đã cam kết cấu trúc lỗi ổn định.

### 3.4. Tình huống vi phạm quy tắc nghiệp vụ

Đầu vào có thể đúng cú pháp nhưng vẫn không được nghiệp vụ chấp nhận:

- Sản phẩm không tồn tại.
- Sản phẩm đã ngừng bán.
- Tồn kho không đủ.
- Tài khoản không đủ điều kiện thực hiện hành động.
- Trạng thái hiện tại không cho phép chuyển sang trạng thái tiếp theo.

Không nên gộp những trường hợp này thành một kiểm thử “request thất bại”. Mỗi quy tắc có thể có phản hồi khác nhau và yêu cầu bảo toàn trạng thái khác nhau.

### 3.5. Tình huống biên

Tình huống biên kiểm tra hành vi tại điểm chuyển giữa hai lớp dữ liệu. Nếu số lượng hợp lệ nằm trong khoảng từ 1 đến 10, các giá trị cần chú ý là:

- 0: ngay dưới giới hạn dưới.
- 1: đúng giới hạn dưới.
- 10: đúng giới hạn trên.
- 11: ngay trên giới hạn trên.

Kiểm thử các điểm biên thường phát hiện lỗi dùng nhầm toán tử nhỏ hơn và nhỏ hơn hoặc bằng, lỗi làm tròn, sai đơn vị hoặc sai cách xử lý giá trị rỗng.

Không phải mọi con số đều cần kiểm thử riêng. Hãy xác định biên từ quy tắc đã được xác nhận, sau đó chọn giá trị đại diện ở hai phía của biên.

### 3.6. Tình huống trạng thái và thứ tự hành động

Kết quả của một hành động có thể phụ thuộc vào trạng thái hiện tại:

- Đơn hàng chỉ được hủy khi còn ở trạng thái cho phép hủy.
- Một tài khoản bị khóa không thể đăng nhập thành công.
- Một tài nguyên đã được xử lý không được xử lý lần thứ hai nếu nghiệp vụ cấm việc đó.

Hãy liệt kê các trạng thái hợp lệ, các chuyển đổi được phép và các chuyển đổi bị cấm. Với mỗi chuyển đổi quan trọng, tạo ít nhất một tình huống được chấp nhận và một tình huống bị từ chối.

Nếu yêu cầu có tính đồng thời, cần xác định rõ bất biến phải được bảo vệ. Ví dụ, khi chỉ còn một sản phẩm nhưng có hai yêu cầu mua đồng thời, hệ thống có thể phải đảm bảo tối đa một yêu cầu được chấp nhận. Chỉ thêm kiểm thử đồng thời khi hợp đồng nghiệp vụ yêu cầu hành vi đó; không tự suy diễn chính sách xử lý tranh chấp.

### 3.7. Tình huống phụ thuộc hoặc lỗi kỹ thuật

Một hành vi có thể phụ thuộc cơ sở dữ liệu, dịch vụ ngoài, hàng đợi hoặc hệ thống lưu trữ. Khi yêu cầu có quy định về lỗi phụ thuộc, hãy kiểm thử:

- Dịch vụ phụ thuộc không phản hồi.
- Kết nối bị từ chối hoặc hết thời gian chờ.
- Dữ liệu phụ thuộc không đúng định dạng.
- Giao dịch bị rollback.
- Việc gửi sự kiện thất bại hoặc được thử lại.

Các tình huống này cần làm rõ hệ thống phải trả lỗi, thử lại, lưu trạng thái chờ hay bù trừ như thế nào. Không nên tự đặt ra số lần retry, thời gian timeout hoặc chính sách fallback nếu yêu cầu chưa quy định.

## 4. Kỹ thuật tìm tình huống có hệ thống

Việc tạo tình huống không nên phụ thuộc hoàn toàn vào trí nhớ. Một số kỹ thuật dưới đây giúp tìm ra các trường hợp quan trọng mà vẫn giữ tập kiểm thử có trọng tâm.

### 4.1. Phân vùng tương đương

Chia đầu vào thành các nhóm mà các giá trị trong cùng nhóm được xử lý theo cùng một quy tắc. Sau đó chọn một hoặc vài giá trị đại diện cho mỗi nhóm.

Với số lượng đặt hàng từ 1 đến 10:

| Nhóm | Giá trị đại diện | Kỳ vọng |
| --- | ---: | --- |
| Nhỏ hơn giới hạn dưới | 0 | Bị từ chối |
| Trong miền hợp lệ | 4 | Được chấp nhận nếu đủ tồn kho |
| Lớn hơn giới hạn trên | 11 | Bị từ chối |
| Không có giá trị | null hoặc thiếu trường | Bị từ chối nếu trường bắt buộc |
| Sai kiểu dữ liệu | chuỗi không phải số | Bị từ chối khi binding hoặc validation |

Phân vùng tương đương giúp tránh thử hàng trăm giá trị liên tiếp trong khi nhiều giá trị chỉ đại diện cho cùng một quy tắc.

### 4.2. Phân tích giá trị biên

Sau khi xác định miền hợp lệ, chọn các giá trị ngay dưới, tại và ngay trên mỗi biên. Với miền từ 1 đến 10, bộ giá trị 0, 1, 10 và 11 thường cung cấp bằng chứng tốt hơn việc chỉ thử một giá trị ở giữa.

Với ngày giờ, tiền tệ hoặc kích thước, biên có thể phụ thuộc đơn vị và độ chính xác. Hãy dùng cùng đơn vị mà hợp đồng quy định và tránh so sánh số thực theo cách gây sai số không cần thiết.

### 4.3. Bảng quyết định

Khi kết quả phụ thuộc nhiều điều kiện, bảng quyết định giúp tránh bỏ sót tổ hợp quan trọng.

Ví dụ với thao tác tạo đơn:

| Sản phẩm tồn tại | Số lượng hợp lệ | Đủ tồn kho | Kết quả |
| --- | --- | --- | --- |
| Có | Có | Có | Tạo đơn |
| Không | Có | Không áp dụng | Từ chối vì không tìm thấy sản phẩm |
| Có | Không | Không cần xét | Từ chối vì dữ liệu không hợp lệ |
| Có | Có | Không | Từ chối vì không đủ tồn kho |

Bảng này cho thấy thứ tự kiểm tra có thể ảnh hưởng đến lỗi được trả về khi nhiều điều kiện cùng sai. Nếu thứ tự đó là một phần của hợp đồng, hãy ghi rõ. Nếu không, đừng tạo assertion phụ thuộc vào thứ tự nội bộ không được cam kết.

### 4.4. Bảng chuyển trạng thái

Với quy trình có trạng thái, hãy liệt kê trạng thái ban đầu, hành động, trạng thái đích, điều kiện cho phép chuyển và trạng thái cần giữ nguyên khi hành động bị từ chối.

Ví dụ, nếu đơn hàng chỉ được hủy khi ở trạng thái PENDING, hãy có một tình huống hủy thành công từ PENDING và một tình huống hủy bị từ chối từ trạng thái đã hoàn tất. Các trạng thái thực tế và phản hồi phải lấy từ yêu cầu của hệ thống.

### 4.5. Kết hợp điều kiện có kiểm soát

Khi có nhiều trường đầu vào, không nhất thiết phải kiểm thử mọi tổ hợp. Hãy ưu tiên:

- Mỗi quy tắc được kiểm tra ít nhất một lần.
- Các tổ hợp có thể làm thay đổi kết quả nghiệp vụ được kiểm tra.
- Các điều kiện có quan hệ phụ thuộc được kiểm tra cùng nhau.
- Các trường hợp rủi ro cao như quyền truy cập, tiền, tồn kho và chuyển trạng thái có bằng chứng riêng.

Kỹ thuật pairwise có thể giúp giảm số tổ hợp cấu hình khi nhiều tham số độc lập. Tuy nhiên, nó không thay thế việc kiểm thử các tổ hợp đặc biệt mà nghiệp vụ xác định rõ.

## 5. Ví dụ xuyên suốt: tạo đơn hàng

Giả sử API tạo đơn hàng có hợp đồng minh họa sau:

- Request gồm mã sản phẩm và số lượng.
- Số lượng bắt buộc là số nguyên từ 1 đến 10.
- Sản phẩm phải tồn tại.
- Tồn kho phải đủ tại thời điểm xác nhận.
- Khi thành công, hệ thống tạo một đơn hàng và giảm tồn kho đúng bằng số lượng đã đặt.
- Khi dữ liệu không hợp lệ, sản phẩm không tồn tại hoặc tồn kho không đủ, hệ thống từ chối và không để lại thay đổi nghiệp vụ một phần.

Các mã HTTP trong ví dụ là lựa chọn minh họa cho một API REST. Dự án thực tế phải tuân theo hợp đồng API đã thống nhất, bao gồm cả mã trạng thái và cấu trúc nội dung lỗi.

### 5.1. Ma trận tình huống

| ID | Trạng thái ban đầu và đầu vào | Kết quả mong đợi | Điều cần giữ nguyên |
| --- | --- | --- | --- |
| ORD-01 | Sản phẩm tồn tại, kho có 5, đặt 2 | Tạo đơn thành công | Không tạo thêm đơn ngoài đơn của yêu cầu |
| ORD-02 | Sản phẩm tồn tại, kho có 5, đặt 1 | Tạo đơn thành công ở biên dưới | Tồn kho giảm đúng 1 |
| ORD-03 | Sản phẩm tồn tại, kho có 10, đặt 10 | Tạo đơn thành công ở biên trên | Tồn kho về 0, không âm |
| ORD-04 | Số lượng bằng 0 | Từ chối dữ liệu | Không tạo đơn, không đổi tồn kho |
| ORD-05 | Số lượng bằng 11 | Từ chối dữ liệu | Không tạo đơn, không đổi tồn kho |
| ORD-06 | Thiếu mã sản phẩm hoặc số lượng | Từ chối dữ liệu | Không tạo đơn, không đổi tồn kho |
| ORD-07 | Mã sản phẩm không tồn tại | Từ chối theo quy tắc tìm tài nguyên | Không tạo đơn |
| ORD-08 | Kho có 1, đặt 2 | Từ chối vì không đủ hàng | Không tạo đơn, kho vẫn còn 1 |

Ma trận này là tập khởi đầu, không phải danh sách cố định cho mọi hệ thống. Nếu API có thêm quy tắc về giá, mã giảm giá, giới hạn theo người dùng hoặc trạng thái sản phẩm, mỗi quy tắc cần được bổ sung tình huống tương ứng.

### 5.2. Viết tiêu chí thành công và thất bại cụ thể

Với ORD-01:

- Given: sản phẩm P tồn tại và có 5 đơn vị trong kho.
- When: gửi yêu cầu tạo đơn với sản phẩm P và số lượng 2.
- Then: phản hồi thể hiện đơn đã được tạo; dữ liệu đơn có đúng sản phẩm và số lượng; số đơn tăng đúng một; tồn kho còn 3.

Với ORD-08:

- Given: sản phẩm P tồn tại và chỉ còn 1 đơn vị.
- When: gửi yêu cầu đặt 2 đơn vị.
- Then: phản hồi thể hiện yêu cầu bị từ chối vì không đủ hàng; số đơn không tăng; tồn kho vẫn là 1.

Với ORD-04:

- Given: sản phẩm P tồn tại và có đủ hàng.
- When: gửi số lượng bằng 0.
- Then: phản hồi thể hiện lỗi validation theo hợp đồng; logic tạo đơn không được thực hiện; dữ liệu đơn và tồn kho không thay đổi.

Ba tình huống có thể đi qua những tầng kiểm thử khác nhau. ORD-04 chủ yếu kiểm tra hợp đồng HTTP và validation. ORD-08 cần chứng minh quy tắc nghiệp vụ. ORD-01 cần xác nhận nhiều thành phần cùng phối hợp và dữ liệu được lưu nhất quán.

## 6. Chọn tầng kiểm thử trong Spring

Spring cung cấp nhiều cách dựng môi trường kiểm thử. Hãy chọn tầng nhỏ nhất có thể chứng minh đầy đủ hành vi đang xét. Nếu một yêu cầu liên quan nhiều thành phần, hãy bổ sung kiểm thử tích hợp ở đúng ranh giới đó.

| Tầng kiểm thử | Công cụ Spring thường dùng | Phù hợp để chứng minh |
| --- | --- | --- |
| Unit test | JUnit và Mockito, không khởi động Spring context | Quy tắc nghiệp vụ thuần, phép tính, quyết định của service |
| Web slice | **@WebMvcTest** và MockMvc | Mapping HTTP, binding, validation, response và cấu hình web cần thiết |
| Data slice | **@DataJpaTest** | Mapping entity, truy vấn repository và ràng buộc dữ liệu |
| Application integration | **@SpringBootTest** kết hợp MockMvc hoặc client phù hợp | Sự phối hợp giữa controller, service, repository, cấu hình và các bean thật |
| HTTP integration | **@SpringBootTest(webEnvironment = RANDOM_PORT)** cùng HTTP client | Hành vi qua server đang chạy, serialization và ranh giới mạng thực tế |

### 6.1. Unit test cho quy tắc nghiệp vụ

Nếu quy tắc có thể kiểm tra bằng một đối tượng Java thông thường, hãy ưu tiên unit test. Ví dụ, service quyết định có chấp nhận số lượng đặt hàng hay không có thể được kiểm thử bằng JUnit và mock cho cổng truy cập dữ liệu.

Unit test thường chạy nhanh, không cần nạp ApplicationContext, dễ tạo dữ liệu đầu vào và kiểm tra nhiều nhánh, đồng thời giúp xác định lỗi thuộc quy tắc nào. Không nên mock mọi đối tượng chỉ để có thể gọi một phương thức. Hãy giữ các đối tượng giá trị và logic thuần ở dạng thật; chỉ thay thế những phụ thuộc bên ngoài cần kiểm soát.

### 6.2. Web slice với @WebMvcTest

**@WebMvcTest** tập trung vào phần MVC, thường dùng cùng MockMvc. Tầng này phù hợp để kiểm tra:

- URL và HTTP method được ánh xạ đúng.
- JSON request được binding vào DTO.
- Bean Validation được áp dụng.
- Lỗi validation được chuyển thành response theo hợp đồng.
- Response có status, header và JSON body mong đợi.
- Các cấu hình web cần thiết như security filter hoạt động đúng trong phạm vi slice.

Ví dụ DTO:

~~~java
public record CreateOrderRequest(
    @NotNull Long productId,
    @NotNull @Min(1) @Max(10) Integer quantity
) {}
~~~

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
~~~

Ví dụ kiểm thử validation:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void rejects_zero_quantity_before_calling_service() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId": 10, "quantity": 0}
                    """))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(orderService);
    }
}
~~~

Đây là ví dụ minh họa; package, kiểu response, cấu hình security và cách khai báo mock cần khớp với ứng dụng thực tế. Điểm quan trọng là tình huống xác nhận hai điều: request không hợp lệ bị từ chối và service không nhận một yêu cầu mà validation đã loại bỏ.

Không dùng **@WebMvcTest** để kết luận rằng dữ liệu đã được lưu đúng trong cơ sở dữ liệu. Ở tầng này, service thường được thay bằng test double, vì vậy kiểm thử chỉ chứng minh phần web.

### 6.3. Data slice với @DataJpaTest

**@DataJpaTest** phù hợp để kiểm tra hành vi của persistence layer:

- Entity được ánh xạ đúng.
- Truy vấn repository trả đúng tập dữ liệu.
- Điều kiện lọc và phân trang hoạt động đúng.
- Ràng buộc hoặc quan hệ dữ liệu được áp dụng như mong đợi.

Tầng này không thay thế kiểm thử nghiệp vụ tạo đơn. Một repository query đúng không chứng minh rằng service đã kiểm tra tồn kho trước khi tạo đơn.

Môi trường cơ sở dữ liệu trong test cũng cần được cân nhắc. Cơ sở dữ liệu nhúng có thể khác hệ quản trị đang chạy ở production về kiểu dữ liệu, collation, SQL dialect, khóa hoặc hành vi transaction. Với truy vấn hay ràng buộc phụ thuộc đặc tính của hệ quản trị thật, hãy cân nhắc Testcontainers để chạy đúng loại cơ sở dữ liệu cần kiểm chứng.

### 6.4. Kiểm thử tích hợp với @SpringBootTest

Khi một tình huống cần chứng minh controller, service và repository phối hợp với nhau, hãy dùng **@SpringBootTest**. Có thể kết hợp MockMvc để gửi request qua MVC stack mà không cần mở cổng mạng.

Ví dụ khung kiểm thử:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CreateOrderFlowTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ProductRepository productRepository;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void creates_order_and_decreases_stock_when_stock_is_sufficient()
            throws Exception {
        // Tạo sản phẩm bằng fixture hoặc factory của dự án với tồn kho = 5.
        Product product = productRepository.save(
            ProductFixtures.withStock(5)
        );

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId": %d, "quantity": 2}
                    """.formatted(product.getId())))
            .andExpect(status().isCreated());

        assertThat(orderRepository.count()).isEqualTo(1);
        Product savedProduct = productRepository
            .findById(product.getId())
            .orElseThrow();
        assertThat(savedProduct.getStock()).isEqualTo(3);
    }
}
~~~

**ProductFixtures.withStock** là tên factory minh họa, không phải API có sẵn của Spring. Trong dự án thật, nên dùng builder, factory hoặc test data helper thống nhất để tạo entity hợp lệ.

Kiểm thử tích hợp cần xác nhận các bất biến quan trọng của tình huống. Với tình huống thiếu hàng, hãy chuẩn bị kho có 1, gửi yêu cầu 2, xác nhận phản hồi từ chối, sau đó đọc lại cơ sở dữ liệu để chứng minh không có đơn mới và tồn kho vẫn là 1.

MockMvc chạy request trong môi trường test MVC nhưng không mở một HTTP server thật. Khi cần kiểm tra hành vi qua cổng mạng, cấu hình server ngẫu nhiên bằng **@SpringBootTest(webEnvironment = RANDOM_PORT)** và gửi request bằng client tương ứng.

### 6.5. Kiểm thử ứng dụng reactive

Với ứng dụng WebFlux, các tình huống vẫn được suy ra từ yêu cầu hành vi như trên; điều thay đổi là stack web và công cụ gửi request. **@WebFluxTest** cùng WebTestClient phù hợp với web slice. **@SpringBootTest** kết hợp WebTestClient có thể kiểm tra luồng tích hợp hoặc server thật tùy cấu hình.

Không nên chuyển nguyên một kiểm thử MVC sang reactive chỉ bằng cách thay tên client. Cần xác nhận hành vi bất đồng bộ, xử lý lỗi trong publisher, cancellation và việc hoàn tất luồng nếu những yếu tố đó thuộc hợp đồng của ứng dụng.

## 7. Viết assertion cho cả thành công lẫn thất bại

Một kiểm thử tốt trả lời được câu hỏi: bằng chứng nào cho thấy hành vi đã đúng?

### 7.1. Kiểm tra hợp đồng phản hồi

Với API HTTP, các điểm có thể cần xác nhận gồm HTTP status, Content-Type và header được cam kết, các trường trong JSON body, mã lỗi hoặc cấu trúc lỗi ổn định, giá trị định danh hoặc liên kết tài nguyên được tạo. Không nên kiểm tra toàn bộ JSON nếu nhiều trường không liên quan đến hành vi; hãy tập trung vào những trường mà hợp đồng yêu cầu.

### 7.2. Kiểm tra trạng thái sau xử lý

Khi hành vi có thay đổi dữ liệu, hãy đọc lại trạng thái qua repository hoặc giao diện quan sát phù hợp:

- Bản ghi mới có tồn tại không?
- Có đúng số bản ghi được tạo không?
- Giá trị trước và sau có quan hệ đúng không?
- Trạng thái có chuyển đúng không?
- Dữ liệu liên quan có còn nhất quán không?

Đối với tình huống thất bại, assertion quan trọng thường là trạng thái không đổi. Đây là cách phát hiện thao tác ghi dở dang hoặc transaction không được rollback như mong muốn.

### 7.3. Kiểm tra tác động phụ

Một số hành vi còn phát ra sự kiện, gửi email, gọi dịch vụ ngoài hoặc ghi vào hàng đợi. Nếu những tác động đó thuộc hợp đồng, hãy kiểm tra:

- Tác động có được phát ra khi thành công không?
- Tác động có bị ngăn khi request bị từ chối không?
- Nội dung sự kiện có đúng dữ liệu nghiệp vụ không?
- Một hành động chỉ phát ra số lần được quy định?

Ở unit test, có thể dùng mock để quan sát lời gọi tới cổng tích hợp. Ở kiểm thử tích hợp, ưu tiên một adapter kiểm thử hoặc hàng đợi giả lập phù hợp. Không kiểm tra một lời gọi nội bộ chỉ vì phương thức đó tồn tại; hãy kiểm tra nó khi lời gọi đại diện cho một tác động có ý nghĩa với hợp đồng.

### 7.4. Không dừng ở mã lỗi

Với một request bị từ chối, chỉ kiểm tra 400, 404 hoặc 409 chưa đủ nếu hành vi có ghi dữ liệu. Ví dụ:

- API trả 409 Conflict.
- Nhưng một đơn hàng đã được tạo trước khi kiểm tra tồn kho.
- Tồn kho bị giảm rồi mới phát hiện lỗi.

Nếu chỉ assertion status, kiểm thử vẫn xanh dù dữ liệu đã hỏng. Hãy kiểm tra số bản ghi, số lượng tồn kho hoặc bất biến liên quan sau khi xử lý.

### 7.5. Chọn mã lỗi theo hợp đồng

Một API REST có thể dùng:

- 400 Bad Request cho request sai định dạng hoặc vi phạm validation.
- 401 Unauthorized khi chưa xác thực.
- 403 Forbidden khi đã xác thực nhưng không có quyền.
- 404 Not Found khi tài nguyên được yêu cầu không tồn tại.
- 409 Conflict khi thao tác xung đột với trạng thái nghiệp vụ hiện tại.

Đây là cách ánh xạ thường gặp, không phải quy tắc bắt buộc cho mọi API. Mã trạng thái và body lỗi phải được xác định trong hợp đồng của hệ thống. Kiểm thử nên bảo vệ hợp đồng đó, không tự áp đặt một cách ánh xạ chỉ vì nó phổ biến.

## 8. Dữ liệu kiểm thử và tính độc lập

Tình huống chỉ đáng tin khi trạng thái ban đầu được kiểm soát. Nếu kết quả phụ thuộc dữ liệu còn sót lại từ lần chạy trước, kiểm thử sẽ không ổn định.

### 8.1. Mỗi tình huống tự chuẩn bị tiền điều kiện

Hãy tạo dữ liệu cần thiết trong chính test hoặc fixture mà test gọi tới. Tránh phụ thuộc vào thứ tự chạy, một test khác đã tạo bản ghi, hoặc dữ liệu thủ công trong môi trường phát triển.

Một fixture tốt tạo được trạng thái hợp lệ tối thiểu, cho phép thay đổi rõ ràng các thuộc tính liên quan, không âm thầm tạo quá nhiều dữ liệu không cần thiết và có tên thể hiện ý nghĩa, chẳng hạn sản phẩm còn 1 đơn vị hoặc sản phẩm đang ngừng bán.

### 8.2. Dọn dữ liệu và transaction

Spring Test hỗ trợ transaction cho nhiều kiểu kiểm thử. Với test được đánh dấu **@Transactional**, Spring Test thường rollback transaction của test sau khi phương thức kiểm thử hoàn tất. Điều này giúp cô lập dữ liệu nhưng cần hiểu ranh giới transaction.

Khi dùng MockMvc trong môi trường test không mở server, request được xử lý trong cùng tiến trình và có thể tương tác với transaction của test tùy cấu hình. Với **RANDOM_PORT**, request được xử lý trên server thread và transaction của test ở thread gọi client không tự động bao trùm transaction của request. Vì vậy, không nên giả định rằng thêm **@Transactional** vào test HTTP thật sẽ tự động rollback mọi thay đổi do server tạo ra.

Ngoài ra, rollback có thể che khuất lỗi chỉ xuất hiện khi commit hoặc khi chạy callback sau commit. Với các hành vi phụ thuộc commit, event listener, transaction boundary hoặc nhiều kết nối, cần thiết kế kiểm thử chứng minh đúng ranh giới đó.

### 8.3. Tránh phụ thuộc thời gian và môi trường

Nếu logic phụ thuộc thời gian hiện tại, hãy đưa Clock hoặc một nguồn thời gian có thể kiểm soát vào thành phần cần kiểm thử. Nếu logic dùng số ngẫu nhiên hoặc mã định danh, hãy tạo điểm thay thế phù hợp để kiểm thử có thể xác định kết quả.

Với xử lý bất đồng bộ, hãy chờ một điều kiện có ý nghĩa bằng cơ chế đồng bộ phù hợp. Không dùng Thread.sleep với một khoảng thời gian tùy ý làm bằng chứng rằng công việc đã hoàn tất.

Với dịch vụ ngoài, hãy dùng test double hoặc container riêng theo đúng mục tiêu kiểm thử. Không để một unit test phụ thuộc mạng công cộng, tài khoản thật hoặc dữ liệu dùng chung.

## 9. Tổ chức test suite và đặt tên

Tên kiểm thử nên mô tả hành vi và điều kiện quan trọng. Một quy ước dễ đọc là:

~~~text
<expected_behavior>_when_<condition>
~~~

Ví dụ:

- creates_order_when_stock_is_sufficient
- rejects_order_when_stock_is_insufficient
- rejects_quantity_below_minimum
- keeps_stock_unchanged_when_order_is_rejected

Tên không cần lặp lại mọi chi tiết của Given – When – Then. Phần thân test nên thể hiện rõ ba giai đoạn:

1. Arrange: tạo trạng thái ban đầu và dữ liệu.
2. Act: thực hiện một hành động chính.
3. Assert: kiểm tra kết quả và trạng thái sau xử lý.

Nếu có nhiều giá trị cùng một quy tắc, JUnit Parameterized Tests có thể giúp biểu diễn dữ liệu đầu vào và kỳ vọng trong một nơi. Mỗi dòng dữ liệu nên có tên hoặc thông tin hiển thị đủ rõ để khi thất bại có thể biết trường hợp nào gây lỗi.

Không nên gộp nhiều hành động nghiệp vụ không liên quan vào một test lớn. Khi test thất bại, người đọc cần xác định được hành vi nào bị sai mà không phải lần theo một kịch bản dài.

## 10. Những sai lầm thường gặp

### Chỉ kiểm tra luồng thành công

Một luồng thành công không chứng minh hệ thống xử lý dữ liệu sai, thiếu quyền, tài nguyên không tồn tại hoặc xung đột trạng thái đúng cách. Hãy tạo tình huống từ từng quy tắc và từng điều kiện từ chối.

### Chỉ kiểm tra status hoặc exception

Status đúng không chứng minh dữ liệu đúng. Exception đúng không chứng minh transaction đã rollback. Với hành vi có tác động, hãy kiểm tra trạng thái và side effect.

### Dùng @SpringBootTest cho mọi thứ

Khởi động toàn bộ ứng dụng cho một phép tính nhỏ làm test chậm và khó cô lập. Hãy dùng unit test hoặc slice test khi chúng đã đủ chứng minh hành vi.

### Mock quá sâu

Nếu mọi repository, mapper và service đều bị mock, kiểm thử có thể chỉ xác nhận rằng các mock được gọi theo đúng thứ tự. Hãy giữ các thành phần cần chứng minh ở dạng thật và chỉ thay thế phụ thuộc nằm ngoài phạm vi.

### Kiểm tra chi tiết triển khai không thuộc hợp đồng

Một refactor có thể đổi thứ tự gọi phương thức nhưng giữ nguyên kết quả. Assertion quá chặt vào chi tiết nội bộ sẽ khiến test báo lỗi dù hành vi vẫn đúng. Chỉ kiểm tra tương tác khi nó biểu thị một tác động nghiệp vụ hoặc ranh giới tích hợp có ý nghĩa.

### Dữ liệu kiểm thử dùng chung

Test phụ thuộc dữ liệu do test khác tạo ra thường thất bại khi chạy riêng hoặc chạy song song. Mỗi tình huống cần tự chuẩn bị trạng thái của nó và dọn dẹp theo đúng ranh giới dữ liệu.

### Tự suy diễn quy tắc còn thiếu

Nếu yêu cầu chưa nói rõ cách xử lý retry, timeout, xung đột đồng thời hoặc mã lỗi, hãy ghi lại câu hỏi. Việc tự chọn một hành vi có thể khiến test khóa chặt một quyết định nghiệp vụ chưa được duyệt.

## 11. Quy trình thực hành từ yêu cầu đến test

**Bước 1 – Gạch chân động từ hành vi.** Xác định hệ thống phải tạo, cập nhật, xóa, trả về, từ chối, phát sự kiện hay chuyển trạng thái điều gì.

**Bước 2 – Ghi tiền điều kiện và đầu vào.** Nêu rõ tác nhân, quyền, trạng thái ban đầu, dữ liệu bắt buộc, dữ liệu tùy chọn và các phụ thuộc.

**Bước 3 – Tách quy tắc thành các điều kiện.** Mỗi điều kiện phải có cách xác minh và kết quả khi thỏa hoặc không thỏa.

**Bước 4 – Tạo tình huống.** Bao gồm luồng thành công chính, các trường hợp biên, dữ liệu không hợp lệ, vi phạm nghiệp vụ và lỗi phụ thuộc đã được yêu cầu.

**Bước 5 – Ghi kết quả và bất biến.** Với mỗi tình huống, mô tả response, thay đổi trạng thái và tác động phụ. Với thất bại, nêu rõ những dữ liệu nào phải giữ nguyên.

**Bước 6 – Chọn tầng kiểm thử.** Dùng unit test cho quy tắc thuần, web slice cho hợp đồng MVC, data slice cho persistence và integration test khi cần chứng minh sự phối hợp giữa nhiều thành phần.

**Bước 7 – Viết assertion theo hợp đồng.** Kiểm tra những điều người gọi có thể quan sát và những bất biến mà hệ thống cam kết.

**Bước 8 – Kiểm tra tính độc lập.** Chạy test riêng lẻ và trong suite; đảm bảo không phụ thuộc thứ tự, dữ liệu dùng chung hoặc thời gian thực.

**Bước 9 – Đối chiếu lại yêu cầu.** Mỗi tiêu chí quan trọng phải có ít nhất một tình huống chứng minh. Mỗi tình huống phải truy ngược được về một quy tắc hoặc rủi ro đã xác định.

## 12. Mẫu mô tả tình huống để sử dụng lại

Trước khi viết mã kiểm thử, có thể ghi mỗi tình huống theo mẫu:

~~~text
ID:
Tên hành vi:
Yêu cầu / tiêu chí liên quan:

Given:
- Trạng thái ban đầu:
- Tác nhân và quyền:
- Dữ liệu đầu vào:
- Phụ thuộc cần chuẩn bị:

When:
- Hành động duy nhất đang kiểm thử:

Then:
- Kết quả quan sát được:
- Trạng thái phải thay đổi:
- Trạng thái phải giữ nguyên:
- Tác động phụ được phép / bị cấm:

Tầng kiểm thử đề xuất:
Bằng chứng / assertion:
Ghi chú hoặc câu hỏi còn mở:
~~~

Mẫu này giúp phát hiện tình huống còn thiếu trước khi viết test code. Nếu không thể điền phần Then một cách cụ thể, tiêu chí chấp nhận có thể chưa đủ rõ. Nếu không thể xác định tầng kiểm thử, hãy xem lại ranh giới hành vi: đó là logic thuần, hợp đồng web, persistence hay sự phối hợp của cả ứng dụng?

## 13. Đánh giá mức bao phủ theo yêu cầu

Không nên đo chất lượng bộ kiểm thử chỉ bằng số lượng test hoặc phần trăm dòng code được chạy. Với một yêu cầu hành vi, hãy xem xét:

- Mỗi tiêu chí chấp nhận quan trọng có tình huống tương ứng chưa?
- Có tình huống thành công và tình huống từ chối cho từng quy tắc quan trọng chưa?
- Các giá trị biên có được kiểm tra không?
- Những lỗi có nguy cơ để lại dữ liệu dở dang có assertion bảo toàn trạng thái không?
- Các tác động tích hợp có được kiểm tra tại đúng ranh giới không?
- Tình huống có độc lập và lặp lại ổn định không?
- Assertion có kiểm tra hợp đồng hay đang khóa vào chi tiết triển khai?

Coverage của mã nguồn vẫn hữu ích để tìm nhánh chưa được thực thi, nhưng nó không thay thế việc đối chiếu với yêu cầu. Một nhánh có thể đã chạy mà kết quả chưa được assertion; một yêu cầu quan trọng có thể chưa được mô hình hóa dù coverage tổng thể cao.

## Kết luận

Một bộ kiểm thử Spring Framework đáng tin bắt đầu từ việc hiểu hành vi mà hệ thống cam kết. Khi yêu cầu được tách thành tiền điều kiện, đầu vào, quy tắc, kết quả và bất biến, người viết có thể tạo ra cả tình huống thành công lẫn thất bại một cách có hệ thống. Sau đó, các công cụ của Spring như **@WebMvcTest**, **@DataJpaTest** và **@SpringBootTest** được chọn theo ranh giới cần chứng minh.

Hãy luôn kiểm tra điều hệ thống phải làm khi thành công và điều hệ thống tuyệt đối không được làm khi thất bại. Chính phần bằng chứng về trạng thái và tác động phụ giúp phát hiện những lỗi mà một assertion đơn giản về HTTP status hoặc exception không thể nhìn thấy.

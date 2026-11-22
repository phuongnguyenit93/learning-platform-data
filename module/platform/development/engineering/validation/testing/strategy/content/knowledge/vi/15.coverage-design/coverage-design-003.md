# Chọn phân vùng tương đương và giá trị biên theo loại dữ liệu

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), thiết kế bao phủ cần chọn các trường hợp kiểm thử đủ đại diện để phát hiện lỗi mà không tạo ra quá nhiều ca trùng lặp. Hai kỹ thuật nền tảng là **phân vùng tương đương (equivalence partitioning)** và **phân tích giá trị biên (boundary value analysis)**. Phân vùng tương đương chia miền đầu vào thành các nhóm được kỳ vọng có hành vi giống nhau; phân tích giá trị biên tập trung vào những điểm gần nơi hành vi chuyển từ hợp lệ sang không hợp lệ hoặc từ một kết quả nghiệp vụ sang kết quả khác.

Cách chọn dữ liệu phải phù hợp với kiểu dữ liệu và quy tắc nghiệp vụ. Giá trị biên của một số nguyên khác với giá trị biên của ngày giờ, chuỗi Unicode, danh sách hoặc tệp tải lên. Nếu chỉ chọn một giá trị bất kỳ trong mỗi nhóm, nhóm có thể bỏ lỡ lỗi tại điểm chuyển tiếp; nếu chỉ thử min, max mà không hiểu quy tắc, nhóm có thể tạo nhiều ca nhưng vẫn bỏ sót hành vi quan trọng.

Bài học này hướng dẫn cách xác định phân vùng, tìm ranh giới theo từng loại dữ liệu, kết hợp các kỹ thuật một cách có chủ đích và ghi lại cơ sở lựa chọn để bộ kiểm thử có thể bảo trì.

## 1. Hai kỹ thuật và mối quan hệ giữa chúng

### 1.1. Phân vùng tương đương

Phân vùng tương đương chia miền đầu vào thành các lớp sao cho các giá trị trong cùng một lớp được kỳ vọng sẽ được xử lý theo cùng một quy tắc. Thay vì kiểm tra mọi giá trị, nhóm chọn một hoặc một số đại diện từ mỗi lớp.

Ví dụ, hệ thống cho phép tuổi từ 18 đến 65, bao gồm cả hai đầu mút. Có thể chia miền thành ba phân vùng:

- Hợp lệ: từ 18 đến 65.
- Không hợp lệ thấp hơn: nhỏ hơn 18.
- Không hợp lệ cao hơn: lớn hơn 65.

Có thể chọn 30 làm đại diện cho phân vùng hợp lệ, 17 cho phân vùng thấp hơn và 66 cho phân vùng cao hơn. Tuy nhiên, các giá trị sát ranh giới như 17, 18, 19, 64, 65 và 66 cần được xem xét riêng bằng phân tích giá trị biên.

Một phân vùng tốt cần có cùng kỳ vọng về kết quả. Nếu hai nhóm giá trị có quy tắc xử lý khác nhau, chúng không nên bị gộp chỉ vì cùng kiểu dữ liệu.

### 1.2. Phân vùng hợp lệ và không hợp lệ

Với mỗi đầu vào, hãy xác định cả phân vùng hợp lệ lẫn không hợp lệ.

Ví dụ trường **quantity** phải là số nguyên từ 1 đến 99:

| Phân vùng | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Hợp lệ | Số nguyên từ 1 đến 99 | Được chấp nhận. |
| Không hợp lệ | Nhỏ hơn 1 | Bị từ chối theo quy tắc số lượng. |
| Không hợp lệ | Lớn hơn 99 | Bị từ chối theo giới hạn. |
| Không hợp lệ | Số thập phân | Bị từ chối nếu hợp đồng yêu cầu số nguyên. |
| Không hợp lệ | Chuỗi, boolean hoặc kiểu không chuyển đổi được | Bị từ chối với lỗi dữ liệu phù hợp. |
| Không hợp lệ hoặc trường hợp riêng | Thiếu, null hoặc chuỗi rỗng | Xử lý theo quy tắc bắt buộc/tùy chọn đã định nghĩa. |

Không nên coi “không phải số” là một phân vùng duy nhất nếu hệ thống có thể xử lý riêng chuỗi, boolean, null và trường bị thiếu. Hãy chia nhỏ khi chúng có thể đi qua các nhánh validation khác nhau hoặc có hậu quả khác nhau.

### 1.3. Phân tích giá trị biên

Giá trị biên là giá trị nằm tại hoặc sát điểm mà hành vi được kỳ vọng thay đổi. Lỗi thường tập trung quanh các điểm này do điều kiện so sánh sai, làm tròn, chuyển kiểu, lệch chỉ số hoặc quy tắc bao gồm/loại trừ đầu mút.

Với một miền số nguyên từ 1 đến 99, các giá trị đáng xem xét là:

- 0: ngay dưới biên dưới.
- 1: biên dưới hợp lệ.
- 2: ngay trên biên dưới.
- 98: ngay dưới biên trên.
- 99: biên trên hợp lệ.
- 100: ngay trên biên trên.

Với miền liên tục hoặc dữ liệu có độ chính xác khác nhau, “ngay dưới” và “ngay trên” cần được xác định theo độ phân giải được hỗ trợ, chẳng hạn một cent, một millisecond hoặc một đơn vị nhỏ nhất của miền dữ liệu.

### 1.4. Phân vùng và giá trị biên bổ sung cho nhau

| Kỹ thuật | Tập trung vào | Câu hỏi chính |
|---|---|---|
| Phân vùng tương đương | Các nhóm đầu vào có hành vi dự kiến giống nhau. | Những loại dữ liệu hoặc trạng thái nào cần ít nhất một đại diện? |
| Giá trị biên | Điểm chuyển tiếp giữa các phân vùng hoặc quy tắc. | Điều gì xảy ra ngay trước, tại và ngay sau ranh giới? |

Phân vùng giúp bao phủ các nhóm hành vi khác nhau. Giá trị biên giúp kiểm tra điểm dễ sai trong từng nhóm. Khi kết hợp, nhóm có thể giảm số ca so với kiểm tra mọi giá trị nhưng vẫn tập trung vào những nơi lỗi có khả năng xuất hiện.

## 2. Quy trình xác định phân vùng và ranh giới

Có thể áp dụng quy trình sau cho từng trường dữ liệu hoặc tham số.

### Bước 1: Đọc quy tắc và xác định miền dữ liệu

Tìm nguồn quy định như yêu cầu, tiêu chí chấp nhận, hợp đồng API, schema, quy tắc nghiệp vụ hoặc giới hạn kỹ thuật. Ghi rõ:

- Kiểu dữ liệu và định dạng.
- Giá trị tối thiểu/tối đa.
- Đầu mút có được bao gồm không.
- Độ chính xác hoặc độ phân giải.
- Trường bắt buộc hay tùy chọn.
- Quan hệ với trường khác hoặc trạng thái hiện tại.
- Quy tắc chuẩn hóa, chuyển đổi và thông báo lỗi.

Nếu yêu cầu chỉ ghi “số lượng hợp lệ” mà không định nghĩa miền, cần làm rõ trước khi có thể thiết kế kiểm thử đáng tin cậy.

### Bước 2: Chia các phân vùng theo hành vi

Liệt kê các nhóm đầu vào có cùng kết quả dự kiến. Tách riêng khi có khác biệt về validation, quyền, trạng thái hoặc tác dụng phụ.

Ví dụ trường email có thể có các nhóm: địa chỉ hợp lệ chưa đăng ký, địa chỉ hợp lệ đã tồn tại, thiếu trường, chuỗi sai cấu trúc, có khoảng trắng cần chuẩn hóa và giá trị vượt giới hạn độ dài.

### Bước 3: Xác định ranh giới của từng phân vùng

Tìm các điểm mà quy tắc thay đổi: min/max, thời điểm hết hạn, độ dài tối đa, số phần tử tối đa, kích thước file, số chữ số thập phân, ngưỡng phí hoặc trạng thái chuyển tiếp.

### Bước 4: Chọn giá trị đại diện và giá trị sát biên

Với mỗi phân vùng, chọn ít nhất một đại diện phù hợp. Với mỗi ranh giới quan trọng, xem xét giá trị ngay dưới, tại và ngay trên biên. Chọn số ca dựa trên độ rủi ro và khả năng thay đổi hành vi.

### Bước 5: Xác định kết quả mong đợi rõ ràng

Mỗi ca cần nêu dữ liệu đầu vào, điều kiện ban đầu, kết quả mong đợi và tác dụng phụ được phép hoặc không được phép. “Request thất bại” có thể chưa đủ; cần biết mã lỗi, thông báo, dữ liệu có thay đổi hay không và có phát sinh giao dịch hay không.

### Bước 6: Xem xét tương tác giữa các trường

Một trường có thể hợp lệ riêng lẻ nhưng không hợp lệ khi kết hợp với trường khác. Ví dụ ngày bắt đầu và ngày kết thúc đều hợp lệ, nhưng ngày kết thúc lại trước ngày bắt đầu. Hãy bổ sung phân vùng cho các quan hệ liên trường có ý nghĩa.

### Bước 7: Ghi lý do và liên kết với yêu cầu

Ghi vì sao một giá trị được chọn, phân vùng nào được đại diện và rủi ro nào được kiểm tra. Điều này giúp nhóm cập nhật bộ test khi giới hạn hoặc quy tắc thay đổi.

## 3. Chọn phân vùng và giá trị biên cho số nguyên và số thực

### 3.1. Số nguyên có giới hạn

Với miền số nguyên có min và max, hãy xác định đầu mút bao gồm hay không. Nếu quy tắc là \(1 \leq x \leq 99\), bộ giá trị biên thường gồm 0, 1, 2, 98, 99 và 100.

Nếu miền là \(1 < x < 99\), thì 1 và 99 là không hợp lệ; giá trị hợp lệ sát biên sẽ là 2 và 98. Không nên mặc định các đầu mút luôn hợp lệ.

Ví dụ kiểm tra số lượng sản phẩm:

| Giá trị | Phân vùng | Kỳ vọng |
|---:|---|---|
| -1 | Dưới miền | Từ chối. |
| 0 | Dưới biên thấp | Từ chối. |
| 1 | Biên dưới hợp lệ | Chấp nhận. |
| 2 | Ngay trên biên dưới | Chấp nhận. |
| 50 | Đại diện miền hợp lệ | Chấp nhận. |
| 99 | Biên trên hợp lệ | Chấp nhận. |
| 100 | Trên biên | Từ chối. |

Nếu giá trị âm và giá trị 0 dẫn đến thông báo hoặc nhánh xử lý khác nhau, cần giữ chúng thành các phân vùng riêng.

### 3.2. Số thực và độ chính xác

Với số thực, cần xác định độ chính xác được hỗ trợ. Không nên dùng các số thập phân tùy ý mà không xem xét cách hệ thống lưu và so sánh chúng.

Các khía cạnh cần kiểm tra:

- Giá trị âm, bằng 0 và dương.
- Ngưỡng min/max.
- Số chữ số trước và sau dấu thập phân.
- Giá trị có quá nhiều chữ số thập phân.
- Làm tròn, cắt bớt hoặc từ chối phần dư.
- Giá trị rất lớn, rất nhỏ và biểu diễn khoa học nếu được phép.
- Giá trị không hữu hạn như NaN hoặc Infinity nếu kiểu và giao thức có thể biểu diễn.

Ví dụ, trường **discountRate** nhận từ 0 đến 1 với tối đa ba chữ số thập phân. Các trường hợp nên xét gồm 0, 0.001, 0.999, 1.000, -0.001, 1.001 và 0.1234. Kỳ vọng với 0.1234 phải được quy định rõ: từ chối, làm tròn hay chuẩn hóa.

### 3.3. Tiền tệ và phép tính tài chính

Với tiền, cần phân biệt giá trị số với quy tắc nghiệp vụ. Nên xác định:

- Đơn vị tiền tệ và số chữ số thập phân được hỗ trợ.
- Giá trị tối thiểu và tối đa của giao dịch.
- Có cho phép số tiền bằng 0 hoặc âm không.
- Quy tắc làm tròn ở từng bước và ở tổng cuối.
- Cách xử lý thuế, phí, giảm giá và chuyển đổi tiền tệ.
- Hành vi khi tổng tiền vượt giới hạn hoặc tràn kiểu lưu trữ.

Ví dụ, một khoản thanh toán bằng VND có thể yêu cầu số nguyên đơn vị đồng, trong khi một loại tiền khác có thể hỗ trợ hai chữ số thập phân. Không nên áp dụng cùng một quy tắc precision cho mọi currency nếu nghiệp vụ không quy định như vậy.

Với ngưỡng thanh toán tối thiểu 10.000 và tối đa 50.000.000, hãy kiểm tra 9.999, 10.000, 10.001, 49.999.999, 50.000.000 và 50.000.001. Bổ sung trường hợp tổng tiền sau thuế hoặc phí vượt ngưỡng, vì kết quả có thể khác với việc chỉ kiểm tra từng dòng.

### 3.4. Số lớn, tràn và giới hạn kỹ thuật

Nếu dữ liệu được lưu trong kiểu có giới hạn, hãy xem xét:

- Giá trị tại giới hạn biểu diễn.
- Giá trị vượt giới hạn.
- Tràn khi nhân, cộng hoặc chuyển kiểu.
- Giá trị âm trong trường chỉ cho phép không âm.
- Sự khác biệt giữa giới hạn ứng dụng, database và API.

Ví dụ, số lượng và đơn giá đều hợp lệ riêng lẻ nhưng phép nhân có thể vượt giới hạn kiểu tiền. Cần kiểm tra kết quả tính toán và việc từ chối hoặc xử lý tràn theo quy tắc.

## 4. Chọn phân vùng và giá trị biên cho ngày giờ

Ngày giờ thường có nhiều ranh giới nghiệp vụ hơn một miền số đơn giản. Cần phân biệt ngày lịch, thời điểm tuyệt đối, múi giờ và độ phân giải.

### 4.1. Ngày lịch

Với một trường ngày có giới hạn, ví dụ ngày đặt lịch từ hôm nay đến 90 ngày tiếp theo, cần xác định:

- Ngày hôm nay có hợp lệ không?
- Ngày cuối cùng trong khoảng có được bao gồm không?
- Ngày quá khứ bị xử lý thế nào?
- Ngày nhuận và ngày cuối tháng có hợp lệ không?
- Quy tắc có phụ thuộc múi giờ của người dùng hoặc tổ chức không?

Ví dụ nếu ngày kết thúc được bao gồm, hãy kiểm tra ngày hôm nay, ngày hôm qua, ngày cuối cùng được phép và ngày ngay sau ngày đó. Không nên chỉ dùng ngày cố định trong test nếu hành vi phụ thuộc ngày hiện tại; cần cố định clock hoặc dùng dữ liệu thời gian có thể kiểm soát để test tái lập.

### 4.2. Thời điểm và độ phân giải

Với timestamp, ranh giới có thể nằm ở millisecond, second hoặc một đơn vị khác theo hợp đồng. Nếu thời hạn kết thúc tại một thời điểm cụ thể và thời điểm bằng ngưỡng đã hết hạn, cần xác định điều kiện là nhỏ hơn hay nhỏ hơn hoặc bằng.

Các giá trị cần xét có thể là:

- Ngay trước thời điểm hết hạn theo độ phân giải hỗ trợ.
- Chính xác tại thời điểm hết hạn.
- Ngay sau thời điểm hết hạn.
- Thời điểm thiếu timezone hoặc có offset khác.
- Thời điểm có phần mili giây hoặc độ chính xác vượt giới hạn.

Không nên dùng sleep để kiểm tra thời gian. Hãy cố định đồng hồ trong test hoặc truyền clock có thể kiểm soát để tạo chính xác các thời điểm cần kiểm tra.

### 4.3. Múi giờ và chuyển đổi giờ mùa hè

Nếu sản phẩm phục vụ nhiều múi giờ, hãy kiểm tra:

- Cùng một thời điểm được hiển thị đúng ở các múi giờ khác nhau.
- Ngày chuyển sang hôm trước hoặc hôm sau khi đổi timezone.
- Khoảng giờ bị lặp hoặc không tồn tại ở nơi có quy tắc daylight saving time.
- Ngày giờ nhập không kèm timezone được hiểu theo quy tắc nào.
- Thời điểm lưu trữ và thời điểm hiển thị có nhất quán không.

Không nên giả định một ngày địa phương luôn tương ứng với 24 giờ. Với quy tắc đặt lịch, hạn thanh toán hoặc thời điểm hết hạn, cần dùng timezone đã được xác định trong yêu cầu.

### 4.4. Ngày nhuận và lịch

Các trường hợp đặc biệt gồm ngày 29 tháng 2, cuối tháng 2, cuối năm, chuyển năm và các ngày không hợp lệ như 31 tháng 4. Nếu có quy tắc cộng tháng hoặc tính tuổi, hãy kiểm tra cách xử lý ngày không tồn tại ở tháng đích.

Ví dụ, cộng một tháng vào ngày 31 cần có quy tắc rõ ràng: chuyển sang ngày cuối tháng, từ chối hay áp dụng hành vi khác. Test phải phản ánh quyết định nghiệp vụ thay vì tự giả định.

## 5. Chọn phân vùng và giá trị biên cho chuỗi

Chuỗi có nhiều chiều hơn độ dài. Cần xét nội dung, định dạng, mã hóa, chuẩn hóa và cách hệ thống đo độ dài.

### 5.1. Độ dài chuỗi

Với trường tên cho phép từ 1 đến 80 ký tự, các giá trị biên cơ bản là 0, 1, 2, 79, 80 và 81. Nhưng cần làm rõ “ký tự” được tính theo byte, code point hay grapheme cluster.

Ví dụ, một emoji có thể được biểu diễn bằng nhiều code unit; một chữ có dấu có thể ở dạng Unicode dựng sẵn hoặc tổ hợp. Nếu backend, database và frontend đếm độ dài khác nhau, dữ liệu có thể bị từ chối hoặc cắt sai.

Vì vậy, hãy kiểm tra:

- Chuỗi rỗng và chuỗi chỉ chứa khoảng trắng.
- Độ dài tối thiểu và tối đa.
- Một đơn vị dưới và trên giới hạn.
- Ký tự tiếng Việt có dấu và ký tự Unicode ngoài ASCII.
- Emoji hoặc ký tự kết hợp nếu sản phẩm hỗ trợ.
- Chuỗi có byte length khác character count đáng kể.
- Khoảng trắng đầu/cuối và nhiều khoảng trắng liên tiếp.

### 5.2. Định dạng và tập ký tự

Với email, số điện thoại, mã bưu chính hoặc username, hãy chia phân vùng theo quy tắc định dạng:

- Định dạng hợp lệ phổ biến.
- Thiếu phần bắt buộc.
- Có ký tự không được phép.
- Dấu phân cách sai hoặc lặp.
- Chữ hoa/chữ thường.
- Khoảng trắng hoặc ký tự điều khiển.
- Ký tự Unicode nếu được phép.
- Chuỗi quá dài hoặc quá ngắn.

Không nên tự tạo regex đơn giản rồi coi đó là định nghĩa chuẩn của email hoặc tên người dùng. Hãy dùng hợp đồng sản phẩm và quy tắc chuẩn hóa thực tế. Các trường hợp hiếm chỉ cần kiểm tra khi sản phẩm có cam kết hỗ trợ.

### 5.3. Chuẩn hóa và so sánh chuỗi

Một chuỗi có thể trông giống nhau nhưng có biểu diễn khác nhau. Cần xác định hệ thống có:

- Trim khoảng trắng đầu/cuối không?
- Chuẩn hóa Unicode không?
- So sánh không phân biệt hoa/thường không?
- Chuẩn hóa dấu hoặc ký tự tương đương không?
- Giữ nguyên khoảng trắng bên trong không?
- Mã hóa hoặc giải mã URL, HTML và JSON đúng không?

Ví dụ, hai dạng Unicode của cùng một chữ có thể hiển thị giống nhau nhưng có byte sequence khác nhau. Nếu username được so sánh theo dạng chuẩn hóa, test cần xác minh hai biểu diễn tương đương không tạo hai tài khoản ngoài ý muốn.

### 5.4. Chuỗi có ý nghĩa nghiệp vụ

Đối với mã giảm giá, mã định danh hoặc mã vùng, phân vùng có thể dựa trên trạng thái và quy tắc:

- Mã hợp lệ và còn hiệu lực.
- Mã đúng định dạng nhưng không tồn tại.
- Mã đã hết hạn hoặc đã sử dụng.
- Mã bị vô hiệu hóa.
- Mã hợp lệ nhưng không áp dụng cho loại người dùng hoặc sản phẩm hiện tại.
- Mã có chữ hoa/thường hoặc khoảng trắng cần chuẩn hóa.

Không gộp tất cả mã bị từ chối thành một phân vùng nếu thông báo, quyền hoặc tác dụng phụ khác nhau.

## 6. Chọn phân vùng và giá trị biên cho danh sách và tập hợp

Với mảng, danh sách hoặc tập hợp, các ranh giới thường liên quan đến số phần tử, tính duy nhất, thứ tự và quan hệ giữa phần tử.

### 6.1. Số lượng phần tử

Nếu API nhận từ 1 đến 20 sản phẩm trong một request, hãy kiểm tra:

- 0 phần tử.
- 1 phần tử.
- 2 phần tử.
- 19 phần tử.
- 20 phần tử.
- 21 phần tử.

Nếu danh sách cho phép rỗng, 0 là biên hợp lệ và cần xác minh hệ thống trả kết quả đúng. Nếu danh sách có giới hạn phân trang, hãy kiểm tra page size bằng 1, giới hạn tối đa và lớn hơn giới hạn.

### 6.2. Phần tử trùng và tính duy nhất

Xác định tập hợp có cho phép phần tử trùng không. Ví dụ, giỏ hàng có thể gộp hai dòng cùng product ID, trong khi danh sách người nhận thông báo có thể loại bỏ email trùng.

Các phân vùng:

- Tất cả phần tử duy nhất.
- Có một phần tử lặp.
- Tất cả phần tử giống nhau.
- Phần tử trùng khác chữ hoa/thường hoặc khác định dạng chuẩn hóa.
- Phần tử null hoặc thiếu thuộc tính bắt buộc.

Kết quả mong đợi cần nói rõ gộp, từ chối hay giữ nguyên phần tử trùng.

### 6.3. Thứ tự và quan hệ giữa phần tử

Nếu thứ tự có ý nghĩa, hãy kiểm tra danh sách đã sắp xếp, đảo ngược, cùng giá trị, phần tử đầu/cuối và thứ tự không hợp lệ. Nếu thứ tự không có ý nghĩa, không nên viết assertion phụ thuộc thứ tự tùy ý.

Với danh sách có quan hệ như khoảng thời gian, tuyến đường hoặc bước quy trình, cần kiểm tra phần tử không liên tục, thiếu phần tử bắt buộc và quan hệ trước/sau.

### 6.4. Phân trang và giới hạn truy vấn

Đối với pagination, cần xét:

- Trang đầu tiên và trang cuối.
- Page size bằng 1 và bằng giới hạn tối đa.
- Page size bằng 0 hoặc âm nếu API nhận kiểu số.
- Trang vượt quá số trang hiện có.
- Dữ liệu thay đổi giữa các lần truy vấn nếu hệ thống hỗ trợ cursor hoặc snapshot.
- Kết quả rỗng và tập kết quả đúng tại ranh giới trang.

Ví dụ, với page size tối đa 100, hãy kiểm tra 99, 100 và 101, cùng page number hợp lệ và không hợp lệ. Nếu API dùng cursor, kiểm tra cursor rỗng, không hợp lệ, hết hạn và cursor tại cuối tập kết quả.

## 7. Chọn phân vùng cho enum, trạng thái và boolean

### 7.1. Enum và tập giá trị hữu hạn

Với trường enum như **orderStatus**, hãy xác định:

- Mỗi giá trị được hỗ trợ.
- Giá trị đã ngừng sử dụng nhưng có thể xuất hiện trong dữ liệu cũ.
- Giá trị không biết hoặc sai chính tả.
- Giá trị thiếu hoặc null.
- Khác biệt chữ hoa/chữ thường nếu hợp đồng có quy định.

Không nên chỉ kiểm tra một enum hợp lệ và một chuỗi ngẫu nhiên. Mỗi trạng thái có thể kích hoạt hành vi khác nhau, đặc biệt với state machine.

### 7.2. Trạng thái chuyển tiếp

Với state machine, cần kiểm tra cả trạng thái hiện tại và hành động:

| Trạng thái hiện tại | Hành động | Kỳ vọng |
|---|---|---|
| PENDING | Confirm | Chuyển sang CONFIRMED. |
| PENDING | Cancel | Chuyển sang CANCELLED nếu quy tắc cho phép. |
| CONFIRMED | Ship | Chuyển sang SHIPPED. |
| SHIPPED | Cancel | Từ chối nếu không còn được phép hủy. |
| CANCELLED | Ship | Từ chối và không phát sinh tác dụng phụ. |
| Trạng thái không biết | Bất kỳ hành động nào | Từ chối hoặc xử lý theo quy tắc dữ liệu cũ. |

Ở đây, phân vùng không chỉ là từng giá trị trạng thái mà còn là cặp trạng thái – hành động. Hãy kiểm tra các chuyển tiếp hợp lệ và không hợp lệ có hậu quả quan trọng.

### 7.3. Boolean và trường có ba trạng thái

Boolean thường có hai giá trị true/false, nhưng dữ liệu đầu vào có thể có thêm trạng thái thiếu hoặc null. Nếu API phân biệt “không gửi trường”, “gửi false” và “gửi null”, hãy kiểm tra cả ba.

Ví dụ, trường **marketingConsent**:

- true: người dùng đồng ý.
- false: người dùng từ chối.
- absent: chưa cung cấp hoặc giữ nguyên giá trị hiện tại, tùy API.
- null: có thể không hợp lệ hoặc có ý nghĩa xóa giá trị.

Không được tự gộp absent và false nếu hợp đồng phân biệt chúng.

## 8. Chọn phân vùng và giá trị biên cho tệp

Tệp tải lên có nhiều thuộc tính độc lập. Chọn ca theo loại tệp, kích thước, nội dung, tên, mã hóa và cách xử lý.

### 8.1. Kích thước tệp

Nếu giới hạn là 10 MB, hãy xác định MB được tính theo 1.000.000 hay 1.048.576 byte. Sau đó kiểm tra:

- Tệp rỗng nếu được phép hoặc không được phép.
- Một byte.
- Ngay dưới giới hạn.
- Chính xác giới hạn.
- Ngay trên giới hạn.
- Tệp lớn hơn nhiều để xác minh giới hạn sớm và xử lý ổn định.

Không chỉ kiểm tra giao diện chặn tệp lớn. Cần xác minh server cũng thực thi giới hạn, vì client có thể bị bỏ qua.

### 8.2. Loại tệp và nội dung thực

Không chỉ dựa vào phần mở rộng. Hãy xem xét:

- Phần mở rộng được hỗ trợ.
- MIME type khai báo.
- Magic bytes hoặc chữ ký định dạng thực.
- Phần mở rộng và nội dung không khớp.
- Tệp bị hỏng hoặc bị cắt cụt.
- Nội dung không an toàn theo chính sách sản phẩm.
- Tên tệp có ký tự đặc biệt, đường dẫn hoặc Unicode.

Ví dụ, một tệp có đuôi PDF nhưng nội dung không phải PDF cần được xử lý theo chính sách. Việc đổi tên tệp không nên làm hệ thống tin rằng nội dung an toàn.

### 8.3. Tệp và metadata

Nếu sản phẩm sử dụng metadata, hãy kiểm tra tên, encoding, ngày tạo, kích thước, số trang hoặc thuộc tính liên quan. Cân nhắc metadata thiếu, sai định dạng hoặc chứa nội dung không mong đợi.

Với upload nhiều tệp, kết hợp phân vùng số lượng phần tử và giới hạn tổng dung lượng. Một tệp riêng lẻ có thể nằm dưới giới hạn nhưng tổng tất cả tệp lại vượt giới hạn request.

## 9. Xử lý các trường hợp kết hợp và phụ thuộc giữa dữ liệu

Phân vùng từng trường riêng lẻ chưa đủ khi quy tắc phụ thuộc vào nhiều đầu vào. Nhóm cần xác định tổ hợp có ý nghĩa mà không tạo toàn bộ tích Descartes của mọi giá trị.

### 9.1. Quy tắc liên trường

Ví dụ:

- Ngày kết thúc phải sau ngày bắt đầu.
- Số lượng nhân đơn giá không vượt giới hạn tổng tiền.
- Mã giảm giá chỉ áp dụng cho một số sản phẩm.
- Quốc gia quyết định định dạng mã bưu chính.
- Trạng thái đơn quyết định trường nào được phép sửa.
- Loại tài khoản quyết định giới hạn giao dịch.

Hãy tạo phân vùng cho quan hệ: hợp lệ, bằng nhau tại ranh giới, đảo ngược, thiếu một phía hoặc xung đột quy tắc.

### 9.2. Kết hợp theo rủi ro và pairwise

Nếu có nhiều trường với nhiều phân vùng, số tổ hợp tăng nhanh. Không phải lúc nào cũng cần kiểm tra mọi tổ hợp. Có thể dùng:

- **Bảng quyết định:** khi kết quả phụ thuộc vào một số điều kiện kết hợp.
- **Pairwise testing:** khi muốn bảo đảm mọi cặp giá trị giữa các yếu tố được kết hợp ít nhất một lần.
- **Risk-based combinations:** chọn tổ hợp có hậu quả cao hoặc có lịch sử lỗi.
- **State transition testing:** khi trạng thái trước và hành động quyết định trạng thái tiếp theo.

Pairwise không bảo đảm phát hiện lỗi chỉ xuất hiện khi ba hoặc nhiều điều kiện cùng xảy ra. Với quy tắc bảo mật, thanh toán hoặc dữ liệu quan trọng, cần thêm tổ hợp chuyên biệt dựa trên hiểu biết nghiệp vụ.

### 9.3. Tránh tổ hợp không thể xảy ra

Một số tổ hợp không hợp lệ về mặt nghiệp vụ hoặc không thể xuất hiện trong hệ thống. Ghi rõ ràng buộc để tránh tạo ca kiểm thử vô nghĩa. Nếu mục tiêu là xác minh hệ thống từ chối một request cố tình vi phạm nhiều quy tắc, có thể vẫn cần test riêng cho trường hợp đó.

## 10. Ví dụ tổng hợp: thiết kế test cho biểu mẫu đặt lịch

Giả sử biểu mẫu đặt lịch có các trường:

- startDate: ngày bắt đầu, từ hôm nay đến 90 ngày tới.
- endDate: ngày kết thúc, không trước ngày bắt đầu và thời lượng tối đa 14 ngày.
- guestCount: số nguyên từ 1 đến 8.
- guestName: từ 1 đến 80 ký tự sau chuẩn hóa.
- roomType: STANDARD, DELUXE hoặc SUITE.
- attachments: tối đa 3 tệp, mỗi tệp PDF hoặc JPG và không quá 5 MB.

### 10.1. Phân vùng tương đương

| Trường | Phân vùng hợp lệ | Phân vùng không hợp lệ hoặc riêng |
|---|---|---|
| startDate | Hôm nay đến ngày thứ 90. | Quá khứ; sau ngày thứ 90; sai định dạng; thiếu nếu bắt buộc. |
| endDate | Từ startDate đến startDate + 14 ngày. | Trước startDate; vượt thời lượng; sai định dạng. |
| guestCount | Số nguyên 1–8. | 0; âm; trên 8; số thập phân; chuỗi; null. |
| guestName | Chuỗi không rỗng sau chuẩn hóa, tối đa 80 ký tự. | Rỗng; chỉ khoảng trắng; quá dài; kiểu dữ liệu sai. |
| roomType | Một trong ba enum được hỗ trợ. | Giá trị lạ; thiếu; null nếu không cho phép. |
| attachments | 0–3 tệp đúng định dạng và kích thước. | Trên 3 tệp; loại không hỗ trợ; tệp sai nội dung; tệp quá lớn. |

### 10.2. Giá trị biên cần chọn

| Trường | Các giá trị sát biên hoặc trường hợp đặc biệt |
|---|---|
| startDate | Hôm qua, hôm nay, ngày mai, ngày thứ 90, ngày thứ 91; ngày nhuận nếu có liên quan. |
| endDate | Bằng startDate; startDate + 1 ngày; đúng 14 ngày; 15 ngày; trước startDate một ngày. |
| guestCount | 0, 1, 2, 7, 8, 9. |
| guestName | 0, 1, 2, 79, 80, 81 ký tự; tiếng Việt có dấu; khoảng trắng; Unicode kết hợp. |
| roomType | Mỗi enum được hỗ trợ; giá trị không biết; khác biệt chữ hoa/thường nếu hợp đồng quy định. |
| attachments | 0, 1, 2, 3, 4 tệp; kích thước 0 byte, ngay dưới 5 MB, đúng 5 MB và ngay trên; MIME/đuôi không khớp. |

### 10.3. Tổ hợp liên trường quan trọng

- endDate bằng startDate: xác minh đặt lịch một ngày có được phép không.
- endDate trước startDate: phải bị từ chối.
- endDate đúng 14 ngày: xác minh đầu mút có được bao gồm.
- startDate ở ngày thứ 90 và endDate vượt ngày cho phép: xác minh giới hạn tổng thể.
- guestCount ở mức 8 với roomType không hỗ trợ sức chứa: xác minh quy tắc sức chứa.
- Tệp hợp lệ về kích thước nhưng MIME không khớp nội dung: phải bị từ chối.
- Ba tệp mỗi tệp hợp lệ nhưng tổng request vượt giới hạn: xác minh giới hạn tổng dung lượng nếu có.

### 10.4. Xác định kết quả mong đợi

Mỗi ca cần xác định không chỉ việc chấp nhận hay từ chối, mà còn:

- Mã lỗi hoặc thông báo theo hợp đồng.
- Trường nào được đánh dấu lỗi.
- Có tạo lịch đặt hay không.
- Có lưu tệp hoặc tài nguyên tạm không.
- Dữ liệu hợp lệ có được chuẩn hóa nhất quán không.
- Không phát sinh tác dụng phụ khi request bị từ chối.

## 11. Tổ chức bộ test và ghi nhận độ bao phủ

### 11.1. Liên kết ca kiểm thử với phân vùng

Mỗi test case nên có thể truy ngược đến trường dữ liệu, phân vùng, ranh giới và yêu cầu. Có thể dùng ID như DATE-LOW-01, COUNT-MAX-01 hoặc nhãn trong test framework.

Không bắt buộc đặt tên test theo một quy tắc cụ thể, nhưng tên và mô tả cần cho biết điều kiện nào đang được xác minh.

### 11.2. Ghi lại giá trị biên và giả định

Tài liệu test nên ghi rõ:

- Giới hạn lấy từ yêu cầu hoặc cấu hình nào.
- Đơn vị và độ chính xác.
- Đầu mút bao gồm hay loại trừ.
- Clock, timezone và locale được dùng.
- Cách đếm độ dài chuỗi hoặc kích thước tệp.
- Quy tắc chuẩn hóa dữ liệu.
- Các tổ hợp được chọn và lý do.

Nếu giới hạn thay đổi, nhóm có thể xác định ca nào cần cập nhật thay vì tìm kiếm thủ công trong toàn bộ bộ test.

### 11.3. Đánh giá bao phủ theo phân vùng và ranh giới

Một báo cáo có thể ghi:

| Chỉ số | Ý nghĩa |
|---|---|
| Phân vùng đã có test / tổng phân vùng xác định | Cho biết các nhóm hành vi có đại diện hay chưa. |
| Ranh giới đã kiểm tra / tổng ranh giới quan trọng | Cho biết các điểm chuyển tiếp có bằng chứng hay chưa. |
| Tổ hợp liên trường đã kiểm tra | Cho biết các quy tắc phụ thuộc nhiều trường được xác minh đến đâu. |
| Trường hợp không hợp lệ đã kiểm tra | Cho biết hệ thống có từ chối dữ liệu sai đúng cách không. |
| Phân vùng có rủi ro cao chưa được kiểm tra | Nêu khoảng trống cần quyết định. |

Không nên báo cáo một tỷ lệ bao phủ duy nhất nếu nó che khuất loại phân vùng hoặc ranh giới bị bỏ sót. 100% phân vùng có đại diện không có nghĩa mọi giá trị hoặc mọi tổ hợp đều đã được kiểm tra.

## 12. Những sai lầm thường gặp

- **Chọn một giá trị bất kỳ mà không hiểu phân vùng:** hai giá trị cùng kiểu có thể đi qua quy tắc khác nhau.
- **Chỉ kiểm tra min và max:** bỏ sót giá trị ngay dưới, ngay trên hoặc đầu mút không được bao gồm.
- **Giả định đầu mút luôn hợp lệ:** phải đọc chính xác điều kiện nhỏ hơn, nhỏ hơn hoặc bằng, lớn hơn hoặc lớn hơn hoặc bằng.
- **Bỏ qua kiểu dữ liệu sai:** chuỗi, boolean, null, thiếu trường và số thập phân có thể được xử lý khác nhau.
- **Không xét độ chính xác:** số thực, tiền và timestamp cần đơn vị nhỏ nhất rõ ràng.
- **Đếm chuỗi theo một cách duy nhất:** byte, code point và grapheme có thể khác nhau.
- **Bỏ qua múi giờ và lịch:** thời điểm hết hạn, ngày nhuận và chuyển giờ có thể làm thay đổi kết quả.
- **Chỉ kiểm tra số phần tử:** danh sách còn có trùng lặp, thứ tự, phần tử null và tổng kích thước.
- **Chỉ kiểm tra phần mở rộng tệp:** nội dung thực và MIME có thể không khớp.
- **Không kiểm tra quan hệ giữa trường:** các trường hợp hợp lệ riêng lẻ vẫn có thể tạo tổ hợp không hợp lệ.
- **Tạo mọi tổ hợp mà không cân nhắc rủi ro:** số ca tăng nhanh nhưng không nhất thiết tạo thêm bằng chứng hữu ích.
- **Không cập nhật khi quy tắc thay đổi:** bộ test có thể tiếp tục kiểm tra giới hạn cũ.

## 13. Danh sách rà soát trước khi chốt thiết kế bao phủ

- [ ] Quy tắc và miền dữ liệu được lấy từ nguồn có thẩm quyền.
- [ ] Kiểu dữ liệu, đơn vị, độ chính xác và điều kiện bắt buộc được ghi rõ.
- [ ] Phân vùng hợp lệ và không hợp lệ được xác định theo hành vi.
- [ ] Mỗi phân vùng quan trọng có ít nhất một giá trị đại diện.
- [ ] Các ranh giới quan trọng có giá trị ngay dưới, tại và ngay trên.
- [ ] Đầu mút bao gồm hoặc loại trừ được kiểm tra đúng.
- [ ] Ngày giờ có kiểm tra timezone, độ phân giải và trường hợp lịch phù hợp.
- [ ] Chuỗi có kiểm tra độ dài, Unicode, khoảng trắng và chuẩn hóa.
- [ ] Danh sách có kiểm tra số lượng, trùng lặp, thứ tự và phân trang khi liên quan.
- [ ] Enum, boolean, null và trường bị thiếu được xử lý theo hợp đồng.
- [ ] Tệp có kiểm tra kích thước, định dạng khai báo và nội dung thực.
- [ ] Quan hệ giữa các trường và tổ hợp rủi ro cao được kiểm tra.
- [ ] Mỗi ca có kết quả mong đợi và tác dụng phụ được phép rõ ràng.
- [ ] Có liên kết giữa phân vùng, ranh giới, yêu cầu và ca kiểm thử.
- [ ] Khoảng trống bao phủ được ghi nhận và ưu tiên theo rủi ro.

## Kết luận

Phân vùng tương đương giúp chọn đại diện cho các nhóm đầu vào có hành vi giống nhau; phân tích giá trị biên giúp tập trung vào những điểm mà quy tắc thay đổi. Khi áp dụng theo từng loại dữ liệu, nhóm cần xem xét kiểu, đơn vị, độ chính xác, định dạng, chuẩn hóa, trạng thái và quan hệ giữa các trường. Kết hợp các kỹ thuật này với đánh giá rủi ro và kết quả mong đợi rõ ràng giúp bộ kiểm thử bao phủ có chủ đích, phát hiện lỗi tại ranh giới và dễ cập nhật khi yêu cầu thay đổi.

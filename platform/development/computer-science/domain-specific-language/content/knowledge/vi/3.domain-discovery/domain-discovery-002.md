# Thu thập ví dụ thực tế

## 1. Vì sao cần thu thập ví dụ thực tế?

Trong quá trình khám phá miền nghiệp vụ, ví dụ thực tế là bằng chứng cụ thể về cách công việc đang diễn ra. Một mô tả như “hệ thống cần áp dụng khuyến mãi linh hoạt” cho biết mong muốn chung, nhưng chưa giải thích khuyến mãi nào được áp dụng, dữ liệu nào được kiểm tra, ai có quyền quyết định, hoặc điều gì xảy ra khi nhiều điều kiện cùng xuất hiện. Một trường hợp đã xảy ra giúp nhóm nhìn thấy các quyết định và quy tắc ẩn sau câu mô tả đó.

Ví dụ thực tế giúp nhóm phát triển ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL):

- Hiểu công việc trong bối cảnh cụ thể, gồm tác nhân, mục tiêu, dữ liệu và kết quả.
- Thu thập đúng từ ngữ mà chuyên gia nghiệp vụ sử dụng.
- Phát hiện quy tắc, ngoại lệ, giới hạn và các trường hợp chưa có cách xử lý thống nhất.
- Phân biệt điều thường xảy ra với điều chỉ được giả định hoặc ghi trong tài liệu.
- Xác định những nội dung người dùng cần diễn đạt bằng DSL.
- Kiểm tra xem một mô hình hoặc cú pháp đề xuất có mô tả được công việc thật hay không.

Ví dụ càng cụ thể thì cuộc trao đổi càng dễ kiểm chứng. Thay vì hỏi “Chương trình khuyến mãi hoạt động như thế nào?”, hãy đề nghị người phụ trách kể lại một đơn hàng gần đây đã được áp dụng ưu đãi: khách hàng thuộc nhóm nào, giỏ hàng có những sản phẩm gì, mã nào được nhập, hệ thống đánh giá điều kiện ra sao, kết quả là gì và vì sao.

Thu thập ví dụ không có nghĩa là sao chép mọi dữ liệu vào tài liệu thiết kế. Mục tiêu là hiểu cấu trúc và quy tắc của công việc. Chỉ giữ thông tin cần thiết cho việc phân tích, ghi rõ nguồn và bối cảnh, đồng thời bảo vệ dữ liệu cá nhân hoặc thông tin kinh doanh nhạy cảm.

## 2. Ví dụ thực tế là gì?

Một ví dụ thực tế là bản ghi có căn cứ về một tình huống nghiệp vụ cụ thể đã xảy ra hoặc đang được xử lý. Nó cần đủ thông tin để người khác hiểu bối cảnh, lần theo quyết định và kiểm tra kết quả.

Một ví dụ có giá trị thường trả lời được các câu hỏi:

1. **Bối cảnh:** Công việc diễn ra ở đâu, vào thời điểm nào, trong tình huống nào?
2. **Mục tiêu:** Người tham gia muốn đạt kết quả gì?
3. **Tác nhân:** Ai thực hiện, phê duyệt hoặc nhận kết quả?
4. **Đầu vào:** Những thông tin nào được dùng để đưa ra quyết định?
5. **Diễn biến:** Các hành động và quyết định diễn ra theo thứ tự nào?
6. **Quy tắc:** Vì sao một lựa chọn được chấp nhận hoặc từ chối?
7. **Kết quả:** Trạng thái, dữ liệu hoặc công việc tiếp theo thay đổi ra sao?
8. **Ngoại lệ:** Có dữ liệu thiếu, điều kiện biên, xung đột hay xử lý thủ công nào không?
9. **Bằng chứng:** Thông tin đến từ quan sát, hồ sơ, hệ thống hay lời kể của ai?

Một câu chuyện chung chung chưa phải ví dụ đủ chi tiết. Chẳng hạn, “khách hàng được giảm giá vì là thành viên thân thiết” chưa cho biết hạng thành viên nào đủ điều kiện, giá trị đơn hàng được tính trước hay sau giảm giá, hoặc có giới hạn mức giảm hay không. Cần hỏi tiếp để chuyển lời kể thành một trường hợp có thể phân tích.

### 2.1 Phân biệt ví dụ, quy tắc và giả thuyết

Ba loại thông tin này cần được ghi riêng:

| Loại thông tin | Ý nghĩa | Ví dụ |
|---|---|---|
| Ví dụ quan sát được | Một trường hợp cụ thể có nguồn hoặc người xác nhận | Đơn hàng A đã nhận mức giảm 10% vào ngày X |
| Quy tắc được xác nhận | Chính sách hoặc điều kiện được người có thẩm quyền xác nhận | Đơn từ 2.000.000 đồng mới đủ điều kiện |
| Giả thuyết cần kiểm chứng | Cách giải thích tạm thời của nhóm | Có thể hệ thống tính ngưỡng trên tổng tiền trước giảm giá |

Một trường hợp đã xảy ra có thể cho thấy hệ thống đã làm gì, nhưng không tự chứng minh rằng hành vi đó đúng với chính sách hiện hành. Có thể hệ thống đang chứa lỗi, dữ liệu lịch sử đã cũ hoặc nhân viên đã xử lý ngoại lệ. Vì vậy, hãy ghi lại cả điều đã quan sát và cách giải thích được người sở hữu nghiệp vụ xác nhận.

Tương tự, một ví dụ minh họa do nhóm phát triển tự tạo có ích để giải thích mô hình, nhưng không được ghi nhận như bằng chứng thực tế. Luôn đánh dấu rõ ví dụ nào đến từ hoạt động thật và ví dụ nào chỉ dùng để minh họa.

## 3. Xác định cần thu thập những loại ví dụ nào

Nếu chỉ thu thập những trường hợp thành công và dễ gặp nhất, nhóm sẽ bỏ sót phần lớn quy tắc quan trọng. DSL thường phải biểu diễn cả điều kiện biên, trường hợp bị từ chối, xung đột và ngoại lệ.

Nên lập danh sách các nhóm tình huống trước khi phỏng vấn hoặc quan sát:

| Nhóm ví dụ | Mục đích | Câu hỏi gợi ý |
|---|---|---|
| Trường hợp điển hình | Hiểu luồng công việc thường ngày | Một trường hợp bình thường được xử lý từ đầu đến cuối thế nào? |
| Trường hợp thành công | Xác định điều kiện tạo ra kết quả hợp lệ | Điều kiện nào đã được đáp ứng? |
| Trường hợp bị từ chối | Tìm hiểu quy tắc loại trừ và lý do lỗi | Trường hợp gần đây nào không được chấp nhận? Vì sao? |
| Trường hợp biên | Xác định giới hạn và toán tử so sánh | Điều gì xảy ra khi giá trị đúng bằng ngưỡng? |
| Trường hợp ngoại lệ | Hiểu cách xử lý khi quy trình thông thường không áp dụng | Khi dữ liệu thiếu hoặc có sự cố, nhân viên làm gì? |
| Trường hợp xung đột | Khám phá thứ tự ưu tiên và cách phối hợp quy tắc | Nếu hai chính sách cùng đúng thì chọn thế nào? |
| Trường hợp thay đổi | Hiểu hiệu lực theo thời gian và lịch sử | Nếu chính sách đổi giữa chừng, giao dịch cũ được xử lý ra sao? |
| Trường hợp liên miền | Nhận diện ranh giới và phụ thuộc | Dữ liệu hoặc quyết định nào đến từ bộ phận khác? |
| Trường hợp hiếm nhưng quan trọng | Phát hiện rủi ro có tác động lớn | Có tình huống ít gặp nào gây thiệt hại đáng kể không? |

Không nhất thiết phải thu thập số lượng bằng nhau ở mọi nhóm. Hãy ưu tiên theo tần suất, mức độ ảnh hưởng, độ phức tạp của quy tắc và mức độ không chắc chắn. Một trường hợp rất hiếm nhưng liên quan đến hoàn tiền lớn hoặc vi phạm chính sách có thể quan trọng hơn nhiều trường hợp thông thường.

### 3.1 Chọn mẫu có chủ đích

Chọn mẫu có chủ đích nghĩa là tìm những trường hợp có khả năng làm rõ một câu hỏi cụ thể. Ví dụ:

- Chọn một giao dịch đúng ngưỡng để xác định điều kiện dùng toán tử lớn hơn hoặc lớn hơn bằng.
- Chọn một giao dịch có hai ưu đãi hợp lệ để hiểu thứ tự ưu tiên.
- Chọn một hồ sơ thiếu dữ liệu để tìm hiểu cách xử lý thông tin không xác định.
- Chọn một trường hợp được sửa sau khi phê duyệt để hiểu lịch sử và quyền thay đổi.
- Chọn một trường hợp phải chuyển cho bộ phận khác để tìm điểm bàn giao.

Có thể bắt đầu với một vài trường hợp đại diện, sau đó bổ sung ví dụ khi xuất hiện quy tắc mới hoặc mâu thuẫn. Số lượng ví dụ không quan trọng bằng khả năng giải thích các quyết định và bao phủ những tình huống có ý nghĩa.

## 4. Nguồn thu thập ví dụ

Không nên dựa vào một nguồn duy nhất. Mỗi nguồn cho thấy một phần khác nhau của hoạt động nghiệp vụ.

### 4.1 Phỏng vấn chuyên gia nghiệp vụ

Phỏng vấn giúp hiểu mục tiêu, lý do của quyết định, chính sách và ngoại lệ. Nên mời cả người thực hiện công việc hằng ngày lẫn người sở hữu hoặc phê duyệt quy tắc.

Thay vì chỉ hỏi quan điểm chung, hãy yêu cầu người được phỏng vấn kể lại một trường hợp gần đây:

- “Anh/chị có thể kể lại lần gần nhất xử lý trường hợp này không?”
- “Lúc đó thông tin nào đã có sẵn?”
- “Anh/chị đã kiểm tra điều gì trước?”
- “Vì sao bước đó cần thiết?”
- “Điều gì khiến trường hợp này khác với trường hợp thông thường?”
- “Nếu thiếu thông tin này thì anh/chị sẽ làm gì?”
- “Ai có quyền quyết định ngoại lệ?”
- “Có tài liệu hoặc bản ghi nào thể hiện trường hợp đó không?”

Khi người tham gia dùng từ mơ hồ như “đủ điều kiện”, “khách tốt”, “đơn lớn” hoặc “xử lý nhanh”, hãy hỏi họ đưa ra ví dụ và tiêu chí cụ thể. Không tự suy diễn định nghĩa từ những từ quen thuộc.

### 4.2 Quan sát công việc

Quan sát trực tiếp giúp phát hiện các bước mà người thực hiện có thể quên kể, chẳng hạn mở nhiều màn hình, tra cứu bảng riêng, gọi điện xác nhận hoặc ghi chú thủ công.

Trong lúc quan sát:

1. Ghi lại thời điểm bắt đầu và kết thúc của tình huống.
2. Ghi hành động thực tế theo thứ tự.
3. Ghi thông tin mà người thực hiện xem hoặc nhập.
4. Hỏi về lý do sau khi người thực hiện hoàn tất một quyết định, tránh ngắt quãng liên tục.
5. Ghi nhận thao tác ngoài hệ thống và điểm cần người khác phê duyệt.
6. Xác nhận lại phần ghi chép với người thực hiện.

Phân biệt hành động quan sát được với lời giải thích. Ví dụ, “nhân viên mở bảng thành viên” là quan sát; “nhân viên làm vậy vì hệ thống không tự lấy được hạng thành viên” là lời giải thích cần được xác nhận.

### 4.3 Hồ sơ và tài liệu nghiệp vụ

Các nguồn có thể gồm:

- Biểu mẫu yêu cầu và phiếu phê duyệt.
- Chính sách, quy định và hướng dẫn vận hành.
- Bảng tính, danh mục và bảng quy tắc.
- Hợp đồng, biểu mẫu trao đổi với đối tác.
- Hồ sơ giao dịch, lịch sử trạng thái và nhật ký xử lý.
- Phiếu hỗ trợ, khiếu nại và báo cáo sự cố.
- Tài liệu đào tạo và hướng dẫn cho nhân viên.

Tài liệu cho biết quy trình được quy định như thế nào; hồ sơ thực tế cho thấy công việc đã được thực hiện ra sao. Khi hai nguồn khác nhau, ghi lại sự khác biệt và hỏi người sở hữu chính sách. Không mặc định tài liệu mới nhất hoặc hệ thống hiện tại luôn phản ánh đúng thực tế.

### 4.4 Nhật ký và dữ liệu hệ thống

Nhật ký có thể cho thấy thứ tự sự kiện, trạng thái trước và sau, lỗi, lần thử lại và thời điểm xử lý. Dữ liệu hệ thống giúp kiểm chứng tần suất và tìm trường hợp biên mà phỏng vấn khó nhớ.

Khi sử dụng dữ liệu, cần hiểu:

- Ý nghĩa nghiệp vụ của từng trường, mã trạng thái và thời điểm.
- Dữ liệu nào được ghi tự động, dữ liệu nào do người dùng nhập.
- Có sự thay đổi hoặc sửa dữ liệu sau khi sự kiện xảy ra không.
- Múi giờ, đơn vị đo và cách làm tròn được sử dụng.
- Bản ghi bị thiếu có nghĩa là không xảy ra sự kiện hay chỉ là không được ghi nhận.

Không đọc giá trị kỹ thuật như một quy tắc nghiệp vụ nếu chưa xác nhận. Ví dụ, trạng thái PENDING có thể được dùng cho nhiều tình huống khác nhau tùy hệ thống.

### 4.5 Trao đổi với các bên ở điểm bàn giao

Một ví dụ thường liên quan đến nhiều nhóm. Hãy hỏi cả bên gửi và bên nhận thông tin để xác định:

- Ai tạo dữ liệu và ai chịu trách nhiệm về độ chính xác?
- Bên nhận cần thông tin nào để tiếp tục?
- Khi dữ liệu không hợp lệ, ai xử lý?
- Có cam kết về thời gian hoặc thứ tự xử lý không?
- Cách hiểu trạng thái ở hai bên có giống nhau không?

Những câu hỏi này giúp nhận diện ranh giới miền và hợp đồng trao đổi giữa các ngữ cảnh.

## 5. Cách khai thác một ví dụ trong phỏng vấn

Một cuộc phỏng vấn hiệu quả đi từ trường hợp cụ thể đến quy tắc khái quát. Có thể sử dụng quy trình sau.

### Bước 1: Chọn một trường hợp có thật

Đề nghị người tham gia chọn một trường hợp gần đây và nhớ rõ, có thể kiểm tra bằng hồ sơ hoặc hệ thống. Ghi nhận mã tham chiếu đã được ẩn danh nếu cần.

### Bước 2: Xác định điểm bắt đầu và kết quả mong muốn

Hỏi điều gì kích hoạt công việc, ai yêu cầu xử lý và kết quả nào được xem là hoàn thành. Nếu có nhiều mục tiêu, ghi rõ mục tiêu chính và mục tiêu phụ.

### Bước 3: Đi theo dòng thời gian

Yêu cầu người tham gia kể từng bước theo đúng thứ tự. Với mỗi bước, hỏi:

- Ai thực hiện?
- Dùng dữ liệu hoặc công cụ nào?
- Đưa ra quyết định gì?
- Dựa vào điều kiện nào?
- Có cần chờ hoặc xin xác nhận không?
- Kết quả của bước này được chuyển cho ai?

### Bước 4: Đào sâu vào quyết định

Mỗi khi người tham gia nói “hệ thống tự động”, “đủ điều kiện” hoặc “theo quy định”, hãy hỏi điều kiện cụ thể và nguồn quy định. Nếu quyết định phụ thuộc vào kinh nghiệm cá nhân, ghi nhận đó là thao tác chuyên môn hoặc ngoại lệ, không tự biến thành quy tắc phổ quát.

### Bước 5: Tìm biến thể và ngoại lệ

Sau khi hiểu trường hợp chính, thay đổi từng điều kiện:

- Nếu giá trị thấp hơn hoặc đúng bằng ngưỡng thì sao?
- Nếu thiếu một trường dữ liệu thì sao?
- Nếu hai điều kiện mâu thuẫn thì sao?
- Nếu sự kiện xảy ra muộn hoặc được gửi lại thì sao?
- Nếu người dùng sửa yêu cầu sau khi đã phê duyệt thì sao?

Các câu hỏi giả định giúp mở rộng hiểu biết, nhưng câu trả lời cho tình huống giả định cần được đánh dấu là giả định cho đến khi có ví dụ hoặc người có thẩm quyền xác nhận.

### Bước 6: Kiểm tra bằng bằng chứng

Đề nghị xem tài liệu, màn hình, lịch sử giao dịch hoặc bản ghi có liên quan nếu được phép. Đối chiếu lời kể với bằng chứng và ghi lại điểm chưa thống nhất.

### Bước 7: Đọc lại và xác nhận

Tóm tắt trường hợp bằng ngôn ngữ trung lập. Hỏi người tham gia xem trình tự, thuật ngữ, điều kiện và kết quả đã chính xác chưa. Ghi rõ ai đã xác nhận và phần nào còn chờ người khác quyết định.

## 6. Mẫu ghi chép một ví dụ

Sử dụng một cấu trúc thống nhất giúp so sánh nhiều ví dụ mà không làm mất bối cảnh. Mẫu dưới đây có thể điều chỉnh theo miền:

| Trường | Nội dung cần ghi |
|---|---|
| Mã ví dụ | Mã nội bộ không chứa thông tin định danh |
| Tên ngắn | Mô tả tình huống trong một câu |
| Nguồn | Phỏng vấn, quan sát, tài liệu hay bản ghi hệ thống |
| Thời điểm | Ngày hoặc khoảng thời gian đã được làm mờ nếu cần |
| Người xác nhận | Vai trò của người xác nhận, không nhất thiết ghi tên |
| Mục tiêu | Kết quả nghiệp vụ cần đạt |
| Tác nhân | Người, nhóm hoặc hệ thống tham gia |
| Điều kiện ban đầu | Trạng thái và giả định trước khi bắt đầu |
| Đầu vào | Dữ liệu và đơn vị đo được sử dụng |
| Trình tự | Các hành động và quyết định theo thứ tự |
| Quy tắc liên quan | Điều kiện được áp dụng và nguồn xác nhận |
| Kết quả | Trạng thái, giá trị hoặc công việc tiếp theo |
| Ngoại lệ | Dữ liệu thiếu, xung đột, xử lý thủ công hoặc lỗi |
| Thuật ngữ | Từ ngữ nghiệp vụ được sử dụng |
| Điểm chưa rõ | Câu hỏi hoặc mâu thuẫn còn mở |
| Mức độ tin cậy | Đã quan sát, có hồ sơ đối chiếu, chỉ được kể lại hoặc đang giả định |

Một ví dụ có thể được ghi dưới dạng bảng, biểu mẫu hoặc cấu trúc dữ liệu. Điều quan trọng là cùng một ý nghĩa được dùng nhất quán giữa các trường hợp.

Ví dụ cấu trúc YAML minh họa:

~~~yaml
exampleId: PROMO-CASE-014
title: "Don hang thanh vien du dieu kien"
source:
  type: "transaction_record"
  verifiedByRole: "promotion_operator"
context:
  event: "customer_submits_order"
  actor: "sales_system"
inputs:
  memberTier: "GOLD"
  cartValue:
    amount: 2500000
    currency: "VND"
  promotionCode: "GOLD10"
decisions:
  - rule: "member_tier_at_least_gold"
    result: "passed"
  - rule: "cart_value_at_least_2000000"
    result: "passed"
outcome:
  discount:
    amount: 250000
    currency: "VND"
  status: "applied"
openQuestions:
  - "Cart value is measured before or after other discounts?"
~~~

Đây là cấu trúc minh họa, không phải dữ liệu được trích từ một doanh nghiệp cụ thể. Trong hồ sơ thực tế, cần bổ sung nguồn bằng chứng, thời điểm, định nghĩa trường và trạng thái xác nhận. Không đưa tên, số điện thoại, địa chỉ hoặc mã khách hàng thật vào ví dụ dùng chung.

## 7. Ví dụ minh họa cách thu thập trong miền khuyến mãi

Giả sử nhóm đang khám phá miền quản lý khuyến mãi cho một doanh nghiệp bán lẻ. Các tình huống sau là **ví dụ giả định để minh họa phương pháp ghi chép**, không phải kết luận về chính sách của một doanh nghiệp. Trong một dự án thật, từng điều kiện phải được kiểm tra bằng hồ sơ và người sở hữu quy tắc.

### 7.1 Trường hợp được áp dụng ưu đãi

Người vận hành cung cấp một giao dịch đã được xác nhận:

- Khách hàng có hạng thành viên Vàng.
- Giá trị giỏ hàng trước ưu đãi là 2.500.000 đồng.
- Mã GOLD10 được nhập trong thời hạn chiến dịch.
- Kết quả hiển thị mức giảm 10%, tương đương 250.000 đồng.

Các câu hỏi cần đặt ra:

- Hạng thành viên được lấy tại thời điểm tạo giỏ hàng hay thời điểm đặt đơn?
- Giá trị giỏ hàng có bao gồm phí giao hàng và thuế không?
- Mức giảm được tính trên toàn bộ giỏ hàng hay chỉ sản phẩm đủ điều kiện?
- Có giới hạn số tiền giảm tối đa không?
- Vì sao mã được chấp nhận: do mã hợp lệ, do hạng thành viên hay do cả hai?

Không thể kết luận toàn bộ quy tắc chỉ từ một giao dịch thành công. Cần thêm ví dụ và xác nhận chính sách.

### 7.2 Trường hợp đúng bằng ngưỡng

Giả sử một chính sách yêu cầu giá trị giỏ hàng tối thiểu 2.000.000 đồng. Hãy tìm hoặc tạo yêu cầu kiểm chứng với giá trị đúng 2.000.000 đồng, sau đó hỏi người sở hữu quy tắc kết quả nào là đúng.

Trường hợp này giúp phân biệt:

- “Lớn hơn 2.000.000”.
- “Lớn hơn hoặc bằng 2.000.000”.

Nếu chỉ quan sát một đơn hàng 2.500.000 đồng, cả hai cách hiểu đều cho kết quả đạt. Ví dụ đúng bằng ngưỡng mới giúp phân biệt ngữ nghĩa. Nếu chưa có giao dịch thật ở điểm biên, hãy đánh dấu đây là tình huống kiểm chứng giả định, không ghi là sự kiện đã xảy ra.

### 7.3 Trường hợp nhiều ưu đãi cùng hợp lệ

Một đơn hàng có thể đồng thời thỏa điều kiện của ưu đãi thành viên và ưu đãi theo danh mục sản phẩm. Cần tìm hiểu:

- Hai ưu đãi có được kết hợp không?
- Nếu không, ưu đãi nào được chọn?
- Thứ tự ưu tiên do ai cấu hình?
- Hệ thống có chọn mức giảm lớn nhất hay tuân theo thứ tự chính sách?
- Người dùng có thể chọn thủ công không?
- Kết quả có được giải thích trong lịch sử đơn hàng không?

Đây là loại ví dụ thường bộc lộ quy tắc ưu tiên mà tài liệu chỉ mô tả từng chương trình riêng lẻ không thể hiện.

### 7.4 Trường hợp thiếu dữ liệu thành viên

Giả sử hệ thống không lấy được hạng thành viên khi đánh giá mã. Hãy xác định hệ thống đã:

- Từ chối ưu đãi ngay lập tức.
- Tạm dừng và yêu cầu tra cứu lại.
- Cho phép tiếp tục theo một chính sách dự phòng.
- Chuyển trường hợp cho nhân viên xử lý.

Mỗi lựa chọn có ý nghĩa nghiệp vụ và rủi ro khác nhau. Không được tự chọn một hành vi chỉ vì cách đó dễ lập trình hơn. Hãy tìm ví dụ thực tế và hỏi người sở hữu chính sách về hành vi mong muốn.

### 7.5 Trường hợp hết hạn hoặc thay đổi chính sách

Tìm một giao dịch xảy ra gần thời điểm chiến dịch kết thúc hoặc một chính sách được sửa trong thời gian có giao dịch đang xử lý. Xác định:

- Thời điểm nào quyết định hiệu lực: lúc tạo giỏ hàng, lúc đặt đơn hay lúc thanh toán?
- Dùng múi giờ nào?
- Nếu đơn được tạo trước khi hết hạn nhưng thanh toán sau đó thì sao?
- Các đơn đã được áp dụng ưu đãi có bị tính lại khi chính sách thay đổi không?
- Có lưu phiên bản chính sách đã dùng cho giao dịch không?

Các trường hợp thời gian giúp làm rõ ý nghĩa của ngày bắt đầu, ngày kết thúc và lịch sử thay đổi.

## 8. Từ ví dụ riêng lẻ đến quy tắc của miền

Sau khi thu thập nhiều ví dụ, nhóm cần so sánh để tìm điểm chung và khác biệt. Không nên biến mỗi trường hợp thành một nhánh xử lý riêng ngay lập tức.

### 8.1 Nhóm các ví dụ có cùng cấu trúc

Có thể nhóm theo:

- Mục tiêu hoặc kết quả nghiệp vụ.
- Loại tác nhân.
- Loại đầu vào.
- Quyết định được đưa ra.
- Trạng thái đầu ra.
- Quy tắc hoặc ngoại lệ liên quan.

Nếu các ví dụ khác nhau về dữ liệu nhưng có cùng trình tự và cùng quyết định, chúng có thể là những trường hợp của một quy tắc chung. Nếu cùng tên gọi nhưng có cách xử lý khác nhau, cần kiểm tra xem chúng thuộc hai ngữ cảnh hay hai chính sách khác nhau không.

### 8.2 So sánh các trường hợp tương phản

Một cách hiệu quả là đặt cạnh nhau hai ví dụ chỉ khác một điều kiện. Ví dụ:

| Thuộc tính | Ví dụ A | Ví dụ B |
|---|---:|---:|
| Hạng thành viên | Vàng | Bạc |
| Giá trị giỏ hàng | 2.500.000 | 2.500.000 |
| Mã ưu đãi | GOLD10 | GOLD10 |
| Kết quả | Được áp dụng | Bị từ chối |

Nếu các yếu tố khác thực sự giống nhau, khác biệt có thể đến từ hạng thành viên. Tuy nhiên, vẫn cần kiểm tra thời hạn, danh mục sản phẩm, trạng thái mã và các điều kiện ẩn trước khi kết luận.

### 8.3 Tách quy tắc, dữ liệu và quy trình

Khi phân tích, phân loại thông tin:

- **Dữ liệu:** giá trị, hạng thành viên, mã, thời gian hoặc trạng thái được cung cấp.
- **Quy tắc:** điều kiện quyết định một giao dịch hợp lệ.
- **Quy trình:** thứ tự các bước và người thực hiện.
- **Quyết định:** kết quả lựa chọn tại một điểm trong quy trình.
- **Ngoại lệ:** cách xử lý khi điều kiện thông thường không đáp ứng.

Sự phân biệt này giúp tránh thiết kế DSL chỉ mô phỏng giao diện hoặc trình tự thao tác của một hệ thống cụ thể. Có thể một số bước giao diện thay đổi nhưng quy tắc nghiệp vụ vẫn giữ nguyên.

### 8.4 Ghi nhận tần suất và mức độ quan trọng

Nếu có đủ dữ liệu, ước lượng tần suất của từng loại tình huống. Đồng thời ghi mức độ ảnh hưởng khi xử lý sai. Không nên chỉ ưu tiên theo số lần xuất hiện: một trường hợp hiếm nhưng gây tổn thất lớn có thể cần được biểu diễn rõ trong mô hình và kiểm tra nghiêm ngặt.

Phân biệt số liệu đã đo với nhận định của người tham gia. Ví dụ, “xảy ra khoảng một lần mỗi tháng theo kinh nghiệm của nhân viên” không có độ chắc chắn giống báo cáo thống kê từ hệ thống.

## 9. Phát hiện mâu thuẫn và xử lý điểm chưa rõ

Trong thực tế, các nguồn thường không hoàn toàn thống nhất. Hai nhân viên có thể mô tả khác nhau; tài liệu có thể cũ; hành vi hệ thống có thể khác chính sách.

Khi gặp mâu thuẫn:

1. Giữ lại từng cách diễn giải cùng nguồn và thời điểm.
2. Xác định đó là khác biệt do vai trò, chi nhánh, thời gian, loại giao dịch hay do hiểu sai.
3. Tìm thêm trường hợp hoặc tài liệu có liên quan.
4. Hỏi người có thẩm quyền sở hữu quy tắc.
5. Ghi quyết định, người xác nhận, ngày hiệu lực và phạm vi áp dụng.
6. Nếu chưa giải quyết được, giữ câu hỏi ở trạng thái mở.

Không tự chọn cách hiểu thuận tiện cho việc viết parser hoặc triển khai. Nếu chính sách thực sự có nhiều biến thể, DSL có thể cần biểu diễn các phiên bản hoặc ngữ cảnh khác nhau.

Một bảng theo dõi điểm chưa rõ có thể dùng cấu trúc:

| Mã | Câu hỏi | Nguồn phát hiện | Người cần xác nhận | Trạng thái |
|---|---|---|---|---|
| Q-01 | Giá trị giỏ hàng tính trước hay sau giảm giá? | Hai giao dịch cho kết quả khác nhau | Chủ sở hữu chính sách khuyến mãi | Chờ xác nhận |
| Q-02 | Mã hết hạn theo múi giờ nào? | Tài liệu và hệ thống khác cách hiển thị | Nhóm vận hành chiến dịch | Đang xác minh |
| Q-03 | Thiếu hạng thành viên thì từ chối hay thử lại? | Phỏng vấn và nhật ký hệ thống | Chủ sở hữu trải nghiệm bán hàng | Chưa quyết định |

Các nội dung trong bảng chỉ là ví dụ minh họa. Trong dự án, trạng thái và người chịu trách nhiệm cần được cập nhật theo thực tế.

## 10. Bảo vệ dữ liệu và chất lượng bằng chứng

Ví dụ thực tế có thể chứa thông tin cá nhân, bí mật kinh doanh hoặc dữ liệu vận hành. Hãy chỉ thu thập những gì cần thiết cho câu hỏi nghiệp vụ.

Một số nguyên tắc thực hành:

- Xin phép trước khi ghi âm, chụp màn hình hoặc trích xuất hồ sơ theo quy định của tổ chức.
- Dùng mã ví dụ thay cho tên, email, số điện thoại, địa chỉ và mã định danh thật.
- Thay giá trị nhạy cảm bằng giá trị đại diện khi danh tính hoặc con số chính xác không cần thiết.
- Giữ lại đơn vị, quan hệ và điều kiện cần cho việc phân tích; không làm sai ý nghĩa khi ẩn danh.
- Giới hạn quyền truy cập và thời gian lưu giữ theo chính sách áp dụng.
- Ghi nguồn và mức độ xác nhận để người đọc biết bằng chứng đến từ đâu.
- Không đưa dữ liệu khách hàng hoặc bí mật nội bộ vào ví dụ công khai, tài liệu đào tạo bên ngoài hay kho mã không được phép.

Chất lượng của ví dụ phụ thuộc vào khả năng truy nguyên. Một ghi chép tốt cho biết nó được quan sát trực tiếp, trích từ hồ sơ hay chỉ được kể lại. Nếu người cung cấp không chắc chắn về thời điểm hoặc con số, hãy ghi rõ độ không chắc chắn thay vì tự điền giá trị.

## 11. Dùng ví dụ để định hình DSL

Chỉ sau khi hiểu các ví dụ và quy tắc, nhóm mới nên thử diễn đạt chúng bằng DSL. Mỗi khái niệm hoặc cấu trúc cú pháp cần có căn cứ từ công việc thật.

### 11.1 Tạo từ vựng từ ngôn ngữ nghiệp vụ

Tập hợp các danh từ và động từ xuất hiện lặp lại trong ví dụ. Xác nhận định nghĩa với người dùng và phân biệt từ đồng nghĩa, từ gần nghĩa hoặc từ chỉ có nghĩa trong một ngữ cảnh.

Ví dụ trong miền khuyến mãi:

- Chiến dịch.
- Điều kiện áp dụng.
- Mã ưu đãi.
- Quyền lợi.
- Thời hạn hiệu lực.
- Thứ tự ưu tiên.
- Kết hợp ưu đãi.

Không nên đưa một thuật ngữ vào DSL chỉ vì nó xuất hiện trong tên cột hoặc tên lớp của hệ thống hiện tại. Thuật ngữ cần có ý nghĩa ổn định đối với người sử dụng ngôn ngữ.

### 11.2 Xác định cấu trúc cần biểu diễn

Từ các ví dụ, xác định người dùng cần khai báo những phần nào:

- Đối tượng hoặc chính sách được mô tả.
- Điều kiện đầu vào.
- Hành động hoặc quyền lợi.
- Phạm vi và thời hạn.
- Thứ tự ưu tiên.
- Ngoại lệ và điều kiện kết hợp.

Nếu một thông tin không cần người dùng thay đổi hoặc không thuộc trách nhiệm của miền, có thể không cần xuất hiện trong DSL. Cần phân biệt cấu hình nghiệp vụ với chi tiết triển khai.

### 11.3 Kiểm tra ngữ nghĩa bằng ví dụ

Với mỗi cấu trúc dự kiến, thử diễn đạt ít nhất một trường hợp hợp lệ, một trường hợp không hợp lệ và một trường hợp biên. Hỏi chuyên gia xem kết quả diễn giải có đúng với ý định nghiệp vụ không.

Ví dụ, nếu DSL có điều kiện “giá trị giỏ hàng lớn hơn hoặc bằng 2.000.000”, cần xác định:

- Giá trị giỏ hàng có đơn vị tiền tệ nào?
- Giá trị được tính từ những thành phần nào?
- Hai triệu đúng bằng có đạt không?
- Giá trị bị thiếu được xử lý thế nào?
- Có làm tròn trước khi so sánh không?

Một biểu thức có thể phân tích cú pháp thành công nhưng vẫn sai ngữ nghĩa. Vì vậy, ví dụ phải kiểm tra cả ý nghĩa và kết quả, không chỉ hình thức câu lệnh.

### 11.4 Biến ví dụ đã xác nhận thành bộ trường hợp kiểm thử

Các ví dụ được người sở hữu nghiệp vụ xác nhận có thể trở thành bộ trường hợp tham chiếu (acceptance examples) để kiểm tra DSL và bộ diễn giải sau này. Với mỗi trường hợp, lưu:

- Mô tả đầu vào.
- Quy tắc hoặc phiên bản chính sách được áp dụng.
- Kết quả mong đợi.
- Lý do của kết quả.
- Người hoặc nguồn xác nhận.

Giữ riêng ví dụ nghiệp vụ đã xác nhận với ví dụ giả định dùng để khám phá. Khi chính sách thay đổi, cần biết trường hợp nào vẫn đúng, trường hợp nào cần phiên bản mới và trường hợp nào đã lỗi thời.

## 12. Sai lầm thường gặp khi thu thập ví dụ

### Chỉ hỏi ý kiến chung

Các câu trả lời như “quy trình rất đơn giản” hoặc “hệ thống tự xử lý” không cho thấy các bước và điều kiện thực tế.

**Cách cải thiện:** yêu cầu kể lại một trường hợp gần đây và lần theo từng hành động, quyết định, đầu vào và kết quả.

### Chỉ thu thập trường hợp thành công

Luồng thành công không cho biết điều kiện bị từ chối, giới hạn hoặc cách xử lý dữ liệu thiếu.

**Cách cải thiện:** chủ động tìm trường hợp biên, lỗi, hủy, sửa đổi và xung đột.

### Dẫn dắt câu trả lời

Hỏi “Hệ thống luôn chọn mức giảm cao nhất đúng không?” có thể khiến người tham gia đồng ý dù chính sách thực tế dùng thứ tự ưu tiên khác.

**Cách cải thiện:** hỏi mở “Khi hai ưu đãi cùng hợp lệ, hệ thống đã chọn thế nào trong trường hợp gần nhất?” rồi xác minh bằng hồ sơ.

### Nhầm hành vi hiện tại với chính sách đúng

Hệ thống có thể chứa lỗi hoặc quy trình tạm thời. Việc một thao tác đã xảy ra không chứng minh rằng nó được cho phép.

**Cách cải thiện:** đối chiếu hành vi với tài liệu có hiệu lực và người sở hữu quy tắc.

### Khái quát từ một trường hợp

Một giao dịch không đủ để chứng minh quy tắc áp dụng cho mọi khách hàng hoặc mọi thời điểm.

**Cách cải thiện:** tìm ví dụ tương phản, xác định phạm vi hiệu lực và ghi mức độ chắc chắn của kết luận.

### Ghi lại dữ liệu mà không ghi bối cảnh

Một con số hoặc trạng thái riêng lẻ không cho biết ai tạo ra nó, đơn vị nào được dùng hoặc quyết định nào phụ thuộc vào nó.

**Cách cải thiện:** luôn ghi mục tiêu, tác nhân, thời điểm, nguồn và trình tự xử lý.

### Vội thiết kế cú pháp

Nếu bắt đầu bằng từ khóa hoặc dấu câu trước khi hiểu khái niệm, DSL dễ phản ánh sở thích của người phát triển hơn là công việc của người dùng.

**Cách cải thiện:** dùng ví dụ để thống nhất thuật ngữ, quy tắc và kết quả trước; sau đó mới thử cách biểu diễn.

## 13. Quy trình làm việc đề xuất

Một vòng thu thập và phân tích có thể tổ chức như sau:

~~~text
Xác định câu hỏi cần tìm hiểu
          |
          v
Chọn nhóm người và nguồn bằng chứng
          |
          v
Thu thập trường hợp cụ thể
          |
          v
Ghi bối cảnh, đầu vào, quyết định, kết quả
          |
          v
Đối chiếu nguồn và xác nhận với chuyên gia
          |
          v
So sánh ví dụ, tìm mẫu chung và ngoại lệ
          |
          v
Ghi quy tắc, thuật ngữ và câu hỏi còn mở
          |
          v
Kiểm tra mô hình miền bằng các ví dụ
          |
          v
Thử biểu diễn bằng DSL và nhận phản hồi
~~~

Có thể lặp lại quy trình khi xuất hiện loại tình huống mới hoặc khi người dùng không thể diễn đạt một ví dụ bằng mô hình hiện tại. Một vòng lặp nên có câu hỏi cụ thể, người chịu trách nhiệm và kết quả cần xác nhận để tránh thu thập dữ liệu dàn trải.

## 14. Sản phẩm cần có sau hoạt động thu thập

Kết thúc một đợt khám phá, nhóm nên có các đầu ra có thể sử dụng lại:

| Đầu ra | Nội dung |
|---|---|
| Danh mục ví dụ | Các tình huống được mã hóa, phân loại và ghi nguồn |
| Hồ sơ tình huống | Bối cảnh, tác nhân, đầu vào, diễn biến, quy tắc và kết quả |
| Ma trận bao phủ | Các nhóm điển hình, biên, ngoại lệ, xung đột và liên miền đã có ví dụ |
| Bảng thuật ngữ | Từ ngữ nghiệp vụ, định nghĩa và ngữ cảnh sử dụng |
| Danh sách quy tắc | Điều kiện đã xác nhận, nguồn và phạm vi hiệu lực |
| Danh sách câu hỏi mở | Mâu thuẫn, giả thuyết và quyết định đang chờ |
| Bộ ví dụ tham chiếu | Các trường hợp đã xác nhận để kiểm tra mô hình hoặc DSL |
| Ghi chú nguồn dữ liệu | Nguồn, thời điểm, mức độ tin cậy và giới hạn sử dụng |

Các đầu ra này cần liên kết được với nhau. Chẳng hạn, một quy tắc nên trỏ đến những ví dụ chứng minh hoặc làm rõ quy tắc đó; một câu hỏi mở nên cho biết ví dụ nào đã làm phát sinh câu hỏi.

## 15. Câu hỏi tự kiểm tra

1. Vì sao một lời mô tả chung về quy trình chưa đủ làm ví dụ thực tế?
2. Phân biệt ví dụ quan sát được, quy tắc đã xác nhận và giả thuyết.
3. Vì sao cần thu thập cả trường hợp biên, ngoại lệ và xung đột?
4. Nêu ưu điểm và giới hạn của phỏng vấn, quan sát, tài liệu và nhật ký hệ thống.
5. Khi phỏng vấn, vì sao nên yêu cầu người tham gia kể lại một trường hợp gần đây?
6. Một hồ sơ ví dụ cần lưu những thông tin nào để có thể kiểm chứng?
7. Nếu hành vi hệ thống khác với tài liệu chính sách, cần xử lý thông tin đó thế nào?
8. Vì sao không nên khái quát quy tắc từ một giao dịch duy nhất?
9. Làm thế nào để bảo vệ dữ liệu nhạy cảm mà vẫn giữ đủ ý nghĩa nghiệp vụ?
10. Ví dụ đã xác nhận có thể hỗ trợ thiết kế và kiểm thử DSL ra sao?

Khi thực hành, hãy chọn một quy trình quen thuộc, thu thập ít nhất một trường hợp điển hình và một trường hợp ngoại lệ, rồi ghi rõ nguồn, bối cảnh, quyết định, kết quả và điểm chưa được xác nhận. Mục tiêu là tạo ra bằng chứng đủ rõ để người nghiệp vụ và người phát triển cùng kiểm tra cách hiểu về miền.

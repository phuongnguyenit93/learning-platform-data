# Chuyển yêu cầu mơ hồ thành hợp đồng và trường hợp kiểm tra

Một yêu cầu như **“Khách VIP được giảm 10% khi đơn hàng đủ điều kiện”** nghe có vẻ rõ ràng. Nhưng trước khi viết code, nhóm phát triển vẫn cần trả lời: “đơn hàng” được tính trước hay sau phí giao hàng? “Đủ điều kiện” bắt đầu từ đúng ngưỡng hay phải lớn hơn ngưỡng? Giảm giá có áp dụng cho thuế không? Nếu số tiền lẻ theo đơn vị tiền tệ thì làm tròn thế nào? Ai xác nhận khách là VIP? Có cộng dồn coupon không?

Nếu mỗi người tự hiểu một cách, implementation có thể biên dịch, test vẫn xanh, nhưng các thành phần trong hệ thống lại cho ra kết quả khác nhau. Khi lỗi xuất hiện, nhóm khó biết đó là lỗi code hay do yêu cầu chưa từng được thống nhất.

Trong chương **Thực hành** của module **CODE_QUALITY_FUNDAMENTALS**, bài này hướng dẫn một quy trình biến câu chữ mơ hồ thành **hợp đồng có thể kiểm chứng**, sau đó suy ra các **trường hợp kiểm tra** và hiện thực bằng Java. Mục tiêu là luyện cách đặt câu hỏi, ghi nhận quyết định, xác định oracle và viết test có ý nghĩa để mã nguồn trở nên **đáng tin cậy, dễ hiểu và dễ thay đổi**.

> Đừng bắt đầu bằng cách đoán ý nghĩa của một câu yêu cầu. Hãy tách những từ chưa rõ thành câu hỏi, xác nhận quyết định, rồi mới viết điều kiện và test.

## 1. Bài thực hành: một yêu cầu chưa đủ rõ

Giả sử nhóm sản phẩm gửi yêu cầu:

> Khách hàng VIP được giảm 10% cho đơn hàng đủ điều kiện. Không áp dụng ưu đãi cho đơn không hợp lệ. Hệ thống phải tính chính xác số tiền cuối cùng và không được để khách hàng bị tính sai khi đặt lại yêu cầu.

Đây là **đầu vào ban đầu**, chưa phải hợp đồng để triển khai. Câu chữ chứa nhiều khái niệm cần làm rõ:

- **VIP:** ai xác định trạng thái và tại thời điểm nào?
- **10%:** tính trên cơ sở tiền nào?
- **Đủ điều kiện:** có ngưỡng tối thiểu, giới hạn tối đa hoặc loại hàng bị loại trừ không?
- **Đơn không hợp lệ:** không hợp lệ ở bước nào, trả lỗi gì, có tạo dữ liệu không?
- **Số tiền cuối cùng:** gồm thuế, vận chuyển, phụ phí và coupon hay không?
- **Đặt lại yêu cầu:** retry do timeout, double-click hay gửi cùng một request ID?

Nếu bỏ qua những điểm này, code có thể phải chứa các giả định không được ai phê duyệt.

### 1.1. Vì sao câu chữ tự nhiên chưa phải hợp đồng?

Ngôn ngữ tự nhiên phù hợp để truyền đạt mục tiêu, nhưng một số từ có thể mang nhiều nghĩa:

| Cụm từ | Những cách hiểu có thể khác nhau |
| --- | --- |
| **Từ 200.000 đồng** | >= 200.000 hay > 200.000? |
| **Đơn hàng** | Tổng hàng hóa, tổng sau giảm giá hay số tiền phải thanh toán? |
| **Khách VIP** | Trạng thái hiện tại, trạng thái lúc tạo đơn hay trạng thái lúc thanh toán? |
| **Giảm 10%** | Làm tròn xuống, làm tròn gần nhất hay giữ phần lẻ? |
| **Không áp dụng** | Trả mức giảm bằng 0, từ chối đơn hay báo lỗi? |
| **Đặt lại yêu cầu** | Có tạo đơn mới, trả lại kết quả cũ hay gửi lại tác dụng phụ? |
| **Chính xác** | Đúng theo công thức nào, đơn vị nào và mức sai số nào? |

Một yêu cầu chỉ trở nên đủ rõ khi người thực hiện và người xác nhận cùng hiểu **đầu vào, điều kiện, kết quả, lỗi, trạng thái và giới hạn** theo cùng một cách.

## 2. Bước đầu tiên: bóc tách điều đã biết và điều chưa biết

Đọc yêu cầu một lượt và phân loại từng phát biểu:

1. **Thông tin đã xác định:** nội dung được nêu rõ, có thể trích dẫn.
2. **Thông tin thiếu:** yêu cầu chưa nói tới.
3. **Thông tin mơ hồ:** có nhiều cách diễn giải.
4. **Giả định tạm thời:** điều nhóm đang dùng để tiếp tục phân tích, chưa được phê duyệt.
5. **Quyết định đã xác nhận:** cách hiểu đã được người có thẩm quyền thống nhất.

Không nên biến giả định thành sự thật bằng cách đưa nó thẳng vào tên biến hoặc comment.

### 2.1. Lập bảng câu hỏi làm rõ

Với yêu cầu giảm giá VIP, bảng đầu tiên có thể như sau:

| Chủ đề | Câu hỏi cần làm rõ | Vì sao quan trọng |
| --- | --- | --- |
| Đối tượng | VIP được xác định từ nguồn nào? | Tránh client tự gửi vip=true |
| Thời điểm | Trạng thái VIP được chụp lúc tạo báo giá hay lúc thanh toán? | Tránh cùng đơn có kết quả thay đổi giữa các bước |
| Cơ sở tính | 10% tính trên tiền hàng, tiền sau coupon hay tổng thanh toán? | Tránh các module tính khác nhau |
| Ngưỡng | “Đủ điều kiện” có ngưỡng tối thiểu không? Biên có bao gồm không? | Xác định điều kiện so sánh |
| Phạm vi | Thuế, phí giao hàng, phụ phí có được giảm không? | Xác định số tiền chịu giảm |
| Coupon | Có được cộng dồn không? Nếu có thì thứ tự ra sao? | Thứ tự giảm có thể làm đổi kết quả |
| Làm tròn | Phần lẻ của VND xử lý thế nào? | Tránh sai khác giữa dịch vụ |
| Đầu vào lỗi | Số tiền âm, null hoặc thiếu dữ liệu được xử lý thế nào? | Ngăn kết quả vô nghĩa |
| Vòng đời | Đơn hủy hoặc hết hạn xử lý ưu đãi thế nào? | Tránh giữ trạng thái hoặc thu tiền sai |
| Retry | Gửi lại cùng yêu cầu có tạo đơn hoặc tính ưu đãi lần nữa không? | Bảo vệ tính idempotent |

### 2.2. Xếp câu hỏi theo mức độ ảnh hưởng

Không phải mọi câu hỏi đều cần giải quyết cùng lúc. Ưu tiên câu hỏi có thể làm đổi:

- Số tiền khách phải trả.
- Quyền được hưởng ưu đãi.
- Trạng thái hoặc tác dụng phụ của đơn hàng.
- Tính tương thích với client và dữ liệu hiện tại.
- Cách hệ thống xử lý retry hoặc phục hồi lỗi.

Những điểm như tên hiển thị trong giao diện có thể được xác nhận ở giai đoạn khác nếu không ảnh hưởng hợp đồng tính tiền.

### 2.3. Ghi câu hỏi sao cho người trả lời có thể quyết định

Một câu hỏi tốt nêu rõ các lựa chọn và hệ quả:

> Ngưỡng tối thiểu được áp dụng trên tổng tiền hàng trước giảm giá, chưa gồm vận chuyển và thuế, hay trên số tiền sau các khoản này? Nếu dùng tổng sau giảm giá, coupon có thể làm một đơn vượt ngưỡng trở thành không đủ điều kiện.

Câu hỏi như “Ngưỡng tính thế nào?” quá chung. Người trả lời có thể không nhận ra hệ quả của các lựa chọn.

Không nên gửi một danh sách dài những câu hỏi kỹ thuật mà không liên hệ tới hành vi sản phẩm. Hãy diễn đạt bằng tình huống cụ thể và yêu cầu người chịu trách nhiệm xác nhận.

## 3. Từ câu hỏi sang quyết định có thể truy vết

Trong bài thực hành, ta giả định nhóm sản phẩm và nghiệp vụ đã xác nhận các quyết định sau. Đây là **hợp đồng giả định dùng để học**, không phải chính sách thật của một cửa hàng.

### 3.1. Bảng quyết định

| Mã | Quyết định đã xác nhận | Lý do |
| --- | --- | --- |
| D1 | VIP được xác định từ dữ liệu membership do server tin cậy cung cấp | Không cho client tự nâng quyền |
| D2 | Trạng thái VIP được chụp tại thời điểm tạo báo giá | Một báo giá có kết quả ổn định |
| D3 | Ngưỡng tối thiểu là **200.000 VND**, tính trên tổng tiền hàng trước giảm giá | Không tính phí giao hàng và thuế vào ngưỡng |
| D4 | Ngưỡng bao gồm điểm bằng: subtotal >= 200.000 | “Đạt ít nhất” có nghĩa bao gồm biên |
| D5 | Giảm 10% trên tổng tiền hàng nếu khách VIP và đạt ngưỡng | Phạm vi giảm được xác định rõ |
| D6 | Không giảm phí giao hàng hoặc thuế | Hai khoản được tính riêng |
| D7 | Coupon không cộng dồn với ưu đãi VIP trong phiên bản này | Tránh thứ tự áp dụng chưa được xác định |
| D8 | Tiền là số nguyên VND; phần lẻ sau phép tính được làm tròn xuống tới VND nguyên | Cùng một quy tắc ở mọi module |
| D9 | Subtotal âm là đầu vào không hợp lệ; subtotal bằng 0 được chấp nhận và không có giảm giá | Quy tắc đầu vào rõ ràng |
| D10 | Nếu không lấy được trạng thái membership đáng tin cậy, không tự coi khách là VIP hoặc thường; báo lỗi để xử lý | Tránh cấp sai ưu đãi do lỗi hạ tầng |
| D11 | Việc tính ưu đãi là phép tính thuần, không tạo đơn và không thu tiền | Tách chính sách khỏi điều phối |
| D12 | Khi đơn được tạo, báo giá và trạng thái VIP dùng để tính được lưu cùng đơn; retry cùng idempotency key không tạo đơn hoặc tác dụng phụ trùng | Kết quả có thể truy vết và gọi lại an toàn |

### 3.2. Phân biệt quyết định nghiệp vụ và quyết định kỹ thuật

| Loại | Ví dụ | Ai cần xác nhận? |
| --- | --- | --- |
| Nghiệp vụ | Ngưỡng 200.000 VND có bao gồm điểm bằng? | Product owner/người phụ trách chính sách |
| Nghiệp vụ | Có cộng dồn coupon không? | Chủ sở hữu chương trình ưu đãi |
| Dữ liệu | VIP được snapshot tại thời điểm nào? | Nghiệp vụ và kiến trúc dữ liệu |
| Kỹ thuật | Dùng long để biểu diễn VND nguyên | Nhóm phát triển, theo hợp đồng tiền tệ |
| Kỹ thuật | Ném exception nào cho subtotal âm? | Thiết kế API và quy ước dự án |
| Vận hành | Membership service timeout thì trả lỗi hay dùng snapshot gần nhất? | Product, platform và vận hành |

Không nên để quyết định kỹ thuật tự thay đổi chính sách sản phẩm. Ví dụ, chọn >= hay > không phải sở thích lập trình viên nếu nó làm thay đổi quyền lợi khách hàng.

### 3.3. Ghi nhận nguồn xác nhận và phiên bản

Trong dự án thật, quyết định nên gắn với:

- Mã yêu cầu, ticket hoặc tài liệu được phê duyệt.
- Người hoặc vai trò xác nhận.
- Ngày có hiệu lực và phiên bản chính sách.
- Phạm vi module/API áp dụng.
- Quyết định thay thế nếu chính sách thay đổi.

Đặc biệt với đơn hàng lịch sử, không nên tính lại bằng chính sách hiện tại nếu hợp đồng yêu cầu giữ chính sách tại thời điểm mua. Lưu **policy version** hoặc dữ liệu báo giá đã chốt giúp giải thích kết quả sau này.

## 4. Viết hợp đồng trước khi viết code

Hợp đồng mô tả rõ một thành phần nhận gì, cần điều kiện nào, trả gì và bảo đảm điều gì sau khi thực hiện.

### 4.1. Hợp đồng của phép tính ưu đãi

**Tên thành phần:** VipDiscountPolicy.

**Mục đích:** tính số tiền giảm VIP trên tổng tiền hàng trước giảm giá.

**Đầu vào:**

- merchandiseSubtotalVnd: tổng tiền hàng, số nguyên VND, không âm.
- vip: trạng thái VIP đáng tin cậy đã được xác định và snapshot ở tầng gọi.

**Tiền điều kiện:**

- Subtotal không âm.
- Trạng thái VIP đã có kết quả đáng tin cậy; tầng gọi không được tự mặc định khi membership service lỗi.

**Hậu điều kiện:**

- Nếu không VIP hoặc subtotal nhỏ hơn 200.000 VND, discount bằng 0.
- Nếu VIP và subtotal từ 200.000 VND trở lên, discount bằng floor(subtotal * 10 / 100).
- Discount không âm và không vượt subtotal.
- Kết quả tính bằng VND nguyên.

**Tác dụng phụ:**

- Không truy cập DB, network, cache hoặc clock.
- Không thay đổi dữ liệu đầu vào.
- Không lưu trạng thái giữa các lần gọi.

**Lỗi:**

- Subtotal âm gây IllegalArgumentException.
- Phép tính không được âm thầm tràn số.
- Lỗi lấy membership được xử lý ở tầng cung cấp dữ liệu, không được biến thành một kết quả VIP tùy tiện.

### 4.2. Công thức

Gọi:

- \(S\): tổng tiền hàng trước giảm giá, đơn vị VND.
- \(V\): trạng thái VIP (true hoặc false).
- \(T = 200.000\): ngưỡng tối thiểu.
- \(D\): số tiền giảm.

Khi đầu vào hợp lệ:

\[
D(S,V)=
\begin{cases}
0 & \text{nếu } V = false\\
0 & \text{nếu } S < T\\
\lfloor S/10 \rfloor & \text{nếu } V = true \land S \ge T
\end{cases}
\]

Phép chia cho 10 tương đương 10% và làm tròn xuống vì số tiền được biểu diễn bằng VND nguyên, subtotal không âm. Ví dụ, 200.019 VND giảm 20.001 VND; phần 0,9 VND bị bỏ theo quyết định D8.

### 4.3. Bất biến và điều không thuộc hợp đồng

**Bất biến:**

- 0 <= discountVnd <= merchandiseSubtotalVnd.
- Cùng đầu vào và cùng phiên bản chính sách luôn cho cùng kết quả.
- Tính toán không phụ thuộc thứ tự gọi trước đó.

**Ngoài phạm vi của thành phần này:**

- Xác thực người dùng có quyền đặt đơn hay không.
- Tra cứu trạng thái VIP từ dịch vụ membership.
- Tính thuế, phí giao hàng và coupon.
- Tạo đơn, thu tiền, hoàn tiền hoặc gửi thông báo.
- Xử lý retry/idempotency của workflow tạo đơn.

Việc ghi rõ ngoài phạm vi giúp tránh một hàm tính giảm giá bị biến thành nơi điều phối toàn bộ checkout.

## 5. Chuyển hợp đồng thành bảng quyết định

Trước khi viết test, hãy biểu diễn các điều kiện bằng một bảng. Bảng giúp nhìn thấy mọi tổ hợp quan trọng và làm rõ nhánh nào được áp dụng.

### 5.1. Bảng quyết định cho ưu đãi VIP

| VIP? | Subtotal tiền hàng | Kết quả |
| --- | --- | --- |
| Không | Bất kỳ giá trị hợp lệ nào | Giảm 0 VND |
| Có | Nhỏ hơn 200.000 VND | Giảm 0 VND |
| Có | Bằng hoặc lớn hơn 200.000 VND | Giảm 10%, làm tròn xuống VND nguyên |
| Bất kỳ | Subtotal âm | Từ chối đầu vào |
| Chưa xác định do membership lỗi | Không tính | Báo lỗi phụ thuộc, không tự gán trạng thái VIP |

Bảng này cũng chỉ ra một điểm thiết kế: hàm tính ưu đãi chỉ nhận **trạng thái VIP đã xác định**. Nó không nên tự gọi membership service rồi tự quyết định cách xử lý timeout.

### 5.2. Decision table dạng điều kiện

| Điều kiện | R1 | R2 | R3 | R4 |
| --- | --- | --- | --- | --- |
| Subtotal hợp lệ? | Có | Có | Có | Không |
| VIP? | Không | Có | Có | Không cần xét |
| Subtotal >= 200.000? | Không cần xét | Không | Có | Không cần xét |
| Hành động | Giảm 0 | Giảm 0 | Giảm 10% | Báo lỗi input |

Khi một điều kiện không ảnh hưởng kết quả của rule hiện tại, có thể ghi **không cần xét**. Ví dụ, khách không VIP thì subtotal có đạt ngưỡng hay không cũng không làm thay đổi mức giảm VIP. Điều này giúp tránh tạo quá nhiều trường hợp lặp.

### 5.3. Tách điều kiện hợp lệ khỏi điều kiện hưởng ưu đãi

Hai câu hỏi này khác nhau:

- **Đầu vào có hợp lệ không?** Subtotal âm là không hợp lệ.
- **Đầu vào hợp lệ có được giảm giá không?** Khách không VIP hoặc chưa đạt ngưỡng vẫn có thể đặt đơn, chỉ không được giảm VIP.

Nếu trộn hai khái niệm, implementation có thể từ chối một đơn bình thường chỉ vì khách không đủ điều kiện ưu đãi. Đây là lỗi ngữ nghĩa thường gặp khi yêu cầu viết “không áp dụng ưu đãi cho đơn không đủ điều kiện”.

## 6. Từ bảng quyết định sang phân hoạch và giá trị biên

Mỗi hàng trong decision table gợi ý một nhóm đầu vào. Sau đó chọn đại diện và các điểm sát ranh giới để kiểm tra.

### 6.1. Các lớp tương đương

| Thuộc tính | Lớp | Giá trị đại diện |
| --- | --- | ---: |
| Trạng thái VIP | Không VIP | false |
| Trạng thái VIP | VIP | true |
| Subtotal | Âm, không hợp lệ | -1 |
| Subtotal | Bằng 0 | 0 |
| Subtotal | Dưới ngưỡng | 199.999 |
| Subtotal | Đúng ngưỡng | 200.000 |
| Subtotal | Trên ngưỡng | 200.001 |
| Phần lẻ sau 10% | Chia hết cho 10 | 200.010 |
| Phần lẻ sau 10% | Có phần dư | 200.019 |
| Giới hạn kiểu | Giá trị lớn nhất của long | Long.MAX_VALUE |

Không cần kiểm tra mọi số trong miền. Cần chọn các đại diện có thể làm đổi nhánh, đổi kết quả hoặc bộc lộ lỗi số học.

### 6.2. Giá trị ngay dưới, bằng và ngay trên ngưỡng

~~~text
199.999 VND       200.000 VND       200.001 VND
     |                  |                  |
     v                  v                  v
 Không giảm         Bắt đầu giảm        Có giảm
~~~

Giá trị 200.000 là điểm quyết định giữa hai nhánh. Nếu implementation vô tình dùng **>** thay vì **>=**, chỉ test 250.000 và 100.000 có thể vẫn xanh; test đúng biên mới làm lộ lỗi.

### 6.3. Kiểm tra làm tròn

Vì hợp đồng chọn làm tròn xuống VND nguyên, cần có ít nhất:

| Subtotal | 10% chính xác | Discount VND |
| ---: | ---: | ---: |
| 200.000 | 20.000 | 20.000 |
| 200.010 | 20.001 | 20.001 |
| 200.019 | 20.001,9 | 20.001 |
| 200.099 | 20.009,9 | 20.009 |

Các ví dụ có phần lẻ giúp xác minh implementation không dùng cách làm tròn gần nhất ngoài hợp đồng.

### 6.4. Kiểm tra miền số và phép toán

Trong Java, phép nhân số nguyên có thể tràn mà không tự ném exception. Nếu viết:

~~~java
long discount = subtotal * 10 / 100;
~~~

giá trị trung gian có thể tràn trước khi chia. Với chính sách 10% trên subtotal không âm, dùng **subtotal / 10** cho kết quả làm tròn xuống và tránh phép nhân trung gian.

Đây là một lựa chọn dựa trên công thức cụ thể. Nếu tỷ lệ thay đổi hoặc có phần trăm khác, cần xem lại cách tính, dùng **Math.multiplyExact** hoặc **BigDecimal** theo hợp đồng và kiểm thử phù hợp. Không nên thay kiểu số chỉ vì nghĩ rằng BigDecimal luôn cần thiết.

## 7. Lập danh sách trường hợp kiểm tra

Một test case tốt ghi rõ **đầu vào, điều kiện, kết quả mong đợi và mục đích**. Không nên chỉ ghi “test VIP” vì người thực hiện không biết cần xác minh điều gì.

### 7.1. Test case cho hàm tính ưu đãi

| ID | VIP | Subtotal VND | Kết quả mong đợi | Mục đích |
| --- | --- | ---: | ---: | --- |
| TC01 | false | 200.000 | 0 | Khách thường không được giảm VIP |
| TC02 | true | 0 | 0 | Subtotal 0 không đạt ngưỡng |
| TC03 | true | 199.999 | 0 | Ngay dưới ngưỡng |
| TC04 | true | 200.000 | 20.000 | Đúng ngưỡng, bao gồm biên |
| TC05 | true | 200.001 | 20.000 | Ngay trên ngưỡng, làm tròn xuống |
| TC06 | true | 200.010 | 20.001 | Tỷ lệ 10% chia hết |
| TC07 | true | 200.019 | 20.001 | Có phần lẻ, làm tròn xuống |
| TC08 | true | -1 | IllegalArgumentException | Subtotal âm bị từ chối |
| TC09 | false | Long.MAX_VALUE | 0 | Không VIP, giá trị lớn không gây phép nhân |
| TC10 | true | Long.MAX_VALUE | Long.MAX_VALUE / 10 | Không tràn phép tính 10% |

### 7.2. Test case cho tầng lấy trạng thái VIP

Hàm thuần không kiểm tra nguồn membership. Một thành phần điều phối cần có test riêng:

| ID | Membership service | Kết quả mong đợi |
| --- | --- | --- |
| TC11 | Trả về VIP | Dùng trạng thái VIP snapshot để tính |
| TC12 | Trả về không VIP | Không áp dụng giảm VIP |
| TC13 | Timeout | Báo lỗi phụ thuộc theo hợp đồng, không tự mặc định |
| TC14 | Trả về dữ liệu không hợp lệ | Từ chối hoặc xử lý lỗi theo hợp đồng dữ liệu |
| TC15 | Trạng thái VIP đổi sau khi báo giá được tạo | Báo giá đã snapshot không tự đổi nếu hợp đồng yêu cầu cố định |

### 7.3. Test case cho workflow tạo đơn và retry

| ID | Tình huống | Điều cần xác minh |
| --- | --- | --- |
| TC16 | Đơn hợp lệ, lần gọi đầu | Lưu một báo giá và tạo một đơn |
| TC17 | Đơn invalid | Không tạo đơn hoặc thu tiền |
| TC18 | Retry cùng idempotency key, cùng payload | Trả kết quả đã có theo hợp đồng, không tạo side effect trùng |
| TC19 | Cùng key nhưng payload khác | Từ chối xung đột hoặc xử lý theo chính sách đã công bố |
| TC20 | Đơn bị hủy trước khi thanh toán | Không capture tiền |
| TC21 | Timeout khi thanh toán, kết quả chưa rõ | Chuyển trạng thái phù hợp và tra cứu/đối soát, không tự kết luận thất bại |

Những test case này không thuộc riêng hàm tính 10%. Chúng xác minh **workflow** và cần được đặt ở đúng tầng test.

### 7.4. Xác định mức kiểm thử

| Phạm vi | Loại test phù hợp | Ví dụ |
| --- | --- | --- |
| Công thức giảm giá | Unit test | TC01–TC10 |
| Tra cứu membership | Unit test với fake hoặc contract test | TC11–TC15 |
| Tạo đơn, lưu báo giá | Integration/service test | TC16–TC17 |
| Idempotency và retry | Integration test, test đồng thời có điều phối | TC18–TC19 |
| Thanh toán và hủy | Contract/integration test với gateway sandbox hoặc fake phù hợp | TC20–TC21 |

Đặt test ở đúng tầng giúp test nhanh và có ý nghĩa. Không cần khởi động toàn bộ ứng dụng Spring chỉ để kiểm tra một phép chia cho 10.

## 8. Hiện thực hợp đồng bằng Java

Khi hợp đồng và test case đã rõ, code có thể ngắn hơn phần phân tích. Đây là điều bình thường: **độ khó nằm ở việc xác định hành vi đúng**, không phải ở số dòng implementation.

### 8.1. Cài đặt chính sách thuần

Tệp **VipDiscountPolicy.java**, dùng Java 17 hoặc mới hơn:

~~~java
public final class VipDiscountPolicy {
    public static final long MIN_SUBTOTAL_VND = 200_000L;

    private VipDiscountPolicy() {
    }

    /**
     * Computes the VIP discount on merchandise subtotal in whole VND.
     *
     * @param merchandiseSubtotalVnd non-negative merchandise subtotal
     * @param vip trusted VIP status snapshot for this quote
     * @return discount in whole VND, rounded down
     * @throws IllegalArgumentException if subtotal is negative
     */
    public static long discountVnd(
            long merchandiseSubtotalVnd,
            boolean vip) {
        if (merchandiseSubtotalVnd < 0) {
            throw new IllegalArgumentException(
                    "Merchandise subtotal must not be negative");
        }

        if (!vip || merchandiseSubtotalVnd < MIN_SUBTOTAL_VND) {
            return 0L;
        }

        // 10% rounded down; division avoids an overflowing * 10 intermediate.
        return merchandiseSubtotalVnd / 10L;
    }
}
~~~

Implementation giữ các quyết định đã ghi:

- Subtotal âm bị từ chối.
- Khách không VIP hoặc dưới ngưỡng nhận mức giảm 0.
- Đúng ngưỡng được áp dụng vì điều kiện kiểm tra là **subtotal < MIN_SUBTOTAL_VND** để trả về 0.
- Chia nguyên cho 10 thực hiện quy tắc làm tròn xuống.
- Phương thức không gọi DB hoặc membership service, không giữ trạng thái và không tạo side effect.

### 8.2. Tại sao không nhận VIP từ request client?

Nếu endpoint nhận JSON như:

~~~json
{
  "merchandiseSubtotalVnd": 500000,
  "vip": true
}
~~~

thì người dùng có thể tự sửa trường **vip** và yêu cầu mức giảm không thuộc quyền của họ. API công khai nên nhận dữ liệu người dùng được phép cung cấp, còn trạng thái membership phải được xác định từ nguồn server tin cậy.

Ví dụ tầng điều phối:

~~~java
public final class QuoteService {
    private final MembershipService membershipService;

    public QuoteService(MembershipService membershipService) {
        this.membershipService = membershipService;
    }

    public long calculateVipDiscount(
            CustomerId customerId,
            long merchandiseSubtotalVnd) {
        boolean vip = membershipService.isVip(customerId);
        return VipDiscountPolicy.discountVnd(
                merchandiseSubtotalVnd, vip);
    }
}
~~~

**MembershipService** và **CustomerId** là kiểu giả định của ví dụ. Nếu membership service timeout, lời gọi ném lỗi và không có kết quả tính; tầng này không được tự đổi lỗi thành **false** nếu chưa có quyết định cho phép fallback. Trong hệ thống thật, trạng thái VIP có thể cần snapshot và lưu cùng báo giá để lần đọc sau không phụ thuộc trạng thái membership hiện tại.

### 8.3. Tách phép tính khỏi vòng đời đơn hàng

Hàm **discountVnd** chỉ trả số tiền giảm. Nó không quyết định:

- Khi nào tạo đơn.
- Có lưu báo giá hay không.
- Khi nào capture payment.
- Đơn hủy thì hoàn tiền ra sao.
- Retry có trả lại kết quả cũ hay tạo đơn mới.

Những quyết định này thuộc hợp đồng của workflow. Giữ ranh giới rõ giúp test chính sách độc lập và tránh một hàm nhỏ trở thành nơi chứa toàn bộ trạng thái checkout.

## 9. Viết JUnit 5 từ test case

Test cần kiểm tra **kết quả theo hợp đồng**, không chỉ kiểm tra phương thức chạy qua mà không ném lỗi.

### 9.1. Test các lớp đầu vào và ngưỡng

Tệp **VipDiscountPolicyTest.java**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class VipDiscountPolicyTest {
    @ParameterizedTest
    @CsvSource({
        "false, 0, 0",
        "false, 200000, 0",
        "false, 500000, 0",
        "true, 0, 0",
        "true, 199999, 0",
        "true, 200000, 20000",
        "true, 200001, 20000",
        "true, 200010, 20001",
        "true, 200019, 20001"
    })
    void calculatesDiscountForEquivalenceClassesAndBoundaries(
            boolean vip,
            long subtotalVnd,
            long expectedDiscountVnd) {
        assertEquals(
                expectedDiscountVnd,
                VipDiscountPolicy.discountVnd(subtotalVnd, vip));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(
                IllegalArgumentException.class,
                () -> VipDiscountPolicy.discountVnd(-1L, true));
    }

    @Test
    void handlesMaximumLongWithoutOverflow() {
        assertEquals(
                Long.MAX_VALUE / 10L,
                VipDiscountPolicy.discountVnd(Long.MAX_VALUE, true));
    }
}
~~~

JUnit Jupiter và Jupiter Params cần được khai báo trong dependency kiểm thử của dự án; chúng không nằm trong JDK. Test parameterized giúp kiểm tra nhiều lớp dữ liệu với cùng một oracle mà không sao chép phần assertion.

### 9.2. Kiểm tra bất biến

Ngoài các giá trị ví dụ, có thể kiểm tra các tính chất phải đúng với nhiều đầu vào:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VipDiscountPolicyInvariantTest {
    @org.junit.jupiter.api.Test
    void discountIsNeverNegativeOrGreaterThanSubtotal() {
        long[] values = {
            0L, 1L, 199_999L, 200_000L,
            200_019L, 1_000_000L, Long.MAX_VALUE
        };

        for (long subtotal : values) {
            long discount =
                    VipDiscountPolicy.discountVnd(subtotal, true);

            assertTrue(discount >= 0L);
            assertTrue(discount <= subtotal);
        }
    }

    @org.junit.jupiter.api.Test
    void nonVipNeverReceivesVipDiscount() {
        long[] values = {
            0L, 200_000L, 500_000L, Long.MAX_VALUE
        };

        for (long subtotal : values) {
            assertEquals(
                    0L,
                    VipDiscountPolicy.discountVnd(subtotal, false));
        }
    }
}
~~~

Các test tính chất không thay thế test biên cụ thể. Chúng giúp kiểm tra thêm những bất biến tổng quát, trong khi test ngưỡng xác nhận chính sách tại điểm dễ nhầm.

## 10. Mở rộng hợp đồng sang workflow tạo đơn

Một chính sách giảm giá thuần chỉ trả một con số. Khi gắn vào quy trình tạo đơn, cần xác định thêm **ai được đặt đơn, báo giá được lưu thế nào, retry có an toàn không và khi nào phát sinh thanh toán**.

### 10.1. Hợp đồng của thao tác tạo đơn

Ví dụ hợp đồng ở mức nghiệp vụ:

**Đầu vào:**

- Khách hàng đã được xác thực.
- Danh sách dòng hàng hợp lệ.
- Idempotency key duy nhất trong phạm vi khách hàng hoặc phạm vi được công bố.

**Xử lý:**

1. Kiểm tra quyền và dữ liệu đơn hàng.
2. Lấy trạng thái VIP từ nguồn server tin cậy.
3. Tạo báo giá theo phiên bản chính sách có hiệu lực.
4. Lưu báo giá, trạng thái VIP snapshot và policy version cùng đơn.
5. Dùng idempotency key để bảo đảm retry không tạo đơn trùng.
6. Chỉ thực hiện thanh toán theo trạng thái và hợp đồng thanh toán riêng.

**Hậu điều kiện khi thành công:**

- Có một định danh đơn hàng ổn định.
- Báo giá đã lưu có thể giải thích được từ dữ liệu và phiên bản chính sách.
- Kết quả trả cho caller phù hợp với đơn đã tạo.

**Hành vi khi lỗi:**

- Dữ liệu không hợp lệ không tạo đơn hoặc thu tiền.
- Membership service lỗi không bị hiểu nhầm thành trạng thái VIP mặc định.
- Retry cùng key và cùng payload trả lại kết quả đã có theo hợp đồng.
- Cùng key nhưng payload khác được phát hiện và xử lý rõ ràng.
- Timeout thanh toán không bị coi là bằng chứng chắc chắn rằng chưa thu tiền.

Đây là một hợp đồng minh họa. Hệ thống thực có thể lưu đơn nháp trước khi thanh toán hoặc dùng quy trình bất đồng bộ. Điều quan trọng là **trạng thái và side effect phải được mô tả**, không suy đoán từ tên phương thức.

### 10.2. Idempotency không chỉ là kiểm tra key có tồn tại

Một hợp đồng idempotency cần trả lời:

- Key duy nhất trong phạm vi nào: khách hàng, endpoint hay toàn hệ thống?
- Key được giữ trong bao lâu?
- Cùng key nhưng payload khác thì sao?
- Nếu request đầu đang xử lý, request thứ hai chờ, nhận trạng thái pending hay lỗi xung đột?
- Nếu lần đầu timeout sau khi DB đã commit, retry lấy lại kết quả nào?
- Có cần chống hai request cùng key chạy đồng thời không?

Một bảng quyết định đơn giản:

| Key | Payload | Trạng thái lần trước | Hành vi mong đợi |
| --- | --- | --- | --- |
| Mới | Hợp lệ | Chưa có | Tiếp nhận và tạo một đơn |
| Đã có | Giống | Đã hoàn tất | Trả lại kết quả đã lưu |
| Đã có | Giống | Đang xử lý | Trả trạng thái đang xử lý hoặc chờ theo hợp đồng |
| Đã có | Khác | Bất kỳ | Từ chối xung đột |
| Mới | Không hợp lệ | Chưa có | Từ chối, không tạo side effect |

Chỉ lưu key ở bộ nhớ của một instance không đủ cho hệ thống nhiều node hoặc restart. Tính duy nhất cần được bảo vệ tại nơi lưu trữ dùng chung, thường bằng unique constraint hoặc cơ chế tương đương, cùng với transaction và xử lý race phù hợp.

### 10.3. Membership timeout là một loại lỗi khác với “không VIP”

Ba trạng thái cần phân biệt:

1. **VIP:** dịch vụ trả về trạng thái VIP.
2. **Không VIP:** dịch vụ trả về kết quả hợp lệ cho biết khách không phải VIP.
3. **Không xác định:** dịch vụ timeout, lỗi xác thực hoặc dữ liệu không hợp lệ.

Không được gộp trạng thái thứ ba vào thứ hai chỉ để tiếp tục tính toán. Nếu sản phẩm chọn fail closed, cần báo lỗi phù hợp và cho phép retry an toàn; nếu sản phẩm cho phép dùng snapshot gần nhất, phải có quy tắc về độ mới, nguồn và thời hạn.

### 10.4. Bài kiểm tra cho workflow

| Tình huống | Điều kiện kiểm tra |
| --- | --- |
| Membership trả VIP | Chính sách nhận snapshot VIP và tính giảm đúng |
| Membership trả non-VIP | Không áp dụng ưu đãi VIP |
| Membership timeout | Không gọi writer hoặc payment bằng trạng thái mặc định |
| Validation lỗi | Không lưu đơn, không capture |
| Lưu đơn thành công | Snapshot báo giá và policy version được lưu |
| Retry cùng key/payload | Không tạo đơn hoặc thanh toán trùng |
| Cùng key, payload khác | Trả lỗi xung đột theo hợp đồng |
| Payment timeout | Trạng thái thể hiện kết quả chưa xác định và có đường tra cứu |
| Đơn bị hủy | Không capture nếu chưa thanh toán; nếu đã thu tiền thì xử lý hoàn tiền theo hợp đồng riêng |

## 11. Tạo ma trận truy vết từ yêu cầu đến bằng chứng

Sau khi có quyết định và test case, nối chúng lại để biết mỗi lời hứa được kiểm tra ở đâu. Ma trận này giúp reviewer phát hiện **yêu cầu chưa có test** và **test không có yêu cầu làm căn cứ**.

### 11.1. Traceability matrix

| Quyết định | Hợp đồng | Test case | Tầng kiểm tra |
| --- | --- | --- | --- |
| D1 – VIP từ server tin cậy | Client không tự quyết định trạng thái VIP | TC11–TC14 | Service/contract test |
| D2 – Snapshot tại lúc tạo quote | Quote dùng một trạng thái cố định | TC15 | Service/integration test |
| D3–D4 – Ngưỡng 200.000, bao gồm biên | Subtotal >= 200.000 mới đủ điều kiện | TC03–TC05 | Unit test |
| D5 – Giảm 10% tiền hàng | Discount = floor(subtotal / 10) | TC04–TC07 | Unit test |
| D6 – Không giảm shipping/tax | Thành phần giảm chỉ là merchandise subtotal | Test tích hợp tính breakdown | Pricing integration test |
| D7 – Không cộng dồn coupon | Coupon không tham gia phép tính VIP trong phiên bản này | Test policy phối hợp | Unit/contract test |
| D8 – VND nguyên, làm tròn xuống | Không trả phần lẻ VND | TC06–TC07 | Unit test |
| D9 – Subtotal âm bị từ chối | IllegalArgumentException | TC08 | Unit test |
| D10 – Membership lỗi không mặc định | Lỗi phụ thuộc được truyền/ánh xạ rõ | TC13 | Service test |
| D11 – Policy thuần | Không I/O, không side effect | Kiểm tra thiết kế và unit test cô lập | Review/unit test |
| D12 – Retry idempotent | Cùng key/payload không tạo side effect trùng | TC18–TC19 | Integration/concurrency test |

### 11.2. Phát hiện khoảng trống

Đọc ma trận theo hai hướng:

- **Từ yêu cầu tới test:** mỗi quyết định quan trọng có bằng chứng nào? Nếu không có, cần bổ sung test hoặc giải thích vì sao không thể tự động kiểm tra.
- **Từ test tới yêu cầu:** expected value đến từ đâu? Nếu test chỉ kiểm tra một chi tiết implementation hoặc một giả định chưa xác nhận, cần xem lại.

Một test có thể phục vụ nhiều quyết định, và một quyết định có thể cần nhiều test. Không cần ép quan hệ một-một; mục tiêu là **không có lời hứa quan trọng nào bị bỏ quên**.

### 11.3. Không nhầm số lượng test với độ bao phủ hợp đồng

Một trăm test đều chạy khách VIP ở mức 1.000.000 VND không thay thế test ở 199.999 và 200.000. Ngược lại, một test parameterized có nhiều dòng dữ liệu có thể kiểm tra nhiều lớp tương đương rất tốt.

Hãy đánh giá:

- Có test cho từng nhánh điều kiện?
- Có test ngay sát ngưỡng?
- Có test cho invalid input và lỗi phụ thuộc?
- Có test cho bất biến và side effect?
- Có test cho trạng thái hoặc tương tác giữa các thành phần?
- Expected value có độc lập với implementation?

## 12. Review implementation bằng cách quay lại hợp đồng

Khi code đã viết, review không nên chỉ xác nhận nó “trông giống” công thức. Hãy kiểm tra từng quyết định:

| Câu hỏi | Bằng chứng trong code |
| --- | --- |
| Subtotal âm bị từ chối? | Validation xảy ra trước nhánh tính |
| Ngưỡng có bao gồm điểm bằng? | Điều kiện **< MIN** trả về 0, nên điểm bằng đi vào nhánh giảm |
| VIP lấy từ nguồn tin cậy? | Caller nhận membership snapshot từ server |
| Không cộng dồn coupon? | Policy không nhận coupon; workflow không tự cộng thêm |
| Làm tròn xuống? | Phép chia nguyên trên số không âm |
| Không tràn số? | Không nhân subtotal với 10 trong implementation này |
| Không có side effect? | Không gọi repository, gateway hoặc clock |
| Retry có an toàn? | Được bảo vệ ở workflow/storage, không nằm trong hàm thuần |

### 12.1. Tên và chữ ký phải phản ánh hợp đồng

Tên **discountVnd** cho biết kết quả là số tiền giảm theo VND. Tên **calculate** chung chung có thể không thể hiện đơn vị hoặc phạm vi. Tham số **merchandiseSubtotalVnd** dài hơn **amount**, nhưng tránh nhầm với tổng thanh toán đã bao gồm phí và thuế.

Chữ ký cũng cho thấy giới hạn: boolean **vip** chỉ biểu diễn hai trạng thái. Trạng thái “không xác định” không nằm trong hàm; do đó lỗi membership phải được giải quyết ở tầng gọi. Nếu nghiệp vụ yêu cầu policy xử lý trạng thái thứ ba, cần một kiểu dữ liệu rõ như enum hoặc kết quả có trạng thái, thay vì nhồi thêm quy ước vào boolean.

### 12.2. Comment không thay thế hợp đồng thực thi

Comment nói “làm tròn xuống” nhưng code dùng **Math.round** thì implementation vẫn sai. Ngược lại, code có thể đúng hôm nay nhưng không rõ tại sao ngưỡng là 200.000. Hãy kết hợp:

- Tên hằng số và tham số có đơn vị.
- Javadoc mô tả input, output và exception.
- Test tại biên và trường hợp làm tròn.
- Tài liệu hoặc quyết định nghiệp vụ có nguồn xác nhận.

Không cần lặp nguyên công thức ở quá nhiều nơi. Nên có **một nguồn chính** và liên kết test/tài liệu với nó.

### 12.3. Kiểm tra mutation ở điểm dễ nhầm

Một cách đánh giá test có bắt được lỗi so sánh là thử thay:

~~~java
if (!vip || merchandiseSubtotalVnd <= MIN_SUBTOTAL_VND) {
    return 0L;
}
~~~

Nếu đổi **<** thành **<=** mà toàn bộ test vẫn xanh, bộ test chưa chứng minh điểm biên 200.000 được bao gồm. Đây là ý tưởng của **mutation testing**: tạo biến đổi nhỏ có chủ đích để xem test có phát hiện hành vi sai hay không.

Không cần chạy mutation tool cho mọi bài tập. Với một ngưỡng quan trọng, chỉ cần tự hỏi **nếu dấu so sánh bị đổi, test nào sẽ đỏ?** Nếu không có câu trả lời, cần thêm test.

## 13. Bài tập mở rộng: yêu cầu giữ hàng trong 15 phút

Hãy áp dụng quy trình vừa học vào một miền khác. Nhóm sản phẩm gửi yêu cầu:

> Khi khách đặt hàng, hệ thống giữ số lượng sản phẩm trong kho trong 15 phút. Nếu khách không thanh toán đúng hạn, hệ thống tự giải phóng số lượng để người khác mua. Không được bán vượt số hàng đang có.

Đừng viết code ngay. Câu yêu cầu có nhiều điểm chưa rõ về thời gian, trạng thái, đồng thời và kết quả thanh toán.

### 13.1. Tự lập danh sách câu hỏi

Hãy xác định ít nhất một câu hỏi cho từng nhóm:

1. **Thời điểm bắt đầu:** 15 phút tính từ lúc nhận request, lúc kiểm tra tồn kho hay lúc reservation được commit?
2. **Điểm hết hạn:** đúng tại thời điểm hết 15 phút có còn giữ hàng không?
3. **Đồng hồ:** dùng múi giờ nào? Có phụ thuộc đồng hồ máy chủ hay nguồn thời gian chung?
4. **Số lượng:** số lượng 0 hoặc âm được xử lý ra sao?
5. **Tồn kho:** hai khách đặt cùng sản phẩm cùng lúc thì làm sao tránh bán vượt?
6. **Thanh toán:** nếu gateway timeout nhưng có thể đã thu tiền, có giải phóng hàng ngay không?
7. **Retry:** gửi lại cùng request có tạo reservation mới không?
8. **Hủy đơn:** khách hủy trước hạn thì khi nào giải phóng?
9. **Nhiều sản phẩm:** nếu một dòng đủ hàng nhưng dòng khác hết hàng, có giữ một phần hay từ chối toàn bộ?
10. **Lịch sử:** trạng thái reservation đã hết hạn có được phục hồi hay tạo mới?

### 13.2. Ví dụ các quyết định cần được xác nhận

Một hợp đồng giả định có thể chọn:

- Thời hạn bắt đầu từ lúc reservation được lưu thành công.
- Dùng thời điểm tuyệt đối kiểu Instant theo UTC.
- Reservation hết hạn khi **now >= expiresAt**.
- Số lượng phải lớn hơn 0.
- Kiểm tra và trừ lượng khả dụng được thực hiện nguyên tử ở tầng lưu trữ.
- Nếu thanh toán đang có kết quả chưa xác định, không tự giải phóng hàng cho tới khi tra cứu/đối soát theo chính sách.
- Cùng idempotency key và payload trả lại cùng reservation.
- Nếu bất kỳ dòng nào không đủ hàng, toàn bộ reservation thất bại; không giữ một phần.

Đây chỉ là **một phương án để luyện tập**. Product owner và người thiết kế hệ thống phải xác nhận thời gian, trải nghiệm khách hàng, khả năng oversell và cách phục hồi thanh toán.

### 13.3. Suy ra trường hợp biên về thời gian

Giả sử reservation được tạo tại **T** và hết hạn tại **T + 15 phút**. Nếu hợp đồng dùng điều kiện **now >= expiresAt**, các ca:

| Thời điểm kiểm tra | Kết quả |
| --- | --- |
| T + 14 phút 59 giây | Còn hiệu lực |
| T + 15 phút đúng | Hết hạn |
| T + 15 phút 1 giây | Hết hạn |

Để test ổn định, nên truyền **Clock** hoặc **Instant now** vào logic kiểm tra thay vì đọc đồng hồ hệ thống ở nhiều vị trí. Test không nên dùng sleep để đợi 15 phút.

Ví dụ hàm kiểm tra thuần:

~~~java
import java.time.Instant;
import java.util.Objects;

public final class ReservationExpiry {
    private ReservationExpiry() {
    }

    public static boolean isExpired(
            Instant now, Instant expiresAt) {
        Objects.requireNonNull(now, "now");
        Objects.requireNonNull(expiresAt, "expiresAt");
        return !now.isBefore(expiresAt);
    }
}
~~~

Test ở đúng điểm biên:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class ReservationExpiryTest {
    private static final Instant EXPIRES_AT =
            Instant.parse("2026-11-16T10:15:00Z");

    @Test
    void isNotExpiredImmediatelyBeforeDeadline() {
        assertFalse(ReservationExpiry.isExpired(
                Instant.parse("2026-11-16T10:14:59Z"),
                EXPIRES_AT));
    }

    @Test
    void isExpiredAtExactDeadline() {
        assertTrue(ReservationExpiry.isExpired(
                EXPIRES_AT, EXPIRES_AT));
    }

    @Test
    void remainsExpiredAfterDeadline() {
        assertTrue(ReservationExpiry.isExpired(
                Instant.parse("2026-11-16T10:15:01Z"),
                EXPIRES_AT));
    }
}
~~~

Đoạn code này chỉ kiểm tra **điều kiện thời gian**. Nó không giải phóng tồn kho, không đổi trạng thái DB và không xử lý race giữa payment và expiry worker. Những hành động đó cần hợp đồng workflow và transaction riêng.

### 13.4. Bài làm cần nộp

Hãy tạo bốn đầu ra:

1. **Bảng câu hỏi:** ít nhất 10 điểm mơ hồ, có nêu hệ quả của từng lựa chọn.
2. **Hợp đồng:** actor, đầu vào, tiền điều kiện, hậu điều kiện, trạng thái, lỗi, thời gian và side effect.
3. **Decision table:** tồn kho đủ/thiếu, thời gian trước/đúng/sau hạn, thanh toán thành công/từ chối/timeout, retry cùng/khác payload.
4. **Test plan:** test unit cho hàm thời gian, test tích hợp cho giữ kho nguyên tử, test đồng thời chống oversell và test phục hồi khi payment timeout.

Không cần viết toàn bộ hệ thống reservation. Bài tập nhằm chứng minh bạn có thể biến một câu yêu cầu thành **quy tắc và bằng chứng có thể kiểm tra**.

## 14. Đánh giá chất lượng một bộ hợp đồng và test

Sau khi hoàn thành bài tập, tự chấm theo rubric:

| Tiêu chí | Đạt | Cần cải thiện |
| --- | --- | --- |
| Nhận diện mơ hồ | Chỉ ra các từ có nhiều nghĩa và hỏi câu cụ thể | Chỉ ghi “cần làm rõ” mà không nêu lựa chọn |
| Quyết định | Có người/nguồn xác nhận và ghi lại | Tự chọn giả định rồi coi như yêu cầu |
| Hợp đồng | Có input, output, lỗi, side effect, bất biến và giới hạn | Chỉ viết lại yêu cầu bằng từ khác |
| Trường hợp biên | Có dưới/bằng/trên ngưỡng và dữ liệu lỗi | Chỉ có happy path |
| Oracle | Expected value độc lập với implementation | Gọi chính hàm đang test để tạo expected |
| Phân tầng test | Unit, integration và contract test đặt đúng nơi | Đưa mọi thứ vào một bài end-to-end chậm |
| Lỗi và retry | Xác định trạng thái sau lỗi và tác dụng phụ | Chỉ assert exception hoặc retry vô hạn |
| Truy vết | Mỗi quyết định quan trọng liên kết với test/bằng chứng | Test không rõ yêu cầu nào bảo vệ |
| Phạm vi kết luận | Nêu rõ test chứng minh điều gì và chưa chứng minh gì | Kết luận “hệ thống an toàn” từ một unit test |

### 14.1. Dấu hiệu bài làm đã đủ tốt để triển khai

- Người nghiệp vụ có thể đọc hợp đồng và xác nhận nó phản ánh ý định.
- Lập trình viên khác có thể triển khai mà không phải tự đoán các quy tắc chính.
- Reviewer có thể chọn một trường hợp và chỉ ra test tương ứng.
- Expected value có thể giải thích bằng quyết định đã được xác nhận.
- Các lỗi quan trọng có hành vi được mô tả.
- Những điều nằm ngoài phạm vi được ghi rõ.

Không phải mọi yêu cầu đều có thể làm rõ hoàn toàn trước khi bắt đầu. Khi còn điểm chưa biết, hãy ghi **giả định, người chịu trách nhiệm xác nhận, rủi ro và điều kiện không được phát hành**. Không nên âm thầm lấp khoảng trống.

## 15. Những lỗi thường gặp khi chuyển yêu cầu thành test

**Viết test ngay khi đọc câu yêu cầu đầu tiên.** Có thể đang kiểm thử một cách hiểu chưa được xác nhận. Hãy lập câu hỏi và bảng quyết định trước.

**Chọn một giả định vì code dễ viết hơn.** Dễ hiện thực không chứng minh đó là chính sách đúng. Những quyết định về quyền lợi, tiền và trạng thái cần người có thẩm quyền xác nhận.

**Dùng implementation làm oracle.** Nếu expected được tính bằng cùng công thức đang test, lỗi có thể lặp lại ở cả hai phía và test vẫn xanh.

**Chỉ test dưới và trên ngưỡng.** Thiếu đúng điểm bằng khiến nhầm lẫn giữa **>** và **>=** không bị phát hiện.

**Không kiểm tra làm tròn.** Hai module có thể cùng áp dụng 10% nhưng một nơi làm tròn xuống, nơi khác làm tròn gần nhất.

**Gộp invalid input với không đủ điều kiện.** Đơn hợp lệ nhưng không được giảm vẫn có thể được đặt hàng.

**Để client tự quyết định quyền.** Trường VIP hoặc vai trò gửi từ request không phải nguồn xác thực đáng tin.

**Gộp timeout với thất bại chắc chắn.** Một hệ thống ngoài có thể đã thực hiện tác dụng phụ dù phản hồi bị mất.

**Chỉ kiểm tra số lần gọi fake rồi kết luận DB không ghi trùng.** Fake xác minh tương tác tại một tầng, không chứng minh transaction hoặc tính duy nhất ở storage thật.

**Viết test quá lớn cho một quy tắc nhỏ.** Dùng unit test cho phép tính thuần; dành integration test cho tương tác thực sự cần xác minh.

**Không lưu phiên bản chính sách.** Kết quả lịch sử có thể không giải thích được sau khi ngưỡng hoặc tỷ lệ thay đổi.

**Dùng checklist như thủ tục hình thức.** Một ô được đánh dấu không phải bằng chứng. Phải biết test chạy ở đâu và kết luận được điều gì.

## 16. Mẫu có thể tái sử dụng cho yêu cầu tiếp theo

Khi nhận một yêu cầu mới, có thể sao chép khung sau vào ticket hoặc tài liệu thiết kế:

~~~text
Tên yêu cầu:
Mục tiêu người dùng:
Nguồn xác nhận:
Phiên bản / ngày hiệu lực:

1. Từ ngữ hoặc điều kiện chưa rõ
   - Câu hỏi:
   - Các lựa chọn:
   - Hệ quả của từng lựa chọn:
   - Người xác nhận:

2. Quyết định đã thống nhất
   - D1:
   - D2:
   - D3:

3. Hợp đồng
   - Actor:
   - Input:
   - Preconditions:
   - Output:
   - Postconditions:
   - Invariants:
   - Errors:
   - Side effects:
   - Compatibility:
   - Out of scope:

4. Decision table
   - Điều kiện:
   - Tổ hợp:
   - Hành động:

5. Test cases
   - ID:
   - Input:
   - Expected:
   - Oracle:
   - Test level:

6. Rủi ro chưa giải quyết
   - Rủi ro:
   - Owner:
   - Mitigation:
   - Release condition:
~~~

Khung này không bắt buộc mọi dự án phải tạo tài liệu dài. Với một hàm nhỏ, có thể ghi hợp đồng trong Javadoc và test. Với workflow thanh toán, phân quyền hoặc migration dữ liệu, cần nhiều bằng chứng hơn.

## 17. Ghi nhớ

- Yêu cầu tự nhiên là điểm bắt đầu; hãy tách **điều đã biết, điều thiếu, điều mơ hồ, giả định và quyết định đã xác nhận**.
- Hỏi câu làm rõ bằng các lựa chọn và hệ quả cụ thể; đừng để lập trình viên tự quyết định chính sách nghiệp vụ.
- Viết hợp đồng với **đầu vào, tiền điều kiện, hậu điều kiện, bất biến, lỗi, side effect và phạm vi** trước khi hiện thực.
- Dùng decision table, phân hoạch tương đương và giá trị **ngay dưới/bằng/ngay trên** để suy ra trường hợp kiểm tra.
- Expected value phải dựa trên **oracle độc lập**; test cần kiểm tra cả kết quả đúng và điều không được xảy ra.
- Đặt test ở đúng tầng: unit cho quy tắc thuần, integration/contract cho dependency và workflow, concurrency test cho race/idempotency khi cần.
- Ghi nhận quyết định và phiên bản chính sách để kết quả có thể truy vết và giải thích về sau.

Một hợp đồng tốt giúp người viết code biết phải làm gì, reviewer biết cần kiểm tra điều gì và người vận hành biết hệ thống hứa điều gì khi thành công hoặc thất bại. Đó là nền tảng để mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**.

## 5. Chuyển hợp đồng thành bảng quyết định

Trước khi viết test, hãy biểu diễn các điều kiện bằng một bảng. Bảng giúp nhìn thấy mọi tổ hợp quan trọng và làm rõ nhánh nào được áp dụng.

### 5.1. Bảng quyết định cho ưu đãi VIP

| VIP? | Subtotal tiền hàng | Kết quả |
| --- | --- | --- |
| Không | Bất kỳ giá trị hợp lệ nào | Giảm 0 VND |
| Có | Nhỏ hơn 200.000 VND | Giảm 0 VND |
| Có | Bằng hoặc lớn hơn 200.000 VND | Giảm 10%, làm tròn xuống VND nguyên |
| Bất kỳ | Subtotal âm | Từ chối đầu vào |
| Chưa xác định do membership lỗi | Không tính | Báo lỗi phụ thuộc, không tự gán trạng thái VIP |

Bảng này cũng chỉ ra một điểm thiết kế: hàm tính ưu đãi chỉ nhận **trạng thái VIP đã xác định**. Nó không nên tự gọi membership service rồi tự quyết định cách xử lý timeout.

### 5.2. Decision table dạng điều kiện

| Điều kiện | R1 | R2 | R3 | R4 |
| --- | --- | --- | --- | --- |
| Subtotal hợp lệ? | Có | Có | Có | Không |
| VIP? | Không | Có | Có | Không cần xét |
| Subtotal >= 200.000? | Không cần xét | Không | Có | Không cần xét |
| Hành động | Giảm 0 | Giảm 0 | Giảm 10% | Báo lỗi input |

Khi một điều kiện không ảnh hưởng kết quả của rule hiện tại, có thể ghi **không cần xét**. Ví dụ, khách không VIP thì subtotal có đạt ngưỡng hay không cũng không làm thay đổi mức giảm VIP. Điều này giúp tránh tạo quá nhiều trường hợp lặp.

### 5.3. Tách điều kiện hợp lệ khỏi điều kiện hưởng ưu đãi

Hai câu hỏi này khác nhau:

- **Đầu vào có hợp lệ không?** Subtotal âm là không hợp lệ.
- **Đầu vào hợp lệ có được giảm giá không?** Khách không VIP hoặc chưa đạt ngưỡng vẫn có thể đặt đơn, chỉ không được giảm VIP.

Nếu trộn hai khái niệm, implementation có thể từ chối một đơn bình thường chỉ vì khách không đủ điều kiện ưu đãi. Đây là lỗi ngữ nghĩa thường gặp khi yêu cầu viết “không áp dụng ưu đãi cho đơn không đủ điều kiện”.

## 6. Từ bảng quyết định sang phân hoạch và giá trị biên

Mỗi hàng trong decision table gợi ý một nhóm đầu vào. Sau đó chọn đại diện và các điểm sát ranh giới để kiểm tra.

### 6.1. Các lớp tương đương

| Thuộc tính | Lớp | Giá trị đại diện |
| --- | --- | ---: |
| Trạng thái VIP | Không VIP | false |
| Trạng thái VIP | VIP | true |
| Subtotal | Âm, không hợp lệ | -1 |
| Subtotal | Bằng 0 | 0 |
| Subtotal | Dưới ngưỡng | 199.999 |
| Subtotal | Đúng ngưỡng | 200.000 |
| Subtotal | Trên ngưỡng | 200.001 |
| Phần lẻ sau 10% | Chia hết cho 10 | 200.010 |
| Phần lẻ sau 10% | Có phần dư | 200.019 |
| Giới hạn kiểu | Giá trị lớn nhất của long | Long.MAX_VALUE |

Không cần kiểm tra mọi số trong miền. Cần chọn các đại diện có thể làm đổi nhánh, đổi kết quả hoặc bộc lộ lỗi số học.

### 6.2. Giá trị ngay dưới, bằng và ngay trên ngưỡng

~~~text
199.999 VND       200.000 VND       200.001 VND
     |                  |                  |
     v                  v                  v
 Không giảm         Bắt đầu giảm        Có giảm
~~~

Giá trị 200.000 là điểm quyết định giữa hai nhánh. Nếu implementation vô tình dùng **>** thay vì **>=**, chỉ test 250.000 và 100.000 có thể vẫn xanh; test đúng biên mới làm lộ lỗi.

### 6.3. Kiểm tra làm tròn

Vì hợp đồng chọn làm tròn xuống VND nguyên, cần có ít nhất:

| Subtotal | 10% chính xác | Discount VND |
| ---: | ---: | ---: |
| 200.000 | 20.000 | 20.000 |
| 200.010 | 20.001 | 20.001 |
| 200.019 | 20.001,9 | 20.001 |
| 200.099 | 20.009,9 | 20.009 |

Các ví dụ có phần lẻ giúp xác minh implementation không dùng cách làm tròn gần nhất ngoài hợp đồng.

### 6.4. Kiểm tra miền số và phép toán

Trong Java, phép nhân số nguyên có thể tràn mà không tự ném exception. Nếu viết:

~~~java
long discount = subtotal * 10 / 100;
~~~

giá trị trung gian có thể tràn trước khi chia. Với chính sách 10% trên subtotal không âm, dùng **subtotal / 10** cho kết quả làm tròn xuống và tránh phép nhân trung gian.

Đây là một lựa chọn dựa trên công thức cụ thể. Nếu tỷ lệ thay đổi hoặc có phần trăm khác, cần xem lại cách tính, dùng **Math.multiplyExact** hoặc **BigDecimal** theo hợp đồng và kiểm thử phù hợp. Không nên thay kiểu số chỉ vì nghĩ rằng BigDecimal luôn cần thiết.

## 7. Lập danh sách trường hợp kiểm tra

Một test case tốt ghi rõ **đầu vào, điều kiện, kết quả mong đợi và mục đích**. Không nên chỉ ghi “test VIP” vì người thực hiện không biết cần xác minh điều gì.

### 7.1. Test case cho hàm tính ưu đãi

| ID | VIP | Subtotal VND | Kết quả mong đợi | Mục đích |
| --- | --- | ---: | ---: | --- |
| TC01 | false | 200.000 | 0 | Khách thường không được giảm VIP |
| TC02 | true | 0 | 0 | Subtotal 0 không đạt ngưỡng |
| TC03 | true | 199.999 | 0 | Ngay dưới ngưỡng |
| TC04 | true | 200.000 | 20.000 | Đúng ngưỡng, bao gồm biên |
| TC05 | true | 200.001 | 20.000 | Ngay trên ngưỡng, làm tròn xuống |
| TC06 | true | 200.010 | 20.001 | Tỷ lệ 10% chia hết |
| TC07 | true | 200.019 | 20.001 | Có phần lẻ, làm tròn xuống |
| TC08 | true | -1 | IllegalArgumentException | Subtotal âm bị từ chối |
| TC09 | false | Long.MAX_VALUE | 0 | Không VIP, giá trị lớn không gây phép nhân |
| TC10 | true | Long.MAX_VALUE | Long.MAX_VALUE / 10 | Không tràn phép tính 10% |

### 7.2. Test case cho tầng lấy trạng thái VIP

Hàm thuần không kiểm tra nguồn membership. Một thành phần điều phối cần có test riêng:

| ID | Membership service | Kết quả mong đợi |
| --- | --- | --- |
| TC11 | Trả về VIP | Dùng trạng thái VIP snapshot để tính |
| TC12 | Trả về không VIP | Không áp dụng giảm VIP |
| TC13 | Timeout | Báo lỗi phụ thuộc theo hợp đồng, không tự mặc định |
| TC14 | Trả về dữ liệu không hợp lệ | Từ chối hoặc xử lý lỗi theo hợp đồng dữ liệu |
| TC15 | Trạng thái VIP đổi sau khi báo giá được tạo | Báo giá đã snapshot không tự đổi nếu hợp đồng yêu cầu cố định |

### 7.3. Test case cho workflow tạo đơn và retry

| ID | Tình huống | Điều cần xác minh |
| --- | --- | --- |
| TC16 | Đơn hợp lệ, lần gọi đầu | Lưu một báo giá và tạo một đơn |
| TC17 | Đơn invalid | Không tạo đơn hoặc thu tiền |
| TC18 | Retry cùng idempotency key, cùng payload | Trả kết quả đã có theo hợp đồng, không tạo side effect trùng |
| TC19 | Cùng key nhưng payload khác | Từ chối xung đột hoặc xử lý theo chính sách đã công bố |
| TC20 | Đơn bị hủy trước khi thanh toán | Không capture tiền |
| TC21 | Timeout khi thanh toán, kết quả chưa rõ | Chuyển trạng thái phù hợp và tra cứu/đối soát, không tự kết luận thất bại |

Những test case này không thuộc riêng hàm tính 10%. Chúng xác minh **workflow** và cần được đặt ở đúng tầng test.

### 7.4. Xác định mức kiểm thử

| Phạm vi | Loại test phù hợp | Ví dụ |
| --- | --- | --- |
| Công thức giảm giá | Unit test | TC01–TC10 |
| Tra cứu membership | Unit test với fake hoặc contract test | TC11–TC15 |
| Tạo đơn, lưu báo giá | Integration/service test | TC16–TC17 |
| Idempotency và retry | Integration test, test đồng thời có điều phối | TC18–TC19 |
| Thanh toán và hủy | Contract/integration test với gateway sandbox hoặc fake phù hợp | TC20–TC21 |

Đặt test ở đúng tầng giúp test nhanh và có ý nghĩa. Không cần khởi động toàn bộ ứng dụng Spring chỉ để kiểm tra một phép chia cho 10.

## 8. Hiện thực hợp đồng bằng Java

Khi hợp đồng và test case đã rõ, code có thể ngắn hơn phần phân tích. Đây là điều bình thường: **độ khó nằm ở việc xác định hành vi đúng**, không phải ở số dòng implementation.

### 8.1. Cài đặt chính sách thuần

Tệp **VipDiscountPolicy.java**, dùng Java 17 hoặc mới hơn:

~~~java
public final class VipDiscountPolicy {
    public static final long MIN_SUBTOTAL_VND = 200_000L;

    private VipDiscountPolicy() {
    }

    /**
     * Computes the VIP discount on merchandise subtotal in whole VND.
     *
     * @param merchandiseSubtotalVnd non-negative merchandise subtotal
     * @param vip trusted VIP status snapshot for this quote
     * @return discount in whole VND, rounded down
     * @throws IllegalArgumentException if subtotal is negative
     */
    public static long discountVnd(
            long merchandiseSubtotalVnd,
            boolean vip) {
        if (merchandiseSubtotalVnd < 0) {
            throw new IllegalArgumentException(
                    "Merchandise subtotal must not be negative");
        }

        if (!vip || merchandiseSubtotalVnd < MIN_SUBTOTAL_VND) {
            return 0L;
        }

        // 10% rounded down; division avoids an overflowing * 10 intermediate.
        return merchandiseSubtotalVnd / 10L;
    }
}
~~~

Implementation giữ các quyết định đã ghi:

- Subtotal âm bị từ chối.
- Khách không VIP hoặc dưới ngưỡng nhận mức giảm 0.
- Đúng ngưỡng được áp dụng vì điều kiện kiểm tra là **subtotal < MIN_SUBTOTAL_VND** để trả về 0.
- Chia nguyên cho 10 thực hiện quy tắc làm tròn xuống.
- Phương thức không gọi DB hoặc membership service, không giữ trạng thái và không tạo side effect.

### 8.2. Tại sao không nhận VIP từ request client?

Nếu endpoint nhận JSON như:

~~~json
{
  "merchandiseSubtotalVnd": 500000,
  "vip": true
}
~~~

thì người dùng có thể tự sửa trường **vip** và yêu cầu mức giảm không thuộc quyền của họ. API công khai nên nhận dữ liệu người dùng được phép cung cấp, còn trạng thái membership phải được xác định từ nguồn server tin cậy.

Ví dụ tầng điều phối:

~~~java
public final class QuoteService {
    private final MembershipService membershipService;

    public QuoteService(MembershipService membershipService) {
        this.membershipService = membershipService;
    }

    public long calculateVipDiscount(
            CustomerId customerId,
            long merchandiseSubtotalVnd) {
        boolean vip = membershipService.isVip(customerId);
        return VipDiscountPolicy.discountVnd(
                merchandiseSubtotalVnd, vip);
    }
}
~~~

**MembershipService** và **CustomerId** là kiểu giả định của ví dụ. Nếu membership service timeout, lời gọi ném lỗi và không có kết quả tính; tầng này không được tự đổi lỗi thành **false** nếu chưa có quyết định cho phép fallback. Trong hệ thống thật, trạng thái VIP có thể cần snapshot và lưu cùng báo giá để lần đọc sau không phụ thuộc trạng thái membership hiện tại.

### 8.3. Tách phép tính khỏi vòng đời đơn hàng

Hàm **discountVnd** chỉ trả số tiền giảm. Nó không quyết định:

- Khi nào tạo đơn.
- Có lưu báo giá hay không.
- Khi nào capture payment.
- Đơn hủy thì hoàn tiền ra sao.
- Retry có trả lại kết quả cũ hay tạo đơn mới.

Những quyết định này thuộc hợp đồng của workflow. Giữ ranh giới rõ giúp test chính sách độc lập và tránh một hàm nhỏ trở thành nơi chứa toàn bộ trạng thái checkout.

## 9. Viết JUnit 5 từ test case

Test cần kiểm tra **kết quả theo hợp đồng**, không chỉ kiểm tra phương thức chạy qua mà không ném lỗi.

### 9.1. Test các lớp đầu vào và ngưỡng

Tệp **VipDiscountPolicyTest.java**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class VipDiscountPolicyTest {
    @ParameterizedTest
    @CsvSource({
        "false, 0, 0",
        "false, 200000, 0",
        "false, 500000, 0",
        "true, 0, 0",
        "true, 199999, 0",
        "true, 200000, 20000",
        "true, 200001, 20000",
        "true, 200010, 20001",
        "true, 200019, 20001"
    })
    void calculatesDiscountForEquivalenceClassesAndBoundaries(
            boolean vip,
            long subtotalVnd,
            long expectedDiscountVnd) {
        assertEquals(
                expectedDiscountVnd,
                VipDiscountPolicy.discountVnd(subtotalVnd, vip));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(
                IllegalArgumentException.class,
                () -> VipDiscountPolicy.discountVnd(-1L, true));
    }

    @Test
    void handlesMaximumLongWithoutOverflow() {
        assertEquals(
                Long.MAX_VALUE / 10L,
                VipDiscountPolicy.discountVnd(Long.MAX_VALUE, true));
    }
}
~~~

JUnit Jupiter và Jupiter Params cần được khai báo trong dependency kiểm thử của dự án; chúng không nằm trong JDK. Test parameterized giúp kiểm tra nhiều lớp dữ liệu với cùng một oracle mà không sao chép phần assertion.

### 9.2. Kiểm tra bất biến

Ngoài các giá trị ví dụ, có thể kiểm tra các tính chất phải đúng với nhiều đầu vào:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VipDiscountPolicyInvariantTest {
    @org.junit.jupiter.api.Test
    void discountIsNeverNegativeOrGreaterThanSubtotal() {
        long[] values = {
            0L, 1L, 199_999L, 200_000L,
            200_019L, 1_000_000L, Long.MAX_VALUE
        };

        for (long subtotal : values) {
            long discount =
                    VipDiscountPolicy.discountVnd(subtotal, true);

            assertTrue(discount >= 0L);
            assertTrue(discount <= subtotal);
        }
    }

    @org.junit.jupiter.api.Test
    void nonVipNeverReceivesVipDiscount() {
        long[] values = {
            0L, 200_000L, 500_000L, Long.MAX_VALUE
        };

        for (long subtotal : values) {
            assertEquals(
                    0L,
                    VipDiscountPolicy.discountVnd(subtotal, false));
        }
    }
}
~~~

Các test tính chất không thay thế test biên cụ thể. Chúng giúp kiểm tra thêm những bất biến tổng quát, trong khi test ngưỡng xác nhận chính sách tại điểm dễ nhầm.

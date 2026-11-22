# Độ hạt (grain): một đối tượng hoặc bản ghi đại diện cho điều gì

Trong mô hình dữ liệu, **độ hạt (grain)** mô tả chính xác một đối tượng, một sự kiện hoặc một bản ghi đại diện cho điều gì trong nghiệp vụ. Khi nói “một bản ghi đơn hàng”, ta cần biết bản ghi đó đại diện cho cả đơn hàng, một dòng hàng trong đơn, một lần thanh toán hay một kiện hàng được gửi đi. Các đối tượng này có liên quan với nhau nhưng không thể thay thế cho nhau.

Xác định độ hạt là một bước quan trọng của mô hình hóa khái niệm. Nó giúp nhóm phân tích xác định ranh giới của thực thể, ý nghĩa của thuộc tính, bội số quan hệ và mức chi tiết mà hệ thống cần quản lý. Trong mô hình phân tích, độ hạt còn quyết định một dòng dữ liệu mô tả một giao dịch, một trạng thái tại một thời điểm hay một kết quả đã tổng hợp.

Bài học này tập trung vào cách diễn đạt độ hạt bằng ngôn ngữ nghiệp vụ, kiểm tra độ hạt qua ví dụ và sử dụng kết quả đó khi xây dựng mô hình quan hệ, document, đồ thị và phân tích.

**Sau bài học, bạn có thể:**

- Giải thích một instance hoặc bản ghi đại diện cho điều gì.
- Phân biệt độ hạt của thực thể, dòng chi tiết, sự kiện, ảnh chụp trạng thái và dữ liệu tổng hợp.
- Viết phát biểu độ hạt đủ cụ thể để người nghiệp vụ xác nhận.
- Nhận biết lỗi trộn nhiều độ hạt trong cùng một cấu trúc dữ liệu.
- Suy luận các quan hệ và câu hỏi về định danh từ độ hạt đã thống nhất.

## 1. Độ hạt là gì?

Độ hạt trả lời câu hỏi:

> Một đối tượng hoặc một bản ghi riêng lẻ trong mô hình đại diện cho một đơn vị nghiệp vụ nào?

Đơn vị đó phải có ý nghĩa rõ ràng trong phạm vi hệ thống. Ví dụ:

- Một **khách hàng** đại diện cho một chủ thể có quan hệ mua bán với doanh nghiệp.
- Một **đơn hàng** đại diện cho một yêu cầu mua đã được tạo theo quy trình đặt hàng.
- Một **dòng đơn hàng** đại diện cho một dòng lựa chọn hàng hóa và điều kiện bán cụ thể trong một đơn.
- Một **lần thử thanh toán** đại diện cho một lần hệ thống hoặc người dùng yêu cầu xử lý thanh toán.
- Một **ảnh chụp tồn kho** đại diện cho lượng tồn của một mặt hàng tại một địa điểm vào một thời điểm xác định.

Mỗi câu mô tả trên xác định một đơn vị khác nhau. Nếu nhóm chỉ nói “hệ thống lưu đơn hàng và thanh toán” mà không làm rõ một bản ghi thanh toán là một khoản thanh toán, một lần thử, một lần thu tiền hay một lần hoàn tiền, mô hình sẽ thiếu thông tin quan trọng.

Có thể hình dung độ hạt như mức phóng đại của một bản đồ: bản đồ cấp quốc gia, cấp tỉnh và cấp đường phố đều mô tả cùng một vùng nhưng trả lời các câu hỏi khác nhau. Tương tự, một đơn hàng và các dòng hàng của nó mô tả cùng giao dịch ở hai mức chi tiết khác nhau.

### 1.1. Độ hạt không chỉ là số lượng dữ liệu

Độ hạt không đơn thuần có nghĩa là “nhiều dữ liệu hơn” hoặc “ít dữ liệu hơn”. Nó xác định **ý nghĩa của một đơn vị dữ liệu**.

Ví dụ, một bảng có 10.000 bản ghi có thể chứa:

- 10.000 đơn hàng;
- 10.000 dòng đơn hàng;
- 10.000 lần thử thanh toán;
- hoặc 10.000 ảnh chụp tồn kho theo mặt hàng, địa điểm và thời gian.

Con số bản ghi giống nhau nhưng nội dung nghiệp vụ hoàn toàn khác. Vì vậy, không thể xác định độ hạt chỉ bằng cách xem số dòng hay tên bảng.

### 1.2. Độ hạt và mức chi tiết

Trong một miền nghiệp vụ, nhiều cấu trúc có thể tồn tại ở các mức chi tiết khác nhau:

| Mức biểu diễn | Một đơn vị đại diện cho | Câu hỏi thường được trả lời |
|---|---|---|
| Đơn hàng | Một giao dịch đặt mua | Khách hàng đã đặt đơn nào? |
| Dòng đơn hàng | Một dòng hàng trong một đơn | Đơn này gồm những mặt hàng và số lượng nào? |
| Sự kiện thanh toán | Một lần phát sinh hành động thanh toán | Đã có những lần thanh toán hoặc thử thanh toán nào? |
| Ảnh chụp tồn kho | Một trạng thái tồn kho tại một thời điểm | Tại thời điểm chụp, còn bao nhiêu hàng? |
| Tổng hợp bán hàng ngày | Kết quả bán hàng theo ngày và các chiều đã chọn | Doanh số theo ngày, sản phẩm hoặc cửa hàng là bao nhiêu? |

Một cấu trúc ở mức tổng hợp thường chứa ít chi tiết hơn cấu trúc giao dịch. Khi tổng hợp, một số thông tin ban đầu có thể không còn khôi phục được. Do đó, cần xác định rõ mức chi tiết nào là nguồn sự thật và mức nào được tạo ra để phục vụ truy vấn hoặc báo cáo.

## 2. Phân biệt độ hạt của thực thể, sự kiện và dữ liệu phân tích

Từ “bản ghi” thường được dùng cho nhiều kiểu dữ liệu. Cần nhận ra bản ghi đang mô tả một đối tượng tồn tại, một việc đã xảy ra hay trạng thái được quan sát.

### 2.1. Độ hạt của thực thể

Thực thể mô tả một đối tượng được nghiệp vụ quan tâm và cần phân biệt với các đối tượng khác.

Ví dụ:

- Một khách hàng;
- Một sản phẩm;
- Một đơn hàng;
- Một kho hàng;
- Một phương thức vận chuyển.

Phát biểu độ hạt nên chỉ rõ điều kiện để một instance được xem là một đối tượng riêng. Với đơn hàng, đó có thể là một đơn được tạo sau khi khách hàng xác nhận đặt mua. Với sản phẩm, doanh nghiệp cần xác định đối tượng được quản lý là sản phẩm chung hay từng biến thể có thể bán.

Không phải mọi danh từ trong yêu cầu đều trở thành thực thể. Một cụm từ có thể chỉ vai trò, thuộc tính, trạng thái hoặc sự kiện. Độ hạt giúp kiểm tra xem khái niệm đang xét có đơn vị tồn tại độc lập trong nghiệp vụ hay không.

### 2.2. Độ hạt của dòng chi tiết

Một đối tượng cấp tổng thể thường chứa các thành phần có độ hạt nhỏ hơn. Ví dụ, đơn hàng có các dòng đơn hàng.

- Một đơn hàng đại diện cho một lần đặt mua.
- Một dòng đơn hàng đại diện cho một dòng được ghi nhận trong đơn, với mặt hàng, số lượng và điều kiện bán tại dòng đó.

Nếu một đơn có ba dòng hàng, mô hình có một đối tượng đơn hàng và ba đối tượng dòng đơn hàng. Không nên hiểu rằng mỗi dòng hàng là một đơn hàng độc lập.

Cũng cần xác minh quy tắc tạo dòng. Nếu người mua thêm cùng một SKU hai lần với hai mức giá hoặc hai chương trình khuyến mại khác nhau, hệ thống có thể giữ hai dòng riêng. Vì vậy, phát biểu “một dòng cho mỗi sản phẩm trong đơn” có thể chưa đủ chính xác. Cách diễn đạt an toàn hơn là “một dòng cho mỗi dòng hàng được ghi nhận trong đơn theo quy tắc tạo dòng của nghiệp vụ”.

### 2.3. Độ hạt của sự kiện

Sự kiện ghi nhận một việc xảy ra, thường gắn với thời điểm và tác nhân.

Ví dụ:

- Một lần khách hàng đặt đơn;
- Một lần thử thanh toán;
- Một lần chuyển trạng thái đơn;
- Một lần quét kiện hàng tại trung tâm phân loại;
- Một lần điều chỉnh số lượng tồn.

Một đối tượng có thể liên quan đến nhiều sự kiện. Một đơn hàng có thể có nhiều lần chuyển trạng thái; một khoản thanh toán có thể có nhiều lần thử xử lý tùy quy trình. Nếu chỉ lưu trạng thái hiện tại, hệ thống có thể không trả lời được ai đã thay đổi trạng thái, khi nào thay đổi và trạng thái trước đó là gì.

Khi mô hình hóa sự kiện, cần hỏi một bản ghi đại diện cho **mỗi lần hành động xảy ra**, mỗi yêu cầu được gửi đi, mỗi kết quả được xác nhận hay mỗi lần trạng thái chuyển đổi. Các cách hiểu này không phải lúc nào cũng giống nhau.

### 2.4. Độ hạt của ảnh chụp trạng thái

Ảnh chụp trạng thái ghi nhận giá trị của một đối tượng hoặc tập đối tượng tại một thời điểm hay một kỳ.

Ví dụ:

- Tồn kho của một SKU tại một kho vào lúc 08:00;
- Số dư tài khoản vào cuối ngày;
- Số lượng đơn đang chờ xử lý tại thời điểm chốt báo cáo;
- Trạng thái hợp đồng tại ngày cuối tháng.

Phát biểu độ hạt phải nêu rõ đơn vị được quan sát và mốc thời gian. “Một bản ghi tồn kho mỗi ngày” chưa đủ nếu doanh nghiệp có nhiều kho, nhiều SKU hoặc nhiều lần chụp trong ngày.

Một phát biểu cụ thể hơn là: “Một ảnh chụp cho mỗi SKU tại mỗi kho vào thời điểm chốt tồn kho hằng ngày”. Nếu hệ thống chụp nhiều lần trong ngày, thời điểm chụp hoặc mã lần chụp cũng thuộc phạm vi cần xác định.

### 2.5. Độ hạt của dữ liệu tổng hợp

Dữ liệu tổng hợp gom nhiều sự kiện hoặc đối tượng thành một kết quả theo các chiều đã chọn.

Ví dụ: doanh số theo ngày, cửa hàng và sản phẩm. Một bản ghi không đại diện cho một đơn hàng riêng lẻ, mà đại diện cho kết quả tổng hợp của tất cả giao dịch thuộc tổ hợp ngày, cửa hàng và sản phẩm đó theo quy tắc tính toán.

Cần ghi rõ:

- Các chiều dùng để nhóm dữ liệu;
- Khoảng thời gian;
- Điều kiện đưa dữ liệu vào tổng hợp;
- Công thức tính các chỉ số;
- Quy tắc xử lý hủy, hoàn, điều chỉnh và dữ liệu đến muộn.

Nếu bỏ mất một chiều khi tổng hợp, không thể phân tích lại theo chiều đó từ kết quả đã lưu. Ví dụ, doanh số tổng hợp theo ngày và cửa hàng không thể tự tách chính xác theo từng sản phẩm nếu dữ liệu sản phẩm đã bị loại khỏi mức chi tiết.

## 3. Viết phát biểu độ hạt

Một phát biểu độ hạt tốt phải đủ rõ để hai người đọc độc lập hiểu cùng một đơn vị nghiệp vụ.

Có thể dùng mẫu:

> Một bản ghi đại diện cho **[đơn vị nghiệp vụ]**, trong phạm vi **[đối tượng hoặc quy trình]**, tại **[thời điểm hoặc khoảng thời gian nếu có]**, theo **[điều kiện ghi nhận hoặc quy tắc phân biệt]**.

Ví dụ:

- Một bản ghi đơn hàng đại diện cho một đơn được tạo khi khách hàng hoàn tất thao tác đặt mua.
- Một bản ghi dòng đơn hàng đại diện cho một dòng hàng được ghi nhận trong một đơn, với số lượng và điều kiện bán của dòng đó.
- Một bản ghi lần thử thanh toán đại diện cho một yêu cầu xử lý thanh toán được gửi tới nhà cung cấp thanh toán.
- Một bản ghi ảnh chụp tồn kho đại diện cho số lượng của một SKU tại một kho vào thời điểm chốt tồn.

Đối với dữ liệu phân tích, có thể dùng mẫu:

> Một dòng dữ liệu đại diện cho **[một sự kiện hoặc trạng thái]** tại tổ hợp **[các chiều]**, trong **[thời điểm hoặc kỳ]**, sau khi áp dụng **[quy tắc lọc và tổng hợp]**.

Ví dụ:

> Một dòng dữ liệu bán hàng đại diện cho doanh số của một sản phẩm tại một cửa hàng trong một ngày, được tổng hợp từ các dòng đơn hàng đủ điều kiện ghi nhận doanh thu trong ngày đó.

### 3.1. Các câu hỏi để kiểm tra phát biểu

Khi viết xong, hãy hỏi:

1. Nếu có thêm một đối tượng hoặc sự kiện cùng loại, nó sẽ tạo ra một bản ghi riêng trong trường hợp nào?
2. Hai bản ghi có thể cùng đại diện cho một đối tượng nghiệp vụ không? Nếu có, đó là lịch sử, phiên bản hay dữ liệu trùng?
3. Bản ghi thuộc phạm vi nào: một khách hàng, một đơn, một dòng hàng, một địa điểm hay một kỳ?
4. Thời điểm nào làm bản ghi được tạo, có hiệu lực hoặc kết thúc?
5. Các thuộc tính được mô tả có đúng với mọi bản ghi ở độ hạt này không?
6. Những quan hệ một-một, một-nhiều hoặc nhiều-nhiều nào phát sinh từ cách xác định này?
7. Có thể phân biệt một bản ghi với bản ghi khác theo quy tắc nghiệp vụ nào?

Nếu câu trả lời còn mơ hồ, phát biểu độ hạt cần được làm rõ với người phụ trách nghiệp vụ.

## 4. Ví dụ xuyên suốt: xác định độ hạt trong hệ thống bán hàng

Giả sử hệ thống cần quản lý khách hàng, đơn hàng, mặt hàng, thanh toán và giao hàng. Một mô tả ban đầu có thể là:

> Khách hàng đặt hàng gồm nhiều sản phẩm. Khách hàng thanh toán cho đơn. Kho chuẩn bị hàng và giao cho khách hàng. Hệ thống lưu lại tồn kho để nhân viên theo dõi.

Mô tả này chưa xác định được một bản ghi đại diện cho điều gì ở từng phần. Ta cần tách các đơn vị nghiệp vụ.

### 4.1. Đơn hàng và dòng đơn hàng

Giả sử khách hàng đặt một đơn gồm:

| Đơn hàng | Dòng | Mặt hàng | Số lượng |
|---|---:|---|---:|
| ORD-1001 | 1 | Bàn phím | 1 |
| ORD-1001 | 2 | Chuột | 2 |
| ORD-1001 | 3 | Tai nghe | 1 |

Có hai độ hạt:

- **Đơn hàng:** một đơn được tạo bởi một lần đặt mua. Bản ghi đơn hàng chứa thông tin chung như người đặt, thời điểm tạo và thông tin tổng thể của đơn.
- **Dòng đơn hàng:** một dòng được ghi nhận trong đơn. Bản ghi dòng hàng chứa mặt hàng, số lượng và các điều kiện áp dụng cho dòng.

Nếu lưu tất cả thông tin ở cấp đơn hàng, nhóm có thể gặp khó khăn khi một đơn có nhiều mặt hàng. Nếu coi từng dòng hàng là đơn hàng, số lượng đơn và doanh số theo đơn có thể bị đếm nhiều lần.

Mối quan hệ khái niệm thường là một đơn hàng có một hoặc nhiều dòng đơn hàng. Tuy nhiên, điều kiện tối thiểu và việc có cho phép đơn nháp chưa có dòng hàng hay không cần được xác nhận theo quy trình thực tế.

### 4.2. Thanh toán và lần thử thanh toán

Một đơn có thể được thanh toán qua nhiều lần xử lý. Ví dụ:

1. Khách hàng gửi yêu cầu thanh toán lần thứ nhất nhưng ngân hàng từ chối.
2. Khách hàng thử lại và giao dịch được chấp nhận.
3. Sau đó doanh nghiệp hoàn lại một phần tiền.

Nếu “một bản ghi thanh toán” được hiểu là một lần thử, hệ thống có thể theo dõi cả lần thất bại và thành công. Nếu bản ghi chỉ đại diện cho khoản tiền đã được thu, các lần thử thất bại không thuộc cùng độ hạt. Hoàn tiền cũng có thể là một loại giao dịch tài chính riêng.

Cần xác minh các khái niệm:

| Khái niệm | Một bản ghi đại diện cho | Câu hỏi cần làm rõ |
|---|---|---|
| Yêu cầu thanh toán | Một yêu cầu xử lý được tạo | Một yêu cầu có thể được gửi lại nhiều lần không? |
| Lần thử thanh toán | Một lần gửi hoặc thực hiện thử | Lần thử có mã riêng từ hệ thống hoặc nhà cung cấp không? |
| Giao dịch thu tiền | Một khoản tiền thực sự được ghi nhận | Thu một phần có được phép không? |
| Giao dịch hoàn tiền | Một khoản tiền được hoàn lại | Một giao dịch thu tiền có thể có nhiều lần hoàn không? |

Tên gọi “thanh toán” có thể được dùng cho cả quy trình, yêu cầu và giao dịch. Phải làm rõ đơn vị ghi nhận trước khi thiết kế quan hệ.

### 4.3. Đơn hàng và kiện hàng giao đi

Một đơn hàng có thể được chia thành nhiều kiện do hàng nằm ở nhiều kho hoặc được giao thành nhiều đợt. Khi đó:

- Một đơn hàng đại diện cho một lần đặt mua.
- Một kiện hàng hoặc lô gửi đại diện cho một đơn vị vận chuyển được bàn giao.
- Một dòng giao hàng đại diện cho phần số lượng của một dòng đơn hàng được đưa vào một kiện.

Nếu dùng “một đơn hàng tương ứng một lần giao hàng”, mô hình có thể không biểu diễn được giao nhiều đợt. Ngược lại, nếu mỗi lần quét mã tại trung tâm vận chuyển được coi là một kiện hàng, hệ thống sẽ nhầm sự kiện theo dõi với đối tượng được vận chuyển.

Cần phân biệt **kiện hàng** và **sự kiện vận chuyển**. Một kiện có thể có nhiều sự kiện quét hoặc cập nhật vị trí trong hành trình.

### 4.4. Tồn kho và ảnh chụp tồn kho

Tồn kho có thể được quản lý theo SKU, kho, vị trí lưu trữ và thời điểm. Một bản ghi chỉ có SKU và số lượng sẽ không đủ nếu cùng SKU tồn tại tại nhiều kho.

Ví dụ phát biểu:

> Một bản ghi ảnh chụp tồn kho đại diện cho số lượng có thể sử dụng của một SKU tại một kho vào thời điểm chốt cuối ngày.

Nếu cần quản lý theo vị trí kệ, độ hạt phải bổ sung vị trí lưu trữ. Nếu cần nhiều lần chụp trong ngày, cần phân biệt các lần chụp. Nếu cần biết các lần nhập, xuất và điều chỉnh, đó là độ hạt của sự kiện biến động tồn kho, khác với ảnh chụp trạng thái.

### 4.5. Tổng hợp doanh số

Một báo cáo có thể yêu cầu doanh số theo ngày, cửa hàng và sản phẩm. Phát biểu độ hạt:

> Một bản ghi đại diện cho tổng doanh số của một sản phẩm tại một cửa hàng trong một ngày nghiệp vụ.

Tổ hợp ngày, cửa hàng và sản phẩm xác định phạm vi của một bản ghi tổng hợp. Nếu báo cáo cần phân tích theo kênh bán hoặc chương trình khuyến mại, các chiều đó cần được giữ lại hoặc có nguồn dữ liệu chi tiết để tính lại.

Không nên trộn bản ghi đơn hàng, dòng đơn hàng và bản ghi tổng hợp doanh số trong cùng một tập dữ liệu mà không phân biệt rõ loại và độ hạt.

## 5. Độ hạt quyết định ý nghĩa thuộc tính và quan hệ

Độ hạt là cơ sở để kiểm tra thuộc tính có thuộc đúng đối tượng hay không.

Ví dụ, nếu độ hạt là **một dòng đơn hàng**, các thuộc tính như số lượng, giá bán tại thời điểm đặt và mức giảm giá của dòng có ý nghĩa trực tiếp. Nếu độ hạt là **một đơn hàng**, tổng tiền hoặc thời điểm đặt có thể thuộc cấp đơn. Tên sản phẩm và giá niêm yết hiện tại lại có thể thuộc danh mục sản phẩm, với quy tắc thay đổi riêng.

Một thuộc tính có vẻ hợp lý ở một mức có thể trở nên mơ hồ ở mức khác:

- **Số lượng:** số lượng của một dòng hàng, hay tổng số lượng của toàn đơn?
- **Giá:** giá niêm yết hiện tại, giá đã chốt khi đặt, hay giá sau giảm?
- **Trạng thái:** trạng thái đơn, trạng thái từng dòng, trạng thái thanh toán hay trạng thái giao hàng?
- **Thời điểm:** thời điểm tạo đơn, thời điểm thanh toán, thời điểm giao hay thời điểm ghi nhận doanh thu?

Nếu một thuộc tính có nhiều giá trị ở cùng một độ hạt, cần xem lại mô hình hoặc xác định rõ tập hợp giá trị đó. Ví dụ, một đơn có nhiều sản phẩm nên “sản phẩm” không phải thuộc tính đơn trị đơn giản của đơn hàng.

### 5.1. Độ hạt và bội số quan hệ

Từ phát biểu độ hạt, có thể suy luận những câu hỏi về cardinality:

- Một đơn hàng có thể có bao nhiêu dòng đơn hàng?
- Một dòng đơn hàng có thể được chia vào bao nhiêu kiện?
- Một đơn hàng có thể có bao nhiêu lần thử thanh toán?
- Một khách hàng có thể tạo bao nhiêu đơn hàng?
- Một kho có thể lưu bao nhiêu SKU?

Ví dụ sơ đồ khái niệm minh họa:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_LINE : contains
    PRODUCT_VARIANT ||--o{ ORDER_LINE : selected_as
    ORDER ||--o{ PAYMENT_ATTEMPT : has
    ORDER ||--o{ SHIPMENT : fulfilled_by
    SHIPMENT ||--o{ SHIPMENT_LINE : includes
    ORDER_LINE ||--o{ SHIPMENT_LINE : allocated_to
~~~

Sơ đồ chỉ minh họa một cách hiểu thường gặp. Các lực lượng tối thiểu, quy tắc chia dòng, thanh toán một phần và chia nhiều kiện phải được xác nhận. Độ hạt giúp đặt đúng câu hỏi nhưng không thay thế việc xác nhận quy tắc nghiệp vụ.

## 6. Độ hạt trong các kiểu mô hình dữ liệu

Một khái niệm nghiệp vụ có thể được biểu diễn bằng các cấu trúc khác nhau. Dù chọn kiểu lưu trữ nào, ý nghĩa của một instance hoặc bản ghi phải nhất quán.

| Kiểu mô hình | Độ hạt cần làm rõ | Ví dụ |
|---|---|---|
| Quan hệ | Một hàng của thực thể hoặc bảng chi tiết đại diện cho đối tượng nào | Một hàng đơn hàng; một hàng dòng đơn hàng |
| Document | Một document đại diện cho aggregate hoặc đối tượng nghiệp vụ nào; phần tử lồng nhau đại diện cho điều gì | Một document cho một đơn, mảng dòng hàng có một phần tử cho mỗi dòng đơn |
| Đồ thị | Một nút đại diện cho loại đối tượng nào; một cạnh đại diện cho một quan hệ hay một lần quan hệ xảy ra | Nút Order; cạnh PLACED biểu diễn khách hàng đặt đơn |
| Phân tích | Một dòng fact đại diện cho sự kiện, trạng thái hoặc tổ hợp chiều nào | Một dòng doanh số theo dòng đơn; một ảnh chụp tồn kho theo SKU, kho và ngày |

### 6.1. Mô hình quan hệ

Trong mô hình quan hệ, độ hạt của một bảng thường được mô tả bằng ý nghĩa của một hàng. Một bảng ORDER có thể có một hàng cho mỗi đơn; ORDER_LINE có một hàng cho mỗi dòng hàng.

Khóa chính được chọn để phân biệt các hàng, nhưng **khóa không tự định nghĩa ý nghĩa nghiệp vụ của độ hạt**. Một ID duy nhất có thể làm cho hai hàng khác nhau về mặt kỹ thuật, nhưng vẫn không trả lời được chúng đại diện cho hai sự kiện, hai phiên bản hay một bản ghi bị nhập trùng.

Cần xác định độ hạt trước, rồi mới tìm định danh và ràng buộc phù hợp.

### 6.2. Mô hình document

Một document có thể đại diện cho một aggregate, chẳng hạn một đơn hàng cùng các dòng hàng của nó. Khi đó, document có độ hạt là một đơn hàng, còn từng phần tử trong mảng dòng hàng có độ hạt là một dòng đơn hàng.

Không nên giả định rằng mọi mảng trong document đều có cùng một độ hạt hoặc có thể được thay thế bằng một tập giá trị không định danh. Nếu cần cập nhật, truy vấn, lưu lịch sử hoặc tham chiếu riêng từng phần tử, phải hiểu rõ đơn vị của phần tử đó.

### 6.3. Mô hình đồ thị

Trong đồ thị, nút có độ hạt của đối tượng mà nút đại diện; cạnh có độ hạt của quan hệ được biểu diễn.

Ví dụ, một nút CUSTOMER đại diện cho một khách hàng, một nút ORDER đại diện cho một đơn hàng, và cạnh PLACED biểu diễn quan hệ khách hàng đã đặt đơn. Nếu cần lưu nhiều lần tương tác giữa cùng hai chủ thể, cần xác định cạnh là quan hệ hiện tại hay từng lần xảy ra. Một quan hệ thành viên có hiệu lực theo thời gian có thể cần thuộc tính thời hạn hoặc một nút sự kiện trung gian, tùy yêu cầu truy vấn và lịch sử.

### 6.4. Mô hình phân tích

Trong mô hình phân tích, độ hạt của bảng sự kiện hoặc bảng fact phải được phát biểu trước khi chọn chỉ số và chiều.

Ví dụ:

- Fact bán hàng ở độ hạt một dòng đơn hàng;
- Fact sự kiện thanh toán ở độ hạt một lần thử hoặc một giao dịch thu tiền;
- Fact ảnh chụp tồn kho ở độ hạt một SKU, một kho và một thời điểm chụp;
- Fact tổng hợp doanh số ở độ hạt một sản phẩm, một cửa hàng và một ngày.

Các loại chỉ số có cách cộng gộp khác nhau. Số lượng bán theo dòng đơn hàng có thể cộng theo thời gian trong điều kiện nghiệp vụ phù hợp; số lượng tồn kho ở ảnh chụp cuối ngày thường không được cộng qua nhiều ngày để tạo ra “tồn kho tổng”. Cần hiểu độ hạt và tính chất của chỉ số trước khi thiết kế báo cáo.

## 7. Độ hạt và định danh

Sau khi xác định một bản ghi đại diện cho điều gì, bước tiếp theo là tìm cách phân biệt hai bản ghi hợp lệ.

Có ba khái niệm cần tách biệt:

- **Độ hạt:** bản ghi đại diện cho đơn vị nghiệp vụ nào.
- **Định danh:** cách nhận biết một instance cụ thể.
- **Khóa:** thuộc tính hoặc tập thuộc tính được dùng trong mô hình lưu trữ để tham chiếu hoặc bảo đảm tính duy nhất.

Ví dụ, độ hạt của dòng đơn hàng có thể là “mỗi dòng hàng được ghi nhận trong một đơn”. Định danh có thể là số thứ tự dòng trong phạm vi đơn hoặc một mã dòng riêng. Việc chọn khóa cụ thể cần xem xét khả năng chỉnh sửa, tích hợp, lịch sử và ràng buộc kỹ thuật ở bước thiết kế tiếp theo.

Một số câu hỏi kiểm tra:

- Định danh có duy nhất trong toàn hệ thống hay chỉ trong một đơn hàng?
- Một dòng có thể bị xóa rồi tạo lại với cùng mã không?
- Khi đơn được sao chép hoặc nhập từ hệ thống khác, định danh có được giữ nguyên không?
- Có cần phân biệt hai lần phát sinh cùng loại cho cùng một đối tượng không?
- Bản ghi có cần lịch sử phiên bản hoặc hiệu lực theo thời gian không?

Không nên dùng ID tự tăng để che đi một độ hạt chưa được định nghĩa. Tính duy nhất về kỹ thuật không bảo đảm rằng mô hình đã phản ánh đúng nghiệp vụ.

## 8. Độ hạt thay đổi theo thời gian và lịch sử

Một số khái niệm cần lưu nhiều lần thay đổi. Cần phân biệt bản ghi hiện tại, phiên bản lịch sử và sự kiện thay đổi.

Ví dụ, một khách hàng có thể đổi địa chỉ nhiều lần. Có ít nhất ba cách hiểu khác nhau:

- Một bản ghi khách hàng chứa địa chỉ hiện tại;
- Một bản ghi địa chỉ theo mỗi phiên bản có hiệu lực;
- Một sự kiện cho mỗi lần khách hàng thay đổi địa chỉ.

Ba cách này có độ hạt khác nhau và trả lời các câu hỏi khác nhau. Nếu yêu cầu chỉ cần địa chỉ hiện tại, có thể không cần lưu mọi lần thay đổi. Nếu cần kiểm toán hoặc tái dựng đơn hàng trong quá khứ, lịch sử địa chỉ có thể cần được quản lý.

Tương tự, trạng thái đơn hàng hiện tại không giống lịch sử chuyển trạng thái. Một bản ghi trạng thái hiện tại đại diện cho tình trạng tại lúc đọc; một bản ghi lịch sử chuyển trạng thái đại diện cho một lần chuyển từ trạng thái trước sang trạng thái sau.

Khi yêu cầu lịch sử xuất hiện, cần hỏi nghiệp vụ muốn:

- Biết giá trị hiện tại;
- Biết giá trị tại một thời điểm trong quá khứ;
- Biết ai đã thay đổi và thay đổi khi nào;
- Hay tái dựng toàn bộ chuỗi sự kiện đã dẫn tới trạng thái hiện tại.

Mỗi mục tiêu có thể cần độ hạt và cấu trúc khác nhau.

## 9. Quy trình xác định và xác nhận độ hạt

Có thể dùng quy trình sau trong các buổi khảo sát và mô hình hóa khái niệm.

### Bước 1: Chọn khái niệm hoặc quy trình cần mô hình hóa

Bắt đầu từ yêu cầu nghiệp vụ cụ thể, chẳng hạn đặt hàng, thanh toán, giao hàng hoặc quản lý tồn kho. Ghi lại động từ và danh từ quan trọng, nhưng chưa quyết định mỗi danh từ là một thực thể.

### Bước 2: Xác định đơn vị được theo dõi

Hỏi hệ thống cần phân biệt từng đối tượng, từng lần xảy ra hay từng trạng thái. Yêu cầu một bản ghi cho mỗi khách hàng, mỗi đơn, mỗi dòng hàng, mỗi lần thử hay mỗi lần chụp?

### Bước 3: Mô tả điều kiện tạo một instance

Xác định sự kiện hoặc điều kiện khiến đối tượng được xem là đã tồn tại. Ví dụ, đơn được tạo khi nào: lúc bắt đầu giỏ hàng, lúc gửi yêu cầu đặt mua hay sau khi hệ thống xác nhận?

### Bước 4: Xác định phạm vi và thời gian

Làm rõ đối tượng thuộc phạm vi nào, có cần phân biệt theo kho, cửa hàng, tổ chức, kênh hoặc kỳ thời gian không. Nếu dữ liệu có lịch sử, xác định thời điểm hiệu lực và thời điểm ghi nhận.

### Bước 5: Viết một câu phát biểu độ hạt

Dùng câu ngắn, tránh từ chung chung như “một giao dịch”, “một bản ghi”, “một mục” nếu chưa giải thích đơn vị cụ thể.

### Bước 6: Kiểm tra thuộc tính và quan hệ

Xem từng thuộc tính có một giá trị rõ ở độ hạt đã chọn không. Xác định một instance liên quan đến bao nhiêu instance khác và có trường hợp chia tách, gộp hoặc lặp lại nào.

### Bước 7: Thử bằng dữ liệu và trường hợp ngoại lệ

Dùng ví dụ thực tế: đơn nhiều dòng, thanh toán thất bại rồi thử lại, giao hàng nhiều kiện, tồn kho ở nhiều kho, hoặc cùng sản phẩm xuất hiện nhiều lần trong một đơn. Nếu phát biểu không giải thích được các trường hợp này, hãy điều chỉnh hoặc tách độ hạt.

### Bước 8: Xác nhận với người phụ trách nghiệp vụ

Đọc lại phát biểu và một vài ví dụ cho người có trách nhiệm. Xác nhận cả trường hợp bình thường và ngoại lệ. Ghi rõ quyết định, người xác nhận, ngày xác nhận và câu hỏi còn mở.

~~~mermaid
flowchart TD
    A["Yêu cầu hoặc quy trình nghiệp vụ"] --> B["Chọn khái niệm cần mô hình hóa"]
    B --> C["Xác định đối tượng, sự kiện hay trạng thái"]
    C --> D["Mô tả một instance đại diện cho điều gì"]
    D --> E["Xác định phạm vi và thời gian"]
    E --> F["Kiểm tra thuộc tính, quan hệ và ngoại lệ"]
    F --> G{"Người nghiệp vụ xác nhận?"}
    G -->|Chưa| H["Ghi câu hỏi và điều chỉnh phát biểu"]
    H --> D
    G -->|Rồi| I["Ghi nhận độ hạt đã thống nhất"]
    I --> J["Tiếp tục mô hình hóa định danh và ràng buộc"]
~~~

## 10. Những lỗi thường gặp khi xác định độ hạt

1. **Dùng tên bảng thay cho phát biểu độ hạt:** tên ORDER không cho biết một hàng là một đơn, một dòng hàng hay một lần thay đổi đơn.
2. **Trộn cấp tổng thể và cấp chi tiết:** lưu thuộc tính của từng dòng hàng cùng với nhiều dòng hàng trong một cấu trúc nhưng không xác định cách phân biệt từng dòng.
3. **Trộn sự kiện và trạng thái:** một lần chuyển trạng thái là sự kiện; trạng thái hiện tại là kết quả sau các sự kiện.
4. **Trộn giao dịch và tổng hợp:** bản ghi tổng doanh số ngày không đại diện cho một đơn hàng riêng.
5. **Mô tả thời gian không rõ:** “mỗi ngày” có thể là ngày lịch, ngày nghiệp vụ, cuối ngày hoặc khoảng thời gian 24 giờ.
6. **Giả định một đối tượng chỉ có một đối tượng liên quan:** một đơn có thể được giao nhiều kiện hoặc thanh toán nhiều lần.
7. **Dùng khóa để thay thế định nghĩa nghiệp vụ:** ID duy nhất không cho biết bản ghi đại diện cho điều gì.
8. **Không thử trường hợp ngoại lệ:** mô hình chỉ đúng với ví dụ đơn giản nhưng thất bại khi đơn có nhiều dòng, thanh toán nhiều lần hoặc giao nhiều đợt.
9. **Thay đổi độ hạt mà không ghi nhận:** khi một báo cáo chuyển từ cấp đơn sang cấp dòng đơn, các chỉ số và phép đếm có thể thay đổi đáng kể.
10. **Cộng gộp chỉ số không phù hợp:** số dư và tồn kho tại một thời điểm thường không thể cộng qua các thời điểm như doanh số giao dịch.

## 11. Checklist trước khi chốt mô hình khái niệm

- [ ] Mỗi thực thể hoặc loại bản ghi quan trọng có một câu mô tả độ hạt.
- [ ] Câu mô tả nêu rõ đơn vị nghiệp vụ, phạm vi và thời gian nếu có.
- [ ] Đã phân biệt đối tượng, dòng chi tiết, sự kiện, ảnh chụp và dữ liệu tổng hợp.
- [ ] Điều kiện tạo một instance đã được xác định.
- [ ] Các thuộc tính đều có ý nghĩa ở đúng độ hạt.
- [ ] Đã kiểm tra trường hợp một đối tượng liên quan đến nhiều đối tượng khác.
- [ ] Đã thử các tình huống lặp, chia tách, giao nhiều đợt, thử lại và hoàn trả nếu có.
- [ ] Độ hạt của dữ liệu phân tích đã nêu rõ các chiều và kỳ tổng hợp.
- [ ] Không dùng khóa kỹ thuật làm lời giải cho một định nghĩa nghiệp vụ mơ hồ.
- [ ] Người phụ trách nghiệp vụ đã xác nhận hoặc các câu hỏi chưa rõ đã được ghi lại.

## 12. Bài tập thực hành

Một hệ thống bán hàng có các yêu cầu:

- Một khách hàng có thể tạo nhiều đơn hàng.
- Mỗi đơn có thể chứa nhiều dòng sản phẩm.
- Khách hàng có thể thử thanh toán nhiều lần.
- Một đơn có thể được giao thành nhiều kiện.
- Hệ thống ghi nhận số lượng tồn theo sản phẩm, kho và thời điểm chốt mỗi ngày.
- Báo cáo cần doanh số theo ngày, cửa hàng và sản phẩm.

Hãy viết phát biểu độ hạt cho từng khái niệm hoặc tập dữ liệu sau:

1. Khách hàng.
2. Đơn hàng.
3. Dòng đơn hàng.
4. Lần thử thanh toán.
5. Kiện hàng.
6. Dòng giao hàng.
7. Ảnh chụp tồn kho.
8. Bản ghi doanh số tổng hợp.

**Gợi ý đáp án:**

| Khái niệm | Phát biểu độ hạt tham khảo |
|---|---|
| Khách hàng | Một instance đại diện cho một chủ thể khách hàng được doanh nghiệp quản lý trong phạm vi bán hàng. |
| Đơn hàng | Một instance đại diện cho một lần đặt mua được hệ thống ghi nhận theo quy trình đặt hàng. |
| Dòng đơn hàng | Một instance đại diện cho một dòng hàng được ghi nhận trong một đơn, theo quy tắc tạo dòng của nghiệp vụ. |
| Lần thử thanh toán | Một instance đại diện cho một lần gửi yêu cầu xử lý thanh toán cho một đơn hoặc khoản phải thu. |
| Kiện hàng | Một instance đại diện cho một đơn vị hàng hóa được đóng gói và bàn giao như một đơn vị vận chuyển. |
| Dòng giao hàng | Một instance đại diện cho phần số lượng của một dòng đơn hàng được phân bổ vào một kiện cụ thể. |
| Ảnh chụp tồn kho | Một instance đại diện cho lượng tồn của một sản phẩm tại một kho vào thời điểm chốt tồn hằng ngày. |
| Doanh số tổng hợp | Một bản ghi đại diện cho doanh số của một sản phẩm tại một cửa hàng trong một ngày nghiệp vụ, theo quy tắc ghi nhận doanh thu đã thống nhất. |

Các câu trả lời trên là phát biểu khởi đầu. Trong dự án thật, cần xác nhận các giả định như một đơn có thể chứa dòng trùng sản phẩm hay không, một lần thử thanh toán có thể tạo nhiều giao dịch hay không, kiện hàng có thể chứa dòng từ nhiều đơn không, và doanh số được ghi nhận theo ngày đặt hàng hay ngày hoàn tất giao dịch.

**Kết quả cần đạt:** mỗi cấu trúc trong mô hình có một ý nghĩa đơn vị rõ ràng. Khi độ hạt được xác nhận, nhóm có thể tiếp tục xác định định danh, thuộc tính, cardinality, ràng buộc và cách biểu diễn phù hợp mà không làm lẫn đơn hàng với dòng hàng, sự kiện hay số liệu tổng hợp.

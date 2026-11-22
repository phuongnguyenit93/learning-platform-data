# Nhận diện tác nhân, hành động, kết quả và thông tin cần thiết

## Vì sao cần khám phá bốn yếu tố này?

Domain-Driven Design (DDD) bắt đầu từ việc hiểu cách nghiệp vụ thực sự vận hành. Đội phát triển cần biết ai đang cố gắng hoàn thành công việc gì, họ thực hiện những hành động nào, kết quả nào được xem là thành công và thông tin nào cần có để đưa ra quyết định. Nếu chỉ thu thập danh sách màn hình, API hoặc trường dữ liệu, nhóm có thể xây dựng phần mềm đúng với mô tả giao diện nhưng vẫn sai với cách tổ chức thực hiện công việc.

Trong chương **Khám phá nghiệp vụ**, việc nhận diện tác nhân, hành động, kết quả và thông tin giúp biến những câu chuyện rời rạc thành một bức tranh có thể kiểm chứng. Bốn yếu tố này tạo nền tảng cho ngôn ngữ chung giữa chuyên gia nghiệp vụ và đội phát triển. Chúng cũng giúp nhóm nhận ra quy tắc, điểm bàn giao, ngoại lệ và ranh giới trách nhiệm trước khi đi sâu vào thiết kế mô hình miền.

Hãy xem đây là một cách đặt câu hỏi có hệ thống khi tìm hiểu một quy trình. Không phải mọi quy trình đều có đúng một tác nhân, một hành động hay một kết quả. Một tình huống thực tế thường có nhiều vai trò cùng tham gia, nhiều bước xử lý và nhiều nhánh kết quả.

Sau bài học, người học có thể:

- Phân biệt tác nhân, hành động, kết quả và thông tin trong một tình huống nghiệp vụ.
- Mô tả một luồng công việc bằng ngôn ngữ của chuyên gia nghiệp vụ.
- Tìm ra quy tắc và ngoại lệ chi phối hành động.
- Ghi nhận kết quả nghiệp vụ đủ rõ để các bên cùng xác nhận.
- Dùng kết quả khám phá làm đầu vào cho các hoạt động mô hình hóa DDD tiếp theo.

## Bốn yếu tố cần nhận diện

### 1. Tác nhân: Ai tham gia hoặc khởi xướng công việc?

Tác nhân là một vai trò có mục tiêu hoặc trách nhiệm trong tình huống nghiệp vụ. Tác nhân có thể là:

- **Con người:** khách hàng, nhân viên bán hàng, nhân viên kho, kế toán, quản lý.
- **Tổ chức hoặc đối tác:** ngân hàng, đơn vị vận chuyển, nhà cung cấp, cơ quan quản lý.
- **Hệ thống bên ngoài:** cổng thanh toán, dịch vụ xác minh danh tính hoặc nền tảng của đối tác.
- **Một tiến trình được kích hoạt theo thời gian hoặc sự kiện:** ví dụ công việc đối soát chạy vào cuối ngày. Trong trường hợp này, cần ghi rõ tác nhân khởi phát là lịch chạy, sự kiện bên ngoài hay một vai trò chịu trách nhiệm vận hành.

Nên mô tả tác nhân bằng **vai trò**, không chỉ bằng tên một cá nhân, tài khoản đăng nhập hoặc màn hình. Một người có thể đảm nhiệm nhiều vai trò; nhiều người cũng có thể cùng đảm nhiệm một vai trò. Vai trò mới là điều quan trọng đối với mô hình nghiệp vụ.

Khi phân tích, hãy phân biệt các trách nhiệm sau:

- Người hoặc tổ chức khởi xướng yêu cầu.
- Người trực tiếp thực hiện một bước.
- Người có quyền quyết định hoặc phê duyệt.
- Người nhận kết quả hoặc chịu ảnh hưởng từ kết quả.
- Hệ thống hay đối tác cung cấp thông tin hoặc thực hiện một phần công việc.

Các trách nhiệm này có thể thuộc về cùng một tác nhân, nhưng không nên mặc định như vậy. Ví dụ, khách hàng gửi yêu cầu hoàn tiền, nhân viên chăm sóc khách hàng kiểm tra điều kiện, quản lý phê duyệt trường hợp ngoại lệ và bộ phận kế toán thực hiện hoàn tiền.

**Câu hỏi khám phá:** Ai muốn công việc này được thực hiện? Ai bắt đầu? Ai có quyền quyết định? Ai thực hiện? Ai nhận kết quả? Có đối tác hoặc hệ thống bên ngoài nào tham gia không?

### 2. Hành động: Tác nhân đang làm gì và muốn đạt điều gì?

Hành động mô tả việc tác nhân thực hiện để đạt một mục tiêu nghiệp vụ. Hãy diễn đạt bằng động từ gắn với đối tượng cụ thể, chẳng hạn:

- Gửi yêu cầu đặt hàng.
- Xác nhận thông tin giao hàng.
- Phê duyệt khoản hoàn tiền.
- Giữ chỗ một phòng.
- Đối soát khoản thanh toán.

Một hành động thường có các thành phần cần làm rõ:

1. **Ý định:** tác nhân muốn đạt được điều gì?
2. **Điểm khởi phát:** điều gì khiến hành động bắt đầu?
3. **Điều kiện trước:** điều gì phải đúng trước khi hành động được chấp nhận?
4. **Thông tin sử dụng:** tác nhân cần biết hoặc cung cấp điều gì?
5. **Quy tắc quyết định:** tiêu chí nào quyết định hành động được chấp nhận, từ chối hoặc chuyển sang xử lý khác?
6. **Kết quả:** sau hành động, trạng thái nghiệp vụ nào thay đổi?

Không nên mô tả hành động chỉ bằng thao tác giao diện như “nhấn nút Lưu” hoặc chi tiết kỹ thuật như “gọi API POST”. Những mô tả đó có thể hữu ích khi thiết kế giao diện hoặc hệ thống, nhưng chưa nói được mục đích nghiệp vụ. Hãy hỏi người dùng đang cố gắng hoàn thành việc gì khi họ nhấn nút đó.

Trong DDD, có thể xem một yêu cầu thể hiện ý định thay đổi trạng thái miền là một **command**. Ví dụ, “Gửi đơn hàng” là yêu cầu thực hiện một hành động. Command có thể được chấp nhận hoặc từ chối tùy theo quy tắc nghiệp vụ. Không phải mọi hành động quan sát được đều cần trở thành command trong mô hình phần mềm; đây là cách diễn đạt giúp nhóm làm rõ ý định và quyết định nghiệp vụ.

**Câu hỏi khám phá:** Tác nhân đang làm gì? Vì sao họ làm việc đó? Điều gì kích hoạt hành động? Có điều kiện nào phải thỏa mãn? Trường hợp nào hành động bị từ chối hoặc cần người khác can thiệp?

### 3. Kết quả: Điều gì thay đổi sau hành động?

Kết quả là điều có ý nghĩa đối với nghiệp vụ sau khi một hành động hoặc một chuỗi hành động diễn ra. Kết quả cần đủ cụ thể để các bên có thể xác nhận rằng công việc đã hoàn tất, thất bại hoặc chuyển sang một trạng thái khác.

Kết quả có thể là:

- Một yêu cầu được tiếp nhận, chấp thuận hoặc từ chối.
- Một đơn hàng chuyển từ trạng thái chờ xác nhận sang đã xác nhận.
- Một khoản thanh toán được ủy quyền hoặc bị từ chối.
- Một lịch hẹn được đặt, thay đổi hoặc hủy.
- Một lô hàng được đóng gói và bàn giao cho đơn vị vận chuyển.
- Một ngoại lệ được chuyển đến người có thẩm quyền xử lý.

Hãy phân biệt **kết quả nghiệp vụ** với phản hồi kỹ thuật. Thông báo “HTTP 200”, một dòng dữ liệu được ghi vào cơ sở dữ liệu hoặc thông báo “Đã lưu” trên giao diện chưa chắc đã chứng minh mục tiêu nghiệp vụ hoàn thành. Cần hỏi điều gì đã thay đổi trong thực tế và ai công nhận thay đổi đó.

Trong DDD, một kết quả đã xảy ra và có ý nghĩa đối với miền thường có thể được diễn đạt thành **domain event**. Tên sự kiện nên mô tả điều đã xảy ra, thường dùng dạng quá khứ: “Đơn hàng đã được xác nhận”, “Thanh toán đã được chấp thuận”, “Lô hàng đã được bàn giao”.

Phân biệt command và domain event:

| Góc nhìn | Command | Domain event |
|---|---|---|
| Ý nghĩa | Yêu cầu thực hiện điều gì đó | Ghi nhận điều đã xảy ra |
| Cách diễn đạt | Động từ ở dạng yêu cầu | Sự kiện ở dạng đã xảy ra |
| Ví dụ | Gửi đơn hàng | Đơn hàng đã được gửi |
| Khả năng | Có thể bị từ chối | Mô tả một sự việc đã xảy ra |

Không phải mọi kết quả đều cần phát ra domain event trong thiết kế cuối cùng. Hãy dùng khái niệm này để nhận diện những thay đổi quan trọng đối với nghiệp vụ, sau đó mới quyết định sự kiện nào cần được mô hình hóa hoặc truyền sang ngữ cảnh khác.

**Câu hỏi khám phá:** Làm sao biết công việc đã hoàn tất? Trạng thái nào thay đổi? Ai xác nhận kết quả? Kết quả có tạo ra nghĩa vụ hoặc công việc tiếp theo không? Nếu thất bại thì trạng thái và cách xử lý là gì?

### 4. Thông tin cần thiết: Cần biết gì để hành động và ra quyết định?

Thông tin cần thiết là dữ liệu hoặc tri thức mà tác nhân sử dụng để thực hiện hành động, kiểm tra điều kiện và đánh giá kết quả. Hãy tìm hiểu ý nghĩa nghiệp vụ của thông tin trước khi nghĩ đến kiểu dữ liệu hoặc cách lưu trữ.

Có thể phân loại thông tin theo mục đích:

- **Thông tin đầu vào:** do khách hàng, nhân viên hoặc đối tác cung cấp, ví dụ số lượng sản phẩm, địa chỉ nhận hàng, lý do yêu cầu hoàn tiền.
- **Thông tin tham chiếu:** được tra cứu để ra quyết định, ví dụ bảng giá, chính sách đổi trả, hạn mức tín dụng, danh sách khu vực giao hàng.
- **Thông tin trạng thái:** cho biết tình hình hiện tại, ví dụ số lượng tồn có thể bán, trạng thái thanh toán hoặc trạng thái phê duyệt.
- **Thông tin phát sinh:** được tính toán hoặc tạo ra trong quá trình xử lý, ví dụ tổng tiền, mức chiết khấu, mã xác nhận.
- **Thông tin kết quả:** được trả lại cho tác nhân hoặc dùng để kích hoạt bước tiếp theo, ví dụ mã đơn hàng, thời hạn giao dự kiến hoặc lý do từ chối.

Với mỗi thông tin, hãy hỏi thêm:

- Ai cung cấp hoặc chịu trách nhiệm về độ chính xác?
- Thông tin được lấy từ đâu và có đáng tin cậy không?
- Có bắt buộc trong mọi trường hợp không, hay chỉ bắt buộc khi có điều kiện?
- Giá trị có thể thay đổi theo thời gian không? Tại thời điểm ra quyết định cần dùng giá trị hiện tại hay giá trị tại thời điểm giao dịch?
- Nếu thiếu, sai hoặc mâu thuẫn thì nghiệp vụ xử lý thế nào?

Đặc biệt, đừng mặc định mọi trường trên biểu mẫu đều là thông tin nghiệp vụ bắt buộc. Một trường có thể chỉ phục vụ giao diện, báo cáo hoặc tích hợp. Ngược lại, có những thông tin quan trọng trong quyết định nghiệp vụ nhưng không xuất hiện trực tiếp trên biểu mẫu, chẳng hạn chính sách có hiệu lực tại thời điểm giao dịch.

**Câu hỏi khám phá:** Tác nhân cần biết gì trước khi hành động? Thông tin nào ảnh hưởng đến quyết định? Nguồn của thông tin là ai? Khi thông tin thay đổi thì kết quả có thay đổi không?

## Khám phá một quy trình theo trình tự

Bốn yếu tố có liên hệ với nhau. Tác nhân có mục tiêu, thực hiện hành động, sử dụng thông tin và tạo ra kết quả. Quy tắc nghiệp vụ quyết định hành động nào được phép và kết quả nào có thể xảy ra. Khi tìm hiểu, hãy đi theo một tình huống cụ thể từ lúc bắt đầu đến khi kết thúc thay vì hỏi chung chung về toàn bộ hệ thống.

### Bước 1: Chốt phạm vi và tình huống

Chọn một tình huống có điểm bắt đầu và kết thúc tương đối rõ, ví dụ “khách hàng đặt một đơn hàng có giao tận nơi”. Nêu mục tiêu nghiệp vụ và những gì nằm ngoài phạm vi. Nếu cuộc trao đổi chuyển sang đổi trả, quản lý kho hoặc kế toán, hãy ghi nhận mối liên hệ nhưng tách thành tình huống riêng khi cần phân tích sâu.

### Bước 2: Xác định tác nhân và mục tiêu

Liệt kê các vai trò tham gia. Với mỗi vai trò, ghi rõ mục tiêu, trách nhiệm và quyền quyết định. Kiểm tra xem một vai trò có đang bị gộp với một vai trò khác chỉ vì cùng một người thực hiện hay không.

### Bước 3: Kể lại từng hành động

Yêu cầu chuyên gia nghiệp vụ kể một trường hợp thực tế gần đây. Ghi từng hành động theo cấu trúc “vai trò + động từ + đối tượng”. Hỏi điều gì kích hoạt bước tiếp theo, ai tiếp nhận và có quyết định nào được đưa ra.

### Bước 4: Ghi nhận thông tin và quy tắc

Ở từng hành động, ghi thông tin được cung cấp, thông tin được tra cứu và thông tin được tính toán. Hỏi vì sao thông tin đó cần thiết. Nếu một giá trị quyết định kết quả, hãy tìm quy tắc liên quan và xác định ai có quyền thay đổi quy tắc.

### Bước 5: Xác định kết quả và trạng thái

Mô tả điều xảy ra sau mỗi hành động. Dùng từ ngữ nghiệp vụ có thể kiểm chứng, ví dụ “đơn hàng được xác nhận” thay cho “hệ thống xử lý thành công”. Ghi nhận kết quả thất bại, bị từ chối, chờ xử lý hoặc cần phê duyệt.

### Bước 6: Tìm ngoại lệ và kiểm chứng

Đừng chỉ hỏi quy trình chuẩn. Hãy hỏi điều gì xảy ra khi thiếu thông tin, thanh toán thất bại, hàng không đủ, đối tác không phản hồi hoặc người phê duyệt vắng mặt. Sau đó đọc lại luồng đã ghi với chuyên gia nghiệp vụ, dùng ví dụ thật và trường hợp phản ví dụ để xác nhận.

## Ví dụ: Khách hàng đặt hàng trực tuyến

Giả sử nhóm đang tìm hiểu quy trình đặt hàng tại một cửa hàng trực tuyến. Đây là ví dụ minh họa; chính sách cụ thể phải được xác nhận với doanh nghiệp thực tế.

### Nhận diện tác nhân, hành động, thông tin và kết quả

| Tác nhân / vai trò | Hành động | Thông tin cần thiết | Kết quả nghiệp vụ |
|---|---|---|---|
| Khách hàng | Gửi yêu cầu đặt hàng | Sản phẩm, số lượng, thông tin người nhận, địa chỉ giao hàng, phương thức thanh toán, mã ưu đãi nếu có | Yêu cầu đặt hàng được tiếp nhận và có mã tham chiếu |
| Nhân viên xử lý đơn hàng hoặc năng lực xử lý đơn | Kiểm tra và quyết định tiếp nhận đơn | Chi tiết đơn, giá áp dụng, tình trạng có thể đáp ứng, chính sách bán hàng | Đơn được chấp nhận, từ chối hoặc chuyển sang xử lý ngoại lệ |
| Cổng thanh toán | Thực hiện yêu cầu thanh toán hoặc ủy quyền | Số tiền, thông tin giao dịch, mã tham chiếu và dữ liệu xác thực được phép sử dụng | Thanh toán được chấp thuận hoặc bị từ chối |
| Nhân viên kho | Chuẩn bị và bàn giao hàng | Đơn đã được xác nhận, sản phẩm cần lấy, vị trí lưu kho, yêu cầu đóng gói | Hàng được chuẩn bị và bàn giao cho đơn vị vận chuyển |
| Đơn vị vận chuyển | Tiếp nhận và vận chuyển kiện hàng | Địa chỉ, thông tin người nhận, mã kiện hàng, yêu cầu giao hàng | Kiện hàng được tiếp nhận, đang vận chuyển, giao thành công hoặc giao không thành công |

Trong một doanh nghiệp, một số bước có thể được tự động hóa hoặc do vai trò khác đảm nhiệm. Bảng này mô tả trách nhiệm nghiệp vụ cần khám phá, không khẳng định tổ chức nào cũng có cùng cơ cấu nhân sự.

### Làm rõ các quyết định nghiệp vụ

Khi khách hàng gửi đơn, nhóm cần hỏi:

- Giá nào được áp dụng: giá tại thời điểm khách hàng thêm sản phẩm vào giỏ hay giá tại thời điểm gửi đơn?
- Mã ưu đãi có được dùng cùng chương trình khuyến mãi khác không?
- Nếu số lượng có thể bán không đủ, đơn bị từ chối, chờ bổ sung hay được tách thành nhiều lần giao?
- Địa chỉ ngoài khu vực phục vụ được xử lý thế nào?
- Khi nào đơn được xem là đã xác nhận: sau khi kiểm tra thông tin, sau khi giữ hàng hay sau khi thanh toán được chấp thuận?
- Nếu cổng thanh toán không phản hồi, nhóm có thể thử lại không và làm sao tránh ghi nhận thanh toán hai lần?

Các câu hỏi này làm lộ ra quy tắc và chính sách đang chi phối hành động. Câu trả lời cần đến từ người hiểu và có thẩm quyền về nghiệp vụ; đội phát triển không nên tự đặt ra chính sách dựa trên suy đoán.

### Biểu diễn luồng bằng command và domain event

Một phần luồng có thể được ghi nhận bằng các cặp ý định và kết quả sau:

| Ý định / command | Kết quả / domain event có thể có |
|---|---|
| Gửi đơn hàng | Đơn hàng đã được gửi |
| Xác nhận đơn hàng | Đơn hàng đã được xác nhận |
| Yêu cầu ủy quyền thanh toán | Thanh toán đã được chấp thuận hoặc Thanh toán đã bị từ chối |
| Bàn giao kiện hàng | Kiện hàng đã được bàn giao cho đơn vị vận chuyển |

Các tên trên là cách diễn đạt để trao đổi và khám phá. Khi mô hình hóa, nhóm cần thống nhất ý nghĩa, điều kiện phát sinh và nơi chịu trách nhiệm về từng sự kiện. Ví dụ, “Đơn hàng đã được gửi” không đồng nghĩa với “Đơn hàng đã được xác nhận”; hai sự kiện này biểu thị hai mốc nghiệp vụ khác nhau.

## Mẫu ghi nhận kết quả khám phá

Có thể dùng bảng sau trong buổi phỏng vấn, workshop hoặc khi đọc lại quy trình với chuyên gia nghiệp vụ:

| Bước | Tác nhân / vai trò | Mục tiêu và hành động | Thông tin sử dụng | Quy tắc / quyết định | Kết quả và bước tiếp theo |
|---|---|---|---|---|---|
| 1 | Ai khởi xướng? | Muốn hoàn thành việc gì? | Cần cung cấp gì? | Điều kiện ban đầu? | Điều gì được ghi nhận? |
| 2 | Ai tiếp nhận? | Kiểm tra hoặc xử lý gì? | Tra cứu nguồn nào? | Tiêu chí chấp nhận? | Chấp nhận, từ chối hay chờ? |
| 3 | Ai quyết định? | Phê duyệt hoặc xử lý ngoại lệ? | Bằng chứng nào cần có? | Ai có thẩm quyền? | Quyết định nào được đưa ra? |
| 4 | Ai nhận kết quả? | Thực hiện bước tiếp theo? | Cần thông tin bàn giao nào? | Điều kiện hoàn tất? | Trạng thái cuối là gì? |

Khi tình huống có nhiều nhánh, hãy tạo thêm dòng cho từng nhánh thay vì ép mọi trường hợp vào một luồng duy nhất. Có thể ghi chú riêng các trường hợp chưa rõ để xác minh ở buổi trao đổi tiếp theo.

Một bản ghi ngắn cho mỗi hành động có thể theo mẫu:

~~~text
Tình huống:
Tác nhân khởi xướng:
Tác nhân thực hiện / quyết định:
Mục tiêu:
Hành động:
Điều kiện trước:
Thông tin đầu vào và nguồn:
Thông tin tham chiếu:
Quy tắc nghiệp vụ:
Kết quả thành công:
Kết quả thay thế / ngoại lệ:
Người nhận kết quả:
Thuật ngữ cần thống nhất:
Điểm cần xác minh:
~~~

## Kỹ thuật đặt câu hỏi trong buổi khám phá

Thay vì hỏi “Hệ thống cần những trường dữ liệu nào?”, hãy yêu cầu chuyên gia kể lại một trường hợp cụ thể và đặt câu hỏi theo từng bước:

**Về tác nhân**

- Ai thường bắt đầu công việc này? Có trường hợp nào người khác bắt đầu thay không?
- Ai có quyền phê duyệt, từ chối hoặc sửa quyết định?
- Có đối tác hoặc bộ phận nào tham gia nhưng thường bị bỏ sót không?

**Về hành động**

- Hành động này nhằm giải quyết nhu cầu nào?
- Điều gì khiến anh/chị thực hiện nó vào thời điểm đó?
- Có thể bỏ qua bước này không? Nếu có thì trong điều kiện nào?
- Điều gì khiến hành động phải dừng hoặc chuyển cho người khác?

**Về thông tin**

- Anh/chị cần biết điều gì để quyết định?
- Thông tin đến từ đâu và ai chịu trách nhiệm?
- Nếu thông tin chưa có hoặc không nhất quán thì sao?
- Có thông tin nào cần giữ nguyên theo thời điểm giao dịch không?

**Về kết quả**

- Điều gì chứng minh công việc đã hoàn thành?
- Ai cần được thông báo hoặc tiếp tục xử lý?
- Có những kết quả khác nhau nào ngoài thành công?
- Khi cần sửa hoặc hủy kết quả đã tạo thì quy trình diễn ra thế nào?

Hãy dùng ví dụ và phản ví dụ để kiểm tra định nghĩa. Nếu chuyên gia nói “đơn đã hoàn tất”, hãy hỏi một đơn đã thanh toán nhưng chưa giao có được xem là hoàn tất không. Nếu hai bên hiểu khác nhau, đó là tín hiệu cần làm rõ thuật ngữ hoặc tách các trạng thái nghiệp vụ.

## Từ kết quả khám phá đến mô hình DDD

Việc nhận diện tác nhân, hành động, kết quả và thông tin chưa phải là thiết kế lớp hay cơ sở dữ liệu. Đây là đầu vào để nhóm hiểu miền nghiệp vụ và quyết định mô hình hóa ở bước phù hợp.

- **Ngôn ngữ chung (Ubiquitous Language):** các vai trò, hành động, trạng thái, quy tắc và sự kiện được ghi bằng thuật ngữ mà chuyên gia nghiệp vụ sử dụng. Mỗi thuật ngữ cần có định nghĩa đủ rõ và ví dụ đi kèm.
- **Subdomain:** các nhóm năng lực nghiệp vụ có thể được nhận ra khi nhóm gom những hành động và quy tắc cùng phục vụ một mục tiêu kinh doanh. Việc khám phá giúp nhóm nhìn thấy đâu là năng lực cốt lõi, hỗ trợ hoặc phổ thông.
- **Bounded Context:** khi một thuật ngữ hoặc quy tắc có ý nghĩa khác nhau giữa các nhóm nghiệp vụ, đó có thể là dấu hiệu của những ranh giới mô hình khác nhau. Không nên ép mọi bộ phận dùng một mô hình duy nhất chỉ vì họ cùng nhắc đến một từ.
- **Context Map:** sau khi nhận diện các ngữ cảnh, nhóm có thể làm rõ quan hệ phụ thuộc, trao đổi dữ liệu và cách các ngữ cảnh phối hợp.
- **Entity, Value Object và Aggregate:** thông tin về danh tính, quy tắc, tính bất biến và vòng đời giúp tìm ra các khái niệm miền có thể cần mô hình hóa. Không nên biến mọi danh từ trong cuộc phỏng vấn thành entity hoặc mọi nhóm trường thành aggregate.
- **Repository và Domain Event:** khi đã hiểu ranh giới và trách nhiệm của mô hình, nhóm mới xác định cách truy xuất đối tượng miền và những sự kiện cần được công bố cho phần khác của hệ thống.

Một kỹ thuật hỗ trợ là **Event Storming**. Nhóm có thể cùng chuyên gia nghiệp vụ đặt các domain event theo trình tự thời gian, sau đó bổ sung command, tác nhân, chính sách và hệ thống bên ngoài liên quan. Những điểm có nhiều tranh luận, nhiều ngoại lệ hoặc nhiều cách hiểu khác nhau thường là nơi cần khám phá sâu hơn. Event Storming hỗ trợ cuộc trao đổi; nó không thay thế việc xác minh quy tắc và trách nhiệm với người có hiểu biết nghiệp vụ.

## Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Xem màn hình hoặc tài khoản là tác nhân | Bỏ sót vai trò và trách nhiệm thật | Ghi nhận vai trò nghiệp vụ và mục tiêu của vai trò |
| Mô tả hành động bằng thao tác giao diện | Không hiểu ý định nghiệp vụ phía sau thao tác | Dùng động từ và đối tượng nghiệp vụ |
| Xem phản hồi kỹ thuật là kết quả nghiệp vụ | Không biết công việc thực sự đã hoàn tất chưa | Xác định trạng thái và thay đổi mà chuyên gia công nhận |
| Chỉ ghi luồng thành công | Phần mềm không xử lý đúng từ chối, chờ và ngoại lệ | Hỏi thêm trường hợp thất bại và tình huống biên |
| Coi mọi trường dữ liệu là bắt buộc | Mô hình bị chi phối bởi biểu mẫu hiện tại | Hỏi thông tin nào ảnh hưởng đến quyết định và trong điều kiện nào |
| Gộp nhiều vai trò vì cùng một người thực hiện | Mờ trách nhiệm và quyền hạn | Phân tích theo vai trò, không theo danh tính cá nhân |
| Vội chuyển danh từ thành entity hoặc bảng dữ liệu | Mô hình phản ánh cấu trúc dữ liệu thay vì quy tắc miền | Xác minh danh tính, vòng đời, hành vi và bất biến trước |
| Giả định một thuật ngữ có cùng nghĩa ở mọi nơi | Ngôn ngữ chung trở nên mơ hồ | Ghi ví dụ, định nghĩa và ngữ cảnh sử dụng của thuật ngữ |

## Tiêu chí hoàn thành một lượt khám phá

Một tình huống được khám phá đủ tốt để chuyển sang bước phân tích tiếp theo khi nhóm có thể trả lời rõ:

1. Tình huống bắt đầu khi nào và mục tiêu nghiệp vụ là gì?
2. Những vai trò nào khởi xướng, thực hiện, quyết định và nhận kết quả?
3. Mỗi vai trò thực hiện hành động nào và vì sao?
4. Thông tin nào được cung cấp, tra cứu hoặc tạo ra; nguồn và độ tin cậy của chúng là gì?
5. Quy tắc nào quyết định hành động được chấp nhận, từ chối hoặc chuyển tiếp?
6. Những kết quả thành công, thất bại, chờ xử lý và ngoại lệ nào có thể xảy ra?
7. Các thuật ngữ quan trọng đã được chuyên gia nghiệp vụ xác nhận và có ví dụ minh họa chưa?

Nếu còn câu trả lời chưa rõ, hãy ghi rõ giả định và người cần xác minh. Một mô hình tốt bắt đầu từ hiểu biết được kiểm chứng, không phải từ những chi tiết đội phát triển tự suy ra.

## Kết luận

Nhận diện tác nhân, hành động, kết quả và thông tin là cách tiếp cận nền tảng để khám phá miền nghiệp vụ trong Domain-Driven Design. Bốn yếu tố giúp nhóm hiểu ai đang làm việc gì, cần biết điều gì, tuân theo quy tắc nào và tạo ra thay đổi gì. Khi được kiểm chứng bằng tình huống thực tế và thuật ngữ thống nhất, kết quả khám phá trở thành cơ sở đáng tin cậy cho việc xác định subdomain, bounded context và xây dựng mô hình miền phù hợp.

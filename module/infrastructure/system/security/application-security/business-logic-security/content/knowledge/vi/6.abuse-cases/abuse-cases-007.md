# Ưu tiên các tình huống lạm dụng — Abuse case prioritization

## 1. Ưu tiên là quyết định xử lý rủi ro, không chỉ là gắn nhãn mức độ

Một nhóm phát triển có thể tìm thấy hàng chục cách lạm dụng nghiệp vụ: sửa giá khi checkout, đọc hồ sơ của tenant khác, nhận lại ưu đãi, hoàn tiền trùng hoặc thay cấu hình để bỏ một bước phê duyệt. Nguồn lực xử lý luôn có giới hạn, nên cần biết trường hợp nào phải chặn trước, trường hợp nào cần điều tra ngay và trường hợp nào có thể đưa vào một kế hoạch có thời hạn.

**Abuse case prioritization** là việc sắp xếp các tình huống lạm dụng theo rủi ro và nhu cầu hành động trong bối cảnh cụ thể. Kết quả không chỉ là một điểm số. Nó cần chỉ ra:

- Tình huống nào cần hành động trước và vì sao.
- Bằng chứng nào hỗ trợ đánh giá, điều gì vẫn chưa biết.
- Biện pháp trước mắt và cách sửa nguyên nhân.
- Ai chịu trách nhiệm, khi nào đánh giá lại và điều kiện nào cho phép đóng việc.

Trong chương **Abuse Cases** của học phần **Business Logic Security**, ưu tiên cần bám vào tài sản và business invariant. Những vấn đề về state machine, quyền theo đối tượng, transaction hoặc idempotency chỉ có ý nghĩa ưu tiên khi được nối với một kết quả nghiệp vụ có thể bị phá.

Sau bài này, bạn cần có khả năng:

- Viết abuse case đủ cụ thể để so sánh rủi ro.
- Đánh giá tác động, khả năng thực hiện và quy mô lạm dụng mà không trộn các yếu tố.
- Xử lý bằng chứng thiếu hoặc chính sách chưa rõ.
- Dùng thang điểm như công cụ hỗ trợ, cùng các quy tắc nâng mức khẩn cấp.
- Chọn biện pháp giảm rủi ro và xác định bằng chứng hoàn tất.

## 2. Đơn vị cần ưu tiên là một kết quả bị cấm có thể xảy ra

Một tiêu đề như “API thiếu validation” quá rộng để đánh giá. Cần mô tả actor, điều kiện và tác động cụ thể.

Ví dụ:

~~~text
Actor:
  Khách hàng đã xác thực, sở hữu một giỏ hàng.

Luồng hợp lệ:
  Chọn hàng, xem giá, xác nhận và thanh toán.

Sai lệch:
  Máy chủ lấy tổng tiền do client gửi làm tổng cần thu.

Kết quả bị cấm:
  Khách trả ít hơn giá đã được chính sách chấp nhận nhưng vẫn nhận đủ hàng.

Invariant:
  Giá trị được cấp phải khớp nghĩa vụ thanh toán do máy chủ xác định.

Bằng chứng:
  Ca kiểm thử được phép tạo đơn với giá trị hàng khác số tiền cần thanh toán.
~~~

Mô tả này giúp phân biệt một lỗi hiển thị giá với một đường làm mất tài sản thật. Nó cũng cho biết cần kiểm tra việc thu tiền và giao hàng, không chỉ response của endpoint tạo đơn.

### 2.1. Tách vấn đề đã xác nhận, giả thuyết và khoảng trống chính sách

| Trạng thái | Ý nghĩa | Việc cần làm |
| --- | --- | --- |
| Đã xác nhận | Có bằng chứng về đường đi đến kết quả vi phạm quy tắc đã xác định | Ưu tiên giảm rủi ro và sửa |
| Giả thuyết có cơ sở | Có đường nghi ngờ nhưng thiếu một mắt xích | Ưu tiên kiểm chứng theo tác động có thể xảy ra |
| Chưa rõ chính sách | Chưa thống nhất điều gì bị cấm hoặc được phép | Làm rõ với người sở hữu nghiệp vụ |
| Đã bị ngăn trong phạm vi kiểm tra | Kiểm soát thực sự chặn kết quả đã mô tả | Ghi bằng chứng, xác định phạm vi và kiểm tra các đường liên quan |

Không gọi một hành vi là gian lận chỉ vì nhóm phát triển không thích kết quả của nó. Nếu chiến dịch chưa định nghĩa một người được nhận bao nhiêu lần, cần làm rõ quy tắc trước khi kết luận hệ thống đang vi phạm quy tắc đó.

Ngược lại, việc còn thiếu một chi tiết không nên khiến một giả thuyết có hậu quả nghiêm trọng bị chôn dưới danh sách. Có thể ưu tiên điều tra hoặc giới hạn phơi lộ trước khi hoàn tất chẩn đoán.

### 2.2. Tránh đếm trùng cùng một rủi ro

Ba endpoint cùng bỏ kiểm tra ngân sách hoàn có thể là ba đường vào của một nguyên nhân chung. Cần giữ từng đường để kiểm thử nhưng không mặc nhiên cộng ba lần cùng một khoản thiệt hại.

Ngược lại, hai lỗi nhìn giống nhau có thể ảnh hưởng tài sản khác nhau. Đọc địa chỉ khách hàng khác và chuyển tiền từ ví khách hàng khác đều có thể liên quan kiểm tra đối tượng, nhưng tác động và khả năng phục hồi khác nhau.

Một cấu trúc hữu ích là:

~~~text
Rủi ro hoặc invariant chung
  -> các đường lạm dụng
  -> actor và điều kiện riêng
  -> kiểm soát chung và kiểm soát riêng
  -> bằng chứng kiểm thử từng đường
~~~

Cách nhóm này giúp chọn một điểm sửa có hiệu quả rộng mà vẫn tránh bỏ sót endpoint cũ, batch, worker hoặc công cụ quản trị.

## 3. Bắt đầu bằng tài sản và tác động nghiệp vụ

Tác động cần được mô tả bằng kết quả, không chỉ tên kỹ thuật của lỗi.

| Tài sản hoặc nghĩa vụ | Tác động cần đánh giá | Câu hỏi gợi ý |
| --- | --- | --- |
| Tiền và số dư | Mất tiền, tạo quyền chi sai, hoàn vượt quyền lợi | Có giới hạn mỗi giao dịch và giới hạn tổng không? |
| Tồn kho hoặc năng lực phục vụ | Chiếm giữ, bán vượt, khóa quyền dùng của người khác | Một actor có thể giữ tài nguyên bao lâu và bao nhiêu? |
| Dữ liệu cá nhân hoặc dữ liệu tenant | Truy cập, xuất hoặc sử dụng ngoài quyền | Dữ liệu nào, của bao nhiêu chủ thể, có thu hồi được không? |
| Phê duyệt và quyền quản trị | Tự duyệt, mở rộng quyền, sửa điều kiện cấp phép | Có thể biến một thay đổi thành nhiều quyết định sai tiếp theo không? |
| Khuyến mãi và thưởng | Cấp lặp, vượt ngân sách, đổi ưu đãi thành tiền ngoài chính sách | Quyền lợi có thể chuyển hoặc rút không? |
| Quy trình và chất lượng dịch vụ | Bỏ bước, tạo backlog, làm chậm tác vụ quan trọng | Phạm vi chỉ một người dùng hay tài nguyên dùng chung? |
| Bằng chứng và đối soát | Che dấu, làm sai lịch sử, không giải thích được số dư | Có nguồn độc lập để phát hiện và phục hồi không? |

Không ép mọi tác động thành một con số tiền khi chưa có cơ sở. Một lần tiết lộ dữ liệu không thể được coi là nhỏ chỉ vì chưa gắn giá tiền. Tương tự, khả năng sửa sổ và bằng chứng có thể làm nhiều kiểm soát khác mất giá trị.

### 3.1. Dùng kịch bản có căn cứ, không chọn hậu quả tưởng tượng lớn nhất

Mỗi mô tả tác động nên chỉ ra chuỗi nhân quả:

~~~text
điểm yếu
  -> hành động actor có thể thực hiện
  -> quyết định hoặc invariant bị phá
  -> tài sản và phạm vi bị ảnh hưởng
~~~

Ví dụ, “có thể sửa giá trị một field” chưa chứng minh chiếm được toàn hệ thống. Cần biết field được dùng ở đâu, có bước kiểm tra sau không và có thể tạo tác động cuối cùng không.

Tương tự, một request tạo bản ghi chờ không tự chứng minh tiền đã được chuyển. Nhưng nếu bản ghi đó là đầu vào có thẩm quyền cho worker chuyển tiền mà worker không kiểm tra lại, cần đánh giá cả chuỗi.

### 3.2. Tác động tại một lần và tác động tích lũy

Một sai lệch 100.000 đồng có thể đáng kể nếu lặp được trên nhiều tài khoản hoặc nhiều giao dịch. Một lần chiếm giữ tồn kho nhỏ có thể trở thành vấn đề khi được tự động hóa và kéo dài.

Cần ghi riêng:

- Mức ảnh hưởng của một lần thành công.
- Giới hạn tổng theo đối tượng, tài khoản, tenant hoặc chiến dịch.
- Khả năng lặp và phối hợp nhiều actor.
- Cửa sổ thời gian trước khi kiểm soát thực sự dừng tác động.
- Khả năng phát hiện, dừng và phục hồi.

Một giới hạn chỉ tồn tại trên giao diện hoặc trong tài liệu chưa được tính như giới hạn đã thực thi.

## 4. Phân biệt khả năng thực hiện, quy mô và độ khẩn cấp

Ba yếu tố này dễ bị trộn lẫn.

### 4.1. Khả năng thực hiện

Cần xác định actor bắt đầu từ đâu và cần điều kiện gì:

- Khách chưa xác thực, khách đã đăng nhập, nhân viên hay quản trị viên?
- Cần một giao dịch thật, số dư, hồ sơ đã duyệt hoặc một quyền được giao?
- Có cần thông tin khó lấy, một cửa sổ cạnh tranh hẹp hoặc nhiều bên phối hợp?
- Kết quả đã được tái hiện ổn định hay mới dựa trên suy đoán?
- Kiểm soát hiện tại có chặn một bước bắt buộc không?

Khả năng thực hiện phải được đánh giá **đối với actor đã nêu**. Nếu actor là người sửa cấu hình có thể trực tiếp phát hành, không tự hạ mức chỉ vì số người có vai trò đó ít. Sự hiếm của vai trò và rủi ro chiếm tài khoản là các dữ kiện phơi lộ bổ sung; chúng không làm hành vi cố ý của chính người giữ quyền trở nên khó thực hiện.

Tương tự, xác thực mạnh có thể làm việc chiếm tài khoản khó hơn. Nó không chặn người có tài khoản hợp lệ tự lạm dụng quyền.

### 4.2. Quy mô hoặc khả năng khuếch đại

Sau lần thành công đầu tiên, actor có thể lặp đến đâu?

- Bị giới hạn ở một đối tượng hay truy cập được nhiều đối tượng?
- Chỉ trong một tenant hay vượt nhiều tenant?
- Có tự động hóa được không?
- Khóa request mới hoặc tài khoản mới có mở thêm quyền lợi không?
- Có một ngân sách cứng, khoản giữ hoặc ràng buộc duy nhất thực sự không?
- Thay đổi chính sách có tiếp tục tác động lên các giao dịch tương lai không?

Rate limiting có thể giảm tốc độ nhưng không nhất thiết giảm tổng quyền lợi bị lấy. Khi cửa sổ kéo dài hoặc có nhiều actor, phải kiểm tra lại hiệu quả thực tế của giới hạn đó.

### 4.3. Độ khẩn cấp

Độ khẩn cấp liên quan đến việc cần hành động khi nào:

- Tác động đang xảy ra hay mới là khả năng?
- Luồng đã mở cho actor liên quan chưa?
- Có chiến dịch hoặc lần phát hành sắp mở rộng phơi lộ không?
- Kiểm soát tạm thời còn hiệu lực bao lâu?
- Nếu chậm, tổn thất có tích lũy hoặc không thể thu hồi không?

Một lỗi nghiêm trọng trong tính năng chưa mở vẫn có thể chặn phát hành. Một lỗi điểm số thấp hơn nhưng đang gây tác động liên tục có thể cần hành động vận hành trước.

Không gộp độ khẩn cấp vào một cảm giác chung như “nghe có vẻ nguy hiểm”. Ghi rõ sự kiện hoặc thời điểm làm thay đổi nhu cầu hành động.

## 5. Đánh giá kiểm soát hiện có trước khi kết luận rủi ro còn lại

Một abuse case cần ghi rõ kiểm soát nào thật sự cắt đứt chuỗi lạm dụng và kiểm soát nào chỉ giúp quan sát.

| Kiểm soát | Có thể làm giảm điều gì? | Điều không được mặc nhiên suy ra |
| --- | --- | --- |
| Quyền theo đối tượng | Chặn actor không có quan hệ phù hợp | Chủ sở hữu hợp lệ không thể lạm dụng |
| State machine có điều kiện | Chặn bước hoặc thứ tự không hợp lệ | Tổng tiền hoặc tổng số lượng luôn đúng |
| Ràng buộc ngân sách nguyên tử | Ngăn nhiều yêu cầu cùng vượt hạn mức | Mọi nguồn ghi có hoặc quyết định giá đều đúng |
| Idempotency key | Chống gửi lại cùng ý định trong phạm vi khóa | Khóa mới không thể dùng lại quyền lợi |
| Tính duy nhất nghiệp vụ | Ngăn nhân bản một quyết định hoặc tác động | Tổng của các quyết định khác nhau nằm trong ngân sách |
| Rate limiting | Giảm tốc độ trong phạm vi áp dụng | Tổng tác động luôn nhỏ hoặc không có nhiều tài khoản |
| Log và cảnh báo | Tăng khả năng phát hiện, điều tra | Chặn được tác động trước khi xảy ra |
| Đối soát và điều chỉnh | Giúp tìm và phục hồi sai lệch trong một số trường hợp | Mọi thiệt hại đều có thể thu hồi |

Một kiểm soát chỉ được tính trong phạm vi đã kiểm chứng. Nếu controller chính có kiểm tra nhưng batch và worker không có, không đánh dấu cả abuse case là đã bị ngăn.

### 5.1. Làm rõ cách dùng từ rủi ro ban đầu và rủi ro còn lại

Các nhóm có thể dùng thuật ngữ khác nhau. Trong bài này:

- **Rủi ro ban đầu:** đánh giá theo đường lạm dụng và phạm vi được mô tả trước khi tính các biện pháp giảm thiểu đang xem xét.
- **Rủi ro còn lại:** đánh giá sau khi tính những kiểm soát hiện hữu hoặc biện pháp đã triển khai, với bằng chứng về hiệu lực.

Cần ghi rõ đường cơ sở. Không so một lỗi theo tình huống không có kiểm soát với lỗi khác sau khi đã tính đầy đủ kiểm soát, rồi coi hai điểm số là tương đương.

Biện pháp mới chỉ nằm trên kế hoạch chưa làm giảm rủi ro thực tế. Sau triển khai, phải xác minh cả đường chính và những đường có thể bỏ qua trước khi cập nhật đánh giá.

### 5.2. Tránh tính một lợi ích hai lần

Nếu rate limit chủ yếu giảm tốc độ mở rộng, tính ảnh hưởng đó ở quy mô hoặc cửa sổ tác động. Không tiếp tục trừ thêm một lần vào khả năng thực hiện nếu actor vẫn dễ tạo lần thành công đầu tiên.

Nếu kiểm tra tenant giới hạn phạm vi dữ liệu, cập nhật phạm vi tác động phù hợp. Không vừa coi như đã chặn hoàn toàn, vừa tiếp tục dùng cùng dữ kiện để làm nhỏ mọi thành phần khác.

Nếu một kiểm soát thật sự chặn mọi mắt xích bắt buộc của tình huống đã mô tả, ghi trạng thái được ngăn trong phạm vi đó. Không cố giữ nó như một lỗ hổng còn mở chỉ để điền điểm thấp.

## 6. Một thang điểm minh họa có thể dùng trong workshop

Thang dưới đây do bài học đặt ra để minh họa cách so sánh. Nó không phải chuẩn bắt buộc và không biểu diễn xác suất thiệt hại.

Dùng ba thành phần:

- `I`: mức nghiêm trọng của tác động trong phạm vi cơ sở đã mô tả.
- `E`: mức dễ thực hiện đối với actor và điều kiện đã nêu.
- `A`: khả năng khuếch đại sau một lần thành công.

Mỗi thành phần từ 1 đến 4:

| Mức | I — tác động | E — khả năng thực hiện | A — khuếch đại |
| --- | --- | --- | --- |
| 1 | Ảnh hưởng hẹp, hậu quả nhỏ theo bối cảnh, có cách phục hồi đã kiểm chứng | Cần nhiều điều kiện khó đạt đã được xác định | Bị chặn ở một đối tượng hoặc tác động đơn lẻ bằng giới hạn cứng |
| 2 | Tổn thất hoặc gián đoạn có giới hạn đáng chú ý | Cần một số điều kiện không thường sẵn có | Có thể lặp nhưng bị một giới hạn tổng nhỏ đã thực thi |
| 3 | Thiệt hại đáng kể hoặc phá một quy tắc quan trọng | Điều kiện thực tế, có thể đạt bằng một chuỗi thao tác hoặc cạnh tranh khả thi | Có thể lặp trên nhiều đối tượng trong một phạm vi hoặc cửa sổ đáng kể |
| 4 | Hậu quả rất nghiêm trọng theo tiêu chí tài sản đã thống nhất | Thao tác trực tiếp, ổn định, ít trở ngại đối với actor đã nêu | Mở rộng lớn, nhiều phạm vi hoặc thay đổi còn ảnh hưởng các giao dịch tương lai |

Cần bổ sung tiêu chí cụ thể theo sản phẩm. “Nhỏ” và “đáng kể” phải có ví dụ được người sở hữu tài sản hiểu giống nhau; không thể áp dụng cùng một ngưỡng tiền cho mọi tổ chức.

Để tránh đếm trùng, `I` đánh giá tính chất và mức nghiêm trọng trong phạm vi cơ sở; `A` đánh giá khả năng mở rộng ra ngoài lần thành công đó. Nếu nhóm đã gộp toàn bộ quy mô vào `I`, cần điều chỉnh rubric thay vì cộng thêm cùng tác động vào `A`.

Một công thức hỗ trợ sắp xếp:

~~~text
S = 3 × I + 2 × E + A
~~~

Điểm nằm từ 6 đến 24. Trọng số phản ánh lựa chọn minh họa rằng tác động có vai trò lớn hơn hai yếu tố còn lại. Một tổ chức có thể chọn cách khác, nhưng cần ghi và sử dụng nhất quán.

### 6.1. Điểm số không có ý nghĩa định lượng ngoài thiết kế

Điểm 24 không có nghĩa nguy hiểm gấp đôi điểm 12. Chênh một điểm cũng không chứng minh hai việc phải nằm ở hai đợt xử lý khác nhau.

Không chuyển trực tiếp điểm ordinal thành số tiền tổn thất kỳ vọng. Nếu muốn tính tổn thất kỳ vọng, cần dữ liệu có cơ sở về tần suất, phạm vi và giá trị; một bảng 1–4 không tự cung cấp những dữ kiện đó.

Không dùng số chữ số thập phân để tạo cảm giác chính xác. Khi hai trường hợp gần nhau, quay về chuỗi nhân quả, tài sản, phơi lộ và bằng chứng.

### 6.2. Quy tắc nâng mức được áp dụng ngoài điểm số

Có thể có các điều kiện cần hành động trước bất kể thứ hạng tính toán:

- Có tác động nghiêm trọng đang diễn ra hoặc dấu hiệu đủ tin cậy cần ngăn ngay.
- Đường dễ thực hiện đang mở tới tài sản quan trọng và chưa có rào cản hiệu lực.
- Thay đổi sắp phát hành sẽ mở rộng đáng kể phơi lộ.
- Bằng chứng hoặc khả năng kiểm soát đang bị mất.
- Biện pháp tạm thời sắp hết hạn trong khi rủi ro chưa được xử lý.

Các điều kiện này cần được kiểm tra, ghi nhận và giao trách nhiệm. Không tự nâng mọi lỗi lên mức khẩn cấp chỉ vì chứa từ “tiền” hoặc “quản trị”.

## 7. Ví dụ xếp hạng một nhóm abuse case

Toàn bộ tình huống dưới đây là **ví dụ giả định cho một ứng dụng Java thương mại**, không phải kết quả kiểm tra một hệ thống thực tế. Giả sử các luồng liên quan được đánh giá trước một lần phát hành; chưa có bằng chứng về tác động đang xảy ra ngoài môi trường kiểm thử.

Nhóm đã thống nhất rubric tài sản và thu được các bằng chứng sau:

| ID | Tình huống và bằng chứng chính | I | E | A | S |
| --- | --- | ---: | ---: | ---: | ---: |
| AC-01 | Checkout chấp nhận tổng tiền client; kiểm thử xác nhận đường phía sau dùng số đó để quyết định nghĩa vụ thanh toán cho hàng có giá trị lớn | 4 | 4 | 4 | 24 |
| AC-02 | Endpoint file cho phép đọc tài liệu ngoài tenant; điều kiện lấy tham chiếu ngoài quyền đã được kiểm chứng qua một luồng liên quan | 4 | 3 | 4 | 22 |
| AC-03 | Hai lệnh chi từ cùng ví cùng vượt khả dụng; kiểm thử cạnh tranh xác nhận; phạm vi và giá trị ví bị giới hạn nhưng có thể lặp trên nhiều đối tượng | 3 | 3 | 3 | 18 |
| AC-04 | Người sửa cấu hình có thể trực tiếp tăng ngưỡng duyệt dù chính sách yêu cầu phê duyệt độc lập; thay đổi ảnh hưởng các quyết định tương lai | 4 | 4 | 4 | 24 |
| AC-05 | Có thể hưởng lại ưu đãi bằng nhiều tài khoản, nhưng khái niệm chủ thể đủ tư cách và một số rào cản chưa rõ | Chưa chốt | Chưa chốt | Chưa chốt | 12–21, tạm tính |
| AC-06 | Tài khoản có quyền xuất báo cáo tạo được nhiều job làm chậm hàng đợi dùng chung; thử tải xác nhận gián đoạn ở mức có giới hạn | 2 | 4 | 3 | 17 |

Đối với AC-05, khoảng 12–21 chỉ là hai kịch bản giả định:

~~~text
Kịch bản thấp: I=2, E=2, A=2 -> S=12
Kịch bản cao:  I=3, E=4, A=4 -> S=21
~~~

Khoảng này không xác nhận đó đã là vi phạm chính sách. Nó giúp thấy câu hỏi nào có thể thay đổi quyết định ưu tiên. Không lấy trung bình rồi coi như đã hiểu rủi ro.

### 7.1. Vì sao AC-04 không được hạ mức chỉ vì cần quyền quản trị?

Actor của tình huống là người đã có quyền sửa cấu hình. Đối với actor đó, thao tác trực tiếp và dễ thực hiện. Nếu chỉ nghĩ đến một kẻ bên ngoài phải chiếm tài khoản, đánh giá sẽ bỏ qua lạm dụng từ người có quyền hợp lệ.

Xác thực mạnh hoặc log đăng nhập có thể hữu ích, nhưng không thay thế phê duyệt độc lập cho thay đổi chính sách nếu đó là quy tắc bắt buộc.

### 7.2. Vì sao AC-03 cần xem sổ thay vì chỉ xem hai response?

Ví có 1.000.000 đồng khả dụng, hai lệnh cùng xin chi 700.000 đồng. Nếu cả hai được chấp nhận, tổng quyền chi được cấp là 1.400.000 đồng, vượt khả dụng ban đầu 400.000 đồng.

Con số 400.000 đồng là phần vượt quyền chi trong ví dụ, chưa tự mô tả đầy đủ thiệt hại tài chính. Nếu xảy ra mất cập nhật ở nguồn nhưng cả hai bên nhận đều được ghi có, sai lệch sổ có thể có dạng khác.

Cần kiểm tra số dư, các mục sổ, khoản giữ và tác động nhận tiền. Chỉ hai mã HTTP thành công chưa đủ để kết luận cơ chế hoặc mức tổn thất chính xác.

### 7.3. Chọn đợt xử lý

Một quyết định minh họa có thể là:

- AC-01, AC-02 và AC-04 phải được chặn hoặc sửa có bằng chứng trước khi mở các luồng liên quan.
- AC-03 cũng là điều kiện chặn phát hành phần chi tiền, dù điểm thấp hơn một số trường hợp khác.
- AC-06 có kế hoạch xử lý cụ thể; chỉ được hoãn nếu người sở hữu chấp nhận phần rủi ro còn lại và phơi lộ thực tế nằm trong giới hạn đã xác minh.
- AC-05 có một đầu việc làm rõ chính sách và kiểm chứng các điều kiện ảnh hưởng lớn, không bị bỏ quên vì chưa có điểm chính xác.

Thứ tự trong cùng đợt có thể phụ thuộc việc nào chặn được nhiều đường lạm dụng, phụ thuộc kỹ thuật và khả năng triển khai an toàn. Chi phí sửa giúp tổ chức công việc; nó không tự làm mức rủi ro thấp đi.

## 8. Tách mức ưu tiên khỏi trạng thái công việc

Có thể dùng các nhãn minh họa sau:

| Nhãn | Ý nghĩa hành động |
| --- | --- |
| P0 | Cần hành động khẩn cấp theo điều kiện đã xác nhận, ưu tiên ngăn tác động và kiểm soát tình hình |
| P1 | Rủi ro cao cần xử lý trước mốc quyết định như mở hoặc phát hành luồng liên quan |
| P2 | Có kế hoạch, người sở hữu, thời hạn và điều kiện đánh giá lại cụ thể |
| P3 | Rủi ro còn lại thấp trong phạm vi có bằng chứng, hoặc được theo dõi với tiêu chí mở lại rõ ràng |

Đây là quy ước của bài học, không phải cam kết thời gian áp dụng cho mọi nhóm. Tổ chức cần định nghĩa cách phản hồi và thời hạn tương ứng.

Các trạng thái như mới phát hiện, đang điều tra, đang sửa, đang chờ triển khai hoặc đã xác minh là một trục khác. Một việc đang chờ phụ thuộc vẫn có thể là P1; không được hạ ưu tiên chỉ vì khó làm.

Một việc đã merge nhưng chưa triển khai cũng chưa chắc giảm rủi ro. Một việc đã triển khai nhưng chưa xác minh đường bỏ qua cũng chưa đủ để đóng.

## 9. Độ chắc chắn của bằng chứng cần được quản lý riêng

Có thể ghi độ tin cậy bằng các mô tả như:

- Đã tái hiện tới tác động cuối trong môi trường đại diện.
- Đã chứng minh một phần chuỗi, còn một điều kiện cần xác minh.
- Suy luận từ thiết kế hoặc mã, chưa có kiểm thử thực thi.
- Chưa rõ chính sách hoặc phạm vi dữ liệu.

Không nhân điểm rủi ro với một hệ số nhỏ chỉ vì chưa có bằng chứng đầy đủ. Cách đó dễ đẩy một giả thuyết hậu quả lớn xuống thấp đúng lúc nó cần được điều tra.

Thay vào đó, giữ các giả định và đặt một nhiệm vụ kiểm chứng có giới hạn:

~~~text
Câu hỏi quyết định:
  Worker có kiểm tra lại tổng tiền trước khi thu không?

Vì sao quan trọng:
  Nếu có, tác động có thể dừng ở bản ghi sai.
  Nếu không, đường cấp hàng với nghĩa vụ thanh toán sai vẫn mở.

Cách kiểm chứng:
  Kiểm thử được phép theo chuỗi với dữ liệu và hệ thống thanh toán mô phỏng.

Kết quả cần lưu:
  Dữ kiện, phạm vi đã kiểm tra và ảnh hưởng lên đánh giá.
~~~

Ưu tiên điều tra những câu hỏi có thể đổi đáng kể quyết định xử lý. Không cần chạy một cuộc nghiên cứu dài cho mọi chi tiết khi đã có đủ bằng chứng để chặn một đường tác động nghiêm trọng.

## 10. Chọn biện pháp theo chuỗi lạm dụng và nguyên nhân

Ưu tiên đúng nhưng chỉ sửa bề mặt sẽ không làm giảm rủi ro như dự kiến. Với mỗi trường hợp, cần tách ba loại công việc.

### 10.1. Ngăn hoặc giới hạn tác động trước mắt

Tùy bối cảnh, có thể:

- Chưa mở hoặc tạm ngừng luồng tạo tác động bị ảnh hưởng.
- Giới hạn actor hoặc phạm vi đối tượng được phép sử dụng.
- Chuyển một số quyết định sang quy trình kiểm tra có thẩm quyền.
- Đặt ngân sách hoặc giới hạn cứng tại nơi ghi.
- Vô hiệu hóa một cấu hình nguy hiểm hoặc quyền không cần thiết.

Biện pháp phải nằm trên đường có thẩm quyền. Ẩn nút, thêm cảnh báo trên frontend hoặc yêu cầu người dùng không gửi đồng thời không phải rào cản đủ cho một invariant quan trọng.

Cần kiểm tra tác động lên người dùng hợp lệ và luồng đang xử lý. Ví dụ, ngừng tạo lệnh hoàn mới không nên làm mất khả năng xác minh kết quả của các lệnh đã gửi.

Biện pháp tạm thời cần người sở hữu, phạm vi, thời hạn và điều kiện hết hiệu lực. Nếu một feature flag bảo vệ bị bật lại, rủi ro có thể quay về mức cũ.

### 10.2. Sửa cơ chế làm invariant bị phá

| Nhóm nguyên nhân | Hướng sửa cần xem xét |
| --- | --- |
| Giá hoặc quyền lợi do client quyết định | Tính hoặc chốt ở máy chủ, ràng buộc nội dung và phạm vi |
| Sai quyền theo đối tượng | Kiểm tra tenant, quan hệ, hành động và dữ liệu trả về |
| Bỏ qua bước phê duyệt | State machine và quyết định gắn với đúng phiên bản nội dung |
| Cạnh tranh ngân sách | Giữ hoặc trừ quyền lợi nguyên tử ở dữ liệu dùng chung |
| Gửi lại tạo thêm tác động | Idempotency cùng tính duy nhất nghiệp vụ và ngân sách tổng |
| Lạm dụng quyền quản trị | Phạm vi quyền, tách biệt nhiệm vụ và kiểm soát thay chính sách |
| Chiếm tài nguyên | Ngân sách theo chi phí, số tác vụ đồng thời và thời gian sử dụng |
| Kết quả ngoài chưa rõ | Mã lệnh ổn định, trạng thái chờ, đối soát và xử lý trùng |

Không chọn giải pháp chỉ từ tên lỗi. “Duplicate request” có thể là retry cùng ý định hoặc nhiều ý định khác nhau cùng tiêu thụ một ngân sách. Hai tình huống cần các ràng buộc bổ sung khác nhau.

### 10.3. Xác minh rủi ro còn lại và phục hồi cần thiết

Sau khi sửa, có thể vẫn còn:

- Đường API hoặc worker khác chưa dùng chung kiểm soát.
- Dữ liệu sai đã được tạo trước đó.
- Lệnh bên ngoài chưa rõ kết quả.
- Một khoảng trễ lan truyền quyền hoặc chính sách.
- Phạm vi chủ thể mà hạn mức hiện tại chưa bao phủ.
- Biện pháp gây chặn nhầm cần điều chỉnh.

Phải phân biệt ngăn lỗi mới với sửa hậu quả cũ. Đổi mã không tự cân bằng lại sổ, thu hồi dữ liệu đã xuất hoặc xử lý một lệnh đã thành công bên ngoài.

## 11. Bằng chứng hoàn tất phải chứng minh điều gì?

Một đầu việc nên có điều kiện hoàn tất được viết trước khi bắt đầu sửa.

| Abuse case | Bằng chứng ngăn đường lạm dụng | Phần cần kiểm tra thêm |
| --- | --- | --- |
| AC-01: giá client | Tổng và snapshot đơn được máy chủ xác định; dữ liệu client không mở rộng quyền lợi | Giảm giá, đổi địa chỉ, báo giá cũ và đường tạo đơn khác |
| AC-02: ngoài tenant | Actor không có quan hệ không đọc được file hoặc dữ liệu qua đường liên quan | Danh sách, cache, link tải, batch và thông báo |
| AC-03: chi đồng thời | Kiểm thử cạnh tranh không cho tổng quyền chi mới vượt ngân sách | Nhiều instance, retry, khoản giữ và đường ghi khác |
| AC-04: đổi ngưỡng | Không phát hành nội dung chưa được duyệt độc lập theo chính sách | Sửa sau duyệt, phiên bản nền cũ, rollback và quyền khẩn cấp |
| AC-06: xuất báo cáo | Ngân sách tài nguyên được thực thi với nhiều job và actor trong phạm vi | Tác vụ đang chạy, hủy, timeout và chi phí từng loại báo cáo |

Một bộ bằng chứng có ích thường ghi:

- Phiên bản ứng dụng và cấu hình liên quan.
- Actor, quan hệ và điều kiện kiểm thử.
- Phạm vi API, job hoặc dịch vụ đã kiểm tra.
- Invariant và trạng thái cuối đã quan sát.
- Những giả định hoặc giới hạn vẫn còn.
- Đánh giá rủi ro sau biện pháp.

Đối với ứng dụng Java, mock repository có thể giúp kiểm tra một nhánh logic nhưng không chứng minh khóa cơ sở dữ liệu, uniqueness hoặc rollback. Các rủi ro phụ thuộc transaction cần kiểm thử tích hợp với ngữ nghĩa lưu trữ phù hợp.

Một ca kiểm thử có giá trị phải chạm đúng kết quả bị cấm. Ví dụ, với chi hai lần, cần xem số dư, khoản giữ và mục sổ sau các transaction, không chỉ xác nhận một exception đã được ném.

Không mở rộng kiểm thử vô hạn khi bằng chứng đã đủ cho phạm vi quyết định. Nếu phát hiện một đường mới hoặc giả định sai, cập nhật phạm vi và kiểm chứng phần bị ảnh hưởng.

### 11.1. Ví dụ cập nhật rủi ro sau biện pháp

- AC-01 chỉ ẩn trường giá trên UI: đường API còn nguyên, chưa có cơ sở hạ rủi ro.
- AC-03 thêm khóa trong một JVM nhưng môi trường có nhiều instance: chưa chứng minh cơ chế cạnh tranh đã được xử lý.
- AC-04 chỉ thêm log thay đổi cấu hình: tăng khả năng điều tra nhưng không chặn tự mở rộng thẩm quyền.
- AC-06 có ngân sách chi phí và số tác vụ đồng thời được thực thi ở worker dùng chung: có thể cập nhật quy mô hoặc tác động còn lại theo kết quả đo.

Nếu đường mô tả đã bị chặn đầy đủ, ghi điều đó cùng bằng chứng thay vì tùy ý đặt mọi thành phần về 1. Rủi ro khác chưa kiểm chứng vẫn cần được giữ riêng.

## 12. Tổ chức thứ tự thực hiện trong cùng một nhóm ưu tiên

Trong một nhóm đều phải xử lý trước phát hành, có thể cân nhắc:

1. Biện pháp nào ngăn ngay đường tác động lớn nhất?
2. Điểm sửa nào bảo vệ được nhiều đường có cùng nguyên nhân?
3. Có phụ thuộc nào phải làm trước để kiểm soát có hiệu lực?
4. Thay đổi nào dễ triển khai, quan sát và phục hồi an toàn?
5. Phần nào cần làm rõ sớm để tránh sửa theo chính sách sai?

Ví dụ, sửa cơ chế quyền theo đối tượng dùng chung có thể bảo vệ nhiều endpoint. Tuy nhiên, vẫn phải kiểm tra các đường không đi qua cơ chế chung. Không coi việc tạo một hàm kiểm tra là bằng chứng mọi caller đã sử dụng nó.

Với lỗi cạnh tranh, thêm một primitive giữ ngân sách có thẩm quyền có thể có giá trị hơn việc thêm nhiều kiểm tra trước ghi ở từng controller.

Một bản sửa nhanh không nên được ưu tiên chỉ vì có thể đóng nhiều ticket. Cần xem số đường lạm dụng và mức rủi ro thực sự được giảm.

### 12.1. Chi phí triển khai và rủi ro là hai trục

Một việc mất nhiều thời gian vẫn có thể là ưu tiên cao. Khi chưa sửa xong, cần một quyết định cụ thể: giới hạn phơi lộ, trì hoãn mở luồng hoặc chấp nhận rủi ro còn lại theo thẩm quyền.

Không tự hạ mức để làm kế hoạch vừa với sprint. Ngược lại, cũng không bỏ qua ảnh hưởng của biện pháp lên hoạt động hợp lệ. Quyết định nên trình bày các phương án cùng tác động và bằng chứng, để người sở hữu tài sản lựa chọn có căn cứ.

Nếu nhiều rủi ro chỉ giảm khi một thay đổi chung được triển khai, phải theo dõi phụ thuộc đó. Merge từng phần chưa đủ để tuyên bố tất cả đã an toàn.

## 13. Hồ sơ ưu tiên và điều kiện đánh giá lại

Một bản ghi tự chứa có thể gồm:

| Trường | Nội dung cần ghi |
| --- | --- |
| ID và tiêu đề | Kết quả bị cấm, không chỉ tên lỗi kỹ thuật |
| Tài sản và chủ sở hữu | Ai có trách nhiệm quyết định về hậu quả |
| Actor và điều kiện | Quyền ban đầu, quan hệ, tài nguyên hoặc dữ kiện cần có |
| Luồng và sai lệch | Chuỗi hợp lệ, đường lạm dụng và invariant bị phá |
| Phạm vi phơi lộ | Tính năng đã mở chưa, tenant, đối tượng và cửa sổ thời gian |
| Bằng chứng | Đã xác nhận gì, còn giả định gì |
| Kiểm soát hiện hữu | Kiểm soát nào chặn, giới hạn hoặc chỉ phát hiện |
| Đánh giá | Thành phần, lý do, khoảng bất định và quy tắc nâng mức |
| Kế hoạch | Biện pháp tạm thời, sửa nguyên nhân, phụ thuộc và người thực hiện |
| Hoàn tất | Điều kiện kiểm thử, triển khai, phục hồi và rủi ro còn lại |
| Chấp nhận nếu có | Người có thẩm quyền, phạm vi, lý do và thời hạn |
| Mở lại | Sự kiện hoặc thay đổi nào buộc đánh giá lại |

Chấp nhận rủi ro không phải một cách xóa vấn đề khỏi lịch sử. Cần có người chịu trách nhiệm, phạm vi và mốc xem xét. Việc người triển khai không còn thời gian không tự tạo thẩm quyền chấp nhận hậu quả thay người sở hữu tài sản.

Các sự kiện có thể làm ưu tiên thay đổi:

- Tính năng mở cho nhiều actor hoặc tenant hơn.
- Giá trị giao dịch hoặc ngân sách chiến dịch tăng.
- Có bằng chứng đường lạm dụng dễ thực hiện hơn dự kiến.
- Một kiểm soát bị gỡ, hết hạn hoặc không bao phủ đường mới.
- Có tự động hóa, tác động thực tế hoặc nhiều lần thử liên quan.
- Chính sách nghiệp vụ thay đổi.
- Dữ liệu mới chứng minh tác động thấp hơn hoặc đường đã bị ngăn.
- Kiến trúc đổi từ một instance sang nhiều instance, hoặc chuyển xử lý sang queue.

Đánh giá lại khi có dữ kiện thay đổi quyết định, không chỉ đổi điểm để bảng trông mới hơn.

## 14. Những sai lầm thường làm lệch thứ tự ưu tiên

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Chỉ nhìn độ khó kỹ thuật | Bỏ qua đường đơn giản gây hậu quả lớn | Nối tới tài sản và kết quả cuối |
| Cần đăng nhập nên mặc định mức thấp | Bỏ qua khách hàng có chủ đích và actor có quyền hợp lệ | Đánh giá từ vị trí actor đã xác định |
| Ít quản trị viên nên không đáng lo | Không xem khả năng thay điều kiện ra quyết định | Đánh giá tác động lan truyền và tách biệt nhiệm vụ |
| Điểm cao nhất luôn làm trước | Bỏ qua tác động đang xảy ra hoặc mốc phát hành | Áp dụng quy tắc khẩn cấp và ngữ cảnh ngoài điểm |
| Chưa tái hiện nên coi như thấp | Đẩy giả thuyết hậu quả lớn xuống cuối | Ưu tiên điều tra theo giá trị thông tin |
| Có log nên coi như đã chặn | Tổn thất vẫn xảy ra trước cảnh báo | Phân biệt phòng ngừa, phát hiện và phục hồi |
| Có rate limit nên không thể lạm dụng | Nhầm tốc độ với tổng quyền lợi | Kiểm tra phạm vi, cửa sổ và ngân sách cứng |
| Có idempotency nên không có tác động trùng | Khóa mới vẫn có thể dùng cùng quyền lợi | Kiểm tra tính duy nhất nghiệp vụ và invariant tổng |
| Sửa nhiều ticket nhỏ nên hiệu quả hơn | Đếm đầu việc thay vì rủi ro được giảm | Nhóm theo nguyên nhân và phạm vi bảo vệ |
| Đã merge nên đóng | Mã chưa chạy hoặc đường bỏ qua còn tồn tại | Xác minh triển khai và kết quả nghiệp vụ |

## 15. Bài tập tự kiểm tra

### Bài 1: cùng điểm, hành động khác nhau

Hai abuse case cùng điểm 21. Một trường hợp nằm trong tính năng chưa mở, trường hợp kia đang tạo giao dịch sai trong môi trường đang phục vụ.

**Gợi ý trả lời:** điểm không quyết định toàn bộ độ khẩn cấp. Trường hợp đang tạo tác động cần xử lý khẩn cấp theo bằng chứng và quy trình; trường hợp chưa mở có thể là điều kiện chặn phát hành. Cả hai đều cần người sở hữu và biện pháp cụ thể.

### Bài 2: actor là người có quyền cấu hình

Nhóm hạ mức một lỗi tự đổi hạn mức vì “muốn làm phải có tài khoản quản trị và xác thực mạnh”. Chính sách lại yêu cầu người sửa không được tự phát hành thay đổi.

**Gợi ý trả lời:** cần đánh giá từ actor đã được mô tả. Người có quyền cấu hình có thể là nguồn lạm dụng; xác thực mạnh không ngăn chính người đó. Thiếu phê duyệt độc lập có thể mở quyền cho các quyết định tương lai, nên phải đánh giá tác động và quy mô đó.

### Bài 3: coupon chưa có quy tắc rõ

Một người dùng tạo hai tài khoản và nhận hai lần ưu đãi. Nhóm chưa thống nhất chiến dịch giới hạn theo tài khoản hay theo chủ thể.

**Gợi ý trả lời:** chưa đủ cơ sở kết luận vi phạm chính sách. Cần ưu tiên làm rõ điều kiện đủ tư cách, bằng chứng hiện có và ngân sách có thể bị ảnh hưởng. Có thể giới hạn phơi lộ theo một quyết định có thẩm quyền trong lúc làm rõ, nhưng không tự gán ý định gian lận cho người dùng.

### Bài 4: sửa bằng khóa trong JVM

Lỗi chi đồng thời được sửa bằng một khóa trong bộ nhớ. Kiểm thử đơn vị qua hết, nhưng môi trường có nhiều instance và một job khác cũng ghi số dư.

**Gợi ý trả lời:** chưa có bằng chứng invariant được giữ ở nơi dữ liệu dùng chung. Cần cơ chế cạnh tranh phù hợp tại ranh giới có thẩm quyền và kiểm thử các đường ghi liên quan. Không hạ rủi ro chỉ vì một kiểm thử cùng tiến trình đã qua.

## 16. Các điểm cần ghi nhớ

Ưu tiên abuse case bắt đầu từ actor, tài sản, invariant và chuỗi tạo tác động. Tác động, khả năng thực hiện, quy mô và độ khẩn cấp cần được mô tả riêng, với bằng chứng và giả định rõ ràng.

Điểm số giúp tổ chức thảo luận nhưng không thay thế chính sách, bằng chứng hoặc trách nhiệm quyết định. Trường hợp chưa chắc cần một nhiệm vụ kiểm chứng phù hợp; trường hợp chưa rõ chính sách cần người sở hữu nghiệp vụ làm rõ; trường hợp đã có tác động nghiêm trọng cần biện pháp theo độ khẩn cấp thực tế.

Câu hỏi cốt lõi là: **Nếu chỉ xử lý được một số việc trước, lựa chọn nào giảm rủi ro nghiệp vụ lớn nhất trong bối cảnh hiện tại, và bằng chứng nào chứng minh rủi ro đã thực sự giảm?**

# Xác định miền nghiệp vụ

## 1. Miền nghiệp vụ là gì?

Miền nghiệp vụ (business domain) là phạm vi kiến thức, hoạt động, mục tiêu và quy tắc mà một tổ chức hoặc một nhóm người cần hiểu và vận hành để tạo ra một kết quả kinh doanh cụ thể. Miền nghiệp vụ mô tả **vấn đề mà tổ chức đang giải quyết**, cách tổ chức đưa ra quyết định và những khái niệm mà người trong lĩnh vực sử dụng để trao đổi với nhau.

Ví dụ, trong một doanh nghiệp bán lẻ có thể nhận diện các miền như bán hàng, quản lý khuyến mãi, quản lý tồn kho, thanh toán, giao nhận và chăm sóc khách hàng. Mỗi miền có mục tiêu, thuật ngữ, quy trình và quy tắc riêng. Các miền có thể phối hợp với nhau nhưng không nhất thiết dùng chung toàn bộ cách hiểu về dữ liệu hoặc trạng thái.

Một miền nghiệp vụ không chỉ là một danh sách chức năng của phần mềm. Chẳng hạn, “thêm sản phẩm vào giỏ hàng” là một chức năng; “bán hàng trực tuyến” là một hoạt động hoặc quy trình; còn “quản lý đơn hàng” có thể là một miền nghiệp vụ với các khái niệm, vòng đời và quy tắc riêng. Khi xác định miền, cần tìm hiểu lý do nghiệp vụ khiến các chức năng tồn tại và mối quan hệ giữa chúng.

Có thể mô tả một miền bằng các thành phần sau:

- **Mục tiêu:** kết quả hoặc giá trị mà miền cần tạo ra.
- **Tác nhân:** người, nhóm hoặc hệ thống tham gia và chịu trách nhiệm.
- **Hoạt động:** công việc được thực hiện để đạt mục tiêu.
- **Khái niệm và thuật ngữ:** các đối tượng, trạng thái, sự kiện và hành động có ý nghĩa trong lĩnh vực.
- **Quy tắc và ràng buộc:** điều kiện quyết định một hoạt động có hợp lệ hay không.
- **Sự kiện:** điều đã xảy ra và có thể làm thay đổi trạng thái hoặc kích hoạt công việc tiếp theo.
- **Ranh giới:** phần trách nhiệm thuộc miền và phần được giao cho miền khác.

Những thành phần này giúp chuyển hiểu biết rời rạc thành một mô hình có thể thảo luận, kiểm chứng và sau đó biểu diễn bằng phần mềm hoặc ngôn ngữ chuyên biệt.

## 2. Vì sao phải xác định miền trước khi thiết kế DSL?

Ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL) được thiết kế để diễn đạt một nhóm vấn đề thuộc một miền xác định. DSL có thể cung cấp cú pháp gần với cách chuyên gia nghiệp vụ suy nghĩ, đồng thời áp đặt quy tắc để các mô tả được kiểm tra và thực thi nhất quán.

Nếu chưa xác định miền, nhóm phát triển dễ bắt đầu từ các cấu trúc kỹ thuật như bảng dữ liệu, lớp, API hoặc câu lệnh. Kết quả có thể là một ngôn ngữ mang hình thức riêng nhưng không phản ánh đúng cách người dùng làm việc. Ngược lại, khi hiểu miền, nhóm có thể xác định:

1. **Ai sẽ viết hoặc đọc DSL:** chuyên gia nghiệp vụ, chuyên viên vận hành, nhà phân tích hay lập trình viên.
2. **Vấn đề nào cần diễn đạt:** quy tắc, chính sách, quy trình, cấu hình hay mô tả một loại tài nguyên.
3. **Thuật ngữ nào cần xuất hiện trong cú pháp:** từ ngữ có nghĩa ổn định với người sử dụng.
4. **Quy tắc nào cần được kiểm tra:** điều kiện hợp lệ, giới hạn, thứ tự ưu tiên và các trường hợp xung đột.
5. **Mô tả DSL có tác động gì:** tạo cấu hình, đánh giá điều kiện, sinh kế hoạch hoặc điều khiển một quy trình.

Xác định miền cũng giúp giữ DSL đủ tập trung. Một DSL cố gắng diễn tả mọi hoạt động của cả doanh nghiệp thường trở nên khó học, khó kiểm tra và khó thay đổi. Một DSL quá hẹp có thể chỉ thay thế một vài dòng cấu hình mà không đem lại lợi ích đáng kể.

Không phải miền nghiệp vụ nào cũng cần DSL. DSL phù hợp hơn khi một nhóm người thường xuyên phải mô tả các quy tắc hoặc cấu trúc lặp lại, các khái niệm tương đối ổn định, và việc diễn đạt bằng ngôn ngữ tổng quát hoặc cấu hình thuần túy gây khó khăn. Nếu công việc chỉ xảy ra một lần, quy tắc thay đổi liên tục hoặc người dùng cần khả năng lập trình tùy ý, một công cụ thông thường có thể phù hợp hơn.

## 3. Phân biệt các khái niệm liên quan

Các thuật ngữ dưới đây có liên hệ với nhau nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Lĩnh vực kinh doanh | Phạm vi hoạt động rộng của tổ chức hoặc ngành | Bán lẻ |
| Miền nghiệp vụ | Nhóm kiến thức và trách nhiệm xoay quanh một mục tiêu nghiệp vụ | Quản lý khuyến mãi |
| Miền con (subdomain) | Một phần có mục tiêu hoặc chuyên môn riêng trong một miền lớn hơn | Tính điều kiện áp dụng ưu đãi |
| Ngữ cảnh được giới hạn (bounded context) | Ranh giới trong đó mô hình và thuật ngữ có một cách hiểu nhất quán | Ngữ cảnh quản lý khuyến mãi |
| Quy trình nghiệp vụ | Chuỗi hoạt động để tạo ra một kết quả | Tiếp nhận, xét duyệt và kích hoạt chiến dịch |
| Module hoặc dịch vụ phần mềm | Cách tổ chức giải pháp kỹ thuật | Dịch vụ khuyến mãi |
| DSL | Ngôn ngữ dùng để mô tả vấn đề hoặc quy tắc trong một phạm vi cụ thể | Ngôn ngữ khai báo điều kiện và quyền lợi khuyến mãi |

Một miền nghiệp vụ có thể được triển khai bằng nhiều module hoặc dịch vụ. Ngược lại, một module kỹ thuật đôi khi hỗ trợ nhiều miền. Vì vậy, không nên lấy tên package, bảng cơ sở dữ liệu, microservice hoặc phòng ban làm ranh giới miền một cách máy móc.

Trong tư duy Domain-Driven Design (DDD), cần đặc biệt chú ý đến hai khái niệm:

- **Subdomain:** cách chia lĩnh vực nghiệp vụ thành những phần nhỏ hơn để hiểu mục tiêu và mức độ quan trọng của từng phần. DDD thường phân biệt miền cốt lõi (core), miền hỗ trợ (supporting) và miền tổng quát (generic).
- **Bounded context:** ranh giới mà trong đó một mô hình miền, thuật ngữ và quy tắc có ý nghĩa thống nhất. Cùng một từ có thể mang nghĩa khác nhau ở hai ngữ cảnh.

Phân loại subdomain giúp quyết định nên đầu tư chuyên môn và năng lực phát triển vào đâu. Xác định bounded context giúp tránh việc một thuật ngữ hoặc mô hình bị dùng với nhiều nghĩa không tương thích. Hai cách nhìn này hỗ trợ xác định miền, nhưng không thay thế việc tìm hiểu hoạt động thực tế.

## 4. Quy trình xác định miền nghiệp vụ

### Bước 1: Bắt đầu từ mục tiêu và vấn đề

Viết một câu ngắn mô tả kết quả mà tổ chức muốn đạt được. Câu mô tả nên nói về giá trị nghiệp vụ, không phải tên công nghệ hoặc chức năng giao diện.

Ví dụ:

- Chưa rõ: “Xây dựng màn hình nhập mã giảm giá.”
- Rõ hơn: “Cho phép doanh nghiệp định nghĩa và áp dụng chính sách khuyến mãi đúng đối tượng, đúng thời hạn và theo các điều kiện đã công bố.”

Tiếp theo, xác định vấn đề hiện tại: công việc nào đang tốn thời gian, quyết định nào thường gây nhầm lẫn, quy tắc nào đang được xử lý thủ công hoặc có nhiều cách hiểu. Điều này giúp phân biệt nhu cầu thực tế với một giải pháp đã được đề xuất sẵn.

### Bước 2: Xác định các bên liên quan và người có kiến thức

Liệt kê những người tham gia, người ra quyết định, người nhận kết quả và hệ thống có trao đổi dữ liệu với miền. Có thể bao gồm:

- Người trực tiếp thực hiện công việc.
- Người sở hữu chính sách hoặc chịu trách nhiệm phê duyệt.
- Bộ phận hỗ trợ, kiểm soát hoặc kiểm toán.
- Khách hàng hoặc đối tác chịu ảnh hưởng.
- Hệ thống bên ngoài cung cấp dữ liệu hoặc nhận kết quả.

Không nên chỉ phỏng vấn quản lý hoặc chỉ hỏi nhóm kỹ thuật. Người thực hiện công việc thường biết các ngoại lệ và thao tác thực tế; người quản lý hiểu mục tiêu, quyền hạn và chính sách; nhóm kỹ thuật hiểu các ràng buộc tích hợp. Cần đối chiếu các góc nhìn này.

### Bước 3: Quan sát công việc và mô tả các kịch bản

Chọn một số tình huống điển hình, sau đó mô tả từ lúc công việc bắt đầu đến khi có kết quả. Với mỗi tình huống, ghi lại:

1. Điều gì kích hoạt công việc?
2. Ai hoặc hệ thống nào thực hiện từng hành động?
3. Thông tin nào được sử dụng?
4. Quyết định được đưa ra theo điều kiện nào?
5. Trạng thái hoặc dữ liệu nào thay đổi?
6. Kết quả được chuyển cho ai?
7. Điều gì xảy ra khi dữ liệu thiếu, điều kiện không đạt hoặc có ngoại lệ?

Nên xem cả trường hợp thành công, bị từ chối, bị hủy, được sửa đổi và phải xử lý lại. Các trường hợp ngoại lệ thường bộc lộ ranh giới trách nhiệm rõ hơn kịch bản lý tưởng.

Một kỹ thuật hữu ích là Event Storming: tập hợp người hiểu nghiệp vụ và người phát triển để cùng ghi nhận sự kiện đã xảy ra, lệnh hoặc yêu cầu dẫn đến sự kiện, quy tắc, tác nhân và hệ thống liên quan. Hoạt động này giúp phát hiện những cách hiểu khác nhau và những điểm bàn giao giữa các nhóm.

### Bước 4: Thu thập ngôn ngữ của miền

Ghi lại các danh từ, động từ, trạng thái và cụm từ mà người trong lĩnh vực thực sự sử dụng. Không vội thay chúng bằng tên lớp hoặc tên cột trong cơ sở dữ liệu.

Với mỗi thuật ngữ, làm rõ:

- Định nghĩa được các bên liên quan thống nhất.
- Ví dụ cụ thể và trường hợp không được xem là ví dụ.
- Thuộc tính hoặc thông tin làm cho khái niệm có ý nghĩa.
- Các trạng thái và chuyển đổi hợp lệ.
- Những thuật ngữ gần nghĩa hoặc dễ bị nhầm lẫn.
- Ngữ cảnh mà thuật ngữ được sử dụng.

Ví dụ, “chiến dịch”, “mã ưu đãi”, “điều kiện áp dụng” và “quyền lợi” có thể là các khái niệm khác nhau. Không nên dùng từ “khuyến mãi” cho tất cả nếu người dùng cần phân biệt chúng khi tạo hoặc kiểm tra chính sách.

Kết quả của bước này là một bảng thuật ngữ nghiệp vụ (glossary). Bảng thuật ngữ nên được các chuyên gia nghiệp vụ xác nhận và cập nhật khi mô hình thay đổi.

### Bước 5: Tìm quy tắc, bất biến và quyết định

Quy tắc nghiệp vụ mô tả điều kiện hoặc chính sách chi phối hoạt động. Hãy chuyển các câu nói chung chung thành phát biểu có thể kiểm chứng.

Ví dụ:

- Mơ hồ: “Khuyến mãi dành cho khách hàng thân thiết.”
- Cụ thể: “Chỉ khách hàng có hạng thành viên từ Vàng trở lên mới đủ điều kiện.”

Với từng quy tắc, xác định chủ sở hữu, dữ liệu đầu vào, thời điểm áp dụng, ngoại lệ và cách xử lý khi nhiều quy tắc cùng có hiệu lực.

Phân biệt:

- **Quy tắc nghiệp vụ:** chính sách do tổ chức đặt ra, có thể thay đổi theo quyết định kinh doanh.
- **Bất biến (invariant):** điều kiện phải luôn đúng để mô hình không rơi vào trạng thái không hợp lệ.
- **Ràng buộc kỹ thuật:** giới hạn do nền tảng, giao thức hoặc cách triển khai tạo ra.

Ví dụ, “mỗi mã ưu đãi chỉ được đổi một lần trên một đơn hàng” có thể là quy tắc nghiệp vụ. “Tổng tiền sau giảm giá không được âm” có thể là bất biến của phép tính. “Tên mã tối đa 64 ký tự” có thể là ràng buộc của hệ thống. Cần biết nguồn gốc của từng điều kiện để xác định ai có quyền thay đổi nó.

### Bước 6: Xác định ranh giới trong và ngoài miền

Ranh giới miền cho biết miền chịu trách nhiệm đến đâu. Hãy lập hai danh sách:

- **Trong phạm vi:** quyết định, dữ liệu, quy trình và quy tắc mà miền sở hữu.
- **Ngoài phạm vi:** hoạt động thuộc miền khác, dù có trao đổi dữ liệu hoặc ảnh hưởng đến kết quả.

Có thể dùng các câu hỏi sau:

- Miền nhận đầu vào nào và tạo ra kết quả nào?
- Ai chịu trách nhiệm cuối cùng khi kết quả sai?
- Miền có quyền quyết định trạng thái nào?
- Dữ liệu nào là nguồn có thẩm quyền?
- Khi một quy tắc thay đổi, nhóm nào phải phê duyệt?
- Điểm bàn giao với miền khác nằm ở đâu?

Một ranh giới tốt giữ các quy tắc có liên quan gần nhau, đồng thời làm rõ các phần phụ thuộc vào miền khác. Không cần tách mọi chức năng thành một miền riêng; chỉ nên tách khi có khác biệt đáng kể về mục tiêu, thuật ngữ, quy tắc, quyền sở hữu hoặc nhịp độ thay đổi.

### Bước 7: Chia miền con và nhận diện ngữ cảnh

Nếu phạm vi quá rộng, chia thành các miền con theo năng lực hoặc mục tiêu nghiệp vụ. Trong DDD, có thể xem xét:

- **Miền cốt lõi:** năng lực tạo lợi thế hoặc giá trị khác biệt quan trọng đối với tổ chức.
- **Miền hỗ trợ:** năng lực cần thiết để vận hành nhưng không phải lợi thế cạnh tranh chính.
- **Miền tổng quát:** vấn đề phổ biến có thể giải quyết bằng giải pháp tiêu chuẩn hoặc dịch vụ có sẵn.

Sau đó, xác định các bounded context. Hãy chú ý nơi thuật ngữ đổi nghĩa, quy tắc khác nhau hoặc quyền sở hữu dữ liệu chuyển sang nhóm khác. Nếu hai nhóm dùng cùng một từ nhưng có định nghĩa và vòng đời khác nhau, cần ghi nhận hai cách hiểu thay vì ép chúng vào một mô hình chung.

Các ngữ cảnh có thể giao tiếp qua hợp đồng rõ ràng, chẳng hạn sự kiện, API hoặc thông điệp. Hợp đồng cần chỉ rõ ý nghĩa dữ liệu và trách nhiệm của bên gửi, bên nhận.

### Bước 8: Kiểm chứng ranh giới bằng tình huống thực tế

Đưa mô hình miền trở lại cho người hiểu nghiệp vụ xem xét. Chọn các tình huống bình thường, ngoại lệ và thay đổi chính sách. Hỏi xem mô hình có diễn tả được quyết định thực tế hay không, có thuật ngữ nào bị dùng sai hay trách nhiệm nào chưa có chủ sở hữu.

Nếu một quy tắc phải được giải thích bằng nhiều ngoại lệ không liên quan, miền có thể đang gộp các ngữ cảnh khác nhau. Nếu một kịch bản đơn giản phải đi qua quá nhiều miền mà không có lý do nghiệp vụ rõ ràng, ranh giới có thể bị chia quá nhỏ.

## 5. Ví dụ: xác định miền quản lý khuyến mãi

Giả sử một doanh nghiệp bán lẻ muốn chuẩn hóa cách tạo và áp dụng khuyến mãi. Ban đầu, yêu cầu được mô tả là “làm màn hình tạo mã giảm giá”. Sau khi trao đổi với bộ phận tiếp thị, bán hàng và vận hành, nhóm phát triển nhận ra vấn đề rộng hơn: chính sách được lưu ở nhiều nơi, điều kiện áp dụng không nhất quán, và nhân viên khó giải thích vì sao một đơn hàng được hoặc không được hưởng ưu đãi.

### 5.1 Mục tiêu và tác nhân

**Mục tiêu:** cho phép doanh nghiệp định nghĩa, kiểm tra và áp dụng chính sách khuyến mãi theo các điều kiện có thể giải thích được.

Các tác nhân chính:

- Nhân viên tiếp thị tạo chiến dịch và xác định đối tượng.
- Người quản lý phê duyệt chính sách.
- Hệ thống bán hàng yêu cầu đánh giá điều kiện cho giỏ hàng hoặc đơn hàng.
- Nhân viên hỗ trợ tra cứu lý do một ưu đãi được áp dụng hoặc bị từ chối.

### 5.2 Thuật ngữ ban đầu

| Thuật ngữ | Cách hiểu trong miền |
|---|---|
| Chiến dịch | Hoạt động khuyến mãi có mục tiêu và thời gian xác định |
| Điều kiện áp dụng | Tiêu chí phải thỏa mãn để được hưởng ưu đãi |
| Quyền lợi | Giá trị ưu đãi mà khách hàng nhận được |
| Mã ưu đãi | Mã khách hàng cung cấp để yêu cầu áp dụng một chính sách |
| Thứ tự ưu tiên | Cách lựa chọn khi nhiều chính sách cùng phù hợp |
| Kết hợp ưu đãi | Quy định một ưu đãi có được áp dụng cùng ưu đãi khác hay không |

Các định nghĩa này là bản đầu tiên. Nhóm cần xác nhận chúng với người sở hữu chính sách và bổ sung các trường hợp cụ thể trước khi dùng làm từ vựng chính thức của DSL.

### 5.3 Phạm vi trách nhiệm

| Thuộc miền quản lý khuyến mãi | Thuộc miền phối hợp khác |
|---|---|
| Định nghĩa chiến dịch và thời hạn | Quản lý hồ sơ khách hàng |
| Khai báo điều kiện áp dụng | Quản lý danh mục sản phẩm |
| Khai báo quyền lợi và giới hạn ưu đãi | Quản lý đơn hàng |
| Xác định thứ tự ưu tiên và khả năng kết hợp | Thanh toán và quyết toán |
| Đánh giá chính sách và trả về lý do | Quản lý tồn kho và giao nhận |

Miền khuyến mãi có thể cần thông tin hạng thành viên, sản phẩm và giá trị giỏ hàng, nhưng không vì thế mà sở hữu toàn bộ hồ sơ khách hàng, danh mục sản phẩm hoặc vòng đời đơn hàng. Các miền phối hợp cung cấp dữ liệu qua giao diện hoặc hợp đồng đã thống nhất.

### 5.4 Quy tắc cần làm rõ

Trước khi thiết kế cú pháp, nhóm cần trả lời những câu hỏi như:

- Thời điểm bắt đầu và kết thúc được tính theo múi giờ nào?
- Điều kiện giá trị đơn hàng được tính trước hay sau khi áp dụng ưu đãi?
- Một khách hàng có thể sử dụng cùng mã nhiều lần không?
- Hai ưu đãi cùng hợp lệ thì ưu tiên theo thứ tự nào?
- Ưu đãi phần trăm có giới hạn số tiền giảm tối đa không?
- Nếu dữ liệu hạng thành viên không có, hệ thống từ chối hay yêu cầu tra cứu lại?
- Người dùng có thể xem lý do không đủ điều kiện hay không?

Những câu hỏi này quyết định mô hình và ngữ nghĩa của DSL. Nếu chưa có câu trả lời, cần ghi nhận đó là quyết định nghiệp vụ đang chờ xác nhận, không tự đặt ra quy tắc trong mã nguồn.

### 5.5 Từ mô hình miền đến một DSL minh họa

Sau khi thuật ngữ và quy tắc đã được xác nhận, nhóm có thể thử một cú pháp khai báo:

~~~text
khuyen_mai "Thanh vien Vang"
  hieu_luc tu "2026-12-01" den "2026-12-31"
  ap_dung_khi:
    hang_thanh_vien >= "VANG"
    va gia_tri_gio_hang >= 2000000
  quyen_loi:
    giam_phan_tram 10
    toi_da 300000
  uu_tien 20
  khong_ket_hop_voi "Giam gia don hang"
~~~

Đây chỉ là ví dụ để minh họa cách dùng từ vựng nghiệp vụ trong DSL, chưa phải cú pháp hoàn chỉnh. Một thiết kế thực tế còn phải định nghĩa kiểu dữ liệu, đơn vị tiền tệ, cách so sánh hạng thành viên, múi giờ, cách xử lý ngày biên, quy tắc kết hợp và thông báo lỗi.

Điều quan trọng là mỗi thành phần cú pháp phải có ý nghĩa nghiệp vụ rõ ràng:

- Tên khuyến mãi xác định chính sách được khai báo.
- Khoảng hiệu lực giới hạn thời gian có thể áp dụng.
- Các điều kiện xác định đối tượng hoặc giao dịch đủ tiêu chuẩn.
- Quyền lợi mô tả kết quả khi điều kiện thỏa mãn.
- Thứ tự ưu tiên và quy tắc kết hợp giải quyết xung đột giữa nhiều chính sách.

Ví dụ cho thấy việc xác định miền giúp lựa chọn đúng khái niệm cho DSL. Nếu nhóm chưa thống nhất “giá trị giỏ hàng” được tính thế nào, việc đưa tên trường đó vào cú pháp chỉ che giấu một quyết định nghiệp vụ chưa được giải quyết.

## 6. Dấu hiệu cho thấy ranh giới miền chưa hợp lý

### Phạm vi quá rộng

- Một miền chứa nhiều mục tiêu ít liên quan.
- Thuật ngữ giống nhau nhưng mỗi nhóm giải thích khác nhau.
- Thay đổi ở một chính sách kéo theo sửa nhiều phần không liên quan.
- Một DSL phải có rất nhiều từ khóa hoặc ngoại lệ để bao quát mọi công việc.

Hướng xử lý: tách theo mục tiêu, quyền quyết định, vòng đời hoặc mô hình ngôn ngữ; sau đó xác định hợp đồng giữa các phần.

### Phạm vi quá hẹp

- Một miền chỉ chứa một thao tác đơn lẻ nhưng không có quy tắc hoặc trách nhiệm độc lập.
- Các miền nhỏ phải gọi lẫn nhau liên tục để hoàn thành một quyết định nghiệp vụ.
- Ranh giới được tạo chỉ vì cấu trúc package hoặc nhóm triển khai.

Hướng xử lý: xem xét gộp những phần có cùng mục tiêu, cùng ngôn ngữ và cùng chủ sở hữu quy tắc. Không nên tạo ranh giới chỉ để đạt một con số module hoặc dịch vụ mong muốn.

### Mô hình chỉ phản ánh hệ thống hiện tại

- Tên trường dữ liệu được dùng làm thuật ngữ nghiệp vụ dù người dùng không hiểu chúng.
- Quy trình được mô tả theo màn hình hoặc API thay vì công việc thực tế.
- Các quy tắc đang nằm trong mã nguồn được xem là chính sách đúng mà không hỏi người sở hữu.

Hướng xử lý: quay lại kịch bản thực tế, tài liệu chính sách và người chịu trách nhiệm. Hệ thống hiện tại là một nguồn tham khảo, không phải định nghĩa cuối cùng của miền.

## 7. Khi nào một miền phù hợp để xây dựng DSL?

Sau khi xác định miền và ranh giới, đánh giá nhu cầu DSL theo các tiêu chí:

| Tiêu chí | Dấu hiệu phù hợp |
|---|---|
| Công việc lặp lại | Nhiều quy tắc hoặc mô tả cùng dạng được tạo và cập nhật thường xuyên |
| Từ vựng ổn định | Chuyên gia có thể thống nhất các khái niệm và cách gọi |
| Có người dùng rõ ràng | Xác định được ai tạo, xem, phê duyệt hoặc vận hành mô tả |
| Quy tắc kiểm chứng được | Có thể phát hiện cấu trúc sai, điều kiện mâu thuẫn hoặc giá trị không hợp lệ |
| Có lợi ích khi diễn đạt khai báo | Người dùng mô tả điều muốn đạt được thay vì tự viết toàn bộ thuật toán |
| Có cách thực thi xác định | Mỗi mô tả hợp lệ có thể được diễn giải hoặc thực thi theo ngữ nghĩa rõ ràng |

Nếu các tiêu chí này chưa được đáp ứng, nên tiếp tục làm rõ mô hình và quy tắc trước khi đầu tư vào parser hoặc cú pháp. Có thể bắt đầu bằng biểu mẫu, bảng quy tắc hoặc một bản mô tả có cấu trúc để kiểm chứng nhu cầu.

## 8. Đầu ra cần có sau khi xác định miền

Một kết quả xác định miền hữu ích nên đủ rõ để người nghiệp vụ và người phát triển cùng sử dụng. Có thể lập một hồ sơ miền với các mục sau:

| Thành phần | Nội dung cần ghi |
|---|---|
| Tên miền | Tên ngắn, phản ánh mục tiêu nghiệp vụ |
| Mục tiêu | Giá trị hoặc kết quả miền chịu trách nhiệm tạo ra |
| Phạm vi | Những hoạt động và quyết định thuộc miền |
| Ngoài phạm vi | Những trách nhiệm thuộc miền hoặc hệ thống khác |
| Tác nhân | Người dùng, nhóm, hệ thống và chủ sở hữu chính sách |
| Kịch bản chính | Các luồng công việc điển hình và ngoại lệ |
| Thuật ngữ | Từ vựng, định nghĩa, ví dụ và cách dùng |
| Quy tắc | Điều kiện, bất biến, giới hạn và ngoại lệ |
| Sự kiện | Những điều đã xảy ra và ảnh hưởng đến miền |
| Ranh giới ngữ cảnh | Các cách hiểu khác nhau và điểm bàn giao |
| Dữ liệu và hợp đồng | Đầu vào, đầu ra, nguồn có thẩm quyền và giao diện tích hợp |
| Nhu cầu DSL | Người dùng DSL, loại mô tả, lợi ích và phạm vi biểu đạt |
| Vấn đề còn mở | Những quyết định cần chuyên gia nghiệp vụ xác nhận |

Hồ sơ này không phải tài liệu cố định. Khi quy trình, chính sách hoặc cách tổ chức thay đổi, cần cập nhật mô hình và xem xét lại ranh giới. Một miền được xác định tốt là nền tảng để xây dựng từ vựng, cú pháp, ngữ nghĩa, bộ kiểm tra và cơ chế thực thi của DSL.

## 9. Câu hỏi tự kiểm tra

1. Vì sao “màn hình tạo mã giảm giá” chưa đủ để xác định miền nghiệp vụ?
2. Phân biệt miền nghiệp vụ, miền con và bounded context.
3. Vì sao không nên dùng cấu trúc microservice hoặc phòng ban làm ranh giới miền một cách tự động?
4. Nêu ba loại thông tin cần thu thập khi quan sát một kịch bản nghiệp vụ.
5. Phân biệt quy tắc nghiệp vụ, bất biến và ràng buộc kỹ thuật.
6. Với miền quản lý khuyến mãi, dữ liệu khách hàng và đơn hàng có nhất thiết thuộc quyền sở hữu của miền này không? Giải thích.
7. Nêu những dấu hiệu cho thấy một miền đang có phạm vi quá rộng hoặc quá hẹp.
8. Những điều kiện nào khiến một miền trở thành ứng viên phù hợp để xây dựng DSL?

Khi trả lời, hãy dùng ví dụ và chỉ rõ ai là người sở hữu quy tắc. Nếu không thể xác định chủ sở hữu, thuật ngữ hoặc cách xử lý ngoại lệ, mô hình miền vẫn cần được làm rõ trước khi chuyển thành thiết kế kỹ thuật.

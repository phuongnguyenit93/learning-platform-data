# Tài sản dữ liệu

## 1. Tài sản dữ liệu là gì?

**Tài sản dữ liệu** là tập thông tin có giá trị đối với hoạt động, quyết định hoặc trách nhiệm của một tổ chức và cần được quản lý, bảo vệ trong vòng đời sử dụng.

Giá trị của dữ liệu không chỉ nằm ở việc giữ bí mật. Một bảng giá đã công khai vẫn cần đúng và sẵn sàng. Một bản ghi quyền nhỏ có thể quyết định ai được truy cập toàn bộ hệ thống. Một lịch sử thao tác có thể không trực tiếp tạo doanh thu nhưng cần thiết để điều tra và phục hồi sự cố.

Ví dụ về tài sản dữ liệu:

- Hồ sơ khách hàng và thông tin giao nhận.
- Đơn hàng, trạng thái xử lý và lịch sử thay đổi.
- Chính sách quyền, phân công và quan hệ giữa các tenant.
- Khóa mật mã, thông tin xác thực và phiên.
- Sự kiện kiểm toán, log và dữ liệu chẩn đoán.
- Bản xuất, báo cáo, chỉ mục tìm kiếm và bản sao lưu.

Nhận diện tài sản dữ liệu giúp trả lời: **bảo vệ thông tin nào, trước hậu quả nào, ai chịu trách nhiệm và cần bằng chứng gì để xác nhận việc bảo vệ**.

### 1.1. Phân biệt tài sản dữ liệu với nơi chứa dữ liệu

| Khái niệm | Ví dụ | Câu hỏi quản lý |
| --- | --- | --- |
| Tài sản dữ liệu | Thông tin giao nhận của khách hàng | Ai được xem, được dùng vào đâu, giữ bao lâu? |
| Kho hoặc nơi biểu diễn | Bảng dữ liệu, tệp xuất, cache, bản sao lưu | Dữ liệu nằm đâu, có những bản sao nào? |
| Thành phần xử lý | API, worker, dịch vụ báo cáo | Ai đọc, biến đổi, chuyển tiếp dữ liệu? |
| Hạ tầng hỗ trợ | Máy chủ, cụm lưu trữ, mạng | Thành phần nào duy trì xử lý và lưu trữ? |
| Biện pháp bảo vệ | Phân quyền, mã hóa, kiểm toán, phục hồi | Kiểm soát nào đáp ứng nghĩa vụ bảo vệ? |

“Cơ sở dữ liệu production” là thông tin quan trọng về hạ tầng và nơi lưu, nhưng chưa thay thế được danh mục tài sản dữ liệu bên trong. Một cơ sở dữ liệu có thể chứa dữ liệu công khai, thông tin cá nhân, chính sách quyền và bí mật xác thực với yêu cầu khác nhau.

Ngược lại, một tài sản dữ liệu có thể có nhiều biểu diễn: bản ghi gốc, phản hồi API, bản xuất, cache và bản sao lưu. Chỉ bảo vệ một biểu diễn chưa đủ nếu dữ liệu vẫn đi ra qua đường khác.

### 1.2. Không chỉ dữ liệu cá nhân mới là tài sản

Dữ liệu cá nhân cần được xem xét về quyền riêng tư, nhưng tài sản dữ liệu còn có:

- Quy tắc phê duyệt và chính sách phân quyền.
- Cấu hình kết nối và tham số vận hành.
- Danh mục sản phẩm hoặc thông tin công khai cần giữ đúng.
- Khóa ký, khóa giải mã hoặc thông tin xác thực dịch vụ.
- Trạng thái công việc và dữ liệu cần phục hồi nghiệp vụ.

Tổ chức cần bảo vệ chúng theo hậu quả nếu bị lộ, bị sửa, bị mất hoặc không còn sử dụng được.

## 2. Các nhóm tài sản dữ liệu thường gặp

Có thể dùng nhóm để phát hiện phạm vi, nhưng không nên coi danh sách nhóm là một hệ thống phân loại bắt buộc.

| Nhóm | Ví dụ | Đặc tính cần chú ý |
| --- | --- | --- |
| Dữ liệu nghiệp vụ | Đơn hàng, tồn kho, kết quả phê duyệt | Tính đúng, nhất quán và khả năng phục hồi |
| Thông tin khách hàng hoặc người dùng | Liên hệ, địa chỉ, hội thoại | Phạm vi truy cập, mục đích xử lý và lưu giữ |
| Dữ liệu điều khiển | Vai trò, quyền, trạng thái khóa tài khoản | Một thay đổi nhỏ có thể mở rộng đặc quyền |
| Cấu hình vận hành | Điểm kết nối, cờ tính năng, chính sách xử lý lỗi | Sai cấu hình có thể làm mất hiệu lực kiểm soát |
| Bí mật và vật liệu mật mã | Token, khóa, thông tin xác thực dịch vụ | Quyền sử dụng, phạm vi ảnh hưởng và khả năng thay thế |
| Dữ liệu kiểm toán | Chủ thể, thao tác, tài nguyên, kết quả | Tính toàn vẹn, khả năng liên kết và quyền đọc |
| Dữ liệu chẩn đoán | Log lỗi, trace, dump | Có thể sao chép nội dung hoặc bí mật ngoài ý định |
| Dữ liệu dẫn xuất | Báo cáo, phân nhóm, chỉ mục, kết quả tổng hợp | Có thể còn nhạy cảm hoặc suy luận được dữ liệu gốc |
| Bản sao và dữ liệu phục hồi | Bản xuất, tệp tạm, sao lưu | Quyền truy cập, thời hạn và điều kiện dùng lại |
| Metadata | Tên tệp, mã tenant, định danh tài nguyên, thời điểm | Có thể làm lộ quan hệ, sự tồn tại hoặc hành vi |

Một đối tượng có thể thuộc nhiều nhóm. Bản sao lưu chứa thông tin cá nhân vẫn mang yêu cầu riêng tư; dữ liệu kiểm toán chứa định danh vẫn có yêu cầu bí mật.

### 2.1. Bí mật xác thực là dữ liệu có khả năng trao quyền

Không phải mọi dữ liệu bị lộ đều có cùng hậu quả. Lộ một token hoặc khóa có thể cho phép chủ thể khác thực hiện hành động, giải mã dữ liệu hoặc tạo bằng chứng giả.

Khi lập danh mục, ghi loại bí mật, chủ sở hữu, vị trí quản lý và phạm vi sử dụng. **Không đưa giá trị bí mật thật vào danh mục hoặc bài mô tả.** Danh mục có thể trỏ tới hệ thống quản lý phù hợp bằng một tham chiếu không tiết lộ bí mật.

Cần phân biệt quyền đọc bí mật với quyền sử dụng bí mật qua một dịch vụ. Một thành phần có thể được phép thực hiện thao tác ký hoặc giải mã mà không được phép lấy giá trị khóa.

### 2.2. Dữ liệu dẫn xuất không tự giảm mức bảo vệ

Bỏ tên khỏi báo cáo chưa chắc loại bỏ khả năng liên kết với cá nhân. Một nhóm thống kê rất nhỏ hoặc kết quả kết hợp nhiều nguồn có thể tiết lộ nhiều hơn từng nguồn riêng lẻ.

Mã hóa, nén, đổi định dạng hoặc băm cũng không tự làm dữ liệu trở thành công khai. Phải xét khả năng khôi phục, đối chiếu, liên kết và quyền của người nhận.

## 3. Nhận diện tài sản từ hoạt động và luồng dữ liệu

Một cách thực dụng là bắt đầu từ các việc hệ thống thực hiện, rồi lần theo dữ liệu cần cho từng việc.

### 3.1. Đi từ nghiệp vụ đến dữ liệu

Với mỗi chức năng, hỏi:

1. Quyết định hoặc kết quả nghiệp vụ dựa trên dữ liệu nào?
2. Dữ liệu do ai cung cấp và ai xác nhận là đúng?
3. Thành phần nào đọc, sửa hoặc tạo mới dữ liệu?
4. Dữ liệu được gửi tới ai hoặc dịch vụ nào?
5. Có bản sao, dữ liệu dẫn xuất hoặc lịch sử nào được tạo ra?
6. Khi lỗi, thử lại hoặc phục hồi, dữ liệu đi đâu?
7. Nếu dữ liệu bị lộ, bị thay đổi hoặc mất đi, hậu quả là gì?

Ví dụ, chức năng xuất đơn hàng không chỉ liên quan bảng đơn hàng. Nó còn dùng quyền của người yêu cầu, bộ lọc, thông điệp công việc, tệp tạm, tệp kết quả, trạng thái công việc và log.

### 3.2. Theo dõi bản gốc và các biểu diễn

~~~mermaid
flowchart LR
    S["Nguồn dữ liệu"] --> P["Xử lý nghiệp vụ"]
    P --> D["Kho dữ liệu chính"]
    P --> A["Phản hồi API"]
    D --> W["Tác vụ xuất hoặc báo cáo"]
    W --> E["Tệp và dữ liệu dẫn xuất"]
    P --> L["Log và kiểm toán"]
    D --> B["Quy trình sao lưu"]
    B --> K["Kho sao lưu"]
    K --> R["Quy trình phục hồi"]
    R --> D
~~~

Sơ đồ minh họa nơi tài sản có thể xuất hiện. Mỗi hệ thống cần xác nhận các đường thực tế; không mặc định có mũi tên là luồng đã được bảo vệ.

Danh mục nên liên kết một tài sản logic với các biểu diễn và nơi lưu liên quan. Nếu bản xuất có quyền, thời hạn hoặc người nhận khác bản gốc, cần ghi riêng các thuộc tính đó để quản lý được.

## 4. Phân loại theo hậu quả cần bảo vệ

Phân loại tài sản dữ liệu là xác định những thuộc tính và mức tác động có ý nghĩa đối với việc bảo vệ. Không nên chỉ gán một nhãn “nhạy cảm” rồi dùng nhãn đó thay cho mọi yêu cầu.

### 4.1. Ba chiều bí mật, toàn vẹn và sẵn sàng

| Chiều đánh giá | Câu hỏi | Ví dụ hậu quả |
| --- | --- | --- |
| Confidentiality — tính bí mật | Nếu chủ thể ngoài quyền đọc được dữ liệu thì sao? | Lộ thông tin giao nhận hoặc bí mật truy cập |
| Integrity — tính toàn vẹn | Nếu dữ liệu bị sửa, thiếu hoặc gắn sai thì sao? | Giao sai hàng, cấp nhầm quyền, phê duyệt sai |
| Availability — tính sẵn sàng | Nếu dữ liệu không sử dụng được đúng lúc thì sao? | Ngừng tiếp nhận đơn, không tra cứu được trạng thái |

Ba chiều không nhất thiết có cùng mức:

| Tài sản minh họa | Bí mật | Toàn vẹn | Sẵn sàng | Lý do |
| --- | --- | --- | --- | --- |
| Danh mục sản phẩm đã công khai | Thấp | Cao | Cao trong giờ phục vụ | Được phép đọc rộng, nhưng giá trị sai hoặc không tra cứu được ảnh hưởng nghiệp vụ |
| Địa chỉ giao nhận | Cao | Cao | Theo bước xử lý đơn | Lộ ảnh hưởng khách hàng; sai dẫn đến giao nhầm |
| Chính sách quyền | Cao theo phạm vi tổ chức | Rất cao | Cao tại điểm quyết định quyền | Sai quyền có thể mở truy cập tới nhiều tài sản khác |
| Khóa giải mã dữ liệu | Rất cao | Rất cao | Theo nhu cầu sử dụng và phục hồi | Lộ cho phép giải mã; mất có thể khiến dữ liệu không dùng được |
| Bản xuất tạm thời có thể tạo lại | Theo nội dung gốc | Cao | Có thể thấp hơn kho gốc | Có thể tái tạo, nhưng không được lộ hoặc trả sai dữ liệu |
| Sự kiện kiểm toán | Theo trường chứa trong sự kiện | Cao | Theo nhu cầu phát hiện và điều tra | Thiếu hoặc sửa dấu vết làm giảm khả năng truy vết |

Các mức là nhận định minh họa trong bối cảnh giả định. Tổ chức phải định nghĩa thang đo và lý do gán mức; không sao chép bảng như chính sách chung.

Tính sẵn sàng cũng không chỉ là “có truy vấn được không”. Dữ liệu có thể tồn tại nhưng thiếu khóa, sai định dạng hoặc không nhất quán nên không thể dùng an toàn.

### 4.2. Xét thêm quyền riêng tư và vòng đời

Với dữ liệu liên quan tới cá nhân, cần ghi mục đích, trường cần thiết, bên nhận và thời hạn. Một tập dữ liệu được giữ bí mật vẫn có thể bị dùng vượt mục đích.

Ngoài ra cần xét:

- Dữ liệu có thể tái tạo được không?
- Nguồn nào được coi là có thẩm quyền?
- Có cần giữ lịch sử để đối chiếu hoặc phục hồi không?
- Có nhiều tenant, môi trường hoặc bên vận hành không?
- Số lượng và mức tập trung dữ liệu làm thay đổi tác động thế nào?
- Dữ liệu hết hạn hoặc bị thu hồi quyền được xử lý ra sao?

Một bản ghi ít nhạy cảm có thể trở nên đáng quan tâm hơn khi ghép thành lịch sử hành vi của nhiều người. Một kho tổng hợp cũng có thể gây hậu quả lớn hơn từng tập nhỏ do phạm vi bị ảnh hưởng.

### 4.3. Nhãn phân loại phải dẫn đến quy tắc xử lý

Nếu dùng nhãn như “công khai”, “nội bộ”, “hạn chế” và “bí mật”, cần định nghĩa:

- Ai có thẩm quyền gán và thay đổi nhãn.
- Điều kiện chia sẻ, xuất hoặc đưa vào môi trường thử.
- Yêu cầu về quyền truy cập và bảo vệ khi truyền, khi lưu.
- Quy tắc log, sao lưu, lưu giữ và loại bỏ.
- Cách xử lý tập dữ liệu có nhiều mức khác nhau.

Không nên mặc định mọi bản ghi trong một cơ sở dữ liệu có cùng mức. Có thể cần phân loại ở cấp tập dữ liệu, trường hoặc nhóm tài nguyên, tùy việc tách có giúp thực thi được chính sách hay không.

Khi chưa thể tách an toàn, áp dụng quy tắc xử lý bảo vệ được thành phần nhạy cảm trong phạm vi đó. Khi dữ liệu được biến đổi, chỉ giảm mức bảo vệ sau khi đánh giá và có quyết định phù hợp; không giảm chỉ vì tên tệp hoặc định dạng đã đổi.

### 4.4. Phân loại tài sản khác với đánh giá rủi ro

Phân loại trả lời dữ liệu quan trọng thế nào và cần bảo vệ thuộc tính nào. Đánh giá rủi ro xét thêm tình huống đe dọa, điểm yếu, khả năng xảy ra và kiểm soát hiện có.

Dữ liệu có tác động cao không đồng nghĩa đang có lỗ hổng. Dữ liệu ít bí mật cũng không đồng nghĩa mọi rủi ro đều thấp: bảng giá công khai bị sửa trái phép có thể gây thiệt hại lớn.

Không cộng các nhãn bí mật, toàn vẹn và sẵn sàng thành một con số nếu chưa có phương pháp được thống nhất. Một điểm trung bình có thể che mất thuộc tính đặc biệt quan trọng.

## 5. Giao trách nhiệm cho tài sản

Một danh mục có tên tài sản nhưng không có người chịu trách nhiệm thường nhanh chóng mất hiệu lực.

| Vai trò | Trách nhiệm điển hình |
| --- | --- |
| Chủ sở hữu dữ liệu | Làm rõ giá trị, mục đích, mức tác động, quy tắc truy cập và nhu cầu giữ dữ liệu |
| Người quản lý chất lượng hoặc nghiệp vụ dữ liệu | Duy trì định nghĩa, ý nghĩa trường, chất lượng và quy tắc sử dụng |
| Bên quản trị kỹ thuật | Vận hành kho, cấu hình quyền, sao lưu, bảo vệ và xử lý sự cố |
| Người hoặc dịch vụ sử dụng | Sử dụng trong phạm vi được cấp và mục đích đã xác định |
| Chủ sở hữu rủi ro | Quyết định xử lý rủi ro còn lại theo thẩm quyền của tổ chức |

Tên vai trò có thể khác giữa các tổ chức; một người có thể kiêm nhiều vai trò. Điều cần giữ là trách nhiệm và quyền quyết định rõ ràng.

Chủ sở hữu dữ liệu trong quản trị không đồng nghĩa với cá nhân được dữ liệu mô tả. Người vận hành máy chủ cũng không tự động có quyền cho phép mọi việc sử dụng dữ liệu.

Trong hệ thống nhiều tenant, cần làm rõ phần quyết định của doanh nghiệp sử dụng và phần trách nhiệm của đơn vị cung cấp nền tảng. Không suy ra rằng bên lưu dữ liệu được tự dùng nội dung của tenant cho mục đích khác.

## 6. Lập danh mục tài sản dữ liệu

Một hồ sơ có thể bắt đầu gọn, sau đó bổ sung các thuộc tính cần cho kiểm soát.

| Trường thông tin | Nội dung cần ghi |
| --- | --- |
| Mã và tên | Định danh ổn định, tên theo ý nghĩa nghiệp vụ |
| Mô tả và phạm vi | Tập bản ghi, trường quan trọng, tenant hoặc môi trường liên quan |
| Mục đích | Tại sao cần dữ liệu và được dùng vào đâu |
| Nguồn và nơi có thẩm quyền | Ai tạo, nguồn nào giải quyết khi có mâu thuẫn |
| Chủ sở hữu và bên vận hành | Ai quyết định, ai thực hiện bảo vệ |
| Đánh giá tác động | Bí mật, toàn vẹn, sẵn sàng và lý do |
| Dữ liệu liên quan đến cá nhân | Chủ thể liên quan, khả năng liên kết và yêu cầu xử lý |
| Nơi lưu và biểu diễn | Kho chính, cache, xuất, chỉ mục, log, sao lưu |
| Bên sử dụng và nhận | Người, dịch vụ, tenant hoặc nhà cung cấp |
| Vòng đời | Tạo, thay đổi, hết hạn, lưu giữ, loại bỏ và phục hồi |
| Phụ thuộc | Quyền, khóa, cấu hình hoặc tài sản cần để dữ liệu sử dụng được |
| Yêu cầu bảo vệ | Các nghĩa vụ có thể thiết kế và kiểm chứng |
| Trạng thái xác nhận | Điều đã biết, giả định và câu hỏi còn mở |
| Thời điểm xem lại | Khi nào hồ sơ được xác nhận và điều gì kích hoạt cập nhật |

Không nhất thiết liệt kê từng hàng dữ liệu thành một tài sản riêng. Chọn mức quản lý đủ để phân biệt chủ sở hữu, tác động, quyền và vòng đời.

Ví dụ, tách “thông tin liên hệ” khỏi “ghi chú hạn chế” có ích nếu hai tập có quyền khác nhau. Tạo một tài sản cho mỗi khách hàng thường không cần thiết nếu cùng một chính sách có thể mô tả được nhóm đó.

Danh mục cũng có thể chứa thông tin nhạy cảm về kiến trúc và vị trí dữ liệu. Cần quản lý quyền đọc, tránh ghi giá trị bí mật hoặc sao chép dữ liệu thật vào mô tả.

## 7. Ví dụ: tài sản dữ liệu trong hệ thống quản lý đơn hàng

Giả sử một nền tảng phục vụ nhiều doanh nghiệp. Mỗi tenant có sản phẩm, khách hàng, đơn hàng và thành viên riêng. Hệ thống cho phép phê duyệt đơn, xuất dữ liệu, xem lịch sử và phục hồi khi sự cố.

### 7.1. Danh mục ban đầu

| Mã | Tài sản | Giá trị hoặc tác động chính | Chủ sở hữu nghiệp vụ minh họa |
| --- | --- | --- | --- |
| DATA-01 | Danh mục sản phẩm được công bố | Dữ liệu phải đúng và truy cập được trong phạm vi công bố | Bộ phận quản lý sản phẩm của tenant |
| DATA-02 | Đơn hàng và lịch sử trạng thái | Sai hoặc mất dữ liệu có thể làm thực hiện sai nghiệp vụ | Bộ phận vận hành đơn hàng của tenant |
| DATA-03 | Hồ sơ khách hàng và thông tin giao nhận | Có thể lộ thông tin cá nhân hoặc gây giao nhầm | Bộ phận quản lý khách hàng của tenant |
| DATA-04 | Vai trò, quyền và phân công | Quyết định ai được đọc, sửa hoặc phê duyệt | Chủ sở hữu chính sách quyền đã xác định |
| DATA-05 | Bí mật dịch vụ và khóa cần dùng | Có thể mở rộng quyền hoặc làm dữ liệu không khôi phục được | Đơn vị phụ trách cơ chế bảo vệ |
| DATA-06 | Sự kiện kiểm toán | Giúp truy vết các thay đổi và quyết định | Đơn vị phụ trách kiểm toán nghiệp vụ và bảo mật |
| DATA-07 | Tệp xuất đơn hàng | Bản dữ liệu dễ được sao chép hoặc chia sẻ | Chủ sở hữu dữ liệu nguồn, có trách nhiệm kỹ thuật được giao |
| DATA-08 | Tập dữ liệu phục hồi | Giúp khôi phục đơn hàng, quyền và cấu hình cần thiết | Chủ sở hữu từng tập dữ liệu cùng bên vận hành phục hồi |

DATA-07 và DATA-08 được quản lý riêng vì có quyền truy cập, nơi lưu và vòng đời khác nguồn. Chúng vẫn phải giữ liên kết với tài sản nguồn, không được coi là dữ liệu không liên quan.

Bảng mới là điểm bắt đầu. Chưa thể suy ra tất cả trách nhiệm hoặc mức bảo vệ chỉ từ tên chủ sở hữu; cần xác nhận theo tổ chức thực tế.

### 7.2. Hồ sơ chi tiết cho DATA-02

~~~text
Mã: DATA-02
Tên: Đơn hàng và lịch sử trạng thái

Phạm vi:
- Đơn hàng của từng tenant.
- Mã khách hàng, dòng hàng, tổng giá trị, trạng thái, lịch sử thao tác.
- Các trường giao nhận được chụp vào đơn nếu nghiệp vụ có dùng.

Mục đích:
- Tiếp nhận, theo dõi, phê duyệt và thực hiện đơn hàng.
- Đối chiếu các thay đổi theo phạm vi đã xác định.

Nguồn có thẩm quyền:
- Kho đơn hàng nghiệp vụ theo quy tắc cập nhật đã chọn.
- Bản xuất và báo cáo không tự trở thành nguồn thay thế.

Chủ sở hữu:
- Bộ phận vận hành đơn hàng của tenant.
- Bên vận hành nền tảng thực hiện các kiểm soát kỹ thuật đã giao.

Tác động:
- Bí mật: cao đối với nội dung không được công bố.
- Toàn vẹn: cao, do thay đổi sai ảnh hưởng quyết định nghiệp vụ.
- Sẵn sàng: cao trong khoảng phục vụ đã xác định.
- Các mức cần được chủ sở hữu xác nhận cùng lý do.

Biểu diễn và nơi lưu:
- Kho chính, bản sao phục vụ đọc, cache nếu có.
- Phản hồi API, bản xuất, dữ liệu báo cáo.
- Bản sao lưu và dữ liệu phục hồi.
- Các trường được phép trong kiểm toán; không mặc định log toàn bộ.

Bên sử dụng:
- Thành viên có quyền trong đúng tenant và phạm vi tài nguyên.
- Dịch vụ hoặc worker được giao nhiệm vụ với giới hạn phù hợp.

Vòng đời:
- Tạo, cập nhật trạng thái, lưu lịch sử, hết thời hạn sử dụng.
- Thời hạn giữ và loại bỏ lấy từ chính sách đã được xác nhận.
- Phục hồi phải đối chiếu tính nhất quán và trạng thái quyền.

Phụ thuộc:
- DATA-04 để quyết định quyền.
- DATA-05 nếu dữ liệu hoặc bản sao được mã hóa.
- Quy tắc nghiệp vụ và cấu hình để diễn giải trạng thái.
~~~

Hồ sơ không chứa dữ liệu khách hàng thật hoặc giá trị khóa. Chỗ chưa xác nhận, chẳng hạn thời hạn giữ, phải được giao cho người có trách nhiệm làm rõ.

### 7.3. Theo một bản sao tới nơi sử dụng cuối

Giả sử worker tạo tệp xuất từ DATA-02 và một số trường của DATA-03:

| Bước | Dữ liệu hoặc bản sao | Điều phải được quản lý |
| --- | --- | --- |
| API nhận yêu cầu | Bộ lọc, người yêu cầu, phạm vi tenant | Quyền xuất và điều kiện tiếp nhận |
| Gửi công việc | Tham chiếu công việc và ngữ cảnh cần thiết | Ai được tạo, đọc và chạy lại thông điệp |
| Worker đọc dữ liệu | Tập đơn hàng và thông tin khách hàng được phép | Phạm vi truy vấn và quyền tại mốc đã chọn |
| Tạo tệp | CSV hoặc định dạng được chọn | Tập trường, tệp tạm, tenant và người được tải |
| Lưu kết quả | Nội dung tệp và metadata | Quyền kho, thời hạn và tham chiếu công việc |
| Tải kết quả | Nội dung được chuyển cho người nhận | Danh tính và quyền tại thời điểm tải |
| Dọn hoặc phục hồi | Bản hết hạn hoặc bản được khôi phục | Chính sách loại bỏ và trạng thái quyền hiện hành |

Nếu đơn hàng có bản chụp địa chỉ, không thể coi việc sửa hoặc xóa hồ sơ khách hàng gốc là đã tự thay đổi mọi bản chụp trong đơn, tệp xuất và sao lưu. Phải xác định mục đích cùng quy tắc xử lý cho từng biểu diễn.

Một tệp được đổi tên hoặc đưa sang kho khác vẫn giữ tính chất dữ liệu bên trong. Phân loại phải theo nội dung và ngữ cảnh sử dụng.

## 8. Các phụ thuộc làm thay đổi giá trị và phạm vi bảo vệ

### 8.1. Quyền là tài sản dữ liệu tác động tới tài sản khác

DATA-04 có thể ít bản ghi hơn DATA-02 nhưng điều khiển việc đọc và thay đổi DATA-02. Vì vậy cần xem:

- Ai được sửa quyền, và có giới hạn theo tenant không?
- Thay đổi quyền có dấu vết không?
- Quyền bị thu hồi lan truyền tới các điểm sử dụng thế nào?
- Bản sao lưu cũ có làm sống lại quyền đã thu hồi không?
- Dịch vụ có dùng bản quyền cũ khi không liên lạc được nguồn không?

Chỉ kiểm kê dữ liệu nghiệp vụ mà bỏ qua dữ liệu điều khiển sẽ làm thiếu một nhóm tài sản có phạm vi ảnh hưởng lớn.

### 8.2. Dữ liệu mã hóa phụ thuộc khả năng dùng khóa

Có bản sao dữ liệu không đồng nghĩa có thể phục hồi. Còn cần khóa, cấu hình và các thông tin giúp giải mã, diễn giải và kiểm tra dữ liệu.

Ngược lại, mất kiểm soát khóa có thể làm mất tính bí mật của nhiều bản sao. Hồ sơ tài sản cần thể hiện:

- Khóa hoặc cơ chế nào liên quan tới tập dữ liệu.
- Chủ thể nào được dùng, quản lý hoặc thay thế.
- Dữ liệu cũ và bản sao lưu chịu ảnh hưởng thế nào khi thay đổi khóa.
- Phụ thuộc có tồn tại trong kịch bản sự cố đang xét không.

Không ghi giá trị khóa để “làm đầy đủ hồ sơ”. Dùng định danh hoặc tham chiếu được quản lý phù hợp.

### 8.3. Danh mục dùng chung có thể mang ranh giới tenant

Dùng chung một bảng không có nghĩa dữ liệu của mọi tenant thuộc cùng một phạm vi quyền. Cần mô tả cách gắn bản ghi với tenant và cách dữ liệu đi qua dịch vụ, cache, xuất, log hoặc báo cáo.

Tương tự, một tenant có nhiều vai trò khác nhau. Quyền quản trị thành viên không tự đồng nghĩa quyền đọc mọi trường hoặc xuất mọi dữ liệu.

### 8.4. Nguồn có thẩm quyền và dữ liệu dẫn xuất

Khi cache, chỉ mục hoặc báo cáo mâu thuẫn với dữ liệu gốc, phải biết nguồn nào quyết định. Nếu một báo cáo được dùng để ra quyết định quan trọng, cần đánh giá độ mới, tính đầy đủ và cách đối chiếu.

Việc tái tạo được dữ liệu dẫn xuất có thể giảm nhu cầu phục hồi riêng cho nó, nhưng không giảm nghĩa vụ giữ bí mật hoặc trả đúng dữ liệu trong lúc nó tồn tại.

## 9. Chuyển phân loại thành yêu cầu bảo mật

Phân loại chỉ có giá trị khi dẫn tới nghĩa vụ cụ thể. “DATA-02 rất quan trọng” chưa cho người thiết kế biết phải làm gì hoặc người kiểm thử biết cần quan sát gì.

Có thể dùng chuỗi:

**Tài sản → thuộc tính cần bảo vệ → tình huống rủi ro → yêu cầu → thành phần thực hiện → bằng chứng.**

### 9.1. Ma trận truy vết minh họa

| Tài sản | Tình huống rủi ro | Yêu cầu bảo vệ | Kiểm chứng dự kiến |
| --- | --- | --- | --- |
| DATA-02, DATA-03, DATA-07 | Người tenant A đọc hoặc xuất dữ liệu tenant B | A-REQ-01: xác thực và kiểm tra quyền theo tenant, tài nguyên, trường và thao tác | Kiểm thử API, tìm kiếm và tải bản xuất bằng các danh tính khác phạm vi |
| DATA-02, DATA-04 | Người không có quyền đổi trạng thái hoặc cấp quyền | A-REQ-02: kiểm tra thẩm quyền và điều kiện nghiệp vụ trước thay đổi | Thử đường bị cấm; kiểm tra cả dữ liệu và tác động bất đồng bộ |
| DATA-05, DATA-06 | Bí mật hoặc nội dung nhạy cảm đi vào log | A-REQ-03: giới hạn trường log và người đọc; loại trừ dữ liệu bị cấm | Dùng giá trị giả có dấu nhận diện, kiểm tra đường thành công và lỗi |
| DATA-02, DATA-04, DATA-05, DATA-08 | Không phục hồi được dữ liệu hoặc mở lại quyền cũ | A-REQ-04: phục hồi đủ dữ liệu, phụ thuộc và trạng thái quyền trước khi mở nghiệp vụ | Diễn tập phục hồi, đối chiếu dữ liệu và thử quyền đã thu hồi |
| DATA-07 và các bản sao | Bản xuất còn dùng được quá hạn hoặc giữ ngoài chính sách | A-REQ-05: chặn truy cập và dọn bản sao theo phạm vi, thời hạn đã xác định | Thử quanh mốc hết hạn và kiểm tra các phiên bản trong phạm vi |
| DATA-03, DATA-07 | Dữ liệu được dùng hoặc chia sẻ vượt mục đích | A-REQ-06: chỉ dùng tập trường, người nhận và mục đích đã được xác định | Kiểm tra schema, luồng xuất, quyền dịch vụ và các đích nhận |
| DATA-04, DATA-05 | Danh tính kỹ thuật có thể tự mở rộng quyền hoặc lấy bí mật không cần thiết | A-REQ-07: giới hạn quyền sử dụng, quản trị và thay đổi cấu hình bảo vệ | Kiểm tra cấu hình và thử bằng danh tính không có quyền tương ứng |

Bảng là kế hoạch minh họa, không phải kết quả rằng một hệ thống đã đáp ứng.

Một yêu cầu có thể bảo vệ nhiều tài sản. Một tài sản có thể cần nhiều yêu cầu vì có đồng thời nhu cầu bí mật, toàn vẹn và sẵn sàng.

### 9.2. Ví dụ yêu cầu cho tính bí mật

> **A-REQ-01:** Trước khi trả dữ liệu đơn hàng hoặc bản xuất, dịch vụ phải xác minh danh tính và quyền của chủ thể đối với tenant, tài nguyên cùng tập trường đích. Nếu không có quyền hoặc không xác định được quyền, không trả nội dung dữ liệu bị hạn chế.

Tiêu chí chấp nhận cần bao phủ:

- Chủ thể hợp lệ trong phạm vi được cấp nhận đúng dữ liệu.
- Chủ thể khác tenant bị từ chối dù biết mã tài nguyên.
- Chủ thể cùng tenant nhưng thiếu quyền không được vượt phạm vi.
- Endpoint danh sách, tìm kiếm và bản xuất áp dụng cùng nghĩa vụ phù hợp.
- Lỗi kiểm tra quyền không dẫn tới cho phép mặc định.
- Phản hồi lỗi không chứa bản sao nội dung bị cấm.

Ẩn nút ở giao diện hoặc chỉ kiểm tra lúc đăng nhập chưa đủ để chứng minh yêu cầu.

### 9.3. Ví dụ yêu cầu cho toàn vẹn

> **A-REQ-02:** Chỉ chủ thể có quyền tương ứng mới được chuyển trạng thái đơn hàng hoặc thay đổi quyền. Dịch vụ phải xác nhận điều kiện trên trạng thái có hiệu lực tại thời điểm thực hiện theo thiết kế nhất quán đã chọn. Yêu cầu bị từ chối không được làm đổi dữ liệu hoặc phát sinh tác động nghiệp vụ.

Cần xem xét trường hợp trạng thái hoặc quyền thay đổi đồng thời. Một lần kiểm tra quá sớm có thể không đủ nếu dữ liệu đã đổi trước khi ghi.

Bằng chứng phải gồm dữ liệu sau thao tác và các công việc đã phát sinh. Mã lỗi HTTP không chứng minh thao tác bị chặn nếu hàng đợi đã nhận một lệnh thực hiện nghiệp vụ.

### 9.4. Ví dụ yêu cầu phục hồi có thể đo

Giả sử chủ sở hữu nghiệp vụ chọn các mục tiêu minh họa cho kịch bản mất kho đơn hàng chính:

> **A-REQ-04:** Với quy mô dữ liệu và tài nguyên phục hồi được mô tả trong kế hoạch, hệ thống phải khôi phục mức phục vụ đã xác định trong tối đa 60 phút từ thời điểm gián đoạn. Khoảng thời gian từ điểm dữ liệu khôi phục được tới thời điểm gián đoạn không được vượt quá 15 phút. Trước khi mở nghiệp vụ nhạy cảm, phải xác minh tính nhất quán, khả năng dùng khóa và trạng thái quyền hiện hành.

Trong ví dụ:

- **RTO — Recovery Time Objective:** mục tiêu thời gian phục hồi là 60 phút.
- **RPO — Recovery Point Objective:** mục tiêu mức mất dữ liệu theo thời gian là 15 phút.

Các số là giả định học tập, không suy ra tự động từ nhãn “sẵn sàng cao”. Cần chọn theo nghiệp vụ, phụ thuộc và khả năng thực hiện.

Tạo sao lưu mỗi 15 phút chưa đủ chứng minh RPO 15 phút. Cần phục hồi được bản hợp lệ, xác định điểm dữ liệu thực tế và đối chiếu giao dịch hoặc thay đổi quanh thời điểm sự cố.

Nếu bản sao lưu có quyền cũ, quy trình phải đối soát các thay đổi thu hồi sau điểm sao lưu hoặc xác lập lại quyền theo phương án đã chấp nhận. Khi chưa có trạng thái đáng tin cậy, chức năng nhạy cảm phải tiếp tục bị chặn.

## 10. Kiểm chứng danh mục và phạm vi bảo vệ

Kiểm tra danh mục là xác nhận mô hình phản ánh dữ liệu và trách nhiệm thực tế, không chỉ kiểm tra đã điền đủ ô.

### 10.1. Đối chiếu theo một tình huống đầu cuối

Chọn một thao tác, chẳng hạn phê duyệt và xuất đơn hàng, rồi lần theo:

1. Dữ liệu đầu vào và nguồn tạo.
2. Dữ liệu quyền dùng để quyết định.
3. Kho được đọc hoặc cập nhật.
4. Thông điệp và công việc nền.
5. Tệp, cache, chỉ mục hoặc báo cáo được tạo.
6. Log, sự kiện kiểm toán và dữ liệu lỗi.
7. Bản sao lưu cùng các phụ thuộc để phục hồi.
8. Quy trình hết hạn và loại bỏ.

Với mỗi điểm, đối chiếu xem có tài sản hoặc biểu diễn tương ứng, chủ sở hữu, mức tác động và yêu cầu liên quan chưa.

Trong một dự án, bằng chứng có thể đến từ hợp đồng dữ liệu, cấu hình, đường xử lý, quan sát thử nghiệm và xác nhận của bên vận hành. Cần ghi rõ đang mô tả thiết kế dự kiến hay hệ thống đã triển khai.

### 10.2. Kiểm tra cả trường hợp thành công và thất bại

Đường lỗi có thể giữ dữ liệu mà đường thành công không giữ:

- Yêu cầu bị lỗi được ghi toàn bộ vào log.
- Thông điệp nằm lâu trong hàng đợi lỗi.
- Tệp tạm còn lại sau khi worker dừng.
- Bản xuất tạo thành công nhưng mất liên kết tới công việc.
- Phục hồi thử nghiệm để lại bản dữ liệu trong môi trường ít được bảo vệ hơn.

Những bản sao này cần được đưa vào danh mục hoặc liên kết với tài sản nguồn. Không gọi là “tạm” rồi bỏ qua quyền đọc và thời hạn.

### 10.3. Đánh giá độ bao phủ có giới hạn rõ ràng

Có thể theo dõi:

- Tập dữ liệu đã có chủ sở hữu trên tổng số tập trong phạm vi đã biết.
- Tài sản đã đánh giá đủ các chiều tác động.
- Biểu diễn và nơi lưu đã được đối chiếu với luồng dữ liệu.
- Yêu cầu có bằng chứng kiểm chứng phù hợp với phiên bản đang xét.
- Câu hỏi còn mở và dữ liệu chưa rõ vòng đời.

Các tỷ lệ giúp quản lý công việc, không chứng minh danh mục đã phát hiện mọi dữ liệu hoặc hệ thống không còn rủi ro. Phải ghi mẫu số, phạm vi, giả định và phần chưa xác nhận.

Không dùng nhiều mục ít quan trọng đã hoàn tất để che một tài sản có phạm vi ảnh hưởng lớn nhưng chưa rõ chủ sở hữu hoặc cách bảo vệ.

## 11. Những lỗi thường gặp khi nhận diện tài sản dữ liệu

| Cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Chỉ liệt kê tên cơ sở dữ liệu | Không thấy dữ liệu và yêu cầu khác nhau bên trong | Tách tài sản theo ý nghĩa, quyền, tác động và vòng đời |
| Chỉ quan tâm dữ liệu cá nhân | Bỏ sót quyền, khóa, cấu hình và dữ liệu công khai quan trọng | Đánh giá hậu quả đối với mọi nhóm dữ liệu |
| Gán một mức “nhạy cảm” cho mọi thuộc tính | Không phân biệt bí mật, toàn vẹn và sẵn sàng | Ghi từng chiều cùng lý do |
| Coi bản sao lưu hoặc log là vấn đề hạ tầng thuần túy | Bỏ qua nội dung, người đọc và điều kiện phục hồi | Liên kết với tài sản nguồn và chính sách riêng |
| Cho rằng dữ liệu đã mã hóa hoặc băm thì có thể giảm nhãn ngay | Không xét quyền giải mã, khả năng đoán và liên kết | Đánh giá lại theo ngữ cảnh và quyết định có thẩm quyền |
| Ghi bí mật thật trong danh mục | Tạo thêm nơi làm lộ quyền truy cập | Chỉ ghi loại, tham chiếu và phạm vi sử dụng |
| Giao mọi quyết định cho quản trị kỹ thuật | Không rõ giá trị nghiệp vụ hoặc thẩm quyền sử dụng | Tách trách nhiệm quyết định và thực hiện |
| Phân loại một lần rồi giữ nguyên | Bỏ sót thay đổi trường, người nhận và bản sao | Xem lại theo thay đổi thực tế |
| Coi danh mục đầy đủ là đã bảo vệ xong | Chưa có nghĩa vụ, thiết kế và bằng chứng | Nối tài sản tới rủi ro, yêu cầu và kiểm chứng |

## 12. Duy trì hồ sơ trong vòng đời phát triển

Cần xem lại tài sản khi thêm trường, API, bản xuất, hệ thống báo cáo, nhà cung cấp, danh tính dịch vụ hoặc môi trường dữ liệu. Thay đổi cách dùng có thể làm thay đổi tác động ngay cả khi schema không đổi.

Ví dụ, một tập dữ liệu ban đầu chỉ dùng cho xử lý đơn được kết hợp thành lịch sử hành vi khách hàng. Khi đó cần đánh giá lại mục đích, khả năng liên kết, bên nhận và thời hạn; không tự kế thừa toàn bộ kết luận cũ.

Một bộ hồ sơ đủ để tiếp tục đặc tả bảo mật nên có:

- Tên tài sản và phạm vi dữ liệu rõ ràng.
- Chủ sở hữu, bên vận hành và người quyết định về rủi ro.
- Đánh giá bí mật, toàn vẹn, sẵn sàng cùng lý do.
- Mục đích và yêu cầu liên quan đến cá nhân nếu có.
- Nguồn có thẩm quyền, biểu diễn, nơi lưu và bên nhận.
- Vòng đời cùng phụ thuộc để sử dụng hoặc phục hồi.
- Liên kết tới rủi ro, yêu cầu và bằng chứng cần thu thập.
- Giả định, câu hỏi còn mở và điều kiện cập nhật.

Khi hồ sơ trả lời được những nội dung này, nhóm phát triển có căn cứ để chọn kiểm soát và kiểm thử theo hậu quả thực tế của dữ liệu, thay vì bảo vệ mọi thứ bằng một nhãn chung không thể nghiệm thu.

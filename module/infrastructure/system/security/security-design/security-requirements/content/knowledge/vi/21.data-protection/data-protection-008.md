# Sensitive field encryption — Đặc tả mã hóa từng trường dữ liệu nhạy cảm

## 1. Từ mục tiêu bảo vệ dữ liệu đến yêu cầu nghiệm thu

Một hệ thống lưu hồ sơ khách hàng có mã định danh cá nhân, thông tin liên hệ và ghi chú hỗ trợ. Database đã bật mã hóa ổ đĩa, nhưng tài khoản báo cáo vẫn có thể chạy truy vấn để lấy toàn bộ mã định danh. Một bản xuất dữ liệu logic cũng chứa những giá trị đọc được.

Yêu cầu “dữ liệu nhạy cảm phải được mã hóa” chưa chỉ ra rủi ro nào đã được xử lý. Mã hóa ổ đĩa bảo vệ một số tình huống mất thiết bị hoặc sao chép dữ liệu vật lý; nó không tự ngăn người có quyền đọc qua database engine nhìn thấy dữ liệu.

**Sensitive field encryption**, hay mã hóa từng trường nhạy cảm, đặt cơ chế bảo vệ vào những thuộc tính cụ thể. Trong thiết kế mã hóa ở tầng ứng dụng, ứng dụng biến plaintext thành ciphertext trước khi ghi xuống nơi lưu trữ. Bên đọc database chỉ nhận được ciphertext nếu họ không đồng thời có quyền hoặc khả năng sử dụng khóa giải mã.

Trong chương Data protection, nhiệm vụ không dừng ở chọn thuật toán. Cần chuyển mục tiêu an toàn thông tin và mô hình đe dọa thành yêu cầu cụ thể về:

- Trường nào được mã hóa và ở thời điểm nào.
- Thành phần nào được giữ hoặc sử dụng khóa.
- Ai được phép yêu cầu giải mã, cho bản ghi nào và với mục đích nào.
- Cách phát hiện ciphertext bị sửa hoặc bị chuyển sang sai ngữ cảnh.
- Ảnh hưởng đến tìm kiếm, logging, sao lưu, phục hồi và vận hành.
- Bằng chứng nào cho phép kết luận hệ thống đáp ứng yêu cầu.

Bài học tập trung vào mã hóa trường ở tầng ứng dụng. Nếu dự án dùng tính năng mã hóa cột của database hoặc driver, vẫn phải xác định cùng các ranh giới: thành phần nào nhìn thấy plaintext, thành phần nào có khóa và bằng chứng nào chứng minh quyền truy cập đã được giới hạn.

## 2. Phân biệt các kiểm soát dễ bị gọi chung là “mã hóa”

| Kiểm soát | Tác dụng chính | Giới hạn cần nêu trong yêu cầu |
|---|---|---|
| TLS | Bảo vệ dữ liệu trên một kết nối được cấu hình đúng | Plaintext vẫn tồn tại tại hai đầu kết nối |
| Mã hóa ổ đĩa hoặc TDE | Bảo vệ dữ liệu lưu trữ vật lý trong những tình huống tương ứng | Quyền đọc hợp lệ qua engine có thể vẫn nhận plaintext |
| Mã hóa trường ở ứng dụng | Giữ ciphertext ở database và các luồng lưu trữ đã bao phủ | Dịch vụ được phép giải mã vẫn có thể thấy plaintext |
| Masking | Giới hạn phần thông tin được hiển thị | Không chứng minh giá trị gốc đã được mã hóa khi lưu |
| Hashing | Tạo giá trị một chiều cho mục đích phù hợp | Không thay thế mã hóa khi nghiệp vụ phải khôi phục giá trị gốc |
| Tokenization | Thay giá trị bằng token và quản lý ánh xạ ở thành phần riêng | Kho ánh xạ và quyền truy cập trở thành ranh giới quan trọng |

Không dùng mã hóa có thể đảo ngược để lưu mật khẩu đăng nhập thông thường. Mật khẩu cần cơ chế băm mật khẩu chuyên dụng với salt và cấu hình chi phí phù hợp. Mã định danh cần đọc lại để thực hiện nghiệp vụ là một bài toán khác.

Masking và mã hóa trường có thể cùng cần thiết: database giữ ciphertext, dịch vụ có quyền chỉ trả vài ký tự cuối cho màn hình thông thường, còn luồng xem đầy đủ yêu cầu quyền riêng. Quyền đọc bản ghi không mặc nhiên bao gồm quyền xem mọi trường nhạy cảm.

## 3. Chốt mô hình đe dọa và giới hạn bảo vệ

### 3.1. Một mục tiêu có thể kiểm chứng

Ví dụ mục tiêu thiết kế:

> Bản dump logic của database hồ sơ không được chứa plaintext của trường mã định danh cá nhân. Tài khoản chỉ có quyền đọc database, không có quyền gọi dịch vụ giải mã hoặc sử dụng khóa, không thể lấy lại giá trị gốc từ các trường đã bảo vệ bằng khả năng truy cập được cấp.

Phạm vi này phải bao gồm cả cột chính, bản ghi lịch sử, bảng tạm, bản sao đọc, dữ liệu xuất và những luồng liên quan đã được nhận diện. Mã hóa một cột nhưng vẫn lưu cùng giá trị trong bảng audit không đạt mục tiêu.

Không nên tuyên bố “database bị xâm nhập thì dữ liệu luôn an toàn”. Nếu kẻ tấn công đồng thời kiểm soát danh tính dịch vụ có quyền giải mã, họ có thể sử dụng đường giải mã được cấp cho danh tính đó. Mô hình đe dọa phải phân biệt hai khả năng.

### 3.2. Bảng rủi ro và quyết định thiết kế

| Tình huống | Kiểm soát cần đặc tả | Giới hạn còn lại |
|---|---|---|
| Tài khoản chỉ đọc database bị lộ | Mã hóa trước khi lưu; khóa tách khỏi dữ liệu | Metadata, độ dài và các trường không mã hóa có thể vẫn lộ |
| Người có quyền sửa database đổi ciphertext | Mã hóa có xác thực; xử lý lỗi toàn vẹn | Kẻ tấn công vẫn có thể xóa dữ liệu hoặc gây gián đoạn |
| Ciphertext bị chép sang bản ghi hoặc tenant khác | Ràng buộc ngữ cảnh bằng AAD | Không thay thế phân quyền truy cập bản ghi |
| Ciphertext cũ hợp lệ được ghi đè lên bản mới | Cơ chế chống rollback nếu nằm trong mô hình đe dọa | Xác thực ciphertext đơn thuần không chứng minh tính mới nhất |
| Tài khoản hỗ trợ xem quá nhiều dữ liệu | Quyền giải mã theo đối tượng, trường và mục đích | Người đã được cấp quyền vẫn có thể sao chép plaintext họ thấy |
| Dịch vụ ứng dụng bị chiếm quyền | Giảm quyền, giới hạn phạm vi khóa, giám sát và cô lập | Mã hóa trường không tự bảo vệ plaintext trong tiến trình đó |
| Khóa hoặc dịch vụ quản lý khóa không sẵn sàng | Chính sách lỗi, dự phòng, sao lưu và diễn tập phục hồi | Không được đánh đổi bằng lưu plaintext dự phòng |

Mã hóa không giải quyết đầy đủ tính sẵn sàng. Ciphertext có thể bị xóa, khóa có thể bị mất, và yêu cầu giải mã có thể bị từ chối. Các rủi ro này phải được đưa vào yêu cầu phục hồi.

## 4. Lập danh mục trường và toàn bộ vòng đời dữ liệu

Với mỗi trường, cần ghi ít nhất:

| Thuộc tính | Ví dụ mô tả |
|---|---|
| Tên nghiệp vụ | Mã định danh cá nhân của khách hàng |
| Mức nhạy cảm và tác động | Có thể liên kết trực tiếp với một cá nhân |
| Nhu cầu đọc lại | Chỉ luồng xác minh đã được phân quyền cần giá trị đầy đủ |
| Nguồn đầu vào | API tiếp nhận hồ sơ và tác vụ import được kiểm soát |
| Nơi lưu hoặc sao chép | Database, lịch sử thay đổi, queue, backup và file xuất |
| Nơi sử dụng plaintext | Dịch vụ xác minh và màn hình có quyền xem đầy đủ |
| Nhu cầu truy vấn | Tìm chính xác; không yêu cầu sắp xếp hoặc tìm theo khoảng |
| Thời hạn lưu | Theo chính sách dữ liệu đã được dự án chốt |
| Chủ sở hữu | Nhóm nghiệp vụ và nhóm chịu trách nhiệm kiểm soát |
| Bằng chứng | Kiểm tra luồng ghi, phân quyền giải mã và phục hồi |

Không đưa cùng một giá trị vào log để “dễ hỗ trợ” sau khi đã quyết định mã hóa. Danh mục phải theo đường đi thực tế, không chỉ theo tên cột.

Các quyết định hợp đồng dữ liệu cũng cần rõ:

- Giá trị vắng mặt và chuỗi rỗng có được xem là khác nhau không?
- Kiểu, độ dài tối đa và biểu diễn Unicode nào được chấp nhận?
- Chuẩn hóa xảy ra trước mã hóa hay chỉ trước tạo chỉ mục tìm kiếm?
- API trả giá trị đầy đủ, giá trị đã che hay không trả trường này?
- Bản ghi bị xóa kéo theo xử lý chỉ mục, cache và bản sao như thế nào?

Mã hóa có xác thực thường làm tăng kích thước lưu trữ vì có nonce, tag và metadata. Base64 làm tăng kích thước biểu diễn thêm nữa. Cần tính trên số byte sau encoding thay vì chỉ nhìn số ký tự của dữ liệu đầu vào.

## 5. Kiến trúc tham chiếu và ranh giới khóa

Một kiến trúc tham chiếu có thể được mô tả như sau:

```text
Caller đã được xác thực
        |
        v
API kiểm tra quyền trên đối tượng, trường và mục đích
        |
        v
Dịch vụ xử lý dữ liệu nhạy cảm
        |                        |
        |                        +--> Dịch vụ quản lý khóa
        |                             dùng danh tính workload
        v
Database: ciphertext + metadata + DEK đã được bọc
```

Plaintext tồn tại tại nơi nhận đầu vào và trong các thao tác nghiệp vụ cần thiết. Mục tiêu là giới hạn thời gian, thành phần và quyền có thể tiếp cận plaintext, không phải tuyên bố plaintext chưa từng tồn tại.

Một phương án phổ biến là **envelope encryption**:

1. Dùng khóa mã hóa dữ liệu, gọi là DEK, để mã hóa trường hoặc một nhóm dữ liệu được xác định.
2. Dùng khóa bảo vệ khóa, gọi là KEK, trong dịch vụ quản lý khóa để bọc DEK.
3. Lưu ciphertext và DEK đã được bọc cùng metadata cần thiết.
4. Khi cần đọc, thành phần được cấp quyền yêu cầu mở bọc DEK rồi giải mã dữ liệu theo ngữ cảnh.

Khóa KEK không cần được xuất ra khỏi dịch vụ quản lý khóa trong phương án này. Plaintext DEK có thể xuất hiện trong bộ nhớ của ứng dụng nếu ứng dụng tự thực hiện mã hóa dữ liệu; yêu cầu phải thừa nhận và kiểm soát điểm đó.

Đơn vị sử dụng DEK là một quyết định kiến trúc. Một DEK dùng chung cho rất nhiều bản ghi có vận hành đơn giản hơn nhưng phạm vi tác động khi lộ khóa và yêu cầu quản lý nonce cũng lớn hơn. DEK theo tenant, nhóm dữ liệu hoặc bản ghi tạo ra những chi phí và khả năng cô lập khác nhau. Không mặc định rằng mọi hệ thống phải có một khóa cho mỗi trường.

Khóa và ciphertext phải có ranh giới truy cập khác nhau. Nếu cùng một bản dump chứa ciphertext và plaintext DEK, việc đổi tên cột khóa không tạo thêm bảo vệ.

## 6. Đặc tả mã hóa có xác thực và quy tắc nonce

### 6.1. Chọn một bộ cấu hình được phê duyệt

Mã hóa trường cần bảo vệ cả tính bí mật và khả năng phát hiện dữ liệu bị sửa. Một lựa chọn phù hợp trong nhiều thiết kế là thuật toán mã hóa có xác thực với dữ liệu bổ sung, gọi là AEAD.

Ví dụ cấu hình dự án có thể chốt:

```text
suite: AES-256-GCM
nonceLength: 12 byte
authenticationTagLength: 16 byte
plaintextEncoding: UTF-8
```

Đây là một cấu hình minh họa, không phải yêu cầu phổ quát cho mọi sản phẩm. Dự án phải chốt thư viện, provider, định dạng và phiên bản giao thức tương ứng. Không tự xây thuật toán mật mã hoặc giao thức ghép nhiều primitive khi thư viện đã cung cấp cơ chế đã được thẩm định.

Không dùng AES-ECB cho trường dữ liệu. Không dùng một chế độ chỉ mã hóa mà bỏ qua cơ chế xác thực toàn vẹn rồi vẫn tuyên bố phát hiện được mọi chỉnh sửa.

### 6.2. Nonce phải được quản lý theo khóa thực tế

Với AES-GCM, không được tái sử dụng cùng nonce cho các lần mã hóa khác nhau dưới cùng một khóa. Nonce không cần bí mật, nhưng quy tắc không lặp lại là yêu cầu an toàn cốt lõi.

Nếu dùng nonce ngẫu nhiên 96 bit, phải sinh bằng nguồn ngẫu nhiên mật mã phù hợp. Tính ngẫu nhiên không bảo đảm tuyệt đối không va chạm; cần giới hạn số lần sử dụng mỗi khóa theo đánh giá của bộ cấu hình và quy mô hệ thống.

Yêu cầu vận hành cần tính đến:

- Nhiều instance cùng dùng một DEK.
- Retry, ghi lại bản ghi và migration.
- Khởi động lại tiến trình, restore snapshot và nhân bản môi trường.
- Số lần gọi mã hóa trong toàn bộ vòng đời khóa.
- Khả năng theo dõi và xoay khóa trước khi vượt ngân sách sử dụng.

Nếu dùng bộ đếm để cấp nonce, phải giải quyết tính duy nhất giữa các instance và việc khôi phục trạng thái. Một bộ đếm trong bộ nhớ bị reset khi restart không đủ.

Khi sửa giá trị hoặc cần mã hóa lại với AAD khác, tạo nonce mới theo cơ chế đã chọn. Không lấy ID bản ghi làm nonce trực tiếp chỉ vì ID là duy nhất: cùng bản ghi có thể được mã hóa nhiều lần dưới cùng khóa.

## 7. Ràng buộc ciphertext với đúng ngữ cảnh bằng AAD

**AAD**, viết tắt của Additional Authenticated Data, được xác thực cùng ciphertext nhưng không được mã hóa bởi thao tác AEAD. Nó hữu ích để ràng buộc dữ liệu với ngữ cảnh nghiệp vụ.

Ví dụ ngữ cảnh cho một trường:

```text
applicationDomain = customer-profile
payloadVersion    = 1
dataSchemaVersion = 3
tenantId          = tenant-a
recordId          = customer-1042
fieldName         = personalIdentifier
```

Dịch vụ phải dựng AAD từ ngữ cảnh đáng tin: tenant đã được xác thực, ID bản ghi đang truy cập và tên trường do code kiểm soát. Không lấy toàn bộ AAD do client hoặc chính envelope trong database khai báo rồi mặc nhiên tin rằng nó mô tả đúng đối tượng cần đọc.

Nếu ciphertext của khách hàng A bị chép sang khách hàng B, dịch vụ giải mã tại B phải dùng AAD của B. Tag phải không hợp lệ vì ngữ cảnh đã thay đổi.

### 7.1. Biểu diễn AAD phải không nhập nhằng

Phép nối chuỗi đơn giản có thể tạo nhiều bộ giá trị khác nhau cho cùng dãy byte. Cần một encoding chuẩn tắc: chẳng hạn định dạng có thứ tự field cố định và độ dài từng thành phần.

Các bên mã hóa và giải mã phải thống nhất kiểu dữ liệu, encoding, thứ tự, giá trị mặc định và phiên bản. Không phụ thuộc vào thứ tự key tùy ý của JSON hoặc biểu diễn ngày giờ theo locale.

Nếu đổi tenant, đổi ID hoặc đổi tên trường là nghiệp vụ được phép, phải có luồng giải mã trong ngữ cảnh cũ rồi mã hóa lại theo ngữ cảnh mới. Không thể chỉ sao chép ciphertext sang vị trí mới và mong nó vẫn hợp lệ.

### 7.2. AAD không tự thực hiện phân quyền hoặc chống rollback

AAD gắn dữ liệu với ngữ cảnh; nó không quyết định caller có quyền xem dữ liệu trong ngữ cảnh đó hay không. Phân quyền vẫn phải được kiểm tra trước khi giải mã.

Một ciphertext cũ hợp lệ với cùng AAD vẫn có thể được xác thực thành công. Nếu rủi ro gồm rollback bởi người có quyền sửa database, cần thêm cơ chế kiểm chứng phiên bản mới nhất từ trạng thái đáng tin.

Chỉ thêm số phiên bản vào cùng bản ghi chưa đủ nếu kẻ tấn công có thể khôi phục đồng thời ciphertext và số phiên bản cũ. Nguồn xác định tính mới nhất phải được thiết kế theo khả năng tấn công này.

AAD có thể được lưu hoặc nhìn thấy ở dạng metadata. Không đặt secret hay dữ liệu cá nhân đầy đủ vào AAD rồi coi chúng đã được che giấu.

## 8. Định dạng lưu trữ cần có phiên bản và giới hạn

Một envelope minh họa:

```json
{
  "version": 1,
  "suite": "AES-256-GCM",
  "dataSchemaVersion": 3,
  "keyRef": "profile-kek-generation-7",
  "wrappedDek": "<base64 của DEK đã bọc>",
  "nonce": "<base64 của nonce 12 byte>",
  "ciphertextAndTag": "<base64 của ciphertext kèm tag>"
}
```

Các giá trị trong dấu ngoặc nhọn là mô tả, không phải ciphertext dùng để chạy thử. Đây là một định dạng thiết kế minh họa.

Yêu cầu parser và crypto adapter cần nêu rõ:

- Chỉ chấp nhận version và suite nằm trong tập hỗ trợ do server kiểm soát.
- Giới hạn kích thước envelope và các field trước khi cấp phát lớn hoặc gọi dịch vụ khóa.
- Kiểm tra biểu diễn Base64, độ dài nonce và độ dài tối thiểu của ciphertext kèm tag.
- Chỉ định tuyến keyRef vào tập khóa được workload, môi trường và mục đích cho phép.
- Không dùng keyRef từ bản ghi làm URL tùy ý hoặc lệnh gọi một dịch vụ bên ngoài.
- Dựng lại ngữ cảnh kỳ vọng; kiểm tra tag và chỉ trả plaintext khi toàn bộ thao tác xác thực thành công.
- Có chính sách đọc dữ liệu phiên bản cũ và từ chối phiên bản không còn được hỗ trợ.

Những metadata ảnh hưởng cách diễn giải dữ liệu, như phiên bản giao thức và schema, phải được ràng buộc bằng thiết kế xác thực phù hợp. Không để một field do người sửa database kiểm soát tự chọn nhánh giải mã yếu hơn.

Cơ chế bọc DEK phải bảo vệ tính toàn vẹn của khóa được bọc và sử dụng ngữ cảnh phù hợp nếu dịch vụ khóa hỗ trợ. Metadata cần thay đổi khi rewrap phải được phân biệt với ngữ cảnh bất biến của ciphertext dữ liệu. Nếu thiết kế đưa metadata đó vào AAD dữ liệu, việc thay đổi nó có thể đòi hỏi mã hóa lại dữ liệu.

Không log toàn bộ envelope như cách thay thế cho việc tránh log plaintext. Ciphertext, keyRef và metadata cũng là dữ liệu cần quản lý truy cập, thời hạn lưu và mức độ liên kết.

## 9. Luồng ghi, đọc và xử lý lỗi

### 9.1. Luồng ghi

1. Xác thực caller và kiểm tra quyền sửa đối tượng cùng trường nhạy cảm.
2. Kiểm tra kiểu, độ dài và các quy tắc nghiệp vụ trên đầu vào.
3. Xác định tenant, ID bản ghi và phiên bản schema từ nguồn đáng tin.
4. Chọn DEK hoặc tạo DEK theo đơn vị đã chốt; chọn bộ cấu hình từ chính sách server.
5. Cấp nonce và dựng AAD chuẩn tắc.
6. Mã hóa bằng thư viện; tạo envelope theo định dạng được quản lý phiên bản.
7. Ghi ciphertext, metadata và chỉ mục dẫn xuất được phép trong một cơ chế nhất quán.
8. Phát event hoặc ghi audit với dữ liệu tối thiểu; không đưa plaintext vào outbox.

Nếu ID bản ghi do database cấp, cần thiết kế cách có ID ổn định trước khi tạo AAD hoặc dùng định danh bất biến khác. Không tùy tiện bỏ recordId khỏi ràng buộc chỉ vì luồng ghi chưa thuận tiện.

Nếu mã hóa hoặc bọc khóa thất bại, thao tác ghi trường phải thất bại theo hợp đồng. Không tự động chuyển sang cột plaintext dự phòng.

### 9.2. Luồng đọc

1. Xác thực caller và kiểm tra quyền trên đối tượng, trường, tenant và mục đích.
2. Đọc ciphertext, kiểm tra cấu trúc và lựa chọn khóa trong chính sách cho phép.
3. Dựng AAD từ ngữ cảnh truy cập hiện tại.
4. Mở bọc DEK hoặc sử dụng cơ chế được phép của dịch vụ quản lý khóa.
5. Giải mã và xác thực toàn bộ; nếu thất bại, không trả plaintext.
6. Chỉ trả dạng dữ liệu mà caller được cấp quyền: đầy đủ, đã che hoặc không có trường.
7. Ghi sự kiện truy cập nhạy cảm theo yêu cầu audit của chức năng.

Đường đọc qua batch, export, công cụ hỗ trợ và job nền phải chịu kiểm soát tương đương. Chỉ bảo vệ API giao diện người dùng không ngăn một job được cấp quyền quá rộng xuất toàn bộ dữ liệu.

### 9.3. Hợp đồng lỗi

| Tình huống | Hành vi cần đặc tả |
|---|---|
| Caller không có quyền | Từ chối trước giải mã; không gọi đường mở khóa cho trường đó |
| Tag không hợp lệ hoặc AAD không khớp | Không trả plaintext; ghi nhận lỗi toàn vẹn có metadata tối thiểu |
| Không nhận diện version hoặc suite | Từ chối theo chính sách; không thử đoán hoặc tự hạ cấp |
| Dịch vụ khóa timeout | Áp dụng timeout, retry có giới hạn và hợp đồng lỗi đã chọn |
| Khóa bị vô hiệu hóa | Ngừng đường đọc cần khóa; thông báo vận hành theo cơ chế quy định |
| Envelope sai cấu trúc | Từ chối có kiểm soát, không làm lộ stack trace hoặc vật liệu khóa |

Cần phân biệt lỗi toàn vẹn với dữ liệu thực sự vắng mặt. Trả chuỗi rỗng khi giải mã thất bại có thể khiến nghiệp vụ ghi đè dữ liệu hoặc đưa ra quyết định sai.

Thông báo ra ngoài không nên cung cấp chi tiết giúp dò dữ liệu hoặc nội bộ khóa. Hệ thống quan sát bên trong vẫn phải phân loại đủ để xử lý nguyên nhân mà không ghi plaintext.

## 10. Ví dụ Java tại ranh giới AEAD

Đoạn sau minh họa thao tác AES-GCM bằng API mật mã của Java. Nó giả định DEK hợp lệ, nonce được cấp đúng chính sách và AAD đã được dựng từ ngữ cảnh đáng tin.

```java
// Imports cần thiết:
// javax.crypto.Cipher
// javax.crypto.SecretKey
// javax.crypto.spec.GCMParameterSpec

// Đầu vào do lớp dịch vụ cung cấp:
// SecretKey dek;          // khóa AES-256 trong cấu hình minh họa
// byte[] nonce;           // 12 byte, không lặp dưới cùng khóa
// byte[] aad;             // ngữ cảnh chuẩn tắc
// byte[] plaintextUtf8;   // dữ liệu hợp lệ theo hợp đồng

Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
encryptor.init(Cipher.ENCRYPT_MODE, dek, new GCMParameterSpec(128, nonce));
encryptor.updateAAD(aad);
byte[] ciphertextAndTag = encryptor.doFinal(plaintextUtf8);

// Ở đường đọc: nonce lấy từ envelope đã kiểm tra;
// aad được dựng lại từ ngữ cảnh kỳ vọng của bản ghi.
Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
decryptor.init(Cipher.DECRYPT_MODE, dek, new GCMParameterSpec(128, nonce));
decryptor.updateAAD(aad);
byte[] verifiedPlaintext = decryptor.doFinal(ciphertextAndTag);

// Chỉ sử dụng verifiedPlaintext sau khi doFinal hoàn tất thành công.
```

Trong GCMParameterSpec, số 128 là độ dài tag tính bằng bit, tương ứng 16 byte. Với cách sử dụng này, kết quả mã hóa do provider trả về chứa ciphertext kèm tag; định dạng lưu trữ phải thống nhất cách biểu diễn này.

Nếu tag không hợp lệ, đường giải mã phải xử lý lỗi xác thực và không có fallback dùng dữ liệu chưa được xác thực. Không dùng kết quả trung gian của một luồng giải mã trước khi kiểm tra tag hoàn tất.

Đoạn code không thực hiện phân quyền, tạo nonce, quản lý khóa, encode AAD, versioning hay audit. Những phần đó thuộc thiết kế dịch vụ và phải có kiểm thử riêng. Nó cũng không phải một lớp tiện ích đầy đủ để sao chép vào production.

Plaintext DEK và plaintext dữ liệu có thể xuất hiện trong bộ nhớ. Với Java, không được hứa rằng xóa một biến String hoặc gán null bảo đảm xóa sạch mọi bản sao trong bộ nhớ. Cần giảm việc tạo bản sao, giới hạn thời gian giữ dữ liệu, kiểm soát heap dump, core dump và quyền chẩn đoán theo rủi ro.

## 11. Tìm kiếm, chỉ mục và thông tin vẫn có thể lộ

### 11.1. Không hy sinh mục tiêu bảo vệ để giữ nguyên truy vấn

Mã hóa ngẫu nhiên khiến hai giá trị bằng nhau thường có ciphertext khác nhau. Vì vậy, không thể kỳ vọng mọi truy vấn equality, prefix, range, sort hoặc full-text cũ tiếp tục hoạt động trên ciphertext.

Nếu giải pháp là thêm một cột plaintext để tìm kiếm, phải đánh giá lại mục tiêu. Dữ liệu không còn được bảo vệ trước tài khoản đọc database theo yêu cầu ban đầu.

Các lựa chọn có thể gồm giảm chức năng tìm kiếm, dùng một dịch vụ tìm kiếm có ranh giới được kiểm soát, tokenization hoặc chỉ mục dẫn xuất được thiết kế cho một nhu cầu cụ thể.

### 11.2. Chỉ mục tìm chính xác có khóa

Một blind index cho equality có thể sử dụng MAC có khóa trên biểu diễn chuẩn tắc của giá trị, kèm domain và tenant phù hợp. Ví dụ ở mức thiết kế:

```text
indexInput = canonicalEncode(
    purpose = personal-identifier-exact-match,
    tenantId,
    normalizedValue,
    indexVersion
)

searchToken = HMAC(indexKey, indexInput)
```

Không thay phép encode chuẩn tắc bằng phép nối chuỗi nhập nhằng. Không dùng cùng khóa thô cho mã hóa dữ liệu và tạo chỉ mục. Khóa chỉ mục phải có mục đích, quyền truy cập và vòng đời được đặc tả riêng; nếu dùng dẫn xuất khóa, cần cơ chế được phê duyệt.

Hash không khóa của dữ liệu có miền giá trị nhỏ có thể bị dò bằng tập ứng viên. HMAC có khóa tránh cho bên chỉ giữ database tự tính token cho mọi ứng viên khi họ không có khóa, nhưng không xóa mọi rủi ro:

- Token có thể bộc lộ quan hệ bằng nhau trong cùng phạm vi thiết kế.
- Tần suất và mối liên kết giữa các bản ghi có thể vẫn lộ.
- API tìm kiếm bị lạm dụng có thể trở thành đường kiểm tra ứng viên.
- Khóa chỉ mục bị lộ cho phép tính lại token của các giá trị có thể đoán.
- Chuẩn hóa sai có thể làm nhiều giá trị nghiệp vụ khác nhau có cùng token đầu vào.

Sau khi tìm ứng viên, dịch vụ vẫn kiểm tra quyền, giải mã và xác minh giá trị theo hợp đồng. Cần quyết định rõ hành vi khi có nhiều ứng viên hoặc khi chỉ mục và ciphertext chưa nhất quán.

Chuẩn hóa là quyết định nghiệp vụ theo từng loại dữ liệu. Ví dụ không áp dụng quy tắc bỏ dấu hoặc chuyển chữ thường cho mọi giá trị chỉ vì tiện tìm kiếm.

### 11.3. Độ dài và metadata

Mã hóa trường không tự che độ dài, thời điểm cập nhật, trường có tồn tại hay không, số bản ghi hoặc quan hệ equality do chỉ mục tạo ra. Nếu những đặc điểm đó nhạy cảm trong mô hình đe dọa, cần đánh giá thêm cơ chế phù hợp, chẳng hạn padding được thiết kế rõ ràng.

Không tự đặt padding tùy ý rồi coi đó là giải pháp đầy đủ. Nó có chi phí, quy tắc giải mã và giới hạn riêng cần được kiểm chứng.

## 12. Vòng đời khóa, xoay khóa và migration

### 12.1. Phân biệt rewrap với mã hóa lại dữ liệu

| Thao tác | Thành phần thay đổi | Điều không được mặc nhiên kết luận |
|---|---|---|
| Đổi KEK và rewrap DEK | Lớp bảo vệ DEK và metadata tương ứng | Ciphertext dữ liệu chưa chắc đã đổi |
| Đổi DEK và mã hóa lại trường | Khóa dữ liệu, nonce và ciphertext | Mọi backup cũ chưa chắc đã được xử lý |
| Đổi khóa chỉ mục | Search token và phiên bản chỉ mục | Luồng tìm kiếm cũ chưa chắc còn dùng được |
| Đổi suite hoặc phiên bản AAD | Giao thức đọc ghi và có thể toàn bộ ciphertext | Reader cũ chưa chắc hiểu dữ liệu mới |

Rewrap có thể không đòi hỏi giải mã rồi mã hóa lại toàn bộ trường nếu thiết kế envelope và dịch vụ khóa cho phép. Tuy nhiên, phải xác minh tính tương thích của ngữ cảnh xác thực và chính sách keyRef thay vì giả định mọi metadata đều có thể đổi độc lập.

### 12.2. Trạng thái khóa và chính sách quyền

Cần phân biệt khả năng được dùng để tạo dữ liệu mới, khả năng được dùng để giải mã dữ liệu lịch sử, trạng thái vô hiệu hóa và trạng thái đã hủy. Các trạng thái cụ thể phụ thuộc nền tảng, nhưng hợp đồng ứng dụng phải rõ.

Dịch vụ ghi chỉ dùng khóa hoặc thế hệ khóa đang được phép mã hóa. Dịch vụ đọc có thể cần một tập phiên bản lịch sử trong khoảng chuyển tiếp được giới hạn. Không thử mọi khóa trong hệ thống để đoán khóa nào đọc được dữ liệu.

Tách vai trò quản trị vòng đời khóa và quyền đọc dữ liệu là một kiểm soát hữu ích. Cần đánh giá cả khả năng thay đổi chính sách để tự cấp quyền; chỉ tách tên hai role không chứng minh đã ngăn được việc tự nâng quyền.

Cache DEK trong bộ nhớ có thể giảm độ trễ nhưng ảnh hưởng phản ứng khi thu hồi quyền hoặc vô hiệu hóa khóa. Phải quy định TTL, giới hạn dung lượng, quyền tiến trình và thời gian tối đa plaintext DEK có thể còn được sử dụng sau một sự kiện thu hồi.

### 12.3. Migration dữ liệu đang ở dạng rõ

Một kế hoạch chuyển đổi có thể gồm:

1. Chốt schema, version, parser và đường đọc tương thích trong thời gian chuyển tiếp.
2. Thay đổi đường ghi để không tạo thêm bản ghi plaintext ngoài chính sách chuyển đổi.
3. Mã hóa dữ liệu cũ theo lô, có checkpoint và kiểm soát quyền.
4. Kiểm tra số lượng, lỗi, ngữ cảnh AAD và khả năng đọc lại trên dữ liệu thử.
5. Xử lý chỉ mục, CDC, bản sao, bảng lịch sử, file tạm và backup theo phạm vi đã chốt.
6. Loại bỏ đường đọc plaintext sau khi đáp ứng điều kiện hoàn tất.
7. Giảm hoặc gỡ quyền migration sau khi kết thúc.

Nếu tạm thời tồn tại hai dạng dữ liệu, phải có thời hạn và tiêu chí kết thúc cụ thể. Một cột plaintext “để rollback” không được tồn tại vô thời hạn mà không được ghi nhận là rủi ro còn mở.

Migration cần idempotent theo thiết kế. Không mã hóa lặp ciphertext như thể nó là plaintext do không kiểm tra trạng thái bản ghi.

## 13. Logging, sao lưu, phục hồi và xóa dữ liệu

### 13.1. Quan sát mà không làm lộ nội dung

Audit có thể cần ghi actor hoặc workload, loại hành động, mã mục đích, đối tượng tham chiếu, quyết định quyền, thế hệ khóa và mã kết quả. Mỗi field trong audit phải được đánh giá về mức độ nhạy cảm và thời hạn lưu.

Không ghi plaintext, plaintext DEK, thông tin xác thực hoặc toàn bộ request chứa dữ liệu nhạy cảm. Cũng phải rà đường exception, tracing, APM, dead-letter queue, cache và file debug thuộc phạm vi chức năng.

Một sự kiện “giải mã thành công” không chứng minh người dùng đã nhìn thấy dữ liệu; một sự kiện “request thành công” không chứng minh không có đường giải mã ngoài quyền. Yêu cầu audit phải nói rõ sự kiện nào đại diện cho thao tác nào.

### 13.2. Backup phải đi cùng khả năng phục hồi khóa

Backup database có ciphertext không đủ để phục hồi nếu khóa cần thiết đã mất. Ngược lại, backup chứa cả plaintext DEK và dữ liệu làm mất ý nghĩa tách ranh giới.

Kế hoạch phục hồi phải chỉ ra:

- Các thế hệ khóa cần để đọc dữ liệu tại mỗi mốc backup được giữ.
- Quyền và thủ tục cấp quyền cho môi trường khôi phục.
- Cách kiểm tra tính toàn vẹn và đối chiếu ngữ cảnh AAD.
- Cách bảo vệ dữ liệu khi diễn tập ngoài môi trường chính.
- Điều kiện đo RTO và RPO cho luồng có mã hóa.
- Việc giới hạn lại quyền và xử lý bản phục hồi sau diễn tập.

Một bài diễn tập có giá trị phải đọc được mẫu dữ liệu đã mã hóa từ các thế hệ khóa thuộc phạm vi giữ lại, bằng danh tính được cấp quyền. Đồng thời, danh tính chỉ đọc bản backup phải không có đường tự lấy plaintext.

### 13.3. Xóa dữ liệu và giới hạn của crypto-shredding

Hủy khóa có thể làm ciphertext không còn giải mã được nếu không còn bản sao khóa hoặc đường khôi phục khác. Điều kiện này phải được xác minh, không suy ra chỉ từ việc một alias đã bị đổi.

Một DEK dùng chung cho nhiều bản ghi không thể bị hủy để xóa riêng một bản ghi mà vẫn giữ khả năng đọc các bản ghi còn lại. Một wrapped DEK đã bị xóa ở database hiện tại có thể vẫn tồn tại trong backup; nếu KEK tương ứng còn dùng được thì dữ liệu lịch sử có thể vẫn đọc được.

Cần phân biệt xóa khỏi hệ thống đang hoạt động, hết thời hạn lưu backup, thu hồi quyền và hủy vật liệu khóa. Không dùng một thao tác để tuyên bố đã hoàn thành mọi loại xóa dữ liệu.

## 14. Bộ yêu cầu bảo mật mẫu

Các mã sau là ví dụ để đưa vào đặc tả. Dự án phải thay tên trường, phạm vi, ngưỡng và môi trường bằng các giá trị đã chốt; không để những quyết định quan trọng ở dạng “sẽ cân nhắc”.

| ID | Yêu cầu có thể kiểm chứng | Bằng chứng nghiệm thu |
|---|---|---|
| SFE-01 | Mọi đường ghi personalIdentifier thuộc phạm vi chỉ lưu envelope đã mã hóa tại database, lịch sử và outbox | Kiểm thử API, import, batch; đối chiếu các nơi lưu bằng marker giả lập |
| SFE-02 | Bộ cấu hình mã hóa và tập version được server cố định theo chính sách; dữ liệu không được tự chọn thuật toán ngoài tập | Kiểm thử suite/version không hỗ trợ và cấu hình triển khai |
| SFE-03 | Nonce không được tái sử dụng dưới cùng DEK; chiến lược cấp và ngân sách sử dụng khóa phải bao phủ nhiều instance, retry và restart | Thiết kế cấp nonce, cấu hình vòng đời khóa và kiểm thử tình huống vận hành |
| SFE-04 | Ciphertext được ràng buộc với domain, tenant, record, field và phiên bản schema đã chọn | Hoán đổi ciphertext giữa các ngữ cảnh phải thất bại xác thực |
| SFE-05 | Caller chỉ được giải mã trường sau khi đáp ứng quyền trên đối tượng và trường, cùng điều kiện mục đích nếu có | Ma trận role/tenant/mục đích; xác minh không gọi mở khóa khi bị từ chối |
| SFE-06 | Tag sai, AAD sai và envelope sai không được tạo plaintext đầu ra hay fallback sang lưu rõ | Ca làm hỏng từng thành phần; kiểm tra response, DB và event |
| SFE-07 | Plaintext DEK không được lưu bền trong database, file cấu hình hoặc artifact vận hành thuộc phạm vi | Rà cấu hình, luồng bọc khóa và các nơi lưu đã liệt kê |
| SFE-08 | KeyRef chỉ được ánh xạ tới tập khóa và môi trường được phép; caller không tự chỉ định khóa ngoài phạm vi | Ca keyRef không hợp lệ, khóa tenant khác và khóa môi trường khác |
| SFE-09 | Log, trace, lỗi, cache bền và dead-letter queue thuộc phạm vi không chứa plaintext của trường | Kiểm tra các kênh bằng marker tổng hợp và đối chiếu đường lỗi |
| SFE-10 | Tìm kiếm chỉ dùng cơ chế dẫn xuất đã phê duyệt với chính sách rò rỉ được chấp nhận | Thiết kế chỉ mục, phân quyền tìm kiếm và kiểm tra không tồn tại bản rõ phụ |
| SFE-11 | Xoay khóa không tạo dữ liệu mới bằng thế hệ đã ngừng ghi; dữ liệu lịch sử được đọc theo chính sách | Kiểm thử ghi/đọc qua các thế hệ và báo cáo migration |
| SFE-12 | Khi dịch vụ khóa lỗi, timeout hoặc bị thu hồi quyền, hệ thống giữ hợp đồng lỗi và không lưu hay trả plaintext trái phép | Fault injection; kiểm tra database, queue, response và telemetry |
| SFE-13 | Backup trong thời hạn giữ lại có đường phục hồi dữ liệu và khóa tương ứng được kiểm soát | Diễn tập restore với dữ liệu nhiều thế hệ khóa và đo RTO/RPO |
| SFE-14 | Thu hồi quyền, cache khóa và hủy khóa có thời hạn hiệu lực và điều kiện quan sát được | Kiểm thử cache/TTL, danh tính bị thu hồi và khả năng truy cập sau thay đổi |
| SFE-15 | Kết thúc migration đồng nghĩa không còn đường plaintext hoạt động ngoài ngoại lệ được ghi nhận | Báo cáo phạm vi chuyển đổi, đường đọc ghi và bản sao còn giữ |
| SFE-16 | Giới hạn dung lượng, thời gian gọi khóa và chi phí vận hành được xác định trước nghiệm thu | Kiểm thử kích thước biên, tải và lỗi trong môi trường đã chốt |

Ví dụ cụ thể hóa SFE-12:

> Khi không mở bọc được DEK trong giới hạn timeout của dịch vụ, API cập nhật hồ sơ trả lỗi theo hợp đồng và không commit thay đổi personalIdentifier, không tạo event chứa plaintext. Trường không liên quan chỉ được cập nhật riêng nếu hợp đồng giao dịch cho phép và ca thử tương ứng đã được xác định.

Ví dụ cụ thể hóa hiệu năng cho một dự án: ở 200 request/giây, dữ liệu giả lập có kích thước đã chốt và trạng thái cache được ghi rõ, p95 độ trễ tăng thêm của đường đọc trường không vượt 25 ms trong kịch bản cache-hit. Cache-miss, timeout và xoay khóa có kịch bản cùng ngưỡng riêng. Các con số này chỉ minh họa cách đặt yêu cầu đo được, không phải ngưỡng an toàn mật mã hoặc cam kết cho mọi kiến trúc.

## 15. Ma trận kiểm thử theo rủi ro và tiêu chí kết luận

| Nhóm ca | Thao tác | Kết quả mong đợi |
|---|---|---|
| Luồng đúng | Mã hóa rồi đọc lại dữ liệu tổng hợp hợp lệ | Giá trị nghiệp vụ khôi phục đúng trong ngữ cảnh được phép |
| Ngẫu nhiên hóa | Mã hóa cùng giá trị nhiều lần với nonce được cấp mới | Giải mã đúng; dữ liệu thử không cho thấy nonce bị tái sử dụng |
| Toàn vẹn | Sửa byte trong ciphertext hoặc tag | Giải mã thất bại; không trả plaintext |
| Sai khóa | Dùng DEK khác trong kiểm thử cô lập | Xác thực thất bại, không có fallback |
| Sai ngữ cảnh | Hoán đổi ciphertext giữa tenant, record hoặc field | Không giải mã thành công tại vị trí đích |
| Phân quyền | Caller cùng tenant nhưng thiếu quyền xem trường | Từ chối trước đường giải mã |
| Phân quyền tenant | Caller tenant A yêu cầu dữ liệu tenant B | Không trả dữ liệu; không mở khóa để phục vụ yêu cầu đó |
| Version | Dùng suite/version ngoài tập và metadata không hợp lệ | Từ chối có kiểm soát |
| Biên dữ liệu | Null, rỗng, Unicode, kích thước tối đa và vượt giới hạn | Đúng hợp đồng; không lỗi tràn cột hoặc cấp phát ngoài giới hạn |
| Lỗi phụ thuộc | Timeout, thiếu quyền hoặc khóa bị vô hiệu hóa | Lỗi theo chính sách; không phát sinh plaintext dự phòng |
| Logging | Kích hoạt cả nhánh thành công và nhánh lỗi bằng marker | Marker plaintext không có trong các kênh bị cấm |
| Xoay khóa | Đọc dữ liệu cũ, ghi dữ liệu mới và chạy migration | Đúng tập khóa được phép, không mất khả năng đọc trong phạm vi hỗ trợ |
| Backup | Restore dữ liệu thuộc nhiều thế hệ khóa | Đọc đúng bằng danh tính hợp lệ; danh tính đọc DB đơn thuần bị giới hạn |
| Tìm kiếm | Tìm bằng token và kiểm tra quyền với các ứng viên | Đúng ngữ nghĩa, đúng tenant và không dùng bản rõ phụ |
| Thu hồi | Giải mã trước và sau thu hồi, bao gồm cache còn nóng | Thời gian hiệu lực đúng chính sách đã đo |

Một test “encrypt rồi decrypt trả đúng” chỉ kiểm tra một phần rất nhỏ. Cần kiểm tra tag, AAD, phân quyền, parser, phiên bản, đường lỗi và vận hành.

Tương tự, lấy mẫu nhiều nonce không trùng không chứng minh toán học rằng cơ chế luôn không trùng. Cần đánh giá thiết kế cấp nonce, phạm vi dùng khóa và giới hạn vận hành. Kiểm thử hỗ trợ phát hiện lỗi triển khai, không thay thế phân tích rủi ro va chạm.

Với kiểm tra không có plaintext trong storage hoặc log, phải mô tả nguồn và nhánh đã quan sát. Không tìm thấy một marker trong một file log không chứng minh toàn bộ hệ thống không lưu plaintext ở bất kỳ đâu.

Chỉ kết luận PASS khi ca đã đi tới điểm cần kiểm chứng và thu đủ bằng chứng. Nếu không quan sát được nhánh lỗi, dịch vụ khóa chưa sẵn sàng hoặc restore chưa chạy, kết quả phải thể hiện chưa kiểm thử hoặc chưa đủ bằng chứng.

## 16. Case study: hồ sơ khách hàng nhiều tenant

Một nền tảng có ba nhóm người dùng:

- Nhân viên hỗ trợ cần xem tên và mã định danh đã che.
- Nhân viên xác minh cần xem đầy đủ mã định danh của hồ sơ được giao.
- Nhóm báo cáo chỉ cần thống kê số hồ sơ theo trạng thái.

Rủi ro chính là tài khoản báo cáo đọc toàn bộ database, nhân viên hỗ trợ sử dụng API để xem giá trị đầy đủ và ciphertext bị chuyển giữa hai tenant.

### 16.1. Quyết định thiết kế

Database lưu envelope cho personalIdentifier. Tài khoản báo cáo không có quyền sử dụng khóa hoặc gọi đường giải mã. Luồng hỗ trợ nhận dữ liệu đã che theo thiết kế; không cấp quyền giải mã hàng loạt chỉ để tạo màn hình danh sách.

Nếu dữ liệu đã che được lưu riêng, phải đưa nó vào danh mục dữ liệu và đánh giá lượng thông tin lộ. Mã hóa trường đầy đủ không làm phần được lưu riêng trở nên không nhạy cảm.

Dịch vụ xác minh kiểm tra vai trò, phạm vi hồ sơ được giao và tenant trước khi giải mã. AAD ràng buộc ciphertext với tenant, hồ sơ và tên trường. Audit ghi nhận thao tác xem đầy đủ với mã mục đích và tham chiếu hồ sơ được kiểm soát.

Nhu cầu tìm chính xác được giải quyết bằng chỉ mục có khóa riêng sau khi đánh giá leakage. Báo cáo thống kê sử dụng dữ liệu tối thiểu cần thiết, không mặc định đi qua đường giải mã.

### 16.2. Truy vết mục tiêu, thiết kế và test

| Rủi ro | Yêu cầu | Thành phần thực hiện | Ca nghiệm thu |
|---|---|---|---|
| Dump database lộ mã định danh | SFE-01, SFE-07, SFE-09 | Bộ mã hóa, quản lý khóa và các luồng lưu | Kiểm tra dump và kênh lưu bằng dữ liệu tổng hợp |
| Hỗ trợ xem giá trị đầy đủ | SFE-05 | Policy truy cập trường và API response | Caller hỗ trợ bị từ chối đường xem đầy đủ trước giải mã |
| Sao chép ciphertext sang tenant khác | SFE-04, SFE-06 | AAD builder và AEAD adapter | Hoán đổi ciphertext; xác thực thất bại |
| Sự cố khóa làm mất dữ liệu | SFE-11, SFE-13 | Quy trình khóa và phục hồi | Restore bản dữ liệu trước xoay khóa bằng danh tính được phép |
| Tìm kiếm tạo bản rõ phụ | SFE-10 | Dịch vụ chỉ mục và truy vấn | Kiểm tra storage, token, quyền tìm và đối chiếu ứng viên |

Kiến trúc chỉ đạt mục tiêu đã nêu khi các đường sử dụng dữ liệu tương ứng được kiểm chứng. Nếu một công cụ hỗ trợ nội bộ vẫn xuất plaintext không qua policy, ranh giới bảo vệ còn thiếu dù primitive mã hóa hoạt động đúng.

## 17. Bài tập đặc tả

Một hệ thống nhân sự cần lưu thông tin tài khoản nhận lương và số giấy tờ định danh. Nhóm kế toán cần xuất thông tin nhận lương, nhóm hỗ trợ chỉ cần bốn ký tự cuối và tác vụ đồng bộ chạy ban đêm đang ghi toàn bộ request vào log.

Hãy hoàn thành các công việc sau:

1. Viết hai mục tiêu bảo vệ, chỉ rõ khả năng của bên tấn công và giới hạn bảo vệ.
2. Lập danh mục các bản sao dữ liệu, bao gồm log, queue, file xuất và backup.
3. Chọn đơn vị sử dụng DEK; giải thích phạm vi tác động và chi phí vận hành.
4. Định nghĩa AAD, encoding chuẩn tắc và luồng khi bản ghi chuyển tenant.
5. Viết yêu cầu phân quyền giải mã cho hỗ trợ, kế toán và job nền.
6. Chốt chính sách tìm kiếm và thông tin dẫn xuất chấp nhận để lộ.
7. Viết hợp đồng khi dịch vụ khóa timeout, tag sai và khóa bị vô hiệu hóa.
8. Thiết kế migration không để cột plaintext phụ tồn tại không thời hạn.
9. Chọn ít nhất sáu ca kiểm thử có điểm quan sát và oracle rõ ràng.
10. Mô tả một diễn tập phục hồi cùng điều kiện hủy hoặc thu hồi khóa.

Một đặc tả tốt cho phép nhóm phát triển biết nơi phải đặt kiểm soát, nhóm kiểm thử biết hành vi nào là đúng và nhóm vận hành biết cách xử lý sự cố mà không phá vỡ mục tiêu bảo vệ dữ liệu.

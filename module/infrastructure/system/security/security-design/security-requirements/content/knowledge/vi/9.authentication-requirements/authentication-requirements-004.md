# Mật khẩu và passphrase

## 1. Mục tiêu của yêu cầu về mật khẩu

Trong chương **Yêu cầu xác thực**, mật khẩu cần được xem như một bí mật dùng để chứng minh quyền kiểm soát tài khoản. Đặc tả tốt phải trả lời được: người dùng được tạo bí mật nào, hệ thống xử lý và bảo vệ bí mật đó ra sao, kẻ tấn công được thử bao nhiêu lần, và điều gì xảy ra khi bí mật bị lộ.

Sau bài này, người học có thể chuyển những mục tiêu như “khó chiếm tài khoản” hoặc “không lộ mật khẩu khi mất cơ sở dữ liệu” thành yêu cầu có phạm vi, chủ sở hữu và bằng chứng kiểm thử. Phạm vi bao gồm việc tạo, xác minh, lưu trữ, thay đổi và vô hiệu hóa mật khẩu; các yêu cầu về logging và phục hồi được liên kết vào cùng vòng đời.

**Mật khẩu** là chuỗi bí mật mà người dùng nhập hoặc trình quản lý mật khẩu cung cấp. **Passphrase** là dạng mật khẩu thường gồm nhiều từ, giúp nhập và ghi nhớ chuỗi dài. Máy chủ vẫn nhận một chuỗi và xác minh theo hợp đồng xử lý đã công bố; không cần một thuật toán lưu trữ riêng chỉ vì chuỗi có nhiều từ.

Độ dài không tự chứng minh độ khó đoán. Một câu hát quen thuộc, tên doanh nghiệp kèm năm, hoặc một mẫu lặp có thể dài nhưng dễ nằm trong tập đoán của đối phương. Passphrase hữu ích khi cách chọn các từ tạo ra đủ tính khó đoán, đồng thời hệ thống hỗ trợ nhập đầy đủ chuỗi đó.

Mật khẩu và passphrase đều thuộc yếu tố **điều người dùng biết**. Nhập thêm một câu bí mật không tạo ra yếu tố xác thực độc lập. Hệ thống có thể cần thêm MFA, tức xác thực đa yếu tố, và yêu cầu chống phishing phù hợp với rủi ro.

## 2. Bắt đầu bằng rủi ro, không bắt đầu bằng biểu thức chính quy

Giả sử cần đặc tả một cổng học tập có tài khoản học viên và tài khoản quản trị. Học viên có thể dùng mật khẩu; quản trị bắt buộc dùng MFA và không được bỏ bước MFA sau khi xác minh đúng mật khẩu.

Các mã rủi ro sau là ví dụ do nhóm thiết kế đặt cho tình huống này:

| Mã | Tình huống đe dọa | Tác động cần giảm | Nhóm yêu cầu liên quan |
| --- | --- | --- | --- |
| R-PW-01 | Đoán nhiều mật khẩu cho một tài khoản | Chiếm tài khoản qua giao diện đăng nhập | Độ dài, danh sách chặn, giới hạn thử |
| R-PW-02 | Thử mật khẩu phổ biến trên nhiều tài khoản | Chiếm hàng loạt tài khoản dù mỗi tài khoản chỉ có ít lần sai | Phát hiện theo nhiều tài khoản, MFA |
| R-PW-03 | Thử lại cặp định danh và mật khẩu đã lộ từ dịch vụ khác | Lợi dụng việc dùng lại bí mật | Danh sách chặn, mật khẩu riêng cho từng dịch vụ, MFA |
| R-PW-04 | Đánh cắp bảng thông tin xác thực hoặc bản sao lưu | Đoán mật khẩu ngoại tuyến | Hàm dẫn xuất dành cho mật khẩu, salt, quản lý bản sao lưu |
| R-PW-05 | Lấy lại tài khoản qua luồng quên mật khẩu yếu | Đi vòng qua chính sách đăng nhập | Bằng chứng phục hồi, token, thu hồi phiên |
| R-PW-06 | Gửi đầu vào rất lớn hoặc nhiều phép băm đồng thời | Cạn CPU, RAM hoặc hàng đợi xác thực | Giới hạn đầu vào, số tác vụ đồng thời và hành vi quá tải |
| R-PW-07 | Mật khẩu xuất hiện trong telemetry hoặc công cụ hỗ trợ | Rò rỉ bí mật qua hệ thống vận hành | Kiểm soát log, trace, analytics và quyền truy cập |

Ba kiểu tấn công đầu thường được gọi lần lượt là password guessing, password spraying và credential stuffing. Chúng cần các tín hiệu phát hiện khác nhau; giới hạn theo một địa chỉ IP không bao phủ được mọi trường hợp phân tán. [OWASP Credential Stuffing Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)

Yêu cầu “tài khoản phải có mật khẩu mạnh” không cho biết đội phát triển cần làm gì để xử lý từng rủi ro. Cần tách thành các điều kiện có thể quan sát, chẳng hạn:

> SR-PW-01: Dịch vụ xác thực phải từ chối mật khẩu mới ngắn hơn 15 mã điểm Unicode sau bước chuẩn hóa đã định nghĩa. Quy tắc áp dụng đồng nhất tại đăng ký, đổi mật khẩu và đặt lại mật khẩu, kể cả khi gọi API trực tiếp.

Yêu cầu này chỉ giải quyết một phần rủi ro. Nó chưa thay thế yêu cầu lưu trữ, chống tự động hóa hoặc phục hồi.

## 3. Xác định chính sách và phạm vi áp dụng

NIST SP 800-63B-4 quy định tối thiểu 15 ký tự khi mật khẩu là yếu tố duy nhất; trường hợp chỉ dùng trong MFA có thể cho phép từ 8 ký tự. Tài liệu khuyến nghị hỗ trợ độ dài tối đa ít nhất 64 ký tự. Khi viện dẫn, cần ghi đúng phiên bản và phân biệt quy định bắt buộc với khuyến nghị. [NIST SP 800-63B-4, mục Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver)

Trong tình huống cổng học tập, nhóm chọn chính sách mẫu dưới đây. Các ngưỡng 128 ký tự, thời gian chờ và ngân sách hiệu năng trong bài là **quyết định minh họa của hệ thống**, không phải tập yêu cầu mặc định cho mọi sản phẩm hay tuyên bố tuân thủ toàn bộ NIST.

| Thuộc tính | Quyết định cho tình huống mẫu | Điều kiện nghiệm thu |
| --- | --- | --- |
| Đối tượng | Tài khoản con người có mật khẩu do dịch vụ quản lý | Danh mục luồng xác thực xác định được nơi nào dùng chính sách |
| Độ dài mới | Từ 15 đến 128 mã điểm Unicode sau NFC | 14 bị từ chối; 15 và 128 đi tiếp nếu đạt các điều kiện khác; 129 bị từ chối |
| Loại ký tự | Hỗ trợ chữ Unicode, chữ số, dấu câu và khoảng trắng; không bắt buộc phối hợp các nhóm ký tự | Passphrase tiếng Việt và mật khẩu do trình quản lý sinh được xử lý đầy đủ |
| Phạm vi đầu vào | API chỉ nhận chuỗi Unicode hợp lệ; từ chối U+0000, CR và LF trong trường mật khẩu | Từ chối rõ ràng; không xóa ký tự để biến đầu vào thành chuỗi khác |
| Đầu vào thô | Trường mật khẩu sau giải mã JSON có tối đa 4.096 byte UTF-8 trước NFC | Vượt giới hạn bị từ chối trước tác vụ KDF; không cắt chuỗi |
| Dùng lại bí mật đã biết | Mật khẩu mới phải qua danh sách chặn tại máy chủ | API không tạo được credential nếu kết quả kiểm tra là bị chặn |
| Thời điểm thay đổi | Không ép đổi chỉ vì qua một số ngày cố định; xử lý riêng khi có bằng chứng lộ | Bộ kiểm thử có kịch bản hết thời gian và kịch bản credential bị đánh dấu lộ |
| Hỗ trợ công cụ | Cho phép dán và tự điền từ trình quản lý mật khẩu | Dán và tự điền không làm đổi giá trị bí mật |
| Tài khoản quản trị | Vẫn dùng tối thiểu 15 ký tự và bắt buộc MFA | Đúng mật khẩu nhưng thiếu yếu tố tiếp theo không được cấp phiên quản trị |

Các ngoại lệ ký tự điều khiển trong bảng là hợp đồng đầu vào của ví dụ, cần có lý do tương thích cụ thể. Không được mở rộng thành việc cấm dấu tiếng Việt, khoảng trắng hoặc dấu câu chỉ vì bộ kiểm tra hiện có khó xử lý.

Nhóm chọn cùng một ngưỡng 15 cho học viên và quản trị để giảm số nhánh chính sách. Nếu một thiết kế khác hạ ngưỡng chỉ cho tài khoản có MFA, yêu cầu phải giải quyết cả việc tắt MFA, mất yếu tố thứ hai và đăng nhập qua đường dự phòng. Một mật khẩu ngắn không được tiếp tục dùng như yếu tố duy nhất sau khi điều kiện bảo vệ ban đầu đã mất.

NIST cũng yêu cầu kiểm tra toàn bộ mật khẩu, không áp đặt quy tắc phối hợp nhóm ký tự, và không đổi định kỳ nếu không có bằng chứng bị xâm phạm. [NIST SP 800-63B-4, mục Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver)

## 4. Đặc tả chuỗi đầu vào: ký tự, byte và Unicode

Một yêu cầu “tối đa 128 ký tự” vẫn mơ hồ nếu các thành phần đếm khác nhau. Byte UTF-8, mã điểm Unicode và ký tự mà mắt nhìn thấy không luôn có quan hệ một-một. Một emoji có thể gồm nhiều mã điểm; chữ có dấu có thể có dạng dựng sẵn hoặc dạng ký tự cơ sở kết hợp dấu.

Trong chính sách mẫu, hợp đồng xử lý cho credential mới là:

1. Giới hạn kích thước request tại cổng vào; sau giải mã JSON, kiểm tra giới hạn 4.096 byte của trường mật khẩu và tính hợp lệ của chuỗi.
2. Từ chối đúng các mã điểm bị cấm đã công bố.
3. Chuẩn hóa NFC, tức đưa các biểu diễn Unicode tương đương về dạng tổ hợp chuẩn.
4. Đếm mã điểm của kết quả NFC; kiểm tra khoảng 15–128 khi thiết lập mật khẩu mới.
5. Đối chiếu danh sách chặn trên giá trị chuẩn hóa khi thiết lập mật khẩu mới.
6. Mã hóa kết quả chuẩn hóa thành UTF-8 và đưa toàn bộ byte vào hàm dẫn xuất mật khẩu.

NIST khuyến nghị NFC trước bước băm và quy định cách đếm theo mã điểm khi hỗ trợ Unicode. Phải cố định cách xử lý giữa các luồng, thay vì trông chờ mỗi thư viện tự chọn. [NIST SP 800-63B-4, mục Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver)

Ba quy tắc bổ sung giúp hợp đồng không làm biến đổi bí mật ngoài dự kiến:

- Không tự bỏ khoảng trắng đầu/cuối, gộp nhiều khoảng trắng hoặc đổi chữ hoa thành chữ thường. NFC không phải thao tác bỏ dấu hay chuyển chữ hoa/thường.
- Không cắt phần vượt giới hạn. Giao diện, API, bộ chuyển đổi dữ liệu và thư viện xác minh đều phải xử lý nhất quán.
- Lưu phiên bản hợp đồng xử lý cùng bản ghi credential. Khi xác minh credential cũ, sử dụng đúng phiên bản đã tạo bản ghi đó.

Ví dụ kiểm thử Unicode có thể dùng hai chuỗi biểu diễn chữ “é”: U+00E9 và cặp U+0065 U+0301, đặt trong cùng một phần còn lại đủ độ dài. Với phiên bản chọn NFC, hai đầu vào này dẫn tới cùng chuỗi chuẩn hóa. Ngược lại, một chuỗi có thêm khoảng trắng cuối phải khác chuỗi không có khoảng trắng đó.

Không áp dụng một cách máy móc toàn bộ chính sách tạo mật khẩu mới vào đăng nhập credential cũ. Ví dụ, tăng độ dài tối thiểu không được âm thầm khiến mọi mật khẩu cũ không đăng nhập được. Giới hạn an toàn đầu vào vẫn cần thiết, nhưng phải tương thích các credential còn hiệu lực hoặc có kế hoạch chuyển đổi rõ ràng.

Đặc biệt, khả năng nhận 128 mã điểm ở giao diện chưa chứng minh thư viện băm xử lý đủ dữ liệu. Nhiều triển khai bcrypt có giới hạn 72 byte; một mật khẩu Unicode có thể chạm giới hạn byte sớm hơn dự tính. Cần kiểm tra thư viện đang dùng và có thiết kế chuyển đổi, không tự ghép một lớp băm trước để che lỗi cắt ngắn. [OWASP Password Storage, phần bcrypt](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#bcrypt)

## 5. Passphrase và kiểm tra mật khẩu dễ đoán

### 5.1. Đánh giá cách sinh, không chỉ đánh giá vẻ ngoài

Một passphrase do người dùng tự chọn từ câu quen thuộc không có cùng đặc tính với các từ được chọn ngẫu nhiên, độc lập. Mẫu ví dụ đã công khai trong tài liệu cũng không còn là lựa chọn riêng tư.

Nếu một bộ sinh chọn độc lập và đồng đều k từ trong tập N từ, số kết quả có thể là N mũ k. Lượng thông tin của quá trình sinh khi đó là:

~~~text
H = log2(N^k) = k × log2(N)
~~~

Chẳng hạn, với N = 7.776 và k = 5, kết quả xấp xỉ 64,6 bit, **chỉ trong giả định sinh ngẫu nhiên nêu trên**. Không được gán con số đó cho một câu năm từ do người dùng tự nghĩ ra; cũng không suy ra một thời gian bẻ khóa cố định nếu chưa biết chi phí thử, năng lực đối phương và khả năng lộ bí mật.

Yêu cầu khả dụng nên cho phép cả passphrase lẫn mật khẩu ngẫu nhiên từ trình quản lý. Không ép tất cả người dùng sang một mẫu câu dễ đoán như “ba từ + năm hiện tại”.

### 5.2. Danh sách chặn là một phụ thuộc có vòng đời

Trong ví dụ, SR-PW-03 yêu cầu máy chủ từ chối mật khẩu mới trùng toàn bộ một mục trong tập mật khẩu phổ biến, đã lộ hoặc dễ dự đoán theo ngữ cảnh dịch vụ. Không cấm mọi passphrase chỉ vì chứa một từ thông dụng.

Đặc tả của tập chặn cần nêu:

| Nội dung | Quyết định minh họa |
| --- | --- |
| Nơi kiểm tra | Máy chủ, tại đăng ký, đổi và đặt lại mật khẩu |
| Cách so khớp | So khớp toàn bộ giá trị sau NFC; có test vector cho định dạng tập chặn |
| Ngữ cảnh riêng | Có bộ vector cho tên dịch vụ và các mẫu mặc định mà dự án đã nhận diện |
| Phiên bản | Mỗi bản phát hành tập chặn có ID, thời điểm và nguồn được duyệt |
| Tính sẵn sàng | Tải bản đã xác thực vào bộ nhớ hoặc kho cục bộ; không phụ thuộc gọi Internet cho mỗi lần đăng nhập |
| Khi không có bản hợp lệ | Tạm từ chối thiết lập mật khẩu mới, trả lỗi dịch vụ có thể thử lại; không tự cho qua |
| Mục tiêu cập nhật | Trong vòng 24 giờ từ khi nguồn được duyệt phát hành dữ liệu mà hệ thống sử dụng |
| Quyền riêng tư | Không gửi mật khẩu nguyên văn hoặc định danh kèm bí mật ra bên ngoài |

Ngưỡng 24 giờ là mục tiêu vận hành giả định. Nếu dùng một giao thức tra cứu bên ngoài, phải đặc tả dữ liệu được tiết lộ và đánh giá quyền riêng tư; không coi việc không gửi nguyên văn là bảo đảm không tiết lộ thông tin.

Thước đo độ mạnh ở giao diện chỉ là phản hồi hỗ trợ. Máy chủ vẫn là nơi quyết định chấp nhận. Giao diện nên giải thích cách chọn bí mật dài, riêng cho dịch vụ và hỗ trợ tự điền; không chặn thao tác dán. [OWASP Authentication, phần Password Managers](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#password-managers)

Danh sách chặn khi tạo mới không phát hiện được mọi lần tái sử dụng mật khẩu. Một yêu cầu riêng phải xử lý credential đang dùng nếu sau đó có bằng chứng lộ; không dùng sự cố dịch vụ tra cứu làm lý do vô hiệu hóa toàn bộ đăng nhập.

## 6. Chuyển mục tiêu bảo vệ dữ liệu thành yêu cầu lưu trữ

### 6.1. Định nghĩa đúng dữ liệu cần bảo vệ

Máy chủ cần lưu một giá trị dùng để **xác minh** bí mật, không cần khôi phục lại mật khẩu gốc. Bản ghi xác minh vẫn là dữ liệu nhạy cảm vì đối phương có thể dùng nó để thử đoán ngoại tuyến.

Sử dụng hàm băm/dẫn xuất thiết kế cho mật khẩu và salt riêng cho từng bản ghi. SHA-256 đơn thuần, mã hóa Base64 hoặc mã hóa đối xứng để lấy lại mật khẩu không đáp ứng mục tiêu lưu trữ xác minh này. Salt không phải bí mật dùng chung; pepper, nếu có, là bí mật bổ sung phải được quản lý tách khỏi kho credential. [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

Ví dụ lựa chọn cho hệ thống mới là Argon2id. Các tham số bộ nhớ, số lượt và mức song song điều khiển chi phí tính toán; việc chọn tham số phải gắn với môi trường chạy. [RFC 9106, phần Inputs và Parameter Choice](https://datatracker.ietf.org/doc/html/rfc9106)

### 6.2. Hồ sơ lưu trữ mẫu có thể kiểm chứng

Cấu hình dưới đây là một **ứng viên để đo hiệu năng và thẩm định**, chưa phải kết quả benchmark:

~~~yaml
credentialProfile:
  id: pw-profile-v1
  inputContract: nfc-utf8-v1
  algorithm: argon2id
  memoryKiB: 65536
  iterations: 3
  parallelism: 1
  saltBytes: 16
  outputBytes: 32
~~~

SR-PW-04 của tình huống mẫu bao gồm các nghĩa vụ:

- Credential mới dùng đúng hồ sơ đã được phê duyệt; salt 16 byte được sinh bằng nguồn ngẫu nhiên mật mã cho mỗi lần tạo.
- Bản ghi lưu thuật toán, phiên bản, tham số, salt và kết quả xác minh theo định dạng thư viện hỗ trợ; không lưu mật khẩu gốc.
- Lời gọi xác minh dùng API thư viện đã được đánh giá, không tự so sánh từng ký tự rồi trả sớm theo tiền tố.
- Quyền đọc kho credential chỉ cấp cho thành phần cần xác minh và tác vụ vận hành được phê duyệt. Bản sao lưu có kiểm soát truy cập và bảo vệ tương ứng.
- Khi chọn dùng pepper, bản ghi chỉ tham chiếu phiên bản khóa; yêu cầu phải nêu nơi giữ khóa, quyền dùng, xử lý khi mất khóa và phương án thay khóa.

Hai tài khoản dùng cùng mật khẩu phải tạo ra bản ghi khác nhau do salt khác nhau. Điều này ngăn việc dùng chung một phép tính cho các bản ghi theo cách đơn giản, nhưng không biến mật khẩu dễ đoán thành mật khẩu khó đoán.

### 6.3. Liên kết bảo mật với tính sẵn sàng

Ngân sách mẫu yêu cầu đo p95 cho phép xác minh không quá 400 ms ở tải 10 yêu cầu/giây trên máy 4 vCPU, 8 GiB RAM với cùng phiên bản thư viện triển khai. Báo cáo cần nêu thêm CPU, RAM thực tế, độ dài hàng đợi và tỷ lệ lỗi. Chưa có số đo thì chưa được tuyên bố đạt.

Với hồ sơ trên, 16 phép tính đồng thời cần khoảng 1 GiB chỉ cho vùng nhớ Argon2, chưa gồm runtime và bộ đệm. Vì vậy, kiến trúc mẫu giới hạn 8 tác vụ KDF đồng thời trên mỗi instance và hàng đợi tối đa 32 yêu cầu; phần vượt trả lỗi quá tải được kiểm soát, không tạo tác vụ vô hạn. Các con số cần được xác nhận lại trên môi trường triển khai.

Không tự giảm tham số băm khi tải tăng. Nếu ứng viên không đạt ngân sách, nhóm cần điều chỉnh năng lực, mô hình tải hoặc ra quyết định bảo mật mới có bằng chứng. Rate limit phải hoạt động trước tác vụ tốn kém.

### 6.4. Nâng cấp credential cũ

Bản ghi chứa phiên bản giúp hệ thống biết lúc nào cần rehash. Sau khi xác minh thành công bằng hồ sơ cũ được phép, dịch vụ có thể tạo lại bản ghi bằng hồ sơ mới và salt mới. Không thể nâng cấp đúng hàm dẫn xuất cho toàn bộ người dùng chỉ từ các kết quả băm cũ; người không đăng nhập cần một chính sách thời hạn chuyển đổi hoặc đặt lại.

Rehash tham số không được tự đổi quy tắc diễn giải đầu vào. Nếu muốn chuyển từ hợp đồng cũ sang NFC, cần xử lý như thay đổi ngữ nghĩa credential và thiết kế chuyển đổi riêng.

Cập nhật phải có điều kiện theo phiên bản bản ghi hoặc cơ chế tương đương. Một rehash chạy chậm không được ghi đè mật khẩu mà người dùng vừa đổi ở luồng khác.

## 7. Đặc tả chống đoán thử trực tuyến

SR-PW-05 trong tình huống mẫu quy định:

1. Dịch vụ đếm thất bại theo tài khoản trong cửa sổ trượt 15 phút, dùng trạng thái chia sẻ giữa các instance.
2. Khi có thất bại thứ năm trong cửa sổ, tài khoản bước vào thời gian hạn chế 60 giây. Các yêu cầu mới trong thời gian này không chạy KDF.
3. Yêu cầu bị chặn không được tính thành một lần xác minh sai mới và không kéo dài mốc hết hạn.
4. Hết thời gian hạn chế, cho phép thử lại; một lần xác minh sai mới khi số thất bại trong cửa sổ vẫn từ năm trở lên kích hoạt thêm 60 giây.
5. Khi hoàn tất xác thực thành công, bao gồm yếu tố bắt buộc tiếp theo nếu có, xóa bộ đếm thất bại của luồng tương ứng. Không xóa chỉ vì bước mật khẩu đúng trong khi MFA vẫn thất bại.
6. Kho bộ đếm lỗi thì đăng nhập bằng mật khẩu chuyển sang trạng thái tạm không khả dụng với lỗi chung; không tự bỏ giới hạn. Phiên đang hợp lệ tuân theo chính sách phiên riêng.

Cần tính cả yêu cầu đang chạy đồng thời: bước cấp quyền thực hiện phép xác minh phải nguyên tử và giới hạn số phép thử đang xử lý cho cùng tài khoản. Nếu chỉ tăng bộ đếm sau khi KDF trả về, hàng trăm yêu cầu có thể vượt cổng kiểm tra cùng lúc.

Quy tắc trên chỉ là một lớp của ví dụ. Bộ phát hiện spraying còn cần nhìn nhiều tài khoản theo nguồn hoặc chiến dịch, trong khi stuffing có thể dùng nhiều IP. Dấu vân tay thiết bị hay CAPTCHA là tín hiệu hỗ trợ, không phải bằng chứng sở hữu tài khoản và không được thay thế yếu tố xác thực bắt buộc.

Giới hạn theo tài khoản cũng tạo rủi ro từ chối dịch vụ có chủ đích. Thiết kế cần đo tỷ lệ người dùng hợp lệ bị ảnh hưởng, cảnh báo tấn công và có lối phục hồi đủ độ tin cậy. Không biến nút “mở khóa” thành cách đặt lại bộ đếm vô điều kiện cho đối phương.

SR-PW-06 yêu cầu thông báo đăng nhập sai không tiết lộ “tài khoản tồn tại nhưng mật khẩu sai”. Kiểm tra cả nội dung, mã HTTP và nhánh xử lý thời gian. Tài khoản không tồn tại phải có cách xử lý so sánh được, có giới hạn chi phí; không tạo một tác vụ băm giả không giới hạn để che giấu sự tồn tại. [OWASP Authentication, phần Authentication and Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages)

Không ghi yêu cầu “thời gian trả về phải bằng nhau tuyệt đối” trên mạng. Thay vào đó, cố định hành vi nghiệp vụ và thiết kế phép kiểm tra thống kê trong môi trường có kiểm soát để tìm nhánh trả sớm hoặc tín hiệu phân biệt có thể khai thác.

## 8. Đổi mật khẩu và phục hồi là cùng một biên bảo mật

Một chính sách tạo mật khẩu tốt có thể bị vô hiệu nếu nhân viên hỗ trợ đọc được mật khẩu hoặc nếu luồng đặt lại cấp luôn phiên quản trị chỉ từ một email.

Hướng dẫn phục hồi của OWASP nhấn mạnh token ngẫu nhiên, dùng một lần, có hạn, phản hồi nhất quán và tránh tự đăng nhập sau khi đặt lại. Các mục tiêu này cần được cụ thể hóa theo rủi ro từng hệ thống. [OWASP Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

SR-PW-07 của tình huống mẫu đặt các điều kiện sau:

| Thao tác | Điều kiện trước khi thay đổi | Kết quả và giới hạn mẫu |
| --- | --- | --- |
| Đổi khi còn biết mật khẩu | Có phiên hợp lệ, xác minh lại mật khẩu hiện tại; tài khoản quản trị hoàn tất MFA | Mật khẩu mới qua cùng chính sách; bản ghi cũ hết hiệu lực ngay khi commit |
| Gửi yêu cầu đặt lại | Nhận định danh nhưng không xác nhận công khai tài khoản tồn tại | Trả cùng phản hồi; tối đa 3 thư mỗi tài khoản trong cửa sổ trượt 1 giờ, có kiểm soát theo nguồn |
| Dùng liên kết đặt lại | Token ngẫu nhiên 32 byte, lưu giá trị băm phía máy chủ, hết hạn sau 15 phút | Token gắn đúng tài khoản và mục đích; tiêu thụ một lần bằng thao tác nguyên tử |
| Hoàn tất đặt lại | Token hợp lệ và mật khẩu mới đạt chính sách | Không tự đăng nhập; các token đặt lại còn lại bị vô hiệu; người dùng quay lại luồng xác thực đầy đủ |
| Xử lý phiên cũ | Đổi hoặc đặt lại mật khẩu đã commit thành công | Phiên và refresh token phát hành trước thời điểm đổi bị thu hồi trong tối đa 60 giây |
| Phục hồi quản trị | Có bằng chứng phục hồi đáp ứng chính sách quản trị | Đặt lại mật khẩu không xóa hoặc bỏ qua MFA; mất MFA cần quy trình riêng |

Token đặt lại là bí mật ngẫu nhiên có entropy cao, không phải mật khẩu do người dùng chọn. Việc lưu băm token bằng cơ chế phù hợp không có nghĩa là SHA-256 đơn thuần trở thành lựa chọn đúng để lưu mật khẩu người dùng.

Yêu cầu thu hồi phiên phải xét kiến trúc thực tế. Nếu access token được xác minh hoàn toàn độc lập và sống lâu, việc xóa refresh token chưa đáp ứng mốc 60 giây. Cần cơ chế kiểm tra phiên bản credential, danh sách thu hồi, kiểm tra trạng thái hoặc thời hạn token phù hợp; phải kiểm thử qua từng dịch vụ tiêu thụ token.

Đổi mật khẩu cần chống CSRF nếu dựa trên cookie. Cập nhật credential và tiêu thụ token phải nhất quán: nếu giao dịch lỗi, không để token được dùng lại sau một lần đổi đã thành công, hoặc tạo trạng thái tài khoản không thể phục hồi.

Khi có bằng chứng tài khoản bị chiếm, phạm vi ứng phó còn gồm phiên đang hoạt động, phương thức MFA và thông tin phục hồi đã bị sửa. Mật khẩu mới không tự loại bỏ mọi đường truy cập của đối phương.

## 9. Liên kết yêu cầu với kiến trúc và logging

Một phân công trách nhiệm mẫu:

~~~mermaid
flowchart LR
    U["Người dùng / trình quản lý mật khẩu"] -->|"TLS"| G["Cổng vào: kích thước, nguồn"]
    G --> A["Dịch vụ xác thực"]
    A --> R["Trạng thái giới hạn thử dùng chung"]
    A --> V["Hợp đồng chuỗi và thư viện KDF"]
    A --> B["Tập chặn cho mật khẩu mới"]
    V --> D["Kho bản ghi credential"]
    A --> M["MFA và quản lý phiên"]
    A --> E["Sự kiện bảo mật đã loại bí mật"]
~~~

Sơ đồ là ranh giới trách nhiệm, không quy định bắt buộc phải tách thành từng microservice. Yêu cầu truyền tin phải bao phủ những đoạn thực sự mang bí mật, kể cả từ điểm kết thúc TLS đến dịch vụ xác thực. Không đặt mật khẩu trong URL hoặc chuyển qua hàng đợi nghiệp vụ.

Nếu dùng nhà cung cấp định danh, ứng dụng cần nêu yêu cầu nào được ủy thác và bằng chứng cấu hình hoặc hợp đồng nào xác nhận việc thực thi. Ứng dụng không thu thêm một mật khẩu cục bộ chỉ để có đủ trường dữ liệu. Tài khoản dự phòng còn dùng mật khẩu cục bộ phải được kiểm kê riêng.

SR-PW-08 quy định ghi sự kiện như tạo credential, đổi, đặt lại, hạn chế thử, lỗi phụ thuộc và nâng cấp hồ sơ. Mỗi sự kiện có thời gian, loại sự kiện, kết quả, ID tương tác và phiên bản chính sách khi cần. Chỉ dùng định danh nội bộ hoặc dữ liệu đã giảm thiểu theo mục đích vận hành.

Mật khẩu, kết quả băm xác minh, pepper, token đặt lại, cookie và token truy cập không được xuất hiện trong log, trace, analytics, bản ghi phiên hỗ trợ hoặc nội dung thư thông báo. Kiểm soát cần bao phủ đường lỗi và chế độ debug. [OWASP Logging, phần Data to Exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude)

Không “ẩn danh” mật khẩu trong telemetry bằng cách băm nhanh rồi lưu. Cách đó vẫn tạo dữ liệu để đối phương đoán bí mật. Dùng sự kiện kết quả thay cho giá trị bí mật.

Các số đo vận hành mẫu gồm tỷ lệ đăng nhập sai, số tài khoản bị thử theo chiến dịch, số yêu cầu bị hạn chế, p95 KDF, độ dài hàng đợi, tỷ lệ rehash và tỷ lệ đặt lại thất bại. Quyền đọc và thời gian giữ dữ liệu cần có mục đích rõ; không đưa email hoặc giá trị mật khẩu thành nhãn metric.

## 10. Viết một yêu cầu hoàn chỉnh và truy vết được

Mỗi yêu cầu nên có ID ổn định, phạm vi, hành vi bắt buộc, điều kiện kích hoạt, cách xử lý lỗi, nguồn hoặc lý do, chủ sở hữu và tiêu chí nghiệm thu. Không gộp mọi vấn đề vào một câu dài khiến mỗi đội hiểu một cách.

Ví dụ đặc tả SR-PW-04:

| Trường | Nội dung mẫu |
| --- | --- |
| ID | SR-PW-04 |
| Mục tiêu | Tăng chi phí đoán ngoại tuyến nếu kho credential bị lộ |
| Rủi ro | R-PW-04 |
| Phạm vi | Credential mật khẩu cục bộ được tạo hoặc nâng cấp sau khi hồ sơ được phê duyệt |
| Nghĩa vụ | Dùng hồ sơ Argon2id đã duyệt; salt riêng từ nguồn ngẫu nhiên mật mã; lưu phiên bản và tham số; không lưu mật khẩu gốc |
| Điểm thực thi | Dịch vụ xác thực, thư viện KDF, kho credential và đường sao lưu |
| Phụ thuộc | Nguồn ngẫu nhiên, phiên bản thư viện, cấu hình năng lực máy chủ |
| Chủ sở hữu | Nhóm định danh triển khai; nhóm an toàn thông tin phê duyệt hồ sơ; nhóm vận hành theo dõi năng lực |
| Hành vi lỗi | Không tạo credential khi hàm dẫn xuất hoặc nguồn ngẫu nhiên lỗi; không chuyển sang thuật toán yếu hơn |
| Bằng chứng | Cấu hình được duyệt, báo cáo hiệu năng, kiểm tra bản ghi, kiểm thử lỗi và cạnh tranh cập nhật |
| Giới hạn bảo vệ | Không ngăn phishing, thiết bị người dùng bị chiếm hoặc kẻ tấn công điều khiển dịch vụ đang chạy |
| Ngoại lệ | Có người chịu trách nhiệm rủi ro, biện pháp bù, ngày hết hạn và kế hoạch thay thế |

Ma trận truy vết cho ví dụ:

| Yêu cầu | Rủi ro chính | Thành phần | Bằng chứng nghiệm thu |
| --- | --- | --- | --- |
| SR-PW-01: độ dài và phạm vi | R-PW-01 | API tạo/đổi/đặt lại | Vector 14, 15, 128, 129 mã điểm qua mọi luồng |
| SR-PW-02: hợp đồng chuỗi | R-PW-04, R-PW-06 | Bộ chuẩn hóa, thư viện xác minh | Vector Unicode, khoảng trắng và phần đuôi dài |
| SR-PW-03: danh sách chặn | R-PW-01, R-PW-03 | Chính sách máy chủ, dữ liệu chặn | Bản dữ liệu có phiên bản, trường hợp bị chặn, kiểm thử mất dữ liệu |
| SR-PW-04: lưu trữ và nâng cấp | R-PW-04, R-PW-06 | KDF, kho credential, tài nguyên | Bản ghi, benchmark và kiểm thử rehash cạnh tranh |
| SR-PW-05: giới hạn thử | R-PW-01, R-PW-02 | Trạng thái chia sẻ, bộ điều phối | Kiểm thử nhiều instance và yêu cầu đồng thời |
| SR-PW-06: phản hồi đăng nhập | R-PW-01 | API và giao diện | So sánh nội dung, HTTP và nhánh thời gian |
| SR-PW-07: thay đổi/phục hồi | R-PW-05 | Token, kho credential, phiên | Token dùng một lần, thu hồi phiên, MFA còn hiệu lực |
| SR-PW-08: telemetry | R-PW-07 | Gateway, ứng dụng, APM, log | Dữ liệu tổng hợp đủ điều tra, không có bí mật thử nghiệm |

Bảng này giúp lần theo cả hai chiều: từ rủi ro đến nơi thực thi, và từ một ca kiểm thử đến mục tiêu cần bảo vệ. Một yêu cầu viện dẫn tiêu chuẩn vẫn phải chỉ ra bằng chứng của hệ thống; câu “theo NIST/OWASP” không tự tạo tiêu chí nghiệm thu.

## 11. Thiết kế bằng chứng kiểm thử theo hành vi quan sát được

Các ca dưới đây là **kế hoạch nghiệm thu của tình huống mẫu**, không phải kết quả kiểm thử đã thực hiện.

| Ca | Dữ liệu hoặc thao tác | Kết quả mong đợi |
| --- | --- | --- |
| AT-PW-01 | Gọi API trực tiếp để đăng ký, đổi và đặt lại với các độ dài biên | Cùng chính sách máy chủ; không thể vượt qua bằng bỏ JavaScript |
| AT-PW-02 | Dùng hai biểu diễn Unicode tương đương theo NFC | Xác minh được theo hợp đồng phiên bản mới; đếm trên chuỗi sau NFC |
| AT-PW-03 | Thêm hoặc bỏ khoảng trắng đầu/cuối, đổi hoa/thường | Bí mật thay đổi; không có trim hoặc đổi hoa/thường ngầm |
| AT-PW-04 | Hai chuỗi hợp lệ có cùng 72 byte đầu nhưng khác phần sau | Mật khẩu sai phần đuôi bị từ chối; không có cắt ngắn ở thư viện |
| AT-PW-05 | Gửi chuỗi quá 128 mã điểm hoặc quá giới hạn byte thô | Từ chối nguyên vẹn; không cắt để chấp nhận; không chạy KDF cho đầu vào vượt cổng an toàn |
| AT-PW-06 | Gửi mật khẩu thuộc tập chặn qua từng API tạo mới | Không lưu credential; phản hồi cho phép người dùng chọn lại mà không lộ dữ liệu nội bộ |
| AT-PW-07 | Cố tạo credential khi không có tập chặn hợp lệ | Trả lỗi dịch vụ có thể thử lại; không âm thầm bỏ kiểm tra |
| AT-PW-08 | Tạo hai tài khoản với cùng mật khẩu, kiểm tra bản ghi qua quyền thử nghiệm | Salt và kết quả khác nhau; có đủ phiên bản và tham số; không có nguyên văn |
| AT-PW-09 | Thử sai từ nhiều instance, xen kẽ nhiều nguồn và đồng thời | Ngưỡng tổng hợp theo tài khoản vẫn có hiệu lực; yêu cầu bị chặn không kéo dài thời gian hạn chế |
| AT-PW-10 | Cho kho bộ đếm mất kết nối | Đăng nhập mới nhận lỗi chung; không có nhánh bỏ rate limit |
| AT-PW-11 | Gửi hai yêu cầu đặt lại đồng thời với cùng token | Chỉ một lần đổi commit thành công; lần còn lại không thay credential |
| AT-PW-12 | Dùng token hết hạn hoặc token cấp trước một lần đặt lại thành công | Bị từ chối, không tạo phiên hoặc sửa credential |
| AT-PW-13 | Dùng phiên và refresh token cũ qua từng dịch vụ sau đổi mật khẩu | Bị thu hồi trong giới hạn 60 giây của chính sách mẫu |
| AT-PW-14 | Đặt lại mật khẩu quản trị rồi bỏ qua MFA | Không cấp quyền quản trị |
| AT-PW-15 | Cho rehash cũ hoàn tất sau một lần đổi mật khẩu mới | Bản ghi mới không bị ghi đè; mật khẩu cũ vẫn vô hiệu |
| AT-PW-16 | Chạy tải mục tiêu với hồ sơ KDF và cấu hình máy đã nêu | Có số đo p95, RAM, CPU, hàng đợi; không đổi tham số bảo mật để đạt số đẹp |
| AT-PW-17 | Gây lỗi xác minh và đặt lại bằng bí mật đánh dấu tổng hợp | Không tìm thấy bí mật hoặc token thử trong log, trace, analytics và thư |
| AT-PW-18 | Tài khoản có mật khẩu cũ dưới ngưỡng mới nhưng chưa đến hạn chuyển đổi | Xử lý đúng chính sách chuyển đổi đã duyệt; không tự thay nghĩa bí mật |

Với ca rò rỉ telemetry, chỉ dùng dữ liệu tổng hợp trong môi trường thử. Kiểm tra cấu hình thu thập và đường lỗi quan trọng vì một lần tìm kiếm không thấy bí mật chưa chứng minh mọi đường chạy đều an toàn.

Với ca bảo vệ chi phí đoán ngoại tuyến, không dùng việc “chưa bẻ được trong một lần thử” làm bằng chứng duy nhất. Cần kiểm tra thuật toán, tham số, nguồn salt, ranh giới truy cập và hồ sơ đánh giá rủi ro.

## 12. Duy trì yêu cầu trong vòng đời phát triển

Ở giai đoạn phân tích, nhóm xác định loại tài khoản, dữ liệu cần bảo vệ, mô hình đe dọa và các mức xác thực. Ở giai đoạn kiến trúc, nhóm chỉ rõ nơi xử lý bí mật, nơi giữ credential, quyền truy cập và phụ thuộc có thể gây mất khả dụng.

Khi triển khai, cấu hình chính sách phải có phiên bản và được thực thi tại máy chủ. Khi nghiệm thu, liên kết từng yêu cầu với bằng chứng thay vì chỉ kiểm tra màn hình đăng nhập. Khi vận hành, theo dõi tấn công, lỗi phụ thuộc và tác động lên người dùng hợp lệ.

Những thay đổi sau cần đánh giá lại yêu cầu liên quan:

- Thêm ứng dụng di động hoặc API có cách đếm chuỗi khác.
- Đổi nhà cung cấp định danh hoặc mở thêm lối đăng nhập dự phòng.
- Tăng tham số KDF, đổi thư viện hoặc đổi hợp đồng Unicode.
- Thay thời hạn access token làm thay đổi khả năng thu hồi phiên.
- Phát hiện lộ credential, tập chặn mới hoặc chiến dịch spraying.
- Tăng tải khiến hàng đợi xác thực chạm giới hạn tài nguyên.

Ngoại lệ cho hệ thống cũ phải có phạm vi, chủ sở hữu, thời hạn và biện pháp bù. Ví dụ, một tập tài khoản chưa chuyển khỏi thư viện cũ có thể cần luồng đặt lại bắt buộc trước hạn đã duyệt; không được âm thầm áp dụng giới hạn cắt ngắn cho mọi mật khẩu mới.

Một bộ yêu cầu hoàn chỉnh cho mật khẩu và passphrase cần chứng minh được cả ba mặt: người dùng có thể tạo và dùng bí mật khó đoán, hệ thống giảm khả năng bí mật bị lộ hoặc bị thử hàng loạt, và có thể khôi phục quyền kiểm soát khi xảy ra sự cố. Giá trị của đặc tả nằm ở mối liên kết giữa rủi ro, hành vi bắt buộc, thành phần chịu trách nhiệm và bằng chứng kiểm chứng.

# Khác biệt secret và key

Trong một hệ thống, mật khẩu cơ sở dữ liệu, API token, khóa mã hóa và khóa ký số đều cần được bảo vệ. Vì chúng thường được gọi chung là “thông tin bí mật”, đội phát triển đôi khi lưu tất cả vào cùng một nơi và áp dụng một quy trình quản lý giống nhau. Cách làm này dễ tạo ra lỗ hổng: mật khẩu người dùng cần được băm để xác minh, API token cần được thu hồi khi bị lộ, còn khóa mã hóa phải được quản lý theo vòng đời mật mã để dữ liệu đã mã hóa vẫn có thể được giải mã khi cần.

**Secret** và **key** có liên quan nhưng không đồng nghĩa. Secret mô tả tính chất cần giữ kín của một giá trị. Key mô tả vai trò của vật liệu mật mã trong một thuật toán hoặc giao thức. Một key có thể là secret, nhưng không phải mọi secret đều là key và không phải mọi key đều cần giữ bí mật.

## 1. Secret và key trả lời hai câu hỏi khác nhau

### Secret là gì?

Secret là thông tin mà hệ thống phải hạn chế người hoặc thành phần không được phép biết, vì việc tiết lộ có thể giúp kẻ tấn công mạo danh, vượt qua kiểm soát truy cập, truy cập dữ liệu hoặc thực hiện hành động trái phép.

Một secret thường được dùng để chứng minh danh tính hoặc quyền truy cập. Ví dụ:

- Mật khẩu người dùng.
- API token hoặc bearer token.
- Mật khẩu tài khoản dịch vụ.
- Chuỗi kết nối cơ sở dữ liệu có chứa thông tin xác thực.
- Client secret dùng trong một luồng xác thực.
- Khóa riêng (private key) dùng để ký hoặc giải mã.
- Khóa đối xứng dùng để mã hóa dữ liệu.

Secret được xác định chủ yếu bởi mức độ nhạy cảm và hậu quả khi bị tiết lộ. Giá trị đó có thể là một chuỗi ký tự, một tệp, một cấu hình hoặc vật liệu mật mã.

Không phải mọi thành phần trong một cấu hình đều là secret. Ví dụ, địa chỉ máy chủ, tên cơ sở dữ liệu và số cổng thường không cần giữ kín. Mật khẩu hoặc token nằm trong cùng chuỗi kết nối mới là phần secret. Việc phân loại theo từng trường giúp tránh che giấu quá mức những dữ liệu vốn không nhạy cảm, đồng thời bảo vệ đúng phần có thể cấp quyền truy cập.

### Key là gì?

Key, trong phạm vi quản lý khóa mật mã, là một giá trị hoặc vật liệu mật mã được thuật toán sử dụng để thực hiện một phép toán như mã hóa, giải mã, tạo chữ ký, xác minh chữ ký hoặc thiết lập bí mật chung.

Ví dụ:

- Khóa AES dùng để mã hóa và giải mã dữ liệu.
- Khóa riêng RSA có thể dùng để ký số hoặc giải mã tùy scheme; khóa riêng EC có thể dùng để ký số hoặc thiết lập bí mật chung tùy thuật toán và giao thức.
- Khóa công khai dùng để xác minh chữ ký hoặc mã hóa cho chủ sở hữu khóa riêng.
- Data Encryption Key (DEK) dùng để mã hóa dữ liệu.
- Key Encryption Key (KEK) dùng để bảo vệ hoặc bọc DEK.
- Khóa dùng trong MAC hoặc một cơ chế dẫn xuất khóa.

Một key có ý nghĩa nhờ thuật toán, mục đích sử dụng, độ dài, định dạng và các tham số liên quan. Key không đơn thuần là một chuỗi cần che giấu. Hệ thống phải quản lý cả cách tạo, phân phối, sử dụng, phiên bản, thời hạn, thu hồi, sao lưu và hủy key.

### Mối quan hệ giữa hai khái niệm

Có thể phân biệt bằng hai câu hỏi:

1. Giá trị này có cần được giữ kín để ngăn truy cập trái phép không? Nếu có, nó có thuộc nhóm secret không?
2. Giá trị này có được một thuật toán mật mã sử dụng như vật liệu khóa không? Nếu có, nó có phải key không?

Một khóa AES thường trả lời “có” cho cả hai câu hỏi: đó là key và cũng là secret. Một API token thông thường là secret nhưng không phải key mật mã. Một public key là key nhưng không cần giữ bí mật; điều quan trọng là xác minh được nguồn gốc và tính toàn vẹn của nó.

## 2. Các trường hợp thường gặp

| Đối tượng | Là secret? | Là key mật mã? | Điều cần bảo vệ |
|---|---|---|---|
| Mật khẩu người dùng | Có | Không | Không để lộ mật khẩu; lưu bộ xác minh bằng hàm băm mật khẩu có salt |
| API token dạng bearer | Có | Thông thường không | Giữ kín token, giới hạn quyền, thời hạn và khả năng thu hồi |
| Mật khẩu tài khoản dịch vụ | Có | Không | Lưu trữ an toàn, phân phối có kiểm soát và luân chuyển |
| Khóa AES | Có | Có | Bí mật khóa, giới hạn phép toán, quản lý phiên bản và khả năng phục hồi |
| Khóa riêng dùng để ký | Có | Có | Bí mật khóa, kiểm soát quyền ký, kiểm toán và bảo vệ tính toàn vẹn |
| Khóa công khai dùng để xác minh | Không nhất thiết | Có | Xác thực đúng chủ thể, nguồn phân phối và trạng thái tin cậy |
| Chứng thư số | Thông thường không | Không phải key | Xác minh chữ ký chứng thư, danh tính, thời hạn và trạng thái thu hồi |
| DEK đã được bọc bằng KEK | Bản rõ là secret | Có | Bảo vệ bản rõ; bảo vệ bản mã và khả năng truy cập KEK |
| Tệp cấu hình có mật khẩu DB | Có, ở phần thông tin xác thực | Không nhất thiết | Tách và bảo vệ trường nhạy cảm; tránh ghi toàn bộ cấu hình vào log |

Bảng này cho thấy tên gọi trong ứng dụng không quyết định bản chất. Một API token có thể là chuỗi ngẫu nhiên dài, nhưng chỉ vì nó có entropy cao không có nghĩa nó là khóa mã hóa. Ngược lại, một public key vẫn là key dù nó có thể được công bố rộng rãi.

### Vì sao public key vẫn là key dù không bí mật?

Trong mật mã bất đối xứng, một cặp khóa gồm public key và private key có quan hệ toán học với nhau, nhưng có chức năng khác nhau:

- Private key được chủ sở hữu bảo vệ. Nó có thể dùng để ký dữ liệu, giải mã hoặc tham gia thiết lập bí mật chung, tùy thuật toán và giao thức.
- Public key được chia sẻ cho bên khác. Nó có thể dùng để xác minh chữ ký hoặc mã hóa dữ liệu gửi cho chủ sở hữu.

Public key không cần bí mật, nhưng cần được gắn đúng với danh tính hoặc chủ thể. Nếu kẻ tấn công thay public key hợp lệ bằng public key của họ, bên gửi có thể mã hóa dữ liệu cho nhầm người hoặc bên nhận có thể xác minh chữ ký sai danh tính. Vì vậy, với public key, yêu cầu trọng tâm là tính xác thực và toàn vẹn, không phải tính bí mật.

Chứng thư số thường chứa public key cùng thông tin nhận dạng và chữ ký của tổ chức phát hành chứng thư. Chứng thư không phải private key và thường không cần giữ kín. Private key tương ứng phải được lưu riêng, với quyền truy cập chặt chẽ.

## 3. Vì sao không nên quản lý mọi secret và key theo cùng một cách?

Cả secret lẫn key đều cần kiểm soát truy cập, mã hóa khi lưu trữ, phân phối có kiểm soát và ghi nhận hoạt động. Tuy nhiên, cách sử dụng và vòng đời của chúng khác nhau.

### Mật khẩu người dùng cần được băm, còn credential ứng dụng thường cần được lấy lại

Khi hệ thống xác minh mật khẩu đăng nhập, nó không cần khôi phục mật khẩu gốc. Hệ thống nên lưu bộ xác minh được tạo bằng thuật toán băm mật khẩu chuyên dụng, có salt riêng cho từng mật khẩu và tham số chi phí phù hợp. Khi người dùng đăng nhập, hệ thống tính toán và so sánh kết quả xác minh.

Với API token hoặc mật khẩu tài khoản dịch vụ, ứng dụng thường cần lấy giá trị gốc để gửi tới dịch vụ đích. Những secret loại này cần được lưu trong kho secret có kiểm soát, thường được mã hóa khi lưu trữ và chỉ cấp cho workload được phép. Không thể thay thế việc lưu credential có thể truy xuất bằng cách chỉ lưu một giá trị băm nếu ứng dụng cần gửi chính credential đó đi xác thực.

Không nên nhầm việc băm mật khẩu với mã hóa khóa. Băm mật khẩu là cách lưu bộ xác minh một chiều; mã hóa dữ liệu bằng key là phép biến đổi có thể đảo ngược khi có khóa phù hợp.

### Key cần được quản lý theo mục đích mật mã

Key phải được tạo bằng nguồn ngẫu nhiên phù hợp và thuật toán được chấp nhận. Hệ thống cần xác định rõ key dùng để làm gì, thuật toán nào được phép sử dụng, thành phần nào được phép gọi phép toán và dữ liệu nào phụ thuộc vào key.

Đối với key quan trọng, KMS (Key Management Service) hoặc HSM (Hardware Security Module) có thể đảm nhiệm việc tạo, lưu giữ và thực hiện phép toán mật mã trong môi trường được kiểm soát. Một số thiết kế cho phép ứng dụng gọi KMS để mã hóa, giải mã hoặc ký mà không cần xuất vật liệu khóa thô ra khỏi ranh giới bảo vệ.

Khi key được dùng để bảo vệ dữ liệu lâu dài, việc vô hiệu hóa hoặc hủy key có thể khiến dữ liệu không thể giải mã. Vì vậy, quản lý key phải xét đến các bản sao lưu, phiên bản key, thời gian lưu trữ dữ liệu và yêu cầu khôi phục.

## 4. Secret Manager, KMS và HSM giải quyết những nhu cầu nào?

Các sản phẩm có thể đặt tên và phân chia tính năng khác nhau, nhưng có thể hiểu vai trò phổ biến như sau:

| Thành phần | Vai trò chính | Ví dụ dữ liệu hoặc thao tác |
|---|---|---|
| Secret Manager | Lưu trữ, phân phối và luân chuyển các secret mà ứng dụng cần truy xuất | API token, mật khẩu DB, client secret |
| KMS | Quản lý vòng đời key và cung cấp API thực hiện phép toán mật mã | Tạo key, mã hóa/giải mã, bọc/mở khóa DEK, ký/xác minh |
| HSM | Bảo vệ vật liệu khóa và thực hiện phép toán mật mã trong phần cứng chuyên dụng | Tạo và giữ private key, ký số, thao tác với key nhạy cảm |

Secret Manager phù hợp khi ứng dụng cần lấy một giá trị bí mật để kết nối hoặc xác thực với dịch vụ khác. KMS phù hợp khi hệ thống cần quản lý key và thực hiện các thao tác mật mã theo chính sách. HSM có thể là nền tảng phần cứng bên dưới KMS hoặc được ứng dụng sử dụng trực tiếp khi yêu cầu bảo vệ khóa cao hơn.

Ranh giới sản phẩm không phải lúc nào cũng tuyệt đối. Một số Secret Manager cho phép lưu chuỗi chứa PEM hoặc key material; một số KMS cho phép nhập key material hoặc quản lý nhiều loại key. Do đó, cần xem xét khả năng thực tế của dịch vụ, cách nó bảo vệ dữ liệu và trách nhiệm vận hành, thay vì chỉ dựa vào tên sản phẩm.

Một nguyên tắc thiết kế hữu ích là để ứng dụng lấy credential từ Secret Manager khi cần xác thực, còn yêu cầu mã hóa hoặc ký được chuyển tới KMS/HSM khi có thể. Cách này giới hạn số thành phần có khả năng đọc vật liệu khóa thô.

## 5. Khác biệt trong vòng đời và vận hành

| Hoạt động | Secret | Key |
|---|---|---|
| Tạo | Sinh token, cấp credential hoặc tạo thông tin xác thực | Sinh key theo thuật toán, độ dài và nguồn ngẫu nhiên phù hợp |
| Lưu trữ | Lưu giá trị có thể truy xuất trong kho secret được bảo vệ; mật khẩu người dùng thường lưu bộ xác minh đã băm | Lưu trong KMS/HSM hoặc kho key được bảo vệ; cân nhắc key không thể xuất |
| Cấp quyền | Cho phép workload hoặc người dùng được phép đọc secret | Cho phép gọi đúng thao tác trên key; hạn chế đọc hoặc xuất vật liệu khóa |
| Sử dụng | Gửi credential tới dịch vụ để xác thực hoặc cấp quyền | Đưa key vào thuật toán để mã hóa, giải mã, ký, xác minh hoặc dẫn xuất |
| Xoay vòng | Cấp credential mới, cập nhật nơi tiêu thụ, kiểm tra hoạt động rồi vô hiệu hóa credential cũ | Tạo phiên bản key mới; xác định dữ liệu mới dùng key nào và dữ liệu cũ cần key nào để giải mã hoặc xác minh |
| Thu hồi | Vô hiệu hóa token, mật khẩu hoặc tài khoản liên quan | Vô hiệu hóa key hoặc giới hạn thao tác; đánh giá tác động đến dữ liệu và chữ ký hiện có |
| Hủy | Xóa giá trị và các bản sao theo chính sách lưu giữ | Hủy vật liệu khóa theo quy trình có kiểm soát; xác nhận ảnh hưởng tới khả năng giải mã hoặc xác minh |
| Kiểm toán | Theo dõi ai hoặc workload nào đọc secret, vào thời điểm nào | Theo dõi ai gọi thao tác nào trên key, với tài nguyên và phiên bản nào |

### Xoay vòng secret thường gắn với việc thay credential ở hai đầu

Giả sử một ứng dụng dùng mật khẩu tài khoản dịch vụ để kết nối cơ sở dữ liệu. Khi xoay vòng, hệ thống cần cấp mật khẩu mới, cập nhật nơi lưu secret, bảo đảm ứng dụng đã dùng giá trị mới, sau đó vô hiệu hóa mật khẩu cũ. Nếu vô hiệu hóa quá sớm, ứng dụng đang chạy có thể mất kết nối. Nếu giữ credential cũ quá lâu, cửa sổ rủi ro khi credential bị lộ sẽ kéo dài.

API token cũng cần quy trình tương tự: phát hành token mới với phạm vi quyền phù hợp, cập nhật workload tiêu thụ, xác minh hoạt động rồi thu hồi token cũ. Với token có hỗ trợ nhiều phiên bản đồng thời, có thể triển khai chuyển đổi theo từng bước.

### Xoay vòng key cần tính đến dữ liệu đã được bảo vệ

Giả sử hệ thống dùng một DEK để mã hóa các tệp. Khi tạo DEK mới, dữ liệu được ghi sau thời điểm chuyển đổi có thể dùng key mới. Nhưng các tệp cũ vẫn cần key cũ để giải mã, trừ khi hệ thống thực hiện giải mã rồi mã hóa lại dữ liệu bằng key mới.

Nếu DEK được bọc bởi một KEK, có thể thay KEK và bọc lại các DEK mà không phải mã hóa lại toàn bộ dữ liệu lớn, tùy kiến trúc và khả năng của KMS. Điều này thường giảm chi phí chuyển đổi, nhưng hệ thống vẫn phải giữ khả năng truy cập phiên bản KEK cần thiết trong thời gian dữ liệu cũ còn tồn tại.

Vì vậy, “xoay vòng key” có thể chỉ là chuyển sang phiên bản key mới cho dữ liệu mới, hoặc có thể bao gồm việc mã hóa lại dữ liệu cũ. Hai thao tác có chi phí và tác động khác nhau; chính sách cần nói rõ hệ thống đang thực hiện loại nào.

### Thu hồi và hủy key có thể ảnh hưởng đến tính sẵn sàng dữ liệu

Khi một API token bị lộ, thu hồi token thường ngăn việc sử dụng token đó trong các yêu cầu tiếp theo. Khi một key mã hóa bị nghi ngờ lộ, đội vận hành phải đánh giá dữ liệu nào đã được mã hóa bằng key đó, có cần mã hóa lại hay không và key mới sẽ được triển khai thế nào.

Hủy key là hành động có thể không đảo ngược. Nếu bản sao lưu chỉ chứa ciphertext và key cần thiết đã bị hủy, dữ liệu có thể không thể khôi phục. Nếu key dùng để ký số bị hủy, chữ ký đã tạo trước đó vẫn có thể được xác minh nếu public key và thông tin tin cậy còn tồn tại; tuy nhiên, hệ thống sẽ không thể tạo chữ ký mới bằng private key đã hủy. Cần phân biệt việc ngừng sử dụng, vô hiệu hóa tạm thời, thu hồi và hủy vật liệu khóa.

## 6. Ví dụ: ứng dụng dùng secret để kết nối và key để mã hóa

Một dịch vụ xử lý đơn hàng có thể cần hai nhóm tài nguyên bảo vệ:

- Mật khẩu hoặc token để kết nối tới cơ sở dữ liệu.
- Key để mã hóa dữ liệu nhạy cảm trước khi lưu.

Ứng dụng lấy credential từ Secret Manager khi cần kết nối. Khi mã hóa dữ liệu, ứng dụng gọi KMS để lấy DEK mới cho đối tượng dữ liệu hoặc yêu cầu KMS thực hiện thao tác mật mã. Với mô hình envelope encryption, KMS bảo vệ DEK bằng KEK. Ứng dụng sử dụng bản rõ DEK trong phạm vi cần thiết để mã hóa dữ liệu, còn bản DEK đã được bọc được lưu cùng ciphertext.

~~~mermaid
flowchart TD
    A[Ứng dụng] -->|Đọc credential có quyền| B[Secret Manager]
    B -->|Mật khẩu DB hoặc API token| A
    A -->|Yêu cầu tạo hoặc sử dụng DEK| C[KMS]
    C -->|DEK bản rõ và DEK đã bọc| A
    A -->|Mã hóa dữ liệu bằng DEK| D[Ciphertext]
    A -->|Lưu DEK đã bọc| E[Kho dữ liệu]
    D --> E
    C --- F[KEK được bảo vệ trong KMS hoặc HSM]
~~~

Trong luồng này, credential và key có mục đích khác nhau:

1. Credential cho phép ứng dụng chứng minh quyền truy cập tới cơ sở dữ liệu hoặc API.
2. DEK thực hiện phép mã hóa dữ liệu.
3. KEK bảo vệ DEK để DEK có thể được lưu trữ hoặc truyền đi dưới dạng đã bọc.
4. KMS kiểm soát quyền sử dụng KEK và ghi nhận các thao tác liên quan.

Không nên ghi credential, DEK bản rõ hoặc key material vào log. Khi có thể, ứng dụng nên giải phóng bản rõ DEK sau khi hoàn thành công việc và hạn chế thời gian, phạm vi mà nó xuất hiện trong bộ nhớ. Cần lưu ý rằng việc xóa dữ liệu khỏi bộ nhớ trong môi trường runtime có thể chịu ảnh hưởng của bản sao bộ nhớ, garbage collector, dump và cơ chế của hệ điều hành; thiết kế giảm tiếp xúc vẫn cần đi kèm kiểm soát dump, quyền truy cập máy chủ và quy trình xử lý sự cố.

## 7. Những nhầm lẫn dễ tạo ra rủi ro

**Coi mọi chuỗi ngẫu nhiên là key.** Một token ngẫu nhiên có thể khó đoán nhưng nếu nó được dịch vụ đích dùng như bearer credential thì nó là secret xác thực. Không nên tự dùng token đó làm khóa mã hóa nếu không có thiết kế mật mã và dẫn xuất khóa phù hợp.

**Coi mọi key đều phải được giữ bí mật.** Public key được thiết kế để chia sẻ. Cần bảo vệ tính xác thực và toàn vẹn của public key, chẳng hạn bằng chứng thư số hoặc một kênh phân phối tin cậy.

**Lưu mật khẩu người dùng dưới dạng mã hóa có thể giải ngược.** Đăng nhập thông thường chỉ cần xác minh mật khẩu. Lưu bộ xác minh bằng thuật toán băm mật khẩu chuyên dụng giúp giảm hậu quả nếu cơ sở dữ liệu xác thực bị lộ. Cách này khác với việc lưu mật khẩu dịch vụ mà ứng dụng phải truy xuất để kết nối.

**Đặt key mã hóa trong cùng kho credential mà mọi ứng dụng đều có thể đọc.** Điều này có thể làm tăng số workload có khả năng lấy vật liệu khóa. Nên giới hạn quyền sử dụng key qua KMS/HSM và chỉ cho phép đúng thao tác cần thiết.

**Xoay vòng key nhưng không giữ khả năng đọc dữ liệu cũ.** Nếu dữ liệu cũ vẫn phụ thuộc vào phiên bản key trước, xóa hoặc hủy phiên bản đó có thể làm mất khả năng giải mã. Cần lập bản đồ phụ thuộc giữa ciphertext, DEK, KEK, phiên bản key và thời hạn lưu giữ.

**Ghi secret hoặc key vào log khi xử lý lỗi.** Log thường được sao chép sang nhiều hệ thống và được nhiều người truy cập. Chỉ ghi định danh secret/key, phiên bản, mã lỗi và thông tin kiểm toán cần thiết; không ghi giá trị secret, key material hoặc dữ liệu bản rõ nhạy cảm.

**Nhầm chứng thư số với private key.** Chứng thư thường có thể phân phối công khai. Private key tương ứng cần được bảo vệ riêng. Sao chép một tệp chứng thư không đồng nghĩa đã sao chép private key, dù một gói định dạng như PKCS#12 có thể chứa cả chứng thư lẫn private key được bảo vệ bằng mật khẩu.

## 8. Cách quyết định nên quản lý một giá trị như secret hay key

Khi thiết kế một hệ thống, có thể dùng trình tự sau:

1. Xác định giá trị được dùng để làm gì. Nó chứng minh quyền truy cập, hay tham gia trực tiếp vào phép toán mật mã?
2. Nếu nó là credential, xác định liệu ứng dụng có cần đọc lại giá trị gốc hay chỉ cần xác minh. Mật khẩu người dùng thường cần bộ xác minh băm; API token và mật khẩu dịch vụ thường cần được truy xuất có kiểm soát.
3. Nếu nó là key, xác định thuật toán, mục đích, chủ thể sở hữu, phiên bản, thời hạn, quyền được phép và dữ liệu phụ thuộc vào key.
4. Chọn nơi quản lý dựa trên thao tác cần thực hiện. Secret Manager phục vụ phân phối secret; KMS/HSM phục vụ quản lý key và phép toán mật mã. Nếu một dịch vụ hỗ trợ cả hai vai trò, cần đánh giá quyền truy cập và ranh giới bảo vệ cụ thể.
5. Xây dựng quy trình tạo, cấp phát, sử dụng, xoay vòng, thu hồi, sao lưu và hủy tương ứng với loại tài nguyên.
6. Kiểm tra log, bản sao lưu, biến môi trường, tệp cấu hình, bộ nhớ và pipeline triển khai để tìm nơi giá trị nhạy cảm có thể bị lộ.

Có thể phân loại nhanh như sau:

- Nếu giá trị cấp quyền truy cập khi được trình bày cho một dịch vụ, hãy xem nó là secret xác thực.
- Nếu giá trị được thuật toán mật mã dùng làm vật liệu khóa, hãy xem nó là key.
- Nếu một giá trị vừa cấp quyền vừa tham gia phép toán mật mã, áp dụng đồng thời yêu cầu bảo vệ của cả hai vai trò.
- Nếu giá trị là public key hoặc chứng thư công khai, tập trung vào xác thực nguồn gốc, tính toàn vẹn và trạng thái tin cậy.

## 9. Kết luận

Secret là khái niệm rộng về thông tin cần giữ kín; key là vật liệu có vai trò cụ thể trong thuật toán mật mã. Một key đối xứng hoặc private key thường vừa là key vừa là secret. API token và mật khẩu dịch vụ thường là secret nhưng không phải key. Public key là key nhưng không cần bí mật; nó cần được xác thực để tránh bị thay thế.

Phân biệt đúng hai khái niệm giúp chọn cách lưu trữ và kiểm soát phù hợp: băm mật khẩu người dùng để xác minh, dùng kho secret để phân phối credential, và dùng KMS/HSM để quản lý key cùng các phép toán mật mã. Khi xây dựng vòng đời riêng cho từng loại tài nguyên, hệ thống giảm nguy cơ lộ thông tin xác thực, hạn chế quyền sử dụng khóa và duy trì khả năng giải mã hoặc xác minh trong suốt thời gian dữ liệu cần được bảo vệ.


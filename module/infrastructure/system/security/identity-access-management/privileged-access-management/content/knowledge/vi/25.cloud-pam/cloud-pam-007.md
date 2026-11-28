# Cloud console session

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích các lớp phiên khi một người truy cập cloud console qua SSO hoặc federation.
- Phân biệt đăng nhập thành công với quyền hiệu lực trên tài nguyên.
- Thiết kế cấp quyền tạm thời, thời hạn phiên và kiểm tra thao tác trong phạm vi được duyệt.
- Đánh giá giới hạn của logout, thu hồi quyền, ghi hình và nhật ký cloud.
- Xây dựng quy trình đóng phiên và xử lý truy cập tồn dư có bằng chứng.

## 1. Cloud console session là gì?

**Cloud console session** là phiên làm việc cho phép người dùng tương tác với giao diện quản trị cloud sau khi hoàn thành một luồng xác thực phù hợp. Giao diện có thể dùng cookie phiên, credential tạm thời hoặc các thành phần khác tùy nền tảng và cách đăng nhập.

Trong PAM, đối tượng cần quản lý không chỉ là trang web đang mở. Cần hiểu ai khởi tạo phiên, danh tính nào được dùng tại cloud, quyền nào đang có hiệu lực, phiên có thể tạo thêm đường truy cập nào và làm sao kết thúc quyền sử dụng thực tế.

Ví dụ, một kỹ sư được duyệt sửa cấu hình dịch vụ trong môi trường thử nghiệm. Họ đăng nhập SSO, chọn account, nhận một vai trò rồi mở console. Sau đó, họ chuyển account hoặc kích hoạt quyền cao hơn. Những bước này có thể tạo các ngữ cảnh quyền khác nhau, dù người dùng vẫn thấy cùng một trình duyệt.

### 1.1. Phiên không đồng nghĩa với mật khẩu

Mật khẩu có thể chỉ tham gia lúc xác thực ban đầu. Sau đó, phiên có thể tiếp tục nhờ một bí mật phiên hoặc credential được cấp.

Vì vậy:

- Không còn biết mật khẩu không có nghĩa không còn sử dụng được phiên đã có.
- Đổi mật khẩu không tự chứng minh mọi phiên phụ thuộc đã bị kết thúc.
- Bật MFA không tự ngăn mọi trường hợp sử dụng lại bí mật phiên bị lấy cắp.
- Đóng một tab không phải bằng chứng thu hồi quyền tại cloud.

### 1.2. Phiên console không phải phiên SSH

Phiên SSH thường có một kênh tương tác tới máy đích. Cloud console là giao diện web có thể gọi nhiều dịch vụ, mở nhiều tab và tạo tác vụ nền.

Một công cụ PAM ghi nhận SSH không tự động có khả năng kiểm soát mọi cloud console. Tương tự, ghi hình trình duyệt không đồng nghĩa đã ghi mọi yêu cầu API, phiên terminal trên cloud hoặc hoạt động ngoài cửa sổ được ghi.

## 2. Các lớp phiên cần tách biệt

Một mô hình thường gặp:

~~~text
Người dùng trên thiết bị
        │
        ▼
Phiên tại nhà cung cấp danh tính (IdP)
        │  federation / SSO
        ▼
Phiên cổng truy cập hoặc hệ thống cấp quyền
        │  chọn account và vai trò
        ▼
Phiên cloud console / credential cloud
        │
        ├── Yêu cầu tới dịch vụ quản lý
        ├── Phiên dịch vụ chuyên biệt
        └── Tác vụ nền được khởi tạo
~~~

Đây là mô hình phân tích; không phải mọi nền tảng đều có đủ các lớp hoặc ghép chúng theo cùng cách.

| Lớp | Trạng thái cần biết | Câu hỏi khi kết thúc truy cập |
|---|---|---|
| Thiết bị và trình duyệt | Profile, cookie, tab, tệp tải về | Còn bí mật phiên hoặc dữ liệu cục bộ không? |
| IdP | Lần xác thực, MFA, phiên SSO | Có thể tạo một assertion hoặc token mới không? |
| Cổng truy cập/PAM | Yêu cầu, phê duyệt, khả năng cấp quyền | Còn được mở phiên hoặc kích hoạt quyền không? |
| Cloud console | Danh tính, account, vai trò và thời hạn | Phiên hiện tại còn được cloud chấp nhận không? |
| Credential hoặc phiên dẫn xuất | Token, vai trò tiếp theo, terminal hoặc kết nối dịch vụ | Có đường sử dụng nào còn hiệu lực không? |
| Tác vụ và kết quả | Job, tài nguyên tạo mới, tệp xuất | Có hậu quả hoặc công việc còn tiếp diễn không? |

Trong federation, phiên tại IdP và phiên tại dịch vụ đích được quản lý riêng; kết thúc một bên không mặc nhiên kết thúc bên kia. NIST cũng phân biệt việc quản lý phiên với token truy cập có thể tiếp tục tồn tại sau phiên xác thực. [NIST SP 800-63B-4 về session management](https://pages.nist.gov/800-63-4/sp800-63b/session/).

Phần còn lại của bài trình bày mô hình kiểm soát PAM đề xuất. Mỗi cơ chế cần được đối chiếu với khả năng thực tế của cloud, IdP và sản phẩm PAM đang dùng.

## 3. Xác thực thành công chưa xác định đủ quyền

### 3.1. Danh tính con người và danh tính thực thi

Cần liên kết ít nhất hai loại thông tin:

- Danh tính cá nhân được tổ chức xác thực.
- Principal mà cloud dùng khi đánh giá yêu cầu: người dùng, vai trò, phiên federation hoặc loại danh tính tương ứng.

Không dùng tên hiển thị hoặc tên phiên do người dùng tùy ý nhập làm bằng chứng duy nhất. Nếu thông tin liên kết danh tính có thể bị sửa, audit có thể quy nhầm người thực hiện.

### 3.2. Quyền phụ thuộc vào ngữ cảnh

Một phiên có thể bị giới hạn bởi:

- Vai trò và các chính sách quyền.
- Account, tenant, project hoặc subscription.
- Tài nguyên và điều kiện trên tài nguyên.
- Cơ chế giới hạn ở cấp tổ chức.
- Các điều kiện theo thiết bị, vị trí hoặc rủi ro nếu nền tảng hỗ trợ.
- Thời điểm và trạng thái cấp quyền tạm thời.

Không nên suy ra quyền chỉ từ nhãn “admin” hoặc “read-only”. Cần kiểm tra chính sách và hành động hiệu lực. Một danh tính có vẻ chỉ đọc vẫn có thể xem dữ liệu nhạy cảm hoặc tạo bản xuất nếu quyền được cấp quá rộng.

### 3.3. Giao diện không phải nơi thực thi duy nhất

Ẩn một nút hoặc chỉ dẫn người dùng không chuyển vai trò là biện pháp giao diện. Quyền thực tế phải được thực thi ở backend và hệ thống đích.

Nếu người dùng có thể dùng cùng credential ở một đường API khác, việc chặn thao tác trên giao diện không đủ. Cần xác định các đường gọi nào được cho phép, bị hạn chế hoặc được giám sát.

## 4. Những thời hạn thường bị nhầm với nhau

Một yêu cầu truy cập có thể liên quan nhiều mốc:

| Thời hạn | Ý nghĩa | Không tự bảo đảm |
|---|---|---|
| Hiệu lực yêu cầu | Khoảng được dùng một phê duyệt | Phiên đã cấp sẽ tự kết thúc đúng lúc |
| Thời hạn quyền JIT | Khoảng được kích hoạt quyền đặc biệt | Credential cũ mất mọi quyền ngay lập tức |
| Phiên IdP | Thời gian SSO có thể còn dùng | Phiên cloud có cùng thời hạn |
| Phiên console | Thời hạn làm việc tại cloud | Mọi phiên dẫn xuất đều hết cùng lúc |
| Credential cloud | Khoảng credential còn hiệu lực theo cơ chế cấp | Mọi tác vụ đã tạo sẽ dừng khi hết hạn |
| Inactivity timeout | Giới hạn khi không có tương tác được hệ thống tính | Có giới hạn tổng thời gian phiên phù hợp |
| Thời hạn tổng | Giới hạn tối đa trước điều kiện xác thực lại hoặc kết thúc | Tự khớp với thời hạn phê duyệt nghiệp vụ |

### 4.1. Ví dụ cửa sổ JIT và credential lệch nhau

Giả sử kế hoạch nội bộ cho phép quyền sửa cấu hình từ 09:00 đến 09:30. Lúc 09:25, người dùng nhận credential có thời hạn đến 10:25.

Các mốc này chỉ là ví dụ. Nếu hệ thống chỉ chặn việc cấp credential mới từ 09:30, credential được cấp lúc 09:25 có thể cần cơ chế bổ sung để giới hạn quyền sau 09:30.

Không thể kết luận hiệu lực thực tế chỉ bằng cách lấy thời hạn ngắn nhất trên bảng. Phải chứng minh lớp thực thi có nhận và áp dụng giới hạn đó.

### 4.2. Gia hạn phải gắn với quyết định mới

Refresh, đăng nhập lại hoặc mở tab mới có thể tạo phiên hoặc credential mới tùy triển khai. Quy trình cần xác định khi nào được gia hạn, khi nào phải phê duyệt lại và khi nào cần xác thực tương tác mới.

Một phiên SSO còn tồn tại có thể khiến người dùng không thấy màn hình nhập mật khẩu lần nữa. Nếu hành động yêu cầu xác thực mới, cần kiểm tra tín hiệu và cơ chế thực tế thay vì chỉ chuyển người dùng qua một URL đăng nhập.

### 4.3. Giảm thời hạn cấu hình không đồng nghĩa thu hồi

Khi thay đổi thời hạn mặc định hoặc tối đa, cần kiểm tra tác động lên phiên đã cấp. Không mặc định phiên cũ bị rút ngắn chỉ vì cấu hình dành cho phiên mới đã thay đổi.

## 5. Luồng truy cập console qua PAM

### Bước 1: Yêu cầu quyền cho một nhiệm vụ

Yêu cầu nên nêu:

- Người dùng và đơn vị chịu trách nhiệm.
- Account, tenant hoặc môi trường đích.
- Vai trò và tập hành động cần thiết.
- Tài nguyên hoặc phạm vi công việc.
- Thời hạn và lý do.
- Mã thay đổi hoặc sự cố liên quan.
- Điều kiện xác minh và đóng quyền.

Không yêu cầu quyền quản trị toàn bộ chỉ vì một thao tác thiếu quyền. Cần chẩn đoán quyền thiếu và cấp phạm vi phù hợp.

### Bước 2: Phê duyệt đúng phạm vi

Người duyệt cần biết hậu quả của quyền, không chỉ biết tên vai trò. Với hành động nhạy cảm, có thể cần phê duyệt độc lập hoặc kế hoạch thao tác cụ thể.

Phê duyệt quyền đăng nhập console không tự cho phép mọi dangerous operation. Các thao tác như xuất dữ liệu lớn, xóa tài nguyên hoặc thay chính sách bảo mật có thể cần kiểm soát riêng.

### Bước 3: Xác thực và đánh giá điều kiện

Xác thực danh tính cá nhân, kiểm tra MFA và điều kiện truy cập cần thiết theo thiết kế. Đánh giá thiết bị hoặc mức rủi ro nếu hệ thống hỗ trợ.

MFA và phê duyệt giải quyết các câu hỏi khác nhau. Một bên tăng độ tin cậy về người xác thực; bên kia xác định công việc được cho phép.

### Bước 4: Cấp quyền hoặc phiên có giới hạn

Ưu tiên danh tính cá nhân và credential có thời hạn thay vì phân phối một mật khẩu quản trị chung. Gắn mã liên kết không chứa secret với lần cấp nếu nền tảng cho phép.

Giới hạn vai trò, môi trường và cửa sổ truy cập. Kiểm tra cấu hình cấp thực tế thay vì chỉ ghi thời hạn mong muốn trong ticket.

### Bước 5: Kiểm tra ngữ cảnh trước thao tác

Người dùng cần nhận biết rõ account, vai trò và môi trường hiện tại. Có thể dùng profile, nhãn, màu cảnh báo hoặc quy ước đặt tên để giảm nhầm lẫn.

Những dấu hiệu đó hỗ trợ người dùng; chúng không thay thế kiểm tra quyền. Account đích phải được đối chiếu bằng định danh ổn định, đặc biệt khi tên tương tự nhau.

### Bước 6: Theo dõi hành động và sai lệch

Đối chiếu hoạt động với nhiệm vụ. Các sự kiện ngoài phạm vi, thay đổi quyền hoặc tạo đường truy cập mới cần được đánh giá.

Không coi một phiên được duyệt là vùng tin cậy trong suốt thời gian tồn tại. Thiết bị có thể bị chiếm hoặc người dùng có thể thao tác sai sau khi đăng nhập.

### Bước 7: Kết thúc và xác minh

Kết thúc khả năng cấp quyền mới, xử lý phiên và credential đang có theo cơ chế tương ứng. Kiểm tra các phiên dẫn xuất và tác vụ quan trọng đã tạo.

Chỉ đóng hồ sơ khi có đủ bằng chứng cho trạng thái cuối hoặc có ngoại lệ rõ ràng với người chịu trách nhiệm.

## 6. Điều gì được kiểm soát bởi từng kiến trúc?

### 6.1. Truy cập trực tiếp bằng federation và quyền tạm thời

Người dùng được cấp quyền rồi truy cập console trực tiếp. Mô hình này có thể cung cấp liên kết danh tính tốt và giảm credential dài hạn.

Tuy nhiên, mức quan sát phụ thuộc nhật ký IdP, cơ chế cấp quyền và audit cloud. Không tự có video màn hình hoặc khả năng chặn từng cú nhấp.

Cần đảm bảo việc mở phiên qua đường trực tiếp vẫn chịu các giới hạn quyền dự kiến.

### 6.2. Trình duyệt từ xa hoặc môi trường phiên được quản lý

Người dùng làm việc qua một môi trường trình duyệt do tổ chức kiểm soát. Tùy sản phẩm và cấu hình, có thể hạn chế tải tệp, clipboard, chuyển hướng hoặc lưu trữ profile.

Các giới hạn phải được kiểm thử. Không giả định chúng chặn được mọi cách đưa dữ liệu ra ngoài hoặc mọi đường API.

Đóng trình duyệt từ xa có thể chấm dứt kênh tương tác đó, nhưng không tự thu hồi credential hoặc phiên đã được cấp ở bên ngoài phạm vi môi trường này.

### 6.3. Proxy hoặc broker mở phiên

Một broker có thể kiểm tra phê duyệt, cấp liên kết vào console và ghi nhận lần khởi tạo. Giá trị chính là kiểm soát đường vào và liên kết danh tính.

Nhưng nếu quyền vẫn cho phép mở một phiên khác mà không qua broker, việc chỉ theo dõi nút “Launch console” không bao phủ toàn bộ truy cập. Cần kiểm tra các đường thay thế và ngoại lệ.

### 6.4. So sánh theo năng lực thực tế

| Năng lực | Cần xác minh |
|---|---|
| Kiểm soát mở phiên | Các đường đăng nhập khác có bị bao phủ không? |
| Giới hạn quyền | Hệ thống đích có thực thi theo tài nguyên và hành động không? |
| Ghi hình | Những cửa sổ, tab hoặc terminal nào được ghi? |
| Ngăn tải dữ liệu | Có áp dụng với download, xuất dữ liệu và đường truy cập khác không? |
| Dừng phiên | Chỉ đóng kênh trình duyệt hay có thu hồi tại cloud? |
| Liên kết audit | Có nối được người, yêu cầu, vai trò và hành động không? |

Tên tính năng trên giao diện sản phẩm chưa đủ để trả lời những câu hỏi này.

## 7. Bảo vệ thiết bị và bí mật phiên

### 7.1. Bí mật phiên cần được bảo vệ như credential

Không sao chép cookie, token hoặc liên kết đăng nhập dùng một lần vào chat, ticket, bản ghi màn hình hay kho mã nguồn.

Tệp chẩn đoán trình duyệt có thể chứa header, tham số URL hoặc nội dung phản hồi nhạy cảm. Nếu cần thu thập, giới hạn quyền truy cập và làm sạch theo quy trình trước khi chia sẻ.

Không dùng thao tác xuất token thật làm bài kiểm thử thông thường.

### 7.2. Tách profile làm việc theo mục đích

Profile riêng cho quản trị giúp giảm nhầm account và hạn chế trộn dữ liệu với hoạt động cá nhân. Thiết bị quản trị nên được tổ chức kiểm soát, cập nhật và hạn chế phần mở rộng không cần thiết.

Một profile riêng không bảo vệ được trước mọi mã độc trên cùng thiết bị. Nếu hệ điều hành bị xâm nhập, dữ liệu hiển thị và khả năng điều khiển phiên vẫn có thể bị ảnh hưởng.

### 7.3. Trình duyệt ẩn danh có giới hạn

Cửa sổ riêng tư có thể giảm một số dữ liệu lưu lại theo cơ chế của trình duyệt, nhưng không tạo ra quyền hẹp hơn tại cloud và không thay thế thiết bị đáng tin cậy.

Đóng cửa sổ riêng tư cũng không chứng minh mọi token, tác vụ hoặc dữ liệu được tải về đã bị thu hồi.

### 7.4. Không dùng dấu hiệu mạng làm danh tính duy nhất

IP, vị trí và user agent là tín hiệu hỗ trợ. Nhiều người có thể dùng chung địa chỉ ra mạng; một người có thể đổi mạng trong phiên.

Khi điều tra, cần kết hợp định danh phiên, nguồn cấp quyền, thiết bị và audit hành động. Tránh quy kết chỉ dựa vào địa chỉ IP.

## 8. Logout, thu hồi quyền và chặn cấp mới

Ba việc sau có thể cần các cơ chế khác nhau:

1. Chấm dứt một phiên tương tác.
2. Ngăn cấp phiên hoặc credential mới.
3. Làm credential hiện tại không còn thực hiện được hành động.

| Thao tác | Tác dụng dự kiến | Điều vẫn phải xác minh |
|---|---|---|
| Đóng tab | Dừng tương tác ở tab đó | Phiên phía máy chủ và tab khác |
| Logout console | Kết thúc theo cơ chế logout của console | Phiên IdP, credential và phiên liên quan |
| Logout IdP | Kết thúc hoặc xử lý phiên tại IdP | Phiên dịch vụ đích đã được tạo |
| Xóa khả năng kích hoạt JIT | Ngăn cấp quyền theo đường đó | Quyền hoặc credential đã cấp trước |
| Chặn trust hoặc cấp quyền mới | Hạn chế tạo phiên tiếp theo theo cơ chế tương ứng | Phiên đang tồn tại |
| Thu hồi theo cơ chế cloud | Từ chối quyền của tập phiên mục tiêu | Phạm vi, độ trễ, phiên khác và tác động |
| Cô lập thiết bị | Giảm khả năng tiếp tục dùng thiết bị | Credential đã bị sao chép sang nơi khác |

Bảng là mô hình kiểm tra, không phải bảo đảm hành vi của một sản phẩm cụ thể.

### 8.1. Ví dụ AWS IAM role

Với IAM role phù hợp, AWS có cơ chế thu hồi quyền của các phiên được cấp trước một mốc bằng chính sách từ chối. Tác động có thể bao gồm nhiều người cùng dùng role, và không mặc nhiên ngăn việc nhận phiên mới sau mốc đó. Các role do IAM Identity Center quản lý có đường xử lý tương ứng riêng. [Tài liệu AWS về thu hồi phiên IAM role](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html).

Điều cần rút ra cho runbook là phải xác định loại phiên trước khi chọn thao tác. Không áp dụng cùng một nút “revoke” cho mọi danh tính và không bỏ qua ảnh hưởng tới người dùng hoặc workload khác.

### 8.2. Kiểm tra sau thu hồi

Một phép kiểm tra phù hợp cần chứng minh yêu cầu mới với ngữ cảnh phiên mục tiêu không còn thực hiện được hành động cần chặn, bằng cách an toàn và được phép.

Không kết luận thất bại chỉ vì trang vẫn hiển thị dữ liệu đã tải trước đó. Ngược lại, một lỗi giao diện không đủ chứng minh mọi API liên quan đều bị từ chối.

Cần xác định phạm vi kiểm tra: quản lý tài nguyên, đọc dữ liệu, chuyển vai trò, terminal trên cloud hoặc phiên dịch vụ liên quan tùy rủi ro.

### 8.3. Quyền phát sinh không tự biến mất

Trong thời gian có quyền, người dùng có thể đã tạo danh tính mới, thay trust, tạo credential, thay cấu hình mạng hoặc khởi tạo công việc.

Thu hồi phiên ban đầu không tự xóa những thay đổi này. Một quy trình ứng phó phải kiểm tra cả truy cập phát sinh và hậu quả đã được tạo.

## 9. Nhiều tab, nhiều account và phiên dẫn xuất

### 9.1. Nhiều tab có thể dùng chung hoặc khác ngữ cảnh

Một số tab có thể chia sẻ trạng thái đăng nhập; tab khác có thể mở phiên riêng hoặc giữ nội dung cũ. Hành vi phụ thuộc console và trình duyệt.

Người vận hành cần kiểm tra danh tính và account tại nơi thực hiện hành động, không suy ra từ tab đầu tiên đã mở.

### 9.2. Chuyển vai trò cần được kiểm soát

Quyền mở console ở một account không nên tự dẫn tới quyền quản trị account khác ngoài phạm vi. Rà soát khả năng chuyển vai trò hoặc thiết lập quan hệ tin cậy liên quan.

Audit cần liên kết được chuỗi chuyển quyền khi nền tảng cung cấp dữ liệu phù hợp. Không chỉ ghi vai trò đầu tiên rồi bỏ qua những vai trò tiếp theo.

### 9.3. Cloud shell, terminal và kết nối dịch vụ

Một console có thể mở terminal hoặc môi trường phát triển được quản lý. Môi trường đó có thể có phiên, credential, tệp hoặc tiến trình riêng.

Khi đánh giá đóng truy cập, cần xác định:

- Terminal có còn hoạt động không?
- Credential được cấp hoặc cache ở đâu?
- Có tiến trình nền nào đang chạy không?
- Có tệp nhạy cảm đã tạo hoặc tải xuống không?
- Cơ chế kết thúc terminal có khác logout console không?

Không coi mọi cloud shell đều có cùng thiết kế credential. Phải kiểm tra dịch vụ cụ thể.

### 9.4. Tác vụ nền có vòng đời riêng

Một lệnh tạo bản sao, xuất dữ liệu hoặc triển khai có thể tiếp tục sau khi người dùng đăng xuất. Việc dừng hay cho chạy tiếp phải theo mục đích nghiệp vụ và mức rủi ro.

Dừng phiên không thay thế quyết định xử lý tác vụ, và dừng tác vụ cũng không tự thu hồi dữ liệu đã xuất.

## 10. Nhật ký cloud và ghi hình bổ sung cho nhau

### 10.1. Nhật ký đăng nhập trả lời một phần câu hỏi

Trong AWS, CloudTrail có sự kiện đăng nhập console, với cấu trúc và vị trí ghi nhận phụ thuộc luồng đăng nhập. Không nên giả định mọi sự kiện ConsoleLogin đều xuất hiện ở một Region cố định. [Tài liệu AWS về console sign-in events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-aws-console-sign-in-events.html).

Về thiết kế giám sát, cần kiểm thử những đường đăng nhập thực sự dùng trong tổ chức. Một rule đúng với tài khoản thử nghiệm chưa chắc bao phủ root, federation và mọi luồng SSO khác.

### 10.2. Đăng nhập thành công không phải bằng chứng hoàn tất công việc

Cần kết hợp sự kiện đăng nhập với hành động cloud, thay đổi quyền và kết quả thực tế. Những câu hỏi khác nhau cần nguồn bằng chứng khác nhau:

| Câu hỏi | Nguồn bằng chứng phù hợp |
|---|---|
| Ai được phê duyệt? | Hệ thống yêu cầu và phê duyệt |
| Ai xác thực và bằng cách nào? | IdP hoặc nguồn xác thực tương ứng |
| Phiên nào được cấp? | Nguồn cấp quyền, federation hoặc audit cloud |
| Hành động nào được chấp nhận? | Nhật ký dịch vụ và sự kiện quyền |
| Người dùng đã thấy gì trên màn hình? | Ghi hình trong phạm vi được ghi |
| Trạng thái tài nguyên cuối cùng? | Truy vấn hoặc kiểm tra kết quả |
| Đã đóng mọi quyền liên quan chưa? | Bằng chứng thu hồi và kiểm tra sau thu hồi |

### 10.3. Ghi hình không thay audit hành động

Video giúp hiểu trình tự tương tác nhưng có thể bỏ sót request nền, tab khác hoặc thao tác qua API. Nó cũng có thể ghi dữ liệu nhạy cảm mà nhật ký metadata không cần lưu.

Cần bảo vệ quyền xem, thời hạn lưu và khả năng xuất video. Không làm lộ secret để đạt mục tiêu “ghi đủ”.

### 10.4. Audit cần đủ độ bao phủ

Không mặc định một loại nhật ký ghi mọi hành động dữ liệu và quản trị. Cần xác định dịch vụ, loại sự kiện và cấu hình ghi nhận thực tế.

Kiểm tra cả độ trễ đến nơi nhận, mất sự kiện, quyền sửa cấu hình log và đồng bộ thời gian. Nếu không thể liên kết được mốc phê duyệt với hành động, hồ sơ kiểm toán sẽ khó kết luận.

## 11. Tình huống: hết quyền JIT nhưng phiên vẫn cần xử lý

Một kỹ sư được duyệt sửa cấu hình trong 30 phút. Hệ thống dùng SSO và vai trò tạm thời. Trong cửa sổ đó, kỹ sư mở console, mở terminal trên cloud và tạo một tác vụ cập nhật.

### 11.1. Báo cáo ban đầu chưa đủ

> Quyền JIT đã hết hạn. Cổng PAM đã đóng yêu cầu. Không còn quyền quản trị.

Báo cáo bỏ qua:

- Phiên console đã được tạo trước lúc hết hạn.
- Credential đang dùng và khả năng nhận credential mới.
- Phiên terminal có thể có vòng đời riêng.
- Tác vụ cập nhật vẫn đang chạy.
- Thay đổi quyền hoặc credential có thể được tạo trong thời gian làm việc.

### 11.2. Runbook phù hợp hơn

1. Ngăn cấp hoặc gia hạn quyền ngoài cửa sổ được phép.
2. Xác định phiên console, vai trò và các credential liên quan.
3. Áp dụng cơ chế kết thúc hoặc thu hồi đúng loại phiên.
4. Xác minh yêu cầu mới bị từ chối trong phạm vi cần chặn.
5. Xử lý terminal và tiến trình liên quan theo thiết kế.
6. Kiểm tra trạng thái tác vụ cập nhật, không dừng mù quáng nếu có thể gây hỏng trạng thái.
7. Đối chiếu thay đổi quyền, credential và tài nguyên với kế hoạch.
8. Ghi kết quả và ngoại lệ còn tồn tại.

Không cần và không nên lấy giá trị token thật làm bằng chứng. Dùng metadata, mã liên kết và kết quả kiểm tra được phép.

### 11.3. Báo cáo phản ánh đúng kết quả

> Đã ngăn cấp quyền mới cho yêu cầu. Quyền của các phiên cloud trong phạm vi đã được xử lý và kiểm tra từ chối yêu cầu mới. Terminal đã kết thúc. Tác vụ cập nhật tiếp tục theo quyết định thay đổi và có owner theo dõi. Chưa đóng hồ sơ cho tới khi xác minh trạng thái tài nguyên cuối cùng.

Nếu một lớp chưa kiểm tra được, báo cáo cần nêu rõ lớp đó, phạm vi rủi ro và thời hạn xử lý.

## 12. Ứng phó khi nghi phiên bị chiếm

### 12.1. Xác định phạm vi nghi ngờ

Thu thập metadata cần thiết:

- Người dùng, account, vai trò và mã phiên.
- Thời điểm bắt đầu và tín hiệu nghi ngờ.
- Thiết bị, địa chỉ mạng và luồng đăng nhập.
- Những quyền đã kích hoạt.
- Các phiên hoặc tác vụ dẫn xuất.
- Những hành động hậu quả cao đã được ghi nhận.

Không sao chép token vào hồ sơ điều tra thông thường.

### 12.2. Chặn cả tái cấp và truy cập hiện tại

Tùy tình huống, cần xử lý nguồn xác thực, khả năng cấp phiên mới, credential đã cấp và thiết bị bị nghi xâm nhập.

Nếu chỉ thu hồi phiên cloud nhưng IdP hoặc thiết bị vẫn cho phép tạo phiên mới, kẻ tấn công có thể quay lại qua cùng đường. Nếu chỉ khóa IdP, phiên cloud đã tồn tại có thể vẫn cần xử lý riêng.

### 12.3. Đánh giá tác động của biện pháp thu hồi

Thu hồi toàn bộ phiên của một vai trò có thể ảnh hưởng người dùng và workload khác. Cần chọn phạm vi phù hợp với khả năng nền tảng và mức khẩn cấp.

Không trì hoãn xử lý chỉ vì chưa có biện pháp hoàn hảo, nhưng phải ghi rõ quyết định, phạm vi ảnh hưởng và phần chưa xác minh.

### 12.4. Tìm đường duy trì quyền và hậu quả

Rà soát danh tính mới, credential mới, quan hệ tin cậy, thay đổi chính sách, cấu hình audit và dữ liệu đã xuất.

Khôi phục phiên sạch không đồng nghĩa môi trường đã sạch. Cần đối soát kết quả theo kế hoạch ứng phó sự cố.

## 13. Tiêu chí kiểm thử một triển khai

Các kiểm thử nên dùng môi trường và danh tính được phép, tránh gây hậu quả lên dữ liệu sản xuất.

| Tình huống | Kết quả cần quan sát |
|---|---|
| Mở console trước khi được duyệt | Không có quyền ngoài chính sách |
| Mở console sau khi được duyệt | Đúng người, account, vai trò và thời hạn |
| Đổi account hoặc vai trò | Chỉ thành công trong phạm vi cho phép |
| Quyền hết hạn khi phiên còn mở | Hành vi thực tế khớp thiết kế |
| Logout IdP nhưng console còn mở | Ghi nhận được trạng thái từng lớp |
| Thu hồi phiên | Yêu cầu mới bị xử lý đúng phạm vi |
| Mở nhiều tab hoặc profile | Không nhầm danh tính và account |
| Mở terminal hoặc phiên dịch vụ | Có kiểm kê vòng đời và cách kết thúc |
| Tạo tác vụ nền rồi logout | Có owner và trạng thái tác vụ rõ ràng |
| Dùng đường truy cập ngoài broker | Được kiểm soát hoặc ghi nhận là ngoại lệ |
| Mất nguồn audit | Có hành vi và cảnh báo theo chính sách |
| Thiết bị thay đổi mức tin cậy | Phản ứng phù hợp với năng lực triển khai |

Một kiểm thử không chỉ hỏi màn hình có đóng không. Nó cần xác định còn hành động nào có thể được chấp nhận, qua đường nào và trong bao lâu.

## 14. Chỉ số vận hành có ý nghĩa

Có thể theo dõi:

- Số phiên đặc quyền gắn được với yêu cầu và danh tính cá nhân.
- Số phiên hoặc quyền được cấp vượt thời hạn mong muốn.
- Thời gian từ quyết định thu hồi đến lúc kiểm tra quyền bị từ chối.
- Số phiên dẫn xuất chưa được kiểm kê.
- Số yêu cầu đóng nhưng còn tác vụ hoặc ngoại lệ mở.
- Tỷ lệ kiểm thử thành công của từng luồng đăng nhập.
- Số hành động ngoài phạm vi trong phiên được duyệt.
- Tỷ lệ sự kiện đến nơi nhận trong độ trễ yêu cầu.

Không nên dùng riêng số phiên “đã logout” để kết luận hiệu quả PAM. Chỉ số cần phản ánh quyền thực tế và khả năng chứng minh kết thúc truy cập.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
|---|---|---|
| Dùng tài khoản console chung | Khó quy trách nhiệm | Dùng danh tính cá nhân và liên kết phiên |
| Coi SSO logout là logout mọi nơi | Bỏ sót phiên dịch vụ đích | Kiểm tra vòng đời từng lớp |
| Coi MFA bảo vệ mọi thời điểm của phiên | Bỏ sót rủi ro token bị lấy cắp | Bảo vệ thiết bị và bí mật phiên |
| Chỉ giới hạn nút mở console | Đường API hoặc đăng nhập khác vẫn tồn tại | Kiểm kê đường truy cập thay thế |
| Cấp vai trò rộng cho nhiệm vụ hẹp | Tăng tác động của sai sót | Giới hạn hành động và tài nguyên |
| Hết JIT nhưng không kiểm tra phiên đã cấp | Quyền có thể còn tồn dư | Đồng bộ hoặc xử lý bằng cơ chế thực thi |
| Chỉ ghi video | Bỏ sót request và tác vụ ngoài màn hình | Kết hợp audit cloud và xác minh trạng thái |
| Chỉ xem sự kiện đăng nhập | Không biết hành động và hậu quả | Liên kết sự kiện thực thi |
| Thu hồi cả vai trò mà không xét người khác | Gián đoạn ngoài phạm vi | Đánh giá phạm vi và runbook ứng phó |
| Log cookie hoặc token | Tạo nguồn lộ credential | Lưu metadata thay giá trị bí mật |
| Đóng phiên rồi quên terminal và job | Còn hoạt động ngoài cửa sổ | Kiểm kê phiên dẫn xuất và công việc nền |
| Tưởng thu hồi phiên xóa được dữ liệu đã xuất | Đánh giá thiếu hậu quả | Xử lý dữ liệu và quyền phát sinh riêng |

## 16. Thực hành

### Bài tập 1: Vẽ vòng đời phiên

Một nhân viên đăng nhập IdP, mở cổng truy cập, vào hai account cloud rồi mở một terminal.

Hãy vẽ các lớp phiên có thể tồn tại. Với mỗi lớp, ghi nguồn cấp, thời hạn, cách ngăn cấp mới, cách xử lý phiên cũ và bằng chứng kết thúc.

### Bài tập 2: Sửa thiết kế JIT

Một quyền JIT có hiệu lực 20 phút nhưng credential cloud được cấp gần cuối cửa sổ có thời hạn dài hơn.

Hãy đề xuất cách ràng buộc cửa sổ nghiệp vụ với quyền thực tế. Nêu rõ cơ chế nào được thực thi tại đích, cơ chế nào chỉ là quy trình và trường hợp cần ngoại lệ.

### Bài tập 3: Phân tích giới hạn ghi hình

Nhà cung cấp PAM cho phép ghi hình trình duyệt từ xa. Người dùng vẫn có quyền mở terminal và xuất dữ liệu ra một nơi lưu trữ cloud.

Hãy xác định những hoạt động có thể nằm ngoài video, những nguồn audit cần bổ sung và cách kiểm thử khả năng dừng truy cập.

### Bài tập 4: Xác minh sau thu hồi

Sau khi xử lý một phiên nghi bị chiếm, trang console vẫn hiển thị tài nguyên nhưng thao tác làm mới bị từ chối.

Hãy giải thích vì sao nội dung cũ chưa chứng minh phiên còn quyền. Thiết kế thêm những kiểm tra an toàn để đánh giá API, phiên dẫn xuất, khả năng cấp mới và thay đổi quyền đã phát sinh.

### Bài tập 5: Viết báo cáo đóng phiên

Báo cáo ban đầu chỉ ghi “đã logout và đóng ticket”.

Hãy bổ sung trạng thái IdP, khả năng nhận quyền mới, phiên cloud, credential, terminal, tác vụ nền và bằng chứng đối chiếu. Nếu một lớp chưa xác minh được, chỉ rõ owner và hạn xử lý.

## 17. Điểm cần ghi nhớ

Cloud console session là một phần của chuỗi xác thực, cấp quyền và thực thi trên nhiều lớp. Một phiên được duyệt phải gắn với người cụ thể, phạm vi quyền cụ thể và cách kết thúc có thể kiểm chứng.

Logout, hết hạn JIT và thu hồi credential không phải cùng một thao tác. PAM cần kiểm soát cả đường cấp mới lẫn truy cập đã tồn tại, kết hợp audit với bằng chứng phiên và xác minh hậu quả còn tiếp diễn sau khi người dùng rời console.

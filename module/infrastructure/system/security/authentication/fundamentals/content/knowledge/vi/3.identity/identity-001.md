# Digital identity (Danh tính số)

> **Chương:** Identity  
> **Phạm vi:** SECURITY_AUTHENTICATION_FUNDAMENTALS — những nguyên lý về danh tính và xác thực, từ credential, mật khẩu, MFA, passkey, chứng chỉ đến phiên, token, liên kết danh tính và khôi phục tài khoản.  
> **Câu hỏi trung tâm:** Hệ thống đang nói tới **ai hoặc thực thể nào**, dựa trên thông tin nào, trong phạm vi tin cậy nào và bằng cách nào một chủ thể chứng minh được quyền đại diện cho danh tính đó?

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Định nghĩa **danh tính số (digital identity)** và phân biệt nó với con người ngoài đời, định danh, tài khoản, credential, phiên đăng nhập và quyền truy cập.
2. Mô tả các thành phần của một danh tính số: chủ thể, mã định danh, thuộc tính, bằng chứng gắn kết, credential và quan hệ tin cậy.
3. Giải thích vì sao email, số điện thoại, tên hiển thị và địa chỉ IP không nên được xem như định danh bất biến hay bằng chứng xác thực.
4. Mô hình hóa vòng đời danh tính: đăng ký, kiểm chứng thuộc tính, gắn credential, sử dụng, cập nhật, liên kết, khôi phục, đình chỉ và kết thúc.
5. Nhận diện rủi ro mạo danh, chiếm tài khoản, nhầm lẫn danh tính, gộp sai tài khoản và lộ thông tin cá nhân ở các ranh giới hệ thống.
6. Áp dụng mô hình danh tính số vào luồng xác thực người dùng, đăng nhập liên kết và xác thực dịch vụ.

## 1. Danh tính số là gì?

**Danh tính số (digital identity)** là tập hợp các thông tin và quan hệ mà một hệ thống sử dụng để **nhận biết, phân biệt và xử lý một chủ thể trong một ngữ cảnh số**. Chủ thể (subject) có thể là người, tổ chức, thiết bị, phần mềm hoặc dịch vụ.

Một danh tính số thường có:

- **Mã định danh (identifier):** dấu hiệu để tham chiếu một chủ thể, chẳng hạn mã nội bộ do hệ thống cấp.
- **Thuộc tính (attributes):** những thông tin mô tả chủ thể, chẳng hạn tên hiển thị, email đã xác minh, vai trò công việc hoặc trạng thái tài khoản.
- **Quan hệ và nguồn thông tin:** tổ chức nào cấp danh tính, hệ thống nào chấp nhận thông tin, thuộc tính nào do ai xác minh.
- **Phương thức chứng minh quyền sử dụng danh tính:** credential hoặc authenticator đã được đăng ký, ví dụ mật khẩu, passkey hay khóa riêng gắn với chứng chỉ.
- **Trạng thái vòng đời:** danh tính còn hoạt động, bị khóa, đã rút quyền hay đã đóng.

Danh tính số **không đồng nghĩa** với một danh tính pháp lý đã kiểm chứng. Diễn đàn có thể dùng danh tính biệt danh; ứng dụng nội bộ có thể dùng tài khoản nhân viên; một máy chủ có thể có danh tính dịch vụ. Mức kiểm chứng cần thiết phụ thuộc mục đích và rủi ro nghiệp vụ.

### Một người có thể có nhiều danh tính số

Giả sử Lan có ba ngữ cảnh độc lập:

| Ngữ cảnh | Danh tính được dùng | Hệ thống cần tin điều gì? |
| --- | --- | --- |
| Diễn đàn lập trình | Biệt danh và mã thành viên do diễn đàn cấp | Đây là cùng tài khoản đã đăng ký trước đó, không nhất thiết là danh tính pháp lý của Lan. |
| Hệ thống nhân sự | Mã nhân viên và thuộc tính từ bộ phận nhân sự | Chủ thể gắn với hồ sơ nhân viên hợp lệ, có trạng thái làm việc phù hợp. |
| Dịch vụ ngân hàng | Hồ sơ khách hàng đã qua mức kiểm chứng cần thiết | Chủ thể có quyền truy cập tài khoản cụ thể và đáp ứng điều kiện cho giao dịch nhạy cảm. |

Ba danh tính có thể thuộc cùng một người nhưng **không tự nhiên được gộp**. Một hệ thống cũng không nên suy ra rằng hai hồ sơ là cùng một người chỉ vì trùng tên hoặc email. Việc liên kết danh tính cần có mục đích rõ ràng, bằng chứng phù hợp và quyền xử lý dữ liệu tương ứng.

Tương tự, **một danh tính dịch vụ** có thể đại diện cho tiến trình tự động "dịch vụ lập hóa đơn" trong môi trường sản xuất, không đại diện cho nhân viên trực tiếp sử dụng máy chủ.

## 2. Tách các khái niệm thường bị đánh đồng

Các khái niệm dưới đây liên quan chặt chẽ nhưng giải quyết những câu hỏi khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Chủ thể (subject)** | Thực thể mà danh tính mô tả. | Một nhân viên, ứng dụng hoặc thiết bị. |
| **Định danh (identifier)** | Giá trị dùng để phân biệt hoặc tham chiếu chủ thể trong một phạm vi. | ID nội bộ 73a…, cặp mã nhà phát hành và mã chủ thể. |
| **Danh tính số (digital identity)** | Bản biểu diễn của chủ thể trong ngữ cảnh, gồm định danh, thuộc tính, liên kết và trạng thái. | Hồ sơ nhân viên số do doanh nghiệp quản lý. |
| **Tài khoản (account)** | Bản ghi và các chức năng mà một dịch vụ cung cấp cho người dùng/chủ thể. | Tài khoản trên ứng dụng quản lý dự án. |
| **Credential** | Thông tin/bằng chứng được dùng để chứng minh quyền sử dụng một danh tính. | Mật khẩu, khóa riêng của passkey, khóa riêng tương ứng chứng chỉ. |
| **Authenticator** | Phương tiện hoặc cơ chế sử dụng yếu tố xác thực để tạo bằng chứng. | Khóa bảo mật vật lý, ứng dụng TOTP, thiết bị giữ passkey. |
| **Xác thực (authentication)** | Kiểm tra bằng chứng chủ thể trình để xác lập danh tính theo chính sách. | Máy chủ xác minh phản hồi thử thách của passkey. |
| **Phân quyền (authorization)** | Quyết định hành động nào được phép trên tài nguyên cụ thể. | Chỉ được sửa dự án thuộc nhóm phụ trách. |
| **Phiên / token** | Cơ chế mang hoặc tham chiếu kết quả đăng nhập và ngữ cảnh sử dụng sau xác thực. | Cookie phiên hoặc access token dùng với API. |

**Tên hiển thị không phải mã định danh đáng tin cậy; mã định danh không phải credential; credential không phải quyền; xác thực thành công không phải giấy phép truy cập mọi tài nguyên.**

Ví dụ, một người đổi tên hiển thị từ "lan.dev" thành "lan.tech". Hệ thống vẫn cần biết đây là cùng bản ghi tài khoản nhờ mã định danh ổn định. Việc đổi tên không nên tạo ra một danh tính mới hoặc làm mất dữ liệu sở hữu.

## 3. Mô hình thành phần và ranh giới của danh tính số

Một mô hình đơn giản:

~~~mermaid
flowchart LR
    S["Chủ thể\nNgười / dịch vụ / thiết bị"]
    D["Hồ sơ danh tính số\nID nội bộ, thuộc tính, trạng thái"]
    C["Credential / authenticator\nMật khẩu, passkey, khóa riêng"]
    I["Nhà phát hành / IdP\nXác lập và quản lý danh tính"]
    A["Ứng dụng / API\nDựa vào bằng chứng để phục vụ"]
    S -->|"Được biểu diễn trong ngữ cảnh"| D
    D -->|"Gắn phương thức xác thực"| C
    I -->|"Cấp / xác minh thuộc tính hoặc danh tính"| D
    C -->|"Chứng minh quyền kiểm soát"| A
    I -->|"Khẳng định danh tính theo giao thức tin cậy"| A
    A -->|"Kiểm tra quyền và trạng thái"| D
~~~

Sơ đồ mang tính khái niệm: ở một hệ thống, ứng dụng có thể vừa quản lý danh tính vừa trực tiếp xác thực; ở hệ thống dùng SSO, Identity Provider (IdP) xác thực và ứng dụng dựa vào một khẳng định danh tính được kiểm chứng.

Điểm quan trọng là **ai phát biểu một thông tin** và **ai có thẩm quyền kiểm chứng thông tin đó**. Ví dụ:

- Trình duyệt tự gửi trường "role: admin" là dữ liệu **do client tự khai**.
- Hệ thống nhân sự cấp thuộc tính phòng ban cho nhân viên là thông tin từ **nguồn quản trị**.
- IdP phát hành một token hợp lệ cho ứng dụng là thông tin được **xác nhận theo quan hệ tin cậy và giao thức**.
- Chính ứng dụng vẫn phải kiểm tra người dùng có quyền sửa **đối tượng cụ thể** hay không.

Ranh giới tin cậy nằm giữa client và máy chủ, giữa ứng dụng và IdP, giữa các dịch vụ nội bộ, cũng như giữa một nguồn thuộc tính và nơi ra quyết định. Không có dữ liệu nào trở thành đáng tin chỉ vì nó được đặt trong JSON, header HTTP hoặc tên biến có vẻ đúng.

## 4. Mã định danh: ổn định, duy nhất và có phạm vi

### 4.1 Một mã chỉ có nghĩa trong phạm vi của nó

Hai công ty có thể cùng dùng mã nhân viên "1001" mà không chỉ cùng một người. Một mã định danh thường cần đi kèm **phạm vi cấp phát** hoặc **nhà phát hành (issuer)**.

Ví dụ trong đăng nhập OpenID Connect (OIDC), cặp:

~~~text
issuer  = https://id.company-a.example
subject = opaque-subject-88
~~~

đại diện cho một chủ thể trong không gian định danh của nhà phát hành đó. Cùng một chuỗi subject do nhà phát hành khác cấp **không mặc nhiên** là cùng danh tính.

### 4.2 Không dùng thông tin dễ đổi làm khóa duy nhất cho danh tính

| Giá trị | Có thể thay đổi hoặc tái sử dụng? | Cách dùng hợp lý |
| --- | --- | --- |
| Mã nội bộ sinh ngẫu nhiên, quản lý ổn định | Được thiết kế để không tái cấp trong phạm vi hệ thống | Khóa tham chiếu nội bộ cho chủ thể/tài khoản. |
| Email | Có thể đổi, bị mất quyền kiểm soát hoặc được cấp lại | Kênh liên hệ, tên đăng nhập tùy chọn; phải theo dõi trạng thái xác minh. |
| Số điện thoại | Có thể được cấp lại hoặc bị chuyển quyền sử dụng | Kênh liên hệ hoặc yếu tố phụ theo rủi ro; không phải định danh bất biến. |
| Tên hiển thị | Dễ thay đổi, có thể trùng | Hiển thị trên giao diện, không nên dùng để quyết định quyền. |
| Địa chỉ IP | Thay đổi, có thể dùng chung qua NAT/proxy | Tín hiệu ngữ cảnh và phát hiện bất thường; không chứng minh con người cụ thể. |
| Subject do IdP cấp | Có nghĩa trong phạm vi issuer và quy tắc của IdP | Ánh xạ từ danh tính liên kết sang tài khoản nội bộ bằng định danh đúng nguồn. |

Ngay cả email đã xác minh cũng chỉ xác nhận **một dạng quyền kiểm soát email tại thời điểm và theo quy trình xác minh**; nó không chứng minh tất cả thông tin pháp lý và không bảo đảm quyền kiểm soát sẽ tồn tại mãi.

**Nguyên tắc thiết kế:** dùng mã nội bộ bền vững cho quan hệ dữ liệu; giữ email/số điện thoại/tên dưới dạng thuộc tính thay đổi được; với danh tính liên kết, ánh xạ bằng khóa có **nguồn phát hành rõ ràng**, chẳng hạn cặp `issuer + subject`.

### 4.3 Định danh công khai và định danh nội bộ

Một API có thể phơi bày ID tham chiếu công khai, nhưng **khó đoán ID không thay thế kiểm tra quyền**. Nếu người dùng thay ID trong URL để xem hồ sơ người khác và API không kiểm tra chủ sở hữu, đó là lỗi kiểm soát truy cập theo đối tượng (IDOR/BOLA), kể cả khi ID được thiết kế ngẫu nhiên.

Có thể phân biệt:

- **ID nội bộ:** khóa liên kết dữ liệu, tối ưu cho tính toàn vẹn và quản trị.
- **ID công khai:** giá trị dùng trong URL/API, có thể tách khỏi khóa lưu trữ.
- **ID liên kết:** mã do IdP khác cấp, chỉ có ý nghĩa khi kèm thông tin nguồn.

Quy tắc phân quyền phải xét **chủ thể đã xác thực + tài nguyên + hành động + ngữ cảnh**, không chỉ kiểu dữ liệu hoặc hình thức của ID.

## 5. Thuộc tính danh tính và mức độ tin cậy

Một hồ sơ danh tính có thể chứa tên, phòng ban, tổ chức, email, nhóm, trạng thái làm việc và nhiều thông tin khác. Các thuộc tính này có nguồn gốc và độ tin cậy khác nhau.

Ví dụ:

| Thuộc tính | Nguồn có thể có | Hệ thống nên ghi nhớ |
| --- | --- | --- |
| Tên hiển thị | Người dùng tự sửa | Phục vụ giao diện, không đủ để xác định danh tính pháp lý. |
| Email liên hệ | Người dùng khai và xác minh qua liên kết/mã | Thời điểm xác minh và trạng thái còn dùng được. |
| Phòng ban | Hệ thống nhân sự | Nguồn cấp, thời điểm đồng bộ, thay đổi khi chuyển việc. |
| Tư cách nhân viên | Quy trình quản lý nhân sự | Cần cập nhật khi nghỉ việc; có thể ảnh hưởng quyền. |
| Vai trò ứng dụng | Chính sách phân quyền của ứng dụng | Không lấy trực tiếp từ trường do client gửi. |
| Mức kiểm chứng danh tính | Quy trình đăng ký/kiểm chứng phù hợp nghiệp vụ | Loại bằng chứng, người/đơn vị xác minh và thời điểm, trong giới hạn cần thiết. |

Thông tin nhạy cảm phải được thu thập và lưu trữ có mục đích; không nên giữ thêm ảnh giấy tờ, sinh trắc học hoặc dữ liệu nhận diện chỉ vì "có thể hữu ích sau này".

### Tự khai, xác minh kênh và kiểm chứng danh tính là ba việc khác nhau

1. **Tự khai:** người dùng nhập "Tôi tên Lan". Hệ thống chỉ biết có một lời khai.
2. **Xác minh kênh:** người dùng nhấp liên kết gửi tới email. Hệ thống biết người đó có thể truy cập email theo cơ chế đang dùng.
3. **Kiểm chứng danh tính (identity proofing):** quy trình chuyên biệt liên kết hồ sơ với chủ thể ngoài đời bằng bằng chứng và kiểm tra tương xứng rủi ro.

Không phải ứng dụng nào cũng cần bước thứ ba. Với một diễn đàn bút danh, xác thực quyền sử dụng cùng tài khoản có thể là đủ. Với nghiệp vụ chịu ràng buộc về danh tính khách hàng, hệ thống có thể cần kiểm chứng cao hơn. Không nên gọi trạng thái "email verified" là "danh tính con người đã được xác minh".

## 6. Credential gắn với danh tính như thế nào?

Hệ thống cần xác định **bằng chứng nào được phép đại diện cho danh tính nào**. Quan hệ đó gọi là gắn kết (binding) credential/authenticator với tài khoản hoặc chủ thể.

Một luồng đăng ký passkey có thể diễn ra như sau:

1. Người dùng đang ở ngữ cảnh đăng ký hoặc phiên có đủ bảo đảm để thêm phương thức xác thực.
2. Máy chủ tạo thử thách mới và bắt đầu đăng ký credential cho tài khoản mục tiêu.
3. Thiết bị tạo cặp khóa theo cơ chế WebAuthn/FIDO2, bảo vệ khóa riêng và gửi dữ liệu đăng ký cần thiết, gồm khóa công khai.
4. Máy chủ kiểm tra thử thách, origin/RP ID và điều kiện đăng ký theo chính sách, rồi lưu liên kết giữa **credential ID, khóa công khai và mã tài khoản nội bộ**.
5. Khi đăng nhập, máy chủ đưa thử thách mới; authenticator chứng minh quyền sở hữu khóa riêng; máy chủ xác minh phản hồi và xác định tài khoản tương ứng.

Với mật khẩu, hệ thống lưu **bản băm mật khẩu có salt** bằng thuật toán chuyên dụng phù hợp như Argon2id; không lưu mật khẩu rõ và không coi mật khẩu là mã định danh. Với chứng chỉ số cho dịch vụ, cần xác minh quyền sở hữu khóa riêng, chuỗi tin cậy/điều kiện cấp phát và ánh xạ chứng chỉ sang đúng danh tính dịch vụ.

Một tài khoản có thể có nhiều authenticator để duy trì truy cập khi đổi thiết bị. Ngược lại, credential không nên được gắn sang tài khoản khác chỉ vì client tự gửi một ID mới: thao tác thêm, tháo hoặc thay authenticator cần được bảo vệ theo mức rủi ro.

**MFA** là việc kết hợp các yếu tố xác thực độc lập theo thiết kế, chẳng hạn điều người dùng biết và thiết bị họ sở hữu. Việc hai màn hình cùng hỏi hai bí mật thuộc nhóm "điều biết" không tự động tạo MFA. Passkey thường dùng thao tác mở khóa cục bộ bằng PIN hoặc sinh trắc học; máy chủ kiểm chứng bằng chứng mật mã, không cần nhận dữ liệu vân tay.

## 7. Vòng đời danh tính số

Danh tính số không phải một bản ghi chỉ tạo một lần rồi giữ mãi. Mỗi thay đổi có thể tác động tới tính hợp lệ của credential, phiên và quyền.

~~~mermaid
flowchart TD
    A["Tạo hồ sơ / đăng ký"] --> B["Kiểm chứng phù hợp rủi ro"]
    B --> C["Gắn credential / authenticator"]
    C --> D["Hoạt động: xác thực, cập nhật, phân quyền"]
    D --> E["Đổi thông tin, thêm thiết bị,\nliên kết hoặc khôi phục"]
    E --> D
    D --> F["Khóa / đình chỉ"]
    F --> G{"Có căn cứ khôi phục?"}
    G -->|"Có"| E
    G -->|"Không / chấm dứt"| H["Thu hồi quyền, đóng hoặc xóa\n theo chính sách"]
    D --> H
~~~

| Giai đoạn | Việc hệ thống cần kiểm soát | Hậu quả nếu xử lý sai |
| --- | --- | --- |
| **Đăng ký (enrollment)** | Tránh tạo trùng trái phép, xác minh kênh liên hệ, xác lập chủ thể thích hợp | Gán hồ sơ cho nhầm người hoặc tạo danh tính giả. |
| **Thiết lập danh tính/kiểm chứng** | Chọn mức kiểm chứng phù hợp, biết nguồn và giới hạn bằng chứng | Tin nhầm thông tin tự khai thành danh tính đã xác minh. |
| **Gắn credential** | Chỉ cho phép gắn vào đúng tài khoản, xác minh quyền quản lý tài khoản | Kẻ tấn công thêm passkey hoặc thiết bị MFA của mình. |
| **Hoạt động** | Xác thực bằng chứng, bảo vệ phiên/token, phân quyền mỗi tác vụ | Chiếm phiên hoặc lạm dụng đặc quyền. |
| **Thay đổi thuộc tính** | Kiểm soát người được sửa, xác minh lại thuộc tính cần thiết, lưu dấu vết phù hợp | Đổi email để chuyển quyền khôi phục. |
| **Liên kết danh tính** | Kiểm tra bằng chứng của cả hai bên, tính nhất quán và đồng ý phù hợp | Gộp tài khoản của hai người thành một. |
| **Khôi phục** | Xử lý mất credential như hành động nhạy cảm; bảo vệ trước social engineering | Bỏ qua cơ chế MFA bằng luồng quên mật khẩu yếu. |
| **Đình chỉ / thu hồi / đóng** | Vô hiệu hóa credential và quyền, xử lý phiên/token tồn tại, quản lý dữ liệu theo chính sách | Người rời tổ chức vẫn đăng nhập được; token cũ tiếp tục có hiệu lực. |

Không nên chỉ đặt cờ "inactive" trong cơ sở dữ liệu rồi cho rằng mọi access token đã phát đều mất hiệu lực tức thì. Tùy kiến trúc, API có thể chấp nhận token còn hạn cho đến khi hết hạn; cần có cơ chế thu hồi, giới hạn TTL, kiểm tra trạng thái hoặc thiết kế phù hợp với yêu cầu vô hiệu hóa.

## 8. Danh tính liên kết và SSO: khi ứng dụng tin một IdP

Một tổ chức có thể dùng Identity Provider (IdP) để xác thực nhân viên cho nhiều ứng dụng. Ứng dụng tiếp nhận (Relying Party, RP) phải thiết lập **quan hệ tin cậy** với IdP và xác minh kết quả bằng giao thức tương ứng.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant R as Ứng dụng (RP)
    participant I as Identity Provider
    participant A as API
    U->>R: Mở chức năng cần đăng nhập
    R->>I: Chuyển đến luồng xác thực đã cấu hình
    U->>I: Trình credential / thực hiện MFA
    I-->>R: Phản hồi theo giao thức liên kết
    R->>R: Kiểm chứng nguồn, token, ngữ cảnh và ánh xạ subject
    R-->>U: Thiết lập phiên ứng dụng
    U->>R: Yêu cầu xem tài nguyên
    R->>A: Truy vấn đã xác thực / được cấp quyền phù hợp
    A-->>R: Kết quả sau kiểm tra quyền
~~~

Trong OIDC, hệ thống thường dựa trên **ID token** đã được kiểm chứng để nhận biết sự kiện xác thực và subject đối với client thích hợp. Ứng dụng phải kiểm chứng các điều kiện phù hợp với luồng, bao gồm issuer, audience, chữ ký, thời hạn và nonce nếu luồng yêu cầu; đồng thời bảo vệ state, trao đổi authorization code an toàn và xử lý callback đúng ngữ cảnh.

**OAuth 2.0 là khuôn khổ ủy quyền**, không mặc nhiên là giao thức xác thực danh tính người dùng. **Access token** dùng để truy cập tài nguyên có thể dành cho API và audience cụ thể; không được coi token bất kỳ hoặc claim "email" là bằng chứng đăng nhập hợp lệ cho ứng dụng.

### Ánh xạ danh tính từ IdP sang tài khoản nội bộ

Mô hình dữ liệu minh họa:

~~~text
LocalAccount
  internalId: "acct_b72f"        # ID ổn định do ứng dụng cấp
  displayName: "Lan"
  status: "active"

FederatedIdentityLink
  accountId: "acct_b72f"
  issuer: "https://id.company-a.example"
  subject: "subject-opaque-88"  # Định danh có phạm vi issuer

ContactPoint
  accountId: "acct_b72f"
  email: "lan@example.test"
  emailVerified: true
~~~

Các giá trị trên chỉ là dữ liệu giả dùng để giải thích, không phải cấu hình hoặc token thật.

Nếu Lan đổi email nhưng IdP vẫn phát hành cùng cặp issuer/subject, ứng dụng có thể nhận ra cùng danh tính liên kết, miễn là quan hệ tin cậy và quy tắc quản lý vẫn hợp lệ. Nếu có một người khác sở hữu email cũ, **không được tự chuyển tài khoản cũ cho người đó**.

Nếu ứng dụng kết nối hai IdP, có thể có hai cặp issuer/subject ánh xạ tới một tài khoản nội bộ, **chỉ sau quy trình liên kết được bảo vệ**.

### Liên kết tài khoản là hành động nhạy cảm

Một sai lầm phổ biến là tự động gộp hai tài khoản khi chúng dùng cùng email. Cách này có thể bị lợi dụng nếu email bị tái cấp, chưa được xác minh hoặc nhà cung cấp dùng quy tắc khác về thuộc tính email.

Quy trình an toàn nên:

1. Xác định tài khoản nội bộ mà người dùng **đang có quyền kiểm soát** và yêu cầu xác thực lại nếu rủi ro cao.
2. Hoàn tất luồng chứng minh quyền kiểm soát **danh tính bên ngoài** cần liên kết, thông qua IdP tin cậy.
3. Kiểm tra có xung đột: cặp issuer/subject đã liên kết với tài khoản nào chưa? Hệ thống có cho phép chuyển liên kết không?
4. Ghi nhận quyết định, thông báo phù hợp, quản lý khả năng hủy liên kết và tránh khóa người dùng khỏi tài khoản duy nhất.
5. Sau khi liên kết, phân quyền dựa trên **chủ thể nội bộ có hiệu lực**, thuộc tính đã được chấp nhận và chính sách, không dựa vào việc "cùng email".

## 9. Danh tính người dùng, danh tính thiết bị và danh tính dịch vụ

Xác thực không chỉ áp dụng cho con người.

**Người dùng:** hệ thống cần biết tài khoản đang được sử dụng bởi người có quyền trình credential. Phiên được tạo sau đăng nhập không bảo đảm người đang cầm thiết bị ở mọi thời điểm vẫn là người ban đầu; các thao tác nhạy cảm có thể cần xác thực lại.

**Thiết bị:** thiết bị có thể được cấp khóa/chứng chỉ riêng và có trạng thái tin cậy. Một thiết bị đã xác thực không chứng minh người hiện tại trên thiết bị là ai. Ngược lại, người đã xác thực không chứng minh máy họ sử dụng an toàn.

**Dịch vụ:** một tiến trình tự động có thể chứng minh danh tính bằng mTLS hoặc credential dịch vụ. API cần xác thực dịch vụ gọi đến, kiểm tra đúng audience và quyền tối thiểu; tên dịch vụ trong một header tự khai không đủ.

**Tài khoản đặc quyền và tài khoản chia sẻ:** có rủi ro truy vết và cấp quyền. Nên ưu tiên danh tính cá nhân hoặc danh tính tác vụ rõ ràng, tách quyền quản trị khỏi tài khoản dùng thường ngày, giới hạn phạm vi và có nhật ký phù hợp.

Ví dụ, nếu một nhân viên đăng nhập dashboard rồi dashboard gọi API xử lý đơn hàng, API cần phân biệt:

- **Ứng dụng nào đang gọi API?** Danh tính của dịch vụ trung gian.
- **Thao tác được thực hiện thay mặt người dùng nào?** Ngữ cảnh ủy quyền được cấp và có thể xác minh.
- **Người dùng đó có quyền trên đơn hàng này không?** Phân quyền trên tài nguyên đích.

Ba câu hỏi không được giải quyết bằng một chuỗi "userId" do client tự đặt.

## 10. Các mối đe dọa khi thiết kế danh tính số

| Mối đe dọa | Ví dụ | Biện pháp cốt lõi |
| --- | --- | --- |
| **Mạo danh qua định danh tự khai** | Request tự đặt "userId" hoặc "serviceName". | Xác thực tại máy chủ và liên kết yêu cầu với chủ thể từ bằng chứng hợp lệ. |
| **Account enumeration** | API báo "email này tồn tại" khác biệt rõ ràng khi đăng nhập/khôi phục. | Giảm lộ trạng thái tài khoản, giới hạn yêu cầu và giám sát lạm dụng. |
| **Credential stuffing / password spraying** | Thử mật khẩu rò rỉ trên nhiều tài khoản. | Mật khẩu an toàn, MFA/phương thức chống phishing, giới hạn thử sai theo rủi ro, phát hiện bất thường. |
| **Phishing** | Trang giả yêu cầu mật khẩu hoặc OTP. | Ưu tiên passkey/FIDO2 khi phù hợp, bảo vệ luồng đăng nhập và truyền thông với người dùng. |
| **Replay** | Phát lại một thông điệp/bằng chứng cũ để qua kiểm tra. | Thử thách mới, nonce, thời hạn, ràng buộc đối tượng nhận và ngữ cảnh. |
| **Chiếm phiên / token** | Token còn hạn bị lấy cắp qua mã độc, log hoặc XSS. | Bảo vệ nơi lưu trữ, cookie/token, hạn sử dụng, thu hồi và xác thực tăng cường khi cần. |
| **Gộp sai danh tính** | Tự liên kết hai IdP do trùng email. | Dựa trên issuer/subject, chứng minh quyền kiểm soát hai bên, xử lý xung đột. |
| **Lạm dụng khôi phục** | Kẻ tấn công đổi email/thiết bị MFA bằng kênh yếu. | Bảo vệ reset và enrollment như thao tác nhạy cảm; giới hạn, thông báo, kiểm tra bổ sung. |
| **IDOR/BOLA** | Đổi mã hồ sơ trong URL để xem dữ liệu người khác. | Phân quyền trên từng đối tượng và hành động ở phía API. |
| **Danh tính không được thu hồi** | Nhân viên nghỉ việc nhưng quyền và token vẫn hoạt động. | Đồng bộ trạng thái, vô hiệu hóa credential/quyền, quản trị vòng đời token/phiên. |
| **Liên kết thông tin không cần thiết** | Dùng cùng ID công khai ở nhiều dịch vụ khiến hoạt động người dùng dễ bị theo dõi. | Giảm dữ liệu thu thập, xem xét mã định danh theo từng ngữ cảnh/pairwise, giới hạn chia sẻ. |

**Điểm chung:** các lỗi không chỉ xảy ra khi nhập mật khẩu. Chúng có thể phát sinh ở bước tạo danh tính, chọn mã, cập nhật thuộc tính, thiết lập phiên, trao đổi token, liên kết IdP và khôi phục.

## 11. Danh tính số và quyền riêng tư

Danh tính số thường chứa dữ liệu cá nhân. Một thiết kế an toàn cần bảo đảm **đúng thông tin, đúng mục đích, đúng bên được phép sử dụng**.

Một số nguyên tắc thực tế:

- **Tối thiểu hóa dữ liệu:** nếu ứng dụng chỉ cần xác nhận người dùng đủ tuổi theo chính sách, không mặc nhiên yêu cầu lưu toàn bộ giấy tờ tùy thân.
- **Giới hạn mục đích:** thông tin phục vụ xác thực và khôi phục không tự động được phép chia sẻ cho mọi mục đích khác.
- **Tách mã nhận diện theo bối cảnh khi cần:** mã định danh theo từng ứng dụng/nhóm ứng dụng giúp hạn chế tương quan hoạt động giữa các dịch vụ. Tuy nhiên, **bút danh không đồng nghĩa ẩn danh tuyệt đối**.
- **Bảo vệ thuộc tính nhạy cảm:** kiểm soát quyền đọc, mã hóa khi phù hợp, tránh đưa credential, token, dữ liệu cá nhân không cần thiết vào log.
- **Quản lý vòng đời dữ liệu:** có chính sách cập nhật, lưu giữ, xóa và xử lý bằng chứng kiểm chứng phù hợp yêu cầu nghiệp vụ/pháp luật áp dụng.
- **Minh bạch với người dùng:** giải thích điều gì được thu thập/xác minh/chia sẻ, hỗ trợ cập nhật thông tin và xử lý sai lệch.

Một mã số nội bộ có thể vô nghĩa khi nhìn riêng lẻ nhưng vẫn là **dữ liệu có khả năng liên kết đến cá nhân** nếu hệ thống có bảng ánh xạ. Do đó, thay tên bằng ID không tự động loại bỏ mọi rủi ro riêng tư.

## 12. Ví dụ thiết kế một dịch vụ học tập

Giả sử hệ thống học tập có đăng ký bằng email, đăng nhập passkey, học viên liên kết tài khoản trường học qua SSO và giảng viên có quyền quản lý lớp.

### 12.1 Chọn cấu trúc danh tính

~~~text
Subject (tài khoản nội bộ)
  id                    # Mã nội bộ bền vững, không tái sử dụng
  status                # Active / suspended / closed
  createdAt

Contact
  subjectId
  email
  verifiedAt            # Có thể chưa xác minh hoặc cần xác minh lại

Authenticator
  subjectId
  type                  # Passkey, password, ...
  credentialReference   # Không chứa khóa riêng hay mật khẩu rõ
  status

ExternalIdentityLink
  subjectId
  issuer
  externalSubject       # Cặp (issuer, externalSubject) phải được quản lý duy nhất

Membership
  subjectId
  classId
  role                  # Ví dụ: learner, instructor
  status
~~~

Đây là mô hình minh họa; cách lưu thực tế phụ thuộc sản phẩm. **Membership** thể hiện quyền trong lớp, còn **Authenticator** thể hiện cách chứng minh quyền sử dụng tài khoản. Hai loại dữ liệu có mục đích khác nhau.

### 12.2 Luồng đăng nhập và truy cập lớp

~~~text
1. Người dùng hoàn tất thử thách đăng nhập hợp lệ.
2. Server ánh xạ credential hoặc (issuer, subject) vào subjectId nội bộ.
3. Server thiết lập phiên/token cho chủ thể và ngữ cảnh được phép.
4. Khi gọi GET /classes/{classId}/students:
   a. API xác minh phiên/token đúng đối tượng và còn hiệu lực;
   b. API lấy subjectId từ kết quả xác minh, không tin subjectId trong body;
   c. API kiểm tra Membership/role cho classId đang yêu cầu;
   d. API trả dữ liệu nếu được phép, ngược lại từ chối.
~~~

Nếu học viên thay email, **subjectId không đổi** và tiến độ học không tự mất. Nếu học viên liên kết SSO của trường, hệ thống chỉ gắn thêm một danh tính liên kết sau khi chứng minh quyền kiểm soát tài khoản hiện tại và tài khoản trường. Nếu người dùng rời trường, hệ thống cần quyết định rõ quyền lớp học có bị thu hồi theo nguồn nào; không nên đồng nhất "mất SSO" với "xóa mọi tiến độ" nếu nghiệp vụ không yêu cầu.

### 12.3 Ba lỗi thiết kế cần tránh

**Lỗi 1 — Cấp quyền theo email:** server cho phép ai có email kết thúc bằng một tên miền trường được làm giảng viên. Tên miền email không tự chứng minh vai trò giảng viên. Quyền cần được cấp bằng nguồn đáng tin và kiểm tra theo từng lớp.

**Lỗi 2 — Tự gộp tài khoản:** người dùng đăng nhập SSO và email do IdP trả về trùng một tài khoản học viên, hệ thống tự động gộp mà không cần chứng minh quyền kiểm soát tài khoản gốc. Nếu thông tin email bị sai hoặc bị tái cấp, có thể dẫn tới chiếm tài khoản.

**Lỗi 3 — Tin subjectId từ client:** client gửi subjectId của giảng viên trong request cập nhật điểm. Nếu API lấy ID này làm chủ thể mà không kiểm tra bằng chứng phiên/token và vai trò trong lớp, học viên có thể mạo danh giảng viên.

## 13. Bộ câu hỏi thiết kế trước khi triển khai

Khi thiết kế một luồng có liên quan đến danh tính số, hãy tự hỏi:

1. **Ai là chủ thể?** Người, thiết bị hay dịch vụ? Danh tính thuộc phạm vi nào?
2. **Ai cấp mã định danh?** Mã có bền vững và có phạm vi rõ ràng không? Có nguy cơ tái cấp hay trùng không?
3. **Thuộc tính đến từ đâu?** Tự khai, xác minh email hay một nguồn có thẩm quyền? Thuộc tính có thể lỗi thời không?
4. **Credential gắn với tài khoản bằng quy trình nào?** Ai có quyền thêm, thay, xóa? Có cần xác thực lại không?
5. **Ai xác thực và ai tiêu thụ kết quả?** Client, máy chủ, IdP và API vượt qua những ranh giới tin cậy nào?
6. **Khi dùng SSO, ứng dụng ánh xạ subject ra sao?** Có kiểm chứng issuer/audience, ngữ cảnh giao thức và xung đột liên kết không?
7. **Quyền cụ thể nằm ở đâu?** Hệ thống có kiểm tra chủ thể, đối tượng và thao tác trên server không?
8. **Khi mất credential, nghỉ việc hoặc bị khóa tài khoản thì sao?** Phiên, token, quyền và luồng khôi phục được xử lý thế nào?
9. **Dữ liệu nào thật sự cần giữ?** Có cần kiểm chứng danh tính ngoài đời không, hay chỉ cần một tài khoản bút danh an toàn?

## 14. Tự kiểm tra

**Câu 1.** Hai tài khoản có cùng tên hiển thị và email thì chắc chắn thuộc một danh tính số duy nhất?

**Đáp án:** Không. Email và tên có thể thay đổi, bị tái cấp hoặc cùng xuất hiện trong nhiều hệ thống. Mỗi định danh phải được hiểu theo phạm vi và nguồn cấp; liên kết tài khoản cần quy trình kiểm chứng riêng.

**Câu 2.** Một ứng dụng nhận từ IdP hai giá trị `sub = "A123"` giống nhau nhưng `iss` khác nhau. Có nên tự gộp?

**Đáp án:** Không. `sub` cần được hiểu trong phạm vi nhà phát hành tương ứng; cặp `iss + sub` mới xác định danh tính liên kết theo quan hệ được cấu hình. Gộp chỉ thực hiện qua quy trình được phép.

**Câu 3.** Một người đã xác minh email có mặc nhiên được coi là đã kiểm chứng danh tính pháp lý?

**Đáp án:** Không. Xác minh email chủ yếu chứng minh quyền kiểm soát kênh tại thời điểm kiểm tra. Identity proofing cần quy trình bằng chứng riêng phù hợp nghiệp vụ.

**Câu 4.** Nếu dùng ID ngẫu nhiên khó đoán trong URL, API có thể bỏ kiểm tra quyền đối với tài nguyên không?

**Đáp án:** Không. ID khó đoán chỉ giảm khả năng đoán ID; quyền phải được kiểm tra dựa trên chủ thể đã xác thực, đối tượng và hành động.

**Câu 5.** Tại sao trạng thái nghỉ việc phải liên quan đến credential và phiên đã cấp?

**Đáp án:** Vì chỉ cập nhật hồ sơ nhân sự chưa bảo đảm credential, token, phiên hoặc quyền ứng dụng mất hiệu lực. Quy trình kết thúc danh tính cần xử lý toàn bộ đường truy cập có liên quan.

**Câu 6.** Thiết bị có chứng chỉ hợp lệ đã chứng minh danh tính của người đang sử dụng thiết bị chưa?

**Đáp án:** Chưa. Chứng chỉ có thể xác thực thiết bị hoặc dịch vụ nắm khóa riêng; muốn xác thực người dùng cần bằng chứng và chính sách tương ứng.

**Câu 7.** Người dùng bị mất passkey và muốn thêm passkey mới. Đây chỉ là thao tác chỉnh sửa cấu hình?

**Đáp án:** Không. Đây là thao tác có thể chuyển quyền kiểm soát danh tính cho một chủ thể khác, nên phải được bảo vệ bằng quy trình khôi phục và gắn authenticator an toàn.

## Ghi nhớ

**Danh tính số là cách hệ thống biểu diễn một chủ thể trong một ngữ cảnh tin cậy.** Định danh cho biết đang tham chiếu hồ sơ nào; thuộc tính mô tả hồ sơ đó và có nguồn tin cậy riêng; credential giúp chứng minh quyền sử dụng danh tính; phiên và token truyền kết quả xác thực theo giới hạn; phân quyền quyết định hành động được phép.

Thiết kế an toàn đòi hỏi định danh có phạm vi và ổn định, kiểm chứng đúng nguồn, gắn và khôi phục credential có kiểm soát, liên kết danh tính không dựa đơn thuần vào email, quản lý trạng thái toàn vòng đời và bảo vệ quyền riêng tư. Đây là nền tảng để chống phishing, replay, lạm dụng đăng nhập và xây dựng các luồng xác thực đáng tin cậy.

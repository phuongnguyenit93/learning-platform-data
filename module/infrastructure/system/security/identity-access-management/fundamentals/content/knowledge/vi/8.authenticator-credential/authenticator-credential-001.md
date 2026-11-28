# Authenticator là gì

## 1. Khái niệm cốt lõi

**Authenticator** là thứ mà người dùng sở hữu hoặc kiểm soát và sử dụng để chứng minh mình có quyền kiểm soát một phương tiện xác thực đã gắn với tài khoản. Nó có thể là mật khẩu, thiết bị giữ khóa mật mã hoặc phần mềm quản lý bí mật dùng để tạo bằng chứng xác thực. Thuật ngữ này rộng hơn tên gọi của một ứng dụng tạo mã trên điện thoại. [NIST SP 800-63B-4 — Glossary](https://pages.nist.gov/800-63-4/sp800-63b/glossary/).

Ví dụ, Lan có tài khoản trên cổng quản trị nhân sự. Địa chỉ email giúp hệ thống xác định Lan muốn truy cập tài khoản nào. Mật khẩu hoặc bằng chứng từ khóa bảo mật giúp hệ thống kiểm tra người đang truy cập có kiểm soát authenticator tương ứng hay không.

Sau khi xác thực, hệ thống còn phải quyết định Lan được đọc hồ sơ nào, có được cấp role hay không và được thao tác trong tenant nào. Authenticator giải quyết một phần của bài toán IAM; nó không tự quyết định toàn bộ quyền truy cập.

Một câu hỏi thực dụng khi phân tích cơ chế đăng nhập là: **người dùng phải kiểm soát thứ gì để tạo ra bằng chứng mà máy chủ chấp nhận?** Câu trả lời giúp phân biệt authenticator thật với tên tài khoản, nhãn thiết bị hoặc một bước giao diện.

## 2. Phân biệt những khái niệm dễ bị gọi chung

| Khái niệm | Vai trò |
| --- | --- |
| Identifier | Định danh tài khoản hoặc chủ thể, chẳng hạn username. |
| Authentication factor | Loại yếu tố được chứng minh: biết, có hoặc đặc điểm của người dùng. |
| Authenticator | Phương tiện hoặc bí mật được người dùng kiểm soát để xác thực. |
| Authenticator output | Giá trị đầu ra được tạo hoặc sử dụng trong giao thức xác thực. |
| Credential | Cấu trúc liên kết danh tính với authenticator theo một mô hình quản lý. |

NIST phân biệt authenticator, đầu ra của nó và credential. Trong mô hình này, credential ghi nhận liên kết danh tính với authenticator; đó không chỉ là tên gọi khác của mọi chuỗi bí mật. [NIST — Glossary](https://pages.nist.gov/800-63-4/sp800-63b/glossary/).

Trong tài liệu sản phẩm và lập trình, từ `credential` đôi khi được dùng theo nghĩa rộng như thông tin đăng nhập hoặc một đối tượng API. Vì vậy, khi đọc một thư viện, cần xem định nghĩa của thư viện thay vì ép mọi trường có tên `credential` vào cùng một nghĩa.

Xét ứng dụng tạo mã TOTP của Lan:

- Biểu tượng ứng dụng trên điện thoại không phải bằng chứng máy chủ có thể tin ngay.
- Bản cấu hình chứa bí mật của đúng tài khoản cho phép ứng dụng tạo mã tương ứng.
- Mã đang hiển thị là đầu ra ngắn hạn, khác với bí mật dài hạn dùng để tạo mã.
- Bản ghi phía hệ thống liên kết cấu hình xác thực với tài khoản Lan.

Nếu Lan chép bí mật tạo mã sang một máy khác, máy đó cũng có thể tạo đầu ra tương ứng. Việc hiểu “thứ gì phải được bảo vệ” có ích hơn việc chỉ ghi nhận đã cài một ứng dụng mang tên Authenticator.

## 3. Ai tham gia kiểm tra authenticator?

Trong mô hình NIST, **claimant** là chủ thể đang yêu cầu được xác thực; **verifier** kiểm tra quyền kiểm soát authenticator; **CSP** quản lý tài khoản và liên kết authenticator; **RP** là bên sử dụng kết quả để cung cấp dịch vụ. Các vai trò có thể nằm trong cùng hệ thống hoặc được phân tách. [NIST — Digital Identity Model](https://pages.nist.gov/800-63-4/sp800-63/model/).

Với ứng dụng đăng nhập trực tiếp, backend có thể vừa quản lý tài khoản, vừa kiểm tra bằng chứng, vừa phục vụ chức năng nghiệp vụ. Khi có SSO, ứng dụng nghiệp vụ có thể dựa vào kết quả từ nhà cung cấp danh tính thay vì trực tiếp kiểm tra mật khẩu hoặc khóa của người dùng.

Điều này ảnh hưởng đến cách điều tra lỗi. Nếu Lan đăng nhập qua IdP, nhóm phát triển phải biết thành phần nào kiểm tra authenticator và thành phần nào kiểm tra kết quả federation. Không mặc định một ứng dụng đã trực tiếp kiểm tra MFA chỉ vì màn hình của nó có nút “Đăng nhập SSO”.

## 4. Authenticator và yếu tố xác thực

Ba loại yếu tố thường được diễn đạt như sau:

| Loại yếu tố | Ví dụ |
| --- | --- |
| Something you know — điều bạn biết | Mật khẩu hoặc bí mật ghi nhớ. |
| Something you have — thứ bạn có | Thiết bị hoặc phần mềm giữ khóa xác thực. |
| Something you are — đặc điểm của bạn | Đặc điểm sinh trắc học dùng trong quá trình xác thực phù hợp. |

Nhiều lần sử dụng cùng loại yếu tố không tạo thành MFA. Ví dụ, mật khẩu và một PIN cùng được kiểm tra như hai bí mật ghi nhớ vẫn thuộc cùng loại. [NIST — Authenticators trong mô hình danh tính](https://pages.nist.gov/800-63-4/sp800-63/model/#authenticators).

Một thiết bị cũng không nhất thiết chỉ cung cấp một yếu tố. Khi thiết bị giữ khóa và yêu cầu yếu tố kích hoạt phù hợp trước khi dùng khóa, một thao tác trên giao diện có thể chứa nhiều bước kiểm tra bên trong.

Ngược lại, việc Lan đã mở khóa điện thoại từ lâu không đủ để tự kết luận mọi hoạt động xác thực sau đó đều là đa yếu tố. Cần xem cơ chế thực tế yêu cầu gì trong từng lần sử dụng và verifier nhận được bằng chứng nào.

Theo NIST, sinh trắc học không phải authenticator độc lập; nó được sử dụng cùng một authenticator vật lý trong xác thực đa yếu tố. PIN hoặc sinh trắc học dùng để mở khả năng sử dụng khóa cục bộ có vai trò là yếu tố kích hoạt. [NIST — Authenticator and Verifier Requirements](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/).

## 5. Ba ví dụ để nhận diện authenticator

### 5.1. Mật khẩu

Lan nhập username và mật khẩu vào cổng đăng nhập. Username xác định tài khoản cần kiểm tra; việc chứng minh biết mật khẩu đã được đăng ký là phần xác thực.

Mật khẩu là ví dụ cho thấy authenticator không nhất thiết là một vật cầm trên tay. Với loại này, một người khác biết được bí mật có thể đưa ra cùng bằng chứng như Lan. Hệ thống không nên suy từ “mật khẩu đúng” rằng thiết bị đang dùng chắc chắn là thiết bị của Lan hoặc danh tính ngoài đời đã được kiểm chứng.

Phía máy chủ cần cơ chế lưu và kiểm tra mật khẩu phù hợp, thay vì lưu nguyên văn để so sánh. Không có lý do ghi mật khẩu vào audit chỉ để chứng minh đã đăng nhập; sự kiện thành công và bí mật dùng để xác thực là hai loại dữ liệu khác nhau.

### 5.2. Ứng dụng tạo mã TOTP

TOTP tạo đầu ra dựa trên khóa bí mật dùng chung và yếu tố thời gian. Bên tạo mã và bên kiểm tra phải có cấu hình tương ứng; bí mật dài hạn không đồng nhất với mã dùng trong một khoảng thời gian. [RFC 6238 — TOTP](https://www.rfc-editor.org/rfc/rfc6238.html).

Tình huống minh họa:

1. Lan hoàn thành quy trình đăng ký TOTP cho tài khoản.
2. Ứng dụng của Lan giữ bí mật cần thiết để tạo mã.
3. Khi đăng nhập, Lan nhập mã hiện tại vào hệ thống.
4. Verifier kiểm tra mã theo cấu hình, trạng thái và các điều kiện của giao thức.

Hai người dùng cùng một loại ứng dụng không có nghĩa dùng cùng một authenticator cho cùng tài khoản. Một ứng dụng có thể chứa nhiều bản cấu hình cho nhiều tài khoản. Ngược lại, sao chép một cấu hình có thể làm nhiều thiết bị cùng giữ bí mật liên quan.

Vì vậy, ảnh chụp QR đăng ký hoặc bản xuất chứa bí mật không phải tài liệu hướng dẫn vô hại. Nếu lộ thông tin đủ để tạo mã, chỉ đợi mã đang hiển thị hết hạn sẽ không giải quyết việc bí mật dài hạn đã bị sao chép.

### 5.3. Authenticator mật mã khóa công khai

Trong WebAuthn, authenticator quản lý credential khóa công khai cho RP. Máy chủ kiểm tra phản hồi bằng khóa công khai đã đăng ký, cùng các điều kiện của giao thức như challenge, origin và RP ID. Khi cần user verification, kết quả tương ứng phải được kiểm tra. [W3C — Web Authentication](https://www.w3.org/TR/webauthn-3/).

Một luồng minh họa đơn giản:

```text
Backend tạo challenge cho lần xác thực
                    |
                    v
Người dùng tương tác với authenticator
                    |
                    v
Authenticator tạo phản hồi bằng khóa riêng
                    |
                    v
Backend xác minh phản hồi và ngữ cảnh yêu cầu
```

Sơ đồ không phải mô tả đầy đủ mọi bước WebAuthn. Điểm cần nắm là máy chủ không xác thực người dùng bằng việc “nhìn thấy khóa bảo mật được cắm vào” mà bằng phản hồi hợp lệ trong giao thức đã xác định.

Nếu thiết bị yêu cầu Lan xác minh bằng vân tay để dùng khóa, không nên diễn giải thành ứng dụng nghiệp vụ đã nhận và so sánh vân tay của Lan. Cần phân biệt bước xác minh cục bộ với bằng chứng máy chủ nhận được.

## 6. Kiểm soát authenticator phải gắn với đúng tài khoản

Một bằng chứng mật mã hợp lệ chưa đủ nếu được kiểm tra với bản ghi không thuộc tài khoản cần xác thực. Hệ thống cần biết authenticator nào đã gắn với chủ thể nào và liên kết đó có còn hiệu lực không.

Ví dụ, Minh có khóa hợp lệ cho tài khoản của Minh. Nếu API của cổng quản trị cho phép người gọi gửi `userId` của Lan cùng một bằng chứng của Minh rồi chỉ kiểm tra “chữ ký có hợp lệ hay không”, hệ thống có thể xác thực nhầm chủ thể.

Luồng kiểm tra về mặt khái niệm nên làm rõ:

1. Xác định tài khoản và bản ghi authenticator theo giao thức hỗ trợ.
2. Kiểm tra liên kết giữa bản ghi và tài khoản cần xác thực.
3. Kiểm tra tài khoản, bản ghi và yêu cầu xác thực còn được phép sử dụng.
4. Xác minh bằng chứng bằng cơ chế chuẩn của loại authenticator.
5. Xử lý các điều kiện về độ mới, lần sử dụng và trạng thái theo giao thức.
6. Chỉ tạo ngữ cảnh đã xác thực sau khi những điều kiện cần thiết đều thỏa mãn.

Đây là mô hình suy nghĩ, không phải hướng dẫn tự viết thuật toán mật mã. Thư viện hoặc dịch vụ xác thực được chọn cần thực thi các bước cụ thể; người tích hợp vẫn phải cấp đúng ngữ cảnh và xử lý đúng kết quả.

Không phải mọi giao thức đều yêu cầu người dùng nhập username trước. Dù cách tìm tài khoản khác nhau, hệ thống vẫn cần xác định đúng chủ thể tương ứng với bằng chứng.

## 7. Đăng ký authenticator là một thao tác có giá trị bảo mật

**Authenticator binding** là việc thiết lập liên kết giữa authenticator cụ thể với tài khoản. NIST quy định quản lý các authenticator đã gắn và những sự kiện vòng đời liên quan; việc thêm authenticator sau khi tài khoản đã tồn tại có yêu cầu riêng. [NIST — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/).

Nếu một người có thể tự thêm khóa vào tài khoản Lan bằng cách chỉ biết email của Lan, cơ chế đăng nhập sau đó có mạnh đến đâu cũng không sửa được liên kết sai đã tạo. Chính việc đăng ký authenticator mới là một hành động cần được bảo vệ.

Một quy trình minh họa cho cổng quản trị có thể gồm:

- Xác nhận người đang thêm phương tiện có quyền quản lý phương tiện của tài khoản.
- Thực hiện bằng chứng và bước xác thực cần thiết cho chính sách đăng ký.
- Kiểm tra authenticator mới có thể hoàn thành quá trình đăng ký phù hợp.
- Tạo bản ghi ở đúng tài khoản và ghi nhận sự kiện.
- Thông báo cho chủ tài khoản qua cơ chế đã thiết kế.

Không lấy một trường `label` như “Điện thoại của Lan” làm bằng chứng quyền sở hữu. Nhãn đó giúp người dùng nhận biết phương tiện trong giao diện; nó có thể được nhập tùy ý.

## 8. Một tài khoản có thể có nhiều authenticator

Lan có thể dùng phương tiện chính khi làm việc và một phương tiện dự phòng được quản lý riêng. Mất thiết bị không nên khiến hệ thống buộc phải chọn giữa khóa tài khoản vĩnh viễn và bỏ qua mọi kiểm tra để khôi phục.

Ví dụ dữ liệu quản lý do ứng dụng tự định nghĩa:

```json
{
  "binding_id": "binding-42",
  "subject_id": "user-17",
  "authenticator_type": "PUBLIC_KEY",
  "label": "Khoa du phong",
  "status": "ACTIVE",
  "verification_material_ref": "verification-record-9"
}
```

Đây là dữ liệu minh họa, không phải schema NIST hoặc bản ghi WebAuthn đầy đủ. `verification_material_ref` là tham chiếu tới dữ liệu cần kiểm tra của loại tương ứng, không phải lời khuyên lưu mọi loại bí mật theo cùng một cách.

Trong màn hình quản lý, Lan cần phân biệt được các phương tiện để thu hồi đúng cái bị mất. Một thiết bị vật lý có thể phục vụ nhiều tài khoản hoặc có nhiều bản ghi; xóa một nhãn trong ứng dụng không đồng nghĩa đã xóa mọi khóa trên thiết bị.

Nhóm phát triển cũng cần phân biệt hai trạng thái:

- Tài khoản có khả năng sử dụng phương thức đa yếu tố.
- Lần xác thực hiện tại đã thực sự sử dụng những yếu tố cần thiết.

Ví dụ, tài khoản đã đăng ký TOTP nhưng phiên hiện tại chỉ đăng nhập bằng mật khẩu thì không thể dựa vào cờ `mfaEnabled=true` để kết luận lần đăng nhập đã hoàn thành MFA.

## 9. Vòng đời: tạo, dùng, thay thế và thu hồi

Trong ứng dụng minh họa, bản ghi authenticator có thể có các trạng thái:

| Trạng thái minh họa | Ý nghĩa ứng dụng cần thực thi |
| --- | --- |
| `PENDING` | Đăng ký chưa hoàn thành; chưa được dùng như phương tiện đã liên kết. |
| `ACTIVE` | Được phép tham gia xác thực theo chính sách. |
| `REVOKED` | Không tiếp tục chấp nhận để xác thực sau thu hồi. |
| `EXPIRED` | Không còn dùng được nếu loại phương tiện và chính sách có thời hạn. |

Tên trạng thái là lựa chọn thiết kế, không phải bộ giá trị chuẩn bắt buộc. Quan trọng là các điểm kiểm tra phải thực thi ý nghĩa đã công bố, kể cả khi có cache hoặc nhiều instance.

Giả sử Lan mất thiết bị tạo mã. Việc thu hồi cấu hình liên quan cần làm cho bằng chứng từ cấu hình đó không còn được chấp nhận. Chỉ xóa mục hiển thị ở giao diện không đủ nếu verifier vẫn sử dụng dữ liệu cũ.

Khôi phục tài khoản và đăng ký phương tiện thay thế phải có quy trình phù hợp. Không coi câu “tôi bị mất điện thoại” là bằng chứng cho phép thay authenticator của một tài khoản bất kỳ.

Ngoài ra, thu hồi authenticator và thu hồi phiên là hai vấn đề cần được liên kết bằng chính sách. Nếu một phiên đã được tạo từ trước, nhóm triển khai phải xác định có kết thúc phiên đó hay không và bằng cơ chế nào. Không tự giả định mọi phiên đã tự biến mất chỉ vì một authenticator bị thu hồi.

## 10. Authenticator mạnh không thay thế toàn bộ hệ thống

Một phương tiện tốt vẫn cần được sử dụng trong quy trình đúng. Các tình huống sau cho thấy ranh giới cần giữ:

| Tình huống | Câu hỏi cần đặt ra |
| --- | --- |
| Người dùng nhập mã vào trang giả | Bằng chứng có bị chuyển sang một phiên khác không? |
| Điện thoại bị sao chép dữ liệu tạo mã | Ai khác có thể tạo đầu ra hợp lệ? |
| Thêm khóa mới sau khi chiếm được phiên | Luồng binding có đủ bảo vệ không? |
| Authenticator bị thu hồi nhưng cache còn cũ | Mọi verifier có thực thi thu hồi theo cam kết không? |
| Phiên sau đăng nhập bị lấy cắp | Cơ chế quản lý phiên xử lý thế nào? |
| Đăng nhập đúng nhưng truy cập tenant khác | Authorization có kiểm tra đúng phạm vi không? |

Trong ví dụ về trang giả, mã có thể còn hiệu lực và chưa từng được dùng nhưng vẫn bị chuyển tiếp ngay sang dịch vụ thật. Vì vậy, chỉ thấy có “mã dùng một lần” chưa đủ để kết luận toàn bộ quá trình chống phishing.

Tương tự, việc authenticator tạo được đầu ra hợp lệ không tự chứng minh người dùng ngoài đời đã được kiểm chứng bằng giấy tờ, hay người đó có quyền cấp đặc quyền. Hệ thống cần sử dụng đúng loại bằng chứng cho đúng quyết định.

Độ bảo đảm xác thực cũng phụ thuộc quá trình thực tế: cách liên kết phương tiện, cách xác minh, yếu tố được yêu cầu và cách quản lý vòng đời. Không gắn một mức bảo đảm chỉ theo tên sản phẩm hoặc hình dáng thiết bị.

## 11. Những nhầm lẫn thường gặp

- **“Authenticator chỉ là ứng dụng tạo OTP.”** Ứng dụng đó là một ví dụ; khái niệm còn bao gồm những phương tiện và bí mật khác.
- **“Biết username nghĩa là đã có yếu tố xác thực.”** Username thường giúp tìm tài khoản, không chứng minh quyền kiểm soát phương tiện đã đăng ký.
- **“Mã OTP chính là bí mật gốc.”** Đầu ra ngắn hạn và dữ liệu tạo ra đầu ra có vai trò khác nhau.
- **“Hai màn hình là hai yếu tố.”** Phải xem loại yếu tố và cách kiểm tra thực tế.
- **“Mở khóa điện thoại nghĩa là server đã kiểm tra vân tay.”** Bước xác minh cục bộ và bằng chứng server nhận được cần được phân biệt.
- **“Có authenticator dự phòng nghĩa là mọi lần đăng nhập mạnh hơn.”** Khả năng của tài khoản không thay thế bằng chứng của lần sử dụng hiện tại.
- **“Thu hồi một phương tiện đã xử lý hết sự cố.”** Còn cần xem phiên, phương tiện khác và thay đổi tài khoản có liên quan.

Khi đọc một thiết kế IAM, hãy tự mô tả được bốn điều: authenticator nào được kiểm soát, nó đã gắn với tài khoản nào, verifier kiểm tra bằng chứng gì và khi nào phương tiện không còn được chấp nhận. Làm rõ những điểm này tạo nền tảng để học tiếp về credential, MFA, phiên đăng nhập và quản lý vòng đời danh tính.

# Assertion lifetime

## 1. Một assertion được sử dụng trong bao lâu?

Trong đăng nhập liên kết SAML, Identity Provider (IdP) phát hành assertion để Service Provider (SP) có căn cứ xác thực người dùng. **Assertion lifetime** là khoảng thời gian assertion có thể được chấp nhận cho mục đích đó. SP phải kiểm tra thời gian cùng với chữ ký, bên phát hành, bên nhận và các ràng buộc của luồng đăng nhập.

Ví dụ, cổng nhân sự nhận một assertion lúc 09:00:20 để tạo phiên cho nhân viên. Thiết kế có thể cho phép trình bày assertion trong vài phút, còn phiên ứng dụng tồn tại lâu hơn theo chính sách riêng. Việc assertion hết hạn sau đó không tự động khiến mọi request đang dùng phiên ứng dụng bị từ chối.

Đối với nền tảng IAM, cần trả lời ba câu hỏi riêng:

- Assertion này còn đủ điều kiện để thiết lập đăng nhập hay không?
- Lần xác thực của người dùng đã diễn ra cách đây bao lâu?
- Phiên truy cập hiện tại còn đáp ứng chính sách của ứng dụng hay không?

Nếu gom ba câu hỏi thành một giá trị thời gian, hệ thống có thể vừa cho phép dùng lại bằng chứng đăng nhập quá lâu, vừa xử lý phiên không đúng kỳ vọng.

## 2. Những mốc thời gian cần phân biệt

Các trường trong SAML không có cùng ý nghĩa:

| Vị trí hoặc trường | Ý nghĩa khi đọc assertion |
| --- | --- |
| `Assertion/@IssueInstant` | Thời điểm phát hành assertion; không tự biểu diễn hạn sử dụng |
| `Conditions/@NotBefore` | Cận bắt đầu hiệu lực của assertion, nếu có |
| `Conditions/@NotOnOrAfter` | Cận kết thúc hiệu lực của assertion, nếu có |
| `SubjectConfirmationData/@NotOnOrAfter` | Hạn của việc xác nhận chủ thể theo phương thức tương ứng |
| `AuthnStatement/@AuthnInstant` | Thời điểm người dùng được xác thực |
| `AuthnStatement/@SessionNotOnOrAfter` | Mốc kết thúc phiên giữa chủ thể và bên phát hành được mô tả trong statement, nếu có |

`NotBefore` bao gồm chính mốc bắt đầu; `NotOnOrAfter` loại trừ chính mốc kết thúc. Các giá trị thời gian dùng UTC. Các định nghĩa nằm trong SAML Core, mục 1.3.3, 2.3.3, 2.4.1.2, 2.5 và 2.7.2. [OASIS SAML Core 2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)

Từ bảng trên có thể hình dung một assertion được phát hành ngay bây giờ nhưng chứng thực một lần đăng nhập đã diễn ra trước đó. Muốn yêu cầu xác thực gần đây cho thao tác nhạy cảm, chỉ nhìn `IssueInstant` là chưa đủ.

## 3. Đọc khoảng hiệu lực trong Conditions

Đoạn XML sau chỉ minh họa một phần của assertion, không phải thông điệp SAML hoàn chỉnh để đưa vào vận hành:

```xml
<saml:Conditions
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    NotBefore="2026-11-20T09:00:00Z"
    NotOnOrAfter="2026-11-20T09:03:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>https://hr.example.test/saml/sp</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
```

Nếu tạm bỏ qua sai lệch đồng hồ, khoảng thời gian trong ví dụ là:

```text
09:00:00Z <= thời điểm SP kiểm tra < 09:03:00Z
```

| Thời điểm SP kiểm tra | Kết quả riêng của điều kiện thời gian |
| --- | --- |
| `08:59:59Z` | Chưa có hiệu lực |
| `09:00:00Z` | Đạt cận bắt đầu |
| `09:02:59Z` | Còn trong khoảng |
| `09:03:00Z` | Đã hết hạn |
| `09:03:01Z` | Đã hết hạn |

Đạt điều kiện thời gian chỉ cho phép tiếp tục đánh giá các điều kiện khác. Chẳng hạn, assertion trong ví dụ vẫn phải bị từ chối nếu đang được trình bày cho một SP không thuộc audience được phép.

Một lỗi ở biên thường gặp là dùng phép so sánh `now <= NotOnOrAfter`. Khi đó, phần mềm chấp nhận thêm đúng thời điểm mà tên trường đã yêu cầu loại trừ. Nên biểu diễn khoảng bằng ký hiệu `[bắt đầu, kết thúc)` trong tài liệu và ca kiểm thử để tránh hiểu nhầm.

## 4. Hạn của bearer SubjectConfirmation

Trong Web Browser SSO Profile, bearer `SubjectConfirmationData` cần có `Recipient` và `NotOnOrAfter`, không được có `NotBefore`; với phản hồi cho `AuthnRequest`, `InResponseTo` phải tương ứng với request. Khi dùng HTTP POST, SP phải chống replay bằng cách lưu các assertion ID đã dùng trong khoảng assertion còn được chấp nhận. [OASIS SAML Profiles 2.0, mục 4.1.4.2–4.1.4.5](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)

Đoạn minh họa cho một luồng SP khởi tạo đăng nhập:

```xml
<saml:SubjectConfirmation
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
  <saml:SubjectConfirmationData
      Recipient="https://hr.example.test/saml/acs"
      InResponseTo="_request-example-01"
      NotOnOrAfter="2026-11-20T09:02:00Z" />
</saml:SubjectConfirmation>
```

Ghép đoạn này với `Conditions` ở phần trước, ta có hai cận trên:

```text
Conditions kết thúc:                 09:03:00Z
Bearer confirmation kết thúc:        09:02:00Z
```

Trong ví dụ có đúng một bearer confirmation này, thời điểm `09:02:30Z` không còn phù hợp để xác nhận bearer, dù `Conditions` vẫn còn hiệu lực. Không chọn mốc muộn hơn để bỏ qua một ràng buộc đã thất bại.

Với dữ liệu có nhiều phương thức hoặc nhiều `SubjectConfirmation`, thư viện phải đánh giá một phương án xác nhận phù hợp và đầy đủ. Không lấy một trường từ phương án thứ nhất rồi ghép với trường của phương án thứ hai để tạo ra phương án giả định luôn hợp lệ.

## 5. Clock skew: cho phép sai lệch đồng hồ có giới hạn

Giả sử đồng hồ IdP đi nhanh hơn SP 15 giây. IdP vừa phát hành assertion với `NotBefore` bằng thời điểm hiện tại của nó; SP có thể thấy assertion đang nằm trong tương lai. Ngược lại, SP đi nhanh có thể cho rằng assertion vừa hết hạn.

**Clock skew allowance** là mức dung sai được cấu hình để xử lý sai lệch này. Đây là quyết định vận hành, không phải một giá trị mặc định nên sao chép giữa mọi hệ thống.

Một mô hình tính minh họa với `N` là thời điểm kiểm tra, `B` là cận bắt đầu, `E` là cận kết thúc và `Δ` là dung sai không âm:

```text
Kiểm tra cận bắt đầu:  N + Δ >= B
Kiểm tra cận kết thúc: N - Δ < E
```

Với `Δ = 30 giây`, khoảng Conditions của ví dụ được chấp nhận về mặt thời gian từ `08:59:30Z` đến trước `09:03:30Z`. Với bearer confirmation đã chọn, cận trên tương ứng là trước `09:02:30Z`. Đây là hệ quả của mô hình trên, không phải giá trị cấu hình bắt buộc của SAML.

Mức dung sai càng lớn thì khoảng chấp nhận thực tế càng rộng. Cần đồng bộ thời gian trên IdP, các node SP và hạ tầng liên quan; theo dõi độ lệch; rồi chọn dung sai dựa trên dữ liệu vận hành và yêu cầu bảo mật. Tăng skew để che giấu đồng hồ sai hàng chục phút sẽ làm suy yếu mục đích của lifetime ngắn.

Khi tích hợp thư viện, cần xác định nó đã áp dụng skew ở đâu. Nếu adapter và thư viện cùng cộng một mức dung sai cho cùng phép kiểm tra, cửa sổ thực tế có thể rộng hơn dự kiến. Đồng thời, chính sách giới hạn tuổi tối đa phải ghi rõ có cho phép dung sai riêng hay không.

## 6. Giới hạn thời gian từ phía SP

SP không nên chỉ hỏi “IdP có ghi một hạn hết hạn ở đâu đó không?”. Một chính sách tích hợp có thể bổ sung các ràng buộc sau:

| Ràng buộc của SP | Vấn đề cần kiểm soát |
| --- | --- |
| Tuổi tối đa từ `IssueInstant` | Tránh chấp nhận assertion đã phát hành quá lâu theo chính sách địa phương |
| Giới hạn thời điểm phát hành trong tương lai | Phát hiện đồng hồ lệch hoặc thông điệp không hợp lý |
| Thời gian chờ của request đăng nhập | Không chấp nhận phản hồi gắn với một giao dịch đã đóng |
| Tuổi tối đa của lần xác thực | Yêu cầu người dùng xác thực đủ gần thời điểm thao tác |
| Các trường thời gian bắt buộc theo hợp đồng tích hợp | Không biến dữ liệu thiếu thành thời hạn vô hạn |

Đây là ví dụ thiết kế chính sách SP; phải cấu hình theo profile, thư viện và thỏa thuận với IdP. Một thuộc tính tùy chọn trong schema tổng quát không có nghĩa SP phải chấp nhận thiếu thuộc tính đó trong mọi tích hợp.

Có thể mô hình hóa cận trên của ví dụ đơn giản như sau:

```text
Hạn chấp nhận = mốc sớm nhất trong các cận trên áp dụng:
  - Conditions.NotOnOrAfter, nếu có;
  - SubjectConfirmationData.NotOnOrAfter của phương án được chọn;
  - IssueInstant + tuổi tối đa mà SP cho phép;
  - hạn giao dịch đăng nhập đang chờ.
```

Mỗi cận có thể có quy tắc dung sai riêng. Đừng cộng skew vào toàn bộ biểu thức nếu chính sách chỉ cho phép skew đối với timestamp do IdP gửi.

Với thao tác nâng đặc quyền, tuổi assertion và tuổi lần xác thực cần được đánh giá riêng. Ví dụ, một assertion được phát hành lúc 09:00 có thể mang `AuthnInstant` lúc 07:00. Chính sách yêu cầu xác thực trong vòng 10 phút sẽ không được thỏa mãn chỉ vì assertion mới phát hành.

## 7. Lifetime ngắn và chống replay giải quyết hai vấn đề khác nhau

Giả sử kẻ tấn công lấy được bản sao assertion có thể trình bày trong hai phút. Rút lifetime xuống 30 giây làm cửa sổ tấn công ngắn hơn, nhưng trong 30 giây đó vẫn cần chặn dùng lại assertion đã được tiêu thụ.

Thiết kế một replay cache cho cụm SP cần cân nhắc:

1. Khóa nhận diện gắn với assertion ID và phạm vi issuer hoặc tenant thích hợp, thay vì chỉ dựa vào tên người dùng.
2. Thao tác đánh dấu đã dùng có tính nguyên tử, trước khi tạo phiên thành công. Hai request đồng thời không được cùng thấy trạng thái “chưa dùng”.
3. Các node xử lý cùng một tích hợp có cùng khả năng phát hiện replay; cache riêng từng node có thể bị vượt qua khi request chuyển node.
4. Bản ghi tồn tại ít nhất đến hết khoảng assertion còn có thể được chấp nhận, tính cả dung sai thực tế liên quan.
5. Khi kho chống replay không khả dụng, xử lý theo chính sách lỗi đã định trước; không âm thầm bỏ kiểm tra rồi tạo phiên.

Ví dụ, bearer confirmation hết hạn lúc `09:02:00Z` nhưng validator có thể chấp nhận đến trước `09:02:30Z`. Nếu xóa bản ghi chống replay ngay lúc `09:02:00Z`, hệ thống tạo ra khoảng trống 30 giây. Sau khi cache quên ID, bản sao assertion có thể tiếp tục vượt qua điều kiện thời gian.

Không kéo dài TTL bằng dữ liệu thời gian tùy ý của một thông điệp chưa được tin cậy. Trước khi ghi cache, hệ thống cần hoàn tất các kiểm tra mật mã và giới hạn chính sách tương ứng, tránh để dữ liệu giả tạo chiếm tài nguyên lâu dài.

## 8. Tách assertion lifetime khỏi phiên ứng dụng

Xét một thiết kế minh họa:

```text
09:00:00  IdP phát hành assertion
09:00:20  SP xác minh và tiêu thụ assertion, tạo phiên ứng dụng
09:02:00  Bearer confirmation hết hạn
09:30:00  Phiên có thể hết idle timeout nếu người dùng không hoạt động
10:00:20  Phiên đạt absolute timeout theo chính sách ví dụ
```

Các mốc trên thuộc những bộ kiểm soát khác nhau. Từ lúc đã tạo phiên, request nghiệp vụ thường mang cookie phiên của SP. SP phải kiểm soát cookie, trạng thái phiên, thời gian không hoạt động, thời hạn tuyệt đối và quyền truy cập hiện tại của người dùng.

`SessionNotOnOrAfter` cần được tích hợp theo ngữ nghĩa và chính sách phiên của sản phẩm; không tự động thay thế mọi timeout của SP. Trong một thiết kế yêu cầu ràng buộc phiên SP theo mốc này, SP phải thực thi ràng buộc đó rõ ràng và vẫn có thể đặt thời hạn địa phương ngắn hơn.

Tương tự, một nhân viên bị thu hồi quyền sau khi đã đăng nhập có thể vẫn sở hữu phiên. Giảm assertion lifetime không tự giải quyết việc thu hồi phiên hoặc quyền đã lưu trong session. IAM cần cơ chế cập nhật quyền, vô hiệu hóa phiên hoặc yêu cầu xác thực lại phù hợp với rủi ro của nghiệp vụ.

## 9. Luồng kiểm tra minh họa

Mã giả dưới đây thể hiện vị trí của lifetime trong luồng xác thực, không phải mã triển khai đầy đủ của một SAML validator:

```text
nhận Response tại ACS
  -> phân tích bằng thư viện SAML với cấu hình XML an toàn
  -> xác minh cấu trúc, chữ ký và liên kết tới đúng assertion được sử dụng
  -> kiểm tra issuer, audience, recipient và giao dịch tương ứng
  -> chọn và kiểm tra đầy đủ một subject confirmation phù hợp
  -> kiểm tra mọi ràng buộc thời gian và chính sách tuổi xác thực
  -> kiểm tra các Conditions còn lại
  -> đánh dấu assertion ID đã dùng bằng thao tác nguyên tử
  -> tạo phiên ứng dụng theo chính sách của SP
```

Chỉ các giá trị thuộc nội dung đã được xác minh tính toàn vẹn mới được dùng làm căn cứ tin cậy. Việc đọc được một timestamp hợp lệ về cú pháp không chứng minh timestamp đó do IdP đáng tin cậy phát hành.

Trong phần kiểm tra thời gian, nên lấy một giá trị `now` cho lần đánh giá liên quan, dùng kiểu thời gian biểu diễn một thời điểm tuyệt đối và từ chối dữ liệu không parse được. So sánh chuỗi ngày giờ hoặc chuyển timestamp sang giờ địa phương rồi bỏ thông tin múi giờ dễ gây lỗi.

Khi nhiều node cùng xử lý, cần áp dụng cùng chính sách lifetime và skew. Nếu node A chấp nhận assertion nhưng node B từ chối tại cùng một thời điểm, người dùng sẽ gặp lỗi phụ thuộc node, rất khó phân biệt với lỗi mạng hoặc lỗi trình duyệt.

## 10. Kiểm thử và quan sát vận hành

Có thể xây dựng bộ kiểm thử bằng đồng hồ điều khiển được, thay vì chờ thời gian thực trôi qua:

| Tình huống | Kỳ vọng cần kiểm chứng |
| --- | --- |
| Ngay trước, đúng và ngay sau `NotBefore` | Đúng quy tắc cận bắt đầu và skew đã chọn |
| Ngay trước, đúng và ngay sau `NotOnOrAfter` | Đúng quy tắc cận kết thúc loại trừ |
| Conditions còn hạn, bearer confirmation hết hạn | Không tạo phiên bằng confirmation đã hết hạn |
| Assertion mới nhưng lần xác thực quá cũ | Chính sách tuổi xác thực hoạt động độc lập |
| Thiếu trường bắt buộc hoặc timestamp sai định dạng | Từ chối rõ nguyên nhân, không cấp thời hạn vô hạn |
| Hai lần gửi cùng assertion đồng thời tới hai node | Chỉ một lần có thể tiêu thụ assertion thành công |
| Phát lại sau hạn gốc nhưng còn trong skew | Replay cache vẫn chặn được |
| Assertion hết hạn sau khi phiên đã được tạo | Phiên được xử lý theo chính sách phiên đã thiết kế |

Khi phân tích lỗi thời gian, nên ghi mã lỗi riêng như `ASSERTION_NOT_YET_VALID`, `ASSERTION_EXPIRED`, `SUBJECT_CONFIRMATION_EXPIRED` hoặc `AUTHENTICATION_TOO_OLD`. Những tên này là ví dụ mã lỗi nội bộ, không phải status code bắt buộc của chuẩn SAML.

Log có thể chứa thời điểm nhận, node xử lý, issuer đã xác minh, các cận thời gian cần thiết và mức skew cấu hình. Hạn chế dữ liệu nhận diện; không ghi toàn bộ SAML Response, assertion hoặc thông tin nhạy cảm chỉ để điều tra lỗi hết hạn.

## 11. Vận dụng vào thiết kế IAM

Khi tích hợp một IdP mới, nhóm phụ trách nên thống nhất thời gian cho phép chuyển giao assertion, tuổi tối đa SP chấp nhận, độ lệch đồng hồ, thời gian chờ request, tuổi lần xác thực cho thao tác nhạy cảm và chính sách phiên sau đăng nhập. Những giá trị ví dụ trong bài không thay thế quá trình thống nhất đó.

Một hệ thống kiểm soát tốt lifetime sẽ từ chối bằng chứng đến quá sớm, quá muộn hoặc đã bị dùng lại, trong khi vẫn giữ chính sách phiên và vòng đời quyền nhất quán. Với tài khoản đặc quyền, cần phối hợp lifetime với yêu cầu MFA hoặc xác thực lại, giới hạn phiên và cơ chế thu hồi quyền; không coi một assertion còn hạn là quyền truy cập vô điều kiện.

# FAL1

## 1. FAL1 là gì?

**Federation Assurance Level 1 — FAL1** là mức bảo đảm cơ bản cho giao dịch liên kết danh tính trong bộ hướng dẫn NIST. Mức này tập trung vào việc bên sử dụng danh tính nhận và kiểm tra assertion từ bên cung cấp danh tính để thiết lập phiên cho đúng chủ thể.

Bài học sử dụng **NIST SP 800-63C-4, bản final tháng 7/2025**, làm mốc yêu cầu. Cần ghi rõ phiên bản khi mô tả hoặc đánh giá một mức FAL, vì cách tổ chức yêu cầu đã thay đổi qua các bản. [Thông tin xuất bản chính thức](https://csrc.nist.gov/pubs/sp/800/63/c/4/final)

Trong kiến trúc thường gặp:

- **Identity Provider — IdP** xác thực người dùng và phát hành assertion.
- **Relying Party — RP** nhận, kiểm tra assertion và thiết lập phiên tại ứng dụng.
- **Assertion** là phát biểu có thể kiểm chứng về chủ thể hoặc sự kiện xác thực. ID token trong OIDC và SAML assertion là những ví dụ.
- **Subscriber** là người có tài khoản được sử dụng trong quá trình liên kết danh tính.

FAL1 cho phép nhiều lựa chọn triển khai, nhưng vẫn có yêu cầu bắt buộc. Một ứng dụng chỉ giải mã token rồi lấy tên người dùng chưa đủ căn cứ kết luận giao dịch được bảo vệ ở FAL1.

Sau bài học, bạn có thể phân biệt các yêu cầu chính của FAL1, giải thích bearer assertion, thiết kế việc kiểm tra tại RP và nhận ra giới hạn của mức bảo đảm này trong một hệ thống IAM.

## 2. FAL1 không đồng nghĩa IAL1, AAL1 hoặc quyền thấp

| Khía cạnh | Câu hỏi chính |
|---|---|
| Identity Assurance Level — IAL | Tài khoản đã được liên hệ với danh tính thực bằng quy trình nào? |
| Authentication Assurance Level — AAL | Lần xác thực bằng authenticator có mức bảo đảm ra sao? |
| Federation Assurance Level — FAL | Giao dịch chuyển và tiếp nhận bằng chứng danh tính được bảo vệ thế nào? |
| Phân quyền | Chủ thể được thực hiện hành động nào trên tài nguyên nào? |

Các trục được lựa chọn theo rủi ro và mục đích dịch vụ; không bắt buộc có cùng số mức. [NIST: Digital Identity Risk Management](https://pages.nist.gov/800-63-4/sp800-63/dirm/)

Ví dụ, người dùng có thể xác thực bằng cơ chế mạnh tại IdP nhưng RP vẫn tiếp nhận phản hồi sai giao dịch. Bảo vệ tốt ở bước xác thực không tự sửa lỗi ở bước federation.

Ngược lại, việc RP kiểm tra federation đúng không tạo quyền xem mọi tài nguyên. Sau khi thiết lập phiên, ứng dụng vẫn áp dụng RBAC, ABAC, quan hệ với tài nguyên và các điều kiện ít quyền nhất đã thiết kế.

Không nên biểu diễn FAL1 như một vai trò nghiệp vụ. Nhãn này không có nghĩa người dùng chỉ được đọc, không được ghi hoặc chắc chắn không có đặc quyền; chính sách cấp quyền phải quyết định những việc đó riêng biệt.

## 3. Yêu cầu nổi bật của FAL1 theo Revision 4

| Nội dung | Vị trí trong FAL1 |
|---|---|
| IdP ký assertion bằng cơ chế mật mã được chấp nhận | Bắt buộc |
| RP kiểm tra chữ ký bằng khóa gắn với IdP dự kiến | Bắt buộc |
| Assertion giới hạn audience; RP xác nhận mình thuộc tập bên nhận | Bắt buộc |
| Chống phát lại assertion tại mỗi RP | Bắt buộc |
| Chống assertion injection | Khuyến nghị trong định nghĩa FAL1 |
| Giao dịch được khởi tạo tại RP | Khuyến nghị |
| Audience chỉ gồm một RP | Khuyến nghị; có thể gồm nhiều RP |
| Thỏa thuận tin cậy | Có thể thiết lập trước hoặc theo subscriber |
| Thiết lập định danh và khóa | Có thể động hoặc thủ công |

FAL1 cũng chịu các yêu cầu chung của federation. Bảng không thay thế việc đánh giá toàn bộ điều khoản áp dụng. Trong tài liệu NIST, **SHALL** biểu thị yêu cầu bắt buộc, **SHOULD** biểu thị khuyến nghị và **MAY** biểu thị lựa chọn được phép. [NIST: Federation Assurance Level, mục 2.2](https://pages.nist.gov/800-63-4/sp800-63c/fal/#federation-assurance-level-1-fal1)

Một khuyến nghị ở phần phân mức không cho phép bỏ yêu cầu bắt buộc khác của giao thức hoặc cách trình assertion. Chẳng hạn, các điều khoản cụ thể về front channel và back channel còn quy định bảo vệ tại RP. Hồ sơ tích hợp phải xét những điều khoản đó cùng nhau.

## 4. Bearer assertion và phạm vi bên nhận

### 4.1. Bearer assertion là gì?

Với bearer assertion, RP không yêu cầu người trình cung cấp thêm bằng chứng kiểm soát authenticator theo cơ chế holder-of-key hoặc bound authenticator của FAL3. RP vẫn phải kiểm tra assertion và các điều kiện của giao dịch.

“Bearer” không có nghĩa bất kỳ chuỗi nào cũng được chấp nhận hoặc assertion được phép dùng lại vô hạn. Các kiểm tra nguồn, tính toàn vẹn, audience, thời gian và chống phát lại vẫn có vai trò bảo vệ. [NIST: Bearer Assertions](https://pages.nist.gov/800-63-4/sp800-63c/Federation/#bearer-assertions)

Ví dụ, kẻ tấn công có một assertion thật nhưng dành cho RP khác. Việc assertion có chữ ký hợp lệ không làm nó trở thành bằng chứng phù hợp cho RP hiện tại.

### 4.2. Một hoặc nhiều audience

FAL1 cho phép assertion dành cho một RP hoặc một tập RP được xác định. Mỗi RP phải xác nhận mình là bên nhận phù hợp và thực hiện chống phát lại trong phạm vi của mình.

Một mô hình dữ liệu khái niệm có thể là:

```json
{
  "assertion_id": "assertion_739",
  "issuer": "company-idp",
  "subject": "subject_1042",
  "audiences": ["portal-a", "portal-b"],
  "issued_at": "2026-11-25T03:00:00Z",
  "expires_at": "2026-11-25T03:02:00Z"
}
```

Đây là mô hình minh họa, không phải một token hoàn chỉnh hoặc tập trường bắt buộc của OIDC. Nội dung cần được bảo vệ theo giao thức; chỉ có JSON không tạo ra assertion đáng tin cậy.

Với ví dụ trên, portal C không được chấp nhận assertion chỉ vì cũng dùng company-idp. Portal A và portal B quản lý việc tiếp nhận theo phạm vi riêng; chấp nhận ở A không tự tạo quyền chấp nhận nhiều lần ở A.

Trong thiết kế mới, giới hạn một RP giúp giảm nơi assertion có thể được sử dụng. Việc cho phép nhiều audience là khả năng của mức bảo đảm, không phải lý do để phát hành assertion cho mọi ứng dụng.

### 4.3. Không nhầm assertion với access token và phiên

| Đối tượng | Cách sử dụng cần phân biệt |
|---|---|
| Assertion đăng nhập | Đại diện cho một sự kiện xác thực, được xử lý để thiết lập phiên tại RP |
| Access token | Được API kiểm tra theo mô hình truy cập và phạm vi được cấp |
| Cookie hoặc định danh phiên | Liên kết các yêu cầu tiếp theo với phiên ứng dụng |

Quy tắc chống phát lại assertion không có nghĩa mọi access token hoặc cookie phải trở thành đối tượng dùng một lần. Cần xử lý từng loại theo đúng giao thức và vòng đời của nó.

Ví dụ, sau khi assertion được chấp nhận, trình duyệt sử dụng phiên ứng dụng cho các lần tải trang tiếp theo. Ứng dụng không cần nhận lại cùng assertion để đăng nhập lại ở mỗi lần tải trang.

## 5. Những gì RP phải kiểm tra

### 5.1. Khóa phải thuộc về nguồn được chấp nhận

Kiểm tra mật mã cần đi cùng kiểm tra nguồn tin cậy. Một token có thể được ký đúng bằng khóa của kẻ tấn công; điều đó không chứng minh nó đến từ IdP mà RP được phép sử dụng.

RP cần liên hệ định danh IdP với khóa và cấu hình tương ứng theo quan hệ tin cậy. Không lấy một địa chỉ khóa tùy ý từ request hoặc từ token rồi mặc định tin mọi dữ liệu kiểm tra được bằng khóa đó.

Quản lý khóa cũng bao gồm thay đổi, xoay vòng và xử lý khi không tải được khóa phù hợp. Không nên chuyển sang bỏ kiểm tra chữ ký chỉ để giữ chức năng đăng nhập hoạt động.

### 5.2. Kiểm tra điều kiện ngoài chữ ký

Trong mô hình IdP dùng chung, các kiểm tra bao gồm bên phát hành dự kiến, thời hạn, audience, nonce khi áp dụng, điều kiện mức bảo đảm và việc assertion chưa bị phát lại tại RP. [NIST: Assertion Contents và kiểm tra tại RP](https://pages.nist.gov/800-63-4/sp800-63c.html#assertion-contents)

Các câu hỏi triển khai tương ứng là:

1. Đã nhận đúng loại phản hồi cho bước hiện tại của giao thức chưa?
2. Bên phát hành có nằm trong phạm vi được chấp nhận không?
3. Cơ chế mật mã, khóa và dữ liệu được bảo vệ có đúng cấu hình không?
4. RP có phải bên nhận của assertion không?
5. Cửa sổ hiệu lực có phù hợp thời điểm xử lý không?
6. Có liên hệ đúng với yêu cầu hoặc phiên ban đầu theo giao thức không?
7. Bằng chứng đã được xử lý trước đó tại RP chưa?
8. Thông tin bảo đảm có đáp ứng chính sách cho chức năng đang truy cập không?

Danh sách là cách tổ chức trách nhiệm, không phải mã kiểm tra hoàn chỉnh. Nên sử dụng thành phần hỗ trợ giao thức đã được kiểm chứng, đồng thời hiểu cách cấu hình và xử lý lỗi.

### 5.3. Ánh xạ chủ thể đúng tài khoản

Sau khi assertion hợp lệ, RP vẫn phải ánh xạ về tài khoản đúng. Với OIDC, cần xét định danh chủ thể trong không gian tên của bên phát hành, không coi một giá trị `sub` đứng riêng là duy nhất trên mọi IdP.

Ví dụ, hai IdP cùng phát hành `sub=42` có thể đang nói về hai người khác nhau. Nếu RP chỉ lưu `42`, người từ một miền có thể bị gắn với tài khoản của miền còn lại.

Tương tự, email trùng không đủ để tự chuyển dữ liệu của tài khoản cũ sang người mới. Một assertion được kiểm tra đúng vẫn có thể dẫn đến chiếm tài khoản nếu bước liên kết bên trong ứng dụng sai.

## 6. Chống phát lại: thời hạn ngắn chưa đủ

### 6.1. Phát lại trong cửa sổ còn hiệu lực

Giả sử assertion còn hiệu lực trong hai phút. Sau khi đã được RP chấp nhận, nó được gửi lại trong cùng khoảng thời gian đó. Nếu RP chỉ kiểm tra thời gian, lần gửi lại vẫn vượt qua điều kiện này.

Vì vậy, cần cơ chế phân biệt và ngăn assertion bị tiếp nhận lại ngoài điều kiện được phép. Các giao thức có thể dùng định danh assertion, nonce hoặc các thông tin liên quan; không nên mặc định mọi định dạng đều có cùng một trường tên `jti`.

Thời hạn ngắn giúp giới hạn khoảng phơi nhiễm, nhưng không thay thế việc xử lý chống phát lại. Ngược lại, việc đã có kho theo dõi sử dụng không cho phép bỏ kiểm tra hết hạn.

### 6.2. Xử lý đồng thời và nhiều instance

Một RP có thể chạy nhiều instance. Nếu mỗi instance chỉ giữ thông tin assertion đã dùng trong bộ nhớ riêng, hai yêu cầu đồng thời đến hai instance có thể cùng được coi là lần đầu.

Thiết kế cần bảo đảm tính nhất quán phù hợp cho việc tiếp nhận. Chẳng hạn, một bản ghi sử dụng được tạo theo thao tác có điều kiện hoặc cơ chế giao thức tương đương, để không có hai luồng cùng xác nhận một bằng chứng chưa được dùng.

Phạm vi khóa theo dõi cũng cần đúng: có thể phải xét IdP, RP và định danh assertion, tùy hợp đồng dữ liệu. Không giả định cùng một chuỗi định danh từ hai nguồn khác nhau luôn là cùng một bằng chứng.

Nếu thành phần cần cho chống phát lại không khả dụng, RP phải xử lý theo hành vi đã thiết kế để vẫn đáp ứng yêu cầu. Tự bỏ kiểm tra rồi tạo phiên sẽ tạo một đường đăng nhập không có các điều kiện đã công bố.

### 6.3. Yêu cầu lặp do trình duyệt

Người dùng có thể tải lại callback hoặc trình duyệt có thể gửi lại yêu cầu. Hệ thống cần phân biệt việc hiển thị lại kết quả hoặc dùng phiên đã tồn tại với việc tiếp nhận lại assertion như một lần xác thực mới.

Không nên giải quyết trải nghiệm tải lại bằng cách mở lại mọi bằng chứng đã dùng. Cách xử lý cần gắn với đúng giao dịch và phiên, đồng thời tránh tiết lộ thông tin phiên cho bên khác.

## 7. Chống assertion injection ở FAL1

Assertion injection xảy ra khi RP bị đưa vào xử lý assertion hoặc tham chiếu assertion sai ngữ cảnh, từ đó gắn phiên với chủ thể không đúng. Bằng chứng có thể bị đánh cắp hoặc được tạo ra cho một luồng khác.

Ví dụ, RP đang chờ phản hồi cho trình duyệt X, nhưng callback nhận dữ liệu của giao dịch Y. Kiểm tra chữ ký riêng lẻ có thể thành công dù phản hồi không thuộc lần đăng nhập đang xử lý.

SP 800-63C-4 nêu khuyến nghị chống injection ở FAL1; các điều khoản về cách trình assertion còn đưa ra những yêu cầu cụ thể. Những cơ chế có thể tham gia bảo vệ gồm ràng buộc giao dịch, nonce, kiểm soát trạng thái và kênh trao đổi phù hợp. [NIST: Protection From Assertion Injection Attacks](https://pages.nist.gov/800-63-4/sp800-63c/Federation/#protection-from-assertion-injection-attacks)

Điểm cần học là đọc đồng thời phần phân mức, yêu cầu chung và giao thức được chọn. Không nên lấy một từ “khuyến nghị” để vô hiệu hóa kiểm tra bắt buộc của thư viện hoặc profile đang triển khai.

RP khởi tạo giao dịch giúp có trạng thái để chờ đúng phản hồi. Tuy nhiên, chỉ đổi nơi bắt đầu hoặc thêm một giá trị ngẫu nhiên mà không kiểm tra đúng lúc cũng chưa chứng minh cơ chế bảo vệ đã có hiệu lực.

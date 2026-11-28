# MFA cho break-glass

## 1. Break-glass cần giải quyết hai yêu cầu cùng lúc

**Break-glass** là cơ chế truy cập khẩn cấp được chuẩn bị trước để người có thẩm quyền xử lý tình huống mà đường truy cập thông thường không đáp ứng được yêu cầu vận hành. Ví dụ: IdP không hoạt động, PAM control plane gặp sự cố hoặc hệ thống phê duyệt không khả dụng trong lúc cần khôi phục một dịch vụ quan trọng.

Trong quản lý truy cập đặc quyền (PAM), break-glass không nên được hiểu là một công tắc tắt mọi kiểm soát. Nó là một tuyến truy cập riêng, có điều kiện kích hoạt, danh tính, phạm vi, thời hạn và bằng chứng sử dụng.

Bài toán MFA cho break-glass có hai mặt:

- Giảm nguy cơ một người có được mật khẩu khẩn cấp là lập tức có toàn quyền.
- Giữ khả năng xác thực và khôi phục khi một số thành phần của đường truy cập thông thường đã hỏng.

Nếu tài khoản khẩn cấp phụ thuộc hoàn toàn vào chính IdP đang cần sửa, nó có thể không giúp được trong sự cố IdP. Nếu tài khoản đó chỉ dùng mật khẩu quản trị tồn tại nhiều năm và không có giám sát, nó có thể trở thành đường truy cập yếu nhất.

Mục tiêu là thiết kế mức xác thực phù hợp với rủi ro **và** với các kịch bản sự cố cụ thể. Không thể đánh giá một thiết kế chỉ bằng câu hỏi “tài khoản break-glass đã bật MFA chưa?”.

Sau bài học, bạn có thể:

- Phân biệt truy cập khẩn cấp với khôi phục authenticator.
- Xác định sự phụ thuộc làm MFA không sử dụng được trong sự cố.
- Thiết kế tuyến MFA độc lập đủ dùng cho từng kịch bản.
- Giới hạn quyền, thời gian và tác động của tài khoản khẩn cấp.
- Kiểm chứng việc sử dụng, thu hồi và khôi phục trạng thái an toàn.

## 2. Phân biệt các tình huống thường bị gộp chung

### 2.1. Cần vượt tuyến phê duyệt, không phải vượt MFA

Một sự cố cần xử lý ngay nhưng chủ hệ thống chưa phản hồi không có nghĩa dịch vụ MFA đã hỏng. Nếu IdP và authenticator vẫn hoạt động, tuyến khẩn cấp có thể giữ nguyên yêu cầu MFA và thay đổi cách chấp thuận theo chính sách đã được tổ chức ban hành.

Ví dụ: cho phép một người trực sự cố đủ điều kiện kích hoạt quyền ngắn hạn theo quy trình khẩn cấp, đồng thời thông báo cho chủ hệ thống và hậu kiểm. Đây là thay đổi tuyến cấp quyền, không phải lý do bỏ yếu tố xác thực.

### 2.2. Hệ thống xác thực thông thường không khả dụng

Khi IdP hoặc dịch vụ MFA không hoạt động, cần một tuyến xác thực không phụ thuộc vào thành phần đã hỏng. Tuyến này phải được chuẩn bị và thử nghiệm trước.

Không nên xử lý sự cố bằng cách tạo vội một tài khoản quản trị không giới hạn rồi quên thu hồi. Cũng không nên cho phép mọi tài khoản thường tự động chuyển sang mật khẩu đơn khi dịch vụ MFA trả lỗi.

### 2.3. Người dùng mất authenticator

Mất điện thoại hoặc security key là vấn đề vòng đời authenticator. Trước hết cần dùng quy trình khôi phục danh tính đã được kiểm soát.

Nếu đồng thời có sự cố khẩn cấp, tổ chức có thể cho phép một tuyến khác, nhưng vẫn phải xác minh người thao tác và giới hạn quyền theo chính sách. Không thể coi câu nói “tôi đang xử lý sự cố” là bằng chứng đủ để đăng ký yếu tố mới cho một tài khoản đặc quyền.

### 2.4. Hệ thống đích không hỗ trợ MFA theo kiến trúc hiện có

Một số hệ thống cũ có thể chỉ hỗ trợ mật khẩu hoặc một cơ chế không đáp ứng MFA. Khi đó phải ghi rõ giới hạn và thiết kế lớp kiểm soát phía trước nếu có thể, chẳng hạn một cổng quản trị độc lập thực sự áp dụng MFA.

Nếu cần truy cập trực tiếp bỏ qua cổng, mức bảo đảm có thể thấp hơn. Các kiểm soát bù phải được đánh giá và chấp nhận theo thẩm quyền, không được mô tả như thể hệ thống đích đã có MFA.

| Tình huống | Hướng thiết kế chính |
|---|---|
| Cần xử lý nhanh, IdP và MFA vẫn hoạt động | Giữ MFA, dùng tuyến cấp quyền khẩn cấp được định nghĩa trước |
| IdP hoặc dịch vụ MFA trung tâm lỗi | Dùng tuyến xác thực khẩn cấp phù hợp, không phụ thuộc vào thành phần lỗi |
| Mất authenticator cá nhân | Khôi phục có xác minh; không tự chuyển thành miễn MFA |
| PAM không khả dụng nhưng hệ thống đích còn hoạt động | Dùng đường quản trị dự phòng đã được kiểm soát và thử nghiệm |
| Hệ thống đích không hỗ trợ MFA | Dùng lớp thực thi phù hợp hoặc ngoại lệ có kiểm soát, ghi rõ giới hạn |

## 3. MFA khác với kiểm soát hai người

### 3.1. Nhiều bí mật cùng loại không tạo thành MFA

Các nhóm yếu tố thường gồm điều người dùng biết, vật người dùng sở hữu và đặc điểm của người dùng.

Ví dụ một security key dùng khóa mật mã cùng bước xác minh người dùng bằng PIN có thể cung cấp nhiều yếu tố khi giải pháp thực sự hỗ trợ và kiểm tra cơ chế đó. Một mật khẩu cộng một mật khẩu khác vẫn chủ yếu dựa vào kiến thức.

Tương tự, tách mật khẩu thành hai phần do hai người giữ không tự biến mật khẩu đó thành MFA. Việc tách giữ có thể tạo kiểm soát hai người trong quy trình lấy bí mật, nhưng hệ thống đích có thể vẫn chỉ xác thực bằng một mật khẩu sau khi ghép lại.

### 3.2. Hai người tham gia trả lời một câu hỏi khác

**Dual control** hoặc kiểm soát hai người giúp hạn chế việc một cá nhân tự ý lấy và sử dụng quyền khẩn cấp. **MFA** giúp hệ thống xác minh danh tính dựa trên nhiều yếu tố.

Hai cơ chế bổ sung cho nhau:

~~~text
Kiểm soát hai người:
    Có đủ người có thẩm quyền tham gia quyết định hoặc lấy quyền không?

MFA:
    Người đang xác thực có cung cấp được các yếu tố bắt buộc không?

Cấp quyền:
    Danh tính đã xác thực được phép làm gì, ở đâu và đến khi nào?
~~~

Một người có thể MFA thành công nhưng không có thẩm quyền kích hoạt break-glass. Hai người có thể đồng ý cấp quyền nhưng người kết nối vẫn phải xác thực theo tuyến đã định nghĩa.

### 3.3. User presence không tự bằng user verification

Một thao tác chạm security key có thể chứng minh sự hiện diện của người dùng, nhưng không nhất thiết cho biết authenticator đã xác minh bằng PIN hoặc sinh trắc.

Nếu chính sách dựa vào user verification để đáp ứng mức bảo đảm, bộ xác minh phải yêu cầu và kiểm tra kết quả tương ứng. Không chỉ nhìn nhãn “hardware key” rồi kết luận mọi trường hợp đều đạt MFA.

Đối với passkey, cần đánh giá cách lưu khóa, phương thức xác minh, cách đồng bộ nếu có và đường khôi phục. Không suy ra tính độc lập với IdP hoặc dịch vụ đám mây chỉ từ tên phương thức.

## 4. Phân tích sự phụ thuộc trước khi chọn phương thức

### 4.1. Vẽ đường xác thực bình thường

Một đường truy cập thường có thể gồm:

~~~text
Máy trạm quản trị
  → mạng và DNS
  → IdP
  → dịch vụ MFA
  → PAM portal
  → vault hoặc dịch vụ cấp quyền
  → gateway
  → hệ thống đích
~~~

Mỗi thành phần có thể là một điểm khiến truy cập không thực hiện được. Một phương thức MFA mạnh trên giấy vẫn không giúp khôi phục nếu người vận hành không thể tới được bộ xác minh hoặc không thể lấy công cụ cần thiết.

### 4.2. Lập ma trận phụ thuộc theo kịch bản

| Thành phần | Câu hỏi cần kiểm tra | Hệ quả thiết kế |
|---|---|---|
| IdP | Tài khoản khẩn cấp có cần IdP lỗi để đăng nhập không? | Có thể cần tuyến xác minh cục bộ hoặc độc lập |
| Vault | Mật khẩu dự phòng có chỉ nằm trong vault đang hỏng không? | Cần cơ chế lấy bí mật dự phòng được quản trị |
| Mạng quản trị | Có đường tới gateway hoặc console khi mạng thường lỗi không? | Cần tuyến quản trị ngoài băng nếu kịch bản yêu cầu |
| DNS và chứng thư | Việc truy cập có phụ thuộc vào dịch vụ đang lỗi không? | Chuẩn bị cách khôi phục hoặc truy cập được xác minh trước |
| Đồng hồ | Phương thức và thời hạn có dựa vào thời gian chính xác không? | Giám sát thời gian và thử kịch bản lệch đồng hồ |
| Thiết bị xác thực | Có khóa, PIN và thiết bị sử dụng được tại thời điểm cần không? | Chuẩn bị dự phòng và quy trình giữ, lấy thiết bị |
| Nguồn điện hoặc vị trí vật lý | Thiết bị dự phòng có cùng hỏng với hạ tầng chính không? | Phân bố phương tiện theo yêu cầu khả dụng |
| Kênh thông báo | Cảnh báo có phụ thuộc cùng một dịch vụ danh tính không? | Chuẩn bị kênh khác cho kịch bản cần thiết |
| Log và SIEM | Có thể ghi bằng chứng khi hệ thống log trung tâm lỗi không? | Có lưu tạm được bảo vệ và chuyển tiếp sau khôi phục |
| Đội trực | Người có quyền và người giữ phương tiện có sẵn không? | Thiết kế phân công và người dự phòng thực tế |

Không cần loại bỏ mọi phụ thuộc. Cần biết thiết kế bao phủ những sự cố nào và chưa bao phủ những sự cố nào.

### 4.3. Độc lập phải được kiểm chứng ở mức triển khai

Một security key đăng ký với IdP bình thường không tự đăng nhập được vào một hệ thống đích khác khi IdP ngừng hoạt động. Hệ thống dự phòng phải có khả năng xác minh credential được đăng ký cho nó theo kiến trúc phù hợp.

Tương tự:

- Hai tài khoản cùng phụ thuộc một IdP chưa tạo ra tuyến độc lập với IdP.
- Hai ứng dụng MFA trên cùng một điện thoại có thể cùng mất khi điện thoại hỏng.
- Hai khóa được giữ cùng một vị trí có thể cùng không lấy được trong một sự cố vật lý.
- Một bản sao mật khẩu nằm trong chính vault cần cứu không giải quyết được lỗi vault.
- Một tuyến khôi phục vẫn cần email trên hệ thống đang lỗi có thể không dùng được.

Độc lập là quan hệ giữa các thành phần trong một kịch bản cụ thể, không phải một thuộc tính tuyệt đối của tên sản phẩm.

## 5. Các mô hình kiến trúc tham chiếu

### 5.1. Tuyến khẩn cấp qua PAM còn hoạt động

Nếu PAM và IdP vẫn dùng được, nên tận dụng các kiểm soát hiện hữu:

- Danh tính cá nhân đã được chuẩn bị.
- MFA theo mức bảo đảm của quyền khẩn cấp.
- Vai trò hoặc tác vụ khẩn cấp có phạm vi.
- Quyền JIT với thời hạn ngắn.
- Ghi nhận phiên và cảnh báo kích hoạt.
- Tuyến quyết định khẩn cấp theo chính sách.

Đường này phù hợp khi nút thắt là phê duyệt thông thường hoặc một hệ thống nghiệp vụ cần phục hồi. Không cần bỏ MFA chỉ để rút ngắn workflow.

### 5.2. Tuyến xác thực dự phòng độc lập

Nếu cần xử lý sự cố IdP hoặc MFA trung tâm, có thể chuẩn bị tài khoản hoặc bộ xác minh độc lập trên một đường quản trị dự phòng.

Thiết kế cần trả lời:

- Danh tính khẩn cấp được lưu và xác minh ở đâu?
- Hệ thống đó có còn dùng được khi IdP chính lỗi không?
- MFA được thực thi tại bộ phận nào?
- Credential và authenticator đã đăng ký đúng với tuyến dự phòng chưa?
- Ai được sử dụng, ai giữ phương tiện và ai giám sát?
- Quyền trên đích được giới hạn và kết thúc như thế nào?

Có thể dùng authenticator mật mã và xác minh người dùng cục bộ nếu các thành phần thực sự hỗ trợ. Việc dùng khóa phần cứng không loại bỏ nhu cầu có một bộ xác minh hoạt động và cấu hình đúng.

Nếu dùng OTP với bộ xác minh dự phòng, cần quản lý secret xác thực, chống dùng lại theo thiết kế, giới hạn thử sai và xử lý phụ thuộc thời gian hoặc bộ đếm tương ứng. Không lưu mật khẩu và secret tạo OTP trong cùng một script cho người dùng chạy.

### 5.3. Truy cập trực tiếp tới hệ thống đích

Khi PAM không khả dụng, một số kịch bản yêu cầu đường trực tiếp tới console hoặc hệ thống đích. Đường này có thể làm mất khả năng ghi phiên, cấp lease hoặc chấm dứt quyền từ PAM.

Do đó cần kiểm soát tại nơi còn hoạt động:

- Danh tính hoặc tài khoản khẩn cấp đã chuẩn bị.
- MFA trên đích hoặc trên đường quản trị dự phòng, nếu kiến trúc hỗ trợ.
- Giới hạn nguồn kết nối, mạng quản trị và thiết bị vận hành.
- Cơ chế theo dõi hành động tại đích.
- Quy trình hạn chế thời gian và kết thúc quyền.
- Bằng chứng về người thực sự sử dụng nếu phải dùng tài khoản kỹ thuật chung.

Một lớp MFA trên gateway không bảo vệ đường trực tiếp nếu người dùng có thể đi vòng gateway. Phải kiểm tra mọi đường được phép trong kịch bản khẩn cấp.

### 5.4. Ngoại lệ khi MFA không thể thực thi

Nếu hệ thống đích và đường dự phòng không thể đáp ứng MFA, cần ghi nhận đúng sự thật đó.

Các biện pháp bù có thể gồm lấy bí mật dưới kiểm soát hai người, truy cập tại console được bảo vệ, hạn chế mạng, chỉ cho thiết bị quản trị được chỉ định, giám sát độc lập và thu hồi hoặc đổi bí mật ngay sau sử dụng.

Các biện pháp này giảm rủi ro theo cách khác; không nên gọi chúng là MFA nếu không có xác thực nhiều yếu tố thực sự. Ngoại lệ cần có phạm vi, thời hạn, người có thẩm quyền và kế hoạch xử lý lâu dài nếu rủi ro đòi hỏi.

## 6. Chuẩn bị tài khoản và phương tiện trước sự cố

### 6.1. Danh tính và phạm vi quyền

Ưu tiên khả năng gắn hành động với từng cá nhân. Khi phải dùng tài khoản kỹ thuật chung do giới hạn hệ thống, cần liên kết được lần sử dụng với người lấy quyền, người thao tác, thời gian và hồ sơ sự cố.

Không tạo một tài khoản “emergency-admin” dùng chung cho mọi công việc hằng ngày. Việc sử dụng thường xuyên làm mất tín hiệu bất thường và tăng khả năng credential bị sao chép.

Quyền khẩn cấp cần đủ để xử lý kịch bản đã xác định, nhưng không mặc nhiên bao phủ mọi tài nguyên. Có thể tách tuyến khôi phục danh tính, hạ tầng, vault và ứng dụng thay vì dùng một tài khoản toàn quyền trên toàn tổ chức.

Nếu một nền tảng buộc phải duy trì sẵn quyền quản trị cho tài khoản dự phòng, cần ghi rõ quyền đó tồn tại thường trực và quản lý cách kích hoạt, sử dụng, giám sát. Không mô tả như JIT nếu không thực sự có cấp và thu hồi quyền theo thời điểm.

### 6.2. Bảo quản yếu tố

Tùy phương thức, cần quản lý:

- Ai sở hữu hoặc giữ authenticator.
- Nơi giữ khóa dự phòng và điều kiện lấy.
- Cách bảo vệ PIN hoặc bí mật liên quan.
- Cách kiểm tra tình trạng phương tiện.
- Quy trình khi mất, hỏng hoặc nghi bị sao chép.
- Cách thay đổi người được phân công.

Không nên đặt khóa và bản ghi PIN ngay cùng nhau để bất kỳ ai lấy được một túi vật lý là có đủ mọi yếu tố. Dù cơ chế xác thực có thể dùng nhiều yếu tố về mặt kỹ thuật, việc bảo quản yếu làm tăng khả năng chúng bị chiếm cùng lúc.

Nếu khóa dành cho từng cá nhân, không chia sẻ tùy tiện. Nếu một authenticator phục vụ tài khoản khẩn cấp dùng chung theo chính sách, cần ghi rõ giới hạn về quy trách nhiệm và áp dụng kiểm soát lấy, trả phù hợp.

### 6.3. Thử khả năng dùng được, không chỉ kiểm kê số lượng

Có hai khóa trong danh sách không chứng minh có thể đăng nhập. Cần xác minh:

- Khóa đúng với tài khoản và bộ xác minh dự phòng.
- Người trực biết cách sử dụng và có phương tiện kết nối.
- PIN hoặc cơ chế xác minh còn dùng được.
- Tài khoản chưa bị vô hiệu hóa hoặc thay đổi ngoài dự kiến.
- Đường mạng, console và máy trạm quản trị hoạt động trong kịch bản cần thiết.
- Việc sử dụng phát ra sự kiện mà đội giám sát nhận được.

Nếu cơ chế hết hạn hoặc chính sách khóa thay đổi, phương tiện dự phòng phải được cập nhật theo quy trình. Một bài thử thành công từ nhiều năm trước không phản ánh trạng thái hiện tại.

## 7. Quy trình kích hoạt có kiểm soát

### 7.1. Ghi nhận lý do và tuyến được sử dụng

Trước hoặc tại lúc kích hoạt theo chính sách khẩn cấp, cần ghi nhận:

- Mã sự cố hoặc định danh hồ sơ tạm thời.
- Sự cố và thành phần không khả dụng.
- Lý do đường truy cập thông thường không đáp ứng.
- Người chịu trách nhiệm điều phối và người thao tác.
- Hệ thống, quyền và thời hạn cần dùng.
- Tuyến break-glass được chọn.
- Người có thẩm quyền chấp thuận nếu tuyến yêu cầu.

Nếu công cụ ticket không hoạt động, có thể dùng cơ chế ghi tạm đã định nghĩa và đối chiếu sau. Không vì công cụ bị lỗi mà tạo lịch sử giả hoặc ghi lùi thời gian phê duyệt.

Thẩm quyền hành động có thể đến từ một chính sách khẩn cấp đã được ban hành trước. Hậu kiểm không biến một lần sử dụng ngoài thẩm quyền thành một quyết định đã có từ trước.

### 7.2. Xác thực trên tuyến phù hợp

Người thao tác thực hiện MFA bằng phương thức được chuẩn bị cho tuyến đó. Nếu yếu tố không dùng được, không tự bỏ qua bước xác thực; phải chuyển sang tuyến dự phòng hoặc ngoại lệ có thẩm quyền tương ứng.

Tránh đăng ký một yếu tố mới cho người chưa được xác minh chỉ vì họ có thể cung cấp một số thông tin về sự cố. Khẩn cấp không làm giảm nhu cầu biết ai đang nhận quyền.

### 7.3. Cấp quyền và thao tác

Sau khi xác thực:

1. Kiểm tra điều kiện kích hoạt và phạm vi.
2. Cấp quyền hoặc mở khả năng sử dụng theo cơ chế của tuyến đó.
3. Ghi thời điểm bắt đầu và hạn cuối.
4. Thông báo sử dụng qua kênh phù hợp.
5. Thực hiện công việc đã xác định.
6. Theo dõi hoạt động và giới hạn thay đổi ngoài phạm vi.

Nếu trong lúc khôi phục phát sinh nhu cầu quyền rộng hơn, phải đánh giá và ghi quyết định tương ứng. Một lần MFA thành công không phải giấy phép mở rộng quyền tùy ý.

~~~mermaid
flowchart TD
    A[Xác định sự cố và đường thường không dùng được] --> B[Chọn tuyến khẩn cấp đã được chuẩn bị]
    B --> C[Kiểm tra người thao tác, thẩm quyền và phạm vi]
    C --> D{Đủ điều kiện kích hoạt?}
    D -- Không --> E[Chuyển tuyến có thẩm quyền hoặc từ chối]
    D -- Có --> F[Thực hiện xác thực của tuyến đã chọn]
    F --> G{Đạt mức xác thực yêu cầu?}
    G -- Không --> E
    G -- Có --> H[Mở quyền có giới hạn và phát cảnh báo]
    H --> I[Thao tác, giám sát và ghi bằng chứng]
    I --> J[Kết thúc, thu hồi và xác minh]
    J --> K[Khôi phục phương tiện dự phòng và hậu kiểm]
~~~

## 8. Giới hạn thời gian và kết thúc quyền

### 8.1. Một trường hết hạn không tự thực thi việc hết hạn

Trong đường PAM bình thường, hệ thống có thể cấp entitlement hoặc lease ngắn hạn. Trên đường dự phòng, tài khoản cục bộ có thể không có cùng khả năng đó.

Thiết kế phải nêu rõ:

- Thành phần nào thực thi hạn cuối.
- Có thể ngăn phiên mới và đóng phiên hiện hữu hay không.
- Token hoặc quyền đã cấp trên đích được xử lý như thế nào.
- Khi control plane lỗi, cơ chế cục bộ nào còn hoạt động.
- Ai kiểm tra kết quả nếu việc thu hồi tự động thất bại.

Không ghi “quyền 30 phút” trong hồ sơ rồi để tài khoản quản trị vẫn dùng được vô thời hạn. Nếu phụ thuộc thao tác thủ công, cần thừa nhận giới hạn này và có cơ chế theo dõi đến khi hoàn tất.

### 8.2. Đăng xuất, đổi mật khẩu và thu hồi quyền là các việc khác nhau

Đăng xuất khỏi portal không nhất thiết đóng phiên trên đích. Đổi mật khẩu không nhất thiết vô hiệu hóa phiên hoặc token đã được cấp. Xóa membership có thể không làm mọi token cũ mất hiệu lực ngay.

Khi kết thúc, cần xử lý các đối tượng liên quan theo kiến trúc:

| Đối tượng | Việc cần xem xét |
|---|---|
| Phiên khẩn cấp | Đóng hoặc hạn chế theo chính sách; xác minh không tiếp tục thao tác |
| Entitlement tạm thời | Thu hồi và kiểm tra trên đích |
| Mật khẩu hoặc bí mật đã tiết lộ | Đổi hoặc thu hồi khi cần, cập nhật bản dự phòng qua quy trình |
| Token hoặc certificate ngắn hạn | Hết hạn, thu hồi hoặc chặn theo khả năng thực thi |
| Authenticator bị mất hoặc nghi lộ | Vô hiệu hóa đăng ký liên quan và thay thế |
| Tài khoản khẩn cấp | Trả về trạng thái sẵn sàng nhưng bị kiểm soát theo thiết kế |
| Tác vụ và thay đổi tồn tại trên đích | Kiểm tra quyền, tài khoản, lịch chạy hoặc cấu hình đã tạo |

Không cần thay authenticator sau mọi lần sử dụng hợp lệ nếu thiết kế không yêu cầu và không có dấu hiệu lộ. Cần phân biệt giữa credential đã tiết lộ, khóa được bảo vệ và một yếu tố bị nghi chiếm đoạt.

### 8.3. Tác vụ nền cần chính sách riêng

Đóng phiên không chứng minh mọi tác vụ nền đã dừng. Trong khôi phục, có thể có công việc dài hạn cần tiếp tục sau khi người vận hành hết quyền.

Nếu được phép, tác vụ đó cần có danh tính thực thi, phạm vi, trách nhiệm giám sát và điều kiện kết thúc riêng. Không giữ phiên quản trị tương tác mở vô hạn chỉ vì một công việc đang chạy.

### 8.4. Mất kết nối và thời gian không đáng tin cậy

Tuyến khẩn cấp có thể hoạt động khi kết nối tới nguồn trạng thái trung tâm bị mất. Khi đó cần xác định hạn cục bộ, tuổi thông tin chấp nhận được và khả năng thu hồi thực tế.

Không thể vừa cho phép một tuyến hoạt động ngoại tuyến lâu dài vừa khẳng định mọi lệnh thu hồi trung tâm có hiệu lực tức thì. Cam kết phải phù hợp với kiến trúc và được kiểm thử.

Nếu đồng hồ không đáng tin cậy, không âm thầm mở rộng cửa sổ. Cần có quy tắc xử lý hoặc tuyến thay thế đã được xác định, đồng thời ghi nhận giới hạn của bằng chứng thời gian.

## 9. Chính sách minh họa

Mô hình dưới đây dùng để trao đổi thiết kế, không phải cấu hình của một sản phẩm cụ thể. Thời lượng là ví dụ, không phải giá trị chuẩn:

~~~yaml
emergency_access:
  profile: "identity-recovery"
  eligible_operators: "designated-identity-responders"
  target_scope: "identity-recovery-components"

  activation:
    incident_reference_required: true
    authority_basis: "preauthorized-emergency-policy"
    independent_custodian_if_required: true
    notify_on_every_use: true

  authentication:
    route: "independently-verified-emergency-route"
    required_assurance: "approved-multi-factor-method"
    user_verification_if_required: true
    ordinary_password_fallback: false

  access:
    maximum_minutes: 30
    new_scope_requires_new_decision: true
    renewal_is_automatic: false

  evidence:
    record_operator_and_account: true
    record_authentication_result_without_secrets: true
    protected_local_capture_when_central_logging_unavailable: true

  closure:
    verify_session_and_entitlement_revocation: true
    rotate_disclosed_secrets_when_required: true
    validate_emergency_readiness: true
    post_incident_review_required: true
~~~

Một hồ sơ không chỉ cần có các trường trên mà còn phải được ánh xạ sang điểm thực thi thực tế. Ví dụ, maximum_minutes phải được thực hiện bởi cơ chế có hiệu lực trên đường khẩn cấp; một con số trong tài liệu không tạo ra hạn sử dụng.

Logic khái niệm:

~~~text
activate_emergency_access(operator, incident, profile):
    require(profile.is_current)
    require(operator.is_eligible_for(profile))
    require(incident.matches_allowed_emergency_conditions)
    require(required_authority_is_present_or_preestablished)

    authentication = authenticate_on_selected_route(operator)
    require(authentication.satisfies(profile.required_assurance))

    scope = resolve_and_validate_emergency_scope(incident, profile)
    expiry = determine_enforceable_expiry(profile)

    record_activation_and_notify(
        operator,
        incident,
        profile.version,
        scope,
        expiry
    )

    grant_or_enable_access_with_defined_controls(scope, expiry)
    track_until_revocation_and_verification_are_complete()
~~~

Trong triển khai, cần xử lý lỗi ở từng bước. Nếu quyền đã được cấp nhưng thông báo bị lỗi, không được báo toàn bộ quy trình chưa từng xảy ra; cần ghi đúng trạng thái, phát cảnh báo bằng đường còn hoạt động và xử lý theo chính sách. Nếu không thể bảo đảm một điều kiện bắt buộc, phải chuyển tuyến có thẩm quyền thay vì tự bỏ điều kiện.

## 10. Bằng chứng và cảnh báo khi hạ tầng giám sát gặp lỗi

### 10.1. Những gì cần chứng minh

Một lần break-glass nên liên kết được:

- Lý do khẩn cấp và đường truy cập thường không dùng được.
- Chính sách hoặc quyết định làm cơ sở cho quyền.
- Danh tính người thao tác và tài khoản kỹ thuật đã dùng.
- Người giữ hoặc bàn giao phương tiện nếu có.
- Tuyến xác thực, kết quả và thời điểm.
- Tài nguyên, quyền và thời hạn.
- Hoạt động quan trọng và thay đổi đã thực hiện.
- Thời điểm kết thúc, kết quả thu hồi và việc khôi phục phương tiện dự phòng.

Nếu chỉ có log “emergency-admin login”, khả năng quy trách nhiệm cho một cá nhân còn hạn chế. Hồ sơ lấy quyền và bằng chứng phiên giúp bổ sung, nhưng không nên mô tả như danh tính cá nhân được xác thực trực tiếp nếu thực tế không phải vậy.

### 10.2. Không ghi yếu tố xác thực vào log

Không lưu:

- Mật khẩu khẩn cấp.
- PIN.
- OTP hoặc secret tạo OTP.
- Recovery code có thể sử dụng.
- Private key.
- Token hoặc cookie có thể dùng lại.

Có thể lưu định danh phương tiện, loại phương thức và kết quả xác thực ở mức cần thiết. Dữ liệu phải đủ để kiểm chứng mà không tạo ra một kho bí mật thứ hai.

### 10.3. Ghi tạm và chuyển tiếp sau sự cố

Nếu SIEM hoặc log collector không khả dụng, cần cơ chế thu thập cục bộ được bảo vệ, hạn chế người có thể sửa hoặc xóa và chuyển tiếp khi phục hồi.

Một bản băm tự tạo không tự chứng minh log chưa từng bị thay đổi nếu cùng người có thể sửa log và thay luôn bản băm. Tính toàn vẹn cần dựa trên ranh giới tin cậy và cơ chế bảo vệ phù hợp, chẳng hạn nơi lưu độc lập hoặc cơ chế phát hiện sửa đổi được quản trị.

Nếu cảnh báo trung tâm không gửi được, tuyến dự phòng có thể dùng kênh liên lạc khác đã chuẩn bị. Cần ghi nhận việc thiếu xác nhận hoặc thiếu log là một giới hạn phải xử lý, không mặc nhiên xem “không thấy cảnh báo” là “không có sử dụng”.

## 11. Tình huống: IdP lỗi trong lúc khôi phục hạ tầng danh tính

Một tổ chức dùng IdP để đăng nhập PAM. Sự cố cấu hình khiến IdP không thể xác thực người dùng, trong khi một số thành phần cần sửa nằm sau quyền quản trị do PAM cấp.

### 11.1. Thiết kế không dùng được

Tài khoản break-glass đã được tạo nhưng:

- Vẫn đăng nhập qua IdP đang lỗi.
- MFA chỉ gửi push qua cùng dịch vụ bị ảnh hưởng.
- Mật khẩu dự phòng chỉ nằm trong vault không thể truy cập.
- Không ai thử tài khoản sau lần thay đổi cấu hình gần nhất.

Dù tài liệu ghi “có tài khoản khẩn cấp và MFA”, đường này không giải quyết được kịch bản cần khôi phục.

### 11.2. Thiết kế được chuẩn bị theo kịch bản

Tổ chức chuẩn bị một tuyến quản trị dự phòng có bộ xác minh phù hợp, không cần IdP chính cho bước đăng nhập đã xác định. Người trực đủ điều kiện có authenticator đã đăng ký cho tuyến đó; phương tiện dự phòng được quản lý và đã thử.

Khi sự cố xảy ra:

1. Điều phối viên xác định sự cố thuộc phạm vi chính sách khẩn cấp.
2. Người thao tác và người tham gia kiểm soát theo yêu cầu được ghi nhận.
3. Người thao tác dùng tuyến MFA dự phòng trên máy trạm quản trị được chỉ định.
4. Phạm vi chỉ bao gồm các thành phần cần khôi phục danh tính.
5. Hệ thống hoặc quy trình thực thi giới hạn thời gian theo khả năng đã kiểm chứng.
6. Hoạt động được ghi tại điểm còn hoạt động và thông báo qua kênh còn sử dụng được.
7. Sau khi IdP phục hồi, đội vận hành đóng phiên, thu hồi quyền liên quan và kiểm tra truy cập thực tế.
8. Những bí mật đã tiết lộ được xử lý, log được đối chiếu và trạng thái sẵn sàng dự phòng được xác minh lại.

Nếu đường dự phòng không ghi phiên đầy đủ như PAM thường ngày, hồ sơ phải nêu rõ khoảng trống đó và bằng chứng thay thế đã có. Không suy diễn rằng mọi kiểm soát của PAM chính vẫn hiện diện.

### 11.3. Hậu kiểm cần trả lời điều gì?

- Có đúng là đường thường không dùng được?
- Người kích hoạt có nằm trong nhóm đủ điều kiện không?
- MFA đã được thực thi ở đâu và bằng phương thức nào?
- Có truy cập ngoài phạm vi hoặc vượt thời gian không?
- Có quyền hoặc credential còn tồn tại ngoài dự kiến không?
- Phương tiện dự phòng còn dùng được cho sự cố tiếp theo không?
- Có cần cải thiện phụ thuộc hoặc tốc độ phát hiện không?

Hậu kiểm phải ghi đúng thời điểm quyết định và sử dụng. Không tạo một bản phê duyệt lùi ngày để làm hồ sơ trông như quy trình thường.

## 12. Diễn tập và tiêu chí nghiệm thu

Một tuyến khẩn cấp ít dùng có thể bị hỏng âm thầm do thay đổi mạng, chứng thư, tài khoản, thiết bị hoặc người trực. Vì vậy cần thử định kỳ và sau các thay đổi liên quan.

Diễn tập nên có phạm vi, người chịu trách nhiệm và kế hoạch khôi phục rõ ràng. Có thể dùng môi trường thử nghiệm hoặc bài tập được phép, tránh gây gián đoạn production chỉ để kiểm tra một giả định.

| Bài thử | Điều cần chứng minh |
|---|---|
| IdP chính không khả dụng trong kịch bản thử | Tuyến dự phòng được thiết kế cho sự cố này vẫn xác thực được |
| PAM portal không khả dụng | Đường dự phòng có kiểm soát thực sự tới được tài nguyên cần khôi phục |
| Người không thuộc nhóm đủ điều kiện có được mật khẩu | Không thể vượt cơ chế còn lại để nhận quyền trái phép |
| Thiếu PIN hoặc user verification bắt buộc | Không bị coi là đủ điều kiện chỉ vì có khóa |
| Khóa chính mất hoặc hỏng | Có đường dự phòng phù hợp, không cần bỏ kiểm soát tùy tiện |
| Phương tiện hoặc ủy quyền đã bị thu hồi | Không sử dụng được theo trạng thái và khả năng thực thi của tuyến |
| Cảnh báo trung tâm bị lỗi | Có phát hiện giới hạn và dùng kênh dự phòng theo chính sách |
| Hết thời hạn khi phiên còn hoạt động | Quyền và phiên được xử lý đúng cơ chế đã công bố |
| Thu hồi quyền thất bại | Có trạng thái chưa hoàn tất, cảnh báo và người xử lý |
| Log trung tâm không sẵn sàng | Có bằng chứng cục bộ được bảo vệ và đối chiếu sau phục hồi |
| Thay đổi người trực hoặc người giữ khóa | Người cũ mất thẩm quyền, người mới có phương tiện hợp lệ |
| Phục hồi hệ thống từ bản sao lưu | Không âm thầm khôi phục lại credential hoặc quyền đã bị thu hồi |
| Kết thúc diễn tập | Phương tiện được trả, quyền được thu hồi và tuyến dự phòng sẵn sàng trở lại |

Một lần đăng nhập thành công chưa đủ để nghiệm thu. Cần kiểm tra cả khả năng thao tác đúng phạm vi, quan sát được việc sử dụng và kết thúc quyền.

## 13. Sai lầm cần tránh

**Miễn MFA cho mọi tài khoản khẩn cấp:** tạo ra một nhóm quyền cao nhưng yếu hơn mà không xem xét từng kịch bản. Cần tuyến xác thực phù hợp và ngoại lệ có thẩm quyền khi thực sự cần.

**Dùng hai người như tên gọi khác của MFA:** nhầm kiểm soát quy trình với cơ chế xác thực. Cần ghi riêng bằng chứng của từng loại kiểm soát.

**Để mọi phương tiện cùng phụ thuộc một nơi:** dễ mất đồng thời khi chính địa điểm, thiết bị hoặc dịch vụ đó gặp lỗi. Phân bố phải theo kịch bản sự cố.

**Tự động fallback sang mật khẩu khi MFA lỗi:** biến lỗi dịch vụ thành cách bỏ qua bảo vệ. Cần tuyến khẩn cấp riêng với danh tính, phạm vi và bằng chứng.

**Cho tài khoản khẩn cấp dùng hằng ngày:** làm tăng phơi nhiễm credential và che lấp tín hiệu bất thường. Công việc thông thường nên đi qua luồng PAM tương ứng.

**Quên thu hồi sau khi đã sửa xong:** để lại phiên, membership, token hoặc credential có thể sử dụng. Kết thúc phải được xác minh ở các điểm thực thi.

**Chỉ đổi mật khẩu rồi coi như hoàn tất:** không xử lý mọi phiên hoặc quyền đã phát sinh. Cần xem toàn bộ vòng đời truy cập.

**Ghi phê duyệt lùi thời gian:** làm sai bằng chứng. Cần phân biệt thẩm quyền khẩn cấp có trước với hậu kiểm sau sử dụng.

**Không kiểm tra lại sau thay đổi hạ tầng:** để tuyến dự phòng hỏng mà không ai biết. Diễn tập cần gắn với thay đổi quan trọng, không chỉ lịch định kỳ.

MFA cho break-glass cần bảo vệ danh tính mà vẫn hoạt động trong các sự cố đã được thiết kế bao phủ. Một tuyến đáng tin cậy phải chứng minh được người dùng có đủ điều kiện, quyền được giới hạn, việc sử dụng quan sát được và các quyền phát sinh đã thực sự kết thúc.

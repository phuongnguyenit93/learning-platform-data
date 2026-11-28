# Pseudonymous identifier — Định danh giả trong IAM

## 1. Nhận biết cùng một chủ thể mà không phát hành danh tính trực tiếp

**Pseudonymous identifier** là một mã dùng để tham chiếu tới chủ thể thay cho những thông tin nhận diện trực tiếp như email, số điện thoại hoặc mã nhân viên có ý nghĩa bên ngoài hệ thống. Mã này cho phép một ứng dụng nhận biết các lần tương tác thuộc cùng tài khoản trong một phạm vi đã xác định mà không nhất thiết biết danh tính ngoài đời của người đó.

Ví dụ, một nền tảng học tập có thể nhận chủ thể `learner-pseudo-82` thay vì địa chỉ email công ty. Ứng dụng dùng mã đó để gắn tiến độ học và kết quả với tài khoản cục bộ. Nhà cung cấp danh tính vẫn có thể biết tài khoản nguồn tương ứng, nhưng nền tảng học tập không cần nhận mọi thông tin trong hồ sơ nhân sự.

Các mã trong bài chỉ là nhãn minh họa dễ đọc, không thể hiện độ dài hoặc chất lượng ngẫu nhiên cần có khi triển khai thực tế.

Một định danh giả tốt có thể giúp giảm thông tin được chia sẻ và giảm khả năng nối hoạt động giữa các hệ thống. Hiệu quả phụ thuộc vào cách cấp mã, phạm vi ổn định, quyền truy cập mapping và các thuộc tính khác được phát hành cùng mã đó.

## 2. Định danh giả không đồng nghĩa với ẩn danh hoặc quyền truy cập

### 2.1. Phân biệt các khái niệm

| Khái niệm | Ví dụ | Điều cần hiểu |
|---|---|---|
| Định danh trực tiếp | Email công việc hoặc số định danh cá nhân | Có thể nhận diện hoặc liên hệ với người đó từ chính giá trị |
| Định danh nội bộ | `user-1042` trong một directory | Có thể không đọc ra tên nhưng vẫn liên kết với hồ sơ nội bộ |
| Định danh giả | Một mã được cấp để tham chiếu chủ thể trong phạm vi cụ thể | Có thể vẫn được ánh xạ hoặc liên kết với một người |
| Dữ liệu ẩn danh | Dữ liệu không còn cho phép nhận diện cá nhân trong bối cảnh được đánh giá | Không đạt được chỉ bằng việc đổi tên hoặc thay email bằng mã |
| Bí mật xác thực | Mật khẩu, khóa riêng hoặc bearer token hợp lệ | Dùng để chứng minh hoặc thực thi quyền theo cơ chế xác thực |

Một UUID ngẫu nhiên có thể được dùng làm định danh giả, nhưng việc chọn UUID không tự tạo ra khả năng ẩn danh. Nếu cùng mã xuất hiện trong mọi hệ thống, các bên có thể dùng nó để nối hoạt động. Nếu ai cũng truy vấn được bảng mã–email, lợi ích che danh tính trực tiếp cũng giảm mạnh.

### 2.2. Biết mã không phải là chứng minh sở hữu tài khoản

Pseudonymous identifier là tham chiếu, không phải credential. Người gọi biết `learner-pseudo-82` không tự có quyền đọc tiến độ học của tài khoản đó. API vẫn phải xác thực người gọi và kiểm tra quyền với đúng đối tượng, tenant cùng hành động.

Một đường dẫn khó đoán không thay thế kiểm soát truy cập. Ngay cả mã được sinh ngẫu nhiên cũng có thể xuất hiện trong lịch sử trình duyệt, log hoặc liên kết được chia sẻ. Thiết kế phải tiếp tục an toàn khi mã đối tượng không còn bí mật.

## 3. Chọn phạm vi ổn định của định danh

### 3.1. Một mã toàn cục và nhiều mã theo phạm vi

Giả sử một người sử dụng ba ứng dụng: cổng học tập, hệ thống hỗ trợ và ứng dụng phúc lợi. Hai cách phát hành có thể khác nhau như sau:

| Bên nhận | Một mã dùng chung | Mã tách theo phạm vi bên nhận |
|---|---|---|
| Cổng học tập | `subject-global-27` | `learning-subject-82` |
| Hệ thống hỗ trợ | `subject-global-27` | `support-subject-46` |
| Ứng dụng phúc lợi | `subject-global-27` | `benefits-subject-91` |

Mã dùng chung giúp liên kết tài khoản thuận tiện nhưng cũng tạo khóa nối hoạt động trực tiếp giữa ba ứng dụng. Các mã theo phạm vi hạn chế cách nối bằng chính định danh đó. Từng ứng dụng vẫn có thể nhận biết người dùng quay lại trong phạm vi của mình.

Việc tách phạm vi phải phục vụ một mục đích rõ ràng. Một nhóm ứng dụng có thể có nhu cầu chia sẻ danh tính để vận hành một chức năng thống nhất. Khi đó cần xác định nhóm nào được liên kết, ai cho phép và những bên nào nằm ngoài phạm vi. Không mở rộng một nhóm liên kết chỉ vì mọi ứng dụng cùng dùng một IdP.

### 3.2. Ổn định theo tài khoản hay theo phiên?

Một ứng dụng giữ lịch sử học cần nhận biết cùng tài khoản qua nhiều lần đăng nhập. Nếu đổi định danh ở mỗi phiên mà không có cơ chế liên kết phù hợp, ứng dụng có thể tạo tài khoản mới, mất lịch sử hoặc gán sai dữ liệu.

Ngược lại, một giao dịch chỉ cần kiểm tra một điều kiện một lần có thể không cần định danh ổn định dài hạn. Cần phân biệt định danh của tài khoản, mã phiên, correlation ID và mã giao dịch. Không dùng một mã lâu dài ở mọi nơi chỉ vì nó tiện cho việc tra cứu.

Phạm vi ổn định nên được ghi vào contract: mã duy nhất trong issuer nào, tenant nào, ứng dụng hoặc nhóm bên nhận nào, có tồn tại qua đổi email hay không và điều gì xảy ra khi tài khoản bị xóa. Những điều này là một phần của thiết kế dữ liệu, không chỉ là lựa chọn định dạng chuỗi.

## 4. Pairwise subject identifier trong OIDC

### 4.1. `sub` cần được hiểu trong phạm vi issuer

Trong OIDC, `sub` là định danh chủ thể do OpenID Provider phát hành cho client. Ứng dụng cần xử lý định danh này trong namespace của issuer đã được xác minh. Hai issuer khác nhau có thể phát hành cùng chuỗi `sub` mà không nói về cùng người.

Một mô hình liên kết tài khoản cục bộ có thể lưu:

```json
{
  "issuer": "https://idp.example.test",
  "subject": "subject-for-learning-82",
  "local_account_ref": "local-learner-17"
}
```

Đây chỉ là dữ liệu liên kết minh họa, không phải một token hoàn chỉnh. Việc có hai chuỗi `issuer` và `subject` do client gửi lên không đủ để tin cậy. Chúng phải được rút ra từ kết quả xác thực đã được kiểm tra đúng protocol, bao gồm các điều kiện như issuer, audience, tính toàn vẹn và thời hạn tương ứng.

Không dùng email làm phương án tự động thay thế khi `sub` thay đổi. Email có thể đổi, được cấp lại hoặc tồn tại ở nhiều nhà cung cấp. Việc nối hai tài khoản cần quy trình liên kết và bằng chứng phù hợp, tránh biến một thay đổi định danh thành chiếm tài khoản.

### 4.2. Pairwise theo Sector Identifier

OIDC phân biệt kiểu subject `public` và `pairwise`. Với pairwise, việc tính `sub` gắn với **Sector Identifier**. Vì vậy, không nên mặc định mỗi `client_id` luôn có một giá trị `sub` khác nhau: nhiều client cùng sector có thể nhận cùng giá trị cho một chủ thể.

Sector là khái niệm của cấu hình OIDC, không nên tự đồng nhất với tenant, hostname API hoặc môi trường triển khai. Nếu dùng một scheme phân vùng riêng ngoài OIDC, cần định nghĩa rõ scheme đó thay vì gọi mọi phạm vi tùy ý là OIDC sector.

OpenID Connect Core mô tả các yêu cầu đối với thuật toán pairwise và cách xác định sector, bao gồm việc sử dụng `sector_identifier_uri` trong những cấu hình tương ứng. Khi cấu hình pairwise thực tế, cần làm theo cơ chế của provider và đặc tả, không chỉ nối thêm `client_id` vào một giá trị rồi coi đã tương thích. [OpenID Connect Core 1.0 — Pairwise Identifier Algorithm](https://openid.net/specs/openid-connect-core-1_0.html#PairwiseAlg).

## 5. Hai hướng tạo định danh giả thường gặp

### 5.1. Sinh mã ngẫu nhiên và lưu mapping

Hệ thống có thể sinh một mã từ nguồn ngẫu nhiên phù hợp cho bảo mật và lưu mapping giữa tài khoản nội bộ, phạm vi và mã đã cấp. Khi cùng tài khoản quay lại trong cùng phạm vi, hệ thống trả mã đã lưu thay vì sinh mã mới.

```text
Tài khoản nội bộ + phạm vi đã xác định
    → tìm mapping hiện hành
    → đã có: dùng lại mã
    → chưa có: sinh mã, lưu mapping với ràng buộc duy nhất
    → phát hành mã cho đúng bên nhận
```

Cần xử lý đồng thời để hai request đầu tiên không tạo ra hai mapping khác nhau cho cùng tài khoản và phạm vi. Kho lưu cần ràng buộc duy nhất theo contract và cơ chế tạo hoặc đọc lại mapping an toàn khi có cạnh tranh.

Mã phải đủ khó đoán, đủ không gian để kiểm soát rủi ro va chạm và không mang thông tin cá nhân trong cấu trúc. Ràng buộc duy nhất ở kho lưu cùng xử lý va chạm vẫn cần thiết; không nên dựa hoàn toàn vào giả định rằng va chạm chắc chắn không bao giờ xảy ra.

Ưu điểm của cách này là có thể quản lý mapping độc lập với việc đổi thuộc tính hồ sơ. Đổi email không nhất thiết đổi mã. Đổi lại, mapping trở thành dữ liệu quan trọng cần bảo vệ, sao lưu và khôi phục đúng; mất mapping có thể làm người dùng không còn liên kết được với tài khoản ứng dụng cũ.

### 5.2. Dẫn xuất có khóa theo phạm vi

Một hướng khác là dẫn xuất bằng cơ chế có khóa, chẳng hạn HMAC trên đầu vào gồm định danh nội bộ ổn định và phạm vi. Mô hình khái niệm có thể như sau:

```text
context = EncodeFields(
    purpose = "iam-subject",
    environment,
    tenant_namespace,
    recipient_scope,
    internal_subject_id
)

pseudonym = Base64Url(HMAC-SHA-256(K_version, context))
```

Đây là mã giả để giải thích thành phần của thiết kế, không phải hướng dẫn tự triển khai thay một cơ chế OIDC đã có. `EncodeFields` cần có định dạng rõ ràng, không nhập nhằng giữa các trường; nối chuỗi tùy ý có thể làm hai bộ giá trị khác nhau tạo cùng đầu vào. Các phạm vi trong ví dụ phải do thành phần có thẩm quyền xác định, không để bên gọi tùy ý chọn tenant hoặc phạm vi của bên khác.

Khóa `K_version` phải được quản lý như bí mật. Không đặt khóa trong mã nguồn, cấu hình public hoặc log. Khóa dùng cho mục đích này cần được phân tách phù hợp với các mục đích khác; gắn một nhãn mục đích vào đầu vào không thay thế việc quản lý khóa.

HMAC mang tính xác định: cùng khóa và cùng đầu vào tạo cùng kết quả. Do đó, dùng cùng phạm vi cho mọi bên nhận vẫn tạo định danh có thể nối hoạt động. Nếu khóa bị lộ hoặc có một API tùy ý cho phép tra cứu giả danh của bất kỳ người nào, khả năng bảo vệ trước việc đối chiếu cũng suy giảm.

### 5.3. Vì sao hash email đơn thuần chưa đủ?

Một thiết kế như `SHA-256(email)` có hai vấn đề rõ ràng. Thứ nhất, email thường có thể đoán hoặc lấy từ danh sách khác rồi hash để so khớp. Thứ hai, cùng email tạo cùng kết quả ở mọi nơi dùng cùng cách tính, nên có thể nối dữ liệu giữa các ứng dụng.

Thêm một salt công khai có thể thay đổi điều kiện tính toán nhưng không tự ngăn người có salt thử các email ứng viên. Cần phân biệt salt với khóa bí mật và đánh giá đúng khả năng đối chiếu. Đổi email còn làm kết quả đổi, có thể gây đứt liên kết tài khoản nếu hash đó được dùng làm khóa lâu dài.

Không nên tự sáng tác thuật toán mật mã hoặc dùng một chuỗi bí mật gắn vào hash như một thay thế tùy ý cho cơ chế đã được phân tích. Với hệ thống thực tế, ưu tiên khả năng sẵn có của nền tảng và thư viện chuẩn, cùng đánh giá phạm vi, vòng đời khóa và mapping.

## 6. Bảo vệ mapping và giới hạn khả năng nối danh tính

### 6.1. Mapping là dữ liệu có giá trị nhận diện

Giả sử một dịch vụ giữ bảng sau:

| Phạm vi | Mã giả phát hành | Tài khoản nguồn |
|---|---|---|
| learning | `learning-subject-82` | `internal-account-27` |
| support | `support-subject-46` | `internal-account-27` |
| benefits | `benefits-subject-91` | `internal-account-27` |

Bên có quyền đọc đầy đủ bảng này có thể nối cả ba mã về cùng tài khoản. Vì vậy, bảng mapping không phải dữ liệu phụ được phép xuất tự do. Cần giới hạn thao tác đọc, tra cứu ngược, export và sử dụng trong hỗ trợ kỹ thuật.

Có thể tách dữ liệu phục vụ nghiệp vụ của từng ứng dụng khỏi thông tin ánh xạ tập trung. Việc ứng dụng đọc mã của chính nó không kéo theo quyền tra cứu mã tại mọi ứng dụng khác. Các thao tác hỗ trợ cần xác định lại chủ thể nên có mục đích, quyền và dấu vết kiểm toán phù hợp.

Trong kiến trúc federation có proxy, không nên giả định IdP nguồn luôn nhìn thấy toàn bộ bên nhận cuối. Cần xác định thành phần nào phát mã theo từng chặng và thành phần nào giữ khả năng nối các mã. Ranh giới riêng tư phụ thuộc cả kiến trúc ánh xạ, không chỉ định dạng `sub` cuối cùng.

### 6.2. Định danh tách riêng nhưng thuộc tính vẫn có thể nối lại

Hai ứng dụng nhận mã khác nhau nhưng cùng email, số điện thoại và ngày sinh vẫn có thể đối chiếu người dùng. Việc phát pairwise identifier trong trường hợp đó chỉ hạn chế một đường nối, không loại bỏ mọi đường nối.

NIST SP 800-63C-4 lưu ý rằng các thuộc tính nhận diện đi kèm có thể cho phép các relying party đối chiếu chủ thể dù chúng nhận pairwise pseudonymous identifier khác nhau. Bởi vậy, định danh giả cần đi cùng việc giảm thuộc tính không cần thiết và kiểm soát cách sử dụng dữ liệu. [NIST SP 800-63C-4 — Pairwise Pseudonymous Identifiers](https://pages.nist.gov/800-63-4/sp800-63c.html#pairwise-pseudonymous-identifiers-ppi).

Địa chỉ IP, thời điểm giao dịch, mẫu hành vi và dữ liệu do người dùng tự nhập cũng có thể tạo liên kết ngoài identifier. Không nên đưa ra bảo đảm “không thể theo dõi” chỉ vì hai chuỗi mã khác nhau.

## 7. Quản lý vòng đời mà không làm sai liên kết tài khoản

### 7.1. Không cấp lại mã cho người khác

Khi một nhân viên nghỉ việc, mã của tài khoản đó không nên được chuyển cho người mới chỉ vì email công ty hoặc vị trí công việc được tái sử dụng. Nếu ứng dụng giữ lịch sử và quyền theo mã cũ, cấp lại mã có thể làm người mới nhận dữ liệu hoặc quyền của người trước.

Hệ thống cần xác định định danh nguồn ổn định của chính tài khoản và quy tắc đối với tài khoản tạo lại. Một hồ sơ mới có cùng tên hoặc địa chỉ liên hệ không tự đồng nghĩa với cùng chủ thể cũ. Việc khôi phục hoặc nối lại lịch sử phải có quyết định rõ ràng.

### 7.2. Rotation khóa và thay đổi phạm vi

Với định danh dẫn xuất, thay khóa hoặc thay đầu vào phạm vi có thể làm mã phát hành đổi. Với mapping lưu trữ, thay cấu hình sector hoặc di chuyển issuer cũng có thể yêu cầu một kế hoạch liên kết mới ở bên nhận.

Trước khi thay đổi, cần kiểm kê ứng dụng đang dùng mã làm khóa, phiên hoặc token còn tồn tại, dữ liệu lịch sử và các quy trình khôi phục. Nếu cần chuyển đổi, phải bảo vệ mapping chuyển tiếp và giới hạn thời gian cũng như chủ thể được dùng nó. Một bảng nối cũ–mới có thể phục hồi khả năng liên kết mà thay đổi mã đang muốn hạn chế.

Rotation không nên được thực hiện bằng cách để người dùng đăng nhập rồi tự tạo tài khoản mới mỗi lần mã đổi. Cũng không nên tự gộp bằng email để che lỗi chuyển đổi. Cần một cơ chế chuyển tài khoản được xác thực và có thể kiểm tra kết quả.

### 7.3. Xóa, lưu giữ và khôi phục

Mapping, log và dữ liệu nghiệp vụ có thể có mục đích cùng vòng đời khác nhau. Cần xác định khi nào còn cần liên kết, khi nào ngừng phát hành mã và cách xử lý các bản sao ở cache, export hoặc backup.

Xóa một mapping không tự làm mọi dữ liệu ở ứng dụng trở thành ẩn danh. Bên nhận có thể đã lưu email, dữ liệu hồ sơ hoặc liên kết khác. Ngược lại, xóa mapping thiếu kế hoạch có thể khiến chủ tài khoản hợp lệ không truy cập được lịch sử của mình hoặc làm công việc điều tra không thể hoàn tất.

Quy trình khôi phục backup phải giữ đúng namespace và liên kết hiện hành. Không được vô tình khôi phục mapping lỗi thời rồi phát cùng một mã cho hai tài khoản khác nhau. Với phương án dẫn xuất, việc sao lưu và khôi phục vật liệu khóa cần theo cơ chế quản lý khóa của hệ thống, không tạo bản sao bí mật tùy tiện để thuận tiện vận hành.

## 8. Tình huống thiết kế một dịch vụ học tập liên kết SSO

Giả sử doanh nghiệp dùng một IdP cho cổng học tập và ứng dụng phúc lợi. Cổng học tập cần lưu kết quả lâu dài, còn hai ứng dụng không có nhu cầu nối hành vi của người dùng với nhau.

Một thiết kế có thể thực hiện theo trình tự:

1. Xác định nguồn định danh tài khoản ổn định tại IdP và ranh giới tenant.
2. Cấu hình phạm vi phát hành mã cho cổng học tập khác phạm vi ứng dụng phúc lợi theo cơ chế được provider hỗ trợ.
3. Cổng học tập liên kết tài khoản cục bộ bằng issuer và subject đã được xác minh, thay vì dùng email làm khóa duy nhất.
4. Chỉ phát hành thêm tên hiển thị hoặc thuộc tính thực sự cần cho chức năng của cổng.
5. Giữ mapping liên kết ở nơi có quyền truy cập phù hợp và không xuất mã của ứng dụng khác cho cổng học tập.
6. Xác định trước quy trình đổi email, nghỉ việc, quay lại làm việc và thay cấu hình IdP.

Kết quả mong muốn là người dùng vẫn thấy đúng lịch sử khi quay lại, trong khi ứng dụng học tập không nhận định danh toàn cục và hồ sơ không cần thiết. Người vận hành vẫn có thể điều tra theo quy trình được cho phép, nhưng không làm mọi nhân viên hỗ trợ có khả năng nối toàn bộ hoạt động giữa hai ứng dụng.

Một lỗi cần tránh là cấu hình pairwise rồi vẫn phát email, mã nhân viên và toàn bộ nhóm cho cả hai ứng dụng. Những thuộc tính đó có thể tái tạo khóa liên kết chung, làm giảm lợi ích của việc tách identifier.

## 9. Tự kiểm tra cách hiểu

**Thay email bằng UUID có biến mọi dữ liệu thành ẩn danh không?**

Không. UUID vẫn có thể liên kết với hồ sơ, mapping hoặc hành vi. Cần đánh giá cả phạm vi sử dụng và dữ liệu bổ trợ.

**Hai client OIDC có luôn nhận `sub` khác nhau khi dùng pairwise không?**

Không nên mặc định như vậy. Cần xét Sector Identifier và cấu hình thực tế của provider; nhiều client trong cùng sector có thể nhận cùng giá trị.

**Có thể dùng định danh giả khó đoán để bỏ kiểm tra quyền trên API không?**

Không. Identifier chỉ tham chiếu chủ thể hoặc đối tượng. Xác thực và kiểm tra quyền vẫn phải thực hiện khi truy cập tài nguyên.

**Vì sao không nên dẫn xuất mã lâu dài trực tiếp từ email?**

Email có thể đoán, thay đổi hoặc được cấp lại. Hash không có khóa còn có thể bị đối chiếu với danh sách ứng viên và tạo cùng giá trị giữa các hệ thống.

**Thiết kế cần bảo đảm điều gì ngoài việc sinh ra một chuỗi khó đọc?**

Mã phải có phạm vi và vòng đời rõ ràng, giữ đúng liên kết tài khoản, tránh cấp lại sai chủ thể, đồng thời bảo vệ mapping và các thuộc tính đi kèm. Khi đó, pseudonymous identifier hỗ trợ giảm chia sẻ danh tính mà vẫn duy trì xác thực, phân quyền và kiểm toán có căn cứ.

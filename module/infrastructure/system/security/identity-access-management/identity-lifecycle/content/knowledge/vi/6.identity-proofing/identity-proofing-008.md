# Identity evidence: bằng chứng danh tính trong quy trình Identity Proofing

**Identity evidence (bằng chứng danh tính)** là tài liệu, dữ liệu hoặc chứng thực được sử dụng để hỗ trợ một hay nhiều **khẳng định về danh tính** (*identity claims*) của một cá nhân: người đó là ai, có những thuộc tính định danh nào và có thể liên kết đáng tin cậy với một hồ sơ danh tính hay không. Trong **Identity Proofing**, bằng chứng không chỉ được thu thập mà còn phải được **đánh giá nguồn phát hành, tính xác thực, tính hiệu lực và sự liên hệ với đúng người đang đăng ký**.

Bài học thuộc chương **Identity proofing**, trong mô-đun quản lý vòng đời danh tính IAM theo **Joiner–Mover–Leaver**. Ở giai đoạn gia nhập, bằng chứng giúp xây dựng cơ sở tin cậy trước khi tạo tài khoản và cấp quyền. Khi đổi vai trò, thay đổi thông tin cá nhân hoặc quay lại làm việc, bằng chứng có thể cần được cập nhật hay xác minh lại. Khi rời tổ chức, thông tin đã xác minh giúp truy vết và thu hồi chính xác các tài khoản, quyền và thông tin xác thực liên quan.

**Thông điệp cốt lõi:** Có một tấm ảnh giấy tờ, một email doanh nghiệp hay một bản ghi trong hệ thống **chưa đủ** để kết luận người đăng ký là chủ thể hợp lệ. Cần xem xét **bằng chứng chứng minh điều gì**, **nguồn và tính toàn vẹn của nó**, **nó còn giá trị hay không** và **người đang hiện diện có đúng là chủ thể được nêu hay không**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa *identity evidence* và phân biệt bằng chứng danh tính với thông tin tự khai, tài khoản, thông tin xác thực và quyền truy cập.
2. Xác định các thuộc tính, nguồn phát hành, mức độ tin cậy và giới hạn của các loại bằng chứng khác nhau.
3. Phân biệt **identity resolution**, **evidence validation** và **identity verification** trong một quy trình proofing.
4. Thiết kế luồng đánh giá bằng chứng cho nhân viên, nhà thầu và người tham gia từ xa; xử lý các trường hợp thông tin không nhất quán.
5. Phân tích rủi ro giả mạo giấy tờ, đánh cắp danh tính, video giả, dữ liệu lỗi thời và liên kết sai hồ sơ.
6. Giải thích cách kết quả proofing đi vào **IdP, SSO, SCIM, RBAC/ABAC**, quy trình cấp/thu hồi quyền, kiểm toán và bảo vệ dữ liệu cá nhân.

## 2. Identity evidence khác gì các thành phần IAM khác?

Cần tách riêng những khái niệm thường xuất hiện cùng nhau:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Identity claim – khẳng định** | Người đăng ký nói điều gì về mình? | “Tôi là Nguyễn A”; “Tôi thuộc dự án X” |
| **Identity evidence – bằng chứng** | Có cơ sở nào hỗ trợ khẳng định đó? | Hộ chiếu, giấy tờ tùy thân, chứng thực điện tử đáng tin cậy |
| **Identity proofing – xác minh danh tính ban đầu** | Có thể tin cậy rằng một cá nhân cụ thể gắn với danh tính này đến mức nào? | Đối chiếu bằng chứng với người đăng ký, kiểm tra tính hợp lệ |
| **Identity record – hồ sơ danh tính** | Hệ thống IAM quản lý chủ thể nào? | `personId=U-2048` cùng trạng thái và thuộc tính đã xác minh |
| **Authenticator – phương tiện xác thực** | Lần đăng nhập này, người dùng chứng minh quyền kiểm soát tài khoản bằng gì? | Passkey, khóa bảo mật, ứng dụng xác thực |
| **Authorization – phân quyền** | Người dùng được làm gì đối với tài nguyên? | Đọc báo cáo tài chính của dự án được giao |

Ví dụ: một người cung cấp bằng chứng hợp lệ để chứng minh danh tính, IAM tạo hồ sơ `U-2048`, người đó đăng ký passkey rồi đăng nhập qua SSO. **Proofing** xác lập cơ sở tin cậy về con người; **authentication** chứng minh quyền kiểm soát phương tiện đăng nhập trong phiên; **authorization** quyết định quyền thực hiện thao tác. Không bước nào tự động thay thế toàn bộ các bước còn lại.

Một email công ty có thể chứng minh rằng ai đó có quyền kiểm soát hộp thư trong thời điểm kiểm tra, nhưng **không tự chứng minh danh tính ngoài đời thực**. Tương tự, thư mời làm việc xác nhận một mối quan hệ nghiệp vụ theo nguồn phát hành, nhưng có thể không đủ để xác thực chính xác người đang xuất hiện trước hệ thống.

## 3. Những gì bằng chứng có thể chứng minh

**Bằng chứng phù hợp với một mục tiêu kiểm tra cụ thể.** Không thể đánh giá một tài liệu là “đủ mạnh” nếu chưa rõ khẳng định cần xác minh.

| Khẳng định cần đánh giá | Nguồn/bằng chứng có thể dùng | Điều cần kiểm tra thêm |
|---|---|---|
| Họ tên và thuộc tính định danh | Giấy tờ do cơ quan có thẩm quyền phát hành; chứng thực số được chấp nhận | Tính xác thực, hiệu lực, thuộc tính và liên kết với người đăng ký |
| Ngày sinh hoặc thuộc tính đủ điều kiện | Giấy tờ phù hợp hoặc xác nhận từ nguồn có thẩm quyền | Có cần lưu giá trị đầy đủ hay chỉ cần kết quả đủ điều kiện? |
| Quan hệ làm việc hiện tại | Bản ghi nhân sự/hợp đồng từ nguồn được tổ chức công nhận | Trạng thái và mốc hiệu lực có cập nhật không? |
| Phân công vào dự án | Quyết định phân công do sponsor hoặc hệ thống quản lý dự án phê duyệt | Người phê duyệt có thẩm quyền, dự án còn hiệu lực không? |
| Liên kết với danh tính ở đối tác | Assertion/chứng thực từ IdP hoặc nguồn đối tác đã thiết lập tin cậy | Định danh ổn định, mức bảo đảm và điều kiện tin cậy giữa hai tổ chức |
| Quyền kiểm soát phương tiện liên lạc | Mã xác nhận gửi đến kênh đã đăng ký đúng quy trình | Chỉ chứng minh kiểm soát kênh, không tự chứng minh nhân thân |

Bằng chứng **danh tính cá nhân** và bằng chứng **đủ điều kiện để được cấp quyền** là hai nhóm có liên hệ nhưng không đồng nghĩa. Một hộ chiếu có thể hỗ trợ xác minh nhân thân; nó không chứng minh người đó cần quyền quản trị production. Ngược lại, văn bản sponsor cho phép tham gia dự án có thể chứng minh nhu cầu nghiệp vụ nhưng chưa đủ để kết luận ai đang sử dụng tài khoản.

## 4. Phân loại identity evidence theo hình thức và nguồn

Không có một danh sách bằng chứng phổ quát áp dụng cho mọi quốc gia, ngành và mức rủi ro. Các hình thức dưới đây giúp phân tích nguồn và cách kiểm tra.

### 4.1. Giấy tờ vật lý

Ví dụ: hộ chiếu, giấy tờ tùy thân được cơ quan có thẩm quyền cấp, giấy tờ cư trú hoặc giấy phép phù hợp với khẳng định đang kiểm tra.

**Điều cần xem:** cơ quan phát hành, đặc điểm xác thực, ảnh/thông tin, thời hạn, trạng thái mất/hủy nếu có kênh kiểm tra và bằng chứng người xuất trình là chủ sở hữu. Một bản photocopy hoặc ảnh chụp bị chỉnh sửa có thể làm mất nhiều dấu hiệu bảo mật vốn có ở giấy tờ gốc.

Không nên đặt giả định rằng mọi loại giấy tờ của mọi quốc gia đều có cùng tính năng kiểm tra hoặc cùng giá trị sử dụng.

### 4.2. Bằng chứng điện tử và chứng thực số

Ví dụ: dữ liệu định danh điện tử được phát hành qua hệ thống đáng tin cậy; chứng thực số được ký và có khả năng kiểm tra chữ ký, issuer, đối tượng nhận, thời gian, trạng thái thu hồi theo đặc tả áp dụng.

**Điều cần xem:** nguồn phát hành, chữ ký/tính toàn vẹn, chuỗi tin cậy, chính sách sử dụng, tính mới và **liên kết giữa credential với người đang trình bày**. Một chứng thực có chữ ký hợp lệ không tự chứng minh người gửi là chủ sở hữu nếu thiếu cơ chế ràng buộc hoặc kiểm tra quyền nắm giữ thích hợp.

### 4.3. Xác nhận từ nguồn có thẩm quyền

Ví dụ: bản ghi nhân sự của tổ chức, hệ thống quản lý nhà thầu, hệ thống hợp đồng, hồ sơ đào tạo bắt buộc hoặc xác nhận do cơ quan có thẩm quyền cung cấp.

**Điều cần xem:** ai được phép cập nhật nguồn đó, quá trình truy xuất có được bảo vệ, thuộc tính nào được xác minh, thời điểm cập nhật và khả năng liên kết với đúng cá nhân.

Dữ liệu HR có thể là **nguồn chuẩn cho tình trạng công việc**, nhưng không mặc nhiên là bằng chứng mạnh nhất cho mọi thuộc tính định danh cá nhân. Hệ thống IAM cần xác định **nguồn có thẩm quyền cho từng loại claim**.

### 4.4. Bằng chứng hỗ trợ, không độc lập quyết định

Email, số điện thoại, tài khoản mạng xã hội, thẻ nhân viên, ảnh chân dung tự gửi, mã đơn hàng, thư giới thiệu và lời xác nhận của quản lý có thể hỗ trợ bối cảnh. Mức chứng minh phụ thuộc vào ai phát hành, cách kiểm tra và rủi ro giả mạo.

Ví dụ, việc bấm liên kết trong email có thể xác nhận quyền kiểm soát hộp thư, song không nên được diễn giải thành “danh tính pháp lý đã được xác minh”.

## 5. Đánh giá chất lượng bằng chứng theo nhiều chiều

Thay vì chỉ gắn nhãn “mạnh/yếu”, hãy xem xét những chiều sau:

| Chiều đánh giá | Câu hỏi cần trả lời | Rủi ro khi bỏ qua |
|---|---|---|
| **Nguồn phát hành (issuer)** | Ai tạo bằng chứng, có được tin cậy cho claim này không? | Tin vào dữ liệu tự khai hoặc nguồn giả mạo |
| **Tính xác thực (authenticity)** | Bằng chứng có thật sự do nguồn đó phát hành không? | Giấy tờ/chứng thực giả |
| **Tính toàn vẹn (integrity)** | Nội dung có bị thay đổi ngoài ý muốn hoặc không được phép không? | Chỉnh sửa họ tên, ảnh, ngày sinh |
| **Tính hiệu lực (validity)** | Bằng chứng còn hạn, bị thu hồi, mất giá trị hay bị thay thế không? | Dùng giấy tờ hết hạn hoặc bị hủy |
| **Độ phù hợp (relevance)** | Bằng chứng có hỗ trợ đúng claim cần kiểm tra không? | Hợp đồng bị dùng thay cho xác minh nhân thân |
| **Liên kết với người trình bày (binding)** | Có cơ sở tin cậy rằng cá nhân đang thực hiện proofing là chủ thể trong bằng chứng không? | Dùng giấy tờ thật của người khác |
| **Tính cập nhật (freshness)** | Thuộc tính đã thay đổi sau thời điểm phát hành/kiểm tra chưa? | Vẫn dùng tên, trạng thái hoặc hợp đồng cũ |
| **Độc lập nguồn (independence)** | Hai bằng chứng thực sự độc lập hay cùng sao chép từ một dữ liệu gốc? | Cộng dồn hai bản sao thành “hai nguồn xác minh” |
| **Khả năng kiểm toán** | Có thể biết ai kiểm tra, lúc nào, bằng cách nào và kết quả gì không? | Không giải thích được quyết định proofing |

**Ví dụ:** một ảnh hộ chiếu có định dạng trông hợp lệ nhưng chưa được xác thực với nguồn hoặc đặc điểm an ninh phù hợp. Ngay cả khi giấy tờ thật, người nộp ảnh có thể không phải chủ giấy tờ. Vì vậy, **authenticity**, **validity** và **binding** là những câu hỏi khác nhau.

Mức bằng chứng được chấp nhận cần dựa vào **mức rủi ro, quy định áp dụng, khả năng xác minh và mức bảo đảm cần thiết** của dịch vụ. Không nên gán thứ bậc cứng cho mọi loại giấy tờ trong mọi tình huống.

## 6. Ba hoạt động thường liên quan: resolution, validation và verification

Quy trình proofing thường có ba hoạt động khái niệm:

1. **Identity resolution – phân giải danh tính:** Tập hợp các thuộc tính đủ để phân biệt người đăng ký với hồ sơ khác, phát hiện khả năng trùng hoặc liên kết nhầm. Đây không phải là việc chỉ ghép chuỗi họ tên.
2. **Evidence validation – kiểm tra bằng chứng:** Kiểm tra chứng cứ có phù hợp, chân thực, toàn vẹn và còn hiệu lực bằng phương thức đáng tin cậy hay không.
3. **Identity verification – xác minh người đăng ký:** Xác định người đang tham gia quy trình là chủ thể gắn với bằng chứng đã được kiểm tra.

~~~mermaid
flowchart TD
    A["Người đăng ký cung cấp claim<br/>và bằng chứng phù hợp"] --> B["Resolution<br/>Phân biệt hoặc liên kết hồ sơ"]
    B --> C["Validation<br/>Nguồn phát hành, tính xác thực,<br/>toàn vẹn, hiệu lực"]
    C --> D["Verification<br/>Ràng buộc người đăng ký<br/>với bằng chứng"]
    D --> E{"Đáp ứng mức bảo đảm<br/>và chính sách?"}
    E -->|Có| F["Ghi kết quả proofing<br/>và định danh ổn định"]
    E -->|Thiếu hoặc bất nhất| G["Bổ sung bằng chứng<br/>hoặc kiểm tra thủ công"]
    E -->|Không hợp lệ| H["Từ chối/tạm dừng<br/>theo quy trình"]
    G --> C
    F --> I["IAM: trạng thái danh tính<br/>và điều kiện onboarding"]
~~~

Sơ đồ là **mô hình học tập**, không quy định một thứ tự cứng cho mọi hệ thống. Trong thực tế, các bước có thể được lặp lại hoặc tương tác; kết quả phải đủ chi tiết để biết điều kiện nào đã được đáp ứng.

### 6.1. Ví dụ phân giải danh tính

Hai hồ sơ cùng tên Nguyễn Minh Anh chưa chắc đại diện cho cùng một người. Ngược lại, một người có thể đổi họ tên, dùng tên không dấu, thay email hoặc có giấy tờ được cấp lại. Ghép đơn thuần theo **họ tên + email** có thể tạo cả trùng lặp lẫn gộp nhầm.

Giải pháp là dùng các định danh/thuộc tính được phép xử lý, nguồn có thẩm quyền, lịch sử liên kết và quy trình giải quyết ngoại lệ. Khi chưa đủ chắc chắn, nên **chuyển kiểm tra** thay vì tự hợp nhất hai hồ sơ vì “trông giống nhau”.

### 6.2. Ví dụ kiểm tra bằng chứng

Một credential số có chữ ký mật mã có thể xác minh bằng khóa công khai tin cậy của issuer, nhưng còn phải xem thời điểm phát hành, đối tượng, phạm vi sử dụng và cơ chế trạng thái nếu có. Một giấy tờ vật lý có thể cần kiểm tra dấu hiệu chống giả cùng nguồn tra cứu phù hợp.

**Chữ ký hợp lệ chứng minh một thuộc tính về nguồn và tính toàn vẹn theo mô hình tin cậy**, không tự thay thế toàn bộ quá trình verification và quyết định cấp quyền.

### 6.3. Ví dụ xác minh người sở hữu

Một cá nhân xuất trình giấy tờ thật của người khác. Validation có thể kết luận giấy tờ là thật, nhưng verification phải tìm cơ sở để xác nhận người đang tham gia chính là chủ thể được nêu. Cách làm có thể bao gồm kiểm tra trực tiếp, so khớp có kiểm soát hoặc phương pháp khác được chính sách chấp nhận; mỗi phương pháp có sai số, giới hạn và yêu cầu riêng về quyền riêng tư.

## 7. Quy trình đánh giá identity evidence từ xa

Remote proofing giảm nhu cầu gặp trực tiếp nhưng làm tăng thách thức về **giả mạo nội dung, giả mạo nguồn, người trung gian và đối chiếu người dùng từ xa**. Một quy trình minh họa:

1. **Xác định mục đích và rủi ro:** Cần chứng minh danh tính cá nhân, điều kiện hợp đồng hay cả hai? Dịch vụ sẽ mở quyền gì?
2. **Thông báo dữ liệu cần thiết:** Giải thích thuộc tính phải cung cấp, mục đích, thời hạn lưu và kênh hỗ trợ theo chính sách.
3. **Thu thập bằng chứng qua kênh bảo vệ:** Chỉ yêu cầu loại tài liệu/dữ liệu phù hợp; tránh gửi ảnh giấy tờ qua kênh chat hoặc email không được phê duyệt.
4. **Kiểm tra nguồn, tính xác thực, hiệu lực:** Áp dụng phương thức có thể kiểm chứng; không xem việc tải tệp thành công là validation.
5. **Liên kết người với bằng chứng:** Sử dụng biện pháp phù hợp rủi ro, bao gồm kiểm soát tính hiện diện/liveness nếu cần và được phép; bảo đảm có cách xử lý các trường hợp không thể tự động xác minh.
6. **Đối chiếu danh tính và bản ghi hiện có:** Phát hiện trùng, thay đổi tên, bất nhất thuộc tính hoặc hồ sơ từng bị vô hiệu hóa.
7. **Ra quyết định và lưu dấu vết:** Ghi kết quả, nguồn/mức tin cậy, phương pháp, thời điểm, các ngoại lệ và quyết định xem xét thủ công; hạn chế lưu bản sao bằng chứng quá mức.
8. **Chỉ chuyển sang IAM khi điều kiện đạt:** Gắn hồ sơ có định danh ổn định với nguồn làm việc/sponsor, từ đó mới áp chính sách tạo tài khoản và cấp quyền.

Không nên coi nhận diện khuôn mặt hoặc kiểm tra liveness là bằng chứng chắc chắn tuyệt đối. Các hệ thống này có nguy cơ **sai số, gian lận bằng hình ảnh/video được tạo hoặc chỉnh sửa, điều kiện camera kém và tác động không đồng đều với các nhóm người dùng**. Cần đánh giá hiệu quả thực tế, quyền riêng tư và cung cấp phương án kiểm tra thay thế phù hợp.

## 8. Ví dụ cho Joiner: nhân viên mới và nhà thầu

### 8.1. Nhân viên mới

Một người nhận lời mời làm việc và được tạo bản ghi trong HR. IAM cần hai kết luận có liên quan:

- **Danh tính:** Người đang kích hoạt tài khoản đã được liên kết đáng tin cậy với cá nhân trong hồ sơ nhân sự hay chưa?
- **Điều kiện cấp quyền:** Hồ sơ đã được phê duyệt, quan hệ làm việc có hiệu lực và vị trí/phòng ban nào xác định quyền nền tảng?

Nếu chỉ gửi email kích hoạt tới một địa chỉ tự khai mà không có cơ sở ràng buộc phù hợp, quy trình có thể cấp tài khoản cho người kiểm soát nhầm hộp thư. Sau proofing, IAM có thể tạo định danh ổn định và chuyển sang các bước cấu hình IdP, MFA/SSO và provisioning ứng dụng.

### 8.2. Nhà thầu (contractor) từ đơn vị đối tác

Một nhà cung cấp gửi danh sách chuyên gia tham gia dự án trong ba tháng. **Danh sách đó có thể là bằng chứng về đề xuất phân công, nhưng chưa nhất thiết là bằng chứng đủ để xác minh nhân thân từng cá nhân.** IAM cần xác định nguồn danh sách, sponsor nội bộ, thời hạn hợp đồng, mức xác minh danh tính cá nhân và cơ chế đăng nhập.

Nếu dùng federation với IdP đối tác, tổ chức phải xác định **mức tin cậy trong quá trình proofing phía đối tác**, thuộc tính được chia sẻ và trách nhiệm chặn quyền khi hợp đồng kết thúc. Quyền trong ứng dụng nội bộ vẫn cần giới hạn theo dự án và ngày hiệu lực.

### 8.3. Khi proofing và quyền công việc tách nhau

Một người đã xác minh danh tính thành công nhưng hợp đồng chưa có hiệu lực. Hệ thống có thể lưu kết quả proofing theo chính sách, nhưng **không vì thế tự động mở quyền vào ứng dụng**. Ngược lại, một quản lý xác nhận nhu cầu dự án chưa đủ để bỏ qua bước bảo đảm người nhận tài khoản là đúng cá nhân.

## 9. Evidence trong các biến cố Mover, Rejoiner và Leaver

Identity evidence không chỉ xuất hiện một lần vào ngày đầu tiên.

| Biến cố | Bằng chứng/thuộc tính cần quan tâm | Quyết định IAM tương ứng |
|---|---|---|
| **Mover: chuyển phòng ban** | Quyết định điều chuyển từ nguồn có thẩm quyền | Tính lại RBAC/ABAC, cấp quyền mới và thu hồi quyền cũ |
| **Thay đổi họ tên hợp lệ** | Thông tin cập nhật đã được xác minh theo chính sách | Cập nhật thuộc tính, giữ liên kết định danh ổn định và lịch sử kiểm toán |
| **Đổi phương thức đăng nhập** | Quy trình xác minh quyền kiểm soát tài khoản và có thể xác minh lại danh tính | Khôi phục/đăng ký authenticator đúng người |
| **Rejoiner: quay lại tổ chức** | Quan hệ mới, trạng thái cũ và bằng chứng liên kết danh tính nếu cần | Đánh giá lại mức tin cậy, không khôi phục máy móc toàn bộ quyền cũ |
| **Contractor gia hạn hoặc đổi dự án** | Phê duyệt engagement và sponsor mới | Gia hạn có điều kiện; thu hồi quyền không còn căn cứ |
| **Leaver: rời tổ chức** | Biến cố kết thúc hợp đồng/quan hệ làm việc từ nguồn có thẩm quyền | Vô hiệu hóa hoặc thu hồi quyền, tài khoản, phiên/token theo chính sách |

**Mover không phải lúc nào cũng cần proofing lại toàn bộ**. Nếu chỉ thay đổi phòng ban, dữ liệu đã được xác minh và định danh ổn định vẫn còn đáng tin cậy, có thể chỉ cần kiểm tra **bằng chứng quan hệ công việc và phạm vi nhiệm vụ mới**. Ngược lại, thay đổi nghi vấn, nhiều hồ sơ trùng, nghi ngờ chiếm tài khoản hoặc khôi phục quyền nhạy cảm có thể đòi hỏi kiểm tra tăng cường.

**Leaver** thường dựa trên bằng chứng/trạng thái kết thúc quan hệ nghiệp vụ, không nhất thiết yêu cầu người rời đi xuất trình lại giấy tờ. Điều quan trọng là thu hồi **đúng danh tính và mọi tài khoản gắn với nó**, có readback từ ứng dụng để hạn chế quyền truy cập tồn dư.

## 10. Kết nối proofing với IdP, SSO, SCIM và RBAC/ABAC

Một thiết kế IAM có thể biểu diễn như sau:

~~~mermaid
flowchart LR
    E["Identity evidence<br/>Nguồn + thuộc tính + hiệu lực"] --> P["Identity proofing<br/>Resolution/Validation/Verification"]
    P --> R["Hồ sơ danh tính<br/>ID ổn định + kết quả proofing"]
    H["Nguồn HR / hợp đồng<br/>Trạng thái JML"] --> R
    R --> I["IAM Lifecycle<br/>Quyền mong muốn"]
    I --> D["IdP / SSO<br/>Xác thực, nhóm, thuộc tính"]
    I --> S["SCIM/API<br/>Tạo/cập nhật/thu hồi tài khoản"]
    D --> A["Ứng dụng đích<br/>RBAC/ABAC và kiểm tra quyền"]
    S --> A
    A --> Q["Kiểm toán và đối soát<br/>Quyền thực tế"]
    Q --> I
~~~

Phân chia trách nhiệm cần rõ:

- **Proofing:** Thiết lập và duy trì cơ sở tin cậy về danh tính người dùng, không cấp sẵn mọi quyền.
- **IdP/SSO:** Xác thực và truyền thông tin cần thiết đến ứng dụng tin cậy; chỉ phát hành những thuộc tính đã được phép chia sẻ.
- **SCIM hoặc API khác:** Đồng bộ danh tính/tài khoản/nhóm với ứng dụng; phải theo dõi lỗi và kết quả thực tế.
- **RBAC/ABAC:** Xác định quyền theo vai trò, thuộc tính, tài nguyên và ngữ cảnh. Chẳng hạn `employmentStatus=active` và `projectId` ảnh hưởng đến quyền nhưng không tự chứng minh nhân thân nếu thiếu nguồn tin cậy.
- **Kiểm toán và đối soát:** Lưu dấu vết ai đã được xác minh, bằng cách nào, những chính sách đã áp dụng và liệu quyền trong ứng dụng đã được cập nhật/thu hồi đúng chưa.

### Không truyền mọi dữ liệu evidence sang mọi hệ thống

Ứng dụng chấm công có thể cần định danh nhân viên và trạng thái làm việc; ứng dụng báo cáo có thể chỉ cần vai trò và phạm vi dữ liệu. **Không mặc định đưa ảnh giấy tờ hoặc thông tin định danh nhạy cảm vào token SSO, SCIM hoặc hồ sơ ứng dụng** nếu ứng dụng không cần xử lý chúng.

Tốt hơn là cung cấp **thuộc tính tối thiểu hoặc kết quả đã xác minh**, kèm bảo vệ truyền và lưu trữ theo chính sách.

## 11. Xử lý bằng chứng không nhất quán và quyết định ngoại lệ

Một quy trình tốt phải định nghĩa tình huống nào **cho phép tiếp tục**, tình huống nào cần **bổ sung bằng chứng hoặc rà soát thủ công**, và tình huống nào phải **tạm dừng/từ chối**.

| Tình huống | Điều cần xác định | Hành động hợp lý |
|---|---|---|
| Họ tên trên hồ sơ và giấy tờ khác do đổi tên | Có bằng chứng thay đổi hợp lệ không? | Liên kết lịch sử danh tính, tránh tạo trùng |
| Tên không dấu và có dấu không khớp hoàn toàn | Sai khác do phiên âm, chuyển tự hay là người khác? | Áp quy tắc chuẩn hóa có kiểm soát, không tự gộp hồ sơ |
| Giấy tờ hết hạn | Chính sách/nguồn có cho phép loại bằng chứng khác không? | Thu thập bằng chứng được chấp nhận, không tự sửa ngày hết hạn |
| Ảnh/tệp có dấu hiệu chỉnh sửa | Nguồn và tính toàn vẹn có kiểm chứng được không? | Tạm dừng, chuyển xác minh độc lập |
| Hai hồ sơ trùng thuộc tính | Cùng người hay trùng tên/định danh? | Kiểm tra thủ công theo quy trình chống gộp nhầm |
| Bằng chứng danh tính đạt nhưng HR chưa xác nhận gia nhập | Quan hệ làm việc đã có hiệu lực chưa? | Giữ kết quả proofing nếu được phép; hoãn quyền công việc |
| Quản lý yêu cầu bỏ qua proofing vì gấp | Có quy trình ngoại lệ đã phê duyệt và mức rủi ro chấp nhận được không? | Áp chính sách ngoại lệ chính thức hoặc từ chối, ghi vết |
| Không thể hoàn thành kiểm tra tự động vì điều kiện tiếp cận | Có phương án thay thế đạt mức bảo đảm không? | Hướng đến quy trình hỗ trợ an toàn, tránh phân biệt đối xử |

**Không tự tạo dữ liệu “cho khớp”** hoặc ghi đè thuộc tính nguồn có thẩm quyền để vượt qua một bước kiểm tra. Sai khác có thể là dấu hiệu gian lận, dữ liệu lỗi thời hoặc tình huống hoàn toàn hợp lệ; quyết định cần có căn cứ và nhật ký.

## 12. Rủi ro đối với identity evidence

| Mối đe dọa | Ví dụ | Kiểm soát giảm thiểu |
|---|---|---|
| **Giả mạo tài liệu** | Ảnh giấy tờ bị chỉnh sửa | Kiểm tra đặc điểm, nguồn phát hành và tính toàn vẹn theo khả năng |
| **Dùng giấy tờ thật của người khác** | Người đăng ký nộp giấy tờ bị đánh cắp | Verification ràng buộc đúng cá nhân với evidence |
| **Danh tính tổng hợp (synthetic identity)** | Kết hợp dữ liệu thật và giả để tạo hồ sơ không tồn tại | Resolution, kiểm tra nguồn độc lập, phát hiện bất thường |
| **Deepfake hoặc presentation attack** | Video/ảnh tạo để qua kiểm tra từ xa | Đánh giá rủi ro, kiểm soát trình bày, giám sát, con người xử lý ngoại lệ |
| **Chiếm tài khoản sau proofing** | Kẻ tấn công lấy quyền kiểm soát authenticator | MFA chống lừa đảo khi phù hợp, đăng ký/khôi phục an toàn, phát hiện bất thường |
| **Tấn công vào nguồn dữ liệu** | Kẻ gian sửa bản ghi HR/VMS | Phân quyền cập nhật, phê duyệt thay đổi, log, đối soát |
| **Sai liên kết hồ sơ** | Hai người trùng tên bị gộp chung | Định danh ổn định, quy tắc resolution và review |
| **Lộ dữ liệu danh tính** | Lưu ảnh giấy tờ tại thư mục chia sẻ rộng | Tối thiểu hóa thu thập, mã hóa, phân quyền, thời hạn lưu, xóa an toàn |
| **Sử dụng kết quả quá hạn** | Coi trạng thái proofing cũ là hợp lệ sau sự kiện nghi vấn | Quy tắc kiểm tra lại theo biến cố/rủi ro |
| **Đồng bộ sai quyền sau proofing** | Danh tính đúng nhưng nhóm ứng dụng cấp sai | Tách proofing với authorization; đối soát RBAC/ABAC |

**Một bằng chứng mạnh không loại bỏ rủi ro của các bước sau.** Một cá nhân thật có thể bị cấp sai vai trò, tài khoản bị chiếm sau khi proofing, hoặc quyền không bị thu hồi khi hợp đồng kết thúc. Vì vậy, proofing là **điều kiện đầu vào của một chuỗi kiểm soát**, không phải chứng nhận an toàn vĩnh viễn.

## 13. Bảo vệ quyền riêng tư và lưu trữ bằng chứng

Identity evidence thường chứa dữ liệu nhạy cảm: ảnh chân dung, số giấy tờ, ngày sinh, địa chỉ hoặc dữ liệu sinh trắc. Cách quản trị nên tuân thủ **mục đích rõ ràng, tối thiểu hóa dữ liệu, quyền truy cập giới hạn và thời hạn lưu phù hợp quy định**.

### 13.1. Chỉ lấy những gì cần thiết

Nếu dịch vụ chỉ cần kết luận cá nhân đã vượt qua một mức proofing xác định, cần đánh giá liệu có thể lưu **kết quả xác minh và metadata cần thiết** thay vì lưu toàn bộ bản sao giấy tờ trong mọi hệ thống.

### 13.2. Bảo vệ dữ liệu trong suốt vòng đời

- Dùng kênh thu thập/bảo quản được phê duyệt; không yêu cầu gửi giấy tờ qua chat cá nhân hay email không bảo vệ.
- Giới hạn người được xem ảnh/chứng cứ gốc; ghi log truy cập của nhân sự xác minh.
- Mã hóa dữ liệu nhạy cảm trong truyền và khi lưu theo kiến trúc.
- Quản lý khóa, sao lưu, xóa hoặc ẩn dữ liệu theo chính sách lưu giữ và yêu cầu pháp lý.
- Không đưa thông tin định danh nhạy cảm vào log ứng dụng, URL, token hoặc thông báo lỗi nếu không cần.
- Phân biệt dữ liệu để **kiểm toán quyết định** với bản sao bằng chứng thô; mỗi loại có chính sách lưu khác nhau.

### 13.3. Sinh trắc học cần đánh giá riêng

Nếu dùng ảnh khuôn mặt hoặc đặc trưng sinh trắc để ràng buộc người với bằng chứng, cần xem xét cơ sở xử lý hợp lệ, tính cần thiết, độ chính xác, tác động đến các nhóm người dùng, cơ chế bảo vệ mẫu dữ liệu, phương án thay thế và quy trình giải quyết khi xác minh thất bại. **Sinh trắc học không phải bằng chứng tuyệt đối và không nên được dùng vượt quá mục đích cho phép.**

## 14. Mô hình dữ liệu tối thiểu cho kết quả proofing

Hệ thống có thể giữ **kết quả xử lý bằng chứng** tách với tài liệu thô. Dưới đây là mô hình JSON *minh họa*, không phải schema chuẩn bắt buộc hay lời khuyên lưu toàn bộ thuộc tính:

~~~json
{
  "personId": "U-2048",
  "proofing": {
    "decision": "VERIFIED",
    "verifiedAt": "2026-03-10T09:15:00Z",
    "method": "REMOTE_VERIFICATION",
    "evidenceMetadata": [
      {
        "category": "GOVERNMENT_ISSUED_ID",
        "issuerChecked": true,
        "authenticityChecked": true,
        "validityChecked": true,
        "subjectBindingChecked": true
      }
    ],
    "reviewRequiredOn": [
      "SUSPECTED_ACCOUNT_TAKEOVER",
      "MATERIAL_IDENTITY_ATTRIBUTE_CHANGE"
    ]
  },
  "engagement": {
    "type": "CONTRACTOR",
    "status": "ACTIVE",
    "sponsorId": "S-1007"
  }
}
~~~

Giá trị trên chỉ minh họa **cách tách kết quả proofing khỏi trạng thái engagement**. Một trạng thái `VERIFIED` không tự nói lên mức bảo đảm, phạm vi nguồn hoặc thời hạn sử dụng nếu thiếu metadata/chính sách. Khi triển khai phải có phiên bản chính sách, bằng chứng kiểm toán và cơ chế kiểm soát quyền xem phù hợp.

Không lưu dữ liệu giấy tờ thật, định danh nhạy cảm hay sinh trắc trong các ví dụ/tài liệu kiểm thử công khai.

## 15. Tình huống tổng hợp: cấp tài khoản cho nhà thầu theo dự án

**Bối cảnh:** Một chuyên gia tư vấn tên Linh tham gia dự án phân tích dữ liệu trong tám tuần. Sponsor nội bộ phê duyệt nhu cầu đọc dashboard đã được giới hạn. Nhà cung cấp gửi một email chứa họ tên, ảnh giấy tờ và thông tin hợp đồng.

**Câu hỏi 1 – Bằng chứng nào đang có?**  
Ảnh giấy tờ là bằng chứng tiềm năng cho danh tính cá nhân nhưng cần kiểm tra nguồn, hiệu lực và sự liên kết với Linh. Email nhà cung cấp là thông tin hỗ trợ; hợp đồng là căn cứ nghiệp vụ cho dự án/thời hạn nếu được kiểm tra từ nguồn có thẩm quyền. Không thể coi mọi thông tin trong email đều đã được xác minh.

**Câu hỏi 2 – Khi nào có thể tạo tài khoản?**  
Sau khi yêu cầu proofing và nguồn nghiệp vụ đạt điều kiện theo chính sách. Có thể chuẩn bị tài khoản ở trạng thái chưa có quyền hoạt động nếu cần, nhưng chỉ mở truy cập ở mốc được phép và sau khi bảo đảm những điều kiện áp dụng.

**Câu hỏi 3 – IdP và SCIM giúp gì?**  
IdP/SSO hỗ trợ đăng nhập, xác thực và thuộc tính tin cậy; SCIM hoặc API giúp đồng bộ tài khoản/nhóm sang ứng dụng. Cả hai đều **không thay thế validation/verification của identity evidence**. Ứng dụng vẫn phải giới hạn dashboard theo vai trò, dự án, dữ liệu và thời hạn.

**Câu hỏi 4 – Nếu Linh đổi dự án sau bốn tuần?**  
Thông tin proofing cá nhân có thể vẫn hợp lệ nếu không có điều kiện kiểm tra lại; tuy nhiên, IAM phải cập nhật engagement, sponsor và RBAC/ABAC để thu hồi quyền dự án cũ và chỉ cấp quyền dự án mới có căn cứ.

**Câu hỏi 5 – Khi hết tám tuần?**  
Nguồn hợp đồng phát biến cố Leaver; IAM thu hồi quyền, tài khoản/nhóm, phiên/token và quyền chia sẻ liên quan theo chính sách. Đối soát kết quả từng ứng dụng để tránh quyền tồn dư. Dữ liệu/bằng chứng cần lưu giữ phục vụ kiểm toán được bảo vệ theo thời hạn riêng.

### Bài tập tự kiểm tra

1. Một giấy tờ có chữ ký số hợp lệ nhưng đã bị thu hồi: thuộc tính nào của bằng chứng chưa đạt?
2. Hai hồ sơ có cùng tên, khác ngày sinh: có thể tự động hợp nhất chỉ dựa vào email giống nhau không?
3. Một nhân viên đăng nhập bằng passkey thành công: điều này có chứng minh mọi thuộc tính nhân thân đã được kiểm tra không?
4. Nhà thầu gia hạn hợp đồng: có cần xác minh lại giấy tờ tùy thân trong mọi trường hợp không, hay cần xem xét biến cố/rủi ro và chính sách?
5. Vì sao ứng dụng không nên nhận cả ảnh giấy tờ chỉ để kiểm tra `projectId` và `role`?

**Gợi ý đáp án:** (1) Tính hiệu lực/trạng thái; (2) Không, cần resolution có căn cứ; (3) Không, authentication và proofing khác nhau; (4) Tùy điều kiện, thường phải đánh giá lại quan hệ, thời hạn và quyền, chỉ re-proofing cá nhân khi cần; (5) Nguyên tắc tối thiểu hóa dữ liệu và phân tách trách nhiệm.

## 16. Checklist triển khai và ghi nhớ

Đối với một quy trình dùng identity evidence làm căn cứ thiết lập danh tính IAM, hãy kiểm tra:

- [ ] Đã xác định **claim và mục đích** cần chứng minh, không yêu cầu bằng chứng vượt nhu cầu?
- [ ] Loại bằng chứng và **nguồn phát hành** có phù hợp với claim và mức rủi ro?
- [ ] Đã kiểm tra **tính xác thực, toàn vẹn, hiệu lực, tính cập nhật** bằng cơ chế phù hợp?
- [ ] Đã có cách **liên kết người trình bày với bằng chứng**, không chỉ kiểm tra tệp?
- [ ] Đã kiểm tra trùng hồ sơ, sai khác tên/thuộc tính và có đường rà soát thủ công?
- [ ] Trạng thái/kết quả proofing có **nguồn, thời điểm, phương thức, quyết định** để kiểm toán?
- [ ] Dữ liệu giấy tờ/sinh trắc đã được **giảm thiểu, phân quyền và quản lý thời hạn lưu**?
- [ ] Danh tính đã xác minh có được tách khỏi **điều kiện công việc, chính sách cấp quyền và authenticator**?
- [ ] Quyền từ **IdP/SSO/SCIM/RBAC/ABAC** đã được kiểm chứng tại hệ thống thực?
- [ ] Các biến cố **Joiner–Mover–Leaver, rejoiner, recovery** có quy tắc cập nhật hoặc kiểm tra lại khi thích hợp?
- [ ] Khi rời tổ chức, hệ thống xác định được mọi tài khoản/phiên/token gắn với **đúng chủ thể** và giảm được quyền tồn dư?

**Ghi nhớ:** *Identity evidence* là nền tảng của việc đưa **đúng người** vào vòng đời danh tính, nhưng phải được đánh giá theo **nguồn, tính xác thực, hiệu lực, độ phù hợp và sự liên kết với cá nhân**. Kết quả proofing đáng tin cậy giúp IAM gắn đúng tài khoản và thông tin công việc, từ đó áp dụng **Joiner–Mover–Leaver, IdP/SSO/SCIM, RBAC/ABAC, kiểm toán và thu hồi quyền** chính xác hơn trong toàn bộ vòng đời.

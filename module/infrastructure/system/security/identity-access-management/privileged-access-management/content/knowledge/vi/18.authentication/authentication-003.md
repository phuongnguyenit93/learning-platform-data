# Certificate authentication — Xác thực bằng chứng thư trong PAM

## 1. Chứng thư giải quyết bài toán gì?

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), mật khẩu không phải cách duy nhất để chứng minh danh tính. Người quản trị, thiết bị, gateway hoặc workload có thể xác thực bằng một khóa riêng gắn với chứng thư do một bên được tin cậy phát hành.

**Certificate authentication** là cơ chế sử dụng chứng thư và bằng chứng sở hữu khóa riêng tương ứng để xác thực. Chứng thư cung cấp một ràng buộc có chữ ký giữa một khóa công khai và các thuộc tính danh tính theo chính sách của bên phát hành.

Một ví dụ điển hình là mTLS: máy khách và máy chủ xác thực nhau bằng chứng thư trong kết nối TLS. Trong PAM, cơ chế này có thể dùng cho:

- Máy trạm hoặc người quản trị truy cập cổng quản trị.
- Gateway xác thực với hệ thống đích.
- Agent hoặc workload xác thực với vault để nhận quyền ngắn hạn.
- Dịch vụ nội bộ gọi API quản lý quyền.
- Một số đường quản trị dùng authenticator phần cứng và chứng thư phù hợp.

Giá trị của cơ chế không chỉ nằm ở việc bỏ nhập mật khẩu. Nó cho phép dùng khóa mật mã, cấp credential có thời hạn, tách danh tính khỏi bí mật dùng chung và tự động hóa vòng đời xác thực.

Tuy nhiên, một chứng thư hợp lệ không tự có nghĩa chủ thể được toàn quyền. PAM vẫn phải kiểm tra tài nguyên, vai trò, phê duyệt, cửa sổ truy cập và điều kiện rủi ro.

Bài học tập trung vào chứng thư X.509, đặc biệt trong mTLS, đồng thời phân biệt với các loại chứng thư khác để tránh áp dụng sai mô hình tin cậy.

## 2. Chứng thư, khóa riêng và danh tính là ba khái niệm khác nhau

### 2.1. Khóa công khai và khóa riêng

Một cặp khóa bất đối xứng gồm:

- **Khóa riêng:** được chủ thể bảo vệ và sử dụng cho các thao tác mật mã phù hợp.
- **Khóa công khai:** được bên xác minh sử dụng để kiểm tra bằng chứng tương ứng.

Trong cơ chế xác thực, chủ thể chứng minh rằng mình sử dụng được khóa riêng. Không cần gửi khóa riêng đến máy chủ để máy chủ kiểm tra.

Nếu khóa riêng bị lấy hoặc bị sử dụng trái phép, kẻ khác có thể giả làm chủ thể trong phạm vi cơ chế chấp nhận khóa đó. Vì vậy, bảo vệ khóa riêng quan trọng không kém bảo vệ mật khẩu.

### 2.2. Chứng thư không phải bản sao khóa riêng

Một chứng thư thường chứa:

| Thành phần | Ý nghĩa |
|---|---|
| Khóa công khai | Khóa được gắn với danh tính hoặc thuộc tính đã chứng nhận |
| Bên phát hành | CA hoặc chủ thể ký chứng thư |
| Định danh chứng thư | Thường gồm serial và bên phát hành để quản lý, thu hồi |
| Subject và các thuộc tính danh tính | Thông tin dùng để mô tả hoặc ánh xạ chủ thể |
| SAN nếu có | Các dạng tên hoặc định danh theo profile chứng thư |
| Khoảng hiệu lực | Thời điểm bắt đầu và kết thúc hiệu lực |
| Ràng buộc và mục đích sử dụng | Giới hạn cách chứng thư hoặc khóa được dùng |
| Chữ ký của bên phát hành | Cho phép kiểm tra tính toàn vẹn và nguồn phát hành theo chuỗi tin cậy |

Chứng thư thường không phải bí mật theo nghĩa của khóa riêng. Sao chép riêng một chứng thư không đủ để hoàn thành một cơ chế xác thực có kiểm tra bằng chứng sở hữu khóa riêng.

Dù vậy, chứng thư có thể chứa thông tin nội bộ như tên hệ thống, danh tính hoặc địa chỉ tổ chức. Không nên công khai hoặc ghi log toàn bộ một cách tùy tiện.

### 2.3. Danh tính được chứng nhận phụ thuộc quy trình phát hành

Chữ ký của CA không tự chứng minh rằng mọi thông tin trong chứng thư đúng theo nhu cầu PAM. Bên tin cậy phải hiểu CA đã xác minh điều gì và được phép phát hành cho phạm vi nào.

Ví dụ:

- Chứng thư thiết bị có thể chứng minh một khóa thuộc thiết bị được quản lý.
- Chứng thư người dùng có thể gắn với một danh tính cá nhân theo quy trình đăng ký.
- Chứng thư workload có thể gắn với một dịch vụ, môi trường và đơn vị triển khai.
- Chứng thư máy chủ có thể dùng để xác thực dịch vụ mà người dùng kết nối tới.

Không dùng chứng thư thiết bị để mặc nhiên kết luận người đang ngồi trước máy là một quản trị viên cụ thể.

## 3. Mô hình tin cậy và chuỗi chứng thư

### 3.1. Root, intermediate và chứng thư đầu cuối

Một mô hình phổ biến gồm:

~~~text
Trust anchor được cấu hình
    → CA trung gian được phép phát hành
        → Chứng thư đầu cuối của người dùng, thiết bị hoặc dịch vụ
~~~

Bên xác minh xây dựng và kiểm tra đường chứng thư theo chính sách. Việc thấy một chứng thư có chữ ký không đủ; cần biết chữ ký đó dẫn đến một trust anchor được chấp nhận và các ràng buộc trên đường đều thỏa mãn.

Các kiểm tra thường liên quan đến:

- Chữ ký hợp lệ và đường chứng thư được tin cậy.
- Thời hạn của các chứng thư theo quy tắc kiểm tra.
- Vai trò CA và các giới hạn của chứng thư trung gian.
- Mục đích sử dụng khóa và chứng thư phù hợp.
- Chính sách thuật toán và các ràng buộc áp dụng.
- Trạng thái thu hồi theo thiết kế.
- Danh tính cuối cùng có đúng với điều ứng dụng yêu cầu không.

Nên dùng bộ xác minh và thư viện phù hợp thay vì tự viết một phần kiểm tra chữ ký rồi coi như đã xác minh đầy đủ chứng thư.

### 3.2. Trust store máy chủ khác trust store xác thực máy khách

Một hệ thống có thể tin các CA công cộng để kiểm tra website bên ngoài. Điều đó không có nghĩa mọi chứng thư từ các CA đó đều nên được chấp nhận để đăng nhập quyền đặc quyền.

Đối với xác thực máy khách vào PAM, nên xác định rõ:

- CA hoặc trust domain nào được chấp nhận.
- Profile chứng thư nào được dùng cho loại danh tính nào.
- Môi trường và phạm vi mà CA được phát hành.
- Cách ánh xạ chứng thư sang principal nội bộ.
- Vai trò nào có thể được cấp sau xác thực.

Nếu ứng dụng chỉ kiểm tra “chứng thư do một CA trong danh sách tin cậy ký” rồi cho phép vào, phạm vi người có thể đăng nhập có thể rộng hơn dự kiến rất nhiều.

### 3.3. Chứng thư tự ký không tự trở thành đáng tin

Một chứng thư tự ký không có chuỗi đến CA khác. Nó chỉ được chấp nhận khi có một cơ chế thiết lập tin cậy phù hợp, chẳng hạn cấu hình trust anchor hoặc pin theo quy trình được quản trị.

Không tắt toàn bộ kiểm tra chứng thư chỉ vì đang dùng hạ tầng nội bộ. Làm vậy loại bỏ nền tảng xác minh danh tính mà cơ chế này cần.

Nếu dùng pin, phải chuẩn bị quy trình thay khóa, thu hồi và cập nhật tin cậy. Một cấu hình pin không được quản lý có thể gây gián đoạn hoặc khiến đội vận hành giữ mãi một khóa đã không còn an toàn.

## 4. Xác thực mTLS diễn ra như thế nào?

### 4.1. TLS một chiều và mTLS

Trong TLS xác thực máy chủ, máy khách kiểm tra chứng thư máy chủ để xác định dịch vụ kết nối tới. Máy khách có thể xác thực bằng mật khẩu hoặc cơ chế khác ở tầng ứng dụng.

Trong **mutual TLS — mTLS**, máy chủ cũng yêu cầu máy khách trình chứng thư và chứng minh sở hữu khóa riêng tương ứng theo giao thức.

Luồng khái niệm:

1. Máy khách kết nối tới dịch vụ.
2. Máy khách kiểm tra danh tính và chứng thư của máy chủ.
3. Máy chủ yêu cầu chứng thư máy khách theo cấu hình.
4. Máy khách trình chứng thư phù hợp và thực hiện bằng chứng bằng khóa riêng.
5. Máy chủ xác minh đường tin cậy, thuộc tính và bằng chứng.
6. Ứng dụng ánh xạ danh tính rồi kiểm tra quyền.

Các bước cụ thể phụ thuộc giao thức và triển khai. Không nên tự xây một giao thức “gửi chứng thư qua HTTP rồi cho đăng nhập” vì việc gửi chứng thư công khai không chứng minh người gửi sở hữu khóa riêng.

### 4.2. Xác thực máy chủ vẫn quan trọng

Có chứng thư máy khách không phải lý do bỏ kiểm tra máy chủ. Máy khách phải xác minh rằng đang kết nối đúng dịch vụ, bao gồm kiểm tra danh tính máy chủ theo cơ chế phù hợp, chẳng hạn tên DNS trong SAN đối với kết nối TLS theo tên máy chủ.

Nếu người quản trị bỏ qua cảnh báo hoặc client được cấu hình chấp nhận mọi chứng thư máy chủ, họ có thể kết nối tới một dịch vụ giả hoặc sai môi trường. Cơ chế xác thực máy khách không thay thế xác thực phía đối diện.

### 4.3. mTLS không tự cấp quyền ứng dụng

Sau khi mTLS thành công, ứng dụng mới biết một chủ thể đáp ứng cơ chế xác thực. Nó vẫn cần quyết định:

- Chủ thể là người, thiết bị hay workload?
- Principal nội bộ nào tương ứng?
- Principal đó còn hoạt động không?
- Có quyền gọi API hoặc mở phiên này không?
- Có đủ phê duyệt và còn trong cửa sổ không?
- Phạm vi của lần cấp quyền là gì?

Một workload được xác thực với vault để lấy một secret không được tự suy ra quyền quản trị toàn bộ vault.

## 5. Ánh xạ chứng thư sang danh tính PAM

### 5.1. Không chỉ dựa vào tên hiển thị

Subject hoặc Common Name có thể dễ đọc nhưng không nhất thiết là định danh duy nhất, ổn định hoặc phù hợp để cấp quyền.

Ví dụ, hai CA khác nhau có thể phát hành chứng thư cùng Subject. Một người được đổi tên cũng có thể cần giữ principal nội bộ không đổi. Vì vậy cần một quy tắc ánh xạ có phạm vi tin cậy rõ ràng.

Một mô hình khái niệm:

~~~text
Trust domain hoặc bên phát hành được chấp nhận
    + loại danh tính
    + thuộc tính định danh đã được quy định trong profile
        → principal nội bộ
~~~

Nếu profile dùng SAN dạng URI để định danh, chỉ dùng giá trị đúng namespace và dạng được chính sách chấp nhận. Một ví dụ minh họa có thể là:

~~~text
Loại chủ thể: human
Định danh trong profile: urn:example:pam:user:engineer-17
Principal nội bộ: engineer-17
Môi trường: production
~~~

Cách mã hóa trên chỉ minh họa mô hình. Không giả định mọi sản phẩm hỗ trợ sẵn cùng một dạng SAN hoặc cùng quy tắc ánh xạ.

### 5.2. Tách danh tính khỏi role

Không nên cấp full administrator chỉ vì Subject chứa chữ “admin” hoặc vì người yêu cầu có thể tự cung cấp thuộc tính đó khi xin chứng thư.

Role phải được quyết định bởi một nguồn phân công hoặc chính sách có thẩm quyền. Nếu dùng thuộc tính chứng thư để ánh xạ quyền, quy trình phát hành phải kiểm soát chặt ai được nhận thuộc tính nào, cho phạm vi nào và trong thời gian nào.

Một nguyên tắc hữu ích:

~~~text
Chứng thư trả lời: khóa này thuộc danh tính nào theo nguồn tin cậy?

Chính sách PAM trả lời: danh tính đó được làm gì trong yêu cầu hiện tại?
~~~

### 5.3. Danh tính người dùng và danh tính kết nối trên đích

PAM gateway có thể xác thực người dùng bằng một cơ chế, sau đó xác thực với hệ thống đích bằng chứng thư của gateway hoặc tài khoản kỹ thuật.

Trong trường hợp đó, hệ thống đích có thể chỉ nhìn thấy danh tính gateway hoặc tài khoản kỹ thuật. Cần giữ liên kết:

~~~text
Người vận hành
    → phiên PAM
    → yêu cầu và phê duyệt
    → danh tính gateway hoặc credential dùng trên đích
    → phiên đích và hành động
~~~

Không mô tả chứng thư gateway như thể hệ thống đích đã trực tiếp xác thực người vận hành.

Nếu truyền danh tính qua proxy hoặc header, backend phải chỉ tin dữ liệu từ một hop đã xác thực và được bảo vệ. Header do client tự gửi không thay thế chứng thư hoặc một assertion đáng tin cậy.

## 6. Certificate authentication trong luồng PAM

~~~mermaid
flowchart TD
    A[Người dùng hoặc workload yêu cầu kết nối] --> B[Xác minh danh tính dịch vụ đích]
    B --> C[Trình chứng thư và chứng minh sở hữu khóa riêng]
    C --> D[Kiểm tra chuỗi, thời hạn, mục đích và trạng thái]
    D --> E{Chứng thư và bằng chứng hợp lệ?}
    E -- Không --> F[Từ chối và ghi lý do phù hợp]
    E -- Có --> G[Ánh xạ sang principal theo nguồn tin cậy]
    G --> H[Kiểm tra quyền, phê duyệt, thời gian và ngữ cảnh]
    H --> I{Đủ điều kiện?}
    I -- Không --> F
    I -- Có --> J[Cấp phiên hoặc lease có giới hạn]
    J --> K[Giám sát vòng đời, hết hạn và thu hồi]
~~~

### 6.1. Truy cập tương tác của con người

Chứng thư có thể là một phần của cơ chế xác thực người dùng. Với quyền nhạy cảm, vẫn phải xác định liệu phương thức đó có đáp ứng MFA, yêu cầu độ mới xác thực và điều kiện thiết bị hay không.

Nếu khóa chỉ được lưu trong một file dễ sao chép, mức bảo đảm khác với một khóa được bảo vệ bằng phần cứng và có xác minh người dùng phù hợp.

### 6.2. Xác thực workload với vault

Một workload có thể dùng chứng thư ngắn hạn để xác thực, sau đó nhận credential hoặc lease giới hạn cho đúng dịch vụ.

Cần tránh biến cùng một chứng thư và khóa thành danh tính chung cho mọi bản triển khai. Khi nhiều workload dùng chung một khóa, việc thu hồi và quy trách nhiệm trở nên khó hơn.

Phạm vi cần phân biệt dịch vụ, môi trường và vai trò. Chứng thư của một workload development không nên tự được nhận credential production chỉ vì cùng tên ứng dụng.

### 6.3. Chứng thư ngắn hạn phục vụ JIT

Một thiết kế có thể chỉ phát hành chứng thư sau khi yêu cầu được duyệt và chặn hạn chứng thư bởi khoảng truy cập:

~~~text
certificate_not_after <= approved_access_end
session_end <= min(
    certificate_policy_limit,
    approved_access_end,
    session_start + maximum_session_duration
)
~~~

Công thức thứ hai là yêu cầu chính sách ứng dụng, không phải hành vi tự động của mọi phiên TLS. Hệ thống phải thực sự áp dụng hạn phiên và các điều kiện tương ứng.

Nếu chứng thư được dùng để đổi lấy token ứng dụng, token có vòng đời riêng. Chứng thư hết hạn hoặc bị thu hồi không tự bảo đảm mọi token đã phát hành mất hiệu lực ngay.

## 7. Vòng đời chứng thư và khóa

### 7.1. Đăng ký và bootstrap danh tính

Trước khi có chứng thư, cần xác minh ai hoặc workload nào được phép nhận nó. Đây là bước thiết lập tin cậy ban đầu, thường gọi là bootstrap hoặc enrollment.

Các câu hỏi quan trọng:

- Ai có thể yêu cầu phát hành?
- Bằng chứng nào xác nhận danh tính?
- Ai được đặt các thuộc tính trong yêu cầu?
- CA có tự kiểm tra hoặc thay thế thuộc tính không đáng tin cậy không?
- Có kiểm tra chủ thể sử dụng được khóa riêng tương ứng không?
- Điều kiện nào cho phép gia hạn hoặc phát hành lại?

Không nên cho người dùng tự nhập một Subject mang tên quản trị viên rồi tự động phát hành chứng thư có quyền cao. Một yêu cầu ký chứng thư chưa phải là bằng chứng thẩm quyền đối với mọi thuộc tính trong đó.

### 7.2. Tạo và bảo vệ khóa

Khóa riêng có thể được bảo vệ bằng cơ chế phần mềm, kho khóa hệ điều hành hoặc phần cứng như TPM, smart card hay HSM theo kiến trúc.

Cần xác định:

- Khóa được tạo ở đâu và có thể xuất ra hay không.
- Chủ thể hoặc tiến trình nào được sử dụng khóa.
- Có yêu cầu PIN, xác minh người dùng hoặc điều kiện thiết bị không.
- Cách phát hiện việc dùng bất thường.
- Cách thu hồi khi thiết bị mất hoặc chủ thể ngừng hoạt động.

Phần cứng không tự ngăn mọi lạm dụng. Một endpoint bị kiểm soát có thể tìm cách yêu cầu phần cứng ký thay cho người dùng trong phạm vi được phép. Bảo vệ thiết bị và quyền sử dụng khóa vẫn quan trọng.

Không gửi private key qua ticket hoặc đưa vào mã nguồn. Nếu một quy trình buộc phải phân phối khóa, cần đánh giá rủi ro và bảo vệ đường phân phối; không coi đó là thao tác sao chép file thông thường.

### 7.3. Phát hành và thời hạn

Profile chứng thư cần phù hợp loại chủ thể và mục đích. Ví dụ trong TLS client authentication, chính sách có thể yêu cầu các thuộc tính sử dụng phù hợp với xác thực máy khách.

Thời hạn ngắn giúp giảm khoảng sử dụng một credential bị lộ, nhưng làm tăng phụ thuộc vào khả năng phát hành hoặc gia hạn. Cần cân bằng theo rủi ro và khả năng vận hành.

Không chọn thời hạn nhiều năm chỉ để tránh thiết kế gia hạn. Cũng không chọn thời hạn rất ngắn mà không có cơ chế giám sát và phục hồi khi dịch vụ phát hành bị lỗi.

### 7.4. Gia hạn khác thay khóa

- **Gia hạn hoặc phát hành chứng thư mới:** tạo một chứng thư có hiệu lực mới theo quy trình.
- **Thay khóa:** tạo cặp khóa mới và chuyển sang sử dụng khóa đó.

Một lần gia hạn có thể vẫn dùng khóa cũ nếu chính sách cho phép; không nên báo đã thay khóa khi thực tế chỉ thay chứng thư.

Khi có dấu hiệu khóa bị lộ, việc phát hành lại chứng thư cho cùng khóa không giải quyết nguyên nhân. Cần xử lý khóa, các chứng thư liên quan và các phiên hoặc token đã được tạo.

### 7.5. Chuyển đổi không gây gián đoạn ngoài ý muốn

Trong giai đoạn thay chứng thư hoặc CA, có thể cần thời gian chuyển tiếp. Phải quản lý rõ:

- Bên nào đã nhận trust anchor hoặc chain mới.
- Chứng thư mới được dùng từ lúc nào.
- Chứng thư và khóa cũ còn được chấp nhận đến khi nào.
- Cách rollback nếu gặp lỗi.
- Cách loại bỏ tin cậy cũ sau chuyển đổi.

Không để một cấu hình “chấp nhận cả cũ và mới tạm thời” tồn tại vô hạn.

## 8. Thu hồi và xử lý chứng thư hết hạn

### 8.1. Khi nào cần thu hồi?

Các tình huống có thể gồm:

- Mất thiết bị hoặc nghi lộ khóa.
- Nhân sự nghỉ việc hoặc không còn đủ điều kiện.
- Workload bị xâm nhập hoặc bị loại bỏ.
- Chứng thư phát hành sai thuộc tính.
- CA hoặc quy trình phát hành bị ảnh hưởng.
- Quyền hoặc trust domain thay đổi.

Thu hồi chứng thư và thu hồi quyền ứng dụng có liên quan nhưng không đồng nhất. Một người có thể vẫn có chứng thư hợp lệ nhưng đã mất quyền PAM; ứng dụng phải kiểm tra trạng thái quyền hiện hành.

### 8.2. CRL, OCSP và chính sách kiểm tra trạng thái

Một hệ thống có thể sử dụng danh sách thu hồi (CRL), truy vấn trạng thái như OCSP, thông tin trạng thái cục bộ hoặc mô hình khác phù hợp.

Cần quy định:

- Thành phần nào kiểm tra.
- Tần suất cập nhật và tuổi dữ liệu chấp nhận được.
- Cách xử lý dữ liệu không còn mới.
- Cách xử lý trạng thái không xác định.
- Hành vi khi nguồn trạng thái không khả dụng.
- Độ trễ thu hồi tối đa mà thiết kế đáp ứng.

Một kết quả “good” từ trước không chứng minh chứng thư chưa bị thu hồi ở thời điểm hiện tại nếu dữ liệu đã quá cũ. Ngược lại, lỗi mạng không nên bị diễn giải thành “chắc chắn chưa thu hồi”.

Đối với quyền đặc quyền, hành vi khi không xác minh được phải được quyết định trước theo rủi ro. Nếu có tuyến khẩn cấp, tuyến đó cần kiểm soát riêng; không âm thầm tắt kiểm tra thu hồi.

### 8.3. Chứng thư ngắn hạn không loại bỏ mọi nhu cầu thu hồi

Thời hạn ngắn có thể giới hạn thời gian sử dụng còn lại của chứng thư. Nhưng nếu chứng thư còn hiệu lực trong lúc có sự cố, tổ chức vẫn cần biết cách chặn danh tính, ngăn phát hành tiếp và xử lý các quyền đã được tạo.

Không tuyên bố “không cần thu hồi” chỉ vì credential sống ngắn. Cần giải thích rõ tổ chức chấp nhận độ trễ nào và có cơ chế bổ sung gì.

### 8.4. Hết hạn không tự đóng mọi kết nối

Một phiên TLS được thiết lập lúc chứng thư còn hiệu lực có thể tiếp tục tồn tại sau thời điểm chứng thư hết hạn nếu ứng dụng không áp dụng giới hạn bổ sung.

Tương tự, thu hồi chứng thư không nhất thiết làm mọi kết nối đang mở tự biến mất. Cần có cơ chế:

- Chặn kết nối mới.
- Giới hạn thời lượng phiên.
- Đánh giá lại hoặc chấm dứt phiên khi có tín hiệu thu hồi.
- Xử lý session resumption theo khả năng và chính sách của triển khai.
- Thu hồi entitlement, token hoặc lease phát sinh nếu cần.

Việc kiểm thử phải đi tới kết quả thực tế trên điểm thực thi, không chỉ thấy một bản ghi chứng thư đã đổi trạng thái.

## 9. Certificate authentication có phải MFA không?

Không phải mọi xác thực bằng chứng thư đều là MFA.

Nếu một tiến trình có file private key và tự sử dụng được, cơ chế đó chủ yếu cung cấp bằng chứng sử dụng khóa. Việc file được đặt mật khẩu không tự chứng minh rằng mỗi lần đăng nhập đều có một yếu tố thứ hai được xác minh theo yêu cầu PAM; khóa có thể đã được mở và lưu trong bộ nhớ.

Một cơ chế dùng smart card hoặc authenticator với khóa được bảo vệ và xác minh người dùng bằng PIN có thể đáp ứng nhiều yếu tố khi thiết kế và kiểm tra đúng. Cần dựa trên khả năng được thực thi, không chỉ dựa vào tên thiết bị.

Cũng cần phân biệt:

- Người dùng đã MFA khi xin chứng thư.
- Người dùng MFA khi sử dụng chứng thư.
- Thiết bị có chứng thư hợp lệ.
- Người dùng có mặt và được xác minh cho hành động hiện tại.

Bốn điều này không tự thay thế lẫn nhau.

Đối với thao tác nhạy cảm như checkout credential hoặc đổi chính sách PAM, có thể cần một bước xác thực mới hoặc mạnh hơn. Chứng thư hợp lệ không tự làm bằng chứng xác thực trở nên mới vô thời hạn.

Workload không có người để nhập PIN hoặc nhận OTP mỗi lần chạy. Nó cần mô hình xác thực danh tính máy phù hợp, bảo vệ khóa, quyền tối thiểu và cơ chế thu hồi, thay vì dùng chung yếu tố MFA tương tác của nhân viên.

## 10. Phân biệt X.509 với chứng thư SSH

Cùng có từ “certificate” nhưng các hệ sinh thái không dùng chung mọi cấu trúc và quy tắc.

| Khía cạnh | X.509 trong TLS | Chứng thư người dùng trong một hệ thống SSH hỗ trợ chứng thư |
|---|---|---|
| Mô hình điển hình | Đường chứng thư tới trust anchor | Khóa CA SSH được cấu hình tin cậy theo triển khai |
| Thuộc tính danh tính | Subject, SAN và profile liên quan | Principal và thuộc tính theo định dạng, chính sách SSH |
| Mục đích kiểm tra | Xác thực phía TLS, sau đó ứng dụng cấp quyền | Xác thực đăng nhập SSH và áp dụng hạn chế liên quan |
| Cơ chế thu hồi | Theo mô hình trạng thái X.509 được triển khai | Theo khả năng và cấu hình riêng của hệ thống SSH |
| Khả năng dùng lẫn nhau | Không tự dùng làm chứng thư SSH | Không tự được chấp nhận bởi bộ xác minh X.509 |

Vì vậy, không lấy một cấu hình CRL hoặc quy tắc SAN của X.509 rồi giả định áp dụng nguyên vẹn cho chứng thư SSH.

Trong PAM, có thể dùng chứng thư SSH ngắn hạn cho một yêu cầu đã được duyệt, nhưng cần quản lý riêng CA tin cậy, principal, thời hạn, hạn chế đăng nhập và thu hồi. Chứng thư đăng nhập vẫn không thay thế chính sách lệnh hoặc giới hạn quyền trên hệ điều hành.

## 11. Chính sách và logic kiểm tra minh họa

### 11.1. Mô hình chính sách

Cấu hình dưới đây chỉ diễn tả ý định, không phải cú pháp của một sản phẩm:

~~~yaml
certificate_authentication:
  use_case: "workload-to-pam-vault"
  certificate_family: "x509"
  trusted_domain: "production-workload-pki"

  validation:
    verify_certificate_path: true
    enforce_validity: true
    enforce_applicable_constraints: true
    require_client_auth_usage: true
    check_revocation_according_to_policy: true

  identity_mapping:
    source: "approved-certificate-profile"
    bind_issuer_scope_and_identity: true
    unknown_principal_action: "deny"
    certificate_text_does_not_assign_admin_role: true

  authorization:
    require_active_principal: true
    restrict_to_workload_environment: true
    issue_scoped_short_lived_lease: true

  sessions:
    enforce_application_lifetime: true
    handle_revocation_for_existing_sessions: true

  operations:
    monitor_expiry: true
    record_issuance_and_revocation: true
    protect_private_keys: true
~~~

Việc require_client_auth_usage được thực thi thế nào phụ thuộc bộ xác minh và profile. Không chỉ lưu một giá trị trong cấu hình mà bỏ qua kết quả kiểm tra ở tầng TLS.

### 11.2. Mã giả phía dịch vụ

~~~text
authenticate_and_authorize(connection, request):
    peer = get_verified_peer_from_trusted_transport(connection)
    require(peer.certificate_path_is_valid)
    require(peer.proof_of_private_key_possession_is_valid)
    require(peer.certificate_meets_profile_and_status_policy)

    identity = map_trusted_certificate_identity(peer)
    require(identity.exists)
    require(identity.active)

    require(request.scope_matches(identity.allowed_scope))
    require(required_approvals_are_current(request))
    require(access_window_is_open(request))
    require(current_context_is_acceptable(request))

    result = issue_bounded_access(identity, request)
    audit_without_private_keys_or_reusable_tokens(result)
    return result
~~~

Đoạn mã chỉ mô tả ranh giới trách nhiệm. Không nên triển khai các biến peer.* bằng thông tin tùy ý từ request hoặc một header chưa được bảo vệ.

Nếu TLS kết thúc ở proxy, dịch vụ phía sau không trực tiếp quan sát bằng chứng mTLS gốc. Nó phải tin proxy theo một cơ chế được bảo vệ và kiểm tra được, đồng thời giữ rõ mô hình danh tính qua từng hop.

## 12. Bằng chứng vận hành và xử lý sự cố

### 12.1. Ghi nhận vòng đời

Các sự kiện cần liên kết gồm:

| Giai đoạn | Dữ liệu hữu ích |
|---|---|
| Enrollment | Danh tính yêu cầu, bằng chứng và cơ sở được phát hành |
| Phát hành | Bên phát hành, serial, profile, định danh chủ thể, thời hạn |
| Sử dụng | Principal đã ánh xạ, dịch vụ nhận, kết quả và lý do |
| Cấp quyền | Yêu cầu, phê duyệt, entitlement, lease hoặc phiên liên quan |
| Gia hạn hoặc thay khóa | Quan hệ giữa credential cũ và mới, thời điểm chuyển đổi |
| Thu hồi | Nguyên nhân, thời điểm quyết định và kết quả phân phối trạng thái |
| Kết thúc | Trạng thái phiên và quyền thực tế sau khi thu hồi |

Serial và issuer giúp định danh chứng thư theo ngữ cảnh. Fingerprint có thể hỗ trợ đối chiếu một chứng thư cụ thể, nhưng cần thống nhất cách tính và không dùng nó như bằng chứng duy nhất về danh tính con người.

Không ghi private key hoặc token vào log. Việc lưu nguyên chứng thư cũng cần xem xét thông tin nhạy cảm và nhu cầu thực tế.

### 12.2. Phân biệt các lớp lỗi

Khi một kết nối bị từ chối, nên phân biệt:

- Không xây dựng được đường tin cậy.
- Sai mục đích hoặc profile.
- Chưa đến thời điểm hiệu lực hoặc đã hết hạn.
- Chứng thư bị thu hồi hoặc trạng thái không đáp ứng chính sách.
- Không hoàn thành bằng chứng sở hữu khóa.
- Không ánh xạ được principal.
- Principal hợp lệ nhưng không có quyền.
- Điều kiện phê duyệt hoặc cửa sổ không đạt.

Thông báo cho người dùng cần đủ để xử lý mà không tiết lộ dữ liệu quá mức. Log nội bộ có thể chi tiết hơn theo quyền truy cập phù hợp.

Không giải quyết lỗi bằng cách tắt kiểm tra chain, bỏ kiểm tra danh tính máy chủ hoặc cho mọi chứng thư ánh xạ vào một tài khoản admin.

### 12.3. Giám sát phát hành và hết hạn

Cần theo dõi các chứng thư sắp hết hạn, gia hạn thất bại, phát hành bất thường và thay đổi trust store.

Việc một ứng dụng chạy được hôm nay không chứng minh đường gia hạn còn hoạt động. Nên kiểm tra cả khả năng cấp mới, thay khóa và cập nhật tin cậy trước khi đến hạn.

Nếu CA hoặc khóa ký bị ảnh hưởng, đây là sự cố có thể tác động tới nhiều danh tính. Cần xác định phạm vi, ngăn phát hành trái phép, cập nhật tin cậy và phát hành lại theo kế hoạch. Chỉ thu hồi một chứng thư đầu cuối có thể không đủ.

## 13. Tình huống: workload nhận credential cơ sở dữ liệu qua vault

Một dịch vụ production cần credential ngắn hạn để thực hiện tác vụ đã được phép. Thay vì chứa một mật khẩu vault dùng chung trong cấu hình, dịch vụ xác thực bằng chứng thư thuộc trust domain workload production.

Luồng tham chiếu:

1. Workload được enrollment theo cơ chế xác minh danh tính triển khai.
2. Nó sử dụng khóa riêng được bảo vệ và nhận chứng thư theo profile.
3. Khi kết nối vault, workload xác minh danh tính máy chủ.
4. Vault kiểm tra chứng thư máy khách, bằng chứng sở hữu khóa và chính sách trạng thái.
5. Chứng thư được ánh xạ sang principal của đúng dịch vụ và môi trường.
6. Vault kiểm tra role và chỉ cấp credential cơ sở dữ liệu có phạm vi, thời hạn tương ứng.
7. Hoạt động cấp và kết thúc lease được ghi nhận.
8. Khi workload bị loại bỏ hoặc bị nghi xâm nhập, tổ chức chặn danh tính, ngăn cấp mới và xử lý credential, phiên liên quan.

Các điều kiện quan trọng:

- Chứng thư development không được ánh xạ sang role production.
- Không có quy tắc “bất kỳ chứng thư hợp lệ nào cũng nhận cùng một secret”.
- Không sao chép một private key vào mọi dịch vụ.
- Chứng thư hết hạn không tự được coi là đã thu hồi mọi credential từng nhận.
- Nếu credential cơ sở dữ liệu đã bị tiết lộ, cần xử lý tại nơi nó được chấp nhận.
- Nếu gia hạn chứng thư lỗi, dịch vụ phải có hành vi rõ ràng khi credential hiện tại hết hạn.

Ví dụ cho thấy certificate authentication là điểm đầu của một chuỗi kiểm soát. Quyền thực tế vẫn cần được cấp, giới hạn và thu hồi độc lập theo vòng đời của nó.

## 14. Kiểm chứng trước khi đưa vào sử dụng

Kiểm thử cần bao phủ cả giao thức, ánh xạ danh tính và thực thi quyền.

| Ca kiểm thử | Kết quả cần đạt |
|---|---|
| Chỉ có chứng thư, không sử dụng được khóa riêng | Không xác thực được |
| Chứng thư do CA không được chấp nhận phát hành | Bị từ chối |
| Chứng thư chưa có hiệu lực hoặc đã hết hạn | Bị từ chối theo chính sách |
| Chứng thư có mục đích hoặc profile không phù hợp | Không được dùng cho đường xác thực này |
| Subject giống người quản trị nhưng khác phạm vi tin cậy | Không được tự ánh xạ vào principal quản trị |
| Danh tính hợp lệ nhưng không có quyền tài nguyên | Bị từ chối ở tầng cấp quyền |
| Thiết bị có chứng thư nhưng người dùng chưa được xác thực theo yêu cầu | Không tự được coi là đủ MFA cho người dùng |
| Chứng thư bị thu hồi và trạng thái đã tới điểm thực thi | Kết nối mới bị chặn theo chính sách |
| Nguồn trạng thái thu hồi không khả dụng hoặc quá cũ | Hành vi đúng quy tắc đã định nghĩa, không tự coi là hợp lệ |
| Hết hạn hoặc thu hồi khi phiên đang mở | Phiên và quyền được xử lý theo cơ chế đã công bố |
| Chứng thư được dùng để lấy token hoặc lease | Có kiểm chứng vòng đời riêng của token hoặc lease |
| Header danh tính do client tự gửi | Không được backend tin như danh tính đã xác thực |
| Thay chứng thư hoặc CA | Có chuyển đổi đúng và loại bỏ tin cậy cũ theo kế hoạch |
| Khóa bị nghi lộ | Có thể chặn cấp mới và xử lý credential, phiên liên quan |
| Log sau các bài thử | Đủ đối chiếu và không chứa private key hoặc bí mật có thể dùng lại |

Xác thực bằng chứng thư có giá trị khi chuỗi tin cậy, bằng chứng sở hữu khóa, ánh xạ danh tính và vòng đời quyền được thiết kế cùng nhau. Một chứng thư hợp lệ chỉ là đầu vào cho PAM; hệ thống vẫn phải bảo đảm đúng chủ thể, đúng phạm vi, đúng thời gian và thu hồi được quyền thực tế.

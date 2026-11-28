# PAM vault

## Mục tiêu bài học

Trong chương **Kiến trúc PAM**, PAM vault là thành phần lưu giữ và kiểm soát việc sử dụng credential đặc quyền. Credential có thể là mật khẩu tài khoản quản trị, khóa truy cập hoặc dữ liệu xác thực của tài khoản dịch vụ. Đây là một phần của hệ thống **Privileged Access Management (PAM)** dùng để kiểm soát quyền truy cập đặc biệt vào tài khoản quản trị, dịch vụ và hạ tầng nhạy cảm.

Một vault có giá trị khi tổ chức biết credential thuộc về ai, được dùng ở đâu, ai có thể sử dụng, cách thay đổi và cách chứng minh những việc đã xảy ra. Lưu bí mật trong một kho được mã hóa mới giải quyết một phần của bài toán.

Sau bài học, bạn có thể:

- Giải thích vai trò và ranh giới trách nhiệm của PAM vault.
- Nhận diện các thành phần, luồng dữ liệu và ranh giới tin cậy quanh vault.
- Phân biệt truy xuất bí mật, checkout, cấp credential có thời hạn và kết nối qua broker.
- Thiết kế vòng đời nhập kho, sử dụng, luân chuyển, thu hồi và kết thúc quản lý credential.
- Phân tích lỗi đồng bộ với hệ thống đích, yêu cầu sẵn sàng và khôi phục.
- Xác định bằng chứng cần lưu để phục vụ kiểm toán và ứng phó sự cố.

## 1. PAM vault giải quyết vấn đề gì?

Giả sử một nhóm vận hành dùng chung mật khẩu quản trị cơ sở dữ liệu production. Mật khẩu được sao chép vào máy cá nhân, công cụ triển khai và tài liệu nội bộ. Khi một người chuyển công việc, tổ chức không biết còn những bản sao nào, ai đã đăng nhập hoặc việc đổi mật khẩu sẽ làm hỏng dịch vụ nào.

PAM vault đưa credential vào một vòng kiểm soát có chủ sở hữu và chính sách:

1. Xác định tài khoản, hệ thống đích và bên chịu trách nhiệm.
2. Lưu credential dưới cơ chế bảo vệ thích hợp.
3. Chỉ cho danh tính đủ điều kiện truy xuất hoặc sử dụng.
4. Gắn việc sử dụng với yêu cầu, phiên hoặc workload cụ thể.
5. Thay đổi credential theo chính sách và sự kiện rủi ro.
6. Theo dõi kết quả ở hệ thống đích và giữ bằng chứng.

**Đối tượng cần bảo vệ không chỉ là giá trị bí mật mà còn là khả năng sử dụng tài khoản đặc quyền.**

Một người không đọc được mật khẩu nhưng có thể yêu cầu broker thực thi lệnh quản trị tùy ý vẫn đang có đặc quyền đáng kể. Vì vậy, kiến trúc phải xem cả đường truy xuất bí mật và đường sử dụng bí mật thay mặt người yêu cầu.

### Kho bí mật chung và PAM vault

Kho bí mật dùng chung và PAM vault có thể có nhiều chức năng giao nhau. Khác biệt cần đánh giá nằm ở khả năng thực tế của giải pháp:

| Khả năng | Câu hỏi cần trả lời |
| --- | --- |
| Lưu giữ bí mật | Dữ liệu và bản sao lưu được bảo vệ thế nào? |
| Quản lý tài khoản đích | Có biết credential thuộc tài khoản và hệ thống nào không? |
| Kiểm soát sử dụng | Có hạn chế người yêu cầu, tài nguyên, mục đích và thời gian không? |
| Luân chuyển | Có đổi credential ở đích và kiểm tra kết quả không? |
| Điều phối phiên | Có thể kết nối mà không đưa credential cho người dùng không? |
| Truy vết | Có liên kết danh tính ban đầu với việc sử dụng ở đích không? |
| Khôi phục | Có xử lý được khi kho và hệ thống đích không còn đồng bộ không? |

Không nên suy ra mọi chức năng từ tên sản phẩm. Session broker, bộ luân chuyển hay hệ thống phê duyệt có thể là thành phần riêng được tích hợp với vault.

## 2. Vault quản lý những đối tượng nào?

Một bản ghi quản lý credential thường cần nhiều hơn tên và mật khẩu.

| Nhóm thông tin | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tài khoản đích | Tài khoản quản trị cơ sở dữ liệu A | Xác định principal thực sự có quyền |
| Đích sử dụng | Cụm dữ liệu production A | Tránh dùng credential sai tài nguyên |
| Bí mật hoặc tham chiếu | Mật khẩu được bảo vệ, tham chiếu khóa | Cung cấp khả năng xác thực cần thiết |
| Chủ sở hữu | Nhóm vận hành dữ liệu | Chịu trách nhiệm về nhu cầu và thay đổi |
| Chính sách truy cập | Nhóm được yêu cầu, điều kiện phê duyệt | Kiểm soát ai được sử dụng |
| Vòng đời | Phiên bản, lần đổi gần nhất, trạng thái xác minh | Theo dõi credential đang có hiệu lực |
| Phụ thuộc | Job, ứng dụng hoặc broker sử dụng | Đánh giá ảnh hưởng của rotation |
| Bằng chứng | Mã yêu cầu, sự kiện, kết quả ở đích | Phục vụ kiểm tra và điều tra |

Metadata cũng có thể nhạy cảm. Danh sách tài khoản quản trị, địa chỉ đích và quan hệ giữa các hệ thống giúp người tấn công hiểu cấu trúc hạ tầng dù chưa đọc được bí mật.

Không phải mọi vật liệu xác thực đều cần được lưu dưới dạng có thể xuất ra. Với thiết kế phù hợp, khóa riêng có thể nằm trong thành phần bảo vệ khóa và chỉ cho phép thao tác ký. Vault khi đó quản lý chính sách, tham chiếu hoặc vòng đời tương ứng, tùy khả năng nền tảng.

## 3. Bức tranh kiến trúc

Một mô hình khái niệm có thể gồm các thành phần sau:

~~~mermaid
flowchart TD
    Human[Người vận hành] --> Access[Cổng truy cập PAM]
    Workload[Ứng dụng hoặc pipeline] --> API[API truy cập bí mật]
    IdP[Nguồn danh tính] --> Access
    Identity[Nguồn xác nhận workload] --> API
    Access --> Policy[Chính sách và phê duyệt]
    API --> Policy
    Policy --> Vault[PAM vault]
    Keys[Thành phần quản lý khóa] --- Vault
    Vault --> Broker[Session broker]
    Vault --> Rotation[Bộ điều phối rotation]
    Broker --> Target[Hệ thống đích]
    Rotation --> Target
    Vault --> Audit[Nơi nhận audit được bảo vệ]
    Broker --> Audit
    Rotation --> Audit
~~~

Sơ đồ thể hiện trách nhiệm logic, không bắt buộc mỗi khối là một máy chủ hay một sản phẩm riêng.

### 3.1. Cổng truy cập và API

Đây là điểm tiếp nhận yêu cầu từ người dùng hoặc workload. Chúng cần xác thực danh tính, kiểm tra yêu cầu, giới hạn phạm vi và tạo dấu vết.

Truy cập của người và máy có cách xác thực khác nhau. Người vận hành có thể cần xác thực đa yếu tố và điều kiện thiết bị. Workload cần danh tính được gắn với môi trường chạy và nhiệm vụ, thay vì dùng chung tài khoản của một nhân viên.

### 3.2. Bộ chính sách và phê duyệt

Thành phần này quyết định yêu cầu nào được chấp nhận dựa trên danh tính, tài nguyên, hành động, thời gian và các điều kiện khác.

Phê duyệt là một điều kiện của quyết định truy cập. Nó không thay thế việc kiểm tra quyền của người yêu cầu hoặc bảo vệ credential sau khi cấp.

### 3.3. Lõi lưu giữ bí mật

Lõi vault bảo vệ dữ liệu credential và quản lý phiên bản, quyền truy cập, trạng thái cùng các thao tác cần thiết. Quyền quản trị kho phải được xem xét riêng với quyền đọc hoặc sử dụng từng bí mật.

### 3.4. Connector và bộ luân chuyển

Connector thực hiện thao tác với hệ thống đích: kiểm tra tài khoản, đổi mật khẩu hoặc xác minh credential mới. Vì có thể tiếp cận tài khoản mạnh ở đích, connector là thành phần nhạy cảm, cần quyền tối thiểu và phạm vi mạng phù hợp.

### 3.5. Session broker

Broker dùng credential để thiết lập phiên thay mặt người đã được cho phép. Tùy giải pháp, nó có thể hỗ trợ ghi nhận phiên, giới hạn kết nối hoặc các thao tác cụ thể.

Cần kiểm tra khả năng của broker trên từng giao thức. Không mặc định rằng mọi phiên đều được ghi đầy đủ hoặc mọi lệnh đều được kiểm soát chi tiết.

### 3.6. Quản lý khóa và nơi nhận audit

Khóa bảo vệ kho và bằng chứng hoạt động có vòng đời riêng. Nếu người kiểm soát vault cũng dễ dàng lấy toàn bộ khóa và xóa mọi dấu vết, việc phân tách trên sơ đồ chưa tạo được ranh giới bảo vệ hữu ích.

## 4. Phân biệt các mặt phẳng trách nhiệm

Có thể tách kiến trúc thành ba nhóm để phân tích:

| Nhóm | Chức năng | Rủi ro cần xem xét |
| --- | --- | --- |
| Điều khiển | Sửa chính sách, thêm tài khoản, duyệt yêu cầu, cấu hình connector | Người có thể tự cấp quyền hoặc đổi đích truy cập |
| Sử dụng credential | Trả bí mật, cấp credential, thiết lập phiên, đổi mật khẩu | Đọc trộm bí mật hoặc sử dụng ngoài phạm vi |
| Bằng chứng | Ghi nhận yêu cầu, thay đổi, kết quả và phiên | Xóa dấu vết hoặc lộ dữ liệu nhạy cảm |

Đây là cách phân tích trách nhiệm, không có nghĩa ba nhóm luôn được triển khai tách biệt về vật lý.

Một số quyền gián tiếp cũng cần được xem là đặc quyền:

- Sửa chính sách để tự cho mình quyền đọc.
- Đổi connector sang một địa chỉ do mình kiểm soát.
- Thay mã hoặc cấu hình của bộ rotation.
- Khôi phục bản sao lưu vào môi trường có thể truy xuất dữ liệu.
- Sửa broker để thu thập credential trong lúc sử dụng.
- Tắt nguồn audit trước khi thực hiện thao tác.

Least privilege phải bao phủ những khả năng này, thay vì chỉ giới hạn nút “xem mật khẩu”.

## 5. Bảo vệ bí mật và khóa mã hóa

### 5.1. Mã hóa dữ liệu và bảo vệ khóa

Vault cần bảo vệ dữ liệu khi lưu trữ và trên các đường truyền liên quan. Tuy nhiên, mã hóa không tự bảo vệ được khi một thành phần đã được phép giải mã bị kiểm soát.

Một mô hình mã hóa phong bì thường được dùng để giải thích sự phân tách khóa:

~~~text
Credential
    |
    | mã hóa bằng khóa dữ liệu
    v
Dữ liệu đã mã hóa

Khóa dữ liệu
    |
    | được bảo vệ bằng khóa bao bọc
    v
Khóa dữ liệu đã được bảo vệ
~~~

Cách tổ chức khóa cụ thể phụ thuộc giải pháp. KMS hoặc HSM có thể hỗ trợ bảo vệ khóa và hạn chế xuất khóa, nhưng phải kiểm tra hệ thống thực sự sử dụng chúng như thế nào.

Các câu hỏi kiến trúc quan trọng:

- Thành phần nào có quyền yêu cầu giải mã?
- Ai có thể sửa chính sách của thành phần quản lý khóa?
- Khi nguồn khóa không sẵn sàng, chức năng nào còn hoạt động?
- Bản sao lưu cần những khóa và trạng thái nào để khôi phục?
- Khóa cũ được xử lý thế nào khi dữ liệu hoặc backup còn phụ thuộc vào nó?

**Luân chuyển khóa mã hóa của kho và luân chuyển mật khẩu ở hệ thống đích là hai việc khác nhau.** Đổi khóa bảo vệ dữ liệu không làm mất hiệu lực một mật khẩu đã bị sao chép ra ngoài.

### 5.2. Bí mật vẫn có thể xuất hiện khi sử dụng

Credential có thể xuất hiện trong bộ nhớ, biến môi trường, tệp tạm, tham số tiến trình hoặc log nếu cách tích hợp không phù hợp. Kiến trúc cần giảm phạm vi và thời gian tồn tại của bản rõ, đồng thời kiểm soát những nơi có thể tạo bản sao.

Không ghi giá trị mật khẩu, token, khóa riêng hoặc nội dung phản hồi chứa bí mật vào audit để “dễ điều tra”. Hãy ghi định danh tham chiếu, phiên bản và kết quả thao tác.

Nếu bí mật được gửi xuống máy người dùng, không thể coi vault là nơi duy nhất còn giữ bí mật đó.

## 6. Các cách sử dụng credential

### 6.1. Đọc trực tiếp

Người dùng hoặc ứng dụng nhận giá trị credential rồi tự kết nối đến đích.

Cách này có thể cần cho một số hệ thống, nhưng tạo thêm bản sao bên ngoài vault. Cần xác định ai nhận, nhận phiên bản nào, được dùng ở đâu và khi nào credential thực sự mất hiệu lực.

Quyền đọc nên là quyền riêng. Người được phép khởi tạo một phiên không nhất thiết cần được xem mật khẩu.

### 6.2. Checkout có kiểm soát

Checkout ghi nhận việc một người nhận hoặc sử dụng credential trong một khoảng thời gian. Một số triển khai có thể giới hạn người dùng đồng thời hoặc đổi mật khẩu khi kết thúc.

Cần phân biệt:

- Hết thời gian checkout trong PAM.
- Credential ở hệ thống đích đã bị thay đổi hoặc thu hồi.
- Phiên được mở bằng credential đó đã kết thúc.

Ba sự kiện này không tự động xảy ra cùng lúc. Việc người dùng chọn “trả lại” không làm cho bản sao họ đã biết trở nên vô dụng nếu đích vẫn chấp nhận credential cũ.

### 6.3. Credential theo yêu cầu và có thời hạn

Nếu nền tảng hỗ trợ, hệ thống có thể tạo tài khoản hoặc credential riêng cho một yêu cầu rồi thu hồi theo vòng đời xác định.

Cần kiểm tra thời hạn được thực thi ở đâu. Một bản ghi lease hết hạn trong vault chưa đủ chứng minh quyền ở đích đã hết, nhất là khi thao tác thu hồi thất bại hoặc phiên đã được thiết lập trước đó vẫn tồn tại.

### 6.4. Kết nối qua broker

Người dùng yêu cầu một phiên; broker lấy credential và kết nối đến hệ thống đích mà không chủ động hiển thị bí mật cho người dùng.

Lợi ích là giảm nhu cầu phân phối credential cho máy trạm. Tuy nhiên:

- Broker trở thành điểm cần bảo vệ nghiêm ngặt.
- Phiên vẫn cần giới hạn theo nhiệm vụ và tài nguyên.
- Người có khả năng quản trị trong phiên có thể tạo đường truy cập mới.
- Credential có thể bị lộ qua giao thức, ứng dụng hoặc cấu hình không phù hợp.

Không nên đồng nhất “không hiển thị mật khẩu” với “không thể lạm dụng quyền”.

## 7. Ví dụ luồng truy cập của một người vận hành

Một kỹ sư cần kiểm tra lỗi trên cơ sở dữ liệu production A.

~~~mermaid
sequenceDiagram
    participant U as Kỹ sư
    participant P as Cổng PAM
    participant V as Vault
    participant B as Broker
    participant D as Cơ sở dữ liệu A
    participant A as Audit
    U->>P: Yêu cầu truy cập theo nhiệm vụ
    P->>P: Xác thực và đánh giá chính sách
    P->>A: Ghi yêu cầu và quyết định
    P->>B: Cho phép mở phiên đúng phạm vi
    B->>V: Yêu cầu credential cho đích A
    V->>V: Kiểm tra quyền của broker và ngữ cảnh
    V-->>B: Cung cấp credential theo cơ chế bảo vệ
    B->>D: Thiết lập phiên
    B->>A: Ghi liên kết người, yêu cầu và phiên
    D-->>B: Kết quả kết nối
    B-->>U: Kênh làm việc được cho phép
~~~

Luồng này cần duy trì liên kết giữa danh tính của kỹ sư và tài khoản đích. Nếu cơ sở dữ liệu chỉ nhìn thấy một tài khoản dùng chung, PAM phải có bằng chứng tương ứng để phân biệt các phiên.

Ngay cả khi dùng broker, tài khoản cơ sở dữ liệu vẫn cần quyền phù hợp. Dùng tài khoản quản trị toàn quyền cho mọi nhiệm vụ chỉ làm credential tập trung hơn, chưa thực hiện least privilege tại đích.

Khi kết thúc nhiệm vụ, cần xác định trách nhiệm đóng phiên, thu hồi quyền tạm thời và xử lý credential theo chính sách. Không giả định việc đóng giao diện người dùng đã kết thúc mọi kết nối.

## 8. Quyền truy cập và phân tách trách nhiệm

Một ma trận khái niệm giúp làm rõ quyền cần thiết:

| Vai trò | Khả năng thường cần | Khả năng cần tách hoặc kiểm soát riêng |
| --- | --- | --- |
| Người yêu cầu phiên | Yêu cầu truy cập đúng tài khoản và đích | Xem bí mật, sửa chính sách, đổi connector |
| Người phê duyệt | Xem ngữ cảnh và quyết định theo thẩm quyền | Tự duyệt yêu cầu của mình nếu chính sách không cho phép |
| Chủ sở hữu tài khoản | Xác nhận nhu cầu, phụ thuộc và lịch đổi | Đọc mọi bí mật trong vault |
| Broker | Lấy hoặc sử dụng credential cho phiên được phép | Duyệt kho hoặc truy cập mọi tài khoản |
| Bộ rotation | Đổi và xác minh credential trong phạm vi quản lý | Mở phiên tương tác ngoài nhiệm vụ |
| Người kiểm toán | Xem bằng chứng cần thiết | Đọc giá trị credential hoặc sửa sự kiện |
| Quản trị nền tảng | Vận hành thành phần được giao | Tự nâng thành người dùng mọi tài khoản đích |

Ma trận này là điểm bắt đầu để thiết kế, không phải cam kết rằng mọi sản phẩm hỗ trợ đúng các vai trò đó.

Tách trách nhiệm phải tính cả quyền trên hệ điều hành, cơ sở dữ liệu lưu trữ, nền tảng triển khai, backup và hệ thống khóa. Một quản trị viên hạ tầng có thể có đường gián tiếp đến dữ liệu hoặc tiến trình giải mã.

Với credential có ảnh hưởng lớn, có thể cần cơ chế kiểm soát độc lập cho thay đổi chính sách và truy cập khẩn cấp. Cách triển khai phải gắn với nhu cầu vận hành thực tế.

## 9. Vòng đời của một credential được quản lý

### 9.1. Kiểm kê và tiếp nhận

Trước khi nhập một tài khoản vào vault, cần xác định:

- Tài khoản có còn cần thiết không và đang có quyền gì?
- Ai là chủ sở hữu và ai sử dụng?
- Credential đang được lưu hoặc phân phối ở đâu?
- Những ứng dụng, job và quy trình nào phụ thuộc?
- Hệ thống đích cho phép đổi và kiểm tra credential bằng cách nào?
- Có quy trình khẩn cấp hoặc phục hồi nào liên quan?

Đưa một mật khẩu đã dùng rộng rãi vào vault không làm mất những bản sao cũ. Kế hoạch tiếp nhận cần xử lý việc chuyển người dùng và ứng dụng sang đường mới, rồi đổi hoặc thu hồi credential cũ khi đã kiểm soát phụ thuộc.

### 9.2. Lưu giữ và gán chính sách

Bản ghi cần có chủ sở hữu, phạm vi, cách sử dụng được phép, cơ chế xác minh và yêu cầu rotation. Không nên mặc định mọi tài khoản trong cùng thư mục có cùng mức nhạy cảm.

### 9.3. Sử dụng

Mỗi đường sử dụng cần có kiểm tra quyền, ngữ cảnh thích hợp và dấu vết. Cần hạn chế việc truy xuất lại toàn bộ kho chỉ để thực hiện một tác vụ hẹp.

### 9.4. Luân chuyển và xác minh

Rotation cần cập nhật credential ở đích, bảo vệ giá trị mới, kiểm tra trạng thái và xử lý bên phụ thuộc. Một thao tác trả về thành công ở vault chưa chứng minh dịch vụ đã chuyển sang dùng phiên bản mới.

### 9.5. Thu hồi và kết thúc quản lý

Khi tài khoản không còn cần thiết, cần xử lý ở hệ thống đích, các đường truy cập, phiên đang tồn tại và credential liên quan.

**Xóa bản ghi trong vault không đồng nghĩa xóa tài khoản hoặc thu hồi quyền ở đích.** Ngược lại, xóa bản ghi quá sớm có thể làm mất thông tin cần cho việc thu hồi và điều tra.

Bằng chứng cần được giữ theo chính sách áp dụng ngay cả khi credential đã được loại bỏ.

## 10. Rotation là bài toán đồng bộ với hệ thống đích

Vault và hệ thống đích thường không nằm trong cùng một giao dịch nguyên tử. Có thể đổi mật khẩu thành công ở đích nhưng mất kết nối trước khi vault ghi nhận kết quả.

Vì vậy, không nên thiết kế trạng thái chỉ gồm “thành công” hoặc “thất bại”.

Một mô hình trạng thái minh họa:

~~~text
Đã xác minh phiên bản hiện tại
              |
              v
Đang chuẩn bị thay đổi
              |
              v
Đang áp dụng ở hệ thống đích
              |
              +--> Kết quả chưa xác định --> Đối soát có kiểm soát
              |
              v
Đang kiểm tra credential mới và phụ thuộc
              |
              v
Đã xác minh phiên bản mới
~~~

Giá trị mới cần được bảo vệ trong quá trình điều phối. Việc giữ credential cũ hoặc mới để đối soát phải có quyền truy cập và thời hạn rõ ràng, không tạo kho bản sao không được quản lý.

| Tình huống | Nguy cơ | Hướng xử lý kiến trúc |
| --- | --- | --- |
| Đích đổi thành công, vault chưa ghi nhận | Kho có thể giữ giá trị cũ | Lưu trạng thái thao tác, xác minh và đối soát |
| Vault có giá trị mới, đích chưa đổi | Người dùng nhận credential không dùng được | Không công bố trạng thái đã xác minh quá sớm |
| Ứng dụng chưa cập nhật | Lỗi kết nối hoặc gián đoạn dịch vụ | Có quy trình chuyển đổi và kiểm tra phụ thuộc |
| Hai bộ rotation cùng đổi một tài khoản | Giá trị cuối không khớp trạng thái dự kiến | Điều phối độc quyền theo tài khoản và kiểm soát retry |
| Hệ thống đích khóa tài khoản sau nhiều lần thử | Mất truy cập và phát sinh sự cố | Giới hạn retry, phân loại lỗi và dừng đúng điều kiện |
| Rotation xong nhưng phiên cũ còn sống | Đặc quyền cũ có thể tiếp tục được dùng | Xử lý vòng đời phiên theo cơ chế của đích |

### Retry cần biết trạng thái

Thử lại thao tác đổi mật khẩu một cách mù quáng có thể làm trạng thái lệch thêm. Bộ điều phối cần nhận diện thao tác đang diễn ra, kết quả chưa rõ và trường hợp cần can thiệp.

Một thiết kế có thể dùng mã thao tác, phiên bản và cơ chế khóa phù hợp để tránh hai bên đồng thời ghi credential khác nhau. Cơ chế cụ thể phụ thuộc hệ thống; điều quan trọng là không để retry tạo thay đổi ngoài ý định.

### Khôi phục không nên làm sống lại credential đã bị lộ

Nếu rotation diễn ra do nghi ngờ credential bị lộ, phương án khôi phục phải xét nguy cơ tiếp tục dùng bí mật cũ. Không tự động đưa credential bị nghi lộ trở lại chỉ để làm cho một kiểm tra kết nối thành công.

Việc đối soát hoặc reset bằng tài khoản mạnh hơn cũng là thao tác đặc quyền và phải được kiểm soát, ghi nhận.

## 11. Tài khoản dịch vụ và bài toán phụ thuộc

Tài khoản dịch vụ thường không có người ngồi chờ nhập mật khẩu mới. Một credential có thể được dùng bởi nhiều tiến trình với chu kỳ chạy khác nhau.

Cần làm rõ:

- Ứng dụng lấy bí mật lúc khởi động hay trong quá trình chạy?
- Có giữ kết nối hoặc cache credential lâu dài không?
- Có hỗ trợ nạp lại mà không khởi động lại không?
- Có cho phép giai đoạn chuyển tiếp nhiều credential không?
- Ai chịu trách nhiệm xác nhận từng bên phụ thuộc đã chuyển đổi?
- Lần chạy hiếm hoặc theo lịch dài sẽ được kiểm tra thế nào?

Nếu hệ thống đích chỉ hỗ trợ một mật khẩu hiện hành, cần một quy trình chuyển đổi phù hợp với giới hạn đó. Không mặc định có thể luôn giữ cả phiên bản cũ và mới cùng hợp lệ.

### Xác thực workload với vault

Ứng dụng cũng cần xác thực trước khi lấy bí mật. Nếu đặt một token quản trị vault dài hạn ngay trong mã nguồn, tổ chức chỉ chuyển vị trí của bí mật gốc.

Khi nền tảng hỗ trợ, có thể dùng danh tính workload gắn với môi trường và nhiệm vụ, xác nhận có thời hạn ngắn và quyền hẹp. Vẫn cần kiểm tra quan hệ tin cậy: workload nào có thể nhận danh tính đó và ai có thể sửa workload.

Trong hệ thống buộc phải dùng credential khởi tạo, cần quản lý phân phối, quyền truy cập và vòng đời của credential này như một bí mật đặc quyền.

## 12. Vault, least privilege, JIT và JEA

Các cơ chế này giải quyết những phần khác nhau:

| Cơ chế | Phần được kiểm soát |
| --- | --- |
| Vault | Lưu giữ, phân phối, sử dụng và vòng đời credential |
| Least privilege | Hành động, tài nguyên và điều kiện mà principal thực sự được phép |
| JIT | Khi nào và trong bao lâu quyền hoặc khả năng nhận quyền có hiệu lực |
| JEA | Những thao tác cần thiết được cho phép trong một phạm vi nhiệm vụ |

Ví dụ, vault giữ mật khẩu của tài khoản có toàn quyền quản trị production. Chỉ cho phép lấy mật khẩu trong một giờ là giới hạn đường lấy bí mật theo thời gian; chưa đủ chứng minh toàn bộ quyền quản trị sẽ hết sau một giờ.

Để đạt mục tiêu cần đánh giá thêm:

- Tài khoản đích có quyền gì?
- Người dùng có tạo credential hoặc principal khác trong lúc được truy cập không?
- Credential được thu hồi hoặc đổi ở đích bằng cách nào?
- Phiên đã mở có bị giới hạn tương ứng không?
- Có thể dùng một tài khoản hoặc công cụ tác vụ hẹp hơn không?

Vault hỗ trợ thực hiện least privilege nhưng không tự thay thế thiết kế phân quyền của hệ thống đích.

## 13. Tính sẵn sàng và hành vi khi có lỗi

Vault là nơi tập trung các khả năng quan trọng. Một thiết kế an toàn nhưng không có phương án vận hành khi mất kết nối có thể khiến người dùng quay lại lưu mật khẩu ở nơi không được kiểm soát.

### 13.1. Xác định chức năng bị ảnh hưởng

Không nên chỉ hỏi “vault có hoạt động không”. Cần xét riêng:

- Có tiếp nhận yêu cầu mới không?
- Có lấy được bí mật không?
- Có mở được phiên mới không?
- Phiên đang chạy có tiếp tục được không?
- Có rotation hoặc thu hồi được không?
- Có ghi được bằng chứng không?
- Có khôi phục được truy cập quản trị vào chính hạ tầng PAM không?

Mỗi chức năng có phụ thuộc riêng vào nguồn danh tính, mạng, khóa, kho dữ liệu, broker, connector và nơi nhận audit.

### 13.2. Nhân bản và nhất quán

Nhân bản dữ liệu không tự bảo đảm mọi node có thể đồng thời thay credential an toàn. Thiết kế cần tránh hai bên cùng điều phối một thay đổi với trạng thái không thống nhất.

Tùy giải pháp, việc này có thể dựa vào cơ chế đồng thuận, vai trò điều phối, khóa hoặc cơ chế tương đương. Cần kiểm tra hành vi thực tế khi mất kết nối giữa các node, chuyển vai trò hoặc retry.

### 13.3. Cache tạo thêm ranh giới bảo vệ

Cache có thể hỗ trợ một số yêu cầu vận hành nhưng đồng thời tạo thêm nơi giữ bí mật. Cần quy định:

- Bí mật nào được cache và ở thành phần nào?
- Được bảo vệ và tồn tại bao lâu?
- Credential đã đổi hoặc bị thu hồi được xử lý thế nào?
- Có dấu vết khi dùng chế độ suy giảm không?
- Sau khi kết nối phục hồi, trạng thái được đối soát ra sao?

Không thể dùng cache vô thời hạn rồi vẫn giả định việc thu hồi ở vault có hiệu lực ngay tại mọi nơi.

### 13.4. Khi audit không sẵn sàng

Cần quyết định rõ thao tác nào phải dừng, thao tác nào được phép tiếp tục có điều kiện và bằng chứng được giữ ở đâu.

Nếu cho phép tiếp tục một số hoạt động quan trọng, phải có cơ chế bảo vệ bản ghi tạm, cảnh báo, đồng bộ lại và đánh dấu khoảng trống. Không nên mặc định im lặng bỏ qua log hoặc tuyên bố mọi trường hợp đều phải dừng mà chưa xét yêu cầu phục hồi.

## 14. Backup, khôi phục và truy cập khẩn cấp

### 14.1. Backup phải khôi phục được khả năng sử dụng

Một bản sao dữ liệu không đủ nếu thiếu khóa giải mã, cấu hình chính sách, quan hệ tin cậy hoặc trạng thái vận hành cần thiết.

Cần xác định:

- **RPO:** mức mất dữ liệu có thể chấp nhận, xét cả thay đổi credential và chính sách.
- **RTO:** khoảng thời gian mục tiêu để khôi phục chức năng cần thiết.
- Thành phần và khóa cần có để giải mã dữ liệu.
- Người được phép khôi phục và môi trường được phép nhận bản sao.
- Cách bảo vệ backup khỏi đọc, sửa hoặc xóa trái phép.
- Cách kiểm tra bí mật khôi phục có còn khớp với hệ thống đích.

Một backup cũ có thể chứa mật khẩu đã hết hiệu lực. Sau phục hồi, không được coi mọi bản ghi là đã xác minh chỉ vì dữ liệu giải mã được.

### 14.2. Tránh phụ thuộc vòng

Ví dụ: credential quản trị nền tảng chạy vault chỉ nằm trong vault; trong khi muốn khởi động lại vault phải quản trị chính nền tảng đó. Khi mất dịch vụ, cả hai đường đều không sử dụng được.

Cần lập bản đồ phụ thuộc và chuẩn bị đường khẩn cấp phù hợp. Đường đó phải được bảo vệ, giới hạn người sử dụng, có trách nhiệm rõ ràng và được kiểm tra định kỳ.

Nếu đường khẩn cấp vẫn cần cùng nguồn danh tính hoặc thành phần đang giả định bị mất, nó chưa giải quyết được kịch bản tương ứng.

### 14.3. Break-glass là quy trình có vòng đời

Quy trình truy cập khẩn cấp cần xác định:

1. Điều kiện kích hoạt và người chịu trách nhiệm.
2. Cách xác nhận người sử dụng khi một số phụ thuộc không hoạt động.
3. Phạm vi quyền và cách lấy vật liệu truy cập.
4. Cách ghi nhận hành động trong điều kiện suy giảm.
5. Việc rà soát, thu hồi hoặc luân chuyển sau sử dụng.
6. Cách đưa hệ thống về trạng thái quản lý bình thường.

Không công bố credential khẩn cấp trong runbook. Tài liệu nên chỉ rõ quy trình và vị trí tham chiếu được bảo vệ.

## 15. Audit và bằng chứng ứng phó sự cố

Một sự kiện sử dụng credential nên liên kết được các đối tượng sau khi phù hợp:

~~~text
Danh tính ban đầu
      |
      v
Yêu cầu và quyết định truy cập
      |
      v
Bản ghi credential / phiên bản
      |
      v
Broker hoặc bên nhận credential
      |
      v
Tài khoản đích và phiên / hành động ở đích
~~~

Các nhóm sự kiện cần xem xét:

| Nhóm | Ví dụ bằng chứng |
| --- | --- |
| Xác thực | Danh tính, phương thức, kết quả, nguồn yêu cầu |
| Chính sách | Chính sách áp dụng, kết quả đánh giá, người phê duyệt |
| Truy xuất hoặc sử dụng | Định danh credential, bên nhận, mục đích, kết quả |
| Thay đổi quản trị | Ai sửa quyền, connector, đích hoặc cấu hình |
| Rotation | Mã thao tác, trạng thái, kết quả xác minh, lỗi |
| Phiên | Danh tính ban đầu, tài khoản đích, thời điểm và mã phiên |
| Khôi phục | Người thực hiện, dữ liệu sử dụng, kết quả đối soát |

Bản ghi cần được bảo vệ và có thời gian đủ nhất quán để đối chiếu. Mã liên kết yêu cầu và phiên giúp tránh chỉ dựa vào thời gian gần nhau khi quy kết hành động.

Ghi hình hoặc ghi nội dung phiên có thể chứa dữ liệu nhạy cảm. Cần kiểm soát người xem, việc xuất dữ liệu và vòng đời lưu giữ theo chính sách áp dụng.

Trong ứng phó sự cố, cần xác định credential nào đã bị truy xuất, danh tính nào sử dụng và những phiên nào còn tồn tại. Chặn quyền đọc vault mới chỉ cắt một đường; vẫn phải xét credential đã sao chép, phiên đang chạy và quyền phát sinh ở đích.

Không đặt một thời hạn lưu bằng chứng cố định cho mọi tổ chức trong thiết kế khái quát. Thời hạn phải đáp ứng yêu cầu vận hành, điều tra và các yêu cầu thực tế áp dụng.

## 16. Ví dụ thiết kế cho một dịch vụ production

Một ứng dụng A dùng tài khoản cơ sở dữ liệu riêng. Nhóm vận hành có nhu cầu bảo trì hiếm gặp. Thiết kế ban đầu dùng cùng mật khẩu quản trị cho ứng dụng và người vận hành.

### 16.1. Phân tách mục đích

Thiết kế đề xuất:

- Tài khoản ứng dụng chỉ có quyền phục vụ chức năng của A.
- Tài khoản bảo trì có phạm vi phù hợp với nhiệm vụ được chấp nhận.
- Workload A lấy credential qua danh tính riêng, chỉ được truy cập bản ghi của A.
- Người vận hành yêu cầu phiên qua PAM; quyền xem bí mật không được mặc định cấp kèm.
- Bộ rotation chỉ được quản lý những tài khoản đã chỉ định.
- Audit liên kết được yêu cầu, credential và phiên hoặc workload sử dụng.

Nếu hệ thống hỗ trợ credential theo nhiệm vụ, có thể đánh giá phương án đó. Nếu chỉ hỗ trợ mật khẩu tĩnh, phải thiết kế chuyển đổi và luân chuyển theo giới hạn thực tế.

### 16.2. Hồ sơ chính sách minh họa

Đây là **mô tả thiết kế, không phải cấu hình có thể áp dụng trực tiếp cho một sản phẩm**. Hồ sơ không chứa giá trị bí mật.

~~~yaml
managed_account:
  reference: production-app-a-database
  owner: application-a-operations
  target: database-a
  purpose: application-runtime

access:
  requester: application-a-workload
  allowed_use: retrieve-own-database-credential
  scope: one-managed-account
  human_secret_read: not-granted-by-this-policy

rotation:
  method: supported-target-connector
  dependencies:
    - application-a-runtime
  success_requires:
    - target-credential-verified
    - application-connectivity-verified
  uncertain_result: stop-and-reconcile

evidence:
  correlate:
    - requester
    - request-id
    - credential-version
    - rotation-operation-id
  record_secret_value: false
~~~

Thông tin “không cấp” trong hồ sơ này chỉ mô tả ý định của chính sách. Vẫn phải kiểm tra các chính sách khác và quyền hiệu lực để bảo đảm không có đường truy cập bổ sung.

### 16.3. Tiêu chí xác nhận

Thiết kế cần chứng minh:

- Workload A truy xuất được credential đúng của mình.
- Workload khác không nhận được credential của A qua các đường trong phạm vi kiểm tra.
- Ứng dụng vẫn thực hiện được các chức năng hợp lệ sau rotation.
- Credential cũ được xử lý theo cơ chế đích và kế hoạch chuyển đổi.
- Người vận hành có thể làm nhiệm vụ được phép và có bằng chứng truy vết.
- Lỗi đổi mật khẩu không làm hệ thống âm thầm công bố một trạng thái sai.
- Khôi phục từ backup có bước xác minh và đối soát với đích.

Việc xác nhận nên dùng môi trường hoặc cách đánh giá phù hợp để tránh thử thao tác có tác động không cần thiết trên production.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao có vấn đề | Hướng sửa |
| --- | --- | --- |
| Đưa mọi mật khẩu vào vault rồi giữ nguyên quyền rộng | Bí mật tập trung nhưng đặc quyền vẫn vượt nhu cầu | Review quyền ở đích và tách mục đích sử dụng |
| Cấp token vault quản trị cho pipeline | Một workload có thể ảnh hưởng toàn bộ kho | Dùng danh tính và chính sách hẹp cho workload |
| Dùng cùng một tài khoản cho ứng dụng và người vận hành | Rotation, truy vết và thu hồi bị trộn lẫn | Tách principal theo nhiệm vụ |
| Xem checkout hết hạn là mật khẩu đã hết hiệu lực | Bản sao có thể vẫn dùng được ở đích | Gắn với cơ chế thu hồi hoặc thay đổi thực tế |
| Rotation không biết bên phụ thuộc | Có thể gây gián đoạn ngoài dự kiến | Kiểm kê, kiểm tra và điều phối chuyển đổi |
| Retry đổi mật khẩu liên tục khi mất kết nối | Có thể làm lệch trạng thái hoặc khóa tài khoản | Nhận diện kết quả chưa rõ và đối soát |
| Backup không kèm phương án quản lý khóa | Có dữ liệu nhưng không khôi phục được | Kiểm tra khôi phục toàn bộ phụ thuộc cần thiết |
| Đường khẩn cấp phụ thuộc đúng dịch vụ đang hỏng | Không dùng được khi cần | Thiết kế theo từng kịch bản mất phụ thuộc |
| Cho rằng broker giải quyết mọi lạm dụng | Người dùng vẫn có thể thực hiện hành động mạnh | Kiểm soát quyền tại đích, phiên và tác vụ |
| Ghi bí mật vào log để hỗ trợ điều tra | Tạo đường lộ credential mới | Dùng tham chiếu và bằng chứng không chứa bí mật |

## 18. Bài tập tự đánh giá

Một nhóm đã đưa mật khẩu quản trị cơ sở dữ liệu vào vault và chỉ cho phép checkout trong một khoảng thời gian. Ứng dụng vẫn dùng chính tài khoản đó. Mật khẩu được đổi theo lịch nhưng chưa có danh sách đầy đủ các ứng dụng phụ thuộc. Bản sao lưu vault có thể phục hồi, còn khóa giải mã được quản lý bởi cùng nguồn danh tính mà vault dùng để xác thực.

Hãy trả lời:

1. Những đặc quyền nào vẫn chưa được kiểm soát chỉ bằng checkout?
2. Vì sao rotation có thể làm dịch vụ gián đoạn?
3. Cần biết gì để xác nhận backup có thể dùng trong tình huống mất nguồn danh tính?
4. Khi nghi ngờ mật khẩu bị lộ, chỉ chặn truy xuất vault có đủ không?
5. Những bằng chứng nào giúp xác định ai đã dùng tài khoản dùng chung?

### Gợi ý phân tích

**Về quyền:** tài khoản quản trị vẫn có phạm vi rộng. Hết checkout không tự làm mất credential hoặc kết thúc phiên ở đích. Cần xem cả quyền tạo tài khoản, khóa hoặc đường truy cập khác.

**Về phụ thuộc:** ứng dụng có thể giữ credential cũ, chỉ đọc khi khởi động hoặc dùng theo lịch dài. Không biết đầy đủ bên sử dụng thì chưa đánh giá được tác động của việc đổi mật khẩu.

**Về khôi phục:** cần kiểm tra cách sử dụng khóa, danh tính phục hồi và khả năng truy cập các thành phần khi nguồn danh tính thông thường mất. Giải mã được backup còn phải đi kèm đối soát credential với đích.

**Về sự cố:** phải xử lý credential và phiên ở hệ thống đích, đồng thời xem hành động đã thực hiện. Chặn yêu cầu mới vào vault không xử lý hết những bản sao đã lấy.

**Về bằng chứng:** cần liên kết danh tính người yêu cầu, quyết định cấp, lần truy xuất hoặc phiên broker, phiên bản credential và log ở đích. Nếu chỉ lưu tên tài khoản dùng chung, khả năng phân biệt người sử dụng sẽ hạn chế.

## 19. Những điểm cần ghi nhớ

- PAM vault quản lý cả việc bảo vệ credential và những đường sử dụng credential trong hệ thống PAM.
- Quyền đọc bí mật, quyền sử dụng qua broker và quyền quản trị chính sách là những khả năng khác nhau.
- Mã hóa dữ liệu phải đi cùng bảo vệ khóa, thành phần giải mã, backup và dữ liệu lúc sử dụng.
- Rotation là quá trình phối hợp giữa vault, hệ thống đích và bên phụ thuộc; cần xử lý kết quả chưa xác định.
- Hết lease, hết checkout hoặc mất quyền truy cập vault không tự chứng minh credential và phiên ở đích đã bị thu hồi.
- Least privilege, JIT và JEA cần được thực thi trên khả năng thực tế, không chỉ trên giao diện truy xuất bí mật.
- Một kiến trúc đầy đủ phải có tính sẵn sàng, khôi phục, truy cập khẩn cấp và bằng chứng có thể đối chiếu.

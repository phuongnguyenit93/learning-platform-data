# Cấp quyền rộng, dùng bí mật tĩnh và điểm truy cập công khai ngoài ý muốn

> **Phạm vi:** Phản mẫu kiến trúc trong CLOUD_ARCHITECTURE. Bài học phân tích ba sai lầm bảo mật thường đi cùng nhau khi thiết kế, di chuyển và vận hành ứng dụng trên đám mây: cấp quyền vượt nhu cầu, phụ thuộc vào thông tin xác thực tĩnh và vô tình mở tài nguyên ra Internet. Người học sẽ liên hệ các quyết định về mạng, compute, dữ liệu, triển khai và vận hành với các đánh đổi về độ tin cậy, bảo mật, khả năng mở rộng, chi phí và các nguyên tắc Well-Architected.

## 1. Bối cảnh: một cấu hình thuận tiện có thể mở rộng phạm vi sự cố

Trong giai đoạn thử nghiệm, nhóm phát triển thường muốn ứng dụng chạy được càng sớm càng tốt. Ba lựa chọn tưởng như giúp tiến nhanh là:

1. Cấp cho ứng dụng hoặc pipeline vai trò có thể thao tác gần như mọi tài nguyên để tránh lỗi thiếu quyền.
2. Tạo một access key, mật khẩu hoặc token dùng chung lâu dài để khỏi phải xử lý cơ chế cấp danh tính cho workload.
3. Mở địa chỉ công khai hoặc cho phép nguồn truy cập bất kỳ để kiểm tra kết nối từ máy cá nhân.

Nếu những thiết lập đó đi vào sản xuất, một lỗi ứng dụng, nhầm cấu hình, rò rỉ token hay mất quyền kiểm soát một thành phần nhỏ có thể ảnh hưởng đến toàn bộ môi trường. Ví dụ: một worker chỉ cần ghi hóa đơn vào một thư mục lưu trữ nhưng được phép xóa mọi bucket; thông tin xác thực của worker lại nằm trong image; đồng thời endpoint quản trị worker có thể truy cập từ Internet. Tác động tiềm ẩn vượt rất xa chức năng ghi hóa đơn.

**Tư duy thiết kế cần thay đổi:** mỗi quyền, mỗi bí mật và mỗi đường kết nối đều là một khả năng được cấp có chủ đích, gắn với một yêu cầu nghiệp vụ cụ thể, một phạm vi tài nguyên cụ thể và một người chịu trách nhiệm. Hệ thống hoạt động thành công chưa đủ chứng minh kiến trúc an toàn.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt **quyền hiệu lực**, **thông tin xác thực** và **khả năng truy cập qua mạng**; giải thích vì sao chúng tạo rủi ro khác nhau nhưng thường kết hợp.
- Nhận ra các dấu hiệu phản mẫu trong IAM, service account, CI/CD, cấu hình mạng, API, cơ sở dữ liệu và lưu trữ.
- Thiết kế quyền tối thiểu, danh tính workload ngắn hạn, quản lý vòng đời bí mật và phân tách vùng mạng.
- Xác định mức ưu tiên khắc phục từ phạm vi ảnh hưởng thực tế thay vì chỉ dựa vào một dấu hiệu như cổng 443 đang mở.
- Viết tiêu chí chấp nhận và phép kiểm tự động để tránh phản mẫu tái diễn, đồng thời ghi nhận các đánh đổi Well-Architected.

## 2. Ba khái niệm phải tách rõ

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Danh tính/principal** | Ai hoặc workload nào đang yêu cầu hành động? | Người quản trị, container xử lý đơn hàng, pipeline CI/CD |
| **Quyền/authorization** | Danh tính được làm gì, trên tài nguyên nào, trong điều kiện nào? | Chỉ được đọc đối tượng báo cáo trong một vùng lưu trữ |
| **Thông tin xác thực/credential** | Bên yêu cầu chứng minh danh tính bằng cách nào? | Token tạm thời, chứng chỉ, mật khẩu, khóa API |
| **Khả năng truy cập/reachability** | Gói tin hoặc yêu cầu có đi tới giao diện dịch vụ được không? | Có thể gọi HTTPS từ Internet đến load balancer |
| **Đường biên tin cậy/trust boundary** | Dữ liệu và thao tác đi qua các miền quyền kiểm soát nào? | Internet → lớp biên → ứng dụng → cơ sở dữ liệu |
| **Phạm vi ảnh hưởng/blast radius** | Nếu một điểm bị chiếm quyền thì phạm vi hậu quả tối đa là gì? | Một thư mục hóa đơn hay toàn bộ tài khoản đám mây |

Ba điều kiện này **không đồng nghĩa**:

- Một cơ sở dữ liệu nằm trong subnet riêng có thể vẫn bị truy cập trái phép nếu ứng dụng bên trong có quyền quá rộng hoặc lộ credential.
- Một endpoint HTTPS công khai có thể hoàn toàn hợp lý nếu đó là API dành cho khách hàng, có xác thực, phân quyền, chống lạm dụng và giám sát phù hợp.
- Một khóa API được mã hóa trong kho cấu hình vẫn có thể mang quyền nguy hiểm nếu nó tồn tại quá lâu và thiếu kiểm soát ai có thể đọc hoặc sử dụng.

Khả năng truy cập qua mạng thường quyết định **ai có thể đến được bề mặt tấn công**; cơ chế xác thực xác định **yêu cầu được gắn với danh tính nào**; phân quyền xác định **danh tính được làm gì**. Bảo vệ chỉ một lớp sẽ để lại rủi ro ở các lớp còn lại.

### 2.1. Mô hình nguy cơ giản lược

~~~mermaid
flowchart LR
    A["Điểm quản trị vô tình công khai"] --> B["Một dịch vụ bị truy cập trái phép"]
    C["Thông tin xác thực tồn tại lâu bị lộ"] --> B
    B --> D{"Quyền của danh tính bị chiếm?"}
    D -->|"Chỉ đủ quyền chức năng"| E["Phạm vi sự cố được giới hạn"]
    D -->|"Quyền vượt nhu cầu"| F["Truy cập nhiều tài nguyên, dữ liệu hoặc thao tác nguy hiểm"]
    E --> G["Phát hiện, cô lập và khôi phục"]
    F --> G
~~~

Đây là sơ đồ **phân tích tác động**, không phải trình tự mà mọi sự cố chắc chắn sẽ diễn ra. Lộ bí mật, mở mạng hoặc cấp quyền rộng đều có thể tạo sự cố riêng lẻ; khi đi cùng nhau, chúng làm gia tăng xác suất và mức độ nghiêm trọng của hậu quả.

## 3. Phản mẫu thứ nhất: cấp quyền rộng hơn nhu cầu

### 3.1. Dấu hiệu nhận biết

**Quyền quá rộng (overprivileged access)** xuất hiện khi quyền thực tế của một principal vượt các hành động và tài nguyên cần thiết để hoàn thành trách nhiệm được giao. Ví dụ phổ biến:

- Tài khoản chạy ứng dụng được cấp quyền quản trị toàn tài khoản hoặc toàn dự án đám mây.
- Chính sách cho phép mọi hành động trên mọi tài nguyên chỉ để bỏ qua lỗi bị từ chối truy cập.
- Một service account dùng chung cho nhiều ứng dụng, môi trường và nhóm phát triển.
- Pipeline chỉ cần triển khai một dịch vụ nhưng có thể xóa cơ sở dữ liệu, tắt nhật ký kiểm toán hoặc thay đổi chính sách định danh.
- Người phát triển dùng danh tính đặc quyền cho công việc thường ngày; tài khoản nghỉ việc hoặc khóa cũ vẫn còn quyền.
- Ứng dụng chỉ cần đọc đối tượng nhưng được phép ghi, xóa hoặc thay đổi quyền công khai của toàn bộ kho lưu trữ.
- Vai trò gắn cho máy ảo, container hay serverless function được tái sử dụng cho tác vụ khác mà không rà soát lại quyền.

Quyền rộng không phải là vấn đề chỉ của một câu lệnh IAM. **Quyền hiệu lực (effective permissions)** có thể đến từ vai trò gắn trực tiếp, nhóm, cơ chế ủy quyền, chính sách tài nguyên, trust policy, vai trò được giả định và các ràng buộc ở cấp tổ chức. Cần kiểm tra toàn bộ đường đi của quyền truy cập.

### 3.2. Vì sao quyền rộng làm rủi ro tăng mạnh?

Giả sử dịch vụ gửi email cần đọc mẫu thư và ghi trạng thái gửi. Nếu quyền của dịch vụ còn cho phép đọc hồ sơ khách hàng ở ứng dụng khác, tạo vai trò quản trị hoặc vô hiệu hóa audit log, thì lỗi bảo mật trong dịch vụ email có thể ảnh hưởng đến những hệ thống không liên quan. Đặc biệt nguy hiểm là các quyền cho phép **cấp thêm quyền**, sửa chính sách, tạo thông tin xác thực mới, vô hiệu hóa kiểm soát hoặc thay đổi luồng ghi log. Khi kết hợp, chúng có thể mở rộng ảnh hưởng vượt vai trò ban đầu.

Nguyên tắc **least privilege** gồm ít nhất bốn chiều:

1. **Hành động:** chỉ cho phép các thao tác cần thiết, ví dụ đọc đối tượng nhưng không xóa.
2. **Tài nguyên:** chỉ các tài nguyên hoặc tiền tố đường dẫn cụ thể, không toàn bộ tổ chức.
3. **Ngữ cảnh:** giới hạn theo môi trường, danh tính workload, mạng, thời gian hoặc thuộc tính được kiểm soát nếu nền tảng hỗ trợ.
4. **Thời hạn:** quyền tồn tại trong thời gian thật sự cần; đặc quyền phát sinh theo yêu cầu thay vì cấp vĩnh viễn.

Một principal có ít thao tác nhưng được truy cập **mọi** bản ghi khách hàng vẫn có thể có phạm vi ảnh hưởng lớn. Ngược lại, chỉ giới hạn tài nguyên nhưng cho phép thay đổi toàn bộ chính sách truy cập của tài nguyên đó vẫn có rủi ro cao.

### 3.3. Ví dụ từ quyền mọi thứ sang quyền vừa đủ

Ví dụ sau minh họa **IAM policy kiểu AWS**. Tên bucket là giả định; đoạn đầu là phản mẫu và không nên áp dụng vào môi trường thật:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "*",
      "Resource": "*"
    }
  ]
}
~~~

Ứng dụng xuất hóa đơn chỉ cần tải tệp hóa đơn xuống có thể bắt đầu với chính sách hẹp hơn:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOwnInvoices",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::example-invoices-prod/generated/*"]
    }
  ]
}
~~~

Chính sách thứ hai **chỉ minh họa giới hạn hành động và tài nguyên**, chưa phải cấu hình hoàn chỉnh cho mọi ứng dụng. Nếu ứng dụng cần liệt kê đối tượng, giải mã bằng khóa do khách hàng quản lý, truy cập qua điểm cuối riêng hoặc dùng điều kiện theo tag, phải bổ sung những quyền tương ứng sau khi kiểm chứng. Quyền hiệu lực còn phụ thuộc các policy khác, quyền truy cập tài nguyên và cơ chế giới hạn ở cấp tổ chức. Một policy cho phép hẹp không bảo đảm an toàn nếu principal còn gắn một policy quản trị khác.

Đối với hệ không dùng AWS, áp dụng cùng nguyên tắc cho role binding, resource policy, RBAC/ABAC và danh tính workload tương đương.

### 3.4. Quy trình sửa quyền quá rộng

1. **Lập danh mục:** lấy principal, dịch vụ, môi trường, chủ sở hữu và tài nguyên liên quan; tách con người, workload và CI/CD.
2. **Xác định nhu cầu nghiệp vụ:** liệt kê hành động thực sự cần, phạm vi dữ liệu và điều kiện hoạt động; phân biệt đọc, ghi, xóa, quản trị và cấp quyền.
3. **Quan sát sử dụng:** xem audit trail, access analysis và các bài kiểm thử để xác định quyền đang dùng. Dữ liệu log không đầy đủ hoặc không thấy hành động trong vài ngày **không chứng minh** quyền không cần thiết, nhất là với thao tác theo tháng hoặc xử lý thảm họa.
4. **Thiết kế vai trò riêng:** mỗi workload có danh tính riêng; tách phát triển, thử nghiệm và sản xuất; tách tác vụ triển khai khỏi tác vụ chạy nghiệp vụ; hạn chế đường ủy quyền chéo.
5. **Kiểm thử dương và âm:** thao tác hợp lệ phải thành công, hành động vượt phạm vi phải bị từ chối; thử cả trường hợp phân quyền qua tài nguyên khác.
6. **Triển khai theo giai đoạn:** theo dõi lỗi bị từ chối, xác định có ảnh hưởng nghiệp vụ không; điều chỉnh trên bằng chứng, không trả lại quyền quản trị chỉ để ứng dụng chạy.
7. **Rà soát định kỳ:** xử lý quyền không còn dùng, vai trò mồ côi, thay đổi nhóm sở hữu, tài khoản bên ngoài và trường hợp đặc quyền khẩn cấp.

**Cấp quyền khẩn cấp (break-glass)** có thể cần cho sự cố hạ tầng. Thiết kế tài khoản hoặc cơ chế khẩn cấp riêng, kiểm soát chặt khả năng kích hoạt, ghi log, cảnh báo, yêu cầu phê duyệt theo tổ chức và thu hồi sau sự cố. Không biến quyền quản trị thường trực thành phương án duy nhất để xử lý lỗi.

### 3.5. RBAC, ABAC và ràng buộc cấp tổ chức

RBAC gắn quyền với vai trò như người triển khai, người trực vận hành hoặc tác vụ đọc báo cáo. ABAC xét thuộc tính của danh tính, tài nguyên và ngữ cảnh như môi trường hoặc nhóm sở hữu. ABAC giúp mở rộng khi nhiều tài nguyên có cùng quy tắc nhưng dễ trở nên nguy hiểm nếu người dùng có thể tự sửa tag quyết định quyền. Hãy giới hạn ai được gán, đổi hoặc xóa thuộc tính dùng cho phân quyền.

Ở quy mô tổ chức, policy giới hạn cấp tổ chức hoặc permission boundary có thể ngăn một vai trò vượt giới hạn cho phép, nhưng **không thay thế** việc thiết kế quyền nhỏ cho từng ứng dụng. Các cơ chế deny và đánh giá policy có khác biệt giữa các nhà cung cấp; cần kiểm tra thứ tự và ngữ nghĩa thực tế của hệ đang sử dụng.

## 4. Phản mẫu thứ hai: phụ thuộc vào bí mật tĩnh

### 4.1. Bí mật tĩnh là gì?

**Bí mật tĩnh (static secret)** là thông tin xác thực có giá trị trong thời gian dài, thường được tạo một lần và dùng lại: access key, mật khẩu dịch vụ, client secret, token bên thứ ba hoặc khóa riêng. Không phải mọi bí mật tĩnh đều bị cấm: một số hệ thống bên thứ ba hoặc thiết bị cũ chưa hỗ trợ liên kết danh tính ngắn hạn. Phản mẫu xuất hiện khi bí mật được dùng **không cần thiết, chia sẻ quá rộng, lưu sai chỗ, không có vòng đời và thiếu khả năng thu hồi**.

Những tình huống cần báo động:

- Dán khóa truy cập vào mã nguồn, file cấu hình đẩy lên Git, tài liệu wiki hoặc script triển khai.
- Đóng gói secret vào container image hoặc đưa qua tham số build; khi đó secret có thể lưu trong lớp image, cache build hoặc metadata.
- Dùng một khóa sản xuất cho nhiều môi trường hoặc nhóm; không biết dịch vụ nào đang dùng khóa.
- Token không có ngày hết hạn, không thay được mà không dừng dịch vụ hoặc không có audit xem khi nào được sử dụng.
- Secret đi vào log do debug, exception, CI/CD output, URL query string hoặc hệ thống thu thập telemetry.
- Quyền đọc kho bí mật được cấp quá rộng; bí mật đã được mã hóa khi lưu nhưng quá nhiều principal có thể giải mã.

Việc mã hóa secret lúc lưu và truyền là cần thiết, nhưng **không giải quyết được** vấn đề: nếu một ứng dụng bị chiếm quyền có thể đọc hoặc sử dụng secret, kẻ kiểm soát ứng dụng có thể tận dụng quyền đó. Vì vậy mục tiêu là vừa giảm số secret dài hạn, vừa giới hạn quyền sử dụng và thời gian hữu dụng của credential.

### 4.2. Thiết kế ưu tiên danh tính workload và thông tin xác thực tạm thời

Ở dịch vụ đám mây hỗ trợ, hãy để workload lấy danh tính từ môi trường chạy thay vì tự mang access key dài hạn:

- Máy ảo hoặc container sử dụng **identity/role gắn với workload** để lấy credential có hạn sử dụng.
- Các dịch vụ được quản lý dùng danh tính dịch vụ riêng để gọi tài nguyên được cấp quyền.
- Pipeline CI/CD có thể dùng cơ chế **OIDC federation** hoặc hình thức liên kết danh tính được nền tảng hỗ trợ để đổi một tín hiệu định danh ngắn hạn lấy quyền triển khai theo phạm vi.
- Người quản trị dùng đăng nhập tập trung, MFA và vai trò đặc quyền theo phiên thay vì tải xuống khóa tồn tại vô thời hạn.

~~~mermaid
sequenceDiagram
    participant App as Workload
    participant IdP as Nền tảng danh tính
    participant Data as Dịch vụ dữ liệu
    App->>IdP: Yêu cầu credential theo danh tính workload
    IdP-->>App: Credential ngắn hạn, phạm vi đã cấp
    App->>Data: Gọi API bằng credential hợp lệ
    Data-->>App: Chỉ cho phép thao tác đúng quyền
    Note over App,Data: Token hết hạn phải được làm mới; cần quan sát lỗi gia hạn
~~~

Mô hình này giảm nhu cầu lưu access key dài hạn. Nó **không tự động tạo least privilege**: nếu vai trò gắn với workload có quyền quản trị thì token ngắn hạn vẫn quá nguy hiểm trong khoảng thời gian còn hiệu lực. Đồng thời, phải kiểm chứng trust policy: chỉ workload hoặc pipeline được xác định mới có thể nhận đúng vai trò.

### 4.3. Khi bắt buộc có secret: quản lý trọn vòng đời

Với mật khẩu DB, khóa API đối tác hoặc chứng chỉ có khóa riêng, thiết kế tối thiểu gồm:

| Giai đoạn | Kiểm soát cần có | Bằng chứng |
|---|---|---|
| Tạo | Sinh bằng công cụ đáng tin cậy, độ mạnh phù hợp; không tái dùng giữa môi trường | Mã định danh secret và chủ sở hữu, không lưu giá trị thật trong báo cáo |
| Lưu | Secret manager hoặc kho bí mật chuyên dụng, mã hóa và phân quyền riêng | Policy kho và lịch sử truy cập |
| Cấp cho runtime | Workload xác thực bằng danh tính riêng; ứng dụng chỉ đọc secret được phép | Thử đọc hợp lệ và đọc ngoài phạm vi bị từ chối |
| Sử dụng | Hạn chế in log, xuất hiện trong lỗi, URL, artifact và bộ nhớ không cần thiết | Kiểm tra log và luồng xử lý lỗi |
| Gia hạn/rotation | Có lịch, cơ chế thay an toàn, cách quản lý kết nối đang mở | Diễn tập rotation và giám sát lỗi xác thực |
| Thu hồi | Có thể vô hiệu hóa khi lộ, nghỉ việc hoặc thay đổi hệ thống | Biên bản revoke và kiểm tra khóa cũ hết tác dụng |
| Xóa | Hủy các bản sao không cần thiết sau thời gian giữ đã duyệt | Quản trị vòng đời và kiểm tra artifact |

**Secret manager không phải “kho để tất cả ứng dụng đọc”.** Đặt quyền đọc theo danh tính của đúng dịch vụ, hạn chế quyền quản trị kho và quyền giải mã, bật audit, cảnh báo truy cập bất thường. Tránh đưa giá trị bí mật vào output của hệ thống IaC, file state không được bảo vệ, tham số dòng lệnh hiện trên danh sách tiến trình hoặc log của pipeline.

Một cấu hình **giả mã** nhằm mô tả ranh giới đúng có thể như sau; cú pháp không thuộc một dịch vụ đám mây cụ thể:

~~~yaml
service: order-worker
identity: workload/order-worker-prod
secret_reference:
  provider: managed-secret-store
  name: payments/api-token-prod
  value_in_source_code: false
permissions:
  - action: secret.read
    resource: payments/api-token-prod
  - action: queue.consume
    resource: order-confirmed-prod
network:
  outbound_destinations:
    - approved-payment-provider
rotation:
  owner: payment-platform
  tested: true
~~~

Ở thiết kế này, ứng dụng sử dụng **tham chiếu** đến bí mật và dựa vào quyền của workload để lấy giá trị khi chạy. Các trường cấu hình cần ánh xạ sang cơ chế thực của nhà cung cấp; không sao chép nguyên ví dụ này làm cấu hình sản xuất.

### 4.4. Rotation an toàn và xử lý khi nghi lộ

Việc thay secret thường thất bại vì nhiều instance còn giữ giá trị cũ hoặc dịch vụ đối tác chỉ cho phép một token. Một quy trình thông thường:

1. Xác định mọi bên sử dụng và khả năng hệ nguồn chấp nhận đồng thời hai credential.
2. Nếu hỗ trợ, tạo credential mới, phân phối qua kho bí mật và cho ứng dụng làm mới theo cơ chế được thử nghiệm.
3. Xác nhận các phiên mới dùng credential mới; kiểm tra retry, connection pool và tác vụ dài hạn.
4. Thu hồi credential cũ, kiểm tra nó không còn dùng được và theo dõi lỗi xác thực.
5. Cập nhật lịch sử rotation, chủ sở hữu và điều kiện xử lý sự cố.

Khi **nghi đã bị lộ**, ưu tiên kích hoạt ứng phó sự cố: bảo toàn bằng chứng cần thiết, giới hạn quyền và khả năng sử dụng credential, thu hồi/thay mới sớm theo mức độ nguy hiểm, kiểm tra log và phạm vi tài nguyên bị tác động. Không đợi đến lịch rotation định kỳ. Nếu việc thu hồi tức thời có thể ảnh hưởng dịch vụ sống còn, người phụ trách sự cố phải cân bằng thời gian khống chế với phương án duy trì dịch vụ, theo kế hoạch ứng cứu đã chuẩn bị.

**Lưu ý với Git:** xóa một dòng secret ở commit mới không làm secret biến mất khỏi lịch sử commit, bản sao đã clone, artifact hoặc hệ thống log. Vì vậy cần thu hồi/rotation và đánh giá các nơi đã sao chép; việc dọn lịch sử chỉ là bước bổ sung.

## 5. Phản mẫu thứ ba: điểm truy cập công khai ngoài ý muốn

### 5.1. “Công khai” phải được đánh giá theo mục đích sử dụng

Một tài nguyên được xem là có bề mặt Internet khi bên ngoài có thể định tuyến yêu cầu đến một giao diện được mở, trực tiếp hoặc qua thành phần trung gian. Nhưng **có địa chỉ công khai**, **có thể truy cập cổng dịch vụ**, **được phép xác thực** và **được phép thực hiện thao tác** là các cấp độ khác nhau.

**Công khai đúng thiết kế:** người dùng cần truy cập trang web hoặc API HTTPS. Tại lớp biên có TLS, định tuyến có chủ đích, kiểm soát truy cập phù hợp, giới hạn lưu lượng và quan sát. Phần backend và dữ liệu không nhất thiết phải truy cập trực tiếp được từ Internet.

**Công khai ngoài ý muốn:** cơ sở dữ liệu, giao diện quản trị, SSH/RDP, dashboard giám sát, worker debug hoặc kho lưu trữ dữ liệu nhạy cảm bị mở ra mọi nguồn mạng hoặc cho phép truy cập không xác thực ngoài yêu cầu nghiệp vụ.

Không thể kết luận an toàn chỉ từ tên subnet **private**, một tên DNS nội bộ hoặc việc dịch vụ “vốn nằm trong VPC”. Phải xét đường đi hiệu lực: địa chỉ IP, route, gateway/load balancer, firewall/security group, ACL, ingress controller, cấu hình dịch vụ, resource policy và xác thực ở lớp ứng dụng.

### 5.2. Những cấu hình đáng rà soát

| Thành phần | Dấu hiệu phản mẫu | Nguy cơ | Hướng kiến trúc |
|---|---|---|---|
| Cơ sở dữ liệu | Có địa chỉ public và cổng DB nhận kết nối từ mọi IP | Tăng khả năng dò quét, đánh cắp dữ liệu nếu xác thực yếu hoặc lỗi dịch vụ | DB trong mạng riêng, chỉ nhận từ ứng dụng/điểm quản trị được kiểm soát |
| Máy ảo/container | Cổng SSH, RDP, debug hoặc quản trị mở cho 0.0.0.0/0 hoặc ::/0 | Tăng bề mặt tấn công vào mặt phẳng quản trị | Kênh quản trị riêng, truy cập theo danh tính, nhật ký và thời hạn |
| Object storage | Cho phép anonymous/public read hoặc write ngoài nhu cầu | Lộ thông tin, sửa/ghi nội dung trái phép | Chặn truy cập công khai mặc định, policy theo principal và prefix |
| API nội bộ | Cấu hình gateway/ingress cho mọi yêu cầu nhưng thiếu auth | Gọi chức năng nội bộ, đọc/ghi dữ liệu trái phép | Xác thực, phân quyền, mạng riêng hoặc gateway có kiểm soát |
| Dashboard/log | URL truy cập công khai, token dùng chung | Lộ cấu trúc nội bộ, dữ liệu nhạy cảm hoặc quyền điều hành | Danh tính tập trung, kiểm soát mạng và quyền riêng |
| CI/CD/callback | Webhook triển khai hoặc endpoint quản lý có thể bị gọi tùy ý | Triển khai ngoài ý muốn, thay đổi artifact hoặc cấu hình | Xác minh danh tính/chữ ký yêu cầu, phân quyền và giới hạn nguồn khi phù hợp |
| CDN/origin | CDN được bảo vệ nhưng origin vẫn được truy cập trực tiếp | Bỏ qua kiểm soát lớp biên | Ràng buộc origin nhận lưu lượng chỉ từ đường đi được duyệt |

**0.0.0.0/0 và ::/0** đại diện cho mọi địa chỉ IPv4/IPv6 trong ngữ cảnh rule nguồn mạng. Một rule cho phép Internet vào cổng 443 của **public load balancer phục vụ website** có thể đúng yêu cầu. Cùng rule đó trên cổng quản trị hoặc DB lại có thể là phát hiện nghiêm trọng. Đừng quên IPv6: chặn toàn bộ IPv4 nhưng mở mọi nguồn IPv6 vẫn tạo đường truy cập công khai.

### 5.3. Phân vùng mạng theo đường đi nghiệp vụ

Ví dụ ứng dụng thương mại điện tử có thể tổ chức kết nối như sau:

~~~mermaid
flowchart TB
    I["Người dùng Internet"]
    subgraph Edge["Lớp biên được phép công khai"]
        WAF["WAF / giới hạn tốc độ / TLS"]
        LB["Public load balancer"]
        WAF --> LB
    end
    subgraph Private["Mạng ứng dụng riêng"]
        WEB["Web/API workload"]
        JOB["Worker nền"]
        DB[("Cơ sở dữ liệu riêng")]
        OBJ[("Kho dữ liệu có kiểm soát")]
        WEB -->|"Chỉ cổng và danh tính cần thiết"| DB
        WEB --> OBJ
        JOB --> DB
    end
    I --> WAF
    LB --> WEB
    WEB -->|"Sự kiện nội bộ"| JOB
    WEB -.->|"Outbound được phê duyệt"| EXT["API đối tác"]
    ID["Danh tính workload"] -.-> WEB
    ID -.-> JOB
    SEC["Secret manager"] -.->|"Quyền đọc giới hạn"| WEB
    SEC -.->|"Quyền đọc giới hạn"| JOB
~~~

Sơ đồ có tính khái niệm. Trong triển khai thật, phải xác minh loại dịch vụ, vị trí mạng, luồng dữ liệu, tuyến egress, quyền của từng principal và khả năng giải quyết tên miền. Một dịch vụ được quản lý có thể không nằm trực tiếp trong subnet của ứng dụng nhưng vẫn cung cấp kết nối riêng hoặc kiểm soát truy cập tương đương.

Hãy bắt đầu từ **ma trận kết nối**:

| Nguồn | Đích | Giao thức/đường đi | Lý do cho phép | Mặc định với kết nối khác |
|---|---|---|---|---|
| Internet | Public ingress | HTTPS 443 | Truy cập sản phẩm | Không cho phép |
| Ingress | API workload | Cổng ứng dụng đã định | Chuyển yêu cầu đã kiểm soát | Không cho phép |
| API/worker | Database | Cổng DB yêu cầu | Đọc/ghi nghiệp vụ | Không cho phép |
| Workload có danh tính | Kho secret/dữ liệu | Endpoint được bảo vệ | Đọc đúng bí mật hoặc dữ liệu cần thiết | Từ chối theo principal |
| Workload | Đối tác | Egress được phê duyệt | Tích hợp bên ngoài | Có kiểm soát, theo thiết kế |
| Người vận hành | Kênh quản trị | Kênh riêng hoặc được xác thực mạnh | Chẩn đoán/sửa sự cố | Không mở cổng quản trị toàn Internet |

**Phân vùng mạng không thay thế quyền truy cập ứng dụng.** Một workload bị chiếm quyền vẫn có thể gọi các dịch vụ mà mạng cho phép; vì vậy phải kết hợp IAM, xác thực giữa dịch vụ, ràng buộc tài nguyên, input validation và nhật ký kiểm toán. Ngược lại, chỉ có IAM đúng mà để endpoint quản trị công khai không cần thiết vẫn làm tăng cơ hội bị khai thác lỗi phần mềm.

### 5.4. Điểm truy cập công khai gián tiếp

Những tình huống dễ bị bỏ sót gồm:

- Bật public access trên bucket để thử tải ảnh, rồi quên tắt khi đưa vào sản xuất.
- Mở một listener trên load balancer nhưng không giới hạn route hoặc không gắn cơ chế xác thực cho đường quản trị.
- Tạo rule tạm cho nhà thầu với nguồn mọi IP, sau đó giữ nguyên.
- Công khai dịch vụ qua một ingress/controller mặc định khi chuyển từ VM sang container.
- Mạng đã chặn đường truy cập trực tiếp nhưng dịch vụ vẫn có public endpoint và resource policy cho phép truy cập không phù hợp từ nơi khác.
- Định nghĩa quy tắc IPv4 rất chặt nhưng quên cấu hình IPv6.
- Kho dữ liệu được cho phép đọc công khai vì cần phân phát vài tệp marketing, trong khi cùng kho chứa báo cáo nội bộ.
- Bảo vệ trước CDN/WAF nhưng không khóa đường truy cập trực tiếp vào origin.

Đặc biệt, **object storage** thường được bảo vệ bằng tổ hợp điều khiển công khai, IAM và resource policy. Thiết kế cần kiểm tra cả quyền đọc, ghi, liệt kê, thay đổi ACL/chính sách và quyền sử dụng khóa mã hóa. Nếu nội dung buộc phải phân phối công khai, hãy tách kho hoặc tiền tố dành riêng cho nội dung đó, sử dụng phương án phân phối phù hợp và tránh chứa dữ liệu nhạy cảm cùng ranh giới quyền.

## 6. Khi ba phản mẫu cùng xuất hiện: phân tích chuỗi ảnh hưởng

Giả sử kiến trúc một doanh nghiệp như sau:

- Container xử lý hóa đơn sử dụng một access key lâu dài được lưu trong cấu hình image.
- Access key thuộc vai trò có thể đọc, ghi, xóa nhiều kho dữ liệu và thay đổi chính sách tài nguyên.
- Một endpoint debug của container được phát hành ra Internet do cấu hình ingress dùng chung.

Một sự cố tại endpoint debug có thể cho phép truy cập thông tin chạy của container; nếu credential bị lộ, phạm vi dữ liệu liên quan đến vai trò rộng hơn rất nhiều so với hóa đơn. Ngay cả khi endpoint debug được vá, credential cũ còn hiệu lực vẫn là nguồn rủi ro. Ngay cả khi credential bị thu hồi, endpoint công khai không cần thiết vẫn có thể có lỗ hổng khác. Vì vậy, phải xử lý **từng nguyên nhân độc lập** và kiểm tra cả khả năng kết hợp.

| Kiểm soát được bổ sung | Tác động lên rủi ro | Rủi ro còn lại |
|---|---|---|
| Đóng endpoint debug công khai | Giảm bề mặt truy cập từ Internet | Quyền và secret vẫn rộng/dài hạn |
| Chuyển từ static key sang workload identity | Giảm credential tồn tại lâu và bản sao bí mật | Vai trò vẫn có thể vượt nhu cầu |
| Thu hẹp IAM theo hành động và tài nguyên | Giảm phạm vi ảnh hưởng nếu danh tính bị chiếm | Endpoint không cần thiết và quản lý secret vẫn cần sửa |
| Bổ sung giám sát, cảnh báo và kiểm thử tự động | Phát hiện lệch cấu hình nhanh hơn | Không thay thế phòng ngừa và bảo vệ dữ liệu |

Đây là tinh thần **phòng thủ nhiều lớp (defense in depth)**: mỗi lớp làm giảm khả năng xảy ra hoặc giảm tác động khi một lớp khác thất bại. Mọi lớp cần được kiểm thử độc lập; không dùng sự tồn tại của WAF, VPN hay mã hóa để bỏ qua các lỗi quyền và danh tính.

## 7. Phát hiện phản mẫu bằng bằng chứng

### 7.1. Kiểm tra ở ba nơi

**Thiết kế và mã hạ tầng:** phân tích IaC, role binding, network rule, công khai bucket, khai báo secret và điều kiện trust. Kiểm tra cả file cấu hình chart, manifest, biến triển khai và mô-đun IaC dùng chung. Quy tắc tự động nên phát hiện trường hợp quyền wildcard, nguồn Internet đến cổng quản trị, secret trong mã hoặc workload dùng tài khoản tĩnh không cần thiết.

**Môi trường đang chạy:** so sánh cấu hình thực tế với mã hạ tầng. Drift có thể xuất hiện khi người vận hành sửa rule thủ công, policy khác được gắn thêm, hoặc nhà cung cấp áp dụng cấu hình mặc định khác với dự kiến. Kiểm tra quyền hiệu lực, địa chỉ/route thật, public access setting, certificate, audit log và danh tính đang được workload sử dụng.

**Luồng xử lý thực:** thực hiện phép thử dương/âm từ vị trí mạng và principal được chọn. Ví dụ: tài khoản worker đọc đúng secret; cùng tài khoản không thể đọc secret của ứng dụng khác. Máy thử bên ngoài gọi được public HTTPS hợp lệ; không thể truy cập giao diện quản trị hoặc cổng DB. Các bài thử phải được phép, giới hạn phạm vi và tránh dùng dữ liệu nhạy cảm thật.

### 7.2. Ma trận kiểm chứng

| Kiểm soát | Kiểm thử được chấp nhận | Dấu hiệu thất bại |
|---|---|---|
| Quyền workload | Chỉ hành động hợp lệ trên tài nguyên sở hữu thành công | Đọc/xóa tài nguyên môi trường khác vẫn được |
| Truyền quyền | Một workload không thể nhận vai trò đặc quyền của workload khác | Trust policy cho phép principal ngoài danh sách |
| Credential | Không có access key tĩnh không cần thiết trong source, image hoặc pipeline artifact | Scanner phát hiện khóa hoặc credential vẫn sống sau khi loại bỏ |
| Rotation | Credential mới hoạt động, credential cũ đã thu hồi không dùng được | Khóa cũ vẫn gọi API thành công hoặc ứng dụng ngừng hoạt động |
| Public reachability | Public ingress chỉ phục vụ route đã duyệt; DB và admin không truy cập trực tiếp từ ngoài | Có đường truy cập ngoài danh mục |
| Object storage | Anonymous access bị từ chối với dữ liệu không công khai | Đọc/ghi được khi không có danh tính hợp lệ |
| Audit/alert | Thay đổi IAM, public rule và truy cập secret để lại dấu vết theo chuẩn tổ chức | Sự kiện quan trọng không ghi nhận/cảnh báo |
| Recovery | Có runbook khôi phục cấu hình đúng và thay secret khi sự cố | Không xác định được ai xử lý hoặc cách ngắt quyền |

Chỉ kiểm tra mã hạ tầng **không đủ**, vì cấu hình runtime có thể đã lệch. Chỉ quan sát runtime **không đủ**, vì bản triển khai tiếp theo có thể tái tạo lỗi từ mã nguồn. Cần gắn cả hai với kiểm thử trước và sau thay đổi.

### 7.3. Guardrail trong pipeline

Ví dụ **quy tắc chính sách dạng giả mã** cho kiểm tra kiến trúc. Cần hiện thực bằng policy-as-code và cấu trúc của công cụ phù hợp:

~~~yaml
security_guardrails:
  iam:
    reject_unjustified_admin_policies: true
    require_workload_identity: true
    require_distinct_prod_roles: true
    approval_for_exception: security-owner
  secrets:
    scan_source_and_artifacts: true
    reject_plaintext_secrets: true
    audit_secret_reads: true
  exposure:
    deny_public_database: true
    deny_public_admin_ports: true
    deny_anonymous_private_storage: true
    allow_public_https_only_on_approved_ingress: true
  verification:
    run_negative_authorization_tests: true
    compare_runtime_with_declared_state: true
    check_ipv4_and_ipv6: true
~~~

**Không dùng một chính sách “cấm toàn bộ public”** nếu sản phẩm có API hoặc website công khai. Thay vào đó, phê duyệt danh sách ingress được thiết kế cho người dùng, bắt buộc kiểm soát ở lớp biên và từ chối việc công khai tài nguyên nội bộ. Ngoại lệ cần có lý do nghiệp vụ, thời hạn, chủ sở hữu và cách kiểm soát bù trừ.

## 8. Ưu tiên khắc phục theo mức ảnh hưởng thực tế

Không phải mọi phát hiện đều nghiêm trọng như nhau. Độ ưu tiên phụ thuộc vào:

1. **Khả năng truy cập:** từ Internet, đối tác, mạng riêng hoặc chỉ trong phiên quản trị đặc biệt?
2. **Độ mạnh của xác thực:** endpoint yêu cầu danh tính, MFA, mTLS hoặc có thể gọi vô danh?
3. **Quyền hiệu lực:** đọc một đối tượng hay có thể xóa dữ liệu, tạo khóa và sửa quyền?
4. **Loại dữ liệu:** công khai, nội bộ, thông tin cá nhân, bí mật kinh doanh hoặc dữ liệu được quản lý đặc biệt?
5. **Thời gian và khả năng phát hiện:** credential còn hạn bao lâu, có log cảnh báo và chủ sở hữu hay không?
6. **Tác động nghiệp vụ:** mất đơn, mất dữ liệu, gián đoạn giao dịch, thiệt hại tài chính hoặc vi phạm cam kết?

Ma trận **minh họa**, phải điều chỉnh theo tiêu chuẩn rủi ro của tổ chức:

| Tình huống | Mức xử lý thường ưu tiên | Cách tiếp cận |
|---|---|---|
| Cơ sở dữ liệu nhạy cảm có thể truy cập trực tiếp từ Internet; quản trị không được kiểm soát | Khẩn cấp | Giới hạn đường truy cập, bảo toàn log, kiểm tra truy cập và sửa cấu hình |
| Access key có quyền cao đã xuất hiện trong kho mã công khai hoặc artifact ngoài phạm vi | Khẩn cấp | Kích hoạt ứng phó, thu hồi/thay, giới hạn quyền và điều tra |
| Role CI/CD có quyền quản trị nhiều môi trường nhưng khóa chưa có dấu hiệu lộ | Cao, có lịch chuyển đổi ngắn | Tách môi trường, giới hạn role, đổi sang federation, kiểm thử |
| Public HTTPS của website có WAF và xác thực phù hợp | Có thể là thiết kế chấp nhận | Xác minh các lớp kiểm soát và kiểm thử định kỳ |
| Quyền đọc của worker rộng hơn một thư mục không nhạy cảm | Cần thu hẹp theo rủi ro | Định nghĩa tác vụ, policy test và triển khai dần |

Các nhãn “khẩn cấp/cao” ở trên mô tả **ví dụ**, không thay cho phân loại sự cố, SLA khắc phục hoặc nghĩa vụ thông báo theo chính sách và quy định áp dụng. Một cấu hình không có dấu hiệu bị khai thác vẫn có thể cần sửa ngay nếu phạm vi ảnh hưởng tiềm ẩn lớn.

## 9. Quy trình sửa kiến trúc mà không làm gián đoạn nghiệp vụ

### Bước 1: Lập bản đồ tài sản và đường đi

Chọn một hành trình quan trọng, ví dụ tạo đơn hàng, và vẽ từ người dùng đến ingress, dịch vụ, queue, DB, object storage và nhà cung cấp ngoài. Bên cạnh mỗi cạnh, ghi **principal, hành động, quyền hiệu lực, cách lấy credential, nguồn/đích mạng và nơi ghi log**. Đặt ranh giới môi trường phát triển, thử nghiệm và sản xuất.

### Bước 2: Đặt mục tiêu thiết kế

Ví dụ với worker gửi hóa đơn:

- Chỉ đọc bản ghi trạng thái và hóa đơn trong miền dữ liệu được giao.
- Chỉ ghi kết quả gửi hóa đơn vào queue hoặc bảng trạng thái của nó.
- Không có quyền quản trị IAM, xóa bucket, đọc secret của thanh toán hoặc sửa cấu hình mạng.
- Nhận credential ngắn hạn qua workload identity; chỉ lấy token đối tác qua kho bí mật nếu cần.
- Không có địa chỉ inbound từ Internet; chỉ nhận sự kiện qua queue và đi ra endpoint đối tác đã duyệt.

### Bước 3: Tạo thay đổi và kiểm thử trong môi trường đại diện

Giới hạn IAM theo tài nguyên; thử các hành động hợp lệ và trái phép. Đổi credential theo từng thành phần, đảm bảo kết nối hiện hành được thay đúng vòng đời. Tạo allowlist kết nối theo ma trận mạng và xác minh cả IPv4/IPv6. Kiểm tra thời gian làm mới token, timeout, retry và các tác vụ ít chạy trước khi triển khai.

### Bước 4: Chuyển đổi theo giai đoạn

Với ứng dụng lớn, nên phân loại vai trò và bí mật theo dịch vụ, bắt đầu bằng workload ít rủi ro để đo lỗi bị từ chối. Áp dụng cấu hình mới trong môi trường đại diện, chạy kiểm thử rồi chuyển dần. Quan sát tỷ lệ lỗi xác thực, lỗi phân quyền, độ trễ lấy secret, số kết nối thành công và lỗi nghiệp vụ. Giữ bản cấu hình đã được phê duyệt để có thể phục hồi **theo quy trình**, nhưng không giữ khóa đã lộ còn hiệu lực chỉ để rollback nhanh.

### Bước 5: Đóng lỗ hổng và ngăn tái diễn

Thu hồi quyền và khóa cũ, đóng cổng công khai ngoài ý muốn, xóa các rule tạm, kiểm tra không có tuyến khác dẫn tới cùng dịch vụ. Bổ sung policy-as-code, kiểm tra drift, quét bí mật và cảnh báo thay đổi nhạy cảm; cập nhật runbook và ADR để nhóm khác không tái sử dụng cấu hình sai.

### 9.1. Khắc phục khác nhau giữa lỗi thiết kế và sự cố đã xảy ra

| Tình trạng | Cách xử lý |
|---|---|
| Phát hiện quyền rộng trong bản IaC chưa triển khai | Sửa policy, chạy kiểm thử âm/dương và chặn merge nếu chưa đạt |
| Phát hiện đường mạng công khai ngoài ý muốn trên sản xuất, chưa có dấu hiệu xâm nhập | Giới hạn đường truy cập theo mức độ rủi ro, xác minh luồng nghiệp vụ, xem lại log và cập nhật IaC |
| Credential nghi bị lộ hoặc có truy cập bất thường | Kích hoạt ứng phó sự cố, cô lập/thu hồi credential, bảo toàn chứng cứ, xác định phạm vi tác động và phục hồi |
| Đã có thay đổi dữ liệu không được phép | Dùng quy trình ứng phó dữ liệu, đối soát, phục hồi từ nguồn tin cậy khi phù hợp; xem xét nghĩa vụ thông báo |

Khắc phục sự cố không dừng ở việc “đóng cổng” hay “đổi password”. Cần xác định dữ liệu hoặc quyền đã bị sử dụng như thế nào, kiểm tra các danh tính liên quan và chứng minh cấu hình an toàn sau khi thay đổi.

## 10. Đánh đổi kiến trúc theo Well-Architected

Phản mẫu bảo mật thường nảy sinh từ mong muốn giảm bước triển khai, tiết kiệm thời gian hoặc tránh lỗi cấp quyền. Một thiết kế tốt phải giải thích rõ cách đạt bảo mật cùng các mục tiêu vận hành khác.

| Góc nhìn | Quyết định bảo mật | Lợi ích | Chi phí/đánh đổi cần quản lý |
|---|---|---|---|
| **Bảo mật** | Quyền tối thiểu theo workload và dữ liệu | Giảm phạm vi ảnh hưởng khi một danh tính bị chiếm | Cần kiểm thử và bảo trì policy |
| **Vận hành xuất sắc** | Identity federation, IaC, policy-as-code, drift detection | Giảm thao tác thủ công, ngăn cấu hình sai lặp lại | Cần chuẩn hóa danh tính, đào tạo đội ngũ và xử lý ngoại lệ |
| **Độ tin cậy** | Credential ngắn hạn và secret manager | Có thể thu hồi nhanh, xoay vòng chủ động | Phải thiết kế gia hạn token, cache an toàn và tình huống dịch vụ danh tính gián đoạn |
| **Hiệu quả hiệu năng** | Private endpoint, TLS, xác thực dịch vụ | Kiểm soát lưu lượng và danh tính liên dịch vụ | Có thể tăng độ phức tạp hoặc độ trễ kết nối; cần đo |
| **Tối ưu chi phí** | Phân vùng mạng, WAF, kiểm soát log và secret | Giảm khả năng phát sinh sự cố lớn | Một số điểm cuối riêng, WAF, log và dịch vụ quản lý có phí vận hành |
| **Bền vững** | Giảm tài nguyên và pipeline thừa, giữ dữ liệu phù hợp | Giảm tiêu thụ tài nguyên không cần thiết | Không cắt dự phòng hoặc kiểm soát an toàn cần thiết để tiết kiệm tài nguyên |

### 10.1. Tránh chuyển từ một cực đoan sang cực đoan khác

**Quyền chặt quá mức mà không kiểm thử** có thể làm tác vụ khóa sổ cuối tháng thất bại dù tác vụ hằng ngày vẫn hoạt động. Cần xem xét các chức năng chạy không thường xuyên và có đường xử lý lỗi rõ.

**Chặn tất cả đường ra ngoài** có thể khiến ứng dụng không gọi được nhà cung cấp thanh toán, OCSP hoặc dịch vụ thời gian/danh tính cần thiết. Định nghĩa egress theo phụ thuộc thật, sử dụng điểm cuối riêng hay proxy khi phù hợp và thử hành vi mất kết nối.

**Giảm thời gian sống credential vô điều kiện** có thể gây gián đoạn nếu phần mềm không gia hạn token hoặc môi trường chạy không lấy được danh tính mới. Phải thử quá trình hết hạn, làm mới, chạy song song và lỗi từ hệ danh tính.

**Mua nhiều công cụ quét** không thay thế trách nhiệm xử lý phát hiện. Cần chủ sở hữu, độ ưu tiên và thời hạn; cảnh báo phải đi đến người có khả năng sửa hệ thống.

## 11. Tình huống thực tế mô phỏng: hệ thống đặt hàng nhiều môi trường

### 11.1. Bối cảnh

Một nhóm chuyển ứng dụng đặt hàng từ máy ảo lên container đám mây. Ứng dụng có ba môi trường: development, staging và production. Các thành phần gồm API, worker, cơ sở dữ liệu, kho hóa đơn, CI/CD, hệ giám sát và cổng quản trị.

Đội triển khai ghi nhận:

- Pipeline triển khai dùng access key lâu hạn có quyền quản trị ở cả ba môi trường.
- Worker sử dụng chung credential với API và được quyền đọc nhiều bucket của hệ thống.
- Một ingress cấu hình theo mẫu mặc định đã phát hành trang quản trị worker ra Internet.
- Bucket hóa đơn có chính sách public read do từng dùng để thử hiển thị tệp.
- Hệ thống không có cảnh báo khi thay đổi policy IAM hoặc quy tắc mạng.

### 11.2. Phân tích vấn đề

| Phát hiện | Ranh giới bị vượt | Tác động có thể xảy ra | Ưu tiên khắc phục |
|---|---|---|---|
| Khóa CI/CD dài hạn, quản trị nhiều môi trường | Danh tính triển khai ↔ mọi tài nguyên | Lộ khóa có thể dẫn tới sửa/xóa diện rộng | Rất cao |
| API và worker chung credential | Chức năng API ↔ xử lý nền | Lỗi ở một thành phần ảnh hưởng quyền thành phần khác | Cao |
| Giao diện quản trị worker công khai | Internet ↔ mặt phẳng quản trị | Tăng bề mặt truy cập ngoài yêu cầu | Rất cao |
| Hóa đơn public read | Internet ↔ dữ liệu nghiệp vụ | Lộ dữ liệu khách hàng nếu object có thể truy cập vô danh | Rất cao |
| Thiếu audit/alert thay đổi quyền | Phát hiện ↔ ứng phó | Chậm nhận biết các thay đổi nguy hiểm | Cao |

Các mức ưu tiên là giả định cho ví dụ này. Cần xác nhận loại dữ liệu, quyền truy cập hiệu lực, truy cập thực tế, tác động pháp lý và bằng chứng log trước khi kết luận mức độ sự cố.

### 11.3. Thiết kế khắc phục

**Danh tính và quyền:** thay khóa CI/CD bằng liên kết danh tính theo phiên, với vai trò triển khai riêng cho production và staging. Tách role API khỏi role worker; mỗi role chỉ có quyền đối với các đối tượng dữ liệu cần thiết. Chỉ một vai trò được phê duyệt mới có thể thay đổi policy hoặc cấu hình mạng.

**Bí mật:** chuyển token đối tác vào kho bí mật. Runtime lấy token bằng workload identity, không đóng token vào image hoặc mã nguồn. Thiết lập rotation và cảnh báo sử dụng bất thường; thu hồi khóa cũ sau khi xác nhận hệ mới chạy ổn định. Với khóa có dấu hiệu bị lộ, thực hiện quy trình ứng phó sự cố trước.

**Mạng:** giữ public ingress cho API khách hàng; trang quản trị worker chỉ truy cập qua kênh quản trị được kiểm soát. DB và worker không có inbound Internet ngoài nhu cầu. Giới hạn nguồn kết nối bằng rule mạng; HTTPS công khai được bảo vệ bằng xác thực, giới hạn tốc độ và giám sát.

**Dữ liệu:** bật cơ chế chặn public access cho kho hóa đơn riêng tư, điều chỉnh resource policy và cách phát tệp qua API hoặc URL truy cập có thời hạn nếu nghiệp vụ cần tải xuống. URL có thời hạn không thay thế phân quyền tạo URL; dịch vụ phát URL phải xác minh người yêu cầu được xem đúng hóa đơn.

**Vận hành:** thiết lập báo động thay đổi IAM, trust policy, public route, secret access; thêm kiểm tra quyền và khả năng truy cập từ bên ngoài vào pipeline. Ghi ADR cho việc tách role và chọn kênh truy cập nội bộ.

### 11.4. Kiểm chứng nghiệm thu

Thiết kế chỉ được chấp nhận khi có bằng chứng:

1. Role API không thể đọc secret của worker và không thể thay đổi policy IAM; role worker không thể đọc dữ liệu ngoài phần hóa đơn được giao.
2. CI/CD từ nhánh hoặc môi trường không được tin cậy không thể nhận vai trò triển khai production; phiên hợp lệ vẫn triển khai được.
3. Không tìm thấy khóa sản xuất còn hiệu lực trong mã nguồn, image, artifact hoặc các vị trí đã rà soát; khóa cũ đã thu hồi và kiểm chứng không thể dùng.
4. Từ mạng ngoài tổ chức, chỉ public API đã duyệt trả lời; cổng DB, trang quản trị worker và các endpoint debug không có đường truy cập ngoài dự kiến.
5. Yêu cầu đọc hóa đơn không có danh tính bị từ chối; người dùng hợp lệ chỉ truy cập hóa đơn thuộc quyền của mình.
6. Thay đổi quyền hoặc public exposure tạo log và cảnh báo đến người trực; lỗi xác thực sau rotation được giám sát.
7. Hiệu năng đặt hàng, tỷ lệ giao dịch thành công và khả năng khôi phục không suy giảm ngoài ngưỡng đã thống nhất.

Với phát hiện thiếu log hoặc thay đổi cấu hình đã tồn tại lâu, báo cáo nghiệm thu phải ghi **giới hạn của bằng chứng**: “không phát hiện truy cập trái phép trong log còn lưu” không đồng nghĩa “chắc chắn chưa từng bị truy cập”.

## 12. Bài thực hành: rà soát một pull request hạ tầng

**Đề bài:** Nhóm của bạn chuẩn bị đưa chức năng gửi hóa đơn mới lên sản xuất. Họ đề xuất cấu hình minh họa:

~~~yaml
service: invoice-sender
deployment_identity: shared-admin-user
credential:
  kind: static-access-key
  source: container-environment-from-build
permissions:
  allowed_actions: ["*"]
  resources: ["*"]
ingress:
  enabled: true
  source_cidrs: ["0.0.0.0/0", "::/0"]
  ports: [8080, 22]
database:
  public_endpoint: true
  allowed_sources: ["0.0.0.0/0"]
logs:
  audit_enabled: false
~~~

Đây là **giả mã chứa các phản mẫu có chủ đích** để phân tích; không triển khai cấu hình này.

Hãy thực hiện:

1. Liệt kê ít nhất **sáu phát hiện**, phân loại theo IAM, credential, network và observability. Nêu tác động nghiệp vụ nếu dịch vụ bị truy cập trái phép.
2. Viết ma trận kết nối chỉ cho phép đường đi thật sự cần cho worker: queue → worker, worker → kho hóa đơn, worker → dịch vụ email và worker → log/metric.
3. Đề xuất danh tính cho worker, hành động và tài nguyên được phép; chỉ rõ **hai hành động phải bị từ chối** trong bài thử âm.
4. Thiết kế thay access key dài hạn bằng credential ngắn hạn; nếu dịch vụ email chỉ chấp nhận API key, mô tả nơi lưu, người quản lý và quy trình rotation.
5. Quyết định có cần inbound Internet cho worker không. Nếu không, chỉ rõ những rule và endpoint cần thu hồi; nếu có trường hợp ngoại lệ, chứng minh mục đích nghiệp vụ và kiểm soát tương ứng.
6. Đề xuất **năm phép kiểm tự động** và hai cảnh báo runtime để ngăn phản mẫu trở lại.
7. Nêu những rủi ro vận hành khi thu hẹp quyền hoặc rotation, cách thử trước triển khai và tiêu chí dừng.

### 12.1. Gợi ý lời giải

- Worker đọc queue, lấy thông tin hóa đơn được phân quyền, gọi API email và ghi trạng thái. Nó **không cần** quản trị toàn bộ đám mây, mở SSH từ Internet hoặc kết nối DB công khai.
- Sử dụng workload identity gắn riêng với invoice-sender ở production; chỉ cấp quyền queue consume, object read theo prefix, ghi log hoặc state theo nhu cầu được đo. Hai bài thử âm có thể là **xóa bucket khác** và **đọc bí mật thanh toán**: cả hai phải bị từ chối.
- Nếu không cần nhận webhook, thiết kế worker **không có ingress công khai**; việc worker kết nối outbound tới nhà cung cấp email không đồng nghĩa phải mở inbound từ Internet.
- DB dùng mạng riêng và chỉ cho các principal/luồng cần thiết. Nếu worker không truy cập DB trong kiến trúc mới, cần loại bỏ hoàn toàn quyền và rule kết nối đến DB.
- API key bên thứ ba được lưu trong secret manager, ràng buộc quyền đọc với workload, không xuất vào image, log hoặc báo cáo; có quy trình rotation và thu hồi.
- Các phép kiểm tự động có thể là: chặn vai trò quản trị của workload, chặn public DB, chặn cổng quản trị mở mọi nguồn, quét secret trong source/artifact, kiểm thử quyền đọc sai tài nguyên bị từ chối. Cảnh báo runtime gồm thay đổi IAM và thay đổi rule mạng dẫn đến public exposure.

### 12.2. Câu hỏi tư duy

**Nếu API key chỉ còn hiệu lực một giờ, đã an toàn chưa?** Chưa chắc. Token ngắn hạn nhưng có quyền đọc/xóa dữ liệu toàn tổ chức vẫn nguy hiểm trong một giờ đó. Đặt thời hạn cùng quyền hiệu lực, trust policy và khả năng phát hiện.

**Nếu DB chỉ có private IP, có cần IAM không?** Có. Private IP giảm đường truy cập mạng trực tiếp nhưng không ngăn truy cập sai quyền từ workload nằm trong cùng mạng hoặc từ dịch vụ đã bị chiếm quyền.

**Nếu mở cổng 443 ra 0.0.0.0/0, luôn phải chặn?** Không. Cổng 443 của public ingress được chủ đích phục vụ người dùng là trường hợp bình thường; cần xem endpoint, lớp bảo vệ, xác thực và dữ liệu liên quan. Quy tắc tương tự trên endpoint quản trị có thể không hợp lệ.

**Nếu cất secret trong secret manager, có thể bỏ rotation?** Không. Vẫn cần đánh giá tuổi thọ, quyền truy cập, khả năng thu hồi và yêu cầu của bên cung cấp; một số loại secret có cơ chế gia hạn tự động, loại khác cần kế hoạch thay theo phiên hoặc theo lịch.

## 13. Checklist kiến trúc trước khi đưa vào sản xuất

### Danh tính và phân quyền

- [ ] Mỗi workload và pipeline có danh tính, chủ sở hữu, môi trường và mục đích rõ ràng.
- [ ] Quyền được giới hạn theo hành động, tài nguyên và ngữ cảnh; các ngoại lệ quản trị có phê duyệt.
- [ ] Không tái sử dụng credential/role chung giữa môi trường hoặc hệ thống không có cùng phạm vi tin cậy.
- [ ] Trust policy và đường giả định vai trò đã được thử với cả principal được phép và không được phép.
- [ ] Các hành động đặc quyền, thay đổi IAM và thao tác dữ liệu nhạy cảm có nhật ký kiểm toán.

### Bí mật và thông tin xác thực

- [ ] Workload sử dụng danh tính được quản lý và credential ngắn hạn khi nền tảng hỗ trợ.
- [ ] Không có secret thật trong mã nguồn, container image, file cấu hình không bảo vệ, artifact hoặc log.
- [ ] Secret còn cần thiết có kho chuyên dụng, quyền đọc giới hạn, chủ sở hữu và vòng đời rõ ràng.
- [ ] Quy trình rotation/thu hồi được diễn tập; khóa cũ đã thu hồi sau khi chuyển đổi.
- [ ] Có cơ chế ứng phó khi phát hiện hoặc nghi ngờ credential lộ.

### Mạng và dữ liệu

- [ ] Danh sách public ingress đã được phê duyệt theo yêu cầu nghiệp vụ; admin và DB không công khai ngoài ý muốn.
- [ ] Luồng API, worker, DB, storage và đối tác có ma trận kết nối, bao gồm IPv4 và IPv6.
- [ ] Chính sách bucket/object và các endpoint dữ liệu được thử từ danh tính hợp lệ lẫn vô danh.
- [ ] WAF/gateway, xác thực, phân quyền và giới hạn lưu lượng được áp dụng tại điểm truy cập cần thiết.
- [ ] Đường truy cập trực tiếp vào origin không bỏ qua lớp bảo vệ đã thiết kế.

### Vận hành và kiểm chứng

- [ ] IaC, cấu hình runtime và policy-as-code không có drift nguy hiểm; thay đổi nhạy cảm có cảnh báo.
- [ ] Các bài thử âm chứng minh quyền ngoài phạm vi và đường truy cập không được phép bị chặn.
- [ ] Thu hẹp quyền, thay secret và đóng đường mạng đã được thử với hành trình nghiệp vụ quan trọng.
- [ ] Runbook, người trực, khả năng rollback an toàn và quy trình phản ứng sự cố đã được xác nhận.
- [ ] Các đánh đổi về chi phí, độ tin cậy, hiệu năng và bảo mật đã được ghi trong quyết định kiến trúc.

## 14. Ghi nhớ để đánh giá thiết kế

Khi đọc một bản thiết kế cloud, hãy đặt lần lượt ba câu hỏi:

1. **Ai được làm gì?** Không dừng ở tên role; kiểm tra quyền hiệu lực trên tài nguyên thực tế và khả năng chuyển tiếp quyền.
2. **Danh tính đó được chứng minh bằng gì và trong bao lâu?** Ưu tiên credential ngắn hạn theo workload; với secret bắt buộc, phải có kho an toàn, vòng đời và khả năng thu hồi.
3. **Ai có thể chạm tới giao diện này qua mạng?** Mở công khai chỉ cho đường đi nghiệp vụ được chấp nhận; mỗi lớp cần xác thực, phân quyền và quan sát tương ứng.

Kiến trúc an toàn không đòi hỏi mọi dịch vụ đều phải nằm sau một tường mạng kín, cũng không đòi hỏi loại bỏ mọi secret. Điều cần đạt là **quyền vừa đủ, credential được kiểm soát và đường truy cập có chủ đích**, được chứng minh qua kiểm thử và giám sát liên tục. Đó là nền tảng để mở rộng ứng dụng đám mây mà vẫn giữ được độ tin cậy, chi phí và khả năng vận hành theo mục tiêu Well-Architected.

# Vault folder và namespace

Trong Privileged Access Management (PAM), vault quản lý credential của tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. **Folder** và **namespace** giúp tổ chức các đối tượng đó, xác định phạm vi quản lý và gắn chính sách truy cập với những ranh giới rõ ràng.

Bài học thuộc chương **Vault**, tập trung vào cách thiết kế cấu trúc lưu trữ để hỗ trợ kiểm kê quyền, least privilege, truy cập đúng lúc (JIT), giới hạn thao tác, luân chuyển credential, giám sát phiên và lưu bằng chứng. Cấu trúc này cần phục vụ cả người quản trị lẫn workload sử dụng secret.

Các thuật ngữ folder và namespace không có một ngữ nghĩa kỹ thuật thống nhất giữa mọi sản phẩm. Trong một hệ thống, folder là đối tượng có ACL riêng; trong hệ thống khác, nó chỉ là các đoạn của đường dẫn. Namespace có thể là phạm vi cấu hình và phân quyền độc lập, nhưng cũng có thể chỉ là một nhãn phân loại. Luôn xác định cơ chế thực thi thực tế trước khi coi chúng là ranh giới bảo mật.

Sau bài học, bạn có thể:

- Phân biệt folder, namespace, đối tượng credential và đường dẫn tham chiếu.
- Chọn cấu trúc theo môi trường, chủ sở hữu và phạm vi rủi ro.
- Thiết kế quyền trên đối tượng và thao tác thay vì chỉ dựa vào tên thư mục.
- Kiểm chứng cô lập, quyền kế thừa, luân chuyển và việc di chuyển credential.
- Xác định bằng chứng cần lưu khi cấu trúc vault thay đổi.

## 1. Bốn khái niệm cần tách biệt

| Khái niệm | Vai trò | Điều không nên mặc định |
|---|---|---|
| Đối tượng credential hoặc secret | Chứa giá trị được bảo vệ hoặc tham chiếu tới cơ chế cấp credential | Mọi loại đối tượng đều có cùng thao tác đọc, dùng và luân chuyển |
| Folder | Nhóm các đối tượng theo cây hoặc theo các đoạn đường dẫn | Tạo folder tự động tạo ra ranh giới truy cập |
| Namespace | Xác định một phạm vi tên và có thể kèm phạm vi chính sách, danh tính hoặc cấu hình | Namespace luôn có khóa mã hóa, hạ tầng và quản trị viên độc lập |
| Đường dẫn hoặc tham chiếu | Định vị đối tượng trong ngữ cảnh cụ thể | Biết đường dẫn đồng nghĩa được phép đọc secret |

Một bản ghi tài khoản quản trị có thể bao gồm định danh tài nguyên, tên tài khoản, chủ sở hữu, chính sách luân chuyển và giá trị credential được mã hóa. Với credential động, đối tượng trong vault có thể mô tả role hoặc cơ chế cấp phát thay vì lưu sẵn một mật khẩu cố định.

Tên tài khoản, endpoint và quan hệ giữa hệ thống cũng có thể là thông tin nhạy cảm. Do đó, quyền xem metadata hoặc liệt kê folder cần được thiết kế riêng với quyền đọc giá trị secret.

## 2. Folder giải quyết bài toán tổ chức nào?

Folder giúp người vận hành tìm đúng đối tượng, áp dụng cách quản lý nhất quán và giảm nhầm lẫn khi có nhiều tài khoản hoặc tài nguyên.

Ví dụ minh họa:

```text
Namespace: prod-payments

/servers/linux/payment-api-01/service-operator
/servers/windows/payment-batch-01/maintenance-account
/databases/orders/application-runtime
/network/devices/edge-router-01/administrator
/automation/deployment/credential-reference
```

Đây là mô hình tên tham khảo, không phải cú pháp bắt buộc của một sản phẩm. Những đoạn cuối có thể là đối tượng, đường dẫn secret hoặc tham chiếu tùy cách triển khai.

Một cấu trúc hữu ích thường giúp trả lời nhanh:

- Đối tượng thuộc dịch vụ hoặc nhóm tài nguyên nào?
- Ai chịu trách nhiệm vận hành và xử lý khi credential lỗi?
- Đối tượng dành cho người quản trị hay workload?
- Chính sách truy cập và luân chuyển nào áp dụng?
- Có phải tài khoản khẩn cấp hoặc một ngoại lệ cần quản lý riêng không?

Không nên đưa giá trị secret, token hoặc thông tin cá nhân không cần thiết vào tên folder. Đường dẫn có thể xuất hiện trong log, thông báo lỗi, giao diện tìm kiếm và hồ sơ kiểm toán.

### Folder có thể có hoặc không có ACL

Nếu sản phẩm hỗ trợ ACL trên folder, cần biết ACL đó áp dụng cho folder, đối tượng con, metadata hay tất cả các loại thao tác. Nếu folder chỉ là tiền tố tên, việc phân quyền phải dựa vào cơ chế policy tương ứng.

Một folder tên `/restricted` không tự hạn chế truy cập. Ranh giới chỉ có ý nghĩa khi mọi đường đọc, ghi, cấp phát, export hoặc quản trị liên quan đều được kiểm soát.

## 3. Namespace bổ sung phạm vi quản lý

Namespace thường được dùng khi cần phân biệt các miền có cùng tên đối tượng nhưng khác chủ sở hữu hoặc chính sách. Ví dụ:

```text
Namespace prod-payments:
  /databases/orders/application-runtime

Namespace nonprod-payments:
  /databases/orders/application-runtime
```

Hai đường dẫn giống nhau vẫn có thể trỏ tới hai đối tượng khác nhau vì ngữ cảnh namespace khác nhau. Một tham chiếu đầy đủ cần đủ thông tin để phân biệt chúng.

### 3.1 Những khả năng cần xác minh

Tùy giải pháp, namespace có thể hỗ trợ một phần các khả năng sau:

- Phạm vi tên độc lập.
- Policy và ánh xạ danh tính riêng.
- Phương thức xác thực hoặc cấu hình tích hợp riêng.
- Delegation cho nhóm vận hành.
- Hạn mức, audit hoặc cấu hình vòng đời riêng.
- Quan hệ cha–con và một dạng kế thừa quản trị.

Không suy ra tất cả những khả năng này chỉ từ việc giao diện có mục “namespace”. Đặc biệt phải kiểm tra quản trị viên cấp cha, quản trị viên toàn hệ thống và quyền phục hồi backup có thể tác động tới namespace con đến mức nào.

### 3.2 Namespace không mặc nhiên là cô lập hạ tầng

Nhiều namespace có thể cùng dùng cụm vault, cơ sở dữ liệu, khóa hoặc dịch vụ khóa và nhóm vận hành nền tảng. Khi đó, chúng có thể tách quyền truy cập thông thường nhưng vẫn chia sẻ miền lỗi và các quyền quản trị cấp cao.

Nếu yêu cầu là cô lập hạ tầng, khóa, quản trị viên hoặc quy trình phục hồi, cần đánh giá kiến trúc triển khai phù hợp. Chỉ tách namespace có thể chưa đáp ứng được yêu cầu đó.

## 4. Chọn folder, namespace hay hệ thống tách biệt

| Nhu cầu | Hướng thiết kế có thể phù hợp | Kiểm tra bắt buộc |
|---|---|---|
| Nhóm credential cùng chính sách và chủ sở hữu | Folder trong cùng phạm vi quản lý | Quyền trên đối tượng và cách kế thừa |
| Tách production và non-production | Namespace riêng hoặc phạm vi tương đương có policy độc lập | Truy cập chéo, quyền cấp cha, credential tích hợp |
| Delegation cho nhiều nhóm sản phẩm | Namespace hoặc ranh giới quản trị tương đương theo nhóm | Nhóm được ủy quyền có thể tự mở rộng tới đâu |
| Tách khách hàng hoặc đơn vị có yêu cầu cô lập cao | Đánh giá namespace cùng các lớp bảo vệ bổ sung hoặc triển khai tách biệt | Hạ tầng, khóa, backup, quản trị và tác động khi bị xâm nhập |
| Giảm ảnh hưởng khi một cụm vault lỗi | Thiết kế HA/DR hoặc phân tách miền lỗi | Namespace không tự tạo dự phòng hạ tầng |

Không cần tạo namespace cho mọi folder. Phân mảnh quá nhiều làm tăng số lượng policy, cấu hình xác thực, bản ghi audit và công việc quản lý. Ngược lại, dồn toàn bộ credential vào một phạm vi có quyền rộng làm tăng hậu quả khi một danh tính hoặc policy bị xâm nhập.

Một tiêu chí thực tế là: **tạo ranh giới ở nơi chính sách, trách nhiệm hoặc mức rủi ro cần tách; dùng cấu trúc nhóm bên trong để hỗ trợ vận hành**.

## 5. Thiết kế cây theo những chiều ổn định

Có thể tổ chức theo môi trường, nhóm sở hữu, dịch vụ, loại tài nguyên hoặc mục đích tài khoản. Nên chọn ít chiều đủ để định vị và phân quyền, thay vì tạo cây quá sâu chứa mọi thông tin tài sản.

Ví dụ một mô hình:

```text
prod-payments                  ← namespace
├── servers                    ← folder nhóm tài nguyên
│   ├── linux
│   └── windows
├── databases
│   ├── orders
│   └── reporting
├── automation
└── emergency
```

Các metadata như owner, mã tài sản, loại tài khoản, mức nhạy cảm và chính sách luân chuyển có thể nằm trong hồ sơ đối tượng. Không nhất thiết biến tất cả thành các tầng đường dẫn.

### 5.1 Quy tắc đặt tên

- Dùng định danh nhất quán, có thể đối chiếu với tài nguyên và tài khoản thực tế.
- Tách production khỏi môi trường thử nghiệm bằng ranh giới chính sách rõ ràng.
- Hạn chế đổi tên chỉ vì thay đổi tên hiển thị của nhóm hoặc dự án.
- Xác định cách xử lý chữ hoa/thường, ký tự đặc biệt và trùng tên theo khả năng sản phẩm.
- Tránh tên quá chung như `admin1` mà không có ngữ cảnh tài nguyên.
- Không đặt secret hoặc dữ liệu nhạy cảm không cần thiết trong đường dẫn.

### 5.2 Một tài khoản đích cần nguồn quản lý có thẩm quyền

Nếu cùng một tài khoản máy chủ được lưu thành nhiều đối tượng trong nhiều namespace, hai bộ luân chuyển có thể cùng thay mật khẩu và làm các bản ghi lệch nhau.

Nên xác định một nguồn quản lý credential có thẩm quyền cho tài khoản đích. Nếu nhiều nhóm cần sử dụng, dùng cơ chế cấp quyền, tham chiếu hoặc broker được kiểm soát nếu giải pháp hỗ trợ. Việc tạo bản sao giá trị secret để chia sẻ thường làm tăng số nơi phải thu hồi, kiểm kê và cập nhật.

## 6. Gắn danh tính với tài nguyên và thao tác

Một quyết định truy cập có thể được biểu diễn như sau:

```text
Chủ thể
  + namespace
  + đối tượng hoặc tập đối tượng
  + thao tác
  + điều kiện
  → cho phép hoặc từ chối
```

- **Chủ thể:** người dùng, nhóm, workload hoặc dịch vụ nội bộ PAM đã xác thực.
- **Namespace:** ngữ cảnh quản lý mà yêu cầu đang nhắm tới.
- **Đối tượng:** credential, metadata, role cấp phát hoặc cấu hình.
- **Thao tác:** liệt kê, đọc, dùng qua broker, tạo, sửa, luân chuyển, xóa hoặc quản lý policy.
- **Điều kiện:** thời hạn, MFA, phê duyệt, tài nguyên đích hoặc các thuộc tính được hệ thống hỗ trợ và kiểm chứng.

Tên thao tác và mức chi tiết khác nhau theo sản phẩm. Không phải giải pháp nào cũng tách được quyền “dùng credential mà không đọc giá trị”. Nếu có khả năng này, vẫn phải kiểm tra người dùng không có một API, chức năng export hoặc đường quản trị khác để lấy secret.

### Ma trận quyền tham chiếu

| Vai trò | Nhu cầu | Phạm vi hạn chế |
|---|---|---|
| Người vận hành qua session proxy | Sử dụng tài khoản đích cho công việc được duyệt | Chỉ nhóm tài nguyên cần thiết; không mặc nhiên được xem secret |
| Workload ứng dụng | Đọc secret cần thiết hoặc nhận credential động | Một dịch vụ và môi trường; không có quyền liệt kê toàn bộ vault |
| Worker luân chuyển | Cập nhật credential ở đích và trong kho theo workflow | Chỉ tập tài khoản được quản lý; bảo vệ danh tính worker |
| Người quản lý cấu trúc | Tạo hoặc sửa folder và metadata theo trách nhiệm | Không tự mở rộng sang policy hoặc lấy secret qua thao tác di chuyển |
| Người quản lý policy | Thiết kế và thay đổi quyền theo quy trình | Đây là quyền nhạy cảm vì có thể dẫn đến cấp quyền truy cập secret |
| Người kiểm toán | Đọc sự kiện và metadata cần cho đối soát | Không mặc nhiên được đọc giá trị credential hoặc toàn bộ bản ghi nhạy cảm |

Tách vai trò trong tên gọi chưa đủ tạo sự phân tách nhiệm vụ. Ví dụ, một quản trị viên không có quyền đọc secret nhưng được tự sửa policy để cấp quyền đọc cho mình vẫn có khả năng tiếp cận secret một cách gián tiếp.

## 7. Quyền kế thừa và quản trị cấp cha

Cây folder hoặc namespace có thể dùng quyền kế thừa, nhưng quy tắc cụ thể phải được xác minh:

- Quyền ở cha có tự áp dụng cho con không?
- Quyền cho phép và từ chối được kết hợp theo nguyên tắc nào?
- Có thể ngắt kế thừa tại con không?
- Khi di chuyển đối tượng, quyền được tính lại hay giữ nguyên?
- Chủ thể có được truy cập bằng một tham chiếu trực tiếp dù không được liệt kê folder không?
- Quản trị viên cấp cha có thể thay policy hoặc tạo danh tính trong phạm vi con không?

Không giả định “deny luôn thắng” hoặc “quyền ở con luôn thay quyền ở cha” nếu chưa biết mô hình của giải pháp.

### Ví dụ quyền rộng ở cha

Nhóm `operations` được đọc mọi đối tượng dưới `/servers`. Một folder `/servers/linux/payment-api-01` được tạo cho công việc riêng của nhóm thanh toán. Nếu quyền cha tiếp tục được kế thừa, credential mới có thể được nhóm `operations` đọc dù người tạo chỉ dự định chia sẻ cho nhóm thanh toán.

Giải pháp không chỉ là đặt tên folder chi tiết hơn. Cần sửa phạm vi quyền, cơ chế kế thừa hoặc ranh giới namespace, sau đó kiểm chứng quyền hiệu lực của các nhóm liên quan.

### Metadata và quyền liệt kê

Một workload có thể cần đọc một secret cụ thể nhưng không cần liệt kê tên các secret khác. Khả năng đọc trực tiếp và khả năng list có thể độc lập tùy sản phẩm.

Ngược lại, cho phép list có thể làm lộ cấu trúc tài nguyên dù không cho đọc giá trị. Cần xem cả giao diện người dùng, API metadata, tìm kiếm, lịch sử phiên bản và chức năng export khi đánh giá mức lộ thông tin.

## 8. Đường dẫn và ngữ cảnh namespace phải rõ ràng

### 8.1 Tham chiếu đầy đủ

Một hồ sơ tích hợp có thể giữ các thành phần như sau:

```text
vault_reference: primary-pam-vault
namespace: prod-payments
object_reference: databases/orders/application-runtime
object_id: một định danh ổn định do hệ thống cấp nếu có
```

Đây là các trường minh họa. Một giải pháp có thể dùng ID đối tượng, đường dẫn hoặc cơ chế khác. Nếu hỗ trợ định danh ổn định, cần hiểu nó có còn hiệu lực khi đổi tên hoặc di chuyển đối tượng hay không.

Client không nên tự chọn namespace mặc định khi thiếu ngữ cảnh bắt buộc. Với những tên đối tượng giống nhau giữa production và non-production, fallback im lặng có thể lấy nhầm credential hoặc cấp quyền sai môi trường.

### 8.2 Xác thực namespace không thay thế phân quyền

Việc client gửi tên namespace chỉ cho biết phạm vi yêu cầu. Hệ thống vẫn phải xác minh danh tính và quyền cho phạm vi đó. Không được tin rằng người dùng chọn được namespace trên giao diện thì đã có quyền với mọi đối tượng bên trong.

Danh tính hoặc token cũng cần đúng ngữ cảnh và giới hạn theo cơ chế sản phẩm. Cần kiểm tra điều gì xảy ra khi token từ một phạm vi được gửi sang phạm vi khác, thay vì giả định mọi token đều bị giới hạn như nhau.

### 8.3 So khớp đường dẫn phải theo cấu trúc

Một policy dựa trên chuỗi cần phân biệt đúng đối tượng, phần tử con và tên gần giống. Ví dụ, quyền cho cây `payment` không nên vô tình bao phủ cây `payment-archive` chỉ vì cùng bắt đầu bằng một chuỗi ký tự.

Khi triển khai hoặc kiểm chứng, cần xét quy tắc chuẩn hóa, dấu phân cách, ký tự mã hóa, alias và cách phân biệt chữ hoa/thường. Nên sử dụng cơ chế phân quyền gốc của nền tảng với ngữ nghĩa rõ ràng, thay vì tự tạo bộ kiểm tra tiền tố đơn giản trong một client.

Đường dẫn API cho dữ liệu, metadata, phiên bản hoặc cấu hình có thể khác nhau. Một mẫu policy nhìn đúng đối với API đọc dữ liệu có thể chưa kiểm soát thao tác xóa phiên bản hoặc truy xuất metadata. Phải ánh xạ tới những endpoint và thao tác thực sự được sử dụng.

## 9. Ví dụ chính sách cho nhóm thanh toán

Giả sử nhóm thanh toán có môi trường production và thử nghiệm. Ứng dụng chỉ cần credential cơ sở dữ liệu của chính nó; người vận hành cần mở phiên vào một nhóm máy; worker luân chuyển quản lý credential đã chỉ định.

### 9.1 Cấu trúc mong muốn

```text
prod-payments
├── databases/orders/application-runtime
├── servers/linux/payment-api-01/service-operator
└── emergency/platform-recovery

nonprod-payments
├── databases/orders/application-runtime
└── servers/linux/payment-api-test-01/service-operator
```

Tài khoản khẩn cấp có thể cần cơ chế phục hồi độc lập với những phụ thuộc chính của PAM. Đặt nó trong folder `emergency` chỉ hỗ trợ phân loại; khả năng sử dụng khi vault lỗi và cách bảo vệ vật liệu phục hồi vẫn cần được thiết kế riêng.

### 9.2 Chính sách minh họa

Đoạn sau mô tả ý định, không phải cú pháp policy của một sản phẩm vault:

```yaml
policy_model:
  default_decision: deny
  grants:
    - subject_reference: payments-runtime-production
      namespace: prod-payments
      resource_reference: databases/orders/application-runtime
      operations:
        - obtain_application_credential
    - subject_reference: payments-production-operators
      namespace: prod-payments
      resource_reference: servers/linux/payment-api-01/service-operator
      operations:
        - use_via_session_broker
      conditions:
        approval_required: true
        mfa_required: true
        maximum_access_minutes: 30
    - subject_reference: payments-credential-rotation-worker
      namespace: prod-payments
      resource_reference: databases/orders/application-runtime
      operations:
        - rotate_managed_credential
```

Các thao tác trên chỉ là tên logic. Khi triển khai, cần dịch sang quyền thực tế, phân biệt loại credential và kiểm tra liệu sản phẩm có hỗ trợ tách chúng hay không. Điều kiện MFA dành cho người dùng cũng không được áp dụng máy móc cho workload; workload cần cơ chế xác thực phù hợp với danh tính máy.

### 9.3 Những gì chính sách này chưa chứng minh

Cần xác nhận ứng dụng không có quyền bổ sung qua nhóm khác, người vận hành không có đường export credential, worker không được sửa policy ngoài trách nhiệm và các danh tính non-production không thể sử dụng phạm vi production.

Đồng thời, quyền tài khoản ở máy chủ hoặc cơ sở dữ liệu phải tối thiểu. Chỉ giới hạn đường lấy credential không làm tài khoản đích bớt quyền. JEA hoặc cơ chế hạn chế hành động ở đích cần được thiết kế riêng khi cần.

## 10. Vòng đời đối tượng và ảnh hưởng của cấu trúc

### 10.1 Tạo mới

Trước khi thêm một credential, xác định tài nguyên đích, tài khoản, chủ sở hữu, namespace, chính sách truy cập, bên sử dụng và cơ chế luân chuyển. Kiểm tra quyền hiệu lực ở vị trí sẽ đặt đối tượng trước khi đưa secret vào.

Có thể chuẩn bị metadata trước rồi tiếp nhận secret bằng một luồng được bảo vệ. Không dùng một vị trí rộng quyền như nơi trung chuyển mặc định cho mọi credential mới nếu đối tượng có thể bị đọc trong thời gian chờ di chuyển.

### 10.2 Luân chuyển

Worker cần biết đối tượng nào gắn với tài khoản đích nào và công việc nào đang có thẩm quyền thực hiện thay đổi. Việc đổi folder không được làm mất ánh xạ, lịch luân chuyển hoặc trạng thái công việc đang dở.

Luân chuyển mật khẩu phải phối hợp với máy đích và bên sử dụng. Một phiên bản mới trong vault chưa chứng minh mật khẩu đã đổi thành công ở đích; ngược lại, đổi ở đích nhưng chưa ghi nhận được ở vault có thể gây lệch trạng thái.

### 10.3 Đổi tên hoặc di chuyển

Di chuyển credential có thể làm thay đổi:

- Quyền kế thừa và nhóm được truy cập.
- Đường dẫn mà ứng dụng, proxy hoặc worker sử dụng.
- Ngữ cảnh namespace và danh tính tích hợp.
- Lịch sử phiên bản, ID đối tượng hoặc tham chiếu audit tùy giải pháp.
- Quyền truy cập qua alias, cache và bản sao còn tồn tại.

Không coi thao tác di chuyển là một thay đổi giao diện đơn thuần. Cần kiểm tra trước và sau cả khả năng sử dụng lẫn phạm vi người có thể sử dụng.

### 10.4 Xóa hoặc ngừng quản lý

Xóa bản ghi không mặc nhiên vô hiệu credential ở đích. Nếu một người đã sao chép mật khẩu hoặc access key, họ có thể tiếp tục sử dụng cho tới khi credential bị thay, thu hồi hoặc hết hiệu lực theo cơ chế thực tế.

Khi ngừng quản lý, cần xử lý tài khoản đích, quyền, credential, bên phụ thuộc, bản sao và bằng chứng theo kế hoạch. Việc xóa mềm, phục hồi hoặc hủy vĩnh viễn phiên bản cũng có ngữ nghĩa khác nhau theo sản phẩm và phải được phân quyền riêng khi cần.

## 11. Di chuyển credential từ cấu trúc cũ

Giả sử trước đây credential production và thử nghiệm đều nằm trong `/shared/payments`. Tổ chức muốn tách sang `prod-payments` và `nonprod-payments`.

Một quy trình tham chiếu:

1. **Lập danh mục:** xác định tài khoản đích, môi trường, chủ sở hữu, phiên bản và bên sử dụng của từng đối tượng.
2. **Thiết kế đích:** tạo phạm vi và policy mới, kiểm tra quyền hiệu lực trước khi đưa credential vào.
3. **Chọn cơ chế chuyển:** hiểu rõ move có giữ ID/lịch sử hay copy tạo đối tượng độc lập; kiểm soát việc truy cập cả nguồn và đích trong thời gian chuyển.
4. **Phối hợp công việc đang chạy:** tránh để hai worker cùng luân chuyển một tài khoản hoặc proxy tiếp tục dùng tham chiếu cũ ngoài kế hoạch.
5. **Cập nhật bên sử dụng:** thay tham chiếu cho ứng dụng, session broker và automation theo cửa sổ đã chọn.
6. **Kiểm chứng:** thử truy cập hợp lệ, truy cập chéo bị cấm, khả năng luân chuyển và liên kết audit.
7. **Thu hẹp cấu trúc cũ:** loại bỏ quyền, alias hoặc bản sao không còn cần thiết; xử lý credential đã từng lộ cho nhóm rộng hơn.
8. **Bàn giao:** ghi nhận nguồn quản lý mới, ngoại lệ, điều kiện rollback và người chịu trách nhiệm.

Nếu secret đã từng được chia sẻ rộng, chuyển nó sang namespace hạn chế không khiến người đã biết secret quên giá trị đó. Cần đánh giá luân chuyển hoặc thu hồi, đồng thời cập nhật bên dùng để không gây gián đoạn ngoài dự kiến.

Rollback cũng cần xét trạng thái credential ở đích. Khôi phục đường dẫn cũ nhưng dùng một giá trị đã hết hiệu lực sẽ không phục hồi được dịch vụ; khôi phục credential từng bị lộ có thể tái tạo rủi ro.

## 12. Audit, phiên bản và quyền quản trị gián tiếp

### 12.1 Sự kiện cần quan sát

Nên xác định các sự kiện quan trọng theo khả năng của hệ thống:

- Tạo, đổi tên, di chuyển hoặc xóa folder và namespace.
- Thay policy, quyền kế thừa, nhóm và ánh xạ danh tính.
- Đọc metadata, liệt kê và truy xuất giá trị hoặc phiên bản secret.
- Cấp credential động, dùng qua broker và luân chuyển.
- Export, backup, restore và truy cập bằng quyền khẩn cấp.
- Thay cấu hình audit, xác thực hoặc kết nối tới hệ thống khóa.

Mỗi sự kiện cần đủ ngữ cảnh để xác định ai, thao tác gì, trên đối tượng nào, thuộc namespace nào, khi nào và kết quả ra sao. Dùng ID ổn định khi có để liên kết sau thay đổi tên.

Không đưa secret, token hoặc private key vào audit. Tên đường dẫn cũng cần được xử lý theo mức nhạy cảm vì có thể tiết lộ cấu trúc hạ tầng.

### 12.2 Đọc phiên bản cũ cũng là đọc secret

Một policy cấm đọc giá trị hiện tại nhưng cho truy xuất lịch sử có thể vẫn làm lộ credential còn dùng được hoặc thông tin nhạy cảm. Cần xét quyền theo phiên bản, export và phục hồi, không chỉ endpoint đọc thông thường.

Việc giữ phiên bản cũ có thể phục vụ khôi phục nhưng không đồng nghĩa credential cũ vẫn được phép sử dụng. Vòng đời dữ liệu trong vault và hiệu lực credential ở đích cần được theo dõi riêng.

### 12.3 Backup và quản trị nền tảng

Namespace tách biệt trên giao diện có thể cùng nằm trong một bản backup. Quyền export hoặc restore có thể vượt ranh giới mà người dùng thông thường nhìn thấy.

Cần bảo vệ bản backup, khóa giải mã, tài khoản phục hồi và nơi thử restore. Khôi phục dữ liệu cũ có thể đưa trở lại policy hoặc quyền đã bị thu hồi; sau phục hồi phải đối soát với trạng thái hiện tại ở đích và nguồn danh tính.

Một cơ chế phân tách nhiệm vụ đáng tin cậy phải xét cả quyền thay policy, lấy khóa, phục hồi backup và thay audit. Chặn nút xem mật khẩu trên giao diện chưa đủ khi các quyền gián tiếp vẫn còn rộng.

## 13. Tình huống lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Hướng xử lý |
|---|---|---|
| Tạo folder mới nhưng nhóm không liên quan vẫn đọc được | Quyền rộng ở cha hoặc policy khác cùng áp dụng | Kiểm tra quyền hiệu lực và mô hình kết hợp policy |
| Workload lấy nhầm secret của môi trường khác | Namespace mặc định hoặc tham chiếu thiếu ngữ cảnh | Ràng buộc phạm vi và kiểm chứng danh tính tài nguyên |
| Đổi tên folder làm ứng dụng lỗi | Client dùng đường dẫn cố định hoặc alias chưa cập nhật | Cập nhật tham chiếu, kiểm tra các bên phụ thuộc |
| Mật khẩu đổi liên tục rồi xác thực thất bại | Cùng tài khoản đích bị nhiều đối tượng hoặc worker quản lý | Chọn nguồn quản lý có thẩm quyền, đối soát trạng thái và phối hợp luân chuyển |
| Không đọc được secret nhưng vẫn thấy toàn bộ tên tài khoản | Quyền list/search hoặc metadata quá rộng | Giới hạn thao tác khám phá theo nhu cầu |
| Người không đọc secret trực tiếp vẫn tự lấy được | Có quyền sửa policy, export, restore hoặc quản trị khác | Sửa phân tách nhiệm vụ và audit quyền gián tiếp |
| Di chuyển xong nhưng người cũ vẫn dùng được | Credential đã bị sao chép, token hoặc phiên còn hiệu lực | Thu hồi hoặc luân chuyển và xử lý phiên theo khả năng thực tế |
| Namespace bị bỏ quên sau đổi cơ cấu nhóm | Thiếu owner hoặc quy trình chuyển giao | Rà soát chủ sở hữu, quyền và nghĩa vụ vận hành |

Một kết quả “không tìm thấy” có thể là đối tượng thực sự không tồn tại hoặc cơ chế che giấu do không có quyền. Khi điều tra, dùng dữ liệu quản trị và audit được phép thay vì tự mở rộng quyền của client để thử.

## 14. Bài thực hành kiểm chứng cấu trúc

Trong môi trường lab được phép, tạo hai phạm vi minh họa cho production và non-production, dùng dữ liệu giả không có giá trị truy cập hệ thống thật. Chuẩn bị một danh tính ứng dụng, một người vận hành, một worker và một người kiểm toán.

### Các tình huống cần kiểm tra

| Tình huống | Kết quả mong muốn theo thiết kế |
|---|---|
| Ứng dụng production lấy đối tượng được cấp | Chỉ nhận credential hoặc kết quả cấp phát cần thiết |
| Danh tính non-production truy cập production | Bị từ chối ở cơ chế phân quyền, không chỉ bị ẩn trên giao diện |
| Ứng dụng thử liệt kê toàn namespace | Chỉ có khả năng khám phá đã được cấp, không lộ cấu trúc ngoài nhu cầu |
| Người vận hành dùng qua broker | Có phiên gắn với yêu cầu; không tự có quyền đọc secret qua đường khác |
| Worker xử lý đối tượng ngoài tập được quản lý | Không thể thay credential hoặc metadata ngoài phạm vi |
| Tạo folder con mới | Quyền hiệu lực khớp quy tắc kế thừa dự kiến |
| Dùng tên gần giống hoặc ngữ cảnh namespace khác | Không vô tình khớp policy của đối tượng được phép |
| Đổi tên hoặc di chuyển một đối tượng | Bên dùng và quyền được cập nhật, audit vẫn liên kết được |
| Thu hồi nhóm hoặc quyền truy cập | Kiểm chứng tác động theo thời gian đồng bộ, token và phiên thực tế |
| Đọc lịch sử, export hoặc restore | Chỉ vai trò đã được thiết kế mới thực hiện được |

Khi thử thu hồi, cần phân biệt từ chối yêu cầu mới với việc chấm dứt một phiên đã mở. Thay ACL ở vault có thể ngăn lần lấy secret tiếp theo nhưng không tự đóng phiên ở tài nguyên đích hoặc vô hiệu credential đã được sao chép.

### Bằng chứng nên giữ từ lab

Ghi nhận cấu trúc, policy, các danh tính kiểm tra, đối tượng giả, kết quả cho phép/từ chối và sự kiện audit liên quan. Không lưu secret thật trong ảnh chụp hoặc đầu ra kiểm thử. Các tình huống trên là hướng dẫn thực hành, không phải báo cáo rằng một hệ thống cụ thể đã được kiểm thử.

## 15. Điều kiện để bàn giao vận hành

Một cấu trúc folder và namespace sẵn sàng bàn giao khi người vận hành có thể xác định:

- Chủ sở hữu và mục đích của từng phạm vi quan trọng.
- Nguồn quản lý có thẩm quyền cho mỗi tài khoản đích.
- Danh tính nào được list, đọc, dùng, sửa, luân chuyển, xóa và quản lý policy.
- Quyền cấp cha, quyền gián tiếp và những lớp cô lập thực sự tồn tại.
- Cơ chế JIT, giới hạn thao tác ở đích và xử lý credential sau phiên khi áp dụng.
- Bên phụ thuộc cần cập nhật khi đối tượng đổi tên, di chuyển hoặc luân chuyển.
- Cách truy vết thay đổi cấu trúc, khôi phục dữ liệu và rà soát quyền sau restore.
- Cách phát hiện credential mồ côi, bản sao trùng, quyền quá rộng và namespace không còn người chịu trách nhiệm.

Cấu trúc vault cần được rà soát khi tài nguyên, tổ chức và ứng dụng thay đổi. Folder hỗ trợ tổ chức; namespace có thể hỗ trợ phân chia phạm vi; các chính sách và cơ chế thực thi mới quyết định ai thực sự tiếp cận được credential và sử dụng đặc quyền đó tới đâu.

# Service identity — danh tính của dịch vụ

**Service identity** là danh tính dùng để nhận diện một dịch vụ phần mềm khi nó giao tiếp với hệ thống khác. Danh tính này đại diện cho chủ thể máy thực hiện công việc, không phải tài khoản cá nhân của lập trình viên, địa chỉ IP hiện tại hay tên được dịch vụ tự khai trong request.

Trong IAM, service identity giúp trả lời ba câu hỏi: dịch vụ nào đang gọi, nó chứng minh danh tính bằng cách nào, và nó được phép thực hiện hành động gì trên tài nguyên nào. Khi các câu hỏi này được giải quyết riêng, hệ thống có thể áp dụng nguyên tắc ít quyền nhất, kiểm toán theo dịch vụ và thay credential mà không phải thay toàn bộ chính sách truy cập.

## 1. Ví dụ: dịch vụ đơn hàng gọi dịch vụ tồn kho

Một hệ thống thương mại có `order-api`, `inventory-api` và `reporting-worker`. Khi tạo đơn hàng, `order-api` cần yêu cầu `inventory-api` giữ chỗ hàng tồn kho. `reporting-worker` chỉ cần đọc dữ liệu phục vụ báo cáo.

```text
order-api
    | danh tính đã xác minh + yêu cầu giữ chỗ
    v
inventory-api
    | xác định bên gọi là order-api
    | kiểm tra quyền inventory:reserve
    v
Cho phép giữ chỗ trong phạm vi chính sách

reporting-worker
    | yêu cầu giữ chỗ bằng danh tính riêng
    v
inventory-api -> từ chối nếu không được cấp quyền tương ứng
```

Nếu cả ba dịch vụ dùng chung một secret “backend-admin”, `inventory-api` chỉ biết người gọi có secret đó, khó phân biệt ứng dụng nào thật sự thực hiện hành động. Một dịch vụ báo cáo bị xâm nhập cũng có thể mang theo quyền dành cho dịch vụ xử lý đơn hàng.

Service identity cho phép tách chủ thể và quyền. `order-api` có quyền giữ chỗ theo nhu cầu nghiệp vụ; `reporting-worker` có quyền đọc phù hợp; không dịch vụ nào nhận quyền quản trị chỉ vì nằm trong mạng nội bộ.

## 2. Phân biệt danh tính, credential và quyền

Ba thành phần liên quan nhưng không đồng nhất:

| Thành phần | Ý nghĩa | Ví dụ trong bài |
|---|---|---|
| Danh tính/Principal | Chủ thể nào đang được nhận diện | `order-api` thuộc môi trường production |
| Credential/bằng chứng | Dữ liệu và cơ chế để chứng minh danh tính | Chứng thư cùng việc chứng minh giữ khóa riêng, hoặc token hợp lệ |
| Chính sách phân quyền | Chủ thể được làm gì và trong điều kiện nào | Được gọi thao tác giữ chỗ của `inventory-api` |

Tên principal không phải bí mật. Biết định danh `order-api` không được đủ để giả mạo dịch vụ. Chứng thư công khai cũng không phải khóa riêng: khi xác thực dựa trên chứng thư, bên gọi phải chứng minh sở hữu khóa tương ứng theo giao thức.

Ngược lại, một bearer token bị lấy cắp có thể được sử dụng bởi người giữ nó trong phạm vi token còn được chấp nhận, nếu không có ràng buộc bên gửi bổ sung. Vì vậy, gọi token là “danh tính” trong hội thoại không làm mất nghĩa vụ bảo vệ credential.

Danh tính thường ổn định qua nhiều lần triển khai; credential có thể được cấp mới và thay thường xuyên. Khi một chứng thư của `order-api` hết hạn và được thay bằng chứng thư khác cho cùng principal, các quyền nghiệp vụ không cần tự động đổi theo số serial của chứng thư.

## 3. Danh tính dịch vụ khác những định danh nào?

| Định danh hoặc khái niệm | Nó mô tả điều gì? | Vì sao không tự thay cho service identity? |
|---|---|---|
| Tài khoản người dùng | Con người đăng nhập hoặc thực hiện nghiệp vụ | Dịch vụ tự chạy không nên phụ thuộc credential cá nhân |
| Danh tính host/node | Máy hoặc node chạy phần mềm | Một node có thể chạy nhiều dịch vụ với quyền khác nhau |
| Pod/container ID | Một lần thực thi cụ thể | Thay đổi khi restart hoặc scale; không nhất thiết là principal chính sách lâu dài |
| IP hoặc subnet | Vị trí mạng của kết nối | Địa chỉ có thể thay đổi, dùng chung hoặc đi qua proxy |
| DNS/service endpoint | Nơi định tuyến tới dịch vụ | Tên được tìm thấy không tự chứng minh bên đang phục vụ là đối tác tin cậy |
| Tài khoản dịch vụ | Một đối tượng tài khoản cho phần mềm trong nền tảng | Còn cần credential, ánh xạ tin cậy và quyền tại hệ thống đích |
| Kubernetes Service | Đối tượng mạng để truy cập một tập backend | Không đồng nghĩa đối tượng ServiceAccount hay bằng chứng xác thực |

Phân tách này đặc biệt quan trọng khi nhiều workload cùng chạy trên một máy. Nếu mọi workload nhận cùng quyền từ danh tính node, dịch vụ có nhu cầu thấp có thể thừa hưởng quyền của dịch vụ có nhu cầu cao.

Con người vẫn có trách nhiệm quản trị service identity. Nhóm sở hữu cần phê duyệt quyền, xử lý sự cố và ngừng sử dụng danh tính khi dịch vụ bị loại bỏ. Tuy nhiên, người sở hữu quản trị không phải chủ thể mà dịch vụ dùng để gọi API.

## 4. Chọn phạm vi danh tính phù hợp

Một quy ước định danh có thể chứa miền tin cậy, môi trường, namespace và dịch vụ. Ví dụ minh họa theo cấu trúc SPIFFE:

```text
Production:
spiffe://prod.example/ns/orders/sa/order-api

Staging:
spiffe://stage.example/ns/orders/sa/order-api
```

[SPIFFE Concepts](https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/) mô tả SPIFFE ID là URI nhận diện workload trong một trust domain; SVID là tài liệu có thể xác minh bằng mật mã để workload chứng minh danh tính. X.509-SVID và JWT-SVID là các dạng bằng chứng liên quan. SPIFFE ID và SVID không phải cùng một đối tượng.

Đường dẫn `ns/orders/sa/order-api` ở trên là quy ước của ví dụ. Không phải mọi service identity đều cần SPIFFE, cũng không phải Kubernetes tự sinh ánh xạ SPIFFE này mà không cấu hình hạ tầng tương ứng.

### 4.1. Tách theo dịch vụ và môi trường

Danh tính của `order-api` không nên được dùng chung cho `reporting-worker` nếu hai thành phần có quyền và vòng đời khác nhau. Danh tính staging cũng không được mặc nhiên có quyền production chỉ vì cùng tên dịch vụ.

Cần kiểm tra đầy đủ phạm vi tin cậy. Nếu chỉ so đoạn cuối `order-api`, hệ thống có thể bỏ qua sự khác biệt giữa trust domain production và staging.

### 4.2. Danh tính logic và nhiều replica

Nhiều replica cùng thực hiện một vai trò có thể dùng cùng service identity logic, trong khi mỗi replica nhận credential riêng theo cơ chế cấp phát. Cách này giữ chính sách ổn định khi scale mà không buộc chia sẻ cùng một khóa riêng được sao chép cho mọi instance.

Khi cần điều tra một instance cụ thể, log có thể bổ sung deployment, pod/instance ID, phiên bản phần mềm và dấu nhận diện credential. Những thông tin này hỗ trợ truy vết; không tự trở thành quyền chỉ vì xuất hiện trong log hay header.

Nếu hai nhóm instance cần quyền khác nhau, phải xem lại ranh giới principal. Một service identity quá rộng sẽ khiến việc thu hồi một bộ phận hoặc giới hạn tác động sự cố trở nên khó khăn.

## 5. Dịch vụ được nhận credential bằng cách nào?

Một chuỗi tin cậy cần giải quyết cả việc cấp phát ban đầu, không chỉ xác minh request sau đó:

```text
Workload khởi chạy
    -> nền tảng xác minh ngữ cảnh thực thi
    -> đối chiếu chính sách cấp danh tính
    -> cấp credential cho principal phù hợp
    -> workload dùng credential gọi hệ thống đích
    -> hệ thống đích xác thực và phân quyền
```

Thông tin tự khai như biến môi trường `SERVICE_NAME=order-api` không đủ làm bằng chứng. Nếu mọi container đều có thể tự đổi biến đó để nhận quyền của `order-api`, cơ chế cấp danh tính đã đánh mất ranh giới tin cậy.

Một triển khai có thể dựa trên thông tin do nền tảng đáng tin cung cấp, như node được xác thực, namespace, tài khoản dịch vụ gắn workload và thuộc tính tiến trình. Ai được sửa deployment, chọn ServiceAccount hoặc thay thuộc tính được dùng để cấp danh tính cũng nằm trong phạm vi kiểm soát bảo mật.

[SPIRE Concepts](https://spiffe.io/docs/latest/spire-about/spire-concepts/) là một ví dụ cụ thể: registration entry ánh xạ SPIFFE ID với các điều kiện selector; agent thực hiện workload attestation để đối chiếu thuộc tính workload với các điều kiện đã đăng ký. SPIRE là một triển khai trong hệ sinh thái SPIFFE, không phải tên gọi chung cho mọi cơ chế service identity.

Attestation không tự chứng minh toàn bộ mã ứng dụng vô hại. Độ mạnh của kết luận phụ thuộc nguồn bằng chứng, điều kiện đã chọn và quyền thay đổi các điều kiện đó. Nếu chỉ kiểm tra một thuộc tính dễ giả mạo, danh tính cấp ra có thể bị lạm dụng dù credential được ký đúng.

Credential có thể được cấp trực tiếp cho ứng dụng, qua agent, SDK, sidecar hoặc cơ chế danh tính của nền tảng. Cách phân phối phải giới hạn workload nào được nhận credential và giữ được ranh giới giữa các workload cùng host.

## 6. Ví dụ với Kubernetes ServiceAccount

Kubernetes có đối tượng ServiceAccount cho tiến trình/workload. Tài khoản này thuộc một namespace, khác tài khoản người dùng. Pod có thể được gắn ServiceAccount qua `spec.serviceAccountName`; cơ chế token ngắn hạn qua TokenRequest/projected volume hỗ trợ cấp và thay token. Có thể dùng `automountServiceAccountToken: false` để tắt việc tự động đưa credential vào Pod khi không cần. [Nguồn: Kubernetes — Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/).

Ví dụ về ý định gắn danh tính, không phải manifest triển khai hoàn chỉnh:

```text
Namespace:          orders
Workload:           order-api
ServiceAccount:     order-api

Một workload báo cáo khác:
Namespace:          reporting
Workload:           reporting-worker
ServiceAccount:     reporting-worker
```

Ba điểm cần phân biệt khi thiết kế:

1. **ServiceAccount không tự cấp quyền quản trị.** Quyền được trao theo các chính sách/binding áp dụng. Vấn đề của dùng chung tài khoản là khó phân tách quyền và trách nhiệm, không phải mọi tài khoản mặc định đều có sẵn quyền cao.
2. **Kubernetes RBAC và quyền API nghiệp vụ là hai lớp.** Quyền đọc một đối tượng qua Kubernetes API không tự cho phép gọi `POST /reservations` tại `inventory-api`.
3. **Token Kubernetes không mặc nhiên được mọi API hay cloud chấp nhận.** Hệ thống đích cần quan hệ tin cậy và kiểm tra đúng issuer, subject, audience cùng các điều kiện áp dụng, hoặc dùng cơ chế trao đổi credential được cấu hình rõ.

Nếu token chỉ dành cho Kubernetes API, không tái sử dụng tùy tiện nó làm token truy cập cho một dịch vụ khác. Nếu có federation, cần giới hạn chính xác workload nào được ánh xạ thành danh tính đích; ánh xạ cả namespace hoặc mọi cluster quá rộng có thể tạo đường leo thang quyền.

Không đưa token vào image hay sao chép credential của một workload vào workload khác để xử lý lỗi xác thực. Nếu dùng projected credential, ứng dụng hoặc thành phần quản lý credential phải xử lý việc thay mới đúng cách, không chỉ đọc một lần rồi giữ bản cũ mãi.

## 7. Hai cách giao tiếp thường gặp: mTLS và access token

### 7.1. Xác thực dịch vụ bằng mTLS

Với mutual TLS, hai phía có thể xác thực nhau dựa trên chứng thư và việc chứng minh sở hữu khóa riêng. Trong một thiết kế dùng SPIFFE, danh tính workload được lấy từ chứng thư theo quy tắc của X.509-SVID và được đối chiếu với trust bundle phù hợp.

Đối với `order-api` gọi `inventory-api`, hai phía cần xác nhận đúng đối tác mong đợi. Chỉ kiểm tra “chứng thư do một CA được tin ký” không đủ cho chính sách ứng dụng nếu CA đó cấp chứng thư cho nhiều dịch vụ khác nhau.

Sau khi xác thực caller là `order-api`, `inventory-api` vẫn phải kiểm tra quyền giữ chỗ. Việc mTLS bắt tay thành công không tự cho phép mọi hành động, cũng không cho biết người dùng cuối nào đã khởi tạo yêu cầu.

### 7.2. Xác thực client và nhận access token

Một dịch vụ có thể xác thực với Authorization Server để nhận access token cho API đích. Client credentials grant trong [RFC 6749, mục 4.4](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.4) dành cho confidential client, với quyền truy cập được kiểm soát hoặc sắp xếp trước. Luồng này không phải bằng chứng rằng một người dùng cuối vừa đăng nhập hay đã ủy quyền cho mọi thao tác.

```text
order-api -- xác thực client --> Authorization Server
order-api <-- access token ---- Authorization Server

order-api -- access token ----> inventory-api
                               kiểm tra token và quyền
```

`inventory-api` kiểm tra audience dành cho mình, issuer tin cậy, hiệu lực và quyền theo profile token được chấp nhận. Không dùng một token có audience của dịch vụ khác chỉ vì cùng nhà phát hành.

Theo [RFC 8705](https://www.rfc-editor.org/rfc/rfc8705.html), mTLS client authentication với Authorization Server và access token được ràng buộc chứng thư là các cơ chế riêng có thể bổ trợ nhau. Dùng mTLS ở token endpoint không tự chứng minh API đã kiểm tra ràng buộc chứng thư của token. Muốn chống sử dụng token bị đánh cắp theo cơ chế này, bên phát hành và resource server phải thực thi ràng buộc tương ứng.

## 8. Áp dụng nguyên tắc ít quyền nhất cho service identity

Một chính sách khái niệm cho ví dụ có thể viết như sau. Đây là YAML minh họa ý định phân quyền, không phải cú pháp của Kubernetes, SPIRE hay một policy engine cụ thể.

```yaml
principal: spiffe://prod.example/ns/orders/sa/order-api
target: inventory-api
allow:
  - inventory:reserve
conditions:
  environment: production
  trustedOrderContextRequired: true
```

Chính sách cần được thực thi bằng dữ liệu đã xác minh, không tin giá trị `environment` hay thông tin đơn hàng do caller tùy ý tự khai. Ví dụ trên không cấp quyền xuất toàn bộ tồn kho, xóa kho hay quản trị người dùng.

Khi thiết kế RBAC hoặc ABAC cho dịch vụ, nên xác định:

- Dịch vụ đích và tập hành động thật sự cần thiết.
- Phạm vi dữ liệu như tenant, vùng hoặc loại tài nguyên.
- Điều kiện ngữ cảnh lấy từ nguồn nào và ai được thay đổi.
- Quyền xin token/credential mới và quyền sử dụng chúng ở downstream.
- Bên phê duyệt, lịch rà soát và điều kiện thu hồi quyền.

Không cho mọi principal cùng trust domain toàn quyền gọi nhau. Trust domain cho biết căn cứ xác minh danh tính; chính sách vẫn phải chọn danh tính nào được thực hiện hành động nào.

### Danh tính dịch vụ và người dùng cuối

Khi người dùng tạo đơn hàng, chuỗi có thể là:

```text
Người dùng -> order-api -> inventory-api
```

Service identity chứng minh `order-api` là bên gọi trực tiếp. Nó không tự chứng minh người dùng có quyền đặt hàng cho tenant bất kỳ. Nếu thao tác cần ngữ cảnh người dùng hoặc ủy quyền, phải chuyển và kiểm tra ngữ cảnh đó bằng cơ chế đáng tin phù hợp, giữ tách biệt danh tính actor và chủ thể nghiệp vụ.

Không tin `X-User-Id`, `X-Service-Name` hay `X-Tenant` từ request bên ngoài như bằng chứng xác thực. Nếu proxy truyền ngữ cảnh danh tính đã xác minh, backend chỉ nên nhận nó qua đường tin cậy và phải ngăn caller bỏ qua proxy hoặc tự chèn cùng header.

## 9. Quản lý vòng đời và xử lý credential bị lộ

Service identity cần được quản lý như một tài sản IAM có chủ sở hữu, không phải cấu hình bí mật được tạo một lần rồi quên.

| Giai đoạn | Việc cần xác định |
|---|---|
| Đăng ký | Dịch vụ, owner, môi trường, căn cứ cấp credential và mục đích |
| Cấp quyền | Tài nguyên/hành động cần dùng, người phê duyệt và phạm vi dữ liệu |
| Cấp credential | Workload nào đủ điều kiện nhận và nơi bảo vệ khóa/token |
| Vận hành | Thay credential tự động, theo dõi hết hạn, kiểm toán và rà soát quyền |
| Sự cố | Ngăn cấp mới, chặn credential hoặc principal phù hợp và đánh giá downstream |
| Ngừng dịch vụ | Gỡ quyền, quan hệ cấp phát/federation và credential còn tồn tại |

Credential ngắn hạn làm giảm thời gian một bản sao bị lộ có thể sử dụng, nhưng không tự loại bỏ sự cố. Nếu workload bị chiếm quyền vẫn liên tục xin credential mới, chỉ chờ credential cũ hết hạn không chặn được kẻ tấn công.

Khi ngừng một instance bị xâm nhập, cần đánh giá có thể chặn riêng instance/credential hay phải ngừng toàn bộ principal. Mức tác động phụ thuộc cách cấp phát, ranh giới dùng chung và cơ chế thực thi thu hồi. Nếu token được xác minh cục bộ hoặc kết nối đã xác thực còn tồn tại lâu, phải tính tới cửa sổ chấp nhận còn lại.

Rotation cũng cần được xử lý trong tiến trình đang chạy. Thay file chứng thư mà ứng dụng vẫn giữ credential cũ trong bộ nhớ không bảo đảm đã chuyển sang credential mới. Không xử lý lỗi hết hạn bằng cách tắt xác minh chứng thư, chấp nhận mọi issuer hoặc dùng một secret dự phòng dùng chung toàn hệ thống.

## 10. Ranh giới proxy, node và nền tảng cấp danh tính

Trong nhiều hệ thống, sidecar hoặc gateway thực hiện mTLS thay cho mã ứng dụng. Khi đó, cần chỉ rõ nơi xác thực kết thúc và cách danh tính đến được bộ quyết định phân quyền.

```text
Caller -> proxy xác thực -> ứng dụng xử lý nghiệp vụ
          principal đã xác minh
               |
               +-- chuyển ngữ cảnh qua đường được bảo vệ
```

Nếu ứng dụng vẫn có cổng cho caller ngoài đi thẳng vào và tự khai principal, việc xác thực tại proxy có thể bị bỏ qua. Nếu proxy chỉ chứng minh danh tính gateway, backend không được mặc nhiên suy ra danh tính dịch vụ gốc nếu chưa có cơ chế truyền bằng chứng đáng tin.

Node, agent cấp danh tính và quyền triển khai cũng là thành phần của chuỗi tin cậy. Người có quyền gán ServiceAccount đặc quyền cho workload của họ hoặc sửa đăng ký cấp danh tính có thể chiếm một principal mà không cần đánh cắp credential trước đó.

Vì vậy, quyền tạo workload, quyền sửa chính sách cấp danh tính, quyền đọc credential và quyền quản trị nền tảng cần được hạn chế và kiểm toán riêng. Service identity không thay thế cơ chế cô lập workload, bảo vệ host hoặc kiểm soát chuỗi cung ứng phần mềm.

## 11. Tình huống cần kiểm chứng

Các trường hợp dưới đây là gợi ý kiểm thử cho thiết kế, không phải báo cáo đã chạy trên một hệ thống cụ thể.

| Tình huống | Kết quả mong đợi |
|---|---|
| `order-api` production có credential đúng và quyền giữ chỗ | Được thực hiện hành động trong phạm vi dữ liệu cho phép |
| `reporting-worker` gọi thao tác giữ chỗ | Bị từ chối nếu không được cấp quyền đó |
| Caller chỉ gửi header `X-Service-Name: order-api` | Không được coi là đã xác thực |
| Credential staging được dùng ở production | Bị từ chối theo ranh giới trust/policy |
| Chứng thư hợp lệ của một dịch vụ khác | Không tự có quyền của `order-api` |
| Token đúng chữ ký nhưng audience sai | Bị từ chối tại API không phải bên nhận |
| Workload cùng node xin danh tính của `order-api` | Không được nhận nếu không đáp ứng điều kiện cấp phát |
| Replica được thay hoặc scale thêm | Nhận đúng danh tính/quyền qua quy trình cấp phát, không cần copy secret thủ công |
| Credential được rotate khi tiến trình đang chạy | Kết nối/yêu cầu mới dùng credential hợp lệ theo thiết kế |
| Tắt một đường cấp credential sau sự cố | Không còn đường cấp mới ngoài ý muốn; credential cũ được xử lý trong cửa sổ đã định |
| Caller bỏ qua proxy và gọi trực tiếp backend | Không vượt qua được kiểm tra danh tính và phân quyền |
| Dịch vụ hợp lệ yêu cầu tài nguyên của tenant khác | Chỉ được phép nếu chính sách nghiệp vụ đã xác minh cho phép |

Log nên giúp trả lời dịch vụ nào gọi dịch vụ nào, trong môi trường nào, thực hiện hành động gì và quyết định truy cập dựa trên phiên bản chính sách nào. Có thể bổ sung instance và dấu nhận diện credential để điều tra, nhưng không ghi khóa riêng hoặc token nguyên văn.

## 12. Tự kiểm tra hiểu biết

**Có tên `order-api` trong request có chứng minh caller là dịch vụ đó không?** Không. Tên là định danh tự khai nếu chưa được ràng buộc với bằng chứng và nguồn tin cậy.

**Service identity có phải chứng thư không?** Không. Danh tính là principal; chứng thư cùng cơ chế chứng minh giữ khóa có thể là một cách chứng minh principal đó.

**mTLS thành công có đồng nghĩa mọi API call được cho phép không?** Không. Xác thực đối tác và phân quyền hành động là hai trách nhiệm khác nhau.

**Kubernetes ServiceAccount có tự cấp quyền tại API nghiệp vụ hoặc cloud không?** Không. Cần quan hệ tin cậy, ánh xạ và chính sách riêng tại hệ thống đích.

**Nhiều replica có thể cùng service identity không?** Có, nếu chúng cùng vai trò và phạm vi quyền. Vẫn cần quản lý credential và thông tin truy vết instance phù hợp; không đồng nghĩa phải sao chép cùng một khóa riêng.

**Credential ngắn hạn có đủ khi workload đang bị chiếm quyền không?** Không. Cần ngăn cấp credential mới, xử lý quyền và xác định cách chặn những credential hoặc phiên kết nối còn được chấp nhận.

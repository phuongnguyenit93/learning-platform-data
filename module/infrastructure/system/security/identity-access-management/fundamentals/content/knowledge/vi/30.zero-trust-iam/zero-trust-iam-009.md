# Micro-perimeter

## 1. Micro-perimeter là gì?

**Micro-perimeter** là ranh giới bảo vệ có phạm vi nhỏ quanh một tài nguyên hoặc một nhóm tài nguyên liên quan. Tại ranh giới đó, hệ thống kiểm soát chủ thể nào được truy cập, được thực hiện hành động nào và phải đáp ứng điều kiện gì.

Trong bài học này, tài nguyên có thể là một API, dịch vụ, workload, cơ sở dữ liệu hoặc một nhóm thành phần có cùng yêu cầu bảo vệ. Micro-perimeter là cách tổ chức ranh giới kiểm soát; nó không phải tên của một giao thức hay một sản phẩm cụ thể.

Hướng tiếp cận này phù hợp với nguyên tắc Zero Trust tập trung bảo vệ tài nguyên và không cấp sự tin cậy ngầm chỉ từ vị trí mạng. Một kết nối đến từ mạng nội bộ vẫn cần được đánh giá theo quyền truy cập tương ứng. [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final).

Ví dụ, một ứng dụng có dịch vụ tài liệu, dịch vụ tìm kiếm và dịch vụ quản trị identity. Việc người dùng được truy cập dịch vụ tài liệu không có nghĩa người đó được kết nối trực tiếp vào cơ sở dữ liệu hoặc gọi API quản trị identity.

Mục tiêu của micro-perimeter là thu hẹp những gì một lần cấp quyền cho phép và giới hạn các đường truy cập không cần thiết giữa các tài nguyên. Nếu một thành phần gặp sự cố hoặc bị chiếm quyền, những ranh giới còn lại có thể hạn chế khả năng lan sang thành phần khác.

## 2. Từ một vành đai lớn đến các ranh giới theo tài nguyên

Một mô hình dựa chủ yếu vào vành đai mạng có thể tạo giả định rằng sau khi vào mạng nội bộ, người dùng hoặc máy chủ được phép tiếp cận nhiều tài nguyên phía trong.

```text
Mô hình có vùng nội bộ rộng:

Người dùng → Cổng vào mạng → Vùng nội bộ
                              ├── Dịch vụ tài liệu
                              ├── Dịch vụ quản trị identity
                              └── Cơ sở dữ liệu
```

Nếu bên trong có quá nhiều kết nối được phép mặc định, một tài khoản hoặc workload bị chiếm quyền có thể tạo điểm xuất phát cho truy cập tiếp sang các tài nguyên khác. Hành vi di chuyển từ một điểm đã bị xâm nhập sang điểm khác thường được gọi là **lateral movement**.

Với micro-perimeter, mỗi đường truy cập cần thiết được xác định rõ hơn:

```text
Người dùng → Điểm kiểm soát tài liệu → Dịch vụ tài liệu
                                          ↓
                             Quyền riêng tới dữ liệu tài liệu

Quản trị viên → Điểm kiểm soát quản trị → Dịch vụ identity

Worker tìm kiếm → Điểm kiểm soát API lập chỉ mục → Dịch vụ tài liệu
```

Sơ đồ chỉ minh họa ranh giới logic. Các điểm kiểm soát có thể được triển khai bằng nhiều thành phần khác nhau, không nhất thiết mỗi tài nguyên phải có một thiết bị mạng riêng.

Một ranh giới nhỏ cũng không tạo sự tin cậy vô điều kiện cho mọi thứ bên trong. Nếu gộp nhiều thành phần vào một micro-perimeter, cần hiểu rõ các quyền và luồng còn tồn tại giữa chúng. Gộp toàn bộ ứng dụng và mọi dữ liệu vào một vùng rồi chỉ đổi tên thành micro-perimeter không làm phạm vi truy cập thực tế nhỏ đi.

## 3. Phân biệt những khái niệm gần nhau

| Khái niệm | Trọng tâm | Quan hệ với micro-perimeter |
|---|---|---|
| Network segmentation | Chia mạng thành các vùng và kiểm soát luồng giữa vùng | Có thể tạo một lớp ranh giới, nhưng chưa mô tả đủ quyền với đối tượng nghiệp vụ |
| Micro-segmentation | Kiểm soát luồng ở phạm vi nhỏ hơn, như workload hoặc nhóm workload | Có thể hỗ trợ hình thành micro-perimeter quanh tài nguyên |
| Authentication | Xác minh chủ thể hoặc bằng chứng nhận dạng | Cung cấp identity để đánh giá truy cập tại ranh giới |
| Authorization | Quyết định hành động nào được phép với tài nguyên | Xác định quyền cụ thể được thực thi tại ranh giới |
| Micro-perimeter | Phạm vi bảo vệ quanh tài nguyên và các đường truy cập của nó | Kết hợp vị trí kiểm soát với chính sách và giới hạn quyền |
| Tenant data boundary | Ranh giới dữ liệu giữa các tenant | Cần được bảo vệ ngay cả khi nhiều tenant dùng chung một dịch vụ trong cùng micro-perimeter |

Ví dụ, firewall cho phép dịch vụ tìm kiếm kết nối cổng API của dịch vụ tài liệu. Quy tắc đó chưa trả lời dịch vụ tìm kiếm được đọc tài liệu tenant nào, được gọi endpoint nào hoặc có được sửa tài liệu không. Các quyết định đó cần kiểm soát identity và phân quyền ở lớp hiểu được ý nghĩa yêu cầu.

Ngược lại, kiểm tra quyền trong ứng dụng không làm các cổng quản trị hoặc đường kết nối cơ sở dữ liệu tự động an toàn. Kiểm soát mạng và kiểm soát IAM có thể bổ sung cho nhau thay vì thay thế hoàn toàn cho nhau.

## 4. Một micro-perimeter cần xác định những gì?

### 4.1. Tài nguyên được bảo vệ

Cần biết chính xác ranh giới đang bao quanh gì: API đọc tài liệu, chức năng export, cổng quản trị hay kho lưu trữ. Một dịch vụ có thể chứa cả chức năng thông thường lẫn chức năng đặc quyền, vì vậy tên dịch vụ chưa đủ để biểu diễn mọi mức quyền.

Việc xác định tài nguyên còn cần bao gồm các đường truy cập phụ: endpoint nội bộ, cổng quản trị, tác vụ nền, bản sao dữ liệu và công cụ hỗ trợ vận hành.

### 4.2. Chủ thể được phép đi qua

Chủ thể có thể là người dùng, thiết bị, ứng dụng hoặc workload. Cần phân biệt identity thật sự với một địa chỉ mạng hoặc nhãn do client tự khai.

Ví dụ, policy có thể cho phép workload `search-indexer` đọc một tập tài liệu phục vụ lập chỉ mục. Nó không nên cho phép mọi máy cùng subnet làm điều đó chỉ vì workload hợp lệ cũng nằm trong subnet ấy.

### 4.3. Hành động và phạm vi dữ liệu

Một kết nối thành công chưa phải quyền thực hiện mọi thao tác. Policy cần mô tả hành động, tài nguyên và phạm vi dữ liệu, chẳng hạn:

```text
search-indexer:
  Được đọc nội dung cần thiết qua API lập chỉ mục.
  Chỉ trong phạm vi tenant và tác vụ được giao.
  Không được sửa role, xóa tài liệu hoặc truy vấn trực tiếp cơ sở dữ liệu.
```

Đối với người dùng, role cũng cần được diễn giải trong phạm vi tenant hoặc tổ chức tương ứng. Một người quản trị tenant An Phú không có quyền quản trị tenant Bình Minh chỉ vì hai tenant được phục vụ bởi cùng một API.

### 4.4. Điểm thực thi chính sách

**Policy enforcement point**, viết tắt là **PEP**, là nơi áp dụng quyết định truy cập. Trong một thiết kế cụ thể, đó có thể là proxy, gateway, thành phần trên host hoặc kiểm tra trong ứng dụng.

Một policy chỉ có giá trị bảo vệ khi yêu cầu thực tế đi qua một điểm kiểm soát phù hợp. Nếu người gọi có đường kết nối trực tiếp tới backend bỏ qua gateway, kiểm tra tại gateway không bao phủ đường đó.

### 4.5. Điều kiện, vòng đời và audit

Quyền truy cập có thể phụ thuộc trạng thái tài khoản, độ mới xác thực, trạng thái thiết bị hoặc credential workload. Ranh giới cần có cách phản ánh thay đổi quyền, hết hạn và thu hồi.

Audit cần cho biết ai đã yêu cầu, tài nguyên nào được nhắm tới, hành động gì được cho phép hoặc từ chối và policy nào được áp dụng. Không đưa token hay bí mật đầy đủ vào log để thay thế định danh và mã truy vết.

## 5. IAM đưa identity vào ranh giới bảo vệ

Một ranh giới chỉ dựa trên địa chỉ IP có thể không theo sát workload được tạo mới, di chuyển hoặc dùng chung hạ tầng. IAM giúp liên kết truy cập với chủ thể và quyền được cấp cho chủ thể đó.

Ở mức kiến trúc ứng dụng, cần xem xét identity của cả người dùng lẫn dịch vụ thực hiện lời gọi, kết hợp với các kiểm soát mạng phù hợp. Đây cũng là hướng được trình bày trong mô hình truy cập cho ứng dụng cloud-native của NIST. [NIST SP 800-207A](https://csrc.nist.gov/pubs/sp/800/207/a/final).

### 5.1. Người dùng gọi một ứng dụng

Người dùng đăng nhập để có phiên hoặc credential phù hợp. Khi gọi API, hệ thống phải kiểm tra credential, chủ thể, tenant và quyền với hành động cụ thể.

Một token được chấp nhận cho dịch vụ tài liệu không nên được mặc nhiên chấp nhận ở API quản trị identity. Dịch vụ nhận cần kiểm tra credential có được cấp cho mục đích và đích sử dụng mà nó chấp nhận hay không, ngoài việc kiểm tra thời hạn và tính xác thực.

Nếu gateway truyền identity qua header tới backend, cần có một mô hình tin cậy rõ ràng. Backend không được chấp nhận một header như `X-User-Role: admin` từ bất kỳ client nào. Đường truyền, bên được phép tạo thông tin và cách loại bỏ hoặc xác minh dữ liệu do bên ngoài gửi phải được thiết kế đồng bộ.

### 5.2. Dịch vụ gọi dịch vụ

Một workload cần identity và credential riêng đủ để thực hiện nhiệm vụ được giao. Dùng chung một credential quản trị cho mọi dịch vụ khiến các micro-perimeter khó phân biệt chủ thể và làm phạm vi ảnh hưởng khi credential bị lộ lớn hơn.

Nếu dịch vụ A gọi B thay người dùng, B cần biết thẩm quyền của lời gọi đến từ đâu: người dùng, workload hay một cơ chế ủy quyền cụ thể. Không nên lấy quyền rộng của A làm lý do để đáp ứng mọi yêu cầu mà bất kỳ người dùng nào gửi cho A.

Ví dụ, người dùng chỉ được export tài liệu của An Phú. Worker export có quyền kỹ thuật để tạo file, nhưng yêu cầu của người dùng không được phép tùy ý chuyển thành một tác vụ xuất dữ liệu Bình Minh.

### 5.3. mTLS không tự tạo quyền nghiệp vụ

TLS bảo vệ kênh truyền theo cấu hình và cách xác minh được sử dụng. Với mTLS, hai đầu có thể xác minh chứng thư của nhau. Tuy nhiên, việc có chứng thư hợp lệ trong một miền tin cậy không đồng nghĩa được gọi mọi endpoint hoặc đọc mọi dữ liệu.

Hệ thống vẫn cần ánh xạ bằng chứng kết nối tới identity được chấp nhận, sau đó kiểm tra quyền của identity đó với tài nguyên và hành động. Một workload có thể được phép gọi endpoint lập chỉ mục nhưng bị từ chối ở endpoint quản trị, dù cả hai sử dụng cùng một kết nối được bảo vệ.

## 6. Kiểm soát cả đường vào, đường ngang và đường ra

### Đường vào tài nguyên

Đường vào gồm các yêu cầu từ người dùng hoặc hệ thống khác tới tài nguyên. Cần xác định ai được tiếp cận, giao thức nào được dùng và hành động nào được phép sau khi kết nối được thiết lập.

Một API gateway có thể chặn credential sai hoặc route không được phép. Ứng dụng phía sau vẫn có thể cần kiểm tra quyền trên từng tài liệu vì gateway không có đủ ngữ cảnh sở hữu tài liệu hoặc membership hiện tại.

### Đường giữa các workload

Hai workload cùng chạy trong một môi trường không mặc nhiên có quyền gọi nhau. Cần ghi rõ những quan hệ như `document-api → document-store`, thay vì cho phép mọi workload kết nối mọi cổng nội bộ.

Một dependency hợp lệ cũng cần phạm vi quyền. Quyền kết nối tới cơ sở dữ liệu không nên đồng nghĩa quyền sửa schema, đọc mọi bảng hay quản trị identity nếu nghiệp vụ chỉ cần đọc một tập dữ liệu giới hạn.

### Đường ra khỏi phạm vi bảo vệ

Kiểm soát outbound hoặc egress giúp giới hạn những đích mà tài nguyên được phép kết nối. Chẳng hạn, worker export có thể cần ghi file vào một kho được chỉ định nhưng không cần gửi dữ liệu tới một dịch vụ bên ngoài tùy ý.

Giới hạn egress có thể hỗ trợ giảm một số đường truyền dữ liệu trái phép, nhưng không bảo đảm loại bỏ mọi khả năng rò rỉ. Một thành phần đã bị chiếm quyền vẫn có thể lạm dụng các đích và hành động vốn được phép. Cần kết hợp giới hạn đích, quyền dữ liệu, quan sát và xử lý sự cố.

Các dependency phụ như phân giải tên, đồng bộ thời gian hoặc thu thập log cũng cần được xem xét. Bỏ sót chúng có thể gây gián đoạn; cho phép quá rộng chỉ để tránh gián đoạn lại làm ranh giới yếu đi.

## 7. Ví dụ thiết kế cho dịch vụ tài liệu

Giả sử hệ thống có bốn thành phần:

- `document-api`: xử lý đọc và cập nhật tài liệu.
- `search-indexer`: đọc dữ liệu cần thiết để lập chỉ mục.
- `export-worker`: tạo file export từ tác vụ đã được chấp thuận.
- `identity-admin-api`: quản trị identity và role binding.

Cơ sở dữ liệu tài liệu và kho file export là các tài nguyên cần quyền riêng. Một ma trận truy cập minh họa có thể như sau:

| Chủ thể | Đích | Hành động cho phép | Giới hạn |
|---|---|---|---|
| Thành viên tenant | `document-api` | Đọc hoặc sửa theo role | Đúng tenant và tài liệu được cấp quyền |
| `search-indexer` | API lập chỉ mục của `document-api` | Đọc trường cần cho chỉ mục | Đúng phạm vi tác vụ; không sửa role hoặc tài liệu |
| `export-worker` | API dữ liệu export | Đọc tập dữ liệu export được giao | Tác vụ hợp lệ, đúng tenant và phạm vi được chấp thuận |
| `export-worker` | Kho file export | Tạo file kết quả | Gắn file với đúng tenant và job |
| `document-api` | Kho dữ liệu tài liệu | Truy cập theo nhiệm vụ ứng dụng | Dùng quyền dữ liệu và tenant context phù hợp |
| Quản trị viên được cấp quyền | `identity-admin-api` | Quản trị theo quyền hiện tại | Kiểm soát đặc quyền, tenant và điều kiện xác thực |

Những quan hệ không có nhu cầu nghiệp vụ cần bị từ chối theo chính sách mặc định. Ví dụ, `search-indexer` không cần truy cập cơ sở dữ liệu trực tiếp và không cần gọi `identity-admin-api`.

### Policy minh họa

```yaml
policy:
  resource: document-indexing-api
  defaultDecision: DENY
  allow:
    principal: search-indexer
    action: document.index.read
    conditions:
      credentialAcceptedForThisApi: true
      workloadIdentityActive: true
      tenantMatchesAssignedJob: true
      documentWithinAssignedScope: true
```

Đây là mô tả ý định chính sách, không phải cú pháp của một sản phẩm có thể áp dụng trực tiếp. Các giá trị điều kiện phải được tính từ nguồn tin cậy ở phía máy chủ; client không được tự gửi `tenantMatchesAssignedJob: true` rồi coi là đã đáp ứng.

Policy cũng cần được phân chia theo nơi có đủ thông tin. Lớp mạng có thể giới hạn workload nào được kết nối API. Lớp nhận dạng xác minh workload. Lớp ứng dụng kiểm tra job, tenant và tài liệu. Không nên giả định một lớp kiểm soát kết nối có thể tự thực thi đầy đủ mọi điều kiện nghiệp vụ trong bảng.

### Luồng đánh giá một yêu cầu

```text
1. Xác minh nguồn gọi và credential dùng cho API đích.
2. Xác định identity của workload và người được đại diện, nếu có.
3. Lấy job và tenant từ ngữ cảnh đã được xác minh.
4. Kiểm tra action và phạm vi tài liệu được phép.
5. Áp dụng các điều kiện và trạng thái quyền hiện tại.
6. Thực hiện truy cập trong phạm vi đó và ghi audit cần thiết.
```

Đường truy cập dữ liệu bên dưới cũng phải giữ tenant context. Một API đã kiểm tra đúng tenant nhưng sử dụng truy vấn thiếu phạm vi tenant vẫn có thể trả sai dữ liệu.

## 8. Những đường đi vòng cần được đóng

Một micro-perimeter không bao phủ tài nguyên nếu vẫn tồn tại một đường khác cho phép tiếp cận cùng dữ liệu với kiểm soát yếu hơn.

| Đường đi vòng | Nguy cơ | Cách tiếp cận thiết kế |
|---|---|---|
| Backend nhận kết nối trực tiếp ngoài gateway dự kiến | Bỏ qua kiểm tra ở gateway | Giới hạn đường tiếp cận và xác minh nguồn gọi tại backend theo mô hình tin cậy |
| Cổng quản trị dùng credential mặc định hoặc quyền quá rộng | Truy cập đặc quyền ngoài luồng IAM chính | Áp dụng identity, quyền riêng, giới hạn tiếp cận và audit |
| Tác vụ định kỳ dùng tài khoản quản trị chung | Một job nhỏ có thể truy cập mọi dữ liệu | Tách workload identity và quyền theo nhiệm vụ |
| File export được đặt ở vị trí tải công khai | Bỏ qua quyền của API nghiệp vụ | Kiểm soát quyền file, thời hạn và quy trình cấp đường tải |
| Công cụ backup hoặc hỗ trợ đọc toàn bộ dữ liệu | Một đường truy cập rộng nằm ngoài ranh giới đã vẽ | Xác định phạm vi đặc quyền, quy trình vận hành và bằng chứng audit riêng |
| Endpoint cũ chưa đưa vào policy | Chính sách mới chỉ áp dụng cho một phần tài nguyên | Kiểm kê route, giao thức, cổng và đường truy cập thực tế |

Nếu dùng liên kết tải có chữ ký, cần kiểm tra quyền trước khi cấp, giới hạn đúng object và thời hạn. Thu hồi quyền ở API không tự động làm mọi liên kết đã cấp hết hiệu lực; khả năng thu hồi phụ thuộc thiết kế phân phối file.

Không nên xem một chức năng là an toàn chỉ vì nó được gọi là “nội bộ”. Cần chứng minh đường gọi nào được phép, ai có thể dùng nó và quyết định nào được áp dụng.

## 9. Giới hạn thiệt hại khi một thành phần bị chiếm quyền

Giả sử `search-indexer` bị chiếm quyền. Với các ranh giới và quyền trong ví dụ, kẻ kiểm soát workload có thể cố sử dụng những quyền mà workload đang có. Micro-perimeter không làm workload bị chiếm quyền trở lại đáng tin cậy.

Thiết kế kỳ vọng giới hạn được các đường ngoài nhiệm vụ: workload không gọi được API quản trị identity, không kết nối trực tiếp kho dữ liệu và không xuất dữ liệu qua một đích tùy ý chỉ vì nó đang ở mạng nội bộ.

Phạm vi thiệt hại còn phụ thuộc quyền đã cấp. Nếu `search-indexer` vốn được phép đọc mọi tài liệu của mọi tenant, ranh giới mạng nhỏ không làm quyền đọc ấy nhỏ đi. Muốn giảm tác động cần xem lại phạm vi tài liệu, dữ liệu thực sự cần đưa vào chỉ mục và thẩm quyền của từng job.

Khi phát hiện sự cố, có thể cần thu hồi identity hoặc credential workload, cập nhật policy và ngắt các truy cập đang mở theo khả năng hệ thống. Luân chuyển credential không tự động bảo đảm các credential đã cấp trước đó bị mọi dịch vụ từ chối ngay.

Tương tự, micro-perimeter không ngăn được mọi lỗi logic trong một hành động vốn được cho phép. Nếu API cho phép một workload đọc tài liệu nhưng truy vấn bị sai tenant, lỗi vẫn nằm trên đường truy cập hợp lệ về mặt kết nối. Vì vậy, kiểm soát ranh giới cần đi cùng phân quyền trên tài nguyên và tính đúng đắn của xử lý dữ liệu.

## 10. Vận hành các ranh giới nhỏ

### Nhất quán chính sách

Nhiều điểm thực thi có thể nhận policy ở các thời điểm khác nhau. Cần theo dõi phiên bản, khả năng triển khai và độ trễ thu hồi để biết tài nguyên nào đang dùng chính sách cũ.

Nếu một quyết định được cache, khóa cache phải biểu diễn đủ ngữ cảnh như chủ thể, tenant, tài nguyên, action và phiên bản liên quan. Quyết định cho phép một workload đọc một tài liệu không nên được tái sử dụng như quyền đọc mọi tài liệu.

### Trạng thái kết nối và phiên

Một ranh giới có thể được kiểm tra lúc mở kết nối nhưng kết nối sống lâu hơn quyền đã cấp. Cần xác định khi nào đánh giá lại, cách ngắt kênh và cách xử lý các thao tác đang chạy.

Chặn kết nối mới không đồng nghĩa đã chặn mọi kết nối cũ. Việc thu hồi cũng không lấy lại dữ liệu đã được trả cho bên gọi.

### Lỗi nguồn identity hoặc chính sách

Một thao tác không đủ bằng chứng bắt buộc không nên được cho phép chỉ vì dịch vụ kiểm tra đang lỗi. Nếu sản phẩm chấp nhận một mức hoạt động giới hạn với policy được lưu tạm, cần xác định rõ hành động, thời hạn và điều kiện áp dụng.

Cơ chế khẩn cấp, nếu có, cần phạm vi và audit riêng. Không dùng lỗi kết nối đến thành phần chính sách như công tắc ngầm mở mọi micro-perimeter.

### Quyền quản trị ranh giới

Người có thể sửa policy, định tuyến hoặc danh tính workload có thể thay đổi tác dụng của ranh giới. Quyền quản trị các thành phần đó cần được bảo vệ tương xứng, có ghi nhận thay đổi và quy trình rà soát phù hợp.

Một hệ thống có nhiều ranh giới nhưng một credential quản trị dùng chung, dễ lấy và không được giám sát vẫn có một điểm đặc quyền rất rộng.

## 11. Cách triển khai từng bước và kiểm chứng

Có thể bắt đầu từ một tài nguyên có giá trị và luồng truy cập tương đối rõ, thay vì tạo quá nhiều ranh giới mà chưa hiểu dependency.

1. **Kiểm kê tài nguyên và đường truy cập:** gồm API, dữ liệu, cổng quản trị, worker, backup và file xuất.
2. **Gắn identity với luồng:** xác định người dùng hoặc workload nào đang gọi, credential nào được dùng và quyền lấy từ đâu.
3. **Mô tả luồng cần thiết:** chỉ rõ nguồn, đích, action, tenant và dữ liệu. Lưu lượng đang tồn tại là bằng chứng để điều tra, không tự động là lưu lượng hợp lệ.
4. **Chọn điểm thực thi phù hợp:** đặt kiểm soát ở nơi chặn được đường đi và có đủ ngữ cảnh cho quyết định tương ứng.
5. **Áp dụng policy có phạm vi:** tách quyền kết nối, quyền ứng dụng và quyền dữ liệu, kiểm soát cả đường quản trị.
6. **Kiểm chứng và mở rộng:** xác nhận truy cập hợp lệ vẫn hoạt động, truy cập ngoài phạm vi bị chặn và không còn đường đi vòng đã biết.

Một số tình huống kiểm tra có ích:

| Tình huống | Điều cần xác nhận |
|---|---|
| Workload hợp lệ gọi action được cấp | Truy cập đúng phạm vi được chấp thuận |
| Workload khác nhưng cùng subnet gọi cùng API | Không được cấp quyền chỉ vì cùng vị trí mạng |
| Có chứng thư hợp lệ nhưng thiếu quyền action | Bị từ chối ở lớp phân quyền phù hợp |
| Token được cấp cho dịch vụ khác | Không được chấp nhận ngoài đích sử dụng được phép |
| Người dùng có role tại tenant khác | Không vượt phạm vi tenant |
| Gọi backend hoặc cổng quản trị trực tiếp | Không đi vòng qua kiểm soát dự kiến |
| Thu hồi quyền khi có kết nối hoặc job đang hoạt động | Hành vi phản ánh chính sách và giới hạn thu hồi đã định nghĩa |
| Nguồn policy không truy cập được | Không tự mở quyền ngoài cơ chế dự phòng đã chấp thuận |

Chỉ số vận hành nên giúp nhận ra ranh giới nào thực sự có hiệu lực: đường truy cập đã được kiểm kê, điểm thực thi đã nhận đúng policy, credential đặc quyền còn tồn tại và thời gian thay đổi quyền được áp dụng. Số lượng rule hoặc số lần chặn đơn lẻ không chứng minh toàn bộ tài nguyên đã được bao phủ.

## 12. Câu hỏi tự kiểm tra

1. Vì sao chia nhiều subnet chưa đủ để quyết định một workload được đọc tài liệu tenant nào?
2. Một gateway đã kiểm tra đăng nhập nhưng backend còn mở đường trực tiếp sẽ tạo vấn đề gì?
3. Vì sao chứng thư mTLS hợp lệ không đồng nghĩa có quyền gọi API quản trị?
4. Khi `search-indexer` bị chiếm quyền, những giới hạn nào còn giúp giảm phạm vi ảnh hưởng và những quyền hợp lệ nào vẫn có thể bị lạm dụng?
5. Vì sao backup, export và quyền sửa policy phải được đưa vào phạm vi thiết kế micro-perimeter?

Micro-perimeter giúp đặt các ranh giới kiểm soát rõ hơn quanh tài nguyên. Hiệu quả của nó phụ thuộc vào identity đáng tin cậy, quyền có phạm vi, điểm thực thi bao phủ đường truy cập và khả năng duy trì các giới hạn đó khi hệ thống thay đổi.

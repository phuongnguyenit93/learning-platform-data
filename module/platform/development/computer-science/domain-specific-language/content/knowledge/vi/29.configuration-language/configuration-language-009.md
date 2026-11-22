# Phát hiện cấu hình lệch

Trong một hệ thống được quản lý bằng ngôn ngữ cấu hình (Configuration DSL), người vận hành thường mô tả trạng thái mong muốn của tài nguyên: máy chủ cần những package nào, dịch vụ phải mở cổng nào, database cần tham số nào, ứng dụng phải chạy phiên bản nào và quyền truy cập được cấp ra sao. Hệ thống triển khai các mô tả đó lên môi trường thật. Theo thời gian, trạng thái thực tế có thể khác với mô hình đã khai báo do thao tác thủ công, thay đổi ngoài pipeline, lỗi triển khai, cập nhật tự động hoặc một thành phần khác sửa tài nguyên.

**Phát hiện cấu hình lệch** (*configuration drift detection*) là quá trình so sánh trạng thái thực tế đã quan sát với trạng thái mong muốn hoặc baseline được quản lý, nhận diện những khác biệt có ý nghĩa, phân loại chúng và cung cấp bằng chứng để người vận hành quyết định xử lý. Trong lĩnh vực Infrastructure as Code (IaC), drift có thể là một security group được mở thêm cổng, một instance bị đổi kích thước, một replica bị xóa hoặc một tham số database khác với cấu hình khai báo. Trong cấu hình ứng dụng, drift có thể là feature flag bị thay đổi trực tiếp, một biến môi trường không đúng giá trị được quản lý hoặc một policy bị sửa ngoài quy trình.

Ví dụ DSL khai báo trạng thái mong muốn:

~~~text
environment production {
    service orders {
        replicas = 4;
        image = "registry.example/orders:2.8.1";
        port = 8080;
        publicAccess = false;
    }

    database ordersDb {
        backupEnabled = true;
        encryption = "managed-key";
        maxConnections = 120;
    }
}
~~~

Khi đọc môi trường production, hệ thống có thể phát hiện service `orders` đang chạy ba replica, image `2.8.0` hoặc cho phép truy cập công khai; database có thể tắt backup. Mỗi khác biệt cần được so sánh với đúng tài nguyên và đúng phiên bản cấu hình. Hệ thống cũng phải phân biệt một thay đổi có chủ đích đã được phê duyệt với một thay đổi ngoài quản lý.

Phát hiện drift không đồng nghĩa với tự động sửa mọi khác biệt. Một hệ thống có thể chỉ báo cáo; hệ thống khác có thể đề xuất kế hoạch sửa; một số môi trường cho phép tự động hội tụ về desired state. Việc phát hiện, đánh giá và remediation cần được thiết kế thành các bước riêng để tránh biến một cảnh báo thành thay đổi hạ tầng ngoài ý muốn.

## 1. Configuration drift là gì?

**Configuration drift** là sự sai khác giữa cấu hình mà hệ thống được kỳ vọng tuân thủ và cấu hình đang tồn tại hoặc đang có hiệu lực trong môi trường. Khái niệm này thường xuất hiện trong quản lý hạ tầng, nhưng cũng áp dụng cho ứng dụng, database, nền tảng dữ liệu, bảo mật, mạng và quy trình vận hành.

Một mô hình đơn giản:

~~~text
Desired state  = trạng thái được khai báo hoặc phê duyệt
Actual state   = trạng thái được quan sát từ môi trường
Drift          = khác biệt có ý nghĩa giữa hai trạng thái
~~~

Không phải mọi khác biệt về byte hoặc cách biểu diễn đều là drift. Ví dụ, API có thể trả danh sách security group theo thứ tự khác nhau dù tập thành viên giống hệt; một timestamp `lastUpdated` có thể thay đổi sau mỗi lần đọc; một ID do cloud provider sinh ra có thể không được khai báo trong DSL. Những trường hợp này cần được chuẩn hóa hoặc phân loại riêng.

### Desired state

Desired state là trạng thái mà hệ thống cần đạt được theo cấu hình được chấp nhận. Nó có thể được lấy từ:

- File DSL trong repository.
- Phiên bản cấu hình đã được review và phê duyệt.
- Module hoặc workspace cấu hình theo môi trường.
- Policy trung tâm do nền tảng quản lý.
- Baseline được import và đánh dấu là trạng thái chuẩn.
- Một revision cụ thể đã được triển khai thành công.

Desired state phải có identity và version rõ ràng. Nếu chỉ đọc nhánh mới nhất của repository mà không ghi nhận commit hoặc revision, báo cáo drift có thể không tái lập được khi cấu hình thay đổi giữa hai lần scan.

### Actual state

Actual state là trạng thái được quan sát từ hệ thống thật qua provider, API, agent, query, inventory hoặc nguồn dữ liệu khác. Nó có thể khác với trạng thái đã triển khai gần nhất do thay đổi thủ công, autoscaling, controller khác hoặc độ trễ đồng bộ.

Actual state cũng cần có thời điểm quan sát, nguồn quan sát và định danh môi trường. Một kết quả đọc từ cache cũ không nên được coi là trạng thái hiện tại mà không ghi rõ độ mới của dữ liệu.

### Baseline

Baseline là một trạng thái chuẩn được dùng làm mốc so sánh. Baseline có thể là desired state hiện tại, revision đã phê duyệt, snapshot sau một lần audit hoặc cấu hình được nhập từ hệ thống có sẵn.

Baseline khác desired state ở chỗ nó có thể được dùng để theo dõi thay đổi lịch sử hoặc phát hiện thay đổi sau một thời điểm cố định. Hệ thống cần nói rõ đang so sánh actual với desired hiện tại hay với baseline đã pin.

## 2. Vì sao cần phát hiện cấu hình lệch?

### Bảo đảm môi trường tuân thủ cấu hình

Hạ tầng có thể được chỉnh sửa qua console, CLI hoặc API mà không cập nhật repository. Drift detection giúp phát hiện các thay đổi đó để môi trường không âm thầm rời khỏi cấu hình đã được review.

### Phát hiện rủi ro bảo mật

Một firewall rule được mở rộng, một bucket chuyển sang public, một tài khoản được cấp quyền quản trị hoặc mã hóa bị tắt có thể tạo ra rủi ro đáng kể. Những khác biệt này cần được nhận diện nhanh và phân loại theo mức độ nghiêm trọng.

### Tăng độ tin cậy vận hành

Khi môi trường khác cấu hình khai báo, lần triển khai tiếp theo có thể tạo kết quả khó dự đoán. Drift detection cho biết hiện trạng trước khi áp dụng thay đổi mới.

### Hỗ trợ audit và compliance

Tổ chức có thể cần bằng chứng rằng cấu hình production đáp ứng baseline. Báo cáo drift, snapshot, thời điểm quan sát và lịch sử remediation giúp kiểm toán xác định điều gì đã thay đổi và ai xử lý.

### Phát hiện lỗi triển khai hoặc lỗi controller

Nếu một pipeline báo deploy thành công nhưng trạng thái thực tế không đạt desired state, drift detection có thể phát hiện việc apply không hoàn tất, controller khác ghi đè hoặc provider trả về giá trị không như mong đợi.

### Kiểm soát thay đổi ngoài quy trình

Thay đổi trực tiếp đôi khi cần thiết để xử lý sự cố. Drift detection giúp ghi nhận thay đổi đó, đánh giá xem nó có cần được đưa trở lại cấu hình nguồn hay hoàn nguyên hay không.

## 3. Phân biệt drift detection, configuration validation và reconciliation

Ba khái niệm thường đi cùng nhau nhưng có mục tiêu khác nhau.

| Hoạt động | Câu hỏi chính | Kết quả |
|---|---|---|
| Configuration validation | Cấu hình khai báo có hợp lệ không? | Diagnostic về schema, kiểu, policy hoặc dependency. |
| Drift detection | Môi trường thực tế có khác trạng thái chuẩn không? | Danh sách khác biệt và bằng chứng. |
| Reconciliation | Cần làm gì để actual state hội tụ về desired state? | Kế hoạch hoặc thao tác thay đổi tài nguyên. |
| Deployment/apply | Thực hiện thay đổi đã được chấp thuận như thế nào? | Tài nguyên được tạo, sửa hoặc xóa. |
| Compliance evaluation | Trạng thái có đáp ứng các quy tắc quản trị không? | Vi phạm policy và mức độ rủi ro. |

Một cấu hình có thể hợp lệ về cú pháp và kiểu nhưng không khớp môi trường. Ngược lại, actual state có thể khác desired state nhưng vẫn tuân thủ policy; ví dụ số replica cao hơn do autoscaling. Vì vậy, validation, drift và compliance không nên bị gộp thành một trạng thái boolean duy nhất.

### Detection không nhất thiết tự sửa

Detection nên tạo ra một kết quả có thể xem xét độc lập. Reconciliation có thể được thực hiện bởi controller tự động, pipeline triển khai hoặc người vận hành. Tách hai bước giúp kiểm soát tác động và audit.

### Desired state không phải lúc nào cũng là actual state phải bằng tuyệt đối

Một số thuộc tính được phép biến động hoặc do hệ thống khác quản lý. Ví dụ autoscaler điều chỉnh replica trong một khoảng, cloud provider gán IP động, hoặc hệ thống quản lý certificate tự gia hạn. DSL cần mô tả những thuộc tính có thể thay đổi và điều kiện chấp nhận chúng.

## 4. Mô hình dữ liệu cho drift detection

Một hệ thống drift detection cần biểu diễn ít nhất cấu hình mong muốn, snapshot thực tế, danh tính tài nguyên và kết quả so sánh.

Mô hình khái niệm:

~~~text
DriftScan
  scanId
  environmentId
  desiredRevision
  startedAt
  completedAt
  status
  resources[]

ResourceComparison
  resourceIdentity
  resourceType
  desiredSnapshot
  actualSnapshot
  observedAt
  differences[]

DriftDifference
  path
  kind
  desiredValue
  actualValue
  severity
  classification
  evidence
~~~

### Resource identity

Identity xác định hai trạng thái đang được so sánh có thuộc cùng một tài nguyên hay không. Nó có thể gồm provider, account/project, region, resource type, logical name và provider ID.

Không nên ghép tài nguyên chỉ bằng tên hiển thị nếu tên có thể trùng giữa account hoặc region. Nếu identity sai, hệ thống có thể báo tài nguyên bị xóa và tài nguyên mới được tạo dù thực tế chỉ là một tài nguyên được rename hoặc chuyển vùng.

### Desired snapshot

Snapshot desired nên ghi revision nguồn, giá trị đã resolve, biến đầu vào và module dependency cần thiết. Nếu cấu hình DSL sử dụng variable hoặc template, cần lưu kết quả resolve để có thể tái hiện phép so sánh.

### Actual snapshot

Snapshot actual lưu các thuộc tính đã đọc từ provider cùng timestamp, provider version hoặc metadata nguồn. Có thể giữ raw response cho audit, nhưng cần kiểm soát dữ liệu nhạy cảm và kích thước lưu trữ.

### Difference

Difference mô tả một đường dẫn cụ thể trong tài nguyên và loại sai khác. Ví dụ `service.orders.replicas` có desired là 4 nhưng actual là 3.

## 5. Mô hình Desired State và Actual State

Một DSL cấu hình thường mô tả desired state theo hướng khai báo: người dùng nói hệ thống cần ở trạng thái nào, không nhất thiết mô tả từng lệnh để đạt trạng thái đó.

Ví dụ:

~~~text
resource service "orders" {
    desired {
        replicas = 4;
        image = "registry.example/orders:2.8.1";
        exposure = private;
    }
}
~~~

Actual state được thu thập từ môi trường:

~~~json
{
  "replicas": 3,
  "image": "registry.example/orders:2.8.1",
  "exposure": "private"
}
~~~

Kết quả so sánh cho biết chỉ thuộc tính `replicas` đang lệch.

### Desired state có thể được resolve

DSL có thể sử dụng biến theo môi trường:

~~~text
variables production {
    ordersReplicas = 4;
    ordersImage = "registry.example/orders:2.8.1";
}

resource service "orders" {
    desired {
        replicas = ${ordersReplicas};
        image = ${ordersImage};
    }
}
~~~

Trước khi so sánh, hệ thống phải resolve variable theo environment và ghi nhận nguồn của giá trị. Nếu variable thay đổi trong lúc scan, desired snapshot cần giữ một revision nhất quán thay vì đọc từng biến ở các thời điểm khác nhau.

### Actual state có thể có thuộc tính do provider sinh

Provider có thể trả thêm ID, timestamp, status, endpoint hoặc metadata không được khai báo trong DSL. Các trường này không mặc nhiên là drift. DSL hoặc provider adapter cần phân biệt managed attributes, computed attributes và informational attributes.

### Desired state một phần

DSL có thể chỉ quản lý một số thuộc tính của tài nguyên. Các thuộc tính còn lại thuộc quyền sở hữu của người vận hành hoặc hệ thống khác. Drift detector cần biết phạm vi quản lý để không coi mọi trường actual không được khai báo là cấu hình thừa.

## 6. Quy trình phát hiện drift tổng quát

Một lượt scan thường đi qua các bước sau:

~~~mermaid
flowchart TD
    A[Load approved desired revision] --> B[Resolve variables and dependencies]
    B --> C[Discover managed resources]
    C --> D[Read actual state]
    D --> E[Normalize snapshots]
    E --> F[Match resource identities]
    F --> G[Compare managed attributes]
    G --> H[Classify and score differences]
    H --> I[Apply suppression and policy rules]
    I --> J[Store evidence and report]
    J --> K[Alert / review / remediation plan]
~~~

### 1. Nạp desired revision

Chọn đúng revision cấu hình đã được phê duyệt cho environment. Ghi lại commit, tag, model version hoặc deployment revision.

### 2. Resolve cấu hình

Giải quyết variable, template, reference và dependency. Giá trị secret không nên bị đưa vào log hoặc report dưới dạng plaintext.

### 3. Khám phá tài nguyên

Lấy danh sách tài nguyên thuộc phạm vi quản lý từ state store, manifest hoặc provider discovery. Cần xác định rõ scope account, project, region, namespace và resource type.

### 4. Đọc actual state

Gọi provider API, agent hoặc inventory service để thu thập thuộc tính thực tế. Ghi thời điểm và trạng thái thành công/thất bại của từng lần đọc.

### 5. Chuẩn hóa snapshot

Chuyển desired và actual về cùng kiểu dữ liệu, đơn vị, representation và quy tắc so sánh.

### 6. Ghép identity

Ghép desired resource với actual resource theo identity đã định nghĩa. Xác định resource missing, unexpected hoặc ambiguous.

### 7. So sánh thuộc tính

So sánh các thuộc tính nằm trong phạm vi quản lý, áp dụng quy tắc equality, default, set ordering và computed fields.

### 8. Phân loại và đánh giá

Xác định loại drift, severity, ownership và policy impact. Một cổng mạng public có thể nghiêm trọng hơn một label hiển thị bị thay đổi.

### 9. Áp dụng suppression

Xem xét exception hoặc waiver đã được phê duyệt. Suppression cần có phạm vi, lý do, người phê duyệt và thời hạn.

### 10. Lưu bằng chứng và báo cáo

Lưu snapshot hoặc hash, differences, timestamps, source revision và provider evidence. Sau đó phát cảnh báo hoặc tạo remediation plan theo policy.

## 7. Thu thập actual state

Chất lượng drift detection phụ thuộc vào độ chính xác và độ mới của actual state.

Các nguồn quan sát có thể gồm:

- API của cloud provider.
- Kubernetes API hoặc control plane tương đương.
- Configuration management agent trên máy chủ.
- Database metadata và system catalog.
- Service registry hoặc application management API.
- Network controller và firewall inventory.
- Secrets/configuration manager metadata.
- CMDB hoặc inventory trung tâm.
- Event stream ghi nhận thay đổi tài nguyên.

### Provider adapter

Một adapter chuyển API riêng của provider thành mô hình actual state chuẩn. Nó có thể chuẩn hóa tên thuộc tính, kiểu số, trạng thái và resource identity để comparator không cần hiểu từng API riêng.

### Read permission

Drift scanner cần quyền đọc đủ để quan sát các thuộc tính được quản lý. Thiếu quyền đọc phải được biểu diễn là `UNKNOWN` hoặc `READ_ERROR`, không được coi là thuộc tính không tồn tại hoặc không lệch.

### API consistency

Một số API trả eventual consistency. Sau khi apply, lần đọc ngay sau có thể chưa thấy trạng thái mới. Scanner cần ghi nhận consistency window hoặc retry có giới hạn trước khi kết luận drift.

### Rate limit và pagination

Inventory lớn có thể cần nhiều request. Adapter phải xử lý pagination, rate limit, retry/backoff và giới hạn concurrency. Nếu chỉ đọc được một phần tài nguyên, report phải thể hiện scan incomplete.

### Snapshot consistency

Actual state của nhiều resource có thể được đọc tại các thời điểm khác nhau. Nếu môi trường thay đổi trong khi scan, kết quả có thể là một tập trạng thái chưa từng cùng tồn tại tại một thời điểm. Với môi trường yêu cầu độ chính xác cao, cần snapshot API, revision token hoặc ghi nhận khoảng thời gian scan và mức độ nhất quán.

## 8. Resource discovery và phạm vi quản lý

Trước khi so sánh, hệ thống phải xác định tài nguyên nào thuộc phạm vi quản lý.

### Managed resource

Resource được khai báo hoặc được import vào state store và có owner rõ ràng. Nó được so sánh với desired state.

### Unmanaged resource

Resource tồn tại trong môi trường nhưng không thuộc phạm vi DSL quản lý. Tùy policy, nó có thể được bỏ qua, báo cáo như unexpected resource hoặc được đề xuất import.

### Missing resource

Resource có trong desired state nhưng không tìm thấy trong actual state. Nó có thể đã bị xóa thủ công, bị provider loại bỏ hoặc không được discovery nhìn thấy do thiếu quyền.

### Unexpected resource

Resource tồn tại trong actual state nhưng không có trong desired scope. Đây có thể là resource được tạo ngoài pipeline, resource tạm thời hợp lệ hoặc tài nguyên do một controller khác sở hữu.

### Scope boundary

Phạm vi scan cần được xác định theo account, project, subscription, region, cluster, namespace, folder hoặc label. Một scope quá rộng có thể phát hiện tài nguyên không liên quan; scope quá hẹp có thể bỏ sót drift.

### Ownership

Mỗi resource hoặc attribute nên có owner. Ví dụ platform team quản lý network, application team quản lý deployment, security team quản lý IAM policy. Nếu nhiều controller cùng sở hữu một thuộc tính, chúng có thể liên tục ghi đè lẫn nhau.

## 9. Ghép tài nguyên và identity matching

Comparator cần xác định desired resource nào tương ứng actual resource nào.

Một resource identity có thể bao gồm:

~~~text
ResourceIdentity
  provider
  accountOrProject
  regionOrZone
  resourceType
  stableProviderId
  logicalName
~~~

### Stable provider ID

Nếu provider cung cấp ID ổn định, nó thường là thành phần mạnh để ghép tài nguyên. Tuy nhiên, ID có thể thay đổi khi resource được recreate; khi đó cần xử lý lifecycle và mapping giữa logical identity với provider identity.

### Logical identity

Logical name trong DSL giúp liên kết tài nguyên với ý định của người dùng. Nhưng tên có thể trùng trong các namespace khác nhau nên cần scope.

### Rename và replacement

Nếu logical resource được rename nhưng provider ID giữ nguyên, hệ thống có thể nhận diện rename. Nếu provider ID đổi nhưng logical identity giữ nguyên, có thể là replacement. Đây là hai sự kiện khác với missing và unexpected độc lập.

### Ambiguous match

Nếu nhiều actual resource cùng phù hợp một desired identity, scanner nên báo ambiguous mapping thay vì chọn tùy tiện. So sánh sai tài nguyên có thể tạo remediation nguy hiểm.

## 10. Chuẩn hóa trước khi so sánh

Desired và actual thường được biểu diễn khác nhau. Provider có thể trả `8080` dưới dạng số, DSL lưu dưới dạng decimal; một giá trị mặc định có thể bị lược khỏi API; một set có thể được trả theo thứ tự không xác định. Cần normalization trước khi diff.

### Kiểu dữ liệu

Chuyển giá trị về kiểu chuẩn theo schema: integer, decimal, boolean, string, enum, duration, timestamp, CIDR, URI hoặc resource reference.

### Đơn vị

Chuẩn hóa đơn vị trước khi so sánh. Ví dụ DSL khai báo `2 GiB` còn API trả số byte. So sánh trực tiếp hai con số sẽ tạo false positive.

### Case sensitivity

Một số identifier không phân biệt hoa thường, nhưng string value có thể phân biệt. Quy tắc phải theo kiểu và semantics của thuộc tính, không áp dụng lowercase cho mọi chuỗi.

### Set và list

Nếu thuộc tính là set, thứ tự phần tử không có ý nghĩa và có thể chuẩn hóa bằng sort theo canonical key. Nếu là list có thứ tự, không được sắp xếp trước khi so sánh.

### Default value

Provider có thể không trả trường có giá trị mặc định. Comparator cần biết missing có tương đương default hay không. Quy tắc default nên gắn với API/provider version và schema version.

### Computed fields

Các trường do provider tự sinh như ARN, IP, timestamps hoặc status có thể không thuộc desired state. Chúng cần được đánh dấu computed hoặc informational.

### Volatile fields

Các trường thay đổi thường xuyên mà không phản ánh drift quản trị, như `lastObservedAt`, resource health timestamp hoặc usage counter, có thể bị loại khỏi managed comparison hoặc xử lý theo policy riêng.

### Canonicalization

Canonicalization chuyển hai representation tương đương về dạng chuẩn. Có thể bao gồm chuẩn hóa JSON object key, enum, decimal, timestamp timezone, CIDR và reference. Không được loại bỏ khác biệt có ý nghĩa chỉ để tăng tỷ lệ match.

## 11. Các loại cấu hình lệch

Drift có thể được phân loại theo bản chất khác biệt.

| Loại drift | Mô tả | Ví dụ |
|---|---|---|
| Missing resource | Desired resource không tồn tại trong actual. | Database replica bị xóa. |
| Unexpected resource | Actual có resource ngoài desired scope. | Một public IP được tạo thủ công. |
| Attribute drift | Giá trị thuộc tính khác nhau. | `replicas` là 3 thay vì 4. |
| Relationship drift | Quan hệ giữa resource khác desired. | Service gắn nhầm load balancer. |
| Access drift | Quyền hoặc exposure thay đổi. | Bucket bị chuyển sang public. |
| Version drift | Artifact hoặc package version khác. | Image chạy `2.8.0` thay vì `2.8.1`. |
| Metadata drift | Tag, label hoặc ownership metadata khác. | Thiếu tag `costCenter`. |
| Structural drift | Số lượng hoặc cấu trúc thành phần khác. | Thiếu một subnet trong nhóm. |
| Behavioral drift | Hành vi quan sát không đáp ứng policy mong muốn. | Backup job không chạy dù cấu hình bật. |
| Unknown state | Không thể xác minh actual. | API trả lỗi permission hoặc timeout. |

### Structural drift

Structural drift xảy ra khi cấu trúc tổng thể khác, ví dụ thiếu child resource, có thêm member hoặc quan hệ parent-child bị thay đổi. Nó thường cần so sánh graph thay vì chỉ so sánh field.

### Behavioral drift

Một cấu hình có thể giống desired nhưng hành vi thực tế không đạt kỳ vọng. Ví dụ `backupEnabled = true` nhưng backup job liên tục thất bại. Đây có thể là operational/compliance drift cần telemetry hoặc kiểm tra ngoài cấu hình thuần.

### Unknown không phải là in-sync

Nếu không đọc được trạng thái, hệ thống không có đủ bằng chứng để nói tài nguyên đồng bộ. Cần giữ trạng thái `UNKNOWN`, `UNOBSERVABLE` hoặc `SCAN_INCOMPLETE` riêng.

## 12. Thuật toán so sánh desired và actual

Comparator có thể hoạt động theo resource identity rồi duyệt các thuộc tính được quản lý.

Pseudocode khái quát:

~~~text
detectDrift(desiredResources, actualResources):
    desiredIndex = indexByIdentity(desiredResources)
    actualIndex = indexByIdentity(actualResources)
    differences = []

    for identity in union(keys(desiredIndex), keys(actualIndex)):
        desired = desiredIndex.get(identity)
        actual = actualIndex.get(identity)

        if desired exists and actual is missing:
            differences.add(MissingResource(identity))
            continue

        if actual exists and desired is missing:
            differences.add(UnexpectedResource(identity))
            continue

        compareManagedAttributes(desired, actual, differences)

    return classify(differences)
~~~

Trong thực tế, `actual is missing` cần phân biệt với `actual read failed`. Nếu API không thể truy cập, không được kết luận resource bị xóa.

### Attribute comparison

Với mỗi thuộc tính:

1. Kiểm tra thuộc tính có nằm trong managed scope không.
2. Resolve desired value và actual value.
3. Chuẩn hóa theo schema và provider adapter.
4. Áp dụng comparator phù hợp với kiểu.
5. Nếu khác, tạo difference chứa path và evidence.
6. Áp dụng classification, severity và suppression policy.

### Comparator theo kiểu

Không phải mọi giá trị đều dùng equality đơn giản:

- Scalar: so sánh giá trị sau normalization.
- Decimal: so sánh theo precision/scale được quy định.
- Set: so sánh membership không phụ thuộc thứ tự.
- Ordered list: so sánh thứ tự và nội dung.
- Map/object: so sánh từng field có quản lý.
- Range: kiểm tra actual nằm trong khoảng cho phép.
- Predicate: đánh giá điều kiện thay vì so sánh giá trị chính xác.
- Reference: so sánh resource identity, không chỉ tên hiển thị.

## 13. So sánh chính xác và so sánh theo policy

Một số thuộc tính cần khớp chính xác; một số khác chỉ cần nằm trong miền giá trị cho phép.

### Exact equality

Ví dụ, `encryption = true` có thể yêu cầu actual phải đúng là true. Với security setting quan trọng, exact equality giúp phát hiện mọi thay đổi không được phê duyệt.

### Allowed set

DSL có thể cho phép một trong các giá trị:

~~~text
allowed instanceType = ["m6i.large", "m6i.xlarge"];
~~~

Actual là một trong các giá trị đó thì không bị xem là drift dù không bằng một giá trị duy nhất.

### Numeric range

~~~text
allow replicas between 3 and 6;
~~~

Actual replicas 5 có thể được xem là hợp lệ. Cách này hữu ích khi autoscaler thay đổi số lượng trong một khoảng.

### Predicate-based comparison

~~~text
require network.cidr isWithin "10.20.0.0/16";
~~~

Comparator kiểm tra predicate thay vì đòi exact string equality.

### Set membership và subset

Một policy có thể yêu cầu actual permissions không được vượt quá allowlist. Khi đó actual có thể chứa ít quyền hơn desired mà vẫn đáp ứng một policy, nhưng có thể ảnh hưởng chức năng. Cần phân biệt compliance condition với desired-state equality.

### Tolerance

Với số đo hoặc giá trị có sai số, có thể cho phép tolerance. Nhưng tolerance phải có đơn vị và ý nghĩa rõ. Không nên dùng epsilon chung cho mọi kiểu số hoặc cho các thuộc tính bảo mật.

## 14. Cấu hình ignore, computed và ownership

Một drift detector hữu ích cần biết trường nào được quản lý, trường nào được provider tính và trường nào được phép thay đổi ngoài DSL.

### Managed attribute

Thuộc tính do DSL hoặc owner chỉ định. Khác biệt của nó thường là drift cần báo cáo.

### Computed attribute

Thuộc tính được provider sinh hoặc tính từ trạng thái khác. Nó có thể được lưu để tham khảo nhưng không được so sánh trực tiếp với desired value.

### Ignored attribute

Thuộc tính được cố ý loại khỏi drift comparison. Ví dụ một trường health timestamp thay đổi liên tục. Ignore rule cần phạm vi và lý do cụ thể.

### Shared ownership

Một thuộc tính có thể được controller khác quản lý. Ví dụ replica count do autoscaler sở hữu còn image do deployment pipeline sở hữu. Drift detector cần phân biệt ownership theo attribute, không chỉ theo resource.

### Ignore không nên là wildcard tùy tiện

Nếu cho phép ignore toàn bộ resource hoặc `*` mà không có thời hạn và phê duyệt, các drift nghiêm trọng có thể bị che giấu. Nên ưu tiên ignore path hẹp và gắn waiver với owner, lý do, ticket hoặc expiry.

## 15. Phát hiện drift trong DSL cấu hình

DSL có thể cung cấp cú pháp để định nghĩa resource, desired attributes, policy so sánh và hành vi khi phát hiện khác biệt.

Một ví dụ minh họa:

~~~text
environment production {
    resource service "orders" {
        desired {
            replicas = 4;
            image = "registry.example/orders:2.8.1";
            publicAccess = false;
        }

        observe using kubernetes;

        drift {
            replicas: exact;
            image: exact;
            publicAccess: exact severity critical;
        }
    }
}
~~~

DSL có thể tách ba khái niệm:

- Desired block mô tả trạng thái mong muốn.
- Observe block xác định nguồn actual state.
- Drift block mô tả cách so sánh và phân loại.

Một DSL khác có thể đặt policy ở cấp environment hoặc module. Điều quan trọng là semantics của từng khai báo được xác định rõ.

### Rule cho một thuộc tính

Ví dụ:

~~~text
driftRule "public-access" {
    target = service.publicAccess;
    expected = false;
    severity = critical;
    onDifference = alert;
}
~~~

Rule có thể chứa target expression, expected value hoặc predicate, severity, owner và remediation policy.

### Phạm vi và selector

DSL có thể chọn tài nguyên theo type, label, tag hoặc environment. Selector cần được resolve rõ để tránh một rule áp dụng ngoài ý định.

### Policy composition

Rule có thể kế thừa hoặc compose từ baseline chung. Cần quy định precedence khi policy môi trường ghi đè policy tổ chức, và cách xử lý khi hai rule mâu thuẫn.

## 16. Phân loại mức độ nghiêm trọng

Không phải drift nào cũng cần xử lý như nhau. Severity có thể dựa trên loại thuộc tính, độ phơi nhiễm, tác động nghiệp vụ và policy.

Một mô hình ví dụ:

| Mức | Ý nghĩa | Ví dụ |
|---|---|---|
| Critical | Có nguy cơ bảo mật hoặc gián đoạn nghiêm trọng. | Database encryption bị tắt; admin access bị mở công khai. |
| High | Có thể ảnh hưởng đáng kể đến tính sẵn sàng hoặc compliance. | Backup bị tắt; production chạy image không được phê duyệt. |
| Medium | Sai khác cần xử lý nhưng tác động giới hạn. | Replica thấp hơn baseline; thiếu network tag. |
| Low | Metadata hoặc khác biệt ít ảnh hưởng. | Description hoặc display label thay đổi. |
| Informational | Khác biệt được chấp nhận hoặc chỉ để quan sát. | Provider-generated ID hoặc trạng thái tự cập nhật. |

Severity không nên chỉ được suy ra từ giá trị khác nhau. Ví dụ, thay đổi một số cổng mạng có thể critical, còn thay đổi display name có thể low. Policy cần có khả năng gắn severity theo path và context.

### Risk scoring

Một hệ thống có thể tính risk score từ severity cơ bản, exposure, asset criticality, exploitability và thời gian tồn tại. Score cần giải thích được; không nên tạo một con số khó hiểu mà không lưu các yếu tố đóng góp.

### Aging

Drift tồn tại lâu có thể tăng mức ưu tiên. Report nên ghi first detected, last observed và thời gian unresolved. Không nhất thiết tăng severity tự động nếu điều đó làm thay đổi ý nghĩa policy; có thể tăng priority riêng.

## 17. Phân biệt drift hợp lệ và drift không được phép

Trong hệ thống động, một số thay đổi là bình thường. Autoscaling, rolling update, certificate rotation, dynamic IP và controller reconciliation có thể làm actual khác desired tĩnh.

### Managed variability

DSL có thể mô tả thuộc tính biến động theo policy:

~~~text
replicas = managedBy autoscaler {
    min = 3;
    max = 8;
}
~~~

Khi actual replica nằm trong khoảng và autoscaler là owner, khác biệt không nhất thiết là drift.

### Ephemeral resource

Pod, task hoặc instance tạm thời có thể được tạo và xóa liên tục. Nếu DSL chỉ quản lý deployment-level specification, không nên báo từng pod mới là unexpected resource.

### Controller-owned fields

Một controller có thể cập nhật annotation hoặc status field. Drift detector cần loại các field đó khỏi managed set hoặc so sánh theo policy của controller.

### Planned change window

Trong deployment window, actual có thể tạm thời ở trạng thái trung gian. Scanner có thể đánh dấu scan đang trong maintenance window hoặc chờ rollout ổn định trước khi báo drift cuối cùng.

### Approved exception

Một thay đổi khẩn cấp có thể được phê duyệt tạm thời. Exception cần expiry và phải được rà soát để tránh biến drift tạm thành cấu hình vĩnh viễn không được quản lý.

## 18. Phát hiện drift theo thời gian

Drift detection thường được chạy định kỳ hoặc kích hoạt khi có event.

### Periodic scan

Scanner chạy theo lịch, ví dụ mỗi 5 phút, mỗi giờ hoặc mỗi ngày tùy mức độ quan trọng và chi phí API. Periodic scan dễ triển khai và có thể phát hiện cả thay đổi không phát event.

### Event-driven detection

Provider phát event khi resource thay đổi. Event có thể kích hoạt scan hẹp cho resource hoặc dependency liên quan. Cách này giảm thời gian phát hiện nhưng phụ thuộc độ đầy đủ và độ tin cậy của event stream.

### Hybrid model

Kết hợp event-driven scan để phản ứng nhanh với periodic scan để kiểm tra lại và phát hiện event bị mất. Đây là mô hình phổ biến khi cần cân bằng latency và độ tin cậy.

### Detection latency

Detection latency là khoảng thời gian từ khi drift xảy ra đến khi hệ thống phát hiện. Nó phụ thuộc lịch scan, event delivery, queue, provider consistency và thời gian so sánh.

### Scan frequency và chi phí

Scan quá thường xuyên có thể tăng API cost, rate limit và tải provider. Scan quá thưa làm drift tồn tại lâu. Tần suất nên dựa trên criticality, thay đổi thường gặp, chi phí và SLA phát hiện.

## 19. Snapshot, baseline và lịch sử drift

Lưu lịch sử giúp trả lời khi nào drift bắt đầu, nó đã thay đổi ra sao và remediation có hiệu quả không.

### Snapshot

Snapshot là bản ghi trạng thái tại một thời điểm. Nó có thể chứa raw actual, normalized actual, desired revision và metadata scan.

### First seen và last seen

- `firstSeenAt`: lần đầu scanner quan sát difference.
- `lastSeenAt`: lần gần nhất difference vẫn tồn tại.
- `resolvedAt`: thời điểm difference không còn được quan sát.

Nếu một scan thất bại, không nên đánh dấu mọi drift đã resolved chỉ vì không có result mới.

### Baseline update

Khi một thay đổi actual được chấp nhận, có thể cập nhật desired configuration hoặc baseline. Cần lưu ai phê duyệt và revision mới. Không nên tự động chấp nhận mọi actual state làm baseline vì điều đó có thể hợp thức hóa một thay đổi trái phép.

### Historical comparison

So sánh snapshot hiện tại với snapshot trước giúp nhận diện thời điểm thay đổi và phân biệt drift mới với drift tồn tại lâu. So sánh với desired revision vẫn cần được thực hiện riêng.

### Retention

Snapshot có thể chứa cấu hình nhạy cảm. Retention policy cần cân bằng audit, điều tra và chi phí lưu trữ. Secret plaintext không nên được lưu trong lịch sử drift.

## 20. Drift trong hệ thống có nhiều controller

Một môi trường có thể được quản lý đồng thời bởi IaC tool, Kubernetes controller, autoscaler, secret manager và operator riêng. Nếu ownership không rõ, các controller có thể tạo ra vòng lặp ghi đè.

### Controller conflict

Controller A đặt replica về 4; autoscaler B đặt replica về 6; A lại phát hiện drift và đặt về 4. Hai bên liên tục sửa nhau.

### Field ownership

Có thể chia ownership theo resource hoặc attribute. Ví dụ:

| Thuộc tính | Owner |
|---|---|
| Container image | Deployment pipeline |
| Replica count | Autoscaler |
| CPU/memory request | Platform configuration |
| Runtime status | Orchestrator |
| Security labels | Security controller |

Drift detector chỉ so sánh desired của owner tương ứng hoặc áp dụng policy hợp nhất được xác định.

### Reconciliation loop

Controller thường lặp: observe, compare, plan, act và observe lại. Cần có convergence condition và giới hạn retry để tránh vòng lặp vô hạn khi provider không thể đạt desired.

### Conflict resolution

Nếu nhiều policy quản lý cùng một field, cần precedence rõ hoặc báo ownership conflict. Không nên chọn policy thắng theo thứ tự load tình cờ.

## 21. Remediation – xử lý sau khi phát hiện drift

Sau khi phát hiện, hệ thống có thể thực hiện nhiều mức phản ứng.

### Alert only

Gửi cảnh báo và giữ nguyên actual state. Phù hợp với môi trường cần người vận hành đánh giá tác động trước khi thay đổi.

### Plan only

Tạo remediation plan mô tả các thao tác cần thực hiện nhưng chưa apply. Người vận hành review diff, dependency, blast radius và approve.

### Manual remediation

Người có quyền thực hiện thay đổi qua quy trình vận hành. Sau đó scanner chạy lại để xác nhận trạng thái.

### Automatic reconciliation

Controller tự áp dụng desired state. Cách này phù hợp với thuộc tính có semantics rõ, có thể hội tụ an toàn và có cơ chế rollback hoặc recovery.

### Import actual into desired

Nếu actual change là có chủ đích, có thể cập nhật DSL để phản ánh trạng thái mới. Việc import cần review và tạo revision được phê duyệt, không chỉ ghi đè source bằng snapshot hiện tại.

### Không nên tự sửa mọi drift

Một số khác biệt có thể là dấu hiệu của sự cố hoặc thay đổi khẩn cấp. Tự động revert ngay có thể phá hỏng quá trình khắc phục. Remediation policy cần xét severity, ownership, maintenance window và loại tài nguyên.

## 22. Lập kế hoạch remediation an toàn

Một plan nên mô tả hành động và hậu quả trước khi thực thi.

Thông tin có thể gồm:

- Resource identity và environment.
- Desired revision và actual snapshot ID.
- Differences cần xử lý.
- Các operation create/update/delete.
- Dependency và thứ tự thực hiện.
- Dự kiến downtime hoặc impact.
- Required permissions.
- Backup/checkpoint cần thiết.
- Rollback hoặc compensation strategy.
- Preconditions và postconditions.
- Approval requirement.

### Blast radius

Thay đổi một network route có thể ảnh hưởng nhiều service. Plan nên tính các resource phụ thuộc và chỉ ra phạm vi tác động.

### Preconditions

Trước khi apply, xác nhận actual state vẫn giống snapshot đã dùng để tạo plan. Nếu tài nguyên đã thay đổi thêm, plan có thể stale và cần tạo lại.

### Postconditions

Sau apply, đọc lại actual state và xác nhận desired đã đạt. Không chỉ dựa vào exit code của lệnh apply.

### Rollback

Không phải mọi thay đổi đều có thể rollback chính xác. Xóa resource hoặc thay đổi dữ liệu có thể không đảo ngược. Plan cần mô tả giới hạn và yêu cầu backup khi phù hợp.

## 23. DSL policy cho drift và remediation

Một DSL có thể mô tả cách phát hiện và phản ứng với drift ở cấp resource hoặc environment.

Ví dụ:

~~~text
policy productionDrift {
    target environment.production;

    rule publicDatabase {
        when database.publicAccess == true;
        severity = critical;
        owner = SecurityTeam;
        action = alertImmediately;
    }

    rule replicaRange {
        when service.replicas notBetween 3 and 8;
        severity = medium;
        owner = PlatformTeam;
        action = createPlan;
    }

    rule imageVersion {
        when service.image != desired.service.image;
        severity = high;
        owner = ApplicationTeam;
        action = requireApproval;
    }
}
~~~

Ví dụ minh họa cách diễn đạt, không phải cú pháp chuẩn của một sản phẩm cụ thể. Một implementation cần định nghĩa target resolution, kiểu biểu thức, semantics của `notBetween`, owner identity và hành vi action.

### Rule priority

Nếu nhiều rule cùng match một difference, cần xác định có áp dụng tất cả, chọn rule cụ thể nhất hay dùng priority. Kết quả phải ổn định và có thể giải thích.

### Policy inheritance

Policy tổ chức có thể đặt baseline, environment bổ sung hoặc nới một số thuộc tính. Cần quy tắc precedence và giới hạn việc override các policy bắt buộc.

### Waiver

Một exception có thể được khai báo:

~~~text
waiver "temporary-scale-window" {
    target service.orders.replicas;
    reason = "Capacity test approved";
    approvedBy = PlatformLead;
    expiresAt = "2026-12-01T00:00:00Z";
}
~~~

Waiver cần được kiểm tra chữ ký hoặc nguồn phê duyệt theo hệ thống quản trị. Khi hết hạn, difference phải quay lại trạng thái được đánh giá bình thường.

## 24. Suppression và false positives

False positive xảy ra khi scanner báo drift dù khác biệt không phải drift theo semantics hoặc ownership. False positive nhiều làm người vận hành mất niềm tin và có thể bỏ qua cảnh báo thật.

Nguyên nhân phổ biến:

- Thứ tự set/list không được chuẩn hóa đúng.
- Provider trả default khác representation.
- Field computed bị so sánh như managed field.
- API eventual consistency.
- Resource identity ghép sai.
- Snapshot desired và actual lấy ở thời điểm không tương thích.
- Autoscaler hoặc controller khác sở hữu thuộc tính.
- Timestamp hoặc dynamic ID bị xem là drift.
- Thiếu schema version hoặc provider adapter cũ.

### Ignore rule

Ignore rule nên chỉ rõ resource selector, attribute path, lý do, owner, người phê duyệt và thời hạn. Nên có report riêng về những difference đang bị suppress.

### Suppression không xóa evidence

Difference bị suppress vẫn nên được lưu trong kết quả scan hoặc audit record. Điều này giúp xem lại quyết định và nhận diện trường hợp suppression che giấu một thay đổi đáng ngờ.

### Suppression có điều kiện

Có thể suppress khi actual nằm trong khoảng, thuộc maintenance window hoặc được controller xác nhận. Điều kiện phải được đánh giá theo snapshot có timestamp rõ.

### Theo dõi false-positive rate

Ghi nhận số cảnh báo bị đánh dấu false positive và nguyên nhân. Dữ liệu này giúp cải thiện normalization, provider adapter và policy.

## 25. Unknown state và lỗi quan sát

Không thể phát hiện drift chính xác nếu actual state không quan sát được.

Các trạng thái nên được phân biệt:

- `IN_SYNC`: đã quan sát đủ và không có difference trong phạm vi quản lý.
- `DRIFTED`: có ít nhất một difference được xác nhận.
- `UNKNOWN`: không đủ dữ liệu để kết luận.
- `READ_ERROR`: provider/API trả lỗi khi đọc.
- `PARTIAL`: chỉ một phần resource hoặc attribute được quan sát.
- `AMBIGUOUS`: không ghép được identity một cách duy nhất.
- `SUPPRESSED`: difference tồn tại nhưng đang được waiver/ignore có hiệu lực.
- `SCAN_INCOMPLETE`: scan chưa hoàn thành toàn bộ scope.

Một tài nguyên không được đọc vì permission error không thể được đánh dấu `IN_SYNC`. Tương tự, một trang API bị bỏ qua do pagination lỗi không thể được coi là không có tài nguyên.

### Retry

Lỗi transient như timeout hoặc throttling có thể retry với backoff. Lỗi authorization hoặc resource not found cần phân loại riêng; retry vô hạn không giải quyết được lỗi cấu hình quyền.

### Partial evidence

Nếu chỉ đọc được một số thuộc tính, report cần chỉ rõ field nào đã kiểm tra và field nào unknown. Không nên kết luận toàn resource in-sync khi một field quan trọng chưa được quan sát.

## 26. Security và quyền cho drift scanner

Drift scanner thường cần quyền đọc nhiều tài nguyên, đôi khi trên nhiều account hoặc environment. Cần giới hạn quyền và bảo vệ dữ liệu thu thập.

### Least privilege

Scanner chỉ nên có quyền đọc các thuộc tính cần thiết. Nếu có remediation, quyền ghi nên tách khỏi quyền scan và chỉ được cấp cho thành phần hoặc principal có nhiệm vụ apply.

### Read-only scan

Chế độ scan chỉ đọc giúp tách phát hiện khỏi thay đổi. Đây là lựa chọn phù hợp cho audit, baseline assessment và giai đoạn đầu triển khai.

### Secret handling

Không ghi secret plaintext vào desired snapshot, actual snapshot, diff hoặc log. Có thể so sánh secret bằng version, reference ID hoặc cryptographic fingerprint được thiết kế phù hợp, nhưng không nên tự hash secret yếu mà không xét nguy cơ dictionary attack.

### Redaction

Report có thể hiển thị `***REDACTED***` thay vì giá trị nhạy cảm. Tuy nhiên, comparator vẫn cần đánh giá giá trị an toàn ở phía server. Redaction chỉ áp dụng cho output, không được làm mất dữ liệu cần so sánh.

### Audit trail

Ghi nhận ai khởi chạy scan, principal nào đọc provider, desired revision nào được dùng, ai phê duyệt waiver và ai thực hiện remediation.

### Integrity của desired configuration

Nếu desired DSL có thể bị sửa bởi người không được phép, drift detector có thể so sánh actual với một baseline đã bị thay đổi trái phép. Cần kiểm soát repository, review, signature hoặc approval workflow theo mức độ rủi ro.

### Multi-tenant isolation

Snapshot và report của tenant này không được truy cập từ tenant khác. Resource identity, cache key, storage namespace và alert routing cần chứa tenant context khi phù hợp.

## 27. Drift detection trong Infrastructure as Code

IaC mô tả hạ tầng bằng code hoặc DSL. Drift detection giúp xác định môi trường thật còn khớp với cấu hình đã quản lý hay không.

Ví dụ resource khai báo:

~~~text
resource firewall "web" {
    ingress = [
        rule(443, source = "10.0.0.0/8"),
        rule(8443, source = "10.0.0.0/8")
    ];
}
~~~

Nếu actual firewall mở thêm port 22 từ `0.0.0.0/0`, scanner cần phát hiện một rule ngoài desired và phân loại critical. Nếu provider trả rule theo thứ tự khác, comparator phải so sánh tập rule theo identity hoặc nội dung chuẩn hóa.

### State file

Một số IaC system lưu mapping giữa logical resource và provider ID trong state file. Drift scan có thể dùng state này để biết resource nào được quản lý. State cần được bảo vệ vì có thể chứa metadata nhạy cảm và là cơ sở của nhiều thao tác quản lý.

### Plan refresh

Một công cụ có thể refresh actual state rồi tạo plan cho thấy khác biệt. Plan là artifact để review; cần biết nó được tạo từ desired revision và actual snapshot nào.

### Import resource

Resource đã tồn tại nhưng chưa được quản lý có thể được import vào state. Import không đồng nghĩa tự động chấp nhận toàn bộ cấu hình actual; cần tạo desired declaration và review.

### Destroy và replacement

Nếu resource bị missing hoặc identity thay đổi, plan có thể đề xuất create, replace hoặc destroy. Đây là thao tác có tác động lớn; không nên tự động thực hiện chỉ dựa trên một lần đọc thiếu dữ liệu.

## 28. Drift detection trong Kubernetes và hệ thống controller

Trong hệ thống khai báo như Kubernetes, người dùng mô tả desired object và controller liên tục quan sát actual state rồi reconcile.

### Spec và status

Thông thường, `spec` mô tả desired state còn `status` phản ánh trạng thái quan sát. Drift detector cần so sánh đúng phần được quản lý, tránh so `status` với desired `spec` như thể chúng cùng loại.

### Defaulting và admission mutation

API server hoặc admission controller có thể thêm default hoặc mutate object. Nếu desired DSL không mô tả các giá trị đó, canonicalization và schema cần biết chúng có được chấp nhận hay không.

### Server-side apply và field ownership

Một số hệ thống theo dõi manager sở hữu từng field. Ownership giúp xác định controller nào được phép thay đổi field và tránh xung đột. Drift detection nên tận dụng metadata ownership nếu provider cung cấp.

### Autoscaling

Replica count có thể do Horizontal Pod Autoscaler quản lý. Nếu manifest cũng cố định replicas, hai controller có thể conflict. Cần xác định owner và cách so sánh theo policy.

### Reconciliation loop

Controller có thể liên tục điều chỉnh actual về desired. Drift detector có thể theo dõi convergence time và báo nếu controller không đạt trạng thái mong muốn trong thời hạn.

## 29. Drift detection cho cấu hình ứng dụng và database

Không chỉ hạ tầng mới có drift.

### Application configuration

Ví dụ, feature flag, logging level, endpoint, retry policy hoặc environment variable có thể bị thay đổi trực tiếp trong production. Scanner so sánh config effective với revision được phê duyệt.

### Secret rotation

Secret value thay đổi theo rotation là thay đổi có chủ đích. Thay vì so plaintext, DSL có thể so secret reference, version hoặc rotation policy. Nếu version mới được cấp đúng theo policy, không nên báo drift.

### Database schema và parameter

Drift có thể là parameter thay đổi, extension bị bật/tắt, role được cấp thêm quyền hoặc schema không còn khớp migration mong muốn. Cần phân biệt schema migration hợp lệ với thay đổi thủ công ngoài migration pipeline.

### Access control

Grant/revoke quyền là một loại drift có rủi ro cao. Comparator cần chuẩn hóa principal identity, role inheritance và permission set. Không nên chỉ so tên hiển thị của role.

### Service mesh và network policy

Routing, timeout, retry, mTLS và access policy có thể thay đổi độc lập. Drift detection nên phân biệt desired policy với runtime counters hoặc status fields.

## 30. Drift trong hệ thống có secret và dynamic values

Secret và dynamic values thường tạo thách thức vì giá trị thay đổi hoặc không thể hiển thị.

### So sánh bằng reference

Thay vì lưu secret value trong DSL, cấu hình có thể tham chiếu đến secret manager:

~~~text
database credentials = secretRef("prod/orders/db-password");
~~~

Drift detector có thể so reference identity và version policy. Nếu policy yêu cầu version mới nhất, cần so actual secret version với version hiện tại được phê duyệt.

### Rotation window

Trong lúc rotation, actual có thể chuyển từ version cũ sang mới. Scanner cần biết trạng thái chuyển tiếp hợp lệ hoặc chỉ đánh giá sau khi rotation hoàn tất.

### Dynamic IP và endpoint

Nếu provider tự cấp IP, desired có thể chỉ khai báo subnet hoặc allocation policy. Comparator cần đánh giá thuộc subnet/region mong muốn thay vì exact string equality.

### Generated identifiers

Provider-generated ID thường là output cần lưu vào state, không phải giá trị desired cố định. Có thể dùng reference binding để các resource khác tham chiếu ID đó mà không coi ID thay đổi sau replacement là drift thuộc tính.

## 31. Báo cáo drift và quy trình xử lý

Một báo cáo tốt giúp người vận hành biết điều gì khác, ở đâu, từ khi nào, mức độ nào và cần ai xử lý.

Một report entry có thể gồm:

~~~text
Drift finding
  environment: production
  resource: firewall.web
  path: ingress[ssh]
  desired: absent
  actual: 0.0.0.0/0:22
  category: unexpected-access-rule
  severity: critical
  firstSeen: 2026-11-15T01:00:00Z
  lastSeen: 2026-11-15T02:00:00Z
  owner: SecurityTeam
  evidence: scan-2026-11-15-0200
~~~

### Summary dashboard

Dashboard có thể trình bày:

- Tổng số resource được scan.
- Số resource in-sync, drifted, unknown và scan incomplete.
- Số finding theo severity.
- Finding mới, unresolved và đã resolved.
- Drift theo environment, owner và resource type.
- Thời gian trung bình từ phát hiện đến xử lý.
- Các waiver sắp hết hạn.

### Alert routing

Critical security drift có thể gửi đến security on-call; drift về replica hoặc capacity có thể gửi đến platform team; metadata drift có thể vào backlog. Routing nên dựa trên owner và severity, không chỉ gửi tất cả cho một nhóm.

### Deduplication

Một difference có thể xuất hiện trong nhiều scan liên tiếp. Alerting cần giữ finding identity để cập nhật một incident đang mở thay vì tạo cảnh báo mới cho mỗi lần poll.

### Resolution

Khi difference không còn, report nên ghi `resolvedAt` và cách giải quyết nếu biết: desired được cập nhật, actual được revert, resource được import hoặc waiver được áp dụng. Không xóa lịch sử finding.

## 32. Đo lường hiệu quả drift detection

Các chỉ số giúp đánh giá hệ thống phát hiện có nhanh, đầy đủ và hữu ích không.

| Metric | Ý nghĩa |
|---|---|
| Scan coverage | Tỷ lệ resource/attribute trong scope đã quan sát thành công. |
| Detection latency | Thời gian từ thay đổi thực tế đến khi phát hiện. |
| Drift count | Số resource hoặc attribute đang lệch. |
| Unknown rate | Tỷ lệ trạng thái không thể xác minh. |
| False-positive rate | Tỷ lệ finding bị xác định là không phải drift. |
| Mean time to acknowledge | Thời gian từ alert đến khi có người nhận xử lý. |
| Mean time to remediate | Thời gian từ phát hiện đến khi được xử lý. |
| Recurrence rate | Tỷ lệ drift tái xuất hiện sau remediation. |
| API error/throttle rate | Mức lỗi và throttling khi thu thập actual state. |
| Suppression inventory | Số và tuổi của finding đang bị suppress. |

### Coverage quan trọng hơn một con số drift thấp

Nếu scanner chỉ đọc được một nửa tài nguyên, số drift thấp không có nghĩa môi trường tốt. Dashboard phải hiển thị coverage và unknown rate cùng drift count.

### Detection latency theo severity

Có thể đặt mục tiêu phát hiện khác nhau cho critical security setting và metadata ít quan trọng. Điều này giúp tối ưu chi phí scan.

### Recurrence

Nếu cùng một drift liên tục tái xuất hiện, có thể có controller conflict, ownership sai hoặc desired configuration chưa được cập nhật. Recurrence là tín hiệu để sửa nguyên nhân gốc.

## 33. Kiểm thử hệ thống drift detection

Kiểm thử cần xác nhận comparator đúng, provider adapter đáng tin cậy và trạng thái scan được quản lý chính xác.

### Unit test cho normalization

Kiểm tra decimal, unit conversion, timestamp, Unicode, case sensitivity, default values, set/list và null/missing.

### Comparator test

Tạo desired/actual fixture với các trường hợp in-sync, changed, missing, unexpected, relationship drift và unknown.

### Provider adapter test

Mock API response có pagination, throttling, eventual consistency, permission error và field không biết. Xác nhận adapter chuẩn hóa đúng và không biến read error thành missing resource.

### Identity matching test

Kiểm tra rename, replacement, duplicate name, provider ID change, cross-region resource và ambiguous match.

### Policy test

Kiểm tra severity, owner, allowed range, ignore, waiver expiry và policy precedence.

### Integration test

Tạo môi trường thử nghiệm, apply desired state, thay đổi một thuộc tính ngoài pipeline rồi chạy scanner. Xác nhận finding chứa đúng resource, path và evidence.

### Remediation test

Nếu có auto-reconcile, xác nhận precondition, approval, operation order, postcondition và rollback. Kiểm tra action không được chạy khi snapshot đã stale.

### Failure test

Giả lập API timeout, thiếu quyền, partial pagination, provider outage và scan bị hủy. Hệ thống phải báo unknown/incomplete thay vì in-sync.

## 34. Ví dụ so sánh thực tế

Desired configuration:

~~~text
environment production {
    resource database "orders" {
        desired {
            backupEnabled = true;
            encryption = "managed-key";
            maxConnections = 120;
        }
    }

    resource service "orders" {
        desired {
            replicas = 4;
            image = "registry.example/orders:2.8.1";
        }
    }
}
~~~

Actual snapshot:

~~~json
{
  "database": {
    "orders": {
      "backupEnabled": false,
      "encryption": "managed-key",
      "maxConnections": 120
    }
  },
  "service": {
    "orders": {
      "replicas": 3,
      "image": "registry.example/orders:2.8.1"
    }
  }
}
~~~

Kết quả normalized diff:

| Resource | Path | Desired | Actual | Classification |
|---|---|---|---|---|
| `database.orders` | `backupEnabled` | `true` | `false` | Attribute drift; high severity. |
| `service.orders` | `replicas` | `4` | `3` | Attribute drift; medium severity. |

Các thuộc tính `encryption`, `maxConnections` và `image` đang in-sync. Nếu replica count được autoscaler quản lý trong khoảng 3–8, finding replica có thể không được xem là drift theo policy, dù nó khác giá trị mong muốn tĩnh ban đầu. Điều này cho thấy comparator phải hiểu ownership và policy chứ không chỉ so sánh từng scalar.

## 35. Tích hợp drift detection vào CI/CD và vận hành

Drift detection có thể được chạy ở nhiều thời điểm trong vòng đời cấu hình.

### Trước deployment

Scan actual state trước khi apply để phát hiện thay đổi ngoài pipeline kể từ lần triển khai trước. Kết quả có thể ảnh hưởng plan hoặc yêu cầu review bổ sung.

### Sau deployment

Scan lại sau khi rollout ổn định để xác nhận desired state đã được áp dụng. Nếu actual không hội tụ, pipeline có thể đánh dấu deployment degraded hoặc tạo incident.

### Scheduled audit

Chạy scan định kỳ để phát hiện drift do thao tác thủ công hoặc controller khác.

### Pull request check

Một PR có thể hiển thị drift hiện tại và tác động dự kiến của desired change. Cần bảo đảm snapshot đủ mới và không biến scan read-only thành thao tác apply.

### Incident response

Trong sự cố, người vận hành có thể thay đổi nhanh actual state. Sau khi ổn định, drift report giúp ghi nhận thay đổi, quyết định cập nhật DSL hay hoàn nguyên và tạo audit trail.

## 36. Những lỗi thiết kế thường gặp

**So sánh raw JSON trực tiếp.** Thứ tự key, default và representation khác nhau có thể tạo false positive. Cần schema-aware normalization.

**Coi lỗi đọc là resource missing.** Permission error hoặc timeout không chứng minh tài nguyên đã bị xóa. Phải có trạng thái unknown riêng.

**Không phân biệt desired revision.** Nếu cấu hình thay đổi trong lúc scan, kết quả không thể tái lập. Cần pin revision và resolve variables nhất quán.

**Ghép tài nguyên chỉ bằng tên.** Tên trùng giữa account hoặc region có thể khiến so sánh nhầm resource. Cần identity đầy đủ.

**Coi mọi thuộc tính actual là managed.** Provider-generated và controller-owned fields sẽ tạo nhiều false positive. Cần ownership và computed metadata.

**Bỏ qua eventual consistency.** Scan ngay sau apply có thể thấy trạng thái trung gian và báo drift sai. Cần consistency window hoặc retry có giới hạn.

**Tự động sửa mọi khác biệt.** Revert một thay đổi khẩn cấp có thể gây gián đoạn. Cần remediation policy theo severity và approval.

**Không kiểm tra precondition trước apply.** Actual có thể đã thay đổi sau khi plan được tạo. Cần refresh hoặc reject stale plan.

**Ignore wildcard quá rộng.** Có thể che giấu drift bảo mật. Ignore cần hẹp, có owner, lý do và expiry.

**Không lưu bằng chứng.** Chỉ lưu trạng thái `DRIFTED` không đủ để audit hoặc điều tra. Cần path, values, revision và observation metadata.

**Không xử lý resource replacement.** ID đổi có thể là recreate hợp lệ hoặc drift. Cần phân biệt logical identity và provider identity.

**Không quản lý ownership giữa controller.** Hai controller có thể liên tục ghi đè cùng field. Cần field ownership và conflict detection.

**Không hiển thị coverage.** Một scan không đọc được nhiều resource vẫn có thể trông như không có drift nếu chỉ đếm finding.

## 37. Quy trình thiết kế drift detection cho một DSL cấu hình

Một quy trình thực tế có thể gồm:

1. **Xác định source of truth:** repository, approved revision, baseline hoặc policy registry.
2. **Định nghĩa managed scope:** environment, account, region, resource type và attribute ownership.
3. **Thiết kế resource identity:** logical ID, provider ID, namespace và replacement semantics.
4. **Định nghĩa actual-state providers:** API, agent, inventory và quyền đọc.
5. **Thiết kế snapshot:** desired revision, actual observation time, provider version và evidence.
6. **Xây normalization layer:** type, unit, default, ordering, computed/volatile fields và secret handling.
7. **Định nghĩa comparator:** exact, set, range, predicate, reference và graph comparison.
8. **Phân loại drift:** missing, unexpected, attribute, relationship, access, behavioral và unknown.
9. **Thiết kế policy:** severity, owner, suppression, waiver và precedence.
10. **Chọn scan strategy:** periodic, event-driven hoặc hybrid; xử lý rate limit và consistency.
11. **Thiết kế report/audit:** finding identity, first/last seen, evidence và retention.
12. **Định nghĩa remediation:** alert, plan, manual, auto-reconcile, import và rollback.
13. **Kiểm thử:** normalization, provider, identity, comparator, failure, security và end-to-end.
14. **Đo lường:** coverage, latency, false positives, unknown rate và recurrence.

## 38. Checklist cho một lần scan drift

Trước khi kết luận một môi trường in-sync hoặc drifted, cần xác nhận:

- Desired revision và environment đã được pin chưa?
- Variable, secret reference và dependency đã được resolve nhất quán chưa?
- Scope resource có đầy đủ và đúng account/region không?
- Provider API có đọc đủ các thuộc tính cần quản lý không?
- Pagination và rate limit đã được xử lý chưa?
- Snapshot actual có timestamp và nguồn rõ ràng không?
- Read error có được phân biệt với missing resource không?
- Resource identity có unique và không ambiguous không?
- Default, unit, case, ordering và computed field đã được chuẩn hóa chưa?
- Attribute ownership và ignore rule có hợp lệ không?
- Comparator có dùng đúng semantics của kiểu dữ liệu không?
- Severity và owner có được xác định không?
- Waiver có lý do, approval và expiry không?
- Finding có evidence đủ để giải thích difference không?
- Scan coverage và unknown rate có được hiển thị không?
- Remediation plan có precondition và postcondition không?
- Actual có được đọc lại sau khi apply không?

## 39. Kết quả cần có sau khi thiết kế drift detection

Một thiết kế phát hiện cấu hình lệch hoàn chỉnh thường cung cấp:

- **Desired-state contract:** nguồn sự thật, revision, environment variables và baseline.
- **Actual-state inventory:** provider adapters, resource discovery, timestamps và observation quality.
- **Identity model:** logical resource ID, provider ID, namespace, rename và replacement handling.
- **Managed-attribute schema:** managed, computed, volatile, ignored và controller-owned fields.
- **Normalization rules:** type, units, defaults, Unicode/case, set/list, secret references và canonicalization.
- **Comparison engine:** exact equality, range, set, predicate, reference và graph comparison.
- **Drift taxonomy:** missing, unexpected, attribute, relationship, access, version, structural, behavioral và unknown.
- **Policy model:** severity, owner, waiver, suppression, expiry và policy precedence.
- **Scan orchestration:** periodic/event-driven scheduling, consistency, retry, rate limit và partial-scan handling.
- **Evidence and reporting:** snapshots, differences, first/last seen, coverage, audit và alert routing.
- **Remediation contract:** alert, plan, approval, apply, reconciliation, postcondition và rollback.
- **Test and metrics:** provider failures, false positives, differential comparison, detection latency, coverage và recurrence.

Phát hiện cấu hình lệch giúp xác định môi trường thực tế có còn tuân thủ trạng thái mong muốn và baseline đã được phê duyệt hay không. Một triển khai đáng tin cậy cần pin desired revision, thu thập actual state có bằng chứng, ghép đúng resource identity, chuẩn hóa representation và so sánh theo semantics của từng thuộc tính. Nó phải phân biệt drift thật với computed value, thay đổi được controller sở hữu, trạng thái chưa quan sát được và exception có thời hạn. Khi detection được tách khỏi remediation, report có thể giải thích được và mọi thao tác sửa có precondition, approval cùng postcondition rõ ràng, DSL cấu hình trở thành nền tảng hữu ích để quản lý thay đổi ngoài quy trình mà vẫn bảo đảm an toàn vận hành.

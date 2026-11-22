# Khối đơn thể phân tán và phát hành đồng bộ nhiều dịch vụ

Một hệ thống có nhiều deployment, nhiều repository và nhiều database chưa chắc đã đạt được kiến trúc microservices độc lập. Nếu chỉ cần thay một API nhỏ mà phải sửa và phát hành đồng thời năm dịch vụ; nếu các service gọi nhau theo chuỗi dài, cùng ghi một database hoặc phụ thuộc chặt vào schema nội bộ; nếu một service không thể triển khai hay rollback khi service khác chưa nâng cấp, hệ thống có thể đã trở thành **khối đơn thể phân tán (Distributed Monolith)**.

Distributed Monolith có hình thức triển khai phân tán nhưng vẫn giữ coupling mạnh của một ứng dụng nguyên khối. Các thành phần chạy ở nhiều process hoặc container, song thay đổi nghiệp vụ, lỗi runtime và quy trình release vẫn lan qua nhiều dịch vụ. Tổ chức phải trả chi phí mạng, vận hành và debug của hệ phân tán nhưng chưa nhận được quyền tự chủ triển khai tương ứng.

**Phát hành đồng bộ nhiều dịch vụ** thường là một dấu hiệu của vấn đề này. Khi một thay đổi chỉ an toàn nếu nhiều service cùng nâng cấp trong một cửa sổ, contract giữa chúng chưa đủ tương thích hoặc ranh giới nghiệp vụ chưa được phân chia đúng.

Bài học này giải thích cách nhận diện distributed monolith, phân biệt nó với modular monolith và một hệ thống microservices có phối hợp release hợp lý, tìm nguyên nhân coupling, đánh giá tác động, rồi tháo gỡ từng bước bằng domain boundaries, ownership dữ liệu, contract compatibility, expand-contract, event-driven integration và rollout độc lập.

## 1. Distributed Monolith là gì?

**Distributed Monolith** là kiến trúc có nhiều thành phần triển khai riêng nhưng các thành phần phụ thuộc chặt đến mức phải thay đổi, kiểm thử, vận hành hoặc phát hành như một đơn vị lớn.

Ví dụ:

    Checkout Service
        |
        v
    Order Service
        |
        v
    Customer Service
        |
        v
    Pricing Service
        |
        v
    Inventory Service
        |
        v
    Payment Service

Mọi request phải đi qua nhiều service đồng bộ. Một service đổi tên field hoặc thay đổi response có thể buộc các service khác đổi theo cùng đợt. Nếu một mắt xích chậm, toàn bộ checkout chậm. Nếu một dependency deploy lỗi, nhiều chức năng cùng thất bại.

Một ví dụ khác là nhiều service có database riêng về mặt tên gọi nhưng thực tế cùng đọc và ghi các bảng trong một database chung. Mỗi team deploy service riêng nhưng một schema migration phải phối hợp nhiều team. Quyền sở hữu dữ liệu vẫn tập trung và mơ hồ.

Distributed Monolith không được xác định bởi số lượng service, số repository hay việc dùng Kubernetes. Nó được nhận diện qua **mức độ phụ thuộc khi thay đổi và vận hành**.

## 2. Modular Monolith và Microservices khác gì?

Cần phân biệt ba kiểu kiến trúc:

| Đặc điểm | Modular Monolith | Microservices tự chủ | Distributed Monolith |
| --- | --- | --- | --- |
| Runtime | Một ứng dụng/process hoặc một số runtime có chủ đích | Nhiều service độc lập | Nhiều service/process |
| Ranh giới code | Module rõ, dependency có kiểm soát | Service có domain boundary | Module/service phụ thuộc xuyên biên giới |
| Dữ liệu | Có thể dùng chung DB, nhưng module ownership rõ | Service sở hữu dữ liệu của mình | Nhiều service cùng sửa schema/bảng |
| Giao tiếp | Lời gọi module trong process | API/event theo contract | Chuỗi RPC dày đặc hoặc shared implementation |
| Phát hành | Một artifact/đợt release | Có thể release độc lập theo compatibility | Thường cần release train đồng bộ |
| Lỗi runtime | Phần lớn lỗi trong process | Có thể cô lập theo service | Lỗi một service dễ lan toàn hệ thống |
| Vận hành | Ít thành phần phân tán | Nhiều thành phần nhưng có tự chủ | Nhiều thành phần và chi phí phối hợp cao |
| Scaling | Theo ứng dụng/module được tách hợp lý | Theo workload/service | Thường phải scale cả chuỗi hoặc vẫn nghẽn ở shared dependency |

**Modular Monolith không phải một kiến trúc thất bại.** Nếu domain chưa ổn định, đội ngũ nhỏ hoặc transaction cần consistency mạnh, một ứng dụng đơn khối có module boundaries tốt có thể đơn giản và hiệu quả hơn việc phân tán quá sớm.

**Microservices không có nghĩa mọi service phải không bao giờ deploy cùng nhau.** Một số thay đổi xuyên service có thể cần rollout phối hợp, nhưng contract và quy trình nên cho phép các phiên bản tương thích cùng tồn tại trong một khoảng thời gian. Release đồng bộ thường xuyên cho thay đổi nhỏ là tín hiệu cần điều tra.

## 3. Các dấu hiệu nhận diện

Những biểu hiện phổ biến:

1. Một thay đổi field trong service A khiến B, C, D phải sửa code cùng lúc.
2. Pipeline release của một service luôn chờ các service khác deploy xong.
3. Không thể rollback riêng một service vì phiên bản cũ không tương thích với service còn lại.
4. Một request nghiệp vụ phải gọi đồng bộ qua nhiều service trước khi trả response.
5. Các service truy vấn trực tiếp database hoặc schema của nhau.
6. Nhiều service dùng chung entity/library nội bộ có thay đổi breaking.
7. Một service không thể chạy integration test nếu phải khởi động gần như toàn bộ hệ thống.
8. Khi một dependency lỗi, hàng loạt service timeout hoặc cạn thread/connection.
9. Team không biết ai sở hữu một bảng, event hoặc quy tắc nghiệp vụ.
10. Một thay đổi schema buộc mọi service phải nâng cấp cùng thời điểm.
11. Các service có cùng chu kỳ release chỉ vì dependency nội bộ, không phải vì nhu cầu nghiệp vụ.
12. Một lỗi nhỏ cần phối hợp nhiều nhóm và nhiều cửa sổ triển khai.
13. Không thể chạy hai phiên bản API/provider cùng lúc trong giai đoạn rollout.
14. Một service chỉ có ý nghĩa khi chạy cùng một tập service khác đã được khóa phiên bản.

Không phải mỗi dấu hiệu riêng lẻ đều chứng minh distributed monolith. Ví dụ một đợt nâng cấp protocol lớn có thể cần phối hợp có kế hoạch. Cần nhìn tần suất, mức độ, lý do và khả năng triển khai độc lập trong các thay đổi bình thường.

## 4. Vì sao distributed monolith hình thành?

### 4.1. Chia service theo tầng kỹ thuật thay vì năng lực nghiệp vụ

Ví dụ tách thành:

- User CRUD Service.
- Database Access Service.
- Validation Service.
- Notification Utility Service.
- Common Business Service.

Một use case đơn giản phải gọi nhiều service nhỏ. Những service này không sở hữu capability hoàn chỉnh; chúng chỉ phân tán các bước của cùng một nghiệp vụ.

Một ranh giới tốt thường xoay quanh capability/bounded context như Order, Billing, Inventory hoặc Customer Profile. Nó có dữ liệu, quy tắc và hợp đồng riêng đủ rõ để tiến hóa.

### 4.2. Shared database và shared schema

Nếu Order Service và Billing Service cùng sửa bảng orders, cả hai phụ thuộc vào cột, index, constraint và transaction của nhau. Database có thể trở thành integration interface ngầm.

Một team đổi cột hoặc constraint sẽ ảnh hưởng service còn lại. Dù process tách riêng, quyền sở hữu dữ liệu vẫn chưa tách.

### 4.3. Synchronous call chain quá dài

Một API có thể gọi 5-8 service tuần tự. Mỗi hop thêm latency, timeout và failure mode. Các service không thể phục vụ chức năng khi một dependency không thiết yếu bị lỗi.

Nếu mỗi service lại retry, tổng số request và thời gian chờ có thể tăng mạnh.

### 4.4. Contract không có compatibility

Provider đổi field, enum hoặc semantics ngay khi deploy. Consumer cũ không đọc được response mới. Đội ngũ buộc phải phát hành provider và tất cả consumer cùng lúc.

### 4.5. Shared library chứa domain logic

Một thư viện common chứa JPA entities, business rules, DTO và repository được nhiều service import. Chỉ cần đổi class hoặc field là phải rebuild/redeploy tất cả consumers.

Shared library cho logging, tracing, authentication client hoặc utility ổn định có thể hữu ích. Vấn đề nằm ở việc dùng library để chia sẻ **mô hình dữ liệu và quy tắc nghiệp vụ thay đổi thường xuyên** giữa các service.

### 4.6. Distributed transaction và lockstep workflow

Các service cùng cần một transaction nguyên tử nhưng không có ranh giới aggregate rõ. Đội ngũ sử dụng transaction coordinator hoặc gọi tuần tự rồi cố rollback thủ công. Kết quả là các service vẫn phụ thuộc chặt vào cùng một workflow.

### 4.7. Một repository không có boundary rõ

Monorepo tự nó không tạo distributed monolith. Tuy nhiên nếu mọi service cùng build từ một shared source model, release version bị khóa và thay đổi module nào cũng phải build toàn bộ, monorepo có thể làm lộ coupling sẵn có.

Ngược lại, nhiều repository cũng không bảo đảm tự chủ nếu API và database phụ thuộc chặt.

## 5. Coupling có nhiều lớp

Để sửa đúng nguyên nhân, cần phân loại coupling:

| Lớp | Ví dụ | Dấu hiệu |
| --- | --- | --- |
| Domain coupling | Service B phụ thuộc quy tắc nội bộ của A | Thay business rule A buộc đổi B |
| Data coupling | Cùng sửa bảng hoặc đọc schema nội bộ | Migration DB cần release nhiều service |
| Contract coupling | Payload/API breaking | Consumer phải nâng cấp đồng thời |
| Temporal coupling | A chỉ hoạt động khi B đang online | Dependency outage làm A ngừng |
| Deployment coupling | Artifact phải phát hành cùng đợt | Không thể rollout/rollback độc lập |
| Operational coupling | Dùng chung pool, queue hoặc quota | Một service làm cạn tài nguyên service khác |
| Organizational coupling | Nhiều team cùng sở hữu một capability | Thay đổi cần phối hợp liên tục |
| Security coupling | Dùng chung credential hoặc quyền DB rộng | Khó giới hạn blast radius |

Một kiến trúc có thể đã tách database nhưng vẫn coupling về domain và deployment. Cần xử lý các lớp ảnh hưởng trực tiếp tới mục tiêu tự chủ, không chỉ đổi topology.

## 6. Ví dụ: release đồng bộ vì thay đổi response

Giả sử Customer Service v1 trả:

    {
      "id": "c-123",
      "name": "An"
    }

Order Service đang đọc field name. Sau đó Customer Service muốn đổi thành displayName và bỏ name:

    {
      "id": "c-123",
      "displayName": "An"
    }

Nếu provider deploy ngay phiên bản mới, Order Service cũ có thể nhận null hoặc lỗi deserialize. Đội ngũ buộc phải:

1. Sửa Order Service.
2. Build lại.
3. Deploy Customer Service và Order Service cùng cửa sổ.
4. Phối hợp rollback nếu một trong hai lỗi.

Đây là contract coupling.

Cách chuyển tương thích hơn:

**Bước 1:** Customer Service thêm displayName nhưng vẫn giữ name.

    {
      "id": "c-123",
      "name": "An",
      "displayName": "An"
    }

**Bước 2:** Deploy provider tương thích trước.

**Bước 3:** Order Service chuyển sang displayName và được phát hành riêng.

**Bước 4:** Theo dõi usage, xác nhận không còn consumer đọc name.

**Bước 5:** Đánh dấu name deprecated, sau cửa sổ tương thích mới xóa.

Nhờ expand-contract, provider v2 và consumer v1 có thể cùng chạy tạm thời.

## 7. Shared database là nguồn coupling thường gặp

Ví dụ:

    Order Service --------+
                         |
    Billing Service -----+----> shared_db
                         |        orders
    Support Service -----+        customers
                                  payments

Nếu mọi service đều có quyền SELECT/UPDATE trực tiếp các bảng, không có owner rõ. Một team có thể thay đổi dữ liệu mà không đi qua validation của service sở hữu nghiệp vụ.

Các bước tháo coupling:

1. Xác định owner cho từng bảng/aggregate.
2. Thu thập mọi reader/writer, bao gồm job, BI và script vận hành.
3. Chuyển lệnh ghi qua API/command của owner.
4. Với query đọc lớn, xây projection hoặc read model có contract.
5. Dùng outbox/CDC để đồng bộ dữ liệu cần thiết.
6. Thu hồi quyền truy cập trực tiếp của consumer sau khi xác minh.
7. Chỉ tách physical database khi lợi ích về ownership, scaling, bảo mật hoặc vận hành đủ lớn.

**Database-per-service là quyền sở hữu logic trước khi là số lượng máy database.** Có thể bắt đầu bằng schema/role riêng trong cùng cluster, miễn là consumer không tự sửa dữ liệu của owner.

## 8. Synchronous call chain và temporal coupling

Ví dụ checkout:

    Gateway
      -> Order
          -> Customer
              -> Pricing
                  -> Inventory
                      -> Payment
                          -> Notification

Nếu Notification lỗi, có cần checkout thất bại không? Nếu Pricing chậm, Order giữ worker bao lâu? Nếu Inventory timeout sau khi reservation thành công, Order có biết kết quả không?

Phân loại dependency theo tính cần thiết:

- **Critical synchronous:** phải có câu trả lời trước khi xác nhận giao dịch, ví dụ kiểm tra reservation theo contract.
- **Non-critical synchronous:** có thể bỏ qua hoặc dùng projection/cache nếu policy cho phép.
- **Asynchronous side effect:** email, analytics hoặc report thường có thể xử lý sau khi business event đã commit.
- **Read model:** có thể được cập nhật eventual từ events.

Giảm số hop trong critical path. Chuyển những công việc có thể xử lý sau sang event/job bền vững. Tuy nhiên không biến một command cần xác nhận thành event fire-and-forget nếu caller phải biết kết quả trước khi commit nghiệp vụ.

### 8.1. Timeout không loại bỏ temporal coupling

Nếu Order gọi Customer với timeout 2 giây, Order vẫn phụ thuộc Customer trong hai giây đó. Khi Customer lỗi, hàng nghìn request có thể giữ thread/connection.

Cần deadline tổng, bulkhead, circuit breaker và fallback theo nghiệp vụ. Nhưng những cơ chế này giảm blast radius, không tự sửa ranh giới domain.

## 9. Shared library và mô hình dữ liệu dùng chung

Một thư viện common như sau có thể gây lockstep:

    common-domain
      CustomerEntity
      OrderEntity
      PaymentEntity
      CustomerRepository
      BusinessValidationRules
      SharedStatusEnum

Mọi service import chung model. Một thay đổi field hoặc annotation có thể buộc phát hành lại tất cả.

Nên chia sẻ có chọn lọc:

**Thường có thể chia sẻ:** logging/tracing conventions, stable protocol utilities, security primitives đã version hóa, generated API client từ contract.

**Cần cân nhắc kỹ:** DTO nghiệp vụ, entity ORM, repository, enum thay đổi thường xuyên, business rule và database migration.

Một service consumer nên có model riêng phù hợp use case. Ví dụ Order cần customer display snapshot có thể định nghĩa DTO OrderCustomerSnapshot thay vì import CustomerEntity từ Profile.

**Code reuse không đồng nghĩa ownership chung.** Có thể dùng schema/IDL để sinh client mà không chia sẻ implementation hoặc database entity.

## 10. Deployment coupling: không thể phát hành độc lập

Các nguyên nhân thường thấy:

- API provider thay đổi breaking.
- Consumer yêu cầu field mới ngay lập tức.
- Database migration xóa field trước khi consumer chuyển.
- Nhiều service dùng chung artifact/version.
- Config hoặc secret đổi cùng lúc nhưng không có compatibility window.
- Event schema mới không đọc được bởi consumer cũ.
- Release pipeline buộc chờ một tập service không có lý do kỹ thuật.
- Smoke test chỉ chạy khi toàn bộ stack được triển khai cùng nhau.

Một pipeline độc lập cần:

- Build/test artifact riêng.
- Contract tests với provider/consumer.
- Compatibility checks.
- Deploy canary hoặc rolling.
- Health/business checks.
- Rollback theo service.
- Observability để phát hiện consumer lỗi khi provider đổi.

Nhưng tách pipeline chỉ giải quyết một phần. Nếu API và dữ liệu vẫn breaking, pipeline riêng chỉ làm sự cố khó phối hợp hơn.

## 11. Phân biệt release đồng bộ hợp lý và anti-pattern

Có những thay đổi thực sự cần phối hợp, ví dụ:

- Một protocol mới không thể chạy cùng protocol cũ.
- Một thuật toán phân tán cần đổi epoch/consensus theo một thủ tục migration.
- Một invariant cross-service được thiết kế lại và cần cutover theo workflow.
- Một lỗ hổng bảo mật buộc thu hồi contract cũ theo thời hạn khẩn cấp.

Tuy nhiên, các trường hợp này nên là ngoại lệ có kế hoạch.

| Tình huống | Release đồng bộ có hợp lý? | Hướng xử lý |
| --- | --- | --- |
| Thêm field optional vào response | Thường không | Provider thêm trước, consumer nâng cấp sau |
| Đổi tên field và xóa field cũ | Có thể cần một cửa sổ, nhưng nên tránh big bang | Expand-contract |
| Thay business rule nội bộ provider | Thường không | Giữ contract và semantics ổn định |
| Thay event schema breaking | Có thể cần migration | Version event, consumer tương thích, replay |
| Chuyển ownership dữ liệu | Có cutover phối hợp | Backfill, delta, fencing và reconciliation |
| Thay protocol bảo mật khẩn cấp | Có thể phải phối hợp | Rollout theo policy và deadline rõ |
| Chia một aggregate có invariant atomic | Có thể cần thay đổi thiết kế lớn | Đánh giá lại domain boundary |

Mục tiêu không phải cấm mọi release phối hợp. Mục tiêu là giảm những đợt phát hành đồng bộ không cần thiết và làm rõ các lần thực sự cần phối hợp.

## 12. Tác động đến độ tin cậy và hiệu năng

Distributed monolith có thể chịu cả hai loại chi phí:

**Chi phí phân tán:** network latency, serialization, connection pools, DNS, retries, broker, deployment, monitoring và incident coordination.

**Chi phí nguyên khối:** thay đổi lan rộng, shared state, release lockstep, blast radius và quyền sở hữu mơ hồ.

Một request qua N service tuần tự có latency gần bằng tổng thời gian từng hop cộng network/queue overhead. Tail latency có thể tệ hơn vì một hop chậm kéo toàn request vượt deadline.

Nếu mỗi hop có xác suất lỗi độc lập p, xác suất tất cả N hop thành công theo mô hình đơn giản là (1-p)^N. Ví dụ mỗi hop thành công 99,9%, chuỗi 8 hop có xác suất thành công khoảng 99,2% trong cùng khoảng đo. Đây chỉ là mô hình minh họa; lỗi thực tế có thể tương quan và phụ thuộc retry, nhưng nó cho thấy việc thêm hop làm tăng bề mặt lỗi.

Khi một service lỗi, các service gọi nó có thể retry, giữ thread và tạo cascading failure. Distributed monolith thường có nhiều failure domains trên sơ đồ nhưng blast radius lại gần như toàn hệ thống.

## 13. Tìm coupling bằng dependency map

Hãy vẽ hai loại sơ đồ:

**Runtime dependency graph:** service nào gọi service nào, theo giao thức gì, có đồng bộ không, critical path nào.

**Change/deployment graph:** thay đổi ở service/schema/event nào buộc service khác thay đổi hoặc deploy.

Ví dụ:

    Customer DB schema
       |             |
       v             v
    Order Service  Support Service
       |             |
       v             v
    Checkout API   Admin API

Nếu Customer đổi một cột khiến cả Order và Support phải deploy, đó là data/contract coupling. Nếu Order gọi Support API trong critical path, có thể còn sai dependency direction.

Một bảng inventory:

| Quan hệ | Kiểu coupling | Mức độ | Bằng chứng |
| --- | --- | --- | --- |
| Order → Customer API | Synchronous | Cao nếu nằm trong checkout path | Trace, timeout, p99 |
| Billing → Order DB | Data/shared schema | Cao | DB audit/query logs |
| Service A/B → common-domain | Code/version | Trung bình/cao | Build graph, release history |
| Order → Notification | Temporal | Không cần thiết nếu chờ email | Call graph |
| Consumer → Event v1 | Contract | Tùy compatibility | Schema registry/contracts |

Không cần lập bản đồ hoàn hảo toàn hệ thống ngay từ đầu. Chọn một capability có nhiều coupling và đo trước/sau.

## 14. Chọn đúng bounded context trước khi tách

Một service boundary nên dựa trên:

- Business capability và ngôn ngữ domain.
- Quyền sở hữu aggregate và invariant.
- Tần suất thay đổi của business rules.
- Mô hình dữ liệu và vòng đời.
- Nhu cầu scaling/availability/security.
- Team ownership và khả năng vận hành.
- Các giao tiếp thực sự cần đồng bộ.

Nếu hai nhóm dữ liệu luôn cần cùng một transaction và thay đổi cùng nhau, chúng có thể thuộc cùng bounded context. Nếu một capability có thể phát triển độc lập với contract rõ, tách có thể hữu ích.

Không tạo service cho mỗi bảng hoặc mỗi CRUD endpoint. Service quá nhỏ làm tăng network hops và chi phí điều phối, dễ tạo distributed monolith ở mức chi tiết hơn.

## 15. Cách tháo coupling theo thứ tự

Một lộ trình an toàn:

1. **Đo hiện trạng:** release frequency, coordinated release count, dependency hops, shared DB access, change failure rate, p95/p99 và incident blast radius.
2. **Chọn một capability:** ưu tiên nơi có ranh giới nghiệp vụ rõ và pain point thực.
3. **Xác định owner:** dữ liệu, invariants, API/event và team chịu trách nhiệm.
4. **Ổn định contract:** thêm compatibility và error semantics.
5. **Tách shared data access:** chuyển writes về owner, dựng projection cho readers.
6. **Giảm synchronous chain:** chuyển side effects không thiết yếu sang async.
7. **Bảo vệ runtime:** timeout, retry budget, circuit breaker, bulkhead.
8. **Tách build/release pipeline:** artifact độc lập, contract tests và canary.
9. **Rollout dần:** chuyển một consumer/tenant/cohort, quan sát rồi mở rộng.
10. **Xóa legacy coupling:** thu hồi quyền DB, bỏ shared DTO và endpoint cũ khi hết phụ thuộc.

Không nên bắt đầu bằng việc chia toàn bộ hệ thống thành hàng chục service mới. Một modular monolith được làm rõ boundary đôi khi là bước trung gian hợp lý.

## 16. Expand-contract để phá lockstep release

Một thay đổi schema/API có thể được chia thành các bước tương thích.

Ví dụ database cũ có cột full_name, schema mới muốn given_name và family_name.

**Expand:**

- Thêm given_name và family_name, giữ full_name.
- Deploy code đọc được cả hai dạng.
- Ghi hai dạng hoặc có một nguồn canonical với đồng bộ được kiểm soát.

**Migrate:**

- Backfill dữ liệu cũ.
- Theo dõi mismatch và records không thể tách tự động.
- Deploy consumers chuyển sang field mới.

**Contract:**

- Xác nhận không còn reader/writer dùng full_name.
- Ngừng ghi field cũ.
- Sau cửa sổ tương thích, xóa full_name.

Không làm tất cả trong một migration phá hủy. Với dữ liệu không thể chuyển đổi chắc chắn, cần quarantine hoặc quy tắc nghiệp vụ được phê duyệt.

### 16.1. Nhiều phiên bản cùng tồn tại

Trong rollout, có thể đồng thời có:

    Provider v1 / Provider v2
    Consumer v1 / Consumer v2

Một contract tốt định nghĩa ma trận phiên bản nào tương thích. Consumer cũ vẫn chạy được khi provider mới đã deploy; provider cũ vẫn chạy được trong thời gian consumer nâng cấp nếu cần.

Compatibility không chỉ là field optional. Còn có enum, default, nullability, semantics, ordering, status codes và authorization.

## 17. Contract-first và consumer-driven tests

Contract-first định nghĩa API/event trước implementation:

- OpenAPI cho REST.
- Protobuf cho gRPC.
- AsyncAPI/Avro/JSON Schema cho event.
- Schema registry và compatibility policy.
- Error catalog và semantics.

Consumer-driven contract tests ghi lại kỳ vọng thực tế của consumers; provider chạy tests trước release để phát hiện breaking changes.

Ví dụ consumer kỳ vọng:

- Response luôn có customerId.
- displayName có thể null theo policy.
- Unknown optional field được bỏ qua.
- 409 biểu thị version conflict.
- 429 có Retry-After nếu provider có thể cung cấp.

Contract tests không chứng minh performance, security hoặc resilience. Vẫn cần integration/load tests và authorization tests.

## 18. Tách database ownership

Một mục tiêu là mỗi service chỉ ghi dữ liệu do mình sở hữu.

Ví dụ:

    Order Service -> order_db
    Billing Service -> billing_db
    Inventory Service -> inventory_db
    Customer Service -> customer_db

Không nhất thiết phải là bốn database server riêng; có thể là schema/role/database riêng trên cùng cluster trong giai đoạn đầu. Điều cần bảo đảm:

- Consumer không ghi bảng của service khác.
- Read access cũng có contract và owner.
- Schema migration của owner không phá consumer.
- Data projection có freshness và rebuild policy.
- Cross-service references dùng ID/contract thay FK vật lý.
- Backup, restore, retention và quyền truy cập được xác định theo owner.

Nếu dùng shared cluster, tài nguyên vẫn có thể cạnh tranh. Logical ownership giảm coupling; performance isolation có thể cần pool/quota/shard riêng.

## 19. Thay direct DB reads bằng API hoặc projection

Không phải mọi read đều cần gọi API đồng bộ.

**Owner API:** khi caller cần dữ liệu mới và provider có thể phục vụ trong deadline.

**Projection/event:** khi query nhiều, có thể chấp nhận eventual consistency.

**Snapshot:** khi cần giữ sự thật tại thời điểm giao dịch.

Ví dụ:

- Checkout gọi Customer API để xác nhận địa chỉ đang hợp lệ.
- Order lưu snapshot địa chỉ khi đơn confirmed.
- Search nhận CustomerUpdated để làm mới index.
- Analytics tiêu thụ event stream hoặc ETL.

Tránh thay một query SQL local bằng 10 API call đồng bộ. Contract mới phải phù hợp use case và latency budget.

## 20. Tháo synchronous chain và chuyển side effects sang async

Một luồng trước:

    Order
      -> Payment
      -> Notification
      -> Analytics
      -> Search Index

Nếu email hoặc analytics không cần xác nhận trước khi Order commit, có thể phát OrderConfirmed event sau transaction và để consumer xử lý độc lập.

Transactional Outbox bảo đảm business record và event intent cùng commit. Consumer cần Inbox/idempotency vì delivery có thể lặp.

Đối với Inventory/Payment, cần xem semantics. Một command cần kết quả trước khi xác nhận đơn có thể vẫn là request/response hoặc workflow có trạng thái pending; không chuyển sang fire-and-forget chỉ để giảm coupling.

## 21. Giảm shared library coupling

Một common library nên ưu tiên:

- Logging/tracing helpers.
- Stable HTTP client configuration.
- Security primitives và protocol utilities.
- Generated client từ OpenAPI/Protobuf.
- Những abstraction kỹ thuật ít thay đổi.

Hạn chế chia sẻ:

- JPA entity và repository.
- Database migration.
- Business rule.
- Mutable DTO của một domain.
- Enum được nhiều service dùng nhưng không có compatibility policy.

Consumer nên sở hữu model riêng cho use case. Generated API client có thể giúp đồng nhất contract nhưng phải version hóa và không chứa business model nội bộ của provider.

## 22. Release pipeline độc lập

Một service có thể có pipeline:

    Source change
       |
       v
    Unit tests
       |
       v
    Build immutable artifact
       |
       v
    Contract + integration checks
       |
       v
    Security/image scan
       |
       v
    Deploy canary
       |
       v
    Business health + SLO checks
       |
       v
    Progressive rollout
       |
       v
    Complete / rollback service

Để release độc lập thực sự:

- Artifact có version rõ và immutable.
- Config tương thích với phiên bản đang chạy.
- Database migration theo expand-contract.
- Provider/consumer contract tests.
- Rollback không yêu cầu tất cả service quay lại cùng lúc.
- Observability xác định lỗi do version nào.
- Feature flag có owner, audit và sunset date.
- Có canary và stop conditions.

Không nên đánh giá autonomy chỉ bằng việc mỗi service có pipeline riêng. Nếu pipeline nào cũng phải chờ một release train chung thì coupling vẫn còn.

## 23. Canary và progressive delivery

Khi contract mới được triển khai:

1. Chọn một tỷ lệ traffic/tenant nhỏ.
2. Chạy provider version mới song song với phiên bản cũ nếu kiến trúc hỗ trợ.
3. Kiểm tra error rate, latency, consumer compatibility và business outcome.
4. Mở rộng theo từng bước.
5. Dừng rollout nếu có regression.
6. Rollback đúng service hoặc chuyển traffic theo policy.

Canary không giải quyết incompatibility cơ bản. Phải có version compatibility trước khi cho nhiều phiên bản chạy cùng lúc.

Đối với command có side effect, không gửi duplicate request đến hai phiên bản để so sánh kết quả. Shadow traffic chỉ nên dùng với read không side effect hoặc môi trường test.

## 24. Resilience để giảm coupling runtime

Một hệ thống độc lập vẫn cần gọi dependency. Mục tiêu là dependency failure không tự động biến thành outage toàn hệ thống.

Các cơ chế:

- **Deadline/timeout:** giới hạn thời gian chờ và giữ tài nguyên.
- **Retry có giới hạn:** chỉ retry transient failure và command idempotent.
- **Circuit breaker:** ngừng gọi dependency đang lỗi để tránh tích lũy request.
- **Bulkhead:** tách concurrency/pool theo dependency hoặc workload.
- **Bounded queue/backpressure:** giới hạn backlog.
- **Fallback:** chỉ dùng khi đúng business semantics và freshness policy.
- **Load shedding:** từ chối công việc không thiết yếu khi quá tải.
- **Idempotency:** chống side effect lặp.
- **Observability:** biết dependency nào gây lỗi và blast radius ra sao.

Resilience giảm hậu quả của coupling runtime; nó không thay thế việc sửa domain/data/deployment boundaries.

## 25. Phân biệt lỗi dependency với lỗi nghiệp vụ

Ví dụ API Customer:

- 400: request không hợp lệ.
- 401/403: authentication/authorization.
- 404: tài nguyên không tồn tại hoặc không được phép tiết lộ.
- 409: conflict/version.
- 422: business validation.
- 429: quota.
- 503/504: dependency/service unavailable hoặc timeout theo contract.

Không retry business rejection như thể dependency đang lỗi. Không fallback authorization thành allow. Không biến payment timeout thành FAILED khi kết quả bên ngoài chưa rõ.

Contract ổn định cần có error code và semantics, không phụ thuộc exception class của provider.

## 26. Organizational coupling cũng là vấn đề kiến trúc

Nếu nhiều team cùng chịu trách nhiệm cho một service hoặc một schema, thay đổi cần họp và phối hợp thường xuyên.

Một capability nên có owner chịu trách nhiệm:

- Domain model và invariants.
- API/event contracts.
- Data lifecycle và migration.
- SLO, incident và on-call.
- Backward compatibility và deprecation.
- Release/rollback.

Team topology có ảnh hưởng tới service boundaries. Nếu tổ chức không có khả năng vận hành độc lập một số service, việc chia quá nhỏ có thể tăng handoff và giảm tốc độ. Ranh giới kỹ thuật cần phù hợp với ownership thực tế.

Không nên ép mỗi team có một database vật lý riêng nếu không có năng lực vận hành; bắt đầu bằng quyền ghi, schema ownership và hợp đồng có thể là bước thực tế hơn.

## 27. Đo mức độ tự chủ sau khi thay đổi

Không chỉ đo số lượng deployment. Có thể theo dõi:

| Chỉ số | Câu hỏi |
| --- | --- |
| Independent deployment rate | Bao nhiêu release hoàn thành mà không cần deploy service khác? |
| Coordinated release frequency | Bao nhiêu lần phải phát hành đồng bộ và lý do? |
| Change lead time | Từ thay đổi đến production mất bao lâu? |
| Change failure rate | Bao nhiêu release gây lỗi/rollback? |
| Recovery time | Khôi phục service sau deploy lỗi mất bao lâu? |
| Cross-service change count | Một thay đổi business cần sửa bao nhiêu service? |
| Shared DB access count | Bao nhiêu consumer còn truy cập trực tiếp dữ liệu owner? |
| Synchronous hop count | Critical path đi qua bao nhiêu service? |
| Contract breaking changes | Có bao nhiêu breaking change không có compatibility window? |
| Dependency failure blast radius | Một dependency lỗi ảnh hưởng bao nhiêu capability? |
| Ownership clarity | Có owner rõ cho API, schema, event và on-call không? |

Các số liệu nên được đo theo capability và release type. Một thay đổi lớn cần phối hợp một lần không chứng minh kiến trúc thất bại; xu hướng lặp lại mới quan trọng.

## 28. Kế hoạch chuyển đổi cho một distributed monolith đang tồn tại

Một kế hoạch thực tế có thể chia thành các giai đoạn:

### Giai đoạn 1: lập bản đồ và chọn điểm bắt đầu

- Vẽ service call graph và data access graph.
- Đọc lịch sử release để biết service nào thường phải phát hành cùng nhau.
- Tìm critical path, shared tables và shared libraries.
- Chọn một capability có domain boundary rõ và pain point đo được.
- Đặt baseline SLO và release metrics.

### Giai đoạn 2: ổn định contract

- Định nghĩa owner/provider/consumer.
- Viết OpenAPI/AsyncAPI/Protobuf hoặc schema phù hợp.
- Thêm error model, version, auth và timeout.
- Tạo contract tests.
- Thêm field mới theo expand-contract.

### Giai đoạn 3: chuyển quyền sở hữu dữ liệu

- Chuyển write path về owner.
- Backfill và delta capture nếu cần.
- Reconcile dữ liệu.
- Chuyển reads sang API/projection.
- Thu hồi direct DB write/read khi an toàn.
- Giữ rollback boundary rõ.

### Giai đoạn 4: giảm runtime coupling

- Loại bỏ call không cần thiết trong critical path.
- Chuyển notification/analytics side effects sang async.
- Đặt timeout, retry budget, circuit breaker và bulkhead.
- Dùng outbox/inbox/idempotency cho workflow event-driven.
- Thiết kế degraded mode đúng nghiệp vụ.

### Giai đoạn 5: tự chủ deployment

- Build/deploy artifact riêng.
- Kiểm thử provider/consumer version matrix.
- Canary và progressive rollout.
- Tách migration schema theo expand-contract.
- Đo số release độc lập và giảm release train.

### Giai đoạn 6: đánh giá và tiếp tục

- So sánh metrics với baseline.
- Kiểm tra incident blast radius và rollback.
- Ghi nhận coupling còn tồn tại và lý do.
- Chọn capability tiếp theo theo giá trị thực.

Không cần đạt trạng thái hoàn hảo trong một lần tái cấu trúc. Thay đổi từng boundary giúp học từ dữ liệu production và giới hạn rủi ro.

## 29. Khi nào nên quay lại Modular Monolith?

Đôi khi cách tốt nhất để xử lý distributed monolith là gom những service không có lý do tồn tại độc lập trở lại một deployable unit có module boundaries rõ.

Dấu hiệu nên cân nhắc:

- Các service luôn được thay đổi cùng nhau.
- Chúng cùng một domain/aggregate và cần transaction nguyên tử.
- Mỗi service không có ownership hoặc scaling khác biệt.
- Network hops gây latency mà không đem lại lợi ích vận hành.
- Team không đủ năng lực vận hành nhiều deployment.
- Tách service khiến logic phân tán khó debug hơn.

Có thể hợp nhất code/runtime nhưng giữ module API, dependency rules và schema ownership rõ. Một modular monolith có thể là nền tảng tốt để tách lại sau khi domain boundaries trưởng thành.

Không coi việc giảm số service là thất bại. Chất lượng kiến trúc nằm ở khả năng thay đổi và vận hành với chi phí hợp lý.

## 30. Ví dụ Java/Spring: module boundaries trước khi tách service

Một monolith có thể chia package/module:

    commerce
      order
        api
        application
        domain
        infrastructure
      inventory
        api
        application
        domain
        infrastructure
      billing
        api
        application
        domain
        infrastructure

Các module chỉ gọi public application interfaces, không truy cập repository hoặc entity nội bộ của nhau.

Ví dụ interface:

    public interface InventoryReservationUseCase {
        ReservationResult reserve(
            ReserveInventoryCommand command
        );
    }

Order module gọi use case này qua interface. Nó không import InventoryEntity hoặc InventoryRepository.

Khi cần tách Inventory thành service riêng, interface có thể được hiện thực bằng HTTP/gRPC adapter mà business use case phía Order ít thay đổi hơn. Đây là lợi ích của boundary trước khi phân tán runtime.

Có thể dùng ArchUnit hoặc module build boundaries để kiểm tra dependency direction. Unit/integration tests phải bảo đảm module không truy cập package nội bộ trái phép.

## 31. Ví dụ contract adapter khi tách service

Một interface consumer-owned:

    public interface CustomerProfilePort {
        CheckoutProfile getForCheckout(
            TenantId tenantId,
            CustomerId customerId
        );
    }

Ban đầu adapter có thể gọi module nội bộ; sau này thay implementation bằng HTTP client:

    @Component
    public class HttpCustomerProfileAdapter
            implements CustomerProfilePort {
        private final WebClient client;

        public HttpCustomerProfileAdapter(WebClient client) {
            this.client = client;
        }

        @Override
        public CheckoutProfile getForCheckout(
                TenantId tenantId,
                CustomerId customerId) {
            return client.get()
                .uri("/customers/{id}/checkout-profile",
                     customerId.value())
                .header("X-Tenant-Context", tenantId.value())
                .retrieve()
                .bodyToMono(CheckoutProfile.class)
                .block(Duration.ofMillis(300));
        }
    }

Đây là ví dụ khái niệm; production cần authentication đáng tin cậy, authorization phía provider, deadline propagation, error mapping, tracing, retry policy và không tin header tenant chưa xác thực. Nếu có thể, truyền identity/claims qua cơ chế service-to-service đã được tổ chức chuẩn hóa.

Port/interface giúp tách implementation, nhưng không tự giải quyết contract semantics hoặc network failure.

## 32. Một số quyết định kiến trúc cần tránh

- Tách service chỉ theo bảng hoặc CRUD endpoint.
- Chia sẻ ORM entities xuyên service.
- Cho phép mọi service ghi chung database.
- Tạo call chain đồng bộ dài mà không có deadline.
- Retry vô hạn khi dependency lỗi.
- Dùng fallback làm sai invariant.
- Chuyển mọi giao tiếp sang event mà không có workflow state.
- Dùng distributed transaction để giữ nguyên mọi transaction cũ mà không đánh giá.
- Cắt contract breaking trong một đợt release big bang.
- Tạo pipeline riêng nhưng vẫn khóa vào release train chung.
- Dùng shared library thay cho API/event contract.
- Dùng monorepo hay polyrepo làm tiêu chí duy nhất đánh giá autonomy.
- Giữ adapter legacy không có owner/sunset.
- Đo thành công bằng số service hoặc số container.
- Xóa shared DB access trước khi kiểm kê batch, BI và operational scripts.

## 33. Bài tập thực hành

Một nền tảng bán hàng có các service:

- Checkout Service gọi Order, Customer, Pricing, Inventory, Payment và Notification theo chuỗi đồng bộ.
- Các service có deployment riêng nhưng cùng sử dụng một PostgreSQL cluster và nhiều bảng chung.
- DTO/Entity nằm trong common-domain library.
- Mọi thay đổi schema đều cần phát hành lại 5 service.
- Release thường được lên lịch cùng một buổi; rollback một service đôi khi làm service khác không deserialize được response.
- Notification có thể gửi sau khi order được xác nhận, nhưng hiện đang nằm trong critical path.

**Yêu cầu:**

1. Xác định các lớp coupling: domain, data, contract, temporal, deployment, operational và organizational.
2. Vẽ runtime dependency graph và change/deployment graph.
3. Chọn bounded contexts phù hợp cho Order, Customer, Pricing, Inventory, Payment.
4. Xác định dữ liệu nào canonical, dữ liệu nào snapshot/projection.
5. Thiết kế contract tương thích để thay field mà không cần release đồng bộ.
6. Lập kế hoạch thu hồi shared DB write và chuyển direct reads.
7. Chuyển Notification sang event/outbox sau commit.
8. Xác định call nào phải đồng bộ và call nào có thể async.
9. Thiết kế timeout, retry, circuit breaker, bulkhead và fallback.
10. Đề xuất rollout/canary và rollback cho từng service.
11. Chọn một module có thể hợp nhất về modular monolith nếu không có autonomy thật.
12. Định nghĩa metrics để chứng minh số coordinated releases giảm và blast radius được thu hẹp.

**Hướng giải:** Bắt đầu bằng inventory và baseline. Chuyển ownership dữ liệu theo bounded context, áp expand-contract cho API/schema, loại bỏ shared entity, giữ snapshot cần thiết ở Order, đưa Notification qua transactional outbox, bảo vệ synchronous calls trong critical path, rồi tách pipeline độc lập và rollout theo compatibility. Không cần tách mọi capability thành deployment riêng nếu chi phí vận hành lớn hơn lợi ích.

## 34. Checklist đánh giá kiến trúc

### Domain và ownership

- Service boundaries theo business capability/bounded context?
- Có một owner rõ cho từng aggregate/table/event?
- Invariants có được đặt trong đúng owner?
- Có shared ORM entity hoặc business rule không?
- Có consumer query/ghi database nội bộ của service khác?

### Runtime và resilience

- Critical path có bao nhiêu synchronous hops?
- Dependency có deadline/timeout?
- Retry có budget, backoff và idempotency?
- Circuit breaker/bulkhead có giới hạn blast radius?
- Fallback có đúng business semantics?
- Async work có outbox/inbox, bounded queue và DLQ?
- Có quan sát queue lag, connection pool và business outcome?

### Contract và release

- API/event contract có version và compatibility policy?
- Có contract tests provider/consumer?
- Có thể chạy phiên bản cũ/mới cùng lúc?
- Database migration theo expand-contract?
- Artifact và pipeline riêng cho service?
- Có canary, health/business check và rollback độc lập?
- Có deprecation/sunset cho contract cũ?
- Coordinated release có lý do và được ghi nhận?

### Organization và operations

- Team sở hữu service, data, SLO và on-call?
- Runbook và incident boundary rõ?
- Shared dependencies có capacity budget?
- Change failure rate và recovery time được theo dõi?
- Có thể thử một service mà không phải khởi động toàn hệ thống?
- Mức độ tự chủ mang lại lợi ích thực tế so với chi phí phân tán?

---

**Điểm cốt lõi:** Distributed Monolith xuất hiện khi nhiều dịch vụ đã được tách về triển khai nhưng vẫn phải thay đổi và vận hành như một khối. Nguyên nhân thường nằm ở ranh giới nghiệp vụ, shared database, shared model, contract breaking và call chain đồng bộ. Cách tháo gỡ là xác định owner đúng, làm contract tương thích, chuyển dữ liệu có kiểm soát, giảm dependency không cần thiết, bảo vệ runtime và phát hành theo từng service. Khi một số capability không có lý do để chạy độc lập, modular monolith với module boundaries rõ cũng là lựa chọn kiến trúc hợp lý.

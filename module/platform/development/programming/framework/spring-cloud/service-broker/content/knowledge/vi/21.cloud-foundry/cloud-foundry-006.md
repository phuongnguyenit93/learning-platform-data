# Tạo và cập nhật dịch vụ bằng cf create-service và cf update-service

Cloud Foundry cung cấp trải nghiệm self-service để developer tạo và quản lý dịch vụ thông qua Cloud Foundry CLI. Hai lệnh thường dùng là cf create-service để tạo service instance mới và cf update-service để thay đổi plan hoặc parameters của instance đã có. Khi thao tác với service broker theo Open Service Broker API (OSB API), Cloud Controller tiếp nhận lệnh từ CLI, kiểm tra service offering/plan rồi gọi broker để provision hoặc update tài nguyên phía sau.

Trong mô hình Spring Cloud Service Broker, broker cung cấp catalog gồm service và plan; triển khai các thao tác provision/update; quản lý trạng thái operation; và tích hợp với provider như database, message broker hoặc Kubernetes. Người dùng làm việc với tên service instance trong Cloud Foundry, còn broker nhận các định danh và payload theo OSB API. Hiểu được luồng này giúp phân biệt lỗi CLI, lỗi Cloud Controller, lỗi broker và lỗi provider.

## 1. Vai trò của marketplace, service và plan

Cloud Foundry Marketplace hiển thị các service offering mà platform đã đăng ký. Một service offering đại diện cho loại dịch vụ, ví dụ PostgreSQL, Redis hoặc message queue. Mỗi offering có thể cung cấp nhiều plan với mức tài nguyên và tính năng khác nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Service offering | Loại dịch vụ được broker công bố | postgresql |
| Service plan | Gói cấu hình của service | small, standard, high-availability |
| Service instance | Một tài nguyên dịch vụ được tạo cho space | orders-db |
| Service binding | Liên kết giữa service instance và ứng dụng | orders-api-binding |
| Parameters | Cấu hình riêng khi tạo hoặc cập nhật instance | storage_gb, backup_retention_days |
| Tags | Nhãn metadata để platform hoặc ứng dụng nhận biết service | production, finance |

Plan thường xác định giới hạn và khả năng chính của tài nguyên: dung lượng, số replica, mức SLA, backup hoặc tính năng bảo mật. Parameters cho phép người dùng tinh chỉnh những giá trị broker cho phép trong plan đó. Không phải mọi tham số của provider đều được phép truyền qua CLI; broker phải validate theo schema và chính sách của service.

Developer có thể xem danh sách service:

    cf marketplace

Xem các plan của một service:

    cf marketplace -s postgresql

Kết quả marketplace phụ thuộc catalog broker đã công bố và các service/plan được administrator bật trên Cloud Foundry. Nếu service không xuất hiện, kiểm tra broker registration, catalog response và quyền truy cập của organization/space trước khi thử tạo instance.

## 2. Chuẩn bị trước khi tạo service instance

Trước khi gọi create-service, developer cần đăng nhập và chọn đúng organization, space:

    cf login
    cf target
    cf target -o engineering -s development

Lệnh target giúp tránh tạo service trong nhầm space. Tên service instance thường được quản lý trong phạm vi space, vì vậy cùng một tên có thể tồn tại ở hai space khác nhau.

Kiểm tra service và plan:

    cf marketplace -s postgresql

Đọc mô tả service, plan và yêu cầu parameters. Với broker tự xây dựng, cần công bố rõ:

- Plan nào được phép dùng trong từng môi trường.
- Parameters nào được hỗ trợ và kiểu dữ liệu tương ứng.
- Giá trị mặc định và giới hạn quota.
- Tạo service có xử lý bất đồng bộ hay không.
- Có hỗ trợ update parameters và đổi plan hay không.
- Service instance có cần binding trước khi ứng dụng sử dụng không.

Không nên đoán tên plan từ tên hiển thị. Dùng đúng service và plan mà marketplace trả về.

## 3. Tạo service instance bằng cf create-service

### 3.1. Cú pháp

Cú pháp thường dùng trong Cloud Foundry CLI:

    cf create-service SERVICE PLAN SERVICE_INSTANCE [-c PARAMETERS_AS_JSON] [-t TAGS] [--wait]

Trong đó:

- SERVICE là tên service offering trong marketplace.
- PLAN là plan của offering.
- SERVICE_INSTANCE là tên người dùng đặt cho instance trong space hiện tại.
- -c hoặc --config truyền parameters dạng JSON hoặc đường dẫn đến file JSON, tùy phiên bản CLI.
- -t hoặc --tags truyền danh sách tags cho service instance.
- --wait yêu cầu CLI chờ operation hoàn tất nếu phiên bản CLI và platform hỗ trợ tùy chọn này.

Ví dụ tạo database với plan standard:

    cf create-service postgresql standard orders-db

Cloud Controller tìm service offering và plan, tạo service instance record rồi gọi service broker. Broker nhận yêu cầu provision theo OSB API và tạo database thực tế ở provider.

### 3.2. Tạo service với parameters

Giả sử broker hỗ trợ parameters storage_gb và backup_retention_days:

    cf create-service postgresql standard orders-db -c '{"storage_gb":100,"backup_retention_days":14}'

Parameters là object JSON. Kiểu dữ liệu phải đúng schema broker công bố. Ví dụ storage_gb có thể là số nguyên, còn backup_retention_days có thể là số nguyên trong một khoảng cho phép. Nếu truyền chuỗi thay vì số, broker nên validate và trả lỗi rõ ràng.

Có thể tách parameters ra file để dễ quản lý:

    {
      "storage_gb": 100,
      "backup_retention_days": 14,
      "region": "ap-southeast"
    }

Sau đó gọi:

    cf create-service postgresql standard orders-db -c ./orders-db-parameters.json

Khả năng nhận file JSON và cách chỉ định file có thể khác theo phiên bản CLI; kiểm tra cf help create-service khi dùng môi trường cụ thể. File parameters có thể chứa dữ liệu nhạy cảm, vì vậy cần giới hạn quyền đọc, tránh commit secret vào Git và xóa hoặc lưu trữ theo chính sách sau khi sử dụng.

Không truyền password hoặc token production trực tiếp trên command line nếu shell history, process inspection hoặc CI log có thể lưu lại. Nếu broker cần secret, ưu tiên cơ chế secret management và quy trình inject an toàn được platform hỗ trợ.

### 3.3. Tạo service với tags

Tags là metadata mô tả service instance:

    cf create-service postgresql standard orders-db -t "production,finance"

Tags không thay thế plan, không cấp quyền truy cập và không phải parameters cấu hình provider. Broker có thể nhận tags qua context hoặc metadata platform tùy cách tích hợp; không nên dựa vào tags để quyết định quyền sở hữu tài nguyên.

## 4. Cloud Controller chuyển create-service thành OSB provision

Lệnh CLI không gọi trực tiếp endpoint broker. Cloud Foundry CLI giao tiếp với Cloud Controller API; Cloud Controller quản lý service instance và thực hiện lời gọi đến broker đã đăng ký.

Luồng khái quát:

    Developer
       |
       | cf create-service postgresql standard orders-db
       v
    Cloud Foundry CLI
       |
       | Cloud Controller API
       v
    Cloud Controller
       |
       | PUT /v2/service_instances/{instance_id}
       | accepts_incomplete=true khi platform hỗ trợ async
       v
    Spring Cloud Service Broker
       |
       | Provision request
       v
    Provider API / Kubernetes / Database

Cloud Controller ánh xạ tên service instance thành GUID nội bộ và gửi các định danh OSB như service_id, plan_id, context và parameters. Broker không nên dùng tên CLI làm khóa duy nhất; service instance ID trong OSB request mới là định danh ổn định được platform quản lý.

Request provision minh họa:

    PUT /v2/service_instances/instance-guid-123?accepts_incomplete=true
    Content-Type: application/json
    X-Broker-API-Version: 2.17

    {
      "service_id": "postgresql-service-v1",
      "plan_id": "postgresql-standard-v1",
      "organization_guid": "org-guid-10",
      "space_guid": "space-guid-20",
      "parameters": {
        "storage_gb": 100,
        "backup_retention_days": 14
      }
    }

Broker validate service, plan, context và parameters trước khi tạo tài nguyên. Sau khi provision thành công, broker lưu external resource ID, cấu hình và trạng thái instance. Nếu provider cần thời gian, broker lưu operation bền vững và trả 202 Accepted cùng operation ID; Cloud Controller theo dõi operation qua endpoint last_operation.

## 5. Tạo service bất đồng bộ và kiểm tra trạng thái

Provision database hoặc cluster thường mất nhiều thời gian. Broker có thể trả kết quả đồng bộ nếu tài nguyên sẵn sàng nhanh, hoặc trả 202 khi platform cho phép xử lý incomplete operation.

Ví dụ response async:

    HTTP/1.1 202 Accepted
    Content-Type: application/json

    {
      "operation": "provision-2026-000891"
    }

Platform tiếp tục polling:

    GET /v2/service_instances/instance-guid-123/last_operation?service_id=postgresql-service-v1&plan_id=postgresql-standard-v1&operation=provision-2026-000891

Broker trả state in progress, succeeded hoặc failed. Các trạng thái nội bộ như QUEUED, RUNNING hoặc RETRY_WAIT phải được ánh xạ sang state OSB tương ứng.

Ở phía developer, có thể xem danh sách service:

    cf services

Xem chi tiết một service instance:

    cf service orders-db

Thông tin hiển thị và cách CLI trình bày operation phụ thuộc phiên bản Cloud Foundry CLI và platform. Nếu lệnh create-service báo đang tạo hoặc đang in progress, không nên tạo một instance khác chỉ vì chưa thấy database ngay lập tức. Hãy kiểm tra cùng instance bằng cf service và chờ operation kết thúc.

Tùy phiên bản CLI, tùy chọn --wait có thể khiến lệnh chờ đến khi service instance sẵn sàng. Nếu không dùng tùy chọn này, lệnh có thể trả về sau khi Cloud Controller đã tiếp nhận yêu cầu; người dùng tiếp tục theo dõi bằng cf service. Kiểm tra trợ giúp CLI đang cài để biết chính xác hành vi.

## 6. Cập nhật service instance bằng cf update-service

Sau khi service instance được tạo, người dùng có thể thay đổi parameters hoặc plan nếu broker và plan hỗ trợ.

Cú pháp thường dùng:

    cf update-service SERVICE_INSTANCE [-p PLAN] [-c PARAMETERS_AS_JSON] [-t TAGS] [--wait]

Các thành phần:

- SERVICE_INSTANCE là tên instance hiện có trong space đang target.
- -p hoặc --plan chọn plan đích.
- -c hoặc --config truyền parameters cập nhật.
- -t hoặc --tags cập nhật tags nếu platform/CLI hỗ trợ.
- --wait yêu cầu chờ operation hoàn tất khi tùy chọn được hỗ trợ.

Ví dụ tăng dung lượng database trong cùng plan:

    cf update-service orders-db -c '{"storage_gb":200}'

Ví dụ đổi plan:

    cf update-service orders-db -p high-availability

Ví dụ đổi plan và cập nhật parameters cùng lúc:

    cf update-service orders-db -p high-availability -c '{"storage_gb":200,"backup_retention_days":30}'

Không gửi toàn bộ parameters cũ nếu broker hiểu field bị thiếu là giữ nguyên và field được gửi là giá trị cần cập nhật; hãy theo đúng semantics và schema mà broker công bố. Một số broker xem parameters là cấu hình đích đầy đủ, số khác xử lý như tập field cần thay đổi. Tài liệu service phải nêu rõ cách hiểu để tránh vô tình reset cấu hình.

## 7. Cloud Controller chuyển update-service thành OSB update

Cloud Controller chuyển lệnh update-service thành request PATCH tới broker:

    PATCH /v2/service_instances/{instance_id}?accepts_incomplete=true
    Content-Type: application/json
    X-Broker-API-Version: 2.17

    {
      "service_id": "postgresql-service-v1",
      "plan_id": "postgresql-high-availability-v1",
      "parameters": {
        "storage_gb": 200,
        "backup_retention_days": 30
      },
      "previous_values": {
        "service_id": "postgresql-service-v1",
        "plan_id": "postgresql-standard-v1",
        "organization_guid": "org-guid-10",
        "space_guid": "space-guid-20"
      }
    }

previous_values cung cấp một số thông tin trước khi cập nhật, hữu ích cho broker xác định thay đổi. Tuy nhiên, trạng thái chuẩn vẫn phải được đọc từ database broker; không dùng previous_values như bằng chứng duy nhất về plan hoặc quyền sở hữu.

Broker cần:

1. Tìm instance theo platform scope và instance ID.
2. Kiểm tra service_id khớp với instance.
3. Kiểm tra plan đích tồn tại và thuộc service.
4. Kiểm tra service có công bố khả năng plan update nếu request đổi plan.
5. Validate parameters theo plan đích và chính sách quota.
6. Kiểm tra không có operation mutation xung đột đang chạy.
7. Quyết định update đồng bộ hay bất đồng bộ.
8. Chỉ commit plan/configuration mới khi provider đã áp dụng thành công hoặc trạng thái đã được xác minh.

## 8. Điều kiện để đổi plan thành công

Không phải service broker nào cũng cho phép đổi plan sau khi provision. Service definition trong catalog có thể công bố plan_updateable. Nếu khả năng này không được bật, platform có thể từ chối hoặc broker có thể trả lỗi PlanChangeNotSupported theo hợp đồng OSB API.

Trước khi đổi plan, kiểm tra:

- Plan đích có thuộc đúng service offering không.
- Plan đích có đang được publish và cho phép sử dụng trong organization/space không.
- Service có hỗ trợ plan update không.
- Broker có hỗ trợ chuyển đổi từ plan hiện tại sang plan đích cụ thể không.
- Dữ liệu và cấu hình hiện tại có tương thích với plan đích không.
- Quota, dung lượng và giới hạn provider có đáp ứng không.
- Có operation update/deprovision khác đang chạy không.

Ví dụ chuyển từ standard sang high-availability có thể yêu cầu tạo replica, đồng bộ dữ liệu và chuyển traffic. Đây không chỉ là thay plan_id trong database. Broker cần thực hiện migration, theo dõi tiến độ và chỉ lưu plan đích sau khi provider xác nhận hoàn tất.

Nếu update cần async và Cloud Controller chấp nhận incomplete operation, broker trả 202 và cung cấp operation ID. Nếu broker bắt buộc xử lý async nhưng request không cho phép, trả 422 AsyncRequired. Nếu instance đang có một operation mutation khác, trả 409 ConcurrencyError theo chính sách concurrency của broker.

## 9. Update parameters trong cùng plan

Update parameters có thể thay đổi thuộc tính của tài nguyên mà không đổi plan. Ví dụ:

- Tăng storage từ 100 GB lên 200 GB.
- Tăng backup retention từ 14 lên 30 ngày.
- Bật hoặc tắt một tính năng được plan cho phép.
- Thay đổi cấu hình maintenance window.

Broker cần phân biệt parameters có thể cập nhật với parameters chỉ được dùng khi provision. Một số giá trị như region, encryption mode hoặc topology có thể không đổi được sau khi tài nguyên đã tạo.

Nên mô tả schema theo từng plan:

| Parameter | Kiểu | Ví dụ | Quy tắc |
|---|---|---|---|
| storage_gb | integer | 200 | Chỉ cho phép tăng trong giới hạn plan |
| backup_retention_days | integer | 30 | Nằm trong khoảng plan hỗ trợ |
| maintenance_window | string | Sun 02:00 UTC | Validate format và timezone |
| encryption_at_rest | boolean | true | Có thể chỉ bật, không cho tắt sau provision |

Khi nhận PATCH, broker phải validate cả giá trị và transition. Một giá trị hợp lệ khi tạo mới chưa chắc hợp lệ khi update. Ví dụ giảm storage có thể không được hỗ trợ vì dữ liệu đang sử dụng vượt dung lượng đích.

## 10. Theo dõi operation từ Cloud Foundry

Với operation async, platform cần theo dõi trạng thái để biết khi nào có thể tiếp tục bind hoặc update. Broker lưu operation với các trường như:

| Trường | Mục đích |
|---|---|
| operation_id | ID broker trả về cho platform |
| service_instance_id | Instance đang thay đổi |
| operation_type | PROVISION hoặc UPDATE |
| target_plan_id | Plan đích nếu có |
| target_parameters | Parameters đã chuẩn hóa |
| state | Trạng thái operation nội bộ |
| attempt_count | Số lần worker đã thử |
| next_retry_at | Thời điểm retry |
| provider_operation_id | ID provider trả về nếu xử lý async riêng |
| created_at/updated_at | Thời gian phục vụ audit |

Worker có thể gặp provider timeout hoặc 503. Nếu lỗi tạm thời, broker giữ operation ở trạng thái chờ retry và tiếp tục báo in progress cho platform. Nếu lỗi không thể phục hồi, operation chuyển failed; description gửi platform cần an toàn và hữu ích.

Platform không nên gửi update mới trên cùng instance khi operation cũ chưa terminal. Broker cần kiểm tra active operation và từ chối mutation xung đột bằng 409 ConcurrencyError. Việc CLI hiển thị command đã hoàn tất gửi request không đồng nghĩa provider operation đã hoàn tất.

## 11. Kết hợp create-service với bind-service

Tạo service instance chưa tự động cấp credentials cho ứng dụng. Sau khi instance sẵn sàng, developer có thể bind:

    cf bind-service orders-api orders-db
    cf restage orders-api

Bind tạo một service binding riêng. Broker có thể tạo database user hoặc credential theo binding ID rồi trả thông tin kết nối. Cloud Foundry đưa credentials vào môi trường ứng dụng theo cơ chế platform.

Nếu service instance đang provision hoặc update chưa hoàn tất, binding có thể bị từ chối hoặc phải chờ theo trạng thái broker. Sau khi binding được tạo, restage ứng dụng thường cần thiết để ứng dụng nhận biến môi trường mới; hành vi cụ thể phụ thuộc loại app và cách platform cập nhật environment.

Khi cập nhật service instance làm thay đổi endpoint hoặc credential, broker cần đánh giá ảnh hưởng đến binding hiện có. Không tự ý đổi credential mà không có quy trình phối hợp để ứng dụng và platform nhận giá trị mới.

## 12. Xử lý lỗi thường gặp

| Lỗi | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Service không tìm thấy trong marketplace | Broker chưa đăng ký, service chưa publish hoặc quyền marketplace bị giới hạn | Kiểm tra cf marketplace, broker catalog và service availability |
| Plan không tồn tại | Gõ sai tên plan hoặc plan không thuộc offering | Dùng cf marketplace -s SERVICE để xem plan |
| Service instance name đã tồn tại | Tên trùng trong space | Kiểm tra cf services và chọn tên phù hợp hoặc xử lý instance hiện có |
| Parameters không hợp lệ | JSON sai, sai kiểu hoặc vượt schema | Kiểm tra JSON và schema broker công bố |
| Quota exceeded | Organization/space/provider hết quota | Kiểm tra quota và plan, không retry liên tục |
| AsyncRequired | Broker cần async nhưng request không chấp nhận incomplete operation | Dùng platform/CLI hỗ trợ async theo cấu hình |
| ConcurrencyError | Instance đang có provision/update/deprovision khác | Chờ operation hiện tại rồi thử lại |
| PlanChangeNotSupported | Broker không cho đổi plan | Giữ plan hiện tại hoặc dùng quy trình migration được hỗ trợ |
| Provider unavailable | API provider đang lỗi hoặc rate limit | Theo dõi operation, retry theo backoff hoặc liên hệ vận hành |
| CLI báo in progress lâu | Provider chậm, operation retry hoặc worker bị kẹt | Dùng cf service và kiểm tra operation/broker logs |

Không xóa và tạo lại service instance chỉ để xử lý một update thất bại nếu dữ liệu bên trong có giá trị. Hãy xem trạng thái operation, xác định provider đã thực hiện side effect hay chưa và dùng quy trình retry/reconciliation của broker.

## 13. Quy trình thực hành hoàn chỉnh

Một quy trình mẫu từ kiểm tra marketplace đến cập nhật service:

1. Đăng nhập Cloud Foundry và target đúng organization/space.
2. Xem service offering và plan bằng cf marketplace.
3. Đọc schema parameters và chính sách plan của broker.
4. Tạo file JSON parameters nếu cần.
5. Chạy cf create-service để tạo service instance.
6. Theo dõi bằng cf service INSTANCE cho đến khi operation hoàn tất.
7. Bind service vào ứng dụng nếu cần credentials.
8. Khi có nhu cầu tăng dung lượng hoặc đổi plan, xác nhận capability update.
9. Chạy cf update-service với -c và/hoặc -p.
10. Theo dõi operation đến terminal state.
11. Kiểm tra lại service và ứng dụng để xác nhận cấu hình mới hoạt động.

Ví dụ command liên tiếp:

    cf target -o engineering -s production
    cf marketplace -s postgresql
    cf create-service postgresql standard orders-db -c ./orders-db-parameters.json
    cf service orders-db
    cf bind-service orders-api orders-db
    cf restage orders-api
    cf update-service orders-db -p high-availability -c ./orders-db-upgrade.json
    cf service orders-db

Các lệnh trên là ví dụ minh họa. Tên service, plan, parameters, CLI flags và khả năng update phụ thuộc catalog broker, phiên bản Cloud Foundry CLI và cấu hình platform.

## 14. Kiểm thử luồng CLI và broker

Ở cấp platform/broker, nên kiểm tra:

1. Marketplace hiển thị đúng service và plan từ catalog.
2. create-service với service/plan hợp lệ tạo đúng service instance trong đúng organization/space.
3. Broker nhận đúng service_id, plan_id, context và parameters.
4. Parameters sai schema bị từ chối trước khi tạo side effect.
5. Provision sync trả kết quả thành công; provision async trả 202 và operation ID.
6. last_operation phản ánh in progress, succeeded và failed chính xác.
7. update-service chỉ đổi parameters khi request không gửi plan đích.
8. Đổi plan được chấp nhận khi service công bố plan update và transition hợp lệ.
9. Plan không hỗ trợ update bị từ chối mà không ghi plan đích vào instance.
10. Hai update đồng thời trên cùng instance được điều phối; request xung đột nhận lỗi phù hợp.
11. Retry request không tạo service instance trùng.
12. Provider timeout được xử lý bằng idempotency và reconciliation.
13. Binding sau provision trả credentials đúng và không lộ secret trong log.
14. CLI nhắm đúng organization/space và service instance name.

Có thể dùng integration test với provider giả lập để kiểm tra timeout, quota, plan transition, async polling và operation conflict mà không cần tạo tài nguyên cloud thật cho mọi trường hợp.

## 15. Lỗi thường gặp khi thiết kế broker cho Cloud Foundry

| Lỗi thiết kế | Tác động | Cách khắc phục |
|---|---|---|
| Dùng service instance name làm khóa toàn cục | Trùng tên giữa các space/organization | Dùng GUID và platform scope |
| Catalog hiển thị plan nhưng broker không xử lý được | create-service thất bại ở runtime | Giữ catalog đồng bộ với khả năng thật |
| Nhận mọi parameters mà không validate | Cấu hình provider không an toàn hoặc vượt quota | Schema validation theo service/plan và operation |
| Coi update parameters giống plan update | Từ chối nhầm hoặc đổi plan sai | Tách logic parameters update và plan transition |
| Công bố plan_updateable quá mức | Platform cho phép thao tác broker không hỗ trợ | Chỉ công bố capability đã triển khai |
| Trả 202 trước khi lưu operation | Platform polling không tìm thấy công việc | Commit operation và outbox trước response |
| Không kiểm soát operation đồng thời | Update/deprovision phá hủy lẫn nhau | Claim instance nguyên tử và trả conflict |
| Cập nhật plan_id trước khi provider thành công | Trạng thái broker lệch provider | Commit cấu hình đích sau khi xác nhận |
| Không lưu external resource ID | Khó update, deprovision hoặc reconcile | Lưu provider resource reference bền vững |
| Xem CLI command return là provider đã sẵn sàng | Ứng dụng bind khi tài nguyên chưa hoàn tất | Theo dõi service instance operation |

## 16. Kết luận

cf create-service tạo service instance từ service offering và plan trong marketplace; cf update-service thay đổi parameters hoặc plan nếu broker hỗ trợ. Cloud Foundry CLI gửi yêu cầu đến Cloud Controller, rồi Cloud Controller gọi Spring Cloud Service Broker theo OSB API. Broker validate request, quản lý operation và điều khiển provider. Khi thao tác bất đồng bộ, platform theo dõi last_operation; người dùng có thể xem trạng thái qua cf service và dùng --wait nếu CLI/platform hỗ trợ. Để luồng vận hành đáng tin cậy, broker cần công bố catalog đúng thực tế, validate parameters, kiểm tra plan update capability, bảo vệ concurrency và chỉ cập nhật trạng thái instance sau khi provider xác nhận kết quả.

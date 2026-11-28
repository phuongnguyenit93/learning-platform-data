# Kiểm tra quan hệ giữa tham số, gói dịch vụ và quyền của khách hàng

Khi một nền tảng gửi yêu cầu provision hoặc update đến service broker, request thường chứa service ID, plan ID và một tập tham số do người dùng lựa chọn. Mỗi giá trị có thể hợp lệ khi xét riêng nhưng không hợp lệ khi kết hợp với các giá trị còn lại. Ví dụ, tham số bật backup nâng cao chỉ có ý nghĩa với plan hỗ trợ backup; vùng triển khai mà khách hàng yêu cầu có thể không nằm trong entitlement của tenant; dung lượng yêu cầu có thể vượt quota còn lại của khách hàng.

Vì vậy, kiểm tra request của broker cần đánh giá đồng thời ba yếu tố:

1. **Tham số** mô tả cấu hình người dùng muốn áp dụng.
2. **Service plan** xác định tập năng lực, giới hạn và cấu hình mà broker có thể cung cấp.
3. **Entitlement của khách hàng** xác định khách hàng/tenant được phép sử dụng service, plan, vùng và hạn mức nào.

Trong module SPRING_CLOUD_SERVICE_BROKER, việc kiểm tra này nên nằm trong application/domain layer sau khi request OSB đã được chuyển thành mô hình nội bộ và danh tính caller/tenant đã được xác minh. Infrastructure adapter chỉ nhận command đã qua kiểm tra và thực hiện thao tác trên backend. Cách tổ chức đó giúp broker từ chối cấu hình không hợp lệ trước khi tạo tài nguyên, đồng thời tránh để dữ liệu do client gửi quyết định quyền của chính client.

## 1. Ba nguồn dữ liệu và mức độ tin cậy

Không phải mọi dữ liệu trong request đều có cùng mức độ tin cậy. Broker cần biết dữ liệu nào do người dùng cung cấp, dữ liệu nào thuộc catalog do broker quản lý và dữ liệu nào đến từ hệ thống entitlement đáng tin cậy.

| Nguồn | Ví dụ | Vai trò | Cách sử dụng |
|---|---|---|---|
| Request OSB | service ID, plan ID, parameters, context | Diễn tả yêu cầu của caller | Xem là input cần xác thực và kiểm tra |
| Catalog/plan registry của broker | plan ID, giới hạn RAM, tính năng backup, vùng hỗ trợ | Định nghĩa năng lực broker công bố | Dùng làm nguồn chuẩn để diễn giải plan và parameter |
| Entitlement/quota service | tenant được dùng plan nào, hạn mức, vùng được phép | Xác định quyền và ngân sách của khách hàng | Lấy từ nguồn đã xác thực, có kiểm soát freshness |
| State store của broker | owner, plan hiện tại, tài nguyên đã dùng, operation đang chạy | Phản ánh trạng thái instance và reservation | Dùng để kiểm tra quan hệ với tài nguyên hiện hữu |

Không tin các trường như tenantId, customerId, owner, isAdmin hoặc quota chỉ vì chúng xuất hiện trong parameters hay context của request. Các trường đó có thể bị người gửi tự đặt. Tenant và principal phải được suy ra từ cơ chế xác thực/ủy quyền đã cấu hình, hoặc từ context nền tảng chỉ khi broker có kênh tin cậy để xác minh nguồn gốc.

Tương tự, không để client gửi một giá trị như maxStorageGb=1000 rồi xem đó là giới hạn được cấp. Giới hạn phải đến từ plan registry và entitlement đã được broker xác minh.

## 2. Phân biệt validation từng lớp và validation quan hệ

Validation từng lớp kiểm tra một đối tượng riêng lẻ. Validation quan hệ kiểm tra nhiều đối tượng cùng lúc.

| Loại kiểm tra | Ví dụ | Câu hỏi |
|---|---|---|
| Cú pháp/type | storageGb là số nguyên dương | Giá trị có đúng kiểu và định dạng không? |
| Schema tham số | backupEnabled là boolean, region là chuỗi trong tập cho phép | Tham số có được định nghĩa và có kiểu hợp lệ không? |
| Ràng buộc tham số | storageGb nằm trong khoảng 10–500 | Giá trị có nằm trong giới hạn khai báo không? |
| Ràng buộc theo plan | Plan Basic không hỗ trợ backup nâng cao | Plan này có hỗ trợ tham số/tính năng đó không? |
| Ràng buộc theo khách hàng | Tenant A không có entitlement cho plan HA | Khách hàng có quyền dùng lựa chọn này không? |
| Ràng buộc liên kết | Plan HA yêu cầu vùng có ít nhất hai availability zone | Các lựa chọn có tương thích với nhau không? |
| Ràng buộc theo trạng thái | Instance đang UPDATE thì không nhận thêm update | Thao tác có hợp lệ với trạng thái hiện tại không? |

Một request có thể vượt qua schema nhưng vẫn thất bại ở bước quan hệ. Ví dụ:

    {
      "service_id": "postgres-service",
      "plan_id": "basic-plan",
      "parameters": {
        "storageGb": 200,
        "backupEnabled": true,
        "region": "region-a"
      }
    }

Giả sử Basic cho phép tối đa 50 GB và không hỗ trợ backup nâng cao. Các giá trị đều có thể đúng kiểu, nhưng request không hợp lệ theo plan. Broker cần báo lỗi validation phù hợp trước khi gọi backend.

## 3. Mô hình hóa plan capability và customer entitlement

Không nên để logic kiểm tra dựa trên chuỗi tên hiển thị như Basic, Premium hoặc Enterprise. Hãy dùng ID ổn định và một mô hình có kiểu cho giới hạn và capability.

Ví dụ mô hình plan nội bộ:

    public record PlanDefinition(
            String serviceId,
            String planId,
            long minStorageGb,
            long maxStorageGb,
            Set<String> supportedRegions,
            Set<String> features,
            int maxConnections) {
    }

Entitlement của khách hàng có thể được biểu diễn riêng:

    public record CustomerEntitlement(
            String tenantId,
            Set<String> allowedServiceIds,
            Set<String> allowedPlanIds,
            Set<String> allowedRegions,
            Map<String, Long> quotas,
            Instant expiresAt,
            String status) {
    }

Hai mô hình có mục đích khác nhau. Plan definition mô tả broker có thể cung cấp gì; entitlement mô tả một khách hàng được phép sử dụng phần nào của năng lực đó và còn bao nhiêu hạn mức. Không gộp entitlement vào catalog công khai, vì quyền của mỗi tenant có thể khác nhau và không nên được công bố cho tenant khác.

Nếu catalog thay đổi theo tenant, broker có thể lọc những service/plan mà tenant được phép nhìn thấy. Tuy nhiên, lọc catalog chỉ cải thiện trải nghiệm sử dụng. Mỗi yêu cầu provision hoặc update vẫn phải được kiểm tra entitlement tại server vì caller có thể gửi trực tiếp ID của plan không xuất hiện trong catalog mà họ đã xem trước đó.

## 4. Quy trình kiểm tra request

Một trình tự hợp lý cho yêu cầu provision:

1. Xác thực caller của OSB endpoint.
2. Xác định tenant/principal từ nguồn đáng tin cậy.
3. Parse request và kiểm tra cấu trúc cơ bản.
4. Tìm service definition và plan theo ID trong catalog/registry của broker.
5. Xác nhận service và plan thuộc cùng một service, đang được phép provision.
6. Nạp entitlement hiện hành của tenant; kiểm tra trạng thái, thời hạn và phạm vi quyền.
7. Validate từng parameter theo schema chung.
8. Validate quan hệ parameter–plan: tính năng, vùng, dung lượng, số lượng replica và các ràng buộc phụ thuộc.
9. Validate quan hệ plan–entitlement: tenant có được dùng plan và các capability được yêu cầu hay không.
10. Kiểm tra quota còn lại và trạng thái tài nguyên hiện hữu.
11. Tạo reservation/operation một cách nguyên tử, sau đó mới gọi adapter hạ tầng.

Thứ tự này giúp broker từ chối sớm các request không có quyền và không tiêu thụ tài nguyên khi cấu hình không hợp lệ. Một số bước có thể cần chạy cùng transaction hoặc cần kiểm tra lại ngay trước khi commit để tránh quota bị hai request đồng thời tiêu thụ vượt mức.

Luồng tổng quát:

    OSB request
        -> Xác thực caller
        -> Xác định tenant đáng tin cậy
        -> Đọc service và plan theo ID
        -> Đọc entitlement
        -> Validate schema parameters
        -> Validate parameters với plan
        -> Validate plan với entitlement
        -> Kiểm tra quota và trạng thái
        -> Reservation + operation
        -> Infrastructure adapter

Nếu schema, quan hệ plan, entitlement hoặc quota không hợp lệ, broker trả lỗi OSB phù hợp và không gọi infrastructure adapter.

## 5. Ví dụ quan hệ giữa parameters và plan

Giả sử broker cung cấp database với ba plan:

| Plan | Storage | Backup | Regions | Connections |
|---|---:|---|---|---:|
| Basic | 10–50 GB | Cơ bản | region-a | 50 |
| Standard | 10–500 GB | Cơ bản/nâng cao | region-a, region-b | 200 |
| High Availability | 50–2000 GB | Nâng cao | region-a, region-b | 1000 |

Một số quy tắc quan hệ:

- storageGb phải nằm trong khoảng của plan đã chọn.
- backupEnabled=true chỉ hợp lệ nếu plan có feature backup tương ứng.
- region phải nằm trong tập vùng plan hỗ trợ.
- Nếu replicaCount lớn hơn 1, plan phải hỗ trợ replication và vùng phải có topology phù hợp.
- connectionLimit không được vượt mức plan cung cấp.
- Một tham số chỉ có ý nghĩa khi một tham số khác được bật phải được kiểm tra theo quan hệ điều kiện. Ví dụ backupRetentionDays chỉ được phép khi backupEnabled=true.

Không nên chỉ kiểm tra từng tham số riêng lẻ. Ví dụ backupRetentionDays=30 có thể hợp lệ về khoảng số ngày nhưng không hợp lệ khi backupEnabled=false. Đây là một ràng buộc chéo giữa hai parameter.

## 6. Ví dụ validator Java theo plan

Một cách thiết kế là chuyển parameters thô thành một command đã chuẩn hóa, sau đó kiểm tra command cùng plan definition. Ví dụ sau minh họa domain validator độc lập với HTTP và SDK hạ tầng:

    public record DatabaseParameters(
            long storageGb,
            boolean backupEnabled,
            int backupRetentionDays,
            String region,
            int connectionLimit) {
    }

    public record ValidationIssue(
            String field,
            String code,
            String message) {
    }

    public final class DatabaseParameterValidator {

        public List<ValidationIssue> validate(
                DatabaseParameters parameters,
                PlanDefinition plan) {

            List<ValidationIssue> issues = new ArrayList<>();

            if (parameters.storageGb() < plan.minStorageGb()
                    || parameters.storageGb() > plan.maxStorageGb()) {
                issues.add(new ValidationIssue(
                        "storageGb",
                        "OUT_OF_PLAN_RANGE",
                        "Dung lượng vượt giới hạn của plan"));
            }

            if (!plan.supportedRegions().contains(parameters.region())) {
                issues.add(new ValidationIssue(
                        "region",
                        "REGION_NOT_SUPPORTED",
                        "Vùng triển khai không được plan hỗ trợ"));
            }

            if (parameters.backupEnabled()
                    && !plan.features().contains("backup")) {
                issues.add(new ValidationIssue(
                        "backupEnabled",
                        "FEATURE_NOT_INCLUDED",
                        "Plan không hỗ trợ backup"));
            }

            if (!parameters.backupEnabled()
                    && parameters.backupRetentionDays() > 0) {
                issues.add(new ValidationIssue(
                        "backupRetentionDays",
                        "DEPENDENT_PARAMETER",
                        "Thời gian lưu backup chỉ áp dụng khi bật backup"));
            }

            if (parameters.connectionLimit() > plan.maxConnections()) {
                issues.add(new ValidationIssue(
                        "connectionLimit",
                        "OUT_OF_PLAN_RANGE",
                        "Số kết nối vượt giới hạn của plan"));
            }

            return List.copyOf(issues);
        }
    }

Các lớp và exception trong ví dụ là mô hình do ứng dụng định nghĩa. Ở hệ thống thực, cần kiểm tra cả giá trị null, số âm, giá trị mặc định và việc chuyển kiểu từ JSON. Không nên ép kiểu trực tiếp từ Map<String, Object> sang long hoặc boolean mà không xử lý trường hợp sai kiểu, thiếu trường hay số vượt phạm vi.

Một điểm hữu ích của việc trả về danh sách ValidationIssue là broker có thể báo nhiều lỗi cấu hình trong một lần, thay vì bắt người dùng sửa từng lỗi một. Tuy nhiên, lỗi không nên tiết lộ thông tin entitlement của tenant khác hoặc chi tiết nội bộ của backend.

## 7. Kiểm tra entitlement của khách hàng

Entitlement trả lời câu hỏi khách hàng có quyền sử dụng service/plan và các tính năng liên quan hay không. Một tenant có thể được phép dùng service database nhưng chỉ có quyền dùng Basic và Standard; tenant khác có entitlement cho High Availability hoặc vùng triển khai riêng.

Ví dụ:

| Thuộc tính entitlement | Giá trị của tenant A | Quy tắc |
|---|---|---|
| Services | postgres-service | Service request phải thuộc danh sách |
| Plans | basic-plan, standard-plan | Plan HA không được phép |
| Regions | region-a | Không được chọn region-b |
| Storage quota | 500 GB tổng | Reservation mới không được làm vượt quota |
| Instance quota | 10 instances | Không tạo instance thứ 11 |
| Status | ACTIVE | Entitlement hết hạn hoặc bị đình chỉ thì từ chối |
| Expiration | Thời điểm trong tương lai | Kiểm tra theo đồng hồ server và chính sách gia hạn |

Ví dụ service kiểm tra entitlement:

    public final class EntitlementValidator {

        public List<ValidationIssue> validate(
                CustomerEntitlement entitlement,
                String serviceId,
                String planId,
                String region,
                Instant now) {

            List<ValidationIssue> issues = new ArrayList<>();

            if (!"ACTIVE".equals(entitlement.status())) {
                issues.add(new ValidationIssue(
                        "entitlement",
                        "ENTITLEMENT_INACTIVE",
                        "Quyền sử dụng dịch vụ hiện không hoạt động"));
            }

            if (!entitlement.expiresAt().isAfter(now)) {
                issues.add(new ValidationIssue(
                        "entitlement",
                        "ENTITLEMENT_EXPIRED",
                        "Quyền sử dụng dịch vụ đã hết hạn"));
            }

            if (!entitlement.allowedServiceIds().contains(serviceId)) {
                issues.add(new ValidationIssue(
                        "serviceId",
                        "SERVICE_NOT_ENTITLED",
                        "Khách hàng không có quyền sử dụng service này"));
            }

            if (!entitlement.allowedPlanIds().contains(planId)) {
                issues.add(new ValidationIssue(
                        "planId",
                        "PLAN_NOT_ENTITLED",
                        "Khách hàng không có quyền sử dụng plan này"));
            }

            if (!entitlement.allowedRegions().contains(region)) {
                issues.add(new ValidationIssue(
                        "region",
                        "REGION_NOT_ENTITLED",
                        "Khách hàng không có quyền triển khai tại vùng này"));
            }

            return List.copyOf(issues);
        }
    }

Đoạn code minh họa giả định entitlement đã được lấy theo tenant đã xác minh. Trong ứng dụng thật, phải xử lý entitlement không tồn tại, thời điểm hết hạn null theo schema, trạng thái bị thu hồi và lỗi khi entitlement service không truy cập được. Không mặc định cho phép khi không thể xác minh quyền; chính sách fail-open hay fail-closed phải được xác định rõ, và với thao tác tạo tài nguyên có chi phí thường cần từ chối khi không thể xác minh entitlement.

## 8. Kiểm tra quota và tránh vượt hạn mức khi có request đồng thời

Một lỗi thường gặp là đọc quota còn 100 GB, sau đó hai request cùng kiểm tra một lúc và mỗi request đều tạo tài nguyên 80 GB. Cả hai đều thấy request của mình hợp lệ, nhưng tổng 160 GB vượt quota.

Vì vậy, kiểm tra quota và giữ chỗ tài nguyên phải có tính nguyên tử. Một cách tiếp cận:

1. Đọc entitlement và mức sử dụng hiện tại.
2. Bắt đầu transaction hoặc dùng cơ chế reservation có atomic compare-and-set.
3. Tạo reservation gắn với tenant và operation ID, bảo đảm tổng used + reserved + requested không vượt quota.
4. Commit reservation trước khi dispatch công việc provision.
5. Khi provision thành công, chuyển reservation thành usage thực tế.
6. Khi thất bại hoàn toàn hoặc hủy operation, giải phóng reservation theo quy tắc idempotent.

Với nhiều broker replica, khóa trong bộ nhớ của một instance không đủ. Cần dùng database constraint, row-level lock, optimistic version, atomic update hoặc một quota service có API reservation đảm bảo tính nhất quán.

Reservation cũng cần có thời hạn và quy trình reconcile. Nếu worker chết giữa chừng, reservation không nên bị giữ vô hạn; nhưng cũng không được giải phóng khi backend đã tạo tài nguyên. Reconciler phải đối chiếu operation, reservation và trạng thái thực tế của backend trước khi quyết định giải phóng hay chuyển thành usage.

## 9. Validation khi update plan hoặc parameters

Provision và update có ngữ cảnh khác nhau. Khi provision, broker kiểm tra cấu hình khởi tạo. Khi update, broker còn phải so sánh trạng thái hiện tại với trạng thái đích và xác định thay đổi có thể thực hiện an toàn hay không.

Ví dụ một instance đang dùng Standard với 120 GB storage. Người dùng gửi update để chuyển về Basic có giới hạn tối đa 50 GB. Request có thể hợp lệ về schema nhưng không thể áp dụng vì dung lượng hiện tại vượt mức plan đích.

Khi update, cần kiểm tra:

- Instance tồn tại, thuộc đúng tenant và đang ở trạng thái cho phép update.
- Service ID trong request khớp với service của instance đã lưu.
- Plan đích thuộc service đó và entitlement hiện tại cho phép sử dụng.
- Cặp plan nguồn/đích nằm trong transition policy.
- Parameter mới hợp lệ theo plan đích.
- Thay đổi không vi phạm dữ liệu hiện có, quota, vùng, binding hoặc phụ thuộc khác.
- Không có operation thay đổi vòng đời khác đang chạy trên cùng instance.

Không thay plan hiện tại trong state store ngay khi nhận request. Với update bất đồng bộ, lưu currentPlanId, targetPlanId và operation ID riêng. Chỉ cập nhật plan có hiệu lực sau khi backend xác nhận thành công. Nếu update thất bại một phần, cần reconcile hoặc rollback trước khi giải phóng reservation.

## 10. Tích hợp validation vào application service

OSB handler nên làm nhiệm vụ chuyển request framework thành command. Application service điều phối các validator và repository. Một luồng khái niệm:

    public Mono<ProvisionResult> provision(ProvisionCommand command) {
        return tenantResolver.resolve(command.authenticatedCaller())
                .flatMap(tenant -> catalogRepository
                        .findPlan(command.serviceId(), command.planId())
                        .switchIfEmpty(Mono.error(new UnknownPlanException()))
                        .flatMap(plan -> entitlementRepository
                                .findCurrent(tenant.id())
                                .switchIfEmpty(Mono.error(
                                        new MissingEntitlementException()))
                                .flatMap(entitlement -> validateAndReserve(
                                        command, tenant, plan, entitlement))))
                .flatMap(reservation -> infrastructureProvisioner
                        .provision(reservation.command())
                        .flatMap(result -> completeReservation(reservation, result))
                        .onErrorResume(error ->
                                compensateReservation(reservation, error)));
    }

Đây là pseudocode Reactor mô tả thứ tự phụ thuộc, không phải một implementation hoàn chỉnh. Cần định nghĩa rõ transaction boundary, cách phân loại lỗi và hành vi khi infrastructureProvisioner timeout nhưng backend có thể đã thực hiện một phần. Nếu validation cần gọi nhiều dịch vụ blocking, không chạy chúng trực tiếp trên event-loop.

Nên tách các thành phần để kiểm thử độc lập:

| Thành phần | Trách nhiệm |
|---|---|
| Parameter schema validator | Kiểm tra type, required, range, enum và cấu trúc |
| Plan compatibility validator | Kiểm tra parameter và capability theo plan |
| Entitlement validator | Kiểm tra quyền service, plan, feature và region |
| Quota reservation service | Giữ chỗ quota nguyên tử và giải phóng an toàn |
| Instance state validator | Kiểm tra trạng thái, owner và operation đang chạy |
| Application service | Điều phối validation, reservation và provisioning |
| OSB error mapper | Ánh xạ lỗi nghiệp vụ sang response phù hợp với OSB/framework |

## 11. Phản hồi lỗi và tránh rò rỉ thông tin

Khi validation thất bại, broker cần phân biệt lỗi request, lỗi quyền và lỗi phụ thuộc:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Invalid parameter | Sai kiểu, ngoài khoảng, thiếu trường bắt buộc | Trả lỗi request theo hợp đồng OSB |
| Plan incompatibility | Tính năng không có trong plan hoặc region không hỗ trợ | Từ chối cấu hình và chỉ rõ trường liên quan ở mức an toàn |
| Entitlement denied | Tenant không được dùng plan hoặc region | Từ chối theo chính sách authorization |
| Quota exceeded | Hết storage quota hoặc instance quota | Từ chối hoặc hướng dẫn khách hàng xử lý quota |
| Entitlement unavailable | Không thể xác minh quyền do hệ thống phụ thuộc lỗi | Không provision khi chưa xác minh được quyền |
| Concurrent modification | Instance đang có operation khác hoặc version đã thay đổi | Yêu cầu caller đọc lại trạng thái hoặc xử lý theo quy tắc retry |

Mã HTTP và body lỗi cụ thể phải theo phiên bản OSB và Spring Cloud Open Service Broker mà ứng dụng hỗ trợ. Không tự tạo response ngoài hợp đồng chỉ để biểu diễn một mã lỗi nội bộ. Error mapper nên giữ thông tin đủ để người dùng sửa request, nhưng không tiết lộ quota của tenant khác, quy tắc chống gian lận, secret, stack trace hoặc chi tiết API backend.

Log cần có correlation ID, tenant ID đã chuẩn hóa, service/plan ID, operation ID và mã lỗi. Tránh ghi toàn bộ parameters nếu có thể chứa mật khẩu, token, dữ liệu cá nhân hoặc cấu hình nhạy cảm. Có thể ghi tên trường lỗi và loại validation để chẩn đoán mà không lưu giá trị nhạy cảm.

## 12. Kiểm thử quan hệ parameter–plan–entitlement

Unit test nên bao phủ cả trường hợp hợp lệ lẫn trường hợp từng thành phần riêng lẻ hợp lệ nhưng quan hệ tổng thể không hợp lệ.

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Parameter nằm trong giới hạn plan và tenant có entitlement | Validation thành công |
| Storage vượt max của plan nhưng vẫn dưới quota tenant | Từ chối do plan constraint |
| Plan hợp lệ nhưng tenant không có quyền dùng plan | Từ chối do entitlement |
| Tenant có plan entitlement nhưng region không được plan hỗ trợ | Từ chối do plan compatibility |
| Region được plan hỗ trợ nhưng tenant không có quyền ở region đó | Từ chối do entitlement |
| Backup retention lớn hơn 0 khi backup bị tắt | Từ chối do phụ thuộc giữa parameters |
| Plan đích hợp lệ nhưng instance đang UPDATE | Từ chối do state conflict |
| Hai request đồng thời cùng sử dụng quota còn lại | Chỉ reservation phù hợp với hạn mức được commit |
| Entitlement đã hết hạn | Từ chối provision/update theo chính sách |
| Entitlement service không truy cập được | Không tự động cấp quyền khi chưa xác minh được entitlement |
| Worker retry sau khi provision một phần | Reservation và tài nguyên được reconcile, không tạo trùng |

Ngoài unit test, cần integration test cho transaction/reservation và contract test qua OSB endpoint. Các test concurrency nên chạy với nhiều transaction hoặc nhiều worker để chứng minh quota không bị vượt khi request đến đồng thời. Test phải kiểm tra cả trạng thái sau lỗi, vì chỉ xác nhận response HTTP không đủ để chứng minh broker đã giải phóng reservation hoặc giữ instance state chính xác.

## 13. Những sai lầm thường gặp

- Chỉ validate từng parameter mà không kiểm tra quan hệ giữa các parameter.
- Tin tenant ID, quota hoặc role do client gửi trong request.
- Chỉ kiểm tra entitlement khi hiển thị catalog nhưng bỏ qua ở provision/update.
- Dùng tên plan hiển thị để xác định giới hạn thay vì ID ổn định.
- Coi free=true hoặc một metadata flag là bằng chứng khách hàng được cấp quyền.
- Đọc quota rồi provision mà không reservation nguyên tử.
- Giải phóng reservation ngay khi timeout dù backend có thể đã tạo tài nguyên.
- Dùng cùng một validator cho provision và update mà không xét trạng thái instance hiện tại.
- Trả chi tiết entitlement hoặc cấu hình backend trong lỗi công khai.

## Kết luận

Kiểm tra quan hệ giữa tham số, gói dịch vụ và quyền của khách hàng là bước bảo vệ quan trọng trước khi service broker tạo hoặc thay đổi tài nguyên. Broker cần diễn giải request bằng catalog/plan registry đáng tin cậy, xác định tenant từ caller đã xác thực, kiểm tra parameters theo capability của plan và đối chiếu entitlement/quota hiện hành. Với quota, cần reservation nguyên tử để xử lý request đồng thời; với update hoặc thao tác bất đồng bộ, cần giữ trạng thái và operation nhất quán qua retry, lỗi một phần và reconcile. Khi các kiểm tra này được tổ chức trong application/domain layer, broker Spring Cloud có thể cung cấp dịch vụ linh hoạt mà vẫn kiểm soát được quyền sử dụng và giới hạn tài nguyên của từng khách hàng.

# Truy xuất cấu hình hiện tại và các tham số được phép công bố

Service broker không chỉ tạo và thay đổi tài nguyên; trong một số nền tảng, broker còn phải cho phép truy vấn lại thông tin của một service instance đã tồn tại. Chức năng này giúp nền tảng đồng bộ trạng thái, hiển thị cấu hình đang áp dụng và hỗ trợ vận hành. Tuy nhiên, dữ liệu broker lưu để quản lý tài nguyên thường phong phú hơn nhiều so với dữ liệu được phép trả ra ngoài. Một cấu hình có thể chứa password, token, khóa truy cập, địa chỉ nội bộ hoặc thông tin tenant mà caller không được xem.

Với module SPRING_CLOUD_SERVICE_BROKER, cần tách ba việc: lưu cấu hình thực tế của instance, xác định caller có quyền truy xuất instance đó và chọn các trường được phép công bố theo hợp đồng OSB. Endpoint retrieval chỉ trả dữ liệu đã được kiểm tra và lọc; nó không được trả nguyên object persistence hoặc toàn bộ parameters đã nhận khi provision.

## 1. Truy xuất service instance trong Open Service Broker API

OSB API có thao tác Retrieve a Service Instance để nền tảng truy vấn thông tin của một instance đã được provision. Endpoint thường có dạng:

    GET /v2/service_instances/{instance_id}?service_id={service_id}&plan_id={plan_id}
    X-Broker-API-Version: 2.17
    Authorization: Basic ...

instance_id xác định instance trong đường dẫn; service_id và plan_id được gửi trong query string theo hợp đồng của endpoint. Broker cần đối chiếu các giá trị này với bản ghi instance đã lưu. Không nên chỉ tin query parameter vì caller có thể gửi ID không khớp với instance thực tế.

Khả năng truy xuất instance được công bố ở service definition bằng capability instances_retrievable. Trong Java builder của Spring Cloud Open Service Broker, API thường biểu diễn bằng method instancesRetrievable(true). Khi bật capability này, broker cam kết hỗ trợ thao tác retrieval theo phiên bản OSB và framework đang dùng.

Ví dụ khai báo service definition:

    ServiceDefinition service = ServiceDefinition.builder()
            .id("postgres-service-id")
            .name("postgresql-database")
            .description("Dịch vụ cơ sở dữ liệu PostgreSQL")
            .bindable(true)
            .instancesRetrievable(true)
            .plans(plans)
            .build();

Tên method và model cần được đối chiếu với phiên bản Spring Cloud Open Service Broker trong ứng dụng. Capability chỉ nên bật khi broker có thể trả kết quả retrieval đáng tin cậy và đúng hợp đồng. Nếu broker không hỗ trợ retrieval, không công bố capability này như thể endpoint đã sẵn sàng.

## 2. Phân biệt retrieval với các thao tác đọc khác

Một số thao tác có thể cùng trả dữ liệu về một instance nhưng mục đích và hợp đồng khác nhau:

| Thao tác | Câu hỏi được trả lời | Dữ liệu phù hợp |
|---|---|---|
| Retrieve service instance | Instance đang được cấu hình như thế nào? | Service ID, plan ID và các thuộc tính cấu hình được phép công bố |
| Last operation | Provision/update/deprovision gần nhất đang ở bước nào? | Operation state, mô tả tiến độ hoặc lỗi đã chuẩn hóa |
| Retrieve service binding | Binding đã tạo có thông tin gì? | Thông tin binding theo capability và chính sách bảo mật |
| Internal state lookup | Broker cần dữ liệu nào để điều phối? | Toàn bộ trạng thái nội bộ cần thiết, chỉ dành cho thành phần được ủy quyền |

GET service instance không thay thế last operation. Nếu một thao tác update đang chạy bất đồng bộ, endpoint retrieval cần phản ánh cấu hình đã được xác nhận là có hiệu lực theo mô hình trạng thái của broker. Endpoint last operation trả tiến độ của yêu cầu đang chạy. Không lấy cấu hình đích chưa áp dụng rồi trình bày như cấu hình hiện tại.

## 3. Phân biệt cấu hình yêu cầu, cấu hình mong muốn và cấu hình thực tế

Trong vòng đời một service instance, có thể tồn tại ba phiên bản cấu hình:

- **Requested configuration:** các giá trị nền tảng gửi trong request provision hoặc update.
- **Desired configuration:** cấu hình broker đã chấp nhận và đang cố gắng áp dụng.
- **Observed/current configuration:** cấu hình đã được backend xác nhận đang có hiệu lực.

Ba trạng thái này không phải lúc nào cũng giống nhau. Ví dụ instance đang chạy với 100 GB storage. Người dùng gửi update lên 200 GB; broker chấp nhận operation nhưng backend vẫn đang mở rộng volume. Trong thời gian này, desired configuration là 200 GB nhưng observed/current configuration vẫn có thể là 100 GB.

Mô hình persistence có thể lưu riêng các trường:

| Trường | Mục đích |
|---|---|
| instanceId | Định danh instance theo OSB |
| serviceId, planId | Service và plan đã được xác nhận |
| currentParameters | Cấu hình thực tế đã áp dụng và xác minh |
| desiredParameters | Cấu hình đích của operation đang chạy, nếu có |
| resourceReference | Tham chiếu tài nguyên backend |
| status | Trạng thái vòng đời instance |
| activeOperationId | Operation đang xử lý |
| version | Phiên bản bản ghi để kiểm soát cập nhật đồng thời |
| updatedAt | Thời điểm trạng thái được xác nhận gần nhất |

Không nhất thiết phải lưu đúng các field này trong mọi hệ thống. Điều quan trọng là retrieval phải biết trường nào thể hiện cấu hình hiện tại, trường nào mới là cấu hình dự kiến và trường nào chỉ phục vụ điều phối nội bộ.

## 4. Xác định những tham số được phép công bố

Parameters trong request provision có thể chứa nhiều loại dữ liệu. Một số trường mô tả cấu hình có thể trả về cho nền tảng; một số trường là bí mật hoặc chỉ dùng nội bộ. Broker nên phân loại trường ngay khi định nghĩa schema.

Ví dụ cho dịch vụ PostgreSQL:

| Tham số | Phân loại | Có thể trả qua retrieval? | Lý do |
|---|---|---:|---|
| engineVersion | Cấu hình | Có, nếu chính sách cho phép | Hữu ích để hiển thị phiên bản database |
| storageGb | Cấu hình | Có | Mô tả dung lượng đã cấp |
| backupEnabled | Cấu hình | Có | Cho biết tính năng đang bật |
| backupRetentionDays | Cấu hình | Có, nếu được phép | Mô tả chính sách backup |
| region | Metadata triển khai | Tùy chính sách | Có thể tiết lộ vị trí hạ tầng |
| connectionLimit | Cấu hình | Có | Giúp nền tảng hiển thị giới hạn |
| adminPassword | Bí mật | Không | Có thể dùng để đăng nhập quản trị |
| accessToken | Bí mật | Không | Là thông tin xác thực |
| privateKey | Bí mật | Không | Có thể cấp quyền truy cập tài nguyên |
| internalEndpoint | Thông tin nội bộ | Tùy chính sách, mặc định không | Có thể tiết lộ topology hoặc mạng riêng |
| tenantInternalId | Dữ liệu nội bộ | Không | Không cần công bố cho caller |

Không nên suy luận rằng một trường an toàn chỉ vì tên trường không có chữ password hoặc secret. Một URL có thể chứa token trong query string; một object metadata có thể lồng credential; một trường endpoint có thể tiết lộ mạng nội bộ. Việc phân loại cần dựa trên ngữ nghĩa và luồng sử dụng của dữ liệu.

Một chính sách công bố nên theo nguyên tắc allowlist: chỉ trường được đánh dấu rõ ràng là có thể công bố mới được đưa vào response. Không dùng denylist đơn giản kiểu “loại bỏ các key có tên password” vì secret có thể mang tên khác hoặc nằm sâu trong object lồng nhau.

## 5. Xây dựng mô hình cấu hình công khai riêng

Không trả thẳng entity persistence hoặc Map<String, Object> thô từ database. Tạo DTO riêng cho dữ liệu được phép công bố:

    public record PublicInstanceConfiguration(
            String engineVersion,
            long storageGb,
            boolean backupEnabled,
            Integer backupRetentionDays,
            String region,
            Integer connectionLimit) {
    }

    public record ServiceInstanceRecord(
            String instanceId,
            String tenantId,
            String serviceId,
            String planId,
            Map<String, Object> currentParameters,
            Map<String, Object> desiredParameters,
            String status,
            String activeOperationId,
            long version) {
    }

ServiceInstanceRecord là mô hình nội bộ; nó chứa tenant, desired parameters, operation và version nên không được serialize trực tiếp ra response OSB. PublicInstanceConfiguration là mô hình được phép công bố sau khi mapper đã chọn đúng trường và kiểm tra kiểu dữ liệu.

Mapper có thể được triển khai rõ ràng:

    public final class PublicConfigurationMapper {

        public PublicInstanceConfiguration toPublic(
                Map<String, Object> current) {

            return new PublicInstanceConfiguration(
                    stringValue(current, "engineVersion"),
                    longValue(current, "storageGb"),
                    booleanValue(current, "backupEnabled"),
                    nullableIntegerValue(current, "backupRetentionDays"),
                    stringValue(current, "region"),
                    nullableIntegerValue(current, "connectionLimit"));
        }

        private String stringValue(Map<String, Object> values, String key) {
            Object value = values.get(key);
            return value instanceof String text ? text : null;
        }

        private long longValue(Map<String, Object> values, String key) {
            Object value = values.get(key);
            if (value instanceof Number number) {
                return number.longValue();
            }
            throw new IllegalStateException("Missing or invalid numeric field: " + key);
        }

        private boolean booleanValue(Map<String, Object> values, String key) {
            Object value = values.get(key);
            if (value instanceof Boolean flag) {
                return flag;
            }
            throw new IllegalStateException("Missing or invalid boolean field: " + key);
        }

        private Integer nullableIntegerValue(Map<String, Object> values, String key) {
            Object value = values.get(key);
            if (value == null) {
                return null;
            }
            if (value instanceof Number number) {
                return number.intValue();
            }
            throw new IllegalStateException("Invalid integer field: " + key);
        }
    }

Đây là ví dụ minh họa cho allowlist có kiểu. Trong hệ thống thật, cần định nghĩa cách xử lý trường cũ hoặc thiếu sau khi nâng cấp schema. Không nên tự động trả null cho mọi lỗi parse, vì việc đó có thể che giấu dữ liệu persistence hỏng. Có thể phân biệt trường tùy chọn với trường bắt buộc và ghi nhận lỗi dữ liệu nội bộ bằng mã lỗi an toàn.

## 6. Luồng retrieval trong Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp extension point để ứng dụng triển khai truy xuất service instance. Ở các phiên bản phổ biến, logic này thuộc ServiceInstanceService và nhận request model tương ứng, ví dụ GetServiceInstanceRequest. Handler nên chuyển request thành lệnh truy xuất nội bộ; application service kiểm tra quyền và lấy trạng thái; mapper tạo response theo model của framework.

Một luồng xử lý:

1. Nhận instance_id, service_id, plan_id từ request OSB.
2. Xác thực caller theo cơ chế bảo vệ broker.
3. Đọc instance theo ID từ repository.
4. Kiểm tra instance tồn tại và thuộc tenant/organization mà caller được phép truy cập.
5. Đối chiếu service_id và plan_id trong request với bản ghi đã lưu theo quy tắc của OSB.
6. Chọn currentParameters đã được xác nhận, không lấy desiredParameters chưa hoàn tất.
7. Map sang DTO công khai bằng allowlist.
8. Tạo response retrieval bằng model của phiên bản Spring Cloud Open Service Broker đang sử dụng.

Sơ đồ trình tự:

    Platform -> OSB Retrieval Handler: GET service_instances/{id}
    OSB Retrieval Handler -> Application Service: Retrieve command
    Application Service -> Access Policy: Kiểm tra caller và tenant
    Access Policy --> Application Service: Access granted
    Application Service -> Instance Repository: Tìm instance theo ID
    Instance Repository --> Application Service: Current instance state
    Application Service -> Application Service: Đối chiếu serviceId/planId
    Application Service -> Public Mapper: Chọn trường công khai
    Public Mapper --> Application Service: Public configuration
    Application Service --> OSB Retrieval Handler: Retrieval result
    OSB Retrieval Handler --> Platform: OSB response

Ví dụ pseudocode ở lớp application:

    public Mono<RetrievedInstance> retrieve(
            RetrieveInstanceCommand command) {

        return instanceRepository.findById(command.instanceId())
                .switchIfEmpty(Mono.error(new InstanceNotFoundException()))
                .flatMap(instance -> accessPolicy
                        .canRead(command.caller(), instance)
                        .filter(Boolean::booleanValue)
                        .switchIfEmpty(Mono.error(new AccessDeniedException()))
                        .thenReturn(instance))
                .flatMap(instance -> {
                    verifyRequestedIdentifiers(
                            command.serviceId(),
                            command.planId(),
                            instance);

                    PublicInstanceConfiguration configuration =
                            publicConfigurationMapper.toPublic(
                                    instance.currentParameters());

                    return Mono.just(new RetrievedInstance(
                            instance.serviceId(),
                            instance.planId(),
                            configuration,
                            instance.dashboardUrl()));
                });
    }

Đây là pseudocode mô tả trách nhiệm, không phải chữ ký API bắt buộc của framework. Cần ánh xạ RetrievedInstance sang response model thực tế của Spring Cloud Open Service Broker và phiên bản OSB đang hỗ trợ. Nếu framework đã cung cấp originating identity hoặc tenant context trong request model, hãy dùng điểm tích hợp đó thay vì tự đọc HTTP request ở sâu trong application service.

## 7. Kiểm soát quyền truy xuất instance

Biết instance_id không có nghĩa caller được phép đọc instance. Broker cần xác minh quan hệ giữa caller, tenant và tài nguyên.

Các kiểm tra thường cần có:

- Caller đã xác thực và được phép gọi endpoint OSB.
- Tenant được xác định từ nguồn tin cậy, không lấy từ query string hoặc parameters tùy ý.
- Instance thuộc tenant hoặc phạm vi mà caller được quyền quản lý.
- Service ID và plan ID trong request khớp với bản ghi hiện tại hoặc được xử lý theo quy tắc tương thích đã định nghĩa.
- Caller chỉ được nhận trường dữ liệu phù hợp với vai trò và mục đích truy cập.

Nếu broker hỗ trợ nhiều nền tảng hoặc nhiều loại caller, policy có thể khác nhau. Ví dụ, nền tảng quản lý broker có thể được phép truy vấn trạng thái vận hành; tenant application chỉ được xem một tập thông tin công khai. Không nên dùng cùng một DTO nội bộ cho mọi loại caller.

Trường hợp instance không tồn tại và trường hợp caller không có quyền cũng cần được xử lý theo chính sách tránh lộ thông tin. Trong một số hệ thống, trả thông báo phân biệt rõ hai trường hợp có thể giúp dò tìm ID instance của tenant khác. Error mapper nên theo hợp đồng OSB và threat model của broker để quyết định thông tin nào được công bố.

## 8. Truy xuất trong khi operation đang chạy

Với provision hoặc update bất đồng bộ, retrieval có thể xảy ra khi backend chưa hoàn tất. Broker cần xác định rõ trạng thái nào được coi là current:

| Tình huống | Cấu hình nên được coi là hiện tại | Nơi xem tiến độ |
|---|---|---|
| Provision đang chạy, tài nguyên chưa sẵn sàng | Chưa có cấu hình active hoàn chỉnh; chỉ trả những trường mà hợp đồng cho phép | Last operation |
| Provision thành công | Cấu hình đã xác minh sau provision | Retrieval |
| Update đang chạy | Cấu hình trước update vẫn là current cho đến khi backend xác nhận thay đổi | Last operation |
| Update thành công | Cấu hình mới đã xác minh | Retrieval |
| Update thất bại một phần | Trạng thái quan sát từ backend sau reconcile; không tự giả định rollback hoàn tất | Last operation và trạng thái lỗi đã chuẩn hóa |
| Deprovision đang chạy | Instance đang trong quá trình thu hồi; response theo trạng thái và hợp đồng retrieval được hỗ trợ | Last operation |

Nếu operation đang chạy, có thể trả metadata không nhạy cảm về trạng thái hiện tại nếu response model cho phép, nhưng không nên trộn progress fields vào cấu hình công khai một cách tùy tiện. Dữ liệu tiến độ thuộc endpoint last operation. Sau khi worker hoàn tất, repository phải cập nhật current configuration và operation trong một quy trình nhất quán.

## 9. Schema versioning và tương thích tham số

Schema parameters có thể thay đổi theo thời gian. Ví dụ phiên bản đầu dùng storageGb, phiên bản sau bổ sung storageClass hoặc đổi tên một trường. Instance cũ có thể vẫn lưu schema trước đó trong nhiều năm.

Nên lưu version schema hoặc version cấu hình cùng instance:

    public record StoredConfiguration(
            int schemaVersion,
            Map<String, Object> values) {
    }

Khi retrieval:

1. Đọc schema version của instance.
2. Chuyển dữ liệu cũ qua mapper tương thích nếu cần.
3. Chọn allowlist theo schema và chính sách công bố hiện tại.
4. Chuẩn hóa kiểu dữ liệu.
5. Tạo response ổn định theo API version mà nền tảng đang sử dụng.

Không xóa ngay field cũ khỏi persistence khi catalog hoặc application code được nâng cấp. Cần có giai đoạn tương thích để retrieval, update và deprovision vẫn xử lý được instance cũ. Nếu một trường không còn được phép công bố, có thể ngừng trả trường đó mà vẫn giữ dữ liệu nội bộ nếu còn cần cho vận hành.

## 10. Cache, nhất quán và hiệu năng

Retrieval thường được gọi trong các quy trình đồng bộ trạng thái của nền tảng. Endpoint nên đọc từ state store có thẩm quyền hoặc một read model được cập nhật có kiểm soát.

Một số nguyên tắc:

- Dùng index theo instance ID để truy vấn trực tiếp.
- Không gọi backend chậm cho mọi GET nếu trạng thái đã được lưu và đủ mới để trả theo hợp đồng.
- Nếu cần đối chiếu backend, xác định rõ độ trễ chấp nhận được và cách biểu diễn trạng thái chưa đồng bộ.
- Cache chỉ chứa dữ liệu phù hợp với phạm vi tenant/caller; không dùng cache key chỉ theo instance ID nếu response có thể khác theo quyền.
- Khi update hoàn tất, invalidation hoặc cập nhật read model phải được phối hợp với transaction trạng thái.
- GET nên không tạo side effect như cấp phát, rotate credentials hoặc sửa plan.

Nếu dùng read replica hoặc cache eventual consistency, cần cân nhắc nền tảng vừa gửi update xong có thể lập tức truy vấn retrieval. Không trả dữ liệu cũ vô thời hạn. Có thể dùng version, updatedAt hoặc operation completion marker để xác định read model đã bắt kịp.

## 11. Kiểm thử retrieval và chính sách công bố

Kiểm thử cần chứng minh broker trả đúng dữ liệu, lọc đúng dữ liệu và kiểm tra quyền đúng:

| Phạm vi | Ca kiểm thử | Kết quả mong đợi |
|---|---|---|
| Catalog | Service có instancesRetrievable(true) | Catalog công bố đúng capability |
| Handler | GET với instance ID hợp lệ | Trả response theo OSB/framework version |
| Identifier | Query service/plan ID không khớp instance | Từ chối theo quy tắc hợp đồng |
| Authorization | Caller thuộc tenant sở hữu instance | Cho phép đọc trường được công bố |
| Authorization | Caller thuộc tenant khác | Không tiết lộ dữ liệu instance |
| Allowlist | Parameters chứa storage và engine version | Chỉ các trường được cho phép xuất hiện |
| Secret filtering | Parameters có password, token và private key | Không trường bí mật nào xuất hiện trong response hoặc log |
| Async update | Desired plan khác current plan trong lúc operation chạy | Retrieval không trình bày desired config như current |
| Schema migration | Instance lưu schema version cũ | Mapper tương thích tạo response an toàn |
| Cache | Update hoàn tất rồi GET ngay | Response không bị giữ ở trạng thái cũ quá giới hạn |
| Side effect | Gọi GET nhiều lần | Không tạo tài nguyên hoặc thay đổi instance |

Nên có unit test cho PublicConfigurationMapper với payload lồng nhau và các kiểu dữ liệu sai; contract test cho JSON response; integration test cho authorization và persistence; test bảo mật xác nhận secret không xuất hiện trong body, exception message hoặc log.

## 12. Những sai lầm thường gặp

- Bật instances_retrievable nhưng chưa triển khai endpoint retrieval.
- Trả nguyên entity persistence hoặc toàn bộ parameters đã nhận từ request.
- Chỉ loại bỏ các key có tên password, bỏ sót token hoặc secret lồng nhau.
- Lấy desired parameters đang xử lý làm cấu hình hiện tại.
- Tin service ID, plan ID hoặc tenant ID do caller gửi mà không đối chiếu state store.
- Cho rằng biết instance ID là đủ quyền truy xuất.
- Dùng GET để gọi backend có side effect hoặc tự động sửa trạng thái.
- Cache dữ liệu theo instance ID nhưng bỏ qua khác biệt quyền giữa các caller.
- Thay schema parameters mà không hỗ trợ retrieval cho instance cũ.
- Ghi nguyên parameters hoặc response retrieval vào log dù có dữ liệu nhạy cảm.

## Kết luận

Truy xuất cấu hình hiện tại giúp nền tảng và hệ thống vận hành đọc lại trạng thái service instance sau khi provision hoặc update. Trong Spring Cloud Open Service Broker, broker công bố khả năng này bằng instances_retrievable và triển khai extension point retrieval phù hợp với phiên bản framework. Trước khi trả response, broker phải xác thực caller, kiểm tra quyền trên instance, đối chiếu service/plan ID và chuyển cấu hình thực tế qua một allowlist có kiểu. Giữ riêng requested, desired và current configuration giúp retrieval không công bố nhầm thay đổi chưa hoàn tất; DTO công khai riêng và kiểm thử secret filtering giúp broker chỉ tiết lộ đúng những tham số được phép công bố.

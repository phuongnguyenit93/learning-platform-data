# Bảo toàn service_id, plan_id, instance_id và binding_id qua nâng cấp

Một service broker theo Open Service Broker API (OSB API) phải duy trì danh tính của dịch vụ và tài nguyên trong suốt vòng đời của chúng. Platform lưu các định danh mà broker đã chấp nhận để gọi lại những thao tác như provision, update, bind, unbind, deprovision và last_operation. Nếu một bản nâng cấp đổi cách tạo, chuẩn hóa hoặc lưu các ID này, platform có thể không còn tìm thấy instance cũ, binding có thể không được thu hồi đúng hoặc broker có thể tạo tài nguyên provider trùng lặp.

Bốn định danh cần được bảo toàn là:

- **service_id:** định danh dịch vụ trong catalog.
- **plan_id:** định danh một gói dịch vụ thuộc service.
- **instance_id:** định danh service instance do platform sử dụng trong các thao tác vòng đời.
- **binding_id:** định danh một binding cụ thể giữa instance và consumer.

Các ID này thuộc hợp đồng công khai giữa platform và broker. Chúng cần ổn định qua nâng cấp ứng dụng, thay đổi schema database, đổi provider adapter, chuyển vùng triển khai hoặc thay đổi cách tổ chức nội bộ. Broker có thể thay đổi tên class, bảng dữ liệu, provider resource ID hay cấu trúc cấu hình, nhưng phải giữ được khả năng diễn giải những định danh platform đã gửi từ trước.

Bài học này trình bày cách quản lý ID công khai và ID nội bộ, duy trì catalog tương thích, tiến hóa service plan, di chuyển dữ liệu không làm mất mapping, triển khai rolling upgrade, xử lý binding và credentials, cũng như xây dựng kiểm thử chứng minh một broker mới vẫn quản lý được tài nguyên được tạo bởi phiên bản cũ.

## 1. Vì sao định danh phải ổn định?

Giả sử platform đã provision một PostgreSQL instance:

~~~text
service_id   = postgres-service
plan_id      = postgres-production
instance_id  = 7b2e...
binding_id   = 9a41...
~~~

Broker lưu mapping giữa instance ID và resource ID do provider trả về. Ứng dụng tạo binding và nhận credentials. Vài tháng sau, broker được nâng cấp để dùng provider adapter mới, schema database mới và cách đặt tên resource mới.

Nếu phiên bản mới chỉ tìm instance theo provider resource ID, trong khi platform vẫn gọi bằng instance ID cũ, broker sẽ không tìm thấy tài nguyên. Nếu broker đổi plan ID vì tên hiển thị thay đổi, catalog cũ và instance hiện hữu có thể mất liên kết. Nếu binding ID bị tái tạo khi rotate credential, lệnh unbind từ platform có thể không thu hồi đúng binding cũ.

Hậu quả có thể gồm:

- Platform gọi deprovision nhưng broker trả not found.
- Instance cũ bị tạo lại thay vì được nhận diện.
- Một plan đang được instance sử dụng biến mất khỏi catalog.
- Binding record không còn trỏ tới credentials hoặc provider attachment cũ.
- Unbind không thu hồi được quyền truy cập.
- Operation đang chạy không còn liên kết với instance sau migration.
- Rollback ứng dụng không thể đọc dữ liệu đã được ghi theo schema mới.

Ổn định ID không chỉ là giữ nguyên chuỗi trong response. Broker cần bảo toàn cả quan hệ và ngữ nghĩa của ID qua mọi lớp: catalog, request handler, database, operation journal, provider mapping, binding store, audit và API response.

## 2. Phân biệt bốn định danh trong OSB

| Định danh | Phạm vi | Vai trò | Khi nào được tạo |
|---|---|---|---|
| service_id | Catalog của broker | Chọn loại dịch vụ | Khi định nghĩa service trong catalog |
| plan_id | Một service trong catalog | Chọn cấu hình/gói dịch vụ | Khi định nghĩa plan |
| instance_id | Một service instance trên platform | Nhận diện tài nguyên được provision | Khi platform yêu cầu provision |
| binding_id | Một binding thuộc instance | Nhận diện consumer binding | Khi platform yêu cầu bind |

service_id và plan_id thường xuất hiện trong catalog và được platform gửi lại khi tạo hoặc cập nhật instance. instance_id và binding_id xuất hiện trong URL và request của các thao tác vòng đời.

Không nên dùng một trường ID chung cho cả bốn khái niệm. Chúng có vòng đời và phạm vi duy nhất khác nhau. Một service có nhiều plan; một plan có nhiều instance; một instance có thể có nhiều binding.

~~~mermaid
flowchart TD
    S[service_id: postgres-service] --> P1[plan_id: small]
    S --> P2[plan_id: production]
    P2 --> I1[instance_id: instance-A]
    P2 --> I2[instance_id: instance-B]
    I1 --> B1[binding_id: app-binding]
    I1 --> B2[binding_id: report-binding]
~~~

Một thay đổi plan không đồng nghĩa đổi service ID. Một lần rotate password không đồng nghĩa tạo binding ID mới. Một lần thay provider resource không đồng nghĩa platform cần nhận instance ID mới.

## 3. Coi public ID là opaque identifier

Broker nên xem các ID do platform gửi là chuỗi opaque: dùng chúng như định danh, không suy diễn cấu trúc nội bộ từ nội dung chuỗi.

Không nên:

- Tách instance ID theo dấu gạch ngang để suy ra tenant hoặc region.
- Chuyển toàn bộ ID thành chữ thường nếu contract không quy định.
- Cắt ngắn ID để vừa cột database.
- Parse một tiền tố cũ rồi tạo lại ID theo format mới.
- Dùng tên hiển thị của service hoặc plan làm ID.
- Tự thay ID của platform bằng provider resource ID trong response.

Hai chuỗi chỉ khác chữ hoa/chữ thường có thể được coi là hai ID khác nhau tùy contract và cách platform phát sinh ID. Broker cần bảo toàn chính xác giá trị nhận được và chọn collation/kiểu so sánh database phù hợp. Không tự chuẩn hóa nếu chưa có quy tắc tương thích đã được xác minh.

Nếu cần ID nội bộ có format riêng, hãy tạo một internal UUID độc lập và lưu mapping giữa public ID và internal ID. Đừng ép public ID phải tuân theo format nội bộ.

## 4. Giữ ổn định service_id trong catalog

service_id là định danh công khai của một service. Tên hiển thị, mô tả, icon hoặc metadata có thể thay đổi, nhưng service ID đã được platform sử dụng cần được giữ nguyên.

Ví dụ catalog:

~~~json
{
  "services": [
    {
      "id": "postgres-service",
      "name": "Managed PostgreSQL",
      "description": "Managed relational database",
      "bindable": true,
      "plans": []
    }
  ]
}
~~~

Nếu đổi tên hiển thị từ "Managed PostgreSQL" thành "PostgreSQL Database", broker vẫn nên giữ id là postgres-service nếu đây là cùng một dịch vụ về mặt hợp đồng.

Đổi service_id có thể khiến platform hiểu đó là một service hoàn toàn mới. Các instance cũ vẫn lưu service ID cũ; broker phải tiếp tục xử lý chúng. Nếu ID cũ bị xóa khỏi catalog hoặc không còn được nhận diện, những thao tác update, bind hoặc deprovision có thể không được thực hiện đúng.

Khi cần thay thế service, hãy xác định đó là đổi metadata hay một sản phẩm mới có semantics khác. Nếu là sản phẩm mới, có thể thêm service ID mới và duy trì service ID cũ cho instance hiện hữu trong giai đoạn hỗ trợ. Không tái sử dụng ID cũ cho một loại dịch vụ khác.

## 5. Giữ ổn định plan_id khi thay đổi tên và cấu hình

plan_id nhận diện một plan cụ thể trong service. Plan có thể có tên hiển thị, mô tả, giá, quota, giới hạn và đặc tính kỹ thuật.

Ví dụ:

~~~json
{
  "id": "postgres-production",
  "name": "Production",
  "description": "Production database with backup",
  "free": false,
  "bindable": true
}
~~~

Nếu chỉ đổi tên hiển thị hoặc mô tả, thường có thể giữ nguyên plan ID. Nhưng nếu semantics thay đổi đáng kể, chẳng hạn dung lượng, SLA, backup policy hoặc giới hạn kết nối khác đi, cần đánh giá liệu đó vẫn là cùng plan hay phải tạo plan ID mới.

Một plan ID không nên được tái sử dụng cho cấu hình khác đến mức platform hoặc operator không thể hiểu instance cũ đang sở hữu điều kiện nào. Cùng một chuỗi plan ID qua hai phiên bản broker cần có ngữ nghĩa tương thích hoặc có migration rõ ràng.

Các trường hợp:

| Thay đổi | Hướng xử lý |
|---|---|
| Đổi tên hiển thị | Giữ plan ID |
| Sửa mô tả hoặc tài liệu | Giữ plan ID |
| Sửa metadata không ảnh hưởng provisioning | Giữ plan ID nếu contract cho phép |
| Tăng quota mặc định cho instance mới | Đánh giá tương thích; không tự đổi tài nguyên cũ |
| Thay đổi loại storage hoặc SLA căn bản | Cân nhắc plan ID mới |
| Ngừng bán plan | Ngừng cấp instance mới theo chính sách nhưng vẫn quản lý instance cũ |
| Thay provider triển khai nhưng giữ semantics | Giữ plan ID nếu mapping và vận hành tương thích |

Không dùng tên plan làm khóa database. Tên có thể đổi theo ngôn ngữ hoặc branding; plan ID là định danh ổn định.

## 6. Ngừng cung cấp plan mà không làm mất instance cũ

Một plan có thể không còn được cung cấp cho khách hàng mới nhưng vẫn đang được nhiều instance sử dụng. Xóa plan khỏi toàn bộ mô hình dữ liệu có thể làm broker không còn biết cách update hoặc deprovision những instance đó.

Nên phân biệt:

- **Selectable for new instances:** platform có thể chọn plan khi provision mới.
- **Existing instances supported:** broker vẫn nhận diện và quản lý instance đang dùng plan.
- **Update target:** plan có được phép làm đích của update hay không.
- **Deprecated:** plan đã được thay thế nhưng vẫn cần duy trì mapping.
- **Retired:** plan không còn cấp mới; vòng đời instance cũ vẫn được hỗ trợ theo chính sách.

Catalog OSB không phải lúc nào cũng biểu diễn mọi trạng thái quản trị nội bộ này. Broker có thể cần cấu hình nội bộ để giữ plan cũ cho xử lý instance hiện hữu, đồng thời kiểm soát việc cấp mới theo khả năng platform và contract đang triển khai.

Nếu loại plan cũ khỏi catalog, phải kiểm tra cách platform và framework xử lý các instance đang tham chiếu plan đó. Một lựa chọn là giữ entry cũ ở trạng thái tương thích trong thời gian migration. Nếu platform không hỗ trợ trạng thái deprecation, broker cần chính sách công bố catalog phù hợp và vẫn duy trì lookup nội bộ theo ID cũ.

Không xóa plan record chỉ vì plan không còn được chọn cho provision mới.

## 7. Bảo toàn instance_id qua toàn bộ vòng đời

instance_id là định danh platform sử dụng cho một service instance. Broker cần dùng chính xác ID này để tìm instance qua provision retry, update, last_operation và deprovision.

Bảng service instance nên lưu public ID độc lập với provider resource ID:

~~~sql
CREATE TABLE service_instance (
    internal_id UUID PRIMARY KEY,
    service_instance_id VARCHAR(255) NOT NULL,
    service_id VARCHAR(255) NOT NULL,
    plan_id VARCHAR(255) NOT NULL,
    tenant_ref VARCHAR(255) NOT NULL,
    provider_key VARCHAR(100) NOT NULL,
    provider_resource_id VARCHAR(512),
    state VARCHAR(40) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_service_instance_public_id
        UNIQUE (service_instance_id)
);
~~~

Đây là schema minh họa. Nếu broker phục vụ nhiều platform hoặc namespace ID có phạm vi riêng, khóa duy nhất có thể cần bao gồm broker/platform scope. Phạm vi đó phải được xác định theo contract và cách triển khai, không được tự thêm tenant vào ID public rồi trả về platform.

internal_id là khóa nội bộ. service_instance_id là ID công khai. provider_resource_id là ID từ provider. Ba giá trị không được ghi đè lẫn nhau.

Khi thay provider, broker có thể cập nhật provider key và resource mapping sau một migration có kiểm soát, nhưng platform vẫn dùng instance ID cũ.

## 8. Bảo toàn binding_id và quan hệ với instance

Một service instance có thể có nhiều binding. Mỗi binding cần giữ ID riêng và liên kết đúng instance:

~~~sql
CREATE TABLE service_binding (
    internal_id UUID PRIMARY KEY,
    binding_id VARCHAR(255) NOT NULL,
    service_instance_id VARCHAR(255) NOT NULL,
    state VARCHAR(40) NOT NULL,
    provider_binding_ref VARCHAR(512),
    secret_reference VARCHAR(512),
    credential_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_binding_public_id
        UNIQUE (binding_id),
    CONSTRAINT fk_binding_instance
        FOREIGN KEY (service_instance_id)
        REFERENCES service_instance(service_instance_id)
);
~~~

Khóa duy nhất của binding có thể cần thêm platform/broker scope nếu ID không duy nhất toàn cục trong triển khai. Cần bảo đảm truy vấn luôn kiểm tra binding ID cùng instance ID theo request path; không chỉ tìm binding theo một chuỗi ID rồi bỏ qua quan hệ cha.

Binding ID không nên bị đổi khi:

- Password được rotate.
- Provider endpoint thay đổi.
- Secret được chuyển từ Kubernetes Secret sang external secret manager.
- Workload được rollout.
- Broker thay đổi cách mã hóa credentials.
- Provider adapter được thay thế nhưng binding vẫn còn hiệu lực.

Nếu cần đổi credentials hoặc provider-side binding reference, cập nhật mapping nội bộ và credential version, giữ binding ID mà platform đã biết.

## 9. Không dùng provider resource ID thay cho instance_id

Provider có thể trả resource ID như db-7f8a, Kubernetes UID hoặc ARN. Đây là định danh thuộc hệ thống provider và có thể thay đổi khi migrate, recreate hoặc đổi provider.

Không nên trả provider resource ID làm instance_id cho platform. Broker cần một lớp mapping:

| Public ID của OSB | Internal ID | Provider reference |
|---|---|---|
| instance-123 | UUID-A | cloud-a/db-7f8a |
| instance-456 | UUID-B | cluster-2/namespace/db-456 |
| binding-789 | UUID-C | cloud-a/user/u-91 |

Khi migrate database từ provider A sang provider B, public instance ID vẫn giữ nguyên. Broker chỉ cập nhật provider reference sau khi migration thành công và xác minh resource mới.

Mapping cần được ghi bền vững, có audit và hỗ trợ phục hồi. Nếu broker chỉ lưu provider ID trong memory hoặc suy ra từ tên tài nguyên, restart hoặc thay đổi provider có thể làm mất liên kết.

## 10. Giữ định danh qua schema migration

Nâng cấp broker thường kéo theo thay đổi schema. Ví dụ cột service_instance_id được đổi tên, tăng độ dài, chuyển kiểu hoặc tách sang bảng mapping riêng.

Migration phải bảo toàn giá trị và uniqueness. Một quy trình an toàn thường dùng expand-and-contract:

1. **Expand:** thêm cột/bảng mới mà code cũ vẫn hoạt động.
2. **Backfill:** sao chép dữ liệu cũ sang cấu trúc mới, có thể chạy theo batch.
3. **Dual read hoặc dual write:** trong giai đoạn chuyển tiếp, code đọc/ghi tương thích với hai cấu trúc theo kế hoạch.
4. **Verify:** so sánh số bản ghi, giá trị ID, quan hệ và constraint.
5. **Switch:** chuyển code sang cấu trúc mới.
6. **Contract:** chỉ xóa cột/bảng cũ sau khi mọi phiên bản chạy đều không còn phụ thuộc.

Ví dụ thêm cột internal UUID mà vẫn giữ public ID:

~~~sql
ALTER TABLE service_instance
    ADD COLUMN internal_id UUID;

UPDATE service_instance
SET internal_id = gen_random_uuid()
WHERE internal_id IS NULL;
~~~

Cú pháp UUID generation phụ thuộc database. Với bảng lớn, backfill cần chia batch và theo dõi lock, replication lag và transaction log. Không chạy một migration dài trên production mà chưa đánh giá tác động.

Không tái tạo public ID trong backfill. Dữ liệu cũ là nguồn sự thật cho ID mà platform đã sử dụng.

## 11. Kiểm tra độ dài và kiểu dữ liệu ID

Cột ID phải đủ khả năng lưu giá trị đã được chấp nhận trước đó. Việc tăng độ dài thường dễ hơn giảm độ dài.

Các lỗi cần tránh:

- Chuyển VARCHAR sang cột ngắn hơn và cắt mất phần cuối.
- Đổi sang kiểu UUID khi platform có thể gửi ID không phải UUID.
- Thay collation làm thay đổi so sánh chữ hoa/chữ thường.
- Dùng numeric type cho ID có thể chứa ký tự.
- Thêm prefix hoặc suffix khi đọc dữ liệu cũ.
- Dùng trim hoặc normalize không có trong contract.
- Tạo unique index mới nhưng không xử lý duplicate hiện có trước.

Nếu cần chuyển kiểu, hãy giữ cột public ID dạng chuỗi đủ dài. Có thể thêm internal UUID làm khóa kỹ thuật thay vì ép public ID vào một định dạng nội bộ.

Trước migration, thống kê độ dài lớn nhất, ký tự hiện có, giá trị trùng và null. Sau migration, so sánh từng tập dữ liệu hoặc checksum theo batch để phát hiện sai lệch.

## 12. Tạo alias khi cần chuyển đổi định danh nội bộ

Đôi khi broker cần thay cấu trúc nội bộ hoặc gộp dữ liệu từ nhiều hệ thống. Nếu ID nội bộ cũ cần được ánh xạ sang ID nội bộ mới, dùng bảng alias/reference thay vì đổi public ID.

Ví dụ:

~~~sql
CREATE TABLE resource_id_alias (
    alias_type VARCHAR(40) NOT NULL,
    legacy_id VARCHAR(255) NOT NULL,
    internal_id UUID NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (alias_type, legacy_id)
);
~~~

Bảng này có thể ánh xạ legacy provider reference hoặc internal key. Với public OSB ID, ưu tiên giữ chính cột public ID ổn định; alias chỉ dùng khi có yêu cầu migration thực sự.

Không để một alias trỏ tới nhiều tài nguyên. Không tái sử dụng legacy ID cho tài nguyên mới. Nếu cần duy trì alias lâu dài, phải có ownership, uniqueness và audit.

## 13. Catalog versioning và khả năng tương thích

Catalog là hợp đồng mà platform đọc để biết service và plan nào có thể được sử dụng. Khi broker nâng cấp, catalog có thể thêm metadata, thay đổi mô tả hoặc bổ sung plan, nhưng cần bảo toàn các entry mà instance hiện hữu phụ thuộc.

Nên có catalog snapshot hoặc fixture theo release để so sánh:

- Service ID cũ vẫn tồn tại hoặc có chính sách hỗ trợ rõ.
- Plan ID cũ vẫn có thể được nhận diện.
- Các thuộc tính bindable, plan_updateable và metadata không bị đổi ngoài ý muốn.
- Plan mới có ID riêng.
- Không có ID bị tái sử dụng cho semantics khác.
- Catalog response vẫn đúng cấu trúc và API version.
- Các service/plan được retire không làm mất khả năng deprovision instance cũ.

Một kiểm thử compatibility có thể lấy catalog ở phiên bản trước và phiên bản mới, so sánh tập ID:

~~~java
assertThat(newCatalog.serviceIds())
        .containsAll(previousCatalog.requiredServiceIds());

assertThat(newCatalog.planIdsFor("postgres-service"))
        .containsAll(previousCatalog.requiredPlanIds());
~~~

Đây là assertion minh họa. Một số plan có thể được retire theo chính sách; test cần dùng danh sách ID phải duy trì thay vì bắt buộc mọi ID lịch sử tồn tại mãi mãi.

## 14. Không thay semantics plan một cách âm thầm

Giữ nguyên plan ID nhưng thay đổi cấu hình thực thi có thể làm instance hiện hữu bị ảnh hưởng dù ID không đổi.

Ví dụ plan production trước đây cấp 200 GiB storage và backup 14 ngày. Bản nâng cấp đổi mặc định thành 100 GiB và backup 7 ngày. Instance cũ vẫn có plan ID production nhưng semantics đã khác.

Cần phân biệt:

- Thay đổi chỉ áp dụng cho instance mới.
- Thay đổi metadata hiển thị.
- Thay đổi policy cho instance hiện hữu.
- Thay đổi cần một OSB update operation.
- Thay đổi không tương thích cần plan ID mới.

Không tự động áp dụng cấu hình plan mới lên mọi instance cũ chỉ vì broker restart hoặc catalog reload. Nếu cần migration instance, phải có kế hoạch riêng, operation state, audit và khả năng theo dõi kết quả.

Với plan update, kiểm tra capability và quy tắc update của broker. Nếu plan không cho phép update, không tự chuyển plan để phù hợp cấu hình mới.

## 15. Bảo toàn operation đang chạy qua nâng cấp

Một broker có thể được nâng cấp trong khi provision hoặc deprovision đang chạy. Operation journal cần lưu đủ dữ liệu để phiên bản mới tiếp tục xử lý.

Operation record nên giữ:

- operation ID của broker.
- service instance ID và binding ID liên quan.
- operation type.
- source/target plan ID nếu có.
- provider key và provider operation ID.
- request fingerprint hoặc payload snapshot đã làm sạch.
- state, attempt count, lease và version.
- schema/event version cần để diễn giải message cũ.

Worker phiên bản mới phải đọc được operation được tạo bởi phiên bản cũ. Nếu message queue còn event cũ, consumer mới phải hiểu schema event cũ hoặc có bước chuyển đổi tương thích.

Không xóa operation cũ khi deploy. Không đổi operation ID chỉ vì code tạo ID đã thay đổi. Nếu provider operation ID không còn dùng, giữ mapping hoặc trạng thái migration để worker biết cách hoàn tất operation đang dở.

## 16. Bảo toàn binding credentials khi thay đổi secret storage

Broker có thể chuyển từ lưu credentials trong database sang secret manager, hoặc Kubernetes controller có thể chuyển từ Secret trực tiếp sang External Secrets Operator/CSI.

Binding ID vẫn cần giữ nguyên. Thay đổi nằm ở nơi lưu secret và reference.

Ví dụ trước migration:

~~~text
binding_id = binding-456
secret_reference = db-row:binding-456
credential_version = 1
~~~

Sau migration:

~~~text
binding_id = binding-456
secret_reference = vault://broker/bindings/binding-456
credential_version = 1
~~~

Quy trình cần:

1. Đọc credential cũ bằng quyền kiểm soát.
2. Ghi vào secret store mới.
3. Xác minh secret reference mới có thể truy cập.
4. Cập nhật binding mapping trong transaction.
5. Xác minh workload vẫn kết nối được.
6. Thu hồi hoặc xóa bản cũ theo retention policy.
7. Ghi audit event không chứa secret.

Không tạo binding ID mới chỉ vì chuyển secret store. Nếu credentials được rotate, có thể tăng credential version trong binding record nhưng giữ ID binding.

## 17. Thay provider adapter mà không đổi public identity

Khi chuyển từ provider A sang provider B, broker có thể cần tạo resource mới và cập nhật mapping. Đây là một migration tài nguyên, không phải thay ID OSB.

Một quy trình tổng quát:

1. Đọc instance theo public instance ID.
2. Kiểm tra plan, trạng thái và khả năng migration.
3. Tạo resource đích bằng adapter mới.
4. Chuyển dữ liệu hoặc cấu hình theo chính sách.
5. Xác minh resource đích hoạt động.
6. Cập nhật provider reference và adapter key trong transaction.
7. Giữ nguyên service ID, plan ID và instance ID nếu semantics dịch vụ không đổi.
8. Thu hồi resource cũ sau khi xác nhận chuyển đổi.
9. Cập nhật binding credentials hoặc endpoint theo quy trình có kiểm soát.
10. Lưu operation history và audit.

Không cập nhật mapping sang provider mới trước khi resource đích được xác minh. Nếu migration thất bại, broker cần biết resource nào đang sở hữu instance và tránh để hai provider cùng bị coi là active.

Nếu provider mới có semantics khác, SLA khác hoặc khả năng khác, cần đánh giá plan ID và catalog. Giữ ID chỉ khi hợp đồng dịch vụ vẫn tương thích.

## 18. Rolling upgrade và nhiều phiên bản chạy đồng thời

Trong triển khai rolling, phiên bản cũ và mới có thể cùng chạy trong một khoảng thời gian. Cả hai cùng đọc/ghi database và có thể cùng xử lý queue.

Cần bảo đảm:

- Schema mới vẫn tương thích với code cũ trong giai đoạn expand.
- Code mới có thể đọc dữ liệu cũ.
- Event mới không làm worker cũ crash nếu queue dùng chung.
- Không đổi cách normalize public ID giữa hai phiên bản.
- Unique constraint và transaction bảo vệ cả hai phiên bản.
- Catalog response không dao động theo replica theo cách làm platform hiểu sai.
- Một operation không bị hai phiên bản claim đồng thời.

Có thể triển khai theo thứ tự:

~~~text
1. Deploy schema expand
2. Deploy code version N+1 có backward compatibility
3. Chờ tất cả replica version N dừng
4. Chạy backfill/verify
5. Chuyển reader/writer sang schema mới
6. Deploy schema contract ở release sau
~~~

Nếu phiên bản mới ghi một định dạng mà phiên bản cũ không thể đọc, rolling upgrade có thể làm lỗi ngẫu nhiên tùy request được định tuyến tới replica nào. Cần tránh thay đổi định dạng dữ liệu không tương thích trong cùng cửa sổ chạy chung.

## 19. Quy trình migration dữ liệu có kiểm soát

Một kế hoạch migration nên có các bước rõ:

**Trước migration**

- Chụp backup và xác minh có thể restore.
- Đếm số service instance, binding và operation.
- Xuất danh sách public ID cùng quan hệ quan trọng.
- Kiểm tra ID trùng, null, độ dài và ký tự.
- Ghi lại catalog snapshot.
- Xác định operation đang active.
- Xác định provider mapping và secret reference.
- Chốt điều kiện rollback.

**Trong migration**

- Thêm schema mới theo expand-and-contract.
- Backfill theo batch có thể resume.
- Dùng transaction hoặc checkpoint để không chạy lại gây duplicate.
- Dual-write nếu cần, có metric phát hiện lệch.
- Không đổi public ID.
- Tạm hạn chế thao tác xung đột nếu migration cần khóa dữ liệu.

**Sau migration**

- So sánh số lượng và checksum.
- Kiểm tra uniqueness và foreign key.
- Kiểm tra instance/plan/service mapping.
- Kiểm tra binding-to-instance mapping.
- Kiểm tra operation đang chạy.
- Thử đọc và deprovision một tài nguyên test theo ID cũ.
- Theo dõi error rate và not-found rate.
- Chỉ contract schema cũ sau khi xác nhận mọi replica và worker đã chuyển đổi.

Không chỉ dựa vào migration tool báo success. Cần xác minh dữ liệu theo invariant nghiệp vụ.

## 20. Rollback khi phiên bản mới đã ghi dữ liệu

Rollback ứng dụng không tự động rollback schema hoặc dữ liệu. Nếu phiên bản mới đã ghi cột mới, format mới hoặc event schema mới, phiên bản cũ có thể không đọc được.

Một số nguyên tắc:

- Duy trì schema backward-compatible trong cửa sổ rollback.
- Không xóa cột cũ ngay khi deploy code mới.
- Dùng dual-write hoặc compatibility view khi cần.
- Không phát event version mới mà consumer cũ không hiểu trong lúc chúng còn chạy.
- Giữ mapping legacy đủ lâu để rollback và phục hồi.
- Có forward-fix plan nếu dữ liệu mới không thể chuyển ngược an toàn.

Nếu migration đã thay đổi provider resource hoặc rotate credentials, rollback code không thể tự đưa provider state trở lại. Cần migration bù trừ hoặc reconciliation có kiểm soát. Không chạy down migration phá hủy public ID mapping chỉ để đưa schema về trạng thái cũ.

## 21. Bảo toàn ID khi đổi cách chuẩn hóa hoặc collation

Một số hệ thống cũ có thể đã lưu ID sau khi trim, lowercase hoặc thay ký tự. Khi nâng cấp, việc thay đổi quy tắc normalization có thể khiến hai ID trước đây bị nhập làm một hoặc một ID cũ không còn được tìm thấy.

Trước khi thay đổi:

1. Xác định quy tắc hiện tại ở API, application và database.
2. Lấy tập ID thực tế đã được lưu.
3. Kiểm tra collision nếu áp dụng normalization mới.
4. Xác định platform gửi ID với dạng nào.
5. Thử truy vấn chính xác các ID lịch sử.
6. Thiết kế alias hoặc compatibility lookup nếu có dữ liệu cũ đã biến đổi.
7. Chỉ chuyển đổi khi có kế hoạch và test đầy đủ.

Không tự động lowercase ID trong code mới nếu phiên bản cũ không làm vậy. Không thay collation unique index mà chưa phân tích collision.

Nếu hệ thống đã làm mất thông tin do normalization trước đây, cần xử lý bằng mapping đã xác minh; không thể khôi phục chuỗi gốc chỉ bằng suy đoán.

## 22. Giữ tính duy nhất và không tái sử dụng ID

ID đã được dùng cho tài nguyên nên không được tái sử dụng cho một tài nguyên khác sau khi deprovision. Nếu ID cũ được tái sử dụng, một request retry hoặc message trễ có thể tác động nhầm tài nguyên mới.

Cần cân nhắc:

- Unique constraint hoặc tombstone cho ID đã xóa.
- Lưu bản ghi deprovisioned trong thời gian retention phù hợp.
- Không xóa operation history ngay sau deprovision.
- Giữ binding ID cũ để nhận diện retry unbind nếu contract yêu cầu.
- Không tái dùng service/plan ID cho semantics khác.
- Khi import dữ liệu, kiểm tra ID collision với dữ liệu đang hoạt động và lịch sử còn hiệu lực.

Tombstone có thể lưu public ID, loại tài nguyên, thời điểm xóa và reference audit tối thiểu. Không cần giữ secret hoặc toàn bộ payload cũ trong tombstone.

## 23. Kiểm thử tương thích qua các phiên bản

Kiểm thử nâng cấp cần dùng dữ liệu được tạo bởi phiên bản cũ. Một bộ test chỉ tạo dữ liệu mới bằng code hiện tại không phát hiện được lỗi đọc dữ liệu lịch sử.

Có thể lưu fixture database hoặc snapshot đã được làm sạch từ release trước. Test nâng cấp:

1. Khởi tạo database theo schema phiên bản N.
2. Nạp service, plan, instance, binding và operation mẫu.
3. Nâng schema lên phiên bản N+1.
4. Khởi động broker phiên bản N+1.
5. Gọi catalog và xác minh service/plan ID.
6. Gọi last_operation cho operation cũ.
7. Gọi bind/unbind hoặc update theo tình huống hỗ trợ.
8. Gọi deprovision một instance fixture.
9. Kiểm tra provider mapping và secret reference.
10. Xác minh ID không đổi và không có tài nguyên duplicate.

Một ma trận tối thiểu:

| Dữ liệu tạo ở version N | Hành động ở version N+1 | Điều cần xác minh |
|---|---|---|
| Catalog service/plan | GET catalog | ID và semantics được bảo toàn |
| Instance ACTIVE | Update hoặc deprovision | Instance ID được lookup đúng |
| Instance PROVISIONING | Recovery worker | Operation cũ tiếp tục được xử lý |
| Binding ACTIVE | Unbind | Binding ID và provider reference còn đúng |
| Binding credentials | Secret lookup/rotation | Binding ID giữ nguyên, secret truy cập được |
| Instance đã xóa | Retry deprovision | Không tạo hoặc xóa nhầm tài nguyên |
| Event outbox cũ | Consumer mới xử lý | Event schema được hỗ trợ |

## 24. Kiểm thử catalog snapshot và contract

Có thể tạo golden fixture cho catalog của mỗi release. Khi thay đổi catalog, test so sánh ID và các thuộc tính quan trọng.

Ví dụ:

~~~java
@Test
void catalogKeepsExistingServiceAndPlanIds() {
    var catalog = catalogService.getCatalog();

    assertThat(catalog.services())
            .extracting(ServiceDefinition::id)
            .contains("postgres-service");

    var postgres = catalog.requireService("postgres-service");

    assertThat(postgres.plans())
            .extracting(PlanDefinition::id)
            .contains("postgres-production");
}
~~~

Ngoài ID, cần kiểm tra:

- Bindable có còn đúng không.
- Plan updateable có đúng semantics không.
- Metadata cần cho platform có tương thích không.
- Service/plan retired có xử lý instance cũ không.
- Catalog không chứa ID duplicate.
- ID mới không vô tình ghi đè ID cũ.

Snapshot test không nên buộc mọi mô tả hoặc trường metadata bất biến. Hãy tách field identity và contract-critical khỏi field có thể thay đổi như description hoặc display name.

## 25. Kiểm thử database mapping và migration

Với mỗi ID, test cần kiểm tra cả uniqueness và quan hệ:

~~~sql
SELECT service_instance_id, COUNT(*)
FROM service_instance
GROUP BY service_instance_id
HAVING COUNT(*) > 1;

SELECT binding_id, COUNT(*)
FROM service_binding
GROUP BY binding_id
HAVING COUNT(*) > 1;

SELECT b.binding_id
FROM service_binding b
LEFT JOIN service_instance i
  ON i.service_instance_id = b.service_instance_id
WHERE i.service_instance_id IS NULL;
~~~

Các truy vấn này giúp phát hiện duplicate và binding mồ côi. Cần bổ sung kiểm tra:

- Service ID và plan ID tham chiếu được catalog registry.
- Provider mapping không bị null với instance cần provider resource.
- Operation liên kết đúng instance.
- Binding liên kết đúng instance và tenant scope.
- ID trước/sau migration có cùng giá trị.
- Không có ID bị truncate hoặc normalize ngoài ý muốn.

Có thể chạy kiểm tra theo batch với bảng lớn. Kết quả cần được lưu trong migration report để operator có thể đối chiếu.

## 26. Kiểm thử rolling upgrade và mixed-version

Trong môi trường nhiều replica, cần test khi phiên bản cũ và mới cùng chạy.

Một kịch bản:

1. Khởi động broker replica N và N+1 cùng database.
2. Gửi request provision qua replica N.
3. Gửi update hoặc last_operation qua replica N+1.
4. Tạo binding ở N+1 và unbind ở N.
5. Đọc catalog từ cả hai replica.
6. Publish event từ N và xử lý bằng worker N+1.
7. Đảm bảo cùng một public ID được nhìn nhận giống nhau.
8. Hoàn tất rollout và xác minh state.

Nếu hai phiên bản cùng trả catalog khác nhau về ID, platform có thể nhận kết quả phụ thuộc load balancer. Vì vậy, catalog identity cần được kiểm tra trong giai đoạn mixed-version.

Không dùng local cache làm nguồn sự thật duy nhất cho ID mapping. Nếu cache có version hoặc invalidation, phải kiểm tra sau migration và rollout.

## 27. Ví dụ tình huống nâng cấp provider nhưng giữ ID

Giả sử PostgreSQL production được chuyển từ provider A sang Kubernetes operator.

Trước migration:

~~~json
{
  "service_id": "postgres-service",
  "plan_id": "postgres-production",
  "instance_id": "instance-123",
  "provider": "cloud-a",
  "provider_resource_id": "db-7f8a"
}
~~~

Sau migration thành công:

~~~json
{
  "service_id": "postgres-service",
  "plan_id": "postgres-production",
  "instance_id": "instance-123",
  "provider": "kubernetes-postgres",
  "provider_resource_id": "orders-db/uid-98c2"
}
~~~

Public IDs giữ nguyên vì platform vẫn quản lý cùng một logical service instance và plan semantics. Chỉ provider mapping thay đổi.

Nếu migration thay đổi loại database, SLA, backup hoặc khả năng binding theo cách không tương thích, broker cần đánh giá plan ID hoặc service ID mới. Không giữ ID bằng mọi giá nếu ngữ nghĩa sản phẩm thực sự đã thay đổi.

## 28. Quan sát và cảnh báo sau nâng cấp

Sau khi triển khai, cần theo dõi các tín hiệu có thể chỉ ra ID mapping bị hỏng:

- Tỷ lệ instance not found tăng đột biến.
- Binding not found tăng sau rollout.
- Provision retry tạo thêm resource provider.
- Deprovision thất bại do không tìm thấy mapping.
- Catalog service/plan ID thay đổi ngoài dự kiến.
- Operation cũ bị stuck hoặc không còn được worker nhận.
- Số binding mồ côi tăng.
- Provider resource không có instance mapping.
- Số request 409 hoặc 404 thay đổi bất thường.
- Lỗi foreign key hoặc unique constraint tăng.

Metric nên gắn nhãn theo loại thao tác, phiên bản broker và provider; tránh dùng public ID hoặc tenant ID làm label có cardinality cao. Log/traces có thể chứa ID để truy vết nhưng cần quyền truy cập và redaction phù hợp.

Nên so sánh baseline trước/sau rollout và đặt ngưỡng cảnh báo cho not-found rate, duplicate conflict, operation lag và reconciliation backlog.

## 29. Quy trình nâng cấp an toàn

Một quy trình thực tế có thể gồm:

1. Chốt danh sách service ID và plan ID đang được platform sử dụng.
2. Xuất danh sách instance ID, binding ID và operation active.
3. Chụp catalog snapshot và dữ liệu mapping.
4. Kiểm tra schema, độ dài, collation và uniqueness.
5. Thiết kế migration expand-and-contract.
6. Bổ sung code mới có thể đọc dữ liệu cũ.
7. Kiểm thử upgrade fixture từ phiên bản trước.
8. Kiểm thử catalog, update, bind, unbind và deprovision với ID cũ.
9. Kiểm thử rolling upgrade và event schema tương thích.
10. Chạy migration trên staging với dữ liệu gần production.
11. Backup và xác minh restore trước production.
12. Triển khai theo từng bước và theo dõi error rate.
13. Đối soát mapping sau rollout.
14. Chỉ contract schema cũ sau khi hết cửa sổ rollback và mọi worker đã nâng cấp.
15. Lưu audit, migration report và phương án forward-fix.

Không nên gộp việc đổi public ID, thay provider, đổi schema và rotate toàn bộ credentials vào một lần deploy nếu không có lý do bắt buộc. Chia thay đổi thành các bước nhỏ giúp xác định nguyên nhân khi một phần migration thất bại.

## 30. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Instance cũ trả 404 sau deploy | Code mới tìm theo provider ID hoặc ID format mới | Giữ public ID mapping và compatibility lookup |
| Catalog xuất hiện service mới ngoài ý muốn | Đổi service ID khi chỉ muốn đổi tên | Giữ ID, thay metadata |
| Instance không còn plan hợp lệ | Xóa plan đang được sử dụng | Retire plan cho cấp mới nhưng giữ quản lý instance cũ |
| Unbind không tìm thấy binding | Binding ID bị tạo lại khi rotate secret | Giữ binding ID và cập nhật credential version |
| Hai instance trỏ cùng provider resource | Backfill mapping không kiểm tra uniqueness | Unique constraint và reconciliation |
| Rolling deploy có lúc 404 | Replica cũ/mới normalize ID khác nhau | Dùng quy tắc ID thống nhất và mixed-version test |
| Worker không xử lý operation cũ | Event schema hoặc operation mapping không tương thích | Versioned event và backward-compatible consumer |
| Rollback không đọc được database | Contract migration quá sớm | Expand-and-contract và rollback window |
| Deprovision xóa nhầm resource | Tái sử dụng ID hoặc stale provider mapping | Tombstone, generation và version check |
| Secret bị mất khi chuyển storage | Mapping binding tới secret reference không được backfill | Verify secret reference trước khi switch |
| Plan ID giữ nguyên nhưng tài nguyên đổi semantics | Thay đổi plan âm thầm | Plan ID mới hoặc migration có kiểm soát |

## 31. Checklist tương thích trước khi phát hành

**Public identity**

- [ ] Service ID hiện hữu vẫn được nhận diện.
- [ ] Plan ID hiện hữu giữ đúng semantics hoặc có migration rõ.
- [ ] Instance ID được lưu nguyên vẹn và duy nhất trong đúng scope.
- [ ] Binding ID giữ nguyên qua rotation và provider change.
- [ ] Public ID không bị lowercase, trim, truncate hoặc parse tùy tiện.
- [ ] Provider resource ID tách biệt khỏi OSB instance ID.
- [ ] ID đã deprovision không bị tái sử dụng ngoài chính sách.

**Catalog và plan**

- [ ] Catalog snapshot xác nhận service/plan ID cần duy trì.
- [ ] Plan retired vẫn được dùng để quản lý instance cũ.
- [ ] Plan mới dùng ID riêng.
- [ ] Thay đổi display name không làm đổi ID.
- [ ] Thay đổi semantics plan được đánh giá và công bố phù hợp.

**Database và migration**

- [ ] Có backup và restore test.
- [ ] Migration theo expand-and-contract.
- [ ] Backfill không thay public ID.
- [ ] Unique constraint và foreign key được xác minh.
- [ ] Binding, operation và provider mapping vẫn liên kết đúng.
- [ ] Không có ID bị truncate hoặc collision do collation.
- [ ] Rollback window được duy trì trước khi contract schema cũ.

**Runtime compatibility**

- [ ] Operation cũ được worker mới đọc và phục hồi.
- [ ] Message/event schema tương thích trong rolling upgrade.
- [ ] Mixed-version test đã chạy.
- [ ] last_operation hoạt động với operation cũ.
- [ ] Bind/unbind/deprovision dùng được ID đã tạo trước upgrade.
- [ ] Provider migration giữ public identity khi semantics không đổi.
- [ ] Có metric/cảnh báo cho not-found, duplicate và mapping drift.

Bảo toàn service_id, plan_id, instance_id và binding_id là điều kiện để platform tiếp tục quản lý tài nguyên đã tạo sau mỗi lần nâng cấp broker. Hãy coi public ID là opaque contract, tách chúng khỏi khóa nội bộ và provider resource ID, giữ catalog/plan tương thích, migrate schema theo expand-and-contract và kiểm thử bằng dữ liệu thật của phiên bản trước. Khi mapping, operation, binding và secret reference đều được bảo toàn, broker có thể thay đổi implementation hoặc provider mà không làm mất danh tính dịch vụ mà platform đang quản lý.


# Khai báo id, name, description và tính ổn định của định danh

Trong Open Service Broker API (OSB API), catalog là hợp đồng để một platform khám phá các dịch vụ mà broker cung cấp. Mỗi service và mỗi plan trong catalog có ba trường cơ bản cần được thiết kế cẩn thận: `id` xác định đối tượng trong các request vòng đời, `name` là tên dễ đọc để người dùng nhận biết, còn `description` giải thích dịch vụ hoặc plan đó cung cấp điều gì.

Với module `SPRING_CLOUD_SERVICE_BROKER`, catalog có thể công bố các dịch vụ như PostgreSQL, Redis hoặc message queue cùng những plan như `small`, `standard` và `high-availability`. Platform đọc catalog qua `GET /v2/catalog`, sau đó gửi `service_id` và `plan_id` trong các thao tác provision, update và deprovision. Vì thế, định danh được công bố hôm nay sẽ tiếp tục được sử dụng trong suốt vòng đời của instance, kể cả khi tên hiển thị hoặc mô tả được cải thiện ở lần phát hành sau.

## 1. Catalog mô tả service và plan

Một service đại diện cho một loại dịch vụ mà broker có thể quản lý. Ví dụ, `managed-postgresql` là dịch vụ cơ sở dữ liệu PostgreSQL. Một plan là một lựa chọn cấu hình hoặc mức cung cấp thuộc service đó, ví dụ dung lượng nhỏ, cấu hình tiêu chuẩn hoặc cấu hình sẵn sàng cao.

Một phần phản hồi catalog có thể trông như sau:

```json
{
  "services": [
    {
      "id": "8f3d2d6a-2f15-4f57-9d71-6d12e90c1001",
      "name": "managed-postgresql",
      "description": "Cơ sở dữ liệu PostgreSQL được quản lý cho ứng dụng",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "c7c4b4c1-0f1a-4c5d-8e6b-4a91c5f20001",
          "name": "small",
          "description": "Một database với giới hạn CPU, RAM và dung lượng cơ bản",
          "free": false
        },
        {
          "id": "c7c4b4c1-0f1a-4c5d-8e6b-4a91c5f20002",
          "name": "high-availability",
          "description": "Database có replica và cơ chế chuyển đổi dự phòng",
          "free": false
        }
      ]
    }
  ]
}
```

Các UUID trong ví dụ là định danh minh họa. Trong hệ thống thật, broker phải cấp định danh ổn định cho từng service và plan, lưu chúng trong mã nguồn hoặc kho cấu hình có quản lý phiên bản, và giữ nguyên chúng qua các lần triển khai. Không tạo UUID mới mỗi lần ứng dụng khởi động.

Catalog còn có thể chứa các trường như `tags`, `metadata`, `requires`, `schemas`, `dashboard_client` hoặc thông tin bảo trì tùy phiên bản OSB API và khả năng broker. Những trường mở rộng này bổ sung mô tả hoặc tính năng; chúng không thay thế vai trò của `id`, `name` và `description`.

## 2. Trường id: định danh máy đọc và tham chiếu vòng đời

`id` là khóa định danh mà platform dùng để tham chiếu service hoặc plan. Đây là trường quan trọng nhất về tính ổn định vì platform gửi các giá trị đó trở lại broker khi thực hiện thao tác vòng đời.

- `service.id` xác định service trong catalog của broker. Giá trị phải duy nhất trong phạm vi catalog và không thay đổi khi đổi tên hiển thị hoặc mô tả.
- `plan.id` xác định plan thuộc một service. Giá trị phải duy nhất trong phạm vi các plan của service đó và không thay đổi khi điều chỉnh câu chữ, giá hiển thị hoặc metadata.
- ID phải được coi là opaque identifier: platform lưu và gửi lại đúng giá trị, không nên phân tích cấu trúc nội bộ của ID để suy ra loại tài nguyên hay tên plan.
- Dùng UUID hoặc một mã định danh ổn định khác được quản lý tập trung. Tránh dùng số thứ tự theo vị trí trong danh sách, timestamp, giá trị ngẫu nhiên khi khởi động hoặc chuỗi có thể tự thay đổi khi refactor.

Ví dụ, khi platform provision một PostgreSQL instance, request có thể chứa:

```http
PUT /v2/service_instances/instance-123?accepts_incomplete=true HTTP/1.1
X-Broker-API-Version: 2.14
Content-Type: application/json

{
  "service_id": "8f3d2d6a-2f15-4f57-9d71-6d12e90c1001",
  "plan_id": "c7c4b4c1-0f1a-4c5d-8e6b-4a91c5f20001",
  "organization_guid": "org-001",
  "space_guid": "space-001"
}
```

Broker tra cứu hai ID để xác định đúng định nghĩa service và plan, rồi chọn cấu hình provisioner tương ứng. Broker cũng cần lưu lại các ID này cùng service instance. Khi platform gọi update hoặc deprovision nhiều ngày hay nhiều tháng sau, broker vẫn phải hiểu được các ID đã dùng lúc instance được tạo.

### Vì sao không dùng name làm id?

Tên thường phục vụ giao diện và có thể cần chỉnh sửa để rõ nghĩa hơn. Nếu `id` được tạo trực tiếp từ `name`, đổi tên `managed-postgres` thành `managed-postgresql` có thể làm platform gửi một ID mới trong khi các instance cũ vẫn lưu ID cũ. Hậu quả là broker không tìm được định nghĩa cần thiết để update hoặc xóa tài nguyên đã tồn tại.

Hãy tách hai mục đích: `id` là định danh ổn định cho máy và `name` là tên dễ đọc cho con người. Hai giá trị có thể liên quan về mặt quy ước, nhưng không nên phụ thuộc vào nhau về mặt vòng đời.

## 3. Trường name: tên hiển thị có quy tắc duy nhất

`name` là tên ngắn, dễ đọc để platform hiển thị trong marketplace, CLI hoặc giao diện quản trị. Nó giúp người dùng chọn đúng dịch vụ và plan, vì vậy cần rõ nghĩa, nhất quán và không gây nhầm lẫn.

Đối với service, chọn tên mô tả loại dịch vụ, ví dụ:

- `managed-postgresql`
- `managed-redis`
- `object-storage`

Đối với plan, chọn tên diễn tả cấp dịch vụ hoặc cấu hình, ví dụ:

- `small`
- `standard`
- `high-availability`

Tên service cần duy nhất trong catalog; tên plan cần phân biệt được trong phạm vi service chứa nó. Không đặt hai service cùng tên chỉ vì chúng được triển khai trên hai nhà cung cấp hạ tầng khác nhau. Nếu cần phân biệt nhà cung cấp hoặc biến thể sản phẩm, hãy đưa thông tin đó vào tên hiển thị theo một quy ước nhất quán.

Tên không nên chứa thông tin bí mật, hostname nội bộ, credential, tenant ID hoặc dữ liệu thay đổi theo từng instance. `name` của service/plan mô tả sản phẩm trong catalog, không phải tên database được tạo cho một khách hàng cụ thể.

Khi cần đổi tên, hãy xem đó là thay đổi giao diện catalog cần phối hợp với platform, tài liệu và người dùng. Nếu hợp đồng hoặc platform yêu cầu tên duy nhất và ổn định trong catalog, phải kiểm tra ràng buộc đó trước khi phát hành. Dù tên hiển thị có thay đổi theo chính sách tương thích, `id` vẫn phải giữ nguyên để các instance hiện hữu tiếp tục được nhận diện.

## 4. Trường description: mô tả đúng khả năng và giới hạn

`description` là văn bản giải thích ý nghĩa của service hoặc plan. Nó thường được hiển thị trên marketplace để người dùng hiểu mình đang chọn gì. Một mô tả tốt nên trả lời được:

- Dịch vụ cung cấp loại tài nguyên nào?
- Plan này phù hợp với nhu cầu hoặc tải công việc nào?
- Có giới hạn hoặc đặc tính quan trọng nào người dùng cần biết trước khi tạo instance?
- Những khả năng nào được hỗ trợ, chẳng hạn backup, replica, dung lượng hoặc mức sẵn sàng?

Ví dụ mô tả chưa tốt: `Database tốt, nhanh và ổn định.` Câu này không cho biết loại database, phạm vi plan hoặc giới hạn.

Ví dụ rõ hơn: `Một PostgreSQL instance dùng cho môi trường phát triển và ứng dụng có tải nhỏ; dung lượng mặc định 20 GB, không có replica dự phòng.` Mô tả này giúp người dùng hiểu được đối tượng và đặc điểm chính của plan.

Mô tả cần phản ánh năng lực mà broker thực sự thực hiện. Nếu plan `high-availability` chưa có replica hoặc cơ chế failover, không nên mô tả rằng plan đã bảo đảm sẵn sàng cao. Tránh cam kết SLA, thời gian phục hồi hoặc tính năng bảo mật nếu backend và quy trình vận hành chưa đáp ứng.

`description` có thể được cải thiện theo thời gian mà không làm thay đổi định danh của service hoặc plan. Tuy nhiên, khi sửa nội dung, cần giữ cho mô tả khớp với cấu hình provisioner và hành vi thật của các instance mới được tạo.

## 5. Phân biệt id, name và description

| Trường | Mục đích | Đặc tính cần giữ | Ví dụ |
|---|---|---|---|
| `id` | Tham chiếu máy đọc trong request OSB API và dữ liệu vòng đời | Duy nhất trong phạm vi quy định, ổn định, không tái sử dụng cho đối tượng khác | `8f3d2d6a-...1001` |
| `name` | Tên nhận biết trong giao diện và tài liệu | Dễ đọc, có quy tắc duy nhất, thay đổi cần phối hợp | `managed-postgresql` |
| `description` | Giải thích khả năng và giới hạn | Chính xác, hữu ích, được cập nhật khi sản phẩm thay đổi | `PostgreSQL được quản lý cho ứng dụng...` |

Một cách ghi nhớ hữu ích là: platform dựa vào `id` để tìm đúng đối tượng, người dùng dựa vào `name` để nhận biết đối tượng, còn `description` giúp người dùng hiểu đối tượng đó cung cấp điều gì.

## 6. Định danh plan cũng phải ổn định

Plan không chỉ là nhãn `small` hay `large`. Nó thường ánh xạ tới một tập cấu hình thực tế như CPU, RAM, dung lượng, số replica, chính sách backup, giới hạn kết nối, vùng triển khai hoặc mức tính phí. Vì vậy, `plan.id` là khóa để broker xác định đúng chính sách provision và diễn giải các instance đã được tạo trước đó.

Ví dụ hai plan có thể có tên và ID riêng:

```json
{
  "id": "c7c4b4c1-0f1a-4c5d-8e6b-4a91c5f20001",
  "name": "small",
  "description": "20 GB storage, cấu hình tài nguyên cơ bản",
  "free": false
}
```

```json
{
  "id": "c7c4b4c1-0f1a-4c5d-8e6b-4a91c5f20002",
  "name": "high-availability",
  "description": "Database có replica và chuyển đổi dự phòng",
  "free": false
}
```

Broker nên có bảng ánh xạ rõ ràng từ `plan.id` sang cấu hình provisioner. Không suy luận cấu hình chỉ bằng cách so sánh một phần chuỗi tên, ví dụ `if (planName.contains("ha"))`. Cách ánh xạ tường minh giúp thay đổi tên hiển thị mà không vô tình thay đổi tài nguyên được tạo.

Nếu plan cho phép cập nhật, trường `plan_updateable` ở service cho platform biết khả năng đổi plan. Dù có hỗ trợ update, broker vẫn phải kiểm tra chuyển đổi cụ thể có hợp lệ hay không: chuyển từ `small` sang `high-availability` có thể cần tạo replica và đồng bộ dữ liệu; chuyển ngược lại có thể không an toàn hoặc không được hỗ trợ. `plan.id` cũ và mới cần được lưu để operation update có thể xử lý đúng.

## 7. Quản lý ID ổn định trong mã nguồn Spring Cloud

Trong ứng dụng Spring Cloud Service Broker, catalog thường được cung cấp thông qua thành phần catalog của Spring Cloud Open Service Broker. Dù dùng cách khai báo bean, cấu hình hay adapter riêng theo phiên bản thư viện, nguyên tắc vẫn giống nhau: tập ID là dữ liệu hợp đồng, phải được quản lý tập trung và không phát sinh ngẫu nhiên khi request tới.

Có thể gom ID vào một lớp hằng số của ứng dụng:

```java
package com.example.broker.catalog;

public final class CatalogIds {
    private CatalogIds() {}

    public static final String POSTGRES_SERVICE =
            "8f3d2d6a-2f15-4f57-9d71-6d12e90c1001";

    public static final String POSTGRES_SMALL_PLAN =
            "c7c4b4c1-0f1a-4c5d-8e6b-4a91c5f20001";

    public static final String POSTGRES_HA_PLAN =
            "c7c4b4c1-0f1a-4c5d-8e6b-4a91c5f20002";
}
```

Các hằng số này được dùng khi xây dựng catalog và khi ánh xạ request tới nghiệp vụ:

```java
switch (request.getPlanId()) {
    case CatalogIds.POSTGRES_SMALL_PLAN -> provisionSmallDatabase(request);
    case CatalogIds.POSTGRES_HA_PLAN -> provisionHighlyAvailableDatabase(request);
    default -> throw new UnsupportedPlanException(request.getPlanId());
}
```

Đoạn switch là minh họa cho việc ánh xạ ID sang nghiệp vụ; kiểu request, cách xử lý reactive và loại exception cụ thể cần theo phiên bản Spring Cloud Open Service Broker mà dự án sử dụng. Điểm quan trọng là so sánh bằng ID đã công bố, không dùng `name` hoặc vị trí phần tử trong danh sách.

Nếu catalog được nạp từ cấu hình ngoài, hãy kiểm tra tính duy nhất của ID và name lúc khởi động. Với catalog tĩnh, có thể kiểm tra trong unit test hoặc test của `CatalogService`. Không để một thay đổi cấu hình vô tình gán cùng một ID cho hai plan khác nhau.

## 8. ID phải tồn tại xuyên suốt vòng đời instance

Platform không chỉ đọc ID ở bước catalog. Nó gửi ID đó trở lại broker ở nhiều thời điểm:

```text
GET /v2/catalog
    -> platform nhận service.id và plan.id

PUT /v2/service_instances/{instance_id}
    -> request.service_id, request.plan_id

PATCH /v2/service_instances/{instance_id}
    -> request.service_id, request.plan_id và plan mới (nếu có)

GET /v2/service_instances/{instance_id}/last_operation
    -> broker tra trạng thái theo instance và operation đã lưu

DELETE /v2/service_instances/{instance_id}
    -> query chứa service_id và plan_id của instance cần thu hồi
```

Ví dụ một instance được provision khi plan có ID `...0001`. Vài tháng sau, broker phát hành phiên bản mới và plan `small` được đổi tên thành `starter`. Platform vẫn có thể gửi ID `...0001` khi deprovision instance cũ. Nếu broker đã thay ID thành `...0003` và xóa ánh xạ cũ, nó có thể không xác định được cách thu hồi database đã tạo trước đó.

Vì vậy, bản ghi service instance nên lưu ít nhất:

- `service_instance_id` do platform cấp;
- `service_id` và `plan_id` tại thời điểm provision;
- trạng thái vòng đời và mã operation gần nhất;
- external resource ID do provider trả về;
- cấu hình hoặc phiên bản cấu hình đã dùng khi tạo tài nguyên;
- thời điểm tạo và cập nhật.

Khi update plan thành công, broker lưu plan đích theo quy tắc nghiệp vụ và giữ đủ thông tin cần thiết để rollback, reconcile hoặc deprovision. Khi xử lý deprovision, phải dựa vào bản ghi instance và định danh tài nguyên ngoài đã lưu, không chỉ dựa vào catalog hiện tại.

## 9. Chiến lược thay đổi catalog mà không phá vỡ instance cũ

Catalog là hợp đồng được platform đọc và có thể cache. Mọi thay đổi ID cần được xem là thay đổi tương thích nghiêm trọng.

| Thay đổi | Ảnh hưởng | Hướng xử lý |
|---|---|---|
| Sửa `description` | Chủ yếu ảnh hưởng nội dung hiển thị | Có thể cập nhật khi mô tả vẫn đúng với hành vi thực tế. |
| Sửa `name` | Ảnh hưởng giao diện, script hoặc tài liệu tham chiếu theo tên | Phối hợp migration và giữ nguyên ID. |
| Đổi `service.id` | Platform không còn nhận diện service cũ theo ID đã lưu | Không đổi ID của service đã công bố; nếu là sản phẩm khác, tạo service mới có ID mới. |
| Đổi `plan.id` | Instance hiện hữu vẫn tham chiếu plan cũ | Giữ ID cũ để quản lý instance; thêm plan mới với ID mới khi cần thay đổi sản phẩm. |
| Xóa plan khỏi catalog | Người dùng có thể không tạo instance mới bằng plan đó | Có kế hoạch ngừng cung cấp; vẫn duy trì khả năng quản lý instance cũ. |
| Xóa service khỏi catalog | Platform không còn thấy dịch vụ cho lựa chọn mới | Chỉ thực hiện sau khi xử lý các instance hiện hữu và bảo đảm broker vẫn xử lý được thao tác vòng đời cần thiết. |

Một quy trình ngừng cung cấp plan nên có các bước: đánh dấu plan không còn được khuyến nghị trong tài liệu hoặc metadata, dừng tạo instance mới theo chính sách platform, thông báo thời hạn chuyển đổi, hỗ trợ migrate các instance còn hoạt động, sau đó mới cân nhắc loại bỏ khỏi danh mục. Không tái sử dụng ID cũ cho một plan có ý nghĩa khác.

Nếu một sản phẩm mới có semantics khác đáng kể, hãy tạo service hoặc plan mới với ID mới. Ví dụ, `postgres-small` dùng một node đơn và `postgres-small-ha` có replica là hai cấu hình có hành vi vận hành khác nhau; việc thay đổi nội dung plan cũ để âm thầm thêm replica có thể làm thay đổi kỳ vọng, chi phí và đặc tính tài nguyên của khách hàng hiện hữu.

## 10. Kiểm tra catalog trước khi công bố

Trước khi đưa catalog vào môi trường dùng chung, broker cần xác minh:

1. Mọi service có `id`, `name`, `description` hợp lệ và không trùng định danh trong catalog.
2. Mỗi plan có `id`, `name`, `description` và ID không trùng với plan khác trong cùng service.
3. ID được khai báo tĩnh hoặc quản lý bằng nguồn dữ liệu bền vững, không đổi giữa các lần khởi động.
4. Name đủ rõ nghĩa, đúng quy ước và không gây nhầm lẫn giữa các service/plan.
5. Description phản ánh đúng tính năng, giới hạn và điều kiện của provisioner.
6. Mỗi `plan.id` được ánh xạ tới đúng cấu hình nghiệp vụ; request với ID không hỗ trợ được xử lý như lỗi hợp đồng phù hợp.
7. Các ID cũ vẫn được nhận diện để update, last operation và deprovision instance đã tạo trước đó.
8. Catalog trả về ổn định giữa các lần gọi nếu không có thay đổi cấu hình được phát hành.

Một kiểm thử đơn giản có thể xác minh tập ID và name không bị trùng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

class CatalogIdentityTest {
    record Entry(String id, String name) {}

    @org.junit.jupiter.api.Test
    void serviceIdsAndNamesMustBeUnique() {
        List<Entry> services = List.of(
                new Entry(CatalogIds.POSTGRES_SERVICE, "managed-postgresql"),
                new Entry("3f6c0a5e-9c52-4c20-a01f-6d12e90c2001", "managed-redis")
        );

        Set<String> ids = new HashSet<>();
        Set<String> names = new HashSet<>();
        for (Entry service : services) {
            assertTrue(ids.add(service.id()), "Duplicate service id: " + service.id());
            assertTrue(names.add(service.name()), "Duplicate service name: " + service.name());
        }
        assertEquals(services.size(), ids.size());
    }
}
```

Đây là ví dụ kiểm tra mô hình đơn giản; trong dự án thực tế nên lấy danh sách service và plan từ chính đối tượng catalog mà broker trả về để kiểm tra hợp đồng thực tế, đồng thời kiểm tra uniqueness của plan trong từng service.

## 11. Những lỗi thiết kế thường gặp

- **Sinh ID ngẫu nhiên khi khởi động:** catalog thay đổi sau mỗi lần restart, platform có thể không nhận diện được service/plan đã dùng trước đó. Hãy dùng ID ổn định.
- **Dùng name làm khóa database:** đổi tên hiển thị khiến truy vấn instance hoặc ánh xạ provisioner bị đứt. Hãy lưu ID và name riêng.
- **Dùng vị trí trong danh sách làm định danh:** sắp xếp lại catalog làm ID thay đổi. Mỗi đối tượng cần ID riêng.
- **Tái sử dụng ID đã ngừng:** platform hoặc bản ghi cũ có thể tham chiếu ID đó nhưng giờ nó mang nghĩa khác. Không tái sử dụng ID.
- **Mô tả vượt quá năng lực thật:** người dùng chọn plan dựa trên cam kết sai. Mô tả phải được đối chiếu với cấu hình và SLA thực tế.
- **Xóa plan ngay khi không muốn bán nữa:** instance cũ có thể vẫn cần update hoặc deprovision. Cần kế hoạch tương thích cho vòng đời cũ.
- **Chỉ kiểm tra catalog bằng mắt:** ID trùng hoặc thay đổi vô tình có thể lọt qua. Hãy tự động hóa kiểm tra uniqueness và tính ổn định trong test.

## 12. Ví dụ thay đổi catalog an toàn

Giả sử phiên bản đầu của broker công bố service `managed-postgresql` với plan `small`. Sau một thời gian, nhóm phát triển muốn đổi tên plan thành `starter` và bổ sung plan `standard`.

| Phiên bản | Service ID | Plan ID | Plan name | Ý nghĩa |
|---|---|---|---|---|
| v1 | `...1001` | `...0001` | `small` | 20 GB, cấu hình cơ bản |
| v2 | `...1001` | `...0001` | `starter` | Vẫn là cấu hình cũ, tên hiển thị được cập nhật theo kế hoạch tương thích |
| v2 | `...1001` | `...0003` | `standard` | Plan mới, cấu hình tài nguyên cao hơn |

Service ID và plan ID của cấu hình cũ vẫn được giữ nguyên. Plan mới có ID mới. Nếu chính sách platform hoặc quy trình vận hành không cho phép đổi tên plan đã công bố, có thể tiếp tục giữ tên `small` và chỉ thêm plan `standard`; điều cần tránh trong mọi trường hợp là thay ID của plan cũ hoặc dùng ID cũ cho cấu hình khác.

Khi nhận request cho instance được tạo từ v1, broker vẫn tìm được service và plan theo ID cũ, rồi sử dụng metadata instance để thực hiện update hoặc deprovision. Request tạo instance mới có thể chọn plan `standard` theo catalog v2. Đây là lý do ID phải được quản lý như một phần của hợp đồng dài hạn.

## 13. Nguyên tắc cần ghi nhớ

Catalog tốt giúp platform và broker hiểu cùng một tập định danh trong suốt vòng đời dịch vụ. Hãy cấp ID duy nhất và ổn định cho service/plan, dùng name dễ đọc để hiển thị, dùng description chính xác để mô tả khả năng và giới hạn. Quản lý các ID như dữ liệu hợp đồng có phiên bản, kiểm tra uniqueness tự động, giữ ánh xạ cho instance hiện hữu và chỉ ngừng cung cấp plan theo một quy trình có kiểm soát.

Khi áp dụng các nguyên tắc này trong Spring Cloud Service Broker, platform có thể cache catalog và gửi lại các ID trong provision, update, binding hoặc deprovision mà broker vẫn xác định đúng nghiệp vụ. Nhờ đó, việc cải thiện tên và mô tả không làm đứt liên kết với tài nguyên đã cấp phát, còn thay đổi sản phẩm mới có thể được công bố bằng ID mới với phạm vi tương thích rõ ràng.

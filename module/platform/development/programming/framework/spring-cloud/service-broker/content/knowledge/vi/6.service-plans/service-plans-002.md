# Định danh, mô tả, thuộc tính free và metadata của gói

Trong Open Service Broker API (OSB API), một **service plan** mô tả một lựa chọn cụ thể mà broker cung cấp cho một service. Ví dụ, service `managed-postgresql` có thể cung cấp các plan `small`, `standard` và `high-availability`. Mỗi plan cần một định danh ổn định, tên dễ nhận biết, mô tả chính xác và những thông tin bổ sung để platform trình bày lựa chọn cho người dùng.

Với module `SPRING_CLOUD_SERVICE_BROKER`, plan còn là đầu vào để broker quyết định cấu hình tài nguyên khi provision hoặc update. Vì platform gửi `plan_id` trở lại broker trong các thao tác vòng đời, định danh và ý nghĩa của plan phải được quản lý nhất quán từ catalog đến provisioner. Thuộc tính `free` và `metadata` giúp mô tả chính sách giá và thông tin hiển thị; chúng không thay thế logic cấp phát, kiểm tra quyền hay quản lý trạng thái của broker.

## 1. Plan nằm ở đâu trong catalog?

Catalog của broker chứa một danh sách service. Mỗi service có thể chứa nhiều plan. Service mô tả loại sản phẩm, còn plan mô tả một cấu hình hoặc cấp dịch vụ thuộc sản phẩm đó.

Ví dụ, service PostgreSQL có thể có ba plan:

| Plan | Đặc điểm tài nguyên | Trường hợp sử dụng |
|---|---|---|
| `small` | Một node, dung lượng và giới hạn kết nối cơ bản | Phát triển, thử nghiệm hoặc tải nhỏ |
| `standard` | Nhiều CPU/RAM hơn, backup định kỳ | Ứng dụng vận hành thường xuyên |
| `high-availability` | Có replica và cơ chế chuyển đổi dự phòng | Ứng dụng yêu cầu độ sẵn sàng cao |

Khi platform gọi `GET /v2/catalog`, broker trả về các service và plan mà platform có thể khám phá. Người dùng chọn một plan, sau đó platform gửi `plan_id` trong request provision. Broker dùng ID đó để tìm đúng định nghĩa và cấu hình provisioner.

Một phần catalog minh họa:

```json
{
  "services": [
    {
      "id": "postgres-service-id",
      "name": "managed-postgresql",
      "description": "Dịch vụ PostgreSQL được quản lý",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "postgres-small-v1",
          "name": "small",
          "description": "PostgreSQL cho tải nhỏ, dung lượng 20 GB",
          "free": false,
          "metadata": {
            "displayName": "PostgreSQL Small",
            "longDescription": "Một database dùng cho ứng dụng có tải nhỏ.",
            "documentationUrl": "https://docs.example.com/postgresql/small",
            "supportUrl": "https://support.example.com"
          }
        }
      ]
    }
  ]
}
```

Các ID và URL trên chỉ là ví dụ. Trong catalog thực tế, ID phải được quản lý ổn định và URL metadata phải trỏ tới tài liệu hoặc trang hỗ trợ thật của nhà cung cấp.

## 2. Định danh plan bằng id

Trường `id` là định danh máy đọc của plan. Platform lưu giá trị này và gửi lại cho broker khi thực hiện provision, update hoặc deprovision. Vì vậy, `id` là một phần của hợp đồng lâu dài giữa broker và platform.

Một ID plan tốt cần đáp ứng các nguyên tắc:

- **Ổn định:** không thay đổi khi broker restart, triển khai phiên bản mới hoặc sắp xếp lại danh sách plan.
- **Duy nhất trong service:** hai plan khác nhau của cùng một service không được dùng chung ID.
- **Không tái sử dụng:** khi ngừng cung cấp một plan, không gán ID cũ cho một cấu hình khác.
- **Opaque:** platform nên lưu và gửi lại ID như một giá trị định danh, không phụ thuộc vào cấu trúc nội bộ của chuỗi.
- **Được quản lý tập trung:** khai báo bằng hằng số, cấu hình có phiên bản hoặc kho dữ liệu có kiểm soát; không sinh ID ngẫu nhiên trong mỗi lần tạo catalog.

Ví dụ, nếu plan `small` có ID `postgres-small-v1`, một instance đã được tạo với ID đó vẫn có thể cần update hoặc deprovision nhiều tháng sau. Nếu broker đổi ID thành `postgres-starter-v2` và xóa định nghĩa cũ, broker có thể không còn nhận diện được plan của instance hiện hữu.

Không dùng vị trí phần tử trong mảng làm ID. Nếu plan đầu tiên hôm nay có index `0` và ngày mai nhóm phát triển chèn thêm một plan ở đầu danh sách, index của các plan cũ sẽ thay đổi. Cũng không nên dùng `name` làm khóa định danh vì tên hiển thị có thể cần điều chỉnh.

## 3. Trường name: tên dễ nhận biết

`name` là tên ngắn mà platform có thể hiển thị trong marketplace hoặc CLI. Tên cần dễ đọc, có quy tắc nhất quán và phân biệt được các lựa chọn trong cùng service.

Ví dụ:

- `small`: plan cơ bản, giới hạn tài nguyên thấp.
- `standard`: plan dùng cho tải sản xuất thông thường.
- `high-availability`: plan có replica hoặc cơ chế dự phòng.

Tránh tên mơ hồ như `plan1`, `new`, `best` hoặc tên gắn với thứ tự phát hành như `version-3` nếu nó không thể hiện ý nghĩa mà người dùng cần lựa chọn. Không đưa tenant ID, tên database cụ thể, hostname nội bộ hay credential vào tên plan.

Tên có thể được điều chỉnh theo quy trình tương thích và khả năng của platform, nhưng việc đổi tên không nên làm thay đổi ID hoặc âm thầm thay đổi cấu hình tài nguyên. Nếu một plan mới có semantics khác đáng kể, hãy tạo plan mới với ID mới thay vì sửa tên cũ để đại diện cho một sản phẩm khác.

## 4. Trường description: giải thích đặc điểm và giới hạn

`description` là mô tả ngắn gọn về plan. Người dùng dựa vào đó để hiểu sự khác nhau giữa các lựa chọn. Mô tả tốt cần cụ thể và phản ánh đúng những gì broker thực sự cấp phát.

Một mô tả yếu như `Database nhanh và ổn định` không nói rõ loại tài nguyên, giới hạn hay điều kiện sử dụng. Có thể viết rõ hơn:

> Một PostgreSQL instance dùng cho ứng dụng tải nhỏ, dung lượng mặc định 20 GB, một node và không có replica dự phòng.

Với plan `high-availability`, mô tả nên nói rõ cơ chế dự phòng đã được triển khai, ví dụ có replica đồng bộ hay bất đồng bộ, cơ chế failover do nhà cung cấp quản lý, hoặc giới hạn vùng triển khai. Chỉ nêu những đặc điểm có thật. Không hứa SLA, RPO, RTO, backup hoặc khả năng mở rộng nếu backend và quy trình vận hành chưa đáp ứng.

Mô tả cần phân biệt được plan này với các plan khác. Nếu `small` và `standard` chỉ khác nhau về giới hạn CPU/RAM, có thể nói rõ mức giới hạn hoặc cách quy đổi mà người dùng có thể hiểu. Nếu thông số thay đổi theo vùng hoặc theo nhà cung cấp, hãy mô tả ở mức chính xác phù hợp và dẫn tới tài liệu chi tiết qua metadata.

## 5. Thuộc tính free: plan có miễn phí hay không

Trường `free` là một giá trị boolean trong định nghĩa plan. Nó cho biết plan có miễn phí hay không theo chính sách mà broker công bố cho platform.

```json
{
  "id": "redis-dev-plan",
  "name": "development",
  "description": "Redis cho môi trường phát triển",
  "free": true
}
```

```json
{
  "id": "redis-standard-plan",
  "name": "standard",
  "description": "Redis được quản lý cho ứng dụng vận hành",
  "free": false
}
```

Ý nghĩa cần được hiểu đúng:

- `true` biểu thị plan miễn phí theo chính sách giá được công bố.
- `false` biểu thị plan không được công bố là miễn phí.
- Đây là thông tin trong catalog để platform có thể trình bày lựa chọn; bản thân trường này không thực hiện thu tiền, không tạo hóa đơn và không thay thế hệ thống billing.
- `free` không phải cờ cấp quyền. Không dùng nó để quyết định người gọi có được provision hay bind hay không.
- Không suy ra rằng một plan miễn phí sẽ không tiêu thụ tài nguyên hoặc không có giới hạn. Broker vẫn cần quota, giới hạn sử dụng và chính sách chống lạm dụng.

Nếu broker có tích hợp billing, cần bảo đảm thông tin `free`, giá và quy tắc tính phí nhất quán với hợp đồng thương mại. OSB API có thể biểu diễn thông tin chi phí bằng trường `costs` riêng; `costs` và `free` không nên mâu thuẫn. Platform có thể xử lý hoặc hiển thị chúng theo cách riêng, vì vậy broker cần kiểm tra khả năng hỗ trợ của platform mục tiêu.

Không dùng `free: true` để biểu diễn trial có thời hạn nếu sau thời gian thử nghiệm người dùng sẽ bị tính phí mà không có cơ chế chuyển đổi được công bố rõ ràng. Một trial có thời hạn cần có chính sách, thời hạn, cách kết thúc và cách chuyển plan minh bạch. Nếu platform không có mô hình trial tương ứng, hãy mô tả điều kiện trong tài liệu và metadata phù hợp thay vì làm sai ý nghĩa của `free`.

Nếu không khai báo `free`, hãy kiểm tra schema và hành vi theo phiên bản OSB API mà broker hỗ trợ cũng như cách platform tiêu thụ trường này. Để tránh mơ hồ về chính sách thương mại, broker nên công bố giá trị rõ ràng cho những plan mà platform cần hiển thị trạng thái miễn phí.

## 6. Metadata: thông tin bổ sung cho platform và marketplace

Trường `metadata` là một object chứa thông tin bổ sung về plan. Các thuộc tính chuẩn như `id`, `name`, `description` và `free` mang ý nghĩa trong hợp đồng OSB API; metadata mở rộng thông tin hiển thị hoặc tích hợp theo nhu cầu của platform.

Ví dụ:

```json
{
  "id": "postgres-standard-v1",
  "name": "standard",
  "description": "PostgreSQL cho ứng dụng có tải trung bình",
  "free": false,
  "metadata": {
    "displayName": "PostgreSQL Standard",
    "longDescription": "Plan có backup định kỳ và giới hạn tài nguyên cao hơn plan small.",
    "providerDisplayName": "Example Data Services",
    "documentationUrl": "https://docs.example.com/postgresql/standard",
    "supportUrl": "https://support.example.com",
    "features": "Daily backup; managed updates; monitoring"
  }
}
```

Metadata có thể được dùng cho các mục đích như:

- Tên hiển thị dài hoặc mô tả chi tiết hơn `description`.
- Tên nhà cung cấp, biểu tượng hoặc liên kết tới tài liệu và hỗ trợ.
- Thông tin đặc điểm nổi bật để marketplace trình bày cho người dùng.
- Nhãn phân loại hoặc thông tin bổ sung mà một platform cụ thể hiểu được.

Các khóa như `displayName`, `longDescription`, `providerDisplayName`, `documentationUrl`, `supportUrl` thường gặp trong tích hợp marketplace, nhưng cách hiểu và khả năng hiển thị phụ thuộc platform. OSB API không bảo đảm mọi platform đều hiển thị tất cả khóa metadata tùy chỉnh. Broker nên xác định rõ tập khóa được hỗ trợ và kiểm tra với platform mục tiêu.

### Metadata không phải provisioning parameters

Hai khái niệm này có mục đích khác nhau:

| Metadata của plan | Parameters trong request provision |
|---|---|
| Mô tả hoặc bổ sung thông tin cho catalog | Cung cấp giá trị người dùng chọn khi tạo instance |
| Được công bố trong catalog | Được gửi trong request `PUT /v2/service_instances/{instance_id}` |
| Thường phục vụ hiển thị, liên kết và tích hợp platform | Được broker kiểm tra schema và dùng trong nghiệp vụ provision |
| Không nên chứa bí mật hoặc dữ liệu riêng của một instance | Có thể chứa cấu hình instance, nhưng phải validate và áp dụng chính sách bảo mật |

Ví dụ `metadata.features` có thể mô tả rằng plan hỗ trợ backup hàng ngày. Tham số `backup_retention_days` trong request provision mới là giá trị cụ thể mà người dùng yêu cầu cho instance, nếu schema của broker cho phép. Không dùng metadata để truyền mật khẩu, token, connection string hoặc giá trị cần giữ bí mật.

### Metadata phải có cấu trúc và được kiểm soát

- Chỉ công bố các khóa có mục đích rõ ràng và có consumer cụ thể.
- Dùng kiểu dữ liệu nhất quán theo quy ước mà platform tích hợp hỗ trợ.
- Không dùng metadata để nhét toàn bộ cấu hình provisioner hoặc đối tượng nội bộ không cần công bố.
- Không đưa credential, thông tin mạng riêng, tenant ID hoặc dữ liệu vận hành nhạy cảm vào catalog công khai.
- Kiểm tra URL là địa chỉ tài liệu/hỗ trợ hợp lệ và không trỏ tới endpoint nội bộ chỉ dành cho quản trị.
- Giữ metadata ngắn gọn, chính xác và cập nhật cùng với khả năng thật của plan.

## 7. Quan hệ giữa plan metadata và cấu hình tài nguyên

Broker phải ánh xạ mỗi `plan.id` tới cấu hình nghiệp vụ cụ thể. Metadata và description giúp con người hiểu plan, còn provisioner cần một cấu hình có cấu trúc, được kiểm soát trong ứng dụng.

Ví dụ mô hình nội bộ:

```java
package com.example.broker.catalog;

import java.util.Map;

public record PlanDescriptor(
        String id,
        String name,
        String description,
        boolean free,
        Map<String, String> metadata,
        String provisionerProfile
) {}
```

Một registry có thể ánh xạ plan ID tới cấu hình:

```java
import java.util.Map;

public final class PlanRegistry {
    private static final Map<String, PlanDescriptor> PLANS = Map.of(
        "postgres-small-v1",
        new PlanDescriptor(
            "postgres-small-v1",
            "small",
            "PostgreSQL cho tải nhỏ, dung lượng 20 GB",
            false,
            Map.of("displayName", "PostgreSQL Small"),
            "postgres-small"
        ),
        "postgres-standard-v1",
        new PlanDescriptor(
            "postgres-standard-v1",
            "standard",
            "PostgreSQL cho tải trung bình, có backup định kỳ",
            false,
            Map.of("displayName", "PostgreSQL Standard"),
            "postgres-standard"
        )
    );

    public static PlanDescriptor require(String planId) {
        PlanDescriptor plan = PLANS.get(planId);
        if (plan == null) {
            throw new IllegalArgumentException("Unsupported plan id: " + planId);
        }
        return plan;
    }

    private PlanRegistry() {}
}
```

Đây là mô hình domain minh họa, không phải API builder cụ thể của Spring Cloud Open Service Broker. Trong dự án thực tế, adapter catalog chuyển `PlanDescriptor` sang kiểu plan mà phiên bản thư viện đang dùng yêu cầu; service xử lý provision dùng cùng registry hoặc cùng nguồn dữ liệu để ánh xạ `plan_id` tới cấu hình provisioner. Tránh duy trì hai danh sách độc lập cho catalog và provision vì chúng có thể lệch nhau.

Khi platform gửi request provision:

```json
{
  "service_id": "postgres-service-id",
  "plan_id": "postgres-small-v1",
  "organization_guid": "org-001",
  "space_guid": "space-001",
  "parameters": {
    "storage_gb": 20
  }
}
```

Broker tìm plan theo `plan_id`, kiểm tra plan còn được phép tạo instance mới, xác thực tham số `storage_gb` theo schema và quota, sau đó gọi provisioner với profile `postgres-small`. Metadata `displayName` không được dùng làm khóa để chọn cấu hình.

## 8. Plan ID gắn với vòng đời service instance

Khi provision thành công, broker cần lưu `service_id` và `plan_id` cùng bản ghi service instance. Các thao tác về sau phụ thuộc vào dữ liệu này:

1. **Provision:** platform gửi plan ID mà người dùng chọn; broker dùng nó để xác định cấu hình tài nguyên.
2. **Update:** nếu service cho phép đổi plan, broker nhận plan đích và phải kiểm tra chuyển đổi từ plan hiện tại sang plan mới.
3. **Last operation:** broker theo dõi tiến trình update hoặc provision theo instance và operation đã lưu; metadata không thay thế trạng thái operation.
4. **Deprovision:** platform gửi service ID và plan ID gắn với instance; broker cần tiếp tục nhận diện plan cũ để thu hồi đúng tài nguyên.

Ví dụ, `postgres-small-v1` được dùng để tạo một database. Sau đó broker phát hành plan mới `postgres-starter-v2` và ngừng cho phép tạo instance mới theo ID cũ. Những instance đã tạo từ `postgres-small-v1` vẫn cần được unbind, update theo chính sách hoặc deprovision. Vì vậy, ngừng bán một plan không đồng nghĩa xóa ngay định nghĩa và logic cần thiết để quản lý instance cũ.

Nếu thay đổi `free` hoặc metadata, cần đánh giá ảnh hưởng đến người dùng và platform đang cache catalog. Nếu thay đổi ý nghĩa tài nguyên hoặc cách tính phí, cần cân nhắc tạo plan mới với ID mới và quy trình chuyển đổi rõ ràng. Không âm thầm đổi một plan cũ từ miễn phí sang tính phí hoặc từ một cấu hình tài nguyên sang cấu hình khác mà không có chính sách tương thích.

## 9. Chiến lược cập nhật và ngừng cung cấp plan

Plan catalog có thể thay đổi theo thời gian: bổ sung plan, sửa mô tả, điều chỉnh metadata, thay đổi chính sách giá hoặc ngừng cung cấp một lựa chọn. Cần phân biệt thay đổi trình bày với thay đổi semantics:

| Thay đổi | Mức độ ảnh hưởng | Cách xử lý |
|---|---|---|
| Sửa lỗi chính tả trong `description` | Thấp | Cập nhật nội dung, giữ nguyên ID. |
| Bổ sung URL tài liệu trong `metadata` | Thấp nếu URL đúng và không đổi hành vi | Cập nhật metadata và kiểm tra platform tiêu thụ. |
| Đổi `name` | Có thể ảnh hưởng giao diện, script và tài liệu | Phối hợp với platform; giữ nguyên ID. |
| Đổi `free` hoặc thông tin giá | Ảnh hưởng kỳ vọng thương mại | Thông báo và áp dụng chính sách giá có phiên bản; không đổi âm thầm. |
| Thay đổi cấu hình tài nguyên của plan | Có thể ảnh hưởng hiệu năng, chi phí và tương thích | Đánh giá semantics; thường nên tạo plan mới nếu thay đổi đáng kể. |
| Ngừng plan | Ảnh hưởng lựa chọn mới và instance hiện hữu | Dừng tạo mới theo lộ trình nhưng giữ khả năng quản lý instance cũ. |

Một quy trình ngừng cung cấp có thể gồm: công bố thời điểm dừng tạo instance mới, thông báo người dùng, cung cấp plan thay thế, hỗ trợ chuyển đổi nếu có thể, theo dõi instance còn tồn tại và chỉ loại bỏ logic cũ khi không còn nghĩa vụ vòng đời. Chính sách này cần phối hợp với khả năng cache catalog của platform.

## 10. Kiểm tra plan trước khi đưa vào catalog

Trước khi công bố, broker nên xác minh các điều kiện sau:

- `id` không rỗng, ổn định và không trùng với plan khác trong cùng service.
- `name` dễ hiểu và phân biệt được với các plan còn lại.
- `description` nêu đúng loại tài nguyên, tính năng và giới hạn quan trọng.
- `free` phản ánh đúng chính sách thương mại; nếu có `costs`, thông tin chi phí phải nhất quán.
- `metadata` là object hợp lệ, chỉ chứa thông tin được phép công bố và có consumer rõ ràng.
- Các URL trong metadata có thể truy cập bởi đối tượng dự kiến và không để lộ endpoint nội bộ.
- `plan.id` ánh xạ tới cấu hình provisioner có thật; không chỉ tồn tại trên giao diện catalog.
- Instance cũ vẫn được nhận diện khi plan đổi tên, ngừng cung cấp hoặc catalog được cập nhật.
- Thay đổi catalog không làm phát sinh ID ngẫu nhiên hoặc khác nhau giữa các replica của broker.

Ví dụ kiểm tra cơ bản trong Java:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class PlanCatalogValidator {
    public static void validate(List<PlanDescriptor> plans) {
        Set<String> ids = new HashSet<>();
        Set<String> names = new HashSet<>();

        for (PlanDescriptor plan : plans) {
            if (plan.id() == null || plan.id().isBlank()) {
                throw new IllegalStateException("Plan id is required");
            }
            if (!ids.add(plan.id())) {
                throw new IllegalStateException("Duplicate plan id: " + plan.id());
            }
            if (plan.name() == null || plan.name().isBlank()) {
                throw new IllegalStateException("Plan name is required: " + plan.id());
            }
            if (!names.add(plan.name())) {
                throw new IllegalStateException("Duplicate plan name: " + plan.name());
            }
            if (plan.description() == null || plan.description().isBlank()) {
                throw new IllegalStateException("Plan description is required: " + plan.id());
            }
            if (plan.metadata() == null) {
                throw new IllegalStateException("Plan metadata must be initialized: " + plan.id());
            }
        }
    }

    private PlanCatalogValidator() {}
}
```

Đây là ví dụ kiểm tra mô hình nội bộ. Quy tắc bắt buộc chính xác phải theo schema OSB API và phiên bản thư viện đang dùng; nếu metadata được phép vắng mặt, adapter có thể biểu diễn trường đó là optional thay vì ép mọi plan phải có metadata. Điều quan trọng là kiểm tra uniqueness, giá trị bắt buộc và khả năng ánh xạ plan tới nghiệp vụ trước khi trả catalog.

## 11. Lỗi thường gặp khi khai báo plan

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Sinh `id` ngẫu nhiên khi khởi động | Platform cache ID cũ nhưng broker chỉ nhận ID mới | Khai báo ID ổn định và kiểm tra bằng test. |
| Dùng `name` để chọn provisioner | Đổi tên làm sai ánh xạ tài nguyên | Ánh xạ bằng `plan.id`. |
| Mô tả không đúng cấu hình thật | Người dùng chọn plan dựa trên kỳ vọng sai | Đối chiếu description với cấu hình và SLA. |
| Đặt `free: true` chỉ để plan xuất hiện nổi bật | Platform có thể hiểu sai chính sách giá | Chỉ dùng `free` theo ý nghĩa miễn phí thực tế. |
| Coi metadata là parameters | Broker có thể bỏ qua hoặc dùng nhầm thông tin catalog khi provision | Dùng request parameters và schema cho cấu hình instance. |
| Đưa secret vào metadata | Catalog có thể làm lộ credential cho platform hoặc người dùng | Chỉ phát hành thông tin công khai; secret cấp qua binding hoặc kênh bảo mật. |
| Xóa plan ngay khi dừng bán | Không xử lý được instance cũ | Giữ định nghĩa và logic vòng đời trong thời gian chuyển tiếp. |
| Catalog và provisioner dùng hai nguồn dữ liệu khác nhau | Plan được công bố nhưng không cấp phát được | Dùng chung registry hoặc nguồn dữ liệu có kiểm soát. |

## 12. Nguyên tắc cần ghi nhớ

Một plan là cam kết cụ thể giữa broker và người dùng về loại tài nguyên, giới hạn và đặc tính cung cấp. `id` phải duy nhất và ổn định để platform tham chiếu xuyên suốt vòng đời; `name` giúp nhận biết; `description` giải thích đúng tính năng và giới hạn; `free` công bố trạng thái miễn phí; `metadata` bổ sung thông tin mà platform có thể dùng để trình bày hoặc tích hợp.

Trong Spring Cloud Service Broker, hãy quản lý định nghĩa plan tập trung, ánh xạ `plan.id` trực tiếp tới cấu hình provisioner, kiểm tra catalog trước khi công bố và duy trì khả năng xử lý các ID cũ. Khi thay đổi giá, cấu hình hoặc ngừng cung cấp, cần có lộ trình tương thích rõ ràng để platform và instance hiện hữu tiếp tục hoạt động đúng.

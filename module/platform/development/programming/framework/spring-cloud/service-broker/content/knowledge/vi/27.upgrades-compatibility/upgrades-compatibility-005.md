# Tiến hóa catalog, schema tham số và metadata mà không phá instance cũ

Trong module **SPRING_CLOUD_SERVICE_BROKER**, catalog là hợp đồng mà platform dùng để khám phá service offering, plan, capability và cấu trúc parameters. Theo thời gian, broker có thể cần thêm field cấu hình, thay đổi mô tả plan, bổ sung metadata cho marketplace hoặc giới thiệu plan mới. Những thay đổi này ảnh hưởng tới platform đang cache catalog, automation đã tích hợp và service instance đã được provision từ nhiều tháng trước.

Một thay đổi catalog có vẻ nhỏ vẫn có thể làm hỏng lifecycle. Ví dụ, thêm một parameter bắt buộc khiến platform cũ không gửi field đó; đổi ý nghĩa của plan ID khiến instance cũ bị diễn giải bằng cấu hình mới; xóa metadata key làm dashboard tích hợp không hiển thị đúng; hoặc thay schema update khiến request của instance cũ không còn hợp lệ.

Mục tiêu của tiến hóa catalog là mở rộng khả năng broker trong khi giữ được hợp đồng mà client hiện tại đang sử dụng. Cần bảo toàn service ID và plan ID, giữ semantics của cấu hình đã provision, xử lý parameters thiếu/null/default có chủ đích, quản lý metadata theo quy ước, và triển khai thay đổi theo giai đoạn. Bài học này tập trung vào backward compatibility của catalog, schema parameters và metadata trong Open Service Broker API (OSB API), cùng cách tổ chức chúng trong Spring Cloud Service Broker.

## 1. Catalog là hợp đồng công khai giữa broker và platform

OSB catalog mô tả các service offering và plan mà broker cung cấp. Platform đọc catalog để hiển thị dịch vụ, kiểm tra capability và xây dựng request provision, update hoặc binding.

Một service definition thường có các thuộc tính như:

- ID và name của service.
- Description.
- Bindable và các capability liên quan.
- Danh sách plans.
- Tags, requires và metadata.
- Schemas cho parameters theo operation nếu được công bố.
- Các thuộc tính mở rộng được phiên bản OSB API và platform hỗ trợ.

Plan có ID, name, description, metadata và có thể có schema riêng. Những giá trị này không chỉ là dữ liệu hiển thị: service ID và plan ID được platform gửi lại trong request lifecycle. Vì vậy, catalog cần được quản lý như một API contract có consumer, compatibility policy và rollout plan.

Một catalog đơn giản:

~~~json
{
  "services": [
    {
      "id": "service-postgresql",
      "name": "postgresql",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "plan-standard",
          "name": "standard",
          "description": "Plan cho ứng dụng production"
        }
      ]
    }
  ]
}
~~~

Platform có thể cache catalog. Vì vậy thay đổi ở broker không nhất thiết xuất hiện ngay ở mọi foundation hoặc mọi controller. Một thời gian có thể tồn tại đồng thời platform dùng catalog cũ và platform đã refresh catalog mới. Broker phải chấp nhận request hợp lệ theo cả hai trạng thái trong giai đoạn chuyển tiếp.

## 2. Phân biệt protocol version, catalog contract và resource configuration

Ba loại version thường bị trộn lẫn:

| Loại | Mô tả | Ví dụ |
|---|---|---|
| OSB API version | Phiên bản giao thức giữa platform và broker | X-Broker-API-Version |
| Catalog/schema revision | Phiên bản nội bộ của định nghĩa service, plan và parameter schema | catalog revision 12 |
| Resource configuration version | Phiên bản cấu hình đã áp dụng cho một instance cụ thể | config version 4 |

Header X-Broker-API-Version xác định phiên bản giao thức OSB mà request sử dụng. Nó không tự động version hóa schema parameters hoặc metadata của catalog.

Một instance được tạo theo schema cũ có thể vẫn tồn tại khi catalog đã tiến hóa. Broker cần biết instance đó được tạo với plan nào, parameters nào và quy tắc diễn giải nào. Không thể chỉ đọc catalog mới rồi giả định mọi instance cũ đã được chuyển sang semantics mới.

Nên lưu resource configuration version hoặc schema revision nội bộ cùng instance record. Version này giúp broker chọn đúng migration/defaulting/validation policy cho dữ liệu đã tồn tại.

## 3. Giữ ổn định service ID và plan ID

Service ID và plan ID là định danh được platform lưu và gửi lại trong các request. Khi thay đổi mô tả, pricing display hoặc schema, hãy giữ nguyên ID nếu semantics của offering/plan vẫn tương thích.

Không tái sử dụng một plan ID cho một loại tài nguyên có ý nghĩa khác. Ví dụ plan-standard trước đây cấp PostgreSQL 4 vCPU, 16 GB RAM; nếu cùng ID sau này đại diện cho engine khác hoặc giới hạn dữ liệu khác, instance cũ có thể bị hiểu sai khi update hoặc deprovision.

Quy tắc gợi ý:

- **Giữ service ID** khi offering vẫn là cùng một sản phẩm và contract lifecycle tương thích.
- **Giữ plan ID** khi semantics, entitlement và cách quản lý tài nguyên vẫn tương thích.
- **Tạo plan ID mới** khi thay đổi làm khác bản chất gói dịch vụ, resource model hoặc contract parameters.
- **Không đổi ID để chỉ sửa tên hiển thị** nếu không cần thiết.
- **Không xóa mapping ID cũ** khi vẫn còn instance/binding tham chiếu tới nó.

Ví dụ khi bổ sung một plan:

~~~json
{
  "plans": [
    {
      "id": "plan-standard",
      "name": "standard",
      "description": "Plan hiện tại, tiếp tục hỗ trợ instance cũ"
    },
    {
      "id": "plan-premium",
      "name": "premium",
      "description": "Plan mới với tài nguyên và SLA cao hơn"
    }
  ]
}
~~~

Thêm plan mới thường ít rủi ro hơn việc thay đổi ý nghĩa của plan đang được sử dụng. Tuy nhiên, cần kiểm tra khả năng provider, quota, billing và platform access trước khi công bố plan mới.

## 4. Thêm parameter mới theo hướng tương thích ngược

Một thay đổi phổ biến là bổ sung cấu hình mới. Ví dụ service PostgreSQL ban đầu chỉ nhận storage_gb, sau đó broker muốn hỗ trợ backup_retention_days.

Schema ban đầu:

~~~json
{
  "type": "object",
  "properties": {
    "storage_gb": {
      "type": "integer",
      "minimum": 10,
      "maximum": 500
    }
  },
  "required": [
    "storage_gb"
  ]
}
~~~

Schema mở rộng:

~~~json
{
  "type": "object",
  "properties": {
    "storage_gb": {
      "type": "integer",
      "minimum": 10,
      "maximum": 500
    },
    "backup_retention_days": {
      "type": "integer",
      "minimum": 1,
      "maximum": 35
    }
  },
  "required": [
    "storage_gb"
  ]
}
~~~

Field mới là optional nên client cũ vẫn gửi request hợp lệ. Broker có thể áp dụng default nội bộ, chẳng hạn 7 ngày, khi field vắng mặt. Không nên thêm field mới vào required ngay khi công bố vì platform đã cache schema cũ hoặc automation cũ có thể không gửi field đó.

### 4.1. Default phải được thực thi ở broker

JSON Schema có thể mô tả default như một annotation, nhưng không nên giả định mọi validator hoặc platform tự động thêm giá trị đó vào request. Broker cần xác định default trong application layer.

Ví dụ:

~~~java
public NormalizedParameters normalize(CreateParameters input) {
    int retentionDays = input.backupRetentionDays() == null
        ? 7
        : input.backupRetentionDays();

    return new NormalizedParameters(
        input.storageGb(),
        retentionDays
    );
}
~~~

Đây là pseudocode minh họa. Model request thực tế phụ thuộc phiên bản thư viện và cách broker parse parameters. Điều quan trọng là defaulting phải có quy tắc ổn định, được kiểm thử và lưu lại như cấu hình đã áp dụng.

Không dùng default động thay đổi theo thời gian nếu instance cũ cần tái tạo cùng cấu hình. Nếu default chuyển từ 7 lên 14 ngày, một request update cũ không gửi field có thể bị hiểu khác trước. Có thể cần lưu resolved value vào instance record để semantics của cấu hình không phụ thuộc default hiện tại.

## 5. Phân biệt field vắng mặt, null, rỗng và giá trị mặc định

Đây là điểm dễ gây breaking change trong schema parameters.

| Dạng input | Ý nghĩa có thể có | Quy tắc cần định nghĩa |
|---|---|---|
| Field không xuất hiện | Client chưa biết field hoặc muốn giữ nguyên | Default khi create; giữ nguyên khi update nếu contract quy định |
| Field có giá trị null | Client gửi giá trị rỗng rõ ràng | Từ chối hoặc xử lý theo schema |
| Chuỗi rỗng/object rỗng | Giá trị có mặt nhưng không chứa dữ liệu | Không tự động coi là absent |
| Giá trị cụ thể | Client chủ động cấu hình | Validate và áp dụng |
| Default do broker chọn | Giá trị đã resolve từ policy | Persist để giữ semantics |

Create và update có thể cần semantics khác nhau. Với create, field vắng mặt thường có thể nhận default. Với update, field vắng mặt thường có nghĩa là không yêu cầu thay đổi field đó, trong khi null có thể có nghĩa xóa giá trị hoặc không hợp lệ. Broker cần tuân theo contract update và định nghĩa của từng parameter.

Không deserialize mọi request vào một DTO rồi để Java null đại diện cho cả absent và explicit null nếu hai trường hợp có ý nghĩa khác nhau. Khi cần phân biệt, dùng representation có presence flag, JSON tree hoặc patch model phù hợp.

## 6. Thay đổi validation constraints có thể phá client cũ

Không phải mọi thay đổi schema đều an toàn.

| Thay đổi | Rủi ro tương thích | Nhận định |
|---|---|---|
| Thêm optional property | Thường thấp | Client cũ có thể bỏ qua |
| Thêm property vào required | Cao | Request cũ thiếu field sẽ bị từ chối |
| Thu hẹp minimum/maximum | Cao | Giá trị trước đây hợp lệ có thể không còn hợp lệ |
| Mở rộng enum | Thường thấp với request cũ | Client cũ có thể không hiểu giá trị mới trong response |
| Xóa enum value | Cao | Automation đang gửi giá trị cũ bị lỗi |
| Đổi type integer thành string | Rất cao | Payload và code client có thể không còn hợp lệ |
| Đổi ý nghĩa của property | Rất cao | Cùng payload tạo resource khác |
| Đổi default | Có thể cao | Request thiếu field có thể tạo cấu hình khác |
| Xóa property | Cao | Client cũ vẫn gửi field đó |
| Đổi tên property | Cao | Client cũ không gửi tên mới |

Khi muốn bỏ một giá trị cũ, có thể triển khai giai đoạn chuyển tiếp: tiếp tục chấp nhận giá trị cũ, phát cảnh báo hoặc metric, cập nhật client, rồi chỉ loại bỏ khi đã có bằng chứng không còn consumer. Nếu cần semantics mới, cân nhắc property mới hoặc plan ID mới thay vì tái sử dụng property cũ với ý nghĩa khác.

## 7. Tách schema cho create, update và binding

Parameters trong OSB có thể được sử dụng ở nhiều operation. Không nên dùng một schema chung cho mọi mục đích nếu field và semantics khác nhau.

Ví dụ:

~~~json
{
  "schemas": {
    "service_instance": {
      "create": {
        "parameters": {
          "type": "object",
          "properties": {
            "storage_gb": {
              "type": "integer",
              "minimum": 10
            },
            "backup_retention_days": {
              "type": "integer",
              "minimum": 1
            }
          },
          "required": [
            "storage_gb"
          ]
        }
      },
      "update": {
        "parameters": {
          "type": "object",
          "properties": {
            "backup_retention_days": {
              "type": "integer",
              "minimum": 1
            }
          }
        }
      }
    },
    "service_binding": {
      "create": {
        "parameters": {
          "type": "object",
          "properties": {
            "role": {
              "type": "string",
              "enum": [
                "read_only",
                "read_write"
              ]
            }
          }
        }
      }
    }
  }
}
~~~

Schema create có thể yêu cầu storage_gb. Schema update chỉ cho phép thay đổi backup_retention_days. Schema binding mô tả role của consumer. Nếu broker thay đổi một schema, cần xác định operation nào bị ảnh hưởng.

Không mặc định parameters của binding là cấu hình instance. Binding có thể tạo credentials hoặc quyền truy cập riêng. Việc đổi schema binding không nên vô tình làm thay đổi permission profile của binding đã tồn tại.

## 8. Lưu cấu hình đã resolve cùng instance

Catalog schema mô tả request được chấp nhận ở thời điểm hiện tại. Instance record phải giữ cấu hình thực tế đã được áp dụng khi provision.

Ví dụ request ban đầu:

~~~json
{
  "storage_gb": 100
}
~~~

Broker áp dụng default backup retention 7 ngày. Instance record nên lưu:

~~~json
{
  "instance_id": "instance-7f3a",
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "schema_revision": 3,
  "configuration_version": 1,
  "requested_parameters": {
    "storage_gb": 100
  },
  "resolved_configuration": {
    "storage_gb": 100,
    "backup_retention_days": 7
  }
}
~~~

Tùy chính sách bảo mật, không nhất thiết lưu cả raw request nếu có PII hoặc secret. Nhưng broker cần lưu resolved configuration và version đủ để quản lý resource về sau.

Khi catalog revision mới đổi default retention lên 14 ngày, instance cũ vẫn giữ 7 ngày nếu không có update được chấp nhận. Không tái tính default của instance cũ mỗi lần worker restart hoặc reconciliation chạy.

### 8.1. Schema revision là dữ liệu nội bộ

OSB API không tự yêu cầu broker phải trả schema revision cho từng instance. Broker có thể lưu revision nội bộ để quản lý compatibility. Không thêm field tùy chỉnh vào OSB response nếu contract không cho phép hoặc platform không hỗ trợ.

Schema revision giúp application service chọn normalizer, validator hoặc migration function phù hợp. Nó không thay service ID, plan ID hoặc OSB API version.

## 9. Tiến hóa metadata an toàn

Metadata thường được dùng để hiển thị tên thân thiện, mô tả dài, icon, tài liệu, support URL, bullets hoặc thông tin chi phí theo quy ước được hỗ trợ. Platform có thể chỉ hiểu một số key và bỏ qua key không biết.

Ví dụ metadata:

~~~json
{
  "displayName": "PostgreSQL Standard",
  "longDescription": "Cơ sở dữ liệu quan hệ được quản lý cho workload production.",
  "documentationUrl": "https://docs.example.invalid/postgresql",
  "supportUrl": "https://support.example.invalid",
  "bullets": [
    "Tự động sao lưu",
    "Mã hóa kết nối",
    "Theo dõi hiệu năng"
  ]
}
~~~

Khi tiến hóa metadata:

- Giữ key hiện có nếu platform hoặc marketplace đang sử dụng.
- Thêm key mới theo cách additive và có namespace nếu là extension riêng.
- Không đổi type của key đã công bố.
- Không đổi semantics của key mà consumer đang dựa vào.
- Không đặt secret, internal endpoint hoặc tenant-specific data trong metadata.
- Không dùng metadata hiển thị làm nguồn quyết định authorization hoặc provider behavior.
- Xác minh URL và dữ liệu hiển thị trước khi công bố.

Nếu cần thay key, có thể hỗ trợ cả key cũ và key mới trong một giai đoạn. Theo dõi consumer còn sử dụng key cũ nếu platform cung cấp telemetry; sau đó mới bỏ key cũ trong một release có thông báo.

## 10. Metadata hiển thị không thay thế capability và schema

Một lỗi thiết kế là đưa behavior vào metadata riêng, ví dụ metadata.requiresBackup=true rồi để platform hoặc broker suy ra semantics. Nếu behavior là một phần contract OSB chuẩn, hãy dùng field chuẩn tương ứng; nếu là parameter, mô tả trong schema; nếu là capability, công bố capability theo đặc tả.

| Nhu cầu | Nơi nên biểu diễn |
|---|---|
| Tên thân thiện | Metadata displayName |
| Tài liệu sản phẩm | Metadata documentation URL theo quy ước hỗ trợ |
| Parameter người dùng nhập | Schemas |
| Broker có hỗ trợ binding không | Capability field chuẩn |
| Plan có cho phép update không | plan_updateable theo OSB |
| Yêu cầu platform có capability gì | requires |
| Quyền user được cấp | Domain policy và binding logic |
| Secret hoặc provider credential | Secret store |
| Cấu hình thực tế của instance | Instance registry |

Metadata có thể bổ sung cách trình bày, nhưng không nên là điều kiện ẩn để provision, bind hoặc deprovision. Nếu platform bỏ qua metadata, lifecycle vẫn phải hoạt động đúng theo contract chuẩn.

## 11. Ngừng cung cấp plan mà vẫn hỗ trợ instance cũ

Một plan có thể không còn phù hợp cho provision mới nhưng vẫn đang được nhiều instance sử dụng. Đây là bài toán deprecation.

Không có một cờ deprecation phổ quát trong mọi platform OSB mà broker có thể giả định. Cách ẩn hoặc khóa plan cho provision mới phụ thuộc platform và quy trình vận hành. Broker cần tách hai chính sách:

- **Admission policy:** có chấp nhận provision mới theo plan này không?
- **Lifecycle policy:** có tiếp tục cho phép update, retrieve, bind/unbind hoặc deprovision các instance hiện hữu không?

Một quy trình an toàn:

1. Xác định plan ID cũ và tất cả instance đang tham chiếu.
2. Thông báo thay đổi và cung cấp plan thay thế nếu có.
3. Dùng cơ chế service access/availability phù hợp của platform để hạn chế provision mới khi được hỗ trợ.
4. Giữ mapping plan cũ trong broker để quản lý resource hiện hữu.
5. Cho phép deprovision và các thao tác cần thiết cho instance cũ.
6. Theo dõi số instance còn dùng plan cũ.
7. Chỉ loại bỏ hoàn toàn khi không còn resource tham chiếu và contract platform cho phép.

Nếu broker từ chối provision mới cho plan cũ ở application layer, cần trả lỗi có thể hành động và bảo đảm không vô tình chặn deprovision. Không xóa plan khỏi catalog trước khi xác định platform còn cần plan metadata để xử lý instance cũ hay không.

## 12. Thay đổi plan và pricing mà không làm sai instance cũ

Giá hoặc quota của plan có thể thay đổi theo thời gian. Broker cần phân biệt:

- Giá hiển thị hiện tại trong catalog.
- Giá đã thỏa thuận với tenant hoặc subscription.
- Resource configuration đã provision.
- Giá áp dụng cho kỳ billing cụ thể.
- Thời điểm policy mới có hiệu lực.

Không dùng catalog metadata hiện tại để tính lại hóa đơn quá khứ. Hệ thống billing cần price version và effective time riêng. Tương tự, không tự động đổi cấu hình instance cũ khi plan metadata hoặc mô tả được cập nhật.

Nếu plan thay đổi đáng kể về CPU, storage, SLA hoặc provider placement, tạo plan ID mới thường dễ quản lý hơn. Nếu chỉ thay display text hoặc URL tài liệu, giữ plan ID và cập nhật metadata thường phù hợp.

## 13. Update instance theo schema mới

Khi instance cũ gửi update request, broker phải validate request theo semantics của update và trạng thái instance, không áp dụng máy móc toàn bộ schema create hiện tại.

Ví dụ instance được provision khi schema revision 2, nhưng hiện catalog ở revision 4. Request update có thể chỉ chứa field được phép thay đổi. Broker nên:

1. Tải instance record và schema/configuration revision đã lưu.
2. Resolve plan và operation policy hiện hành.
3. Parse update parameters theo schema update tương thích.
4. Phân biệt field absent, null và explicit value.
5. Merge với resolved configuration hiện tại theo update semantics.
6. Validate cấu hình đích và quota/provider capability.
7. Tạo operation nếu update bất đồng bộ.
8. Chỉ ghi configuration version mới sau khi provider xác nhận thành công.

Không thay toàn bộ resolved configuration bằng payload update nếu payload chỉ chứa delta. Việc đó có thể làm mất các field đã được áp dụng từ trước nhưng không được gửi lại.

### 13.1. Không tự động migrate mọi instance khi schema đổi

Catalog/schema revision mới không đồng nghĩa mọi instance phải thay cấu hình. Có thể có ba loại thay đổi:

- **Presentation-only:** đổi metadata hiển thị; không cần thay instance.
- **Compatible default/optional extension:** chỉ ảnh hưởng instance mới hoặc instance update có field liên quan.
- **Resource migration:** cần thay đổi provider resource, có operation, quota và rollback riêng.

Nếu cần migration tài nguyên, thực hiện qua workflow có version, trạng thái và audit. Không âm thầm thay cấu hình trong quá trình GET hoặc reconciliation.

## 14. Rollout theo giai đoạn để tránh mixed-version behavior

Trong một hệ thống nhiều replica và nhiều foundation, catalog có thể được cache khác thời điểm. Broker mới cũng có thể chạy song song với phiên bản cũ trong quá trình deployment.

Một rollout an toàn:

~~~mermaid
flowchart TD
    A["Thiết kế schema additive"] --> B["Triển khai broker chấp nhận cũ và mới"]
    B --> C["Cập nhật catalog"]
    C --> D["Platform refresh catalog"]
    D --> E["Theo dõi request và parameter usage"]
    E --> F["Cập nhật client/automation"]
    F --> G["Đánh giá bỏ field hoặc plan cũ"]
    G --> H["Gỡ hỗ trợ sau khi hết consumer"]
~~~

Quy trình cụ thể:

1. Triển khai broker có khả năng đọc cả payload cũ và mới.
2. Giữ schema hiện tại cho đến khi tất cả replica hỗ trợ logic mới.
3. Công bố field optional hoặc plan mới.
4. Chờ platform refresh catalog theo cơ chế của nó.
5. Theo dõi request để biết client đã gửi field mới hay còn dùng field cũ.
6. Cập nhật automation và tài liệu consumer.
7. Nếu cần bỏ field cũ, bắt đầu cảnh báo và giai đoạn chuyển tiếp.
8. Chỉ loại bỏ sau khi có bằng chứng không còn consumer và instance lifecycle vẫn được hỗ trợ.

Không triển khai thay đổi schema phá vỡ trước khi broker có khả năng chấp nhận cả hai dạng request. Với rolling deployment, replica cũ và mới có thể cùng nhận request trong thời gian ngắn; schema và persistence changes cần tương thích trong giai đoạn đó.

## 15. Versioning nội bộ và migration dữ liệu

Broker nên version hóa schema/configuration nội bộ độc lập với OSB API version.

Một bảng version mapping có thể gồm:

| Schema revision | Thay đổi | Cách đọc dữ liệu cũ |
|---|---|---|
| 1 | storage_gb | Đọc trực tiếp |
| 2 | Thêm backup_retention_days optional | Thiếu field dùng giá trị đã lưu/default revision 2 |
| 3 | Chuẩn hóa tên storage tier | Migration từ legacy tier |
| 4 | Thêm backup_window | Optional, không đổi cấu hình cũ |

Khi khởi động hoặc xử lý instance, broker cần biết record thuộc revision nào. Có thể dùng migration database để chuẩn hóa cấu trúc lưu trữ và application mapper để diễn giải giá trị lịch sử.

Không ghi đè dữ liệu gốc trước khi có thể phục hồi. Với migration lớn, lưu source snapshot hoặc audit record và có kế hoạch rollback. Nếu schema revision không xác định hoặc record không hợp lệ, đưa vào trạng thái review thay vì đoán cấu hình.

## 16. Spring Cloud: tổ chức catalog và schema trong code

Trong Spring Cloud Open Service Broker, catalog có thể được xây dựng từ service definition/plan model hoặc cấu hình theo cơ chế của phiên bản thư viện. Nên tách catalog definition khỏi lifecycle state và provider implementation.

Các thành phần gợi ý:

| Thành phần | Trách nhiệm |
|---|---|
| CatalogDefinitionProvider | Xây dựng service/plan definitions |
| ParameterSchemaRegistry | Quản lý schema theo service, plan và operation |
| SchemaNormalizer | Áp dụng default và chuẩn hóa payload |
| InstanceConfigurationRepository | Lưu resolved configuration và revision |
| PlanCompatibilityPolicy | Xác định plan cũ còn hỗ trợ lifecycle nào |
| MetadataMapper | Map metadata chuẩn và extension |
| LifecycleCoordinator | Provision/update/deprovision theo instance state |
| CatalogContractTest | Xác minh catalog JSON và compatibility |

Ví dụ schema revision:

~~~java
public record InstanceConfiguration(
    String serviceId,
    String planId,
    int schemaRevision,
    int configurationVersion,
    Map<String, Object> resolvedParameters
) {}
~~~

Pseudocode normalizer:

~~~java
public NormalizedConfiguration normalizeCreate(
        String planId,
        int schemaRevision,
        Map<String, Object> parameters) {

    ParameterSchema schema =
        schemaRegistry.requireCreateSchema(planId, schemaRevision);

    schema.validate(parameters);

    Map<String, Object> resolved =
        schema.applyBrokerDefaults(parameters);

    return new NormalizedConfiguration(
        planId,
        schemaRevision,
        resolved
    );
}
~~~

Đây là model minh họa, không phải API class cố định của Spring Cloud Open Service Broker. Hãy ánh xạ vào catalog/plan abstractions của phiên bản dependency đang dùng. Điều quan trọng là schema revision và defaulting policy phải được quản lý rõ, có thể kiểm thử và không bị trộn với protocol version.

## 17. Kiểm thử compatibility cho catalog và parameters

Test nên kiểm tra cả JSON catalog, request cũ, request mới và instance đã provision từ schema revision trước.

| Nhóm test | Trường hợp | Kết quả mong đợi |
|---|---|---|
| Catalog contract | Service/plan IDs hiện tại | IDs và semantics ổn định |
| Additive schema | Client cũ bỏ qua optional field mới | Request vẫn hợp lệ |
| Required field | Thêm field bắt buộc | Compatibility test phát hiện breaking change |
| Defaulting | Field vắng mặt khi create | Broker áp dụng default xác định và persist |
| Update absent | Field không xuất hiện trong update | Giữ giá trị hiện tại theo contract |
| Explicit null | Field gửi null | Xử lý theo schema, không nhầm với absent |
| Enum evolution | Giá trị cũ còn được hỗ trợ | Instance/automation cũ tiếp tục hoạt động |
| Metadata | Thêm key mới | Consumer cũ không bị ảnh hưởng |
| Metadata removal | Bỏ key cũ | Chỉ sau khi consumer đã chuyển |
| Legacy instance | Instance schema revision cũ | Read/update/deprovision vẫn đúng |
| Legacy plan | Plan không còn cho provision mới | Lifecycle resource hiện hữu vẫn hoạt động |
| Mixed replica | Broker phiên bản cũ/mới trong rollout | Không đọc/ghi dữ liệu sai schema |
| Migration rerun | Chạy lại data migration | Không tạo duplicate hoặc đổi semantics |
| Billing | Plan price thay đổi | Kỳ cũ giữ price version lịch sử |

Nên lưu fixture catalog và request từ các phiên bản trước để chạy contract regression. Một test hữu ích là provision instance theo schema cũ, triển khai catalog revision mới, rồi update/deprovision instance đó. Kết quả phải giữ cấu hình đã resolve và resource mapping đúng.

## 18. Các lỗi thường gặp khi tiến hóa catalog

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Đổi ý nghĩa service/plan ID | Instance cũ bị diễn giải sai | Giữ ID hoặc tạo plan ID mới |
| Thêm parameter mới vào required ngay | Client cũ không provision được | Thêm optional trước, migrate consumer sau |
| Đổi default mà không lưu resolved value | Instance cũ thay cấu hình ngoài ý muốn | Persist resolved configuration |
| Coi absent và null giống nhau | Update xóa/ghi đè cấu hình sai | Định nghĩa presence semantics |
| Xóa enum cũ ngay | Automation cũ bị lỗi | Deprecation period và telemetry |
| Đổi type property | Request cũ không validate | Additive field hoặc plan mới |
| Dùng metadata để điều khiển lifecycle | Platform bỏ qua key làm behavior sai | Dùng capability/schema/domain policy chuẩn |
| Xóa plan khỏi catalog quá sớm | Khó quản lý instance cũ | Giữ legacy mapping và lifecycle support |
| Dùng catalog mới để tính lại instance cũ | Cấu hình/billing lịch sử sai | Lưu schema/config/price revision |
| Deploy replica không tương thích schema | Lỗi ngẫu nhiên trong rolling update | Expand-and-contract migration |
| Không test platform cache cũ | Request từ client cũ bị từ chối | Mixed-version contract tests |

## 19. Checklist phát hành catalog revision mới

Trước khi thay đổi catalog, hãy xác nhận:

- [ ] Service ID và plan ID không bị tái sử dụng với semantics khác.
- [ ] Plan mới có ID riêng nếu resource model hoặc entitlement thay đổi đáng kể.
- [ ] Parameter mới được thêm optional trước khi có consumer gửi field.
- [ ] Default được áp dụng ở broker và resolved value được lưu.
- [ ] Absent, null, empty và explicit value có semantics rõ.
- [ ] Create, update và binding có schema riêng khi cần.
- [ ] Validation constraints không vô tình loại bỏ request hợp lệ cũ.
- [ ] Enum value cũ còn được hỗ trợ trong thời gian chuyển tiếp.
- [ ] Metadata key được thêm/xóa theo compatibility policy.
- [ ] Metadata không chứa secret hoặc điều khiển authorization/lifecycle.
- [ ] Instance lưu schema/configuration revision và resolved configuration.
- [ ] Instance cũ vẫn update, retrieve, bind/unbind và deprovision được theo policy.
- [ ] Plan ngừng provision mới vẫn có lifecycle policy cho resource hiện hữu.
- [ ] OSB API version được phân biệt với catalog/schema revision.
- [ ] Rolling deployment hỗ trợ mixed-version request và database schema.
- [ ] Có contract fixtures, regression tests và migration rollback plan.

Tiến hóa catalog an toàn đòi hỏi broker coi service ID, plan ID, parameter schema và metadata là hợp đồng dài hạn với platform. Thay đổi additive, default được lưu rõ ràng, schema revision nội bộ, plan deprecation có kiểm soát và kiểm thử với request cũ giúp instance đã provision tiếp tục hoạt động theo cấu hình ban đầu. Khi Spring Cloud Service Broker tách catalog definition khỏi resource state và lifecycle policy, broker có thể phát triển offering mới mà không làm mất khả năng quản lý những instance cũ.

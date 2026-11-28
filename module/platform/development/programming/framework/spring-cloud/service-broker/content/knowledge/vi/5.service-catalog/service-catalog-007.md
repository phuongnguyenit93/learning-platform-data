# Metadata, tags, liên kết tài liệu và thông tin hiển thị trên marketplace

Catalog là điểm bắt đầu để Cloud Foundry, Kubernetes hoặc một nền tảng khác khám phá dịch vụ do Spring Cloud Service Broker cung cấp. Ngoài ID, tên và mô tả, một catalog hữu ích cần có metadata để marketplace trình bày dịch vụ, tags để hỗ trợ tìm kiếm và các liên kết để người dùng đọc tài liệu hoặc nhận trợ giúp. Các thông tin này giúp người dùng chọn đúng dịch vụ và service plan trước khi thực hiện provision.

Open Service Broker API (OSB API) định nghĩa cấu trúc catalog và một số field như `tags`, `metadata`, `plans`, `bindable` và `dashboard_client`. Trong đó, `metadata` là object mở để broker cung cấp thông tin bổ sung; cách marketplace hiển thị từng khóa metadata phụ thuộc vào platform. Vì vậy, thiết kế catalog cần phân biệt field được OSB API định nghĩa với quy ước metadata riêng của marketplace.

## 1. Catalog cung cấp thông tin gì?

Endpoint `GET /v2/catalog` trả về danh sách service definition mà broker cung cấp. Một service thường có các thông tin chính:

- `id`: định danh ổn định của service trong broker.
- `name`: tên kỹ thuật của service.
- `description`: mô tả ngắn về chức năng.
- `bindable`: cho biết service instance có hỗ trợ binding hay không.
- `plans`: danh sách service plan có thể chọn.
- `tags`: danh sách nhãn phục vụ phân loại và tìm kiếm.
- `metadata`: object chứa thông tin bổ sung, thường được marketplace sử dụng để hiển thị tên thân thiện, hình ảnh, mô tả dài và liên kết.
- `dashboard_client`: thông tin client để platform tích hợp dashboard nếu broker hỗ trợ chức năng dashboard SSO theo OSB API.

Một catalog có thể có nhiều service, mỗi service có nhiều plan. Metadata có thể xuất hiện ở cấp service hoặc cấp plan. Metadata cấp service mô tả sản phẩm nói chung; metadata cấp plan mô tả biến thể, mức dịch vụ hoặc thông tin riêng của một lựa chọn.

Ví dụ cấu trúc rút gọn:

```json
{
  "services": [
    {
      "id": "postgresql-service-v1",
      "name": "postgresql",
      "description": "Dịch vụ cơ sở dữ liệu PostgreSQL được quản lý",
      "bindable": true,
      "tags": ["database", "relational", "sql", "postgresql"],
      "metadata": {
        "displayName": "PostgreSQL Database",
        "providerDisplayName": "Example Cloud",
        "longDescription": "Cơ sở dữ liệu PostgreSQL được vận hành và giám sát bởi nền tảng.",
        "documentationUrl": "https://docs.example.com/services/postgresql",
        "supportUrl": "https://support.example.com/postgresql",
        "imageUrl": "https://cdn.example.com/catalog/postgresql.png"
      },
      "plans": [
        {
          "id": "postgresql-standard-v1",
          "name": "standard",
          "description": "Dành cho ứng dụng có tải vừa",
          "free": false,
          "metadata": {
            "displayName": "Standard",
            "bullets": ["Sao lưu hằng ngày", "Dung lượng 20 GB"]
          }
        }
      ]
    }
  ]
}
```

Đây là ví dụ minh họa. Tên khóa metadata như `displayName`, `longDescription`, `documentationUrl`, `supportUrl`, `imageUrl` và `bullets` là các quy ước thường gặp trong marketplace; không nên hiểu rằng mọi platform đều bắt buộc nhận diện hoặc hiển thị chúng. Các field OSB API như `id`, `name`, `description`, `bindable`, `plans`, `tags` và `metadata` mới là cấu trúc giao thức cần tuân thủ.

## 2. Phân biệt metadata, tags và các field giao thức

### 2.1. Metadata là object mở

`metadata` là một JSON object chứa các cặp khóa và giá trị bổ sung. Broker có thể dùng nó để cung cấp thông tin phục vụ marketplace hoặc tích hợp riêng với platform. OSB API không quy định mọi khóa bên trong metadata phải có cùng ý nghĩa trên tất cả nền tảng.

Một số khóa phổ biến ở cấp service:

| Khóa metadata | Ý nghĩa thường gặp | Gợi ý nội dung |
|---|---|---|
| `displayName` | Tên thân thiện trên giao diện | `PostgreSQL Database` |
| `providerDisplayName` | Tên nhà cung cấp hiển thị | `Example Cloud` |
| `longDescription` | Mô tả dài về tính năng và phạm vi dịch vụ | Nêu khả năng vận hành, backup, giám sát và giới hạn chính |
| `imageUrl` | Ảnh hoặc biểu tượng đại diện | URL HTTPS đến ảnh có quyền sử dụng |
| `featuredImageUrl` | Ảnh nổi bật cho trang chi tiết nếu marketplace hỗ trợ | Ảnh banner hoặc hình minh họa |
| `documentationUrl` | Trang tài liệu sản phẩm | Hướng dẫn bắt đầu và tham chiếu kỹ thuật |
| `supportUrl` | Trang hỗ trợ hoặc tạo ticket | Kênh liên hệ hỗ trợ khách hàng |

Một số marketplace còn đọc các khóa bổ sung như `bullets`, `shareable` hoặc metadata riêng của nhà cung cấp. Trước khi phát hành, cần xác định platform đích thực sự tiêu thụ khóa nào. Khóa lạ có thể bị bỏ qua mà không làm catalog mất hiệu lực, nhưng không có nghĩa nó sẽ xuất hiện trên UI.

Metadata cấp plan có thể chứa `displayName`, `bullets`, mô tả hoặc thông tin giá theo quy ước marketplace. OSB API cũng có các field riêng ở plan như `free`, `bindable`, `schemas`, `maximum_polling_duration` và `maintenance_info` tùy phiên bản. Khi thông tin đã có field giao thức riêng, nên dùng đúng field đó thay vì tạo bản sao trong metadata. Ví dụ, dùng `free: false` để thể hiện plan tính phí theo hợp đồng OSB; không chỉ ghi chuỗi `paid` trong metadata.

### 2.2. Tags là danh sách nhãn riêng

`tags` là một mảng chuỗi ở cấp service, thường dùng để phân loại và hỗ trợ tìm kiếm. Ví dụ:

```json
"tags": ["database", "relational", "sql", "postgresql"]
```

Tags nên ngắn gọn, có nghĩa ổn định và phản ánh đặc tính người dùng có thể tìm kiếm. Với service cơ sở dữ liệu, các nhãn như `database`, `relational`, `sql` và `postgresql` hữu ích hơn những từ chung chung như `best`, `new` hoặc `popular`. Không đưa secret, ID tenant, tên khách hàng hoặc dữ liệu cá nhân vào tags.

Tags không thay thế metadata. Tag phù hợp cho lọc và phân loại; metadata phù hợp cho nội dung trình bày có cấu trúc. Cũng không dùng `tags` để mô tả capability theo hợp đồng khi OSB API đã có field `requires` dành cho các yêu cầu/capability mà service cần từ platform, chẳng hạn `route_forwarding`, `syslog_drain` hoặc `volume_mount`.

### 2.3. Liên kết tài liệu khác với dashboard URL

Các liên kết `documentationUrl` và `supportUrl` thường được đặt trong metadata vì đây là thông tin trình bày hoặc quy ước marketplace. Broker nên cung cấp URL HTTPS ổn định, có thể truy cập từ mạng người dùng marketplace và không yêu cầu nhúng token bí mật trong query string.

`dashboard_client` là field giao thức riêng, phục vụ việc platform tích hợp dashboard SSO. Nó không phải nơi thay thế `documentationUrl` hoặc `supportUrl`. Nếu broker không cung cấp dashboard hoặc platform không dùng chức năng này, không cần tạo object giả chỉ để có thêm liên kết. Khi sử dụng `dashboard_client`, phải tuân thủ cấu trúc và luồng xác thực mà OSB API quy định; không công khai secret của hệ thống quản trị nội bộ trong metadata thông thường.

## 3. Marketplace sử dụng metadata như thế nào?

Marketplace thường có ít nhất hai vùng hiển thị:

1. **Danh sách dịch vụ:** hiển thị tên, biểu tượng, mô tả ngắn và một số tags để người dùng nhận biết hoặc lọc sản phẩm.
2. **Trang chi tiết dịch vụ:** hiển thị mô tả dài, nhà cung cấp, tài liệu, hỗ trợ, các plan và thông tin tính năng của từng plan.

Ví dụ cách ánh xạ thông tin:

| Thành phần giao diện | Dữ liệu catalog thường dùng |
|---|---|
| Tên dịch vụ | `metadata.displayName`, dự phòng `name` |
| Nhà cung cấp | `metadata.providerDisplayName` |
| Mô tả ngắn | `description` |
| Mô tả chi tiết | `metadata.longDescription` |
| Ảnh đại diện | `metadata.imageUrl` |
| Nhãn tìm kiếm | `tags` |
| Tài liệu | `metadata.documentationUrl` |
| Hỗ trợ | `metadata.supportUrl` |
| Tên plan trên UI | `plan.metadata.displayName`, dự phòng `plan.name` |
| Điểm nổi bật của plan | `plan.metadata.bullets` nếu marketplace hỗ trợ |

Ánh xạ trên chỉ là quy ước trình bày. Một marketplace có thể chỉ hiển thị `name`, `description`, `plans` và bỏ qua một số metadata. Broker không nên dựa vào việc UI nhất định render một trường không được platform cam kết hỗ trợ. Khi cần hiển thị một nội dung quan trọng cho mọi client OSB, hãy đặt phần cốt lõi trong các field chuẩn như `description` hoặc tài liệu bên ngoài có thể truy cập được.

## 4. Thiết kế metadata cho service và plan

Metadata nên có cấu trúc nhất quán giữa các service. Một ví dụ cho service PostgreSQL:

```json
{
  "displayName": "PostgreSQL Database",
  "providerDisplayName": "Example Cloud",
  "longDescription": "Dịch vụ PostgreSQL được quản lý, hỗ trợ sao lưu, giám sát và khôi phục dữ liệu.",
  "documentationUrl": "https://docs.example.com/services/postgresql",
  "supportUrl": "https://support.example.com/postgresql",
  "imageUrl": "https://cdn.example.com/catalog/postgresql.png"
}
```

Plan `standard` có thể bổ sung thông tin riêng:

```json
{
  "displayName": "Standard",
  "bullets": [
    "Dung lượng lưu trữ 20 GB",
    "Sao lưu hằng ngày",
    "Phù hợp với môi trường production tải vừa"
  ]
}
```

Khi thiết kế schema nội bộ, nên thống nhất:

- Quy tắc đặt tên khóa và kiểu dữ liệu của từng khóa.
- Khóa nào thuộc service, khóa nào thuộc plan.
- Trường nào là bắt buộc trong catalog nội bộ và trường nào chỉ là tùy chọn.
- URL nào cần kiểm tra HTTPS, host được phép và khả năng truy cập.
- Cách xử lý khi marketplace không hỗ trợ một metadata key.
- Cách version hóa metadata riêng nếu nhiều client phụ thuộc vào một cấu trúc mở rộng.

Không nên đưa toàn bộ cấu hình triển khai vào metadata. Thông tin kết nối database, credential, secret manager reference nội bộ, địa chỉ control plane riêng tư hoặc chi tiết topology không phải nội dung marketplace. Catalog có thể được cache hoặc hiển thị rộng rãi trong phạm vi platform; chỉ đưa thông tin cần thiết cho việc khám phá và lựa chọn dịch vụ.

## 5. Xây dựng catalog bằng Spring Cloud Open Service Broker

Trong Spring Cloud Open Service Broker, ứng dụng cung cấp catalog thông qua `CatalogService`. Cấu trúc `Catalog`, `ServiceDefinition` và `Plan` biểu diễn phản hồi catalog của OSB API. Có thể tập trung metadata trong một nguồn cấu hình hoặc cơ sở dữ liệu rồi chuyển thành model giao thức khi `getCatalog()` được gọi.

Ví dụ minh họa một catalog tĩnh:

```java
@Service
public class ExampleCatalogService implements CatalogService {

    @Override
    public Catalog getCatalog() {
        Map<String, Object> serviceMetadata = Map.of(
                "displayName", "PostgreSQL Database",
                "providerDisplayName", "Example Cloud",
                "longDescription", "Cơ sở dữ liệu PostgreSQL được quản lý.",
                "documentationUrl", "https://docs.example.com/services/postgresql",
                "supportUrl", "https://support.example.com/postgresql",
                "imageUrl", "https://cdn.example.com/catalog/postgresql.png"
        );

        Map<String, Object> planMetadata = Map.of(
                "displayName", "Standard",
                "bullets", List.of("Dung lượng 20 GB", "Sao lưu hằng ngày")
        );

        Plan standardPlan = Plan.builder()
                .id("postgresql-standard-v1")
                .name("standard")
                .description("Dành cho ứng dụng có tải vừa")
                .free(false)
                .metadata(planMetadata)
                .build();

        ServiceDefinition postgres = ServiceDefinition.builder()
                .id("postgresql-service-v1")
                .name("postgresql")
                .description("Dịch vụ cơ sở dữ liệu PostgreSQL được quản lý")
                .bindable(true)
                .tags(List.of("database", "relational", "sql", "postgresql"))
                .metadata(serviceMetadata)
                .plans(List.of(standardPlan))
                .build();

        return Catalog.builder()
                .serviceDefinitions(List.of(postgres))
                .build();
    }
}
```

Đây là ví dụ theo mô hình builder của thư viện; tên phương thức builder hoặc kiểu collection có thể khác giữa các phiên bản Spring Cloud Open Service Broker. Cần đối chiếu API của dependency thực tế khi tích hợp. Nguyên tắc thiết kế vẫn giữ nguyên: `tags` được đặt ở service definition, metadata service gắn với service, metadata plan gắn với plan, và các field chuẩn như `id`, `name`, `description`, `bindable`, `free` được thiết lập rõ ràng.

### 5.1. Quản lý metadata từ cấu hình

Với catalog có nhiều service, không nên viết metadata rải rác trong controller. Có thể lưu dữ liệu trong YAML hoặc database và xây dựng một lớp chuyển đổi:

```text
Catalog configuration / Catalog repository
                 |
                 v
       CatalogDefinitionMapper
                 |
                 v
       Catalog + ServiceDefinition
                 |
                 v
        CatalogService.getCatalog()
                 |
                 v
           GET /v2/catalog
```

Lớp mapper chịu trách nhiệm chuẩn hóa tags, kiểm tra metadata, gắn metadata đúng cấp và tạo các model OSB. Controller chỉ nên tiếp nhận request và trả catalog đã được xây dựng. Cách này giúp thay đổi ảnh, liên kết hoặc mô tả mà không phải sửa logic provision.

### 5.2. Catalog theo platform instance

Nếu broker phục vụ nhiều platform instance, catalog có thể khác nhau theo capability, tenant hoặc chính sách đã đăng ký. Ví dụ một plan chỉ hỗ trợ volume mount không nên xuất hiện như một lựa chọn khả dụng trên platform không đáp ứng capability đó. Khi lọc catalog theo platform, cần dùng `PlatformContext` đã xác thực và kiểm tra quyền; không chọn catalog chỉ dựa trên một header hoặc query parameter do client tự gửi.

Metadata hiển thị cũng có thể khác theo platform, nhưng `service_id` và `plan_id` phải ổn định trong phạm vi mà broker quản lý. Không thay đổi ID chỉ vì đổi `displayName`, ảnh hoặc mô tả. Các tài nguyên đã provision vẫn tham chiếu đến service và plan ID đã được chọn lúc tạo.

## 6. Quy trình cập nhật và version hóa catalog

Catalog thường được platform tải lại định kỳ hoặc khi có thay đổi. Một thay đổi metadata có thể tác động trực tiếp đến cách sản phẩm xuất hiện trong marketplace, vì vậy cần có quy trình phát hành:

1. **Soạn metadata:** cập nhật tên hiển thị, mô tả, tags, ảnh và liên kết trong nguồn cấu hình.
2. **Kiểm tra:** xác nhận kiểu dữ liệu, trường bắt buộc, URL, tags trùng lặp và metadata không chứa secret.
3. **Kiểm tra tương thích:** thử catalog trên platform mục tiêu và xác nhận marketplace hiển thị đúng các trường mà platform hỗ trợ.
4. **Phát hành:** triển khai cấu hình hoặc phiên bản broker có catalog mới.
5. **Theo dõi:** gọi `GET /v2/catalog`, kiểm tra response và xem log khi platform tải catalog.

`id` của service và plan là định danh giao thức, nên giữ ổn định khi chỉ thay đổi nội dung trình bày. Nếu thay đổi có ảnh hưởng tương thích hoặc tạo ra một sản phẩm/plan mới, hãy đánh giá việc cấp ID mới và cách xử lý các instance đã tồn tại. Không tái sử dụng ID cũ cho một sản phẩm có ý nghĩa khác.

Metadata có thể được cache ở platform hoặc gateway. Nếu thay đổi không xuất hiện ngay, cần xem chu kỳ refresh catalog và cache policy của platform. Broker không nên giả định mọi thay đổi metadata được marketplace hiển thị tức thì.

## 7. Kiểm tra chất lượng catalog

Trước khi công bố catalog, nên kiểm tra cả hợp đồng OSB API và trải nghiệm marketplace:

| Hạng mục | Kiểm tra |
|---|---|
| Service identity | `id` duy nhất và ổn định; `name` và `description` có ý nghĩa |
| Plan identity | Mỗi plan có ID ổn định, tên và mô tả rõ ràng |
| Bindability | `bindable` và capability thực tế nhất quán với thao tác binding |
| Tags | Là mảng chuỗi, không rỗng vô nghĩa, không trùng và không chứa dữ liệu nhạy cảm |
| Metadata | Là JSON object hợp lệ, dùng đúng kiểu dữ liệu và đúng cấp service/plan |
| Documentation | URL HTTPS hợp lệ, không chứa token hoặc thông tin nội bộ |
| Support | URL dẫn đến kênh hỗ trợ có người chịu trách nhiệm |
| Marketplace | Thử trên platform mục tiêu để xác nhận các khóa metadata được hiển thị như dự kiến |
| Compatibility | Không xóa hoặc đổi ID plan đang được service instance sử dụng |
| Exposure | Không trả credential, secret, endpoint quản trị riêng tư hoặc cấu hình nội bộ |

Một ví dụ kiểm tra logic trong code:

```java
static void validateCatalogMetadata(Map<String, Object> metadata) {
    Object displayName = metadata.get("displayName");
    if (displayName != null && !(displayName instanceof String)) {
        throw new IllegalArgumentException("metadata.displayName phải là chuỗi");
    }

    for (String key : List.of("documentationUrl", "supportUrl", "imageUrl")) {
        Object value = metadata.get(key);
        if (value == null) {
            continue;
        }
        if (!(value instanceof String url) || !url.startsWith("https://")) {
            throw new IllegalArgumentException(key + " phải là URL HTTPS");
        }
    }
}
```

Đoạn mã chỉ minh họa kiểm tra kiểu và scheme. Hệ thống thực tế nên dùng URI parser, allowlist host khi cần, kiểm tra độ dài và quy tắc truy cập; không tải URL tùy ý trong request catalog vì có thể tạo rủi ro SSRF. Kiểm tra metadata nên diễn ra khi cấu hình được nạp hoặc trong pipeline phát hành, tránh để một giá trị sai làm hỏng request catalog ở runtime.

## 8. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Đưa mọi thông tin vào `description` | Marketplace khó phân tách tên, ảnh, link và tags | Dùng field chuẩn và metadata theo quy ước được hỗ trợ |
| Cho rằng mọi platform hiển thị cùng metadata key | UI có thể bỏ qua một số thông tin | Kiểm tra marketplace đích và duy trì mô tả chuẩn trong `description` |
| Dùng tags thay metadata | Không thể trình bày mô tả hoặc liên kết có cấu trúc | Dùng tags cho phân loại, metadata cho nội dung bổ sung |
| Đặt documentation URL trong `dashboard_client` | Nhầm mục đích dashboard SSO với tài liệu | Dùng metadata key phù hợp cho tài liệu và hỗ trợ |
| Thay service/plan ID khi sửa tên hiển thị | Instance hiện có có thể không còn khớp catalog | Giữ ID ổn định qua các thay đổi trình bày |
| Đưa secret vào metadata | Bí mật có thể bị hiển thị hoặc lưu cache | Chỉ xuất bản dữ liệu dành cho marketplace |
| Metadata service và plan không nhất quán | UI hiển thị sai hoặc thiếu thông tin | Chuẩn hóa schema và mapper cho từng cấp |
| Giả định catalog cập nhật tức thì | Marketplace tiếp tục hiển thị dữ liệu cache cũ | Kiểm tra cơ chế refresh và cache của platform |

## 9. Kết luận

Metadata, tags và liên kết tài liệu giúp catalog của Spring Cloud Service Broker trở thành danh mục có thể khám phá và dễ sử dụng trên marketplace. Hãy dùng các field chuẩn của OSB API cho định danh và hành vi dịch vụ, `tags` cho phân loại, `metadata` cho thông tin trình bày theo quy ước của platform, và `dashboard_client` đúng mục đích dashboard SSO. Quản lý metadata tập trung, giữ ổn định service/plan ID, kiểm tra URL và dữ liệu nhạy cảm, rồi xác nhận kết quả trên marketplace mục tiêu trước khi phát hành.

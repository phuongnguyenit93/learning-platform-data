# Tiến hóa schema tham số và tương thích với yêu cầu cũ

Service broker nhận tham số từ nền tảng khi người dùng tạo service instance, cập nhật cấu hình hoặc tạo service binding. Các tham số này là một phần của hợp đồng giữa nền tảng và broker. Khi dịch vụ phát triển, nhóm có thể cần thêm trường, thay đổi giới hạn, ngừng hỗ trợ một tùy chọn hoặc đổi cách diễn giải dữ liệu. Nếu chỉ sửa schema rồi triển khai phiên bản mới, những request được tạo bởi nền tảng cũ, catalog đang cache hoặc instance đã tồn tại có thể không còn hoạt động.

Với `SPRING_CLOUD_SERVICE_BROKER`, tiến hóa schema cần được xem như tiến hóa API. Schema công bố cho nền tảng phải khớp với khả năng xử lý thực tế; broker phải tiếp tục hiểu các request hợp lệ đã được phát hành trước đó; dữ liệu cấu hình đã lưu phải có cách đọc và chuyển đổi rõ ràng. Mục tiêu là thay đổi hợp đồng có kiểm soát, tránh làm hỏng thao tác provision, update và bind đang được sử dụng.

## 1. Schema tham số nằm ở đâu trong Open Service Broker API?

Trong OSB API, broker có thể công bố schema của tham số trong catalog theo từng service plan. Các vị trí thường dùng gồm:

- `schemas.service_instance.create.parameters`: tham số gửi khi tạo service instance.
- `schemas.service_instance.update.parameters`: tham số gửi khi cập nhật service instance.
- `schemas.service_binding.create.parameters`: tham số gửi khi tạo binding.

Mỗi schema mô tả cấu trúc của object `parameters`, chẳng hạn tên thuộc tính, kiểu dữ liệu, trường bắt buộc, giá trị cho phép và giới hạn. Schema giúp nền tảng biết cách tạo giao diện nhập liệu và giúp người tích hợp hiểu request hợp lệ trông như thế nào.

Ví dụ plan PostgreSQL công bố schema tạo instance:

```json
{
  "schemas": {
    "service_instance": {
      "create": {
        "parameters": {
          "$schema": "http://json-schema.org/draft-04/schema#",
          "type": "object",
          "properties": {
            "storage_gb": {
              "type": "integer",
              "minimum": 20,
              "maximum": 500,
              "description": "Dung lượng lưu trữ tính bằng GB"
            },
            "backup_enabled": {
              "type": "boolean",
              "description": "Bật backup định kỳ"
            },
            "region": {
              "type": "string",
              "enum": ["ap-southeast-1", "ap-southeast-2"]
            }
          },
          "required": ["storage_gb"],
          "additionalProperties": false
        }
      }
    }
  }
}
```

Ví dụ dùng JSON Schema Draft 4 theo hợp đồng schema của OSB API. Cần kiểm tra phiên bản OSB API và model mà Spring Cloud Open Service Broker đang sử dụng trước khi chọn validator hoặc cú pháp schema. Không mặc định rằng mọi từ khóa của các bản JSON Schema mới hơn đều được nền tảng và broker hỗ trợ.

Schema được công bố không thay thế kiểm tra ở server. Nền tảng có thể cache catalog, có thể không hỗ trợ toàn bộ từ khóa hoặc có thể gửi request trực tiếp. Broker phải xác thực tham số nhận được bằng logic của chính mình trước khi tạo hoặc thay đổi tài nguyên.

## 2. Phân biệt schema create, update và binding

Ba luồng tham số có vòng đời và ý nghĩa khác nhau. Không nên dùng chung một schema cho tất cả chỉ vì chúng cùng là JSON object.

| Vị trí schema | Mục đích | Ví dụ tham số |
|---|---|---|
| `service_instance.create.parameters` | Chọn cấu hình ban đầu cho tài nguyên | Dung lượng, vùng triển khai, phiên bản engine |
| `service_instance.update.parameters` | Thay đổi cấu hình của instance đã tồn tại | Tăng dung lượng, bật backup, đổi cửa sổ bảo trì |
| `service_binding.create.parameters` | Điều chỉnh một binding cụ thể | Vai trò truy cập, tên database/schema, quyền kết nối |

Khi tạo instance, broker cần biết trường nào bắt buộc để xác định cấu hình ban đầu. Khi update, cần quy định request là tập thay đổi một phần hay cấu hình đích đầy đủ. Nếu trường bị bỏ qua có nghĩa là giữ giá trị cũ, broker phải giữ nguyên giá trị đó. Nếu trường bị bỏ qua có nghĩa là quay về mặc định, hành vi này cần được công bố và áp dụng nhất quán.

Với binding, tham số thường gắn với cách một workload sử dụng instance, không nên vô tình làm thay đổi cấu hình lõi của instance. Credential trả về từ binding thường do broker tạo và kiểm soát; không đưa secret do broker sinh vào schema tham số đầu vào.

## 3. Những nguyên tắc tương thích khi thay đổi schema

Tương thích cần được xem theo ít nhất ba hướng:

1. **Client cũ gọi broker mới:** request đã được phát hành trước đây vẫn được broker mới chấp nhận và giữ đúng ý nghĩa.
2. **Client mới gọi broker cũ:** request được tạo từ catalog mới không làm hỏng các replica broker cũ trong giai đoạn rollout hoặc nền tảng chưa đồng bộ.
3. **Dữ liệu cũ được code mới đọc:** cấu hình instance đã lưu từ trước vẫn có thể được truy xuất, cập nhật và thu hồi sau khi schema thay đổi.

Một thay đổi có thể tương thích theo hướng này nhưng không tương thích theo hướng khác. Ví dụ, thêm trường tùy chọn thường giúp broker mới hiểu được cấu hình mới, nhưng client mới gửi trường đó đến broker cũ có thể bị từ chối nếu broker cũ dùng `additionalProperties: false`.

### Các thay đổi thường an toàn hơn

- Thêm một thuộc tính tùy chọn mà request cũ không cần gửi.
- Mở rộng giới hạn cho phép theo cách không làm thay đổi ý nghĩa của giá trị cũ.
- Tiếp tục chấp nhận tên trường cũ trong một giai đoạn chuyển tiếp.
- Thêm metadata mô tả hoặc ví dụ mà không thay đổi cách xử lý request.
- Bổ sung khả năng mới nhưng vẫn duy trì hành vi mặc định tương thích với request cũ.

Ngay cả các thay đổi này cũng cần kiểm tra hành vi validator, `additionalProperties`, catalog cache và các client có kiểm tra schema nghiêm ngặt.

### Các thay đổi có nguy cơ phá vỡ tương thích

- Thêm trường mới vào `required`, khiến request cũ thiếu trường bị từ chối.
- Xóa hoặc đổi tên thuộc tính mà client cũ vẫn gửi.
- Đổi kiểu dữ liệu, ví dụ từ số nguyên sang chuỗi hoặc từ scalar sang object.
- Thu hẹp `minimum`, `maximum`, `minLength`, `maxLength` hoặc `pattern` khiến giá trị trước đây hợp lệ trở thành không hợp lệ.
- Xóa giá trị khỏi `enum` mà client cũ đang sử dụng.
- Đổi đơn vị hoặc ý nghĩa của trường nhưng vẫn giữ nguyên tên, ví dụ từ GB sang GiB hoặc từ giờ UTC sang giờ địa phương.
- Đổi giá trị mặc định khiến request không gửi trường đó tạo ra tài nguyên khác trước.
- Thay đổi ngữ nghĩa update từ giữ trường bị bỏ qua sang đặt lại mặc định.

Không chỉ cấu trúc JSON mới quyết định tương thích. Thay đổi ý nghĩa nghiệp vụ hoặc hành vi mặc định cũng có thể làm hỏng ứng dụng dù request vẫn vượt qua schema.

## 4. Ví dụ tiến hóa schema theo cách tương thích

Giả sử phiên bản đầu của plan PostgreSQL chỉ cho phép chọn dung lượng và vùng:

```json
{
  "type": "object",
  "properties": {
    "storage_gb": {
      "type": "integer",
      "minimum": 20,
      "maximum": 500
    },
    "region": {
      "type": "string",
      "enum": ["ap-southeast-1", "ap-southeast-2"]
    }
  },
  "required": ["storage_gb"],
  "additionalProperties": false
}
```

Sau một thời gian, sản phẩm cần bổ sung tùy chọn `backup_enabled`. Một schema mới có thể thêm thuộc tính này dưới dạng tùy chọn:

```json
{
  "type": "object",
  "properties": {
    "storage_gb": {
      "type": "integer",
      "minimum": 20,
      "maximum": 500
    },
    "region": {
      "type": "string",
      "enum": ["ap-southeast-1", "ap-southeast-2"]
    },
    "backup_enabled": {
      "type": "boolean"
    }
  },
  "required": ["storage_gb"],
  "additionalProperties": false
}
```

Broker mới vẫn chấp nhận request cũ vì `backup_enabled` không bắt buộc. Nếu trường bị bỏ qua, broker áp dụng mặc định đã được xác định rõ, ví dụ `false`, rồi lưu cấu hình hiệu lực. Nếu trường được gửi, broker kiểm tra plan có hỗ trợ backup và tenant có quyền sử dụng tính năng đó hay không.

Tuy nhiên, do schema vẫn đặt `additionalProperties: false`, broker cũ sẽ từ chối request có `backup_enabled`. Trong môi trường nhiều replica, cần triển khai code hiểu trường mới trên toàn bộ replica trước khi công bố schema hoặc bật giao diện gửi trường này. Một cách khác là dùng cơ chế rollout có feature gate để nền tảng chỉ gửi trường mới khi broker đã sẵn sàng.

Lưu ý: từ khóa `default` trong JSON Schema là metadata mô tả giá trị mặc định; không phải mọi validator đều tự chèn giá trị này vào object. Ứng dụng phải áp dụng default tường minh sau khi parse và validate.

## 5. Bảng đánh giá các loại thay đổi

| Thay đổi | Rủi ro | Cách xử lý khuyến nghị |
|---|---|---|
| Thêm thuộc tính tùy chọn | Thấp đến trung bình | Giữ default ổn định; bảo đảm code cũ hoặc replica cũ không nhận trường mới ngoài dự kiến |
| Thêm thuộc tính bắt buộc | Cao | Dùng giai đoạn chuyển tiếp, default có kiểm soát hoặc hợp đồng/plan mới |
| Mở rộng `maximum` hoặc nới `minimum` | Thấp với broker mới; có thể không tương thích client/replica cũ | Kiểm tra giới hạn ở provider và các phiên bản đang chạy |
| Thu hẹp miền giá trị | Cao | Không áp dụng đột ngột; deprecate giá trị cũ và lập kế hoạch chuyển đổi |
| Thêm giá trị `enum` | Trung bình | Kiểm tra client có enum đóng hoặc validator cache schema cũ |
| Xóa giá trị `enum` | Cao | Ngừng khuyến nghị trước, tiếp tục nhận giá trị cũ trong thời gian chuyển tiếp |
| Đổi tên hoặc đổi kiểu trường | Rất cao | Giữ alias cũ, chuyển đổi nội bộ hoặc tạo hợp đồng phiên bản mới |
| Đổi đơn vị hoặc ý nghĩa | Rất cao | Dùng trường mới có tên rõ đơn vị; không âm thầm đổi cách diễn giải |
| Đổi default | Cao về ngữ nghĩa | Giữ default cũ cho request cũ hoặc phân biệt phiên bản cấu hình |
| Xóa trường cũ | Cao | Chỉ xóa sau khi ngừng sử dụng, migrate dữ liệu và hết thời gian tương thích |

Rủi ro trong bảng phụ thuộc cả cách client xử lý schema và chiến lược triển khai. Trước khi công bố thay đổi, cần kiểm thử cả request cũ lẫn request mới trên phiên bản broker sẽ nhận chúng.

## 6. Thêm trường tùy chọn mà không làm thay đổi request cũ

Khi thêm thuộc tính, cần xác định bốn điểm:

1. **Tính tùy chọn:** request cũ không gửi trường mới vẫn phải hợp lệ.
2. **Giá trị mặc định:** ứng dụng phải có default rõ ràng và giữ ổn định cho cấu hình cũ.
3. **Kiểm tra điều kiện:** trường mới chỉ được áp dụng nếu plan, vùng triển khai và tenant hỗ trợ.
4. **Lưu cấu hình hiệu lực:** broker nên lưu giá trị đã chuẩn hóa để thao tác về sau không phụ thuộc việc default thay đổi trong code.

Ví dụ Java minh họa chuẩn hóa request:

```java
public record CreateDatabaseParameters(
        Integer storageGb,
        String region,
        Boolean backupEnabled) {
}

public record EffectiveDatabaseConfiguration(
        int storageGb,
        String region,
        boolean backupEnabled) {
}

public class DatabaseConfigurationMapper {

    public EffectiveDatabaseConfiguration normalize(
            CreateDatabaseParameters input) {
        int storage = input.storageGb() == null
                ? 20
                : input.storageGb();
        String region = input.region() == null
                ? "ap-southeast-1"
                : input.region();
        boolean backup = Boolean.TRUE.equals(input.backupEnabled());

        return new EffectiveDatabaseConfiguration(storage, region, backup);
    }
}
```

Đây là ví dụ mô hình hóa thuộc ứng dụng. Trong triển khai thật, giá trị mặc định phải lấy từ chính sách plan và có thể khác nhau theo plan. Không nên đặt một default toàn cục nếu `small` và `production` có chính sách khác nhau. Cũng cần phân biệt trường bị bỏ qua với trường được gửi `null` nếu API của ứng dụng có quy định hai trường hợp này khác nhau.

## 7. Ngừng hỗ trợ trường cũ theo lộ trình

Giả sử broker ban đầu nhận `storage_gb`, sau đó muốn chuyển sang `storage_gib` với cách định nghĩa đơn vị chính xác hơn. Đổi tên ngay sẽ làm client cũ gửi `storage_gb` bị lỗi. Có thể thực hiện chuyển đổi theo các giai đoạn:

**Giai đoạn 1 — Bổ sung:** schema công bố trường mới tùy chọn, broker vẫn nhận trường cũ. Nếu cả hai cùng xuất hiện, xác định quy tắc rõ ràng: từ chối request mâu thuẫn hoặc quy định ưu tiên có kiểm soát.

**Giai đoạn 2 — Khuyến nghị:** tài liệu và giao diện chuyển sang trường mới. Broker tiếp tục nhận trường cũ, chuyển nó sang biểu diễn nội bộ thống nhất và ghi metric về mức sử dụng trường cũ.

**Giai đoạn 3 — Cảnh báo:** đánh dấu trường cũ là deprecated trong tài liệu và metadata phù hợp; thông báo thời điểm dự kiến ngừng hỗ trợ. Không dựa vào việc schema JSON tự có cơ chế deprecation chuẩn để đảm bảo mọi nền tảng hiển thị cảnh báo.

**Giai đoạn 4 — Chuyển đổi:** hỗ trợ khách hàng hoặc workload chuyển sang trường mới; kiểm tra log, metric và dữ liệu cấu hình để xác nhận không còn request phụ thuộc trường cũ.

**Giai đoạn 5 — Ngừng nhận:** chỉ loại bỏ trường cũ khi đã hết thời gian tương thích và có phương án cho instance đang tồn tại. Nếu việc bỏ trường làm thay đổi hợp đồng lớn, nên cung cấp service hoặc plan phiên bản mới thay vì âm thầm phá vỡ contract cũ.

Không nên tự động giả định `storage_gb` và `storage_gib` có cùng giá trị số. GB theo hệ thập phân và GiB theo hệ nhị phân khác nhau. Chuyển đổi cần quy định đơn vị, cách làm tròn và giới hạn tài nguyên.

## 8. Versioning schema và plan

OSB API có phiên bản giao thức riêng, nhưng phiên bản đường dẫn API như `/v2` không phải là phiên bản schema tham số của từng plan. Việc broker nâng phiên bản giao thức không tự động version hóa các tham số nghiệp vụ.

Không phải mọi thay đổi schema đều cần plan ID mới. Có thể giữ nguyên plan ID khi bổ sung thuộc tính tùy chọn và duy trì hành vi cũ. Khi thay đổi không tương thích hoặc làm thay đổi đáng kể cấu hình/tính năng mà khách hàng mua, cần cân nhắc một hợp đồng mới, ví dụ:

- Một plan mới với ID ổn định mới nếu đó là gói dịch vụ khác biệt.
- Một service definition phiên bản mới nếu sản phẩm hoặc contract tổng thể thay đổi lớn.
- Một trường phiên bản tham số do ứng dụng định nghĩa nếu cần nhiều dạng cấu hình cùng tồn tại trong một plan.

Không có một trường `schemaVersion` chung được OSB API tự động áp dụng cho mọi request tham số. Nếu ứng dụng thêm `configuration_version` hoặc `contract_version`, đó là quy ước riêng của broker; phải công bố, validate và duy trì tương thích rõ ràng.

Một cách hữu ích là lưu phiên bản contract nội bộ cùng cấu hình đã chuẩn hóa:

```java
public record StoredInstanceConfiguration(
        String serviceId,
        String planId,
        int parameterContractVersion,
        EffectiveDatabaseConfiguration configuration) {
}
```

Khi đọc instance cũ, broker biết cấu hình được tạo theo quy tắc nào và có thể chuyển đổi sang model nội bộ mới. Giá trị version này là dữ liệu quản lý của ứng dụng, không phải trường chuẩn bắt buộc của OSB API.

## 9. Validate schema và validate nghiệp vụ ở server

Schema công bố giúp kiểm tra cấu trúc, nhưng broker cần nhiều lớp kiểm tra hơn:

1. **Kiểm tra cú pháp và kiểu:** JSON hợp lệ, object đúng kiểu, số nguyên/chuỗi/boolean đúng định dạng.
2. **Kiểm tra schema:** trường bắt buộc, enum, pattern, min/max, độ dài và cấu trúc lồng nhau.
3. **Chuẩn hóa:** áp dụng default, chuẩn hóa đơn vị, chuỗi, vùng và biểu diễn nội bộ.
4. **Kiểm tra nghiệp vụ:** plan có hỗ trợ tính năng không, quota còn đủ không, vùng có sẵn sàng không, tổ hợp tham số có hợp lệ không.
5. **Kiểm tra quyền:** tenant và caller có quyền yêu cầu cấu hình đó không; không tin `tenant_id` do người dùng tự gửi nếu danh tính phải lấy từ context đã xác thực.
6. **Kiểm tra trạng thái:** update có hợp lệ với trạng thái hiện tại không; instance có đang provision hoặc deprovision không.

Ví dụ, schema cho phép `storage_gb` trong khoảng 20 đến 500 nhưng tenant chỉ được cấp tối đa 200 GB. Request 300 GB vượt qua JSON Schema nhưng vẫn phải bị từ chối bởi chính sách quota. Tương tự, schema có thể cho phép region `ap-southeast-2`, nhưng broker cần xác nhận plan và tài khoản đó có quyền triển khai ở vùng này.

Không dùng schema làm ranh giới bảo mật. Request có thể đến từ client không tuân theo catalog, catalog cache có thể cũ và các validator có thể diễn giải từ khóa khác nhau. Tất cả điều kiện quan trọng phải được kiểm tra ở broker.

## 10. Xử lý thuộc tính không biết và `additionalProperties`

`additionalProperties` quyết định schema có cho phép thuộc tính không được liệt kê trong `properties` hay không. Nếu đặt `false`, validator từ chối trường lạ. Điều này giúp phát hiện lỗi đánh máy và tránh nhận cấu hình ngoài dự kiến, nhưng có thể gây vấn đề khi client mới gửi trường mới đến broker cũ.

Nếu cho phép thuộc tính lạ, broker có thể dễ tiếp nhận mở rộng trong giai đoạn rollout, nhưng phải tránh âm thầm bỏ qua một trường mà client nghĩ rằng đã được áp dụng. Một lựa chọn là chỉ cho phép một vùng mở rộng được kiểm soát, ví dụ `extensions`, và định nghĩa schema cho từng khóa con.

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| `additionalProperties: false` | Hạn chế dữ liệu ngoài hợp đồng, phát hiện typo | Replica hoặc broker cũ từ chối trường mới |
| Cho phép mọi thuộc tính lạ | Dễ mở rộng theo hướng forward-compatible | Có thể bỏ qua tham số mà client nghĩ đã có hiệu lực |
| Cho phép vùng `extensions` có schema riêng | Có ranh giới mở rộng rõ ràng | Cần quản lý namespace và phiên bản từng extension |

Nếu broker bỏ qua thuộc tính không biết, cần ghi nhận có kiểm soát để phát hiện client gửi sai tên trường; không log toàn bộ payload nếu có thể chứa dữ liệu nhạy cảm. Với tham số có ảnh hưởng tài nguyên, lựa chọn an toàn thường là từ chối rõ ràng hoặc chỉ nhận trong namespace đã được định nghĩa.

## 11. Update parameters: trường bị bỏ qua, null và cấu hình cũ

Update thường phức tạp hơn create vì broker đã có cấu hình hiệu lực. Cần định nghĩa rõ ngữ nghĩa của từng request:

- Trường không xuất hiện: giữ nguyên giá trị cũ hay áp dụng default?
- Trường xuất hiện với `null`: xóa giá trị, đặt về default hay không hợp lệ?
- Trường xuất hiện với giá trị mới: thay đổi ngay hay cần kiểm tra khả năng chuyển đổi?
- Trường không còn nằm trong schema mới: có tiếp tục được chấp nhận cho instance cũ không?

Không nên suy luận các quy tắc này từ cách thư viện deserialize JSON. Hãy quy định trong contract và triển khai rõ ở application service. Với update dạng partial, cần merge request với cấu hình hiện tại trước khi validate cấu hình đích. Với update dạng desired-state đầy đủ, cần yêu cầu đủ trường và định nghĩa default nhất quán.

Ví dụ logic cập nhật một phần:

```java
public EffectiveDatabaseConfiguration applyUpdate(
        EffectiveDatabaseConfiguration current,
        UpdateDatabaseParameters update) {

    int storage = update.storageGb() == null
            ? current.storageGb()
            : update.storageGb();

    boolean backup = update.backupEnabled() == null
            ? current.backupEnabled()
            : update.backupEnabled();

    return new EffectiveDatabaseConfiguration(
            storage,
            current.region(),
            backup);
}
```

Đây là ví dụ cho hợp đồng partial update, trong đó `null` được dùng như dấu hiệu không thay đổi. Nếu API cần phân biệt “không gửi trường” với “gửi null để xóa”, DTO phải giữ được sự khác biệt đó, chẳng hạn dùng wrapper biểu diễn presence hoặc giữ map JSON đã parse. Không nên dùng `Boolean`/`Integer` nullable rồi giả định luôn phân biệt được hai trường hợp.

Sau khi tạo cấu hình đích, broker phải kiểm tra chuyển đổi có hợp lệ với plan, provider và trạng thái instance. Việc tăng dung lượng có thể hỗ trợ online, trong khi giảm dung lượng có thể không được phép hoặc cần thao tác di chuyển dữ liệu.

## 12. Giữ tương thích với instance và operation đã tồn tại

Schema mới chủ yếu mô tả request mới. Nó không được dùng để diễn giải lại tùy tiện cấu hình cũ đã lưu. Mỗi instance nên lưu các thông tin cần thiết để vận hành lâu dài, ví dụ:

- Service ID và plan ID tại thời điểm tạo.
- Cấu hình đã chuẩn hóa và đơn vị rõ ràng.
- Phiên bản contract hoặc schema nội bộ đã dùng để tạo cấu hình.
- Thời điểm tạo/cập nhật và nguồn thay đổi.
- Trạng thái operation gần nhất và định danh tài nguyên provider.

Khi triển khai phiên bản mới, code phải tiếp tục đọc được cấu hình của phiên bản cũ. Nếu cần migration, hãy chuyển đổi theo bước có thể kiểm soát, có log/audit, có khả năng retry và không làm mất dữ liệu. Không bắt buộc phải migrate tất cả instance ngay trong lúc deploy; có thể dùng lazy migration khi đọc hoặc migration nền theo batch.

Deprovision cần được thiết kế đặc biệt cẩn thận. Thu hồi tài nguyên không nên phụ thuộc vào việc tham số create cũ còn vượt qua schema hiện tại hay không. Broker phải tra cứu định danh tài nguyên và trạng thái đã lưu để thu hồi đúng tài nguyên, kể cả khi schema của plan đã thay đổi hoặc plan không còn cho cấp phát mới.

Với operation bất đồng bộ đang chạy, nên lưu snapshot command hoặc cấu hình hiệu lực mà worker cần dùng. Worker không nên đọc lại một default mới sau khi deploy rồi vô tình thay đổi ý nghĩa của job đã được chấp nhận trước đó.

## 13. Idempotency khi schema thay đổi

OSB API có thể gửi lại request khi nền tảng không nhận được phản hồi. Broker cần xử lý request lặp theo định danh instance và quy tắc idempotency của thao tác. Khi schema thay đổi, cách tính fingerprint của request cũng cần được quản lý.

Ví dụ, request cũ không gửi `backup_enabled`; broker mới chuẩn hóa default là `false`. Request retry sau deploy có thể được parse thành cùng cấu hình hiệu lực. Nếu fingerprint được tính trực tiếp trên JSON thô, khác biệt về thứ tự key, cách biểu diễn số hoặc việc thêm default có thể tạo fingerprint khác dù ý nghĩa giống nhau.

Một quy trình hợp lý:

1. Parse và validate theo contract phù hợp với request.
2. Chuẩn hóa giá trị và đơn vị theo quy tắc của contract đó.
3. Tạo canonical representation có thứ tự và định dạng ổn định.
4. Tính fingerprint từ dữ liệu chuẩn hóa cùng các định danh cần thiết.
5. Tra cứu operation đã ghi nhận; nếu cùng yêu cầu thì trả lại kết quả hoặc trạng thái trước đó.
6. Nếu cùng instance ID nhưng nội dung khác nhau, trả lỗi xung đột phù hợp thay vì tạo thêm tài nguyên.

Khi nâng schema, cần giữ cách chuẩn hóa/fingerprint tương thích với những operation còn có thể retry. Có thể lưu fingerprint version cùng operation record để code mới biết cách so sánh request được tạo theo phiên bản cũ.

## 14. Triển khai schema mới trong môi trường nhiều replica

Trong môi trường Cloud Foundry hoặc Kubernetes, nhiều replica của broker có thể chạy các phiên bản khác nhau trong một khoảng thời gian. Catalog cũng có thể được cache ở nền tảng. Vì vậy, thứ tự rollout ảnh hưởng trực tiếp đến khả năng tương thích.

Một quy trình triển khai thêm trường tùy chọn có thể là:

1. **Chuẩn bị code:** triển khai broker có thể parse, validate và xử lý trường mới; trường chưa xuất hiện vẫn dùng default cũ.
2. **Rollout replica:** bảo đảm toàn bộ replica có khả năng nhận request mới trước khi client bắt đầu gửi trường đó.
3. **Cập nhật catalog:** công bố schema mới sau khi backend đã sẵn sàng; lưu ý catalog cache có thể khiến thời điểm quan sát khác nhau.
4. **Bật tính năng:** cho phép giao diện hoặc client gửi trường mới sau khi xác nhận toàn bộ đường đi đã hỗ trợ.
5. **Quan sát:** theo dõi lỗi validation, request cũ, request có trường mới và khác biệt giữa các replica.
6. **Thu hồi tương thích cũ:** chỉ thực hiện khi có kế hoạch deprecation và dữ liệu chứng minh client cũ không còn sử dụng.

Nếu cần rollback, phiên bản code trước phải có thể đọc dữ liệu đã được phiên bản mới ghi. Nếu không thể bảo đảm, hãy dùng feature gate hoặc giữ tương thích lưu trữ trước khi bật tính năng. Không chỉ kiểm tra readiness của HTTP server; cần kiểm tra cả schema, provider adapter và khả năng xử lý request mới.

## 15. Kiểm thử tương thích schema

Nên duy trì các fixture request đại diện cho những phiên bản schema đã phát hành. Mỗi lần thay đổi, chạy kiểm thử trên các hướng tương thích quan trọng.

| Nhóm kiểm thử | Câu hỏi cần xác minh |
|---|---|
| Request cũ với schema mới | Payload cũ có tiếp tục hợp lệ và giữ cùng ý nghĩa không? |
| Request mới với broker cũ | Trường mới có bị từ chối trong rolling deployment không? |
| Giá trị biên | Min/max, chuỗi rỗng, enum và kiểu sai có được xử lý đúng không? |
| Trường bị bỏ qua | Default hoặc giữ giá trị cũ có đúng hợp đồng không? |
| Trường lạ | `additionalProperties` được áp dụng nhất quán không? |
| Update | Merge, null và trường không xuất hiện có đúng ngữ nghĩa không? |
| Instance cũ | Cấu hình và operation đã lưu có đọc được sau nâng cấp không? |
| Retry | Request lặp sau deploy có cùng kết quả idempotent không? |
| Deprovision | Instance tạo theo schema cũ vẫn thu hồi được không? |

Ví dụ kiểm thử chuẩn hóa default cho request cũ:

```java
class DatabaseConfigurationMapperTest {

    private final DatabaseConfigurationMapper mapper =
            new DatabaseConfigurationMapper();

    @Test
    void keepsOldRequestBehaviorWhenBackupFieldIsAbsent() {
        var oldRequest = new CreateDatabaseParameters(
                20,
                "ap-southeast-1",
                null);

        var effective = mapper.normalize(oldRequest);

        assertThat(effective.storageGb()).isEqualTo(20);
        assertThat(effective.backupEnabled()).isFalse();
    }
}
```

Ngoài unit test, nên có contract test xác minh schema công bố trong catalog khớp với validator và DTO mà broker dùng. Integration test cần gửi request qua endpoint OSB API thực tế, vì khác biệt ở deserialization, thư viện validator hoặc phiên bản framework có thể không xuất hiện trong unit test.

## 16. Quan sát và quản trị vòng đời schema

Sau khi phát hành, cần biết client đang sử dụng trường nào và phiên bản contract nào. Có thể ghi metric hoặc structured log về:

- Số request theo service ID, plan ID và loại thao tác.
- Số lần validation thất bại theo mã lỗi và tên trường, tránh ghi giá trị nhạy cảm.
- Tần suất sử dụng trường cũ đã deprecated.
- Số request có thuộc tính không biết hoặc schema version không được hỗ trợ.
- Số instance còn lưu contract version cũ.
- Số operation đang chạy được tạo trước lần nâng cấp gần nhất.

Các dữ liệu này giúp quyết định khi nào có thể ngừng hỗ trợ trường cũ. Không ghi toàn bộ `parameters` vào log một cách mặc định vì chúng có thể chứa token, password, tên khách hàng hoặc thông tin nhạy cảm. Nếu cần chẩn đoán, hãy che dữ liệu và chỉ lưu tên trường hoặc mã lỗi cần thiết.

Nên có người hoặc nhóm sở hữu contract schema, quy trình review thay đổi và tài liệu ghi rõ thay đổi nào tương thích, thời gian deprecation và cách rollback. Schema là một phần của giao diện sản phẩm, nên cần được quản lý cùng mã nguồn và phiên bản phát hành.

## 17. Trình tự tiến hóa schema cho service broker

Khi cần thay đổi tham số của một plan, có thể làm theo trình tự:

1. Xác định thao tác bị ảnh hưởng: create, update hay binding; ghi lại payload hiện đang được client gửi.
2. Phân loại thay đổi là bổ sung tương thích hay thay đổi có thể phá vỡ hợp đồng.
3. Xác định default, đơn vị, ngữ nghĩa khi thiếu/null và chính sách với thuộc tính không biết.
4. Cập nhật code để đọc request cũ và mới, chuẩn hóa thành cấu hình nội bộ có version.
5. Kiểm tra ảnh hưởng đến instance, operation, retry và deprovision đã tồn tại.
6. Triển khai backend tương thích trước, sau đó mới công bố schema mới và bật client gửi trường mới.
7. Theo dõi metric sử dụng trường cũ, lỗi validation và request từ catalog cache.
8. Deprecate và loại bỏ trường cũ theo thời gian chuyển tiếp đã công bố.
9. Lưu fixture và contract test để những lần tiến hóa tiếp theo không làm mất tương thích.

Khi schema được tiến hóa theo các bước này, broker có thể mở rộng tham số và tính năng mà vẫn duy trì những request cũ, instance đã tạo và operation đang xử lý. Điều đó giúp nền tảng tiếp tục sử dụng service plan ổn định trong khi ứng dụng broker phát triển theo nhu cầu mới.

# Bảo trì theo maintenance_info khi framework và nền tảng hỗ trợ

Một service broker có thể cần cập nhật phần mềm, bản vá bảo mật, cấu hình hoặc phiên bản engine của backing service sau khi service instance đã được cấp phát. Ví dụ, một instance PostgreSQL đang chạy trên phiên bản engine cũ cần được nâng cấp lên phiên bản đã vá lỗi. Đây là hoạt động bảo trì trên tài nguyên đang tồn tại, khác với việc tạo instance mới hoặc chuyển người dùng sang một service plan khác.

Open Service Broker API (OSB API) có trường `maintenance_info` trong thông tin plan để broker công bố phiên bản bảo trì. Khi phiên bản API, framework và platform đều hỗ trợ trường này, platform có thể sử dụng thông tin đó để nhận biết phiên bản bảo trì mục tiêu và gửi yêu cầu cập nhật tương ứng tới broker. Broker chịu trách nhiệm thực hiện công việc trên tài nguyên thực tế, lưu trạng thái và báo kết quả theo hợp đồng OSB.

Bài học này giải thích ý nghĩa của `maintenance_info`, cách công bố thông tin trong catalog, cách tiếp nhận yêu cầu bảo trì trong luồng update, các điều kiện tương thích giữa framework và platform, cùng cách tổ chức thao tác bảo trì an toàn, có thể retry và theo dõi được.

## 1. Maintenance_info giải quyết vấn đề gì?

Service plan mô tả một lựa chọn dịch vụ như PostgreSQL small hoặc PostgreSQL production. Trong thời gian sử dụng, nhà cung cấp có thể phát hành phiên bản mới của engine, bản vá bảo mật hoặc cấu hình vận hành. Những thay đổi đó có thể cần được áp dụng cho các service instance đã tồn tại.

Nếu broker chỉ công bố catalog ban đầu và không có cách thể hiện phiên bản bảo trì, platform khó nhận biết rằng plan đang có một phiên bản bảo trì mới. Broker cũng cần một cách thống nhất để nhận yêu cầu bảo trì mà không phải biến mỗi bản vá thành một service plan mới.

`maintenance_info` cung cấp metadata bảo trì gắn với plan. Metadata này giúp platform biết phiên bản bảo trì mà broker hiện công bố. Khi có yêu cầu bảo trì, platform có thể chuyển thông tin phiên bản mục tiêu tới broker thông qua request update nếu các thành phần trong hệ thống hỗ trợ.

Ví dụ, plan PostgreSQL production có thể công bố:

~~~json
{
  "id": "postgres-production-plan-id",
  "name": "production",
  "description": "PostgreSQL production",
  "maintenance_info": {
    "version": "2026.11.2",
    "description": "Bản vá bảo mật và cập nhật minor PostgreSQL"
  }
}
~~~

Trong ví dụ, `2026.11.2` là mã phiên bản bảo trì do broker quản lý. Nó có thể biểu diễn bản vá, phiên bản engine hoặc một đợt bảo trì đã được kiểm thử. Broker cần quy định rõ ý nghĩa của version trong sản phẩm của mình.

`maintenance_info` là metadata mô tả phiên bản bảo trì. Việc thay đổi metadata trong catalog không tự động nâng cấp database, restart workload hay thay đổi tài nguyên provider. Hoạt động trên instance chỉ diễn ra khi platform gửi yêu cầu phù hợp và broker thực thi thành công.

## 2. Vị trí của maintenance_info trong catalog

Trong OSB API, `maintenance_info` được gắn với service plan. Một service có thể có nhiều plan, và mỗi plan có thể công bố thông tin bảo trì riêng.

Ví dụ catalog rút gọn:

~~~json
{
  "services": [
    {
      "id": "postgres-service-id",
      "name": "postgresql",
      "description": "Dịch vụ cơ sở dữ liệu PostgreSQL",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "postgres-small-plan-id",
          "name": "small",
          "description": "Gói nhỏ",
          "maintenance_info": {
            "version": "2026.11.2",
            "description": "Bản vá bảo mật PostgreSQL"
          }
        },
        {
          "id": "postgres-production-plan-id",
          "name": "production",
          "description": "Gói production",
          "maintenance_info": {
            "version": "2026.11.2",
            "description": "Bản vá bảo mật và cập nhật minor"
          }
        }
      ]
    }
  ]
}
~~~

Các trường có ý nghĩa:

| Trường | Ý nghĩa |
|---|---|
| `maintenance_info` | Metadata mô tả phiên bản bảo trì của plan |
| `maintenance_info.version` | Mã phiên bản bảo trì do broker công bố |
| `maintenance_info.description` | Mô tả ngắn nội dung hoặc mục tiêu của phiên bảo trì |

Version cần được quản lý ổn định và có ý nghĩa trong phạm vi plan. Description giúp người vận hành hiểu thay đổi, nhưng không nên chứa thông tin nội bộ nhạy cảm hoặc chi tiết khai thác lỗ hổng.

Không nên dùng tên hiển thị của plan làm mã phiên bản bảo trì. Plan ID nhận diện gói dịch vụ; maintenance version nhận diện trạng thái bảo trì của gói đó. Hai giá trị có vòng đời khác nhau.

## 3. Phân biệt bảo trì với thay đổi plan

Bảo trì và thay đổi plan đều có thể đi qua luồng update service instance, nhưng mục đích của chúng khác nhau.

| Tiêu chí | Bảo trì qua maintenance_info | Thay đổi plan |
|---|---|---|
| Mục tiêu | Áp dụng phiên bản hoặc bản vá bảo trì | Thay đổi mức dịch vụ hoặc cấu hình tài nguyên |
| Service ID | Thường giữ nguyên | Thường giữ nguyên trong cùng service |
| Plan ID | Có thể giữ nguyên | Thay đổi sang plan khác |
| Ví dụ | Nâng PostgreSQL từ bản minor cũ lên bản đã vá | Chuyển từ plan small sang production |
| Metadata chính | Maintenance version | Plan ID đích và parameters |
| Tác động tài nguyên | Phụ thuộc nội dung bảo trì | Thường thay đổi theo đặc tính plan |

Một instance PostgreSQL production có thể vẫn ở plan production sau khi được cập nhật engine. Khi đó plan ID không cần thay đổi; thông tin bảo trì đã áp dụng được cập nhật từ phiên bản cũ sang phiên bản mới.

Ngược lại, nếu người dùng muốn tăng CPU, memory hoặc storage theo một plan khác, đó là thay đổi plan. Broker cần xử lý theo quy tắc update plan và kiểm tra quota tương ứng.

Không nên dùng việc tạo plan mới cho mọi bản vá. Làm như vậy sẽ khiến catalog tăng nhanh, làm phức tạp lựa chọn của người dùng và gây khó khăn cho việc quản lý các instance đã tồn tại.

## 4. Điều kiện tương thích giữa OSB API, framework và platform

`maintenance_info` chỉ hữu ích khi toàn bộ đường đi hỗ trợ nó. Cần kiểm tra ba lớp:

1. Phiên bản OSB API mà platform và broker sử dụng có định nghĩa trường maintenance_info trong catalog và request update tương ứng hay không.
2. Phiên bản Spring Cloud Open Service Broker đang dùng có model và cơ chế binding để đọc, công bố metadata bảo trì hay không.
3. Platform có hiểu metadata đó và có cơ chế gửi yêu cầu update bảo trì hay không.

Header `X-Broker-API-Version` cho biết phiên bản API mà client sử dụng theo hợp đồng OSB. Không nên giả định chỉ cần thêm một thuộc tính vào YAML là platform cũ sẽ hiểu hoặc gửi nó trong request.

### 4.1. Kiểm tra khả năng của framework

Trước khi triển khai, kiểm tra tài liệu và API của đúng phiên bản Spring Cloud Open Service Broker trong dự án:

- Model plan có trường maintenance info hay không.
- Builder hoặc constructor của plan có cách thiết lập maintenance info hay không.
- Model update request có cung cấp maintenance info cho handler hay không.
- Framework serialize metadata vào catalog và deserialize trường trong update request như thế nào.
- Có giới hạn hoặc khác biệt nào giữa các phiên bản thư viện không.

Tên class và builder method có thể thay đổi theo phiên bản thư viện. Không nên sao chép ví dụ từ một release khác mà chưa xác nhận API thực tế.

### 4.2. Kiểm tra khả năng của platform

Platform có thể hỗ trợ OSB API ở mức cơ bản nhưng chưa chắc đã triển khai luồng bảo trì. Cần xác nhận:

- Platform có đọc maintenance_info từ catalog hay không.
- Platform lưu hoặc so sánh phiên bản bảo trì nào cho mỗi instance.
- Platform có thể gửi maintenance_info trong request update hay không.
- Người vận hành có thể chủ động yêu cầu bảo trì hoặc đặt lịch hay không.
- Platform xử lý update bất đồng bộ và last_operation ra sao.
- Có chính sách downtime, retry và thông báo người dùng nào được platform áp dụng hay không.

Không nên giả định mọi platform tự động gọi update ngay khi catalog có version mới. Cách platform sử dụng metadata, hiển thị cảnh báo hoặc điều phối bảo trì phụ thuộc implementation của platform và chính sách vận hành.

### 4.3. Kiểm thử hợp đồng trước khi bật

Nên kiểm thử trên môi trường staging bằng một plan và instance thử nghiệm. Xác nhận catalog trả đúng metadata, platform gửi đúng request, broker nhận được đúng version mục tiêu và handler thực hiện đúng thao tác.

Nếu một thành phần không hỗ trợ trường này, cần dùng quy trình bảo trì riêng phù hợp với platform đó. Không được trả thành công giả cho một request mà broker không hiểu hoặc không thể thực hiện.

## 5. Khai báo maintenance_info trong cấu hình

Có thể quản lý phiên bản bảo trì cùng cấu hình catalog của ứng dụng. Ví dụ một namespace nội bộ:

~~~yaml
broker:
  catalog:
    services:
      - id: postgres-service-id
        name: postgresql
        description: Dịch vụ cơ sở dữ liệu PostgreSQL
        bindable: true
        plan-updateable: true
        plans:
          - id: postgres-production-plan-id
            name: production
            description: Gói PostgreSQL production
            maintenance-info:
              version: "2026.11.2"
              description: "Bản vá bảo mật PostgreSQL"
~~~

Đây là cấu trúc YAML do ứng dụng lựa chọn để lưu cấu hình. OSB API dùng tên trường JSON `maintenance_info`; Spring Boot có thể bind tên YAML `maintenance-info` vào thuộc tính Java theo quy tắc relaxed binding.

Một lớp cấu hình có thể biểu diễn metadata này:

~~~java
public record MaintenanceInfoConfig(
        String version,
        String description) {
}

public record PlanConfig(
        String id,
        String name,
        String description,
        MaintenanceInfoConfig maintenanceInfo) {
}
~~~

Ví dụ là cấu trúc DTO minh họa. Ứng dụng cần đăng ký và bind các lớp bằng `@ConfigurationProperties` theo namespace đang sử dụng, đồng thời validate version trước khi công bố catalog.

Không nên đưa thông tin tiến độ của từng instance vào catalog. Catalog mô tả phiên bản bảo trì mục tiêu của plan; trạng thái instance đã áp dụng phiên bản nào phải được lưu riêng trong dữ liệu service instance.

## 6. Chuyển metadata thành plan của Spring Cloud Open Service Broker

Sau khi cấu hình được bind, CatalogService hoặc adapter của broker chuyển DTO sang model catalog của framework.

Ở các phiên bản thư viện có model maintenance info, logic chuyển đổi có thể được tổ chức theo dạng:

~~~java
// Ví dụ minh họa; đối chiếu tên model và builder
// với phiên bản Spring Cloud Open Service Broker đang dùng.

MaintenanceInfo maintenanceInfo = MaintenanceInfo.builder()
        .version(planConfig.maintenanceInfo().version())
        .description(planConfig.maintenanceInfo().description())
        .build();

Plan plan = Plan.builder()
        .id(planConfig.id())
        .name(planConfig.name())
        .description(planConfig.description())
        .maintenanceInfo(maintenanceInfo)
        .build();
~~~

Nếu phiên bản framework chưa có model hoặc builder tương ứng, cần kiểm tra khả năng nâng cấp thư viện hoặc dùng adapter tương thích. Không nên tự thêm một JSON field ngoài hợp đồng rồi giả định framework sẽ serialize nó.

Sau khi tạo catalog, kiểm tra response endpoint catalog để xác nhận:

- Plan có đúng ID và tên.
- `maintenance_info.version` có giá trị mong muốn.
- Description phản ánh đúng đợt bảo trì.
- Metadata được trả dưới đúng plan.
- Không có secret, provider credentials hoặc dữ liệu nội bộ nhạy cảm trong response.

Catalog là nguồn công bố trạng thái mục tiêu. Việc instance nào đã nhận bản vá được ghi nhận trong kho dữ liệu của broker.

## 7. Lưu phiên bản bảo trì đã áp dụng cho từng instance

Broker nên lưu phiên bản bảo trì đã áp dụng cho mỗi service instance. Khi catalog chuyển sang version mới, broker có thể xác định instance nào đang ở phiên bản cũ và cần xử lý.

Ví dụ bổ sung các trường vào bản ghi service instance:

| Trường | Mục đích |
|---|---|
| applied_maintenance_version | Version bảo trì đã xác nhận áp dụng trên tài nguyên |
| target_maintenance_version | Version đang được yêu cầu áp dụng |
| maintenance_state | Trạng thái bảo trì hiện tại |
| maintenance_operation_id | ID thao tác bảo trì nội bộ |
| maintenance_started_at | Thời điểm bắt đầu |
| maintenance_completed_at | Thời điểm hoàn tất gần nhất |
| maintenance_error_code | Mã lỗi đã chuẩn hóa nếu thất bại |

Có thể lưu lịch sử trong bảng riêng nếu cần giữ nhiều lần bảo trì:

~~~sql
CREATE TABLE service_instance_maintenance (
    operation_id VARCHAR(255) PRIMARY KEY,
    service_instance_id VARCHAR(255) NOT NULL,
    previous_version VARCHAR(100),
    target_version VARCHAR(100) NOT NULL,
    state VARCHAR(40) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    error_code VARCHAR(100),
    FOREIGN KEY (service_instance_id)
        REFERENCES service_instance(service_instance_id)
);
~~~

Không nên chỉ nhìn version hiện tại trong catalog để kết luận mọi instance đã được cập nhật. Một instance có thể đang bảo trì, bị lỗi, đang chờ lịch hoặc không thể nâng cấp do ràng buộc riêng. Trạng thái thực tế cần được ghi nhận theo từng instance.

Nếu version là chuỗi tùy ý, broker nên so sánh equality với version mục tiêu đã lưu thay vì tự giả định thứ tự từ vựng. Nếu sản phẩm cần so sánh thứ tự, hãy quy định một định dạng version rõ ràng và bộ so sánh phù hợp.

## 8. Tiếp nhận yêu cầu bảo trì qua update

Khi platform gửi request update có maintenance info, handler cần phân biệt yêu cầu bảo trì với yêu cầu thay đổi plan hoặc parameters.

Luồng xử lý tổng quát:

1. Nhận instance ID và nội dung update request.
2. Tra cứu service instance, xác minh tenant và trạng thái hiện tại.
3. Đọc maintenance_info mục tiêu nếu request có trường này.
4. Kiểm tra version mục tiêu có được plan hiện tại công bố và broker hỗ trợ hay không.
5. Kiểm tra instance có đủ điều kiện bảo trì hay không.
6. Tạo maintenance operation và lưu target version.
7. Thực hiện quy trình bảo trì trên provider.
8. Xác minh tài nguyên hoạt động với version mới.
9. Cập nhật applied_maintenance_version và trạng thái instance.
10. Trả response update đồng bộ hoặc bất đồng bộ theo hợp đồng OSB.

Ví dụ request minh họa:

~~~http
PATCH /v2/service_instances/instance-123
Content-Type: application/json
X-Broker-API-Version: <phiên-bản-OSB-API-được-hỗ-trợ>
~~~

~~~json
{
  "service_id": "postgres-service-id",
  "plan_id": "postgres-production-plan-id",
  "maintenance_info": {
    "version": "2026.11.2",
    "description": "Bản vá bảo mật PostgreSQL"
  }
}
~~~

Cấu trúc request thực tế cần khớp với phiên bản OSB API và framework. Đặc biệt, không được giả định mọi bản Spring Cloud Open Service Broker đều bind trường maintenance_info giống nhau.

Handler nên xác định rõ các trường hợp:

- Request không có maintenance_info: xử lý update thông thường theo hợp đồng.
- Request có version hiện đã áp dụng: trả kết quả phù hợp với thao tác đã hoàn tất, tránh chạy lại bảo trì.
- Request có version mục tiêu hợp lệ và mới: bắt đầu hoặc tiếp tục maintenance operation.
- Request có version không được plan công bố: từ chối với lỗi có thể giải thích.
- Instance đang chạy một maintenance operation khác: không khởi tạo thao tác xung đột.

## 9. Phân tách logic update plan và maintenance

Một request update có thể liên quan tới thay đổi plan, parameters hoặc maintenance. Broker cần xác định những thay đổi nào được yêu cầu và hỗ trợ.

Ví dụ:

| Plan ID hiện tại | Plan ID yêu cầu | Maintenance version | Diễn giải |
|---|---|---|---|
| production | production | version mới | Bảo trì trên cùng plan |
| small | production | không có | Nâng plan |
| small | small | không có | Update parameters trên cùng plan |
| small | production | version mới | Có thể gồm nâng plan và bảo trì; phải xác định thứ tự và hỗ trợ rõ |

Nếu một request kết hợp nhiều loại thay đổi, broker cần xác định thứ tự thực hiện và cách bù trừ. Ví dụ nâng compute thành công nhưng bảo trì engine thất bại; broker phải lưu trạng thái từng bước và không ghi nhận toàn bộ request thành công.

Trong nhiều hệ thống, tách riêng thao tác nâng plan và bảo trì giúp giảm độ phức tạp. Nếu OSB request có nhiều trường thay đổi, handler vẫn phải xác định đầy đủ ý nghĩa và không bỏ qua một thay đổi đã được yêu cầu.

## 10. Thiết kế quy trình bảo trì an toàn

Bảo trì có thể gây downtime, ảnh hưởng kết nối hoặc làm thay đổi trạng thái dữ liệu. Broker nên kiểm tra điều kiện trước khi bắt đầu.

Các bước thường cần có:

- Xác minh instance đang ACTIVE và không có operation xung đột.
- Kiểm tra version mục tiêu được hỗ trợ cho plan và provider hiện tại.
- Kiểm tra cửa sổ bảo trì hoặc chính sách downtime nếu hệ thống có quy định.
- Kiểm tra dung lượng, backup, replica và điều kiện nâng cấp.
- Thông báo hoặc phối hợp với platform theo khả năng tích hợp.
- Tạo operation record trước khi gọi provider.
- Thực hiện backup hoặc snapshot khi quy trình yêu cầu.
- Áp dụng bản vá hoặc nâng cấp theo từng bước.
- Kiểm tra health, connectivity và dữ liệu sau bảo trì.
- Chỉ cập nhật applied version sau khi xác minh thành công.

Ví dụ state machine nội bộ:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> MAINTENANCE_REQUESTED
    MAINTENANCE_REQUESTED --> PRECHECK
    PRECHECK --> BACKUP
    PRECHECK --> FAILED
    BACKUP --> APPLYING
    BACKUP --> FAILED
    APPLYING --> VERIFYING
    APPLYING --> FAILED
    VERIFYING --> ACTIVE: Xác minh thành công
    VERIFYING --> FAILED: Xác minh thất bại
    FAILED --> PRECHECK: Retry hoặc phục hồi
    ACTIVE --> [*]
~~~

Tên trạng thái là mô hình nội bộ minh họa. Có thể bổ sung WAITING_FOR_WINDOW, ROLLING_BACK hoặc NEEDS_OPERATOR nếu quy trình thực tế cần. Điều quan trọng là không chuyển instance về ACTIVE trước khi provider đã đạt trạng thái sẵn sàng.

## 11. Bảo trì bất đồng bộ và last_operation

Nâng cấp database, thay đổi cluster hoặc cập nhật image có thể mất nhiều phút. Nếu platform cho phép thao tác bất đồng bộ, broker có thể chấp nhận request, lưu operation và trả trạng thái đang xử lý.

Trong thời gian bảo trì:

- Giữ maintenance operation và target version trong kho trạng thái bền vững.
- Không cho phép một operation update khác xung đột trên cùng instance.
- Theo dõi provider operation ID nếu nhà cung cấp có trả về.
- Cập nhật tiến độ và trạng thái lỗi trong broker.
- Trả trạng thái qua last_operation theo hợp đồng OSB.
- Khi hoàn tất, xác minh provider và cập nhật applied version.

Một bảng trạng thái minh họa:

| Trạng thái operation | Ý nghĩa |
|---|---|
| ACCEPTED | Broker đã nhận yêu cầu |
| PRECHECK | Đang kiểm tra điều kiện |
| BACKUP_IN_PROGRESS | Đang sao lưu hoặc tạo snapshot |
| APPLYING | Đang áp dụng bản vá |
| VERIFYING | Đang kiểm tra sau bảo trì |
| SUCCEEDED | Bảo trì hoàn tất và đã xác minh |
| FAILED | Bảo trì thất bại |
| RECOVERY_REQUIRED | Cần quy trình phục hồi hoặc người vận hành can thiệp |

Nếu platform không chấp nhận bất đồng bộ, broker phải xử lý đồng bộ trong giới hạn phù hợp hoặc phản hồi theo quy tắc OSB. Không được trả thành công trong khi thao tác vẫn đang chạy.

## 12. Idempotency và retry khi bảo trì

Platform có thể retry update do timeout hoặc mất kết nối. Provider cũng có thể trả timeout dù thao tác bảo trì đã bắt đầu. Broker cần tránh chạy cùng một bản vá nhiều lần hoặc cập nhật sai version.

Một khóa idempotency có thể kết hợp:

~~~text
service_instance_id + operation_type + target_maintenance_version
~~~

Ví dụ:

~~~text
instance-123:MAINTENANCE:2026.11.2
~~~

Với cùng instance và target version:

- Nếu operation đã SUCCEEDED, trả kết quả phù hợp mà không chạy lại.
- Nếu operation đang chạy, tiếp tục theo dõi operation hiện tại.
- Nếu operation thất bại ở bước có thể retry, tiếp tục từ trạng thái phục hồi được.
- Nếu version đã áp dụng trên provider nhưng broker chưa ghi nhận, đối soát provider trước khi chạy lại.
- Nếu request mới yêu cầu version khác trong khi operation cũ đang chạy, xử lý theo chính sách xung đột thay vì chạy song song.

Provider idempotency key nên được dùng nếu API hỗ trợ. Nếu không, broker cần lưu operation ID, tag hoặc metadata để tìm trạng thái thực tế của tài nguyên trước khi gửi lệnh lặp.

Không nên coi mọi lỗi timeout là thất bại chắc chắn. Timeout chỉ cho biết broker chưa nhận được kết quả trong thời gian chờ. Provider có thể vẫn đang thực hiện bảo trì. Trước khi retry lệnh có tác dụng phụ, hãy truy vấn trạng thái operation hoặc tài nguyên.

## 13. Rollback và phục hồi khi bảo trì thất bại

Không phải mọi bản vá đều có thể rollback. Một số nâng cấp database có thay đổi format dữ liệu hoặc schema nội bộ khiến việc quay lại phiên bản cũ không an toàn.

Trước khi bảo trì, cần xác định:

- Có thể rollback phần mềm hay không.
- Snapshot/backup có thể phục hồi về thời điểm nào.
- Có cần migration dữ liệu hoặc format chuyển đổi hay không.
- Nếu chỉ một node trong cluster được nâng cấp, cách xử lý các node còn lại ra sao.
- Khi không thể rollback, instance sẽ ở trạng thái nào và cần can thiệp gì.

Nếu bảo trì thất bại, broker không nên cập nhật applied_maintenance_version thành version mục tiêu. Có thể giữ version cũ nếu provider xác nhận tài nguyên đã quay lại phiên bản cũ; nếu trạng thái không rõ, đánh dấu UNKNOWN hoặc RECOVERY_REQUIRED và ngăn các thao tác không an toàn.

Bản ghi operation nên lưu bước cuối cùng đã hoàn thành, provider operation ID, lỗi đã chuẩn hóa và thông tin phục hồi cần thiết. Không lưu nội dung secret hoặc log provider chứa dữ liệu nhạy cảm vào trường lỗi.

## 14. Bảo trì có kiểm soát downtime và rolling maintenance

Một số backing service có thể nâng cấp mà không dừng toàn bộ dịch vụ. Ví dụ cluster database có nhiều node hoặc service có replica. Broker có thể phối hợp với provider để thực hiện rolling maintenance theo từng node.

Một quy trình rolling có thể gồm:

1. Xác định node hoặc replica đủ điều kiện nâng cấp.
2. Kiểm tra replica còn lại có khả năng phục vụ.
3. Nâng cấp một node hoặc chuyển vai trò primary theo quy trình provider.
4. Kiểm tra replication lag và health.
5. Tiếp tục với node kế tiếp.
6. Xác minh toàn cluster đã ở version mục tiêu.

Không phải provider nào cũng hỗ trợ rolling upgrade hoặc zero downtime. Broker cần công bố đúng đặc tính của dịch vụ và không hứa hẹn thời gian gián đoạn bằng 0 nếu nhà cung cấp không bảo đảm.

Nếu cần maintenance window, broker có thể lưu trạng thái WAITING_FOR_WINDOW hoặc platform có thể quản lý lịch bên ngoài. Việc lên lịch và gửi request phải tuân theo khả năng thật của platform; trường maintenance_info tự nó không phải bộ lập lịch.

## 15. Ví dụ handler bảo trì trong Spring Cloud

Ở tầng ứng dụng, có thể tách phần nhận request OSB và service nghiệp vụ bảo trì. Handler đọc thông tin request, còn MaintenanceService chịu trách nhiệm kiểm tra, lưu operation và gọi provider.

Ví dụ mã giả:

~~~java
public Mono<UpdateServiceInstanceResponse> updateServiceInstance(
        UpdateServiceInstanceRequest request) {

    var maintenanceInfo = request.getMaintenanceInfo();

    if (maintenanceInfo != null) {
        return maintenanceService.apply(
                        request.getServiceInstanceId(),
                        maintenanceInfo.getVersion())
                .map(result -> UpdateServiceInstanceResponse.builder()
                        .build());
    }

    return planUpdateService.update(request)
            .map(result -> UpdateServiceInstanceResponse.builder()
                    .build());
}
~~~

Đây là cấu trúc minh họa, không phải chữ ký có thể dùng nguyên trạng cho mọi release. Cần kiểm tra interface, kiểu response, model maintenance info và khả năng hỗ trợ của phiên bản Spring Cloud Open Service Broker trong dự án.

MaintenanceService nên thực hiện các trách nhiệm:

- Tra cứu instance và xác minh quyền sở hữu.
- Xác minh version mục tiêu có được công bố cho plan hiện tại.
- Kiểm tra instance không có operation xung đột.
- Tạo operation bền vững với khóa idempotency.
- Gọi provider adapter để thực hiện bảo trì.
- Theo dõi operation bất đồng bộ nếu có.
- Xác minh tài nguyên và cập nhật applied version.
- Chuyển lỗi sang response hoặc last_operation theo hợp đồng OSB.

Không nên đặt toàn bộ logic backup, upgrade, polling và rollback trong method handler. Tách lớp giúp kiểm thử và thay provider dễ dàng hơn.

## 16. Quản lý nhiều plan và nhiều provider

Một service broker có thể hỗ trợ PostgreSQL từ nhiều nhà cung cấp hoặc nhiều loại triển khai. Cùng một maintenance version không nhất thiết áp dụng cho mọi provider.

Ví dụ:

| Service plan | Provider | Maintenance version | Nội dung |
|---|---|---|---|
| PostgreSQL production | Provider A | 2026.11.2-a | Bản vá engine theo lịch A |
| PostgreSQL production | Provider B | 16.4-r3 | Cập nhật minor theo lịch B |
| PostgreSQL small | Kubernetes operator | 16.4-operator-2 | Cập nhật image và operator |

Nếu cùng service plan được phục vụ từ nhiều provider, broker cần quyết định metadata catalog được công bố theo cách nào. Có thể tách service hoặc plan theo provider nếu người dùng cần lựa chọn rõ; hoặc giữ một plan thống nhất nhưng broker phải xác định chính sách version mục tiêu theo provider của từng instance.

Không được áp dụng version của provider A cho instance đang chạy ở provider B nếu hai hệ thống dùng quy ước version khác nhau. Provider adapter nên chịu trách nhiệm kiểm tra khả năng nâng cấp và chuyển version mục tiêu sang lệnh cụ thể.

## 17. Bảo mật và kiểm soát quyền bảo trì

Bảo trì có thể thay đổi engine, restart service hoặc ảnh hưởng dữ liệu. Đây là thao tác có mức tác động cao, nên broker cần xác minh request và giới hạn quyền.

Các nguyên tắc cần áp dụng:

- Chỉ chấp nhận request từ platform đã xác thực.
- Kiểm tra tenant ownership và instance ID.
- Chỉ áp dụng version được broker công bố hoặc cho phép theo chính sách.
- Không cho client tùy ý gửi version provider chưa được kiểm thử.
- Lưu audit về ai hoặc platform nào yêu cầu, instance nào và version nào.
- Bảo vệ provider credentials và secret trong quá trình gọi API.
- Không ghi dữ liệu nhạy cảm vào log hoặc response lỗi.
- Giới hạn quyền của service account dùng để thực hiện maintenance.

Nếu tổ chức có quy trình phê duyệt bảo trì, có thể yêu cầu approval ở platform hoặc workflow quản trị trước khi gửi update. Không nên mặc định mọi client có quyền provision đều có quyền yêu cầu bảo trì production.

## 18. Lỗi thường gặp khi triển khai maintenance_info

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Catalog không trả maintenance_info | Framework model hoặc mapper chưa hỗ trợ | Kiểm tra phiên bản và mapping catalog |
| Platform không nhận ra version mới | Platform hoặc API version chưa hỗ trợ trường này | Kiểm tra header và khả năng OSB client |
| Update request không có maintenance_info | Platform chưa triển khai luồng bảo trì hoặc request không đúng contract | Kiểm tra request thực tế và tài liệu platform |
| Broker nhận version không hợp lệ | Client gửi version không được plan công bố | Validate version tại broker |
| Bảo trì chạy lặp sau timeout | Không có idempotency hoặc không tra cứu operation cũ | Dùng khóa theo instance và target version |
| Catalog có version mới nhưng instance chưa cập nhật | Chỉ thay đổi metadata, chưa có request bảo trì | Điều phối update theo khả năng platform |
| Broker báo thành công nhưng provider vẫn ở version cũ | Cập nhật trạng thái trước khi xác minh | Chỉ commit applied version sau health check |
| Update plan bị nhầm thành maintenance | Handler không phân biệt thay đổi plan và maintenance | Tách logic theo dữ liệu request |
| Provider timeout nhưng broker retry tạo thao tác thứ hai | Không kiểm tra trạng thái operation provider | Lưu provider operation ID và reconciliation |
| Bảo trì thất bại nhưng applied version đã đổi | Ghi version mục tiêu quá sớm | Lưu target riêng, chỉ commit sau thành công |
| Instance bị thao tác update đồng thời | Không khóa hoặc kiểm tra state transition | Dùng optimistic locking hoặc operation lock |

## 19. Quy trình phát hành một phiên bản bảo trì

Khi cần phát hành maintenance version mới, có thể thực hiện theo trình tự:

1. Xác định plan và các provider bị ảnh hưởng.
2. Xác định version mục tiêu và ý nghĩa của version.
3. Kiểm thử bản vá trên môi trường thử nghiệm.
4. Xác định điều kiện tương thích, downtime, backup và rollback.
5. Cập nhật maintenance_info trong catalog.
6. Xác minh catalog response và platform có thể đọc metadata.
7. Điều phối platform gửi yêu cầu update theo lịch hoặc quy trình quản trị.
8. Broker kiểm tra instance và version mục tiêu.
9. Thực hiện bảo trì đồng bộ hoặc bất đồng bộ.
10. Xác minh provider, cập nhật applied version và hoàn tất operation.
11. Theo dõi lỗi, instance chưa cập nhật và các operation đang chờ.
12. Lưu audit và đóng đợt bảo trì khi đạt tiêu chí hoàn tất.

Nên phát hành theo nhóm instance hoặc theo tenant nếu provider hỗ trợ. Việc triển khai từng đợt giúp quan sát lỗi sớm và giới hạn phạm vi ảnh hưởng. Catalog có thể công bố version mục tiêu trước, nhưng thời điểm và tốc độ áp dụng cần được điều phối phù hợp với platform và chính sách vận hành.

## 20. Checklist triển khai

- [ ] Đã xác nhận OSB API version của platform và broker hỗ trợ maintenance_info.
- [ ] Phiên bản Spring Cloud Open Service Broker có model và binding cần thiết.
- [ ] Platform có khả năng đọc catalog và gửi maintenance_info trong update request.
- [ ] Catalog công bố version và description đúng ở plan tương ứng.
- [ ] Version được quản lý ổn định và có quy ước so sánh rõ ràng.
- [ ] Broker lưu applied version riêng cho từng service instance.
- [ ] Handler phân biệt bảo trì với thay đổi plan và parameters.
- [ ] Request được kiểm tra quyền sở hữu và version mục tiêu.
- [ ] Maintenance operation được lưu bền vững trước khi gọi provider.
- [ ] Retry không tạo thao tác bảo trì trùng lặp.
- [ ] Provider operation ID được lưu nếu thao tác bất đồng bộ.
- [ ] last_operation phản ánh trạng thái thực tế.
- [ ] Có backup, precheck, health check và quy trình phục hồi phù hợp.
- [ ] Chỉ cập nhật applied version sau khi xác minh thành công.
- [ ] Có audit, metric và báo cáo instance chưa được bảo trì.
- [ ] Đã thử nghiệm trên staging với đúng platform và framework dự kiến triển khai.

`maintenance_info` giúp broker công bố phiên bản bảo trì gắn với service plan và tạo một cách trao đổi mục tiêu bảo trì khi OSB API, framework và platform cùng hỗ trợ. Catalog chỉ thông báo version mục tiêu; broker vẫn phải thực hiện công việc trên tài nguyên thật, lưu trạng thái theo từng instance, xử lý retry và xác minh kết quả. Khi phân biệt rõ bảo trì với thay đổi plan, quản lý version bền vững và điều phối operation an toàn, service broker có thể đưa bản vá và cập nhật vận hành tới các instance đang chạy một cách có kiểm soát.


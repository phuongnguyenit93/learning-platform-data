# Kiểm tra tham số tại broker thay vì chỉ dựa vào kiểm tra của nền tảng

Trong Open Service Broker API (OSB API), platform gửi tham số cấu hình đến service broker khi yêu cầu provision, update hoặc binding. Platform có thể hiển thị biểu mẫu, kiểm tra kiểu dữ liệu và giới hạn giá trị trước khi gửi request. Tuy nhiên, broker vẫn phải tự xác thực mọi dữ liệu nhận được trước khi tạo tài nguyên, thay đổi cấu hình hoặc cấp credential.

Platform là một client bên ngoài ranh giới tin cậy của broker. Request có thể đến từ một platform khác, một phiên bản CLI khác, một công cụ quản trị nội bộ hoặc một client gọi API trực tiếp. Vì vậy, kiểm tra ở giao diện chỉ cải thiện trải nghiệm người dùng; nó không bảo vệ tài nguyên của provider. Broker phải xem dữ liệu đầu vào là không đáng tin cậy, xác thực lại theo service offering, plan, trạng thái instance, chính sách và quyền của caller.

Bài học thuộc module **SPRING_CLOUD_SERVICE_BROKER**. Nội dung tập trung vào cách xây dựng lớp validation phía broker khi triển khai OSB API bằng Spring Cloud Open Service Broker: xác định hợp đồng tham số, kiểm tra kiểu và miền giá trị, kiểm tra quy tắc nghiệp vụ, trả lỗi đúng giao thức, bảo vệ bí mật và kiểm thử các trường hợp sai.

## 1. Vì sao broker phải tự kiểm tra?

Giả sử catalog công bố plan PostgreSQL có giới hạn lưu trữ 10 đến 500 GB. Platform có thể hiển thị một ô nhập dung lượng và chặn người dùng nhập 20.000 GB. Nhưng request HTTP vẫn có thể được gửi thủ công với giá trị vượt giới hạn. Nếu broker tin vào kết quả kiểm tra từ platform, provider có thể tạo tài nguyên quá lớn, vượt quota hoặc phát sinh chi phí không được phép.

Có nhiều nguyên nhân khiến dữ liệu đến broker không hợp lệ:

- Client không dùng giao diện marketplace, hoặc gọi trực tiếp endpoint OSB API.
- Platform và broker triển khai các phiên bản schema khác nhau.
- Người dùng thay đổi request sau khi giao diện đã kiểm tra.
- Dữ liệu bị sửa bởi script, automation hoặc integration trung gian.
- Tham số hợp lệ về cú pháp nhưng vi phạm chính sách của plan hoặc trạng thái instance.
- Caller gửi thêm field ngoài hợp đồng nhằm khai thác lỗi xử lý hoặc truyền dữ liệu không được phép.
- Một request cũ được phát lại sau khi chính sách hoặc trạng thái tài nguyên đã thay đổi.

Vì thế, broker cần có một ranh giới xác thực độc lập. Luồng xử lý đúng là: nhận request, xác thực danh tính và quyền, kiểm tra cấu trúc, kiểm tra tham số theo hợp đồng, kiểm tra quy tắc nghiệp vụ và trạng thái, rồi mới gọi provider hoặc đưa thao tác vào hàng đợi.

~~~mermaid
flowchart TD
    A["Platform gửi request OSB"] --> B["Broker xác thực caller và quyền"]
    B --> C{"Request hợp lệ về cấu trúc?"}
    C -->|"Không"| E["Trả lỗi OSB API"]
    C -->|"Có"| D["Kiểm tra tham số theo schema và kiểu"]
    D --> F{"Tham số hợp lệ?"}
    F -->|"Không"| E
    F -->|"Có"| G["Kiểm tra plan, quota, trạng thái và chính sách"]
    G --> H{"Được phép thực hiện?"}
    H -->|"Không"| E
    H -->|"Có"| I["Ghi nhận operation / trạng thái"]
    I --> J["Gọi provider hoặc enqueue công việc"]
~~~

Validation phải xảy ra trước mọi side effect. Nếu broker đã tạo database rồi mới phát hiện tên database không hợp lệ, việc khôi phục sẽ phức tạp và có thể để lại tài nguyên mồ côi.

## 2. Những loại tham số trong OSB API

Không phải mọi dữ liệu trong request đều có cùng ý nghĩa. Cần phân biệt tham số cấu hình do người dùng gửi với định danh và ngữ cảnh do platform cung cấp.

| Nhóm dữ liệu | Ví dụ | Cách broker xử lý |
|---|---|---|
| Tham số service instance | database name, storage size, region, backup | Kiểm tra theo schema và chính sách của service/plan |
| Tham số update | dung lượng mới, retention, cấu hình có thể thay đổi | Kiểm tra khả năng update, giới hạn và trạng thái hiện tại |
| Tham số binding | tên consumer, quyền truy cập, scope hoặc role yêu cầu | Kiểm tra theo hợp đồng binding và quyền của consumer |
| Định danh OSB | service_id, plan_id, instance_id, binding_id | Tra cứu từ catalog và dữ liệu vòng đời; không xem là dữ liệu cấu hình tùy ý |
| Ngữ cảnh platform | organization_guid, space_guid, context, app_guid | Xác thực nguồn và kiểm tra quyền, không dùng như bằng chứng ủy quyền độc lập |
| Dữ liệu nội bộ | provider resource ID, operation ID, trạng thái lưu trữ | Broker tự quản lý; không cho caller ghi đè trực tiếp |

Trong OSB API, trường **parameters** thường là một JSON object chứa tham số riêng của service broker. Cấu trúc cụ thể phụ thuộc vào offering, plan và thao tác. Một tham số có thể hợp lệ trong lúc provision nhưng không được phép thay đổi khi update. Tham số binding cũng có hợp đồng riêng, không nên dùng chung một allowlist với tham số provision.

Các trường như **service_id** và **plan_id** không thay thế việc xác thực quyền. Việc request chứa một plan ID có thật không có nghĩa caller được phép sử dụng plan đó trong organization hoặc tenant đang gọi broker. Broker phải tra cứu plan và kiểm tra quyền theo dữ liệu đáng tin cậy của mình.

## 3. Schema trong catalog giúp platform, nhưng không thay validation ở broker

OSB API cho phép broker công bố schema tham số trong catalog để platform xây dựng biểu mẫu và hỗ trợ kiểm tra trước khi gửi request. Schema có thể mô tả kiểu dữ liệu, field bắt buộc, miền giá trị và cấu trúc object.

Ví dụ minh họa schema JSON cho tham số tạo service instance:

~~~json
{
  "schemas": {
    "service_instance": {
      "create": {
        "parameters": {
          "type": "object",
          "additionalProperties": false,
          "required": ["databaseName", "storageGb"],
          "properties": {
            "databaseName": {
              "type": "string",
              "minLength": 3,
              "maxLength": 63,
              "pattern": "^[a-z][a-z0-9_]*$"
            },
            "storageGb": {
              "type": "integer",
              "minimum": 10,
              "maximum": 500
            },
            "region": {
              "type": "string",
              "enum": ["ap-southeast-1", "ap-southeast-2"]
            },
            "backupEnabled": {
              "type": "boolean",
              "default": false
            }
          }
        }
      }
    }
  }
}
~~~

Schema có thể giúp platform biết rằng database name phải là chuỗi, dung lượng là số nguyên và region chỉ được chọn trong danh sách cho phép. Tuy nhiên, broker không được giả định rằng mọi client đã đọc schema hoặc thực thi schema chính xác.

Một số quy tắc còn phụ thuộc vào trạng thái tại thời điểm request:

- Quota còn lại của organization hoặc tenant.
- Giới hạn dung lượng riêng của plan đã chọn.
- Region được phép theo tài khoản hoặc vị trí triển khai.
- Khả năng cung cấp tài nguyên hiện tại của provider.
- Trạng thái service instance và những thuộc tính không được phép thay đổi.
- Quyền của caller đối với service instance hoặc application.

Những quy tắc này không thể được bảo đảm chỉ bằng schema tĩnh trong catalog. Broker phải kiểm tra lại trên server tại thời điểm xử lý request.

## 4. Thiết kế validation theo nhiều lớp

Một lớp validation dễ bảo trì nên tách thành các lớp kiểm tra có mục tiêu rõ ràng. Không nên gom toàn bộ logic vào controller hoặc gọi provider trước khi kiểm tra xong.

| Lớp kiểm tra | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Cấu trúc request | Body có đúng dạng object và có field cần thiết không? | parameters phải là JSON object |
| Allowlist | Có field nào ngoài hợp đồng không? | Reject adminMode hoặc providerEndpoint |
| Kiểu dữ liệu | Giá trị có đúng kiểu không? | storageGb phải là số nguyên, backupEnabled phải là boolean |
| Ràng buộc field | Giá trị có nằm trong miền cho phép không? | databaseName đúng pattern, storageGb trong khoảng |
| Ràng buộc liên trường | Các giá trị có hợp lệ khi kết hợp không? | backupEnabled=true thì retention phải được cung cấp |
| Quy tắc plan | Giá trị có phù hợp với plan đã chọn không? | Plan small không được yêu cầu 500 GB |
| Quy tắc trạng thái | Thao tác có được phép ở trạng thái hiện tại không? | Không update instance đang deprovision |
| Quyền và quota | Caller có quyền và còn hạn mức không? | Organization chưa vượt quota database |
| Kiểm tra provider | Provider có hỗ trợ lựa chọn đó không? | Region còn khả dụng, engine version được hỗ trợ |

Có thể triển khai theo thứ tự:

1. Xác thực request và danh tính caller.
2. Kiểm tra service ID, plan ID và instance ID có tồn tại, thuộc đúng phạm vi.
3. Kiểm tra cấu trúc, field được phép, kiểu dữ liệu và giá trị.
4. Nạp chính sách của plan và quota hiện tại từ nguồn dữ liệu tin cậy.
5. Kiểm tra quy tắc liên trường, trạng thái và quyền.
6. Tạo đối tượng tham số đã chuẩn hóa (validated parameters).
7. Chỉ sau đó mới ghi nhận operation và gọi provider.

Đối tượng đã xác thực nên là một kiểu dữ liệu riêng. Các lớp tích hợp provider nhận kiểu này thay vì nhận trực tiếp Map thô từ request. Cách tổ chức đó giảm nguy cơ một nhánh code quên validation rồi truyền dữ liệu không đáng tin cậy xuống provider.

## 5. Kiểm tra allowlist, kiểu dữ liệu và miền giá trị

Giả sử broker cung cấp PostgreSQL với các tham số provision sau:

| Tham số | Bắt buộc | Kiểu | Quy tắc |
|---|---|---|---|
| databaseName | Có | String | 3–63 ký tự, bắt đầu bằng chữ thường, chỉ gồm chữ thường, số và dấu gạch dưới |
| storageGb | Có | Integer | Từ 10 đến giới hạn của plan |
| region | Có | String | Phải nằm trong region được plan và tài khoản cho phép |
| backupEnabled | Không | Boolean | Mặc định false nếu không gửi |
| backupRetentionDays | Có điều kiện | Integer | Bắt buộc khi backupEnabled=true, từ 7 đến 35 ngày |

Broker nên từ chối field lạ. Ví dụ request có **providerAdminPassword** hoặc **skipQuotaCheck** không được âm thầm chấp nhận. Nếu bỏ qua field không biết, client có thể tưởng broker đã áp dụng cấu hình đó trong khi thực tế broker không hiểu field; nếu chuyển nguyên object xuống provider, caller có thể vô tình hoặc cố ý điều khiển các thuộc tính nội bộ.

Cần kiểm tra kiểu dữ liệu thực tế, không chỉ chuyển đổi tự động. Một chuỗi "500" không nên tự động được hiểu là số 500 nếu hợp đồng quy định storageGb là integer. Tương tự, chuỗi "false" không phải boolean false. Việc ép kiểu rộng có thể khiến các client khác nhau tạo ra kết quả không nhất quán.

### Ví dụ validator phía broker

Đoạn mã sau minh họa validator độc lập với HTTP controller và provider. Nó nhận Map từ request, kiểm tra allowlist, kiểu dữ liệu và miền giá trị theo chính sách plan, rồi trả về một record đã được chuẩn hóa.

~~~java
import java.util.ArrayList;
import java.util.Map;
import java.util.Set;

public record ProvisionParameters(
        String databaseName,
        int storageGb,
        String region,
        boolean backupEnabled,
        Integer backupRetentionDays
) {
}

public record PlanLimits(
        int minStorageGb,
        int maxStorageGb,
        Set<String> allowedRegions
) {
}

public final class InvalidParametersException extends RuntimeException {
    private final java.util.List<String> violations;

    public InvalidParametersException(java.util.List<String> violations) {
        super("Provision parameters are invalid");
        this.violations = java.util.List.copyOf(violations);
    }

    public java.util.List<String> getViolations() {
        return violations;
    }
}

public final class ProvisionParameterValidator {

    private static final Set<String> ALLOWED_KEYS = Set.of(
            "databaseName",
            "storageGb",
            "region",
            "backupEnabled",
            "backupRetentionDays"
    );

    public ProvisionParameters validate(
            Map<String, Object> input,
            PlanLimits limits) {

        Map<String, Object> parameters =
                input == null ? Map.of() : input;

        var violations = new ArrayList<String>();

        parameters.keySet().stream()
                .filter(key -> !ALLOWED_KEYS.contains(key))
                .forEach(key -> violations.add(
                        "Unknown parameter: " + key));

        String databaseName = readString(
                parameters, "databaseName", true, violations);
        Integer storageGb = readInteger(
                parameters, "storageGb", true, violations);
        String region = readString(
                parameters, "region", true, violations);
        Boolean backupEnabled = readBoolean(
                parameters, "backupEnabled", false, violations);
        Integer retentionDays = readInteger(
                parameters, "backupRetentionDays", false, violations);

        if (databaseName != null
                && !databaseName.matches("^[a-z][a-z0-9_]{2,62}$")) {
            violations.add(
                    "databaseName must be 3-63 lowercase letters, digits or underscores");
        }

        if (storageGb != null
                && (storageGb < limits.minStorageGb()
                || storageGb > limits.maxStorageGb())) {
            violations.add(
                    "storageGb is outside the selected plan limits");
        }

        if (region != null && !limits.allowedRegions().contains(region)) {
            violations.add("region is not allowed for the selected plan");
        }

        boolean useBackup = Boolean.TRUE.equals(backupEnabled);

        if (useBackup && retentionDays == null) {
            violations.add(
                    "backupRetentionDays is required when backupEnabled is true");
        }

        if (useBackup && retentionDays != null
                && (retentionDays < 7 || retentionDays > 35)) {
            violations.add("backupRetentionDays must be between 7 and 35");
        }

        if (!useBackup && retentionDays != null) {
            violations.add(
                    "backupRetentionDays is only valid when backupEnabled is true");
        }

        if (!violations.isEmpty()) {
            throw new InvalidParametersException(violations);
        }

        return new ProvisionParameters(
                databaseName,
                storageGb,
                region,
                useBackup,
                retentionDays
        );
    }

    private static String readString(
            Map<String, Object> parameters,
            String key,
            boolean required,
            java.util.List<String> violations) {

        Object value = parameters.get(key);

        if (value == null) {
            if (required) {
                violations.add(key + " is required");
            }
            return null;
        }

        if (!(value instanceof String text)) {
            violations.add(key + " must be a string");
            return null;
        }

        if (text.isBlank()) {
            violations.add(key + " must not be blank");
            return null;
        }

        return text;
    }

    private static Integer readInteger(
            Map<String, Object> parameters,
            String key,
            boolean required,
            java.util.List<String> violations) {

        Object value = parameters.get(key);

        if (value == null) {
            if (required) {
                violations.add(key + " is required");
            }
            return null;
        }

        if (!(value instanceof Number number)) {
            violations.add(key + " must be an integer");
            return null;
        }

        long parsed = number.longValue();

        if (number.doubleValue() != parsed
                || parsed < Integer.MIN_VALUE
                || parsed > Integer.MAX_VALUE) {
            violations.add(key + " must be an integer in range");
            return null;
        }

        return (int) parsed;
    }

    private static Boolean readBoolean(
            Map<String, Object> parameters,
            String key,
            boolean defaultValue,
            java.util.List<String> violations) {

        Object value = parameters.get(key);

        if (value == null) {
            return defaultValue;
        }

        if (!(value instanceof Boolean flag)) {
            violations.add(key + " must be a boolean");
            return null;
        }

        return flag;
    }
}
~~~

Đây là ví dụ minh họa phần kiểm tra dữ liệu; trong ứng dụng thật cần bổ sung giới hạn độ dài request, xử lý JSON null rõ ràng, chuẩn hóa chuỗi theo chính sách và kiểm tra chính sách plan được nạp từ nguồn dữ liệu tin cậy. Nếu cần phân biệt field không được gửi với field được gửi rõ ràng bằng null, hãy kiểm tra **containsKey()** thay vì chỉ dựa vào **get()**.

Điểm quan trọng là validator trả về **ProvisionParameters**. Tầng provision nên nhận record này, không nhận lại Map gốc. Như vậy, provider adapter chỉ có thể sử dụng những giá trị đã được kiểm tra và chuẩn hóa.

## 6. Kiểm tra theo plan và theo ngữ cảnh của caller

Một schema chung chỉ mô tả giới hạn tĩnh. Giới hạn thực tế có thể khác nhau theo plan, tenant, organization hoặc môi trường triển khai.

Ví dụ, hai plan cùng chấp nhận storage từ 10 GB nhưng có giới hạn tối đa khác nhau:

| Plan | Storage tối thiểu | Storage tối đa | Region được phép |
|---|---:|---:|---|
| small | 10 GB | 100 GB | ap-southeast-1 |
| standard | 10 GB | 500 GB | ap-southeast-1, ap-southeast-2 |
| enterprise | 10 GB | 2.000 GB | Theo hợp đồng và khu vực triển khai |

Khi nhận request, broker phải tra cứu plan theo **service_id** và **plan_id** đã được xác thực. Không nhận giới hạn tối đa do client gửi lên như một nguồn đáng tin. Đối tượng **PlanLimits** trong ví dụ validator phải được tạo từ cấu hình plan phía broker hoặc từ hệ thống chính sách đã xác thực.

Tương tự, platform có thể gửi **organization_guid**, **space_guid**, **app_guid** hoặc **context**. Các giá trị đó hữu ích để xác định vị trí và chủ thể sử dụng dịch vụ, nhưng broker vẫn cần xác minh quan hệ của chúng với caller đã xác thực. Không nên tin một organization ID chỉ vì nó xuất hiện trong JSON body.

Ví dụ: người dùng của organization A cố gửi organization_guid của organization B để tạo database vào quota của B. Nếu broker chỉ kiểm tra ID có tồn tại mà không kiểm tra caller có quyền trên organization đó, đây là lỗi phân quyền theo đối tượng (BOLA/IDOR). Xác thực danh tính và kiểm tra quyền phải được thực hiện ở phía broker hoặc lớp gateway được tin cậy.

## 7. Gắn validation vào luồng ServiceInstanceService

Trong Spring Cloud Open Service Broker, **ServiceInstanceService** xử lý các thao tác vòng đời service instance. Validation cần được gọi trước khi phần nghiệp vụ gọi provider.

Luồng xử lý provision có thể được tổ chức như sau:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant C as SCOSB Controller
    participant S as ServiceInstanceService
    participant V as ParameterValidator
    participant R as Plan/Quota Repository
    participant Q as Operation Store
    participant H as Provider

    P->>C: PUT /v2/service_instances/{instance_id}
    C->>S: Create request + parameters
    S->>R: Load service, plan, quota and policy
    R-->>S: Trusted plan policy
    S->>V: Validate raw parameters
    alt Validation fails
        V-->>S: Validation violations
        S-->>C: OSB invalid-parameters error
        C-->>P: Error response
    else Validation passes
        V-->>S: ProvisionParameters
        S->>Q: Persist operation and validated input
        S->>H: Provision with validated input
        H-->>S: Provider result / operation
        S-->>C: OSB response
        C-->>P: Success or accepted response
    end
~~~

Pseudocode cho tầng nghiệp vụ:

~~~java
public Mono<ProvisionResult> provision(
        String instanceId,
        String serviceId,
        String planId,
        Map<String, Object> rawParameters,
        AuthenticatedCaller caller) {

    return policyRepository.load(serviceId, planId, caller)
            .switchIfEmpty(Mono.error(
                    new PlanNotAvailableException()))
            .map(policy -> validator.validate(
                    rawParameters, policy.planLimits()))
            .flatMap(validated -> quotaService.checkProvision(
                    caller, serviceId, planId, validated))
            .flatMap(validated -> operationService.startProvision(
                    instanceId, serviceId, planId, validated, caller));
}
~~~

Đoạn pseudocode chỉ thể hiện thứ tự trách nhiệm; kiểu request, response và exception cụ thể cần điều chỉnh theo phiên bản SCOSB đang dùng. Không để provider được gọi trong **map()** hoặc trước bước kiểm tra quota. Nếu bất kỳ validation nào thất bại, luồng phải kết thúc trước khi ghi nhận hoặc tạo tài nguyên.

Với dữ liệu lớn hoặc nhiều bước validation, nên tách các thành phần như **ParameterValidator**, **PlanPolicyRepository**, **QuotaService** và **AuthorizationService**. Mỗi thành phần chịu trách nhiệm cho một loại quy tắc và có thể kiểm thử độc lập.

## 8. Kiểm tra tham số trong update và binding

Không thể áp dụng nguyên xi quy tắc provision cho tất cả thao tác. Mỗi endpoint có ngữ nghĩa khác nhau.

### Update service instance

Update thường chỉ cho phép thay đổi một tập con cấu hình. Ví dụ, broker có thể cho phép tăng storage nhưng không cho phép đổi engine hoặc region sau khi database đã được tạo.

| Tham số | Provision | Update | Lý do |
|---|---|---|---|
| databaseName | Cho phép đặt lúc tạo | Không cho đổi | Định danh tài nguyên đã được provider tạo |
| storageGb | Cho phép trong giới hạn plan | Có thể tăng theo chính sách | Có thể cần migration hoặc mở rộng storage |
| region | Chọn khi tạo | Thường bất biến | Di chuyển vùng là thao tác riêng |
| backupEnabled | Chọn khi tạo | Có thể bật/tắt | Phụ thuộc khả năng provider |
| backupRetentionDays | Chọn khi tạo nếu bật backup | Có thể thay đổi trong giới hạn | Cần kiểm tra quan hệ với backupEnabled |

Khi update, broker cần đọc trạng thái hiện tại và so sánh với giá trị mới. Chỉ kiểm tra từng field độc lập là chưa đủ. Ví dụ, request gửi storageGb=50 có thể hợp lệ theo plan nhưng không hợp lệ nếu instance hiện tại đang ở trạng thái **DELETING**, hoặc nếu provider không cho giảm dung lượng từ 100 GB xuống 50 GB.

Với update có các giá trị trước đó (previous values), không tin các giá trị client tự khai báo để xác định trạng thái thực. Broker nên lấy trạng thái authoritative từ kho dữ liệu của mình và provider khi cần.

### Binding service instance

Tham số binding dùng để tạo quyền truy cập cho một consumer. Ví dụ có thể gồm tên role, database/schema được phép truy cập hoặc scope. Broker cần xác minh:

- Offering có công bố **bindable=true** và broker có hỗ trợ binding.
- Service instance tồn tại và đang ở trạng thái có thể bind.
- Caller có quyền bind instance đó.
- Consumer hoặc app context được xác thực theo nền tảng.
- Tham số chỉ yêu cầu các quyền mà plan và chính sách cho phép.
- Mỗi binding có định danh riêng và có thể thu hồi độc lập.

Không cho client gửi trực tiếp username/password quản trị của provider rồi lưu lại như credential binding. Broker nên tạo credential riêng với quyền tối thiểu thông qua provider, lưu mapping binding ID và chỉ trả thông tin cần thiết cho consumer qua response binding.

## 9. Chuẩn hóa lỗi validation theo OSB API

Khi validation thất bại, broker cần trả lỗi theo hợp đồng OSB API và cơ chế exception mapping của phiên bản Spring Cloud Open Service Broker đang sử dụng. Không nên để lỗi tham số bị biến thành lỗi HTTP 500 chung chung, vì platform sẽ khó phân biệt request không hợp lệ với lỗi nội bộ tạm thời.

Một phản hồi lỗi nên có mô tả đủ để client sửa request nhưng không tiết lộ thông tin nhạy cảm:

~~~json
{
  "description": "Invalid service instance parameters: storageGb is outside the selected plan limits"
}
~~~

Thông báo trên chỉ là ví dụ về nội dung mô tả. Status code và kiểu exception phải tuân theo OSB API version, thao tác đang xử lý và mapping được SCOSB hỗ trợ. Hãy dùng exception chuyên biệt cho lỗi tham số nếu phiên bản framework cung cấp; nếu dùng exception nội bộ, cần có lớp chuyển đổi rõ ràng sang response OSB API tương ứng.

Nên phân biệt các nhóm lỗi:

| Nhóm lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Request sai cấu trúc | parameters là chuỗi thay vì object | Trả lỗi request không hợp lệ |
| Tham số không hợp lệ | storageGb vượt giới hạn plan | Trả lỗi validation có mô tả field |
| Service/plan không khả dụng | plan đã ngừng nhận provision mới | Trả lỗi phù hợp với trạng thái offering/plan |
| Không đủ quyền | Caller không có quyền trên organization hoặc instance | Trả lỗi authorization, tránh tiết lộ tài nguyên của tenant khác |
| Vượt quota | Organization đã dùng hết quota | Trả lỗi nghiệp vụ có thể hành động |
| Provider tạm lỗi | Provider timeout sau khi validation thành công | Xử lý theo cơ chế lỗi/tái thử, không báo sai là tham số không hợp lệ |
| Lỗi lập trình hoặc dữ liệu nội bộ | Null pointer, schema lưu trữ hỏng | Ghi nhận lỗi nội bộ và trả lỗi server phù hợp |

Không trả stack trace, SQL, tên host nội bộ, access token, password hoặc nội dung request chứa bí mật trong response. Có thể trả danh sách field lỗi và mã lỗi nội bộ không nhạy cảm, đồng thời ghi correlation ID để vận hành tra log.

Ví dụ cấu trúc lỗi nội bộ:

~~~java
public record ParameterViolation(
        String field,
        String code,
        String message
) {
}
~~~

Các message cho client nên được chuẩn hóa. Ví dụ, "storageGb exceeds the maximum allowed by the selected plan" hữu ích hơn một thông báo chung "invalid input"; nhưng không cần đưa giá trị quota bí mật hoặc thông tin của tenant khác vào response.

## 10. Validation với thao tác bất đồng bộ và idempotency

Provision hoặc update có thể mất nhiều thời gian. Dù broker trả response bất đồng bộ và xử lý provider trong background, việc kiểm tra đầu vào vẫn phải diễn ra trước khi enqueue operation.

Quy trình gợi ý:

1. Nhận request và xác thực caller.
2. Validate schema, allowlist, kiểu, miền giá trị, plan, quota và quyền.
3. Chuẩn hóa tham số thành đối tượng bất biến.
4. Tạo operation record có trạng thái ban đầu và lưu bản tham số đã xác thực hoặc bản tham chiếu an toàn.
5. Enqueue công việc cho worker.
6. Worker đọc operation, kiểm tra trạng thái và thực thi provider.
7. Nếu chính sách có thể thay đổi giữa lúc enqueue và lúc thực thi, kiểm tra lại những điều kiện cần thiết trước side effect.

Không nên lưu nguyên request có chứa secret vào log hoặc queue không được bảo vệ. Nếu operation cần giữ tham số nhạy cảm để worker sử dụng, phải mã hóa khi lưu, giới hạn quyền đọc và xóa theo chính sách retention.

Idempotency cũng liên quan trực tiếp đến validation. Khi platform gửi lại cùng instance ID sau timeout, broker cần nhận diện request lặp và so sánh với operation hoặc tài nguyên hiện tại. Không được bỏ qua validation chỉ vì instance ID đã tồn tại, cũng không được tạo operation mới nếu request thực chất là retry của thao tác đã ghi nhận.

Có thể tính fingerprint từ dữ liệu đã chuẩn hóa cùng service ID, plan ID và operation type để phát hiện request lặp. Fingerprint không thay thế authorization và không nên bao gồm secret theo cách có thể làm lộ thông tin qua log.

## 11. Bảo mật dữ liệu tham số

Parameters có thể chứa tên tài nguyên, lựa chọn cấu hình, dữ liệu tenant hoặc bí mật. Broker cần áp dụng các nguyên tắc sau:

- **Allowlist field:** chỉ chấp nhận những key được định nghĩa trong hợp đồng của thao tác.
- **Giới hạn kích thước:** giới hạn kích thước body, độ dài chuỗi, số phần tử mảng và độ sâu JSON để tránh cạn bộ nhớ.
- **Chống injection:** truyền giá trị qua parameterized query hoặc API client có kiểu; không ghép chuỗi đầu vào thành SQL, shell command hoặc URL tùy ý.
- **Bảo vệ secret:** không log password, token, private key hoặc raw parameter map có chứa secret.
- **Kiểm soát URL/endpoint:** không cho client chỉ định endpoint provider tùy ý; nếu cần endpoint, chọn từ cấu hình được broker quản lý để tránh SSRF.
- **Phân quyền theo tenant:** xác minh caller được phép thao tác trên organization, space, app và instance được tham chiếu.
- **Giới hạn tài nguyên:** kiểm tra quota và giới hạn plan trước khi gọi provider.
- **Audit:** ghi nhận ai yêu cầu thao tác, resource ID, kết quả validation và correlation ID; loại bỏ giá trị nhạy cảm khỏi audit log.

Không đưa toàn bộ parameters vào log chỉ để tiện debug. Có thể log danh sách tên field, mã lỗi validation, operation ID và service/plan ID nếu các giá trị này không nhạy cảm. Nếu cần lưu giá trị để điều tra, áp dụng masking và kiểm soát truy cập.

## 12. Kiểm thử validation phía broker

Validation cần được kiểm thử ở nhiều tầng. Unit test xác minh quy tắc thuần; service test xác minh thứ tự gọi repository, quota và provider; HTTP integration test xác minh response theo OSB API.

Ví dụ unit test cho validator:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;

class ProvisionParameterValidatorTest {

    private final ProvisionParameterValidator validator =
            new ProvisionParameterValidator();

    private final PlanLimits limits = new PlanLimits(
            10,
            500,
            Set.of("ap-southeast-1", "ap-southeast-2")
    );

    @Test
    void acceptsValidParameters() {
        var result = validator.validate(Map.of(
                "databaseName", "orders_db",
                "storageGb", 100,
                "region", "ap-southeast-1",
                "backupEnabled", true,
                "backupRetentionDays", 14
        ), limits);

        assertThat(result.storageGb()).isEqualTo(100);
        assertThat(result.backupEnabled()).isTrue();
        assertThat(result.backupRetentionDays()).isEqualTo(14);
    }

    @Test
    void rejectsUnknownParameter() {
        assertThatThrownBy(() -> validator.validate(Map.of(
                "databaseName", "orders_db",
                "storageGb", 100,
                "region", "ap-southeast-1",
                "adminMode", true
        ), limits))
                .isInstanceOf(InvalidParametersException.class)
                .hasMessageContaining("Provision parameters are invalid");
    }

    @Test
    void rejectsStorageOutsidePlanLimit() {
        assertThatThrownBy(() -> validator.validate(Map.of(
                "databaseName", "orders_db",
                "storageGb", 900,
                "region", "ap-southeast-1"
        ), limits))
                .isInstanceOf(InvalidParametersException.class);
    }
}
~~~

Các test này minh họa ba trường hợp cơ bản. Một bộ test đầy đủ nên có thêm:

| Tình huống | Kết quả mong đợi |
|---|---|
| Thiếu databaseName | Validation thất bại trước provider |
| databaseName sai pattern hoặc quá dài | Từ chối request |
| storageGb là chuỗi "100" | Từ chối vì sai kiểu |
| storageGb nhỏ hơn min hoặc lớn hơn max | Từ chối theo policy của plan |
| region không được plan cho phép | Từ chối request |
| backupEnabled là chuỗi "true" | Từ chối vì sai kiểu boolean |
| backupEnabled=true nhưng thiếu retention | Từ chối request |
| Có key ngoài allowlist | Từ chối request và không chuyển key xuống provider |
| Caller gửi organization_guid không thuộc quyền | Từ chối authorization |
| Quota đã hết | Từ chối trước side effect |
| Instance đang DELETING nhưng nhận update | Từ chối theo state machine |
| Provider bị timeout sau validation | Trả lỗi provider phù hợp, không gắn nhãn validation |
| Request retry cùng instance ID | Nhận diện operation cũ, không tạo tài nguyên trùng |
| Response lỗi | Không chứa credential, stack trace hoặc nội dung nhạy cảm |

Một integration test quan trọng là gửi trực tiếp request HTTP đến endpoint OSB với parameters sai, bỏ qua giao diện platform. Kiểm tra rằng broker trả response lỗi theo hợp đồng, không gọi provider và không ghi nhận operation thành công. Test này chứng minh validation nằm thật sự ở phía broker.

## 13. Quy trình thực hành khi bổ sung một tham số mới

Khi thêm tham số, ví dụ **backupRetentionDays**, không chỉ thêm field vào form platform. Cần cập nhật toàn bộ hợp đồng và đường xử lý:

1. Xác định tham số thuộc provision, update hay binding.
2. Quy định kiểu JSON, bắt buộc/tùy chọn, default và miền giá trị.
3. Cập nhật schema catalog để platform có thể hiển thị đúng biểu mẫu.
4. Bổ sung validation ở broker, bao gồm quy tắc liên trường và plan.
5. Bổ sung trường vào validated parameter model.
6. Chỉ truyền giá trị đã xác thực tới provider adapter.
7. Cập nhật xử lý update và lưu cấu hình thực tế nếu cần.
8. Bổ sung unit test, service test và HTTP contract test.
9. Kiểm tra log, audit và response lỗi không làm lộ dữ liệu.
10. Xem xét tương thích ngược với platform và request đã phát hành trước đó.

Nếu tham số mới làm thay đổi ý nghĩa của plan, hãy cân nhắc version hóa schema hoặc tạo plan mới. Không thay đổi âm thầm một tham số hiện có từ optional thành required nếu platform và automation cũ chưa được cập nhật.

## Kết luận

Platform có thể hỗ trợ người dùng nhập tham số đúng, nhưng broker là nơi quyết định request có được phép tạo hoặc thay đổi tài nguyên hay không. Hãy kiểm tra lại cấu trúc, allowlist, kiểu dữ liệu, miền giá trị, quy tắc liên trường, plan, quota, quyền và trạng thái trước mọi side effect. Trong Spring Cloud Open Service Broker, tách validator khỏi controller và provider, chuyển dữ liệu thô thành kiểu tham số đã xác thực, ánh xạ lỗi theo OSB API và kiểm thử trực tiếp endpoint broker. Cách làm này giúp service broker an toàn trước request sai hoặc bị giả mạo, giữ dữ liệu nhất quán và tránh tạo tài nguyên ngoài chính sách.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md) — cấu trúc request, parameters và schema trong catalog.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — các service interface, request model và cơ chế xử lý lỗi.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/) — chuẩn validation cho object và constraint.
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) — allowlist, kiểu dữ liệu, miền giá trị và validation phía server.
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/) — phân quyền theo đối tượng, kiểm soát đầu vào và giới hạn tài nguyên API.


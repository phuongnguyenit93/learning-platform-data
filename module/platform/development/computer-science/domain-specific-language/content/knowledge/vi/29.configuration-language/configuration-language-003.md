# Ghi đè cấu hình

## Ghi đè cấu hình trong DSL cấu hình là gì?

Trong một ngôn ngữ chuyên miền dùng để mô tả cấu hình (configuration DSL), cùng một ứng dụng thường cần chạy ở nhiều môi trường và với nhiều mục đích khác nhau. Một cấu hình cơ sở có thể mô tả cổng mạng, database, logging, giới hạn tài nguyên và các rule nghiệp vụ. Khi triển khai ở máy phát triển, môi trường kiểm thử hoặc production, một số giá trị cần thay đổi mà không phải sao chép toàn bộ cấu hình.

**Ghi đè cấu hình (configuration override)** là cơ chế cho phép một nguồn cấu hình có độ ưu tiên cao hơn thay thế hoặc điều chỉnh giá trị được khai báo ở nguồn có độ ưu tiên thấp hơn. Cấu hình cuối cùng được tạo từ các giá trị mặc định, cấu hình chung, profile, môi trường triển khai, tham số dòng lệnh hoặc các nguồn được hệ thống cho phép.

Ví dụ, DSL khai báo cấu hình cơ sở:

~~~text
SERVICE checkout {
  http {
    host = "127.0.0.1"
    port = 8080
  }

  database {
    host = "localhost"
    port = 5432
    poolSize = 10
  }

  logging {
    level = "INFO"
  }
}
~~~

Khi chạy trên production, hệ thống có thể ghi đè một số giá trị:

~~~text
OVERRIDE SERVICE checkout {
  http.port = 8443
  database.host = "db-prod.internal"
  database.poolSize = 40
  logging.level = "WARN"
}
~~~

Kết quả là cấu hình cuối cùng giữ nguyên những giá trị không bị ghi đè, đồng thời dùng các giá trị mới cho những đường dẫn được chỉ định. Trong ví dụ này, host của HTTP vẫn là 127.0.0.1 nếu không có lớp cấu hình khác thay đổi nó; port và các trường được nêu trong override nhận giá trị mới.

Cơ chế này hữu ích vì:

- Một cấu hình chung có thể được tái sử dụng giữa nhiều môi trường.
- Mỗi môi trường chỉ cần khai báo phần khác biệt.
- Giá trị triển khai có thể được cung cấp từ biến môi trường hoặc dòng lệnh.
- Người vận hành có thể điều chỉnh một phần cấu hình mà không sao chép toàn bộ tài liệu.
- Các profile như development, test và production có thể dùng chung cấu trúc.
- Hệ thống có thể ghi nhận nguồn gốc và lý do của từng giá trị cuối cùng.

Ghi đè cấu hình không đơn giản chỉ là thay một chuỗi bằng chuỗi khác. Một DSL cần xác định rõ nguồn nào có quyền ưu tiên, cách hợp nhất object và collection, ý nghĩa của null hoặc giá trị bị thiếu, cách kiểm tra kiểu và cách xử lý xung đột. Nếu các quy tắc này không được đặc tả, cùng một cấu hình có thể tạo kết quả khác nhau tùy thứ tự nạp file hoặc cách chạy ứng dụng.

## Phân biệt override với default, merge, inheritance và patch

Các khái niệm này có liên quan nhưng không đồng nhất.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Default | Giá trị được dùng khi không có giá trị cụ thể | port mặc định là 8080 |
| Override | Giá trị ưu tiên hơn thay thế giá trị đã có | production đặt port thành 8443 |
| Merge | Kết hợp nhiều cấu trúc theo quy tắc | ghép hai object cấu hình |
| Inheritance | Cấu hình con nhận giá trị từ cấu hình cha | profile production kế thừa base |
| Patch | Tập thao tác thay đổi một cấu hình hiện tại | replace field, add item, remove key |
| Interpolation | Thay placeholder bằng giá trị từ context | đọc DB_HOST từ môi trường |
| Runtime mutation | Thay đổi trạng thái cấu hình khi ứng dụng đang chạy | cập nhật log level qua API |

Một giá trị default chỉ được dùng khi không có giá trị khác theo quy tắc. Override thể hiện một nguồn có chủ đích thay thế giá trị trước đó. Merge là thuật toán kết hợp các phần cấu trúc; một override có thể sử dụng merge để chỉ thay đổi một nhánh.

Inheritance mô tả quan hệ giữa các cấu hình, còn precedence xác định giá trị nào thắng khi nhiều lớp cùng khai báo một đường dẫn. Một profile có thể kế thừa base nhưng vẫn cần quy tắc ưu tiên giữa profile, biến môi trường và CLI.

Patch thường mô tả thao tác cụ thể, chẳng hạn thêm phần tử, xóa khóa hoặc thay thế giá trị. Override có thể được xem là một dạng patch đơn giản, nhưng không phải mọi patch đều là override. Ví dụ, thao tác append một phần tử vào danh sách không chỉ thay thế giá trị cũ.

Runtime mutation xảy ra sau khi cấu hình đã được nạp và có thể có tác động đến trạng thái đang chạy. Nó cần cơ chế đồng bộ, quyền truy cập và chính sách rollback riêng. Không nên mặc định coi một runtime mutation là một lớp cấu hình có thể tái lập.

## Mô hình các lớp cấu hình và thứ tự ưu tiên

Một hệ thống cấu hình thường nhận dữ liệu từ nhiều nguồn. Các nguồn phổ biến gồm:

1. Giá trị mặc định được định nghĩa trong schema hoặc ứng dụng.
2. Cấu hình cơ sở đi kèm project.
3. File cấu hình dùng chung của tổ chức.
4. Profile theo môi trường.
5. File hoặc fragment riêng cho máy triển khai.
6. Biến môi trường.
7. Tham số dòng lệnh.
8. Override được truyền trực tiếp qua API hoặc deployment system.
9. Giá trị runtime được cập nhật theo policy riêng.

Một thứ tự ưu tiên minh họa:

~~~text
Schema defaults
      |
      v
Base configuration
      |
      v
Organization configuration
      |
      v
Environment profile
      |
      v
Deployment-specific file
      |
      v
Environment variables
      |
      v
Command-line arguments
      |
      v
Explicit runtime override
      |
      v
Final effective configuration
~~~

Trong sơ đồ này, lớp ở dưới có độ ưu tiên cao hơn lớp ở trên. Đây chỉ là một chính sách mẫu. Một hệ thống khác có thể đặt CLI cao nhất, cấm runtime override hoặc không cho phép file máy triển khai ghi đè secret. Điều quan trọng là thứ tự phải được công bố và ổn định.

### Precedence phải có tính xác định

Nếu hai nguồn cùng đặt database.port, hệ thống phải biết nguồn nào thắng. Không nên để kết quả phụ thuộc vào thứ tự duyệt thư mục, thứ tự key của map hoặc thời điểm một file được đọc xong.

Có thể biểu diễn mỗi nguồn bằng metadata:

~~~text
ConfigurationSource
  id
  kind
  priority
  scope
  version
  loadedAt
  content
~~~

Khi hợp nhất, hệ thống sắp xếp nguồn theo một thứ tự xác định rồi áp dụng merge policy. Nếu hai nguồn có cùng priority và cùng ghi một đường dẫn, hệ thống có thể:

- Báo lỗi xung đột.
- Áp dụng tie-breaker được công bố như source rank.
- Yêu cầu người dùng chỉ định thứ tự rõ.
- Cho phép nguồn cụ thể thắng theo một quy tắc ổn định.

Báo lỗi thường phù hợp hơn khi hai nguồn ngang quyền nhưng có giá trị mâu thuẫn, vì nó tránh kết quả bất ngờ.

### Precedence không phải là thứ tự thời gian

Nguồn được nạp sau không nhất thiết phải thắng. Một hệ thống có thể nạp CLI trước file profile vì lý do kỹ thuật nhưng vẫn áp dụng CLI ở priority cao nhất. Thứ tự nạp và thứ tự ưu tiên là hai khái niệm khác nhau; nên mô hình hóa riêng.

### Ưu tiên theo đường dẫn

Một số hệ thống cho phép precedence khác nhau theo từng nhánh. Ví dụ, biến môi trường có thể được phép ghi đè logging và network port nhưng không được ghi đè security policy. Khi đó, policy cần xác định cả priority lẫn quyền ghi theo path.

Không nên chỉ dùng một con số priority nếu các nguồn có quyền khác nhau theo loại trường. Có thể định nghĩa policy như:

~~~text
OverridePolicy
  sourceKind: ENVIRONMENT
  allowedPaths:
    - service.http.*
    - service.logging.*
  deniedPaths:
    - service.security.*
    - service.secrets.*
~~~

## Phạm vi cấu hình (scope)

Override cần có phạm vi rõ ràng. Một giá trị có thể áp dụng cho toàn hệ thống, một module, một service, một tenant hoặc một instance cụ thể.

Các scope thường gặp:

- Global: áp dụng cho toàn bộ ứng dụng.
- Workspace: áp dụng cho project hoặc workspace.
- Module: áp dụng cho một module DSL.
- Service: áp dụng cho một service được định danh.
- Environment: áp dụng theo môi trường như development hoặc production.
- Tenant: áp dụng cho một khách hàng hoặc tổ chức.
- Instance: áp dụng cho một process hoặc node triển khai.
- Request: chỉ áp dụng cho một request nếu sản phẩm cho phép.

Ví dụ:

~~~text
CONFIG {
  defaults {
    timeout = 30s
  }

  SERVICE checkout {
    timeout = 10s
  }

  SERVICE reporting {
    timeout = 60s
  }
}
~~~

Giá trị global timeout là 30 giây. Service checkout có giá trị riêng 10 giây, còn reporting dùng 60 giây. Scope cụ thể hơn có thể thắng scope tổng quát hơn, nhưng quy tắc này cần được đặc tả cùng với source priority.

### Scope và precedence là hai chiều

Một cấu hình có thể có scope cụ thể nhưng nguồn priority thấp; một nguồn global có thể có priority cao. Ví dụ, CLI toàn cục có thể ghi đè profile service-specific, hoặc policy có thể cấm điều đó.

Một hệ thống nên xác định cách so sánh theo thứ tự, chẳng hạn:

1. Kiểm tra scope có bao phủ target hay không.
2. Chọn các nguồn hợp lệ cho target.
3. Áp dụng source priority.
4. Áp dụng path policy.
5. Xử lý xung đột nếu còn nhiều giá trị ngang quyền.

Không nên mặc định rằng scope cụ thể luôn thắng nếu chưa được quy định.

### Scope inheritance

Một service có thể kế thừa cấu hình từ module, workspace và global scope. Khi đó, mỗi path có thể nhận giá trị từ scope gần nhất có khai báo.

Ví dụ:

~~~text
GLOBAL {
  retryCount = 2
}

MODULE billing {
  timeout = 20s
}

SERVICE invoice {
  retryCount = 4
}
~~~

Service invoice có thể nhận retryCount 4 từ service scope và timeout 20 giây từ module scope. Nếu global scope không khai báo timeout, schema default có thể được dùng.

Cần xác định inheritance có áp dụng cho mọi field hay chỉ những field được đánh dấu inheritable. Một số trường như secret, identity hoặc network binding có thể không được kế thừa vì lý do bảo mật hoặc tính duy nhất.

## Cú pháp override trong DSL

Một DSL có thể hỗ trợ nhiều hình thức ghi đè. Cú pháp cần dễ đọc, có thể kiểm tra tĩnh và phân biệt rõ giá trị gốc với giá trị được điều chỉnh.

### Khối OVERRIDE

Một cách là dùng khối riêng:

~~~text
OVERRIDE PROFILE production {
  SERVICE checkout {
    http.port = 8443
    logging.level = "WARN"
  }
}
~~~

Ưu điểm là thể hiện rõ ý định ghi đè. Parser có thể tạo OverrideBlock riêng và semantic analyzer có thể kiểm tra quyền ghi đè theo scope.

### Khai báo profile

Một cách khác là dùng profile:

~~~text
PROFILE production EXTENDS base {
  SERVICE checkout {
    http.port = 8443
    database.poolSize = 40
  }
}
~~~

Profile có thể kế thừa một profile cơ sở rồi thay đổi một số trường. Cần quy định profile có được kế thừa nhiều cha hay không, và nếu có thì xử lý xung đột giữa các cha thế nào.

### Assignment theo đường dẫn

Nguồn ngoài có thể cung cấp path-value pair:

~~~text
service.checkout.http.port = 8443
service.checkout.logging.level = "WARN"
~~~

Cách này phù hợp CLI, environment mapping hoặc API. Path cần được parse và resolve theo schema, không nên dùng reflection tùy ý trên object runtime.

### Operator riêng cho override

Một DSL có thể phân biệt assignment thông thường và override:

~~~text
database.poolSize = 10
database.poolSize OVERRIDE = 40
~~~

Hoặc dùng toán tử:

~~~text
database.poolSize := 40
~~~

Nếu có nhiều toán tử assignment, grammar và semantics phải giải thích rõ chúng khác nhau thế nào. Không nên dùng ký hiệu chỉ vì ngắn gọn nếu người đọc khó nhận biết nguồn nào đang ghi đè.

### Include fragment và overlay file

Cấu hình có thể được chia thành nhiều file:

~~~text
INCLUDE "base.dsl"
INCLUDE "profiles/production.dsl" AS OVERRIDE
~~~

Cách này hỗ trợ tổ chức cấu hình lớn, nhưng cần kiểm soát include cycle, đường dẫn, thứ tự fragment và quyền ghi đè. File include không nên tự động được tin cậy chỉ vì nằm cùng thư mục.

## Hợp nhất cấu hình (merge semantics)

Một trong những quyết định quan trọng nhất là cách hợp nhất hai cấu trúc. Có nhiều chiến lược và mỗi chiến lược có thể tạo kết quả khác nhau.

### Replace toàn bộ

Trong replace semantics, giá trị mới thay thế toàn bộ giá trị cũ tại path.

Base:

~~~text
database {
  host = "localhost"
  port = 5432
  poolSize = 10
}
~~~

Override:

~~~text
database = {
  host = "db-prod.internal"
}
~~~

Nếu database object bị replace toàn bộ, kết quả chỉ có host. port và poolSize có thể bị mất hoặc được lấp lại từ default tùy schema. Cách này dễ hiểu ở cấp scalar nhưng dễ gây mất dữ liệu khi dùng với object.

### Shallow merge

Shallow merge chỉ hợp nhất một cấp. Các field trực tiếp được ghi đè, nhưng object lồng nhau có thể bị thay thế toàn bộ.

Base:

~~~text
service {
  http {
    host = "127.0.0.1"
    port = 8080
  }
  logging {
    level = "INFO"
    format = "plain"
  }
}
~~~

Override:

~~~text
service {
  logging {
    level = "WARN"
  }
}
~~~

Nếu shallow merge áp dụng ở service, logging object mới có thể thay thế logging cũ và làm mất format. Điều này thường không phải điều người dùng mong đợi nếu họ chỉ muốn đổi level.

### Deep merge

Deep merge đi xuống các object lồng nhau và thay đổi leaf field được khai báo:

~~~text
service {
  http {
    host = "127.0.0.1"
    port = 8080
  }
  logging {
    level = "INFO"
    format = "plain"
  }
}
~~~

Khi override logging.level thành WARN, kết quả giữ logging.format là plain. Đây là chiến lược thường hữu ích cho cấu hình dạng cây, nhưng cần quy định rõ cách xử lý array, null và kiểu khác nhau.

### Scalar và object conflict

Nếu base có scalar nhưng override cung cấp object tại cùng path, hoặc ngược lại, hệ thống cần báo lỗi kiểu hoặc áp dụng replace nếu policy cho phép.

Ví dụ:

~~~text
Base:     database = "disabled"
Override: database = { host = "db.internal" }
~~~

Không nên tự chuyển đổi hoặc merge hai kiểu không tương thích. Schema cần xác định kiểu mong đợi và diagnostic nên chỉ ra cả nguồn gốc của hai giá trị xung đột.

## Quy tắc hợp nhất collection

Collection cần semantics riêng. Nếu chỉ nói "merge", người dùng không biết list sẽ được thay thế, nối thêm hay hợp nhất theo khóa.

### Replace list

Danh sách mới thay thế toàn bộ danh sách cũ:

~~~text
Base:
  allowedOrigins = ["https://a.example", "https://b.example"]

Override:
  allowedOrigins = ["https://prod.example"]
~~~

Kết quả chỉ còn origin production. Đây thường là lựa chọn dễ dự đoán nhất cho danh sách có thứ tự.

### Append list

Danh sách mới được nối vào cuối:

~~~text
Base:
  plugins = ["audit", "metrics"]

Override:
  plugins += ["tracing"]
~~~

Kết quả là audit, metrics, tracing. Cần xác định duplicate có được giữ hay loại bỏ, và thứ tự có ảnh hưởng đến runtime hay không.

### Prepend list

Một số cấu hình cần phần tử mới được ưu tiên trước:

~~~text
searchPaths PREPEND ["./local", "/opt/shared"]
~~~

Thứ tự có thể ảnh hưởng đến việc tìm file hoặc plugin. Vì vậy, append và prepend phải là thao tác khác nhau, không chỉ là hai cách viết của cùng một merge.

### Merge theo key

Với collection gồm object có ID ổn định, có thể hợp nhất theo key:

~~~text
routes = [
  { id = "public", path = "/health", enabled = true },
  { id = "admin", path = "/admin", enabled = false }
]
~~~

Override chỉ cập nhật route admin:

~~~text
OVERRIDE routes BY id {
  admin.enabled = true
}
~~~

Cách này tránh thay thế toàn bộ collection. Tuy nhiên, cần quy định ID duy nhất, hành vi khi key chưa tồn tại, thứ tự phần tử và cách xóa phần tử.

### Set semantics

Một số collection không có thứ tự và không cho phép duplicate. Khi đó có thể dùng union, add và remove:

~~~text
permissions += ["invoice.read"]
permissions -= ["invoice.delete"]
~~~

Set merge cần quy định equality theo value hay stable ID, cách chuẩn hóa và thứ tự khi serialize.

### Chọn merge policy theo field

Không nên áp dụng một chiến lược collection cho mọi trường. Ví dụ:

| Trường | Merge policy có thể phù hợp |
|---|---|
| allowedOrigins | Replace hoặc set union tùy yêu cầu |
| plugins | Append hoặc merge theo plugin ID |
| route definitions | Merge theo route ID |
| command arguments | Replace vì thứ tự có ý nghĩa |
| access roles | Set union có kiểm soát |
| middleware chain | Append/prepend vì thứ tự thực thi quan trọng |

Schema có thể khai báo merge strategy cho từng field để người viết cấu hình không phải đoán.

## Ý nghĩa của missing, null, delete và reset

Một override có thể không khai báo một trường, khai báo null hoặc yêu cầu xóa giá trị. Các trạng thái này không nên bị nhập làm một.

### Missing: không có chỉ thị

Nếu override không đề cập database.port, giá trị trước đó được giữ nguyên. Đây là semantics phổ biến của partial override.

### Null: giá trị rỗng có chủ đích

Null có thể có nghĩa field được đặt thành không có giá trị. Tuy nhiên, field có thể không nullable. Cần schema quy định null được phép hay không và null có khác với empty string hoặc empty list không.

### Delete: loại bỏ giá trị được kế thừa

Nếu một field đã được khai báo ở lớp thấp hơn nhưng profile muốn xóa nó, có thể cần một thao tác delete riêng:

~~~text
OVERRIDE SERVICE checkout {
  REMOVE legacyEndpoint
}
~~~

Sau khi xóa, field có thể trở thành absent, được dùng default hoặc gây lỗi nếu là required. Quy tắc cần rõ.

### Reset: quay về default

Reset khác với delete. Reset có thể loại bỏ mọi override hiện tại tại path rồi áp dụng schema default:

~~~text
OVERRIDE SERVICE checkout {
  RESET timeout
}
~~~

Nếu không có default, hệ thống cần xác định reset tạo absent hay lỗi.

### Empty collection

Empty list hoặc empty object là giá trị có thật, không nhất thiết tương đương với missing. Ví dụ, đặt allowedOrigins thành [] có thể chủ đích chặn mọi origin. Nếu merge policy coi list rỗng là "không có thay đổi", người dùng sẽ không thể biểu đạt ý định này.

Một mô hình dữ liệu nội bộ có thể dùng trạng thái rõ:

~~~text
OverrideValue
  Unspecified
  Set(value)
  SetNull
  Remove
  ResetToDefault
  Append(values)
  Prepend(values)
~~~

Không nhất thiết phải có tất cả trạng thái trong mọi DSL, nhưng semantics cần được mô tả và kiểm tra.

## Profile và cấu hình theo môi trường

Profile cho phép nhóm các override theo một mục đích hoặc môi trường.

Ví dụ:

~~~text
PROFILE development EXTENDS base {
  SERVICE checkout {
    logging.level = "DEBUG"
    database.host = "localhost"
    database.poolSize = 5
  }
}

PROFILE test EXTENDS base {
  SERVICE checkout {
    logging.level = "WARN"
    database.host = "test-db.internal"
    database.poolSize = 8
  }
}

PROFILE production EXTENDS base {
  SERVICE checkout {
    logging.level = "ERROR"
    database.host = "prod-db.internal"
    database.poolSize = 40
  }
}
~~~

Ứng dụng chọn profile bằng cấu hình triển khai hoặc tham số được phép. Không nên mặc định tự chọn production chỉ vì một biến môi trường nào đó tồn tại; profile đang hoạt động cần được xác định rõ và có thể quan sát.

### Kế thừa profile

Profile có thể mở rộng một profile khác:

~~~text
PROFILE production-eu EXTENDS production {
  SERVICE checkout {
    region = "eu-west"
    database.host = "db-eu.internal"
  }
}
~~~

Nếu cho phép nhiều profile cha, cần xử lý trường hợp hai cha cùng khai báo một path. Có thể yêu cầu thứ tự cha rõ ràng hoặc báo conflict để tránh kết quả phụ thuộc vào thứ tự không ổn định.

### Profile theo feature

Ngoài môi trường, profile có thể đại diện cho tính năng hoặc cách triển khai:

~~~text
PROFILE high-availability EXTENDS base {
  SERVICE checkout {
    replicas = 3
    healthCheck.enabled = true
  }
}
~~~

Có thể kích hoạt nhiều profile nếu hệ thống hỗ trợ. Khi đó, cần quy tắc precedence giữa profile và policy kiểm tra xung đột.

### Không nhúng secret vào profile

Profile thường được lưu trong repository, vì vậy không nên chứa password, API token hoặc private key. Profile có thể tham chiếu đến secret được cấp từ secret manager hoặc môi trường triển khai, nhưng việc resolve cần được kiểm soát riêng.

## Ghi đè bằng biến môi trường

Biến môi trường thường được dùng để đưa giá trị triển khai vào ứng dụng mà không phải sửa file cấu hình.

Một quy ước có thể ánh xạ:

~~~text
APP_SERVICE_CHECKOUT_HTTP_PORT=8443
APP_SERVICE_CHECKOUT_LOGGING_LEVEL=WARN
APP_SERVICE_CHECKOUT_DATABASE_POOL_SIZE=40
~~~

Deserializer hoặc configuration loader chuyển tên biến thành path:

~~~text
APP_SERVICE_CHECKOUT_HTTP_PORT
            |
            v
service.checkout.http.port
~~~

### Quy tắc ánh xạ tên

Cần đặc tả:

- Prefix được dùng để nhận diện biến thuộc ứng dụng.
- Cách chuyển dấu gạch dưới thành path separator.
- Cách biểu diễn tên field có dấu gạch dưới.
- Quy tắc chữ hoa/chữ thường.
- Cách xử lý array index hoặc map key.
- Cách xử lý tên trùng sau chuẩn hóa.

Ví dụ, hai field service.httpPort và service.http.port có thể va chạm nếu quy tắc mapping không đủ rõ. Có thể dùng escaping hoặc mapping table thay vì tự tách mọi dấu gạch dưới.

### Chuyển kiểu từ chuỗi

Environment variable thường là chuỗi. Loader cần parse theo schema:

- "8443" thành integer.
- "true" thành boolean theo grammar được công bố.
- "30s" thành duration nếu DSL hỗ trợ.
- "1.25" thành Decimal.
- "a,b,c" thành list chỉ khi schema quy định delimiter.
- Một chuỗi có thể được giữ nguyên nếu field là string.

Không nên suy luận kiểu chỉ từ hình dạng chuỗi. Ví dụ, "0012" có thể là mã định danh chứ không phải số 12. Schema là nguồn xác định kiểu.

### Giá trị rỗng

Environment variable tồn tại nhưng có giá trị rỗng khác với biến không tồn tại. Có thể xem empty string là giá trị string hợp lệ, là null, hoặc là lỗi theo schema. Không nên tự động biến chuỗi rỗng thành missing vì có thể làm mất ý định cấu hình.

### Không ghi giá trị secret vào log

Khi báo lỗi parse environment variable, không nên in nguyên giá trị nếu nó có thể chứa secret. Có thể ghi tên path và kiểu mong đợi, che giá trị hoặc chỉ ghi error code.

## Ghi đè qua command line và API

CLI hữu ích cho script triển khai, công cụ local và chạy thử:

~~~text
dsl-run --profile production \
  --set service.checkout.http.port=8443 \
  --set service.checkout.logging.level=WARN
~~~

### Cú pháp CLI

Một CLI có thể hỗ trợ:

- --profile để chọn profile.
- --config để nạp file.
- --set path=value để ghi đè scalar.
- --append path=value để thêm phần tử.
- --remove path để xóa.
- --reset path để trở về default.
- --dry-run để hiển thị cấu hình hiệu lực mà không chạy ứng dụng.

Cần quy định cách parse dấu bằng, dấu phẩy, khoảng trắng, escape và giá trị có ký tự đặc biệt. Một CLI tốt nên cho phép truyền value nguyên vẹn mà không vô tình tách thành nhiều đối số.

### Nhiều lần --set cùng path

Nếu cùng path xuất hiện nhiều lần, CLI cần policy rõ. Có thể áp dụng theo thứ tự đối số, từ trái sang phải, hoặc báo lỗi duplicate. Nếu dùng thứ tự đối số, phải bảo đảm shell và parser không làm thay đổi thứ tự.

### API override

Một service quản lý cấu hình có thể nhận patch qua API. API cần xác thực người gọi, kiểm tra quyền theo path, validate kiểu, ghi audit và áp dụng thay đổi theo transaction.

Không nên cho phép client gửi object tùy ý rồi merge trực tiếp vào runtime state. Cần một schema và allowlist các path được phép sửa.

### Dry run và explain

CLI/API có thể cung cấp chế độ preview:

~~~text
dsl-config explain service.checkout.database.poolSize
~~~

Kết quả có thể cho biết giá trị hiệu lực là 40, đến từ profile production, còn giá trị base là 10 và schema default là 5. Điều này giúp người vận hành hiểu vì sao cấu hình có giá trị hiện tại.

## Thứ tự resolve và pipeline tạo effective configuration

Một pipeline nên tách việc đọc nguồn, chuẩn hóa, hợp nhất và validation.

~~~text
Load schema and defaults
          |
          v
Read base configuration
          |
          v
Load selected profiles
          |
          v
Load environment-specific sources
          |
          v
Read environment and CLI overrides
          |
          v
Normalize paths and values
          |
          v
Apply precedence and merge policies
          |
          v
Resolve references and interpolation
          |
          v
Validate effective configuration
          |
          v
Freeze / publish configuration snapshot
~~~

### Tạo snapshot

Kết quả hợp nhất nên được biểu diễn thành một snapshot bất biến hoặc có version. Các thành phần runtime đọc cùng một snapshot để tránh một request nhìn thấy nửa cấu hình cũ và nửa cấu hình mới.

Ví dụ:

~~~text
EffectiveConfiguration
  version
  values
  sourceMap
  schemaVersion
  profile
  resolvedAt
~~~

Snapshot có thể được thay thế nguyên tử khi có cấu hình mới. Các thành phần đang xử lý request có thể tiếp tục dùng snapshot cũ cho đến khi hoàn tất, tùy consistency model.

### Validation sau merge

Không chỉ validate từng file riêng lẻ. Một file profile có thể hợp lệ độc lập nhưng khi kết hợp với base lại tạo cấu hình thiếu trường bắt buộc hoặc có quan hệ không tương thích.

Ví dụ, base đặt TLS enabled nhưng profile override certificatePath thành absent. Cấu hình cuối cùng có thể không hợp lệ dù từng source đều parse được.

Cần thực hiện:
- Parse và structural validation từng nguồn.
- Kiểm tra quyền override.
- Hợp nhất theo precedence và merge policy.
- Resolve reference.
- Validate invariant trên effective configuration.
- Chỉ publish snapshot nếu mọi điều kiện bắt buộc đều thành công.

### Atomicity

Nếu cấu hình được reload, không nên cập nhật từng field trực tiếp trên object đang được nhiều thread sử dụng. Có thể tạo snapshot mới, validate đầy đủ rồi atomically swap reference. Nếu bước nào thất bại, giữ snapshot cũ và báo lỗi.

## Nguồn gốc giá trị và khả năng giải thích

Khi một field có giá trị bất ngờ, người vận hành cần biết nó đến từ đâu. Giá trị cuối cùng nên có provenance, tức thông tin nguồn gốc.

Một provenance record có thể gồm:

~~~text
ConfigurationValue
  path
  effectiveValue
  sourceId
  sourceKind
  sourceLocation
  priority
  overriddenSources[]
  mergeOperation
~~~

Ví dụ:

~~~text
Path: service.checkout.database.poolSize
Default: 5
Base file: 10
Production profile: 40
Environment variable: not set
CLI: not set
Effective value: 40
Winner: production profile
~~~

### Explain command

Một lệnh explain có thể trả lời:

- Giá trị cuối cùng là gì?
- Nguồn nào đã đặt giá trị?
- Những nguồn nào đã bị ghi đè?
- Merge strategy nào được áp dụng?
- Có default hoặc fallback nào được dùng?
- Có interpolation nào được resolve?
- Giá trị có bị policy giới hạn không?

Provenance rất hữu ích khi có nhiều lớp cấu hình, nhưng cần tránh hiển thị secret. Explain cho secret nên hiển thị nguồn và trạng thái đã resolve, không hiển thị nội dung bí mật.

### Audit trail

Nếu override có thể được thay đổi qua API hoặc deployment tool, cần audit:

- Ai thực hiện thay đổi.
- Thời điểm.
- Path bị thay đổi.
- Giá trị trước và sau theo policy bảo mật.
- Lý do hoặc change ticket nếu được yêu cầu.
- Kết quả validation.
- Snapshot version được áp dụng.

Audit không nhất thiết phải lưu raw secret hoặc toàn bộ cấu hình. Có thể lưu hash, metadata và masked value.

## Validation kiểu và ràng buộc của override

Một override phải tuân theo schema của field đích. Không nên chấp nhận mọi giá trị rồi ép kiểu ở runtime.

Ví dụ schema:

~~~text
CONFIG_SCHEMA {
  service.checkout.http.port: Integer {
    min = 1
    max = 65535
  }

  service.checkout.logging.level: Enum {
    values = ["TRACE", "DEBUG", "INFO", "WARN", "ERROR"]
  }

  service.checkout.database.poolSize: Integer {
    min = 1
    max = 200
  }
}
~~~

Override port thành chuỗi "abc" phải tạo lỗi type conversion. Override poolSize thành 500 phải tạo lỗi constraint. Override một path không tồn tại có thể bị từ chối hoặc được cho phép như extension theo policy.

### Kiểm tra kiểu trước hay sau merge?

Nguồn riêng lẻ nên được kiểm tra cú pháp và khả năng chuyển kiểu. Tuy nhiên, một số validation chỉ có thể thực hiện trên giá trị cuối cùng vì phụ thuộc nhiều field.

Ví dụ:
- TLS enabled yêu cầu certificate path.
- Pool size không được vượt tổng connection budget.
- Timeout của child service không được vượt timeout của request cha.
- Một endpoint chỉ hợp lệ khi feature tương ứng được bật.

Vì vậy, cần cả source validation và effective configuration validation.

### Unknown path

Nếu override ghi service.checkout.db.potr thay vì db.port, hệ thống cần phát hiện path không tồn tại. Chế độ strict nên báo lỗi. Với hệ thống hỗ trợ extension, có thể cho phép path trong namespace mở rộng nhưng phải có quy tắc rõ.

Không nên âm thầm bỏ qua typo vì cấu hình cuối cùng có thể tiếp tục dùng giá trị cũ mà người vận hành không biết override đã thất bại.

### Immutable và mutable field

Schema có thể đánh dấu field chỉ được đặt lúc khởi động hoặc được phép thay đổi khi reload:

~~~text
FieldPolicy
  startupOnly
  reloadable
  secret
  overridableSources
  allowedScopes
~~~

Ví dụ, port listener có thể yêu cầu restart, trong khi logging.level có thể reload trực tiếp. Override runtime cần tôn trọng khả năng reload của field.

## Bảo mật và quyền ghi đè

Ghi đè cấu hình có thể thay đổi network exposure, quyền truy cập, secret, database, feature flag hoặc giới hạn tài nguyên. Vì vậy, quyền override cần được kiểm soát theo source và path.

### Allowlist path

Một nguồn như environment variable có thể chỉ được ghi đè một số path. CLI của developer có thể được phép đổi log level nhưng không được đổi security policy trong production.

### Denylist không đủ

Chỉ chặn một vài path nhạy cảm có thể bỏ sót trường mới được thêm sau này. Có thể dùng allowlist cho nguồn có quyền hạn chế, sau đó mở rộng có chủ đích.

### Phân quyền theo vai trò

Một hệ thống quản trị có thể phân quyền:

- Developer: thay đổi cấu hình local.
- Operator: thay đổi một số field runtime.
- Security administrator: quản lý policy và secret references.
- Deployment system: đặt các field theo manifest được phê duyệt.

Quyền cần được kiểm tra ở server side, không chỉ dựa vào editor hoặc CLI.

### Secret và secret reference

Không nên lưu password hoặc token trực tiếp trong file profile được commit. Có thể tham chiếu:

~~~text
database.password = SECRET("checkout/database/password")
~~~

Resolver lấy secret từ secret manager theo identity và policy được cấp. Cần tránh:
- In secret trong logs.
- Hiển thị secret trong explain output.
- Ghi secret vào provenance hoặc audit.
- Đưa secret vào metric label.
- Serialize effective configuration chứa secret ra artifact không bảo vệ.

### Không cho override làm mất policy bảo mật

Một nguồn có priority cao không nên tự động có quyền thay đổi mọi trường. Security invariant có thể được áp dụng sau merge để ngăn cấu hình cuối cùng vô hiệu hóa authentication, TLS hoặc permission controls.

## Reload cấu hình và override khi ứng dụng đang chạy

Một số ứng dụng cần đọc lại cấu hình khi file thay đổi hoặc khi API gửi override mới. Reload tạo ra một chu kỳ xử lý khác với initial load.

Một quy trình an toàn:

1. Nhận biết source thay đổi.
2. Đọc snapshot mới của các nguồn.
3. Parse và validate.
4. Áp dụng migration nếu cần.
5. Hợp nhất lại toàn bộ effective configuration.
6. Resolve secret và reference.
7. Kiểm tra field có thể reload.
8. Tạo snapshot mới.
9. Publish snapshot nguyên tử.
10. Ghi event và audit theo policy.

### Reload toàn bộ hay cập nhật một phần?

Reload toàn bộ từ các nguồn chuẩn thường dễ tái lập hơn vì kết quả không phụ thuộc lịch sử các patch runtime. Cập nhật một phần có thể nhanh hơn nhưng cần xác định patch được áp dụng trên snapshot nào và có còn hợp lệ sau thay đổi source khác hay không.

### Field cần restart

Một số thay đổi không thể áp dụng an toàn khi process đang chạy. Hệ thống có thể:

- Từ chối reload và yêu cầu restart.
- Áp dụng các field reloadable, giữ field startup-only và báo trạng thái partial.
- Tạo pending configuration để áp dụng ở lần khởi động tiếp theo.

Nếu hỗ trợ partial reload, giao diện cần cho biết chính xác field nào đã áp dụng và field nào đang chờ. Không nên báo toàn bộ reload thành công nếu chỉ một phần được áp dụng.

### Đồng bộ giữa nhiều thread

Runtime có thể đọc cấu hình đồng thời khi reload. Immutable snapshot và atomic swap giúp mọi request dùng một phiên bản nhất quán. Nếu một thao tác cần nhiều giá trị liên quan, không nên đọc từng field từ các mutable map đang được cập nhật riêng lẻ.

### Rollback

Nếu cấu hình mới làm health check thất bại, hệ thống có thể rollback về snapshot trước đó nếu policy cho phép. Cần lưu version, validation result và lý do rollback. Rollback không nên vô tình khôi phục secret đã bị thu hồi hoặc policy đã bị thay đổi vì lý do bảo mật.

## Tính xác định và khả năng tái lập

Cùng một tập source, schema, profile và context nên tạo cùng effective configuration. Đây là tính xác định (determinism).

Các nguyên nhân có thể làm kết quả khác nhau:

- Thứ tự đọc file không ổn định.
- Environment variable thay đổi giữa các lần chạy.
- Secret reference trỏ đến version mới.
- Default phụ thuộc thời gian hoặc hostname.
- Merge list không có quy tắc thứ tự.
- Runtime override được áp dụng theo lịch sử.
- Schema hoặc catalog version thay đổi.
- Profile được chọn ngầm theo môi trường.

Để tái lập, cần ghi nhận:
- Schema version.
- Phiên bản DSL hoặc loader.
- Danh sách source và content hash.
- Profile được chọn.
- Override path đã áp dụng.
- Merge policy version.
- Reference version hoặc secret version khi phù hợp.
- Các biến môi trường được dùng ở dạng đã che hoặc metadata không nhạy cảm.

Không nên ghi secret value để phục vụ tái lập. Có thể lưu secret version hoặc identifier an toàn và yêu cầu resolver cung cấp đúng version khi chạy lại nếu policy cho phép.

### Effective configuration snapshot

Một snapshot có thể được serialize dưới dạng redacted để hỗ trợ debug. Nó nên phân biệt giá trị literal, giá trị được resolve và nguồn gốc, đồng thời đánh dấu field nhạy cảm.

### Cache key

Nếu kết quả cấu hình được cache, cache key cần bao gồm mọi đầu vào có ảnh hưởng đến effective value: schema, base file, profile, override source, environment inputs được cho phép và version của resolver. Chỉ hash base file là không đủ nếu environment override thay đổi.

## Ghi đè cấu hình và feature flags

Feature flag là một trường hợp thường gặp của override. Một flag có thể được đặt mặc định trong code, trong profile, bởi tenant hoặc qua hệ thống quản trị.

Ví dụ:

~~~text
FEATURES {
  newCheckout = false
  expressShipping = true
}

OVERRIDE TENANT customer-42 {
  FEATURES {
    newCheckout = true
  }
}
~~~

Feature flag có thể có nhiều scope: global, environment, tenant, user hoặc request. Hệ thống cần quy tắc ưu tiên rõ và bảo đảm các flag phụ thuộc nhau vẫn nhất quán.

Ví dụ, bật newCheckout có thể yêu cầu paymentV2 cũng được bật. Validation sau merge có thể kiểm tra dependency này.

Cần phân biệt cấu hình triển khai với quyết định rollout. Một flag có thể được điều khiển bởi percentage rollout hoặc targeting rule, không chỉ một boolean. Khi đó, model nên biểu diễn strategy và context thay vì ép mọi thứ thành giá trị true/false đơn giản.

## Ghi đè cấu hình đa tenant

Ứng dụng đa tenant có thể dùng cấu hình nền chung và override cho từng tenant.

~~~text
BASE {
  limits {
    maxProjects = 10
    maxUsers = 50
  }
}

TENANT acme EXTENDS BASE {
  limits {
    maxProjects = 100
    maxUsers = 500
  }
}
~~~

Cần xác định tenant nào được phép ghi đè field nào. Tenant không nên có quyền thay đổi các cấu hình ảnh hưởng đến tenant khác hoặc hạ thấp security policy chung.

### Cô lập và cache

Effective configuration của tenant phải được xác định theo tenant identity đã xác thực. Không lấy tenant ID từ một field không đáng tin trong payload rồi dùng nó để resolve cấu hình.

Cache key phải bao gồm tenant ID hoặc một identity nội bộ an toàn. Không dùng chung snapshot giữa hai tenant nếu có field riêng.

### Giới hạn tài nguyên

Tenant override không được vượt quota do hệ thống quản trị đặt. Ví dụ tenant có thể yêu cầu maxUsers 1000 nhưng organization policy chỉ cho phép 500. Validation cần áp dụng giới hạn tổng thể sau khi merge.

## Ví dụ hoàn chỉnh về cấu hình nhiều lớp

Giả sử hệ thống checkout có schema default:

~~~text
DEFAULTS {
  service.checkout.http.port = 8080
  service.checkout.database.poolSize = 5
  service.checkout.logging.level = "INFO"
  service.checkout.features.expressShipping = false
}
~~~

File base:

~~~text
SERVICE checkout {
  http {
    host = "127.0.0.1"
    port = 8081
  }
  database {
    host = "localhost"
    poolSize = 10
  }
  logging {
    level = "DEBUG"
    format = "json"
  }
  features {
    expressShipping = true
  }
}
~~~

Profile production:

~~~text
PROFILE production {
  SERVICE checkout {
    http.port = 8443
    database.host = "db-prod.internal"
    database.poolSize = 40
    logging.level = "WARN"
  }
}
~~~

Environment override:

~~~text
APP_SERVICE_CHECKOUT_DATABASE_POOL_SIZE=50
~~~

CLI override:

~~~text
--set service.checkout.logging.level=ERROR
~~~

Giả sử policy là schema default thấp nhất, base kế tiếp, profile cao hơn, environment cao hơn profile và CLI cao nhất. Deep merge được dùng cho object; scalar được replace.

Effective configuration:

~~~text
service.checkout.http.host = "127.0.0.1"
service.checkout.http.port = 8443
service.checkout.database.host = "db-prod.internal"
service.checkout.database.poolSize = 50
service.checkout.logging.level = "ERROR"
service.checkout.logging.format = "json"
service.checkout.features.expressShipping = true
~~~

Nguồn gốc:
- http.host đến từ base.
- http.port đến từ production profile.
- database.host đến từ production profile.
- database.poolSize đến từ environment.
- logging.level đến từ CLI.
- logging.format đến từ base.
- features.expressShipping đến từ base.

Ví dụ cho thấy override chỉ thay đổi các path được chỉ định, còn những path khác tiếp tục nhận giá trị từ lớp thấp hơn. Nếu policy dùng shallow merge thay vì deep merge, logging.format có thể bị mất khi profile khai báo object logging; vì vậy merge semantics phải là một phần của hợp đồng.

## Diagnostics khi override thất bại

Override có thể thất bại vì nhiều lý do:

- Path không tồn tại.
- Giá trị không đúng kiểu.
- Giá trị ngoài giới hạn.
- Nguồn không có quyền ghi path.
- Hai nguồn ngang priority xung đột.
- Collection merge không hợp lệ.
- Reference không resolve được.
- Profile kế thừa có chu trình.
- Effective configuration vi phạm invariant.
- Field không thể reload trong runtime.
- Secret resolver không truy cập được.

Một diagnostic có thể chứa:

~~~text
ConfigurationDiagnostic
  code
  severity
  path
  message
  sourceId
  sourceLocation
  relatedSources
  expectedType
  actualType
  remediation
~~~

Nếu hai nguồn cùng ghi một path, diagnostic nên chỉ ra cả hai nguồn và priority. Nếu environment variable sai kiểu, có thể báo tên biến và kiểu mong đợi nhưng che giá trị.

### Fail fast và thu thập nhiều lỗi

Ở chế độ deploy production, có thể dừng nếu có bất kỳ lỗi nghiêm trọng nào. Trong editor, có thể thu thập nhiều lỗi để người dùng sửa cùng lúc.

Một loader có thể phân loại:
- Fatal: không thể xác định cấu trúc hoặc schema version.
- Error: cấu hình cuối không hợp lệ.
- Warning: field deprecated hoặc override không có hiệu lực.
- Info: một giá trị đã được thay thế bởi nguồn priority cao hơn.

Không nên coi mọi override bị ghi đè là lỗi. Có thể đó là hành vi bình thường, nhưng hệ thống nên cho phép explain khi cần.

## Tích hợp với IDE và Language Server

Nếu DSL cấu hình có editor hoặc language server, override có thể được hỗ trợ ngay trong lúc soạn thảo.

Các tính năng hữu ích:

- Completion cho path có thể ghi đè.
- Hover hiển thị kiểu, default và merge policy.
- Diagnostics khi override path không tồn tại.
- Cảnh báo khi nguồn không có quyền ghi.
- Go to definition từ override đến field schema.
- Find references cho một path.
- Explain value hiển thị nguồn thắng.
- Preview effective configuration.
- Gợi ý profile đang được chọn.
- Highlight các giá trị bị override hoặc bị override bởi nguồn khác.

Language server cần phân biệt cấu hình đang chỉnh sửa với effective configuration đã được resolve. Khi file chưa lưu hoặc environment chưa được cung cấp, preview có thể chỉ là kết quả tạm thời và cần được gắn trạng thái incomplete.

Không nên gửi secret hoặc giá trị nhạy cảm đến completion, hover hay telemetry. Editor có thể hiển thị tên secret reference và trạng thái resolve mà không tiết lộ nội dung.

## Kiểm thử cơ chế override

Kiểm thử cần xác nhận cả giá trị cuối cùng và nguồn gốc của giá trị.

### Unit test cho precedence

Tạo nhiều nguồn cùng đặt một path và kiểm tra nguồn thắng đúng theo policy. Kiểm tra cả trường hợp priority bằng nhau, scope khác nhau và nguồn bị cấm ghi path.

### Test merge semantics

Bao phủ:
- Scalar replace.
- Deep merge object.
- Shallow merge nếu được hỗ trợ.
- List replace, append và prepend.
- Merge theo key.
- Set union và remove.
- Scalar/object type conflict.
- Missing, null, delete và reset.
- Empty collection.

### Test schema và validation

Kiểm tra:
- Giá trị đúng kiểu.
- Giá trị sai kiểu.
- Boundary min/max.
- Enum không hợp lệ.
- Unknown path.
- Field required bị xóa.
- Invariant liên trường.
- Secret field và quyền truy cập.

### Test profile và inheritance

Kiểm tra:
- Profile kế thừa base.
- Profile lồng nhau.
- Nhiều cha có conflict.
- Chu trình inheritance.
- Profile không tồn tại.
- Thứ tự kích hoạt nhiều profile.
- Scope override theo module hoặc service.

### Test environment và CLI

Kiểm tra mapping tên biến, prefix, escaping, empty string, boolean, number, duration, array và nhiều lần --set cùng path. Cần chạy test qua cách shell truyền đối số thực tế nếu CLI có quoting phức tạp.

### Test reload và atomicity

Giả lập reload thành công và thất bại. Xác nhận snapshot cũ vẫn được dùng khi validation thất bại; snapshot mới chỉ được publish sau khi toàn bộ bước bắt buộc hoàn tất. Kiểm tra field startup-only và rollback policy.

### Test determinism

Với cùng tập source và context, chạy hợp nhất nhiều lần và so sánh effective configuration cùng provenance. Thay đổi thứ tự file vật lý không được làm thay đổi kết quả nếu priority policy không thay đổi.

### Test security

Kiểm tra nguồn bị cấm không thể ghi security path, secret không xuất hiện trong log hoặc explain output, tenant không thể đọc override của tenant khác và resource resolver chỉ truy cập namespace được phép.

## Những lỗi thiết kế thường gặp

### Không công bố precedence

Khi không biết nguồn nào thắng, người vận hành khó giải thích giá trị cuối cùng. Cần một thứ tự ưu tiên xác định và có thể tra cứu.

### Dựa vào thứ tự nạp file

Thứ tự nạp có thể thay đổi theo filesystem hoặc concurrency. Cần tách source priority khỏi thời điểm đọc.

### Dùng một merge policy cho mọi field

Deep merge object nhưng list có thể cần replace; middleware chain có thể cần append; permission có thể cần union hoặc deny-wins. Schema nên định nghĩa policy theo field.

### Không phân biệt null với missing

Điều này khiến người dùng không thể biểu đạt rõ ý định giữ, xóa hoặc đặt rỗng. Cần semantics riêng cho từng trạng thái.

### Bỏ qua unknown path

Typo có thể làm override không có hiệu lực trong khi ứng dụng vẫn dùng giá trị cũ. Strict validation giúp phát hiện sớm.

### Chỉ validate từng file

Các file riêng lẻ có thể hợp lệ nhưng cấu hình cuối không nhất quán. Cần validate effective configuration sau merge.

### Không giữ provenance

Khi giá trị bất ngờ, không thể biết nguồn nào đã ghi đè. Lưu source map và cung cấp explain command.

### Cho phép mọi nguồn ghi mọi field

CLI, environment hoặc tenant override có thể vô tình thay đổi security policy. Cần allowlist và quyền theo path.

### Reload trực tiếp trên mutable object

Các thread có thể nhìn thấy trạng thái nửa cũ nửa mới. Tạo snapshot mới rồi publish nguyên tử.

### Không bảo đảm tái lập

Nếu kết quả phụ thuộc thứ tự file, biến môi trường ngầm hoặc secret version không được ghi nhận, khó tái tạo lỗi. Cần ghi lại input metadata và version.

## Quy trình thiết kế ghi đè cấu hình cho DSL

Một quy trình thực tế có thể đi theo các bước:

1. **Xác định nguồn cấu hình:** defaults, base files, profiles, environment, CLI, API và runtime source.
2. **Định nghĩa precedence:** quy định thứ tự ưu tiên, tie-breaker và trường hợp xung đột.
3. **Xác định scope:** global, workspace, module, service, tenant, instance hoặc request.
4. **Thiết kế cú pháp override:** block, profile, path assignment, include overlay hoặc patch operation.
5. **Định nghĩa merge policy:** scalar, object, list, map và set; xác định policy theo field.
6. **Quy định trạng thái giá trị:** missing, null, delete, reset, empty và default.
7. **Xây schema và field policy:** type, range, enum, required, secret, reloadable và allowed source.
8. **Thiết kế pipeline:** load, normalize, merge, resolve, validate và tạo effective snapshot.
9. **Giữ provenance:** ghi nguồn thắng, nguồn bị ghi đè và merge operation.
10. **Thiết kế bảo mật:** allowlist path, role, secret resolver, tenant isolation và audit.
11. **Thiết kế reload:** atomic snapshot, startup-only fields, rollback và concurrency.
12. **Bảo đảm determinism:** khóa version, source hash, profile và context cần thiết.
13. **Tích hợp công cụ:** explain, dry-run, IDE diagnostics và effective configuration preview.
14. **Kiểm thử:** precedence, merge, type, migration, reload, security và reproducibility.

Bảng contract cho mỗi field có thể ghi: path, type, default, nullable, merge strategy, allowed scopes, allowed sources, secret flag, reload policy và validation rules. Đây là cơ sở để parser, loader, CLI, IDE và runtime cùng hiểu một semantics.

## Kết luận

Ghi đè cấu hình cho phép một nguồn có độ ưu tiên cao hơn thay đổi một phần cấu hình đã được khai báo. Trong DSL cấu hình, cơ chế này giúp tái sử dụng cấu hình cơ sở giữa các môi trường, profile, tenant và deployment mà không phải sao chép toàn bộ tài liệu.

Một thiết kế đáng tin cậy cần xác định precedence, scope, cú pháp override và merge semantics cho scalar, object và collection. Nó phải phân biệt missing, null, delete, reset và default; kiểm tra kiểu và invariant trên effective configuration; đồng thời giữ provenance để giải thích nguồn gốc giá trị.

Khi override đến từ environment, CLI, API hoặc runtime, hệ thống cần kiểm soát quyền theo path, bảo vệ secret, quản lý reload bằng snapshot nhất quán và ghi audit phù hợp. Precedence có tính xác định, schema version rõ ràng, dry-run/explain và bộ kiểm thử về merge, security và reproducibility giúp cấu hình cuối dễ dự đoán và vận hành an toàn qua nhiều môi trường.

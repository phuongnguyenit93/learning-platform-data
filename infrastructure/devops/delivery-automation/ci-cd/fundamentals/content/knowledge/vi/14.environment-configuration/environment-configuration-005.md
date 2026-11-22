# Quản lý phiên bản và kiểm tra tính hợp lệ của cấu hình

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vì sao cấu hình môi trường cần được quản lý phiên bản như một phần của quá trình phát hành.
- Phân biệt cấu hình ứng dụng, cấu hình theo môi trường, tham số triển khai, cấu hình động và bí mật.
- Thiết kế cách tổ chức cấu hình theo nguồn dữ liệu, môi trường và quy tắc ưu tiên rõ ràng.
- Xác thực cấu hình bằng schema, kiểu dữ liệu, miền giá trị, ràng buộc liên trường và kiểm tra dependency.
- Kiểm tra cấu hình trước deploy, khi ứng dụng khởi động và trong quá trình vận hành.
- Phát hiện configuration drift, truy vết revision đang chạy và khôi phục cấu hình khi cần.
- Tích hợp quản lý cấu hình vào pipeline CI/CD với bằng chứng và quyền truy cập phù hợp.

## 1. Vì sao cấu hình cần được quản lý như mã nguồn?

Cấu hình quyết định cách một ứng dụng hoạt động trong từng môi trường. Cùng một artifact có thể kết nối đến database khác nhau, dùng endpoint khác nhau, bật hoặc tắt tính năng khác nhau và nhận giới hạn tài nguyên khác nhau tùy cấu hình.

Ví dụ, một dịch vụ API có thể dùng database local trong môi trường phát triển, database riêng trong integration hoặc staging, và database production với quyền truy cập cùng chính sách backup riêng. Payment provider có thể ở chế độ sandbox trong test nhưng dùng endpoint thật trong production. Feature flag có thể chỉ bật cho một nhóm người dùng trong giai đoạn rollout.

Nếu cấu hình được sửa thủ công trên máy chủ hoặc truyền qua nhiều kênh không có lịch sử, đội ngũ sẽ khó trả lời:

- Dịch vụ đang chạy với cấu hình nào?
- Ai đã thay đổi giá trị và thay đổi khi nào?
- Giá trị hiện tại có được kiểm tra trước khi áp dụng không?
- Staging và production khác nhau ở điểm nào?
- Có thể khôi phục cấu hình trước đó không?
- Cấu hình đang chạy có đúng với cấu hình được phê duyệt không?

Quản lý cấu hình theo phiên bản giúp mỗi thay đổi có lịch sử, có review, có thể so sánh và khôi phục. Kiểm tra tính hợp lệ giúp phát hiện lỗi trước khi cấu hình gây ra sự cố ở runtime.

Một nguyên tắc cần giữ:

> Cấu hình là một phần của trạng thái phát hành. Cần biết phiên bản nào được áp dụng, xác minh nó trước khi sử dụng và giữ khả năng truy vết, khôi phục.

Điều này không có nghĩa mọi giá trị phải nằm trong Git. Bí mật cần được quản lý bằng secret manager hoặc cơ chế bảo vệ tương đương. Điều quan trọng là cả cấu hình thông thường lẫn tham chiếu đến bí mật đều có thể truy vết mà không làm lộ giá trị nhạy cảm.

## 2. Phân biệt các loại cấu hình

Trước khi chọn cách lưu trữ và versioning, hãy phân loại cấu hình theo vai trò và độ nhạy cảm.

| Loại | Ví dụ | Cách quản lý gợi ý |
|---|---|---|
| Application defaults | Timeout mặc định, số lần retry mặc định | Lưu cùng mã nguồn hoặc artifact |
| Environment configuration | Database host, endpoint, log level | Config repository, manifest hoặc environment store |
| Deployment configuration | Replica, resource limits, port, volume | IaC, Helm values hoặc manifest có version |
| Runtime/dynamic configuration | Feature flag, ngưỡng nghiệp vụ, tham số đổi khi chạy | Config service hoặc feature management có revision |
| Secret | Password, API token, private key | Secret manager, không lưu plaintext trong repository |
| Build configuration | Tham số build, toolchain, profile đóng gói | Pipeline as code và cấu hình build được quản trị |

Cần phân biệt thêm:

- **Cấu hình build-time:** được dùng khi tạo artifact. Thay đổi có thể làm nội dung artifact khác đi.
- **Cấu hình deploy-time:** được dùng khi triển khai artifact, ví dụ replica, port hoặc resource limit.
- **Cấu hình runtime:** được ứng dụng đọc khi chạy, có thể thay đổi mà không build lại artifact nếu hệ thống hỗ trợ.

Phân loại này giúp xác định thay đổi nào cần build lại, thay đổi nào chỉ cần triển khai lại và thay đổi nào có thể cập nhật động theo chính sách.

## 3. Cấu hình cần có nguồn sự thật và chủ sở hữu

Một hệ thống có thể nhận cấu hình từ file trong repository, biến môi trường, command-line argument, secret manager, config service, Kubernetes ConfigMap, Helm values hoặc tham số do nền tảng triển khai cung cấp.

Nếu không xác định nguồn nào có thẩm quyền cho từng trường, giá trị có thể bị ghi đè không rõ ràng. Khi điều tra sự cố, kỹ sư có thể nhìn vào file Git nhưng ứng dụng thực tế lại đang nhận một giá trị từ environment variable hoặc config service.

Hãy lập bản đồ cấu hình:

| Nhóm | Nguồn sự thật đề xuất | Chủ sở hữu |
|---|---|---|
| Default ứng dụng | File cấu hình trong source | Nhóm phát triển |
| Giá trị theo môi trường | Config repository hoặc environment store | Nhóm sở hữu dịch vụ / platform |
| Hạ tầng và deployment | IaC hoặc manifest repository | Platform/DevOps |
| Bí mật | Secret manager | Nhóm bảo mật hoặc owner được ủy quyền |
| Feature flag | Feature management service | Product/service owner |
| Quy tắc phát hành | Policy repository hoặc policy engine | Release/platform governance |

Một trường cấu hình nên có owner rõ ràng, đặc biệt khi nó ảnh hưởng đến bảo mật, chi phí hoặc hành vi nghiệp vụ. Tránh tình trạng nhiều nhóm cùng sửa một giá trị nhưng không ai chịu trách nhiệm cuối cùng.

Cũng cần xác định ai có quyền đọc, ai có quyền thay đổi và ai có quyền áp dụng cấu hình lên production. Quyền sửa file cấu hình và quyền triển khai cấu hình có thể là hai quyền riêng biệt.

## 4. Tổ chức cấu hình theo môi trường

Có thể tổ chức cấu hình theo một số cách:

- Một repository cấu hình riêng cho nhiều dịch vụ.
- Thư mục cấu hình trong repository của từng dịch vụ.
- Helm chart và values theo môi trường.
- IaC module cùng biến đầu vào được quản trị.
- Config service cung cấp revision cho ứng dụng khi chạy.

Dù chọn cách nào, cần tránh sao chép toàn bộ cấu hình thành nhiều bản gần giống nhau. Khi một giá trị chung cần sửa, việc cập nhật nhiều file dễ tạo ra sai lệch.

Một cấu trúc minh họa:

~~~text
config/
├── base/
│   ├── application.yml
│   └── logging.yml
├── environments/
│   ├── dev/
│   │   └── values.yml
│   ├── staging/
│   │   └── values.yml
│   └── production/
│       └── values.yml
├── schema/
│   └── application.schema.json
└── policies/
    └── production-policy.yml
~~~

Trong mô hình này, base chứa giá trị mặc định dùng chung; environments chứa khác biệt có chủ đích; schema mô tả cấu trúc và ràng buộc; policies chứa quy tắc bổ sung cho môi trường nhạy cảm.

Đây chỉ là một cách tổ chức. Dự án có thể dùng Helm, Kustomize, Spring profiles hoặc config service. Điều quan trọng là quy tắc hợp nhất và nguồn ưu tiên phải được ghi rõ, có thể kiểm tra và có thể tái tạo.

Không nên sao chép secret thật vào các thư mục môi trường. Repository chỉ nên chứa tên tham chiếu hoặc placeholder an toàn.

## 5. Quản lý phiên bản cấu hình

Cấu hình có thể được version bằng Git commit, tag, revision của config service hoặc một artifact cấu hình bất biến.

Một phiên bản cấu hình cần cho biết:

- Nội dung nào đã thay đổi.
- Ai tạo và review thay đổi.
- Thời điểm thay đổi.
- Dịch vụ và môi trường nào bị ảnh hưởng.
- Schema hoặc policy version nào đã được dùng để kiểm tra.
- Phiên bản nào đang được triển khai.
- Có thể khôi phục về revision trước hay không.

### 5.1. Dùng Git để quản lý cấu hình

Git phù hợp với cấu hình dạng văn bản không chứa bí mật. Mỗi thay đổi đi qua pull request giúp review, thảo luận và lưu lịch sử.

Một quy trình cơ bản:

1. Tạo branch cho thay đổi cấu hình.
2. Chỉnh sửa file có liên quan.
3. Chạy format, schema validation và policy checks.
4. Xem diff để xác định môi trường và dịch vụ bị ảnh hưởng.
5. Review bởi owner.
6. Merge vào nhánh cấu hình được quản trị.
7. Pipeline triển khai revision đã được chấp nhận.
8. Ghi nhận revision thực tế trên môi trường.

Không nên chỉnh trực tiếp cấu hình production trên máy chủ rồi quên cập nhật lại repository. Cách làm đó tạo ra drift: trạng thái thực tế khác nguồn sự thật được quản trị.

### 5.2. Version của cấu hình và version của ứng dụng

Không nên mặc định version ứng dụng đại diện cho version cấu hình. Một artifact có thể được giữ nguyên trong khi cấu hình thay đổi nhiều lần.

Hãy ghi nhận riêng:

- Application version hoặc artifact digest.
- Configuration revision.
- Deployment manifest revision.
- Secret reference/version metadata.
- Environment revision nếu nền tảng hỗ trợ.

Nhờ đó, khi điều tra lỗi có thể xác định ứng dụng và cấu hình nào đã cùng tạo ra hành vi quan sát được.

### 5.3. Cấu hình bất biến và lịch sử thay đổi

Một revision đã được áp dụng nên có thể truy xuất lại nội dung chính xác. Nếu config service chỉ cung cấp giá trị hiện tại mà không có revision history, việc tái tạo trạng thái cũ sẽ khó khăn.

Với cấu hình nhạy cảm, có thể lưu snapshot đã loại bỏ bí mật hoặc chỉ lưu version reference. Không lưu plaintext secret vào Git history, build log hoặc deployment metadata.

## 6. Quy tắc ưu tiên khi hợp nhất cấu hình

Một ứng dụng có thể nhận giá trị từ nhiều nguồn. Ví dụ:

1. Giá trị mặc định trong file application.
2. File cấu hình theo profile.
3. Environment variable.
4. Command-line argument.
5. Config service hoặc tham số do nền tảng cấp.

Thứ tự thực tế phụ thuộc framework và cách ứng dụng được cấu hình. Không nên giả định mọi nền tảng đều dùng cùng một precedence.

Hãy xác định rõ:

- Nguồn nào được phép override nguồn nào.
- Trường nào chỉ được thay đổi qua config repository.
- Trường nào chỉ được cấp từ secret manager.
- Có cho phép override qua command line trong production không.
- Giá trị thiếu sẽ dùng default, báo lỗi hay chặn khởi động.
- Cách merge map, list và nested object.
- Cách xử lý giá trị null hoặc chuỗi rỗng.

Ví dụ, nếu file base đặt request-timeout là 3 giây, staging đặt 5 giây và environment variable đặt 10 giây, ứng dụng cần có quy tắc xác định nguồn nào thắng. Nếu không, cùng một file Git có thể tạo ra hành vi khác nhau tùy cách triển khai.

Nên tạo một bước render hoặc resolve configuration để pipeline có thể kiểm tra cấu hình cuối cùng trước khi áp dụng. Khi có thể, lưu fingerprint hoặc revision của cấu hình đã resolve để truy vết.

## 7. Kiểm tra tính hợp lệ của cấu hình theo nhiều lớp

Một file YAML hoặc JSON parse thành công chưa có nghĩa cấu hình đúng. Cấu hình cần qua nhiều lớp validation.

### 7.1. Kiểm tra cú pháp

Xác nhận file có thể parse và không có lỗi định dạng:

- YAML/JSON hợp lệ.
- Không có key trùng nếu parser có thể xử lý mơ hồ.
- Encoding đúng.
- Không có cấu trúc ngoài dự kiến.
- Template được render thành nội dung hợp lệ.

Cú pháp là lớp đầu tiên, nhưng chỉ phát hiện lỗi hình thức.

### 7.2. Kiểm tra schema và kiểu dữ liệu

Schema mô tả trường nào được phép, trường nào bắt buộc, kiểu dữ liệu và cấu trúc lồng nhau.

Ví dụ một schema có thể yêu cầu:

- port là số nguyên trong khoảng 1 đến 65535.
- replicas là số nguyên dương.
- logLevel chỉ nhận DEBUG, INFO, WARN hoặc ERROR.
- database.url là chuỗi có định dạng URI.
- featureFlags là map boolean.
- timeout có định dạng duration hợp lệ.

Schema giúp phát hiện lỗi như replicas nhận chuỗi three hoặc đặt nhầm tên trường.

### 7.3. Kiểm tra miền giá trị

Một giá trị đúng kiểu vẫn có thể không hợp lệ.

Ví dụ:

- Timeout bằng 0 hoặc âm.
- Replica vượt quota của môi trường.
- Retry count quá lớn.
- Log level không nằm trong danh sách cho phép.
- Connection pool lớn hơn giới hạn tài nguyên.
- URL trỏ đến endpoint không được phép.

Cần xác định miền giá trị theo cả logic ứng dụng và năng lực của môi trường đích.

### 7.4. Kiểm tra ràng buộc giữa các trường

Một số giá trị chỉ hợp lệ khi kết hợp với giá trị khác.

Ví dụ:

- Nếu tls.enabled là true, certificate reference và trust configuration phải tồn tại.
- Nếu payment.mode là production, endpoint phải thuộc allowlist production.
- Nếu autoscaling.enabled là true, min replicas không được lớn hơn max replicas.
- Nếu bật tính năng yêu cầu message broker, broker endpoint và credential reference phải được cấu hình.
- Nếu bật migration tự động, database identity phải trỏ đến môi trường được phép.

Những ràng buộc này thường cần logic validation riêng, vì schema đơn thuần không mô tả đầy đủ quan hệ nghiệp vụ.

### 7.5. Kiểm tra ngữ nghĩa và dependency

Cấu hình có thể hợp lệ về cấu trúc nhưng không hoạt động trong môi trường thực tế.

Ví dụ:

- Database host không phân giải được DNS.
- Secret reference không tồn tại.
- Service account không có quyền truy cập.
- TLS certificate hết hạn.
- Endpoint không phản hồi.
- Queue hoặc topic chưa được tạo.
- Phiên bản schema database không tương thích với ứng dụng.

Những kiểm tra này có thể cần chạy ở môi trường kiểm thử hoặc trong bước readiness trước deploy. Không nên thực hiện mọi kiểm tra kết nối thật trong lúc parse file vì một số dependency có thể tạm thời không sẵn sàng; cần phân biệt lỗi cấu hình với lỗi hạ tầng.

### 7.6. Kiểm tra chính sách

Policy validation xác nhận cấu hình tuân thủ yêu cầu vận hành và bảo mật.

Ví dụ:

- Production không được bật debug mode.
- Database production không được dùng tài khoản có quyền quản trị toàn hệ thống nếu không cần thiết.
- TLS phải bật cho endpoint công khai.
- Container không được chạy privileged nếu policy không cho phép.
- Resource request/limit phải nằm trong phạm vi.
- CORS không được mở wildcard cho các API nhạy cảm.
- Không được dùng endpoint sandbox trong production.

Policy nên được kiểm tra tự động trong CI và có kết quả giải thích được.

## 8. Ví dụ schema và cấu hình hợp lệ

Ví dụ cấu hình ứng dụng:

~~~yaml
server:
  port: 8080
  shutdown: graceful

application:
  environment: staging
  log-level: INFO

database:
  url: jdbc:postgresql://db-staging.internal:5432/orders
  connection-timeout: 5s
  maximum-pool-size: 20
  credentials:
    secret-reference: orders-db-staging

features:
  checkout-enabled: true
  new-pricing-enabled: false
~~~

Schema JSON minh họa:

~~~json
{
  "type": "object",
  "required": ["server", "application", "database", "features"],
  "properties": {
    "server": {
      "type": "object",
      "required": ["port"],
      "properties": {
        "port": {
          "type": "integer",
          "minimum": 1,
          "maximum": 65535
        }
      },
      "additionalProperties": false
    },
    "application": {
      "type": "object",
      "required": ["environment", "log-level"],
      "properties": {
        "environment": {
          "enum": ["dev", "staging", "production"]
        },
        "log-level": {
          "enum": ["DEBUG", "INFO", "WARN", "ERROR"]
        }
      }
    },
    "database": {
      "type": "object",
      "required": ["url", "credentials"],
      "properties": {
        "url": {
          "type": "string",
          "minLength": 1
        },
        "credentials": {
          "type": "object",
          "required": ["secret-reference"],
          "properties": {
            "secret-reference": {
              "type": "string",
              "minLength": 1
            }
          }
        }
      }
    },
    "features": {
      "type": "object",
      "additionalProperties": {
        "type": "boolean"
      }
    }
  }
}
~~~

Schema này chỉ minh họa cấu trúc và một số ràng buộc. Trong hệ thống thực tế, cần bổ sung schema cho timeout, connection pool, URL format, trường được phép theo môi trường và các quy tắc liên trường.

Không nên coi schema là nơi duy nhất để kiểm tra endpoint, quyền truy cập hoặc secret. Những điều kiện phụ thuộc vào môi trường cần có bước validation riêng.

## 9. Biến môi trường và giới hạn của chúng

Environment variable là cách phổ biến để truyền cấu hình vào process hoặc container. Chúng hữu ích vì có thể thay đổi theo môi trường mà không cần sửa mã nguồn.

Ví dụ:

~~~bash
APP_ENV=staging
SERVER_PORT=8080
LOG_LEVEL=INFO
DATABASE_URL=jdbc:postgresql://db-staging.internal:5432/orders
DATABASE_SECRET_REF=orders-db-staging
~~~

Tuy nhiên, environment variable có một số giới hạn:

- Hầu hết giá trị được process nhận dưới dạng chuỗi và cần parse, validate.
- Tên biến có thể khác giữa local, container và CI nếu không chuẩn hóa.
- Giá trị có thể bị ghi ra log nếu script in toàn bộ environment.
- Một số nền tảng truyền biến qua process metadata hoặc cấu hình deployment mà quyền đọc cần được kiểm soát.
- Thay đổi environment variable thường cần restart hoặc rollout để process nhận giá trị mới.
- Biến môi trường có thể bị override bởi nguồn cấu hình khác theo precedence của framework.

Nên chuẩn hóa tên biến, kiểu dữ liệu sau parse, giá trị mặc định và hành vi khi thiếu. Với cấu hình bắt buộc, ứng dụng nên báo lỗi rõ khi khởi động thay vì âm thầm dùng một default nguy hiểm.

Không dùng environment variable để truyền secret nếu nền tảng có cơ chế secret mount hoặc workload identity phù hợp hơn. Nếu vẫn dùng biến môi trường cho secret, cần hiểu cách process, runner và log quản lý chúng.

## 10. Quản lý secrets tách biệt với cấu hình thông thường

Secret bao gồm password, API token, private key, certificate material và credential khác. Những giá trị này cần cơ chế bảo vệ khác với cấu hình không nhạy cảm.

Thực hành nên áp dụng:

1. Lưu secret trong secret manager hoặc hệ thống được phê duyệt.
2. Repository chỉ lưu tên tham chiếu hoặc metadata không nhạy cảm.
3. Cấp secret theo workload, job và môi trường.
4. Dùng quyền tối thiểu và credential ngắn hạn khi có thể.
5. Không ghi plaintext secret vào log, artifact, test report hoặc approval snapshot.
6. Có quy trình rotate và revoke.
7. Theo dõi version hoặc metadata của secret nếu cần truy vết.
8. Không cấp secret production cho job chạy trên pull request không tin cậy.

Một file cấu hình có thể chứa:

~~~yaml
database:
  credentials:
    secret-reference: orders-db-production
~~~

Ứng dụng hoặc deployment platform sẽ lấy giá trị từ secret manager theo danh tính và quyền được cấp. Cách tham chiếu này giúp cấu hình có thể version mà không đưa bí mật vào Git.

Khi secret được xoay vòng, cần xác định ứng dụng nhận giá trị mới bằng cách nào: restart, reload, sidecar, volume update hoặc API của secret manager. Không nên giả định mọi process tự động nhận secret mới ngay lập tức.

## 11. Kiểm tra cấu hình trong pipeline CI/CD

Cấu hình nên được kiểm tra trước khi tác động đến môi trường dùng chung hoặc production.

Một pipeline tham khảo:

~~~mermaid
flowchart TD
    A["Pull request cấu hình"] --> B["Parse và format check"]
    B --> C["Schema validation"]
    C --> D["Type, range và cross-field checks"]
    D --> E["Policy validation"]
    E --> F["Resolve cấu hình theo môi trường"]
    F --> G["Render manifest / deployment plan"]
    G --> H["Review diff và impact"]
    H --> I{"Required checks đạt?"}
    I -- "Không" --> X["Chặn merge và báo lỗi"]
    I -- "Có" --> J["Merge revision"]
    J --> K["Deploy vào môi trường kiểm thử"]
    K --> L["Runtime validation và smoke checks"]
    L --> M{"Hoạt động đúng?"}
    M -- "Không" --> N["Dừng rollout / khôi phục"]
    M -- "Có" --> O["Promote revision theo policy"]
~~~

Các bước kiểm tra có thể gồm:

| Bước | Nội dung | Bằng chứng |
|---|---|---|
| Parse | Kiểm tra cú pháp YAML/JSON/template | Parse result |
| Schema | Kiểm tra trường, kiểu và cấu trúc | Schema validation report |
| Semantic | Kiểm tra miền giá trị và quan hệ trường | Validation result |
| Policy | Kiểm tra quy tắc bảo mật và vận hành | Policy report |
| Resolve | Hợp nhất base, environment và override | Resolved config fingerprint |
| Render | Sinh manifest hoặc deployment plan | Rendered output/diff |
| Test | Chạy test với cấu hình dự kiến | Test report |
| Deploy | Áp dụng revision được chấp nhận | Deployment ID và config revision |
| Verify | Xác nhận cấu hình thực tế và hành vi | Runtime config revision, health result |

Nếu cấu hình được render từ template, cần kiểm tra cả template và đầu ra sau khi render. Một template hợp lệ vẫn có thể tạo manifest không hợp lệ khi dữ liệu đầu vào thiếu hoặc sai kiểu.

Không nên để pipeline deploy cấu hình chỉ vì file parse được. Cần có schema, policy và kiểm tra tương thích với môi trường đích.

## 12. Kiểm tra cấu hình khi ứng dụng khởi động và khi runtime

CI validation không thay thế hoàn toàn runtime validation. Cấu hình cuối cùng còn có thể bị thay đổi bởi secret manager, environment variable, config service hoặc nền tảng triển khai.

### 12.1. Startup validation

Khi ứng dụng khởi động, cần kiểm tra:

- Trường bắt buộc có giá trị.
- Giá trị có đúng kiểu và miền cho phép.
- URI, duration và danh sách được parse đúng.
- Các cặp cấu hình có quan hệ với nhau thỏa điều kiện.
- Secret reference có thể resolve theo quyền được cấp.
- Dependency cần thiết có thể được truy cập hoặc ít nhất ở trạng thái phù hợp.

Nếu cấu hình bắt buộc không hợp lệ, ứng dụng nên fail fast với thông báo chỉ ra trường hoặc quy tắc lỗi. Không nên log giá trị nhạy cảm.

### 12.2. Readiness và health checks

Không phải mọi dependency đều cần kết nối ngay trong lúc parse cấu hình. Có thể dùng readiness check để xác nhận ứng dụng đã sẵn sàng phục vụ.

Ví dụ:

- Database có thể kết nối và schema tương thích.
- Message broker có thể truy cập.
- Certificate còn hiệu lực.
- Endpoint dependency nằm trong allowlist và phản hồi theo yêu cầu.
- Runtime config revision đã được nạp thành công.

Health check cần phân biệt lỗi cấu hình với sự cố tạm thời của dependency để hỗ trợ chẩn đoán.

### 12.3. Dynamic configuration

Một số giá trị có thể thay đổi khi ứng dụng đang chạy, như feature flag hoặc ngưỡng nghiệp vụ. Khi hỗ trợ dynamic configuration, cần xác định:

- Revision nào đang được process sử dụng.
- Cấu hình được áp dụng nguyên tử hay từng phần.
- Nếu tải cấu hình mới thất bại thì giữ cấu hình cũ hay dừng hoạt động.
- Có validate trước khi áp dụng không.
- Có cần restart cho một số trường hay không.
- Làm thế nào quan sát và khôi phục revision trước.

Không nên áp dụng từng trường cấu hình rời rạc nếu trạng thái trung gian có thể vi phạm invariant. Tốt hơn là resolve và validate toàn bộ cấu hình mới, sau đó chuyển sang revision mới một cách nhất quán.

## 13. Phát hiện configuration drift

Configuration drift xảy ra khi cấu hình thực tế của môi trường khác với cấu hình được quản trị hoặc được phê duyệt.

Nguyên nhân phổ biến:

- Người vận hành sửa trực tiếp trên máy chủ hoặc cluster.
- Một pipeline khác áp dụng manifest cũ.
- Config service bị thay đổi ngoài quy trình review.
- Giá trị mặc định của chart hoặc module IaC được cập nhật.
- Secret reference được chuyển sang version mới.
- Một thay đổi khẩn cấp không được đồng bộ lại về repository.

Drift có thể làm môi trường production khác staging dù cùng chạy một artifact. Khi xảy ra sự cố, việc tái tạo hành vi trở nên khó khăn.

Có thể phát hiện drift bằng cách:

1. Resolve cấu hình mong muốn từ revision đã được phê duyệt.
2. Thu thập trạng thái thực tế từ environment hoặc config service.
3. Chuẩn hóa hai tập cấu hình theo cùng quy tắc.
4. So sánh field và fingerprint.
5. Phân loại khác biệt theo mức độ ảnh hưởng.
6. Cảnh báo hoặc tạo yêu cầu khôi phục.
7. Ghi nhận người hoặc workload tạo ra thay đổi nếu nền tảng cung cấp audit log.

Không nên tự động ghi đè mọi drift mà chưa phân loại. Có thể có thay đổi khẩn cấp được phê duyệt tạm thời. Cần có quy trình break-glass: ghi lý do, người thực hiện, thời hạn và yêu cầu đồng bộ lại cấu hình về nguồn sự thật.

Với môi trường được quản lý bằng GitOps, controller có thể liên tục so sánh trạng thái mong muốn và trạng thái thực tế. Chính sách reconcile cần được xác định rõ: tự sửa drift, cảnh báo hay yêu cầu người vận hành xử lý.

## 14. Promote cấu hình giữa các môi trường

Một quy trình phát hành thường đưa cùng artifact qua dev, staging và production. Cấu hình môi trường có thể khác nhau, nhưng cần được quản lý và kiểm tra theo cùng một hợp đồng.

Có hai mô hình thường gặp:

**Một revision chung với overlay theo môi trường:** dùng cấu hình base và các phần override cho dev, staging, production. Pipeline resolve ra cấu hình cuối cùng cho từng môi trường.

**Revision riêng cho từng môi trường:** mỗi môi trường có một revision được quản lý và phê duyệt riêng. Cách này phù hợp khi mức độ khác biệt hoặc quyền thay đổi giữa các môi trường lớn.

Dù dùng mô hình nào, nên giữ:

- Schema và quy tắc validation thống nhất.
- Khác biệt môi trường được khai báo rõ.
- Giá trị production được review và bảo vệ riêng.
- Artifact được định danh độc lập với config revision.
- Bằng chứng kiểm thử gắn với artifact và cấu hình đã dùng.
- Cách promote hoặc rollback cấu hình có thể truy vết.

Không nên copy nguyên file staging sang production rồi sửa thủ công một vài giá trị trên cluster. Hãy tạo revision production từ nguồn được quản trị, render và kiểm tra diff trước khi áp dụng.

## 15. Rollback cấu hình và xử lý thay đổi khẩn cấp

Cấu hình sai có thể gây sự cố dù artifact không đổi. Vì vậy, rollback không chỉ là quay lại image trước đó.

Một kế hoạch khôi phục cấu hình cần xác định:

- Revision cấu hình gần nhất được biết là tốt.
- Artifact nào tương thích với revision đó.
- Secret reference/version nào còn hiệu lực.
- Có migration hoặc thay đổi trạng thái không thể đảo ngược hay không.
- Cách áp dụng revision cũ và xác minh sau khi khôi phục.
- Ai có quyền thực hiện rollback.

Không phải mọi cấu hình cũ đều an toàn để khôi phục. Credential cũ có thể đã bị revoke; endpoint cũ có thể đã ngừng hoạt động; schema database có thể đã được nâng cấp. Cần kiểm tra tương thích trước khi rollback.

Với thay đổi khẩn cấp, có thể cho phép break-glass theo chính sách:

1. Xác định sự cố và phạm vi thay đổi tối thiểu.
2. Ghi actor, lý do, ticket hoặc incident ID.
3. Áp dụng thay đổi với quyền giới hạn.
4. Xác minh hành vi và theo dõi.
5. Tạo commit hoặc revision chính thức phản ánh trạng thái đã thay đổi.
6. Review hậu kiểm và loại bỏ ngoại lệ tạm thời.

Break-glass không nên trở thành kênh cấu hình thường xuyên. Nếu một thay đổi khẩn cấp được giữ lại, nó phải được đưa về nguồn sự thật để tránh drift kéo dài.

## 16. Ví dụ pipeline kiểm tra và triển khai cấu hình

YAML dưới đây mô tả logic tổng quát, không phải cú pháp trực tiếp của một nền tảng CI/CD cụ thể:

~~~yaml
configuration_pipeline:
  trigger:
    - pull_request
    - merge_to_main

  validate:
    steps:
      - parse_configuration
      - validate_schema
      - validate_types_and_ranges
      - validate_cross_field_constraints
      - validate_environment_policy
      - scan_for_plaintext_secrets

  resolve:
    steps:
      - load_base_configuration
      - load_environment_overlay
      - resolve_allowed_overrides
      - resolve_secret_references
      - create_config_fingerprint

  preview:
    steps:
      - render_deployment_manifest
      - compare_with_current_environment
      - publish_diff_and_validation_report

  deploy:
    requires:
      - validation_passed
      - policy_passed
      - approval_if_required
    steps:
      - apply_versioned_configuration
      - record_config_revision
      - run_startup_and_readiness_checks
      - verify_effective_configuration

  on_failure:
    steps:
      - stop_rollout
      - retain_previous_known_good_revision
      - record_failure_and_changed_fields
~~~

Pipeline cần bảo đảm dữ liệu nhạy cảm không xuất hiện trong report hoặc diff được publish. Có thể hiển thị secret reference và version metadata thay cho giá trị thực.

Nếu cấu hình được tải từ nhiều nguồn, bước resolve phải dùng đúng quy tắc precedence của runtime. Nếu pipeline và ứng dụng hợp nhất cấu hình theo hai cách khác nhau, validation ở CI có thể không đại diện cho giá trị thực tế mà ứng dụng nhận được.

## 17. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Sửa trực tiếp trên production | Không có lịch sử và dễ tạo drift | Thay đổi qua nguồn được quản trị và pipeline |
| Không có schema | Sai kiểu hoặc thiếu trường chỉ bị phát hiện khi chạy | Thêm schema validation |
| Dùng default cho mọi lỗi cấu hình | Ứng dụng có thể chạy với giá trị nguy hiểm | Fail fast với trường bắt buộc |
| Nhiều nguồn override không rõ | Không biết giá trị thực tế đến từ đâu | Định nghĩa precedence và resolve report |
| Lưu secret plaintext trong Git | Lộ credential và khó thu hồi | Dùng secret manager và reference |
| Dùng chung một file cho mọi môi trường | Cấu hình sai endpoint hoặc quyền | Base plus environment overlays |
| Chỉ kiểm tra file nguồn | Bỏ sót lỗi sau khi render hoặc merge | Validate resolved configuration |
| Không ghi config revision | Khó tái tạo hành vi production | Gắn revision/fingerprint với deployment |
| Tự động sửa mọi drift | Có thể ghi đè thay đổi khẩn cấp hợp lệ | Phân loại, audit và reconcile theo policy |
| Rollback image nhưng giữ config lỗi | Dịch vụ vẫn có thể tiếp tục lỗi | Khôi phục cặp artifact/config tương thích |
| Dynamic config áp dụng từng phần | Trạng thái trung gian không nhất quán | Validate toàn bộ và áp dụng nguyên tử |

## 18. Checklist quản lý phiên bản và xác thực cấu hình

Trước khi áp dụng cấu hình vào môi trường dùng chung hoặc production, hãy kiểm tra:

- [ ] Mỗi nhóm cấu hình có nguồn sự thật và owner rõ ràng.
- [ ] Cấu hình build-time, deploy-time và runtime được phân biệt.
- [ ] Revision hoặc fingerprint của cấu hình có thể truy vết.
- [ ] Khác biệt giữa các môi trường được khai báo có chủ đích.
- [ ] Quy tắc precedence và merge được ghi rõ.
- [ ] Cấu hình được parse và kiểm tra schema.
- [ ] Kiểu dữ liệu, miền giá trị và ràng buộc liên trường được xác minh.
- [ ] Policy production được kiểm tra tự động.
- [ ] Secret không nằm trong Git, log hoặc artifact dưới dạng plaintext.
- [ ] Secret reference và version metadata được quản lý an toàn.
- [ ] Cấu hình sau khi resolve/render được kiểm tra.
- [ ] Startup validation và readiness checks phản ánh đúng điều kiện runtime.
- [ ] Runtime config revision có thể quan sát.
- [ ] Có phát hiện và xử lý configuration drift.
- [ ] Có audit trail cho thay đổi và break-glass.
- [ ] Có revision tốt đã biết và kế hoạch rollback tương thích.
- [ ] Artifact digest và config revision được ghi nhận riêng trong deployment evidence.

## 19. Bài tập tự đánh giá

Một dịch vụ API chạy trên ba môi trường dev, staging và production. Ứng dụng dùng file application.yml, environment variables và một config service. Trong một lần phát hành:

- Staging chạy tốt nhưng production không kết nối được database.
- File cấu hình trong Git có đúng database host, nhưng một environment variable cũ vẫn override giá trị đó.
- Một người vận hành sửa trực tiếp timeout trên cluster để xử lý sự cố.
- Revision config service không được ghi vào deployment record.
- Một secret vừa được rotate nhưng ứng dụng vẫn giữ kết nối cũ.

Hãy phân tích:

1. Nguồn nào đang cung cấp giá trị database host cuối cùng?
2. Làm thế nào xác định và công bố precedence của các nguồn cấu hình?
3. Cần kiểm tra những gì ở schema, miền giá trị và runtime?
4. Vì sao validation chỉ trên file Git chưa đủ?
5. Làm thế nào đưa thay đổi timeout khẩn cấp về nguồn sự thật?
6. Deployment record cần lưu những revision nào?
7. Secret rotation cần cơ chế reload hoặc restart ra sao?
8. Làm thế nào phát hiện drift giữa Git, config service và cluster?
9. Nếu cần rollback, cần kiểm tra tương thích giữa artifact, config revision và secret version như thế nào?

Một thiết kế tốt phải chỉ ra được giá trị cuối cùng đến từ đâu, ai sở hữu nó, nó đã được kiểm tra ra sao và revision nào đang thực sự được ứng dụng sử dụng.

## Kết luận

Quản lý cấu hình theo phiên bản giúp đội ngũ biết thay đổi nào đã được review, revision nào đang chạy và cách khôi phục khi có lỗi. Kiểm tra tính hợp lệ cần đi từ cú pháp, schema và kiểu dữ liệu đến miền giá trị, ràng buộc liên trường, dependency và policy môi trường.

Trong CI/CD, hãy resolve cấu hình theo một quy tắc precedence rõ ràng, kiểm tra cả nội dung sau render, bảo vệ secret bằng cơ chế riêng và ghi nhận config revision cùng artifact trong deployment evidence. Khi phát hiện drift, cần phân loại và xử lý theo chính sách; khi rollback, phải xác nhận cấu hình cũ còn tương thích. Nhờ vậy, cùng một artifact có thể được vận hành nhất quán trong từng môi trường với cấu hình có thể kiểm chứng và truy vết.


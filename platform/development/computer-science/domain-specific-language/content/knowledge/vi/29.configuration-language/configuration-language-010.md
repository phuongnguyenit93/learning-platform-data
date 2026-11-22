# Khả năng truy vết

## 1. Khả năng truy vết trong DSL cấu hình là gì?

Trong một hệ thống dùng DSL (*Domain-Specific Language*) để khai báo cấu hình, một giá trị thường không đến từ một nơi duy nhất. Nó có thể được đặt mặc định trong chương trình, khai báo trong file cấu hình, ghi đè theo môi trường, nhận từ biến môi trường, truyền qua command line, lấy từ remote configuration service hoặc được đọc từ secret manager.

Khi hệ thống hoạt động, người vận hành cần trả lời những câu hỏi như:

- Giá trị hiệu lực của `database.poolSize` hiện là bao nhiêu?
- Giá trị đó được khai báo ở file và dòng nào?
- Nó đến từ default, file cấu hình, environment variable hay remote override?
- Có nguồn nào đã ghi đè giá trị trước đó không?
- Một giá trị dẫn xuất phụ thuộc vào những key nào?
- Thành phần nào đang sử dụng key đó?
- Phiên bản cấu hình nào đã được áp dụng cho một request hoặc instance?
- Ai đã thay đổi cấu hình, thay đổi lúc nào và thông qua kênh nào?
- Có thể tái tạo chính xác cấu hình của một lần chạy cũ hay không?

**Khả năng truy vết (*traceability*)** là khả năng theo dõi mối liên hệ giữa khai báo ban đầu, các phép biến đổi và ghi đè, giá trị cấu hình cuối cùng, các thành phần sử dụng giá trị đó và những thay đổi xảy ra trong vòng đời cấu hình.

Một phần quan trọng của traceability là **provenance**: thông tin về nguồn gốc và lịch sử hình thành của một giá trị. Ví dụ, nếu `request.timeout` cuối cùng là `8s`, provenance có thể cho biết giá trị mặc định là `3s`, file môi trường staging đặt thành `5s`, và biến môi trường ghi đè thành `8s`.

Traceability giúp cấu hình trở nên có thể giải thích, kiểm toán, tái lập và điều tra. Nó đặc biệt hữu ích khi cùng một DSL được dùng trên nhiều môi trường, nhiều tenant, nhiều service hoặc nhiều phiên bản triển khai.

## 2. Traceability khác logging và configuration history như thế nào?

Các khái niệm này liên quan nhưng giải quyết những câu hỏi khác nhau.

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| Traceability | Giá trị này đến từ đâu và được dùng ở đâu? | `poolSize` được ghi đè bởi env var và được connection pool sử dụng |
| Logging | Sự kiện nào đã xảy ra trong lúc chạy? | Runtime nạp cấu hình version 42 thành công |
| Configuration history | Cấu hình đã thay đổi qua các phiên bản ra sao? | Version 41 đổi timeout từ 3s thành 5s |
| Audit trail | Ai thực hiện thay đổi và có quyền gì? | Operator A phê duyệt override cho production |
| Runtime observability | Cấu hình ảnh hưởng đến hành vi hệ thống thế nào? | Pool saturation tăng sau khi giảm pool size |

Một log có thể nói rằng runtime đã nạp cấu hình thành công, nhưng không nhất thiết giải thích tại sao một key có giá trị cụ thể. Một lịch sử version có thể cho biết giá trị đã đổi, nhưng không nhất thiết chỉ ra dòng source tạo ra nó hoặc component đang sử dụng nó.

Một hệ thống traceability tốt liên kết các thông tin đó qua key identity, source location, configuration version, provenance record và runtime consumer.

## 3. Các loại đối tượng cần truy vết

### 3.1. Configuration key

Configuration key là định danh của một mục cấu hình, ví dụ:

~~~text
database.poolSize
http.requestTimeout
feature.checkoutV2.enabled
logging.level
service.payment.endpoint
~~~

Key nên có identity ổn định. Tên hiển thị có thể đổi qua migration, nhưng hệ thống cần cách liên kết key cũ và key mới.

### 3.2. Declared value

Declared value là giá trị được khai báo tại một nguồn cụ thể. Một key có thể có nhiều declared values từ nhiều nguồn khác nhau.

Ví dụ:

~~~yaml
# defaults.yml
database:
  poolSize: 10
~~~

~~~yaml
# production.yml
database:
  poolSize: 30
~~~

Hai khai báo cùng thuộc key database.poolSize nhưng có source location và source identity khác nhau.

### 3.3. Effective value

Effective value là giá trị mà runtime thực sự sử dụng sau khi áp dụng precedence, merge, interpolation, conversion và validation.

Không nên coi effective value chỉ là một scalar. Để truy vết, cần lưu cả giá trị đã resolve và đường đi tạo ra nó.

### 3.4. Source

Source là nơi cung cấp một khai báo hoặc override. Các source phổ biến:
- Built-in default.
- Base configuration file.
- Environment-specific file.
- Environment variable.
- Command-line argument.
- Remote configuration service.
- Database hoặc configuration registry.
- Secret manager.
- Programmatic override từ host application.
- Runtime-generated value.

Mỗi source cần một định danh và metadata đủ để phân biệt với source khác.

### 3.5. Consumer

Consumer là thành phần đọc hoặc sử dụng một configuration key:
- HTTP server.
- Database pool.
- Message broker client.
- Feature flag evaluator.
- Logging subsystem.
- Workflow engine.
- Một module hoặc service trong ứng dụng.

Traceability nên liên kết được key với consumer, đặc biệt khi một thay đổi có thể ảnh hưởng nhiều thành phần.

## 4. Configuration pipeline và các điểm tạo provenance

Một configuration DSL thường đi qua pipeline:

~~~text
Built-in defaults
       |
       v
Configuration files
       |
       v
Environment overlays
       |
       v
Environment variables / CLI
       |
       v
Remote sources / Secret references
       |
       v
Merge and precedence resolution
       |
       v
Interpolation and expression evaluation
       |
       v
Type conversion and validation
       |
       v
Effective configuration snapshot
       |
       v
Runtime consumers
~~~

Mỗi bước có thể làm thay đổi giá trị hoặc cách diễn giải giá trị. Nếu chỉ ghi provenance ở cuối pipeline, hệ thống sẽ không giải thích được một override đến từ đâu. Nếu chỉ ghi source ban đầu, hệ thống không biết giá trị cuối cùng đã bị biến đổi thế nào.

Do đó, cần theo dõi provenance xuyên suốt các bước.

### 4.1. Nạp nguồn

Khi đọc một source, parser hoặc loader nên tạo metadata:
- Source ID.
- Source type.
- URI, file path hoặc resource name.
- Version, revision hoặc ETag nếu có.
- Environment hoặc tenant scope.
- Thời điểm đọc.
- Actor hoặc service identity nếu có.
- Source range của từng khai báo.

### 4.2. Merge và precedence

Khi nhiều nguồn cùng khai báo một key, resolver chọn giá trị hiệu lực theo chính sách đã định nghĩa. Provenance cần lưu cả winner và những candidate bị ghi đè.

### 4.3. Interpolation

Một giá trị có thể tham chiếu key khác:

~~~text
database.url = "jdbc:postgresql://${database.host}:${database.port}/app"
~~~

Provenance của database.url cần liên kết với database.host và database.port, vì thay đổi một trong hai có thể làm URL thay đổi.

### 4.4. Conversion và validation

Giá trị từ file hoặc environment variable có thể bắt đầu dưới dạng text rồi được chuyển thành integer, duration, URI hoặc domain type. Cần lưu nguồn text, phép conversion và kết quả đã kiểm tra.

### 4.5. Snapshot

Sau khi cấu hình được resolve và validate, hệ thống có thể tạo một immutable configuration snapshot. Snapshot là đơn vị quan trọng để liên kết runtime execution với đúng cấu hình đã dùng.

## 5. Precedence và override trace

### 5.1. Vì sao precedence phải rõ ràng?

Một key có thể được khai báo nhiều lần. Nếu precedence không được xác định rõ, hai môi trường có thể chọn giá trị khác nhau do thứ tự nạp file, thứ tự iteration hoặc hành vi của thư viện.

Một chính sách ví dụ:

| Thứ tự ưu tiên | Nguồn |
|---:|---|
| 1 - cao nhất | Command-line override |
| 2 | Environment variable |
| 3 | Remote environment configuration |
| 4 | Environment-specific file |
| 5 | Base configuration |
| 6 - thấp nhất | Built-in default |

Đây chỉ là một ví dụ. Hệ thống cần công bố precedence thực tế và không nên để người dùng phải suy đoán.

### 5.2. Override chain

Giả sử key database.poolSize có các khai báo:

~~~yaml
# defaults.yml
database:
  poolSize: 10
~~~

~~~yaml
# staging.yml
database:
  poolSize: 20
~~~

~~~text
APP_DATABASE_POOLSIZE=40
~~~

Override chain có thể được trình bày:

~~~text
database.poolSize

default       10  defaults.yml:2
staging       20  staging.yml:2
environment   40  APP_DATABASE_POOLSIZE

effective     40  <- selected
~~~

Người vận hành có thể thấy tất cả candidate và lý do environment variable thắng.

### 5.3. Winner và shadowed values

Một provenance record nên phân biệt:
- Selected source: nguồn thắng theo precedence.
- Shadowed source: nguồn bị ghi đè.
- Rejected source: nguồn không được dùng do sai kiểu, không hợp lệ hoặc không thuộc scope.
- Fallback source: nguồn được dùng khi nguồn ưu tiên không có giá trị, nếu policy cho phép.

Không nên gộp mọi nguồn không thắng thành một loại, vì lý do không thắng khác nhau.

### 5.4. Null, absent và empty

Ba trạng thái có thể khác nhau:
- Absent: key không được khai báo.
- Null: key được khai báo với giá trị null.
- Empty: key có giá trị rỗng như chuỗi rỗng hoặc collection rỗng.

Một số resolver cho phép null ghi đè giá trị thấp hơn; hệ thống khác coi null là không có giá trị. Cần định nghĩa rõ để trace giải thích đúng.

### 5.5. Merge semantics

Không phải mọi cấu trúc đều dùng last-write-wins. Với map, list hoặc object, hệ thống có thể:
- Replace toàn bộ.
- Merge theo key.
- Append list.
- Merge sâu theo field.
- Xóa key bằng tombstone.
- Từ chối xung đột.

Traceability phải ghi loại phép merge và các nguồn đóng góp cho từng field. Nếu chỉ lưu một source cho cả object, thông tin nguồn gốc của từng thuộc tính sẽ bị mất.

## 6. Provenance record

Một provenance record mô tả cách một giá trị được tạo ra. Ví dụ schema khái niệm:

~~~json
{
  "configKey": "database.poolSize",
  "effectiveValue": 40,
  "valueType": "Integer",
  "selectedSource": {
    "sourceId": "env:production",
    "kind": "ENVIRONMENT_VARIABLE",
    "name": "APP_DATABASE_POOLSIZE"
  },
  "overrides": [
    {
      "sourceId": "file:defaults",
      "location": "defaults.yml:2",
      "value": 10,
      "selected": false
    },
    {
      "sourceId": "file:production",
      "location": "production.yml:2",
      "value": 30,
      "selected": false
    }
  ],
  "resolutionPolicy": "ENVIRONMENT_OVERRIDES_FILE",
  "snapshotId": "config-snapshot-42"
}
~~~

Schema thực tế có thể khác, nhưng nên lưu được các nhóm thông tin sau.

### 6.1. Key identity

- Stable key ID.
- Canonical key path.
- Display name.
- Namespace/module.
- Data type.
- Schema version.

### 6.2. Source metadata

- Source ID.
- Source type.
- Source URI hoặc resource name.
- Source revision.
- Environment/tenant.
- Actor hoặc service identity.
- Source location.
- Timestamp nạp.

### 6.3. Resolution metadata

- Precedence rank.
- Merge operation.
- Selected/rejected/shadowed state.
- Conversion function.
- Defaulting rule.
- Validation result.
- Resolver version.

### 6.4. Lineage metadata

- Parent configuration keys.
- Expression hoặc interpolation node.
- Dependency edges.
- Transformation steps.
- Snapshot ID.
- Runtime consumer references.

### 6.5. Value representation

Giá trị có thể được lưu trực tiếp nếu không nhạy cảm. Với secret hoặc dữ liệu hạn chế, provenance nên lưu reference, fingerprint hoặc trạng thái thay vì raw value.

## 7. Source location và truy ngược về khai báo

Traceability hữu ích khi người dùng có thể nhảy từ một effective key về nơi khai báo.

Một source location có thể chứa:
- URI hoặc path.
- Start line và column.
- End line và column.
- Document version.
- Module hoặc package.
- Source kind.
- Generated/source mapping nếu có.

Ví dụ:

~~~text
database.poolSize
  effective value: 40
  source: APP_DATABASE_POOLSIZE
  overridden:
    defaults.yml:2
    production.yml:2
~~~

Với file cấu hình DSL, editor có thể mở đúng file và highlight range của key hoặc value.

### 7.1. Includes và imports

Một file có thể include file khác:

~~~text
include "common.dsl"
include "environment/production.dsl"
~~~

Nếu giá trị đến từ file được include, trace cần giữ cả:
- Vị trí include trong file cha.
- Vị trí khai báo trong file con.
- Đường dẫn include chain.
- Phiên bản hoặc revision của file con.

Điều này giúp giải thích vì sao một file xuất hiện trong effective configuration dù người vận hành không mở nó trực tiếp.

### 7.2. Generated configuration

Một tool có thể sinh file cấu hình từ template hoặc model. Khi đó, source location ở generated file chưa đủ. Cần source map liên kết generated range về template, model element hoặc generator input.

### 7.3. Remote source

Remote configuration có thể không có line/column. Có thể dùng:
- Resource key.
- Document ID.
- Revision hoặc ETag.
- JSON pointer hoặc field path.
- API endpoint/service identity.

Traceability không nên giả định mọi nguồn đều là file trên filesystem.

## 8. Truy vết giá trị dẫn xuất và interpolation

### 8.1. Derived values

Một giá trị có thể được tính từ nhiều key:

~~~text
service.url = "https://" + service.host + ":" + service.port
~~~

Nếu service.url sai, người vận hành cần biết:
- Biểu thức nào tạo ra nó.
- service.host và service.port lấy từ đâu.
- Conversion hoặc normalization nào đã chạy.
- Phần nào của biểu thức gây lỗi.

### 8.2. Dependency graph

Có thể biểu diễn quan hệ:

~~~text
service.host --------+
                    |
                    +----> service.url
                    |
service.port --------+

tls.enabled --------> service.scheme
service.scheme ------> service.url
~~~

Graph cho phép:
- Truy ngược từ output đến input.
- Truy xuôi từ key thay đổi đến các key bị ảnh hưởng.
- Phát hiện dependency cycle.
- Tính lại phần cấu hình cần thiết.
- Giải thích tác động của một override.

### 8.3. Dependency edge

Một edge có thể chứa:
- Source key ID.
- Target key ID.
- Expression node hoặc source range.
- Dependency type.
- Transformation step.
- Evaluation order.
- Whether dependency is conditional.

Dependency có điều kiện cần được biểu diễn nếu chỉ một nhánh expression được đánh giá trong một context.

### 8.4. Cycle detection

Ví dụ:

~~~text
service.a = service.b + 1
service.b = service.c + 1
service.c = service.a + 1
~~~

Đây là dependency cycle nếu DSL không định nghĩa semantics đặc biệt cho vòng lặp. Resolver nên phát diagnostic có đường đi cycle:

~~~text
service.a -> service.b -> service.c -> service.a
~~~

Diagnostic nên trỏ về các source ranges tạo cạnh, không chỉ báo chung là circular reference.

### 8.5. Evaluation trace

Với expression phức tạp, có thể lưu trace các bước:
1. Resolve service.host.
2. Resolve service.port.
3. Convert port thành integer.
4. Evaluate concatenation.
5. Validate URL.
6. Gán service.url.

Trace này giúp phân biệt lỗi nguồn dữ liệu với lỗi biểu thức hoặc conversion.

## 9. Explain Effective Configuration

Một chức năng quan trọng là cho phép truy vấn vì sao key có giá trị hiện tại.

Ví dụ output:

~~~text
Key: http.requestTimeout
Effective value: 8s
Type: Duration
Snapshot: config-42

Resolution:
  1. Built-in default: 3s
  2. base.dsl: 5s
  3. production.dsl: 6s
  4. APP_HTTP_TIMEOUT: 8s  [selected]

Reason:
  Environment variables have higher precedence than files.

Consumers:
  - HttpClient
  - ApiGateway
~~~

### 9.1. Explain theo key

API hoặc CLI có thể nhận key path và trả:
- Effective value hoặc redacted state.
- Selected source.
- Các override trước đó.
- Merge/precedence policy.
- Dependency parents.
- Consumer list.
- Snapshot version.
- Validation status.

### 9.2. Explain theo source

Người dùng cũng có thể chọn một dòng khai báo và hỏi:
- Giá trị này có đang được dùng không?
- Nó bị nguồn nào ghi đè?
- Những key nào phụ thuộc vào nó?
- Nó có được nạp vào runtime nào?

Đây là góc nhìn ngược của truy vết.

### 9.3. Explain theo consumer

Khi một service có cấu hình sai, có thể xem tất cả key mà consumer đọc và nguồn tạo ra từng giá trị. Điều này giúp tránh phải tìm từng key trong nhiều file.

### 9.4. Output phải thể hiện độ đầy đủ

Nếu một source không được index hoặc một remote revision không truy cập được, Explain API phải đánh dấu provenance incomplete. Không nên trình bày một phần dữ liệu như thể đã truy vết đầy đủ.

## 10. Runtime lineage: từ cấu hình đến hành vi

Traceability không dừng ở thời điểm parse hoặc resolve. Một giá trị hiệu lực cần được liên kết với runtime component đã nhận nó.

Ví dụ:

~~~text
production.dsl
      |
      v
Configuration snapshot 42
      |
      +---- database.poolSize = 40
      |          |
      |          v
      |      DatabasePool instance A
      |
      +---- http.requestTimeout = 8s
      |          |
      |          v
      |      HttpClient instance B
      |
      +---- feature.checkoutV2 = true
                 |
                 v
             Checkout service
~~~

Runtime lineage có thể ghi:
- Snapshot ID.
- Service/instance ID.
- Consumer ID.
- Key ID.
- Thời điểm apply.
- Apply result.
- Component version.
- Reload generation.
- Request hoặc execution correlation ID nếu cần.

### 10.1. Config snapshot ID

Mỗi lần cấu hình được resolve và publish nên có snapshot ID hoặc revision ổn định. Runtime component có thể ghi nhận snapshot đã nhận.

Khi sự cố xảy ra, operator có thể xác định instance đang dùng snapshot nào thay vì chỉ xem file cấu hình mới nhất trên repository.

### 10.2. Consumer registry

Consumer registry mô tả thành phần nào đăng ký sử dụng key nào. Có thể được khai báo tĩnh qua schema hoặc ghi nhận khi component bind configuration.

Ví dụ:

~~~text
HttpClient
  reads:
    http.requestTimeout
    http.maxConnections

DatabasePool
  reads:
    database.poolSize
    database.connectionTimeout
~~~

Registry giúp đánh giá blast radius trước khi thay đổi key.

### 10.3. Actual usage

Một key có thể được nạp nhưng không được đọc trong runtime. Cần phân biệt:
- Declared: có trong source.
- Resolved: có effective value.
- Delivered: được gửi đến consumer.
- Read: consumer thực sự đọc.
- Applied: component áp dụng thành công.
- Observed: có bằng chứng hành vi tương ứng.

Những trạng thái này không thể thay thế cho nhau. Ví dụ, một feature flag có thể được nạp nhưng không có request nào đi qua nhánh feature đó.

## 11. Change history và audit trail

### 11.1. Change event

Một thay đổi cấu hình quan trọng có thể được ghi thành event:

~~~json
{
  "event": "configuration.changed",
  "key": "http.requestTimeout",
  "oldValue": "5s",
  "newValue": "8s",
  "actor": "deployment-service",
  "source": "production.dsl",
  "revision": "rev-42",
  "timestamp": "2026-11-15T10:30:00Z"
}
~~~

Với secret, không ghi oldValue hoặc newValue dạng raw. Có thể lưu fingerprint hoặc chỉ ghi rằng reference/version đã thay đổi.

### 11.2. Actor và approval

Audit record có thể gồm:
- Actor ID hoặc service identity.
- Vai trò/quyền tại thời điểm thay đổi.
- Change request hoặc ticket reference.
- Reviewer/approver.
- Lý do thay đổi.
- Source channel.
- Timestamp.
- Revision trước và sau.

### 11.3. Append-only history

Nếu cần audit đáng tin cậy, lịch sử nên được lưu theo cách chống sửa/xóa trái phép, chẳng hạn append-only storage hoặc integrity checks. Một bảng log có thể chỉnh sửa bởi admin không tự động trở thành audit trail.

### 11.4. Change correlation

Một thay đổi có thể ảnh hưởng nhiều key hoặc nhiều service. Nên có change ID để liên kết:
- Commit hoặc configuration revision.
- Snapshot mới.
- Rollout operation.
- Instance acknowledgements.
- Alert hoặc incident phát sinh sau thay đổi.

### 11.5. Ai thay đổi và nguồn nào thắng?

Audit trả lời ai đã thay đổi dữ liệu. Provenance trả lời nguồn nào tạo ra effective value. Hai thông tin cần liên kết nhưng không nên nhập làm một. Một environment variable có thể ghi đè file mà không có người sửa file tại thời điểm runtime; actor của lần deploy và actor sửa file có thể khác nhau.

## 12. Truy vết secrets và dữ liệu nhạy cảm

Cấu hình thường chứa password, API token, certificate, private key hoặc connection string. Traceability không được biến thành kênh làm lộ secret.

### 12.1. Secret reference

Thay vì lưu secret trực tiếp:

~~~text
database.password = secret("vault/prod/database-password")
~~~

Provenance có thể lưu:
- Secret provider.
- Secret path hoặc resource ID.
- Version ID nếu provider hỗ trợ.
- Thời điểm resolve.
- Consumer nhận secret.
- Kết quả fetch/rotation.
- Fingerprint không thể đảo ngược nếu cần so sánh thay đổi.

Không lưu secret raw vào provenance, logs, diagnostics hoặc Explain API.

### 12.2. Redaction

Explain API có thể trả:

~~~text
database.password
  effective value: [REDACTED]
  source: secret://vault/prod/database-password
  version: 17
  resolved: true
  consumer: DatabasePool
~~~

Người dùng có quyền xem provenance không nhất thiết có quyền đọc secret.

### 12.3. Fingerprints

Nếu cần biết secret có thay đổi hay không, có thể dùng fingerprint an toàn theo chính sách bảo mật, hoặc provider version ID. Không dùng hash yếu của secret ngắn nếu có nguy cơ dò từ điển.

### 12.4. Access control

Phân quyền theo hành động:
- Xem key name.
- Xem source path.
- Xem secret metadata.
- Resolve secret.
- Xem giá trị raw (nếu có quy trình đặc biệt).
- Thay đổi reference hoặc rotation policy.

Mọi thao tác đặc quyền cần audit riêng.

## 13. Reproducibility và configuration snapshot

Để tái lập một lần chạy cũ, cần biết chính xác cấu hình nào đã được dùng.

Một snapshot có thể chứa:
- Snapshot ID.
- Effective configuration schema.
- Non-secret effective values.
- Secret references và version IDs.
- Source revisions.
- Resolver/merge policy version.
- DSL grammar/schema version.
- Application build/version.
- Environment identity.
- Timestamp.
- Provenance graph hoặc digest của graph.

### 13.1. Immutable snapshot

Sau khi publish, snapshot nên bất biến. Nếu cấu hình thay đổi, tạo snapshot mới thay vì sửa nội dung snapshot cũ.

Điều này giúp liên kết request hoặc runtime instance với cấu hình chính xác tại thời điểm xử lý.

### 13.2. Snapshot digest

Có thể tạo digest từ canonical representation của snapshot. Digest giúp:
- So sánh hai instance có dùng cùng config hay không.
- Phát hiện drift.
- Kiểm tra artifact đã được truyền nguyên vẹn.
- Liên kết config với deployment manifest.

Secret raw không nên được đưa trực tiếp vào digest representation có thể công khai. Dùng version reference hoặc một cơ chế fingerprint được thiết kế cho secrets.

### 13.3. Reproduce và external dependencies

Cùng một snapshot chưa chắc tạo cùng hành vi nếu chương trình phụ thuộc:
- Remote service response.
- Current time.
- Feature flag từ nguồn khác.
- Secret đã rotation nhưng không pin version.
- Runtime version.
- Environment variable chưa được ghi nhận.
- External schema hoặc database state.

Cần lưu dependency version hoặc reference phù hợp để biết mức độ có thể tái lập.

### 13.4. Snapshot completeness

Một snapshot cần ghi trạng thái đầy đủ/incomplete. Nếu remote source không trả revision hoặc secret provider không hỗ trợ pin version, khả năng tái lập bị giới hạn và cần thể hiện rõ.

## 14. Drift detection giữa môi trường

Traceability giúp so sánh cấu hình giữa development, staging và production.

Ví dụ:

| Key | Development | Staging | Production |
|---|---:|---:|---:|
| database.poolSize | 5 | 20 | 40 |
| http.requestTimeout | 3s | 5s | 8s |
| feature.checkoutV2 | false | true | true |

Một số khác biệt là có chủ ý. Drift detection cần phân biệt:
- Expected environment override.
- Unreviewed manual change.
- Missing key.
- Unexpected source.
- Different schema version.
- Different secret reference/version.
- Different effective value.

### 14.1. Compare source và effective value

So sánh file cấu hình không đủ vì environment variable hoặc remote source có thể ghi đè file. Nên so sánh cả:
- Source declarations.
- Effective values.
- Provenance chain.
- Snapshot version.
- Consumer application state.

### 14.2. Policy-based drift

Có thể định nghĩa policy:
- Key bắt buộc giống nhau giữa staging và production.
- Key được phép khác theo environment.
- Key không được phép đến từ command line trong production.
- Secret reference phải thuộc đúng vault path.
- Một số security settings phải có giá trị tối thiểu.

Policy violation nên có diagnostic chỉ rõ key, source và environment.

## 15. Dependency impact và change analysis

Khi một key thay đổi, hệ thống cần xác định các giá trị dẫn xuất và consumer có thể bị ảnh hưởng.

Ví dụ:

~~~text
database.host
      |
      v
database.url
      |
      v
DatabasePool

database.poolSize
      |
      v
DatabasePool
~~~

Thay database.host có thể ảnh hưởng database.url và DatabasePool. Thay database.poolSize ảnh hưởng DatabasePool nhưng không nhất thiết ảnh hưởng database.url.

### 15.1. Forward impact query

Truy vấn từ key thay đổi theo chiều downstream:
- Derived keys.
- Validation rules.
- Consumers.
- Services hoặc instances.
- Feature branches hoặc workflow components.

### 15.2. Reverse dependency query

Truy vấn từ consumer về upstream:
- Consumer đang dùng key nào?
- Key đó được tính từ những key nào?
- Những source nào đóng góp?
- Có secret reference nào liên quan?

### 15.3. Impact confidence

Dependency graph có thể không đầy đủ nếu code đọc cấu hình động bằng string key hoặc reflection. Hệ thống nên đánh dấu dependency được khai báo tĩnh, quan sát runtime hoặc suy đoán, thay vì tuyên bố mọi impact đều chính xác tuyệt đối.

## 16. Dynamic configuration và reload trace

Một số ứng dụng có thể thay cấu hình mà không restart.

Quy trình reload:

~~~text
New source revision
       |
       v
Parse and resolve
       |
       v
Validate candidate snapshot
       |
       v
Compare with active snapshot
       |
       v
Publish new snapshot
       |
       v
Notify consumers
       |
       v
Collect apply acknowledgements
       |
       v
Mark rollout state
~~~

### 16.1. Candidate và active snapshot

Candidate snapshot là cấu hình đang được kiểm tra. Active snapshot là cấu hình runtime đang sử dụng. Không nên coi candidate đã thành active trước khi validation và publish thành công.

### 16.2. Consumer acknowledgement

Consumer có thể:
- Applied: đã áp dụng.
- Rejected: không thể áp dụng.
- Pending: chưa phản hồi.
- Restart required: cần restart.
- Partially applied: chỉ áp dụng một phần.

Traceability cần ghi trạng thái từng consumer, không chỉ ghi rằng configuration service đã publish.

### 16.3. Mixed-version window

Trong quá trình rollout, một số instance có thể dùng snapshot mới và một số vẫn dùng snapshot cũ. Điều này cần được thể hiện qua instance ID và snapshot ID để điều tra hành vi không đồng nhất.

### 16.4. Atomic reload

Nếu nhiều key phụ thuộc lẫn nhau, cập nhật từng key riêng lẻ có thể tạo trạng thái trung gian không hợp lệ. Có thể publish toàn snapshot atomically hoặc dùng transaction/config generation để consumer chỉ nhìn thấy một version hoàn chỉnh.

## 17. Rollback và phục hồi

Rollback là chuyển runtime về một snapshot đã biết là hợp lệ. Traceability giúp xác định:
- Snapshot nào trước đó đang hoạt động.
- Thay đổi nào gây sự cố.
- Key nào khác nhau.
- Consumer nào đã nhận version mới.
- Instance nào đã rollback thành công.

Một quy trình rollback:

1. Chọn snapshot cũ đã được xác minh.
2. Kiểm tra compatibility với application version hiện tại.
3. Publish rollback revision mới tham chiếu snapshot cũ.
4. Thông báo consumer.
5. Thu thập acknowledgement.
6. Xác nhận instance đang dùng đúng snapshot.
7. Ghi audit event và incident/change correlation.

Không nên xóa lịch sử snapshot mới khi rollback. Snapshot gây lỗi vẫn cần được giữ để điều tra.

## 18. Diagnostics và cảnh báo provenance

Một cấu hình có thể có giá trị hợp lệ về kiểu nhưng provenance không phù hợp policy.

Ví dụ:
- Production key bị ghi đè bởi command-line argument không được phép.
- Secret đến từ vault path sai môi trường.
- Key quan trọng chỉ có built-in default.
- Hai source cùng precedence tạo xung đột.
- Derived value phụ thuộc vào một key chưa được resolve.
- Source remote không có revision để tái lập.
- File include nằm ngoài workspace được phép.

Diagnostic nên chứa:
- Key ID và path.
- Source hoặc source chain.
- Source location.
- Environment/tenant.
- Policy bị vi phạm.
- Severity.
- Gợi ý khắc phục.
- Snapshot hoặc revision liên quan.

Không nên chỉ đưa ra thông báo “invalid provenance” mà không giải thích nguồn nào và policy nào gây lỗi.

## 19. Kiến trúc traceability service

Một kiến trúc khái niệm:

~~~text
Configuration Sources
        |
        v
Source Loaders / Parsers
        |
        v
Provenance-aware Resolver
        |
        +------> Dependency Graph
        |
        +------> Source Map
        |
        v
Validated Configuration Snapshot
        |
        +------> Provenance Store
        |
        +------> Audit / History Store
        |
        v
Runtime Distribution
        |
        +------> Consumer Registry
        |
        +------> Apply Acknowledgements
        |
        v
Traceability API / CLI / UI
~~~

Các thành phần:

- **Source loader:** nạp file, environment, remote config và secret references.
- **Parser:** chuyển DSL thành configuration model.
- **Resolver:** áp dụng precedence, merge và interpolation.
- **Provenance collector:** ghi nguồn gốc và các bước biến đổi.
- **Dependency graph:** lưu quan hệ giữa các key.
- **Validator:** kiểm tra schema và policy.
- **Snapshot manager:** tạo, version và publish snapshot.
- **Provenance store:** lưu lineage để truy vấn.
- **Audit store:** lưu thay đổi và actor.
- **Consumer registry:** liên kết key với runtime components.
- **Traceability API:** cung cấp explain, impact, history và compare.

Các thành phần có thể nằm trong một process hoặc được triển khai thành service. Điều quan trọng là provenance được tạo ngay trong resolver, thay vì cố suy ra sau khi giá trị đã bị flatten.

## 20. API và truy vấn traceability

Một API khái niệm:

~~~java
interface ConfigurationTraceability {
    Provenance explainKey(
        ConfigSnapshotId snapshot,
        ConfigKey key
    );

    List<ConfigKey> findDependencies(
        ConfigSnapshotId snapshot,
        ConfigKey key
    );

    ImpactReport analyzeChange(
        ConfigSnapshotId snapshot,
        ConfigKey changedKey
    );

    List<ConfigChange> history(
        ConfigKey key,
        TimeRange range
    );

    ConsumerUsage findConsumers(
        ConfigSnapshotId snapshot,
        ConfigKey key
    );
}
~~~

Các thao tác thường hữu ích:

| Operation | Kết quả |
|---|---|
| Explain key | Nguồn và quá trình tạo effective value |
| Find overrides | Các nguồn ghi đè và bị ghi đè |
| Find dependencies | Các key upstream/downstream |
| Find consumers | Component sử dụng key |
| Compare snapshots | Khác biệt giữa hai version |
| Change history | Lịch sử sửa đổi và actor |
| Analyze impact | Phạm vi ảnh hưởng của thay đổi |
| Verify runtime | Snapshot đã áp dụng trên từng instance |

API cần hỗ trợ pagination, access control, version consistency và trạng thái incomplete.

## 21. Bảo mật và quyền riêng tư

Traceability có thể tiết lộ cấu trúc hạ tầng, tên service, đường dẫn file, deployment topology và secret references. Vì vậy, cần kiểm soát quyền ở mức key, source và consumer.

Các nguyên tắc:
- Chỉ hiển thị metadata cần thiết cho vai trò hiện tại.
- Không lưu secret raw trong provenance.
- Không đưa token hoặc credential vào logs.
- Tách quyền xem provenance khỏi quyền resolve secret.
- Kiểm tra tenant boundary trong mọi truy vấn.
- Giới hạn khả năng enumerate key và source.
- Audit các thao tác truy vấn nhạy cảm nếu policy yêu cầu.
- Bảo vệ provenance store và audit store khỏi sửa trái phép.
- Mã hóa dữ liệu nhạy cảm khi lưu và truyền.
- Giới hạn retention theo mục đích.

Source path cũng có thể nhạy cảm. Một API chỉ cho xem effective value nhưng tiết lộ đường dẫn nội bộ hoặc tên secret có thể vẫn tạo rủi ro.

## 22. Kiểm thử traceability

### 22.1. Precedence tests

Tạo nhiều nguồn cùng khai báo một key và xác nhận:
- Source thắng đúng policy.
- Các source bị ghi đè được lưu.
- Precedence explanation chính xác.
- Thứ tự nạp không làm thay đổi kết quả nếu policy không phụ thuộc thứ tự.

### 22.2. Merge tests

Kiểm tra object, map, list, null, absent và tombstone theo semantics đã định nghĩa. Provenance phải ghi được nguồn đóng góp cho từng field sau merge.

### 22.3. Interpolation tests

Với derived key, xác nhận:
- Dependency edges đúng.
- Thay upstream key làm downstream được tính lại.
- Cycle được phát hiện.
- Source range của expression được lưu.
- Conversion errors được gắn với đúng dependency.

### 22.4. Source mapping tests

Kiểm tra file path, line/column, include chain, JSON pointer và generated source mapping. Với file có Unicode, xác nhận range đúng theo encoding đã chọn.

### 22.5. Snapshot tests

Xác nhận snapshot bất biến, digest ổn định theo canonical representation và mỗi runtime consumer ghi nhận đúng snapshot ID.

### 22.6. Dynamic reload tests

Kiểm tra:
- Candidate validation thất bại không thay active snapshot.
- Consumer acknowledgement được ghi đúng.
- Partial rollout được biểu diễn.
- Rollback tạo event mới và giữ history cũ.
- Không có consumer nhìn thấy snapshot nửa chừng.

### 22.7. Secret tests

Xác nhận raw secret không xuất hiện trong:
- Provenance API.
- Logs.
- Diagnostics.
- Snapshot export.
- Diff output.
- Error messages.

### 22.8. Access control tests

Kiểm tra user không thể xem source, consumer hoặc provenance ngoài quyền, kể cả qua key path, search, compare hoặc impact analysis.

## 23. Những sai lầm thường gặp

1. **Chỉ lưu effective value:** không thể biết giá trị đến từ đâu.
2. **Chỉ lưu source thắng:** mất lịch sử các override bị che.
3. **Không định nghĩa precedence:** kết quả phụ thuộc thứ tự nạp hoặc implementation.
4. **Flatten object quá sớm:** mất provenance ở cấp field.
5. **Không truy vết interpolation:** không giải thích được giá trị dẫn xuất.
6. **Dùng line number làm source identity:** vị trí thay đổi làm lineage mất ổn định.
7. **Không gắn snapshot ID:** không biết runtime đã dùng config version nào.
8. **Nhầm published với applied:** service đã publish nhưng consumer có thể chưa nhận.
9. **Không theo dõi consumer:** không đánh giá được blast radius.
10. **Ghi raw secret:** biến traceability thành kênh rò rỉ credential.
11. **Không lưu source revision:** không thể tái lập file hoặc remote config cũ.
12. **Coi dependency graph là đầy đủ:** dynamic key access có thể không được phát hiện tĩnh.
13. **Xóa snapshot khi rollback:** làm mất bằng chứng điều tra.
14. **Trả kết quả partial như đầy đủ:** người dùng hiểu sai provenance.
15. **Không audit actor và approval:** không xác định được trách nhiệm thay đổi.

## 24. Quy trình triển khai khả năng truy vết

Có thể triển khai theo các bước:

1. **Xác định câu hỏi cần trả lời:** tập trung vào nguồn gốc, override, dependency, consumer và lịch sử.
2. **Định nghĩa configuration key identity:** stable ID, canonical path, namespace và type.
3. **Chuẩn hóa source metadata:** file/resource ID, revision, environment, actor và source range.
4. **Định nghĩa precedence và merge semantics:** xử lý rõ absent, null, empty và delete.
5. **Tích hợp provenance vào resolver:** ghi selected, shadowed, rejected và fallback sources.
6. **Theo dõi interpolation:** tạo dependency graph và evaluation trace.
7. **Giữ source mapping:** liên kết effective key về khai báo và include chain.
8. **Tạo immutable snapshot:** gắn revision, digest, resolver version và provenance graph.
9. **Đăng ký runtime consumers:** ghi key nào được component nhận và áp dụng.
10. **Xây Explain API:** hỗ trợ explain key, source, consumer và dependency.
11. **Thiết kế audit:** actor, approval, change ID và append-only history nếu cần.
12. **Bảo vệ secrets:** reference/version/fingerprint, redaction và access control.
13. **Hỗ trợ compare và impact analysis:** so sánh snapshot và xác định downstream consumers.
14. **Theo dõi reload và rollback:** candidate, active snapshot, acknowledgements và rollout state.
15. **Kiểm thử:** precedence, merge, interpolation, source map, snapshots, secrets và quyền.
16. **Đo vận hành:** storage growth, query latency, index freshness và provenance completeness.

Có thể bắt đầu bằng provenance cho từng key sau khi resolve, rồi mở rộng sang dependency graph và runtime consumer lineage. Tuy nhiên, source identity và snapshot version nên được thiết kế ngay từ đầu để tránh phải suy dựng lịch sử từ dữ liệu đã flatten.

## 25. Kết luận

Khả năng truy vết trong DSL cấu hình cho biết một giá trị hiệu lực được hình thành từ nguồn nào, qua những override và phép biến đổi nào, được áp dụng vào snapshot nào và đang được component nào sử dụng. Provenance liên kết khai báo với effective value; dependency graph giải thích giá trị dẫn xuất; runtime lineage nối cấu hình với consumer; audit trail ghi lại actor và lịch sử thay đổi.

Một hệ thống traceability đáng tin cậy cần stable key identity, source metadata, precedence và merge semantics rõ ràng, source locations, immutable snapshots, dependency tracking, consumer registry và API giải thích cấu hình. Secrets phải được bảo vệ, kết quả incomplete phải được đánh dấu và mọi lần reload/rollback cần có version cùng trạng thái áp dụng. Khi các lớp này được kết nối, đội phát triển có thể điều tra cấu hình sai, đánh giá tác động thay đổi và tái lập môi trường với độ tin cậy cao hơn.


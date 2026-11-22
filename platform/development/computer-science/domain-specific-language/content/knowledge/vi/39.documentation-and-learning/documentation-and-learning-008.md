# Hướng dẫn di trú

Trong vòng đời của một DSL (Domain-Specific Language), grammar, metamodel, semantics, runtime API và công cụ hỗ trợ có thể thay đổi. Một phiên bản mới có thể đổi tên keyword, thay kiểu dữ liệu, bổ sung cấu trúc, loại bỏ cú pháp cũ hoặc thay đổi ý nghĩa của một khai báo. Khi đó, các file DSL, cấu hình và ứng dụng được xây dựng theo phiên bản trước có thể không còn hoạt động như cũ. **Hướng dẫn di trú (migration guide)** giải thích những thay đổi đó và chỉ dẫn người dùng chuyển dự án sang phiên bản mới một cách có kiểm soát.

Di trú không đơn thuần là đổi version dependency. Nó có thể tác động đến source DSL, generated code, dữ liệu lưu trữ, API contract, workflow đang chạy, build pipeline và quy trình triển khai. Một hướng dẫn tốt cần nêu điều kiện trước khi bắt đầu, breaking changes, cách chuyển đổi từng bước, công cụ tự động nếu có, cách xác minh kết quả và phương án phục hồi khi di trú thất bại.

## 1. Di trú là gì?

Di trú là quá trình chuyển một dự án, dữ liệu hoặc hệ thống từ phiên bản hiện tại sang phiên bản đích. Trong hệ sinh thái DSL, đối tượng di trú có thể gồm:

- Source files viết bằng DSL.
- Grammar và metamodel.
- Schema cấu hình hoặc dữ liệu.
- API definitions và event contracts.
- Runtime library và compiler.
- Generated source, binary hoặc deployment artifacts.
- Workflow definitions và trạng thái đang chạy.
- IDE plugin, language server và build tooling.
- Tài liệu, test fixtures và pipeline release.

Ví dụ một phiên bản DSL cũ dùng cú pháp:

~~~text
service endpoint = "https://api.example.test"
~~~

Phiên bản mới chuyển sang block cấu hình:

~~~text
service {
    endpoint = "https://api.example.test"
}
~~~

Migration guide cần giải thích cú pháp cũ bị thay thế, phiên bản nào còn hỗ trợ, cách chuyển file, cách chạy validator và cách xử lý nếu có nhiều dạng khai báo cũ trong cùng repository.

### 1.1. Migration khác upgrade

Upgrade là cập nhật thành phần hoặc dependency lên phiên bản mới. Migration là chuyển đổi dữ liệu, source hoặc cấu hình để tương thích với phiên bản mới. Một lần upgrade có thể không cần migration nếu contract tương thích ngược; một lần migration có thể cần nhiều bước upgrade trung gian.

### 1.2. Migration khác refactoring

Refactoring thường thay đổi cấu trúc nội bộ nhưng giữ hành vi quan sát được. Migration có thể thay đổi syntax hoặc contract và cần cập nhật consumer. Một migration tốt vẫn cố gắng bảo toàn semantics nghiệp vụ nếu mục tiêu là chuyển đổi tương đương.

### 1.3. Migration có thể là một chiều

Một số thay đổi có thể đảo ngược, nhưng các thay đổi như xóa field, chuyển đổi precision hoặc ghi dữ liệu vào format mới có thể mất thông tin. Cần phân loại migration reversible và irreversible trước khi chạy.

## 2. Vì sao DSL cần migration guide?

DSL thường trở thành một phần của quy trình vận hành. Người dùng có thể lưu hàng nghìn file DSL trong repository hoặc database. Thay đổi grammar nhỏ cũng có thể ảnh hưởng nhiều nhóm.

Migration guide giúp:

- Phát hiện breaking changes trước khi nâng cấp.
- Xác định đúng phiên bản nguồn và phiên bản đích.
- Chuyển source DSL có hệ thống.
- Giữ semantics khi đổi syntax hoặc metamodel.
- Cập nhật generated code và runtime dependency.
- Giảm thời gian dừng dịch vụ.
- Xác minh kết quả bằng parser, validator và test.
- Phối hợp thay đổi provider/consumer theo giai đoạn.
- Lập kế hoạch rollback hoặc forward-fix.
- Lưu lại quyết định và bằng chứng của quá trình chuyển đổi.

### 2.1. Không có migration guide

Nếu chỉ phát hành release notes ngắn, người dùng có thể bỏ sót thay đổi ngữ nghĩa, sửa source không đầy đủ hoặc triển khai runtime mới trước khi dữ liệu đã sẵn sàng. Những lỗi này thường chỉ xuất hiện khi chạy workflow hoặc xử lý dữ liệu thật.

### 2.2. Migration là một phần của compatibility policy

Một framework DSL nên công bố rõ các phiên bản còn được hỗ trợ, thời gian deprecation, mức tương thích và đường nâng cấp được khuyến nghị. Migration guide biến policy đó thành các bước có thể thực hiện.

## 3. Xác định phiên bản nguồn và phiên bản đích

Trước khi di trú, cần biết dự án đang dùng phiên bản nào và sẽ chuyển đến phiên bản nào.

Thông tin cần xác định:

| Thông tin | Ví dụ |
|---|---|
| Source DSL version | 2.3 |
| Target DSL version | 3.0 |
| Compiler version | 3.0.1 |
| Runtime version | 3.0.1 |
| Metamodel/schema version | 5 |
| Generator version | 3.0 |
| IDE/language server | 3.0 |
| Build plugin | Phiên bản tương thích với compiler |
| Target platform | Java 21, database hoặc cloud runtime |

### 3.1. Không chỉ đọc version khai báo

Một repository có thể chứa module dùng version khác nhau, file cũ không có version marker hoặc generated artifacts được tạo từ compiler khác. Nên kiểm kê dependency lockfile, build configuration, manifest và metadata của artifact.

### 3.2. Kiểm tra đường nâng cấp được hỗ trợ

Một framework có thể yêu cầu nâng cấp qua phiên bản trung gian. Ví dụ, từ 1.x lên 3.x có thể cần đi qua 2.x để chuyển metamodel hoặc dữ liệu. Không nên giả định migration trực tiếp được hỗ trợ nếu release policy không nói rõ.

### 3.3. Inventory source files

Cần biết số lượng file, module, version marker, generated files, custom extension và dependency. Inventory giúp ước tính thời gian, chọn batch và phát hiện những vùng không thể tự động chuyển.

### 3.4. Xác định môi trường

Phân biệt local, CI, staging và production. Migration nên được thử trên bản sao đại diện trước khi chạy trên dữ liệu hoặc hệ thống thật.

## 4. Phân loại thay đổi

Migration guide nên nhóm thay đổi theo mức độ và cách xử lý.

| Loại thay đổi | Ví dụ | Tác động |
|---|---|---|
| Additive | Thêm keyword hoặc optional field | Có thể không cần sửa source cũ |
| Deprecation | Đánh dấu cú pháp cũ sẽ bị loại bỏ | Cần lên kế hoạch chuyển |
| Rename | Đổi tên type, field hoặc operation | Cần update references |
| Type change | Integer thành Decimal | Cần chuyển dữ liệu và kiểm tra precision |
| Structural | Đổi block syntax hoặc metamodel | Cần AST transformation |
| Semantic | Thay default hoặc evaluation order | Có thể đổi hành vi |
| Removal | Bỏ function hoặc keyword | Cần thay thế |
| Runtime change | Đổi API hoặc lifecycle | Cần cập nhật implementation |
| Serialization change | Đổi schema lưu trữ | Cần data migration |
| Tooling change | Đổi compiler/IDE protocol | Cần cập nhật build và editor |

### 4.1. Syntax-breaking changes

Syntax-breaking change làm source cũ không parse được hoặc parse thành cấu trúc khác. Cần có before/after examples và công cụ chuyển đổi nếu số lượng file lớn.

### 4.2. Semantic-breaking changes

Source có thể parse thành công nhưng hành vi khác. Ví dụ default timeout đổi từ 30 giây sang 5 giây hoặc enum state mới thay đổi transition. Đây là loại thay đổi dễ bị bỏ sót nếu chỉ chạy parser.

### 4.3. Data-breaking changes

Schema mới có thể không đọc được dữ liệu cũ hoặc đổi cách serialize null, timestamp, decimal và identifier. Cần migration dữ liệu riêng.

### 4.4. Tooling-breaking changes

Compiler, plugin, generator hoặc language server có thể đổi API. Dự án cần cập nhật build script, extension và integration tests.

## 5. Deprecation trước khi loại bỏ

Một thay đổi an toàn thường có giai đoạn deprecation trước khi xóa cú pháp hoặc API cũ.

Một lifecycle có thể là:

~~~text
Supported
    |
    v
Deprecated with warning
    |
    v
Migration tooling available
    |
    v
Legacy mode optional
    |
    v
Removed in major release
~~~

### 5.1. Deprecation warning

Compiler nên cảnh báo vị trí dùng cú pháp cũ, chỉ rõ replacement và phiên bản dự kiến loại bỏ. Warning cần có stable diagnostic code để CI có thể thống kê.

### 5.2. Sunset date/version

Nên công bố version hoặc ngày dự kiến kết thúc hỗ trợ. Tránh dùng thông báo mơ hồ như “sẽ sớm bị loại bỏ”.

### 5.3. Legacy compatibility mode

Có thể duy trì parser mode cho cú pháp cũ trong một khoảng thời gian. Cần nói rõ mode này chỉ hỗ trợ parse, hay còn hỗ trợ generator, runtime và tooling.

### 5.4. Deprecation không phải bảo đảm tương thích vô thời hạn

Người dùng cần biết thời hạn và các điều kiện hỗ trợ. Nếu tiếp tục dùng legacy mode sau khi hết hạn, có thể không nhận bug fixes hoặc security updates.

## 6. Lập kế hoạch migration

Trước khi thay đổi, cần lập kế hoạch theo phạm vi và rủi ro.

Các bước chuẩn bị:

1. Xác định source và target versions.
2. Đọc release notes, breaking changes và migration guide liên quan.
3. Kiểm kê DSL files, modules, dependencies và generated artifacts.
4. Chạy baseline tests trên phiên bản hiện tại.
5. Backup source, data và configuration.
6. Chọn migration tool hoặc viết transformation.
7. Thử trên branch hoặc bản sao staging.
8. Đo số file tự động chuyển và số file cần sửa tay.
9. Chạy validation, integration tests và target compilation.
10. Chuẩn bị rollback hoặc forward-fix.
11. Lên lịch triển khai và thông báo cho consumer.
12. Lưu kết quả, version và người chịu trách nhiệm.

### 6.1. Migration scope

Xác định rõ những gì nằm trong phạm vi: source DSL, generated code, database, API, workflow state hay tất cả. Không nên gộp các thay đổi không liên quan vào cùng một đợt nếu khó xác định nguyên nhân khi fail.

### 6.2. Risk assessment

Đánh giá số lượng file, mức độ breaking, dữ liệu có thể mất, downtime, dependency bên ngoài và khả năng rollback. Những thay đổi có thể gây mất dữ liệu cần thử nghiệm trên bản sao và có backup đã xác minh.

### 6.3. Migration window

Nếu cần dừng ghi hoặc đồng bộ dữ liệu, chọn maintenance window. Với hệ thống hỗ trợ rolling migration, có thể chuyển từng nhóm mà không dừng toàn bộ dịch vụ.

### 6.4. Ownership

Mỗi domain hoặc module nên có owner review thay đổi. Migration tool có thể tự động sửa cú pháp, nhưng owner cần xác nhận semantics nghiệp vụ.

## 7. Tự động hóa migration bằng AST transformation

Với DSL có parser và AST, migration tool có thể chuyển đổi cấu trúc thay vì thay thế chuỗi văn bản.

Ví dụ cú pháp cũ:

~~~text
service endpoint = "https://api.example.test"
~~~

AST cũ:

~~~text
ServiceDeclaration
└── endpoint: StringLiteral
~~~

AST mới mong muốn:

~~~text
ServiceDeclaration
└── properties
    └── EndpointProperty
        └── value: StringLiteral
~~~

Migration tool có thể parse source cũ, tạo node model mới, rồi serialize về cú pháp mới.

### 7.1. Vì sao AST transformation an toàn hơn text replacement?

Text replacement có thể đổi nhầm tên trong comment, string hoặc identifier khác. AST transformation biết token đang đóng vai trò gì nên có thể sửa đúng node.

### 7.2. Parse bằng phiên bản nguồn

Tool cần parse theo grammar cũ hoặc một parser tương thích. Nếu dùng parser mới trực tiếp, source cũ có thể không parse được hoặc bị hiểu theo semantics mới ngoài ý muốn.

### 7.3. Transform có kiểu

Transformation nên kiểm tra node type và precondition. Nếu gặp cấu trúc không nhận diện, nên tạo diagnostic hoặc giữ nguyên để người dùng xử lý, không nên đoán.

### 7.4. Preserve source mapping

Node mới nên giữ source origin để diff, diagnostic và review có thể trỏ về vị trí cũ. Nếu comment/trivia được giữ, serializer nên duy trì chúng theo policy.

### 7.5. Transform từng bước

Với thay đổi lớn, chia migration thành các pass nhỏ có version rõ. Ví dụ pass A đổi field name, pass B chuyển type, pass C thay cấu trúc block. Điều này giúp xác định pass nào gây lỗi.

## 8. Migration bằng codemod và text transformation

Không phải DSL nào cũng có parser hoặc AST tooling đầy đủ. Một codemod có thể dùng token stream, syntax-aware editor hoặc pattern matching có giới hạn.

### 8.1. Khi nào text replacement phù hợp?

Text replacement phù hợp với thay đổi đơn giản, không mơ hồ và có thể kiểm soát bằng boundary rõ. Ví dụ đổi một tên file hoặc sửa metadata trong header theo format ổn định.

### 8.2. Khi nào không nên dùng regex?

Không nên dùng regex đơn giản để thay đổi cấu trúc có nesting, string escaping, comments hoặc tên trùng. Regex có thể sửa nhầm phần source không thuộc target.

### 8.3. Dry run

Codemod nên hỗ trợ chế độ dry run để hiển thị diff mà không ghi file. Người dùng review các thay đổi trước khi áp dụng.

### 8.4. Idempotence

Chạy migration tool lần thứ hai trên output đã chuyển nên không tạo thay đổi mới nếu migration đã hoàn tất. Idempotence giúp retry sau sự cố và tránh biến đổi lặp.

### 8.5. Backup và patch output

Tool có thể tạo patch hoặc ghi file vào branch riêng. Không nên ghi đè hàng loạt trước khi có bản sao và báo cáo kết quả.

## 9. Migration metamodel và schema

Nếu DSL dựa trên metamodel như Ecore hoặc schema JSON, thay đổi cấu trúc cần migration model/data.

Ví dụ schema cũ:

~~~json
{
  "customerName": "An",
  "postalCode": "700000"
}
~~~

Schema mới nhóm địa chỉ:

~~~json
{
  "customerName": "An",
  "address": {
    "postalCode": "700000"
  }
}
~~~

Migration phải chuyển customerName và postalCode đúng nơi, đồng thời xác định default cho field mới.

### 9.1. Rename field

Rename field cần cập nhật source references, serialized data, API consumers và query expressions. Có thể giữ alias đọc cũ trong giai đoạn chuyển tiếp.

### 9.2. Split và merge fields

Tách một field thành nhiều field cần quy tắc suy ra dữ liệu. Gộp nhiều field cần xác định precedence và cách xử lý trường hợp dữ liệu mâu thuẫn.

### 9.3. Type conversion

Chuyển Integer sang Decimal có thể an toàn trong nhiều trường hợp; chuyển Decimal sang Integer có thể mất phần thập phân. Migration cần xác định rounding, overflow và validation.

### 9.4. Cardinality changes

Đổi field từ scalar sang list hoặc ngược lại cần quy tắc mapping. Ví dụ scalar có thể trở thành list một phần tử, nhưng trường hợp null/empty cần được định nghĩa.

### 9.5. Default và null semantics

Thêm default có thể làm thay đổi hành vi. Cần phân biệt field không tồn tại, null, empty và giá trị default. Không nên tự động biến mọi trường hợp thành cùng một giá trị nếu domain không cho phép.

### 9.6. Schema version markers

Dữ liệu có thể lưu schemaVersion để loader biết cần chạy migration nào. Version marker nên được cập nhật cùng dữ liệu sau khi migration thành công.

## 10. Migration runtime và generated code

DSL compiler hoặc generator có thể thay đổi API mà generated code phụ thuộc.

### 10.1. Runtime API changes

Nếu runtime method bị đổi tên hoặc đổi signature, generated code cần được tạo lại hoặc cập nhật. Migration guide nên chỉ rõ phiên bản runtime tương thích với compiler.

### 10.2. Regenerate hay sửa generated source?

Nếu generated source có thể tái tạo, ưu tiên chạy generator mới. Không nên sửa tay generated output vì lần generate sau sẽ ghi đè và source of truth vẫn cũ.

### 10.3. Custom code extensions

Người dùng có thể mở rộng generated classes hoặc hook. Cần phân biệt vùng generated và handwritten; migration tool không nên ghi đè custom code.

### 10.4. Binary compatibility

Một runtime library mới có thể giữ source compatibility nhưng phá binary compatibility. Cần kiểm tra public signatures, package names và dependency graph.

### 10.5. Target platform changes

Nếu generator đổi target language hoặc version, ví dụ Java 17 sang Java 21, dự án cần cập nhật toolchain và test generated artifact trên target mới.

## 11. Migration API contract và consumer

Nếu DSL mô tả API, thay đổi contract có thể ảnh hưởng các consumer triển khai độc lập.

### 11.1. Additive API changes

Thêm endpoint hoặc optional response field thường ít rủi ro hơn, nhưng consumer nghiêm ngặt có thể không chấp nhận enum hoặc field mới. Cần kiểm tra compatibility theo consumer model.

### 11.2. Breaking API changes

Xóa field, đổi type, đổi error code hoặc thay semantics cần migration plan. Có thể tạo API version mới và duy trì version cũ trong thời gian chuyển tiếp.

### 11.3. Expand-contract

Một chiến lược thường dùng:

1. Expand: provider hỗ trợ cả contract cũ và mới.
2. Migrate consumers: cập nhật từng consumer.
3. Observe: xác nhận traffic cũ đã giảm hoặc ngừng.
4. Contract: loại bỏ contract cũ sau khi hết thời gian hỗ trợ.

### 11.4. Event schema migration

Event đã được publish có thể nằm trong broker hoặc archive lâu dài. Consumer cần đọc được event cũ trong thời gian retention hoặc dùng upcaster chuyển schema cũ sang model nội bộ mới.

### 11.5. Webhook consumers

Nếu payload webhook thay đổi, provider cần version event, giữ backward compatibility hoặc cung cấp endpoint test để consumer xác nhận trước khi cutover.

## 12. Migration workflow và trạng thái đang chạy

Workflow DSL có thể lưu instance state lâu dài. Thay đổi workflow definition không tự động biến đổi các instance đang chạy theo định nghĩa cũ.

### 12.1. Definition version

Mỗi workflow instance nên biết nó được khởi tạo từ definition version nào. Khi definition mới được publish, instance cũ có thể tiếp tục bằng version cũ hoặc được migrate theo policy.

### 12.2. State mapping

Nếu state cũ bị đổi tên hoặc tách thành nhiều state mới, cần mapping rõ. Một state cũ có thể không đủ thông tin để chọn state mới; khi đó cần manual intervention.

### 12.3. In-flight instances

Có thể chọn một trong các chiến lược:

- Let old instances finish: instance cũ chạy đến khi kết thúc.
- Freeze and restart: dừng instance và khởi tạo lại theo definition mới.
- Migrate in place: chuyển state và context theo mapping.
- Drain gradually: không tạo instance mới theo version cũ, chờ số instance cũ giảm.

### 12.4. Event compatibility

Event đang chờ hoặc được phát theo schema cũ cần được xử lý. Migration cần giữ correlation và event identity để tránh workflow nhận event hai lần.

### 12.5. Timers và retries

Timer, retry schedule và compensation state có thể cần chuyển. Không nên chỉ đổi definition rồi giả định scheduler tự hiểu trạng thái cũ.

## 13. Migration cấu hình môi trường

Profile và configuration DSL thường khác nhau giữa development, staging và production.

### 13.1. Tách source khỏi secret

Migration không nên đưa secret thật vào file mới hoặc commit credential. Nếu schema mới chuyển từ inline value sang secret reference, cần chuyển credential sang secret manager trước.

### 13.2. Preserve effective values

Sau migration, effective configuration nên giữ giá trị tương đương trừ khi release cố ý thay đổi default hoặc policy. Có thể so sánh effective config trước và sau, đồng thời redact secrets.

### 13.3. Profile inheritance

Nếu phiên bản mới thay đổi cách merge hoặc precedence, cần kiểm tra từng profile và tổ hợp profile. Một giá trị bị override khác thứ tự có thể làm production behavior thay đổi.

### 13.4. Validation trước deploy

Không triển khai profile mới trước khi parse, resolve parameters và validate cross-field constraints. Có thể tạo report cho từng environment.

### 13.5. Rollback configuration

Giữ revision cũ và biết cách chuyển lại. Nếu schema mới không thể đọc bởi runtime cũ, cần chuẩn bị artifact/config version tương thích trước khi cutover.

## 14. Data migration và database changes

DSL có thể mô tả entity, schema hoặc query. Thay đổi metamodel có thể yêu cầu migration dữ liệu đang lưu trong database.

### 14.1. Backup và restore test

Backup cần được tạo trước migration và kiểm tra có thể restore. Chỉ có file backup mà chưa thử restore không chứng minh khả năng phục hồi.

### 14.2. Online migration

Với hệ thống cần hoạt động liên tục, có thể thêm cấu trúc mới, ghi song song hoặc backfill theo batch rồi chuyển read path.

### 14.3. Backfill

Backfill chuyển dữ liệu cũ sang field/schema mới. Nên hỗ trợ checkpoint, retry và progress để có thể tiếp tục sau lỗi.

### 14.4. Data validation

Sau migration, so sánh row count, null count, aggregate, checksum hoặc business invariants. Với chuyển đổi mất mát, cần báo rõ số record không thể chuyển tự động.

### 14.5. Dual-write risks

Ghi đồng thời schema cũ và mới có thể tạo divergence nếu một phía thất bại. Cần transaction, outbox hoặc reconciliation job và thời gian giới hạn cho dual-write.

### 14.6. Large datasets

Batch size, lock duration, index creation và replication lag có thể ảnh hưởng production. Migration guide cần chỉ ra cách đo và giới hạn tài nguyên.

## 15. Quy trình thực hiện migration

Một quy trình thực tế có thể gồm các giai đoạn:

~~~text
Inventory and backup
        |
        v
Preflight validation
        |
        v
Dry-run / preview diff
        |
        v
Apply source/model migration
        |
        v
Regenerate and rebuild
        |
        v
Run tests and semantic checks
        |
        v
Deploy to staging
        |
        v
Verify behavior and data
        |
        v
Approval and production rollout
        |
        v
Monitor / rollback or forward-fix
~~~

### 15.1. Preflight

Kiểm tra source version, dependency, disk space, tool version, permissions, schema marker và điều kiện đầu vào. Nếu không đúng, dừng trước khi thay đổi file.

### 15.2. Dry run

Dry run báo file nào sẽ thay đổi, node nào sẽ được chuyển và trường hợp nào không tự động xử lý được. Nên xuất diff và summary để review.

### 15.3. Apply

Migration có thể chạy theo batch. Mỗi batch cần có log, checkpoint và khả năng retry mà không tạo thêm thay đổi ngoài ý muốn.

### 15.4. Validate

Parse source mới, resolve references, chạy semantic validation, regenerate artifacts, compile target và test behavior. Với data migration, chạy integrity checks.

### 15.5. Deploy

Triển khai theo rollout strategy đã chọn. Với API hoặc workflow, cần kiểm soát compatibility giữa version cũ và mới trong thời gian đồng tồn tại.

### 15.6. Observe

Theo dõi error rate, parse failures, runtime diagnostics, queue lag, workflow failures và dữ liệu chưa migrate. Giữ khả năng dừng rollout khi vượt ngưỡng.

## 16. Migration tool design

Một migration tool tốt cần predictable, có thể preview, có thể retry và có báo cáo.

### 16.1. Tool interface

Một CLI có thể cung cấp các lệnh:

~~~text
dsl-migrate inspect --from 2.3 --to 3.0
dsl-migrate plan --workspace ./project
dsl-migrate apply --workspace ./project --dry-run
dsl-migrate apply --workspace ./project
dsl-migrate verify --workspace ./project
~~~

Tên lệnh chỉ minh họa; tool thực tế cần định nghĩa flags, exit codes và config rõ ràng.

### 16.2. Migration registry

Có thể đăng ký các migration theo source version và target version. Mỗi migration có ID, precondition, transform, postcondition và metadata.

### 16.3. Chaining migrations

Nếu chỉ có migration 2.3→2.4 và 2.4→3.0, tool có thể chạy tuần tự. Cần xác định có hỗ trợ đường tắt 2.3→3.0 hay không.

### 16.4. Idempotent execution

Tool cần ghi nhận migration đã chạy hoặc thiết kế transformation idempotent. Nếu process dừng giữa chừng, lần chạy lại không được làm hỏng phần đã hoàn tất.

### 16.5. Atomic file updates

Với mỗi file, có thể ghi ra temporary file, validate rồi rename atomically. Với nhiều file, cần manifest/checkpoint để xác định file nào đã chuyển nếu batch bị gián đoạn.

### 16.6. Exit codes

Exit code nên phân biệt migration completed, partial/manual action required, invalid source, unsupported version và infrastructure failure. CI có thể dựa vào mã để dừng đúng cách.

### 16.7. Reports

Report nên ghi số file đã quét, đã chuyển, không đổi, cần review, thất bại và bỏ qua. Có thể liệt kê diagnostic theo file/line nhưng không đưa secret vào report.

## 17. Kiểm tra tương đương trước và sau migration

Mục tiêu của migration thường là giữ hành vi nghiệp vụ trong khi thay representation hoặc platform.

### 17.1. Golden behavior tests

Chạy cùng input qua phiên bản cũ và mới rồi so sánh kết quả ở những trường hợp phải giữ semantics.

### 17.2. Differential tests

Có thể chạy compiler/runtime cũ và mới trên cùng fixture. So sánh generated output, diagnostics hoặc observable behavior.

### 17.3. Tolerated differences

Không phải mọi output đều phải giống byte-for-byte. Ví dụ formatting hoặc generated identifiers có thể thay đổi. Cần định nghĩa rõ phần nào là contract và phần nào chỉ là implementation detail.

### 17.4. Business invariants

Kiểm tra các invariant như tổng tiền, số lượng record, trạng thái workflow, quyền truy cập và kết quả tính toán. Đây là lớp xác minh quan trọng khi semantics thay đổi.

### 17.5. Performance regression

Migration có thể làm query chậm, build lâu hoặc memory tăng. Nên đo baseline và target trên workload đại diện.

## 18. Rollback và forward recovery

Rollback là quay lại phiên bản trước; forward recovery là sửa tiếp ở phiên bản mới khi quay lại không an toàn hoặc không khả thi.

### 18.1. Khi rollback phù hợp?

Rollback phù hợp khi artifact cũ vẫn tương thích với dữ liệu và trạng thái hiện tại. Nếu migration đã xóa hoặc biến đổi dữ liệu không thể đảo, rollback code có thể khiến runtime cũ không đọc được data mới.

### 18.2. Backup restore

Restore backup có thể khôi phục trạng thái trước migration nhưng có thể mất các thay đổi phát sinh sau backup. Cần đánh giá write freeze, log replay và business impact.

### 18.3. Forward fix

Nếu schema đã được mở rộng hoặc dữ liệu đã chuyển một phần, forward fix có thể an toàn hơn. Migration cần có checkpoint để hoàn tất phần còn lại.

### 18.4. Rollback plan phải được thử

Không nên chỉ viết “có thể rollback”. Cần thử triển khai phiên bản cũ trên bản sao dữ liệu sau migration hoặc chứng minh compatibility.

### 18.5. Stop conditions

Đặt điều kiện dừng rõ: parse failure vượt ngưỡng, data validation mismatch, error rate tăng, workflow không resume hoặc migration lag quá lớn.

## 19. Tài liệu migration theo từng thay đổi

Mỗi breaking change nên có một mục riêng với cấu trúc nhất quán:

- Tên thay đổi và phiên bản áp dụng.
- Lý do thay đổi.
- Phiên bản bắt đầu deprecate.
- Source hoặc data pattern cũ.
- Cấu trúc mới.
- Before/after example.
- Migration tool có hỗ trợ không.
- Các trường hợp cần sửa tay.
- Ảnh hưởng semantics/runtime.
- Cách kiểm tra sau chuyển đổi.
- Cách rollback hoặc xử lý ngoại lệ.

### 19.1. Before/after examples

Ví dụ cần đủ nhỏ để dễ hiểu nhưng phải thể hiện chính xác thay đổi.

~~~text
Before:
field userName: String

After:
field username: String
~~~

Nếu chỉ đổi tên, migration tool có thể sửa identifier references. Nếu đổi cả semantics hoặc casing policy, cần giải thích thêm.

### 19.2. Manual migration cases

Một số thay đổi không thể tự động chuyển vì thiếu ngữ cảnh. Hướng dẫn cần đưa ra quy tắc quyết định và ví dụ để người dùng xử lý.

### 19.3. FAQ và troubleshooting

Nêu các lỗi thường gặp như version mismatch, unresolved reference, duplicate symbol, missing required field, invalid enum hoặc generated output khác dự kiến.

## 20. Migration trong CI/CD

Migration nên được tích hợp vào pipeline để kiểm tra liên tục và tránh chỉ phát hiện khi triển khai.

### 20.1. Compatibility checks

CI có thể parse fixture cũ bằng compiler mới, so sánh contract và kiểm tra generated output. Nếu source cũ không còn được hỗ trợ, pipeline cần báo rõ.

### 20.2. Automated codemod stage

Có thể chạy migration tool trong branch riêng hoặc tạo patch artifact. Không nên tự merge thay đổi source lớn nếu chưa review.

### 20.3. Data migration stage

Với production data, pipeline có thể tạo migration plan và yêu cầu approval trước khi thực thi. Dry run và estimate cần chạy trước.

### 20.4. Environment promotion

Thử migration ở test, staging và production theo cùng artifact/tool version. Nếu data volume khác nhau, staging cần dữ liệu đủ đại diện hoặc benchmark bổ sung.

### 20.5. Audit trail

Ghi migration ID, tool version, source revision, target version, operator, start/end time, số record/file và kết quả. Migration có thể thay đổi dữ liệu quan trọng nên cần audit.

## 21. Bảo mật trong migration

Migration tool thường có quyền đọc và ghi nhiều file hoặc dữ liệu. Cần kiểm soát quyền và nguồn đầu vào.

Các biện pháp:

- Chạy với quyền tối thiểu.
- Xác minh workspace root và tránh path traversal.
- Không thực thi DSL/plugin không tin cậy trong lúc migrate.
- Che secret trong diff và report.
- Lấy dependency từ registry đáng tin cậy.
- Ký hoặc xác minh migration package nếu phân phối riêng.
- Giới hạn tài nguyên với file lớn hoặc nesting sâu.
- Bảo vệ backup và dữ liệu tạm.
- Audit ai chạy migration và trên môi trường nào.
- Kiểm soát quyền phê duyệt production migration.

### 21.1. Untrusted source files

Source DSL có thể chứa macro hoặc plugin. Migration parser nên xử lý cú pháp như dữ liệu, không thực thi side effects chỉ để phân tích.

### 21.2. Secret handling

Nếu config cũ chứa secret inline, migration nên chuyển sang secret reference mà không ghi secret vào patch, console hoặc audit report.

### 21.3. Temporary files

File tạm có thể chứa bản sao dữ liệu nhạy cảm. Cần quyền filesystem phù hợp, cleanup và encryption nếu cần.

## 22. Những lỗi migration thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Nâng runtime trước khi chuyển source | Source cũ không parse hoặc chạy sai | Theo đúng thứ tự upgrade/migration |
| Chỉ chạy parser mới | Syntax qua nhưng semantics thay đổi | Chạy semantic và behavior tests |
| Dùng regex cho cấu trúc lồng nhau | Sửa nhầm comment/string hoặc identifier | Dùng AST/codemod syntax-aware |
| Không backup hoặc chưa thử restore | Không phục hồi được khi migration lỗi | Backup và restore rehearsal |
| Chạy migration nhiều lần không kiểm soát | Dữ liệu bị chuyển lặp | Idempotence và migration ledger |
| Bỏ qua generated code | Output vẫn dùng runtime API cũ | Regenerate bằng toolchain mới |
| Không kiểm tra in-flight workflows | Instance đang chạy bị mất state | Version-aware state migration |
| Không kiểm tra event/schema cũ | Consumer không đọc được message tồn tại | Upcasting và compatibility window |
| Không giữ source mapping | Diagnostic khó truy ngược source | Preserve origin metadata |
| Không đo dữ liệu thực tế | Migration quá chậm hoặc lock lâu | Dry run và batch sizing |
| Rollback chỉ đổi binary | Schema/data không tương thích | Kế hoạch rollback/forward recovery |
| Không ghi audit migration | Không biết ai đổi và kết quả gì | Migration audit record |

## 23. Ví dụ tổng hợp: di trú DSL từ v2 sang v3

Giả sử DSL v2 có cấu trúc:

~~~text
workflow orderFlow {
    timeout = 30
    onSuccess = "ship"
}
~~~

DSL v3 yêu cầu khai báo block rõ hơn và dùng duration có đơn vị:

~~~text
workflow orderFlow {
    timeout 30s
    transitions {
        success -> ship
    }
}
~~~

Một migration plan có thể gồm:

1. Kiểm kê mọi workflow file đang dùng v2.
2. Chạy parser v2 và lưu baseline diagnostics.
3. Tìm assignment timeout và onSuccess trong AST.
4. Chuyển timeout integer thành DurationLiteral với đơn vị giây.
5. Chuyển onSuccess thành transition declaration.
6. Giữ source origin và comment nếu serializer hỗ trợ.
7. Ghi file mới vào branch hoặc patch để review.
8. Parse bằng compiler v3.
9. Chạy semantic validation và kiểm tra target state tồn tại.
10. So sánh workflow behavior với phiên bản cũ.
11. Deploy thử trên staging và kiểm tra instance mới.
12. Xử lý in-flight instances theo policy riêng.
13. Promote compiler/runtime v3 và source đã chuyển.
14. Theo dõi diagnostics và workflow failures sau cutover.

### 23.1. Trường hợp tự động chuyển được

Nếu timeout luôn là integer theo giây và onSuccess luôn là tên state hợp lệ, tool có thể chuyển tự động.

### 23.2. Trường hợp cần review

Nếu timeout có thể là phút hoặc giá trị được lấy từ biến, tool cần hiểu expression. Nếu onSuccess có nhiều nhánh hoặc phụ thuộc condition, có thể cần người thiết kế quyết định transition mới.

### 23.3. Kiểm tra semantics

Cần xác nhận timeout 30 cũ có đúng nghĩa 30 giây không, và success transition mới có chạy ở cùng thời điểm không. Cú pháp tương đương không tự chứng minh hành vi tương đương.

## 24. Checklist cho người thực hiện migration

Trước khi chạy:

- Đã xác định source/target versions và đường nâng cấp được hỗ trợ.
- Đã đọc breaking changes và deprecation policy.
- Đã kiểm kê source, data, dependencies và generated artifacts.
- Đã có backup và thử restore.
- Đã chạy baseline tests.
- Đã xác định migration scope, owner và maintenance window.
- Đã chọn tool version và cấu hình ổn định.

Trong khi chạy:

- Đã chạy preflight và dry run.
- Đã review diff hoặc migration plan.
- Đã lưu checkpoint và migration ID.
- Đã kiểm soát batch size và tài nguyên.
- Đã redacted secret trong output.
- Đã ghi nhận file/record thất bại và trường hợp cần manual action.

Sau khi chạy:

- Source mới parse và validate.
- References và type checks thành công.
- Generated code đã được tái tạo và compile.
- Data counts và business invariants khớp.
- Workflow/API consumers tương thích.
- Integration và end-to-end tests đạt.
- Staging behavior được xác nhận.
- Rollback/forward recovery đã sẵn sàng.
- Migration report và audit trail được lưu.

## 25. Nguyên tắc thiết kế hướng dẫn di trú

Một migration guide hữu ích nên:

1. **Nêu rõ phạm vi và phiên bản.** Người đọc biết đang chuyển từ đâu đến đâu.
2. **Liệt kê breaking changes.** Phân biệt syntax, semantics, data và tooling.
3. **Cung cấp before/after examples.** Cho thấy chính xác cách chuyển.
4. **Đưa ra thứ tự thao tác.** Tránh nâng runtime hoặc data sai thời điểm.
5. **Mô tả automation.** Nêu tool, precondition, dry run, output và giới hạn.
6. **Nêu trường hợp cần xử lý tay.** Không che giấu sự mơ hồ bằng auto-fix.
7. **Bảo toàn semantics.** Kiểm tra behavior, không chỉ parse.
8. **Bảo vệ dữ liệu.** Backup, redaction, permission và audit.
9. **Đề cập in-flight state.** Workflow, event và job đang chạy cần policy riêng.
10. **Có validation steps.** Parser, semantic, integration và target tests.
11. **Có recovery plan.** Phân biệt rollback code, data và configuration.
12. **Version hóa migration tool.** Có thể tái tạo kết quả.
13. **Ghi lại kết quả.** Migration report và audit trail giúp điều tra.
14. **Giữ tài liệu đồng bộ.** Cập nhật guide cùng release và deprecation timeline.

## 26. Kết luận

Hướng dẫn di trú giúp người dùng chuyển source DSL, metamodel, dữ liệu, runtime và tooling từ phiên bản cũ sang phiên bản mới một cách có kiểm soát. Một migration không chỉ cần làm cho source parse được; nó còn phải giữ hoặc chủ động thay đổi semantics theo hợp đồng, bảo toàn dữ liệu và duy trì khả năng vận hành.

Quy trình đáng tin cậy bắt đầu bằng inventory, backup và baseline tests; tiếp tục bằng dry run, AST-aware transformation, data migration và regeneration; rồi xác minh parser, semantic rules, generated output, workflow state và behavior trước khi rollout. Migration tool cần idempotent, có checkpoint, báo cáo rõ và không tự đoán các trường hợp mơ hồ.

Khi breaking changes, deprecation, migration tooling, validation và recovery được công bố cùng release, người dùng có thể lập kế hoạch nâng cấp, review thay đổi và xử lý ngoại lệ trước khi ảnh hưởng đến production.

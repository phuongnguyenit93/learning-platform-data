# Tự động nâng cấp trong DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích tự động nâng cấp (automated upgrade) trong bối cảnh phiên bản và di trú của DSL.
- Phân biệt nâng cấp phiên bản compiler/runtime với di trú source, schema, cấu hình và dữ liệu.
- Xác định phiên bản hiện tại, phiên bản đích và các bước chuyển đổi cần thiết.
- Đọc compatibility policy và xác định thay đổi breaking, non-breaking hoặc deprecated.
- Thiết kế migration rule có điều kiện, có phiên bản, có thể chạy lặp an toàn và có thể kiểm tra.
- Áp dụng AST transformation, codemod và schema migration để cập nhật source DSL.
- Lập dependency graph và sắp xếp thứ tự các bước nâng cấp.
- Thực hiện dry-run, backup, checkpoint, transaction, staged rollout và phục hồi.
- Xử lý conflict, migration lỗi giữa chừng và trường hợp không thể rollback.
- Tạo báo cáo, audit trail và kiểm thử để chứng minh kết quả nâng cấp.

## 1. Tự động nâng cấp là gì?

Tự động nâng cấp (automated upgrade) là quá trình dùng công cụ để đưa một project, cấu hình, schema, dữ liệu hoặc runtime từ một phiên bản cũ sang phiên bản mới theo một tập quy tắc đã xác định.

Trong hệ sinh thái DSL, một project có thể phụ thuộc vào:
- Phiên bản ngôn ngữ và grammar.
- Compiler hoặc interpreter.
- Runtime engine.
- Thư viện và plugin.
- Schema dữ liệu.
- API contract.
- Workflow definition.
- Cấu hình môi trường.
- Generated code và artifact đã compile.

Khi một thành phần thay đổi, project có thể cần chuyển đổi để tiếp tục hoạt động đúng. Ví dụ, phiên bản DSL mới đổi tên keyword, thay đổi kiểu mặc định, loại bỏ một operator cũ hoặc thay đổi cấu trúc khai báo workflow. Một công cụ nâng cấp có thể phát hiện các pattern cũ và chuyển chúng sang cú pháp mới.

Ví dụ minh họa:

Phiên bản cũ:

~~~text
service "billing" {
    timeout = 5000
}
~~~

Phiên bản mới yêu cầu đơn vị thời gian tường minh:

~~~text
service "billing" {
    timeout = 5 seconds
}
~~~

Một migration rule có thể nhận diện giá trị timeout dạng số và chuyển sang duration có đơn vị. Nhưng công cụ chỉ nên tự chuyển nếu biết chắc đơn vị cũ là milliseconds. Nếu đơn vị cũ không được xác định, cần cảnh báo hoặc yêu cầu người dùng chọn cách diễn giải.

Tự động nâng cấp không chỉ là tìm và thay thế chuỗi. Một quy trình đáng tin cậy cần hiểu cấu trúc và semantics của DSL, biết phiên bản nguồn, biết phiên bản đích, kiểm tra điều kiện áp dụng và xác minh kết quả sau chuyển đổi.

## 2. Các loại nâng cấp trong hệ sinh thái DSL

Một lần nâng cấp có thể tác động đến nhiều lớp khác nhau.

### 2.1. Nâng cấp phiên bản ngôn ngữ

Compiler hoặc parser mới có thể hỗ trợ cú pháp mới và loại bỏ cú pháp cũ. Source DSL cần được chuyển đổi hoặc khai báo version phù hợp.

### 2.2. Nâng cấp compiler và runtime

Project có thể cần compiler mới để xử lý language feature, IR hoặc generated code mới. Runtime có thể thay đổi API, scheduling, serialization hoặc execution behavior.

### 2.3. Nâng cấp thư viện và plugin

Một dependency có thể đổi tên package, signature, cấu hình hoặc behavior. Migration có thể cập nhật declaration và call site.

### 2.4. Di trú schema

Schema dữ liệu có thể đổi tên field, đổi kiểu, thêm constraint hoặc tách một trường thành nhiều trường. Cần chuyển cả schema và dữ liệu hiện có nếu chúng phải tiếp tục tương thích.

### 2.5. Di trú API contract

Endpoint, request/response schema, error code hoặc authentication policy có thể thay đổi. Client DSL và server contract cần được nâng cấp theo quy tắc tương thích.

### 2.6. Di trú workflow và rule

Workflow có thể thay đổi step, transition, retry policy hoặc state model. Rule có thể đổi operator, priority hoặc action.

### 2.7. Nâng cấp cấu hình môi trường

Tên config key, default value, secret reference, connection setting và resource limit có thể thay đổi giữa các version.

### 2.8. Tái sinh generated artifact

Sau khi source hoặc compiler version thay đổi, generated code, query plan, binary artifact hoặc cache có thể cần được tạo lại.

Một công cụ cần phân biệt những loại nâng cấp này vì mỗi loại có rủi ro và phương thức phục hồi riêng.

## 3. Vì sao cần tự động nâng cấp?

Khi một hệ thống có nhiều project hoặc nhiều file DSL, sửa thủ công từng nơi dễ gây sai sót và tốn thời gian.

Tự động nâng cấp có thể:
- Giảm công việc lặp lại.
- Áp dụng cùng một quy tắc nhất quán.
- Hạn chế bỏ sót vị trí cần đổi.
- Cung cấp báo cáo về file và declaration bị ảnh hưởng.
- Tạo migration có thể chạy lại.
- Chuẩn hóa project trước khi dùng compiler/runtime mới.
- Giảm chi phí duy trì nhiều phiên bản.
- Giúp tổ chức chuyển đổi theo từng nhóm project.

Tuy nhiên, automation không có nghĩa là mọi thay đổi đều có thể tự quyết định. Nếu một migration cần suy luận ý nghĩa nghiệp vụ hoặc dữ liệu không đủ để xác định cách chuyển đổi, công cụ phải dừng ở trạng thái cần review.

## 4. Phiên bản nguồn và phiên bản đích

Mỗi lần nâng cấp cần xác định rõ điểm xuất phát và đích đến.

- **Source version:** phiên bản hiện tại của project hoặc artifact.
- **Target version:** phiên bản mà project cần đạt tới.
- **Migration path:** chuỗi bước chuyển đổi từ source đến target.
- **Compatibility range:** tập phiên bản được hỗ trợ.
- **Migration metadata:** thông tin ghi lại những bước đã áp dụng.

Ví dụ:

~~~text
project {
    languageVersion = "2.1"
    runtimeVersion = "5.4"
}
~~~

Project có thể cần nâng languageVersion lên 3.0 và runtimeVersion lên 6.0. Hai thành phần có thể có quy tắc tương thích độc lập.

### 4.1. Không suy đoán version từ cú pháp nếu có metadata

Một số cú pháp có thể xuất hiện ở nhiều phiên bản. Nếu project có manifest hoặc version declaration, nên dùng metadata đó làm nguồn chính.

### 4.2. Version thiếu hoặc không rõ

Nếu project không khai báo version, tool có thể phân tích feature để đưa ra khoảng phiên bản có thể phù hợp. Kết quả suy luận nên được đánh dấu là inferred và yêu cầu xác nhận khi có rủi ro.

### 4.3. Version không được hỗ trợ

Nếu source version quá cũ hoặc quá mới so với migration tool, không nên áp dụng một chuỗi chuyển đổi không đầy đủ. Hãy thông báo version được hỗ trợ và đề xuất đường nâng cấp phù hợp.

### 4.4. Version của từng thành phần

Project có thể có nhiều module dùng language version khác nhau hoặc dependency có version riêng. Không nên giả định mọi thành phần đều nâng cấp cùng một lúc.

## 5. Compatibility và breaking changes

Compatibility policy xác định thay đổi nào có thể được áp dụng mà không làm hỏng consumer.

### 5.1. Backward-compatible change

Một thay đổi thường được xem là tương thích ngược khi consumer cũ vẫn hoạt động theo contract đã cam kết. Ví dụ:
- Thêm operation mới.
- Thêm field response optional.
- Thêm giá trị mặc định an toàn.
- Bổ sung một capability không làm thay đổi hành vi cũ.

Tính tương thích còn phụ thuộc vào cách client xử lý unknown field và enum.

### 5.2. Breaking change

Một thay đổi có thể phá vỡ consumer:
- Xóa hoặc đổi tên field bắt buộc.
- Đổi kiểu dữ liệu.
- Thay đổi ý nghĩa của giá trị null.
- Đổi thứ tự hoặc semantics của rule.
- Loại bỏ keyword đang được dùng.
- Thay đổi default behavior.
- Đổi error handling hoặc transaction boundary.
- Thay đổi thứ tự side effect.

### 5.3. Deprecated feature

Một feature deprecated vẫn có thể hoạt động trong một số version nhưng đã được đánh dấu sẽ bị loại bỏ. Công cụ nên cảnh báo trước khi feature bị xóa để người dùng có thời gian chuyển đổi.

### 5.4. Compatibility matrix

Có thể mô tả khả năng tương thích theo bảng:

| Source | Target | Hỗ trợ | Cách xử lý |
|---|---|---|---|
| 1.x | 2.0 | Có | Migration trực tiếp |
| 2.0 | 3.0 | Có | Áp dụng migration 2-to-3 |
| 1.x | 3.0 | Có điều kiện | Qua version trung gian |
| 0.x | 3.0 | Không | Nâng cấp theo hướng dẫn thủ công |

### 5.5. Semantic compatibility

Source có thể parse được ở version mới nhưng hành vi lại thay đổi. Vì vậy, kiểm tra cú pháp không đủ; cần xem cả semantics và behavior contract.

## 6. Migration path và dependency graph

Một migration path là chuỗi các migration cần chạy để đi từ version nguồn đến version đích.

Ví dụ:

~~~text
DSL 1.0
   |
   v
DSL 1.5
   |
   v
DSL 2.0
   |
   v
DSL 3.0
~~~

Mỗi bước có thể yêu cầu một migration trước đó.

### 6.1. Direct migration

Nếu có migration trực tiếp từ 1.0 lên 3.0, tool có thể chọn nó khi quy tắc đã được định nghĩa và kiểm thử đầy đủ.

### 6.2. Sequential migration

Nếu chỉ có migration 1-to-2 và 2-to-3, tool cần chạy theo thứ tự. Không nên bỏ qua bước trung gian nếu nó chuẩn hóa cấu trúc hoặc dữ liệu mà migration tiếp theo cần.

### 6.3. Dependency graph

Migration có thể phụ thuộc lẫn nhau. Ví dụ đổi schema field cần chạy trước khi đổi expression sử dụng field đó.

~~~text
Update Type Definitions
        |
        v
Rename Field References
        |
        v
Update API Mapping
        |
        v
Regenerate Artifacts
        |
        v
Verify Project
~~~

### 6.4. Topological ordering

Nếu dependency graph không có cycle, có thể dùng topological sort để tìm thứ tự chạy hợp lệ.

### 6.5. Dependency cycle

Nếu hai migration phụ thuộc lẫn nhau, cần phân tích lại thiết kế hoặc tạo migration hợp nhất có semantics rõ. Không nên chọn thứ tự tùy ý để né cycle.

### 6.6. Migration bundle

Một release có thể đóng gói:
- Migration ID.
- Source và target version.
- Dependencies.
- Transformation rules.
- Preconditions.
- Postconditions.
- Rollback hoặc recovery guidance.
- Documentation link hoặc release note.

## 7. Kiến trúc của công cụ tự động nâng cấp

Một công cụ migration có thể gồm các thành phần:

~~~text
Project Scanner
      |
      v
Version Detector
      |
      v
Compatibility Analyzer
      |
      v
Migration Planner
      |
      v
Dry-run / Preview
      |
      v
Migration Executor
      |
      v
Validator / Verifier
      |
      v
Upgrade Report
~~~

### 7.1. Project scanner

Quét project để tìm manifest, source DSL, schema, config và artifact liên quan. Scanner cần tuân theo include/exclude rules và không tự ý sửa file.

### 7.2. Version detector

Đọc version từ manifest hoặc metadata. Nếu không có, có thể phân tích feature và báo mức độ tin cậy.

### 7.3. Compatibility analyzer

So sánh source version với target version, xác định feature đã deprecated hoặc removed và liệt kê migration cần thiết.

### 7.4. Migration planner

Tạo kế hoạch có thứ tự, hiển thị file bị ảnh hưởng, transformation dự kiến, conflict và thao tác cần người dùng quyết định.

### 7.5. Dry-run engine

Chạy logic phân tích và transformation trên bản sao trong bộ nhớ hoặc workspace tạm, không commit thay đổi vào project chính.

### 7.6. Executor

Áp dụng migration theo kế hoạch đã được xác nhận. Executor cần quản lý transaction, checkpoint, file permissions và trạng thái từng bước.

### 7.7. Verifier

Kiểm tra source mới, schema, dependency, generated artifact và postcondition sau migration.

### 7.8. Report generator

Tạo báo cáo kết quả, warning, file đã đổi, file cần review và thông tin phục hồi.

## 8. Phân tích source trước khi nâng cấp

Một migration tốt cần hiểu source DSL thay vì chỉ thay thế chuỗi văn bản.

### 8.1. Text-based replacement

Tìm và thay chuỗi đơn giản có thể phù hợp với thay đổi thuần văn bản, nhưng dễ nhầm:
- Keyword xuất hiện trong comment.
- Tên field xuất hiện trong string literal.
- Identifier là một phần của tên khác.
- Cú pháp nằm trong embedded code.
- Format khác nhau giữa các file.

### 8.2. AST-based migration

AST transformation parse source thành cây cấu trúc, tìm node có đúng loại và thay đổi node đó.

Ví dụ, đổi function call cũ:

~~~text
legacyDate.parse(value)
~~~

thành:

~~~text
Date.parse(value, format = "ISO")
~~~

AST migration có thể chỉ thay function call có symbol resolution trỏ đến legacyDate.parse, không thay chuỗi trùng tên trong comment hoặc string.

### 8.3. Type-aware migration

Nếu migration phụ thuộc kiểu, compiler hoặc migration engine cần type information. Ví dụ đổi phép cộng chuỗi và số chỉ có thể tự động khi biết kiểu operand.

### 8.4. Symbol resolution

Rename symbol cần tìm declaration và mọi reference thực sự trỏ đến declaration đó. Thay tên text có thể vô tình đổi một biến cùng tên ở scope khác.

### 8.5. Source location và formatting

Transformation nên giữ source location hoặc tạo mapping mới để người dùng xem diff và tìm lỗi. Formatter có thể được chạy sau migration để chuẩn hóa code.

### 8.6. Comment và annotation

Comment có thể chứa hướng dẫn hoặc metadata. Migration nên giữ comment, trừ khi có quy tắc rõ ràng để chuyển annotation cũ.

## 9. Codemod và transformation rule

Codemod là công cụ biến đổi source code có cấu trúc theo một quy tắc cụ thể.

### 9.1. Một rule migration

Một rule nên có:
- ID ổn định.
- Source version.
- Target version.
- Pattern nhận diện.
- Preconditions.
- Transformation.
- Postconditions.
- Severity hoặc risk level.
- Hướng dẫn khi không thể tự chuyển.

Ví dụ:

~~~text
migration "duration-unit-001" {
    from = "2.x"
    to = "3.0"

    match NumericTimeout(value)

    precondition:
        legacyTimeoutUnit == "MILLISECONDS"

    transform:
        replace with Duration.milliseconds(value)

    postcondition:
        expression.type == Duration
}
~~~

### 9.2. Preconditions

Precondition xác định điều kiện phải đúng trước khi transformation chạy. Nếu điều kiện không thỏa, migration phải skip hoặc báo conflict.

### 9.3. Postconditions

Postcondition xác nhận kết quả có hình dạng hoặc semantics mong đợi. Nếu không đạt, transaction không nên được commit.

### 9.4. Idempotent migration

Migration idempotent có thể chạy lại mà không tiếp tục thay đổi một source đã được chuyển. Có thể dùng target pattern để nhận biết code đã nâng cấp.

### 9.5. Rule ordering

Một transformation có thể làm thay đổi pattern mà rule khác cần. Migration bundle cần khai báo thứ tự hoặc dependency rõ.

### 9.6. Không tự động hóa khi thiếu ngữ nghĩa

Nếu một giá trị số có thể là milliseconds hoặc seconds tùy project, công cụ không được tự đoán. Nó nên đưa ra lựa chọn hoặc yêu cầu metadata.

## 10. Tự động nâng cấp cú pháp DSL

Cú pháp là một trong những mục tiêu phổ biến của migration.

### 10.1. Rename keyword

Nếu keyword cũ đổi tên, parser cũ hoặc migration parser có thể nhận diện cú pháp nguồn và chuyển sang keyword mới.

### 10.2. Thay đổi block syntax

Một DSL có thể chuyển từ dạng:

~~~text
task "send" {
    retryCount = 3
}
~~~

sang dạng:

~~~text
task "send" {
    retry {
        maxAttempts = 3
    }
}
~~~

Migration cần hiểu block cũ và chuyển property vào cấu trúc mới.

### 10.3. Đơn vị tường minh

Nếu version mới yêu cầu đơn vị duration, công cụ cần biết quy tắc của version cũ và chuyển đổi theo đơn vị được khai báo.

### 10.4. Operator replacement

Nếu operator cũ được thay thế, migration cần xác định đúng operator node và semantics. Không nên thay ký tự đơn thuần vì cùng một ký hiệu có thể xuất hiện trong string hoặc expression khác.

### 10.5. Grammar không tương thích

Nếu cú pháp cũ không thể parse bằng parser mới, migration tool cần parser cho version nguồn hoặc một parser compatibility. Không thể dựa vào parser đích để đọc mọi source cũ.

### 10.6. Format sau transformation

Sau khi AST được biến đổi, formatter có thể tạo indentation, quote style và line break thống nhất. Formatting nên tách khỏi semantics migration để diff dễ hiểu.

## 11. Tự động nâng cấp type và schema

Type và schema thường có tác động rộng vì nhiều module cùng tham chiếu.

### 11.1. Rename field

Ví dụ đổi customer.fullName thành customer.displayName. Migration phải cập nhật declaration, access expression, mapping, query, test và documentation reference nếu nằm trong scope.

### 11.2. Split field

Một trường address có thể được tách thành street, city và postalCode. Nếu dữ liệu cũ chỉ có một chuỗi tự do, không phải lúc nào cũng có thể phân tách chính xác tự động.

### 11.3. Merge field

Hai field firstName và lastName có thể được gộp thành fullName. Cần quy định cách xử lý null, whitespace, locale và dữ liệu đã chuẩn hóa.

### 11.4. Change type

Chuyển integer sang decimal có thể cần scale và rounding rule. Chuyển string sang date cần format và timezone rõ.

### 11.5. Required field

Nếu field mới trở thành required, migration cần tìm default hoặc lấy giá trị từ nguồn khác. Nếu không có nguồn xác định, cần báo dữ liệu thiếu.

### 11.6. Enum evolution

Khi enum value được rename hoặc loại bỏ, cần mapping cũ sang mới. Nếu có giá trị không thể ánh xạ, không nên chọn default tùy tiện.

### 11.7. Schema version

Mỗi schema có thể có version riêng. Project migration cần đồng bộ version của schema với code hoặc workflow sử dụng schema đó.

## 12. Tự động nâng cấp API contract và integration

API DSL thường mô tả endpoint, request, response, error và authentication. Migration cần giữ client và server tương thích theo policy.

### 12.1. Endpoint rename

Nếu path đổi, cập nhật declaration và mọi nơi gọi endpoint. Nếu server hỗ trợ cả path cũ và mới trong giai đoạn chuyển tiếp, migration có thể cập nhật client theo rollout plan.

### 12.2. Request field rename

Cập nhật schema, serializer, client call và mapping. Cần xác định server có chấp nhận field cũ trong thời gian tương thích hay không.

### 12.3. Response field type change

Nếu response đổi từ number sang string decimal, client phải thay đổi parser và model. Migration cần biết scale, precision và format.

### 12.4. Authentication upgrade

Chuyển từ API key sang OAuth có thể cần thay connector configuration, credential reference, token refresh và permission scope. Không thể tự sinh secret mới nếu cần thao tác của administrator.

### 12.5. Error contract change

Nếu error code hoặc error body đổi, cập nhật mapping và branch handling. Không nên xóa handler cũ trước khi chắc chắn server không còn trả lỗi cũ trong compatibility window.

### 12.6. Contract verification

Sau migration, so sánh generated client và contract với schema đích. Có thể dùng compatibility checker để xác định request/response có thay đổi phá vỡ consumer không.

## 13. Tự động nâng cấp dữ liệu

Di trú dữ liệu là chuyển các record đang tồn tại sang schema hoặc semantics mới.

### 13.1. Schema migration và data migration

Schema migration thay cấu trúc lưu trữ. Data migration chuyển nội dung record. Hai bước có thể cần chạy theo thứ tự cụ thể.

### 13.2. Expand-and-contract

Một chiến lược phổ biến:
1. Expand: thêm field hoặc cấu trúc mới nhưng vẫn hỗ trợ dữ liệu cũ.
2. Migrate: chuyển dần dữ liệu sang cấu trúc mới.
3. Switch: chuyển application sang đọc/ghi cấu trúc mới.
4. Contract: xóa cấu trúc cũ sau khi không còn consumer.

Cách này giảm downtime và cho phép rollout theo từng giai đoạn.

### 13.3. Backfill

Backfill điền dữ liệu mới cho record cũ. Có thể chạy theo batch, checkpoint và giới hạn tốc độ để không làm quá tải database.

### 13.4. Data validation

Sau backfill, kiểm tra:
- Số record đã xử lý.
- Record còn thiếu field.
- Giá trị ngoài range.
- Duplicate key.
- Referential integrity.
- Tổng số hoặc checksum.
- Các invariant nghiệp vụ.

### 13.5. Migration dữ liệu không mất mát

Nếu chuyển decimal hoặc timestamp, cần quy định precision, rounding và timezone. Lưu raw source hoặc backup khi biến đổi có thể mất thông tin.

### 13.6. Dữ liệu lớn

Với bảng lớn, migration cần chia batch, giới hạn lock, theo dõi progress và hỗ trợ resume. Một transaction khổng lồ có thể gây lock lâu và tăng log.

## 14. Tự động nâng cấp cấu hình và dependency

Project có thể cần cập nhật cấu hình để runtime mới hoạt động.

### 14.1. Rename config key

Cập nhật key cũ thành key mới, đồng thời xử lý trường hợp cả hai key cùng tồn tại.

### 14.2. Default value change

Nếu default thay đổi, project có thể thay đổi hành vi dù không có dòng config nào đổi. Migration nên thêm giá trị tường minh nếu muốn giữ behavior cũ.

### 14.3. Dependency version

Một dependency mới có thể yêu cầu version runtime hoặc plugin khác. Dependency resolver cần kiểm tra conflict và lockfile.

### 14.4. Configuration secret

Không copy secret vào file source. Migration nên giữ credential reference hoặc hướng dẫn người dùng cập nhật secret trong hệ thống quản lý phù hợp.

### 14.5. Environment-specific configuration

Dev, test, staging và production có thể dùng endpoint, quota hoặc credential khác nhau. Migration cần bảo toàn các profile và không ghi đè giá trị môi trường bằng default chung.

### 14.6. Lockfile

Sau khi nâng dependency, lockfile cần được cập nhật nhất quán. Không nên sửa lockfile bằng text replacement nếu format có checksum hoặc resolution metadata.

## 15. Dry-run và preview

Dry-run cho phép xem kế hoạch và kết quả dự kiến trước khi thay đổi project chính.

### 15.1. Mục đích

Dry-run giúp:
- Phát hiện file sẽ bị thay đổi.
- Xem diff.
- Tính số migration được áp dụng.
- Tìm conflict và unsupported pattern.
- Ước lượng thời gian hoặc dung lượng.
- Xác nhận precondition.

### 15.2. Ví dụ lệnh

~~~bash
dsl-upgrade plan --from 2.1 --to 3.0 --dry-run
~~~

Đây là CLI minh họa; tên lệnh thực tế tùy công cụ.

### 15.3. Báo cáo preview

Một preview có thể cho biết:
- 12 file sẽ được sửa.
- 3 file cần format.
- 2 migration tự động an toàn.
- 1 migration cần lựa chọn thủ công.
- 0 file bị xóa.
- 1 dependency conflict.

### 15.4. Không ghi file trong dry-run

Dry-run đúng nghĩa không commit thay đổi vào workspace chính. Có thể tạo artifact tạm hoặc diff preview nhưng phải làm rõ vị trí và vòng đời của chúng.

### 15.5. Dry-run không thay thế backup

Preview giúp phát hiện vấn đề trước khi chạy, nhưng không bảo vệ dữ liệu nếu có lỗi trong quá trình thực thi. Backup và checkpoint vẫn cần thiết.

## 16. Backup, transaction và checkpoint

Nâng cấp có thể sửa nhiều file hoặc dữ liệu. Cần có cơ chế phục hồi nếu quá trình bị gián đoạn.

### 16.1. Backup source

Trước khi sửa source, lưu bản gốc hoặc dùng version control để có thể khôi phục diff.

### 16.2. Backup dữ liệu

Với data migration, backup cần nhất quán và có thể phục hồi. Xác định retention, encryption và quyền truy cập.

### 16.3. File transaction

Có thể ghi file mới vào temporary path, xác minh thành công rồi atomically replace file cũ. Tránh để file ở trạng thái ghi dở nếu process crash.

### 16.4. Project transaction

Nếu nhiều file cần thay đổi cùng nhau, công cụ có thể tạo staging workspace và chỉ promote khi toàn bộ transformation hợp lệ.

### 16.5. Checkpoint

Checkpoint lưu migration ID, bước hiện tại, số record đã xử lý, last key, checksum và trạng thái. Khi resume, executor tiếp tục từ checkpoint an toàn.

### 16.6. Idempotent execution

Một bước đã hoàn tất không nên bị thực hiện lại theo cách tạo side effect trùng. Migration cần lưu completion marker hoặc thiết kế operation idempotent.

### 16.7. Locking

Có thể dùng project lock hoặc migration lock để ngăn hai process nâng cấp cùng một workspace hoặc database đồng thời.

## 17. Rollback và roll-forward

Không phải migration nào cũng có thể đảo ngược.

### 17.1. Rollback

Rollback đưa project hoặc dữ liệu về trạng thái trước migration. Nó phù hợp khi transformation có thể đảo ngược và không có side effect không thể phục hồi.

### 17.2. Roll-forward

Roll-forward sửa trạng thái hiện tại bằng một migration mới. Đây thường là lựa chọn phù hợp khi dữ liệu đã bị biến đổi không thể đảo ngược hoặc hệ thống đã nhận traffic.

### 17.3. Reversible migration

Ví dụ rename field có thể đảo ngược nếu không có dữ liệu mới hoặc conflict phát sinh sau rename.

### 17.4. Irreversible migration

Ví dụ gộp hai field thành một chuỗi và bỏ mất cấu trúc ban đầu có thể không thể đảo ngược. Cần backup hoặc lưu dữ liệu nguồn trong giai đoạn chuyển đổi.

### 17.5. Compensation

Với migration có side effect ngoài database, có thể cần hành động bù thay vì rollback. Ví dụ cập nhật một resource ở service khác có thể cần gửi lệnh khôi phục.

### 17.6. Rollback plan

Mỗi migration quan trọng nên nêu:
- Điều kiện rollback.
- Các artifact cần khôi phục.
- Cách phục hồi dữ liệu.
- Tác động với version đã deploy.
- Cách xử lý event hoặc request đã phát sinh.
- Trường hợp phải roll-forward.

## 18. Thực thi nâng cấp theo giai đoạn

Nâng cấp đồng loạt có thể gây downtime hoặc rủi ro lớn. Một số hệ thống nên rollout theo từng nhóm.

### 18.1. Canary upgrade

Nâng cấp một nhóm nhỏ project hoặc instance trước, theo dõi lỗi và hiệu năng rồi mới mở rộng.

### 18.2. Blue-green

Duy trì môi trường cũ và môi trường mới song song. Chuyển traffic khi môi trường mới đã được xác minh.

### 18.3. Rolling upgrade

Nâng cấp từng instance hoặc node. Cần bảo đảm các version có thể cùng tồn tại trong giai đoạn chuyển tiếp.

### 18.4. Feature flag

Có thể bật behavior mới theo feature flag. Giữ đường cũ trong thời gian migration và chỉ loại bỏ sau khi xác nhận không còn consumer.

### 18.5. Compatibility window

Trong giai đoạn chuyển tiếp, server hoặc runtime có thể hỗ trợ cả contract cũ và mới. Cần quy định thời điểm kết thúc hỗ trợ version cũ.

### 18.6. Traffic và data consistency

Nếu hai version cùng ghi dữ liệu, cần quy định field ownership, dual-write, read preference và cách đối chiếu. Dual-write không có transaction phù hợp có thể tạo trạng thái lệch.

## 19. Conflict và migration cần người quyết định

Không phải transformation nào cũng có một kết quả duy nhất.

### 19.1. Rename conflict

Tên đích đã được dùng cho một symbol khác. Công cụ cần báo conflict thay vì ghi đè declaration.

### 19.2. Default ambiguity

Một field mới cần giá trị nhưng dữ liệu cũ không có nguồn xác định. Người dùng cần chọn default hoặc cung cấp mapping.

### 19.3. Duplicate transformation

Một file có thể đã được sửa thủ công một phần. Migration cần nhận diện trạng thái hỗn hợp và tránh áp dụng mù quáng.

### 19.4. Multiple candidate mappings

Một enum cũ có thể tương ứng với nhiều enum mới. Công cụ nên trình bày lựa chọn và ảnh hưởng.

### 19.5. Manual intervention

Một migration có thể đánh dấu:
- AUTO_SAFE: có thể tự áp dụng.
- REVIEW_REQUIRED: cần xem diff và xác nhận.
- BLOCKED: không thể tiếp tục nếu thiếu dữ liệu.
- MANUAL_ONLY: cần người dùng sửa theo hướng dẫn.

### 19.6. Conflict resolution record

Lưu quyết định của người dùng, thời điểm, migration ID và lựa chọn được chọn để lần sau có thể tái hiện.

## 20. Báo cáo và audit trail

Một công cụ nâng cấp cần cho biết đã làm gì, ở đâu và kết quả ra sao.

### 20.1. Upgrade report

Báo cáo có thể gồm:
- Project identifier.
- Source và target version.
- Thời điểm bắt đầu/kết thúc.
- Migration IDs.
- File được tạo, sửa hoặc bỏ qua.
- Số transformation thành công.
- Warning và conflict.
- Postcondition result.
- Backup/checkpoint reference.
- Trạng thái cuối.

### 20.2. Audit trail

Audit ghi lại ai khởi tạo, ai phê duyệt, migration nào chạy, phiên bản tool, môi trường và thao tác manual. Không ghi secret hoặc payload nhạy cảm.

### 20.3. Diff

Diff giúp review từng thay đổi. Với source DSL, nên giữ context và source mapping để người review hiểu transformation.

### 20.4. Machine-readable report

JSON hoặc định dạng có schema giúp CI pipeline và dashboard đọc kết quả tự động. Schema báo cáo cần có version.

### 20.5. Status

Một migration có thể có trạng thái:
- PLANNED.
- PREVIEWED.
- APPROVED.
- RUNNING.
- SUCCEEDED.
- PARTIALLY_SUCCEEDED.
- FAILED.
- ROLLED_BACK.
- NEEDS_ATTENTION.

Không nên gộp PARTIALLY_SUCCEEDED thành SUCCEEDED nếu còn file hoặc record chưa được xử lý.

## 21. Kiểm tra sau nâng cấp

Sau khi migration chạy, cần xác nhận project thực sự dùng được với target version.

### 21.1. Parse và compile

Parse source bằng parser đích và compile theo target compiler. Lỗi cú pháp hoặc type cần được báo theo file và vị trí.

### 21.2. Schema validation

Kiểm tra schema mới, reference và dữ liệu theo constraint.

### 21.3. Dependency resolution

Đảm bảo dependency graph không còn conflict và lockfile nhất quán.

### 21.4. Generated artifact

Tái sinh code, client, query hoặc binary artifact nếu cần. Xác nhận artifact được tạo từ source và compiler version mới.

### 21.5. Behavioral verification

Chạy test xác nhận output và side effect giữ semantics. Với migration nghiệp vụ, cần test case trước và sau.

### 21.6. Data reconciliation

So sánh count, checksum, aggregate hoặc invariant trước và sau di trú. Sai lệch cần được giải thích.

### 21.7. Runtime smoke test

Khởi chạy một luồng cơ bản trên môi trường thử nghiệm để xác nhận integration và runtime hoạt động.

### 21.8. Không tự coi parse thành công là migration hoàn tất

Source có thể compile nhưng behavior vẫn sai. Cần postcondition và test phù hợp với loại migration.

## 22. Tích hợp tự động nâng cấp vào CI/CD

CI/CD có thể kiểm tra migration mỗi khi project hoặc dependency thay đổi.

### 22.1. Upgrade check

Pipeline kiểm tra source có feature deprecated hoặc version không tương thích.

### 22.2. Migration preview

Tạo diff preview và report để reviewer biết những gì sẽ thay đổi.

### 22.3. Approval gate

Migration có risk cao có thể yêu cầu approval trước khi chạy trên môi trường chia sẻ hoặc production.

### 22.4. Automated test

Chạy parse, compile, unit test, contract test và migration test trong pipeline.

### 22.5. Artifact promotion

Chỉ promote artifact đã được tạo và kiểm tra với đúng target version.

### 22.6. Environment sequencing

Có thể nâng cấp dev, test, staging rồi production. Mỗi môi trường cần ghi lại migration version và trạng thái.

### 22.7. Drift detection

Nếu source project khác với version hoặc schema đã khai báo, pipeline nên báo drift. Không tự động sửa production config khi chưa có kế hoạch được duyệt.

## 23. Thiết kế migration DSL

Một migration DSL có thể mô tả source version, target version, pattern, transform và verification.

Ví dụ minh họa:

~~~text
migration "rename-customer-name" {
    from = "2.x"
    to = "3.0"

    description = "Rename fullName to displayName"

    match FieldAccess(
        receiver = Customer,
        field = "fullName"
    )

    precondition:
        targetFieldDoesNotConflict("displayName")

    transform:
        renameField("fullName", "displayName")

    verify:
        noReferenceRemains("fullName")
        allReferencesResolve("displayName")
}
~~~

### 23.1. Khai báo phạm vi

Migration nên chỉ rõ áp dụng cho module, file pattern, schema hoặc operation nào. Phạm vi hẹp giảm nguy cơ sửa nhầm.

### 23.2. Pattern matching

Pattern có thể dựa trên AST node, symbol, type hoặc metadata thay vì chỉ text.

### 23.3. Transform action

Action có thể gồm rename symbol, wrap expression, change type, move declaration, add default, split field hoặc update config.

### 23.4. Verification rule

Verification có thể kiểm tra:
- Không còn pattern cũ.
- Không tạo duplicate symbol.
- Type hợp lệ.
- Schema references resolve.
- Version declaration đã đổi.
- Invariant dữ liệu được giữ.

### 23.5. Migration metadata

Mỗi project có thể lưu migration history để biết rule nào đã chạy. History giúp resume và tránh chạy lặp.

### 23.6. Giới hạn quyền của migration

Migration code có thể tác động nhiều file hoặc dữ liệu. Nên giới hạn filesystem scope, database permission và external capability theo nguyên tắc least privilege.

## 24. An toàn và bảo mật khi nâng cấp

Migration thường có quyền đọc hoặc ghi nhiều tài nguyên, nên cần được kiểm soát.

### 24.1. Least privilege

Công cụ chỉ nên có quyền cần thiết cho project và môi trường hiện tại. Migration source không nên tự động nhận quyền truy cập production secret.

### 24.2. Supply chain

Migration bundle và plugin cần có nguồn tin cậy, version, checksum hoặc signature. Không chạy script không rõ nguồn chỉ vì nó được khai báo trong manifest.

### 24.3. Secret handling

Không ghi secret vào report, diff hoặc log. Nếu migration cần đổi credential, dùng secret manager hoặc bước cấu hình riêng.

### 24.4. Data privacy

Backup và staging data cần được mã hóa và có retention phù hợp. Dữ liệu production không nên được sao chép sang môi trường kém bảo vệ.

### 24.5. Approval và audit

Thao tác phá hủy dữ liệu hoặc thay đổi production nên có quyền và audit rõ. Công cụ cần phân biệt preview, approval và execution.

### 24.6. Resource limits

Giới hạn CPU, memory, file count, record batch size và execution time để một migration lỗi không làm cạn tài nguyên.

## 25. Hiệu năng của migration

Migration có thể chạy trên project lớn hoặc database lớn. Thiết kế hiệu năng ảnh hưởng trực tiếp đến downtime và thời gian triển khai.

### 25.1. Incremental scanning

Chỉ phân tích file đã thay đổi hoặc file có khả năng chứa pattern cần chuyển đổi khi có cache đáng tin cậy.

### 25.2. Parallel transformation

Các file độc lập có thể được chuyển đổi song song. Tuy nhiên, symbol resolution toàn project hoặc shared metadata có thể yêu cầu phase tuần tự.

### 25.3. Batch data migration

Chia dữ liệu thành batch có kích thước giới hạn, lưu checkpoint và điều chỉnh tốc độ theo tải database.

### 25.4. Streaming

Đọc và xử lý dữ liệu theo stream thay vì tải toàn bộ bảng hoặc file lớn vào memory.

### 25.5. Index và lock

Migration schema hoặc backfill có thể tạo index và lock bảng. Cần chọn cách thực thi phù hợp với database và SLA.

### 25.6. Progress reporting

Báo tiến độ theo số file, record hoặc phase. Không ước lượng phần trăm dựa trên số bước nếu mỗi bước có chi phí rất khác nhau.

## 26. Những lỗi thiết kế thường gặp

### 26.1. Chạy migration mà không biết source version

Một transformation có thể áp dụng sai cho source đã ở version mới. Hãy kiểm tra version và precondition.

### 26.2. Chỉ dùng text replacement

Text replacement có thể đổi comment, string hoặc identifier không liên quan. Dùng AST và symbol resolution khi cần.

### 26.3. Không có dry-run

Người dùng không nhìn thấy diff hoặc conflict trước khi file bị sửa. Hãy cung cấp preview.

### 26.4. Không lưu backup hoặc checkpoint

Process crash có thể để project ở trạng thái nửa cũ nửa mới. Cần staging, transaction hoặc checkpoint.

### 26.5. Migration không idempotent

Chạy lại có thể lặp transformation hoặc nhân đôi dữ liệu. Dùng migration history và thiết kế operation an toàn khi retry.

### 26.6. Default tùy tiện

Gán một giá trị mặc định không có căn cứ có thể làm thay đổi nghiệp vụ. Cần yêu cầu lựa chọn nếu không thể suy ra.

### 26.7. Bỏ qua generated artifact

Source đã đổi nhưng generated code hoặc cache vẫn ở version cũ. Tái sinh hoặc invalidation artifact theo dependency.

### 26.8. Không xác minh behavior

Compile thành công không chứng minh semantics được giữ. Cần test và reconciliation.

### 26.9. Rollback không thực tế

Một migration đã phát event hoặc tạo side effect ngoài hệ thống có thể không thể đảo ngược hoàn toàn. Cần recovery hoặc roll-forward plan.

### 26.10. Báo thành công khi còn phần chưa xử lý

Partial success cần trạng thái và report riêng. Không đánh dấu toàn project hoàn tất khi còn conflict hoặc migration pending.

## 27. Quy trình tự động nâng cấp đề xuất

Một quy trình tổng quát:

1. Xác định project và môi trường đích.
2. Đọc manifest và xác định source version.
3. Kiểm tra target version và compatibility matrix.
4. Quét source, schema, config, dependency và artifact liên quan.
5. Xây migration dependency graph.
6. Kiểm tra precondition và phát hiện conflict.
7. Tạo dry-run report và diff.
8. Yêu cầu review hoặc approval cho migration có rủi ro.
9. Tạo backup hoặc staging workspace.
10. Thực thi migration theo thứ tự dependency.
11. Lưu checkpoint và migration history.
12. Chạy parse, type check, compile và schema validation.
13. Chạy test và data reconciliation.
14. Tái sinh artifact và cập nhật version metadata.
15. Promote theo staged rollout.
16. Theo dõi runtime và xử lý rollback hoặc roll-forward nếu cần.
17. Lưu audit trail và upgrade report.

## 28. Ví dụ tổng hợp: nâng cấp DSL từ version 2 lên version 3

Giả sử version 3 có ba thay đổi:

- Timeout phải có đơn vị tường minh.
- Field customer.fullName được đổi thành customer.displayName.
- Retry configuration được chuyển từ retryCount thành block retry.

### 28.1. Source version 2

~~~text
project {
    languageVersion = "2.4"
}

service "customer" {
    timeout = 5000
    retryCount = 3
}

rule "display_customer" {
    when customer.active
    then print(customer.fullName)
}
~~~

### 28.2. Target version 3

~~~text
project {
    languageVersion = "3.0"
}

service "customer" {
    timeout = 5 seconds

    retry {
        maxAttempts = 3
    }
}

rule "display_customer" {
    when customer.active
    then print(customer.displayName)
}
~~~

### 28.3. Phân tích migration

Công cụ đọc version 2.4, xác định target 3.0 và chọn migration bundle 2-to-3. Nó kiểm tra:
- timeout cũ được định nghĩa theo milliseconds.
- retryCount chưa có block retry.
- customer.displayName tồn tại trong schema đích hoặc có rule rename tương ứng.
- Không có symbol displayName gây conflict.

### 28.4. Dry-run

Preview cho thấy:
- Một file DSL sẽ được sửa.
- Ba transformation được đề xuất.
- Một schema mapping cần cập nhật.
- Không có dependency conflict.
- Cần xác nhận default retry semantics nếu version 2 dùng cách đếm attempts khác.

### 28.5. Thực thi

Sau khi được xác nhận, executor:
1. Tạo bản sao hoặc backup source.
2. Chuyển timeout thành duration.
3. Chuyển retryCount thành retry block.
4. Rename field reference bằng symbol-aware transformation.
5. Cập nhật languageVersion.
6. Lưu file và migration history.

### 28.6. Verification

Verifier:
- Parse source bằng DSL 3.0.
- Type-check field reference.
- Xác nhận không còn retryCount cũ.
- Xác nhận timeout có kiểu Duration.
- Chạy rule test.
- So sánh output trước và sau trên test fixture.

### 28.7. Báo cáo

Report ghi migration ID, source/target version, file thay đổi, transformation áp dụng, warning, test result và backup reference. Nếu retry semantics không xác định được, migration không được tự đánh dấu hoàn tất.

## 29. Bài tập tự kiểm tra

### Bài 1: Phân loại nâng cấp

Một project nâng compiler, schema, API contract và runtime. Hãy phân loại từng thay đổi và nêu tài nguyên cần di trú.

### Bài 2: Compatibility

Một version mới xóa field response cũ và thêm field mới bắt buộc trong request. Giải thích vì sao đây là breaking change và đề xuất cách chuyển tiếp.

### Bài 3: Migration path

Có migration 1-to-2, 2-to-3 và 1-to-3. Hãy chọn path cho project version 1 và nêu điều kiện để chọn đường trực tiếp.

### Bài 4: AST codemod

Một function được đổi tên nhưng cùng identifier xuất hiện trong comment và string. Giải thích vì sao text replacement nguy hiểm và AST migration xử lý thế nào.

### Bài 5: Schema migration

Một field address được tách thành street, city và postalCode nhưng dữ liệu cũ là chuỗi tự do. Hãy xác định phần nào tự động được và phần nào cần review.

### Bài 6: Dry-run và backup

Thiết kế report preview cho migration có 20 file và 2 schema. Nêu cách lưu backup và phục hồi nếu bước thứ ba thất bại.

### Bài 7: Data backfill

Một bảng có hàng chục triệu record cần thêm field mới. Hãy thiết kế batch size, checkpoint, validation và cách giảm lock.

### Bài 8: Rollback

Một migration đã cập nhật database và phát event sang hệ thống ngoài. Giải thích vì sao rollback đơn giản có thể không đủ và khi nào cần roll-forward hoặc compensation.

### Bài 9: CI/CD

Thiết kế pipeline kiểm tra version drift, dry-run, approval, migration test và staged rollout.

### Bài 10: Migration DSL

Viết migration giả định có source version, target version, precondition, transformation, postcondition và conflict handling.

## Kết luận

Tự động nâng cấp giúp project DSL chuyển từ phiên bản cũ sang phiên bản mới một cách nhất quán, nhưng chỉ an toàn khi công cụ biết rõ source version, target version và semantics của từng thay đổi. Một hệ thống migration cần phân tích source có cấu trúc, lập dependency graph, kiểm tra precondition, cung cấp dry-run và diff, sau đó thực thi bằng staging, backup, checkpoint và migration history. Những thay đổi không thể suy luận chắc chắn phải được đưa ra review thay vì tự gán giá trị hoặc sửa dữ liệu theo phỏng đoán. Sau khi chuyển đổi, cần kiểm tra cú pháp, kiểu, schema, dependency, generated artifact, behavior và dữ liệu. Với rollout nhiều môi trường, staged deployment, audit và kế hoạch rollback hoặc roll-forward giúp kiểm soát rủi ro. Khi các migration có version, có thể tái hiện, có postcondition và được kiểm thử, tự động nâng cấp trở thành một phần có thể quản lý của vòng đời DSL.

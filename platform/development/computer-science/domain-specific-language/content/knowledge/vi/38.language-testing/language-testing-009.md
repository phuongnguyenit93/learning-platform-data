# Kiểm thử mã sinh

Trong kiểm thử ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), **kiểm thử mã sinh (generated code testing)** là quá trình xác minh mã hoặc artifact được tạo ra từ DSL có đúng cấu trúc, đúng ngữ nghĩa, biên dịch được, chạy đúng và đáp ứng các yêu cầu chất lượng của hệ thống. Một DSL compiler có thể nhận model, rule, schema hoặc workflow rồi sinh Java, Kotlin, SQL, YAML, source code khác hay deployment manifest. Kiểm thử phải xác minh cả mối quan hệ giữa input DSL và output được tạo ra, không chỉ kiểm tra generator có chạy mà không báo lỗi.

Ví dụ, người dùng khai báo một service trong DSL:

~~~text
service OrderService {
    operation findOrder(id: UUID): Order
}
~~~

Generator có thể tạo Java interface, DTO, adapter hoặc cấu hình dependency injection. Một lỗi nhỏ trong generator có thể làm sai kiểu trả về, mất annotation, tạo tên method trùng hoặc sinh source không biên dịch được. Vì vậy, kiểm thử mã sinh cần bao gồm nhiều tầng: so sánh output với kết quả mong đợi, phân tích cấu trúc output, compile, thực thi, kiểm tra contract, kiểm tra tính xác định và thử các trường hợp biên.

## 1. Mã sinh trong DSL là gì?

Mã sinh là output được tạo tự động từ một input có cấu trúc. Input có thể là DSL source, AST, domain model, schema hoặc metadata đã được phân tích.

### 1.1. Source generation

Source generator tạo file mã nguồn cho ngôn ngữ đích, ví dụ Java, Kotlin, TypeScript, SQL hoặc một DSL khác. Output thường được đưa vào compiler tiếp theo.

### 1.2. Configuration generation

Generator có thể tạo file cấu hình như YAML, JSON, XML, properties hoặc deployment manifest. Những file này cần được kiểm tra cú pháp và semantics theo hệ thống tiêu thụ chúng.

### 1.3. Artifact generation

Một số generator tạo bytecode, binary descriptor, schema bundle, API client, documentation hoặc metadata. Không phải output nào cũng là source code có thể đọc trực tiếp.

### 1.4. Model transformation

Trước khi in source, toolchain có thể chuyển DSL model sang intermediate representation (IR), sau đó từ IR sang output. Kiểm thử cần xác định lỗi nằm ở parsing, semantic analysis, model transformation hay code emission.

### 1.5. Generator contract

Generator có contract về input được hỗ trợ, output format, target language version, naming convention, runtime dependency và behavior khi input không hợp lệ. Bộ kiểm thử nên phản ánh contract này.

## 2. Mục tiêu của kiểm thử mã sinh

Một bộ kiểm thử tốt xác minh output đáp ứng yêu cầu từ hình thức đến hành vi.

### 2.1. Output đúng cấu trúc

File được tạo có đúng declaration, field, method, import, annotation, block và metadata theo model.

### 2.2. Output đúng ngữ nghĩa

Mã sinh thể hiện đúng ý nghĩa của DSL. Ví dụ một field nullable phải được biểu diễn theo đúng semantics của target language hoặc runtime library.

### 2.3. Output hợp lệ với toolchain đích

Source cần compile được với compiler version và dependency đã công bố. Manifest cần được parser hoặc validator của nền tảng đích chấp nhận.

### 2.4. Runtime behavior đúng

Compile thành công chưa chứng minh chương trình chạy đúng. Cần kiểm tra hành vi với input đại diện, boundary và error cases.

### 2.5. Output ổn định

Cùng input, cấu hình và generator version cần tạo output xác định nếu generator được thiết kế deterministic. Output không nên thay đổi do thứ tự map ngẫu nhiên hoặc timestamp không cần thiết.

### 2.6. Regression protection

Khi generator thay đổi, test giúp phát hiện output cũ bị thay đổi ngoài ý muốn. Đây là điều quan trọng vì generated code có thể được nhiều module hoặc người dùng phụ thuộc.

### 2.7. Traceability

Có thể liên kết output với source declaration, generator rule và source location. Điều này giúp tìm nguyên nhân khi một method hoặc field được sinh sai.

## 3. Các tầng kiểm thử mã sinh

Không có một loại test duy nhất đủ để chứng minh mọi khía cạnh của generated code.

| Tầng kiểm thử | Kiểm tra điều gì |
|---|---|
| Golden / snapshot | Output văn bản có đúng như mong đợi |
| Structural | Cấu trúc AST hoặc document tree đúng |
| Compilation | Output hợp lệ với compiler/parser đích |
| Semantic | Type, signature, schema và contract đúng |
| Runtime | Hành vi khi thực thi đúng |
| Property-based | Nhiều input được sinh tự động vẫn giữ invariant |
| Differential | So sánh với implementation hoặc oracle khác |
| Metamorphic | Quan hệ giữa các input biến đổi và output |
| Integration | Kết quả hoạt động trong hệ thống thật hoặc test environment |
| Security | Output không tạo injection hoặc cấu hình nguy hiểm |
| Performance | Generator và output đáp ứng giới hạn hiệu năng |

### 3.1. Golden test

Golden test so sánh output sinh ra với file expected được lưu trong repository. Nó hữu ích cho formatter, import ordering, naming và cấu trúc source.

### 3.2. Structural test

Structural test parse output thành AST hoặc document model rồi kiểm tra declaration, type và quan hệ thay vì so từng ký tự.

### 3.3. Compilation test

Compile generated source bằng target compiler thực tế. Với YAML/JSON/SQL, dùng parser hoặc validator tương ứng.

### 3.4. Runtime test

Chạy generated artifact với input kiểm thử và xác minh kết quả, side effect hoặc exception.

### 3.5. Property-based test

Sinh nhiều DSL input từ một generator dữ liệu và kiểm tra các thuộc tính phải luôn đúng.

### 3.6. Differential test

So sánh output hoặc behavior với một implementation tham chiếu, phiên bản generator trước hoặc một đường thực thi độc lập.

### 3.7. Integration test

Đưa generated output vào consumer thực tế như application compiler, schema registry, database test instance hoặc deployment validator.

## 4. Golden tests và snapshot tests

Golden test là cách trực quan để kiểm soát thay đổi văn bản do generator tạo ra.

### 4.1. Cách hoạt động

Test tạo output từ fixture DSL, đọc file expected và so sánh hai nội dung. Nếu khác nhau, test báo diff để reviewer xem thay đổi.

### 4.2. Cấu trúc fixture

Có thể tổ chức theo cặp input/output:

~~~text
tests/
  generator/
    fixtures/
      simple-service/
        input.dsl
        expected/
          OrderService.java
          OrderDto.java
      nullable-field/
        input.dsl
        expected/
          Customer.java
~~~

### 4.3. Ưu điểm

Golden file cho thấy chính xác output thay đổi ra sao. Nó đặc biệt hữu ích khi output là source code hoặc config mà con người cần review.

### 4.4. Hạn chế

Một thay đổi whitespace hoặc import order có thể tạo diff lớn dù semantics không đổi. Golden test cũng không chứng minh output compile hoặc chạy đúng.

### 4.5. Snapshot update

Không tự động chấp nhận mọi snapshot mới sau khi test fail. Cần review diff, hiểu lý do thay đổi và chạy thêm structural/compile tests trước khi cập nhật expected output.

### 4.6. Golden file nhỏ và tập trung

Mỗi fixture nên kiểm tra một hoặc vài đặc tính rõ. Fixture quá lớn khiến diff khó đọc và khó xác định regression.

### 4.7. Không snapshot dữ liệu biến động

Tránh ghi timestamp, absolute path, random identifier hoặc thông tin môi trường vào golden output nếu chúng không thuộc contract. Nếu bắt buộc, dùng clock hoặc ID provider giả lập để tạo kết quả xác định.

### 4.8. Normalization

Có thể chuẩn hóa line ending hoặc metadata không thuộc semantics trước khi so sánh. Không chuẩn hóa quá rộng đến mức che lỗi formatting hoặc nội dung quan trọng.

## 5. Kiểm thử cấu trúc bằng AST

So sánh văn bản không phải lúc nào cũng là cách tốt nhất để kiểm tra source code.

### 5.1. Parse generated source

Dùng parser của ngôn ngữ đích để chuyển output thành AST. Nếu không parse được, test phát hiện lỗi cú pháp trước khi chạy compiler đầy đủ.

### 5.2. Kiểm tra declaration

Xác minh class, interface, enum, field, method, constructor và modifier được tạo đúng.

### 5.3. Kiểm tra signature

Kiểm tra tên method, parameter order, generic type, return type, visibility và exception declaration.

### 5.4. Kiểm tra annotation

Annotation như nullability, serialization, validation hoặc dependency injection có thể ảnh hưởng runtime. Structural test nên xác minh annotation cần thiết xuất hiện đúng vị trí và giá trị.

### 5.5. Kiểm tra import

Xác minh import được tạo đúng, không thiếu type và không tạo import mơ hồ hoặc không dùng nếu policy yêu cầu output sạch.

### 5.6. Kiểm tra modifier

Public/private, static/final, async hoặc abstract modifier có thể làm thay đổi API và semantics. Kiểm tra theo AST giúp tránh chỉ dựa vào chuỗi.

### 5.7. Kiểm tra cấu trúc config

Với YAML/JSON/XML, parse thành tree rồi kiểm tra key, value, type và nesting. Không chỉ tìm substring trong file.

### 5.8. Structural assertion có ý nghĩa

Assertion nên nói rõ contract, ví dụ class OrderService có method findOrder nhận UUID và trả Order. Assertion chỉ kiểm tra số node hoặc tên file thường chưa đủ.

## 6. Compilation tests

Compilation test xác minh generated source hợp lệ với compiler và dependency của target.

### 6.1. Compile đúng target version

Nếu DSL hỗ trợ Java 17 và Java 21, test cần chạy với các target được công bố. Mã sinh dùng API mới có thể compile trên một JDK nhưng thất bại trên JDK cũ.

### 6.2. Dependency classpath

Generated source có thể tham chiếu runtime library, annotation hoặc framework. Compile test phải sử dụng classpath tương ứng với contract phát hành.

### 6.3. Multi-file compilation

Nhiều declaration có thể tham chiếu lẫn nhau. Compile từng file độc lập có thể bỏ sót lỗi package, visibility hoặc cyclic reference; cần compile nhóm file như consumer sẽ dùng.

### 6.4. Generic types

Kiểm tra generic parameter, bound, variance hoặc wildcard được sinh đúng. Lỗi generic đôi khi chỉ xuất hiện khi compiler type-check toàn bộ usage.

### 6.5. Nullability và optional values

Compile test có thể phát hiện type mismatch giữa nullable/non-null hoặc Optional wrapper. Tuy nhiên, nullability semantics cũng cần runtime test nếu target không kiểm tra đầy đủ.

### 6.6. Annotation processor và generated source tiếp theo

Nếu target build dùng annotation processor, test cần chạy đúng pipeline để phát hiện xung đột giữa generator của DSL và generator của compiler.

### 6.7. Compiler diagnostics

Khi compile thất bại, lưu diagnostic có source location và generated file path. Test harness nên hiển thị output compiler hữu ích nhưng không để log quá lớn.

### 6.8. Compile không phải bằng chứng runtime

Mã có thể compile nhưng dùng sai field, sai thứ tự gọi hoặc sai conversion. Compilation test là một tầng cần thiết, không thay thế behavioral test.

## 7. Runtime và behavioral tests

Runtime test xác minh generated artifact thực hiện đúng hành vi mà DSL mô tả.

### 7.1. Test qua public API

Khởi tạo generated class hoặc service qua API mà consumer thực tế sẽ dùng. Tránh test private implementation detail nếu contract không yêu cầu.

### 7.2. Input/output cases

Dùng input đại diện, giá trị biên, null, missing và dữ liệu sai. So sánh output với kết quả nghiệp vụ mong đợi.

### 7.3. Side effects

Nếu generated code ghi database, publish event hoặc gọi service, kiểm tra side effect trong môi trường test cô lập.

### 7.4. Error behavior

Xác minh exception, error code, validation result và fallback behavior. Mã sinh không nên âm thầm nuốt lỗi hoặc chuyển lỗi thành kết quả hợp lệ.

### 7.5. Resource lifecycle

Generated code có thể mở file, connection hoặc stream. Kiểm tra close/release khi thành công và khi có exception.

### 7.6. Concurrency

Nếu generated code được gọi đồng thời, kiểm tra race condition, shared mutable state và thread safety theo contract.

### 7.7. Serialization round-trip

Với DTO hoặc schema code, serialize rồi deserialize và so sánh giá trị. Kiểm tra nullability, enum, decimal và timestamp.

### 7.8. Integration runtime

Có thể chạy generated service với test database, in-memory broker hoặc fake HTTP server để xác minh tương tác thực tế.

## 8. Kiểm thử ánh xạ từ DSL sang mã đích

Một generator thường chuyển semantics DSL thành cấu trúc của target language. Cần kiểm tra mapping ở nhiều dạng input.

### 8.1. Type mapping

Tạo bảng mapping giữa DSL type và target type. Ví dụ DSL UUID có thể ánh xạ sang java.util.UUID; DSL Money có thể ánh xạ sang một domain class thay vì floating point.

### 8.2. Optional và nullable mapping

Xác định cách biểu diễn field tùy chọn, null và default. Test riêng các trạng thái để không nhầm missing với null.

### 8.3. Collection mapping

Kiểm tra list, set, map, element type và ordering. Nếu DSL không bảo đảm thứ tự map, generated output không nên dựa vào thứ tự ngẫu nhiên.

### 8.4. Enum mapping

Kiểm tra tên constant, serialization name và behavior với giá trị không biết. Enum mở rộng có thể cần unknown value strategy.

### 8.5. Date/time mapping

Kiểm tra LocalDate, LocalDateTime, Instant, timezone và precision. Chuyển đổi sai timezone có thể tạo bug dù source compile thành công.

### 8.6. Decimal và unit mapping

Số tiền, percentage, duration và size cần đơn vị rõ ràng. Không chuyển sang floating point nếu semantics cần decimal chính xác.

### 8.7. Reference mapping

Kiểm tra import, module reference và qualified name. Hai type trùng tên ở namespace khác nhau cần được phân giải đúng.

### 8.8. Unsupported type

Nếu DSL có type không được target hỗ trợ, generator nên phát diagnostic rõ hoặc dùng mapping được công bố. Không tạo output gần đúng một cách âm thầm.

## 9. Kiểm thử tên và identifier

Tên từ DSL có thể được chuyển thành class, method, field, package hoặc file name.

### 9.1. Naming convention

Kiểm tra PascalCase, camelCase, snake_case hoặc convention mà generator công bố.

### 9.2. Reserved words

Tên DSL có thể trùng keyword của target language. Generator cần escape, rename theo quy tắc hoặc từ chối với diagnostic.

### 9.3. Invalid characters

Identifier có thể chứa dấu cách, dấu gạch ngang, Unicode hoặc ký tự đặc biệt. Kiểm tra cách normalize và bảo toàn liên kết đến tên gốc.

### 9.4. Collision

Hai tên DSL khác nhau có thể normalize thành cùng identifier target. Generator phải phát hiện collision thay vì ghi đè file hoặc tạo class trùng.

### 9.5. Case sensitivity

Filesystem có thể không phân biệt chữ hoa/thường trong tên file, trong khi ngôn ngữ đích có thể phân biệt. Test cần bao phủ khác biệt nền tảng.

### 9.6. Unicode normalization

Hai identifier có thể nhìn giống nhau nhưng có biểu diễn Unicode khác. Chọn normalization policy và kiểm thử ký tự tương đương.

### 9.7. Stable naming

Tên generated output nên ổn định qua các lần chạy nếu input semantics không đổi. Không phụ thuộc thứ tự duyệt collection hoặc random suffix trừ khi đó là yêu cầu rõ.

## 10. Kiểm thử escaping và injection trong generated output

Generator thường đưa string từ DSL vào source code hoặc config. Đây là nơi dễ xảy ra lỗi quoting và injection.

### 10.1. String literal

Kiểm tra quote, backslash, newline, tab, Unicode và control character được escape đúng theo target language.

### 10.2. SQL generation

Nếu DSL sinh SQL, kiểm tra identifier quoting, parameter binding, literal encoding và dialect compatibility. Không ghép dữ liệu runtime trực tiếp vào SQL string.

### 10.3. HTML/JavaScript generation

Kiểm tra output encoding theo đúng ngữ cảnh HTML text, attribute, URL và script. Một chuỗi escape dùng cho HTML không tự an toàn khi đặt vào JavaScript.

### 10.4. Shell/config generation

Nếu generator tạo script hoặc command, dữ liệu phải được truyền qua argument structure hoặc escaping theo shell cụ thể. Tránh ghép input không tin cậy vào command string.

### 10.5. Path generation

Tên file và output path cần được kiểm tra để không thoát khỏi output root hoặc ghi đè file không thuộc generator.

### 10.6. Template delimiter

Nếu target output chứa ký hiệu trùng delimiter của template, cần kiểm tra escaping để generator không diễn giải nội dung dữ liệu thành template expression.

### 10.7. Security regression fixtures

Lưu các input có chuỗi đặc biệt và xác minh generated output không thực thi hoặc diễn giải chúng thành cú pháp điều khiển ngoài ý muốn.

## 11. Deterministic generation và reproducibility

Deterministic generator tạo cùng output khi nhận cùng input, cấu hình và toolchain version.

### 11.1. Stable ordering

Sắp xếp import, declaration, field và file output theo quy tắc xác định. Không dựa vào iteration order của unordered map.

### 11.2. Timestamp

Tránh chèn thời điểm hiện tại vào output nếu không cần. Nếu cần build timestamp, đưa clock vào dependency injection để test có thể cố định.

### 11.3. Random identifiers

Không tạo random identifier cho output ổn định trừ khi cần. Nếu cần ID, dùng seed hoặc input-derived identity theo contract.

### 11.4. Environment independence

Không để output thay đổi theo locale, timezone, absolute workspace path hoặc environment variable không được khai báo.

### 11.5. Toolchain version

Generator version, template version, target compiler version và dependency version có thể ảnh hưởng output. Reproducibility cần ghi nhận chúng.

### 11.6. Byte-for-byte stability

Với artifact có yêu cầu reproducible build, so sánh hash hoặc bytes. Với source text, có thể so nội dung chuẩn hóa theo line ending đã công bố.

### 11.7. Repeated generation

Chạy generator hai lần trên cùng input và kiểm tra output giống nhau, không tạo file trùng hoặc tích lũy nội dung.

### 11.8. Clean versus incremental generation

So sánh kết quả generate trên thư mục sạch với kết quả sau incremental update. Hai cách cần tạo cùng tập artifact cuối.

## 12. Kiểm thử source mapping và diagnostics

Generated code thường cần liên kết ngược về vị trí trong DSL để hỗ trợ debugging.

### 12.1. Source map

Source map hoặc mapping metadata liên kết generated line/column với DSL source span. Test cần xác minh mapping trỏ đúng declaration và expression.

### 12.2. Diagnostic mapping

Lỗi compile ở generated file có thể được chuyển thành diagnostic tại DSL source. Cần kiểm tra file, line, column và message được ánh xạ đúng.

### 12.3. Multiple source origins

Một generated method có thể được tạo từ nhiều declaration hoặc template. Mapping cần hỗ trợ nhiều origin hoặc xác định origin chính.

### 12.4. Generated line changes

Thay đổi formatting hoặc thêm import có thể dịch chuyển line. Mapping cần được tạo lại từ output mới, không reuse vị trí cũ.

### 12.5. Synthetic code

Một số code được generator tạo ra mà không có source tương ứng. Diagnostic cần đánh dấu generated/synthetic để IDE không dẫn người dùng đến vị trí giả.

### 12.6. Debug metadata

Nếu target hỗ trợ debug symbol, kiểm tra source file path và line mapping được đóng gói đúng. Tránh ghi absolute path nhạy cảm vào artifact phát hành.

## 13. Kiểm thử generated configuration và schema

Không phải generated artifact nào cũng là source code. File cấu hình và schema cũng cần được xác minh.

### 13.1. Parse output

Parse YAML, JSON, XML, SQL hoặc manifest bằng parser tương ứng. Test phát hiện syntax error và cấu trúc không hợp lệ.

### 13.2. Schema validation

Dùng schema hoặc validator của nền tảng đích để kiểm tra required field, type, enum và constraint.

### 13.3. Semantic validation

Một manifest có thể hợp lệ về schema nhưng tham chiếu resource không tồn tại hoặc chứa cấu hình mâu thuẫn. Cần semantic validation bổ sung.

### 13.4. Environment variants

Sinh output cho development, test, staging và production; xác minh mỗi profile có đúng endpoint, resource và policy.

### 13.5. Secret handling

Generated config không được chứa secret thật ngoài phạm vi được phép. Test có thể dùng canary value để tìm rò rỉ trong file, log và artifact.

### 13.6. Schema evolution

Kiểm tra generated schema tương thích với consumer cũ hoặc mới theo policy. Với database migration, kiểm tra thứ tự và tính an toàn của migration script.

### 13.7. Deployment validation

Dùng validator của nền tảng đích hoặc dry-run để kiểm tra manifest trước khi apply. Không coi parse thành công là bằng chứng deployment sẽ hoạt động.

## 14. Property-based testing cho generator

Property-based testing tạo nhiều input từ một mô hình và kiểm tra thuộc tính phải luôn đúng.

### 14.1. Input generator

Sinh DSL model có nhiều tổ hợp type, field, annotation, name và dependency. Generator dữ liệu test nên có seed để tái lập lỗi.

### 14.2. Property: parse generated output

Với mọi input hợp lệ trong domain test, generated source phải parse được bằng parser đích.

### 14.3. Property: compile

Với các fixture nhỏ, generated source phải compile thành công với target configuration đã chọn.

### 14.4. Property: round-trip

Nếu DSL hỗ trợ import/export hoặc serialize/deserialize, kiểm tra model sau round-trip tương đương model ban đầu theo semantics.

### 14.5. Property: stable generation

Cùng input và cấu hình phải tạo output giống nhau qua nhiều lần chạy.

### 14.6. Property: no name collision

Các declaration khác nhau trong miền hỗ trợ không được âm thầm tạo cùng target identifier hoặc ghi đè output.

### 14.7. Property: semantic invariant

Ví dụ, field nullable trong DSL không được sinh thành primitive non-null nếu điều đó làm mất khả năng biểu diễn null.

### 14.8. Shrinking

Khi property fail, framework có thể thu nhỏ input để tìm trường hợp tối thiểu. Lưu minimized fixture làm regression test.

### 14.9. Domain boundaries

Sinh cả input nhỏ, lớn, rỗng, nhiều field, nested type, generic và tên đặc biệt trong giới hạn DSL.

## 15. Differential và metamorphic testing

Khi không có expected output dễ viết, có thể kiểm tra quan hệ giữa các đường xử lý.

### 15.1. Differential testing

Chạy cùng model qua hai phiên bản generator hoặc hai backend độc lập rồi so sánh semantics. Khác biệt cần được giải thích, không phải mọi text diff đều là bug.

### 15.2. Reference implementation

Một implementation đơn giản hoặc interpreter có thể làm oracle cho generated code. Ví dụ tính kết quả rule bằng interpreter rồi so với kết quả của code được sinh.

### 15.3. Metamorphic testing

Biến đổi input theo cách có semantics đã biết rồi kiểm tra quan hệ output. Ví dụ thêm comment hoặc whitespace không nên làm thay đổi behavior của generated program.

### 15.4. Reordering invariant

Nếu DSL quy định thứ tự declaration không ảnh hưởng semantics, hoán đổi declaration phải giữ output behavior. Nếu thứ tự có ý nghĩa, test cần xác nhận semantics tương ứng.

### 15.5. Renaming transformation

Đổi tên symbol và cập nhật mọi reference nên chỉ đổi tên tương ứng trong generated output, không làm thay đổi hành vi khác.

### 15.6. Dead declaration

Thêm một declaration không được tham chiếu có thể không thay đổi runtime behavior, dù output file hoặc metadata có thể thay đổi theo contract.

### 15.7. Compare interpreter and generated backend

Nếu DSL có interpreter, cùng input nên tạo kết quả tương đương khi chạy qua interpreter và generated code. Đây là test mạnh để phát hiện sai lệch semantics giữa hai backend.

## 16. Kiểm thử tương thích và nhiều phiên bản target

Generator có thể hỗ trợ nhiều compiler, runtime hoặc platform version.

### 16.1. Target matrix

Xác định các phiên bản target được hỗ trợ và chạy compile/validation test trên từng phiên bản cần thiết.

### 16.2. Runtime compatibility

Generated code có thể compile nhưng gọi API runtime không tồn tại ở version cũ. Kiểm tra dependency và runtime API theo từng target.

### 16.3. Language feature compatibility

Generator cần biết target language version để chọn cú pháp tương ứng, chẳng hạn record, sealed type hoặc pattern matching.

### 16.4. Platform variants

Nếu sinh code cho Windows, Linux hoặc architecture khác nhau, kiểm tra path, line ending, native library và platform-specific API.

### 16.5. Backward compatibility

Generated public API có thể được consumer sử dụng. So sánh signature hoặc ABI giữa version generator để phát hiện breaking change.

### 16.6. Schema compatibility

Với generated API schema hoặc event schema, chạy compatibility checker giữa version trước và version mới.

### 16.7. Deprecation

Nếu generator thay đổi naming hoặc API, có thể sinh deprecation annotation hoặc compatibility adapter trong giai đoạn chuyển tiếp.

## 17. Kiểm thử lỗi và input không hợp lệ

Generator cần từ chối hoặc xử lý có kiểm soát các input sai.

### 17.1. Syntax error

Input DSL sai grammar phải tạo diagnostic rõ và không để generator tiếp tục với AST lỗi như thể hợp lệ.

### 17.2. Semantic error

Reference không tồn tại, type mismatch hoặc duplicate declaration cần được phát hiện trước code emission.

### 17.3. Unsupported construct

Nếu backend không hỗ trợ một feature, báo lỗi cụ thể kèm source location. Không sinh code gần đúng mà làm thay đổi semantics âm thầm.

### 17.4. Boundary values

Kiểm tra tên dài, số lượng field lớn, nesting sâu, empty collection, string chứa Unicode và giá trị numeric ở biên.

### 17.5. Error aggregation

Có thể thu thập nhiều diagnostic độc lập trong một lần chạy. Tuy nhiên, không nên tạo output phát hành nếu có error ngăn cản correctness.

### 17.6. No partial artifact

Nếu generation thất bại giữa chừng, không để một phần output mới bị coi là bản hoàn chỉnh. Dùng staging directory rồi commit output sau khi tất cả bước thành công.

### 17.7. Recovery

Sau failure, lần chạy tiếp theo cần dọn hoặc thay staging output đúng cách. Không để file thừa từ lần generate trước làm test pass giả.

## 18. Kiểm thử hiệu năng và quy mô

Generator có thể hoạt động tốt với fixture nhỏ nhưng chậm hoặc tiêu tốn bộ nhớ với project lớn.

### 18.1. Throughput

Đo số declaration, file hoặc node được sinh trên một đơn vị thời gian.

### 18.2. Latency

Đo thời gian từ khi nhận model đến khi output sẵn sàng, bao gồm parsing, transformation, formatting và I/O nếu thuộc phạm vi generator.

### 18.3. Memory profile

Theo dõi peak memory, AST retention, template context và output buffer. Tránh giữ toàn bộ output trong memory nếu có thể stream an toàn.

### 18.4. Large fixture

Tạo project có số module, field, rule và dependency gần với workload thực tế. Benchmark cần lặp lại và ghi nhận môi trường.

### 18.5. Incremental generation

Thay một declaration trong project lớn và đo số file được sinh lại. Kiểm tra output cuối vẫn giống full generation.

### 18.6. Parallel generation

Nếu generator sinh file song song, kiểm tra race condition, collision, deterministic ordering và giới hạn I/O.

### 18.7. Performance regression

Theo dõi benchmark qua các phiên bản. Một thay đổi nhỏ ở template engine hoặc AST traversal có thể làm chi phí tăng theo cấp số nhân.

## 19. Kiểm thử bảo mật của generated code

Generated code có thể tạo ra bề mặt tấn công trong ứng dụng tiêu thụ.

### 19.1. Injection resistance

Dùng fixture có quote, newline, comment marker, Unicode và chuỗi giống cú pháp điều khiển. Xác minh output giữ chúng ở dạng dữ liệu.

### 19.2. Unsafe API

Kiểm tra generator không tự tạo lệnh shell, deserialization nguy hiểm hoặc truy cập reflection không cần thiết từ input thông thường.

### 19.3. Path safety

Tên module và file từ DSL không được tạo output path vượt khỏi output root.

### 19.4. Secret leakage

Không sinh credential từ environment vào source hoặc manifest. Secret reference phải được giữ ở dạng tham chiếu theo contract.

### 19.5. Permission defaults

Generated deployment config nên chọn quyền tối thiểu theo policy và không tự mở endpoint, port hoặc role rộng hơn cần thiết.

### 19.6. Dependency safety

Generated source hoặc manifest không nên thêm dependency ngoài allowlist hoặc dùng version không được pin nếu policy yêu cầu.

### 19.7. Static analysis

Có thể chạy linter, SAST hoặc rule checker trên generated code. Kết quả cần phân biệt lỗi do generator với warning của target project.

### 19.8. Fuzzed source strings

Fuzz các field được đưa vào identifier, string literal, path và annotation để tìm lỗi escaping hoặc injection.

## 20. Kiểm thử formatter và output normalization

Formatting là một phần của contract nếu output được commit hoặc review.

### 20.1. Formatting rules

Kiểm tra indentation, line wrapping, blank lines, import order và newline cuối file theo convention đã chọn.

### 20.2. Formatter idempotency

Chạy formatter hai lần và xác minh lần thứ hai không làm thay đổi output. Đây là một property hữu ích cho formatting pipeline.

### 20.3. Formatter/compiler agreement

Formatter không được làm thay đổi semantics hoặc tạo source không còn parse được. Chạy parser/compiler sau formatting.

### 20.4. Line ending

Chuẩn hóa LF hoặc CRLF theo policy. Tránh golden test thất bại chỉ vì môi trường tạo line ending khác nếu line ending không thuộc semantics.

### 20.5. Encoding

Output thường cần UTF-8. Kiểm tra BOM, Unicode và ký tự không hợp lệ theo contract của target toolchain.

### 20.6. Whitespace significance

Không loại bỏ whitespace tùy tiện trong SQL, template hoặc language nơi whitespace có ý nghĩa. Normalization phải phù hợp với output format.

## 21. Kiểm thử nhiều file và atomic output

Generator thường tạo một tập file có quan hệ với nhau.

### 21.1. Output manifest

Có thể tạo manifest liệt kê file được sinh, loại artifact, hash và source origin. Test xác minh tập file đúng và không có file thừa.

### 21.2. Cross-file references

Kiểm tra class hoặc module được sinh có import/reference đúng file khác. Compile toàn bộ output để phát hiện lỗi liên kết.

### 21.3. Atomic generation

Sinh vào staging directory, validate output rồi thay thế output directory hiện hành. Điều này tránh consumer nhìn thấy tập file nửa cũ nửa mới.

### 21.4. Stale file cleanup

Khi declaration bị xóa, file generated tương ứng cần được loại bỏ theo ownership rule. Không xóa file người dùng tự quản lý.

### 21.5. Ownership marker

Generated file có thể chứa header hoặc metadata cho biết generator sở hữu file. Toolchain nên xác minh ownership trước khi ghi đè hoặc xóa.

### 21.6. Partial failure

Nếu generation một file thất bại, output cũ cần được giữ hoặc staging bị hủy. Test xác minh không có trạng thái hỗn hợp.

### 21.7. Concurrent invocation

Hai generator invocation cùng project có thể ghi đè nhau. Dùng lock hoặc output directory theo revision và atomic promotion.

## 22. Source fixtures và test data design

Chất lượng test phụ thuộc vào fixture đại diện và dễ hiểu.

### 22.1. Small focused fixture

Mỗi fixture nên tập trung vào một feature như nullable field, enum, generic, nested object hoặc annotation.

### 22.2. Realistic fixture

Bổ sung một số project gần thực tế để phát hiện tương tác giữa nhiều feature.

### 22.3. Edge-case fixture

Tạo fixture cho identifier đặc biệt, string escaping, duplicate name, empty model, nested type và version boundary.

### 22.4. Invalid fixture

Lưu input sai syntax, type mismatch, unresolved reference và unsupported construct để kiểm tra diagnostic.

### 22.5. Expected output organization

Tách expected output theo target hoặc backend. Không dùng một golden file chung nếu target language version tạo cú pháp khác nhau.

### 22.6. Fixture naming

Tên fixture nên nói rõ đặc tính kiểm tra, ví dụ generic-bound, nullable-collection hoặc escaped-string. Điều này giúp reviewer hiểu mục đích từ test report.

### 22.7. Test isolation

Mỗi test cần output directory riêng và dọn dữ liệu sau khi chạy. Không để output từ test trước làm test sau pass.

## 23. Test harness cho generator

Test harness giúp chạy cùng một chuỗi bước cho nhiều fixture.

### 23.1. Load DSL fixture

Đọc input và cấu hình target version từ fixture.

### 23.2. Parse và validate

Chạy parser và semantic analyzer; test có thể kiểm tra diagnostic trước khi gọi generator.

### 23.3. Generate output

Gọi generator với clock, ID provider, file system và configuration có thể kiểm soát trong test.

### 23.4. Inspect output

Liệt kê file, kiểm tra encoding, parse output hoặc so sánh golden.

### 23.5. Compile

Chạy target compiler trong process test riêng hoặc build fixture project.

### 23.6. Execute

Chạy test runtime trên generated classes hoặc artifact.

### 23.7. Compare result

So sánh expected output/behavior, diagnostic và metadata. Khi fail, report cần chỉ rõ fixture và generated file liên quan.

### 23.8. Capture diagnostics

Giữ stdout/stderr và compiler diagnostics có giới hạn. Không che mất nguyên nhân lỗi bằng cách chỉ báo “generation failed”.

### 23.9. Seed và reproducibility

Với property-based tests, lưu seed và minimized input để tái hiện failure.

## 24. Mutation testing cho generator tests

Mutation testing đánh giá liệu bộ test có phát hiện những lỗi có chủ ý trong generator hay không.

### 24.1. Mutation examples

Có thể thử thay đổi mapping type, bỏ annotation, đảo parameter order, bỏ escaping hoặc thay đổi null handling.

### 24.2. Test kill

Một mutant bị “kill” khi ít nhất một test thất bại vì phát hiện thay đổi. Mutant sống sót có thể chỉ ra thiếu assertion hoặc feature chưa được kiểm tra.

### 24.3. Mutation score

Mutation score là tỷ lệ mutant bị phát hiện trong tập mutant được xem xét. Đây là chỉ số tham khảo, không phải thước đo tuyệt đối chất lượng.

### 24.4. Equivalent mutant

Một mutation có thể không thay đổi behavior trong fixture hoặc toàn bộ miền hợp lệ. Cần phân biệt equivalent mutant với test yếu.

### 24.5. Focused mutations

Ưu tiên mutation tại mapping, escaping, branch selection và semantic transformation quan trọng. Không cần tạo mutation vô nghĩa chỉ để tăng số lượng.

## 25. CI pipeline cho kiểm thử mã sinh

CI nên chạy các tầng test theo chi phí và mức độ bảo vệ.

~~~mermaid
flowchart TD
    A[DSL and generator changes] --> B[Unit and structural tests]
    B --> C[Golden and snapshot tests]
    C --> D[Target compilation tests]
    D --> E[Runtime and contract tests]
    E --> F[Security and compatibility tests]
    F --> G[Performance suite]
    G --> H[Publish generator artifacts]
~~~

### 25.1. Fast feedback

Unit, structural và golden tests thường chạy sớm để phát hiện lỗi nhanh.

### 25.2. Compile matrix

Compile test chạy trên target versions và dependency sets được hỗ trợ.

### 25.3. Runtime integration

Runtime test có thể chạy trong container hoặc test service để kiểm tra contract.

### 25.4. Security scanning

Chạy static analysis, dependency scanning và injection fixtures trên generated output.

### 25.5. Performance suite

Benchmark nặng có thể chạy theo lịch hoặc khi thay đổi phần generator có ảnh hưởng lớn. Regression gate cần dựa trên ngưỡng ổn định.

### 25.6. Artifact retention

Giữ generated output và test report khi CI fail để reviewer có thể tải và kiểm tra. Cần tránh lưu secret hoặc dữ liệu thật.

### 25.7. Version matrix

Ghi rõ generator version, target compiler, runtime dependency và platform trong report để failure có thể tái hiện.

## 26. Ví dụ tổng hợp: test generator tạo Java model

Giả sử DSL khai báo:

~~~text
model Customer {
    id: UUID
    name: String
    nickname: String?
    tags: List<String>
}
~~~

Generator tạo Java class Customer.

### 26.1. Golden test

Expected output có thể chứa field, constructor, accessor và annotation theo convention của generator. Golden test xác minh output text.

### 26.2. Structural test

Parse Java output và kiểm tra class Customer có field id kiểu UUID, name kiểu String, nickname theo nullable mapping và tags là List<String>.

### 26.3. Compile test

Compile Customer.java cùng runtime dependency. Điều này xác minh import và type mapping thực tế.

### 26.4. Runtime test

Tạo object, gán nickname null, thêm tags và kiểm tra getter/serialization theo contract.

### 26.5. Escaping test

Dùng name có dấu nháy, newline và Unicode trong fixture dữ liệu để kiểm tra serializer hoặc generated literal nếu generator tạo constant.

### 26.6. Determinism test

Chạy generator hai lần trên cùng model và so sánh hash output. Không có timestamp hoặc random suffix không được kiểm soát.

### 26.7. Compatibility test

Compile output với từng Java target được hỗ trợ và kiểm tra generated API không thay đổi ngoài dự kiến giữa các phiên bản generator.

## 27. Ví dụ tổng hợp: test generator tạo SQL

Giả sử DSL mô tả một bảng:

~~~text
table Customer {
    id: UUID primary-key
    email: String unique
    createdAt: Instant required
}
~~~

### 27.1. SQL golden

So sánh câu CREATE TABLE với expected SQL theo dialect đã chọn.

### 27.2. Parser test

Parse SQL bằng parser của dialect để xác minh syntax.

### 27.3. Database integration

Chạy migration trên database tạm, kiểm tra schema được tạo đúng và constraint hoạt động.

### 27.4. Constraint behavior

Thử insert email trùng để xác minh unique constraint; thử bỏ createdAt để xác minh required constraint.

### 27.5. Identifier safety

Dùng tên field có keyword hoặc ký tự đặc biệt trong miền hỗ trợ và kiểm tra quoting đúng.

### 27.6. Migration ordering

Nếu generator tạo nhiều migration, kiểm tra thứ tự, dependency và khả năng apply trên schema trước đó.

### 27.7. Rollback behavior

Nếu hệ thống hỗ trợ rollback migration, kiểm tra script rollback trên database fixture và xác định dữ liệu nào có thể mất.

## 28. Những sai lầm thường gặp

### 28.1. Chỉ kiểm tra generator không ném exception

Generator có thể hoàn tất nhưng output sai. Cần kiểm tra nội dung, cấu trúc và behavior.

### 28.2. Chỉ dùng golden tests

Golden test không chứng minh code compile hoặc chạy đúng. Kết hợp structural, compilation và runtime tests.

### 28.3. Cập nhật snapshot tự động không review

Accept mọi snapshot mới có thể che regression. Review diff và chạy test ở tầng cao hơn.

### 28.4. Không test target compiler

Source có thể hợp lệ với version mới nhưng không tương thích target cũ mà DSL cam kết hỗ trợ.

### 28.5. Fixture chỉ có trường hợp đơn giản

Thiếu generic, nullability, Unicode, collision, nested type và boundary khiến nhiều bug không được phát hiện.

### 28.6. So sánh text quá cứng

Line ending hoặc import ordering có thể làm test nhiễu. Dùng structural test khi semantics quan trọng hơn formatting, nhưng vẫn giữ golden cho contract văn bản.

### 28.7. Normalization quá mạnh

Xóa mọi whitespace hoặc sắp xếp lại mọi field có thể che lỗi output. Chỉ normalize phần không thuộc semantics theo policy rõ.

### 28.8. Không kiểm tra output cũ

Generator có thể để lại file từ declaration đã xóa. Kiểm tra manifest và stale file cleanup.

### 28.9. Không test atomic generation

Failure giữa chừng có thể để output nửa mới nửa cũ. Dùng staging directory và kiểm tra behavior khi task fail.

### 28.10. Bỏ qua deterministic output

Output thay đổi ngẫu nhiên tạo diff lớn, cache miss và build khó tái lập. Cố định ordering, clock và identifier source.

### 28.11. Không test source mapping

Generated compile error có thể trỏ sai dòng DSL, làm trải nghiệm debugging kém. Kiểm tra mapping và diagnostic end-to-end.

### 28.12. Chỉ test output mà không test input invalid

Generator cần từ chối hoặc báo lỗi rõ với input sai, unsupported hoặc nguy hiểm.

### 28.13. Không kiểm tra injection

String được đưa vào SQL, shell, HTML hoặc source code có thể biến thành cú pháp điều khiển. Tạo security fixtures cho từng sink.

### 28.14. Test không cô lập

Output còn sót từ test trước hoặc environment máy developer có thể làm kết quả khác nhau. Dùng workspace riêng và dependency cố định.

## 29. Nguyên tắc thiết kế kiểm thử mã sinh

Một chiến lược kiểm thử generator tốt cần xác định contract và kiểm tra từ output nhỏ nhất đến hành vi tích hợp.

### 29.1. Kiểm tra nhiều tầng

Kết hợp golden, structural, compilation, runtime, property-based và integration tests. Mỗi tầng bắt một nhóm lỗi khác nhau.

### 29.2. Test theo contract DSL

Mỗi feature DSL như type, nullable, enum, generic, rule và annotation cần có fixture thể hiện output mong đợi.

### 29.3. Dùng target toolchain thật

Compile và validate bằng compiler/parser mà consumer thực tế sẽ dùng, với version và dependency được khóa.

### 29.4. Kiểm tra behavior

Với generated code có logic, kiểm tra hành vi qua public API và các trường hợp biên.

### 29.5. Bảo đảm deterministic output

Cùng input/configuration/toolchain tạo output ổn định. Kiểm soát clock, random, ordering và environment.

### 29.6. Kiểm tra security

Test escaping, path, injection, secret leakage, permission defaults và dependency policy.

### 29.7. Test failure và recovery

Xác minh input invalid, generator crash, partial output, cleanup và lần chạy lại sau failure.

### 29.8. Giữ fixture nhỏ, có mục đích

Mỗi fixture tập trung vào một behavior; thêm một số integration fixture thực tế để kiểm tra tương tác nhiều feature.

### 29.9. So sánh với oracle

Dùng interpreter, full compiler hoặc implementation tham chiếu để kiểm tra semantics của generated backend.

### 29.10. Đo hiệu năng

Benchmark project đại diện, số file lớn, incremental generation và memory usage. Theo dõi regression theo phiên bản.

### 29.11. Review snapshot có kiểm soát

Snapshot diff cần được review cùng lý do thay đổi, target compatibility và kết quả compile/runtime.

### 29.12. Lưu bằng chứng tái lập

Test report nên ghi input fixture, generator version, target version, dependency và seed để tái hiện lỗi.

## 30. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Generated Code | Mã nguồn hoặc artifact được tạo tự động từ DSL |
| Code Generator | Thành phần chuyển model hoặc AST thành output |
| Golden Test | Test so sánh output với file expected đã lưu |
| Snapshot Test | Test lưu và so sánh trạng thái output theo phiên bản |
| Structural Test | Test cấu trúc AST hoặc document tree thay vì chỉ so text |
| Compilation Test | Test biên dịch output bằng compiler đích |
| Runtime Test | Test hành vi của generated artifact khi thực thi |
| Property-based Test | Test nhiều input được sinh tự động dựa trên invariant |
| Differential Test | So sánh output hoặc behavior giữa các implementation |
| Metamorphic Test | Kiểm tra quan hệ kết quả khi input được biến đổi có kiểm soát |
| Fixture | Input và dữ liệu hỗ trợ được chuẩn bị cho test |
| Snapshot Update | Cập nhật expected output sau khi review thay đổi |
| AST | Cây cú pháp trừu tượng của source |
| Type Mapping | Quy tắc ánh xạ kiểu DSL sang kiểu target |
| Source Mapping | Liên kết vị trí generated output với source DSL |
| Deterministic Generation | Sinh cùng output với cùng input và cấu hình |
| Reproducible Build | Quá trình tạo artifact có thể tái hiện với input/toolchain cố định |
| Target Matrix | Tập phiên bản compiler/runtime/platform cần kiểm thử |
| Contract Test | Test xác minh producer/consumer hoặc generator tuân thủ hợp đồng |
| Mutation Testing | Đánh giá khả năng phát hiện lỗi bằng cách tạo thay đổi có chủ ý |
| Atomic Generation | Công bố output như một đơn vị hoàn chỉnh sau khi generation thành công |
| Stale Generated File | File cũ còn sót lại sau khi declaration nguồn đã bị xóa |
| Code Emission | Giai đoạn in hoặc ghi source/artifact từ model |
| Output Normalization | Chuẩn hóa phần output không thuộc semantics trước khi so sánh |
| Security Fixture | Input được thiết kế để kiểm tra injection, path hoặc rò rỉ dữ liệu |
| Test Harness | Hạ tầng chạy generator, kiểm tra output và thu thập kết quả |

Kiểm thử mã sinh cần xác minh toàn bộ đường đi từ DSL input đến artifact mà hệ thống đích sử dụng. Golden test giúp review output, structural test xác nhận cấu trúc, compilation test kiểm tra tính hợp lệ, runtime test xác minh hành vi và property/differential test mở rộng phạm vi trường hợp. Khi bổ sung deterministic generation, source mapping, compatibility matrix, security fixtures và kiểm tra atomic output, nhóm phát triển có thể thay đổi generator tự tin hơn mà vẫn giữ được contract và khả năng tái lập của các artifact được sinh.

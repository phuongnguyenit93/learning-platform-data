# Đánh dấu ngừng dùng

Trong quản lý phiên bản và di trú của ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), **đánh dấu ngừng dùng (deprecation marker)** là metadata hoặc cú pháp được gắn vào một thành phần để thông báo rằng thành phần đó vẫn còn được nhận diện trong một giai đoạn chuyển tiếp nhưng không còn được khuyến nghị sử dụng. Thành phần được đánh dấu có thể là keyword, directive, field, option, type, function, annotation, API, event, schema field hoặc một dạng cấu hình. Mục tiêu là cho người dùng biết lựa chọn hiện tại sẽ được thay thế, vì sao cần thay đổi, cách chuyển sang lựa chọn mới và mốc thời gian dự kiến loại bỏ.

Ví dụ, một DSL triển khai từng dùng option cũ:

~~~text
service billing {
    replicas = 2
    legacyHealthCheck = true
}
~~~

Ở phiên bản DSL mới, option legacyHealthCheck có thể được thay bằng healthProbe. Thay vì xóa ngay option cũ và khiến mọi project hiện tại lỗi, compiler có thể tiếp tục chấp nhận nó nhưng phát diagnostic deprecation, chỉ ra vị trí, giải thích lựa chọn thay thế và liên kết đến hướng dẫn di trú.

~~~text
service billing {
    replicas = 2
    healthProbe = {
        path = "/health"
        interval = 10 seconds
    }
}
~~~

Deprecation marker là một phần của contract tiến hóa DSL. Nó tạo ra khoảng thời gian để người dùng, nhóm phát triển và hệ thống tích hợp cập nhật dần. Một chính sách deprecation tốt cần nêu rõ phạm vi, lý do, replacement, phiên bản bắt đầu cảnh báo, phiên bản dự kiến loại bỏ, mức độ nghiêm trọng và cách tắt hoặc xử lý cảnh báo trong các trường hợp được cho phép. Nếu marker chỉ nói “đã lỗi thời” mà không chỉ ra cách chuyển đổi, nó không giúp giảm chi phí di trú.

## 1. Deprecation là gì?

Deprecation là trạng thái một tính năng vẫn tồn tại để tương thích trong một giai đoạn nhưng đã được công bố là không nên dùng cho phát triển mới. Nó báo hiệu hướng thay đổi của DSL mà không buộc tất cả consumer phải nâng cấp ngay lập tức.

### 1.1. Deprecated khác với removed

Deprecated nghĩa là tính năng vẫn được hỗ trợ theo policy hiện tại nhưng người dùng được khuyến nghị chuyển sang lựa chọn khác. Removed nghĩa là tính năng không còn được parser, compiler hoặc runtime chấp nhận. Hai trạng thái này cần được phân biệt trong tài liệu và diagnostic.

### 1.2. Deprecated khác với obsolete

Obsolete thường được dùng như từ đồng nghĩa trong tài liệu thông thường, nhưng một DSL có thể định nghĩa semantics riêng. Nếu có cả hai trạng thái, cần nêu rõ khác biệt về mức cảnh báo, hỗ trợ và thời điểm loại bỏ.

### 1.3. Deprecated khác với experimental

Experimental là tính năng đang thử nghiệm và có thể thay đổi. Deprecated là tính năng đã có người dùng nhưng đang được thay thế hoặc loại bỏ. Một tính năng experimental có thể chưa bao giờ trở thành stable; một tính năng deprecated thường cần kế hoạch chuyển tiếp cho consumer hiện tại.

### 1.4. Deprecation là một quá trình

Một vòng đời thường gồm stable, deprecated, sunset hoặc removal-planned, removed và có thể có trạng thái archived trong tài liệu. Các mốc phải gắn với phiên bản hoặc thời điểm có thể kiểm chứng.

### 1.5. Mục tiêu tương thích

Deprecation giúp giảm breaking change đột ngột, cho phép migration theo từng project và giúp nhóm phát triển đo mức độ sử dụng trước khi loại bỏ tính năng cũ.

## 2. Vì sao DSL cần deprecation markers?

DSL thường là contract được lưu trong repository, được tạo tự động hoặc được chia sẻ giữa nhiều nhóm. Một thay đổi cú pháp có thể ảnh hưởng hàng trăm project và pipeline.

### 2.1. Tiến hóa ngôn ngữ có kiểm soát

DSL cần sửa cú pháp khó hiểu, thay đổi semantics chưa hợp lý hoặc loại bỏ tính năng trùng lặp. Deprecation tạo giai đoạn chuyển tiếp trước khi thay đổi có hiệu lực.

### 2.2. Thay thế API hoặc cấu hình cũ

Một directive có thể được thay bằng cấu trúc rõ ràng hơn. Marker giúp người dùng biết cách chuyển và tránh tiếp tục tạo cấu hình mới dựa trên thiết kế cũ.

### 2.3. Sửa semantics nguy hiểm

Một option cũ có thể có default không an toàn hoặc hành vi mơ hồ. Deprecation cho phép khuyến nghị cách viết an toàn hơn trước khi buộc mọi consumer nâng cấp.

### 2.4. Chuẩn hóa cách khai báo

DSL có thể thay nhiều cách viết tương đương bằng một cú pháp chuẩn. Marker giúp thống nhất dần source mà không yêu cầu sửa toàn bộ project trong một lần.

### 2.5. Giảm chi phí hỗ trợ

Diagnostic có replacement và migration guide giúp người dùng tự sửa, giảm câu hỏi lặp lại và giảm lỗi do hiểu nhầm.

### 2.6. Quản lý dependency bên ngoài

DSL có thể wrapper một package, provider hoặc protocol sắp ngừng hỗ trợ. Deprecation marker cho biết cấu hình nào cần chuyển trước khi dependency bị loại bỏ.

### 2.7. Đo mức độ sẵn sàng loại bỏ

Compiler hoặc telemetry có thể đếm số lần marker được kích hoạt. Số liệu này hỗ trợ quyết định có nên chuyển sang removal ở major version tiếp theo hay cần kéo dài thời gian.

## 3. Những thành phần có thể được đánh dấu

Deprecation không chỉ áp dụng cho một keyword. Mọi phần tử có contract với người dùng đều có thể cần lifecycle.

| Thành phần | Ví dụ | Phạm vi tác động |
|---|---|---|
| Keyword | old-service | Cú pháp nguồn |
| Directive | legacyHealthCheck | Cấu hình |
| Field | retryCount | Schema/model |
| Option | enableCompatMode | Hành vi runtime |
| Type | OldIdentifier | Type system |
| Function | resolveLegacyName | Expression API |
| Annotation | @OldMapping | Metadata |
| Module/API | v1 adapter | Tích hợp |
| Event/schema field | customerName | Message contract |
| Plugin/provider | oldCloudProvider | Build/deploy |
| CLI flag | --legacy-mode | Developer tooling |
| Environment variable | OLD_ENDPOINT | Runtime configuration |
| Generated API | OldClient | Code generation |

### 3.1. Cú pháp nguồn

Keyword, directive hoặc shorthand cũ có thể tiếp tục parse nhưng phát warning tại source span tương ứng.

### 3.2. Schema field

Field cũ có thể được giữ để đọc file cấu hình trước đây. Parser có thể ánh xạ field cũ sang field mới trong compatibility layer.

### 3.3. Semantic API

Function hoặc type được gọi trong biểu thức có thể được đánh dấu để IDE và compiler thông báo replacement.

### 3.4. Generated API

Generator có thể tiếp tục tạo method cũ trong một thời gian nhưng gắn annotation deprecated của target language, đồng thời sinh method mới.

### 3.5. CLI và build options

Flag cũ có thể được chấp nhận trong một phiên bản để không phá script tự động. Tool nên chỉ ra flag thay thế và phiên bản dự kiến loại bỏ.

### 3.6. Integration contract

Event field, endpoint, plugin capability hoặc provider config có thể được đánh dấu để consumer biết thời hạn chuyển đổi.

## 4. Vòng đời của một thành phần

Một DSL nên định nghĩa lifecycle rõ ràng để người dùng hiểu trạng thái hiện tại và bước tiếp theo.

~~~mermaid
stateDiagram-v2
    [*] --> Experimental
    Experimental --> Stable: API được cam kết
    Stable --> Deprecated: Có replacement hoặc lý do loại bỏ
    Deprecated --> RemovalPlanned: Đã công bố mốc loại bỏ
    RemovalPlanned --> Removed: Đến phiên bản loại bỏ
    Removed --> [*]
~~~

### 4.1. Experimental

Tính năng đang được thử nghiệm, có thể thay đổi và chưa có cam kết tương thích dài hạn. Không nên dùng experimental làm trạng thái deprecation.

### 4.2. Stable

Tính năng được hỗ trợ theo compatibility policy. Thay đổi phá vỡ cần tuân thủ quy trình versioning.

### 4.3. Deprecated

Tính năng vẫn hoạt động trong phạm vi được công bố nhưng không còn được khuyến nghị. Diagnostic nên chỉ ra replacement hoặc lý do vì sao chưa có replacement.

### 4.4. Removal planned

Nhà phát triển đã công bố phiên bản hoặc thời điểm loại bỏ. Giai đoạn này giúp người dùng lập kế hoạch nâng cấp.

### 4.5. Removed

Parser hoặc runtime không còn chấp nhận tính năng. Nếu người dùng vẫn khai báo, tool nên phát lỗi có hướng dẫn nếu có thể nhận diện cú pháp cũ.

### 4.6. Archived

Một số hệ thống giữ tài liệu hoặc migration note của tính năng đã bị loại bỏ. Archived không có nghĩa runtime còn hỗ trợ.

### 4.7. Trạng thái có thể khác theo phiên bản

Một tính năng có thể stable trong DSL 2.x, deprecated từ 3.0 và removed trong 4.0. Metadata lifecycle cần gắn với version range, không chỉ một boolean deprecated.

## 5. Metadata của deprecation marker

Marker hữu ích cần chứa đủ thông tin cho compiler, IDE, tài liệu và công cụ migration.

Một metadata model có thể gồm:

- Element identity: tên, namespace và loại thành phần.
- Deprecated since: phiên bản bắt đầu đánh dấu.
- Removal target: phiên bản dự kiến hoặc mốc sunset.
- Message: lý do ngắn gọn.
- Replacement: phần tử thay thế.
- Migration guide: tài liệu hoặc hướng dẫn chuyển đổi.
- Severity: mức cảnh báo.
- Scope: source, schema, runtime, CLI hoặc generated API.
- Owner: nhóm chịu trách nhiệm.
- Compatibility behavior: cách xử lý trong thời gian chuyển tiếp.
- Exception policy: trường hợp được phép tiếp tục sử dụng.

### 5.1. Deprecated since

Phiên bản bắt đầu phát diagnostic cần được ghi rõ. Người dùng có thể xác định khi nào cảnh báo xuất hiện và tại sao project cũ chưa từng thấy nó.

### 5.2. Removal target

Mốc loại bỏ có thể là phiên bản cụ thể, ví dụ 5.0, hoặc một thời điểm sunset. Tránh ghi mốc không có cơ sở hoặc không được duy trì.

### 5.3. Replacement

Replacement nên chỉ ra identifier mới hoặc cấu trúc thay thế. Nếu cần nhiều bước, liên kết đến migration guide.

### 5.4. Reason

Lý do nên nói rõ vấn đề: cú pháp mơ hồ, API không an toàn, trùng chức năng, dependency hết hỗ trợ hoặc semantics không còn phù hợp.

### 5.5. Severity

Warning có thể là mức mặc định; một số tính năng có rủi ro cao có thể phát error trong strict mode hoặc ở phiên bản gần removal. Severity phải có semantics ổn định.

### 5.6. Owner

Owner giúp người dùng tìm đúng nhóm khi replacement chưa đáp ứng một trường hợp sử dụng đặc biệt.

## 6. Cú pháp khai báo marker trong DSL

Có nhiều cách biểu diễn deprecation metadata. Lựa chọn phụ thuộc vào DSL có annotation, schema metadata hay registry tập trung.

### 6.1. Annotation trên declaration

~~~text
@deprecated(
    since = "3.2",
    replacement = "healthProbe",
    message = "Dùng healthProbe để khai báo kiểm tra sức khỏe."
)
option legacyHealthCheck: Boolean
~~~

Annotation gắn marker trực tiếp với declaration và có thể được compiler đọc trong semantic model.

### 6.2. Metadata trong schema

~~~yaml
fields:
  legacyHealthCheck:
    type: boolean
    deprecated:
      since: "3.2"
      replacement: "healthProbe"
      message: "Use healthProbe instead."
~~~

Cách này phù hợp với DSL có schema ngoài source.

### 6.3. Registry trung tâm

Một registry có thể lưu deprecation metadata theo element ID. Cách này giúp quản lý nhiều phiên bản và nhiều target nhưng cần đồng bộ registry với compiler.

### 6.4. Directive cho version compatibility

~~~text
compatibility {
    acceptDeprecated = true
    warningsAsErrors = false
}
~~~

Directive này minh họa policy ở cấp project. Nó không nên xóa metadata hoặc làm biến mất deprecation khỏi report.

### 6.5. Marker trên generated API

~~~java
@Deprecated(since = "3.2", forRemoval = true)
public boolean legacyHealthCheck() {
    return healthProbeEnabled();
}
~~~

Generator có thể truyền deprecation metadata của DSL sang target language nếu semantics tương thích.

### 6.6. Syntax và metadata cần tách biệt

Cú pháp marker trong source là một cách biểu diễn. Metadata lifecycle có thể được lưu trong model trung gian để nhiều backend và tool dùng chung.

## 7. Diagnostic cho thành phần deprecated

Diagnostic là cách người dùng nhận biết việc đang sử dụng một thành phần đã được đánh dấu.

### 7.1. Source location

Diagnostic nên trỏ đến identifier hoặc toàn bộ declaration liên quan, không chỉ dòng đầu file.

### 7.2. Message có hành động

Thông báo tốt gồm tên phần tử, trạng thái, lý do, replacement và mốc loại bỏ nếu đã công bố.

Ví dụ:

~~~text
warning DSL-DP001:
  'legacyHealthCheck' is deprecated since DSL 3.2.
  Use 'healthProbe' instead.
  It is scheduled for removal in DSL 5.0.
  See migration guide: /migration/health-probe
~~~

### 7.3. Diagnostic code ổn định

Mã như DSL-DP001 giúp IDE, CI và suppression config tham chiếu mà không phụ thuộc câu chữ message.

### 7.4. Severity

Warning phù hợp trong giai đoạn chuyển tiếp. Strict mode có thể nâng warning thành error để ngăn source mới dùng API cũ.

### 7.5. Replacement hint

IDE có thể hiển thị quick fix hoặc code action. Hint nên được tạo từ migration rule đã xác minh, không suy đoán chỉ từ tên.

### 7.6. Diagnostic không lặp

Một declaration được tham chiếu ở nhiều nơi có thể tạo nhiều diagnostic. Tool nên chọn cách báo phù hợp: tại declaration, tại từng use site hoặc kết hợp cả hai với grouping.

### 7.7. Không che lỗi khác

Deprecation warning không nên làm mất syntax/type error thực sự. Diagnostic engine cần phân loại và sắp xếp để lỗi blocking dễ nhận biết.

## 8. Deprecation policy và severity

Policy xác định mức độ nghiêm trọng, thời gian chuyển tiếp và điều kiện sử dụng.

### 8.1. Warning mặc định

Khi thành phần lần đầu deprecated, compiler thường phát warning nhưng vẫn cho phép build. Điều này tạo cơ hội di trú mà không phá pipeline ngay.

### 8.2. Warning as error

Project có thể bật chế độ coi warning là error. Chế độ này hữu ích để ngăn thêm usage mới trong repository đã sẵn sàng chuyển đổi.

### 8.3. Strict mode

Strict mode có thể từ chối deprecated feature hoặc chỉ cho phép trong phạm vi compatibility được cấu hình. Cần phân biệt strict validation với việc tính năng đã bị remove toàn cục.

### 8.4. Security deprecation

Nếu một option có hành vi không an toàn, policy có thể rút ngắn thời gian chuyển tiếp hoặc phát error ngay ở môi trường production. Lý do và tác động cần được công bố.

### 8.5. No replacement

Không phải tính năng nào cũng có replacement. Diagnostic cần giải thích tính năng bị loại vì không còn cần thiết, không an toàn hoặc không có cách hỗ trợ tiếp.

### 8.6. Exception

Một số consumer có thể cần dùng tính năng cũ trong thời gian dài. Exception phải có phạm vi, owner, lý do và thời hạn; không nên tạo suppression vô thời hạn.

### 8.7. Policy nhất quán

Các module của cùng DSL nên dùng cách phân loại và mã diagnostic nhất quán để người dùng không phải học một quy tắc khác cho từng plugin.

## 9. Quy tắc thời gian chuyển tiếp

Thời gian từ deprecation đến removal cần đủ để người dùng nâng cấp và kiểm thử.

### 9.1. Theo semantic version

Một policy có thể đánh dấu trong minor release và loại bỏ ở major release tiếp theo. Tuy nhiên, DSL cần công bố compatibility policy cụ thể.

### 9.2. Theo ngày sunset

API hoặc dịch vụ tích hợp có thể dùng ngày sunset vì consumer không phải lúc nào cũng nâng cấp theo version compiler.

### 9.3. Theo mức sử dụng

Telemetry có thể cho biết mức độ sử dụng, nhưng dữ liệu cần được thu thập hợp pháp, minh bạch và không chứa nội dung nhạy cảm.

### 9.4. Không thay đổi mốc tùy tiện

Nếu removal target thay đổi, release note và migration guide cần cập nhật. Dời mốc liên tục làm người dùng mất niềm tin.

### 9.5. Consumer cũ và mới

Trong thời gian chuyển tiếp, producer và consumer có thể chạy version khác nhau. Compatibility layer cần hỗ trợ tổ hợp version được công bố.

### 9.6. Hỗ trợ LTS

Một số DSL có phiên bản hỗ trợ dài hạn. Tính năng deprecated có thể được giữ lâu hơn trong nhánh LTS, trong khi nhánh mới tiến tới removal.

### 9.7. End-of-support

Removal khỏi DSL và kết thúc hỗ trợ cho runtime/provider là hai mốc có thể khác nhau. Tài liệu cần nói rõ compiler còn nhận cú pháp nhưng service phía sau không còn được hỗ trợ hay không.

## 10. Replacement và migration guidance

Marker có giá trị nhất khi người dùng biết phải làm gì tiếp theo.

### 10.1. Replacement trực tiếp

Nếu oldOption được thay một-một bằng newOption, metadata có thể cung cấp replacement identifier và quick fix.

### 10.2. Replacement có cấu trúc

Một field boolean có thể được thay bằng object nhiều field. Migration cần chuyển semantics, không chỉ đổi tên.

### 10.3. Replacement phụ thuộc ngữ cảnh

Cùng một API cũ có thể được thay bằng hai API mới tùy cách sử dụng. Không thể cung cấp một quick fix duy nhất cho mọi trường hợp.

### 10.4. Migration guide

Guide nên mô tả lý do, trước/sau, thay đổi semantics, điều kiện cần, các trường hợp không tự động chuyển được và cách xác minh.

### 10.5. Migration example

~~~text
# Cú pháp cũ
service api {
    legacyHealthCheck = true
}

# Cú pháp mới
service api {
    healthProbe {
        path = "/health"
        interval = 10 seconds
    }
}
~~~

### 10.6. Behavior mapping

Nếu option cũ có default hoặc behavior khác option mới, migration phải nêu cách giữ nguyên behavior. Chỉ đổi cú pháp có thể làm thay đổi vận hành.

### 10.7. Manual steps

Một số migration cần tạo resource, thay credential, cập nhật endpoint hoặc điều chỉnh deployment. Guide phải đánh dấu các bước không thể tự động.

### 10.8. Verification

Sau migration, chạy parser, validator, tests và plan preview. Người dùng cần biết cách xác nhận cấu hình mới tương đương hoặc chấp nhận thay đổi có chủ đích.

## 11. Automatic migration và code actions

Công cụ có thể tự động sửa một số trường hợp đơn giản.

### 11.1. Quick fix

IDE có thể cung cấp action chuyển identifier cũ sang identifier mới khi mapping chắc chắn.

### 11.2. Rewrite rule

Migration tool có thể định nghĩa pattern cũ và replacement mới, kèm điều kiện áp dụng.

~~~text
rewrite {
    match: legacyHealthCheck == true
    replace: healthProbe.enabled = true
}
~~~

### 11.3. AST-based migration

Nên sửa AST hoặc syntax tree có source span thay vì dùng tìm/thay chuỗi toàn văn. Cách này giảm nguy cơ sửa comment, string literal hoặc identifier không liên quan.

### 11.4. Semantic migration

Nếu thay đổi cần hiểu type, scope hoặc context, migration tool nên dùng semantic model để xác định đúng target.

### 11.5. Idempotent migration

Chạy migration nhiều lần không nên tiếp tục làm source thay đổi. Tool cần nhận diện source đã được chuyển đổi.

### 11.6. Preview diff

Hiển thị diff trước khi ghi file. Người dùng có thể review các thay đổi và từ chối phần không phù hợp.

### 11.7. Backup và rollback

Migration tool nên hỗ trợ version control diff hoặc backup theo policy. Nếu migration tạo lỗi, người dùng cần phục hồi dễ dàng.

### 11.8. Partial migration

Tool có thể chuyển những trường hợp rõ ràng và báo các trường hợp cần thao tác thủ công. Không nên giả vờ migration hoàn tất nếu còn usage cũ chưa xử lý.

## 12. Deprecation trong parser và compiler

Compiler cần nhận diện thành phần deprecated ở đúng giai đoạn và tạo diagnostic mà không làm sai semantics trong giai đoạn chuyển tiếp.

### 12.1. Parser compatibility

Parser có thể tiếp tục chấp nhận cú pháp cũ. AST node có thể giữ source span và element identity để semantic analyzer phát warning.

### 12.2. Semantic resolution

Deprecation có thể chỉ được xác định sau khi resolve symbol. Một identifier có cùng tên nhưng thuộc namespace khác không nhất thiết là API deprecated.

### 12.3. Type checker

Type hoặc function deprecated có thể được đánh dấu trong symbol metadata. Khi expression tham chiếu nó, type checker hoặc diagnostic pass phát warning.

### 12.4. Lowering

Compiler có thể chuyển cú pháp cũ sang cùng IR với cú pháp mới. Điều này giúp giữ behavior trong thời gian chuyển tiếp.

### 12.5. Error recovery

Khi thành phần đã removed, parser có thể tạo diagnostic chuyên biệt nếu nhận diện được cú pháp cũ. Không nên âm thầm bỏ qua declaration.

### 12.6. Version gates

Parser hoặc semantic analyzer cần biết DSL language version. Cùng một token có thể hợp lệ ở version cũ, deprecated ở version giữa và lỗi ở version mới.

### 12.7. Compiler plugin

Plugin có thể cung cấp deprecation metadata cho declaration của nó. Compiler cần xác định plugin nào sở hữu element và cách hiển thị source location.

### 12.8. Generated code

Nếu DSL deprecated feature được lower sang code mới, compiler có thể phát warning ở DSL source mà không nhất thiết tạo warning ở generated source. Tránh nhân đôi diagnostic khó hiểu.

## 13. Deprecation và versioning của DSL

Deprecation phải gắn với chính sách versioning của ngôn ngữ và công cụ.

### 13.1. Language version

File DSL có thể khai báo version hoặc được project cấu hình version. Compiler dùng version này để quyết định feature nào stable, deprecated hoặc removed.

### 13.2. Compiler version

Compiler mới có thể hỗ trợ nhiều language version. Cần tách compiler implementation version khỏi DSL language version.

### 13.3. Semantic versioning

Nếu DSL tuân theo SemVer, việc đánh dấu deprecated thường có thể xuất hiện trong minor release; removal có thể là breaking change ở major release. Đây là policy cần được công bố, không phải quy luật tự động cho mọi DSL.

### 13.4. Compatibility mode

Compiler có thể cung cấp mode để đọc source cũ. Compatibility mode cần giới hạn rõ version range và không nên tồn tại vô thời hạn.

### 13.5. Version matrix

Tài liệu có thể thể hiện element được giới thiệu, deprecated và removed ở từng version. Matrix giúp người dùng xác định bước nâng cấp.

### 13.6. Version pinning

Project nên pin language version hoặc compiler toolchain để build không đổi behavior bất ngờ khi cài phiên bản mới.

### 13.7. Default language version

Nếu compiler tự chọn language version mới nhất, project cũ có thể gặp warning hoặc error mới. Việc nâng default cần có kế hoạch và thông báo.

## 14. Deprecation trong schema và configuration

DSL cấu hình thường có nhiều file được lưu lâu dài. Schema evolution cần hỗ trợ đọc cấu hình cũ và khuyến khích ghi cấu hình mới.

### 14.1. Deprecated field

Một field cũ có thể được nhận khi đọc nhưng không được sinh ra trong output mới. Parser phát warning và ánh xạ sang model mới.

### 14.2. Deprecated default

Một default cũ có thể được thay bằng default an toàn hơn. Thay đổi default có thể ảnh hưởng behavior ngay cả khi người dùng không khai báo field, vì vậy cần migration note.

### 14.3. Alias

Schema có thể hỗ trợ alias từ tên cũ sang tên mới. Alias cần có diagnostic để source không tiếp tục dùng tên cũ mãi.

### 14.4. Unknown fields

Khi field đã removed, nên phát error có hướng dẫn thay thế nếu compiler còn nhận diện được tên cũ. Không âm thầm bỏ qua field có thể ảnh hưởng semantics.

### 14.5. Configuration normalization

Sau khi đọc source cũ, model nội bộ có thể được chuẩn hóa về schema hiện tại. Cần giữ source provenance để diagnostic và formatter vẫn trỏ đúng chỗ.

### 14.6. Read compatibility và write compatibility

Một tool có thể đọc schema cũ nhưng chỉ ghi schema mới. Phân biệt hai khả năng này giúp migration tool hoạt động mà không tạo thêm cấu hình legacy.

### 14.7. Round-trip behavior

Nếu formatter đọc file cũ rồi ghi lại, cần quyết định có giữ cú pháp cũ hay chuyển sang cú pháp mới. Hành vi này phải được công bố và test.

## 15. Deprecation của API, plugin và generated code

DSL thường tạo ra hoặc gọi các API bên ngoài. Deprecation có thể truyền qua nhiều lớp.

### 15.1. API wrapper

Nếu DSL wrapper một API runtime đã deprecated, marker nên chỉ rõ cả DSL replacement và runtime dependency version cần có.

### 15.2. Plugin API

Plugin author có thể đánh dấu extension point cũ và cung cấp extension point mới. Host compiler cần hiển thị warning khi plugin hoặc project sử dụng extension cũ.

### 15.3. Generated API annotation

Generator có thể phát annotation tương ứng của target language, ví dụ Java Deprecated. Cần kiểm tra semantics annotation ở target version.

### 15.4. Compatibility adapter

Có thể giữ adapter hoặc forwarding method để code cũ tiếp tục hoạt động. Adapter nên có test bảo đảm behavior tương đương và có removal plan.

### 15.5. Dependency deprecation

Nếu package bị deprecated upstream, dependency analyzer có thể hiển thị warning trong build report. Cần phân biệt upstream deprecation với deprecation do DSL project tự đặt.

### 15.6. Binary compatibility

Xóa method hoặc class được generated code public hóa có thể phá binary consumer. Cần API/ABI compatibility test trước removal.

### 15.7. Plugin ecosystem

Trước khi loại extension point, cần thông báo cho plugin authors và có thể cung cấp compatibility shim hoặc migration window riêng.

## 16. Deprecation trong event và integration contract

Event schema và API contract thường có nhiều consumer triển khai độc lập.

### 16.1. Deprecated event field

Producer có thể tiếp tục phát field cũ trong giai đoạn chuyển tiếp, đồng thời phát field mới. Consumer mới chuyển sang field mới trước khi producer ngừng field cũ.

### 16.2. Deprecated event type

Một event type cũ có thể được thay bằng event mới có semantics rõ hơn. Cần mapping và thời gian song song để consumer di trú.

### 16.3. Schema registry

Registry có thể lưu deprecated metadata và enforce compatibility policy. Build pipeline có thể từ chối thêm consumer dependency mới vào field đã deprecated.

### 16.4. Consumer inventory

Cần biết consumer nào còn dùng field hoặc event cũ. Không nên xóa contract chỉ dựa trên việc producer không còn dùng nội bộ.

### 16.5. Dual publish

Trong một số migration, producer có thể publish event cũ và mới song song. Cần tránh consumer xử lý cả hai và tạo side effect trùng.

### 16.6. Sunset date

Webhook endpoint hoặc API version có thể công bố sunset date. Cần thông báo trước và cung cấp hướng dẫn chuyển sang endpoint mới.

### 16.7. Contract testing

Consumer-driven contract test giúp xác định consumer còn phụ thuộc field cũ trước khi removal.

## 17. Deprecation trong CLI và automation

CLI flags và environment variables thường nằm trong script CI/CD hoặc automation khó phát hiện bằng cách tìm source DSL đơn thuần.

### 17.1. Deprecated flag

CLI có thể tiếp tục nhận flag cũ và in warning đến stderr. Warning nên xuất hiện một lần theo command invocation hoặc được group để không gây nhiễu.

### 17.2. Replacement flag

Thông báo cần chỉ ra flag mới và cách giữ nguyên behavior. Nếu flag cũ có nhiều semantics, migration có thể cần sửa nhiều tham số.

### 17.3. Environment variable

Tên biến môi trường cũ có thể được hỗ trợ tạm thời. Nếu cả tên cũ và mới đều được đặt, cần quy định precedence và phát diagnostic.

### 17.4. Script compatibility

Automation có thể chạy ở môi trường không tương tác. Warning nên có mã ổn định và chế độ CI để nâng thành error khi nhóm đã sẵn sàng.

### 17.5. Machine-readable output

CLI có thể xuất deprecation findings dưới dạng JSON hoặc SARIF để CI tổng hợp và theo dõi theo repository.

### 17.6. Shell completion và help

Help và completion nên ưu tiên option mới, đánh dấu option cũ deprecated hoặc ẩn khỏi gợi ý thông thường nhưng vẫn nhận trong compatibility period.

## 18. Suppression và exception management

Đôi khi người dùng chưa thể di trú ngay. Suppression cho phép quản lý cảnh báo có kiểm soát.

### 18.1. Suppress theo element

Có thể suppress một diagnostic cụ thể tại declaration hoặc use site. Phạm vi cần nhỏ để không che warning khác.

### 18.2. Suppress theo file hoặc project

Project có thể có baseline cho legacy usage. Baseline nên có owner, lý do và thời hạn review.

### 18.3. Expiring suppression

Suppression có ngày hết hạn hoặc target version để không trở thành giải pháp vĩnh viễn.

### 18.4. Không suppress security-critical removal

Với tính năng nguy hiểm hoặc đã bị cấm, suppression không nên khôi phục khả năng thực thi trong production nếu policy không cho phép.

### 18.5. Suppression metadata

Lưu diagnostic code, scope, reason, owner và expiry. Không chỉ tắt warning mà không để lại dấu vết.

### 18.6. CI policy

CI có thể cho phép baseline hiện tại nhưng chặn số usage deprecated tăng thêm. Cách này giúp giảm nợ di trú theo từng pull request.

### 18.7. Review exception

Exception nên được xem xét lại khi nâng major version hoặc đến gần removal target.

## 19. Theo dõi mức sử dụng và mức độ di trú

Đội phát triển cần dữ liệu để biết deprecation có thể tiến tới removal hay chưa.

### 19.1. Static usage scan

Quét repository để tìm identifier, directive hoặc field deprecated. Static scan có thể phát hiện source usage nhưng có thể bỏ sót dynamic config.

### 19.2. Compiler diagnostics

Compiler report số lần từng diagnostic xuất hiện theo project hoặc build. Có thể dùng dữ liệu cục bộ trong CI mà không gửi source ra ngoài.

### 19.3. Runtime telemetry

Runtime có thể ghi nhận việc sử dụng API cũ nếu policy cho phép. Telemetry cần tôn trọng privacy, tenant isolation và data retention.

### 19.4. Consumer inventory

Với event/API contract, catalog có thể theo dõi consumer và version đang sử dụng. Đây là dữ liệu quan trọng trước khi ngừng endpoint hoặc field.

### 19.5. Migration progress

Dashboard có thể cho biết số project đã chuyển, số warning còn lại, exception đang mở và owner chịu trách nhiệm.

### 19.6. Không dựa vào số liệu thiếu

Không thấy usage trong telemetry không chứng minh không còn consumer. Cần kết hợp repository scan, contract registry, support channel và thông báo chính thức.

### 19.7. Removal readiness

Tiêu chí có thể gồm không còn internal usage, consumer quan trọng đã chuyển, replacement ổn định, migration tool sẵn sàng và support window đã kết thúc.

## 20. Quy trình deprecate một tính năng

Một quy trình có thể chuẩn hóa việc đưa marker, truyền thông và loại bỏ.

### 20.1. Xác định lý do

Ghi nhận vấn đề của tính năng cũ và lợi ích của replacement. Phân biệt cải tiến tiện ích với vấn đề bảo mật hoặc correctness khẩn cấp.

### 20.2. Thiết kế replacement

Đảm bảo replacement có semantics rõ, tài liệu và test. Tránh deprecate API cũ trước khi có con đường thay thế khả dụng nếu không có lý do cấp thiết.

### 20.3. Đánh giá tác động

Tìm internal usage, public consumer, plugin, generated code, example, tutorial và automation. Xác định phạm vi breaking change.

### 20.4. Thêm metadata và diagnostic

Đánh dấu declaration, cung cấp diagnostic code, message, replacement và version target. Test rằng warning xuất hiện đúng source span.

### 20.5. Cung cấp migration tool

Nếu có thể, tạo quick fix hoặc migration command. Với migration phức tạp, cung cấp hướng dẫn từng bước và ví dụ.

### 20.6. Công bố thay đổi

Release note, migration guide, API reference và deprecation catalog cần được cập nhật cùng release.

### 20.7. Theo dõi usage

Thu thập số liệu phù hợp và xử lý phản hồi từ consumer. Nếu replacement chưa đủ, điều chỉnh kế hoạch có công bố.

### 20.8. Xác nhận removal readiness

Kiểm tra compatibility, test, consumer inventory và support commitments trước khi xóa.

### 20.9. Remove và dọn adapter

Loại parser branch, compatibility shim, test fixture legacy và documentation cũ theo kế hoạch. Giữ migration note lịch sử.

## 21. Migration tool và codemod

Codemod là công cụ chuyển đổi source theo quy tắc có cấu trúc.

### 21.1. Pattern matching

Codemod nhận diện AST pattern cũ và thay bằng pattern mới. Pattern cần đủ cụ thể để tránh sửa nhầm.

### 21.2. Semantic rewrite

Nếu replacement phụ thuộc type hoặc symbol resolution, codemod cần semantic model chứ không chỉ parse syntax.

### 21.3. Batch migration

Có thể chạy trên toàn workspace hoặc repository. Tool cần báo số file đã sửa, số trường hợp bỏ qua và lý do.

### 21.4. Dry run

Dry run hiển thị diff mà không ghi file. Đây là bước hữu ích trước migration hàng loạt.

### 21.5. Partial success

Codemod có thể chuyển phần an toàn và để lại TODO cho trường hợp phức tạp. Report phải chỉ rõ phần chưa chuyển.

### 21.6. Idempotence

Chạy codemod lần thứ hai không nên thay đổi source đã được chuyển đổi.

### 21.7. Versioned rules

Migration rule nên gắn với source version và target version. Điều này giúp chuỗi migration nhiều major release có thể được áp dụng tuần tự.

### 21.8. Validation after rewrite

Sau codemod, parse, type-check và chạy tests trên source mới. Migration thành công về mặt text chưa bảo đảm semantics.

## 22. Tương thích ngược và compatibility layer

Compatibility layer giữ cho consumer cũ hoạt động trong giai đoạn chuyển tiếp.

### 22.1. Parser alias

Parser nhận tên cũ và ánh xạ sang model mới. Warning giúp người dùng biết alias sẽ không tồn tại mãi.

### 22.2. Forwarding API

Method cũ có thể gọi method mới. Cần kiểm tra tham số, default và exception semantics tương đương.

### 22.3. Adapter

Adapter chuyển object hoặc config cũ sang contract mới. Adapter nên được cô lập để dễ theo dõi usage và loại bỏ.

### 22.4. Dual read

Một service có thể đọc cả schema cũ và mới trong giai đoạn migration. Cần xác định precedence khi cả hai field cùng xuất hiện.

### 22.5. Dual write

Ghi cả field cũ và mới có thể hỗ trợ consumer chưa nâng cấp, nhưng có nguy cơ hai giá trị lệch nhau. Cần chọn một nguồn sự thật và quy tắc đồng bộ.

### 22.6. Compatibility cost

Mỗi adapter tăng code, test và bề mặt bảo trì. Cần có removal date để compatibility layer không tồn tại vô thời hạn.

### 22.7. Compatibility test matrix

Test các tổ hợp producer/consumer/compiler version được hỗ trợ. Không nên tuyên bố tương thích rộng hơn phạm vi đã kiểm chứng.

## 23. Tài liệu và truyền thông deprecation

Deprecation chỉ có hiệu quả nếu người dùng biết và hiểu cách hành động.

### 23.1. API reference

Trang API cần đánh dấu rõ trạng thái, phiên bản deprecated, replacement và removal target.

### 23.2. Migration guide

Guide nên có ví dụ trước/sau, thay đổi semantics, bước thủ công và cách kiểm thử sau chuyển đổi.

### 23.3. Release notes

Release note cần nêu phần tử nào mới deprecated, tại sao, ai bị ảnh hưởng và mốc dự kiến removal.

### 23.4. Deprecation catalog

Một catalog tập trung giúp tìm tất cả phần tử deprecated theo version, module, owner và replacement.

### 23.5. IDE support

Hover, completion, quick fix và diagnostic panel giúp cảnh báo xuất hiện ngay trong workflow của developer.

### 23.6. CI report

CI có thể tổng hợp warning theo repository và tạo issue hoặc report cho owner. Cần tránh tạo noise cho mỗi lần build.

### 23.7. Communication timeline

Với thay đổi lớn, thông báo trước trong roadmap hoặc release candidate để consumer có thời gian thử nghiệm.

## 24. Kiểm thử deprecation markers

Marker cũng là behavior của compiler và tooling, vì vậy cần được kiểm thử.

### 24.1. Diagnostic presence

Sử dụng element deprecated phải tạo diagnostic đúng code, severity và source span.

### 24.2. Non-deprecated usage

Element thay thế không được phát warning cũ. Test này tránh marker lan nhầm sang declaration khác.

### 24.3. Version boundary

Kiểm tra behavior ở version trước deprecation, version bắt đầu deprecated và version removal.

### 24.4. Replacement hint

Xác minh replacement identifier, guide link và migration hint chính xác.

### 24.5. Suppression scope

Kiểm tra suppression chỉ áp dụng cho diagnostic được chỉ định và hết hạn theo policy.

### 24.6. Strict mode

Kiểm tra warning được nâng thành error đúng khi bật strict policy, và compatibility mode hoạt động đúng phạm vi.

### 24.7. Migration tests

Chạy codemod trên fixture cũ, so sánh output mới, xác minh idempotence và parse/type-check sau chuyển đổi.

### 24.8. Compatibility tests

Kiểm tra source cũ vẫn hoạt động trong version được cam kết hỗ trợ và bị từ chối ở version đã remove.

### 24.9. Generated API tests

Xác minh annotation hoặc metadata deprecated được truyền sang generated code đúng target language.

### 24.10. Documentation consistency

Có thể kiểm tra catalog, release note và API metadata không mâu thuẫn về since, replacement và removal target.

## 25. Ví dụ tổng hợp: thay thế directive triển khai cũ

Giả sử DSL có directive timeout cũ:

~~~text
service reportApi {
    requestTimeout = 30 seconds
}
~~~

Thiết kế mới gom timeout theo từng operation:

~~~text
service reportApi {
    timeouts {
        request = 30 seconds
        connect = 5 seconds
        read = 20 seconds
    }
}
~~~

### 25.1. Đánh dấu directive cũ

~~~text
@deprecated(
    since = "2.6",
    replacement = "timeouts.request",
    removal = "4.0",
    message = "Dùng timeouts.request để phân biệt các loại timeout."
)
option requestTimeout: Duration
~~~

### 25.2. Giữ behavior trong compatibility layer

Trong DSL 2.6 và 3.x, compiler có thể chuyển requestTimeout sang timeouts.request nếu người dùng chưa khai báo giá trị mới.

### 25.3. Xử lý khi cả hai được khai báo

Nếu requestTimeout và timeouts.request cùng xuất hiện, compiler cần phát conflict diagnostic hoặc áp dụng precedence được công bố. Không nên âm thầm chọn một giá trị.

### 25.4. Migration command

Migration tool có thể chuyển directive cũ thành block mới và giữ nguyên duration. Nếu source có biểu thức động hoặc override theo environment, tool có thể yêu cầu review thủ công.

### 25.5. Kiểm tra tương đương

Chạy plan preview trước và sau migration để xác minh timeout hiệu lực giống nhau. Nếu semantics mới bổ sung connect/read timeout, chỉ request timeout được giữ nguyên và các giá trị mới cần được cấu hình theo nhu cầu.

### 25.6. Removal

Ở DSL 4.0, parser từ chối requestTimeout với diagnostic chỉ ra timeouts.request. Compatibility alias được xóa sau khi support window kết thúc.

## 26. Ví dụ tổng hợp: deprecate event schema field

Giả sử event CustomerRegistered từng có field name nhưng cần tách thành givenName và familyName.

~~~text
event CustomerRegistered version 1 {
    data {
        customerId: UUID
        name: String
    }
}
~~~

Schema mới:

~~~text
event CustomerRegistered version 2 {
    data {
        customerId: UUID
        givenName: String
        familyName: String
    }
}
~~~

### 26.1. Mark field cũ

Schema registry đánh dấu name deprecated và cung cấp replacement fields. Consumer có thể kiểm tra warning trong contract validation.

### 26.2. Dual representation

Trong thời gian chuyển tiếp, producer có thể phát cả name và hai field mới nếu mapping đủ rõ. Nếu không thể tách name một cách chắc chắn, cần policy dữ liệu thay vì tự đoán.

### 26.3. Consumer migration

Consumer chuyển sang givenName và familyName, sau đó cập nhật contract test để không còn phụ thuộc name.

### 26.4. Usage inventory

Registry hoặc consumer inventory xác định consumer còn đọc field cũ. Không remove chỉ vì producer đã ngừng dùng field nội bộ.

### 26.5. Removal

Khi consumer đã chuyển và support window kết thúc, schema version mới có thể loại name. Consumer dùng schema cũ vẫn cần được quản lý theo retention và compatibility policy.

## 27. Những sai lầm thường gặp

### 27.1. Đánh dấu nhưng không có replacement

Người dùng biết tính năng cũ không nên dùng nhưng không biết phải chuyển sang đâu. Nếu không có replacement, cần nói rõ lý do và lựa chọn thay thế ở cấp kiến trúc nếu có.

### 27.2. Không công bố removal target

Warning không có mốc khiến người dùng không biết phải ưu tiên migration khi nào. Nếu chưa xác định được version, hãy nói rõ mốc chưa được công bố.

### 27.3. Remove quá sớm

Consumer có thể chưa kịp nâng cấp, đặc biệt khi contract được dùng bởi nhiều tổ chức. Cần đánh giá dependency và support window.

### 27.4. Giữ deprecated vô thời hạn

Compatibility layer tăng chi phí và làm API phức tạp. Cần owner và tiêu chí removal.

### 27.5. Quick fix chỉ thay chuỗi

Text replacement có thể sửa nhầm comment, literal hoặc identifier khác. Dùng AST và semantic information.

### 27.6. Không giữ behavior

Replacement có thể có default hoặc semantics khác. Migration phải xác minh behavior, không chỉ làm source compile.

### 27.7. Warning quá nhiều

Phát warning ở mọi reference có thể gây noise. Grouping và severity phù hợp giúp người dùng tập trung vào hành động cần thiết.

### 27.8. Suppression không có hạn

Suppression vĩnh viễn che nợ kỹ thuật và khiến removal khó thực hiện. Dùng expiry, owner và review.

### 27.9. Không theo dõi consumer

Event field hoặc API có thể vẫn được consumer bên ngoài sử dụng dù repository nội bộ không còn reference. Cần catalog và consumer inventory.

### 27.10. Không test version boundary

Một tính năng có thể vô tình bị remove ở minor release hoặc vẫn được chấp nhận sau mốc removal. Test matrix phát hiện lỗi lifecycle.

### 27.11. Không cập nhật tài liệu

Compiler phát warning nhưng API reference vẫn nói tính năng được khuyến nghị. Tài liệu và metadata cần được phát hành đồng bộ.

### 27.12. Đổi nghĩa nhưng không đổi version

Giữ tên và type nhưng đổi semantics có thể khiến consumer không phát hiện. Thay đổi contract cần version hoặc element mới.

## 28. Nguyên tắc thiết kế deprecation cho DSL

Một chính sách deprecation tốt cần rõ ràng, có thể hành động và có thể kiểm chứng.

### 28.1. Marker có metadata đầy đủ

Ghi deprecated since, lý do, replacement, removal target, owner và migration guide.

### 28.2. Tách deprecated khỏi removed

Giữ semantics riêng cho giai đoạn chuyển tiếp và giai đoạn không còn hỗ trợ. Version gate phải được kiểm thử.

### 28.3. Diagnostic hữu ích

Cung cấp source span, diagnostic code ổn định, severity và hành động tiếp theo. Tránh warning chỉ nói “deprecated”.

### 28.4. Replacement sẵn sàng

Đảm bảo lựa chọn thay thế có contract và tài liệu trước khi yêu cầu consumer chuyển đổi, trừ trường hợp bảo mật cần xử lý khẩn cấp.

### 28.5. Migration có kiểm soát

Dùng AST rewrite, semantic migration, preview diff, idempotence và validation sau chuyển đổi.

### 28.6. Compatibility có thời hạn

Adapter, alias và dual-read/write cần owner, phạm vi version và removal plan.

### 28.7. Quản lý consumer

Theo dõi usage trong source, plugin, API, event và automation. Không coi thiếu telemetry là bằng chứng không còn consumer.

### 28.8. Policy suppression

Cho phép exception có lý do, owner và expiry. Không để suppression che security-critical removal.

### 28.9. Đồng bộ công cụ và tài liệu

Compiler, IDE, CLI, schema registry, migration tool và API docs cần dùng cùng metadata để tránh thông tin mâu thuẫn.

### 28.10. Test lifecycle

Kiểm thử stable/deprecated/removed ở các version boundary, compatibility mode, warning-as-error và migration output.

### 28.11. Công bố thay đổi

Thông báo trong release notes, migration guide và deprecation catalog đủ sớm để consumer lập kế hoạch.

### 28.12. Loại bỏ có trách nhiệm

Chỉ remove sau khi replacement ổn định, support window kết thúc, consumer quan trọng đã chuyển và compatibility policy được tuân thủ.

## 29. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Deprecation | Trạng thái không còn khuyến nghị dùng nhưng còn được hỗ trợ trong giai đoạn chuyển tiếp |
| Deprecation Marker | Metadata hoặc annotation đánh dấu thành phần deprecated |
| Deprecated Since | Phiên bản bắt đầu đánh dấu ngừng dùng |
| Removal Target | Phiên bản hoặc thời điểm dự kiến loại bỏ |
| Replacement | Thành phần hoặc cú pháp được khuyến nghị thay thế |
| Sunset Date | Ngày kết thúc hỗ trợ của API hoặc integration |
| Compatibility Layer | Lớp chuyển đổi để giữ consumer cũ hoạt động |
| Migration Guide | Tài liệu hướng dẫn chuyển sang cách dùng mới |
| Codemod | Công cụ tự động sửa source theo quy tắc có cấu trúc |
| Quick Fix | Hành động sửa nhanh được IDE cung cấp |
| AST Rewrite | Chuyển đổi source thông qua cây cú pháp |
| Warning as Error | Chính sách nâng warning thành lỗi |
| Strict Mode | Chế độ áp dụng policy nghiêm ngặt với deprecated usage |
| Suppression | Cơ chế ẩn hoặc miễn một diagnostic trong phạm vi xác định |
| Deprecation Catalog | Danh mục tập trung các thành phần deprecated |
| Consumer Inventory | Danh sách hệ thống hoặc project đang dùng contract |
| Schema Evolution | Quá trình thay đổi schema theo thời gian |
| Backward Compatibility | Consumer mới vẫn đọc hoặc dùng được contract cũ |
| Forward Compatibility | Consumer cũ vẫn xử lý được contract mới trong phạm vi hỗ trợ |
| Dual Read | Đọc đồng thời schema hoặc field cũ và mới |
| Dual Write | Ghi cả representation cũ và mới trong giai đoạn chuyển tiếp |
| Semantic Versioning | Quy ước version biểu thị mức độ thay đổi tương thích |
| Version Gate | Quy tắc bật/tắt feature theo language hoặc tool version |
| Removal | Giai đoạn tính năng không còn được chấp nhận |
| Experimental | Tính năng thử nghiệm chưa có cam kết ổn định |
| API/ABI Compatibility | Mức tương thích ở giao diện nguồn hoặc nhị phân |
| Migration Verification | Kiểm tra source và behavior sau khi chuyển đổi |

Đánh dấu ngừng dùng giúp DSL tiến hóa mà vẫn cho người dùng thời gian chuyển đổi. Một marker có giá trị cần xác định chính xác phần tử, phiên bản bắt đầu, lý do, replacement và mốc loại bỏ; compiler và IDE cần phát diagnostic có vị trí cùng hướng dẫn hành động. Khi kết hợp compatibility layer có thời hạn, migration tool dựa trên AST, consumer inventory, version-boundary tests và tài liệu đồng bộ, nhóm phát triển có thể loại bỏ cú pháp hoặc API cũ một cách dự đoán được mà giảm nguy cơ phá vỡ project đang vận hành.

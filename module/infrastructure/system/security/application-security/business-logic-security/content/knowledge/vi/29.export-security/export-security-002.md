# Export field allowlist: danh sách field được phép xuất dữ liệu

## 1. Quyền xem danh sách không tự cho phép xuất mọi thuộc tính

Một API danh sách chỉ trả mã hồ sơ, số tiền và trạng thái. Chức năng export lại dùng reflection để ghi mọi thuộc tính của entity ra file. Kết quả có thêm email, tài khoản người nhận, ghi chú nội bộ hoặc quan hệ role mà giao diện chưa từng công bố.

Một phiên bản khác xóa các cột nhạy cảm khỏi sheet đang hiển thị nhưng vẫn giữ chúng trong sheet ẩn hoặc metadata của template. Người dùng không nhìn thấy ngay không có nghĩa dữ liệu đã được loại khỏi artifact.

**Export field allowlist** là danh mục những field và cách biểu diễn mà server cho phép đưa vào một loại export trong một ngữ cảnh có thẩm quyền cụ thể.

Mục tiêu là để dữ liệu không được cấp phép không đi vào file hoặc các bề mặt liên quan, thay vì xuất rộng rồi cố che ở cuối.

Trong bảo vệ logic nghiệp vụ, export thường gom nhiều dữ liệu thành một artifact dễ lưu và chuyển tiếp. Vì vậy, ranh giới cần bao phủ cả row scope, field, quyền tạo job, quyền xử lý và quyền nhận kết quả.

## 2. Allowlist field nằm trong một chính sách nhiều chiều

### 2.1. Một field có thể được phép ở ngữ cảnh này nhưng không ở ngữ cảnh khác

Những yếu tố có thể ảnh hưởng gồm:

- Loại báo cáo/export và mục đích nghiệp vụ được hệ thống chấp nhận.
- Tenant, actor và phạm vi đối tượng được phép đọc/xuất.
- Field, representation và điều kiện theo từng dòng.
- Định dạng và template/renderer được hỗ trợ.
- Thời điểm tạo, thực thi và tải artifact theo hợp đồng.

Một giá trị `purpose = audit` do client tự gửi không tự tạo quyền kiểm toán. Nó chỉ là đầu vào cần được kiểm tra trong policy nếu sản phẩm hỗ trợ mục đích đó.

### 2.2. Tách quyền row, field và action export

| Lớp kiểm soát | Câu hỏi |
|---|---|
| Quyền yêu cầu export | Actor có được tạo loại công việc này không? |
| Row scope | Những hồ sơ nào được đưa vào? |
| Field/representation | Mỗi dòng được xuất những giá trị nào, ở mức chi tiết nào? |
| Quyền xử lý | Worker được thực hiện kế hoạch nào và theo căn cứ nào? |
| Quyền nhận kết quả | Ai được xem status, metadata và tải file? |

Có field đúng nhưng row sai vẫn rò rỉ. Row đúng nhưng cột tài khoản ngân hàng không được phép vẫn rò rỉ. Biết job ID cũng không tự tạo quyền tải.

### 2.3. Không dùng nhãn admin như một allowlist vô hạn

Tenant admin có thể không được đọc mọi dữ liệu cá nhân hoặc dữ liệu nền tảng. Nhân viên hỗ trợ có thể xem trạng thái nhưng không được export chi tiết tài chính.

Định nghĩa quyền theo khả năng và scope thực sự. Các bí mật như credential, token phiên, mã khôi phục hay dữ liệu xác thực không nên xuất hiện trong cơ chế export báo cáo tổng quát chỉ vì actor có một role rộng.

## 3. Thiết kế field catalog tường minh

### 3.1. Public field ID khác tên cột hoặc property path

Một catalog minh họa cho báo cáo chi phí:

| Field ID công khai | Giá trị xuất | Điều kiện đáng chú ý |
|---|---|---|
| `reference` | Mã hồ sơ | Trong row scope được phép |
| `submittedAt` | Thời điểm gửi theo hợp đồng | Format/time zone rõ |
| `amount` | Số tiền theo căn cứ báo cáo | Có loại tiền/đơn vị đi kèm phù hợp |
| `currency` | Loại tiền | Không ngầm gộp các loại tiền khác nhau |
| `state` | Trạng thái nghiệp vụ được chọn | Nêu rõ snapshot/độ mới |
| `requesterDisplayName` | Tên hiển thị được phép | Không serialize cả object requester |
| `requesterEmail` | Email | Cần quyền và điều kiện row tương ứng |
| `payeeAccountLast4` | Biểu diễn đã hạn chế | Không tương đương quyền xuất tài khoản đầy đủ |

Catalog thật chỉ nên có những khả năng sản phẩm chủ ý hỗ trợ. Không cho client gửi SQL expression, tên cột DB, JSON path hoặc tên getter tùy ý.

### 3.2. Mỗi field cần định nghĩa nguồn và renderer

Một field definition có thể mô tả:

```text
fieldId ổn định
nhãn hiển thị theo locale được hỗ trợ
loại dữ liệu và ngữ nghĩa
nguồn/projection do server quản lý
representation được hỗ trợ
điều kiện permission và row
phụ thuộc field khác nếu có
format/renderer version
```

Một field tổng tiền có thể cần currency. Một field tên người không được trả cả entity chứa email/role qua `toString` hoặc JSON fallback.

Các phụ thuộc cần được giải quyết trong kế hoạch có kiểm tra quyền; không tự thêm một cột riêng tư chỉ để renderer chạy được.

### 3.3. Field mới trong domain không tự được xuất

Không lấy `entity.getProperties()`, `SELECT *` hoặc toàn bộ enum để tạo danh sách mặc định. Khi domain có thêm thuộc tính bảo mật, export cũ phải tiếp tục không xuất nó nếu chưa có quyết định mở khả năng đó.

Allowlist giúp mặc định từ chối field mới. Denylist như “xuất mọi thứ trừ password và bankAccount” dễ bỏ sót thuộc tính nhạy cảm mới hoặc một đường nested khác.

### 3.4. Masking là một representation có policy

`payeeAccountLast4` nên được xem như một field/representation xác định, không phải `bankAccountNumber` cộng cờ `mask=false` mà client có thể đổi.

Hash, token hóa hoặc che một phần không tự làm dữ liệu thành công khai. Vẫn cần xem thông tin còn lại cho phép liên kết hoặc suy ra gì, và ai được nhận representation đó.

## 4. Hợp đồng request và lựa chọn field

### 4.1. Ví dụ yêu cầu export

```http
POST /tenants/{tenantId}/expense-exports
Content-Type: application/json
Idempotency-Key: client-export-request-key

{
  "exportType": "EXPENSE_SUMMARY",
  "fields": ["reference", "amount", "currency", "state"],
  "filters": {
    "states": ["SUBMITTED", "APPROVED"]
  },
  "format": "CSV"
}
```

Tenant mục tiêu được xác minh với actor. Filter chỉ thu hẹp row scope, không cấp quyền xem toàn bộ tenant. Field và format chỉ là lựa chọn được đề nghị, phải được server xét.

### 4.2. Quy tắc đầu vào cần rõ

Một hợp đồng có thể chọn:

1. Nếu vắng `fields`, dùng tập mặc định tối thiểu đã được định nghĩa rõ cho export type.
2. Nếu có `fields`, danh sách phải không rỗng, nằm trong giới hạn số phần tử và dùng ID được hỗ trợ.
3. Field lặp hoặc không dùng được trong ngữ cảnh bị từ chối theo hợp đồng.
4. Không có wildcard `*`, field path tùy ý hoặc cờ bypass nhạy cảm.
5. Thứ tự field là thứ tự cột được yêu cầu nếu sản phẩm hỗ trợ lựa chọn đó.

Đây là chính sách mẫu. Nếu một dự án bỏ qua field không hỗ trợ, phải nói rõ field hiệu lực và không tạo file trông như đã đáp ứng đầy đủ yêu cầu. Không âm thầm xuất toàn bộ khi input rỗng hoặc lỗi parse.

### 4.3. Đừng công bố field bí mật qua lỗi

Có thể dùng mã như `FIELD_NOT_EXPORTABLE` cho field không được chấp nhận trong ngữ cảnh, theo cách tiết lộ được phép. Không cần trả schema DB hoặc toàn bộ catalog đặc quyền của hệ thống.

Danh sách field khả dụng nếu có endpoint khám phá cũng phải được lọc theo loại export và policy phù hợp. Biết field ID không tạo quyền sử dụng.

### 4.4. Quyền field theo từng dòng

Một actor có thể được xuất email của mình nhưng không phải email mọi thành viên. Không lấy việc actor được phép field trên một dòng làm quyền cho tất cả dòng.

Có thể chọn chỉ chấp nhận field nếu nó có representation được phép cho toàn row scope, hoặc dùng policy theo từng dòng với mask/omission được mô tả rõ. Cần biết các giá trị trống là không có dữ liệu, bị hạn chế hay lỗi; không làm báo cáo gây hiểu sai.

Ví dụ chính dưới đây chọn kiểm tra representation hợp lệ cho scope dự kiến. Các trường hợp phụ thuộc từng dòng cần một kế hoạch và writer thực thi điều kiện tương ứng.

## 5. Minh họa Java: resolve field plan phía server

Các dependency sau là hợp đồng của ứng dụng. Kế hoạch được xây phía server, không deserialize từ một object client đặt tên là “approved plan”.

```java
ResolvedExportPlan resolvePlan(
        ActorContext actor,
        ExportRequestInput input) {

    ValidatedExportRequest request = inputRules.validateAndBound(input);
    ExportDefinition definition = catalog.requireExportType(
            request.exportType());

    exportPolicy.requireCanRequest(actor, definition);
    ExportRowScope rowScope = rowScopes.requireAllowedScope(
            actor, definition, request.filters());

    List<String> requestedIds = request.hasFieldSelection()
            ? request.fieldIds()
            : definition.explicitDefaultFieldIds();

    Set<String> seen = new HashSet<>();
    List<ResolvedColumn> columns = new ArrayList<>();

    for (String fieldId : requestedIds) {
        if (!seen.add(fieldId)) {
            throw new ExportInputException("DUPLICATE_EXPORT_FIELD");
        }

        FieldDefinition field = definition.requirePublicField(fieldId);
        ColumnGrant grant = fieldPolicy.requireExportableForScope(
                actor, field, rowScope);

        columns.add(columnCompiler.compile(field, grant));
    }

    return plans.freeze(
            actor.tenantId(), actor.principalId(),
            definition.version(), rowScope, columns, request.format());
}
```

Các hợp đồng quan trọng:

- Độ dài field ID, số field, cấu trúc filter và format được giới hạn trước công việc đắt.
- `explicitDefaultFieldIds` là danh sách có chủ ý, không phải mọi property/enum mới có trong code.
- `requirePublicField` ánh xạ ID sang definition tĩnh/có quản trị; không reflection từ chuỗi client.
- `requireExportableForScope` xét field và representation trong row scope thực sự, không chỉ role chung.
- `compile` chọn extractor/renderer được server hỗ trợ và không giữ một đường đọc raw field tùy ý.
- Kế hoạch cố định thứ tự cột, representation và phiên bản định nghĩa để tránh template thay đổi tự mở thêm field.
- Việc resolve không tự bảo đảm quyền còn nguyên lúc job chạy hoặc file được tải; cần vòng đời kiểm tra ở các phần sau.

Nếu không đủ căn cứ để xác lập một field grant bắt buộc, không dùng một grant rỗng như nghĩa “không hạn chế”. Từ chối hoặc báo lỗi phù hợp theo nguyên nhân.

## 6. Projection và writer phải thực thi cùng allowlist

### 6.1. Không xuất toàn bộ rồi xóa cột cấm

Luồng dễ sai:

```text
nạp toàn bộ entity/graph
→ chuyển mọi property sang map hoặc workbook
→ xóa một vài cột trên sheet chính
→ trả artifact
```

Dữ liệu có thể còn ở các field nested, sheet ẩn, metadata, log hoặc một renderer khác. Danh sách cấm cũng dễ trôi khi model thay đổi.

Hướng rõ hơn là query/projection cần thiết cho plan, rồi writer chỉ ghi đúng cột đã resolve.

### 6.2. Minh họa writer giới hạn cột

```java
for (ExportRow row : source.readAuthorizedChunks(plan)) {
    List<ExportCell> cells = new ArrayList<>(plan.columns().size());

    for (ResolvedColumn column : plan.columns()) {
        cells.add(column.extractPermittedValue(row));
    }

    writer.writeRow(cells);
}
```

Đoạn mã chỉ thể hiện hợp đồng. `readAuthorizedChunks` phải thực sự giữ row scope; `extractPermittedValue` phải dùng renderer và điều kiện đã được cấp, không fallback serialize cả object khi gặp kiểu lạ.

Không thêm `map.putAll(entity)` sau vòng lặp, hoặc cho một hook/template bổ sung property ngoài plan.

### 6.3. Giảm dữ liệu lấy từ nguồn khi có thể

Chỉ lấy những dữ kiện cần thiết để tạo các representation được phép. Nếu phải đọc dữ liệu gốc để biến đổi có thẩm quyền, giới hạn nó trong đường xử lý phù hợp, không đưa vào row debug, log hay artifact phụ.

Một field hiển thị tên không cần tải và serialize toàn bộ quan hệ tài khoản. Một representation hạn chế không tự cho mọi downstream truy cập source đầy đủ.

### 6.4. Sort, filter và aggregate cũng có quyền riêng

Không xuất cột nhạy cảm nhưng cho người gọi lọc, sort hoặc group theo mọi giá trị của nó có thể tạo kênh suy đoán qua các dòng/số lượng được trả.

Allowlist field đầu ra cần đi cùng tiêu chí query được phép. Row scope phải áp dụng trước count/tổng hợp và không bị filter client ghi đè.

Với field tổng hợp, chỉ dùng tập dữ liệu được phép và công thức đúng domain. Không tạo một cột tưởng như vô hại nhưng bao gồm giá trị của những dòng bí mật.

## 7. Định dạng có những bề mặt rò rỉ khác nhau

### 7.1. CSV và dữ liệu dạng bảng tính

Allowlist quyết định field nào được xuất, không tự làm nội dung cell an toàn khi mở bằng một ứng dụng bảng tính.

Một giá trị text có thể bị consumer diễn giải thành công thức theo hành vi của nó. Quote đúng cú pháp CSV không tự biến mọi chuỗi thành text vô hại trong bảng tính.

Cần chính sách serialization theo consumer/hợp đồng, như biểu diễn cell text rõ khi định dạng hỗ trợ hoặc cách xử lý text có thể bị diễn giải ngoài ý định. Không coi đây là lý do bỏ qua allowlist; hai lớp xử lý những rủi ro khác nhau.

### 7.2. Workbook có thể chứa dữ liệu ngoài vùng đang nhìn thấy

Kiểm soát sheet ẩn, cột ẩn, comment, công thức, named range, pivot/cache dữ liệu và các phần phụ mà template hoặc writer có thể mang theo.

Không dùng việc ẩn hoặc thu gọn làm cơ chế loại bỏ field. Nếu dùng lại template, phải biết nó có dữ liệu cũ hoặc liên kết nào, không chỉ kiểm tra header của sheet chính.

### 7.3. JSON, tài liệu và báo cáo có cấu trúc

Một exporter JSON có thể vô tình chứa object con đầy đủ; một báo cáo có thể giữ thông tin trong metadata hoặc nội dung không được hiển thị ở view chính.

Không dựa vào CSS, layout hoặc một lớp hiển thị để bảo đảm dữ liệu không có trong artifact. Các renderer phải dùng cùng projection/allowlist và không nhúng source object không cần thiết.

### 7.4. Header và tên file cũng là dữ liệu đầu ra

Dùng nhãn cột có kiểm soát, locale/format được hỗ trợ và tên file được tạo/xử lý phù hợp. Không để người gọi dùng tên field như một đường dẫn tài nguyên hoặc một biểu thức renderer.

Không đưa email, tài khoản nhận tiền hoặc thông tin bí mật vào tên file/URL chỉ để tiện tìm kiếm nếu không có nhu cầu và quyền phù hợp.

## 8. Job bất đồng bộ và thay đổi quyền trong lúc export

### 8.1. Ghi lại một đặc tả xác định

Job cần tham chiếu tenant, requester thực tế, export type, row scope/selection, filter, thứ tự field, representation, format và phiên bản definition/renderer liên quan.

Nếu dùng idempotency, fingerprint phải phản ánh những lựa chọn có ý nghĩa. Cùng key nhưng đổi từ field hạn chế sang field đầy đủ không được nhận một artifact mới ngoài hợp đồng.

Không cho một worker tự đọc entity hiện hành rồi dùng mọi field vì plan cũ không có một thuộc tính mới.

### 8.2. Worker không dùng quyền rộng của mình để mở dữ liệu

Service có thể truy cập nhiều tenant vì nhiệm vụ kỹ thuật, nhưng từng job vẫn phải gắn với kế hoạch được chấp nhận và thẩm quyền cụ thể.

Consumer cần kiểm tra nguồn job/message, tenant và artifact/operation tương ứng. Một `actorId`, field list hoặc scope tự khai trong message không tự là grant hợp lệ.

### 8.3. Mẫu chọn kiểm tra lại quyền hiện hành bắt buộc

Trong mô hình của bài, lúc job chạy cần xác lập lại quyền request export, row/field grant và các điều kiện hiện hành theo contract. Nếu một field không còn được phép, job không xuất field đó bằng quyền service.

Có thể chọn thất bại toàn job hoặc tạo representation hạn chế nếu hợp đồng chủ động hỗ trợ. Mẫu strict chọn không công bố artifact nếu plan yêu cầu không còn được phép; không âm thầm tạo báo cáo thiếu mà vẫn báo đã đáp ứng đầy đủ.

Nếu sản phẩm dùng một ủy nhiệm có thời hạn đã chốt lúc nhận job, phải mô tả rõ những điều kiện nào được bảo lưu và giới hạn của nó. Không mặc định mọi export job là quyền đọc vô thời hạn.

### 8.4. Chunking không tự giải quyết thu hồi giữa chừng

Job dài có thể gặp thay đổi membership, ownership hoặc field policy giữa các chunk. Cần biết đang dùng snapshot dữ liệu nào và quyền được kiểm tra theo điểm/thời gian nào.

Có thể kiểm tra các version/epoch liên quan ở ranh giới theo thiết kế, nhưng một lần recheck cuối không tự tạo bảo đảm thu hồi tức thời toàn cục. Nếu cần cam kết chặt, đường thu hồi và bước công bố/phát dữ liệu phải có giao thức đồng bộ đủ mạnh.

Không khóa một transaction lớn vô hạn chỉ để tránh phải định nghĩa semantics cho export dài.

### 8.5. Artifact tạm không được công khai trước khi hoàn tất

Ghi vào vùng staging có quyền phù hợp, không phát URL công khai cho file đang viết. Nếu job bị chặn hoặc thất bại, không để người gọi tải một phần dữ liệu đã được ghi trước đó ngoài contract.

Metadata job/artifact cần thể hiện chính xác field plan và trạng thái. Cơ sở dữ liệu và object storage thường là hai ranh giới; xử lý publish, orphan và cleanup theo giao thức thực tế, không giả định một transaction cục bộ rollback được mọi byte đã lưu.

## 9. Quyền tải, cache và vòng đời artifact

### 9.1. Kiểm tra quyền nhận file, không chỉ người tạo job

Status, metadata và download đều cần quyền phù hợp. Job ID hoặc đường dẫn khó đoán không thay authorization.

Theo chính sách, có thể cần quyền hiện hành đủ với field/row scope đã đóng gói hoặc một capability/ủy nhiệm còn hiệu lực. Chỉ kiểm tra `requesterId` có thể chưa đủ khi chia sẻ hồ sơ đã bị thu hồi hoặc role dữ liệu thay đổi.

Với artifact lớn, một lựa chọn là làm mất hiệu lực khi các căn cứ quyền/scope liên quan thay đổi rồi yêu cầu tạo lại. Cách khác cần có mô hình kiểm chứng phù hợp. Không khẳng định kiểm tra một role chung luôn chứng minh được quyền trên mọi dòng lịch sử trong file.

### 9.2. URL có thời hạn là một capability có giới hạn thực tế

Nếu phát URL mà chỉ cần nắm giữ là tải được, phải biết phạm vi và thời hạn của nó. Người mất quyền có thể còn dùng URL cũ đến hạn nếu cơ chế không kiểm tra/thu hồi lại.

Không hứa thu hồi tức thời chỉ vì endpoint cấp URL đã kiểm tra quyền tại lúc phát. Muốn kiểm soát khác cần cơ chế phân phối và thu hồi tương ứng.

Không dùng bucket công khai hoặc tên file chứa secret làm hàng rào chính.

### 9.3. Cache/reuse artifact theo đúng plan

Hai người dùng cùng filter không tự được chia sẻ cùng artifact nếu field grant hoặc row scope khác nhau. Key/cache binding phải phản ánh ngữ cảnh và projection được phép.

Role được mở rộng sau đó cũng không tự thêm cột vào một artifact đã đóng. Role bị thu hẹp cần xử lý khả năng nhận artifact theo policy, không chỉ dựa vào việc file đã từng tạo hợp lệ.

### 9.4. Retention và cleanup không làm mất dấu vết cần thiết

Quy định thời hạn lưu job/file, quyền truy cập vùng tạm và cách dọn artifact lỗi/mồ côi. Audit có thể giữ tham chiếu/digest/field manifest theo nhu cầu mà không giữ toàn bộ dữ liệu xuất vô hạn.

Server không thể thu hồi mọi byte người dùng đã tải hợp lệ trước đó. Cần nói đúng giới hạn, đồng thời chặn các lần tải hoặc chia sẻ mới ngoài hợp đồng.

## 10. Hành vi lỗi, manifest và audit

### 10.1. Không fallback sang xuất rộng khi plan lỗi

Field không được hỗ trợ, renderer không tương thích hoặc không tải được field policy phải không dẫn tới `exportAllProperties` hay `SELECT *` làm phương án dự phòng.

Không đánh dấu hoàn tất một file có field bị bỏ/đổi representation trái contract. Nếu có chế độ best effort, cần định nghĩa rõ và vẫn tuyệt đối không mở rộng quyền dữ liệu.

### 10.2. Manifest giúp kiểm tra điều gì đã được xuất

Có thể giữ field ID, thứ tự, representation, definition/renderer version, format và các tham chiếu snapshot/scope cần thiết. Số dòng/tổng hợp trong manifest cũng có thể nhạy cảm và cần quyền xem.

Không lưu nguyên dữ liệu gốc, token hoặc credential vào manifest chỉ để phục vụ truy vết. Digest có thể hỗ trợ kiểm chứng tính toàn vẹn nhưng không tự chứng minh dữ liệu ban đầu được phép xuất.

### 10.3. Audit theo cả vòng đời

Ghi ai yêu cầu, ai hoặc service nào thực thi, tenant, export type, plan đã được chấp nhận, các thay đổi quyền cần xử lý và việc công bố/tải theo chính sách.

Không chỉ log `export success`. Cần phân biệt đã nhận job, đang tạo, artifact sẵn sàng, bị từ chối, hết hạn và đã tải khi có yêu cầu ghi nhận đó.

Audit từ chối cần cơ chế không mất theo rollback nghiệp vụ. Lỗi log không được làm field trái quyền đi vào file.

### 10.4. Giới hạn tài nguyên bổ sung

Giới hạn số field, row/range, kích thước artifact, độ sâu quan hệ và số job đồng thời theo nhu cầu. Allowlist không tự làm một export hàng triệu dòng trở nên rẻ.

Không dùng áp lực tải làm lý do bỏ kiểm tra field hoặc chuyển sang renderer tổng quát ít kiểm soát hơn.

## 11. Kiểm thử export field allowlist

| Tình huống | Kỳ vọng |
|---|---|
| Field hợp lệ, đúng quyền và scope | Chỉ xuất representation được cấp |
| Field ngoài catalog, wildcard hoặc property path | Không reflection/đọc tùy ý; outcome đúng contract |
| Field tồn tại nhưng actor không được xuất | Không có giá trị nhạy cảm trong artifact hoặc phần phụ |
| Không có fields | Dùng default explicit, không toàn bộ entity |
| fields rỗng hoặc lặp | Đúng hợp đồng, không fallback mở rộng |
| Model/enum có thêm thuộc tính nhạy cảm | Export cũ không tự có cột mới |
| Masked field và raw field bị tráo | Không dùng grant cho masked để xuất đầy đủ |
| Quyền field chỉ đúng trên một phần row | Không áp quyền của dòng này cho mọi dòng |
| Chọn object requester/quan hệ nested | Không serialize toàn bộ entity qua fallback |
| Filter/sort/group theo field không được phép suy ra | Không tạo kênh rò rỉ ngoài policy |
| Worker có credential rộng hơn requester | Vẫn chỉ thực thi plan và thẩm quyền được chấp nhận |
| Mất quyền trước hoặc trong job | Không công bố artifact trái semantics đã chọn |
| Mất quyền sau tạo, trước tải | Quyền nhận artifact được kiểm tra theo contract |
| Cùng key nhưng đổi field/order/representation có ý nghĩa | Phát hiện xung đột hoặc xử lý đúng định nghĩa fingerprint |
| Reuse cache với actor/row scope khác | Không trả file của ngữ cảnh khác |
| Template có sheet/cột ẩn, comment hoặc dữ liệu cũ | Không mang field ngoài allowlist vào file đầu ra |
| Giá trị text có thể bị consumer hiểu thành công thức | Được xử lý theo chính sách serialization, không chỉ quote cú pháp |
| Job lỗi giữa chừng | File tạm không thành đường tải dữ liệu một phần ngoài quyền |

### 11.1. Kiểm tra artifact thực tế, không chỉ header

Với mỗi format được hỗ trợ, kiểm tra dữ liệu và các phần phụ liên quan. Một header đúng không chứng minh không có cột ẩn, object nested hoặc metadata thừa.

Kiểm tra cả source field nhạy cảm không xuất hiện dưới alias, trong note, tên file, log hoặc lỗi renderer. Không chỉ tìm một tên cột đã biết.

### 11.2. Fixture cần có dữ liệu được và không được phép

Tạo nhiều tenant/owner, field nhạy cảm riêng biệt và trường hợp quyền theo dòng. Nếu mọi row đều cùng quyền và mọi field đều công khai, writer xuất quá rộng có thể vẫn trông đúng.

Cần positive case cho export hợp lệ, bao gồm representation hạn chế được cấp. Một hệ thống từ chối mọi field không đáp ứng nghiệp vụ.

### 11.3. Kiểm thử vòng đời và version

Điều khiển thời điểm thu hồi quyền, đổi owner hoặc thay catalog/template giữa enqueue, chạy chunk, publish và download. Xác nhận không mở rộng field khi retry hoặc phục hồi job.

Kiểm tra cơ sở dữ liệu, worker và storage integration phù hợp với kiến trúc. Unit test một danh sách field không chứng minh renderer/template thực sự không chứa dữ liệu khác.

## 12. Tự rà soát thiết kế

Trước khi cho một loại export hoạt động, hãy trả lời:

1. Field catalog có explicit ID, nguồn và representation hay đang lấy mọi property?
2. Quyền export, row scope và field/row condition có được xét độc lập, đầy đủ không?
3. Default, danh sách rỗng, unknown field, wildcard và nested path được xử lý thế nào?
4. Masked representation có bị mở lại thành raw bằng một cờ input không?
5. Query và writer có chỉ lấy/ghi dữ liệu cần thiết cho plan không?
6. Format/template có bề mặt ẩn hoặc dữ liệu cũ ngoài sheet/view chính không?
7. Worker, retry và thay đổi quyền có giữ nguyên giới hạn dữ liệu được cấp không?
8. Artifact tạm, publish, cache và download có hợp đồng quyền rõ không?
9. Manifest/audit có nói được những field nào thực sự đã xuất mà không chứa bí mật thừa không?
10. Test có kiểm tra nội dung artifact thật qua toàn bộ vòng đời, thay vì chỉ kiểm tra header hoặc DTO không?

Export field allowlist có giá trị khi giới hạn được giữ từ yêu cầu, projection và renderer tới artifact cuối cùng và người nhận. Cột không được cấp phép phải không trở thành dữ liệu có thể lấy ra, kể cả qua nested object, template, cache hoặc một worker có quyền rộng hơn.

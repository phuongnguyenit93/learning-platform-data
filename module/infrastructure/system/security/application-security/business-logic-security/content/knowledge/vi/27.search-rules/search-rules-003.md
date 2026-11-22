# Search wildcard limits: giới hạn wildcard để bảo vệ tìm kiếm nghiệp vụ

## 1. Mục tiêu bài học

Trong chương **Search Rules** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **search wildcard limits** là các quy tắc giới hạn cách caller sử dụng ký tự đại diện và các chế độ tìm kiếm có khả năng mở rộng tập kết quả.

Wildcard có thể phục vụ nhu cầu hợp lệ như tìm theo đầu mã hồ sơ. Nhưng một truy vấn quá rộng hoặc quá đắt có thể hỗ trợ thu thập hàng loạt dữ liệu, dò đối tượng, làm cạn tài nguyên tìm kiếm hoặc khiến các chức năng nghiệp vụ khác không được phục vụ.

Mục tiêu không phải chặn mọi ký tự đặc biệt. Cần xác định cú pháp API, biểu diễn literal, mode được phép, scope, chi phí và cách trả kết quả.

Sau bài học, bạn có thể:

- Phân biệt wildcard, literal, prefix, substring và biểu thức tìm kiếm.
- Hiểu vì sao bind parameter chưa loại bỏ wildcard semantics.
- Thiết kế mode tìm kiếm và giới hạn theo field/quyền thay vì cho chạy pattern thô.
- Giữ tenant, object scope, count và pagination đúng khi truy vấn rộng.
- Áp giới hạn chi phí thực thi ngoài page size hoặc rate limit đơn giản.
- Kiểm thử cả lộ dữ liệu và hành vi truy vấn tốn tài nguyên.

## 2. Wildcard không có cùng nghĩa trong mọi lớp

| Ngữ cảnh | Ví dụ có thể gặp | Điều phải xác định |
|---|---|---|
| Pattern kiểu SQL LIKE | % và _ | Ký tự nào là wildcard, escape được cấu hình ra sao |
| Cú pháp glob hoặc search API | * hoặc ? | API thật sự hỗ trợ dạng nào và ở vị trí nào |
| Mode PREFIX | term là phần đầu cần tìm | Caller gửi literal hay tự thêm wildcard |
| Mode CONTAINS | Tìm chuỗi xuất hiện bên trong | Field, quyền và ngân sách thực thi được cấp |
| Regex | Một ngôn ngữ pattern riêng | Không được xem như wildcard đơn giản |
| Full-text query | Token/operator theo engine | Cần hợp đồng riêng; không chuyển nguyên input giữa các ngôn ngữ |

Không phải mọi dấu * trong JSON hoặc mọi dấu % trong dữ liệu đều là wildcard. Ý nghĩa đến từ parser và query được backend tạo.

Một mã sản phẩm thực sự có dấu _ hoặc % cần có cách tìm literal phù hợp, thay vì bị cấm chỉ vì trùng ký hiệu của một engine.

### 2.1. Ba cách tìm khác nhau

~~~text
EXACT:
  tìm đúng giá trị theo hợp đồng chuẩn hóa/so sánh.

PREFIX:
  tìm các giá trị bắt đầu bằng literal đã cung cấp.

CONTAINS:
  tìm literal xuất hiện ở bất kỳ vị trí nào.
~~~

PREFIX và CONTAINS không nên bị gộp thành “tự thêm dấu đại diện quanh input”. Chúng có tập kết quả và đặc tính chi phí khác nhau.

### 2.2. Wildcard thô có thể mở nhiều hơn caller dự kiến

Nếu input được đưa trực tiếp vào một pattern:

~~~text
prefix dài, cụ thể
    → có thể là tập nhỏ.

pattern gần như chỉ có wildcard
    → có thể khớp phần lớn tập dữ liệu trong scope.
~~~

Leading wildcard hoặc wildcard ở giữa có thể làm engine phải thực hiện nhiều công việc hơn một tìm prefix được hỗ trợ tốt. Chi phí cụ thể phụ thuộc engine, index, dữ liệu và kế hoạch truy vấn; không có một quy tắc hiệu năng tuyệt đối cho mọi backend.

## 3. Mối đe dọa đối với logic nghiệp vụ

| Hành vi | Rủi ro |
|---|---|
| Gửi pattern khớp gần như mọi bản ghi | Thu thập dữ liệu rộng hơn ý định chức năng tìm nhanh |
| Dò nhiều prefix ngắn | Quét dần danh mục khách hàng/hồ sơ |
| Dùng count/facet với wildcard | Suy ra tồn tại, phân loại hoặc số liệu ngoài quyền |
| Pattern đắt lặp song song | Chiếm worker, connection hoặc tài nguyên search dùng chung |
| Dùng cursor liên tục để vượt giới hạn trang | Biến tìm kiếm tương tác thành export không được cấp |
| Chuyển từ tìm field cụ thể sang mọi field | Lộ hoặc truy cập trường nhạy cảm ngoài hợp đồng |
| Làm mất scope khi pattern rỗng | Truy vấn toàn tenant hoặc toàn nền tảng ngoài ý định |
| Gọi lại query sau timeout bằng nhiều biến thể | Công việc cũ còn chạy trong khi công việc mới tiếp tục tăng |

Một wildcard không tự phá điều kiện tenant trong một query được viết đúng. Ví dụ tenant=A AND field LIKE pattern vẫn phải giữ biên A.

Rủi ro xuất hiện khi ứng dụng thiếu scope, làm rơi điều kiện, cho truy xuất quá rộng trong một scope lớn hoặc không bảo vệ tài nguyên trước truy vấn được phép nhưng quá tốn kém.

### 3.1. Authorization vẫn phải áp dụng cho mọi lần tìm

Actor được READ một số hồ sơ không mặc định được tìm trên mọi hồ sơ rồi lọc sau.

Search cần cùng tenant, object/field scope và chính sách tiết lộ như các đường đọc khác. Điều đó áp dụng cả list, count, autocomplete, facet, snippet và export.

Một giới hạn wildcard tốt không bù được query thiếu quyền theo đối tượng.

### 3.2. Query nhỏ không chắc có chi phí nhỏ

Một pattern ngắn có thể mở rộng rất lớn. Ngược lại, một chuỗi dài có thể vẫn mang wildcard ở vị trí làm truy vấn đắt.

Giới hạn số ký tự input cần kết hợp với loại query, field, độ chọn lọc và ngân sách thực thi. Không chỉ đặt maxlength trên ô nhập rồi coi công việc đã xong.

## 4. Chọn hợp đồng tìm kiếm tường minh

Một thiết kế dễ kiểm soát có thể dùng:

~~~json
{
  "field": "REQUEST_CODE",
  "mode": "PREFIX",
  "term": "REQ-2026",
  "pageSize": 20
}
~~~

Trong mode này, term là literal prefix. Server tạo query phù hợp; client không cần gửi % hoặc * để yêu cầu prefix.

### 4.1. Các trường có thẩm quyền khác nhau

| Input/điều kiện | Vai trò |
|---|---|
| field | Lựa chọn trong tập field server cho phép |
| mode | Lựa chọn trong tập mode được phép cho actor/field |
| term | Dữ liệu literal hoặc pattern có ngữ pháp được công bố |
| pageSize | Kích thước mong muốn trong giới hạn server |
| tenant/scope thực tế | Đến từ ngữ cảnh quyền đã kiểm chứng |
| deadline/cost/concurrency budget | Do server xác lập |
| sort/facet/total options | Chỉ được dùng nếu có hợp đồng và quyền phù hợp |

Không nhận một allowedFields hoặc unrestricted=true từ client làm thẩm quyền mở query.

### 4.2. Search trống và “liệt kê tất cả” là hai hành động khác nhau

Term thiếu, rỗng hoặc chỉ khoảng trắng không được tự đổi thành pattern khớp tất cả.

Nếu sản phẩm cần một màn hình browse hoặc danh sách mặc định, hãy định nghĩa endpoint/action, scope và giới hạn riêng. Một danh sách gợi ý công khai được chọn trước cũng không đồng nghĩa chạy wildcard trên dữ liệu riêng tư.

Không dùng fallback “query không hiểu thì tìm mọi thứ” để giúp UI có kết quả.

## 5. Giới hạn theo field, mode và quyền

Một policy minh họa có thể là:

| Field | Mode được hỗ trợ | Điều kiện mẫu |
|---|---|---|
| REQUEST_CODE | EXACT, PREFIX | Prefix có ít nhất 6 code point literal hợp lệ; đúng scope hồ sơ |
| PRODUCT_CODE | EXACT, PREFIX | Prefix tối thiểu 3 code point; tập sản phẩm được phép |
| CUSTOMER_NAME | EXACT, PREFIX có kiểm soát | Quyền tìm khách hàng; scope hẹp; prefix tối thiểu theo chính sách tên/ngôn ngữ |
| DESCRIPTION | Không mở wildcard thô trong API thông thường | Nếu cần, dùng chức năng tìm nội dung có hợp đồng/ngân sách riêng |
| SENSITIVE_ACCOUNT_REFERENCE | EXACT theo quyền riêng | Không mở prefix/contains mặc định |
| INTERNAL_AUDIT_CONTENT | Không tìm qua API công khai này | Chức năng điều tra có quyền và scope riêng nếu được cấp |

Các con số là ví dụ, không phải ngưỡng an toàn chung. Mã ngắn hợp lệ có thể vẫn được tìm bằng EXACT.

### 5.1. Minimum length phải đo literal thật

Nếu một cú pháp wildcard cho phép hậu tố *, không tính * vào số ký tự cụ thể.

Nếu dùng escaping cho backend, không tính chuỗi đã escape vì nó dài hơn dữ liệu literal.

Ví dụ một literal có một ký tự % có thể thành hai ký tự trong pattern sau escape. Điều đó không biến nó thành một prefix hai ký tự thực.

Quy ước đếm cần rõ: byte, code unit, code point hay một đơn vị khác. Không dùng String.length rồi mô tả như số ký tự người dùng cảm nhận nếu hai khái niệm không tương đương.

### 5.2. Không áp một ngưỡng máy móc cho mọi ngôn ngữ/field

Một prefix phù hợp cho mã hồ sơ có thể không phù hợp với tên người ngắn.

Thiết kế có thể kết hợp mode EXACT, thêm điều kiện phạm vi, chọn field khác hoặc một luồng tìm kiếm được kiểm soát, thay vì buộc mọi người nhập thêm wildcard cho đủ độ dài.

Ngưỡng prefix đủ dài cũng chưa chắc tạo tập nhỏ. Phân bố dữ liệu, index và scope thực tế vẫn cần được đánh giá.

### 5.3. Role rộng không tự bỏ mọi giới hạn chi phí

Operator được xem nhiều dữ liệu có thể cần truy vấn rộng hơn. Quyền đó nên đi kèm hợp đồng riêng về field, thời gian, concurrency và export, không phải một cờ bỏ mọi limit.

Quyền dữ liệu và quyền tiêu thụ tài nguyên là hai chiều liên quan nhưng không giống nhau.

## 6. Nếu phải hỗ trợ cú pháp wildcard cũ

Một hệ thống chuyển đổi từ UI cũ có thể cần nhận:

~~~text
ABC*
~~~

Một grammar hạn chế có thể là:

~~~text
Chỉ cho phép đúng một * ở cuối.
Phần trước * là literal prefix hợp lệ.
Không có wildcard ở đầu hoặc giữa.
Không có pattern chỉ gồm wildcard.
Không có operator/regex/field expression khác.
~~~

Các dạng như *ABC, A*BC hoặc ** bị từ chối theo hợp đồng này.

### 6.1. Parse thành ý định, không chuyển raw pattern xuống engine

~~~text
ABC*
    → SearchMode.PREFIX, literal=ABC
    → cùng policy/compiler với mode PREFIX tường minh.
~~~

Không thay * thành một chuỗi regex hoặc native query rồi chạy trực tiếp.

Nếu người dùng muốn tìm một dấu * thật, cung cấp mode literal phù hợp hoặc một cơ chế escape được đặc tả. Không tự phát minh nhiều tầng escape mơ hồ ở UI và backend.

### 6.2. Các ký tự của engine không tự là operator của API

Nếu grammar API chỉ hỗ trợ * cuối chuỗi, dấu % hoặc _ không tự trở thành wildcard chỉ vì backend dùng LIKE.

Chúng phải được xử lý như literal khi hợp đồng cho phép dữ liệu đó. Nếu field có grammar riêng không cho ký tự đó, từ chối như lỗi field; không vô tình chuyển sang query mở rộng.

Tương tự, dấu :, ngoặc hoặc từ khóa boolean không nên được truyền vào một search DSL như lệnh nếu API chỉ nhận literal.

### 6.3. Chuẩn hóa và parse cần cùng một hợp đồng

Quy định rõ normalization nào áp dụng cho từng field và trước bước nào.

Không kiểm tra pattern ở một dạng rồi để một lớp sau chuẩn hóa thành operator mới. Không normalize lại sau escape theo cách làm thay đổi ý nghĩa ký tự.

Các nguồn input lặp hoặc mâu thuẫn giữa query/body cần được decode nhất quán, không để validator thấy một term còn search engine dùng term khác.

## 7. Bind parameter không loại bỏ wildcard semantics

### 7.1. Hai mục tiêu khác nhau

Bind parameter bảo vệ cách đưa giá trị vào câu lệnh, tránh coi giá trị đó như cấu trúc SQL khi được sử dụng đúng.

Nhưng với LIKE, các ký tự pattern trong chính giá trị bound vẫn có ý nghĩa của pattern nếu chưa được xử lý.

~~~sql
WHERE request_code LIKE :pattern
~~~

Nếu :pattern chứa một wildcard khớp rộng, query vẫn có thể khớp rộng dù không có SQL injection.

Cần cả parameter binding và cách tạo pattern đúng hợp đồng.

### 7.2. Ví dụ dùng escape character tường minh

Ví dụ khái niệm dưới đây chọn ! làm escape character:

~~~sql
SELECT r.request_id, r.request_code
FROM purchase_request r
WHERE r.tenant_id = :verified_tenant_id
  AND r.branch_id IN (:authorized_branch_ids)
  AND r.request_code LIKE :pattern ESCAPE '!';
~~~

Cú pháp, collation và hành vi thực tế cần được xác nhận trên backend được chọn. Các giá trị được bind; field/column đến từ ánh xạ server cho phép.

Đây không phải query đầy đủ cho mọi policy. Các scope khác và projection vẫn phải áp dụng nếu có.

### 7.3. Escape literal rồi mới thêm wildcard do server sở hữu

~~~java
String escapeLikeLiteral(String literal) {
    return literal
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}

String prefixPattern(String literal) {
    return escapeLikeLiteral(literal) + "%";
}
~~~

Thứ tự có ý nghĩa: escape ký tự ! gốc trước khi thêm các ! cho % và _.

Ví dụ literal A_10% được biến thành:

~~~text
escaped literal: A!_10!%
prefix pattern:  A!_10!%%
~~~

Trong hợp đồng SQL minh họa, phần % được server nối sau cùng là wildcard prefix; % thuộc dữ liệu gốc đã được escape.

Không thêm % ở cả đầu và cuối nếu API chỉ cho phép PREFIX.

### 7.4. Identifier không phải value parameter

Client chọn field trong một enum/registry cho phép. Server ánh xạ nó sang column hoặc query component đã biết.

Không nối raw fieldName của client vào SQL/DSL rồi nghĩ bind :pattern đã bảo vệ cả query.

Sort field, direction, facet và các operator cũng phải có hợp đồng tương ứng.

## 8. Java minh họa compiler cho EXACT/PREFIX

Mã là phác thảo với các kiểu giả định, không phải ứng dụng tìm kiếm độc lập. Decoder đã giới hạn kích thước và kiểm tra các field bắt buộc trước bước này.

~~~java
CompiledSearch compile(
        VerifiedSearchContext context,
        SearchCommand command) {

    var field = fields.requireAllowed(
            context, command.field());
    var rule = searchRules.requireFor(
            context, field, command.mode());

    var literal = normalizers.forField(field)
            .normalize(command.term());

    terms.requireNonEmpty(literal);
    terms.requireWithinLength(literal, rule.maxTermLength());

    if (command.mode() == PREFIX) {
        int literalLength = literal.codePointCount(
                0, literal.length());
        terms.requireMinimumPrefix(
                literalLength, rule.minimumPrefixLength());
    }

    int pageSize = pages.requireAllowedSize(
            command.pageSize(), rule.maxPageSize());

    String boundValue = switch (command.mode()) {
        case EXACT -> literal;
        case PREFIX -> escapeLikeLiteral(literal) + "%";
    };

    return new CompiledSearch(
            field.serverColumn(),
            command.mode(),
            boundValue,
            pageSize,
            context.authorizedScope(),
            budgets.assign(context, rule));
}
~~~

Compiler phải giữ sự khác biệt: EXACT dùng phép so sánh đúng hợp đồng, PREFIX dùng pattern có escape phù hợp. Không lấy boundValue của EXACT rồi đưa vào LIKE ngoài ý định.

SearchCommand không chứa unrestricted, allowedTenantIds hoặc raw SQL. VerifiedSearchContext đến từ nguồn quyền được kiểm chứng.

Mã này chỉ bảo vệ cấu trúc/ý nghĩa query ở một lớp. Execution budget, scope thực tế và response disclosure vẫn cần được thực thi.

## 9. Scope phải tồn tại trong query thực tế

### 9.1. Pattern rộng không được làm mất tenant/object scope

Một query logic cần giữ dạng:

~~~text
mandatory tenant boundary
AND authorized object scope
AND allowed field/mode predicate
AND client filters được chấp nhận
~~~

Không bỏ scope khi:

- Term rỗng hoặc không parse được.
- Danh sách branch/project được phép là rỗng.
- Một query builder không tạo ra predicate.
- Backend báo pattern không hỗ trợ.
- Caller yêu cầu wildcard trên mọi field.

Tập scope rỗng phải cho kết quả rỗng/từ chối theo hợp đồng, không biến thành “không có filter”.

### 9.2. Điều kiện OR phải giữ đúng biên

Nếu API cho tìm trên nhiều field được phép, cần giữ nhóm logic rõ ràng:

~~~text
tenant/scope AND (predicate field-A OR predicate field-B)
~~~

Không để nhánh OR thoát ra ngoài biên tenant hoặc dùng một field caller không được tìm.

Query được viết với tenant ở đầu không tự bảo đảm engine thực thi nó trước về mặt hiệu năng. Cần cấu trúc logic đúng và đánh giá kế hoạch/backend thực tế.

### 9.3. Không chỉ lọc các dòng sau khi engine đã tính metadata

Một cách xử lý có thể làm lộ dữ liệu:

~~~text
Search engine tìm trên tập rộng.
Engine trả total, facet, snippet hoặc suggestion.
Application xóa các row ngoài quyền.
Application vẫn trả metadata của tập rộng.
~~~

Row bị che nhưng total/facet vẫn có thể tiết lộ tồn tại hoặc phân loại dữ liệu.

Áp scope ở nơi hỗ trợ truy vấn và kiểm chứng kết quả theo chính sách hiện tại. Không trả count/highlight/debug explanation rộng hơn view được phép.

### 9.4. Index có ACL vẫn cần quản lý độ mới

Search index có thể giữ tenant và ACL, nhưng membership/ownership có thể thay đổi sau khi index được cập nhật.

Cần cam kết về độ mới, cơ chế cập nhật và kiểm chứng tại điểm công bố dữ liệu. Nếu phải kiểm tra lại với nguồn có thẩm quyền, summary/count cũng phải có basis phù hợp.

Không tuyên bố thu hồi quyền tức thời chỉ vì document đã từng có field tenantId. Cũng không coi việc giấu field khỏi output là đủ nếu caller vẫn có thể search/filter theo field đó để dò dữ liệu.

## 10. Giới hạn chi phí theo nhiều lớp

### 10.1. Page size không giới hạn toàn bộ công việc

Trả 20 dòng có thể cần tìm hoặc xếp hạng trên rất nhiều dữ liệu. Exact count, facet, sort hoặc mở rộng pattern có thể tốn nhiều hơn phần trả row.

Nên xem từng lớp:

| Lớp | Giới hạn có thể áp dụng |
|---|---|
| Decode | Kích thước request, term và cấu trúc filter |
| Ngữ nghĩa query | Field/mode, vị trí wildcard, minimum literal prefix |
| Độ phức tạp | Số clause/filter, field expansion, operator được hỗ trợ |
| Execution | Deadline/cancellation và ngân sách backend khả dụng |
| Concurrency | Số search đang tiêu thụ tài nguyên theo actor/tenant |
| Output | Page size, tổng số dòng được duyệt qua, field/snippet |
| Aggregate | Exact count/facet/sort có quyền và hạn mức riêng |
| Export | Job/action riêng với giới hạn và audit phù hợp |

Khả năng đo/giới hạn cụ thể phụ thuộc backend. Không hứa có một cờ universal chặn mọi query đắt.

### 10.2. Ngưỡng phải dựa trên công việc đại diện

Ví dụ max page size 50 chỉ là một lựa chọn sản phẩm. Cần kiểm tra các prefix phổ biến, dữ liệu lệch, tập tenant lớn, filter ít chọn lọc và các quyền rộng.

Một prefix hiếm có thể nhanh trong khi prefix cùng độ dài khớp phần lớn dữ liệu. Vì vậy minimum length không thay một execution budget.

Chỉ thử trên dữ liệu mẫu vài chục dòng dễ bỏ sót vấn đề khi triển khai với dữ liệu thực tế lớn hơn.

### 10.3. Rate limit không thay concurrency/cost limit

Hai query cùng tính là một request có thể có chi phí rất khác.

Cần theo dõi chủ thể/tenant đã xác thực và tài nguyên dùng chung. IP có thể là tín hiệu phụ, nhưng không phải mô hình duy nhất cho một ứng dụng có nhiều người qua cùng mạng hoặc nhiều client cho một tài khoản.

Những endpoint liên quan như search, count, autocomplete và export cần ngân sách phù hợp với cùng bề mặt nghiệp vụ. Đừng bảo vệ một endpoint rồi để endpoint phụ chạy query rộng không giới hạn.

### 10.4. Client timeout không chứng minh query đã dừng

Server HTTP hết thời gian chờ nhưng search/DB có thể vẫn đang làm việc.

Cần dùng cơ chế cancellation/deadline phù hợp và kiểm chứng việc ngừng hoặc giới hạn công việc ở backend. Theo dõi cả công việc còn chạy sau khi client đóng kết nối.

Không chỉ giải phóng quota vì response đã kết thúc trong khi phần tốn tài nguyên vẫn còn tiếp diễn. Connection/session cần được trả về trạng thái an toàn trước khi tái sử dụng theo cơ chế thực tế.

### 10.5. Cắt output không được nói sai kết quả

Nếu hệ thống cho trả một phần kết quả khi chạm giới hạn, response cần phản ánh đúng:

~~~text
partial/truncated theo hợp đồng
số dòng thực sự được công bố
count là chính xác, ước lượng hay không có
khả năng tiếp tục có được hỗ trợ không
~~~

Không trả results=[] như thể không có match nếu thực tế query đã bị hủy/chưa đánh giá xong.

Không ghi hasMore=false nếu chưa đủ căn cứ. Nếu có cursor, continuation vẫn phải chịu ngân sách/scope, không là đường bỏ giới hạn query ban đầu.

## 11. Pagination không được biến thành export ngầm

### 11.1. Giới hạn một trang chưa giới hạn cả phiên tìm

Nếu mỗi trang nhỏ nhưng caller có thể lấy vô hạn và yêu cầu exact total trên từng trang, chức năng tìm tương tác có thể bị dùng như một export rộng.

Theo sản phẩm, có thể cần:

- Giới hạn số kết quả/độ sâu pagination của một search.
- Search session/cursor gắn với query và ngân sách.
- Endpoint export riêng cho tập lớn với quyền tương ứng.
- Cách thu hẹp query khi vượt hợp đồng.

Các giới hạn không thay object permission; chúng bổ sung ranh giới sử dụng của chức năng.

### 11.2. Cursor cần gắn với query và view

Cursor có thể được ràng buộc với tenant, actor/view scope, field, mode, literal đã chuẩn hóa, sort, result version và hiệu lực theo thiết kế.

Không dùng cursor của query cụ thể để đổi sang term rỗng hoặc một pattern rộng hơn. Không phục vụ cursor của một operator cho người khác mà không kiểm tra quyền.

Khi quyền hoặc query không còn phù hợp, yêu cầu bắt đầu lại hoặc từ chối theo hợp đồng. Không fallback thành browse toàn bộ.

### 11.3. Đường export có quyền rộng cần được cấp rõ

Nếu nghiệp vụ cần xuất tất cả kết quả trong scope, đó có thể là chức năng hợp lệ. Nó cần action, row/field scope, ngân sách, lịch xử lý và audit riêng.

Không mở leading wildcard/unlimited pages cho mọi user chỉ để hỗ trợ một nhu cầu báo cáo của nhóm vận hành.

## 12. Cache và lỗi không được mở query ngoài ý định

### 12.1. Cache giữ đúng scope và semantics

Các phụ thuộc có thể gồm:

~~~text
tenant và view scope
actor/nguồn quyền nếu kết quả phụ thuộc chúng
field, mode và literal canonical
filter/sort/pagination
phiên bản quyền, projection và dữ liệu cần thiết
~~~

Không chỉ cache theo term. Cùng một prefix ở hai tenant hoặc hai người có quyền khác nhau có thể cho kết quả khác nhau.

Cache hit không thay việc đáp ứng cam kết hiệu lực thu hồi. Cache cũng cần giới hạn dung lượng; số lượng term khác nhau có thể rất lớn.

### 12.2. Đừng cache lỗi như kết quả rỗng

Timeout hoặc nguồn quyền không truy cập được không có nghĩa dữ liệu không tồn tại.

Nếu lưu lỗi đó như một search rỗng thành công, client có thể đưa ra quyết định sai hoặc người dùng không tìm được hồ sơ hợp lệ. Hợp đồng cần phân biệt no match, query bị chặn và dependency/execution failure.

### 12.3. Public error nên giúp thu hẹp mà không tiết lộ dữ liệu

Các code minh họa:

~~~text
SEARCH_QUERY_INVALID
SEARCH_MODE_NOT_ALLOWED
SEARCH_QUERY_TOO_BROAD
SEARCH_BUDGET_EXCEEDED
SEARCH_CURSOR_NOT_USABLE
SEARCH_DEPENDENCY_UNAVAILABLE
~~~

Có thể thông báo prefix chưa đạt quy tắc công khai của field hoặc yêu cầu thêm phạm vi. Không cần trả “query của bạn khớp 12.345 hồ sơ khách hàng ngoài quyền” để giải thích vì sao bị chặn.

Lỗi phải kết thúc an toàn, không kích hoạt một query đơn giản hơn nhưng rộng hơn, hoặc chuyển nguyên pattern sang một engine khác.

## 13. Kiểm thử wildcard theo hợp đồng và backend thật

### 13.1. Fixture phân biệt literal và pattern

Chuẩn bị các mã sản phẩm minh họa:

~~~text
P1: A_10%X, actor được xem.
P2: AB10ZX, cùng tenant và actor được xem.
P3: A_10%Z, tenant khác.
P4: A_10%Y, cùng tenant nhưng ngoài object scope.
~~~

Nếu field cho phép các ký tự này, tìm PREFIX với literal A_10% chỉ được khớp các giá trị thật sự bắt đầu bằng literal đó và nằm trong quyền, như P1.

P2 giúp phát hiện việc _ và % bị hiểu thành wildcard. P3/P4 giúp phát hiện thiếu tenant hoặc object scope.

Không chỉ unit test hàm replace rồi kết luận engine sẽ có cùng semantics. Cần kiểm chứng cấu hình escape, binding và query thực tế trên backend được dùng.

### 13.2. Ma trận tình huống

| Tình huống | Điều phải kiểm chứng |
|---|---|
| EXACT với mã ngắn hợp lệ | Không bị áp nhầm minimum length của PREFIX |
| PREFIX vừa dưới ngưỡng | Bị chặn trước query nghiệp vụ theo policy |
| PREFIX đúng ngưỡng nhưng quá phổ biến | Execution budget vẫn được áp dụng |
| Literal chứa %, _ hoặc escape character | Không bị mở rộng ngoài ý nghĩa literal |
| Typed PREFIX có dấu * thật nếu field cho phép | Không tự đổi thành raw wildcard của API khác |
| Legacy chỉ có wildcard | Bị chặn theo grammar |
| Legacy wildcard ở đầu/giữa hoặc lặp | Không lọt sang engine dưới dạng pattern tự do |
| Field/mode không được cấp | Không fallback sang all-fields hoặc CONTAINS |
| Term thiếu/rỗng/trắng | Không chuyển thành match-all ngoài hợp đồng |
| Term quá dài hoặc filter quá nhiều | Giới hạn sớm, không cấp phát/compile query không cần thiết |
| Đầu vào sau normalization đổi ý nghĩa | Validator và compiler vẫn dùng cùng biểu diễn |
| Scope branch/project rỗng | Không bỏ filter và trả mọi dữ liệu |
| Pattern OR nhiều field | Các nhánh vẫn ở trong tenant/scope và field được phép |
| Row đã lọc nhưng total/facet rộng | Test phát hiện metadata ngoài quyền |
| Search index có quyền cũ | Output/count theo cam kết độ mới, không giữ quyền vô hạn |
| Page nhỏ nhưng query đắt | Không dùng page size làm bằng chứng chi phí thấp |
| HTTP timeout hoặc client đóng kết nối | Backend work được hủy/giới hạn theo thiết kế, không chỉ trả response sớm |
| Query bị cắt/hủy | Không báo no match hoặc hasMore=false thiếu căn cứ |
| Cursor đổi term/field/tenant | Không mở rộng query hoặc scope ngoài hợp đồng |
| Cache của actor/tenant khác | Không trả dữ liệu chéo scope |
| Dependency/query lỗi | Không cache như một search rỗng thành công |
| Autocomplete/count/API cũ | Không trở thành đường bỏ giới hạn chính |
| Export theo wildcard rộng | Cần đúng action, field scope và ngân sách export |

### 13.3. Kiểm tra không có lời gọi backend cho query bị chặn sớm

Các lỗi grammar, mode không hỗ trợ hoặc prefix không đạt policy có thể được chặn trước query dữ liệu.

Test nên xác nhận không có một nhánh fallback vẫn gọi backend với pattern rỗng hoặc rộng hơn.

Tuy nhiên, một mock xác nhận repository không được gọi chỉ chứng minh nhánh chặn sớm. Nó không thay kiểm thử hiệu năng và authorization của query được phép chạy.

### 13.4. Kiểm thử literal end-to-end

Với fixture P1–P4:

~~~text
Input:
  field = PRODUCT_CODE
  mode = PREFIX
  term = A_10%

Expected:
  Chỉ dữ liệu đúng literal prefix và scope được công bố.
  Không có P2 do wildcard semantics.
  Không có P3/P4 do tenant/object scope.
  Count/snippet/cursor không lộ P3/P4.
~~~

Thêm trường hợp escape character xuất hiện thật trong dữ liệu để phát hiện escape sai thứ tự hoặc escape hai lần.

Nếu backend/collation có quy tắc so sánh riêng, expected phải theo hợp đồng field đã xác định. Không dùng giả định từ một engine khác.

### 13.5. Kiểm thử cost bằng dữ liệu đại diện

Chuẩn bị dữ liệu có:

- Prefix hiếm và prefix rất phổ biến cùng độ dài.
- Tenant nhỏ và lớn.
- Phân bố tên/mã lệch.
- Filter chọn lọc và ít chọn lọc.
- Query có sort/count/facet theo các quyền được hỗ trợ.
- Nhiều request hợp lệ chạy song song.

Đo những chỉ số backend có thể cung cấp, như thời gian, tài nguyên, số công việc đang chạy hoặc mở rộng pattern. Acceptance criteria cần gắn với ngân sách của hệ thống, không một số thời gian universal.

Xác nhận cơ chế deadline/cancellation thực sự có tác dụng với công việc ở backend. Ném một timeout trong HTTP handler không chứng minh query phía sau đã dừng.

### 13.6. Kiểm thử pagination và quota liên quan

Một chuỗi nhiều trang vẫn phải giữ query canonical, tenant, quyền và giới hạn toàn phiên nếu hợp đồng có.

Thử dùng cursor với literal khác, mode khác, sort khác và actor khác. Server không được âm thầm tiếp tục một tập rộng hơn.

Kiểm tra search, autocomplete, count và export không có một đường ít kiểm soát hơn cho cùng mục tiêu thu thập dữ liệu.

Nếu có browse/gợi ý mặc định hợp lệ, kiểm thử rằng nó dùng tập/scope riêng, không phải wildcard trên mọi dữ liệu khi q rỗng.

## 14. Tình huống thực hành: limit 20 vẫn làm lộ dữ liệu và tốn tài nguyên

Một UI mô tả chức năng “tìm theo đầu mã”, page size tối đa 20. Backend lại tạo:

~~~text
pattern = "%" + clientTerm + "%"
~~~

và chỉ lọc các row ngoài quyền sau khi engine trả total.

Caller gửi một term có ý nghĩa wildcard đối với backend. Các lỗi có thể cùng xuất hiện:

1. API không xác định term là literal hay pattern.
2. Backend thực hiện CONTAINS dù UI mô tả PREFIX.
3. Ký tự pattern trong input không được xử lý đúng.
4. Page size nhỏ không hạn chế công việc tính total.
5. Count rộng còn được trả sau khi row đã lọc.
6. Timeout khiến client thử tiếp trong khi query cũ có thể còn chạy.

Cách thiết kế phù hợp:

~~~text
Field/mode được server cho phép.
Literal được chuẩn hóa và kiểm tra theo policy.
Query compiler escape theo engine và chỉ thêm operator được cho phép.
Tenant/object scope nằm trong query thực tế.
Count/output chỉ trong phạm vi được cấp.
Execution/concurrency budget được áp dụng.
Lỗi không đổi thành query rộng hơn hoặc no-match giả.
~~~

Chỉ thêm một kiểm tra “không có dấu %” không giải quyết toàn bộ vấn đề. Dữ liệu hợp lệ có thể cần tìm literal %, còn API khác có thể dùng wildcard khác hoặc một mode tốn kém dù không có ký hiệu nào.

### 14.1. Giới hạn tìm kiếm không hứa ngăn mọi sao chép dữ liệu hợp lệ

Nếu actor được cấp quyền đọc nhiều đối tượng, họ có thể có nhiều đường truy cập hợp lệ. Wildcard limits giúp bảo vệ hợp đồng tìm kiếm, chi phí và khả năng thu thập hàng loạt, nhưng không thay chính sách cấp dữ liệu.

Cần kết hợp row/field scope, action export, quota và audit theo nhu cầu. Không tuyên bố chỉ một ngưỡng prefix đã ngăn mọi hình thức enumeration.

## 15. Audit và tín hiệu vận hành

Thông tin có thể hữu ích:

~~~text
actor/tenant và action tìm kiếm
field/mode được chấp nhận
hình dạng query canonical theo mức cần thiết
scope/permission version liên quan
page/cursor hoặc search session
cost class, deadline và kết quả execution
số row công bố, basis của count và partial flag
reason code khi query bị chặn
~~~

Term có thể chứa tên, mã tài khoản hoặc dữ liệu nhạy cảm. Không log nguyên mọi query hoặc raw token theo mặc định.

Hash một prefix ngắn không tự làm nó thành dữ liệu ẩn danh. Chọn dữ liệu giám sát tối thiểu, bảo vệ quyền truy cập và quy định thời hạn lưu.

Các mẫu đáng theo dõi gồm nhiều prefix ngắn nối tiếp, query bị chặn lặp lại, concurrency cao, nhiều công việc còn chạy sau timeout hoặc chuyển qua count/autocomplete khi search chính bị giới hạn.

Các tín hiệu cần được xem trong ngữ cảnh nghiệp vụ. Một người tìm nhiều mã có thể đang làm công việc hợp lệ; mục tiêu là phát hiện sử dụng ngoài hợp đồng và điều chỉnh giới hạn có căn cứ.

Không đưa mọi term/resourceId thành một nhãn metric riêng không giới hạn.

## 16. Khung đặc tả wildcard limits

~~~text
Action và tập field được tìm:
Mode được hỗ trợ cho từng field/actor:
Term là literal hay pattern:
Grammar wildcard/escape nếu có:
Normalization và cách đếm literal prefix:

Giá trị missing/empty/whitespace và exact mã ngắn:
Minimum/maximum term, operator/clause/field limits:
Compiler và binding theo backend:
Tenant, row/field scope và độ mới của ACL:

Page size, tổng kết quả/độ sâu pagination:
Count/facet/sort/snippet được cấp:
Execution deadline, cancellation và concurrency budget:
Cache, cursor và export:
Hành vi partial/truncated/no match/error:

Audit, dữ liệu nhạy cảm và test đại diện:
Các đường autocomplete/count/legacy tương ứng:
~~~

## 17. Câu hỏi tự kiểm tra

1. Term của API đang là literal hay native pattern, và client có biết rõ không?
2. Bind parameter bảo vệ điều gì nhưng không loại bỏ wildcard semantics nào?
3. Minimum prefix đang đếm literal trước hay sau khi thêm/escape operator?
4. Vì sao page size nhỏ vẫn có thể tạo query đắt?
5. Term rỗng hoặc scope rỗng có làm query builder bỏ filter không?
6. Total, facet, snippet và suggestion có áp cùng quyền với row không?
7. Query có thực sự dừng khi HTTP handler timeout không?
8. Cursor hoặc export có thể vượt hợp đồng giới hạn tìm tương tác không?
9. Test nào phân biệt một ký tự %/_ thật trong dữ liệu với một wildcard?
10. Các ngưỡng có phù hợp field, ngôn ngữ và phân bố dữ liệu hay chỉ là một con số chung?

Nguyên tắc cần giữ là **caller được chọn một ý định tìm kiếm trong hợp đồng, còn server quyết định cú pháp thực thi, phạm vi và ngân sách được phép**. Wildcard, pagination và các đường phụ đều phải ở trong ranh giới đó.

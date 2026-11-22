# Sort direction validation: kiểm tra hướng sắp xếp theo hợp đồng

## 1. Một tham số nhỏ có thể thay đổi cấu trúc truy vấn

Một API nhận `sortBy` và `direction`, rồi ghép trực tiếp chúng vào câu truy vấn. UI chỉ gửi `ASC` hoặc `DESC`, nhưng người gọi có thể gửi chuỗi khác, nhiều giá trị hoặc một phần cú pháp sắp xếp bổ sung.

Ngay cả khi không dẫn tới injection, việc diễn giải direction không nhất quán có thể làm sai trang tiếp theo, trả nhầm response cache hoặc khiến client xử lý một tập hồ sơ khác với ý định.

**Sort direction validation** là việc kiểm tra và chuyển đầu vào hướng sắp xếp thành một giá trị domain giới hạn, rồi dùng giá trị đó nhất quán trong truy vấn, pagination và response.

Trong bảo vệ logic nghiệp vụ, hướng sort chỉ được thay đổi thứ tự biểu diễn trong phạm vi được phép. Nó không được mở rộng tenant, chọn field bí mật, ghi lại độ ưu tiên nghiệp vụ hoặc làm thay đổi quyền thực hiện action.

Mục tiêu chính:

- Chỉ chấp nhận những giá trị direction được hợp đồng công bố.
- Không để chuỗi client điều khiển cấu trúc SQL hoặc query ngoài khả năng được cấp.
- Phân biệt vắng tham số với sai dữ liệu.
- Giữ direction đồng bộ với tiebreaker, cursor và cache.
- Bảo vệ scope/field và ngân sách query độc lập với việc direction hợp lệ.

## 2. Định nghĩa ASC và DESC trong một hợp đồng cụ thể

### 2.1. Hướng tăng/giảm phụ thuộc thứ tự của field

`ASC` và `DESC` áp dụng lên một quan hệ thứ tự đã được xác định cho field. Chúng không tự định nghĩa collation văn bản, thứ tự trạng thái nghiệp vụ hoặc cách xếp null.

Ví dụ với timestamp hợp lệ, tăng dần thường đưa thời điểm sớm hơn lên trước. Với trạng thái như `DRAFT`, `APPROVED`, `PAID`, thứ tự chữ cái có thể khác thứ tự workflow mong muốn.

Không dùng direction để che việc field chưa có ngữ nghĩa sort rõ.

### 2.2. Mẫu hợp đồng đầu vào

Trong bài, một endpoint chọn:

```text
Tham số: direction
Số lần xuất hiện: tối đa một
Giá trị: ASC hoặc DESC, chấp nhận khác biệt hoa/thường ASCII
Giá trị chuẩn hóa: ASC hoặc DESC
Mặc định khi tham số vắng: DESC
Chuỗi rỗng, null được gửi rõ, giá trị khác hoặc tham số lặp: từ chối
Không chấp nhận khoảng trắng hoặc cú pháp bổ sung
```

Đây là một lựa chọn minh họa. Một API có thể chọn chỉ nhận chữ thường hoặc một dạng enum khác, nhưng mọi lớp phải cùng hiểu một contract.

### 2.3. Không mặc định mọi biểu diễn là tương đương

`ascending`, `down`, `true`, `1` hoặc `-1` không tự có nghĩa hợp lệ chỉ vì một thư viện lưu trữ có thể dùng một biểu diễn tương tự.

Nếu API muốn hỗ trợ alias hoặc số, phải ánh xạ tường minh sang tập giá trị nội bộ. Không đưa toàn bộ khả năng cấu hình của engine ra client một cách ngầm định.

### 2.4. Mặc định không phải cách xử lý mọi lỗi

`direction` vắng có thể dùng `DESC`. Nhưng `direction=` hoặc một giá trị không biết cần được xử lý theo hợp đồng, không âm thầm đổi thành default.

Fallback im lặng có thể làm client tưởng đang nhận thứ tự khác và che các lần gửi dữ liệu không hợp lệ. Nó cũng làm khó chẩn đoán khi cache hoặc cursor dùng một cách diễn giải khác.

## 3. Ranh giới tin cậy và ghép truy vấn

### 3.1. Không nối raw direction vào SQL

Một mẫu dễ sai:

```text
sql = baseSql + " ORDER BY " + clientField + " " + clientDirection
```

Tham số direction lúc này không chỉ là lựa chọn tăng/giảm mà có thể trở thành một phần cú pháp truy vấn.

Chặn riêng dấu chấm phẩy hoặc một số từ khóa không tạo một hợp đồng đầy đủ. Một chuỗi có thể bổ sung biểu thức hoặc tùy chọn sort mà không cần một statement mới.

### 3.2. Parameter binding không thay ánh xạ từ khóa cấu trúc

Placeholder dùng cho giá trị không phải một cơ chế chung để thay tên cột hoặc keyword `ASC`/`DESC`. Viết `ORDER BY :field :direction` không mặc định có nghĩa những placeholder đó được diễn giải như cấu trúc mong muốn.

Chọn cấu trúc từ những fragment/enum do server định nghĩa, còn giá trị filter/cursor dùng cơ chế bind phù hợp. Không coi mọi string concatenation đều giống nhau: ghép các fragment cố định từ allowlist khác với nối dữ liệu tùy ý của người gọi.

### 3.3. Direction hợp lệ chưa bảo vệ sort field

`direction=ASC` với `sortBy` là một field bí mật vẫn có thể tạo kênh suy đoán qua thứ tự. Một field tùy ý cũng có thể dẫn tới truy vấn đắt hoặc mapping sai.

Cần allowlist sort field theo endpoint và quyền, rồi ánh xạ field công khai sang biểu thức server đã kiểm soát. Không dùng tên field client gửi trực tiếp như tên cột/path nội bộ.

### 3.4. Chuẩn hóa xong chỉ dùng giá trị chuẩn hóa

Một validator kiểm tra prefix hoặc một bản string đã sửa không bảo vệ được bước sau nếu SQL vẫn dùng raw value ban đầu.

Nếu một logic chỉ ánh xạ prefix sang hằng số cố định, nó có thể tránh một số nguy cơ injection nhưng vẫn chấp nhận dữ liệu ngoài hợp đồng. Không trộn mục tiêu chống injection với việc định nghĩa grammar đúng.

Giá trị đã parse thành enum phải là đầu vào của planner/repository, không chỉ là một cờ để cho phép raw string đi tiếp.

## 4. Các biểu diễn và nguồn tham số cần kiểm tra

### 4.1. Tham số lặp

```http
GET /expense-requests?direction=ASC&direction=DESC
```

Nếu lớp kiểm tra lấy giá trị đầu còn mapper hoặc cache lấy giá trị cuối, request có hai cách hiểu. Mẫu của bài từ chối mọi lần xuất hiện lặp, kể cả cùng giá trị.

Adapter cần lấy được toàn bộ danh sách giá trị, không làm mất thông tin lặp trước khi validation chạy.

### 4.2. Alias và nguồn mâu thuẫn

Một hệ thống có thể hỗ trợ `direction`, `order`, `descending` hoặc direction nằm trong cursor. Cần có một cách diễn giải canonical và quy tắc khi các nguồn mâu thuẫn.

Không để query bị chặn còn một field trong body, header hoặc cursor vẫn đi thẳng vào engine. Nếu không hỗ trợ alias, đừng giữ một fallback không được tài liệu hóa.

### 4.3. Khoảng trắng, Unicode và locale

Nếu contract chỉ nhận ASCII `ASC`/`DESC` không có khoảng trắng, từ chối biểu diễn ngoài tập đó. Không cần tự đoán ý nghĩa của một ký tự trông giống chữ Latin.

Việc đổi hoa/thường nên có quy tắc không phụ thuộc locale môi trường. Kiểm tra alphabet trước cũng giúp không vô tình mở rộng grammar bằng một phép biến đổi Unicode ngoài ý định.

Không áp dụng quy tắc ASCII này cho nội dung người dùng một cách tổng quát. Nó phù hợp riêng với một enum giao thức nhỏ, không phải lý do từ chối tên tiếng Việt.

### 4.4. Giới hạn kích thước trước xử lý

Direction chỉ cần vài ký tự. Không nhận một chuỗi rất dài rồi mới uppercase, regex hoặc ghi nguyên văn vào log.

Kiểm tra type và độ dài sớm, giữ nhất quán việc decode của HTTP stack. Không parse lại cùng dữ liệu ở một lớp sau theo cách tạo thêm giá trị mà validator chưa kiểm tra.

## 5. Minh họa Java: parse thành enum giới hạn

Ví dụ dùng contract ở phần 2. Các exception là kiểu của ứng dụng; `values` phải giữ khác biệt giữa tham số vắng và tham số có giá trị rỗng.

```java
enum SortDirection {
    ASC,
    DESC;

    static SortDirection fromQueryValues(List<String> values) {
        if (values == null || values.isEmpty()) {
            return DESC;
        }
        if (values.size() != 1) {
            throw new InvalidSortDirection("DUPLICATE_SORT_DIRECTION");
        }

        String raw = values.get(0);
        if (raw == null || (raw.length() != 3 && raw.length() != 4)) {
            throw new InvalidSortDirection("INVALID_SORT_DIRECTION");
        }

        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            boolean asciiLetter = (c >= 'A' && c <= 'Z')
                    || (c >= 'a' && c <= 'z');
            if (!asciiLetter) {
                throw new InvalidSortDirection("INVALID_SORT_DIRECTION");
            }
        }

        return switch (raw.toUpperCase(Locale.ROOT)) {
            case "ASC" -> ASC;
            case "DESC" -> DESC;
            default -> throw new InvalidSortDirection("INVALID_SORT_DIRECTION");
        };
    }
}
```

Các đặc điểm có ý nghĩa:

- Chỉ mặc định khi vắng, không cho lỗi trở thành default.
- Reject duplicate trước khi chọn một giá trị.
- Giới hạn độ dài trước biến đổi chuỗi.
- Chỉ nhận đúng alphabet và hai token có chủ ý.
- Sau parse, lớp sau nhận enum thay vì raw direction.

Adapter cho JSON/form hoặc entry point nội bộ cần hợp đồng tương ứng. Không deserialize một map rộng rồi lấy direction bằng một phép ép kiểu khác với đường HTTP đã bảo vệ.

### 5.1. Không truyền raw value cùng enum để dùng lại

Có thể giữ raw input tối thiểu cho chẩn đoán được giới hạn theo chính sách, nhưng planner không được chọn nó làm keyword.

Một wrapper có cả `validatedDirection` và `rawDirection` rồi vô tình dùng trường raw sẽ phá ranh giới. Thiết kế chữ ký hàm để chỉ giá trị đã kiểm tra cần thiết đi tới lớp thực thi.

## 6. Ánh xạ sang order và continuation cố định

### 6.1. Một ví dụ chỉ hỗ trợ createdAt không null

Giả sử endpoint có sort field công khai `createdAt`, dữ liệu tương ứng không null và `id` là tiebreaker duy nhất trong scope.

```java
record SortSql(String orderBy, String continuationPredicate) {}

SortSql createdAtSql(SortDirection direction) {
    return switch (direction) {
        case ASC -> new SortSql(
                "e.created_at ASC, e.id ASC",
                "(e.created_at > :afterTime "
                        + "OR (e.created_at = :afterTime AND e.id > :afterId))");
        case DESC -> new SortSql(
                "e.created_at DESC, e.id DESC",
                "(e.created_at < :afterTime "
                        + "OR (e.created_at = :afterTime AND e.id < :afterId))");
    };
}
```

Các fragment đều do server định nghĩa. Timestamp, ID, tenant, filter và page limit vẫn được kiểm tra/bind theo hợp đồng, không nối từ raw request.

Chỉ thêm continuation predicate khi có cursor/position hợp lệ. Ở mọi nhánh, giữ nguyên predicate scope bắt buộc.

### 6.2. Direction của tiebreaker phải được định nghĩa

Ví dụ chọn ID cùng chiều với field chính. Một thiết kế có thể chọn tuple nhiều chiều khác nhau, nhưng comparator và cursor predicate phải khớp chính xác tuple đó.

Không đổi `ORDER BY` sang DESC mà vẫn dùng phép so continuation của ASC. Kết quả có thể lặp, bỏ sót hoặc đi sai chiều.

### 6.3. Scope không được phụ thuộc vào direction

Truy vấn vẫn cần tenant, owner/grant và policy field như với mọi query khác. Không để một nhánh DESC dùng repository khác thiếu filter hoặc một nhánh reverse bật chế độ quản trị.

Direction chỉ chọn thứ tự trong tập được phép. Count, facet và metadata cũng không được trở thành toàn cục ở một chiều sort khác.

### 6.4. Query builder/ORM không thay policy field

Một API builder có thể giúp tạo cấu trúc sort an toàn, nhưng vẫn cần giới hạn những field, relation và tùy chọn client được chọn.

Không suy rằng vì direction đã là enum nên có thể nhận mọi property path hoặc biểu thức. Chỉ ánh xạ các lựa chọn đã được endpoint và quyền hiện tại chấp nhận.

## 7. Null, collation và nhiều field sort

### 7.1. ASC/DESC không tự định nghĩa vị trí null

Nguồn dữ liệu có thể có hành vi mặc định khác nhau với null. Nếu field nullable được hỗ trợ, hợp đồng cần nói null đứng ở đâu và cursor xử lý phần null thế nào.

Không cho client nhét thêm `NULLS FIRST`, `NULLS LAST` hoặc cú pháp khác vào direction string. Nếu muốn hỗ trợ, dùng một lựa chọn cấu trúc riêng được validation/ánh xạ rõ.

### 7.2. Collation và thứ tự domain là vấn đề riêng

Sort văn bản có thể phụ thuộc collation, dấu, hoa/thường và cách lưu trữ. Đổi direction không giải quyết sự không nhất quán giữa comparator của client, DB và cursor.

Với trạng thái/độ ưu tiên nghiệp vụ, có thể cần mapping thứ tự riêng phía server. Không mặc định thứ tự chữ cái là thứ tự được nghiệp vụ yêu cầu.

Với tiền nhiều currency, cũng cần định nghĩa ý nghĩa sắp xếp thay vì so các con số khác đơn vị như cùng một đại lượng.

### 7.3. Multi-sort cần validation cho từng thành phần

Nếu hỗ trợ danh sách field, mỗi phần tử cần field và direction hợp lệ, thứ tự ưu tiên rõ và giới hạn số thành phần.

Cần quy tắc cho field lặp, direction thiếu và tiebreaker tự bổ sung. Không nhận một string `sort` tùy ý rồi truyền nguyên cho engine vì đã kiểm tra một token đầu tiên.

### 7.4. Không coi đảo một trang là sort toàn tập theo chiều ngược lại

Lấy 25 hồ sơ mới nhất rồi đảo mảng không giống truy vấn 25 hồ sơ cũ nhất. Nó chỉ đảo thứ tự hiển thị của cửa sổ đã chọn.

Đảo trang có thể phù hợp một tính năng phân trang lùi được thiết kế rõ, nhưng không thay truy vấn và continuation tương ứng cho một global sort mới.

## 8. Cursor và tính ổn định giữa các trang

### 8.1. Cursor phải ràng buộc với tuple sort

Một cursor có thể cần tham chiếu:

```text
sort field + direction + tiebreaker/null policy
+ vị trí cuối + filter fingerprint
+ tenant/ngữ cảnh quyền hoặc binding phù hợp
+ snapshot/version nếu contract có bảo đảm đó
```

Không dùng cursor của ASC với query DESC như thể hai vị trí tương đương. Nếu mismatch, trả outcome theo hợp đồng thay vì âm thầm bắt đầu lại hoặc đi sai phần dữ liệu.

### 8.2. Mặc định khi có cursor phải được thiết kế rõ

Một lựa chọn là mọi trang áp default DESC khi direction vắng, rồi yêu cầu tuple sau parse khớp cursor. Khi đó next link server cần lặp direction ASC nếu trang đầu chọn ASC; bỏ nó có thể gây mismatch hợp lệ theo contract.

Một lựa chọn khác là dùng tuple từ cursor đã được kiểm chứng khi tham số vắng, và chỉ đối chiếu khi client gửi direction. Cách này cần parser/planner giữ được khác biệt vắng và giá trị cụ thể.

Không để hai lớp áp hai quy tắc khác nhau. Việc chọn default trong ví dụ parser cần được đặt đúng vào hợp đồng pagination thực tế.

### 8.3. Chữ ký cursor không cấp quyền đọc

Cursor toàn vẹn vẫn cần đúng scope và các điều kiện hiện hành. Không dùng tenant, role hoặc field permission cũ trong cursor để mở quyền đã bị thu hồi.

Client thay direction bằng một giá trị hợp lệ cũng không được làm một cursor sai binding trở nên dùng được.

### 8.4. Tiebreaker không đóng băng dữ liệu đang thay đổi

Thứ tự xác định giúp phân trang trên một tập ổn định, nhưng insert/delete hoặc thay field sort giữa các request vẫn có thể làm vị trí thay đổi.

Cần nói rõ live pagination hay snapshot pagination. Không tuyên bố tuyệt đối không lặp/bỏ sót dưới mọi thay đổi đồng thời chỉ vì đã thêm ID vào ORDER BY.

Nếu workflow cần một tập lựa chọn cố định để xử lý sau, dùng cơ chế snapshot/selection phù hợp và vẫn kiểm tra quyền action khi thực thi.

## 9. Cache, field permission và tác động nghiệp vụ

### 9.1. Cache key phải giữ direction hiệu lực

Cache chỉ theo keyword/filter mà bỏ field hoặc direction có thể trả trang DESC cho request ASC. Điều đó làm sai kết quả và continuation dù dữ liệu vẫn cùng tenant.

Dùng giá trị canonical như ASC/DESC để tránh các entry khác nhau chỉ vì hoa/thường mà contract coi tương đương. Vẫn cần tenant, scope quyền, projection, cursor, page size và các yếu tố liên quan theo thiết kế cache.

### 9.2. Field không hiển thị vẫn có thể bị suy ra qua thứ tự

Không trả một field nhưng cho sort theo nó có thể tiết lộ thứ tự tương đối hoặc hỗ trợ suy đoán với filter khác. Quyền sort cần được xem cùng chính sách dữ liệu.

Một direction đúng grammar không hợp thức hóa sort trên thuộc tính riêng tư. Cũng không được dùng role từ query để mở field mà actor hiện không được chọn.

### 9.3. Thứ tự search không tự quyết định ưu tiên thực thi

Người dùng có thể đổi ASC/DESC để xem hồ sơ. Điều đó không tự cho phép thay ưu tiên chi trả, cấp quyền hoặc xử lý nghĩa vụ theo thứ tự có lợi cho họ.

Nếu sản phẩm cho phép chọn thứ tự thực thi, đó là một khả năng của command cần policy rõ. Không để một read sort vô tình ghi lại priority hoặc được batch worker hiểu là quy tắc ưu tiên bắt buộc.

### 9.4. Kết quả sort không thay authorization của command

Hồ sơ đứng đầu danh sách vẫn có thể không được actor duyệt hoặc đã đổi basis trước khi bấm thao tác. Command phải kiểm tra lại quyền, trạng thái và version.

Không dùng việc item xuất hiện trên một trang đã sort làm bằng chứng đã được cấp quyền thay đổi nó.

## 10. Giới hạn chi phí và hành vi lỗi

### 10.1. Hai direction hợp lệ vẫn có chi phí khác nhau theo triển khai

Khả năng tận dụng chỉ mục, sort và paging phụ thuộc nguồn dữ liệu và query plan. Không mặc định mọi field sort đều rẻ chỉ vì direction có hai giá trị.

Giới hạn page size, số field sort, độ sâu relation, range và các lựa chọn tốn tài nguyên. Đánh giá dữ liệu đại diện và plan thực tế khi bổ sung kiểu sort mới.

### 10.2. Không fallback sang đường rộng hơn khi direction sai

Invalid direction không được làm repository bỏ ORDER BY, bỏ pagination hoặc dùng một truy vấn toàn cục. Nếu contract từ chối, dừng theo lỗi đó trước công việc không cần thiết.

Nếu một hệ thống chủ động có fallback cho một trường hợp tương thích, phải ghi rõ và vẫn giữ mọi scope/ngân sách. Không dùng fallback không tài liệu hóa để che lỗi input.

### 10.3. Lỗi ổn định, không lộ cấu trúc nội bộ

Có thể dùng `400` với mã như `INVALID_SORT_DIRECTION`, `DUPLICATE_SORT_DIRECTION` hoặc lỗi cursor theo contract. Không cần trả câu SQL, stack trace hoặc danh sách toàn bộ field riêng tư của hệ thống.

Thông tin field được hỗ trợ trong response nên phù hợp endpoint và quyền người gọi. Không dùng lỗi sort làm một API khám phá schema nhạy cảm.

### 10.4. Audit và log có giới hạn

Có thể ghi direction canonical, field đã chọn, mã lỗi, tenant/actor và correlation ID theo nhu cầu. Giới hạn dữ liệu input thô được ghi để tránh log rất lớn hoặc chuỗi làm giả cấu trúc.

Một lần sort sai có thể là client bug hoặc alias cũ, không tự chứng minh ý đồ tấn công. Việc quan sát không thay validation và không cho phép request đi tiếp nếu điều kiện bắt buộc chưa đạt.

## 11. Kiểm thử sort direction validation

| Tình huống | Kỳ vọng theo contract mẫu |
|---|---|
| Không có direction | Dùng default đúng và nhất quán với cursor contract |
| ASC, DESC và biến thể hoa/thường ASCII được cho phép | Chuẩn hóa đúng thành enum |
| Rỗng, null gửi rõ, khoảng trắng, dấu hoặc số | Bị từ chối, không tự trở thành default |
| Alias không được hỗ trợ hoặc token viết sai | Không được suy đoán/nhận bằng prefix |
| Chuỗi rất dài, ký tự ngoài alphabet | Bị chặn trước biến đổi/tạo query đắt không cần thiết |
| Direction có thêm cú pháp sort | Không đi vào cấu trúc query như raw string |
| Query direction lặp, kể cả cùng giá trị | Xử lý đúng quy tắc lặp, không first/last-wins ngầm |
| Thay đổi locale môi trường | Grammar/canonical direction không đổi ngoài contract |
| Direction hợp lệ nhưng field ngoài allowlist/quyền | Không sort theo field bị cấm |
| ASC/DESC với nhiều giá trị field trùng nhau | Tiebreaker và continuation đúng tuple |
| Cursor ASC dùng cùng DESC hoặc binding khác | Không tiếp tục theo một cách hiểu sai |
| Tham số vắng ở trang sau | Đúng lựa chọn default/cursor đã tài liệu hóa |
| Field nullable hoặc multi-sort mới | Null policy và từng direction được kiểm tra đầy đủ |
| Cache đã có trang chiều ngược lại | Không trả nhầm thứ tự/next cursor |
| Đổi direction trong query tenant/owner khác | Scope và field permission không bị bỏ qua |
| Gửi request read sort | Không thay priority, owner, approval hoặc operation nghiệp vụ |
| Luồng hợp lệ cả hai chiều | Trả đúng thứ tự, không chặn tất cả để tránh lỗi |

### 11.1. Kiểm tra thứ tự và tập dữ liệu, không chỉ status

Với dataset ổn định, đối chiếu thứ tự theo comparator đã định và đi qua nhiều trang để kiểm tra tiebreaker/continuation. Tập ID nhận được phải đúng tập được phép theo query contract.

Không chỉ test một record hoặc các giá trị field hoàn toàn khác nhau; cần nhiều record cùng createdAt và ID khác nhau để bắt lỗi nhánh bằng nhau.

### 11.2. Kiểm thử qua parser và repository thật

Gửi tham số lặp và các biểu diễn biên qua HTTP stack. Unit test nhận sẵn enum không chứng minh raw input đã được kiểm tra đúng.

Integration test cần xác nhận các lựa chọn hợp lệ tạo đúng kết quả trên nguồn truy vấn, và input không hợp lệ không đi tới đường search đắt hoặc cấu trúc ngoài allowlist. Không cần buộc mọi test khớp nguyên string SQL nếu hành vi có thể chứng minh trực tiếp.

### 11.3. Tách tập ổn định với dữ liệu đang thay đổi

Kiểm tra đủ hai direction trên dữ liệu cố định trước, rồi thử insert/update/delete giữa các trang để xác nhận semantics live/snapshot đã công bố.

Không coi mọi thay đổi thứ tự khi dữ liệu mới xuất hiện là lỗi validation. Cũng không dùng tính biến động làm lý do chấp nhận vòng lặp cursor hoặc bỏ mất scope.

### 11.4. Regression khi mở rộng sort

Khi thêm field, null policy, alias hoặc multi-sort, cập nhật mapping, cursor binding, cache key, field authorization và test tương ứng.

Không chỉ thêm một giá trị vào UI rồi để generic binder mở mọi khả năng phía dưới. Hợp đồng cần được giữ xuyên suốt từ parser tới truy vấn và response.

## 12. Tự rà soát thiết kế

Trước khi nhận direction từ client, hãy trả lời:

1. Grammar, cách chuẩn hóa và default có được công bố rõ không?
2. Vắng mặt, rỗng, lặp, alias và nguồn mâu thuẫn được phân biệt thế nào?
3. Có raw direction nào vẫn được dùng sau khi parse enum không?
4. Sort field có allowlist và quyền riêng, hay chỉ direction được bảo vệ?
5. Keyword/order fragment và continuation operator có do server chọn cố định không?
6. Tiebreaker, null policy và multi-sort có cùng nghĩa với cursor không?
7. Direction vắng hoặc đổi ở trang sau có outcome xác định không?
8. Cache có giữ field/direction canonical cùng scope và các điều kiện cần thiết không?
9. Đổi thứ tự hiển thị có vô tình thay ưu tiên hoặc quyền thực thi nghiệp vụ không?
10. Test có chứng minh cả thứ tự đúng, phạm vi đúng và không có mutation ngoài ý định không?

Kiểm tra hướng sort đúng nghĩa là biến một chuỗi không đáng tin thành một lựa chọn nhỏ, có ngữ nghĩa rõ và được dùng nhất quán. Lựa chọn đó chỉ điều khiển thứ tự được phép; nó không được trở thành quyền thay cấu trúc truy vấn, dữ liệu nhìn thấy hoặc hành động nghiệp vụ.

# Page size limits: giới hạn kích thước trang ở phía server

## 1. Page size là một giới hạn tài nguyên, không phải gợi ý của UI

Một giao diện chỉ cho chọn 10, 25 hoặc 50 dòng. Backend nhận `pageSize` rồi truyền thẳng vào repository. Người gọi gửi một giá trị rất lớn, hoặc một giá trị đặc biệt mà lớp truy vấn diễn giải thành không giới hạn, khiến ứng dụng đọc và serialize lượng dữ liệu ngoài dự kiến.

Trong hệ thống nhiều tenant, một truy vấn như vậy có thể làm chậm những người dùng khác. Nếu điều kiện scope sai, nó còn khuếch đại tốc độ lấy dữ liệu ngoài quyền.

**Page size limits** là các giới hạn mà server áp dụng cho số đối tượng gốc được trả trong một trang, cùng quy tắc diễn giải đầu vào và ngân sách xử lý liên quan.

Giới hạn cần được giữ khi gọi trực tiếp API, dùng cursor cũ, thay account, đi qua cache hoặc bỏ qua hoàn toàn giao diện.

Trong bảo vệ logic nghiệp vụ, page size giúp giới hạn một phần tác động của mỗi request. Nó không thay authorization, tenant isolation, giới hạn tần suất hay quy tắc truy vấn dữ liệu nhạy cảm.

## 2. Giới hạn số item bảo vệ được gì?

| Vấn đề | Page size có giúp không? | Điều vẫn cần riêng |
|---|---|---|
| Đọc/serialize quá nhiều đối tượng trong một trang | Có, nếu giới hạn được đẩy xuống đường đọc thực tế | Giới hạn byte, quan hệ lồng nhau và bộ nhớ |
| Truy vấn sai tenant hoặc owner | Chỉ giảm lượng mỗi lần, không sửa lỗi quyền | Scope và authorization đúng |
| Gọi nhiều trang hoặc nhiều request đồng thời | Không tự ngăn | Quota, rate limit và kiểm soát đồng thời phù hợp |
| Sort, tìm kiếm hoặc count đắt | Không bảo đảm chi phí thấp | Kế hoạch truy vấn, chỉ mục, ngân sách thời gian/chi phí |
| Một item có dữ liệu rất lớn | Không đủ | Projection gọn, ngân sách response và tài nguyên phụ |
| Client thử sửa limit/cursor | Có nếu mọi đường đều áp chính sách hiện hành | Parser, contract và kiểm tra ngữ cảnh |

### 2.1. Trang nhỏ không làm dữ liệu trở thành được phép xem

Một API trả 1 hồ sơ của tenant khác vẫn vi phạm isolation. Không dùng `maxPageSize = 1` như cách bù cho predicate quyền bị thiếu.

Ngược lại, một người được phép xem nhiều hồ sơ vẫn có thể gây quá tải bằng cách đọc chúng không kiểm soát. Quyền đọc và ngân sách sử dụng tài nguyên cần cùng tồn tại.

### 2.2. LIMIT không đồng nghĩa chỉ xử lý đúng số dòng đó

Cơ sở dữ liệu có thể cần quét, join hoặc sắp xếp nhiều dữ liệu trước khi tạo ra một trang nhỏ. Một truy vấn count có thể đọc phạm vi lớn dù trang chỉ chứa 25 item.

Không cam kết chi phí luôn tỉ lệ với page size nếu chưa xét query plan, dữ liệu và chính sách lọc thực tế.

## 3. Viết hợp đồng min, default, max và đơn vị

### 3.1. Một hợp đồng minh họa

Giả sử một endpoint danh sách chọn:

```text
Tên tham số: pageSize
Vị trí: query string, tối đa một lần xuất hiện
Kiểu biểu diễn: chữ số ASCII thập phân, không dấu và không số 0 đầu
Giá trị nhỏ nhất: 1
Mặc định khi vắng tham số: 25
Giá trị lớn nhất: 100
Vượt giới hạn hoặc sai biểu diễn: từ chối request
```

Đây là các giá trị minh họa cho bài học. Giới hạn thật cần dựa trên kích thước dữ liệu, chi phí truy vấn, mức đồng thời và yêu cầu của endpoint, không chỉ sao chép một số phổ biến.

“100 item” ở đây nghĩa là 100 đối tượng gốc. Nếu có các collection con, phải có ngân sách riêng cho tổng dữ liệu mở rộng.

### 3.2. Chỉ dùng mặc định khi thực sự vắng mặt

Phân biệt:

```http
GET /expense-requests
GET /expense-requests?pageSize=
GET /expense-requests?pageSize=0
GET /expense-requests?pageSize=-1
```

Trong hợp đồng trên, request đầu dùng mặc định. Các request còn lại không hợp lệ; không tự biến chúng thành một chế độ unlimited hoặc che lỗi parse bằng giá trị mặc định.

Không dùng một số như `0`, `-1` hay chuỗi `all` làm cách bỏ giới hạn trên endpoint thường nếu đó không phải một khả năng riêng được cấp quyền và quản lý tài nguyên.

### 3.3. Reject và clamp là hai lựa chọn khác nhau

Một API có thể từ chối `pageSize` vượt max, hoặc hạ xuống max theo hợp đồng. Cả hai cần nhất quán; mẫu của bài chọn từ chối.

Nếu clamp, response nên cho client biết kích thước hiệu lực, và cursor/next link phải tính từ dữ liệu thực trả. Không để client tăng offset theo 10.000 trong khi server chỉ trả 100 mà không biết đã bị hạ giới hạn.

Clamp không phải lý do parse một chuỗi số vô hạn hoặc để tràn kiểu trước khi áp giới hạn. Kiểm tra kích thước và dạng biểu diễn vẫn cần đi trước phép chuyển đổi.

### 3.4. Max theo actor hoặc loại truy vấn phải lấy từ server

Nếu mỗi gói dịch vụ hay loại projection có cap khác nhau, server xác định cap từ policy/ngữ cảnh đáng tin. Không nhận `isAdmin`, `plan = enterprise` hoặc một max tùy ý trong body/query để mở rộng limit.

Một quyền quản trị đọc dữ liệu cũng không mặc định đồng nghĩa được dùng tài nguyên không giới hạn.

## 4. Parser phải chặn các biểu diễn gây hiểu khác nhau

### 4.1. Không ép kiểu quá dễ dãi

Theo hợp đồng minh họa, các giá trị sau không được chấp nhận:

```text
0, -1, +10, 10.5, 1e3, NaN, Infinity
chuỗi rỗng, khoảng trắng, số có 0 đầu, chữ số ngoài tập được công bố
chuỗi số quá dài hoặc vượt miền số nguyên
```

Một parser tổng quát có thể hiểu được một số biểu diễn trong danh sách, nhưng endpoint không cần hỗ trợ chúng chỉ vì thư viện có khả năng đọc.

Không chuyển qua số thực rồi làm tròn/cắt phần lẻ thành page size. Không để tràn số biến một giá trị lớn thành số âm hoặc một giá trị mặc định đặc biệt.

### 4.2. Tham số lặp phải có một nghĩa rõ

```http
GET /expense-requests?pageSize=10&pageSize=1000000
```

Nếu middleware đọc giá trị đầu còn repository dùng giá trị cuối, kiểm tra ở lớp ngoài không bảo vệ được truy vấn.

Mẫu chọn từ chối tham số lặp, kể cả khi hai giá trị giống nhau. Nếu framework hỗ trợ alias như `limit`, cần một nguồn canonical rõ và cách xử lý mâu thuẫn. Không để một tham số phụ đi vòng qua validator chính.

### 4.3. Decode và chuẩn hóa thống nhất

Adapter HTTP cần giữ được khác biệt vắng mặt/rỗng và mọi lần xuất hiện của tham số. Không chỉ lấy một giá trị từ multi-map rồi quên rằng còn giá trị khác.

Dữ liệu đã được HTTP stack decode theo hợp đồng không nên được một lớp phía sau diễn giải lại theo quy tắc khác. Kiểm tra và giá trị thực thi phải áp lên cùng một biểu diễn.

### 4.4. Kiểm tra trước khi phát sinh công việc đắt

Giới hạn độ dài, số tham số và dạng số có thể được kiểm tra sớm. Với cap theo actor, cần xác thực/ngữ cảnh phù hợp trước khi chọn cap đó.

Không thực hiện truy vấn lớn rồi mới kiểm tra rằng client yêu cầu quá nhiều. Một response lỗi sau khi đã tiêu tốn tài nguyên không đạt mục tiêu giới hạn xử lý.

## 5. Minh họa Java cho giá trị page size đã kiểm tra

Ví dụ dành cho hợp đồng cố định min 1, default 25, max 100. Các exception là kiểu của ứng dụng.

```java
record PageSize(int value) {
    static final int DEFAULT = 25;
    static final int MAX = 100;

    public PageSize {
        if (value < 1 || value > MAX) {
            throw new InvalidPageSize("INVALID_PAGE_SIZE");
        }
    }

    static PageSize fromQueryValues(List<String> values) {
        if (values == null || values.isEmpty()) {
            return new PageSize(DEFAULT);
        }
        if (values.size() != 1) {
            throw new InvalidPageSize("DUPLICATE_PAGE_SIZE");
        }

        String raw = values.get(0);
        if (raw == null || raw.isEmpty() || raw.length() > 3
                || raw.charAt(0) == '0') {
            throw new InvalidPageSize("INVALID_PAGE_SIZE");
        }

        for (int i = 0; i < raw.length(); i++) {
            char digit = raw.charAt(i);
            if (digit < '0' || digit > '9') {
                throw new InvalidPageSize("INVALID_PAGE_SIZE");
            }
        }

        return new PageSize(Integer.parseInt(raw));
    }

    int fetchLimitWithLookahead() {
        return Math.addExact(value, 1);
    }
}
```

Các điểm cần hiểu:

- Adapter phải truyền được toàn bộ danh sách giá trị và không chuyển `pageSize=` thành “tham số vắng”.
- Giới hạn 3 ký tự phù hợp riêng với max 100 và grammar mẫu. Nếu thay cap/grammar, phải cập nhật nhất quán, không sao chép hằng số một cách độc lập.
- Sau kiểm tra độ dài và chữ số, parse không đi qua một chuỗi số có thể tràn `int`.
- Canonical constructor vẫn kiểm tra miền giá trị, nên code nội bộ không tạo `new PageSize(-1)` để vượt đường HTTP.
- `fetchLimitWithLookahead` hỗ trợ đọc thêm một dòng để biết có trang sau; số trả cho client vẫn tối đa `value`.

Value object không tự kiểm tra quyền đọc hay chi phí truy vấn. Nó làm cho giới hạn số lượng trở thành một hợp đồng rõ ở lớp ứng dụng/repository.

## 6. Đẩy giới hạn xuống đường đọc thực tế

### 6.1. Không đọc toàn bộ rồi cắt trong bộ nhớ

Mẫu sau không bảo vệ tài nguyên ở tầng dữ liệu:

```text
repository.findAll(...)
→ tải toàn bộ entity và quan hệ
→ stream.limit(pageSize)
→ trả response nhỏ
```

Client chỉ thấy một trang nhỏ nhưng server có thể đã dùng lượng lớn DB I/O, bộ nhớ và thời gian serialize trung gian.

Repository cần nhận giá trị đã được giới hạn và áp dụng giới hạn trong truy vấn/cơ chế đọc tương ứng, trước khi materialize dữ liệu ngoài ngân sách.

### 6.2. Scope phải đứng trước phép chọn trang

Nếu lọc owner/tenant sau khi đọc trang toàn cục, kết quả có thể thiếu, metadata có thể lộ và server có thể phải quét nhiều trang để tìm đủ item được phép xem.

Ưu tiên đưa phạm vi đọc vào tập dữ liệu đầu vào của pagination. Nếu một policy không thể đẩy hoàn toàn xuống nguồn, cần ngân sách cho số candidate được xét và cơ chế continuation đúng, không lặp vô hạn đến khi đủ page size.

Không được bỏ authorization để lấp đầy một trang.

### 6.3. Ví dụ truy vấn owner-only có keyset

Ví dụ này giả định policy chỉ cho đọc hồ sơ thuộc membership đã xác minh:

```sql
SELECT id, state, created_at, amount, currency
FROM expense_request
WHERE tenant_id = :authorized_tenant_id
  AND owner_membership_id = :verified_membership_id
  AND (
      :after_created_at IS NULL
      OR created_at < :after_created_at
      OR (created_at = :after_created_at AND id < :after_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :bounded_fetch_limit;
```

Cú pháp và kế hoạch thực thi cụ thể cần phù hợp cơ sở dữ liệu. Tenant/membership lấy từ nguồn đã xác minh, cursor được kiểm tra, và `bounded_fetch_limit` không phải số thô client gửi.

Nếu có chia sẻ/phạm vi phòng ban, predicate phải biểu diễn policy đó đầy đủ. Tên biến `authorized` không tự tạo kiểm tra quyền.

### 6.4. Lookahead có giới hạn

Có thể lấy `pageSize + 1` dòng trong tập đã được phép để tính `hasNext`, rồi chỉ trả tối đa page size. Với mẫu max 100, số dòng gốc cho lookahead tối đa là 101.

Không kết luận có trang sau chỉ vì tồn tại một dòng ngoài phạm vi quyền. Không tính `hasNext`, count hoặc tổng từ tập toàn cục rồi chỉ lọc item trong response.

## 7. Giới hạn byte, quan hệ lồng nhau và query count

### 7.1. Một item có thể rất lớn

100 hồ sơ chỉ có ID/trạng thái khác với 100 hồ sơ chứa chứng từ nhúng, lịch sử và văn bản dài. Page size không giới hạn được byte nếu mỗi item không có giới hạn phù hợp.

Có thể dùng summary projection, tham chiếu tải tài liệu riêng theo quyền, giới hạn field dài và ngân sách response. Không trả BLOB lớn trong mọi item chỉ vì số item đã nhỏ.

### 7.2. Collection con làm tăng dữ liệu theo nhiều chiều

Nếu 100 parent mỗi parent mở rộng 100 child, tổng dữ liệu lớn hơn nhiều 100 item gốc. Cần giới hạn child size, độ sâu và tổng số node/byte theo hợp đồng.

Một tham số `include` hoặc `expand` cũng cần allowlist và quyền field. Không cho client chọn đồ thị bất kỳ mà vẫn áp cùng cap như view gọn.

### 7.3. Tránh N+1 không đồng nghĩa bỏ giới hạn

Batch-fetch hoặc join có thể giảm số query nhưng cũng có thể làm tăng số hàng trung gian. Cần đo hành vi thực tế và giữ giới hạn theo đối tượng gốc cùng ngân sách quan hệ.

Không tự khẳng định `LIMIT 100` trên một join luôn cho đúng 100 parent hoặc giới hạn mọi dữ liệu con. Ý nghĩa phụ thuộc truy vấn và cách dựng kết quả.

### 7.4. Nếu response chạm ngân sách byte

Chọn hành vi rõ: dùng view gọn hơn, trả lỗi phù hợp hoặc trả trang ngắn hơn với continuation chính xác nếu contract cho phép.

Không cắt JSON giữa chừng. Nếu dừng sớm, cursor phải tiến theo item thực đã trả, không theo toàn bộ candidate đã nạp mà client chưa thấy.

Nếu một item không thể vừa ngân sách, không được tạo vòng lặp trang rỗng với cursor không tiến triển. Cần một outcome xử lý được theo hợp đồng.

## 8. Offset, count và sort có ngân sách riêng

### 8.1. Page nhỏ vẫn có thể có offset rất lớn

Một request size 10 nhưng page number cực lớn có thể gây scan/skip đắt hoặc làm tràn phép tính offset nếu dùng kiểu không đủ lớn.

Kiểm tra miền page/offset, dùng phép tính có phát hiện tràn và giới hạn cửa sổ phân trang phù hợp. Không để một số âm sau tràn trở thành hành vi unlimited hoặc bỏ qua điều kiện.

Keyset/cursor có thể phù hợp cho đọc sâu, nhưng hiệu quả vẫn phụ thuộc chỉ mục, sort và predicate quyền. Nó không tự bảo đảm truy vấn rẻ trong mọi trường hợp.

### 8.2. Total count không bị giới hạn bởi page size

`includeTotal=true` có thể yêu cầu một phép đếm toàn phạm vi. Cần quyết định có hỗ trợ không, tần suất/chi phí nào cho phép và count là chính xác hay ước lượng.

Nếu ước lượng, ghi rõ semantics. Nếu tính count, áp cùng scope quyền trước khi đếm. Không trả tổng của cả tenant khi người gọi chỉ được xem phần của mình.

### 8.3. Sort và filter ảnh hưởng chi phí

Allowlist field sort và bộ lọc được hỗ trợ. Một sort trên field không phù hợp dữ liệu/chỉ mục có thể đắt dù chỉ trả vài dòng.

Không chèn trực tiếp tên field hoặc biểu thức query client gửi vào truy vấn. Cần ánh xạ sang lựa chọn được server hỗ trợ và kiểm tra giới hạn của range, search và điều kiện lồng nhau.

### 8.4. Ngân sách thời gian và kết nối

Cần kiểm soát thời gian truy vấn, số request đồng thời và vòng đời tài nguyên đọc theo kiến trúc. Client chậm hoặc đã ngắt không nên làm giữ tài nguyên không giới hạn.

Không coi streaming là cách bỏ mọi cap. Một stream lớn vẫn tiêu thụ kết nối, băng thông, CPU và có thể kéo dài thời gian truy cập dữ liệu nhạy cảm.

## 9. Cursor, cache và giới hạn thay đổi theo ngữ cảnh

### 9.1. Cursor không được quyền ghi đè cap hiện hành

Một cursor có thể chứa page size hoặc tham số đọc từ trước. Dù cursor có chữ ký, nó không tự cho phép giữ cap cũ sau khi policy hiện hành đã giảm.

Mỗi request cần áp giới hạn được phép dùng hiện tại theo hợp đồng. Nếu cursor ràng buộc size, thay đổi size phải được xử lý như mismatch. Nếu cursor chỉ ràng buộc vị trí, có thể cho đổi size nhưng vẫn áp min/max mới.

Chọn rõ một cách; không để query param bị chặn ở controller nhưng `cursor.limit` đi thẳng xuống repository.

### 9.2. Cursor cũng không phải credential

Xác minh tenant, chủ thể/scope, filter, sort và các ràng buộc cần thiết của cursor theo thiết kế. Vẫn kiểm tra quyền đọc cho trang tiếp theo.

Người dùng mất membership hoặc quyền đối tượng không được dùng cursor cũ để khôi phục phạm vi đã mất. Page size hợp lệ không làm cursor sai ngữ cảnh trở nên hợp lệ.

### 9.3. Next link dùng giá trị server đã chấp nhận

Nếu dùng clamp hoặc trả trang ngắn do ngân sách, response cần thể hiện size hiệu lực và continuation phù hợp. Không lắp next link từ một limit thô chưa kiểm tra.

Vị trí trang sau phải dựa vào item đã trả theo thứ tự xác định. Dùng tiebreaker ổn định khi cần để tránh vòng lặp hoặc bỏ sót do sort không rõ thứ tự.

### 9.4. Cache không được trả trang vượt quyền/cap của ngữ cảnh mới

Cache cần scope phù hợp tenant, actor/quyền đọc, filter, sort, cursor và size hiệu lực theo contract. Một entry được tạo dưới cap lớn không được dùng để trả quá cap hiện hành cho người khác.

Kiểm tra điều kiện cache và quyền trước khi trả dữ liệu. Xóa một key hoặc giữ TTL ngắn không tự bảo đảm thu hồi tức thời; cần độ mới phù hợp nguồn quyền và policy.

## 10. Giới hạn tần suất, export và hành vi lỗi

### 10.1. Một trăm trang nhỏ vẫn có thể là tải lớn

Page size chỉ giới hạn từng request. Cần quota/rate limit, kiểm soát mức đồng thời hoặc ngân sách chi phí theo actor/tenant khi hệ thống yêu cầu.

Không chỉ dựa vào IP trong mọi môi trường vì nhiều người có thể dùng chung mạng và một chủ thể có thể dùng nhiều địa chỉ. Chọn chiều kiểm soát phù hợp, giữ tính công bằng giữa tenant.

### 10.2. Export không phải `pageSize=all`

Nếu cần xuất dữ liệu lớn, có thể thiết kế một job riêng với quyền, phạm vi, quota, chunk và thời hạn artifact rõ ràng. Job vẫn phải bảo vệ dữ liệu và tài nguyên.

Không mở một cờ query bí mật để bypass cap cho mọi request có nhãn admin. Công cụ vận hành hoặc service nội bộ cũng cần thẩm quyền và ngân sách cụ thể.

### 10.3. Lỗi limit không được kích hoạt fallback không giới hạn

Nếu cấu hình cap động hoặc một nguồn bắt buộc lỗi, không dùng `Integer.MAX_VALUE`, bỏ `LIMIT` hoặc chuyển sang `findAll` để giữ request thành công.

Có thể dùng một mức hạn chế đã được policy cho phép và còn đủ căn cứ, hoặc trả lỗi dịch vụ phù hợp. Thiếu authorization không được bù bằng việc chỉ chọn một page size nhỏ.

### 10.4. Response lỗi và quan sát

Sai biểu diễn/vượt giới hạn trong mẫu có thể trả `400` với mã ổn định. Không cần trả stack trace hoặc thông tin query plan nội bộ.

Theo dõi requested/effective size trong phạm vi hợp lệ, lý do từ chối, chi phí truy vấn, byte response và tenant/actor đã xác minh khi cần. Giới hạn độ dài giá trị được log, không lưu nguyên chuỗi số khổng lồ hay payload nhạy cảm.

Hit rate hoặc số request bị chặn không tự chứng minh hệ thống được bảo vệ. Cần biết truy vấn hợp lệ ở cap tối đa có chi phí và tác động thế nào.

## 11. Kiểm thử page size limits

| Tình huống | Kỳ vọng theo hợp đồng mẫu |
|---|---|
| Không có tham số | Dùng 25, không unlimited |
| Giá trị 1 và 100 | Được chấp nhận; tối đa số item gốc tương ứng |
| Giá trị 101 hoặc lớn hơn max | Bị từ chối trước truy vấn nghiệp vụ đắt không cần thiết |
| Rỗng, 0, âm, có dấu hoặc khoảng trắng | Không biến thành mặc định/unlimited |
| Phần lẻ, số mũ, không hữu hạn hoặc chữ số ngoài grammar | Không ép kiểu dễ dãi |
| Chuỗi số quá dài hoặc vượt kiểu | Không tràn số, không parse tốn tài nguyên ngoài giới hạn |
| Tham số pageSize lặp, kể cả cùng giá trị | Bị xử lý đúng contract lặp, không first/last-wins ngoài ý muốn |
| Alias hoặc nguồn limit phụ | Không đi vòng qua cap canonical |
| Khởi tạo PageSize trực tiếp ngoài HTTP | Constructor vẫn chặn giá trị không hợp lệ |
| Repository được gọi ở max | Áp limit thực tế; lookahead chỉ trong ngân sách đã định |
| Lọc quyền và count/hasNext | Không lộ phạm vi ngoài quyền hoặc bỏ lọc để đủ trang |
| Một item hoặc collection con rất lớn | Ngân sách byte/depth/child được giữ |
| Size nhỏ nhưng offset/sort/count đắt | Có giới hạn bổ sung theo thiết kế |
| Cursor chứa limit cũ lớn hơn cap hiện hành | Không ghi đè cap mới hoặc policy được phép dùng |
| Cache được tạo ở actor/cap khác | Không trả sai scope hoặc quá size hiệu lực |
| Nhiều request song song ở max | Tuân thủ quota/đồng thời và mức tài nguyên đã kiểm chứng |
| Lỗi cấu hình/nguồn dữ liệu | Không fallback truy vấn toàn bộ |
| Trang hợp lệ dưới cap | Trả dữ liệu và continuation đúng, không chặn quá mức |

### 11.1. Kiểm tra lượng đọc và lượng trả

Không chỉ assert `items.size() <= 100`. Kiểm tra query/repository không tải toàn bộ rồi cắt, và không phát sinh graph dữ liệu ngoài ngân sách.

Lookahead hợp lệ có thể đọc thêm một dòng. Test phải theo thiết kế thật, không gắn số max trả cho client thành giới hạn tuyệt đối của mọi hàng trung gian mà không xét ý nghĩa.

### 11.2. Kiểm thử ranh giới HTTP thật

Gửi tham số lặp, rỗng và các dạng biểu diễn qua HTTP stack thực tế. Unit test một hàm nhận `int` không chứng minh parser không chọn nhầm giá trị hoặc đã giữ phân biệt vắng/rỗng.

Với scope, fixture cần có nhiều owner/tenant để phát hiện pagination hoặc count chạy trước lọc. Với cursor/cache, thử đổi account hoặc policy giữa các trang.

### 11.3. Đánh giá chi phí bằng dữ liệu đại diện

Kiểm tra truy vấn ở cap tối đa với dữ liệu, quan hệ và mức đồng thời phù hợp. Xem plan/chỉ mục và các nguồn chi phí như count, sort, expand, serialization.

Không coi một lần chạy nhanh trên bảng nhỏ là bằng chứng cap luôn an toàn. Chọn giới hạn từ ngân sách đo được và tiếp tục quan sát khi dữ liệu hoặc view thay đổi.

## 12. Tự rà soát thiết kế

Trước khi công bố một endpoint phân trang, hãy trả lời:

1. Min, default, max, đơn vị và hành vi reject/clamp có rõ không?
2. Vắng mặt, rỗng, âm, quá lớn, tràn số và tham số lặp được xử lý thế nào?
3. Có nguồn phụ như cursor, alias hoặc cờ admin vượt qua validator không?
4. Giới hạn được áp trước materialization hay chỉ cắt response trong bộ nhớ?
5. Scope quyền có đi trước pagination, count và hasNext không?
6. Byte, child collection, độ sâu và query count có ngân sách phù hợp không?
7. Offset, sort, search và total count có thể làm request nhỏ trở nên đắt không?
8. Cursor/cache có tái áp cap và quyền phù hợp ở mỗi ngữ cảnh không?
9. Request lặp, song song hoặc export có hàng rào tài nguyên riêng không?
10. Test có chứng minh cả lượng đọc thực tế và dữ liệu người gọi được phép nhận không?

Page size limit chỉ có giá trị khi server giữ nó xuyên suốt từ parser tới truy vấn và response. Nó cần đi cùng phạm vi quyền, ngân sách dữ liệu và kiểm soát chi phí để một trang hợp lệ không trở thành đường đọc vượt quyền hoặc sử dụng tài nguyên ngoài dự kiến.
